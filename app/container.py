"""应用容器（P01 Bootstrap / P02 Config / P03 Domain / P04 Database / P05 Repository /
P06 UnitOfWork / P07 Seed / P08 Registry / P09 Schema / P10–P13 Security /
P14–P18 Execution / P19–P20 Adapters / P21 Idempotency / P22–P28 Task Engine）。

- 本文件是**唯一**的依赖装配点（`docs/07` §3.3 冻结结构）。
- 禁止在模块层创建全局单例（`blue` §123：禁止 `global TaskEngine()`）。
- 形状对齐 `docs/02` §33（Bootstrap Container），字段由后续批次逐个接入：

| 字段 | 接入批次 |
| --- | --- |
| `settings` / `runtime_config` | **P02 ✅** |
| `engine` / `session_factory` | **P04 ✅** |
| `repositories`（会话级，**不**进容器） | **P05 ✅** |
| `unit_of_work`（会话级，**不**进容器） | **P06 ✅** |
| `seed()` / `SeedReport`（数据装配，**不**进容器） | **P07 ✅** |
| `operation_registry` | **P08 ✅** |
| `schema_registry` / `schema_engine` | **P09 ✅ 不进容器**（§33 冻结形状无此字段） |
| 安全服务（`authentication` / `session` / `rbac` / `permission`；会话级，不进容器） | **P10 ✅** |
| 资源 / 能力服务（`resolver` / `lock_manager` / `capability_resolver`） | **P14 ✅** |
| 适配器（`AdapterManager`；**进程级**，不进容器） | **P19 ✅** |
| `execution_service` | P36 |

生命周期（`docs/02` §34 / §79 / §80）：

    build_container(settings)   → 装配 engine / session_factory（不做连接 I/O）
    await container.startup()   → 建立并校验数据库连接 + 装配 Registry（失败即不就绪）
    await container.shutdown()  → await engine.dispose()

🔴 禁止项（`docs/07` §14.3）：

- 启动时**不得**静默 `ALTER TABLE`，也**不得**静默建表 / 改表 —— schema 演进一律
  交给 Alembic；`Base.metadata.create_all` 只在验收脚本 / 测试中**显式**调用。
- 日志**绝不**输出连接串中的凭据：一律用 `URL.render_as_string(hide_password=True)`
  （`docs/07` §14.3：绝不记录 secret）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.execution.confirmation import ConfirmationGuard, ConfirmationService
from app.application.execution.context import ExecutionContext
from app.application.execution.engineering_validator import EngineeringValidator
from app.application.execution.idempotency import IdempotencyService
from app.application.execution.identity import (
    MCPAuthenticator,
    MCPIdentity,
    identity_from_security,
)
from app.application.execution.pipeline import ExecutionPipeline
from app.application.execution.postconditions import PostconditionEvaluator
from app.application.execution.preconditions import PreconditionEvaluator
from app.application.execution.service import ExecutionService
from app.application.execution.validation import SchemaEngine
from app.application.resource.lock_manager import ResourceLockManager
from app.application.resource.lock_policy import LockPolicy
from app.application.resource.resolver import ResourceResolver
from app.application.security import PasswordService, SecurityServices, build_security_services
from app.application.services.adapter_resolver import AdapterResolver
from app.application.services.artifact import ArtifactService
from app.application.services.backup import BackupService, RestoreService, RetentionService
from app.application.services.capability_resolver import CapabilityResolver
from app.application.services.document import DocumentService
from app.application.services.model import ModelService
from app.application.services.quota import QuotaService, StaticQuotaPolicySource
from app.application.services.result import ResultService
from app.application.task.cancellation import CancellationService
from app.application.task.engine import TaskEngine
from app.application.task.lease import LeaseService
from app.application.task.progress import ProgressReporter
from app.application.task.queue import TaskQueue
from app.application.task.recovery import RecoveryService
from app.application.task.scheduler import Scheduler
from app.application.task.worker import TaskWorker
from app.config.runtime_config import RuntimeConfig, build_runtime_config
from app.config.settings import Settings
from app.domain.enums import HealthStatus, SoftwareConnectionState
from app.domain.errors import InternalError
from app.domain.protocols import TaskRecord
from app.infrastructure.adapters.base.manager import AdapterManager
from app.infrastructure.adapters.mock.adapter import MockAdapter
from app.infrastructure.database.models.software import (
    SoftwareInstanceORM,
    SoftwareORM,
    SoftwareProductORM,
    SoftwareVersionORM,
)
from app.infrastructure.database.repositories import (
    build_artifact_store,
    build_audit_store,
    build_document_store,
    build_document_version_store,
    build_idempotency_store,
    build_resource_store,
    build_security_stores,
    build_task_store,
)
from app.infrastructure.database.session import (
    create_engine,
    create_session_factory,
    verify_connection,
)
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.infrastructure.events import (
    EventDispatcher,
    InMemoryEventRecordStore,
    InProcessEventBus,
)
from app.infrastructure.locks.in_memory import InMemoryLock
from app.infrastructure.notifications import NotificationService
from app.infrastructure.registry.capability_registry import CapabilityRegistry
from app.infrastructure.registry.operation_registry import OperationRegistry
from app.infrastructure.registry.schema_registry import SchemaRegistry
from app.infrastructure.secrets import EnvironmentCredentialProvider
from app.infrastructure.storage import ArtifactStorageManager, build_local_storage
from app.observability import (
    AuditService,
    CallableHealthChecker,
    HealthRegistry,
    HealthService,
    MetricsService,
    TraceService,
)

__all__ = [
    "BATCH_ID",
    "AppContainer",
    "ExecutionRuntime",
    "ExecutionServiceFactory",
    "ExecutionSession",
    "build_container",
    "build_execution_runtime",
    "resolve_local_identity",
]

BATCH_ID: Final[str] = "P42"

logger = logging.getLogger("structai")


@dataclass(slots=True)
class AppContainer:
    """应用依赖容器。

    P04：`settings` / `runtime_config` / `engine` / `session_factory` 已接入；
    P05：仓储**不**在此装配 —— 仓储持有 `AsyncSession`，属会话级对象，
    由 `build_repositories(session)` 装配（`docs/02` §16 / §33）；
    P06：`UnitOfWork` 同理**不**在此装配 —— 它持有同一个会话，由调用方按业务事务
    构造（`docs/02` §16：一个业务事务 = 一个明确 UnitOfWork）；
    `operation_registry` 由 P08 在 `startup()` 装配；P09 的 `SchemaEngine` / `SchemaRegistry`
    按 `docs/02` §33 的冻结容器形状**不**进本容器（见 `build_container` 的说明）；
    P10：安全服务（`app.application.security`）同理**不**进本容器 —— 它们是会话级
    对象（见 `build_container` 的说明），由 `build_security_stores(session)` +
    `build_security_services(...)` 按会话装配；
    P14：资源 / 能力服务（`app.application.resource` / `app.application.services`）同理
    **不**进本容器 —— `ResourceResolver` 持有会话级的 `ResourceStore`，
    `ResourceLockManager` 是进程内状态，`CapabilityResolver` 依赖会话级 `ResourceStore`；
    三者都由调用方（P36 的 `ExecutionService`）按会话 / 进程装配；
    `execution_service` 仍为空（P36 填充）。

    P19：适配器（`app.infrastructure.adapters`）同样**不**进本容器 ——
    `AdapterManager` 是**进程级**对象（Adapter 注册 / 实例绑定 / 运行时能力快照都在进程内，
    见 `adapters/base/manager.py` 裁决 1 / 2），由 P36 的 `ExecutionService` 持有，
    并作为 `RuntimeCapabilitySource` 注入 `CapabilityResolver`（`docs/07` §16 R30）。
    P21：幂等记录存储（`app.infrastructure.database.repositories.idempotency`）同样**不**进本
    容器 —— 它持有**会话级**的 `AsyncSession`，由 `build_idempotency_store(session)` 按会话装配；
    `IdempotencyService`（`app.application.execution.idempotency`）只依赖 Domain 契约
    `IdempotencyStore`，由 P36 的 `ExecutionService` 按会话构造（`docs/02` §28 / §33）。
    `started` 仅表示生命周期已进入运行态。
    P22–P28：任务引擎（`app.application.task`）同样**不**在此装配 —— `TaskEngine` /
    `TaskWorker` 持有**会话级**的 `TaskStore`（由 `build_task_store(session)` 装配），
    `TaskQueue` / `Scheduler` / `ResourceLockManager` 是**进程内**状态
    （`docs/02` §38），`LeaseService` / `CancellationService` / `RecoveryService` /
    `ProgressReporter` 由调用方按会话装配。故容器形状**不变**
    （`docs/02` §33 的冻结形状；`tests/test_task_engine_p22_p28.py` 逐字段断言）。
    """

    settings: Settings
    runtime_config: RuntimeConfig
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    operation_registry: OperationRegistry | None = None
    """运行时 Operation Registry（P08 装配；`docs/02` §28）。

    `startup()` 成功后为已装配实例；数据库未配备时为 `None`（见 `startup()` 的说明）。
    """
    execution_service: Any = None
    started: bool = field(default=False, repr=False)

    async def startup(self) -> None:
        """启动钩子：建立并校验数据库连接（P04）→ 装配 Registry（P08）。

        - 只做连接与一次 `SELECT 1` 连通性校验；**不建表、不改表**
          （`docs/07` §14.3：禁止启动时静默 `ALTER TABLE`）。
        - 连接失败即抛异常，进程以非 0 退出码结束 —— 不允许「带病启动」。
        - P08：装配运行时 Operation Registry（`docs/02` §28）；**校验失败即抛异常**，
          Server 不得进入 READY（`docs/07` §14.4）。数据库尚未配备（缺 `operations` 表）时
          Registry 留空并告警 —— 这**不算**校验失败：P01–P07 的回归门槛要求
          `python -m app.main` 在未配备的开发库上仍以退出码 0 结束。
        """
        await verify_connection(self.engine)

        self.operation_registry = await OperationRegistry.load(self.engine, self.session_factory)

        self.started = True
        logger.info(
            "database connection established: %s",
            make_url(self.settings.database_url).render_as_string(hide_password=True),
        )
        if self.operation_registry is None:
            logger.warning(
                "operation registry is not assembled: database is not provisioned "
                "(run `python -m app.infrastructure.database.seed`)"
            )
        else:
            logger.info("registry ready: %s", self.operation_registry.summary())

        # P29–P36（`docs/02` §123 / §17 / §54）：装配进程级执行运行时 + 健康检查器。
        # ⚠️ Registry 校验失败 → Server MUST NOT become READY（`docs/07` §14.4）：
        # 未配备库时运行时的 `ready()` 为 False，健康检查器会如实报告 `UNAVAILABLE`。
        runtime = build_execution_runtime(
            self.settings,
            runtime_config=self.runtime_config,
            operation_registry=self.operation_registry,
            capability_registry=(
                None
                if self.operation_registry is None
                else await CapabilityRegistry.load(self.engine, self.session_factory)
            ),
        )
        runtime.session_factory = self.session_factory
        bound = await bind_mock_instances(runtime, self.session_factory)
        await register_health_checkers(runtime, self.engine)
        self.execution_service = runtime.execution
        if bound:
            logger.info("bound %d software instance(s) to the mock adapter", len(bound))

    async def shutdown(self) -> None:
        """关闭钩子：释放连接池（P04）。

        `await engine.dispose()` 是进程能干净退出的前提（`docs/02` §80）。
        """
        self.started = False
        await self.engine.dispose()


def build_container(settings: Settings) -> AppContainer:
    """构造应用容器（`docs/02` §33）。

    P04 在此装配 `engine` / `session_factory`（`docs/02` §15）；
    P05 的仓储是**会话级**对象，由 `build_repositories(session)` 装配（`docs/02` §16 / §33）；
    P06 的 `UnitOfWork` 同样是**会话级**对象（持有会话、决定 commit / rollback），
    由调用方按业务事务构造（`docs/02` §16），**不**进本容器；
    P08：`operation_registry` 由 `startup()` 装配（需要数据库连接；校验失败即不就绪）；
    P09：`schema_registry` / `schema_engine` **不**在此装配 —— `docs/02` §33 的冻结形状
    没有这两个字段，且 `SchemaEngine` 只依赖 `SchemaLookup`（`docs/02` §16 的原文签名
    按 `docs/07` §2.2 收窄），由 P36 的 `ExecutionService` 构造（`docs/07` §9 第 8 步）。
    P10：`AuthenticationService` / `SessionService` / `RBACService` /
    `EffectivePermissionService` 等安全服务**不**在此装配 —— 它们同样是**会话级**
    对象（持有 `SessionStore` / `UserLookup` / `RoleLookup` / `ProjectMembershipLookup`，
    全部绑定在 `AsyncSession` 上），由
    `app.infrastructure.database.repositories.build_security_stores(session)`
    + `app.application.security.build_security_services(...)` 按会话装配。
    P14：`ResourceResolver` / `ResourceLockManager` / `CapabilityResolver` 同样**不**在此
    装配 —— `ResourceResolver` 与 `CapabilityResolver` 持有**会话级**的 `ResourceStore`
    （由 `app.infrastructure.database.repositories.build_resource_store(session)` 装配），
    `ResourceLockManager` 是**进程内**状态（`docs/02` §38），三者都由 P36 的
    `ExecutionService` 按会话 / 进程持有（`docs/02` §33 / §123）。

    ⚠️ 本函数**不建立连接**（只构造引擎），连接与校验由 `startup()` 完成；

    P19：`AdapterManager`（`app.infrastructure.adapters.base.manager`）**不**在此装配 ——
    它是**进程级**对象（注册表与实例绑定是进程内状态；`docs/02` §15 的
    `adapter_instances` 表本批**不**建，见该模块裁决 2），由 P36 的 `ExecutionService`
    持有。`MockAdapter` 由调用方 `register()` + `bind_instance()` 显式装配
    （`docs/02` §54 的启动序列；Plugin Loader / Entry Point 不在本批，见 `docs/02` §117）。
    仓储是**会话级**对象，由 `app.infrastructure.database.repositories.build_repositories`
    按会话装配，**不**进本容器（`docs/02` §16 / §33）；因此本函数仍是同步的。
    """
    engine = create_engine(settings.database_url, echo=settings.sql_echo)
    session_factory = create_session_factory(engine)

    return AppContainer(
        settings=settings,
        runtime_config=build_runtime_config(settings),
        engine=engine,
        session_factory=session_factory,
    )


# ===== P29–P36：进程级执行运行时与会话级装配（`docs/02` §33 / §123）=====


@dataclass(frozen=True, slots=True)
class ExecutionSession:
    """一次会话级的装配产物（`docs/02` §33 的会话级对象集合）。

    ⚠️ 这是**会话级**对象：生命周期与 `AsyncSession` 绑定，不得跨请求复用
    （`docs/02` §16 / §33）。事务边界归调用方的 `UnitOfWork`。
    """

    service: ExecutionService
    pipeline: ExecutionPipeline
    engine: TaskEngine
    worker: TaskWorker
    queue: TaskQueue
    security: SecurityServices
    resolver: ResourceResolver
    capabilities: CapabilityResolver
    artifacts: ArtifactService
    documents: DocumentService
    models: ModelService
    results: ResultService
    adapter_resolver: AdapterResolver
    audit: AuditService
    backup: BackupService
    restore: RestoreService
    retention: RetentionService


@dataclass(slots=True)
class ExecutionRuntime:
    """进程级执行运行时（`docs/02` §123 的装配产物）。

    承载 `docs/02` §123 列出的进程级单例：`AdapterManager` / `ArtifactStorage` /
    `EventBus` / `Metrics` / `Trace` / 审计链锁 / `Quota` / `Confirmation` /
    `CredentialProvider` / `Notification` / `Health`，以及 P36 的
    `ExecutionServiceFactory`（会话级 `ExecutionService` 的唯一构造入口）。

    ⚠️ 本对象**不**进 `AppContainer` 的字段（`docs/02` §33 的冻结形状是 **7 字段**，
    P22–P28 的测试逐字段断言）—— 它经 `AppContainer.execution_service.runtime`
    可达（见 `ExecutionServiceFactory.runtime`）。
    """

    settings: Settings
    runtime_config: RuntimeConfig
    adapters: AdapterManager
    storage: ArtifactStorageManager
    bus: InProcessEventBus
    outbox: InMemoryEventRecordStore
    dispatcher: EventDispatcher
    locks: ResourceLockManager
    lock_policy: LockPolicy
    chain_lock: InMemoryLock
    metrics: MetricsService
    trace: TraceService
    quota: QuotaService
    confirmation: ConfirmationService
    confirmation_guard: ConfirmationGuard
    credentials: EnvironmentCredentialProvider
    notifications: NotificationService
    health_registry: HealthRegistry
    health: HealthService
    session_factory: async_sessionmaker[AsyncSession] | None = None
    operation_registry: OperationRegistry | None = None
    capability_registry: CapabilityRegistry | None = None
    schema_registry: SchemaRegistry | None = None
    execution: ExecutionServiceFactory | None = None
    password_service: PasswordService | None = None

    def ready(self) -> bool:
        """运行时是否具备执行条件（`docs/07` §14.4：Registry 未装配 → 不就绪）。"""
        return self.operation_registry is not None and self.capability_registry is not None


def build_execution_runtime(
    settings: Settings,
    *,
    runtime_config: RuntimeConfig | None = None,
    operation_registry: OperationRegistry | None = None,
    capability_registry: CapabilityRegistry | None = None,
    schema_registry: SchemaRegistry | None = None,
) -> ExecutionRuntime:
    """装配进程级执行运行时（`docs/02` §123）。

    Args:
        settings: 进程级配置（`docs/02` §5）。
        runtime_config: 运行期参数快照（`docs/02` §6）；缺省由 `settings` 派生。
        operation_registry: P08 的运行时 Operation Registry（可为 `None`）。
        capability_registry: P08 的能力注册表（可为 `None`）。
        schema_registry: P09 的 Schema 注册表；缺省用空注册表 —— 未登记的 id 会抛
            `NotFoundError`，管线据此记为「Schema 未配备」（`pipeline.py` 裁决 2）。

    Returns:
        已装配的 `ExecutionRuntime`（含 `execution` 工厂）。

    🔴 本函数**不**建立数据库连接、**不**建表、**不**改表（`docs/07` §14.3）：
    全部是**纯内存**装配，唯一的 I/O 是本地存储目录的**惰性**创建（首次 `put` 时发生）。
    """
    resolved_config = runtime_config or build_runtime_config(settings)
    adapters = AdapterManager()
    adapters.register(MockAdapter())
    bus = InProcessEventBus()
    outbox = InMemoryEventRecordStore()
    health_registry = HealthRegistry()
    confirmation = ConfirmationService()
    runtime = ExecutionRuntime(
        settings=settings,
        runtime_config=resolved_config,
        adapters=adapters,
        storage=build_local_storage(settings.artifact_root),
        bus=bus,
        outbox=outbox,
        dispatcher=EventDispatcher(outbox, bus),
        locks=ResourceLockManager(default_timeout_seconds=settings.lock_default_timeout_seconds),
        lock_policy=LockPolicy(timeout_seconds=settings.lock_default_timeout_seconds),
        chain_lock=InMemoryLock(),
        metrics=MetricsService(),
        trace=TraceService(),
        quota=QuotaService(StaticQuotaPolicySource()),
        confirmation=confirmation,
        confirmation_guard=ConfirmationGuard(confirmation),
        credentials=EnvironmentCredentialProvider(),
        notifications=NotificationService(),
        health_registry=health_registry,
        health=HealthService(health_registry),
        operation_registry=operation_registry,
        capability_registry=capability_registry,
        schema_registry=schema_registry or SchemaRegistry(),
    )
    runtime.password_service = PasswordService()
    runtime.execution = ExecutionServiceFactory(runtime)
    return runtime


class _DeferredTaskExecutor:
    """把「`TaskWorker` 需要 `executor`」与「`ExecutionService` 需要 `TaskEngine`」的环解开。

    `docs/02` §123 把两者都列为容器装配项，但装配**顺序**上互为前置：Worker 要
    `executor`，而 `ExecutionService` 要 `TaskEngine`（它要 Worker）。故容器注入一个
    **一次绑定**的代理：`bind()` 之前调用一律 `STRUCTAI-7000`
    （`reason = "executor_not_bound"`），**绝不**静默空跑或返回假结果。
    """

    def __init__(self) -> None:
        self._service: ExecutionService | None = None

    def bind(self, service: ExecutionService) -> None:
        """绑定真正的执行服务（`create()` 在装配完 `ExecutionService` 后调用一次）。"""
        self._service = service

    @property
    def bound(self) -> bool:
        """是否已绑定（诊断用）。"""
        return self._service is not None

    async def execute(
        self,
        task: TaskRecord,
        *,
        context: ExecutionContext | None = None,
    ) -> Mapping[str, Any]:
        """转发到 `ExecutionService.execute`（P22–P28 的 `TaskExecutor` 端口）。"""
        if self._service is None:
            raise InternalError(
                "Task executor is not bound",
                details={"stage": "container", "reason": "executor_not_bound"},
            )
        return await self._service.execute(task, context=context)


def _as_execution_context(context: object) -> ExecutionContext:
    """把收窄契约的 `object` 收窄回 `ExecutionContext`（装配期检查）。

    `ModelQuerySource.query` 的 `context` 声明为 `object`（避免 Application 层之间的
    环状依赖），而 Adapter 只接受 `ExecutionContext`（`docs/02` §5 / §29）。
    非法类型 → `STRUCTAI-7000`（装配错误），**不**静默透传。
    """
    if not isinstance(context, ExecutionContext):
        raise InternalError(
            "Adapter execution context is not an ExecutionContext",
            details={"stage": "container", "reason": "invalid_execution_context"},
        )
    return context


class _AdapterExecutorAdapter:
    """把 `AdapterManager.execute` 适配成 `AdapterExecutor`（收窄契约，`docs/02` §62）。

    ⚠️ 为什么需要这一层：`AdapterManager.execute` 的 `parameters` 声明为
    `dict[str, Any]`（P19–P20 的冻结签名），而管线的收窄契约是更宽松的
    `Mapping[str, Any]` —— 参数是**逆变**位置，故必须显式 `dict(parameters)`。
    这是**纯转发**：不缓存、不改取值、不吞异常。
    """

    def __init__(self, adapters: AdapterManager) -> None:
        self._adapters = adapters

    @property
    def manager(self) -> AdapterManager:
        """被包装的 `AdapterManager`（只读用途）。"""
        return self._adapters

    async def execute(
        self,
        instance_id: str,
        operation: str,
        parameters: Mapping[str, Any],
        context: ExecutionContext,
    ) -> Mapping[str, Any]:
        """转发到 `AdapterManager.execute`（`docs/02` §62）。"""
        return await self._adapters.execute(instance_id, operation, dict(parameters), context)


class _AdapterModelQuery:
    """把 Adapter 执行适配成 `ModelQuerySource`（收窄契约，`docs/02` §48）。

    `ModelService` 只做「查询 → 规范化映射」的转发，真正的软件交互在 Adapter
    （`docs/02` §62 / §89），故这里是**纯转发**适配器：不缓存、不改参数、不吞异常。
    """

    def __init__(self, executor: _AdapterExecutorAdapter) -> None:
        self._executor = executor

    async def query(
        self,
        *,
        software_instance_id: str,
        operation: str,
        parameters: Mapping[str, Any],
        context: object,
    ) -> Mapping[str, Any]:
        """转发到 Adapter 执行（`docs/02` §62）。"""
        return await self._executor.execute(
            software_instance_id,
            operation,
            parameters,
            _as_execution_context(context),
        )


def _result_normalizer(
    results: ResultService,
) -> Callable[[str, Mapping[str, Any]], Mapping[str, Any]]:
    """把 `ResultService.normalize` 适配成管线的 `normalizer`（`docs/02` §49 / §90）。"""

    def _normalize(operation: str, raw: Mapping[str, Any]) -> Mapping[str, Any]:
        normalized = results.normalize(operation, raw)
        data = normalized.data
        if isinstance(data, Mapping):
            return {str(key): value for key, value in data.items()}
        return {"data": data}

    return _normalize


class _FactoryAuthenticator:
    """把会话级安全服务适配成传输层的认证端口（`docs/03` §12；`docs/07` §8.1）。

    ⚠️ 每次认证都开一个**自己的**数据库会话并立即关闭：HTTP 的鉴权中间件是
    请求级的，而 `SecurityServices` 持有会话级的 `*Store`（`docs/02` §16 / §33），
    两者不能共享同一个 `AsyncSession`（并发使用不安全）。因此这里按请求装配、
    用完即关 —— 认证路径**零写入**（P10–P13 已用 SQL 级钩子证明），
    故不涉及事务边界（`docs/02` §16：只有 UnitOfWork 能 commit / rollback）。

    Attributes:
        factory: 会话级装配工厂（`ExecutionServiceFactory`）。
    """

    def __init__(self, factory: ExecutionServiceFactory) -> None:
        """绑定装配工厂。"""
        self._factory = factory

    @property
    def factory(self) -> ExecutionServiceFactory:
        """被绑定的装配工厂（只读用途）。"""
        return self._factory

    async def authenticate(self, token: str) -> MCPIdentity:
        """凭据 → 服务端身份（`docs/02` §20；`docs/03` §12）。

        Raises:
            PermissionDeniedError: `STRUCTAI-4000` —— 凭据无效 / 会话失效
                （错误形状与凭据种类无关，`docs/02` §17）。
        """
        session_factory = self._factory.runtime.session_factory
        if session_factory is None:  # pragma: no cover - 装配错误
            raise InternalError(
                "HTTP transport authentication requires a session factory",
                details={"stage": "container", "reason": "session_factory_not_bound"},
            )
        async with session_factory() as session:
            security = self._factory.security_for(session)
            return identity_from_security(await security.guard.build_context(token))


class ExecutionServiceFactory:
    """会话级 `ExecutionService` 的**唯一**构造入口（`docs/02` §123）。

    为什么容器持有的是**工厂**而不是 `ExecutionService` 本身：`ExecutionService`
    及其全部步骤服务都持有**会话级**的 `*Store`（`TaskStore` / `IdempotencyStore` /
    `ResourceStore` / `AuditStore` / `ArtifactStore` / `DocumentStore`），
    而 `docs/02` §33 的冻结容器形状是 **7 字段**且 P22–P28 的测试逐字段断言
    （本批**不得**扩展）。故容器把「装配点」暴露为工厂：进程级对象由
    `ExecutionRuntime` 持有一次，会话级对象按请求由 `create(session)` 装配
    （`docs/02` §16 / §33）。
    """

    def __init__(self, runtime: ExecutionRuntime) -> None:
        """绑定进程级运行时。"""
        self._runtime = runtime

    @property
    def runtime(self) -> ExecutionRuntime:
        """被绑定的进程级运行时（只读用途；容器字段因此可达全部进程级对象）。"""
        return self._runtime

    def security_for(self, session: AsyncSession) -> SecurityServices:
        """按会话装配安全服务（`docs/02` §33 / §123；`docs/03` §12）。

        传输层（HTTP 鉴权）需要「凭据 → 服务端身份」，而安全服务持有**会话级**
        `*Store`（`docs/02` §16 / §33），故这里复用与 `create()` **同一套**
        装配口径（同一个 `PasswordService`，同一个会话有效期），避免出现
        两套可能失同步的判定。

        Args:
            session: 调用方的会话（由 `_FactoryAuthenticator` 按请求新建）。

        Returns:
            `SecurityServices`（含 `guard` 这一唯一安全入口，`docs/02` §40 / §41）。
        """
        return build_security_services(
            build_security_stores(session),
            password_service=self._runtime.password_service or PasswordService(),
            session_lifetime_seconds=self._runtime.settings.session_expire_seconds,
        )

    def authenticator(self) -> MCPAuthenticator:
        """传输层的认证端口（`docs/03` §12；见 `_FactoryAuthenticator`）。"""
        return _FactoryAuthenticator(self)

    def create_service(
        self,
        session: AsyncSession,
        *,
        password_service: PasswordService | None = None,
    ) -> ExecutionService:
        """只装配 `ExecutionService`（`docs/02` §123 的 ExecutionService 入口）。"""
        return self.create(session, password_service=password_service).service

    def create(
        self,
        session: AsyncSession,
        *,
        password_service: PasswordService | None = None,
    ) -> ExecutionSession:
        """按会话装配 P36 的执行主干与各步骤服务（`docs/02` §33 / §123）。

        Args:
            session: 会话（通常由调用方的 `UnitOfWork` 提供）。
            password_service: 可选的口令服务（测试用快哈希器）；缺省 `PasswordService()`。

        Returns:
            `ExecutionSession`（含 `service` 与全部步骤服务）。

        Raises:
            InternalError: `STRUCTAI-7000` —— 进程级 Registry 未装配
                （`reason = "runtime_not_ready"`）。**不**用空 Registry 继续执行：
                那样每个 Operation 都会变成「未知 Operation」（`docs/07` §14.4）。
        """
        runtime = self._runtime
        if not runtime.ready():
            raise InternalError(
                "Execution runtime is not ready: registry not assembled",
                details={"stage": "container", "reason": "runtime_not_ready"},
            )
        operations = runtime.operation_registry
        capabilities_registry = runtime.capability_registry
        assert operations is not None  # noqa: S101 - `ready()` 已保证
        assert capabilities_registry is not None  # noqa: S101 - `ready()` 已保证
        settings = runtime.settings
        config = runtime.runtime_config
        executor = _DeferredTaskExecutor()
        adapter_executor = _AdapterExecutorAdapter(runtime.adapters)
        store = build_task_store(session)
        queue = TaskQueue()
        lease = LeaseService(
            store,
            lease_seconds=config.lease_seconds,
            heartbeat_seconds=config.heartbeat_seconds,
        )
        scheduler = Scheduler()
        progress = ProgressReporter(store, bus=runtime.bus)
        worker = TaskWorker(
            worker_id="worker-1",
            queue=queue,
            store=store,
            lease=lease,
            executor=executor,
            progress=progress,
            scheduler=scheduler,
            locks=runtime.locks,
            lock_policy=runtime.lock_policy,
            operations=operations,
            poll_interval=config.task_poll_interval_seconds,
            default_timeout_seconds=settings.task_default_timeout_seconds,
        )
        engine = TaskEngine(
            store,
            queue=queue,
            lease=lease,
            scheduler=scheduler,
            recovery=RecoveryService(store, operations),
            cancellation=CancellationService(store, runtime.adapters),
            progress=progress,
            worker=worker,
            operations=operations,
        )
        security = (
            build_security_services(
                build_security_stores(session),
                password_service=password_service,
                session_lifetime_seconds=settings.session_expire_seconds,
            )
            if password_service is not None
            else self.security_for(session)
        )
        resource_store = build_resource_store(session)
        resolver = ResourceResolver(resource_store, tenant_access=security.tenant_access)
        capabilities = CapabilityResolver(
            capabilities_registry,
            resource_store,
            cache_ttl_seconds=settings.capability_cache_seconds,
            runtime=runtime.adapters,
        )
        artifacts = ArtifactService(
            build_artifact_store(session),
            runtime.storage.backend(),
            storage_backend=runtime.storage.default_backend,
        )
        results = ResultService()
        audit = AuditService(build_audit_store(session), lock=runtime.chain_lock)
        pipeline = ExecutionPipeline(
            operations=operations,
            schema=SchemaEngine(runtime.schema_registry or SchemaRegistry()),
            engineering=EngineeringValidator(),
            preconditions=PreconditionEvaluator(),
            postconditions=PostconditionEvaluator(),
            permissions=security.permissions,
            confirmation=runtime.confirmation_guard,
            idempotency=IdempotencyService(build_idempotency_store(session)),
            resolver=resolver,
            locks=runtime.locks,
            lock_policy=runtime.lock_policy,
            capabilities=capabilities,
            quota=runtime.quota,
            normalizer=_result_normalizer(results),
        )
        service = ExecutionService(
            pipeline=pipeline,
            tasks=engine,
            adapters=adapter_executor,
            audit=audit,
            trace=runtime.trace,
            metrics=runtime.metrics,
            events=runtime.bus,
            outbox=runtime.outbox,
            results=results,
        )
        executor.bind(service)
        return ExecutionSession(
            service=service,
            pipeline=pipeline,
            engine=engine,
            worker=worker,
            queue=queue,
            security=security,
            resolver=resolver,
            capabilities=capabilities,
            artifacts=artifacts,
            documents=DocumentService(
                build_document_store(session),
                build_document_version_store(),
                artifacts=artifacts,
            ),
            models=ModelService(_AdapterModelQuery(adapter_executor)),
            results=results,
            adapter_resolver=AdapterResolver(
                runtime.adapters,
                instances=resource_store,
                capabilities=capabilities,
            ),
            audit=audit,
            backup=BackupService(
                database_path=_database_path(settings),
                artifact_root=settings.artifact_root,
                artifacts=build_artifact_store(session),
                storage=runtime.storage.backend(),
            ),
            restore=RestoreService(
                backup=BackupService(
                    database_path=_database_path(settings),
                    artifact_root=settings.artifact_root,
                    artifacts=build_artifact_store(session),
                    storage=runtime.storage.backend(),
                ),
                database_path=_database_path(settings),
                artifact_root=settings.artifact_root,
                storage=runtime.storage.backend(),
            ),
            retention=RetentionService(
                artifacts=build_artifact_store(session),
                storage=runtime.storage.backend(),
            ),
        )


# ===== P29–P36：启动装配与健康检查器（`docs/02` §17 / §54 / §94；`docs/07` §14.4）=====


def _database_path(settings: Settings) -> str:
    """从 `database_url` 取数据库文件路径（`docs/02` §21 的备份源）。"""
    return str(make_url(settings.database_url).database or "")


async def _database_check(engine: AsyncEngine) -> Mapping[str, Any]:
    """数据库检查器（`docs/02` §16.2 / §94）：一次 `SELECT 1`。"""
    try:
        async with engine.connect() as connection:
            result = await connection.exec_driver_sql("SELECT 1")
            result.scalar_one()
    except Exception as error:
        return {"status": str(HealthStatus.UNAVAILABLE), "reason": type(error).__name__}
    return {"status": str(HealthStatus.HEALTHY)}


async def _registry_check(runtime: ExecutionRuntime) -> Mapping[str, Any]:
    """Registry 检查器（`docs/07` §14.4：校验失败 → MUST NOT become READY）。"""
    if not runtime.ready():
        return {"status": str(HealthStatus.UNAVAILABLE), "reason": "registry_not_assembled"}
    operations = runtime.operation_registry
    definitions = await operations.list() if operations is not None else []
    return {"status": str(HealthStatus.HEALTHY), "operations": len(definitions)}


async def _task_engine_check(engine: AsyncEngine) -> Mapping[str, Any]:
    """任务引擎检查器（`docs/02` §16.2）：`tasks` 表可达即 UP。"""
    try:
        async with engine.connect() as connection:
            result = await connection.exec_driver_sql("SELECT count(*) FROM tasks")
            result.scalar_one()
    except Exception as error:
        return {"status": str(HealthStatus.UNAVAILABLE), "reason": type(error).__name__}
    return {"status": str(HealthStatus.HEALTHY)}


async def _adapter_manager_check(runtime: ExecutionRuntime) -> Mapping[str, Any]:
    """Adapter Manager 检查器（**非关键**；`docs/02` §16.3 / §94）。

    单个软件不可用只让整体 `DEGRADED`，**绝不**让 Core DOWN（`docs/07` §14.4）。
    """
    instances = tuple(runtime.adapters.bound_instance_ids())
    if not instances:
        return {"status": str(HealthStatus.DEGRADED), "reason": "no_instances"}
    reports = await runtime.adapters.health_check_all()
    unhealthy = sorted(str(key) for key, value in reports.items() if not value.get("healthy"))
    if unhealthy:
        return {"status": str(HealthStatus.DEGRADED), "unavailable": unhealthy}
    return {"status": str(HealthStatus.HEALTHY), "instances": len(instances)}


async def _software_instances_check(runtime: ExecutionRuntime) -> Mapping[str, Any]:
    """软件实例检查器（**非关键**；`docs/02` §94）。"""
    instances = tuple(runtime.adapters.bound_instance_ids())
    if not instances:
        return {"status": str(HealthStatus.DEGRADED), "reason": "no_instances"}
    return {"status": str(HealthStatus.HEALTHY), "instances": len(instances)}


async def register_health_checkers(runtime: ExecutionRuntime, engine: AsyncEngine) -> None:
    """把真实检查器注入健康 Registry（`docs/02` §17 / §94）。

    `database` / `registry` / `task_engine` 是**关键**检查（`docs/02` §16.2 的 `/readyz`）；
    `adapter_manager` / `software_instances` 是**非关键**检查（§94 的 `/health`）。
    """
    runtime.health_registry.register(
        "database",
        CallableHealthChecker("database", lambda: _database_check(engine)),
    )
    runtime.health_registry.register(
        "registry",
        CallableHealthChecker("registry", lambda: _registry_check(runtime)),
    )
    runtime.health_registry.register(
        "task_engine",
        CallableHealthChecker("task_engine", lambda: _task_engine_check(engine)),
    )
    runtime.health_registry.register(
        "adapter_manager",
        CallableHealthChecker(
            "adapter_manager",
            lambda: _adapter_manager_check(runtime),
            critical=False,
        ),
    )
    runtime.health_registry.register(
        "software_instances",
        CallableHealthChecker(
            "software_instances",
            lambda: _software_instances_check(runtime),
            critical=False,
        ),
    )


async def bind_mock_instances(
    runtime: ExecutionRuntime,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[str, ...]:
    """把已配备的 Mock 软件实例绑定到 `MockAdapter`（`docs/02` §54 的启动序列）。

    只绑定 `software_instances` 里 vendor / product 与已注册 Manifest 一致的实例
    （`docs/07` §4.3 #10–#13 的四级软件注册表）；绑定或连接失败**不**抛出
    （`docs/07` §14.4：单实例失败不得让整个服务器不可用）。

    Returns:
        成功绑定并连接的实例 id 元组。
    """
    keys = tuple(runtime.adapters.registered_keys())
    if not keys:
        return ()
    vendor, product = keys[0]
    try:
        async with session_factory() as session:
            statement = (
                select(SoftwareInstanceORM.id)
                .join(
                    SoftwareVersionORM,
                    SoftwareVersionORM.id == SoftwareInstanceORM.version_id,
                )
                .join(
                    SoftwareProductORM,
                    SoftwareProductORM.id == SoftwareVersionORM.product_id,
                )
                .join(SoftwareORM, SoftwareORM.id == SoftwareProductORM.software_id)
                .where(SoftwareORM.vendor == vendor)
            )
            instance_ids = tuple(
                str(value) for value in (await session.execute(statement)).scalars()
            )
    except Exception:
        logger.warning("could not enumerate software instances for the mock adapter")
        return ()
    bound: list[str] = []
    for instance_id in instance_ids:
        try:
            runtime.adapters.bind_instance(instance_id, vendor=vendor, product=product)
            await runtime.adapters.connect(instance_id)
        except Exception:
            logger.warning("could not bind software instance %s to the mock adapter", instance_id)
            continue
        bound.append(instance_id)
    if bound:
        await _mark_instances_connected(session_factory, bound)
    return tuple(bound)


async def resolve_local_identity(
    session_factory: async_sessionmaker[AsyncSession],
) -> MCPIdentity:
    """解析 STDIO 的**本地可信身份**（`docs/03` §11；`docs/07` §8.1）。

    本地 STDIO 允许 *local trusted identity*，但 `docs/03` §11 明确「**不得**因为
    STDIO 是本地连接就绕过 RBAC / Tenant Isolation / Audit」，故这里仍然
    **只**从已配备的种子数据里取服务端事实（`docs/02` §43 / §44 的引导管理员），
    并如实标注 `authentication_method = LOCAL`。

    Args:
        session_factory: 进程级会话工厂（`AppContainer.session_factory`）。

    Returns:
        `MCPIdentity`（身份 ＋ 该身份的有效权限快照）。

    Raises:
        InternalError: `STRUCTAI-7000` —— 数据库未配备 / 没有可用管理员
            （**绝不**回落成匿名身份）。
    """
    from app.application.execution.identity import local_identity
    from app.application.security import build_security_services
    from app.application.security.context import (
        AUTHENTICATION_METHOD_LOCAL,
        IdentityContext,
    )
    from app.infrastructure.database.models.user import UserORM

    try:
        async with session_factory() as session:
            user = (await session.execute(select(UserORM))).scalars().first()
            if user is None:
                raise InternalError(
                    "No seeded user is available for the local stdio identity",
                    details={"stage": "container", "reason": "local_identity_missing"},
                )
            security = build_security_services(
                build_security_stores(session),
                password_service=PasswordService(),
            )
            identity = IdentityContext(
                user_id=UUID(str(user.id)),
                tenant_id=UUID(str(user.tenant_id)),
                roles=tuple(await security.roles.get_user_roles(str(user.id))),
                authentication_method=AUTHENTICATION_METHOD_LOCAL,
            )
            permissions = await security.permissions.get_permissions(identity)
    except InternalError:
        raise
    except Exception as error:
        raise InternalError(
            "Could not resolve the local stdio identity: database is not provisioned",
            details={"stage": "container", "reason": "local_identity_unavailable"},
        ) from error
    return local_identity(identity, permissions=permissions)


async def _mark_instances_connected(
    session_factory: async_sessionmaker[AsyncSession],
    instance_ids: Sequence[str],
) -> None:
    """把已连接的实例状态写回软件注册表（`docs/02` §19 的连接生命周期）。

    ⚠️ 只有 `UnitOfWork` 能提交（`docs/02` §16）：这里用
    `UnitOfWork.from_session_factory(...)`。写的是**数据**
    （`software_instances.status`），**不**是 schema —— `docs/07` §14.3 禁止的是
    「启动时静默 `ALTER TABLE`」，不是状态更新。写入失败只告警
    （`docs/07` §14.4：单实例失败不得让整个服务器不可用）。
    """
    try:
        async with UnitOfWork.from_session_factory(session_factory) as uow:
            await uow.session.execute(
                update(SoftwareInstanceORM)
                .where(SoftwareInstanceORM.id.in_(list(instance_ids)))
                .values(status=str(SoftwareConnectionState.CONNECTED))
            )
    except Exception:
        logger.warning("could not persist the software instance connection state")
