"""P167 / **R160**：`POST.TABLE` 的 `TABLE_TYPE` 枚举**收口** ⇒ 解锁 `RESULT.ANALYSIS.SUMMARY`。

R151 的答案（真机实测，2026-10-15，`gen-local`，自建混凝土简支梁：21 节点 / 20 单元 / 工况 `DL`）
--------------------------------------------------------------------------------------------
拦住 `RESULT.ANALYSIS.SUMMARY` 的**不是**原生，而是核心自己的 `spec_guard`（**R140**）手里那份
**只有 2 个取值**的 `TABLE_TYPE` 枚举（来自 help center **一篇文章**的 `json_schema`）。
原生对 `POST /POST/TABLE {TABLE_TYPE: "DISPLACEMENTG"}` 回的是 **`200`** 且
`HEAD` **9** 列 / `DATA` **63** 行。

本批的裁决（**数据侧**）
----------------------
枚举来源换成**两个可复算来源的并集**（生成器 `registry/tools/sync_table_type_enum.py`）：

* ① **登记表** = `registry/manifest.json` 里已登记的 `POST.TABLE.*` 端点的 `table_type`（**194**）；
* ② **手册声明** = `MIDAS_API_Online_Manual_数据_v1.0.json` 全部 `json_schema` 的
  `TABLE_TYPE.enum`（**121**）；
* 并集 = **225** ⇒ **严格包含**旧枚举（`WEIGHT_IRREGULARITY_X` / `_Y` 一个不丢 ⇒ **只增不减**）。

⚠️ **只取①会丢掉 `WEIGHT_IRREGULARITY_Y`**（手册声明但未登记成独立端点）⇒ 那是把闸门
**收紧**，与 R151 的教训（枚举**可能不全**）**反向**。
⚠️ **R140 的保护照旧**：伪 token 两个来源都不在 ⇒ 仍被 `spec_guard` 拦在**发请求之前**（零请求）。

本文件钉住的判据（**铁律 ⓪**：效果，**不**是状态码）
-------------------------------------------------
1. **枚举可复算** 且 **只增不减**；
2. **原生阳性**有 `HEAD` / `DATA` **真值**；**原生阴性**被拒（`400`）；
3. **核心阳性**（经 MCP Tool 契约）的规范化结果**真的有数据行**；
4. **核心阴性** = **零请求** + `STRUCTAI-1200 value_not_in_spec_enum`（`midas_adapter` 拦）；
5. **生产口径**（`allow_unverified=False`，**无**旁路）也通过；
6. 跑前 / 跑后 **6** 个模型哨兵**逐项一致**（取报表**不**写模型）；
7. 主指标 `67 / 71` → **`68 / 71`**（被挡 **4 → 3** · 挡点端点 **14 → 13**）。
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
"""仓库根目录。"""

TOOL = REPO_ROOT / "registry" / "tools" / "probe_post_table_enum.py"
"""效果判据探针（默认预演 / `--probe` 真机 / `--probe --production` / `--check` 离线自洽）。"""

ENUM_TOOL = REPO_ROOT / "registry" / "tools" / "sync_table_type_enum.py"
"""枚举生成器（**唯一**所有者：只拥有 `TABLE_TYPE` 的 `enum` / `description`）。"""

EVIDENCE = REPO_ROOT / "registry" / "live" / "post_table_enum_probe.json"
"""真机证据。"""

ENDPOINT_YAML = REPO_ROOT / "registry" / "common" / "post" / "TABLE.yaml"
SCHEMA_JSON = REPO_ROOT / "registry" / "schema" / "common" / "post" / "TABLE.json"
MANIFEST = REPO_ROOT / "registry" / "manifest.json"
"""端点数据侧条目 + 枚举落点 + YAML 的派生物。"""

SPEC_GUARD = REPO_ROOT / "app" / "infrastructure" / "adapters" / "midas" / "spec_guard.py"
ADAPTER = REPO_ROOT / "app" / "infrastructure" / "adapters" / "midas" / "adapter.py"
"""核心侧的枚举闸门（**R140**）—— 本批**一行未改**（只换数据侧的枚举来源）。"""

DOCS_07 = REPO_ROOT / "docs" / "07_开发方案与任务续接_v1.0.md"
REGISTRY_README = REPO_ROOT / "registry" / "README.md"

AVAILABILITY_TOOL = REPO_ROOT / "registry" / "tools" / "check_operation_availability.py"
"""主指标工具（**R158 / R159 / R160**）。"""

OPERATION = "RESULT.ANALYSIS.SUMMARY"
ENDPOINT = "POST.TABLE"
TOKEN = "DISPLACEMENTG"
FAKE_TOKEN = "NOT_A_REAL_TABLE_XYZ"

EXPECTED_REGISTERED = 194
EXPECTED_MANUAL = 121
EXPECTED_UNION = 225
HISTORICAL_ENUM = ("WEIGHT_IRREGULARITY_X", "WEIGHT_IRREGULARITY_Y")
"""**旧**枚举（收口前的 2 个取值）—— 新枚举必须**严格包含**它们。"""

EXPECTED_DATA_ROWS = 63
"""自建混凝土简支梁的位移结果行数（**真值**；与 `HEAD` 的 **9** 列一起构成「真的有数据行」）。"""

EXPECTED_HEAD_COLUMNS = 9

AVAILABILITY_TOTALS = {"verified": 514, "unverified": 23, "untested": 126}
NO_GET = 98
"""`availability != verified` 且**没有 `GET`** 的端点数（R160 收口 `POST.TABLE` 后 **101**；
**P174 / R166** 收口 `POST.STEELCODECHECK` 后 **100**）。"""


def _load(path: pathlib.Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _evidence() -> dict:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _entry(key: str) -> dict:
    for item in _manifest()["endpoints"]:
        if item["key"] == key:
            return item
    raise AssertionError(f"{key} not in registry/manifest.json")


# ===== 1. 枚举：可复算 + 只增不减 =====


def test_p167_the_enum_is_the_union_of_the_two_computable_sources() -> None:
    """门槛（**收口的核心**）：落盘枚举 == 机械并集（登记表 ∪ 手册声明）。"""
    tool = _load(ENUM_TOOL, "sync_table_type_enum_p167")
    registered = tool.registered_table_types(REPO_ROOT)
    manual = tool.manual_table_types(REPO_ROOT)
    enum = tool.expected_enum(REPO_ROOT)
    assert len(registered) == EXPECTED_REGISTERED, len(registered)
    assert len(manual) == EXPECTED_MANUAL, len(manual)
    assert len(enum) == EXPECTED_UNION, len(enum)
    assert enum == sorted(set(enum)), "枚举必须去重且有序（确定性）"
    assert TOKEN in set(registered), f"{TOKEN} 必须在登记表里"
    assert FAKE_TOKEN not in set(enum), "伪 token **不得**出现在枚举里"
    assert tool.on_disk_enum(REPO_ROOT) == enum, "已落盘枚举必须逐条等于机械结果"


def test_p167_the_new_enum_is_a_strict_superset_of_the_historical_one() -> None:
    """门槛（**只增不减**）：旧枚举的 2 个取值一个不丢 ⇒ 闸门**没有**被收紧。"""
    tool = _load(ENUM_TOOL, "sync_table_type_enum_p167_superset")
    enum = set(tool.expected_enum(REPO_ROOT))
    missing = [value for value in HISTORICAL_ENUM if value not in enum]
    assert missing == [], f"新枚举丢掉了旧取值（= 收紧闸门，须显式裁决）：{missing}"
    # 其中 `_Y` 是**手册声明但未登记**的取值 —— 正是「并集」这条裁决的理由
    registered = set(tool.registered_table_types(REPO_ROOT))
    manual = set(tool.manual_table_types(REPO_ROOT))
    assert "WEIGHT_IRREGULARITY_X" in registered
    assert "WEIGHT_IRREGULARITY_Y" in manual and "WEIGHT_IRREGULARITY_Y" not in registered
    document = _evidence()
    assert document["enum"]["superset_of_historical"] is True, document["enum"]


def test_p167_the_generator_refuses_to_shrink_the_enum(tmp_path: pathlib.Path) -> None:
    """门槛（**结构性护栏**）：机械结果**丢掉**已落盘取值时，`--write` **拒绝写入**。

    ⚠️ 这是「枚举只增不减」从**注释**变成**可执行判定**（收紧闸门必须是一次**显式裁决**）。
    """
    registry = tmp_path / "registry"
    (registry / "schema" / "common" / "post").mkdir(parents=True)
    (registry / "manifest.json").write_text(
        json.dumps(
            {
                "endpoints": [
                    {"key": "POST.TABLE.AAA", "table_type": "AAA"},
                    {"key": "POST.TABLE.string", "table_type": ""},
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "MIDAS_API_Online_Manual_数据_v1.0.json").write_text(
        json.dumps(
            {
                "endpoints": [
                    {"json_schema": json.dumps({"TABLE_TYPE": {"enum": ["AAA"]}})},
                ]
            }
        ),
        encoding="utf-8",
    )
    target = registry / "schema" / "common" / "post" / "TABLE.json"
    body = {
        "key": "POST.TABLE",
        "schema": {
            "properties": {
                "Argument": {
                    "properties": {
                        "TABLE_TYPE": {"type": "string", "enum": ["AAA", "ZZZ"], "description": ""}
                    }
                }
            }
        },
    }
    target.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    before = target.read_text(encoding="utf-8")

    tool = _load(ENUM_TOOL, "sync_table_type_enum_p167_shrink")
    code = tool.main(["--repo", str(tmp_path), "--write"])
    assert code == 1, "丢掉已落盘取值时必须拒绝写入"
    assert target.read_text(encoding="utf-8") == before, "拒绝写入后文件必须一字未改"
    # 显式裁决才放行
    code = tool.main(["--repo", str(tmp_path), "--write", "--allow-shrink"])
    assert code == 0, "显式 --allow-shrink 应当放行"


def test_p167_the_spec_guard_is_unchanged_and_carries_no_midas_table_token() -> None:
    """门槛（**架构红线**）：枚举是**数据**，不是 Core 里的常量 ——
    ① `spec_guard.py` **不**含任何 MIDAS 取值 / 字段名；
    ② `adapter.py` 的闸门**只**从**数据侧 Schema** 取枚举（**不**硬编码取值列表）；
    ③ 全 `app/**` **不**出现 `TABLE_TYPE` 的枚举取值（`WEIGHT_IRREGULARITY_*` / 伪 token）。

    ⚠️ `adapter.py` 里**可以**出现 `DISPLACEMENTG` —— 那是**结果行解析器**的表键
    （`_RESULT_ROW_TRANSFORMERS`，与请求枚举无关）；本用例**只**管请求侧的枚举来源。

    ⚠️ **P168 / R161 更新（只改现状声称）**：闸门取 Schema 的**口径**由
    `registry.schema_json(...)`（**原样、含包装根键**）改为 `registry.effective_schema(...)`
    （**剥离包装根键**，P09 的口径）—— 前者对 **393 / 652** 个「根键 = 包装键」的文件
    会让闸门**一个字段都不检查**（**盲区 104 / 225**）。**红线不变**：枚举仍然**只**来自
    **数据侧 Schema**（`registry/**`），Core 里**没有**任何取值列表。
    """
    guard = SPEC_GUARD.read_text(encoding="utf-8")
    for value in (TOKEN, FAKE_TOKEN, "WEIGHT_IRREGULARITY_X", "TABLE_TYPE"):
        assert value not in guard, f"spec_guard 里出现了 MIDAS 取值 / 字段名 {value}"
    adapter = ADAPTER.read_text(encoding="utf-8")
    assert "guard_spec_values(" in adapter, "闸门仍接在 `build_request()` 之前"
    assert "registry.effective_schema(resolved.definition.key)" in adapter, (
        "闸门必须从**数据侧 Schema** 取枚举（不得在 Core 里硬编码取值列表；R161 起用生效 Schema）"
    )
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "app").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for value in ("WEIGHT_IRREGULARITY_X", "WEIGHT_IRREGULARITY_Y", FAKE_TOKEN):
            if value in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{value}")
    assert offenders == [], f"`app/**` 里硬编码了 TABLE_TYPE 取值：{offenders}"


# ===== 2. 效果判据（**铁律 ⓪**）=====


def test_p167_the_native_positive_really_returns_data_rows() -> None:
    """门槛（**效果**）：原生 `POST /POST/TABLE` ⇒ `200` · `HEAD` **9** 列 · `DATA` **63** 行。"""
    native = _evidence()["effect"]["native"]
    positive = native["positive"]
    assert positive["token"] == TOKEN, positive
    assert positive["status"] == 200, positive
    assert positive["head_columns"] == EXPECTED_HEAD_COLUMNS, positive
    assert positive["data_rows"] == EXPECTED_DATA_ROWS, positive
    assert len(positive["head_names"]) == EXPECTED_HEAD_COLUMNS, positive


def test_p167_the_native_negative_is_rejected() -> None:
    """门槛（**负向对照，原生**）：伪 token ⇒ `4xx`（本 build 实测 `400`）。"""
    negative = _evidence()["effect"]["native"]["negative"]
    assert negative["token"] == FAKE_TOKEN, negative
    assert negative["status"] >= 400, negative
    assert negative["data_rows"] == 0, negative


def test_p167_the_core_path_parses_real_rows() -> None:
    """门槛（**核心，Contract-Test 口径**）：经 MCP Tool 契约 ⇒ `PASSED` ∧ `rows` **63**。

    ⚠️ 这是 R151 的**直接反证**：收口前这里**零请求**（`value_not_in_spec_enum`）。
    """
    positive = _evidence()["effect"]["positive"]
    assert positive["operation"] == OPERATION, positive
    assert positive["status"] == "PASSED", positive
    assert positive["readback"]["count"] == EXPECTED_DATA_ROWS, positive["readback"]
    assert positive["parameters"] == {"table_type": TOKEN}, positive
    requests = positive["requests"]
    assert len(requests) == 1, requests
    assert requests[0]["method"] == "POST", requests
    assert requests[0]["path"].endswith("/POST/TABLE"), requests
    assert requests[0]["status"] == 200, requests
    assert requests[0]["body"] == {"Argument": {"TABLE_TYPE": TOKEN}}, requests


def test_p167_the_negative_control_is_a_zero_request_rejection() -> None:
    """门槛（**负向对照，核心**）：伪 token ⇒ **零请求** + `STRUCTAI-1200`（**R140 未丢**）。"""
    negative = _evidence()["effect"]["negative_control"]
    assert negative["requests"] == [], negative
    assert negative["http"] == 0, negative
    error = negative["error"]
    assert error["code"] == "STRUCTAI-1200", error
    assert error["native_reason"] == "value_not_in_spec_enum", error
    assert error["native_stage"] == "midas_adapter", error
    assert error["native_endpoint"] == ENDPOINT, error


def test_p167_the_production_phase_passes_without_any_bypass() -> None:
    """门槛（**生产口径**）：`allow_unverified=False` 也 `PASSED` ∧ `rows` **63**。

    ⚠️ 这一条才证明**生产路径本身**已通（不是靠旁路测出来的效果）。
    """
    production = _evidence()["production"]
    assert production["allow_unverified"] is False, production
    assert production["verdict"] == "PASSED", production
    assert production["positive_ok"] is True, production
    positive = production["positive"]
    assert positive["status"] == "PASSED", positive
    assert positive["readback"]["count"] == EXPECTED_DATA_ROWS, positive["readback"]
    requests = positive["requests"]
    assert len(requests) == 1 and requests[0]["status"] == 200, requests


def test_p167_the_run_left_no_residue() -> None:
    """门槛：两个口径的跑前 / 跑后 **6** 项模型哨兵**逐项一致**（取报表**不**写模型）。"""
    document = _evidence()
    for section in ("effect", "production"):
        sentinel = document[section]["sentinel"]
        assert sentinel["unchanged"] is True, (section, sentinel)
        assert sentinel["before"] == sentinel["after"], (section, sentinel)
        assert set(sentinel["before"]) == set(sentinel["keys"]), (section, sentinel)
        assert len(sentinel["keys"]) == 6, sentinel


def test_p167_the_evidence_carries_no_credentials() -> None:
    """门槛（`docs/07` §14.3）：证据里**绝不**出现凭据。"""
    raw = EVIDENCE.read_text(encoding="utf-8")
    for marker in ("MAPI-Key", "MAPI_KEY", "mapi-key", "password", "secret", "MAPI"):
        assert marker not in raw, marker


# ===== 3. 离线自洽 + 零请求 =====


def test_p167_the_offline_check_passes() -> None:
    """门槛：`--check` 退出码 0（证据齐备 + 判据全真 + 与数据侧一致）。"""
    result = subprocess.run(
        [sys.executable, str(TOOL), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "只增不减" in result.stdout, result.stdout


def test_p167_the_default_run_is_a_dry_run() -> None:
    """门槛：默认（无 `--probe`）只预演，**零请求**。"""
    result = subprocess.run(
        [sys.executable, str(TOOL)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "预演" in result.stdout, result.stdout
    assert str(EXPECTED_UNION) in result.stdout, result.stdout


def test_p167_the_enum_tool_check_passes() -> None:
    """门槛：枚举生成器 `--check` 退出码 0（已落盘 == 机械结果）。"""
    result = subprocess.run(
        [sys.executable, str(ENUM_TOOL), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "与机械结果一致" in result.stdout, result.stdout


# ===== 4. 四处记录必须一致（数据侧 / 主指标 / 文档）=====


def test_p167_the_endpoint_yaml_and_manifest_are_closed() -> None:
    """门槛（**收口**）：端点 YAML `untested → verified`；`manifest` 派生一致。"""
    text = ENDPOINT_YAML.read_text(encoding="utf-8")
    assert "availability: verified" in text, "必须收口"
    assert 'verified_on: ["gen-local"]' in text, text
    assert "R160" in text and "P167" in text, "必须写明裁决 / 批次"
    assert "TABLE_TYPE" in text and "spec_guard" in text, "必须写明成因（枚举来源太窄）"
    entry = _entry(ENDPOINT)
    assert entry["availability"] == "verified", entry
    assert entry["verified_on"] == ["gen-local"], entry
    assert "GEN_NX" in [str(item) for item in entry["products"]], entry


def test_p167_the_schema_description_names_the_source() -> None:
    """门槛：落盘 Schema 的 `TABLE_TYPE.description` 指向**两个可复算来源**（不是手写取值）。"""
    document = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
    node = document["schema"]["properties"]["Argument"]["properties"]["TABLE_TYPE"]
    assert len(node["enum"]) == EXPECTED_UNION, len(node["enum"])
    assert "manifest.json" in node["description"], node["description"]
    assert "sync_table_type_enum.py" in node["description"], node["description"]
    assert "R160" in node["description"], node["description"]


def test_p167_the_main_indicator_is_backfilled() -> None:
    """门槛（**主指标回填**）：`67 / 71` → **`68 / 71`**；`POST.TABLE` 不再是挡点。

    ⚠️ **R166（P174）**：主指标现为 **`71 / 73`**（`POST.STEELCODECHECK` 已收口）。
    本用例钉的是**本批的增量**（`POST.TABLE` 不再是挡点）⇒ 断言按**当前**值写，
    并**额外**确认本批的 `ENDPOINT` / `OPERATION` 仍成立。
    """
    module = _load(AVAILABILITY_TOOL, "check_operation_availability_p167")
    document: dict[str, Any] = module.compute()
    assert document["available"] == 71, document["available"]
    assert document["blocked"] == 2, document["blocked"]
    assert document["blocker_endpoint_count"] == 4, sorted(document["blocker_endpoints"])
    assert ENDPOINT not in document["blocker_endpoints"], document["blocker_endpoints"]
    assert OPERATION in document["available_operations"], OPERATION
    assert OPERATION not in document["blocked_operations"], OPERATION


def test_p167_the_availability_totals_match() -> None:
    """门槛：`availability` 三档 = `verified` 514 · `unverified` 23 · `untested` 126。"""
    endpoints = _manifest()["endpoints"]
    totals: dict[str, int] = {}
    for item in endpoints:
        name = str(item["availability"])
        totals[name] = totals.get(name, 0) + 1
    assert totals == AVAILABILITY_TOTALS, totals
    no_get = [
        item
        for item in endpoints
        if str(item["availability"]) != "verified" and "GET" not in str(item["methods"])
    ]
    assert len(no_get) == NO_GET, len(no_get)


def test_p167_the_ruling_and_the_ledger_register_it() -> None:
    """门槛：`docs/07` §16.1 登记 **R160**；`registry/README.md` §8.21 同步。"""
    docs = DOCS_07.read_text(encoding="utf-8")
    assert "**R160**" in docs, "R160 必须登记"
    assert "probe_post_table_enum.py" in docs, "必须留下可复算的工具"
    assert "sync_table_type_enum.py" in docs, "必须留下枚举生成器"
    assert "registry/live/post_table_enum_probe.json" in docs, "必须留下证据路径"
    ledger = REGISTRY_README.read_text(encoding="utf-8")
    assert "### 8.21" in ledger, "数据侧账本必须新增一节"
    assert "TABLE_TYPE" in ledger, "必须记下枚举口径"
