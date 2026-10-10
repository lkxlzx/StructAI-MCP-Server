#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
**机械**生成写路径请求体模板（P149-B：为「已具备可判形态但缺模板」的端点补齐）。

为什么需要这个工具
------------------
P148 及以前的模板是**逐批手工**落盘的（每批 10~13 条）。P149-A 修正方法集后，池子里还有
**205** 个端点「已具备可判形态」却**既无 Transformer 又无模板**，其中 **192** 个在上游手册里
有**可用示例**（旧来源 122 · 仅新来源 70）、**13** 个没有可用示例。逐条手工誊抄既不可行、
也无法复算，故本工具把这一步**机械化**：

1. **选点**（数据驱动，逐条可复算）：读 `registry/manifest.json` + `registry/live/live_methods.json`
   + Registry，按下面的判据算出「**仍**缺模板」的池子（P149-B2 落盘后 = **202** = 留缺账本
   **189** + 无可用示例 **13**；落盘**前** = **205**）；再**减去**
   `registry/live/write_template_left_out.json` 里如实留缺的 key（那是**实测被拒 / 读不回 /
   读映射未验证 / 未取得结论**的端点，见 R101–R105 / R109–R112）。
2. **取示例**：复用 `check_write_templates.py` 的 `normalize_uri()`（**同一套口径**）与
   `MANUAL_FILENAMES`（**旧来源 → 新来源**），取**第一个**可用条目（包装键恰好 1 个 +
   内层是对象 + 条目是**非空**对象）。取不到 → 该 key 如实记原因，**不**入模板。
3. **落盘**：把生成条目与**既有**模板合并成**同一份** `registry/live/write_templates.json`
   （既有条目**内容**逐字保留；文件由本工具**统一重排**）。

池子判据（逐条可复算；与 `tests/test_midas_write_coverage_p148.py::_derived_candidates()` 同源）
--------------------------------------------------------------------------------------------
`enabled` ∧ 非 `destructive` ∧ 有写方法（`POST` / `PUT`）∧ 非 `delete_all_via_body` ∧
`live_methods` 非空（本 build 路由存在）∧ 有 `GET` ∧ 有 `read_root` ∧ 有 `DELETE` ∧
**无原生 Transformer** ∧ **无模板** ∧ 不在留缺表里。

⚠️ 「无 Transformer」这一条**不能**省：已有 Transformer 的端点（如 `DB.NODE`）靠
`derive_body()` 就能走三步链，**已经**是候选，不属于「欠账」。

用法（仓库根目录执行；**只依赖标准库 + `app/`**）
-----------------------------------------------
    # 预演：列出会新增 / 会剔除 / 无可用示例的 key（不写盘）
    python registry/tools/sync_write_templates.py

    # 写回模板文件
    python registry/tools/sync_write_templates.py --write

    # 断言：已落盘 == 机械结果（CI 用）
    python registry/tools/sync_write_templates.py --check

纪律
----
* 生成的条目一律 `source.kind = "manual_example"`（**逐字节**照抄示例条目，**零** `adjustments`、
  **零**前置链）—— 需要前置链 / 改值的端点**不**由本工具处理（仍走逐批手工 + 实测）。
* 留缺 key（`write_template_left_out.json`）**必须**没有模板；本工具会**主动剔除**它们的旧模板
  （若有），保证「被拒的端点不入候选、不污染 limit」。
* 本工具**不**改任何判定：`verification_status` / `availability` / `products` / `methods` 一律不动。
* 无可用示例的原因**如实**分三类：`no_manual_entry`（两个来源都没有该 URI）·
  `example_item_empty`（示例条目是空对象）· `example_shape_unusable`（包装键 ≠ 1 或内层不是对象）。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple

REPO_DEFAULT = "."
TEMPLATES_RELATIVE = "live/write_templates.json"
LEFT_OUT_RELATIVE = "live/write_template_left_out.json"
MANIFEST_FILENAME = "manifest.json"
LIVE_METHODS_RELATIVE = "live/live_methods.json"
CHECK_TOOL_RELATIVE = "registry/tools/check_write_templates.py"
RETRIEVED_AT = "2026-10-10"

NOTE_MARKER = "P149-B（第二子批）："
NOTE_TEXT = (
    "本文件的条目**由 `registry/tools/sync_write_templates.py` 机械生成/维护** —— 对"
    "「已具备可判形态但**既无 Transformer 又无模板**」的端点，按「旧来源 → 新来源」顺序取"
    "**第一个**可用手册示例条目，原样照抄（`manual_example`、零 adjustments、零前置链）；"
    "实测被拒 / 读不回 / 无可用示例的端点列入 `registry/live/write_template_left_out.json`，"
    "本工具会**主动剔除**它们的模板。改本文件必须走该工具的 --write，并用 --check 断言一致。"
)
WRITE_METHODS = ("POST", "PUT")
PRODUCT = "GEN_NX"

GAP_NO_ENTRY = "no_manual_entry"
GAP_EMPTY_ITEM = "example_item_empty"
GAP_SHAPE = "example_shape_unusable"


class Pick(NamedTuple):
    """一个可用示例的定位（**逐字节**照抄 `item`）。"""

    source_file: str
    source: dict[str, Any]
    example: str
    item_id: str
    item: dict[str, Any]


class Analysis(NamedTuple):
    """一次池子分析的结果（全部可复算）。"""

    registry: Any
    tool: Any
    picks: dict[str, Pick]
    gaps: list[tuple[str, str]]
    wrappers: dict[str, str]

    @property
    def pool(self) -> list[str]:
        """池子 = 可生成的 key + 无可用示例的 key（升序）。"""
        return sorted(list(self.picks) + [key for key, _ in self.gaps])


def load_module(path: Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法装载 {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_registry(repo: Path) -> Any:
    """数据侧 Registry（`registry/` 的唯一权威来源）。"""
    sys.path.insert(0, str(repo))
    sys.path.insert(0, str(repo / "tests"))
    import midas_p119_p126_support as support  # noqa: PLC0415

    return support.registry()


def has_transformer(key: str) -> bool:
    """该端点是否**已有**原生 Transformer（有 → 已经是候选，**不**属于本池）。

    ⚠️ 判据与 `tests/test_midas_write_coverage_p148.py` 的 `_derived_candidates()` 同源：
    「既无 Transformer 又无模板」才是写路径的**欠账**；已有 Transformer 的端点
    （如 `DB.NODE`）靠 `derive_body()` 就能走三步链，**不**在本批的补齐范围内。
    """
    from app.infrastructure.adapters.midas.transforms import TRANSFORMER_REGISTRY  # noqa: PLC0415
    from app.infrastructure.adapters.midas.write_probe import transformer_name_for  # noqa: PLC0415

    return TRANSFORMER_REGISTRY.get(transformer_name_for(key)) is not None


def source_entries(repo: Path, tool: Any) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    """`归一化 uri` → `[(来源文件名, 条目)]`（顺序 = `MANUAL_FILENAMES`，**旧来源在前**）。"""
    table: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for filename in tool.MANUAL_FILENAMES:
        path = repo / filename
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for entry in payload["endpoints"]:
            uri = tool.normalize_uri(entry.get("input_uri") or "")
            if uri:
                table.setdefault(uri, []).append((filename, entry))
    return table


def _wrapper_items(example: Any) -> dict[str, Any] | None:
    """示例 JSON → 内层 `{编号: 条目}`（包装键 ≠ 1 / 内层不是对象 → `None`）。"""
    try:
        wrapper = json.loads(example["json"])
    except (KeyError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(wrapper, dict) or len(wrapper) != 1:
        return None
    inner = next(iter(wrapper.values()))
    return inner if isinstance(inner, dict) else None


def pick_example(
    tool: Any, candidates: list[tuple[str, dict[str, Any]]], *, uri: str
) -> Pick | None:
    """取**第一个**可用示例条目 → `Pick`（取不到 → `None`）。

    顺序 = 「来源顺序（旧 → 新）→ 条目顺序 → 示例顺序 → 编号升序」，**第一个**命中即取，
    故结果对同一份数据**逐字节**确定。判据与 `check_write_templates.manual_item()` 一致
    （包装键恰好 1 个 + 内层是对象），并额外要求**条目非空**（空对象 = 无内容可写）。
    """
    for filename, entry in candidates:
        url = str(entry.get("url") or "")
        for example in entry.get("examples") or []:
            name = str(example.get("name") or "")
            inner = _wrapper_items(example)
            if inner is None:
                continue
            for item_id in sorted(inner, key=str):
                item = inner[item_id]
                if isinstance(item, dict) and item:
                    source = {
                        "kind": "manual_example",
                        "uri": str(entry.get("input_uri") or ""),
                        "example": name,
                        "example_id": str(item_id),
                        "url": url,
                        "retrieved_at": RETRIEVED_AT,
                    }
                    return Pick(filename, source, name, str(item_id), item)
    return None


def gap_reason(candidates: list[tuple[str, dict[str, Any]]]) -> str:
    """无可用示例的**如实**归类（见模块文档「纪律」）。"""
    if not candidates:
        return GAP_NO_ENTRY
    saw_example = False
    for _filename, entry in candidates:
        for example in entry.get("examples") or []:
            inner = _wrapper_items(example)
            if inner is None:
                continue
            saw_example = True
            if not any(isinstance(item, dict) and item for item in inner.values()):
                continue
            return GAP_SHAPE  # 理论不可达：`pick_example()` 会先命中
    return GAP_EMPTY_ITEM if saw_example else GAP_SHAPE


def analyze(repo: Path) -> Analysis:
    """按判据算出池子（只读）。"""
    registry = load_registry(repo)
    tool = load_module(repo / CHECK_TOOL_RELATIVE, "structai_check_write_templates_p149b")
    entries = source_entries(repo, tool)
    live_by_key = json.loads(
        (repo / "registry" / LIVE_METHODS_RELATIVE).read_text(encoding="utf-8")
    )["endpoints"]
    manifest = json.loads((repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    wrappers = {
        str(item["key"]): str((item.get("wrapper") or {}).get("write") or "")
        for item in manifest["endpoints"]
    }

    picks: dict[str, Pick] = {}
    gaps: list[tuple[str, str]] = []
    for key in sorted(registry.keys()):
        definition = registry.endpoint(key)
        if not definition.enabled or definition.destructive:
            continue
        methods = set(registry.methods_for(key=key, product=PRODUCT))
        if not (methods & set(WRITE_METHODS)):
            continue
        try:
            if registry.resolve(key=key, product=PRODUCT).delete_all_via_body:
                continue
        except Exception:  # noqa: BLE001 - 该产品不可得
            continue
        if not live_by_key.get(key, {}).get("live_methods"):
            continue
        if "GET" not in methods or not definition.read_root or "DELETE" not in methods:
            continue
        if registry.write_template(key) is not None or has_transformer(key):
            continue
        candidates = entries.get(tool.normalize_uri(str(definition.uri)), [])
        found = pick_example(tool, candidates, uri=str(definition.uri))
        if found is None:
            gaps.append((key, gap_reason(candidates)))
        else:
            picks[key] = found
    return Analysis(registry, tool, picks, gaps, wrappers)


def read_left_out(repo: Path) -> dict[str, str]:
    """留缺表（`key → 原因`；文件不存在 → 空表）。"""
    path = repo / "registry" / LEFT_OUT_RELATIVE
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(key): str(reason) for key, reason in (payload.get("keys") or {}).items()}


def build(repo: Path) -> tuple[dict[str, Any], Analysis, list[str], list[str]]:
    """生成完整模板文档 → `(文档, 分析, 新增 key, 被剔除的留缺 key)`。"""
    analysis = analyze(repo)
    left_out = read_left_out(repo)
    document = json.loads((repo / "registry" / TEMPLATES_RELATIVE).read_text(encoding="utf-8"))
    templates: dict[str, Any] = dict(document["templates"])

    removed: list[str] = []
    for key in sorted(left_out):
        if key in templates:
            templates.pop(key)
            removed.append(key)

    added: list[str] = []
    for key in sorted(analysis.picks):
        if key in templates or key in left_out:
            continue
        pick = analysis.picks[key]
        templates[key] = {
            "wrapper": analysis.wrappers.get(key) or "Assign",
            "source": pick.source,
            "adjustments": [],
            "body": pick.item,
            "prerequisites": [],
        }
        added.append(key)

    document["templates"] = dict(sorted(templates.items()))
    document["note"] = [
        str(item) for item in document["note"] if not str(item).startswith(NOTE_MARKER)
    ] + [NOTE_MARKER + NOTE_TEXT]
    return document, analysis, added, removed


def render(document: dict[str, Any]) -> str:
    """产物文本（统一缩进，便于逐行 diff）。"""
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=REPO_DEFAULT)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()

    document, analysis, added, removed = build(repo)
    text = render(document)
    target = repo / "registry" / TEMPLATES_RELATIVE
    current = target.read_text(encoding="utf-8")
    current_keys = set(json.loads(current)["templates"])
    new_keys = set(document["templates"])

    by_source: dict[str, int] = {}
    for pick in analysis.picks.values():
        by_source[pick.source_file] = by_source.get(pick.source_file, 0) + 1
    by_gap: dict[str, list[str]] = {}
    for key, reason in analysis.gaps:
        by_gap.setdefault(reason, []).append(key)

    print(f"池子 = {len(analysis.pool)}（可生成 {len(analysis.picks)} + 无可用示例 {len(analysis.gaps)}）")
    print(f"  示例来源：{by_source}")
    for reason in sorted(by_gap):
        print(f"  无可用示例 [{reason}] = {len(by_gap[reason])} {by_gap[reason]}")
    print(f"模板 = {len(new_keys)}（盘面 {len(current_keys)}）")
    print(f"  将新增 = {len(added)}；将剔除（留缺）= {len(removed)} {removed[:10]}")

    if args.check and current != text:
        print("\n❌ 模板文件与机械结果不一致（请跑 --write）")
        return 1
    if args.check:
        print("\n✅ 模板文件与机械结果一致")
    if args.write:
        target.write_text(text, encoding="utf-8")
        print(f"已写入 registry/{TEMPLATES_RELATIVE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
