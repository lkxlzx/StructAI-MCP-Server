#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`OPE.LINEBMLD` 的 `Argument.TYPE` 枚举收口（P179 · `docs/07` **R172**）。

为什么
------
`registry/schema/products/gen_nx/ope/LINEBMLD.json` 的 `Argument.TYPE` 只声明
`{"type": "string"}`，**没有** `enum` ⇒ `spec_guard` 对**任何**字符串都放行
（包括伪值）。而手册**自己的规格表**已经把 9 个取值**逐条列出** ⇒ 可复算，不该留缺。

来源（**唯一**，机械扫描，无人工取值）
--------------------------------------
`MIDAS_API_Online_Manual_数据_v1.0.json` 里 `input_uri == "ope/LINEBMLD"` 的条目，
`specifications` 表中 `Key == '"TYPE"'` 且 `Value Type == "String"` 的那一行，
从其 `Description` 里按 `• ...: "VALUE"` 的格式**逐条**提取。

⚠️ **同名不同义**（P171 / R164 的教训）：`Argument.LOAD.TYPE` 与 `Argument.ECCEN.TYPE`
是 **Integer**，**不**属于本枚举 ⇒ 本工具只取规格表第 3 行（`No. == "3"`），
不按字段名递归收集。

幂等 / 用法
-----------
    python registry/tools/sync_linebmld_type_enum.py            # 预演
    python registry/tools/sync_linebmld_type_enum.py --write    # 写回
    python registry/tools/sync_linebmld_type_enum.py --check    # 断言「已落盘 == 机械结果」

⚠️ **枚举只增不减**：机械结果丢掉已落盘取值 ⇒ 拒绝写入。
只依赖标准库。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any, Final

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
MANUAL: Final[str] = "MIDAS_API_Online_Manual_数据_v1.0.json"
SCHEMA_RELATIVE: Final[str] = "registry/schema/common/ope/LINEBMLD.json"
POINTER: Final[tuple[str, ...]] = (
    "schema",
    "LINEBMLD",
    "properties",
    "Argument",
    "properties",
    "TYPE",
)
ENDPOINT: Final[str] = "OPE.LINEBMLD"
VALUE_PATTERN: Final[re.Pattern[str]] = re.compile(r'•[^:]*:\s*"([A-Z_]+)"')


def _manual_values() -> list[str]:
    """手册规格表第 3 行（`"TYPE"`, String）里列出的全部取值（保持原文顺序）。"""
    document = json.loads((REPO / MANUAL).read_text(encoding="utf-8"))
    for entry in document.get("endpoints") or []:
        uri = str(entry.get("input_uri") or "").strip("/").lower()
        if uri != "ope/linebmld":
            continue
        for row in entry.get("specifications") or []:
            if len(row) < 4:
                continue
            if str(row[2]).strip('"') != "TYPE" or str(row[3]).strip() != "String":
                continue
            values = VALUE_PATTERN.findall(str(row[1]))
            if values:
                return values
    return []


def _node(document: dict[str, Any]) -> dict[str, Any]:
    """按 `POINTER` 取 Schema 节点。"""
    node: Any = document
    for step in POINTER:
        node = node[step]
    return node


def is_applied(repo: pathlib.Path) -> bool:
    """`--check` 的复算入口：已落盘 == 手册规格表（供 `check_spec_enums.py` 调用）。"""
    path = repo / SCHEMA_RELATIVE
    if not path.is_file():
        return False
    document = json.loads(path.read_text(encoding="utf-8"))
    return list(_node(document).get("enum") or []) == _manual_values()


def main() -> int:
    """入口（默认预演 / `--write` / `--check`）。"""
    parser = argparse.ArgumentParser(description="按手册规格表补全 OPE.LINEBMLD 的 TYPE 枚举")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="写回 Schema")
    group.add_argument("--check", action="store_true", help="断言已落盘 == 机械结果")
    args = parser.parse_args()

    wanted = _manual_values()
    if not wanted:
        print(f"❌ 无法从 {MANUAL} 的规格表提取取值（判据失效，拒绝猜测）")
        return 1

    path = REPO / SCHEMA_RELATIVE
    document = json.loads(path.read_text(encoding="utf-8"))
    node = _node(document)
    stored = list(node.get("enum") or [])

    lost = [value for value in stored if value not in wanted]
    if lost:
        print(f"❌ 机械结果丢掉了已落盘取值 {lost}（只增不减，拒绝写入）")
        return 1

    added = [value for value in wanted if value not in stored]
    print(f"· {ENDPOINT}::TYPE: 手册规格表 {len(wanted)} 个取值 · 已落盘 {len(stored)} 个")
    if not added and stored == wanted:
        print("  一致")
    else:
        print(f"  将追加：{added}")

    if args.check:
        if stored != wanted:
            print(f"❌ 已落盘 {len(stored)} != 机械结果 {len(wanted)}")
            return 1
        print("\n✅ 自洽：已落盘 == 手册规格表（9 个取值）")
        return 0

    if not args.write:
        print(f"\n预演结束（{'待改' if stored != wanted else '无变化'}；加 --write 落盘）")
        return 0

    if stored != wanted:
        node["enum"] = wanted
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"\n✅ 已写入（{len(stored)} → {len(wanted)}）")
    else:
        print("\n无变化")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
