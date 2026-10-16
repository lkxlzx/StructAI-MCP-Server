"""P166 / **R159**：`VIEW.RESULTGRAPHIC` 的**纯 API 进结果视图（post）路径** + **效果判据**。

结论（真机实测，2026-10-15，`gen-local`，自建混凝土简支梁，工况 `DL`）
------------------------------------------------------------------
**R157 的「静默 `200` / 画面没变」有答案了**：当时的请求体**缺 `TYPE_OF_DISPLAY`** ——
`TYPE_OF_DISPLAY.<子块>.OPT_CHECK = true` 才是**真正把结果图形打开**的开关。
补上它之后，`VIEW.RESULTGRAPHIC` 的**效果判据 7 / 7 通过**：
`33438` → **`81236`** 字节（换 `CURRENT_MODE` 再变 `84494`），
**阳性对照**（`VIEW.DISPLAY` 的 `ELEM_NUMBER` 开/关 = `40211` vs `33438`）通过
⇒ **铁律 ⓪ 成立** ⇒ `availability` **收口为 `verified`**（`untested → verified`）。

本文件钉住的**方法学要求（缺一不可）**
------------------------------------
1. **阳性对照**必须先通过（否则「无差异」无法区分「原生空转」与「截图拍不到结果图形」）。
2. **基线渲染确定**（同设置连拍两次 ⇒ **0** 字节差异）—— 把**噪声地板**变成实测值。
3. **同取值可复现** 且 **图形关掉即回到基线**。
4. **pre 模式画不出结果** —— 证明效果确实来自 post 模式。
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

TOOL = REPO_ROOT / "registry" / "tools" / "probe_view_result_post.py"
"""效果判据探针（默认预演 / `--probe` 真机 / `--check` 离线自洽）。"""

EVIDENCE = REPO_ROOT / "registry" / "live" / "view_result_post_probe.json"
"""真机证据。"""

MODES_EVIDENCE = REPO_ROOT / "registry" / "live" / "view_result_modes.json"
"""取值表（**R155**）。"""

ENDPOINT_YAML = REPO_ROOT / "registry" / "common" / "view" / "RESULTGRAPHIC.yaml"
CAPTURE_YAML = REPO_ROOT / "registry" / "common" / "view" / "CAPTURE.yaml"
SELECT_YAML = REPO_ROOT / "registry" / "common" / "view" / "SELECT.yaml"
"""端点数据侧条目。"""

MANIFEST = REPO_ROOT / "registry" / "manifest.json"
"""YAML 的派生物（`sync_manifest.py`）。"""

DOCS_07 = REPO_ROOT / "docs" / "07_开发方案与任务续接_v1.0.md"
REGISTRY_README = REPO_ROOT / "registry" / "README.md"

AVAILABILITY_TOOL = REPO_ROOT / "registry" / "tools" / "check_operation_availability.py"
"""主指标工具（**R158 / R159**）。"""


def _evidence() -> dict:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def _step(tag: str) -> dict:
    for row in _evidence()["steps"]:
        if row["tag"] == tag:
            return row
    raise AssertionError(f"证据里没有步骤 {tag!r}")


# ===== 1. 效果判据的七个条件 =====


def test_p166_the_effect_verdict_is_passed() -> None:
    """门槛：真机实测判定 = **PASSED**（七条判据全真）⇒ 可收口。"""
    effect = _evidence()["effect"]
    assert effect["verdict"] == "PASSED", effect
    for key in (
        "baseline_is_deterministic",
        "graphic_changes_the_picture",
        "mode_change_changes_the_picture",
        "same_graphic_reproducible",
        "turning_the_graphic_off_restores_the_baseline",
        "pre_mode_does_not_render_the_result",
        "instrument_works",
    ):
        assert effect[key] is True, (key, effect)


def test_p166_the_graphic_actually_changes_the_picture() -> None:
    """门槛（**核心**）：改前 `33438` → 改后 **`81236`** 字节（≈**2.4×**）。"""
    before = _step("01_baseline")
    after = _step("03_after_graphic_a")
    assert before["status"] == 200 and after["status"] == 200, (before, after)
    assert before["exists"] and after["exists"], (before, after)
    assert before["sha256"] != after["sha256"], "改前/改后**必须**不同"
    assert after["bytes"] > before["bytes"] * 2, (before["bytes"], after["bytes"])
    assert before["bytes"] == 33438, before["bytes"]
    assert after["bytes"] == 81236, after["bytes"]


def test_p166_the_current_mode_really_drives_the_picture() -> None:
    """门槛：**换取值 ⇒ 画面真的换**，且**同取值可复现**。

    ⚠️ 只换 `CURRENT_MODE`（`TYPE_OF_DISPLAY` 逐字相同）—— 这正是 R155 的变体选择子。
    """
    a = _step("03_after_graphic_a")
    b = _step("04_after_graphic_b")
    replay = _step("05_after_graphic_a_replay")
    assert a["sha256"] != b["sha256"], "换 CURRENT_MODE 必须改变画面"
    assert replay["sha256"] == a["sha256"], "同取值必须可复现（否则截图不稳定）"
    assert a["bytes"] == replay["bytes"] == 81236, (a["bytes"], replay["bytes"])
    assert b["bytes"] == 84494, b["bytes"]


def test_p166_the_baseline_is_deterministic_and_restorable() -> None:
    """门槛（**噪声地板**）：基线连拍两次 **逐字节相同**；图形关掉 ⇒ **回到基线**。

    ⚠️ 这一条把「字节差异一定有语义」从**假设**变成**实测**：
    本批实测的噪声地板 = **0** 字节。
    """
    one = _step("01_baseline")
    two = _step("02_baseline_repeat")
    off = _step("06_graphic_off_again")
    assert one["sha256"] == two["sha256"], "同一状态连拍两次不一致 ⇒ 字节差异不能当证据"
    assert one["bytes"] == two["bytes"], (one["bytes"], two["bytes"])
    assert off["sha256"] == one["sha256"], "图形关掉后必须回到基线"


def test_p166_the_pre_mode_does_not_render_the_result() -> None:
    """门槛：`SET_MODE: "pre"` ⇒ 结果**画不出来**（与两个结果视图都不同）。

    ⇒ 效果确实来自 **post 模式**（而不是「只要调过 `RESULTGRAPHIC` 就会变」）。
    """
    pre = _step("07_pre_mode_with_graphic")
    a = _step("03_after_graphic_a")
    b = _step("04_after_graphic_b")
    assert pre["exists"] and pre["status"] == 200, pre
    assert pre["sha256"] not in {a["sha256"], b["sha256"]}, "pre 模式画出了结果 ⇒ 结论要重写"
    assert pre["bytes"] < a["bytes"] / 2, (pre["bytes"], a["bytes"])


def test_p166_the_positive_control_passed() -> None:
    """门槛（**方法学必需**）：阳性对照通过 ⇒ 截图**确实**能看见显示变化。

    ⚠️ 没有这条，「改前/改后不同」就**不能**当证据 —— 那可能只是截图不稳定。
    """
    control = _evidence()["control"]
    assert control["instrument_works"] is True, control
    rows = control["rows"]
    assert len(rows) == 2, rows
    on, off = rows
    assert on["elem_number"] is True and off["elem_number"] is False, rows
    assert on["display_status"] == 200 and off["display_status"] == 200, rows
    assert on["sha256"] != off["sha256"], "阳性对照必须产生**不同**的截图"
    assert off["sha256"] == _step("01_baseline")["sha256"], "对照组应等于基线（图形全关）"


def test_p166_the_probed_modes_are_both_documented() -> None:
    """门槛：两个取值**都**在 R155 的手册取值表里（不是随便挑的）。"""
    document = _evidence()
    known = set(json.loads(MODES_EVIDENCE.read_text(encoding="utf-8"))["modes"])
    assert document["mode_a"] in known, document["mode_a"]
    assert document["mode_b"] in known, document["mode_b"]
    assert document["mode_a"] != document["mode_b"]


def test_p166_the_root_cause_is_the_missing_type_of_display() -> None:
    """门槛（**R159 的成因**）：打开 / 关闭请求体的差别**只**在 `OPT_CHECK`。"""
    document = _evidence()
    on = document["graphic_block"]["TYPE_OF_DISPLAY"]
    off = document["graphic_off_block"]["TYPE_OF_DISPLAY"]
    assert set(on) == set(off), (sorted(on), sorted(off))
    assert all(block.get("OPT_CHECK") is True for block in on.values()), on
    assert all(block.get("OPT_CHECK") is False for block in off.values()), off
    assert "TYPE_OF_DISPLAY" in document["finding"]["root_cause_of_r157"], document["finding"]


def test_p166_the_run_left_no_residue() -> None:
    """门槛：跑后哨兵 6 项**逐项一致**（视图类操作**不**动模型 ⇒ 零残留）。"""
    sentinel = _evidence()["sentinel"]
    assert sentinel["unchanged"] is True, sentinel
    assert sentinel["before"] == sentinel["after"], sentinel
    assert set(sentinel["before"]) == set(sentinel["keys"]), sentinel


# ===== 2. 离线自洽 + 零请求 =====


def test_p166_the_offline_check_passes() -> None:
    """门槛：`--check` 退出码 0（证据齐备 + 七条件都在 + 与数据侧一致）。"""
    result = subprocess.run(
        [sys.executable, str(TOOL), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "纯 API 路径存在" in result.stdout, result.stdout


def test_p166_the_default_run_is_a_dry_run() -> None:
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


# ===== 3. 四处记录必须一致（数据侧 / 主指标 / 文档）=====


def test_p166_the_endpoint_yaml_and_manifest_are_closed() -> None:
    """门槛（**收口**）：端点 YAML `untested → verified`；`manifest` 派生一致。"""
    text = ENDPOINT_YAML.read_text(encoding="utf-8")
    assert "availability: verified" in text, "必须收口"
    assert "verified_on: [gen-local]" in text, text
    assert "R159" in text and "P166" in text, "必须写明裁决 / 批次"
    assert "TYPE_OF_DISPLAY" in text, "必须写明成因（缺 TYPE_OF_DISPLAY）"
    entry = next(
        row
        for row in json.loads(MANIFEST.read_text(encoding="utf-8"))["endpoints"]
        if row["key"] == "VIEW.RESULTGRAPHIC"
    )
    assert entry["availability"] == "verified", entry
    assert entry["verified_on"] == ["gen-local"], entry


def test_p166_the_sibling_view_endpoints_record_the_finding() -> None:
    """门槛：`CAPTURE` 写明 `SET_MODE` 的语义；`SELECT` 写明「**不是**激活入口」。"""
    capture = CAPTURE_YAML.read_text(encoding="utf-8")
    assert "R159" in capture, "CAPTURE 必须记录 SET_MODE 的实测语义"
    assert "SET_MODE" in capture and "post" in capture, capture
    select = SELECT_YAML.read_text(encoding="utf-8")
    assert "R159" in select and "P166" in select, "SELECT 必须记录离线结论"
    assert "不是" in select, "必须写明它**不是**激活 / 选择结果视图的入口"
    assert "NODE_LIST" in select, "必须留下手册响应示例作为依据"


def test_p166_the_main_indicator_is_backfilled() -> None:
    """门槛（**主指标回填**）：`61 / 71` → `67 / 71`（**R159**），`VIEW.RESULTGRAPHIC` 不再是挡点。

    ⚠️ **P167 / R160** 再把 `POST.TABLE` 收口 ⇒ **`68 / 71`**（被挡 **3** · 挡点端点 **13**）；
    ⚠️ **P174 / R166** 再收口 `POST.STEELCODECHECK` ⇒ **`69 / 71`**（被挡 **2** · 挡点 **4**）。
    本用例的判据是「**R159 的收益仍在**」，故按**现值**断言并逐条核 R159 的那 6 个 Operation。
    """
    spec = importlib.util.spec_from_file_location("check_operation_availability", AVAILABILITY_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    document: dict[str, Any] = module.compute()
    assert document["available"] == 69, document["available"]
    assert document["blocked"] == 2, document["blocked"]
    assert document["blocker_endpoint_count"] == 4, sorted(document["blocker_endpoints"])
    assert "VIEW.RESULTGRAPHIC" not in document["blocker_endpoints"], document["blocker_endpoints"]
    for name in (
        "VIEW.DEFORMED_MODEL",
        "VIEW.DISPLACEMENT",
        "VIEW.FORCE",
        "VIEW.MODE_SHAPE",
        "VIEW.REACTION",
        "VIEW.STRESS",
    ):
        assert name in document["available_operations"], name


def test_p166_the_ruling_and_the_ledger_register_it() -> None:
    """门槛：`docs/07` §16.1 登记 **R159**；`registry/README.md` §8.20 同步。"""
    docs = DOCS_07.read_text(encoding="utf-8")
    assert "**R159**" in docs, "R159 必须登记"
    assert "probe_view_result_post.py" in docs, "必须留下可复算的工具"
    assert "registry/live/view_result_post_probe.json" in docs, "必须留下证据路径"
    ledger = REGISTRY_README.read_text(encoding="utf-8")
    assert "8.20" in ledger, "数据侧账本必须新增一节"
    assert "TYPE_OF_DISPLAY" in ledger, "必须记下成因"
