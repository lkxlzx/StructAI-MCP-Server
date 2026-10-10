"""P124 验收：Contract Test 分层 L1–L5（`docs/04` §69–§72；`docs/07` §12 P124）。

权威来源
--------
- `docs/04` §69（Contract Test 目的）—— 证明「Registry 描述 == 真实 MIDAS API」。
- `docs/04` §71（分层）—— **L1** Static Registry Test · **L2** Schema Test ·
  **L3** Mock Transport Test · **L4** Live MIDAS Contract Test · **L5** Business Effect Test；
  **CI 默认 L1–L3**，L4–L5 需**专用 MIDAS 环境**。
- `docs/04` §72（安全）—— Live Test 必须使用专用实例 / 专用 API Key / 专用项目 / 专用测试模型。
- `docs/07` §7.2 / §16 R1 —— `verification_status` 的 `VERIFIED` 判定是 **7 项 AND**，
  含「至少一次真实 Contract Test 通过」；本批**只**写 L1–L3 记录，
  **不得**因为「有冒烟记录」就升 `VERIFIED`。
- `docs/04` §18（API Contract Snapshot）—— 记录 `method` / `path` / `schema_hash` / `tested_at`。

落地裁决
--------
1. **L4 / L5 本批不执行**：`docs/04` §72 要求的专用环境（专用实例 / 专用 Key /
   专用项目 / 专用测试模型）在本机**不存在**，因此本批**不**伪造 L4/L5 记录；
   验收测试显式断言「L4/L5 记录为空」。
2. **不升级任何 `verification_status`**：L1–L3 记录写入 `midas_api_verifications`，
   但 `midas_api_endpoints.verification_status` 仍按 `availability` 的机械映射
   （`docs/07` §7.2），**不**因本批的 L1–L3 记录而提升（R1 的 7 项 AND 未满足）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema  # type: ignore[import-untyped]
import pytest
from sqlalchemy import func, select

import midas_p119_p126_support as support
from app.infrastructure.adapters.midas.import_registry import MidasRegistryImporter
from app.infrastructure.adapters.midas.models import (
    MidasApiEndpointORM,
    MidasApiVerificationORM,
)
from app.infrastructure.adapters.midas.operations import OPERATION_PLANS, plan_for
from app.infrastructure.adapters.midas.transforms import TRANSFORMER_REGISTRY
from app.infrastructure.database.base import utcnow

_NO_CONTEXT: Any = None
"""测试用的占位执行上下文（Adapter 侧只做转发，见 `tests/test_midas_p119_p123.py`）。"""

CONTRACT_LEVELS_CI: tuple[str, ...] = ("L1", "L2", "L3")
CONTRACT_LEVELS_DEDICATED: tuple[str, ...] = ("L4", "L5")
"""`docs/04` §71：CI 跑 L1–L3，专用 MIDAS 环境跑 L4–L5（逐条照抄）。"""


def _validator_for(schema: dict[str, Any]) -> Any:
    """按 Schema 自身声明的方言选校验器（P09 裁决 R18 的同一口径）。"""
    declared = str(schema.get("$schema") or "")
    if "draft-07" in declared:
        return jsonschema.Draft7Validator
    return jsonschema.Draft202012Validator


def _effective(schema_document: dict[str, Any]) -> dict[str, Any]:
    """剥离请求体包装根键后的生效 Schema（`registry/README.md` §2.1）。"""
    schema = schema_document.get("schema")
    if not isinstance(schema, dict):
        raise AssertionError("schema document has no object `schema`")
    if "properties" in schema or "type" in schema:
        return schema
    if len(schema) == 1:
        only = next(iter(schema.values()))
        if isinstance(only, dict):
            return only
    return schema


KNOWN_METHOD_CONFLICTS: tuple[str, ...] = ()
"""`operations.py` 声明的写步骤里，方法集与 `registry/` **冲突**的项 —— 现为**空**。

P124 时这里记的是 `MODEL.GROUP.DELETE:DB.GRUP:DELETE`（`docs/07` §6.4 把
`MODEL.GROUP.DELETE` 映射到 `DELETE /DB/GRUP/{id}`，而 `registry/` 里 `DB.GRUP` 的方法集
当时是 `POST, GET, PUT`）。**P149-A 更正**：只读 `OPTIONS` 实测（`Allow` 头 = 路由真实
方法集）确认 `DB.GRUP` 的该路由**确实**支持 `DELETE` ⇒ 冲突**消失**，清单归空。

按 `docs/07` 的硬性约束「涉及 MIDAS API 一律以 `registry/` 为准」，**任何**残余冲突都必须
在**解析期**明确失败（`STRUCTAI-3000` `method_not_available_for_product`）——**不**臆造端点、
**不**静默回落（下面用仍无 `DELETE` 的 `DB.UNIT` 继续验证这条口径）。
"""


def test_p124_l1_static_registry_layer() -> None:
    """L1（`docs/04` §71）：端点 / 方法 / Schema / Transformer 在**静态**层面自洽。"""
    registry = support.registry()
    conflicts: list[str] = []
    for plan in OPERATION_PLANS.values():
        for step in plan.steps:
            assert registry.has(step.key), f"{plan.operation}:{step.key}"
            definition = registry.endpoint(step.key)
            product = next(
                (
                    candidate
                    for candidate in ("CIVIL_NX", "GEN_NX")
                    if candidate in definition.products or candidate in definition.overrides
                ),
                None,
            )
            assert product is not None, f"{plan.operation}:{step.key}"
            resolved = registry.resolve(key=step.key, product=product)
            assert resolved.uri.startswith("/")
            if resolved.definition.methods and step.method not in resolved.definition.methods:
                conflicts.append(f"{plan.operation}:{step.key}:{step.method}")
            if step.transformer is not None:
                assert step.transformer in TRANSFORMER_REGISTRY
    assert len(OPERATION_PLANS) == 69
    assert conflicts == list(KNOWN_METHOD_CONFLICTS)
    # 方法集里**没有**的方法必须在**解析期**明确失败（不是静默用一个别的方法顶替）。
    # P149-A 更正：`DB.GRUP` 现已实测支持 `DELETE`（冲突消失），故用仍**无** `DELETE`
    # 的 `DB.UNIT` 验证同一条口径。
    from app.infrastructure.adapters.midas.errors import MidasCapabilityError

    with pytest.raises(MidasCapabilityError) as failure:
        registry.resolve(key="DB.UNIT", product="CIVIL_NX", method="DELETE")
    assert failure.value.details["reason"] == "method_not_available_for_product"
    # 每个带 Schema 的端点的 `schema_uri` 都是可计算的（`docs/07` §7.2）
    from app.infrastructure.adapters.midas.import_registry import schema_uri_for

    assert schema_uri_for("DB.NODE", product="CIVIL NX") == "midas://civil/db/node/request/v1"


def test_p124_l2_built_requests_validate_against_the_registry_schema() -> None:
    """L2（`docs/04` §71）：Transformer 产出的请求体必须能过 **Registry Schema**。"""
    registry = support.registry()
    checked = 0
    for operation in support.END_TO_END_OPERATIONS_SPEC:
        plan = plan_for(operation)
        for step in plan.steps:
            document = registry.schema_document(step.key)
            if document is None or step.transformer is None:
                continue
            effective = _effective(document)
            wrapper = registry.effective_schema(step.key) or {}
            properties = wrapper.get("properties") or {}
            body = _sample_body(step.key, step.transformer, registry)
            if not body:
                continue
            target = body
            for name in ("Argument", "Assign"):
                if name in properties and isinstance(body, dict) and name in body:
                    target = body[name]
                    break
            schema = effective
            if "properties" in effective and set(effective["properties"]) == {"Argument"}:
                schema = effective["properties"]["Argument"]
            errors = list(_validator_for(schema)(schema).iter_errors(target))
            assert errors == [], f"{operation}:{step.key}:{errors[:2]}"
            checked += 1
    assert checked >= 5, checked


def _sample_body(key: str, transformer_name: str, registry: Any) -> dict[str, Any]:
    """按端点给出一个**合法**样例条目（只用于 L2 的 Schema 校验）。"""
    samples: dict[str, dict[str, Any]] = {
        "DB.NODE": {"x": 0.0, "y": 0.0, "z": 0.0},
        "DB.ELEM": {"type": "BEAM", "node_ids": [1, 2], "material_id": 1, "section_id": 1},
        "DB.MATL": {"name": "Q355B", "type": "STEEL", "elastic_modulus": 2.06e11},
        "DB.SECT": {"name": "H400", "section_type": "DBUSER"},
        "DB.CONS": {
            "node_id": 1,
            "ux": True,
            "uy": True,
            "uz": True,
            "rx": True,
            "ry": True,
            "rz": True,
        },
        "DB.CNLD": {"load_type": "NODE_FORCE", "load_case": "AXIAL", "fz": -500_000.0},
        "DOC.ANAL": {"analysis_type": "STATIC"},
        "POST.TABLE": {"table_type": "DISPLACEMENTG"},
    }
    item = samples.get(key)
    if item is None:
        return {}
    transformer = TRANSFORMER_REGISTRY[transformer_name](registry)
    return transformer.to_native(item)


async def test_p124_l3_mock_transport_round_trip(tmp_path: Path) -> None:
    """L3（`docs/04` §71）：Registry → client → **Mock Transport** → 解析，全链可跑。"""
    transport = support.RecordingTransport()
    adapter = support.adapter(transport=transport)
    await adapter.connect(support.connect_config())
    outcome = await adapter.execute_normalized(
        "RESULT.NODE.DISPLACEMENT", {"node_ids": [2]}, _NO_CONTEXT
    )
    assert transport.calls[-1][:2] == ("POST", "/POST/TABLE")
    assert transport.calls[-1][2] == {"Argument": {"TABLE_TYPE": "DISPLACEMENTG"}}
    row = outcome["data"]["result"]["rows"][0]
    assert row["uz"] == pytest.approx(support.DISPLACEMENT_UZ_M)
    await adapter.disconnect()


async def _record_verifications(factory: Any, *, key: str, levels: tuple[str, ...]) -> None:
    """把 L1–L3 的结论写进 `midas_api_verifications`（`docs/04` §18）。"""
    registry = support.registry()
    definition = registry.endpoint(key)
    async with factory() as session:
        for level in levels:
            identity = {
                "endpoint_key": key,
                "contract_level": level,
                "product": "CIVIL_NX",
                "version_range": "2025-2026",
            }
            existing = (
                (await session.execute(select(MidasApiVerificationORM).filter_by(**identity)))
                .scalars()
                .first()
            )
            if existing is None:
                session.add(
                    MidasApiVerificationORM(
                        **identity,
                        method=definition.methods[0] if definition.methods else "",
                        path=definition.uri,
                        status="PASSED",
                        schema_hash="sha256:" + "0" * 8,
                        detail=f"{level} contract test passed (CI)",
                        verified_at=utcnow(),
                    )
                )
            else:
                existing.status = "PASSED"
        await session.commit()


async def test_p124_l1_to_l3_records_never_promote_verification_status(tmp_path: Path) -> None:
    """门槛 ⑤（`docs/07` §16 R1）：L1–L3 记录**不**升 `VERIFIED`（7 项 AND 未满足）。"""
    engine = support.engine_for(tmp_path)
    await support.midas_tables(engine)
    factory = support.session_factory_for(engine)
    async with factory() as session:
        await MidasRegistryImporter(support.registry()).import_all(session)
        await session.commit()
    before = await _status_of(factory, "DOC.NEW")
    assert before == "PARTIAL"

    await _record_verifications(factory, key="DOC.NEW", levels=CONTRACT_LEVELS_CI)
    await _record_verifications(factory, key="DOC.NEW", levels=CONTRACT_LEVELS_CI)  # 幂等
    async with factory() as session:
        count = await session.scalar(select(func.count()).select_from(MidasApiVerificationORM))
        levels = sorted(
            row[0]
            for row in await session.execute(
                select(MidasApiVerificationORM.contract_level).where(
                    MidasApiVerificationORM.endpoint_key == "DOC.NEW"
                )
            )
        )
    after = await _status_of(factory, "DOC.NEW")
    await engine.dispose()
    assert count == len(CONTRACT_LEVELS_CI)
    assert levels == list(CONTRACT_LEVELS_CI)
    assert after == before


async def test_p124_l4_l5_are_not_claimed_without_a_dedicated_environment(tmp_path: Path) -> None:
    """门槛 ⑤（`docs/04` §71 / §72）：本批**不**声称 L4/L5；无专用环境即不执行。"""
    engine = support.engine_for(tmp_path)
    await support.midas_tables(engine)
    factory = support.session_factory_for(engine)
    async with factory() as session:
        await MidasRegistryImporter(support.registry()).import_all(session)
        await session.commit()
    await _record_verifications(factory, key="DB.NODE", levels=CONTRACT_LEVELS_CI)
    async with factory() as session:
        recorded = sorted(
            row[0] for row in await session.execute(select(MidasApiVerificationORM.contract_level))
        )
    await engine.dispose()
    assert set(recorded) == set(CONTRACT_LEVELS_CI)
    for level in CONTRACT_LEVELS_DEDICATED:
        assert level not in recorded
    # 专用环境四要素（§72）在本机不可得 —— 明确记录为「未满足」，**不**伪造
    assert support.SECRET == "probe-key-not-a-real-credential"
    assert "example.invalid" in support.BASE_URL


async def _status_of(factory: Any, key: str) -> str:
    """读某端点的 `verification_status`（逐产品取 `CIVIL_NX` 的那一行）。"""
    async with factory() as session:
        row = (
            (
                await session.execute(
                    select(MidasApiEndpointORM.verification_status).where(
                        MidasApiEndpointORM.operation == key,
                        MidasApiEndpointORM.product == "CIVIL_NX",
                    )
                )
            )
            .scalars()
            .first()
        )
    return str(row)
