"""P09 验收测试：Schema（`docs/07` §12 P09；`docs/02` §12–§17 / §22 / §114）。

验收点（与续接提示词的 ①–⑧ 一一对应）：

① 主门槛（`docs/07` §12 P09 / `docs/02` §114）：`load schema` → `validate valid data`（通过）
   → `reject invalid data`（拒绝）；拒绝必须抛 `SchemaValidationError` = `STRUCTAI-1100`，
   **不**返回 `False` / 静默通过；
② `SchemaRegistry`（`docs/02` §14 / §15 / §22）：id 口径 `structai://schema/<…>/v1`；
   未注册 id → `NotFoundError`（P08 已落地，不得回退，**不**自造 `STRUCTAI-xxxx` 码）；
③ Schema 装载：`registry/schema/` 的 **616** 个 Schema 与 P07 固化的
   `input_schema` / `output_schema` URI 对齐，并说明无法对齐的部分（20 个端点无 Schema，R5）；
④ JSON Schema 版本裁决（`docs/07` §16 R18）：440 draft-07 / 175 未声明 / 1 个非法 JSON 字符串；
⑤ 分层与边界（`docs/07` §14.1 / §2.2）：`SchemaEngine` 只做「Schema → 参数」校验，
   `EngineeringValidator` 本批**不**实现；容器形状仍为 `docs/02` §33 的冻结形状；
⑥ 回归：`python -m app.main` 退出码 0（stdout 0 字节；未配备库与已配备库两种情形）、
   P04 建表 24 张 / `SELECT 1`、P02 覆盖行为、**59 项既有 pytest 不得回退**
   （由整轮 `pytest -q` 与验收证据覆盖；本文件只补 `app.main` 两条）；
⑦ 质量：由 `ruff` / `mypy` 覆盖（本文件不重复）；本文件额外断言依赖清单**未扩**（`docs/07` §3.1）；
⑧ 红线：`app/` 内厂商名 0 处、`app/domain/` 无 SQLAlchemy、不新增 `STRUCTAI-xxxx` 码、
   `commit()` / `rollback()` 只出现在 `unit_of_work.py`。

⚠️ 本文件里的「规范原文副本」（20 码清单 / 数据侧计数 / 端点清单）**故意不**从被测模块取：
若断言只与被测常量比较，「常量被改错」与「实现被改错」会一起通过（同源循环）。
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
import tomllib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft7Validator, Draft202012Validator  # type: ignore[import-untyped]
from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.execution.validation import (
    DEFAULT_DIALECT,
    DRAFT7_URI,
    SCHEMA_2020_12_URI,
    SUPPORTED_DIALECTS,
    SchemaEngine,
    dialect_of,
    validator_for,
)
from app.config.settings import Settings
from app.container import BATCH_ID, AppContainer
from app.domain.errors import InternalError, NotFoundError, StructAIError
from app.infrastructure.database import Base, create_engine, create_session_factory
from app.infrastructure.database.models import OperationORM
from app.infrastructure.database.seed import (
    ADMIN_PASSWORD_ENV,
    OPERATIONS,
    input_schema_uri,
    output_schema_uri,
    seed,
)
from app.infrastructure.registry import (
    SCHEMA_DIR,
    SCHEMA_URI_PREFIX,
    UNDECLARED_DIALECT,
    SchemaRegistry,
    schema_id_for,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
REGISTRY_ROOT = REPO_ROOT / "registry"
SCHEMA_ROOT = REGISTRY_ROOT / SCHEMA_DIR

VENDOR_NAMES = ("MIDAS", "CSI", "ANSYS")
"""`docs/07` §14.2：`app/` 内禁止出现的厂商名。"""

TEST_PASSWORD = "P09-Schema-验收-口令-4f13"
"""测试用口令（非真实 secret，仅存在于测试进程内）。"""

SessionFactory = async_sessionmaker[AsyncSession]
"""会话工厂类型别名（`docs/02` §15）。"""


# ===== 规范原文副本（`docs/07` §11 / §12 P09；`docs/02` §114；数据侧实测计数）=====

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

EXPECTED_SCHEMA_FILES = 616
"""`registry/README.md` §3：数据侧 Schema 文件数。"""

EXPECTED_REGISTERED = 615
"""本批实际登记的 Schema 数（616 − 1 个无法还原，见 `UNRESOLVABLE_FILES`）。"""

EXPECTED_DRAFT7 = 440
"""数据侧声明 `draft-07` 的 Schema 数（本批实测）。"""

EXPECTED_UNDECLARED = 175
"""数据侧**未**声明 `$schema` 的 Schema 数（本批实测；R18 的另一半）。"""

ENDPOINTS_WITHOUT_SCHEMA = frozenset(
    {
        "DB.LCOM",
        "DOC.CLOSEALL",
        "DOC.EXIT",
        "OPE.BMLD",
        "OPE.CPCREATE",
        "OPE.CPEXPORT",
        "OPE.CPUPDATEMODEL",
        "OPE.CPUPDATERESULT",
        "OPE.MEMB",
        "OPE.PROJECTSTATUS",
        "OPE.SECTPROP",
        "OPE.STOR",
        "OPE.STORPROP",
        "OPE.STORYPROP",
        "OPE.STORY_IRR_PARAM",
        "OPE.STORY_PARAM",
        "POST.TABLE.CONCURRENT_JOINT_FORCE",
        "POST.TABLE.STORY_SHEAR_FORCE_COEFFICIENT",
        "POST.TABLE.WEIGHT_IRREGULARITY_X",
        "VIEW.SELECT",
    }
)
"""`docs/07` §16 R5：数据侧 **20** 个没有 JSON Schema 的端点（本批实测清单）。"""

UNRESOLVABLE_FILES = ("products/gen_nx/db/MBTP.json",)
"""数据缺陷：`schema` 是**非法 JSON 字符串**，无法还原成对象（`docs/07` §16 R19）。"""

DEFECTIVE_SCHEMA_IDS = frozenset(
    {
        "structai://schema/design/src/aik-src2k/matd/v1",
        "structai://schema/design/src/aik-src2k/mcrd/v1",
        "structai://schema/design/src/aik-src2k/mrbd/v1",
        "structai://schema/ope/edmp/v1",
    }
)
"""不是合法 JSON Schema 的 4 个已登记 id（`docs/07` §16 R19；由 `check_schema` 诊断）。"""

ALIGNED_OPERATION_URIS = frozenset(
    {
        "structai://schema/doc/close/v1",
        "structai://schema/doc/new/v1",
        "structai://schema/doc/open/v1",
        "structai://schema/doc/save/v1",
    }
)
"""P07 的 138 个 Operation URI 中，能被数据侧 Schema 解析的 **4** 个（本批实测）。"""

ACTL_ID = "structai://schema/db/actl/v1"
"""`DB.ACTL` 的 Schema id（主门槛用它演示「合法通过 / 非法拒绝」）。"""


# ===== 夹具与辅助 =====


@pytest.fixture(scope="module")
def schema_registry() -> SchemaRegistry:
    """从 `registry/` 装载的 Schema 注册表（`docs/02` §14 / §22）。"""
    return SchemaRegistry.load(REGISTRY_ROOT)


@pytest.fixture(scope="module")
def schema_engine(schema_registry: SchemaRegistry) -> SchemaEngine:
    """绑定真实注册表的 `SchemaEngine`（`docs/02` §16）。"""
    return SchemaEngine(schema_registry)


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    """临时 SQLite + 建表（`docs/02` §15 / §36）。"""
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p09_schema.db').as_posix()}"
    engine = create_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> SessionFactory:
    """会话工厂（`docs/02` §15）。"""
    return create_session_factory(engine)


async def _provision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str = "p09_main.db",
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


def _relative_schema_files() -> tuple[str, ...]:
    """数据侧 Schema 文件的相对路径（升序）。"""
    return tuple(
        sorted(path.relative_to(SCHEMA_ROOT).as_posix() for path in SCHEMA_ROOT.rglob("*.json"))
    )


def _document(relative: str) -> dict[str, Any]:
    """读取一个数据侧 Schema 文件。"""
    return json.loads((SCHEMA_ROOT / relative).read_text(encoding="utf-8"))


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


# ===== ① 主门槛（`docs/07` §12 P09 / `docs/02` §114）=====


def test_gate_load_schema_then_validate_valid_and_reject_invalid(
    schema_registry: SchemaRegistry,
    schema_engine: SchemaEngine,
) -> None:
    """门槛 ①：`load schema` → 合法通过 → 非法拒绝（三步一条链，`docs/02` §114）。"""
    # 1) load schema
    assert schema_registry.is_registered(ACTL_ID)
    schema = schema_registry.get(ACTL_ID)
    assert schema["type"] == "object"
    assert {"ARDC", "ITER"} <= set(schema["properties"])

    # 2) validate valid data → 通过（返回 None，不抛异常）
    schema_engine.validate(ACTL_ID, {"ARDC": True, "ITER": 5, "TOL": 0.001})

    # 3) reject invalid data → 抛 `SchemaValidationError`（**不**返回 False / 静默通过）
    with pytest.raises(StructAIError) as excinfo:
        schema_engine.validate(ACTL_ID, {"ARDC": "not-a-boolean"})
    assert excinfo.value.code == "STRUCTAI-1100"
    assert excinfo.value.error_type == "SCHEMA_VALIDATION_ERROR"


def test_reject_carries_the_spec_error_details(schema_engine: SchemaEngine) -> None:
    """门槛 ①：`details` 形状 = `docs/02` §16 原文的 `errors`（`path` + `message`）。"""
    with pytest.raises(StructAIError) as excinfo:
        schema_engine.validate(ACTL_ID, {"ITER": "many"})

    details = excinfo.value.details
    assert details["schema_id"] == ACTL_ID
    assert set(details) == {"schema_id", "errors"}
    assert len(details["errors"]) == 1
    assert set(details["errors"][0]) == {"path", "message"}
    assert details["errors"][0]["path"] == ["ITER"]
    assert "is not of type 'integer'" in details["errors"][0]["message"]

    envelope = excinfo.value.to_dict()
    assert envelope["code"] == "STRUCTAI-1100"
    assert envelope["retryable"] is False


def test_reject_lists_every_error_in_a_deterministic_order(schema_engine: SchemaEngine) -> None:
    """门槛 ①：多条错误按**路径**排序输出（`docs/02` §16 原文的排序语义，总序实现）。"""
    with pytest.raises(StructAIError) as excinfo:
        schema_engine.validate(ACTL_ID, {"ITER": "many", "ARDC": "yes", "TOL": "small"})

    paths = [error["path"] for error in excinfo.value.details["errors"]]
    assert paths == [["ARDC"], ["ITER"], ["TOL"]]
    assert paths == sorted(paths)


def test_missing_required_field_is_rejected(schema_engine: SchemaEngine) -> None:
    """门槛 ①：`required` 缺失同样必须拒绝（不是「字段可选」）。"""
    schema_id = "structai://schema/doc/active/v1"
    assert schema_engine.registry.get(schema_id)["required"] == ["DocName"]

    with pytest.raises(StructAIError) as excinfo:
        schema_engine.validate(schema_id, {})
    assert excinfo.value.code == "STRUCTAI-1100"
    assert excinfo.value.details["errors"][0]["path"] == []
    assert "DocName" in excinfo.value.details["errors"][0]["message"]

    # 补上必填字段即通过（同一条链的两个方向）
    schema_engine.validate(schema_id, {"DocName": "p09-demo"})


def test_non_object_data_is_rejected_instead_of_raising_type_error(
    schema_engine: SchemaEngine,
) -> None:
    """门槛 ①：传入非对象也走**同一条拒绝路径**（不得泄漏 `TypeError`）。"""
    with pytest.raises(StructAIError) as excinfo:
        schema_engine.validate(ACTL_ID, ["ARDC"])
    assert excinfo.value.code == "STRUCTAI-1100"


def test_core_authored_2020_12_schema_round_trip() -> None:
    """门槛 ①/④：Core 自有的 **2020-12** Schema（`docs/02` §12 / §22）同样可校验。"""
    registry = SchemaRegistry()
    registry.register(
        "structai://schema/build/column/v1",
        {
            "$schema": SCHEMA_2020_12_URI,
            "type": "object",
            "required": ["base_node", "height"],
            "properties": {
                "base_node": {
                    "type": "object",
                    "required": ["x", "y", "z"],
                    "properties": {
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                        "z": {"type": "number"},
                    },
                },
                "height": {"type": "number", "exclusiveMinimum": 0},
            },
        },
    )
    engine = SchemaEngine(registry)
    assert engine.dialect("structai://schema/build/column/v1") == SCHEMA_2020_12_URI
    engine.validate(
        "structai://schema/build/column/v1",
        {"base_node": {"x": 0, "y": 0, "z": 0}, "height": 6},
    )

    with pytest.raises(StructAIError) as excinfo:
        engine.validate(
            "structai://schema/build/column/v1",
            {"base_node": {"x": 0, "y": 0, "z": None}, "height": 6},
        )
    assert excinfo.value.code == "STRUCTAI-1100"
    assert excinfo.value.details["errors"][0]["path"] == ["base_node", "z"]


def test_unknown_schema_id_is_not_a_schema_validation_error(schema_engine: SchemaEngine) -> None:
    """门槛 ②：未注册 id → `NotFoundError`（**不**伪装成 `STRUCTAI-1100`）。"""
    with pytest.raises(NotFoundError):
        schema_engine.validate("structai://schema/not/registered/v1", {})


# ===== ② SchemaRegistry 契约（P08 不得回退）=====


def test_registry_register_get_contract_is_unchanged() -> None:
    """门槛 ②：`register` / `get` 与 P08 逐项一致（含浅拷贝语义）。"""
    registry = SchemaRegistry()
    assert len(registry) == 0
    assert registry.registered_ids() == ()

    source = {"type": "object", "properties": {"id": {"type": "integer"}}}
    registry.register("structai://schema/model/node/v1", source)
    assert registry.is_registered("structai://schema/model/node/v1")
    assert "structai://schema/model/node/v1" in registry
    assert registry.get("structai://schema/model/node/v1") == source

    # 注册后改动调用方对象不得影响注册表（P08 的浅拷贝口径）
    source["type"] = "string"
    assert registry.get("structai://schema/model/node/v1")["type"] == "object"

    # 同名 id 再次登记 = 覆盖（`docs/02` §15 原文语义；版本靠 id 表达）
    registry.register("structai://schema/model/node/v1", {"type": "array"})
    assert registry.get("structai://schema/model/node/v1") == {"type": "array"}
    assert len(registry) == 1


def test_unregistered_id_raises_not_found_without_any_error_code() -> None:
    """门槛 ②：`NotFoundError` 是 `LookupError` 子类、**不带** `STRUCTAI-xxxx`（20 码不扩）。"""
    registry = SchemaRegistry()
    with pytest.raises(NotFoundError) as excinfo:
        registry.get("structai://schema/model/node/v9")
    assert str(excinfo.value) == "Schema not found: structai://schema/model/node/v9"
    assert not isinstance(excinfo.value, StructAIError)
    assert isinstance(excinfo.value, LookupError)
    assert not hasattr(excinfo.value, "code")
    assert not hasattr(excinfo.value, "to_dict")


def test_loaded_ids_follow_the_documented_uri_shape(schema_registry: SchemaRegistry) -> None:
    """门槛 ②/③：id 口径 = `structai://schema/<key 小写、"." → "/">/v1`。"""
    assert SCHEMA_URI_PREFIX == "structai://schema/"
    assert schema_id_for("DB.ACTL") == ACTL_ID
    assert (
        schema_id_for("POST.TABLE.DISPLACEMENTG") == "structai://schema/post/table/displacementg/v1"
    )
    assert (
        schema_id_for("DESIGN.RC.KDS-41-20-2022.DCO")
        == "structai://schema/design/rc/kds-41-20-2022/dco/v1"
    )

    ids = schema_registry.registered_ids()
    assert ids == tuple(sorted(ids))
    assert all(schema_id.startswith(SCHEMA_URI_PREFIX) for schema_id in ids)
    assert all(schema_id.endswith("/v1") for schema_id in ids)
    assert all(not schema_id.endswith("/result/v1") for schema_id in ids)


def test_load_reports_a_missing_data_source(tmp_path: Path) -> None:
    """门槛 ②/③：数据源缺失 → `NotFoundError`（装配期信号，`docs/07` §14.4）。"""
    with pytest.raises(NotFoundError):
        SchemaRegistry.load(tmp_path)


def test_load_rejects_a_malformed_schema_file(tmp_path: Path) -> None:
    """门槛 ②/③：文件不可解析 / 缺 `key` / id 重复 → `InternalError`（不得 READY）。"""
    schema_dir = tmp_path / SCHEMA_DIR
    schema_dir.mkdir()
    (schema_dir / "broken.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(InternalError) as excinfo:
        SchemaRegistry.load(tmp_path)
    assert excinfo.value.code == "STRUCTAI-7000"

    (schema_dir / "broken.json").write_text(json.dumps({"uri": "X"}), encoding="utf-8")
    with pytest.raises(InternalError):
        SchemaRegistry.load(tmp_path)

    payload = {"key": "DB.ACTL", "schema": {"ACTL": {"type": "object"}}}
    (schema_dir / "broken.json").write_text(json.dumps(payload), encoding="utf-8")
    duplicate = {"key": "db.actl", "schema": {"ACTL": {"type": "object"}}}
    (schema_dir / "duplicate.json").write_text(json.dumps(duplicate), encoding="utf-8")
    with pytest.raises(InternalError) as excinfo:
        SchemaRegistry.load(tmp_path)
    assert "duplicate" in str(excinfo.value.details).lower()


# ===== ③ Schema 装载与 Operation URI 对齐 =====


def test_load_covers_every_data_side_schema_file(schema_registry: SchemaRegistry) -> None:
    """门槛 ③：616 个文件 → 615 个登记 + 1 个无法还原（逐项计数可复算）。"""
    files = sorted(SCHEMA_ROOT.rglob("*.json"))
    assert len(files) == EXPECTED_SCHEMA_FILES

    report = schema_registry.report()
    assert report is not None
    assert report.files == EXPECTED_SCHEMA_FILES
    assert report.registered == EXPECTED_REGISTERED
    assert len(schema_registry) == EXPECTED_REGISTERED
    assert tuple(path for path, _ in report.unresolvable) == UNRESOLVABLE_FILES
    assert "not valid JSON" in report.unresolvable[0][1]

    summary = schema_registry.summary()
    assert summary["files"] == EXPECTED_SCHEMA_FILES
    assert summary["schemas"] == EXPECTED_REGISTERED
    assert summary["envelopes"] + summary["verbatim"] == EXPECTED_REGISTERED
    assert summary["unresolvable"] == [[UNRESOLVABLE_FILES[0], report.unresolvable[0][1]]]


def test_loaded_ids_correspond_one_to_one_with_the_manifest(
    schema_registry: SchemaRegistry,
) -> None:
    """门槛 ③：Schema 文件与 `manifest.json` 里带 `schema` 的端点 **1:1**（无孤儿）。"""
    manifest = json.loads((REGISTRY_ROOT / "manifest.json").read_text(encoding="utf-8"))
    endpoints = manifest["endpoints"]
    assert len(endpoints) == 636

    with_schema = {item["key"] for item in endpoints if item.get("schema")}
    without_schema = {item["key"] for item in endpoints if not item.get("schema")}
    assert len(with_schema) == EXPECTED_SCHEMA_FILES
    assert without_schema == ENDPOINTS_WITHOUT_SCHEMA

    file_keys = {_document(relative)["key"] for relative in _relative_schema_files()}
    assert file_keys == with_schema
    assert file_keys.isdisjoint(without_schema)

    expected_ids = {schema_id_for(key) for key in with_schema} - {schema_id_for("DB.MBTP")}
    assert set(schema_registry.registered_ids()) == expected_ids


def test_twenty_endpoints_still_have_no_schema_on_the_data_side() -> None:
    """门槛 ③（`docs/07` §16 R5）：20 个端点无 Schema —— 本批**不**臆造。"""
    manifest = json.loads((REGISTRY_ROOT / "manifest.json").read_text(encoding="utf-8"))
    without = [item for item in manifest["endpoints"] if not item.get("schema")]
    assert len(without) == len(ENDPOINTS_WITHOUT_SCHEMA) == 20
    assert {item["key"] for item in without} == ENDPOINTS_WITHOUT_SCHEMA


def test_operation_schema_uris_align_with_the_data_side(schema_registry: SchemaRegistry) -> None:
    """门槛 ③：P07 的 138 个 Operation URI 中 **4** 个可解析，**0** 个 `/result/v1`。"""
    assert len(OPERATIONS) == 69
    operation_uris: set[str] = set()
    for tool, name in OPERATIONS:
        input_uri = input_schema_uri(tool, name)
        operation_uris.add(input_uri)
        operation_uris.add(output_schema_uri(input_uri))
    assert len(operation_uris) == 138

    registered = set(schema_registry.registered_ids())
    resolved = operation_uris & registered
    assert resolved == ALIGNED_OPERATION_URIS
    assert {uri for uri in resolved if uri.endswith("/result/v1")} == set()

    # 4 个可解析的 URI 逐一对回数据侧端点 key（DOC 命名空间）
    for key in ("DOC.NEW", "DOC.OPEN", "DOC.SAVE", "DOC.CLOSE"):
        assert schema_id_for(key) in resolved

    # 其余 134 个 URI 指向 Core 自有的 `schemas/`（`docs/02` §22），本批不产出
    assert len(operation_uris - registered) == 134


def test_save_as_is_the_single_uri_shape_divergence(schema_registry: SchemaRegistry) -> None:
    """门槛 ③：`SAVE_AS` 是**唯一**形态差异（P07 保留下划线，数据侧 key 无分隔符）。"""
    assert input_schema_uri("engineering_doc", "SAVE_AS") == "structai://schema/doc/save_as/v1"
    assert schema_id_for("DOC.SAVEAS") == "structai://schema/doc/saveas/v1"
    assert not schema_registry.is_registered("structai://schema/doc/save_as/v1")
    assert schema_registry.is_registered("structai://schema/doc/saveas/v1")


def test_registered_schemas_are_never_rewritten(schema_registry: SchemaRegistry) -> None:
    """门槛 ③：登记内容只能是数据侧对象本身或其**唯一**内层对象（不改写任何取值）。"""
    checked = 0
    for relative in _relative_schema_files():
        document = _document(relative)
        content = document["schema"]
        if isinstance(content, str):  # 数据缺陷：非法 JSON 字符串（R19）
            continue
        candidates: list[Any] = [content]
        if isinstance(content, dict) and len(content) == 1:
            candidates.append(next(iter(content.values())))
        assert schema_registry.get(schema_id_for(document["key"])) in candidates, relative
        checked += 1
    assert checked == EXPECTED_REGISTERED


def test_envelope_root_keys_are_stripped_and_multi_root_documents_kept(
    schema_registry: SchemaRegistry,
) -> None:
    """门槛 ③：单根包装键被机械剥离；多根键文档**原样**登记（两种形态各举一例）。"""
    actl = _document("common/db/ACTL.json")
    assert list(actl["schema"]) == ["ACTL"]
    assert schema_registry.get(ACTL_ID) == actl["schema"]["ACTL"]

    steel = _document("products/gen_nx/post/STEELCODECHECK.json")
    assert list(steel["schema"]) == ["vSECT", "vELEM"]
    assert schema_registry.get(schema_id_for("POST.STEELCODECHECK")) == steel["schema"]


# ===== ④ JSON Schema 版本裁决（`docs/07` §16 R18）=====


def test_dialect_distribution_matches_the_measured_data(schema_registry: SchemaRegistry) -> None:
    """门槛 ④：440 个 draft-07 + 175 个未声明（+ 1 个无法装载）。"""
    report = schema_registry.report()
    assert report is not None
    assert dict(report.dialects) == {
        UNDECLARED_DIALECT: EXPECTED_UNDECLARED,
        DRAFT7_URI: EXPECTED_DRAFT7,
    }
    assert EXPECTED_DRAFT7 + EXPECTED_UNDECLARED == EXPECTED_REGISTERED
    assert DRAFT7_URI == "http://json-schema.org/draft-07/schema#"
    assert SCHEMA_2020_12_URI == "https://json-schema.org/draft/2020-12/schema"


def test_dialect_decision_selects_the_validator_per_schema() -> None:
    """门槛 ④（裁决）：声明 draft-07 → `Draft7Validator`；未声明 / 未知 → 项目标准 2020-12。"""

    assert DEFAULT_DIALECT == SCHEMA_2020_12_URI
    assert SUPPORTED_DIALECTS == {
        DRAFT7_URI: Draft7Validator,
        "https://json-schema.org/draft-07/schema": Draft7Validator,
    }

    assert dialect_of({"$schema": DRAFT7_URI}) == DRAFT7_URI
    assert validator_for({"$schema": DRAFT7_URI}) is Draft7Validator
    assert dialect_of({}) == DEFAULT_DIALECT
    assert validator_for({}) is Draft202012Validator

    # 未知方言（如 draft-04）**回落**到 2020-12，并如实报告生效方言
    unknown = {"$schema": "http://json-schema.org/draft-04/schema#"}
    assert dialect_of(unknown) == DEFAULT_DIALECT
    assert validator_for(unknown) is Draft202012Validator


def test_engine_reports_the_effective_dialect_per_schema(schema_engine: SchemaEngine) -> None:
    """门槛 ④：`SchemaEngine.dialect()` 如实返回生效方言（声明与未声明各一例）。"""
    assert schema_engine.dialect(ACTL_ID) == DRAFT7_URI
    assert schema_engine.dialect("structai://schema/design/src/aik-src2k/dco/v1") == DEFAULT_DIALECT


def test_draft7_semantics_are_not_silently_reinterpreted() -> None:
    """门槛 ④（裁决依据）：用错方言会**改变语义 / 直接报错** —— 必须按声明选校验器。

    证据：draft-07 的**数组形式** `items`（位置化校验）在 2020-12 里已由 `prefixItems`
    取代；同一份文档喂给 2020-12 校验器时 `iter_errors` 直接抛 `AttributeError`。
    """

    document = {"$schema": DRAFT7_URI, "type": "array", "items": [{"type": "string"}]}
    registry = SchemaRegistry()
    registry.register("structai://schema/probe/tuple-items/v1", document)
    engine = SchemaEngine(registry)

    engine.validate("structai://schema/probe/tuple-items/v1", ["ok"])
    with pytest.raises(StructAIError) as excinfo:
        engine.validate("structai://schema/probe/tuple-items/v1", [5])
    assert excinfo.value.code == "STRUCTAI-1100"

    with pytest.raises(AttributeError):
        list(Draft202012Validator(document).iter_errors([5]))


def test_undeclared_draft7_only_construct_fails_loudly_not_silently() -> None:
    """门槛 ④/⑤：方言不匹配时**不得**静默通过 —— 兜底为 `STRUCTAI-7000`（装配问题）。"""
    document = {"type": "array", "items": [{"type": "string"}]}  # 未声明方言 → 按 2020-12 校验
    registry = SchemaRegistry()
    registry.register("structai://schema/probe/undeclared/v1", document)
    engine = SchemaEngine(registry)

    with pytest.raises(InternalError) as excinfo:
        engine.validate("structai://schema/probe/undeclared/v1", [5])
    assert excinfo.value.code == "STRUCTAI-7000"
    assert excinfo.value.details["schema_id"] == "structai://schema/probe/undeclared/v1"
    assert excinfo.value.details["dialect"] == DEFAULT_DIALECT


def test_check_schema_flags_exactly_the_four_defective_schemas(
    schema_registry: SchemaRegistry,
    schema_engine: SchemaEngine,
) -> None:
    """门槛 ④（R19）：615 个已登记 Schema 中恰好 **4** 个不是合法 JSON Schema。"""
    failures: dict[str, str] = {}
    for schema_id in schema_registry.registered_ids():
        try:
            schema_engine.check_schema(schema_id)
        except InternalError as error:
            assert error.code == "STRUCTAI-7000"
            assert set(error.details) == {"schema_id", "dialect", "reason"}
            failures[schema_id] = error.details["reason"]

    assert set(failures) == DEFECTIVE_SCHEMA_IDS
    assert all(reason for reason in failures.values())
    assert len(schema_registry) - len(failures) == 611


# ===== ③/⑥ P07 固化的 URI 口径（落库侧）=====


async def test_p07_seed_fixes_the_operation_schema_uris(
    session_factory: SessionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ③/⑥：P07 落库的 `operations.input_schema` 正是本批对齐的 URI 口径。"""
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    await seed(session_factory)

    async with session_factory() as session:
        total = (await session.execute(select(func.count()).select_from(OperationORM))).scalar_one()
        assert total == 69
        row = (
            (await session.execute(select(OperationORM).where(OperationORM.name == "BUILD.COLUMN")))
            .scalars()
            .one()
        )
        assert row.input_schema == "structai://schema/build/column/v1"
        assert row.output_schema == "structai://schema/build/column/result/v1"
        assert row.input_schema == input_schema_uri(row.tool, row.name)
        assert row.output_schema == output_schema_uri(row.input_schema)


# ===== ⑤ 分层与边界（`docs/07` §14.1 / §2.2；`docs/02` §13 / §33）=====


def test_schema_engine_only_depends_on_domain_and_the_json_schema_library() -> None:
    """门槛 ⑤：Application 层**不**依赖 Infrastructure（`docs/07` §2.2 冻结方向）。"""
    validation_module = APP_DIR / "application" / "execution" / "validation.py"
    modules = _imported_modules(validation_module)
    assert {"app.domain.errors", "jsonschema"} <= modules
    assert [name for name in modules if name.startswith("app.infrastructure")] == []
    assert [
        name for name in modules if name.split(".")[0] in {"sqlalchemy", "fastapi", "mcp", "httpx"}
    ] == []

    offenders = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in (APP_DIR / "application").rglob("*.py")
        if [name for name in _imported_modules(path) if name.startswith("app.infrastructure")]
    )
    assert offenders == []


def test_schema_layer_keeps_engineering_semantics_out() -> None:
    """门槛 ⑤（P09）＋ P14 的落地：`SchemaEngine` 只做结构校验，工程语义在另一模块。

    ⚠️ P09 收尾时本用例断言「`engineering_validator.py` **不**存在」；P14–P18 已落地
    `EngineeringValidator`（`docs/07` §12 P14–P18），故该断言改为**分层分离**口径
    （`docs/02` §13 / §17 / §69：`Schema Validation` 先于 `Engineering Validation`，
    且工程语义**不得**塞回 Schema 层）—— 否则每批都要改上一批的测试文件。
    """
    execution_dir = APP_DIR / "application" / "execution"
    assert (execution_dir / "validation.py").is_file()

    source = (execution_dir / "validation.py").read_text(encoding="utf-8")
    assert "EngineeringValidationError" not in source
    # ⚠️ 只断言**实现**层面的分离：文档字符串里说明「工程语义归 EngineeringValidator」
    # 是允许的（那是分层说明），不得因此被判违规。
    schema_imports = _imported_modules(execution_dir / "validation.py")
    for leaked in ("engineering_validator", "preconditions", "postconditions"):
        assert not [name for name in schema_imports if name.endswith(leaked)], leaked


def test_container_shape_stays_frozen() -> None:
    """门槛 ⑤：容器字段仍为 `docs/02` §33 的冻结形状（P09 **不**加 schema 字段）。"""
    names = [field.name for field in dataclasses.fields(AppContainer)]
    assert names == [
        "settings",
        "runtime_config",
        "engine",
        "session_factory",
        "operation_registry",
        "execution_service",
        "started",
    ]
    assert [name for name in names if "schema" in name] == []


# ===== ⑥ 回归（`python -m app.main` / P04 / P02 / 既有 59 项 pytest）=====


def test_batch_id_is_a_batch_marker() -> None:
    """同步改动：`BATCH_ID` 始终形如 `P<两位数字>`（`docs/08` §3 的批次口径）。

    ⚠️ P10 收尾时把本断言从「等于 P09」改为与具体批次无关（与 P08 收尾时的做法一致），
    否则每批都要改上一批的测试文件。
    """
    assert re.fullmatch(r"P\d{2}", BATCH_ID)


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


def test_main_exits_zero_with_empty_stdout_on_an_unprovisioned_database(tmp_path: Path) -> None:
    """门槛 ⑥：未配备库 → 退出码 0、**stdout 0 字节**、Registry 留空但进程正常结束。"""
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p09_empty.db').as_posix()}"
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
    database_url = asyncio.run(_provision(tmp_path, monkeypatch, "p09_main_cli.db"))
    completed = _run_main(database_url)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert f"batch={BATCH_ID}" in completed.stderr
    assert "registry ready" in completed.stderr


async def test_p04_tables_and_select_one_are_not_regressed(engine: AsyncEngine) -> None:
    """门槛 ⑥（P04）：建表 **24** 张（与 24 个 ORM Model 一一对应）+ `SELECT 1` → 1。"""
    async with engine.connect() as connection:
        names = await connection.run_sync(
            lambda sync_connection: inspect(sync_connection).get_table_names()
        )
        assert len(names) == 24
        assert set(names) == set(Base.metadata.tables)
        assert (await connection.execute(select(1))).scalar_one() == 1


def test_p02_settings_override_is_not_regressed(monkeypatch: pytest.MonkeyPatch) -> None:
    """门槛 ⑥（P02）：环境变量能覆盖默认值（含 P08 新增的 `REGISTRY_ROOT`）。"""
    defaults = Settings()
    assert defaults.log_level == "INFO"
    assert defaults.database_url == "sqlite+aiosqlite:///./data/structai.db"
    assert defaults.registry_root == "./registry"

    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./data/p09.db")
    monkeypatch.setenv("REGISTRY_ROOT", "./registry")
    overridden = Settings()
    assert overridden.log_level == "DEBUG"
    assert overridden.database_url == "sqlite+aiosqlite:///./data/p09.db"
    assert overridden.registry_root == "./registry"


# ===== ⑦ 质量（依赖清单冻结；`ruff` / `mypy` 由验收命令覆盖）=====


def test_technology_stack_is_frozen() -> None:
    """门槛 ⑦：运行期依赖与 `docs/07` §3.1 / §3.2 一致（本批**不**引入新依赖）。"""
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    names = sorted(re.split(r"[\[<>=!~; ]", item, maxsplit=1)[0] for item in dependencies)
    assert tuple(names) == FROZEN_DEPENDENCIES
    assert any(item.startswith("jsonschema>=4.23") for item in dependencies)


# ===== ⑧ 红线（`docs/07` §11 / §14）=====


def test_twenty_code_contract_is_not_extended() -> None:
    """门槛 ⑧：20 码契约不扩（`SchemaValidationError` = `STRUCTAI-1100` 是既有码）。"""
    from app.domain import errors as errors_module

    assert len(TWENTY_CODE_CONTRACT) == 20
    assert errors_module.SchemaValidationError.code == "STRUCTAI-1100"
    assert errors_module.SchemaValidationError.error_type == "SCHEMA_VALIDATION_ERROR"
    assert errors_module.InternalError.code == "STRUCTAI-7000"

    derived = [
        name
        for name, value in vars(errors_module).items()
        if isinstance(value, type)
        and issubclass(value, StructAIError)
        and value is not StructAIError
    ]
    assert len(derived) == 20
    assert {
        value.code
        for value in vars(errors_module).values()
        if isinstance(value, type) and issubclass(value, StructAIError)
    } == set(TWENTY_CODE_CONTRACT)


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


def test_new_modules_never_commit_and_uow_is_the_only_committer() -> None:
    """门槛 ⑧：本批两个新模块不得 `commit` / `rollback`（边界归 `UnitOfWork`）。"""
    for relative in (
        "app/application/execution/validation.py",
        "app/infrastructure/registry/schema_registry.py",
    ):
        assert _commit_or_rollback_calls(REPO_ROOT / relative) == []

    committers = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in APP_DIR.rglob("*.py")
        if _commit_or_rollback_calls(path)
    )
    assert committers == ["app/infrastructure/database/unit_of_work.py"]
