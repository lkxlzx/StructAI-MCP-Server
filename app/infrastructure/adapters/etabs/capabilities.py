"""Infrastructure · Adapters · CSI ETABS · Capabilities —— 能力映射（`docs/07` §14.2 / §16 R30）。

权威来源
--------
- `docs/07` §14.2 —— 能力取值**不得**含厂商名，且只能来自 P07 落库的 `capabilities`
  （**41** 条；`app.domain.enums.Capability` 是类型化视图）。
- `docs/07` §16 R30 / R38 —— `runtime_capabilities()` 是 `CapabilityResolver.status_of()`
  的接入点；`UNKNOWN ≠ SUPPORTED`，清单**可得**但缺码 → `UNSUPPORTED`。
- `docs/02` §43 / §46 —— 能力 ≠ Operation：一个 Operation 需要**多个**能力码（ALL 语义）。

落地裁决（只补实现手段，不改语义）
--------------------------------
1. **能力映射由 catalogue 推导**：一条能力码只有在「其全部必需 Operation 都在
   catalogue 里」时才算可得 —— 推导**只**读本子包的 `catalogue.py`，
   **不**猜测、**不**写死产品差异。
2. **只声明确实支持的码**：本批 catalogue 只有 `ANALYSIS.STATIC`，故运行时清单
   **恰好** `("ANALYSIS.STATIC",)`（`docs/02` §31：`ANALYSIS.STATIC → ANALYSIS.STATIC`）。
   其余 40 条能力码**不**声明 —— 声明它们就等于声称 ETABS 支持对应的原生操作，
   而本仓库**没有**任何可追溯依据（`docs/07` §16 R76 的同一口径）。
3. **码只经 `Capability` 枚举取值**：本模块**不**写裸字符串能力码，
   从而「不在 41 条词表内」在类型层面即不可能。

分层红线：只依赖标准库、`app.domain` 与同包的 `catalogue.py` / `errors.py`。
"""

from __future__ import annotations

from typing import Final

from app.domain.enums import Capability
from app.infrastructure.adapters.etabs.catalogue import has

__all__ = [
    "CAPABILITY_OPERATIONS",
    "KNOWN_CAPABILITY_CODES",
    "capability_codes",
    "capability_for_operation",
    "unknown_codes",
]

CAPABILITY_OPERATIONS: Final[dict[str, tuple[str, ...]]] = {
    Capability.ANALYSIS_STATIC.value: ("ANALYSIS.STATIC",),
}
"""能力码 → 必需 Operation（**只**含 catalogue 里可追溯的那些；见裁决 1 / 2）。"""

KNOWN_CAPABILITY_CODES: Final[frozenset[str]] = frozenset(code.value for code in Capability)
"""P07 落库的能力词表（41 条；`app.domain.enums.Capability`）。"""


def capability_codes() -> tuple[str, ...]:
    """本 Adapter 在 ETABS 上**确实支持**的能力码（升序；见裁决 2）。

    Returns:
        能力码元组；全部必需 Operation 都在 catalogue 里才算可得。
        ⚠️ 清单**不**以 `verification_status` 过滤：执行门槛由
        `client.guard_verified()` 单独把关（与 MIDAS 侧同一分工）。
    """
    codes = [
        code
        for code, operations in CAPABILITY_OPERATIONS.items()
        if operations and all(has(operation) for operation in operations)
    ]
    return tuple(sorted(codes))


def capability_for_operation(operation: str) -> str | None:
    """反查该 Operation 的能力码（**只**在已声明时返回；见裁决 2）。

    Returns:
        能力码；未声明时 `None` —— 调用方据此**不**在 `details` 里编造能力码。
    """
    target = str(operation)
    for code, operations in sorted(CAPABILITY_OPERATIONS.items()):
        if target in operations:
            return code
    return None


def unknown_codes() -> tuple[str, ...]:
    """词表自检：本映射里出现、但**不在** 41 条落库词表内的能力码（升序）。

    Returns:
        悬空能力码；空元组表示词表一致（`docs/07` §14.2）。
    """
    return tuple(sorted(set(CAPABILITY_OPERATIONS) - KNOWN_CAPABILITY_CODES))
