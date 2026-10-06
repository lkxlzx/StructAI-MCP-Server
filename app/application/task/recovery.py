"""Application · Task · Recovery（`docs/07` §10.2 / §12 P22–P28）。
覆盖 `docs/02` §18 / §40–§45 / §52 / §66 / §81 的启动恢复语义。

权威来源
--------
- `docs/02` §18（`task`）—— 重启链路：`unfinished tasks ↓ inspect lease ↓ RECOVERING ↓
  REQUEUE / RESUME / FAIL`；「不能把恢复中的 Task 直接标记为 `COMPLETED`」。
- `docs/02` §40（`task`）—— 崩溃后 `Task = RUNNING` / `Worker = gone` /
  `Lease = expired`；启动时由 `RecoveryManager` 扫描 `RUNNING` / `PROCESSING` / `QUEUED`。
- `docs/02` §41（`task`）—— 恢复算法**原文流程**：`find unfinished tasks ↓ check lease ↓
  lease expired? ├── NO → leave running │ └── YES ↓ RECOVERING ↓ determine policy ↓
  REQUEUE / RESUME / FAIL`。
- `docs/02` §42（`task`）—— 策略词表（示例 `REQUEUE` / `RESUME` / `FAIL` / `MANUAL`）与
  「第一阶段 `REQUEUE` 优先」。
- `docs/02` §43（`task`）—— `TaskRecoveryService.recover_expired_tasks()`：逐条
  `RECOVERING` → 按 `retry_count < max_retries` 决定是否重试。
- `docs/02` §44（`task`）—— 「Recovery 不能重复执行危险操作」。
- `docs/02` §45（`task`）—— **Recovery Policy 分类**：`SAFE_RETRY` / `STATE_RECONCILE` /
  `MANUAL_REVIEW` / `FAIL`，「最终由 `OperationDefinition` 指定」。
- `docs/02` §52 / §66（`task`）—— 启动恢复只查**未完成**任务：`QUEUED` / `RUNNING` /
  `PROCESSING` / `RECOVERING`（`docs/07` §10.2 的同一条）。
- `docs/02` §81（Recovery Test）—— `status = RUNNING` + `lease_until = expired` →
  `RECOVERING → RETRYING → QUEUED`，然后 Worker 重新 `RUNNING`。
- `docs/07` §10.2 —— 「查 `QUEUED/RUNNING/PROCESSING/RECOVERING` → 检查 lease → 有效则
  等待 / 对账，否则 `RECOVERING` → 重试 / 重排」；「恢复策略 `REQUEUE` / `FAIL` /
  `RESUME`（按 Operation 的 `recovery_policy`）」；「**不得把恢复中的 Task 直接标记
  `COMPLETED`**」。
- `docs/07` §11 —— `STRUCTAI-5300 Task Recovery Error`；`docs/07` §14.4 —— 不得把恢复中的
  任务标记 `COMPLETED`。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **两个词表之间的唯一转换点**（`docs/07` §16 R15 / R43）：`OperationDefinition.recovery_policy`
   的词表是 `docs/02` §45 的 `SAFE_RETRY` / `STATE_RECONCILE` / `MANUAL_REVIEW` / `FAIL`
   （R15 已裁决以 §45 为准），而 `REQUEUE` / `RESUME` / `FAIL` 是**恢复动作**词表
   （`docs/02` §18 / §42 / §52）。`POLICY_TO_ACTION` 是两套词表之间**唯一**的转换点：

   | `recovery_policy`（§45） | 恢复动作（§18 / §42） |
   | --- | --- |
   | `SAFE_RETRY` | `REQUEUE` |
   | `STATE_RECONCILE` | `RESUME` |
   | `MANUAL_REVIEW` | `FAIL` |
   | `FAIL` | `FAIL` |

   **未知策略一律 `FAIL`**（`POLICY_TO_ACTION.get(policy, RecoveryAction.FAIL)`）：
   臆测「未知即可重试」会在语义不明时重复执行**可能已产生副作用**的操作
   （`docs/02` §44 的禁止项），故未知一律走最保守的 `FAIL`。
2. **`REQUEUE` 直接 `RECOVERING → QUEUED`，不经过 `RETRYING`**（本批裁决，见
   `docs/07` §16 R43）：`docs/02` §81 的验收链写作 `RECOVERING → RETRYING → QUEUED`，
   但 `docs/02` §7 / §8 的**冻结转移表没有** `RECOVERING → RETRYING` 这条边
   （`RECOVERING` 的出边只有 `QUEUED` / `RUNNING` / `FAILED`）。本批**不**改冻结表
   （12 态与转移由 `state_machine.py` 集中实现，`docs/07` §10.1），故 `REQUEUE` 直接落
   `QUEUED` —— 语义等价：最终都被 Worker 重新取走执行；`retry_count` 的递增归
   `TaskWorker` / `TaskEngine.retry` 的重试链（`docs/02` §77 / §78）。
3. **「租约仍有效」= 等待 / 对账，零状态变更**：`docs/02` §41 的 `lease expired? NO →
   leave running`。该分支**不写任何列**（连 `version` 都不变），`waited=True`，
   `action` 只作**诊断**（`status` 取 `task.status`）—— 「对账」不等于「改状态」。
4. **四条入口状态之外的任务一律不动**（防御性守卫，**加严**而非放宽）：
   `store.transition` 只做 `WHERE status = :expected` 的条件更新，**不**做合法性判定；
   若把 `COMPLETED` / `CANCELLED` 等状态交给 `recover_task`，SQL 层会**成功**把它改成
   `RECOVERING` —— 那会绕过状态机。故本模块在 CAS 之前显式要求
   `status ∈ RECOVERY_ENTRY_STATUSES`（`docs/02` §52 / §66 的四态），否则原样返回
   `waited=False, reason="not_unfinished"`。
5. **`enqueue` 回调收到回读后的最新记录**：`docs/02` §42 的重排需要真实状态与
   `priority` / `created_at`（队列按 `priority` + `created_at` 排序，`docs/02` §17），
   故 CAS 成功后先 `store.get` 回读再回调；回读失败则回退为传入的 `task`
   （**不**因回读失败而放弃重排）。
6. **`FAIL` 落 `STRUCTAI-5300` 的 `to_dict()` JSON**：`docs/07` §11 的
   `TaskRecoveryError` 正是「恢复失败」的码；`error_json` 只放 20 码信封
   （`code` / `type` / `message` / `details` / `retryable`），**不**放原生 message
   （`docs/07` §14.3 / §14.4）。
7. **恢复**绝不**把任务置 `COMPLETED`**：三种动作只产生 `QUEUED` / `RUNNING` / `FAILED`，
   **没有**任何写入 `COMPLETED` 的路径 —— 该红线因此是**结构性**的（`docs/07` §14.4；
   `RECOVERING` 的出边里本来也没有 `COMPLETED`）。
8. **`RESUME` = 原地继续（状态保持 `RUNNING`）**并**重新入队**让 Worker 接管；
   `REQUEUE` = 回到 `QUEUED` 重跑**（`docs/02` §41 / §42）：只把状态 CAS 成 `RUNNING`
   而**不**入队，会让该任务永远不在队列里（Worker 取不到），每次启动扫描还把它
   `RUNNING → RECOVERING → RUNNING` 反复翻转 —— 任务一次也不会被执行。故 `RESUME`
   与 `REQUEUE` **共用**「CAS 成功后 `enqueue`」这条可执行路径；两者的差别只在**落哪个
   状态**（`RUNNING` vs `QUEUED`）。`TaskWorker.run_task` 因此把预执行状态放宽为
   `QUEUED` **或** `RUNNING`（`worker.py` 模块裁决 10：`RUNNING` 的接管即本节的 `RESUME`）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，
**不**依赖 `app.infrastructure`（持久化经 Domain 契约 `TaskStore`、操作定义经 Domain 契约
`OperationRegistry` 注入），也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from app.domain.enums import TaskStatus
from app.domain.errors import TaskRecoveryError
from app.domain.protocols import OperationRegistry, TaskRecord, TaskStore

__all__ = [
    "POLICY_TO_ACTION",
    "RECOVERY_ENTRY_STATUSES",
    "RECOVERY_STAGE",
    "UNKNOWN_POLICY_FALLBACK",
    "RecoveryAction",
    "RecoveryOutcome",
    "RecoveryService",
]

RECOVERY_STAGE: Final[str] = "recovery"
"""错误 / 诊断的 `stage` 取值（与 `lease` / `progress` 同口径）。"""

RECOVERY_ENTRY_STATUSES: Final[tuple[TaskStatus, ...]] = (
    TaskStatus.QUEUED,
    TaskStatus.RUNNING,
    TaskStatus.PROCESSING,
    TaskStatus.RECOVERING,
)
"""启动恢复**只**扫描的四条入口状态（`docs/02` §52 / §66；`docs/07` §10.2）。

⚠️ `COMPLETED` / `CANCELLED` **不在**其中（已终结，无需恢复）；
`FAILED` / `TIMEOUT` / `RETRYING` / `CREATED` / `VALIDATING` / `CANCEL_REQUESTED`
也**不在**其中（它们的推进归重试链与取消链，不归启动恢复）。
"""

UNKNOWN_POLICY_FALLBACK: Final[str] = "FAIL"
"""未知 `recovery_policy` 的回落值（见模块裁决 1；`docs/02` §11 的字段默认值也是 `FAIL`）。"""


class RecoveryAction(StrEnum):
    """服务器启动恢复的动作词表（`docs/02` §18 / §42 / §52）。

    ⚠️ 与 `recovery_policy`（`docs/02` §45 的 `SAFE_RETRY` / `STATE_RECONCILE` /
    `MANUAL_REVIEW` / `FAIL`）是**两套**词表：`POLICY_TO_ACTION` 是它们之间唯一的
    转换点（见模块裁决 1）。

    - `REQUEUE` —— 重新入队（`docs/02` §42 的「重排」；第一阶段优先）；
    - `RESUME` —— 原地恢复（Worker 重新取租约继续）；
    - `FAIL` —— 置 `FAILED` 并记录 `STRUCTAI-5300`。
    """

    REQUEUE = "REQUEUE"
    RESUME = "RESUME"
    FAIL = "FAIL"


POLICY_TO_ACTION: Final[Mapping[str, RecoveryAction]] = MappingProxyType(
    {
        "SAFE_RETRY": RecoveryAction.REQUEUE,
        "STATE_RECONCILE": RecoveryAction.RESUME,
        "MANUAL_REVIEW": RecoveryAction.FAIL,
        "FAIL": RecoveryAction.FAIL,
    }
)
"""`recovery_policy`（`docs/02` §45）→ 恢复动作（`docs/02` §18 / §42）的**唯一**转换点。

⚠️ 未知策略**不在**本映射内：调用方必须用
`POLICY_TO_ACTION.get(policy, RecoveryAction.FAIL)` 显式回落 `FAIL`
（**不**臆测可重试，见模块裁决 1）。
"""

Clock = Callable[[], datetime]
"""取当前时间的可注入时钟（验收测试据此制造过期租约；`docs/02` §41 的 `check lease`）。"""


@dataclass(frozen=True, slots=True)
class RecoveryOutcome:
    """一条任务的恢复结果（`docs/02` §41 的决策结果）。

    Attributes:
        task_id: 任务标识。
        action: 本次（或**诊断**用的）恢复动作（`docs/02` §18 的三词表）。
        status: 恢复后（或保持）的**真实**状态。
        policy: 该任务的 `recovery_policy`（`docs/02` §45 的四词表）；操作未登记时取
            `UNKNOWN_POLICY_FALLBACK`。
        waited: 是否「等待 / 对账」—— 租约仍有效（`docs/02` §41 的 `NO → leave running`）
            或 CAS 失败（状态已被别人推进）时为 `True`，此时**零状态变更**。
        reason: `""`（正常） / `"state_changed"`（CAS 失败） / `"not_unfinished"`
            （任务不在四条入口状态内，见模块裁决 4）。
    """

    task_id: str
    action: RecoveryAction
    status: TaskStatus
    policy: str
    waited: bool
    reason: str = ""


class RecoveryService:
    """服务器启动恢复（`docs/02` §18 / §40–§45 / §52 / §66 / §81；`docs/07` §10.2）。

    ⚠️ 持久化经 Domain 契约 `TaskStore` 注入、操作定义经 Domain 契约
    `OperationRegistry` 注入：本模块**不**依赖 `app.infrastructure`（`docs/07` §14.1）。
    事务边界归调用方的 `UnitOfWork`（`docs/02` §16）—— 本类**从不** `commit` / `rollback`。

    🔴 **绝不**把恢复中的任务置 `COMPLETED`（`docs/07` §14.4）：本类的三种动作只产生
    `QUEUED` / `RUNNING` / `FAILED`（见模块裁决 7）。
    """

    def __init__(
        self,
        store: TaskStore,
        operations: OperationRegistry,
        *,
        enqueue: Callable[[TaskRecord], Awaitable[None]] | None = None,
        clock: Clock | None = None,
    ) -> None:
        """绑定任务存储、操作注册表与可选的重排回调。

        Args:
            store: `docs/02` §34 的持久化入口（`unfinished` / `transition` / `get`）。
            operations: 运行时 Operation Registry（`docs/02` §28）；`recovery_policy`
                由它给出（`docs/02` §45 的「最终由 `OperationDefinition` 指定」）。
            enqueue: 重排回调（`docs/02` §42 的「重排」）；`REQUEUE` **与** `RESUME` 都会
                调用它（见模块裁决 8）；缺省 `None` 表示只改状态、不入队（Core Alpha
                允许不装配队列）。
            clock: 可注入时钟；缺省为带时区的 UTC 当前时间（`docs/02` §41 的 `now`）。
        """
        self._store = store
        self._operations = operations
        self._enqueue = enqueue
        self._clock: Clock = clock or _utc_now

    # ===== 只读视图 =====

    @property
    def store(self) -> TaskStore:
        """被绑定的存储（只读用途）。"""
        return self._store

    @property
    def operations(self) -> OperationRegistry:
        """被绑定的操作注册表（只读用途）。"""
        return self._operations

    def now(self) -> datetime:
        """当前时间（`docs/02` §41 的 `now`；缺省为带时区的 UTC）。"""
        return self._clock()

    # ===== `docs/02` §42：启动扫描 =====

    async def recover_unfinished_tasks(self) -> tuple[RecoveryOutcome, ...]:
        """扫描并逐条恢复未完成任务（`docs/02` §42 / §52 / §66；`docs/07` §10.2）。

        Returns:
            每条未完成任务一条 `RecoveryOutcome`（顺序与存储返回的顺序一致 ——
            存储按 `priority` + `created_at` **有界**返回，见 `repositories/task.py`）。

        ⚠️ 只扫描 `RECOVERY_ENTRY_STATUSES` 的四态（`docs/02` §52 / §66）：
        `COMPLETED` / `CANCELLED` 等状态**不会**进入恢复流程。
        """
        tasks = await self._store.unfinished(
            statuses=tuple(str(status) for status in RECOVERY_ENTRY_STATUSES),
        )
        outcomes: list[RecoveryOutcome] = []
        for task in tasks:
            outcomes.append(await self.recover_task(task))
        return tuple(outcomes)

    # ===== `docs/02` §41：单条恢复 =====

    async def recover_task(self, task: TaskRecord) -> RecoveryOutcome:
        """恢复一条任务（`docs/02` §41 的 `check lease → RECOVERING → REQUEUE/RESUME/FAIL`）。

        Args:
            task: 待恢复的任务快照（通常来自 `recover_unfinished_tasks` 的扫描）。

        Returns:
            `RecoveryOutcome`：**真实**状态 + 动作 + 是否等待 / 对账 + `reason`。

        Raises:
            ValueError: `task.status` 不在 12 态内（数据错误，**不**静默当作某个状态）。
        """
        now = self.now()
        current = TaskStatus(str(task.status))
        policy, action = await self._policy_for(task)

        if not task.lease_is_expired(now):
            # 见模块裁决 3：租约仍有效 → 等待 / 对账，**零状态变更**。
            return RecoveryOutcome(
                task_id=task.id,
                action=action,
                status=current,
                policy=policy,
                waited=True,
            )

        if current not in RECOVERY_ENTRY_STATUSES:
            # 见模块裁决 4：四条入口状态之外一律不动（防御性守卫）。
            return RecoveryOutcome(
                task_id=task.id,
                action=action,
                status=current,
                policy=policy,
                waited=False,
                reason="not_unfinished",
            )

        if current is not TaskStatus.RECOVERING:
            moved = await self._store.transition(
                task.id,
                expected=str(current),
                new=str(TaskStatus.RECOVERING),
            )
            if not moved:
                # 状态已被别人推进：**不**覆盖（`docs/07` §14.4）。
                return RecoveryOutcome(
                    task_id=task.id,
                    action=action,
                    status=current,
                    policy=policy,
                    waited=True,
                    reason="state_changed",
                )

        return await self._apply(task, action, policy)

    # ===== 内部 =====

    async def _policy_for(self, task: TaskRecord) -> tuple[str, RecoveryAction]:
        """取该任务的 `recovery_policy` 与对应恢复动作（见模块裁决 1）。

        Returns:
            `(policy, action)`：操作未登记时 `policy = UNKNOWN_POLICY_FALLBACK`，
            未知策略一律 `FAIL`（**不**臆测可重试）。
        """
        definition = await self._operations.get(task.operation)
        policy = definition.recovery_policy if definition is not None else UNKNOWN_POLICY_FALLBACK
        return policy, POLICY_TO_ACTION.get(policy, RecoveryAction.FAIL)

    async def _apply(
        self,
        task: TaskRecord,
        action: RecoveryAction,
        policy: str,
    ) -> RecoveryOutcome:
        """按恢复动作出结果（`docs/02` §41 的 `REQUEUE / RESUME / FAIL`）。

        ⚠️ 三种动作都从 `RECOVERING` 出发（上一步已 CAS 到位），且**没有**任何写入
        `COMPLETED` 的路径（`docs/07` §14.4；见模块裁决 7）。
        """
        if action is RecoveryAction.REQUEUE:
            return await self._requeue(task, policy)
        if action is RecoveryAction.RESUME:
            return await self._resume(task, policy)
        return await self._fail(task, policy)

    async def _requeue(self, task: TaskRecord, policy: str) -> RecoveryOutcome:
        """`RECOVERING → QUEUED` 并重排（`docs/02` §42；见模块裁决 2 / 5）。"""
        moved = await self._store.transition(
            task.id,
            expected=str(TaskStatus.RECOVERING),
            new=str(TaskStatus.QUEUED),
        )
        if not moved:
            return RecoveryOutcome(
                task_id=task.id,
                action=RecoveryAction.REQUEUE,
                status=TaskStatus.RECOVERING,
                policy=policy,
                waited=True,
                reason="state_changed",
            )
        if self._enqueue is not None:
            await self._enqueue(await self._read_back(task))
        return RecoveryOutcome(
            task_id=task.id,
            action=RecoveryAction.REQUEUE,
            status=TaskStatus.QUEUED,
            policy=policy,
            waited=False,
        )

    async def _resume(self, task: TaskRecord, policy: str) -> RecoveryOutcome:
        """`RECOVERING → RUNNING` **并重新入队**（原地恢复；`docs/02` §41 / §42）。

        ⚠️ 只 CAS 成 `RUNNING` 是**不够**的（见模块裁决 8）：`RESUME` 的语义是「原地继续」，
        但状态 `RUNNING` 的任务**不在队列里**，Worker 永远取不到它 —— 于是每次启动扫描都
        把它 `RUNNING → RECOVERING → RUNNING` 反复翻转，任务一次也不会被执行。
        故与 `REQUEUE` **共用可执行路径**：CAS 成功后同样 `enqueue`（回调收到回读后的最新
        记录，`docs/02` §42 的「重排」），让 Worker 按 `docs/02` §42 的 `RESUME` 语义接管
        （`TaskWorker.run_task` 接受 `RUNNING` 的预执行状态，见 `worker.py` 模块裁决 10）。

        Returns:
            `RecoveryOutcome`：`status` 为 `RUNNING`，`waited=False`；CAS 失败时
            `waited=True, reason="state_changed"`（**不**覆盖别人的推进）。
        """
        moved = await self._store.transition(
            task.id,
            expected=str(TaskStatus.RECOVERING),
            new=str(TaskStatus.RUNNING),
        )
        if not moved:
            return RecoveryOutcome(
                task_id=task.id,
                action=RecoveryAction.RESUME,
                status=TaskStatus.RECOVERING,
                policy=policy,
                waited=True,
                reason="state_changed",
            )
        if self._enqueue is not None:
            await self._enqueue(await self._read_back(task))
        return RecoveryOutcome(
            task_id=task.id,
            action=RecoveryAction.RESUME,
            status=TaskStatus.RUNNING,
            policy=policy,
            waited=False,
        )

    async def _fail(self, task: TaskRecord, policy: str) -> RecoveryOutcome:
        """`RECOVERING → FAILED` 并记录 `STRUCTAI-5300`（`docs/07` §11；见模块裁决 6）。"""
        error = TaskRecoveryError(
            "Task recovery failed",
            details={"stage": RECOVERY_STAGE, "reason": "policy_fail", "policy": policy},
        )
        moved = await self._store.transition(
            task.id,
            expected=str(TaskStatus.RECOVERING),
            new=str(TaskStatus.FAILED),
            fields={
                "error_json": json.dumps(error.to_dict(), ensure_ascii=False, sort_keys=True),
            },
        )
        if not moved:
            return RecoveryOutcome(
                task_id=task.id,
                action=RecoveryAction.FAIL,
                status=TaskStatus.RECOVERING,
                policy=policy,
                waited=True,
                reason="state_changed",
            )
        return RecoveryOutcome(
            task_id=task.id,
            action=RecoveryAction.FAIL,
            status=TaskStatus.FAILED,
            policy=policy,
            waited=False,
        )

    async def _read_back(self, task: TaskRecord) -> TaskRecord:
        """回读任务（见模块裁决 5）；读不到时回退为传入的 `task`。

        ⚠️ 回读失败**不**放弃重排：`enqueue` 仍会被调用（用 CAS 之前拿到的 `task`），
        否则「状态已 `QUEUED` 但没入队」会让任务永远停在队列之外。
        """
        latest = await self._store.get(task.id, task.tenant_id)
        return task if latest is None else latest


def _utc_now() -> datetime:
    """默认时钟：带时区的 UTC 当前时间（`docs/02` §41 的 `datetime.now(timezone.utc)`）。"""
    return datetime.now(UTC)
