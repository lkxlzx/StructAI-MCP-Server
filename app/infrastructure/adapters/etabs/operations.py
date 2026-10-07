"""Infrastructure · Adapters · CSI ETABS · Operations —— Operation → 原生调用编排（P128）。

权威来源
--------
- `docs/02` §88 L7602–7612 / `docs/03` §106 L3173–3181 —— `ANALYSIS.STATIC` → `COM RunAnalysis`。
- `docs/07` §6.11 —— Operation → 原生 API 的映射**只能**落在 Adapter 子包的数据里。

落地裁决（只补实现手段，不改任何映射）
------------------------------------
1. **编排是数据、不是分支**：`NATIVE_STEPS` 由 `catalogue.CATALOGUE` **机械推导**
   （一条 catalogue 条目 → 一步原生调用），**不**在代码里写 `if operation == ...`。
2. **`arguments` 为空元组**：本仓库**没有**任何 ETABS 原生参数的权威来源，
   因此该步**不**发出任何参数（`()` = 「无可追溯的原生参数」）。
   编造参数名会直接违反 `docs/07` §16 R76 的口径。
3. **未覆盖的 Operation 明确失败**：`plan_for()` 抛 `OperationNotInCatalogue`
   （`STRUCTAI-3000`，`details.stage = "capability"`）—— **不**回落、**不**猜测。

分层红线：只依赖标准库与同包的 `catalogue.py` / `capabilities.py` / `errors.py`；
**不**发任何请求。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.infrastructure.adapters.etabs.capabilities import capability_for_operation
from app.infrastructure.adapters.etabs.catalogue import CATALOGUE, entry_for

__all__ = [
    "NATIVE_STEPS",
    "NativeStep",
    "native_steps",
    "plan_for",
    "plans_for_tool",
    "tools",
]


@dataclass(frozen=True, slots=True)
class NativeStep:
    """一步原生调用（`docs/02` §88 的一行）。

    Attributes:
        operation: 规范化 Operation 名。
        tool: 该 Operation 所属的 MCP Tool（`docs/07` §5.1）。
        protocol: 协议（`COM`）。
        method: 原生方法名（可追溯的事实）。
        intent: 该步在做什么（`analyze`）；Adapter 据此选择 Transformer。
        arguments: 该步**发出**的参数名（空 = 无可追溯的原生参数，见裁决 2）。
    """

    operation: str
    tool: str
    protocol: str
    method: str
    intent: str
    arguments: tuple[str, ...] = ()


NATIVE_STEPS: Final[dict[str, NativeStep]] = {
    entry.operation: NativeStep(
        operation=entry.operation,
        tool=entry.tool,
        protocol=entry.protocol,
        method=entry.method,
        intent="analyze",
        arguments=(),
    )
    for entry in CATALOGUE.values()
}
"""全部编排（**恰好 1 步**；见裁决 1）。"""


def plan_for(operation: str) -> NativeStep:
    """取该 Operation 的原生编排（`docs/07` §6.11）。

    Raises:
        OperationNotInCatalogue: `STRUCTAI-3000`，该 Operation 不在 catalogue（见裁决 3）。
    """
    entry = entry_for(str(operation), capability=capability_for_operation(operation))
    return NATIVE_STEPS[entry.operation]


def native_steps() -> tuple[NativeStep, ...]:
    """全部原生步骤（按 Operation 名升序；输出确定性）。"""
    return tuple(NATIVE_STEPS[key] for key in sorted(NATIVE_STEPS))


def plans_for_tool(tool: str) -> tuple[NativeStep, ...]:
    """某 Tool 的全部编排（按 Operation 名升序；`docs/07` §5.1 的 Tool 划分）。"""
    return tuple(step for step in native_steps() if step.tool == str(tool))


def tools() -> tuple[str, ...]:
    """本 Adapter 覆盖到的 Tool（升序）。"""
    return tuple(sorted({step.tool for step in NATIVE_STEPS.values()}))
