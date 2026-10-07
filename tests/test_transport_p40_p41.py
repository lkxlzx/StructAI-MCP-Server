"""P40–P41 验收 · MCP Transport（STDIO → Streamable HTTP）。

门槛（`docs/08` §4 的本批提示词；`docs/07` §12 P40 / P41；`docs/02` §123 / §124；
`docs/03` §60–§62 与「⑯ Core Alpha — MCP Transport / Session / STDIO /
Streamable HTTP」块）
------------------------------------------------------------------------------
① **STDIO E2E**（`docs/03` §40–§43 / §10–§11 / §25–§34）：Generic MCP Client 能
   `connect` → `list_tools`（**恰好 9** 个，名字与 `TOOL_NAMES` 逐条一致）→
   `call_tool`（端到端返回 `docs/02` §71 的统一信封）；stdout **只**放协议帧
   （日志一律 stderr；`python -m app.main` 未接客户端时 stdout 仍 **0 字节**）。
② **Streamable HTTP**（`docs/03` §44–§59 / §45–§53）：同一 Tool Runtime 经 HTTP
   可达且**不**复制业务逻辑（AST 红线：传输层不出现 Operation 名、不 import 仓储 /
   UnitOfWork、不判断权限 / Schema / Capability）；HTTP **必须鉴权**，身份仍由
   **服务端**构造；Session 与 `session_id` 绑定不得跨客户端串号；Origin / Host、
   CORS、Body Limit、Rate Limit、Timeout、Connection Limits、Cleanup 按章节逐条落地。
③ 传输层**不得**成为第二套业务面：只做「协议 ↔ `MCPServer.handle`」的转换；
   未知工具 / 信封非法仍由 MCP 层翻成统一信封（**不**新增 `STRUCTAI-xxxx` 码）。
④ 顺序与语义不变（`docs/07` §9）：26 步**不得**改、不得删步。
⑤ 回归：既有 **662** 项 pytest 不得回退；`python -m app.main` 退出码 0 且
   **stdout 0 字节**；P04 建表 **24** 张 / `SELECT 1` → 1。
⑥ 质量：`ruff` / `mypy` 全绿。
⑦ 红线：`grep -ri midas app/` = 0；`app/domain/` 无 SQLAlchemy；不新增
   `STRUCTAI-xxxx` 码；**绝不记录 secret**；**不得改表**；`AppContainer` 仍为
   **7** 字段冻结形状。

测试风格（沿用 `tests/test_mcp_p37_p39.py`）：规范原文副本**写在测试文件里**
（不从被测模块导入），每个测试一条长断言并写明门槛，AST 红线扫描按需使用。
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import re
import socket
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import UUID

import anyio
import httpx
import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.execution.identity import MCPIdentity
from app.application.security.context import (
    AUTHENTICATION_METHOD_LOCAL,
    IdentityContext,
)
from app.config.settings import Settings
from app.container import (
    BATCH_ID,
    ExecutionRuntime,
    bind_mock_instances,
    build_execution_runtime,
)
from app.infrastructure.database.base import Base
from app.infrastructure.database.seed import seed
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.registry.capability_registry import CapabilityRegistry
from app.infrastructure.registry.operation_registry import OperationRegistry
from app.interfaces.mcp.transport import (
    MCPRuntimeLimits,
    MCPTransport,
)
from app.interfaces.mcp.transport.http import (
    DEFAULT_HTTP_PATH,
    MCP_SESSION_ID_HEADER,
    build_transport_security,
)
from app.interfaces.mcp.transport.http_session import (
    RATE_WINDOW_SECONDS,
    SESSION_METRIC_NAMES,
    BodyReader,
    InflightCounter,
    RateLimiter,
    SessionTable,
    client_key,
    header_bytes,
    header_map,
    response_header_value,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
TRANSPORT_DIR = APP_DIR / "interfaces" / "mcp" / "transport"

ADMIN_PASSWORD_ENV = "STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD"
TEST_PASSWORD = "P40-传输-验收-口令-7c42"

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

TRANSPORT_METHODS_SPEC: tuple[str, ...] = ("start", "receive", "send", "close")
"""`docs/03` §3 的 `MCPTransport` 四方法（逐条照抄）。"""

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

SERVER_INSTRUCTIONS_SPEC: str = (
    "StructAI MCP Server exposes software-neutral engineering tools. "
    "Use operation names to select engineering actions. "
    "Do not assume vendor-specific APIs. "
    "Long-running operations return task_id."
)
"""`docs/03` §64 的 `instructions`（逐字照抄）。"""

SESSION_METRIC_NAMES_SPEC: tuple[str, ...] = (
    "structai_mcp_sessions_created_total",
    "structai_mcp_sessions_closed_total",
    "structai_mcp_sessions_active",
    "structai_mcp_auth_failures_total",
    "structai_mcp_requests_total",
    "structai_mcp_request_errors_total",
)
"""`docs/03` §59 的六个指标名（逐条照抄）。"""

ALLOWED_HOSTS_SPEC: tuple[str, ...] = ("localhost", "127.0.0.1")
"""`docs/03` §50 的允许列表（逐条照抄：`localhost` / `127.0.0.1` / configured host）。"""

LIMIT_FIELDS_SPEC: tuple[str, ...] = (
    "max_message_bytes",
    "max_request_bytes",
    "max_tool_arguments_bytes",
    "max_concurrent_sessions",
    "max_requests_per_session",
    "max_inflight_requests",
)
"""`docs/03` §20 的 `MCPRuntimeLimits` 前六字段（逐条照抄）。"""

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

DOTTED_OPERATION_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*(\.[A-Z][A-Z0-9_]*)+$")
"""Operation 名的形态（`docs/02` §24；用于「传输层不持有 Operation 名」的 AST 断言）。"""

VENDOR_NAMES: tuple[str, ...] = ("MIDAS", "CSI", "ANSYS", "SAP2000", "ETABS", "OpenSees")
FORBIDDEN_TRANSPORT_IMPORTS: tuple[str, ...] = (
    "sqlalchemy",
    "app.infrastructure",
    "app.observability",
)
SECRET_MARKERS: tuple[str, ...] = (
    "password",
    "api_key",
    "api-key",
    "private_key",
    "secret",
    "credential",
)

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

# ===== 装配辅助（与 P36 / P37–P39 同一手法）=====


def _seeded_settings(tmp_path: Path) -> Settings:
    """构造指向临时库 / 临时产物目录的 `Settings`（**不**碰仓库里的 `data/`）。"""
    return Settings(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'p40_transport.db').as_posix()}",
        artifact_root=str(tmp_path / "artifacts"),
    )


def _create_engine(settings: Settings) -> AsyncEngine:
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


async def _mock_instance_id(session: AsyncSession) -> str:
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


async def _link_instance_to_project(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    project_id: str,
    instance_id: str,
) -> str:
    """在项目下建一个绑定 Mock 实例的模型（`docs/07` §16 R25 的租户归属链）。"""
    from app.infrastructure.database.models.model import ModelORM
    from app.infrastructure.database.unit_of_work import UnitOfWork

    async with UnitOfWork.from_session_factory(session_factory) as uow:
        row = ModelORM(
            project_id=project_id,
            software_instance_id=instance_id,
            name="P40 Transport Model",
        )
        uow.session.add(row)
        await uow.session.flush()
        return str(row.id)


async def _prepare_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """建表 + Seed + 建模型，返回指向该库的 `Settings`（**只**用于验收准备）。

    ⚠️ `docs/02` §102 的 `--create-tables` 等价物：被测的服务器进程本身**不**建表、
    **不**改表（`docs/07` §14.3）。
    """
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    settings = _seeded_settings(tmp_path)
    engine = _create_engine(settings)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    await seed(factory)
    async with factory() as session:
        tenant_id, user_id, project_id = await _seeded_ids(session)
        instance_id = await _mock_instance_id(session)
    await _link_instance_to_project(
        factory,
        project_id=project_id,
        instance_id=instance_id,
    )
    await engine.dispose()
    return settings


async def _seeded_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ExecutionRuntime, async_sessionmaker[AsyncSession], dict[str, str]]:
    """装配「已配备库 + 进程级运行时」，并绑定 Mock 软件实例。

    Returns:
        `(runtime, factory, ids)`；`ids` 含 `tenant_id` / `user_id` /
        `project_id` / `instance_id` / `model_id`（均为字符串）。
    """
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    settings = _seeded_settings(tmp_path)
    engine = _create_engine(settings)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
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
        tenant_id, user_id, project_id = await _seeded_ids(session)
    model_id = await _link_instance_to_project(
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


def _client_context(ids: Mapping[str, str]) -> dict[str, object]:
    """客户端**允许**提供的资源标识（`docs/02` §69；`docs/07` §8.1）。"""
    return {
        "project_id": ids["project_id"],
        "software_instance_id": ids["instance_id"],
        "model_id": ids["model_id"],
    }


def _local_identity(ids: Mapping[str, str]) -> MCPIdentity:
    """STDIO 的**本地可信身份**（`docs/03` §11；`authentication_method = LOCAL`）。"""

    return MCPIdentity(
        identity=IdentityContext(
            user_id=UUID(ids["user_id"]),
            tenant_id=UUID(ids["tenant_id"]),
            roles=("system_admin",),
            authentication_method=AUTHENTICATION_METHOD_LOCAL,
        ),
        permissions=frozenset({"MODEL_READ", "MODEL_WRITE"}),
    )


async def _mcp_server(
    runtime: ExecutionRuntime,
    factory: async_sessionmaker[AsyncSession],
) -> Any:
    """按会话装配一个既有 `MCPServer`（`docs/02` §123 / §124）。"""
    from app.interfaces.mcp.server import build_mcp_server

    async with factory() as session:
        service = runtime.execution.create_service(session)
        return build_mcp_server(service)


def _statements(engine: AsyncEngine) -> list[str]:
    """录制 SQL 语句（SQL 级钩子；与 P22–P28 / P36 / P37–P39 同一手法）。"""
    captured: list[str] = []

    def _capture(conn: object, cursor: object, statement: str, *rest: object) -> None:
        captured.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _capture)
    return captured


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


def _string_literals(path: Path) -> list[str]:
    """模块里**非文档字符串**的字符串字面量（AST 扫描）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", [])
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            if isinstance(body[0].value.value, str):
                skip.add(id(body[0].value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip
    ]


def _commit_or_rollback_calls(path: Path) -> list[str]:
    """`.commit()` / `.rollback()` 的调用点（AST 红线扫描）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"commit", "rollback"}:
                found.append(node.func.attr)
    return found


def _transport_module_paths() -> list[Path]:
    """传输层模块路径（`docs/07` §3.3 的登记形状）。"""
    return sorted(path for path in TRANSPORT_DIR.rglob("*.py") if path.name != "__pycache__")


def _run_main(
    *args: str,
    database_url: str | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """以子进程跑 `python -m app.main`（门槛：退出码 0 + stdout 0 字节）。"""
    environment = dict(os.environ)
    if database_url is not None:
        environment["DATABASE_URL"] = database_url
    if env:
        environment.update(env)
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "app.main", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


def _free_port() -> int:
    """取一个空闲端口（HTTP E2E 用）。"""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_for_port(port: int, *, budget_seconds: float = 30.0) -> None:
    """等待 HTTP 服务器就绪（连得上即返回）。

    ⚠️ 参数名**不**叫 `timeout`：`ruff` 的 `ASYNC109` 要求异步函数的超时改用
    `anyio.fail_after`。这里刻意保留「轮询 + 预算」的写法，因为要等的是**外部**
    进程开始监听（`anyio.fail_after` 会在超时时抛出，而本函数需要一个明确的
    装配错误信息），故用中性名字表达「等待预算」。
    """
    deadline = anyio.current_time() + budget_seconds
    while anyio.current_time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            await anyio.sleep(0.05)
    raise AssertionError(f"HTTP transport did not start listening on port {port}")


# ===== ① 抽象与结构（`docs/03` §3 / §20 / §27 / §50 / §59）=====


def test_batch_id_is_a_batch_marker() -> None:
    """门槛 ⑦（`docs/08` §3）：容器批次号是 `P<两位数字>` 的批次标记。

    ⚠️ 断言**不**绑定具体批次：后续批次会继续推进 `BATCH_ID`。
    """
    assert re.fullmatch(r"P\d{2}", BATCH_ID), BATCH_ID


def test_transport_abstract_has_exactly_the_four_documented_methods() -> None:
    """门槛 ①（`docs/03` §3）：`MCPTransport` **恰好**四个通信方法，且不认业务概念。"""
    declared = tuple(name for name in TRANSPORT_METHODS_SPEC if hasattr(MCPTransport, name))
    assert declared == TRANSPORT_METHODS_SPEC
    for forbidden in ("tool", "operation", "adapter", "software", "database"):
        assert not hasattr(MCPTransport, forbidden), forbidden


def test_tool_input_schema_is_the_documented_two_level_envelope() -> None:
    """门槛 ③（`docs/02` §84 ∪ `docs/03` §27）：顶层信封键逐条一致，且只要求 `operation`。"""
    from app.interfaces.mcp.transport import TOOL_INPUT_SCHEMA

    assert tuple(TOOL_INPUT_SCHEMA["properties"]) == TOOL_INPUT_SCHEMA_KEYS_SPEC
    assert TOOL_INPUT_SCHEMA["required"] == ["operation"]
    assert TOOL_INPUT_SCHEMA["type"] == "object"


def test_runtime_limits_follow_the_documented_defaults() -> None:
    """门槛 ②（`docs/03` §20 / §79）：运行期限制字段与规范默认值逐条一致。"""
    limits = MCPRuntimeLimits()
    for name in LIMIT_FIELDS_SPEC:
        assert hasattr(limits, name), name
    assert limits.max_message_bytes == 10_485_760
    assert limits.max_request_bytes == 10_485_760
    assert limits.max_concurrent_sessions == 100
    assert limits.max_inflight_requests == 100
    assert limits.session_idle_timeout_seconds == 1800
    assert limits.session_max_lifetime_seconds == 86_400


def test_server_instructions_are_the_documented_text() -> None:
    """门槛 ②（`docs/03` §64）：`initialize` 的 `instructions` 逐字一致。"""
    from app.interfaces.mcp.transport import SERVER_INSTRUCTIONS

    assert SERVER_INSTRUCTIONS == SERVER_INSTRUCTIONS_SPEC


def test_origin_and_host_allowlist_is_never_wide_open() -> None:
    """门槛 ②（`docs/03` §50）：允许列表**永远**显式，不存在 `allow all` 默认值。"""
    settings = build_transport_security("127.0.0.1")
    assert settings.enable_dns_rebinding_protection is True
    joined = " ".join(settings.allowed_hosts)
    for host in ALLOWED_HOSTS_SPEC:
        assert host in joined, host
    assert "*" not in joined.replace(":*", "")
    assert settings.allowed_origins


def test_session_metric_names_match_the_documented_six() -> None:
    """门槛 ②（`docs/03` §59）：六个指标名逐条一致（本层名字去掉 SDK 前缀）。"""
    assert len(SESSION_METRIC_NAMES) == 6
    assert tuple(f"structai_mcp_{name}" for name in SESSION_METRIC_NAMES) == (
        SESSION_METRIC_NAMES_SPEC
    )


# ===== ② HTTP 会话 / 限额原语（`docs/03` §16 / §22–§24 / §47–§53）=====


def test_session_table_binds_identity_and_expires() -> None:
    """门槛 ②（`docs/03` §16 / §47 / §49 / §57）：会话绑定主体；空闲 / 最长存活都会过期。"""
    table = SessionTable(idle_timeout_seconds=10, max_lifetime_seconds=100)
    assert table.bind("s1", "tenant-a:user-a", 0.0) is True
    assert table.bind("s1", "tenant-b:user-b", 1.0) is False
    assert table.principal_of("s1") == "tenant-a:user-a"
    assert table.count_for("tenant-a:user-a") == 1
    assert len(table) == 1
    assert table.expired(5.0) == ()
    assert table.expired(11.0) == ("s1",)
    assert table.sweep(11.0) == ("s1",)
    assert len(table) == 0
    assert table.bind("s2", "tenant-a:user-a", 0.0) is True
    assert table.expired(101.0) == ("s2",)
    assert table.principal_of("missing") is None


def test_rate_limiter_is_a_fixed_window_per_dimension() -> None:
    """门槛 ②（`docs/03` §53）：固定窗口限流（超限即拒；窗口滚动后恢复；维度互不影响）。"""
    limiter = RateLimiter(limit_per_minute=2)
    assert RATE_WINDOW_SECONDS == 60.0
    assert limiter.allow("ip", "10.0.0.1", 0.0) is True
    assert limiter.allow("ip", "10.0.0.1", 0.1) is True
    assert limiter.allow("ip", "10.0.0.1", 0.2) is False
    assert limiter.allow("identity", "t:u", 0.2) is True
    assert limiter.allow("ip", "10.0.0.1", 61.0) is True


def test_inflight_counter_refuses_beyond_the_limit() -> None:
    """门槛 ②（`docs/03` §24）：全局在途上限；释放后名额可复用（幂等保护）。"""
    counter = InflightCounter(limit=2)
    assert counter.acquire() is True
    assert counter.acquire() is True
    assert counter.acquire() is False
    counter.release()
    assert counter.acquire() is True
    counter.release()
    counter.release()
    counter.release()
    assert counter.active == 0


async def test_body_reader_enforces_the_limit_before_parsing() -> None:
    """门槛 ②（`docs/03` §52）：body 在**进入解析前**就被限制（超限即截断）。"""
    chunks: list[dict[str, Any]] = [
        {"type": "http.request", "body": b"x" * 8, "more_body": True},
        {"type": "http.request", "body": b"y" * 8, "more_body": False},
    ]
    calls = 0

    async def _receive() -> Any:
        nonlocal calls
        message = chunks[min(calls, len(chunks) - 1)]
        calls += 1
        return message

    reader = BodyReader(_receive, limit=10)
    first = await reader()
    assert first["body"] == b"x" * 8
    message = await reader()
    assert reader.exceeded is True
    assert message["body"] == b""
    assert message["more_body"] is False


def test_header_helpers_are_case_insensitive_and_count_bytes() -> None:
    """门槛 ②（`docs/03` §47 / §54）：header 解析（大小写不敏感）与字节计数。"""
    scope: dict[str, Any] = {
        "headers": [(b"Authorization", b"Bearer t"), (b"Mcp-Session-Id", b"abc")],
        "client": ("10.0.0.9", 1234),
    }
    headers = header_map(scope)
    assert headers["authorization"] == "Bearer t"
    assert headers[MCP_SESSION_ID_HEADER] == "abc"
    assert header_bytes(scope) == sum(len(key) + len(value) for key, value in scope["headers"])
    assert client_key(scope) == "10.0.0.9"
    assert client_key({}) == "unknown"
    assert response_header_value([(b"Mcp-Session-Id", b"xyz")], MCP_SESSION_ID_HEADER) == "xyz"
    assert response_header_value([(b"Other", b"xyz")], MCP_SESSION_ID_HEADER) is None


# ===== ③ HTTP 鉴权 / 会话绑定（`docs/03` §12 / §49；`docs/07` §8.1）=====


async def _http_app_stub(calls: list[dict[str, Any]], *, session_id: str = "sess-1") -> Any:
    """记录转发 + 回一个带 `mcp-session-id` 的响应（`docs/03` §47）。"""

    async def _app(scope: Any, receive: Any, send: Any) -> None:
        # 读掉 body（真实下游会读）：这样 `BodyReader` 的限额判定才会生效
        # （`docs/03` §52「在 body 进入业务解析前限制」）。
        while True:
            message = await receive()
            if message.get("type") != "http.request" or not message.get("more_body"):
                break
        calls.append({"scope": scope, "state": dict(scope.get("state") or {})})
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(MCP_SESSION_ID_HEADER.encode(), session_id.encode())],
            }
        )
        await send({"type": "http.response.body", "body": b"{}"})

    return _app


def _http_middleware(
    *,
    runtime: ExecutionRuntime,
    calls: list[dict[str, Any]],
    limits: MCPRuntimeLimits | None = None,
) -> Any:
    """装配守门中间件 + 一个「记录转发」的下游应用（`docs/03` §44）。"""
    from app.interfaces.mcp.transport.http import MCPHTTPMiddleware

    return MCPHTTPMiddleware(
        app=_app_placeholder(calls),
        authenticator=runtime.execution.authenticator(),
        limits=limits or MCPRuntimeLimits(),
        path=DEFAULT_HTTP_PATH,
    )


def _app_placeholder(calls: list[dict[str, Any]]) -> Any:
    """下游应用的占位（在 `_http_middleware` 里由事件循环装配真实实现）。"""
    raise AssertionError("the stub app must be provided by _http_app_stub")


async def _call_asgi(
    middleware: Any,
    *,
    headers: Sequence[tuple[bytes, bytes]] = (),
    method: str = "POST",
    path: str = DEFAULT_HTTP_PATH,
    body: bytes = b"{}",
    client: tuple[str, int] = ("10.0.0.7", 4321),
) -> tuple[int, dict[str, str], bytes]:
    """驱动一次 ASGI 请求并收集响应（`docs/03` §44 的守门路径）。"""
    sent: list[Any] = []
    scope: dict[str, Any] = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": list(headers),
        "client": client,
    }
    delivered = False

    async def _receive() -> Any:
        nonlocal delivered
        if delivered:
            return {"type": "http.request", "body": b"", "more_body": False}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def _send(message: Any) -> None:
        sent.append(message)

    await middleware(scope, _receive, _send)
    status = 200
    response_headers: dict[str, str] = {}
    payload = b""
    for message in sent:
        if message["type"] == "http.response.start":
            status = int(message["status"])
            response_headers = {
                bytes(key).decode("latin-1").lower(): bytes(value).decode("latin-1")
                for key, value in message.get("headers", [])
            }
        elif message["type"] == "http.response.body":
            payload += message.get("body", b"")
    return status, response_headers, payload


async def _seeded_token(
    runtime: ExecutionRuntime,
    factory: async_sessionmaker[AsyncSession],
) -> str:
    """用**已配备库**里的管理员口令登录，拿一个真实的会话 Token（P10–P13）。

    ⚠️ Token 只在这个变量里存活，**不**写入任何断言消息 / 日志 / 审计（`docs/07` §14.3）。
    """
    from app.infrastructure.database.unit_of_work import UnitOfWork

    async with UnitOfWork.from_session_factory(factory) as uow:
        security = runtime.execution.security_for(uow.session)
        result = await security.guard.login("admin", TEST_PASSWORD)
    return result.access_token


async def test_http_requires_bearer_authentication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ②（`docs/03` §12 / §58；`docs/07` §8.1）：缺凭据 → `401` + `WWW-Authenticate`。"""
    from app.interfaces.mcp.transport.http import MCPHTTPMiddleware

    runtime, _factory, _ids = await _seeded_runtime(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []
    middleware = MCPHTTPMiddleware(
        app=await _http_app_stub(calls),
        authenticator=runtime.execution.authenticator(),
        path=DEFAULT_HTTP_PATH,
    )
    status, headers, _payload = await _call_asgi(middleware)
    assert status == 401
    assert headers.get("www-authenticate", "").startswith("Bearer")
    assert calls == []  # 未认证的请求**不**触达 MCP 应用
    assert middleware.metrics["auth_failures_total"] == 1

    status, _headers, _payload = await _call_asgi(
        middleware, headers=[(b"authorization", b"Bearer not-a-real-token")]
    )
    assert status == 401
    assert calls == []
    assert middleware.metrics["auth_failures_total"] == 2


async def test_http_identity_comes_from_the_server_not_the_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ②（`docs/07` §8.1）：身份由**服务端**构造，客户端 header / body 声明无效。"""
    from app.interfaces.mcp.transport.http import MCPHTTPMiddleware

    runtime, factory, ids = await _seeded_runtime(tmp_path, monkeypatch)
    token = await _seeded_token(runtime, factory)
    calls: list[dict[str, Any]] = []
    middleware = MCPHTTPMiddleware(
        app=await _http_app_stub(calls),
        authenticator=runtime.execution.authenticator(),
        path=DEFAULT_HTTP_PATH,
    )
    forged = json.dumps(
        {
            "operation": "MODEL.NODE.QUERY",
            "context": {"user_id": ids["user_id"], "tenant_id": ids["tenant_id"]},
        }
    ).encode()
    status, headers, _payload = await _call_asgi(
        middleware,
        headers=[
            (b"authorization", f"Bearer {token}".encode()),
            (b"x-user-id", b"forged"),
            (b"content-type", b"application/json"),
        ],
        body=forged,
    )
    assert status == 200
    assert headers.get(MCP_SESSION_ID_HEADER) == "sess-1"
    assert len(calls) == 1
    bound = calls[0]["state"].get("structai.mcp.identity")
    assert isinstance(bound, MCPIdentity)
    assert str(bound.identity.tenant_id) == ids["tenant_id"]
    assert str(bound.identity.user_id) == ids["user_id"]
    assert middleware.metrics["sessions_created_total"] == 1
    assert middleware.metrics["sessions_active"] == 1


async def test_http_session_cannot_be_reused_by_another_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ②（`docs/03` §47–§49）：会话与 `session_id` 绑定，换身份**必须**拒绝。"""
    from app.interfaces.mcp.transport.http import MCPHTTPMiddleware

    runtime, factory, _ids = await _seeded_runtime(tmp_path, monkeypatch)
    token = await _seeded_token(runtime, factory)
    calls: list[dict[str, Any]] = []
    middleware = MCPHTTPMiddleware(
        app=await _http_app_stub(calls),
        authenticator=runtime.execution.authenticator(),
        path=DEFAULT_HTTP_PATH,
    )
    first = await _call_asgi(middleware, headers=[(b"authorization", f"Bearer {token}".encode())])
    assert first[0] == 200
    assert middleware.session_principal("sess-1") is not None

    # 同一个 Token 复用**自己的**会话 → 放行
    again = await _call_asgi(
        middleware,
        headers=[
            (b"authorization", f"Bearer {token}".encode()),
            (MCP_SESSION_ID_HEADER.encode(), b"sess-1"),
        ],
    )
    assert again[0] == 200

    # 另一个身份（不同主体的会话）→ 拒绝（`docs/03` §49）
    # ⚠️ 用**当前时钟**登记，避免被空闲回收误判为已过期（那是另一条规则，见 §16）。
    middleware._sessions.bind(
        "sess-other",
        "other-tenant:other-user",
        middleware.clock(),
    )
    status, _headers, payload = await _call_asgi(
        middleware,
        headers=[
            (b"authorization", f"Bearer {token}".encode()),
            (MCP_SESSION_ID_HEADER.encode(), b"sess-other"),
        ],
    )
    assert status == 403
    assert b"another authenticated identity" in payload
    assert middleware.session_principal("sess-other") == "other-tenant:other-user"

    # 会话过期后，**同一个** `mcp-session-id` 不再被识别为「属于别人」：
    # 本层回收后由下游（SDK 会话表）按「未知会话」处理（`docs/03` §49 / §57）。
    middleware._sessions.bind(
        "sess-expired", "other-tenant:other-user", middleware.clock() - 10_000
    )
    status, _headers, _payload = await _call_asgi(
        middleware,
        headers=[
            (b"authorization", f"Bearer {token}".encode()),
            (MCP_SESSION_ID_HEADER.encode(), b"sess-expired"),
        ],
    )
    assert status == 200
    assert middleware.session_principal("sess-expired") is None
    assert middleware.metrics["sessions_closed_total"] >= 1


async def test_http_body_limit_is_enforced_before_the_application_sees_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ②（`docs/03` §52）：超限 body → `413`（**不**进业务解析）。"""
    from app.interfaces.mcp.transport.http import MCPHTTPMiddleware

    runtime, factory, _ids = await _seeded_runtime(tmp_path, monkeypatch)
    token = await _seeded_token(runtime, factory)
    calls: list[dict[str, Any]] = []
    middleware = MCPHTTPMiddleware(
        app=await _http_app_stub(calls),
        authenticator=runtime.execution.authenticator(),
        limits=MCPRuntimeLimits(max_request_bytes=16),
        path=DEFAULT_HTTP_PATH,
    )
    status, _headers, _payload = await _call_asgi(
        middleware,
        headers=[(b"authorization", f"Bearer {token}".encode())],
        body=b"x" * 64,
    )
    assert status == 413
    assert middleware.metrics["request_errors_total"] >= 1


async def test_http_rate_limit_and_inflight_limit_are_enforced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ②（`docs/03` §24 / §53）：限流 `429`、在途上限 `503`（传输保护）。"""
    from app.interfaces.mcp.transport.http import MCPHTTPMiddleware

    runtime, factory, _ids = await _seeded_runtime(tmp_path, monkeypatch)
    token = await _seeded_token(runtime, factory)
    calls: list[dict[str, Any]] = []
    middleware = MCPHTTPMiddleware(
        app=await _http_app_stub(calls),
        authenticator=runtime.execution.authenticator(),
        limits=MCPRuntimeLimits(rate_limit_per_minute=1, max_inflight_requests=1),
        path=DEFAULT_HTTP_PATH,
    )
    headers = [(b"authorization", f"Bearer {token}".encode())]
    first = await _call_asgi(middleware, headers=headers)
    assert first[0] == 200
    second = await _call_asgi(middleware, headers=headers)
    assert second[0] == 429

    relaxed = MCPHTTPMiddleware(
        app=await _http_app_stub(calls),
        authenticator=runtime.execution.authenticator(),
        limits=MCPRuntimeLimits(max_inflight_requests=0, max_concurrent_sessions=1),
        path=DEFAULT_HTTP_PATH,
    )
    assert (await _call_asgi(relaxed, headers=headers))[0] == 200
    # 会话上限已满（第 1 个会话占位）→ 第 2 个新会话被拒
    third = await _call_asgi(
        relaxed,
        headers=[(b"authorization", f"Bearer {token}".encode()), (b"x-fresh", b"1")],
    )
    assert third[0] in {200, 503}
    assert relaxed.metrics["sessions_active"] == len(relaxed._sessions)


async def test_http_non_mcp_path_is_forwarded_untouched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ②（`docs/03` §45）：MCP endpoint 之外的路径**不**由本传输处理。"""
    from app.interfaces.mcp.transport.http import MCPHTTPMiddleware

    runtime, _factory, _ids = await _seeded_runtime(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []
    middleware = MCPHTTPMiddleware(
        app=await _http_app_stub(calls),
        authenticator=runtime.execution.authenticator(),
        path=DEFAULT_HTTP_PATH,
    )
    status, _headers, _payload = await _call_asgi(middleware, path="/livez")
    assert status == 200
    assert len(calls) == 1  # 直接转发给下游，**不**做鉴权 / 会话判定


# ===== ④ STDIO E2E（`docs/03` §40–§43 / §25–§34；`docs/02` §97 / §123）=====


async def test_stdio_end_to_end_with_a_generic_mcp_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ①（`docs/03` §40–§43 / §66）：Generic MCP Client 能
    `connect` → `list_tools`（**恰好 9** 个）→ `call_tool`（统一信封）。

    ⚠️ 这里跑的是**真实子进程** `python -m app.main --transport stdio`：
    因此 `connect` 是真正的 STDIO 握手，`stdout` 也确实是协议帧（见下一个测试）。
    """
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    settings = await _prepare_database(tmp_path, monkeypatch)
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.main", "--transport", "stdio"],
        env={
            "DATABASE_URL": settings.database_url,
            "ARTIFACT_ROOT": settings.artifact_root,
            "LOG_LEVEL": "WARNING",
        },
        cwd=str(REPO_ROOT),
    )
    ids = await _database_ids(settings)
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = tuple(tool.name for tool in listed.tools)
            assert sorted(names) == sorted(TOOL_NAMES_SPEC)
            assert len(names) == 9

            context = {
                "project_id": ids["project_id"],
                "software_instance_id": ids["instance_id"],
                "model_id": ids["model_id"],
            }

            # (a) SYNC 查询：端到端返回 `docs/02` §71 的统一信封（`docs/03` §70）
            queried = await session.call_tool(
                "engineering_model_query",
                {"operation": "MODEL.NODE.QUERY", "parameters": {}, "context": context},
            )
            envelope = queried.structured_content
            assert isinstance(envelope, Mapping)
            assert envelope["success"] is True, envelope.get("errors")
            assert envelope["tool"] == "engineering_model_query"
            assert envelope["operation"] == "MODEL.NODE.QUERY"
            assert envelope["request_id"].startswith("req_")
            assert envelope["trace_id"].startswith("trace_")
            assert envelope["errors"] == []
            assert queried.is_error is False
            assert queried.content[0].type == "text"

            # (b) 高风险写操作：缺确认令牌 → 明确的 `STRUCTAI-4100`（`docs/03` §68）
            #     ⚠️ 传输层**不**做这个判定，它由管线第 13 步给出（`docs/07` §9）。
            built = await session.call_tool(
                "engineering_model_build",
                {
                    "operation": "BUILD.COLUMN",
                    "parameters": dict(BUILD_COLUMN_PARAMETERS),
                    "context": context,
                },
            )
            refusal = built.structured_content
            assert isinstance(refusal, Mapping)
            assert refusal["success"] is False
            assert refusal["errors"][0]["code"] == "STRUCTAI-4100"
            assert refusal["errors"][0]["details"]["reason"] == "missing_token"
            assert built.is_error is True

            # (c) 未知工具：仍由 MCP 层翻成统一信封（`docs/02` §58；**不**新增码）
            unknown = await session.call_tool("engineering_nope", {"operation": "MODEL.NODE.QUERY"})
            unknown_envelope = unknown.structured_content
            assert isinstance(unknown_envelope, Mapping)
            assert unknown_envelope["success"] is False
            assert unknown_envelope["errors"][0]["code"] == "STRUCTAI-1000"
            assert unknown_envelope["errors"][0]["details"]["reason"] == "unknown_tool"


async def _database_ids(settings: Settings) -> dict[str, str]:
    """从已配备库读回验收需要的资源标识（`docs/02` §69 的白名单字段）。"""
    engine = _create_engine(settings)
    factory = create_session_factory(engine)
    async with factory() as session:
        tenant_id, user_id, project_id = await _seeded_ids(session)
        instance_id = await _mock_instance_id(session)
        from app.infrastructure.database.models.model import ModelORM

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


def test_main_without_transport_keeps_stdout_empty(tmp_path: Path) -> None:
    """门槛 ① / ⑤（`docs/03` §42；`docs/02` §97）：未接客户端时 stdout **0 字节**。

    ⚠️ 这是 P02 门槛「stdout 0 字节」在传输层上线后的**延伸**：`--transport none`
    （缺省）只做启动 / 关闭，任何日志都走 stderr。
    """
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p40_main.db').as_posix()}"
    completed = _run_main(database_url=database_url)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert f"batch={BATCH_ID}" in completed.stderr


def test_main_stdio_without_a_client_keeps_stdout_empty(tmp_path: Path) -> None:
    """门槛 ①（`docs/03` §42 / §76）：STDIO 上线后，**未接客户端**仍 stdout 0 字节。

    `python -m app.main --transport stdio` 在 stdin 立刻 EOF（这里 stdin 是关闭的）
    时应当干净退出：退出码 0、stdout 0 字节、日志全在 stderr。
    """
    settings = asyncio.run(_prepare_database_offline(tmp_path))
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "app.main", "--transport", "stdio"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "DATABASE_URL": settings.database_url,
            "ARTIFACT_ROOT": settings.artifact_root,
            "LOG_LEVEL": "WARNING",
            ADMIN_PASSWORD_ENV: TEST_PASSWORD,
        },
        input="",
        check=False,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    # 日志确实走 stderr（`docs/03` §42）：`LOG_LEVEL=WARNING` 下只剩 registry 告警。
    assert "structai" in completed.stderr


async def _prepare_database_offline(tmp_path: Path) -> Settings:
    """不依赖 monkeypatch 的建库辅助（供**同步**测试用）。"""
    previous = os.environ.get(ADMIN_PASSWORD_ENV)
    os.environ[ADMIN_PASSWORD_ENV] = TEST_PASSWORD
    try:
        settings = _seeded_settings(tmp_path)
        engine = _create_engine(settings)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = create_session_factory(engine)
        await seed(factory)
        async with factory() as session:
            tenant_id, user_id, project_id = await _seeded_ids(session)
            instance_id = await _mock_instance_id(session)
        await _link_instance_to_project(
            factory,
            project_id=project_id,
            instance_id=instance_id,
        )
        await engine.dispose()
        return settings
    finally:
        if previous is None:
            os.environ.pop(ADMIN_PASSWORD_ENV, None)
        else:
            os.environ[ADMIN_PASSWORD_ENV] = previous


# ===== ⑤ Streamable HTTP E2E（`docs/03` §44–§59 / §66 / §77）=====


async def test_http_end_to_end_with_a_generic_mcp_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ②（`docs/03` §44 / §77）：同一 Tool Runtime 经 Streamable HTTP 可达。

    ⚠️ 这里跑的是**真实 uvicorn 服务器**（`python -m app.main --transport http`）：
    客户端是 SDK 的通用 Streamable HTTP 客户端，`Authorization: Bearer <token>`
    是唯一的凭据通道（`docs/07` §8.1）—— 身份由**服务端**从 Token 还原。
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    settings = await _prepare_database(tmp_path, monkeypatch)
    ids = await _database_ids(settings)
    token = await _token_for(settings, ids)
    port = _free_port()
    environment = {
        **os.environ,
        "DATABASE_URL": settings.database_url,
        "ARTIFACT_ROOT": settings.artifact_root,
        "LOG_LEVEL": "WARNING",
        "HOST": "127.0.0.1",
        "PORT": str(port),
        ADMIN_PASSWORD_ENV: TEST_PASSWORD,
    }
    # ⚠️ 这里**故意**用同步 `Popen`：被测的是「`python -m app.main --transport http`
    # 这个真实进程」，而 `anyio.open_process` 会把子进程绑到当前事件循环的取消作用域，
    # 测试结束时难以保证「进程已终止 + stdout/stderr 已读完」的断言顺序。
    process = subprocess.Popen(  # noqa: S603, ASYNC220
        [sys.executable, "-m", "app.main", "--transport", "http"],
        cwd=REPO_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        await _wait_for_port(port)
        headers = {"Authorization": f"Bearer {token}"}
        probe = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        accept = {"Accept": "application/json, text/event-stream"}
        # (a) 未认证 → `401`（`docs/03` §12；`docs/07` §8.1）
        #     ⚠️ 守门中间件在**协议层之前**就拒绝，因此这里**不**带 `Authorization`。
        async with httpx.AsyncClient(timeout=30.0) as anonymous:
            unauthorized = await anonymous.post(
                f"http://127.0.0.1:{port}{DEFAULT_HTTP_PATH}",
                json=probe,
                headers=accept,
            )
            assert unauthorized.status_code in {401, 403}
            assert "unauthorized" in unauthorized.text
        async with httpx.AsyncClient(headers=headers, timeout=60.0):
            # (b) 通用 MCP 客户端：initialize → tools/list → tools/call
            async with streamable_http_client(
                f"http://127.0.0.1:{port}{DEFAULT_HTTP_PATH}",
                http_client=httpx.AsyncClient(headers=headers, timeout=60.0),
            ) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    names = tuple(tool.name for tool in listed.tools)
                    assert sorted(names) == sorted(TOOL_NAMES_SPEC)
                    assert len(names) == 9

                    result = await session.call_tool(
                        "engineering_model_query",
                        {
                            "operation": "MODEL.NODE.QUERY",
                            "parameters": {},
                            "context": {
                                "project_id": ids["project_id"],
                                "software_instance_id": ids["instance_id"],
                                "model_id": ids["model_id"],
                            },
                        },
                    )
                    envelope = result.structured_content
                    assert isinstance(envelope, Mapping)
                    assert envelope["success"] is True, envelope.get("errors")
                    assert envelope["tool"] == "engineering_model_query"
                    assert envelope["request_id"].startswith("req_")
                    assert result.is_error is False
    finally:
        process.terminate()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:  # pragma: no cover - 兜底
            process.kill()
        stdout = process.stdout.read() if process.stdout else ""
        stderr = process.stderr.read() if process.stderr else ""
        assert stdout == ""  # stdout 只放协议帧（`docs/03` §42 的同一纪律）
        assert "structai" in stderr


async def _token_for(settings: Settings, ids: Mapping[str, str]) -> str:
    """在**测试进程**里签发一个真实会话 Token（P10–P13 的登录链）。

    ⚠️ Token 只在这个变量里存活，**不**写入任何断言消息 / 日志 / 审计（`docs/07` §14.3）。
    """
    from app.infrastructure.database.unit_of_work import UnitOfWork

    engine = _create_engine(settings)
    factory = create_session_factory(engine)
    runtime = build_execution_runtime(
        settings,
        operation_registry=await OperationRegistry.load(engine, factory),
        capability_registry=await CapabilityRegistry.load(engine, factory),
    )
    runtime.session_factory = factory
    async with UnitOfWork.from_session_factory(factory) as uow:
        security = runtime.execution.security_for(uow.session)
        result = await security.guard.login("admin", TEST_PASSWORD)
        token = result.access_token
    await engine.dispose()
    assert ids  # 保留参数以便未来断言身份（当前只签发 Token）
    return token
