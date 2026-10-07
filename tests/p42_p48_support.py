"""P42–P48 七类测试的**共享装配辅助**（`docs/07` §12 P42–P48；`docs/02` §67–§75）。

⚠️ 本模块**只**提供装配 / 扫描 / 规范原文副本，**不**承载任何断言，也**不**持有
可变状态：每个测试自己用 `tmp_path` 建**独立临时库**，测试之间不共享会话、
不依赖执行顺序（`docs/08` §4 的本批门槛 ②）。

装配手法照抄 `tests/test_transport_p40_p41.py` / `tests/test_mcp_p37_p39.py`
（前两批已验收的写法），规范原文副本一律**写在测试侧**、不从被测模块导入。
"""

from __future__ import annotations

import ast
import os
import socket
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import anyio
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.execution.identity import MCPIdentity
from app.application.security.context import (
    AUTHENTICATION_METHOD_LOCAL,
    IdentityContext,
)
from app.config.settings import Settings
from app.container import (
    ExecutionRuntime,
    bind_mock_instances,
    build_execution_runtime,
)
from app.infrastructure.database.base import Base
from app.infrastructure.database.seed import seed
from app.infrastructure.database.session import (
    create_engine,
    create_session_factory,
)
from app.infrastructure.registry.capability_registry import CapabilityRegistry
from app.infrastructure.registry.operation_registry import OperationRegistry

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
TESTS_DIR = REPO_ROOT / "tests"

ADMIN_PASSWORD_ENV = "STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD"
TEST_PASSWORD = "P42-测试-验收-口令-5e11"
ADMIN_USERNAME = "admin"

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
"""每个 Tool 的验收样例：`(tool, operation, 执行模式)`（模式取自落库 `operations` 表）。"""

TOOL_REQUEST_FIELDS_SPEC: tuple[str, ...] = (
    "operation",
    "parameters",
    "context",
    "idempotency_key",
    "confirmation_token",
    "dry_run",
)
"""`docs/02` §54 / §70 的统一请求信封（**恰好 6** 个字段）。"""

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
"""`docs/02` §71 ∪ `docs/07` §5.3 的统一响应信封（**13** 键）。"""

ERROR_ENVELOPE_KEYS_SPEC: tuple[str, ...] = (
    "code",
    "type",
    "message",
    "details",
    "retryable",
)
"""`docs/07` §11 / `docs/03` §75 的错误信封（**5** 键）。"""

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

RETRYABLE_CODES_SPEC: frozenset[str] = frozenset(
    {"STRUCTAI-2000", "STRUCTAI-2300", "STRUCTAI-5000"}
)
"""`docs/07` §11 里 `retryable=True` 的三个码（逐条抄写）。"""

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

TASK_STATUSES_SPEC: tuple[str, ...] = (
    "CREATED",
    "VALIDATING",
    "QUEUED",
    "RUNNING",
    "PROCESSING",
    "COMPLETED",
    "FAILED",
    "CANCEL_REQUESTED",
    "CANCELLED",
    "TIMEOUT",
    "RETRYING",
    "RECOVERING",
)
"""`docs/07` §10.1 的 **12** 态（逐条照抄）。"""

RECOVERY_ENTRY_STATUSES_SPEC: tuple[str, ...] = ("QUEUED", "RUNNING", "PROCESSING", "RECOVERING")
"""`docs/02` §42 / §81 的四条恢复入口状态（逐条照抄）。"""

RECOVERY_POLICIES_SPEC: tuple[str, ...] = (
    "SAFE_RETRY",
    "STATE_RECONCILE",
    "MANUAL_REVIEW",
    "FAIL",
)
"""`docs/02` §45 的四个恢复策略取值（逐条照抄）。"""

RECOVERY_ACTIONS_SPEC: tuple[str, ...] = ("REQUEUE", "RESUME", "FAIL")
"""`docs/07` §10.2 的三个恢复动作取值（逐条照抄）。"""

SECURITY_CHAIN_SPEC: tuple[str, ...] = (
    "Authentication",
    "Session",
    "RBAC",
    "Effective Permission",
)
"""`docs/07` §8.1 / `docs/02` §41 的安全链顺序（逐条照抄）。"""

FORBIDDEN_CONFIRMATION_TOKENS: tuple[str, ...] = (
    "CONFIRM",
    "confirm",
    "YES",
    "yes",
    "true",
    "True",
    "1",
    "OK",
    "Y",
)
"""`docs/02` §38 / `docs/07` §14.3：固定串**不得**用作 confirmation token。"""

MOCK_UNSUPPORTED_TOOLS_SPEC: tuple[str, ...] = ("engineering_doc", "engineering_view")
"""Mock Adapter 无 handler 的 Tool（`docs/07` §16 R37 / R63）。"""

VENDOR_NAMES: tuple[str, ...] = ("MIDAS", "CSI", "ANSYS", "SAP2000", "ETABS", "OpenSees")
SECRET_MARKERS: tuple[str, ...] = (
    "password",
    "passwd",
    "api_key",
    "apikey",
    "api-key",
    "private_key",
    "private-key",
    "secret",
    "credential",
    "authorization",
)

CAPABILITY_REFUSAL_CODE = "STRUCTAI-3000"
CONFIRMATION_REQUIRED_CODE = "STRUCTAI-4100"
TENANT_DENIED_CODE = "STRUCTAI-4200"
PROTOCOL_ERROR_CODE = "STRUCTAI-1000"
CONFLICT_CODE = "STRUCTAI-1300"
TASK_RECOVERY_CODE = "STRUCTAI-5300"
LOCK_CONFLICT_CODE = "STRUCTAI-6100"

UNKNOWN_TOOL_REASON = "unknown_tool"
INVALID_CREDENTIALS_REASON = "invalid_credentials"
MISSING_TOKEN_REASON = "missing_token"

BUILD_COLUMN_PARAMETERS: Mapping[str, object] = {
    "base_node": {"x": 0.0, "y": 0.0, "z": 0.0},
    "height": 6.0,
    "material": "Q355B",
    "section": "H400x400x13x21",
}
"""`docs/03` §68 的 Generic Client Build 参数（逐字照抄）。"""

ELEMENT_FORCE_N = 500_000.0
COLUMN_HEIGHT_M = 6.0
STEEL_MODULUS = 2.06e11
SECTION_AREA = 0.025
EXPECTED_AXIAL_DISPLACEMENT = ELEMENT_FORCE_N * COLUMN_HEIGHT_M / (STEEL_MODULUS * SECTION_AREA)
"""`docs/02` §42 的 Mock 位移公式 `δ = F L / (E A)`（`docs/07` §16 R32）。"""

STEEL_UTILIZATION = 0.72
"""`docs/02` §47 的 Mock 设计利用率（固定测试值）。"""

# ===== 装配辅助 =====


def seeded_settings(tmp_path: Path, *, name: str = "p42.db") -> Settings:
    """构造指向**临时**库 / 临时产物目录的 `Settings`（**不**碰仓库里的 `data/`）。"""
    return Settings(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / name).as_posix()}",
        artifact_root=str(tmp_path / "artifacts"),
    )


def engine_for(settings: Settings) -> AsyncEngine:
    """按 `Settings` 建引擎（`docs/02` §15；建表只在测试里显式做）。"""
    return create_engine(settings.database_url)


async def create_tables(engine: AsyncEngine) -> None:
    """`docs/02` §102 的 `--create-tables` 等价物（被测服务器本身**不**建表）。"""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def seeded_ids(session: AsyncSession) -> tuple[str, str, str]:
    """取 seed 落库的租户 / 管理员 / 项目标识（`docs/02` §44）。"""
    from app.infrastructure.database.models.project import ProjectORM
    from app.infrastructure.database.models.tenant import TenantORM
    from app.infrastructure.database.models.user import UserORM

    tenant = (await session.execute(select(TenantORM))).scalars().first()
    user = (await session.execute(select(UserORM))).scalars().first()
    project = (await session.execute(select(ProjectORM))).scalars().first()
    return str(tenant.id), str(user.id), str(project.id)


async def mock_instance_id(session: AsyncSession) -> str:
    """取 seed 落库的 Mock 软件实例标识（`docs/02` §54 的启动序列）。"""
    from app.infrastructure.database.models.software import (
        SoftwareInstanceORM,
        SoftwareORM,
        SoftwareProductORM,
        SoftwareVersionORM,
    )

    statement = (
        select(SoftwareInstanceORM.id)
        .join(SoftwareVersionORM, SoftwareVersionORM.id == SoftwareInstanceORM.version_id)
        .join(SoftwareProductORM, SoftwareProductORM.id == SoftwareVersionORM.product_id)
        .join(SoftwareORM, SoftwareORM.id == SoftwareProductORM.software_id)
    )
    return str((await session.execute(statement)).scalars().first())


async def link_instance_to_project(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    project_id: str,
    instance_id: str,
    name: str = "P42 Model",
) -> str:
    """在项目下建一个绑定 Mock 实例的模型（`docs/07` §16 R25 的租户归属链）。"""
    from app.infrastructure.database.models.model import ModelORM
    from app.infrastructure.database.unit_of_work import UnitOfWork

    async with UnitOfWork.from_session_factory(session_factory) as uow:
        row = ModelORM(
            project_id=project_id,
            software_instance_id=instance_id,
            name=name,
        )
        uow.session.add(row)
        await uow.session.flush()
        return str(row.id)


async def prepare_database(
    tmp_path: Path,
    monkeypatch: Any,
    *,
    name: str = "p42.db",
) -> Settings:
    """建表 + Seed + 建模型，返回指向该库的 `Settings`（**只**用于验收准备）。"""
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    settings = seeded_settings(tmp_path, name=name)
    engine = engine_for(settings)
    await create_tables(engine)
    factory = create_session_factory(engine)
    await seed(factory)
    async with factory() as session:
        _, _, project_id = await seeded_ids(session)
        instance_id = await mock_instance_id(session)
    await link_instance_to_project(
        factory,
        project_id=project_id,
        instance_id=instance_id,
    )
    await engine.dispose()
    return settings


async def database_ids(settings: Settings) -> dict[str, str]:
    """从已配备库读回验收需要的资源标识（`docs/02` §69 的白名单字段）。"""
    from app.infrastructure.database.models.model import ModelORM

    engine = engine_for(settings)
    factory = create_session_factory(engine)
    async with factory() as session:
        tenant_id, user_id, project_id = await seeded_ids(session)
        instance_id = await mock_instance_id(session)
        model = (await session.execute(select(ModelORM))).scalars().first()
        model_id = str(model.id)
    await engine.dispose()
    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "project_id": project_id,
        "instance_id": instance_id,
        "model_id": model_id,
    }


async def seeded_runtime(
    tmp_path: Path,
    monkeypatch: Any,
    *,
    name: str = "p42.db",
) -> tuple[ExecutionRuntime, async_sessionmaker[AsyncSession], dict[str, str]]:
    """装配「已配备库 + 进程级运行时」，并绑定 Mock 软件实例。

    Returns:
        `(runtime, factory, ids)`；`ids` 含 `tenant_id` / `user_id` /
        `project_id` / `instance_id` / `model_id`（均为字符串）。
    """
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    settings = seeded_settings(tmp_path, name=name)
    engine = engine_for(settings)
    await create_tables(engine)
    factory = create_session_factory(engine)
    await seed(factory)
    runtime = build_execution_runtime(
        settings,
        operation_registry=await OperationRegistry.load(engine, factory),
        capability_registry=await CapabilityRegistry.load(engine, factory),
    )
    runtime.session_factory = factory
    bound = await bind_mock_instances(runtime, factory)
    assert len(bound) == 1, bound
    async with factory() as session:
        tenant_id, user_id, project_id = await seeded_ids(session)
    model_id = await link_instance_to_project(
        factory,
        project_id=project_id,
        instance_id=bound[0],
    )
    await engine.dispose()
    ids = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "project_id": project_id,
        "instance_id": bound[0],
        "model_id": model_id,
    }
    return runtime, factory, ids


def client_context(ids: Mapping[str, str]) -> dict[str, object]:
    """客户端**允许**提供的资源标识（`docs/02` §69；`docs/07` §8.1）。"""
    return {
        "project_id": ids["project_id"],
        "software_instance_id": ids["instance_id"],
        "model_id": ids["model_id"],
    }


def identity_context(ids: Mapping[str, str], *, roles: tuple[str, ...] = ("system_admin",)) -> Any:
    """**服务端**身份（`docs/02` §26；客户端不可声明）。"""
    from uuid import UUID

    return IdentityContext(
        user_id=UUID(ids["user_id"]),
        tenant_id=UUID(ids["tenant_id"]),
        roles=roles,
        authentication_method="PASSWORD",
    )


def local_identity(ids: Mapping[str, str]) -> MCPIdentity:
    """STDIO 的**本地可信身份**（`docs/03` §11；`authentication_method = LOCAL`）。"""
    from uuid import UUID

    return MCPIdentity(
        identity=IdentityContext(
            user_id=UUID(ids["user_id"]),
            tenant_id=UUID(ids["tenant_id"]),
            roles=("system_admin",),
            authentication_method=AUTHENTICATION_METHOD_LOCAL,
        ),
        permissions=frozenset({"MODEL_READ", "MODEL_WRITE"}),
    )


def arguments(
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


def run_main(
    *args: str,
    database_url: str | None = None,
    env: Mapping[str, str] | None = None,
    stdin_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """以子进程跑 `python -m app.main`（门槛：退出码 0 + stdout **0 字节**）。"""
    environment = dict(os.environ)
    if database_url is not None:
        environment["DATABASE_URL"] = database_url
    if env:
        environment.update(env)
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "app.main", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        input=stdin_text,
        check=False,
        timeout=300,
    )


def free_port() -> int:
    """取一个空闲端口（HTTP E2E 用）。"""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def wait_for_port(port: int, *, budget_seconds: float = 30.0) -> None:
    """等待 HTTP 服务器就绪（连得上即返回）。

    ⚠️ 参数名**不**叫 `timeout`：`ruff` 的 `ASYNC109` 要求异步函数改用
    `anyio.fail_after`；这里刻意保留「轮询 + 预算」的写法，因为等的是**外部**
    进程开始监听，需要一个明确的装配错误信息。
    """
    deadline = anyio.current_time() + budget_seconds
    while anyio.current_time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            await anyio.sleep(0.05)
    raise AssertionError(f"HTTP transport did not start listening on port {port}")


# ===== SQL / AST 级扫描 =====


def record_statements(engine: AsyncEngine) -> list[str]:
    """录制 SQL 语句（SQL 级钩子；与 P22–P28 / P36–P41 同一手法）。"""
    captured: list[str] = []

    def _capture(conn: object, cursor: object, statement: str, *rest: object) -> None:
        captured.append(statement)

    sa.event.listen(engine.sync_engine, "before_cursor_execute", _capture)
    return captured


async def all_text_values(engine: AsyncEngine) -> list[str]:
    """全库**文本列**的取值（只用于「绝不记录 secret」的可执行断言）。"""
    values: list[str] = []
    async with engine.connect() as connection:
        tables = await connection.run_sync(_inspected_tables)
        for table in tables:
            result = await connection.execute(sa.text(f'SELECT * FROM "{table}"'))
            for row in result.mappings():
                values.extend(value for value in row.values() if isinstance(value, str))
    return values


def app_module_paths() -> list[Path]:
    """`app/` 下的全部模块文件（红线扫描用）。"""
    return sorted(path for path in APP_DIR.rglob("*.py") if "__pycache__" not in path.parts)


def imported_modules(path: Path) -> set[str]:
    """模块级 import 的模块名集合（AST 红线扫描）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def docstring_nodes(tree: ast.AST) -> set[int]:
    """文档字符串所在 `Constant` 节点的 `id()` 集合（扫描时排除）。"""
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


def string_literals(path: Path) -> list[str]:
    """模块里**非文档字符串**的字符串字面量（AST 扫描）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = docstring_nodes(tree)
    literals: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            literals.append(node.value)
    return literals


def commit_or_rollback_calls(path: Path) -> list[str]:
    """`.commit()` / `.rollback()` 的调用点（AST 红线扫描）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"commit", "rollback"}:
                found.append(node.func.attr)
    return found


def structai_code_literals(paths: list[Path] | None = None) -> set[str]:
    """`app/` 内出现的 `STRUCTAI-xxxx` 字面量集合（**不**新增码的可执行判定）。"""
    codes: set[str] = set()
    for path in paths if paths is not None else app_module_paths():
        for literal in string_literals(path):
            if literal.startswith("STRUCTAI-") and len(literal) == len("STRUCTAI-1000"):
                codes.add(literal)
    return codes


TOOL_INPUT_SCHEMA_KEYS_SPEC: tuple[str, ...] = (
    "operation",
    "parameters",
    "context",
    "idempotency_key",
    "confirmation_token",
    "dry_run",
    "batch",
)
"""`docs/02` §84 ∪ `docs/03` §27 的 MCP Tool 顶层信封键（逐条照抄）。"""

LIMIT_FIELDS_SPEC: tuple[str, ...] = (
    "max_message_bytes",
    "max_request_bytes",
    "max_tool_arguments_bytes",
    "max_concurrent_sessions",
    "max_requests_per_session",
    "max_inflight_requests",
)
"""`docs/03` §20 的 `MCPRuntimeLimits` 前六字段（逐条照抄）。"""

MCP_STEPS_SPEC: tuple[str, ...] = PIPELINE_ORDER_SPEC[:4]
"""`docs/07` §9 的**前 4 步**（MCP 层；`docs/02` §122）。"""

PIPELINE_EXECUTION_STEPS_SPEC: tuple[str, ...] = (
    "Adapter",
    "Result Normalization",
    "Postconditions",
    "Release Lock",
    "Persist Result",
    "Audit",
    "Trace",
    "Event",
)
"""`docs/07` §9 的第 18–25 步（执行链 8 步；`docs/07` §16 R57）。"""


async def table_names(engine: AsyncEngine) -> tuple[str, ...]:
    """已建表名（`docs/07` §4.3 的 24 张；用于「不得改表」的可执行判定）。"""
    return await _inspected_tables_for(engine)


async def select_one(engine: AsyncEngine) -> int:
    """`SELECT 1` → 1（`docs/07` §12 P04 的连接门槛）。"""
    async with engine.connect() as connection:
        return int((await connection.execute(sa.text("SELECT 1"))).scalar())


def _inspected_tables(connection: Any) -> list[str]:
    """同步上下文里的表名读取（`run_sync` 用；`docs/07` §4.3）。"""
    return list(sa.inspect(connection).get_table_names())


async def _inspected_tables_for(engine: AsyncEngine) -> tuple[str, ...]:
    """异步读取已建表名（供「不得改表」的可执行判定）。"""
    async with engine.connect() as connection:
        names = await connection.run_sync(_inspected_tables)
    return tuple(sorted(names))


async def seeded_database(
    tmp_path: Path,
    monkeypatch: Any,
    *,
    name: str = "p42.db",
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """建表 + Seed（**不**绑定 Mock 实例），返回 `(engine, factory)`。"""
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    settings = seeded_settings(tmp_path, name=name)
    engine = engine_for(settings)
    await create_tables(engine)
    factory = create_session_factory(engine)
    await seed(factory)
    return engine, factory


async def row_count(engine: AsyncEngine, table: str) -> int:
    """某表的行数（`docs/07` §4.3；只用于端到端的落库证据）。"""
    async with engine.connect() as connection:
        result = await connection.execute(sa.text(f'SELECT COUNT(*) FROM "{table}"'))
    return int(result.scalar())
