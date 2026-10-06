"""Application · Task · Progress（`docs/07` §10.2 / §12 P22–P28；`docs/02` §31–§33 / §44）。

权威来源
--------
- `docs/02` §31（`task`）—— `update_progress(task_id, progress)` 的**原文实现**：
  `progress = max(0, min(100, progress))` 后再写库；范围 `0 → 100`。
- `docs/02` §32（`task`）—— `TaskProgress(task_id, progress, message)` 事件，
  经 Event Bus 后续转 MCP progress notification。
- `docs/02` §33（`task`）—— **Progress 不可信**：Adapter 返回 `150` → Core 归一化为 `100`；
  返回 `-10` → 归一化为 `0`。
- `docs/02` §44（`task`）—— `ProgressReporter.report(task_id, progress, message=None)`
  的方法形状（本模块照抄）。
- `docs/07` §10.2 —— 「Progress 唯一来源是 Task Engine；范围 0–100；**Progress 不可信**
  （来自 Adapter 的进度需校验）」。
- `docs/07` §11 —— `STRUCTAI-1200 Engineering Validation Error`（工程语义非法）、
  `STRUCTAI-5000 Task Error`（任务执行失败，含「任务不存在」口径）。
- `docs/07` §14.3 —— 绝不记录 secret：错误 `details` 只放 `stage` / `reason`。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **非数值一律拒绝，绝不回落默认值**（`docs/02` §33；本批裁决，见 `docs/07` §16 R48）：
   `docs/02` §31 的原文是 `max(0, min(100, progress))`，对**数值**给出「夹到区间」的语义；
   但 §33 明确「来自 Adapter 的进度不可信」。因此本模块把两条口径**分开**：

   - `int` / `float`（非 `bool`）→ 先 `int(...)` 截断再夹到 `[0, 100]`
     （`150 → 100`、`-10 → 0`、`42.7 → 42`）；
   - `bool` → **拒绝**：`bool` 是 `int` 的子类，若按数值采信，`True` 会静默变成 `1%`
     —— 那是「把类型错误当成进度值」，与 §33 的不可信口径冲突；
   - 非数值（`None` / `str` / 序列 / 映射 / 其它对象）与 `NaN` / `inf` → **拒绝**
     （`STRUCTAI-1200`，`details = {stage: "progress", reason: <词表之一>}`）。

   **不**回落 `0` / `100` / 上一次的值：静默兜底会让「Adapter 传了垃圾」在库里表现为
   「进度正常」，调用方再也看不到问题（`docs/07` §14.4：不允许「带病继续」）。
2. **`bool` 走 `not_a_number`、`NaN` / `inf` 走 `not_finite`**：`PROGRESS_UNTRUSTED_REASONS`
   是两个词的**唯一**来源，使「不可信」在错误信封里可被机器区分（`docs/07` §14.3 只放
   `stage` / `reason`）。
3. **`report` 与 `report_from_adapter` 共用同一条写库路径**：`report_from_adapter` 只多一层
   「Adapter 输入不可信」的语义标注，**不**是第二份实现（`docs/02` §28 的「只允许一处实现」
   同理）。两者都先 `sanitize_progress` 再 `report`。
4. **进度只有一个写入口**：本模块是 `tasks.progress` 的**唯一** Application 侧写入点
   （`docs/07` §10.2 的「唯一来源是 Task Engine」）。`TaskEngine` / `TaskWorker`
   一律经 `ProgressReporter` 更新进度，**不**自行写该列 —— 否则「唯一来源」不成立。
5. **`message` 原样透传、不落库**：`docs/02` §32 的 `message` 只进事件（供 MCP progress
   notification），`tasks` 表**没有**该列（`docs/07` §4.3 #19，本批**不得改表**），
   故本模块**不**把它写进任何持久化结构。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，
**不**依赖 `app.infrastructure`（持久化经 Domain 契约 `TaskStore` 注入，事件经 Domain
契约 `EventBus` 注入），也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from app.domain.errors import EngineeringValidationError, TaskError
from app.domain.events import TaskProgress
from app.domain.protocols import EventBus, TaskStore

__all__ = [
    "PROGRESS_MAX",
    "PROGRESS_MIN",
    "PROGRESS_STAGE",
    "PROGRESS_UNTRUSTED_REASONS",
    "ProgressReporter",
    "ProgressUpdate",
    "sanitize_progress",
]

PROGRESS_MIN: Final[int] = 0
"""进度下界（`docs/02` §31 / §33 的 `0`）。"""

PROGRESS_MAX: Final[int] = 100
"""进度上界（`docs/02` §31 / §33 的 `100`）。"""

PROGRESS_STAGE: Final[str] = "progress"
"""错误 `details.stage` 的固定取值（与 `state_machine` / `lease` 同口径）。"""

PROGRESS_UNTRUSTED_REASONS: Final[tuple[str, ...]] = (
    "not_a_number",
    "not_finite",
)
"""进度不可信的原因词表（见模块裁决 1 / 2）。

- `not_a_number` —— 取值不是数值（含 `bool`）；
- `not_finite` —— 取值是 `NaN` / `inf`（`float` 的「非有限」值）。
"""


def sanitize_progress(value: object) -> int:
    """把不可信的进度取值规整为 `[0, 100]` 的整数（`docs/02` §31 / §33）。

    Args:
        value: 待校验的进度取值（可能来自 Adapter，因此**不可信**）。

    Returns:
        `0`–`100` 的整数：`150 → 100`、`-10 → 0`、`42 → 42`、`42.7 → 42`
        （`docs/02` §31 的 `max(0, min(100, progress))` 与 §33 的三个示例）。

    Raises:
        EngineeringValidationError: `STRUCTAI-1200` —— 取值不是有限数值
            （`bool` / `None` / 字符串 / 序列 / 映射 / `NaN` / `inf`）。
            `details = {stage: "progress", reason: <词表之一>}`；
            **不**回落默认值、**不**静默忽略（见模块裁决 1）。
    """
    if isinstance(value, bool):
        # `bool` 是 `int` 的子类：显式先拦，避免 `True` 被当成 `1%`（见模块裁决 1 / 2）。
        raise _untrusted("not_a_number")
    if isinstance(value, int):
        return _clamp(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _untrusted("not_finite")
        return _clamp(int(value))
    raise _untrusted("not_a_number")


@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    """一次进度上报的结果（`docs/02` §32 的 `TaskProgress` 载荷）。

    Attributes:
        task_id: 任务标识。
        progress: 已规整到 `[0, 100]` 的进度值（实际落库的值）。
        message: 可选的人类可读说明（`docs/02` §32；只进事件，**不**落库 —— 见模块裁决 5）。
    """

    task_id: str
    progress: int
    message: str | None = None


class ProgressReporter:
    """任务进度的**唯一**写入口（`docs/07` §10.2；`docs/02` §31–§33 / §44）。

    ⚠️ 持久化经 Domain 契约 `TaskStore` 注入：本模块**不**依赖 `app.infrastructure`
    （`docs/07` §14.1）。事务边界归调用方的 `UnitOfWork`（`docs/02` §16）——
    本类**从不** `commit` / `rollback`。

    🔴 `Task Engine` 是进度的**唯一来源**（`docs/07` §10.2），因此
    `app/application/task/engine.py` 与 `worker.py` **不得**自行写 `tasks.progress`：
    它们只能经本类（见模块裁决 4）。
    """

    def __init__(self, store: TaskStore, *, bus: EventBus | None = None) -> None:
        """绑定进度存储与可选事件总线。

        Args:
            store: `docs/02` §31 的持久化入口（`update_progress` / `get`）。
            bus: 可选 `EventBus`（`docs/02` §32 / §34）；缺省不发布事件。
        """
        self._store = store
        self._bus = bus

    @property
    def store(self) -> TaskStore:
        """被绑定的存储（只读用途）。"""
        return self._store

    @property
    def bus(self) -> EventBus | None:
        """被绑定的事件总线（只读用途；缺省 `None`）。"""
        return self._bus

    async def report(
        self,
        task_id: str,
        progress: object,
        message: str | None = None,
    ) -> ProgressUpdate:
        """上报进度（`docs/02` §31 的 `update_progress` ＋ §32 的事件）。

        Args:
            task_id: 任务标识。
            progress: 进度取值（**不可信**，先经 `sanitize_progress`）。
            message: 可选的人类可读说明（只进事件，见模块裁决 5）。

        Returns:
            `ProgressUpdate`：含**实际落库**的规整后进度值。

        Raises:
            EngineeringValidationError: `STRUCTAI-1200` —— 进度取值不可信
                （`details.stage = "progress"`；见 `sanitize_progress`）。
            TaskError: `STRUCTAI-5000` —— 任务不存在（`update_progress` 影响 0 行）。
                `details = {stage: "progress", reason: "unknown_task"}`。
        """
        value = sanitize_progress(progress)
        updated = await self._store.update_progress(task_id, value)
        if not updated:
            raise TaskError(
                "Task not found for progress update",
                details={"stage": PROGRESS_STAGE, "reason": "unknown_task"},
            )
        if self._bus is not None:
            await self._bus.publish(
                TaskProgress.create(
                    task_id=UUID(task_id),
                    progress=value,
                    message=message,
                )
            )
        return ProgressUpdate(task_id=task_id, progress=value, message=message)

    async def report_from_adapter(
        self,
        task_id: str,
        value: object,
        message: str | None = None,
    ) -> ProgressUpdate:
        """采信 Adapter 上报的进度（`docs/02` §33；`docs/07` §10.2）。

        🔴 这是**唯一**采信 Adapter 进度的入口：Adapter 的进度**不可信**，
        必须先 `sanitize_progress` 校验（不可信 → `STRUCTAI-1200`），再走与
        `report` **完全相同**的写库 / 发事件路径（见模块裁决 3）。

        Args:
            task_id: 任务标识。
            value: Adapter 上报的原始进度取值。
            message: 可选说明。

        Returns:
            `ProgressUpdate`（含实际落库的规整值）。

        Raises:
            EngineeringValidationError: `STRUCTAI-1200` —— Adapter 进度不可信。
            TaskError: `STRUCTAI-5000` —— 任务不存在。
        """
        return await self.report(task_id, value, message)


def _clamp(value: int) -> int:
    """把整数进度夹到 `[0, 100]`（`docs/02` §31 的 `max(0, min(100, progress))`）。"""
    return max(PROGRESS_MIN, min(PROGRESS_MAX, value))


def _untrusted(reason: str) -> EngineeringValidationError:
    """构造「进度不可信」的错误（`STRUCTAI-1200`；见模块裁决 1）。

    ⚠️ `details` 只放 `stage` / `reason`：**不**回显被拒的取值本身
    （取值可能来自 Adapter，形态不可控；`docs/07` §14.3 的严格口径）。
    """
    return EngineeringValidationError(
        "Task progress is not a trustworthy number",
        details={"stage": PROGRESS_STAGE, "reason": reason},
    )
