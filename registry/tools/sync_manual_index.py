#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把上游 NX 手册（`midas Gen API 使用手册.md`）抽成**数据侧模板来源**（P149-B）。

为什么需要这个工具
------------------
P148 及以前的模板来源**只有**一份：仓库根的 `MIDAS_API_Online_Manual_数据_v1.0.json`
（Help Center 抓取，359 个端点）。P149-A 发现 `E:\\MCP\\MIDAS-API-Online-Manual\\manual\\
midas Gen API 使用手册.md`（12 MB）是它的**超集**：406 个 URI · 619 个 JSON Schema ·
292 个 `Request Examples` · 629 条 `Active Methods`（与 live `OPTIONS` 在 541 个可比端点里 532 个一致）。

本工具把这份手册**机械**抽成一份**与既有来源同形**的数据文件（`endpoints[].input_uri` +
`examples[].json`），使 `registry/tools/check_write_templates.py` 能对**两个来源**用同一套
`manual_item()` 逻辑逐条复算（**不**改复算口径、**不**手工誊抄）。

产物
----
`MIDAS_API_Online_Manual_Gen_NX_v1.0.json`（仓库根，与既有来源并列）：

    {
      "source": {"path": ..., "sha256": ..., "bytes": ...},
      "note": [...],
      "stats": {"endpoints": N, "with_examples": N, "with_methods": N},
      "endpoints": [
        {"input_uri": "DB/REBB", "title": "Modify Beam Rebar Data",
         "active_methods": ["POST", "GET", "PUT", "DELETE"],
         "url": "https://support.midasuser.com/hc/en-us/articles/...",
         "examples": [{"name": "Request Example 1", "json": "{\n \"Assign\": {...}\n}"}]},
        ...
      ]
    }

`examples[].json` 是**原样**的 fenced JSON 文本（与既有来源同形），因此「包装键恰好 1 个 +
条目是对象」的取值口径**完全一致**；`json_schema` 字段**不**抽取（数据侧已有 208/208 个 Schema，
模板复算只需示例）。

用法（仓库根目录执行；**只依赖标准库**）
--------------------------------------
    # 预演：报告会抽出多少端点 / 示例，并给出与既有来源的差异（不写盘）
    python registry/tools/sync_manual_index.py

    # 写回数据文件
    python registry/tools/sync_manual_index.py --write

    # 断言：已落盘 == 机械结果（CI 用）
    python registry/tools/sync_manual_index.py --check

    # 手册不在默认路径时显式指定（值不落盘）
    python registry/tools/sync_manual_index.py --manual "D:\\path\\to\\manual.md"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

DEFAULT_MANUAL = Path(r"E:\MCP\MIDAS-API-Online-Manual\manual\midas Gen API 使用手册.md")
OUTPUT_FILENAME = "MIDAS_API_Online_Manual_Gen_NX_v1.0.json"
LEGACY_FILENAME = "MIDAS_API_Online_Manual_数据_v1.0.json"

HEADING = re.compile(r"^(#{2,6})\s+(.*\S)\s*$")
CODE = re.compile(r"接口代码[:：]\s*`([^`]+)`")
URI_LINE = re.compile(r"\*\*\s*\{base url\}\s*\+\s*([^|*]+?)\s*\*\*")
METHODS_LINE = re.compile(r"^\|\s*\*\*([A-Za-z,\s]+)\*\*\s*\|\s*$")
LINK = re.compile(r"\[[^\]]*\]\((https?://[^)\s]+)\)")
FENCE = re.compile(r"^```[A-Za-z]*\s*$")
METHOD_WORDS = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH"})
EXAMPLE_SECTIONS = ("Request Examples", "Input Data Examples", "Examples")
SKIP_SECTIONS = ("Response Examples",)


def parse_manual(path: Path) -> list[dict[str, Any]]:
    """把手册解析成端点条目列表（h4/h5 标题切条目；逐条收集 uri / 方法 / URL / 示例）。"""
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    section = ""
    in_fence = False
    fence_lines: list[str] = []
    fence_target: str | None = None

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()

        if FENCE.match(stripped):
            if in_fence:
                if fence_target == "example" and current is not None and fence_lines:
                    label = str(current.get("title") or current.get("code") or "Example").strip()
                    current["examples"].append(
                        {
                            "name": f"{label} #{len(current['examples']) + 1}",
                            "json": "\n".join(fence_lines),
                        }
                    )
                in_fence = False
                fence_lines = []
                fence_target = None
            else:
                in_fence = True
                fence_lines = []
                fence_target = "example" if section in EXAMPLE_SECTIONS else None
            continue
        if in_fence:
            fence_lines.append(line)
            continue

        heading = HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            plain = title.strip("*").strip()
            if level in (4, 5) and not title.startswith("**"):
                current = {
                    "input_uri": "",
                    "title": plain,
                    "code": "",
                    "active_methods": [],
                    "url": "",
                    "examples": [],
                }
                entries.append(current)
                section = ""
                continue
            section = plain
            continue
        if current is None:
            continue

        code_match = CODE.search(line)
        if code_match and not current["code"]:
            current["code"] = code_match.group(1)
            continue

        if not current["input_uri"]:
            uri_match = URI_LINE.search(line)
            if uri_match:
                current["input_uri"] = uri_match.group(1).strip()
                continue

        if not current["active_methods"]:
            methods_match = METHODS_LINE.match(stripped)
            if methods_match:
                tokens = [
                    part.strip().upper()
                    for part in re.split(r"[,/]", methods_match.group(1))
                    if part.strip()
                ]
                if tokens and all(token in METHOD_WORDS for token in tokens):
                    current["active_methods"] = tokens
                    continue

        if not current["url"] and section.lower().startswith(("input uri", "active methods", "")):
            link = LINK.search(line)
            if link:
                current["url"] = link.group(1)

    return [entry for entry in entries if entry["input_uri"]]


def build(path: Path) -> dict[str, Any]:
    """读手册 → 产物文档（含来源指纹，便于复算与追溯）。"""
    raw = path.read_bytes()
    endpoints = parse_manual(path)
    with_examples = sum(1 for entry in endpoints if entry["examples"])
    with_methods = sum(1 for entry in endpoints if entry["active_methods"])
    return {
        "source": {
            "path": str(path),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        },
        "note": [
            "P149-B：上游 NX 手册（midas Gen API 使用手册.md）的**机械抽取**，作为写路径模板的**第二个来源**。",
            "`examples[].json` 是手册里 fenced JSON 的**原样**文本 —— 与既有来源同形，故 `manual_item()` 的取值口径一致。",
            "`json_schema` **不**抽取（数据侧已有 208/208 个请求 Schema；模板复算只需示例）。",
            "由 `registry/tools/sync_manual_index.py` 生成；改动必须走该工具的 --write，并用 --check 断言一致。",
        ],
        "stats": {
            "endpoints": len(endpoints),
            "with_examples": with_examples,
            "with_methods": with_methods,
            "examples_total": sum(len(entry["examples"]) for entry in endpoints),
        },
        "endpoints": endpoints,
    }


def render(document: dict[str, Any]) -> str:
    """产物文本（与既有来源同样的 `ensure_ascii=False` + 缩进，便于逐行 diff）。"""
    return json.dumps(document, ensure_ascii=False, indent=1) + "\n"


def legacy_uris(repo: Path) -> set[str]:
    """既有来源的 `input_uri` 集合（用于报告重叠度）。"""
    path = repo / LEGACY_FILENAME
    if not path.is_file():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(entry.get("input_uri") or "") for entry in payload["endpoints"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--manual", default=str(DEFAULT_MANUAL))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    manual = Path(args.manual)

    if not manual.is_file():
        print(f"手册不存在：{manual}", file=sys.stderr)
        print("（用 --manual 指定路径；本工具**不**联网、**不**猜路径）", file=sys.stderr)
        return 2

    document = build(manual)
    stats = document["stats"]
    print(f"手册 = {manual}")
    print(f"  sha256 = {document['source']['sha256'][:16]}… · {document['source']['bytes']} bytes")
    print(
        f"  端点 = {stats['endpoints']}（有示例 {stats['with_examples']} · 有方法集 {stats['with_methods']} · "
        f"示例总数 {stats['examples_total']}）"
    )

    target = repo / OUTPUT_FILENAME
    text = render(document)
    print(f"产物 = {OUTPUT_FILENAME}（{len(text.encode('utf-8'))} bytes）")

    existing = legacy_uris(repo)
    fresh = {str(entry["input_uri"]) for entry in document["endpoints"]}
    print(f"  与既有来源 {LEGACY_FILENAME}：共有 {len(fresh & existing)} · 仅新来源有 {len(fresh - existing)}")

    if args.check:
        if not target.is_file():
            print(f"\n❌ 产物不存在：{OUTPUT_FILENAME}")
            return 1
        if target.read_text(encoding="utf-8") != text:
            print(f"\n❌ 产物与机械结果不一致（请跑 --write）")
            return 1
        print("\n✅ 产物与机械结果一致")
    if args.write:
        target.write_text(text, encoding="utf-8")
        print(f"已写入 {OUTPUT_FILENAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
