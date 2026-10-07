"""P10–P13 验收测试：Security（`docs/07` §12 P10–P13；`docs/02` §6 / §10–§33 / §40–§63）。

验收点（与续接提示词的 ①–⑨ 一一对应）：

① 主门槛（`docs/07` §12 P10–P13 / `docs/02` §115）：`Authentication` → `Session` →
   `RBAC` → `Effective Permission` 四步全通，且**必须先于任何写操作**
   （`docs/07` §9 流水线第 2–4 / 11 步）—— 由 `SECURITY_CHAIN_ORDER` + 「授权路径零写入」
   两条证据覆盖；
② 认证：口令只经 `PasswordService`（Argon2id）校验；失败口径 = 既有 `STRUCTAI-4000`
   （`STRUCTAI-4001` 不在 20 码契约内，见 `authentication.py` 裁决）；**不泄露用户是否存在**
   （同一错误形状 + 同一耗时口径）；
③ 会话：库中**只存 token hash**（明文 token 绝不落库 / 落日志 / 进响应）；按
   `session_expire_seconds` 过期；注销后立即失效；
④ RBAC：`roles` / `role_permissions`（24 条 = 12 + 9 + 3 + 0）与 `docs/07` §5.7 的 4 角色
   逐条一致；
⑤ Effective Permission = 用户角色权限 ∪ 项目成员权限 − 显式拒绝；全局 / 租户 / 用户 /
   实例四级取**最严格**；跨租户 → `STRUCTAI-4200`；
⑥ `ai_agent` **不得提权**（= 用户有效权限 ∩ Agent 权限）；
⑦ 回归：`python -m app.main` 退出码 0（**stdout 0 字节**；未配备库与已配备库两种情形）、
   P04 建表 24 张 / `SELECT 1`、P02 覆盖行为、既有 **98 项 pytest 不得回退**
   （由整轮 `pytest -q` 与验收证据覆盖；本文件只补 `app.main` 两条）；
⑧ 质量：`ruff` / `mypy` 覆盖；本文件额外断言依赖清单**未扩**、容器形状**未变**、
   Application 安全层**不依赖** Infrastructure、安全模块**不得 `commit`**；
⑨ 红线：`app/` 内厂商名 0 处、`app/domain/` 无 SQLAlchemy、不新增 `STRUCTAI-xxxx` 码、
   新增 Settings 字段必须同步 `.env.example`（本批未新增，由清单比对固化）。

⚠️ 本文件里的「规范原文副本」（20 码清单 / 4 角色 × 权限 / 24 条 RolePermission / 依赖清单）
**故意不**从被测模块取：若断言只与被测常量比较，「常量被改错」与「实现被改错」会一起通过
（同源循环）。
"""

from __future__ import annotations

import ast
import asyncio
import os
import re
import subprocess
import sys
import time
import tomllib
from collections.abc import AsyncIterator, Collection, Sequence
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from argon2 import PasswordHasher
from sqlalchemy import event, inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.security import (
    AUTHENTICATION_METHOD_PASSWORD,
    AUTHENTICATION_METHOD_TOKEN,
    SECURITY_CHAIN_ORDER,
    AgentPermissionService,
    AuthenticationService,
    EffectivePermissionService,
    IdentityContext,
    InMemoryResourceACLLookup,
    NullResourceACLLookup,
    PasswordService,
    ProjectAccessService,
    RBACService,
    RoleService,
    SecurityGuard,
    SecurityServices,
    SessionService,
    TenantAccessService,
    TokenService,
    build_security_services,
)
from app.application.security.permission import (
    ACL_DECISION_PRIORITY,
    TENANT_ACCESS_DENIED_MESSAGE,
    acl_decision_for,
    entry_matches_resource,
)
from app.application.security.session import (
    INVALID_SESSION_MESSAGE,
    SESSION_FAILURE_REASONS,
)
from app.config.settings import Settings
from app.container import BATCH_ID, AppContainer
from app.domain.enums import (
    ACLPrincipalType,
    ACLScope,
    AuthenticationMethod,
    PermissionCode,
    PermissionEffect,
    RoleName,
)
from app.domain.errors import (
    PermissionDeniedError,
    StructAIError,
    TenantAccessDeniedError,
)
from app.domain.protocols import ResourceACLEntry
from app.infrastructure.database import Base, create_engine, create_session_factory
from app.infrastructure.database.models import (
    PermissionORM,
    ProjectMemberORM,
    ProjectORM,
    RoleORM,
    RolePermissionORM,
    SessionORM,
    TenantORM,
    UserORM,
    UserRoleORM,
)
from app.infrastructure.database.repositories import (
    UserRepository,
    build_security_stores,
)
from app.infrastructure.database.seed import (
    ADMIN_PASSWORD_ENV,
    ROLE_NAMES,
    ROLE_PERMISSIONS,
    seed,
)
from app.infrastructure.database.unit_of_work import UnitOfWork

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
SECURITY_DIR = APP_DIR / "application" / "security"

VENDOR_NAMES = ("MIDAS", "CSI", "ANSYS")
"""`docs/07` §14.2：`app/` 内禁止出现的厂商名。"""

TEST_PASSWORD = "P10-Security-验收-口令-7c41"
"""测试用口令（非真实 secret，仅存在于测试进程内）。"""

SessionFactory = async_sessionmaker[AsyncSession]
"""会话工厂类型别名（`docs/02` §15）。"""

FAST_HASHER = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
"""测试造数据用的低开销 Argon2id 参数。

⚠️ 只用于生成测试用户的 `password_hash`；认证路径仍然只经 `PasswordService`
（`docs/02` §7）。Argon2 的自描述哈希里带参数，故低开销哈希与默认参数哈希可互相校验，
不影响被测逻辑。
"""


# ===== 规范原文副本（`docs/07` §5.7 / §11；`docs/02` §5 / §71 / §72）=====

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

EXPECTED_ROLE_PERMISSIONS = {
    # `docs/07` §5.7 / `docs/02` §72 —— 逐条硬编码的规范原文副本。
    "system_admin": tuple(code.value for code in PermissionCode),  # 12 = ALL
    "engineer": (
        "MODEL_READ",
        "MODEL_WRITE",
        "MODEL_DELETE",
        "ANALYSIS_EXECUTE",
        "DESIGN_EXECUTE",
        "DESIGN_MODIFY",
        "RESULT_READ",
        "DOCUMENT_READ",
        "DOCUMENT_WRITE",
    ),  # 9
    "viewer": ("MODEL_READ", "RESULT_READ", "DOCUMENT_READ"),  # 3
    "ai_agent": (),  # 0（动态求交，不得静态授予）
}
"""4 个角色的权限映射（`docs/07` §5.7；`docs/02` §72）。"""

EXPECTED_ROLE_PERMISSION_ROWS = 24
"""`role_permissions` 行数 = 12 + 9 + 3 + 0（`docs/07` §12 P10–P13 门槛 ④）。"""

SECURITY_MODULES = (
    "context.py",
    "token.py",
    "session.py",
    "rbac.py",
    "permission.py",
    "authentication.py",
)
"""本批的 6 个 Application 安全模块（`docs/07` §3.3 冻结结构 + `docs/02` §24）。"""

INFRASTRUCTURE_FREE_MODULES = (
    "app/application/security/__init__.py",
    "app/application/security/authentication.py",
    "app/application/security/context.py",
    "app/application/security/permission.py",
    "app/application/security/rbac.py",
    "app/application/security/session.py",
    "app/application/security/token.py",
)
"""红线检查范围：Application 安全层全部文件（`docs/07` §14.1 / §2.2）。"""


# ===== 夹具与辅助 =====


@pytest.fixture
async def seeded_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncEngine]:
    """临时 SQLite + 建表 + 真实 Seed（`docs/02` §15 / §36 / §43–§46）。"""
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p10_security.db').as_posix()}"
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


def _services(
    session: AsyncSession,
    *,
    lifetime_seconds: int = 3600,
    resource_acl: Any = None,
    agent_permissions: Collection[str] | None = None,
    password_service: PasswordService | None = None,
    max_failed_attempts: int = 5,
) -> SecurityServices:
    """按会话装配安全服务（`docs/02` §33 / §123）。"""
    return build_security_services(
        build_security_stores(session),
        password_service=password_service or PasswordService(FAST_HASHER),
        session_lifetime_seconds=lifetime_seconds,
        resource_acl=resource_acl,
        agent_permissions=agent_permissions,
        max_failed_attempts=max_failed_attempts,
    )


async def _default_tenant_id(session: AsyncSession) -> str:
    """默认租户的 id（Seed 落库的唯一租户）。"""
    result = await session.execute(select(TenantORM.id).order_by(TenantORM.created_at))
    return str(result.scalars().first())


async def _add_user(
    session: AsyncSession,
    *,
    tenant_id: str,
    username: str,
    role_names: Sequence[str] = (),
    password: str = TEST_PASSWORD,
    is_active: bool = True,
    locked: bool = False,
) -> str:
    """插入一个用户（可选多个角色）并返回其 id。"""
    user = UserORM(
        tenant_id=str(tenant_id),
        username=username,
        password_hash=PasswordService(FAST_HASHER).hash(password),
        is_active=is_active,
        locked=locked,
        failed_login_count=0,
    )
    session.add(user)
    await session.flush()
    for role_name in role_names:
        result = await session.execute(
            select(RoleORM.id).where(
                RoleORM.tenant_id == str(tenant_id),
                RoleORM.name == role_name,
            )
        )
        session.add(UserRoleORM(user_id=user.id, role_id=result.scalar_one()))
    await session.flush()
    return str(user.id)


async def _add_tenant_with_project(
    session: AsyncSession,
    *,
    tenant_name: str,
    project_name: str,
) -> tuple[str, str]:
    """新建租户 + 项目（跨租户场景），返回 `(tenant_id, project_id)`。"""
    tenant = TenantORM(name=tenant_name)
    session.add(tenant)
    await session.flush()
    project = ProjectORM(tenant_id=tenant.id, name=project_name)
    session.add(project)
    await session.flush()
    return str(tenant.id), str(project.id)


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


def _write_verbs(statements: Sequence[str]) -> list[str]:
    """语句里的写动词（INSERT / UPDATE / DELETE / REPLACE）。

    用于「授权路径零写入」断言（`docs/07` §9：鉴权先于写操作）。
    """
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
    name: str = "p10_main.db",
) -> str:
    """建表 + Seed 一个临时库，返回其 `database_url`（供容器 / CLI 验收使用）。"""
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


class _CountingPasswordService(PasswordService):
    """记录 `verify` 调用次数的口令服务（门槛 ② 的耗时口径证据）。"""

    def __init__(self) -> None:
        super().__init__(FAST_HASHER)
        self.verify_calls = 0

    def verify(self, password_hash: str, password: str) -> bool:
        """计数后委托真实实现（`docs/02` §7 的参数顺序不变）。"""
        self.verify_calls += 1
        return super().verify(password_hash, password)


def _entry(
    *,
    permission: str,
    effect: PermissionEffect,
    scope: ACLScope,
    principal_type: ACLPrincipalType,
    principal_id: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
) -> ResourceACLEntry:
    """构造一条 ACL 条目（`docs/02` §25 / §27）。"""
    return ResourceACLEntry(
        principal_type=principal_type,
        principal_id=principal_id,
        permission=permission,
        effect=effect,
        scope=scope,
        resource_type=resource_type,
        resource_id=resource_id,
    )


# ===== ① 主门槛（`docs/07` §12 P10–P13 / `docs/02` §115）=====


def test_gate_chain_order_matches_the_frozen_pipeline() -> None:
    """门槛 ①：四步链顺序冻结为 Authentication → Session → RBAC → Effective Permission。"""
    assert SECURITY_CHAIN_ORDER == (
        "Authentication",
        "Session",
        "RBAC",
        "Effective Permission",
    )


def test_identity_context_is_frozen_and_server_generated() -> None:
    """门槛 ①：`IdentityContext` 不可变、`roles` 规整为 tuple（`docs/02` §26）。"""
    identity = IdentityContext(user_id=uuid4(), tenant_id=uuid4(), roles=["viewer"])  # type: ignore[arg-type]

    assert identity.roles == ("viewer",)
    assert identity.authentication_method == "unknown"
    with pytest.raises(FrozenInstanceError):
        identity.user_id = uuid4()  # type: ignore[misc]


def test_authentication_methods_are_the_frozen_enum_values() -> None:
    """门槛 ①：认证方式取值取自 `AuthenticationMethod`（`docs/02` §5；不新造取值）。"""
    assert AUTHENTICATION_METHOD_PASSWORD == AuthenticationMethod.PASSWORD.value
    assert AUTHENTICATION_METHOD_TOKEN == AuthenticationMethod.TOKEN.value
    assert AUTHENTICATION_METHOD_PASSWORD != "password"  # 规范小写写法被归一化


def test_gate_authentication_then_session_then_rbac_then_effective_permission(
    sessions: SessionFactory,
) -> None:
    """门槛 ①（主门槛）：认证 → 会话 → RBAC → 有效权限 四步全通（`docs/02` §47）。"""

    async def _run() -> None:
        async with sessions() as session:
            services = _services(session)

            # ① Authentication：口令只经 PasswordService 校验（docs/02 §16）。
            login = await services.guard.login("admin", TEST_PASSWORD)
            assert login.identity.roles == ("system_admin",)
            assert login.identity.authentication_method == AUTHENTICATION_METHOD_PASSWORD
            assert login.access_token
            assert login.session_id == str(login.identity.session_id)

            # ② Session：token → 服务端身份（docs/02 §20）。
            identity = await services.guard.authenticate(login.access_token)
            assert (
                identity.user_id,
                identity.tenant_id,
                identity.session_id,
                identity.roles,
            ) == (
                login.identity.user_id,
                login.identity.tenant_id,
                login.identity.session_id,
                login.identity.roles,
            )
            assert identity.authentication_method == AUTHENTICATION_METHOD_TOKEN

            # ③ RBAC：角色 → 权限（docs/02 §23 / §30 第 1–2 步）。
            assert await services.roles.get_user_roles(str(identity.user_id)) == ["system_admin"]
            assert await services.rbac.has_permission(identity, PermissionCode.MODEL_READ.value)
            assert await services.rbac.has_permission(identity, PermissionCode.SYSTEM_ADMIN.value)
            await services.rbac.require_permission(identity, PermissionCode.MODEL_DELETE.value)

            # ④ Effective Permission：system_admin = 12 条全量（docs/07 §5.7）。
            permissions = await services.permissions.resolve(identity)
            assert permissions == set(EXPECTED_ROLE_PERMISSIONS["system_admin"])

            context = await services.guard.build_context(login.access_token)
            assert context.permissions == frozenset(permissions)
            assert context.identity == identity
            assert context.authenticated is True

    asyncio.run(_run())


def test_authorization_path_performs_no_writes(
    seeded_engine: AsyncEngine,
    sessions: SessionFactory,
) -> None:
    """门槛 ①：认证 + 授权路径**零写入** —— 因此可以先于任何写操作执行（`docs/07` §9）。

    `docs/07` §9 把 `Authenticate`（第 2 步）与 `Effective Permission`（第 11 步）都排在
    写操作之前；本用例用 SQL 级钩子证明这两步只发 `SELECT`。
    """
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
            services = _services(session)
            async with UnitOfWork(session):
                login = await services.guard.login("admin", TEST_PASSWORD)

            statements.clear()  # 登录含会话 INSERT，不算授权路径
            identity = await services.guard.authenticate(login.access_token)
            await services.rbac.require_permission(identity, PermissionCode.MODEL_READ.value)
            await services.permissions.resolve(identity)

    event.listen(seeded_engine.sync_engine, "before_cursor_execute", _record)
    try:
        asyncio.run(_run())
    finally:
        event.remove(seeded_engine.sync_engine, "before_cursor_execute", _record)

    assert statements, "授权路径应当至少发出读查询"
    assert _write_verbs(statements) == []


# ===== ② 认证（`docs/02` §16–§18；门槛 ②）=====


def test_login_failure_shape_is_identical_for_unknown_user_and_wrong_password(
    sessions: SessionFactory,
) -> None:
    """门槛 ②：三种失败情形**形状完全一致**（不泄露用户是否存在，`docs/02` §17）。"""

    async def _run() -> None:
        async with sessions() as session:
            services = _services(session)
            shapes: list[tuple[str, str, str, dict[str, Any]]] = []
            for username in ("admin", "no-such-user"):
                with pytest.raises(PermissionDeniedError) as excinfo:
                    await services.guard.login(username, "definitely-wrong")
                error = excinfo.value
                shapes.append((error.code, error.error_type, error.message, dict(error.details)))

            assert shapes[0] == shapes[1]
            assert shapes[0][0] == "STRUCTAI-4000"
            assert shapes[0][2] == "Invalid username or password"
            assert shapes[0][3] == {
                "stage": "authentication",
                "reason": "invalid_credentials",
            }

    asyncio.run(_run())


def test_inactive_and_locked_accounts_share_the_same_failure_shape(
    sessions: SessionFactory,
) -> None:
    """门槛 ②：停用 / 锁定账号的失败形状与口令错误一致（`docs/02` §17）。"""

    async def _run() -> None:
        async with sessions() as session:
            services = _services(session)
            tenant_id = await _default_tenant_id(session)
            await _add_user(
                session,
                tenant_id=tenant_id,
                username="inactive-user",
                is_active=False,
            )
            await _add_user(
                session,
                tenant_id=tenant_id,
                username="locked-user",
                locked=True,
            )
            async with UnitOfWork(session):
                pass

        async with sessions() as session:
            services = _services(session)
            shapes = []
            for username in ("inactive-user", "locked-user"):
                with pytest.raises(PermissionDeniedError) as excinfo:
                    await services.guard.login(username, TEST_PASSWORD)
                shapes.append((excinfo.value.code, excinfo.value.message))
            assert shapes == [
                ("STRUCTAI-4000", "Invalid username or password"),
                ("STRUCTAI-4000", "Invalid username or password"),
            ]

    asyncio.run(_run())


def test_password_is_verified_exactly_once_on_every_path(sessions: SessionFactory) -> None:
    """门槛 ②：每条路径**恰好一次** Argon2 校验（同一耗时口径，`docs/02` §17）。"""

    async def _run() -> None:
        async with sessions() as session:
            counting = _CountingPasswordService()
            services = _services(session, password_service=counting)

            counting.verify_calls = 0
            await services.guard.login("admin", TEST_PASSWORD)
            assert counting.verify_calls == 1

            counting.verify_calls = 0
            with pytest.raises(PermissionDeniedError):
                await services.guard.login("admin", "wrong-password")
            assert counting.verify_calls == 1

            counting.verify_calls = 0
            with pytest.raises(PermissionDeniedError):
                await services.guard.login("ghost-user", "wrong-password")
            assert counting.verify_calls == 1

    asyncio.run(_run())


def test_failure_paths_have_the_same_cost_profile(sessions: SessionFactory) -> None:
    """门槛 ②：未知用户与口令错误的**实测耗时同量级**（哑哈希对齐耗时，`docs/02` §17）。

    使用规范默认 Argon2 参数（`PasswordService()`），并先预热一次未知用户路径
    （首次会生成哑哈希，属一次性开销）。
    """

    async def _run() -> None:
        async with sessions() as session:
            services = _services(session, password_service=PasswordService())

            with pytest.raises(PermissionDeniedError):
                await services.guard.login("warm-up-unknown", "wrong-password")

            durations: list[float] = []
            for username in ("admin", "unknown-user"):
                started = time.perf_counter()
                with pytest.raises(PermissionDeniedError):
                    await services.guard.login(username, "wrong-password")
                durations.append(time.perf_counter() - started)

            fastest, slowest = min(durations), max(durations)
            assert fastest > 0.001, "Argon2 校验应当有可测量的成本"
            assert slowest < fastest * 5, f"耗时口径差异过大: {durations}"

    asyncio.run(_run())


def test_authentication_verifies_only_through_the_password_service() -> None:
    """门槛 ②：认证模块不得自行哈希 / 比较口令（只经 `PasswordService`，`docs/02` §7）。"""
    modules = _imported_modules(SECURITY_DIR / "authentication.py")
    assert "argon2" not in modules
    assert "hashlib" not in modules
    assert "app.application.security.password" in modules
    assert _commit_or_rollback_calls(SECURITY_DIR / "authentication.py") == []


def test_failed_login_counter_and_lock_threshold_are_enforced(sessions: SessionFactory) -> None:
    """门槛 ②：连续失败计数 + 达阈值锁定（`docs/02` §18）。"""

    async def _run() -> None:
        async with sessions() as session:
            services = _services(session, max_failed_attempts=3)
            for _ in range(2):
                with pytest.raises(PermissionDeniedError):
                    await services.guard.login("admin", "wrong-password")
            result = await session.execute(select(UserORM.failed_login_count, UserORM.locked))
            assert result.one() == (2, False)

            async with UnitOfWork(session):
                with pytest.raises(PermissionDeniedError):
                    await services.guard.login("admin", "wrong-password")
            assert (
                await session.execute(select(UserORM.failed_login_count, UserORM.locked))
            ).one() == (
                3,
                True,
            )

            # 解锁必须显式发生（docs/02 §18：不要永久锁死账号）。
            async with UnitOfWork(session):
                await services.authentication.unlock(
                    str((await session.execute(select(UserORM.id))).scalar_one())
                )
            assert (
                await session.execute(select(UserORM.failed_login_count, UserORM.locked))
            ).one() == (
                0,
                False,
            )

    asyncio.run(_run())


# ===== ③ 会话 / Token（`docs/02` §10–§13 / §19–§21；门槛 ③）=====


def test_token_service_matches_the_spec() -> None:
    """门槛 ③：token 生成 / 哈希 / 指纹口径（`docs/02` §12 / §13 / §58）。"""
    service = TokenService()
    token = service.generate()

    assert len(token) >= 60  # token_urlsafe(48) → 64 字符左右
    assert service.hash(token) == hashlib_sha256_hex(token)
    assert len(service.hash(token)) == 64  # 落在 sessions.token_hash String(128) 内
    assert service.generate() != token
    assert service.fingerprint(token) == service.hash(token)[:12]
    assert service.fingerprint(token) != token


def hashlib_sha256_hex(value: str) -> str:
    """规范原文副本：`hashlib.sha256(value.encode()).hexdigest()`（`docs/02` §12）。"""
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _all_text_values(session: AsyncSession) -> list[str]:
    """全库文本列的值（用于「明文 token / 口令绝不落库」的扫描断言）。"""
    values: list[str] = []
    for table in Base.metadata.sorted_tables:
        result = await session.execute(select(table))
        for row in result.mappings():
            values.extend(value for value in row.values() if isinstance(value, str))
    return values


def test_only_token_hash_is_stored_and_the_raw_token_never_touches_the_database(
    sessions: SessionFactory,
) -> None:
    """门槛 ③：库中只有 `token_hash`；明文 token 与明文口令都不落库（`docs/02` §13 / §54）。"""

    async def _run() -> None:
        async with sessions() as session:
            services = _services(session)
            async with UnitOfWork(session):
                login = await services.guard.login("admin", TEST_PASSWORD)

            stored = list((await session.execute(select(SessionORM.token_hash))).scalars().all())
            assert stored == [TokenService().hash(login.access_token)]
            assert login.access_token not in stored

            dumped = " ".join(await _all_text_values(session))
            assert login.access_token not in dumped
            assert TEST_PASSWORD not in dumped

            # 明文 token 也不得出现在 `repr` 里（避免日志 / 异常把它带出去）。
            assert login.access_token not in repr(login)

    asyncio.run(_run())


def test_session_lifetime_follows_the_setting(sessions: SessionFactory) -> None:
    """门槛 ③：会话按 `session_expire_seconds` 过期（`docs/07` §3.1 / §8.3）。"""
    setting = Settings().session_expire_seconds

    async def _run() -> None:
        async with sessions() as session:
            services = _services(session, lifetime_seconds=setting)
            assert services.sessions.lifetime_seconds == setting

            started = datetime.now(UTC)
            async with UnitOfWork(session):
                login = await services.guard.login("admin", TEST_PASSWORD)
            expires_at = (
                await session.execute(
                    select(SessionORM.expires_at).where(SessionORM.id == login.session_id)
                )
            ).scalar_one()
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            delta = expires_at - started
            assert abs(delta - timedelta(seconds=setting)) < timedelta(seconds=30)

    asyncio.run(_run())


def test_expired_session_is_rejected_and_creates_no_identity(sessions: SessionFactory) -> None:
    """门槛 ③：过期会话被拒且**不产生** `IdentityContext`（`docs/02` §53）。"""

    async def _run() -> None:
        async with sessions() as session:
            services = _services(session, lifetime_seconds=-1)
            async with UnitOfWork(session):
                login = await services.guard.login("admin", TEST_PASSWORD)

            identity: IdentityContext | None = None
            with pytest.raises(PermissionDeniedError) as excinfo:
                identity = await services.guard.authenticate(login.access_token)
            assert identity is None
            assert excinfo.value.code == "STRUCTAI-4000"
            assert excinfo.value.message == INVALID_SESSION_MESSAGE
            assert excinfo.value.details["reason"] == "session_expired"

    asyncio.run(_run())


def test_logout_invalidates_the_session_immediately(sessions: SessionFactory) -> None:
    """门槛 ③：注销后立即失效（`docs/02` §11 / §21）。"""

    async def _run() -> None:
        async with sessions() as session:
            services = _services(session)
            async with UnitOfWork(session):
                login = await services.guard.login("admin", TEST_PASSWORD)
            await services.guard.authenticate(login.access_token)

            async with UnitOfWork(session):
                assert await services.guard.logout(login.session_id) is True
            with pytest.raises(PermissionDeniedError) as excinfo:
                await services.guard.authenticate(login.access_token)
            assert excinfo.value.details["reason"] == "session_revoked"

            # 重复注销：不再报告「刚撤销」（避免存在性泄露，docs/02 §48）。
            async with UnitOfWork(session):
                assert await services.guard.logout(login.session_id) is False

    asyncio.run(_run())


def test_locked_user_invalidates_existing_sessions(sessions: SessionFactory) -> None:
    """门槛 ③：用户锁定 → 既有会话立即失效（`docs/07` §8.3）。"""

    async def _run() -> None:
        async with sessions() as session:
            services = _services(session)
            async with UnitOfWork(session):
                login = await services.guard.login("admin", TEST_PASSWORD)
            await services.guard.authenticate(login.access_token)

            async with UnitOfWork(session):
                await UserRepository(session).set_locked(str(login.identity.user_id), locked=True)
            with pytest.raises(PermissionDeniedError) as excinfo:
                await services.guard.authenticate(login.access_token)
            assert excinfo.value.details["reason"] == "user_inactive"

    asyncio.run(_run())


def test_session_failure_shapes_are_uniform(sessions: SessionFactory) -> None:
    """门槛 ③：会话失败的对外形状一致（`STRUCTAI-4000` + 固定 `details` 键集合）。"""

    async def _run() -> None:
        async with sessions() as session:
            services = _services(session, lifetime_seconds=-1)
            async with UnitOfWork(session):
                expired = await services.guard.login("admin", TEST_PASSWORD)
            async with UnitOfWork(session):
                revoked = await services.guard.login("admin", TEST_PASSWORD)
                await services.sessions.revoke(revoked.session_id)

            shapes = []
            for token in ("not-a-real-token", expired.access_token, revoked.access_token):
                with pytest.raises(PermissionDeniedError) as excinfo:
                    await services.guard.authenticate(token)
                error = excinfo.value
                shapes.append(
                    (
                        error.code,
                        error.error_type,
                        error.message,
                        tuple(sorted(error.details)),
                    )
                )

            assert len(set(shapes)) == 1
            assert shapes[0] == (
                "STRUCTAI-4000",
                "PERMISSION_DENIED",
                INVALID_SESSION_MESSAGE,
                ("reason", "stage"),
            )

    asyncio.run(_run())


def test_session_failure_reasons_are_the_frozen_vocabulary() -> None:
    """门槛 ③：会话失败原因的机器可读词表（服务端诊断用）。"""
    assert SESSION_FAILURE_REASONS == (
        "unknown_session",
        "session_revoked",
        "session_expired",
        "user_inactive",
    )
    assert INVALID_SESSION_MESSAGE == "Invalid session"


def test_session_service_never_logs_or_returns_the_token_hash(sessions: SessionFactory) -> None:
    """门槛 ③：`SessionRecord` 不携带 `token_hash`（`docs/07` §14.3：绝不记录 secret）。"""
    from app.domain.protocols import SessionRecord

    assert [field.name for field in fields(SessionRecord)] == [
        "id",
        "user_id",
        "tenant_id",
        "expires_at",
        "revoked",
        "last_seen_at",
    ]

    async def _run() -> None:
        async with sessions() as session:
            services = _services(session)
            async with UnitOfWork(session):
                login = await services.guard.login("admin", TEST_PASSWORD)
            record = await build_security_stores(session).sessions.get_by_token_hash(
                TokenService().hash(login.access_token)
            )
            assert record is not None
            assert login.access_token not in repr(record)
            assert TokenService().hash(login.access_token) not in repr(record)

    asyncio.run(_run())


# ===== ④ RBAC（`docs/07` §5.7 / §8.2；`docs/02` §23 / §72；门槛 ④）=====
def test_spec_copies_are_self_consistent() -> None:
    """门槛 ④：本文件内硬编码的规范副本自检（12 权限 / 4 角色 / 24 条 / 20 码）。"""
    assert len(PermissionCode) == 12
    assert len(EXPECTED_ROLE_PERMISSIONS) == 4
    assert sum(len(codes) for codes in EXPECTED_ROLE_PERMISSIONS.values()) == (
        EXPECTED_ROLE_PERMISSION_ROWS
    )
    assert tuple(EXPECTED_ROLE_PERMISSIONS) == ROLE_NAMES
    assert {
        name: tuple(code.value for code in codes) for name, codes in ROLE_PERMISSIONS.items()
    } == EXPECTED_ROLE_PERMISSIONS
    assert len(TWENTY_CODE_CONTRACT) == 20


def test_role_name_enum_matches_the_seed_vocabulary() -> None:
    """门槛 ④：`RoleName` 与 P07 Seed 的 4 个角色名逐一一致（防漂移）。"""
    assert tuple(role.value for role in RoleName) == ROLE_NAMES
    assert tuple(role.value for role in RoleName) == tuple(EXPECTED_ROLE_PERMISSIONS)


def test_seeded_role_permission_matrix_matches_the_spec(sessions: SessionFactory) -> None:
    """门槛 ④：P07 落库的 `roles` / `role_permissions` 与规范逐条一致（24 条 = 12+9+3+0）。"""

    async def _run() -> None:
        async with sessions() as session:
            tenant_id = await _default_tenant_id(session)

            rows = (
                await session.execute(
                    select(RoleORM.name, RolePermissionORM.permission_id).join(
                        RolePermissionORM,
                        RolePermissionORM.role_id == RoleORM.id,
                    )
                )
            ).all()
            assert len(rows) == EXPECTED_ROLE_PERMISSION_ROWS

            permission_codes = {
                str(permission_id): str(code)
                for permission_id, code in (
                    await session.execute(select(PermissionORM.id, PermissionORM.code))
                ).all()
            }
            from_db: dict[str, set[str]] = {name: set() for name in ROLE_NAMES}
            for role_name, permission_id in rows:
                from_db[str(role_name)].add(permission_codes[str(permission_id)])

            assert from_db == {
                name: set(codes) for name, codes in EXPECTED_ROLE_PERMISSIONS.items()
            }

            # 同一份映射必须能经 RoleService 复现（docs/02 §23 / §30）。
            services = _services(session)
            for name, codes in EXPECTED_ROLE_PERMISSIONS.items():
                assert await services.roles.get_role_permissions([name], tenant_id) == set(codes)

    asyncio.run(_run())


def test_rbac_service_agrees_with_the_role_grants_for_every_role(
    sessions: SessionFactory,
) -> None:
    """门槛 ④：`RBACService.has_permission` 对 4 个角色 × 12 个权限逐格一致。"""

    async def _run() -> None:
        async with sessions() as session:
            tenant_id = await _default_tenant_id(session)
            for role_name in ROLE_NAMES:
                await _add_user(
                    session,
                    tenant_id=tenant_id,
                    username=f"rbac-{role_name}",
                    role_names=[role_name],
                )
            async with UnitOfWork(session):
                pass

        async with sessions() as session:
            services = _services(session)
            for role_name in ROLE_NAMES:
                async with UnitOfWork(session):
                    login = await services.guard.login(f"rbac-{role_name}", TEST_PASSWORD)
                identity = await services.guard.authenticate(login.access_token)
                assert identity.roles == (role_name,)

                granted = set(EXPECTED_ROLE_PERMISSIONS[role_name])
                for code in PermissionCode:
                    expected = code.value in granted
                    actual = await services.rbac.has_permission(identity, code.value)
                    assert actual is expected, f"{role_name} / {code.value}"
                assert await services.permissions.get_permissions(identity) == granted

    asyncio.run(_run())


# ===== ⑤ Effective Permission（`docs/07` §8.2；`docs/02` §24–§31；门槛 ⑤）=====


def test_acl_decision_priority_is_the_frozen_order() -> None:
    """门槛 ⑤：判定优先级 `DENY > ALLOW`（`docs/02` §28：Deny wins）。"""
    assert ACL_DECISION_PRIORITY == (PermissionEffect.DENY, PermissionEffect.ALLOW)


def test_acl_scope_is_the_four_level_vocabulary() -> None:
    """门槛 ⑤：四级作用域（全局 / 租户 / 用户 / 实例，`docs/07` §8.2）。"""
    assert {scope.value for scope in ACLScope} == {"GLOBAL", "TENANT", "USER", "RESOURCE"}
    assert {kind.value for kind in ACLPrincipalType} == {"USER", "ROLE", "TENANT"}


def test_four_scopes_take_the_strictest() -> None:
    """门槛 ⑤：四级取最严格 —— 任一级 `DENY` 即 `DENY`（`docs/02` §28）。"""
    user_id = uuid4()
    tenant_id = uuid4()
    identity = IdentityContext(user_id=user_id, tenant_id=tenant_id, roles=("engineer",))

    allow_only = (
        _entry(
            permission="MODEL_WRITE",
            effect=PermissionEffect.ALLOW,
            scope=ACLScope.GLOBAL,
            principal_type=ACLPrincipalType.TENANT,
            principal_id=str(tenant_id),
        ),
        _entry(
            permission="MODEL_WRITE",
            effect=PermissionEffect.ALLOW,
            scope=ACLScope.TENANT,
            principal_type=ACLPrincipalType.ROLE,
            principal_id="engineer",
        ),
    )
    assert acl_decision_for(allow_only, identity, None, None) == {
        "MODEL_WRITE": PermissionEffect.ALLOW
    }

    for deny_scope, principal in (
        (ACLScope.GLOBAL, (ACLPrincipalType.TENANT, str(tenant_id))),
        (ACLScope.TENANT, (ACLPrincipalType.ROLE, "engineer")),
        (ACLScope.USER, (ACLPrincipalType.USER, str(user_id))),
    ):
        entries = allow_only + (
            _entry(
                permission="MODEL_WRITE",
                effect=PermissionEffect.DENY,
                scope=deny_scope,
                principal_type=principal[0],
                principal_id=principal[1],
            ),
        )
        assert acl_decision_for(entries, identity, None, None) == {
            "MODEL_WRITE": PermissionEffect.DENY
        }, deny_scope

    # 顺序无关：DENY 在前、ALLOW 在后也必须仍是 DENY。
    reversed_entries = tuple(reversed(entries))
    assert acl_decision_for(reversed_entries, identity, None, None) == {
        "MODEL_WRITE": PermissionEffect.DENY
    }


def test_entry_matches_resource_scope_rules() -> None:
    """门槛 ⑤：资源级条目必须 `resource_type` + `resource_id` 同时命中（`docs/02` §24）。"""
    tenant_only = _entry(
        permission="MODEL_READ",
        effect=PermissionEffect.ALLOW,
        scope=ACLScope.TENANT,
        principal_type=ACLPrincipalType.TENANT,
        principal_id="t",
    )
    resource_scoped = _entry(
        permission="MODEL_READ",
        effect=PermissionEffect.DENY,
        scope=ACLScope.RESOURCE,
        principal_type=ACLPrincipalType.USER,
        principal_id="u",
        resource_type="MODEL",
        resource_id="m-1",
    )

    assert entry_matches_resource(tenant_only, None, None) is True
    assert entry_matches_resource(tenant_only, "MODEL", "m-1") is True
    assert entry_matches_resource(resource_scoped, None, None) is False
    assert entry_matches_resource(resource_scoped, "MODEL", "m-1") is True
    assert entry_matches_resource(resource_scoped, "MODEL", "m-2") is False
    assert entry_matches_resource(resource_scoped, "DOCUMENT", "m-1") is False


def test_null_acl_lookup_never_grants_or_denies() -> None:
    """门槛 ⑤：未装配 ACL 来源时按空集处理（`docs/02` §24；不臆造判定）。"""

    async def _run() -> None:
        lookup = NullResourceACLLookup()
        assert await lookup.entries_for(tenant_id="t", resource_type=None, resource_id=None) == ()
        assert await lookup.entries_for(tenant_id="t", resource_type="MODEL", resource_id="m") == ()

    asyncio.run(_run())


def test_resource_acl_never_crosses_tenants() -> None:
    """门槛 ⑤：ACL 来源按租户隔离，跨租户查询返回空集（`docs/02` §48）。"""
    entry = _entry(
        permission="MODEL_WRITE",
        effect=PermissionEffect.DENY,
        scope=ACLScope.TENANT,
        principal_type=ACLPrincipalType.TENANT,
        principal_id="tenant-a",
    )
    lookup = InMemoryResourceACLLookup("tenant-a", (entry,))

    async def _run() -> None:
        assert await lookup.entries_for(
            tenant_id="tenant-a", resource_type=None, resource_id=None
        ) == (entry,)
        assert (
            await lookup.entries_for(tenant_id="tenant-b", resource_type=None, resource_id=None)
            == ()
        )

    asyncio.run(_run())


def test_tenant_access_service_denies_foreign_tenant() -> None:
    """门槛 ⑤：跨租户 → `STRUCTAI-4200`，消息不泄露存在性（`docs/02` §22 / §48）。"""
    service = TenantAccessService()
    identity = IdentityContext(user_id=uuid4(), tenant_id=uuid4())
    service.ensure_access(identity, str(identity.tenant_id))
    service.ensure_resource_access(identity, str(identity.tenant_id))

    for check in (
        lambda: service.ensure_access(identity, str(uuid4())),
        lambda: service.ensure_resource_access(identity, str(uuid4())),
        lambda: service.ensure_resource_access(identity, None),
    ):
        with pytest.raises(TenantAccessDeniedError) as excinfo:
            check()
        assert excinfo.value.code == "STRUCTAI-4200"
        assert excinfo.value.message == TENANT_ACCESS_DENIED_MESSAGE


def test_project_membership_adds_permissions_on_top_of_user_roles(
    sessions: SessionFactory,
) -> None:
    """门槛 ⑤：有效权限 = 用户角色权限 ∪ 项目成员权限（`docs/02` §30 第 4 步）。"""

    async def _run() -> None:
        async with sessions() as session:
            tenant_id = await _default_tenant_id(session)
            user_id = await _add_user(
                session,
                tenant_id=tenant_id,
                username="project-viewer",
                role_names=[RoleName.VIEWER.value],
            )
            project = ProjectORM(tenant_id=tenant_id, name="project-b")
            session.add(project)
            await session.flush()
            session.add(
                ProjectMemberORM(
                    project_id=project.id,
                    user_id=user_id,
                    role=RoleName.ENGINEER.value,
                )
            )
            await session.flush()
            project_id = str(project.id)
            async with UnitOfWork(session):
                pass

        async with sessions() as session:
            services = _services(session)
            async with UnitOfWork(session):
                login = await services.guard.login("project-viewer", TEST_PASSWORD)
            identity = await services.guard.authenticate(login.access_token)

            baseline = await services.permissions.get_permissions(identity)
            assert baseline == set(EXPECTED_ROLE_PERMISSIONS[RoleName.VIEWER.value])

            with_project = await services.permissions.get_permissions(
                identity, project_id=project_id
            )
            assert with_project == set(EXPECTED_ROLE_PERMISSIONS[RoleName.VIEWER.value]) | set(
                EXPECTED_ROLE_PERMISSIONS[RoleName.ENGINEER.value]
            )
            assert PermissionCode.MODEL_WRITE.value in with_project

    asyncio.run(_run())


def test_cross_tenant_project_access_is_denied_with_structai_4200(
    sessions: SessionFactory,
) -> None:
    """门槛 ⑤：跨租户项目 → `STRUCTAI-4200`（`docs/07` §14.3 的唯一拦截点）。"""

    async def _run() -> None:
        async with sessions() as session:
            _, foreign_project_id = await _add_tenant_with_project(
                session,
                tenant_name="tenant-b",
                project_name="project-b",
            )
            async with UnitOfWork(session):
                pass

        async with sessions() as session:
            services = _services(session)
            async with UnitOfWork(session):
                login = await services.guard.login("admin", TEST_PASSWORD)
            identity = await services.guard.authenticate(login.access_token)

            with pytest.raises(TenantAccessDeniedError) as excinfo:
                await services.permissions.get_permissions(identity, project_id=foreign_project_id)
            assert excinfo.value.code == "STRUCTAI-4200"
            assert excinfo.value.message == TENANT_ACCESS_DENIED_MESSAGE

    asyncio.run(_run())


def test_missing_and_foreign_projects_are_indistinguishable(sessions: SessionFactory) -> None:
    """门槛 ⑤：「项目不存在」与「项目属于别的租户」返回同一个错误（`docs/02` §48）。"""

    async def _run() -> None:
        async with sessions() as session:
            _, foreign_project_id = await _add_tenant_with_project(
                session,
                tenant_name="tenant-b",
                project_name="project-b",
            )
            async with UnitOfWork(session):
                pass

        async with sessions() as session:
            services = _services(session)
            async with UnitOfWork(session):
                login = await services.guard.login("admin", TEST_PASSWORD)
            identity = await services.guard.authenticate(login.access_token)

            shapes = []
            for project_id in (foreign_project_id, str(uuid4())):
                with pytest.raises(TenantAccessDeniedError) as excinfo:
                    await services.project_access.ensure_access(identity, project_id)
                shapes.append((excinfo.value.code, excinfo.value.message, excinfo.value.details))
            assert shapes[0] == shapes[1]
            assert shapes[0][0] == "STRUCTAI-4200"

    asyncio.run(_run())


def test_explicit_deny_removes_an_otherwise_granted_permission(
    sessions: SessionFactory,
) -> None:
    """门槛 ⑤：显式拒绝优先 —— 角色已授予的权限被 ACL DENY 移除（`docs/02` §50）。"""

    async def _run() -> None:
        async with sessions() as session:
            tenant_id = await _default_tenant_id(session)
            user_id = await _add_user(
                session,
                tenant_id=tenant_id,
                username="denied-engineer",
                role_names=[RoleName.ENGINEER.value],
            )
            async with UnitOfWork(session):
                pass

        async with sessions() as session:
            services = _services(session)
            async with UnitOfWork(session):
                login = await services.guard.login("denied-engineer", TEST_PASSWORD)
            identity = await services.guard.authenticate(login.access_token)
            assert await services.rbac.has_permission(identity, PermissionCode.MODEL_WRITE.value)

            deny = _entry(
                permission=PermissionCode.MODEL_WRITE.value,
                effect=PermissionEffect.DENY,
                scope=ACLScope.USER,
                principal_type=ACLPrincipalType.USER,
                principal_id=user_id,
            )
            denied_services = _services(
                session,
                resource_acl=InMemoryResourceACLLookup(str(identity.tenant_id), (deny,)),
            )

            permissions = await denied_services.permissions.get_permissions(identity)
            assert permissions == set(EXPECTED_ROLE_PERMISSIONS[RoleName.ENGINEER.value]) - {
                PermissionCode.MODEL_WRITE.value
            }
            with pytest.raises(PermissionDeniedError) as excinfo:
                await denied_services.permissions.require(
                    identity, PermissionCode.MODEL_WRITE.value
                )
            assert excinfo.value.code == "STRUCTAI-4000"
            assert excinfo.value.message == "Permission denied: MODEL_WRITE"

    asyncio.run(_run())


def test_resource_scoped_deny_only_applies_to_that_resource(sessions: SessionFactory) -> None:
    """门槛 ⑤：实例级 DENY 只影响该资源（`docs/02` §24 的资源粒度）。"""

    async def _run() -> None:
        async with sessions() as session:
            tenant_id = await _default_tenant_id(session)
            user_id = await _add_user(
                session,
                tenant_id=tenant_id,
                username="resource-deny",
                role_names=[RoleName.ENGINEER.value],
            )
            async with UnitOfWork(session):
                pass

        async with sessions() as session:
            services = _services(session)
            async with UnitOfWork(session):
                login = await services.guard.login("resource-deny", TEST_PASSWORD)
            identity = await services.guard.authenticate(login.access_token)

            deny = _entry(
                permission=PermissionCode.MODEL_WRITE.value,
                effect=PermissionEffect.DENY,
                scope=ACLScope.RESOURCE,
                principal_type=ACLPrincipalType.USER,
                principal_id=user_id,
                resource_type="MODEL",
                resource_id="model-1",
            )
            denied_services = _services(
                session,
                resource_acl=InMemoryResourceACLLookup(str(identity.tenant_id), (deny,)),
            )

            on_resource = await denied_services.permissions.get_permissions(
                identity, "MODEL", "model-1"
            )
            assert PermissionCode.MODEL_WRITE.value not in on_resource
            other_resource = await denied_services.permissions.get_permissions(
                identity, "MODEL", "model-2"
            )
            assert PermissionCode.MODEL_WRITE.value in other_resource
            no_resource = await denied_services.permissions.get_permissions(identity)
            assert PermissionCode.MODEL_WRITE.value in no_resource

    asyncio.run(_run())


# ===== ⑥ AI Agent 不得提权（`docs/07` §5.7 / §14.3；`docs/02` §32 / §33）=====


def test_agent_intersection_only_reduces_permissions() -> None:
    """门槛 ⑥：`Effective User Permission ∩ Agent Permission`（`docs/02` §33）。"""

    async def _run() -> None:
        service = AgentPermissionService()
        user = {"MODEL_READ", "MODEL_WRITE", "ANALYSIS_EXECUTE", "DESIGN_EXECUTE", "SYSTEM_ADMIN"}
        agent = {"MODEL_READ", "MODEL_WRITE", "ANALYSIS_EXECUTE"}

        assert await service.intersect(user, agent) == agent
        assert await service.intersect(user, set()) == set()
        assert await service.intersect(set(), agent) == set()
        # Agent 不能增加权限（docs/02 §33）。
        assert await service.intersect(agent, user) == agent

    asyncio.run(_run())


def test_ai_agent_identity_cannot_escalate(sessions: SessionFactory) -> None:
    """门槛 ⑥：`ai_agent` 有效权限 = 用户有效权限 ∩ Agent 权限，不得提权（`docs/02` §51）。"""
    agent_scope = {"MODEL_READ", "MODEL_WRITE", "ANALYSIS_EXECUTE"}

    async def _run() -> None:
        async with sessions() as session:
            tenant_id = await _default_tenant_id(session)
            await _add_user(
                session,
                tenant_id=tenant_id,
                username="agent-user",
                role_names=[RoleName.SYSTEM_ADMIN.value, RoleName.AI_AGENT.value],
            )
            async with UnitOfWork(session):
                pass

        async with sessions() as session:
            services = _services(session)
            async with UnitOfWork(session):
                login = await services.guard.login("agent-user", TEST_PASSWORD)
            identity = await services.guard.authenticate(login.access_token)
            assert set(identity.roles) == {"ai_agent", "system_admin"}

            # 用户侧确实是 12 条全量（证明「交集」不是「本来就没有」）。
            assert await services.roles.get_user_permissions(str(identity.user_id)) == set(
                EXPECTED_ROLE_PERMISSIONS[RoleName.SYSTEM_ADMIN.value]
            )

            scoped = await services.permissions.get_permissions(
                identity, agent_permissions=agent_scope
            )
            assert scoped == agent_scope
            assert PermissionCode.SYSTEM_ADMIN.value not in scoped
            assert PermissionCode.DESIGN_EXECUTE.value not in scoped

            # 即使 Agent 自己请求 SYSTEM_ADMIN，也必须拒绝（docs/02 §32）。
            with pytest.raises(PermissionDeniedError):
                await services.permissions.require(
                    identity,
                    PermissionCode.SYSTEM_ADMIN.value,
                    agent_permissions=agent_scope,
                )

            # 构造期默认的 Agent 权限同样生效（等价于按次传入）。
            defaulted = _services(session, agent_permissions=agent_scope)
            assert await defaulted.permissions.get_permissions(identity) == agent_scope

    asyncio.run(_run())


def test_ai_agent_without_scope_gets_no_permissions(sessions: SessionFactory) -> None:
    """门槛 ⑥：Agent 身份未提供 Agent 权限时按**空集**处理（绝不退化为用户权限）。"""

    async def _run() -> None:
        async with sessions() as session:
            tenant_id = await _default_tenant_id(session)
            await _add_user(
                session,
                tenant_id=tenant_id,
                username="agent-without-scope",
                role_names=[RoleName.SYSTEM_ADMIN.value, RoleName.AI_AGENT.value],
            )
            async with UnitOfWork(session):
                pass

        async with sessions() as session:
            services = _services(session)
            async with UnitOfWork(session):
                login = await services.guard.login("agent-without-scope", TEST_PASSWORD)
            identity = await services.guard.authenticate(login.access_token)

            assert await services.permissions.get_permissions(identity) == set()
            with pytest.raises(PermissionDeniedError):
                await services.permissions.require(identity, PermissionCode.MODEL_READ.value)

    asyncio.run(_run())


# ===== ⑦ 回归（`python -m app.main` / P04 / P02）=====


def test_batch_id_is_a_batch_marker() -> None:
    """同步改动：`BATCH_ID` 始终形如 `P<两位数字>`（`docs/08` §3 的批次口径）。

    ⚠️ P14 收尾时把本断言从「等于 P10」改为与具体批次无关（与 P08 / P09 收尾时的做法一致），
    否则每批都要改上一批的测试文件。
    """
    assert re.fullmatch(r"P\d{2}", BATCH_ID)


def test_main_exits_zero_with_empty_stdout_on_an_unprovisioned_database(
    tmp_path: Path,
) -> None:
    """门槛 ⑦：未配备库 → 退出码 0、**stdout 0 字节**、Registry 留空但进程正常结束。"""
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p10_empty.db').as_posix()}"
    completed = _run_main(database_url)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert f"batch={BATCH_ID}" in completed.stderr
    assert "operation registry is not assembled" in completed.stderr


def test_main_exits_zero_with_empty_stdout_on_a_provisioned_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ⑦：已配备库（建表 + Seed）→ 退出码 0、**stdout 0 字节**、Registry 就绪。"""
    database_url = asyncio.run(_provision(tmp_path, monkeypatch, "p10_main_cli.db"))
    completed = _run_main(database_url)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert f"batch={BATCH_ID}" in completed.stderr
    assert "registry ready" in completed.stderr


def test_p04_tables_and_select_one_are_not_regressed(seeded_engine: AsyncEngine) -> None:
    """门槛 ⑦（P04）：建表 **24** 张（与 24 个 ORM Model 一一对应）+ `SELECT 1` → 1。"""

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
    """门槛 ⑦（P02）：环境变量覆盖默认值（`docs/07` §12 P02）。"""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./data/p10_gate.db")
    monkeypatch.setenv("SESSION_EXPIRE_SECONDS", "120")

    overridden = Settings()

    assert overridden.log_level == "DEBUG"
    assert overridden.database_url == "sqlite+aiosqlite:///./data/p10_gate.db"
    assert overridden.session_expire_seconds == 120


# ===== ⑧ 质量与结构（`docs/07` §3.1 / §3.3 / §14）=====


def test_technology_stack_is_frozen() -> None:
    """门槛 ⑧：依赖清单未扩（`docs/07` §3.1 / §3.2：不得引入新依赖）。"""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = {
        re.split(r"[<>=!\[;]", dependency.strip())[0].strip().lower()
        for dependency in pyproject["project"]["dependencies"]
    }
    assert declared == set(FROZEN_DEPENDENCIES)


def test_container_shape_stays_frozen() -> None:
    """门槛 ⑧：容器字段仍为 `docs/02` §33 的冻结形状（P10 **不**加安全字段）。"""
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
    assert [name for name in names if "security" in name or "auth" in name] == []


def test_application_security_does_not_depend_on_infrastructure() -> None:
    """门槛 ⑧：Application 安全层不依赖 `app.infrastructure`（`docs/07` §14.1 / §2.2）。"""
    offenders: list[str] = []
    for relative in INFRASTRUCTURE_FREE_MODULES:
        for module in _imported_modules(_relative_path(relative)):
            if module.startswith("app.infrastructure") or module.startswith("app.interfaces"):
                offenders.append(f"{relative} → {module}")
            if module.split(".")[0] in {"sqlalchemy", "fastapi", "mcp", "httpx"}:
                offenders.append(f"{relative} → {module}")
    assert offenders == []


def test_security_modules_never_commit() -> None:
    """门槛 ⑧：安全模块不得 `commit` / `rollback`（边界归 `UnitOfWork`，`docs/07` §14.4）。"""
    for relative in INFRASTRUCTURE_FREE_MODULES:
        assert _commit_or_rollback_calls(_relative_path(relative)) == [], relative
    assert (
        _commit_or_rollback_calls(
            _relative_path("app/infrastructure/database/repositories/security.py")
        )
        == []
    )


def test_security_services_share_one_session(sessions: SessionFactory) -> None:
    """门槛 ⑧：会话级装配把全部安全服务绑到**同一个**会话（`docs/02` §33 / §123）。"""

    async def _run() -> None:
        async with sessions() as session:
            stores = build_security_stores(session)
            assert stores.users is not None
            services = _services(session)
            assert isinstance(services, SecurityServices)
            assert isinstance(services.guard, SecurityGuard)
            assert isinstance(services.authentication, AuthenticationService)
            assert isinstance(services.sessions, SessionService)
            assert isinstance(services.roles, RoleService)
            assert isinstance(services.rbac, RBACService)
            assert isinstance(services.permissions, EffectivePermissionService)
            assert isinstance(services.tenant_access, TenantAccessService)
            assert isinstance(services.project_access, ProjectAccessService)
            assert isinstance(services.agents, AgentPermissionService)
            assert services.guard.chain_order == SECURITY_CHAIN_ORDER

    asyncio.run(_run())


def test_twenty_code_contract_is_not_extended() -> None:
    """门槛 ⑨：20 码契约不扩（认证 / 会话失败复用既有 `STRUCTAI-4000`）。"""
    from app.domain import errors as errors_module

    assert len(TWENTY_CODE_CONTRACT) == 20
    assert errors_module.PermissionDeniedError.code == "STRUCTAI-4000"
    assert errors_module.PermissionDeniedError.error_type == "PERMISSION_DENIED"
    assert errors_module.TenantAccessDeniedError.code == "STRUCTAI-4200"

    derived = [
        name
        for name, value in vars(errors_module).items()
        if isinstance(value, type)
        and issubclass(value, StructAIError)
        and value is not StructAIError
    ]
    assert len(derived) == 20


def test_no_new_structai_error_code_anywhere_in_app() -> None:
    """门槛 ⑨：`app/` 内出现的 `STRUCTAI-xxxx` 字面量只能是那 20 个码。"""
    declared: set[str] = set()
    for path in sorted(APP_DIR.rglob("*.py")):
        declared.update(re.findall(r"STRUCTAI-\d{4}", path.read_text(encoding="utf-8")))
    assert declared == set(TWENTY_CODE_CONTRACT)


def test_red_lines_vendor_names_and_domain_purity() -> None:
    """门槛 ⑨：`app/` 内厂商名 0 处；`app/domain/` 内无 SQLAlchemy。"""
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


def test_settings_fields_are_registered_in_env_example() -> None:
    """门槛 ⑨：每个 Settings 字段都在 `.env.example` 登记（本批未新增字段）。"""
    registered = set(
        re.findall(
            r"^([A-Z0-9_]+)=",
            (REPO_ROOT / ".env.example").read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
    )
    declared = {name.upper() for name in Settings.model_fields}

    assert declared <= registered


def test_security_modules_exist_and_are_exported() -> None:
    """门槛 ⑧：`docs/07` §3.3 冻结结构中的 6 个安全模块 + `password.py` 全部存在。"""
    present = {path.name for path in SECURITY_DIR.glob("*.py")}
    assert set(SECURITY_MODULES) <= present
    assert "password.py" in present
    for relative in INFRASTRUCTURE_FREE_MODULES:
        assert _relative_path(relative).is_file(), relative


def _relative_path(relative: str) -> Path:
    """仓库内相对路径 → 绝对路径。"""
    return REPO_ROOT / relative
