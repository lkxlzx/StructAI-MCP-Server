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
import re
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
        fields: 多个候选字段名（与 `field` 二选一；用于钢筋规格这类**同一取值出现在
            不同字段名下**的场景，如 `MAIN_REBAR` / `NAME` / `VERTICAL_REBAR`）。
        pattern: 取值必须匹配的正则（可选；用于把 `NAME` 这类**通用字段名**限定为
            钢筋规格 `D\\d+`，避免把非直径字符串并进枚举）。
    """

    def __init__(
        self,
        key: str,
        relative: str,
        pointer: str,
        field: str,
        *,
        fields: tuple[str, ...] = (),
        pattern: str = "",
    ) -> None:
        self.key = key
        self.relative = relative
        self.pointer = pointer
        self.field = field
        self.fields = fields or (field,)
        self.pattern = pattern

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
    # ---- P179 / R172：钢筋规格（5 个端点 / 共 21 个枚举节点） ----
    # ⚠️ **不是**「凑出 19 个」—— 只补**本端点自己的手册示例体**里真实出现过的直径。
    #    示例体里同一取值可能挂在 `MAIN_REBAR`（数组元素）或 `NAME` / `VERTICAL_REBAR`
    #    等**不同字段名**下 ⇒ 用 `fields` 多候选 + `pattern` 把通用名限定为 `D\\d+`。
    Target(
        "DESIGN.RC.KDS-41-20-2022.DCRE",
        "schema/design/rc/KDS-41-20-2022/DCRE.json",
        "properties/Assign/patternProperties/^[0-9]+$/properties/BEAM/properties/MAIN_REBAR/items",
        "MAIN_REBAR",
        fields=("MAIN_REBAR", "STIRRUPS", "SIDE_BAR", "TIES_SPIRALS", "VERTICAL_REBAR",
                "HORIZONTAL_REBAR", "END_REBAR", "BE_HORZ_REBAR", "REBAR_DIAMETER"),
        pattern=r"D\d+",
    ),
    Target(
        "DESIGN.RC.KDS-41-20-2022.DCRM-WALL",
        "schema/design/rc/KDS-41-20-2022/DCRM-WALL.json",
        "properties/Assign/patternProperties/^[0-9]+$/properties/ITEMS/items/properties/VERTICAL_REBAR",
        "VERTICAL_REBAR",
        fields=("VERTICAL_REBAR", "HORIZONTAL_REBAR", "END_REBAR", "BE_HORZ_REBAR"),
        pattern=r"D\d+",
    ),
    Target(
        "DESIGN.RC.KDS-41-20-2022.REBC",
        "schema/design/rc/KDS-41-20-2022/REBC.json",
        "properties/Assign/patternProperties/^[0-9]+$/properties/ITEMS/items/properties/MAIN_BAR/properties/NAME",
        "NAME",
        fields=("NAME", "NAME_CORNER"),
        pattern=r"D\d+",
    ),
    Target(
        "DESIGN.RC.KDS-41-20-2022.REBR",
        "schema/design/rc/KDS-41-20-2022/REBR.json",
        "properties/Assign/patternProperties/^[0-9]+$/properties/ITEMS/items/properties/MAIN_BAR/properties/NAME",
        "NAME",
        fields=("NAME",),
        pattern=r"D\d+",
    ),
    Target(
        "DESIGN.RC.KDS-41-20-2022.REBW",
        "schema/design/rc/KDS-41-20-2022/REBW.json",
        "properties/Assign/patternProperties/^[0-9]+$/properties/ITEMS/items/properties/VERTICAL_REBAR/properties/NAME",
        "NAME",
        fields=("NAME",),
        pattern=r"D\d+",
    ),
)
"""两个**类型兼容且可复算**的窄枚举（string 补 string）。

⚠️ `DB.REBR.HOOP_TYPE` **不**纳入：枚举是 **integer** 而手册示例给 **string**（`"Spirals"`）
⇒ 混型会与 `/info` 的 `type: integer` + `description: "Hoop Type (1=Tied, 2=Spiral)"` 冲突。
它的处置 = **台账留缺**（见 `check_spec_enums.DISPOSITIONS`）。

⚠️ `DESIGN.STEEL.…TABLE.PARTS` 的 `"All"` **不**纳入：它只出现在 `default` 里，
**P170 从未实测过它**（实测的是 `PartI` / `PartJ` / `Part1/4`… 与伪值 `PartZ`）。
⚠️ **`default` 不是「合法取值」的证据** —— 把未实测的 `default` 塞进 `enum` 是**放松**闸门。

⚠️ **钢筋规格（P179 / R172 已收口，不再是留缺）**：`description` 说「전체 19종: D4 ~ D57」，
但**手册没有**这 19 个取值的**完整表**（`D57` 在手册里出现 **0** 次）。**P179** 的收口口径
不是「凑出 19 个」，而是**只补手册自己的示例体里真实出现过的取值**（可复算、可追溯）：
`D10` / `D13` / `D16` / `D19` / `D22` / `D25` / `D32` / `D41`（另有已落盘的 `D4`~`D8`，含示例里的 `D7`）。
⚠️ 仍**不发明** `D9` / `D11` / … / `D57` 等**从未在任何来源出现过**的取值 ——
闸门对它们的拦截是**有意的**取舍（宁可我方拦，也不把不确定取值放行到原生）。
"""


def _manual_examples(key: str, repo: pathlib.Path = REPO) -> list[Any]:
    """**本端点**手册文章里的全部示例体（`input_uri` ≈ key，大小写/斜杠归一）。"""
    wanted = key.replace(".", "/").lower()
    bodies: list[Any] = []
    for filename in MANUALS:
        path = repo / filename
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


def _leaf_values(node: Any, fields: tuple[str, ...], pattern: str = "") -> list[Any]:
    """递归收集**同名字段**的标量取值（对象 / 数组不下钻该字段本身）。

    Args:
        node: 示例体节点。
        fields: 候选字段名集合（命中任一即取）。
        pattern: 可选正则；非空时只保留**匹配**的取值（用于 `NAME` 这类通用字段名）。
    """
    found: list[Any] = []
    matcher = re.compile(pattern) if pattern else None

    def accept(value: Any) -> None:
        if matcher is None or (isinstance(value, str) and matcher.fullmatch(value)):
            found.append(value)

    if isinstance(node, dict):
        for name, value in node.items():
            if name in fields:
                if isinstance(value, (str, int, float, bool)):
                    accept(value)
                elif isinstance(value, list):
                    # 数组字段（如 `MAIN_REBAR: ["D22"]`）⇒ 收集其**标量元素**
                    for item in value:
                        if isinstance(item, (str, int, float, bool)):
                            accept(item)
            else:
                found.extend(_leaf_values(value, fields, pattern))
    elif isinstance(node, list):
        for item in node:
            found.extend(_leaf_values(item, fields, pattern))
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


def _merged_values(stored: list[Any], examples: list[Any]) -> tuple[list[Any], list[Any]]:
    """**只增不减**的并集；返回 `(机械结果, 被拒的示例取值)`。

    ⚠️ **类型不兼容**的示例取值**不**并入（宁可留缺，也不混型）—— 它们会被**拒**并报出。
    """
    wanted = list(stored)
    seen = set(wanted)
    rejected: list[Any] = []
    allowed_types = _types(stored) if stored else set()
    for value in examples:
        if value in seen:
            continue
        value_type = bool if isinstance(value, bool) else type(value)
        if allowed_types and value_type not in allowed_types:
            rejected.append(value)  # 类型冲突 ⇒ 拒
            continue
        seen.add(value)
        wanted.append(value)
    return wanted, rejected


def _same_file_nodes(document: dict[str, Any], target: Target) -> list[dict[str, Any]]:
    """**同一文件**里与 `target` 同族的全部枚举节点。

    为什么需要它：钢筋规格在 `DCRE` / `DCRM-WALL` / `REBC` / `REBR` / `REBW` 里
    各有多处（`MAIN_REBAR` / `STIRRUPS` / `SIDE_BAR` / …），`pointer` 只指向**其中一个**。
    只补一个会让同一文件里其余同类节点**仍拦合法取值** ⇒ 全量收集。

    判据（**结构**，不猜字段名）：
      * 配了 `pattern`（如 `D\\d+`）⇒ 枚举**全部取值都匹配**该正则；
      * 未配 ⇒ 节点名 == `pointer` 末段（原口径）。
    """
    leaf = target.pointer.rsplit("/", 1)[-1]
    matcher = re.compile(target.pattern) if target.pattern else None
    found: list[dict[str, Any]] = []

    def matches(node: dict[str, Any], name: str) -> bool:
        values = node.get("enum")
        if not isinstance(values, list) or not values:
            return False
        if matcher is None:
            return name == leaf
        return all(isinstance(item, str) and matcher.fullmatch(item) for item in values)

    def walk(node: Any, name: str) -> None:
        if isinstance(node, dict):
            if matches(node, name):
                found.append(node)
            for key, value in node.items():
                walk(value, key)
        elif isinstance(node, list):
            for item in node:
                walk(item, name)

    walk(document.get("schema"), "")
    return found


def _merged(target: Target) -> tuple[list[Any], list[Any]]:
    """**只增不减**的并集（按 `pointer` 指向的**单个**节点）。

    ⚠️ 同文件的其余同类节点由 `main` 用 `_same_file_nodes` 一并处理。
    """
    return _merged_at(REPO, target)


def _merged_at(repo: pathlib.Path, target: Target) -> tuple[list[Any], list[Any]]:
    """按指定仓库根复算（供 `is_applied` 使用）。"""
    document = json.loads((repo / "registry" / target.relative).read_text(encoding="utf-8"))
    stored = _enum_of(_node(document, target.pointer))
    examples = [
        value
        for body in _manual_examples(target.key, repo)
        for value in _leaf_values(body, target.fields, target.pattern)
    ]
    return _merged_values(stored, examples)


def is_applied(repo: pathlib.Path) -> bool:
    """`--check` 的复算入口：**全部** target 的同类节点 == 机械结果。"""
    for target in TARGETS:
        path = repo / "registry" / target.relative
        if not path.is_file():
            return False
        document = json.loads(path.read_text(encoding="utf-8"))
        nodes = _same_file_nodes(document, target)
        if not nodes:
            return False
        wanted, _ = _merged_at(repo, target)
        if any(_enum_of(node) != wanted for node in nodes):
            return False
    return True


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
        nodes = _same_file_nodes(document, target)
        if not nodes:
            problems.append(f"{target.key}: 找不到 `{target.pointer}` 对应的枚举节点")
            continue

        wanted, rejected = _merged(target)
        if rejected:
            print(f"· {target.key}: ⚠️ **拒**并类型不兼容的示例取值 {sorted(set(map(str, rejected)))}")

        pending: list[tuple[dict[str, Any], list[Any]]] = []
        for node in nodes:
            stored = _enum_of(node)
            lost = [value for value in stored if value not in wanted]
            if lost:
                problems.append(f"{target.key}: 机械结果丢掉了已落盘取值 {lost}")
            if stored != wanted:
                pending.append((node, stored))

        if not pending:
            print(f"· {target.key}: 一致（{len(nodes)} 个节点）")
            continue

        changed += 1
        if args.check:
            for _node_obj, stored in pending:
                problems.append(
                    f"{target.key}: 已落盘 {len(stored)} != 机械结果 {len(wanted)}"
                )
            continue
        if not args.write:
            for _node_obj, stored in pending:
                added = [value for value in wanted if value not in stored]
                print(f"    将追加：{added}")
            print(f"· {target.key}: **待补** {len(pending)}/{len(nodes)} 个节点")
            continue

        for node, stored in pending:
            node["enum"] = wanted
        target.path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"· {target.key}: ✅ 已写入 {len(pending)}/{len(nodes)} 个节点（{len(wanted)} 个取值）")

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
