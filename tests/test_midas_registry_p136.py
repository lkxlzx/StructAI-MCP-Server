"""P136 验收：数据侧收口（生成链）—— R85 产品可得性 + R87 response 方向 Schema。

权威来源
--------
- `docs/07` §16 **R85**（L4 实测的产品可得性差异）· **R87 / R90**（缺 response 方向 Schema）·
  **R4 / R14**（写路径实测覆盖）· `docs/04` §8（`VERIFIED` 的 **7 项 AND**）。
- `registry/README.md` §2.2（response 方向 Schema）· §8.2（R85 的产品可得性收口）。
- `docs/reports/P136_数据侧收口与L4复核_v1.0.md`（本批的脱敏实测证据）。

落地裁决（本文件的硬事实，不美化）
--------------------------------
1. **数据侧改动可复算**：`registry/tools/sync_response_schemas.py` 幂等 —— 重算出的
   `response` 块与数据**逐字节一致**，且**只追加**该块（请求方向 `schema` 一行未改）。
2. **只按实测写**：response 方向 Schema **只**断言**实测到的信封层级**，
   叶子类型留空（未实测 → 不猜），载荷字段一个都不写。
3. **R85 已落进数据**：不可得的产品从 `products` 摘除、`unavailable_on` 保留实例级记录；
   判定口径（`availability` → `verification_status`）**一行未改**。
4. **判定点如实**：已实测端点在同一判定点上升 `VERIFIED`；缺项（如 `DB.MBTP` 的
   请求 Schema 数据缺陷，`docs/07` §16 R19）**如实**保留 `PARTIAL` 并报出缺哪一项。
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

import midas_p119_p126_support as support
from app.infrastructure.adapters.midas.live import (
    PROBE_PASSED,
    SEVEN_AND_ITEMS,
    STATUS_PARTIAL,
    STATUS_VERIFIED,
    registry_evidence,
    seven_and_verdict,
)
from app.infrastructure.adapters.midas.registry import MidasRegistry

TOOL_PATH = Path("registry/tools/sync_response_schemas.py")
"""数据侧生成链的唯一入口（`registry/tools/`，只依赖标准库）。"""

RESPONSE_BLOCK_ENDPOINTS = 239
"""已实测端点（`availability=verified` + `GET` + 有 Schema 文件）= 补了 `response` 块的端点数。"""

R85_GEN_NX_PRODUCT_GAPS: tuple[str, ...] = (
    "DB.CAMB",
    "DB.CJFG",
    "DB.CMCS",
    "DB.CRGR",
    "DB.DYFG",
    "DB.DYLA",
    "DB.DYNF",
    "DB.EWSF",
    "DB.GCMB",
    "DB.GSBG",
    "DB.PLCB",
    "DB.RCHK",
    "DB.STRPSSM",
    "DB.WVLD",
)
"""R85：GEN NX 上实测 `404` → `GEN_NX` 已从 `products` 摘除的 14 个端点。"""

R85_CIVIL_NX_PRODUCT_GAPS_REMOVED: tuple[str, ...] = (
    "DB.SDHY",
    "DB.SDIS",
    "DB.THRS",
    "DESIGN.RC.KDS-41-20-2022.MATD",
    "DESIGN.SRC.AIK-SRC2K.MATD",
)
"""R85：CIVIL NX 上实测 `404` → `CIVIL_NX` 已从 `products` 摘除的 5 个端点。"""

R85_CIVIL_NX_PRODUCT_GAPS_UNVERIFIED: tuple[str, ...] = ("DB.UFTR", "DB.UTBL")
"""R85：CIVIL NX 上实测 `404`，数据侧**本来**就标了 `unverified` → 本批**不动**。"""

_SCHEMA_FILE_KEYS = {"key", "uri", "source", "schema", "shape", "response"}
"""Schema 文件允许出现的键（`response` 是本批**唯一**新增的，见裁决 1）。"""


def _registry() -> MidasRegistry:
    """数据侧 Registry（`registry/` 的唯一权威来源）。"""
    return support.registry()


def _manifest() -> dict[str, Any]:
    """`registry/manifest.json` 原文（`products` / `unavailable_on` 等派生字段的唯一来源）。"""
    return json.loads((_registry().root / "manifest.json").read_text(encoding="utf-8"))


def _entry(key: str) -> dict[str, Any]:
    """按 key 取 manifest 条目。"""
    for entry in _manifest()["endpoints"]:
        if entry["key"] == key:
            return entry
    raise AssertionError(f"{key} not in registry/manifest.json")


def _tool() -> Any:
    """装载数据侧生成器（按文件路径导入，**不**进 `app/`）。"""
    spec = importlib.util.spec_from_file_location("sync_response_schemas", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _covered_keys() -> tuple[str, ...]:
    """数据里声明了 `response` 块的端点 key。"""
    registry = _registry()
    keys: list[str] = []
    for entry in _manifest()["endpoints"]:
        document = registry.schema_document(entry["key"])
        if document is not None and document.get("response"):
            keys.append(entry["key"])
    return tuple(keys)


def _evidence(key: str, **overrides: Any) -> dict[str, bool]:
    """该端点在「L4 已通过」前提下的 7 项 AND 证据。"""
    entry = _entry(key)
    base = registry_evidence(
        _registry(),
        key=key,
        product=entry["products"][0],
        version="2026",
        supported_versions=support.SUPPORTED_VERSIONS_SPEC,
        live_outcome=PROBE_PASSED,
    )
    assert set(base) == set(SEVEN_AND_ITEMS), key
    return {**base, **overrides}


# ===== P136b：response 方向 Schema 的覆盖与内容 =====


def test_p136_response_schema_coverage_is_exactly_the_measured_rule() -> None:
    """P136b：`response` 块的覆盖 == 「已实测」规则（`verified` + `GET` + 有 Schema 文件）。"""
    registry = _registry()
    covered = _covered_keys()
    for entry in _manifest()["endpoints"]:
        document = registry.schema_document(entry["key"])
        has_block = bool(document is not None and document.get("response"))
        measured = (
            str(entry["availability"]) == "verified"
            and "GET" in [part.strip().upper() for part in str(entry["methods"]).split(",")]
            and bool(entry.get("schema"))
        )
        assert has_block is measured, entry["key"]
    assert len(covered) == RESPONSE_BLOCK_ENDPOINTS
    # 未实测 / 无 Schema 的端点**没有** response 块（**不**臆造）
    for key in ("DB.SWIND", "OPE.PROJECTSTATUS", "DB.LCOM"):
        assert key not in covered, key


def test_p136_the_generator_is_idempotent_and_only_appends_the_response_block() -> None:
    """P136b：生成器可复算 —— 重算块与数据逐字节一致，且请求方向**一行未改**。"""
    tool = _tool()
    registry = _registry()
    checked = 0
    for entry in _manifest()["endpoints"]:
        document = registry.schema_document(entry["key"])
        if document is None or not document.get("response"):
            continue
        assert set(document) <= _SCHEMA_FILE_KEYS, entry["key"]
        block = document["response"]
        assert block == tool.response_block(tool.envelope_chains(entry)), entry["key"]
        assert block["direction"] == "response", entry["key"]
        assert block["source"] == tool.RESPONSE_SOURCE, entry["key"]
        checked += 1
    assert checked == RESPONSE_BLOCK_ENDPOINTS


def test_p136_the_response_schema_only_asserts_the_measured_envelope() -> None:
    """P136b：response Schema **只**断言实测到的信封层级（载荷字段一个都不写）。"""
    registry = _registry()
    node = registry.response_schema_json("DB.NODE")
    assert node is not None
    assert node["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert node["type"] == "object"
    branches = node["oneOf"]
    # NX 系实测口径（`registry/README.md` §4）：`{<read_root>: {...}}`
    assert {"required": ["NODE"], "properties": {"NODE": {"type": "object"}}} in branches
    # `CIVIL_DESIGNER` 实测口径（R83）：业务载荷在 `result.return_value`
    assert {
        "type": "object",
        "required": ["result"],
        "properties": {
            "result": {
                "type": "object",
                "required": ["return_value"],
                "properties": {"return_value": {}},
            }
        },
    } in branches
    # 单信封端点（Designer 专有）只有一层链
    unit = registry.response_schema_json("DOC.UNIT")
    assert unit is not None and "oneOf" not in unit
    assert unit["properties"]["result"]["properties"]["return_value"] == {}
    # 实测未覆盖的载荷字段（`X` / `Y` / `Z`）**不得**出现在任何 response Schema 里
    for key in _covered_keys():
        schema = registry.response_schema_json(key)
        assert schema is not None, key
        assert schema["type"] == "object", key
        for forbidden in ('"X"', '"Y"', '"Z"', "ITEMS"):
            assert forbidden not in json.dumps(schema), (key, forbidden)


# ===== P136b / R87：同一判定点如实升级 =====


def test_p136_measured_endpoints_are_verified_on_all_seven_items() -> None:
    """P136b / R87：已实测端点在同一判定点上升 `VERIFIED`（**恰好 1** 个例外见 R19）。"""
    fully, partial = 0, []
    for key in _covered_keys():
        verdict = seven_and_verdict(_evidence(key))
        if verdict.status == STATUS_VERIFIED:
            assert verdict.missing == ()
            fully += 1
            continue
        partial.append((key, verdict.missing))
    # P138a（R19 收口）后**没有**例外：`DB.MBTP` 的请求 Schema 已从上游重建为合法对象
    assert fully == RESPONSE_BLOCK_ENDPOINTS
    assert partial == []


def test_p136_unmeasured_endpoints_stay_partial_and_report_what_is_missing() -> None:
    """R87 / R78：未实测的端点仍**如实**缺项（`response_schema_confirmed` 恒在缺项里）。"""
    for key in ("DB.SWIND", "OPE.PROJECTSTATUS"):
        verdict = seven_and_verdict(_evidence(key))
        assert verdict.status == STATUS_PARTIAL, key
        assert "response_schema_confirmed" in verdict.missing, key
    # 缺该项时**只**缺它（把 `DB.NODE` 的该项改回假 → 立刻回到 `PARTIAL`）
    downgraded = seven_and_verdict(_evidence("DB.NODE", response_schema_confirmed=False))
    assert downgraded.status == STATUS_PARTIAL
    assert downgraded.missing == ("response_schema_confirmed",)


# ===== P136a：R85 落进数据，且**不改判定** =====


def test_p136_r85_removals_are_applied_to_manifest_and_yaml_alike() -> None:
    """P136a：`products` 的改动**同时**落在 YAML（真源）与 `manifest.json`（派生）。"""
    registry = _registry()
    registry_root = registry.root
    cases = (
        *((key, "GEN_NX", "CIVIL_NX") for key in R85_GEN_NX_PRODUCT_GAPS),
        *((key, "CIVIL_NX", "GEN_NX") for key in R85_CIVIL_NX_PRODUCT_GAPS_REMOVED),
    )
    for key, removed, kept in cases:
        definition = registry.endpoint(key)
        assert removed not in definition.products, key
        assert kept in definition.products, key
        assert _entry(key)["products"] == list(definition.products), key
        document = yaml.safe_load(
            (registry_root / _entry(key)["definition"]).read_text(encoding="utf-8")
        )
        assert document["products"] == list(definition.products), key


def test_p136_r85_keeps_the_instance_level_record_and_never_moves_a_status() -> None:
    """P136a：`unavailable_on` 保留实例级实测记录；`availability` / `enabled` **未动**。"""
    registry = _registry()
    for key in (*R85_GEN_NX_PRODUCT_GAPS, *R85_CIVIL_NX_PRODUCT_GAPS_REMOVED):
        definition = registry.endpoint(key)
        assert definition.availability == "verified", key
        assert definition.enabled is True, key
        assert definition.verification_status == "VERIFIED", key
        assert _entry(key)["unavailable_on"], key
    for key in R85_CIVIL_NX_PRODUCT_GAPS_UNVERIFIED:
        definition = registry.endpoint(key)
        # 数据侧**本来**就如实标了 `unverified` → 本批**不动**（改反而会臆造）
        assert definition.availability == "unverified", key
        assert definition.verification_status == "UNVERIFIED", key
        assert "CIVIL_NX" in definition.products, key


def test_p138_span_gen_nx_is_removed_consistently_with_the_fourteen() -> None:
    """R85 裁决（P138d，选项 A）：`DB.SPAN` 的 `GEN_NX` **一致地**摘除。

    依据（**可执行**）：`DB.SPAN` 与 P136 已摘除的 **14** 条**同形** —— 在 `gen-local`
    上 `404`（`unavailable_on`）、在非 GEN 实例上可用；把「实测 `404` 的产品从 `products`
    摘除」的口径只用在这 14 条上、却对同形的 `DB.SPAN` 例外，是**口径不一致**。
    `availability` / `verified_on` / `unavailable_on` / `enabled` **一行未改**（改数据不改判定）。
    恢复条件：**更新**的 GEN NX 构建上 `/DB/SPAN` 路由成功（新的 L4 `PASSED`）→ 恢复 `GEN_NX`。
    """
    definition = _registry().endpoint("DB.SPAN")
    assert "CIVIL_DESIGNER" in definition.products
    assert "CIVIL_NX" in definition.products
    assert "GEN_NX" not in definition.products, "R85 裁决 A：与 14 条同形 → 一致摘除"
    entry = _entry("DB.SPAN")
    assert "gen-local" in entry["unavailable_on"]
    assert definition.availability == "verified", "判定口径未改（仍由 availability 机械映射）"
    # 解析期即如实失败（不再发必然 404 的请求）
    with pytest.raises(Exception) as failure:
        _registry().resolve(key="DB.SPAN", product="GEN_NX", method="GET")
    assert getattr(failure.value, "code", "") == "STRUCTAI-3000"
    assert failure.value.details["reason"] == "endpoint_not_available_for_product"


# ===== 红线：数据侧工具不得引入新依赖 / 不得进 `app/` =====


def test_p136_the_generator_is_a_data_side_standard_library_tool() -> None:
    """数据侧生成器只依赖标准库（**不**新增依赖，`docs/07` §3.1）。"""
    tree = ast.parse(TOOL_PATH.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    assert modules <= {"__future__", "argparse", "json", "pathlib", "sys", "typing"}, modules
    for name in ("sqlalchemy", "fastapi", "mcp", "httpx", "yaml", "jsonschema", "app"):
        assert not any(module == name or module.startswith(f"{name}.") for module in modules), name
