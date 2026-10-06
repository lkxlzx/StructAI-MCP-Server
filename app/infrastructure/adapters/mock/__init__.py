"""Infrastructure · Adapters · Mock（`docs/07` §3.3 冻结结构；`docs/02` §27–§51 / §117）。

| 文件 | 内容 | 规范 |
| --- | --- | --- |
| `adapter.py` | `MockAdapter`（实现 ABC 的 8 个方法 + 分派表） | `docs/02` §29–§48 |
| `model_store.py` | `MockModelStore`（六类实体 + 版本 + 自动 ID） | `docs/02` §27 / §28 / §35 |
| `analysis.py` | Mock 静力分析 / 结果 / 设计（确定性，非工程级） | `docs/02` §41–§47 |

⚠️ `MockAdapter` **不允许**成为生产计算器（`docs/02` §65）：只用于 unit / integration /
e2e / demo / development。
"""

from __future__ import annotations

from app.infrastructure.adapters.mock.adapter import (
    MOCK_CAPABILITIES,
    MOCK_NAME,
    MOCK_PRODUCT,
    MOCK_PROTOCOL,
    MOCK_SUPPORTED_OPERATIONS,
    MOCK_SUPPORTED_VERSIONS,
    MOCK_VENDOR,
    MOCK_VERSION,
    MockAdapter,
)
from app.infrastructure.adapters.mock.analysis import (
    DISPLACEMENT_FALLBACK_SCALE,
    ENGINEERING_GRADE,
    MOCK_ENGINE,
    NOT_ENGINEERING_GRADE_NOTE,
    STEEL_STATUS_PASS,
    STEEL_UTILIZATION,
    axial_displacement,
    element_force,
    element_stress,
    mark,
    node_displacement,
    node_reaction,
    static_analysis,
    steel_design,
)
from app.infrastructure.adapters.mock.model_store import (
    DEFAULT_MATERIAL,
    DEFAULT_SECTION,
    MOCK_MATERIALS,
    MOCK_SECTIONS,
    MockBoundary,
    MockElement,
    MockLoad,
    MockMaterial,
    MockModelStore,
    MockNode,
    MockSection,
)

__all__ = [
    "DEFAULT_MATERIAL",
    "DEFAULT_SECTION",
    "DISPLACEMENT_FALLBACK_SCALE",
    "ENGINEERING_GRADE",
    "MOCK_CAPABILITIES",
    "MOCK_ENGINE",
    "MOCK_MATERIALS",
    "MOCK_NAME",
    "MOCK_PRODUCT",
    "MOCK_PROTOCOL",
    "MOCK_SECTIONS",
    "MOCK_SUPPORTED_OPERATIONS",
    "MOCK_SUPPORTED_VERSIONS",
    "MOCK_VENDOR",
    "MOCK_VERSION",
    "NOT_ENGINEERING_GRADE_NOTE",
    "STEEL_STATUS_PASS",
    "STEEL_UTILIZATION",
    "MockAdapter",
    "MockBoundary",
    "MockElement",
    "MockLoad",
    "MockMaterial",
    "MockModelStore",
    "MockNode",
    "MockSection",
    "axial_displacement",
    "element_force",
    "element_stress",
    "mark",
    "node_displacement",
    "node_reaction",
    "static_analysis",
    "steel_design",
]
