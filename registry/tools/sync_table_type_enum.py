#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`POST.TABLE` 的 `TABLE_TYPE` 枚举收口（P167 · `docs/07` §16.1 **R160**；**R151** 的恢复条件①）。

问题（R151，P160e-a 实测）
-------------------------
`RESULT.ANALYSIS.SUMMARY`（`docs/07` §6.7 的**通用取表入口**，走 `POST /POST/TABLE`）
在生产路径上**一个请求都发不出去**：核心自己的 `spec_guard`（**R140**，为防弹窗 / 防崩溃而加）
在**发请求之前**就回 `STRUCTAI-1200 value_not_in_spec_enum`。

成因**不是**原生：真机实测 `POST /POST/TABLE {"Argument": {"TABLE_TYPE": "DISPLACEMENTG"}}`
⇒ **`200`** 且 `HEAD` **9** 列 / `DATA` **63** 行（自建混凝土简支梁的位移结果）。
拦住它的是**枚举**——`registry/schema/common/post/TABLE.json` 的 `TABLE_TYPE.enum`
**只有 2 个取值**（`WEIGHT_IRREGULARITY_X` / `_Y`），因为它是从 help center
**一篇文章**（`Story Mass Summary`）的 `json_schema` 落下来的 ⇒ 来源**太窄**。

本工具的裁决（**数据侧**，`docs/07` §16.1 **R160**）
--------------------------------------------------
`TABLE_TYPE.enum` 的来源换成**两个可复算来源的并集**（**不**按手册**示例体**硬凑 ——
R151 的教训）：

| 来源 | 判据（**机械扫描**，无人工取值） | 规模 |
| --- | --- | --- |
| ① **登记表** | `registry/manifest.json` 里 key 以 `POST.TABLE.` 开头且 `table_type` 非空的端点 ⇒ 取其 `table_type` | 194 |
| ② **手册声明** | `MIDAS_API_Online_Manual_数据_v1.0.json` 里**所有**条目 `json_schema` 的 `TABLE_TYPE.enum`（含嵌套；与 `sync_request_schemas.table_type_tokens()` 同一扫描口径） | 121 |

⚠️ **为什么取并集，而不是只取①**：`WEIGHT_IRREGULARITY_Y` 是**手册声明**但**没有**登记成
独立端点的取值（`POST.TABLE.WEIGHT_IRREGULARITY_Y` 不存在）。只取①会把它**删掉**
⇒ 那是把闸门**收紧**，与 R151 的教训（枚举**可能不全**）**反向**。
并集则**严格包含**旧枚举（2 个取值一个不丢）⇒ **既不放松也不收紧**非法取值的拦截。

⚠️ **R140 的保护照旧**：伪 token（两个来源都不在）**仍然**被 `spec_guard` 拦在**发请求之前**
（零请求）。本工具**只**扩枚举的**来源**，**不动** `spec_guard` 一行代码
（`app/**` 一行未改）。

幂等 / 用法
-----------
只拥有 `registry/schema/common/post/TABLE.json` 的
`schema.properties.Argument.properties.TABLE_TYPE` 的 **`enum`** 与 **`description`** 两个键
（其余内容**逐字节**透传；同一文件的 `response` 块由 `sync_response_schemas.py` 拥有）。

    python registry/tools/sync_table_type_enum.py            # 预演（只打印差异）
    python registry/tools/sync_table_type_enum.py --write     # 写回
    python registry/tools/sync_table_type_enum.py --check     # 断言「已落盘 == 机械结果」

⚠️ **枚举只增不减**：`--write` 时若机械结果**丢掉**了已落盘的任何取值，工具**拒绝写入**
（那是「收紧闸门」，必须是一次**显式裁决**）—— 确需收紧才加 `--allow-shrink`。
只依赖标准库（数据侧工具不引入新依赖）。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

MANIFEST_FILENAME = "manifest.json"
MANUAL_FILENAME = "MIDAS_API_Online_Manual_数据_v1.0.json"
TARGET_RELATIVE = "schema/common/post/TABLE.json"
ENDPOINT_KEY = "POST.TABLE"
TABLE_PREFIX = "POST.TABLE."

TABLE_TYPE_PATH: tuple[str, ...] = ("properties", "Argument", "properties", "TABLE_TYPE")
"""`TABLE_TYPE` 节点在 Schema **体内**的路径（`registry/schema/**` 的文件是
`{key, uri, source, schema}` 四个键，`MidasRegistry.schema_json()` 取的是 `schema`）。"""

TABLE_TYPE_DESCRIPTION = (
    "结果表类型（TABLE_TYPE）。取值 = **两个可复算来源的并集**："
    "① `registry/manifest.json` 里已登记的 `POST.TABLE.*` 端点的 `table_type`；"
    f"② 上游手册 `{MANUAL_FILENAME}` 的 `json_schema` 里声明的 `TABLE_TYPE.enum`。"
    "由 `registry/tools/sync_table_type_enum.py` 机械派生"
    "（`--check` 断言已落盘 == 机械结果）；依据 = `docs/07` §16.1 R160。"
)


# ===== 两个来源（都**机械扫描**，无人工取值）=====


def _manifest(repo: pathlib.Path) -> dict[str, Any]:
    return json.loads((repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8"))


def registered_table_types(repo: pathlib.Path) -> list[str]:
    """来源①：`registry/manifest.json` 里已登记的 `POST.TABLE.*` 的 `table_type`（去重 + 排序）。

    Raises:
        SystemExit: 登记表为空，或某个 token 不是「非空、无空白的字符串」。
    """
    endpoints = _manifest(repo)["endpoints"]
    tokens: list[str] = []
    for entry in endpoints:
        key = str(entry.get("key") or "")
        if not key.startswith(TABLE_PREFIX):
            continue
        token = str(entry.get("table_type") or "")
        if not token:
            # `POST.TABLE.string`：源手册解析残留，`table_type` 无法确定 ⇒ **不**进枚举
            # （**不**臆造一个取值；它的 `key` 后缀不是 token）。
            continue
        if token != token.strip() or any(char.isspace() for char in token):
            raise SystemExit(f"❌ 登记表里的 table_type 含空白：{key} → {token!r}")
        tokens.append(token)
    if not tokens:
        raise SystemExit(f"❌ 登记表里没有 {TABLE_PREFIX}* 的 table_type")
    return sorted(set(tokens))


def manual_table_types(repo: pathlib.Path) -> list[str]:
    """来源②：上游手册**全部**条目 `json_schema` 里的 `TABLE_TYPE.enum`（去重 + 排序）。

    扫描口径与 `sync_request_schemas.table_type_tokens()` **逐字相同**（递归 `walk`，
    只认 `{"TABLE_TYPE": {"enum": [...]}}`），故两个工具的「手册声明」永远一致。
    """
    path = repo / MANUAL_FILENAME
    if not path.is_file():
        raise SystemExit(f"❌ 上游手册不存在：{MANUAL_FILENAME}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "TABLE_TYPE" and isinstance(value, dict):
                    for member in value.get("enum") or []:
                        if isinstance(member, str) and member.strip():
                            found.add(member)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for entry in payload.get("endpoints") or []:
        try:
            schema = json.loads(str(entry.get("json_schema") or ""))
        except (TypeError, ValueError):
            continue
        walk(schema)
    if not found:
        raise SystemExit(f"❌ 上游手册 {MANUAL_FILENAME} 里没有声明任何 TABLE_TYPE.enum")
    return sorted(found)


def expected_enum(repo: pathlib.Path) -> list[str]:
    """机械结果：两个来源的**并集**（排序、去重、确定性）。"""
    return sorted(set(registered_table_types(repo)) | set(manual_table_types(repo)))


# ===== 目标文件（**只**拥有 TABLE_TYPE 的 enum / description）=====


def table_type_node(document: dict[str, Any]) -> dict[str, Any]:
    """取目标文件里 `TABLE_TYPE` 的 Schema 节点（取不到 ⇒ **明确失败**，**不**猜路径）。"""
    node: Any = document.get("schema")
    for segment in TABLE_TYPE_PATH:
        if not isinstance(node, dict) or segment not in node:
            raise SystemExit(
                f"❌ {TARGET_RELATIVE} 里找不到 "
                f"`schema.{'.'.join(TABLE_TYPE_PATH)}`（数据文件结构变了？）"
            )
        node = node[segment]
    if not isinstance(node, dict):
        raise SystemExit(f"❌ {TARGET_RELATIVE} 的 TABLE_TYPE 节点不是对象")
    return node


def build_document(repo: pathlib.Path) -> dict[str, Any]:
    """装配目标文件（其余键**逐字节**透传；只改 `TABLE_TYPE` 的 `enum` / `description`）。"""
    path = repo / "registry" / TARGET_RELATIVE
    document = json.loads(path.read_text(encoding="utf-8"))
    node = table_type_node(document)
    node["enum"] = expected_enum(repo)
    node["description"] = TABLE_TYPE_DESCRIPTION
    return document


def render(document: dict[str, Any]) -> str:
    """落盘文本（与既有 `registry/schema/**` 的写法一致：`indent=2` + 结尾换行）。"""
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def on_disk_enum(repo: pathlib.Path) -> list[str]:
    """已落盘的枚举（**只读**；缺失 ⇒ 空列表）。"""
    path = repo / "registry" / TARGET_RELATIVE
    if not path.is_file():
        return []
    node = table_type_node(json.loads(path.read_text(encoding="utf-8")))
    enum = node.get("enum")
    return [str(item) for item in enum] if isinstance(enum, list) else []


# ===== 入口 =====


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="POST.TABLE 的 TABLE_TYPE 枚举收口（R160）")
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

    registered = registered_table_types(repo)
    manual = manual_table_types(repo)
    enum = expected_enum(repo)
    disk = on_disk_enum(repo)
    text = render(build_document(repo))
    current = path.read_text(encoding="utf-8") if path.is_file() else None

    print(f"来源① 登记表（{MANIFEST_FILENAME} 的 {TABLE_PREFIX}*）= {len(registered)} 个取值")
    print(f"来源② 手册声明（{MANUAL_FILENAME} 的 TABLE_TYPE.enum）= {len(manual)} 个取值")
    print(
        f"并集 = {len(enum)} 个取值（登记表独有 {len(set(registered) - set(manual))} · "
        f"手册独有 {len(set(manual) - set(registered))}）"
    )
    print(f"已落盘 = {len(disk)} 个取值")

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
        print("WROTE registry/schema/common/post/TABLE.json")
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
