"""P05 验收测试：Repository CRUD / 租户隔离 / 事务边界（`docs/07` §12 P05）。

对应 `docs/02` §40（Repository Test）与 §48（Tenant Isolation Test）。验收点：

① 逐 Repository 跑 `add → get → 更新 → remove/列表`，写回数据库后**原样读回**
   （含 `created_at` / `updated_at` / `version`）；
② 租户隔离：按 `tenant_id` 过滤的查询不得返回其他租户的行（`docs/02` §11）；
③ Repository **不得自行 `commit`**（`docs/07` §14.4）—— 只 `flush`。

全部测试使用临时 SQLite 文件库（`tests/conftest.py`），并只用仓储 API 读写；
`session.commit()` 只出现在**测试自身**（扮演 P06 UnitOfWork 的角色）。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.enums import SoftwareStatus, TaskStatus
from app.domain.errors import ConcurrencyConflictError, TenantAccessDeniedError
from app.infrastructure.database.models import (
    ModelORM,
    ProjectORM,
    SoftwareORM,
    TaskORM,
    TenantORM,
    UserORM,
)
from app.infrastructure.database.repositories import (
    ModelRepository,
    ProjectRepository,
    SoftwareRepository,
    TaskRepository,
    TenantRepository,
    UserRepository,
    build_repositories,
)

SessionFactory = async_sessionmaker[AsyncSession]
"""会话工厂类型别名（`docs/02` §15）。"""

TENANT_A = "11111111-1111-4111-8111-111111111111"
TENANT_B = "22222222-2222-4222-8222-222222222222"


def _utc(value: datetime) -> datetime:
    """归一化到 UTC 再比较。

    SQLite 的 `DATETIME` 不保留 `tzinfo`（`docs/02` §36 只规定 PRAGMA），
    因此「写回后原样读回」的比较必须先补齐时区，否则 aware / naive 永不相等。
    """
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def _seed(session_factory: SessionFactory, *entities: object) -> None:
    """写入前置数据（前置数据不是被测仓储的行为，故直接用会话提交）。"""
    async with session_factory() as session:
        session.add_all(list(entities))
        await session.commit()


async def _two_tenants(session_factory: SessionFactory) -> None:
    """建立 Tenant A / Tenant B（`docs/02` §48 的隔离场景）。"""
    await _seed(
        session_factory,
        TenantORM(id=TENANT_A, name="tenant-a"),
        TenantORM(id=TENANT_B, name="tenant-b"),
    )


# ===== ① CRUD 原样读回 =====


async def test_tenant_repository_crud_round_trip(session_factory: SessionFactory) -> None:
    """`tenants`：add → get → 更新 → 列表 → remove。"""
    async with session_factory() as session:
        repo = TenantRepository(session)
        tenant = TenantORM(id=TENANT_A, name="tenant-a")

        await repo.add(tenant)
        assert tenant.created_at is not None
        assert tenant.updated_at is not None
        await session.commit()

        created_at, updated_at = tenant.created_at, tenant.updated_at

    async with session_factory() as session:
        repo = TenantRepository(session)
        loaded = await repo.get(TENANT_A)

        assert loaded is not None
        assert loaded.name == "tenant-a"
        # 写回后可原样读回（`created_at` / `updated_at` 不是 Python 侧幻觉）
        assert _utc(loaded.created_at) == _utc(created_at)
        assert _utc(loaded.updated_at) == _utc(updated_at)

        assert (await repo.get_by_name("tenant-a")) is not None
        assert [row.id for row in await repo.list_all()] == [TENANT_A]

        await repo.update(loaded, name="tenant-a-renamed")
        await session.commit()

    async with session_factory() as session:
        repo = TenantRepository(session)
        loaded = await repo.get(TENANT_A)

        assert loaded is not None
        assert loaded.name == "tenant-a-renamed"
        # 更新发生在后续事务 → `updated_at` 必须真的被推进（`TimestampMixin.onupdate`）
        assert _utc(loaded.updated_at) > _utc(loaded.created_at)

        await repo.remove(loaded)
        await session.commit()

    async with session_factory() as session:
        repo = TenantRepository(session)
        assert (await repo.get(TENANT_A)) is None
        assert await repo.list_all() == []


async def test_user_repository_crud_and_tenant_isolation(
    session_factory: SessionFactory,
) -> None:
    """`users`：Tenant-owned —— A 租户的查询不得返回 B 租户的行（`docs/02` §11）。"""
    await _two_tenants(session_factory)

    async with session_factory() as session:
        repo = UserRepository(session)
        user_a = UserORM(tenant_id=TENANT_A, username="alice", password_hash="hash-a")
        user_b = UserORM(tenant_id=TENANT_B, username="bob", password_hash="hash-b")

        await repo.add(user_a)
        await repo.add(user_b)

        # P04 的列默认值确实落到数据库（`docs/07` §4.3 #2）
        assert user_a.is_active is True
        assert user_a.locked is False
        assert user_a.failed_login_count == 0
        await session.commit()

        user_a_id, user_b_id = user_a.id, user_b.id

    async with session_factory() as session:
        repo = UserRepository(session)

        assert (await repo.get_for_tenant(user_a_id, TENANT_A)) is not None
        # 跨租户：查询本身限制了 tenant_id，因此读不到（不是「读到再判断」）
        assert (await repo.get_for_tenant(user_b_id, TENANT_A)) is None
        assert (await repo.get_for_tenant(user_a_id, TENANT_B)) is None

        assert [row.id for row in await repo.list_for_tenant(TENANT_A)] == [user_a_id]
        assert [row.id for row in await repo.list_for_tenant(TENANT_B)] == [user_b_id]

        # 用户名查只提供租户内入口（`docs/02` §11；全局查会把过滤推给调用方）
        assert (await repo.get_by_username_for_tenant("bob", TENANT_A)) is None
        assert (await repo.get_by_username_for_tenant("bob", TENANT_B)) is not None

        # 跨租户删除不生效，且不区分「不存在 / 不属于本租户」（`docs/02` §48）
        assert (await repo.remove_for_tenant(user_b_id, TENANT_A)) is False
        await session.commit()

    async with session_factory() as session:
        repo = UserRepository(session)
        assert (await repo.get_for_tenant(user_b_id, TENANT_B)) is not None

        user_a = await repo.get_for_tenant(user_a_id, TENANT_A)
        assert user_a is not None
        await repo.update_for_tenant(user_a, TENANT_A, locked=True, failed_login_count=3)
        await session.commit()

    async with session_factory() as session:
        loaded = await UserRepository(session).get_for_tenant(user_a_id, TENANT_A)
        assert loaded is not None
        assert loaded.locked is True
        assert loaded.failed_login_count == 3
        assert _utc(loaded.updated_at) > _utc(loaded.created_at)
        # `users` 不是可变资源：没有 `version` 列（`docs/07` §4.3）
        assert not hasattr(loaded, "version")


async def test_project_repository_version_and_concurrency_conflict(
    session_factory: SessionFactory,
) -> None:
    """`projects`：可变资源 —— `version` 条件自增，冲突抛 `STRUCTAI-1300`（`docs/02` §12）。"""
    await _two_tenants(session_factory)

    async with session_factory() as session:
        repo = ProjectRepository(session)
        project = ProjectORM(tenant_id=TENANT_A, name="project-a")

        await repo.add(project)
        assert project.version == 1
        await session.commit()

        project_id = project.id

    async with session_factory() as session:
        repo = ProjectRepository(session)
        project = await repo.get_for_tenant(project_id, TENANT_A)
        assert project is not None

        await repo.update_for_tenant(project, TENANT_A, name="project-a-v2")
        assert project.version == 2
        await session.commit()

    async with session_factory() as session:
        repo = ProjectRepository(session)
        loaded = await repo.get_for_tenant(project_id, TENANT_A)

        assert loaded is not None
        assert (loaded.name, loaded.version) == ("project-a-v2", 2)
        assert _utc(loaded.updated_at) > _utc(loaded.created_at)
        # 租户隔离
        assert (await repo.get_for_tenant(project_id, TENANT_B)) is None
        assert await repo.list_for_tenant(TENANT_B) == []

    # 乐观并发：两个会话读到同一版本，后写者必须失败且不得覆盖
    async with session_factory() as first, session_factory() as second:
        repo_first = ProjectRepository(first)
        repo_second = ProjectRepository(second)
        entity_first = await repo_first.get_for_tenant(project_id, TENANT_A)
        entity_second = await repo_second.get_for_tenant(project_id, TENANT_A)
        assert entity_first is not None
        assert entity_second is not None
        assert entity_first.version == entity_second.version == 2

        await repo_first.update_for_tenant(entity_first, TENANT_A, name="from-first")
        await first.commit()

        with pytest.raises(ConcurrencyConflictError) as excinfo:
            await repo_second.update_for_tenant(entity_second, TENANT_A, name="from-second")
        assert excinfo.value.code == "STRUCTAI-1300"

        # 冲突时**不得**污染内存实体（UPDATE 使用 synchronize_session=False）
        assert (entity_second.name, entity_second.version) == ("project-a-v2", 2)
        await second.rollback()

    async with session_factory() as session:
        loaded = await ProjectRepository(session).get_for_tenant(project_id, TENANT_A)
        assert loaded is not None
        assert (loaded.name, loaded.version) == ("from-first", 3)


async def test_software_repository_crud(session_factory: SessionFactory) -> None:
    """`software`：软件无关的厂商级注册表（`docs/07` §14.5 / §4.3 #10）。"""
    async with session_factory() as session:
        repo = SoftwareRepository(session)
        software = SoftwareORM(
            vendor="VendorX",
            name="StructuralSolver",
            status=SoftwareStatus.REGISTERED.value,
        )

        await repo.add(software)
        await session.commit()

        software_id = software.id

    async with session_factory() as session:
        repo = SoftwareRepository(session)
        loaded = await repo.get(software_id)

        assert loaded is not None
        assert (loaded.vendor, loaded.name, loaded.status) == (
            "VendorX",
            "StructuralSolver",
            SoftwareStatus.REGISTERED.value,
        )
        assert [row.id for row in await repo.list_by_vendor("VendorX")] == [software_id]
        assert await repo.list_by_vendor("VendorY") == []

        await repo.update(loaded, status=SoftwareStatus.DISABLED.value)
        await session.commit()

    async with session_factory() as session:
        repo = SoftwareRepository(session)
        loaded = await repo.get(software_id)
        assert loaded is not None
        assert loaded.status == SoftwareStatus.DISABLED.value
        assert _utc(loaded.updated_at) > _utc(loaded.created_at)

        await repo.remove(loaded)
        await session.commit()

    async with session_factory() as session:
        repo = SoftwareRepository(session)
        assert (await repo.get(software_id)) is None
        assert await repo.list_all() == []


async def test_model_repository_crud_and_indirect_tenant_isolation(
    session_factory: SessionFactory,
) -> None:
    """`models` 无 `tenant_id` 列：租户过滤经 `projects` 追溯（`docs/02` §11 / §22）。"""
    await _two_tenants(session_factory)

    project_a = ProjectORM(tenant_id=TENANT_A, name="project-a")
    project_b = ProjectORM(tenant_id=TENANT_B, name="project-b")
    await _seed(session_factory, project_a, project_b)

    async with session_factory() as session:
        repo = ModelRepository(session)
        model_a = ModelORM(project_id=project_a.id, name="model-a")
        model_b = ModelORM(project_id=project_b.id, name="model-b")

        await repo.add(model_a)
        await repo.add(model_b)
        assert model_a.version == 1
        await session.commit()

        model_a_id, model_b_id = model_a.id, model_b.id

    async with session_factory() as session:
        repo = ModelRepository(session)

        # 间接租户隔离：A 租户看不到 B 租户项目下的模型
        assert (await repo.get_for_tenant(model_a_id, TENANT_A)) is not None
        assert (await repo.get_for_tenant(model_b_id, TENANT_A)) is None
        assert [row.id for row in await repo.list_for_tenant(TENANT_A)] == [model_a_id]
        assert [row.id for row in await repo.list_for_tenant(TENANT_B)] == [model_b_id]

        # `project_id` + `tenant_id` 必须同时限制（`docs/02` §11）
        assert [row.id for row in await repo.list_by_project(project_a.id, TENANT_A)] == [
            model_a_id
        ]
        assert await repo.list_by_project(project_a.id, TENANT_B) == []

        model_a = await repo.get_for_tenant(model_a_id, TENANT_A)
        assert model_a is not None
        await repo.update_for_tenant(model_a, TENANT_A, name="model-a-v2")
        assert model_a.version == 2
        await session.commit()

    async with session_factory() as session:
        repo = ModelRepository(session)
        loaded = await repo.get_for_tenant(model_a_id, TENANT_A)

        assert loaded is not None
        assert (loaded.name, loaded.version) == ("model-a-v2", 2)
        assert _utc(loaded.updated_at) > _utc(loaded.created_at)
        assert (await repo.get_for_tenant(model_a_id, TENANT_B)) is None

        # 跨租户删除不生效
        assert (await repo.remove_for_tenant(model_a_id, TENANT_B)) is False
        await session.commit()

    async with session_factory() as session:
        repo = ModelRepository(session)
        assert (await repo.get_for_tenant(model_a_id, TENANT_A)) is not None


async def test_task_repository_crud_and_tenant_isolation(
    session_factory: SessionFactory,
) -> None:
    """`tasks`：Tenant-owned + 可变资源；列表必须分页（`docs/07` §14.4）。"""
    await _two_tenants(session_factory)

    project_a = ProjectORM(tenant_id=TENANT_A, name="project-a")
    await _seed(session_factory, project_a)

    async with session_factory() as session:
        repo = TaskRepository(session)
        task = TaskORM(
            tenant_id=TENANT_A,
            project_id=project_a.id,
            request_id="req-p05-1",
            trace_id="trace-p05-1",
            tool="engineering_model_build",
            operation="BUILD.COLUMN",
            status=TaskStatus.QUEUED.value,
            priority=100,
        )

        await repo.add(task)
        assert task.progress == 0
        assert task.version == 1
        assert task.lease_owner is None
        assert task.cancel_requested is False
        await session.commit()

        task_id = task.id

    async with session_factory() as session:
        repo = TaskRepository(session)

        assert (await repo.get_for_tenant(task_id, TENANT_A)) is not None
        assert (await repo.get_for_tenant(task_id, TENANT_B)) is None
        assert await repo.list_for_tenant(TENANT_B) == []
        assert [row.id for row in await repo.list_by_project(project_a.id, TENANT_A)] == [task_id]
        assert await repo.list_by_project(project_a.id, TENANT_B) == []
        assert [row.id for row in await repo.list_by_status(TaskStatus.QUEUED.value, TENANT_A)] == [
            task_id
        ]
        assert await repo.list_by_status(TaskStatus.RUNNING.value, TENANT_A) == []

        task = await repo.get_for_tenant(task_id, TENANT_A)
        assert task is not None
        await repo.update_for_tenant(
            task,
            TENANT_A,
            status=TaskStatus.RUNNING.value,
            progress=10,
        )
        assert task.version == 2
        await session.commit()

    async with session_factory() as session:
        repo = TaskRepository(session)
        loaded = await repo.get_for_tenant(task_id, TENANT_A)

        assert loaded is not None
        assert (loaded.status, loaded.progress, loaded.version) == (
            TaskStatus.RUNNING.value,
            10,
            2,
        )
        assert _utc(loaded.updated_at) > _utc(loaded.created_at)

        # 分页（`docs/07` §14.4：禁止无限 payload）
        assert len(await repo.list_for_tenant(TENANT_A, limit=1)) == 1
        assert await repo.list_for_tenant(TENANT_A, offset=1) == []

        await repo.remove(loaded)
        await session.commit()

    async with session_factory() as session:
        repo = TaskRepository(session)
        assert (await repo.get_for_tenant(task_id, TENANT_A)) is None


# ===== ② 租户隔离的强制口径 =====


async def test_tenant_scoped_read_requires_tenant_id(
    session_factory: SessionFactory,
) -> None:
    """Tenant-owned 实体**不允许**无租户过滤的读取（`docs/02` §11）。"""
    await _two_tenants(session_factory)

    async with session_factory() as session:
        repo = UserRepository(session)
        user_b = await repo.add(UserORM(tenant_id=TENANT_B, username="bob", password_hash="hash-b"))
        await session.commit()
        user_b_id = user_b.id

    async with session_factory() as session:
        repo = UserRepository(session)

        with pytest.raises(ValueError, match="tenant_id is required"):
            await repo.get(user_b_id)
        with pytest.raises(ValueError, match="tenant_id is required"):
            await repo.list_all()

        # 带上租户才能读；跨租户读不到
        assert (await repo.get(user_b_id, tenant_id=TENANT_B)) is not None
        assert (await repo.get(user_b_id, tenant_id=TENANT_A)) is None
        assert await repo.list_all(tenant_id=TENANT_A) == []
        assert [row.id for row in await repo.list_all(tenant_id=TENANT_B)] == [user_b_id]


async def test_update_for_tenant_rejects_cross_tenant_write(
    session_factory: SessionFactory,
) -> None:
    """跨租户写必须被拒绝：`STRUCTAI-4200`，且不区分「不存在 / 不属于本租户」。"""
    await _two_tenants(session_factory)
    project_b = ProjectORM(tenant_id=TENANT_B, name="project-b")
    await _seed(session_factory, project_b)

    async with session_factory() as session:
        repo = ProjectRepository(session)
        entity = await repo.get_for_tenant(project_b.id, TENANT_B)
        assert entity is not None

        with pytest.raises(TenantAccessDeniedError) as excinfo:
            await repo.update_for_tenant(entity, TENANT_A, name="hijacked")
        assert excinfo.value.code == "STRUCTAI-4200"
        await session.rollback()

    async with session_factory() as session:
        loaded = await ProjectRepository(session).get_for_tenant(project_b.id, TENANT_B)
        assert loaded is not None
        assert (loaded.name, loaded.version) == ("project-b", 1)


async def test_update_rejects_unknown_and_immutable_columns(
    session_factory: SessionFactory,
) -> None:
    """`update` 只接受真实列，且不得触碰受保护列（`docs/02` §12 / §26）。"""
    # 本测试只验证列校验；不预置租户行（`tenants.name` 唯一，避免与其它测试同名冲突）

    async with session_factory() as session:
        tenant_repo = TenantRepository(session)
        tenant = await tenant_repo.add(TenantORM(id=TENANT_A, name="tenant-a"))

        with pytest.raises(ValueError, match="immutable column"):
            await tenant_repo.update(tenant, id=TENANT_B)
        with pytest.raises(ValueError, match="unknown column"):
            await tenant_repo.update(tenant, nope="x")

        project_repo = ProjectRepository(session)
        project = await project_repo.add(ProjectORM(tenant_id=TENANT_A, name="project-a"))

        # `version` 由条件更新自增；`tenant_id` 不得改（否则等于跨租户搬行）
        with pytest.raises(ValueError, match="immutable column"):
            await project_repo.update_for_tenant(project, TENANT_A, version=99)
        # ⚠️ `update_for_tenant` 的 `tenant_id` 形参会与同名列冲突（TypeError），
        # 因此用底层 `update` 验证 `tenant_id` 受保护列在菱形继承下仍然生效
        with pytest.raises(ValueError, match="immutable column"):
            await project_repo.update(project, tenant_id=TENANT_B)
        await session.rollback()


# ===== ③ 事务边界：Repository 不得自行 commit =====


async def test_repository_does_not_commit(session_factory: SessionFactory) -> None:
    """`docs/07` §14.4：Repository 只 `flush` / `UPDATE`，提交 / 回滚归上层（P06 UnitOfWork）。"""
    # add：回滚后不可见
    async with session_factory() as session:
        repo = TenantRepository(session)
        tenant = await repo.add(TenantORM(id=TENANT_A, name="tenant-a"))

        # 已 flush：同一事务内可见
        assert (await repo.get(TENANT_A)) is not None
        await repo.update(tenant, name="tenant-a-renamed")
        await session.rollback()

    async with session_factory() as session:
        # 若 Repository 曾自行 commit，这里必然读得到
        assert (await TenantRepository(session).get(TENANT_A)) is None

    # remove：回滚后行仍在
    await _seed(session_factory, TenantORM(id=TENANT_B, name="tenant-b"))

    async with session_factory() as session:
        repo = TenantRepository(session)
        loaded = await repo.get(TENANT_B)
        assert loaded is not None
        await repo.remove(loaded)
        assert (await repo.get(TENANT_B)) is None
        await session.rollback()

    async with session_factory() as session:
        assert (await TenantRepository(session).get(TENANT_B)) is not None

    # 可变资源的条件更新：回滚后回到原值
    async with session_factory() as session:
        project = await ProjectRepository(session).add(
            ProjectORM(tenant_id=TENANT_A, name="project-a")
        )
        await session.commit()
        project_id = project.id

    async with session_factory() as session:
        repo = ProjectRepository(session)
        loaded = await repo.get_for_tenant(project_id, TENANT_A)
        assert loaded is not None
        await repo.update_for_tenant(loaded, TENANT_A, name="project-a-v2")
        assert loaded.version == 2
        await session.rollback()

    async with session_factory() as session:
        loaded = await ProjectRepository(session).get_for_tenant(project_id, TENANT_A)
        assert loaded is not None
        assert (loaded.name, loaded.version) == ("project-a", 1)


async def test_build_repositories_shares_one_session(
    session_factory: SessionFactory,
) -> None:
    """`build_repositories` 把 6 个仓储绑到**同一个会话**（`docs/02` §16 / §33）。"""
    async with session_factory() as session:
        bundle = build_repositories(session)

        repos = (
            bundle.tenant,
            bundle.user,
            bundle.project,
            bundle.software,
            bundle.model,
            bundle.task,
        )
        assert {id(repo.session) for repo in repos} == {id(session)}

        await bundle.tenant.add(TenantORM(id=TENANT_A, name="tenant-a"))
        await session.rollback()
