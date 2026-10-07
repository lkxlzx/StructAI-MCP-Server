"""Alembic 环境（`docs/07` §12 P119 门槛 ⑦ / §14.3）。

权威来源
--------
- `docs/07` §12 P119 门槛 ⑦ —— 「**若**新增 MIDAS 表，必须走 Alembic 迁移，
  并同步更新建表断言与 `docs/07` §4.3 / §4.4」。
- `docs/07` §14.3 —— **禁止启动时静默 `ALTER TABLE`**：改表必须走 Alembic。
- `docs/02` §14（base）—— 约束命名约定复用 Core 的 `NAMING_CONVENTION`
  （`midas/models.py` 的 `MIDAS_METADATA` 即用它构造）。

落地裁决（只补实现手段）
----------------------
1. **`target_metadata` 同时含 Core 与 MIDAS 两套**：autogenerate 能同时看到 24 + 7 张表，
   但本批**只**提供一条**显式**迁移（`0001_midas_registry_tables`），只创建 MIDAS 的
   7 张表 —— Core 的 24 张表由既有 `Base.metadata.create_all` 路径负责，
   **不**在本迁移里重复创建。
2. **连接串来自 `Settings`**（`DATABASE_URL`），不在 `alembic.ini` 里写死。
3. **异步引擎**：项目全链路 async（`docs/07` §3.1），故用
   `async_engine_from_config` + `run_sync`（Alembic 官方 async 配方）。
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config.settings import Settings
from app.infrastructure.adapters.midas.models import MIDAS_METADATA
from app.infrastructure.database.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", Settings().database_url)

target_metadata = [Base.metadata, MIDAS_METADATA]
"""Core 的 24 张表 + MIDAS 的 7 张表（见模块裁决 1）。"""


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL（`--sql`）。"""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """在给定连接上执行迁移。"""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """在线模式：建异步引擎并在同步回调里跑迁移。"""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """在线模式入口。"""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()