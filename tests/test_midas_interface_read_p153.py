"""P153 / **接口层读路径**（`MODEL.*.QUERY` / `INFO` / 取结果族）—— 端到端判据。

背景
----
P152 把**接口层**的「添加 / 删除 / 编辑」三条**写**路径经**既有 9 个 MCP Tool 契约**
跑通（`registry/live/interface_path_probe.json`：**13** 条 = **4** `PASSED` + **9**
`FAILED`）。P153 补**读**路径 —— **同一链路**（`MCP Tool → OperationPlan（operations.py）
→ Adapter（intent 分派）→ MidasHttpClient（护栏 + 包装键）→ MIDAS 实例`），但**零写请求**：
只发 `GET` 与取报表 `POST /POST/TABLE`。

本文件的判定点
--------------
1. **读路径证据**（`registry/live/interface_read_probe.json`）：**15** 条读类 Operation
   （8 个 `MODEL.*.QUERY` + `INFO` + 6 个取结果族）—— 计数 `2 PASSED / 7 PARTIAL / 6 FAILED`；
   `write_requests == 0`、`methods ⊆ {GET, POST}`、跑前 / 跑后哨兵**逐条相同**、`residue` 空、
   `aborted` 空。
2. **判据沿用 L4 口径**（`docs/04` §71）：`2xx` ∧ 解包链命中（`read_root` 在响应顶层）
   ⇒ 数据块非空 `PASSED` / **空块 `PARTIAL`**；`4xx` / 解包链不命中 ⇒ `FAILED`。
3. **逐行与 `operations.py` 复算一致**：`{tool, operation, endpoints, method, intent, uri}`
   必须等于编排里的声明（**判定点唯一** —— 端点**不**在声明里写死）。
4. **`FAILED` 行必须带原生成因**：`RESULT.*` 的 5 条 = `400` + `native_status = 400` +
   `[empty] Cannot generate table data…`；`RESULT.ANALYSIS.SUMMARY` = **零请求** +
   `STRUCTAI-3000` + **`registry_mapping_not_verified`**
   （⚠️ **P157 / R129 同步**：P153 时成因是 `endpoint_not_available_for_product`，因为
   `POST.TABLE` 的 `products` **不含** `GEN_NX`；R129 的数据更正落地后**产品闸门已通过**，
   现在的闸门是 `availability: untested`）。
5. **R126 裁决输入证据包**（`registry/live/canonical_field_gap.json`）：**71** 个模板端点
   逐条字段差集（有 Transformer **10** / 无 **61**）；**字段集缺口 4**
   （`DB.BMLD` / `DB.MATL` / `DB.PRES` / `DB.SECT`）+ **取值缺口 2**（`DB.CONS` / `DB.ELEM`）；
   P152 实测被拒的 **4** 个端点逐条在列。
6. **映射缺口分类**（`registry/live/interface_mapping_classification.json`）：缺口
   **517 = 271 + 246** 不变；**271** 个「契约外」分桶 = **0** 已有 canonical 模型 +
   **51** 有手册示例 + **220** 需产品裁决。
7. **不变量**：数据侧写路径分母**不变**（`write_path_coverage(registry, [])` = `0 / 633`、
   `model_write_ratio` = `0 / 434`）；P152 的写路径子桶（**13** = 4 + 9）与缺口
   （**517** = 271 + 246）**一行未变**；读路径判据**不**并入任何覆盖率分子。
8. **凭据绝不入证据**；**成功**响应**不留原文**（读路径只留结构形态 `kind` / `size`）。
9. **实例门控**：缺 `MIDAS_BASE_URL` / `MIDAS_MAPI_KEY` 时，真实接口层用例如实 `skip`
   （**不**失败、**不**伪造）。
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.infrastructure.adapters.midas.live import write_path_coverage
from app.infrastructure.adapters.midas.registry import MidasRegistry

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录。"""

PROBE_TOOL = REPO_ROOT / "registry" / "tools" / "probe_interface_paths.py"
"""接口层探针（写路径 `--probe` + 读路径 `--probe-read`）。"""

READ_EVIDENCE = REPO_ROOT / "registry" / "live" / "interface_read_probe.json"
"""读路径端到端证据（**15** 行；**零写请求**）。"""

WRITE_EVIDENCE = REPO_ROOT / "registry" / "live" / "interface_path_probe.json"
"""P152 写路径证据（**13** 行 = 4 + 9；本批**不得**改动）。"""

GAP_EVIDENCE = REPO_ROOT / "registry" / "live" / "interface_mapping_gap.json"
"""P152 映射缺口清单（**517** = 271 + 246；本批**不得**改动）。"""

CLASSIFICATION = REPO_ROOT / "registry" / "live" / "interface_mapping_classification.json"
"""映射缺口分类清单（P153 新增；**只登记**）。"""

FIELD_GAP = REPO_ROOT / "registry" / "live" / "canonical_field_gap.json"
"""R126 裁决输入证据包（P153 新增）。"""

CLASSIFY_TOOL = REPO_ROOT / "registry" / "tools" / "classify_mapping_gap.py"
FIELD_GAP_TOOL = REPO_ROOT / "registry" / "tools" / "check_canonical_field_gap.py"

MANIFEST_PATH = REPO_ROOT / "registry" / "manifest.json"

READ_CRITERION_VERSION = 1
EXPECTED_READ_ROWS = 15
EXPECTED_READ_COUNTS = {"PASSED": 2, "PARTIAL": 7, "FAILED": 6}
EXPECTED_READ_BY_TOOL = {
    "engineering_model_query": {"PASSED": 1, "PARTIAL": 7},
    "engineering_doc": {"PASSED": 1},
    "engineering_result": {"FAILED": 6},
}
"""读路径计数：**8** 个 `MODEL.*.QUERY` + `INFO` + **6** 个取结果族 = **15** 行。"""

EXPECTED_PASSED_OPERATIONS = ("INFO", "MODEL.QUERY")
"""非空数据块（`OPE.PROJECTSTATUS` 的项目状态表）⇒ `PASSED`。"""

EXPECTED_EMPTY_BLOCK_OPERATIONS = (
    "MODEL.BOUNDARY.QUERY",
    "MODEL.ELEMENT.QUERY",
    "MODEL.GROUP.QUERY",
    "MODEL.LOAD.QUERY",
    "MODEL.MATERIAL.QUERY",
    "MODEL.NODE.QUERY",
    "MODEL.SECTION.QUERY",
)
"""空项目上的空数据块 ⇒ `PARTIAL`（L4 口径的第三态）。"""

EXPECTED_TABLE_FAILURES = (
    "RESULT.ELEMENT.FORCE",
    "RESULT.ELEMENT.STRESS",
    "RESULT.MODE.SHAPE",
    "RESULT.NODE.DISPLACEMENT",
    "RESULT.NODE.REACTION",
)
"""空项目**没有分析结果** ⇒ 原生 `400`（逐条留原生 `error.message`）。"""

TABLE_FAILURE_MARKER = "[empty] Cannot generate table data as there is no analysis result."
"""`POST /POST/TABLE` 在无分析结果项目上的原生拒绝文案（前 200 字）。"""

SUMMARY_OPERATION = "RESULT.ANALYSIS.SUMMARY"
"""取结果族的**通用入口** `POST.TABLE`。

⚠️ **P157 同步（有实测依据）**：P153 / P154 时 `products` **不含** `GEN_NX` ⇒ 解析层拒绝
（`endpoint_not_available_for_product`）；**R129 的数据更正已落地**（补 `GEN_NX`）后
**该闸门已通过**，下一个闸门是 `availability: untested` ⇒ `registry_mapping_not_verified`
（`docs/07` §6.11：`verification_status != VERIFIED` ⇒ `RegistryMappingNotVerified`）。
"""

READ_METHODS = {"GET", "POST"}
WRITE_METHODS = {"PUT", "DELETE", "PATCH"}
TABLE_URI = "/POST/TABLE"

EXPECTED_WRITE_ROWS = 13
EXPECTED_WRITE_COUNTS = {"PASSED": 13}
"""⚠️ **P157 同步（有实测依据）**：P153 时是 `4 / 9`；P154 落地 **R126 裁决 A′** 后重测
⇒ `11 / 2`；**P157 落地 D2 = A**（`BoundaryTransformer` 加第 **7** 个自由度 `rw` ⇒ `CONSTRAINT`
输出 **7** 位）后重测 ⇒ **`13 / 0`**。断言**未**放宽，只同步数字。"""
EXPECTED_GAP_TOTAL = 489
EXPECTED_GAP_NOT_IN_CONTRACT = 243
EXPECTED_GAP_NO_READBACK = 246

EXPECTED_CLASSIFICATION = {
    "gap_total": 489,
    "gap_not_in_contract": 243,
    "gap_no_readback": 246,
}
"""**271** 个「契约外」的分类清单的顶层钉住计数。"""

EXPECTED_ADOPTION_COUNTS = {
    "adoptable_with_existing_canonical_model": 0,
    "adoptable_with_manual_example": 51,
    "needs_product_decision": 192,
}
"""**271** 个「契约外」的三分类（**离线可复算**）。"""

EXPECTED_FIELD_GAP = {
    "template_endpoints": 71,
    "with_transformer": 17,
    "without_transformer": 54,
    "field_set_gap": 3,
    "value_gap": 2,
    "no_canonical_model": 54,
    "covered": 12,
}
"""R126 裁决输入证据包的钉住计数。

⚠️ **P154 同步（有实测依据）**：P153 时是「字段集缺口 **4** / 取值缺口 **2** / 已覆盖 **4**」；
P154 落地**裁决 A′**（扩 `DB.MATL` **11** + `DB.SECT` **6** = **17** 个 canonical 字段）后重算 ⇒
「字段集缺口 **2**（`DB.BMLD` / `DB.PRES`）/ 取值缺口 **3** / 已覆盖 **5**」。

⚠️ **P157 同步（有实测依据）**：**D2 = A 落地**后接口层的 `CONSTRAINT` 由 **6** 位变 **7** 位
（= 原生要求的位数）⇒ `DB.CONS` 由 `value_gap` 移入 `covered` ⇒
「字段集缺口 **2** / 取值缺口 **2** / 已覆盖 **6**」（`template_endpoints` 仍 **71 = 10 + 61**）。
依据 = `registry/live/interface_path_probe.json`（`DB.CONS` 添加 / 删除**都** `PASSED`）+
`check_canonical_field_gap --recon` 复算。断言**未**放宽，只同步数字与注释。"""

P152_MEASURED_ENDPOINTS = ("DB.CONS", "DB.ELEM", "DB.MATL", "DB.SECT")
"""**P152 当时**实测被原生拒绝的 4 个端点（历史事实；逐条必须在证据包的 `endpoints` 里）。"""

CURRENT_MEASURED_ENDPOINTS: tuple[str, ...] = ()
"""⚠️ **P157 同步（有实测依据）**：P154 / P156 时只剩 `DB.CONS` 仍被原生拒绝（成因 = **R128**
的形状 → 取值）；**D2 = A 落地**后接口层写路径 **13 / 13 全部 `PASSED`** ⇒ 当前证据里
**没有**被原生拒绝的端点（`measured_endpoints` / `measured_rejections` 均为**空**，
由证据**复算**得出）。断言**变强**（原为「必须有拒绝」，现为「**不得**有拒绝」）。"""

FIELD_SET_GAP_ENDPOINTS = ("DB.BMLD", "DB.PRES", "DESIGN.RC.KDS-41-20-2022.DCO")
"""「二选一」方案**适用**的端点（有 Transformer ∧ 字段表表达不了手册示例的字段）。

⚠️ **P154 同步**：`DB.MATL` / `DB.SECT` 已由 **A′** 落地 ⇒ 只剩这 **2** 个
（且它们**未**实测原生拒绝，只是字段差集）。"""

VALUE_GAP_ENDPOINTS = ("DB.ELEM", "DB.MATL")
"""字段**已在** canonical 里、实测 body 里没有值 / 形态不同的端点。

⚠️ **P154 同步**：`DB.MATL` 因 A′ 后仍有两个未填的可选字段（`MASS` / `THERMAL`）而入列；
`DB.SECT` 已**全部填齐** ⇒ 移出（`covered`）。
⚠️ **P157 同步（有实测依据）**：`DB.CONS` 的取值缺口（`CONSTRAINT` 6 位 vs 模板 7 位）
**已由 D2 = A 关闭** ⇒ 移出（`covered`）。"""

EXPECTED_WRITE_PATH_TOTAL = 633
EXPECTED_MODEL_WRITE_TOTAL = 434


def _load(path: Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _probe() -> Any:
    return _load(PROBE_TOOL, "structai_probe_interface_paths_p153")


def _read_document() -> dict[str, Any]:
    return json.loads(READ_EVIDENCE.read_text(encoding="utf-8"))


def _read_rows() -> list[dict[str, Any]]:
    return list(_read_document()["paths"])


def _read_row(operation: str) -> dict[str, Any]:
    for row in _read_rows():
        if row["operation"] == operation:
            return row
    raise AssertionError(f"{operation} not in read evidence")


def _manifest_entry(key: str) -> dict[str, Any]:
    document = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for entry in document["endpoints"]:
        if str(entry["key"]) == key:
            return entry
    raise AssertionError(f"{key} not in registry/manifest.json")


def _live_ready() -> bool:
    """真实接口层探针的执行条件（`MIDAS_BASE_URL` + `MIDAS_MAPI_KEY`）。"""
    return bool((os.environ.get("MIDAS_BASE_URL") or "").strip()) and bool(
        (os.environ.get("MIDAS_MAPI_KEY") or "").strip()
    )


# ===== 1. 读路径证据：15 条读类 Operation 各取得结论（任务 1）=====


def test_p153_the_read_path_covers_every_read_class_operation() -> None:
    """门槛：**15** 条读类 Operation 逐条取得结论（PASSED / PARTIAL / FAILED）。"""
    document = _read_document()
    rows = _read_rows()
    assert document["criterion_version"] == READ_CRITERION_VERSION
    assert len(rows) == EXPECTED_READ_ROWS
    assert document["counts"] == EXPECTED_READ_COUNTS
    assert document["by_tool"] == EXPECTED_READ_BY_TOOL
    assert {str(row["operation"]) for row in rows} == {
        str(item["operation"]) for item in _probe().READ_EXERCISES
    }
    # 三个读类 Tool 都取得结论
    assert set(document["by_tool"]) == {
        "engineering_model_query",
        "engineering_doc",
        "engineering_result",
    }
    # 非空块 ⇒ PASSED；空块 ⇒ PARTIAL；原生拒绝 ⇒ FAILED
    passed = {str(row["operation"]) for row in rows if row["status"] == "PASSED"}
    partial = {str(row["operation"]) for row in rows if row["status"] == "PARTIAL"}
    failed = {str(row["operation"]) for row in rows if row["status"] == "FAILED"}
    assert passed == set(EXPECTED_PASSED_OPERATIONS), passed
    assert partial == set(EXPECTED_EMPTY_BLOCK_OPERATIONS), partial
    assert failed == set(EXPECTED_TABLE_FAILURES) | {SUMMARY_OPERATION}, failed


def test_p153_the_read_path_issues_zero_write_requests() -> None:
    """门槛：读路径**零写请求**（只发 `GET` 与取报表 `POST /POST/TABLE`）。"""
    document = _read_document()
    assert document["read_only"] is True
    assert document["write_requests"] == 0
    assert set(document["methods"]) <= READ_METHODS, document["methods"]
    for row in _read_rows():
        for item in row["requests"]:
            assert str(item["method"]) in READ_METHODS, (row["operation"], item)
            if str(item["method"]) == "POST":
                assert str(item["path"]).endswith(TABLE_URI), (row["operation"], item)


def test_p153_the_read_path_leaves_no_side_effect() -> None:
    """门槛：跑前 / 跑后只读哨兵**逐条相同**、`residue` 空、`aborted` 空。"""
    document = _read_document()
    assert document["aborted"] == ""
    assert document["residue"] == {}
    assert document["allowed_residue"] == []
    assert document["sentinel_before"] == document["sentinel_after"]
    assert tuple(document["sentinel_endpoints"]) == tuple(_probe().read_sentinel_keys(REPO_ROOT))
    for key, value in document["sentinel_before"].items():
        assert value["ids"] == [], (key, value)


# ===== 2. 逐行与 `operations.py` 复算一致（判定点唯一）=====


def test_p153_every_read_row_matches_the_operation_plan() -> None:
    """门槛：`{tool, operation, endpoints, method, intent, uri}` 逐行等于编排 + manifest。"""
    tool = _probe()
    plans = tool.operation_plans(REPO_ROOT)
    assert len(plans) == 71
    for row in _read_rows():
        operation = str(row["operation"])
        plan = plans[operation]
        assert str(plan.tool) == str(row["tool"]), operation
        endpoints = [str(step.key) for step in tool.steps_of(plan)]
        assert list(row["endpoints"]) == endpoints, operation
        assert str(row["method"]) == str(tool.steps_of(plan)[0].method), operation
        assert str(row["intent"]) == str(tool.steps_of(plan)[0].intent), operation
        entry = _manifest_entry(endpoints[0])
        assert str(row["uri"]) == "/" + str(entry["uri"]).lstrip("/"), operation
        assert [str(item["endpoint"]) for item in row["steps"]] == endpoints, operation


def test_p153_the_read_endpoints_are_not_hard_coded_in_the_declaration() -> None:
    """门槛（判定点唯一）：读类声明里**只有** Tool + Operation，端点一律由编排推导。"""
    tool = _probe()
    for exercise in tool.READ_EXERCISES:
        assert set(exercise) == {"tool", "operation"}, exercise
        assert tool.read_endpoints(REPO_ROOT, str(exercise["operation"])), exercise
    assert tool.READ_METHODS == frozenset(READ_METHODS)
    assert tool.WRITE_REQUEST_METHODS == frozenset(WRITE_METHODS)
    assert tool.TABLE_URI == TABLE_URI


# ===== 3. L4 口径：PASSED / PARTIAL / FAILED 三态逐条可复核 =====


def test_p153_every_passed_row_has_a_non_empty_unwrapped_block() -> None:
    """门槛：`PASSED` ⇒ `2xx` ∧ 解包链命中 ∧ 数据块**非空** ∧ 读回条目数 ≥ 1。"""
    for operation in EXPECTED_PASSED_OPERATIONS:
        row = _read_row(operation)
        assert row["status"] == "PASSED", operation
        assert 200 <= int(row["http"]) < 300, operation
        assert row["detail"] == "", operation
        assert row["readback"]["count"] >= 1, operation
        for step in row["steps"]:
            assert step["block"] == "nonempty", (operation, step)
            assert step["native_size"] >= 1, (operation, step)


def test_p153_every_partial_row_is_an_empty_block_on_this_project() -> None:
    """门槛：`PARTIAL` ⇒ `2xx` ∧ 解包链命中 ∧ 数据块**为空**（L4 口径的第三态）。"""
    for operation in EXPECTED_EMPTY_BLOCK_OPERATIONS:
        row = _read_row(operation)
        assert row["status"] == "PARTIAL", operation
        assert 200 <= int(row["http"]) < 300, operation
        assert row["detail"] == "empty_block", operation
        assert row["readback"]["count"] == 0, operation
        assert any(step["block"] == "empty" for step in row["steps"]), operation
        for step in row["steps"]:
            assert step["block"] in {"empty", "nonempty"}, (operation, step)
            assert step["native_size"] == 0, (operation, step)


def test_p153_every_failed_row_carries_its_native_cause() -> None:
    """门槛：`FAILED` ⇒ 有原生状态码 / 原因（**不**留空、**不**美化）。"""
    failures = [row for row in _read_rows() if row["status"] == "FAILED"]
    assert len(failures) == EXPECTED_READ_COUNTS["FAILED"]
    for row in failures:
        operation = str(row["operation"])
        assert row["detail"], operation
        error = row["error"]
        assert error, operation
        assert error["native_reason"], (operation, error)
        assert row["readback"]["intent"] == "result", operation
    # 5 条取报表：原生 400 + `[empty] Cannot generate table data…`
    for operation in EXPECTED_TABLE_FAILURES:
        row = _read_row(operation)
        assert row["detail"] == "http_400:STRUCTAI-2200", operation
        assert row["http"] == 400, operation
        assert row["error"]["native_status"] == 400, operation
        assert row["error"]["native_reason"] == "software_api_error", operation
        rejected = [item for item in row["requests"] if int(item["status"]) >= 400]
        assert rejected, operation
        assert any(
            TABLE_FAILURE_MARKER in str(item.get("native_error") or "") for item in rejected
        ), operation


def test_p153_the_generic_table_entry_is_blocked_by_its_verification_status() -> None:
    """门槛（⚠️ **P157 / R129 同步，有实测依据**）：通用入口 `POST.TABLE` 的闸门**已前移一位**。

    P153 / P154 时 `products` **不含** `GEN_NX` ⇒ 解析层拒绝
    （`endpoint_not_available_for_product`）。
    **R129 的数据更正已落地**（`registry/common/post/TABLE.yaml` 的 `products` 补 `GEN_NX`，
    `sync_manifest` 复算差异 **1 → 0**）⇒ **产品闸门已通过**；现在的成因是
    `availability: untested` ⇒ **`registry_mapping_not_verified`**（`docs/07` §6.11）。
    ⚠️ 判定**未**放宽：仍是 `FAILED` + **零** transport 调用（**不**发请求）+ 原生原因**逐条**留证。
    """
    row = _read_row(SUMMARY_OPERATION)
    assert row["status"] == "FAILED", row
    assert row["http"] == 0, row
    assert row["requests"] == [], row
    assert row["detail"] == "no_interface_request:STRUCTAI-3000", row
    assert row["error"]["code"] == "STRUCTAI-3000", row
    assert row["error"]["native_reason"] == "registry_mapping_not_verified", row
    # ⚠️ **R129 已落地**：`products` **现在**含 `GEN_NX`（产品闸门不再是成因）
    entry = _manifest_entry("POST.TABLE")
    assert "GEN_NX" in [str(item) for item in entry["products"]], entry
    assert str(entry["availability"]) == "untested", entry


# ===== 4. 凭据 / 响应原文（判定 8）=====


def test_p153_the_read_evidence_never_carries_credentials_or_response_text() -> None:
    """门槛（`docs/07` §14.3）：无凭据形态；成功响应**不留原文**（只留结构形态）。"""
    raw = READ_EVIDENCE.read_text(encoding="utf-8")
    for marker in ("MAPI-Key", "MAPI_KEY", "mapi-key", "password", "secret"):
        assert marker not in raw, marker
    for row in _read_rows():
        for item in row["requests"]:
            if int(item["status"]) < 400:
                assert "native_error" not in item, (row["operation"], item)
                shape = item.get("shape")
                if shape is None:
                    continue
                # 结构形态**只**允许 `kind` / `size`
                for value in shape.values():
                    assert set(value) == {"kind", "size"}, (row["operation"], value)
                    assert value["kind"] in {"mapping", "list", "scalar"}, value
            else:
                assert len(str(item.get("native_error") or "")) <= 200, item


# ===== 5. R126 的裁决输入证据包（任务 2）=====


def test_p153_the_canonical_field_gap_pack_is_recomputable() -> None:
    """门槛：R126 证据包与 `transforms.py` / `operations.py` / 模板 / P152 证据逐条一致。"""
    tool = _load(FIELD_GAP_TOOL, "structai_field_gap_p153")
    document = json.loads(FIELD_GAP.read_text(encoding="utf-8"))
    fresh = tool.build_document(REPO_ROOT)
    for key, expected in EXPECTED_FIELD_GAP.items():
        assert int(document["summary"][key]) == expected, (key, document["summary"][key])
        assert int(fresh["summary"][key]) == expected, (key, fresh["summary"][key])
    for key in (
        "summary",
        "buckets",
        "options",
        "value_gaps",
        "no_canonical_model_inventory",
        "measured_rejections",
        "measured_endpoints",
        "newly_discovered",
        "endpoints",
    ):
        assert document[key] == fresh[key], key


def test_p153_the_field_gap_pack_pins_the_p152_measured_endpoints() -> None:
    """门槛：P152 实测被拒的 **4** 个端点逐条在列，且各带接口层实测 body。

    ⚠️ **P154 同步**：`gap_class` 允许 `covered` —— `DB.SECT` 的字段集缺口已由 **A′** 关闭，
    且接口层实测 body 已把 6 个 `SECT_BEFORE.*` 填齐（**判定变强**，不是放宽）。
    """
    document = json.loads(FIELD_GAP.read_text(encoding="utf-8"))
    assert tuple(document["measured_endpoints"]) == CURRENT_MEASURED_ENDPOINTS
    index = {str(row["endpoint"]): row for row in document["endpoints"]}
    for endpoint in P152_MEASURED_ENDPOINTS:
        row = index[endpoint]
        assert row["has_transformer"] is True, endpoint
        assert row["interface_body"] is not None, endpoint
        assert row["gap_class"] in {"field_set_gap", "value_gap", "covered"}, endpoint
    # 原生拒绝逐条留证（⚠️ **P154 / P155 / P156 / P157 同步**：证据包由**当前**证据复算 ⇒
    # P155 修好**形状**后 `DB.CONS` 的文案已下沉到**取值级**「约束条件输入有错误」；
    # **P157 落地 D2 = A** 后该文案**消失**（`DB.CONS` 添加 / 删除**都** `PASSED`）⇒
    # 当前复算清单里**没有**原生拒绝。P152 当时的 `Wrong Field` / `Unknown Error` 与 P156 的
    # 「约束条件输入有错误」是**历史事实**，保留在 `docs/reports/P153_*.md` §2.4、
    # `docs/reports/P154_*.md` §3、`docs/reports/P156_*.md` §1.2 与 `docs/07` §16.1 的 R126 行，
    # **不**在本复算清单里。⚠️ 判定**变强**：原为「必须有拒绝」，现为「**不得**有拒绝」。)
    assert document["measured_rejections"] == [], document["measured_rejections"]
    assert document["measured_endpoints"] == [], document["measured_endpoints"]


def test_p153_the_two_options_are_scoped_to_the_field_set_gap() -> None:
    """门槛：「扩 canonical / 补原生默认值」**二选一**只覆盖字段集缺口端点。"""
    document = json.loads(FIELD_GAP.read_text(encoding="utf-8"))
    options = document["options"]
    assert tuple(options["A_extend_canonical_field_set"]["endpoints"]) == FIELD_SET_GAP_ENDPOINTS
    assert tuple(options["B_allow_native_defaults"]["endpoints"]) == FIELD_SET_GAP_ENDPOINTS
    assert tuple(document["buckets"]["field_set_gap"]) == FIELD_SET_GAP_ENDPOINTS
    assert tuple(document["buckets"]["value_gap"]) == VALUE_GAP_ENDPOINTS
    # 方案 B 的每个字段都必须给出**手册示例**里的取值来源（**不**臆造）
    for endpoint, fields in options["B_allow_native_defaults"]["per_endpoint"].items():
        assert fields, endpoint
        for field in fields:
            assert field["native"], (endpoint, field)
            assert "manual_example_value" in field, (endpoint, field)
    # 取值缺口**不**并入二选一（⚠️ P154：`DB.SECT` 已填齐 ⇒ 移出；`DB.MATL` 入列）
    assert set(document["value_gaps"]) == set(VALUE_GAP_ENDPOINTS)
    # 无 canonical 模型的端点清单 = 61（与 summary 一致）
    assert (
        len(document["no_canonical_model_inventory"]) == EXPECTED_FIELD_GAP["without_transformer"]
    )
    # `DB.ELEM` 的缺口是**取值**（字段可表达）—— A′ 后 `MATL` / `SECT` 已由接口层实测填上
    index = {str(row["endpoint"]): row for row in document["endpoints"]}
    assert index["DB.ELEM"]["missing_in_canonical"] == []
    assert set(index["DB.ELEM"]["unfilled_expressible"]) == {"ANGLE"}
    # `DB.MATL` / `DB.SECT` 的字段集缺口已由 **A′** 关闭（17 个字段逐条可表达）
    assert index["DB.MATL"]["missing_in_canonical"] == []
    assert index["DB.SECT"]["missing_in_canonical"] == []
    assert index["DB.SECT"]["gap_class"] == "covered"
    # `DB.CONS` 的 `CONSTRAINT` 由 Transformer **合成**（不在字段表里）⇒ **不**算字段集缺口
    assert index["DB.CONS"]["missing_in_canonical"] == []
    assert "CONSTRAINT" in index["DB.CONS"]["synthesized_keys"]
    # ⚠️ **P157 同步（有实测依据）**：**D2 = A 落地**后接口层产出 **7** 位 ⇒ `DB.CONS` 的
    # 取值缺口**已关闭**（`covered`）—— 原用例钉住的是「interface 6 ≠ template 7」的**不一致**，
    # 现在改为**更强**的判定：接口层实测 body 的 `CONSTRAINT` **恰好等于**原生要求的 **7** 位。
    assert index["DB.CONS"]["gap_class"] == "covered"
    assert "DB.CONS" not in document["value_gaps"]
    write_document = json.loads(WRITE_EVIDENCE.read_text(encoding="utf-8"))
    boundary_add = next(
        row
        for row in write_document["paths"]
        if row["path"] == "add" and str(row["endpoint"]) == "DB.CONS"
    )
    bodies = [
        item["body"]
        for item in boundary_add["requests"]
        if item["method"] == "POST" and str(item["path"]).endswith("/DB/CONS")
    ]
    entry = bodies[0]["Assign"][next(iter(bodies[0]["Assign"]))]["ITEMS"][0]
    assert len(str(entry["CONSTRAINT"])) == 7, entry
    assert str(entry["CONSTRAINT"]) == "1110000", entry


# ===== 6. 映射缺口 517 的分类收口（任务 3）=====


def test_p153_the_mapping_gap_classification_is_recomputable() -> None:
    """门槛：分类清单与 `mapping_gap()` / YAML / `transforms.py` 逐条一致。"""
    tool = _load(CLASSIFY_TOOL, "structai_classify_gap_p153")
    document = json.loads(CLASSIFICATION.read_text(encoding="utf-8"))
    fresh = tool.classify(REPO_ROOT)
    for key, expected in EXPECTED_CLASSIFICATION.items():
        assert int(document[key]) == expected, (key, document[key])
        assert int(fresh[key]) == expected, (key, fresh[key])
    for key, expected in EXPECTED_ADOPTION_COUNTS.items():
        assert int(document["adoption_counts"][key]) == expected, (
            key,
            document["adoption_counts"][key],
        )
        assert int(fresh["adoption_counts"][key]) == expected, (key, fresh["adoption_counts"][key])
    for key in (
        "buckets",
        "adoption_counts",
        "adoptable",
        "adoptable_with_manual_example",
        "needs_product_decision",
        "endpoints",
    ):
        assert document[key] == fresh[key], key


def test_p153_the_classification_does_not_move_the_gap_counts() -> None:
    """门槛：**517 = 271 + 246** 与 P152 的缺口清单**逐条**一致（本批只登记）。"""
    document = json.loads(CLASSIFICATION.read_text(encoding="utf-8"))
    gap = json.loads(GAP_EVIDENCE.read_text(encoding="utf-8"))
    assert int(gap["gap_total"]) == EXPECTED_GAP_TOTAL
    assert len(gap["gap_three_step"]) == EXPECTED_GAP_NOT_IN_CONTRACT
    assert len(gap["gap_no_readback"]) == EXPECTED_GAP_NO_READBACK
    assert int(document["gap_total"]) == EXPECTED_GAP_TOTAL
    assert int(document["gap_not_in_contract"]) == EXPECTED_GAP_NOT_IN_CONTRACT
    assert int(document["gap_no_readback"]) == EXPECTED_GAP_NO_READBACK
    assert {str(row["key"]) for row in document["endpoints"]} == {
        str(row["key"]) for row in gap["gap_three_step"]
    }
    # 三类互斥且覆盖全部
    adoptable = {str(row["key"]) for row in document["adoptable"]}
    manual = {str(row["key"]) for row in document["adoptable_with_manual_example"]}
    needs = {str(row["key"]) for row in document["needs_product_decision"]}
    assert not (adoptable & manual) and not (adoptable & needs) and not (manual & needs)
    assert len(adoptable | manual | needs) == EXPECTED_GAP_NOT_IN_CONTRACT
    # 每个契约外端点都带 `{key, uri, methods, read_root, availability, reason}`
    for row in document["endpoints"]:
        assert row["key"] and row["uri"].startswith("/") and row["methods"]
        assert row["read_root"], row
        assert "GET" in row["methods"], row
        assert row["capability"], row
        assert row["adoption"] in {
            "adoptable_with_existing_canonical_model",
            "adoptable_with_manual_example",
            "needs_product_decision",
        }


def test_p153_the_classification_buckets_by_namespace_capability_and_tool() -> None:
    """门槛：按命名空间 / 能力码 / Tool 归属分桶（逐条可复核）。"""
    document = json.loads(CLASSIFICATION.read_text(encoding="utf-8"))
    buckets = document["buckets"]
    assert buckets["by_namespace"] == {"DB": 172, "DESIGN": 68, "OPE": 3}
    assert buckets["by_capability"] == {"DELETE": 158, "DESIGN": 68, "MODEL": 175, "OPERATION": 3}
    assert buckets["by_tool_map"] == {"assign": 242, "delete": 158, "query": 243}
    assert buckets["by_readiness"] == {
        "manual_example_ready": 51,
        "no_request_schema": 1,
        "schema_only": 191,
    }
    assert buckets["by_availability"] == {"verified": 243}
    # 分桶之和自洽：命名空间 = 契约外条数
    assert sum(buckets["by_namespace"].values()) == EXPECTED_GAP_NOT_IN_CONTRACT
    assert sum(buckets["by_adoption"].values()) == EXPECTED_GAP_NOT_IN_CONTRACT


# ===== 7. 不变量（本批**不得**改动既有钉住计数）=====


def test_p153_the_invariants_are_untouched() -> None:
    """门槛：写路径分母 / P152 的写路径子桶与缺口**一行未变**。"""
    registry = MidasRegistry.load(REPO_ROOT / "registry")
    coverage = write_path_coverage(registry, [])
    assert coverage.ratio == f"0 / {EXPECTED_WRITE_PATH_TOTAL}"
    assert coverage.model_write_ratio == f"0 / {EXPECTED_MODEL_WRITE_TOTAL}"
    write_document = json.loads(WRITE_EVIDENCE.read_text(encoding="utf-8"))
    assert len(write_document["paths"]) == EXPECTED_WRITE_ROWS
    assert write_document["counts"] == EXPECTED_WRITE_COUNTS
    assert write_document["residue"] == {}
    # 读路径证据**不**并入任何覆盖率口径（两个证据文件互不引用对方的计数键）
    read_document = _read_document()
    for key in ("ratio", "model_write_ratio", "coverage", "numerator"):
        assert key not in read_document, key
    assert "paths" in read_document and "counts" in read_document


# ===== 8. 离线复算入口（CI）=====


def test_p153_the_check_modes_agree_offline() -> None:
    """门槛：三个工具的 `--check` 离线跑通（退出码 0）—— CI 的复算入口。"""
    for tool in (PROBE_TOOL, CLASSIFY_TOOL, FIELD_GAP_TOOL):
        result = subprocess.run(
            [sys.executable, str(tool), "--check"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0, tool.name + result.stdout + result.stderr
        assert "✅" in result.stdout, tool.name + result.stdout


# ===== 9. 实例门控（真实接口层探针）=====


def test_p153_the_live_read_probe_is_skipped_without_the_documented_declaration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛（`docs/04` §71–§72）：缺环境声明 ⇒ 真实用例如实 `skip`（**不**失败、**不**伪造）。"""
    for name in ("MIDAS_BASE_URL", "MIDAS_MAPI_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert _live_ready() is False


@pytest.mark.skipif(
    not _live_ready(),
    reason="真实接口层探针需 MIDAS_BASE_URL + MIDAS_MAPI_KEY（见 scripts/load-midas-env.ps1）",
)
def test_p153_the_live_read_probe_is_bounded_and_read_only() -> None:
    """门槛：读路径探针**有界**（分块 ≤ 20 + 块间只读健康检查）且**只**发 `GET` / 取报表 `POST`。

    ⚠️ 本用例**不**重跑请求（真实读路径已由 `--probe-read` 落证据）；它只断言
    「探针的纪律参数可被读出」—— 避免 CI 里对实例重复施加请求压力。
    """
    tool = _probe()
    assert tool.CHUNK_SIZE <= 20
    assert tool.HEALTH_PATH == "/DB/NODE"
    assert tool.READ_METHODS == frozenset(READ_METHODS)
    assert tool.WRITE_REQUEST_METHODS == frozenset(WRITE_METHODS)
    assert tool.TABLE_URI == TABLE_URI
    assert tool.READ_EVIDENCE_RELATIVE == "live/interface_read_probe.json"
    for exercise in tool.READ_EXERCISES:
        assert exercise["tool"] in {
            "engineering_model_query",
            "engineering_doc",
            "engineering_result",
        }
        assert exercise["operation"] in tool.operation_plans(REPO_ROOT)
