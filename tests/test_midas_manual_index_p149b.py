"""P149-B：**第二个模板来源**（上游 NX 手册抽取）与**多来源**复算（可执行判定）。

权威来源
--------
- `docs/reports/P149-A_端点方法集实测修正与分母重算_v1.0.md` §5（P149-B 的下一步）。
- `MIDAS_API_Online_Manual_Gen_NX_v1.0.json`（本批新增：上游 NX 手册的**机械抽取**）。
- `registry/tools/sync_manual_index.py`（生成器：`--write` / `--check`）·
  `registry/tools/check_write_templates.py`（**多来源**逐条复算）。

本文件的**可执行判定**
--------------------
1. **第二来源存在且可追溯**：含来源指纹（`source.sha256` / `source.bytes`）与 `stats`；
   端点 **841**（有示例 **607** · 有方法集 **629** · 示例总数 **1488**）。
2. **复算一致**：`sync_manual_index.py --check` 退出码 0（已落盘 == 机械结果）。
3. **多来源查表**：`check_write_templates.manual_examples()` 同时覆盖两个来源 ——
   新来源独有的 URI 可取值，既有来源的 URI **仍**可取值（合并、先到先得，不互相覆盖）。
4. **URI 归一**：`DB/REBB` 与 `/db/REBB` 视作同一路由（`normalize_uri()`）。
5. **无回归**：既有 57 条模板在**多来源**复算下仍 **0** 错。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录（两个上游来源与数据侧工具都在这里）。"""

NEW_SOURCE_PATH = REPO_ROOT / "MIDAS_API_Online_Manual_Gen_NX_v1.0.json"
"""P149-B 的第二个来源（由 `registry/tools/sync_manual_index.py` 生成）。"""

INDEX_TOOL_PATH = REPO_ROOT / "registry" / "tools" / "sync_manual_index.py"
"""第二来源的生成器（`--check` 断言已落盘 == 机械结果）。"""

CHECK_TOOL_PATH = REPO_ROOT / "registry" / "tools" / "check_write_templates.py"
"""模板复算工具（P149-B 起为**多来源**）。"""

EXPECTED_STATS = {
    "endpoints": 841,
    "with_examples": 607,
    "with_methods": 629,
    "examples_total": 1488,
}
"""第二来源的规模（机械抽取的确定性结果）。"""

NEW_SOURCE_ONLY_URI = "DB/REBB"
"""只在新来源里出现的路由（既有来源没有 `db/REBB` 的条目）—— 用于验证多来源查表。"""

LEGACY_URI = "db/POGD"
"""只在既有来源里出现的路由（P147 的模板用它）—— 用于验证合并**不**丢既有来源。"""


def _load(path: Path, name: str):
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ===== 1. 第二来源存在且可追溯（判定 1）=====


def test_p149b_the_second_source_is_present_and_traceable() -> None:
    """门槛：第二来源含来源指纹与规模统计（841 / 607 / 629 / 1488）。"""
    document = json.loads(NEW_SOURCE_PATH.read_text(encoding="utf-8"))
    source = document["source"]
    assert len(source["sha256"]) == 64
    assert int(source["bytes"]) > 1_000_000
    assert source["path"].endswith(".md")
    assert document["stats"] == EXPECTED_STATS
    # 每条目都必须有 uri 与 examples 数组（形状与既有来源一致）
    for entry in document["endpoints"]:
        assert entry["input_uri"], entry
        assert isinstance(entry["examples"], list), entry["input_uri"]
        for example in entry["examples"]:
            assert isinstance(example["json"], str), entry["input_uri"]


# ===== 2. 复算一致（判定 2）=====


def test_p149b_the_index_tool_check_is_green() -> None:
    """门槛：`sync_manual_index.py --check` 退出码 0（已落盘 == 机械结果）。"""
    completed = subprocess.run(  # noqa: S603
        [sys.executable, str(INDEX_TOOL_PATH), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stdout[-800:]
    assert "✅" in completed.stdout


# ===== 3. 多来源查表（判定 3 / 4）=====


def test_p149b_the_lookup_covers_both_sources() -> None:
    """门槛：`manual_examples()` 同时覆盖两个来源；URI 按 `normalize_uri()` 归一。"""
    tool = _load(CHECK_TOOL_PATH, "structai_check_write_templates_p149b")
    table = tool.manual_examples(REPO_ROOT)
    # 新来源独有的路由：归一化后可查
    assert tool.normalize_uri(NEW_SOURCE_ONLY_URI) in table
    assert table[tool.normalize_uri(NEW_SOURCE_ONLY_URI)]
    # 既有来源的路由：合并**不**丢
    assert tool.normalize_uri(LEGACY_URI) in table
    assert table[tool.normalize_uri(LEGACY_URI)]
    # 归一：`DB/X` 与 `/db/X` 同一路由
    assert tool.normalize_uri("DB/REBB") == tool.normalize_uri("/db/REBB")
    # 新来源的示例可取到条目
    document = json.loads(NEW_SOURCE_PATH.read_text(encoding="utf-8"))
    entry = next(item for item in document["endpoints"] if item["input_uri"] == NEW_SOURCE_ONLY_URI)
    example = entry["examples"][0]
    wrapper = json.loads(example["json"])
    inner = next(iter(wrapper.values()))
    item_id = str(next(iter(inner)))
    item = tool.manual_item(
        table, uri=NEW_SOURCE_ONLY_URI, example=example["name"], item_id=item_id
    )
    assert isinstance(item, dict) and item, (NEW_SOURCE_ONLY_URI, example["name"])


# ===== 4. 无回归（判定 5）=====


def test_p149b_the_existing_templates_still_recompute_with_two_sources() -> None:
    """门槛：既有模板在**多来源**复算下仍 0 错（57 条 / 101 body / 23 references / 4 self）。"""
    tool = _load(CHECK_TOOL_PATH, "structai_check_write_templates_p149b_recompute")
    errors, _notes, counts = tool.check(REPO_ROOT)
    assert errors == [], "\n".join(errors)
    assert counts["templates"] == 57
    assert counts["bodies"] == 101
    assert counts["references"] == 23
    assert counts["self_references"] == 4
    assert counts["unverifiable"] == 0
