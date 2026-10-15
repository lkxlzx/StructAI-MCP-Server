#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`VIEW.RESULTGRAPHIC` 的 `CURRENT_MODE` **枚举补全**（P168 · `docs/07` §16.1 **R161**；**R155** 的留缺）。

问题（**R155** 留缺，P164-d 离线定案）
-------------------------------------
`VIEW.RESULTGRAPHIC` 是**多变体端点**：手册里 **34** 篇文章（`… - Result Display` /
`… - Moving Tracer Display` / `… - Mode Shapes Display` / `… - Heat of Hydration Display`）
都映射到 `view/RESULTGRAPHIC`，**由 `Argument.CURRENT_MODE` 选变体**（**36** 个取值）。
而请求 Schema 的 `Argument` **只**声明了 `TYPE_OF_DISPLAY` ⇒ **没有** `CURRENT_MODE` 的枚举可查
⇒ `spec_guard`（**R140**）**抓不到**非法取值 —— 非法值一路发到原生（回
`400` `MIDAS GEN NX second query is wrong`，P160d 实测）。

本工具的裁决（**数据侧**，`docs/07` §16.1 **R161**）
--------------------------------------------------
给 `Argument` **补上** `CURRENT_MODE` 的 `enum`，来源 = **两个可复算来源的并集**：

| 来源 | 判据（**机械扫描**，无人工取值） | 规模 |
| --- | --- | --- |
| ① **手册变体文章** | 两份上游手册里 `input_uri` 末段 = `resultgraphic` 的**全部**文章（**34** 篇）的示例体 `Argument.CURRENT_MODE`（**56** 条示例逐条回溯到文章标题 / 示例名 / URL） | **36** |
| ② **已落盘** | 当前 Schema 里已经写下的取值（**只增不减**的护栏） | 0（本批首次补全） |

⚠️ **为什么这不违反「不按手册示例体硬凑」（R151 的教训）**：R151 的错在于枚举是从
**一篇文章**的 `json_schema` 落下来的 —— **来源太窄**；而这里是**该端点自己的全部变体文章**
（一篇文章 = 一个变体，**34** 篇 = 变体清单本身），且与 `registry/live/view_result_modes.json`
（R155 的既有证据，**逐条**可回溯）**机械一致**（本工具会**断言**两者相同）。

⚠️ **只增不减**：`--write` 时若机械结果**丢掉**了已落盘的任何取值 ⇒ **拒绝写入**
（那是把闸门**收紧**，必须是一次显式裁决）—— 确需收紧才加 `--allow-shrink`。

⚠️ **R140 的保护照旧**：伪取值（两个来源都不在）**仍然**被 `spec_guard` 拦在**发请求之前**
（零请求）。本工具**只**补**数据侧**的枚举，**不动** `spec_guard` 一行代码（`app/**` 一行未改）。

幂等 / 用法
-----------
只拥有 `registry/schema/common/view/RESULTGRAPHIC.json` 的
`schema.RESULTGRAPHIC.properties.Argument.properties.CURRENT_MODE` 的 **`enum`** 与
**`description`** 两个键（其余内容**逐字节**透传；同一文件的 `response` 块由
`sync_response_schemas.py` 拥有）。

    python registry/tools/sync_result_graphic_modes.py            # 预演（只打印差异）
    python registry/tools/sync_result_graphic_modes.py --write     # 写回
    python registry/tools/sync_result_graphic_modes.py --check     # 断言「已落盘 == 机械结果」

只依赖标准库（数据侧工具不引入新依赖）。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys
from typing import Any, Final

MANUAL_FILENAMES: Final[tuple[str, ...]] = (
    "MIDAS_API_Online_Manual_Gen_NX_v1.0.json",
    "MIDAS_API_Online_Manual_数据_v1.0.json",
)
"""两份上游手册（`input_uri` 末段 = `resultgraphic` 的文章都在这里）。"""

EXTRACT_TOOL: Final[str] = "extract_result_modes.py"
"""`R155` 的取证工具（**同一套扫描口径**；本工具**复用**它，**不**另写一套）。"""

EVIDENCE_RELATIVE: Final[str] = "live/view_result_modes.json"
"""`R155` 的证据文件 —— 本工具**断言**机械结果与它的取值表**逐条相同**。"""

TARGET_RELATIVE: Final[str] = "schema/common/view/RESULTGRAPHIC.json"
ENDPOINT_KEY: Final[str] = "VIEW.RESULTGRAPHIC"
ENDPOINT_SUFFIX: Final[str] = "resultgraphic"

CURRENT_MODE_PATH: tuple[str, ...] = (
    "RESULTGRAPHIC",
    "properties",
    "Argument",
    "properties",
    "CURRENT_MODE",
)
"""`CURRENT_MODE` 节点在 Schema **体内**的路径。

⚠️ 本文件的 `schema` 根键**就是包装键** `RESULTGRAPHIC`（`{RESULTGRAPHIC: {…}}`）——
`registry/schema/**` 里 **393 / 625** 个文件是这个形态（**R161** 的普查，`registry/README.md` §8.22）。
⚠️ 路径里**必须**带上这个根键：`MidasRegistry.effective_schema()`（**R161** 起 `spec_guard` 用的就是它）
会**剥掉**包装根键，而 `schema_json()`（原样）不会。
"""

CURRENT_MODE_DESCRIPTION: Final[str] = (
    "结果图形类型（CURRENT_MODE，**变体选择子**）。取值 = **两个可复算来源的并集**："
    "① 上游手册里 `input_uri` 末段 = `resultgraphic` 的**全部变体文章**（34 篇 / 56 条示例）"
    "的 `Argument.CURRENT_MODE`；② 已落盘枚举（**只增不减**）。"
    f"由 `registry/tools/sync_result_graphic_modes.py` 机械派生"
    f"（`--check` 断言已落盘 == 机械结果；并与 `registry/{EVIDENCE_RELATIVE}` 机械一致）；"
    "依据 = `docs/07` §16.1 R161。"
)


# ===== 来源①：手册变体文章（**复用** R155 的取证工具）=====


def _extract_tool() -> Any:
    """按路径装载 `extract_result_modes.py`（`registry/tools` 不是包）—— **不**复制扫描逻辑。"""
    path = pathlib.Path(__file__).with_name(EXTRACT_TOOL)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manual_modes(repo: pathlib.Path) -> list[str]:
    """来源①：手册**全部变体文章**的示例体 `Argument.CURRENT_MODE`（去重 + 排序）。

    ⚠️ 两份手册**都**扫（R155 的工具默认只扫 Gen NX）—— 取**并集**，与 R160 的口径一致。

    Raises:
        SystemExit: 一份手册都读不到，或一个取值都没有。
    """
    tool = _extract_tool()
    found: set[str] = set()
    scanned = 0
    for filename in MANUAL_FILENAMES:
        path = repo / filename
        if not path.is_file():
            continue
        scanned += 1
        entries = tool.load_entries(path)
        collected = tool.collect_modes(entries)
        for key, slot in collected["modes"].items():
            # ⚠️ `collect_modes()` 把「示例体**没有** `CURRENT_MODE`」也归成一个槽
            # （`current_mode = None`）—— 那不是取值，**不**进枚举。
            if slot["count"] <= 0 or slot["current_mode"] is None:
                continue
            found.add(str(slot["current_mode"]))
    if scanned == 0:
        raise SystemExit("❌ 两份上游手册都不存在 ⇒ 无法复算 `CURRENT_MODE` 的取值表")
    if not found:
        raise SystemExit(f"❌ 手册里没有任何 `{ENDPOINT_SUFFIX}` 变体文章的 `CURRENT_MODE`")
    return sorted(found)


def evidence_modes(repo: pathlib.Path) -> list[str]:
    """`R155` 的证据文件里的取值表（**只读**；缺失 ⇒ 空列表）。"""
    path = repo / "registry" / EVIDENCE_RELATIVE
    if not path.is_file():
        return []
    document = json.loads(path.read_text(encoding="utf-8"))
    modes = document.get("modes") or {}
    return sorted(str(key) for key in modes)


def on_disk_enum(repo: pathlib.Path) -> list[str]:
    """已落盘的枚举（**只读**；节点 / 枚举缺失 ⇒ 空列表）。"""
    path = repo / "registry" / TARGET_RELATIVE
    if not path.is_file():
        return []
    document = json.loads(path.read_text(encoding="utf-8"))
    node: Any = document.get("schema")
    for segment in CURRENT_MODE_PATH:
        if not isinstance(node, dict) or segment not in node:
            return []
        node = node[segment]
    if not isinstance(node, dict):
        return []
    enum = node.get("enum")
    return [str(item) for item in enum] if isinstance(enum, list) else []


def expected_enum(repo: pathlib.Path) -> list[str]:
    """机械结果：来源① ∪ 来源②（**已落盘**，护栏）—— 排序、去重、确定性。"""
    return sorted(set(manual_modes(repo)) | set(on_disk_enum(repo)))


def is_applied(repo: pathlib.Path) -> bool:
    """收口是否已落盘（`check_spec_enums.py` 的**回归**判据：已收口项不可回退）。"""
    return on_disk_enum(repo) == expected_enum(repo)


# ===== 目标文件（**只**拥有 `CURRENT_MODE` 的 `enum` / `description`）=====


def current_mode_node(document: dict[str, Any]) -> dict[str, Any]:
    """取目标文件里的 `CURRENT_MODE` 节点（**缺失 ⇒ 补一个空节点**，**不**猜别的路径）。"""
    node: Any = document.get("schema")
    for segment in CURRENT_MODE_PATH[:-1]:
        if not isinstance(node, dict) or segment not in node:
            raise SystemExit(
                f"❌ {TARGET_RELATIVE} 里找不到 "
                f"`schema.{'.'.join(CURRENT_MODE_PATH[:-1])}`（数据文件结构变了？）"
            )
        node = node[segment]
    # ⚠️ 循环已经把 `Argument.properties` 走完了 ⇒ `node` **就是** `Argument` 的属性表。
    if not isinstance(node, dict):
        raise SystemExit(f"❌ {TARGET_RELATIVE} 的 `Argument.properties` 不是对象")
    field = CURRENT_MODE_PATH[-1]
    if field not in node:
        # **补一个**字段节点（**只**有 type / description / enum 三个键，**不**臆造别的约束）
        node[field] = {"type": "string"}
    target = node[field]
    if not isinstance(target, dict):
        raise SystemExit(f"❌ {TARGET_RELATIVE} 的 `{field}` 节点不是对象")
    return target


def build_document(repo: pathlib.Path) -> dict[str, Any]:
    """装配目标文件（其余键**逐字节**透传；只改 `CURRENT_MODE` 的 `enum` / `description`）。"""
    path = repo / "registry" / TARGET_RELATIVE
    document = json.loads(path.read_text(encoding="utf-8"))
    node = current_mode_node(document)
    node["enum"] = expected_enum(repo)
    node["description"] = CURRENT_MODE_DESCRIPTION
    return document


def render(document: dict[str, Any]) -> str:
    """落盘文本（与既有 `registry/schema/**` 的写法一致：`indent=2` + 结尾换行）。"""
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


# ===== 入口 =====


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VIEW.RESULTGRAPHIC 的 CURRENT_MODE 枚举补全（R161）")
    parser.add_argument("--repo", default=".", help="仓库根目录（默认当前目录）")
    parser.add_argument("--write", action="store_true", help="实际写回（默认只预演）")
    parser.add_argument("--check", action="store_true", help="断言已落盘 == 机械结果（CI）")
    parser.add_argument(
        "--allow-shrink",
        action="store_true",
        help="允许枚举**变窄**（丢掉已落盘取值）—— 必须是一次**显式裁决**",
    )
    args = parser.parse_args(argv)

    repo = pathlib.Path(args.repo).resolve()
    path = repo / "registry" / TARGET_RELATIVE

    manual = manual_modes(repo)
    evidence = evidence_modes(repo)
    disk = on_disk_enum(repo)
    enum = expected_enum(repo)
    text = render(build_document(repo))
    current = path.read_text(encoding="utf-8") if path.is_file() else None

    print(f"来源① 手册变体文章（{', '.join(MANUAL_FILENAMES)} 的 `{ENDPOINT_SUFFIX}` 文章）= {len(manual)} 个取值")
    print(f"来源② 已落盘 = {len(disk)} 个取值")
    print(f"并集 = {len(enum)} 个取值（手册独有 {len(set(manual) - set(disk))}）")
    if evidence:
        same = set(evidence) == set(manual)
        print(
            f"与 `{EVIDENCE_RELATIVE}`（R155 的证据，{len(evidence)} 个取值）机械一致：{same}"
        )
        if not same:
            print(
                "❌ 手册复算结果与 R155 的证据**不一致** ⇒ 先重跑 "
                "`python registry/tools/extract_result_modes.py`（证据是取证物，必须可复算）"
            )
            return 1

    lost = sorted(set(disk) - set(enum))
    if lost:
        print(f"⚠️ 机械结果**丢掉**了已落盘的 {len(lost)} 个取值（枚举变窄）：{lost[:10]}")
        if args.write and not args.allow_shrink:
            print(
                "❌ 拒绝写入：枚举只增不减（收紧闸门必须是一次显式裁决；确需收紧加 --allow-shrink）"
            )
            return 1

    if current == text:
        print(f"✅ {TARGET_RELATIVE} 与机械结果一致（无差异）")
        return 0

    print(f"  需写入 {TARGET_RELATIVE}")
    if args.check:
        print("❌ --check：已落盘内容与机械结果不一致（或文件缺失）")
        return 1
    if args.write:
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"WROTE registry/{TARGET_RELATIVE}")
    else:
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
