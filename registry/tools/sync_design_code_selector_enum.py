#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
设计规范选择器（`DRC` / `DSTL` / `DSRC`）的 `DGNCODE` 枚举**补全**（P177 · `docs/07` §16.1 **R169** 续）。

问题（**R151 的镜像**）
-----------------------
`spec_guard`（**R140**）按 Schema 的 `enum` 拦「非法取值」。枚举**太窄**时它反过来
**拦住合法调用**（**R151** 的原形态：`POST.TABLE` 的 `TABLE_TYPE` 只有 **2** 个取值，
而登记表里有 **194** 个）。本工具修的是**同一形态**、**另一处**：

| 端点 | 落盘枚举 | 手册码表 |
| --- | ---: | ---: |
| `DESIGN.RC.DRC`（`DGNCODE`） | **1**（`KDS 41 20 : 2022`） | **64**（`DB.DCON` 规格表） |
| `DESIGN.STEEL.DSTL`（`DGNCODE`） | **1**（`KDS 41 30 : 2022`） | **66**（`DB.DSTL` 规格表） |
| `DESIGN.SRC.AIK-SRC2K.DSRC`（`DGNCODE`） | **1**（`AIK-SRC2K`） | 手册**无**码表 ⇒ **保持原样** |

⇒ `GB/T50010-10` 这类**实测合法**（P176：`BD-ANAL` `200` ∧ `BD-TABLE` **3 行**）的规范码
在 `DESIGN.RC.DRC` 上会被闸门拦住 —— 这是**误拦**。

⚠️ **本批的诚实边界（必读）**
------------------------------
**R170**（P177 实测）发现：`spec_guard` 的 `check_spec_values()` **只**走 `properties` 与 `items`，
**不**处理 `patternProperties` ⇒ **上面三个选择器的 `DGNCODE` 枚举补了也【不会】生效**
（它们**全部**在 `patternProperties` 下，**21** 个文件 / **90** 个枚举节点 **100% 盲区**）。
⇒ 本批补全的**真实收益**是：

1. **数据侧一致**（`registry/design_codes.yaml` ↔ Schema ↔ 手册码表三处同源）；
2. **闸门修好后立刻生效**（**R170** 修复时**不**需再补一次枚举）；
3. ⚠️ **不**是「现在闸门就会拦住非法规范码」—— **不是**，现在它**不拦**。

来源（**只增不减**，逐条可复算）
--------------------------------
| 来源 | 判据（**机械扫描**，无人工取值） |
| --- | --- |
| ① **已落盘** | 当前 Schema 的 `enum` / `oneOf[].const` 全部保留（**只增不减**） |
| ② **手册码表** | `MIDAS_API_Online_Manual_完整API手册_v1.0.md` 里 `DB.DCON` / `DB.DSTL` 的 **`| No. | Design Code | DGNCODE |`** 规格表，取第 **3** 列（**带引号的取值列**） |

⚠️ **为什么不取第 2 列**：第 2 列是**显示名**，与取值**不一定**相同 ——
`AASHTO-LRFD20(US)`（显示）→ `AASHTO-LRFD20`（取值）。取错列会**发明**不存在的取值。
⚠️ **为什么不从 `registry/design_codes.yaml` 读**：那是 `extract_design_codes.py` 的**产物**；
直接读它会把「生成器的产物」当成「来源」（**循环引用**）。本工具**直接**扫手册原文，
并与 `design_codes.yaml` **交叉断言**（`--check`：两者必须逐条一致）。

⚠️ **`KDS 41 20 : 2022` 不在 `DB.DCON` 的码表里**（P177 复核：码表 **64** 项，无此项）——
它是 **P176 实测**合法且**已在落盘枚举**里 ⇒ 由来源 ① 保留。这正是「**只增不减**」的作用：
并集**严格包含**旧枚举 ⇒ 既不放松也不收紧。

幂等 / 用法
-----------
    python registry/tools/sync_design_code_selector_enum.py            # 预演（只打印差异）
    python registry/tools/sync_design_code_selector_enum.py --write     # 写回
    python registry/tools/sync_design_code_selector_enum.py --check     # 断言「已落盘 == 机械结果」

⚠️ **只拥有** `DGNCODE` 节点的 **`enum`** 键（`oneOf` 形状的 `DSRC` **不**动 —— 见上表）。
其余内容**逐字节**透传（`json.dumps(indent=2, ensure_ascii=False)` 与原文件**逐字节同形**，
`--check` 会断言这一点）。
⚠️ **枚举只增不减**：若机械结果**丢掉**了已落盘的任何取值，工具**拒绝写入**。
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
"""仓库根目录（`registry/tools/` 的上两级）。"""

MANUAL: Final[pathlib.Path] = REPO / "MIDAS_API_Online_Manual_完整API手册_v1.0.md"
DESIGN_CODES_YAML: Final[pathlib.Path] = REPO / "registry" / "design_codes.yaml"

ENTRY_PATH: Final[tuple[str, ...]] = ("properties", "Assign", "patternProperties", "^[0-9]+$")
"""条目节点在 Schema **体内**的路径（三个选择器**同形**；`--check` 逐条断言）。"""


class Target:
    """一个待补全的选择器。

    Attributes:
        endpoint: 端点 key（诊断用）。
        relative: Schema 文件相对 `registry/` 的路径。
        table_start: 手册规格表的**表头行**（1-based，`| No. | Design Code | DGNCODE |`）。
        table_end: 手册规格表的**最后一行**（1-based，含）。
        yaml_section: `design_codes.yaml` 的段名（交叉断言用；`None` = 无码表）。
    """

    def __init__(
        self,
        endpoint: str,
        relative: str,
        table_start: int,
        table_end: int,
        yaml_section: str | None,
    ) -> None:
        self.endpoint = endpoint
        self.relative = relative
        self.table_start = table_start
        self.table_end = table_end
        self.yaml_section = yaml_section

    @property
    def path(self) -> pathlib.Path:
        """Schema 文件的绝对路径。"""
        return REPO / "registry" / self.relative


TARGETS: Final[tuple[Target, ...]] = (
    Target("DESIGN.RC.DRC", "schema/design/rc/DRC.json", 6703, 6766, "nx_rc"),
    Target("DESIGN.STEEL.DSTL", "schema/design/steel/DSTL.json", 56359, 56424, "nx_steel"),
    # ⚠️ SRC 的手册条目**没有**码表（`DESIGN/SRC/AIK-SRC2K/DSRC` 只有示例体）
    #    ⇒ **不**纳入（纳入会**发明**取值）。它的 `oneOf` 形状也**不**是本工具的所有权。
    Target("DESIGN.SRC.AIK-SRC2K.DSRC", "schema/design/src/AIK-SRC2K/DSRC.json", 0, 0, None),
)
"""三个选择器；`table_start == 0` ⇒ 手册无码表 ⇒ **只**保留落盘枚举（**不**改）。"""


def manual_codes(start_1based: int, end_1based: int) -> list[str]:
    """从手册规格表取**取值列**（第 3 列，去引号）。

    ⚠️ 表头行（`| No. | Design Code | DGNCODE |`）与续行（`| 1 | KDS … | "KDS …" |`）
    **都**匹配，故用「第 3 列以引号开头」过滤 —— 表头第 3 列是 `DGNCODE`（**无**引号）。
    """
    lines = MANUAL.read_text(encoding="utf-8").splitlines()
    codes: list[str] = []
    for index in range(start_1based - 1, min(end_1based, len(lines))):
        line = lines[index]
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 3 or not re.fullmatch(r"\d+", cells[0]):
            continue
        value = cells[2]
        if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
            codes.append(value[1:-1])
    return codes


def yaml_codes(section: str) -> list[str]:
    """`design_codes.yaml` 某段的 `code:` 取值（**交叉断言**用；不参与生成）。"""
    text = DESIGN_CODES_YAML.read_text(encoding="utf-8")
    # 段从 `\n<name>:` 开始，到下一个顶层 `\n<word>:` 或文件尾
    match = re.search(rf"^{re.escape(section)}:(.*?)(?=^\S)", text, re.MULTILINE | re.DOTALL)
    if not match:
        raise SystemExit(f"❌ design_codes.yaml 缺段：{section}")
    return re.findall(r'\{ no: \d+, display: "[^"]*", code: "([^"]*)" \}', match.group(1))


def stored_codes(document: dict[str, Any], target: Target) -> list[str]:
    """当前落盘枚举（`enum` 或 `oneOf[].const`；**两种形状都**支持）。"""
    node: Any = document["schema"]
    for step in ENTRY_PATH:
        node = node[step]
    field = node["properties"]["DGNCODE"]
    if isinstance(field.get("enum"), list):
        return [str(item) for item in field["enum"]]
    branches = field.get("oneOf")
    if isinstance(branches, list):
        return [str(branch["const"]) for branch in branches if "const" in branch]
    raise SystemExit(f"❌ {target.endpoint} 的 DGNCODE **没有**枚举形状（enum / oneOf）")


def merged(target: Target, stored: list[str]) -> list[str]:
    """**只增不减**的并集：已落盘（原序）+ 手册码表（原序，去重）。"""
    if target.table_start == 0:
        return list(stored)
    out = list(stored)
    seen = set(out)
    for code in manual_codes(target.table_start, target.table_end):
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def _write_node(document: dict[str, Any], target: Target, codes: list[str]) -> None:
    """把并集写回 `DGNCODE` 节点（`enum` 形状 ⇒ `enum`；`oneOf` 形状 ⇒ **不动**）。"""
    node: Any = document["schema"]
    for step in ENTRY_PATH:
        node = node[step]
    field = node["properties"]["DGNCODE"]
    if "enum" in field:
        field["enum"] = codes
    elif "oneOf" in field:  # pragma: no cover —— 本批的 3 个目标都是 enum 形状
        raise SystemExit(f"❌ {target.endpoint} 是 oneOf 形状 ⇒ 本工具不拥有它")


def _dump(document: dict[str, Any]) -> str:
    """与原文件**逐字节同形**的序列化（`indent=2` + `ensure_ascii=False` + 尾换行）。"""
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def _load(target: Target) -> dict[str, Any]:
    """读 Schema 文件。"""
    return json.loads(target.path.read_text(encoding="utf-8"))


def main() -> int:
    """入口（默认预演 / `--write` / `--check`）。"""
    parser = argparse.ArgumentParser(description="设计规范选择器的 DGNCODE 枚举补全")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="写回 Schema")
    group.add_argument("--check", action="store_true", help="断言已落盘 == 机械结果")
    args = parser.parse_args()

    problems: list[str] = []
    changed = 0

    for target in TARGETS:
        document = _load(target)
        stored = stored_codes(document, target)
        wanted = merged(target, stored)

        # ⚠️ 只增不减：机械结果必须**包含**已落盘的每一个取值
        missing = [code for code in stored if code not in wanted]
        if missing:
            problems.append(f"{target.endpoint}: 机械结果**丢掉**了已落盘取值 {missing}")

        # 交叉断言：手册码表 == design_codes.yaml（**同一批**来源必须一致）
        if target.yaml_section is not None:
            manual = manual_codes(target.table_start, target.table_end)
            reference = yaml_codes(target.yaml_section)
            if manual != reference:
                problems.append(
                    f"{target.endpoint}: 手册码表({len(manual)}) != "
                    f"design_codes.yaml:{target.yaml_section}({len(reference)})"
                )

        status = "一致" if stored == wanted else f"**待补** {len(stored)} → {len(wanted)}"
        print(f"· {target.endpoint}: {status}")

        if stored == wanted:
            continue

        changed += 1
        if args.check:
            problems.append(
                f"{target.endpoint}: 已落盘 {len(stored)} 个取值 != 机械结果 {len(wanted)} 个"
            )
            continue
        if not args.write:
            added = [code for code in wanted if code not in stored]
            print(f"    将追加 {len(added)} 个：{added[:5]}{' …' if len(added) > 5 else ''}")
            continue

        _write_node(document, target, wanted)
        target.path.write_text(_dump(document), encoding="utf-8", newline="\n")
        print(f"    ✅ 已写入（{len(stored)} → {len(wanted)}）")

    if problems:
        print("\n❌ 失败：")
        for item in problems:
            print(f"  · {item}")
        return 1

    if args.check:
        print("\n✅ 自洽：三个选择器的枚举 == 机械结果（只增不减；手册码表 == design_codes.yaml）")
    elif args.write:
        print(f"\n✅ 写入完成（{changed} 个文件）")
    else:
        print(f"\n预演结束（{changed} 个文件待改；加 --write 落盘）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
