"""Application · Services · CapabilityResolver（`docs/07` §12 P14–P18；`docs/02` §43–§48）。

权威来源
--------
- `docs/02` §43（`exec`）—— Capability ≠ Operation：`ANALYSIS.STATIC` 需要同名能力，
  而 `BUILD.COLUMN` 需要 `MODEL.NODE.WRITE` + `MODEL.ELEMENT.WRITE`（多个）——
  因此 Resolver 必须支持**多个** capability。
- `docs/02` §44（`exec`）—— 接口：`check(context, operation) -> None`。
- `docs/02` §34 / §31（`blue` / `source9`）—— `supports(instance_id, capability) -> bool` /
  `require(software_instance_id, capability)`；能力来源 = `Static Manifest + Runtime Detection`。
- `docs/02` §45（`exec`）—— 能力来源链：`Software → Product → Version → Adapter →
  Runtime Capability`。
- `docs/02` §46（`exec`）—— 算法：`Operation → required_capabilities → Software Instance →
  Capability Cache → Runtime Detection → ALL required capabilities supported?`
  —— 是 **ALL**，不是 **ANY**。
- `docs/02` §47（`exec`）—— `UNKNOWN ≠ SUPPORTED`：`status != SUPPORTED` 一律拒绝。
- `docs/02` §48（`exec`）—— 缓存字段 `software_instance_id` / `product` / `version` /
  `capability` / `status` / `checked_at` / `expires_at` + `TTL`；
  **重新连接 / 版本变化必须 invalidate**。
- `docs/02` §12（`exec`）—— 软件实例的租户归属必须补齐，**不能允许跨租户实例被直接执行**
  （租户边界由 `ResourceResolver` 负责；本模块消费的是**已解析**的实例）。
- `docs/07` §9 第 16 步 —— `Capability Check`（**先于** `Task / Transaction`（17））。
- `docs/07` §11 —— 未知 / 不支持落 **`STRUCTAI-3000` Capability Not Supported**（20 码契约）。
- `docs/07` §14.2 —— 能力取值**不得**含厂商名；能力码只能来自 P07 落库的
  `capabilities`（41 条），**不得**在代码里另造。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **能力词表来自 Registry，不来自本模块的常量**：`docs/07` §12 P14–P18 门槛 ④ 明确
   「取值只来自 P07 落库的 `capabilities`（41 条），**不得**在代码里另造能力码」。
   因此本模块**不定义任何能力码常量**，只经 `CapabilityLookup` 契约读取
   `codes()` / `capabilities_for(operation)`（P08 的 `CapabilityRegistry` 结构上即满足，
   **不**触碰它的任何私有属性）。`unknown_codes(operations)` 提供装配期自检。
2. **`required_capabilities` 的权威是 `OperationDefinition`**（`docs/02` §24 第 7 个字段，
   P08 由 `operations` 表 + `OPERATION_PROFILES` 装配）。`required_for(operation)` 直接读它；
   `registry_required_for(name)` 读 Registry 关系，供**交叉核对**（两者必须一致，
   否则装配有漂移）。本模块**不**用 Registry 关系去覆盖 OperationDefinition。
3. **「静态支持」的判定口径**：`docs/02` §34 说能力来源 = `Static Manifest + Runtime Detection`；
   §45 的运行时检测要经 Adapter（P19–P20 才有）。本批因此把 `status_of()` 定义为
   **静态 Manifest 口径**：能力码在落库词表内（`capabilities`，权威静态清单）
   **且**实例状态为 `CONNECTED` → `SUPPORTED`；否则 `UNKNOWN`。
   **`UNKNOWN ≠ SUPPORTED`**（§47），因此一律拒绝。
   ⚠️ `UNSUPPORTED` 只在**运行时清单可得**时产出：`docs/02` §45 的 `UNSUPPORTED`（如
   「某软件不支持 `DESIGN.STEEL`」）来自 Adapter 的运行时能力清单（`get_capabilities()`）。
   未注入运行时来源时（P14–P18 口径）「说不清」一律落 `UNKNOWN`（更严格、且与 §47 的
   拒绝语义一致）；P19–P20 起由 `runtime=` 注入 Adapter 的运行时快照：
   **清单可得**且不含该能力 → `UNSUPPORTED`；**清单不可得**（未连接 / 未绑定）→ `UNKNOWN`。
   「探测不到」与「明确不支持」严格区分。接入点仍是同一个 `status_of()`（`docs/07` §16 R30）。
4. **`check()` 是 ALL 语义**（`docs/02` §46）：`required_capabilities` 中**任一**不是
   `SUPPORTED` 即拒绝，`details` 一次列全缺口 —— 便于诊断，而不是逐个报错。
5. **缓存键含 `product` + `version`**（`docs/02` §48）：版本变化必然 miss；
   `invalidate(instance_id)` 覆盖「重新连接」场景（§48 明列两种失效条件）。
6. **实例不可解析 → `STRUCTAI-3000`**：实例应在第 7 步由 `ResourceResolver` 解析
   （`docs/02` §12）。若此处仍取不到实例，它不可能被判定为「支持该能力」，
   故落 `CapabilityError` 并带 `reason = "software_instance_unresolved"`
   （**不**新增错误码；语义上属 3xxx 能力族）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`（含 `ResourceStore` 契约）：**不**引用 SQLAlchemy /
FastAPI / MCP SDK / httpx，**不**依赖 `app.infrastructure`，
也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, Protocol

from app.domain.enums import CapabilityStatus, SoftwareConnectionState
from app.domain.errors import CapabilityError, NotFoundError
from app.domain.protocols import OperationDefinition, SoftwareInstanceRecord

__all__ = [
    "DEFAULT_CAPABILITY_CACHE_SECONDS",
    "CapabilityDecision",
    "CapabilityLookup",
    "CapabilityResolver",
    "CapabilitySupport",
    "InstanceLookup",
    "RuntimeCapabilitySource",
]

DEFAULT_CAPABILITY_CACHE_SECONDS: Final[int] = 300
"""默认能力缓存 TTL（秒）。与 `Settings.capability_cache_seconds` 一致（`docs/07` §3.1）。"""

Clock = Callable[[], datetime]
"""可注入时钟（验收测试据此制造缓存过期）。"""


def _utc_now() -> datetime:
    """默认时钟：带时区的 UTC 当前时间。"""
    return datetime.now(UTC)


class CapabilityLookup(Protocol):
    """能力词表契约（`docs/02` §20 的 `CapabilityRegistry` 收窄形态）。

    P08 的 `CapabilityRegistry` **结构上**即满足本契约（`codes()` /
    `capabilities_for(operation)`），因此不需要适配器（与 P09 的 `SchemaLookup`
    同一做法：Application 只依赖收窄后的结构，不依赖 Infrastructure）。
    """

    def codes(self) -> Sequence[str]:
        """全部能力码（`capabilities` 表的权威集合）。"""
        ...

    def capabilities_for(self, operation: str) -> Sequence[str]:
        """某 Operation 依赖的能力码（`operation_capabilities` 关系）。"""
        ...


class InstanceLookup(Protocol):
    """软件实例读取契约（`docs/02` §19 / §21）。

    `app.domain.protocols.ResourceStore` 结构上即满足它。
    """

    async def software_instance(self, instance_id: str) -> SoftwareInstanceRecord | None:
        """按主键读取实例快照；不存在返回 `None`。"""
        ...


class RuntimeCapabilitySource(Protocol):
    """运行时能力来源契约（`docs/02` §21 / §23 / §57；`docs/07` §16 R30 的接入点）。

    `AdapterManager.runtime_capabilities(instance_id)` 结构上即满足它 ——
    Application 层因此**不**依赖 `app.infrastructure`（`docs/07` §14.1）。

    ⚠️ 必须区分「不可得」与「空集」：

    - `None` → **探测不到**（实例未绑定 Adapter / Adapter 未连接）→ 判定落 `UNKNOWN`；
    - `frozenset()` → 清单**可得**但为空 → 判定落 `UNSUPPORTED`。
    """

    def runtime_capabilities(self, instance_id: str) -> frozenset[str] | None:
        """该实例的运行时能力快照；不可得时返回 `None`。"""
        ...


@dataclass(frozen=True, slots=True)
class CapabilitySupport:
    """一条能力支持判定（`docs/02` §48 的缓存记录，逐字段照抄）。

    Attributes:
        instance_id: 软件实例标识。
        product: 软件产品（`docs/02` §45 来源链第二级）。
        version: 软件版本（第三级）。
        capability: 能力码。
        status: `CapabilityStatus`（`SUPPORTED` / `UNSUPPORTED` / `UNKNOWN`）。
        checked_at: 判定时刻（`docs/02` §48）。
        expires_at: 缓存到期时刻（`docs/02` §48 的 `TTL`）。
    """

    instance_id: str
    product: str
    version: str
    capability: str
    status: CapabilityStatus
    checked_at: datetime
    expires_at: datetime

    def is_expired(self, now: datetime) -> bool:
        """在 `now` 是否已过缓存期（`docs/02` §48 的 TTL）。"""
        return self.expires_at <= now


@dataclass(frozen=True, slots=True)
class CapabilityDecision:
    """一次能力判定的完整结果（`docs/02` §46）。

    Attributes:
        instance_id: 软件实例标识。
        product: 软件产品。
        version: 软件版本。
        capabilities: 逐能力判定（顺序 = `OperationDefinition.required_capabilities`）。
        cache_hits: 命中缓存的条数（诊断 / 验收证据）。
    """

    instance_id: str
    product: str
    version: str
    capabilities: tuple[CapabilitySupport, ...]
    cache_hits: int = 0

    @property
    def supported(self) -> tuple[str, ...]:
        """判定为 `SUPPORTED` 的能力码（保持判定顺序）。"""
        return tuple(
            item.capability
            for item in self.capabilities
            if item.status is CapabilityStatus.SUPPORTED
        )

    @property
    def unknown(self) -> tuple[str, ...]:
        """判定为 `UNKNOWN` 的能力码（`docs/02` §47：`UNKNOWN ≠ SUPPORTED`）。"""
        return tuple(
            item.capability for item in self.capabilities if item.status is CapabilityStatus.UNKNOWN
        )

    @property
    def missing(self) -> tuple[str, ...]:
        """**未**判定为 `SUPPORTED` 的能力码（ALL 语义下的缺口，`docs/02` §46）。"""
        return tuple(
            item.capability
            for item in self.capabilities
            if item.status is not CapabilityStatus.SUPPORTED
        )

    @property
    def unsupported(self) -> tuple[str, ...]:
        """判定为 `UNSUPPORTED` 的能力码（`docs/02` §45：清单明确不含该能力）。"""
        return tuple(
            item.capability
            for item in self.capabilities
            if item.status is CapabilityStatus.UNSUPPORTED
        )

    @property
    def ok(self) -> bool:
        """是否**全部**要求的能力都 `SUPPORTED`（`docs/02` §46 的 ALL 语义）。"""
        return not self.missing


class CapabilityResolver:
    """能力判定（`docs/02` §43–§48；`docs/07` §9 第 16 步）。

    ⚠️ 只做**判定**：不调用 Adapter、不写表、不 `commit`（`docs/07` §14.4）。
    Adapter 侧的运行时检测在 P19–P20 接入（见模块裁决 3）。
    """

    def __init__(
        self,
        registry: CapabilityLookup,
        instances: InstanceLookup | None = None,
        *,
        cache_ttl_seconds: int = DEFAULT_CAPABILITY_CACHE_SECONDS,
        clock: Clock | None = None,
        runtime: RuntimeCapabilitySource | None = None,
    ) -> None:
        """绑定能力词表、实例来源与缓存参数。

        Args:
            registry: 能力词表来源（P08 的 `CapabilityRegistry` 结构上满足
                `CapabilityLookup`）。**本模块不内置任何能力码**（见模块裁决 1）。
            instances: 软件实例来源；`None` 时 `check()` 必须由调用方显式传入
                `instance=`（避免隐式依赖）。
            cache_ttl_seconds: 缓存 TTL（秒）；调用方传 `settings.capability_cache_seconds`。
            clock: 可注入时钟；缺省带时区的 UTC 当前时间。
            runtime: **运行时**能力来源（`docs/02` §21 / §23 / §57）。缺省 `None` 时
                `status_of()` 只做静态判定（P14–P18 口径，**不**产出 `UNSUPPORTED`）；
                注入 `AdapterManager`（P19–P20）后，运行时清单可得即按清单区分
                `SUPPORTED` / `UNSUPPORTED`（见模块裁决 3）。
        """
        self._registry = registry
        self._instances = instances
        self._runtime = runtime
        self._cache_ttl_seconds = cache_ttl_seconds
        self._clock: Clock = clock or _utc_now
        self._cache: dict[tuple[str, str, str, str], CapabilitySupport] = {}
        self._known: frozenset[str] = frozenset(str(code) for code in registry.codes())

    @property
    def cache_ttl_seconds(self) -> int:
        """缓存 TTL（秒）。"""
        return self._cache_ttl_seconds

    @property
    def known(self) -> frozenset[str]:
        """已知能力码集合（`capabilities` 表的权威集合，`docs/02` §20）。"""
        return self._known

    # ===== 词表自检（见模块裁决 1 / 2）=====

    def unknown_codes(self, operations: Iterable[OperationDefinition]) -> tuple[str, ...]:
        """Registry 关系里出现、但不在 `capabilities` 里的能力码（升序）。

        `docs/07` §14.2 要求能力取值只来自落库词表；本方法给出**可断言**的自检入口：
        调用方传入 Operation 集合（通常是 `operation_registry` 的全量），
        返回其中的悬空能力码。

        Args:
            operations: 待核对的 Operation 定义集合。

        Returns:
            悬空能力码（升序）；空元组表示词表一致。
        """
        referenced: set[str] = set()
        for operation in operations:
            referenced.update(str(code) for code in self._registry.capabilities_for(operation.name))
        return tuple(sorted(referenced - self._known))

    def registry_required_for(self, operation: str) -> tuple[str, ...]:
        """Registry 关系声明的能力码（`docs/02` §27 / §31；供交叉核对）。"""
        return tuple(str(code) for code in self._registry.capabilities_for(operation))

    def required_for(self, operation: OperationDefinition) -> tuple[str, ...]:
        """该 Operation 要求的能力码（`docs/02` §46 第 1 步）。

        权威 = `OperationDefinition.required_capabilities`（`docs/02` §24 第 7 个字段，
        P08 装配）。**不**用 Registry 关系覆盖它（见模块裁决 2）。
        """
        return tuple(str(code) for code in operation.required_capabilities)

    def require_known(self, capability: str) -> str:
        """能力码必须在落库词表内，否则拒绝（`docs/07` §14.2；见模块裁决 1）。

        Raises:
            NotFoundError: 该码不在 `capabilities` 里（装配期查找失败口径，
                **不**携带 `STRUCTAI-xxxx`；见 `app/domain/errors.py`）。
        """
        code = str(capability)
        if code not in self._known:
            raise NotFoundError(f"Capability not found: {code}")
        return code

    # ===== 判定（`docs/02` §43–§48）=====

    def status_of(
        self,
        instance: SoftwareInstanceRecord,
        capability: str,
    ) -> CapabilityStatus:
        """单个能力的静态判定（`docs/02` §34 / §45 / §47；见模块裁决 3）。

        Args:
            instance: 已解析的软件实例快照（`docs/02` §19）。
            capability: 能力码。

        Returns:
            `SUPPORTED`（在落库词表内且实例已连接）或 `UNKNOWN`。
            **`UNKNOWN ≠ SUPPORTED`**（`docs/02` §47）。
        """
        code = str(capability)
        if code not in self._known:
            return CapabilityStatus.UNKNOWN
        if instance.status != SoftwareConnectionState.CONNECTED.value:
            return CapabilityStatus.UNKNOWN
        if self._runtime is None:
            return CapabilityStatus.SUPPORTED
        available = self._runtime.runtime_capabilities(instance.id)
        if available is None:
            return CapabilityStatus.UNKNOWN
        return CapabilityStatus.SUPPORTED if code in available else CapabilityStatus.UNSUPPORTED

    async def supports(
        self,
        instance_id: str,
        capability: str,
    ) -> bool:
        """`docs/02` §34 的 `supports(instance_id, capability)`。

        Returns:
            仅当判定为 `SUPPORTED` 时为 `True`（`UNKNOWN` 也是 `False`）。

        Raises:
            CapabilityError: `STRUCTAI-3000`，实例取不到（见模块裁决 6）。
        """
        instance = await self._load_instance(str(instance_id))
        return self.status_of(instance, capability) is CapabilityStatus.SUPPORTED

    async def require(
        self,
        software_instance_id: str,
        capability: str,
    ) -> None:
        """`docs/02` §31 的 `require(software_instance_id, capability)`。

        Raises:
            CapabilityError: `STRUCTAI-3000`，实例取不到，或该能力不是 `SUPPORTED`
                （`docs/07` §11）。
        """
        instance = await self._load_instance(str(software_instance_id))
        status = self.status_of(instance, capability)
        if status is not CapabilityStatus.SUPPORTED:
            raise self._unsupported(instance, (str(capability),), (status,))

    async def check(
        self,
        context: object,
        operation: OperationDefinition,
        *,
        instance: SoftwareInstanceRecord | None = None,
    ) -> CapabilityDecision:
        """ALL 语义的能力判定（`docs/02` §44 / §46；`docs/07` §9 第 16 步）。

        Args:
            context: `ExecutionContext`（只读取 `context.software.instance_id`）。
            operation: 操作定义（`docs/02` §24）。
            instance: 已解析的实例快照；缺省时经 `InstanceLookup` 读取。

        Returns:
            `CapabilityDecision`（全部 `SUPPORTED` 时 `ok is True`）。

        Raises:
            CapabilityError: `STRUCTAI-3000`（`docs/07` §11）—— 实例不可解析，
                或**任一**要求的能力不是 `SUPPORTED`（见模块裁决 4 / 6）。
        """
        resolved = instance
        if resolved is None:
            instance_id = _software_instance_id(context)
            if instance_id is None:
                raise CapabilityError(
                    "capability check requires a software instance",
                    details={
                        "stage": "capability",
                        "reason": "software_instance_unresolved",
                    },
                )
            resolved = await self._load_instance(str(instance_id))

        required = self.required_for(operation)
        now = self._clock()
        items: list[CapabilitySupport] = []
        cache_hits = 0
        for capability in required:
            item, hit = self._resolve_one(resolved, capability, now)
            items.append(item)
            cache_hits += 1 if hit else 0

        decision = CapabilityDecision(
            instance_id=resolved.id,
            product=resolved.product,
            version=resolved.version,
            capabilities=tuple(items),
            cache_hits=cache_hits,
        )
        if decision.missing:
            statuses = tuple(item.status for item in items if item.capability in decision.missing)
            raise self._unsupported(resolved, decision.missing, statuses)
        return decision

    # ===== 缓存（`docs/02` §48）=====

    def invalidate(self, instance_id: str | None = None) -> int:
        """使缓存失效（`docs/02` §48：重新连接 / 版本变化必须 invalidate）。

        Args:
            instance_id: 只失效该实例的条目；`None` 表示失效全部。

        Returns:
            被移除的条目数。
        """
        if instance_id is None:
            removed = len(self._cache)
            self._cache.clear()
            return removed
        target = str(instance_id)
        keys = [key for key in self._cache if key[0] == target]
        for key in keys:
            self._cache.pop(key, None)
        return len(keys)

    def cached_entries(self) -> int:
        """当前缓存条目数（诊断用）。"""
        return len(self._cache)

    # ===== 内部 =====

    def _resolve_one(
        self,
        instance: SoftwareInstanceRecord,
        capability: str,
        now: datetime,
    ) -> tuple[CapabilitySupport, bool]:
        """取一条判定，命中未过期缓存则复用（`docs/02` §48）。"""
        key = (instance.id, instance.product, instance.version, str(capability))
        cached = self._cache.get(key)
        if cached is not None and not cached.is_expired(now):
            return cached, True
        item = CapabilitySupport(
            instance_id=instance.id,
            product=instance.product,
            version=instance.version,
            capability=str(capability),
            status=self.status_of(instance, capability),
            checked_at=now,
            expires_at=now + timedelta(seconds=self._cache_ttl_seconds),
        )
        self._cache[key] = item
        return item, False

    async def _load_instance(self, instance_id: str) -> SoftwareInstanceRecord:
        """读取实例快照；取不到即拒绝（见模块裁决 6）。"""
        if self._instances is None:
            raise CapabilityError(
                "capability check requires an instance source or an explicit instance",
                details={
                    "stage": "capability",
                    "reason": "software_instance_unresolved",
                    "instance_id": instance_id,
                },
            )
        record = await self._instances.software_instance(instance_id)
        if record is None:
            raise CapabilityError(
                "software instance could not be resolved",
                details={
                    "stage": "capability",
                    "reason": "software_instance_unresolved",
                    "instance_id": instance_id,
                },
            )
        return record

    def _unsupported(
        self,
        instance: SoftwareInstanceRecord,
        missing: Sequence[str],
        statuses: Sequence[CapabilityStatus],
    ) -> CapabilityError:
        """构造 `STRUCTAI-3000`（`docs/07` §11）。

        `details` 只含实例标识 / 产品 / 版本 / 缺口能力码与状态 ——
        **不含**凭据、**不含**厂商专属 endpoint（`docs/07` §14.3 / §14.2）。
        """
        return CapabilityError(
            "Capability not supported",
            details={
                "stage": "capability",
                "instance_id": instance.id,
                "product": instance.product,
                "version": instance.version,
                "missing": list(missing),
                "statuses": [status.value for status in statuses],
            },
        )


def _software_instance_id(context: object) -> object | None:
    """取 `context.software.instance_id`（`docs/02` §3）。"""
    software = getattr(context, "software", None)
    return getattr(software, "instance_id", None)
