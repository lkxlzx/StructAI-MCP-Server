#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`VIEW.RESULTGRAPHIC` 的 **`LOAD_CASE_COMB` 缺字段补全**（P169 · `docs/07` §16.1 **R162**）。

问题（**R155** 记录的**缺字段**，**不**是缺枚举）
------------------------------------------------
`VIEW.RESULTGRAPHIC` 的请求 Schema 的 `Argument` **只**声明了 `TYPE_OF_DISPLAY`
（P168 补了 `CURRENT_MODE`），**没有** `LOAD_CASE_COMB` —— 而上游手册里
**66 / 66** 条示例（`input_uri` 末段 = `resultgraphic`）**都**带它。

⚠️ 这不是「枚举太窄」也不是「缺枚举」—— **枚举普查（R161）的口径只管枚举**
⇒ 本项**单独**一次数据侧作业（P169 · **R162**）。

本工具的裁决（**数据侧**）
--------------------------
给 `Argument` **补上** `LOAD_CASE_COMB` 节点，形状 = **上游手册示例体的并集**
（**逐字段**可复算；**不**臆造）：

* 必填 `TYPE`（**自由文本**，**不**加枚举 —— 实测取值有 `ST` / `MV` / `SM` / `String`（示例占位）
  与**小写** `st`，且不同分析类型的取值表**未见**权威来源 ⇒ 加枚举是**收紧**闸门）；
* 必填 `NAME`；
* 可选 `STEP_INDEX` / `MINMAX` / `KEY_NODE_ELEM` / `TH_OPTION` / `OPT_MAXMIN_DIAGRAM` /
  `SCALE_FACTOR`（示例体里出现过、且**不是** `required`）。

⚠️ **不设 `additionalProperties: false`**（示例体里出现过但本工具**未**声明的字段会被拒 —— 那是**收紧**）。
⚠️ **不加 `enum`**（同上：**只增不减**原则要求新增约束必须是**显式裁决**；
本批的裁决是「补字段」，**不**包含「给自由文本加取值表」）。
⚠️ `app/**` 一行未改（字段是**数据**）；`spec_guard`（**R140**）**不**校验无枚举的字段
⇒ 补字段**不**会拦任何调用（**零回归**）。

幂等 / 用法
-----------
只拥有目标文件 `…Argument.properties.LOAD_CASE_COMB` 这一个键（其余内容**逐字节**透传）。

    python registry/tools/sync_result_graphic_lcc.py            # 预演（只打印差异）
    python registry/tools/sync_result_graphic_lcc.py --write     # 写回
    python registry/tools/sync_result_graphic_lcc.py --check     # 断言「已落盘 == 机械结果」
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
"""两份上游手册（与 `check_spec_enums.py` 的**同一**口径）。"""

TARGET_RELATIVE: Final[str] = "schema/common/view/RESULTGRAPHIC.json"
ENDPOINT_SUFFIX: Final[str] = "resultgraphic"
FIELD: Final[str] = "LOAD_CASE_COMB"

KNOWN_INNER_FIELDS: Final[tuple[str, ...]] = (
    "TYPE",
    "NAME",
    "STEP_INDEX",
    "MINMAX",
    "KEY_NODE_ELEM",
    "TH_OPTION",
    "OPT_MAXMIN_DIAGRAM",
    "SCALE_FACTOR",
)
"""示例体里出现过的**全部**内键（**机械**取自并集）。

⚠️ **没有**一个内键是**普遍必填**：内键**随变体而变**（实测 —— 模态类只有 `NAME`、
水化热类只有 `STEP_INDEX`、其余是 `TYPE` + `NAME`）⇒ `required` 由**交集**机械判定
（本批的交集 = **空** ⇒ **不**写 `required`，**不**臆造必填性）。
若上游手册新增内键 ⇒ `--check` 会红（**不**允许静默漂移）。
"""

DESCRIPTION: Final[str] = (
    "荷载工况 / 组合选择（LOAD_CASE_COMB）。⚠️ **R155 记录的缺字段**：请求 Schema 原先"
    "**没有**声明它，而上游手册里 `input_uri` 末段 = `resultgraphic` 的**全部 66 条示例都带它**"
    "（**56** 条在 Gen NX 手册 + **10** 条在数据手册）。字段形状 = 示例体的**并集**"
    "（内键 `TYPE` / `NAME` / `STEP_INDEX` / `MINMAX` / `KEY_NODE_ELEM` / `TH_OPTION` / "
    "`OPT_MAXMIN_DIAGRAM` / `SCALE_FACTOR`）。"
    "⚠️ **不写 `required`**：内键**随变体而变**（实测 —— 模态类只有 `NAME`、水化热类只有 "
    "`STEP_INDEX`）⇒ 交集为**空**，**不**臆造必填性。"
    "⚠️ `TYPE` / `NAME` **故意不加 `enum`**：实测取值含 `ST` / `MV` / `SM` / 小写 `st` / "
    "示例占位 `String`，且不同分析类型的取值表**未见**权威来源 ⇒ 加枚举是**收紧**闸门（须另一次显式裁决）。"
    "由 `registry/tools/sync_result_graphic_lcc.py` 机械派生（`--check` 断言已落盘 == 机械结果）；"
    "依据 = `docs/07` §16.1 R162。"
)


def load_examples(repo: pathlib.Path) -> list[dict[str, Any]]:
    """上游手册里 `input_uri` 末段 = `resultgraphic` 的**全部**示例体（**逐条**可回溯）。"""
    found: list[dict[str, Any]] = []
    for filename in MANUAL_FILENAMES:
        path = repo / filename
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        for entry in document.get("endpoints") or []:
            uri = str(entry.get("input_uri") or "")
            if uri.split("/")[-1].lower() != ENDPOINT_SUFFIX:
                continue
            for example in entry.get("examples") or []:
                try:
                    body = json.loads(str(example.get("json") or "{}"))
                except ValueError:
                    continue
                argument = body.get("Argument") if isinstance(body, dict) else None
                if not isinstance(argument, dict):
                    continue
                node = argument.get(FIELD)
                if isinstance(node, dict):
                    found.append(
                        {
                            "file": filename,
                            "title": str(entry.get("title") or ""),
                            "example": str(example.get("name") or ""),
                            "keys": sorted(str(key) for key in node),
                        }
                    )
    return found


def observed_inner_keys(repo: pathlib.Path) -> list[str]:
    """示例体里 `LOAD_CASE_COMB` 的内键**并集**（排序、去重）。"""
    keys: set[str] = set()
    for item in load_examples(repo):
        keys.update(item["keys"])
    return sorted(keys)


def observed_required(repo: pathlib.Path) -> list[str]:
    """示例体里**每条都有**的内键（⇒ 必填；**机械**判定，**不**猜）。"""
    items = load_examples(repo)
    if not items:
        return []
    common = set(items[0]["keys"])
    for item in items[1:]:
        common &= set(item["keys"])
    return sorted(common)


def build_node(repo: pathlib.Path) -> dict[str, Any]:
    """机械结果：`LOAD_CASE_COMB` 的 Schema 节点（形状 = 示例体并集；**不**臆造约束）。"""
    required = observed_required(repo)
    keys = observed_inner_keys(repo)
    node: dict[str, Any] = {
        "type": "object",
        "description": DESCRIPTION,
        "properties": {key: {"type": "string"} for key in keys},
    }
    # ⚠️ `required` 只在**交集非空**时写（本批的交集 = 空：内键随变体而变）——
    # **不**臆造必填性（写上空的 `required` 只是噪音）。
    if required:
        node["required"] = list(required)
    # ⚠️ `STEP_INDEX` 在示例体里是**数字**（实测）⇒ 如实标 `integer`（**不**一律写 string）
    if "STEP_INDEX" in keys:
        node["properties"]["STEP_INDEX"] = {"type": "integer"}
    return node


def _argument_properties(document: dict[str, Any]) -> dict[str, Any]:
    """取目标文件的 `schema.RESULTGRAPHIC.properties.Argument.properties`（**不**猜路径）。"""
    node: Any = document.get("schema")
    for segment in ("RESULTGRAPHIC", "properties", "Argument", "properties"):
        if not isinstance(node, dict) or segment not in node:
            raise SystemExit(
                f"❌ {TARGET_RELATIVE} 里找不到 `schema.{segment}`（数据文件结构变了？）"
            )
        node = node[segment]
    if not isinstance(node, dict):
        raise SystemExit(f"❌ {TARGET_RELATIVE} 的 `Argument.properties` 不是对象")
    return node


def on_disk_node(repo: pathlib.Path) -> dict[str, Any] | None:
    """已落盘的节点（**只读**；缺失 ⇒ `None`）。"""
    path = repo / "registry" / TARGET_RELATIVE
    if not path.is_file():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    node = _argument_properties(document).get(FIELD)
    return node if isinstance(node, dict) else None


def build_document(repo: pathlib.Path) -> dict[str, Any]:
    """装配目标文件（其余键**逐字节**透传；只改 `LOAD_CASE_COMB` 一个键）。"""
    path = repo / "registry" / TARGET_RELATIVE
    document = json.loads(path.read_text(encoding="utf-8"))
    _argument_properties(document)[FIELD] = build_node(repo)
    return document


def is_applied(repo: pathlib.Path) -> bool:
    """补字段是否已落盘（**回归**判据：形状与机械结果一致）。"""
    return on_disk_node(repo) == build_node(repo)


def render(document: dict[str, Any]) -> str:
    """落盘文本（与既有 `registry/schema/**` 的写法一致：`indent=2` + 结尾换行）。"""
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VIEW.RESULTGRAPHIC 的 LOAD_CASE_COMB 补字段（R162）")
    parser.add_argument("--repo", default=".", help="仓库根目录（默认当前目录）")
    parser.add_argument("--write", action="store_true", help="实际写回（默认只预演）")
    parser.add_argument("--check", action="store_true", help="断言已落盘 == 机械结果（CI）")
    args = parser.parse_args(argv)

    repo = pathlib.Path(args.repo).resolve()
    items = load_examples(repo)
    node = build_node(repo)
    if not items:
        print("❌ 上游手册里没有 `resultgraphic` 的示例体 ⇒ 无法复算")
        return 1
    print(f"上游示例体（`{ENDPOINT_SUFFIX}`）= **{len(items)}** 条 · 内键并集 = {observed_inner_keys(repo)}")
    print(f"必填（**每条都有**）= {observed_required(repo)}")
    extra = sorted(set(observed_inner_keys(repo)) - set(KNOWN_INNER_FIELDS))
    if extra:
        print(f"❌ 示例体里出现**未声明**的内键 {extra} ⇒ 需一次显式裁决（**不**静默补）")
        return 1

    path = repo / "registry" / TARGET_RELATIVE
    current = path.read_text(encoding="utf-8")
    text = render(build_document(repo))
    if current == text:
        print(f"✅ {TARGET_RELATIVE} 与机械结果一致（无差异）")
        return 0
    print(f"  需写入 {TARGET_RELATIVE}（补 `Argument.properties.{FIELD}`）")
    if args.check:
        print("❌ --check：已落盘内容与机械结果不一致（或字段缺失）")
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
