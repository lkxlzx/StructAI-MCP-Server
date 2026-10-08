#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R19 数据侧缺陷收口 —— `registry/schema/**` 的生成链归一（P138a）。

三类缺陷（P09 实测；`docs/07` §16 R19 / `registry/README.md` §2.1）：

1. **坏串**：`DB.MBTP` 的请求方向 `schema` 是**字符串**且不是合法 JSON。上游手册
   `MIDAS_API_Online_Manual_数据_v1.0.json` 的 `endpoints[].json_schema` 是**同一条坏串**
   （缺 1 个 `}`）→ 本工具从**上游重新生成**（补齐尾部闭合符 → 落成**对象**），
   **不**手改单个产物文件。
2. **占位分支**：`enum` / `oneOf` 列表里的 `"...(전체 N개)"`（手册该表共 N 项、未逐项转录，
   原文见 `MIDAS_API_开发文档_v1.0.md`）→ 换成**合法**分支：类型由**已转录成员**推断
   （推断不出就不写 `type`），并带 `description` 注明「手册该表共 N 项，仅转录前 K 项」。
   `oneOf` → `anyOf`：否则兜底分支会让已转录取值**恰好匹配两次**，把合法取值全判为非法。
   **不**编造枚举值。
3. **`type` 大小写**：`Number` / `String` / `Boolean` / `Object` / `Array` / `Integer` / `Null`
   → 小写（当前仅 `OPE.EDMP` 2 处）。上游手册 `specifications` 参数表里另有 1344 处
   `"Number"`，属**参数表**口径、不在 Schema 生成链内（`--check` 会如实报出）。

可复算 / 幂等：默认**预演**（只打印逐条差异），`--write` 写回，连跑第二次差异为 0。
写回格式与数据侧现状逐字节一致（`json.dumps(..., ensure_ascii=False, indent=2) + "\\n"`，LF）。
只依赖标准库。

用法（仓库根目录执行）：
    python registry/tools/fix_schema_defects.py            # 预演（只打印差异）
    python registry/tools/fix_schema_defects.py --write    # 写回
    python registry/tools/fix_schema_defects.py --check    # 只校验不变量（CI；不合规退出码 1）
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

#: 手册「未逐项转录」占位串（原文：`...(전체 19개)`）。
PLACEHOLDER_RE = re.compile(r"^\.\.\.\(전체\s*(\d+)개\)$")

#: `type` 关键字的**大小写归一**表（上游手册里的大小写变体 → JSON Schema 合法取值）。
TYPE_CASE_MAP = {
    "Number": "number",
    "String": "string",
    "Boolean": "boolean",
    "Object": "object",
    "Array": "array",
    "Integer": "integer",
    "Null": "null",
}

#: 允许出现占位分支的容器关键字。
PLACEHOLDER_KEYWORDS = ("enum", "oneOf", "anyOf", "allOf")

DEFAULT_MANUAL = "MIDAS_API_Online_Manual_数据_v1.0.json"
DEFAULT_DOC = "MIDAS_API_开发文档_v1.0.md"

EXPECTED_SCHEMA_FILES = 620
"""`registry/schema/**` 的文件数（**不变量**）。

P138a（R19 收口）时为 **616**；**P140** 的 R5 补齐**新增 4** 个请求 Schema 文件
（`POST.TABLE.{WEIGHT_IRREGULARITY_X, CONCURRENT_JOINT_FORCE, STORY_SHEAR_FORCE_COEFFICIENT}` 与
`OPE.BMLD`），由 `registry/tools/sync_request_schemas.py` 从上游手册 / 开发文档**机械生成**
（`--check` 断言「已落盘 == 机械结果」）→ **616 + 4 = 620**。
"""


# ===== 1. 尾部闭合符修复（只补缺失的闭合符，绝不猜内容）=====


def repair_json_text(text: str) -> str | None:
    """把「只缺尾部闭合符」的 JSON 文本补齐成可解析文本。

    只做**结构性**补齐：扫描时跳过字符串与转义，若扫描结束时仍有未闭合的 `{` / `[`
    且括号配平无交叉，就在尾部按栈逆序补上闭合符。补齐后必须能 `json.loads` 通过，
    否则返回 `None`（**不**猜内容、**不**臆造取值）。

    Args:
        text: 上游（或产物）里的 JSON 文本。

    Returns:
        可解析的 JSON 文本；无法**确定性**修复时返回 `None`。
    """
    stack: list[str] = []
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append(char)
        elif char in "}]":
            if not stack:
                return None
            opening = stack.pop()
            if (opening, char) not in (("{", "}"), ("[", "]")):
                return None
    if in_string or not stack:
        return None
    repaired = text + "".join("}" if item == "{" else "]" for item in reversed(stack))
    try:
        json.loads(repaired)
    except ValueError:
        return None
    return repaired


# ===== 2. `type` 大小写归一 =====


def _normalize_types(node: object, changes: list[str], path: str = "") -> None:
    """就地归一 `type` 的大小写（含 `type` 为列表的形式）。"""
    if isinstance(node, dict):
        if "type" in node:
            value = node["type"]
            if isinstance(value, str) and value in TYPE_CASE_MAP:
                node["type"] = TYPE_CASE_MAP[value]
                changes.append(f"type {value} -> {node['type']} @ {path or '/'}")
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    if isinstance(item, str) and item in TYPE_CASE_MAP:
                        value[index] = TYPE_CASE_MAP[item]
                        changes.append(
                            f"type[{index}] {item} -> {value[index]} @ {path or '/'}"
                        )
        for key, value in node.items():
            _normalize_types(value, changes, f"{path}/{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _normalize_types(item, changes, f"{path}[{index}]")


# ===== 3. 占位分支 → 合法分支 =====


def _json_type_of(value: object) -> str | None:
    """把已转录成员映射成 JSON Schema 的 `type` 名（推不出返回 `None`）。"""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if value is None:
        return "null"
    return None


def _member_type(member: object) -> str | None:
    """一个已转录成员的「类型」（`{const: ...}` / `{enum: [...]}` 取内部标量）。"""
    if isinstance(member, dict):
        if "const" in member:
            return _json_type_of(member["const"])
        if isinstance(member.get("enum"), list) and len(member["enum"]) == 1:
            return _json_type_of(member["enum"][0])
        return "object"
    return _json_type_of(member)


def _fallback_branch(transcribed: list[object], total: int) -> dict[str, object]:
    """占位串的合法替代分支：类型由已转录成员推断 + 如实说明未逐项转录。"""
    inferred = {_member_type(member) for member in transcribed}
    branch: dict[str, object] = {}
    if len(inferred) == 1 and None not in inferred:
        branch["type"] = next(iter(inferred))
    branch["description"] = (
        f"MIDAS 手册该表共 {total} 项，仅转录前 {len(transcribed)} 项（未逐项转录）；"
        "未转录取值由本分支放行，不编造枚举值。"
    )
    return branch


def _replace_keyword(
    node: dict[str, object], keyword: str, new_keyword: str, replacement: object
) -> None:
    """在**保持键顺序**的前提下把 `keyword` 换成 `new_keyword` + `replacement`。"""
    items: list[tuple[str, object]] = []
    for key, value in node.items():
        if key == keyword:
            items.append((new_keyword, replacement))
        else:
            items.append((key, value))
    node.clear()
    node.update(items)


def _legalize_placeholders(node: object, changes: list[str], path: str = "") -> None:
    """就地替换占位分支（`enum` / `oneOf` → `anyOf` + 兜底分支；`anyOf` / `allOf` 原位替换）。"""
    if isinstance(node, dict):
        for keyword in PLACEHOLDER_KEYWORDS:
            members = node.get(keyword)
            if not isinstance(members, list):
                continue
            totals = [
                int(match.group(1))
                for item in members
                if isinstance(item, str) and (match := PLACEHOLDER_RE.match(item))
            ]
            if not totals:
                continue
            total = max(totals)
            transcribed = [
                item
                for item in members
                if not (isinstance(item, str) and PLACEHOLDER_RE.match(item))
            ]
            fallback = _fallback_branch(transcribed, total)
            placeholder = f"...(전체 {total}개)"
            prefix = f'{keyword}({len(transcribed)} + "{placeholder}")'
            if keyword == "enum":
                # `enum` 里出现占位串 → 改成 `anyOf`：已转录取值的 enum + 兜底分支
                _replace_keyword(node, "enum", "anyOf", [{"enum": transcribed}, fallback])
                changes.append(f"{prefix} -> anyOf @ {path}/{keyword}")
            elif keyword == "oneOf":
                # `oneOf` 必须换关键字：兜底分支会让已转录取值**匹配两次**
                _replace_keyword(node, "oneOf", "anyOf", [*transcribed, fallback])
                changes.append(
                    f"{prefix} -> anyOf(手册共 {total} 项) @ {path}/{keyword}"
                )
            else:
                node[keyword] = [*transcribed, fallback]
                changes.append(
                    f"{prefix} -> 合法兜底分支(手册共 {total} 项) @ {path}/{keyword}"
                )
        for key, value in node.items():
            _legalize_placeholders(value, changes, f"{path}/{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _legalize_placeholders(item, changes, f"{path}[{index}]")


# ===== 文件级处理 =====


def _dump(document: dict[str, object]) -> str:
    """数据侧既定的落盘格式（逐字节可复算）。"""
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def _manual_by_uri(manual_path: pathlib.Path) -> dict[str, list[str]]:
    """上游手册的 `json_schema` 原文索引（`uri` 小写 → 候选文本）。"""
    payload = json.loads(manual_path.read_text(encoding="utf-8"))
    index: dict[str, list[str]] = {}
    for endpoint in payload["endpoints"]:
        index.setdefault(str(endpoint["input_uri"]).lower(), []).append(
            str(endpoint["json_schema"])
        )
    return index


def _upstream_object(manual: dict[str, list[str]], uri: str) -> tuple[object | None, bool]:
    """按 `uri` 从上游手册重建 Schema 对象；第二个返回值 = 是否用了「尾部闭合符修复」。"""
    for text in manual.get(uri.lower(), []):
        try:
            return json.loads(text), False
        except ValueError:
            repaired = repair_json_text(text)
            if repaired is not None:
                return json.loads(repaired), True
    return None, False


def process_file(
    path: pathlib.Path,
    *,
    manual: dict[str, list[str]],
    doc_text: str,
) -> tuple[dict[str, object] | None, list[str], list[str]]:
    """处理单个 Schema 文件。

    Returns:
        `(新文档 or None, 改动说明, 上游溯源说明)`。
    """
    text = path.read_text(encoding="utf-8")
    document = json.loads(text)
    if not isinstance(document, dict):
        raise ValueError(f"{path}: 顶层不是对象")
    changes: list[str] = []
    provenance: list[str] = []

    schema = document.get("schema")
    if isinstance(schema, str):
        rebuilt, repaired = _upstream_object(manual, str(document.get("uri", "")))
        if rebuilt is not None:
            document["schema"] = rebuilt
            changes.append(
                "schema: 字符串 -> 对象（从上游手册重新生成"
                + ("，补齐缺失的尾部闭合符" if repaired else "")
                + "）"
            )
            provenance.append(
                "上游手册 json_schema 与产物同一坏串 -> 已按上游重建"
                if repaired
                else "上游手册 json_schema 可直接解析 -> 已按上游重建"
            )
        else:
            local = repair_json_text(schema)
            if local is None:
                changes.append("schema: 字符串且无法确定性修复（**未改**）")
            else:
                document["schema"] = json.loads(local)
                changes.append("schema: 字符串 -> 对象（就地补齐尾部闭合符）")

    schema = document.get("schema")
    if isinstance(schema, dict):
        _normalize_types(schema, changes)
        _legalize_placeholders(schema, changes)

    if not changes:
        return None, [], provenance

    for item in changes:
        match = re.search(r"\.\.\.\(전체\s*(\d+)개\)", item)
        if match or "占位" in item:
            placeholder = f"...(전체 {match.group(1)}개)" if match else ""
            if placeholder and placeholder in doc_text:
                provenance.append(f"占位串 {placeholder} 出自 {DEFAULT_DOC}（手册原文）")
    return document, changes, provenance


def collect_files(registry_root: pathlib.Path) -> list[pathlib.Path]:
    """`registry/schema/**/*.json`，按路径排序（可复算）。"""
    return sorted((registry_root / "schema").rglob("*.json"))


def check_invariants(registry_root: pathlib.Path) -> list[str]:
    """R19 修复后的不变量（CI 可执行判定）；返回违规清单。"""
    violations: list[str] = []
    files = collect_files(registry_root)
    if len(files) != EXPECTED_SCHEMA_FILES:
        violations.append(f"registry/schema/** 文件数 = {len(files)}，期望 {EXPECTED_SCHEMA_FILES}")
    for path in files:
        relative = path.relative_to(registry_root).as_posix()
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:  # pragma: no cover - 防御性
            violations.append(f"{relative}: 不是合法 JSON（{error}）")
            continue
        schema = document.get("schema")
        if not isinstance(schema, dict):
            violations.append(f"{relative}: schema 不是对象（R19 缺陷 1）")
            continue
        found: list[str] = []
        _scan_violations(schema, found)
        violations.extend(f"{relative}: {item}" for item in found)
    return violations


def _scan_violations(node: object, found: list[str], path: str = "") -> None:
    """递归找残留的占位串与大小写不符的 `type`。"""
    if isinstance(node, dict):
        value = node.get("type")
        if isinstance(value, str) and value in TYPE_CASE_MAP:
            found.append(f"type {value!r} 未归一 @ {path}/type")
        for key, item in node.items():
            if key in PLACEHOLDER_KEYWORDS and isinstance(item, list):
                for member in item:
                    if isinstance(member, str) and PLACEHOLDER_RE.match(member):
                        found.append(f"残留占位串 @ {path}/{key}")
            _scan_violations(item, found, f"{path}/{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _scan_violations(item, found, f"{path}[{index}]")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R19 数据侧缺陷收口（生成链归一）")
    parser.add_argument("--repo", default=".", help="仓库根目录")
    parser.add_argument("--write", action="store_true", help="实际写回（默认只预演）")
    parser.add_argument("--check", action="store_true", help="只校验不变量（CI）")
    args = parser.parse_args(argv)

    repo = pathlib.Path(args.repo).resolve()
    registry_root = repo / "registry"

    if args.check:
        violations = check_invariants(registry_root)
        if violations:
            print(f"❌ 不变量违规 {len(violations)} 条：")
            for item in violations[:40]:
                print(f"  - {item}")
            return 1
        print(f"✅ registry/schema/** 文件数 = {len(collect_files(registry_root))}；"
              "schema 全为对象；无残留占位串；无大小写不符的 type。")
        return 0

    manual = _manual_by_uri(repo / DEFAULT_MANUAL)
    doc_path = repo / DEFAULT_DOC
    doc_text = doc_path.read_text(encoding="utf-8") if doc_path.exists() else ""

    files = collect_files(registry_root)
    touched = 0
    total_changes = 0
    for path in files:
        document, changes, provenance = process_file(
            path, manual=manual, doc_text=doc_text
        )
        if document is None:
            continue
        touched += 1
        total_changes += len(changes)
        print(f"  {path.relative_to(repo).as_posix()}")
        for item in changes:
            print(f"      {item}")
        for item in provenance:
            print(f"      ↳ 溯源：{item}")
        if args.write:
            path.write_text(_dump(document), encoding="utf-8", newline="\n")

    print(f"\n文件数 = {len(files)}；需改动文件 = {touched}；逐条改动 = {total_changes}")
    if args.write:
        print("WROTE registry/schema/**" if touched else "无差异，未写入。")
        violations = check_invariants(registry_root)
        if violations:
            print(f"❌ 写回后不变量违规 {len(violations)} 条：")
            for item in violations[:40]:
                print(f"  - {item}")
            return 1
        print("✅ 写回后不变量全部满足。")
    else:
        print("（预演模式；加 --write 才会写回）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
