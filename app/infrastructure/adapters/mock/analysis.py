"""Infrastructure · Adapters · Mock · Analysis —— Mock 静力分析与结果（`docs/02` §41–§47 / §91）。

权威来源
--------
- `docs/02` §41 / §42（`adapter`）—— Mock **不**声称是工程真实求解器，必须标记
  `NOT ENGINEERING-GRADE`；单柱近似用 `δ = F L / (E A)`。
- `docs/02` §45（`adapter`）—— `ANALYSIS.STATIC`：无节点 / 无单元 → 拒绝；成功返回
  `{"status": "COMPLETED", "analysis_type": "STATIC", "engine": "MockEngineering",
  "engineering_grade": false}`。
- `docs/02` §46（`adapter`）—— `RESULT.NODE.DISPLACEMENT`：`uz = |fz| × 1e-8`
  （节点必须存在），并带 `engine` / `engineering_grade`。
- `docs/02` §47 / §92（`adapter`）—— `DESIGN.STEEL`：`{"status": "PASS",
  "utilization": 0.72, "engine": "MockEngineering", "engineering_grade": false}`。
- `docs/02` §63（`adapter`）—— Mock E2E 的**所有**结果 `engineering_grade = false`。
- `docs/02` §65（`adapter`）—— Mock Adapter **不允许**成为生产计算器：只用于
  unit / integration / e2e / demo / development。
- `docs/07` §12.1 里程碑 ③④⑤ —— `ANALYSIS.STATIC` / `RESULT.*` / `DESIGN.STEEL` 的
  可运行闭环（本批实现，端到端验收在后续批次）。

落地裁决（只补实现手段，不改取值 / 不改语义）
--------------------------------------------
1. **位移优先用 `docs/02` §42 的 `δ = F L / (E A)`，缺信息时回落 §46 的 `|fz| × 1e-8`**：
   §42（公式）与 §46（示例代码 `fz * 1e-8`）给出的数值口径不同。本模块的规则是：
   - 节点所属单元**同时**有材料与截面（`E` / `A` 可得）→ 用 §42 的公式，`L` 取该单元
     两端节点的 `|Δz|`（单柱的柱高）；
   - 否则 → 用 §46 的 `|fz| × 1e-8`（**不**臆造几何 / 材料，与 R19「不臆造内容」同口径）。
   两条分支都确定性（无随机、无时钟），且都带 `engineering_grade = false`。
2. **符号约定照抄 §46**：位移返回**幅值**（正值），表示轴向变形量；`RESULT.ELEMENT.FORCE`
   的 `axial` 取「该单元节点荷载 `fz` 之和」（负 = 受压，Mock 约定），
   `RESULT.ELEMENT.STRESS` 的 `axial_stress = axial / A`（截面未知 → `0.0`，**不**臆造）。
3. **`RESULT.NODE.REACTION` = 全模型荷载的相反数**：Mock 只做「静力平衡一致」的确定性
   结果；节点**有**边界条件时返回 `-Σload`，无边界条件时返回 0。
   ⚠️ 多支座模型下**不**做反力分配（`docs/02` §41：`NOT ENGINEERING-GRADE`）——
   仅用于 Core 闭环测试（§64 / §65）。
4. **`DESIGN.STEEL` 的 `utilization = 0.72` 是 `docs/02` §47 的**固定测试值**，
   不是计算出来的利用率；本模块**不**把它包装成工程结论（§47 / §92 原文即固定值）。
5. **所有结果经 `mark()` 注入 `engine` / `engineering_grade`**：`docs/02` §42 / §63 要求
   Mock 结果一律可识别为**非工程级**；注入点只此一处，避免某个结果漏标。

分层红线（`docs/07` §14.1 / §14.2 / §14.3）
------------------------------------------
本模块只依赖标准库与同层的 `model_store` / `base/errors`（**不**引用 SQLAlchemy /
FastAPI / MCP SDK / httpx，**不**依赖 `app.interfaces`）；**不**写表、**不** `commit`、
**不**记录 secret；`MATERIALS` / `SECTIONS` 是测试数据（`docs/02` §43 / §44）。
"""

from __future__ import annotations

from typing import Any, Final

from app.infrastructure.adapters.base.errors import AdapterValidationError
from app.infrastructure.adapters.mock.model_store import MockElement, MockModelStore

__all__ = [
    "DISPLACEMENT_FALLBACK_SCALE",
    "ENGINEERING_GRADE",
    "MOCK_ENGINE",
    "NOT_ENGINEERING_GRADE_NOTE",
    "STEEL_STATUS_PASS",
    "STEEL_UTILIZATION",
    "axial_displacement",
    "element_force",
    "element_stress",
    "mark",
    "node_displacement",
    "node_reaction",
    "static_analysis",
    "steel_design",
]

MOCK_ENGINE: Final[str] = "MockEngineering"
"""结果里的引擎标识（`docs/02` §42 / §45 / §46 / §47 / §92，逐字照抄）。"""

ENGINEERING_GRADE: Final[bool] = False
"""Mock 结果**永远**不是工程级（`docs/02` §41 / §42 / §63）。"""

NOT_ENGINEERING_GRADE_NOTE: Final[str] = (
    "MockEngineering results are NOT ENGINEERING-GRADE and must not be used for "
    "design, construction drawings, review or engineering calculation reports"
)
"""`docs/02` §41 / §65 的明文声明（供日志 / 文档 / 响应注释使用）。"""

STEEL_UTILIZATION: Final[float] = 0.72
"""`DESIGN.STEEL` 的固定测试利用率（`docs/02` §47 / §92 原文取值）。"""

STEEL_STATUS_PASS: Final[str] = "PASS"
"""`DESIGN.STEEL` 的固定测试状态（`docs/02` §47 / §92 原文取值）。"""

DISPLACEMENT_FALLBACK_SCALE: Final[float] = 1e-8
"""`docs/02` §46 的位移回落系数（`|fz| × 1e-8`，见裁决 1）。"""


# ===== 统一标记（见裁决 5）=====


def mark(payload: dict[str, Any]) -> dict[str, Any]:
    """给结果注入 `engine` / `engineering_grade`（`docs/02` §42 / §63）。

    Args:
        payload: Mock 计算出的结果字段。

    Returns:
        新字典 = `payload` + `engine` + `engineering_grade`（**不**修改入参）。
    """
    return {**payload, "engine": MOCK_ENGINE, "engineering_grade": ENGINEERING_GRADE}


# ===== 静力分析（`docs/02` §45 / §91）=====


def static_analysis(store: MockModelStore) -> dict[str, Any]:
    """Mock 静力分析（`docs/02` §45 / §91）。

    流程（§91）：`Validate model → Find loads → Generate deterministic test result`。

    Args:
        store: 进程内模型状态。

    Returns:
        `{"status": "COMPLETED", "analysis_type": "STATIC", "engine": ...,
        "engineering_grade": False, ...}`（§45 逐字段照抄 + 计数摘要）。

    Raises:
        AdapterValidationError: `STRUCTAI-1200` —— 无节点或**无单元**（§45）。
    """
    if not store.nodes:
        raise AdapterValidationError(
            "No nodes",
            details={"stage": "mock_analysis", "reason": "no_nodes"},
        )
    if not store.elements:
        raise AdapterValidationError(
            "No elements",
            details={"stage": "mock_analysis", "reason": "no_elements"},
        )
    return mark(
        {
            "status": "COMPLETED",
            "analysis_type": "STATIC",
            "nodes": len(store.nodes),
            "elements": len(store.elements),
            "loads": len(store.loads),
            "boundaries": len(store.boundaries),
        }
    )


# ===== 结果（`docs/02` §46）=====


def node_displacement(store: MockModelStore, node_id: int) -> dict[str, Any]:
    """节点位移（`docs/02` §46；见裁决 1 / 2）。

    Args:
        store: 进程内模型状态。
        node_id: 节点 id；**必须**存在（§46）。

    Returns:
        `{"node_id": ..., "ux": 0.0, "uy": 0.0, "uz": <幅值>, "engine": ...,
        "engineering_grade": False}`。

    Raises:
        AdapterValidationError: `STRUCTAI-1200` —— 节点不存在（§46）。
    """
    target = int(node_id)
    if target not in store.nodes:
        raise AdapterValidationError(
            "Node not found",
            details={"stage": "mock_analysis", "reason": "node_not_found"},
        )
    load = store.loads.get(target)
    axial_force = abs(load.fz) if load is not None else 0.0

    displacement = _axial_displacement_for_node(store, target, axial_force)
    return mark(
        {
            "node_id": target,
            "ux": 0.0,
            "uy": 0.0,
            "uz": displacement,
        }
    )


def node_reaction(store: MockModelStore, node_id: int) -> dict[str, Any]:
    """节点反力（`docs/02` §30 的 `RESULT.REACTION`；见裁决 3）。

    Args:
        store: 进程内模型状态。
        node_id: 节点 id；**必须**存在。

    Returns:
        节点**有**边界条件时为全模型荷载的相反数（静力平衡一致）；否则全 0。

    Raises:
        AdapterValidationError: `STRUCTAI-1200` —— 节点不存在。
    """
    target = int(node_id)
    if target not in store.nodes:
        raise AdapterValidationError(
            "Node not found",
            details={"stage": "mock_analysis", "reason": "node_not_found"},
        )
    if target not in store.boundaries:
        return mark({"node_id": target, "fx": 0.0, "fy": 0.0, "fz": 0.0})
    return mark(
        {
            "node_id": target,
            "fx": -sum(load.fx for load in store.loads.values()),
            "fy": -sum(load.fy for load in store.loads.values()),
            "fz": -sum(load.fz for load in store.loads.values()),
        }
    )


def element_force(store: MockModelStore, element_id: int) -> dict[str, Any]:
    """单元内力（`docs/02` §30 的 `RESULT.ELEMENT_FORCE`；见裁决 2）。

    Args:
        store: 进程内模型状态。
        element_id: 单元 id；**必须**存在。

    Returns:
        `axial` = 该单元节点荷载 `fz` 之和（**负 = 受压**，Mock 约定）；
        剪力 / 弯矩一律 0（Mock 不做真实求解，`docs/02` §41）。

    Raises:
        AdapterValidationError: `STRUCTAI-1200` —— 单元不存在。
    """
    element = _require_element(store, element_id)
    axial = sum(store.loads[node_id].fz for node_id in element.node_ids if node_id in store.loads)
    return mark(
        {
            "element_id": element.id,
            "axial": axial,
            "shear_y": 0.0,
            "shear_z": 0.0,
            "moment_y": 0.0,
            "moment_z": 0.0,
        }
    )


def element_stress(store: MockModelStore, element_id: int) -> dict[str, Any]:
    """单元应力（`docs/02` §30 的 `RESULT.STRESS`；见裁决 2）。

    Args:
        store: 进程内模型状态。
        element_id: 单元 id；**必须**存在。

    Returns:
        `axial_stress = axial / A`（`A` 取该单元截面的 `area`）；
        截面未知 → `0.0`（**不**臆造几何，见裁决 2）。

    Raises:
        AdapterValidationError: `STRUCTAI-1200` —— 单元不存在。
    """
    element = _require_element(store, element_id)
    force = element_force(store, element.id)
    section = store.sections.get(element.section or "")
    area = section.area if section is not None else 0.0
    axial_stress = float(force["axial"]) / area if area else 0.0
    return mark(
        {
            "element_id": element.id,
            "axial_stress": axial_stress,
            "bending_stress": 0.0,
            "combined_stress": axial_stress,
        }
    )


# ===== 设计（`docs/02` §47 / §92）=====


def steel_design(store: MockModelStore, element_id: int) -> dict[str, Any]:
    """钢结构设计（`docs/02` §47 / §92；见裁决 4）。

    Args:
        store: 进程内模型状态。
        element_id: 单元 id；**必须**存在（§92 的返回含 `element_id`）。

    Returns:
        `{"element_id": ..., "utilization": 0.72, "status": "PASS", "engine": ...,
        "engineering_grade": False}` —— `utilization` / `status` 是 §47 的**固定测试值**。

    Raises:
        AdapterValidationError: `STRUCTAI-1200` —— 单元不存在。
    """
    element = _require_element(store, element_id)
    return mark(
        {
            "element_id": element.id,
            "utilization": STEEL_UTILIZATION,
            "status": STEEL_STATUS_PASS,
        }
    )


# ===== 公式（`docs/02` §42）=====


def axial_displacement(
    axial_force: float,
    length: float,
    elastic_modulus: float,
    area: float,
) -> float:
    """轴向变形幅值 `δ = |F| L / (E A)`（`docs/02` §42）。

    Args:
        axial_force: 轴力（取幅值）。
        length: 构件长度 `L`。
        elastic_modulus: 弹性模量 `E`。
        area: 截面面积 `A`。

    Returns:
        `δ`；`E` / `A` / `L` 非正时返回 `0.0`（**不**抛除零，也**不**臆造参数）。
    """
    if elastic_modulus <= 0 or area <= 0 or length <= 0:
        return 0.0
    return abs(float(axial_force)) * float(length) / (float(elastic_modulus) * float(area))


# ===== 内部 =====


def _require_element(store: MockModelStore, element_id: int) -> MockElement:
    """取单元；不存在 → `STRUCTAI-1200`（§46 的节点口径同族）。"""
    element = store.elements.get(int(element_id))
    if element is None:
        raise AdapterValidationError(
            "Element not found",
            details={"stage": "mock_analysis", "reason": "element_not_found"},
        )
    return element


def _axial_displacement_for_node(
    store: MockModelStore,
    node_id: int,
    axial_force: float,
) -> float:
    """按裁决 1 选公式：可得的 `E` / `A` / `L` → §42；否则 §46 的回落。"""
    for element in store.elements.values():
        if node_id not in element.node_ids:
            continue
        material = store.materials.get(element.material or "")
        section = store.sections.get(element.section or "")
        if material is None or section is None:
            continue
        heights = [store.nodes[member].z for member in element.node_ids if member in store.nodes]
        if len(heights) < 2:
            continue
        length = max(heights) - min(heights)
        return axial_displacement(axial_force, length, material.elastic_modulus, section.area)
    return axial_force * DISPLACEMENT_FALLBACK_SCALE
