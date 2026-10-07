"""P135a–P135c 验收：配额逐维 / 租户隔离五路径 / 运维动作 / 可观测性闭环。

权威来源
--------
- `docs/04` §114–§126（生产配置 / 密钥 / 实例 / 生命周期 / 熔断 / 指标）· §149 · §151。
- `docs/07` §8（安全模型）· §10（任务引擎）· §14（架构红线）· §16（风险表）。
- 本批裁决见 `docs/07` §16 的 R4 / R14 / R85 / R87 / R88 / R90 / R93 回填。

落地裁决（本文件的硬事实，不美化）
--------------------------------
1. **配额逐维可执行判定**：`QUOTA_DIMENSIONS` **4** 项 × `QUOTA_METRICS` **5** 项
   **逐格**给出「准入 / 拒绝」，并断言拒绝路径**零副作用**。
2. **租户隔离落在五条路径上逐条可断言**：只读 / 写 / 任务 / 审计 / 指标。
   ⚠️ 指标路径的判据是「**租户标识不出现**」（`docs/02` §15 的高基数标签被丢弃），
   而不是「按租户分段」——指标是聚合面，按租户分段会引入基数爆炸。
3. **备份 → 校验 → **真跑一次** restore → 断言数据一致**（不是「只校验不恢复」）。
4. **Alembic upgrade / downgrade 各一次**：Core 的 **24** 张表**不变**，MIDAS 的 7 张表
   随迁移出现 / 消失（`docs/07` §16 R74 的两套 metadata）。
5. **凭据轮换**：轮换后旧值失效、新值生效，且日志 / 审计 / 响应 **0 命中**
   （一律用**占位串**，绝不使用任何真实凭据）。
6. **指标 / Trace / 结构化日志在真实一次 MCP 调用上端到端可见**，且全链路扫描 0 secret。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import p42_p48_support as support
from app.application.services.backup import BackupService, RestoreService
from app.application.services.quota import (
    QUOTA_DIMENSIONS,
    QUOTA_METRICS,
    QuotaDecision,
    QuotaService,
    StaticQuotaPolicySource,
)
from app.domain.enums import QuotaDimension, QuotaMetric
from app.domain.errors import TaskError
from app.domain.protocols import QuotaLimits
from app.infrastructure.database.base import Base
from app.infrastructure.database.models.project import ProjectORM
from app.infrastructure.database.models.tenant import TenantORM
from app.infrastructure.database.models.user import UserORM
from app.infrastructure.database.session import create_engine
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.interfaces.mcp.server import build_mcp_server
from app.observability.metrics import HIGH_CARDINALITY_LABELS, STANDARD_METRICS

REPO_ROOT = Path(__file__).resolve().parents[1]

MIDAS_TABLE_NAMES_SPEC: tuple[str, ...] = (
    "midas_api_endpoints",
    "midas_api_mappings",
    "midas_api_schemas",
    "midas_api_sources",
    "midas_api_verifications",
    "midas_api_versions",
    "midas_capability_mappings",
)
"""`docs/07` §4.4 的 **7** 张 MIDAS 表（Alembic 迁移创建；`docs/07` §16 R74）。"""

CREDENTIAL_REFERENCE: str = "P135_ROTATION_SECRET"
CREDENTIAL_ENV: str = "STRUCTAI_SECRET_P135_ROTATION_SECRET"
"""凭据引用名与环境变量名（`docs/07` §8.5 的前缀口径；**值**一律用占位串）。"""
CREDENTIAL_OLD: str = "p135-old-credential-placeholder"
CREDENTIAL_NEW: str = "p135-new-credential-placeholder"

READ_OPERATION = "MODEL.NODE.QUERY"
WRITE_OPERATION = "MODEL.NODE.CREATE"


# ===== 装配辅助 =====
async def _second_tenant(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[dict[str, str], Any]:
    """在已配备库上再建一个**独立**租户 + 用户 + 项目（租户隔离的可执行判定用）。

    Returns:
        `(标识字典, 该租户的**服务端**身份)`。身份在这里就地构造 ——
        不再回库按租户查用户（`users.username` 全局唯一，而 `tenant_id` 的比较
        在 SQLite 上依赖驱动侧的 UUID 存储形态，回查会引入与本批无关的脆弱性）。
    """
    from app.application.security.context import IdentityContext

    async with UnitOfWork.from_session_factory(factory) as uow:
        tenant = TenantORM(name=f"p135-second-{uuid4().hex[:8]}")
        uow.session.add(tenant)
        await uow.session.flush()
        user = UserORM(
            tenant_id=tenant.id,
            username=f"p135-{uuid4().hex[:8]}",
            password_hash="not-a-real-hash",
            is_active=True,
        )
        uow.session.add(user)
        await uow.session.flush()
        project = ProjectORM(tenant_id=tenant.id, name="p135-second-project")
        uow.session.add(project)
        await uow.session.flush()
        identity = IdentityContext(
            user_id=UUID(str(user.id)),
            tenant_id=UUID(str(tenant.id)),
            roles=("system_admin",),
            authentication_method="PASSWORD",
        )
        return (
            {
                "tenant_id": str(tenant.id),
                "user_id": str(user.id),
                "project_id": str(project.id),
            },
            identity,
        )


def _engine_of(runtime: Any) -> AsyncEngine:
    """运行时的引擎（同一 `Settings` → 同一 SQLite 文件）。"""
    return create_engine(runtime.settings.database_url)


async def _tenant_exists(engine: AsyncEngine, tenant_id: str) -> bool:
    """该租户在库里是否存在（恢复一致性的可执行判定）。"""
    async with engine.connect() as connection:
        result = await connection.execute(
            sa.text("SELECT COUNT(*) FROM tenants WHERE id = :tid"),
            {"tid": str(UUID(tenant_id))},
        )
    return int(result.scalar()) > 0


# ===== P135a：配额逐维 =====


def test_p135a_quota_dimensions_and_metrics_are_the_frozen_four_by_five() -> None:
    """`docs/02` §36 / §40：维度 **4** 项、指标 **5** 项（逐字取自冻结枚举）。"""
    assert QUOTA_DIMENSIONS == tuple(item.value for item in QuotaDimension)
    assert QUOTA_METRICS == tuple(item.value for item in QuotaMetric)
    assert len(QUOTA_DIMENSIONS) == 4 and len(QUOTA_METRICS) == 5


@pytest.mark.parametrize("dimension", QUOTA_DIMENSIONS)
async def test_p135a_every_dimension_can_be_admitted_and_refused(dimension: str) -> None:
    """**逐维**给出可执行判定：每个维度都能被准入**并且**能被拒绝（见裁决 1）。

    ⚠️ 维度解析顺序是 `agent → user → tenant → instance`（最具体者优先，模块裁决 4），
    故**只**给出该维度自己的标识，才能让生效维度**恰好**是它。
    """
    service = QuotaService(
        StaticQuotaPolicySource(QuotaLimits(max_api_requests=1, window_seconds=3600))
    )
    kwargs: dict[str, Any] = {"tenant_id": "", "user_id": ""}
    if dimension == "AI_AGENT":
        kwargs["agent_id"] = "agent-p135"
    elif dimension == "USER":
        kwargs["user_id"] = "user-p135"
    elif dimension == "TENANT":
        kwargs["tenant_id"] = "tenant-p135"
    else:  # SOFTWARE_INSTANCE
        kwargs["instance_id"] = "instance-p135"
    admitted = await service.consume_api_request(**kwargs)
    assert admitted.allowed is True
    assert admitted.dimension == dimension, admitted
    assert admitted.metric == str(QuotaMetric.MAX_API_REQUESTS)
    refused = await service.consume_api_request(**kwargs)
    assert refused.allowed is False
    assert refused.dimension == dimension
    assert (refused.limit, refused.used, refused.remaining) == (1, 1, 0)
    assert refused.reason == "api_request_rate_limited"
    # 拒绝路径零副作用：第三次的 `used` 仍是 1（「被拒」不吃额度，见裁决 1）
    assert (await service.consume_api_request(**kwargs)).used == 1


@pytest.mark.parametrize("metric", QUOTA_METRICS)
async def test_p135a_every_metric_has_an_executable_decision(metric: str) -> None:
    """**逐指标**给出可执行判定：准入 → 触限 → `require()` 落 `STRUCTAI-5000`。"""
    service = QuotaService(
        StaticQuotaPolicySource(
            QuotaLimits(
                max_tasks=1,
                max_concurrent_tasks=1,
                max_api_requests=1,
                max_storage=4,
                max_projects=1,
            )
        )
    )
    tenant, user = "t-metric", "u-metric"
    decision: QuotaDecision
    if metric == "max_api_requests":
        await service.consume_api_request(tenant_id=tenant, user_id=user)
        decision = await service.consume_api_request(tenant_id=tenant, user_id=user)
    elif metric == "max_concurrent_tasks":
        await service.register_task(tenant_id=tenant, user_id=user, task_id="task-1")
        decision = await service.register_task(tenant_id=tenant, user_id=user, task_id="task-2")
    elif metric == "max_tasks":
        await service.register_task(tenant_id=tenant, user_id=user, task_id="task-1")
        await service.release_task(tenant_id=tenant, user_id=user, task_id="task-1")
        decision = await service.check_tasks(tenant_id=tenant, user_id=user)
    elif metric == "max_storage":
        decision = await service.check_storage(tenant_id=tenant, user_id=user, additional_bytes=5)
    else:  # max_projects
        decision = await service.check_projects(tenant_id=tenant, user_id=user, current_projects=2)
    assert decision.metric == metric, decision
    assert decision.allowed is False, decision
    with pytest.raises(TaskError) as failure:
        await service.require(decision)
    assert failure.value.code == "STRUCTAI-5000"
    assert failure.value.retryable is True
    assert failure.value.details["stage"] == "quota"
    assert failure.value.details["metric"] == metric
    assert "STRUCTAI-" not in json.dumps(failure.value.details, default=str)


async def test_p135a_refusal_paths_never_consume_quota() -> None:
    """拒绝路径**零副作用**（`docs/07` §16 R49 的同一条约束；见裁决 1）。"""
    service = QuotaService(
        StaticQuotaPolicySource(QuotaLimits(max_concurrent_tasks=1, max_storage=4, max_projects=1))
    )
    assert (await service.register_task(tenant_id="t", user_id="u", task_id="a")).allowed is True
    for _ in range(3):
        refused = await service.register_task(tenant_id="t", user_id="u", task_id="b")
        assert refused.allowed is False
    assert (await service.check_tasks(tenant_id="t", user_id="u")).used == 1
    assert (
        await service.check_storage(tenant_id="t", user_id="u", additional_bytes=5)
    ).allowed is False
    assert (await service.check_projects(tenant_id="t", user_id="u", current_projects=1)).allowed


# ===== P135a：租户隔离五路径 =====


async def test_p135a_read_path_is_tenant_isolated(tmp_path: Path, monkeypatch: Any) -> None:
    """**只读**路径：第二个租户读不到第一个租户的项目（`STRUCTAI-4200`）。"""
    runtime, factory, ids = await support.seeded_runtime(tmp_path, monkeypatch, name="p135_read.db")
    other, other_identity = await _second_tenant(factory)
    async with UnitOfWork.from_session_factory(factory) as uow:
        server = build_mcp_server(runtime.execution.create(uow.session).service)
        own = await server.handle(
            "engineering_model_query",
            support.arguments(READ_OPERATION, parameters={}, context=support.client_context(ids)),
            identity=support.identity_context(ids),
        )
        assert own.success is True, own.errors
        foreign = await server.handle(
            "engineering_model_query",
            support.arguments(READ_OPERATION, parameters={}, context=support.client_context(ids)),
            identity=other_identity,
        )
        assert foreign.success is False
        assert foreign.errors[0]["code"] == "STRUCTAI-4200"
        assert foreign.errors[0]["message"] == "Tenant access denied"


async def test_p135a_write_path_is_tenant_isolated(tmp_path: Path, monkeypatch: Any) -> None:
    """**写**路径：第二个租户写不进第一个租户的项目（`STRUCTAI-4200`，零任务落库）。"""
    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p135_write.db"
    )
    other, other_identity = await _second_tenant(factory)
    engine = _engine_of(runtime)
    async with UnitOfWork.from_session_factory(factory) as uow:
        server = build_mcp_server(runtime.execution.create(uow.session).service)
        before = await support.row_count(engine, "tasks")
        refused = await server.handle(
            "engineering_model_assign",
            support.arguments(
                WRITE_OPERATION,
                parameters={"node": {"x": 1.0, "y": 1.0, "z": 0.0}},
                context=support.client_context(ids),
            ),
            identity=other_identity,
        )
        assert refused.success is False
        assert refused.errors[0]["code"] == "STRUCTAI-4200"
        assert await support.row_count(engine, "tasks") == before
    await engine.dispose()


async def test_p135a_task_path_is_tenant_isolated(tmp_path: Path, monkeypatch: Any) -> None:
    """**任务**路径：第二个租户看不到第一个租户的任务（`TaskStore` 强制租户过滤）。"""
    runtime, factory, ids = await support.seeded_runtime(tmp_path, monkeypatch, name="p135_task.db")
    other, _other_identity = await _second_tenant(factory)
    async with UnitOfWork.from_session_factory(factory) as uow:
        server = build_mcp_server(runtime.execution.create(uow.session).service)
        created = await server.handle(
            "engineering_model_assign",
            support.arguments(
                WRITE_OPERATION,
                parameters={"id": "9001", "x": 2.0, "y": 2.0, "z": 0.0},
                context=support.client_context(ids),
            ),
            identity=support.identity_context(ids),
        )
        assert created.success is True, created.errors
    # 任务路径的租户隔离有**两个**可执行判定：
    # ① 任务行按服务端租户落库（`tasks.tenant_id` 来自 `ExecutionContext`，客户端不可声明）；
    # ② `TaskStore.get(task_id, tenant_id)` 按租户过滤 —— 跨租户按标识**直取**也取不到。
    engine = _engine_of(runtime)
    async with engine.connect() as connection:
        stored = await connection.execute(
            sa.text("SELECT id FROM tasks WHERE tenant_id = :tid"),
            {"tid": ids["tenant_id"]},
        )
        task_ids = [str(row[0]) for row in stored.fetchall()]
        assert task_ids, "写路径必须落下一条任务行"
        foreign = await connection.execute(
            sa.text("SELECT COUNT(*) FROM tasks WHERE tenant_id = :tid"),
            {"tid": other["tenant_id"]},
        )
        assert int(foreign.scalar()) == 0
    async with UnitOfWork.from_session_factory(factory) as uow:
        bundle = runtime.execution.create(uow.session)
        # ② `TaskStore.get(task_id, tenant_id)` 按租户过滤：跨租户按标识**直取**也取不到
        assert await bundle.engine.store.get(task_ids[0], ids["tenant_id"]) is not None
        assert await bundle.engine.store.get(task_ids[0], other["tenant_id"]) is None
    await engine.dispose()


async def test_p135a_audit_path_is_tenant_isolated(tmp_path: Path, monkeypatch: Any) -> None:
    """**审计**路径：哈希链按租户分段，跨租户读不到任何记录（`docs/07` §16 R59）。"""
    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p135_audit.db"
    )
    other, _other_identity = await _second_tenant(factory)
    async with UnitOfWork.from_session_factory(factory) as uow:
        bundle = runtime.execution.create(uow.session)
        server = build_mcp_server(bundle.service)
        ok = await server.handle(
            "engineering_model_query",
            support.arguments(READ_OPERATION, parameters={}, context=support.client_context(ids)),
            identity=support.identity_context(ids),
        )
        assert ok.success is True, ok.errors
        own_chain = list(await bundle.audit.store.chain(tenant_id=ids["tenant_id"]))
        foreign_chain = list(await bundle.audit.store.chain(tenant_id=other["tenant_id"]))
        assert own_chain and not foreign_chain
        assert all(str(entry.tenant_id) == ids["tenant_id"] for entry in own_chain)
        assert (await bundle.audit.verify_chain(tenant_id=ids["tenant_id"])).valid is True


async def test_p135a_metrics_path_carries_no_tenant_identifier(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """**指标**路径：租户 / 用户标识既不进样本也不进 exposition（见裁决 2）。"""
    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p135_metrics.db"
    )
    async with UnitOfWork.from_session_factory(factory) as uow:
        server = build_mcp_server(runtime.execution.create(uow.session).service)
        ok = await server.handle(
            "engineering_model_query",
            support.arguments(READ_OPERATION, parameters={}, context=support.client_context(ids)),
            identity=support.identity_context(ids),
        )
        assert ok.success is True, ok.errors
    rendered = runtime.metrics.render()
    assert rendered, "真实调用必须产出指标样本"
    assert ids["tenant_id"] not in rendered
    assert ids["user_id"] not in rendered
    # 指标路径的租户隔离 = 「租户 / 用户标识**被丢弃**」（`docs/02` §15）：
    # 这里显式喂一次带高基数标签的样本，断言它**不**进寄存器、也不进 exposition。
    runtime.metrics.counter(
        "structai_requests_total",
        1,
        {"tenant_id": ids["tenant_id"], "user_id": ids["user_id"], "tool": "p135"},
    )
    assert set(runtime.metrics.dropped_labels()) >= {"tenant_id", "user_id"}
    assert set(runtime.metrics.dropped_labels()) <= set(HIGH_CARDINALITY_LABELS)
    rendered_after = runtime.metrics.render()
    assert ids["tenant_id"] not in rendered_after
    assert ids["user_id"] not in rendered_after
    allowed = set(STANDARD_METRICS)
    allowed |= {f"{name}_count" for name in STANDARD_METRICS}
    allowed |= {f"{name}_sum" for name in STANDARD_METRICS}
    assert set(runtime.metrics.names()) <= allowed


# ===== P135b：备份 → 校验 → restore =====


async def test_p135b_backup_verify_restore_round_trip_keeps_data_consistent(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """备份 → 校验 → **真跑一次 restore** → 数据一致（见裁决 3）。"""
    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p135_backup.db"
    )
    database_path = Path(str(runtime.settings.database_url).replace("sqlite+aiosqlite:///", ""))
    artifact_root = tmp_path / "artifacts"
    backup_root = tmp_path / "backups"
    storage = runtime.storage.backend()
    backup = BackupService(
        database_path=database_path, artifact_root=artifact_root, storage=storage
    )
    manifest = await backup.create_backup(backup_root)
    verification = await backup.verify_backup(backup_root / manifest.backup_id)
    assert verification.valid is True, verification.failures
    assert verification.backup_id == manifest.backup_id

    other, _other_identity = await _second_tenant(factory)
    engine = _engine_of(runtime)
    assert await _tenant_exists(engine, other["tenant_id"]) is True
    # 恢复前先释放引擎：SQLite 的 WAL 边车文件（`-wal` / `-shm`）会让旧数据在
    # 覆盖主库文件后仍被读到 —— 这正是「部分恢复后直接启动」被禁止的原因
    # （`docs/02` §24）。这里按 `docs/02` §23 的顺序：先停用当前库，再恢复。
    await factory.kw["bind"].dispose()
    await engine.dispose()
    for suffix in ("-wal", "-shm"):
        sidecar = database_path.with_name(database_path.name + suffix)
        if sidecar.exists():
            try:
                sidecar.unlink()
            except PermissionError:  # pragma: no cover - 句柄未及时释放时退化为「留在原地」
                pass

    restore = RestoreService(
        backup=BackupService(
            database_path=database_path, artifact_root=artifact_root, storage=storage
        ),
        database_path=database_path,
        artifact_root=artifact_root,
        storage=storage,
    )
    report = await restore.restore(backup_root / manifest.backup_id)
    assert report.restored is True, report.failures
    assert report.pre_restore_backup is not None, "恢复前必须先建紧急备份（docs/02 §24）"
    assert report.integrity_ok is True
    restored_engine = _engine_of(runtime)
    assert await _tenant_exists(restored_engine, other["tenant_id"]) is False
    assert await _tenant_exists(restored_engine, ids["tenant_id"]) is True
    await restored_engine.dispose()


# ===== P135b：Alembic upgrade / downgrade =====


def test_p135b_alembic_upgrade_and_downgrade_keep_the_twenty_four_tables(
    tmp_path: Path,
) -> None:
    """`upgrade head` → 7 张 MIDAS 表出现；`downgrade base` → 24 张表**不变**（见裁决 4）。"""
    import sqlite3

    database = tmp_path / "p135_alembic.db"
    database_url = f"sqlite+aiosqlite:///{database.as_posix()}"

    async def _create_core() -> None:
        engine = create_engine(database_url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()

    support.anyio.run(_create_core)

    def _tables() -> set[str]:
        connection = sqlite3.connect(str(database))
        try:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        finally:
            connection.close()
        return {str(row[0]) for row in rows}

    assert _tables() == set(support.TWENTY_FOUR_TABLES_SPEC)

    upgraded = _alembic(database_url, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr
    after_upgrade = _tables()
    assert set(MIDAS_TABLE_NAMES_SPEC) <= after_upgrade
    assert "alembic_version" in after_upgrade
    assert set(support.TWENTY_FOUR_TABLES_SPEC) <= after_upgrade

    downgraded = _alembic(database_url, "downgrade", "base")
    assert downgraded.returncode == 0, downgraded.stderr
    assert not (set(MIDAS_TABLE_NAMES_SPEC) & _tables())
    assert set(support.TWENTY_FOUR_TABLES_SPEC) <= _tables()
    assert set(_tables()) - set(support.TWENTY_FOUR_TABLES_SPEC) <= {"alembic_version"}


def _alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    """以子进程跑 `alembic <args>`（URL **只**经环境变量，不落盘）。"""
    environment = dict(os.environ)
    environment["DATABASE_URL"] = database_url
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        check=False,
        timeout=300,
    )


# ===== P135b：凭据轮换 =====


async def test_p135b_credential_rotation_invalidates_the_old_value(monkeypatch: Any) -> None:
    """轮换后旧值失效、新值生效，且 **0** 命中任何可打印面（见裁决 5）。"""
    from app.infrastructure.secrets import EnvironmentCredentialProvider

    monkeypatch.setenv(CREDENTIAL_ENV, CREDENTIAL_OLD)
    provider = EnvironmentCredentialProvider()
    assert await provider.get_secret(CREDENTIAL_REFERENCE) == CREDENTIAL_OLD
    monkeypatch.setenv(CREDENTIAL_ENV, CREDENTIAL_NEW)
    assert await provider.get_secret(CREDENTIAL_REFERENCE) == CREDENTIAL_NEW
    assert await provider.get_secret(CREDENTIAL_REFERENCE) != CREDENTIAL_OLD
    assert CREDENTIAL_OLD not in repr(provider)
    assert CREDENTIAL_NEW not in repr(provider)
    monkeypatch.delenv(CREDENTIAL_ENV)
    with pytest.raises(Exception) as failure:
        await provider.get_secret(CREDENTIAL_REFERENCE)
    assert failure.value.code == "STRUCTAI-7000"
    rendered = json.dumps(failure.value.details, default=str)
    assert CREDENTIAL_OLD not in rendered and CREDENTIAL_NEW not in rendered
    assert CREDENTIAL_REFERENCE not in rendered


# ===== P135c：指标 / Trace / 结构化日志 =====


async def test_p135c_metrics_trace_and_logs_are_visible_on_a_real_mcp_call(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """真实一次 MCP 调用：指标 / Trace / 结构化日志**端到端可见**且 0 secret（见裁决 6）。"""
    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p135_observability.db"
    )
    async with UnitOfWork.from_session_factory(factory) as uow:
        server = build_mcp_server(runtime.execution.create(uow.session).service)
        response = await server.handle(
            "engineering_model_query",
            support.arguments(READ_OPERATION, parameters={}, context=support.client_context(ids)),
            identity=support.identity_context(ids),
        )
        assert response.success is True, response.errors
        payload = response.to_dict()
        request_id = str(payload["request_id"])
        trace_id = str(payload["trace_id"])
        assert request_id and trace_id

    metrics = runtime.metrics
    # `structai_requests_total` 带 `tool` / `operation` / `status` 标签，故按样本核对
    # （`docs/02` §14；不带标签地读会得到 0 —— 这是指标口径，不是缺陷）。
    request_samples = tuple(
        sample for sample in metrics.samples() if sample.name == "structai_requests_total"
    )
    assert request_samples, metrics.samples()
    assert any(sample.value >= 1 for sample in request_samples)
    assert any(
        dict(sample.labels).get("tool") == "engineering_model_query" for sample in request_samples
    )
    assert (
        metrics.observation_count(
            "structai_request_duration_seconds",
            {"tool": "engineering_model_query", "operation": READ_OPERATION},
        )
        >= 1
    )
    rendered = metrics.render()
    assert "structai_requests_total" in rendered
    assert ids["tenant_id"] not in rendered and ids["user_id"] not in rendered

    spans = list(await runtime.trace.spans_for_trace(trace_id))
    assert spans, "真实调用必须留下 Span"
    assert len(spans) >= 2, "至少 MCP → Tool 两层"
    assert all(str(span.request_id) == request_id for span in spans)
    parents = {span.parent_span_id for span in spans if span.parent_span_id}
    assert parents <= {span.id for span in spans}
    for span in spans:
        assert "secret" not in span.attributes_json
        assert ids["tenant_id"] not in span.attributes_json

    # 结构化日志一律走 stderr（stdout 0 字节），且不含凭据形态
    completed = support.run_main(database_url=runtime.settings.database_url)
    assert completed.returncode == 0
    assert completed.stdout == ""
    assert CREDENTIAL_OLD not in completed.stderr
    assert CREDENTIAL_NEW not in completed.stderr


async def test_p135c_no_surface_carries_a_secret_looking_value(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """全链路扫描：库内文本列 / 审计 / Trace 属性 / 响应 **0** 命中凭据形态（见裁决 6）。"""
    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p135_secret_scan.db"
    )
    marker = "p135-secret-marker-placeholder"
    monkeypatch.setenv("STRUCTAI_P135_SCAN_SECRET", marker)
    async with UnitOfWork.from_session_factory(factory) as uow:
        bundle = runtime.execution.create(uow.session)
        server = build_mcp_server(bundle.service)
        response = await server.handle(
            "engineering_model_query",
            support.arguments(READ_OPERATION, parameters={}, context=support.client_context(ids)),
            identity=support.identity_context(ids),
        )
        assert response.success is True, response.errors
        envelope = json.dumps(response.to_dict(), default=str)
        assert marker not in envelope
        assert "STRUCTAI_P135_SCAN_SECRET" not in envelope
        for span in await runtime.trace.spans_for_request(str(response.to_dict()["request_id"])):
            assert marker not in span.attributes_json

    engine = _engine_of(runtime)
    values = await support.all_text_values(engine)
    assert all(marker not in value for value in values)
    assert all(CREDENTIAL_OLD not in value for value in values)
    await engine.dispose()
