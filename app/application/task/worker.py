"""Application · Task · Worker（`docs/07` §10.2 / §12 P22–P28）。
覆盖 `docs/02` §15 / §39–§41 / §50 / §65 / §77 / §78 / §91 的执行语义。

权威来源
--------
- `docs/02` §50（`task`）—— Worker 的**原文顺序**：`取 Task ↓ 获取 Lease ↓ RUNNING ↓
  获取 Lock ↓ 执行 Pipeline ↓ Adapter ↓ 更新 Progress ↓ 保存 Result ↓ COMPLETED ↓
  释放 Lock`。
- `docs/02` §40（`task`）—— `Queue.get ↓ Lease ↓ RUNNING ↓ ExecutionService ↓ Progress ↓
  COMPLETED / FAILED ↓ Release`（同一顺序的另一份来源）。
- `docs/02` §15（`task`）—— Worker 循环的**原文实现**：`while self._running:` →
  `item = await self.queue.get()` → `await self.task_engine.run_task(item.task_id,
  self.worker_id)` → `finally: self.queue.task_done()`；`stop()` 只置 `_running = False`。
- `docs/02` §39（`task`）—— Worker Heartbeat Loop：周期续租；任务到终态即停。
- `docs/02` §41（`task`）—— `Lease expired? NO → leave running`（租约是执行期所有权凭据）。
- `docs/02` §91（`task`）—— `Task Engine 与 Lock`：**推荐** `Worker 获得 Task ↓
  Acquire Resource Lock ↓ Execute ↓ Release`，即锁必须覆盖实际执行期间。
- `docs/02` §65（`exec`）—— 锁作用域 `Acquire ↓ Execute ↓ Release`，**禁止异常情况下不释放**。
- `docs/02` §77 / §78（`task`）—— Retry / Timeout：`max_retries = 2` → 共 3 次尝试；
  `timeout = 0.1s` + `sleep(1s)` → `TIMEOUT`，再由重试策略决定是否重试。
- `docs/07` §10.2 —— 取消不得杀进程；恢复不得置 `COMPLETED`。
- `docs/07` §11 —— `STRUCTAI-5000`（任务不存在 / 未登记）、`STRUCTAI-5100`（超时）、
  `STRUCTAI-6100`（资源被锁）、`STRUCTAI-7000`（未装配执行器）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **`TaskExecutor` 是收窄契约，实现在 P36**（同 P14–P18 R38 的做法）：真正的执行编排是
   `ExecutionService`（`docs/07` §9 的 15 步主干），**属 P36**；本批**不**实现它，故这里声明
   **结构契约** `execute(task, *, context=None) -> Mapping[str, Any]`，由测试替身 / P36 满足。
   Application 层**不得** import `app.infrastructure`（`docs/07` §14.1），
   所以 Adapter 与执行流水线只能经此契约注入。
2. **未装配执行器 → `STRUCTAI-7000`，任务落 `FAILED`**：执行器是 Worker 的**必需**协作者；
   缺失属装配错误，必须显式暴露（`docs/07` §14.4），**不**静默当作成功。
3. **`finally` 逐条幂等释放**（`docs/02` §41 / §65）：资源锁（有句柄时）→ 并发额度
   （准入成功时）→ 租约；**任一释放失败都不得掩盖原异常**。因此**没有**
   「异常路径不释放」的出口。
4. **心跳是独立协程，结束即 `cancel()` 并 `gather`**（`docs/02` §39）：心跳失败
   （`TaskLeaseError`）只**停止循环**、不抛给主流程 —— 租约被别人抢走时，主流程会由后续
   CAS 失败自然退出，不需要心跳再抛一次。
5. **`software_instance_id` 取不到，故实例级并发与实例级锁降级为 `project_id`**：
   `tasks` 表**没有** `software_instance_id` 列（`docs/07` §4.3 #19），本批**不得改表**
   （`docs/07` §14.3）。因此 `ConcurrencyRequest.software_instance_id` 传 `None`
   （global / tenant / user 三级仍然生效，`docs/02` §18），资源锁落在
   `ResourceType.PROJECT` + `task.project_id` 上（`docs/02` §91 的唯一可用资源引用）。
   实例级串行（`SERIAL`）由 `Scheduler` 的实例策略承担（`docs/02` §20）。
6. **超时用 `asyncio.wait_for(..., timeout=default_timeout_seconds)`**：`docs/02` §78 的
   `timeout = 0.1s` 语义即「等待上限」；超时后协程被**取消**（`wait_for` 的语义），
   任务按重试预算决定 `RETRYING` 还是 `FAILED`（`docs/02` §77 / §78）。
7. **`result_json` 序列化失败也算执行失败**：`json.dumps(..., sort_keys=True)` 遇到
   不可序列化的结果会抛 `TypeError`；本模块把它归一化为 `STRUCTAI-7000` 并走**失败路径**，
   **不**写入半截结果（`docs/07` §14.4）。
8. **抢到租约之后的**全部**路径都在同一个 `try/finally` 内**（`docs/02` §41 / §65）：
   租约获取成功之后、`try` 之前的任何异常（`scheduler.try_acquire(...)` 会调用注入的
   `policy_for`；`_current(...)` 会读库）若不释放租约，会让该任务在 `lease_seconds`
   （默认 30s）内对**所有** Worker 都不可用 —— 那正是 §65「禁止异常情况下不释放」。
   故 `try:` 紧跟在 `lease.acquire()` 之后，`admitted` 初值 `False`、准入成功后置 `True`，
   `finally` 按 `admitted` 释放额度。
9. **未准入不丢队列**（`docs/02` §17 / §18）：队列项在 `run()` 的
   `finally: task_done()` 已被消费，若只释放租约就返回，任务会永远停在 `QUEUED` ——
   没人执行、也不报错。故未准入分支 `sleep(poll_interval)` 后**重新入队**
   （`_enqueue` 保留原始 `created_at`）。aging / 分布式重排留待后续批次
   （`docs/02` §14 的 `priority starvation`）。
10. **`run_task` 的预执行状态放宽为 `QUEUED` **或** `RUNNING`**（`docs/02` §20 / §42）：
    抢到租约后按 `str(task.status)` 做 CAS；`started_at` **只在为 `None` 时**写入
    （`RESUME` 不得覆盖原来的开始时间）。`RUNNING` 的接管即 `docs/02` §42 的 `RESUME`
    （原地继续）；`RecoveryService` 的 `RESUME` 分支因此只需**重新入队**，不必再改状态。
    其余状态 → 释放租约并返回当前记录（**不**覆盖别人的推进）。
11. **Worker 循环逐项异常隔离**（`docs/07` §14.4）：「单实例失败不得让整个服务器不可用」。
    `run()` 里 `run_task` 的异常只记日志（`logger.exception`，**stderr**）并 `continue`，
    `finally: task_done()` 照常执行 —— 一条坏任务（例如未登记 `task_id`）不得让 `while`
    循环整体退出、把队列中其余任务一起饿死。**日志绝不进 stdout**（P01 验收：0 字节）。
12. **`user_id` 由调用方注入，本批恒为空**（`docs/02` §18；见 `_concurrency_request`）：
    `tasks` 表**没有** `user_id` 列（`docs/07` §4.3 #19，本批不得改表），Worker 无从得知
    用户；P36 的 `ExecutionService` 可从 `IdentityContext.user_id` 注入。未注入时所有任务
    共用空键，`user_limit`（默认 `4`）在单进程内表现为**全局**上限。`tenant` 维度取
    `task.tenant_id`（可靠）；`software-instance` 维度本批取 `project_id`（同 §4.3 #19）。
13. **进度上报必须带租户**（`docs/02` §11 的租户隔离）：Worker 已知 `task_id → tenant_id`，
    故 `_report_progress` 透传 `tenant_id=` 给 `ProgressReporter.report` —— 否则进度写入
    只按 `id` 过滤，跨租户的 `task_id` 能改到别的租户的行。
分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库、`app.domain` 与**同层**的 `app.application.*`：
**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖 `app.infrastructure`
（持久化经 Domain 契约 `TaskStore`、执行经 `TaskExecutor` 注入），
也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Protocol

from app.application.execution.context import ExecutionContext
from app.application.resource.lock_manager import LockHandle, ResourceLockManager
from app.application.resource.lock_policy import LockPolicy
from app.application.task.lease import LeaseService, TaskLeaseError
from app.application.task.progress import ProgressReporter
from app.application.task.queue import TaskQueue
from app.application.task.scheduler import ConcurrencyRequest, Scheduler
from app.domain.enums import ResourceType, TaskStatus
from app.domain.errors import (
    InternalError,
    ResourceLockedError,
    StructAIError,
    TaskError,
    TaskTimeoutError,
)
from app.domain.protocols import OperationRegistry, TaskRecord, TaskStore

__all__ = [
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "DEFAULT_TASK_TIMEOUT_SECONDS",
    "EXECUTABLE_STATUSES",
    "WORKER_STAGE",
    "TaskExecutor",
    "TaskWorker",
]

WORKER_STAGE: Final[str] = "worker"
"""错误 `details.stage` 的固定取值（与 `lease` / `progress` 同口径）。"""

DEFAULT_POLL_INTERVAL_SECONDS: Final[float] = 0.5
"""默认轮询间隔（秒）—— `RuntimeConfig.task_poll_interval_seconds` 的默认值（`docs/02` §6）。"""

logger = logging.getLogger("structai.task")
"""Worker 循环的日志器（`docs/07` §14.3：只记 `task_id`，**不**记 secret / 原生 message）。

⚠️ 走 `logging` 的默认 `StreamHandler`（stderr）：`python -m app.main` 的
**stdout 必须保持 0 字节**（`docs/07` §12 P01 的验收口径）。
"""

DEFAULT_TASK_TIMEOUT_SECONDS: Final[int] = 3600
"""默认任务超时（秒）—— 一小时；`docs/02` §78 的超时语义（等待上限）。"""

EXECUTABLE_STATUSES: Final[frozenset[TaskStatus]] = frozenset(
    {TaskStatus.QUEUED, TaskStatus.RUNNING}
)
"""Worker **可接管**的预执行状态（`docs/02` §20 / §42；见模块裁决 10）。

- `QUEUED` —— 正常路径（`QUEUED → RUNNING`）；
- `RUNNING` —— `RESUME` 的接管（`docs/02` §42：原地继续，状态保持 `RUNNING`）。

其余状态一律**不**接管：释放租约后返回当前记录（**不**覆盖别人的推进）。"""

_EXECUTABLE_STATUSES: Final[frozenset[TaskStatus]] = EXECUTABLE_STATUSES
"""模块内引用别名（与公开常量同一对象，避免第二份定义）。"""


class TaskExecutor(Protocol):
    """任务执行契约（`docs/07` §9 的 `Adapter` + `Result Normalization` 收窄形态）。

    🔴 实现落在 **P36 的 `ExecutionService`**（`docs/07` §9 的 15 步主干），本批**不**实现；
    P22–P28 用测试替身满足本契约。这是 Application 侧的**收窄**契约
    （P14–P18 R38 对 Adapter 的同一做法）：Application 层不得 import
    `app.infrastructure`，故 Adapter 只能经此注入。

    注意实现**必须**返回**规范化**结果（`docs/02` §33 / §37），不得返回原生响应。
    """

    async def execute(
        self,
        task: TaskRecord,
        *,
        context: ExecutionContext | None = None,
    ) -> Mapping[str, Any]:
        """执行该任务并返回规范化结果（`docs/02` §48 的 `execute`）。

        Args:
            task: 待执行的任务快照（状态为 `RUNNING`）。
            context: 可选执行上下文（`docs/02` §5）。

        Returns:
            规范化结果（`Mapping`），将被序列化为 `tasks.result_json`。

        Raises:
            StructAIError: 执行失败 —— 归一化后的 20 码异常（`docs/02` §50）。
        """
        ...


@dataclass(frozen=True, slots=True)
class _ResourceRef:
    """满足 `LockPolicy.resolve` 鸭子类型要求的资源引用（`docs/02` §73）。

    `LockPolicy.resolve` 只读取 `resource_type` / `resource_id` 两个**字符串**属性
    （见 `lock_policy.py`），故本类型只需这两个字段（见模块裁决 5）。
    """

    resource_type: str
    resource_id: str


class TaskWorker:
    """任务 Worker：取任务 → 租约 → 并发准入 → 锁 → 执行 → 落库 → 释放（`docs/02` §50）。

    ⚠️ 持久化经 Domain 契约 `TaskStore` 注入：本模块**不**依赖 `app.infrastructure`
    （`docs/07` §14.1）。事务边界归调用方的 `UnitOfWork`（`docs/02` §16）——
    本类**从不** `commit` / `rollback`。

    🔴 取消 / 失败**绝不**杀 Python 进程（`docs/07` §14.4）：本模块只改状态与释放资源。
    """

    def __init__(
        self,
        *,
        worker_id: str,
        queue: TaskQueue,
        store: TaskStore,
        lease: LeaseService,
        executor: TaskExecutor | None = None,
        progress: ProgressReporter | None = None,
        scheduler: Scheduler | None = None,
        locks: ResourceLockManager | None = None,
        lock_policy: LockPolicy | None = None,
        operations: OperationRegistry | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        default_timeout_seconds: int = DEFAULT_TASK_TIMEOUT_SECONDS,
    ) -> None:
        """绑定 Worker 的必需协作者与可选端口。

        Args:
            worker_id: 本 Worker 的标识（写入 `lease_owner`）。
            queue: 任务队列（`docs/02` §11 / §13）。
            store: `docs/02` §34 的持久化入口。
            lease: 租约服务（`docs/02` §34–§38）。
            executor: 执行契约（`docs/02` §48；缺省时任务落 `FAILED`，见模块裁决 2）。
            progress: 进度上报（`docs/02` §31–§33）；缺省时不报进度。
            scheduler: 四级并发准入（`docs/02` §18）；缺省时不设并发上限。
            locks: 资源锁管理器（`docs/02` §91）；与 `lock_policy` / `operations`
                三者齐备时才抢锁。
            lock_policy: 锁策略（`docs/02` §74）。
            operations: 运行时 Operation Registry（`docs/02` §28）。
            poll_interval: 轮询间隔（秒）；缺省
                `RuntimeConfig.task_poll_interval_seconds`。
            default_timeout_seconds: 单次执行的等待上限（秒；`docs/02` §78）。
        """
        self._worker_id = worker_id
        self._queue = queue
        self._store = store
        self._lease = lease
        self._executor = executor
        self._progress = progress
        self._scheduler = scheduler
        self._locks = locks
        self._lock_policy = lock_policy
        self._operations = operations
        self._poll_interval = poll_interval
        self._timeout_seconds = default_timeout_seconds
        self._tenants: dict[str, str] = {}
        self._running = False

    # ===== 只读视图 =====

    @property
    def worker_id(self) -> str:
        """本 Worker 的标识。"""
        return self._worker_id

    @property
    def queue(self) -> TaskQueue:
        """被绑定的任务队列。"""
        return self._queue

    @property
    def running(self) -> bool:
        """是否处于运行态（`stop()` 之后为 `False`）。"""
        return self._running

    @property
    def default_timeout_seconds(self) -> int:
        """单次执行的等待上限（秒）。"""
        return self._timeout_seconds

    def registered_tenants(self) -> Mapping[str, str]:
        """已登记的 `task_id → tenant_id`（只读快照；诊断用）。"""
        return dict(self._tenants)

    # ===== `docs/02` §15：循环 / 停机 / 登记 =====

    async def run(self) -> None:
        """Worker 主循环（`docs/02` §15 的原文实现 ＋ §38 的优雅停机）。

        循环条件：`self._running and not queue.closed`。取项用
        `asyncio.wait_for(queue.get(), poll_interval)`；超时即**继续轮询**，
        因此 `stop()` + `queue.shutdown()` 能让本方法**自然返回** ——
        **不**取消协程、**不**杀进程（`docs/07` §14.4）。

        取到项后 `try: await self.run_task(item.task_id, self.worker_id) except
        Exception: logger.exception(...) finally: queue.task_done()`（`docs/02` §15 的
        `finally`）。逐项异常隔离：**单条**坏任务不得让整个 Worker 循环退出
        （`docs/07` §14.4「单实例失败不得让整个服务器不可用」；见模块裁决 11）。

        日志走 stderr（`logging` 的默认 `StreamHandler`），**stdout 必须保持 0 字节**。
        """
        self._running = True
        while self._running and not self._queue.closed:
            try:
                item = await asyncio.wait_for(self._queue.get(), self._poll_interval)
            except TimeoutError:
                continue
            try:
                await self.run_task(item.task_id, self._worker_id)
            except Exception:  # noqa: BLE001 —— 逐项隔离，见模块裁决 11
                logger.exception("task execution failed: %s", item.task_id)
            finally:
                self._queue.task_done()

    def stop(self) -> None:
        """请求停机（`docs/02` §15 的 `stop()`）。

        ⚠️ 只置 `_running = False`：**不**杀进程、**不**取消协程、**不**丢弃队列中
        已取出的项（`docs/07` §14.4）。
        """
        self._running = False

    def register(self, task: TaskRecord) -> None:
        """登记 `task_id → tenant_id`（`submit` 路径调用；`docs/02` §11）。

        `TaskStore` 的读取是**租户作用域**的（`docs/02` §11），而队列项只携带
        `task_id`（`docs/02` §12 的 `QueueItem`），故 Worker 必须持有租户映射。
        """
        self._tenants[task.id] = task.tenant_id

    # ===== `docs/02` §50：单任务执行 =====

    async def run_task(self, task_id: str, worker_id: str) -> TaskRecord:
        """执行一个任务（`docs/02` §50 的十步顺序；`docs/07` §10.2）。

        顺序（不可换）：取租户与任务 → 抢占租约 → 并发准入 → `QUEUED → RUNNING` →
        资源锁 → 心跳 → 执行（带超时）→ 落结果 / 超时 / 失败 → `finally` 逐条释放。

        Args:
            task_id: 任务标识。
            worker_id: Worker 标识（写入 `lease_owner`）。

        Returns:
            执行后的 `TaskRecord`（**真实**状态；被拒 / 未准入时返回当前记录，**不**执行）。

        Raises:
            TaskError: `STRUCTAI-5000` —— 未登记的 `task_id`（`reason = "unknown_task"`）。
        """
        tenant_id = self._tenants.get(task_id)
        if tenant_id is None:
            raise TaskError(
                "Task not found",
                details={"stage": WORKER_STAGE, "reason": "unknown_task"},
            )
        task = await self._store.get(task_id, tenant_id)
        if task is None:
            raise TaskError(
                "Task not found",
                details={"stage": WORKER_STAGE, "reason": "unknown_task"},
            )

        # 2. 租约（`docs/02` §35 / §80）：抢不到就**不执行**（Worker B 不得执行）。
        try:
            task = await self._lease.acquire(task_id, worker_id)
        except TaskLeaseError:
            return await self._current(task_id, tenant_id, task)

        # 3. 见模块裁决 3 / 8：抢到租约之后的**全部**路径都在 `try/finally` 内 ——
        #    准入与预执行 CAS 本身抛异常时同样要释放租约（否则 30s 内谁都抢不到）。
        request = self._concurrency_request(task)
        admitted = False
        lock_handle: LockHandle | None = None
        heartbeat: asyncio.Task[None] | None = None
        try:
            # 4. 并发准入（`docs/02` §18）：未准入 → 见模块裁决 9（**不丢队列**）。
            if self._scheduler is not None:
                decision = await self._scheduler.try_acquire(request)
                if not decision.admitted:
                    return await self._not_admitted(task_id, tenant_id, task)
                admitted = True

            # 5. 预执行状态 CAS（`docs/02` §20 / §42）：`QUEUED` 与 `RUNNING` 都可接管。
            #    `RUNNING` 的接管 = `docs/02` §42 的 `RESUME`（见模块裁决 10）。
            if TaskStatus(str(task.status)) not in _EXECUTABLE_STATUSES:
                return await self._current(task_id, tenant_id, task)
            running = await self._store.transition(
                task_id,
                expected=str(task.status),
                new=str(TaskStatus.RUNNING),
                fields=None if task.started_at is not None else {"started_at": self._now()},
            )
            if not running:
                # 状态已被别人改过（例如被取消）→ 保持真实状态返回（`docs/07` §14.4）。
                return await self._current(task_id, tenant_id, task)
            current = await self._current(task_id, tenant_id, task)

            # 5. 资源锁（`docs/02` §91）：三者齐备时才抢；被锁 → 走失败路径。
            try:
                lock_handle = await self._acquire_lock(current)
            except ResourceLockedError as error:
                return await self._mark_failed(current, error)

            # 6. 心跳（`docs/02` §39）：独立协程，`finally` 里 `cancel` + `gather`。
            heartbeat = asyncio.create_task(self._heartbeat_loop(task_id, worker_id))

            # 7. 执行（`docs/02` §78 的等待上限）。
            try:
                result = await asyncio.wait_for(
                    self._execute(current),
                    timeout=self._timeout_seconds,
                )
                payload = self._encode_result(result)
            except TimeoutError:
                return await self._mark_timeout(current)
            except Exception as error:  # noqa: BLE001 —— 归一化，见模块裁决 2 / 7
                return await self._mark_failed(current, error)

            # 7b. 成功：进度 100 → `PROCESSING` → `COMPLETED`。
            await self._report_progress(task_id, 100, tenant_id)
            return await self._mark_completed(current, payload)
        finally:
            # 10. 见模块裁决 3：逐条幂等释放，任一失败都不得掩盖原异常。
            if heartbeat is not None:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
            await self._release_lock(lock_handle)
            if admitted and self._scheduler is not None:
                await self._scheduler.release(request)
            await self._release_lease(task_id, worker_id)

    # ===== 内部：执行前后 =====

    def _concurrency_request(self, task: TaskRecord) -> ConcurrencyRequest:
        """构造并发准入请求（`docs/02` §18；实例维度见模块裁决 5）。

        ⚠️ **`user_id` 由调用方注入**（`docs/02` §18 的 user 维度；见模块裁决 12）：
        `tasks` 表**没有** `user_id` 列（`docs/07` §4.3 #19，本批**不得改表**），
        Worker 因此无法从任务行得知用户。P36 的 `ExecutionService` 可从
        `IdentityContext.user_id` 给出该值（那时把本方法换成按调用方上下文构造）。
        **未注入**时所有任务共用空键 `""`，于是 `user_limit`（默认 `4`）在**单进程**内
        退化为一个**全局**上限 —— 这是本批的已知限制，不是「user 维度已实现」。

        同理：`tenant` 维度取 `task.tenant_id`（可靠）；`software-instance` 维度本批取
        `project_id`（`docs/07` §4.3 #19 无 `software_instance_id` 列）。
        """
        return ConcurrencyRequest(
            task_id=task.id,
            tenant_id=task.tenant_id,
            user_id="",
        )

    async def _not_admitted(
        self,
        task_id: str,
        tenant_id: str,
        task: TaskRecord,
    ) -> TaskRecord:
        """并发未准入：**不丢队列**（`docs/02` §17；见模块裁决 9）。

        队列项已在 `run()` 的 `finally: task_done()` 被消费，若不重新入队，任务会永远
        停在 `QUEUED` —— 既没人执行，也不报错。故此处：

        1. 先 `asyncio.sleep(poll_interval)`（避免忙等把 CPU 打满）；
        2. 再 `_enqueue(task)`（保留**原始** `created_at`，`docs/02` §17 的排序键）；
        3. 返回当前记录（**真实**状态，仍然是 `QUEUED`）。

        租约由调用方的 `finally` 释放（见模块裁决 3 / 8）。

        ⚠️ aging / 分布式重排**留待后续批次**（`docs/02` §14 的 `priority starvation`）：
        本批只保证「不丢队列」。
        """
        await asyncio.sleep(self._poll_interval)
        await self._enqueue(task)
        return await self._current(task_id, tenant_id, task)

    async def _acquire_lock(self, task: TaskRecord) -> LockHandle | None:
        """按 Operation + 项目资源抢锁（`docs/02` §91 / §74）。

        Returns:
            锁句柄；三者未齐备、Operation 未登记或任务无 `project_id` 时返回 `None`
            （此时**不**抢锁，而不是抢一把没有意义的锁）。

        Raises:
            ResourceLockedError: `STRUCTAI-6100` —— 资源被别的任务占用。
        """
        if self._locks is None or self._lock_policy is None or self._operations is None:
            return None
        if not task.project_id:
            return None
        definition = await self._operations.get(task.operation)
        if definition is None:
            return None
        resource = _ResourceRef(
            resource_type=str(ResourceType.PROJECT),
            resource_id=task.project_id,
        )
        return await self._locks.acquire_lock(
            self._lock_policy.resolve(definition, resource, owner_id=task.id)
        )

    async def _release_lock(self, handle: LockHandle | None) -> None:
        """释放资源锁（`docs/02` §41 / §65）；失败只吞掉**自己的**异常。"""
        if handle is None or self._locks is None:
            return
        try:
            await self._locks.release(handle)
        except Exception:  # noqa: BLE001 —— 释放失败不得掩盖原异常（见模块裁决 3）
            return

    async def _release_lease(self, task_id: str, worker_id: str) -> None:
        """释放租约（`docs/02` §40）；失败只吞掉**自己的**异常。"""
        try:
            await self._lease.release(task_id, worker_id)
        except Exception:  # noqa: BLE001 —— 同上
            return

    async def _execute(self, task: TaskRecord) -> Mapping[str, Any]:
        """调用执行契约（`docs/02` §48）。

        Raises:
            InternalError: `STRUCTAI-7000` —— 未装配执行器（见模块裁决 2）。
        """
        if self._executor is None:
            raise InternalError(
                "Task executor is not configured",
                details={"stage": WORKER_STAGE, "reason": "executor_not_configured"},
            )
        return await self._executor.execute(task)

    def _encode_result(self, result: Mapping[str, Any]) -> str:
        """规范化结果 → `result_json`（`docs/02` §53 / §54 的 `Task Result Persist`）。

        Raises:
            InternalError: `STRUCTAI-7000` —— 结果不可 JSON 序列化（见模块裁决 7）。
        """
        try:
            return json.dumps(dict(result), ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as error:
            raise InternalError(
                "Task result is not JSON serializable",
                details={"stage": WORKER_STAGE, "reason": "result_not_serializable"},
                cause=error,
            ) from error

    async def _report_progress(self, task_id: str, value: int, tenant_id: str) -> None:
        """上报进度（`docs/02` §31 / §32）；未装配时不报。

        ⚠️ **必须带租户**（`docs/02` §11 的租户隔离；见模块裁决 13）：Worker 已知
        `task_id → tenant_id`（`register` 的映射），故把租户一并透传给
        `ProgressReporter.report(..., tenant_id=...)` —— 否则进度写入只按 `id` 过滤，
        跨租户的 `task_id` 也能改到别的租户的行。
        """
        if self._progress is not None:
            await self._progress.report(task_id, value, tenant_id=tenant_id)

    async def _heartbeat_loop(self, task_id: str, worker_id: str) -> None:
        """周期续租（`docs/02` §39）；续租失败即**停止循环**（见模块裁决 4）。"""
        while True:
            await asyncio.sleep(self._lease.heartbeat_seconds)
            try:
                await self._lease.heartbeat(task_id, worker_id)
            except StructAIError:
                return

    async def _enqueue(self, task: TaskRecord) -> None:
        """把任务放回队列（`docs/02` §17 的排序键：原始 `created_at`）。"""
        await self._queue.put(task.id, task.priority, created_at=task.created_at)

    async def _current(
        self,
        task_id: str,
        tenant_id: str,
        fallback: TaskRecord,
    ) -> TaskRecord:
        """回读最新记录；读不到时回退为 `fallback`（**不**静默返回 `None`）。"""
        latest = await self._store.get(task_id, tenant_id)
        return fallback if latest is None else latest

    @staticmethod
    def _now() -> datetime:
        """当前时间（带时区的 UTC；`docs/02` §20 的 `task.started_at = now()`）。"""
        return datetime.now(UTC)

    # ===== 内部：结果落库（`docs/02` §53 / §54；§77 / §78） =====

    async def _mark_completed(self, task: TaskRecord, payload: str) -> TaskRecord:
        """`RUNNING → PROCESSING → COMPLETED` 并写入规范化结果（`docs/02` §53 / §54）。

        注意任一步 CAS 失败都**不**覆盖：保持真实状态并返回（例如状态已被
        `CancellationService` 改成 `CANCEL_REQUESTED`；`docs/07` §14.4）。
        """
        processing = await self._store.transition(
            task.id,
            expected=str(TaskStatus.RUNNING),
            new=str(TaskStatus.PROCESSING),
        )
        if not processing:
            return await self._current(task.id, task.tenant_id, task)
        completed = await self._store.transition(
            task.id,
            expected=str(TaskStatus.PROCESSING),
            new=str(TaskStatus.COMPLETED),
            fields={"result_json": payload, "completed_at": self._now()},
        )
        if not completed:
            return await self._current(task.id, task.tenant_id, task)
        return await self._current(task.id, task.tenant_id, task)

    async def _mark_timeout(self, task: TaskRecord) -> TaskRecord:
        """超时路径：`RUNNING → TIMEOUT` → 按预算 `RETRYING` 或 `FAILED`（`docs/02` §78 / §77）。

        `error_json` 落 `TaskTimeoutError`（`STRUCTAI-5100`）的 `to_dict()` JSON；
        预算耗尽时只改状态，**保留**该信封（`docs/07` §11）。
        """
        error = TaskTimeoutError(
            "Task execution timed out",
            details={"stage": WORKER_STAGE, "reason": "timeout"},
        )
        moved = await self._store.transition(
            task.id,
            expected=str(TaskStatus.RUNNING),
            new=str(TaskStatus.TIMEOUT),
            fields={"error_json": self._encode_error(error)},
        )
        if not moved:
            return await self._current(task.id, task.tenant_id, task)
        latest = await self._current(task.id, task.tenant_id, task)
        if self._attempts_left(latest):
            return await self._retry_chain(latest)
        failed = await self._store.transition(
            task.id,
            expected=str(TaskStatus.TIMEOUT),
            new=str(TaskStatus.FAILED),
        )
        if not failed:
            return await self._current(task.id, task.tenant_id, task)
        return await self._current(task.id, task.tenant_id, task)

    async def _mark_failed(self, task: TaskRecord, error: Exception) -> TaskRecord:
        """失败路径：`→ FAILED` 并落归一化错误；`retryable` 且仍有预算则走重试链。

        `StructAIError` 用其 `to_dict()` JSON；其它异常归一化为
        `InternalError`（`STRUCTAI-7000`；`docs/07` §11 的兜底码），
        **不**把原生 message 写进库（`docs/07` §14.3）。
        """
        envelope = self._envelope(error)
        moved = await self._store.transition(
            task.id,
            expected=str(task.status),
            new=str(TaskStatus.FAILED),
            fields={"error_json": self._encode_error(envelope)},
        )
        if not moved:
            return await self._current(task.id, task.tenant_id, task)
        latest = await self._current(task.id, task.tenant_id, task)
        if envelope.retryable and self._attempts_left(latest):
            return await self._retry_chain(latest)
        return latest

    async def _retry_chain(self, task: TaskRecord) -> TaskRecord:
        """`→ RETRYING`（`retry_count + 1`）→ `QUEUED` → 重新入队（`docs/02` §77 / §78）。

        注意预算判定在调用方（`_attempts_left`）；本方法只执行转移链。
        """
        retrying = await self._store.transition(
            task.id,
            expected=str(task.status),
            new=str(TaskStatus.RETRYING),
            fields={"retry_count": task.retry_count + 1},
        )
        if not retrying:
            return await self._current(task.id, task.tenant_id, task)
        queued = await self._store.transition(
            task.id,
            expected=str(TaskStatus.RETRYING),
            new=str(TaskStatus.QUEUED),
        )
        if not queued:
            return await self._current(task.id, task.tenant_id, task)
        latest = await self._current(task.id, task.tenant_id, task)
        await self._enqueue(latest)
        return latest

    @staticmethod
    def _attempts_left(task: TaskRecord) -> bool:
        """是否仍有重试预算（`docs/02` §77 / §78 的 `retry_count < max_retries`）。

        预算取自 `tasks.max_retries` 列（Worker 没有 `max_retries` 参数）；
        `max_retries = 0` 表示**不**重试（**不**表示无限）。
        """
        return task.retry_count < task.max_retries

    @staticmethod
    def _envelope(error: Exception) -> StructAIError:
        """把任意异常归一化为 20 码信封（`docs/07` §11；见模块裁决 2）。"""
        if isinstance(error, StructAIError):
            return error
        return InternalError(
            "Task execution failed",
            details={"stage": WORKER_STAGE, "reason": "unexpected_error"},
            cause=error,
        )

    @staticmethod
    def _encode_error(error: StructAIError) -> str:
        """错误信封 → `error_json`（只含 20 码字段；`docs/07` §14.3）。"""
        return json.dumps(error.to_dict(), ensure_ascii=False, sort_keys=True)
