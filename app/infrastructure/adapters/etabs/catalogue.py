"""Infrastructure · Adapters · CSI ETABS · Catalogue —— **可追溯**的 Operation 数据（P128）。

权威来源（本仓库内**唯一**可追溯的 ETABS 原生事实）
--------------------------------------------------
- `docs/02` §88 L7602–7612 —— `ANALYSIS.STATIC` → ETABS `COM RunAnalysis`。
- `docs/03` §106 L3173–3181 —— 同一映射（`Adapter → COM → RunAnalysis`）。
- `docs/01` §20 L907–918 —— 事实块：`software=CSI` / `product=ETABS` / `version=22` /
  `protocol=COM` / `method=RunAnalysis`。
- `docs/02` §58 L26168–26183 —— `ETABS 22 → COM RunAnalysis`。

落地裁决（只补实现手段，不改任何取值）
------------------------------------
1. **catalogue 恰好 1 条**：本仓库**没有**任何其他 ETABS 原生方法名 / 端点 / 参数的
   权威来源，因此**不**臆造 —— 除 `ANALYSIS.STATIC` 外的条目数为 **0**，
   并把该事实钉成**可执行断言**（`tests/test_etabs_p127_p133.py` 的 L1 层）。
2. **每条目必须带出处锚点**：`provenance` 为空 → `CatalogueNotTraceable`（`3000`，
   装配期自检 `verify_traceable()`）。这样「数据可追溯」不是注释里的承诺，
   而是**可执行**的判定。
3. **`verification_status` 如实写作 `PARTIAL`**：`VERIFIED` 的判定是 **7 项 AND**
   （`docs/07` §16 R1 / R78），含「至少一次真实 Contract Test 通过」；本批**没有**
   ETABS 实例 / 凭据，故**不**升级任何状态（`docs/07` §16 R78 的同一口径）。
4. **其余 68 个 Operation 一律不入 catalogue**：能力判定阶段明确失败为
   `STRUCTAI-3000`（`details.stage = "capability"`，照 R63 的口径），
   **不**静默成功、**不**回落、**不**用别的原生调用顶替。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与同包的 `errors.py`；**不**引用 SQLAlchemy / FastAPI / MCP SDK /
httpx，**不**依赖 `app.interfaces` / `app.application`，也**不**发任何请求。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from app.infrastructure.adapters.etabs.errors import CatalogueNotTraceable, OperationNotInCatalogue

__all__ = [
    "ANALYSIS_STATIC_ENTRY",
    "CATALOGUE",
    "DEPRECATED",
    "PARTIAL",
    "PROVENANCE_ANCHORS",
    "UNVERIFIED",
    "VERIFIED",
    "CatalogueEntry",
    "catalogue_size",
    "entry_for",
    "has",
    "operations",
    "partial_operations",
    "verify_traceable",
]

VERIFIED: Final[str] = "VERIFIED"
UNVERIFIED: Final[str] = "UNVERIFIED"
PARTIAL: Final[str] = "PARTIAL"
DEPRECATED: Final[str] = "DEPRECATED"
"""`docs/04` §8 的四个状态取值（逐字照抄；见裁决 3）。"""

PROVENANCE_ANCHORS: Final[tuple[str, ...]] = (
    "docs/02 §88 L7602-7612",
    "docs/03 §106 L3173-3181",
    "docs/01 §20 L907-918",
    "docs/02 §58 L26168-26183",
)
"""本 catalogue 允许引用的出处锚点（**逐字**取自仓库内的既有事实；见裁决 1 / 2）。"""


@dataclass(frozen=True, slots=True)
class CatalogueEntry:
    """一条**可追溯**的 Operation → 原生调用映射（`docs/02` §88 / `docs/03` §106）。

    Attributes:
        operation: 规范化 Operation 名（Core 的标识，**不是**原生方法名）。
        tool: 该 Operation 所属的 MCP Tool（`docs/07` §5.1）。
        protocol: 协议（`COM`；见 `manifest.py` 裁决 3）。
        method: 原生方法名（**唯一**可追溯的事实：`RunAnalysis`）。
        verification_status: 验证状态（本批 = `PARTIAL`，见裁决 3）。
        provenance: 出处锚点（非空；见裁决 2）。
        note: 非敏感诊断说明。
    """

    operation: str
    tool: str
    protocol: str
    method: str
    verification_status: str
    provenance: tuple[str, ...]
    note: str = ""


ANALYSIS_STATIC_ENTRY: Final[CatalogueEntry] = CatalogueEntry(
    operation="ANALYSIS.STATIC",
    tool="engineering_analysis",
    protocol="COM",
    method="RunAnalysis",
    verification_status=PARTIAL,
    provenance=PROVENANCE_ANCHORS,
    note="本仓库内唯一可追溯的 ETABS 原生事实；其余 Operation 无权威数据源（PARTIAL）",
)
"""`docs/02` §88 L7602–7612 / `docs/03` §106 L3173–3181（逐条照抄）。"""

CATALOGUE: Final[dict[str, CatalogueEntry]] = {
    ANALYSIS_STATIC_ENTRY.operation: ANALYSIS_STATIC_ENTRY,
}
"""全部可追溯条目（**恰好 1 条**；见裁决 1）。"""


def catalogue_size() -> int:
    """catalogue 条目数（**必须**为 1；见裁决 1）。"""
    return len(CATALOGUE)


def operations() -> tuple[str, ...]:
    """全部可追溯的 Operation 名（升序）。"""
    return tuple(sorted(CATALOGUE))


def has(operation: str) -> bool:
    """该 Operation 是否可追溯（**不**做任何猜测）。"""
    return str(operation) in CATALOGUE


def partial_operations() -> tuple[str, ...]:
    """`verification_status == PARTIAL` 的 Operation（升序；见裁决 3）。"""
    return tuple(
        sorted(key for key, entry in CATALOGUE.items() if entry.verification_status == PARTIAL)
    )


def entry_for(operation: str, *, capability: str | None = None) -> CatalogueEntry:
    """取该 Operation 的可追溯条目（`docs/02` §88）。

    Args:
        operation: 规范化 Operation 名。
        capability: 诊断用的能力码（**只**来自落库的 41 条词表；未知时留 `None`，
            此时 `details` 里**不**编造能力码）。

    Returns:
        可追溯条目。

    Raises:
        OperationNotInCatalogue: `STRUCTAI-3000`，该 Operation **不在** catalogue
            （`details.stage = "capability"`；见裁决 4）。
    """
    entry = CATALOGUE.get(str(operation))
    if entry is None:
        raise OperationNotInCatalogue(str(operation), capability=capability)
    return entry


def verify_traceable() -> tuple[str, ...]:
    """装配期自检：每条目都必须带**已登记**的出处锚点（见裁决 2）。

    Returns:
        问题清单（升序）；空元组表示全部可追溯。

    Raises:
        CatalogueNotTraceable: `STRUCTAI-3000`，任一条目的锚点为空 / 不在
            `PROVENANCE_ANCHORS` 内（**不**静默放行）。
    """
    problems: list[str] = []
    for operation in sorted(CATALOGUE):
        entry = CATALOGUE[operation]
        if not entry.provenance:
            problems.append(f"{operation}:no-provenance")
            continue
        unknown = [anchor for anchor in entry.provenance if anchor not in PROVENANCE_ANCHORS]
        if unknown:
            problems.append(f"{operation}:unknown-anchor:{unknown[0]}")
    if problems:
        raise CatalogueNotTraceable(problems[0].split(":")[0], problems[0])
    return ()


def as_dict(entry: CatalogueEntry) -> dict[str, Any]:
    """条目的诊断视图（**不含**凭据 / 请求体；供日志与验收证据）。"""
    return {
        "operation": entry.operation,
        "tool": entry.tool,
        "protocol": entry.protocol,
        "method": entry.method,
        "verification_status": entry.verification_status,
        "provenance": list(entry.provenance),
    }
