"""Application · Execution · Postconditions（`docs/07` §12 P14–P18；`docs/02` §32）。

权威来源
--------
- `docs/02` §32（`blue` / `source9`）—— 后置条件，文件
  `application/execution/postconditions.py`。原文示例：
  `MODEL.NODE.CREATE` 的 Postcondition = 「node 存在」；
  `ANALYSIS.STATIC` 的 Postcondition = 「analysis task 已完成 + result 可查询」。
- `docs/07` §9 第 20 步 —— `Postconditions`，**先于** `Release Lock`（第 21 步）
  ——「锁与 Task 生命周期绑定」（`docs/07` §9 的不可变依据）。
- `docs/07` §11 —— 后置条件不满足落 **`STRUCTAI-5000` Task Error**
  （操作已尝试但未产生应有状态；20 码契约**不扩**）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **后置条件与前置条件同构、同样「事实驱动」**：`docs/02` §32 给的是**声明式**后置条件，
   本模块把它们表达为 `Postcondition(name, description, check)` 的目录，由
   `PostconditionEvaluator` 对 `ExecutionFacts` 求值。事实只来自**已完成**的步骤
   （任务状态、结果可用性、模型侧计数）；本模块不持有仓储、不发查询
   （与 `preconditions.py` 同一口径，`docs/02` §70）。
2. **三态结果**：事实缺失时返回 `None` = **未验证**（不是通过、也不是失败），
   由 `PostconditionReport.unverified` 如实报告 —— 避免「还没跑完就先断言」。
3. **失败错误码 = `STRUCTAI-5000`（与前置条件的 `STRUCTAI-1200` 有意不对称）**：
   前置条件不满足 = **什么都没做** → 工程校验族 `STRUCTAI-1200`（`docs/02` §90）；
   后置条件不满足 = **已经做了，但应有状态不存在** → 任务执行失败 `STRUCTAI-5000`
   （`docs/07` §11 的 `Task Error`）。两者都在 20 码契约内，**不新增码**；
   `details.stage = "postconditions"` 区分阶段。
4. **顺序：后置条件先于释放锁**（`docs/07` §9 第 20 / 21 步）：本模块因此**不**做任何
   释放动作、也不感知锁；调用方必须在 `Postconditions` 之后才 `release`。
   `POSTCONDITION_STAGE_ORDER` 把这一相对顺序固化为可断言的常量。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库、`app.domain` 与同层的 `preconditions` / `app.application.resource`：
**不**引用 ORM / Web 框架 / MCP SDK / httpx，**不**依赖 `app.infrastructure`，
也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from app.application.execution.preconditions import ExecutionFacts
from app.domain.enums import TaskStatus
from app.domain.errors import TaskError
from app.domain.protocols import OperationDefinition

__all__ = [
    "POSTCONDITIONS",
    "POSTCONDITION_OPERATIONS",
    "POSTCONDITION_STAGE_ORDER",
    "Postcondition",
    "PostconditionCheck",
    "PostconditionEvaluator",
    "PostconditionReport",
]

POSTCONDITION_STAGE_ORDER: Final[tuple[str, ...]] = (
    "Postconditions",
    "Release Lock",
)
"""后置条件相对释放锁的顺序（`docs/07` §9 第 20 / 21 步，**冻结**）。

「锁与 Task 生命周期绑定」（`docs/07` §9 的不可变依据）：后置条件校验必须在
释放锁**之前**完成 —— 本常量把该顺序固化为可断言的对象（见模块裁决 4）。
"""


def _is_present(value: object) -> bool:
    """计数 / 布尔事实是否「存在」：数值 > 0 或布尔 `True`。

    ⚠️ 与 `preconditions.py` 的同名私有工具**有意各自保留一份**：两个模块只共享
    公开的 `ExecutionFacts` 形状，不互相导入私有实现（避免把内部工具变成隐式契约）。
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    return bool(value)


@dataclass(frozen=True, slots=True)
class Postcondition:
    """一条声明式后置条件（`docs/02` §32）。

    Attributes:
        name: 机器可读的名字（用于报告与断言）。
        description: 人可读描述（照抄 `docs/02` §32 的措辞）。
        check: 求值函数（纯函数；见模块裁决 1）。
    """

    name: str
    description: str
    check: PostconditionCheck


PostconditionCheck = Callable[[ExecutionFacts], "list[str] | None"]
"""一条后置条件检查：`facts -> None | [未满足原因]`。

- `[]` —— 满足；
- `[原因, ...]` —— 不满足（`require()` 据此抛 `STRUCTAI-5000`）；
- `None` —— **事实不足，未验证**（见模块裁决 2）。
"""


@dataclass(frozen=True, slots=True)
class PostconditionReport:
    """一次后置条件求值的结果（`docs/02` §32）。

    Attributes:
        operation: Operation 名。
        satisfied: 已求值且满足的条件名（登记顺序）。
        unverified: 事实不足、未能求值的条件名（见模块裁决 2）。
        issues: 不满足的原因（人可读）。
    """

    operation: str
    satisfied: tuple[str, ...] = ()
    unverified: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """是否**没有**不满足项（未验证项**不**算失败，见模块裁决 2）。"""
        return not self.issues


# ===== 检查实现（`docs/02` §32）=====


def _node_exists(facts: ExecutionFacts) -> list[str] | None:
    """「node 存在」（`docs/02` §32 的 `MODEL.NODE.CREATE` 后置条件）。"""
    state = facts.model_state
    if not state:
        return None
    if not _is_present(state.get("nodes")):
        return ["postcondition not met: no node present after the operation"]
    return []


def _element_exists(facts: ExecutionFacts) -> list[str] | None:
    """「element 存在」（`docs/02` §32 的 `MODEL.NODE.CREATE` 后置条件的同族补齐）。"""
    state = facts.model_state
    if not state:
        return None
    if not _is_present(state.get("elements")):
        return ["postcondition not met: no element present after the operation"]
    return []


def _task_completed(facts: ExecutionFacts) -> list[str] | None:
    """「analysis task 已完成」（`docs/02` §32）。

    ⚠️ 只接受 `COMPLETED`：`docs/07` §14.4 明确「**禁止**把恢复中的 Task 直接标记
    `COMPLETED`」，因此 `RECOVERING` / `RETRYING` 等中间态一律视为未满足。
    """
    status = facts.task_status
    if status is None:
        return None
    if status != TaskStatus.COMPLETED.value:
        return [f"task is not completed (status={status})"]
    return []


def _result_available(facts: ExecutionFacts) -> list[str] | None:
    """「result 可查询」（`docs/02` §32）。"""
    available = facts.result_available
    if available is None:
        return None
    if not available:
        return ["postcondition not met: result is not queryable"]
    return []


#: 声明式后置条件目录（`docs/02` §32）。
POSTCONDITIONS: Mapping[str, tuple[Postcondition, ...]] = MappingProxyType(
    {
        "MODEL.NODE.CREATE": (Postcondition("node_exists", "node 存在", _node_exists),),
        "MODEL.NODE.UPDATE": (Postcondition("node_exists", "node 存在", _node_exists),),
        "MODEL.ELEMENT.CREATE": (Postcondition("element_exists", "element 存在", _element_exists),),
        "MODEL.ELEMENT.UPDATE": (Postcondition("element_exists", "element 存在", _element_exists),),
        "BUILD.COLUMN": (Postcondition("task_completed", "build task 已完成", _task_completed),),
        "ANALYSIS.STATIC": (
            Postcondition("task_completed", "analysis task 已完成", _task_completed),
            Postcondition("result_available", "result 可查询", _result_available),
        ),
        "DESIGN.STEEL": (
            Postcondition("task_completed", "design task 已完成", _task_completed),
            Postcondition("result_available", "result 可查询", _result_available),
        ),
    }
)
"""Operation → 后置条件（`docs/02` §32）。

⚠️ `MODEL.NODE.CREATE` / `ANALYSIS.STATIC` 两条是 §32 的**原文示例**；
其余是同族**同构补齐**（`BUILD.COLUMN` 是 `ASYNC` 操作 → 任务完成类后置条件）。
未登记的 Operation **没有**后置条件声明（不隐式兜底）。
"""

POSTCONDITION_OPERATIONS: Final[tuple[str, ...]] = tuple(sorted(POSTCONDITIONS))
"""已声明后置条件的 Operation 名（升序元组；供装配期核对与验收断言）。"""


class PostconditionEvaluator:
    """后置条件求值器（`docs/02` §32；`docs/07` §9 第 20 步）。

    ⚠️ 本类**不**读库、**不**发请求、**不**改状态、**不**感知锁：只对调用方提供的
    `ExecutionFacts` 求值（见模块裁决 1 / 4）。
    """

    def __init__(
        self,
        *,
        postconditions: Mapping[str, Sequence[Postcondition]] | None = None,
    ) -> None:
        """绑定后置条件目录。

        Args:
            postconditions: Operation → 后置条件；缺省用 `POSTCONDITIONS`（`docs/02` §32）。
        """
        source = POSTCONDITIONS if postconditions is None else postconditions
        self._postconditions: Mapping[str, tuple[Postcondition, ...]] = MappingProxyType(
            {name: tuple(items) for name, items in source.items()}
        )

    @property
    def operations(self) -> tuple[str, ...]:
        """已声明后置条件的 Operation 名（升序）。"""
        return tuple(sorted(self._postconditions))

    def for_operation(self, operation: str) -> tuple[Postcondition, ...]:
        """该 Operation 的后置条件（未声明时为空元组，不隐式兜底）。"""
        return self._postconditions.get(operation, ())

    def check(self, operation: str, facts: ExecutionFacts) -> PostconditionReport:
        """求值（`docs/02` §32）。

        Args:
            operation: Operation 名。
            facts: 流水线已产生的事实（`ExecutionFacts`）。

        Returns:
            `PostconditionReport`：已满足 / 未验证 / 不满足三类条目。
        """
        satisfied: list[str] = []
        unverified: list[str] = []
        issues: list[str] = []
        for postcondition in self.for_operation(operation):
            outcome = postcondition.check(facts)
            if outcome is None:
                unverified.append(postcondition.name)
            elif outcome:
                issues.extend(f"{postcondition.name}: {reason}" for reason in outcome)
            else:
                satisfied.append(postcondition.name)
        return PostconditionReport(
            operation=operation,
            satisfied=tuple(satisfied),
            unverified=tuple(unverified),
            issues=tuple(issues),
        )

    async def require(
        self,
        operation: OperationDefinition,
        facts: ExecutionFacts,
    ) -> PostconditionReport:
        """要求后置条件满足（`docs/07` §9 第 20 步，**先于**释放锁）。

        Args:
            operation: 操作定义（`docs/02` §24）。
            facts: 流水线已产生的事实（含任务状态 / 结果可用性 / 模型侧计数）。

        Returns:
            `PostconditionReport`（未验证项如实返回，调用方可据此记录诊断）。

        Raises:
            TaskError: `STRUCTAI-5000`（见模块裁决 3），
                `details = {stage: "postconditions", operation, issues}`。
                仅在存在**不满足**项时抛出；未验证项不阻断（见模块裁决 2）。
        """
        report = self.check(operation.name, facts)
        if report.issues:
            raise TaskError(
                "Postconditions not satisfied",
                details={
                    "stage": "postconditions",
                    "operation": operation.name,
                    "issues": list(report.issues),
                },
            )
        return report
