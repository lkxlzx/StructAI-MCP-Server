"""Infrastructure · Adapters · CSI ETABS · Manifest —— Adapter 注册声明（`docs/07` §12 P127）。

权威来源
--------
- `docs/01` §20（L907–918）—— ETABS 的原生事实块：
  `{"software": "CSI", "product": "ETABS", "version": "22", "operation": "ANALYSIS.STATIC",
  "protocol": "COM", "method": "RunAnalysis"}` —— 本模块的 `vendor` / `product` /
  `supported_versions` / `protocols` **逐字**取自它。
- `docs/02` §58（L26168–26183）—— 同一映射（`ETABS 22 → COM RunAnalysis`）。
- `docs/07` §14.2 —— 厂商名只允许出现在 Adapter 子包内（Core 中 `grep -ri csi app/` 必须为 0）。
- `docs/02` §6 / §7 / §19 / §20（adapter）—— Manifest 字段与**严格精确**版本匹配。

落地裁决（只补实现手段，不改字段名 / 取值）
--------------------------------------------
1. **`name` 是本批选定的诊断标识**：`docs/02` L24946 只给出了一个**示例入口名**
   （`structai_csi.adapter:CSIAdapter`，属未来的 entry point 形态，不在本批范围）。
   `name` 不参与注册键（`base/manifest.py` 裁决 4：键 = `(vendor, product)`），
   故本批写作 `csi.etabs` 并在此登记 —— **不**声称它来自规范。
2. **`supported_versions = ("22",)`**：`docs/01` §20 的 `version` 逐字为 `"22"`。
   匹配是**严格精确**的（`docs/02` §20）：`21` / `2024` 一律拒绝，**不**回落。
3. **`protocols = ("COM",)`**：`docs/01` §20 / `docs/03` §106 逐字；`COM` 是
   `AdapterManifest` 开放词表内的合法 token（`base/manifest.py` 裁决 1）。
4. **`capabilities` 留空**：`docs/02` §22（impl）的真实厂商 Manifest 示例即
   `"capabilities": []`（运行时能力由探测给出）。本批的运行时清单**只**来自
   `catalogue.py` 的可追溯条目（见 `capabilities.py`），**不**在这里静态声明。
5. **`ETABS_CATALOGUE_VERSION`**：catalogue 数据的版本标记（P133「Version migration」
   的可执行判定：条目带版本锚点，未声明的版本一律拒绝）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与既有 Adapter 基座；**不**引用 SQLAlchemy / FastAPI / MCP SDK /
httpx，**不**依赖 `app.interfaces` / `app.application`。
"""

from __future__ import annotations

from typing import Final

from app.infrastructure.adapters.base.manifest import AdapterManifest

__all__ = [
    "ETABS_ADAPTER_NAME",
    "ETABS_CAPABILITIES",
    "ETABS_CATALOGUE_VERSION",
    "ETABS_PRODUCT",
    "ETABS_PROTOCOLS",
    "ETABS_SUPPORTED_VERSIONS",
    "ETABS_VENDOR",
    "etabs_manifest",
]

ETABS_ADAPTER_NAME: Final[str] = "csi.etabs"
"""Adapter 包标识（诊断用，**不**参与注册键；见裁决 1）。"""

ETABS_VENDOR: Final[str] = "CSI"
"""`docs/01` §20 L911：厂商。厂商名只允许出现在本子包（`docs/07` §14.2）。"""

ETABS_PRODUCT: Final[str] = "ETABS"
"""`docs/01` §20 L912：产品（注册键的一半）。"""

ETABS_SUPPORTED_VERSIONS: Final[tuple[str, ...]] = ("22",)
"""`docs/01` §20 L913 / `docs/02` §58 L26178：声明支持的版本（严格精确匹配）。"""

ETABS_PROTOCOLS: Final[tuple[str, ...]] = ("COM",)
"""`docs/01` §20 L915 / `docs/03` §106 L3178：协议族（开放词表 token）。"""

ETABS_CAPABILITIES: Final[tuple[str, ...]] = ()
"""静态能力清单**留空**（见裁决 4）；运行时清单见 `capabilities.py`。"""

ETABS_CATALOGUE_VERSION: Final[str] = "csi.etabs.v1"
"""catalogue 数据的版本标记（见裁决 5）。"""


def etabs_manifest() -> AdapterManifest:
    """构造 ETABS Adapter 的 `AdapterManifest`（`docs/01` §20）。

    Returns:
        **未**校验的 Manifest；装配期由 `AdapterManager.register()` 调 `validate()`
        （`docs/02` §19）—— 重复注册同一 `(vendor, product)` → `STRUCTAI-7000`。
    """
    return AdapterManifest(
        name=ETABS_ADAPTER_NAME,
        vendor=ETABS_VENDOR,
        product=ETABS_PRODUCT,
        supported_versions=ETABS_SUPPORTED_VERSIONS,
        protocols=ETABS_PROTOCOLS,
        capabilities=ETABS_CAPABILITIES,
    )
