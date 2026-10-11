#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P153：映射缺口 **517** 的**分类收口** —— 把 **271** 个「契约外」
（`not_in_operation_contract`）按**命名空间 / 能力码 / Tool 归属 / 是否已有 Transformer**
分桶，并给出「可纳入契约 / 需产品裁决」的**可复算**清单。

背景
----
P152 登记了映射缺口 **517** = **271** `not_in_operation_contract`（形态齐备：有 `GET` +
`read_root`，但 9 Tool 的 **69** 个 Operation **没有**一条映射到它）+ **246**
`no_readback_route`（没有 `GET` 或没有 `read_root`）。本工具**只**对那 **271** 个做分类：

* **`adoptable_with_existing_canonical_model`** —— 该端点**已有**写侧 Transformer
  （`transforms.py` 的 `TRANSFORMER_REGISTRY`）⇒ 纳入契约只需**声明** Operation
  （canonical 模型已存在）；
* **`needs_product_decision`** —— 该端点**没有**任何 Transformer ⇒ 纳入契约 =
  **新增 canonical 模型**（产品 / 契约裁决）。

判定点（**唯一**，不另写一份规则）
----------------------------------
* 缺口本身**只**由 `registry/tools/probe_interface_paths.py` 的 `mapping_gap()`
  复算（它**只**读 `operations.py` 的 `OPERATION_PLANS` + `registry/manifest.json`）；
* 能力码 / Tool 归属**只**读端点 YAML（`capability` / `tool_map`，端点 YAML 是唯一真源）；
* 「是否已有 Transformer」**只**读 `transforms.py` 的 `TRANSFORMER_REGISTRY`。

本工具**只登记**：**不**改 `app/**`、**不**改契约、**不**改 `registry/manifest.json`，
**不**动 P152 的缺口计数（`--check` 逐条断言缺口 271 / 246 与 P152 证据一致）。

用法
----
    python registry/tools/classify_mapping_gap.py --recon     # 离线：写分类清单（零请求）
    python registry/tools/classify_mapping_gap.py --check     # 离线复算
    python registry/tools/classify_mapping_gap.py --summary   # 摘要
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys
from collections.abc import Mapping
from typing import Any

import yaml

REPO_DEFAULT = "."
EVIDENCE_RELATIVE = "live/interface_mapping_classification.json"
"""映射缺口的**分类**清单（**离线可复算**；**零请求**）。"""

GAP_RELATIVE = "live/interface_mapping_gap.json"
"""P152 的缺口清单（本工具**只读**它做一致性断言，**不**改写）。"""

TEMPLATES_RELATIVE = "live/write_templates.json"
"""数据侧写路径手册示例模板（「是否有手册示例」的**唯一**判定点）。"""

PROBE_TOOL = "probe_interface_paths.py"
CRITERION_VERSION = 1

ADOPTABLE = "adoptable_with_existing_canonical_model"
ADOPTABLE_MANUAL = "adoptable_with_manual_example"
NEEDS_DECISION = "needs_product_decision"

READY_MANUAL = "manual_example_ready"
READY_SCHEMA = "schema_only"
READY_NONE = "no_request_schema"

REASON_NOT_IN_CONTRACT = "not_in_operation_contract"
REASON_NO_READBACK = "no_readback_route"


def _load_module(path: pathlib.Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def probe_tool() -> Any:
    """P152 的缺口复算工具（缺口定义的**唯一**判定点）。"""
    return _load_module(pathlib.Path(__file__).with_name(PROBE_TOOL), "structai_probe_paths_p153")


def _read_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


def manifest_index(repo: pathlib.Path) -> dict[str, dict[str, Any]]:
    """端点 key → manifest 条目。"""
    document = _read_json(repo / "registry" / "manifest.json")
    return {
        str(entry["key"]): dict(entry)
        for entry in document.get("endpoints") or []
        if isinstance(entry, Mapping) and entry.get("key")
    }


def yaml_fields(repo: pathlib.Path, definition: str) -> dict[str, Any]:
    """端点 YAML 的 `capability` / `tool_map`（端点 YAML 是唯一真源）。"""
    path = repo / "registry" / str(definition or "")
    if not path.is_file():
        return {"capability": [], "tool_map": {}}
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {"capability": [], "tool_map": {}}
    if not isinstance(document, Mapping):
        return {"capability": [], "tool_map": {}}
    capability = document.get("capability") or []
    if isinstance(capability, str):
        capability = [capability]
    tool_map = document.get("tool_map") or {}
    return {
        "capability": sorted(str(item) for item in capability),
        "tool_map": {
            str(key): str(value)
            for key, value in (tool_map.items() if isinstance(tool_map, Mapping) else ())
        },
    }


def transformer_endpoints(repo: pathlib.Path) -> dict[str, list[str]]:
    """端点 → 绑定它的 Transformer 名（**唯一**判定点 = `transforms.py`）。"""
    root = str(repo)
    if root not in sys.path:
        sys.path.insert(0, root)
    from app.infrastructure.adapters.midas.transforms import (  # noqa: PLC0415
        TRANSFORMER_REGISTRY,
    )

    rows: dict[str, list[str]] = {}
    for name, cls in sorted(TRANSFORMER_REGISTRY.items()):
        endpoint = str(getattr(cls, "endpoint", "") or "")
        if endpoint:
            rows.setdefault(endpoint, []).append(str(name))
    return rows


def classify(repo: pathlib.Path) -> dict[str, Any]:
    """把 **271** 个「契约外」端点分桶（**离线可复算**）。"""
    gap = probe_tool().mapping_gap(repo)
    index = manifest_index(repo)
    transformers = transformer_endpoints(repo)
    templates = _read_json(repo / "registry" / TEMPLATES_RELATIVE).get("templates") or {}
    rows: list[dict[str, Any]] = []
    for item in gap["gap_three_step"]:
        key = str(item["key"])
        entry = index.get(key) or {}
        fields = yaml_fields(repo, str(entry.get("definition") or ""))
        bound = transformers.get(key) or []
        has_template = key in templates
        has_schema = bool(entry.get("schema"))
        if bound:
            adoption = ADOPTABLE
        elif has_template:
            adoption = ADOPTABLE_MANUAL
        else:
            adoption = NEEDS_DECISION
        readiness = READY_MANUAL if has_template else (READY_SCHEMA if has_schema else READY_NONE)
        rows.append(
            {
                "key": key,
                "uri": str(item["uri"]),
                "namespace": str(entry.get("namespace") or key.split(".")[0]),
                "methods": str(item["methods"]),
                "read_root": str(item["read_root"]),
                "availability": str(item["availability"]),
                "table_type": str(entry.get("table_type") or ""),
                "risk_level": str((entry.get("risk") or {}).get("level") or ""),
                "capability": list(fields["capability"]),
                "tool_map": dict(fields["tool_map"]),
                "transformers": bound,
                "has_transformer": bool(bound),
                "has_request_schema": has_schema,
                "has_manual_example": has_template,
                "adoption": adoption,
                "readiness": readiness,
            }
        )

    def count_by(name: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            counts[str(row[name])] = counts.get(str(row[name]), 0) + 1
        return dict(sorted(counts.items()))

    def count_multi(name: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            for value in row[name]:
                counts[str(value)] = counts.get(str(value), 0) + 1
        return dict(sorted(counts.items()))

    adoptable = [row for row in rows if row["adoption"] == ADOPTABLE]
    adoptable_manual = [row for row in rows if row["adoption"] == ADOPTABLE_MANUAL]
    needs = [row for row in rows if row["adoption"] == NEEDS_DECISION]
    return {
        "note": [
            "P153：映射缺口 **517** 的**分类收口** —— 只对 **271** 个「契约外」"
            f"（`reason = {REASON_NOT_IN_CONTRACT}`）分桶；另 **246** 个 "
            f"`{REASON_NO_READBACK}` **不**在本清单内（它们的缺口是「读回不可表达」）。",
            f"`adoption = {ADOPTABLE}`：该端点**已有**写侧 Transformer ⇒ 纳入契约只需"
            "**声明** Operation（canonical 模型已存在）；"
            f"`adoption = {ADOPTABLE_MANUAL}`：**没有** Transformer，但有**数据侧手册示例模板**"
            "（已实测可用）⇒ 字段清单与可用取值已就绪，属「按既有模式补 canonical 模型」；"
            f"`adoption = {NEEDS_DECISION}`：两者都没有 ⇒ 连手册示例都没有，"
            "必须先裁决「要不要做 / 按哪份资料做」。",
            "判定点**唯一**：缺口**只**由 `registry/tools/probe_interface_paths.py` 的 "
            "`mapping_gap()` 复算（它**只**读 `operations.py` + `manifest.json`）；"
            "能力码 / Tool 归属**只**读端点 YAML 的 `capability` / `tool_map`；"
            "「是否已有 Transformer」**只**读 `transforms.py` 的 `TRANSFORMER_REGISTRY`；"
            "「是否有手册示例」**只**读 `registry/live/write_templates.json`。",
            "本清单**只登记**：**不**改 `app/**`、**不**改契约、**不**改 `registry/manifest.json`，"
            "**不**动 P152 的缺口计数（`--check` 逐条断言 271 / 246 与 P152 证据一致）。",
            "生成器 = `registry/tools/classify_mapping_gap.py --recon`（**零请求**）。",
        ],
        "criterion_version": CRITERION_VERSION,
        "gap_total": int(gap["gap_total"]),
        "gap_not_in_contract": len(rows),
        "gap_no_readback": len(gap["gap_no_readback"]),
        "mapped_endpoints": int(gap["mapped_endpoints"]),
        "write_capable_endpoints": int(gap["write_capable_endpoints"]),
        "three_step_endpoints": int(gap["three_step_endpoints"]),
        "buckets": {
            "by_namespace": count_by("namespace"),
            "by_capability": count_multi("capability"),
            "by_tool_map": count_multi("tool_map"),
            "by_adoption": count_by("adoption"),
            "by_readiness": count_by("readiness"),
            "by_availability": count_by("availability"),
        },
        "adoption_counts": {
            ADOPTABLE: len(adoptable),
            ADOPTABLE_MANUAL: len(adoptable_manual),
            NEEDS_DECISION: len(needs),
        },
        "adoptable": adoptable,
        "adoptable_with_manual_example": adoptable_manual,
        "needs_product_decision": needs,
        "endpoints": rows,
    }


def recon(repo: pathlib.Path) -> int:
    """写分类清单（**零请求**）。"""
    document = classify(repo)
    path = repo / "registry" / EVIDENCE_RELATIVE
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    buckets = document["buckets"]
    print(
        f"映射缺口分类：缺口 {document['gap_total']} = "
        f"契约外 {document['gap_not_in_contract']} + 无读回 {document['gap_no_readback']}"
    )
    print(f"  按命名空间：{buckets['by_namespace']}")
    print(f"  按能力码：{buckets['by_capability']}")
    print(f"  按 Tool 归属：{buckets['by_tool_map']}")
    print(f"  按可纳入性：{buckets['by_adoption']}")
    print(f"已写入 registry/{EVIDENCE_RELATIVE}")
    return 0


def check(repo: pathlib.Path) -> int:
    """离线断言：分类清单与 `mapping_gap()` / YAML / `transforms.py` 逐条一致。"""
    stored = _read_json(repo / "registry" / EVIDENCE_RELATIVE)
    if not stored:
        print(f"❌ 缺分类清单 registry/{EVIDENCE_RELATIVE}（先跑 --recon）")
        return 1
    fresh = classify(repo)
    problems: list[str] = []
    if int(stored.get("criterion_version") or 0) != CRITERION_VERSION:
        problems.append(f"{EVIDENCE_RELATIVE}: criterion_version 不符")
    for key in (
        "gap_total",
        "gap_not_in_contract",
        "gap_no_readback",
        "mapped_endpoints",
        "write_capable_endpoints",
        "three_step_endpoints",
    ):
        if int(stored.get(key) or -1) != int(fresh[key]):
            problems.append(f"{EVIDENCE_RELATIVE}: {key} = {stored.get(key)!r} ≠ 复算 {fresh[key]!r}")
    for key in (
        "buckets",
        "adoption_counts",
        "adoptable",
        "adoptable_with_manual_example",
        "needs_product_decision",
        "endpoints",
    ):
        if stored.get(key) != fresh[key]:
            problems.append(f"{EVIDENCE_RELATIVE}: {key} 与复算不一致")
    # 与 P152 的缺口清单**逐条**一致（缺口定义未被本工具改写）
    gap = _read_json(repo / "registry" / GAP_RELATIVE)
    if gap:
        if len(gap.get("gap_three_step") or []) != fresh["gap_not_in_contract"]:
            problems.append(f"{GAP_RELATIVE}: gap_three_step 条数 ≠ 分类清单的契约外条数")
        if len(gap.get("gap_no_readback") or []) != fresh["gap_no_readback"]:
            problems.append(f"{GAP_RELATIVE}: gap_no_readback 条数 ≠ 分类清单的无读回条数")
        keys_gap = {str(row["key"]) for row in gap.get("gap_three_step") or []}
        keys_classified = {str(row["key"]) for row in fresh["endpoints"]}
        if keys_gap != keys_classified:
            problems.append(f"{EVIDENCE_RELATIVE}: 契约外端点集 ≠ {GAP_RELATIVE}")
    # 三类互斥且覆盖全部
    adoptable = {str(row["key"]) for row in fresh["adoptable"]}
    manual = {str(row["key"]) for row in fresh["adoptable_with_manual_example"]}
    needs = {str(row["key"]) for row in fresh["needs_product_decision"]}
    if (adoptable & manual) or (adoptable & needs) or (manual & needs):
        problems.append(f"{EVIDENCE_RELATIVE}: 三类的交集 ≠ ∅")
    if len(adoptable | manual | needs) != fresh["gap_not_in_contract"]:
        problems.append(f"{EVIDENCE_RELATIVE}: 三类之并 ≠ 契约外条数")
    if problems:
        print("❌ 映射缺口分类清单不一致：")
        for item in problems:
            print(f"  - {item}")
        return 1
    buckets = fresh["buckets"]
    print(
        f"✅ 映射缺口分类自洽：契约外 {fresh['gap_not_in_contract']} = "
        f"已有 canonical 模型 {len(fresh['adoptable'])} + 有手册示例 {len(fresh['adoptable_with_manual_example'])}"
        f" + 需产品裁决 {len(fresh['needs_product_decision'])}"
        f"（无读回 {fresh['gap_no_readback']} 不在本清单）· 命名空间 {buckets['by_namespace']}"
    )
    return 0


def summary(repo: pathlib.Path) -> int:
    """打印分类摘要（只读）。"""
    document = _read_json(repo / "registry" / EVIDENCE_RELATIVE)
    if not document:
        print(f"❌ 缺分类清单 registry/{EVIDENCE_RELATIVE}（先跑 --recon）")
        return 1
    print(f"映射缺口分类清单：判据版本 {document.get('criterion_version')}")
    print(
        f"  缺口 {document.get('gap_total')} = 契约外 {document.get('gap_not_in_contract')} + "
        f"无读回 {document.get('gap_no_readback')}"
    )
    buckets = document.get("buckets") or {}
    for name in (
        "by_namespace",
        "by_capability",
        "by_tool_map",
        "by_adoption",
        "by_readiness",
        "by_availability",
    ):
        print(f"  {name}: {buckets.get(name)}")
    print(f"  可纳入（已有 canonical 模型）：{len(document.get('adoptable') or [])}")
    for row in document.get("adoptable") or []:
        print(f"    {row['key']} · {row['namespace']} · {row['capability']} · {row['transformers']}")
    print(
        "  可纳入（有数据侧手册示例 ⇒ 输入就绪）："
        f"{len(document.get('adoptable_with_manual_example') or [])}"
    )
    for row in document.get("adoptable_with_manual_example") or []:
        print(f"    {row['key']} · {row['namespace']} · {row['capability']}")
    print(f"  需产品裁决（无 Transformer 且无手册示例）：{len(document.get('needs_product_decision') or [])}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="P153：映射缺口 517 的分类收口（271 契约外分桶）")
    parser.add_argument("--repo", default=REPO_DEFAULT, help="仓库根目录（默认当前目录）")
    parser.add_argument("--recon", action="store_true", help="离线：写分类清单（零请求）")
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
