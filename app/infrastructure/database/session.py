"""AsyncEngine / Session 工厂（`docs/02` §15；`docs/02` §2.2 异步模型；§36 SQLite 特别处理）。

权威来源：

- `docs/02` §15（`source9` §15）—— `create_engine(database_url, *, echo=False)` 与
  `create_session_factory(engine)`，签名与参数逐项照抄：
  `echo=echo` · `future=True` · `expire_on_commit=False` · `autoflush=False`。
- `docs/02` §2.2 —— 数据库访问统一走 SQLAlchemy AsyncIO + aiosqlite（全链路异步）。
- `docs/02` §36 —— SQLite 特别处理：`PRAGMA foreign_keys=ON` 通过 SQLAlchemy event
  在**引擎层**设置一次，**不要在每个 Repository 中重复设置**。
- `docs/07` §3.1 —— Core Alpha = SQLite(aiosqlite)；生产可切 PostgreSQL（仅换 URL）。

本文件在规范之上的补充（只解决「首次运行必然失败」的可复现问题，不改变接口口径）：

- `_ensure_sqlite_directory` —— 默认 `DATABASE_URL` 指向 `./data/structai.db`，
  而 SQLite 不会自动创建父目录；父目录缺失时连接直接失败。该逻辑放在引擎工厂，
  与 `PRAGMA` 同层（`docs/02` §36 的「SQLite 特别处理」），Repository 不感知。
- 非 SQLite URL（PostgreSQL 等）一律不做任何特殊处理。

禁止项（`docs/07` §14.3）：本模块**不得**执行 `ALTER TABLE`，也**不得**在日志中
输出连接串中的凭据；本批次只提供建表入口 `Base.metadata.create_all`（由调用方显式触发）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

__all__ = ["create_engine", "create_session_factory", "verify_connection"]

_MEMORY_DATABASES = frozenset({":memory:", ""})


def _ensure_sqlite_directory(database_url: str) -> None:
    """SQLite 文件库：确保数据库文件所在目录存在（`docs/02` §36）。

    - 非 SQLite URL 直接返回（PostgreSQL 由服务端管理）。
    - 内存库（`sqlite+aiosqlite:///:memory:`）与匿名库直接返回。
    """
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite"):
        return

    database = url.database
    if database is None or database in _MEMORY_DATABASES:
        return

    Path(database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def _sqlite_on_connect(dbapi_connection: Any, _connection_record: Any) -> None:
    """SQLite 连接建立时的 PRAGMA 设置（`docs/02` §36）。

    `PRAGMA foreign_keys=ON` 是 SQLite 的**每连接**设置；只在引擎层挂一次，
    禁止在各 Repository 中重复设置（`docs/02` §36）。
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        # `docs/02` §36（连接级 PRAGMA）：WAL 让「一个写连接 + 多个读连接」可以共存 ——
        # 这是 P40 / P41 传输层上线后的**必要**前提：MCP 的每个请求开自己的会话
        # （`docs/02` §16 / §33），而长任务的 Worker 会与后续请求的写入并发。
        # 没有 WAL 时 SQLite 的默认日志模式会让第二个写入者撞上 `database is locked`
        # （`busy_timeout` 只有 5 秒，长任务远超这个窗口）。
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
    finally:
        cursor.close()


def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """创建 `AsyncEngine`（`docs/02` §15）。

    Args:
        database_url: 形如 `sqlite+aiosqlite:///./data/structai.db`
            （`docs/07` §3.1：Core Alpha = SQLite；生产可切 PostgreSQL）。
        echo: 是否回显 SQL（来自 `Settings.sql_echo`，`docs/02` §5.1）。

    Returns:
        已配置好命名约定元数据之外的连接级行为（SQLite PRAGMA）的异步引擎。
    """
    _ensure_sqlite_directory(database_url)

    engine = create_async_engine(
        database_url,
        echo=echo,
        future=True,
    )

    if make_url(database_url).drivername.startswith("sqlite"):
        event.listen(engine.sync_engine, "connect", _sqlite_on_connect)

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """创建会话工厂（`docs/02` §15）。

    - `expire_on_commit=False` —— 提交后对象仍可读，避免 Application 层隐式懒加载。
    - `autoflush=False` —— 事务边界由 UnitOfWork 显式控制（`docs/07` §14.4：
      Repository 不得自行 `commit`）。
    """
    return async_sessionmaker(
        engine,
        expire_on_commit=False,
        autoflush=False,
    )


async def verify_connection(engine: AsyncEngine) -> None:
    """建立并校验数据库连接（容器 `startup()` 使用；`docs/02` §37）。

    只做一次 `SELECT 1` 连通性校验：**不建表、不改表**
    （`docs/07` §14.3：禁止启动时静默 `ALTER TABLE`）。
    连接失败直接抛异常，由调用方决定进程退出码 —— 不允许「带病启动」。
    """
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
