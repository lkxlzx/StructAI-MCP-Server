"""P137 验收：response 方向 Schema 落库收口（P137a）+ 7 项 AND 如实报告（P137b）+ 真实 L5
写路径（P137c）。

权威来源
--------
- `docs/07` §16 **R87**（response 方向 Schema）· **R78**（7 项 AND 与 CI 层记录不得升级状态）·
  **R4 / R14**（写路径实测覆盖）· `docs/04` §8（`VERIFIED` 的 7 项 AND）· §71 / §72（L4 / L5
  分层）。
- `registry/README.md` §2.2（同一份 Schema 文件里的 `response` 块）· §4（`availability` 口径）。
- `docs/04` §12（`midas_api_schemas`）· §17（`midas_api_mappings` 的 `request_schema` /
  `response_schema`）。

落地裁决（本文件的硬事实，不美化）
--------------------------------
1. **两个方向都落库**：`midas_api_schemas` 按 `schema_uri` 各占一行 —— 请求方向 **615** 行
   （`DB.MBTP` 的 `schema` 是非法 JSON 字符串，R19）、响应方向 **239** 行
   （`availability = verified` + `GET` + 有 Schema 文件，`registry/tools/sync_response_schemas.py`
   的判定），合计 **854** 行；响应方向的 URI = `midas://<product>/<code>/response/v1`。
2. **回填**：`midas_api_endpoints.response_schema_id` 与 `midas_api_mappings.response_schema`
   指向**响应方向**的 Schema 行 id（与 `request_schema*` 同口径）；未声明 `response` 块的端点
   仍为 `None`（**不**臆造）。
3. **7 项 AND 只做如实报告**：`ImportReport.seven_and` 汇总**同一判定点**
   （`live.py` 的 `registry_evidence` / `seven_and_verdict`）；端点行的 `verification_status`
   **仍**只由 `availability` 机械映射 —— CI 层（L1–L3）记录与写入前后**均不**改状态。
4. **真实 L5 只在专用测试项目上执行**：缺 `MIDAS_LIVE_L4` / `MIDAS_LIVE_PROJECT` 等声明 →
   用例 `pytest.skip`（**不**失败、**不**伪造）；探针在缺声明时 `STRUCTAI-3000` + **零** transport
   调用。
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import midas_p119_p126_support as support
from app.infrastructure.adapters.midas.client import (
    MidasEnvironmentCredential,
    MidasHttpClient,
)
from app.infrastructure.adapters.midas.import_registry import (
    REQUEST_DIRECTION,
    RESPONSE_DIRECTION,
    RESPONSE_SCHEMA_URI_TEMPLATE,
    VERSION_RANGE,
    MidasRegistryImporter,
    schema_uri_for,
    seven_and_report,
)
from app.infrastructure.adapters.midas.live import (
    LIVE_PROJECT_ENV,
    MIDAS_LIVE_ENV,
    PROBE_PASSED,
    SEVEN_AND_ITEMS,
    STATUS_PARTIAL,
    STATUS_VERIFIED,
    dedicated_test_project_from_env,
    live_opt_in_from_env,
    registry_evidence,
    seven_and_verdict,
)
from app.infrastructure.adapters.midas.models import (
    MidasApiEndpointORM,
    MidasApiMappingORM,
    MidasApiSchemaORM,
    MidasApiSourceORM,
    MidasApiVerificationORM,
)
from app.infrastructure.adapters.midas.registry import MidasRegistry
from app.infrastructure.adapters.midas.write_probe import MidasLiveWriteProbe
from app.infrastructure.database.base import utcnow

IMPORT_REGISTRY_PATH = Path("app/infrastructure/adapters/midas/import_registry.py")
"""P137a / P137b 的实现落点（唯一）。"""

REQUEST_SCHEMA_ROWS = 615
"""请求方向 Schema 行数（616 个文件里 `DB.MBTP` 无法装载，R19）。"""

RESPONSE_SCHEMA_ROWS = 239
"""响应方向 Schema 行数 = 已实测端点（`availability = verified` + `GET` + 有 Schema 文件）。"""

TOTAL_SCHEMA_ROWS = REQUEST_SCHEMA_ROWS + RESPONSE_SCHEMA_ROWS
"""两个方向合计 **854** 行（P137a 之前的断言值 615 只覆盖请求方向）。"""

SOURCE_ROWS = 11
"""`midas_api_sources` 行数（8 个 provenance 标题 ∪ 7 个 Schema `source`，含
`l4_measured_envelope`；P137a 起响应方向 Schema 也挂到自己的来源行）。"""

MEASURED_ENVELOPE_SOURCE = "l4_measured_envelope"
"""响应方向 Schema 的 `source`（`registry/tools/sync_response_schemas.py`）。"""

NODE_KEY = "DB.NODE"
"""覆盖两个信封的样例端点（NX 系 `NODE` + Designer `result.return_value`）。"""

DESIGNER_ONLY_KEY = "DOC.UNIT"
"""只有 Designer 单信封链的样例端点（`registry/README.md` §2.2）。"""

UNCOVERED_KEYS = ("DB.SWIND", "OPE.PROJECTSTATUS", "DOC.NEW")
"""无 `response` 块的端点（未实测 / 无 Schema / 已禁用）—— 必须如实留 `None`。"""

LIVE_BASE_ENV = "MIDAS_BASE_URL"
LIVE_KEY_ENV = "MIDAS_MAPI_KEY"
LIVE_PRODUCT = "GEN_NX"
"""真实 L5 的实例口径（`docs/04` §72：专用实例 / 专用 Key / 专用项目 / 专用测试模型）。"""


# ===== 装配辅助 =====


async def _import(tmp_path: Path, times: int = 1) -> tuple[AsyncEngine, Any, Any]:
    """建临时库 → 导入 `times` 次 → 返回 `(engine, 末次报告, session factory)`。"""
    engine = support.engine_for(tmp_path)
    await support.midas_tables(engine)
    factory = support.session_factory_for(engine)
    importer = MidasRegistryImporter(support.registry())
    report: Any = None
    for _ in range(times):
        async with factory() as session:
            report = await importer.import_all(session)
            await session.commit()
    return engine, report, factory


async def _schema_rows(
    factory: async_sessionmaker[AsyncSession], *, direction: str
) -> tuple[MidasApiSchemaORM, ...]:
    """按方向取全部 Schema 行（顺序 = `schema_uri`）。"""
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    select(MidasApiSchemaORM)
                    .where(MidasApiSchemaORM.direction == direction)
                    .order_by(MidasApiSchemaORM.schema_uri)
                )
            )
            .scalars()
            .all()
        )
    return tuple(rows)


async def _direction_counts(factory: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    """按方向统计 Schema 行数（幂等证据）。"""
    async with factory() as session:
        rows = await session.execute(
            select(MidasApiSchemaORM.direction, func.count()).group_by(MidasApiSchemaORM.direction)
        )
    return {str(direction): int(count) for direction, count in rows}


def _covered_keys(registry: MidasRegistry) -> tuple[str, ...]:
    """数据里声明了 `response` 块的端点 key（`registry/` 是唯一权威）。"""
    return tuple(
        key for key in registry.keys() if registry.response_schema_document(key) is not None
    )


def _imported_modules(path: Path) -> set[str]:
    """模块级 import 的模块名集合（AST 扫描）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


# ===== P137a：response 方向 Schema 落库 =====


async def test_p137a_schemas_are_imported_in_both_directions(tmp_path: Path) -> None:
    """P137a：请求 **615** + 响应 **239** = **854** 行，响应方向有自己的 URI（不新增文件）。"""
    engine, report, factory = await _import(tmp_path)
    assert report.totals["midas_api_schemas"] == TOTAL_SCHEMA_ROWS
    request_rows = await _schema_rows(factory, direction=REQUEST_DIRECTION)
    response_rows = await _schema_rows(factory, direction=RESPONSE_DIRECTION)
    await engine.dispose()
    assert len(request_rows) == REQUEST_SCHEMA_ROWS
    assert len(response_rows) == RESPONSE_SCHEMA_ROWS

    registry = support.registry()
    covered = set(_covered_keys(registry))
    assert {row.schema_uri for row in response_rows} == {
        schema_uri_for(key, product="CIVIL NX", direction=RESPONSE_DIRECTION) for key in covered
    }
    for row in response_rows:
        assert row.schema_uri.endswith("/response/v1"), row.schema_uri
        assert row.schema_uri.startswith("midas://civil/"), row.schema_uri
        assert row.product == "CIVIL NX" and row.version_range == VERSION_RANGE
    # 响应方向的本体 = 数据侧 `response.schema` **原样**（不改写任何取值）
    by_uri = {row.schema_uri: row for row in response_rows}
    for key in (NODE_KEY, DESIGNER_ONLY_KEY):
        row = by_uri[schema_uri_for(key, product="CIVIL NX", direction=RESPONSE_DIRECTION)]
        assert row.schema_json == registry.response_schema_json(key), key
    node_schema = by_uri[
        schema_uri_for(NODE_KEY, product="CIVIL NX", direction=RESPONSE_DIRECTION)
    ].schema_json
    assert node_schema["type"] == "object" and node_schema["oneOf"], "多信封 → `oneOf` 原样保留"
    # 请求方向**一行未改**（含 `DB.MBTP` 仍无法装载 → 没有请求方向行）
    request_by_uri = {row.schema_uri: row for row in request_rows}
    assert request_by_uri[
        schema_uri_for(NODE_KEY, product="CIVIL NX")
    ].schema_json == registry.schema_json(NODE_KEY)
    assert schema_uri_for("DB.MBTP", product="CIVIL NX") not in request_by_uri
    # `DB.MBTP` 的 `response` 块是**合法对象** → 如实登记（R19 只影响请求方向）
    assert schema_uri_for("DB.MBTP", product="CIVIL NX", direction=RESPONSE_DIRECTION) in by_uri


async def test_p137a_endpoints_and_mappings_backfill_the_response_schema_id(
    tmp_path: Path,
) -> None:
    """P137a：`response_schema_id` / `response_schema` 回填**响应方向**行 id；未覆盖仍 `None`。"""
    engine, _, factory = await _import(tmp_path)
    registry = support.registry()
    covered = set(_covered_keys(registry))
    response_by_uri = {
        row.schema_uri: row for row in await _schema_rows(factory, direction=RESPONSE_DIRECTION)
    }
    async with factory() as session:
        endpoints = (await session.execute(select(MidasApiEndpointORM))).scalars().all()
        mappings = (await session.execute(select(MidasApiMappingORM))).scalars().all()
        covered_endpoint_rows = await session.scalar(
            select(func.count())
            .select_from(MidasApiEndpointORM)
            .where(MidasApiEndpointORM.operation.in_(covered))
        )
        covered_mapping_rows = await session.scalar(
            select(func.count())
            .select_from(MidasApiMappingORM)
            .where(MidasApiMappingORM.endpoint_key.in_(covered))
        )
    await engine.dispose()

    filled = [row for row in endpoints if row.response_schema_id is not None]
    assert len(filled) == covered_endpoint_rows, "只**有** response 块的端点行才回填"
    for row in filled:
        assert row.operation in covered, row.operation
        uri = schema_uri_for(str(row.operation), product="CIVIL NX", direction=RESPONSE_DIRECTION)
        assert response_by_uri[uri].direction == RESPONSE_DIRECTION
        assert str(row.response_schema_id) == str(response_by_uri[uri].id)
        # 请求方向与响应方向指向**不同**的行（不得互相覆盖）
        assert row.request_schema_id != row.response_schema_id
    for row in endpoints:
        if row.operation in UNCOVERED_KEYS:
            assert row.response_schema_id is None, row.operation

    filled_mappings = [row for row in mappings if row.response_schema is not None]
    assert len(filled_mappings) == covered_mapping_rows
    for row in filled_mappings:
        assert row.endpoint_key in covered, row.endpoint_key
        uri = schema_uri_for(
            str(row.endpoint_key), product="CIVIL NX", direction=RESPONSE_DIRECTION
        )
        assert str(row.response_schema) == str(response_by_uri[uri].id)
    for row in mappings:
        if row.endpoint_key in UNCOVERED_KEYS:
            assert row.response_schema is None, row.endpoint_key


async def test_p137a_response_schema_rows_are_linked_to_their_own_source(tmp_path: Path) -> None:
    """P137a：响应方向 Schema 挂到 `l4_measured_envelope` 来源行；来源总数 **11**。"""
    engine, report, factory = await _import(tmp_path)
    assert report.totals["midas_api_sources"] == SOURCE_ROWS
    async with factory() as session:
        sources = (await session.execute(select(MidasApiSourceORM))).scalars().all()
        rows = (
            (
                await session.execute(
                    select(MidasApiSchemaORM).where(
                        MidasApiSchemaORM.direction == RESPONSE_DIRECTION
                    )
                )
            )
            .scalars()
            .all()
        )
    await engine.dispose()
    by_title = {str(row.source_title): row for row in sources}
    measured = by_title[MEASURED_ENVELOPE_SOURCE]
    assert measured.category == "schema"
    assert all(str(row.source_id) == str(measured.id) for row in rows)
    assert {str(row.source_title) for row in sources} >= {
        MEASURED_ENVELOPE_SOURCE,
        "repo_midas_api",
    }


async def test_p137a_import_is_idempotent_in_both_directions(tmp_path: Path) -> None:
    """P137a：连跑两次第二次 `inserted` 全 0，且两个方向的行数**逐条不变**。"""
    engine, first, factory = await _import(tmp_path, times=1)
    counts_before = await _direction_counts(factory)
    await engine.dispose()
    engine2, second, factory2 = await _import(tmp_path, times=1)
    counts_after = await _direction_counts(factory2)
    await engine2.dispose()
    assert first.totals["midas_api_schemas"] == TOTAL_SCHEMA_ROWS
    assert second.inserted == {name: 0 for name in second.inserted}
    assert second.totals["midas_api_schemas"] == TOTAL_SCHEMA_ROWS
    assert counts_after == counts_before
    assert counts_before[REQUEST_DIRECTION] == REQUEST_SCHEMA_ROWS
    assert counts_before[RESPONSE_DIRECTION] == RESPONSE_SCHEMA_ROWS


def test_p137a_schema_uri_for_rejects_an_unknown_direction() -> None:
    """P137a：方向模板**唯一**取值点；未知方向**明确失败**（不回落请求方向）。"""
    registry = support.registry()
    assert RESPONSE_SCHEMA_URI_TEMPLATE == "midas://{product}/{code}/response/v1"
    assert schema_uri_for(NODE_KEY, product="CIVIL NX") == "midas://civil/db/node/request/v1"
    assert (
        schema_uri_for(NODE_KEY, product="CIVIL NX", direction=RESPONSE_DIRECTION)
        == "midas://civil/db/node/response/v1"
    )
    with pytest.raises(ValueError):
        schema_uri_for(NODE_KEY, product="CIVIL NX", direction="both")
    assert registry.response_schema_document("DB.SWIND") is None


# ===== P137b：7 项 AND 如实报告（不写状态）=====


async def test_p137b_seven_and_is_reported_truthfully_without_promoting_any_status(
    tmp_path: Path,
) -> None:
    """P137b：报告如实汇总 7 项 AND；端点状态**仍**只由 `availability` 机械映射。"""
    engine, report, factory = await _import(tmp_path)
    assert report.seven_and is not None
    summary = report.seven_and.as_dict()
    assert summary["endpoints"] == 636
    assert summary["live_outcomes"] == 0, "CI 层无 L4 / L5 结论 → 第 7 项如实为假"
    assert summary["satisfied"] == {
        "official_endpoint_confirmed": 636,
        "http_method_confirmed": 635,  # `DB.SWIND` 没有任何方法（R9）
        "request_schema_confirmed": REQUEST_SCHEMA_ROWS,
        "response_schema_confirmed": RESPONSE_SCHEMA_ROWS,
        "product_scope_confirmed": 636,
        "version_range_confirmed": 636,
        "live_contract_test_passed": 0,
    }
    assert summary["missing"]["response_schema_confirmed"] == 636 - RESPONSE_SCHEMA_ROWS
    assert summary["verdicts"] == {STATUS_VERIFIED: 0, STATUS_PARTIAL: 636}
    assert report.as_dict()["seven_and"] == summary

    # 端点行的状态 = `availability` 机械映射（`docs/07` §7.2 / §16 R79），与报告无关
    async with factory() as session:
        statuses = dict(
            (
                await session.execute(
                    select(MidasApiEndpointORM.verification_status, func.count()).group_by(
                        MidasApiEndpointORM.verification_status
                    )
                )
            ).all()
        )
        node = await _status_of(session, NODE_KEY)
        partial = await _status_of(session, "DOC.NEW")
    await engine.dispose()
    # 实测端点（7 项 AND 全满足）与未实测端点（缺 response 项）都**未**被报告改动：
    # `DOC.NEW` 的 `availability = untested` → 仍是 `PARTIAL`（**不**升级、**不**降级）
    assert node == "VERIFIED" and partial == "PARTIAL"
    assert statuses["PARTIAL"] > 0 and statuses["VERIFIED"] > 0


async def _status_of(session: AsyncSession, key: str) -> str:
    """读某端点（`CIVIL_NX` 行）的 `verification_status`。"""
    value = (
        await session.execute(
            select(MidasApiEndpointORM.verification_status).where(
                MidasApiEndpointORM.operation == key,
                MidasApiEndpointORM.product == "CIVIL_NX",
            )
        )
    ).scalars()
    return str(value.first())


async def test_p137b_ci_records_never_promote_a_verification_status(tmp_path: Path) -> None:
    """P137b / R78：写入 L1 记录后再导入，状态与报告**逐条不变**。"""
    engine, before, factory = await _import(tmp_path)
    async with factory() as session:
        session.add(
            MidasApiVerificationORM(
                endpoint_key="DOC.NEW",
                contract_level="L1",
                product="CIVIL_NX",
                version_range=VERSION_RANGE,
                method="POST",
                path="/DOC/NEW",
                status="PASSED",
                schema_hash="sha256:" + "0" * 8,
                detail="L1 contract test passed (CI)",
                verified_at=utcnow(),
            )
        )
        await session.commit()
    async with factory() as session:
        after_import = await MidasRegistryImporter(support.registry()).import_all(session)
        await session.commit()
    async with factory() as session:
        status = await _status_of(session, "DOC.NEW")
        levels = (
            (await session.execute(select(MidasApiVerificationORM.contract_level))).scalars().all()
        )
    await engine.dispose()
    assert status == "PARTIAL"
    assert list(levels) == ["L1"]
    assert after_import.seven_and is not None and before.seven_and is not None
    assert after_import.seven_and.as_dict() == before.seven_and.as_dict()


def test_p137b_the_same_judgment_point_yields_verified_once_l4_passed() -> None:
    """P137b：L4 结论**显式**传入时同一判定点如实升 `VERIFIED`（238 + 1 例外 = R19）。"""
    registry = support.registry()
    covered = _covered_keys(registry)
    report = seven_and_report(
        registry,
        version="2026",
        supported_versions=support.SUPPORTED_VERSIONS_SPEC,
        live_outcomes={key: PROBE_PASSED for key in covered},
    )
    assert report.live_outcomes == RESPONSE_SCHEMA_ROWS
    assert report.verdicts == {
        STATUS_VERIFIED: RESPONSE_SCHEMA_ROWS - 1,
        STATUS_PARTIAL: 636 - (RESPONSE_SCHEMA_ROWS - 1),
    }
    evidence = registry_evidence(
        registry,
        key="DB.MBTP",
        product="GEN_NX",
        version="2026",
        supported_versions=support.SUPPORTED_VERSIONS_SPEC,
        live_outcome=PROBE_PASSED,
    )
    verdict = seven_and_verdict(evidence)
    assert verdict.status == STATUS_PARTIAL
    assert verdict.missing == ("request_schema_confirmed",), "唯一缺口 = R19 的请求 Schema 缺陷"
    # 报告**不**回写任何状态：端点状态仍由 `availability` 机械映射
    assert registry.endpoint("DB.MBTP").verification_status == "VERIFIED"
    assert registry.endpoint("DOC.NEW").verification_status == "PARTIAL"


def test_p137b_the_judgment_point_is_not_duplicated_in_the_importer() -> None:
    """P137b：7 项 AND 的判定点**只有** `live.py` 一处；导入器只**汇总**。"""
    source = IMPORT_REGISTRY_PATH.read_text(encoding="utf-8")
    assert len(SEVEN_AND_ITEMS) == 7
    for item in SEVEN_AND_ITEMS:
        assert item not in source, item
    modules = _imported_modules(IMPORT_REGISTRY_PATH)
    assert "app.infrastructure.adapters.midas.live" in modules
    for name in ("app.application", "app.interfaces", "app.observability", "app.container"):
        assert not any(module == name or module.startswith(f"{name}.") for module in modules), name
    for name in ("fastapi", "mcp"):
        assert not any(module == name or module.startswith(f"{name}.") for module in modules), name


# ===== P137c：真实 L5 写路径（缺声明 → skip，不失败、不伪造）=====


def _live_ready() -> bool:
    """真实 L5 的执行条件（`docs/04` §72 四要素 + 显式 opt-in）。"""
    if not live_opt_in_from_env(os.environ):
        return False
    if dedicated_test_project_from_env(os.environ) is None:
        return False
    return bool((os.environ.get(LIVE_BASE_ENV) or "").strip()) and bool(
        (os.environ.get(LIVE_KEY_ENV) or "").strip()
    )


def test_p137c_live_l5_is_skipped_without_the_documented_declaration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P137c：缺声明 → 用例**跳过**（判定只依赖环境声明，**不**回落当前项目）。"""
    for name in (MIDAS_LIVE_ENV, LIVE_PROJECT_ENV, LIVE_BASE_ENV, LIVE_KEY_ENV):
        monkeypatch.delenv(name, raising=False)
    assert live_opt_in_from_env(os.environ) is False
    assert dedicated_test_project_from_env(os.environ) is None
    assert _live_ready() is False


@pytest.mark.skipif(
    not _live_ready(),
    reason="真实 L5 需 MIDAS_LIVE_L4=1 + MIDAS_LIVE_PROJECT + MIDAS_BASE_URL + MIDAS_MAPI_KEY",
)
async def test_p137c_live_l5_write_path_only_touches_its_own_id(tmp_path: Path) -> None:
    """P137c：专用测试项目上「列出既有编号 → 建未占用编号 → 读回 → 按路径 key 删除」。"""
    engine = support.engine_for(tmp_path)
    await support.midas_tables(engine)
    factory = support.session_factory_for(engine)
    async with factory() as session:
        await MidasRegistryImporter(support.registry()).import_all(session)
        await session.commit()

    client = MidasHttpClient(
        base_url=os.environ[LIVE_BASE_ENV],
        credential_provider=MidasEnvironmentCredential(),
        secret_ref=LIVE_KEY_ENV,
    )
    probe = MidasLiveWriteProbe(
        client,
        support.registry(),
        product=LIVE_PRODUCT,
        project=dedicated_test_project_from_env(os.environ),
        only=(NODE_KEY,),
    )
    report = await probe.probe()
    assert report.keys() == (NODE_KEY,)
    outcome = report.outcomes[0]
    # 脱敏证据：只记方法 / 路径 / 结论 / 自建编号 —— **不**落响应体、**不**落凭据
    assert outcome.created_id, "L5 必须记下自己创建的编号"
    assert outcome.deleted is True, "按路径 key 清理必须成功"
    assert outcome.is_passed, outcome.detail
    assert support.SECRET not in json.dumps(
        {"key": outcome.key, "method": outcome.method, "path": outcome.path}, ensure_ascii=False
    )
    async with factory() as session:
        session.add(
            MidasApiVerificationORM(
                endpoint_key=outcome.key,
                contract_level="L5",
                product=LIVE_PRODUCT,
                version_range=VERSION_RANGE,
                method=outcome.method,
                path=outcome.path,
                status=outcome.outcome,
                schema_hash="",
                detail=outcome.detail,
                verified_at=utcnow(),
            )
        )
        await session.commit()
    async with factory() as session:
        stored = (
            (
                await session.execute(
                    select(MidasApiVerificationORM).where(
                        MidasApiVerificationORM.contract_level == "L5"
                    )
                )
            )
            .scalars()
            .all()
        )
    await client.close()
    await engine.dispose()
    assert len(stored) == 1 and stored[0].status == PROBE_PASSED
    assert stored[0].endpoint_key == NODE_KEY
