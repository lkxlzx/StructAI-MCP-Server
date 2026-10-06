"""Infrastructure · Adapters · Base · Adapter —— `EngineeringSoftwareAdapter` ABC 与生命周期基类。

权威来源
--------
- `docs/02` §32 / §21（`source7` / `impl`）—— `EngineeringSoftwareAdapter(ABC)` 的**八个**
  方法：`connect` / `disconnect` / `health_check` / `get_version` / `get_capabilities` /
  `execute` / `cancel` / `normalize_error`（本模块逐个照抄签名与顺序）。
- `docs/02` §4 / §5（`adapter`）—— 同上八个方法；并定义 `AdapterContext`
  （Adapter **不**接收任意全局对象）。
- `docs/02` §8 / §9 / §10（`adapter`）—— 生命周期状态机与 `BaseAdapter` 的
  `connect` / `disconnect` 骨架（含 `_connect` / `_disconnect` / `_initialize` 钩子）。
- `docs/02` §11（`adapter`）—— 连接成功后：version detection → capability detection →
  health check → `READY`。
- `docs/02` §21 / §23 / §25 / §33（`adapter`）—— 能力检测与 `health_check()` 的统一返回
  形状（`healthy` / `state` / `version` / `latency_ms`）。
- `docs/02` §50（`adapter`）—— Adapter 必须把原生异常转成 StructAI Error。
- `docs/02` §33（`impl`）/ §37（`py`）/ §89（`blue`）—— Result Normalization：
  Adapter 只产出规范化结果（客户端不依赖任何软件原始字段）。
- `docs/07` §9 第 18–19 步 / §14.1 / §14.2 —— Adapter 位置与红线（**不得**依赖
  `app.interfaces` / FastAPI / MCP SDK；Core 内不出现厂商 endpoint / 参数 / 响应）。

落地裁决（只补实现手段，不改签名 / 不改语义）
--------------------------------------------
1. **八个方法全部抽象在 ABC 上**：`docs/07` §12 P19–P20 门槛 ① 要求 ABC「抽象出八个
   方法」，故 `EngineeringSoftwareAdapter.__abstractmethods__` **恰好**是这八个；
   `BaseAdapter` 只给其中三个（`connect` / `disconnect` / `normalize_error`）提供
   通用实现，其余五个仍由具体 Adapter 实现。
2. **`manifest` 由类属性构造**：`docs/02` §32 只列 `name` / `vendor` / `product` 三个
   属性，而 §6 / §7 的 `AdapterManifest` 还需要 versions / protocols / capabilities。
   本模块把六个都声明为 `ClassVar`，`manifest` 属性据此构造（不引入第二处声明）。
3. **`_initialize()` 只做「版本 + 能力」探测**：`docs/02` §11 的顺序是
   version → capability → **health** → `READY`，而 §54 的顺序是
   Connect → **Health Check** → Capability Detection → `READY`。两处对 health 的位置
   不一致；本模块按 §11 做前两步，把 health 交给调用方在 `connect()` 返回后立即执行
   （即 §54 的顺序）—— 这样**不会**出现「刚连上就报告 unhealthy」的中间态
   （§33 的 `healthy` 以 `READY` 为准）。
4. **`AdapterContext` 由 `ExecutionContext` 派生**：`execute(operation, parameters,
   context)` 的 `context` 按 `docs/02` §32 是 `ExecutionContext`；Adapter 内部
   **只**经 `adapter_context_from()` 取用 §5 的六个字段（tenant / project / instance /
   product / version / task），从而拿不到权限、会话、原始请求。
   `AdapterContext` **不**携带 password / session token / 全局权限 / 原始客户端请求
   （`docs/02` §5 的明文禁令）。
5. **`execute_normalized()` 是 Core 的唯一调用入口**：它把原生异常经
   `base.errors.normalize_error()`（20 码的**唯一**归一化点）转成领域异常，并断言返回值
   是映射（`docs/02` §33 / §37 的「规范化结果」）。`AdapterManager` 只调它，
   因此**任何**原生异常都不可能穿到 Core。
6. **`runtime_capabilities` 在 `connect()` 时快照**：`docs/02` §21 / §23 要求
   「能动态检测就必须优先用 runtime」；§48 的能力缓存以「实例 + 版本」为键。
   本模块把 `get_capabilities()` 的结果缓存在实例上（未连接时为 `None`），
   由 `AdapterManager` 暴露给 `CapabilityResolver.status_of()`（`docs/07` §16 R30
   的接入点），从而**不**在每次判定时都探测软件。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库、`app.domain` 与 `app.application.execution.context`
（`docs/07` §2.2：`Infrastructure → Domain / Application Interfaces`；
`docs/02` §32 的签名本身就引用 `ExecutionContext`）。**不**引用 SQLAlchemy / FastAPI /
MCP SDK / httpx，**不**依赖 `app.interfaces`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar, Final
from uuid import UUID

from app.application.execution.context import ExecutionContext
from app.domain.errors import AdapterError, StructAIError
from app.infrastructure.adapters.base.errors import normalize_error, raise_normalized
from app.infrastructure.adapters.base.manifest import AdapterManifest

__all__ = [
    "ADAPTER_METHODS",
    "UNRESOLVED_INSTANCE_ID",
    "AdapterContext",
    "AdapterState",
    "BaseAdapter",
    "EngineeringSoftwareAdapter",
    "adapter_context_from",
]

ADAPTER_METHODS: Final[tuple[str, ...]] = (
    "connect",
    "disconnect",
    "health_check",
    "get_version",
    "get_capabilities",
    "execute",
    "cancel",
    "normalize_error",
)
"""`docs/02` §32 的八个方法（顺序照抄；门槛 ① 逐项断言本常量）。"""

UNRESOLVED_INSTANCE_ID: Final[str] = ""
"""`AdapterContext.software_instance_id` 的「未解析」取值（见 `adapter_context_from`）。"""


class AdapterState(StrEnum):
    """Adapter 生命周期状态（`docs/02` §9，逐项照抄）。

    正常路径：`CREATED → CONNECTING → CONNECTED → READY → DISCONNECTING → DISCONNECTED`；
    任一步抛异常 → `ERROR`（`docs/02` §8 / §10）。
    """

    CREATED = "CREATED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    READY = "READY"
    DISCONNECTING = "DISCONNECTING"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class AdapterContext:
    """Adapter 可见的最小上下文（`docs/02` §5，逐字段照抄）。

    🔴 **不**携带：password / session token / 全局权限 / 原始客户端请求（§5 明文禁令）。
    本类型不可变，Adapter 无法就地提权或篡改身份。
    """

    software_instance_id: str
    product: str
    version: str
    tenant_id: str
    project_id: str | None
    task_id: str | None


def adapter_context_from(
    context: ExecutionContext,
    *,
    task_id: str | None = None,
) -> AdapterContext:
    """由 `ExecutionContext` 派生 `AdapterContext`（`docs/02` §5；见裁决 4）。

    Args:
        context: 服务端构造的执行上下文（`docs/02` §3 / §29）。
        task_id: 任务标识；任务引擎（P22+）接入后由调用方给出，本批为 `None`。

    Returns:
        只含实例 / 产品 / 版本 / 租户 / 项目 / 任务六个字段的不可变上下文。
        实例标识未解析时为 `UNRESOLVED_INSTANCE_ID`（空串）——
        `AdapterContext` **不**参与租户边界与权限判定（那是 `ResourceResolver` /
        `PermissionGuard` 的职责），故空值不会放松任何判定。
    """
    software = context.software
    return AdapterContext(
        software_instance_id=_text(software.instance_id),
        product=str(software.product or ""),
        version=str(software.version or ""),
        tenant_id=_text(context.identity.tenant_id),
        project_id=_optional_text(context.project.project_id),
        task_id=task_id,
    )


class EngineeringSoftwareAdapter(ABC):
    """工程软件适配器接口（`docs/02` §32 / §4 / §21）。

    🔴 **Core 不知道任何软件差异**（`docs/07` §2.1）：本接口的输入 / 输出一律是
    **规范化**的（Operation 名 + 规范化参数 + 规范化结果），厂商 endpoint / 参数 /
    响应只允许存在于 Adapter 实现内部。

    Attributes:
        name: Adapter 包标识（如 `structai.mock`）。
        vendor: 厂商；厂商名只允许出现在 Adapter 层（`docs/07` §14.2）。
        product: 产品。
        supported_versions: 声明的版本集合（严格精确匹配，`docs/02` §20）。
        protocols: 通信协议（`IN_PROCESS` / `REST` …）。
        capabilities: **静态**能力清单；运行时清单见 `get_capabilities()`。
    """

    name: ClassVar[str] = ""
    vendor: ClassVar[str] = ""
    product: ClassVar[str] = ""
    supported_versions: ClassVar[tuple[str, ...]] = ()
    protocols: ClassVar[tuple[str, ...]] = ()
    capabilities: ClassVar[tuple[str, ...]] = ()

    # ===== `docs/02` §32 的八个方法 =====

    @abstractmethod
    async def connect(self, config: dict[str, Any]) -> None:
        """建立连接（`docs/02` §32）。

        Args:
            config: Adapter **私有**的连接配置。凭据只经运行环境注入，
                **绝不**落库 / 落日志 / 落文件（`docs/07` §8.5 / §14.3）。

        Raises:
            Exception: 连接失败由实现抛出原生异常，经 `execute_normalized()` /
                `normalize_error()` 归一化（`docs/02` §50）。
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接；实现必须幂等（`docs/02` §10 / §32）。"""
        ...

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """健康检查（`docs/02` §25 / §32）。

        Returns:
            统一形状：`{"healthy": bool, "state": str, "version": str, "latency_ms": int}`。
        """
        ...

    @abstractmethod
    async def get_version(self) -> str:
        """读取软件版本（`docs/02` §32）。"""
        ...

    @abstractmethod
    async def get_capabilities(self) -> list[str]:
        """读取**运行时**能力清单（`docs/02` §21 / §23 / §32）。

        Returns:
            能力码列表（软件无关词表；`docs/07` §14.2）。
        """
        ...

    @abstractmethod
    async def execute(
        self,
        operation: str,
        parameters: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """执行一个**规范化** Operation（`docs/02` §32 / §48）。

        Args:
            operation: Operation 名（如 `BUILD.COLUMN`）—— Core 的规范化标识，
                **不是**任何软件的 endpoint。
            parameters: 规范化参数（`docs/02` §24 的 `input_schema` 口径）。
            context: 执行上下文；Adapter 只经 `adapter_context_from()` 取用（见裁决 4）。

        Returns:
            规范化结果（`docs/02` §33 / §37 / §89）—— 客户端不依赖任何软件原始字段。

        Raises:
            Exception: 失败由实现抛原生异常；Core 侧一律经 `execute_normalized()` 归一化。
        """
        ...

    @abstractmethod
    async def cancel(self, task_id: str) -> None:
        """取消一个任务（`docs/02` §51 / §32）。

        ⚠️ **不得**杀 Python 进程，**不得**伪造 `CANCELLED`（`docs/07` §14.4）。
        """
        ...

    @abstractmethod
    def normalize_error(self, error: Exception) -> dict[str, Any]:
        """把原生异常归一化成 20 码错误信封（`docs/02` §49 / §50）。

        🔴 本项目的**唯一**归一化点是
        `app.infrastructure.adapters.base.errors.normalize_error()`；实现应直接委托它，
        不得各写一套映射（否则「哪类异常落哪一码」会有多处可漂移的实现）。
        """
        ...

    # ===== Core 侧入口（见裁决 5 / 6）=====

    @property
    def runtime_capabilities(self) -> tuple[str, ...] | None:
        """运行时能力快照（`docs/02` §21 / §23；见裁决 6）。

        Returns:
            已探测到的能力码；`None` 表示**未探测 / 未连接** ——
            `CapabilityResolver.status_of()` 据此落 `UNKNOWN`
            （`docs/07` §16 R30：`UNKNOWN ≠ SUPPORTED`，一律拒绝）。
            缺省实现返回 `None`；`BaseAdapter` 在 `connect()` 时快照。
        """
        return None

    async def execute_normalized(
        self,
        operation: str,
        parameters: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """执行并**归一化**（`docs/02` §50；`docs/07` §9 第 18–19 步）。

        🔴 这是 Core（`AdapterManager` / P36 的 `ExecutionService`）的**唯一**调用入口：
        它保证「原生异常绝不外泄」与「返回值必为规范化映射」两件事，
        且两件事都只在此实现。

        Args:
            operation: 规范化 Operation 名。
            parameters: 规范化参数。
            context: 执行上下文。

        Returns:
            规范化结果（映射）。

        Raises:
            StructAIError: 20 码领域异常 —— 原生异常在此**不再**向上传播
                （`docs/02` §50：「Core 不允许直接暴露 native exception」）；
                `__cause__` 保留原始异常供服务端诊断。
        """
        try:
            result = await self.execute(operation, parameters, context)
        except StructAIError:
            raise
        except Exception as error:
            raise_normalized(error)
        return _canonical_result(result)

    # ===== 声明（`docs/02` §6 / §7；见裁决 2）=====

    @property
    def manifest(self) -> AdapterManifest:
        """本 Adapter 的注册声明（`docs/02` §6 / §7）。

        Returns:
            由类属性构造的 `AdapterManifest`（**未**校验；装配期由
            `AdapterManager.register()` 调 `validate()`）。
        """
        return AdapterManifest(
            name=self.name,
            vendor=self.vendor,
            product=self.product,
            supported_versions=tuple(self.supported_versions),
            protocols=tuple(self.protocols),
            capabilities=tuple(self.capabilities),
        )

    @property
    def adapter_key(self) -> tuple[str, str]:
        """注册键 `(vendor, product)`（`docs/07` §12 P19–P20 门槛 ②）。"""
        return (self.vendor, self.product)


class BaseAdapter(EngineeringSoftwareAdapter):
    """生命周期与错误归一化的通用基类（`docs/02` §10；见裁决 1）。

    实现三个方法：`connect` / `disconnect`（生命周期状态机）与 `normalize_error`
    （委托 20 码的**唯一**归一化点）。其余五个方法（`health_check` / `get_version` /
    `get_capabilities` / `execute` / `cancel`）仍由具体 Adapter 实现。

    额外提供两个诊断入口：`state`（生命周期状态）与 `last_health`
    （最近一次健康检查结果）。运行时能力快照见 `runtime_capabilities`。
    """

    def __init__(self) -> None:
        """初始化状态机与运行时快照（**不**做任何 I/O）。"""
        self._state: AdapterState = AdapterState.CREATED
        self._version: str | None = None
        self._runtime_capabilities: tuple[str, ...] | None = None
        self._last_health: dict[str, Any] | None = None

    # ===== 状态（`docs/02` §9 / §10）=====

    @property
    def state(self) -> AdapterState:
        """当前生命周期状态（`docs/02` §9）。"""
        return self._state

    @property
    def runtime_capabilities(self) -> tuple[str, ...] | None:
        """`connect()` 时快照的运行时能力；**未连接时为 `None`**（见裁决 6）。"""
        return self._runtime_capabilities

    @property
    def last_health(self) -> dict[str, Any] | None:
        """最近一次 `health_check()` 的结果（诊断用，可为 `None`）。"""
        return self._last_health

    # ===== 生命周期（`docs/02` §10 / §11）=====

    async def connect(self, config: dict[str, Any]) -> None:
        """建立连接并完成初始化（`docs/02` §10 的骨架，逐句照抄语义）。

        Args:
            config: Adapter 私有连接配置（凭据绝不落库 / 落日志，`docs/07` §8.5）。

        Raises:
            Exception: 任一步失败 → 状态置 `ERROR` 并**原样上抛**（`docs/02` §10）；
                归一化由调用方经 `execute_normalized()` / `normalize_error()` 完成。
        """
        self._state = AdapterState.CONNECTING
        try:
            await self._connect(config)
            self._state = AdapterState.CONNECTED
            await self._initialize()
            self._state = AdapterState.READY
        except Exception:
            self._state = AdapterState.ERROR
            self._runtime_capabilities = None
            raise

    async def disconnect(self) -> None:
        """断开连接（`docs/02` §10；`DISCONNECTED` / `CREATED` 时直接返回，幂等）。"""
        if self._state in {AdapterState.DISCONNECTED, AdapterState.CREATED}:
            return
        self._state = AdapterState.DISCONNECTING
        try:
            await self._disconnect()
        finally:
            self._state = AdapterState.DISCONNECTED
            self._runtime_capabilities = None
            self._version = None

    def normalize_error(self, error: Exception) -> dict[str, Any]:
        """委托 20 码的**唯一**归一化点（`docs/02` §49 / §50；见裁决 1）。"""
        return normalize_error(error)

    # ===== 子类钩子（`docs/02` §10）=====

    async def _connect(self, config: dict[str, Any]) -> None:
        """原生连接钩子（`docs/02` §10 / §31）。

        Raises:
            NotImplementedError: 具体 Adapter 必须实现它。
        """
        raise NotImplementedError

    async def _disconnect(self) -> None:
        """原生断开钩子（`docs/02` §10）；缺省无操作。"""
        return None

    async def _initialize(self) -> None:
        """连接成功后的初始化（`docs/02` §11 的前两步；见裁决 3）。

        顺序：version detection → capability detection。健康检查由调用方在
        `connect()` 返回后立即执行（`docs/02` §54）。
        """
        self._version = await self.get_version()
        self._runtime_capabilities = tuple(str(code) for code in await self.get_capabilities())


# ===== 内部 =====


def _canonical_result(result: object) -> dict[str, Any]:
    """断言返回值是**规范化**映射（`docs/02` §33 / §37；见裁决 5）。

    Raises:
        AdapterError: `STRUCTAI-6000`，Adapter 返回了非映射结果（Core 无法消费）。
    """
    if isinstance(result, Mapping):
        return {str(key): value for key, value in result.items()}
    raise AdapterError(
        "Adapter returned a non-canonical result",
        details={"stage": "adapter_result", "type": type(result).__name__},
    )


def _text(value: object) -> str:
    """把标识规整成字符串（`None` → 空串）。"""
    return "" if value is None else str(value)


def _optional_text(value: UUID | str | None) -> str | None:
    """把可选标识规整成 `str | None`。"""
    return None if value is None else str(value)
