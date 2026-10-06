"""Infrastructure · Adapters · Base · Manager —— `AdapterManager`（注册 / 查找 / 连接）。

权威来源
--------
- `docs/02` §33（`source7`）—— `AdapterManager` 的职责：**注册 / 查找 / 连接实例 /
  断开实例 / 健康检查**。
- `docs/02` §12 / §13（`adapter`）—— `register(adapter)` 与 `resolve(...)`；
  未知 Adapter → `AdapterNotFoundError`。
- `docs/02` §14（`adapter`）—— 必须区分 Adapter Package / Adapter Instance /
  Software Instance 三者。
- `docs/02` §15（`adapter`）—— 建议新增 `adapter_instances` 表；⚠️ 本批**不得改表**
  （`docs/07` §14.3），见裁决 2。
- `docs/02` §52 / §53（`adapter`）—— `AdapterHealthManager.check(adapter)` 与
  「Health 隔离原则」：**一个实例挂掉 → Core 仍 READY，只有该实例 unhealthy**。
- `docs/02` §54 / §55（`adapter`）—— 启动 / 关闭序列（Connect → Health → Capability
  → READY；STOP → 拒绝新执行 → 等待 → 断开）。
- `docs/02` §56（`adapter`）—— `resolve_for_instance(software_instance_id)`：
  经软件仓储确认实例存在，再取已加载的 Adapter 实例。
- `docs/02` §57（`adapter`）—— Capability Resolver 的链路：
  `Core → AdapterManager → Adapter.get_capabilities()`。
- `docs/02` §48（`adapter`）—— 执行分派；无 handler → `AdapterCapabilityError`。
- `docs/07` §12 P19–P20 门槛 ②—— 按 `AdapterManifest` 注册 / 查找 / 连接 / 断开；
  同一 `(vendor, product)` **不**重复注册；**未知实例 → 明确失败（不静默回落）**；
  单实例失败**不得**让整个 Manager 不可用。
- `docs/07` §14.4 / §11 —— 单实例失败不拖垮服务器；错误一律落 20 码。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **注册键 = `(vendor, product)`，注册物 = 原型 + 工厂**：`docs/02` §13 的键含 `name`，
   但门槛 ② 明确「同一 `(vendor, product)` 不重复注册」，故以 `(vendor, product)` 为
   唯一键（`manifest_key()`）。`docs/02` §14 又要求区分「Adapter Instance」与
   「Software Instance」，§54 的启动序列含「Create Instances」——因此 `register()`
   同时记录**工厂**（缺省 `type(adapter)`，即要求无参构造；需注入依赖时显式传
   `factory`），`bind_instance()` 用工厂为**每个软件实例**创建**独立** Adapter 实例。
   这样两个软件实例不会共享原生会话 / 模型状态（Mock 的进程内 store 因此天然隔离）。
2. **Adapter Instance Registry 是进程内状态，不建表**：`docs/02` §15 建议新增
   `adapter_instances` 表，而 `docs/07` §14.3 禁止改表、§4.3 冻结的是 24 张表。
   与 R21（ACL 不建表）/ R25（实例租户归属不改表）同一口径：本批把注册与绑定落在
   进程内（`self._adapters` / `self._instances`）；需要持久化时以 Alembic 迁移新增表。
3. **未知实例 → 查找口径 `AdapterNotFoundError` / 执行口径 `STRUCTAI-3000`**：
   `docs/02` §13 / §56 用 `AdapterNotFoundError`；本模块把它实现为既有
   `app.domain.errors.NotFoundError` 的子类，**不**新增 `STRUCTAI-xxxx` 码
   （与 P08 对 `NotFoundError` 的裁决一致）。`resolve_for_instance()` 是装配 / 查找入口，
   按 §56 抛 `AdapterNotFoundError`；`execute()` 是**运行时**入口（流水线第 18 步，
   此前已在第 7 步通过资源解析、第 16 步通过能力检查），此处的「未绑定 / 未就绪」属
   「说不清」——按 R30 的 `UNKNOWN ≠ SUPPORTED` 一律落 **`STRUCTAI-3000`**，
   且 `details` **不**泄露实例存在性（`docs/02` §48）。
4. **能力来源 = Adapter 的运行时快照**：`runtime_capabilities(instance_id)` 是
   `CapabilityResolver.status_of()` 的接入点（`docs/07` §16 R30；`docs/02` §57）。
   未绑定 / 未连接 → `None` → 判定落 `UNKNOWN`（**不是** `UNSUPPORTED`）——
   「探测不到」与「明确不支持」严格区分（`docs/02` §21 / §47）。
5. **单实例失败隔离**：`connect()` / `disconnect()` / `execute()` / `detect_capabilities()`
   抛归一化异常（调用方必须知道失败），但 `connect_all()` / `disconnect_all()` /
   `health_check_all()` **永不**抛出 —— 逐实例收集结果（`docs/07` §14.4 / §02 §53）。
   失败同时记入 `instance_errors()`（**只**放归一化后的 20 码信封，不含原生 message /
   凭据）。
6. **连接配置只经内存传递**：`BoundInstance.config` 声明 `repr=False`，
   只用于 `connect()`，**绝不**落库 / 落日志 / 进 `instance_errors()`
   （`docs/07` §8.5 / §14.3）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库、`app.domain`、`app.application.execution.context` 与同层的
`adapters/base/*`。**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖
`app.interfaces`；软件实例来源以**结构化契约**注入（`SoftwareInstanceLookup`，
P08 的 `SoftwareRegistry` 结构上即满足），从而不把 Registry 实现绑进 Adapter 层。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final, NoReturn, Protocol

from app.application.execution.context import ExecutionContext
from app.domain.errors import CapabilityError, InternalError, NotFoundError, StructAIError
from app.infrastructure.adapters.base.adapter import AdapterState, EngineeringSoftwareAdapter
from app.infrastructure.adapters.base.errors import error_for, normalize_error
from app.infrastructure.adapters.base.manifest import AdapterManifest, manifest_key

__all__ = [
    "ADAPTER_ERROR_STAGE",
    "AdapterFactory",
    "AdapterHealthManager",
    "AdapterManager",
    "AdapterNotFoundError",
    "BoundInstance",
    "SoftwareInstanceLike",
    "SoftwareInstanceLookup",
]

ADAPTER_ERROR_STAGE: Final[str] = "adapter_manager"
"""归一化错误 / 装配期异常的 `details.stage`（便于诊断定位）。"""


class AdapterNotFoundError(NotFoundError):
    """未找到已注册 / 已绑定的 Adapter（`docs/02` §13 / §56）。

    ⚠️ **不**携带 `STRUCTAI-xxxx`、**不**继承 `StructAIError`（与 P08 对
    `NotFoundError` 的裁决一致，见裁决 3）：它是**装配 / 查找**口径的失败信号，
    运行时入口（`execute()`）会把它转成 `STRUCTAI-3000`，**不**让它进 MCP 错误信封。
    """


class SoftwareInstanceLike(Protocol):
    """`docs/02` §56 读取的软件实例视图（P08 的 `SoftwareInstanceView` 结构上即满足）。

    成员一律声明为**只读属性**：实现通常是 frozen dataclass（`SoftwareInstanceView`
    即 frozen + slots），而「只读视图」与「可写属性」在类型层面并不兼容；
    `AdapterManager` 只需要读，故按只读声明。
    """

    @property
    def instance_id(self) -> str: ...

    @property
    def vendor(self) -> str: ...

    @property
    def product(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def status(self) -> str: ...


class SoftwareInstanceLookup(Protocol):
    """软件实例读取契约（`docs/02` §19 / §56 的 `software_repository.get_instance`）。

    P08 的 `SoftwareRegistry` 结构上即满足它（`get_instance`）。
    """

    async def get_instance(self, instance_id: str) -> SoftwareInstanceLike | None:
        """按实例 id 读取；不存在返回 `None`。"""
        ...


AdapterFactory = Callable[[], EngineeringSoftwareAdapter]
"""按需创建 Adapter 实例的工厂（`docs/02` §54 的「Create Instances」）。"""


@dataclass(slots=True)
class BoundInstance:
    """一条「软件实例 ↔ Adapter 实例」绑定（`docs/02` §14）。

    ⚠️ `config` 可能含凭据：声明 `repr=False`，**绝不**进日志 / 审计 / 错误信封
    （`docs/07` §8.5 / §14.3）。
    """

    instance_id: str
    vendor: str
    product: str
    adapter: EngineeringSoftwareAdapter
    config: dict[str, Any] = field(default_factory=dict, repr=False)


class AdapterHealthManager:
    """健康检查隔离器（`docs/02` §52 / §53）。

    一个实例挂掉 → Core 仍 READY，只有该实例 `unhealthy`（`docs/07` §14.4）。
    """

    async def check(self, adapter: EngineeringSoftwareAdapter) -> dict[str, Any]:
        """检查单个 Adapter；**永不**抛出（`docs/02` §52）。

        Args:
            adapter: 待检查的 Adapter。

        Returns:
            Adapter 自己的健康结果；异常时返回
            `{"healthy": False, "state": "ERROR", "error": {"type": <异常类名>}}`
            （§52 的形状）——只带**类名**，**不**回显原生 message / 凭据。
        """
        try:
            health = await adapter.health_check()
        except Exception as error:
            return {
                "healthy": False,
                "state": AdapterState.ERROR.value,
                "error": {"type": type(error).__name__},
            }
        return {str(key): value for key, value in health.items()}


class AdapterManager:
    """Adapter 管理器（`docs/02` §33 / §12–§14 / §52–§57；门槛 ②）。

    ⚠️ 只做注册 / 查找 / 生命周期 / 健康 / 能力快照与执行转发：**不**写表、
    **不** `commit`（`docs/07` §14.4）、**不**做权限与租户判定（那是流水线第 7 / 11 步）。
    """

    def __init__(
        self,
        *,
        software: SoftwareInstanceLookup | None = None,
        health: AdapterHealthManager | None = None,
    ) -> None:
        """装配管理器（**不**做任何 I/O，也**不**连接任何实例）。

        Args:
            software: 软件实例读取契约（`docs/02` §56）；缺省时
                `resolve_for_instance()` 只查本地绑定。
            health: 健康检查隔离器；缺省为 `AdapterHealthManager()`。
        """
        self._adapters: dict[tuple[str, str], EngineeringSoftwareAdapter] = {}
        self._manifests: dict[tuple[str, str], AdapterManifest] = {}
        self._factories: dict[tuple[str, str], AdapterFactory] = {}
        self._instances: dict[str, BoundInstance] = {}
        self._errors: dict[str, dict[str, Any]] = {}
        self._software = software
        self._health = health or AdapterHealthManager()

    # ===== 注册 / 查找（`docs/02` §12 / §13）=====

    def register(
        self,
        adapter: EngineeringSoftwareAdapter,
        *,
        factory: AdapterFactory | None = None,
    ) -> AdapterManifest:
        """注册 Adapter（`docs/02` §12 / §54；门槛 ②）。

        Args:
            adapter: Adapter 原型（其 `manifest` 会被校验，`docs/02` §19）。
            factory: 为每个软件实例创建 Adapter 实例的工厂；缺省 `type(adapter)`
                （即要求无参构造，见裁决 1）。

        Returns:
            已校验的 `AdapterManifest`。

        Raises:
            InternalError: `STRUCTAI-7000` —— Manifest 校验失败（`docs/02` §19），
                或同一 `(vendor, product)` 重复注册（门槛 ②）。
        """
        manifest = adapter.manifest.validate()
        key = manifest_key(manifest)
        if key in self._adapters:
            raise InternalError(
                "Adapter is already registered",
                details={
                    "stage": ADAPTER_ERROR_STAGE,
                    "vendor": manifest.vendor,
                    "product": manifest.product,
                },
            )
        self._adapters[key] = adapter
        self._manifests[key] = manifest
        self._factories[key] = factory or type(adapter)
        return manifest

    def unregister(self, *, vendor: str, product: str) -> None:
        """注销 Adapter（`docs/02` §12）。

        Raises:
            AdapterNotFoundError: 该 `(vendor, product)` 未注册。
            InternalError: 仍有软件实例绑定在它上面（先 `unbind_instance()`）。
        """
        key = (str(vendor), str(product))
        if key not in self._adapters:
            raise AdapterNotFoundError(f"Adapter not found: {key}")
        bound = sorted(
            binding.instance_id
            for binding in self._instances.values()
            if (binding.vendor, binding.product) == key
        )
        if bound:
            raise InternalError(
                "Adapter is still bound to software instances",
                details={"stage": ADAPTER_ERROR_STAGE, "instances": bound},
            )
        self._adapters.pop(key, None)
        self._manifests.pop(key, None)
        self._factories.pop(key, None)

    def resolve(self, *, vendor: str, product: str) -> EngineeringSoftwareAdapter:
        """按 `(vendor, product)` 查找已注册的 Adapter 原型（`docs/02` §13）。

        Raises:
            AdapterNotFoundError: 未注册 —— **不**静默回落（门槛 ②）。
        """
        key = (str(vendor), str(product))
        adapter = self._adapters.get(key)
        if adapter is None:
            raise AdapterNotFoundError(f"Adapter not found: {key}")
        return adapter

    def manifests(self) -> tuple[AdapterManifest, ...]:
        """全部已注册的 Manifest（按 `(vendor, product)` 升序，输出确定性）。"""
        return tuple(self._manifests[key] for key in sorted(self._manifests))

    def registered_keys(self) -> tuple[tuple[str, str], ...]:
        """全部已注册的注册键（按 `(vendor, product)` 升序）。"""
        return tuple(sorted(self._adapters))

    # ===== 实例绑定（`docs/02` §14 / §54；见裁决 1 / 2）=====

    def bind_instance(
        self,
        instance_id: str,
        *,
        vendor: str,
        product: str,
        config: Mapping[str, Any] | None = None,
    ) -> EngineeringSoftwareAdapter:
        """把一个软件实例绑定到**独立的** Adapter 实例（`docs/02` §14 / §54）。

        Args:
            instance_id: 软件实例标识（`docs/02` §12）。
            vendor: 厂商（注册键的一部分）。
            product: 产品（注册键的一部分）。
            config: 连接配置；只经内存传递（见裁决 6）。

        Returns:
            新建（或既有）的 Adapter 实例。

        Raises:
            AdapterNotFoundError: `(vendor, product)` 未注册（**不**静默回落）。
            InternalError: 该实例已绑定到**另一个** `(vendor, product)`。
        """
        target = str(instance_id)
        key = (str(vendor), str(product))
        if key not in self._factories:
            raise AdapterNotFoundError(f"Adapter not found: {key}")

        existing = self._instances.get(target)
        if existing is not None:
            if (existing.vendor, existing.product) != key:
                raise InternalError(
                    "Software instance is already bound to another adapter",
                    details={
                        "stage": ADAPTER_ERROR_STAGE,
                        "instance_id": target,
                        "vendor": existing.vendor,
                        "product": existing.product,
                    },
                )
            return existing.adapter

        adapter = self._factories[key]()
        self._instances[target] = BoundInstance(
            instance_id=target,
            vendor=key[0],
            product=key[1],
            adapter=adapter,
            config=dict(config or {}),
        )
        return adapter

    def unbind_instance(self, instance_id: str) -> bool:
        """解除绑定（**不**断开；调用方应先 `disconnect()`）。

        Returns:
            是否真的移除了一个绑定。
        """
        target = str(instance_id)
        self._errors.pop(target, None)
        return self._instances.pop(target, None) is not None

    def bound_instance_ids(self) -> tuple[str, ...]:
        """全部已绑定的软件实例标识（升序，输出确定性）。"""
        return tuple(sorted(self._instances))

    def instances(self) -> tuple[BoundInstance, ...]:
        """全部绑定记录（按实例标识升序）。"""
        return tuple(self._instances[key] for key in sorted(self._instances))

    def adapter_for_instance(self, instance_id: str) -> EngineeringSoftwareAdapter:
        """取已绑定的 Adapter（同步查找口径）。

        Raises:
            AdapterNotFoundError: 未绑定（见裁决 3）。
        """
        return self._require_binding(str(instance_id)).adapter

    async def resolve_for_instance(self, software_instance_id: str) -> EngineeringSoftwareAdapter:
        """`docs/02` §56 的 `resolve_for_instance(software_instance_id)`。

        Args:
            software_instance_id: 软件实例标识。

        Returns:
            该实例已加载的 Adapter 实例。

        Raises:
            NotFoundError: 软件实例本身不存在（§56 原文口径；仅在注入
                `SoftwareInstanceLookup` 时可判定）。
            AdapterNotFoundError: 该实例未加载 Adapter（§56 的
                `Adapter instance not loaded`）。
        """
        target = str(software_instance_id)
        if self._software is not None:
            record = await self._software.get_instance(target)
            if record is None:
                raise NotFoundError(f"Software instance not found: {target}")
        return self._require_binding(target).adapter

    # ===== 生命周期（`docs/02` §54 / §55）=====

    async def connect(self, instance_id: str) -> dict[str, Any]:
        """连接单个实例并做一次健康检查（`docs/02` §54）。

        Args:
            instance_id: 软件实例标识。

        Returns:
            该实例的健康结果（`docs/02` §25）。

        Raises:
            AdapterNotFoundError: 实例未绑定。
            StructAIError: 连接失败 —— 归一化后的 20 码异常（`docs/02` §50）。
        """
        binding = self._require_binding(str(instance_id))
        health: dict[str, Any] = {}
        try:
            await binding.adapter.connect(dict(binding.config))
            health = await self._health.check(binding.adapter)
        except StructAIError:
            raise
        except Exception as error:
            self._fail(binding.instance_id, error)
        self._errors.pop(binding.instance_id, None)
        return health

    async def disconnect(self, instance_id: str) -> None:
        """断开单个实例（`docs/02` §10 / §55）。

        Raises:
            AdapterNotFoundError: 实例未绑定。
            StructAIError: 断开失败 —— 归一化后的 20 码异常。
        """
        binding = self._require_binding(str(instance_id))
        try:
            await binding.adapter.disconnect()
        except StructAIError:
            raise
        except Exception as error:
            self._fail(binding.instance_id, error)

    async def connect_all(self) -> dict[str, dict[str, Any]]:
        """连接全部已绑定实例；**永不**抛出（`docs/07` §14.4；见裁决 5）。

        Returns:
            `{instance_id: 健康结果或归一化错误信封}`（实例标识升序，输出确定性）。
        """
        results: dict[str, dict[str, Any]] = {}
        for instance_id in self.bound_instance_ids():
            try:
                results[instance_id] = await self.connect(instance_id)
            except StructAIError as error:
                results[instance_id] = error.to_dict()
            except AdapterNotFoundError as error:
                results[instance_id] = self._unhealthy(type(error).__name__)
        return results

    async def disconnect_all(self) -> None:
        """断开全部已绑定实例；**永不**抛出（`docs/02` §55；见裁决 5）。"""
        for instance_id in self.bound_instance_ids():
            try:
                await self.disconnect(instance_id)
            except (StructAIError, AdapterNotFoundError):
                continue

    # ===== 健康（`docs/02` §25 / §52 / §53）=====

    async def health_check(self, instance_id: str) -> dict[str, Any]:
        """检查单个实例的健康（`docs/02` §52）。

        Raises:
            AdapterNotFoundError: 实例未绑定（**不**静默回落，门槛 ②）。
        """
        binding = self._require_binding(str(instance_id))
        return await self._health.check(binding.adapter)

    async def health_check_all(self) -> dict[str, dict[str, Any]]:
        """检查全部已绑定实例；**永不**抛出（`docs/02` §53；见裁决 5）。

        Returns:
            `{instance_id: 健康结果}`（实例标识升序）—— 一个实例不健康**不会**
            影响其它实例，也**不会**让 Core 失去 READY（`docs/07` §14.4）。
        """
        return {
            instance_id: await self.health_check(instance_id)
            for instance_id in self.bound_instance_ids()
        }

    # ===== 能力（`docs/02` §21–§24 / §57）=====

    def runtime_capabilities(self, instance_id: str) -> frozenset[str] | None:
        """运行时能力快照（`docs/02` §21 / §23 / §57；见裁决 4）。

        🔴 这是 `CapabilityResolver.status_of()` 的**接入点**（`docs/07` §16 R30）。

        Args:
            instance_id: 软件实例标识。

        Returns:
            已快照的能力码集合；**未绑定 / 未连接 → `None`** ——
            调用方据此落 `UNKNOWN`（`UNKNOWN ≠ SUPPORTED`，`docs/02` §47），
            而不是 `UNSUPPORTED`（「探测不到」≠「明确不支持」）。
        """
        binding = self._instances.get(str(instance_id))
        if binding is None:
            return None
        codes = binding.adapter.runtime_capabilities
        if codes is None:
            return None
        return frozenset(str(code) for code in codes)

    async def detect_capabilities(self, instance_id: str) -> list[str]:
        """重新探测实例的运行时能力（`docs/02` §21 / §23）。

        ⚠️ 本方法只**探测**并返回；刷新 `CapabilityResolver` 的缓存是调用方的职责
        （§48 的 `invalidate`）。

        Raises:
            AdapterNotFoundError: 实例未绑定。
            StructAIError: 探测失败 —— 归一化后的 20 码异常。
        """
        binding = self._require_binding(str(instance_id))
        try:
            codes = await binding.adapter.get_capabilities()
        except StructAIError:
            raise
        except Exception as error:
            self._fail(binding.instance_id, error)
        return [str(code) for code in codes]

    # ===== 执行（`docs/02` §48 / §50；`docs/07` §9 第 18–19 步）=====

    async def execute(
        self,
        instance_id: str,
        operation: str,
        parameters: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """在指定实例上执行一个规范化 Operation（`docs/02` §48）。

        Args:
            instance_id: 软件实例标识（第 7 步已由 `ResourceResolver` 解析）。
            operation: 规范化 Operation 名。
            parameters: 规范化参数。
            context: 执行上下文。

        Returns:
            规范化结果（`docs/02` §33 / §37）。

        Raises:
            CapabilityError: `STRUCTAI-3000` —— 实例未绑定 Adapter，或 Adapter 未
                就绪（见裁决 3；`UNKNOWN ≠ SUPPORTED`，`docs/02` §47）。
            StructAIError: 执行失败 —— 归一化后的 20 码异常（`docs/02` §50）。
        """
        binding = self._require_executable(str(instance_id))
        return await binding.adapter.execute_normalized(
            str(operation),
            dict(parameters),
            context,
        )

    async def cancel(self, instance_id: str, task_id: str) -> None:
        """请求取消一个任务（`docs/02` §51）。

        ⚠️ 取消**不得**杀 Python 进程，**不得**伪造 `CANCELLED`（`docs/07` §14.4）；
        本方法只把请求转给 Adapter，最终状态由 Task Engine（P22+）判定。

        Raises:
            AdapterNotFoundError: 实例未绑定。
            StructAIError: 取消失败 —— 归一化后的 20 码异常。
        """
        binding = self._require_binding(str(instance_id))
        try:
            await binding.adapter.cancel(str(task_id))
        except StructAIError:
            raise
        except Exception as error:
            self._fail(binding.instance_id, error)

    # ===== 诊断（见裁决 5 / 6）=====

    def instance_errors(self) -> dict[str, dict[str, Any]]:
        """最近一次失败的归一化错误信封（按实例标识升序）。

        ⚠️ 只含 20 码信封（`code` / `type` / `message` / `details` / `retryable`），
        **不含**原生 message、**不含**连接配置 / 凭据（`docs/07` §14.3）。
        """
        return {key: dict(self._errors[key]) for key in sorted(self._errors)}

    # ===== 内部 =====

    def _require_binding(self, instance_id: str) -> BoundInstance:
        """取绑定；未绑定 → `AdapterNotFoundError`（门槛 ②：**不**静默回落）。"""
        binding = self._instances.get(instance_id)
        if binding is None:
            raise AdapterNotFoundError(f"Adapter instance not loaded: {instance_id}")
        return binding

    def _require_executable(self, instance_id: str) -> BoundInstance:
        """取**可执行**的绑定；否则 `STRUCTAI-3000`（见裁决 3）。"""
        binding = self._instances.get(instance_id)
        if binding is None:
            raise CapabilityError(
                "Capability not supported",
                details={
                    "stage": ADAPTER_ERROR_STAGE,
                    "reason": "adapter_instance_not_bound",
                },
            )
        state = getattr(binding.adapter, "state", None)
        if state is not None and str(state) != AdapterState.READY.value:
            raise CapabilityError(
                "Capability not supported",
                details={
                    "stage": ADAPTER_ERROR_STAGE,
                    "reason": "adapter_not_ready",
                    "state": str(state),
                },
            )
        return binding

    def _fail(self, instance_id: str, error: Exception) -> NoReturn:
        """记录并抛出**归一化**异常（`docs/02` §50；见裁决 5）。"""
        normalized = normalize_error(error)
        self._errors[instance_id] = normalized
        raise error_for(normalized) from error

    @staticmethod
    def _unhealthy(error_type: str) -> dict[str, Any]:
        """构造 `docs/02` §52 形状的不健康结果（只带异常**类名**）。"""
        return {
            "healthy": False,
            "state": AdapterState.ERROR.value,
            "error": {"type": error_type},
        }
