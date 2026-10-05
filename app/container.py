"""应用容器（P01 Bootstrap / P02 Config / P03 Domain / P04 Database / P05 Repository /
P06 UnitOfWork / P07 Seed）。

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
| `operation_registry` | P08 |
| `execution_service` | P36 |

生命周期（`docs/02` §34 / §79 / §80）：

    build_container(settings)   → 装配 engine / session_factory（不做连接 I/O）
    await container.startup()   → 建立并校验数据库连接
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

__all__ = ["BATCH_ID", "AppContainer", "build_container"]

BATCH_ID: Final[str] = "P07"

logger = logging.getLogger("structai")


@dataclass(slots=True)
class AppContainer:
    """应用依赖容器。

    P04：`settings` / `runtime_config` / `engine` / `session_factory` 已接入；
    P05：仓储**不**在此装配 —— 仓储持有 `AsyncSession`，属会话级对象，
    由 `build_repositories(session)` 装配（`docs/02` §16 / §33）；
    P06：`UnitOfWork` 同理**不**在此装配 —— 它持有同一个会话，由调用方按业务事务
    构造（`docs/02` §16：一个业务事务 = 一个明确 UnitOfWork）；
    `operation_registry` / `execution_service` 仍为空（后续批次填充）。
    `started` 仅表示生命周期已进入运行态。
    """

    settings: Settings
    runtime_config: RuntimeConfig
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    operation_registry: Any = None
    execution_service: Any = None
    started: bool = field(default=False, repr=False)

    async def startup(self) -> None:
        """启动钩子：建立并校验数据库连接（P04）。

        - 只做连接与一次 `SELECT 1` 连通性校验；**不建表、不改表**
          （`docs/07` §14.3：禁止启动时静默 `ALTER TABLE`）。
        - 连接失败即抛异常，进程以非 0 退出码结束 —— 不允许「带病启动」。
        - P08：Registry 校验失败时 Server 不得进入 READY（`docs/07` §14.4）。
        """
        await verify_connection(self.engine)

        self.started = True
        logger.info(
            "database connection established: %s",
            make_url(self.settings.database_url).render_as_string(hide_password=True),
        )

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
    P08 起装配 `operation_registry`。

    ⚠️ 本函数**不建立连接**（只构造引擎），连接与校验由 `startup()` 完成；
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
