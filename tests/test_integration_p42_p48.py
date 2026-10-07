"""P42–P48 验收 · 第 3 类：**Integration**（真实 SQLite + Mock Adapter 的端到端）。

门槛（`docs/08` §4 的本批提示词；`docs/07` §12 P42–P48 / §13.1 / §13.3 / §13.6；
`docs/02` §70 / §67）
------------------------------------------------------------------------------
① 链路（`docs/02` §70）：`Tool → Application Service → Task Engine → Mock Adapter`，
   在**真实 SQLite**（每测试一个独立临时库）上端到端跑通。
② 落库证据：任务行 / 审计行 / Outbox 记录 / 链路 Span 逐条可查；
   失败与成功的信封、`SYNC` / `ASYNC` / `DRY_RUN` 三种模式各自可判定。
③ 回归：`python -m app.main` 退出码 0 且 **stdout 0 字节**（未配备 / 已配备两种情形）、
   建表 24 张 + `SELECT 1` → 1（`docs/07` §13.1：Integration Test 通过）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select

import p42_p48_support as support
from app.application.execution.pipeline import PipelineRequest
from app.container import ExecutionRuntime, ExecutionServiceFactory, build_container
from app.domain.enums import AuditResult, TaskStatus
from app.infrastructure.database.models.task import TaskORM
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.interfaces.mcp import build_mcp_server


async def _task_rows(factory: Any) -> list[TaskORM]:
    """读回全部任务行（`tasks` 表；用于端到端的落库证据）。"""
    async with factory() as session:
        return list((await session.execute(select(TaskORM))).scalars().all())


async def _task_count(factory: Any) -> int:
    """任务行数（`docs/02` §92：Dry Run **零**任务落库）。"""
    async with factory() as session:
        return int((await session.execute(select(func.count()).select_from(TaskORM))).scalar())


def _confirmation(
    runtime: ExecutionRuntime, ids: dict[str, str], operation: str, resource_id: str | None
) -> str:
    """现签确认令牌（`docs/07` §8.4；只允许返回给客户端一次）。"""
    return runtime.confirmation.issue(
        user_id=ids["user_id"],
        tenant_id=ids["tenant_id"],
        operation=operation,
        resource_id=resource_id,
    ).token


# ===== ① SYNC：Tool → Service → Task Engine → Mock Adapter（`docs/02` §70 / §77）=====


async def test_sync_query_runs_the_whole_application_chain(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/02` §70 / §77）：SYNC 端到端跑通，且 22 步 + 落库证据齐全。"""
    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_integration_sync.db"
    )
    identity = support.identity_context(ids)
    async with UnitOfWork.from_session_factory(factory) as uow:
        bundle = runtime.execution.create(uow.session)
        server = build_mcp_server(bundle.service)
        response = await server.handle(
            "engineering_model_query",
            support.arguments("MODEL.NODE.QUERY", context=support.client_context(ids)),
            identity=identity,
        )
        assert response.success is True, response.errors
        assert response.execution["mode"] == "SYNC"
        assert response.execution["status"] == "COMPLETED"
        assert response.execution["steps"] == list(support.PIPELINE_ORDER_SPEC[4:])
        assert response.execution["unprovisioned_schemas"] == [
            "structai://schema/model/node/query/v1"
        ], "未配备的 Schema 必须**如实**出现（docs/07 §16 R54）"
        assert response.data is not None
        assert set(response.data) == {"items"}
        assert bundle.audit.records_written() >= 1

    rows = await _task_rows(factory)
    assert len(rows) == 1, rows
    assert rows[0].operation == "MODEL.NODE.QUERY"
    assert rows[0].tool == "engineering_model_query"
    assert rows[0].status == str(TaskStatus.COMPLETED)
    assert rows[0].tenant_id == ids["tenant_id"]
    assert rows[0].result_json is not None
    assert rows[0].lease_owner is None, "完成后不得残留租约"
    assert await runtime.outbox.count() >= 1, "事件必须进 Outbox（docs/02 §6）"
    report = await runtime.dispatcher.dispatch_pending()
    assert report.published >= 1
    assert await runtime.outbox.count() == len(runtime.outbox.records())


# ===== ② ASYNC：任务入队 → Worker 执行 → 结果落库（`docs/02` §78 / §88）=====


async def test_async_build_is_queued_then_completed_by_the_task_engine(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/02` §78；`docs/07` §13.5）：ASYNC 首次响应 = `{mode,status,task_id}`。"""
    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_integration_async.db"
    )
    identity = support.identity_context(ids)
    context = support.client_context(ids)
    async with UnitOfWork.from_session_factory(factory) as uow:
        bundle = runtime.execution.create(uow.session)
        server = build_mcp_server(bundle.service)
        resolved = await bundle.resolver.resolve(
            server.contexts.create(identity, client_context=context).execution
        )
        assert resolved is not None
        token = _confirmation(runtime, ids, "BUILD.COLUMN", resolved.resource_id)
        built = await server.handle(
            "engineering_model_build",
            support.arguments(
                "BUILD.COLUMN",
                parameters=support.BUILD_COLUMN_PARAMETERS,
                context=context,
                confirmation_token=token,
            ),
            identity=identity,
        )
        assert built.success is True, built.errors
        assert built.execution["mode"] == "ASYNC"
        assert built.execution["status"] == str(TaskStatus.QUEUED)
        assert built.data is None, "异步首次响应的 data 为 null（docs/02 §71）"
        task_id = built.execution["task_id"]
        assert isinstance(task_id, str)

        record = await bundle.engine.run_task(task_id)
        assert str(record.status) == "COMPLETED", record.status
        column = json.loads(record.result_json or "{}")
        assert set(column) == {"node_ids", "element_ids"}, column
        assert runtime.confirmation.pending() == 0, "确认令牌一次性消费（docs/02 §38）"

        read_back = await server.handle(
            "engineering_model_query",
            support.arguments("MODEL.NODE.QUERY", context=context),
            identity=identity,
        )
        assert read_back.success is True, read_back.errors
        assert read_back.data is not None
        items = read_back.data["items"]
        assert {item["id"] for item in items} == set(column["node_ids"]), items
        assert {item["id"]: item["z"] for item in items}[column["node_ids"][1]] == (
            support.COLUMN_HEIGHT_M
        )

    rows = await _task_rows(factory)
    assert len(rows) == 2, rows
    build_row = next(row for row in rows if row.operation == "BUILD.COLUMN")
    assert build_row.status == str(TaskStatus.COMPLETED)
    assert build_row.started_at is not None
    assert build_row.completed_at is not None
    assert build_row.lease_owner is None


# ===== ③ DRY_RUN：不落库、不执行（`docs/02` §92）=====


async def test_dry_run_creates_no_task_and_calls_no_adapter(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/02` §92）：Dry Run **零**任务落库、**零** Adapter 调用、锁已释放。"""
    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_integration_dry_run.db"
    )
    identity = support.identity_context(ids)
    context = support.client_context(ids)
    async with UnitOfWork.from_session_factory(factory) as uow:
        bundle = runtime.execution.create(uow.session)
        server = build_mcp_server(bundle.service)
        resolved = await bundle.resolver.resolve(
            server.contexts.create(identity, client_context=context).execution
        )
        assert resolved is not None
        token = _confirmation(runtime, ids, "BUILD.COLUMN", resolved.resource_id)
        response = await server.handle(
            "engineering_model_build",
            support.arguments(
                "BUILD.COLUMN",
                parameters=support.BUILD_COLUMN_PARAMETERS,
                context=context,
                confirmation_token=token,
                dry_run=True,
            ),
            identity=identity,
        )
        assert response.success is True, response.errors
        assert response.execution["mode"] == "DRY_RUN"
        assert "Adapter" not in response.execution["steps"], response.execution["steps"]
        assert "Postconditions" in response.execution["steps"]
        assert await bundle.pipeline.locks.held_count() == 0, "Dry Run 的锁必须释放"

    assert await _task_count(factory) == 0, "Dry Run 不得落任何任务（docs/02 §92）"


# ===== ④ 文档规定的五步链（`docs/07` §13.5）在 Application Service 层跑通 =====


async def test_the_documented_five_step_chain_persists_real_results(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/07` §13.3 / §13.5）：`BUILD.COLUMN → 边界 / 荷载 → ANALYSIS.STATIC
    → RESULT.NODE.DISPLACEMENT → DESIGN.STEEL` 全部通过，数值来自 Mock Adapter。"""
    from app.interfaces.mcp import MCPContextFactory

    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_integration_chain.db"
    )
    identity = support.identity_context(ids)
    client_context = support.client_context(ids)
    async with UnitOfWork.from_session_factory(factory) as uow:
        bundle = runtime.execution.create(uow.session)
        execution_context = (
            MCPContextFactory().create(identity, client_context=client_context).execution
        )
        resolved = await bundle.resolver.resolve(execution_context)
        assert resolved is not None
        resource_id = resolved.resource_id

        async def call(
            tool: str,
            operation: str,
            parameters: dict[str, object] | None = None,
            *,
            confirm: bool = False,
        ) -> tuple[str, dict[str, object] | None]:
            """经 Application Service 调一次；返回 `(mode, result)`（ASYNC 由 Worker 跑完）。"""
            token = _confirmation(runtime, ids, operation, resource_id) if confirm else None
            result = await bundle.service.execute_request(
                PipelineRequest(
                    tool=tool,
                    operation=operation,
                    parameters=dict(parameters or {}),
                    context=execution_context,
                    confirmation_token=token,
                )
            )
            if result.mode == "ASYNC":
                assert result.status == str(TaskStatus.QUEUED), result.status
                assert result.task_id is not None
                record = await bundle.engine.run_task(result.task_id)
                assert str(record.status) == "COMPLETED", record.status
                payload = json.loads(record.result_json or "{}")
                return result.mode, payload
            return result.mode, None if result.result is None else dict(result.result)

        mode, column = await call(
            "engineering_model_build",
            "BUILD.COLUMN",
            dict(support.BUILD_COLUMN_PARAMETERS),
            confirm=True,
        )
        assert mode == "ASYNC"
        assert column is not None
        assert set(column) == {"node_ids", "element_ids"}, column
        base_id, top_id = column["node_ids"]
        element_id = column["element_ids"][0]

        _, boundary = await call(
            "engineering_model_assign",
            "MODEL.BOUNDARY.ASSIGN",
            {
                "node_id": base_id,
                "ux": True,
                "uy": True,
                "uz": True,
                "rx": True,
                "ry": True,
                "rz": True,
            },
        )
        assert boundary == {
            "node_id": base_id,
            "ux": True,
            "uy": True,
            "uz": True,
            "rx": True,
            "ry": True,
            "rz": True,
        }, boundary
        _, load = await call(
            "engineering_model_assign",
            "MODEL.LOAD.ASSIGN",
            {"node_id": top_id, "fz": -support.ELEMENT_FORCE_N},
        )
        assert load == {
            "node_id": top_id,
            "fx": 0.0,
            "fy": 0.0,
            "fz": -support.ELEMENT_FORCE_N,
        }, load

        mode, analysis = await call("engineering_analysis", "ANALYSIS.STATIC", {}, confirm=True)
        assert mode == "ASYNC"
        assert analysis is not None
        assert analysis["status"] == "COMPLETED"
        assert analysis["engineering_grade"] is False, "Mock 不得冒充工程级结果"

        _, displacement = await call(
            "engineering_result", "RESULT.NODE.DISPLACEMENT", {"node_id": top_id}
        )
        assert displacement is not None
        assert displacement["uz"] == pytest.approx(support.EXPECTED_AXIAL_DISPLACEMENT, rel=1e-9), (
            displacement
        )
        _, force = await call(
            "engineering_result", "RESULT.ELEMENT.FORCE", {"element_id": element_id}
        )
        assert force is not None
        assert force["axial"] == pytest.approx(-support.ELEMENT_FORCE_N), force

        mode, design = await call(
            "engineering_design", "DESIGN.STEEL", {"element_id": element_id}, confirm=True
        )
        assert mode == "ASYNC"
        assert design == {
            "element_id": element_id,
            "utilization": support.STEEL_UTILIZATION,
            "status": "PASS",
            "engine": "MockEngineering",
            "engineering_grade": False,
        }, design
        assert runtime.confirmation.pending() == 0, "确认令牌必须一次性消费"

    rows = await _task_rows(factory)
    assert len(rows) >= 6, [row.operation for row in rows]
    assert all(row.status == str(TaskStatus.COMPLETED) for row in rows)
    assert {row.operation for row in rows} >= {
        "BUILD.COLUMN",
        "MODEL.BOUNDARY.ASSIGN",
        "MODEL.LOAD.ASSIGN",
        "ANALYSIS.STATIC",
        "RESULT.NODE.DISPLACEMENT",
        "RESULT.ELEMENT.FORCE",
        "DESIGN.STEEL",
    }


# ===== ⑤ 容器装配与 P02 / P04 回归（`docs/07` §12 P08 / P36；`docs/08` §4 门槛 ④）=====


async def test_container_startup_provisions_the_registry(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/02` §33 / §123）：`startup()` 装配 Registry 且容器形状不变。"""
    settings = await support.prepare_database(
        tmp_path, monkeypatch, name="p42_integration_container.db"
    )
    container = build_container(settings)
    assert container.started is False
    assert container.operation_registry is None
    await container.startup()
    try:
        assert container.started is True
        assert container.operation_registry is not None
        assert len(container.operation_registry.names()) == 69
        assert isinstance(container.execution_service, ExecutionServiceFactory)
        assert container.execution_service.runtime.ready() is True
    finally:
        await container.shutdown()


def test_main_exits_zero_with_empty_stdout_when_unprovisioned(tmp_path: Path) -> None:
    """门槛 ④（`docs/03` §42；`docs/02` §97）：未配备库时退出码 0 且 stdout **0 字节**。"""
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p42_main_offline.db').as_posix()}"
    completed = support.run_main(database_url=database_url)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert "structai" in completed.stderr
    assert "batch=" in completed.stderr


async def test_main_exits_zero_with_empty_stdout_when_provisioned(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ④（`docs/07` §14.4）：已配备库时同样退出码 0、stdout **0 字节**、Registry 就绪。"""
    settings = await support.prepare_database(tmp_path, monkeypatch, name="p42_main_provisioned.db")
    completed = support.run_main(
        database_url=settings.database_url,
        env={"ARTIFACT_ROOT": settings.artifact_root},
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert "registry ready" in completed.stderr


# ===== ⑥ 多租户隔离与审计链（`docs/02` §22 / §8；`docs/07` §8.2）=====


async def test_task_store_is_tenant_scoped_end_to_end(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/02` §22；`docs/07` §14.3）：任务读取按租户隔离，跨租户读不到。"""
    from uuid import UUID

    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_integration_tenant.db"
    )
    identity = support.identity_context(ids)
    async with UnitOfWork.from_session_factory(factory) as uow:
        bundle = runtime.execution.create(uow.session)
        server = build_mcp_server(bundle.service)
        response = await server.handle(
            "engineering_model_query",
            support.arguments("MODEL.NODE.QUERY", context=support.client_context(ids)),
            identity=identity,
        )
        assert response.success is True, response.errors
        task_id = response.execution["task_id"]
        assert isinstance(task_id, str)
        assert await bundle.engine.store.get(task_id, ids["tenant_id"]) is not None
        assert await bundle.engine.store.get(task_id, str(UUID(int=9999))) is None


async def test_audit_chain_is_recomputable_and_records_success_and_denial(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/02` §8 / §39；`docs/07` §16 R59）：审计链可复算，成功与拒绝都留痕。"""
    name = "p42_integration_audit.db"
    settings = support.seeded_settings(tmp_path, name=name)
    runtime, factory, ids = await support.seeded_runtime(tmp_path, monkeypatch, name=name)
    identity = support.identity_context(ids)
    async with UnitOfWork.from_session_factory(factory) as uow:
        server = build_mcp_server(runtime.execution.create(uow.session).service)
        allowed = await server.handle(
            "engineering_model_query",
            support.arguments("MODEL.NODE.QUERY", context=support.client_context(ids)),
            identity=identity,
        )
        assert allowed.success is True, allowed.errors
    async with UnitOfWork.from_session_factory(factory) as uow:
        server = build_mcp_server(runtime.execution.create(uow.session).service)
        refused = await server.handle(
            "engineering_model_build",
            support.arguments(
                "BUILD.COLUMN",
                parameters=support.BUILD_COLUMN_PARAMETERS,
                context=support.client_context(ids),
            ),
            identity=identity,
        )
        assert refused.success is False
        assert refused.errors[0]["code"] == support.CONFIRMATION_REQUIRED_CODE
    async with UnitOfWork.from_session_factory(factory) as uow:
        verification = await runtime.execution.create(uow.session).audit.verify_chain(
            tenant_id=ids["tenant_id"]
        )
    assert verification.valid is True, verification.reason
    assert verification.total >= 2
    assert verification.first_broken_id is None
    engine = support.engine_for(settings)
    try:
        values = await support.all_text_values(engine)
        assert str(AuditResult.SUCCESS) in values
        assert str(AuditResult.DENIED) in values
        assert support.TEST_PASSWORD not in values, "绝不记录 secret（docs/07 §14.3）"
    finally:
        await engine.dispose()


# ===== ⑦ Seed 幂等与落库规模（`docs/02` §45 / §44；`docs/07` §12 P07）=====


async def test_seed_is_idempotent_and_creates_the_documented_rows(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/02` §45）：Seed 可重复执行且第二次为 no-op；落库规模逐表一致。"""
    from app.infrastructure.database.seed import seed

    engine, factory = await support.seeded_database(
        tmp_path, monkeypatch, name="p42_integration_seed.db"
    )
    try:
        report = await seed(factory)
        assert report.created == {}
        assert report.updated == {}
        assert report.is_noop is True
        assert await support.row_count(engine, "tenants") == 1
        assert await support.row_count(engine, "users") == 1
        assert await support.row_count(engine, "permissions") == 12
        assert await support.row_count(engine, "roles") == 4
        assert await support.row_count(engine, "role_permissions") == 24
        assert await support.row_count(engine, "capabilities") == 41
        assert await support.row_count(engine, "operations") == 69
        assert await support.row_count(engine, "software_instances") == 1
        assert await support.select_one(engine) == 1
    finally:
        await engine.dispose()
