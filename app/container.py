"""应用容器（P01 Bootstrap / P02 Config / P03 Domain / P04 Database / P05 Repository /
P06 UnitOfWork / P07 Seed / P08 Registry / P09 Schema / P10–P13 Security /
P14–P18 Execution / P19–P20 Adapters / P21 Idempotency）。

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
from dataclasses import dataclass, field
from typing import Any, Final

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config.runtime_config import RuntimeConfig, build_runtime_config
from app.config.settings import Settings
from app.infrastructure.database.session import (
    create_engine,
    create_session_factory,
    verify_connection,
)
from app.infrastructure.registry.operation_registry import OperationRegistry

__all__ = ["BATCH_ID", "AppContainer", "build_container"]

BATCH_ID: Final[str] = "P21"

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
