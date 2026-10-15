"""P164-f / R157：`VIEW.RESULTGRAPHIC` 的**效果判据**（**铁律 ⓪**）—— 真机受控测量的离线判定。

结论（真机实测，2026-10-14，`gen-local`）
----------------------------------------
**表内** `CURRENT_MODE` ⇒ `200`（R150 的 `second query is wrong` **确实**是取值非法），
**但画面没变** ⇒ 效果判据 **FAILED** ⇒ `availability` **保持 `untested`**（**不**收口）。

本文件钉住的**方法学**要求（缺一不可）
--------------------------------------
1. **阳性对照**必须先通过（`VIEW.DISPLAY` 的 `ELEM_NUMBER` 开/关 ⇒ 截图字节**不同**）
   —— 否则「无差异」无法区分「原生静默空转」与「截图拍不到结果图形」。
2. **同取值可复现**（对照组 C == A）—— 排除「截图本身不稳定」。
3. **换取值无差异**（B == A）—— 这才是「空转」的证据。
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
"""仓库根目录。"""

TOOL = REPO_ROOT / "registry" / "tools" / "probe_view_result_effect.py"
"""效果判据探针（默认预演 / `--probe` 真机 / `--check` 离线自洽）。"""

EVIDENCE = REPO_ROOT / "registry" / "live" / "view_result_effect_probe.json"
"""真机证据。"""

MODES_EVIDENCE = REPO_ROOT / "registry" / "live" / "view_result_modes.json"
"""取值表（**R155**）。"""

ENDPOINT_YAML = REPO_ROOT / "registry" / "common" / "view" / "RESULTGRAPHIC.yaml"
"""端点数据侧条目。"""

DOCS_07 = REPO_ROOT / "docs" / "07_开发方案与任务续接_v1.0.md"
"""裁决表（§16.1）。"""

REGISTRY_README = REPO_ROOT / "registry" / "README.md"
"""数据侧账本。"""


def _evidence() -> dict:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


# ===== 1. 效果判据的三个条件 =====


def test_p164f_the_effect_verdict_is_failed() -> None:
    """门槛：真机实测判定 = **FAILED**（`200` 但画面没变）⇒ **不**收口。"""
    effect = _evidence()["effect"]
    assert effect["verdict"] == "FAILED", effect
    assert effect["graphic_changed_when_mode_changed"] is False, effect
    assert effect["same_mode_reproducible"] is True, effect


def test_p164f_the_positive_control_passed() -> None:
    """门槛（**方法学必需**）：阳性对照通过 ⇒ 截图**确实**能看见显示变化。

    ⚠️ 没有这条，「换取值无差异」就**不能**当证据 —— 那可能只是截图拍不到结果图形。
    """
    control = _evidence()["control"]
    assert control["instrument_works"] is True, control
    rows = control["rows"]
    assert len(rows) == 2, rows
    on, off = rows
    assert on["elem_number"] is True and off["elem_number"] is False, rows
    assert on["display_status"] == 200 and off["display_status"] == 200, rows
    assert on["sha256"] != off["sha256"], "阳性对照必须产生**不同**的截图"
    assert on["bytes"] != off["bytes"], rows


def test_p164f_the_three_resultgraphic_captures_are_byte_identical() -> None:
    """门槛：A/B/C 三次截图**字节完全相同**（换取值不换画面 + 同取值可复现）。"""
    rows = _evidence()["rows"]
    assert [row["tag"] for row in rows] == ["A", "B", "C"], rows
    assert [row["resultgraphic_status"] for row in rows] == [200, 200, 200], rows
    hashes = {row["sha256"] for row in rows}
    assert len(hashes) == 1, f"出现差异 ⇒ 空转结论要重写：{hashes}"
    assert all(row["exists"] and row["bytes"] > 0 for row in rows), rows


def test_p164f_the_probed_modes_are_both_documented() -> None:
    """门槛：两个取值**都**在 R155 的取值表里（不是随便挑的）。"""
    document = _evidence()
    known = set(json.loads(MODES_EVIDENCE.read_text(encoding="utf-8"))["modes"])
    assert document["mode_a"] in known, document["mode_a"]
    assert document["mode_b"] in known, document["mode_b"]
    assert document["mode_a"] != document["mode_b"]


# ===== 2. 离线自洽 + 零副作用 =====


def test_p164f_the_offline_check_passes() -> None:
    """门槛：`--check` 退出码 0（证据齐备且三条件都在）。"""
    result = subprocess.run(
        [sys.executable, str(TOOL), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "静默空转" in result.stdout, result.stdout


def test_p164f_the_default_run_is_a_dry_run() -> None:
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


# ===== 3. 三处记录必须一致 =====


def test_p164f_the_endpoint_yaml_records_the_measured_effect() -> None:
    """门槛：端点 YAML 写明**效果判据 FAILED** 与「不空转假设」的对照要求。

    ⚠️ **P166 / R159 更新（只改现状声称、不篡改历史）**：P164-f 当时 `availability` 保持
    `untested`（本文件原文断言）；**P166 找到成因与纯 API 路径** ⇒ 收口为 `verified`。
    P164-f 的实测记录（**32023** 字节 / 阳性对照 **38869 vs 32023** / 「静默空转」）
    **必须原样保留** —— 那是历史事实，也是 R159 的出发点。
    """
    text = ENDPOINT_YAML.read_text(encoding="utf-8")
    assert "P164-f" in text, "必须留 P164-f 的记录"
    assert "静默空转" in text or "空转" in text, "必须写明实测结论"
    assert "阳性对照" in text, "必须写明方法学要求（否则结论不可信）"
    assert "availability: verified" in text, "P166 / R159 已收口 ⇒ availability 升为 verified"
    assert "P166" in text and "R159" in text, "收口必须可回溯到批次 / 裁决编号"


def test_p164f_the_ruling_and_the_ledger_register_it() -> None:
    """门槛：`docs/07` §16.1 登记 **R157**；`registry/README.md` §8.19 同步。"""
    docs = DOCS_07.read_text(encoding="utf-8")
    assert "**R157**" in docs, "R157 必须登记"
    assert "probe_view_result_effect.py" in docs, "必须留下可复算的工具"
    assert "registry/live/view_result_effect_probe.json" in docs, "必须留下证据路径"
    ledger = REGISTRY_README.read_text(encoding="utf-8")
    assert "静默空转" in ledger, "数据侧账本必须记下实测结论"
