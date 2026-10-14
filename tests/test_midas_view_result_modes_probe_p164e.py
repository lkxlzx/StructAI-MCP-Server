"""P164-e：`VIEW.RESULTGRAPHIC` 真机重测探针的**离线**判定（**零请求**）。

本文件钉住的事实
----------------
1. **硬闸门真的会拦**：`CURRENT_MODE` 不在手册取值表里 ⇒ 探针**发请求之前**退出码 **3**
   —— 这正是把 **R150** 那个 `"displacement"` 挡在门外的机制。
2. **崩溃族路径真的会拦**：探针自带 `httpx.Client`（护栏管不到）⇒ 它**自己**查一次
   `app/**` 的路径表，命中崩溃族 ⇒ 退出码 **4**。
3. **默认零请求**：不带 `--probe` 只预演；**不**写任何证据文件。
4. **不**升级 `availability`：探针只产出「合法取值是否被接受」这一步的证据。

⚠️ 真机那一步（`--probe`）**需要实例**，本文件**不**跑它。
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

TOOL = REPO_ROOT / "registry" / "tools" / "probe_view_result_modes.py"
"""探针（默认预演 / `--probe` 真机 / `--check` 离线自洽）。"""

MODES_EVIDENCE = REPO_ROOT / "registry" / "live" / "view_result_modes.json"
"""取值表（**R155**）。"""

PROBE_EVIDENCE = REPO_ROOT / "registry" / "live" / "view_result_modes_probe.json"
"""探针落点（本文件**不**允许它出现）。"""

REJECTED = "displacement"
"""R150 实测被拒的取值。"""

CRASH_PATH = "/DESIGN/RC/KDS-41-20-2022/BD-ANAL"
"""原生崩溃族路径（`wg_db.dll` `0xc0000005` @ `0x2d97e5c`）。"""


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    """跑探针（**不**给 `--probe`）。"""
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
        check=False,
    )


def _load_tool() -> Any:
    """按路径装载探针模块（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location("probe_view_result_modes", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ===== 1. 离线自洽 =====


def test_p164e_the_offline_check_passes() -> None:
    """门槛：`--check` 退出码 0，且**明确**报告「被拒取值不在表内」。"""
    result = _run("--check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "36 个取值" in result.stdout, result.stdout
    assert "不在表内" in result.stdout, result.stdout


# ===== 2. 硬闸门：非法取值发请求之前就被拒 =====


def test_p164e_an_undocumented_mode_is_refused_before_any_request() -> None:
    """门槛（**R150 的成因被挡住**）：`--modes displacement` ⇒ 退出码 **3**，零请求。"""
    result = _run("--modes", REJECTED)
    assert result.returncode == 3, result.stdout + result.stderr
    assert REJECTED in result.stdout, result.stdout
    assert "不在手册取值表里" in result.stdout, result.stdout


def test_p164e_the_gate_is_the_manual_table_itself() -> None:
    """门槛：闸门判据 = **取值表**（不是硬编码名单）—— 表里有就放行、没有就拒。"""
    table = json.loads(MODES_EVIDENCE.read_text(encoding="utf-8"))
    assert REJECTED not in table["modes"], "被拒取值混进表里了 ⇒ R155 结论要重写"
    module = _load_tool()
    # 表内取值：放行（不抛）
    module.guard_modes(("DeformedShape",), table)
    # 表外取值：拒绝
    import pytest  # noqa: PLC0415

    with pytest.raises(SystemExit) as caught:
        module.guard_modes((REJECTED,), table)
    assert caught.value.code == 3


# ===== 3. 崩溃族路径自检（探针自带 httpx ⇒ 护栏管不到，必须自查）=====


def test_p164e_a_native_crash_path_is_refused() -> None:
    """门槛：`--path <崩溃族路径>` ⇒ 退出码 **4**（**不**打崩 MIDAS）。"""
    result = _run("--path", CRASH_PATH)
    assert result.returncode == 4, result.stdout + result.stderr
    assert "崩溃族" in result.stdout, result.stdout


def test_p164e_the_crash_path_check_reuses_the_app_table() -> None:
    """门槛：自查**复用** `app/**` 的路径表（**不**另抄一份字面量）。"""
    module = _load_tool()
    assert module.native_crash_key_of(CRASH_PATH) == "DESIGN.RC.KDS-41-20-2022.BD-ANAL"
    assert module.native_crash_key_of("/DB/NODE") is None
    assert module.native_crash_key_of(module.PATH) is None


# ===== 4. 默认零请求 =====


def test_p164e_the_default_run_is_a_dry_run_and_writes_nothing() -> None:
    """门槛：默认（无 `--probe`）只预演 —— 打印**表内**取值构成的请求体，**零**落盘。"""
    assert not PROBE_EVIDENCE.exists(), "预演不该留下证据文件"
    result = _run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "预演" in result.stdout, result.stdout
    assert "DisplacementContour" in result.stdout, result.stdout
    assert "LOAD_CASE_COMB" in result.stdout, result.stdout
    assert not PROBE_EVIDENCE.exists(), "预演**不**允许写证据文件"
