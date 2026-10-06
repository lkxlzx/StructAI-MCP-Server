"""Application · Services · AdapterResolver（`docs/02` §87 / §13 / §56 / §48）。

权威来源
--------
- `docs/02` §87（`adapter`）—— 解析链：`Software Instance → Vendor/Product/Version →
  Adapter Manifest → Capability → API Registry → Adapter`。本模块落地**前四段**
  （最后两段由 P19–P20 的 Adapter 实现持有）。
- `docs/02` §13（`adapter`）—— `AdapterResolver` 的接口职责：把一个**已解析**的软件实例
  映射到一个 Adapter 实例。
- `docs/02` §56（`adapter`）—— `resolve_for_instance(software_instance_id)`：实例未加载
  Adapter 时必须**明确失败**，不得静默回落。
- `docs/02` §48（`exec`）—— **不得泄露存在性**：错误 `details` 里**不**回显任何实例标识。
- `docs/07` §12 P35 / §16 R35 —— 该条目的验收要求：未知实例 / 未绑定 Adapter 落
  `STRUCTAI-3000`，且 `details` 不含实例标识。
- `docs/07` §9 第 7 / 16 步 —— 资源解析（含租户边界）**先于**能力判定：本模块消费的是
  已解析的实例，且能力判定复用 P14–P18 的 `CapabilityResolver`（同一层，可安全导入）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **来源是 Domain 的 `AdapterResolverSource` 收窄契约**（`docs/02` §87 / §56）：
   Application 层**不得**依赖 `app.infrastructure`（`docs/07` §14.1），故这里只声明三个
   问题（`adapter_for_instance` / `resolve_for_instance` / `registered_keys`）。
   Core Alpha 由 P19–P20 的 `AdapterManager` **结构上**满足它（**不**触碰其私有属性）。
2. **实例来源是本地收窄契约 `InstanceLookup`**：`vendor` / `product` / `version` 取自
   `docs/02` §19 的实例记录（`SoftwareInstanceRecord`）。`app.domain.protocols.ResourceStore`
   **结构上**即满足 `InstanceLookup`（同名同签名的 `software_instance`），因此不需要适配器。
3. **未注入实例来源 → `STRUCTAI-3000`**：`AdapterResolution` 必须携带
   `vendor` / `product` / `version`（`docs/02` §87 的第二段），而这三个值只来自实例记录。
   没有实例来源就无法诚实地填这三个字段，故 `resolve()` 直接落 `adapter_unavailable`
   —— 宁可明确失败，也不回填空串（见模块裁决 4）。
4. **「不存在」与「未绑定」共用同一个错误、且不含实例标识**（`docs/02` §48；R35）：
   未知实例、未绑定 Adapter、Adapter 解析抛错，三者一律落
   `CapabilityError`（`STRUCTAI-3000`）且
   `details = {"stage": "adapter_resolver", "reason": "adapter_unavailable"}`
   —— **没有** `instance_id` / `vendor` / `product` 等可识别值（不泄露存在性）。
   判定语义上也正确：一个解析不出 Adapter 的实例**不可能**具备该操作要求的能力。
5. **Adapter 查找：先同步绑定、再异步解析**（`docs/02` §56）：先问
   `adapter_for_instance()`（同步、已绑定），取不到再 `await resolve_for_instance()`
   （可能加载）。两条路径都失败 → `adapter_unavailable`。本模块**不**缓存 Adapter：
   绑定 / 卸载是 P19–P20 的职责，缓存会引入陈旧引用。
6. **「未绑定」的两种结构信号都接受**：`AdapterResolverSource.adapter_for_instance` 的
   类型是 `object | None`，而 Core Alpha 的 `AdapterManager` 在未绑定时**抛**
   `AdapterNotFoundError`（`docs/02` §56 的明确失败口径）。`vendor_product_for()` 因此
   把「返回 `None`」与「抛出」都当作**未绑定**，并**永不**向外抛（R35 的断言要求）。
7. **`vendor_product_for()` 读的是已绑定 Adapter 的 Manifest 键**：`docs/02` §87 的第三段
   是 Adapter Manifest，而 `AdapterManager` 的 Manifest 恰好带 `vendor` / `product`
   （注册键 `(vendor, product)`，`docs/02` §14）。故本方法从
   `adapter_for_instance()` 返回的 Adapter 的 `manifest` 读这两个字段；未绑定 / 读不到 →
   `None`（**不**回退到实例记录的字段 —— 那会回答「实例声明了什么」而不是
   「Adapter 声明了什么」，是两个问题）。
8. **能力判定只在调用方给出 `operation` 时执行**（`docs/02` §46 / §87 第四段）：
   能力判定本身属 `CapabilityResolver`（P14–P18，**一处实现**）；本模块只按
   `operation.required_capabilities` 逐个 `require()`。未注入 `capabilities` 或未给
   `operation` 时跳过 —— 装配期查表不需要能力判定。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库、`app.domain` 与**同层**的
`app.application.services.capability_resolver`：**不**引用 SQLAlchemy / FastAPI /
MCP SDK / httpx，**不**依赖 `app.infrastructure`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Protocol

from app.application.services.capability_resolver import CapabilityResolver
from app.domain.errors import CapabilityError
from app.domain.protocols import (
    AdapterResolverSource,
    OperationDefinition,
    SoftwareInstanceRecord,
)

__all__ = [
    "ADAPTER_RESOLVER_STAGE",
    "AdapterResolution",
    "AdapterResolver",
    "InstanceLookup",
]

ADAPTER_RESOLVER_STAGE: Final[str] = "adapter_resolver"
"""本模块所有异常 `details["stage"]` 的固定取值（`docs/07` §11 的诊断口径）。"""


class InstanceLookup(Protocol):
    """软件实例读取契约（`docs/02` §12 / §19 / §21）。

    `app.domain.protocols.ResourceStore` **结构上**即满足它（同名同签名的
    `software_instance(instance_id)`），因此不需要适配器 —— Application 只依赖收窄后的
    结构，不依赖 Infrastructure（`docs/07` §14.1）。
    """

    async def software_instance(self, instance_id: str) -> SoftwareInstanceRecord | None:
        """按主键读取实例快照；不存在返回 `None`。"""
        ...


@dataclass(frozen=True, slots=True)
class AdapterResolution:
    """一次 Adapter 解析的结果（`docs/02` §87 的前四段，逐字段照抄语义）。

    Attributes:
        software_instance_id: 软件实例标识（已解析）。
        vendor: 厂商（`docs/02` §87 第二段）。
        product: 产品（第二段）。
        version: 版本（第二段）。
        adapter: 绑定到该实例的 Adapter 实例（第三 / 四段；类型由实现决定）。
    """

    software_instance_id: str
    vendor: str
    product: str
    version: str
    adapter: object


class AdapterResolver:
    """实例 → Adapter 的解析（`docs/02` §87 / §13 / §56；`docs/07` §16 R35）。

    ⚠️ 本服务只**解析**：不连接、不调用 Adapter 的业务方法、不写表、不 `commit` /
    `rollback`（`docs/07` §14.4）。错误 `details` **不**泄露实例存在性（见模块裁决 4）。
    """

    def __init__(
        self,
        source: AdapterResolverSource,
        *,
        instances: InstanceLookup | None = None,
        capabilities: CapabilityResolver | None = None,
    ) -> None:
        """绑定 Adapter 来源、实例来源与能力判定入口。

        Args:
            source: 满足 `app.domain.protocols.AdapterResolverSource` 的来源
                （Core Alpha 由 P19–P20 的 `AdapterManager` 结构性满足）。
            instances: 实例读取来源（`ResourceStore` 结构性满足）；`None` 时 `resolve()`
                落 `adapter_unavailable`（见模块裁决 3）。
            capabilities: 能力判定服务（P14–P18，同一层）；仅在同时给出 `operation` 时使用。
        """
        self._source = source
        self._instances = instances
        self._capabilities = capabilities

    @property
    def source(self) -> AdapterResolverSource:
        """Adapter 来源（只读用途）。"""
        return self._source

    @property
    def instances(self) -> InstanceLookup | None:
        """实例读取来源；未注入时为 `None`。"""
        return self._instances

    @property
    def capabilities(self) -> CapabilityResolver | None:
        """能力判定服务；未注入时为 `None`。"""
        return self._capabilities

    # ===== 解析（`docs/02` §87）=====

    async def resolve(
        self,
        *,
        software_instance_id: str,
        operation: OperationDefinition | None = None,
    ) -> AdapterResolution:
        """走 `docs/02` §87 的解析链（见模块裁决 3 / 4 / 5 / 8）。

        Args:
            software_instance_id: 已解析的软件实例标识（租户边界由 `ResourceResolver`
                负责，`docs/07` §9 第 7 步）。
            operation: 可选的操作定义；给出且注入了 `capabilities` 时，逐个
                `require()` 其 `required_capabilities`（`docs/02` §46 的 ALL 语义）。

        Returns:
            `AdapterResolution`（实例标识 + 厂商 / 产品 / 版本 + Adapter）。

        Raises:
            CapabilityError: `STRUCTAI-3000`，实例取不到、Adapter 未绑定 / 解析失败
                （`details = {stage: "adapter_resolver", reason: "adapter_unavailable"}`，
                **不含**实例标识）；能力判定不通过时由 `CapabilityResolver` 抛出它自己的
                `STRUCTAI-3000`。
        """
        target = str(software_instance_id)
        instance = await self._instance(target)
        if instance is None:
            raise _unavailable()
        adapter = await self._adapter(target)
        if adapter is None:
            raise _unavailable()

        if operation is not None and self._capabilities is not None:
            for capability in operation.required_capabilities:
                await self._capabilities.require(target, str(capability))

        return AdapterResolution(
            software_instance_id=target,
            vendor=str(instance.vendor),
            product=str(instance.product),
            version=str(instance.version),
            adapter=adapter,
        )

    def vendor_product_for(self, software_instance_id: str) -> tuple[str, str] | None:
        """已绑定 Adapter 的 Manifest 注册键（`docs/02` §87 / §14；见模块裁决 6 / 7）。

        Args:
            software_instance_id: 软件实例标识。

        Returns:
            `(vendor, product)`；未绑定 / 读不到 Manifest → `None`。
            **永不**抛出（R35 的断言要求）。
        """
        adapter = _call(lambda: self._source.adapter_for_instance(str(software_instance_id)))
        if adapter is None:
            return None
        manifest = getattr(adapter, "manifest", None)
        vendor = getattr(manifest, "vendor", None)
        product = getattr(manifest, "product", None)
        if vendor is None or product is None:
            return None
        return (str(vendor), str(product))

    def registered(self) -> tuple[tuple[str, str], ...]:
        """全部已注册的 Adapter 注册键（`docs/02` §14 / §56）。"""
        return tuple(
            (str(vendor), str(product)) for vendor, product in self._source.registered_keys()
        )

    # ===== 内部 =====

    async def _instance(self, instance_id: str) -> SoftwareInstanceRecord | None:
        """读取实例快照；未注入来源时返回 `None`（见模块裁决 3）。"""
        if self._instances is None:
            return None
        return await self._instances.software_instance(instance_id)

    async def _adapter(self, instance_id: str) -> object | None:
        """先同步绑定、再异步解析（`docs/02` §56；见模块裁决 5）。"""
        bound = _call(lambda: self._source.adapter_for_instance(instance_id))
        if bound is not None:
            return bound
        try:
            return await self._source.resolve_for_instance(instance_id)
        except Exception:  # 见模块裁决 4：解析失败统一落 adapter_unavailable
            return None


def _call(action: Callable[[], object | None]) -> object | None:
    """调用一个「未绑定即失败」的同步查找；抛出视同 `None`（见模块裁决 6）。"""
    try:
        return action()
    except Exception:  # 见模块裁决 6：未绑定的两种结构信号都接受
        return None


def _unavailable() -> CapabilityError:
    """构造 `STRUCTAI-3000`（`docs/07` §11 / §16 R35；见模块裁决 4）。

    ⚠️ `details` **只有** `stage` + `reason`：不含 `instance_id` / `vendor` / `product`
    （`docs/02` §48：不得泄露存在性）。
    """
    return CapabilityError(
        "Adapter not available for the software instance",
        details={"stage": ADAPTER_RESOLVER_STAGE, "reason": "adapter_unavailable"},
    )
