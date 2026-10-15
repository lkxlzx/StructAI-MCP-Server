#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`PARTS`（输出部位）枚举的**收口**（P169 · `docs/07` §16.1 **R162**；**R151** 的教训）。

问题（P168 普查的留缺项）
------------------------
**6** 个端点的 `PARTS` 枚举与**手册同一篇文章**的**示例体**互相矛盾
（`json_schema` 的**声明**用 `Part1`（数字 **1**），示例体用 `PartI`（罗马数字 **I**））：

| 端点 | 声明 | 示例体 |
| --- | --- | --- |
| `POST.TABLE.BEAMFORCE` / `_VBM` | `Part1` / `Part1/4` / `Part2/4` / `Part3/4` / `PartJ` | `['PartI','PartJ']` |
| `POST.TABLE.THISBEAMFORCE` | `PartI` / `Part1/4` / `Part2/4` / `Part3/4` / `PartJ` | `['PartI','PartJ']` |
| `POST.TABLE.RESULTANT_FORCES` / `_VBM` | `PartI` / `PartJ` | `['PartI','PartJ']` |
| `DESIGN.STEEL.KDS-41-30-2022.TABLE` | `PartI` / `Part1/4` / … | `['All', …]` |

⚠️ **裁决依据 = 真机实测**（`registry/live/parts_disposition_probe.json`，**铁律 ⓪**）：
示例体的取值经 `POST /POST/TABLE` **原生 `200` 且返回真数据行** ⇒ 我们 Schema 的**声明**
是**上游笔误**（同一份手册的**规格表**也写 `"Part I"`，佐证 `Part1` = `Part I` 的转写错）
⇒ 按实测**收口**（**只增不减**）。
⚠️ **不**按示例体硬凑（**R151**）：收口的来源**逐条可回溯**到「哪篇文章 / 哪个示例 / 哪一行」，
且**同时**保留原声明（`Part1` 可能是**独立**的合法取值 —— 原生对大小写与同义写法宽容，
**未**做「原生拒绝 `Part1`」的断言 ⇒ **不**敢删）。

本工具的裁决（**数据侧**）
--------------------------
`PARTS.items.enum` = **三个来源的并集**（**只增不减**）：

* ① **手册示例体**：上游手册里 `input_uri` 命中本端点 URI 的**全部**示例体的 `Argument.PARTS`；
* ② **已落盘**：当前 Schema 里已经写下的取值（护栏 —— 机械结果**丢掉**任何已落盘取值即**拒绝写入**）；
* ③ **真机实测**：`registry/live/parts_disposition_probe.json` 里原生 `200` 的取值（本批的裁决证据）。

⚠️ **只**碰 `PARTS` 的 `enum` / `description` 两个键（其余内容**逐字节**透传）。
⚠️ **R140** 的保护照旧：伪取值（三个来源都没有）**仍**被拦在**发请求之前**（零请求）；
`app/**` **未**因本工具而改（枚举是**数据**）。

用法
----
    python registry/tools/sync_parts_enum.py            # 预演（只打印差异）
    python registry/tools/sync_parts_enum.py --write     # 写回
    python registry/tools/sync_parts_enum.py --check     # 断言「已落盘 == 机械结果」
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Final

MANUAL_FILENAMES: Final[tuple[str, ...]] = (
    "MIDAS_API_Online_Manual_Gen_NX_v1.0.json",
    "MIDAS_API_Online_Manual_数据_v1.0.json",
)
"""上游手册（与 `check_spec_enums.py` 的**同一**口径）。"""

PROBE_FILENAMES: Final[tuple[str, ...]] = (
    "parts_disposition_probe.json",
    "parts_disposition_probe_p170.json",
)
"""真机裁决证据（来源③；**不含**凭据 / 响应原文）。

⚠️ **P170**：`PARTS` 的「有效取值」**随模型**变（同一个端点在不同模型上会过滤出**不同**的
部位集合）⇒ **同一份探针**在**两个模型**上各留一份证据：
① `.tmp_p164c/p164c-concrete.mgbx`（**纯梁**）—— P169 的原始证据；
② `.tmp_p164c/p170-discriminator.mgbx`（**板网格 + 虚拟截面 + 钢结构设计**）—— P170 的可判别化证据。
**合并口径**：**任一**证据判为**可判别** ⇒ 该端点**可判别**（取**并集**的实测有效取值）。"""

PARTS_DESCRIPTION: Final[str] = (
    "输出部位（PARTS）。取值 = **三个可复算来源的并集**：① 上游手册**本端点**文章的示例体"
    "（`Argument.PARTS`，**仅**在端点**可判别**时参与）；② 已落盘枚举（**只增不减**）；"
    "③ 真机实测**有效**的取值（`registry/live/parts_disposition_probe.json` 的 `measured[].valid`"
    "= 有数据行且**少于**基线 ⇒ **真的过滤**；状态码 `200` **不算**）。"
    "由 `registry/tools/sync_parts_enum.py` 机械派生（`--check` 断言已落盘 == 机械结果）；"
    "依据 = `docs/07` §16.1 R162。"
)

URI_TOKENS: Final[dict[str, str]] = {
    "POST.TABLE.BEAMFORCE": "post/TABLE",
    "POST.TABLE.BEAMFORCEVBM": "post/TABLE",
    "POST.TABLE.THISBEAMFORCE": "post/TABLE",
    "POST.TABLE.RESULTANT_FORCES": "post/TABLE",
    "POST.TABLE.RESULTANT_FORCESVBM": "post/TABLE",
    "DESIGN.STEEL.KDS-41-30-2022.TABLE": "DESIGN/STEEL/KDS-41-30-2022/TABLE",
}
"""收口对象 → 手册里该端点的 `input_uri`（**不**猜；取不到 ⇒ 该端点没有示例体来源）。

⚠️ 前 **5** 个共享 `post/TABLE` 这个 URI —— 手册的示例体因此是**共享**的
（一篇 = 一个变体；示例体的 `TABLE_TYPE` 决定它属于哪个变体）。
⚠️ `POST.TABLE.THISBEAMFORCE` 的文章在 `post/TABLE` 里**没有**示例体
（`Beam Force - TH Result Table` 只有 `json_schema`）⇒ 它的来源① = 空。
"""


def _registered_token(repo: pathlib.Path, key: str) -> str:
    """端点在**登记表**里声明的 `table_type`（没有 ⇒ 空串）。"""
    for entry in manifest_entries(repo):
        if str(entry.get("key") or "") == key:
            return str(entry.get("table_type") or "")
    return ""


def manual_parts(repo: pathlib.Path, key: str) -> list[str]:
    """来源①：上游手册里**本端点自己那篇 / 那几篇**文章的示例体的 `Argument.PARTS`。

    ⚠️ **口径（R151 的教训）**：**5** 个 `POST.TABLE.*` 变体共享 `post/TABLE` 这个 URI
    ⇒ 只按 URI 取会把**别的变体**的取值（`PartC` / `Top` / `Bot` / `PartK` …）混进来
    （那正是「一篇文章的枚举」反向的错）。判据 = 示例体的 `Argument.TABLE_TYPE`
    **等于本端点的登记 token**（一篇 = 一个变体；`DESIGN.STEEL.…` 的 URI 唯一 ⇒ 不筛）。
    """
    uri = URI_TOKENS.get(key)
    if not uri:
        return []
    wanted = _registered_token(repo, key)
    found: set[str] = set()
    for filename in MANUAL_FILENAMES:
        path = repo / filename
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        for entry in document.get("endpoints") or []:
            if str(entry.get("input_uri") or "") != uri:
                continue
            for example in entry.get("examples") or []:
                try:
                    body = json.loads(str(example.get("json") or "{}"))
                except ValueError:
                    continue
                if not isinstance(body, dict):
                    continue
                argument = body.get("Argument")
                if not isinstance(argument, dict):
                    continue
                if wanted and str(argument.get("TABLE_TYPE") or "") != wanted:
                    continue
                parts = argument.get("PARTS")
                if not isinstance(parts, list):
                    continue
                found.update(str(value) for value in parts)
    return sorted(found)


def probe_values(repo: pathlib.Path, key: str) -> list[str]:
    """来源③：真机裁决证据里**实测有效**的取值（**没有**证据 ⇒ 空）。

    ⚠️ **门槛**：只有 `verdict.decidable`（基线**有**数据行）的端点才算 ——
    取值本身必须 `measured[value].valid`（**有**数据行 ∧ **少于**基线 = **真的过滤**）。
    状态码 `200` **不算**（实测：原生对**任何**取值都回 `200`，含伪取值）。

    ⚠️ **候选集合 = 手册示例体取值 ∪ 已落盘声明取值**（探针**逐条**实测）⇒
    声明里**被证伪**的取值（`Part1` ⇒ 空块）**不**入来源、但**仍**留在枚举里
    （**只增不减** —— 未断言它「非法」，只是**没有证据**支持它）。

    ⚠️ **P170 起合并多份证据**（见 `PROBE_FILENAMES`）：逐份读，**任一**判为**可判别**即
    该端点可判别，实测有效取值取**并集**（同一个端点在不同模型上过滤出的部位集合不同）。
    """
    valid: set[str] = set()
    for filename in PROBE_FILENAMES:
        path = repo / "registry" / "live" / filename
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        for row in document.get("targets") or []:
            if str(row.get("endpoint") or "") != key:
                continue
            if not (row.get("verdict") or {}).get("decidable"):
                continue
            measured = row.get("measured") or {}
            valid.update(str(value) for value, item in measured.items() if item.get("valid"))
    return sorted(valid)


def manifest_entries(repo: pathlib.Path) -> list[dict[str, Any]]:
    """登记表的端点条目。"""
    document = json.loads((repo / "registry" / "manifest.json").read_text(encoding="utf-8"))
    return list(document["endpoints"])


def _unwrap(document: dict[str, Any]) -> dict[str, Any] | None:
    """剥掉**包装根键**（两种根形态都认；**不**猜路径）。"""
    schema = document.get("schema")
    if not isinstance(schema, dict):
        return None
    if isinstance(schema.get("properties"), dict):
        return schema
    roots = [key for key in schema if key not in {"$schema", "title", "type"}]
    if len(roots) != 1 or not isinstance(schema[roots[0]], dict):
        return None
    return schema[roots[0]]


def parts_node(document: dict[str, Any]) -> dict[str, Any] | None:
    """取 `Argument.PARTS` 的 Schema 节点（取不到 ⇒ `None`）。"""
    node: Any = _unwrap(document)
    for segment in ("properties", "Argument", "properties", "PARTS"):
        if not isinstance(node, dict) or segment not in node:
            return None
        node = node[segment]
    return node if isinstance(node, dict) else None


def on_disk_enum(path: pathlib.Path) -> list[str]:
    """来源②：已落盘的枚举（**只读**；没有 ⇒ 空）。"""
    if not path.is_file():
        return []
    node = parts_node(json.loads(path.read_text(encoding="utf-8")))
    items = (node or {}).get("items")
    enum = (items or {}).get("enum") if isinstance(items, dict) else None
    return [str(item) for item in enum] if isinstance(enum, list) else []


def targets(repo: pathlib.Path) -> list[dict[str, Any]]:
    """收口对象 = 三个来源的并集 **⊋** 已落盘（逐条可复算）。

    ⚠️ **手册示例体（来源①）的取舍**：端点**不可判别**（模型无该表数据）时，示例体取值
    **未**经实测确认 ⇒ **不**进收口（**不**按示例体硬凑 —— **R151** 的教训）；
    此时只有**已落盘**（来源②=护栏）与**实测有效**（来源③）参与。
    ⚠️ **可判别**时来源①与来源③是**同一份实测证据**（候选集合 = 示例体 ∪ 声明）⇒ 无重叠。
    """
    found: list[dict[str, Any]] = []
    for entry in manifest_entries(repo):
        key = str(entry.get("key") or "")
        if key not in URI_TOKENS:
            continue
        file = str(entry.get("schema") or "")
        if not file:
            continue
        disk = on_disk_enum(repo / "registry" / file)
        if not disk:
            continue
        probed = probe_values(repo, key)
        manual = manual_parts(repo, key) if probed else []
        # ⚠️ **P170 修正（判据 v2 的一致性）**：端点**可判别**时，来源①（手册示例体）必须与
        # **实测有效**取交集 —— 否则会把**实测无效**的示例体取值（`DESIGN.STEEL.…` 的 `All`
        # ⇒ 空块，与伪取值**同形**）当成收口来源写进枚举（= **按示例体硬凑**，**R151** 的镜像事故）。
        if probed:
            valid = set(probed)
            manual = [value for value in manual if value in valid]
        expected = sorted(set(disk) | set(manual) | set(probed))
        found.append(
            {
                "key": key,
                "file": file,
                "on_disk": disk,
                "manual": manual,
                "probed": [item for item in probed if item not in disk],
                "expected": expected,
            }
        )
    return found


def is_applied(repo: pathlib.Path) -> bool:
    """收口是否已落盘（`check_spec_enums.py` 的**回归**判据：已收口项不可回退）。

    ⚠️ 判据 = **枚举**相等（**不**看 `description`）：枚举没变的端点**不**写文件
    （避免 diff 噪音），因此它们的 `description` 仍是旧的。
    """
    return all(set(item["expected"]) <= set(item["on_disk"]) for item in targets(repo))


def build_document(repo: pathlib.Path, item: dict[str, Any]) -> dict[str, Any]:
    """装配目标文件（其余键**逐字节**透传；只改 `PARTS` 的 `enum` / `description`）。"""
    path = repo / "registry" / item["file"]
    document = json.loads(path.read_text(encoding="utf-8"))
    node = parts_node(document)
    if node is None:
        raise SystemExit(f"❌ {item['file']} 里找不到 `PARTS` 节点")
    items = node.get("items")
    if not isinstance(items, dict):
        raise SystemExit(f"❌ {item['file']} 的 `PARTS` 不是数组形态")
    items["enum"] = list(item["expected"])
    items["description"] = PARTS_DESCRIPTION
    return document


def render(document: dict[str, Any]) -> str:
    """落盘文本（与既有 `registry/schema/**` 的写法一致：`indent=2` + 结尾换行）。"""
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PARTS 枚举收口（R162）")
    parser.add_argument("--repo", default=".", help="仓库根目录（默认当前目录）")
    parser.add_argument("--write", action="store_true", help="实际写回（默认只预演）")
    parser.add_argument("--check", action="store_true", help="断言已落盘 == 机械结果（CI）")
    args = parser.parse_args(argv)

    repo = pathlib.Path(args.repo).resolve()
    items = targets(repo)
    print(f"收口对象 = **{len(items)}** 个端点（`PARTS`）")
    changed: list[str] = []
    for item in items:
        grew = sorted(set(item["expected"]) - set(item["on_disk"]))
        print(
            f"  {item['key']}  {len(item['on_disk'])} → {len(item['expected'])} 个取值"
            f"  新增={grew}  （{item['file']}）"
        )
        if not grew:
            continue  # ⚠️ 枚举没变 ⇒ **不**写文件（避免 diff 噪音）
        path = repo / "registry" / item["file"]
        changed.append(item["file"])
        if args.write:
            path.write_text(render(build_document(repo, item)), encoding="utf-8", newline="\n")
            print(f"WROTE registry/{item['file']}")

    if not changed:
        print(f"✅ {len(items)} 个文件与机械结果一致（无差异）")
        return 0
    print(f"  需写入 {len(changed)} 个文件（**只增不减**：示例体 / 实测取值追加进枚举）")
    if args.check:
        print("❌ --check：已落盘内容与机械结果不一致")
        return 1
    if not args.write:
        print("（预演模式；加 --write 才会写回）")
    return 0


if __name__ == "__main__":
    # Windows 控制台默认 cp949/cp936：本工具会打印中文/符号，不重设编码会 UnicodeEncodeError。
    # ⚠️ 必须在 `__main__` 块内：测试用 `exec_module()` 装载本模块，模块级调用会改写
    #    **pytest 的捕获流**，破坏其后所有用例的 capture。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
