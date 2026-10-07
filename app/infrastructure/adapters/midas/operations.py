"""Infrastructure · Adapters · MIDAS · Operations —— Operation → endpoint 编排（`docs/07` §6）。

权威来源
--------
- `docs/07` §6（**全章** Operation → MIDAS API 映射）—— 逐表照抄：`engineering_doc`(6) /
  `engineering_model_query`(8) / `engineering_model_assign`(8) / `engineering_model_delete`(7) /
  `engineering_model_build`(14) / `engineering_view`(7) / `engineering_result`(6) /
  `engineering_design`(6) / `engineering_analysis`(7) = **69**。
- `docs/07` §6.4 —— 🔴 NX 系 `DELETE` 必须把 key 写在 URL 路径（`DELETE {uri}/{id}`）；
  `DELETE {uri}` 不带路径 key 会**删除全表**。
- `docs/07` §6.5 / §16 R2 —— `BUILD.*` 与 `MODEL.COPY/MOVE/MIRROR/PATTERN/GENERATE_GRID`
  **无直接 API**，必须由 Adapter **多步组合**（**不**臆造单端点）。
- `docs/07` §6.8 —— `DESIGN.FOUNDATION` / `DESIGN.OPTIMIZE` **无** MIDAS API
  （自研引擎）；`DESIGN.CODE_CHECK` 按「材料 × 构件类型」路由。
- `docs/07` §6.11 —— 映射落地位置 = 本模块；`verification_status != VERIFIED` 时抛
  `RegistryMappingNotVerified`（由 `client.py` / `adapter.py` 执行）。

落地裁决（只补实现手段，不改任何映射）
------------------------------------
1. **映射是数据、不是分支**：全部 69 条写在本模块的 `OPERATION_PLANS` 里
   （`docs/04` §21：**不**在 Transformer 里写 `if operation == ...`），
   执行侧只按 `plan_for()` 的结果逐步调用。
2. **`intent` 表达「这一步在做什么」**：`read` / `write_*` / `delete` / `analyze` /
   `result` / `design`。Adapter 据此选择 Transformer 与请求包装，**不**从端点名反推。
3. **无原生映射的两条 Operation 明确失败**：`DESIGN.FOUNDATION` / `DESIGN.OPTIMIZE`
   → `MidasCapabilityError`（`3000`，`details.reason = "operation_has_no_native_mapping"`）；
   **不**回落、**不**用别的端点顶替（`docs/07` §6.8）。
4. **未登记 Operation 明确失败**：`plan_for()` 抛 `operation_not_mapped`。
5. **`DESIGN.CODE_CHECK` 是路由表**：按 `parameters.material`（`steel` / `concrete` /
   `src`）与 `parameters.member_type` 选择「材料 × 构件」对应的分析端点 + 结果端点；
   路由不到 → `code_check_route_not_mapped`（**不**猜测）。
6. **`ANALYSIS.TIME_HISTORY` 只用数据里存在的端点**：`docs/07` §6.9 列的 `DB.THOO`
   **不在** `registry/manifest.json`（数据现状），故本批编排 `DOC.ANAL` + `DB.THGC` +
   `DB.THIS`，并把该差异记入 `docs/07` §16（**不**臆造端点）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与同包的 `errors.py`；**不**引用 SQLAlchemy / FastAPI / MCP SDK /
httpx，**不**依赖 `app.interfaces`，也**不**发任何请求。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from app.infrastructure.adapters.midas.errors import MidasCapabilityError, MidasValidationError

__all__ = [
    "LOAD_STEP_BY_TYPE",
    "NO_NATIVE_MAPPING",
    "OPERATION_PLANS",
    "EndpointStep",
    "OperationPlan",
    "plan_for",
    "plans_for_tool",
    "select_steps",
]

NO_NATIVE_MAPPING: Final[tuple[str, ...]] = ("DESIGN.FOUNDATION", "DESIGN.OPTIMIZE")
"""`docs/07` §6.8：**无** MIDAS API 的 Operation（自研引擎；见裁决 3）。"""

LOAD_STEP_BY_TYPE: Final[dict[str, str]] = {
    "NODE_FORCE": "DB.CNLD",
    "NODE_MOMENT": "DB.CNLD",
    "BEAM_FORCE": "DB.BMLD",
    "BEAM_MOMENT": "DB.BMLD",
    "PRESSURE": "DB.PRES",
    "SELF_WEIGHT": "DB.BODF",
    "FLOOR_LOAD": "DB.FBLD",
}
"""`docs/04` §32 的荷载类型 → `docs/07` §6.3 的端点（`TEMPERATURE` **无**原生映射）。"""


@dataclass(frozen=True, slots=True)
class EndpointStep:
    """一步编排（`docs/07` §6 的一行）。"""

    key: str
    method: str
    intent: str
    transformer: str | None = None
    note: str = ""
    alternatives: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OperationPlan:
    """一个 Operation 的完整编排（`docs/07` §6 的一个小节）。"""

    operation: str
    tool: str
    composite: bool = False
    steps: tuple[EndpointStep, ...] = ()
    routes: Mapping[str, tuple[EndpointStep, ...]] = field(default_factory=dict)
    note: str = ""


def _read(
    key: str, transformer: str | None = None, *, method: str = "GET", note: str = ""
) -> EndpointStep:
    """读步骤。"""
    return EndpointStep(key=key, method=method, intent="read", transformer=transformer, note=note)


def _write(key: str, intent: str, transformer: str | None, *, method: str = "POST") -> EndpointStep:
    """写步骤（intent 见模块裁决 2）。"""
    return EndpointStep(key=key, method=method, intent=intent, transformer=transformer)


def _delete(key: str, intent: str) -> EndpointStep:
    """删除步骤（`docs/07` §6.4：NX 系必须带路径 key）。"""
    return EndpointStep(key=key, method="DELETE", intent=intent, note="delete_with_path_key")


def _steps(*items: EndpointStep) -> tuple[EndpointStep, ...]:
    """把步骤列表收成元组（保持声明顺序 = 执行顺序）。"""
    return tuple(items)


# ===== §6.1 engineering_doc（6）=====

_DOC: Final[dict[str, OperationPlan]] = {
    "NEW": OperationPlan(
        "NEW", "engineering_doc", steps=_steps(_write("DOC.NEW", "write_doc", None))
    ),
    "OPEN": OperationPlan(
        "OPEN", "engineering_doc", steps=_steps(_write("DOC.OPEN", "write_doc", None))
    ),
    "SAVE": OperationPlan(
        "SAVE", "engineering_doc", steps=_steps(_write("DOC.SAVE", "write_doc", None))
    ),
    "SAVE_AS": OperationPlan(
        "SAVE_AS", "engineering_doc", steps=_steps(_write("DOC.SAVEAS", "write_doc", None))
    ),
    "CLOSE": OperationPlan(
        "CLOSE", "engineering_doc", steps=_steps(_write("DOC.CLOSE", "write_doc", None))
    ),
    "INFO": OperationPlan(
        "INFO",
        "engineering_doc",
        steps=_steps(_read("OPE.PROJECTSTATUS")),
        note="docs/07 §6.1：无 /doc/INFO，用项目状态代替",
    ),
}

# ===== §6.2 engineering_model_query（8）=====

_QUERY: Final[dict[str, OperationPlan]] = {
    "MODEL.QUERY": OperationPlan(
        "MODEL.QUERY", "engineering_model_query", steps=_steps(_read("OPE.PROJECTSTATUS"))
    ),
    "MODEL.NODE.QUERY": OperationPlan(
        "MODEL.NODE.QUERY",
        "engineering_model_query",
        steps=_steps(_read("DB.NODE", "midas.node.v1")),
    ),
    "MODEL.ELEMENT.QUERY": OperationPlan(
        "MODEL.ELEMENT.QUERY",
        "engineering_model_query",
        steps=_steps(_read("DB.ELEM", "midas.elem.v1")),
    ),
    "MODEL.MATERIAL.QUERY": OperationPlan(
        "MODEL.MATERIAL.QUERY",
        "engineering_model_query",
        steps=_steps(_read("DB.MATL", "midas.matl.v1")),
    ),
    "MODEL.SECTION.QUERY": OperationPlan(
        "MODEL.SECTION.QUERY",
        "engineering_model_query",
        steps=_steps(_read("DB.SECT", "midas.sect.v1")),
    ),
    "MODEL.BOUNDARY.QUERY": OperationPlan(
        "MODEL.BOUNDARY.QUERY",
        "engineering_model_query",
        steps=_steps(_read("DB.CONS", "midas.cons.v1")),
    ),
    "MODEL.LOAD.QUERY": OperationPlan(
        "MODEL.LOAD.QUERY",
        "engineering_model_query",
        steps=_steps(
            _read("DB.STLD", "midas.stld.v1"),
            _read("DB.BMLD", "midas.bmld.v1"),
            _read("DB.BODF", "midas.bodf.v1"),
            _read("DB.PRES", "midas.pres.v1"),
        ),
        note="docs/07 §6.2：多端点",
    ),
    "MODEL.GROUP.QUERY": OperationPlan(
        "MODEL.GROUP.QUERY", "engineering_model_query", steps=_steps(_read("DB.GRUP"))
    ),
}

# ===== §6.3 engineering_model_assign（8）=====

_ASSIGN: Final[dict[str, OperationPlan]] = {
    "MODEL.NODE.CREATE": OperationPlan(
        "MODEL.NODE.CREATE",
        "engineering_model_assign",
        steps=_steps(_write("DB.NODE", "write_node", "midas.node.v1")),
    ),
    "MODEL.NODE.UPDATE": OperationPlan(
        "MODEL.NODE.UPDATE",
        "engineering_model_assign",
        steps=_steps(_write("DB.NODE", "write_node", "midas.node.v1", method="PUT")),
    ),
    "MODEL.ELEMENT.CREATE": OperationPlan(
        "MODEL.ELEMENT.CREATE",
        "engineering_model_assign",
        steps=_steps(_write("DB.ELEM", "write_element", "midas.elem.v1")),
    ),
    "MODEL.ELEMENT.UPDATE": OperationPlan(
        "MODEL.ELEMENT.UPDATE",
        "engineering_model_assign",
        steps=_steps(_write("DB.ELEM", "write_element", "midas.elem.v1", method="PUT")),
    ),
    "MODEL.MATERIAL.ASSIGN": OperationPlan(
        "MODEL.MATERIAL.ASSIGN",
        "engineering_model_assign",
        steps=_steps(_write("DB.MATL", "write_material", "midas.matl.v1")),
    ),
    "MODEL.SECTION.ASSIGN": OperationPlan(
        "MODEL.SECTION.ASSIGN",
        "engineering_model_assign",
        steps=_steps(_write("DB.SECT", "write_section", "midas.sect.v1")),
    ),
    "MODEL.BOUNDARY.ASSIGN": OperationPlan(
        "MODEL.BOUNDARY.ASSIGN",
        "engineering_model_assign",
        steps=_steps(_write("DB.CONS", "write_boundary", "midas.cons.v1")),
    ),
    "MODEL.LOAD.ASSIGN": OperationPlan(
        "MODEL.LOAD.ASSIGN",
        "engineering_model_assign",
        steps=_steps(
            _write("DB.STLD", "write_load_case", "midas.stld.v1"),
            _write("DB.BMLD", "write_load", "midas.load.v1"),
            _write("DB.BODF", "write_load", "midas.load.v1"),
            _write("DB.PRES", "write_load", "midas.load.v1"),
            _write("DB.CNLD", "write_load", "midas.load.v1"),
            _write("DB.FBLD", "write_load", "midas.load.v1"),
        ),
        note="docs/07 §6.3：按荷载类型分派（Adapter 只执行该类型对应的那一步）",
    ),
}

# ===== §6.4 engineering_model_delete（7）=====

_DELETE: Final[dict[str, OperationPlan]] = {
    "MODEL.NODE.DELETE": OperationPlan(
        "MODEL.NODE.DELETE",
        "engineering_model_delete",
        steps=_steps(_delete("DB.NODE", "delete_node")),
    ),
    "MODEL.ELEMENT.DELETE": OperationPlan(
        "MODEL.ELEMENT.DELETE",
        "engineering_model_delete",
        steps=_steps(_delete("DB.ELEM", "delete_element")),
    ),
    "MODEL.LOAD.DELETE": OperationPlan(
        "MODEL.LOAD.DELETE",
        "engineering_model_delete",
        steps=_steps(_delete("DB.STLD", "delete_load"), _delete("DB.BMLD", "delete_load")),
    ),
    "MODEL.BOUNDARY.DELETE": OperationPlan(
        "MODEL.BOUNDARY.DELETE",
        "engineering_model_delete",
        steps=_steps(_delete("DB.CONS", "delete_boundary")),
    ),
    "MODEL.GROUP.DELETE": OperationPlan(
        "MODEL.GROUP.DELETE",
        "engineering_model_delete",
        steps=_steps(_delete("DB.GRUP", "delete_group")),
    ),
    "MODEL.MATERIAL.DELETE": OperationPlan(
        "MODEL.MATERIAL.DELETE",
        "engineering_model_delete",
        steps=_steps(_delete("DB.MATL", "delete_material")),
    ),
    "MODEL.SECTION.DELETE": OperationPlan(
        "MODEL.SECTION.DELETE",
        "engineering_model_delete",
        steps=_steps(_delete("DB.SECT", "delete_section")),
    ),
}

# ===== §6.5 engineering_model_build（14；组合编排）=====

_NODE = _write("DB.NODE", "write_node", "midas.node.v1")
_ELEM = _write("DB.ELEM", "write_element", "midas.elem.v1")
_MATL = _write("DB.MATL", "write_material", "midas.matl.v1")
_SECT = _write("DB.SECT", "write_section", "midas.sect.v1")
_CONS = _write("DB.CONS", "write_boundary", "midas.cons.v1")

_BUILD: Final[dict[str, OperationPlan]] = {
    "BUILD.NODE_GRID": OperationPlan(
        "BUILD.NODE_GRID",
        "engineering_model_build",
        composite=True,
        steps=_steps(_NODE),
        note="docs/07 §6.5：无专用 /db/GRID 端点，按网格坐标批量建节点",
    ),
    "BUILD.BEAM": OperationPlan(
        "BUILD.BEAM",
        "engineering_model_build",
        composite=True,
        steps=_steps(_NODE, _ELEM, _MATL, _SECT),
    ),
    "BUILD.COLUMN": OperationPlan(
        "BUILD.COLUMN",
        "engineering_model_build",
        composite=True,
        steps=_steps(_NODE, _ELEM, _MATL, _SECT),
    ),
    "BUILD.FRAME": OperationPlan(
        "BUILD.FRAME",
        "engineering_model_build",
        composite=True,
        steps=_steps(_NODE, _ELEM, _MATL, _SECT),
    ),
    "BUILD.TRUSS": OperationPlan(
        "BUILD.TRUSS",
        "engineering_model_build",
        composite=True,
        steps=_steps(_NODE, _ELEM, _MATL, _SECT),
    ),
    "BUILD.SLAB": OperationPlan(
        "BUILD.SLAB", "engineering_model_build", composite=True, steps=_steps(_NODE, _ELEM)
    ),
    "BUILD.WALL": OperationPlan(
        "BUILD.WALL", "engineering_model_build", composite=True, steps=_steps(_NODE, _ELEM)
    ),
    "BUILD.FOUNDATION": OperationPlan(
        "BUILD.FOUNDATION",
        "engineering_model_build",
        composite=True,
        steps=_steps(_NODE, _ELEM, _CONS),
    ),
    "BUILD.STEEL_FRAME": OperationPlan(
        "BUILD.STEEL_FRAME",
        "engineering_model_build",
        composite=True,
        steps=_steps(_NODE, _ELEM, _MATL, _SECT, _CONS),
    ),
    "MODEL.COPY": OperationPlan(
        "MODEL.COPY",
        "engineering_model_build",
        composite=True,
        steps=_steps(_NODE, _ELEM),
        note="docs/07 §6.5：无直接 API",
    ),
    "MODEL.MOVE": OperationPlan(
        "MODEL.MOVE",
        "engineering_model_build",
        composite=True,
        steps=_steps(_write("DB.NODE", "write_node", "midas.node.v1", method="PUT"), _ELEM),
        note="docs/07 §6.5：无直接 API（改坐标 + 重建单元）",
    ),
    "MODEL.MIRROR": OperationPlan(
        "MODEL.MIRROR",
        "engineering_model_build",
        composite=True,
        steps=_steps(_NODE, _ELEM),
        note="docs/07 §6.5：无直接 API",
    ),
    "MODEL.PATTERN": OperationPlan(
        "MODEL.PATTERN",
        "engineering_model_build",
        composite=True,
        steps=_steps(_NODE, _ELEM),
        note="docs/07 §6.5：无直接 API",
    ),
    "MODEL.GENERATE_GRID": OperationPlan(
        "MODEL.GENERATE_GRID",
        "engineering_model_build",
        composite=True,
        steps=_steps(_NODE),
        note="docs/07 §6.5：无直接 API",
    ),
}

# ===== §6.6 engineering_view（7）=====

_DISPLAY = _write("VIEW.DISPLAY", "view", None)
_RESULTGRAPHIC = _write("VIEW.RESULTGRAPHIC", "view", None)
_CAPTURE = _write("VIEW.CAPTURE", "view", "midas.view.capture.v1")

_VIEW: Final[dict[str, OperationPlan]] = {
    "VIEW.MODEL": OperationPlan("VIEW.MODEL", "engineering_view", steps=_steps(_DISPLAY, _CAPTURE)),
    "VIEW.DEFORMED_MODEL": OperationPlan(
        "VIEW.DEFORMED_MODEL", "engineering_view", steps=_steps(_DISPLAY, _RESULTGRAPHIC, _CAPTURE)
    ),
    "VIEW.REACTION": OperationPlan(
        "VIEW.REACTION", "engineering_view", steps=_steps(_RESULTGRAPHIC, _CAPTURE)
    ),
    "VIEW.DISPLACEMENT": OperationPlan(
        "VIEW.DISPLACEMENT", "engineering_view", steps=_steps(_RESULTGRAPHIC, _CAPTURE)
    ),
    "VIEW.STRESS": OperationPlan(
        "VIEW.STRESS", "engineering_view", steps=_steps(_RESULTGRAPHIC, _CAPTURE)
    ),
    "VIEW.FORCE": OperationPlan(
        "VIEW.FORCE", "engineering_view", steps=_steps(_RESULTGRAPHIC, _CAPTURE)
    ),
    "VIEW.MODE_SHAPE": OperationPlan(
        "VIEW.MODE_SHAPE", "engineering_view", steps=_steps(_RESULTGRAPHIC, _CAPTURE)
    ),
}

# ===== §6.7 engineering_result（6）=====


def _result(key: str, *, alternatives: tuple[str, ...] = (), note: str = "") -> EndpointStep:
    """结果读取步骤（`docs/07` §6.7：全部为 `POST /POST/TABLE` + `Argument.TABLE_TYPE`）。"""
    return EndpointStep(
        key=key,
        method="POST",
        intent="result",
        transformer="midas.result.request.v1",
        note=note,
        alternatives=alternatives,
    )


_RESULT: Final[dict[str, OperationPlan]] = {
    "RESULT.NODE.DISPLACEMENT": OperationPlan(
        "RESULT.NODE.DISPLACEMENT",
        "engineering_result",
        steps=_steps(
            _result("POST.TABLE.DISPLACEMENTG", alternatives=("POST.TABLE.DISPLACEMENTL",))
        ),
    ),
    "RESULT.NODE.REACTION": OperationPlan(
        "RESULT.NODE.REACTION",
        "engineering_result",
        steps=_steps(
            _result(
                "POST.TABLE.REACTIONG",
                alternatives=("POST.TABLE.REACTIONL", "POST.TABLE.REACTIONLSURFACESPRING"),
            )
        ),
    ),
    "RESULT.ELEMENT.FORCE": OperationPlan(
        "RESULT.ELEMENT.FORCE",
        "engineering_result",
        steps=_steps(
            _result(
                "POST.TABLE.BEAMFORCE",
                alternatives=(
                    "POST.TABLE.TRUSSFORCE",
                    "POST.TABLE.PLATEFORCEL",
                    "POST.TABLE.SOLIDFL",
                ),
            )
        ),
    ),
    "RESULT.ELEMENT.STRESS": OperationPlan(
        "RESULT.ELEMENT.STRESS",
        "engineering_result",
        steps=_steps(
            _result(
                "POST.TABLE.BEAMSTRESS",
                alternatives=("POST.TABLE.PLATESTRESSL", "POST.TABLE.SOLIDSL"),
            )
        ),
    ),
    "RESULT.MODE.SHAPE": OperationPlan(
        "RESULT.MODE.SHAPE",
        "engineering_result",
        steps=_steps(
            _result("POST.TABLE.EIGENVALUEMODE", alternatives=("POST.TABLE.BUCKLINGMODE",))
        ),
    ),
    "RESULT.ANALYSIS.SUMMARY": OperationPlan(
        "RESULT.ANALYSIS.SUMMARY",
        "engineering_result",
        steps=_steps(_result("POST.TABLE", note="docs/07 §6.7：通用入口，需 TABLE_TYPE")),
        note="按需选具体表",
    ),
}

# ===== §6.8 engineering_design（6）=====

_DESIGN_ANAL = _write("DESIGN.STEEL.KDS-41-30-2022.CODE-ANAL", "design", "midas.design.steel.v1")
_DESIGN_TABLE = _write("DESIGN.STEEL.KDS-41-30-2022.CODE-TABLE", "design_result", None)

_DESIGN: Final[dict[str, OperationPlan]] = {
    "DESIGN.STEEL": OperationPlan(
        "DESIGN.STEEL",
        "engineering_design",
        composite=True,
        steps=_steps(
            _read("DESIGN.STEEL.DSTL"),
            _read("DESIGN.STEEL.KDS-41-30-2022.DCO"),
            _read("DESIGN.STEEL.KDS-41-30-2022.DCTL"),
            _read("DESIGN.STEEL.KDS-41-30-2022.MEMB"),
            _DESIGN_ANAL,
            _DESIGN_TABLE,
        ),
        note="docs/07 §6.8：规范选择 → 选项 → 控制 → 构件 → 校核 → 结果",
    ),
    "DESIGN.CONCRETE": OperationPlan(
        "DESIGN.CONCRETE",
        "engineering_design",
        composite=True,
        steps=_steps(
            _read("DESIGN.RC.DRC"),
            _read("DESIGN.RC.KDS-41-20-2022.DCO"),
            _read("DESIGN.RC.KDS-41-20-2022.DCTL"),
            _read("DESIGN.RC.KDS-41-20-2022.MEMB"),
            _write("DESIGN.RC.KDS-41-20-2022.BD-ANAL", "design", None),
            _write("DESIGN.RC.KDS-41-20-2022.BD-TABLE", "design_result", None),
        ),
        note="docs/07 §6.8：BD/CD/BRD/WD-ANAL（设计）或 BC/CC/BRC/WC-ANAL（校核）",
    ),
    "DESIGN.SRC": OperationPlan(
        "DESIGN.SRC",
        "engineering_design",
        composite=True,
        steps=_steps(
            _write("DESIGN.SRC.AIK-SRC2K.DSRC", "design", None, method="PUT"),
            _read("DESIGN.SRC.AIK-SRC2K.DCO"),
            _read("DESIGN.SRC.AIK-SRC2K.DCTL"),
            _read("DESIGN.SRC.AIK-SRC2K.MEMB"),
            _write("DESIGN.SRC.AIK-SRC2K.BC-ANAL", "design", None),
            _write("DESIGN.SRC.AIK-SRC2K.BC-TABLE", "design_result", None),
        ),
        note="docs/07 §6.8：DSRC（规范选择）→ DCO → DCTL → MEMB → BC/CC-ANAL → *-TABLE",
    ),
    "DESIGN.FOUNDATION": OperationPlan(
        "DESIGN.FOUNDATION",
        "engineering_design",
        note="docs/07 §6.8：MIDAS 无任何 API（自研引擎；仅提供基底反力 POST.TABLE.REACTIONG）",
    ),
    "DESIGN.OPTIMIZE": OperationPlan(
        "DESIGN.OPTIMIZE",
        "engineering_design",
        note="docs/07 §6.8：唯一真优化端点为 SRC 专用 DESIGN.SRC.AIK-SRC2K.OCHECK；"
        "自研优化循环 apply=false 默认",
    ),
    "DESIGN.CODE_CHECK": OperationPlan(
        "DESIGN.CODE_CHECK",
        "engineering_design",
        composite=True,
        note="docs/07 §6.8：MIDAS 无统一校核入口，按「材料 × 构件类型」路由",
        routes={
            "steel": _steps(
                _write("DESIGN.STEEL.KDS-41-30-2022.CODE-ANAL", "design", "midas.design.steel.v1"),
                _write("DESIGN.STEEL.KDS-41-30-2022.CODE-TABLE", "design_result", None),
                _write("POST.STEELCODECHECK", "design_result", None),
            ),
            "concrete:BD": _steps(
                _write("DESIGN.RC.KDS-41-20-2022.BD-ANAL", "design", None),
                _write("DESIGN.RC.KDS-41-20-2022.BD-TABLE", "design_result", None),
            ),
            "concrete:CD": _steps(
                _write("DESIGN.RC.KDS-41-20-2022.CD-ANAL", "design", None),
                _write("DESIGN.RC.KDS-41-20-2022.CD-TABLE", "design_result", None),
            ),
            "concrete:BRD": _steps(
                _write("DESIGN.RC.KDS-41-20-2022.BRD-ANAL", "design", None),
                _write("DESIGN.RC.KDS-41-20-2022.BRD-TABLE", "design_result", None),
            ),
            "concrete:WD": _steps(
                _write("DESIGN.RC.KDS-41-20-2022.WD-ANAL", "design", None),
                _write("DESIGN.RC.KDS-41-20-2022.WD-TABLE", "design_result", None),
            ),
            "src:BC": _steps(
                _write("DESIGN.SRC.AIK-SRC2K.BC-ANAL", "design", None),
                _write("DESIGN.SRC.AIK-SRC2K.BC-TABLE", "design_result", None),
            ),
            "src:CC": _steps(
                _write("DESIGN.SRC.AIK-SRC2K.CC-ANAL", "design", None),
                _write("DESIGN.SRC.AIK-SRC2K.CC-TABLE", "design_result", None),
            ),
        },
    ),
}

# ===== §6.9 engineering_analysis（7）=====


def _analyze(*prerequisites: EndpointStep) -> tuple[EndpointStep, ...]:
    """分析编排：前置表先读/写，最后执行 `DOC.ANAL`（`docs/07` §6.9 的「+ 前置」）。"""
    return (*prerequisites, _write("DOC.ANAL", "analyze", "midas.anal.v1"))


_ANALYSIS: Final[dict[str, OperationPlan]] = {
    "ANALYSIS.STATIC": OperationPlan(
        "ANALYSIS.STATIC",
        "engineering_analysis",
        steps=_analyze(_read("DB.STLD"), _read("DB.BMLD"), _read("DB.CONS")),
        note="docs/07 §6.9：DOC.ANAL + 前置 DB.STLD / DB.BMLD / DB.CONS",
    ),
    "ANALYSIS.MODAL": OperationPlan(
        "ANALYSIS.MODAL",
        "engineering_analysis",
        steps=_analyze(_read("DB.EIGV")),
        note="特征值控制 DB.EIGV",
    ),
    "ANALYSIS.SEISMIC": OperationPlan(
        "ANALYSIS.SEISMIC",
        "engineering_analysis",
        steps=_analyze(_read("DB.POSL"), _read("DB.STYP")),
        note="地震荷载参数 + 层类型",
    ),
    "ANALYSIS.SPECTRUM": OperationPlan(
        "ANALYSIS.SPECTRUM",
        "engineering_analysis",
        steps=_analyze(_read("DB.STLD"), _read("DB.POSL")),
        note="反应谱荷载工况",
    ),
    "ANALYSIS.BUCKLING": OperationPlan(
        "ANALYSIS.BUCKLING",
        "engineering_analysis",
        steps=_analyze(_read("DB.EIGV")),
        note="屈曲模式（特征值控制）",
    ),
    "ANALYSIS.TIME_HISTORY": OperationPlan(
        "ANALYSIS.TIME_HISTORY",
        "engineering_analysis",
        steps=_analyze(_read("DB.THGC"), _read("DB.THIS")),
        note="docs/07 §6.9 另列 DB.THOO，但该 key **不在** registry/manifest.json（见 §16）",
    ),
    "ANALYSIS.NONLINEAR": OperationPlan(
        "ANALYSIS.NONLINEAR",
        "engineering_analysis",
        steps=_analyze(_read("DB.NLCT")),
        note="非线性控制",
    ),
}

OPERATION_PLANS: Final[dict[str, OperationPlan]] = {
    plan.operation: plan
    for plan in (
        *_DOC.values(),
        *_QUERY.values(),
        *_ASSIGN.values(),
        *_DELETE.values(),
        *_BUILD.values(),
        *_VIEW.values(),
        *_RESULT.values(),
        *_DESIGN.values(),
        *_ANALYSIS.values(),
    )
}
"""`docs/07` §6 的全部映射（**69** 条；逐条照抄，见模块裁决 1）。"""


def plan_for(operation: str) -> OperationPlan:
    """取 Operation 的编排（`docs/07` §6.11）。

    Raises:
        MidasCapabilityError: `STRUCTAI-3000`，未登记 Operation（`operation_not_mapped`），
            或该 Operation **无**原生映射（`operation_has_no_native_mapping`，见裁决 3）。
    """
    plan = OPERATION_PLANS.get(str(operation))
    if plan is None:
        raise MidasCapabilityError("operation_not_mapped", operation=str(operation))
    if str(operation) in NO_NATIVE_MAPPING:
        raise MidasCapabilityError("operation_has_no_native_mapping", operation=str(operation))
    return plan


def plans_for_tool(tool: str) -> tuple[OperationPlan, ...]:
    """某 Tool 的全部编排（按 Operation 名升序；`docs/07` §5.1 的 Tool 划分）。"""
    return tuple(plan for _, plan in sorted(OPERATION_PLANS.items()) if plan.tool == str(tool))


def select_steps(operation: str, parameters: Mapping[str, Any]) -> tuple[EndpointStep, ...]:
    """选定该次调用真正要执行的步骤（`docs/07` §6.3 / §6.8 的路由）。

    Args:
        operation: Operation 名。
        parameters: 规范化参数（只读；用于路由与分派）。

    Returns:
        有序步骤；复合 Operation 返回全部步骤（Adapter 逐步执行）。

    Raises:
        MidasCapabilityError: 路由不到（`code_check_route_not_mapped`）——
            **不**猜测端点（`docs/07` §6.8）。
    """
    plan = plan_for(operation)
    if plan.operation == "MODEL.LOAD.ASSIGN":
        # `docs/07` §6.3 列了**六个**荷载端点，本次调用只执行 `load_type` 对应的那一个。
        return (load_step_for(plan, parameters),)
    if not plan.routes:
        return plan.steps
    route = _route_key(parameters)
    steps = plan.routes.get(route)
    if steps is None:
        raise MidasCapabilityError(
            "code_check_route_not_mapped",
            operation=operation,
            route=route,
            routes=sorted(plan.routes),
        )
    return steps


def _route_key(parameters: Mapping[str, Any]) -> str:
    """`DESIGN.CODE_CHECK` 的路由键：`材料[:构件类型]`（`docs/07` §6.8）。"""
    material = str(parameters.get("material") or "").lower()
    member_type = str(parameters.get("member_type") or "").lower()
    if material == "steel":
        return "steel"
    if material in {"concrete", "rc"} and member_type:
        return f"concrete:{member_type.upper()}"
    if material == "src" and member_type:
        return f"src:{member_type.upper()}"
    return material


def load_step_for(plan: OperationPlan, parameters: Mapping[str, Any]) -> EndpointStep:
    """`MODEL.LOAD.ASSIGN` 的单步选择（`docs/07` §6.3；未映射 → 明确错误）。

    Raises:
        MidasValidationError: `STRUCTAI-1200`，`load_type` 未映射
            （`details.reason = "load_type_not_mapped"`；`TEMPERATURE` 在 `registry/`
            的 DB Schema 里**没有**对应端点，见 `transforms.py` 裁决 7）。
        MidasCapabilityError: 该类型的端点不在本 Operation 的编排里（数据不一致）。
    """
    load_type = str(parameters.get("load_type") or "").upper()
    key = LOAD_STEP_BY_TYPE.get(load_type)
    if key is None:
        raise MidasValidationError(
            "load_type_not_mapped",
            load_type=load_type,
            mapped=sorted(LOAD_STEP_BY_TYPE),
        )
    for step in plan.steps:
        if step.key == key:
            return step
    raise MidasCapabilityError("load_step_not_in_plan", load_type=load_type, endpoint=key)
