"""P06 验收测试：UnitOfWork —— 事务边界 / 上下文管理 / 会话释放（`docs/07` §12 P06）。

对应 `docs/02` §42（UnitOfWork Commit Test）/ §43（Rollback Test）。验收点：

① 事务：`commit` 后**新会话可见**；`rollback`（异常或显式）后**新会话不可见**；
② 上下文管理：`async with UnitOfWork(session)` 正常退出 → `commit`；
   异常退出 → `rollback` 且**原异常继续向上抛**（不吞 / 不替换）；
③ `close`：会话释放、连接归还连接池，`await engine.dispose()` 无泄漏；
④ 与仓储协作：同一 UoW 内用 `build_repositories(session)` 跨表写入多个实体，
   成功一起可见、失败一起不可见（原子性）；Repository 仍**不得**自行 `commit`
   （`docs/07` §14.4）—— 提交前另一会话看不到，回滚后本会话也看不到。

全部测试使用临时 SQLite 文件库（`tests/conftest.py`），被测路径只用 `UnitOfWork`
与仓储 API；`session.commit()` 只出现在测试自身的**前置数据**准备（`_seed`）中。
"""

from __future__ import annotations

import asyncio
from typing import cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import QueuePool

from app.domain.protocols import UnitOfWork as DomainUnitOfWork
from app.infrastructure.database.models import ProjectORM, TenantORM, UserORM
from app.infrastructure.database.repositories import (
    TenantRepository,
    build_repositories,
)
from app.infrastructure.database.unit_of_work import UnitOfWork

SessionFactory = async_sessionmaker[AsyncSession]
"""会话工厂类型别名（`docs/02` §15）。"""

TENANT_A = "11111111-1111-4111-8111-111111111111"
TENANT_B = "22222222-2222-4222-8222-222222222222"


def _domain_uow(unit_of_work: UnitOfWork) -> DomainUnitOfWork:
    """结构性子类型断言：`UnitOfWork` 满足 `docs/02` §11 的 Domain 契约。

    纯类型层面的检查（由 `mypy` 保证）：返回类型是 `app.domain.protocols.UnitOfWork`，
    因此 `UnitOfWork` 必须实现 `commit` / `rollback`，否则本文件无法通过类型检查。
    """
    return unit_of_work


def _checked_out(engine: AsyncEngine) -> int:
    """当前被借出的连接数（测试专用；`conftest` 用文件库 → `QueuePool`）。"""
    return cast("QueuePool", engine.pool).checkedout()


async def _seed(session_factory: SessionFactory, *entities: object) -> None:
    """写入前置数据（前置数据不是被测行为，故直接用会话提交）。"""
    async with session_factory() as session:
        session.add_all(list(entities))
        await session.commit()


# ===== ① + ② 上下文管理：正常退出 → commit =====


async def test_context_manager_commits_and_new_session_sees_it(
    session_factory: SessionFactory,
) -> None:
    """`async with UnitOfWork(session)` 正常退出 → `commit`；提交后新会话可见（§42）。"""
    async with session_factory() as session:
        unit_of_work = UnitOfWork(session)

        async with unit_of_work as active:
            assert active is unit_of_work
            # `docs/02` §11 的 Domain 契约（`commit` / `rollback`）
            assert _domain_uow(active) is active
            # 进入 UoW 不自行开启事务（事务由会话首次使用时自动开始）
            assert session.in_transaction() is False

            repositories = build_repositories(session)
            await repositories.tenant.add(TenantORM(id=TENANT_A, name="tenant-a"))

            assert session.in_transaction() is True

        # 正常退出 → 已 commit（事务结束，而不是仅 flush）
        assert session.in_transaction() is False

    async with session_factory() as session:
        loaded = await TenantRepository(session).get(TENANT_A)

        assert loaded is not None
        assert loaded.name == "tenant-a"


async def test_explicit_commit_inside_context_is_idempotent(
    session_factory: SessionFactory,
) -> None:
    """`docs/02` §35 的用法：块内显式 `commit()`，正常退出不得报错，数据可见。"""
    async with session_factory() as session:
        async with UnitOfWork(session) as unit_of_work:
            repositories = build_repositories(session)
            await repositories.tenant.add(TenantORM(id=TENANT_A, name="tenant-a"))
            await unit_of_work.commit()
            assert session.in_transaction() is False

    async with session_factory() as session:
        assert (await TenantRepository(session).get(TENANT_A)) is not None


# ===== ① + ② 异常退出 → rollback 且原异常继续向上抛 =====


async def test_exception_rolls_back_and_propagates_original(
    session_factory: SessionFactory,
) -> None:
    """异常退出 → `rollback`；**原异常对象**继续向上抛（不吞、不替换，§43）。"""
    original = RuntimeError("force rollback")

    async with session_factory() as session:
        unit_of_work = UnitOfWork(session)

        with pytest.raises(RuntimeError) as excinfo:
            async with unit_of_work:
                repositories = build_repositories(session)
                await repositories.tenant.add(TenantORM(id=TENANT_A, name="tenant-a"))
                raise original

        # 同一个异常对象、同一条消息（既没被吞掉，也没被换成别的异常）
        assert excinfo.value is original
        assert str(excinfo.value) == "force rollback"
        assert excinfo.type is RuntimeError
        # 回滚后会话仍可用（不是「坏掉的会话」）
        assert session.in_transaction() is False

    async with session_factory() as session:
        assert (await TenantRepository(session).get(TENANT_A)) is None


async def test_base_exception_rolls_back_and_propagates(
    session_factory: SessionFactory,
) -> None:
    """`BaseException`（如 `asyncio.CancelledError`）同样回滚并向上抛。"""
    async with session_factory() as session:
        with pytest.raises(asyncio.CancelledError):
            async with UnitOfWork(session):
                repositories = build_repositories(session)
                await repositories.tenant.add(TenantORM(id=TENANT_A, name="tenant-a"))
                raise asyncio.CancelledError

    async with session_factory() as session:
        assert (await TenantRepository(session).get(TENANT_A)) is None


async def test_explicit_rollback_discards_pending_changes(
    session_factory: SessionFactory,
) -> None:
    """显式 `rollback()`：挂起变更被丢弃，退出时的提交是空提交 → 新会话不可见。"""
    async with session_factory() as session:
        async with UnitOfWork(session) as unit_of_work:
            repositories = build_repositories(session)
            await repositories.tenant.add(TenantORM(id=TENANT_A, name="tenant-a"))
            assert session.in_transaction() is True

            await unit_of_work.rollback()

            assert session.in_transaction() is False

    async with session_factory() as session:
        assert (await TenantRepository(session).get(TENANT_A)) is None


# ===== ③ close：会话释放 / 连接归还连接池 =====


async def test_close_releases_session_and_returns_connection(
    engine: AsyncEngine,
    session_factory: SessionFactory,
) -> None:
    """`close()` 关闭会话、把连接归还连接池；`engine.dispose()` 无泄漏（§12 P06）。"""
    session = session_factory()
    await session.execute(text("SELECT 1"))

    assert _checked_out(engine) == 1

    unit_of_work = UnitOfWork(session)
    await unit_of_work.close()

    assert session.in_transaction() is False
    assert _checked_out(engine) == 0

    # 幂等：重复 close 安全
    await unit_of_work.close()
    assert _checked_out(engine) == 0

    # 没有未归还的连接 → dispose 不报错、不挂起
    await engine.dispose()
    assert _checked_out(engine) == 0


async def test_from_session_factory_owns_and_closes_session(
    engine: AsyncEngine,
    session_factory: SessionFactory,
) -> None:
    """`docs/02` §16（source7）的 `SQLAlchemyUnitOfWork`：会话由 UoW 创建并关闭。"""
    unit_of_work = UnitOfWork.from_session_factory(session_factory)
    owned_session = unit_of_work.session

    async with unit_of_work as active:
        assert active is unit_of_work
        repositories = build_repositories(owned_session)
        await repositories.tenant.add(TenantORM(id=TENANT_A, name="tenant-a"))

        assert _checked_out(engine) == 1

    # 退出即归还连接（会话由本 UoW 拥有）
    assert _checked_out(engine) == 0
    assert owned_session.in_transaction() is False

    async with session_factory() as session:
        assert (await TenantRepository(session).get(TENANT_A)) is not None


# ===== ④ 与仓储协作：跨表原子性 =====


async def test_repositories_never_commit_before_unit_of_work(
    session_factory: SessionFactory,
) -> None:
    """仓储只 `flush`：UoW 提交前，另一个会话看不到该行（`docs/07` §14.4）。"""
    async with session_factory() as session:
        async with UnitOfWork(session):
            repositories = build_repositories(session)
            await repositories.tenant.add(TenantORM(id=TENANT_A, name="tenant-a"))

            async with session_factory() as observer:
                assert (await TenantRepository(observer).get(TENANT_A)) is None


async def test_atomicity_across_tables_commit(session_factory: SessionFactory) -> None:
    """同一 UoW 内跨表写入 tenant / user / project → 成功一起可见。"""
    async with session_factory() as session:
        async with UnitOfWork(session):
            repositories = build_repositories(session)
            await repositories.tenant.add(TenantORM(id=TENANT_A, name="tenant-a"))
            await repositories.user.add(
                UserORM(tenant_id=TENANT_A, username="alice", password_hash="hash-a")
            )
            await repositories.project.add(ProjectORM(tenant_id=TENANT_A, name="bridge"))

    async with session_factory() as session:
        repositories = build_repositories(session)

        assert (await repositories.tenant.get(TENANT_A)) is not None
        assert (await repositories.user.get_by_username_for_tenant("alice", TENANT_A)) is not None
        assert len(await repositories.project.list_for_tenant(TENANT_A)) == 1


async def test_atomicity_across_tables_rollback(session_factory: SessionFactory) -> None:
    """同一 UoW 内跨表写入中途失败 → 三张表都不可见（原子性）；前置数据不受影响。"""
    await _seed(session_factory, TenantORM(id=TENANT_B, name="tenant-b"))

    with pytest.raises(RuntimeError, match="boom"):
        async with session_factory() as session:
            async with UnitOfWork(session):
                repositories = build_repositories(session)
                await repositories.tenant.add(TenantORM(id=TENANT_A, name="tenant-a"))
                await repositories.user.add(
                    UserORM(tenant_id=TENANT_A, username="alice", password_hash="hash-a")
                )
                await repositories.project.add(ProjectORM(tenant_id=TENANT_A, name="bridge"))

                raise RuntimeError("boom")

    async with session_factory() as session:
        repositories = build_repositories(session)

        # 失败的那个 UoW 的三张表写入一起不可见
        assert (await repositories.tenant.get(TENANT_A)) is None
        assert (await repositories.user.get_by_username_for_tenant("alice", TENANT_A)) is None
        assert await repositories.project.list_for_tenant(TENANT_A) == []

        # 回滚只影响本 UoW：此前已提交的前置数据仍在
        assert (await repositories.tenant.get(TENANT_B)) is not None
        assert [row.id for row in await repositories.tenant.list_all()] == [TENANT_B]
