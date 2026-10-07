"""P19–P20 验收测试：Adapter Base + Mock Adapter（`docs/07` §12 P19–P20；`docs/02` §32–§33）。

验收点（与续接提示词的 ①–⑧ 一一对应）：
① Adapter Base（`docs/02` §32）：`EngineeringSoftwareAdapter` 抽象出
   `connect` / `disconnect` / `health_check` / `get_version` / `get_capabilities` /
   `execute` / `cancel` / `normalize_error` **八个**方法；`execute(operation, parameters,
   context)` 只接受**规范化**输入 / 返回**规范化**结果；Core 内不得出现任何厂商内容；
② AdapterManager（`docs/02` §33）：按 `AdapterManifest` 注册 / 查找 / 连接 / 断开；
   同一 `(vendor, product)` 不重复注册；未知实例 → 明确失败（**不**静默回落）；
   单实例失败**不得**让整个 Manager 不可用（`docs/07` §14.4）；
③ 错误归一化（`docs/07` §11；`docs/02` §49 / §50）：连接 → `STRUCTAI-2000`、
   鉴权 → `STRUCTAI-2100`、业务错 → `STRUCTAI-2200`、超时 → `STRUCTAI-2300`、
   兜底 → `STRUCTAI-6000`；**不泄露**原生 message / 凭据；
④ Mock Adapter 端到端（`docs/02` §117 / §61 / §62；`docs/07` §12.1 里程碑 ①②）：
   `BUILD.COLUMN` 走通「OperationDefinition → MockAdapter.execute → 规范化结果」，
   并覆盖 `MODEL.NODE.QUERY` 与 `MODEL.LOAD.ASSIGN`；执行前后模型状态可读回；
⑤ Capability 联动（`docs/07` §16 R30）：Mock Adapter 的 `get_capabilities()` 提供
   **运行时**能力清单，接入 `CapabilityResolver.status_of()`；`UNSUPPORTED` 由它给出
   （本批**首次**产出 `UNSUPPORTED`，P14–P18 只产出 `UNKNOWN`）；
⑥ 回归：既有 **229 项 pytest 不得回退**（由整轮 `pytest -q` 覆盖；本文件只补
   `app.main` 两条）、P04 建表 24 张 / `SELECT 1`、P02 覆盖行为；
⑦ 质量：`ruff` / `mypy` 覆盖；本文件额外断言依赖清单**未扩**、容器形状**未变**、
   Adapter 层**不依赖** `app.interfaces` / FastAPI / MCP SDK、新模块**不得 `commit`**；
⑧ 红线：`app/` 内厂商名 0 处、`app/domain/` 无 SQLAlchemy、不新增 `STRUCTAI-xxxx` 码、
   **绝不记录 secret**、新增 Settings 字段必须同步 `.env.example`（本批未新增）。

⚠️ 本文件里的「规范原文副本」（八方法清单 / 21 条能力码 / 原生异常映射表 / Mock E2E 顺序 /
20 码清单 / 依赖清单）**故意不**从被测模块取：若断言只与被测常量比较，
「常量被改错」与「实现被改错」会一起通过（同源循环）。
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import AsyncIterator, Sequence
from dataclasses import fields
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import event, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.execution import ExecutionContext, ExecutionContextFactory
from app.application.security.context import IdentityContext
from app.application.services import CapabilityResolver, RuntimeCapabilitySource
from app.config.settings import Settings
from app.container import BATCH_ID, AppContainer
from app.domain.enums import CapabilityStatus, SoftwareConnectionState
from app.domain.errors import (
    AdapterError,
    CapabilityError,
    InternalError,
    ResourceLockedError,
    StructAIError,
    TenantAccessDeniedError,
)
from app.domain.protocols import OperationDefinition, SoftwareInstanceRecord
from app.infrastructure.adapters import (
    ADAPTER_METHODS,
    MOCK_CAPABILITIES,
    MOCK_PROTOCOL,
    MOCK_SUPPORTED_OPERATIONS,
    MOCK_SUPPORTED_VERSIONS,
    MOCK_VENDOR,
    AdapterContext,
    AdapterManager,
    AdapterManifest,
    AdapterNotFoundError,
    AdapterState,
    BaseAdapter,
    EngineeringSoftwareAdapter,
    MockAdapter,
    MockModelStore,
    adapter_context_from,
    manifest_key,
    normalize_error,
)
from app.infrastructure.adapters.base.errors import (
    ADAPTER_NATIVE_ERROR_CODES,
    FALLBACK_ADAPTER_MESSAGE,
    REDACTION_MARKER,
    SENSITIVE_DETAIL_KEY_PARTS,
    AdapterAPIError,
    AdapterAuthenticationError,
    AdapterCapabilityError,
    AdapterConnectionError,
    AdapterNativeError,
    AdapterTimeoutError,
    AdapterValidationError,
    error_for,
    raise_normalized,
)
from app.infrastructure.database import Base, create_engine, create_session_factory
from app.infrastructure.database.models import SoftwareInstanceORM, TenantORM, UserORM
from app.infrastructure.database.seed import ADMIN_PASSWORD_ENV, seed
from app.infrastructure.registry.capability_registry import CapabilityRegistry
from app.infrastructure.registry.operation_registry import OperationRegistry
from app.infrastructure.registry.software_registry import SoftwareInstanceView

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
ADAPTERS_DIR = APP_DIR / "infrastructure" / "adapters"
BASE_DIR = ADAPTERS_DIR / "base"
MOCK_DIR = ADAPTERS_DIR / "mock"

VENDOR_NAMES = ("MIDAS", "CSI", "ANSYS")
"""`docs/07` §14.2：`app/` 内禁止出现的厂商名。"""

TEST_PASSWORD = "P19-Adapter-验收-口令-4c81"
"""测试用口令（非真实 secret，仅存在于测试进程内）。"""

SessionFactory = async_sessionmaker[AsyncSession]
"""会话工厂类型别名（`docs/02` §15）。"""


# ===== 规范原文副本（`docs/02` §30 / §32 / §49 / §50 / §90；`docs/07` §11）=====

ADAPTER_METHODS_SPEC = (
    "connect",
    "disconnect",
    "health_check",
    "get_version",
    "get_capabilities",
    "execute",
    "cancel",
    "normalize_error",
)
"""`docs/02` §32 的**八个**方法（逐字抄写）。"""

MOCK_CAPABILITIES_SPEC = (
    "MODEL.NODE.READ",
    "MODEL.NODE.WRITE",
    "MODEL.NODE.DELETE",
    "MODEL.ELEMENT.READ",
    "MODEL.ELEMENT.WRITE",
    "MODEL.ELEMENT.DELETE",
    "MODEL.MATERIAL.READ",
    "MODEL.MATERIAL.WRITE",
    "MODEL.SECTION.READ",
    "MODEL.SECTION.WRITE",
    "MODEL.BOUNDARY.READ",
    "MODEL.BOUNDARY.WRITE",
    "MODEL.LOAD.READ",
    "MODEL.LOAD.WRITE",
    "MODEL.LOAD.DELETE",
    "ANALYSIS.STATIC",
    "RESULT.DISPLACEMENT",
    "RESULT.REACTION",
    "RESULT.ELEMENT_FORCE",
    "RESULT.STRESS",
    "DESIGN.STEEL",
)
"""`docs/02` §30 的 Mock 能力清单（逐条抄写；本批不得改）。"""

NATIVE_ERROR_MAPPING_SPEC = (
    (AdapterConnectionError, "STRUCTAI-2000", "SOFTWARE_CONNECTION_ERROR", True),
    (AdapterAuthenticationError, "STRUCTAI-2100", "SOFTWARE_AUTHENTICATION_ERROR", False),
    (AdapterAPIError, "STRUCTAI-2200", "SOFTWARE_API_ERROR", False),
    (AdapterTimeoutError, "STRUCTAI-2300", "SOFTWARE_TIMEOUT", True),
    (AdapterCapabilityError, "STRUCTAI-3000", "CAPABILITY_ERROR", False),
    (AdapterValidationError, "STRUCTAI-1200", "ENGINEERING_VALIDATION_ERROR", False),
)
"""`docs/02` §49 / §50 的原生异常 → 20 码映射（含 `retryable` 口径）。"""

MOCK_E2E_SEQUENCE = (
    "BUILD.COLUMN",
    "MODEL.BOUNDARY.ASSIGN",
    "MODEL.LOAD.ASSIGN",
    "ANALYSIS.STATIC",
    "RESULT.NODE.DISPLACEMENT",
    "DESIGN.STEEL",
)
"""`docs/02` §62 的 Mock E2E 顺序（逐字抄写）。"""

MOCK_BUILD_COLUMN_KEYS = ("node_ids", "element_ids")
"""`docs/02` §90 的 `BUILD.COLUMN` 返回键（逐字抄写）。"""

MOCK_QUERY_KEYS = ("items", "pagination")
"""`docs/02` §35 的查询返回键（逐字抄写）。"""

MOCK_LOAD_KEYS = ("node_id", "fx", "fy", "fz")
"""`docs/02` §40 的荷载返回键（逐字抄写）。"""

HEALTH_KEYS = ("healthy", "state", "version", "latency_ms")
"""`docs/02` §25 / §33 的健康返回键（逐字抄写）。"""

ERROR_ENVELOPE_KEYS = ("code", "type", "message", "details", "retryable")
"""`docs/03` §7 的错误信封键（`StructAIError.to_dict()` 的形状）。"""

TWENTY_CODE_CONTRACT = (
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
)
"""`docs/07` §11：**20 码**错误契约（逐字抄写；本批不得扩）。"""

FROZEN_DEPENDENCIES = (
    "aiosqlite",
    "alembic",
    "argon2-cffi",
    "fastapi",
    "httpx",
    "jsonschema",
    "mcp",
    "pydantic",
    "pydantic-settings",
    "sqlalchemy",
    "structlog",
    "uvicorn",
)
"""`docs/07` §3.1 / §3.2 冻结的运行期依赖（本批不得引入新依赖）。"""

P19_MODULES = (
    "app/infrastructure/adapters/base/adapter.py",
    "app/infrastructure/adapters/base/manifest.py",
    "app/infrastructure/adapters/base/errors.py",
    "app/infrastructure/adapters/base/manager.py",
    "app/infrastructure/adapters/mock/adapter.py",
    "app/infrastructure/adapters/mock/model_store.py",
    "app/infrastructure/adapters/mock/analysis.py",
)
"""本批新增的 Adapter 层模块（`docs/07` §3.3 冻结结构）。"""

P19_PACKAGES = (
    "app/infrastructure/adapters/__init__.py",
    "app/infrastructure/adapters/base/__init__.py",
    "app/infrastructure/adapters/mock/__init__.py",
)
"""本批新增的包入口。"""

FORBIDDEN_FRAMEWORK_ROOTS = ("sqlalchemy", "fastapi", "mcp", "httpx")
"""`docs/07` §14.1：Adapter 层不得依赖的框架 / SDK。"""


# ===== 夹具与辅助 =====


@pytest.fixture
async def seeded_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncEngine]:
    """临时 SQLite + 建表 + 真实 Seed（`docs/02` §15 / §36 / §43–§46）。"""
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p19_adapters.db').as_posix()}"
    engine = create_engine(database_url, echo=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await seed(create_session_factory(engine))
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def sessions(seeded_engine: AsyncEngine) -> SessionFactory:
    """已配备库上的会话工厂（`docs/02` §15）。"""
    return create_session_factory(seeded_engine)


def _relative_path(relative: str) -> Path:
    """仓库内相对路径 → 绝对路径。"""
    return REPO_ROOT / relative


def _imported_modules(path: Path) -> set[str]:
    """文件里 `import` / `from … import` 的模块名（AST 级）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _commit_or_rollback_calls(path: Path) -> list[str]:
    """文件内 `.commit()` / `.rollback()` 调用的属性名（AST 级，忽略文档字符串）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"commit", "rollback"}
    ]


def _defined_functions(path: Path) -> list[str]:
    """文件内 `def` 定义的函数 / 方法名（AST 级）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _recorded_statements(engine: AsyncEngine) -> list[str]:
    """录制引擎上执行过的 SQL 语句（验收用 SQL 级钩子）。"""
    statements: list[str] = []

    def _capture(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _capture)
    return statements


def _write_verbs(statements: Sequence[str]) -> list[str]:
    """语句里的写动词（INSERT / UPDATE / DELETE / REPLACE）。"""
    verbs: list[str] = []
    for statement in statements:
        head = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
        if head in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
            verbs.append(head)
    return verbs


def _run_main(database_url: str) -> subprocess.CompletedProcess[str]:
    """以指定库运行 `python -m app.main`（`docs/07` §12 P01 / P04 的回归入口）。"""
    environment = {**os.environ, "DATABASE_URL": database_url, "LOG_LEVEL": "INFO"}
    return subprocess.run(
        [sys.executable, "-m", "app.main"],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )


async def _provision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str = "p19_main.db",
) -> str:
    """建表 + Seed 一个临时库，返回其 `database_url`。"""
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    database_url = f"sqlite+aiosqlite:///{(tmp_path / name).as_posix()}"
    engine = create_engine(database_url, echo=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await seed(create_session_factory(engine))
    finally:
        await engine.dispose()
    return database_url


def _async_engine_of(session: AsyncSession) -> AsyncEngine:
    """取会话背后的 `AsyncEngine`（`docs/02` §15）。"""
    engine = getattr(session, "bind", None)
    assert isinstance(engine, AsyncEngine), "session is not bound to an AsyncEngine"
    return engine


async def _operation(session: AsyncSession, name: str) -> OperationDefinition:
    """从已配备库装配的 Operation Registry 取一条定义（`docs/02` §28）。"""
    engine = _async_engine_of(session)
    registry = await OperationRegistry.load(engine, create_session_factory(engine))
    assert registry is not None
    return registry.require(name)


async def _operation_names(session: AsyncSession) -> tuple[str, ...]:
    """已配备库里的全部 Operation 名（69 条，升序）。"""
    engine = _async_engine_of(session)
    registry = await OperationRegistry.load(engine, create_session_factory(engine))
    assert registry is not None
    return tuple(sorted(item.name for item in await registry.list()))


async def _capability_registry(session: AsyncSession) -> CapabilityRegistry:
    """从已配备库装配 Capability Registry（P08；41 条能力码）。"""
    engine = _async_engine_of(session)
    registry = await CapabilityRegistry.load(engine, create_session_factory(engine))
    assert registry is not None
    return registry


async def _seeded_instance_id(session: AsyncSession) -> str:
    """Seed 落库的 Mock 软件实例 id（`docs/02` §101）。"""
    result = await session.execute(select(SoftwareInstanceORM.id))
    return str(result.scalars().first())


async def _seeded_tenant_id(session: AsyncSession) -> str:
    """Seed 落库的唯一租户 id。"""
    result = await session.execute(select(TenantORM.id))
    return str(result.scalars().first())


async def _seeded_user_id(session: AsyncSession) -> str:
    """Seed 落库的管理员用户 id。"""
    result = await session.execute(select(UserORM.id).where(UserORM.username == "admin"))
    return str(result.scalars().one())


def _identity(
    *,
    user_id: str | UUID,
    tenant_id: str | UUID,
    roles: Sequence[str] = (),
) -> IdentityContext:
    """构造服务端身份（`docs/02` §26）。"""
    return IdentityContext(
        user_id=user_id if isinstance(user_id, UUID) else UUID(str(user_id)),
        tenant_id=tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id)),
        roles=tuple(roles),
    )


def _context(
    identity: IdentityContext,
    *,
    software_instance_id: str | None = None,
    project_id: str | None = None,
) -> ExecutionContext:
    """由服务端身份构造执行上下文（`docs/02` §5）。"""
    return ExecutionContextFactory().create(
        identity,
        software_instance_id=software_instance_id,
        project_id=project_id,
    )


def _instance_record(
    instance_id: str,
    *,
    status: str = SoftwareConnectionState.CONNECTED.value,
    version: str = "1.0",
    product: str = "Mock Engineering Software",
) -> SoftwareInstanceRecord:
    """构造软件实例快照（`docs/02` §19；本批只用于能力判定的输入）。"""
    return SoftwareInstanceRecord(
        id=instance_id,
        name="Mock Instance",
        version_id="",
        status=status,
        vendor=MOCK_VENDOR,
        product=product,
        version=version,
    )


def _instance_view(instance_id: str) -> SoftwareInstanceView:
    """构造软件实例**视图**（`docs/02` §19；`AdapterManager` 的 `software=` 契约要求）。"""
    return SoftwareInstanceView(
        instance_id=instance_id,
        name="Mock Instance",
        endpoint=None,
        status=SoftwareConnectionState.CONNECTED.value,
        vendor=MOCK_VENDOR,
        product="Mock Engineering Software",
        version="1.0",
    )


def _new_manager() -> AdapterManager:
    """注册 `MockAdapter` 的管理器（`docs/02` §54 的 Register 步骤）。"""
    manager = AdapterManager()
    manager.register(MockAdapter())
    return manager


async def _wired_manager(
    instance_id: str,
    *,
    connect: bool = True,
) -> tuple[AdapterManager, MockAdapter]:
    """注册 + 绑定 + （可选）连接的 Mock 管理器（`docs/02` §54）。"""
    manager = _new_manager()
    adapter = manager.bind_instance(
        instance_id,
        vendor=MockAdapter.vendor,
        product=MockAdapter.product,
    )
    assert isinstance(adapter, MockAdapter)
    if connect:
        await manager.connect(instance_id)
    return manager, adapter


class _BrokenAdapter(MockAdapter):
    """连接必失败、健康检查必抛异常的 Adapter（`docs/07` §14.4 的隔离验收用）。"""

    product = "BrokenEngineering"

    async def _connect(self, config: dict[str, Any]) -> None:
        """永远连不上（`docs/02` §50 的 `STRUCTAI-2000` 场景）。"""
        raise AdapterConnectionError("connect refused")

    async def health_check(self) -> dict[str, Any]:
        """健康探测直接炸掉（`docs/02` §52 的隔离场景）。"""
        raise RuntimeError("health probe exploded")


class _Lookup:
    """最小软件实例来源（`docs/02` §56 的 `software_repository.get_instance`）。"""

    def __init__(self, records: dict[str, SoftwareInstanceView]) -> None:
        self._records = records

    async def get_instance(self, instance_id: str) -> SoftwareInstanceView | None:
        """按 id 读取；不存在返回 `None`。"""
        return self._records.get(instance_id)


# ===== ① Adapter Base（`docs/02` §32 / §4 / §5 / §9 / §10）=====


def test_adapter_abc_abstracts_exactly_the_eight_methods() -> None:
    """门槛 ①：ABC 恰好抽象出 `docs/02` §32 的**八个**方法（顺序也一致）。"""
    assert ADAPTER_METHODS == ADAPTER_METHODS_SPEC
    assert EngineeringSoftwareAdapter.__abstractmethods__ == frozenset(ADAPTER_METHODS_SPEC)
    assert all(name in EngineeringSoftwareAdapter.__dict__ for name in ADAPTER_METHODS_SPEC)

    implemented = {name for name in ADAPTER_METHODS_SPEC if name in BaseAdapter.__dict__}
    assert implemented == {"connect", "disconnect", "normalize_error"}
    assert MockAdapter.__abstractmethods__ == frozenset()
    assert issubclass(MockAdapter, EngineeringSoftwareAdapter)


def test_adapter_abc_signatures_match_docs_02_section_32() -> None:
    """门槛 ①：八个方法的签名与 `docs/02` §32 一致（含 `execute` 的三个参数）。"""
    expected: dict[str, tuple[str, ...]] = {
        "connect": ("self", "config"),
        "disconnect": ("self",),
        "health_check": ("self",),
        "get_version": ("self",),
        "get_capabilities": ("self",),
        "execute": ("self", "operation", "parameters", "context"),
        "cancel": ("self", "task_id"),
        "normalize_error": ("self", "error"),
    }
    for name, parameters in expected.items():
        method = getattr(EngineeringSoftwareAdapter, name)
        assert tuple(inspect.signature(method).parameters) == parameters, name

    for name in ADAPTER_METHODS_SPEC:
        is_async = inspect.iscoroutinefunction(getattr(EngineeringSoftwareAdapter, name))
        assert is_async is (name != "normalize_error"), name


def test_mock_adapter_declares_the_frozen_manifest() -> None:
    """门槛 ①：`MockAdapter` 的声明与 `docs/02` §6 / §29 / §30 逐条一致。"""
    assert MockAdapter.name == "structai.mock"
    assert MockAdapter.vendor == MOCK_VENDOR == "StructAI"
    assert MockAdapter.product == "MockEngineering"
    assert MockAdapter.supported_versions == MOCK_SUPPORTED_VERSIONS == ("1.0",)
    assert MockAdapter.protocols == (MOCK_PROTOCOL,) == ("IN_PROCESS",)
    assert MOCK_CAPABILITIES == MOCK_CAPABILITIES_SPEC

    manifest = MockAdapter().manifest
    assert isinstance(manifest, AdapterManifest)
    assert manifest.validate() is manifest
    assert manifest_key(manifest) == ("StructAI", "MockEngineering")


def test_execute_accepts_normalized_input_and_returns_normalized_result() -> None:
    """门槛 ①：`execute` 只接受规范化输入、只返回规范化结果（`docs/02` §90 / §33）。"""

    async def _run() -> None:
        identity = _identity(user_id=UUID(int=1), tenant_id=UUID(int=2))
        context = _context(identity)
        parameters: dict[str, Any] = {
            "base_node": {"x": 0.0, "y": 0.0, "z": 0.0},
            "height": 6.0,
            "material": "Q355B",
            "section": "H400x400x13x21",
        }

        adapter = MockAdapter()
        await adapter.connect({})
        result = await adapter.execute("BUILD.COLUMN", parameters, context)
        assert tuple(result) == MOCK_BUILD_COLUMN_KEYS
        assert result["node_ids"] == [1, 2]
        assert result["element_ids"] == [1]

        normalized = await adapter.execute_normalized("MODEL.NODE.QUERY", {}, context)
        assert tuple(normalized) == MOCK_QUERY_KEYS
        assert normalized["pagination"] == {"has_more": False, "next_cursor": None}

    asyncio.run(_run())


def test_execute_normalized_rejects_a_non_canonical_result() -> None:
    """门槛 ①：Adapter 返回非映射结果 → `STRUCTAI-6000`（Core 无法消费）。"""

    class _NonCanonical(MockAdapter):
        """故意返回列表（违反「只返回规范化结果」）。"""

        product = "NonCanonicalEngineering"

        async def execute(
            self,
            operation: str,
            parameters: dict[str, Any],
            context: ExecutionContext,
        ) -> Any:
            """返回非映射结果。"""
            return ["not", "a", "mapping"]

    async def _run() -> None:
        adapter = _NonCanonical()
        with pytest.raises(AdapterError) as error:
            await adapter.execute_normalized(
                "MODEL.NODE.QUERY",
                {},
                _context(_identity(user_id=UUID(int=1), tenant_id=UUID(int=2))),
            )
        assert error.value.code == "STRUCTAI-6000"

    asyncio.run(_run())


def test_base_adapter_lifecycle_matches_docs_02_section_10() -> None:
    """门槛 ①：生命周期状态机与 `docs/02` §9 / §10 / §11 一致。"""
    assert tuple(state.value for state in AdapterState) == (
        "CREATED",
        "CONNECTING",
        "CONNECTED",
        "READY",
        "DISCONNECTING",
        "DISCONNECTED",
        "ERROR",
    )

    async def _run() -> None:
        adapter = MockAdapter()
        assert adapter.state.value == "CREATED"
        assert adapter.runtime_capabilities is None

        await adapter.connect({})
        assert adapter.state.value == "READY"
        assert adapter.runtime_capabilities == MOCK_CAPABILITIES_SPEC
        assert await adapter.get_version() == "1.0"

        health = await adapter.health_check()
        assert tuple(health) == HEALTH_KEYS
        assert health["healthy"] is True
        assert health["state"] == "READY"

        await adapter.cancel("task-1")

        await adapter.disconnect()
        assert adapter.state.value == "DISCONNECTED"
        assert adapter.runtime_capabilities is None

        await adapter.disconnect()
        assert adapter.state.value == "DISCONNECTED"

    asyncio.run(_run())


def test_base_adapter_marks_error_state_and_reraises() -> None:
    """门槛 ①：连接失败 → 状态 `ERROR` 且异常**原样上抛**（`docs/02` §10）。"""

    async def _run() -> None:
        adapter = _BrokenAdapter()
        with pytest.raises(AdapterConnectionError):
            await adapter.connect({})
        assert adapter.state.value == "ERROR"
        assert adapter.runtime_capabilities is None

    asyncio.run(_run())


def test_adapter_context_carries_only_the_six_frozen_fields() -> None:
    """门槛 ①：`AdapterContext` 只有 §5 的六个字段，且由执行上下文派生。"""
    names = tuple(field.name for field in fields(AdapterContext))
    assert names == (
        "software_instance_id",
        "product",
        "version",
        "tenant_id",
        "project_id",
        "task_id",
    )
    forbidden = ("password", "token", "secret", "permission", "session", "request")
    assert [name for name in names if any(part in name.lower() for part in forbidden)] == []

    identity = _identity(user_id=UUID(int=1), tenant_id=UUID(int=2))
    context = _context(
        identity,
        software_instance_id=str(UUID(int=3)),
        project_id=str(UUID(int=4)),
    )
    adapter_context = adapter_context_from(context, task_id="task-9")
    assert adapter_context.software_instance_id == str(UUID(int=3))
    assert adapter_context.project_id == str(UUID(int=4))
    assert adapter_context.tenant_id == str(UUID(int=2))
    assert adapter_context.task_id == "task-9"
    assert adapter_context.product == ""

    empty = adapter_context_from(_context(identity))
    assert empty.software_instance_id == ""
    assert empty.project_id is None
    assert empty.task_id is None


def test_adapter_layer_contains_no_vendor_names_and_no_framework_imports() -> None:
    """门槛 ①/⑧：Adapter 层无厂商名，也不依赖 `app.interfaces` / 框架（§14.1 / §14.2）。"""
    paths = [_relative_path(relative) for relative in (*P19_MODULES, *P19_PACKAGES)]
    vendor_hits = [
        f"{path.name}:{vendor}"
        for path in paths
        for vendor in VENDOR_NAMES
        if vendor.lower() in path.read_text(encoding="utf-8").lower()
    ]
    assert vendor_hits == []

    offenders: list[str] = []
    for path in paths:
        for module in _imported_modules(path):
            if module.startswith("app.interfaces"):
                offenders.append(f"{path.name} -> {module}")
            if module.split(".")[0] in FORBIDDEN_FRAMEWORK_ROOTS:
                offenders.append(f"{path.name} -> {module}")
    assert offenders == []


def test_normalize_error_has_exactly_one_mapping_point() -> None:
    """门槛 ③：20 码映射表只出现在 `base/errors.py`（唯一归一化点）。"""
    declared: dict[str, set[str]] = {}
    for relative in P19_MODULES:
        path = _relative_path(relative)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        codes = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and re.fullmatch(r"STRUCTAI-\d{4}", node.value)
        }
        if codes:
            declared[relative] = codes

    errors_module = "app/infrastructure/adapters/base/errors.py"
    assert tuple(declared) == (errors_module,)
    assert declared[errors_module] <= set(TWENTY_CODE_CONTRACT)
    assert ADAPTER_NATIVE_ERROR_CODES == tuple(
        (error_class, code) for error_class, code, _, _ in NATIVE_ERROR_MAPPING_SPEC
    )
    assert "normalize_error" in _defined_functions(_relative_path(errors_module))
    assert not issubclass(AdapterNativeError, StructAIError)


# ===== ② AdapterManager（`docs/02` §12–§14 / §33 / §52–§57）=====


def test_register_returns_validated_manifest_and_rejects_duplicates() -> None:
    """门槛 ②：注册返回已校验的 Manifest；同一 `(vendor, product)` 不重复注册。"""
    manager = AdapterManager()
    manifest = manager.register(MockAdapter())
    assert manifest == MockAdapter().manifest
    assert manager.registered_keys() == (("StructAI", "MockEngineering"),)
    assert manager.manifests() == (manifest,)
    assert isinstance(manager.resolve(vendor="StructAI", product="MockEngineering"), MockAdapter)

    with pytest.raises(InternalError) as error:
        manager.register(MockAdapter())
    assert error.value.code == "STRUCTAI-7000"
    assert error.value.details["stage"] == "adapter_manager"
    assert error.value.details["vendor"] == "StructAI"
    assert manager.registered_keys() == (("StructAI", "MockEngineering"),)


def test_manifest_validation_rejects_incomplete_declarations() -> None:
    """门槛 ②：`docs/02` §19 的 Manifest 校验逐项生效（缺一即拒绝）。"""
    good = MockAdapter().manifest
    assert good.validate() is good

    base: dict[str, Any] = {
        "name": "structai.mock",
        "vendor": "StructAI",
        "product": "MockEngineering",
        "supported_versions": ("1.0",),
        "protocols": ("IN_PROCESS",),
    }
    broken_manifests = (
        AdapterManifest(**{**base, "name": ""}),
        AdapterManifest(**{**base, "vendor": "   "}),
        AdapterManifest(**{**base, "product": ""}),
        AdapterManifest(**{**base, "supported_versions": ()}),
        AdapterManifest(**{**base, "protocols": ()}),
        AdapterManifest(**{**base, "protocols": ("in_process",)}),
        AdapterManifest(**{**base, "capabilities": ("model.node.write",)}),
    )
    for manifest in broken_manifests:
        with pytest.raises(InternalError) as error:
            manifest.validate()
        assert error.value.code == "STRUCTAI-7000"
        assert error.value.details["stage"] == "adapter_manifest"

    class _NoProduct(MockAdapter):
        """缺 `product` 的 Adapter（注册期即拒绝）。"""

        product = ""

    with pytest.raises(InternalError):
        AdapterManager().register(_NoProduct())

    assert AdapterManifest(**{**base, "capabilities": ()}).validate().capabilities == ()


def test_manifest_version_matching_is_strict() -> None:
    """门槛 ②：版本匹配**严格精确**（`docs/02` §20：不得偷偷回落）。"""
    manifest = AdapterManifest(
        name="structai.mock",
        vendor="StructAI",
        product="MockEngineering",
        supported_versions=("2025", "2026"),
        protocols=("REST",),
    )
    assert manifest.supports_version("2025") is True
    assert manifest.supports_version("2026") is True
    assert manifest.supports_version("2027") is False
    assert manifest.supports_version("2026.0") is False
    assert manifest.matches(vendor="StructAI", product="MockEngineering") is True
    assert manifest.matches(vendor="StructAI", product="Mock") is False


def test_resolve_unknown_adapter_fails_loudly() -> None:
    """门槛 ②：未注册 / 未绑定 → 明确失败，且**不**进 20 码信封（装配口径）。"""
    manager = AdapterManager()
    for call in (
        lambda: manager.resolve(vendor="StructAI", product="MockEngineering"),
        lambda: manager.bind_instance("instance-1", vendor="StructAI", product="MockEngineering"),
        lambda: manager.unregister(vendor="StructAI", product="MockEngineering"),
    ):
        with pytest.raises(AdapterNotFoundError) as error:
            call()
        assert not isinstance(error.value, StructAIError)
    assert manager.registered_keys() == ()
    assert manager.bound_instance_ids() == ()


def test_bind_instance_creates_independent_adapters() -> None:
    """门槛 ②：每个软件实例拿到**独立**的 Adapter 实例（`docs/02` §14 / §54）。"""
    manager = _new_manager()
    first = manager.bind_instance(
        "instance-a", vendor=MockAdapter.vendor, product=MockAdapter.product
    )
    second = manager.bind_instance(
        "instance-b", vendor=MockAdapter.vendor, product=MockAdapter.product
    )
    assert isinstance(first, MockAdapter)
    assert isinstance(second, MockAdapter)
    assert first is not second
    assert first.store is not second.store
    assert manager.bound_instance_ids() == ("instance-a", "instance-b")
    assert manager.adapter_for_instance("instance-a") is first
    assert (
        manager.bind_instance("instance-a", vendor=MockAdapter.vendor, product=MockAdapter.product)
        is first
    )

    manager.register(_BrokenAdapter())
    with pytest.raises(InternalError) as error:
        manager.bind_instance("instance-a", vendor="StructAI", product="BrokenEngineering")
    assert error.value.details["instance_id"] == "instance-a"

    assert manager.unbind_instance("instance-a") is True
    assert manager.unbind_instance("instance-a") is False
    assert manager.bound_instance_ids() == ("instance-b",)


def test_unknown_instance_fails_loudly_in_lookup_and_runtime_paths() -> None:
    """门槛 ②：未知实例在查找 / 生命周期 / 执行路径上都**明确失败**。"""

    async def _run() -> None:
        manager = _new_manager()
        with pytest.raises(AdapterNotFoundError):
            manager.adapter_for_instance("ghost")
        with pytest.raises(AdapterNotFoundError):
            await manager.resolve_for_instance("ghost")
        with pytest.raises(AdapterNotFoundError):
            await manager.health_check("ghost")
        with pytest.raises(AdapterNotFoundError):
            await manager.connect("ghost")
        with pytest.raises(AdapterNotFoundError):
            await manager.detect_capabilities("ghost")
        with pytest.raises(AdapterNotFoundError):
            await manager.cancel("ghost", "task-1")

        context = _context(_identity(user_id=UUID(int=1), tenant_id=UUID(int=2)))
        with pytest.raises(CapabilityError) as error:
            await manager.execute("ghost", "MODEL.NODE.QUERY", {}, context)
        assert error.value.code == "STRUCTAI-3000"
        assert error.value.details["reason"] == "adapter_instance_not_bound"
        assert "ghost" not in str(error.value.details)
        assert manager.runtime_capabilities("ghost") is None

    asyncio.run(_run())


def test_manager_requires_a_ready_adapter_to_execute() -> None:
    """门槛 ②：绑定但**未就绪** → `STRUCTAI-3000`；就绪后同一调用成功。"""

    async def _run() -> None:
        manager = _new_manager()
        manager.bind_instance("instance-x", vendor=MockAdapter.vendor, product=MockAdapter.product)
        context = _context(_identity(user_id=UUID(int=1), tenant_id=UUID(int=2)))

        with pytest.raises(CapabilityError) as error:
            await manager.execute("instance-x", "MODEL.NODE.QUERY", {}, context)
        assert error.value.details["reason"] == "adapter_not_ready"
        assert error.value.details["state"] == "CREATED"

        await manager.connect("instance-x")
        result = await manager.execute("instance-x", "MODEL.NODE.QUERY", {}, context)
        assert tuple(result) == MOCK_QUERY_KEYS

    asyncio.run(_run())


def test_single_instance_failure_does_not_break_the_manager() -> None:
    """门槛 ②：单实例失败**不得**让整个 Manager 不可用（`docs/07` §14.4）。"""

    async def _run() -> None:
        manager = _new_manager()
        manager.register(_BrokenAdapter())
        manager.bind_instance("good", vendor=MockAdapter.vendor, product=MockAdapter.product)
        manager.bind_instance("broken", vendor="StructAI", product="BrokenEngineering")

        results = await manager.connect_all()
        assert results["good"]["healthy"] is True
        assert results["broken"]["code"] == "STRUCTAI-2000"
        assert tuple(results["broken"]) == ERROR_ENVELOPE_KEYS

        health = await manager.health_check_all()
        assert health["good"]["healthy"] is True
        assert health["broken"]["healthy"] is False
        assert health["broken"]["state"] == "ERROR"

        context = _context(_identity(user_id=UUID(int=1), tenant_id=UUID(int=2)))
        result = await manager.execute("good", "MODEL.NODE.QUERY", {}, context)
        assert tuple(result) == MOCK_QUERY_KEYS
        with pytest.raises(CapabilityError) as error:
            await manager.execute("broken", "MODEL.NODE.QUERY", {}, context)
        assert error.value.code == "STRUCTAI-3000"

    asyncio.run(_run())


def test_manager_health_check_never_raises() -> None:
    """门槛 ②：`health_check_all()` / `disconnect_all()` **永不**抛出（`docs/02` §52 / §53）。"""

    async def _run() -> None:
        manager = _new_manager()
        manager.register(_BrokenAdapter())
        manager.bind_instance("good", vendor=MockAdapter.vendor, product=MockAdapter.product)
        manager.bind_instance("broken", vendor="StructAI", product="BrokenEngineering")

        health = await manager.health_check_all()
        assert tuple(health) == ("broken", "good")
        assert health["broken"] == {
            "healthy": False,
            "state": "ERROR",
            "error": {"type": "RuntimeError"},
        }
        assert tuple(health["good"]) == HEALTH_KEYS
        assert health["good"]["healthy"] is False
        assert health["good"]["state"] == "CREATED"

        await manager.disconnect_all()
        assert (await manager.health_check_all())["broken"]["healthy"] is False

    asyncio.run(_run())


def test_manager_writes_nothing_to_the_database(seeded_engine: AsyncEngine) -> None:
    """门槛 ②：注册 / 绑定 / 连接 / 健康 / 执行路径**零 SQL**（`docs/07` §14.4）。"""

    async def _run() -> None:
        statements = _recorded_statements(seeded_engine)
        manager = _new_manager()
        manager.bind_instance("instance-db", vendor=MockAdapter.vendor, product=MockAdapter.product)
        await manager.connect("instance-db")
        await manager.health_check_all()
        await manager.detect_capabilities("instance-db")
        await manager.execute(
            "instance-db",
            "BUILD.COLUMN",
            {"base_node": {"x": 0, "y": 0, "z": 0}, "height": 6},
            _context(_identity(user_id=UUID(int=1), tenant_id=UUID(int=2))),
        )
        await manager.disconnect_all()
        assert statements == []
        assert _write_verbs(statements) == []

    asyncio.run(_run())


def test_manager_exposes_runtime_capabilities_and_detects_on_demand() -> None:
    """门槛 ②：运行时能力快照在连接时建立、断开后消失（`docs/02` §21 / §23）。"""

    async def _run() -> None:
        manager = _new_manager()
        manager.bind_instance(
            "instance-cap", vendor=MockAdapter.vendor, product=MockAdapter.product
        )
        assert manager.runtime_capabilities("instance-cap") is None

        await manager.connect("instance-cap")
        assert manager.runtime_capabilities("instance-cap") == frozenset(MOCK_CAPABILITIES_SPEC)
        assert sorted(await manager.detect_capabilities("instance-cap")) == sorted(
            MOCK_CAPABILITIES_SPEC
        )

        await manager.disconnect("instance-cap")
        assert manager.runtime_capabilities("instance-cap") is None
        assert await manager.detect_capabilities("instance-cap") == list(MOCK_CAPABILITIES_SPEC)

    asyncio.run(_run())


def test_unregister_requires_unbinding_first() -> None:
    """门槛 ②：仍有实例绑定 → 拒绝注销；解绑后可注销。"""
    manager = _new_manager()
    manager.bind_instance("instance-u", vendor=MockAdapter.vendor, product=MockAdapter.product)
    with pytest.raises(InternalError) as error:
        manager.unregister(vendor=MockAdapter.vendor, product=MockAdapter.product)
    assert error.value.details["instances"] == ["instance-u"]

    manager.unbind_instance("instance-u")
    manager.unregister(vendor=MockAdapter.vendor, product=MockAdapter.product)
    assert manager.registered_keys() == ()
    assert manager.manifests() == ()


def test_resolve_for_instance_uses_the_software_lookup() -> None:
    """门槛 ②：`docs/02` §56 的 `resolve_for_instance` 经软件仓储确认实例存在。"""

    async def _run() -> None:
        view = _instance_view("instance-s")
        manager = AdapterManager(software=_Lookup({"instance-s": view}))
        manager.register(MockAdapter())
        manager.bind_instance("instance-s", vendor=MockAdapter.vendor, product=MockAdapter.product)
        resolved = await manager.resolve_for_instance("instance-s")
        assert isinstance(resolved, MockAdapter)

        with pytest.raises(LookupError) as error:
            await manager.resolve_for_instance("instance-missing")
        assert "Software instance not found" in str(error.value)
        assert not isinstance(error.value, StructAIError)

    asyncio.run(_run())


def test_manager_instance_errors_are_normalized_envelopes() -> None:
    """门槛 ②/③：实例失败记入 20 码信封，且只在 `instance_errors()` 里出现。"""

    async def _run() -> None:
        manager = _new_manager()
        manager.register(_BrokenAdapter())
        manager.bind_instance("broken-2", vendor="StructAI", product="BrokenEngineering")

        with pytest.raises(StructAIError) as error:
            await manager.connect("broken-2")
        assert error.value.code == "STRUCTAI-2000"
        assert error.value.retryable is True

        envelopes = manager.instance_errors()
        assert tuple(envelopes) == ("broken-2",)
        assert tuple(envelopes["broken-2"]) == ERROR_ENVELOPE_KEYS
        assert envelopes["broken-2"]["code"] == "STRUCTAI-2000"
        assert envelopes["broken-2"]["type"] == "SOFTWARE_CONNECTION_ERROR"
        assert envelopes["broken-2"]["details"]["reason"] == "connect refused"

        manager.unbind_instance("broken-2")
        assert manager.instance_errors() == {}

    asyncio.run(_run())


def test_manager_never_records_connection_config() -> None:
    """门槛 ⑧：连接配置（可能含凭据）只经内存传递，**绝不**进 repr / 错误信封。"""
    secret = "SECRET-VALUE-42"
    manager = _new_manager()
    manager.bind_instance(
        "instance-secret",
        vendor=MockAdapter.vendor,
        product=MockAdapter.product,
        config={"api_key": secret},
    )
    assert secret not in repr(manager.instances())
    assert secret not in str(manager.instance_errors())
    assert manager.instance_errors() == {}

    async def _run() -> None:
        manager.register(_BrokenAdapter())
        manager.bind_instance(
            "broken-3",
            vendor="StructAI",
            product="BrokenEngineering",
            config={"api_key": secret},
        )
        with pytest.raises(StructAIError):
            await manager.connect("broken-3")
        assert secret not in repr(manager.instance_errors())
        assert secret not in repr(manager.instances())

    asyncio.run(_run())


# ===== ③ 错误归一化（`docs/07` §11；`docs/02` §49 / §50）=====


def test_native_errors_map_to_the_twenty_code_contract() -> None:
    """门槛 ③：原生异常族 → 20 码的映射与 `docs/02` §49 / §50 逐条一致。"""
    for error_class, code, error_type, retryable in NATIVE_ERROR_MAPPING_SPEC:
        envelope = normalize_error(error_class("native exploded"))
        assert tuple(envelope) == ERROR_ENVELOPE_KEYS
        assert envelope["code"] == code
        assert envelope["type"] == error_type
        assert envelope["retryable"] is retryable
        assert envelope["code"] in TWENTY_CODE_CONTRACT
        assert envelope["message"] == error_class.default_message
        assert "native exploded" not in envelope["message"]

    fallback = normalize_error(RuntimeError("native exploded"))
    assert fallback["code"] == "STRUCTAI-6000"
    assert fallback["message"] == FALLBACK_ADAPTER_MESSAGE
    assert fallback["details"] == {}
    assert fallback["retryable"] is False


def test_error_normalization_never_leaks_native_messages_or_secrets() -> None:
    """门槛 ③/⑧：归一化**不泄露**原生 message / 凭据（`docs/07` §14.3）。"""
    secret = "abc123"
    samples = (
        RuntimeError(f"native failure with {secret}"),
        AdapterAuthenticationError(f"credential {secret}"),
        AdapterAPIError("business failure", details={"api_key": secret, "native_code": "E42"}),
        AdapterTimeoutError("timeout", details={"password": secret, "timeout_ms": 5000}),
    )
    for error in samples:
        envelope = normalize_error(error)
        assert tuple(envelope) == ERROR_ENVELOPE_KEYS
        assert secret not in str(envelope)

    api = normalize_error(
        AdapterAPIError("business failure", details={"api_key": secret, "native_code": "E42"})
    )
    assert "api_key" not in api["details"]
    assert api["details"]["native_code"] == "E42"
    assert (
        normalize_error(AdapterAuthenticationError(f"credential {secret}"))["details"]["reason"]
        == REDACTION_MARKER
    )
    assert "password" in SENSITIVE_DETAIL_KEY_PARTS


def test_error_normalization_is_idempotent_for_structai_errors() -> None:
    """门槛 ③：已是 `StructAIError` 的异常原样透传（既有码语义不被重写）。"""
    for error in (
        TenantAccessDeniedError("Tenant access denied"),
        ResourceLockedError("Resource locked"),
        CapabilityError("Capability not supported"),
    ):
        assert normalize_error(error) == error.to_dict()

    restored = error_for(normalize_error(AdapterConnectionError("refused")))
    assert normalize_error(restored)["code"] == "STRUCTAI-2000"
    assert restored.code == "STRUCTAI-2000"


def test_error_for_round_trips_and_falls_back() -> None:
    """门槛 ③：信封 → 领域异常可往返；未知码回落 `STRUCTAI-6000`。"""
    for error_class, code, _, _ in NATIVE_ERROR_MAPPING_SPEC:
        restored = error_for(normalize_error(error_class("x")))
        assert isinstance(restored, StructAIError)
        assert restored.code == code

    unknown = error_for({"code": "STRUCTAI-9999", "message": "?"})
    assert isinstance(unknown, AdapterError)
    assert unknown.code == "STRUCTAI-6000"


def test_mock_adapter_normalize_error_delegates_to_the_single_point() -> None:
    """门槛 ③：Adapter 的 `normalize_error` 就是那一个归一化点（不得各写一套）。"""
    adapter = MockAdapter()
    for error in (AdapterValidationError("duplicate"), RuntimeError("boom")):
        assert adapter.normalize_error(error) == normalize_error(error)
    timeout = AdapterTimeoutError("t")
    assert BaseAdapter.normalize_error(adapter, timeout) == normalize_error(timeout)


def test_raise_normalized_raises_a_domain_error_with_cause() -> None:
    """门槛 ③：归一化出口抛领域异常，且保留 `__cause__` 供服务端诊断。"""
    original = AdapterConnectionError("refused")
    with pytest.raises(StructAIError) as error:
        raise_normalized(original)
    assert error.value.code == "STRUCTAI-2000"
    assert error.value.__cause__ is original


# ===== ④ Mock Adapter 端到端（`docs/02` §117 / §61 / §62；`docs/07` §12.1 里程碑 ①②）=====


def test_mock_e2e_sequence_from_operation_definitions(seeded_engine: AsyncEngine) -> None:
    """门槛 ④（主门槛）：`BUILD.COLUMN` 走通「OperationDefinition → execute → 规范化结果」。"""

    async def _run() -> None:
        registry = await OperationRegistry.load(
            seeded_engine, create_session_factory(seeded_engine)
        )
        assert registry is not None
        definitions = {name: registry.require(name) for name in MOCK_E2E_SEQUENCE}

        column_definition = definitions["BUILD.COLUMN"]
        assert column_definition.tool == "engineering_model_build"
        assert column_definition.input_schema == "structai://schema/build/column/v1"
        assert column_definition.output_schema == "structai://schema/build/column/result/v1"
        for name, definition in definitions.items():
            missing = [
                code for code in definition.required_capabilities if code not in MOCK_CAPABILITIES
            ]
            assert missing == [], name

        instance_id = str(UUID(int=7))
        manager, adapter = await _wired_manager(instance_id)
        context = _context(
            _identity(user_id=UUID(int=1), tenant_id=UUID(int=2)),
            software_instance_id=instance_id,
        )

        column = await manager.execute(
            instance_id,
            column_definition.name,
            {
                "base_node": {"x": 0.0, "y": 0.0, "z": 0.0},
                "height": 6.0,
                "material": "Q355B",
                "section": "H400x400x13x21",
            },
            context,
        )
        assert tuple(column) == MOCK_BUILD_COLUMN_KEYS
        base_id, top_id = column["node_ids"]
        element_id = column["element_ids"][0]

        nodes = await manager.execute(instance_id, "MODEL.NODE.QUERY", {}, context)
        assert tuple(nodes) == MOCK_QUERY_KEYS
        by_id = {item["id"]: item for item in nodes["items"]}
        assert set(by_id) == {base_id, top_id}
        assert by_id[base_id] == {"id": base_id, "x": 0.0, "y": 0.0, "z": 0.0}
        assert by_id[top_id]["z"] == 6.0
        assert adapter.store.version > 0

        elements = await manager.execute(instance_id, "MODEL.ELEMENT.QUERY", {}, context)
        assert elements["items"] == [
            {
                "id": element_id,
                "node_ids": [base_id, top_id],
                "material": "Q355B",
                "section": "H400x400x13x21",
            }
        ]

        boundary = await manager.execute(
            instance_id,
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
            context,
        )
        assert boundary["node_id"] == base_id
        assert boundary["uz"] is True

        load = await manager.execute(
            instance_id, "MODEL.LOAD.ASSIGN", {"node_id": top_id, "fz": -500000.0}, context
        )
        assert tuple(load) == MOCK_LOAD_KEYS
        assert load == {"node_id": top_id, "fx": 0.0, "fy": 0.0, "fz": -500000.0}

        analysis_result = await manager.execute(instance_id, "ANALYSIS.STATIC", {}, context)
        assert analysis_result["status"] == "COMPLETED"
        assert analysis_result["analysis_type"] == "STATIC"
        assert analysis_result["engineering_grade"] is False

        displacement = await manager.execute(
            instance_id, "RESULT.NODE.DISPLACEMENT", {"node_id": top_id}, context
        )
        expected = 500000.0 * 6.0 / (2.06e11 * 0.025)
        assert displacement["node_id"] == top_id
        assert displacement["ux"] == 0.0
        assert displacement["uz"] == pytest.approx(expected, rel=1e-9)

        design = await manager.execute(
            instance_id, "DESIGN.STEEL", {"element_id": element_id}, context
        )
        assert design == {
            "element_id": element_id,
            "utilization": 0.72,
            "status": "PASS",
            "engine": "MockEngineering",
            "engineering_grade": False,
        }

        assert set(MOCK_E2E_SEQUENCE) <= set(MOCK_SUPPORTED_OPERATIONS)

    asyncio.run(_run())


def test_build_column_accepts_both_normalized_input_shapes() -> None:
    """门槛 ④：`docs/02` §83 的 `base_node` 与 §38 的 `*_node_id` 两种入参都支持。"""

    async def _run() -> None:
        manager, adapter = await _wired_manager("instance-shapes")
        context = _context(_identity(user_id=UUID(int=1), tenant_id=UUID(int=2)))

        by_object = await manager.execute(
            "instance-shapes",
            "BUILD.COLUMN",
            {"base_node": {"x": 1.0, "y": 2.0, "z": 3.0}, "height": 4.0},
            context,
        )
        assert by_object["node_ids"] == [1, 2]
        assert by_object["element_ids"] == [1]
        first, second = adapter.store.all_nodes()
        assert (first.x, first.y, first.z) == (1.0, 2.0, 3.0)
        assert (second.x, second.y, second.z) == (1.0, 2.0, 7.0)

        by_ids = await manager.execute(
            "instance-shapes",
            "BUILD.COLUMN",
            {"base_node_id": 10, "top_node_id": 11, "height": 5.0, "material": "Q235B"},
            context,
        )
        assert by_ids["node_ids"] == [10, 11]

        reused = await manager.execute(
            "instance-shapes",
            "BUILD.COLUMN",
            {"base_node_id": 10, "top_node_id": 11, "height": 99.0},
            context,
        )
        assert reused["node_ids"] == [10, 11]
        assert adapter.store.nodes[10].z == 0.0
        assert adapter.store.nodes[11].z == 5.0
        assert len(adapter.store.all_elements()) == 3

    asyncio.run(_run())


def test_build_column_rejects_non_positive_height() -> None:
    """门槛 ④：`height` 必须为正（`docs/02` §83 的 `exclusiveMinimum: 0`）。"""

    async def _run() -> None:
        manager, adapter = await _wired_manager("instance-height")
        context = _context(_identity(user_id=UUID(int=1), tenant_id=UUID(int=2)))

        with pytest.raises(AdapterValidationError) as direct:
            await adapter.execute("BUILD.COLUMN", {"height": 0.0}, context)
        assert direct.value.reason == "Column height must be positive"

        with pytest.raises(StructAIError) as normalized:
            await manager.execute("instance-height", "BUILD.COLUMN", {"height": 0.0}, context)
        assert normalized.value.code == "STRUCTAI-1200"
        assert normalized.value.details["reason"] == "invalid_height"

    asyncio.run(_run())


def test_mock_supported_operations_are_seeded_operations(seeded_engine: AsyncEngine) -> None:
    """门槛 ④：Mock 实现的操作 ⊆ P07 落库的 69 个 Operation；能力 ⊆ 落库的 41 条。"""

    async def _run() -> None:
        factory = create_session_factory(seeded_engine)
        operation_registry = await OperationRegistry.load(seeded_engine, factory)
        capability_registry = await CapabilityRegistry.load(seeded_engine, factory)
        assert operation_registry is not None
        assert capability_registry is not None

        names = {item.name for item in await operation_registry.list()}
        assert len(names) == 69
        assert set(MOCK_SUPPORTED_OPERATIONS) <= names
        assert MOCK_SUPPORTED_OPERATIONS == MockAdapter().supported_operations()

        codes = set(capability_registry.codes())
        assert len(codes) == 41
        assert set(MOCK_CAPABILITIES) <= codes
        assert "ANALYSIS.NONLINEAR" in codes
        assert "ANALYSIS.NONLINEAR" not in MOCK_CAPABILITIES

    asyncio.run(_run())


def test_unsupported_operation_is_structai_3000() -> None:
    """门槛 ④：无 handler 的 Operation → `STRUCTAI-3000`（`docs/02` §48）。"""

    async def _run() -> None:
        manager, adapter = await _wired_manager("instance-unsupported")
        context = _context(_identity(user_id=UUID(int=1), tenant_id=UUID(int=2)))

        assert "BUILD.BEAM" not in MOCK_SUPPORTED_OPERATIONS
        with pytest.raises(CapabilityError) as error:
            await manager.execute("instance-unsupported", "BUILD.BEAM", {"height": 3.0}, context)
        assert error.value.code == "STRUCTAI-3000"
        assert error.value.details["reason"] == "unsupported_operation"
        assert error.value.details["operation"] == "BUILD.BEAM"

        with pytest.raises(AdapterCapabilityError) as native:
            await adapter.execute("BUILD.BEAM", {"height": 3.0}, context)
        assert native.value.code == "STRUCTAI-3000"

    asyncio.run(_run())


def test_invalid_parameters_are_structai_1200() -> None:
    """门槛 ④：参数 / 模型语义非法 → `STRUCTAI-1200`（`docs/02` §49）。"""

    async def _run() -> None:
        manager, _ = await _wired_manager("instance-invalid")
        context = _context(_identity(user_id=UUID(int=1), tenant_id=UUID(int=2)))

        with pytest.raises(StructAIError) as missing:
            await manager.execute("instance-invalid", "MODEL.NODE.CREATE", {}, context)
        assert missing.value.code == "STRUCTAI-1200"
        assert missing.value.details["reason"] == "missing_parameter"

        created = await manager.execute(
            "instance-invalid",
            "MODEL.NODE.CREATE",
            {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
            context,
        )
        assert created == {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0}

        with pytest.raises(StructAIError) as duplicate:
            await manager.execute(
                "instance-invalid",
                "MODEL.NODE.CREATE",
                {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
                context,
            )
        assert duplicate.value.details["reason"] == "duplicate_node"

        with pytest.raises(StructAIError) as absent:
            await manager.execute(
                "instance-invalid", "MODEL.ELEMENT.CREATE", {"node_ids": [99]}, context
            )
        assert absent.value.details["reason"] == "node_not_found"

        with pytest.raises(StructAIError) as material:
            await manager.execute(
                "instance-invalid", "MODEL.MATERIAL.ASSIGN", {"code": "NOPE"}, context
            )
        assert material.value.details["reason"] == "material_not_found"

    asyncio.run(_run())


def test_model_store_satisfies_docs_02_section_35() -> None:
    """门槛 ④：`docs/02` §35 的六项要求（协程安全 / 自动 ID / 版本 / 查 / 改 / 删）。"""

    async def _run() -> None:
        store = MockModelStore()
        assert store.summary()["version"] == 0

        first = await store.create_node(x=0.0, y=0.0, z=0.0)
        second = await store.create_node(x=1.0, y=1.0, z=1.0)
        assert (first.id, second.id) == (1, 2)
        assert store.version == 2
        assert store.node(1) == first

        updated = await store.update_node(1, z=9.0)
        assert updated.z == 9.0
        assert store.nodes[1].z == 9.0
        assert await store.delete_node(2) is True
        assert store.node(2) is None
        assert await store.delete_node(2) is False

        element = await store.create_element(
            node_ids=[1], material="Q355B", section="H400x400x13x21"
        )
        assert element.id == 1
        assert store.all_elements() == (element,)
        boundary = await store.assign_boundary(1, uz=True)
        assert boundary.uz is True
        assert store.boundary(1) == boundary
        load = await store.assign_load(1, fz=-1000.0)
        assert store.load(1) == load

        assert await store.delete_node(1) is True
        assert store.boundary(1) is None
        assert store.load(1) is None

        store.clear()
        assert store.summary()["version"] == 0
        assert store.summary()["nodes"] == 0

        created = await asyncio.gather(*(store.create_node(x=0.0, y=0.0, z=0.0) for _ in range(5)))
        assert sorted(node.id for node in created) == [1, 2, 3, 4, 5]

        material = await store.assign_material("Q355B")
        assert material.elastic_modulus == 2.06e11
        assert material.yield_strength == 355e6
        section = await store.assign_section("H400x400x13x21")
        assert section.area == 0.025
        with pytest.raises(AdapterValidationError):
            await store.assign_material("NOPE")
        with pytest.raises(AdapterValidationError):
            await store.assign_section("NOPE")

    asyncio.run(_run())


def test_mock_results_are_never_engineering_grade() -> None:
    """门槛 ④：所有 Mock 结果带 `engine` / `engineering_grade = false`（§42 / §63）。"""

    async def _run() -> None:
        manager, _ = await _wired_manager("instance-grade")
        context = _context(_identity(user_id=UUID(int=1), tenant_id=UUID(int=2)))
        column = await manager.execute(
            "instance-grade",
            "BUILD.COLUMN",
            {"base_node": {"x": 0.0, "y": 0.0, "z": 0.0}, "height": 6.0},
            context,
        )
        top_id = column["node_ids"][1]
        element_id = column["element_ids"][0]
        await manager.execute(
            "instance-grade", "MODEL.LOAD.ASSIGN", {"node_id": top_id, "fz": -1.0}, context
        )

        calls: tuple[tuple[str, dict[str, Any]], ...] = (
            ("ANALYSIS.STATIC", {}),
            ("RESULT.NODE.DISPLACEMENT", {"node_id": top_id}),
            ("RESULT.NODE.REACTION", {"node_id": top_id}),
            ("RESULT.ELEMENT.FORCE", {"element_id": element_id}),
            ("RESULT.ELEMENT.STRESS", {"element_id": element_id}),
            ("DESIGN.STEEL", {"element_id": element_id}),
        )
        for name, parameters in calls:
            result = await manager.execute("instance-grade", name, parameters, context)
            assert result["engine"] == "MockEngineering", name
            assert result["engineering_grade"] is False, name

    asyncio.run(_run())


def test_query_pagination_supports_limit_and_cursor() -> None:
    """门槛 ④：查询默认形状照抄 §35；可选 `limit` / `cursor` 使 payload 有界（§14.4）。"""

    async def _run() -> None:
        manager, adapter = await _wired_manager("instance-page")
        context = _context(_identity(user_id=UUID(int=1), tenant_id=UUID(int=2)))
        for index in range(5):
            await adapter.store.create_node(x=float(index), y=0.0, z=0.0)

        page = await manager.execute("instance-page", "MODEL.NODE.QUERY", {"limit": 2}, context)
        assert [item["id"] for item in page["items"]] == [1, 2]
        assert page["pagination"] == {"has_more": True, "next_cursor": 2}

        second_page = await manager.execute(
            "instance-page", "MODEL.NODE.QUERY", {"limit": 2, "cursor": 2}, context
        )
        assert [item["id"] for item in second_page["items"]] == [3, 4]
        assert second_page["pagination"] == {"has_more": True, "next_cursor": 4}

        last_page = await manager.execute(
            "instance-page", "MODEL.NODE.QUERY", {"limit": 2, "cursor": 4}, context
        )
        assert [item["id"] for item in last_page["items"]] == [5]
        assert last_page["pagination"] == {"has_more": False, "next_cursor": None}

        everything = await manager.execute("instance-page", "MODEL.NODE.QUERY", {}, context)
        assert len(everything["items"]) == 5
        assert everything["pagination"] == {"has_more": False, "next_cursor": None}

        with pytest.raises(StructAIError) as error:
            await manager.execute("instance-page", "MODEL.NODE.QUERY", {"limit": 0}, context)
        assert error.value.code == "STRUCTAI-1200"

    asyncio.run(_run())


# ===== ⑤ Capability 联动（`docs/07` §16 R30；`docs/02` §21 / §23 / §45 / §57）=====


def test_capability_resolver_yields_supported_and_unsupported(
    seeded_engine: AsyncEngine,
) -> None:
    """门槛 ⑤：运行时清单接入 `status_of()`，**首次**产出 `UNSUPPORTED`。"""

    async def _run() -> None:
        registry = await CapabilityRegistry.load(
            seeded_engine, create_session_factory(seeded_engine)
        )
        assert registry is not None
        instance_id = str(UUID(int=11))
        manager, _ = await _wired_manager(instance_id)
        resolver = CapabilityResolver(registry, runtime=manager)
        instance = _instance_record(instance_id)

        assert resolver.status_of(instance, "MODEL.NODE.WRITE") is CapabilityStatus.SUPPORTED
        assert resolver.status_of(instance, "MODEL.NODE.READ") is CapabilityStatus.SUPPORTED
        assert resolver.status_of(instance, "DESIGN.STEEL") is CapabilityStatus.SUPPORTED
        assert resolver.status_of(instance, "ANALYSIS.NONLINEAR") is CapabilityStatus.UNSUPPORTED
        assert resolver.status_of(instance, "RESULT.MODE_SHAPE") is CapabilityStatus.UNSUPPORTED
        assert resolver.status_of(instance, "MODEL.NOPE.NOPE") is CapabilityStatus.UNKNOWN

        disconnected = _instance_record(
            instance_id, status=SoftwareConnectionState.DISCONNECTED.value
        )
        assert resolver.status_of(disconnected, "MODEL.NODE.WRITE") is CapabilityStatus.UNKNOWN

        unbound = _instance_record(str(UUID(int=12)))
        assert resolver.status_of(unbound, "MODEL.NODE.WRITE") is CapabilityStatus.UNKNOWN

    asyncio.run(_run())


def test_capability_resolver_without_runtime_never_reports_unsupported(
    seeded_engine: AsyncEngine,
) -> None:
    """门槛 ⑤：未注入运行时来源时行为与 P14–P18 完全一致（`UNSUPPORTED` 不出现）。"""

    async def _run() -> None:
        registry = await CapabilityRegistry.load(
            seeded_engine, create_session_factory(seeded_engine)
        )
        assert registry is not None
        resolver = CapabilityResolver(registry)
        instance_id = str(UUID(int=11))
        instance = _instance_record(instance_id)

        assert resolver.status_of(instance, "MODEL.NODE.WRITE") is CapabilityStatus.SUPPORTED
        assert resolver.status_of(instance, "ANALYSIS.NONLINEAR") is CapabilityStatus.SUPPORTED
        assert resolver.status_of(instance, "MODEL.NOPE.NOPE") is CapabilityStatus.UNKNOWN

        disconnected = _instance_record(
            instance_id, status=SoftwareConnectionState.DISCONNECTED.value
        )
        assert resolver.status_of(disconnected, "MODEL.NODE.WRITE") is CapabilityStatus.UNKNOWN

    asyncio.run(_run())


def test_runtime_capabilities_are_none_when_unbound_or_disconnected(
    seeded_engine: AsyncEngine,
) -> None:
    """门槛 ⑤：「探测不到」与「明确不支持」严格区分（`docs/02` §21 / §47）。"""

    async def _run() -> None:
        registry = await CapabilityRegistry.load(
            seeded_engine, create_session_factory(seeded_engine)
        )
        assert registry is not None
        instance_id = str(UUID(int=14))
        manager, _ = await _wired_manager(instance_id, connect=False)
        resolver = CapabilityResolver(registry, runtime=manager)
        instance = _instance_record(instance_id)

        assert manager.runtime_capabilities(instance_id) is None
        assert resolver.status_of(instance, "MODEL.NODE.WRITE") is CapabilityStatus.UNKNOWN

        await manager.connect(instance_id)
        assert resolver.status_of(instance, "MODEL.NODE.WRITE") is CapabilityStatus.SUPPORTED

        await manager.disconnect(instance_id)
        assert manager.runtime_capabilities(instance_id) is None
        assert resolver.status_of(instance, "MODEL.NODE.WRITE") is CapabilityStatus.UNKNOWN

    asyncio.run(_run())


def test_check_rejects_an_operation_with_an_unsupported_capability(
    seeded_engine: AsyncEngine,
) -> None:
    """门槛 ⑤：`check()` 是 ALL 语义；缺口来自运行时清单（`docs/02` §46 / §47）。"""

    async def _run() -> None:
        factory = create_session_factory(seeded_engine)
        capabilities = await CapabilityRegistry.load(seeded_engine, factory)
        operations = await OperationRegistry.load(seeded_engine, factory)
        assert capabilities is not None
        assert operations is not None

        instance_id = str(UUID(int=15))
        manager, _ = await _wired_manager(instance_id)
        resolver = CapabilityResolver(capabilities, runtime=manager)
        instance = _instance_record(instance_id)
        context = _context(
            _identity(user_id=UUID(int=1), tenant_id=UUID(int=2)),
            software_instance_id=instance_id,
        )

        column = await resolver.check(
            context, operations.require("BUILD.COLUMN"), instance=instance
        )
        assert column.ok is True
        assert column.supported == ("MODEL.NODE.WRITE", "MODEL.ELEMENT.WRITE")
        assert column.unsupported == ()
        assert column.missing == ()
        assert column.cache_hits == 0

        cached = await resolver.check(
            context, operations.require("BUILD.COLUMN"), instance=instance
        )
        assert cached.cache_hits == 2

        with pytest.raises(CapabilityError) as error:
            await resolver.check(
                context, operations.require("ANALYSIS.NONLINEAR"), instance=instance
            )
        assert error.value.code == "STRUCTAI-3000"
        assert error.value.details["missing"] == ["ANALYSIS.NONLINEAR"]
        assert error.value.details["statuses"] == ["UNSUPPORTED"]

    asyncio.run(_run())


def test_runtime_capability_vocabulary_comes_only_from_the_seeded_table(
    seeded_engine: AsyncEngine,
) -> None:
    """门槛 ⑤/⑧：能力码只来自落库的 41 条（`docs/07` §14.2）。"""

    async def _run() -> None:
        registry = await CapabilityRegistry.load(
            seeded_engine, create_session_factory(seeded_engine)
        )
        assert registry is not None
        codes = set(registry.codes())
        assert len(codes) == 41
        assert set(MOCK_CAPABILITIES) <= codes
        assert sorted(codes) == sorted({str(code) for code in registry.codes()})

        instance_id = str(UUID(int=16))
        manager, _ = await _wired_manager(instance_id)
        runtime = manager.runtime_capabilities(instance_id)
        assert runtime is not None
        assert runtime <= codes

    asyncio.run(_run())


def test_runtime_capability_source_is_a_structural_contract() -> None:
    """门槛 ⑤：Application 侧只依赖收窄契约（**不**依赖 Infrastructure 实现）。"""
    source = AdapterManager()
    assert callable(source.runtime_capabilities)
    assert not inspect.iscoroutinefunction(AdapterManager.runtime_capabilities)
    assert source.runtime_capabilities("nope") is None
    assert RuntimeCapabilitySource.__name__ == "RuntimeCapabilitySource"

    manager_modules = _imported_modules(
        _relative_path("app/infrastructure/adapters/base/manager.py")
    )
    assert "app.application.services.capability_resolver" not in manager_modules
    resolver_modules = _imported_modules(
        _relative_path("app/application/services/capability_resolver.py")
    )
    assert [module for module in resolver_modules if module.startswith("app.infrastructure")] == []


# ===== ⑥ 回归（`python -m app.main` / P04 / P02）=====


def test_batch_id_is_a_batch_marker() -> None:
    """`container.BATCH_ID` 是形如 `Pnn` 的批次口径，且**不回退**（`docs/08` §3）。

    ⚠️ P21 收尾时本用例由「恰好等于 `P19`」改为**与具体批次无关**：批次号每批都推进
    （`docs/08` §1 的交接协议），把上一批的批号写死会让每一批都必须改上一批的测试文件
    （P09 / P14 / P19 已连续三次如此）。批次是否已推进由 `docs/08` §3 状态表与
    `tests/test_idempotency_p21.py` 的 `test_batch_id_is_the_p21_batch_marker` 负责。
    """
    assert re.fullmatch(r"P\d{2}", BATCH_ID)
    assert int(BATCH_ID[1:]) >= 19


def test_main_exits_zero_with_empty_stdout_on_an_unprovisioned_database(
    tmp_path: Path,
) -> None:
    """门槛 ⑥：未配备库上 `python -m app.main` 退出码 0 且 **stdout 0 字节**。"""
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p19_unprovisioned.db').as_posix()}"
    completed = _run_main(database_url)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert f"batch={BATCH_ID}" in completed.stderr


def test_main_exits_zero_with_empty_stdout_on_a_provisioned_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ⑥：已配备库上 `python -m app.main` 退出码 0 且 **stdout 0 字节**。"""
    database_url = asyncio.run(_provision(tmp_path, monkeypatch))
    completed = _run_main(database_url)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert "registry ready" in completed.stderr


def test_p04_tables_and_select_one_are_not_regressed(seeded_engine: AsyncEngine) -> None:
    """门槛 ⑥（P04）：建表 **24** 张 + `SELECT 1` → 1（本批**未**改表）。"""

    async def _run() -> None:
        async with seeded_engine.connect() as connection:
            names = set(
                await connection.run_sync(
                    lambda sync_connection: sa_inspect(sync_connection).get_table_names()
                )
            )
            assert len(names) == 24
            assert len(Base.metadata.tables) == 24
            result = await connection.exec_driver_sql("SELECT 1")
            assert result.scalar_one() == 1

    asyncio.run(_run())


def test_p02_settings_override_is_not_regressed(monkeypatch: pytest.MonkeyPatch) -> None:
    """门槛 ⑥（P02）：环境变量覆盖默认值（本批**未**新增 Settings 字段）。"""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./data/p19_gate.db")
    monkeypatch.setenv("CAPABILITY_CACHE_SECONDS", "88")

    overridden = Settings()

    assert overridden.log_level == "DEBUG"
    assert overridden.database_url == "sqlite+aiosqlite:///./data/p19_gate.db"
    assert overridden.capability_cache_seconds == 88


# ===== ⑦ 质量与结构（`docs/07` §3.1 / §3.3 / §14）=====


def test_technology_stack_is_frozen() -> None:
    """门槛 ⑦：依赖清单未扩（`docs/07` §3.1 / §3.2：不得引入新依赖）。"""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = {
        re.split(r"[<>=!\[;]", dependency.strip())[0].strip().lower()
        for dependency in pyproject["project"]["dependencies"]
    }
    assert declared == set(FROZEN_DEPENDENCIES)


def test_container_shape_stays_frozen() -> None:
    """门槛 ⑦：容器字段仍为 `docs/02` §33 的冻结形状（适配器**不**进容器）。"""
    names = [field.name for field in fields(AppContainer)]
    assert names == [
        "settings",
        "runtime_config",
        "engine",
        "session_factory",
        "operation_registry",
        "execution_service",
        "started",
    ]
    assert [name for name in names if "adapter" in name] == []


def test_p19_modules_exist_and_are_exported() -> None:
    """门槛 ⑦：`docs/07` §3.3 冻结结构中的 7 个新模块 + 3 个包入口全部存在。"""
    for relative in (*P19_MODULES, *P19_PACKAGES):
        assert _relative_path(relative).is_file(), relative

    assert {path.name for path in BASE_DIR.glob("*.py")} == {
        "adapter.py",
        "manifest.py",
        "errors.py",
        "manager.py",
        "__init__.py",
    }
    assert {path.name for path in MOCK_DIR.glob("*.py")} == {
        "adapter.py",
        "model_store.py",
        "analysis.py",
        "__init__.py",
    }


def test_p19_modules_never_commit() -> None:
    """门槛 ⑦：新模块不得 `commit` / `rollback`（边界归 `UnitOfWork`，§14.4）。"""
    for relative in P19_MODULES:
        assert _commit_or_rollback_calls(_relative_path(relative)) == [], relative


def test_application_services_do_not_depend_on_infrastructure() -> None:
    """门槛 ⑦：Application 层不依赖 `app.infrastructure`（`docs/07` §14.1 / §2.2）。"""
    for relative in (
        "app/application/services/capability_resolver.py",
        "app/application/services/__init__.py",
    ):
        offenders = [
            module
            for module in _imported_modules(_relative_path(relative))
            if module.startswith("app.infrastructure")
            or module.split(".")[0] in FORBIDDEN_FRAMEWORK_ROOTS
        ]
        assert offenders == [], relative


# ===== ⑧ 红线（`docs/07` §14）=====


def test_twenty_code_contract_is_not_extended() -> None:
    """门槛 ⑧：20 码契约不扩（本批复用既有的 1200 / 2000 / 2100 / 2200 / 2300 / 3000 / 6000）。"""
    from app.domain import errors as errors_module

    assert len(TWENTY_CODE_CONTRACT) == 20
    derived = [
        name
        for name, value in vars(errors_module).items()
        if isinstance(value, type)
        and issubclass(value, StructAIError)
        and value is not StructAIError
    ]
    assert len(derived) == 20
    for code, exception in (
        ("STRUCTAI-1200", AdapterValidationError),
        ("STRUCTAI-2000", AdapterConnectionError),
        ("STRUCTAI-2100", AdapterAuthenticationError),
        ("STRUCTAI-2200", AdapterAPIError),
        ("STRUCTAI-2300", AdapterTimeoutError),
        ("STRUCTAI-3000", AdapterCapabilityError),
    ):
        assert exception.code == code
        assert code in TWENTY_CODE_CONTRACT


def test_no_new_structai_error_code_anywhere_in_app() -> None:
    """门槛 ⑧：`app/` 内出现的 `STRUCTAI-xxxx` 字面量只能是那 20 个码。"""
    declared: set[str] = set()
    for path in sorted(APP_DIR.rglob("*.py")):
        declared.update(re.findall(r"STRUCTAI-\d{4}", path.read_text(encoding="utf-8")))
    assert declared == set(TWENTY_CODE_CONTRACT)


def test_red_lines_vendor_names_and_domain_purity() -> None:
    """门槛 ⑧：`app/` 内厂商名 0 处；`app/domain/` 内无 SQLAlchemy。"""
    vendor_hits = [
        f"{path.relative_to(REPO_ROOT).as_posix()}:{vendor}"
        for path in sorted(APP_DIR.rglob("*.py"))
        if "midas" not in path.parts  # docs/07 §7.1：厂商专属代码的唯一豁免区
        for vendor in VENDOR_NAMES
        if vendor.lower() in path.read_text(encoding="utf-8").lower()
    ]
    assert vendor_hits == []

    domain_hits = [
        path.name
        for path in sorted((APP_DIR / "domain").glob("*.py"))
        if "sqlalchemy" in path.read_text(encoding="utf-8").lower()
    ]
    assert domain_hits == []


def test_domain_stays_free_of_frameworks() -> None:
    """门槛 ⑧：`app/domain/` 不得引用 SQLAlchemy / FastAPI / MCP SDK（`docs/07` §14.1）。"""
    offenders: list[str] = []
    for path in sorted((APP_DIR / "domain").glob("*.py")):
        for module in _imported_modules(path):
            if module.split(".")[0] in FORBIDDEN_FRAMEWORK_ROOTS:
                offenders.append(f"{path.name} -> {module}")
    assert offenders == []


def test_settings_fields_are_registered_in_env_example() -> None:
    """门槛 ⑧：每个 Settings 字段都在 `.env.example` 登记（本批未新增字段）。"""
    registered = set(
        re.findall(
            r"^([A-Z0-9_]+)=",
            (REPO_ROOT / ".env.example").read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
    )
    declared = {name.upper() for name in Settings.model_fields}
    assert declared <= registered


def test_adapter_native_errors_carry_no_structai_code_of_their_own() -> None:
    """门槛 ⑧：原生异常族**不**继承 `StructAIError`、也**不**自造码（装配期口径）。"""
    assert not issubclass(AdapterNativeError, StructAIError)
    for error_class, code, _, _ in NATIVE_ERROR_MAPPING_SPEC:
        assert issubclass(error_class, AdapterNativeError)
        assert code in TWENTY_CODE_CONTRACT

    not_found = AdapterNotFoundError("Adapter not found")
    assert isinstance(not_found, LookupError)
    assert not isinstance(not_found, StructAIError)
    assert not hasattr(not_found, "code")


def test_secrets_never_appear_in_adapter_envelopes() -> None:
    """门槛 ⑧：**绝不记录 secret**（`docs/07` §14.3）—— 归一化信封逐条核验。"""
    secret = "S3CR3T"
    samples = (
        RuntimeError(f"native failure with {secret}"),
        AdapterAuthenticationError(f"invalid credential {secret}"),
        AdapterAPIError(f"api_key={secret}", details={"password": secret, "native_code": "E1"}),
        AdapterTimeoutError("timeout", details={"token": secret}),
    )
    for error in samples:
        envelope = normalize_error(error)
        assert secret not in str(envelope), error
        assert secret not in repr(error_for(envelope)), error
        assert secret not in str(error.to_dict()) if isinstance(error, StructAIError) else True

    dropped = normalize_error(
        AdapterAPIError("x", details={part: "value" for part in SENSITIVE_DETAIL_KEY_PARTS})
    )
    assert [key for key in dropped["details"] if key in SENSITIVE_DETAIL_KEY_PARTS] == []
    assert dropped["details"] == {"reason": "x"}

    for _, code, _, _ in NATIVE_ERROR_MAPPING_SPEC:
        assert code in TWENTY_CODE_CONTRACT
    assert AdapterError.code == "STRUCTAI-6000"
