"""Application · Task · Lease（`docs/07` §10.2 / §12 P22–P28）。

覆盖 `docs/02` §18 / §34–§38 / §40 / §80 的租约语义。

权威来源
--------
- `docs/02` §34（`task`）—— 租约三列 `lease_owner` / `lease_until` / `heartbeat_at`
  （`docs/07` §10.2 写作 `last_heartbeat`，落库列名是 `heartbeat_at`），
  示例 `worker-001` / `lease_until = now + 30s`。
- `docs/02` §35（`task`）—— `acquire_lease(task_id, worker_id, lease_seconds=30)` 的
  **原文实现**：`now = datetime.now(timezone.utc)`、`until = now + timedelta(seconds=...)`，
  `task is None` → `raise TaskLeaseError("Task lease unavailable")`（消息逐字照抄）。
- `docs/02` §36（`task`）—— **Lease 原子更新**：禁止 `SELECT ↓ UPDATE`（两个 Worker 会同时
  抢到同一任务）；必须单条 `UPDATE tasks SET lease_owner=?, lease_until=? WHERE id=?
  AND (lease_owner IS NULL OR lease_until < now)`，且**影响行数 = 1** 才代表获得租约。
- `docs/02` §37（`task`）—— `heartbeat < lease / 2`（示例 `10s heartbeat` / `30s lease`）。
- `docs/02` §38（`task`）—— `heartbeat(task_id, worker_id, lease_seconds=30)` 的原文实现
  （续租即刷新 `heartbeat_at` 与 `lease_until`）。
- `docs/02` §40（`task`）—— 恢复算法：`lease expired? ├── NO → leave running`；
  即「租约仍有效」是**等待 / 对账**的判据。
- `docs/02` §80（Lease Conflict Test）—— Worker A 已获租约时 Worker B 抢同一任务
  必须 `TaskLeaseError`，且 Worker B **不得执行**。
- `docs/02` §18（`task`）—— 重启链路 `unfinished tasks ↓ inspect lease ↓ RECOVERING`。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **`TaskLeaseError` 不新增 `STRUCTAI-xxxx` 码**（本批裁决，见 `docs/07` §16 R42）：
   租约抢占是**单条条件 `UPDATE`**，影响 0 行 = 乐观锁失败 —— `docs/07` §11 的
   `STRUCTAI-1300 Concurrency Conflict` 的触发场景逐字包含「乐观锁失败」。故本类实现为既有
   `app.domain.errors.ConcurrencyConflictError`（**`STRUCTAI-1300`**）的子类：
   租约抢占失败与状态 CAS 失败因此**同码同族**，客户端只有一种「状态冲突」语义。
   `details` 只放 `stage` / `reason`（`docs/07` §14.3：绝不记录 secret）。
2. **`heartbeat` 成功路径要回读**：`docs/02` §38 的原文只调用仓储、不返回任务；而本模块的
   对外契约要求返回续租后的 `TaskRecord`（调用方据此观察 `lease_until` / `heartbeat_at`）。
   故成功时用 `store.get(task_id, tenant_id)` 回读。`TaskStore.get` 是**租户作用域**读
   （`docs/02` §11 的 `tenant_id` + `resource_id`），而租户不在 `heartbeat` 的参数里，
   因此增加一个**可选**关键字参数 `tenant_id`：给了就回读并校验回读结果，没给就**只**
   做条件更新（此时无租户上下文，**不**允许退化成「不过滤租户」的全局读 —— `docs/02` §11）。
   给了 `tenant_id` 却回读不到刚更新成功的行 = **数据损坏**，落 `STRUCTAI-7000`
   （`docs/07` §14.4：不允许「带病继续」），**不**静默返回半截对象。
3. **构造期校验 `heartbeat < lease / 2`**（`docs/02` §37）：违反即 `ValueError` ——
   这是**装配错误**（策略值配错），`docs/07` §14.4 的「不允许带病启动」要求在此直接拒绝，
   **不**静默把 heartbeat 调小或把 lease 调大（静默放宽会让租约语义不可预期）。
4. **时间一律为 UTC 感知时间**：`clock` 缺省 `lambda: datetime.now(UTC)`，
   使 `lease_until` 与库中时间（由实现补 `UTC`，见 `repositories/task.py` 的时间口径）
   是「感知 vs 感知」比较（`docs/02` §36 的 `lease_until < now`）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，
**不**依赖 `app.infrastructure`（持久化经 Domain 契约 `TaskStore` 注入），
也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Final

from app.domain.errors import ConcurrencyConflictError, InternalError
from app.domain.protocols import TaskRecord, TaskStore

__all__ = [
    "DEFAULT_HEARTBEAT_SECONDS",
    "DEFAULT_LEASE_SECONDS",
    "LEASE_STAGE",
    "TASK_LEASE_MESSAGE",
    "LeaseService",
    "TaskLeaseError",
    "heartbeat_is_within_lease",
]

DEFAULT_LEASE_SECONDS: Final[int] = 30
"""默认租约时长（秒）—— `docs/02` §35 原文 `lease_seconds: int = 30`；与
`RuntimeConfig.lease_seconds` 的默认值一致（`docs/02` §6）。"""

DEFAULT_HEARTBEAT_SECONDS: Final[int] = 10
"""默认心跳间隔（秒）—— `docs/02` §37 原文示例 `10s heartbeat`；与
`RuntimeConfig.heartbeat_seconds` 的默认值一致（`docs/02` §6）。"""

LEASE_STAGE: Final[str] = "lease"
"""错误 `details.stage` 的固定取值（与 `state_machine` / `progress` 同口径）。"""

TASK_LEASE_MESSAGE: Final[str] = "Task lease unavailable"
"""租约抢占失败的对外消息（`docs/02` §35 原文，逐字照抄）。"""

Clock = Callable[[], datetime]
"""取当前时间的可注入时钟（验收测试据此制造过期租约；`docs/02` §35 的 `now`）。"""


class TaskLeaseError(ConcurrencyConflictError):
    """租约不可用（`docs/02` §35 / §80）。

    ⚠️ **不新增 `STRUCTAI-xxxx` 码**（20 码契约不扩，`docs/07` §11）：本类实现为既有
    `ConcurrencyConflictError`（**`STRUCTAI-1300`**）的子类 —— 租约抢占是**单条条件
    `UPDATE`**，影响 0 行即「乐观锁失败」（`docs/07` §11 的触发场景逐字包含该情形），
    故与状态 CAS 失败同码同族。消息逐字照抄 `docs/02` §35。
    """


def heartbeat_is_within_lease(lease_seconds: int, heartbeat_seconds: int) -> bool:
    """心跳间隔是否满足 `docs/02` §37 的 `heartbeat < lease / 2`。

    Args:
        lease_seconds: 租约时长（秒）。
        heartbeat_seconds: 心跳间隔（秒）。

    Returns:
        仅当 `heartbeat_seconds * 2 < lease_seconds` 时为 `True`。

    ⚠️ 规范原文是严格小于（`heartbeat < lease / 2`）：`heartbeat == lease / 2` 时
    一次心跳丢失就会让租约到期，故**不**放宽为 `<=`。
    """
    return heartbeat_seconds * 2 < lease_seconds


class LeaseService:
    """任务租约的获取 / 续租 / 释放 / 过期判定（`docs/02` §34–§38 / §40 / §80）。

    ⚠️ 持久化经 Domain 契约 `TaskStore` 注入：本模块**不**依赖 `app.infrastructure`
    （`docs/07` §14.1）。事务边界归调用方的 `UnitOfWork`（`docs/02` §16）——
    本类**从不** `commit` / `rollback`。

    原子性由**存储实现**负责（`docs/02` §36 的单条条件 `UPDATE`）：本类只做
    「调用 + 影响行数判定 + 错误构造」，**不**做 `SELECT → UPDATE`。
    """

    def __init__(
        self,
        store: TaskStore,
        *,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        heartbeat_seconds: int = DEFAULT_HEARTBEAT_SECONDS,
        clock: Clock | None = None,
    ) -> None:
        """绑定租约存储与租约参数。

        Args:
            store: `docs/02` §34 的持久化入口（`acquire_lease` / `heartbeat` /
                `release_lease` / `get`）。
            lease_seconds: 租约时长（秒）；调用方传 `RuntimeConfig.lease_seconds`。
            heartbeat_seconds: 心跳间隔（秒）；调用方传 `RuntimeConfig.heartbeat_seconds`。
            clock: 可注入时钟；缺省为带时区的 UTC 当前时间（`docs/02` §35）。

        Raises:
            ValueError: 任一参数 `<= 0`，或不满足 `docs/02` §37 的
                `heartbeat < lease / 2`（装配错误，**不**静默放宽 —— 见模块裁决 3）。
        """
        if lease_seconds <= 0:
            raise ValueError(f"lease_seconds must be positive: {lease_seconds}")
        if heartbeat_seconds <= 0:
            raise ValueError(f"heartbeat_seconds must be positive: {heartbeat_seconds}")
        if not heartbeat_is_within_lease(lease_seconds, heartbeat_seconds):
            raise ValueError(
                "heartbeat must be less than half the lease "
                f"(docs/02 §37): heartbeat={heartbeat_seconds}s lease={lease_seconds}s"
            )
        self._store = store
        self._lease_seconds = lease_seconds
        self._heartbeat_seconds = heartbeat_seconds
        self._clock: Clock = clock or _utc_now

    # ===== 只读视图 =====

    @property
    def store(self) -> TaskStore:
        """被绑定的存储（只读用途）。"""
        return self._store

    @property
    def lease_seconds(self) -> int:
        """租约时长（秒）。"""
        return self._lease_seconds

    @property
    def heartbeat_seconds(self) -> int:
        """心跳间隔（秒）。"""
        return self._heartbeat_seconds

    def now(self) -> datetime:
        """当前时间（`docs/02` §35 的 `now`；缺省为带时区的 UTC）。"""
        return self._clock()

    # ===== `docs/02` §35 / §36：抢占 =====

    async def acquire(self, task_id: str, worker_id: str) -> TaskRecord:
        """抢占任务租约（`docs/02` §35 的 `acquire_lease`；§36 的原子更新）。

        Args:
            task_id: 任务标识。
            worker_id: Worker 标识（写入 `lease_owner`）。

        Returns:
            抢占成功后的任务快照（`lease_owner` / `lease_until` / `heartbeat_at` 已刷新）。

        Raises:
            TaskLeaseError: `STRUCTAI-1300` —— 存储返回 `None`（条件更新影响 0 行，
                说明租约被别人持有且未过期）。`details = {stage: "lease",
                reason: "unavailable"}`（`docs/02` §80 的 Worker B 路径）。
        """
        now = self.now()
        task = await self._store.acquire_lease(
            task_id,
            worker_id=worker_id,
            now=now,
            lease_until=now + timedelta(seconds=self._lease_seconds),
        )
        if task is None:
            raise TaskLeaseError(
                TASK_LEASE_MESSAGE,
                details={"stage": LEASE_STAGE, "reason": "unavailable"},
            )
        return task

    # ===== `docs/02` §38：续租 =====

    async def heartbeat(
        self,
        task_id: str,
        worker_id: str,
        *,
        tenant_id: str | None = None,
    ) -> TaskRecord | None:
        """续租（`docs/02` §38 的 `heartbeat`；§37 的心跳间隔）。

        Args:
            task_id: 任务标识。
            worker_id: 当前持有者标识。
            tenant_id: 可选租户上下文；给了就回读并返回续租后的 `TaskRecord`
                （`TaskStore.get` 是租户作用域读，见模块裁决 2）。

        Returns:
            给了 `tenant_id` 时返回续租后的任务快照；未给时返回 `None`
            （条件更新已生效，但**不**做无租户过滤的全局读 —— `docs/02` §11）。

        Raises:
            TaskLeaseError: `STRUCTAI-1300` —— 条件更新影响 0 行（调用方**不是**
                租约持有者）。`details.reason = "not_owner"`。
            InternalError: `STRUCTAI-7000` —— 给了 `tenant_id` 却回读不到该行
                （数据损坏，见模块裁决 2）。
        """
        now = self.now()
        updated = await self._store.heartbeat(
            task_id,
            worker_id=worker_id,
            heartbeat_at=now,
            lease_until=now + timedelta(seconds=self._lease_seconds),
        )
        if not updated:
            raise TaskLeaseError(
                TASK_LEASE_MESSAGE,
                details={"stage": LEASE_STAGE, "reason": "not_owner"},
            )
        if tenant_id is None:
            return None
        task = await self._store.get(task_id, tenant_id)
        if task is None:
            raise InternalError(
                "task disappeared right after a successful lease heartbeat",
                details={"stage": LEASE_STAGE, "reason": "read_back_missing"},
            )
        return task

    # ===== `docs/02` §40：释放与过期判定 =====

    async def release(self, task_id: str, worker_id: str) -> bool:
        """释放租约（`docs/02` §40 的 `release_lease`；`docs/07` §9 第 21 步同族）。

        Args:
            task_id: 任务标识。
            worker_id: 当前持有者标识。

        Returns:
            `True` 表示确实释放了租约；`False` 表示调用方**不是**持有者或租约已不存在
            （两种情况**不做区分**，且绝不释放别人手里的租约）。
        """
        return await self._store.release_lease(task_id, worker_id=worker_id)

    def is_expired(self, task: TaskRecord, now: datetime | None = None) -> bool:
        """租约是否已失效（`docs/02` §36 / §40）。

        Args:
            task: 任务快照。
            now: 判定基准时间；缺省取 `self.now()`。

        Returns:
            `True` 表示该任务的租约可被抢占 / 该任务可被恢复 ——
            「无租约」与「租约到期」**都**算失效（`docs/02` §40 的
            `lease_owner IS NULL OR lease_until < now`）。
        """
        return task.lease_is_expired(now or self.now())


def _utc_now() -> datetime:
    """默认时钟：带时区的 UTC 当前时间（`docs/02` §35 的 `datetime.now(timezone.utc)`）。"""
    return datetime.now(UTC)
