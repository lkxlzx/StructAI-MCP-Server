"""Application · Execution · Preconditions（`docs/07` §12 P14–P18；`docs/02` §23 / §32）。

权威来源
--------
- `docs/02` §32（`blue` / `source9`）—— 前置 / 后置条件，文件
  `application/execution/preconditions.py`。原文示例：
  `MODEL.NODE.CREATE` 的 Precondition = 「model 可写」；
  `ANALYSIS.STATIC` 的 Precondition = 「model 完整 + software 已连接 + capability 存在」。
- `docs/02` §23（`exec`）—— `ANALYSIS.STATIC` 的前置链：`Model exists → Node count > 0 →
  Element count > 0 → Material assigned → Section assigned → Boundary exists →
  Load exists → Software supports ANALYSIS.STATIC`；并明确「因此 `ANALYSIS.STATIC`
  **不能直接调用 Adapter**」。
- `docs/02` §90（`exec`）—— 职责划分：`EngineeringValidator` 负责
  **`Engineering preconditions`**。
- `docs/07` §9 第 10 步 —— `Preconditions`（**先于** `Effective Permission`（11）/
  `Quota`（12）/ `Confirmation`（13）/ `Idempotency`（14）/ `Lock`（15）/ `Capability`（16））。
- `docs/07` §11 —— 前置条件不满足落 **`STRUCTAI-1200` Engineering Validation Error**
  （`docs/02` §90 把前置条件归入工程校验族；20 码契约**不扩**）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **前置条件是「声明 + 事实驱动」的，不自己读库**：`docs/02` §32 给的是**声明式**前置
   条件（「model 可写」「software 已连接」「capability 存在」），不是可直接执行的 SQL。
   本模块把它们表达为 `Precondition(name, description, check)` 的**目录**，
   由 `PreconditionEvaluator` 对调用方提供的 `ExecutionFacts` 求值。事实只来自
   **已完成**的流水线步骤（`docs/07` §9）；本模块不持有仓储、不发查询 —— 与
   `docs/02` §70「Validator 只操作已解析且已授权的资源」同一口径。
2. **三态结果，避免「未算就先断言」**：某个事实没提供时，检查返回 `None` = **未验证**
   （既不是通过，也不是失败）。这是必要的：`Capability`（第 16 步）在
   `Preconditions`（第 10 步）**之后**执行，因此前置条件里的「capability 存在」
   在事实尚未提供时**不得**被判为失败（会与 `docs/07` §9 的冻结顺序冲突），
   也**不得**被判为通过。`PreconditionReport.unverified` 如实报告这些条目。
3. **检查签名只取 `required_capabilities`**：检查需要知道的 Operation 信息**只有**
   「这个 Operation 声明了哪些能力」（`docs/02` §24 的 `OperationDefinition`
   第 7 个字段）。因此检查签名为
   `(required_capabilities, facts) -> list[str] | None`，而不是把整个
   `OperationDefinition` 传进来 —— 依赖面收窄到真正需要的那一项。
4. **失败错误码 = `STRUCTAI-1200`**：20 码契约没有「前置条件」专用码，而
   `docs/02` §90 把前置条件归入工程校验族，故复用既有 `EngineeringValidationError`，
   用 `details.stage = "preconditions"` 区分阶段。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库、`app.domain` 与同层的 `app.application.resource`
（`ResolvedResource` 的类型化引用）：**不**引用 ORM / Web 框架 / MCP SDK / httpx，
**不**依赖 `app.infrastructure`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final

from app.application.resource.resolver import ResolvedResource
from app.domain.enums import ResourceType, SoftwareConnectionState
from app.domain.errors import EngineeringValidationError
from app.domain.protocols import OperationDefinition

__all__ = [
    "MODEL_COMPLETENESS_KEYS",
    "PRECONDITIONS",
    "PRECONDITION_OPERATIONS",
    "ExecutionFacts",
    "Precondition",
    "PreconditionCheck",
    "PreconditionEvaluator",
    "PreconditionReport",
]

MODEL_COMPLETENESS_KEYS: Final[tuple[str, ...]] = (
    "nodes",
    "elements",
    "materials",
    "sections",
    "boundary",
    "load",
)
"""「model 完整」所需的模型侧计数键（`docs/02` §23 的 8 步前置链去掉首尾两步）。

对应：`Node count > 0` → `nodes`；`Element count > 0` → `elements`；
`Material assigned` → `materials`；`Section assigned` → `sections`；
`Boundary exists` → `boundary`；`Load exists` → `load`。
（`Model exists` 由 `resolved_resource` 承载；`Software supports ANALYSIS.STATIC`
由 `supported_capabilities` 承载。）
"""


@dataclass(frozen=True, slots=True)
class ExecutionFacts:
    """前置 / 后置条件求值所需的事实（全部来自已完成的流水线步骤）。

    ⚠️ 每个字段都**可为空**：`None` / 空表示「该事实尚未产生」，对应检查会如实报告为
    **未验证**（见模块裁决 2），而不是通过或失败。

    Attributes:
        resolved_resource: 第 7 步 `Resolve Resource` 的结果（`docs/02` §73）。
        software_status: 软件实例连接状态（`docs/02` §19 的
            `SoftwareConnectionState` 取值）；`None` 表示未解析。
        supported_capabilities: 已判定为 `SUPPORTED` 的能力码集合；
            `None` 表示**尚未判定**（第 16 步 `Capability` 还没跑）。
        model_state: 模型侧计数（键见 `MODEL_COMPLETENESS_KEYS`）；空映射表示未提供。
        task_status: 任务状态（`app.domain.enums.TaskStatus` 取值）；
            `None` 表示无任务上下文。
        result_available: 结果是否可查询；`None` 表示未提供。
    """

    resolved_resource: ResolvedResource | None = None
    software_status: str | None = None
    supported_capabilities: frozenset[str] | None = None
    model_state: Mapping[str, Any] = field(default_factory=dict)
    task_status: str | None = None
    result_available: bool | None = None


PreconditionCheck = Callable[[tuple[str, ...], ExecutionFacts], "list[str] | None"]
"""一条前置条件检查：`(required_capabilities, facts) -> None | [未满足原因]`。

- `[]` —— 满足；
- `[原因, ...]` —— 不满足（`require()` 据此拒绝）；
- `None` —— **事实不足，未验证**（见模块裁决 2）。
"""


@dataclass(frozen=True, slots=True)
class Precondition:
    """一条声明式前置条件（`docs/02` §32）。

    Attributes:
        name: 机器可读的名字（用于报告与断言）。
        description: 人可读描述（照抄 `docs/02` §32 的措辞）。
        check: 求值函数（纯函数；见模块裁决 1）。
    """

    name: str
    description: str
    check: PreconditionCheck


@dataclass(frozen=True, slots=True)
class PreconditionReport:
    """一次前置条件求值的结果（`docs/02` §32）。

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


# ===== 检查实现（`docs/02` §23 / §32）=====


def _model_writable(required: tuple[str, ...], facts: ExecutionFacts) -> list[str] | None:
    """「model 可写」（`docs/02` §32 的 `MODEL.NODE.CREATE` 前置条件）。

    判定：必须已解析出**数据侧**资源（`MODEL` / `DOCUMENT` / `PROJECT`）——
    只解析出软件实例时，写操作没有落点。
    """
    del required
    resolved = facts.resolved_resource
    if resolved is None:
        return None
    if resolved.resource_type == ResourceType.SOFTWARE_INSTANCE.value:
        return ["model is not writable: no data resource (model/document/project) resolved"]
    return []


def _software_connected(required: tuple[str, ...], facts: ExecutionFacts) -> list[str] | None:
    """「software 已连接」（`docs/02` §32 / §19）。"""
    del required
    status = facts.software_status
    if status is None:
        return None
    if status != SoftwareConnectionState.CONNECTED.value:
        return [f"software instance is not connected (status={status})"]
    return []


def _capability_supported(required: tuple[str, ...], facts: ExecutionFacts) -> list[str] | None:
    """「capability 存在」（`docs/02` §32 / §23 末步）。

    ⚠️ 事实未提供时返回 `None`（未验证）—— 第 16 步 `Capability` 在第 10 步
    `Preconditions` **之后**执行（`docs/07` §9），此时不得断言（见模块裁决 2）。
    """
    supported = facts.supported_capabilities
    if supported is None:
        return None
    missing = sorted(set(required) - set(supported))
    if missing:
        return [f"required capability not supported: {', '.join(missing)}"]
    return []


def _model_complete(required: tuple[str, ...], facts: ExecutionFacts) -> list[str] | None:
    """「model 完整」（`docs/02` §23 的 8 步前置链）。"""
    del required
    state = facts.model_state
    if not state:
        return None
    missing = [key for key in MODEL_COMPLETENESS_KEYS if not _is_present(state.get(key))]
    if missing:
        return [f"model is incomplete: missing or empty {', '.join(missing)}"]
    return []


def _is_present(value: Any) -> bool:
    """计数 / 布尔事实是否「存在」：数值 > 0 或布尔 `True`。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    return bool(value)


#: 声明式前置条件目录（`docs/02` §32；`docs/02` §23 的前置链）。
PRECONDITIONS: Mapping[str, tuple[Precondition, ...]] = MappingProxyType(
    {
        "MODEL.NODE.CREATE": (Precondition("model_writable", "model 可写", _model_writable),),
        "MODEL.NODE.UPDATE": (Precondition("model_writable", "model 可写", _model_writable),),
        "MODEL.ELEMENT.CREATE": (Precondition("model_writable", "model 可写", _model_writable),),
        "MODEL.ELEMENT.UPDATE": (Precondition("model_writable", "model 可写", _model_writable),),
        "MODEL.MATERIAL.ASSIGN": (Precondition("model_writable", "model 可写", _model_writable),),
        "MODEL.SECTION.ASSIGN": (Precondition("model_writable", "model 可写", _model_writable),),
        "MODEL.BOUNDARY.ASSIGN": (Precondition("model_writable", "model 可写", _model_writable),),
        "MODEL.LOAD.ASSIGN": (Precondition("model_writable", "model 可写", _model_writable),),
        "BUILD.COLUMN": (
            Precondition("model_writable", "model 可写", _model_writable),
            Precondition("software_connected", "software 已连接", _software_connected),
        ),
        "ANALYSIS.STATIC": (
            Precondition("model_complete", "model 完整", _model_complete),
            Precondition("software_connected", "software 已连接", _software_connected),
            Precondition("capability_supported", "capability 存在", _capability_supported),
        ),
        "DESIGN.STEEL": (
            Precondition("model_complete", "model 完整", _model_complete),
            Precondition("software_connected", "software 已连接", _software_connected),
            Precondition("capability_supported", "capability 存在", _capability_supported),
        ),
    }
)
"""Operation → 前置条件（`docs/02` §32 / §23）。

⚠️ `MODEL.NODE.CREATE` / `ANALYSIS.STATIC` 两条是 §32 的**原文示例**；
其余同族 Operation 是**同构补齐**（同一前置条件 —— §32 的声明粒度即按族）。
未登记的 Operation **没有**前置条件声明（不隐式兜底）。
"""

PRECONDITION_OPERATIONS: Final[tuple[str, ...]] = tuple(sorted(PRECONDITIONS))
"""已声明前置条件的 Operation 名（升序元组；供装配期核对与验收断言）。"""


class PreconditionEvaluator:
    """前置条件求值器（`docs/02` §23 / §32；`docs/07` §9 第 10 步）。

    ⚠️ 本类**不**读库、**不**发请求、**不**改状态：只对调用方提供的 `ExecutionFacts`
    求值（见模块裁决 1）。事实由**已完成**的流水线步骤提供。
    """

    def __init__(
        self,
        *,
        preconditions: Mapping[str, Sequence[Precondition]] | None = None,
    ) -> None:
        """绑定前置条件目录。

        Args:
            preconditions: Operation → 前置条件；缺省用 `PRECONDITIONS`（`docs/02` §32）。
        """
        source = PRECONDITIONS if preconditions is None else preconditions
        self._preconditions: Mapping[str, tuple[Precondition, ...]] = MappingProxyType(
            {name: tuple(items) for name, items in source.items()}
        )

    @property
    def operations(self) -> tuple[str, ...]:
        """已声明前置条件的 Operation 名（升序）。"""
        return tuple(sorted(self._preconditions))

    def for_operation(self, operation: str) -> tuple[Precondition, ...]:
        """该 Operation 的前置条件（未声明时为空元组，不隐式兜底）。"""
        return self._preconditions.get(operation, ())

    def check(
        self,
        operation: str,
        facts: ExecutionFacts,
        *,
        required_capabilities: tuple[str, ...] = (),
    ) -> PreconditionReport:
        """求值（`docs/02` §32）。

        Args:
            operation: Operation 名。
            facts: 流水线已产生的事实（`ExecutionFacts`）。
            required_capabilities: 该 Operation 声明的能力（`docs/02` §24 第 7 个字段）；
                缺省空元组表示「调用方未提供」—— 此时能力类检查按未验证处理。

        Returns:
            `PreconditionReport`：已满足 / 未验证 / 不满足三类条目。
        """
        satisfied: list[str] = []
        unverified: list[str] = []
        issues: list[str] = []
        for precondition in self.for_operation(operation):
            outcome = precondition.check(required_capabilities, facts)
            if outcome is None:
                unverified.append(precondition.name)
            elif outcome:
                issues.extend(f"{precondition.name}: {reason}" for reason in outcome)
            else:
                satisfied.append(precondition.name)
        return PreconditionReport(
            operation=operation,
            satisfied=tuple(satisfied),
            unverified=tuple(unverified),
            issues=tuple(issues),
        )

    async def require(
        self,
        operation: OperationDefinition,
        facts: ExecutionFacts,
    ) -> PreconditionReport:
        """要求前置条件满足（`docs/07` §9 第 10 步）。

        Args:
            operation: 操作定义（`docs/02` §24）。
            facts: 流水线已产生的事实。

        Returns:
            `PreconditionReport`（未验证项如实返回，调用方可据此记录诊断）。

        Raises:
            EngineeringValidationError: `STRUCTAI-1200`（见模块裁决 4），
                `details = {stage: "preconditions", operation, issues}`。
                仅在存在**不满足**项时抛出；未验证项不阻断（见模块裁决 2）。
        """
        report = self.check(
            operation.name,
            facts,
            required_capabilities=tuple(operation.required_capabilities),
        )
        if report.issues:
            raise EngineeringValidationError(
                "Preconditions not satisfied",
                details={
                    "stage": "preconditions",
                    "operation": operation.name,
                    "issues": list(report.issues),
                },
            )
        return report
