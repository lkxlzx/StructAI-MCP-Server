"""P05 Repository 验收测试夹具（`docs/02` §40；`docs/07` §12 P05）。

- 每个测试使用**独立的临时 SQLite 文件库**：先 `Base.metadata.create_all`
  （`docs/07` §12 P04 的建表入口），再逐 Repository 跑 CRUD。
- 引擎与会话工厂一律走被测代码自身（`create_engine` / `create_session_factory`），
  从而同时覆盖 SQLite 目录创建与连接级 `PRAGMA foreign_keys=ON`（`docs/02` §36）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.infrastructure.database import Base, create_engine, create_session_factory


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    """临时文件库 + 建表（`docs/02` §15 / §36）。"""
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p05_repository.db').as_posix()}"
    engine = create_engine(database_url)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """会话工厂（`expire_on_commit=False` / `autoflush=False`，`docs/02` §15）。"""
    return create_session_factory(engine)
