#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
窄枚举收口：把「**手册自己的示例用了、但枚举里没有**」的取值补进去（P178 · `docs/07` **R171**）。

为什么需要它（**R170 修复的直接后果**）
--------------------------------------
**R170**（P178）修好了 `spec_guard` 的 `patternProperties` 盲区后，闸门**第一次真正检查**
那 **21** 个文件的枚举 ⇒ 立刻暴露出 **8** 条**本来就存在**的窄枚举
（`check_spec_enums.py` 的「误伤普查」从 **3 → 11** 条）：

| 端点 | 字段 | 拦住的手册示例取值 | 枚举里有的 |
| --- | --- | --- | --- |
| `DB.SWIND` | `WIND_CODE` | `USER TYPE` | 只有 `KDS(41-12: 2022)` |
| `DB.SSEIS` | `SEIS_CODE` | `USER TYPE` | 只有 `KDS(41-17-00: 2019)` |
| `DB.REBR` | `HOOP_TYPE` | `Spirals`（string） | `[1, 2]`（integer） |
| `DESIGN.RC.*.DCRE` / `REBC` / `REBR` / `REBW` / `DCRM-WALL` | 钢筋规格 | `D19` / `D22` | `[D4…D8]` |
| `DESIGN.STEEL.KDS-41-30-2022.TABLE` | `PARTS` | `All` | `PartI` / `Part1/4`… |

⚠️ **这不是「新增闸门」，是「闸门终于看见既有窄枚举」** —— 若不管，**合法调用会被拦死**
（**R151** 的镜像事故：枚举太窄 ⇒ 拦住合法调用）。

来源（**只增不减**，逐条可复算）
--------------------------------
| 来源 | 判据（**机械扫描**，无人工取值） |
| --- | --- |
| ① **已落盘** | 当前 Schema 的 `enum` / `oneOf[].const` 全部保留 |
| ② **手册示例体** | **本端点自己**的手册文章 `examples[].json` 里、**同名字段**的叶子取值 |

⚠️ **只取「同一端点自己的文章」** —— 跨端点借取值会把**同名不同义**的字段并进来
（P171 / R164 已踩过：`LOAD.TYPE` 与 `ECCEN.TYPE` 同名不同义）。
⚠️ **只补字符串 / 数值标量**；对象 / 数组不下钻（那是**另一层**约束，不该由本工具决定）。
⚠️ **类型冲突不自动合并**：`DB.REBR.HOOP_TYPE` 的枚举是 **integer**，示例给的是 **string**
（`"Spirals"`）⇒ 混进 enum 会让 `enum` 变成混合类型，**且**与 `/info` 的
`{"type": "integer", "description": "Hoop Type (1=Tied, 2=Spiral)"}` 冲突
⇒ 本工具**拒绝**这种补全，改用**台账留缺**（`left_open`，见 `check_spec_enums.DISPOSITIONS`）。

幂等 / 用法
-----------
    python registry/tools/sync_narrow_enum_from_examples.py            # 预演
    python registry/tools/sync_narrow_enum_from_examples.py --write     # 写回
    python registry/tools/sync_narrow_enum_from_examples.py --check     # 断言「已落盘 == 机械结果」

⚠️ **枚举只增不减**：机械结果**丢掉**已落盘取值 ⇒ **拒绝写入**。
只依赖标准库（数据侧工具不引入新依赖）。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Final

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
MANUALS: Final[tuple[str, ...]] = (
    "MIDAS_API_Online_Manual_Gen_NX_v1.0.json",
    "MIDAS_API_Online_Manual_数据_v1.0.json",
)


class Target:
    """一个窄枚举。

    Attributes:
        key: 端点 key（与 `registry/manifest.json` 一致）。
        relative: Schema 文件相对 `registry/` 的路径。
        pointer: `enum` / `oneOf` 节点在 **schema 体**内的路径（`/` 分隔）。
        field: 字段名（在示例体里**递归**找同名叶子）。
    """

    def __init__(self, key: str, relative: str, pointer: str, field: str) -> None:
        self.key = key
        self.relative = relative
        self.pointer = pointer
        self.field = field

    @property
    def path(self) -> pathlib.Path:
        """Schema 文件的绝对路径。"""
        return REPO / "registry" / self.relative


# ⚠️ 只登记**已实测被误伤**的项（普查给出，不手工扩大范围）。
TARGETS: Final[tuple[Target, ...]] = (
    Target(
        "DB.SWIND",
        "schema/products/gen_nx/db/SWIND.json",
        "properties/Assign/patternProperties/^[0-9]+$/properties/WIND_CODE",
        "WIND_CODE",
    ),
    Target(
        "DB.SSEIS",
        "schema/products/gen_nx/db/SSEIS.json",
        "properties/Assign/patternProperties/^[0-9]+$/properties/SEIS_CODE",
        "SEIS_CODE",
    ),
)
"""两个**类型兼容且可复算**的窄枚举（string 补 string）。

⚠️ `DB.REBR.HOOP_TYPE` **不**纳入：枚举是 **integer** 而手册示例给 **string**（`"Spirals"`）
⇒ 混型会与 `/info` 的 `type: integer` + `description: "Hoop Type (1=Tied, 2=Spiral)"` 冲突。
它的处置 = **台账留缺**（见 `check_spec_enums.DISPOSITIONS`）。

⚠️ `DESIGN.STEEL.…TABLE.PARTS` 的 `"All"` **不**纳入：它只出现在 `default` 里，
**P170 从未实测过它**（实测的是 `PartI` / `PartJ` / `Part1/4`… 与伪值 `PartZ`）。
⚠️ **`default` 不是「合法取值」的证据** —— 把未实测的 `default` 塞进 `enum` 是**放松**闸门。

⚠️ 钢筋规格（`D4…D57`）**暂不补**：Schema 的 `description` 说「전체 19종: D4 ~ D57」，
但**手册没有**这 19 个取值的**完整表**（`D57` 在手册里出现 **0** 次）⇒ **不可复算**，
只能如实留缺（要求用户/MIDAS 给出权威清单）。见同一台账。
"""


def _manual_examples(key: str) -> list[Any]:
    """**本端点**手册文章里的全部示例体（`input_uri` ≈ key，大小写/斜杠归一）。"""
    wanted = key.replace(".", "/").lower()
    bodies: list[Any] = []
    for filename in MANUALS:
        path = REPO / filename
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        for entry in document.get("endpoints") or []:
            uri = str(entry.get("input_uri") or "").strip("/").replace(".", "/").lower()
            if uri != wanted:
                continue
            for example in entry.get("examples") or []:
                raw = example.get("json")
                if not isinstance(raw, str):
                    continue
                try:
                    bodies.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
    return bodies


def _leaf_values(node: Any, field: str) -> list[Any]:
    """递归收集**同名字段**的标量取值（对象 / 数组不下钻该字段本身）。"""
    found: list[Any] = []
    if isinstance(node, dict):
        for name, value in node.items():
            if name == field and isinstance(value, (str, int, float, bool)):
                found.append(value)
            else:
                found.extend(_leaf_values(value, field))
    elif isinstance(node, list):
        for item in node:
            found.extend(_leaf_values(item, field))
    return found


def _node(document: dict[str, Any], pointer: str) -> dict[str, Any]:
    """按 `/` 路径取 Schema 节点。"""
    node: Any = document["schema"]
    for step in pointer.split("/"):
        node = node[step]
    return node


def _enum_of(node: dict[str, Any]) -> list[Any]:
    """节点的枚举（`enum` 或 `oneOf[].const`）。"""
    if isinstance(node.get("enum"), list):
        return list(node["enum"])
    branches = node.get("oneOf")
    if isinstance(branches, list):
        return [branch["const"] for branch in branches if isinstance(branch, dict) and "const" in branch]
    return []


def _types(values: list[Any]) -> set[type]:
    """取值集合的类型（bool 单独算，避免与 int 混淆）。"""
    return {bool if isinstance(item, bool) else type(item) for item in values}


def _merged(target: Target) -> tuple[list[Any], list[Any]]:
    """**只增不减**的并集；返回 `(机械结果, 被拒的示例取值)`。

    ⚠️ **类型不兼容**的示例取值**不**并入（宁可留缺，也不混型）—— 它们会被**拒**并报出。
    """
    document = json.loads(target.path.read_text(encoding="utf-8"))
    stored = _enum_of(_node(document, target.pointer))
    wanted = list(stored)
    seen = set(wanted)
    rejected: list[Any] = []
    allowed_types = _types(stored) if stored else set()
    for body in _manual_examples(target.key):
        for value in _leaf_values(body, target.field):
            if value in seen:
                continue
            value_type = bool if isinstance(value, bool) else type(value)
            if allowed_types and value_type not in allowed_types:
                rejected.append(value)  # 类型冲突 ⇒ 拒
                continue
            seen.add(value)
            wanted.append(value)
    return wanted, rejected


def main() -> int:
    """入口（默认预演 / `--write` / `--check`）。"""
    parser = argparse.ArgumentParser(description="按手册示例补全窄枚举（只增不减）")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="写回 Schema")
    group.add_argument("--check", action="store_true", help="断言已落盘 == 机械结果")
    args = parser.parse_args()

    problems: list[str] = []
    changed = 0

    for target in TARGETS:
        document = json.loads(target.path.read_text(encoding="utf-8"))
        node = _node(document, target.pointer)
        stored = _enum_of(node)
        wanted, rejected = _merged(target)

        if rejected:
            print(f"· {target.key}: ⚠️ **拒**并类型不兼容的示例取值 {sorted(set(map(str, rejected)))}")

        lost = [value for value in stored if value not in wanted]
        if lost:
            problems.append(f"{target.key}: 机械结果丢掉了已落盘取值 {lost}")

        print(f"· {target.key}: " + ("一致" if stored == wanted else f"**待补** {len(stored)} → {len(wanted)}"))
        if stored == wanted:
            continue

        changed += 1
        if args.check:
            problems.append(f"{target.key}: 已落盘 {len(stored)} != 机械结果 {len(wanted)}")
            continue
        if not args.write:
            added = [value for value in wanted if value not in stored]
            print(f"    将追加：{added}")
            continue

        if "enum" in node:
            node["enum"] = wanted
        else:
            problems.append(f"{target.key}: `oneOf` 形状不在本工具所有权内")
            continue
        target.path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"    ✅ 已写入（{len(stored)} → {len(wanted)}）")

    if problems:
        print("\n❌ 失败：")
        for item in problems:
            print(f"  · {item}")
        return 1

    if args.check:
        print("\n✅ 自洽：三个窄枚举 == 机械结果（只增不减；来源 = 本端点自己的手册示例）")
    elif args.write:
        print(f"\n✅ 写入完成（{changed} 个文件）")
    else:
        print(f"\n预演结束（{changed} 个文件待改；加 --write 落盘）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
