"""P36 验收 · ExecutionService + 26 步管线（`docs/07` §9 / §12 P36 / §13；`docs/02` §86–§94）。

门槛（`docs/08` §4 的本批提示词 ⑧；`docs/07` §9 的 26 步**冻结**顺序）
------------------------------------------------------------------------
① **端到端管线可跑**：Mock Adapter + **真实** Security / Schema / Capability / Lock /
   Idempotency / TaskEngine —— `SYNC` 等完成返回，`ASYNC` 立即返回 `task_id`；
② 顺序 `ExecutionService → Idempotency → Task Create` **不变**（`docs/02` §90），
   且 `Idempotency`(14) 先于 `Concurrency / Resource Lock`(15)；
③ **长任务在 Worker 取到任务后才抢资源锁**（`docs/02` §91）：本批的管线**不**抢锁
   （`acquire_lock=False`），锁由 `TaskWorker` 的 `finally` 释放；
④ Confirmation **必须**在 Task 创建**之前**（`docs/02` §92）：HIGH 操作缺 token → 4100
   且**零**任务落库；
⑤ 26 步**分区**拼接后逐条等于 `EXECUTION_PIPELINE_ORDER`（本批只**组织**，不改顺序 / 不删步）；
⑥ 审计 / Trace / Event 的接入点：`trace_id` 贯穿 MCP → Tool → Operation → Adapter；
   任务事件**先写 Outbox**（`docs/02` §5.4），再由 `EventDispatcher` 发布；
⑦ 回归与红线：`python -m app.main` 退出码 0 且 **stdout 0 字节**、建表 **24** 张、
   `grep -ri midas app/` = 0、20 码不扩、`app/application/**` **不**依赖
   `app.infrastructure` / `app.observability`、`commit` / `rollback` 只在 `unit_of_work.py`。

测试风格（沿用 `tests/test_task_engine_p22_p28.py`）：规范原文副本**写在测试文件里**
（不从被测模块导入），每个测试一条长断言并写明门槛，SQL 级钩子 / AST 红线扫描按需使用。
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.execution import EXECUTION_PIPELINE_ORDER
from app.application.execution.context import ExecutionContextFactory
from app.application.execution.pipeline import (
    MCP_PIPELINE_STEPS,
    PIPELINE_EXECUTION_STEPS,
    PIPELINE_GATE_STEPS,
    PIPELINE_RESPONSE_STEPS,
    PIPELINE_TASK_STEP,
    PipelineRequest,
    audit_action_for,
)
from app.application.execution.service import (
    ASYNC_MODE,
    DENIED_ERROR_CODES,
    DRY_RUN_MODE,
    ERROR_CLASSES,
    EXECUTION_STEPS,
    SYNC_MODE,
    ExecutionService,
)
from app.application.security.context import IdentityContext
from app.config.settings import Settings
from app.container import (
    BATCH_ID,
    AppContainer,
    ExecutionRuntime,
    ExecutionServiceFactory,
    bind_mock_instances,
    build_execution_runtime,
)
from app.domain.enums import AuditResult, TaskStatus
from app.domain.errors import InternalError, StructAIError
from app.infrastructure.database.base import Base
from app.infrastructure.database.seed import seed
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.infrastructure.registry.capability_registry import CapabilityRegistry
from app.infrastructure.registry.operation_registry import OperationRegistry

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
APPLICATION_DIR = APP_DIR / "application"

ADMIN_PASSWORD_ENV = "STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD"
TEST_PASSWORD = "P36-Execution-Service-验收-口令-9d31"

PIPELINE_ORDER_SPEC: tuple[str, ...] = (
    "MCP Request",
    "Authenticate",
    "Build Server IdentityContext",
    "Build ExecutionContext",
    "Resolve Tool",
    "Resolve Operation",
    "Resolve Resource",
    "Schema Validation",
    "Engineering Validation",
    "Preconditions",
    "Effective Permission",
    "Quota / Rate Limit",
    "Confirmation",
    "Idempotency",
    "Concurrency / Resource Lock",
    "Capability Check",
    "Task / Transaction",
    "Adapter",
    "Result Normalization",
    "Postconditions",
    "Release Lock",
    "Persist Result",
    "Audit",
    "Trace",
    "Event",
    "MCP Response",
)
"""`docs/07` §9 的 26 步**冻结**顺序（逐条抄写；**不**从被测模块导入）。"""

ERROR_CODES_SPEC: frozenset[str] = frozenset(
    {
        "STRUCTAI-1000",
        "STRUCTAI-1100",
        "STRUCTAI-1200",
        "STRUCTAI-1300",
        "STRUCTAI-2000",
        "STRUCTAI-2100",
        "STRUCTAI-2200",
        "STRUCTAI-2300",
        "STRUCTAI-3000",
        "STRUCTAI-4000",
        "STRUCTAI-4100",
        "STRUCTAI-4200",
        "STRUCTAI-5000",
        "STRUCTAI-5100",
        "STRUCTAI-5200",
        "STRUCTAI-5300",
        "STRUCTAI-6000",
        "STRUCTAI-6100",
        "STRUCTAI-6200",
        "STRUCTAI-7000",
    }
)
"""`docs/07` §11 的 **20** 码契约（逐条抄写）。"""

CONTAINER_FIELDS_SPEC: tuple[str, ...] = (
    "settings",
    "runtime_config",
    "engine",
    "session_factory",
    "operation_registry",
    "execution_service",
    "started",
)
"""`docs/02` §33 的冻结容器形状（P22–P28 已逐字段断言；本批**不**扩展）。"""

TWENTY_FOUR_TABLES_SPEC: tuple[str, ...] = (
    "tenants",
    "users",
    "roles",
    "permissions",
    "user_roles",
    "role_permissions",
    "sessions",
    "projects",
    "project_members",
    "software",
    "software_products",
    "software_versions",
    "software_instances",
    "models",
    "documents",
    "capabilities",
    "operations",
    "operation_capabilities",
    "tasks",
    "task_steps",
    "artifacts",
    "resource_locks",
    "idempotency_records",
    "audit_records",
)
"""`docs/07` §4.3 的 24 张表（逐条抄写；本批**不得改表**）。"""

VENDOR_NAMES: tuple[str, ...] = ("MIDAS", "CSI", "ANSYS", "SAP2000", "ETABS", "OpenSees")
SECRET_MARKERS: tuple[str, ...] = (
    "password",
    "api_key",
    "api-key",
    "token",
    "private_key",
    "secret",
    "credential",
)
FORBIDDEN_APPLICATION_IMPORTS: tuple[str, ...] = (
    "app.infrastructure",
    "app.interfaces",
    "app.observability",
)

BUILD_COLUMN_PARAMETERS: Mapping[str, object] = {
    "base_node": {"x": 0.0, "y": 0.0, "z": 0.0},
    "height": 6.0,
    "material": "Q355B",
    "section": "H400x400x13x21",
}


def _seeded_settings(tmp_path: Path) -> Settings:
    """构造指向临时库 / 临时产物目录的 `Settings`（**不**碰仓库里的 `data/`）。"""
    return Settings(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'p36_execution.db').as_posix()}",
        artifact_root=str(tmp_path / "artifacts"),
    )


async def _seeded_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ExecutionRuntime, async_sessionmaker[AsyncSession], str, str, str]:
    """装配「已配备库 + 进程级运行时」，并绑定 Mock 软件实例。

    Returns:
        `(runtime, session_factory, tenant_id, user_id, project_id, instance_id)` 的六元组。
    """
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    settings = _seeded_settings(tmp_path)
    engine = create_engine_for(settings)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    await seed(factory)
    runtime = build_execution_runtime(
        settings,
        operation_registry=await OperationRegistry.load(engine, factory),
        capability_registry=await CapabilityRegistry.load(engine, factory),
    )
    bound = await bind_mock_instances(runtime, factory)
    assert len(bound) == 1, bound
    async with factory() as session:
        tenant_id, user_id, project_id = await _seeded_ids(session)
    model_id = await _link_instance_to_project(
        factory,
        project_id=project_id,
        instance_id=bound[0],
    )
    await engine.dispose()
    return runtime, factory, tenant_id, user_id, project_id, bound[0], model_id


async def _link_instance_to_project(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    project_id: str,
    instance_id: str,
) -> str:
    """在项目下建一个绑定 Mock 实例的模型（`docs/02` §12；`docs/07` §16 R25）。

    R25 的裁决：`software_instances` **没有** `tenant_id` 列，实例的租户归属
    **只能**经 `models.software_instance_id → projects.tenant_id` 推导 ——
    未被任何项目链绑定的实例不属于任何租户，任何租户都不得直接执行（`STRUCTAI-4200`）。
    故端到端用例必须先建立这条链。
    """
    from app.infrastructure.database.models.model import ModelORM

    async with UnitOfWork.from_session_factory(session_factory) as uow:
        row = ModelORM(
            project_id=project_id,
            software_instance_id=instance_id,
            name="P36 Execution Model",
        )
        uow.session.add(row)
        await uow.session.flush()
        return str(row.id)


def create_engine_for(settings: Settings) -> AsyncEngine:
    """按 `Settings` 建引擎（`docs/02` §15；只在测试里显式建表）。"""
    from app.infrastructure.database.session import create_engine

    return create_engine(settings.database_url)


async def _seeded_ids(session: AsyncSession) -> tuple[str, str, str]:
    """取 seed 落库的租户 / 管理员 / 项目标识（`docs/02` §44）。"""
    from app.infrastructure.database.models.project import ProjectORM
    from app.infrastructure.database.models.tenant import TenantORM
    from app.infrastructure.database.models.user import UserORM

    tenant = (await session.execute(select(TenantORM))).scalars().first()
    user = (await session.execute(select(UserORM))).scalars().first()
    project = (await session.execute(select(ProjectORM))).scalars().first()
    return str(tenant.id), str(user.id), str(project.id)


def _identity(tenant_id: str, user_id: str) -> IdentityContext:
    """服务端身份（`docs/02` §26）：本批由测试扮演认证链。"""
    return IdentityContext(
        user_id=UUID(user_id),
        tenant_id=UUID(tenant_id),
        roles=("system_admin",),
        authentication_method="PASSWORD",
    )


def _context(
    identity: IdentityContext,
    *,
    project_id: str,
    instance_id: str,
    model_id: str | None = None,
    trace_id: str | None = None,
) -> object:
    """构造 `ExecutionContext`（`docs/02` §5；身份由服务端构造）。"""
    return ExecutionContextFactory().create(
        identity,
        project_id=project_id,
        model_id=model_id,
        software_instance_id=instance_id,
        request_id=f"req-{uuid4().hex}",
        trace_id=trace_id or f"trace-{uuid4().hex}",
    )


def _request(
    context: object,
    *,
    tool: str = "engineering_model_query",
    operation: str = "MODEL.NODE.QUERY",
    parameters: Mapping[str, object] | None = None,
    idempotency_key: str | None = None,
    confirmation_token: str | None = None,
    dry_run: bool = False,
) -> PipelineRequest:
    """构造管线请求（`docs/02` §27 / §33）。"""
    return PipelineRequest(
        tool=tool,
        operation=operation,
        parameters=dict(parameters or {}),
        context=context,  # type: ignore[arg-type]
        idempotency_key=idempotency_key,
        confirmation_token=confirmation_token,
        dry_run=dry_run,
    )


def _recorded_statements(engine: AsyncEngine) -> list[str]:
    """录制 SQL 语句（SQL 级钩子；与 P22–P28 同一手法）。"""
    statements: list[str] = []

    def _capture(conn: object, cursor: object, statement: str, *rest: object) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _capture)
    return statements


def _imported_modules(path: Path) -> set[str]:
    """模块级 import 的模块名集合（AST 红线扫描）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _commit_or_rollback_calls(path: Path) -> list[str]:
    """`.commit()` / `.rollback()` 的调用点（AST 红线扫描）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"commit", "rollback"}:
                found.append(node.func.attr)
    return found


def _run_main(database_url: str) -> subprocess.CompletedProcess[str]:
    """以子进程跑 `python -m app.main`（门槛：退出码 0 + stdout 0 字节）。"""
    environment = dict(os.environ)
    environment["DATABASE_URL"] = database_url
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "app.main"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


# ===== ① 批次与结构（`docs/08` §3）=====


def test_batch_id_is_a_batch_marker() -> None:
    """门槛 ⑦（`docs/08` §3 的批次口径）：`BATCH_ID` 始终形如 `P<两位数字>`。

    ⚠️ P37–P39 收尾时把本断言从「等于 `P29`」改为**与具体批次无关**（与 P09 / P14 / P19 /
    P21 / P22 的同一先例）：批次号随每一批推进，硬编码会让后续批次无谓地改上一批的测试。
    本批的批次号断言由 `tests/test_mcp_p37_p39.py::test_batch_id_is_a_batch_marker` 负责。
    """
    assert re.fullmatch(r"P\d{2}", BATCH_ID)


def test_container_shape_is_unchanged_and_exposes_the_execution_factory() -> None:
    """门槛 ⑦（`docs/02` §33）：容器仍是 **7** 字段，`execution_service` 是装配工厂。"""
    import dataclasses

    names = tuple(item.name for item in dataclasses.fields(AppContainer))
    assert names == CONTAINER_FIELDS_SPEC, names
    assert [name for name in names if "task" in name] == []
    assert isinstance(ExecutionServiceFactory, type)
    assert isinstance(ExecutionService, type)
    assert isinstance(ExecutionRuntime, type)


def test_pipeline_partitions_rebuild_the_frozen_twenty_six_steps() -> None:
    """门槛 ⑤（`docs/07` §9）：分区拼接**逐条**等于 26 步冻结顺序。"""
    rebuilt = (
        MCP_PIPELINE_STEPS
        + PIPELINE_GATE_STEPS
        + (PIPELINE_TASK_STEP,)
        + PIPELINE_EXECUTION_STEPS
        + PIPELINE_RESPONSE_STEPS
    )
    assert rebuilt == PIPELINE_ORDER_SPEC
    assert EXECUTION_PIPELINE_ORDER == PIPELINE_ORDER_SPEC
    assert EXECUTION_STEPS == PIPELINE_ORDER_SPEC
    assert len(PIPELINE_ORDER_SPEC) == 26
    assert len(MCP_PIPELINE_STEPS) == 4
    assert len(PIPELINE_GATE_STEPS) == 12
    assert len(PIPELINE_EXECUTION_STEPS) == 8
    assert PIPELINE_ORDER_SPEC.index("Idempotency") < PIPELINE_ORDER_SPEC.index(
        "Concurrency / Resource Lock"
    )
    assert PIPELINE_ORDER_SPEC.index("Confirmation") < PIPELINE_ORDER_SPEC.index("Idempotency")
    assert PIPELINE_ORDER_SPEC.index("Capability Check") < PIPELINE_ORDER_SPEC.index(
        "Task / Transaction"
    )
    assert PIPELINE_ORDER_SPEC.index("Postconditions") < PIPELINE_ORDER_SPEC.index("Release Lock")


def test_error_class_mapping_covers_exactly_the_twenty_codes() -> None:
    """门槛 ⑦（`docs/07` §11）：反向还原表恰好覆盖 **20** 码，不新增。"""
    assert set(ERROR_CLASSES) == ERROR_CODES_SPEC
    assert set(DENIED_ERROR_CODES) <= ERROR_CODES_SPEC
    for code, error_class in ERROR_CLASSES.items():
        assert error_class.code == code, (code, error_class)


def test_audit_action_resolution_maps_the_mandated_families() -> None:
    """门槛 ⑥（`docs/02` §8.3）：动作名经族映射推导，未命中原样返回。"""
    assert audit_action_for("BUILD.COLUMN") == "MODEL.CREATE"
    assert audit_action_for("ANALYSIS.STATIC") == "ANALYSIS.RUN"
    assert audit_action_for("DESIGN.STEEL") == "DESIGN.RUN"
    assert audit_action_for("MODEL.LOAD.ASSIGN") == "MODEL.UPDATE"
    assert audit_action_for("MODEL.NODE.DELETE") == "MODEL.DELETE"
    assert audit_action_for("RESULT.NODE.DISPLACEMENT") == "RESULT.NODE.DISPLACEMENT"


# ===== ② 端到端（`docs/07` §9 / §12 P36；`docs/02` §86–§94）=====


def test_sync_execution_runs_the_full_chain_and_returns_the_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ①：`SYNC` 等完成返回 —— Mock Adapter + 真实 Security / Capability / TaskEngine。"""

    async def _run() -> None:
        (
            runtime,
            factory,
            tenant_id,
            user_id,
            project_id,
            instance_id,
            model_id,
        ) = await _seeded_runtime(tmp_path, monkeypatch)
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            context = _context(
                _identity(tenant_id, user_id),
                project_id=project_id,
                instance_id=instance_id,
                model_id=model_id,
            )
            result = await bundle.service.execute_request(_request(context))
            assert result.mode == SYNC_MODE, result.mode
            assert result.status == str(TaskStatus.COMPLETED), result.status
            assert result.task_id is not None
            assert result.replayed is False
            assert result.result is not None
            # Mock Adapter 的规范化响应（`docs/02` §31 的分页信封）经管线原样返回：
            # 这证明第 18 步（Adapter）真的执行了，且第 19 步（Result Normalization）保住了信封。
            assert "items" in result.result, result.result
            assert result.result["pagination"] == {"has_more": False, "next_cursor": None}
            assert result.unprovisioned_schemas == ("structai://schema/model/node/query/v1",)

    asyncio.run(_run())


def test_sync_execution_steps_are_the_frozen_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ①/⑤：SYNC 路径实际执行过的步骤**逐条**等于 26 步冻结顺序。"""

    async def _run() -> None:
        (
            runtime,
            factory,
            tenant_id,
            user_id,
            project_id,
            instance_id,
            model_id,
        ) = await _seeded_runtime(tmp_path, monkeypatch)
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            context = _context(
                _identity(tenant_id, user_id),
                project_id=project_id,
                instance_id=instance_id,
                model_id=model_id,
            )
            result = await bundle.service.execute_request(_request(context))
            # 第 1–4 步（MCP Request → Build ExecutionContext）属 P37–P39 的 MCP 层，
            # 本批由调用方传入已构造的 `ExecutionContext`，故服务执行的是第 5–26 步。
            assert result.steps == PIPELINE_ORDER_SPEC[4:], result.steps
            assert result.steps == (
                PIPELINE_GATE_STEPS
                + (PIPELINE_TASK_STEP,)
                + PIPELINE_EXECUTION_STEPS
                + PIPELINE_RESPONSE_STEPS
            )

    asyncio.run(_run())


def test_gate_records_unprovisioned_schemas_and_delegates_the_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ①/③（`pipeline.py` 裁决 2；`docs/02` §91）：未配备 Schema 被**记录**；锁**委派**。"""

    async def _run() -> None:
        (
            runtime,
            factory,
            tenant_id,
            user_id,
            project_id,
            instance_id,
            model_id,
        ) = await _seeded_runtime(tmp_path, monkeypatch)
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            context = _context(
                _identity(tenant_id, user_id),
                project_id=project_id,
                instance_id=instance_id,
                model_id=model_id,
            )
            gate = await bundle.pipeline.gate(_request(context))
            assert gate.unprovisioned_schemas == ("structai://schema/model/node/query/v1",)
            assert gate.steps == PIPELINE_GATE_STEPS, gate.steps
            assert gate.lock is None, "Task 路径的锁必须委派给 Worker（docs/02 §91）"
            assert gate.locked_here is False
            assert gate.lock_owner() == ""
            assert await bundle.pipeline.release(gate) is False

    asyncio.run(_run())


def test_async_execution_returns_the_task_id_immediately(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ①（`docs/02` §89）：`ASYNC` 立即返回 `mode` / `status` / `task_id` 三键。"""

    async def _run() -> None:
        (
            runtime,
            factory,
            tenant_id,
            user_id,
            project_id,
            instance_id,
            model_id,
        ) = await _seeded_runtime(tmp_path, monkeypatch)
        identity = _identity(tenant_id, user_id)
        context = _context(
            identity,
            project_id=project_id,
            instance_id=instance_id,
            model_id=model_id,
        )
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            resource = await bundle.resolver.resolve(context)
            assert resource is not None
            confirmation = runtime.confirmation.issue(
                user_id=str(identity.user_id),
                tenant_id=str(identity.tenant_id),
                operation="BUILD.COLUMN",
                resource_id=resource.resource_id,
            )
            result = await bundle.service.execute_request(
                _request(
                    context,
                    tool="engineering_model_build",
                    operation="BUILD.COLUMN",
                    parameters=BUILD_COLUMN_PARAMETERS,
                    confirmation_token=confirmation.token,
                )
            )
            assert result.mode == ASYNC_MODE, result.mode
            assert result.status == str(TaskStatus.QUEUED), result.status
            assert result.task_id is not None
            assert result.result is None
            payload = result.to_dict()
            assert payload["mode"] == ASYNC_MODE
            assert payload["status"] == str(TaskStatus.QUEUED)
            assert payload["task_id"] == result.task_id
            expected = PIPELINE_GATE_STEPS + (PIPELINE_TASK_STEP,) + PIPELINE_RESPONSE_STEPS
            assert result.steps == expected

    asyncio.run(_run())


def test_async_task_completes_through_the_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ①/③（`docs/02` §88 / §91）：Worker 取到任务后抢锁 → 执行 → 释放，任务完成。"""

    async def _run() -> None:
        (
            runtime,
            factory,
            tenant_id,
            user_id,
            project_id,
            instance_id,
            model_id,
        ) = await _seeded_runtime(tmp_path, monkeypatch)
        identity = _identity(tenant_id, user_id)
        context = _context(
            identity,
            project_id=project_id,
            instance_id=instance_id,
            model_id=model_id,
        )
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            resource = await bundle.resolver.resolve(context)
            assert resource is not None
            confirmation = runtime.confirmation.issue(
                user_id=str(identity.user_id),
                tenant_id=str(identity.tenant_id),
                operation="BUILD.COLUMN",
                resource_id=resource.resource_id,
            )
            submitted = await bundle.service.execute_request(
                _request(
                    context,
                    tool="engineering_model_build",
                    operation="BUILD.COLUMN",
                    parameters=BUILD_COLUMN_PARAMETERS,
                    confirmation_token=confirmation.token,
                )
            )
            assert submitted.task_id is not None
            record = await bundle.engine.run_task(submitted.task_id, "sync-worker")
            assert str(record.status) == str(TaskStatus.COMPLETED), record.status
            assert record.result_json is not None
            payload = json.loads(record.result_json)
            assert "node_ids" in payload, payload
            assert len(payload["node_ids"]) == 2, payload
            assert len(payload["element_ids"]) == 1, payload
            assert await runtime.locks.held_count() == 0, "Worker 必须在 finally 释放锁"

    asyncio.run(_run())


def test_high_risk_operation_requires_confirmation_before_task_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ④（`docs/02` §92）：缺 Confirmation → `4100` 且**零**任务落库。"""

    async def _run() -> None:
        from app.infrastructure.database.models.task import TaskORM

        (
            runtime,
            factory,
            tenant_id,
            user_id,
            project_id,
            instance_id,
            model_id,
        ) = await _seeded_runtime(tmp_path, monkeypatch)
        context = _context(
            _identity(tenant_id, user_id),
            project_id=project_id,
            instance_id=instance_id,
            model_id=model_id,
        )
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            with pytest.raises(StructAIError) as excinfo:
                await bundle.service.execute_request(
                    _request(
                        context,
                        tool="engineering_model_build",
                        operation="BUILD.COLUMN",
                        parameters=BUILD_COLUMN_PARAMETERS,
                    )
                )
            error = excinfo.value
            assert error.code == "STRUCTAI-4100", error.code
            assert error.details["stage"] == "confirmation", error.details
            rows = (await uow.session.execute(select(TaskORM))).scalars().all()
            assert len(rows) == 0, "Confirmation 失败时不得创建任务（docs/02 §92）"

    asyncio.run(_run())


# ===== ③ 幂等 / Dry Run / 拒绝路径（`docs/02` §86 / §90 / §92 / §82 / §48）=====


def test_idempotent_replay_returns_the_first_response_without_rerunning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ②（`docs/02` §86 / §90）：同键同请求 → **重放**既有响应，不建新任务、不重发审计。"""

    async def _run() -> None:
        from app.infrastructure.database.models.task import TaskORM

        (
            runtime,
            factory,
            tenant_id,
            user_id,
            project_id,
            instance_id,
            model_id,
        ) = await _seeded_runtime(tmp_path, monkeypatch)
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            context = _context(
                _identity(tenant_id, user_id),
                project_id=project_id,
                instance_id=instance_id,
                model_id=model_id,
            )
            request = _request(context, idempotency_key="p36-replay-001")
            first = await bundle.service.execute_request(request)
            assert first.replayed is False
            assert first.result is not None
            tasks_after_first = len((await uow.session.execute(select(TaskORM))).scalars().all())
            second = await bundle.service.execute_request(request)
            assert second.replayed is True
            assert second.result == first.result
            assert second.task_id is None, "重放不新建任务"
            tasks_after_second = len((await uow.session.execute(select(TaskORM))).scalars().all())
            assert tasks_after_first == tasks_after_second == 1
            # 重放路径的步骤只到 Idempotency（不抢锁、不执行 Adapter、不重发审计）。
            assert second.steps == PIPELINE_GATE_STEPS[:10] + PIPELINE_RESPONSE_STEPS

    asyncio.run(_run())


def test_idempotency_conflict_on_a_different_request_is_1300(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ②（`docs/07` §10.3）：同键**不同**请求 → `1300`，且不建新任务。"""

    async def _run() -> None:
        from app.infrastructure.database.models.task import TaskORM

        (
            runtime,
            factory,
            tenant_id,
            user_id,
            project_id,
            instance_id,
            model_id,
        ) = await _seeded_runtime(tmp_path, monkeypatch)
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            context = _context(
                _identity(tenant_id, user_id),
                project_id=project_id,
                instance_id=instance_id,
                model_id=model_id,
            )
            await bundle.service.execute_request(
                _request(context, idempotency_key="p36-conflict-001")
            )
            with pytest.raises(StructAIError) as excinfo:
                await bundle.service.execute_request(
                    _request(
                        context,
                        parameters={"node_ids": [1]},
                        idempotency_key="p36-conflict-001",
                    )
                )
            error = excinfo.value
            assert error.code == "STRUCTAI-1300", error.code
            assert error.details == {
                "stage": "idempotency",
                "reason": "request_hash_mismatch",
            }, error.details
            tasks = len((await uow.session.execute(select(TaskORM))).scalars().all())
            assert tasks == 1, "冲突路径不得创建第二个任务"

    asyncio.run(_run())


def test_dry_run_returns_the_frozen_payload_and_never_creates_a_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ①（`docs/02` §92）：Dry Run 返回 `changes` / `warnings` 均为空列表的冻结载荷。"""

    async def _run() -> None:
        from app.infrastructure.database.models.task import TaskORM

        (
            runtime,
            factory,
            tenant_id,
            user_id,
            project_id,
            instance_id,
            model_id,
        ) = await _seeded_runtime(tmp_path, monkeypatch)
        identity = _identity(tenant_id, user_id)
        context = _context(
            identity,
            project_id=project_id,
            instance_id=instance_id,
            model_id=model_id,
        )
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            resource = await bundle.resolver.resolve(context)
            assert resource is not None
            confirmation = runtime.confirmation.issue(
                user_id=str(identity.user_id),
                tenant_id=str(identity.tenant_id),
                operation="BUILD.COLUMN",
                resource_id=resource.resource_id,
            )
            result = await bundle.service.execute_request(
                _request(
                    context,
                    tool="engineering_model_build",
                    operation="BUILD.COLUMN",
                    parameters=BUILD_COLUMN_PARAMETERS,
                    confirmation_token=confirmation.token,
                    dry_run=True,
                )
            )
            assert result.mode == DRY_RUN_MODE, result.mode
            assert result.result == {"mode": "DRY_RUN", "changes": [], "warnings": []}
            assert result.task_id is None
            tasks = len((await uow.session.execute(select(TaskORM))).scalars().all())
            assert tasks == 0, "Dry Run 不得创建任务（docs/02 §92）"
            assert await runtime.locks.held_count() == 0, "Dry Run 自己持有的锁必须释放（第 21 步）"

    asyncio.run(_run())


def test_tool_mismatch_and_unknown_operation_are_1000(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ①（`docs/02` §82）：Tool ↔ Operation 不匹配 / 未知 Operation → `1000`。"""

    async def _run() -> None:
        (
            runtime,
            factory,
            tenant_id,
            user_id,
            project_id,
            instance_id,
            model_id,
        ) = await _seeded_runtime(tmp_path, monkeypatch)
        context = _context(
            _identity(tenant_id, user_id),
            project_id=project_id,
            instance_id=instance_id,
            model_id=model_id,
        )
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            with pytest.raises(StructAIError) as mismatch:
                await bundle.service.execute_request(
                    _request(context, tool="engineering_model_build")
                )
            assert mismatch.value.code == "STRUCTAI-1000", mismatch.value.code
            assert mismatch.value.details["reason"] == "tool_mismatch"
            with pytest.raises(StructAIError) as unknown:
                await bundle.service.execute_request(_request(context, operation="MODEL.NODE.NOPE"))
            assert unknown.value.code == "STRUCTAI-1000", unknown.value.code
            assert unknown.value.details["reason"] == "unknown_operation"
            with pytest.raises(StructAIError) as unknown_tool:
                await bundle.service.execute_request(_request(context, tool="nope"))
            assert unknown_tool.value.code == "STRUCTAI-1000", unknown_tool.value.code
            assert unknown_tool.value.details["reason"] == "unknown_tool"

    asyncio.run(_run())


def test_cross_tenant_request_is_4200(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ①（`docs/07` §9 第 7 步 / §14.3）：跨租户 → `4200`（**先于**任何其它判定）。"""

    async def _run() -> None:
        (
            runtime,
            factory,
            tenant_id,
            user_id,
            project_id,
            instance_id,
            model_id,
        ) = await _seeded_runtime(tmp_path, monkeypatch)
        foreign = IdentityContext(
            user_id=UUID(user_id),
            tenant_id=uuid4(),
            roles=("system_admin",),
            authentication_method="PASSWORD",
        )
        context = _context(
            foreign,
            project_id=project_id,
            instance_id=instance_id,
            model_id=model_id,
        )
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            with pytest.raises(StructAIError) as excinfo:
                await bundle.service.execute_request(_request(context))
            error = excinfo.value
            assert error.code == "STRUCTAI-4200", error.code
            assert error.message == "Tenant access denied"

    asyncio.run(_run())


def test_missing_permission_is_4000(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ①（`docs/07` §8.2 / §13.4）：无权限用户 → `4000`。"""

    async def _run() -> None:
        (
            runtime,
            factory,
            tenant_id,
            user_id,
            project_id,
            instance_id,
            model_id,
        ) = await _seeded_runtime(tmp_path, monkeypatch)
        stranger = IdentityContext(
            user_id=uuid4(),
            tenant_id=UUID(tenant_id),
            roles=(),
            authentication_method="PASSWORD",
        )
        context = _context(
            stranger,
            project_id=project_id,
            instance_id=instance_id,
            model_id=model_id,
        )
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            with pytest.raises(StructAIError) as excinfo:
                await bundle.service.execute_request(_request(context))
            error = excinfo.value
            assert error.code == "STRUCTAI-4000", error.code
            assert error.details["stage"] == "authorization", error.details
            assert error.details["permission"] == "MODEL_READ", error.details

    asyncio.run(_run())


def test_capability_check_rejects_a_disconnected_instance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ①（`docs/02` §43–§48；`docs/07` §16 R30）：说不清能力 → `3000`，**不**放行。"""

    async def _run() -> None:
        (
            runtime,
            factory,
            tenant_id,
            user_id,
            project_id,
            instance_id,
            model_id,
        ) = await _seeded_runtime(tmp_path, monkeypatch)
        await runtime.adapters.disconnect(instance_id)
        context = _context(
            _identity(tenant_id, user_id),
            project_id=project_id,
            instance_id=instance_id,
            model_id=model_id,
        )
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            with pytest.raises(StructAIError) as excinfo:
                await bundle.service.execute_request(_request(context))
            error = excinfo.value
            assert error.code == "STRUCTAI-3000", error.code
            assert error.details["stage"] == "capability", error.details

    asyncio.run(_run())


# ===== ④ Worker 路径与观测接入点（`docs/02` §88 / §5.4 / §12 / §8）=====


def test_worker_path_without_a_registered_context_is_7000(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ①（`service.py` 裁决 4）：进程内没有上下文时**必须**报错，绝不用空身份执行。"""

    async def _run() -> None:
        from app.application.task.engine import TaskSubmission

        (
            runtime,
            factory,
            tenant_id,
            user_id,
            project_id,
            instance_id,
            model_id,
        ) = await _seeded_runtime(tmp_path, monkeypatch)
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            record = await bundle.engine.create(
                TaskSubmission(
                    tenant_id=tenant_id,
                    request_id="req-p36-orphan",
                    trace_id="trace-p36-orphan",
                    tool="engineering_model_query",
                    operation="MODEL.NODE.QUERY",
                    project_id=project_id,
                )
            )
            with pytest.raises(StructAIError) as excinfo:
                await bundle.service.execute(record)
            error = excinfo.value
            assert error.code == "STRUCTAI-7000", error.code
            assert error.details["reason"] == "context_not_available", error.details

    asyncio.run(_run())


def test_outbox_receives_the_task_event_and_the_dispatcher_publishes_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ⑥（`docs/02` §5.4 / §42）：任务事件**先写 Outbox**，再由 Dispatcher 发布。"""

    async def _run() -> None:
        from app.domain.events import TaskCompleted
        from app.infrastructure.events import STANDARD_EVENT_TYPES

        (
            runtime,
            factory,
            tenant_id,
            user_id,
            project_id,
            instance_id,
            model_id,
        ) = await _seeded_runtime(tmp_path, monkeypatch)
        delivered: list[str] = []

        async def _handler(event: object) -> None:
            delivered.append(type(event).__name__)

        await runtime.bus.subscribe(TaskCompleted, _handler)
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            context = _context(
                _identity(tenant_id, user_id),
                project_id=project_id,
                instance_id=instance_id,
                model_id=model_id,
            )
            result = await bundle.service.execute_request(_request(context))
            assert result.task_id is not None
        pending = await runtime.outbox.pending()
        assert [record.event_type for record in pending] == ["TaskCompleted"]
        assert pending[0].status == "PENDING"
        assert pending[0].task_id == result.task_id
        assert "TaskCompleted" in STANDARD_EVENT_TYPES
        report = await runtime.dispatcher.dispatch_pending()
        assert report.published == 1, report
        assert delivered == ["TaskCompleted"]
        assert await runtime.outbox.pending() == ()

    asyncio.run(_run())


def test_trace_spans_share_the_trace_id_and_carry_the_task_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ⑥（`docs/02` §12 / §53）：`trace_id` 贯穿 MCP → Tool → Operation → Adapter。"""

    async def _run() -> None:
        from app.domain.enums import TraceSpanKind, TraceStatus

        (
            runtime,
            factory,
            tenant_id,
            user_id,
            project_id,
            instance_id,
            model_id,
        ) = await _seeded_runtime(tmp_path, monkeypatch)
        context = _context(
            _identity(tenant_id, user_id),
            project_id=project_id,
            instance_id=instance_id,
            model_id=model_id,
        )
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            result = await bundle.service.execute_request(_request(context))
            assert result.task_id is not None
        spans = await runtime.trace.spans_for_trace(context.trace_id)
        kinds = [span.kind for span in spans]
        assert kinds == [
            str(TraceSpanKind.MCP),
            str(TraceSpanKind.TOOL),
            str(TraceSpanKind.OPERATION),
            str(TraceSpanKind.ADAPTER),
        ], kinds
        assert {span.trace_id for span in spans} == {context.trace_id}
        operation_span = spans[2]
        adapter_span = spans[3]
        assert adapter_span.parent_span_id == operation_span.id
        assert operation_span.parent_span_id == spans[1].id
        assert spans[1].parent_span_id == spans[0].id
        assert spans[0].parent_span_id is None
        assert all(span.status == str(TraceStatus.OK) for span in spans)
        assert all(span.end_time is not None for span in spans)
        task_spans = await runtime.trace.spans_for_task(result.task_id)
        assert {span.kind for span in task_spans} == {
            str(TraceSpanKind.OPERATION),
            str(TraceSpanKind.ADAPTER),
        }

    asyncio.run(_run())


def test_audit_records_one_entry_per_attempt_and_the_chain_verifies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ⑥（`docs/02` §8 / §44 / §65）：审计一条链、可验证、篡改可检测。"""

    async def _run() -> None:
        from sqlalchemy import text

        (
            runtime,
            factory,
            tenant_id,
            user_id,
            project_id,
            instance_id,
            model_id,
        ) = await _seeded_runtime(tmp_path, monkeypatch)
        context = _context(
            _identity(tenant_id, user_id),
            project_id=project_id,
            instance_id=instance_id,
            model_id=model_id,
        )
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            await bundle.service.execute_request(_request(context))
            await bundle.service.execute_request(_request(context))
            entries = list(await bundle.audit.store.chain(tenant_id=tenant_id))
            assert len(entries) == 2, [entry.action for entry in entries]
            assert entries[0].action == "MODEL.NODE.QUERY"
            assert entries[0].previous_hash is None
            assert entries[1].previous_hash == entries[0].entry_hash
            assert all(entry.result == str(AuditResult.SUCCESS) for entry in entries)
            assert all(entry.user_id == user_id for entry in entries)
            assert all(entry.tenant_id == tenant_id for entry in entries)
            verification = await bundle.audit.verify_chain(tenant_id=tenant_id)
            assert verification.valid is True, verification
            assert verification.total == 2
            # 篡改：直接改一条已落库记录的内容 → 链必须被检测为不成立。
            await uow.session.execute(
                text("UPDATE audit_records SET action = :action WHERE id = :id"),
                {"action": "TAMPERED", "id": entries[0].id},
            )
            await uow.session.flush()
            tampered = await bundle.audit.verify_chain(tenant_id=tenant_id)
            assert tampered.valid is False, tampered
            assert tampered.first_broken_id == entries[0].id
            assert tampered.reason == "hash_mismatch"

    asyncio.run(_run())


def test_audit_never_records_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ⑥（`docs/07` §14.3）：审计 / Trace 属性 / 指标标签都不含 secret。"""

    async def _run() -> None:
        (
            runtime,
            factory,
            tenant_id,
            user_id,
            project_id,
            instance_id,
            model_id,
        ) = await _seeded_runtime(tmp_path, monkeypatch)
        context = _context(
            _identity(tenant_id, user_id),
            project_id=project_id,
            instance_id=instance_id,
            model_id=model_id,
        )
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            await bundle.service.execute_request(_request(context, confirmation_token="CONFIRM"))
            entries = list(await bundle.audit.store.chain(tenant_id=tenant_id))
            blob = json.dumps(
                [
                    {
                        "action": entry.action,
                        "resource": entry.resource,
                        "result": entry.result,
                        "previous_hash": entry.previous_hash,
                        "entry_hash": entry.entry_hash,
                    }
                    for entry in entries
                ],
                ensure_ascii=False,
            )
            for marker in SECRET_MARKERS:
                assert marker not in blob.lower(), marker
            rendered = runtime.metrics.render()
            for marker in SECRET_MARKERS:
                assert marker not in rendered.lower(), marker
            assert runtime.metrics.dropped_labels() == ()

    asyncio.run(_run())


def test_health_readiness_requires_the_registry_and_a_degraded_adapter_is_not_core_down(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ⑥（`docs/02` §16.2 / §94）：Registry 决定 READY；单软件 DOWN ≠ Core DOWN。"""

    async def _run() -> None:
        from app.container import _database_check, register_health_checkers
        from app.observability import READY, HealthService

        settings = _seeded_settings(tmp_path)
        engine = create_engine_for(settings)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = create_session_factory(engine)
        monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
        await seed(factory)
        runtime = build_execution_runtime(
            settings,
            operation_registry=await OperationRegistry.load(engine, factory),
            capability_registry=await CapabilityRegistry.load(engine, factory),
        )
        await register_health_checkers(runtime, engine)
        readiness = await runtime.health.readiness()
        assert readiness["status"] == READY, readiness
        assert await runtime.health.liveness() == {"status": "HEALTHY"}
        report = await runtime.health.health()
        assert report["status"] in {"HEALTHY", "DEGRADED"}, report
        assert set(report) >= {"status", "database", "registry", "task_engine", "adapters"}
        # 未装配 Registry 时 `registry` 检查必须 `UNAVAILABLE` → 不得 READY。
        empty_runtime = build_execution_runtime(settings)
        await register_health_checkers(empty_runtime, engine)
        empty_service = HealthService(empty_runtime.health_registry)
        not_ready = await empty_service.readiness()
        assert not_ready["status"] == "NOT_READY", not_ready
        assert not_ready["checks"]["registry"]["reason"] == "registry_not_assembled"
        assert (await _database_check(engine))["status"] == "HEALTHY"
        await engine.dispose()

    asyncio.run(_run())


def test_runtime_is_not_ready_without_a_registry_and_create_fails_loudly(
    tmp_path: Path,
) -> None:
    """门槛 ①（`docs/07` §14.4）：Registry 未装配 → `create()` 抛 `7000`，绝不用空 Registry。"""

    async def _run() -> None:
        settings = _seeded_settings(tmp_path)
        runtime = build_execution_runtime(settings)
        assert runtime.ready() is False
        assert runtime.operation_registry is None
        assert runtime.capability_registry is None
        factory = runtime.execution
        assert factory is not None
        with pytest.raises(InternalError) as excinfo:
            factory.create(None)  # type: ignore[arg-type]
        assert excinfo.value.code == "STRUCTAI-7000", excinfo.value.code
        assert excinfo.value.details["reason"] == "runtime_not_ready"

    asyncio.run(_run())


# ===== ⑤ 回归与红线（`docs/07` §11 / §14；`docs/08` §3）=====


def test_commit_and_rollback_only_in_unit_of_work() -> None:
    """门槛 ⑦（`docs/02` §16）：`commit` / `rollback` 只允许出现在 `unit_of_work.py`。"""
    offenders: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        if path.name == "unit_of_work.py":
            continue
        calls = _commit_or_rollback_calls(path)
        if calls:
            offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{calls}")
    assert offenders == [], offenders
    assert _commit_or_rollback_calls(APP_DIR / "infrastructure" / "database" / "unit_of_work.py"), (
        "unit_of_work.py 必须仍是唯一的提交点"
    )


def test_application_layer_does_not_import_infrastructure_or_observability() -> None:
    """门槛 ⑦（`docs/07` §2.2）：`app/application/**` 不依赖 Infrastructure / Observability。"""
    offenders: list[str] = []
    for path in sorted(APPLICATION_DIR.rglob("*.py")):
        imported = _imported_modules(path)
        hits = sorted(
            module
            for module in imported
            if any(
                module == forbidden or module.startswith(f"{forbidden}.")
                for forbidden in FORBIDDEN_APPLICATION_IMPORTS
            )
        )
        if hits:
            offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{hits}")
    assert offenders == [], offenders


def test_no_vendor_names_in_app() -> None:
    """门槛 ⑦（`docs/07` §14.2）：`app/` 内**零**厂商专属内容。"""
    offenders: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        lowered = path.read_text(encoding="utf-8").lower()
        for vendor in VENDOR_NAMES:
            if vendor.lower() in lowered:
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{vendor}")
    assert offenders == [], offenders


def test_twenty_codes_and_twenty_four_tables_are_not_regressed(engine: AsyncEngine) -> None:
    """门槛 ⑦（`docs/07` §11 / §4.3）：20 码不扩；建表仍是 **24** 张（**未改表**）。"""

    async def _run() -> None:
        from sqlalchemy import inspect as sa_inspect

        async with engine.connect() as connection:
            names = set(
                await connection.run_sync(
                    lambda sync_connection: sa_inspect(sync_connection).get_table_names()
                )
            )
        assert names == set(TWENTY_FOUR_TABLES_SPEC), names ^ set(TWENTY_FOUR_TABLES_SPEC)
        assert len(Base.metadata.tables) == 24

    asyncio.run(_run())
    literals: set[str] = set()
    for path in sorted(APP_DIR.rglob("*.py")):
        literals.update(re.findall(r"STRUCTAI-\d{4}", path.read_text(encoding="utf-8")))
    assert literals == ERROR_CODES_SPEC, literals ^ ERROR_CODES_SPEC


def test_main_exits_zero_with_empty_stdout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """门槛 ⑦（`docs/08` §3）：`python -m app.main` 退出码 0 且 **stdout 0 字节**（两种情形）。"""
    unprovisioned = _run_main(f"sqlite+aiosqlite:///{(tmp_path / 'p36_empty.db').as_posix()}")
    assert unprovisioned.returncode == 0, unprovisioned.stderr
    assert unprovisioned.stdout == ""

    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    settings = _seeded_settings(tmp_path)
    engine = create_engine_for(settings)

    async def _provision() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await seed(create_session_factory(engine))
        await engine.dispose()

    asyncio.run(_provision())
    provisioned = _run_main(settings.database_url)
    assert provisioned.returncode == 0, provisioned.stderr
    assert provisioned.stdout == ""
    assert "registry ready" in provisioned.stderr
    assert f"batch={BATCH_ID}" in provisioned.stderr
