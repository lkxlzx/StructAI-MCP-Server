"""P14–P18 验收测试：Execution Foundation（`docs/07` §12 P14–P18；`docs/02` §116 / §117）。

验收点（与续接提示词的 ①–⑧ 一一对应）：

① 主门槛（`docs/07` §12 P14–P18 / `docs/02` §116）：`ResourceResolver` 把
   `project_id` / `model_id` / `document_id` / `software_instance_id` 解析成
   `ResourceContext`（`docs/02` §73 的 `ResolvedResource`），且**跨租户 → `STRUCTAI-4200`**
   （`docs/07` §9 第 7 步：跨租户唯一拦截点，必须最先）；`ExecutionContext` **只能由 Core
   构造**，客户端提供的 `context.identity` / `user_id` / `tenant_id` / `roles` /
   `permissions` 一律忽略（`docs/07` §8.1 / §14.3）；
② 顺序冻结（`docs/02` §13 / §30 / §67–§70）：`Schema Validation` **先于**
   `Engineering Validation`；`Permission` **先于** `Capability`；`Postconditions` **先于**
   `Release Lock`；且工程语义**不得**塞回 Schema 层；
③ Lock（`docs/02` §36–§42）：按资源键互斥，冲突 → **`STRUCTAI-6100`**（`docs/07` §11）；
   `LockPolicy` 的兼容矩阵逐条可查；
④ Capability（`docs/02` §43–§48）：以「实例 + 版本 + 能力码」判定，未知 / 不支持 →
   **`STRUCTAI-3000`**（`docs/07` §11）；取值只来自 P07 落库的 `capabilities`（41 条），
   **不得**在代码里另造能力码（`docs/07` §14.2）；
⑤ Confirmation（`docs/07` §8.4；`docs/02` §34–§39）：server-generated / 短期 /
   绑定 user + tenant + operation + resource / 一次性；缺 token → **`STRUCTAI-4100`**；
   **禁止**固定字符串；验证成功即消费；过期 / 跨用户 / 跨租户 / 跨 operation / 跨 resource
   全部拒绝；
⑥ 回归：`python -m app.main` 退出码 0（**stdout 0 字节**；未配备库与已配备库两种情形）、
   P04 建表 24 张 / `SELECT 1`、P02 覆盖行为、既有 **152 项 pytest 不得回退**
   （由整轮 `pytest -q` 覆盖；本文件只补 `app.main` 两条）；
⑦ 质量：`ruff` / `mypy` 覆盖；本文件额外断言依赖清单**未扩**、容器形状**未变**、
   Application 新层**不依赖** Infrastructure、新模块**不得 `commit`**；
⑧ 红线：`app/` 内厂商名 0 处、`app/domain/` 无 SQLAlchemy、不新增 `STRUCTAI-xxxx` 码、
   新增 Settings 字段必须同步 `.env.example`（本批未新增，由清单比对固化）。

⚠️ 本文件里的「规范原文副本」（20 码清单 / 依赖清单 / 流水线 26 步顺序 / 锁兼容矩阵 /
固定确认串）**故意不**从被测模块取：若断言只与被测常量比较，「常量被改错」与
「实现被改错」会一起通过（同源循环）。
"""

from __future__ import annotations

import ast
import asyncio
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import AsyncIterator, Sequence
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.execution import (
    CLIENT_CONTROLLED_IDENTITY_FIELDS,
    CLIENT_PROVIDABLE_RESOURCE_FIELDS,
    CONFIRMATION_FAILURE_REASONS,
    CONFIRMATION_REQUIRED_RISK_LEVELS,
    EXECUTION_PIPELINE_ORDER,
    FORBIDDEN_CONFIRMATION_TOKENS,
    INVALID_CONFIRMATION_MESSAGE,
    MIN_ELEMENT_NODES,
    MODEL_COMPLETENESS_KEYS,
    POSTCONDITION_OPERATIONS,
    POSTCONDITION_STAGE_ORDER,
    PRECONDITION_OPERATIONS,
    ConfirmationGuard,
    ConfirmationService,
    EngineeringValidator,
    ExecutionContext,
    ExecutionContextFactory,
    ExecutionFacts,
    PostconditionEvaluator,
    PreconditionEvaluator,
    ignored_client_identity_fields,
)
from app.application.resource import (
    EXCLUSIVE_RISK_LEVELS,
    LOCK_COMPATIBILITY,
    PIPELINE_LOCK_HINTS,
    RESOLUTION_PRECEDENCE,
    LockPolicy,
    ResolvedResource,
    ResourceKey,
    ResourceLockManager,
    ResourceResolver,
    locks_are_compatible,
    with_resolved_software,
)
from app.application.security.context import IdentityContext
from app.application.services import CapabilityResolver
from app.config.settings import Settings
from app.container import BATCH_ID, AppContainer
from app.domain.enums import CapabilityStatus, LockMode, ResourceType, RiskLevel, TaskStatus
from app.domain.errors import (
    CapabilityError,
    ConfirmationRequiredError,
    EngineeringValidationError,
    ProtocolError,
    ResourceLockedError,
    StructAIError,
    TaskError,
    TenantAccessDeniedError,
)
from app.domain.protocols import OperationDefinition
from app.domain.value_objects import ResourceRef
from app.infrastructure.database import Base, create_engine, create_session_factory
from app.infrastructure.database.models import (
    DocumentORM,
    ModelORM,
    ProjectORM,
    SoftwareInstanceORM,
    SoftwareVersionORM,
    TenantORM,
    UserORM,
)
from app.infrastructure.database.repositories import build_resource_store
from app.infrastructure.database.seed import ADMIN_PASSWORD_ENV, seed
from app.infrastructure.registry.capability_registry import CapabilityRegistry
from app.infrastructure.registry.operation_registry import OperationRegistry

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"

EXECUTION_DIR = APP_DIR / "application" / "execution"
RESOURCE_DIR = APP_DIR / "application" / "resource"
SERVICES_DIR = APP_DIR / "application" / "services"

VENDOR_NAMES = ("MIDAS", "CSI", "ANSYS")
"""`docs/07` §14.2：`app/` 内禁止出现的厂商名。"""

TEST_PASSWORD = "P14-Execution-验收-口令-9b27"
"""测试用口令（非真实 secret，仅存在于测试进程内）。"""

SessionFactory = async_sessionmaker[AsyncSession]
"""会话工厂类型别名（`docs/02` §15）。"""

P14_MODULES = (
    "app/application/execution/context.py",
    "app/application/execution/engineering_validator.py",
    "app/application/execution/preconditions.py",
    "app/application/execution/postconditions.py",
    "app/application/execution/confirmation.py",
    "app/application/resource/resolver.py",
    "app/application/resource/lock_manager.py",
    "app/application/resource/lock_policy.py",
    "app/application/services/capability_resolver.py",
)
"""本批新增的 Application 层模块（`docs/07` §3.3 冻结结构）。"""

INFRASTRUCTURE_FREE_MODULES = P14_MODULES
"""红线检查范围：Application 新层全部文件（`docs/07` §14.1 / §2.2）。"""


# ===== 规范原文副本（`docs/07` §9 / §11 / §3.1 / §8.4；`docs/02` §36）=====

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

PIPELINE_26_STEPS = (
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
"""`docs/07` §9 的 26 步冻结顺序（逐字抄写）。"""

LOCK_MATRIX_SPEC = (
    (LockMode.READ, LockMode.READ, True),
    (LockMode.READ, LockMode.WRITE, False),
    (LockMode.READ, LockMode.EXCLUSIVE, False),
    (LockMode.WRITE, LockMode.READ, False),
    (LockMode.WRITE, LockMode.WRITE, False),
    (LockMode.WRITE, LockMode.EXCLUSIVE, False),
    (LockMode.EXCLUSIVE, LockMode.READ, False),
    (LockMode.EXCLUSIVE, LockMode.WRITE, False),
    (LockMode.EXCLUSIVE, LockMode.EXCLUSIVE, False),
)
"""`docs/02` §36 的兼容矩阵逐格副本（`held`, `requested`, 是否可授予）。"""

FIXED_CONFIRMATION_STRINGS = ("CONFIRM", "YES", "true", "TRUE", "ok", "Y", "1", " confirm ")
"""`docs/07` §8.4 禁止用作确认的固定字符串（含大小写与空白变体）。"""

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

DOTTED_UPPER = re.compile(r"^[A-Z][A-Z0-9_]*(?:\.[A-Z0-9_]+)+$")
"""形如 `MODEL.NODE.WRITE` / `BUILD.COLUMN` 的字面量（能力码或 Operation 名）。"""


# ===== 夹具与辅助 =====


@pytest.fixture
async def seeded_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncEngine]:
    """临时 SQLite + 建表 + 真实 Seed（`docs/02` §15 / §36 / §43–§46）。"""
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p14_execution.db').as_posix()}"
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


async def _default_tenant_id(session: AsyncSession) -> str:
    """Seed 落库的唯一租户 id。"""
    result = await session.execute(select(TenantORM.id).order_by(TenantORM.created_at))
    return str(result.scalars().first())


async def _admin_user_id(session: AsyncSession) -> str:
    """Seed 落库的管理员用户 id。"""
    result = await session.execute(select(UserORM.id).where(UserORM.username == "admin"))
    return str(result.scalars().one())


async def _mock_instance_id(session: AsyncSession) -> str:
    """Seed 落库的 Mock 软件实例 id（`docs/02` §101）。"""
    result = await session.execute(select(SoftwareInstanceORM.id))
    return str(result.scalars().first())


async def _seed_version_id(session: AsyncSession) -> str:
    """Seed 落库的软件版本 id（新建实例时复用）。"""
    result = await session.execute(select(SoftwareVersionORM.id))
    return str(result.scalars().first())


async def _add_tenant(session: AsyncSession, name: str) -> str:
    """新建租户，返回其 id。"""
    tenant = TenantORM(name=name)
    session.add(tenant)
    await session.flush()
    return str(tenant.id)


async def _add_project(session: AsyncSession, tenant_id: str, name: str) -> str:
    """新建项目，返回其 id。"""
    project = ProjectORM(tenant_id=str(tenant_id), name=name)
    session.add(project)
    await session.flush()
    return str(project.id)


async def _add_model(
    session: AsyncSession,
    project_id: str,
    name: str,
    *,
    software_instance_id: str | None = None,
) -> str:
    """新建工程模型（可绑定软件实例），返回其 id。"""
    model = ModelORM(
        project_id=str(project_id),
        software_instance_id=None if software_instance_id is None else str(software_instance_id),
        name=name,
    )
    session.add(model)
    await session.flush()
    return str(model.id)


async def _add_document(
    session: AsyncSession,
    project_id: str,
    name: str,
    *,
    model_id: str | None = None,
) -> str:
    """新建文档，返回其 id。"""
    document = DocumentORM(
        project_id=str(project_id),
        model_id=None if model_id is None else str(model_id),
        name=name,
        status="NEW",
    )
    session.add(document)
    await session.flush()
    return str(document.id)


async def _add_instance(
    session: AsyncSession,
    *,
    name: str,
    status: str,
) -> str:
    """新建软件实例（复用 Seed 的版本链），返回其 id。"""
    instance = SoftwareInstanceORM(
        version_id=await _seed_version_id(session),
        name=name,
        status=status,
    )
    session.add(instance)
    await session.flush()
    return str(instance.id)


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
    project_id: str | None = None,
    model_id: str | None = None,
    document_id: str | None = None,
    software_instance_id: str | None = None,
) -> ExecutionContext:
    """由服务端身份构造执行上下文（`docs/02` §5）。"""
    return ExecutionContextFactory().create(
        identity,
        project_id=project_id,
        model_id=model_id,
        document_id=document_id,
        software_instance_id=software_instance_id,
    )


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


def _string_literals(path: Path) -> list[str]:
    """文件内全部字符串字面量（AST 级）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


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
    name: str = "p14_main.db",
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
    """取会话背后的 `AsyncEngine`（`docs/02` §15）。

    ⚠️ `AsyncSession.get_bind()` 返回的是**同步** `Engine`；Registry 装配需要
    `AsyncEngine`（它要 `await engine.connect()`），故这里用 `session.bind`。
    """
    engine = getattr(session, "bind", None)
    assert isinstance(engine, AsyncEngine), "session is not bound to an AsyncEngine"
    return engine


async def _operation(session: AsyncSession, name: str) -> OperationDefinition:
    """从已配备库装配的 Operation Registry 取一条定义（`docs/02` §28）。"""
    engine = _async_engine_of(session)
    registry = await OperationRegistry.load(engine, create_session_factory(engine))
    assert registry is not None  # noqa: S101 - 已配备库必然装配成功
    return registry.require(name)


async def _capability_registry(session: AsyncSession) -> CapabilityRegistry:
    """从已配备库装配 Capability Registry（P08；41 条能力码）。"""
    engine = _async_engine_of(session)
    registry = await CapabilityRegistry.load(engine, create_session_factory(engine))
    assert registry is not None  # noqa: S101 - 已配备库必然装配成功
    return registry


async def _operation_registry_list(session: AsyncSession) -> list[OperationDefinition]:
    """装配全量 Operation 定义（69 条；`docs/02` §28）。"""
    engine = _async_engine_of(session)
    registry = await OperationRegistry.load(engine, create_session_factory(engine))
    assert registry is not None
    return await registry.list()


def _relative_path(relative: str) -> Path:
    """仓库内相对路径 → 绝对路径。"""
    return REPO_ROOT / relative


# ===== ① 主门槛（`docs/07` §12 P14–P18 / `docs/02` §116）=====


def test_gate_pipeline_order_matches_docs_07_section_9() -> None:
    """门槛 ①：流水线 26 步顺序与 `docs/07` §9 逐条一致（冻结）。"""
    assert EXECUTION_PIPELINE_ORDER == PIPELINE_26_STEPS


def test_execution_context_is_frozen_and_only_built_by_core() -> None:
    """门槛 ①：`ExecutionContext` 不可变，默认子上下文为空（`docs/02` §3 / §5）。"""
    identity = _identity(user_id=uuid4(), tenant_id=uuid4())
    context = ExecutionContextFactory().create(identity)

    assert context.identity is identity
    assert context.request_id.startswith("req_")
    assert context.trace_id.startswith("trace_")
    assert context.software.instance_id is None
    assert context.project.project_id is None
    assert context.resource.model_id is None
    assert context.resource.document_id is None
    with pytest.raises(FrozenInstanceError):
        context.request_id = "tampered"  # type: ignore[misc]


def test_client_providable_and_forbidden_fields_are_the_frozen_lists() -> None:
    """门槛 ①：客户端可提供 / 不可提供的字段清单（`docs/02` §4；`docs/07` §8.1）。"""
    assert CLIENT_PROVIDABLE_RESOURCE_FIELDS == (
        "software_instance_id",
        "project_id",
        "model_id",
        "document_id",
    )
    for forbidden in ("user_id", "tenant_id", "roles", "permissions", "session_id", "identity"):
        assert forbidden in CLIENT_CONTROLLED_IDENTITY_FIELDS


def test_client_identity_fields_are_ignored_not_merged() -> None:
    """门槛 ①：客户端提供的身份字段**一律忽略**（`docs/07` §8.1 / §14.3）。"""
    server_user = uuid4()
    server_tenant = uuid4()
    identity = _identity(user_id=server_user, tenant_id=server_tenant, roles=("viewer",))
    project_id = str(uuid4())

    client_context = {
        "project_id": project_id,
        "identity": {"user_id": str(uuid4()), "tenant_id": str(uuid4())},
        "user_id": str(uuid4()),
        "tenant_id": str(uuid4()),
        "roles": ["system_admin"],
        "permissions": ["SYSTEM_ADMIN"],
        "session_id": str(uuid4()),
        "unknown_key": "ignored",
    }
    context = ExecutionContextFactory().from_client_context(identity, client_context)

    assert context.identity is identity
    assert context.identity.user_id == server_user
    assert context.identity.tenant_id == server_tenant
    assert context.identity.roles == ("viewer",)
    assert context.project.project_id == UUID(project_id)
    assert ignored_client_identity_fields(client_context) == (
        "identity",
        "user_id",
        "tenant_id",
        "roles",
        "permissions",
        "session_id",
    )
    assert ignored_client_identity_fields({"project_id": project_id}) == ()


def test_invalid_client_resource_identifier_is_structai_1000() -> None:
    """门槛 ①：非法 UUID → `STRUCTAI-1000`（不新增错误码；见 `context.py` 裁决 2）。"""
    identity = _identity(user_id=uuid4(), tenant_id=uuid4())

    with pytest.raises(ProtocolError) as excinfo:
        ExecutionContextFactory().from_client_context(identity, {"project_id": "not-a-uuid"})

    assert excinfo.value.code == "STRUCTAI-1000"
    assert excinfo.value.details["stage"] == "context"


def test_resolved_resource_matches_docs_02_section_73_shape() -> None:
    """门槛 ①：`ResolvedResource` 字段与 `docs/02` §73 一致（含 `as_key`）。"""
    names = [field.name for field in fields(ResolvedResource)]
    assert names == ["resource_type", "resource_id", "tenant_id", "project_id"]
    assert RESOLUTION_PRECEDENCE == (
        ResourceType.DOCUMENT,
        ResourceType.MODEL,
        ResourceType.PROJECT,
        ResourceType.SOFTWARE_INSTANCE,
    )


def test_resource_resolver_resolves_all_four_identifiers(
    sessions: SessionFactory,
) -> None:
    """门槛 ①（主门槛）：四类标识解析成 `ResolvedResource`，最具体者胜（`docs/02` §8 / §73）。"""

    async def _run() -> None:
        async with sessions() as session:
            tenant_id = await _default_tenant_id(session)
            user_id = await _admin_user_id(session)
            project_id = await _add_project(session, tenant_id, "P14 项目")
            instance_id = await _add_instance(session, name="P14 实例", status="CONNECTED")
            model_id = await _add_model(
                session, project_id, "P14 模型", software_instance_id=instance_id
            )
            document_id = await _add_document(session, project_id, "P14 文档", model_id=model_id)
            identity = _identity(user_id=user_id, tenant_id=tenant_id)
            resolver = ResourceResolver(build_resource_store(session))

            project = await resolver.resolve_project(_context(identity, project_id=project_id))
            assert (project.resource_type, project.resource_id) == ("PROJECT", project_id)
            assert project.tenant_id == tenant_id
            assert project.project_id is None

            model = await resolver.resolve_model(
                _context(identity, project_id=project_id, model_id=model_id)
            )
            assert (model.resource_type, model.resource_id) == ("MODEL", model_id)
            assert model.tenant_id == tenant_id
            assert model.project_id == project_id

            document = await resolver.resolve_document(
                _context(
                    identity,
                    project_id=project_id,
                    model_id=model_id,
                    document_id=document_id,
                )
            )
            assert (document.resource_type, document.resource_id) == ("DOCUMENT", document_id)
            assert document.tenant_id == tenant_id
            assert document.project_id == project_id

            instance = await resolver.resolve_software_instance(
                _context(identity, software_instance_id=instance_id)
            )
            assert (instance.resource_type, instance.resource_id) == (
                "SOFTWARE_INSTANCE",
                instance_id,
            )
            assert instance.tenant_id == tenant_id
            assert instance.as_key() == ResourceKey("SOFTWARE_INSTANCE", instance_id)

            # 四类一起给出 → 校验全部、返回最具体的一个（见 `resolver.py` 裁决 3）。
            combined = await resolver.resolve(
                _context(
                    identity,
                    project_id=project_id,
                    model_id=model_id,
                    document_id=document_id,
                    software_instance_id=instance_id,
                )
            )
            assert combined is not None
            assert combined.resource_type == ResourceType.DOCUMENT.value
            assert combined.resource_id == document_id

    asyncio.run(_run())


def test_resource_resolver_returns_none_when_no_identifier_is_given(
    sessions: SessionFactory,
) -> None:
    """门槛 ①：一个标识都没提供 → `resolve()` 返回 `None`（不臆造资源）。"""

    async def _run() -> None:
        async with sessions() as session:
            identity = _identity(
                user_id=await _admin_user_id(session),
                tenant_id=await _default_tenant_id(session),
            )
            resolver = ResourceResolver(build_resource_store(session))
            assert await resolver.resolve(_context(identity)) is None

    asyncio.run(_run())


def test_cross_tenant_resource_resolution_is_denied_with_structai_4200(
    sessions: SessionFactory,
) -> None:
    """门槛 ①：跨租户 → **`STRUCTAI-4200`**（`docs/07` §9 第 7 步 / §11）。"""

    async def _run() -> None:
        async with sessions() as session:
            tenant_a = await _default_tenant_id(session)
            project_a = await _add_project(session, tenant_a, "租户 A 项目")
            instance_a = await _add_instance(session, name="A 的实例", status="CONNECTED")
            model_a = await _add_model(
                session, project_a, "A 的模型", software_instance_id=instance_a
            )
            document_a = await _add_document(session, project_a, "A 的文档", model_id=model_a)

            tenant_b = await _add_tenant(session, "租户 B")
            identity_b = _identity(user_id=uuid4(), tenant_id=tenant_b)
            resolver = ResourceResolver(build_resource_store(session))

            attempts = (
                resolver.resolve_project(_context(identity_b, project_id=project_a)),
                resolver.resolve_model(
                    _context(identity_b, project_id=project_a, model_id=model_a)
                ),
                resolver.resolve_document(
                    _context(
                        identity_b,
                        project_id=project_a,
                        model_id=model_a,
                        document_id=document_a,
                    )
                ),
                resolver.resolve_software_instance(
                    _context(identity_b, software_instance_id=instance_a)
                ),
            )
            for attempt in attempts:
                with pytest.raises(TenantAccessDeniedError) as excinfo:
                    await attempt
                assert excinfo.value.code == "STRUCTAI-4200"
                assert excinfo.value.message == "Tenant access denied"
                assert excinfo.value.details == {}

    asyncio.run(_run())


def test_missing_and_foreign_resources_are_indistinguishable(
    sessions: SessionFactory,
) -> None:
    """门槛 ①：不存在与属于别的租户返回**同一形状**（`docs/02` §48：不泄露存在性）。"""

    async def _run() -> None:
        async with sessions() as session:
            tenant_a = await _default_tenant_id(session)
            project_a = await _add_project(session, tenant_a, "A 的项目")
            tenant_b = await _add_tenant(session, "B 租户")
            identity_b = _identity(user_id=uuid4(), tenant_id=tenant_b)
            resolver = ResourceResolver(build_resource_store(session))

            shapes: list[tuple[str, str, dict[str, Any]]] = []
            for project_id in (project_a, str(uuid4())):
                with pytest.raises(TenantAccessDeniedError) as excinfo:
                    await resolver.resolve_project(_context(identity_b, project_id=project_id))
                shapes.append((excinfo.value.code, excinfo.value.message, excinfo.value.details))

            assert shapes[0] == shapes[1]
            assert shapes[0][0] == "STRUCTAI-4200"

    asyncio.run(_run())


def test_resource_resolution_path_performs_no_writes(
    seeded_engine: AsyncEngine,
    sessions: SessionFactory,
) -> None:
    """门槛 ①：解析路径**零写入** —— 因此可以先于权限 / 锁执行（`docs/07` §9 第 7 步）。"""
    statements: list[str] = []

    def _record(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    async def _run() -> None:
        async with sessions() as session:
            tenant_id = await _default_tenant_id(session)
            user_id = await _admin_user_id(session)
            project_id = await _add_project(session, tenant_id, "只读项目")
            model_id = await _add_model(session, project_id, "只读模型")
            document_id = await _add_document(session, project_id, "只读文档", model_id=model_id)
            identity = _identity(user_id=user_id, tenant_id=tenant_id)
            resolver = ResourceResolver(build_resource_store(session))
            await session.commit()

            statements.clear()
            await resolver.resolve(
                _context(
                    identity,
                    project_id=project_id,
                    model_id=model_id,
                    document_id=document_id,
                )
            )

    event.listen(seeded_engine.sync_engine, "before_cursor_execute", _record)
    try:
        asyncio.run(_run())
    finally:
        event.remove(seeded_engine.sync_engine, "before_cursor_execute", _record)

    assert statements, "解析路径应当至少发出读查询"
    assert _write_verbs(statements) == []


def test_resolver_rejects_inconsistent_client_identifiers(
    sessions: SessionFactory,
) -> None:
    """门槛 ①：客户端标识自相矛盾 → `STRUCTAI-1000`（见 `resolver.py` 裁决 2）。"""

    async def _run() -> None:
        async with sessions() as session:
            tenant_id = await _default_tenant_id(session)
            user_id = await _admin_user_id(session)
            project_one = await _add_project(session, tenant_id, "项目一")
            project_two = await _add_project(session, tenant_id, "项目二")
            model_two = await _add_model(session, project_two, "项目二的模型")
            identity = _identity(user_id=user_id, tenant_id=tenant_id)
            resolver = ResourceResolver(build_resource_store(session))

            with pytest.raises(ProtocolError) as excinfo:
                await resolver.resolve_model(
                    _context(identity, project_id=project_one, model_id=model_two)
                )
            assert excinfo.value.code == "STRUCTAI-1000"
            assert excinfo.value.details["resource_type"] == "MODEL"

    asyncio.run(_run())


def test_software_instance_requires_a_tenant_binding(
    sessions: SessionFactory,
) -> None:
    """门槛 ①：软件实例的租户归属必须补齐（`docs/02` §12；见 `resolver.py` 裁决 4）。"""

    async def _run() -> None:
        async with sessions() as session:
            tenant_a = await _default_tenant_id(session)
            project_a = await _add_project(session, tenant_a, "绑定项目")
            instance_id = await _add_instance(session, name="待绑定实例", status="CONNECTED")
            identity_a = _identity(user_id=await _admin_user_id(session), tenant_id=tenant_a)
            resolver = ResourceResolver(build_resource_store(session))

            # 未被任何项目链绑定 → 任何租户都不得直接执行。
            with pytest.raises(TenantAccessDeniedError) as unbound:
                await resolver.resolve_software_instance(
                    _context(identity_a, software_instance_id=instance_id)
                )
            assert unbound.value.code == "STRUCTAI-4200"

            await _add_model(session, project_a, "绑定模型", software_instance_id=instance_id)

            allowed = await resolver.resolve_software_instance(
                _context(identity_a, software_instance_id=instance_id)
            )
            assert allowed.tenant_id == tenant_a

            tenant_b = await _add_tenant(session, "未绑定租户")
            with pytest.raises(TenantAccessDeniedError) as foreign:
                await resolver.resolve_software_instance(
                    _context(
                        _identity(user_id=uuid4(), tenant_id=tenant_b),
                        software_instance_id=instance_id,
                    )
                )
            assert foreign.value.code == "STRUCTAI-4200"

    asyncio.run(_run())


def test_verify_access_rejects_foreign_and_unknown_resources(
    sessions: SessionFactory,
) -> None:
    """门槛 ①：`docs/02` §9 的 `verify_access` 逐类型生效，未知类型 → `STRUCTAI-1000`。"""

    async def _run() -> None:
        async with sessions() as session:
            tenant_a = await _default_tenant_id(session)
            project_a = await _add_project(session, tenant_a, "校验项目")
            model_a = await _add_model(session, project_a, "校验模型")
            identity_a = _identity(user_id=await _admin_user_id(session), tenant_id=tenant_a)
            resolver = ResourceResolver(build_resource_store(session))
            context = _context(identity_a, project_id=project_a)

            await resolver.verify_access(ResourceRef("PROJECT", project_a), context)
            await resolver.verify_access(ResourceRef("MODEL", model_a), context)

            with pytest.raises(ProtocolError) as excinfo:
                await resolver.verify_access(ResourceRef("UNKNOWN_TYPE", project_a), context)
            assert excinfo.value.code == "STRUCTAI-1000"

            with pytest.raises(TenantAccessDeniedError):
                await resolver.verify_access(ResourceRef("PROJECT", str(uuid4())), context)

    asyncio.run(_run())


def test_with_resolved_software_fills_product_and_version_without_mutating() -> None:
    """门槛 ①：`product` / `version` 只能由解析结果回填（`docs/07` §8.1）。"""
    identity = _identity(user_id=uuid4(), tenant_id=uuid4())
    context = _context(identity, software_instance_id=str(uuid4()))

    filled = cast(
        ExecutionContext,
        with_resolved_software(context, product="Mock Engineering Software", version="1.0"),
    )

    assert filled.software.product == "Mock Engineering Software"
    assert filled.software.version == "1.0"
    assert filled.software.instance_id == context.software.instance_id
    assert context.software.product is None
    assert context.software.version is None


# ===== ② 顺序冻结（`docs/02` §13 / §30 / §67–§70）=====


def _step(name: str) -> int:
    """流水线步骤序号（顺序断言用）。"""
    return EXECUTION_PIPELINE_ORDER.index(name)


def test_schema_validation_precedes_engineering_validation() -> None:
    """门槛 ②：`Schema Validation` **先于** `Engineering Validation`（`docs/02` §13 / §30）。"""
    assert _step("Schema Validation") < _step("Engineering Validation")


def test_permission_precedes_capability() -> None:
    """门槛 ②：`Permission` **先于** `Capability`（`docs/02` §68）。"""
    assert _step("Effective Permission") < _step("Capability Check")


def test_postconditions_precede_release_lock() -> None:
    """门槛 ②：`Postconditions` **先于** `Release Lock`（`docs/07` §9 第 20 / 21 步）。"""
    assert _step("Postconditions") < _step("Release Lock")
    assert POSTCONDITION_STAGE_ORDER == ("Postconditions", "Release Lock")


def test_resolve_resource_is_the_first_boundary_check() -> None:
    """门槛 ②：`Resolve Resource` **先于** Schema / Engineering / Permission / Lock。"""
    resolve = _step("Resolve Resource")
    for later in (
        "Schema Validation",
        "Engineering Validation",
        "Preconditions",
        "Effective Permission",
        "Confirmation",
        "Idempotency",
        "Concurrency / Resource Lock",
        "Capability Check",
        "Task / Transaction",
        "Adapter",
    ):
        assert resolve < _step(later), later


def test_idempotency_precedes_lock() -> None:
    """门槛 ②：`Idempotency` **先于** `Lock`（`docs/07` §9：重复请求直接返回，不抢锁）。"""
    assert _step("Idempotency") < _step("Concurrency / Resource Lock")


def test_capability_precedes_task() -> None:
    """门槛 ②：`Capability` **先于** `Task`（`docs/07` §9：无能力的任务不得入队）。"""
    assert _step("Capability Check") < _step("Task / Transaction")


def test_schema_engine_stays_free_of_engineering_semantics() -> None:
    """门槛 ②：工程语义**不得**塞回 Schema 层（`docs/02` §17 / §69）。

    ⚠️ 只断言**实现**层面的分离：`validation.py` 不得实现 / 导入工程规则
    （文档字符串里提到 `EngineeringValidator` 归属何处是**允许**的 —— 那是分层说明）。
    """
    source = (EXECUTION_DIR / "validation.py").read_text(encoding="utf-8")
    assert "EngineeringValidationError" not in source
    schema_imports = _imported_modules(EXECUTION_DIR / "validation.py")
    assert not [name for name in schema_imports if name.endswith("engineering_validator")]
    assert not [name for name in schema_imports if name.endswith("preconditions")]
    assert not [name for name in schema_imports if name.endswith("postconditions")]

    engineering_imports = _imported_modules(EXECUTION_DIR / "engineering_validator.py")
    assert not [name for name in engineering_imports if "jsonschema" in name]
    assert not [name for name in engineering_imports if name.endswith("validation")]


# ===== ③ Lock（`docs/02` §36–§42）=====


def test_lock_compatibility_matrix_matches_docs_02_section_36() -> None:
    """门槛 ③：兼容矩阵逐格可查（`docs/02` §36）。"""
    assert LOCK_COMPATIBILITY[LockMode.READ] == frozenset({LockMode.READ})
    assert LOCK_COMPATIBILITY[LockMode.WRITE] == frozenset()
    assert LOCK_COMPATIBILITY[LockMode.EXCLUSIVE] == frozenset()
    for held, requested, allowed in LOCK_MATRIX_SPEC:
        assert locks_are_compatible(held, requested) is allowed, (held, requested)


def test_lock_manager_mutual_exclusion_by_resource_key() -> None:
    """门槛 ③：按资源键互斥（`docs/02` §37 / §38 / §39）。"""

    async def _run() -> None:
        manager = ResourceLockManager()
        first = ResourceKey("MODEL", "model-1")
        second = ResourceKey("MODEL", "model-2")

        read_a = await manager.acquire(first, LockMode.READ, "owner-a")
        read_b = await manager.acquire(first, LockMode.READ, "owner-b")
        assert await manager.held_count() == 2

        with pytest.raises(ResourceLockedError) as blocked_write:
            await manager.acquire(first, LockMode.WRITE, "owner-c")
        assert blocked_write.value.code == "STRUCTAI-6100"
        assert blocked_write.value.details["held_modes"] == ["READ"]
        assert blocked_write.value.details["requested_mode"] == "WRITE"

        # 另一个资源键互不影响。
        other = await manager.acquire(second, LockMode.EXCLUSIVE, "owner-d")

        await manager.release(read_a)
        await manager.release(read_b)
        writer = await manager.acquire(first, LockMode.WRITE, "owner-e")
        with pytest.raises(ResourceLockedError):
            await manager.acquire(first, LockMode.EXCLUSIVE, "owner-f")
        await manager.release(writer)
        await manager.release(other)
        assert await manager.held_count() == 0

    asyncio.run(_run())


def test_lock_manager_releases_on_exception() -> None:
    """门槛 ③：异常路径也必须释放（`docs/02` §41 / §65；`docs/02` §88 lock leak）。"""

    async def _run() -> None:
        manager = ResourceLockManager()
        key = ResourceKey("DOCUMENT", "doc-1")

        with pytest.raises(RuntimeError):
            async with manager.hold(key, LockMode.EXCLUSIVE, "owner-a"):
                raise RuntimeError("adapter failed")

        assert await manager.held_count() == 0
        # 释放后可再次获取（无锁泄漏）。
        async with manager.hold(key, LockMode.EXCLUSIVE, "owner-b"):
            assert await manager.is_locked(key) is True
        assert await manager.is_locked(key) is False

    asyncio.run(_run())


def test_lock_lease_expiry_releases_stale_holders() -> None:
    """门槛 ③：租约到期后不再占住资源（`docs/02` §13 的 `timeout`）。"""

    async def _run() -> None:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        manager = ResourceLockManager(clock=lambda: now, default_timeout_seconds=60)
        key = ResourceKey("MODEL", "model-lease")

        handle = await manager.acquire(key, LockMode.WRITE, "owner-a")
        with pytest.raises(ResourceLockedError):
            await manager.acquire(key, LockMode.READ, "owner-b")

        # 时钟前进超过租约 → 陈旧持有者被清理。
        manager._clock = lambda: now + timedelta(seconds=61)  # noqa: SLF001 - 测试注入时钟
        assert await manager.expire_stale() == 1
        assert await manager.is_locked(key) is False

        replacement = await manager.acquire(key, LockMode.READ, "owner-c")
        assert await manager.release(handle) is False  # 句柄已失效，不影响新持有者
        assert await manager.release(replacement) is True

    asyncio.run(_run())


def test_lock_manager_does_not_touch_the_database(seeded_engine: AsyncEngine) -> None:
    """门槛 ③：锁是**进程内**状态，不发任何 SQL（`docs/02` §38；`docs/07` §14.4）。"""
    statements: list[str] = []

    def _record(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    async def _run() -> None:
        manager = ResourceLockManager()
        key = ResourceKey("MODEL", "no-sql")
        async with manager.hold(key, LockMode.WRITE, "owner"):
            pass

    event.listen(seeded_engine.sync_engine, "before_cursor_execute", _record)
    try:
        asyncio.run(_run())
    finally:
        event.remove(seeded_engine.sync_engine, "before_cursor_execute", _record)

    assert statements == []


def test_lock_policy_resolves_modes_per_docs_02_section_74(
    sessions: SessionFactory,
) -> None:
    """门槛 ③：`LockPolicy` 的三条分支（`docs/02` §74）。"""

    async def _run() -> None:
        async with sessions() as session:
            policy = LockPolicy(timeout_seconds=123)
            resource = ResolvedResource(
                resource_type=ResourceType.MODEL.value,
                resource_id="model-lock",
                tenant_id="tenant",
                project_id="project",
            )
            query = await _operation(session, "MODEL.NODE.QUERY")
            high = await _operation(session, "BUILD.COLUMN")
            medium = await _operation(session, "MODEL.NODE.CREATE")

            assert policy.mode_for(query) is LockMode.READ
            assert policy.mode_for(high) is LockMode.EXCLUSIVE
            assert policy.mode_for(medium) is LockMode.WRITE

            lock = policy.resolve(high, resource, owner_id="request-1")
            assert lock.resource == ResourceKey(ResourceType.MODEL.value, "model-lock")
            assert lock.mode is LockMode.EXCLUSIVE
            assert lock.owner_id == "request-1"
            assert lock.timeout_seconds == 123

            with pytest.raises(TypeError):
                policy.resolve(high, object())

    asyncio.run(_run())


def test_lock_policy_agrees_with_pipeline_hints(sessions: SessionFactory) -> None:
    """门槛 ③：`docs/02` §74 的判定与 §58 的流水线建议一致处一致、更严格处更严格。

    ⚠️ `docs/02` §58 建议 `Build = WRITE Model` / `Delete = WRITE Model`，而 §74 的
    第 2 条规则是 `risk_level ∈ {HIGH, CRITICAL} → EXCLUSIVE`。
    `engineering_model_build` 与 `engineering_model_delete` 在 `docs/07` §5.1 里**都是
    `HIGH`**，故 §74 对 `BUILD.*` / `MODEL.*.DELETE` 给出 `EXCLUSIVE` ——
    **比 §58 的建议更严格**。本批以 §74 为准（它是 `LockPolicy` 的原文实现），
    取更严格者是安全方向（见 `lock_policy.py` 裁决 1）。
    """

    async def _run() -> None:
        async with sessions() as session:
            policy = LockPolicy()
            # 一致的三处：ANALYSIS / DESIGN 都是 HIGH → EXCLUSIVE；QUERY 是 READ。
            assert (
                policy.mode_for(await _operation(session, "ANALYSIS.STATIC"))
                is (PIPELINE_LOCK_HINTS["ANALYSIS"])
            )
            assert (
                policy.mode_for(await _operation(session, "DESIGN.STEEL"))
                is (PIPELINE_LOCK_HINTS["DESIGN"])
            )
            assert (
                policy.mode_for(await _operation(session, "MODEL.QUERY"))
                is (PIPELINE_LOCK_HINTS["QUERY"])
            )

            # 更严格的两处：BUILD.* / MODEL.*.DELETE 都是 HIGH → EXCLUSIVE（§74 胜出）。
            for name in ("BUILD.BEAM", "MODEL.NODE.DELETE"):
                operation = await _operation(session, name)
                assert operation.risk_level is RiskLevel.HIGH, name
                assert policy.mode_for(operation) is LockMode.EXCLUSIVE, name
            assert PIPELINE_LOCK_HINTS["BUILD"] is LockMode.WRITE
            assert PIPELINE_LOCK_HINTS["DELETE"] is LockMode.WRITE
            assert EXCLUSIVE_RISK_LEVELS == {RiskLevel.HIGH, RiskLevel.CRITICAL}

    asyncio.run(_run())


def test_double_release_does_not_affect_other_holders() -> None:
    """门槛 ③：重复释放不改变其他持有者的计数（见 `lock_manager.py` 裁决 1）。"""

    async def _run() -> None:
        manager = ResourceLockManager()
        key = ResourceKey("MODEL", "double-release")
        first = await manager.acquire(key, LockMode.READ, "owner-a")
        second = await manager.acquire(key, LockMode.READ, "owner-b")

        assert await manager.release(first) is True
        assert await manager.release(first) is False
        assert await manager.held_count() == 1

        with pytest.raises(ResourceLockedError):
            await manager.acquire(key, LockMode.WRITE, "owner-c")

        await manager.release(second)
        assert await manager.held_count() == 0

    asyncio.run(_run())


# ===== ④ Capability（`docs/02` §43–§48）=====


def test_capability_vocabulary_comes_only_from_the_seeded_table(
    sessions: SessionFactory,
) -> None:
    """门槛 ④：能力词表只来自 P07 落库的 `capabilities`（41 条），代码里不得另造。"""

    async def _run() -> None:
        async with sessions() as session:
            registry = await _capability_registry(session)
            resolver = CapabilityResolver(registry, build_resource_store(session))
            operations = await _operation_registry_list(session)

            assert len(resolver.known) == 41
            assert resolver.known == frozenset(registry.codes())
            assert resolver.unknown_codes(operations) == ()
            for operation in operations:
                assert resolver.required_for(operation) == resolver.registry_required_for(
                    operation.name
                ), operation.name

    asyncio.run(_run())


def test_p14_modules_contain_no_vendor_names() -> None:
    """门槛 ④／⑧：新模块内不得出现任何厂商名（`docs/07` §14.2）。"""
    offenders: list[str] = []
    for relative in P14_MODULES:
        source = _relative_path(relative).read_text(encoding="utf-8")
        for vendor in VENDOR_NAMES:
            if vendor.lower() in source.lower():
                offenders.append(f"{relative}:{vendor}")
    assert offenders == []


def test_p14_modules_declare_no_capability_or_operation_code_of_their_own(
    sessions: SessionFactory,
) -> None:
    """门槛 ④：新模块里出现的 `A.B.C` 字面量只能是已登记 Operation 名或落库能力码。"""

    async def _run() -> None:
        async with sessions() as session:
            registry = await _capability_registry(session)
            operations = await _operation_registry_list(session)
            vocabulary = set(registry.codes()) | {operation.name for operation in operations}

            offenders: list[str] = []
            for relative in P14_MODULES:
                for literal in _string_literals(_relative_path(relative)):
                    if DOTTED_UPPER.match(literal) and literal not in vocabulary:
                        offenders.append(f"{relative}:{literal}")
            assert offenders == []

    asyncio.run(_run())


def test_capability_decision_is_per_instance_and_version(
    sessions: SessionFactory,
) -> None:
    """门槛 ④：以「实例 + 版本 + 能力码」判定，并带缓存 TTL（`docs/02` §45 / §48）。"""

    async def _run() -> None:
        async with sessions() as session:
            registry = await _capability_registry(session)
            store = build_resource_store(session)
            resolver = CapabilityResolver(registry, store, cache_ttl_seconds=300)
            tenant_id = await _default_tenant_id(session)
            project_id = await _add_project(session, tenant_id, "能力项目")
            instance_id = await _add_instance(session, name="能力实例", status="CONNECTED")
            await _add_model(session, project_id, "能力模型", software_instance_id=instance_id)
            identity = _identity(user_id=await _admin_user_id(session), tenant_id=tenant_id)
            context = _context(identity, software_instance_id=instance_id)
            operation = await _operation(session, "BUILD.COLUMN")

            first = await resolver.check(context, operation)
            assert first.ok is True
            assert first.instance_id == instance_id
            assert first.product == "Mock Engineering Software"
            assert first.version == "1.0"
            assert first.cache_hits == 0
            assert first.supported == tuple(operation.required_capabilities)

            second = await resolver.check(context, operation)
            assert second.cache_hits == len(operation.required_capabilities)

            # 版本变化 → 缓存键必然 miss（`docs/02` §48）。
            assert resolver.invalidate(instance_id) == len(operation.required_capabilities)
            third = await resolver.check(context, operation)
            assert third.cache_hits == 0
            assert resolver.cached_entries() == len(operation.required_capabilities)
            assert resolver.invalidate() == len(operation.required_capabilities)
            assert resolver.cached_entries() == 0

    asyncio.run(_run())


def test_capability_check_rejects_disconnected_instance_with_structai_3000(
    sessions: SessionFactory,
) -> None:
    """门槛 ④：`UNKNOWN ≠ SUPPORTED` —— 未连接的实例一律拒绝（`docs/02` §47）。"""

    async def _run() -> None:
        async with sessions() as session:
            registry = await _capability_registry(session)
            resolver = CapabilityResolver(registry, build_resource_store(session))
            tenant_id = await _default_tenant_id(session)
            project_id = await _add_project(session, tenant_id, "未连接项目")
            instance_id = await _mock_instance_id(session)
            await _add_model(session, project_id, "未连接模型", software_instance_id=instance_id)
            identity = _identity(user_id=await _admin_user_id(session), tenant_id=tenant_id)
            context = _context(identity, software_instance_id=instance_id)
            operation = await _operation(session, "BUILD.COLUMN")

            with pytest.raises(CapabilityError) as excinfo:
                await resolver.check(context, operation)

            assert excinfo.value.code == "STRUCTAI-3000"
            assert excinfo.value.details["missing"] == list(operation.required_capabilities)
            assert set(excinfo.value.details["statuses"]) == {"UNKNOWN"}
            assert await resolver.supports(instance_id, operation.required_capabilities[0]) is False

    asyncio.run(_run())


def test_unknown_capability_is_never_supported(sessions: SessionFactory) -> None:
    """门槛 ④：未知能力码 → `UNKNOWN`（`docs/02` §47），`require` → `STRUCTAI-3000`。"""

    async def _run() -> None:
        async with sessions() as session:
            registry = await _capability_registry(session)
            resolver = CapabilityResolver(registry, build_resource_store(session))
            tenant_id = await _default_tenant_id(session)
            project_id = await _add_project(session, tenant_id, "未知能力项目")
            instance_id = await _add_instance(session, name="未知能力实例", status="CONNECTED")
            await _add_model(session, project_id, "未知能力模型", software_instance_id=instance_id)
            identity = _identity(user_id=await _admin_user_id(session), tenant_id=tenant_id)
            context = _context(identity, software_instance_id=instance_id)
            operation = await _operation(session, "BUILD.COLUMN")

            # 造一个「实例 + 版本 + 能力码」里能力码未知的情形：替换成不存在的码。
            unknown = OperationDefinition(
                name=operation.name,
                tool=operation.tool,
                risk_level=operation.risk_level,
                execution_mode=operation.execution_mode,
                input_schema=operation.input_schema,
                output_schema=operation.output_schema,
                required_permissions=operation.required_permissions,
                required_capabilities=("MODEL.NOT_A_REAL_CAPABILITY",),
                transactional=operation.transactional,
                rollback_supported=operation.rollback_supported,
                dry_run_supported=operation.dry_run_supported,
                recovery_policy=operation.recovery_policy,
            )

            with pytest.raises(CapabilityError) as excinfo:
                await resolver.check(context, unknown)
            assert excinfo.value.code == "STRUCTAI-3000"
            assert excinfo.value.details["missing"] == ["MODEL.NOT_A_REAL_CAPABILITY"]
            assert excinfo.value.details["statuses"] == ["UNKNOWN"]

            with pytest.raises(CapabilityError):
                await resolver.require(instance_id, "MODEL.NOT_A_REAL_CAPABILITY")

            with pytest.raises(LookupError):
                resolver.require_known("MODEL.NOT_A_REAL_CAPABILITY")

    asyncio.run(_run())


def test_capability_check_requires_a_resolvable_instance(
    sessions: SessionFactory,
) -> None:
    """门槛 ④：实例不可解析 → `STRUCTAI-3000`（见 `capability_resolver.py` 裁决 6）。"""

    async def _run() -> None:
        async with sessions() as session:
            registry = await _capability_registry(session)
            resolver = CapabilityResolver(registry)
            identity = _identity(
                user_id=await _admin_user_id(session),
                tenant_id=await _default_tenant_id(session),
            )
            operation = await _operation(session, "BUILD.COLUMN")

            with pytest.raises(CapabilityError) as missing_context:
                await resolver.check(_context(identity), operation)
            assert missing_context.value.details["reason"] == "software_instance_unresolved"

            with pytest.raises(CapabilityError) as unresolved:
                await resolver.check(
                    _context(identity, software_instance_id=str(uuid4())),
                    operation,
                )
            assert unresolved.value.details["reason"] == "software_instance_unresolved"

    asyncio.run(_run())


def test_capability_status_vocabulary_keeps_unknown_strict() -> None:
    """门槛 ④：`CapabilityStatus` 词表与 `docs/02` §8 一致（`UNKNOWN ≠ SUPPORTED`）。"""
    assert [status.value for status in CapabilityStatus] == [
        "SUPPORTED",
        "UNSUPPORTED",
        "UNKNOWN",
    ]


# ===== ⑤ Confirmation（`docs/07` §8.4；`docs/02` §34–§39）=====


def test_confirmation_token_is_server_generated_and_short_lived() -> None:
    """门槛 ⑤：token 由服务端生成、短期有效（`docs/02` §36）。"""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    service = ConfirmationService(ttl_seconds=120, clock=lambda: now)

    confirmation = service.issue(
        user_id="user-1",
        tenant_id="tenant-1",
        operation="BUILD.COLUMN",
        resource_id="model-1",
    )

    assert len(confirmation.token) >= 32
    assert confirmation.token.strip().upper() not in FORBIDDEN_CONFIRMATION_TOKENS
    assert confirmation.expires_at == now + timedelta(seconds=120)
    assert confirmation.binding.user_id == "user-1"
    assert confirmation.binding.tenant_id == "tenant-1"
    assert confirmation.binding.operation == "BUILD.COLUMN"
    assert confirmation.binding.resource_id == "model-1"
    assert service.pending() == 1


def test_confirmation_missing_token_is_structai_4100() -> None:
    """门槛 ⑤：缺 token → **`STRUCTAI-4100`**（`docs/07` §8.4 / §11）。"""
    service = ConfirmationService()

    for missing in (None, ""):
        with pytest.raises(ConfirmationRequiredError) as excinfo:
            service.verify(missing, "user-1", "tenant-1", "BUILD.COLUMN")
        assert excinfo.value.code == "STRUCTAI-4100"
        assert excinfo.value.message == INVALID_CONFIRMATION_MESSAGE
        assert excinfo.value.details["reason"] == "missing_token"


def test_fixed_strings_are_never_accepted_as_confirmation() -> None:
    """门槛 ⑤：固定字符串（`CONFIRM` / `YES` / `true` …）一律拒绝（`docs/07` §8.4）。"""
    service = ConfirmationService()

    assert "CONFIRM" in FORBIDDEN_CONFIRMATION_TOKENS
    assert "YES" in FORBIDDEN_CONFIRMATION_TOKENS
    assert "TRUE" in FORBIDDEN_CONFIRMATION_TOKENS

    for fixed in FIXED_CONFIRMATION_STRINGS:
        with pytest.raises(ConfirmationRequiredError) as excinfo:
            service.verify(fixed, "user-1", "tenant-1", "BUILD.COLUMN")
        assert excinfo.value.code == "STRUCTAI-4100"
        assert excinfo.value.details["reason"] == "forbidden_token", fixed

    with pytest.raises(RuntimeError):
        ConfirmationService(token_factory=lambda: "CONFIRM").issue(
            user_id="user-1",
            tenant_id="tenant-1",
            operation="BUILD.COLUMN",
        )


def test_confirmation_is_consumed_on_first_success() -> None:
    """门槛 ⑤：一次性 —— 第二次 verify 必须失败（`docs/02` §38）。"""
    service = ConfirmationService()
    confirmation = service.issue(
        user_id="user-1",
        tenant_id="tenant-1",
        operation="BUILD.COLUMN",
        resource_id="model-1",
    )

    consumed = service.verify(confirmation.token, "user-1", "tenant-1", "BUILD.COLUMN", "model-1")
    assert consumed.token == confirmation.token
    assert service.pending() == 0

    with pytest.raises(ConfirmationRequiredError) as excinfo:
        service.verify(confirmation.token, "user-1", "tenant-1", "BUILD.COLUMN", "model-1")
    assert excinfo.value.details["reason"] == "invalid_token"


def test_confirmation_binding_is_enforced_on_every_dimension() -> None:
    """门槛 ⑤：跨用户 / 跨租户 / 跨 operation / 跨 resource 全部拒绝（`docs/02` §37）。"""
    service = ConfirmationService()

    cases = (
        ("user_mismatch", ("user-2", "tenant-1", "BUILD.COLUMN", "model-1")),
        ("tenant_mismatch", ("user-1", "tenant-2", "BUILD.COLUMN", "model-1")),
        ("operation_mismatch", ("user-1", "tenant-1", "ANALYSIS.STATIC", "model-1")),
        ("resource_mismatch", ("user-1", "tenant-1", "BUILD.COLUMN", "model-2")),
        ("resource_mismatch", ("user-1", "tenant-1", "BUILD.COLUMN", None)),
    )
    for reason, (user_id, tenant_id, operation, resource_id) in cases:
        confirmation = service.issue(
            user_id="user-1",
            tenant_id="tenant-1",
            operation="BUILD.COLUMN",
            resource_id="model-1",
        )
        with pytest.raises(ConfirmationRequiredError) as excinfo:
            service.verify(confirmation.token, user_id, tenant_id, operation, resource_id)
        assert excinfo.value.code == "STRUCTAI-4100"
        assert excinfo.value.details["reason"] == reason, reason
        # 未匹配的失败**不**消费 token（`docs/02` §38 只消费成功的那一次）。
        assert service.pending() == 1
        service.revoke(confirmation.token)


def test_expired_confirmation_is_rejected_and_purged() -> None:
    """门槛 ⑤：过期即拒绝并删除（`docs/02` §37）。"""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    service = ConfirmationService(ttl_seconds=60, clock=lambda: now)
    confirmation = service.issue(
        user_id="user-1",
        tenant_id="tenant-1",
        operation="BUILD.COLUMN",
    )

    service._clock = lambda: now + timedelta(seconds=61)  # noqa: SLF001 - 测试注入时钟

    with pytest.raises(ConfirmationRequiredError) as excinfo:
        service.verify(confirmation.token, "user-1", "tenant-1", "BUILD.COLUMN")
    assert excinfo.value.details["reason"] == "expired"
    assert service.pending() == 0

    assert service.purge_expired() == 0


def test_confirmation_guard_only_gates_high_risk_operations(
    sessions: SessionFactory,
) -> None:
    """门槛 ⑤：`LOW` / `MEDIUM` 放行，`HIGH` / `CRITICAL` 必须确认（`docs/02` §29）。"""

    async def _run() -> None:
        async with sessions() as session:
            service = ConfirmationService()
            guard = ConfirmationGuard(service)
            identity = _identity(
                user_id=await _admin_user_id(session),
                tenant_id=await _default_tenant_id(session),
            )

            low = await _operation(session, "MODEL.NODE.QUERY")
            medium = await _operation(session, "MODEL.NODE.CREATE")
            high = await _operation(session, "BUILD.COLUMN")

            assert CONFIRMATION_REQUIRED_RISK_LEVELS == {
                RiskLevel.HIGH,
                RiskLevel.CRITICAL,
            }
            assert guard.requires_confirmation(low) is False
            assert guard.requires_confirmation(medium) is False
            assert guard.requires_confirmation(high) is True

            assert guard.require(identity, low, None) is None
            assert guard.require(identity, medium, None) is None

            with pytest.raises(ConfirmationRequiredError) as missing:
                guard.require(identity, high, None, "model-1")
            assert missing.value.code == "STRUCTAI-4100"

            issued = service.issue(
                user_id=str(identity.user_id),
                tenant_id=str(identity.tenant_id),
                operation=high.name,
                resource_id="model-1",
            )
            consumed = guard.require(identity, high, issued.token, "model-1")
            assert consumed is not None
            assert consumed.operation == high.name
            with pytest.raises(ConfirmationRequiredError):
                guard.require(identity, high, issued.token, "model-1")

    asyncio.run(_run())


def test_confirmation_token_never_leaks_through_repr_or_details() -> None:
    """门槛 ⑤：token 是 secret，绝不进 `repr` / 异常 / `details`（`docs/07` §14.3）。"""
    service = ConfirmationService()
    confirmation = service.issue(
        user_id="user-1",
        tenant_id="tenant-1",
        operation="BUILD.COLUMN",
    )

    assert confirmation.token not in repr(confirmation)
    with pytest.raises(ConfirmationRequiredError) as excinfo:
        service.verify(confirmation.token, "user-2", "tenant-1", "BUILD.COLUMN")
    assert confirmation.token not in str(excinfo.value)
    assert confirmation.token not in repr(excinfo.value.details)
    assert set(excinfo.value.details) == {"stage", "reason", "operation"}


def test_confirmation_service_rejects_non_positive_ttl() -> None:
    """门槛 ⑤：非正 TTL 是装配错误，构造时直接拒绝（见 `confirmation.py` 裁决 5）。"""
    for invalid in (0, -1):
        with pytest.raises(ValueError):
            ConfirmationService(ttl_seconds=invalid)


def test_confirmation_failure_reason_vocabulary() -> None:
    """门槛 ⑤：失败原因词表与 `docs/02` §37 的六种不匹配 + 缺失 / 固定串一致。"""
    assert CONFIRMATION_FAILURE_REASONS == (
        "missing_token",
        "forbidden_token",
        "invalid_token",
        "expired",
        "user_mismatch",
        "tenant_mismatch",
        "operation_mismatch",
        "resource_mismatch",
    )


# ===== 前置 / 后置条件与工程校验（`docs/02` §18–§23 / §32）=====


def test_preconditions_cover_the_spec_operations() -> None:
    """门槛 ②／①：前置条件目录覆盖 `docs/02` §32 的原文示例及其同族（`docs/02` §23）。"""
    assert "MODEL.NODE.CREATE" in PRECONDITION_OPERATIONS
    assert "ANALYSIS.STATIC" in PRECONDITION_OPERATIONS
    evaluator = PreconditionEvaluator()
    names = [item.name for item in evaluator.for_operation("MODEL.NODE.CREATE")]
    assert names == ["model_writable"]
    assert [item.name for item in evaluator.for_operation("ANALYSIS.STATIC")] == [
        "model_complete",
        "software_connected",
        "capability_supported",
    ]
    assert MODEL_COMPLETENESS_KEYS == (
        "nodes",
        "elements",
        "materials",
        "sections",
        "boundary",
        "load",
    )
    assert evaluator.for_operation("NOT.A.REAL.OPERATION") == ()


def test_precondition_failure_is_structai_1200(sessions: SessionFactory) -> None:
    """门槛 ②：前置条件不满足 → **`STRUCTAI-1200`**（见 `preconditions.py` 裁决 4）。"""

    async def _run() -> None:
        async with sessions() as session:
            evaluator = PreconditionEvaluator()
            operation = await _operation(session, "BUILD.COLUMN")

            # 只解析出软件实例（没有数据侧资源）→「model 可写」不满足。
            facts = ExecutionFacts(
                resolved_resource=ResolvedResource(
                    resource_type=ResourceType.SOFTWARE_INSTANCE.value,
                    resource_id="instance-1",
                    tenant_id="tenant-1",
                ),
                software_status="CONNECTED",
            )
            with pytest.raises(EngineeringValidationError) as excinfo:
                await evaluator.require(operation, facts)
            assert excinfo.value.code == "STRUCTAI-1200"
            assert excinfo.value.details["stage"] == "preconditions"
            assert excinfo.value.details["operation"] == "BUILD.COLUMN"

            # 数据侧资源已解析 + 实例已连接 → 全部满足。
            ok = await evaluator.require(
                operation,
                ExecutionFacts(
                    resolved_resource=ResolvedResource(
                        resource_type=ResourceType.MODEL.value,
                        resource_id="model-1",
                        tenant_id="tenant-1",
                        project_id="project-1",
                    ),
                    software_status="CONNECTED",
                ),
            )
            assert ok.ok is True
            assert ok.satisfied == ("model_writable", "software_connected")

    asyncio.run(_run())


def test_precondition_unverified_is_not_a_failure(sessions: SessionFactory) -> None:
    """门槛 ②：事实不足时按**未验证**处理，不误判为失败（见 `preconditions.py` 裁决 2）。"""

    async def _run() -> None:
        async with sessions() as session:
            evaluator = PreconditionEvaluator()
            operation = await _operation(session, "ANALYSIS.STATIC")

            report = await evaluator.require(
                operation,
                ExecutionFacts(
                    resolved_resource=ResolvedResource(
                        resource_type=ResourceType.MODEL.value,
                        resource_id="model-1",
                        tenant_id="tenant-1",
                        project_id="project-1",
                    ),
                    model_state={
                        "nodes": 4,
                        "elements": 3,
                        "materials": 1,
                        "sections": 1,
                        "boundary": True,
                        "load": True,
                    },
                ),
            )
            assert report.ok is True
            assert report.satisfied == ("model_complete",)
            assert report.unverified == ("software_connected", "capability_supported")

            # 事实齐备时能力不足才是失败。
            with pytest.raises(EngineeringValidationError) as excinfo:
                await evaluator.require(
                    operation,
                    ExecutionFacts(
                        resolved_resource=ResolvedResource(
                            resource_type=ResourceType.MODEL.value,
                            resource_id="model-1",
                            tenant_id="tenant-1",
                        ),
                        software_status="CONNECTED",
                        supported_capabilities=frozenset(),
                    ),
                )
            assert "capability_supported" in str(excinfo.value.details["issues"])

    asyncio.run(_run())


def test_model_incompleteness_blocks_analysis(sessions: SessionFactory) -> None:
    """门槛 ②：`ANALYSIS.STATIC` 的前置链（`docs/02` §23）逐项生效。"""

    async def _run() -> None:
        async with sessions() as session:
            evaluator = PreconditionEvaluator()
            operation = await _operation(session, "ANALYSIS.STATIC")

            # 模型不完整（缺材料 / 截面 / 边界 / 荷载）→ 一次报全（`docs/02` §23）。
            with pytest.raises(EngineeringValidationError) as incomplete:
                await evaluator.require(
                    operation,
                    ExecutionFacts(
                        resolved_resource=ResolvedResource(
                            resource_type=ResourceType.MODEL.value,
                            resource_id="model-1",
                            tenant_id="tenant-1",
                        ),
                        model_state={"nodes": 2, "elements": 0},
                    ),
                )
            issues = " ".join(incomplete.value.details["issues"])
            for key in ("elements", "materials", "sections", "boundary", "load"):
                assert key in issues, key

            # 荷载「存在但为 False」同样不算满足（`_is_present` 语义）。
            with pytest.raises(EngineeringValidationError) as no_load:
                await evaluator.require(
                    operation,
                    ExecutionFacts(
                        resolved_resource=ResolvedResource(
                            resource_type=ResourceType.MODEL.value,
                            resource_id="model-1",
                            tenant_id="tenant-1",
                        ),
                        model_state={
                            "nodes": 2,
                            "elements": 1,
                            "materials": 1,
                            "sections": 1,
                            "boundary": True,
                            "load": False,
                        },
                    ),
                )
            assert "load" in " ".join(no_load.value.details["issues"])

    asyncio.run(_run())


def test_postconditions_cover_the_spec_operations() -> None:
    """门槛 ②：后置条件目录覆盖 `docs/02` §32 的原文示例及其同族。"""
    assert "MODEL.NODE.CREATE" in POSTCONDITION_OPERATIONS
    assert "ANALYSIS.STATIC" in POSTCONDITION_OPERATIONS
    evaluator = PostconditionEvaluator()
    assert [item.name for item in evaluator.for_operation("ANALYSIS.STATIC")] == [
        "task_completed",
        "result_available",
    ]


def test_postcondition_failure_is_structai_5000(sessions: SessionFactory) -> None:
    """门槛 ②：后置条件不满足 → **`STRUCTAI-5000`**（见 `postconditions.py` 裁决 3）。"""

    async def _run() -> None:
        async with sessions() as session:
            evaluator = PostconditionEvaluator()
            operation = await _operation(session, "ANALYSIS.STATIC")

            with pytest.raises(TaskError) as excinfo:
                await evaluator.require(
                    operation,
                    ExecutionFacts(
                        task_status=TaskStatus.FAILED.value,
                        result_available=False,
                    ),
                )
            assert excinfo.value.code == "STRUCTAI-5000"
            assert excinfo.value.details["stage"] == "postconditions"

            ok = await evaluator.require(
                operation,
                ExecutionFacts(
                    task_status=TaskStatus.COMPLETED.value,
                    result_available=True,
                ),
            )
            assert ok.ok is True

    asyncio.run(_run())


def test_recovering_task_is_never_a_satisfied_postcondition(
    sessions: SessionFactory,
) -> None:
    """门槛 ②：恢复中的 Task **不得**视为已完成（`docs/07` §14.4）。"""

    async def _run() -> None:
        async with sessions() as session:
            evaluator = PostconditionEvaluator()
            operation = await _operation(session, "BUILD.COLUMN")

            for status in (TaskStatus.RECOVERING, TaskStatus.RETRYING, TaskStatus.RUNNING):
                with pytest.raises(TaskError):
                    await evaluator.require(
                        operation,
                        ExecutionFacts(task_status=status.value),
                    )

    asyncio.run(_run())


def test_engineering_validator_covers_the_docs_02_section_20_operations() -> None:
    """门槛 ②：工程规则表覆盖 `docs/02` §20 的 10 个 Operation（含同族补齐）。"""
    validator = EngineeringValidator()
    for operation in (
        "MODEL.NODE.CREATE",
        "MODEL.NODE.UPDATE",
        "MODEL.ELEMENT.CREATE",
        "MODEL.ELEMENT.UPDATE",
        "MODEL.BOUNDARY.ASSIGN",
        "MODEL.LOAD.ASSIGN",
        "BUILD.COLUMN",
        "BUILD.BEAM",
        "ANALYSIS.STATIC",
        "DESIGN.STEEL",
    ):
        assert operation in validator.operations
    assert MIN_ELEMENT_NODES == 2


def test_engineering_validator_rejects_null_coordinates_and_duplicate_nodes() -> None:
    """门槛 ②：坐标为 null / 节点 id 重复 → `STRUCTAI-1200`（`docs/02` §21 / §30）。"""
    validator = EngineeringValidator()

    assert validator.check("MODEL.NODE.CREATE", {"id": "n1", "x": 0.0, "y": 0.0, "z": 0.0}) == []
    assert validator.check("MODEL.NODE.CREATE", {"id": "n1", "x": None}) != []
    assert validator.check("MODEL.NODE.CREATE", {"node": {"y": None}}) != []
    assert validator.check("MODEL.NODE.CREATE", {"id": ""}) != []
    duplicated = validator.check(
        "MODEL.NODE.CREATE",
        {"nodes": [{"id": "n1"}, {"id": "n1"}]},
    )
    assert any("duplicate node id" in issue for issue in duplicated)


def test_engineering_validator_rejects_invalid_elements() -> None:
    """门槛 ②：元素少于两个节点 / 引用 null → `STRUCTAI-1200`（`docs/02` §22）。"""
    validator = EngineeringValidator()

    assert validator.check("MODEL.ELEMENT.CREATE", {"node_ids": ["n1", "n2"]}) == []
    assert validator.check("MODEL.ELEMENT.CREATE", {"node_ids": ["n1"]}) != []
    assert validator.check("MODEL.ELEMENT.CREATE", {"elements": [{"node_ids": ["n1"]}]}) != []
    assert validator.check("MODEL.ELEMENT.CREATE", {"elements": [{}]}) != []
    assert validator.check("MODEL.ELEMENT.CREATE", {"node_ids": ["n1", None]}) != []
    assert validator.check("MODEL.ELEMENT.CREATE", {"node_ids": "n1"}) != []


def test_engineering_validator_rejects_non_finite_and_zero_length() -> None:
    """门槛 ②：NaN / Inf 与零长度一律拒绝（`docs/02` §31「长度不得为 0」）。"""
    validator = EngineeringValidator()

    assert validator.check("ANALYSIS.STATIC", {"damping": 0.05}) == []
    assert validator.check("ANALYSIS.STATIC", {"damping": float("nan")}) != []
    assert validator.check("ANALYSIS.STATIC", {"nested": [{"value": float("inf")}]}) != []
    assert validator.check("BUILD.COLUMN", {"length": 3.0}) == []
    assert validator.check("BUILD.COLUMN", {"length": 0}) != []
    assert validator.check("BUILD.COLUMN", {"length": "3"}) != []


def test_engineering_validator_reports_issues_once_not_short_circuits() -> None:
    """门槛 ②：一次报全（不逐个报错），并给出 `details.issues`（`docs/02` §19）。"""

    async def _run() -> None:
        validator = EngineeringValidator()
        with pytest.raises(EngineeringValidationError) as excinfo:
            await validator.validate(
                "MODEL.ELEMENT.CREATE",
                {"node_ids": [None]},
                None,
            )
        assert excinfo.value.code == "STRUCTAI-1200"
        assert excinfo.value.details["stage"] == "engineering"
        assert len(excinfo.value.details["issues"]) >= 2

    asyncio.run(_run())


def test_engineering_validator_is_pure() -> None:
    """门槛 ②：Validator **不持有**任何存储 / 会话（`docs/02` §70）。"""
    validator = EngineeringValidator()
    assert [name for name in vars(validator) if "store" in name or "session" in name] == []

    imports = _imported_modules(EXECUTION_DIR / "engineering_validator.py")
    assert not [name for name in imports if name.startswith("app.infrastructure")]


# ===== ⑥ 回归（`python -m app.main` / P04 / P02）=====


def test_batch_id_is_a_batch_marker() -> None:
    """同步改动：`BATCH_ID` 形如 `P<两位数字>`（`docs/08` §3 的批次口径）。"""
    assert re.fullmatch(r"P\d{2}", BATCH_ID)


def test_main_exits_zero_with_empty_stdout_on_an_unprovisioned_database(
    tmp_path: Path,
) -> None:
    """门槛 ⑥：未配备库 → 退出码 0、**stdout 0 字节**、Registry 留空但进程正常结束。"""
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p14_empty.db').as_posix()}"
    completed = _run_main(database_url)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert f"batch={BATCH_ID}" in completed.stderr
    assert "operation registry is not assembled" in completed.stderr


def test_main_exits_zero_with_empty_stdout_on_a_provisioned_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ⑥：已配备库（建表 + Seed）→ 退出码 0、**stdout 0 字节**、Registry 就绪。"""
    database_url = asyncio.run(_provision(tmp_path, monkeypatch, "p14_main_cli.db"))
    completed = _run_main(database_url)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert f"batch={BATCH_ID}" in completed.stderr
    assert "registry ready" in completed.stderr


def test_p04_tables_and_select_one_are_not_regressed(seeded_engine: AsyncEngine) -> None:
    """门槛 ⑥（P04）：建表 **24** 张（与 24 个 ORM Model 一一对应）+ `SELECT 1` → 1。"""

    async def _run() -> None:
        async with seeded_engine.connect() as connection:
            names = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_table_names()
            )
            assert len(names) == 24
            assert len(Base.metadata.tables) == 24
            result = await connection.exec_driver_sql("SELECT 1")
            assert result.scalar_one() == 1

    asyncio.run(_run())


def test_p02_settings_override_is_not_regressed(monkeypatch: pytest.MonkeyPatch) -> None:
    """门槛 ⑥（P02）：环境变量覆盖默认值（`docs/07` §12 P02）。"""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./data/p14_gate.db")
    monkeypatch.setenv("LOCK_DEFAULT_TIMEOUT_SECONDS", "77")
    monkeypatch.setenv("CAPABILITY_CACHE_SECONDS", "88")

    overridden = Settings()

    assert overridden.log_level == "DEBUG"
    assert overridden.database_url == "sqlite+aiosqlite:///./data/p14_gate.db"
    assert overridden.lock_default_timeout_seconds == 77
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
    """门槛 ⑦：容器字段仍为 `docs/02` §33 的冻结形状（P14 **不**加资源 / 能力字段）。"""
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
    assert [name for name in names if "resource" in name or "capability" in name] == []


def test_application_execution_layers_do_not_depend_on_infrastructure() -> None:
    """门槛 ⑦：Application 新层不依赖 `app.infrastructure`（`docs/07` §14.1 / §2.2）。"""
    offenders: list[str] = []
    for relative in INFRASTRUCTURE_FREE_MODULES:
        for module in _imported_modules(_relative_path(relative)):
            if module.startswith("app.infrastructure") or module.startswith("app.interfaces"):
                offenders.append(f"{relative} → {module}")
            if module.split(".")[0] in {"sqlalchemy", "fastapi", "mcp", "httpx"}:
                offenders.append(f"{relative} → {module}")
    assert offenders == []


def test_p14_modules_never_commit() -> None:
    """门槛 ⑦：新模块不得 `commit` / `rollback`（边界归 `UnitOfWork`，`docs/07` §14.4）。"""
    for relative in P14_MODULES:
        assert _commit_or_rollback_calls(_relative_path(relative)) == [], relative
    assert (
        _commit_or_rollback_calls(
            _relative_path("app/infrastructure/database/repositories/resource.py")
        )
        == []
    )


def test_p14_modules_exist_and_are_exported() -> None:
    """门槛 ⑦：`docs/07` §3.3 冻结结构中的 9 个新模块全部存在且可导入。"""
    for relative in P14_MODULES:
        assert _relative_path(relative).is_file(), relative
    assert {path.name for path in RESOURCE_DIR.glob("*.py")} >= {
        "resolver.py",
        "lock_manager.py",
        "lock_policy.py",
        "__init__.py",
    }
    assert {path.name for path in SERVICES_DIR.glob("*.py")} >= {
        "capability_resolver.py",
        "__init__.py",
    }


def test_resource_store_repository_is_read_only(sessions: SessionFactory) -> None:
    """门槛 ⑦：`ResourceStore` 实现只读（不发 `flush` / 写语句；`docs/07` §14.4）。"""

    async def _run() -> None:
        async with sessions() as session:
            store = build_resource_store(session)
            assert hasattr(store, "tenant_ids_binding_instance")
            assert await store.project(str(uuid4())) is None
            assert await store.model(str(uuid4())) is None
            assert await store.document(str(uuid4())) is None
            assert await store.software_instance(str(uuid4())) is None
            assert await store.tenant_ids_binding_instance(str(uuid4())) == frozenset()
            assert len(session.new) == 0

    asyncio.run(_run())


# ===== ⑧ 红线（`docs/07` §14）=====


def test_twenty_code_contract_is_not_extended() -> None:
    """门槛 ⑧：20 码契约不扩（本批复用既有 1000 / 1200 / 3000 / 4100 / 4200 / 5000 / 6100）。"""
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
        ("STRUCTAI-3000", CapabilityError),
        ("STRUCTAI-4100", ConfirmationRequiredError),
        ("STRUCTAI-4200", TenantAccessDeniedError),
        ("STRUCTAI-5000", TaskError),
        ("STRUCTAI-6100", ResourceLockedError),
        ("STRUCTAI-1200", EngineeringValidationError),
    ):
        assert exception.code == code


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
            if module.split(".")[0] in {"sqlalchemy", "fastapi", "mcp", "httpx"}:
                offenders.append(f"{path.name} → {module}")
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
