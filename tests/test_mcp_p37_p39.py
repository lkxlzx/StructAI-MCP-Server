"""P37–P39 验收 · MCP（MCP Context → Dispatcher → BaseTool → 9 Tools）。

门槛（`docs/08` §4 的本批提示词；`docs/07` §12 P37–P39；`docs/02` §53 / §54 / §57 / §58 /
§69 / §72 / §122）
------------------------------------------------------------------------------
① **MCP Context**：`MCPContext` 承载**服务端**身份（tenant / user / roles / permissions /
   session / `request_id` / `trace_id`）；`context.identity` **不得**由客户端覆盖 ——
   客户端传入的 identity 字段一律**忽略**并给出可审计证据（沿用 P14–P18 的
   `ignored_client_identity_fields()` 口径）；`request_id` / `trace_id` 由 Core 生成并
   **贯穿**整条管线；
② **Dispatcher**：按工具名分发到已注册 Tool；未知工具 → 明确错误（**不**静默回落、
   **不**新增码）；分发路径**不**做业务判断（权限 / Schema / Capability 仍归 26 步管线）；
③ **BaseTool**：统一请求信封 `ToolRequest`（`operation` / `parameters` / `context` /
   `idempotency_key` / `confirmation_token` / `dry_run`）＋统一响应信封（`data` /
   `pagination` / `artifacts` / `error`）；`dry_run=True` → 只走 Dry Run、**不落库不执行**；
   `confirmation_token` 原样透传给 `ExecutionService`（**绝不**进日志 / 审计 / 响应）；
④ **9 Tools**：**恰好 9 个**，逐个可注册 + 可分发 + 端到端跑通（Mock Adapter）；
   每个 Tool 只做「参数 → `ExecutionService`」，**不**承载工程语义、**不**重复管线步骤；
⑤ **顺序**：前 **4** 步（MCP 层）在本批实现，`ExecutionResult.steps` 从第 **5** 步起；
   26 步顺序**不得**改、不得删步；`ExecutionService → Idempotency → Task Create` 不变；
⑥ **回归**：既有 **626** 项 pytest 不得回退；`python -m app.main` 退出码 0 且
   **stdout 0 字节**（未配备 / 已配备两种情形）；建表 **24** 张 + `SELECT 1` → 1；P02 覆盖行为；
⑦ **质量**：`ruff` / `mypy` 全绿；
⑧ **红线**：`grep -ri midas app/` = 0；`app/domain/` 无 SQLAlchemy；Interface 层不依赖
   `app.infrastructure`（SQLAlchemy / Adapter / 仓储一律不可见）；不新增 `STRUCTAI-xxxx` 码；
   **绝不记录 secret**（含 confirmation token）；**不得改表**；`AppContainer` 仍为 **7** 字段。

测试风格（沿用 `tests/test_execution_service_p36.py` / `tests/test_task_engine_p22_p28.py`）：
规范原文副本**写在测试文件里**（不从被测模块导入），每个测试一条长断言并写明门槛，
SQL 级钩子 / AST 红线扫描按需使用。
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
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
from app.application.execution.pipeline import MCP_PIPELINE_STEPS
from app.application.execution.service import ExecutionResult
from app.application.security.context import IdentityContext, SecurityContext
from app.config.settings import Settings
from app.container import (
    BATCH_ID,
    AppContainer,
    ExecutionRuntime,
    bind_mock_instances,
    build_execution_runtime,
)
from app.domain.errors import ProtocolError, StructAIError
from app.infrastructure.database.base import Base
from app.infrastructure.database.seed import seed
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.infrastructure.registry.capability_registry import CapabilityRegistry
from app.infrastructure.registry.operation_registry import OperationRegistry
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
from app.interfaces.mcp.errors import REDACTION_MARKER

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
MCP_DIR = APP_DIR / "interfaces" / "mcp"

ADMIN_PASSWORD_ENV = "STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD"
TEST_PASSWORD = "P37-MCP-验收-口令-9d31"

# ===== 规范原文副本（**不**从被测模块导入）=====

TOOL_NAMES_SPEC: tuple[str, ...] = (
    "engineering_doc",
    "engineering_model_query",
    "engineering_model_assign",
    "engineering_model_delete",
    "engineering_model_build",
    "engineering_view",
    "engineering_result",
    "engineering_design",
    "engineering_analysis",
)
"""`docs/02` §53 / §74 的 **9** 个 Tool（顺序逐条照抄）。"""

TOOL_REQUEST_FIELDS_SPEC: tuple[str, ...] = (
    "operation",
    "parameters",
    "context",
    "idempotency_key",
    "confirmation_token",
    "dry_run",
)
"""`docs/02` §54 / §70 的统一请求信封（**恰好 6** 个字段，逐条照抄）。"""

RESPONSE_KEYS_SPEC: tuple[str, ...] = (
    "success",
    "request_id",
    "trace_id",
    "tool",
    "operation",
    "execution",
    "data",
    "pagination",
    "artifacts",
    "warnings",
    "errors",
    "error",
    "metadata",
)
"""统一响应信封（`docs/02` §71 ∪ `docs/07` §5.3 ∪ 本批提示词 ③；见 `responses.py` 裁决 1）。"""

MCP_STEPS_SPEC: tuple[str, ...] = (
    "MCP Request",
    "Authenticate",
    "Build Server IdentityContext",
    "Build ExecutionContext",
)
"""`docs/07` §9 的**前 4 步**（MCP 层；`docs/02` §122）。"""

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
"""`docs/07` §9 的 **26 步**冻结顺序（逐条抄写）。"""

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
"""`docs/02` §33 的冻结容器形状（**7** 字段；本批**不**扩展）。"""

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
"""`docs/07` §4.3 的 24 张表（本批**不得改表**）。"""

TOOL_OPERATION_COUNTS_SPEC: tuple[tuple[str, int], ...] = (
    ("engineering_doc", 6),
    ("engineering_model_query", 8),
    ("engineering_model_assign", 8),
    ("engineering_model_delete", 7),
    ("engineering_model_build", 14),
    ("engineering_view", 7),
    ("engineering_result", 6),
    ("engineering_design", 6),
    ("engineering_analysis", 7),
)
"""`docs/07` §5.1 的每 Tool Operation 数（6+8+8+7+14+7+6+6+7 = **69**）。"""

TOOL_CALL_MATRIX_SPEC: tuple[tuple[str, str, str], ...] = (
    ("engineering_model_query", "MODEL.NODE.QUERY", "SYNC"),
    ("engineering_model_assign", "MODEL.NODE.CREATE", "SYNC"),
    ("engineering_model_delete", "MODEL.NODE.DELETE", "ASYNC"),
    ("engineering_model_build", "BUILD.COLUMN", "ASYNC"),
    ("engineering_result", "RESULT.NODE.DISPLACEMENT", "SYNC"),
    ("engineering_design", "DESIGN.STEEL", "ASYNC"),
    ("engineering_analysis", "ANALYSIS.STATIC", "ASYNC"),
    ("engineering_doc", "INFO", "SYNC"),
    ("engineering_view", "VIEW.MODEL", "SYNC"),
)
"""每个 Tool 的验收样例：`(tool, operation, 执行模式)`（模式取自落库的 `operations` 表）。

`engineering_doc` / `engineering_view` 的 13 个 Operation **均无** Mock handler，且能力码
不在 `MOCK_CAPABILITIES`（`docs/07` §16 R37：能力 ≠ handler）→ 端到端结论是**明确的**
`STRUCTAI-3000`（见 `test_doc_and_view_tools_reach_the_capability_gate_and_fail_loudly`）。
"""

MOCK_UNSUPPORTED_TOOLS_SPEC: tuple[str, ...] = ("engineering_doc", "engineering_view")
"""Mock Adapter 无 handler 的 Tool（`docs/07` §16 R37 / R2；编排归 P122）。"""

CAPABILITY_REFUSAL_CODE: str = "STRUCTAI-3000"
"""能力不足的码（`docs/07` §11；`UNKNOWN ≠ SUPPORTED`，`docs/02` §47）。"""

CONFIRMATION_REQUIRED_CODE: str = "STRUCTAI-4100"
"""缺确认令牌的码（`docs/07` §8.4 / §11）。"""

UNKNOWN_TOOL_REASON: str = "unknown_tool"
"""未知工具的原因取值（`docs/02` §58）。"""

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
FORBIDDEN_INTERFACE_IMPORTS: tuple[str, ...] = (
    "sqlalchemy",
    "app.infrastructure",
    "app.observability",
)

BUILD_COLUMN_PARAMETERS: Mapping[str, object] = {
    "base_node": {"x": 0.0, "y": 0.0, "z": 0.0},
    "height": 6.0,
    "material": "Q355B",
    "section": "H400x400x13x21",
}

ELEMENT_FORCE_N = 500000.0
COLUMN_HEIGHT_M = 6.0
STEEL_MODULUS = 2.06e11
SECTION_AREA = 0.025
EXPECTED_AXIAL_DISPLACEMENT = ELEMENT_FORCE_N * COLUMN_HEIGHT_M / (STEEL_MODULUS * SECTION_AREA)
"""`docs/02` §42 的 Mock 位移公式 `δ = F L / (E A)`（`docs/07` §16 R32）。"""

STEEL_UTILIZATION = 0.72
"""`docs/02` §47 的 Mock 设计利用率（固定测试值）。"""

DOTTED_OPERATION_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*(\.[A-Z][A-Z0-9_]*)+$")
"""Operation 名的形态（`docs/02` §24；用于「Tool 不持有 Operation 名」的 AST 断言）。"""


# ===== 装配辅助（与 P36 同一手法）=====


def _seeded_settings(tmp_path: Path) -> Settings:
    """构造指向临时库 / 临时产物目录的 `Settings`（**不**碰仓库里的 `data/`）。"""
    return Settings(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'p37_mcp.db').as_posix()}",
        artifact_root=str(tmp_path / "artifacts"),
    )


def create_engine_for(settings: Settings) -> AsyncEngine:
    """按 `Settings` 建引擎（`docs/02` §15；只在测试里显式建表）。"""
    from app.infrastructure.database.session import create_engine

    return create_engine(settings.database_url)


async def _seeded_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ExecutionRuntime, async_sessionmaker[AsyncSession], str, str, str, str, str]:
    """装配「已配备库 + 进程级运行时」，并绑定 Mock 软件实例。

    Returns:
        `(runtime, factory, tenant_id, user_id, project_id, instance_id, model_id)`。
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
    """在项目下建一个绑定 Mock 实例的模型（`docs/07` §16 R25 的租户归属链）。"""
    from app.infrastructure.database.models.model import ModelORM

    async with UnitOfWork.from_session_factory(session_factory) as uow:
        row = ModelORM(
            project_id=project_id,
            software_instance_id=instance_id,
            name="P37 MCP Model",
        )
        uow.session.add(row)
        await uow.session.flush()
        return str(row.id)


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
    """**服务端**身份（`docs/02` §26）：本批由测试扮演认证链（`docs/07` §8.1）。"""
    return IdentityContext(
        user_id=UUID(user_id),
        tenant_id=UUID(tenant_id),
        roles=("system_admin",),
        authentication_method="PASSWORD",
    )


def _client_context(project_id: str, instance_id: str, model_id: str) -> dict[str, object]:
    """客户端**允许**提供的 4 个资源标识（`docs/02` §69；`docs/07` §8.1）。"""
    return {
        "project_id": project_id,
        "software_instance_id": instance_id,
        "model_id": model_id,
    }


def _arguments(
    operation: str,
    *,
    parameters: Mapping[str, object] | None = None,
    context: Mapping[str, object] | None = None,
    idempotency_key: str | None = None,
    confirmation_token: str | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """构造 MCP 调用的 `arguments`（`docs/02` §54 的请求信封）。"""
    payload: dict[str, object] = {
        "operation": operation,
        "parameters": dict(parameters or {}),
        "context": dict(context or {}),
    }
    if idempotency_key is not None:
        payload["idempotency_key"] = idempotency_key
    if confirmation_token is not None:
        payload["confirmation_token"] = confirmation_token
    if dry_run:
        payload["dry_run"] = True
    return payload


def _recorded_statements(engine: AsyncEngine) -> list[str]:
    """录制 SQL 语句（SQL 级钩子；与 P22–P28 / P36 同一手法）。"""
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


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """文档字符串所在 `Constant` 节点的 `id()` 集合（用于排除文档字符串）。"""
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", [])
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstrings.add(id(first.value))
    return docstrings


def _body_statements(node: ast.AST) -> list[ast.stmt]:
    """函数体的语句（**去掉**首行文档字符串；AST 结构断言用）。"""
    body = list(getattr(node, "body", []))
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return body


def _string_literals(path: Path) -> list[str]:
    """模块里**非文档字符串**的字符串字面量（AST 扫描）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = _docstring_nodes(tree)
    literals: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            literals.append(node.value)
    return literals


def _tool_module_paths() -> list[Path]:
    """9 个 Tool 模块的路径（`docs/07` §3.3 的冻结结构）。"""
    return [MCP_DIR / "tools" / f"{name}.py" for name in TOOL_NAMES_SPEC]


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


class _RecordingService:
    """记录 `PipelineRequest` 的假执行服务（只用于「可分发」的单元级断言）。

    ⚠️ 它**只**实现 Tool 依赖的那一条契约（`execute_request`），因此「Tool 只依赖
    `ExecutionService.execute_request`」由类型与运行双重证明。
    """

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


# ===== ① 批次、结构与信封（`docs/02` §54 / §71；`docs/07` §9 / §16 R57）=====


def test_batch_id_is_a_batch_marker() -> None:
    """门槛 ⑦（`docs/08` §3）：容器批次号是一个**批次标记**（与具体批次无关）。

    ⚠️ 断言**不**绑定 P37：后续批次（P40+）会推进 `BATCH_ID`，
    本测试只要求它仍是 `P<两位数字>` 的形态（P05 起的既有口径）。
    """
    assert re.fullmatch(r"P\d{2}", BATCH_ID), BATCH_ID


def test_mcp_layer_implements_exactly_the_first_four_frozen_steps() -> None:
    """门槛 ⑤（`docs/07` §9 / §16 R57）：MCP 层实现的**恰好**是前 4 步。"""
    assert MCP_STEPS == MCP_STEPS_SPEC
    assert MCP_PIPELINE_STEPS == MCP_STEPS_SPEC
    assert MCP_STEPS == EXECUTION_PIPELINE_ORDER[:4]
    assert len(MCP_STEPS) == 4
    assert EXECUTION_PIPELINE_ORDER == PIPELINE_ORDER_SPEC
    assert len(EXECUTION_PIPELINE_ORDER) == 26


def test_container_shape_is_unchanged() -> None:
    """门槛 ⑧（`docs/02` §33）：容器仍是 **7** 字段冻结形状（MCP 层**不**进容器）。"""
    names = tuple(item.name for item in dataclasses.fields(AppContainer))
    assert names == CONTAINER_FIELDS_SPEC, names
    assert [name for name in names if "mcp" in name or "tool" in name] == []


def test_tool_request_envelope_has_the_six_frozen_fields() -> None:
    """门槛 ③（`docs/02` §54 / §70）：统一请求信封**恰好 6** 个字段，token 不进 `repr`。"""
    names = tuple(item.name for item in dataclasses.fields(ToolRequest))
    assert names == TOOL_REQUEST_FIELDS_SPEC, names
    assert TOOL_REQUEST_FIELDS == TOOL_REQUEST_FIELDS_SPEC
    fields = ToolRequest.__dataclass_fields__
    assert fields["confirmation_token"].repr is False, "confirmation token 绝不进 repr"
    request = ToolRequest(operation="MODEL.NODE.QUERY", confirmation_token="tok-1")
    assert "tok-1" not in repr(request)
    assert "tok-1" not in str(request)


def test_response_envelope_has_the_frozen_keys() -> None:
    """门槛 ③（`docs/02` §71 / §90；`docs/07` §5.3）：响应信封的键集合**恰好** 13 个。"""
    response = ToolResponse(
        success=True,
        request_id="req_1",
        trace_id="trace_1",
        tool="engineering_model_query",
        operation="MODEL.NODE.QUERY",
    )
    payload = response.to_dict()
    assert tuple(payload) == RESPONSE_KEYS_SPEC, tuple(payload)
    assert RESPONSE_KEYS == RESPONSE_KEYS_SPEC
    assert payload["errors"] == []
    assert payload["error"] is None
    assert payload["data"] is None
    assert payload["pagination"] is None
    assert payload["artifacts"] == []
    assert payload["warnings"] == []


def test_request_envelope_rejects_malformed_arguments_with_1000() -> None:
    """门槛 ③（`docs/07` §11「请求格式非法」）：信封非法一律 `STRUCTAI-1000`，**不**强转。"""
    cases: tuple[object, ...] = (
        None,
        {},
        {"operation": ""},
        {"operation": 1},
        {"operation": "MODEL.NODE.QUERY", "parameters": []},
        {"operation": "MODEL.NODE.QUERY", "context": "x"},
        {"operation": "MODEL.NODE.QUERY", "idempotency_key": 7},
        {"operation": "MODEL.NODE.QUERY", "confirmation_token": 7},
        {"operation": "MODEL.NODE.QUERY", "dry_run": "true"},
    )
    for arguments in cases:
        with pytest.raises(ProtocolError) as excinfo:
            ToolRequest.from_mapping(arguments)  # type: ignore[arg-type]
        assert excinfo.value.code == "STRUCTAI-1000", arguments
        assert excinfo.value.details["stage"] == "mcp"
    assert unknown_tool_error("nope").code == "STRUCTAI-1000"
    assert unknown_tool_error("nope").details["reason"] == UNKNOWN_TOOL_REASON


def test_request_envelope_ignores_unknown_and_identity_keys() -> None:
    """门槛 ①（`docs/07` §8.1 / §14.3）：顶层身份键**连读都不读**（连 `repr` 都不出现）。"""
    request = ToolRequest.from_mapping(
        {
            "operation": "MODEL.NODE.QUERY",
            "parameters": {"limit": 1},
            "identity": {"user_id": "attacker"},
            "user_id": "attacker",
            "tenant_id": "attacker-tenant",
            "roles": ["system_admin"],
            "permissions": ["SYSTEM_ADMIN"],
            "session_id": "attacker-session",
            "unknown_extra": 1,
        }
    )
    assert request.operation == "MODEL.NODE.QUERY"
    assert request.parameters == {"limit": 1}
    assert request.context == {}
    assert request.idempotency_key is None
    assert request.confirmation_token is None
    assert request.dry_run is False
    assert "attacker" not in repr(request), "未登记的顶层键不得进入信封"
    # 信封结构上**没有**任何身份字段（连字段名都不存在，见 `docs/02` §54 的 6 个字段）。
    assert not any(
        name in TOOL_REQUEST_FIELDS_SPEC
        for name in ("identity", "user_id", "tenant_id", "roles", "permissions", "session_id")
    )


def test_error_envelope_sanitizes_secret_keys_and_keeps_reasons() -> None:
    """门槛 ⑧（`docs/07` §14.3）：错误信封按**键名**脱敏，合法诊断（reason）原样保留。"""
    error = StructAIError(
        "boom",
        details={
            "stage": "x",
            "reason": "missing_token",
            "api_key": "AKIA-secret",
            "nested": {"password": "p", "keep": 1},
            "items": [{"token": "t"}, {"keep": 2}],
        },
    )
    envelope = error_envelope(error)
    assert tuple(envelope) == ("code", "type", "message", "details", "retryable")
    assert envelope["details"]["reason"] == "missing_token"
    assert envelope["details"]["api_key"] == REDACTION_MARKER
    assert envelope["details"]["nested"] == {"password": REDACTION_MARKER, "keep": 1}
    assert envelope["details"]["items"] == [{"token": REDACTION_MARKER}, {"keep": 2}]
    assert "AKIA-secret" not in json.dumps(envelope)
    assert "cause" not in envelope
    assert sanitize_details(None) == {}


# ===== ② 9 个 Tool：声明 / 注册 / 装配（`docs/02` §53 / §74；`docs/07` §5.1）=====


def test_exactly_nine_tools_are_declared_registered_and_built() -> None:
    """门槛 ④（`docs/02` §53 / §74）：**恰好 9 个** Tool，声明 = 注册 = 装配。"""
    assert TOOL_NAMES == TOOL_NAMES_SPEC, TOOL_NAMES
    assert len(TOOL_NAMES) == 9
    assert tuple(TOOL_CLASSES) == TOOL_NAMES_SPEC, tuple(TOOL_CLASSES)
    assert len(set(TOOL_CLASSES.values())) == 9, "9 个 Tool 必须是 9 个不同的类"
    assert all(issubclass(cls, BaseEngineeringTool) for cls in TOOL_CLASSES.values()), TOOL_CLASSES
    service = _RecordingService()
    tools = build_tools(service)  # type: ignore[arg-type]
    assert tuple(tool.name for tool in tools) == TOOL_NAMES_SPEC
    assert all(isinstance(tool, BaseEngineeringTool) for tool in tools)
    assert all(tool.execution is service for tool in tools), "9 个 Tool 共享同一个执行服务"
    dispatcher = ToolDispatcher(tools)
    assert dispatcher.names() == tuple(sorted(TOOL_NAMES_SPEC))
    assert len(dispatcher) == 9
    assert all(name in dispatcher for name in TOOL_NAMES_SPEC)
    server = MCPServer(execution=service)  # type: ignore[arg-type]
    assert server.list_tools() == tuple(sorted(TOOL_NAMES_SPEC))
    assert server.tool_names() == tuple(sorted(TOOL_NAMES_SPEC))
    assert len(server.dispatcher) == 9


def test_each_tool_class_name_matches_its_registry_key() -> None:
    """门槛 ④：工具名 = 注册键 = 类属性（三者不得漂移）。"""
    for name, tool_class in TOOL_CLASSES.items():
        assert tool_class.name == name, (name, tool_class.name)
    assert len({cls.__name__ for cls in TOOL_CLASSES.values()}) == 9


def test_the_nine_tools_partition_the_sixty_nine_operations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ④（`docs/07` §5.1）：9 个 Tool **恰好**划分落库的 **69** 个 Operation。"""

    async def _run() -> None:
        monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
        settings = _seeded_settings(tmp_path)
        engine = create_engine_for(settings)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = create_session_factory(engine)
        await seed(factory)
        registry = await OperationRegistry.load(engine, factory)
        assert registry is not None
        definitions = await registry.list()
        counts: dict[str, int] = {name: 0 for name in TOOL_NAMES_SPEC}
        for definition in definitions:
            assert definition.tool in counts, definition.name
            counts[definition.tool] += 1
        assert len(definitions) == 69
        assert tuple(sorted(counts.items())) == tuple(sorted(TOOL_OPERATION_COUNTS_SPEC)), counts
        # 每个 Tool 的验收样例必须真的属于该 Tool（`docs/02` §82 的 Tool ↔ Operation 一致）。
        for tool, operation, mode in TOOL_CALL_MATRIX_SPEC:
            definition = registry.require(operation)
            assert definition.tool == tool, (tool, operation)
            assert str(definition.execution_mode) == mode, (operation, definition.execution_mode)
        await engine.dispose()

    asyncio.run(_run())


# ===== ③ MCP Context：服务端身份 / request_id / trace_id（`docs/02` §54 / §57 / §69）=====


def test_mcp_context_carries_the_server_identity_and_core_generated_ids() -> None:
    """门槛 ①（`docs/02` §57 / §69）：`MCPContext` 承载服务端身份与 Core 生成的 id。"""
    identity = IdentityContext(
        user_id=UUID(int=11),
        tenant_id=UUID(int=12),
        session_id=UUID(int=13),
        roles=("system_admin",),
        authentication_method="PASSWORD",
    )
    security = SecurityContext(identity=identity, permissions=frozenset({"MODEL_READ"}))
    factory = MCPContextFactory()
    context = factory.from_security_context(security)
    assert isinstance(context, MCPContext)
    assert context.identity is identity
    assert context.execution.identity is identity
    assert context.permissions == frozenset({"MODEL_READ"})
    assert context.roles == ("system_admin",)
    assert context.session_id == str(UUID(int=13))
    assert context.request_id.startswith("req_")
    assert context.trace_id.startswith("trace_")
    # 见 `context.py` 裁决 2：MCP 层的 id 与管线内的 id **逐字节相同**。
    assert context.request_id == context.execution.request_id
    assert context.trace_id == context.execution.trace_id
    assert context.ignored_identity_fields == ()
    # 未提供权限快照 → 空集（`docs/02` §51：**不得提权**）。
    assert factory.create(identity).permissions == frozenset()
    assert factory.executions is not None


def test_mcp_context_ignores_every_client_identity_field() -> None:
    """门槛 ①（`docs/07` §8.1 / §14.3）：客户端 identity 一律忽略，并给出**可审计证据**。"""
    identity = IdentityContext(
        user_id=UUID(int=21),
        tenant_id=UUID(int=22),
        roles=("system_admin",),
    )
    attacker_tenant = str(uuid4())
    client_context = {
        "project_id": str(UUID(int=23)),
        "software_instance_id": str(UUID(int=24)),
        "identity": {"user_id": str(uuid4())},
        "user_id": str(uuid4()),
        "tenant_id": attacker_tenant,
        "roles": ["system_admin", "root"],
        "permissions": ["SYSTEM_ADMIN"],
        "session_id": str(uuid4()),
    }
    context = MCPContextFactory().create(identity, client_context=client_context)
    assert context.identity is identity
    assert context.execution.identity is identity
    assert str(context.execution.identity.tenant_id) == str(UUID(int=22))
    assert str(context.execution.identity.user_id) == str(UUID(int=21))
    assert context.execution.identity.roles == ("system_admin",)
    assert context.ignored_identity_fields == (
        "identity",
        "user_id",
        "tenant_id",
        "roles",
        "permissions",
        "session_id",
    )
    # 白名单字段照常解析（`docs/02` §69）。
    assert str(context.execution.project.project_id) == str(UUID(int=23))
    assert str(context.execution.software.instance_id) == str(UUID(int=24))


def test_client_identity_claim_cannot_reach_another_tenants_audit_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ①（`docs/07` §14.3）：客户端声明的 tenant **不会**被用来执行 / 记账。"""

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
        attacker_tenant = str(uuid4())
        client_context = _client_context(project_id, instance_id, model_id)
        client_context["tenant_id"] = attacker_tenant
        client_context["user_id"] = str(uuid4())
        identity = _identity(tenant_id, user_id)
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            server = build_mcp_server(bundle.service)
            response = await server.handle(
                "engineering_model_query",
                _arguments("MODEL.NODE.QUERY", context=client_context),
                identity=identity,
            )
            payload = response.to_dict()
            assert payload["success"] is True, payload
            assert payload["metadata"]["ignored_identity_fields"] == ["user_id", "tenant_id"]
            # 审计按**服务端**租户分段：真实租户有记录，被冒名的租户**没有**任何记录。
            entries = list(await bundle.audit.store.chain(tenant_id=tenant_id))
            assert [(entry.action, entry.result) for entry in entries] == [
                ("MODEL.NODE.QUERY", "SUCCESS")
            ]
            assert all(str(entry.tenant_id) == tenant_id for entry in entries)
            assert list(await bundle.audit.store.chain(tenant_id=attacker_tenant)) == []

    asyncio.run(_run())


def test_request_id_and_trace_id_span_the_whole_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ①（`docs/02` §5 / §12）：`request_id` / `trace_id` 由 Core 生成并贯穿整条管线。"""

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
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            server = build_mcp_server(bundle.service)
            response = await server.handle(
                "engineering_model_query",
                _arguments(
                    "MODEL.NODE.QUERY",
                    context=_client_context(project_id, instance_id, model_id),
                ),
                identity=identity,
            )
            payload = response.to_dict()
            assert payload["request_id"].startswith("req_")
            assert payload["trace_id"].startswith("trace_")
            spans = list(await runtime.trace.spans_for_trace(payload["trace_id"]))
            assert {span.kind for span in spans} == {"MCP", "TOOL", "OPERATION", "ADAPTER"}, [
                span.kind for span in spans
            ]
            assert all(span.trace_id == payload["trace_id"] for span in spans)
            assert all(span.request_id == payload["request_id"] for span in spans)
            assert all(span.status == "OK" for span in spans)
            assert list(await runtime.trace.spans_for_request(payload["request_id"])) == list(spans)
            # MCP / TOOL Span 的父子关系由 `ExecutionService` 建立（`docs/02` §12）。
            by_kind = {span.kind: span for span in spans}
            assert by_kind["TOOL"].parent_span_id == by_kind["MCP"].id

    asyncio.run(_run())


# ===== ④ Dispatcher：可分发 / 未知工具 / 不做业务判断（`docs/02` §58 / §72）=====


def test_dispatcher_routes_all_nine_tools_and_passes_the_pipeline_request() -> None:
    """门槛 ②④（`docs/02` §58 / §72）：9 个 Tool **逐个可分发**，且只传一条管线请求。"""
    service = _RecordingService()
    dispatcher = ToolDispatcher(build_tools(service))  # type: ignore[arg-type]
    context = MCPContextFactory().create(
        IdentityContext(user_id=UUID(int=1), tenant_id=UUID(int=2))
    )

    async def _run() -> None:
        for tool, operation, _mode in TOOL_CALL_MATRIX_SPEC:
            request = ToolRequest(operation=operation, parameters={"a": 1}, dry_run=True)
            response = await dispatcher.dispatch(tool, request, context)
            assert isinstance(response, ToolResponse)
            assert response.success is True
            assert response.tool == tool
            assert response.operation == operation
            assert tuple(response.to_dict()) == RESPONSE_KEYS_SPEC
        assert len(service.requests) == 9, len(service.requests)
        # Tool 交给管线的**唯一**契约：`PipelineRequest`（tool 取自 Tool 名，不取客户端输入）。
        for (tool, operation, _mode), pipeline_request in zip(
            TOOL_CALL_MATRIX_SPEC, service.requests, strict=True
        ):
            assert pipeline_request.tool == tool, pipeline_request
            assert pipeline_request.operation == operation, pipeline_request
            assert pipeline_request.context is context.execution
            assert pipeline_request.dry_run is True

    asyncio.run(_run())


def test_dispatcher_rejects_unknown_tool_loudly_without_new_codes() -> None:
    """门槛 ②（`docs/02` §58）：未知工具 → `STRUCTAI-1000`，**不**静默回落、**不**新增码。"""
    service = _RecordingService()
    dispatcher = ToolDispatcher(build_tools(service))  # type: ignore[arg-type]
    context = MCPContextFactory().create(
        IdentityContext(user_id=UUID(int=1), tenant_id=UUID(int=2))
    )

    async def _run() -> None:
        with pytest.raises(ProtocolError) as excinfo:
            await dispatcher.dispatch(
                "engineering_nonexistent", ToolRequest(operation="X"), context
            )
        assert excinfo.value.code == "STRUCTAI-1000"
        assert excinfo.value.details["reason"] == UNKNOWN_TOOL_REASON
        assert excinfo.value.details["tool"] == "engineering_nonexistent"
        # 大小写 / 空白 / 近似名都不匹配（**不**做模糊匹配）。
        for name in (
            "Engineering_Model_Query",
            " engineering_model_query",
            "engineering_model",
            "",
        ):
            with pytest.raises(ProtocolError):
                await dispatcher.dispatch(name, ToolRequest(operation="X"), context)
        assert service.requests == [], "未知工具绝不允许触达执行服务"

    asyncio.run(_run())


def test_server_turns_unknown_tool_into_a_failure_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ②（`docs/02` §58 / §71）：未知工具在 MCP 边界翻成统一失败响应，且**零**副作用。"""

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
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            server = build_mcp_server(bundle.service)
            before = await bundle.audit.store.count()
            response = await server.handle(
                "engineering_nonexistent",
                _arguments(
                    "MODEL.NODE.QUERY",
                    context=_client_context(project_id, instance_id, model_id),
                ),
                identity=identity,
            )
            payload = response.to_dict()
            assert payload["success"] is False
            assert payload["errors"][0]["code"] == "STRUCTAI-1000"
            assert payload["errors"][0]["details"]["reason"] == UNKNOWN_TOOL_REASON
            assert payload["error"] == payload["errors"][0]
            assert payload["execution"] == {
                "mode": None,
                "status": "FAILED",
                "task_id": None,
                "steps": [],
                "unprovisioned_schemas": [],
                "replayed": False,
            }, "失败与成功的 `execution` 段**同形**（6 个键）"
            assert payload["metadata"]["mcp_steps"] == list(MCP_STEPS_SPEC)
            assert await bundle.audit.store.count() == before, "分发路径不得产生任何业务副作用"

    asyncio.run(_run())


def test_server_turns_malformed_arguments_into_a_failure_envelope() -> None:
    """门槛 ③（`docs/07` §11）：信封非法也是「一个响应」，且 `request_id` 可定位。"""
    service = _RecordingService()
    server = MCPServer(execution=service)  # type: ignore[arg-type]
    identity = IdentityContext(user_id=UUID(int=1), tenant_id=UUID(int=2))

    async def _run() -> None:
        response = await server.handle("engineering_model_query", None, identity=identity)
        payload = response.to_dict()
        assert payload["success"] is False
        assert payload["errors"][0]["code"] == "STRUCTAI-1000"
        assert payload["operation"] == ""
        assert payload["request_id"].startswith("req_")
        assert payload["trace_id"].startswith("trace_")
        # 见 `responses.py` 裁决 5：请求信封都没构造成功时**不**谎报 4 步全跑。
        assert payload["metadata"]["mcp_steps"] == [MCP_STEPS_SPEC[0]]
        assert service.requests == []

    asyncio.run(_run())


def test_dispatcher_registration_failures_are_structai_7000() -> None:
    """门槛 ②（`docs/07` §14.4 同口径）：装配错误 → `STRUCTAI-7000`，**不**静默覆盖。"""
    service = _RecordingService()
    dispatcher = ToolDispatcher()
    tool = build_tools(service)[0]  # type: ignore[arg-type]
    dispatcher.register(tool)
    with pytest.raises(StructAIError) as excinfo:
        dispatcher.register(tool)
    assert excinfo.value.code == "STRUCTAI-7000"
    assert excinfo.value.details["reason"] == "duplicate_tool"
    with pytest.raises(StructAIError) as excinfo:
        dispatcher.register("not-a-tool")  # type: ignore[arg-type]
    assert excinfo.value.code == "STRUCTAI-7000"
    assert excinfo.value.details["reason"] == "invalid_tool"

    class _UnnamedTool(BaseEngineeringTool):
        async def handle(self, request: ToolRequest, context: MCPContext) -> ToolResponse:
            return ToolResponse(
                success=True,
                request_id="r",
                trace_id="t",
                tool="",
                operation="",
            )

    with pytest.raises(StructAIError) as excinfo:
        dispatcher.register(_UnnamedTool(service))  # type: ignore[arg-type]
    assert excinfo.value.code == "STRUCTAI-7000"
    assert excinfo.value.details["reason"] == "unnamed_tool"
    assert len(dispatcher) == 1


def test_dispatcher_does_no_business_judgement() -> None:
    """门槛 ②（`docs/02` §72 / `docs/07` §9）：分发路径**只**查表 → 抛错 → `handle`。"""
    tree = ast.parse((MCP_DIR / "dispatcher.py").read_text(encoding="utf-8"))
    dispatch = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "dispatch"
    )
    kinds = [type(statement).__name__ for statement in _body_statements(dispatch)]
    assert kinds == ["Assign", "If", "Return"], kinds
    source = ast.unparse(dispatch)
    for forbidden in ("Permission", "permission", "schema", "Schema", "Capabilit", "adapters"):
        assert forbidden not in source, forbidden


# ===== ⑤ 端到端：9 个 Tool 逐个跑通（Mock Adapter；`docs/07` §12.1 / §13.5）=====


def test_the_documented_end_to_end_chain_runs_through_the_mcp_layer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ④（主门槛；`docs/07` §13.5）：五步 E2E 链经 **MCP 层**跑通（Mock Adapter）。

    链：`engineering_model_build` → `engineering_model_assign`（边界 / 荷载）→
    `engineering_analysis` → `engineering_result` → `engineering_design`，外加
    `engineering_model_query`（读回）与 `engineering_model_delete`（删除后读回）。
    数值一律来自 Mock Adapter（`docs/07` §13.5 的「不得硬编码」）。
    """

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
        client_context = _client_context(project_id, instance_id, model_id)
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            server = build_mcp_server(bundle.service)
            resolved = await bundle.resolver.resolve(
                server.contexts.create(identity, client_context=client_context).execution
            )
            assert resolved is not None

            async def call(
                tool: str,
                operation: str,
                parameters: Mapping[str, object] | None = None,
                *,
                confirm: bool = False,
            ) -> dict[str, object]:
                """经 MCP 层调用一次；HIGH 操作按 `docs/07` §8.4 现签确认令牌。"""
                arguments = _arguments(
                    operation,
                    parameters=parameters,
                    context=client_context,
                )
                if confirm:
                    arguments["confirmation_token"] = runtime.confirmation.issue(
                        user_id=user_id,
                        tenant_id=tenant_id,
                        operation=operation,
                        resource_id=resolved.resource_id,
                    ).token
                response = await server.handle(tool, arguments, identity=identity)
                return response.to_dict()

            async def complete(payload: Mapping[str, object]) -> object:
                """把 ASYNC 首次响应里的任务跑完（`docs/02` §88 的同一执行链）。"""
                execution = payload["execution"]
                assert isinstance(execution, Mapping)
                task_id = execution["task_id"]
                assert isinstance(task_id, str), payload
                record = await bundle.engine.run_task(task_id)
                assert str(record.status) == "COMPLETED", record.status
                assert record.result_json is not None
                return json.loads(record.result_json)

            # ---- 第 1 步：BUILD.COLUMN（ASYNC；`docs/07` §13.5 步 1）----
            build = await call(
                "engineering_model_build", "BUILD.COLUMN", BUILD_COLUMN_PARAMETERS, confirm=True
            )
            assert build["success"] is True, build
            assert build["tool"] == "engineering_model_build"
            assert build["execution"]["mode"] == "ASYNC", build["execution"]
            assert build["execution"]["status"] == "QUEUED", build["execution"]
            assert build["data"] is None, "异步首次响应的 data 为 null（docs/02 §71）"
            assert build["errors"] == []
            column = await complete(build)
            assert set(column) == {"node_ids", "element_ids"}, column
            base_id, top_id = column["node_ids"]
            element_id = column["element_ids"][0]

            # ---- 读回：MODEL.NODE.QUERY（SYNC；证明第 18 步真的执行过）----
            nodes = await call("engineering_model_query", "MODEL.NODE.QUERY")
            assert nodes["success"] is True, nodes
            assert nodes["execution"]["mode"] == "SYNC"
            assert nodes["execution"]["status"] == "COMPLETED"
            assert nodes["execution"]["steps"] == list(PIPELINE_ORDER_SPEC[4:]), "steps 从第 5 步起"
            assert nodes["metadata"]["mcp_steps"] == list(PIPELINE_ORDER_SPEC[:4])
            assert nodes["execution"]["unprovisioned_schemas"] == [
                "structai://schema/model/node/query/v1"
            ], "未配备的 Schema 必须**如实**出现（docs/07 §16 R54）"
            by_id = {item["id"]: item for item in nodes["data"]["items"]}
            assert set(by_id) == set(column["node_ids"]), by_id
            assert by_id[top_id]["z"] == COLUMN_HEIGHT_M, by_id[top_id]
            assert nodes["pagination"] == {"has_more": False, "next_cursor": None}

            # ---- 第 2 步：边界 + 荷载（SYNC；`docs/07` §13.5 步 2）----
            boundary = await call(
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
            assert boundary["success"] is True, boundary
            assert boundary["data"]["node_id"] == base_id
            load = await call(
                "engineering_model_assign",
                "MODEL.LOAD.ASSIGN",
                {"node_id": top_id, "fz": -ELEMENT_FORCE_N},
            )
            assert load["success"] is True, load
            assert load["data"] == {
                "node_id": top_id,
                "fx": 0.0,
                "fy": 0.0,
                "fz": -ELEMENT_FORCE_N,
            }, load["data"]

            # ---- 第 3 步：ANALYSIS.STATIC（ASYNC；`docs/07` §13.5 步 3）----
            analysis = await call("engineering_analysis", "ANALYSIS.STATIC", {}, confirm=True)
            assert analysis["success"] is True, analysis
            assert analysis["execution"]["status"] == "QUEUED"
            analysis_result = await complete(analysis)
            assert analysis_result["status"] == "COMPLETED", analysis_result
            assert analysis_result["engineering_grade"] is False, "Mock 不得冒充工程级结果"

            # ---- 第 4 步：RESULT.NODE.DISPLACEMENT（SYNC；`docs/07` §13.5 步 4）----
            displacement = await call(
                "engineering_result", "RESULT.NODE.DISPLACEMENT", {"node_id": top_id}
            )
            assert displacement["success"] is True, displacement
            assert displacement["data"]["node_id"] == top_id
            assert displacement["data"]["uz"] == pytest.approx(
                EXPECTED_AXIAL_DISPLACEMENT, rel=1e-9
            ), displacement["data"]
            force = await call(
                "engineering_result", "RESULT.ELEMENT.FORCE", {"element_id": element_id}
            )
            assert force["success"] is True, force
            assert force["data"]["axial"] == pytest.approx(-ELEMENT_FORCE_N), force["data"]

            # ---- 第 5 步：DESIGN.STEEL（ASYNC；`docs/07` §13.5 步 5）----
            design = await call(
                "engineering_design", "DESIGN.STEEL", {"element_id": element_id}, confirm=True
            )
            assert design["success"] is True, design
            design_result = await complete(design)
            assert design_result == {
                "element_id": element_id,
                "utilization": STEEL_UTILIZATION,
                "status": "PASS",
                "engine": "MockEngineering",
                "engineering_grade": False,
            }, design_result

            # ---- 第 6 步：MODEL.NODE.DELETE（ASYNC；删除后读回证明 Adapter 真的执行）----
            deletion = await call(
                "engineering_model_delete",
                "MODEL.NODE.DELETE",
                {"node_id": base_id},
                confirm=True,
            )
            assert deletion["success"] is True, deletion
            deleted = await complete(deletion)
            assert deleted == {"node_id": base_id, "deleted": True}, deleted
            remaining = await call("engineering_model_query", "MODEL.NODE.QUERY")
            assert [item["id"] for item in remaining["data"]["items"]] == [top_id]
            # 所有 HIGH 操作的确认令牌都被**一次性消费**（`docs/02` §38）。
            assert runtime.confirmation.pending() == 0

    asyncio.run(_run())


def test_doc_and_view_tools_reach_the_capability_gate_and_fail_loudly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ④（`docs/07` §16 R37）：`engineering_doc` / `engineering_view` 的端到端结论。

    ⚠️ 这两个 Tool 的 13 个 Operation **均无** Mock handler，且能力码不在
    `MOCK_CAPABILITIES` —— 故端到端结论是**明确的** `STRUCTAI-3000`（能力 ≠ handler），
    而**不是**静默成功 / 静默回落。审计里必须留下 `DENIED` 记录，证明请求确实走完了
    闸门链直到第 16 步（`Capability Check`）。
    """

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
        client_context = _client_context(project_id, instance_id, model_id)
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            server = build_mcp_server(bundle.service)
            for tool, operation, _mode in TOOL_CALL_MATRIX_SPEC:
                if tool not in MOCK_UNSUPPORTED_TOOLS_SPEC:
                    continue
                response = await server.handle(
                    tool,
                    _arguments(operation, context=client_context),
                    identity=identity,
                )
                payload = response.to_dict()
                assert payload["success"] is False, payload
                assert payload["errors"][0]["code"] == CAPABILITY_REFUSAL_CODE, payload["errors"]
                details = payload["errors"][0]["details"]
                assert details["stage"] == "capability", details
                assert details["statuses"] == ["UNSUPPORTED"], details
                assert details["missing"], details
                assert payload["data"] is None
                assert payload["execution"]["task_id"] is None, "能力不足不得创建任务"
            entries = list(await bundle.audit.store.chain(tenant_id=tenant_id))
            assert [(entry.action, entry.result) for entry in entries] == [
                ("INFO", "DENIED"),
                ("VIEW.MODEL", "DENIED"),
            ], entries
            rendered = runtime.metrics.render()
            assert "structai_requests_total" in rendered, rendered
            assert "structai_audit_total" in rendered, rendered

    asyncio.run(_run())


def test_dry_run_only_goes_through_the_dry_run_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ③（`docs/02` §92）：`dry_run=True` → 只走 Dry Run，**不落库不执行**。"""

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
        client_context = _client_context(project_id, instance_id, model_id)
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            server = build_mcp_server(bundle.service)
            response = await server.handle(
                "engineering_model_assign",
                _arguments(
                    "MODEL.NODE.CREATE",
                    parameters={"node": {"id": 5, "x": 1.0, "y": 2.0, "z": 3.0}},
                    context=client_context,
                    dry_run=True,
                ),
                identity=identity,
            )
            payload = response.to_dict()
            assert payload["success"] is True, payload
            assert payload["execution"]["mode"] == "DRY_RUN", payload["execution"]
            assert payload["execution"]["status"] == "COMPLETED"
            assert payload["execution"]["task_id"] is None, "Dry Run 不得创建任务"
            assert payload["data"] == {"mode": "DRY_RUN", "changes": []}, payload["data"]
            assert payload["warnings"] == []
            steps = payload["execution"]["steps"]
            assert "Adapter" not in steps, steps
            assert steps[-3:] == ["Postconditions", "Release Lock", "MCP Response"], steps
            tasks = (await uow.session.execute(select(TaskORM))).scalars().all()
            assert tasks == [], "Dry Run 不得落库"
            assert await runtime.locks.held_count() == 0, "Dry Run 自己持有的锁必须释放"
            # Dry Run 未执行 Adapter → 模型里**没有**新节点。
            query = await server.handle(
                "engineering_model_query",
                _arguments("MODEL.NODE.QUERY", context=client_context),
                identity=identity,
            )
            assert query.to_dict()["data"]["items"] == []

    asyncio.run(_run())


# ===== ⑥ 确认令牌：原样透传 + 绝不泄漏（`docs/07` §8.4 / §14.3；`docs/02` §54）=====


def test_confirmation_token_is_passed_through_and_never_leaked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ③（`docs/02` §54；`docs/07` §8.4 / §14.3）：token 透传，**绝不**进日志 / 审计 / 响应。

    这里同时覆盖「缺 token → 4100」「固定串 → 4100」「有效 token → 通过第 13 步」与
    「token 不出现在响应 / 审计 / 指标」四条断言。
    """

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
        client_context = _client_context(project_id, instance_id, model_id)
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            server = build_mcp_server(bundle.service)
            resolved = await bundle.resolver.resolve(
                server.contexts.create(identity, client_context=client_context).execution
            )
            assert resolved is not None

            # ① 缺 token 的 HIGH 操作 → `STRUCTAI-4100`，且**零**任务落库。
            refused = await server.handle(
                "engineering_model_build",
                _arguments(
                    "BUILD.COLUMN",
                    parameters=BUILD_COLUMN_PARAMETERS,
                    context=client_context,
                ),
                identity=identity,
            )
            refused_payload = refused.to_dict()
            assert refused_payload["success"] is False
            assert refused_payload["errors"][0]["code"] == CONFIRMATION_REQUIRED_CODE
            assert refused_payload["errors"][0]["details"]["reason"] == "missing_token"
            tasks = (await uow.session.execute(select(TaskORM))).scalars().all()
            assert tasks == [], "确认必须在 Task 创建之前（docs/02 §92）"

            # ② 固定串同样被拒（`docs/07` §8.4：禁止固定字符串作确认）。
            for fixed in ("CONFIRM", "YES", "true", "1"):
                rejected = await server.handle(
                    "engineering_model_build",
                    _arguments(
                        "BUILD.COLUMN",
                        parameters=BUILD_COLUMN_PARAMETERS,
                        context=client_context,
                        confirmation_token=fixed,
                    ),
                    identity=identity,
                )
                rejected_payload = rejected.to_dict()
                assert rejected_payload["errors"][0]["code"] == CONFIRMATION_REQUIRED_CODE
                assert rejected_payload["errors"][0]["details"]["reason"] == "forbidden_token"

            # ③ 服务端签发的 token **原样透传** → 通过第 13 步（Confirmation）。
            token = runtime.confirmation.issue(
                user_id=user_id,
                tenant_id=tenant_id,
                operation="BUILD.COLUMN",
                resource_id=resolved.resource_id,
            ).token
            request = ToolRequest.from_mapping(
                _arguments(
                    "BUILD.COLUMN",
                    parameters=BUILD_COLUMN_PARAMETERS,
                    context=client_context,
                    confirmation_token=token,
                )
            )
            assert request.confirmation_token == token
            assert token not in repr(request)
            accepted = await server.handle(
                "engineering_model_build",
                _arguments(
                    "BUILD.COLUMN",
                    parameters=BUILD_COLUMN_PARAMETERS,
                    context=client_context,
                    confirmation_token=token,
                ),
                identity=identity,
            )
            accepted_payload = accepted.to_dict()
            assert accepted_payload["success"] is True, accepted_payload
            assert accepted_payload["execution"]["status"] == "QUEUED"
            # 一次性消费：同一个 token 不能再用于第二次（`docs/02` §38）。
            assert runtime.confirmation.pending() == 0
            replay = await server.handle(
                "engineering_model_build",
                _arguments(
                    "BUILD.COLUMN",
                    parameters=BUILD_COLUMN_PARAMETERS,
                    context=client_context,
                    confirmation_token=token,
                ),
                identity=identity,
            )
            assert replay.to_dict()["errors"][0]["details"]["reason"] == "invalid_token"

            # ④ token **绝不**出现在响应 / 审计 / 指标里。
            blob = json.dumps(accepted_payload, ensure_ascii=False)
            assert token not in blob
            entries = list(await bundle.audit.store.chain(tenant_id=tenant_id))
            audit_blob = json.dumps(
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
            assert token not in audit_blob
            assert token not in runtime.metrics.render()
            envelope_keys = (
                set(accepted_payload)
                | set(accepted_payload["execution"])
                | set(accepted_payload["metadata"])
            )
            for marker in SECRET_MARKERS:
                assert not any(marker in key.lower() for key in envelope_keys), marker

    asyncio.run(_run())


def test_idempotency_key_is_passed_through_and_replay_semantics_are_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ③（`docs/02` §31 / §33 / §86）：`idempotency_key` 透传；重放口径**如实**断言。

    🔴 **跨批次交互（本批实测结论）**：`docs/02` §33 的幂等摘要载荷是
    `{tool, operation, parameters, context, dry_run}`，而 `context`（`ExecutionContext`）
    **含 Core 生成的 `request_id` / `trace_id`**（§5；`docs/07` §9 第 4 步）。故：

    - 复用**同一个** `MCPContext`（同一 `request_id` / `trace_id`）→ 同键同摘要 → **重放**；
    - 经 `handle()` 重发（每次都生成新的 `request_id` / `trace_id`）→ 同键**不同**摘要 →
      `STRUCTAI-1300`（`request_hash_mismatch`），但**绝不**重复执行。

    两条都断言，结论登记为 `docs/07` §16 **R62**（本批**不**改幂等摘要：P21 已验收、
    `docs/02` §33 逐字；`request_id` / `trace_id` 由 Core 生成亦不可退让）。
    """

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
        client_context = _client_context(project_id, instance_id, model_id)
        arguments = _arguments(
            "MODEL.NODE.QUERY",
            context=client_context,
            idempotency_key=f"p37-{uuid4().hex}",
        )
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            server = build_mcp_server(bundle.service)

            # ① 经 `handle()` 两次：同键但 `request_id` / `trace_id` 不同 → 幂等**冲突**。
            first = (
                await server.handle("engineering_model_query", arguments, identity=identity)
            ).to_dict()
            conflicted = (
                await server.handle("engineering_model_query", arguments, identity=identity)
            ).to_dict()
            assert first["success"] is True, first
            assert first["execution"]["replayed"] is False
            assert conflicted["success"] is False, conflicted
            assert conflicted["errors"][0]["code"] == "STRUCTAI-1300", conflicted["errors"]
            assert conflicted["errors"][0]["details"]["reason"] == "request_hash_mismatch"
            assert conflicted["request_id"] != first["request_id"]
            tasks = (await uow.session.execute(select(TaskORM))).scalars().all()
            assert len(tasks) == 1, "冲突不得重复执行"

            # ② 复用**同一个** `MCPContext` → 同键同摘要 → 重放**直接返回**首次响应。
            replay_context = server.contexts.create(identity, client_context=client_context)
            replay_request = ToolRequest.from_mapping(
                _arguments(
                    "MODEL.NODE.QUERY",
                    context=client_context,
                    idempotency_key=f"p37-{uuid4().hex}",
                )
            )
            original = (
                await server.call_tool("engineering_model_query", replay_request, replay_context)
            ).to_dict()
            replayed = (
                await server.call_tool("engineering_model_query", replay_request, replay_context)
            ).to_dict()
            assert original["success"] is True, original
            assert original["execution"]["replayed"] is False
            assert replayed["success"] is True, replayed
            assert replayed["execution"]["replayed"] is True, "同键同摘要 → 重放（§86）"
            assert replayed["data"] == original["data"]
            assert replayed["execution"]["task_id"] is None, "重放**不**新建任务"
            assert replayed["request_id"] == original["request_id"], "同一上下文 → 同一 request_id"
            after = (await uow.session.execute(select(TaskORM))).scalars().all()
            assert len(after) == 2, "重放不得再建任务"

    asyncio.run(_run())


# ===== ⑦ 9 个 Tool 都是 thin wrapper（`docs/02` §53 / §59；`docs/07` §12 P37–P39）=====


def test_every_tool_module_is_a_thin_wrapper() -> None:
    """门槛 ④（`docs/02` §53 / §59）：每个 Tool 只做「参数 → `ExecutionService`」。"""
    offenders: list[str] = []
    for path in _tool_module_paths():
        assert path.is_file(), path
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = _imported_modules(path)
        allowed = {
            "__future__",
            "app.interfaces.mcp.context",
            "app.interfaces.mcp.responses",
            "app.interfaces.mcp.tools.base",
        }
        extra = sorted(imported - allowed)
        if extra:
            offenders.append(f"{path.name}: imports {extra}")
        classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        assert len(classes) == 1, path.name
        tool_class = classes[0]
        handles = [
            node
            for node in tool_class.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "handle"
        ]
        assert len(handles) == 1, path.name
        body = _body_statements(handles[0])
        assert len(body) == 1, f"{path.name}: handle 必须恰好一条语句"
        statement = body[0]
        assert isinstance(statement, ast.Return), path.name
        assert ast.unparse(statement) == "return await self.invoke(request, context)", path.name
        for literal in _string_literals(path):
            assert not DOTTED_OPERATION_PATTERN.match(literal), f"{path.name}: {literal}"
    assert offenders == [], offenders


def test_base_tool_calls_the_execution_service_exactly_once() -> None:
    """门槛 ④（`docs/02` §53）：`base.py` 只有**一个** `execute_request` 调用点。"""
    path = MCP_DIR / "tools" / "base.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute_request"
    ]
    assert len(calls) == 1, calls
    imported = _imported_modules(path)
    assert not [name for name in imported if name.startswith("app.infrastructure")], imported
    source = path.read_text(encoding="utf-8")
    for forbidden in ("UnitOfWork", "sqlalchemy", "AdapterManager"):
        assert forbidden not in source, forbidden


def test_interface_layer_never_imports_infrastructure_or_sqlalchemy() -> None:
    """门槛 ⑧（`docs/07` §14.1）：Interface 层**不**依赖 Infrastructure / Observability。

    即 `app/interfaces/mcp/**` 看不到 SQLAlchemy / 仓储 / 事务 / Adapter / 观测实现 ——
    只有 Application 契约（`docs/07` §2.2 的依赖方向）。
    """
    offenders: list[str] = []
    for path in sorted(MCP_DIR.rglob("*.py")):
        imported = _imported_modules(path)
        hits = sorted(
            module
            for module in imported
            if any(
                module == forbidden or module.startswith(f"{forbidden}.")
                for forbidden in FORBIDDEN_INTERFACE_IMPORTS
            )
        )
        if hits:
            offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{hits}")
    assert offenders == [], offenders


def test_no_vendor_names_in_the_mcp_layer() -> None:
    """门槛 ⑧（`docs/07` §14.2）：`app/` 内**零**厂商专属内容。"""
    offenders: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        if {"midas", "etabs"} & set(path.parts):  # docs/07 §7.1：厂商专属代码的唯一豁免区
            continue
        lowered = path.read_text(encoding="utf-8").lower()
        for vendor in VENDOR_NAMES:
            if vendor.lower() in lowered:
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{vendor}")
    assert offenders == [], offenders


# ===== ⑧ 回归与红线（`docs/07` §11 / §14；`docs/08` §3）=====


def test_commit_and_rollback_only_in_unit_of_work() -> None:
    """门槛 ⑧（`docs/02` §16）：`commit` / `rollback` 只允许出现在 `unit_of_work.py`。"""
    offenders: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        if path.name == "unit_of_work.py":
            continue
        calls = _commit_or_rollback_calls(path)
        if calls:
            offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{calls}")
    assert offenders == [], offenders
    assert _commit_or_rollback_calls(APP_DIR / "infrastructure" / "database" / "unit_of_work.py")


def test_domain_layer_has_no_sqlalchemy() -> None:
    """门槛 ⑧（`docs/07` §14.1）：`app/domain/` 不引用 SQLAlchemy。"""
    offenders: list[str] = []
    for path in sorted((APP_DIR / "domain").rglob("*.py")):
        if any(name.startswith("sqlalchemy") for name in _imported_modules(path)):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == [], offenders


def test_twenty_codes_and_twenty_four_tables_are_not_regressed(engine: AsyncEngine) -> None:
    """门槛 ⑥⑧（`docs/07` §11 / §4.3）：20 码不扩；建表仍是 **24** 张（**未改表**）。"""

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
    """门槛 ⑥（`docs/08` §3）：`python -m app.main` 退出码 0 且 **stdout 0 字节**（两种情形）。"""
    unprovisioned = _run_main(f"sqlite+aiosqlite:///{(tmp_path / 'p37_empty.db').as_posix()}")
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


def test_explicit_correlation_ids_must_match_the_layer_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ①（`docs/02` §5；`server.py` 裁决 6）：显式 `request_id` / `trace_id` 只接受本层形态。

    这样 P40 / P41 的传输层**不能**把客户端给的关联 id（如 JSON-RPC `id`）原样塞进
    审计 / Trace 的关联字段 —— 关联 id 由 Core 生成是 `docs/02` §5 的硬要求。
    """

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
        client_context = _client_context(project_id, instance_id, model_id)
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            server = build_mcp_server(bundle.service)
            arguments = _arguments("MODEL.NODE.QUERY", context=client_context)

            for forged in ("client-supplied", "req_1", "trace_x", ""):
                response = await server.handle(
                    "engineering_model_query",
                    arguments,
                    identity=identity,
                    request_id=forged,
                )
                payload = response.to_dict()
                assert payload["success"] is False, forged
                assert payload["errors"][0]["code"] == "STRUCTAI-1000", payload["errors"]
                assert payload["errors"][0]["details"]["reason"] == "invalid_request_id"
                # 失败响应也必须带**服务端生成**的关联 id（可定位，且不回显伪造值）。
                assert payload["request_id"] != forged
                assert re.fullmatch(r"req_[0-9a-f]{32}", payload["request_id"])

            response = await server.handle(
                "engineering_model_query",
                arguments,
                identity=identity,
                trace_id="client-supplied",
            )
            assert response.to_dict()["errors"][0]["details"]["reason"] == "invalid_trace_id"

            accepted_id = f"req_{uuid4().hex}"
            accepted_trace = f"trace_{uuid4().hex}"
            accepted = await server.handle(
                "engineering_model_query",
                arguments,
                identity=identity,
                request_id=accepted_id,
                trace_id=accepted_trace,
            )
            accepted_payload = accepted.to_dict()
            assert accepted_payload["success"] is True, accepted_payload
            assert accepted_payload["request_id"] == accepted_id
            assert accepted_payload["trace_id"] == accepted_trace
            spans = list(await runtime.trace.spans_for_trace(accepted_trace))
            assert spans and all(span.request_id == accepted_id for span in spans)

    asyncio.run(_run())


def test_pipeline_request_never_exposes_the_confirmation_token_in_repr() -> None:
    """门槛 ③（`docs/07` §14.3）：**服务端**管线请求的 `repr` 也不得带出 confirmation token。"""
    from app.application.execution.pipeline import PipelineRequest
    from app.interfaces.mcp.tools.base import BaseEngineeringTool

    token = "p37-confirmation-token-绝密"
    identity = IdentityContext(user_id=UUID(int=31), tenant_id=UUID(int=32))
    context = MCPContextFactory().create(identity)
    tool = build_tools(_RecordingService())[0]  # type: ignore[arg-type]
    assert isinstance(tool, BaseEngineeringTool)
    request = ToolRequest(
        operation="MODEL.NODE.QUERY",
        confirmation_token=token,
        idempotency_key="key-1",
    )
    pipeline_request = tool.pipeline_request(request, context)
    assert isinstance(pipeline_request, PipelineRequest)
    assert pipeline_request.confirmation_token == token, "**原样**透传（docs/02 §54）"
    assert token not in repr(pipeline_request)
    assert token not in str(pipeline_request)
    assert token not in repr(request)
    assert PipelineRequest.__dataclass_fields__["confirmation_token"].repr is False
    assert ToolRequest.__dataclass_fields__["confirmation_token"].repr is False
