#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P153：**R126 的裁决输入证据包** —— 逐端点复算「接口层 canonical → native 产出的 body」
vs「数据侧手册示例 body」的**字段差集**。

为什么需要这个工具
------------------
P152 实测：**接口层**（既有 9 Tool 契约）在专用空项目上创建 `DB.ELEM` / `DB.MATL` /
`DB.SECT` / `DB.CONS` 时被原生 `400 Wrong Field` / `400 Unknown Error` 拒绝，而**同一端点**
在**数据侧**用**手册示例**是**已实测可用**的（`registry/live/write_templates.json` +
`registry/live/put_edit_probe.json`）。⇒ 成因**不在**端点 / 护栏 / 数据侧模板，而在
**接口层的 canonical 模型**（`docs/04` §20–§31）。本工具把这个结论做成**可复算**的输入：

* **`field_set_gap`** —— 手册示例用了、而该端点的 Transformer **字段表表达不了**的原生字段
  （⇒ 只能「扩 canonical 字段集」或「允许原生默认值」**二选一**）；
* **`value_gap`** —— 字段表**能**表达、但接口层实测 body 里**没有值**（如空项目上无材质 /
  截面可引用的 `MATL` / `SECT`）⇒ 成因是**前置对象建不出来**（同一成因的连带面），
  **不是**字段集缺口；
* **`value_shape`** —— 两侧都有该字段但**形态不同**（如 `CONSTRAINT` 6 位 vs 手册 7 位）；
* **`no_canonical_model`** —— 该端点**没有任何** Transformer（⇒ 连 canonical 模型都没有，
  属「需产品裁决：要不要纳入契约」，与 R126 的字段集裁决**不同层**）。

判定点（**唯一**，不另写一份规则）
----------------------------------
* 「接口层能表达什么」**只**读 `app/infrastructure/adapters/midas/transforms.py` 的
  `TRANSFORMER_REGISTRY`（各 Transformer 的 `endpoint` + `fields` 字段表）；
* 「接口层实际产出了什么」**只**读 P152 的实测证据
  `registry/live/interface_path_probe.json` 的 `requests[].body`（**接口层真实发出**的请求体）；
* 「数据侧手册示例是什么」**只**读 `registry/live/write_templates.json` 的 `body`
  （其自身已由 `registry/tools/check_write_templates.py` 逐条复算）；
* 「哪个 Operation 映射到该端点」**只**读 `app/.../operations.py` 的 `OPERATION_PLANS`。

本工具**只**产出**输入**：**不**改 `app/**`、**不**改契约、**不**改数据侧模板、
**不**放宽任何既有判定。

用法
----
    # 离线：生成 / 刷新证据包（**零请求**）
    python registry/tools/check_canonical_field_gap.py --recon

    # 离线复算（CI 用）
    python registry/tools/check_canonical_field_gap.py --check

    # 摘要
    python registry/tools/check_canonical_field_gap.py --summary
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections.abc import Mapping, Sequence
from typing import Any

REPO_DEFAULT = "."
EVIDENCE_RELATIVE = "live/canonical_field_gap.json"
"""R126 的裁决输入证据包（**离线可复算**；**零请求**）。"""

TEMPLATES_RELATIVE = "live/write_templates.json"
INTERFACE_EVIDENCE_RELATIVE = "live/interface_path_probe.json"
CRITERION_VERSION = 1

GAP_FIELD_SET = "field_set_gap"
GAP_VALUE = "value_gap"
GAP_NO_MODEL = "no_canonical_model"
GAP_COVERED = "covered"

WRITE_INTENTS = frozenset(
    {"write_doc", "view", "view_display", "view_result", "view_capture", "analyze", "design"}
)
"""写步骤的 intent 前缀之外的**具名**写 intent（其余写 intent 以 `write_` 开头）。"""

RESULT_INTENTS = frozenset({"read", "result", "design_result"})
"""**读**侧 intent（这些步骤的 Transformer **不**算写侧字段表）。"""


def _load_app(repo: pathlib.Path) -> None:
    """把仓库根放进 `sys.path`（`registry/tools` 不是包）。"""
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))


def _read_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


# ===== 判定点：接口层能表达什么（transforms.py）=====


def write_endpoint_keys(repo: pathlib.Path) -> dict[str, list[str]]:
    """**写**端点 → 引用它的 Operation（**唯一**判定点 = `operations.py` 的编排）。"""
    _load_app(repo)
    from app.infrastructure.adapters.midas.operations import OPERATION_PLANS  # noqa: PLC0415

    rows: dict[str, list[str]] = {}
    for name, plan in sorted(OPERATION_PLANS.items()):
        steps = list(plan.steps)
        for route in sorted(plan.routes):
            steps.extend(plan.routes[route])
        for step in steps:
            if str(step.intent) in RESULT_INTENTS:
                continue
            rows.setdefault(str(step.key), []).append(name)
    return {key: sorted(set(value)) for key, value in rows.items()}


def write_transformers(repo: pathlib.Path) -> dict[str, list[dict[str, Any]]]:
    """端点 → 写侧 Transformer 字段表（**唯一**判定点 = `transforms.py`）。

    「写侧」判定：该 Transformer 的 `endpoint` 被 `operations.py` 里**非读侧 intent**
    （`read` / `result` / `design_result` 之外）的步骤引用。
    ⚠️ 荷载端点的步骤 `transformer` 写的是分派器 `midas.load.v1`，真正的字段表在
    `LOAD_TRANSFORMERS` 指向的具体类上（各自声明 `endpoint`）⇒ 这里按**端点**绑定，
    与 `LoadTransformer.delegate()` 的**同一份**声明对齐。
    """
    _load_app(repo)
    from app.infrastructure.adapters.midas.transforms import (  # noqa: PLC0415
        TRANSFORMER_REGISTRY,
    )

    write_keys = write_endpoint_keys(repo)
    tables: dict[str, list[dict[str, Any]]] = {}
    for name, cls in sorted(TRANSFORMER_REGISTRY.items()):
        endpoint = str(getattr(cls, "endpoint", "") or "")
        fields = tuple(getattr(cls, "fields", ()) or ())
        if not endpoint or not fields or endpoint not in write_keys:
            continue
        tables.setdefault(endpoint, []).append(
            {
                "name": name,
                "operations": write_keys[endpoint],
                "fields": [
                    {
                        "canonical": str(field.canonical),
                        "native": str(field.native),
                        "required": bool(field.required),
                    }
                    for field in fields
                ],
            }
        )
    return tables


# ===== 字段路径（递归、确定性）=====


def leaf_paths(value: Any, prefix: str = "") -> list[str]:
    """递归**叶子**点路径（数组用 `[]` 归一；空容器记为空串后缀）。"""
    if isinstance(value, Mapping):
        if not value:
            return [prefix or "<empty>"]
        rows: list[str] = []
        for key in sorted(value, key=str):
            rows.extend(leaf_paths(value[key], f"{prefix}.{key}" if prefix else str(key)))
        return rows
    if isinstance(value, Sequence) and not isinstance(value, str):
        if not value:
            return [f"{prefix}[]" if prefix else "<empty>"]
        rows = []
        for item in value:
            rows.extend(leaf_paths(item, f"{prefix}[]"))
        return rows
    return [prefix]


def leaf_keys(value: Any) -> list[str]:
    """递归**叶子键名**（去重、升序）—— 两侧结构不同（`Assign` 包装 / 编号键）时按名比对。"""
    keys: set[str] = set()
    for path in leaf_paths(value):
        name = path.split(".")[-1].removesuffix("[]")
        if name and name != "<empty>":
            keys.add(name)
    return sorted(keys)


def native_leaf(native: str) -> str:
    """Transformer 字段表的 native 路径 → 叶子键名（`PARAM[].ELAST` → `ELAST`）。"""
    return native.split(".")[-1].removesuffix("[]")


def _item_body(body: Any, wrapper: str) -> Any:
    """请求体 → **条目体**（去掉包装键与编号键 / `ITEMS` 外层）。"""
    inner = body
    if wrapper and wrapper != "none" and isinstance(body, Mapping) and wrapper in body:
        inner = body[wrapper]
    if isinstance(inner, Mapping):
        nested = inner.get("ITEMS")
        if isinstance(nested, Sequence) and not isinstance(nested, str) and nested:
            return nested[0]
        numeric = [key for key in inner if str(key).isdigit()]
        if len(numeric) == 1:
            return inner[numeric[0]]
    return inner


def interface_bodies(repo: pathlib.Path) -> dict[str, Any]:
    """端点 → **接口层实际发出**的条目体（判定点 = P152 证据的 `requests[].body`）。

    ⚠️ 一条证据行里的 `requests` 还包含**前置创建**（如 `DB.NODE`）⇒ 必须按
    **URI 后缀**把请求认回该端点（P153 实测：不按 URI 匹配会把前置节点的 body
    错记到目标端点上）。
    """
    document = _read_json(repo / "registry" / INTERFACE_EVIDENCE_RELATIVE)
    templates = _read_json(repo / "registry" / TEMPLATES_RELATIVE).get("templates") or {}
    manifest = _read_json(repo / "registry" / "manifest.json")
    uris = {
        str(entry.get("key")): "/" + str(entry.get("uri") or "").lstrip("/")
        for entry in manifest.get("endpoints") or []
        if isinstance(entry, Mapping)
    }
    # 端点 → (行优先级, 条目体)：`add` 行的**目标**创建优先（编辑行是同一形状）
    picked: dict[str, tuple[int, Any]] = {}
    for row in document.get("paths") or []:
        if not isinstance(row, Mapping):
            continue
        endpoint = str(row.get("endpoint") or "")
        uri = uris.get(endpoint, "")
        wrapper = str((templates.get(endpoint) or {}).get("wrapper") or "")
        priority = 0 if str(row.get("path")) == "add" else 1
        for item in row.get("requests") or []:
            if not isinstance(item, Mapping):
                continue
            if str(item.get("method")) not in {"POST", "PUT"}:
                continue
            if not uri or not str(item.get("path") or "").endswith(uri):
                continue
            body = item.get("body")
            if not isinstance(body, Mapping):
                continue
            current = picked.get(endpoint)
            if current is None or priority < current[0]:
                picked[endpoint] = (priority, _item_body(body, wrapper))
    return {endpoint: value for endpoint, (_, value) in picked.items()}


def _string_leaves(value: Any) -> dict[str, str]:
    """递归收集**叶子键名 → 字符串取值**（同名取**首个**；遍历顺序确定）。"""
    rows: dict[str, str] = {}

    def collect(node: Any, name: str) -> None:
        if isinstance(node, Mapping):
            for key in sorted(node, key=str):
                collect(node[key], str(key))
        elif isinstance(node, Sequence) and not isinstance(node, str):
            for item in node:
                collect(item, name)
        elif isinstance(node, str) and name and name not in rows:
            rows[name] = node

    collect(value, "")
    return rows


def _string_shape_diffs(interface: Any, template: Any) -> list[dict[str, Any]]:
    """两侧同名叶子键的**宽度差**（**只**看全数字串，如 `CONSTRAINT` 6 位 vs 手册 7 位）。

    ⚠️ 名字 / 描述类的字符串**长度不同不算形态差**（`P152M1` vs `DB_Steel`）⇒
    只有**两侧都是全数字串**且长度不同才记（自由度串 / 位标志串的典型形态）。
    """
    left = _string_leaves(interface)
    right = _string_leaves(template)
    diffs: list[dict[str, Any]] = []
    for key in sorted(set(left) & set(right)):
        if not (left[key].isdigit() and right[key].isdigit()):
            continue
        if left[key] == right[key] or len(left[key]) == len(right[key]):
            continue
        diffs.append(
            {
                "field": key,
                "interface": left[key],
                "interface_length": len(left[key]),
                "template": right[key],
                "template_length": len(right[key]),
            }
        )
    return diffs


def build_rows(repo: pathlib.Path) -> list[dict[str, Any]]:
    """逐端点（数据侧 **71** 个模板端点）的字段差集（**离线可复算**）。"""
    templates = _read_json(repo / "registry" / TEMPLATES_RELATIVE).get("templates") or {}
    tables = write_transformers(repo)
    operations = write_endpoint_keys(repo)
    bodies = interface_bodies(repo)
    rows: list[dict[str, Any]] = []
    for endpoint in sorted(templates):
        entry = templates[endpoint] if isinstance(templates[endpoint], Mapping) else {}
        template_body = entry.get("body")
        template_keys = leaf_keys(template_body)
        bound = tables.get(endpoint) or []
        declared_keys = sorted(
            {native_leaf(str(field["native"])) for item in bound for field in item["fields"]}
        )
        interface_body = bodies.get(endpoint)
        interface_keys = leaf_keys(interface_body) if interface_body is not None else None
        # 「能产出」= 字段表声明的 ∪ **实测产出过**的（如 `CONSTRAINT` 由 `to_native`
        # 从六个自由度**合成**，不在字段表里 —— 只数字段表会把它误判成缺口）。
        synthesized = (
            sorted(set(interface_keys) - set(declared_keys))
            if interface_keys is not None
            else []
        )
        expressible_keys = sorted(set(declared_keys) | set(interface_keys or []))
        required_paths = sorted(
            {
                str(field["native"])
                for item in bound
                for field in item["fields"]
                if field["required"]
            }
        )
        missing = sorted(set(template_keys) - set(expressible_keys)) if bound else template_keys
        unfilled = (
            sorted(set(expressible_keys) - set(interface_keys))
            if bound and interface_keys is not None
            else []
        )
        extra = sorted(set(expressible_keys) - set(template_keys)) if bound else []
        shape = _string_shape_diffs(interface_body, template_body) if interface_body else []
        if not bound:
            gap_class = GAP_NO_MODEL
        elif missing:
            gap_class = GAP_FIELD_SET
        elif unfilled or shape:
            gap_class = GAP_VALUE
        else:
            gap_class = GAP_COVERED
        rows.append(
            {
                "endpoint": endpoint,
                "wrapper": str(entry.get("wrapper") or ""),
                "has_transformer": bool(bound),
                "transformers": [str(item["name"]) for item in bound],
                "operations": sorted(
                    {name for item in bound for name in item["operations"]}
                    | set(operations.get(endpoint) or [])
                ),
                "template_keys": template_keys,
                "template_paths": sorted(leaf_paths(template_body)),
                "expressible_keys": expressible_keys,
                "declared_keys": declared_keys,
                "synthesized_keys": synthesized,
                "expressible_paths": sorted(
                    {str(field["native"]) for item in bound for field in item["fields"]}
                ),
                "required_paths": required_paths,
                "interface_keys": interface_keys if interface_keys is not None else [],
                "interface_body": interface_body,
                "missing_in_canonical": missing,
                "unfilled_expressible": unfilled,
                "extra_in_canonical": extra,
                "value_shape": shape,
                "gap_class": gap_class,
            }
        )
    return rows


def _leaf_values(value: Any) -> dict[str, Any]:
    """递归收集**叶子键名 → 取值**（任意类型；同名取**首个**；遍历顺序确定）。"""
    rows: dict[str, Any] = {}

    def collect(node: Any, name: str) -> None:
        if isinstance(node, Mapping):
            if not node and name and name not in rows:
                rows[name] = {}
                return
            for key in sorted(node, key=str):
                collect(node[key], str(key))
            return
        if isinstance(node, Sequence) and not isinstance(node, str):
            if not node and name and name not in rows:
                rows[name] = []
                return
            for item in node:
                collect(item, name)
            return
        if name and name not in rows:
            rows[name] = node

    collect(value, "")
    return rows


def _template_defaults(
    repo: pathlib.Path, row: Mapping[str, Any], fields: Sequence[str]
) -> list[dict[str, Any]]:
    """方案 B：缺口字段在**手册示例**里的取值（逐条可回溯，**不**臆造）。"""
    templates = _read_json(repo / "registry" / TEMPLATES_RELATIVE).get("templates") or {}
    entry = templates.get(str(row["endpoint"])) or {}
    values = _leaf_values(entry.get("body"))
    rows: list[dict[str, Any]] = []
    for name in fields:
        rows.append(
            {
                "native": name,
                "manual_example_value": values.get(name),
                "canonical_hint": name.lower(),
            }
        )
    return rows


def measured_rejections(repo: pathlib.Path) -> list[dict[str, Any]]:
    """P152 实测被原生拒绝的行（判定点 = P152 证据的 `write` / `cleanup` 的 `error`）。"""
    document = _read_json(repo / "registry" / INTERFACE_EVIDENCE_RELATIVE)
    rows: list[dict[str, Any]] = []
    for row in document.get("paths") or []:
        if not isinstance(row, Mapping) or str(row.get("status")) != "FAILED":
            continue
        error = (row.get("write") or {}).get("error") or {}
        native = ""
        for item in row.get("requests") or []:
            if isinstance(item, Mapping) and int(item.get("status") or 0) >= 400:
                native = str(item.get("native_error") or "")[:200]
        rows.append(
            {
                "endpoint": str(row.get("endpoint") or ""),
                "operation": str(row.get("operation") or ""),
                "path": str(row.get("path") or ""),
                "native_status": error.get("native_status"),
                "native_reason": str(error.get("native_reason") or ""),
                "native_error": native,
            }
        )
    return rows


def build_document(repo: pathlib.Path) -> dict[str, Any]:
    """证据包（逐端点字段差集 + **二选一**方案）。"""
    rows = build_rows(repo)
    by_endpoint = {str(row["endpoint"]): row for row in rows}
    field_set = sorted(row["endpoint"] for row in rows if row["gap_class"] == GAP_FIELD_SET)
    value_gap = sorted(row["endpoint"] for row in rows if row["gap_class"] == GAP_VALUE)
    no_model = sorted(row["endpoint"] for row in rows if row["gap_class"] == GAP_NO_MODEL)
    covered = sorted(row["endpoint"] for row in rows if row["gap_class"] == GAP_COVERED)
    option_a: dict[str, Any] = {}
    option_b: dict[str, Any] = {}
    value_gaps: dict[str, Any] = {}
    no_model_inventory: dict[str, Any] = {}
    for endpoint in sorted(by_endpoint):
        row = by_endpoint[endpoint]
        if not row["has_transformer"]:
            # 「二选一」**只**适用于**已有** canonical 模型的端点；没有模型的属另一层裁决
            no_model_inventory[endpoint] = {
                "operations": list(row["operations"]),
                "template_keys": list(row["template_keys"]),
                "note": "该端点**没有**任何写侧 Transformer ⇒ 连 canonical 模型都没有；"
                "属「需产品裁决：要不要纳入 9 Tool 契约」，**不是** R126 的字段集裁决。",
            }
            continue
        missing = list(row["missing_in_canonical"])
        if missing:
            option_a[endpoint] = [
                {
                    "native": name,
                    "canonical_hint": name.lower(),
                    "required": any(
                        str(path).split(".")[-1].removesuffix("[]") == name
                        for path in row["required_paths"]
                    ),
                }
                for name in missing
            ]
            option_b[endpoint] = _template_defaults(repo, row, missing)
        if row["unfilled_expressible"] or row["value_shape"]:
            value_gaps[endpoint] = {
                "unfilled_expressible": list(row["unfilled_expressible"]),
                "value_shape": list(row["value_shape"]),
                "note": "字段**已在** canonical 里（或由 Transformer 合成），接口层实测 body 里"
                "没有值 / 形态不同 ⇒ 成因是**前置对象 / 取值**，**不是**字段集缺口；"
                "**不**并入「二选一」方案。",
            }
    measured = measured_rejections(repo)
    measured_endpoints = sorted({str(item["endpoint"]) for item in measured})
    discovered = sorted((set(field_set) | set(value_gap)) - set(measured_endpoints))
    return {
        "note": [
            "P153 / **R126 的裁决输入证据包**：逐端点复算「接口层 canonical → native 产出的 body」"
            "vs「数据侧手册示例 body」的**字段差集**（**只**做输入，**不**改 `app/**`、"
            "**不**改契约、**不**放宽任何既有判定）。",
            f"`gap_class = {GAP_FIELD_SET}`：手册示例用了、而该端点的 Transformer **字段表"
            "表达不了**的原生字段 ⇒ 只能「扩 canonical 字段集」或「允许原生默认值」**二选一**。",
            f"`gap_class = {GAP_VALUE}`：字段表**能**表达、但接口层实测 body 里**没有值**"
            "（空项目上无前置对象可引用 / 形态不同）⇒ 成因是**前置对象建不出来**，"
            "**不是**字段集缺口。",
            f"`gap_class = {GAP_NO_MODEL}`：该端点**没有任何** Transformer ⇒ 连 canonical 模型"
            "都没有（属「需产品裁决：要不要纳入契约」，与 R126 的字段集裁决**不同层**）。",
            "判定点**唯一**：接口层能表达什么 = `transforms.py` 的 `TRANSFORMER_REGISTRY`；"
            "接口层实际产出什么 = P152 证据 `requests[].body`；数据侧手册示例 = "
            f"`registry/{TEMPLATES_RELATIVE}` 的 `body`；Operation 映射 = `operations.py`。",
            "本清单**零请求**、**不改**任何数据侧文件；生成器 = "
            "`registry/tools/check_canonical_field_gap.py --recon`。",
        ],
        "criterion_version": CRITERION_VERSION,
        "summary": {
            "template_endpoints": len(rows),
            "with_transformer": len([row for row in rows if row["has_transformer"]]),
            "without_transformer": len(no_model),
            "field_set_gap": len(field_set),
            "value_gap": len(value_gap),
            "no_canonical_model": len(no_model),
            "covered": len(covered),
        },
        "buckets": {
            GAP_FIELD_SET: field_set,
            GAP_VALUE: value_gap,
            GAP_NO_MODEL: no_model,
            GAP_COVERED: covered,
        },
        "measured_rejections": measured,
        "measured_endpoints": measured_endpoints,
        "newly_discovered": discovered,
        "newly_discovered_note": "同一算法在**有 Transformer 的模板端点**上扫出的、"
        "P152 **未**实测过原生拒绝的端点（⇒ 只是字段差集，**不**声称会被拒；"
        "要断言必须再跑一次接口层 `--probe`）。",
        "options": {
            "A_extend_canonical_field_set": {
                "note": "扩 canonical 字段集（`docs/04` §20–§31）—— 需同步 Operation 输入 Schema"
                "与 9 Tool Contract；**超出**本批授权（P153 只做输入）。",
                "endpoints": sorted(option_a),
                "per_endpoint": option_a,
                "requires": [
                    "`docs/04` §20–§31 canonical 字段集显式裁决",
                    "Operation 输入 Schema 同步（`structai://schema/...`）",
                    "9 Tool Contract / Operation 定义同步",
                ],
            },
            "B_allow_native_defaults": {
                "note": "**显式**允许「按手册示例补原生必填字段」的例外 —— 直接违反既有裁决"
                "「**不**臆造字段 / **不**虚构 `0`」（`transforms.py` §21 / §26 / §31），"
                "属**放宽**判定 ⇒ 必须由产品**显式**裁决。",
                "endpoints": sorted(option_b),
                "per_endpoint": option_b,
                "requires": [
                    "显式裁决例外（放宽 `transforms.py` 的『不臆造字段』）",
                    "逐字段声明默认值来源（本清单的 `manual_example_value` 即来源）",
                ],
            },
        },
        "value_gaps": value_gaps,
        "value_gaps_note": "字段**已在** canonical 里（或由 Transformer 合成）但实测 body 里"
        "没有值 / 形态不同 —— 成因是**前置对象 / 取值**（空项目），**不**属「二选一」的字段集裁决；"
        "⚠️ 这里**只**登记事实，**不**声称「补上就能通过」（要断言必须再实测）。",
        "no_canonical_model_inventory": no_model_inventory,
        "no_canonical_model_note": "**没有**写侧 Transformer 的模板端点（逐条给出该端点的"
        "Operation 与手册示例字段清单）—— 要纳入契约 = **新增 canonical 模型**（产品裁决），"
        "与 R126 的「扩既有模型字段集」**不同层**。",
        "endpoints": rows,
    }


def recon(repo: pathlib.Path) -> int:
    """写证据包（**零请求**）。"""
    document = build_document(repo)
    path = repo / "registry" / EVIDENCE_RELATIVE
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = document["summary"]
    print(
        f"R126 裁决输入：模板端点 {summary['template_endpoints']} · "
        f"有 Transformer {summary['with_transformer']} · "
        f"字段集缺口 {summary['field_set_gap']} · 取值缺口 {summary['value_gap']} · "
        f"无 canonical 模型 {summary['no_canonical_model']} · 已覆盖 {summary['covered']}"
    )
    print(f"已写入 registry/{EVIDENCE_RELATIVE}")
    return 0


def check(repo: pathlib.Path) -> int:
    """离线断言：证据包与 `transforms.py` / `operations.py` / 模板 / P152 证据逐条一致。"""
    stored = _read_json(repo / "registry" / EVIDENCE_RELATIVE)
    if not stored:
        print(f"❌ 缺证据包 registry/{EVIDENCE_RELATIVE}（先跑 --recon）")
        return 1
    fresh = build_document(repo)
    problems: list[str] = []
    if int(stored.get("criterion_version") or 0) != CRITERION_VERSION:
        problems.append(f"{EVIDENCE_RELATIVE}: criterion_version 不符")
    for key in (
        "summary",
        "buckets",
        "options",
        "value_gaps",
        "no_canonical_model_inventory",
        "measured_rejections",
        "measured_endpoints",
        "newly_discovered",
    ):
        if stored.get(key) != fresh[key]:
            problems.append(f"{EVIDENCE_RELATIVE}: {key} 与复算不一致")
    if stored.get("endpoints") != fresh["endpoints"]:
        problems.append(f"{EVIDENCE_RELATIVE}: endpoints 与复算不一致")
    # 4 个 R126 端点必须在列（P152 实测被原生拒绝的四个）
    r126 = ("DB.CONS", "DB.ELEM", "DB.MATL", "DB.SECT")
    index = {str(row["endpoint"]): row for row in fresh["endpoints"]}
    for endpoint in r126:
        row = index.get(endpoint)
        if row is None:
            problems.append(f"{endpoint}: 不在证据包里（R126 的 4 个端点必须逐条复算）")
            continue
        if not row["has_transformer"]:
            problems.append(f"{endpoint}: 有写侧 Transformer 但复算说没有")
        if row["interface_body"] is None:
            problems.append(f"{endpoint}: P152 证据里没有接口层实测 body")
    if problems:
        print("❌ R126 裁决输入证据包不一致：")
        for item in problems:
            print(f"  - {item}")
        return 1
    summary = fresh["summary"]
    print(
        "✅ R126 裁决输入证据包自洽：模板端点 "
        f"{summary['template_endpoints']}（有 Transformer {summary['with_transformer']} / "
        f"无 {summary['without_transformer']}）· 字段集缺口 {summary['field_set_gap']} · "
        f"取值缺口 {summary['value_gap']} · 无 canonical 模型 {summary['no_canonical_model']} · "
        f"已覆盖 {summary['covered']}"
    )
    return 0


def summary(repo: pathlib.Path) -> int:
    """打印证据包摘要（只读）。"""
    document = _read_json(repo / "registry" / EVIDENCE_RELATIVE)
    if not document:
        print(f"❌ 缺证据包 registry/{EVIDENCE_RELATIVE}（先跑 --recon）")
        return 1
    counts = document.get("summary") or {}
    print(f"R126 裁决输入证据包：判据版本 {document.get('criterion_version')}")
    for key in (
        "template_endpoints",
        "with_transformer",
        "without_transformer",
        "field_set_gap",
        "value_gap",
        "no_canonical_model",
        "covered",
    ):
        print(f"  {key} = {counts.get(key)}")
    buckets = document.get("buckets") or {}
    print(f"  字段集缺口：{buckets.get(GAP_FIELD_SET)}")
    print(f"  取值缺口：{buckets.get(GAP_VALUE)}")
    for row in document.get("endpoints") or []:
        if row.get("gap_class") == GAP_NO_MODEL:
            continue
        print(
            f"  {row.get('endpoint')} [{row.get('gap_class')}] "
            f"缺字段={row.get('missing_in_canonical')} "
            f"未填={row.get('unfilled_expressible')} 形态差={row.get('value_shape')}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="P153：R126 的裁决输入证据包（字段差集）")
    parser.add_argument("--repo", default=REPO_DEFAULT, help="仓库根目录（默认当前目录）")
    parser.add_argument("--recon", action="store_true", help="离线：写证据包（零请求）")
    parser.add_argument("--check", action="store_true", help="离线：断言与判定点一致")
    parser.add_argument("--summary", action="store_true", help="打印摘要")
    args = parser.parse_args(argv)
    repo = pathlib.Path(args.repo).resolve()
    if args.recon:
        return recon(repo)
    if args.check:
        return check(repo)
    if args.summary:
        return summary(repo)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
