#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R117：请求方向 Schema 的「覆盖不全」收口（P150）。

为什么需要这个工具
------------------
`registry/schema/**` 的**请求方向** Schema 是**手册子集**的转录（`registry/README.md` §2.1
「外部手册 / 权威来源**原样登记**」）。而端点定义里**已登记**一个**只读**的机械来源：

    schema_ref.introspect: info/db/<CODE>      →  GET /info/db/<CODE>

它返回本 build **自己声明的**请求形状（`{$schema, Argument: {type: object, properties: {...}}}`，
`registry/README.md` §4 / §2.3）。两者逐字段比对即可**机械**量化「数据侧只转录了子集」这件事
——本工具把它做成**可复算**的证据 + 落盘动作：

1. `--probe`（**只发 `GET`**，零副作用）：对**全部**有 `introspect` 的端点逐条取自省，
   与数据侧请求 Schema 做**递归**字段集差集：
   * `introspect_only` = 自省**声明**而数据侧**没有**的字段路径（含「数据侧把该字段声明为
     **裸 `object`**（无 `properties`）而自省声明了子字段」的情形 —— 逐个子字段路径）；
   * `data_only` = 数据侧**有**而自省**没有**的字段路径（**反向缺口**，同样**如实**记录）。
   证据落 `registry/live/introspect_field_diff.json`（**不含任何凭据**；含自省原文，故
   `--write` / `--check` 均可**离线**复算）。

2. `--write`：按**裁决 R117**（见下）**只补**自省**实际声明**的字段（`--check` 逐字节可复算）。

3. `--check`：断言「盘面 == 证据的机械结果」——`introspect_only` 逐条可复算、可补的端点
   **已经补完**（无待写差异）、留缺的端点**未**被改动、计数一致、证据里**没有**凭据。

裁决 R117（**先写清楚再动手**）
------------------------------
| 取值 | 判据（工具**逐条**复算） | 影响面 |
| --- | --- | --- |
| `add_fields`（**补 Schema**） | 端点 `products` 含探针实例的产品 ∧ 每个待补节点的**整棵子树**都是合法 JSON Schema 片段 ∧ 待补字段的**父节点**未声明 `additionalProperties: false` | 白名单**内容**按本 build 的声明据实扩大（逐条记来源）；同时把若干「裸 `object` ⇒ **不可判**」的位置变成**可判** ⇒ 判定在该处**变强**（`check_write_templates` 的字段白名单**非空判**面扩大，可能**暴露新的既有缺口** —— 逐条裁决，**不**静默放宽） |
| `record_left_out`（**如实留缺**） | 下列任一：`product_not_probed`（端点不含探针产品 ⇒ 自省与端点**不可比**）· `invalid_introspect_node`（自省声明的节点**不是**合法 JSON Schema：`type` 非合法取值 / 数组无 `items`）· `strict_schema_conflict`（父节点 `additionalProperties: false` ⇒ 补字段会**放宽**一份**手工收紧**的 Schema） | 数据侧**一行未改**；原因与恢复条件逐条记进证据 |
| `no_gap` | 自省与数据侧**字段集一致** | 无 |
| `not_comparable` | 非 `200`（本 build 无该自省路由）或自省无条目节点或数据侧无请求 Schema 文件 | 如实记录 `status_code` / `detail` |

⚠️ **反向缺口（`data_only`）一律不动**：手册声明而本 build 自省**没有**的字段**不删**、
**不改名**（删除会**削弱**既有判定；`DB.ACTL` 的 `CLATS` vs `ACWC` 是 R101 已在案的
手册 / build 命名差异）——只**如实**记进证据。

纪律
----
* **只发 `GET`**（零副作用）：本工具**不**构造、**不**发送任何写请求。
* **分块 + 健康检查**（P149-B2 两次实例崩溃的教训）：每块 ≤ `--chunk-size`（默认 **20**）条，
  块间做**只读**健康检查 `GET /DB/NODE`；非 `200` ⇒ **立即中止**，并把「实例不可达 /
  `The project is not opened`」的行标成 `SKIPPED`（**不**冒充 `FAILED`）。
* **累积**：既有证据里的行**逐字节保留**（不重测），本批只补新目标；`CRITERION_VERSION`
  变更 ⇒ 既有行**全部**重测（判据变了，旧结论不成立）。
* 证据文件里**绝不**出现凭据（`MAPI-Key` 只经环境变量注入）。
* 数据侧工具**只依赖标准库**（唯一的跨工具依赖是同目录的 `check_write_templates.py`，
  以保证「字段白名单」的**形状判定点唯一**）。

用法（仓库根目录执行；`--probe` 需要 `MIDAS_BASE_URL` / `MIDAS_MAPI_KEY`）
------------------------------------------------------------------------
    # 只读自省扫描（**分块** ≤ 20 + 块间只读健康检查；可只测一部分：--only KEY1,KEY2）
    python registry/tools/sync_introspect_fields.py --probe
    python registry/tools/sync_introspect_fields.py --probe --chunk-size 10
    python registry/tools/sync_introspect_fields.py --probe --only DB.SECT,DB.ELEM

    # 按裁决落盘（只补自省声明的字段；默认只预演）
    python registry/tools/sync_introspect_fields.py --write

    # 断言一致（CI 用）
    python registry/tools/sync_introspect_fields.py --check
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import sys
from typing import Any

REPO_DEFAULT = "."
EVIDENCE_RELATIVE = "live/introspect_field_diff.json"
MANIFEST_FILENAME = "manifest.json"
CHECK_TOOL_FILENAME = "check_write_templates.py"

INSTANCE_ALIAS = "gen-local"
INSTANCE_PRODUCT = "GEN_NX"
PROBED_AT = "2026-10-11"
"""证据的**实测日期**（P150；与 P149-D / P149-E 同日）。"""

CRITERION_VERSION = 1
"""判据版本：变更 ⇒ 既有证据行**全部**重测（判据变了，旧结论不成立）。"""

CHUNK_SIZE = 20
"""每块端点上限（P149-B2 两次实例崩溃的教训：**绝不**一次连发；块间做只读健康检查）。"""

HEALTH_PATH = "/DB/NODE"
"""块间**只读**健康检查路径；非 `200` ⇒ **立即中止**并如实记录（**不**继续发请求）。"""

INSTANCE_DOWN_MARKER = "The project is not opened"
"""实例崩溃后重启会**关闭项目** —— 该形态**不**算「端点被拒」（与 `sync_availability.py` 同口径）。"""

PASSED = "PASSED"
"""自省可取（`200` ∧ 有条目节点 ∧ 数据侧有请求 Schema）。"""

FAILED = "FAILED"
"""本 build **没有**该自省路由（非 `200`）—— 如实记录，**不**冒充「字段集一致」。"""

SKIPPED = "SKIPPED"
"""传输失败 / 实例不可达（续跑时重测；**不**计入任何收口）。"""

NOT_COMPARABLE = "NOT_COMPARABLE"
"""`200` 但**不可比**（自省无条目节点 / 数据侧无请求 Schema 文件）。"""

ADD_FIELDS = "add_fields"
RECORD_LEFT_OUT = "record_left_out"
NO_GAP = "no_gap"

REASON_PRODUCT_NOT_PROBED = "product_not_probed"
REASON_INVALID_NODE = "invalid_introspect_node"
REASON_STRICT_PARENT = "strict_schema_conflict"
REASON_INTROSPECT_DECLARED = "introspect_declared_and_schema_compatible"
REASON_NO_DIFF = "no_field_diff"
REASON_NOT_AVAILABLE = "not_available_on_instance"
REASON_NO_ITEM_NODE = "introspect_has_no_item_node"
REASON_NO_DATA_SCHEMA = "data_side_request_schema_missing"

LEGAL_TYPES = frozenset(
    {"object", "array", "string", "number", "integer", "boolean", "null"}
)
"""JSON Schema 的合法 `type` 取值（`fix_schema_defects.py` 的不变量之一：**小写**）。"""

SCHEMA_ROOT_KEY = "$schema"


# ===== 同目录工具（字段白名单的**形状判定点唯一**）=====


def _load_check_tool() -> Any:
    """装载同目录的 `check_write_templates.py`（形状判定与字段白名单**同源**）。"""
    path = pathlib.Path(__file__).resolve().parent / CHECK_TOOL_FILENAME
    spec = importlib.util.spec_from_file_location("structai_check_write_templates", path)
    if spec is None or spec.loader is None:  # pragma: no cover - 防御性
        raise SystemExit(f"❌ 无法装载 {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_yaml_module() -> Any:
    """PyYAML（仓库既有依赖，不新增）。"""
    import yaml  # noqa: PLC0415

    return yaml


# ===== 目标集 =====


def targets(repo: pathlib.Path) -> list[dict[str, Any]]:
    """全部「声明了 `schema_ref.introspect`」的端点（按 key 排序；`--only` 过滤在调用方）。

    Returns:
        `[{key, introspect, uri, schema, products, enabled, methods}, ...]`；`introspect`
        是端点定义里的**声明**（`info/db/<CODE>`），`uri` 是加前导斜杠后的调用路径。
    """
    manifest = json.loads((repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    yaml = _load_yaml_module()
    rows: list[dict[str, Any]] = []
    for item in manifest["endpoints"]:
        definition = repo / "registry" / str(item["definition"])
        document = yaml.safe_load(definition.read_text(encoding="utf-8"))
        introspect = str((document.get("schema_ref") or {}).get("introspect") or "").strip()
        if not introspect:
            continue
        rows.append(
            {
                "key": str(item["key"]),
                "introspect": introspect,
                "uri": "/" + introspect.lstrip("/"),
                "schema": str(item.get("schema") or ""),
                "products": [str(name) for name in (item.get("products") or [])],
                "enabled": bool(item.get("enabled", True)),
                "methods": str(item.get("methods") or ""),
            }
        )
    return sorted(rows, key=lambda row: str(row["key"]))


def target_keys(repo: pathlib.Path) -> list[str]:
    """全部有 `introspect` 的端点 key（**不**按可用性过滤：本工具是**只读**的）。"""
    return [str(row["key"]) for row in targets(repo)]


# ===== 自省 → 条目节点 =====


def item_node(payload: Any) -> dict[str, Any] | None:
    """自省响应 → **条目**节点（`Argument` / 单根键 / 根自身）。

    实测形态（**199 / 199** 一致）：`{"$schema": ..., "Argument": {"type": "object",
    "properties": {...}}}` —— 根键名是 `Argument`（**不**等于数据侧的 `wrapper.write`），
    其 `properties` 就是**条目字段表**，与数据侧 `request_schema()` 的条目 Schema 同级可比。
    """
    if not isinstance(payload, dict):
        return None
    keys = [name for name in payload if name != SCHEMA_ROOT_KEY]
    if len(keys) == 1 and isinstance(payload[keys[0]], dict):
        return payload[keys[0]]
    if isinstance(payload.get("properties"), dict):
        return payload
    return None


# ===== 递归差集 =====


def _properties(node: Any) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    value = node.get("properties")
    return value if isinstance(value, dict) else {}


def _flatten(node: Any, path: str, found: list[str]) -> None:
    """把 `node` 的**全部**后代字段路径平铺进 `found`（用于「一侧有 `properties`、另一侧没有」）。"""
    for name, child in _properties(node).items():
        where = f"{path}.{name}" if path else name
        found.append(where)
        _flatten(child, where, found)


def plan_additions(intro: Any, data: Any, path: str = "") -> list[tuple[str, Any]]:
    """`[(路径, 待插入节点)]`：自省**声明**而数据侧**没有**的字段（递归）。

    递归规则（**唯一**判定点，`--write` 与证据的 `introspect_only` 都由它产出）：

    * 自省有、数据侧**没有**该名字 ⇒ 整棵自省节点作为一个**插入**；
    * 两侧都有该名字、自省有 `properties` 而数据侧是**裸 `object`**（无 `properties`）
      ⇒ 逐个**子字段**作为一个插入（父节点保持原样，只补 `properties`）；
    * 两侧都有 `properties` ⇒ **递归**；
    * 其余（数据侧有 `properties` 而自省没有、或两侧都是叶子）⇒ **不**产出。
    """
    found: list[tuple[str, Any]] = []
    intro_properties = _properties(intro)
    data_properties = _properties(data)
    for name, node in intro_properties.items():
        where = f"{path}.{name}" if path else name
        if name not in data_properties:
            found.append((where, node))
            continue
        child = data_properties[name]
        if isinstance(node, dict) and isinstance(child, dict):
            if isinstance(node.get("properties"), dict) and not isinstance(
                child.get("properties"), dict
            ):
                for inner, inner_node in node["properties"].items():
                    found.append((f"{where}.{inner}", inner_node))
            else:
                found.extend(plan_additions(node, child, where))
    return found


def data_only_paths(intro: Any, data: Any, path: str = "") -> list[str]:
    """数据侧**有**而自省**没有**的字段路径（**反向缺口**，递归；只记录、**不**改动）。"""
    found: list[str] = []
    intro_properties = _properties(intro)
    data_properties = _properties(data)
    for name, node in data_properties.items():
        where = f"{path}.{name}" if path else name
        if name not in intro_properties:
            found.append(where)
            continue
        child = intro_properties[name]
        if isinstance(node, dict) and isinstance(child, dict):
            if isinstance(child.get("properties"), dict) and not isinstance(
                node.get("properties"), dict
            ):
                _flatten(node, where, found)
            else:
                found.extend(data_only_paths(child, node, where))
    return found


# ===== 裁决判据（**机械**、逐条可复算）=====


def decision_basis(decision: str, reasons: list[str]) -> str:
    """裁决的**依据**（单个串；`add_fields` / `no_gap` 的正面依据，其余取首个阻断原因）。"""
    if decision == ADD_FIELDS:
        return REASON_INTROSPECT_DECLARED
    if decision == NO_GAP:
        return REASON_NO_DIFF
    return reasons[0] if reasons else ""


def invalid_schema_fragments(node: Any, path: str = "") -> list[str]:
    """节点**整棵子树**里不是合法 JSON Schema 片段的位置（空 ⇒ 合法）。

    判据（`registry/README.md` §2.1 的生成链不变量）：`type` 必须是合法**小写**取值；
    `type: array` 必须带 `items`。实测本 build 的自省里 **4** 处 `type: "multi object"`
    （`DB.GALD.SUBTYPE` / `DB.GALD.LOAD` / `DB.SSEIS.INPUTS` / `DB.SWIND.INPUTS`）——
    它们**不得**被搬进数据侧（会引入非法关键字）。
    """
    found: list[str] = []
    if isinstance(node, dict):
        declared = node.get("type")
        if isinstance(declared, str) and declared not in LEGAL_TYPES:
            found.append(f"{path or '/'}/type={declared}")
        elif isinstance(declared, list):
            for item in declared:
                if item not in LEGAL_TYPES:
                    found.append(f"{path or '/'}/type[]={item}")
        if declared == "array" and not isinstance(node.get("items"), dict):
            found.append(f"{path or '/'}/array-without-items")
        for name, child in node.items():
            found.extend(invalid_schema_fragments(child, f"{path}/{name}"))
    elif isinstance(node, list):
        for index, child in enumerate(node):
            found.extend(invalid_schema_fragments(child, f"{path}[{index}]"))
    return found


def blocking_reasons(row: dict[str, Any], intro: Any, data: Any) -> list[str]:
    """该端点的**阻断原因**（空 ⇒ 可补）；按固定顺序逐条复算。

    三条判据（**不**放宽、**不**臆造）：

    * `product_not_probed`：端点的 `products` **不含**探针实例的产品 ⇒ 自省与端点**不可比**；
    * `strict_schema_conflict`：待补字段的**父节点**声明 `additionalProperties: false`
      ⇒ 补字段会**放宽**一份**手工收紧**的 Schema（数据侧**故意**收紧的判定不得被静默削弱）；
    * `invalid_introspect_node`：待补节点的**整棵子树**不是合法 JSON Schema 片段
      （`type` 非合法取值 / 数组无 `items`）⇒ 搬进数据侧会引入非法关键字。
    """
    reasons: list[str] = []
    if INSTANCE_PRODUCT not in row["products"]:
        reasons.append(REASON_PRODUCT_NOT_PROBED)
    pending = plan_additions(intro, data)
    for path, node in pending:
        parent = _parent_node(data, path)
        if isinstance(parent, dict) and parent.get("additionalProperties") is False:
            reasons.append(REASON_STRICT_PARENT)
            break
    for _, node in pending:
        if invalid_schema_fragments(node):
            reasons.append(REASON_INVALID_NODE)
            break
    return reasons


def _parent_node(item: dict[str, Any], dotted_path: str) -> Any:
    """条目 Schema 里该字段路径的**父节点**（取不到 ⇒ `None`）。"""
    parts = dotted_path.split(".")
    node: Any = item
    for name in parts[:-1]:
        node = _properties(node).get(name)
        if node is None:
            return None
    return node


# ===== 单端点实测 =====


def probe_key(client: Any, row: dict[str, Any], repo: pathlib.Path, check_tool: Any) -> dict[str, Any]:
    """单端点只读自省 + 递归差集 + 裁决（**只发 `GET`**；任何失败都被归类而**不**上抛）。"""
    base: dict[str, Any] = {
        "uri": row["uri"],
        "schema": row["schema"],
        "products": list(row["products"]),
        "introspect": None,
        "introspect_only": [],
        "data_only": [],
        "decision": "",
        "reasons": [],
        "basis": "",
    }
    try:
        response = client.get(row["uri"])
    except Exception as error:  # noqa: BLE001 - 传输失败 / 实例不可达如实归类
        return {
            **base,
            "status_code": "",
            "verdict": SKIPPED,
            "decision": NOT_COMPARABLE,
            "reasons": [REASON_NOT_AVAILABLE],
            "basis": REASON_NOT_AVAILABLE,
            "detail": type(error).__name__,
        }
    detail = ""
    if response.status_code != 200:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            detail = str(payload["error"].get("message") or "")[:200]
        verdict = SKIPPED if INSTANCE_DOWN_MARKER in detail else FAILED
        return {
            **base,
            "status_code": response.status_code,
            "verdict": verdict,
            "decision": NOT_COMPARABLE,
            "reasons": [REASON_NOT_AVAILABLE],
            "basis": REASON_NOT_AVAILABLE,
            "detail": detail or f"http_{response.status_code}",
        }
    try:
        payload = response.json()
    except ValueError:
        payload = None
    node = item_node(payload)
    if node is None:
        return {
            **base,
            "status_code": 200,
            "verdict": NOT_COMPARABLE,
            "decision": NOT_COMPARABLE,
            "reasons": [REASON_NO_ITEM_NODE],
            "basis": REASON_NO_ITEM_NODE,
            "detail": "introspect_payload_has_no_item_node",
        }
    data = check_tool.request_schema(repo, row["schema"], row["key"])
    if data is None:
        return {
            **base,
            "status_code": 200,
            "verdict": NOT_COMPARABLE,
            "decision": NOT_COMPARABLE,
            "reasons": [REASON_NO_DATA_SCHEMA],
            "basis": REASON_NO_DATA_SCHEMA,
            "detail": "no_request_schema_file",
        }
    introspect_only = [path for path, _ in plan_additions(node, data)]
    data_only = data_only_paths(node, data)
    reasons = blocking_reasons(row, node, data)
    if not introspect_only:
        decision = NO_GAP
    elif reasons:
        decision = RECORD_LEFT_OUT
    else:
        decision = ADD_FIELDS
    return {
        **base,
        "status_code": 200,
        "verdict": PASSED,
        "introspect": node,
        "introspect_only": introspect_only,
        "data_only": data_only,
        "decision": decision,
        "reasons": reasons,
        "basis": decision_basis(decision, reasons),
        "detail": "",
    }


# ===== 证据读写 =====


def _existing_document(repo: pathlib.Path) -> dict[str, Any]:
    path = repo / "registry" / EVIDENCE_RELATIVE
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


def _existing_rows(repo: pathlib.Path) -> dict[str, dict[str, Any]]:
    """既有证据里的逐条结论（**累积**用；`CRITERION_VERSION` 变更 ⇒ 视为空 = 全部重测）。"""
    document = _existing_document(repo)
    if int(document.get("criterion_version") or 0) != CRITERION_VERSION:
        return {}
    rows = document.get("endpoints")
    return rows if isinstance(rows, dict) else {}


def probe(repo: pathlib.Path, only: tuple[str, ...], chunk_size: int = CHUNK_SIZE) -> int:
    """只读自省扫描 → 证据文件（零副作用；**分块** + 块间只读健康检查；**累积**）。"""
    import httpx  # noqa: PLC0415

    base_url = os.environ.get("MIDAS_BASE_URL", "").rstrip("/")
    key_value = os.environ.get("MIDAS_MAPI_KEY", "")
    if not base_url or not key_value:
        print("❌ --probe 需要 MIDAS_BASE_URL / MIDAS_MAPI_KEY（见 scripts/load-midas-env.ps1）")
        return 1
    check_tool = _load_check_tool()
    all_rows = targets(repo)
    selected = [row for row in all_rows if not only or str(row["key"]) in only]
    endpoints = _existing_rows(repo)
    pending = [row for row in selected if str(row["key"]) not in endpoints]
    print(
        f"只读自省扫描：有 introspect 的端点 {len(all_rows)} 个"
        f"（本批目标 {len(selected)} 个；既有证据 {len(endpoints)} 行 ⇒ 待测 {len(pending)} 个）"
        f"（实例 {INSTANCE_ALIAS} / {INSTANCE_PRODUCT}）"
    )
    aborted = ""
    with httpx.Client(
        base_url=base_url, headers={"MAPI-Key": key_value}, timeout=30.0
    ) as client:
        for start in range(0, len(pending), chunk_size):
            chunk = pending[start : start + chunk_size]
            for row in chunk:
                endpoints[str(row["key"])] = probe_key(client, row, repo, check_tool)
            health = client.get(HEALTH_PATH).status_code
            print(f"  块 {start // chunk_size + 1} 完成（{len(chunk)} 条）；健康检查 → {health}")
            if health != 200:
                aborted = f"健康检查 {HEALTH_PATH} → {health}（**立即中止**，P149-B2 的教训）"
                print(f"  ⚠️ {aborted}")
                break
    counts: dict[str, int] = {}
    decisions: dict[str, int] = {}
    for row in endpoints.values():
        counts[str(row.get("verdict"))] = counts.get(str(row.get("verdict")), 0) + 1
        decisions[str(row.get("decision"))] = decisions.get(str(row.get("decision")), 0) + 1
    document = {
        "note": [
            "`schema_ref.introspect`（`GET /info/db/<CODE>`）是本 build **自己声明**的请求形状，"
            "而数据侧请求 Schema 是**手册子集**的转录 ⇒ 本证据逐端点做**递归**字段集差集。",
            "`introspect_only` = 自省**声明**而数据侧**没有**的字段路径（含「数据侧是**裸 `object`**、"
            "自省声明了子字段」时逐个子字段）；`data_only` = **反向缺口**（数据侧有、自省没有）"
            "—— 反向缺口**一律不动**、只如实记录。",
            "判据（**裁决 R117**，见工具文档）：`add_fields` = 产品可比 ∧ 待补子树是合法 JSON Schema "
            "∧ 父节点未 `additionalProperties: false`；否则 `record_left_out`（原因逐条记）。",
            "生成器 = `registry/tools/sync_introspect_fields.py --probe`（**只发 `GET`**；"
            f"**分块** ≤ {CHUNK_SIZE} + 块间只读健康检查 `{HEALTH_PATH}`；**累积**：既有行逐字节保留）；"
            "落盘 = `--write`；`--check` 断言一致。",
            "证据里**没有**凭据（MAPI-Key 只经环境变量注入）；`introspect` 是自省响应的**原文**"
            "（条目节点），使 `--write` / `--check` 可**离线**复算。",
        ],
        "criterion_version": CRITERION_VERSION,
        "instance": {
            "alias": INSTANCE_ALIAS,
            "product": INSTANCE_PRODUCT,
            "base_url": base_url,
            "probed_at": PROBED_AT,
            "scope": "schema_ref.introspect 非空（全部端点；本工具**只发 GET**）",
        },
        "counts": counts,
        "decisions": decisions,
        "aborted": aborted,
        "endpoints": dict(sorted(endpoints.items())),
    }
    (repo / "registry" / EVIDENCE_RELATIVE).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("verdict =", counts, " 裁决 =", decisions, " 中止 =", bool(aborted))
    print(f"已写入 registry/{EVIDENCE_RELATIVE}（{len(endpoints)} 行）")
    return 1 if aborted else 0


def load_evidence(repo: pathlib.Path) -> dict[str, dict[str, Any]]:
    """证据里的逐条结论（缺文件 / 版本不符 ⇒ 报错退出）。"""
    document = _existing_document(repo)
    if not document:
        raise SystemExit(f"❌ 缺证据文件 registry/{EVIDENCE_RELATIVE}（先跑 --probe）")
    if int(document.get("criterion_version") or 0) != CRITERION_VERSION:
        raise SystemExit(
            f"❌ 证据的 criterion_version = {document.get('criterion_version')!r}，"
            f"本工具为 {CRITERION_VERSION}（判据已变 ⇒ 先重跑 --probe）"
        )
    return document["endpoints"]


# ===== 落盘（**只补**自省声明的字段）=====


def _insert(item: dict[str, Any], dotted_path: str, node: Any) -> None:
    """把自省声明的节点插入条目 Schema 的该路径（**只**新增名字，**不**覆盖既有声明）。"""
    parts = dotted_path.split(".")
    current = item
    for name in parts[:-1]:
        child = _properties(current).get(name)
        if not isinstance(child, dict):  # pragma: no cover - 证据与盘面不一致时才会发生
            raise SystemExit(f"❌ 路径 {dotted_path!r} 的中段 {name!r} 在盘面上不是对象")
        if not isinstance(child.get("properties"), dict):
            child["properties"] = {}
        current = child
    properties = current.setdefault("properties", {})
    if not isinstance(properties, dict):  # pragma: no cover - 防御性
        raise SystemExit(f"❌ 路径 {dotted_path!r} 的父节点没有 properties")
    properties[parts[-1]] = node


def apply_additions(repo: pathlib.Path, key: str, row: dict[str, Any]) -> list[str]:
    """按证据把该端点的 `introspect_only` 补进 Schema 文件；返回实际补入的路径。

    ⚠️ 条目节点**必须**从**本次读盘的同一个文档**里定位（`item_schema_of(document["schema"])`）：
    若另调 `request_schema()` 再读一次盘，改动会落在**另一份副本**上、写回时被丢掉
    （P150 实测踩过这个坑）。两处的「条目形状判定」是**同一个**纯函数 ⇒ 判定点仍**唯一**。
    """
    check_tool = _load_check_tool()
    relative = str(row.get("schema") or "")
    path = repo / "registry" / relative
    document = json.loads(path.read_text(encoding="utf-8"))
    schema = document.get("schema")
    item = check_tool.item_schema_of(schema) if isinstance(schema, dict) else None
    if item is None:  # pragma: no cover - 防御性
        raise SystemExit(f"❌ {key}: 盘面上的请求 Schema 无法定位条目节点")
    intro = row.get("introspect")
    pending = plan_additions(intro, item)
    applied: list[str] = []
    for dotted, node in pending:
        _insert(item, dotted, node)
        applied.append(dotted)
    if applied:
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return applied


def write_back(repo: pathlib.Path) -> int:
    """按裁决落盘（**只**处理 `add_fields`；`record_left_out` / `no_gap` 一行未改）。"""
    endpoints = load_evidence(repo)
    total = 0
    for key, row in sorted(endpoints.items()):
        if str(row.get("decision")) != ADD_FIELDS:
            continue
        applied = apply_additions(repo, key, row)
        total += len(applied)
        if applied:
            print(f"  {key}: +{len(applied)} 字段（来源 introspect:{row['uri']}）")
            for dotted in applied:
                print(f"      + {dotted}")
        else:
            print(f"  {key}: 已一致（0 待补）")
    print(f"补 Schema 的端点 = {sum(1 for r in endpoints.values() if r.get('decision') == ADD_FIELDS)}；"
          f"逐条补入字段 = {total}")
    return 0


# ===== 校验 =====


def check(repo: pathlib.Path) -> int:
    """断言「盘面 == 证据的机械结果」（`--write` 已落盘且幂等；留缺端点未被改动）。"""
    check_tool = _load_check_tool()
    endpoints = load_evidence(repo)
    errors: list[str] = []
    counts: dict[str, int] = {}
    decisions: dict[str, int] = {}
    for key, row in sorted(endpoints.items()):
        counts[str(row.get("verdict"))] = counts.get(str(row.get("verdict")), 0) + 1
        decisions[str(row.get("decision"))] = decisions.get(str(row.get("decision")), 0) + 1
        if str(row.get("verdict")) not in {PASSED, NOT_COMPARABLE}:
            continue
        intro = row.get("introspect")
        if intro is None:
            continue
        item = check_tool.request_schema(repo, str(row.get("schema") or ""), key)
        if item is None:
            errors.append(f"{key}: 盘面上的请求 Schema 无法定位条目节点")
            continue
        pending = [dotted for dotted, _ in plan_additions(intro, item)]
        data_only = data_only_paths(intro, item)
        decision = str(row.get("decision"))
        if decision == ADD_FIELDS:
            if pending:
                errors.append(f"{key}: 裁决 = 补 Schema 但盘面仍缺 {len(pending)} 个字段（未落盘？）")
        elif decision in {RECORD_LEFT_OUT, NO_GAP}:
            recorded = [str(name) for name in (row.get("introspect_only") or [])]
            if pending != recorded:
                errors.append(
                    f"{key}: 留缺端点的盘面差集与证据不一致（证据 {len(recorded)} · 盘面 {len(pending)}）"
                )
        if data_only != [str(name) for name in (row.get("data_only") or [])]:
            errors.append(f"{key}: 反向缺口（data_only）与证据不一致 —— 反向缺口**一律不动**")
    document = _existing_document(repo)
    if document.get("counts") != counts:
        errors.append(f"证据 counts = {document.get('counts')}，复算 = {counts}")
    if document.get("decisions") != decisions:
        errors.append(f"证据 decisions = {document.get('decisions')}，复算 = {decisions}")
    if errors:
        print("❌ 与证据不一致：")
        for line in errors:
            print("  ", line)
        return 1
    print(
        f"✅ 与证据一致（{counts.get(PASSED, 0)} 个端点可比；"
        f"补 Schema {decisions.get(ADD_FIELDS, 0)} · 留缺 {decisions.get(RECORD_LEFT_OUT, 0)} · "
        f"无缺口 {decisions.get(NO_GAP, 0)}）"
    )
    return 0


def summary(repo: pathlib.Path) -> int:
    """只打印汇总（逐条差异见证据文件）。"""
    document = _existing_document(repo)
    if not document:
        print(f"（缺 registry/{EVIDENCE_RELATIVE}）")
        return 0
    print(f"criterion_version = {document.get('criterion_version')}")
    print(f"实例 = {document.get('instance')}")
    print(f"verdict = {document.get('counts')}")
    print(f"裁决 = {document.get('decisions')}")
    print(f"中止 = {document.get('aborted')!r}")
    for key, row in sorted(document["endpoints"].items()):
        if row.get("introspect_only") or row.get("data_only"):
            print(
                f"  {key}: 自省独有 {len(row.get('introspect_only') or [])} · "
                f"数据侧独有 {len(row.get('data_only') or [])} · {row.get('decision')}"
                f"{(' ' + str(row.get('reasons'))) if row.get('reasons') else ''}"
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R117：请求方向 Schema 的「覆盖不全」收口")
    parser.add_argument("--repo", default=REPO_DEFAULT)
    parser.add_argument("--probe", action="store_true", help="只读自省扫描 → 证据（零副作用）")
    parser.add_argument("--write", action="store_true", help="按裁决补 Schema（默认只预演）")
    parser.add_argument("--check", action="store_true", help="断言盘面 == 证据的机械结果（CI）")
    parser.add_argument("--summary", action="store_true", help="只打印汇总")
    parser.add_argument("--only", default="", help="只处理这些 key（逗号分隔；定位失败时用）")
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    args = parser.parse_args(argv)
    repo = pathlib.Path(args.repo).resolve()
    only = tuple(part.strip() for part in args.only.split(",") if part.strip())

    status = 0
    if args.probe:
        status = max(status, probe(repo, only, args.chunk_size))
    if args.write:
        status = max(status, write_back(repo))
    if args.check:
        status = max(status, check(repo))
    if args.summary:
        status = max(status, summary(repo))
    if not (args.probe or args.write or args.check or args.summary):
        print(__doc__)
    return status


if __name__ == "__main__":
    sys.exit(main())
