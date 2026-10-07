"""Infrastructure · Adapters · CSI ETABS · Adapter —— 适配器实现（`docs/07` §12 P127）。

权威来源
--------
- `docs/07` §12 P127 —— 实现 `EngineeringSoftwareAdapter` 的**八个**方法，
  继承 `BaseAdapter`，Manifest 走既有 `validate()`，注册进**既有** `AdapterManager`。
- `docs/04` §154（第二软件接入原则）—— 接入 ETABS **不**修改 9 MCP Tools / Task Engine /
  RBAC / MCP Session / Core Execution Pipeline；只增加 Adapter / Registry / Schema /
  Transformer / Capability Mapping / Contract Test。
- `docs/02` §88 L7602–7612 / `docs/03` §106 L3173–3181 —— `ANALYSIS.STATIC` → `COM RunAnalysis`。

落地裁决（只补实现手段，不改契约）
--------------------------------
1. **一个类、一条可追溯映射**：本 Adapter 只服务 `catalogue.CATALOGUE` 里的 Operation
   （本批恰好 `ANALYSIS.STATIC`）。其余 Operation **先**在能力阶段抛
   `STRUCTAI-3000`（`details.stage = "capability"`），**零** transport 调用 ——
   **不**静默成功、**不**回落（`docs/07` §16 R63 / R76 的同一口径）。
2. **`cancel()` 明确失败**：本仓库**没有**任何 ETABS 取消方法的事实依据，故**不**伪造取消
   （`docs/07` §14.4 / `docs/02` §30）—— 抛 `STRUCTAI-3000`
   （`details.reason = "cancel_not_supported"`），由 Core 的取消路径按 R48 保留
   `CANCEL_REQUESTED`。
3. **`allow_partial` 只服务 Contract / E2E 模式**：生产路径下
   `verification_status != VERIFIED` 一律拒绝（`docs/07` §16 R78）；本批的条目是
   `PARTIAL`，因此**生产路径拒绝**、L3 层（Mock Transport）放行 —— 该开关**不**改任何
   `verification_status` 取值。
4. **版本来自实例声明且**严格精确**：连接配置里的 `version` 必须在
   `supported_versions`（`("22",)`）内，否则 `STRUCTAI-1200`
   （`details.reason = "version_not_supported"`）—— **不**回落「最新版本」。
5. **原生派发必须注入**：本仓库**不**引入 COM 依赖（`docs/07` §3.1 技术栈冻结），
   故未注入 `dispatch` 时 `connect()` 明确失败为 `STRUCTAI-2000`
   （`details.reason = "dispatch_not_configured"`）—— **不**伪造连接、**不**静默降级。

分层红线：只依赖标准库、`app.domain`、Adapter 基座与同包的
`catalogue.py` / `capabilities.py` / `operations.py` / `client.py` / `lifecycle.py` /
`transforms.py` / `health.py` / `manifest.py` / `errors.py` / `hardening.py`；
**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖
`app.interfaces` / `app.application`，**不**写数据库。
"""

from __future__ import annotations

from typing import Any, ClassVar

from app.infrastructure.adapters.base.adapter import BaseAdapter
from app.infrastructure.adapters.etabs.capabilities import capability_codes
from app.infrastructure.adapters.etabs.client import DEFAULT_BUDGET_SECONDS, EtabsComClient
from app.infrastructure.adapters.etabs.errors import (
    EtabsCapabilityError,
    EtabsConnectionError,
    EtabsValidationError,
)
from app.infrastructure.adapters.etabs.health import EtabsHealthChecker
from app.infrastructure.adapters.etabs.lifecycle import (
    CREDENTIAL_REFERENCE_KEY,
    ComDispatch,
    ComSession,
    CredentialProviderLike,
)
from app.infrastructure.adapters.etabs.manifest import (
    ETABS_ADAPTER_NAME,
    ETABS_CAPABILITIES,
    ETABS_PRODUCT,
    ETABS_PROTOCOLS,
    ETABS_SUPPORTED_VERSIONS,
    ETABS_VENDOR,
)
from app.infrastructure.adapters.etabs.transforms import transformer_for

__all__ = ["EtabsAdapter"]


class EtabsAdapter(BaseAdapter):
    """CSI ETABS 适配器（`docs/07` §12 P127；`docs/04` §154）。"""

    name: ClassVar[str] = ETABS_ADAPTER_NAME
    vendor: ClassVar[str] = ETABS_VENDOR
    product: ClassVar[str] = ETABS_PRODUCT
    supported_versions: ClassVar[tuple[str, ...]] = ETABS_SUPPORTED_VERSIONS
    protocols: ClassVar[tuple[str, ...]] = ETABS_PROTOCOLS
    capabilities: ClassVar[tuple[str, ...]] = ETABS_CAPABILITIES

    def __init__(
        self,
        *,
        dispatch: ComDispatch | None = None,
        credential_provider: CredentialProviderLike | None = None,
        credential_reference: str = "",
        allow_partial: bool = False,
        version: str = "",
        budget_seconds: float = DEFAULT_BUDGET_SECONDS,
    ) -> None:
        """构造（**不**做 I/O；见裁决 3 / 5）。"""
        super().__init__()
        self._dispatch = dispatch
        self._credentials = credential_provider
        self._configured_reference = str(credential_reference)
        self._allow_partial = bool(allow_partial)
        self._configured_version = str(version)
        self._budget_seconds = float(budget_seconds)
        self._declared_version = ""
        self._session = ComSession(
            dispatch,
            credential_provider=credential_provider,
            credential_reference=self._configured_reference,
        )
        self._client: EtabsComClient | None = None

    # ===== 诊断（只读）=====

    @property
    def allow_partial(self) -> bool:
        """是否处于 Contract / E2E 模式（见裁决 3）。"""
        return self._allow_partial

    @property
    def client(self) -> EtabsComClient | None:
        """已装配的 COM 客户端（未连接时为 `None`；诊断 / 验收断言用）。"""
        return self._client

    @property
    def session(self) -> ComSession:
        """COM 会话（只读用途；**不含**凭据值）。"""
        return self._session

    @property
    def declared_version(self) -> str:
        """实例声明的软件版本（探测不到即空串；`health.py` 裁决 3）。"""
        return self._declared_version

    # ===== 生命周期（`docs/02` §10 / §54）=====

    async def _connect(self, config: dict[str, Any]) -> None:
        """建立 COM 会话（`docs/02` §54；见裁决 4 / 5）。

        Raises:
            EtabsValidationError: `STRUCTAI-1200`，版本不在声明集合内。
            EtabsConnectionError: `STRUCTAI-2000`，未注入 dispatch / 原生 attach 失败。
        """
        version = str(config.get("version") or self._configured_version or "")
        if version and version not in ETABS_SUPPORTED_VERSIONS:
            raise EtabsValidationError(
                "version_not_supported",
                version=version,
                declared=list(ETABS_SUPPORTED_VERSIONS),
            )
        self._declared_version = version
        reference = str(config.get(CREDENTIAL_REFERENCE_KEY) or self._configured_reference)
        await self._session.configure(reference)
        await self._session.attach()
        dispatch = self._dispatch
        if dispatch is None:  # pragma: no cover - `attach()` 已保证非空
            raise EtabsConnectionError("dispatch_not_configured")
        self._client = EtabsComClient(dispatch, budget_seconds=self._budget_seconds)

    async def _disconnect(self) -> None:
        """释放 COM 会话（幂等；**不**缓存任何凭据）。"""
        self._client = None
        await self._session.detach()

    async def get_version(self) -> str:
        """软件版本（见裁决 4：只回实例声明，探测不到即空串）。"""
        return self._declared_version

    async def get_capabilities(self) -> list[str]:
        """运行时能力清单（`docs/07` §16 R30 / R38；能力码取自落库的 41 条词表）。"""
        if not self._session.attached:
            return []
        return list(capability_codes())

    async def health_check(self) -> dict[str, Any]:
        """健康检查（`docs/02` §25 的四键形状；见 `health.py`）。"""
        self._last_health = await EtabsHealthChecker(
            self._session, version=self._declared_version
        ).check()
        return dict(self._last_health)

    async def cancel(self, task_id: str) -> None:
        """**明确失败**：本仓库没有 ETABS 取消方法的事实依据（见裁决 2）。

        Raises:
            EtabsCapabilityError: `STRUCTAI-3000`，`details.reason = "cancel_not_supported"`。
        """
        raise EtabsCapabilityError("cancel_not_supported", task_id=str(task_id))

    # ===== 执行（`docs/02` §32 / §48）=====

    async def execute(
        self,
        operation: str,
        parameters: dict[str, Any],
        context: Any,
    ) -> dict[str, Any]:
        """执行一个规范化 Operation（`docs/02` §32；见裁决 1）。

        Args:
            operation: 规范化 Operation 名（如 `ANALYSIS.STATIC`）——**不是**原生方法名。
            parameters: 规范化参数（`docs/02` §24 的 `input_schema` 口径）。
            context: 执行上下文（Adapter 只经 `adapter_context_from()` 取用）。

        Returns:
            规范化结果（`docs/02` §33 / §89）：`operation` / `protocol` / `method` /
            `analysis_type` / `completed` / `arguments` / `native_payload` /
            `native_keys` / `verification_status` + `adapter` / `product`。

        Raises:
            EtabsCapabilityError: `STRUCTAI-3000` —— Operation 不在 catalogue（能力阶段，
                **零** transport 调用）或 Adapter 未连接。
            EtabsValidationError: `STRUCTAI-1200` —— 参数未覆盖 / 破坏性形态。
            StructAIError: 由 `execute_normalized()` 归一化后的 20 码异常。
        """
        transformer = transformer_for(str(operation))
        client = self._require_client()
        arguments = transformer.request_to_native(dict(parameters))
        request = client.build_request(
            transformer.entry,
            operation=str(operation),
            arguments=arguments,
            allow_partial=self._allow_partial,
        )
        invocation = await client.send(request)
        result = transformer.result_from_native(invocation)
        result["adapter"] = self.name
        result["product"] = self.product
        return result

    def _require_client(self) -> EtabsComClient:
        """取客户端（未连接 → `STRUCTAI-3000`）。"""
        if self._client is None:
            raise EtabsCapabilityError("adapter_not_connected")
        return self._client
