#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R5 剩余补齐：为「上游资料**已有**请求 Schema / 规格表」的端点生成请求 Schema 文件（P140 · P141）。

背景（`docs/07` §16 **R5** / §16.1）
----------------------------------
`registry/schema/**` 里有 **20** 个端点没有请求 Schema（P138b 按**实测**分成 5 类）。
其中 **9** 个的来源其实**可复算** —— 上游资料里已经有请求 Schema / 完整规格表 /
开发文档 JSON Schema，只是数据侧还没落盘。本工具把这 9 个**机械生成**出来
（**不**手抄、**不**臆造）。四类来源（括号里是落盘的 `source` 取值）：

| 类 | 判据（工具**逐条断言**） | 端点 |
| --- | --- | --- |
| `manual_json_schema`（`help_center`） | 手册 `endpoints[].json_schema` 里 `TABLE_TYPE.enum` **包含**该端点 token | `POST.TABLE.WEIGHT_IRREGULARITY_X` · `POST.TABLE.CONCURRENT_JOINT_FORCE` |
| `manual_spec_table`（`help_center_spec_table`） | 手册条目**没有** `json_schema`，但有**完整规格表**（`specifications`） | `POST.TABLE.STORY_SHEAR_FORCE_COEFFICIENT` |
| `dev_doc_json_schema`（`civil_nx_manual`） | `MIDAS_API_开发文档_v1.0.md` 的端点章节里**已给出**完整 JSON Schema | `OPE.BMLD` |
| `manual_spec_table` · **同 URI**（`help_center_spec_table`） | **P141**：手册条目与端点**同一 `input_uri`**（`uri:` 定位串，工具会断言两者一致）或按 `title:` 定位，且有完整规格表 | `OPE.MEMB` · `OPE.STOR` · `OPE.STORPROP` · `OPE.STORY_IRR_PARAM` · `OPE.STORY_PARAM` |

规格表 → JSON Schema 的**机械规则**（全部取自表格本身，无人工取值）
-----------------------------------------------------------------
1. **字段行** = 6 列且第 3 列是 `"<NAME>"` 形态的引号键；表头 / 小节标题行（`Root Object`、
   `General` …）**跳过**；
2. **嵌套**：行号带 `(n)` 或 `n.m` 的行是**上一个顶层字段**的子字段 → 写进该字段的
   `properties`；其 `Required` 记进**父对象**的 `required`；
3. **类型**：`String` → `string`、`Integer` → `integer`、`Number` → `number`、
   `Boolean` → `boolean`、`Object` → `object`、`Array [X]` → `array` + `items: {type: X}`；
   表里未给类型（`-`）→ **不写** `type`（不猜）；
4. **包装键**：规格表自己声明了 `"Argument"` 行 → 用它；否则按端点数据侧的
   `wrapper.write` 包一层（`POST/TABLE` 系 = `Argument`）；
5. **`TABLE_TYPE` 的取值**：规格表若记的是**兄弟 token**（手册把两张表合并在同一条目里），
   则替换为**本端点的 token** 并在 `description` 里**注明依据**（API 实测确认该 token 有效）。

幂等：默认**预演**（只打印差异），`--write` 写回；`--check` 断言「已落盘 == 机械结果」。
只依赖标准库（数据侧工具不引入新依赖）。

⚠️ **只拥有 `key` / `uri` / `source` / `schema` 四个键**：同一批文件里由
`sync_response_schemas.py` 追加的 `response` 块（L4 实测信封，`docs/07` §16 R87 / R90）
在装配时**原样透传**（`with_preserved_response()`）—— 两个工具写同一批文件，
不透明传就会互相抹掉对方的内容。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any

MANUAL_FILENAME = "MIDAS_API_Online_Manual_数据_v1.0.json"
DEV_DOC_FILENAME = "MIDAS_API_开发文档_v1.0.md"
MANIFEST_FILENAME = "manifest.json"
DIALECT = "http://json-schema.org/draft-07/schema#"

# 端点 key → (schema 文件相对路径, source, 来源定位)
JSON_SCHEMA_SOURCES: tuple[tuple[str, str, str], ...] = (
    (
        "POST.TABLE.WEIGHT_IRREGULARITY_X",
        "schema/products/gen_nx/post/TABLE/WEIGHT_IRREGULARITY_X.json",
        "help_center",
    ),
    (
        "POST.TABLE.CONCURRENT_JOINT_FORCE",
        "schema/products/gen_nx/post/TABLE/CONCURRENT_JOINT_FORCE.json",
        "help_center",
    ),
)

SPEC_TABLE_SOURCES: tuple[tuple[str, str, str, str], ...] = (
    (
        "POST.TABLE.STORY_SHEAR_FORCE_COEFFICIENT",
        "schema/products/gen_nx/post/TABLE/STORY_SHEAR_FORCE_COEFFICIENT.json",
        "help_center_spec_table",
        "title:Story Shear Force Coefficient",
    ),
    # P141：`manual_has_no_json_schema` 的 5 条（手册**同 URI** 条目只有规格表）
    (
        "OPE.MEMB",
        "schema/products/gen_nx/ope/MEMB.json",
        "help_center_spec_table",
        "uri:ope/MEMB",
    ),
    (
        "OPE.STOR",
        "schema/products/gen_nx/ope/STOR.json",
        "help_center_spec_table",
        "uri:ope/STOR",
    ),
    (
        "OPE.STORPROP",
        "schema/products/gen_nx/ope/STORPROP.json",
        "help_center_spec_table",
        "uri:ope/STORPROP",
    ),
    (
        "OPE.STORY_IRR_PARAM",
        "schema/products/gen_nx/ope/STORY_IRR_PARAM.json",
        "help_center_spec_table",
        "uri:ope/STORY_IRR_PARAM",
    ),
    (
        "OPE.STORY_PARAM",
        "schema/products/gen_nx/ope/STORY_PARAM.json",
        "help_center_spec_table",
        "uri:ope/STORY_PARAM",
    ),
)

DEV_DOC_SOURCES: tuple[tuple[str, str, str, str], ...] = (
    (
        "OPE.BMLD",
        "schema/products/civil_nx/ope/BMLD.json",
        "civil_nx_manual",
        "/OPE/BMLD",
    ),
)

TYPE_MAP = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "object": "object",
    "array": "array",
}

TOKEN_ADJUSTMENT_NOTE = (
    "本端点的 token 由 **API 实测**确认（GEN NX `POST /POST/TABLE` → `200`）；"
    "手册把本表与 `STORY_SHEAR_FOR_RS` 合并在**同一条目**里，故其规格表记的是**兄弟 token**。"
)


# ===== 上游资料 =====


def manual_entries(repo: pathlib.Path) -> list[dict[str, Any]]:
    """上游手册的端点条目（`json_schema` 是**字符串**）。"""
    payload = json.loads((repo / MANUAL_FILENAME).read_text(encoding="utf-8"))
    return list(payload["endpoints"])


def table_type_tokens(schema_text: str) -> set[str]:
    """从 `json_schema` 里抽出 `TABLE_TYPE` 的 `enum` 取值（机械扫描，不改写）。"""
    try:
        schema = json.loads(schema_text)
    except (TypeError, ValueError):
        return set()
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "TABLE_TYPE" and isinstance(value, dict):
                    for member in value.get("enum") or []:
                        if isinstance(member, str):
                            found.add(member)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema)
    return found


def entry_by_table_type(entries: list[dict[str, Any]], token: str) -> dict[str, Any]:
    """按 `TABLE_TYPE.enum` 定位条目（**恰好一条**，否则报错）。"""
    matches = [
        entry
        for entry in entries
        if token in table_type_tokens(str(entry.get("json_schema") or ""))
    ]
    if len(matches) != 1:
        raise SystemExit(f"❌ TABLE_TYPE = {token!r} 的手册条目数 = {len(matches)}，期望 1")
    return matches[0]


def entry_by_locator(
    entries: list[dict[str, Any]], locator: str, *, endpoint_uri: str
) -> dict[str, Any]:
    """按**声明的定位串**定位手册条目（**恰好一条**且**没有** `json_schema`，否则报错）。

    定位串两种（**不**猜）：

    - `uri:<input_uri>`：手册条目的 `input_uri` **逐字等于**它 —— 并**断言**该 URI 就是
      端点在数据侧的 URI（这正是 R5 的 `manual_has_no_json_schema` 类判据：**手册有同一个 URI**
      的条目，只是没有 `json_schema`）；
    - `title:<片段>`：手册条目的标题含该片段（如手册把两张表合并在同一条目里时用）。
    """
    kind, _, value = locator.partition(":")
    if kind == "uri":
        wanted = value.strip().lower()
        if wanted != endpoint_uri.strip().lower():
            raise SystemExit(f"❌ 定位串 {locator!r} 与端点 URI {endpoint_uri!r} 不一致")
        matches = [
            entry for entry in entries if str(entry.get("input_uri") or "").lower() == wanted
        ]
    elif kind == "title":
        fragment = value.strip().lower()
        matches = [
            entry
            for entry in entries
            if fragment in str(entry.get("title") or "").lower()
        ]
    else:
        raise SystemExit(f"❌ 未知的定位串种类：{locator!r}")
    if len(matches) != 1:
        raise SystemExit(f"❌ 定位串 {locator!r} 命中的手册条目数 = {len(matches)}，期望 1")
    entry = matches[0]
    if entry.get("json_schema"):
        raise SystemExit(f"❌ {locator!r} 的条目**有** json_schema → 应改走 manual_json_schema")
    return entry


def dev_doc_schema(repo: pathlib.Path, uri: str) -> dict[str, Any]:
    """从 `MIDAS_API_开发文档_v1.0.md` 的端点章节里取出**完整** JSON Schema。"""
    text = (repo / DEV_DOC_FILENAME).read_text(encoding="utf-8", errors="ignore")
    anchor = f"| URI | `{uri}` |"
    start = text.find(anchor)
    if start < 0:
        raise SystemExit(f"❌ 开发文档里找不到 `{uri}` 的条目")
    section = text[start:]
    fence = section.find("#### 请求示例")
    if fence < 0:
        raise SystemExit(f"❌ `{uri}` 章节里没有「请求示例」小节")
    match = re.search(r"```json\s*\n(.*?)\n```", section[fence:], re.S)
    if match is None:
        raise SystemExit(f"❌ `{uri}` 章节里没有 ```json 代码块")
    schema = json.loads(match.group(1))
    if not isinstance(schema, dict) or "properties" not in schema:
        raise SystemExit(f"❌ `{uri}` 的 JSON 块不是 JSON Schema（缺 properties）")
    return schema


# ===== 规格表 → JSON Schema =====


def _type_of(raw: object) -> dict[str, Any]:
    """规格表的「Value Type」→ JSON Schema 类型（未给类型 → 不写 `type`）。

    ⚠️ 规格表用**首字母大写**的写法（`String` / `Object` / `Array [String]`），
    而 JSON Schema 一律小写 → 此处**大小写归一**（`fix_schema_defects.py --check` 的不变量之一）。
    规格表的 `Default` 列（`Empty` / `System` / `-` …）不是 JSON 取值 → **不**搬进 Schema。
    """
    text = str(raw or "").strip()
    if text.lower().startswith("array"):
        inner = text[text.find("[") + 1 : text.rfind("]")] if "[" in text else ""
        first = inner.split(",")[0].strip().lower()
        item = {"type": TYPE_MAP[first]} if first in TYPE_MAP else {}
        return {"type": "array", "items": item} if item else {"type": "array"}
    lowered = text.lower()
    return {"type": TYPE_MAP[lowered]} if lowered in TYPE_MAP else {}


def spec_table_schema(
    entry: dict[str, Any], *, token: str, wrapper: str, adjust_token: bool
) -> dict[str, Any]:
    """规格表 → `{<wrapper>: {type: object, properties, required}}`（见模块文档的 5 条规则）。"""
    properties: dict[str, Any] = {}
    required: list[str] = []
    current: str | None = None
    for row in entry.get("specifications") or []:
        if not isinstance(row, list) or len(row) < 6:
            continue
        key_cell = str(row[2] or "").strip()
        match = re.fullmatch(r'"([A-Za-z0-9_]+)"', key_cell)
        if match is None:
            continue
        name = match.group(1)
        if name.lower() in {"no.", "description", "key", "value type", "default", "required"}:
            continue
        number = str(row[0] or "").strip()
        description = str(row[1] or "").strip()
        if name == "TABLE_TYPE" and adjust_token:
            description = f"{re.sub(chr(34) + '[A-Z0-9_]+' + chr(34), chr(34) + token + chr(34), description)}（{TOKEN_ADJUSTMENT_NOTE}）"
        node: dict[str, Any] = {"description": description}
        node.update(_type_of(row[3]))
        is_child = number.startswith("(") or "." in number
        if is_child and current is not None:
            parent = properties[current]
            parent.setdefault("properties", {})[name] = node
            if str(row[5] or "").strip().lower() == "required":
                parent.setdefault("required", []).append(name)
        else:
            properties[name] = node
            current = name
            if str(row[5] or "").strip().lower() == "required":
                required.append(name)

    if wrapper in properties and properties[wrapper].get("type") == "object":
        # 规格表自己声明了包装键（如 `"Argument"`）→ 用它，不再多包一层
        return {
            "$schema": DIALECT,
            "title": str(entry.get("title") or ""),
            "type": "object",
            "properties": {wrapper: properties[wrapper]},
        }
    return {
        "$schema": DIALECT,
        "title": str(entry.get("title") or ""),
        "type": "object",
        "properties": {wrapper: {"type": "object", "properties": properties, "required": required}},
    }


# ===== 装配 =====


def endpoint_entries(repo: pathlib.Path) -> dict[str, dict[str, Any]]:
    """`registry/manifest.json` 的 key → 条目（用于取 `uri` / 断言缺口）。"""
    document = json.loads((repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    return {str(entry["key"]): entry for entry in document["endpoints"]}


def endpoint_wrappers(repo: pathlib.Path) -> dict[str, str]:
    """端点 key → 数据侧声明的请求体包装键（从端点 YAML 读，**不**猜）。"""
    wrappers: dict[str, str] = {}
    for path in (repo / "registry").rglob("*.yaml"):
        if path.name == "instances.yaml" or "schema" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        key_match = re.search(r"^key:\s*(\S+)\s*$", text, re.M)
        if key_match is None:
            continue
        wrapper_match = re.search(r"^wrapper:\s*\n\s+write:\s*(\S+)\s*$", text, re.M)
        wrappers[key_match.group(1)] = wrapper_match.group(1) if wrapper_match else ""
    return wrappers


def build_documents(repo: pathlib.Path) -> list[tuple[str, dict[str, Any], str]]:
    """产出 `[(相对路径, 文件内容, 来源说明)]`（确定性；顺序固定）。"""
    entries = manual_entries(repo)
    manifest = endpoint_entries(repo)
    wrappers = endpoint_wrappers(repo)
    documents: list[tuple[str, dict[str, Any], str]] = []

    for key, relative, source in JSON_SCHEMA_SOURCES:
        entry = entry_by_table_type(entries, str(manifest[key]["table_type"]))
        schema = json.loads(str(entry["json_schema"]))
        documents.append(
            (
                relative,
                {
                    "key": key,
                    "uri": str(manifest[key]["uri"]).lstrip("/"),
                    "source": source,
                    "schema": schema,
                },
                f"手册条目 {entry.get('title')!r} 的 json_schema（TABLE_TYPE.enum 含 {manifest[key]['table_type']}）",
            )
        )

    for key, relative, source, fragment in SPEC_TABLE_SOURCES:  # `fragment` = 定位串（见 entry_by_locator）
        entry = entry_by_locator(
            entries, fragment, endpoint_uri=str(manifest[key]["uri"]).lstrip("/")
        )
        schema = spec_table_schema(
            entry,
            token=str(manifest[key]["table_type"]),
            wrapper=wrappers.get(key) or "Argument",
            adjust_token=True,
        )
        documents.append(
            (
                relative,
                {
                    "key": key,
                    "uri": str(manifest[key]["uri"]).lstrip("/"),
                    "source": source,
                    "schema": schema,
                },
                f"手册条目 {entry.get('title')!r} 的规格表（无 json_schema）",
            )
        )

    for key, relative, source, uri in DEV_DOC_SOURCES:
        schema = dev_doc_schema(repo, uri)
        documents.append(
            (
                relative,
                {
                    "key": key,
                    "uri": str(manifest[key]["uri"]).lstrip("/"),
                    "source": source,
                    "schema": schema,
                },
                f"{DEV_DOC_FILENAME} 的 {uri} 章节（来源《midas Civil NX - API 用户手册》）",
            )
        )
    return documents


def with_preserved_response(path: pathlib.Path, document: dict[str, Any]) -> dict[str, Any]:
    """把**别人拥有**的 `response` 块透传进本次装配结果（本工具**不**生成也不改写它）。

    本工具只拥有 `key` / `uri` / `source` / `schema` **四个**键；`response` 由
    `sync_response_schemas.py` 依 **L4 实测信封**追加（`docs/07` §16 R87 / R90）。
    两个工具写**同一批文件**，因此装配时必须透传 —— 否则 `--write` / `--check`
    会把另一个工具刚写的块**抹掉**。

    P141 实测：这 5 个端点补完请求 Schema 后，`OPE.STORY_IRR_PARAM` 与
    `OPE.STORY_PARAM` **立刻**满足 `sync_response_schemas.py` 的全部条件
    （`availability == verified` + 有 `GET` + 有可读 Schema 文件 + 声明了解包链）
    → 同一次收口里两个工具都会碰这两个文件。
    """
    if not path.is_file():
        return document
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return document
    if isinstance(current, dict) and "response" in current:
        return {**document, "response": current["response"]}
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R5 剩余补齐：生成请求 Schema 文件")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--write", action="store_true", help="实际写回（默认只预演）")
    parser.add_argument("--check", action="store_true", help="断言已落盘 == 机械结果（CI）")
    args = parser.parse_args(argv)

    repo = pathlib.Path(args.repo).resolve()
    registry = repo / "registry"
    documents = build_documents(repo)

    changed: list[str] = []
    missing: list[str] = []
    for relative, document, origin in documents:
        path = registry / relative
        document = with_preserved_response(path, document)
        text = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == text:
            continue
        changed.append(relative)
        print(f"  {relative}\n      ↳ 来源：{origin}")
        if current is None:
            missing.append(relative)
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")

    print(f"端点 = {len(documents)}；需写入文件 = {len(changed)}（其中新文件 {len(missing)}）")
    if args.check:
        if changed:
            print("❌ --check：已落盘内容与机械结果不一致（或文件缺失）")
            return 1
        print(f"✅ --check：{len(documents)} 个文件与机械结果一致")
        return 0
    if args.write:
        print("WROTE registry/schema/**" if changed else "无差异，未写入。")
    else:
        print("（预演模式；加 --write 才会写回）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
