"""Infrastructure · Adapters · MIDAS · Manifest —— Adapter 注册声明（`docs/04` §62）。

权威来源
--------
- `docs/07` §7.1（唯一入口与新增文件）—— MIDAS 相关代码**只能**出现在
  `app/infrastructure/adapters/midas/`；本模块是该子包的声明面。
- `docs/07` §12 P119 —— `AdapterManifest`：`name=midas.civil`、`vendor=MIDAS`、
  `product=CIVIL NX`、`supported_versions=[2025,2026]`、`protocols=[REST]`。
- `docs/04` §62（Version Adapter Manifest）—— 逐字给出上述 JSON 形状；
  另给出 GEN NX 的 `name=midas.gen` / `product=GEN NX`。
- `docs/02` §6 / §7 / §19 / §20（adapter）—— Manifest 的字段与**严格精确**版本匹配；
  校验与注册复用既有 `AdapterManager`（`docs/07` §12 P119：「注册进既有 `AdapterManager`，
  **不**改 Core 装配形状」）。
- `registry/manifest.json` —— 端点数据里的产品键是 `CIVIL_NX` / `GEN_NX` /
  `CIVIL_DESIGNER`（`registry/README.md` §4 的 `products`），而 Manifest 的 `product`
  按 `docs/07` §7.1 写作 `CIVIL NX`（带空格）。两者是**同一个产品**的两种书写，
  本模块用 `REGISTRY_PRODUCT_KEYS` 做**单向**映射（Manifest 产品 → 数据产品键），
  **不**反向改写数据（`registry/` 是唯一权威）。

落地裁决（只补实现手段，不改字段名 / 取值）
--------------------------------------------
1. **版本取值写作字符串**：`docs/04` §62 的 JSON 是 `["2025","2026"]`；既有
   `AdapterManifest.supported_versions` 是 `tuple[str, ...]` 且匹配为**严格精确**
   （`docs/02` §20），故逐字写作 `("2025","2026")`，**不**做数值化 / 区间化。
2. **`capabilities` 留空**：`docs/02` §22（impl）的真实厂商 Manifest 示例即
   `"capabilities": []`（运行时能力由探测给出，`docs/04` §45 / `docs/07` §7.4）。
   静态声明与运行时探测**不得**混为一谈。
3. **`protocols = ("REST",)`**：`docs/04` §62 逐字；`AdapterManifest` 的协议词表是
   开放词表（`base/manifest.py` 裁决 1），`REST` 是其中的合法 token。
4. **厂商名只允许出现在本子包**：`docs/07` §14.2 要求 Core 中 `grep -ri midas app/` 为
   **0** 处（`app/infrastructure/adapters/midas/` 之外）；本模块即该红线的**唯一**豁免区，
   故这里出现 `MIDAS` / `midas.*` 是**规范要求**，不是违规。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与既有 Adapter 基座（`app/infrastructure/adapters/base`），
**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖 `app.interfaces`。
"""

from __future__ import annotations

from typing import Final

from app.infrastructure.adapters.base.manifest import AdapterManifest

__all__ = [
    "MIDAS_ADAPTER_NAME",
    "MIDAS_CAPABILITIES",
    "MIDAS_PRODUCT",
    "MIDAS_PROTOCOLS",
    "MIDAS_SUPPORTED_VERSIONS",
    "MIDAS_VENDOR",
    "REGISTRY_PRODUCT_KEYS",
    "midas_manifest",
    "registry_product_key",
]

MIDAS_ADAPTER_NAME: Final[str] = "midas.civil"
"""`docs/07` §7.1 / `docs/04` §62：Adapter 包标识（诊断用，不参与注册键）。"""

MIDAS_VENDOR: Final[str] = "MIDAS"
"""`docs/07` §7.1 / `docs/04` §62：厂商。厂商名只允许出现在本子包（见裁决 4）。"""

MIDAS_PRODUCT: Final[str] = "CIVIL NX"
"""`docs/07` §7.1 / `docs/04` §62：产品（注册键的一半）。"""

MIDAS_SUPPORTED_VERSIONS: Final[tuple[str, ...]] = ("2025", "2026")
"""`docs/04` §62 / §61：`CIVIL NX 2025` / `CIVIL NX 2026`（严格精确匹配）。"""

MIDAS_PROTOCOLS: Final[tuple[str, ...]] = ("REST",)
"""`docs/04` §62：协议族（开放词表 token）。"""

MIDAS_CAPABILITIES: Final[tuple[str, ...]] = ()
"""静态能力清单**留空**（见裁决 2）；运行时清单见 `capabilities.py`。"""

REGISTRY_PRODUCT_KEYS: Final[dict[str, str]] = {
    "CIVIL NX": "CIVIL_NX",
    "GEN NX": "GEN_NX",
    "Civil Designer": "CIVIL_DESIGNER",
}
"""Manifest 产品名 → `registry/manifest.json` 的产品键（单向；见模块裁决 1 的注）。"""


def midas_manifest() -> AdapterManifest:
    """构造 MIDAS Adapter 的 `AdapterManifest`（`docs/07` §7.1；`docs/04` §62）。

    Returns:
        **未**校验的 Manifest；装配期由 `AdapterManager.register()` 调 `validate()`
        （`docs/02` §19）—— 重复注册同一 `(vendor, product)` → `STRUCTAI-7000`。
    """
    return AdapterManifest(
        name=MIDAS_ADAPTER_NAME,
        vendor=MIDAS_VENDOR,
        product=MIDAS_PRODUCT,
        supported_versions=MIDAS_SUPPORTED_VERSIONS,
        protocols=MIDAS_PROTOCOLS,
        capabilities=MIDAS_CAPABILITIES,
    )


def registry_product_key(product: str) -> str:
    """Manifest 产品名 → 数据文件的产品键（**单向**映射；未登记则原样返回）。

    Args:
        product: Manifest 侧的产品名（如 `CIVIL NX`）或数据侧的产品键（如 `CIVIL_NX`）。

    Returns:
        `registry/manifest.json` 里的产品键；未登记时原样返回 ——
        调用方据此在数据里**找不到**端点并明确失败（**不**回落，`docs/04` §16）。
    """
    return REGISTRY_PRODUCT_KEYS.get(str(product), str(product))
