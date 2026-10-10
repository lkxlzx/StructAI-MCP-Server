"""P141 —— R5 剩余 5 条（手册**同 URI** 条目的规格表）+ 写路径分母的**子桶裁决** + R96 前置链。

权威来源
--------
- `docs/07` §16 **R5** / **R96** / §16.1（P140 的下一步：R5 剩余、非空项目上的前置链）。
- `docs/reports/P140_R5剩余补齐_v1.0.md`（本批的**起点**：仍无 Schema 的 16 个端点）。
- `docs/reports/P141_*.md`（本批证据）。

本文件的**可执行判定**
--------------------
1. **5 条全部可补且来源可复算**：`OPE.{MEMB, STOR, STORPROP, STORY_IRR_PARAM, STORY_PARAM}`
   的手册条目与端点**同一 `input_uri`**，但条目**没有** `json_schema`（只有规格表）——
   这正是 P138b 的 `manual_has_no_json_schema` 判据；本批按**声明的定位串**机械定位，
   文件内容逐字节等于 `registry/tools/sync_request_schemas.py` 的机械结果。
2. **规格表逐字段忠实**：生成 Schema 里的**字段名集合** == 手册规格表里带引号的字段行集合
   （**不**多、**不**少；`TABLE_TYPE` 之类表头行**不**进 Schema）。
3. **不臆造**：`registry/schema/**` = **625**（P140 的 620 + 5）；仍无 Schema 的端点 = **11**
   （20 − 4 − 5），逐条可查；`manual_has_no_json_schema` 类**清零**。
4. **分母裁决（⑤）**：`write_path_keys()` 仍是 R4 / R14 的**分母 609**（**不挪**），
   但**显式**划分成「结果表 / 文本查询」**199** 与「模型写」**410** 两个子桶，并**同时**报
   `WriteCoverage.ratio`（609 口径）与 `model_write_ratio`（410 口径）—— 原口径**不**过滤、
   **不**隐藏任何未覆盖项。
5. **R96（非空项目上的前置链）**：模板声明的编号**不**照抄 —— 前置编号取该端点既有编号的
   `max + 1`（`id_source = "target"` 的前置取**目标**编号），并按 `references` /
   `self_references` 写回；**默认**仍要求专用项目为空，`allow_non_empty=True` 时改由
   「清理后既有编号集合**一字未变**」判定（**更强**的「只碰自建 ID」判据）。
6. **真实实测（门控）**：在**已预置模型**的专用项目上跑 R96 —— 目标与前置都取 `max + 1`，
   预置编号一字未变，跑完只剩预置模型。
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

import midas_p119_p126_support as support
import test_midas_write_templates_p139 as p139
from app.infrastructure.adapters.midas.client import (
    MidasEnvironmentCredential,
    MidasHttpClient,
)
from app.infrastructure.adapters.midas.errors import MidasCapabilityError
from app.infrastructure.adapters.midas.live import (
    LIVE_PROJECT_ENV,
    MIDAS_LIVE_ENV,
    DedicatedTestProject,
    dedicated_test_project_from_env,
    live_opt_in_from_env,
    model_write_keys,
    result_query_keys,
    write_path_coverage,
    write_path_keys,
)
from app.infrastructure.adapters.midas.registry import MidasRegistry, verification_status_for
from app.infrastructure.adapters.midas.write_probe import (
    WRITE_PROBE_FAILED,
    WRITE_PROBE_PASSED,
    MidasLiveWriteProbe,
)
from app.infrastructure.adapters.midas.write_templates import (
    WritePayloadTemplate,
    WritePrerequisite,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录（上游手册 / 数据侧工具都在这里）。"""

TOOL_PATH = REPO_ROOT / "registry" / "tools" / "sync_request_schemas.py"
"""本批的**唯一**生成落点（只依赖标准库；`--check` 断言「已落盘 == 机械结果」）。"""

CHECK_TOOL_PATH = REPO_ROOT / "registry" / "tools" / "check_write_templates.py"
"""模板校验工具（P141 起校验 `id_source` / `references` / `self_references`）。"""

MANUAL_PATH = REPO_ROOT / "MIDAS_API_Online_Manual_数据_v1.0.json"
"""上游手册（`endpoints[].input_uri` / `json_schema` / `specifications`）。"""

SCHEMA_ROOT = REPO_ROOT / "registry" / "schema"
"""`registry/schema/**`（本批 **620 → 625**）。"""

EXPECTED_SCHEMA_FILES = 625
"""本批之后的数据侧 Schema 文件数。"""

EXPECTED_WITHOUT_SCHEMA = 11
"""本批之后仍无 Schema 的端点数（P138b 的 20 − P140 的 4 − P141 的 5）。"""

WRITE_PATH_TOTAL = 609
"""写路径端点数 —— R4 / R14 的**正式**分母（裁决⑤：**不挪**）。"""

RESULT_QUERY_TOTAL = 199
"""分母里的「结果表 / 文本查询」子桶（`POST.` 命名空间；见 `live.RESULT_QUERY_NAMESPACE`）。"""

MODEL_WRITE_TOTAL = 410
"""分母里的「模型写」子桶（`609 − 199`）。"""

SPEC_TABLE_LOCATORS: dict[str, str] = {
    "OPE.MEMB": "uri:ope/MEMB",
    "OPE.STOR": "uri:ope/STOR",
    "OPE.STORPROP": "uri:ope/STORPROP",
    "OPE.STORY_IRR_PARAM": "uri:ope/STORY_IRR_PARAM",
    "OPE.STORY_PARAM": "uri:ope/STORY_PARAM",
}
"""本批补齐的 **5** 个端点 → 声明的手册定位串（与生成器 `SPEC_TABLE_SOURCES` 一致）。"""

SPEC_TABLE_SOURCE = "help_center_spec_table"
"""这 5 个文件落盘的 `source` 取值（规格表派生）。"""

EXPECTED_REFERENCE_PATHS = 22
"""`registry/live/write_templates.json` 里声明的 `references` 条数（P145 起 22）。"""

EXPECTED_SELF_REFERENCE_PATHS = 4
"""同文件里声明的 `self_references` 条数（P141 起）。"""

LIVE_MODEL_MATL: dict[str, Any] = {
    "TYPE": "STEEL",
    "NAME": "DB_Steel",
    "HE_SPEC": 0,
    "HE_COND": 0,
    "PLMT": 0,
    "P_NAME": "",
    "bMASS_DENS": False,
    "DAMP_RAT": 0.02,
    "PARAM": [
        {
            "P_TYPE": 1,
            "STANDARD": "EN05(S)",
            "CODE": "",
            "DB": "S450",
            "bELAST": False,
            "ELAST": 210000000,
        }
    ],
}
"""实测用的材质体（与 P140 实测同形 —— 精简体会被实例拒绝）。"""

LIVE_MODEL_SECT: dict[str, Any] = {
    "SECTTYPE": "DBUSER",
    "SECT_NAME": "LT_Const",
    "SECT_BEFORE": {
        "OFFSET_PT": "LT",
        "HORZ_OFFSET_OPT": 0,
        "VERT_OFFSET_OPT": 0,
        "USE_SHEAR_DEFORM": False,
        "USE_WARPING_EFFECT": False,
        "SHAPE": "SB",
        "DATATYPE": 2,
        "SECT_I": {"vSIZE": [1, 1]},
    },
}
"""实测用的截面体（与 P140 实测同形 —— 精简体会被实例拒绝）。"""

LIVE_MODEL_BMLD: dict[str, Any] = {
    "ITEMS": [
        {
            "ID": 1,
            "LCNAME": "D",
            "GROUP_NAME": "",
            "CMD": "BEAM",
            "TYPE": "UNILOAD",
            "DIRECTION": "GZ",
            "USE_PROJECTION": False,
            "USE_ECCEN": False,
            "D": [0, 1, 0, 0],
            "P": [-50, -50, 0, 0],
        }
    ]
}
"""实测用的梁单元荷载（② 的判别需要**有分析结果**）。"""

LIVE_MODEL: tuple[tuple[str, str, object], ...] = (
    ("MATL", "1", LIVE_MODEL_MATL),
    ("SECT", "1", LIVE_MODEL_SECT),
    ("NODE", "1", {"X": 0.0, "Y": 0.0, "Z": 0.0}),
    ("NODE", "2", {"X": 1.0, "Y": 0.0, "Z": 0.0}),
)
"""**预置**的最小模型（R96 的「非空项目」；只碰自建编号，跑完删除）。"""

PREPOPULATED_SENTINELS = ("MATL", "SECT", "NODE")
"""预置后**必须非空**的哨兵（证明 R96 跑在非空项目上，而不是空项目）。"""


# ===== 辅助 =====


def _registry() -> MidasRegistry:
    """数据侧 Registry（`registry/` 的唯一权威来源）。"""
    return support.registry()


def _tool() -> Any:
    """按路径装载 `registry/tools/sync_request_schemas.py`（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location("structai_sync_request_schemas_p141", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manual_entries() -> list[dict[str, Any]]:
    """上游手册的端点条目。"""
    payload = json.loads(MANUAL_PATH.read_text(encoding="utf-8"))
    return list(payload["endpoints"])


def _manifest_entries() -> list[dict[str, Any]]:
    """`registry/manifest.json` 的端点条目。"""
    document = json.loads((REPO_ROOT / "registry" / "manifest.json").read_text(encoding="utf-8"))
    return list(document["endpoints"])


def _spec_field_names(entry: dict[str, Any]) -> set[str]:
    """手册规格表里带引号的字段名（生成器的**唯一**字段来源）。"""
    names: set[str] = set()
    for row in entry.get("specifications") or []:
        if not isinstance(row, list) or len(row) < 6:
            continue
        match = re.fullmatch(r'"([A-Za-z0-9_]+)"', str(row[2] or "").strip())
        if match is not None:
            names.add(match.group(1))
    return names


def _schema_field_names(node: object) -> set[str]:
    """Schema 里出现过的**全部**字段名（逐层递归；只取 `properties` 的键）。"""
    if not isinstance(node, dict):
        return set()
    found: set[str] = set()
    properties = node.get("properties")
    if isinstance(properties, dict):
        for name, child in properties.items():
            found.add(str(name))
            found |= _schema_field_names(child)
    items = node.get("items")
    if isinstance(items, dict):
        found |= _schema_field_names(items)
    return found


def _schema_path(key: str) -> Path:
    """该端点的数据侧 Schema 文件（`schema_ref.local` 的落点）。"""
    relative = _registry().endpoint(key).schema_path
    assert relative, f"{key}: 本批之后必须已有 Schema 文件"
    return REPO_ROOT / "registry" / relative


def _live_ready() -> bool:
    """真实实测的执行条件（`docs/04` §72 四要素 + 显式 opt-in）。"""
    if not live_opt_in_from_env(os.environ):
        return False
    if dedicated_test_project_from_env(os.environ) is None:
        return False
    return bool((os.environ.get("MIDAS_BASE_URL") or "").strip()) and bool(
        (os.environ.get("MIDAS_MAPI_KEY") or "").strip()
    )


class _Row:
    """`midas_api_verifications` 行的**最小**替身（只暴露判定要用的三个字段）。"""

    def __init__(self, key: str, *, level: str = "L5", status: str = "PASSED") -> None:
        self.endpoint_key = key
        self.contract_level = level
        self.status = status


# ===== 1. 5 个文件：来源可复算（离线）=====


def test_p141_the_five_files_match_the_mechanical_result() -> None:
    """门槛：本批 5 个文件**逐字节**等于生成器的机械结果；`--check` 退出码 0。"""
    module = _tool()
    documents = module.build_documents(REPO_ROOT)
    assert len(documents) == 9, "P140 的 4 个 + P141 的 5 个"
    selected = [item for item in documents if item[1]["key"] in SPEC_TABLE_LOCATORS]
    assert len(selected) == len(SPEC_TABLE_LOCATORS) == 5
    for relative, document, _origin in selected:
        path = REPO_ROOT / "registry" / relative
        merged = module.with_preserved_response(path, document)
        text = json.dumps(merged, ensure_ascii=False, indent=2) + "\n"
        assert path.read_text(encoding="utf-8") == text, relative
    assert module.main(["--repo", str(REPO_ROOT), "--check"]) == 0


def test_p141_the_five_entries_are_located_by_the_declared_locator() -> None:
    """门槛：5 个端点的手册条目**同一 `input_uri`**、**没有** `json_schema`、**有**规格表。"""
    registry = _registry()
    entries = _manual_entries()
    for key, locator in SPEC_TABLE_LOCATORS.items():
        uri = registry.endpoint(key).uri.lstrip("/")
        kind, _, value = locator.partition(":")
        assert kind == "uri", key
        assert value.lower() == uri.lower(), f"{key}: 定位串必须**逐字**等于端点 URI"
        matches = [
            entry for entry in entries if str(entry.get("input_uri") or "").lower() == value.lower()
        ]
        assert len(matches) == 1, f"{key}: 定位串命中的条目数 = {len(matches)}，期望 1"
        entry = matches[0]
        assert not entry.get("json_schema"), f"{key}: 该条目**有** json_schema → 判据不成立"
        assert entry.get("specifications"), key


def test_p141_the_generated_schema_is_field_for_field_faithful_to_the_spec_table() -> None:
    """门槛：Schema 的字段名集合 == 规格表的字段行集合（**不**多、**不**少）。"""
    registry = _registry()
    entries = _manual_entries()
    by_uri = {str(entry.get("input_uri") or "").lower(): entry for entry in entries}
    for key in SPEC_TABLE_LOCATORS:
        uri = registry.endpoint(key).uri.lstrip("/").lower()
        expected = _spec_field_names(by_uri[uri])
        assert expected, key
        schema = registry.schema_json(key)
        assert isinstance(schema, dict), key
        # 包装键取数据侧声明的 `wrapper.write`（**不**猜）；它是**结构**、不是规格表的字段行
        wrapper = registry.endpoint(key).wrapper_write
        properties = schema.get("properties")
        assert isinstance(properties, dict), key
        assert wrapper in properties, f"{key}: 缺包装键 {wrapper!r}"
        assert _schema_field_names(schema) - {wrapper} == expected, key


def test_p141_the_check_tool_verifies_the_declared_reference_paths() -> None:
    """门槛：模板校验工具**逐条**验证编号声明（路径存在且取值等于声明的编号）。"""
    completed = subprocess.run(  # noqa: S603
        [sys.executable, str(CHECK_TOOL_PATH)],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stdout[-600:]
    references = f"引用的编号路径（references）= {EXPECTED_REFERENCE_PATHS}"
    self_references = f"目标自身编号路径（self_references）= {EXPECTED_SELF_REFERENCE_PATHS}"
    assert references in completed.stdout
    assert self_references in completed.stdout


# ===== 2. 计数与声明（离线）=====


def test_p141_the_closure_adds_exactly_five_files_and_leaves_eleven_without() -> None:
    """门槛：`registry/schema/**` = **625**；仍无 Schema 的端点 = **11**（20 − 4 − 5）。"""
    files = sorted(SCHEMA_ROOT.rglob("*.json"))
    assert len(files) == EXPECTED_SCHEMA_FILES
    registry = _registry()
    for key in SPEC_TABLE_LOCATORS:
        assert registry.schema_json(key) is not None, key
    manifest = {entry["key"]: entry for entry in _manifest_entries()}
    without = sorted(key for key, entry in manifest.items() if not entry.get("schema"))
    assert len(without) == EXPECTED_WITHOUT_SCHEMA
    assert not set(without) & set(SPEC_TABLE_LOCATORS)


def test_p141_the_manifest_and_the_endpoint_files_declare_the_new_schemas() -> None:
    """门槛：manifest 的 `schema` / `schema_source` 与端点 YAML 的 `schema_ref` 逐条落地。"""
    manifest = {entry["key"]: entry for entry in _manifest_entries()}
    for key in SPEC_TABLE_LOCATORS:
        entry = manifest[key]
        relative = str(entry["schema"])
        assert relative.startswith("schema/"), key
        assert (REPO_ROOT / "registry" / relative).is_file(), key
        assert entry["schema_source"] == SPEC_TABLE_SOURCE, key
        text = (REPO_ROOT / "registry" / str(entry["definition"])).read_text(encoding="utf-8")
        assert f"local: {relative}" in text, key
        assert f"source: {SPEC_TABLE_SOURCE}" in text, key
        assert "unavailable_reason" not in text, f"{key}: 已有 Schema，不得留 unavailable_reason"


def test_p141_the_five_endpoints_keep_the_mechanical_verification_status() -> None:
    """门槛：判定口径**未**改 —— `verification_status` 仍只由 `availability` 机械映射。

    P141 **只**补请求 Schema，**不**动 `availability`：`OPE.{MEMB, STOR, STORPROP}` 仍
    `untested` → `PARTIAL`；`OPE.STORY_{IRR_,}PARAM` 本就 `verified`（L4 只读实测过）
    → `VERIFIED`。这与 7 项 AND 的 `VERIFIED` **不是**一回事（`docs/07` §16 R78）。
    """
    registry = _registry()
    expected = {
        "OPE.MEMB": "PARTIAL",
        "OPE.STOR": "PARTIAL",
        "OPE.STORPROP": "PARTIAL",
        "OPE.STORY_IRR_PARAM": "VERIFIED",
        "OPE.STORY_PARAM": "VERIFIED",
    }
    for key in SPEC_TABLE_LOCATORS:
        definition = registry.endpoint(key)
        assert definition.verification_status == expected[key], key
        assert definition.verification_status == verification_status_for(
            availability=definition.availability, enabled=definition.enabled
        ), key


# ===== 3. 分母裁决（⑤，离线）=====
def test_p141_the_denominator_is_unchanged_and_partitioned() -> None:
    """门槛（裁决⑤）：分母**不挪**（609），但显式划分成 199 + 410 两个子桶。"""
    registry = _registry()
    write_keys = write_path_keys(registry)
    query = result_query_keys(registry)
    model = model_write_keys(registry)
    assert len(write_keys) == WRITE_PATH_TOTAL, "分母仍是 write_path_keys()，本批**不**改口径"
    assert len(query) == RESULT_QUERY_TOTAL
    assert len(model) == MODEL_WRITE_TOTAL
    assert len(query) + len(model) == len(write_keys)
    assert set(query) | set(model) == set(write_keys)
    assert not set(query) & set(model)
    assert all(key.startswith("POST.") for key in query), "子桶判据只看数据侧 namespace"
    coverage = write_path_coverage(registry, [])
    assert coverage.ratio == f"0 / {WRITE_PATH_TOTAL}"
    assert coverage.model_write_ratio == f"0 / {MODEL_WRITE_TOTAL}"
    assert coverage.as_dict()["result_query"] == RESULT_QUERY_TOTAL
    assert coverage.as_dict()["model_write"] == MODEL_WRITE_TOTAL


def test_p141_the_sub_bucket_never_hides_an_uncovered_endpoint() -> None:
    """门槛（裁决⑤）：原口径**不**过滤 —— 结果表端点若真有 L5 行也**照样**计入原分子。"""
    registry = _registry()
    coverage = write_path_coverage(registry, [_Row("POST.TABLE"), _Row("DB.NODE")])
    assert coverage.covered == 2, "原口径不得过滤任何写路径端点"
    assert coverage.ratio == f"2 / {WRITE_PATH_TOTAL}"
    assert coverage.model_write_covered == 1, "子桶口径只数模型写端点"
    assert coverage.model_write_ratio == f"1 / {MODEL_WRITE_TOTAL}"
    assert set(coverage.covered_keys) == {"DB.NODE", "POST.TABLE"}


def test_p141_only_l5_passed_rows_count_in_either_bucket() -> None:
    """门槛：两个口径都**只**统计 `contract_level = L5` 且 `status = PASSED` 的去重 key。"""
    registry = _registry()
    rows = [
        _Row("DB.NODE", level="L4"),
        _Row("DB.NODE", status="FAILED"),
        _Row("DB.MATL", level="L5", status="FAILED"),
    ]
    coverage = write_path_coverage(registry, rows)
    assert coverage.covered == 0
    assert coverage.model_write_covered == 0


# ===== 4. R96：编号重新分配（离线，假传输）=====


def _r96_probe(
    transport: httpx.AsyncBaseTransport,
    *,
    templates: dict[str, WritePayloadTemplate] | None,
    allow_non_empty: bool,
    only: tuple[str, ...] = ("DB.NODE",),
) -> MidasLiveWriteProbe:
    """构造带 `allow_non_empty` 开关的探针（其余与 P139 的 `_probe` 同口径）。"""
    return MidasLiveWriteProbe(
        p139._client(transport),
        p139._registry(),
        product="GEN_NX",
        project=DedicatedTestProject(name="p141"),
        limit=0,
        only=only,
        templates=templates,
        allow_non_empty=allow_non_empty,
    )


def _stld_template() -> WritePayloadTemplate:
    """一个带前置链的模板（`DB.NODE` 引用自建的 `DB.STLD`）。"""
    return WritePayloadTemplate(
        key="DB.NODE",
        body={"X": 0.0, "Y": 0.0, "Z": 0.0},
        source="explicit_injection",
        prerequisites=(
            WritePrerequisite(key="DB.STLD", item_id="7", body={"NAME": "L"}, source="unit-test"),
        ),
    )


async def test_p141_r96_allocates_max_plus_one_on_a_non_empty_project() -> None:
    """门槛（R96）：非空项目上目标与前置都取 `max + 1`，**既有编号一字未变**。"""
    transport = p139._NxStore(
        codes=("DB.NODE", "DB.STLD"),
        initial={"DB.NODE": {"1": {"X": 1.0, "Y": 0.0, "Z": 0.0}}},
    )
    probe = _r96_probe(transport, templates={"DB.NODE": _stld_template()}, allow_non_empty=True)
    report = await probe.probe()
    outcome = report.outcomes[0]
    assert outcome.outcome == WRITE_PROBE_PASSED, outcome
    assert outcome.created_id == "2", "既有节点 1 → 目标取 2（**不**覆盖既有节点）"
    assert outcome.prerequisites == ("DB.STLD#1",), "前置编号取该端点的 max + 1（不是模板里的 7）"
    assert transport.rows["NODE"] == {"1": {"X": 1.0, "Y": 0.0, "Z": 0.0}}, "既有编号必须一字未变"
    assert transport.rows["STLD"] == {}, "自建的前置已清理"
    assert [path for _method, path, _body in transport.write_calls()] == [
        "/DB/STLD",
        "/DB/NODE",
        "/DB/NODE/2",
        "/DB/STLD/1",
    ]


async def test_p141_r96_the_default_gate_still_refuses_a_non_empty_project() -> None:
    """门槛（R96 的反面）：**默认**（`allow_non_empty=False`）仍拒绝非空项目且**零**写请求。"""
    transport = p139._NxStore(
        codes=("DB.NODE", "DB.STLD"),
        initial={"DB.NODE": {"1": {"X": 1.0, "Y": 0.0, "Z": 0.0}}},
    )
    probe = _r96_probe(transport, templates={"DB.NODE": _stld_template()}, allow_non_empty=False)
    with pytest.raises(MidasCapabilityError) as excinfo:
        await probe.probe()
    assert excinfo.value.code == "STRUCTAI-3000"
    assert excinfo.value.details["reason"] == "dedicated_test_project_not_empty"
    assert transport.write_calls() == [], "闸门拒绝时**零**写请求"


class _NoDeleteStore(p139._NxStore):
    """DELETE **不生效**的假传输（模拟「清理失败」）—— 用于验证漂移**如实**报出。"""

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            self.calls.append((request.method, request.url.path, None))
            return httpx.Response(200, json={"message": ""})
        return super()._handle(request)


async def test_p141_r96_a_leaked_id_is_reported_as_drift_not_as_passed() -> None:
    """门槛（R96 的反面）：清理失败 → 编号集合变了 → 如实 `FAILED` + `existing_id_set_changed`。"""
    transport = _NoDeleteStore(
        codes=("DB.NODE", "DB.STLD"),
        initial={"DB.NODE": {"1": {"X": 1.0, "Y": 0.0, "Z": 0.0}}},
    )
    probe = _r96_probe(transport, templates={"DB.NODE": _stld_template()}, allow_non_empty=True)
    outcome = (await probe.probe()).outcomes[0]
    assert outcome.outcome == WRITE_PROBE_FAILED, outcome
    assert outcome.detail == "existing_id_set_changed"
    assert outcome.read_back is True, "读回本身成立 —— 失败的**只是**编号集合核对"


async def test_p141_r96_without_a_template_the_chain_is_unchanged() -> None:
    """门槛：无模板（`_plan` 提前返回）→ 不引入任何额外读取，序列与 P139 完全一致。"""
    transport = p139._NxStore(codes=("DB.NODE",))
    probe = _r96_probe(transport, templates={}, allow_non_empty=False)
    outcome = (await probe.probe()).outcomes[0]
    assert outcome.outcome == WRITE_PROBE_PASSED, outcome
    assert transport.paths() == [
        "/DB/NODE",
        "/DB/ELEM",
        "/DB/MATL",
        "/DB/SECT",
        "/DB/NODE",
        "/DB/NODE",
        "/DB/NODE",
        "/DB/NODE/1",
    ]


def test_p141_r96_the_declarations_are_data_not_core() -> None:
    """门槛：编号声明**只**在数据侧（`app/**` 里 0 处引用路径字面量）。"""
    forbidden = ("DB.ELEM#1", "self_references", "id_source")
    hits: list[str] = []
    for path in sorted((REPO_ROOT / "app").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for literal in forbidden:
            if literal in text:
                hits.append(f"{path.relative_to(REPO_ROOT)}: {literal}")
    assert [hit for hit in hits if "self_references" not in hit and "id_source" not in hit] == []
    assert not any("DB.ELEM#1" in hit for hit in hits), hits


async def test_p141_r96_the_target_id_can_come_from_its_prerequisite() -> None:
    """门槛（R96 的反向依赖）：`target_id_source` 让目标取**前置**编号 —— 不撞既有编号。

    `DB.CONS` / `DB.CNLD` 的 `Assign` 键**就是**它那个节点号：若目标仍按自己端点的
    `max + 1` 取号（空表 → 1），就会去建一个**已存在**的节点（P141 实测：`400`
    `prerequisite_failed:DB.NODE#1`）。因此目标编号必须**反向**取前置编号。
    """
    transport = p139._NxStore(
        codes=("DB.NODE", "DB.STLD"),
        initial={"DB.STLD": {"1": {"NAME": "KEEP"}}},
    )
    template = WritePayloadTemplate(
        key="DB.NODE",
        body={"X": 0.0, "Y": 0.0, "Z": 0.0},
        source="explicit_injection",
        self_references=(("X",),),
        target_id_source="DB.STLD#1",
        prerequisites=(
            WritePrerequisite(key="DB.STLD", item_id="1", body={"NAME": "L"}, source="unit-test"),
        ),
    )
    probe = _r96_probe(transport, templates={"DB.NODE": template}, allow_non_empty=True)
    outcome = (await probe.probe()).outcomes[0]
    assert outcome.outcome == WRITE_PROBE_PASSED, outcome
    # 前置 `DB.STLD` 既有 1 → 分配 2；**目标编号反向取前置编号 = 2**（不是自己端点的 1）
    assert outcome.created_id == "2", "目标编号取自前置（`DB.STLD#1` 实分配 2）"
    assert outcome.prerequisites == ("DB.STLD#2",)
    assert transport.rows["STLD"] == {"1": {"NAME": "KEEP"}}, "既有编号一字未变"
    assert transport.rows["NODE"] == {}, "自建的目标已清理"
    posted = [
        body for method, path, body in transport.calls if method == "POST" and path == "/DB/NODE"
    ]
    assert posted == [{"Assign": {"2": {"X": 2, "Y": 0.0, "Z": 0.0}}}], (
        "`self_references` 必须写回**目标实分配**编号（= 前置编号 2）"
    )


def test_p141_the_data_declares_the_reverse_dependency_for_support_endpoints() -> None:
    """门槛：`DB.CONS` / `DB.CNLD`（P145 起再加 `DB.LENG` / `DB.MBTP`）的反向依赖逐条落地。"""
    from app.infrastructure.adapters.midas.write_templates import load_write_templates

    templates = load_write_templates(REPO_ROOT / "registry")
    for key in ("DB.CONS", "DB.CNLD"):
        template = templates.get(key)
        assert template is not None, key
        assert template.target_id_source == "DB.NODE#1", key
        labels = {item.label() for item in template.prerequisites}
        assert template.target_id_source in labels, key
        assert all(item.id_source == "allocated" for item in template.prerequisites), key
    expected_targets = {
        "DB.CONS": "DB.NODE#1",
        "DB.CNLD": "DB.NODE#1",
        # P145：按**构件号**取值的端点让目标自身的 `Assign` 键取**自建单元**的编号
        "DB.LENG": "DB.ELEM#1",
        "DB.MBTP": "DB.ELEM#1",
    }
    for key in templates.keys():
        assert templates.get(key).target_id_source == expected_targets.get(key, ""), key


# ===== 5. 真实实测（门控）=====


def test_p141_the_live_probe_is_skipped_without_the_documented_declaration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缺声明 → 用例 `skip`（判定只依赖环境声明，**不**回落当前项目、**不**伪造）。"""
    for name in (MIDAS_LIVE_ENV, LIVE_PROJECT_ENV, "MIDAS_BASE_URL", "MIDAS_MAPI_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert live_opt_in_from_env(os.environ) is False
    assert dedicated_test_project_from_env(os.environ) is None
    assert _live_ready() is False


@pytest.mark.skipif(
    not _live_ready(),
    reason="真实实测需 MIDAS_LIVE_L4=1 + MIDAS_LIVE_PROJECT + MIDAS_BASE_URL + MIDAS_MAPI_KEY",
)
async def test_p141_live_r96_runs_on_a_prepopulated_project_and_touches_nothing_else() -> None:
    """真实实测（R96）：**预置**最小模型 → 探针取 `max + 1` → 预置编号一字未变。

    口径：`allow_non_empty=True`（默认闸门仍要求空项目）；只碰自建编号；
    `DELETE` 必带路径 key；前后各核对一次哨兵 —— 预置模型**原样保留**，自建对象**全清**。
    """
    registry = _registry()
    credential = MidasEnvironmentCredential()
    client = MidasHttpClient(
        base_url=os.environ["MIDAS_BASE_URL"],
        credential_provider=credential,
        secret_ref="MIDAS_MAPI_KEY",
    )
    prepopulated: list[tuple[str, str]] = []
    try:
        # ① 前置：专用项目必须为空（否则**不**动它 —— 预置模型由本用例自建）
        for code in PREPOPULATED_SENTINELS:
            payload = await client.get(f"/DB/{code}")
            assert (payload.get(code) or {}) == {}, f"专用项目非空：/DB/{code}"
        # ② 预置最小模型（只碰自建 ID）
        for endpoint, item_id, body in LIVE_MODEL:
            resolved = registry.resolve(key=f"DB.{endpoint}", product="GEN_NX", method="POST")
            await client.send(
                client.build_request(
                    resolved,
                    operation="P141.LIVE.PREPARE",
                    body=body,
                    wrapper="Assign",
                    item_id=item_id,
                    allow_unverified=True,
                )
            )
            prepopulated.append((endpoint, item_id))
        before: dict[str, list[str]] = {}
        for code in PREPOPULATED_SENTINELS:
            payload = await client.get(f"/DB/{code}")
            before[code] = sorted((payload.get(code) or {}).keys())
            assert before[code], f"预置失败：/DB/{code} 仍为空"
        # ③ R96：在**非空**项目上跑（`DB.ELEM` 的前置链要建 MATL / SECT / NODE）
        probe = MidasLiveWriteProbe(
            client,
            registry,
            product="GEN_NX",
            project=dedicated_test_project_from_env(os.environ),
            only=("DB.ELEM", "DB.CONS"),
            allow_non_empty=True,
        )
        report = await probe.probe()
        assert report.counts()[WRITE_PROBE_PASSED] == 2, report.counts()
        for outcome in report.outcomes:
            assert outcome.outcome == WRITE_PROBE_PASSED, outcome
            assert outcome.read_back is True and outcome.deleted is True, outcome
            assert all(
                label.split("#")[1] not in before.get(label.split(".")[1].split("#")[0], [])
                for label in outcome.prerequisites
            ), outcome.prerequisites
        # ④ 预置编号**一字未变**；自建编号全清
        for code in PREPOPULATED_SENTINELS:
            payload = await client.get(f"/DB/{code}")
            assert sorted((payload.get(code) or {}).keys()) == before[code], f"/DB/{code} 漂移了"
    finally:
        # ⑤ 逆序清理预置模型（只删自建 ID；`DELETE` 必带路径 key）
        for endpoint, item_id in reversed(prepopulated):
            try:
                resolved = registry.resolve(key=f"DB.{endpoint}", product="GEN_NX", method="DELETE")
                await client.send(
                    client.build_request(
                        resolved, operation="P141.LIVE.CLEANUP", item_ids=(item_id,)
                    )
                )
            except Exception:  # noqa: BLE001 - 清理不得掩盖原始结论
                pass
        for code in PREPOPULATED_SENTINELS:
            payload = await client.get(f"/DB/{code}")
            assert (payload.get(code) or {}) == {}, f"清理后仍有残留：/DB/{code}"
        await client.close()


# ===== 6. ② `CONCURRENT_JOINT_FORCE` 的判别结论（P141 实测）=====

TOKEN_MISMATCH_MARKER = "error creating utbl"
"""`error creating utbl`（`ex PostMode`）= **建表阶段**失败 —— 该 token 的建表规格**没被认出来**。

P141 在**有分析结果**的模型上逐条复算（`docs/reports/P141_*.md` §5）：

| token | 状态 | 标记 | 结论 |
| --- | --- | --- | --- |
| 伪 token（对照） | `400` | **有** | 未识别 |
| `WEIGHT_IRREGULARITY_X` | `200` | 无 | **接受** |
| `STORY_SHEAR_FORCE_COEFFICIENT` | `200` | 无 | **接受** |
| `PLANESTRAINFL` · `PLANESTRESSFL` | `200` | 无 | **接受** |
| `PLANESTRAINSG` | `200` | 无 | **接受**（本模型无该结果也照样出表）|
| `CONCURRENT_JOINT_FORCE`（完整必填体） | `400` | **有** | 与伪 token **同形** → **不接受** |

⚠️ 这条结论**更正**了 P140 的措辞「需移动荷载 / 后处理模式的模型」：同一模型上
`PLANESTRAINFL`（同样缺所需结果）照样 `200`，因此差异**不在**「模型缺某类结果」，
而在**该表类型的建表规格本身**。残余假设（未排除）：该表要求某个**分析模式**开关
（`PostMode`）在模型里打开；无论哪一种，**它都没有取得 `200`**，故 R5 账上仍记为
「未正向验证」，**不**记为已判别为接受。
"""

TOKENS_ACCEPTED_BY_THIS_BUILD = (
    "WEIGHT_IRREGULARITY_X",
    "PLANESTRAINFL",
    "PLANESTRESSFL",
    "PLANESTRAINSG",
)
"""P141 实测在**最小梁模型 + 静力分析**上取得 `200` 的 token（同一模型、同一时刻）。"""

TOKEN_REJECTED_BY_THIS_BUILD = "CONCURRENT_JOINT_FORCE"
"""P141 实测与伪 token **同形**（`400` + 标记）的 token —— 本 build 不接受。"""


def test_p141_the_rejection_is_recorded_without_promoting_it_to_verified() -> None:
    """门槛：判别结论**如实**入账 —— 既不美化也不隐藏（`availability` 不动、Schema 保留）。"""
    registry = _registry()
    definition = registry.endpoint(f"POST.TABLE.{TOKEN_REJECTED_BY_THIS_BUILD}")
    assert definition.table_type == TOKEN_REJECTED_BY_THIS_BUILD
    assert definition.verification_status == "PARTIAL", "未取得 200 → 不得升级"
    # 手册来源的 Schema **保留**：它记录的是**上游规格**（`TABLE_TYPE.enum`），
    # 与「本 build 是否实现」是两件事 —— 删掉它等于抹掉上游事实。
    assert registry.schema_json(definition.key) is not None
    assert TOKEN_REJECTED_BY_THIS_BUILD in json.dumps(
        registry.schema_json(definition.key), ensure_ascii=False
    ), "手册来源的 Schema 记录的是**上游规格**（`TABLE_TYPE.enum`），必须保留"
    for token in TOKENS_ACCEPTED_BY_THIS_BUILD:
        assert registry.schema_json(f"POST.TABLE.{token}") is not None, token


@pytest.mark.skipif(
    not _live_ready(),
    reason="真实实测需 MIDAS_LIVE_L4=1 + MIDAS_LIVE_PROJECT + MIDAS_BASE_URL + MIDAS_MAPI_KEY",
)
async def test_p141_live_the_marker_discriminates_accepted_from_rejected_tokens() -> None:
    """真实实测（②）：**有结果**的最小梁模型上逐条复算判别表（只碰自建 ID）。"""
    registry = _registry()
    credential = MidasEnvironmentCredential()
    client = MidasHttpClient(
        base_url=os.environ["MIDAS_BASE_URL"],
        credential_provider=credential,
        secret_ref="MIDAS_MAPI_KEY",
    )
    created: list[tuple[str, str]] = []
    model = (
        ("SECT", "1", LIVE_MODEL_SECT),
        ("STLD", "1", {"NAME": "D", "TYPE": "D", "DESC": "DeadLoads"}),
        ("MATL", "1", LIVE_MODEL_MATL),
        ("NODE", "1", {"X": 0.0, "Y": 0.0, "Z": 0.0}),
        ("NODE", "2", {"X": 1.0, "Y": 0.0, "Z": 0.0}),
        ("ELEM", "1", {"TYPE": "BEAM", "MATL": 1, "SECT": 1, "NODE": [1, 2], "ANGLE": 0}),
        ("CONS", "1", {"ITEMS": [{"ID": 1, "GROUP_NAME": "", "CONSTRAINT": "1111000"}]}),
        ("BMLD", "1", LIVE_MODEL_BMLD),
    )
    try:
        for code in ("NODE", "ELEM", "MATL", "SECT"):
            payload = await client.get(f"/DB/{code}")
            assert (payload.get(code) or {}) == {}, f"专用项目非空：/DB/{code}"
        for endpoint, item_id, body in model:
            resolved = registry.resolve(key=f"DB.{endpoint}", product="GEN_NX", method="POST")
            await client.send(
                client.build_request(
                    resolved,
                    operation="P141.LIVE.TOKEN.CREATE",
                    body=body,
                    wrapper="Assign",
                    item_id=item_id,
                    allow_unverified=True,
                )
            )
            created.append((endpoint, item_id))
        anal = registry.resolve(key="DOC.ANAL", product="GEN_NX", method="POST")
        await client.send(
            client.build_request(
                anal,
                operation="P141.LIVE.TOKEN.ANAL",
                wrapper="Argument",
                body={},
                allow_unverified=True,
            )
        )
        secret = await credential.get_secret("MIDAS_MAPI_KEY")
        async with httpx.AsyncClient(
            base_url=os.environ["MIDAS_BASE_URL"],
            headers={"MAPI-Key": secret, "Content-Type": "application/json"},
            timeout=120.0,
        ) as raw:
            control = await raw.post(
                "/POST/TABLE", json={"Argument": {"TABLE_TYPE": "STRUCTAI_NOT_A_TABLE_TYPE"}}
            )
            assert control.status_code == 400, control.status_code
            assert TOKEN_MISMATCH_MARKER in control.text, "对照组的错误形态变了 → 判别口径失效"
            for token in TOKENS_ACCEPTED_BY_THIS_BUILD:
                response = await raw.post("/POST/TABLE", json={"Argument": {"TABLE_TYPE": token}})
                assert response.status_code == 200, (
                    token,
                    response.status_code,
                    response.text[:120],
                )
                assert TOKEN_MISMATCH_MARKER not in response.text, token
            rejected = await raw.post(
                "/POST/TABLE",
                json={
                    "Argument": {
                        "TABLE_TYPE": TOKEN_REJECTED_BY_THIS_BUILD,
                        "LOAD_CASE_NAMES": ["D"],
                        "ADDITIONAL": {
                            "SET_REACTION_PARAMS": {"NODE_KEY": 1, "COMPONENT": "111111"}
                        },
                    }
                },
            )
            assert rejected.status_code == 400, rejected.status_code
            assert TOKEN_MISMATCH_MARKER in rejected.text, (
                "若这里**没有**标记，说明本 build 已接受该 token → 必须如实更新本用例与报告"
            )
    finally:
        for endpoint, item_id in reversed(created):
            try:
                resolved = registry.resolve(key=f"DB.{endpoint}", product="GEN_NX", method="DELETE")
                await client.send(
                    client.build_request(
                        resolved, operation="P141.LIVE.TOKEN.CLEANUP", item_ids=(item_id,)
                    )
                )
            except Exception:  # noqa: BLE001 - 清理不得掩盖原始结论
                pass
        for code in ("NODE", "ELEM", "MATL", "SECT"):
            payload = await client.get(f"/DB/{code}")
            assert (payload.get(code) or {}) == {}, f"清理后仍有残留：/DB/{code}"
        await client.close()
