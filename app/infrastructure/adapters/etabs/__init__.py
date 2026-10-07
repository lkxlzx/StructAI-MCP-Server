"""Infrastructure · Adapters · CSI ETABS —— 第二个工程软件接入的**唯一**入口子包（P127–P133）。

权威来源
--------
- `docs/04` §154（第二个软件接入原则）—— 接入 ETABS **不**修改 9 MCP Tools / Task Engine /
  RBAC / MCP Session / Core Execution Pipeline；只增加 Adapter / Registry / Schema /
  Transformer / Capability Mapping / Contract Test。
- `docs/07` §12 P127 —— 注册进**既有** `AdapterManager`，**不**改 Core 装配形状
  （`AppContainer` 仍 **7** 字段、9 Tool 契约不变）。
- `docs/07` §14.2 —— Core 中**不得**出现任何厂商专属内容：
  `grep -ri etabs app/` / `grep -ri csi app/` 在**本子包之外**必须仍为 **0** 处。
- `docs/02` §88 L7602–7612 / `docs/03` §106 L3173–3181 —— `ANALYSIS.STATIC` → `COM RunAnalysis`
  （本仓库内**唯一**可追溯的 ETABS 原生事实；见 `catalogue.py`）。

落地裁决（只补实现手段，不改契约）
--------------------------------
1. **注册入口是 `install()`，由部署方显式调用**（`docs/07` §16 R81 的同一口径）：
   Core 侧**不**允许出现厂商字样（`docs/07` §14.2），因此 `app/container.py` /
   `app/main.py` **不**装配本 Adapter —— 部署方（或验收测试）显式调用
   `install(manager, factory=...)` 完成注册。这样「注册进既有 `AdapterManager`」
   与「Core 装配形状不变」两条要求同时成立。
2. **原生派发必须由工厂注入，或经 entry point 发现**（P135 / `docs/07` §16 **R88**）：
   本仓库**不**引入 COM 依赖（`docs/07` §3.1 技术栈冻结），故 `install(manager)` 在
   `factory` 缺省时**先**用 `dispatch.load_dispatch()` 发现部署方注册的 entry point
   （group = `structai.adapters.etabs.dispatch`，标准库 `importlib.metadata`）；
   发现不到就构造「未注入 dispatch」的 Adapter —— 它 `connect()` 时明确失败为
   `STRUCTAI-2000`（`reason = "dispatch_not_configured"`），**不**伪造连接。
   生产部署可以任选其一：① 注册 entry point；② 传
   `factory=lambda: EtabsAdapter(dispatch=<部署方的 COM 派发>)`。
3. **R93 的强制口径也在本子包**（`concurrency.py`）：`COM_SESSION_CONCURRENCY_SAFE = False`
   → `EtabsSerialConcurrencyPolicy` 把 ETABS 实例的策略**强制**成 `SERIAL`，
   供装配方注入 Core 的 `Scheduler(policies=...)`；Core 一行未改。
4. **本模块不导出任何业务判断**：只做转发导出，避免 Core 侧出现「ETABS 分支」。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本子包只依赖标准库、`app.domain` 与 Adapter 基座；**不**引用 SQLAlchemy / FastAPI /
MCP SDK / httpx，**不**依赖 `app.interfaces` / `app.application`，**不**建表、**不**写文件。
"""

from __future__ import annotations

from app.infrastructure.adapters.base.manager import AdapterFactory, AdapterManager
from app.infrastructure.adapters.base.manifest import AdapterManifest
from app.infrastructure.adapters.etabs.adapter import EtabsAdapter
from app.infrastructure.adapters.etabs.capabilities import (
    CAPABILITY_OPERATIONS,
    KNOWN_CAPABILITY_CODES,
    capability_codes,
    capability_for_operation,
    unknown_codes,
)
from app.infrastructure.adapters.etabs.catalogue import (
    ANALYSIS_STATIC_ENTRY,
    CATALOGUE,
    PARTIAL,
    PROVENANCE_ANCHORS,
    CatalogueEntry,
    catalogue_size,
    entry_for,
    has,
    partial_operations,
    verify_traceable,
)
from app.infrastructure.adapters.etabs.client import (
    CIRCUIT_CLOSED,
    CIRCUIT_OPEN,
    COM_PROTOCOL,
    DEFAULT_BUDGET_SECONDS,
    DESTRUCTIVE_SUFFIXES,
    BuiltRequest,
    CircuitBreaker,
    ComInvocation,
    EtabsComClient,
    RetryPolicy,
    guard_arguments,
    guard_destructive,
    guard_protocol,
    guard_verified,
    is_destructive,
)
from app.infrastructure.adapters.etabs.concurrency import (
    CONCURRENCY_LIMITED,
    CONCURRENCY_PARALLEL,
    CONCURRENCY_SERIAL,
    EtabsSerialConcurrencyPolicy,
    InstancePolicySourceLike,
    policies_for_instances,
)
from app.infrastructure.adapters.etabs.dispatch import (
    DISPATCH_ENTRY_POINT_GROUP,
    DispatchFactory,
    DispatchLoader,
    load_dispatch,
    registered_dispatch_entry_points,
)
from app.infrastructure.adapters.etabs.errors import (
    CAPABILITY_STAGE,
    ETABS_ERROR_STAGE,
    CatalogueNotTraceable,
    EtabsAPIError,
    EtabsAuthenticationError,
    EtabsCapabilityError,
    EtabsConnectionError,
    EtabsResultShapeError,
    EtabsTimeoutError,
    EtabsTransformerError,
    EtabsValidationError,
    MappingNotVerified,
    OperationNotInCatalogue,
    ProtocolNotDeclared,
    UnsupportedRequest,
)
from app.infrastructure.adapters.etabs.hardening import (
    COM_SESSION_CONCURRENCY_SAFE,
    DELEGATED,
    HARDENING,
    HARDENING_ITEMS,
    IMPLEMENTED,
    NOT_IMPLEMENTED,
    HardeningItem,
    status_of,
)
from app.infrastructure.adapters.etabs.health import HEALTH_KEYS, EtabsHealthChecker
from app.infrastructure.adapters.etabs.lifecycle import (
    CREDENTIAL_REFERENCE_KEY,
    ComDispatch,
    ComSession,
    ComSessionState,
)
from app.infrastructure.adapters.etabs.manifest import (
    ETABS_ADAPTER_NAME,
    ETABS_CAPABILITIES,
    ETABS_CATALOGUE_VERSION,
    ETABS_PRODUCT,
    ETABS_PROTOCOLS,
    ETABS_SUPPORTED_VERSIONS,
    ETABS_VENDOR,
    etabs_manifest,
)
from app.infrastructure.adapters.etabs.operations import (
    NATIVE_STEPS,
    NativeStep,
    native_steps,
    plan_for,
    plans_for_tool,
    tools,
)
from app.infrastructure.adapters.etabs.transforms import (
    ANALYSIS_TRANSFORMER_NAME,
    RESULT_FIELDS,
    TRANSFORMER_REGISTRY,
    AnalysisTransformer,
    transformer_for,
)

__all__ = [
    "ANALYSIS_STATIC_ENTRY",
    "ANALYSIS_TRANSFORMER_NAME",
    "CAPABILITY_OPERATIONS",
    "CAPABILITY_STAGE",
    "CATALOGUE",
    "CIRCUIT_CLOSED",
    "CIRCUIT_OPEN",
    "COM_PROTOCOL",
    "COM_SESSION_CONCURRENCY_SAFE",
    "CONCURRENCY_LIMITED",
    "CONCURRENCY_PARALLEL",
    "CONCURRENCY_SERIAL",
    "CREDENTIAL_REFERENCE_KEY",
    "DEFAULT_BUDGET_SECONDS",
    "DELEGATED",
    "DESTRUCTIVE_SUFFIXES",
    "DISPATCH_ENTRY_POINT_GROUP",
    "ETABS_ADAPTER_NAME",
    "ETABS_CAPABILITIES",
    "ETABS_CATALOGUE_VERSION",
    "ETABS_ERROR_STAGE",
    "ETABS_PRODUCT",
    "ETABS_PROTOCOLS",
    "ETABS_SUPPORTED_VERSIONS",
    "ETABS_VENDOR",
    "HARDENING",
    "HARDENING_ITEMS",
    "HEALTH_KEYS",
    "IMPLEMENTED",
    "KNOWN_CAPABILITY_CODES",
    "NATIVE_STEPS",
    "NOT_IMPLEMENTED",
    "PARTIAL",
    "PROVENANCE_ANCHORS",
    "RESULT_FIELDS",
    "TRANSFORMER_REGISTRY",
    "AnalysisTransformer",
    "BuiltRequest",
    "CatalogueEntry",
    "CatalogueNotTraceable",
    "CircuitBreaker",
    "ComDispatch",
    "ComInvocation",
    "ComSession",
    "ComSessionState",
    "DispatchFactory",
    "DispatchLoader",
    "EtabsAPIError",
    "EtabsAdapter",
    "EtabsAuthenticationError",
    "EtabsCapabilityError",
    "EtabsComClient",
    "EtabsConnectionError",
    "EtabsHealthChecker",
    "EtabsResultShapeError",
    "EtabsSerialConcurrencyPolicy",
    "EtabsTimeoutError",
    "EtabsTransformerError",
    "EtabsValidationError",
    "HardeningItem",
    "InstancePolicySourceLike",
    "MappingNotVerified",
    "NativeStep",
    "OperationNotInCatalogue",
    "ProtocolNotDeclared",
    "RetryPolicy",
    "UnsupportedRequest",
    "capability_codes",
    "capability_for_operation",
    "catalogue_size",
    "entry_for",
    "etabs_manifest",
    "guard_arguments",
    "guard_destructive",
    "guard_protocol",
    "guard_verified",
    "has",
    "install",
    "is_destructive",
    "load_dispatch",
    "native_steps",
    "partial_operations",
    "plan_for",
    "plans_for_tool",
    "policies_for_instances",
    "registered_dispatch_entry_points",
    "status_of",
    "tools",
    "transformer_for",
    "unknown_codes",
    "verify_traceable",
]


def install(
    manager: AdapterManager,
    *,
    adapter: EtabsAdapter | None = None,
    factory: AdapterFactory | None = None,
    dispatch_loader: DispatchLoader | None = None,
) -> AdapterManifest:
    """把 ETABS Adapter 注册进既有 `AdapterManager`（`docs/07` §12 P127；见裁决 1–3）。

    Args:
        manager: 既有 Adapter 管理器（Core 的进程级对象）。
        adapter: 注册原型；缺省为 `EtabsAdapter()`（**未**注入 dispatch，见裁决 2）。
        factory: 为每个软件实例创建 Adapter 实例的工厂；给了 `factory` 时**不**再
            经 entry point 发现（部署方显式装配优先）。
        dispatch_loader: 可注入的派发加载器；缺省 `dispatch.load_dispatch`
            （entry point group = `structai.adapters.etabs.dispatch`，见裁决 2）。

    Returns:
        已校验的 `AdapterManifest`（`vendor=CSI` / `product=ETABS`）。

    Raises:
        InternalError: `STRUCTAI-7000` —— Manifest 校验失败，或同一
            `(vendor, product)` 重复注册（`docs/02` §19）。
        EtabsConnectionError: `STRUCTAI-2000` —— entry point 存在但加载失败
            （`dispatch.py` 裁决 5；**不**回显第三方异常 message）。
    """
    if adapter is not None:
        return manager.register(adapter, factory=factory)
    loader: DispatchLoader = dispatch_loader if dispatch_loader is not None else load_dispatch
    if factory is not None:
        return manager.register(EtabsAdapter(), factory=factory)
    # 见裁决 2：缺省路径**先**发现部署方注册的 entry point；发现不到即构造
    # 「未注入 dispatch」的 Adapter（`connect()` 时明确失败，**不**伪造连接）。
    dispatch = loader()
    return manager.register(EtabsAdapter(dispatch=dispatch))
