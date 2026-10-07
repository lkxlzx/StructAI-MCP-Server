"""Infrastructure · Adapters · MIDAS · Capabilities —— 能力与规范探测（`docs/07` §6.12）。

权威来源
--------
- `docs/07` §7.4 / §5.6 —— 能力码取自落库的 **41** 条词表（`app.domain.enums.Capability`）；
  能力码中**不得**出现厂商名（`docs/07` §14.2）。
- `docs/07` §6.12（设计规范归属与发现机制）—— 三段式：静态候选集
  （`registry/design_codes.yaml`，155 条）→ **运行时探测**
  （`GET /DESIGN/{material}/{code}/DCO`：`200` 支持 / `404` 不支持，**零副作用**，
  结果只存连接会话、**不落盘**）→ 读当前生效值（`GET /db/DCON` / `/db/DSTL` / `/db/MODULE`）。
- `docs/04` §45 / §47（Capability Detection）—— `UNKNOWN ≠ SUPPORTED`；
  探测不到**不**等于「明确不支持」。
- `registry/README.md` §7.1 —— 探测路径与「结果只存连接会话」的原文口径。

落地裁决（只补实现手段，不改语义）
--------------------------------
1. **能力清单由数据可得性推导**：一条能力码在「其全部必需端点对该产品可得」时才算
   **可得**（`SUPPORTED`）；推导**只**读 `registry/`，不猜测、不写死产品差异。
2. **静态候选集本批不读**：`registry/design_codes.yaml` 是 YAML，而 `pyyaml`
   **不在** `docs/07` §3.2 的依赖清单里（§3.1 技术栈冻结、本批禁止引入新依赖）。
   本批只实现 §6.12 的**第 2 步**（对**请求到的** `code` 做零副作用探测）——
   枚举全量支持集不是本批门槛，**不**为它引入依赖或自写 YAML 解析器。
3. **探测结果只留在进程内**：`DesignCodeProbe` 把结果缓存在实例内存里
   （`docs/07` §6.12「结果只存连接会话，**不**落盘」），**不**写库、**不**写文件。
4. **材料段映射**：canonical 的 `material` 自由字符串 → 路径段 `STEEL` / `RC` / `SRC`
   （`registry/README.md` §7 的 D 套：`/DESIGN/{RC|STEEL|SRC}/{code}/…`）；
   未登记的材料 → **不**探测、返回 `False`（**不**猜测路径）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库、`app.domain` 与同包的 `errors.py` / `registry.py` / `client.py`；
**不**引用 SQLAlchemy / FastAPI / MCP SDK，**不**依赖 `app.interfaces`。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from app.domain.enums import Capability
from app.infrastructure.adapters.midas.client import MidasHttpClient
from app.infrastructure.adapters.midas.registry import MidasRegistry

__all__ = [
    "CAPABILITY_ENDPOINTS",
    "DESIGN_CODE_MATERIALS",
    "DESIGN_CODE_PROBE_TEMPLATE",
    "DesignCodeProbe",
    "capability_codes",
    "design_code_material",
]

CAPABILITY_ENDPOINTS: Final[dict[str, tuple[str, ...]]] = {
    Capability.MODEL_READ.value: ("OPE.PROJECTSTATUS",),
    Capability.MODEL_NODE_READ.value: ("DB.NODE",),
    Capability.MODEL_NODE_WRITE.value: ("DB.NODE",),
    Capability.MODEL_NODE_DELETE.value: ("DB.NODE",),
    Capability.MODEL_ELEMENT_READ.value: ("DB.ELEM",),
    Capability.MODEL_ELEMENT_WRITE.value: ("DB.ELEM",),
    Capability.MODEL_ELEMENT_DELETE.value: ("DB.ELEM",),
    Capability.MODEL_MATERIAL_READ.value: ("DB.MATL",),
    Capability.MODEL_MATERIAL_WRITE.value: ("DB.MATL",),
    Capability.MODEL_SECTION_READ.value: ("DB.SECT",),
    Capability.MODEL_SECTION_WRITE.value: ("DB.SECT",),
    Capability.MODEL_BOUNDARY_READ.value: ("DB.CONS",),
    Capability.MODEL_BOUNDARY_WRITE.value: ("DB.CONS",),
    Capability.MODEL_LOAD_READ.value: ("DB.STLD", "DB.BMLD", "DB.BODF", "DB.PRES"),
    Capability.MODEL_LOAD_WRITE.value: ("DB.STLD", "DB.BMLD", "DB.BODF", "DB.PRES"),
    Capability.MODEL_LOAD_DELETE.value: ("DB.STLD", "DB.BMLD"),
    Capability.MODEL_GROUP_READ.value: ("DB.GRUP",),
    Capability.DOCUMENT_NEW.value: ("DOC.NEW",),
    Capability.DOCUMENT_OPEN.value: ("DOC.OPEN",),
    Capability.DOCUMENT_SAVE.value: ("DOC.SAVE",),
    Capability.DOCUMENT_SAVE_AS.value: ("DOC.SAVEAS",),
    Capability.DOCUMENT_CLOSE.value: ("DOC.CLOSE",),
    Capability.DOCUMENT_INFO.value: ("OPE.PROJECTSTATUS",),
    Capability.ANALYSIS_STATIC.value: ("DOC.ANAL",),
    Capability.ANALYSIS_MODAL.value: ("DOC.ANAL", "DB.EIGV"),
    Capability.ANALYSIS_SEISMIC.value: ("DOC.ANAL", "DB.POSL"),
    Capability.ANALYSIS_SPECTRUM.value: ("DOC.ANAL", "DB.POSL"),
    Capability.ANALYSIS_BUCKLING.value: ("DOC.ANAL", "DB.EIGV"),
    Capability.ANALYSIS_TIME_HISTORY.value: ("DOC.ANAL", "DB.THGC"),
    Capability.ANALYSIS_NONLINEAR.value: ("DOC.ANAL", "DB.NLCT"),
    Capability.RESULT_DISPLACEMENT.value: ("POST.TABLE.DISPLACEMENTG",),
    Capability.RESULT_REACTION.value: ("POST.TABLE.REACTIONG",),
    Capability.RESULT_ELEMENT_FORCE.value: ("POST.TABLE.BEAMFORCE",),
    Capability.RESULT_STRESS.value: ("POST.TABLE.BEAMSTRESS",),
    Capability.RESULT_MODE_SHAPE.value: ("POST.TABLE.EIGENVALUEMODE",),
    Capability.DESIGN_STEEL.value: ("DESIGN.STEEL.DSTL", "DESIGN.STEEL.KDS-41-30-2022.DCO"),
    Capability.DESIGN_CONCRETE.value: ("DESIGN.RC.DRC", "DESIGN.RC.KDS-41-20-2022.DCO"),
    Capability.DESIGN_SRC.value: ("DESIGN.SRC.AIK-SRC2K.DCO",),
    Capability.DESIGN_CODE_CHECK.value: ("DESIGN.STEEL.KDS-41-30-2022.CODE-ANAL",),
}
"""能力码 → 必需端点（`docs/04` §9 的 `midas_capability_mappings` 的数据来源）。"""

DESIGN_CODE_MATERIALS: Final[dict[str, str]] = {
    "steel": "STEEL",
    "concrete": "RC",
    "rc": "RC",
    "src": "SRC",
}
"""canonical 材料 → `/DESIGN/{material}/{code}` 的路径段（`registry/README.md` §7）。"""

DESIGN_CODE_PROBE_TEMPLATE: Final[str] = "/DESIGN/{material}/{code}/DCO"
"""`docs/07` §6.12 第 2 步的探测路径（`200` 支持 / `404` 不支持；零副作用）。"""


def design_code_material(material: str) -> str | None:
    """canonical 材料 → 路径段；未登记 → `None`（**不**猜测，见裁决 4）。"""
    return DESIGN_CODE_MATERIALS.get(str(material).lower())


def capability_codes(registry: MidasRegistry, *, product: str) -> list[str]:
    """该产品上**可得**的能力码（`docs/07` §7.4；见裁决 1）。

    Args:
        registry: 端点数据视图。
        product: 数据侧的产品键（如 `CIVIL_NX`）。

    Returns:
        能力码列表（升序）；全部必需端点对该产品可得才算可得。
        ⚠️ 清单**不**以 `verification_status` 过滤：执行门槛由 `client.guard_verified()`
        单独把关（`docs/07` §7.2 / §16 R1），两者语义不同。
    """
    codes: list[str] = []
    for code, keys in CAPABILITY_ENDPOINTS.items():
        if all(_available_for(registry, key=key, product=product) for key in keys):
            codes.append(code)
    return sorted(codes)


def _available_for(registry: MidasRegistry, *, key: str, product: str) -> bool:
    """该端点对该产品是否可得（`registry/README.md` §4 的 `products` / `product_overrides`）。"""
    if not registry.has(key):
        return False
    definition = registry.endpoint(key)
    if not definition.enabled:
        return False
    return str(product) in definition.products or str(product) in definition.overrides


class DesignCodeProbe:
    """设计规范支持性探测（`docs/07` §6.12 第 2 步；见裁决 3）。

    结果缓存在**进程内**（连接会话级），**不**落盘、**不**写库。
    """

    def __init__(self, client: MidasHttpClient) -> None:
        """绑定客户端（探测本身零副作用）。"""
        self._client = client
        self._cache: dict[tuple[str, str], bool] = {}

    def cached(self) -> Mapping[tuple[str, str], bool]:
        """已探测结果（只读快照；`(material, code) → supported`）。"""
        return dict(self._cache)

    async def supported(self, *, material: str, code: str) -> bool:
        """`GET /DESIGN/{material}/{code}/DCO` → `200` 支持 / `404` 不支持。

        Args:
            material: canonical 材料（`steel` / `concrete` / `src`）。
            code: 自由字符串规范名（`docs/07` §6.12：Core 侧**不**出现厂商规范名）。

        Returns:
            是否支持；未登记材料 → `False`（**不**探测、**不**猜测路径）。

        Raises:
            MidasConnectionError: 传输层失败（`STRUCTAI-2000`）—— 与「不支持」严格区分。
            MidasTimeoutError: 探测超时（`STRUCTAI-2300`）。
        """
        segment = design_code_material(material)
        if segment is None:
            return False
        cache_key = (segment, str(code))
        if cache_key in self._cache:
            return self._cache[cache_key]
        path = DESIGN_CODE_PROBE_TEMPLATE.format(material=segment, code=str(code))
        status = await self._client.probe(path)
        supported = status == 200
        self._cache[cache_key] = supported
        return supported
