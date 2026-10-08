"""P119–P123 验收：MIDAS 接入（Manifest / Registry 导入 / Transformer / 编排 / 护栏）。

权威来源
--------
- `docs/07` §12.2（P119–P126 任务卡）与 §12 P119–P123 的验收门槛。
- `docs/07` §6（Operation → MIDAS API 映射，**全章**）/ §7（Adapter 设计，**全章**）。
- `docs/04` §9–§18（Registry 数据模型）/ §19–§55（Transformer）/ §69–§72（Contract Test 分层）。
- `registry/README.md`（端点 / Schema 的**唯一**权威口径）。

⚠️ 规范原文副本一律写在**测试侧**（`tests/midas_p119_p126_support.py`），
不从被测模块导入 —— 这样「规范说 X」与「实现给出 X」是两个独立事实。
"""

from __future__ import annotations

import os
import subprocess  # noqa: S404 - 迁移判定需要子进程（与既有批次同口径）
import sys
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select

import midas_p119_p126_support as support
from app.domain.errors import InternalError, StructAIError
from app.infrastructure.adapters.base.manager import AdapterManager
from app.infrastructure.adapters.midas import install
from app.infrastructure.adapters.midas.client import (
    MAPI_KEY_HEADER,
    BuiltRequest,
    guard_destructive,
    guard_enabled,
    guard_shape,
    guard_solver,
    guard_verified,
)
from app.infrastructure.adapters.midas.errors import (
    MidasEndpointDisabled,
    MidasGlobalDeleteRejected,
    MidasResultShapeError,
    MidasSchemaShapeMismatch,
    MidasSolverUnsupported,
    MidasTransformerError,
    MidasValidationError,
    RegistryMappingNotVerified,
)
from app.infrastructure.adapters.midas.import_registry import (
    IMPORT_TABLES,
    MidasRegistryImporter,
    schema_uri_for,
)
from app.infrastructure.adapters.midas.models import MIDAS_TABLE_NAMES, MidasApiEndpointORM
from app.infrastructure.adapters.midas.operations import (
    NO_NATIVE_MAPPING,
    OPERATION_PLANS,
    plan_for,
    plans_for_tool,
    select_steps,
)
from app.infrastructure.adapters.midas.registry import (
    verification_status_for,
)
from app.infrastructure.adapters.midas.transforms import (
    TRANSFORMER_REGISTRY,
    AnalysisTransformer,
    BoundaryTransformer,
    DesignResultTransformer,
    DisplacementTransformer,
    ElementTransformer,
    LoadCaseTransformer,
    LoadTransformer,
    MaterialTransformer,
    NodeTransformer,
    ReactionTransformer,
    ResultRequestTransformer,
    SectionTransformer,
    ViewTransformer,
)

_NO_CONTEXT: Any = None
"""测试用的占位执行上下文：本批的 Adapter **不**读 `ExecutionContext`
（`docs/02` §5 的 `AdapterContext` 由 Core 构造，Adapter 侧只做转发）。"""

TEN_CATEGORIES: tuple[str, ...] = (
    "Node",
    "Element",
    "Material",
    "Section",
    "Boundary",
    "Load",
    "Analysis",
    "Result",
    "View",
    "Design",
)
"""`docs/07` §7.4 的**十类** Transformer（逐条照抄）。"""


# ===== P119：Manifest 与注册 =====


def test_p119_manifest_matches_docs_07_section_7_1() -> None:
    """门槛 ①（`docs/07` §7.1；`docs/04` §62）：Manifest 逐字段一致且通过既有校验。"""
    adapter = support.adapter()
    manifest = adapter.manifest.validate()
    assert manifest.name == support.MANIFEST_SPEC[0]
    assert manifest.vendor == support.MANIFEST_SPEC[1]
    assert manifest.product == support.MANIFEST_SPEC[2]
    assert manifest.supported_versions == support.SUPPORTED_VERSIONS_SPEC
    assert manifest.protocols == support.PROTOCOLS_SPEC
    assert manifest.capabilities == ()  # `docs/02` §22：静态清单留空
    assert adapter.adapter_key == ("MIDAS", "CIVIL NX")
    assert manifest.supports_version("2026") is True
    assert manifest.supports_version("2027") is False  # 严格精确，**不**回落


def test_p119_registers_into_the_existing_adapter_manager() -> None:
    """门槛 ①（`docs/07` §12 P119）：注册进既有 `AdapterManager`；重复注册 → 7000。"""
    manager = AdapterManager()
    manifest = install(manager)
    assert manager.registered_keys() == (("MIDAS", "CIVIL NX"),)
    assert manifest.vendor == "MIDAS" and manifest.product == "CIVIL NX"
    with pytest.raises(InternalError) as failure:
        install(manager)
    assert failure.value.code == "STRUCTAI-7000"
    assert failure.value.details["stage"] == "adapter_manager"
    assert failure.value.details["vendor"] == "MIDAS"


def test_p119_core_assembly_shape_and_tool_contract_are_unchanged() -> None:
    """门槛 ①（`docs/07` §12 P119 / §14.5）：容器仍 7 字段、9 Tool 契约不变。"""
    from app.container import BATCH_ID, AppContainer

    assert tuple(field for field in AppContainer.__dataclass_fields__) == (
        "settings",
        "runtime_config",
        "engine",
        "session_factory",
        "operation_registry",
        "execution_service",
        "started",
    )
    assert len(AppContainer.__dataclass_fields__) == 7
    assert BATCH_ID.startswith("P") and BATCH_ID[1:].isdigit()
    assert len(support.OPERATION_COUNTS_SPEC) == 9


def test_p119_vendor_names_stay_inside_the_sanctioned_package() -> None:
    """红线（`docs/07` §7.1 / §14.2）：`midas` 子包**之外**厂商名为 0 处。"""
    outside: list[str] = []
    for path in support.app_module_paths():
        lowered = path.read_text(encoding="utf-8").lower()
        for vendor in support.VENDOR_NAMES:
            if vendor.lower() in lowered:
                outside.append(f"{path.name}:{vendor}")
    assert outside == [], outside
    # 豁免区**必须**确实存在且确实含厂商名（证明豁免不是空豁免）
    inside = "\n".join(
        path.read_text(encoding="utf-8") for path in support.MIDAS_PACKAGE_DIR.glob("*.py")
    )
    assert "MIDAS" in inside


# ===== P120：Registry 导入 =====


async def _import_twice(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """跑两次导入，返回两次的报告（供幂等断言复用）。"""
    engine = support.engine_for(tmp_path)
    await support.midas_tables(engine)
    factory = support.session_factory_for(engine)
    importer = MidasRegistryImporter(support.registry())
    async with factory() as session:
        first = await importer.import_all(session)
        await session.commit()
    async with factory() as session:
        second = await importer.import_all(session)
        await session.commit()
    await engine.dispose()
    return first.as_dict(), second.as_dict()


async def test_p120_import_is_idempotent_and_covers_every_endpoint(tmp_path: Path) -> None:
    """门槛 ②（`docs/07` §12 P120 / §7.2）：636 端点逐条落库；连跑两次第二次 0 新增。"""
    first, second = await _import_twice(tmp_path)
    assert set(first["totals"]) == {
        name for name in IMPORT_TABLES if name != "midas_api_verifications"
    }
    assert second["inserted"] == {name: 0 for name in IMPORT_TABLES}

    engine = support.engine_for(tmp_path)
    factory = support.session_factory_for(engine)
    async with factory() as session:
        keys = await session.scalar(
            select(func.count(func.distinct(MidasApiEndpointORM.operation)))
        )
        assert keys == 636
        rows = (
            (
                await session.execute(
                    select(MidasApiEndpointORM).where(MidasApiEndpointORM.operation == "DB.NODE")
                )
            )
            .scalars()
            .all()
        )
    await engine.dispose()
    assert {(row.product, row.method) for row in rows} == {
        ("CIVIL_NX", "POST"),
        ("CIVIL_NX", "GET"),
        ("CIVIL_NX", "PUT"),
        ("CIVIL_NX", "DELETE"),
        ("GEN_NX", "POST"),
        ("GEN_NX", "GET"),
        ("GEN_NX", "PUT"),
        ("GEN_NX", "DELETE"),
        ("CIVIL_DESIGNER", "GET"),
    }
    for row in rows:
        assert row.path == "/DB/NODE"
        assert row.read_root == "NODE"
        assert row.verification_status == "VERIFIED"
        assert row.category == "DB"
        assert row.product_family in {"NX", "DESIGNER"}


def test_p120_availability_maps_to_verification_status_per_docs_07_section_7_2() -> None:
    """门槛 ②（`docs/07` §7.2）：映射规则逐条一致；`enabled=false` → `DEPRECATED`。"""
    for availability, expected in support.AVAILABILITY_TO_STATUS_SPEC:
        assert verification_status_for(availability=availability, enabled=True) == expected
    assert verification_status_for(availability="untested", enabled=False) == "DEPRECATED"
    registry = support.registry()
    assert registry.endpoint("DB.SWIND").verification_status == "DEPRECATED"
    assert registry.endpoint("DB.NODE").verification_status == "VERIFIED"
    assert registry.endpoint("DOC.NEW").verification_status == "PARTIAL"


async def test_p120_schema_is_registered_verbatim(tmp_path: Path) -> None:
    """门槛 ②（`docs/04` §107）：Schema **原样**登记，不改写任何取值。"""
    engine = support.engine_for(tmp_path)
    await support.midas_tables(engine)
    factory = support.session_factory_for(engine)
    async with factory() as session:
        report = await MidasRegistryImporter(support.registry()).import_all(session)
        await session.commit()
    await engine.dispose()
    # P137a 起两个方向各占一行；P138a 起请求方向 **616**（原 `DB.MBTP` 的坏串已从上游重建）；
    # P140 的 R5 补齐再 +4（手册 json_schema ×2 / 规格表 ×1 / 开发文档 ×1）
    # → 请求 **620** + 响应 **239** = **859**（逐条更新，**不**放宽）
    assert report.totals["midas_api_schemas"] == 620 + 239

    from app.infrastructure.adapters.midas.models import MidasApiSchemaORM

    engine = support.engine_for(tmp_path)
    factory = support.session_factory_for(engine)
    registry = support.registry()
    async with factory() as session:
        uri = schema_uri_for("DB.NODE", product="CIVIL NX")
        row = (
            (
                await session.execute(
                    select(MidasApiSchemaORM).where(MidasApiSchemaORM.schema_uri == uri)
                )
            )
            .scalars()
            .one()
        )
        response_uri = schema_uri_for("DB.NODE", product="CIVIL NX", direction="response")
        response_row = (
            (
                await session.execute(
                    select(MidasApiSchemaORM).where(MidasApiSchemaORM.schema_uri == response_uri)
                )
            )
            .scalars()
            .one()
        )
    await engine.dispose()
    assert uri == "midas://civil/db/node/request/v1"
    assert row.schema_json == registry.schema_json("DB.NODE")
    assert row.direction == "request"
    # P137a：响应方向是**另一行**（`/response/v1`），请求方向**一行未改**
    assert response_uri == "midas://civil/db/node/response/v1"
    assert response_row.direction == "response"
    assert response_row.schema_json == registry.response_schema_json("DB.NODE")
    assert response_row.id != row.id


def test_p120_every_schema_file_loads_after_the_p138a_and_p140_fixes() -> None:
    """`docs/07` §16 R19 / R5 收口：620 个文件**全部**可装载（P140 起；原 616 + R5 补齐 4 个）。"""
    registry = support.registry()
    keys = [key for key in registry.keys() if registry.schema_json(key) is not None]
    assert len(keys) == 620
    # P138a：坏串已按上游手册重建为**对象**（不再 `None`）
    assert registry.schema_json("DB.MBTP") == {
        "TABLE": {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "Argument": {
                "type": "object",
                "properties": {
                    "TYPE": {"description": "MemberType", "type": "string"},
                },
            },
        }
    }
    assert registry.endpoint("DB.MBTP").schema_path.endswith("MBTP.json")


def test_p120_alembic_migration_creates_exactly_the_seven_tables(tmp_path: Path) -> None:
    """门槛 ⑦（`docs/07` §12 P119）：7 张 MIDAS 表**只能**经 Alembic 迁移创建。"""
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    environment = dict(os.environ)
    environment["DATABASE_URL"] = database_url
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=support.REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        check=False,
        timeout=600,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    # Alembic 的日志走 stderr（`alembic.ini` 的 console handler 绑 `sys.stderr`）。
    assert completed.stderr.count("Running upgrade") == 1

    import sqlite3

    connection = sqlite3.connect(tmp_path / "migrated.db")
    tables = sorted(
        row[0] for row in connection.execute("select name from sqlite_master where type='table'")
    )
    columns = {
        name: [row[1] for row in connection.execute(f'pragma table_info("{name}")')]
        for name in tables
    }
    connection.close()
    assert tables == sorted([*MIDAS_TABLE_NAMES, "alembic_version"])
    for name in MIDAS_TABLE_NAMES:
        assert "id" in columns[name]
        assert "created_at" in columns[name]
    assert "read_root" in columns["midas_api_endpoints"]
    assert "table_type" in columns["midas_api_endpoints"]


# ===== P121：Transformer（`docs/07` §7.4 的十类）=====

CATEGORY_TRANSFORMERS: dict[str, tuple[str, ...]] = {
    "Node": ("midas.node.v1",),
    "Element": ("midas.elem.v1",),
    "Material": ("midas.matl.v1",),
    "Section": ("midas.sect.v1",),
    "Boundary": ("midas.cons.v1",),
    "Load": (
        "midas.load.v1",
        "midas.stld.v1",
        "midas.cnld.v1",
        "midas.bmld.v1",
        "midas.pres.v1",
        "midas.bodf.v1",
    ),
    "Analysis": ("midas.anal.v1",),
    "Result": (
        "midas.result.request.v1",
        "midas.result.displacement.v1",
        "midas.result.reaction.v1",
        "midas.result.element_force.v1",
        "midas.result.design.v1",
    ),
    "View": ("midas.view.capture.v1",),
    "Design": ("midas.design.steel.v1",),
}
"""`docs/07` §7.4 的十类 → 本批实现（数据库只存**名字**，`docs/04` §103）。"""


def test_p121_every_documented_category_has_a_transformer() -> None:
    """门槛 ③（`docs/07` §7.4）：十类逐类有实现，且名字都在 Transformer Registry 里。"""
    assert tuple(CATEGORY_TRANSFORMERS) == TEN_CATEGORIES
    for names in CATEGORY_TRANSFORMERS.values():
        for name in names:
            assert name in TRANSFORMER_REGISTRY, name


def test_p121_node_element_material_section_round_trip() -> None:
    """门槛 ③：模型域四类的 Canonical ↔ Native 双向逐条可判定。"""
    registry = support.registry()
    node = NodeTransformer(registry)
    assert node.to_native({"x": 0.0, "y": 1.0, "z": 2.0}) == {"X": 0.0, "Y": 1.0, "Z": 2.0}
    assert node.from_native({"X": 0.0, "Y": 1.0, "Z": 2.0}) == {"x": 0.0, "y": 1.0, "z": 2.0}
    assert node.from_native({}) == {"x": None, "y": None, "z": None}  # 缺值 → null，不虚构 0

    element = ElementTransformer(registry)
    native = element.to_native(
        {"type": "BEAM", "node_ids": [1, 2], "material_id": 1, "section_id": 1}
    )
    assert native == {"TYPE": "BEAM", "NODE": [1, 2], "MATL": 1, "SECT": 1}
    assert element.from_native(native)["type"] == "BEAM"

    material = MaterialTransformer(registry)
    body = material.to_native(
        {"name": "Q355B", "type": "STEEL", "elastic_modulus": 2.06e11, "poisson_ratio": 0.3}
    )
    assert body["NAME"] == "Q355B" and body["TYPE"] == "STEEL"
    assert body["PARAM"][0]["ELAST"] == 2.06e11
    assert body["PARAM"][0]["POISN"] == 0.3
    assert "DEN" not in body["PARAM"][0]  # 未给 → **不写**（不虚构 0）
    assert material.from_native(body)["elastic_modulus"] == 2.06e11

    section = SectionTransformer(registry)
    assert section.to_native({"name": "H400", "section_type": "DBUSER", "shape": "H"}) == {
        "SECT_NAME": "H400",
        "SECTTYPE": "DBUSER",
        "SECT_BEFORE": {"SHAPE": "H"},
    }


def test_p121_boundary_flags_become_the_documented_constraint_string() -> None:
    """门槛 ③（`docs/04` §31）：`(DX,DY,DZ,RX,RY,RZ)` → `CONSTRAINT` 字符串并原样回读。"""
    boundary = BoundaryTransformer(support.registry())
    native = boundary.to_native(
        {"node_id": 1, "ux": True, "uy": True, "uz": True, "rx": False, "ry": False, "rz": False}
    )
    assert native == {"ID": 1, "CONSTRAINT": "111000"}
    canonical = boundary.from_native({"ID": 1, "CONSTRAINT": "111000"})
    assert (canonical["ux"], canonical["uy"], canonical["uz"]) == (True, True, True)
    assert (canonical["rx"], canonical["ry"], canonical["rz"]) == (False, False, False)
    assert canonical["node_id"] == 1


def test_p121_load_dispatch_and_analysis_view_design_round_trip() -> None:
    """门槛 ③（`docs/04` §32–§34 / §35 / §48 / §52）：荷载分派与其余四类。"""
    registry = support.registry()
    loads = LoadTransformer(registry)
    assert loads.to_native({"load_type": "NODE_FORCE", "load_case": "AXIAL", "fz": -500_000.0}) == {
        "LCNAME": "AXIAL",
        "FZ": -500_000.0,
    }
    assert loads.to_native(
        {"load_type": "SELF_WEIGHT", "load_case": "SW", "factors": [0.0, 0.0, -1.0]}
    ) == {"LCNAME": "SW", "FV": [0.0, 0.0, -1.0]}
    assert loads.to_native({"load_type": "PRESSURE", "load_case": "P1"})["LCNAME"] == "P1"
    assert LoadCaseTransformer(registry).to_native({"name": "AXIAL", "type": "USER"}) == {
        "NAME": "AXIAL",
        "TYPE": "USER",
    }
    assert AnalysisTransformer(registry).to_native({"analysis_type": "STATIC"}) == {
        "TYPE": "STATIC"
    }
    assert ViewTransformer(registry).to_native({"figure_name": "F1", "width": 1200}) == {
        "FIGURE_NAME": "F1",
        "WIDTH": 1200,
    }
    from app.infrastructure.adapters.midas.transforms import DesignTransformer

    assert DesignTransformer(registry).to_native({"perform_type": "DESIGN"}) == {
        "PERFORM_TYPE": "DESIGN"
    }


def test_p121_result_request_and_result_parsing() -> None:
    """门槛 ③（`docs/04` §42–§47）：结果请求只写 Schema 允许的字段；解析带显式单位。"""
    registry = support.registry()
    request = ResultRequestTransformer(registry).to_native(
        {"table_type": "DISPLACEMENTG", "load_cases": ["AXIAL"]}
    )
    assert request == {"TABLE_TYPE": "DISPLACEMENTG", "LOAD_CASE_NAMES": ["AXIAL"]}

    parsed = DisplacementTransformer().parse(support.displacement_table())
    assert parsed["table_type"] == "DISPLACEMENTG"
    assert parsed["units"] == {"FORCE": "N", "DIST": "m"}
    row = parsed["rows"][0]
    assert row["node_id"] == "2" and row["load_case"] == "AXIAL"
    assert row["uz"] == pytest.approx(support.DISPLACEMENT_UZ_M)
    assert row["stage"] is None and row["step"] is None  # 原生缺列 → None，**不**虚构

    reaction = ReactionTransformer().parse(support.displacement_table())
    assert reaction["rows"][0]["fx"] is None  # 列名不匹配 → None（**不**错位取值）

    design = DesignResultTransformer().parse(support.design_table())
    assert design["rows"][0]["ratio"] == pytest.approx(support.DESIGN_RATIO)
    assert design["rows"][0]["status"] == "PASS"
    assert design["rows"][0]["code"] == "CODE-X"  # 占位原样透传（`docs/04` §54）


def test_p121_invalid_inputs_fail_loudly_instead_of_inventing() -> None:
    """门槛 ③（`docs/07` §7.4 的硬约束）：未映射 / 未登记 / 形态不符 → 明确错误。"""
    registry = support.registry()
    with pytest.raises(MidasTransformerError):
        NodeTransformer(registry).to_native({"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0})
    with pytest.raises(MidasValidationError):
        NodeTransformer(registry).to_native({"x": 0.0})
    with pytest.raises(MidasValidationError) as material_failure:
        MaterialTransformer(registry).to_native(
            {"name": "M", "type": "STEEL", "elastic_modulus": -1.0}
        )
    assert material_failure.value.details["reason"] == "material_elastic_modulus_not_positive"
    with pytest.raises(MidasValidationError) as load_failure:
        LoadTransformer(registry).to_native({"load_type": "TEMPERATURE", "load_case": "T"})
    assert load_failure.value.details["reason"] == "load_type_not_mapped"
    with pytest.raises(MidasResultShapeError):
        DisplacementTransformer().parse({"X": {"HEAD": ["Node", "DX"], "DATA": [["1"]]}})
    with pytest.raises(MidasValidationError):
        BoundaryTransformer(registry).to_native({"node_id": 1, "ux": True})


# ===== P122：Operation → endpoint 编排（`docs/07` §6）=====


def test_p122_operation_counts_match_docs_07_section_5_1() -> None:
    """门槛 ③（`docs/07` §5.1 / §6.10）：9 Tool / **69** Operation 逐 Tool 计数一致。"""
    assert len(OPERATION_PLANS) == 69
    for tool, expected in support.OPERATION_COUNTS_SPEC:
        assert len(plans_for_tool(tool)) == expected, tool


def test_p122_every_step_matches_the_registry() -> None:
    """门槛 ③（`docs/07` §6.11）：每一步的 key / 方法 / 路径都取自 Registry，**不**臆造。

    ⚠️ 产品可得性按**数据**判定：`docs/07` §6 的映射表没有逐端点标注产品，
    实测有 **3** 处只在单一产品上可得（见 `test_p122_product_availability_gaps_are_data_facts`）。
    故这里的判据是「至少对一个声明产品可得」，而不是「两个产品都可得」。
    """
    registry = support.registry()
    problems: list[str] = []
    for plan in OPERATION_PLANS.values():
        routes = list(plan.routes.values()) or [plan.steps]
        for steps in routes:
            for step in steps:
                if not registry.has(step.key):
                    problems.append(f"{plan.operation}:{step.key}")
                    continue
                definition = registry.endpoint(step.key)
                available = [
                    product
                    for product in ("CIVIL_NX", "GEN_NX")
                    if product in definition.products or product in definition.overrides
                ]
                if not available:
                    problems.append(f"{plan.operation}:{step.key}:no-product")
                    continue
                for product in available:
                    resolved = registry.resolve(key=step.key, product=product)
                    if resolved.uri != definition.uri and step.method not in definition.methods:
                        problems.append(f"{plan.operation}:{step.key}:{product}:method")
                for alternative in step.alternatives:
                    if not registry.has(alternative):
                        problems.append(f"{plan.operation}:alt:{alternative}")
                if step.transformer and step.transformer not in TRANSFORMER_REGISTRY:
                    problems.append(f"{plan.operation}:transformer:{step.transformer}")
    assert problems == [], problems


def test_p122_product_availability_gaps_are_data_facts() -> None:
    """把实测的**产品可得性差异**钉成事实（`docs/07` §6 的映射未逐端点标注产品）。"""
    registry = support.registry()
    assert "GEN_NX" not in registry.endpoint("POST.TABLE").products
    assert registry.endpoint("POST.STEELCODECHECK").products == ("GEN_NX",)
    assert registry.endpoint("DB.POSL").products == ("GEN_NX",)
    assert registry.has("DB.THOO") is False  # `docs/07` §6.9 提到，但数据里没有


def test_p122_unmapped_and_no_native_mapping_operations_fail_loudly() -> None:
    """门槛 ③（`docs/07` §6.8 / §12 P122）：未映射 / 未实现 → 明确错误，**不**回落。"""
    from app.infrastructure.adapters.midas.errors import MidasCapabilityError

    with pytest.raises(MidasCapabilityError) as unmapped:
        plan_for("MODEL.NOPE")
    assert unmapped.value.details["reason"] == "operation_not_mapped"
    for operation in NO_NATIVE_MAPPING:
        with pytest.raises(MidasCapabilityError) as native:
            plan_for(operation)
        assert native.value.details["reason"] == "operation_has_no_native_mapping"
    assert NO_NATIVE_MAPPING == ("DESIGN.FOUNDATION", "DESIGN.OPTIMIZE")


def test_p122_composite_plans_follow_docs_07_section_6_5() -> None:
    """门槛 ③（`docs/07` §6.5 / §16 R2）：组合 Operation 多步编排，**不**臆造单端点。"""
    column = plan_for("BUILD.COLUMN")
    assert column.composite is True
    assert [step.key for step in column.steps] == ["DB.NODE", "DB.ELEM", "DB.MATL", "DB.SECT"]
    assert {step.method for step in column.steps} == {"POST"}
    assert [step.key for step in plan_for("BUILD.STEEL_FRAME").steps][-1] == "DB.CONS"
    assert [step.key for step in plan_for("MODEL.GENERATE_GRID").steps] == ["DB.NODE"]
    move = plan_for("MODEL.MOVE")
    assert move.steps[0].method == "PUT"  # 改坐标
    assert move.steps[1].key == "DB.ELEM"
    assert all(
        plan.composite
        for plan in (
            plan_for(name)
            for name in ("BUILD.FRAME", "MODEL.COPY", "MODEL.MIRROR", "MODEL.PATTERN")
        )
    )


def test_p122_result_plans_keep_the_documented_alternatives() -> None:
    """门槛 ③（`docs/07` §6.7）：主端点 + 备选端点逐条保留。"""
    displacement = plan_for("RESULT.NODE.DISPLACEMENT").steps[0]
    assert displacement.key == "POST.TABLE.DISPLACEMENTG"
    assert displacement.method == "POST"
    assert displacement.alternatives == ("POST.TABLE.DISPLACEMENTL",)
    reaction = plan_for("RESULT.NODE.REACTION").steps[0]
    assert reaction.alternatives == (
        "POST.TABLE.REACTIONL",
        "POST.TABLE.REACTIONLSURFACESPRING",
    )
    summary = plan_for("RESULT.ANALYSIS.SUMMARY").steps[0]
    assert summary.key == "POST.TABLE" and summary.note.startswith("docs/07 §6.7")


def test_p122_load_and_code_check_routing() -> None:
    """门槛 ③（`docs/07` §6.3 / §6.8）：荷载按类型分派；校核按「材料 × 构件」路由。"""
    assert [step.key for step in select_steps("MODEL.LOAD.ASSIGN", {"load_type": "PRESSURE"})] == [
        "DB.PRES"
    ]
    assert [
        step.key for step in select_steps("MODEL.LOAD.ASSIGN", {"load_type": "SELF_WEIGHT"})
    ] == ["DB.BODF"]
    concrete = select_steps("DESIGN.CODE_CHECK", {"material": "concrete", "member_type": "bd"})
    assert [step.key for step in concrete] == [
        "DESIGN.RC.KDS-41-20-2022.BD-ANAL",
        "DESIGN.RC.KDS-41-20-2022.BD-TABLE",
    ]
    steel = select_steps("DESIGN.CODE_CHECK", {"material": "steel"})
    assert [step.key for step in steel][-1] == "POST.STEELCODECHECK"
    from app.infrastructure.adapters.midas.errors import MidasCapabilityError

    with pytest.raises(MidasCapabilityError) as unroutable:
        select_steps("DESIGN.CODE_CHECK", {"material": "timber"})
    assert unroutable.value.details["reason"] == "code_check_route_not_mapped"


# ===== P123：破坏性护栏与求解器门控（`docs/07` §7.3 / §7.6）=====


def _resolved(key: str, *, product: str = "CIVIL_NX", method: str | None = None) -> Any:
    """解析一个端点（测试辅助）。"""
    return support.registry().resolve(key=key, product=product, method=method)


def test_p123_destructive_guards_reject_before_any_request() -> None:
    """门槛 ④（`docs/07` §7.6）：全表删除形态**发请求前**拒绝（`STRUCTAI-1200`）。"""
    nx_delete = _resolved("DB.NODE", method="DELETE")
    with pytest.raises(MidasGlobalDeleteRejected) as missing_key:
        guard_destructive(nx_delete, method="DELETE", item_ids=(), payload=None)
    assert missing_key.value.details["guard"] == "nx_delete_requires_path_key"
    assert missing_key.value.code == "STRUCTAI-1200"
    guard_destructive(nx_delete, method="DELETE", item_ids=("1", "2"), payload=None)

    designer = _resolved("DB.MEMB", product="CIVIL_DESIGNER", method="DELETE")
    assert designer.delete_all_via_body is True
    with pytest.raises(MidasGlobalDeleteRejected) as empty_body:
        guard_destructive(designer, method="DELETE", item_ids=("1",), payload=None)
    assert empty_body.value.details["guard"] == "designer_delete_all_via_body"
    with pytest.raises(MidasGlobalDeleteRejected):
        guard_destructive(designer, method="DELETE", item_ids=("1",), payload={"Type": 0})
    guard_destructive(designer, method="DELETE", item_ids=("1",), payload={"Type": 1})


def test_p123_solver_gate_and_disabled_endpoint() -> None:
    """门槛 ④（`docs/07` §7.3 / §7.6）：求解器门控与 `enabled=false` 一律拒绝。"""
    registry = support.registry()
    hyper = next(key for key in registry.keys() if registry.endpoint(key).solver == "HYPER_S")
    resolved = registry.resolve(key=hyper, product="GEN_NX")
    with pytest.raises(MidasSolverUnsupported) as solver:
        guard_solver(resolved, "")
    assert solver.value.code == "STRUCTAI-3000"
    assert solver.value.details["required_solver"] == "HYPER_S"
    guard_solver(resolved, "HYPER_S")

    disabled = registry.resolve(key="DB.SWIND", product="GEN_NX")
    with pytest.raises(MidasEndpointDisabled) as endpoint:
        guard_enabled(disabled)
    assert endpoint.value.code == "STRUCTAI-3000"


def test_p123_unverified_endpoint_is_refused_unless_contract_mode() -> None:
    """门槛 ④（`docs/04` §130 / `docs/07` §7.2）：`!= VERIFIED` → 拒绝（除 Contract 模式）。"""
    partial = _resolved("DOC.NEW", method="POST")
    assert partial.verification_status == "PARTIAL"
    with pytest.raises(RegistryMappingNotVerified) as refused:
        guard_verified(partial, operation="NEW", allow_unverified=False)
    assert refused.value.code == "STRUCTAI-3000"
    assert refused.value.details["verification_status"] == "PARTIAL"
    guard_verified(partial, operation="NEW", allow_unverified=True)


def test_p123_request_shape_guards() -> None:
    """门槛 ④（`docs/07` §7.3 第 4 步）：数组 / 对象形态不符 → `STRUCTAI-1200`。"""
    designer_array = _resolved("DB.MEMB", product="CIVIL_DESIGNER", method="POST")
    with pytest.raises(MidasSchemaShapeMismatch):
        guard_shape(designer_array, {"NAME": "x"})
    guard_shape(designer_array, [{"NAME": "x"}])


async def test_p123_guards_run_before_the_transport_is_touched() -> None:
    """门槛 ④：护栏在**发请求前**求值 —— 拒绝时传输层**零**调用。"""
    transport = support.RecordingTransport()
    adapter = support.adapter(transport=transport)
    await adapter.connect(support.connect_config())
    transport.clear()
    with pytest.raises(StructAIError) as failure:
        await adapter.execute_normalized("MODEL.NODE.DELETE", {}, _NO_CONTEXT)
    assert failure.value.code == "STRUCTAI-1200"
    assert transport.calls == []
    await adapter.disconnect()


async def test_p123_requests_follow_the_registry_wrapper_and_path_key() -> None:
    """门槛 ④（`docs/07` §7.3）：`Assign` / `Argument` 包装与 `DELETE {uri}/{id}` 路径 key。"""
    transport = support.RecordingTransport()
    adapter = support.adapter(transport=transport)
    await adapter.connect(support.connect_config())

    await adapter.execute_normalized(
        "MODEL.NODE.CREATE", {"nodes": [{"id": 7, "x": 1.0, "y": 2.0, "z": 3.0}]}, _NO_CONTEXT
    )
    method, path, body = transport.calls[-1]
    assert (method, path) == ("POST", "/DB/NODE")
    assert body == {"Assign": {"7": {"X": 1.0, "Y": 2.0, "Z": 3.0}}}

    transport.clear()
    await adapter.execute_normalized("MODEL.NODE.DELETE", {"item_ids": [1, 2]}, _NO_CONTEXT)
    assert transport.calls[-1][:2] == ("DELETE", "/DB/NODE/1,2")

    transport.clear()
    await adapter.execute_normalized("NEW", {"arguments": {}}, _NO_CONTEXT)
    assert transport.calls[-1][2] == {"Argument": {}}  # `DOC.NEW` 的 Schema 包装键

    await adapter.disconnect()
    assert adapter.state.value == "DISCONNECTED"


def test_p123_client_keeps_the_key_in_the_header_only() -> None:
    """红线（`docs/04` §6 / `docs/07` §14.3）：MAPI-Key 只进请求头，**不**进 URL。"""
    request = BuiltRequest(
        operation="MODEL.NODE.QUERY",
        endpoint="DB.NODE",
        product="CIVIL_NX",
        method="GET",
        uri="/DB/NODE",
        body=None,
        wrapper="none",
        table_type="",
        budget_seconds=30.0,
    )
    assert support.SECRET not in request.uri
    assert support.SECRET not in repr(request)
    assert MAPI_KEY_HEADER == "MAPI-Key"
