"""P07 验收测试：幂等 Seed（`docs/07` §12 P07；`docs/02` §43–§46 / §69–§72 / §100–§101）。

验收点（与续接提示词的 ①–⑤ / ⑧ 一一对应）：

① 幂等（`docs/02` §45）：同一库连跑 3 次，第 2 / 第 3 次**不新增任何行**，
   且各表的自然键（natural key）无重复；
② 顺序（`docs/02` §46）：以 SQL 级录制断言实际 `INSERT` 顺序 =
   `SEED_ORDER`（前 8 张即规范强制顺序，不得反过来）；
③ 内容（`docs/02` §43 / §69–§72 / §100–§101；`docs/07` §5.6 / §5.7）：1 Tenant ·
   1 System Admin（`username=admin`）· Role 4 · Permission 12 · RolePermission ·
   UserRole · Capability · Operation 69 · Mock Software / Product / Version / Instance；
④ 安全（`docs/02` §44 / §8）：口令只经环境变量注入（缺失即 `RuntimeError`）；
   库中只写 `password_hash`（Argon2id），全库任何文本列都不含明文口令；
⑤ 事务（`docs/07` §14.4）：`seed.py` 内**不得**出现裸 `commit` / `rollback`
   （AST 级检查，忽略文档字符串），且必须经 `UnitOfWork` 提交；
⑧ 红线（`docs/07` §14.2）：落库的 Capability / Operation 取值不含任何厂商名。

全部测试使用临时 SQLite 文件库（`tests/conftest.py`），且一律通过被测代码自身的
`seed()` 入口驱动。
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.security.password import PasswordService
from app.config.settings import Settings
from app.domain.enums import Capability, PermissionCode, SoftwareConnectionState, SoftwareStatus
from app.infrastructure.database import Base, seed_database
from app.infrastructure.database import seed as seed_module
from app.infrastructure.database.models import (
    CapabilityORM,
    OperationORM,
    PermissionORM,
    ProjectMemberORM,
    ProjectORM,
    RoleORM,
    RolePermissionORM,
    SoftwareInstanceORM,
    SoftwareORM,
    SoftwareProductORM,
    SoftwareVersionORM,
    TenantORM,
    UserORM,
    UserRoleORM,
)
from app.infrastructure.database.seed import (
    ADMIN_PASSWORD_ENV,
    ADMIN_USERNAME,
    DEFAULT_PROJECT_NAME,
    DEFAULT_TENANT_NAME,
    MOCK_INSTANCE_NAME,
    MOCK_PRODUCT,
    MOCK_VENDOR,
    MOCK_VERSION,
    OPERATIONS,
    ROLE_NAMES,
    ROLE_PERMISSIONS,
    SEED_ORDER,
    seed,
)

SessionFactory = async_sessionmaker[AsyncSession]
"""会话工厂类型别名（`docs/02` §15）。"""

TEST_PASSWORD = "P07-Seed-验收-口令-9f3a1c"
"""测试用口令（非真实 secret，仅存在于测试进程内）。"""

VENDOR_NAMES = ("MIDAS", "CSI", "ANSYS")
"""`docs/07` §14.2：Capability 中禁止出现的厂商名。"""

# 自然键（与 `seed.py` 的幂等口径一一对应；`docs/02` §45）
NATURAL_KEYS: tuple[tuple[type[Any], tuple[str, ...]], ...] = (
    (TenantORM, ("name",)),
    (PermissionORM, ("code",)),
    (RoleORM, ("tenant_id", "name")),
    (RolePermissionORM, ("role_id", "permission_id")),
    (UserORM, ("username",)),
    (UserRoleORM, ("user_id", "role_id")),
    (ProjectORM, ("tenant_id", "name")),
    (ProjectMemberORM, ("project_id", "user_id")),
    (CapabilityORM, ("code",)),
    (OperationORM, ("name",)),
    (SoftwareORM, ("vendor", "name")),
    (SoftwareProductORM, ("software_id", "product")),
    (SoftwareVersionORM, ("product_id", "version")),
    (SoftwareInstanceORM, ("version_id", "name")),
)

INSERT_PATTERN = re.compile(r"^INSERT INTO\s+(\w+)", re.IGNORECASE)


# ===== 规范原文的独立副本（`docs/02` §69–§72；`docs/07` §5.6 / §5.7）=====
# ⚠️ 这些字面量**故意**不从 `app.infrastructure.database.seed` 取：若断言只与 seed.py 的
#    常量比较，则「常量被改错」与「写库被改错」会一起通过（同源循环）。此处逐字抄写规范，
#    任何一侧漂移都会让测试失败。

DOC_PERMISSION_CODES: tuple[str, ...] = (
    "MODEL_READ",
    "MODEL_WRITE",
    "MODEL_DELETE",
    "ANALYSIS_EXECUTE",
    "DESIGN_EXECUTE",
    "DESIGN_MODIFY",
    "RESULT_READ",
    "DOCUMENT_READ",
    "DOCUMENT_WRITE",
    "SYSTEM_ADMIN",
    "TOOL_TEST",
    "API_TEST",
)
"""`docs/02` §71 / `docs/07` §5.7：Permission 12 条。"""

DOC_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "system_admin": DOC_PERMISSION_CODES,
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
    ),
    "viewer": ("MODEL_READ", "RESULT_READ", "DOCUMENT_READ"),
    "ai_agent": (),
}
"""`docs/02` §72 / `docs/07` §5.7：Role 4 条及其权限（`system_admin` = ALL；`ai_agent` 动态）。"""

DOC_CAPABILITIES: tuple[str, ...] = (
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
    "MODEL.GROUP.READ",
    "MODEL.READ",
    "DOCUMENT.NEW",
    "DOCUMENT.OPEN",
    "DOCUMENT.SAVE",
    "DOCUMENT.SAVE_AS",
    "DOCUMENT.CLOSE",
    "DOCUMENT.INFO",
    "ANALYSIS.STATIC",
    "ANALYSIS.MODAL",
    "ANALYSIS.SEISMIC",
    "ANALYSIS.SPECTRUM",
    "ANALYSIS.BUCKLING",
    "ANALYSIS.TIME_HISTORY",
    "ANALYSIS.NONLINEAR",
    "RESULT.DISPLACEMENT",
    "RESULT.REACTION",
    "RESULT.ELEMENT_FORCE",
    "RESULT.STRESS",
    "RESULT.MODE_SHAPE",
    "DESIGN.STEEL",
    "DESIGN.CONCRETE",
    "DESIGN.SRC",
    "DESIGN.FOUNDATION",
    "DESIGN.OPTIMIZATION",
    "DESIGN.CODE_CHECK",
)
"""`docs/02` §70 ＋ `docs/07` §5.6：Capability 全量 41 条（`VIEW.*` 是通配写法，非能力码）。"""


DOC_OPERATIONS: dict[str, tuple[str, ...]] = {
    "engineering_doc": ("NEW", "OPEN", "SAVE", "SAVE_AS", "CLOSE", "INFO"),
    "engineering_model_query": (
        "MODEL.QUERY",
        "MODEL.NODE.QUERY",
        "MODEL.ELEMENT.QUERY",
        "MODEL.MATERIAL.QUERY",
        "MODEL.SECTION.QUERY",
        "MODEL.BOUNDARY.QUERY",
        "MODEL.LOAD.QUERY",
        "MODEL.GROUP.QUERY",
    ),
    "engineering_model_assign": (
        "MODEL.NODE.CREATE",
        "MODEL.NODE.UPDATE",
        "MODEL.ELEMENT.CREATE",
        "MODEL.ELEMENT.UPDATE",
        "MODEL.MATERIAL.ASSIGN",
        "MODEL.SECTION.ASSIGN",
        "MODEL.BOUNDARY.ASSIGN",
        "MODEL.LOAD.ASSIGN",
    ),
    "engineering_model_delete": (
        "MODEL.NODE.DELETE",
        "MODEL.ELEMENT.DELETE",
        "MODEL.LOAD.DELETE",
        "MODEL.BOUNDARY.DELETE",
        "MODEL.GROUP.DELETE",
        "MODEL.MATERIAL.DELETE",
        "MODEL.SECTION.DELETE",
    ),
    "engineering_model_build": (
        "BUILD.NODE_GRID",
        "BUILD.BEAM",
        "BUILD.COLUMN",
        "BUILD.FRAME",
        "BUILD.TRUSS",
        "BUILD.SLAB",
        "BUILD.WALL",
        "BUILD.FOUNDATION",
        "BUILD.STEEL_FRAME",
        "MODEL.COPY",
        "MODEL.MOVE",
        "MODEL.MIRROR",
        "MODEL.PATTERN",
        "MODEL.GENERATE_GRID",
    ),
    "engineering_view": (
        "VIEW.MODEL",
        "VIEW.DEFORMED_MODEL",
        "VIEW.REACTION",
        "VIEW.DISPLACEMENT",
        "VIEW.STRESS",
        "VIEW.FORCE",
        "VIEW.MODE_SHAPE",
    ),
    "engineering_result": (
        "RESULT.NODE.DISPLACEMENT",
        "RESULT.NODE.REACTION",
        "RESULT.ELEMENT.FORCE",
        "RESULT.ELEMENT.STRESS",
        "RESULT.MODE.SHAPE",
        "RESULT.ANALYSIS.SUMMARY",
    ),
    "engineering_design": (
        "DESIGN.STEEL",
        "DESIGN.CONCRETE",
        "DESIGN.SRC",
        "DESIGN.FOUNDATION",
        "DESIGN.CODE_CHECK",
        "DESIGN.OPTIMIZE",
    ),
    "engineering_analysis": (
        "ANALYSIS.STATIC",
        "ANALYSIS.MODAL",
        "ANALYSIS.SEISMIC",
        "ANALYSIS.SPECTRUM",
        "ANALYSIS.BUCKLING",
        "ANALYSIS.TIME_HISTORY",
        "ANALYSIS.NONLINEAR",
    ),
}
"""`docs/02` §69 / `docs/07` §5.1：Operation 全量 69 条（含 2026-10-05 新增 `DESIGN.SRC`）。"""

DOC_OPERATION_COUNT: int = 69
DOC_CAPABILITY_COUNT: int = 41


async def _count(session_factory: SessionFactory, model: type[Any]) -> int:
    """统计某表的行数。"""
    async with session_factory() as session:
        result = await session.execute(select(func.count()).select_from(model))
        return int(result.scalar_one())


async def _duplicate_natural_keys(session_factory: SessionFactory) -> list[str]:
    """返回存在重复自然键的表名（空列表 = 无重复，`docs/02` §45）。"""
    duplicates: list[str] = []
    async with session_factory() as session:
        for model, columns in NATURAL_KEYS:
            attributes = [getattr(model, column) for column in columns]
            statement = select(*attributes).group_by(*attributes).having(func.count() > 1)
            if (await session.execute(statement)).first() is not None:
                duplicates.append(model.__tablename__)
    return duplicates


async def _seeded_strings(engine: AsyncEngine) -> list[str]:
    """全库所有文本列的取值（用于「明文口令不得落库」检查）。"""
    values: list[str] = []
    async with engine.connect() as connection:
        for table in Base.metadata.sorted_tables:
            result = await connection.execute(select(table))
            for row in result.mappings():
                values.extend(value for value in row.values() if isinstance(value, str))
    return values


# ===== ① 幂等（`docs/02` §45）=====


async def test_seed_is_idempotent_over_three_runs(
    session_factory: SessionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """连跑 3 次：第 2 / 第 3 次**零新增**，且各表自然键无重复（`docs/02` §45）。"""
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)

    first = await seed(session_factory)
    assert first.total_created > 0
    assert first.created["tenants"] == 1
    assert first.created["users"] == 1
    assert first.created["user_roles"] == 1

    second = await seed(session_factory)
    third = await seed(session_factory)

    # 第 2 / 第 3 次不新增任何行（口令未变 → 也没有原地更新）
    assert second.created == {}
    assert third.created == {}
    assert second.is_noop is True
    assert third.is_noop is True
    assert second.summary().startswith("created 0 row(s)")
    assert third.summary().startswith("created 0 row(s)")

    # 自然键无重复：Tenant / Role / Permission / User / UserRole 等 14 张表
    assert await _duplicate_natural_keys(session_factory) == []

    # 行数在三次运行之间完全一致：第 3 次之后的行数 = 首次运行的新增数（都 > 0）
    for model, _columns in NATURAL_KEYS:
        assert await _count(session_factory, model) == first.created[model.__tablename__] > 0


async def test_seed_report_counts_match_seeded_rows(
    session_factory: SessionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """首次运行的新增计数 = 落库行数（报告不是装饰品）。"""
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)

    report = await seed(session_factory)

    for model, _columns in NATURAL_KEYS:
        table = model.__tablename__
        assert report.created[table] == await _count(session_factory, model)


async def test_seed_converges_admin_password_without_new_rows(
    session_factory: SessionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """环境变量口令变更 → 原地更新 `password_hash`，**不新增行**（`docs/02` §45 upsert）。"""
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    await seed(session_factory)

    rotated = f"{TEST_PASSWORD}-rotated"
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, rotated)
    report = await seed(session_factory)

    assert report.total_created == 0
    assert report.updated == {"users": 1}
    assert await _count(session_factory, UserORM) == 1

    async with session_factory() as session:
        user = (await session.execute(select(UserORM))).scalar_one()

    service = PasswordService()
    assert service.verify(user.password_hash, rotated) is True
    assert service.verify(user.password_hash, TEST_PASSWORD) is False


# ===== ② 顺序（`docs/02` §46）=====


async def test_seed_follows_documented_order(
    engine: AsyncEngine,
    session_factory: SessionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """实际 `INSERT` 顺序 = `SEED_ORDER`；前 8 张即 `docs/02` §46 的强制顺序。"""
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    statements: list[str] = []

    def _record(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "after_cursor_execute", _record)
    try:
        await seed(session_factory)
    finally:
        event.remove(engine.sync_engine, "after_cursor_execute", _record)

    inserted: list[str] = []
    for statement in statements:
        match = INSERT_PATTERN.match(statement.strip())
        if match is not None and match.group(1) not in inserted:
            inserted.append(match.group(1))

    assert inserted == list(SEED_ORDER)

    required = [
        "tenants",
        "permissions",
        "roles",
        "role_permissions",
        "users",
        "user_roles",
        "projects",
        "project_members",
    ]
    positions = [inserted.index(table) for table in required]
    assert positions == sorted(positions), "docs/02 §46 的顺序不得反过来"


# ===== ③ 内容（`docs/02` §43 / §69–§72 / §100–§101）=====


async def test_seed_creates_tenant_admin_roles_and_permissions(
    session_factory: SessionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1 Tenant · 1 System Admin · Role 4 · Permission 12 · RolePermission · UserRole。"""
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    await seed(session_factory)

    async with session_factory() as session:
        tenant = (await session.execute(select(TenantORM))).scalar_one()
        admin = (await session.execute(select(UserORM))).scalar_one()
        roles = list((await session.execute(select(RoleORM))).scalars().all())
        permissions = list((await session.execute(select(PermissionORM))).scalars().all())
        role_permissions = list((await session.execute(select(RolePermissionORM))).scalars().all())
        user_roles = list((await session.execute(select(UserRoleORM))).scalars().all())
        project = (await session.execute(select(ProjectORM))).scalar_one()
        members = list((await session.execute(select(ProjectMemberORM))).scalars().all())

    assert tenant.name == DEFAULT_TENANT_NAME
    assert await _count(session_factory, TenantORM) == 1

    # 1 System Admin（`docs/02` §43）
    assert admin.username == ADMIN_USERNAME
    assert admin.tenant_id == tenant.id
    assert admin.is_active is True
    assert admin.locked is False
    assert admin.failed_login_count == 0
    assert await _count(session_factory, UserORM) == 1

    # Role 4（`docs/02` §72 的规范原文副本）
    assert [role.name for role in roles] == list(DOC_ROLE_PERMISSIONS)
    assert {role.tenant_id for role in roles} == {tenant.id}
    assert set(ROLE_NAMES) == set(DOC_ROLE_PERMISSIONS)

    # Permission 12（`docs/02` §71 的规范原文副本）
    assert {permission.code for permission in permissions} == set(DOC_PERMISSION_CODES)
    assert len(permissions) == len(DOC_PERMISSION_CODES) == 12
    assert {code.value for code in PermissionCode} == set(DOC_PERMISSION_CODES)

    # RolePermission（`docs/02` §72：ALL + 9 + 3 + 0 = 24）
    expected_links = sum(len(codes) for codes in DOC_ROLE_PERMISSIONS.values())
    assert len(role_permissions) == expected_links == 24

    roles_by_name = {role.name: role.id for role in roles}
    permissions_by_code = {permission.code: permission.id for permission in permissions}
    for role_name, codes in DOC_ROLE_PERMISSIONS.items():
        actual = {
            link.permission_id
            for link in role_permissions
            if link.role_id == roles_by_name[role_name]
        }
        assert actual == {permissions_by_code[code] for code in codes}
    assert DOC_ROLE_PERMISSIONS["ai_agent"] == ()
    # seed.py 的角色→权限常量也必须与规范副本一致
    assert {
        role_name: tuple(code.value for code in codes)
        for role_name, codes in ROLE_PERMISSIONS.items()
    } == DOC_ROLE_PERMISSIONS

    # UserRole（`docs/02` §46）
    assert len(user_roles) == 1
    assert user_roles[0].user_id == admin.id
    assert user_roles[0].role_id == roles_by_name["system_admin"]

    # Project / ProjectMember（`docs/02` §46）
    assert project.name == DEFAULT_PROJECT_NAME
    assert project.tenant_id == tenant.id
    assert len(members) == 1
    assert members[0].project_id == project.id
    assert members[0].user_id == admin.id
    assert members[0].role == "system_admin"


async def test_seed_creates_capabilities_and_operations(
    session_factory: SessionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Capability 全量（`docs/07` §5.6）· Operation 69（`docs/02` §69）· 厂商名 0 处。"""
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    await seed(session_factory)

    async with session_factory() as session:
        capabilities = list((await session.execute(select(CapabilityORM))).scalars().all())
        operations = list((await session.execute(select(OperationORM))).scalars().all())

    # Capability：与 docs/02 §70 ＋ docs/07 §5.6 的**规范原文副本**逐条一致（41 条）
    assert {capability.code for capability in capabilities} == set(DOC_CAPABILITIES)
    assert len(capabilities) == DOC_CAPABILITY_COUNT == 41
    assert await _count(session_factory, CapabilityORM) == DOC_CAPABILITY_COUNT
    # P03 的类型化视图（app.domain.enums.Capability）也必须与规范副本一致
    assert {capability.value for capability in Capability} == set(DOC_CAPABILITIES)

    # Operation：69 条，与 docs/02 §69 的**规范原文副本**逐条一致（名称 + Tool）
    expected_operations = {(tool, name) for tool, names in DOC_OPERATIONS.items() for name in names}
    assert len(expected_operations) == DOC_OPERATION_COUNT == 69
    assert {(operation.tool, operation.name) for operation in operations} == expected_operations
    assert await _count(session_factory, OperationORM) == DOC_OPERATION_COUNT
    # seed.py 的常量也必须与规范副本一致（否则「常量改错」会静默通过）
    assert set(OPERATIONS) == expected_operations

    # Tool 分布 = docs/07 §5.1 的 Op 数（6/8/8/7/14/7/6/6/7）
    distribution = Counter(tool for tool, _name in OPERATIONS)
    assert distribution == {tool: len(names) for tool, names in DOC_OPERATIONS.items()}
    assert sum(distribution.values()) == DOC_OPERATION_COUNT

    # Schema URI（docs/02 §14 / §86）：BUILD.COLUMN 与规范示例逐字一致
    by_name = {operation.name: operation for operation in operations}
    assert by_name["BUILD.COLUMN"].input_schema == "structai://schema/build/column/v1"
    assert by_name["BUILD.COLUMN"].output_schema == "structai://schema/build/column/result/v1"
    assert by_name["MODEL.NODE.QUERY"].input_schema == "structai://schema/model/node/query/v1"
    assert by_name["MODEL.NODE.QUERY"].tool == "engineering_model_query"
    assert by_name["DESIGN.SRC"].tool == "engineering_design"

    # Risk / Mode 取 docs/07 §5.1 的 Tool 总表
    assert by_name["BUILD.COLUMN"].risk_level == "HIGH"
    assert by_name["BUILD.COLUMN"].execution_mode == "ASYNC"
    assert by_name["MODEL.NODE.QUERY"].risk_level == "LOW"
    assert by_name["MODEL.NODE.QUERY"].execution_mode == "SYNC"
    assert by_name["ANALYSIS.STATIC"].risk_level == "HIGH"

    # ⑧ 红线：Capability / Operation 取值不含厂商名（docs/07 §14.2）
    values = [capability.code for capability in capabilities]
    values += [operation.name for operation in operations]
    values += [operation.tool for operation in operations]
    for value in values:
        assert not any(vendor in value.upper() for vendor in VENDOR_NAMES), value


async def test_seed_creates_mock_software_chain(
    session_factory: SessionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock Software / Product / Version / Instance（`docs/02` §100 / §101）。"""
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    await seed(session_factory)

    async with session_factory() as session:
        software = (await session.execute(select(SoftwareORM))).scalar_one()
        product = (await session.execute(select(SoftwareProductORM))).scalar_one()
        version = (await session.execute(select(SoftwareVersionORM))).scalar_one()
        instance = (await session.execute(select(SoftwareInstanceORM))).scalar_one()

    assert software.vendor == MOCK_VENDOR == "StructAI"
    assert software.status == SoftwareStatus.ENABLED.value
    assert product.product == MOCK_PRODUCT == "Mock Engineering Software"
    assert product.software_id == software.id
    assert version.version == MOCK_VERSION == "1.0"
    assert version.product_id == product.id
    assert instance.name == MOCK_INSTANCE_NAME
    assert instance.version_id == version.id
    assert instance.status == SoftwareConnectionState.DISCONNECTED.value
    # 凭据只存引用、绝不存明文；Mock 实例无需凭据（`docs/07` §14.3）
    assert instance.credential_reference is None
    assert instance.endpoint is None


# ===== ④ 安全（`docs/02` §44 / §8；`docs/07` §14.3）=====


async def test_seed_requires_admin_password_from_environment(
    session_factory: SessionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """环境变量缺失 → `RuntimeError`，且库中**不留下**任何半成品数据（`docs/02` §44）。"""
    monkeypatch.delenv(ADMIN_PASSWORD_ENV, raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        await seed(session_factory)

    assert ADMIN_PASSWORD_ENV in str(excinfo.value)
    assert await _count(session_factory, TenantORM) == 0
    assert await _count(session_factory, UserORM) == 0

    # 空字符串同样视为缺失
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, "")
    with pytest.raises(RuntimeError):
        await seed(session_factory)


async def test_seed_stores_only_password_hash(
    engine: AsyncEngine,
    session_factory: SessionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """库中只写 Argon2id `password_hash`；明文口令不出现在任何表（`docs/02` §8）。"""
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    await seed(session_factory)

    async with session_factory() as session:
        user = (await session.execute(select(UserORM))).scalar_one()
    stored_hash = user.password_hash

    assert stored_hash != TEST_PASSWORD
    assert stored_hash.startswith("$argon2id$")

    service = PasswordService()
    assert service.verify(stored_hash, TEST_PASSWORD) is True
    assert service.verify(stored_hash, "wrong-password") is False

    # 全库扫描：任何文本列都不得包含明文口令
    for value in await _seeded_strings(engine):
        assert TEST_PASSWORD not in value


# ===== ⑤ 事务（`docs/07` §14.4）=====


def test_seed_module_uses_unit_of_work_without_bare_commit() -> None:
    """`seed.py` 内不得出现裸 `commit` / `rollback`，且必须经 `UnitOfWork` 提交。"""
    source_path = Path(seed_module.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    offenders = sorted(
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"commit", "rollback"}
    )
    assert offenders == []

    # 必须真的用 `async with UnitOfWork(session)` 包住写入（不是「提到过这个名字」）
    unit_of_work_blocks = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncWith)
        and any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Name)
            and item.context_expr.func.id == "UnitOfWork"
            for item in node.items
        )
    ]
    assert len(unit_of_work_blocks) == 1
    # 且该块内就是 Seed 的执行体（`_Seeder(...).run(...)`）
    block_source = ast.unparse(unit_of_work_blocks[0])
    assert "_Seeder" in block_source and ".run(" in block_source


# ===== 入口（CLI / 包级导出）=====


def test_cli_entry_point_seeds_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`python -m app.infrastructure.database.seed` 的等价调用：建表 → Seed → 幂等。"""
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p07_cli.db').as_posix()}"
    monkeypatch.setattr(seed_module, "settings", Settings(database_url=database_url))
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)

    # 库中还没有表：不加 --create-tables 必须明确失败（不静默建表，docs/02 §102）
    assert seed_module.main([]) == 2

    assert seed_module.main(["--create-tables"]) == 0
    assert seed_module.main([]) == 0
    assert seed_module.main([]) == 0


def test_cli_entry_point_requires_password(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """口令缺失 → 退出码 2（`docs/02` §44：缺失即 `RuntimeError`）。"""
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p07_cli_no_pw.db').as_posix()}"
    monkeypatch.setattr(seed_module, "settings", Settings(database_url=database_url))
    monkeypatch.delenv(ADMIN_PASSWORD_ENV, raising=False)

    assert seed_module.main(["--create-tables"]) == 2


def test_seed_entry_is_exported_from_package() -> None:
    """包级导出（PEP 562 惰性）指向同一个 `seed()`（`docs/07` §12 P07）。"""
    assert seed_database is seed
    assert SEED_ORDER is seed_module.SEED_ORDER
