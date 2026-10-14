"""P152 / **接口层**（`app/` 适配层）的「添加 / 删除 / 编辑」三条路径 —— 端到端判据。

背景
----
P139–P151 的写路径判据**全部**绕开 `app/`（模板 / 前置链 / 编号分配都在数据侧探针里实现，
`app/` 一行未改）。用户口径（`docs/08` §4）：接口层与数据侧**解耦**，故本批（P152）起
开始**接口层**调试 —— 走**既有 9 个 MCP Tool 契约**：

    MCP Tool → OperationPlan（`operations.py`）→ Adapter（intent 分派）
        → MidasHttpClient（护栏 + 包装键）→ MIDAS 实例

本文件的判定点
--------------
1. **端到端证据**（`registry/live/interface_path_probe.json`）：**13** 条路径 ——
   **4** `PASSED` + **9** `FAILED`；三条路径（添加 / 编辑 / 删除）**各至少一条** `PASSED`；
   `aborted` 空、`residue` 空（**零残留**）。
2. **逐行与 `operations.py` 复算一致**：`{tool, operation, endpoint, method, uri}` 必须等于
   编排里的声明（**判定点唯一** —— 工具不另写一份映射规则）。
3. **`PASSED` 行必须六步齐全**：只读侦察确认解包链 → 创建 `2xx` → 读回在 →（编辑）改动
   **生效** → 删除**带路径 key** → 再读确认消失。
4. **`FAILED` 行必须带原生成因**：`native_status` / `native_reason` 或前置创建失败的原因
   （**不**留空、**不**美化）。
5. **映射缺口**（`registry/live/interface_mapping_gap.json`）：**离线可复算**，
   `gap_total = 511 = 265（契约外）+ 246（无读回）`。
6. **不变量**：数据侧写路径分母**不变**（`write_path_coverage(registry, [])` = `0 / 633`、
   `model_write_ratio` = `0 / 434`）；接口层判据**不**并入任何数据侧覆盖率分子。
7. **凭据绝不入证据**；成功响应**不**留原文（只有失败响应留 `error.message` 前 200 字）。
8. **实例门控**：缺 `MIDAS_BASE_URL` / `MIDAS_MAPI_KEY` 时，真实接口层用例如实 `skip`
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

TOOL_PATH = REPO_ROOT / "registry" / "tools" / "probe_interface_paths.py"
"""接口层探针（`--recon` / `--probe` / `--check` / `--summary`）。"""

EVIDENCE_PATH = REPO_ROOT / "registry" / "live" / "interface_path_probe.json"
"""接口层端到端证据（**13** 行；**不含**凭据、成功响应**不含**原文）。"""

GAP_PATH = REPO_ROOT / "registry" / "live" / "interface_mapping_gap.json"
"""映射缺口清单（离线可复算：`registry/` ∪ `operations.py`）。"""

MANIFEST_PATH = REPO_ROOT / "registry" / "manifest.json"

CRITERION_VERSION = 1
EXPECTED_ROWS = 13
EXPECTED_COUNTS = {"PASSED": 13}
"""⚠️ **P157 同步（有实测依据）**：P152 当时是 `4 / 9`；P154 落地 **R126 裁决 A′**（扩
`DB.MATL` 11 + `DB.SECT` 6 = **17** 个 canonical 字段）+ 修探针的节点几何（两节点坐标必须不同）
+ 补 `DB.CONS` 的 `group_name` 后重测 ⇒ **`11 / 2`**；**P157 落地 D2 = A**（`BoundaryTransformer`
加第 **7** 个自由度 `rw` ⇒ `CONSTRAINT` 输出 **7** 位，与原生要求一致）后重测 ⇒ **`13 / 0`**
（`registry/live/interface_path_probe.json`，零残留、未中止）。断言**未**放宽，只同步数字。"""
EXPECTED_BY_PATH = {
    "add": {"PASSED": 5},
    "edit": {"PASSED": 2},
    "delete": {"PASSED": 6},
}
EXPECTED_PASSED = (
    ("add", "DB.CONS"),
    ("add", "DB.ELEM"),
    ("add", "DB.MATL"),
    ("add", "DB.NODE"),
    ("add", "DB.SECT"),
    ("delete", "DB.CONS"),
    ("delete", "DB.ELEM"),
    ("delete", "DB.GRUP"),
    ("delete", "DB.MATL"),
    ("delete", "DB.NODE"),
    ("delete", "DB.SECT"),
    ("edit", "DB.ELEM"),
    ("edit", "DB.NODE"),
)
"""本批**全部** `PASSED` 行（添加 / 编辑 / 删除三条路径各有证据）。"""

EXPECTED_ENDPOINTS = ("DB.CONS", "DB.ELEM", "DB.GRUP", "DB.MATL", "DB.NODE", "DB.SECT")
"""哨兵端点集 = **全部**被触碰的端点（跑前 / 跑后只读 `GET`）。"""

EXPECTED_GAP_COUNTS = {
    "operations": 71,
    "write_capable_endpoints": 556,
    "three_step_endpoints": 280,
    "mapped_endpoints": 68,
    "mapped_inside_three_step": 37,
    "gap_total": 489,
}
"""映射缺口的钉住计数（离线复算；见 `--recon`）。

⚠️ **P157 / R129 同步（有实测依据）**：`POST.TABLE` 的 `products` 补 `GEN_NX` 后成为 GEN_NX 的
**可写端点** ⇒ `write_capable_endpoints` **576 → 577**（`POST.TABLE` 是 `POST` 端点）。
⚠️ **缺口总数 517 → 511**（**511 = 265 + 246**，P157 / R136）；
`three_step_endpoints` **不变**、`mapped_endpoints` **61 → 67**（+6 个荷载组合）。
"""

EXPECTED_GAP_THREE_STEP = 243
"""缺口里的「契约外」条数（形态齐备但没有任何 Operation 映射到它）。"""

EXPECTED_GAP_NO_READBACK = 246
"""缺口里的「无读回」条数（没有 `GET` 或没有 `read_root`）。"""

EXPECTED_WRITE_PATH_TOTAL = 633
"""数据侧写路径分母（`docs/07` §16 R4 / R14 的 633；本批**不得**改动）。"""

EXPECTED_MODEL_WRITE_TOTAL = 434
"""`model_write` 分母（本批**不得**改动）。"""

FAILED_NATIVE_MARKERS = ("Wrong Field", "Unknown Error", "约束条件输入有错误")
"""原生拒绝文案的词表（逐条进证据的 `native_error`）。

⚠️ **P154 / P155 / P156 / P157 同步**：R126 的 A′ 落地后只剩 `DB.CONS` 一条；P155 修好**形状**
（外层编号键）后，`DB.CONS` 的原生文案从 `Wrong Field`（**形状级**）变成
**`约束条件输入有错误。`**（**取值级** = `CONSTRAINT` 必须是 **7** 位）；**P157 落地 D2 = A**
（`BoundaryTransformer` 加第 7 个自由度 `rw`）后，原生拒绝**清零** ⇒ 本词表保留为**守卫词表**
（一旦某行再出现这些文案，用例**立刻**失败）。断言**未**放宽（由「失败行必须命中词表」
**收紧**为「**没有**失败行、**没有**拒绝文案」）。"""


def _load(path: Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tool() -> Any:
    return _load(TOOL_PATH, "structai_probe_interface_paths_p152")


def _evidence() -> dict[str, Any]:
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def _gap() -> dict[str, Any]:
    return json.loads(GAP_PATH.read_text(encoding="utf-8"))


def _rows() -> list[dict[str, Any]]:
    return list(_evidence()["paths"])


def _row(path: str, endpoint: str) -> dict[str, Any]:
    for row in _rows():
        if row["path"] == path and row["endpoint"] == endpoint:
            return row
    raise AssertionError(f"{path}/{endpoint} not in evidence")


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


# ===== 1. 端到端证据：三条路径各有结论（本轮任务 1）=====


def test_p152_the_three_paths_are_exercised_through_the_mcp_contract() -> None:
    """门槛：**13** 条路径 —— 添加 / 编辑 / 删除**各至少一条** `PASSED`（任务 1 的硬要求）。"""
    document = _evidence()
    rows = _rows()
    assert document["criterion_version"] == CRITERION_VERSION
    assert len(rows) == EXPECTED_ROWS
    assert document["counts"] == EXPECTED_COUNTS
    assert document["by_path"] == EXPECTED_BY_PATH
    assert document["aborted"] == "", "跑前哨兵非空会中止 ⇒ 本批必须没有中止"
    assert document["residue"] == {}, "本批**零残留**（自建编号已逐条再读确认不在）"
    assert document["allowed_residue"] == []
    # 三条路径各至少一条 PASSED
    passed_paths = {str(row["path"]) for row in rows if row["status"] == "PASSED"}
    assert passed_paths == {"add", "edit", "delete"}, passed_paths
    assert {
        (str(row["path"]), str(row["endpoint"])) for row in rows if row["status"] == "PASSED"
    } == set(EXPECTED_PASSED)


def test_p152_the_sentinel_covers_every_touched_endpoint() -> None:
    """门槛：跑前 / 跑后只读哨兵覆盖**全部**被触碰的端点（6 个），且都读得回。"""
    document = _evidence()
    assert tuple(document["sentinel_endpoints"]) == EXPECTED_ENDPOINTS
    for snapshot in (document["sentinel_before"], document["sentinel_after"]):
        assert sorted(snapshot) == list(EXPECTED_ENDPOINTS)
        for key, value in snapshot.items():
            assert value["status"] == 200, (key, value)
            assert value["ids"] == [], (key, value)
    assert document["sentinel_before"] == document["sentinel_after"]


# ===== 2. 逐行与 `operations.py` 复算一致（判定点唯一）=====


def test_p152_every_row_matches_the_operation_plan() -> None:
    """门槛：`{tool, operation, endpoint, method, uri}` 逐行等于 `operations.py` + manifest。"""
    tool = _tool()
    plans = tool.operation_plans(REPO_ROOT)
    mapped = tool.mapped_endpoints(REPO_ROOT)
    assert len(plans) == 71
    for row in _rows():
        endpoint = str(row["endpoint"])
        operation = str(row["operation"])
        plan = plans[operation]
        assert str(plan.tool) == str(row["tool"]), (endpoint, operation)
        step = next((item for item in tool.steps_of(plan) if str(item.key) == endpoint), None)
        assert step is not None, (endpoint, operation)
        assert str(step.method) == str(row["method"]), (endpoint, operation)
        assert endpoint in mapped, endpoint
        entry = _manifest_entry(endpoint)
        assert str(row["uri"]) == "/" + str(entry["uri"]).lstrip("/"), endpoint
        # 该端点在编排里的 tool 必须与**路径声明**一致（`--check` 的同一判定）
        assert str(plan.tool) == tool.TOOL_BY_OPERATION_PATH[str(row["path"])], endpoint


def test_p152_the_declarations_do_not_duplicate_the_mapping_rules() -> None:
    """门槛（判定点唯一）：工具里的**声明**表必须与 `operations.py` 的编排**逐条**一致。"""
    tool = _tool()
    plans = tool.operation_plans(REPO_ROOT)
    for endpoint, operation in tool.CREATE_OPERATION_BY_ENDPOINT.items():
        plan = plans[operation]
        step = next((item for item in tool.steps_of(plan) if str(item.key) == endpoint), None)
        assert step is not None, (endpoint, operation)
        assert str(step.method) in {"POST", "PUT"}, (endpoint, operation)
        assert str(step.intent).startswith("write_"), (endpoint, operation)
    for endpoint, operation in tool.DELETE_OPERATION_BY_ENDPOINT.items():
        plan = plans[operation]
        step = next((item for item in tool.steps_of(plan) if str(item.key) == endpoint), None)
        assert step is not None, (endpoint, operation)
        assert str(step.method) == "DELETE", (endpoint, operation)
        assert str(step.intent).startswith("delete_"), (endpoint, operation)
    # 三条路径的 Tool 划分也必须与编排一致
    for path, name in tool.TOOL_BY_OPERATION_PATH.items():
        assert name in {str(plan.tool) for plan in plans.values()}, path


# ===== 3. `PASSED` 行：六步齐全（判定 2 / 3）=====


def test_p152_every_passed_row_carries_the_full_chain() -> None:
    """门槛：`PASSED` ⇒ 侦察确认解包链 ∧ 创建 `2xx` ∧ 读回在 ∧（编辑）生效 ∧ 删除确认。"""
    for row in _rows():
        if row["status"] != "PASSED":
            continue
        endpoint = str(row["endpoint"])
        assert row["own_id"], endpoint
        recon = row["recon"]
        assert recon["read_root_present"] is True, endpoint
        assert recon["method_allowed"] is True, endpoint
        assert recon["get_status"] == 200, endpoint
        # 创建：经接口层；删除路径的前置创建同样必须成功
        write = row["write"]
        create_status = write.get("create_http") or write.get("http")
        assert 200 <= int(create_status) < 300, (endpoint, write)
        if row["path"] != "delete":
            assert row["readback"]["present"] is True, endpoint
            assert row["readback"]["observed"]["id"] == row["own_id"], endpoint
        if row["path"] == "edit":
            assert row["edit"]["effective"] is True, endpoint
            assert row["edit"]["observed"][row["edit"]["field"]] == row["edit"]["expected"], (
                endpoint
            )
        cleanup = row["cleanup"]
        assert cleanup["gone"] is True, endpoint
        assert cleanup["attempts"] >= 1, endpoint
        # 删除**必带路径 key**（`docs/07` §6.4）
        deletes = [item for item in row["requests"] if item["method"] == "DELETE"]
        assert deletes, endpoint
        assert any(str(item["path"]).endswith(f"/{row['own_id']}") for item in deletes), (
            endpoint,
            deletes,
        )


def test_p152_the_requests_are_recorded_verbatim_for_the_interface_layer() -> None:
    """门槛：逐行记**接口层实际发出**的请求（method + path + 请求体），且与声明一致。"""
    for row in _rows():
        assert row["requests"], (row["path"], row["endpoint"])
        for item in row["requests"]:
            assert str(item["path"]).startswith("/"), item
            assert int(item["status"]) > 0, item
            if item["method"] in {"POST", "PUT"}:
                assert isinstance(item.get("body"), dict), item
        if row["status"] != "PASSED":
            continue
        # `PASSED` 行必须真的发出过该路径声明的方法（添加 = POST / 编辑 = PUT / 删除 = DELETE）
        methods = {str(item["method"]) for item in row["requests"]}
        assert str(row["method"]) in methods, (row["endpoint"], methods)


# ===== 4. `FAILED` 行：原生成因逐条留证（判定 4）=====


def test_p152_every_failed_row_carries_its_native_cause() -> None:
    """门槛：`FAILED` ⇒ 有原生状态码 / 原因（或前置创建失败的原因），**不**留空。

    ⚠️ **P157 同步（有实测依据）**：**D2 = A** 落地后 `DB.CONS` 的添加 / 删除**都** `PASSED`
    ⇒ 证据里**没有** `FAILED` 行，本用例的逐行断言在**零失败**时空转，但**判定保留**
    （一旦再出现失败行，仍**逐条**要求原生成因）。断言**未**放宽。
    """
    failures = [row for row in _rows() if row["status"] == "FAILED"]
    assert len(failures) == EXPECTED_COUNTS.get("FAILED", 0)
    for row in failures:
        endpoint = str(row["endpoint"])
        assert row["detail"], endpoint
        error = (row["write"] or {}).get("error") or {}
        assert error, (endpoint, row["write"])
        assert error.get("code") == "STRUCTAI-2200", (endpoint, error)
        assert error.get("native_status") == 400, (endpoint, error)
        assert error.get("native_reason") == "software_api_error", (endpoint, error)
        # 原生拒绝文案逐条进证据（诊断必需；与数据侧探针同一口径）
        rejected = [item for item in row["requests"] if int(item["status"]) >= 400]
        assert rejected, endpoint
        assert any(str(item.get("native_error") or "") for item in rejected), endpoint


def test_p152_the_native_rejections_are_the_recorded_ones() -> None:
    """门槛：**本批起零原生拒绝** —— 13 条**全部** `PASSED`，证据里**没有**任何拒绝文案。

    ⚠️ **P157 同步（有实测依据）**：P154 / P156 时只剩 `DB.CONS` 一条（成因 = 取值
    `CONSTRAINT` 必须是 **7** 位）；**D2 = A 落地**后 `POST /DB/CONS` 返回 **`200` 且落库**
    ⇒ 拒绝集**清空**。⚠️ 判定**变强**（原为「失败行必须命中拒绝词表」，现为
    「**没有**失败行、**没有**拒绝文案」）。
    """
    texts = {
        str(item.get("native_error") or "")
        for row in _rows()
        for item in row["requests"]
        if item.get("native_error")
    }
    assert texts == set(), texts
    assert not any(marker in text for text in texts for marker in FAILED_NATIVE_MARKERS), texts
    assert {row["status"] for row in _rows()} == {"PASSED"}, _rows()


# ===== 5. 映射缺口：离线可复算（本轮任务 2）=====


def test_p152_the_mapping_gap_is_recomputable_offline() -> None:
    """门槛：缺口清单与 `registry/` ∪ `operations.py` 的**离线**复算逐条一致。"""
    tool = _tool()
    document = _gap()
    fresh = tool.mapping_gap(REPO_ROOT)
    assert document["criterion_version"] == CRITERION_VERSION
    for key, expected in EXPECTED_GAP_COUNTS.items():
        assert int(document[key]) == expected, (key, document[key])
        assert int(fresh[key]) == expected, (key, fresh[key])
    assert document["gap_three_step"] == fresh["gap_three_step"]
    assert document["gap_no_readback"] == fresh["gap_no_readback"]
    assert document["mapped"] == fresh["mapped"]
    assert len(document["gap_three_step"]) == EXPECTED_GAP_THREE_STEP
    assert len(document["gap_no_readback"]) == EXPECTED_GAP_NO_READBACK
    # 缺口的 reason 取值只有两种；且两类互斥
    reasons = {row["reason"] for row in document["gap_three_step"]} | {
        row["reason"] for row in document["gap_no_readback"]
    }
    assert reasons == {"not_in_operation_contract", "no_readback_route"}, reasons
    keys_three = {row["key"] for row in document["gap_three_step"]}
    keys_none = {row["key"] for row in document["gap_no_readback"]}
    assert not (keys_three & keys_none)
    # 已映射的端点**不得**出现在缺口里（映射与缺口互补）
    mapped = set(document["mapped"])
    assert not (mapped & (keys_three | keys_none))


def test_p152_the_gap_is_a_strict_subset_of_the_write_path_denominator() -> None:
    """门槛：接口层可达集 ⊆ 数据侧写路径分母（**不**重复计数、**不**凭空多出端点）。"""
    document = _gap()
    registry = MidasRegistry.load(REPO_ROOT / "registry")
    coverage = write_path_coverage(registry, [])
    assert coverage.ratio == f"0 / {EXPECTED_WRITE_PATH_TOTAL}"
    assert coverage.model_write_ratio == f"0 / {EXPECTED_MODEL_WRITE_TOTAL}"
    write_keys = {
        str(entry["key"])
        for entry in json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["endpoints"]
        if any(
            method in str(entry["methods"]).upper() for method in ("POST", "PUT", "DELETE", "PATCH")
        )
    }
    assert len(write_keys) == EXPECTED_WRITE_PATH_TOTAL, len(write_keys)
    gap_keys = {row["key"] for row in document["gap_three_step"]} | {
        row["key"] for row in document["gap_no_readback"]
    }
    assert gap_keys <= write_keys, sorted(gap_keys - write_keys)[:5]
    # 缺口与「已映射」互补：接口层可达集 = 缺口 ∪ 已映射 ∩ 可写集
    assert not (gap_keys & set(document["mapped"]))
    reachable = gap_keys | (set(document["mapped"]) & write_keys)
    assert reachable <= write_keys, sorted(reachable - write_keys)[:5]
    # 接口层可达（GEN NX ∧ 已启用 ∧ 非破坏性）比数据侧分母更窄
    assert document["write_capable_endpoints"] < EXPECTED_WRITE_PATH_TOTAL


def test_p152_the_gap_entries_carry_a_computable_reason() -> None:
    """门槛：每条缺口行都有 `key` / `uri` / `methods` / `read_root` / `reason`（逐条可复核）。"""
    document = _gap()
    for row in document["gap_three_step"] + document["gap_no_readback"]:
        assert row["key"]
        assert row["uri"].startswith("/")
        assert row["methods"]
        assert row["reason"] in {"not_in_operation_contract", "no_readback_route"}
        if row["reason"] == "not_in_operation_contract":
            # 形态齐备 ⇒ 有 GET + read_root
            assert "GET" in row["methods"], row
            assert row["read_root"], row
        else:
            assert "GET" not in row["methods"] or not row["read_root"], row
    # 契约内的端点**不得**出现在缺口里（例如本批实测的 6 个端点）
    gap_keys = {row["key"] for row in document["gap_three_step"] + document["gap_no_readback"]}
    for key in EXPECTED_ENDPOINTS:
        assert key not in gap_keys, key


# ===== 6. 凭据 / 响应原文 / 判据版本（判定 6 / 7）=====


def test_p152_the_evidence_never_carries_credentials() -> None:
    """门槛（`docs/07` §14.3）：证据里**没有**任何凭据形态，成功响应**没有**原文。"""
    raw = EVIDENCE_PATH.read_text(encoding="utf-8")
    for marker in ("MAPI-Key", "MAPI_KEY", "mapi-key", "password", "secret"):
        assert marker not in raw, marker
    document = _evidence()
    for row in document["paths"]:
        for item in row["requests"]:
            if int(item["status"]) < 400:
                assert "native_error" not in item, (row["endpoint"], item)
            else:
                assert len(str(item.get("native_error") or "")) <= 200, item


def test_p152_the_check_mode_agrees_offline() -> None:
    """门槛：`--check` 离线跑通（退出码 0）—— CI 的复算入口。"""
    result = subprocess.run(
        [sys.executable, str(TOOL_PATH), "--check"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "接口层证据自洽" in result.stdout


# ===== 7. 实例门控（真实接口层探针）=====


def test_p152_the_live_probe_is_skipped_without_the_documented_declaration(
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
def test_p152_the_live_probe_is_bounded_and_reports_its_own_limits() -> None:
    """门槛：真实探针**有界**（分块 ≤ 20 + 块间只读健康检查）且**只碰自建编号**。

    ⚠️ 本用例**不**重跑写请求（真实实例的写路径已由 `--probe` 逐批实测并落证据）；
    它只断言「探针的纪律参数可被读出」—— 避免 CI 里对实例重复施加写压力。
    """
    tool = _tool()
    assert tool.CHUNK_SIZE <= 20
    assert tool.HEALTH_PATH == "/DB/NODE"
    assert tool.INSTANCE_PRODUCT == "GEN NX"
    for exercise in tool.EXERCISES:
        assert exercise["path"] in {"add", "edit", "delete"}
        assert exercise["endpoint"] in EXPECTED_ENDPOINTS
        assert exercise["query"].startswith("MODEL.")
        assert exercise["operation"] in tool.operation_plans(REPO_ROOT)
