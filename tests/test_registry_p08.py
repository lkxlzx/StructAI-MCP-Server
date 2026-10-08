"""P08 验收测试：Registry（`docs/07` §12 P08；`docs/02` §11 / §15 / §19–§23 / §86–§87 / §113）。

验收点（与续接提示词的 ①–⑩ 一一对应）：

① 主门槛：`operation_registry.get("BUILD.COLUMN")` 返回**完整** `OperationDefinition`
   （12 字段），且 69 个 Operation **全部**可 `get`；
② 装配来源：六个字段取自 P07 落库的 `operations` 表，其余六字段由 Registry 补齐
   （每条映射都能指回章节 —— 逐条断言 `anchor` 非空且引用 `docs/07` / `docs/02` 章节）；
③ `CapabilityRegistry`：`capabilities` 表 41 条可查询；`operation_capabilities` 由本批落库；
④ `SchemaRegistry`：`register` / `get`；未注册 id → `NotFoundError`（且**不**新增错误码）；
⑤ `SoftwareRegistry`：`get_instance` / `get_product` / `get_version` / `list_instances`；
⑥ API Registry：九字段；636 端点 / 625 Schema 可装载；取值只能来自数据文件；
⑦ 失败即不就绪：Registry 校验失败 → `InternalError` 且容器**不**进入 READY；
⑧ 未配备的库不阻断启动（`python -m app.main` 回归门槛）；
⑨ 质量：由 `ruff` / `mypy` 覆盖（本文件不重复）；
⑩ 红线：`app/` 内厂商名 0 处；`app/domain/` 无 SQLAlchemy；Registry 不得自行 `commit`。

⚠️ 本文件里的「规范原文副本」（Tool 表 / 能力码 / Recovery Policy 分类）**故意不**从
被测模块取：若断言只与被测常量比较，则「常量被改错」与「写库被改错」会一起通过
（同源循环）。此处逐字抄写规范，任何一侧漂移都会让测试失败。
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import re
import subprocess
import sys
from collections.abc import AsyncIterator
from dataclasses import fields
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config.settings import Settings
from app.container import BATCH_ID, build_container
from app.domain.enums import (
    Capability,
    ExecutionMode,
    PermissionCode,
    RiskLevel,
    SoftwareConnectionState,
)
from app.domain.errors import InternalError, NotFoundError, StructAIError
from app.infrastructure.database import Base, create_engine, create_session_factory
from app.infrastructure.database.models import (
    CapabilityORM,
    OperationCapabilityORM,
    OperationORM,
    SoftwareInstanceORM,
    SoftwareProductORM,
    SoftwareVersionORM,
)
from app.infrastructure.database.seed import (
    ADMIN_PASSWORD_ENV,
    MOCK_INSTANCE_NAME,
    MOCK_PRODUCT,
    MOCK_VENDOR,
    MOCK_VERSION,
    seed,
)
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.infrastructure.registry import (
    API_REGISTRY_FIELDS,
    ApiRegistry,
    ApiRegistryEntry,
    CapabilityRegistry,
    OperationRegistry,
    SchemaRegistry,
    SoftwareRegistry,
    sync_operation_capabilities,
)
from app.infrastructure.registry import operation_registry as operation_registry_module
from app.infrastructure.registry.operation_registry import (
    OPERATION_CAPABILITIES,
    OPERATION_COUNT,
    OPERATION_PROFILES,
    RECOVERY_POLICIES,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"

VENDOR_NAMES = ("MIDAS", "CSI", "ANSYS")
"""`docs/07` §14.2：Capability / Operation 取值与 `app/` 内禁止出现的厂商名。"""

TEST_PASSWORD = "P08-Registry-验收-口令-7c21"
"""测试用口令（非真实 secret，仅存在于测试进程内）。"""

SessionFactory = async_sessionmaker[AsyncSession]
"""会话工厂类型别名（`docs/02` §15）。"""


# ===== 规范原文副本（`docs/07` §5.1 / §5.4 / §6.10；`docs/02` §45 / §69–§70 / §86–§87）=====

DOC_TOOL_OPERATIONS: dict[str, tuple[str, ...]] = {
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
"""`docs/07` §5.1（Tool 总表）＋ `docs/02` §69：Tool → Operation（6+8+8+7+14+7+6+6+7 = 69）。"""

DOC_TOOL_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "engineering_doc": ("DOCUMENT_READ", "DOCUMENT_WRITE"),
    "engineering_model_query": ("MODEL_READ",),
    "engineering_model_assign": ("MODEL_WRITE",),
    "engineering_model_delete": ("MODEL_DELETE",),
    "engineering_model_build": ("MODEL_WRITE",),
    "engineering_view": ("MODEL_READ", "RESULT_READ"),
    "engineering_result": ("RESULT_READ",),
    "engineering_design": ("DESIGN_EXECUTE", "DESIGN_MODIFY"),
    "engineering_analysis": ("ANALYSIS_EXECUTE",),
}
"""`docs/07` §5.1 的权限列（`/` 表示按 Operation 二选一；`(+…)` 为条件权限）。"""

DOC_TRANSACTIONAL_TOOLS = (
    "engineering_model_build",
    "engineering_result",
    "engineering_design",
)
"""`docs/07` §6.10：映射性质为「组合」的三类（build 14 + result 6 + design 6 = 26）。"""

DOC_DRY_RUN_TOOLS = (
    "engineering_model_build",
    "engineering_model_assign",
    "engineering_model_delete",
    "engineering_design",
    "engineering_analysis",
)
"""`docs/07` §5.4 Dry Run 矩阵：build=必须；assign / delete / design / analysis=推荐。"""

DOC_SAFE_RETRY_OPERATIONS = ("MODEL.NODE.QUERY",)
"""`docs/02` §45：`MODEL.NODE.QUERY → SAFE_RETRY`。"""

DOC_STATE_RECONCILE_OPERATIONS = ("BUILD.COLUMN", "MODEL.NODE.DELETE")
"""`docs/02` §45：`BUILD.COLUMN → STATE_RECONCILE`、`MODEL.DELETE → STATE_RECONCILE`。

⚠️ §45 的第二个例子写作 `MODEL.DELETE`（族名写法）；此处按**具体 Operation**
`MODEL.NODE.DELETE` 核对（7 条 `MODEL.*.DELETE` 同属该族）。
"""

DOC_MANUAL_REVIEW_OPERATIONS = ("DESIGN.OPTIMIZE",)
"""`docs/02` §45：`DESIGN.OPTIMIZE → MANUAL_REVIEW`。"""

DOC_CAPABILITY_CODES: tuple[str, ...] = (
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
"""`docs/02` §70 ＋ `docs/07` §5.6：41 条能力码（逐字抄写）。"""

DOC_RECOVERY_POLICY_VALUES = frozenset({"SAFE_RETRY", "STATE_RECONCILE", "MANUAL_REVIEW", "FAIL"})
"""`docs/02` §45 的 Recovery Policy 分类（`FAIL` 为 `docs/02` §11 的默认值）。"""

DOC_ERROR_CODES = (
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
"""`docs/07` §11：冻结的 **20 码**错误契约（逐字抄写）。"""


# ===== 夹具 =====


@pytest.fixture
async def seeded_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncEngine]:
    """临时 SQLite + 24 张表 + P07 Seed（69 Operation / 41 Capability / Mock 软件链）。"""
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p08_registry.db').as_posix()}"
    engine = create_engine(database_url, echo=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    await seed(create_session_factory(engine))

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def seeded_factory(seeded_engine: AsyncEngine) -> SessionFactory:
    """已 Seed 库的会话工厂。"""
    return create_session_factory(seeded_engine)


async def _sync_operation_capabilities(factory: SessionFactory) -> None:
    """在一个 `UnitOfWork` 内落库 Operation ↔ Capability（`docs/02` §27 / §31）。"""
    async with factory() as session:
        async with UnitOfWork(session):
            await sync_operation_capabilities(session)


async def _provision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str = "p08_main.db",
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


async def _count(factory: SessionFactory, model: type[object]) -> int:
    """某表行数。"""
    async with factory() as session:
        return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


# ===== ① 主门槛（`docs/07` §12 P08 / `docs/02` §113）=====

DOC_OPERATION_FIELDS = (
    "name",
    "tool",
    "risk_level",
    "execution_mode",
    "input_schema",
    "output_schema",
    "required_permissions",
    "required_capabilities",
    "transactional",
    "rollback_supported",
    "dry_run_supported",
    "recovery_policy",
)
"""`docs/07` §4.2 / `docs/02` §21：`OperationDefinition` 的 **12 字段**（逐字抄写）。"""


async def test_gate_build_column_returns_the_complete_definition(
    seeded_engine: AsyncEngine,
    seeded_factory: SessionFactory,
) -> None:
    """门槛 ①：`get("BUILD.COLUMN")` 返回**完整** `OperationDefinition`（12 字段全有值）。"""
    registry = await OperationRegistry.load(seeded_engine, seeded_factory)
    assert registry is not None

    definition = await registry.get("BUILD.COLUMN")
    assert definition is not None
    assert tuple(field.name for field in fields(definition)) == DOC_OPERATION_FIELDS

    assert definition.name == "BUILD.COLUMN"
    assert definition.tool == "engineering_model_build"
    assert definition.risk_level is RiskLevel.HIGH
    assert definition.execution_mode is ExecutionMode.ASYNC
    assert definition.input_schema == "structai://schema/build/column/v1"
    assert definition.output_schema == "structai://schema/build/column/result/v1"
    assert definition.required_permissions == ("MODEL_WRITE",)
    assert definition.required_capabilities == ("MODEL.NODE.WRITE", "MODEL.ELEMENT.WRITE")
    assert definition.transactional is True
    assert definition.rollback_supported is True
    assert definition.dry_run_supported is True
    assert definition.recovery_policy == "STATE_RECONCILE"
    assert definition.recovery_policy in DOC_RECOVERY_POLICY_VALUES


async def test_gate_all_69_operations_are_resolvable(
    seeded_engine: AsyncEngine,
    seeded_factory: SessionFactory,
) -> None:
    """门槛 ①：69 个 Operation **全部**可 `get`（任一返回 `None` 即失败）。"""
    registry = await OperationRegistry.load(seeded_engine, seeded_factory)
    assert registry is not None

    expected = {name for names in DOC_TOOL_OPERATIONS.values() for name in names}
    assert len(expected) == OPERATION_COUNT == 69
    assert len(registry) == 69
    assert registry.names() == tuple(sorted(expected))

    for name in sorted(expected):
        definition = await registry.get(name)
        assert definition is not None, name
        assert definition.name == name
        assert definition.tool in DOC_TOOL_OPERATIONS
        assert definition.risk_level in RiskLevel
        assert definition.execution_mode in ExecutionMode

    # 未知 Operation → `None`（域契约口径）
    assert await registry.get("NOT.AN.OPERATION") is None
    with pytest.raises(NotFoundError):
        registry.require("NOT.AN.OPERATION")

    # Tool 归属与 `docs/07` §5.1 的 6/8/8/7/14/7/6/6/7 一致
    for tool, names in DOC_TOOL_OPERATIONS.items():
        assert [item.name for item in registry.for_tool(tool)] == sorted(names)

    listed = await registry.list()
    assert [item.name for item in listed] == sorted(expected)


# ===== ② 装配来源（六字段来自 `operations` 表；六字段由 Registry 补齐）=====


async def test_six_fields_come_from_the_operations_table(
    seeded_engine: AsyncEngine,
    seeded_factory: SessionFactory,
) -> None:
    """门槛 ②：六字段取自 P07 落库的 `operations` 表 —— 改库后重新装配即随之变化。"""
    registry = await OperationRegistry.load(seeded_engine, seeded_factory)
    assert registry is not None
    definition = await registry.get("MODEL.NODE.QUERY")
    assert definition is not None

    async with seeded_factory() as session:
        row = (
            await session.execute(
                select(OperationORM).where(OperationORM.name == "MODEL.NODE.QUERY")
            )
        ).scalar_one()
        assert definition.tool == row.tool
        assert definition.risk_level.value == row.risk_level
        assert definition.execution_mode.value == row.execution_mode
        assert definition.input_schema == row.input_schema
        assert definition.output_schema == row.output_schema

    # 改库（仍是合法取值）→ 重新装配后定义随之变化（证明不是硬编码）
    async with seeded_factory() as session:
        async with UnitOfWork(session):
            await session.execute(
                update(OperationORM)
                .where(OperationORM.name == "MODEL.NODE.QUERY")
                .values(
                    risk_level=RiskLevel.MEDIUM.value,
                    execution_mode=ExecutionMode.STREAM.value,
                    input_schema="structai://schema/model/node/query/v9",
                    output_schema="structai://schema/model/node/result/v9",
                )
            )

    reloaded = await OperationRegistry.load(seeded_engine, seeded_factory)
    assert reloaded is not None
    changed = await reloaded.get("MODEL.NODE.QUERY")
    assert changed is not None
    assert changed.risk_level is RiskLevel.MEDIUM
    assert changed.execution_mode is ExecutionMode.STREAM
    assert changed.input_schema == "structai://schema/model/node/query/v9"
    assert changed.output_schema == "structai://schema/model/node/result/v9"

    # 其余六字段仍由 Registry 补齐（与静态映射逐项一致）
    profile = OPERATION_PROFILES["MODEL.NODE.QUERY"]
    assert changed.required_permissions == profile.required_permissions
    assert changed.required_capabilities == profile.required_capabilities
    assert changed.transactional is profile.transactional
    assert changed.rollback_supported is profile.rollback_supported
    assert changed.dry_run_supported is profile.dry_run_supported
    assert changed.recovery_policy == profile.recovery_policy


def test_profiles_cover_all_operations_and_are_anchored() -> None:
    """门槛 ②：69 条补齐映射齐全；每条都能指回具体章节；取值都来自 P03 冻结枚举。"""
    expected = {name for names in DOC_TOOL_OPERATIONS.values() for name in names}
    assert len(OPERATION_PROFILES) == OPERATION_COUNT == 69
    assert set(OPERATION_PROFILES) == expected
    assert set(OPERATION_CAPABILITIES) == expected

    capability_codes = {code.value for code in Capability}
    permission_codes = {code.value for code in PermissionCode}
    assert capability_codes == set(DOC_CAPABILITY_CODES)
    assert len(capability_codes) == 41

    for name, profile in OPERATION_PROFILES.items():
        assert profile.anchor, name
        assert "docs/07 §" in profile.anchor, name
        assert "docs/02 §" in profile.anchor, name
        assert profile.required_permissions, name
        assert profile.required_capabilities, name
        assert profile.recovery_policy in DOC_RECOVERY_POLICY_VALUES, name
        assert profile.rollback_supported is profile.transactional, name
        assert set(profile.required_permissions) <= permission_codes, name
        assert set(profile.required_capabilities) <= capability_codes, name


def test_profiles_match_the_documented_examples() -> None:
    """门槛 ②：`docs/02` §86 / §87 与 `docs/07` §5.1 / §5.5 的示例逐条对齐。"""
    node_create = OPERATION_PROFILES["MODEL.NODE.CREATE"]
    assert node_create.required_permissions == ("MODEL_WRITE",)
    assert node_create.required_capabilities == ("MODEL.NODE.WRITE",)

    node_delete = OPERATION_PROFILES["MODEL.NODE.DELETE"]
    assert node_delete.required_permissions == ("MODEL_DELETE",)
    assert node_delete.required_capabilities == ("MODEL.NODE.DELETE",)

    static = OPERATION_PROFILES["ANALYSIS.STATIC"]
    assert static.required_permissions == ("ANALYSIS_EXECUTE",)
    assert static.required_capabilities == ("ANALYSIS.STATIC",)

    query = OPERATION_PROFILES["MODEL.NODE.QUERY"]
    assert query.required_permissions == ("MODEL_READ",)
    assert query.required_capabilities == ("MODEL.NODE.READ",)

    # `docs/07` §5.1 `engineering_view` 的 `MODEL_READ/RESULT_READ`：按 Operation 二选一
    assert OPERATION_PROFILES["VIEW.MODEL"].required_permissions == ("MODEL_READ",)
    assert OPERATION_PROFILES["VIEW.DISPLACEMENT"].required_permissions == ("RESULT_READ",)

    # `docs/07` §5.1 `engineering_design` 的 `DESIGN_EXECUTE(+DESIGN_MODIFY)`：条件权限只挂 OPTIMIZE
    assert OPERATION_PROFILES["DESIGN.STEEL"].required_permissions == ("DESIGN_EXECUTE",)
    assert OPERATION_PROFILES["DESIGN.OPTIMIZE"].required_permissions == (
        "DESIGN_EXECUTE",
        "DESIGN_MODIFY",
    )

    # `docs/07` §5.1 `engineering_doc` 的 `DOCUMENT_READ/WRITE`：只读的 INFO 取 READ
    assert OPERATION_PROFILES["INFO"].required_permissions == ("DOCUMENT_READ",)
    assert OPERATION_PROFILES["SAVE"].required_permissions == ("DOCUMENT_WRITE",)

    # `docs/07` §6.5 / `docs/02` §86：Build 类只声明两个写能力；NODE_GRID 只建节点
    assert OPERATION_PROFILES["BUILD.NODE_GRID"].required_capabilities == ("MODEL.NODE.WRITE",)
    assert OPERATION_PROFILES["BUILD.FOUNDATION"].required_capabilities == (
        "MODEL.NODE.WRITE",
        "MODEL.ELEMENT.WRITE",
    )

    # `docs/07` §6.7：`RESULT.ANALYSIS.SUMMARY` 是通用入口 → 覆盖 RESULT 域全部能力码
    assert set(OPERATION_PROFILES["RESULT.ANALYSIS.SUMMARY"].required_capabilities) == {
        code for code in DOC_CAPABILITY_CODES if code.startswith("RESULT.")
    }


def test_transactional_dry_run_and_recovery_follow_the_matrices() -> None:
    """门槛 ②：`transactional` / `dry_run_supported` / `recovery_policy` 与规范矩阵一致。"""
    transactional_tools = set(DOC_TRANSACTIONAL_TOOLS)
    dry_run_tools = set(DOC_DRY_RUN_TOOLS)

    for tool, names in DOC_TOOL_OPERATIONS.items():
        for name in names:
            profile = OPERATION_PROFILES[name]
            assert profile.transactional is (tool in transactional_tools), name
            assert profile.dry_run_supported is (tool in dry_run_tools), name

    # `docs/07` §6.10：组合类 14 + 6 + 6 = 26；`docs/07` §5.4：Dry Run 支持 14+8+7+6+7 = 42
    assert sum(1 for item in OPERATION_PROFILES.values() if item.transactional) == 26
    assert sum(1 for item in OPERATION_PROFILES.values() if item.dry_run_supported) == 42

    for name in DOC_SAFE_RETRY_OPERATIONS:
        assert OPERATION_PROFILES[name].recovery_policy == "SAFE_RETRY"
    for name in DOC_STATE_RECONCILE_OPERATIONS:
        assert OPERATION_PROFILES[name].recovery_policy == "STATE_RECONCILE"
    for name in DOC_MANUAL_REVIEW_OPERATIONS:
        assert OPERATION_PROFILES[name].recovery_policy == "MANUAL_REVIEW"
    assert "FAIL" not in {item.recovery_policy for item in OPERATION_PROFILES.values()}
    assert RECOVERY_POLICIES == DOC_RECOVERY_POLICY_VALUES


# ===== ③ CapabilityRegistry（41 条可查询 + `operation_capabilities` 落库）=====


async def test_capability_registry_exposes_the_41_capabilities(
    seeded_engine: AsyncEngine,
    seeded_factory: SessionFactory,
) -> None:
    """门槛 ③：`capabilities` 表 41 条可查询，取值与 `docs/02` §70 一致。"""
    registry = await CapabilityRegistry.load(seeded_engine, seeded_factory)
    assert registry is not None
    assert len(registry) == 41

    listed = await registry.list()
    assert [item.code for item in listed] == sorted(DOC_CAPABILITY_CODES)
    assert registry.codes() == tuple(sorted(DOC_CAPABILITY_CODES))
    assert "MODEL.NODE.READ" in registry

    first = await registry.get("MODEL.NODE.READ")
    assert first is not None
    assert first.code == "MODEL.NODE.READ"
    assert first.category == "MODEL"
    assert first.name == "MODEL.NODE.READ"
    assert first.version == "1.0"

    assert await registry.get("MODEL.NOPE") is None
    with pytest.raises(NotFoundError):
        registry.require("MODEL.NOPE")

    # `docs/07` §14.2：能力码不得含厂商名
    for code in registry.codes():
        assert not any(vendor.lower() in code.lower() for vendor in VENDOR_NAMES)

    # Operation ↔ Capability 关系（`docs/02` §31）
    assert registry.capabilities_for("MODEL.NODE.CREATE") == ("MODEL.NODE.WRITE",)
    assert registry.capabilities_for("DESIGN.STEEL") == ("DESIGN.STEEL",)
    assert registry.capabilities_for("NOT.AN.OPERATION") == ()
    assert "MODEL.NODE.CREATE" in registry.operations_for("MODEL.NODE.WRITE")
    assert registry.operations_for("MODEL.NOPE") == ()


async def test_operation_capabilities_are_persisted_and_idempotent(
    seeded_engine: AsyncEngine,
    seeded_factory: SessionFactory,
) -> None:
    """门槛 ③：`operation_capabilities` 由本批落库；重复执行零新增（幂等）。"""
    assert await _count(seeded_factory, OperationCapabilityORM) == 0

    expected_pairs = {
        (name, code) for name, codes in OPERATION_CAPABILITIES.items() for code in codes
    }
    assert len(expected_pairs) == 86

    async with seeded_factory() as session:
        async with UnitOfWork(session):
            report = await sync_operation_capabilities(session)
    assert report.created == 86
    assert report.existing == 0
    assert report.total == 86
    assert "created 86 row(s)" in report.summary()

    async with seeded_factory() as session:
        async with UnitOfWork(session):
            second = await sync_operation_capabilities(session)
    assert second.created == 0
    assert second.existing == 86
    assert await _count(seeded_factory, OperationCapabilityORM) == 86

    # 落库内容 == 静态映射（逐对核对，含 id → 业务键的还原）
    async with seeded_factory() as session:
        operation_names = {
            str(identifier): str(name)
            for identifier, name in (
                await session.execute(select(OperationORM.id, OperationORM.name))
            ).all()
        }
        capability_codes = {
            str(identifier): str(code)
            for identifier, code in (
                await session.execute(select(CapabilityORM.id, CapabilityORM.code))
            ).all()
        }
        rows = (
            await session.execute(
                select(
                    OperationCapabilityORM.operation_id,
                    OperationCapabilityORM.capability_id,
                )
            )
        ).all()
    actual_pairs = {(operation_names[str(o)], capability_codes[str(c)]) for o, c in rows}
    assert actual_pairs == expected_pairs

    # 关系表也能被 CapabilityRegistry 反查（落库后走数据库路径）
    registry = await CapabilityRegistry.load(seeded_engine, seeded_factory)
    assert registry is not None
    assert registry.capabilities_for("BUILD.COLUMN") == (
        "MODEL.NODE.WRITE",
        "MODEL.ELEMENT.WRITE",
    )
    assert "BUILD.COLUMN" in registry.operations_for("MODEL.NODE.WRITE")
    assert registry.summary()["relations"] == 86


async def test_operation_capabilities_sync_keeps_the_transaction_boundary(
    seeded_factory: SessionFactory,
) -> None:
    """门槛 ③/⑩：同步只 `flush` —— 回滚后一行都不留（边界归 `UnitOfWork`）。"""

    class _Abort(Exception):
        """测试用异常：触发 `UnitOfWork` 的回滚路径。"""

    with pytest.raises(_Abort):
        async with seeded_factory() as session:
            async with UnitOfWork(session):
                await sync_operation_capabilities(session)
                raise _Abort

    assert await _count(seeded_factory, OperationCapabilityORM) == 0


# ===== ④ SchemaRegistry（`docs/02` §15 / §22）=====


def test_schema_registry_register_get_and_not_found() -> None:
    """门槛 ④：`register` / `get`；未注册 id → `NotFoundError`（照 `docs/02` §15 原文）。"""
    registry = SchemaRegistry()
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}
    assert len(registry) == 0

    registry.register("structai://schema/model/node/v1", schema)
    assert registry.get("structai://schema/model/node/v1") == schema
    assert registry.is_registered("structai://schema/model/node/v1")
    assert registry.registered_ids() == ("structai://schema/model/node/v1",)
    assert "structai://schema/model/node/v1" in registry
    assert len(registry) == 1

    with pytest.raises(NotFoundError) as excinfo:
        registry.get("structai://schema/model/node/v2")
    assert "structai://schema/model/node/v2" in str(excinfo.value)

    # `docs/02` §12：旧版本不可覆盖 —— 靠版本化 id 表达（v1 / v2 是不同 id）
    registry.register("structai://schema/model/node/v2", {"type": "array"})
    assert registry.get("structai://schema/model/node/v1") == schema
    assert registry.get("structai://schema/model/node/v2") == {"type": "array"}
    assert registry.registered_ids() == (
        "structai://schema/model/node/v1",
        "structai://schema/model/node/v2",
    )


def test_not_found_error_does_not_extend_the_twenty_code_contract() -> None:
    """门槛 ④：`NotFoundError` **不**携带 `STRUCTAI-xxxx`；20 码契约仍恰好 20 码。"""
    assert not issubclass(NotFoundError, StructAIError)
    assert not hasattr(NotFoundError, "code")
    assert issubclass(NotFoundError, LookupError)

    declared = {klass.code for klass in StructAIError.__subclasses__()}
    assert declared == set(DOC_ERROR_CODES)
    assert len(declared) == 20

    # `app/` 内出现的 `STRUCTAI-xxxx` 字面量只能是这 20 码
    literal_codes: set[str] = set()
    for path in APP_DIR.rglob("*.py"):
        literal_codes |= set(re.findall(r"STRUCTAI-\d{4}", path.read_text(encoding="utf-8")))
    assert literal_codes == set(DOC_ERROR_CODES)


# ===== ⑤ SoftwareRegistry（`docs/02` §19）=====


async def test_software_registry_reads_the_mock_software_chain(
    seeded_engine: AsyncEngine,
    seeded_factory: SessionFactory,
) -> None:
    """门槛 ⑤：`get_instance` / `get_product` / `get_version` / `list_instances`。"""
    registry = await SoftwareRegistry.load(seeded_engine, seeded_factory)
    assert registry is not None

    instances = await registry.list_instances()
    assert len(instances) == 1
    instance = instances[0]
    assert instance.name == MOCK_INSTANCE_NAME
    assert instance.vendor == MOCK_VENDOR
    assert instance.product == MOCK_PRODUCT
    assert instance.version == MOCK_VERSION
    assert instance.status == SoftwareConnectionState.DISCONNECTED.value
    assert instance.endpoint is None

    # 视图**不**下发凭据引用（`docs/02` §21；`docs/07` §8.5 / §14.3）
    assert not hasattr(instance, "credential_reference")

    assert await registry.get_instance(instance.instance_id) == instance
    assert await registry.get_instance("nope") is None
    with pytest.raises(NotFoundError):
        registry.require_instance("nope")
    assert registry.instances() == (instance,)
    assert len(registry) == 1

    async with seeded_factory() as session:
        product_row = (await session.execute(select(SoftwareProductORM))).scalar_one()
        version_row = (await session.execute(select(SoftwareVersionORM))).scalar_one()
        instance_row = (await session.execute(select(SoftwareInstanceORM))).scalar_one()

    assert instance.instance_id == instance_row.id
    assert instance_row.credential_reference is None

    product = await registry.get_product(product_row.id)
    assert product is not None
    assert product.product == MOCK_PRODUCT
    assert product.vendor == MOCK_VENDOR
    assert product.software_id == product_row.software_id
    assert await registry.get_product("nope") is None

    version = await registry.get_version(version_row.id)
    assert version is not None
    assert version.version == MOCK_VERSION
    assert version.product_id == product_row.id
    assert await registry.get_version("nope") is None

    assert registry.summary()["vendors"] == [MOCK_VENDOR]


# ===== ⑥ API Registry（`docs/02` §23；数据源 = `registry/`）=====


def test_api_registry_loads_636_endpoints_and_625_schemas() -> None:
    """门槛 ⑥：`registry/` 是唯一数据源；636 端点 / 625 Schema 可装载（P141 起）。"""
    registry = ApiRegistry.load(REPO_ROOT / "registry")

    keys = registry.endpoint_keys()
    assert len(keys) == 636
    assert len(set(keys)) == 636

    schemas = registry.request_schemas()
    assert len(schemas) == 625
    for relative in schemas:
        assert (REPO_ROOT / "registry" / relative).is_file(), relative

    summary = registry.summary()
    assert summary["endpoints"] == 636
    assert summary["schemas"] == 625
    assert summary["products"] == ["CIVIL_DESIGNER", "CIVIL_NX", "GEN_NX"]
    assert summary["disabled"] == ["DB.SWIND"]

    # 数据文件里被禁用的端点（`enabled: false`）不得产生映射（`registry/README.md` §4）
    assert registry.is_disabled("DB.SWIND")
    assert registry.disable_reason("DB.SWIND")
    assert registry.for_operation("DB.SWIND") == ()


def test_api_registry_entries_have_exactly_the_nine_fields() -> None:
    """门槛 ⑥：九字段不多不少；取值只能来自数据文件；产品覆盖生效。"""
    registry = ApiRegistry.load(REPO_ROOT / "registry")

    assert API_REGISTRY_FIELDS == (
        "software",
        "product",
        "version",
        "operation",
        "protocol",
        "method",
        "path",
        "request_schema",
        "response_schema",
    )
    assert tuple(field.name for field in fields(ApiRegistryEntry)) == API_REGISTRY_FIELDS

    seen: set[tuple[str, str, str]] = set()
    for entry in registry.list():
        assert entry.operation
        assert entry.product
        assert entry.method in {"GET", "POST", "PUT", "DELETE"}
        assert entry.protocol == "REST"
        assert entry.path.startswith("/")
        assert entry.software
        assert entry.request_schema == "" or entry.request_schema.startswith("schema/")
        assert entry.response_schema == ""
        identity = (entry.product, entry.operation, entry.method)
        assert identity not in seen
        seen.add(identity)
    assert len(seen) == len(registry)

    # 逐字段回溯到数据文件（`docs/07` §14.2：不得硬编码）
    manifest = json.loads((REPO_ROOT / "registry" / "manifest.json").read_text(encoding="utf-8"))
    by_key = {item["key"]: item for item in manifest["endpoints"]}

    resolved = registry.resolve(product="CIVIL_NX", operation="DB.NODE", method="GET")
    assert resolved is not None
    assert resolved.path == by_key["DB.NODE"]["uri"]
    assert resolved.request_schema == by_key["DB.NODE"]["schema"]
    assert resolved.operation in by_key

    # `product_overrides`：CIVIL_DESIGNER 的 NODE 只有 GET
    assert registry.resolve(product="CIVIL_DESIGNER", operation="DB.NODE", method="POST") is None
    assert registry.resolve(product="CIVIL_DESIGNER", operation="DB.NODE", method="GET") is not None
    assert registry.resolve(product="CIVIL_NX", operation="DB.NODE", method="POST") is not None
    assert registry.resolve(product="CIVIL_NX", operation="NOPE", method="GET") is None

    # `POST.TABLE.*` 端点（`docs/07` §6.7）在数据文件里逐表登记
    assert registry.for_operation("POST.TABLE.DISPLACEMENTG")


def test_api_registry_requires_the_configured_data_root(tmp_path: Path) -> None:
    """门槛 ⑥：数据源缺失 → `NotFoundError`；`app/` 内不得硬编码路径。"""
    with pytest.raises(NotFoundError):
        ApiRegistry.load(tmp_path)

    source = (APP_DIR / "infrastructure" / "registry" / "api_registry.py").read_text(
        encoding="utf-8"
    )
    for literal in ("/DB/", "/DOC/", "/POST/", "/VIEW/", "/OPE/", "/DESIGN/", "/OPRT/"):
        assert literal not in source


# ===== ⑦ 失败即不就绪（`docs/07` §14.4）=====


async def test_container_startup_assembles_the_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ⑦（正常路径）：装配成功 → `started` = True 且 Registry 有 69 条定义。"""
    database_url = await _provision(tmp_path, monkeypatch, "p08_container.db")
    container = build_container(Settings(database_url=database_url))
    try:
        await container.startup()
        assert container.started is True
        registry = container.operation_registry
        assert registry is not None
        assert len(registry) == 69
        assert await registry.get("BUILD.COLUMN") is not None
        assert registry.summary()["operations"] == 69
    finally:
        await container.shutdown()


async def test_container_startup_fails_when_an_operation_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ⑦（失败路径）：Registry 校验失败 → `InternalError`，Server MUST NOT become READY。"""
    database_url = await _provision(tmp_path, monkeypatch, "p08_missing_op.db")
    engine = create_engine(database_url, echo=False)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                delete(OperationORM).where(OperationORM.name == "BUILD.COLUMN")
            )
    finally:
        await engine.dispose()

    container = build_container(Settings(database_url=database_url))
    with pytest.raises(InternalError) as excinfo:
        await container.startup()
    assert excinfo.value.code == "STRUCTAI-7000"
    assert any("BUILD.COLUMN" in item for item in excinfo.value.details["failures"])
    assert container.started is False
    assert container.operation_registry is None
    await container.shutdown()


async def test_container_startup_fails_when_operation_capabilities_diverge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ⑦：`operation_capabilities` 与静态映射不一致 → 校验失败（不得 READY）。"""
    database_url = await _provision(tmp_path, monkeypatch, "p08_dangling.db")
    engine = create_engine(database_url, echo=False)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            async with UnitOfWork(session):
                session.add(OperationCapabilityORM(operation_id="ghost", capability_id="ghost"))
    finally:
        await engine.dispose()

    container = build_container(Settings(database_url=database_url))
    with pytest.raises(InternalError) as excinfo:
        await container.startup()
    assert any("dangling" in item for item in excinfo.value.details["failures"])
    assert container.started is False
    await container.shutdown()


async def test_container_startup_tolerates_an_unprovisioned_database(tmp_path: Path) -> None:
    """门槛 ⑧：未配备的库（无表）不阻断启动 —— Registry 留空、`started` = True。"""
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p08_empty.db').as_posix()}"
    container = build_container(Settings(database_url=database_url))
    try:
        await container.startup()
        assert container.started is True
        assert container.operation_registry is None
    finally:
        await container.shutdown()


async def test_all_four_registries_return_none_when_not_provisioned(tmp_path: Path) -> None:
    """门槛 ⑧：未配备的库上四个库注册表都返回 `None`（不抛异常、不建表）。"""
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p08_bare.db').as_posix()}"
    engine = create_engine(database_url, echo=False)
    try:
        factory = create_session_factory(engine)
        assert await OperationRegistry.load(engine, factory) is None
        assert await CapabilityRegistry.load(engine, factory) is None
        assert await SoftwareRegistry.load(engine, factory) is None
    finally:
        await engine.dispose()


def test_batch_id_is_a_batch_marker() -> None:
    """同步改动：`BATCH_ID` 始终形如 `P<两位数字>`（`docs/08` §3 的批次口径）。

    ⚠️ 本断言**刻意不绑定具体批次**：批次号每批前移（P08 → P09 → …），
    某一批的哈希与证据留在 `docs/08` §3 与对应提交里；当前批次的号由该批次自己的
    验收测试断言（如 `tests/test_schema_p09.py::test_batch_id_is_p09`）。
    """
    assert re.fullmatch(r"P\d{2}", BATCH_ID)


# ===== ⑩ 红线（`docs/07` §14）=====


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


def test_registry_never_commits_and_uow_is_the_only_committer() -> None:
    """门槛 ⑩：Registry 不得自行 `commit` / `rollback`（边界归 `UnitOfWork`）。"""
    registry_dir = APP_DIR / "infrastructure" / "registry"
    offenders = {
        path.name: _commit_or_rollback_calls(path)
        for path in sorted(registry_dir.glob("*.py"))
        if _commit_or_rollback_calls(path)
    }
    assert offenders == {}

    committers = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in APP_DIR.rglob("*.py")
        if _commit_or_rollback_calls(path)
    )
    assert committers == ["app/infrastructure/database/unit_of_work.py"]


def test_red_lines_vendor_names_and_domain_purity() -> None:
    """门槛 ⑩：`app/` 内厂商名 0 处；`app/domain/` 内无 SQLAlchemy。"""
    vendor_hits = [
        f"{path.relative_to(REPO_ROOT).as_posix()}:{vendor}"
        for path in sorted(APP_DIR.rglob("*.py"))
        if not ({"midas", "etabs"} & set(path.parts))  # docs/07 §7.1：厂商专属代码的唯一豁免区
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


# ===== 入口（CLI / `python -m app.main`）=====


def test_operation_registry_cli_persists_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`python -m app.infrastructure.registry.operation_registry`：落库 → 幂等 → 退出码 0。"""
    database_url = asyncio.run(_provision(tmp_path, monkeypatch, "p08_cli.db"))
    monkeypatch.setattr(operation_registry_module, "settings", Settings(database_url=database_url))

    assert operation_registry_module.main([]) == 0
    assert "created 86 row(s)" in capsys.readouterr().out

    assert operation_registry_module.main([]) == 0
    assert "created 0 row(s)" in capsys.readouterr().out


def test_main_entry_point_exits_zero_with_empty_stdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ⑦/⑧：已配备的库上 `python -m app.main` 退出码 0 且 **stdout 0 字节**。"""
    database_url = asyncio.run(_provision(tmp_path, monkeypatch, "p08_main_cli.db"))
    environment = {**os.environ, "DATABASE_URL": database_url, "LOG_LEVEL": "INFO"}

    completed = subprocess.run(
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
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert f"batch={BATCH_ID}" in completed.stderr
