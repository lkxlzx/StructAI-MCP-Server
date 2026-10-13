"""P149-D —— **R106**：`POST.*`「结果表 / 文本查询」端点的**取报表判据**
（`registry/README.md` §8.13）。

本批把 `docs/07` §16.1 的 **R106** 落地：这 **197** 个端点（⚠️ **P157 / R129** 起 **198**，
见 `EXPECTED_TARGETS`）在 L5 三步链（创建 → 读回 → 按路径 key
删除）下**结构上不适用**（**只**有 `POST`、**没有** `GET` / `read_root` ⇒ 没有「自建 ID」可读回 /
可删），此前一律落在「无读回」桶里、**从未取得结论**。判据（**与三步链并列的第二条**）：

1. **前置链** = 最小模型（`MINIMAL_MODEL`，**只**用自建编号）+ `POST /DOC/ANAL`（空体 = 执行分析）
   —— 实测确认：空项目下 `POST /POST/TABLE` → `400`「no analysis result」⇒ **必须**有分析结果；
2. **请求体** = 上游手册里该端点**自己那张表**的示例，**唯一**改动 = 剥掉 `Argument.EXPORT_PATH`
   （带它会让实例**落文件**）；
3. **判定** = `HTTP 200` ∧ **实测信封形状**（恰好 1 个顶层键 ∧ 其值是对象 ∧ 含 `HEAD` / `DATA`
   两个数组）⇒ `PASSED`（信封键**逐端点**不同，记在 `envelope_key`）；`200` ∧ 空块 ⇒ `PARTIAL`；
   其余 ⇒ `FAILED`；
4. **零残留** = 跑前 / 跑后模型哨兵**逐条相同**（取报表**不**写模型数据），清理后**全空**。

本文件的**可执行判定**
----------------------
1. **目标集 197 逐条可复算**（`targets()`；GEN NX 的 `POST.*`）。
   ⚠️ **P157 / R129** 起为 **198**（`POST.TABLE` 补 `GEN_NX`），但新增的那一条**未**实测。
2. **证据完整**：**195** 条实测 + **2** 条留缺；`counts == {PASSED: 15, PARTIAL: 172, FAILED: 8}`；
   无 `SKIPPED`；`aborted == ""`。
3. **判据可复算**：工具重算的 `select_example()` 与证据的 `example_id` / `body_sha256` /
   `adjustments` **逐条**一致。
4. **不带 `EXPORT_PATH`**：每条证据的改动**至多**一条且**只**删 `Argument.EXPORT_PATH`。
5. **零残留**：`residue.clean` / `residue.model_untouched` 为真、`cleanup_failures` 空、
   `after_cleanup` 全空。
6. **R115 永不再试**：`POST.TABLE.FIBR_MAXCONTRACT` 在 `never_retry` 里、留缺原因 =
   `crashes_instance`、且**没有**被收口。
7. **落盘一致**：`--check` 退出码 **0**；PASSED 的 `response` 块 == 实测信封；
   可收口的端点 `availability: verified` + `verified_on` 含 `gen-local`；其余**不得** `verified`。
8. **计数钉住**：全库 `availability == verified` = **481**；`response` 块 = **305**。
9. **前置链的字段不臆造**：`MINIMAL_MODEL` 的每个字段都在数据侧请求 Schema 里声明
   （把 **R112** 的修与 **R106** 的前置链**绑在一起**）。
10. **不泄密**：证据文件里没有凭据、没有请求体原文。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录。"""

TOOL_PATH = REPO_ROOT / "registry" / "tools" / "probe_result_tables.py"
"""本批**唯一**的取报表工具（只依赖标准库 + `httpx`）。"""

EVIDENCE_PATH = REPO_ROOT / "registry" / "live" / "result_table_probe.json"
"""取报表判据的**实测证据**（`--probe` 的产物；不含凭据、不含请求体原文）。"""

EXPECTED_TARGETS = 198
"""目标集（GEN NX 的 `POST.*`：`POST.TABLE.*` **194** + `POST.TABLE` + `POST.PM` / `POST.TEXT` /
`POST.STEELCODECHECK`）。

⚠️ **P157 / R129 同步（有实测依据）**：`POST.TABLE` 的 `products` 补 `GEN_NX` 后**进入**本目标集
（**197 → 198**）—— 但它**既没有**实测行、**也不在** `gaps` 里：取报表判据的 `--probe` 需要
**先跑分析**（`POST /DOC/ANAL`，见本文件模块 docstring 的判据 1），而 P157 **明确禁止**在**唯一**
项目上跑分析（分析结果**可能清不掉**）⇒ **如实记为「目标集 +1、实测未覆盖」**，
**不**伪造行、**不**把它塞进 `gaps`。恢复条件 = 有专用建模 / 分析项目后重跑 `--probe`。
"""

EXPECTED_PROBED = 195
"""取得结论的端点数（原 **197** − **2** 条如实留缺；⚠️ **P157 / R129**：目标集 +1 = **198**，
但新增的 `POST.TABLE` **未**实测 ⇒ 本值**不变**，差额如实披露）。"""

EXPECTED_COUNTS = {"PASSED": 15, "PARTIAL": 172, "FAILED": 8}
"""三态计数（**P149-D** 全量实测；无 `SKIPPED`）。"""

EXPECTED_GAPS = {
    "POST.TABLE.FIBR_MAXCONTRACT": "crashes_instance",
    "POST.STEELCODECHECK": "no_manual_entry",
}
"""如实留缺：**R115** 崩溃（**永不再试**）· 手册里没有该 URI 的条目。"""

EXPECTED_NEVER_RETRY = {"POST.TABLE.FIBR_MAXCONTRACT": "R115"}
"""**永不再试**的端点（使 NX 实例**崩溃**，两次实测确认）。"""

EXPECTED_VERIFIED_TOTAL = 501
"""全库 `availability == verified`（P149-C 的 296 + P149-D 收口的 185 + P149-E 补测的 12）。"""

EXPECTED_RESPONSE_BLOCKS = 317
"""全库 `response` 块数（P149-C 的 290 + P149-D 的 15 个 `PASSED` + P149-E 的 12）。"""

ENVELOPE_KEYS: dict[str, str] = {
    "POST.TABLE.ELEMENTWEIGHT": "Example",
    "POST.TABLE.ELEM_PROP_EACH_STAGE": "ElementPropertiesatEachStage",
    "POST.TABLE.MATERIAL": "Example",
    "POST.TABLE.SECTIONALL": "Example",
    "POST.TABLE.SUPPORTS": "Example",
    "POST.TABLE.TNDN_WEIGHT_GROUP": "TendonGroup",
    "POST.TABLE.TNDN_WEIGHT_PROFILE": "TendonProfile",
    "POST.TABLE.TNDN_WEIGHT_PROPERTY": "TendonProperty",
    "POST.TABLE.ULTIMATE_STORY_SHEAR_FORCE_CHECK": "empty",
}
"""**实测信封键逐端点不同**（`Example` 之外还有表自己的名字与字面 `empty`）—— 抽样钉住。"""

INSTANCE_ALIAS = "gen-local"
EXPORT_PATH = "EXPORT_PATH"


def _load(path: Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tool() -> Any:
    """取报表工具（`probe_result_tables.py`）。"""
    return _load(TOOL_PATH, "structai_probe_result_tables_p149d")


def _evidence() -> dict[str, Any]:
    """取报表证据原文。"""
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def _manifest() -> dict[str, Any]:
    """`registry/manifest.json` 原文。"""
    return json.loads((REPO_ROOT / "registry" / "manifest.json").read_text(encoding="utf-8"))


# ===== 1. 目标集与判据可复算（判定 1 / 3）=====


def test_p149d_the_target_set_is_one_hundred_ninety_eight_by_measurement() -> None:
    """门槛：目标集 = **198**（GEN NX 的 `POST.*`），且**全部**没有 `GET` / `read_root`。

    ⚠️ **P157 / R129 同步（有实测依据）**：`POST.TABLE` 的 `products` 补 `GEN_NX` 后进入本目标集
    （**197 → 198**）；判定**未**放宽（仍逐条要求 `namespace == POST` ∧ `GEN_NX ∈ products` ∧
    无 `GET` ∧ 无 `read_root`）。⚠️ 该新增目标**未**实测（见 `EXPECTED_TARGETS` 的说明）。
    """
    tool = _tool()
    keys = tool.targets(REPO_ROOT, ())
    assert len(keys) == EXPECTED_TARGETS
    entries = tool.manifest_entries(REPO_ROOT)
    for key in keys:
        entry = entries[key]
        assert entry["namespace"] == "POST", key
        assert "GEN_NX" in entry["products"], key
        assert "GET" not in str(entry["methods"]), key
        assert not (entry.get("wrapper") or {}).get("read_root"), key
    # 构成：194 `POST.TABLE.*` + 4 个同命名空间的其它取报表端点（含通用入口 `POST.TABLE`）
    assert sum(1 for key in keys if key.startswith("POST.TABLE.")) == 194
    assert set(keys) >= {"POST.TABLE", "POST.PM", "POST.TEXT", "POST.STEELCODECHECK"}


def test_p149d_every_probed_body_is_recomputable_from_the_manual() -> None:
    """门槛：证据里每条的 `example_id` / `body_sha256` / `adjustments` 都由工具**重算**得出。"""
    tool = _tool()
    examples = tool.check_tool(REPO_ROOT).manual_examples(REPO_ROOT)
    entries = tool.manifest_entries(REPO_ROOT)
    document = _evidence()
    checked = 0
    for key, row in sorted(document["endpoints"].items()):
        picked = tool.select_example(tool.check_tool(REPO_ROOT), examples, entries[key])
        assert not isinstance(picked, str), (key, picked)
        assert picked.example_id == row["example_id"], key
        assert picked.body_sha256 == row["body_sha256"], key
        assert list(picked.adjustments) == row["adjustments"], key
        checked += 1
    assert checked == EXPECTED_PROBED


def test_p149d_the_only_adjustment_is_dropping_export_path() -> None:
    """门槛：**唯一**改动 = 剥掉 `Argument.EXPORT_PATH`（带它会让实例落文件）。"""
    tool = _tool()
    examples = tool.check_tool(REPO_ROOT).manual_examples(REPO_ROOT)
    entries = tool.manifest_entries(REPO_ROOT)
    with_change = 0
    for key, row in sorted(_evidence()["endpoints"].items()):
        adjustments = row["adjustments"]
        assert len(adjustments) <= 1, (key, adjustments)
        for adjustment in adjustments:
            assert adjustment["path"] == ["Argument", EXPORT_PATH], key
            assert adjustment["to"] is None, key
        picked = tool.select_example(tool.check_tool(REPO_ROOT), examples, entries[key])
        assert not isinstance(picked, str), key
        assert EXPORT_PATH not in (picked.body.get("Argument") or {}), key
        with_change += 1 if adjustments else 0
    # 165 条的示例带 EXPORT_PATH（被剥掉）、30 条本来就没有
    assert with_change == 165


# ===== 2. 证据完整与零残留（判定 2 / 5）=====


def test_p149d_the_evidence_covers_everything_with_the_measured_counts() -> None:
    """门槛：**195** 条实测 + **2** 条留缺；三态计数与**零残留**逐条如实。"""
    document = _evidence()
    assert document["counts"] == EXPECTED_COUNTS
    assert len(document["endpoints"]) == EXPECTED_PROBED
    assert document["gaps"] == EXPECTED_GAPS
    assert document["never_retry"] == EXPECTED_NEVER_RETRY
    assert document["aborted"] == ""
    assert document["instance"]["alias"] == INSTANCE_ALIAS
    assert document["instance"]["product"] == "GEN_NX"
    # 零残留：跑前 / 跑后哨兵逐条相同（取报表**不**写模型数据），清理后全空
    residue = document["residue"]
    assert residue["clean"] is True
    assert residue["model_untouched"] is True
    assert residue["cleanup_failures"] == []
    assert all(not members for members in residue["after_cleanup"].values())
    assert residue["after_model"] == residue["expected_model"]
    assert all(not members for members in residue["before"].values())


def test_p149d_the_envelope_shape_is_measured_and_endpoint_specific() -> None:
    """门槛：`PASSED` 的 `envelope_key` 是**实测**值（键名逐端点不同，**不**是全局常量）。"""
    document = _evidence()
    passed = {
        key: row["envelope_key"]
        for key, row in document["endpoints"].items()
        if row["verdict"] == "PASSED"
    }
    assert len(passed) == EXPECTED_COUNTS["PASSED"]
    assert all(passed[key] for key in passed)
    assert len(set(passed.values())) > 1, "信封键必须逐端点不同（否则判据退化）"
    for key, envelope in ENVELOPE_KEYS.items():
        assert passed[key] == envelope, key
    # `PARTIAL` = 200 ∧ 空块（该表在最小模型上无数据）；`FAILED` = 原生拒绝
    for key, row in document["endpoints"].items():
        if row["verdict"] == "PARTIAL":
            assert row["status_code"] == 200, key
            assert row["top_keys"] in ([], ["message"]), (key, row["top_keys"])
            assert row["envelope_key"] == "", key
        if row["verdict"] == "FAILED":
            assert row["status_code"] != 200, key
            assert row["envelope_key"] == "", key


def test_p149d_the_crashing_endpoint_is_never_retried_and_never_upgraded() -> None:
    """门槛（**R115**）：崩溃端点如实留缺、**不**发请求、**不**被收口。"""
    tool = _tool()
    files = tool.endpoint_files(REPO_ROOT)
    for key in EXPECTED_NEVER_RETRY:
        assert key not in _evidence()["endpoints"], key
        availability, _ = tool.read_availability(files[key])
        assert availability != "verified", key
    assert set(tool.NEVER_RETRY) == set(EXPECTED_NEVER_RETRY)


# ===== 3. 落盘一致与计数（判定 7 / 8）=====


def test_p149d_the_data_side_matches_the_evidence() -> None:
    """门槛：`--check` 退出码 **0**（数据侧 == 取报表证据）。"""
    tool = _tool()
    assert tool.check(REPO_ROOT) == 0


def test_p149d_every_upgradable_endpoint_is_verified_and_the_rest_is_not() -> None:
    """门槛：`PASSED` / `PARTIAL` 已 `verified` + `verified_on` 含 `gen-local`；
    其余**不**得 `verified`。"""
    tool = _tool()
    files = tool.endpoint_files(REPO_ROOT)
    document = _evidence()
    upgradable = 0
    for key, row in sorted(document["endpoints"].items()):
        availability, verified_on = tool.read_availability(files[key])
        if row["verdict"] in tool.UPGRADABLE:
            assert availability == "verified", key
            assert INSTANCE_ALIAS in verified_on, (key, verified_on)
            upgradable += 1
        else:
            assert availability != "verified", key
    assert upgradable == EXPECTED_PROBED - EXPECTED_COUNTS["FAILED"]
    for key in document["gaps"]:
        availability, _ = tool.read_availability(files[key])
        assert availability != "verified", key


def test_p149d_the_response_blocks_carry_the_measured_envelope_key() -> None:
    """门槛：`PASSED` 端点的 `response` 块 == `response_block(实测信封键)`；全库计数钉住。"""
    tool = _tool()
    entries = tool.manifest_entries(REPO_ROOT)
    document = _evidence()
    blocks = 0
    verified = 0
    for entry in _manifest()["endpoints"]:
        if entry["availability"] == "verified":
            verified += 1
        relative = str(entry.get("schema") or "")
        path = REPO_ROOT / "registry" / relative
        if not relative or not path.is_file():
            continue
        block = json.loads(path.read_text(encoding="utf-8")).get("response")
        if not isinstance(block, dict):
            continue
        blocks += 1
        row = document["endpoints"].get(entry["key"])
        if row is None or row["verdict"] != "PASSED":
            continue
        assert block == tool.response_block(row["envelope_key"]), entry["key"]
        assert block["source"] == tool.RESPONSE_SOURCE, entry["key"]
    assert verified == EXPECTED_VERIFIED_TOTAL
    assert blocks == EXPECTED_RESPONSE_BLOCKS
    # 抽样：`response` 块只断言**实测到**的那个键
    section = json.loads(
        (REPO_ROOT / "registry" / entries["POST.TABLE.SECTIONALL"]["schema"]).read_text(
            encoding="utf-8"
        )
    )["response"]["schema"]
    assert section["required"] == ["Example"]


# ===== 4. 前置链与保密（判定 9 / 10）=====


def test_p149d_the_minimal_model_fields_are_all_declared_by_the_request_schemas() -> None:
    """门槛：最小模型的字段**全部**在数据侧请求 Schema 里声明
    （**R112** 的修 + **R106** 的前置链）。"""
    tool = _tool()
    check_tool = tool.check_tool(REPO_ROOT)
    entries = tool.manifest_entries(REPO_ROOT)
    assert len(tool.MINIMAL_MODEL) == 8
    for endpoint, _item_id, body in tool.MINIMAL_MODEL:
        key = f"DB.{endpoint}"
        schema = check_tool.request_schema(REPO_ROOT, str(entries[key].get("schema") or ""), key)
        assert schema is not None, key
        assert check_tool.unknown_fields(body, schema) == [], key


def test_p149d_the_evidence_carries_no_secret_and_no_raw_body() -> None:
    """门槛：证据里**没有**凭据、**没有**请求体 / 响应体原文。"""
    text = EVIDENCE_PATH.read_text(encoding="utf-8")
    for forbidden in ("MAPI-Key", "MIDAS_MAPI_KEY", "midas-test.env", "sha256:"):
        assert forbidden not in text, forbidden
    document = _evidence()
    for key, row in document["endpoints"].items():
        assert set(row) == {
            "uri",
            "wrapper",
            "example_id",
            "body_sha256",
            "adjustments",
            "status_code",
            "top_keys",
            "payload_bytes",
            "envelope_key",
            "criterion_version",
            "verdict",
            "detail",
            "instance_down",
        }, key
        assert len(row["body_sha256"]) == 64, key


@pytest.mark.parametrize("key", sorted(ENVELOPE_KEYS))
def test_p149d_the_sampled_envelope_keys_are_recorded_with_evidence(key: str) -> None:
    """门槛（逐条）：抽样的 9 个端点都如实记下了**实测**信封键与响应字节数。"""
    row = _evidence()["endpoints"][key]
    assert row["verdict"] == "PASSED"
    assert row["status_code"] == 200
    assert row["top_keys"] == [ENVELOPE_KEYS[key]]
    assert row["payload_bytes"] > 0
    assert row["criterion_version"] == _tool().CRITERION_VERSION
