"""Application · Task · StateMachine（`docs/07` §10.1 / §12 P22–P28；`docs/02` §7 / §8 / §47）。

权威来源
--------
- `docs/07` §10.1 —— **12 态**与转移图（冻结）：`CREATED → VALIDATING → QUEUED →
  RUNNING → PROCESSING → COMPLETED`，异常分支 `FAILED` / `TIMEOUT` /
  `CANCEL_REQUESTED → CANCELLED` / `RETRYING → QUEUED` / `RECOVERING`；
  「**状态机必须集中实现**（`task/state_machine.py`），不得散落」。
- `docs/02` §8（`py` / `blue` 来源）—— `transition(new_status)` 的**原文实现**：
  取 `ALLOWED_TRANSITIONS[self.status]`，不在其中即 `raise TaskStateError(
  f"Invalid transition: {self.status} -> {new_status}")`，否则赋值。
- `docs/02` §7 —— 同一张表的另一份来源（**更宽**：含 `QUEUED/RUNNING/PROCESSING/
  CANCEL_REQUESTED → RECOVERING`、`FAILED → RETRYING`、`TIMEOUT → {RETRYING,
  FAILED, RECOVERING}`，且 `COMPLETED` / `CANCELLED` 为终态空集）。
- `docs/02` §76（State Machine Test）—— 合法链 `VALIDATING → QUEUED → RUNNING →
  PROCESSING → COMPLETED` 必须成功；在 `COMPLETED` 上再 `transition(RUNNING)`
  必须 `TaskStateError`。
- `docs/07` §10.2 / §14.4 —— 非法转移**必须拒绝**（不得静默忽略、不得自动纠正）；
  **禁止**把恢复中的 Task 直接标记 `COMPLETED`。

落地裁决（只补实现手段，不改任何取值）
--------------------------------------
1. **`ALLOWED_TRANSITIONS` 取两份来源的并集**：`docs/02` §8 与 §7 是同一张表的
   两处写法，二者**互有缺项**（§8 缺 `RECOVERING` 的四条入口与 `FAILED →
   RETRYING` / `TIMEOUT → RETRYING`，§7 缺 `RUNNING → COMPLETED`）。只取其一都会
   让 `docs/02` §77（Retry）/ §78（Timeout）/ §81（Recovery）的验收链**无法实现**。
   故本模块以**并集**为准，并保证：① 12 态**恰好** 12 个键（含两个终态空集）；
   ② §8 与 §7 的每一条边都在并集内（两份来源都不落空）；③ 两个终态**无出边**
   （`docs/07` §10.1 的 `COMPLETED` / `CANCELLED` 是终点）。
2. **「恢复中的 Task 不得直接 `COMPLETED`」由表本身保证**：`RECOVERING` 的出边
   只有 `QUEUED` / `RUNNING` / `FAILED`（`docs/02` §7 / §8 一致），**没有**
   `COMPLETED` —— 该红线因此是**结构性**的，而不是靠调用方自觉（`docs/07` §14.4）。
3. **非法转移落 `STRUCTAI-1300`**：20 码契约（`docs/07` §11）里没有「状态机」
   专用码，**不新增码**。`TaskStateError` 实现为既有
   `ConcurrencyConflictError` 的子类 —— 理由：① 本项目的状态推进一律是
   **条件更新**（`WHERE status = :expected`，见 `domain.protocols.TaskStore.transition`），
   影响 0 行 = 乐观锁失败 = `STRUCTAI-1300`（§11 的触发场景逐字包含「乐观锁失败」）；
   ② 状态机层的拒绝与存储层的 CAS 失败因此**同码同族**，客户端只有一种「状态冲突」
   语义；③ §11 的 `STRUCTAI-5000` 是「任务**执行**失败」，而一次被拒的转移
   **什么都没执行**，用它反而不准确。`details` 只放 `stage` / `from` / `to`
   （状态名是 Core 的冻结取值，非敏感）。
4. **纯函数 + 值对象两种用法**：`transition()`（模块级纯函数）供持久化层与测试
   逐格断言；`TaskStateMachine`（持有 `status`）复刻 `docs/02` §8 的
   `task.transition(...)` 调用形态。**两者共用同一张表**，不存在第二份判定
   （`docs/07` §10.1：集中实现，不得散落）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 SQLAlchemy / FastAPI / MCP SDK /
httpx，**不**依赖 `app.infrastructure`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from app.domain.enums import TaskStatus
from app.domain.errors import ConcurrencyConflictError

__all__ = [
    "ALLOWED_TRANSITIONS",
    "STATE_MACHINE_STAGE",
    "TASK_STATE_SEQUENCE",
    "TASK_STATUSES",
    "TERMINAL_STATUSES",
    "TaskStateError",
    "TaskStateMachine",
    "can_transition",
    "transition",
]

TASK_STATE_SEQUENCE: Final[tuple[TaskStatus, ...]] = (
    TaskStatus.CREATED,
    TaskStatus.VALIDATING,
    TaskStatus.QUEUED,
    TaskStatus.RUNNING,
    TaskStatus.PROCESSING,
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCEL_REQUESTED,
    TaskStatus.CANCELLED,
    TaskStatus.TIMEOUT,
    TaskStatus.RETRYING,
    TaskStatus.RECOVERING,
)
"""12 态的**规范顺序**（`docs/07` §10.1 / `docs/02` §8 的枚举顺序，逐项照抄）。

顺序即 `app.domain.enums.TaskStatus` 的声明顺序；「恰好 12 态」由
`tests/test_task_engine_p22_p28.py` 逐项断言（防漂移）。
"""

TASK_STATUSES: Final[frozenset[TaskStatus]] = frozenset(TASK_STATE_SEQUENCE)
"""12 态的集合视图（`docs/07` §10.1）。"""

TERMINAL_STATUSES: Final[frozenset[TaskStatus]] = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.CANCELLED}
)
"""终态：**无出边**（`docs/07` §10.1 的 `COMPLETED` / `CANCELLED`；`docs/02` §7 的空集）。

⚠️ `FAILED` / `TIMEOUT` **不是**终态：它们还有 `RETRYING` 出边
（`docs/02` §7 / §77 / §78 的 Retry 链）。
"""

ALLOWED_TRANSITIONS: Final[Mapping[TaskStatus, frozenset[TaskStatus]]] = MappingProxyType(
    {
        TaskStatus.CREATED: frozenset(
            {
                TaskStatus.VALIDATING,
                TaskStatus.CANCELLED,
            }
        ),
        TaskStatus.VALIDATING: frozenset(
            {
                TaskStatus.QUEUED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            }
        ),
        TaskStatus.QUEUED: frozenset(
            {
                TaskStatus.RUNNING,
                TaskStatus.CANCELLED,
                TaskStatus.RECOVERING,
            }
        ),
        TaskStatus.RUNNING: frozenset(
            {
                TaskStatus.PROCESSING,
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCEL_REQUESTED,
                TaskStatus.TIMEOUT,
                TaskStatus.RECOVERING,
            }
        ),
        TaskStatus.PROCESSING: frozenset(
            {
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCEL_REQUESTED,
                TaskStatus.TIMEOUT,
                TaskStatus.RECOVERING,
            }
        ),
        TaskStatus.COMPLETED: frozenset(),
        TaskStatus.FAILED: frozenset({TaskStatus.RETRYING}),
        TaskStatus.CANCEL_REQUESTED: frozenset(
            {
                TaskStatus.CANCELLED,
                TaskStatus.FAILED,
                TaskStatus.RECOVERING,
            }
        ),
        TaskStatus.CANCELLED: frozenset(),
        TaskStatus.TIMEOUT: frozenset(
            {
                TaskStatus.RETRYING,
                TaskStatus.FAILED,
                TaskStatus.RECOVERING,
            }
        ),
        TaskStatus.RETRYING: frozenset(
            {
                TaskStatus.QUEUED,
                TaskStatus.FAILED,
            }
        ),
        TaskStatus.RECOVERING: frozenset(
            {
                TaskStatus.QUEUED,
                TaskStatus.RUNNING,
                TaskStatus.FAILED,
            }
        ),
    }
)
"""冻结的转移表（`docs/02` §8 ∪ §7；见模块裁决 1）。

语义：`ALLOWED_TRANSITIONS[current]` = 从 `current` **允许**迁往的状态集合。
`COMPLETED` / `CANCELLED` 为空集（终态）。表内**没有**的格子一律**拒绝**
（`docs/07` §10.2），既不静默忽略也不自动纠正。
"""

STATE_MACHINE_STAGE: Final[str] = "state_machine"
"""错误 `details.stage` 的固定取值（与 `idempotency` / `confirmation` 同口径）。"""


class TaskStateError(ConcurrencyConflictError):
    """非法状态转移（`docs/02` §8 / §76）。

    ⚠️ **不新增 `STRUCTAI-xxxx` 码**（20 码契约不扩，`docs/07` §11）：本类实现为
    既有 `ConcurrencyConflictError`（**`STRUCTAI-1300`**）的子类，理由见模块裁决 3。
    消息格式逐字照抄 `docs/02` §8：`Invalid transition: <from> -> <to>`。
    """


def can_transition(current: TaskStatus | str, new: TaskStatus | str) -> bool:
    """该转移是否被允许（`docs/02` §8 的 `new_status in allowed`）。

    Args:
        current: 当前状态（`TaskStatus` 或其字符串取值）。
        new: 目标状态。

    Returns:
        `True` 仅当 `(current, new)` 落在 `ALLOWED_TRANSITIONS` 内。

    Raises:
        ValueError: 取值不在 12 态内（装配 / 数据错误，**不**静默当作非法转移）。
    """
    return _coerce(new) in ALLOWED_TRANSITIONS[_coerce(current)]


def transition(current: TaskStatus | str, new: TaskStatus | str) -> TaskStatus:
    """校验并返回目标状态（`docs/02` §8 的纯函数形态）。

    Args:
        current: 当前状态。
        new: 目标状态。

    Returns:
        校验通过后的目标状态（`TaskStatus`）。

    Raises:
        TaskStateError: 非法转移（`STRUCTAI-1300`）—— 拒绝，**不**忽略、**不**纠正。
        ValueError: 取值不在 12 态内。
    """
    source = _coerce(current)
    target = _coerce(new)
    if target not in ALLOWED_TRANSITIONS[source]:
        raise TaskStateError(
            f"Invalid transition: {source} -> {target}",
            details={
                "stage": STATE_MACHINE_STAGE,
                "from": str(source),
                "to": str(target),
            },
        )
    return target


class TaskStateMachine:
    """任务状态机（`docs/02` §8 的 `task.transition(...)` 形态）。

    持有单一 `status`，每次 `transition()` 都经同一张 `ALLOWED_TRANSITIONS`
    校验；**所有状态更新必须经过本类**（`docs/02` §8 末句）。
    """

    def __init__(self, status: TaskStatus | str = TaskStatus.CREATED) -> None:
        """以给定状态初始化（缺省 `CREATED`，`docs/02` §8）。

        Raises:
            ValueError: 初始状态不在 12 态内。
        """
        self._status = _coerce(status)

    @property
    def status(self) -> TaskStatus:
        """当前状态（只读；变更只能经 `transition()`）。"""
        return self._status

    def can(self, new: TaskStatus | str) -> bool:
        """当前状态下该转移是否允许（不改变状态）。"""
        return can_transition(self._status, new)

    def allowed(self) -> frozenset[TaskStatus]:
        """当前状态允许迁往的状态集合（`docs/02` §8 的 `allowed`）。"""
        return ALLOWED_TRANSITIONS[self._status]

    def transition(self, new: TaskStatus | str) -> TaskStatus:
        """执行一次转移（`docs/02` §8 的原文方法）。

        Returns:
            转移后的状态（`self.status` 已更新）。

        Raises:
            TaskStateError: 非法转移（`STRUCTAI-1300`）；状态**保持不变**。
        """
        self._status = transition(self._status, new)
        return self._status

    def __repr__(self) -> str:
        """诊断表示（只含状态名，无敏感字段）。"""
        return f"TaskStateMachine(status={self._status})"


def _coerce(status: TaskStatus | str) -> TaskStatus:
    """把状态取值规整为 `TaskStatus`（`docs/07` §10.1 的 12 态）。

    Raises:
        ValueError: 取值不在 12 态内（`TaskStatus` 的 `ValueError` 原样上抛 ——
            这是数据 / 装配错误，不是「非法转移」，两者语义不同）。
    """
    if isinstance(status, TaskStatus):
        return status
    return TaskStatus(str(status))
