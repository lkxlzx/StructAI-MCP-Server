"""P42–P48 验收 · 第 2 类：**Contract**（9 Tool / 69 Operation / 响应信封 / Schema）。

门槛（`docs/08` §4 的本批提示词；`docs/07` §12 P42–P48 / §13.1 / §13.6；`docs/02` §69 /
§67）
------------------------------------------------------------------------------
① 契约面：9 Tool 的**声明 = 注册 = 装配**；请求信封 6 字段、响应信封 13 键、
   错误信封 5 键；69 个 Operation 逐条可解析且 12 字段齐全；
   `docs/02` §69 的六类 Schema（Tool / Operation / Response / Error / Context /
   Canonical Model）各有**可执行**判定。
② 每个测试用独立临时库（`docs/08` §4 门槛 ②）；不依赖执行顺序。
③ 判定逐条可执行（`docs/07` §13.1：Contract / Unit Test 通过）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

import p42_p48_support as support
from app.application.execution.context import CLIENT_CONTROLLED_IDENTITY_FIELDS
from app.application.execution.pipeline import (
    MCP_PIPELINE_STEPS,
    PIPELINE_GATE_STEPS,
    PIPELINE_RESPONSE_STEPS,
    PIPELINE_TASK_STEP,
    ExecutionPipeline,
)
from app.application.execution.service import ExecutionResult
from app.application.security.context import IdentityContext, SecurityContext
from app.container import AppContainer, ExecutionServiceFactory, build_container
from app.domain.enums import ExecutionMode, RiskLevel
from app.domain.errors import ProtocolError
from app.domain.protocols import OperationDefinition
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.infrastructure.registry.operation_registry import (
    OPERATION_PROFILES,
    OperationRegistry,
)
from app.interfaces.mcp import (
    MCP_STEPS,
    RESPONSE_KEYS,
    TOOL_CLASSES,
    TOOL_NAMES,
    TOOL_REQUEST_FIELDS,
    BaseEngineeringTool,
    MCPContext,
    MCPContextFactory,
    MCPServer,
    ToolDispatcher,
    ToolRequest,
    ToolResponse,
    build_mcp_server,
    build_tools,
    error_envelope,
    sanitize_details,
    unknown_tool_error,
)
from app.interfaces.mcp.errors import (
    INVALID_ARGUMENTS_MESSAGE,
    REDACTION_MARKER,
    UNKNOWN_TOOL_REASON,
)
from app.interfaces.mcp.tools.base import (
    CONTEXT_NOT_A_MAPPING_REASON,
    INVALID_CONFIRMATION_TOKEN_REASON,
    INVALID_DRY_RUN_REASON,
    INVALID_IDEMPOTENCY_KEY_REASON,
    MISSING_OPERATION_REASON,
    PARAMETERS_NOT_A_MAPPING_REASON,
)
from app.interfaces.mcp.transport import TOOL_INPUT_SCHEMA, MCPRuntimeLimits, tool_definition


class _RecordingService:
    """记录 `PipelineRequest` 的假执行服务（只用于「可注册 / 可分发」的契约断言）。"""

    def __init__(self) -> None:
        self.requests: list[object] = []

    async def execute_request(self, request: object) -> ExecutionResult:
        """记录请求并返回一个成功结果（**不**触碰任何真实服务）。"""
        self.requests.append(request)
        return ExecutionResult(
            mode="SYNC",
            status="COMPLETED",
            tool=str(getattr(request, "tool", "")),
            operation=str(getattr(request, "operation", "")),
            task_id="task-stub",
            result={"stub": True},
            steps=("Resolve Tool", "MCP Response"),
        )


# ===== ① 9 Tool 契约（`docs/02` §53 / §74 / §69）=====


def test_exactly_nine_tools_are_declared_registered_and_built() -> None:
    """门槛 ①（`docs/02` §53 / §74）：**恰好 9 个** Tool，声明 = 注册 = 装配。"""
    assert TOOL_NAMES == support.TOOL_NAMES_SPEC
    assert len(TOOL_NAMES) == 9
    assert tuple(TOOL_CLASSES) == support.TOOL_NAMES_SPEC
    assert len(set(TOOL_CLASSES.values())) == 9
    assert all(issubclass(cls, BaseEngineeringTool) for cls in TOOL_CLASSES.values())
    for name, tool_class in TOOL_CLASSES.items():
        assert tool_class.name == name, (name, tool_class.name)

    service = _RecordingService()
    tools = build_tools(service)  # type: ignore[arg-type]
    assert tuple(tool.name for tool in tools) == support.TOOL_NAMES_SPEC
    dispatcher = ToolDispatcher(tools)
    assert dispatcher.names() == tuple(sorted(support.TOOL_NAMES_SPEC))
    assert len(dispatcher) == 9
    assert all(name in dispatcher for name in support.TOOL_NAMES_SPEC)

    server = MCPServer(execution=service)  # type: ignore[arg-type]
    assert server.list_tools() == tuple(sorted(support.TOOL_NAMES_SPEC))
    assert server.tool_names() == tuple(sorted(support.TOOL_NAMES_SPEC))
    assert len(server.dispatcher) == 9


def test_tool_input_schema_is_the_documented_two_level_envelope() -> None:
    """门槛 ①（`docs/02` §84 / `docs/03` §27）：Tool 输入 Schema 是两级信封。"""
    assert TOOL_INPUT_SCHEMA["type"] == "object"
    assert tuple(TOOL_INPUT_SCHEMA["properties"]) == support.TOOL_INPUT_SCHEMA_KEYS_SPEC
    assert TOOL_INPUT_SCHEMA["required"] == ["operation"]
    for name in support.TOOL_NAMES_SPEC:
        definition = tool_definition(name)
        assert definition.name == name
        assert dict(definition.input_schema) == dict(TOOL_INPUT_SCHEMA), name


def test_runtime_limits_follow_the_documented_defaults() -> None:
    """门槛 ①（`docs/03` §20 / §79）：传输层限额字段与默认值逐条落地。"""
    limits = MCPRuntimeLimits()
    for field in support.LIMIT_FIELDS_SPEC:
        assert hasattr(limits, field), field
    assert limits.max_message_bytes > 0
    assert limits.max_request_bytes > 0
    assert limits.max_tool_arguments_bytes > 0
    assert limits.max_concurrent_sessions > 0
    assert limits.max_requests_per_session > 0
    assert limits.max_inflight_requests > 0


# ===== ② 请求 / 响应 / 错误信封（`docs/02` §54 / §71；`docs/07` §11）=====


def test_request_envelope_has_exactly_the_six_frozen_fields() -> None:
    """门槛 ①（`docs/02` §54 / §70）：请求信封 **恰好 6** 字段，且 `repr` 不带 token。"""
    assert TOOL_REQUEST_FIELDS == support.TOOL_REQUEST_FIELDS_SPEC
    assert len(TOOL_REQUEST_FIELDS) == 6
    request = ToolRequest.from_mapping(
        {
            "operation": "BUILD.COLUMN",
            "parameters": {"height": 6.0},
            "context": {"model_id": "m-1"},
            "idempotency_key": "k-1",
            "confirmation_token": "token-value",
            "dry_run": True,
            "unknown_key": "ignored",
            "user_id": "ignored",
            "tenant_id": "ignored",
            "roles": ["ignored"],
            "permissions": ["ignored"],
            "session_id": "ignored",
        }
    )
    assert request.operation == "BUILD.COLUMN"
    assert request.parameters == {"height": 6.0}
    assert request.context == {"model_id": "m-1"}
    assert request.idempotency_key == "k-1"
    assert request.dry_run is True
    assert "token-value" not in repr(request), "confirmation token 是 secret（docs/07 §14.3）"
    assert not hasattr(request, "user_id")
    assert not hasattr(request, "tenant_id")


def test_request_envelope_rejects_malformed_arguments_with_structai_1000() -> None:
    """门槛 ①（`docs/02` §54；`docs/07` §14.3）：信封非法 → `STRUCTAI-1000` 且不静默强转。"""
    with pytest.raises(ProtocolError) as missing:
        ToolRequest.from_mapping({})
    assert missing.value.code == support.PROTOCOL_ERROR_CODE
    assert missing.value.details["reason"] == MISSING_OPERATION_REASON
    assert missing.value.message == INVALID_ARGUMENTS_MESSAGE

    for arguments, reason in (
        (
            {"operation": "BUILD.COLUMN", "parameters": ["not", "a", "mapping"]},
            PARAMETERS_NOT_A_MAPPING_REASON,
        ),
        (
            {"operation": "BUILD.COLUMN", "context": ["not", "a", "mapping"]},
            CONTEXT_NOT_A_MAPPING_REASON,
        ),
        (
            {"operation": "BUILD.COLUMN", "idempotency_key": 5},
            INVALID_IDEMPOTENCY_KEY_REASON,
        ),
        (
            {"operation": "BUILD.COLUMN", "confirmation_token": 5},
            INVALID_CONFIRMATION_TOKEN_REASON,
        ),
        ({"operation": "BUILD.COLUMN", "dry_run": "yes"}, INVALID_DRY_RUN_REASON),
    ):
        with pytest.raises(ProtocolError) as failure:
            ToolRequest.from_mapping(arguments)
        assert failure.value.code == support.PROTOCOL_ERROR_CODE
        assert failure.value.details["reason"] == reason, arguments


def test_response_envelope_has_the_thirteen_documented_keys() -> None:
    """门槛 ①（`docs/02` §71 ∪ `docs/07` §5.3）：响应信封 **13** 键且逐键齐全。"""
    assert RESPONSE_KEYS == support.RESPONSE_KEYS_SPEC
    assert len(RESPONSE_KEYS) == 13
    response = ToolResponse(
        success=True,
        request_id="req_00000000000000000000000000000001",
        trace_id="trace_00000000000000000000000000000001",
        tool="engineering_model_query",
        operation="MODEL.NODE.QUERY",
        execution={"mode": "SYNC", "status": "COMPLETED"},
        data={"items": []},
        pagination={"has_more": False, "next_cursor": None},
        artifacts=(),
        warnings=(),
        errors=(),
        metadata={"mcp_steps": list(support.MCP_STEPS_SPEC)},
    )
    payload = response.to_dict()
    assert tuple(payload) == support.RESPONSE_KEYS_SPEC
    assert payload["success"] is True
    assert payload["error"] is None
    assert response.error is None

    failure = ToolResponse(
        success=False,
        request_id=response.request_id,
        trace_id=response.trace_id,
        tool="engineering_model_query",
        operation="MODEL.NODE.QUERY",
        execution={"mode": "SYNC", "status": "FAILED"},
        errors=(error_envelope(unknown_tool_error("engineering_nope")),),
    )
    failure_payload = failure.to_dict()
    assert tuple(failure_payload) == support.RESPONSE_KEYS_SPEC
    assert failure_payload["errors"]
    assert failure.error == failure_payload["errors"][0]


def test_error_schema_is_five_keys_and_sanitizes_secret_keys() -> None:
    """门槛 ①（`docs/07` §11 / `docs/03` §62）：错误信封 5 键；敏感键值被替换为 `<redacted>`。"""
    error = unknown_tool_error("engineering_nope")
    envelope = error_envelope(error)
    assert tuple(envelope) == support.ERROR_ENVELOPE_KEYS_SPEC
    assert envelope["code"] == support.PROTOCOL_ERROR_CODE
    assert envelope["retryable"] is False
    assert envelope["details"]["reason"] == UNKNOWN_TOOL_REASON

    sanitized = sanitize_details(
        {
            "reason": UNKNOWN_TOOL_REASON,
            "password": "p",
            "api_key": "k",
            "confirmation_token": "t",
            "nested": {"private_key": "x", "stage": "mcp"},
            "list": [{"authorization": "Bearer y"}],
        }
    )
    assert sanitized["reason"] == UNKNOWN_TOOL_REASON
    for key in ("password", "api_key", "confirmation_token"):
        assert sanitized[key] == REDACTION_MARKER, key
    assert sanitized["nested"]["private_key"] == REDACTION_MARKER
    assert sanitized["nested"]["stage"] == "mcp"
    assert sanitized["list"][0]["authorization"] == REDACTION_MARKER

    leaked = error_envelope(
        ProtocolError(
            "boom",
            details={"password": "secret-value", "reason": "x"},
        )
    )
    assert "secret-value" not in json.dumps(leaked, ensure_ascii=False)
    assert leaked["details"]["password"] == REDACTION_MARKER


# ===== ③ Context Schema（`docs/02` §54 / §57 / §69；`docs/07` §8.1）=====


def test_context_schema_carries_server_identity_and_core_generated_ids() -> None:
    """门槛 ①（`docs/02` §57 / §69）：身份来自**服务端**；两个 id 由 Core 生成。"""
    identity = IdentityContext(
        user_id=UUID(int=11),
        tenant_id=UUID(int=12),
        session_id=UUID(int=13),
        roles=("system_admin",),
        authentication_method="PASSWORD",
    )
    security = SecurityContext(identity=identity, permissions=frozenset({"MODEL_READ"}))
    context = MCPContextFactory().from_security_context(security)
    assert isinstance(context, MCPContext)
    assert context.identity is identity
    assert context.request_id.startswith("req_")
    assert context.trace_id.startswith("trace_")
    assert context.request_id == context.execution.request_id
    assert context.trace_id == context.execution.trace_id
    assert context.session_id == str(UUID(int=13))
    assert context.roles == ("system_admin",)

    forged = MCPContextFactory().create(
        identity,
        permissions=frozenset({"MODEL_READ"}),
        client_context={
            "project_id": str(UUID(int=99)),
            "identity": "forged",
            "user_id": "forged",
            "tenant_id": "forged",
            "roles": ["system_admin"],
            "permissions": ["SYSTEM_ADMIN"],
            "session_id": "forged",
        },
    )
    assert forged.identity is identity, "客户端身份字段一律忽略（docs/07 §8.1）"
    assert set(forged.ignored_identity_fields) == {
        "identity",
        "user_id",
        "tenant_id",
        "roles",
        "permissions",
        "session_id",
    }
    assert set(forged.ignored_identity_fields) == set(CLIENT_CONTROLLED_IDENTITY_FIELDS)


# ===== ④ Operation Schema（`docs/02` §11 / §24 / §69；`docs/07` §5.1 / §12 P08）=====


async def test_the_nine_tools_partition_the_sixty_nine_operations(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/07` §5.1）：9 个 Tool **恰好**划分落库的 **69** 个 Operation。"""
    runtime, _factory, _ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_contract_partition.db"
    )
    registry = runtime.operation_registry
    assert registry is not None
    definitions = await registry.list()
    assert len(definitions) == 69
    counts: dict[str, int] = {name: 0 for name in support.TOOL_NAMES_SPEC}
    for definition in definitions:
        assert definition.tool in counts, definition.name
        counts[definition.tool] += 1
    assert tuple(sorted(counts.items())) == tuple(sorted(support.TOOL_OPERATION_COUNTS_SPEC))
    for tool, operation, mode in support.TOOL_CALL_MATRIX_SPEC:
        definition = registry.require(operation)
        assert definition.tool == tool, (tool, operation)
        assert str(definition.execution_mode) == mode, (operation, definition.execution_mode)


async def test_every_operation_definition_has_the_twelve_frozen_fields(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/02` §11 / §24）：69 个 Operation 逐条 12 字段齐全且取值在冻结词表内。"""
    runtime, _factory, _ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_contract_operations.db"
    )
    registry = runtime.operation_registry
    assert registry is not None
    definitions = await registry.list()
    assert set(OPERATION_PROFILES) == {definition.name for definition in definitions}
    assert len(OPERATION_PROFILES) == 69
    for definition in definitions:
        assert isinstance(definition.risk_level, RiskLevel), definition.name
        assert isinstance(definition.execution_mode, ExecutionMode), definition.name
        assert definition.input_schema.startswith("structai://schema/"), definition.name
        assert definition.output_schema.startswith("structai://schema/"), definition.name
        assert definition.input_schema.endswith("/v1"), definition.name
        assert definition.output_schema.endswith("/result/v1"), definition.name
        assert definition.recovery_policy in support.RECOVERY_POLICIES_SPEC, definition.name
        assert isinstance(definition.transactional, bool)
        assert isinstance(definition.rollback_supported, bool)
        assert isinstance(definition.dry_run_supported, bool)
        assert definition.required_permissions, definition.name
        for permission in definition.required_permissions:
            assert permission.isupper(), (definition.name, permission)
        for capability in definition.required_capabilities:
            assert "." in capability, (definition.name, capability)


# ===== ⑤ Response / Canonical Model Schema（`docs/02` §71 / §89–§90）=====


async def test_success_and_failure_execution_envelopes_are_the_same_shape(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/02` §71；`docs/07` §16 R57）：失败与成功的 `execution` 段**同形**。"""
    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_contract_envelope.db"
    )
    identity = support.identity_context(ids)
    context = support.client_context(ids)
    async with UnitOfWork.from_session_factory(factory) as uow:
        server = build_mcp_server(runtime.execution.create(uow.session).service)
        succeeded = await server.handle(
            "engineering_model_query",
            support.arguments("MODEL.NODE.QUERY", context=context),
            identity=identity,
        )
        refused = await server.handle(
            "engineering_model_build",
            support.arguments(
                "BUILD.COLUMN",
                parameters=support.BUILD_COLUMN_PARAMETERS,
                context=context,
            ),
            identity=identity,
        )
    assert succeeded.success is True, succeeded.errors
    assert refused.success is False
    assert refused.errors[0]["code"] == support.CONFIRMATION_REQUIRED_CODE
    assert refused.errors[0]["details"]["reason"] == support.MISSING_TOKEN_REASON
    assert set(succeeded.to_dict()) == set(refused.to_dict())
    assert set(succeeded.execution) == set(refused.execution), "失败与成功的 execution 段同形"
    assert tuple(succeeded.to_dict()) == support.RESPONSE_KEYS_SPEC
    assert succeeded.metadata["mcp_steps"] == list(support.MCP_STEPS_SPEC)
    assert succeeded.execution["steps"] == list(support.PIPELINE_ORDER_SPEC[4:])
    assert MCP_STEPS == support.MCP_STEPS_SPEC
    assert MCP_PIPELINE_STEPS == support.MCP_STEPS_SPEC
    assert (
        MCP_PIPELINE_STEPS
        + PIPELINE_GATE_STEPS
        + (PIPELINE_TASK_STEP,)
        + support.PIPELINE_EXECUTION_STEPS_SPEC
        + PIPELINE_RESPONSE_STEPS
    ) == support.PIPELINE_ORDER_SPEC
    assert isinstance(runtime.execution, ExecutionServiceFactory)
    async with UnitOfWork.from_session_factory(factory) as uow:
        bundle = runtime.execution.create(uow.session)
        assert isinstance(bundle.pipeline, ExecutionPipeline)
        assert isinstance(bundle.service, object)


async def test_canonical_model_shapes_come_from_the_mock_adapter(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/02` §89 / §90）：规范化结果形状逐条一致（**不**硬编码数值）。"""
    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_contract_canonical.db"
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
        token = runtime.confirmation.issue(
            user_id=ids["user_id"],
            tenant_id=ids["tenant_id"],
            operation="BUILD.COLUMN",
            resource_id=resolved.resource_id,
        ).token
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
        task_id = built.execution["task_id"]
        assert isinstance(task_id, str)
        record = await bundle.engine.run_task(task_id)
        assert str(record.status) == "COMPLETED", record.status
        column = json.loads(record.result_json or "{}")
        assert set(column) == {"node_ids", "element_ids"}, column
        base_id, top_id = column["node_ids"]
        element_id = column["element_ids"][0]

        nodes = await server.handle(
            "engineering_model_query",
            support.arguments("MODEL.NODE.QUERY", context=context),
            identity=identity,
        )
        assert nodes.success is True, nodes.errors
        assert set(nodes.data or {}) == {"items"}, nodes.data
        assert set(nodes.pagination or {}) == {"has_more", "next_cursor"}

        load = await server.handle(
            "engineering_model_assign",
            support.arguments(
                "MODEL.LOAD.ASSIGN",
                parameters={"node_id": top_id, "fz": -support.ELEMENT_FORCE_N},
                context=context,
            ),
            identity=identity,
        )
        assert load.success is True, load.errors
        assert set(load.data or {}) == {"node_id", "fx", "fy", "fz"}, load.data

        displacement = await server.handle(
            "engineering_result",
            support.arguments(
                "RESULT.NODE.DISPLACEMENT",
                parameters={"node_id": top_id},
                context=context,
            ),
            identity=identity,
        )
        assert displacement.success is True, displacement.errors
        assert set(displacement.data or {}) == {
            "node_id",
            "ux",
            "uy",
            "uz",
            "engine",
            "engineering_grade",
        }, displacement.data
        assert displacement.data is not None
        assert displacement.data["uz"] == pytest.approx(
            support.EXPECTED_AXIAL_DISPLACEMENT, rel=1e-9
        ), "数值必须来自 Mock Adapter（docs/07 §13.5）"
        assert element_id


# ===== ⑥ 结构红线与 P04 / P02 回归（`docs/07` §13.1 / §14；`docs/08` §4 门槛 ④⑥）=====


def test_container_shape_is_unchanged(tmp_path: Path) -> None:
    """门槛 ⑥（`docs/02` §33）：`AppContainer` 仍为 **7** 字段冻结形状。"""
    assert tuple(AppContainer.__dataclass_fields__) == support.CONTAINER_FIELDS_SPEC
    assert len(support.CONTAINER_FIELDS_SPEC) == 7
    container = build_container(support.seeded_settings(tmp_path, name="p42_contract_container.db"))
    assert isinstance(container, AppContainer)
    assert container.started is False
    assert container.execution_service is None
    assert container.operation_registry is None


async def test_operation_registry_returns_the_complete_build_column_definition(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/07` §12 P08）：`get("BUILD.COLUMN")` 返回**完整** 12 字段定义。"""
    engine, factory = await support.seeded_database(
        tmp_path, monkeypatch, name="p42_contract_registry.db"
    )
    registry = await OperationRegistry.load(engine, factory)
    assert registry is not None
    definition = registry.require("BUILD.COLUMN")
    assert isinstance(definition, OperationDefinition)
    assert definition.name == "BUILD.COLUMN"
    assert definition.tool == "engineering_model_build"
    assert definition.risk_level is RiskLevel.HIGH
    assert definition.execution_mode is ExecutionMode.ASYNC
    assert definition.input_schema == "structai://schema/build/column/v1"
    assert definition.output_schema == "structai://schema/build/column/result/v1"
    assert definition.required_capabilities == ("MODEL.NODE.WRITE", "MODEL.ELEMENT.WRITE")
    assert "MODEL_WRITE" in definition.required_permissions
    assert definition.transactional is True
    assert definition.rollback_supported is True
    assert definition.dry_run_supported is True
    assert definition.recovery_policy == "STATE_RECONCILE"
    assert len(registry.names()) == 69
    await engine.dispose()


async def test_p04_tables_and_select_one_are_not_regressed(tmp_path: Path) -> None:
    """门槛 ④（`docs/07` §12 P04）：建表 **24** 张、`SELECT 1` → 1、**不得改表**。"""
    settings = support.seeded_settings(tmp_path, name="p42_contract_tables.db")
    engine = support.engine_for(settings)
    await support.create_tables(engine)
    assert await support.table_names(engine) == tuple(sorted(support.TWENTY_FOUR_TABLES_SPEC))
    assert await support.select_one(engine) == 1
    await engine.dispose()


def test_twenty_codes_are_not_extended() -> None:
    """门槛 ⑥（`docs/07` §11）：`app/` 内出现的码字面量**恰好**是 20 码契约。"""
    assert support.structai_code_literals() == support.ERROR_CODES_SPEC


def test_domain_layer_has_no_sqlalchemy_and_midas_is_absent() -> None:
    """门槛 ⑥（`docs/07` §14.1 / §14.2）：Domain 层无 ORM；`app/` 内 0 处厂商名。"""
    for path in sorted((support.APP_DIR / "domain").glob("*.py")):
        imported = support.imported_modules(path)
        assert not any(name.startswith("sqlalchemy") for name in imported), path.name
        assert "fastapi" not in imported, path.name
        assert not any(name.startswith("mcp") for name in imported), path.name
    for path in support.app_module_paths():
        lowered = path.read_text(encoding="utf-8").lower()
        for vendor in support.VENDOR_NAMES:
            assert vendor.lower() not in lowered, (path.name, vendor)
