"""Infrastructure · Adapters · MIDAS —— MIDAS 接入的唯一入口子包（`docs/07` §7.1）。

权威来源
--------
- `docs/07` §7.1（唯一入口与新增文件）—— MIDAS 相关代码**只能**出现在本子包；
  文件形状为 `adapter` / `manifest` / `client` / `capabilities` / `operations` /
  `transforms` / `errors` / `health`（本批另加 `registry` / `models` /
  `import_registry`，见各模块 docstring 的裁决）。
- `docs/07` §14.2 —— Core 中**不得**出现任何厂商专属 endpoint / 参数 / 响应 / SDK：
  `grep -ri midas app/` 在**本子包之外**必须仍为 **0** 处。本子包即该红线的唯一豁免区。
- `docs/07` §12 P119 —— 注册进**既有** `AdapterManager`，**不**改 Core 装配形状
  （`AppContainer` 仍 **7** 字段、9 Tool 契约不变）。
- `docs/04` §104（Adapter 文件结构）—— 子包内的推荐布局。

落地裁决（只补实现手段，不改契约）
--------------------------------
1. **注册入口是 `install()`，由部署方显式调用**：Core 侧**不**允许出现 `midas`
   字样（`docs/07` §14.2），因此 `app/container.py` **不**装配本 Adapter ——
   部署方（或验收测试）显式调用 `install(manager)` 完成注册。
   这样「Core 装配形状不变」与「注册进既有 `AdapterManager`」两条要求同时成立。
2. **本模块不导出任何业务判断**：只做转发导出，避免 Core 侧出现「MIDAS 分支」。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本子包只依赖标准库、`app.domain` / `app.config`、Adapter 基座与 SQLAlchemy
（仅 `models.py` / `import_registry.py`）；**不**引用 FastAPI / MCP SDK，
**不**依赖 `app.interfaces` / `app.application`。
"""

from __future__ import annotations

from app.infrastructure.adapters.base.manager import AdapterFactory, AdapterManager
from app.infrastructure.adapters.base.manifest import AdapterManifest
from app.infrastructure.adapters.midas.adapter import MIDAS_INSTANCE_PRODUCTS, MidasAdapter
from app.infrastructure.adapters.midas.capabilities import (
    CAPABILITY_ENDPOINTS,
    DesignCodeProbe,
    capability_codes,
)
from app.infrastructure.adapters.midas.client import (
    MIDAS_BASE_URL_ENV,
    MIDAS_MAPI_KEY_ENV,
    BuiltRequest,
    MidasEnvironmentCredential,
    MidasHttpClient,
    guard_destructive,
    guard_enabled,
    guard_shape,
    guard_solver,
    guard_verified,
)
from app.infrastructure.adapters.midas.errors import RegistryMappingNotVerified
from app.infrastructure.adapters.midas.hardening import (
    HARDENING,
    HARDENING_ITEMS,
    HardeningItem,
)
from app.infrastructure.adapters.midas.health import HEALTH_CHECK_ENDPOINT, MidasHealthChecker
from app.infrastructure.adapters.midas.import_registry import (
    ImportReport,
    MidasRegistryImporter,
    schema_uri_for,
)
from app.infrastructure.adapters.midas.manifest import (
    MIDAS_ADAPTER_NAME,
    MIDAS_PRODUCT,
    MIDAS_PROTOCOLS,
    MIDAS_SUPPORTED_VERSIONS,
    MIDAS_VENDOR,
    midas_manifest,
    registry_product_key,
)
from app.infrastructure.adapters.midas.models import MIDAS_METADATA, MIDAS_TABLE_NAMES
from app.infrastructure.adapters.midas.operations import (
    OPERATION_PLANS,
    EndpointStep,
    OperationPlan,
    plan_for,
    plans_for_tool,
    select_steps,
)
from app.infrastructure.adapters.midas.registry import (
    MidasRegistry,
    ResolvedEndpoint,
    verification_status_for,
)
from app.infrastructure.adapters.midas.transforms import (
    TRANSFORMER_REGISTRY,
    SchemaBoundTransformer,
)
from app.infrastructure.adapters.midas.write_probe import (
    WRITE_METHODS,
    WRITE_PROBE_FAILED,
    WRITE_PROBE_NO_PAYLOAD,
    WRITE_PROBE_NO_READBACK,
    WRITE_PROBE_PASSED,
    MidasLiveWriteProbe,
    WriteProbeOutcome,
    WriteProbeReport,
    derive_body,
    transformer_name_for,
)

__all__ = [
    "MIDAS_ADAPTER_NAME",
    "MIDAS_PROTOCOLS",
    "CAPABILITY_ENDPOINTS",
    "HEALTH_CHECK_ENDPOINT",
    "MIDAS_BASE_URL_ENV",
    "MIDAS_INSTANCE_PRODUCTS",
    "MIDAS_MAPI_KEY_ENV",
    "MIDAS_METADATA",
    "MIDAS_PRODUCT",
    "MIDAS_SUPPORTED_VERSIONS",
    "MIDAS_TABLE_NAMES",
    "MIDAS_VENDOR",
    "OPERATION_PLANS",
    "HARDENING",
    "HARDENING_ITEMS",
    "TRANSFORMER_REGISTRY",
    "MidasLiveWriteProbe",
    "WRITE_METHODS",
    "WRITE_PROBE_FAILED",
    "WRITE_PROBE_NO_PAYLOAD",
    "WRITE_PROBE_NO_READBACK",
    "WRITE_PROBE_PASSED",
    "WriteProbeOutcome",
    "WriteProbeReport",
    "BuiltRequest",
    "DesignCodeProbe",
    "HardeningItem",
    "EndpointStep",
    "ImportReport",
    "MidasAdapter",
    "MidasEnvironmentCredential",
    "MidasHealthChecker",
    "MidasHttpClient",
    "MidasRegistry",
    "MidasRegistryImporter",
    "OperationPlan",
    "RegistryMappingNotVerified",
    "ResolvedEndpoint",
    "SchemaBoundTransformer",
    "capability_codes",
    "guard_destructive",
    "guard_enabled",
    "guard_shape",
    "derive_body",
    "transformer_name_for",
    "guard_solver",
    "guard_verified",
    "install",
    "midas_manifest",
    "plan_for",
    "plans_for_tool",
    "registry_product_key",
    "schema_uri_for",
    "select_steps",
    "verification_status_for",
]


def install(
    manager: AdapterManager,
    *,
    adapter: MidasAdapter | None = None,
    factory: AdapterFactory | None = None,
) -> AdapterManifest:
    """把 MIDAS Adapter 注册进既有 `AdapterManager`（`docs/07` §12 P119；见裁决 1）。

    Args:
        manager: 既有 Adapter 管理器（Core 的进程级对象）。
        adapter: 注册原型；缺省为 `MidasAdapter()`。
        factory: 为每个软件实例创建 Adapter 实例的工厂；缺省 `type(adapter)`
            （`MidasAdapter` 全部参数可选，故无参构造可用）。

    Returns:
        已校验的 `AdapterManifest`（`vendor=MIDAS` / `product=CIVIL NX`）。

    Raises:
        InternalError: `STRUCTAI-7000` —— Manifest 校验失败，或同一
            `(vendor, product)` 重复注册（`docs/02` §19；`docs/07` §12 P119 门槛 ①）。
    """
    return manager.register(adapter or MidasAdapter(), factory=factory)
