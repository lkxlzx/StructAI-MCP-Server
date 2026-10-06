"""Application · Task · Engine（`docs/07` §10.1 / §10.2 / §12 P22–P28）。
覆盖 `docs/02` §9 / §15 / §19 / §47 / §48 / §54 / §77 / §78 / §88 / §90 的任务编排语义。

权威来源
--------
- `docs/02` §48（`task`）—— `TaskEngine` 的五个方法：`submit` / `get` / `cancel` /
  `retry` / `recover`（本模块逐项实现，并补 `create` / `run_task` / `update_progress`）。
- `docs/02` §15（`task`）—— `task_engine.run_task(task_id, worker_id)` 的调用形状；
  §88 —— 同步执行的 `worker_id = "sync-worker"`（本模块常量逐字照抄）。
- `docs/02` §9（`task`）—— 任务创建字段（`request_id` / `trace_id` / `tool` /
  `operation` / `project_id` / `priority`）。
- `docs/02` §47（`task`）—— 提交链 `CREATED → VALIDATING → QUEUED`
  （`docs/07` §10.1 的冻结 12 态）。
- `docs/02` §19 / §54（`task`）—— 「依赖满足后才能执行」「循环依赖必须在**提交前**拒绝」。
- `docs/02` §77 / §78（`task`）—— Retry / Timeout 的预算语义（`max_retries = 2` →
  共 3 次尝试）。
- `docs/02` §90（`task`）—— **顺序冻结**：`ExecutionService ↓ Idempotency ↓ Task Create`；
  「不能 `Task Create ↓ Idempotency`，否则重复请求可能先创建多个 Task」。
- `docs/07` §10.1 / §10.2 —— 状态机集中实现；恢复不得置 `COMPLETED`；取消不得杀进程。
- `docs/07` §11 —— `STRUCTAI-5000`（任务不存在 / 重试预算耗尽）、`STRUCTAI-1300`
  （非法转移，经 `TaskStateError`）、`STRUCTAI-7000`（未装配端口）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **本模块是**唯一**的 Task 创建点，且**不得** import
   `app.application.execution.idempotency`**（`docs/02` §90；本批裁决，见 `docs/07` §16 R43）：
   幂等是 Task 创建的**上游** —— 流水线顺序是
   `ExecutionService → Idempotency → Task Create`。若先建 Task 再判幂等，一次重复请求会
   创建**多个** Task。故本模块把该顺序固化为 `TASK_CREATE_ORDER` 常量（供验收逐条断言），
   并在源码层面**不**引用幂等模块 —— 上游关系不是靠注释，而是靠**依赖方向**保证。
2. **DAG 校验先于落库**：`create()` 在 `store.create` **之前**完成
   `graph_from_drafts` + `validate_dag`（`docs/02` §19 / §54）。环 / 缺依赖 / 未知 Operation
   在此时抛 `STRUCTAI-1200`，库里**一行都没有** —— 「提交前拒绝」因此是**结构性**的，
   而不是靠事后补偿删除。
3. **每步 CAS 都经状态机校验**：`_advance` 先用
   `state_machine.transition(expected, new)` 判合法性（非法 → `TaskStateError`），
   再做条件更新（影响 0 行 → 同样 `TaskStateError`）。**不**另写第二份转移判定
   （`docs/07` §10.1）。
4. **`retry` 的重试预算**只有**一个来源 —— 任务行**（`docs/02` §77 / §78）：
   `TaskEngine.retry` 与 `TaskWorker` 的重试链必须对「一个任务能重试几次」给出**同一**
   答案，而 Worker 只读 `tasks.max_retries` 列（它没有引擎级参数）。故 `_retry_budget`
   **直接**返回 `task.max_retries`；`self._max_retries` **只**用于**创建**（`create` 的
   `TaskDraft.max_retries = submission.max_retries if submission.max_retries > 0 else
   self._max_retries`）。若在预算判定里回落引擎级值，「`max_retries = 0` 的行 ＋
   引擎级 `2`」就会出现引擎允许重试、Worker 拒绝重试的两套口径。
   `max_retries = 0` 表示**不**重试（**不**无限）。
5. **`retry` 重新入队用**原始** `created_at`**：`docs/02` §17 要求队列按
   `priority` + `created_at` 排序；重试的任务是「旧任务」，若用当前时间入队会被排到
   新任务之后（`queue.py` 模块裁决 1 的同一理由）。
6. **`submit` 的 `TaskView` 不带 `steps`**：`docs/02` §48 的 `submit` 只返回任务；
   步骤列表由 `get` 提供（多一次 `list_steps` 查询）。本模块照此实现，避免在提交路径上
   多做一次读。
7. **未装配端口一律 `STRUCTAI-7000`**：`cancel` / `run_task` / `update_progress` 在
   缺少对应端口时抛 `InternalError`（`details.reason = "<port>_not_configured"`）——
   装配错误必须显式暴露，**不**静默变成空操作（`docs/07` §14.4）。`recover` 例外：
   返回空元组（Core Alpha 允许不装配启动恢复）。
8. **`_enqueue` 入队后**同时**登记租户**（`docs/02` §11 / §12 / §48）：队列项只携带
   `task_id`，而 `TaskStore` 的读取是**租户作用域**的，故 `TaskEngine.retry` 的重新入队
   路径也必须 `self._worker.register(task)`（`submit` 一直如此）。否则 Worker 取到该任务
   会抛 `unknown_task`（`STRUCTAI-5000`），任务永远执行不了 —— 正好触发 Worker 循环的
   逐项异常隔离（`worker.py` 模块裁决 11）。
9. **`update_progress` 透传 `tenant_id`**（`docs/02` §11 的租户隔离；`progress.py`
   模块裁决 6）：`TaskEngine.update_progress(..., *, tenant_id=None)` 是**新增的关键字**，
   转发给 `ProgressReporter.report` —— 否则进度写入只按 `id` 过滤，跨租户的 `task_id`
   能改到别的租户的行。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain` / **同层**的 `app.application.task.*`：
**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖 `app.infrastructure`
（持久化经 Domain 契约 `TaskStore` 注入），也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from app.application.task.cancellation import CancellationOutcome, CancellationService
from app.application.task.dag import graph_from_drafts, validate_dag
from app.application.task.lease import LeaseService
from app.application.task.progress import ProgressReporter, ProgressUpdate
from app.application.task.queue import TaskQueue, priority_value
from app.application.task.recovery import RecoveryOutcome, RecoveryService
from app.application.task.scheduler import Scheduler
from app.application.task.state_machine import TaskStateError
from app.application.task.state_machine import transition as transition_status
from app.application.task.worker import TaskWorker
from app.domain.enums import TaskPriority, TaskStatus
from app.domain.errors import InternalError, TaskError
from app.domain.protocols import (
    OperationRegistry,
    TaskDraft,
    TaskRecord,
    TaskStepDraft,
    TaskStepRecord,
    TaskStore,
)

__all__ = [
    "DEFAULT_MAX_RETRIES",
    "SYNC_WORKER_ID",
    "TASK_CREATE_ORDER",
    "TASK_ENGINE_STAGE",
    "RETRYABLE_STATUSES",
    "TaskEngine",
    "TaskSubmission",
    "TaskView",
]

TASK_ENGINE_STAGE: Final[str] = "task"
"""错误 `details.stage` 的固定取值（与 `state_machine` / `lease` 同口径）。"""

DEFAULT_MAX_RETRIES: Final[int] = 0
"""默认重试预算（`docs/02` §11 的 `max_retries: int = 0`）。

⚠️ `0` 表示**不**重试（**不**表示无限）—— 与 `tasks.max_retries` 的列默认值一致。
"""

SYNC_WORKER_ID: Final[str] = "sync-worker"
"""同步执行的 Worker 标识（`docs/02` §88 原文 `worker_id="sync-worker"`，逐字照抄）。"""

TASK_CREATE_ORDER: Final[tuple[str, ...]] = (
    "ExecutionService",
    "Idempotency",
    "Task Create",
)
"""`docs/02` §90 的顺序副本（**仅供断言**，不参与执行；见模块裁决 1）。

⚠️ 反序（`Task Create → Idempotency`）是**禁止**的：重复请求会先创建多个 Task。
"""


RETRYABLE_STATUSES: Final[frozenset[TaskStatus]] = frozenset(
    {TaskStatus.FAILED, TaskStatus.TIMEOUT}
)
"""`retry()` 允许的入口状态（`docs/02` §77 / §78）。

注意 `FAILED` / `TIMEOUT` **不是**终态：它们都有 `RETRYING` 出边
（`state_machine.TERMINAL_STATUSES` 只含 `COMPLETED` / `CANCELLED`）。
"""


@dataclass(frozen=True, slots=True)
class TaskSubmission:
    """一次任务提交（`docs/02` §9 的字段 ＋ §47 的 DAG 步骤）。

    Attributes:
        tenant_id: 租户标识（`docs/02` §11：Task 是 Tenant-owned）。
        request_id: 服务端请求标识（`docs/02` §5）。
        trace_id: 服务端链路标识（`docs/02` §5）。
        tool: Tool 名（`docs/02` §9）。
        operation: 规范化 Operation 名（`docs/02` §24）。
        project_id: 可选项目标识。
        software_instance_id: 可选软件实例标识（`docs/02` §19 的实例归属）。
        user_id: 用户标识（四级并发判定用；`docs/02` §18）。
        priority: 优先级（`TaskPriority` / 整数 / 枚举字符串；`docs/02` §14）。
        max_retries: 该任务声明的重试预算（`docs/02` §77 / §78）。
        steps: DAG 步骤草稿（`docs/02` §47）；为空表示单步任务。
    """

    tenant_id: str
    request_id: str
    trace_id: str
    tool: str
    operation: str
    project_id: str | None = None
    software_instance_id: str | None = None
    user_id: str = ""
    priority: TaskPriority | int | str = TaskPriority.NORMAL
    max_retries: int = DEFAULT_MAX_RETRIES
    steps: tuple[TaskStepDraft, ...] = ()


@dataclass(frozen=True, slots=True)
class TaskView:
    """一个任务及其步骤的只读视图（`docs/02` §48 的 `get` 返回）。

    `task_id` / `status` / `progress` 三个属性直接转发 `task` 的同名取值，
    便于调用方少写一层 `view.task.xxx`。
    """

    task: TaskRecord
    steps: tuple[TaskStepRecord, ...] = ()

    @property
    def task_id(self) -> str:
        """任务标识（转发 `task.id`）。"""
        return self.task.id

    @property
    def status(self) -> TaskStatus:
        """**真实**状态（转发 `task.status`；`docs/07` §10.1 的 12 态）。

        Raises:
            ValueError: 取值不在 12 态内（数据错误，**不**静默当作某个状态）。
        """
        return TaskStatus(str(self.task.status))

    @property
    def progress(self) -> int:
        """进度（转发 `task.progress`；`docs/02` §31 的 `0`–`100`）。"""
        return self.task.progress


class TaskEngine:
    """任务编排入口（`docs/02` §48 / §15 / §90；`docs/07` §10.1 / §10.2）。

    ⚠️ 持久化经 Domain 契约 `TaskStore` 注入：本模块**不**依赖 `app.infrastructure`
    （`docs/07` §14.1）。事务边界归调用方的 `UnitOfWork`（`docs/02` §16）——
    本类**从不** `commit` / `rollback`。

    🔴 本类是**唯一**的 Task 创建点（`docs/02` §90），且**不**依赖幂等模块
    （见模块裁决 1）。
    """

    def __init__(
        self,
        store: TaskStore,
        *,
        queue: TaskQueue | None = None,
        lease: LeaseService | None = None,
        scheduler: Scheduler | None = None,
        recovery: RecoveryService | None = None,
        cancellation: CancellationService | None = None,
        progress: ProgressReporter | None = None,
        worker: TaskWorker | None = None,
        operations: OperationRegistry | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        """绑定任务存储与各可选端口（**全部**由调用方注入）。

        Args:
            store: `docs/02` §34 的持久化入口（必需）。
            queue: 任务队列（`docs/02` §11 / §49）；缺省 `None` 表示不入队。
            lease: 租约服务（`docs/02` §34–§38）；本类只转发，不直接使用。
            scheduler: 四级并发准入（`docs/02` §18）；同上。
            recovery: 启动恢复（`docs/02` §42）；缺省时 `recover()` 返回空元组。
            cancellation: 取消服务（`docs/02` §43）；缺省时 `cancel()` 抛
                `STRUCTAI-7000`。
            progress: 进度上报（`docs/02` §31–§33）；缺省时 `update_progress()` 抛
                `STRUCTAI-7000`。
            worker: 任务 Worker（`docs/02` §40）；缺省时 `run_task()` 抛 `STRUCTAI-7000`。
            operations: 运行时 Operation Registry（`docs/02` §28）；用于
                `create()` 的 DAG `unknown_step` 校验。
            max_retries: 引擎级重试预算缺省值（见模块裁决 4）。
        """
        self._store = store
        self._queue = queue
        self._lease = lease
        self._scheduler = scheduler
        self._recovery = recovery
        self._cancellation = cancellation
        self._progress = progress
        self._worker = worker
        self._operations = operations
        self._max_retries = max_retries

    # ===== 只读视图 =====

    @property
    def store(self) -> TaskStore:
        """被绑定的任务存储（只读用途）。"""
        return self._store

    @property
    def queue(self) -> TaskQueue | None:
        """被绑定的任务队列（只读用途；缺省 `None`）。"""
        return self._queue

    # ===== `docs/02` §47 / §90：创建与提交 =====

    async def create(self, submission: TaskSubmission) -> TaskRecord:
        """创建并推进到 `QUEUED`（`docs/02` §47 的 `CREATED → VALIDATING → QUEUED`）。

        ⚠️ 有 `steps` 时**先**做 DAG 校验（`docs/02` §19 / §54）：环 / 缺依赖 /
        未知 Operation 在**落库之前**抛 `STRUCTAI-1200`，库里一行都没有
        （见模块裁决 2）。

        Args:
            submission: 任务提交。

        Returns:
            最新的 `TaskRecord`（状态 `QUEUED`）。

        Raises:
            EngineeringValidationError: `STRUCTAI-1200` —— DAG 缺陷
                （`details.reason ∈ {duplicate_step, missing_dependency, cycle, unknown_step}`）。
            TaskStateError: `STRUCTAI-1300` —— 提交链上的 CAS 失败。
            InternalError: `STRUCTAI-7000` —— CAS 成功但回读不到该行。
            ValueError: 优先级取值非法（`priority_value`）。
        """
        if submission.steps:
            graph = graph_from_drafts(submission.steps)
            validate_dag(graph, known_operations=await self._known_operations())

        draft = TaskDraft(
            tenant_id=submission.tenant_id,
            request_id=submission.request_id,
            trace_id=submission.trace_id,
            tool=submission.tool,
            operation=submission.operation,
            project_id=submission.project_id,
            # 见 `queue.py`：优先级落库口径 = `docs/02` §14 的整数映射（§14 的 `LOW` = 100）。
            priority=priority_value(submission.priority),
            # 见模块裁决 4：**创建**是引擎级 `max_retries` 的**唯一**用途 —— 提交未声明
            # （`0`）时落引擎级缺省值；落库之后**任务行就是唯一真源**（`_retry_budget`）。
            max_retries=(
                submission.max_retries if submission.max_retries > 0 else self._max_retries
            ),
            status=str(TaskStatus.CREATED),
        )
        created = await self._store.create(draft, submission.steps)
        await self._advance(created, TaskStatus.CREATED, TaskStatus.VALIDATING)
        return await self._advance(created, TaskStatus.VALIDATING, TaskStatus.QUEUED)

    async def submit(self, submission: TaskSubmission) -> TaskView:
        """`create` + 入队 + 登记（`docs/02` §48 的 `submit`；§13 的 `queue.put`）。

        Args:
            submission: 任务提交。

        Returns:
            `TaskView`（**不含** `steps` —— 见模块裁决 6）。

        Raises:
            EngineeringValidationError: `STRUCTAI-1200`（DAG 缺陷，同 `create`）。
            TaskStateError: `STRUCTAI-1300`（提交链 CAS 失败）。
            TaskError: `STRUCTAI-5000` —— 队列已满（`docs/02` §56；`retryable = true`）。
            RuntimeError: 队列已 `shutdown()`（不再接受新任务）。
        """
        task = await self.create(submission)
        if self._queue is not None:
            # `created_at` 必须用任务自己的创建时刻（`docs/02` §17 的排序键）。
            await self._queue.put(task.id, task.priority, created_at=task.created_at)
        if self._worker is not None:
            self._worker.register(task)
        return TaskView(task=task)

    async def get(self, task_id: str, tenant_id: str) -> TaskView:
        """读取任务及其步骤（`docs/02` §48 的 `get`；§11 的租户作用域读）。

        Args:
            task_id: 任务标识。
            tenant_id: 租户标识（`docs/02` §11：读取必须同时限制租户）。

        Returns:
            `TaskView`（含 `steps`）。

        Raises:
            TaskError: `STRUCTAI-5000` —— 任务不存在（或不属于该租户）。
                `details.reason = "unknown_task"`。
        """
        task = await self._store.get(task_id, tenant_id)
        if task is None:
            raise self._unknown_task()
        steps = tuple(await self._store.list_steps(task_id))
        return TaskView(task=task, steps=steps)

    # ===== 内部：CAS 推进 =====

    async def _advance(
        self,
        task: TaskRecord,
        expected: TaskStatus,
        new: TaskStatus,
        *,
        fields: Mapping[str, object] | None = None,
    ) -> TaskRecord:
        """校验并执行一次状态推进，随后回读（见模块裁决 3）。

        Raises:
            TaskStateError: `STRUCTAI-1300` —— 转移非法（状态机拒绝）或 CAS 失败
                （状态已被别人改过）。
            InternalError: `STRUCTAI-7000` —— CAS 成功但回读不到该行。
        """
        target = transition_status(expected, new)
        moved = await self._store.transition(
            task.id,
            expected=str(expected),
            new=str(target),
            fields=fields,
        )
        if not moved:
            raise TaskStateError(
                f"Invalid transition: {expected} -> {target}",
                details={
                    "stage": TASK_ENGINE_STAGE,
                    "from": str(expected),
                    "to": str(target),
                },
            )
        latest = await self._store.get(task.id, task.tenant_id)
        if latest is None:
            raise InternalError(
                "task disappeared right after a successful transition",
                details={"stage": TASK_ENGINE_STAGE, "reason": "read_back_missing"},
            )
        return latest

    async def _known_operations(self) -> tuple[str, ...] | None:
        """已登记的 Operation 名（供 DAG 的 `unknown_step` 校验）。

        Returns:
            `None` 表示**不**检查 Operation 合法性（未装配 Registry 时）；
            否则为已登记名元组。

        说明：Domain 契约 `app.domain.protocols.OperationRegistry` 只有
        `register` / `get` / `list` 三个方法（`docs/02` §13），**没有** `names()`
        ——`names()` 是 Infrastructure 实现（`docs/07` §12 P08）的便捷入口。
        本模块只依赖 Domain 契约，故用 `list()` 取名字（行为等价，见模块裁决 2）。
        """
        if self._operations is None:
            return None
        return tuple(definition.name for definition in await self._operations.list())

    def _unknown_task(self) -> TaskError:
        """构造「任务不存在」的错误（`STRUCTAI-5000`；`docs/07` §11）。"""
        return TaskError(
            "Task not found",
            details={"stage": TASK_ENGINE_STAGE, "reason": "unknown_task"},
        )

    # ===== `docs/02` §48：取消 / 重试 / 恢复 / 同步执行 / 进度 =====

    async def cancel(
        self,
        task_id: str,
        tenant_id: str,
        *,
        software_instance_id: str | None = None,
    ) -> CancellationOutcome:
        """取消任务（`docs/02` §43；`docs/07` §10.2 的 `TaskEngine.cancel()`）。

        Args:
            task_id: 任务标识。
            tenant_id: 租户标识。
            software_instance_id: 目标软件实例（`docs/02` §53）。

        Returns:
            `CancellationOutcome`（**真实**状态；`docs/02` §30：不得伪造 `CANCELLED`）。

        Raises:
            InternalError: `STRUCTAI-7000` —— 未装配 `CancellationService`
                （`details.reason = "cancellation_not_configured"`；见模块裁决 7）。
            TaskError: `STRUCTAI-5000` —— 任务不存在。
            TaskStateError: `STRUCTAI-1300` —— 该状态不可取消。
        """
        if self._cancellation is None:
            raise InternalError(
                "Task cancellation is not configured",
                details={
                    "stage": TASK_ENGINE_STAGE,
                    "reason": "cancellation_not_configured",
                },
            )
        return await self._cancellation.cancel(
            task_id,
            tenant_id,
            software_instance_id=software_instance_id,
        )

    async def retry(self, task_id: str, tenant_id: str) -> TaskRecord:
        """重试失败 / 超时的任务（`docs/02` §77 / §78 的 Retry 链）。

        Args:
            task_id: 任务标识。
            tenant_id: 租户标识。

        Returns:
            最新的 `TaskRecord`（状态 `QUEUED`，`retry_count` 已 +1）。

        Raises:
            TaskError: `STRUCTAI-5000` —— 任务不存在（`reason = "unknown_task"`），
                或重试预算已耗尽（`reason = "retry_exhausted"`；**不**无限重试）。
            TaskStateError: `STRUCTAI-1300` —— 当前状态不是 `FAILED` / `TIMEOUT`，
                或 CAS 失败。
            InternalError: `STRUCTAI-7000` —— CAS 成功但回读不到该行。
        """
        task = await self._store.get(task_id, tenant_id)
        if task is None:
            raise self._unknown_task()

        current = TaskStatus(str(task.status))
        if current not in RETRYABLE_STATUSES:
            raise TaskStateError(
                f"Invalid transition: {current} -> {TaskStatus.RETRYING}",
                details={
                    "stage": TASK_ENGINE_STAGE,
                    "from": str(current),
                    "to": str(TaskStatus.RETRYING),
                },
            )
        if task.retry_count >= self._retry_budget(task):
            raise TaskError(
                "Task retry budget exhausted",
                details={"stage": TASK_ENGINE_STAGE, "reason": "retry_exhausted"},
            )

        retrying = await self._advance(
            task,
            current,
            TaskStatus.RETRYING,
            fields={"retry_count": task.retry_count + 1},
        )
        queued = await self._advance(retrying, TaskStatus.RETRYING, TaskStatus.QUEUED)
        # 见模块裁决 5：用**原始** `created_at` 重新入队（§17 的排序键）。
        await self._enqueue(queued)
        return queued

    async def recover(self) -> tuple[RecoveryOutcome, ...]:
        """扫描并恢复未完成任务（`docs/02` §42 的 `recovery.recover_unfinished_tasks()`）。

        Returns:
            每条未完成任务一条 `RecoveryOutcome`；未装配 `RecoveryService` 时返回**空元组**
            （Core Alpha 允许不装配启动恢复；见模块裁决 7）。
        """
        if self._recovery is None:
            return ()
        return await self._recovery.recover_unfinished_tasks()

    async def run_task(
        self,
        task_id: str,
        worker_id: str = SYNC_WORKER_ID,
    ) -> TaskRecord:
        """同步执行一个任务（`docs/02` §15 / §88 的 `task_engine.run_task(...)`）。

        Args:
            task_id: 任务标识。
            worker_id: Worker 标识；缺省 `SYNC_WORKER_ID`（`docs/02` §88）。

        Returns:
            执行后的 `TaskRecord`（**真实**状态）。

        Raises:
            InternalError: `STRUCTAI-7000` —— 未装配 `TaskWorker`
                （`details.reason = "worker_not_configured"`；见模块裁决 7）。
            TaskError: `STRUCTAI-5000` —— Worker 侧未登记该任务（`reason = "unknown_task"`）。
        """
        if self._worker is None:
            raise InternalError(
                "Task worker is not configured",
                details={"stage": TASK_ENGINE_STAGE, "reason": "worker_not_configured"},
            )
        return await self._worker.run_task(task_id, worker_id)

    async def update_progress(
        self,
        task_id: str,
        progress: object,
        message: str | None = None,
        *,
        tenant_id: str | None = None,
    ) -> ProgressUpdate:
        """上报进度（`docs/02` §31–§33；`docs/07` §10.2 的**唯一**写入口）。

        Args:
            task_id: 任务标识。
            progress: 进度取值（**不可信**，先经 `sanitize_progress`）。
            message: 可选说明（只进事件，**不**落库）。
            tenant_id: 可选租户限制（`docs/02` §11；见模块裁决 8）；透传给
                `ProgressReporter.report`（**新增的关键字**，位置参数不变）。

        Returns:
            `ProgressUpdate`（含实际落库的规整值）。

        Raises:
            InternalError: `STRUCTAI-7000` —— 未装配 `ProgressReporter`
                （`details.reason = "progress_not_configured"`；见模块裁决 7）。
            EngineeringValidationError: `STRUCTAI-1200` —— 进度不可信。
            TaskError: `STRUCTAI-5000` —— 任务不存在（或不属于该租户）。
        """
        if self._progress is None:
            raise InternalError(
                "Task progress reporter is not configured",
                details={"stage": TASK_ENGINE_STAGE, "reason": "progress_not_configured"},
            )
        return await self._progress.report(task_id, progress, message, tenant_id=tenant_id)

    # ===== 内部：重试预算与入队 =====

    def _retry_budget(self, task: TaskRecord) -> int:
        """该任务的重试预算（见模块裁决 4）。

        Returns:
            `task.max_retries`（`docs/02` §77 / §78 的 `tasks.max_retries` 列）——
            **任务行是唯一真源**。`self._max_retries` **只**用于**创建**（`create` 把
            `TaskDraft.max_retries` 写成 `submission.max_retries if > 0 else
            self._max_retries`），**不**在此处回落：否则「`max_retries = 0` 的行 ＋
            引擎级 `2`」会让引擎允许重试、而 `TaskWorker._attempts_left`（只看任务行）
            拒绝重试 —— 两处口径不一致。
        """
        return task.max_retries

    async def _enqueue(self, task: TaskRecord) -> None:
        """把任务放回队列（`docs/02` §13 / §17 / §42）；未装配队列时**不**报错。

        ⚠️ 入队后**同时**登记租户（见模块裁决 8）：队列项只携带 `task_id`
        （`docs/02` §12 的 `QueueItem`），而 `TaskStore` 的读取是**租户作用域**的
        （`docs/02` §11）—— 不登记的话 Worker 取到该任务会抛 `unknown_task`
        （`STRUCTAI-5000`），任务永远执行不了。
        """
        if self._queue is not None:
            await self._queue.put(task.id, task.priority, created_at=task.created_at)
        if self._worker is not None:
            self._worker.register(task)
