#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校验 `registry/live/write_templates.json`（P139：写路径 L5 的请求体模板）。

为什么需要这个工具
------------------
P138c 的真实批量实测暴露：`write_probe.derive_body()` 从数据侧 Schema **机械派生**的
请求体（`default` / `const` / `enum[0]` / 类型零值）会被实例拒绝（9 / 10 个候选 `400`）。
P139 为这 9 个端点补了**真实请求体模板**。模板**不得**是「凭印象手写的 JSON」，
否则等于把伪造搬进数据侧。本工具把每一条模板**逐条复算**：

1. **来源可复算**（`source.kind` = `manual_example` / `manual_example_adjusted`）：
   模板 `body` 必须**等于**「上游手册 `MIDAS_API_Online_Manual_数据_v1.0.json` 里
   `endpoints[].examples[].json` 的某个包装编号下的条目」再**施加本文件声明的
   `adjustments`**（逐条 `from` → `to`）。任何取值漂移都会被逐条报出。
   `manual_example` 种类**必须**没有 adjustments（原样照抄）。
2. **字段不臆造**（结构校验）：`body` 里的每个字段名都必须在数据侧请求 Schema 里
   存在（根级 / `ITEMS[]` 条目级 / 逐层嵌套）。Schema 未声明子字段时**不判**（如实
   报「不可判」，而不是假定合法）。
3. **前置链可执行**：`prerequisites[].key` 必须是已登记、已启用、含 `POST` 且有
   Schema 文件的端点；`item_id` 必须是正整数（探针**只**碰自建的编号）。

4. **目标编号来源可判**（P141 / R96 的反向依赖）：模板的 `target_id_source` 必须为空串或
   本模板里某个前置的 `<key>#<item_id>` 标签；被指向的前置**不得**又用 `id_source = "target"`
   （否则是循环依赖）。`DB.CONS` / `DB.CNLD` 的 `Assign` 键就是它那个节点号 —— 目标编号
   **取前置**编号，因此非空项目上也不会与既有编号冲突。

5. **编号声明可判**（P141 / R96）：`prerequisites[].id_source` 必须是 `allocated` / `target`；
   `prerequisites[].references[].in` 必须是 `owner` 或本模板里另一个前置的 `<key>#<id>`，
   且其 `path` 必须**存在**、当前取值必须**恰好**等于该前置声明的 `item_id`；模板的
   `self_references` 各路径必须存在且取值为正整数编号。**不**做「body 里每个像编号的整数
   都必须被声明」这类判定（同一个整数可能同时是材质号 / 截面号 / 枚举值，无从机械区分）。

用法（仓库根目录执行）
----------------------
    python registry/tools/check_write_templates.py           # 校验（不合规退出码 1）
    python registry/tools/check_write_templates.py --summary  # 只打印汇总

只依赖标准库（数据侧工具不引入新依赖）。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

MANUAL_FILENAME = "MIDAS_API_Online_Manual_数据_v1.0.json"
TEMPLATES_RELATIVE = "live/write_templates.json"
MANIFEST_FILENAME = "manifest.json"

MANUAL_KINDS = {"manual_example", "manual_example_adjusted"}
SOURCE_KINDS = MANUAL_KINDS | {"explicit_injection"}


# ===== 上游手册（唯一来源）=====


def manual_examples(repo: pathlib.Path) -> dict[str, dict[str, dict[str, Any]]]:
    """`input_uri` → {示例名 → 该示例的 `{包装键: {编号: 条目}}`}（原样解析，不改写）。"""
    payload = json.loads((repo / MANUAL_FILENAME).read_text(encoding="utf-8"))
    table: dict[str, dict[str, dict[str, Any]]] = {}
    for entry in payload["endpoints"]:
        uri = str(entry.get("input_uri") or "")
        if not uri:
            continue
        examples: dict[str, dict[str, Any]] = {}
        for example in entry.get("examples") or []:
            try:
                parsed = json.loads(example["json"])
            except (KeyError, TypeError, json.JSONDecodeError):
                continue
            if isinstance(parsed, dict):
                examples[str(example.get("name") or "")] = parsed
        table[uri] = examples
    return table


def manual_item(
    examples: dict[str, dict[str, Any]], *, uri: str, example: str, item_id: str
) -> Any:
    """取「某示例 → 某包装编号 → 条目」（取不到 → `None`，由调用方如实报错）。"""
    wrapper = examples.get(str(uri), {}).get(str(example))
    if not isinstance(wrapper, dict) or len(wrapper) != 1:
        return None
    inner = next(iter(wrapper.values()))
    if not isinstance(inner, dict):
        return None
    return inner.get(str(item_id))


# ===== 路径与 adjustments =====


def split_path(path: str) -> list[Any]:
    """`ITEMS[0].GROUP_NAME` → `["ITEMS", 0, "GROUP_NAME"]`（只支持点号 + 下标）。"""
    parts: list[Any] = []
    for segment in str(path).split("."):
        name, _, rest = segment.partition("[")
        if name:
            parts.append(name)
        while rest:
            index, _, rest = rest.partition("]")
            parts.append(int(index))
            rest = rest.lstrip("[")
    return parts


def apply_adjustments(item: Any, adjustments: list[dict[str, Any]]) -> Any:
    """按 adjustments 逐条替换（`from` 必须命中，否则报错）。"""
    document = json.loads(json.dumps(item))
    for step in adjustments:
        parts = split_path(str(step.get("path") or ""))
        if not parts:
            raise ValueError("adjustment path is empty")
        node = document
        for part in parts[:-1]:
            node = node[part]
        current = node[parts[-1]]
        if current != step.get("from"):
            raise ValueError(
                f"adjustment at {step.get('path')!r}: manual value is {current!r}, "
                f"declared from is {step.get('from')!r}"
            )
        node[parts[-1]] = step.get("to")
    return document


# ===== 数据侧 Schema（字段不臆造）=====


def request_schema(repo: pathlib.Path, relative: str) -> dict[str, Any] | None:
    """端点 Schema 文件的**请求方向**生效 Schema（剥离包装根键；无文件 → `None`）。"""
    if not relative:
        return None
    path = repo / "registry" / relative
    if not path.is_file():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    schema = document.get("schema")
    if not isinstance(schema, dict):
        return None
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for wrapper in ("Argument", "Assign"):
            node = properties.get(wrapper)
            if isinstance(node, dict) and isinstance(node.get("properties"), dict):
                return node
    return schema


def unknown_fields(body: Any, schema: dict[str, Any], path: str = "") -> list[str]:
    """`body` 里**数据侧 Schema 未声明**的字段路径（Schema 未声明子字段 → 不判）。"""
    if not isinstance(body, dict):
        return []
    properties = schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        return []
    found: list[str] = []
    for name, value in body.items():
        child = properties.get(name)
        where = f"{path}.{name}" if path else name
        if child is None:
            found.append(where)
            continue
        if isinstance(child, dict) and isinstance(child.get("items"), dict):
            items = child["items"]
            if isinstance(value, list):
                for index, item in enumerate(value):
                    found.extend(unknown_fields(item, items, f"{where}[{index}]"))
        else:
            found.extend(unknown_fields(value, child, where))
    return found


# ===== 主校验 =====


def check(repo: pathlib.Path) -> tuple[list[str], list[str], dict[str, int]]:
    """返回 `(错误, 提示, 计数)`（错误非空即不合规）。"""
    errors: list[str] = []
    notes: list[str] = []
    templates_path = repo / "registry" / TEMPLATES_RELATIVE
    if not templates_path.is_file():
        return ([f"missing {TEMPLATES_RELATIVE}"], [], {"templates": 0, "bodies": 0})
    document = json.loads(templates_path.read_text(encoding="utf-8"))
    templates = document.get("templates")
    if not isinstance(templates, dict) or not templates:
        return ([f"{TEMPLATES_RELATIVE}: templates 缺失或为空"], [], {"templates": 0, "bodies": 0})

    examples = manual_examples(repo)
    manifest = json.loads((repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    endpoints = {str(entry["key"]): entry for entry in manifest["endpoints"]}

    counts = {
        "templates": len(templates),
        "bodies": 0,
        "manual_example": 0,
        "unverifiable": 0,
        "references": 0,
        "self_references": 0,
    }
    for key, template in sorted(templates.items()):
        entry_errors = _check_endpoint(key, template, examples, endpoints, repo, counts, notes)
        errors.extend(entry_errors)
    return errors, notes, counts


def _check_endpoint(
    key: str,
    template: Any,
    examples: dict[str, dict[str, dict[str, Any]]],
    endpoints: dict[str, dict[str, Any]],
    repo: pathlib.Path,
    counts: dict[str, int],
    notes: list[str],
) -> list[str]:
    """校验一个端点模板（目标 + 前置链）。"""
    errors: list[str] = []
    if not isinstance(template, dict):
        return [f"{key}: 模板不是对象"]
    if "body" not in template:
        errors.append(f"{key}: 缺少 body")
    endpoint = endpoints.get(key)
    if endpoint is None:
        errors.append(f"{key}: 不在 manifest.json 里（模板必须对应已登记端点）")
    schema = request_schema(repo, str((endpoint or {}).get("schema") or ""))
    counts["bodies"] += 1
    errors.extend(_check_body(key, template, schema, examples, counts, notes, indent="  "))
    prerequisites = template.get("prerequisites") or []
    if not isinstance(prerequisites, list):
        errors.append(f"{key}: prerequisites 不是数组")
        prerequisites = []
    seen: set[tuple[str, str]] = set()
    for index, prerequisite in enumerate(prerequisites):
        where = f"{key}.prerequisites[{index}]"
        if not isinstance(prerequisite, dict):
            errors.append(f"{where}: 不是对象")
            continue
        prereq_key = str(prerequisite.get("key") or "")
        item_id = str(prerequisite.get("item_id") or "")
        if not item_id.isdigit() or int(item_id) <= 0:
            errors.append(f"{where}: item_id 必须是正整数（探针只碰自建编号）")
        if (prereq_key, item_id) in seen:
            errors.append(f"{where}: 前置 (key, item_id) 重复")
        seen.add((prereq_key, item_id))
        prereq_entry = endpoints.get(prereq_key)
        if prereq_entry is None:
            errors.append(f"{where}: {prereq_key} 不在 manifest.json 里")
            continue
        if not bool(prereq_entry.get("enabled", True)):
            errors.append(f"{where}: {prereq_key} 在数据侧被禁用（enabled: false）")
        methods = {str(part).strip().upper() for part in str(prereq_entry.get("methods") or "").split(",")}
        if "POST" not in methods:
            errors.append(f"{where}: {prereq_key} 没有 POST（无法创建前置对象）")
        counts["bodies"] += 1
        errors.extend(
            _check_body(
                where,
                prerequisite,
                request_schema(repo, str(prereq_entry.get("schema") or "")),
                examples,
                counts,
                notes,
                indent="    ",
            )
        )
    _check_references(key, template, prerequisites, errors, counts)
    return errors


def _check_body(
    where: str,
    entry: dict[str, Any],
    schema: dict[str, Any] | None,
    examples: dict[str, dict[str, dict[str, Any]]],
    counts: dict[str, int],
    notes: list[str],
    *,
    indent: str,
) -> list[str]:
    """校验一个 body（来源复算 + 字段不臆造）。"""
    errors: list[str] = []
    if "body" not in entry:
        return [f"{where}: 缺少 body"]
    body = entry["body"]
    source = entry.get("source")
    if not isinstance(source, dict):
        errors.append(f"{where}: 缺少 source（模板必须可追溯）")
        return errors
    kind = str(source.get("kind") or "")
    if kind not in SOURCE_KINDS:
        errors.append(f"{where}: source.kind = {kind!r} 不在允许集合里")
        return errors
    adjustments = entry.get("adjustments") or []
    if not isinstance(adjustments, list):
        errors.append(f"{where}: adjustments 不是数组")
        return errors
    if kind in MANUAL_KINDS:
        counts["manual_example"] += 1
        if kind == "manual_example" and adjustments:
            errors.append(f"{where}: kind = manual_example 不得带 adjustments（必须原样照抄）")
        item = manual_item(
            examples,
            uri=str(source.get("uri") or ""),
            example=str(source.get("example") or ""),
            item_id=str(source.get("example_id") or ""),
        )
        if item is None:
            errors.append(
                f"{where}: 上游手册里找不到 "
                f"{source.get('uri')}#{source.get('example')}[{source.get('example_id')}]"
            )
        else:
            try:
                expected = apply_adjustments(item, adjustments)
            except (KeyError, IndexError, TypeError, ValueError) as error:
                errors.append(f"{where}: adjustments 无法施加（{error}）")
            else:
                if expected != body:
                    errors.append(
                        f"{where}: body 与「手册示例 + adjustments」不一致\n"
                        f"{indent}      手册复算 = {json.dumps(expected, ensure_ascii=False, sort_keys=True)}\n"
                        f"{indent}      文件声明 = {json.dumps(body, ensure_ascii=False, sort_keys=True)}"
                    )
    if schema is None:
        counts["unverifiable"] += 1
        notes.append(f"{where}: 无请求 Schema 文件 → 只做来源复算，字段不臆造**不可判**")
        return errors
    invented = unknown_fields(body, schema)
    if invented:
        errors.append(f"{where}: body 含数据侧 Schema 未声明的字段：{sorted(set(invented))}")
    return errors


def _parts_of(path: Any) -> list[Any] | None:
    """JSON 数组形态的路径 → `list`（非数组 / 空 / 段类型不符 → `None`）。"""
    if not isinstance(path, list) or not path:
        return None
    for segment in path:
        if isinstance(segment, bool) or not isinstance(segment, (str, int)):
            return None
    return list(path)


def _check_reference_value(
    where: str, container: dict[str, Any], path: Any, item_id: str, errors: list[str]
) -> None:
    """该路径必须**存在**；给了 `item_id` 时取值必须**恰好**是它（`from` 口径，**不**猜）。"""
    parts = _parts_of(path)
    if parts is None:
        errors.append(f"{where}: path 必须是「字符串键 + 整数下标」的非空数组")
        return
    node: Any = container.get("body")
    for step in parts:
        try:
            node = node[step]
        except (KeyError, IndexError, TypeError):
            errors.append(f"{where}: body 里没有路径 {parts!r}")
            return
    if item_id:
        if node != int(item_id):
            errors.append(
                f"{where}: 路径 {parts!r} 的取值是 {node!r}，声明的前置编号是 {item_id!r}"
            )
        return
    if isinstance(node, bool) or not isinstance(node, int) or node <= 0:
        errors.append(f"{where}: 路径 {parts!r} 的取值 {node!r} 不是正整数编号")


def _check_references(
    key: str,
    template: dict[str, Any],
    prerequisites: list[Any],
    errors: list[str],
    counts: dict[str, int],
) -> None:
    """校验 P141 / R96 的编号声明（`id_source` / `references` / `self_references`）。

    ⚠️ 本函数**只**做**可判**的检查：声明的路径必须存在、且当前取值必须**恰好**等于声明的编号
    （这样运行期的「写回」才是良定义的）。**不**做「body 里每个像编号的整数都必须被声明」
    这类判定 —— 同一个整数（如 `1`）可能同时是材质号 / 截面号 / 节点号 / 枚举值，
    无从机械区分，硬判只会制造假阳性。
    """
    labels: dict[str, dict[str, Any]] = {"owner": template}
    for prerequisite in prerequisites:
        if isinstance(prerequisite, dict):
            labels[f"{prerequisite.get('key')}#{prerequisite.get('item_id')}"] = prerequisite
    target_id_source = str(template.get("target_id_source") or "")
    if target_id_source:
        source_entry = labels.get(target_id_source)
        if source_entry is None or source_entry is template:
            errors.append(
                f"{key}: target_id_source = {target_id_source!r} 不是本模板里某个前置的标签"
            )
        elif str(source_entry.get("id_source") or "allocated") == "target":
            errors.append(f"{key}: target_id_source 指向的前置又用 id_source = target → 循环依赖")
    for index, prerequisite in enumerate(prerequisites):
        if not isinstance(prerequisite, dict):
            continue
        where = f"{key}.prerequisites[{index}]"
        item_id = str(prerequisite.get("item_id") or "")
        id_source = str(prerequisite.get("id_source") or "allocated")
        if id_source not in {"allocated", "target"}:
            errors.append(f"{where}: id_source = {id_source!r} 不在 {{allocated, target}} 里")
        references = prerequisite.get("references") or []
        if not isinstance(references, list):
            errors.append(f"{where}: references 不是数组")
            continue
        counts["references"] += len(references)
        for position, reference in enumerate(references):
            at = f"{where}.references[{position}]"
            if not isinstance(reference, dict):
                errors.append(f"{at}: 不是对象")
                continue
            label = str(reference.get("in") or "")
            container = labels.get(label)
            if container is None:
                errors.append(f"{at}: in = {label!r} 不是 owner、也不是本模板里的前置标签")
                continue
            _check_reference_value(at, container, reference.get("path"), item_id, errors)
    self_references = template.get("self_references") or []
    if not isinstance(self_references, list):
        errors.append(f"{key}: self_references 不是数组")
        return
    counts["self_references"] += len(self_references)
    for position, path in enumerate(self_references):
        _check_reference_value(
            f"{key}.self_references[{position}]", template, path, "", errors
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--summary", action="store_true", help="只打印汇总")
    args = parser.parse_args()

    repo = pathlib.Path(args.repo).resolve()
    errors, notes, counts = check(repo)
    print(f"模板文件 = registry/{TEMPLATES_RELATIVE}")
    print(f"端点模板 = {counts['templates']}；校验的 body 数 = {counts['bodies']}")
    print(f"来源 = 手册示例（含调整）的 body 数 = {counts['manual_example']}")
    print(f"不可判（无请求 Schema）的 body 数 = {counts['unverifiable']}")
    print(f"引用的编号路径（references）= {counts['references']}")
    print(f"目标自身编号路径（self_references）= {counts['self_references']}")
    if notes and not args.summary:
        print("-" * 90)
        for note in notes:
            print(f"  NOTE {note}")
    if errors:
        print("-" * 90)
        for error in errors:
            print(f"  FAIL {error}")
        print(f"\n不合规：{len(errors)} 条")
        return 1
    print("\n✅ 全部模板的来源可复算；body 无 Schema 未声明的字段；前置链可执行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
