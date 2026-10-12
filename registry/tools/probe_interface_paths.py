#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P152 / P153：**接口层**（`app/` 适配层）的**写路径**（添加 / 删除 / 编辑）与
**读路径**（`MODEL.*.QUERY` / `INFO` / 取结果族）的**端到端**判据。

为什么需要这个工具
------------------
P139–P151 把**数据侧**的写路径判据做到了「创建 → 读回 → 编辑 → 读回确认 → 删除 →
读回消失」（R118 / R4 / R14），但那些判据**全部**绕开了 `app/`：模板、前置链、编号分配
都在探针里自己实现，`app/` 一行未改。用户口径（`docs/08` §4）：接口层与数据侧**解耦**，
故 P152 起开始**接口层**调试 —— 走**既有 9 个 MCP Tool 契约**：

    MCP Tool（9 个之一）→ OperationPlan（`operations.py` 的 §6 编排）
        → Adapter（`MidasAdapter.execute` 的 intent 分派）
        → MidasHttpClient（`build_request` 的护栏 + 包装键）→ MIDAS 实例

判据（**先写清楚再动手**）
--------------------------
| 取值 | 判据 |
| --- | --- |
| `PASSED` | **添加**：`POST` 经接口层 → 读回在；**编辑**：创建 → `PUT` 改动过的值 → 读回确认**改动生效**；**删除**：创建 → `DELETE` 带路径 key → 读回**确认消失**；且该行的**清理**成立（自建编号再读不在） |
| `FAILED` | 任一步不成立（闸门拒绝 / 原生 `4xx` / 读不回 / 改动未生效 / 删不掉）—— 逐条记状态码 / 错误码 / 原生短原因 |
| `LEFT_OUT` | 该端点在本 build 上**没有**对应的接口层 Operation（如无 `MODEL.GROUP.CREATE`）⇒ 如实留缺，**不**硬凑。⚠️ P152 的计划内**没有**这种行（每条路径都有对应 Operation；`DB.GRUP` 的删除路径用**原生**前置并在证据里显式标 `via = raw_precondition`）—— 该取值留给后续批次 |
| `SKIPPED` | 传输失败 / 实例不可达（`The project is not opened`）—— **不**计入结论 |

**读路径（P153，`--probe-read`）**：与写路径**同一链路**，但**零写请求** —— 只发 `GET`
与取报表 `POST /POST/TABLE`；判定沿用 **L4 口径**（`docs/04` §71）：`2xx` ∧ 解包链命中
（`read_root` 在响应顶层）⇒ 数据块非空 `PASSED` / **空块 `PARTIAL`**；`4xx` / 解包链
不命中 ⇒ `FAILED`。规范化结果的键是 **`intent`**（读 = `data["read"]`、取报表 =
`data["result"]`）—— **不是** Mock Adapter 的 `data["items"]`。

**只读侦察先行**（每条路径之前）：对目标端点发 `OPTIONS`（只读）核对 `Allow` 是否含该
Operation 声明的方法，并发 `GET` 核对解包链（`read_root`）—— 映射**必须**由实测确认，
**不**按名字臆造。

**证据里记什么**：写路径逐条 `{path, tool, operation, endpoint, method, uri, status,
own_id, preconditions, recon, write, readback, edit, cleanup, requests, detail}`；
读路径逐条 `{tool, operation, endpoint, endpoints, method, uri, status, http, intent,
recon, steps, readback, requests, detail}`。其中 `requests` 是**接口层实际发出**的请求
（method + path + 请求体 —— 请求体是**本探针自建的规范化数据**，非凭据、非响应体原文）。

映射缺口（P152 任务 2）
----------------------
「**接口层可达但适配层未映射**」= `registry/manifest.json` 里在 GEN NX 上**可写**
（`methods` 含 `POST` / `PUT` / `DELETE` / `PATCH`）∧ 已启用 ∧ 非破坏性，但**任何**
`OperationPlan` 的步骤都没引用它的端点。逐条登记进
`registry/live/interface_mapping_gap.json`（**离线可复算**），并给出留缺原因：

* `not_in_operation_contract` —— 形态齐备（有 `GET` + `read_root` ⇒ L5 三步链可表达），
  但 9 Tool 的 **69** 个 Operation **没有**一条映射到它（**契约外**）；
* `no_readback_route` —— 没有 `GET` 或没有 `read_root` ⇒ 读回不可表达。

⚠️ **判定点唯一**：Operation → 端点的编排**只**由
`app/infrastructure/adapters/midas/operations.py` 解释（本工具直接读 `OPERATION_PLANS`），
`--check` 据此**离线**复算证据的每一行（写路径 + 读路径**都**复算）。

纪律
----
* **只碰自建编号**：编号 = 该端点既有编号的 `max + 1`（专用空项目 ⇒ `1`）；
  **删除必带路径 key**（`DELETE {uri}/{id}`）。
* **跑前 / 跑后只读哨兵**：对**全部**被触碰的端点做只读 `GET`；**跑前非空 ⇒ 一个请求
  都不发**（`aborted`）；跑后非空 ⇒ 如实记 `residue`（**不**声称零残留）；
  `residue ⊄ allowed_residue` ⇒ 退出码 1。
* **分块 + 健康检查**（P149-B2 两次实例崩溃的教训）：每块 ≤ `--chunk-size`（默认 **5**）条，
  块间做**只读**健康检查 `GET /DB/NODE`；非 `200` ⇒ **立即中止**。
* **删除以「再读一次、该编号确实不在」为准**（R119：本 build 的 `DELETE` 会返回 `200`
  并回显被删记录却**不真正删除**）。
* **绝不逐端点连发原生试探**（R115 / P146 §7 的教训）：本工具**只**经接口层发请求，
  且每次 `--probe` / `--probe-read` 都是**有界**批量。
* 证据里**绝不**出现凭据；**成功**响应**不**留任何原文（读路径只留结构形态 `kind` / `size`）；
  只有**失败**请求留原生 `error.message` 的前 200 字（`native_error`，诊断必需；
  与数据侧 `probe_put_edits` 同一口径）。
* 专用项目（`docs/04` §72）：本工具在**临时库**里自建一个项目 + 模型 + GEN NX 实例绑定，
  跑完即弃；**不**碰仓库的 `data/`，也**不**写任何仓库内文件（除证据文件）。

用法（仓库根目录执行；`--probe` / `--probe-read` 需要 `MIDAS_BASE_URL` / `MIDAS_MAPI_KEY`）
----------------------------------------------------------------------------------------
    # ① 离线：映射缺口清单（**零请求**）
    python registry/tools/probe_interface_paths.py --recon

    # ② 接口层写路径端到端（有界：默认一块 ≤ 5 条 + 块间只读健康检查 + 跑前 / 跑后只读哨兵）
    python registry/tools/probe_interface_paths.py --probe
    python registry/tools/probe_interface_paths.py --probe --only DB.NODE --limit 3
    python registry/tools/probe_interface_paths.py --probe --path add --path edit

    # ③ 接口层读路径端到端（**零写请求**）
    python registry/tools/probe_interface_paths.py --probe-read
    python registry/tools/probe_interface_paths.py --probe-read --only MODEL.NODE.QUERY

    # ④ 离线复算（CI 用）
    python registry/tools/probe_interface_paths.py --check
    python registry/tools/probe_interface_paths.py --summary
    python registry/tools/probe_interface_paths.py --read-summary
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
import tempfile
from collections.abc import Mapping, Sequence
from typing import Any

REPO_DEFAULT = "."
EVIDENCE_RELATIVE = "live/interface_path_probe.json"
"""接口层端到端证据（**不含**凭据、**不含**响应体原文）。"""

GAP_RELATIVE = "live/interface_mapping_gap.json"
"""映射缺口清单（**离线可复算**：registry ∪ `operations.py`）。"""

MANIFEST_FILENAME = "manifest.json"

INSTANCE_ALIAS = "gen-local"
INSTANCE_PRODUCT = "GEN NX"
PRODUCT_KEY = "GEN_NX"
INSTANCE_VERSION = "2026"
PROBED_AT = "2026-10-11"
CRITERION_VERSION = 1

CHUNK_SIZE = 5
"""每块路径条数上限（**≤ 20** 的纪律；每条路径要发 4–6 次请求，故取 5）。"""

HEALTH_PATH = "/DB/NODE"
"""块间**只读**健康检查路径；非 `200` ⇒ **立即中止**。"""

INSTANCE_DOWN_MARKER = "The project is not opened"
"""实例崩溃后重启会**关闭项目** —— 该形态归 `SKIPPED`（**不**冒充端点被拒）。"""

ADMIN_PASSWORD_ENV = "STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD"
SEED_PASSWORD = "P152-接口层-调试-口令-7c31"
"""临时库的引导管理员口令（**只**在进程内环境注入，绝不落任何文件）。"""

PASSED = "PASSED"
FAILED = "FAILED"
LEFT_OUT = "LEFT_OUT"
SKIPPED = "SKIPPED"

PATH_ADD = "add"
PATH_EDIT = "edit"
PATH_DELETE = "delete"
PATH_LABELS = {PATH_ADD: "添加", PATH_EDIT: "编辑", PATH_DELETE: "删除"}

WRITE_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})
REASON_NOT_IN_CONTRACT = "not_in_operation_contract"
REASON_NO_READBACK = "no_readback_route"

CREATE_OPERATION_BY_ENDPOINT: dict[str, str] = {
    "DB.NODE": "MODEL.NODE.CREATE",
    "DB.ELEM": "MODEL.ELEMENT.CREATE",
    "DB.MATL": "MODEL.MATERIAL.ASSIGN",
    "DB.SECT": "MODEL.SECTION.ASSIGN",
    "DB.CONS": "MODEL.BOUNDARY.ASSIGN",
}
"""端点 → **创建**类 Operation（`docs/07` §6.3；`DB.GRUP` **没有**创建类 Operation）。"""

DELETE_OPERATION_BY_ENDPOINT: dict[str, str] = {
    "DB.NODE": "MODEL.NODE.DELETE",
    "DB.ELEM": "MODEL.ELEMENT.DELETE",
    "DB.MATL": "MODEL.MATERIAL.DELETE",
    "DB.SECT": "MODEL.SECTION.DELETE",
    "DB.CONS": "MODEL.BOUNDARY.DELETE",
    "DB.GRUP": "MODEL.GROUP.DELETE",
}
"""端点 → **删除**类 Operation（`docs/07` §6.4）。"""


# ===== 被调试的三条路径（**声明**；判定点仍是 `operations.py`）=====

EXERCISES: tuple[dict[str, Any], ...] = (
    # ---- 添加（`engineering_model_assign` 的 *CREATE / ASSIGN）----
    {
        "path": PATH_ADD,
        "endpoint": "DB.NODE",
        "operation": "MODEL.NODE.CREATE",
        "query": "MODEL.NODE.QUERY",
        "preconditions": (),
    },
    {
        "path": PATH_ADD,
        "endpoint": "DB.ELEM",
        "operation": "MODEL.ELEMENT.CREATE",
        "query": "MODEL.ELEMENT.QUERY",
        "preconditions": ("node", "node", "material", "section"),
    },
    {
        "path": PATH_ADD,
        "endpoint": "DB.MATL",
        "operation": "MODEL.MATERIAL.ASSIGN",
        "query": "MODEL.MATERIAL.QUERY",
        "preconditions": (),
    },
    {
        "path": PATH_ADD,
        "endpoint": "DB.SECT",
        "operation": "MODEL.SECTION.ASSIGN",
        "query": "MODEL.SECTION.QUERY",
        "preconditions": (),
    },
    {
        "path": PATH_ADD,
        "endpoint": "DB.CONS",
        "operation": "MODEL.BOUNDARY.ASSIGN",
        "query": "MODEL.BOUNDARY.QUERY",
        "preconditions": ("node",),
        "id_policy": "precondition_node",
    },
    # ---- 编辑（`engineering_model_assign` 的 *UPDATE ⇒ PUT）----
    {
        "path": PATH_EDIT,
        "endpoint": "DB.NODE",
        "operation": "MODEL.NODE.UPDATE",
        "query": "MODEL.NODE.QUERY",
        "preconditions": (),
    },
    {
        "path": PATH_EDIT,
        "endpoint": "DB.ELEM",
        "operation": "MODEL.ELEMENT.UPDATE",
        "query": "MODEL.ELEMENT.QUERY",
        "preconditions": ("node", "node", "material", "section"),
    },
    # ---- 删除（`engineering_model_delete` ⇒ `DELETE {uri}/{id}`）----
    {
        "path": PATH_DELETE,
        "endpoint": "DB.NODE",
        "operation": "MODEL.NODE.DELETE",
        "query": "MODEL.NODE.QUERY",
        "preconditions": (),
    },
    {
        "path": PATH_DELETE,
        "endpoint": "DB.ELEM",
        "operation": "MODEL.ELEMENT.DELETE",
        "query": "MODEL.ELEMENT.QUERY",
        "preconditions": ("node", "node", "material", "section"),
    },
    {
        "path": PATH_DELETE,
        "endpoint": "DB.MATL",
        "operation": "MODEL.MATERIAL.DELETE",
        "query": "MODEL.MATERIAL.QUERY",
        "preconditions": (),
    },
    {
        "path": PATH_DELETE,
        "endpoint": "DB.SECT",
        "operation": "MODEL.SECTION.DELETE",
        "query": "MODEL.SECTION.QUERY",
        "preconditions": (),
    },
    {
        "path": PATH_DELETE,
        "endpoint": "DB.CONS",
        "operation": "MODEL.BOUNDARY.DELETE",
        "query": "MODEL.BOUNDARY.QUERY",
        "preconditions": ("node",),
        "id_policy": "precondition_node",
    },
    {
        "path": PATH_DELETE,
        "endpoint": "DB.GRUP",
        "operation": "MODEL.GROUP.DELETE",
        "query": "MODEL.GROUP.QUERY",
        "preconditions": (),
        "precondition_raw": "group",
    },
)

TOOL_BY_OPERATION_PATH: dict[str, str] = {
    PATH_ADD: "engineering_model_assign",
    PATH_EDIT: "engineering_model_assign",
    PATH_DELETE: "engineering_model_delete",
}
"""三条路径的 Tool（`docs/07` §5.1；**声明**，`--check` 会与 `operations.py` 复算比对）。"""


# ===== P153：接口层**读路径**（零写请求）=====

READ_EVIDENCE_RELATIVE = "live/interface_read_probe.json"
"""接口层读路径证据（**零写请求**；**不含**凭据、**不含**响应原文，只留结构形态）。"""

READ_CRITERION_VERSION = 1

PARTIAL = "PARTIAL"
"""L4 口径的第三态：`200` ∧ 解包链命中，但**数据块为空**（`docs/04` §71）。"""

READ_EXERCISES: tuple[dict[str, Any], ...] = (
    # ---- `engineering_model_query`（8 个 `MODEL.*.QUERY`；`docs/07` §6.2）----
    {"tool": "engineering_model_query", "operation": "MODEL.QUERY"},
    {"tool": "engineering_model_query", "operation": "MODEL.NODE.QUERY"},
    {"tool": "engineering_model_query", "operation": "MODEL.ELEMENT.QUERY"},
    {"tool": "engineering_model_query", "operation": "MODEL.MATERIAL.QUERY"},
    {"tool": "engineering_model_query", "operation": "MODEL.SECTION.QUERY"},
    {"tool": "engineering_model_query", "operation": "MODEL.BOUNDARY.QUERY"},
    {"tool": "engineering_model_query", "operation": "MODEL.LOAD.QUERY"},
    {"tool": "engineering_model_query", "operation": "MODEL.GROUP.QUERY"},
    # ---- `engineering_doc` 的 `INFO`（`docs/07` §6.1：无 `/doc/INFO`，用项目状态代替）----
    {"tool": "engineering_doc", "operation": "INFO"},
    # ---- `engineering_result` 取结果族（6；`docs/07` §6.7）----
    {"tool": "engineering_result", "operation": "RESULT.NODE.DISPLACEMENT"},
    {"tool": "engineering_result", "operation": "RESULT.NODE.REACTION"},
    {"tool": "engineering_result", "operation": "RESULT.ELEMENT.FORCE"},
    {"tool": "engineering_result", "operation": "RESULT.ELEMENT.STRESS"},
    {"tool": "engineering_result", "operation": "RESULT.MODE.SHAPE"},
    {"tool": "engineering_result", "operation": "RESULT.ANALYSIS.SUMMARY"},
)
"""读类 Operation（**声明**；端点一律由 `operations.py` 的编排**推导**，不在这里写死）。

⚠️ 端点集**不**声明：`--check` 用 `steps_of(plan)` 复算 ⇒ 判定点仍**唯一**在
`app/infrastructure/adapters/midas/operations.py`。
"""

READ_METHODS = frozenset({"GET", "POST"})
"""读路径**允许**发出的方法（`GET` + 取报表的 `POST`；`docs/08` §4 纪律 3）。"""

WRITE_REQUEST_METHODS = frozenset({"PUT", "DELETE", "PATCH"})
"""读路径**绝不**发出的方法（`--probe-read` 跑完逐条断言 = 0）。"""

TABLE_URI = "/POST/TABLE"
"""`POST` 只允许打到这里（`POST.TABLE*` 的取报表；**不**落文件、**不**改模型）。"""


def _load_app(repo: pathlib.Path) -> None:
    """把仓库根放进 `sys.path`（`registry/tools` 不是包）。"""
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))


# ===== 离线：映射与缺口（判定点 = `operations.py`）=====


def operation_plans(repo: pathlib.Path) -> dict[str, Any]:
    """全部 `OperationPlan`（**唯一**判定点：`app/.../operations.py`）。"""
    _load_app(repo)
    from app.infrastructure.adapters.midas.operations import (  # noqa: PLC0415
        OPERATION_PLANS,
    )

    return dict(OPERATION_PLANS)


def steps_of(plan: Any) -> tuple[Any, ...]:
    """一个 Operation 的**全部**步骤（含 `routes` 的每一条路由；判定点不重写）。"""
    steps = list(plan.steps)
    for route in sorted(plan.routes):
        steps.extend(plan.routes[route])
    return tuple(steps)


def mapped_endpoints(repo: pathlib.Path) -> dict[str, list[dict[str, str]]]:
    """端点 key → 引用它的 `(operation, tool, method, intent)` 列表（升序、确定性）。"""
    rows: dict[str, list[dict[str, str]]] = {}
    for name, plan in sorted(operation_plans(repo).items()):
        for step in steps_of(plan):
            rows.setdefault(str(step.key), []).append(
                {
                    "operation": name,
                    "tool": str(plan.tool),
                    "method": str(step.method),
                    "intent": str(step.intent),
                }
            )
    return rows


def _methods(value: Any) -> set[str]:
    """`methods` 字段（`"POST, GET"` 或列表）→ 大写集合。"""
    if isinstance(value, Sequence) and not isinstance(value, str):
        return {str(item).strip().upper() for item in value if str(item).strip()}
    return {part.strip().upper() for part in str(value or "").split(",") if part.strip()}


def manifest_endpoints(repo: pathlib.Path) -> list[dict[str, Any]]:
    """`registry/manifest.json` 的端点条目（原样；**不**改写数据）。"""
    document = json.loads((repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    return list(document["endpoints"])


def manifest_index(repo: pathlib.Path) -> dict[str, dict[str, Any]]:
    """端点 key → manifest 条目（供逐行复算）。"""
    return {str(entry["key"]): entry for entry in manifest_endpoints(repo)}


def _row_of(entry: Mapping[str, Any]) -> dict[str, Any]:
    """缺口行（只含**非敏感**的结构字段）。"""
    return {
        "key": str(entry["key"]),
        "uri": "/" + str(entry.get("uri") or "").lstrip("/"),
        "methods": ",".join(sorted(_methods(entry.get("methods")))),
        "read_root": str((entry.get("wrapper") or {}).get("read_root") or ""),
        "availability": str(entry.get("availability") or ""),
    }


def write_capable_endpoints(repo: pathlib.Path) -> list[dict[str, Any]]:
    """接口层**可达**（GEN NX 上可写）的端点全集：已启用 ∧ 非破坏性 ∧ 有写方法。"""
    rows: list[dict[str, Any]] = []
    for entry in manifest_endpoints(repo):
        if not bool(entry.get("enabled", True)):
            continue
        if bool((entry.get("risk") or {}).get("destructive")):
            continue
        if PRODUCT_KEY not in [str(name) for name in (entry.get("products") or [])]:
            continue
        if not (_methods(entry.get("methods")) & WRITE_METHODS):
            continue
        rows.append(entry)
    return sorted(rows, key=lambda item: str(item["key"]))


def three_step_endpoints(repo: pathlib.Path) -> list[dict[str, Any]]:
    """形态**齐备**的子集（有 `GET` + `read_root` ⇒ 读回可表达）。"""
    return [
        entry
        for entry in write_capable_endpoints(repo)
        if "GET" in _methods(entry.get("methods"))
        and str((entry.get("wrapper") or {}).get("read_root") or "")
    ]


def mapping_gap(repo: pathlib.Path) -> dict[str, Any]:
    """「接口层可达但适配层未映射」的**逐条**清单（离线可复算）。"""
    mapped = mapped_endpoints(repo)
    write_capable = write_capable_endpoints(repo)
    three_step = {str(entry["key"]) for entry in three_step_endpoints(repo)}
    gap: list[dict[str, Any]] = []
    for entry in write_capable:
        key = str(entry["key"])
        if key in mapped:
            continue
        row = _row_of(entry)
        row["reason"] = REASON_NOT_IN_CONTRACT if key in three_step else REASON_NO_READBACK
        gap.append(row)
    return {
        "operations": len(operation_plans(repo)),
        "mapped_endpoints": len(mapped),
        "write_capable_endpoints": len(write_capable),
        "three_step_endpoints": len(three_step),
        "mapped_inside_three_step": len([key for key in mapped if key in three_step]),
        "gap_total": len(gap),
        "gap_three_step": [row for row in gap if row["reason"] == REASON_NOT_IN_CONTRACT],
        "gap_no_readback": [row for row in gap if row["reason"] == REASON_NO_READBACK],
        "mapped": {key: mapped[key] for key in sorted(mapped)},
    }


def recon(repo: pathlib.Path) -> int:
    """写映射缺口清单（**零请求**）。"""
    fresh = mapping_gap(repo)
    document = {
        "note": [
            "「接口层可达但适配层未映射」= `registry/manifest.json` 里在 GEN NX 上**可写**"
            "（`methods` 含 POST/PUT/DELETE/PATCH）∧ 已启用 ∧ 非破坏性，但**任何** "
            "`OperationPlan` 的步骤都没引用它的端点。",
            "判定点**唯一**：Operation → 端点的编排**只**由 "
            "`app/infrastructure/adapters/midas/operations.py` 的 `OPERATION_PLANS` 解释"
            "（本工具直接读它，**不**另写一份映射规则）。",
            f"`reason = {REASON_NOT_IN_CONTRACT}`：形态齐备（有 GET + read_root ⇒ L5 三步链"
            "可表达）但**契约外**；"
            f"`reason = {REASON_NO_READBACK}`：没有 GET 或没有 read_root ⇒ 读回不可表达。",
            "本清单**零请求**、**不改**任何数据侧文件；生成器 = "
            "`registry/tools/probe_interface_paths.py --recon`。",
        ],
        "criterion_version": CRITERION_VERSION,
        "instance": {"alias": INSTANCE_ALIAS, "product": INSTANCE_PRODUCT, "probed_at": PROBED_AT},
        "product_key": PRODUCT_KEY,
        **fresh,
    }
    path = repo / "registry" / GAP_RELATIVE
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"映射缺口：可写端点 {fresh['write_capable_endpoints']} · "
        f"形态齐备 {fresh['three_step_endpoints']} · 已映射 {fresh['mapped_endpoints']} · "
        f"缺口 {fresh['gap_total']}"
        f"（契约外 {len(fresh['gap_three_step'])} / 无读回 {len(fresh['gap_no_readback'])}）"
    )
    print(f"已写入 registry/{GAP_RELATIVE}")
    return 0


# ===== 规范化参数（**由接口层契约给出**；不臆造字段）=====


def _node_parameters(own_id: str, *, x: float, y: float = 2.0, z: float = 3.0) -> dict[str, Any]:
    """`MODEL.NODE.CREATE` / `UPDATE` 的规范化参数（`NodeTransformer` 的 canonical 键）。"""
    return {"nodes": [{"id": own_id, "x": x, "y": y, "z": z}]}


def _element_parameters(
    own_id: str,
    *,
    nodes: Sequence[str],
    materials: Sequence[str] = (),
    sections: Sequence[str] = (),
    angle: float | None = None,
) -> dict[str, Any]:
    """`MODEL.ELEMENT.CREATE` / `UPDATE` 的规范化参数（`ElementTransformer` 的 canonical 键）。

    ⚠️ `material_id` / `section_id` **必须**引用**本批自建**的材质 / 截面编号
    （P152 的 `FAILED` 就是空项目上没有可引用的编号 ⇒ 见 R126 的连带面）。
    """
    item: dict[str, Any] = {
        "id": own_id,
        "type": "BEAM",
        "node_ids": [int(nodes[0]), int(nodes[1])],
    }
    if materials:
        item["material_id"] = int(materials[0])
    if sections:
        item["section_id"] = int(sections[0])
    if angle is not None:
        item["angle"] = angle
    return {"elements": [item]}


def _material_parameters(own_id: str) -> dict[str, Any]:
    """`MODEL.MATERIAL.ASSIGN` 的规范化参数（`MaterialTransformer` 的 canonical 键）。

    ⚠️ **P154 裁决 A′**：除原有的 5 个字段外，另给出 R126 新纳入的 **11** 个原生字段的取值 ——
    取值逐条取自**数据侧手册示例**（`registry/live/write_templates.json` 的 `DB.MATL.body`，
    已被 `check_write_templates` 复算），**不**在 `app/**` 里给默认值（`transforms.py` §21 / §26）。
    """
    return {
        "materials": [
            {
                "id": own_id,
                "name": f"P154M{own_id}",
                "type": "STEEL",
                "elastic_modulus": 2.1e11,
                "poisson_ratio": 0.3,
                "density": 7850.0,
                # ---- R126 / P154 A′（11 个字段；取值来源 = 手册示例）----
                "he_spec": 0,
                "he_cond": 0,
                "plmt": 0,
                "p_name": "",
                "bmass_dens": False,
                "damp_rat": 0.02,
                "p_type": 1,
                "standard": "EN05(S)",
                "code": "",
                "db": "S450",
                "belast": False,
            }
        ]
    }


def _section_parameters(own_id: str) -> dict[str, Any]:
    """`MODEL.SECTION.ASSIGN` 的规范化参数（`SectionTransformer` 的 canonical 键）。

    ⚠️ **P154 裁决 A′**：另给出 R126 新纳入的 **6** 个 `SECT_BEFORE.*` 字段（取值来源同
    `_material_parameters` 的说明）。
    """
    return {
        "sections": [
            {
                "id": own_id,
                "name": f"P154S{own_id}",
                "section_type": "DBUSER",
                # ---- R126 / P154 A′（6 个字段；取值来源 = 手册示例）----
                "shape": "SB",
                "offset_point": "LT",
                "datatype": 2,
                "horz_offset_opt": 0,
                "vert_offset_opt": 0,
                "use_shear_deform": False,
                "use_warping_effect": False,
                "vsize": [1, 1],
            }
        ]
    }


def _boundary_parameters(own_id: str, *, nodes: Sequence[str]) -> dict[str, Any]:
    """`MODEL.BOUNDARY.ASSIGN` 的规范化参数（canonical 键 + 六自由度；`docs/04` §31）。

    ⚠️ **P154 / N1**：`group_name` 在 canonical 字段表里**一直存在**
    （`BoundaryTransformer` 的 `FieldMap("group_name", "GROUP_NAME")`），P152 的探针**没传**它 ⇒
    手册示例用的是**空串**（「不分组」，P139 实测：非空组名会 `400 Unknown Error`）。这里补上。
    """
    return {
        "boundaries": [
            {
                "id": own_id,
                "node_id": int(nodes[0]),
                "group_name": "",
                "ux": True,
                "uy": True,
                "uz": True,
                "rx": False,
                "ry": False,
                "rz": False,
            }
        ]
    }


PRECONDITION_KINDS: dict[str, tuple[str, str]] = {
    "node": ("DB.NODE", "MODEL.NODE.CREATE"),
    "material": ("DB.MATL", "MODEL.MATERIAL.ASSIGN"),
    "section": ("DB.SECT", "MODEL.SECTION.ASSIGN"),
}
"""前置对象的种类 → `(端点 key, 创建类 Operation)`（`docs/07` §6.3）。"""


def _precondition_parameters(kind: str, own_id: str, *, index: int = 0) -> dict[str, Any]:
    """前置对象的规范化参数（按种类分派；未知种类 → 空，由调用方如实记缺口）。

    ⚠️ **P154 实测**：`DB.ELEM` 的两个节点**必须坐标不同** —— 同一坐标 ⇒ 零长度单元 ⇒
    原生 `400`「不能添加/编辑单元。单元 1 的几何形状不正确。」（**不是**契约缺口）。
    这里让第 `index` 个节点沿 `-Z` 逐级下移（`0` / `-6` …），即 `docs/07` §13.5 的竖向构件。
    """
    if kind == "node":
        return _node_parameters(own_id, x=0.0, y=0.0, z=-6.0 * index)
    if kind == "material":
        return _material_parameters(own_id)
    if kind == "section":
        return _section_parameters(own_id)
    return {}


def _parameters_for(
    endpoint: str,
    own_id: str,
    *,
    nodes: Sequence[str],
    materials: Sequence[str] = (),
    sections: Sequence[str] = (),
    edited: bool,
) -> dict[str, Any]:
    """该端点的规范化参数（`edited=True` ⇒ 编辑步骤的**改动过的值**）。"""
    if endpoint == "DB.NODE":
        return _node_parameters(own_id, x=2.0 if edited else 1.0)
    if endpoint == "DB.ELEM":
        return _element_parameters(
            own_id, nodes=nodes, materials=materials, sections=sections, angle=1.0 if edited else None
        )
    if endpoint == "DB.MATL":
        return _material_parameters(own_id)
    if endpoint == "DB.SECT":
        return _section_parameters(own_id)
    if endpoint == "DB.CONS":
        return _boundary_parameters(own_id, nodes=nodes)
    return {}


def _expected_value(endpoint: str) -> tuple[str, Any]:
    """读回要比对的 `(canonical 字段, 改动后的期望值)`（编辑生效的**唯一**判定）。"""
    if endpoint == "DB.NODE":
        return "x", 2.0
    if endpoint == "DB.ELEM":
        return "angle", 1.0
    return "", None


# ===== 证据读写 =====


def _read_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


def _write_json(path: pathlib.Path, document: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_evidence(path: pathlib.Path, document: Mapping[str, Any], aborted: str) -> bool:
    """落证据；⚠️ **中止**时**不**覆盖既有证据（**P155 加固**）。

    P154 的 `--probe` 在实例不可达时：5 条行全失败 → 块间健康检查**抛异常** → 进程崩溃
    ⇒ **证据文件没写成**（而此前已把好证据删掉）⇒ **上一份有效证据被冲掉**。
    这里改为：`aborted` 非空且**已有**证据 ⇒ **保留**既有证据、只打印原因（退出码仍为 1）。

    Returns:
        `True` = 已写入；`False` = 因中止而保留既有证据。
    """
    if aborted and path.is_file():
        print(
            f"⚠️ 本次中止（{aborted[:80]}）⇒ **不覆盖**既有证据 registry/"
            f"{path.relative_to(path.parents[1])}（保留上一份有效证据）"
        )
        return False
    _write_json(path, document)
    return True


def load_evidence(repo: pathlib.Path) -> dict[str, Any]:
    """接口层端到端证据（缺失 / 版本不符 → 明确退出）。"""
    document = _read_json(repo / "registry" / EVIDENCE_RELATIVE)
    if not document:
        raise SystemExit(f"❌ 缺证据文件 registry/{EVIDENCE_RELATIVE}（先跑 --probe）")
    if int(document.get("criterion_version") or 0) != CRITERION_VERSION:
        raise SystemExit(
            f"❌ 证据的 criterion_version = {document.get('criterion_version')!r}，"
            f"本工具为 {CRITERION_VERSION}（判据已变 ⇒ 先重跑 --probe）"
        )
    return document


# ===== 实时：接口层端到端 =====


class _RecordingTransport:
    """记录**接口层实际发出**的请求，并转发给真实网络（`httpx.AsyncBaseTransport`）。

    ⚠️ 只记录 `method` / `path` / 状态码 / **请求体**（请求体是本探针自建的规范化数据，
    非凭据、非响应原文）；**绝不**记录请求头（`MAPI-Key` 在里面）。

    `capture_shape = True`（**只**读路径开启）时，**成功**响应额外记一份**结构形态**
    `shape`（每个顶层键的 `kind` / `size`）—— 这是应用 L4 判据「`200` ∧ 解包链命中；
    空块 ⇒ `PARTIAL`」**必需**的最小元数据（`{}` 与 `{"1": {...}}` 必须能区分），
    **不含**任何取值 / 原文。
    """

    def __init__(self, inner: Any, *, capture_shape: bool = False) -> None:
        self._inner = inner
        self.capture_shape = capture_shape
        self.calls: list[dict[str, Any]] = []

    async def handle_async_request(self, request: Any) -> Any:
        record: dict[str, Any] = {"method": str(request.method), "path": str(request.url.path)}
        body = request.content
        if body:
            try:
                record["body"] = json.loads(body)
            except (ValueError, TypeError):
                record["body"] = "<unparsed>"
        response = await self._inner.handle_async_request(request)
        status = int(response.status_code)
        record["status"] = status
        if status >= 400:
            # 失败时**只**留原生 `error.message` 的前 200 字（诊断必需；与数据侧
            # `probe_put_edits` 的口径一致）；成功响应**不**留任何原文。
            try:
                await response.aread()
                record["native_error"] = response.text[:200]
            except Exception:  # noqa: BLE001 - 读不回就如实留空
                record["native_error"] = ""
        elif self.capture_shape:
            try:
                await response.aread()
                record["shape"] = _shape_of(response.json())
            except Exception:  # noqa: BLE001 - 形态取不到就如实留空
                record["shape"] = {}
        self.calls.append(record)
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()


def _shape_of(payload: Any) -> dict[str, Any]:
    """响应的**结构形态**（每个顶层键的 `kind` / `size`）——**不含**任何取值。

    L4 判据要区分「解包链命中但块为空」（`PARTIAL`）与「块非空」（`PASSED`），
    故必须知道 `{<read_root>: {}}` 与 `{<read_root>: {"1": {...}}}` 的差别；
    这里只记 `kind` 与 `size`，**不**记键名以外的任何内容（编号键**不**进证据）。
    """
    if not isinstance(payload, Mapping):
        return {}
    shape: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, Mapping):
            shape[str(key)] = {"kind": "mapping", "size": len(value)}
        elif isinstance(value, Sequence) and not isinstance(value, str):
            shape[str(key)] = {"kind": "list", "size": len(value)}
        else:
            shape[str(key)] = {"kind": "scalar", "size": None}
    return shape


class _Stack:
    """一次接口层探针的**进程内装配**（临时库 + GEN NX 实例绑定 + MCP Server）。"""

    def __init__(self, repo: pathlib.Path, workdir: pathlib.Path, *, read_mode: bool = False) -> None:
        self.repo = repo
        self.workdir = workdir
        self.read_mode = read_mode
        """`True` ⇒ **读路径**探针（零写请求；成功响应记结构形态 `shape`）。"""
        self.transport: _RecordingTransport | None = None
        self.log: list[dict[str, Any]] = []
        """自上次 `clear()` 以来**接口层实际发出**的全部请求（供逐行证据）。"""
        self.runtime: Any = None
        self.factory: Any = None
        self.engine: Any = None
        self.server: Any = None
        self.bundle: Any = None
        self.uow: Any = None
        self.session: Any = None
        self.ids: dict[str, str] = {}
        self.instance_id = ""
        self.tenant_id = ""
        self.user_id = ""
        self.resolved: Any = None
        self.client: Any = None
        self.registry: Any = None

    # ---- 装配 ----

    async def __aenter__(self) -> _Stack:
        import httpx  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        from app.config.settings import Settings  # noqa: PLC0415
        from app.container import build_execution_runtime  # noqa: PLC0415
        from app.infrastructure.adapters.midas import install  # noqa: PLC0415
        from app.infrastructure.adapters.midas.adapter import MidasAdapter  # noqa: PLC0415
        from app.infrastructure.adapters.midas.manifest import (  # noqa: PLC0415
            MIDAS_PRODUCT,
            MIDAS_VENDOR,
        )
        from app.infrastructure.adapters.midas.registry import MidasRegistry  # noqa: PLC0415
        from app.infrastructure.database.base import Base  # noqa: PLC0415
        from app.infrastructure.database.models.model import ModelORM  # noqa: PLC0415
        from app.infrastructure.database.models.project import ProjectORM  # noqa: PLC0415
        from app.infrastructure.database.models.software import (  # noqa: PLC0415
            SoftwareInstanceORM,
            SoftwareProductORM,
            SoftwareORM,
            SoftwareVersionORM,
        )
        from app.infrastructure.database.models.tenant import TenantORM  # noqa: PLC0415
        from app.infrastructure.database.models.user import UserORM  # noqa: PLC0415
        from app.infrastructure.database.seed import seed  # noqa: PLC0415
        from app.infrastructure.database.session import (  # noqa: PLC0415
            create_engine,
            create_session_factory,
        )
        from app.infrastructure.database.unit_of_work import UnitOfWork  # noqa: PLC0415
        from app.infrastructure.registry.capability_registry import (  # noqa: PLC0415
            CapabilityRegistry,
        )
        from app.infrastructure.registry.operation_registry import (  # noqa: PLC0415
            OperationRegistry,
        )
        from app.infrastructure.registry.schema_registry import (  # noqa: PLC0415
            SchemaRegistry,
        )
        from app.interfaces.mcp.server import build_mcp_server  # noqa: PLC0415

        os.environ[ADMIN_PASSWORD_ENV] = SEED_PASSWORD
        settings = Settings(
            database_url=f"sqlite+aiosqlite:///{(self.workdir / 'p152.db').as_posix()}",
            artifact_root=str(self.workdir / "artifacts"),
            registry_root=str(self.repo / "registry"),
        )
        engine = create_engine(settings.database_url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = create_session_factory(engine)
        await seed(factory)
        self.factory = factory
        self.engine = engine

        runtime = build_execution_runtime(
            settings,
            operation_registry=await OperationRegistry.load(engine, factory),
            capability_registry=await CapabilityRegistry.load(engine, factory),
            schema_registry=SchemaRegistry.load(self.repo / "registry"),
        )
        runtime.session_factory = factory
        self.runtime = runtime
        self.registry = MidasRegistry.load(self.repo / "registry")

        # ---- 专用实例：MIDAS / GEN NX（**只**在本临时库里登记）----
        self.transport = _RecordingTransport(
            httpx.AsyncHTTPTransport(), capture_shape=self.read_mode
        )
        install(
            runtime.adapters,
            factory=lambda: MidasAdapter(
                transport=self.transport,
                environ=dict(os.environ),
                product=INSTANCE_PRODUCT,
            ),
        )
        async with UnitOfWork.from_session_factory(factory) as uow:
            software = SoftwareORM(vendor=MIDAS_VENDOR, name="P152 MIDAS", status="CONNECTED")
            uow.session.add(software)
            await uow.session.flush()
            product = SoftwareProductORM(software_id=str(software.id), product=INSTANCE_PRODUCT)
            uow.session.add(product)
            await uow.session.flush()
            version = SoftwareVersionORM(product_id=str(product.id), version=INSTANCE_VERSION)
            uow.session.add(version)
            await uow.session.flush()
            instance = SoftwareInstanceORM(
                version_id=str(version.id),
                name="P152 GEN NX",
                endpoint=str(os.environ.get("MIDAS_BASE_URL") or ""),
                status="CONNECTED",
                credential_reference="MIDAS_MAPI_KEY",
            )
            uow.session.add(instance)
            await uow.session.flush()
            self.instance_id = str(instance.id)
            project = (await uow.session.execute(select(ProjectORM))).scalars().first()
            if project is None:
                raise SystemExit("❌ Seed 未落库任何项目（装配失败）")
            model = ModelORM(
                project_id=str(project.id),
                software_instance_id=self.instance_id,
                name="P152 接口层专用模型",
            )
            uow.session.add(model)
            await uow.session.flush()
            self.ids = {"project_id": str(project.id), "model_id": str(model.id)}

        runtime.adapters.bind_instance(
            self.instance_id,
            vendor=MIDAS_VENDOR,
            product=MIDAS_PRODUCT,
            config={
                "product": INSTANCE_PRODUCT,
                "version": INSTANCE_VERSION,
                "base_url": str(os.environ.get("MIDAS_BASE_URL") or ""),
            },
        )
        await runtime.adapters.connect(self.instance_id)

        # ---- 身份 / 客户端上下文 / MCP Server ----
        self.uow = UnitOfWork.from_session_factory(factory)
        await self.uow.__aenter__()
        self.session = self.uow.session
        self.bundle = runtime.execution.create(self.session)
        self.server = build_mcp_server(self.bundle.service)
        async with factory() as session:
            self.tenant_id = str((await session.execute(select(TenantORM))).scalars().first().id)
            self.user_id = str((await session.execute(select(UserORM))).scalars().first().id)
        self.resolved = await self.bundle.resolver.resolve(
            self.server.contexts.create(self.identity(), client_context=self.client_context()).execution
        )
        self.client = httpx.Client(
            base_url=str(os.environ["MIDAS_BASE_URL"]).rstrip("/"),
            headers={"MAPI-Key": str(os.environ["MIDAS_MAPI_KEY"])},
            timeout=60.0,
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self.client is not None:
            self.client.close()
        if self.uow is not None:
            await self.uow.__aexit__(None, None, None)
        if self.runtime is not None:
            try:
                await self.runtime.adapters.disconnect_all()
            except Exception:  # noqa: BLE001 - 收尾失败不影响判定
                pass
        if self.engine is not None:
            await self.engine.dispose()

    # ---- 身份 / 上下文 ----

    def identity(self) -> Any:
        """**服务端**身份（种子管理员；客户端不可声明）。"""
        from uuid import UUID  # noqa: PLC0415

        from app.application.security.context import IdentityContext  # noqa: PLC0415

        return IdentityContext(
            user_id=UUID(self.user_id),
            tenant_id=UUID(self.tenant_id),
            roles=("system_admin",),
            authentication_method="PASSWORD",
        )

    def client_context(self) -> dict[str, Any]:
        """客户端**允许**提供的资源标识（`docs/02` §69）。"""
        return {
            "project_id": self.ids["project_id"],
            "software_instance_id": self.instance_id,
            "model_id": self.ids["model_id"],
        }

    # ---- 接口层调用 ----

    async def call(
        self,
        tool: str,
        operation: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """经 MCP 层调用一次；HIGH / CRITICAL 操作现签确认令牌（`docs/07` §8.4）。"""
        arguments: dict[str, Any] = {
            "operation": operation,
            "parameters": dict(parameters or {}),
            "context": self.client_context(),
        }
        if confirm:
            arguments["confirmation_token"] = self.runtime.confirmation.issue(
                user_id=self.user_id,
                tenant_id=self.tenant_id,
                operation=operation,
                resource_id=None if self.resolved is None else self.resolved.resource_id,
            ).token
        response = await self.server.handle(tool, arguments, identity=self.identity())
        return dict(response.to_dict())

    async def complete(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """把 ASYNC 首次响应里的任务跑完（`docs/02` §88 的同一执行链）。"""
        execution = payload.get("execution") or {}
        task_id = execution.get("task_id")
        if not isinstance(task_id, str):
            return {}
        record = await self.bundle.engine.run_task(task_id)
        if record.result_json is None:
            return {}
        return dict(json.loads(record.result_json))

    async def run_operation(
        self,
        tool: str,
        operation: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """一次完整调用：分发 → （ASYNC）跑完任务 ⇒ `{response, result, error, requests}`。"""
        if self.transport is not None:
            self.transport.calls.clear()
        response = await self.call(tool, operation, parameters, confirm=confirm)
        result: dict[str, Any] = {}
        if response.get("success") is True:
            execution = response.get("execution") or {}
            if str(execution.get("mode")) == "ASYNC":
                result = await self.complete(response)
        requests = [] if self.transport is None else list(self.transport.calls)
        self.log.extend(requests)
        return {
            "response": response,
            "result": result,
            "data": response.get("data"),
            "error": _error_of(response),
            "requests": requests,
        }

    # ---- 只读侦察 / 哨兵 ----

    def read_ids(self, endpoint: str) -> tuple[str, ...]:
        """只读 `GET` 该端点 → 既有**编号**（升序；**零副作用**）。

        ⚠️ 只有**编号键**算编号：单例 / 状态表的读回块是 `{"DATA": ..., "HEAD": ...}`
        （`OPE.PROJECTSTATUS`），把它当「既有编号」会让哨兵**假非空**（P153 实测）。
        """
        definition = self.registry.endpoint(endpoint)
        response = self.client.get("/" + str(definition.uri).lstrip("/"))
        if response.status_code != 200:
            return ()
        try:
            payload = response.json()
        except ValueError:
            return ()
        read_root = str(definition.read_root)
        block = payload.get(read_root) if isinstance(payload, Mapping) else None
        if not isinstance(block, Mapping):
            return ()
        nested = block.get("ITEMS")
        if isinstance(nested, Sequence) and not isinstance(nested, str):
            return tuple(
                sorted(str(item.get("ID")) for item in nested if isinstance(item, Mapping))
            )
        return tuple(sorted(str(key) for key in block if str(key).isdigit()))

    def next_id(self, endpoint: str) -> str:
        """自建编号 = 该端点既有编号的 `max + 1`（空 ⇒ `1`；见纪律）。"""
        existing = [int(value) for value in self.read_ids(endpoint) if str(value).isdigit()]
        return str(max(existing) + 1) if existing else "1"

    def sentinel(self, endpoints: Sequence[str]) -> dict[str, dict[str, Any]]:
        """跑前 / 跑后只读哨兵（只发 `GET`；记录状态码与既有编号）。"""
        snapshot: dict[str, dict[str, Any]] = {}
        for key in endpoints:
            definition = self.registry.endpoint(key)
            uri = "/" + str(definition.uri).lstrip("/")
            try:
                response = self.client.get(uri)
            except Exception as error:  # noqa: BLE001 - 传输失败如实记录
                snapshot[key] = {"status": 0, "ids": [], "error": type(error).__name__}
                continue
            snapshot[key] = {
                "status": int(response.status_code),
                "ids": list(self.read_ids(key)),
            }
        return snapshot

    def recon(self, endpoint: str, method: str) -> dict[str, Any]:
        """只读侦察：`OPTIONS` 核对方法 + `GET` 核对解包链（映射**由实测确认**）。"""
        definition = self.registry.endpoint(endpoint)
        uri = "/" + str(definition.uri).lstrip("/")
        allow: list[str] = []
        try:
            options = self.client.options(uri)
            raw = options.headers.get("allow") or ""
            allow = sorted({part.strip().upper() for part in raw.split(",") if part.strip()})
        except Exception:  # noqa: BLE001 - 无 Allow 时如实留空
            allow = []
        response = self.client.get(uri)
        read_root = str(definition.read_root)
        try:
            payload: Any = response.json()
        except ValueError:
            payload = None
        return {
            "uri": uri,
            "allow": allow,
            "get_status": int(response.status_code),
            "read_root": read_root,
            "read_root_present": isinstance(payload, Mapping) and read_root in payload,
            "method_allowed": (not allow) or (str(method).upper() in allow),
        }


def _error_of(response: Mapping[str, Any]) -> dict[str, Any]:
    """统一响应信封里的错误摘要（只取码 / 原因 / 阶段 / 原生状态码，**不**回显原生 message）。

    ⚠️ 任务型失败（`STRUCTAI-2200 task_not_completed`）的真实成因在
    `details.task_error.details`（`endpoint` / `reason` / `status_code`）—— 一并取出，
    否则证据只剩「任务没跑完」这一层，无法定位。
    """
    errors = response.get("errors") or []
    if not isinstance(errors, Sequence) or not errors:
        return {}
    first = errors[0] if isinstance(errors[0], Mapping) else {}
    details = first.get("details") or {}
    summary: dict[str, Any] = {
        "code": str(first.get("code") or ""),
        "reason": str(details.get("reason") or "") if isinstance(details, Mapping) else "",
        "stage": str(details.get("stage") or "") if isinstance(details, Mapping) else "",
    }
    if not isinstance(details, Mapping):
        return summary
    task_error = details.get("task_error")
    if not isinstance(task_error, Mapping):
        return summary
    nested = task_error.get("details") or {}
    if not isinstance(nested, Mapping):
        return summary
    summary["task_code"] = str(task_error.get("code") or "")
    summary["native_reason"] = str(nested.get("reason") or "")
    summary["native_stage"] = str(nested.get("stage") or "")
    if nested.get("status_code") is not None:
        summary["native_status"] = int(nested["status_code"])
    if nested.get("endpoint"):
        summary["native_endpoint"] = str(nested["endpoint"])
    return summary


def _items_of(response: Mapping[str, Any]) -> list[dict[str, Any]]:
    """读响应的条目列表（`MODEL.*.QUERY` 的规范化结果）。

    ⚠️ 接口层把每步结果按 **`intent`** 落进 `data`：读步骤的 intent = `"read"`，
    故 `MODEL.*.QUERY` 的结果键是 **`data["read"]`**（**不是** `data["items"]` ——
    那是 Mock Adapter 的形态）。两种键都接受，**不**臆造第三处判定。
    """
    data = response.get("data")
    if not isinstance(data, Mapping):
        return []
    for name in ("items", "read"):
        items = data.get(name)
        if isinstance(items, Sequence) and not isinstance(items, str):
            return [dict(item) for item in items if isinstance(item, Mapping)]
    return []


def _find(items: Sequence[Mapping[str, Any]], own_id: str) -> Mapping[str, Any] | None:
    """按自建编号在读回结果里找条目（`id` 为**字符串**比较）。"""
    for item in items:
        if str(item.get("id")) == str(own_id):
            return item
    return None


def _last_status(requests: Sequence[Mapping[str, Any]]) -> int:
    """该次调用**接口层实际发出**的最后一个请求状态码（取不到 ⇒ 0）。"""
    if not requests:
        return 0
    return int(requests[-1].get("status") or 0)


async def _exercise(stack: _Stack, exercise: Mapping[str, Any]) -> dict[str, Any]:
    """跑一条路径（添加 / 编辑 / 删除）并返回**逐条**证据行。

    ⚠️ **无论判定如何**，本函数都会尝试删除自己创建过的编号（`finally` 段）——
    只碰自建编号，且以「再读确认不在」为准；清理失败 ⇒ 该行**降级**为 `FAILED`
    并如实进哨兵 / `residue`（**不**声称零残留）。
    """
    endpoint = str(exercise["endpoint"])
    path = str(exercise["path"])
    operation = str(exercise["operation"])
    tool = TOOL_BY_OPERATION_PATH[path]
    query = str(exercise["query"])
    row: dict[str, Any] = {
        "path": path,
        "path_label": PATH_LABELS[path],
        "tool": tool,
        "operation": operation,
        "endpoint": endpoint,
        "method": "",
        "uri": "",
        "status": FAILED,
        "own_id": "",
        "preconditions": [],
        "recon": {},
        "write": {},
        "readback": {},
        "edit": {},
        "cleanup": {},
        "requests": [],
        "detail": "",
    }
    stack.log.clear()
    created_preconditions: list[dict[str, str]] = []
    own_id = ""
    may_exist = False
    try:
        # ---- ① 只读侦察（映射**必须**由实测确认）----
        method = _declared_method(stack, endpoint, operation)
        row["method"] = method
        definition = stack.registry.endpoint(endpoint)
        row["uri"] = "/" + str(definition.uri).lstrip("/")
        row["recon"] = stack.recon(endpoint, method)
        if not row["recon"]["read_root_present"]:
            row["detail"] = "read_root_missing_on_this_build"
            return row

        # ---- ② 前置对象（**只**碰自建编号；按声明顺序创建）----
        nodes: list[str] = []
        materials: list[str] = []
        sections: list[str] = []
        buckets: dict[str, list[str]] = {
            "node": nodes,
            "material": materials,
            "section": sections,
        }
        for kind in exercise.get("preconditions") or ():
            spec = PRECONDITION_KINDS.get(str(kind))
            if spec is None:
                continue
            endpoint_key, operation_name = spec
            own = stack.next_id(endpoint_key)
            outcome = await stack.run_operation(
                "engineering_model_assign",
                operation_name,
                _precondition_parameters(str(kind), own, index=len(created_preconditions)),
            )
            if outcome["error"] or outcome["response"].get("success") is not True:
                row["detail"] = f"precondition_failed:{outcome['error']}"
                return row
            buckets[str(kind)].append(own)
            created_preconditions.append({"endpoint": endpoint_key, "id": own})
        row["preconditions"] = list(created_preconditions)

        # ---- ③ 自建编号 ----
        own_id = (
            nodes[0]
            if str(exercise.get("id_policy") or "") == "precondition_node"
            else stack.next_id(endpoint)
        )
        row["own_id"] = own_id

        if path == PATH_DELETE:
            prepared = await _prepare_for_delete(stack, endpoint, own_id, nodes, materials, sections)
            row["write"] = prepared["write"]
            may_exist = bool(prepared["may_exist"])
            if prepared["detail"]:
                row["detail"] = prepared["detail"]
                return row
            deletion = await stack.run_operation(
                tool, operation, {"item_ids": [own_id]}, confirm=True
            )
            gone, observed = await _gone(stack, query, own_id)
            row["readback"] = {"present": not gone, "observed": observed}
            row["cleanup"] = {
                "delete_http": _last_status(deletion["requests"]),
                "delete_data": deletion["data"],
                "delete_result": deletion["result"],
                "error": deletion["error"],
                "gone": gone,
                "observed": observed,
                "attempts": 1,
            }
            row["status"] = PASSED if (gone and not deletion["error"]) else FAILED
            if row["status"] != PASSED:
                row["detail"] = row["detail"] or f"delete_not_confirmed:{deletion['error']}"
        else:
            created = await stack.run_operation(
                "engineering_model_assign",
                CREATE_OPERATION_BY_ENDPOINT[endpoint],
                _parameters_for(
                    endpoint,
                    own_id,
                    nodes=nodes,
                    materials=materials,
                    sections=sections,
                    edited=False,
                ),
            )
            create_http = _last_status(created["requests"])
            row["write"] = {
                "create_http": create_http,
                "create_data": created["data"],
                "create_result": created["result"],
                "error": created["error"],
            }
            may_exist = 200 <= create_http < 300
            if created["error"]:
                row["detail"] = f"create_rejected:{created['error']}"
            present, observed = await _present(stack, query, own_id)
            row["readback"] = {"present": present, "observed": observed}
            if present and not created["error"]:
                if path == PATH_ADD:
                    row["status"] = PASSED
                else:
                    edited = await stack.run_operation(
                        tool,
                        operation,
                        _parameters_for(
                            endpoint,
                            own_id,
                            nodes=nodes,
                            materials=materials,
                            sections=sections,
                            edited=True,
                        ),
                    )
                    field, expected = _expected_value(endpoint)
                    row["edit"] = {
                        "http": _last_status(edited["requests"]),
                        "data": edited["data"],
                        "error": edited["error"],
                        "field": field,
                        "expected": expected,
                    }
                    effective, after = await _value_is(stack, query, own_id, field, expected)
                    row["edit"]["effective"] = effective
                    row["edit"]["observed"] = after
                    row["status"] = PASSED if (effective and not edited["error"]) else FAILED
                    if row["status"] != PASSED:
                        row["detail"] = row["detail"] or "edit_not_effective"
            elif not present:
                row["detail"] = row["detail"] or "readback_absent"
        return row
    except Exception as error:  # noqa: BLE001 - 逐条隔离（单条失败不打死整批）
        row["status"] = SKIPPED if INSTANCE_DOWN_MARKER in str(error) else FAILED
        row["detail"] = f"{type(error).__name__}:{error}"[:200]
        return row
    finally:
        # ---- ④ 清理（**一律**尝试；只碰自建编号；以「再读确认不在」为准）----
        if own_id and (may_exist or (row.get("cleanup") or {}).get("gone") is False):
            await _finalize(stack, endpoint, query, own_id, row)
        await _cleanup_preconditions(stack, created_preconditions)
        row["requests"] = list(stack.log)


async def _finalize(
    stack: _Stack, endpoint: str, query: str, own_id: str, row: dict[str, Any]
) -> None:
    """收尾清理：删除自建编号并**再读确认**（最多 2 次；失败 ⇒ 降级为 `FAILED`）。"""
    cleanup = row.setdefault("cleanup", {})
    if cleanup.get("gone") is True:
        return
    attempts = int(cleanup.get("attempts") or 0)
    while attempts < 2:
        outcome = await stack.run_operation(
            "engineering_model_delete",
            DELETE_OPERATION_BY_ENDPOINT[endpoint],
            {"item_ids": [own_id]},
            confirm=True,
        )
        gone, observed = await _gone(stack, query, own_id)
        attempts += 1
        cleanup.update(
            {
                "delete_http": _last_status(outcome["requests"]),
                "delete_data": outcome["data"],
                "delete_result": outcome["result"],
                "error": outcome["error"],
                "gone": gone,
                "observed": observed,
                "attempts": attempts,
            }
        )
        if gone:
            break
    if cleanup.get("gone") is not True:
        row["status"] = FAILED
        row["detail"] = row.get("detail") or "cleanup_not_confirmed"


def _declared_method(stack: _Stack, endpoint: str, operation: str) -> str:
    """`operations.py` 声明的该方法（判定点唯一；取不到 ⇒ 空串，由侦察如实反映）。"""
    _load_app(stack.repo)
    from app.infrastructure.adapters.midas.operations import plan_for  # noqa: PLC0415

    for step in steps_of(plan_for(operation)):
        if str(step.key) == endpoint:
            return str(step.method)
    return ""


async def _prepare_for_delete(
    stack: _Stack,
    endpoint: str,
    own_id: str,
    nodes: Sequence[str],
    materials: Sequence[str] = (),
    sections: Sequence[str] = (),
) -> dict[str, Any]:
    """删除路径的**前置创建**（经接口层；`DB.GRUP` 无创建 Operation ⇒ 声明为原生前置）。

    Returns:
        `{write, may_exist, detail}`；`may_exist = True` 表示该编号**可能**已经落到实例上
        （收尾必须尝试删除）。
    """
    if endpoint == "DB.GRUP":
        uri = "/" + str(stack.registry.endpoint(endpoint).uri).lstrip("/")
        body = {"Assign": {own_id: {"NAME": f"P152G{own_id}"}}}
        response = stack.client.post(uri, json=body)
        status = int(response.status_code)
        stack.log.append(
            {
                "method": "POST",
                "path": uri,
                "status": status,
                "body": body,
                "via": "raw_precondition",
            }
        )
        return {
            "write": {"precondition": "raw_post", "http": status},
            "may_exist": 200 <= status < 300,
            "detail": "" if status < 400 else f"raw_precondition_http_{status}",
        }
    created = await stack.run_operation(
        "engineering_model_assign",
        CREATE_OPERATION_BY_ENDPOINT[endpoint],
        _parameters_for(
            endpoint, own_id, nodes=nodes, materials=materials, sections=sections, edited=False
        ),
    )
    status = _last_status(created["requests"])
    return {
        "write": {
            "precondition": "interface",
            "create_http": status,
            "error": created["error"],
        },
        "may_exist": 200 <= status < 300,
        "detail": "" if not created["error"] else f"precondition_failed:{created['error']}",
    }


async def _cleanup_preconditions(stack: _Stack, created: Sequence[Mapping[str, str]]) -> None:
    """**逆序**回收前置对象（节点 / 材质 / 截面；**再读确认不在**；失败只记不抛）。

    ⚠️ 顺序不可换：`DB.ELEM` 引用材质 / 截面 ⇒ 目标先删、前置**逆序**再删
    （声明顺序 `node, node, material, section` ⇒ 回收顺序 `section, material, node, node`）。
    """
    for item in reversed(list(created)):
        endpoint = str(item.get("endpoint"))
        operation = DELETE_OPERATION_BY_ENDPOINT.get(endpoint)
        if operation is None:
            continue
        try:
            await stack.run_operation(
                "engineering_model_delete",
                operation,
                {"item_ids": [str(item.get("id"))]},
                confirm=True,
            )
        except Exception:  # noqa: BLE001 - 收尾失败不影响判定（哨兵会如实反映）
            continue


async def _present(stack: _Stack, query: str, own_id: str) -> tuple[bool, dict[str, Any]]:
    """读回：该编号是否在（经接口层 `MODEL.*.QUERY`）。"""
    outcome = await stack.run_operation("engineering_model_query", query)
    found = _find(_items_of(outcome["response"]), own_id)
    return found is not None, dict(found) if found is not None else {}


async def _gone(stack: _Stack, query: str, own_id: str) -> tuple[bool, dict[str, Any]]:
    """删除确认：**再读一次**，该编号确实不在（R119）。"""
    present, observed = await _present(stack, query, own_id)
    return (not present), observed


async def _value_is(
    stack: _Stack, query: str, own_id: str, field: str, expected: Any
) -> tuple[bool, dict[str, Any]]:
    """编辑确认：读回该字段 == 改动后的值。"""
    present, observed = await _present(stack, query, own_id)
    if not present or not field:
        return False, observed
    return _close(observed.get(field), expected), observed


def _close(actual: Any, expected: Any) -> bool:
    """数值比较（`1` / `1.0` 视为相等；布尔严格比较；其余严格相等）。"""
    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual == expected
    try:
        return abs(float(actual) - float(expected)) < 1e-9
    except (TypeError, ValueError):
        return actual == expected


def _existing_rows(repo: pathlib.Path) -> dict[tuple[str, str], dict[str, Any]]:
    """既有证据的逐行结果（判据版本不符 ⇒ 空 ⇒ **全部重测**）。"""
    document = _read_json(repo / "registry" / EVIDENCE_RELATIVE)
    if int(document.get("criterion_version") or 0) != CRITERION_VERSION:
        return {}
    rows = document.get("paths")
    if not isinstance(rows, list):
        return {}
    return {
        (str(row.get("path")), str(row.get("endpoint"))): dict(row)
        for row in rows
        if isinstance(row, Mapping)
    }


def _sorted_rows(rows: Mapping[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    """证据行排序（路径顺序 → 端点名；确定性）。"""
    order = {PATH_ADD: 0, PATH_EDIT: 1, PATH_DELETE: 2}
    return [
        rows[key]
        for key in sorted(rows, key=lambda item: (order.get(item[0], 9), item[1]))
    ]


# ===== P153：读路径（零写请求）=====


def load_read_evidence(repo: pathlib.Path) -> dict[str, Any]:
    """接口层**读路径**证据（缺失 / 版本不符 → 明确退出）。"""
    document = _read_json(repo / "registry" / READ_EVIDENCE_RELATIVE)
    if not document:
        raise SystemExit(f"❌ 缺证据文件 registry/{READ_EVIDENCE_RELATIVE}（先跑 --probe-read）")
    if int(document.get("criterion_version") or 0) != READ_CRITERION_VERSION:
        raise SystemExit(
            f"❌ 读路径证据的 criterion_version = {document.get('criterion_version')!r}，"
            f"本工具为 {READ_CRITERION_VERSION}（判据已变 ⇒ 先重跑 --probe-read）"
        )
    return document


def read_plan(repo: pathlib.Path, operation: str) -> Any:
    """该 Operation 的 `OperationPlan`（**唯一**判定点 = `operations.py`）。"""
    _load_app(repo)
    from app.infrastructure.adapters.midas.operations import plan_for  # noqa: PLC0415

    return plan_for(operation)


def read_endpoints(repo: pathlib.Path, operation: str) -> tuple[str, ...]:
    """读类 Operation 引用的**全部**端点（由编排推导，**不**在声明里写死）。"""
    return tuple(str(step.key) for step in steps_of(read_plan(repo, operation)))


def read_sentinel_keys(repo: pathlib.Path) -> list[str]:
    """读路径哨兵端点集 = 全部读类 Operation 引用到的端点（去重、升序）。"""
    keys: set[str] = set()
    for exercise in READ_EXERCISES:
        keys.update(read_endpoints(repo, str(exercise["operation"])))
    return sorted(keys)


def _step_block(shape: Mapping[str, Any], read_root: str) -> str:
    """解包链命中情况：`nonempty` / `empty` / `absent` / `n/a`（结果类端点无 `read_root`）。"""
    if not read_root:
        return "n/a"
    info = shape.get(read_root)
    if not isinstance(info, Mapping):
        return "absent"
    return "empty" if int(info.get("size") or 0) == 0 else "nonempty"


async def _read_exercise(stack: _Stack, exercise: Mapping[str, Any]) -> dict[str, Any]:
    """跑一条**读**路径（`GET` / 取报表 `POST`）并返回**逐条**证据行。

    ⚠️ **零写请求**：只发 `GET` 与 `POST /POST/TABLE`；`PUT` / `DELETE` / `PATCH`
    在本路径**结构上不可能**出现（`--check` 与测试逐条断言 = 0）。
    """
    tool = str(exercise["tool"])
    operation = str(exercise["operation"])
    steps = steps_of(read_plan(stack.repo, operation))
    endpoints = [str(step.key) for step in steps]
    first = steps[0]
    row: dict[str, Any] = {
        "tool": tool,
        "operation": operation,
        "endpoint": endpoints[0],
        "endpoints": endpoints,
        "method": str(first.method),
        "uri": "",
        "status": FAILED,
        "http": 0,
        "intent": str(first.intent),
        "recon": {},
        "steps": [],
        "readback": {},
        "error": {},
        "requests": [],
        "detail": "",
    }
    stack.log.clear()
    try:
        definition = stack.registry.endpoint(endpoints[0])
        row["uri"] = "/" + str(definition.uri).lstrip("/")
        row["recon"] = stack.recon(endpoints[0], str(first.method))
        outcome = await stack.run_operation(
            tool, operation, dict(exercise.get("parameters") or {})
        )
        requests = list(stack.log)
        row["http"] = _last_status(requests)
        row["requests"] = requests
        row["error"] = _error_of(outcome["response"])
        step_rows: list[dict[str, Any]] = []
        for index, step in enumerate(steps):
            record = requests[index] if index < len(requests) else {}
            try:
                resolved = stack.registry.resolve(
                    key=str(step.key), product=PRODUCT_KEY, method=str(step.method)
                )
                read_root = str(resolved.read_root or "")
            except Exception:  # noqa: BLE001 - 解析失败（如产品不可得）如实留空
                read_root = ""
            shape = record.get("shape") if isinstance(record.get("shape"), Mapping) else {}
            step_rows.append(
                {
                    "endpoint": str(step.key),
                    "method": str(step.method),
                    "intent": str(step.intent),
                    "status": int(record.get("status") or 0),
                    "read_root": read_root,
                    "block": _step_block(shape, read_root),
                    "native_size": int((shape.get(read_root) or {}).get("size") or 0)
                    if read_root and isinstance(shape.get(read_root), Mapping)
                    else 0,
                }
            )
        row["steps"] = step_rows
        row["readback"] = _readback_of(str(first.intent), outcome["data"])
        row["detail"], row["status"] = _read_verdict(row)
        return row
    except Exception as error:  # noqa: BLE001 - 逐条隔离（单条失败不打死整批）
        row["status"] = SKIPPED if INSTANCE_DOWN_MARKER in str(error) else FAILED
        row["detail"] = f"{type(error).__name__}:{error}"[:200]
        return row
    finally:
        row["requests"] = list(stack.log)


def _readback_of(intent: str, data: Any) -> dict[str, Any]:
    """规范化结果的**摘要**（读 = 有取值的条目数 + 首条键集；结果 = 行数）。

    ⚠️ **不**留任何取值 —— 只有计数与键名（键名来自 canonical 模型，非响应原文）。
    ⚠️ 「有取值」= 条目里**至少一个**字段不是 `None`：空块经 Transformer 会退化成
    `{"x": None, "y": None, ...}`（**非空** dict），只数「非空 dict」会把空块算成 1 条
    （P153 实测）⇒ 计数口径必须按**取值**判。
    """
    summary: dict[str, Any] = {"intent": intent, "count": 0, "keys": []}
    if not isinstance(data, Mapping):
        return summary
    payload = data.get(intent)
    if intent == "result":
        rows = payload.get("rows") if isinstance(payload, Mapping) else None
        summary["count"] = len(rows) if isinstance(rows, Sequence) else 0
        return summary
    if not isinstance(payload, Sequence) or isinstance(payload, str):
        return summary
    items = [item for item in payload if isinstance(item, Mapping)]
    valued = [item for item in items if any(value is not None for value in item.values())]
    summary["count"] = len(valued)
    if items:
        summary["keys"] = sorted(str(key) for key in items[0])
    return summary


def _read_verdict(row: Mapping[str, Any]) -> tuple[str, str]:
    """L4 口径的读路径判定：`2xx` ∧ 解包链命中；空块 ⇒ `PARTIAL`。

    Returns:
        `(detail, status)`。
    """
    requests = list(row.get("requests") or [])
    step_rows = list(row.get("steps") or [])
    error = row.get("error") or {}
    code = str(error.get("code") or "")
    if not requests:
        return (f"no_interface_request:{code}" if code else "no_interface_request"), FAILED
    statuses = [int(item.get("status") or 0) for item in requests]
    if any(not 200 <= value < 300 for value in statuses):
        return f"http_{statuses[-1]}:{code}" if code else f"http_{statuses[-1]}", FAILED
    count = int((row.get("readback") or {}).get("count") or 0)
    if str(row.get("intent")) == "result":
        return ("", PASSED) if count > 0 else ("empty_table", PARTIAL)
    blocks = [str(item.get("block")) for item in step_rows]
    if any(block == "absent" for block in blocks):
        return "read_root_missing", FAILED
    if all(block == "nonempty" for block in blocks):
        return ("", PASSED) if count > 0 else ("readback_empty_after_transform", PARTIAL)
    return "empty_block", PARTIAL


def _read_existing_rows(repo: pathlib.Path) -> dict[str, dict[str, Any]]:
    """既有**读路径**证据的逐行结果（判据版本不符 ⇒ 空 ⇒ 全部重测）。"""
    document = _read_json(repo / "registry" / READ_EVIDENCE_RELATIVE)
    if int(document.get("criterion_version") or 0) != READ_CRITERION_VERSION:
        return {}
    rows = document.get("paths")
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("operation")): dict(row)
        for row in rows
        if isinstance(row, Mapping) and row.get("operation")
    }


def probe_read(
    repo: pathlib.Path,
    *,
    only: tuple[str, ...] = (),
    limit: int = CHUNK_SIZE,
    chunk_size: int = CHUNK_SIZE,
    allow_residue: tuple[str, ...] = (),
) -> int:
    """接口层**读路径**（有界：分块 + 块间只读健康检查 + 跑前 / 跑后只读哨兵 + 累积）。"""
    base_url = os.environ.get("MIDAS_BASE_URL", "").rstrip("/")
    key_value = os.environ.get("MIDAS_MAPI_KEY", "")
    if not base_url or not key_value:
        print("❌ --probe-read 需要 MIDAS_BASE_URL / MIDAS_MAPI_KEY（见 scripts/load-midas-env.ps1）")
        return 1

    existing = _read_existing_rows(repo)
    pending = [
        exercise
        for exercise in READ_EXERCISES
        if (not only or str(exercise["operation"]) in only)
        and str(exercise["operation"]) not in existing
    ][:limit]
    sentinel_keys = read_sentinel_keys(repo)
    print(
        f"接口层读路径：读类 Operation {len(READ_EXERCISES)} 条 · 端点 {len(sentinel_keys)} 个 · "
        f"哨兵 {len(sentinel_keys)} 个端点 · 既有证据 {len(existing)} 行 ⇒ "
        f"本次待跑 {len(pending)} 条（实例 {INSTANCE_ALIAS} / {INSTANCE_PRODUCT}）"
    )

    with tempfile.TemporaryDirectory(prefix="p153-interface-read-") as raw:
        fresh_rows, aborted, before, after, dedicated = asyncio.run(
            _probe_read_async(
                repo, pathlib.Path(raw), pending, sentinel_keys, chunk_size, allow_residue
            )
        )

    merged = dict(existing)
    for row in fresh_rows:
        merged[str(row["operation"])] = row
    order = {str(item["operation"]): index for index, item in enumerate(READ_EXERCISES)}
    rows = [merged[key] for key in sorted(merged, key=lambda name: order.get(name, 99))]
    counts: dict[str, int] = {}
    by_tool: dict[str, dict[str, int]] = {}
    for row in rows:
        counts[str(row["status"])] = counts.get(str(row["status"]), 0) + 1
        bucket = by_tool.setdefault(str(row["tool"]), {})
        bucket[str(row["status"])] = bucket.get(str(row["status"]), 0) + 1
    residue = {key: value["ids"] for key, value in after.items() if value.get("ids")}
    methods: dict[str, int] = {}
    for row in rows:
        for item in row.get("requests") or []:
            name = str(item.get("method"))
            methods[name] = methods.get(name, 0) + 1
    document = {
        "note": [
            "判据（**P153 接口层读路径**）：与写路径**同一链路** —— "
            "MCP Tool → OperationPlan（`operations.py`）→ Adapter（intent 分派）→ "
            "MidasHttpClient（护栏 + 包装键）→ MIDAS 实例。",
            "**零写请求**：只发 `GET` 与取报表 `POST /POST/TABLE`；"
            "`PUT` / `DELETE` / `PATCH` 在本路径**结构上不可能**出现（逐条断言 = 0）。",
            "判定沿用 **L4 口径**（`docs/04` §71）：`2xx` ∧ 解包链命中（`read_root` 在响应顶层）"
            "⇒ 数据块非空 `PASSED` / 空块 `PARTIAL`；`4xx` / 解包链不命中 ⇒ `FAILED`。",
            "规范化结果的键是 **`intent`**（读 = `data[\"read\"]`、取报表 = `data[\"result\"]`）"
            "—— **不是** Mock Adapter 的 `data[\"items\"]`。",
            "⚠️ 多端点读 Operation（如 `MODEL.LOAD.QUERY` 的 4 个端点）的规范化结果键**相同**，"
            "接口层按 `intent` 落键 ⇒ `data[\"read\"]` **只保留最后一步**（本证据的逐端点读数"
            "取自 `steps[]`，不依赖该聚合键）。",
            "证据里**只有**结构形态（每个顶层键的 `kind` / `size`）——**不含**任何取值 / 响应原文；"
            "失败请求**只**留原生 `error.message` 的前 200 字（`native_error`）。",
            "生成器 = `registry/tools/probe_interface_paths.py --probe-read`"
            f"（分块 ≤ `--chunk-size` + 块间只读健康检查 `{HEALTH_PATH}` + 跑前 / 跑后只读哨兵；"
            "累积：既有行逐字节保留）。",
            "⚠️ 本判据**不**并入任何覆盖率口径（`live.write_path_coverage()` **不变**），"
            "也**不**并入 P152 的写路径子桶（**13** 条 = 4 + 9）。",
        ],
        "criterion_version": READ_CRITERION_VERSION,
        "instance": {
            "alias": INSTANCE_ALIAS,
            "product": INSTANCE_PRODUCT,
            "base_url": base_url,
            "probed_at": PROBED_AT,
        },
        "dedicated_project": dedicated,
        "read_only": True,
        "methods": methods,
        "write_requests": sum(
            count for name, count in methods.items() if name in WRITE_REQUEST_METHODS
        ),
        "sentinel_endpoints": sentinel_keys,
        "sentinel_before": before,
        "sentinel_after": after,
        "residue": residue,
        "allowed_residue": sorted(allow_residue),
        "aborted": aborted,
        "counts": counts,
        "by_tool": by_tool,
        "paths": rows,
    }
    path = repo / "registry" / READ_EVIDENCE_RELATIVE
    if _write_evidence(path, document, aborted):
        print(f"已写入 registry/{READ_EVIDENCE_RELATIVE}（{len(rows)} 行）")
    undisclosed = {name for name in residue if name not in allow_residue}
    print(
        "verdict =",
        counts,
        " by_tool =",
        by_tool,
        " 中止 =",
        bool(aborted),
        " 残留 =",
        sorted(residue),
        " 未披露残留 =",
        sorted(undisclosed),
    )
    return 1 if (aborted or undisclosed) else 0


async def _probe_read_async(
    repo: pathlib.Path,
    workdir: pathlib.Path,
    pending: Sequence[Mapping[str, Any]],
    sentinel_keys: Sequence[str],
    chunk_size: int,
    allow_residue: tuple[str, ...],
) -> tuple[list[dict[str, Any]], str, dict[str, Any], dict[str, Any], dict[str, Any]]:
    """读路径的异步主体（装配 → 哨兵 → 分块 → 哨兵；**零写请求**）。"""
    rows: list[dict[str, Any]] = []
    aborted = ""
    async with _Stack(repo, workdir, read_mode=True) as stack:
        dedicated = {
            "note": "临时库自建（`docs/04` §72：专用实例 / 专用 Key / 专用项目）；跑完即弃",
            "project_id": stack.ids.get("project_id", ""),
            "model_id": stack.ids.get("model_id", ""),
            "software_instance_id": stack.instance_id,
            "product": INSTANCE_PRODUCT,
        }
        before = stack.sentinel(sentinel_keys)
        # ⚠️ **P155 加固**：读路径**零写请求** ⇒ 只要求「**全部**不可读」时中止（部分 405 是正常的：
        # `POST.TABLE*` 的 `GET` 本就 `405`）。
        unreadable = sorted(
            key
            for key, value in before.items()
            if int(value.get("status") or 0) == 0 or value.get("error")
        )
        if unreadable and len(unreadable) == len(before):
            aborted = f"跑前哨兵**全部不可读**（实例不可达 / 传输失败）⇒ 一个请求都不发：{unreadable[:5]}"
            print(f"⚠️ {aborted}")
            return rows, aborted, before, before, dedicated
        blocked = {
            key: value["ids"]
            for key, value in before.items()
            if value.get("ids") and key not in allow_residue
        }
        if blocked:
            aborted = f"跑前哨兵**非空** ⇒ 一个请求都不发（{sorted(blocked)[:5]}）"
            print(f"⚠️ {aborted}")
            return rows, aborted, before, before, dedicated
        for start in range(0, len(pending), chunk_size):
            chunk = list(pending[start : start + chunk_size])
            for exercise in chunk:
                row = await _read_exercise(stack, exercise)
                rows.append(row)
                print(
                    f"  [{row['tool']}] {row['operation']} → {','.join(row['endpoints'])} "
                    f"= {row['status']} {row.get('detail') or ''}"
                )
            try:
                health = int(stack.client.get(HEALTH_PATH).status_code)
            except Exception as error:  # noqa: BLE001 - 传输失败如实中止
                aborted = (
                    f"健康检查 {HEALTH_PATH} **传输失败**（{type(error).__name__}）"
                    "⇒ **立即中止**（P149-B2 的教训 + P155 的加固）"
                )
                print(f"  ⚠️ {aborted}")
                break
            print(f"  块 {start // chunk_size + 1} 完成（{len(chunk)} 条）；健康检查 → {health}")
            if health != 200:
                aborted = f"健康检查 {HEALTH_PATH} → {health}（**立即中止**，P149-B2 的教训）"
                print(f"  ⚠️ {aborted}")
                break
        after = stack.sentinel(sentinel_keys)
        # ---- 零写请求（结构性断言：只允许 GET 与取报表 POST）----
        offenders = [
            item
            for row in rows
            for item in row.get("requests") or []
            if str(item.get("method")) in WRITE_REQUEST_METHODS
        ]
        off_table = [
            item
            for row in rows
            for item in row.get("requests") or []
            if str(item.get("method")) == "POST"
            and not str(item.get("path")).endswith(TABLE_URI)
        ]
        if offenders or off_table:
            aborted = (
                "读路径出现了写请求 / 表外 POST ⇒ 中止并如实报告"
                f"（写方法 {len(offenders)} 条 / 表外 POST {len(off_table)} 条）"
            )
            print(f"  ⚠️ {aborted}")
        return rows, aborted, before, after, dedicated


def probe(
    repo: pathlib.Path,
    *,
    only: tuple[str, ...] = (),
    paths: tuple[str, ...] = (),
    limit: int = CHUNK_SIZE,
    chunk_size: int = CHUNK_SIZE,
    allow_residue: tuple[str, ...] = (),
) -> int:
    """接口层端到端（有界：分块 + 块间只读健康检查 + 跑前 / 跑后只读哨兵 + **累积**）。"""
    base_url = os.environ.get("MIDAS_BASE_URL", "").rstrip("/")
    key_value = os.environ.get("MIDAS_MAPI_KEY", "")
    if not base_url or not key_value:
        print("❌ --probe 需要 MIDAS_BASE_URL / MIDAS_MAPI_KEY（见 scripts/load-midas-env.ps1）")
        return 1

    existing = _existing_rows(repo)
    pending = [
        exercise
        for exercise in EXERCISES
        if (not only or str(exercise["endpoint"]) in only)
        and (not paths or str(exercise["path"]) in paths)
        and (str(exercise["path"]), str(exercise["endpoint"])) not in existing
    ][:limit]
    sentinel_keys = sorted({str(item["endpoint"]) for item in EXERCISES})
    print(
        f"接口层端到端：路径 {len(EXERCISES)} 条 · 端点 {len(sentinel_keys)} 个 · "
        f"哨兵 {len(sentinel_keys)} 个端点 · 既有证据 {len(existing)} 行 ⇒ "
        f"本次待跑 {len(pending)} 条（实例 {INSTANCE_ALIAS} / {INSTANCE_PRODUCT}）"
    )

    with tempfile.TemporaryDirectory(prefix="p152-interface-") as raw:
        fresh_rows, aborted, before, after, dedicated = asyncio.run(
            _probe_async(
                repo, pathlib.Path(raw), pending, sentinel_keys, chunk_size, allow_residue
            )
        )

    merged = dict(existing)
    for row in fresh_rows:
        merged[(str(row["path"]), str(row["endpoint"]))] = row
    rows = _sorted_rows(merged)
    counts: dict[str, int] = {}
    by_path: dict[str, dict[str, int]] = {}
    for row in rows:
        counts[str(row["status"])] = counts.get(str(row["status"]), 0) + 1
        bucket = by_path.setdefault(str(row["path"]), {})
        bucket[str(row["status"])] = bucket.get(str(row["status"]), 0) + 1
    residue = {key: value["ids"] for key, value in after.items() if value.get("ids")}
    document = {
        "note": [
            "判据（**P152 接口层**）：经**既有 9 个 MCP Tool 契约** —— "
            "MCP Tool → OperationPlan（`operations.py`）→ Adapter（intent 分派）→ "
            "MidasHttpClient（护栏 + 包装键）→ MIDAS 实例。",
            "**添加** = 创建经接口层 → 读回在；**编辑** = 创建 → `PUT` 改动过的值 → "
            "读回确认**改动生效**；**删除** = 创建 → `DELETE` 带路径 key → 读回**确认消失**；"
            "每行另有**清理**（自建编号再读不在）。",
            "**只读侦察先行**：每条路径前对目标端点发 `OPTIONS`（核对 `Allow`）与 `GET`"
            "（核对解包链 `read_root`）—— 映射**由实测确认**，不按名字臆造。",
            "**删除以「再读一次、该编号确实不在」为准**（R119：本 build 的 `DELETE` 会返回 "
            "`200` 并回显被删记录却**不真正删除**）。",
            "**只碰自建编号**（= 该端点既有编号的 `max + 1`；专用空项目 ⇒ `1`）；"
            "跑前哨兵非空 ⇒ **一个写请求都不发**（`aborted`）。",
            "证据里的 `requests` 是**接口层实际发出**的请求（method + path + 请求体）——"
            "请求体是本探针自建的**规范化数据**，非凭据、非响应体原文；"
            "⚠️ **失败**请求另留原生 `error.message` 的前 200 字（`native_error`，"
            "诊断必需，与数据侧 `probe_put_edits` 的口径一致）；**成功**响应不留任何原文。",
            "生成器 = `registry/tools/probe_interface_paths.py --probe`（**分块** ≤ "
            f"`--chunk-size` + 块间只读健康检查 `{HEALTH_PATH}` + 跑前 / 跑后只读哨兵；"
            "**累积**：既有行逐字节保留，本批只补新目标）。",
            "⚠️ 本判据**不**并入任何数据侧覆盖率口径（`live.write_path_coverage()` **不变**）。",
        ],
        "criterion_version": CRITERION_VERSION,
        "instance": {
            "alias": INSTANCE_ALIAS,
            "product": INSTANCE_PRODUCT,
            "base_url": base_url,
            "probed_at": PROBED_AT,
        },
        "dedicated_project": dedicated,
        "sentinel_endpoints": sentinel_keys,
        "sentinel_before": before,
        "sentinel_after": after,
        "residue": residue,
        "allowed_residue": sorted(allow_residue),
        "aborted": aborted,
        "counts": counts,
        "by_path": by_path,
        "paths": rows,
    }
    path = repo / "registry" / EVIDENCE_RELATIVE
    if _write_evidence(path, document, aborted):
        print(f"已写入 registry/{EVIDENCE_RELATIVE}（{len(rows)} 行）")
    undisclosed = {name for name in residue if name not in allow_residue}
    print(
        "verdict =",
        counts,
        " by_path =",
        by_path,
        " 中止 =",
        bool(aborted),
        " 残留 =",
        sorted(residue),
        " 未披露残留 =",
        sorted(undisclosed),
    )
    return 1 if (aborted or undisclosed) else 0


async def _probe_async(
    repo: pathlib.Path,
    workdir: pathlib.Path,
    pending: Sequence[Mapping[str, Any]],
    sentinel_keys: Sequence[str],
    chunk_size: int,
    allow_residue: tuple[str, ...],
) -> tuple[list[dict[str, Any]], str, dict[str, Any], dict[str, Any], dict[str, Any]]:
    """真正的异步主体（装配 → 哨兵 → 分块 → 哨兵）。"""
    rows: list[dict[str, Any]] = []
    aborted = ""
    async with _Stack(repo, workdir) as stack:
        dedicated = {
            "note": "临时库自建（`docs/04` §72：专用实例 / 专用 Key / 专用项目）；跑完即弃",
            "project_id": stack.ids.get("project_id", ""),
            "model_id": stack.ids.get("model_id", ""),
            "software_instance_id": stack.instance_id,
            "product": INSTANCE_PRODUCT,
        }
        before = stack.sentinel(sentinel_keys)
        # ⚠️ **P155 加固（实测事故驱动）**：哨兵**读不到**（传输失败 / 实例不可达）时**绝不盲写** ——
        # 读不到就**无法**证明「跑前为空」；P154 的 `--probe` 在实例不可达时曾一路发到 5 条失败并
        # 在块间健康检查处**崩溃**（证据文件都没写成）。这里改为：**任一**被触碰端点读不到 ⇒ 中止。
        unreadable = sorted(
            key
            for key, value in before.items()
            if int(value.get("status") or 0) == 0 or value.get("error")
        )
        if unreadable:
            aborted = (
                "跑前哨兵**不可读**（实例不可达 / 传输失败）⇒ 一个请求都不发："
                f"{unreadable[:5]}（P138c：读不到就**不盲写**）"
            )
            print(f"⚠️ {aborted}")
            return rows, aborted, before, before, dedicated
        blocked = {
            key: value["ids"]
            for key, value in before.items()
            if value.get("ids") and key not in allow_residue
        }
        if blocked:
            aborted = f"跑前哨兵**非空** ⇒ 一个写请求都不发（{sorted(blocked)[:5]}）"
            print(f"⚠️ {aborted}")
            return rows, aborted, before, before, dedicated
        for start in range(0, len(pending), chunk_size):
            chunk = list(pending[start : start + chunk_size])
            for exercise in chunk:
                row = await _exercise(stack, exercise)
                rows.append(row)
                print(
                    f"  [{row['path_label']}] {row['operation']} → {row['endpoint']} "
                    f"= {row['status']} {row.get('detail') or ''}"
                )
            # ⚠️ **P155 加固**：健康检查的**传输失败**也归 `aborted`（**不**让异常把整批打崩、
            # 从而丢掉已跑出的行与证据文件）。
            try:
                health = int(stack.client.get(HEALTH_PATH).status_code)
            except Exception as error:  # noqa: BLE001 - 传输失败如实中止
                aborted = (
                    f"健康检查 {HEALTH_PATH} **传输失败**（{type(error).__name__}）"
                    "⇒ **立即中止**（P149-B2 的教训 + P155 的加固）"
                )
                print(f"  ⚠️ {aborted}")
                break
            print(f"  块 {start // chunk_size + 1} 完成（{len(chunk)} 条）；健康检查 → {health}")
            if health != 200:
                aborted = f"健康检查 {HEALTH_PATH} → {health}（**立即中止**，P149-B2 的教训）"
                print(f"  ⚠️ {aborted}")
                break
        after = stack.sentinel(sentinel_keys)
        return rows, aborted, before, after, dedicated


# ===== 离线复算 =====


def _plan_step(repo: pathlib.Path, operation: str, endpoint: str) -> Mapping[str, Any] | None:
    """`operations.py` 里该 Operation 引用的该端点步骤（**唯一**判定点）。"""
    _load_app(repo)
    from app.infrastructure.adapters.midas.operations import plan_for  # noqa: PLC0415

    try:
        plan = plan_for(operation)
    except Exception:  # noqa: BLE001 - 未登记 ⇒ 由调用方记缺口
        return None
    for step in steps_of(plan):
        if str(step.key) == endpoint:
            return {"method": str(step.method), "intent": str(step.intent), "tool": str(plan.tool)}
    return None


def check_read(repo: pathlib.Path) -> list[str]:
    """离线断言：**读路径**证据与 `operations.py` / manifest / 判据自洽（零写请求）。"""
    problems: list[str] = []
    document = load_read_evidence(repo)
    rows = document.get("paths") or []
    index = manifest_index(repo)
    if not isinstance(rows, list) or not rows:
        problems.append(f"{READ_EVIDENCE_RELATIVE}: paths 为空")
        return problems
    by_operation = {str(row.get("operation")): row for row in rows}
    expected = [str(item["operation"]) for item in READ_EXERCISES]
    if sorted(by_operation) != sorted(expected):
        problems.append(
            f"{READ_EVIDENCE_RELATIVE}: 行集 ≠ 读类 Operation 声明集"
            f"（缺 {sorted(set(expected) - set(by_operation))} / 多 "
            f"{sorted(set(by_operation) - set(expected))}）"
        )
    for row in rows:
        tool = str(row.get("tool"))
        operation = str(row.get("operation"))
        declared = next(
            (item for item in READ_EXERCISES if str(item["operation"]) == operation), None
        )
        if declared is None:
            problems.append(f"{operation}: 不在读类 Operation 声明里")
            continue
        if tool != str(declared["tool"]):
            problems.append(f"{operation}: tool = {tool!r} ≠ 声明 {declared['tool']!r}")
        try:
            plan = read_plan(repo, operation)
        except Exception as error:  # noqa: BLE001 - 未登记 ⇒ 如实记
            problems.append(f"{operation}: operations.py 里不可解析（{error}）")
            continue
        if str(plan.tool) != tool:
            problems.append(f"{operation}: tool ≠ operations.py 的 {str(plan.tool)!r}")
        endpoints = [str(step.key) for step in steps_of(plan)]
        if list(row.get("endpoints") or []) != endpoints:
            problems.append(f"{operation}: endpoints = {row.get('endpoints')!r} ≠ 编排 {endpoints}")
        if str(row.get("method")) != str(steps_of(plan)[0].method):
            problems.append(f"{operation}: method ≠ 编排首步")
        if str(row.get("intent")) != str(steps_of(plan)[0].intent):
            problems.append(f"{operation}: intent ≠ 编排首步")
        entry = index.get(endpoints[0])
        if entry is None:
            problems.append(f"{operation}: manifest 里没有端点 {endpoints[0]}")
        elif str(row.get("uri")) != "/" + str(entry.get("uri") or "").lstrip("/"):
            problems.append(f"{operation}: uri = {row.get('uri')!r} ≠ manifest")
        status = str(row.get("status"))
        if status not in {PASSED, PARTIAL, FAILED, SKIPPED}:
            problems.append(f"{operation}: 未知 status {status!r}")
        if status in {PASSED, PARTIAL}:
            http = int(row.get("http") or 0)
            if not 200 <= http < 300:
                problems.append(f"{operation}: {status} 但接口层最后一个请求状态码 = {http}")
            if not (row.get("readback") or {}).get("intent"):
                problems.append(f"{operation}: {status} 但读回摘要为空")
            if status == PASSED and int((row.get("readback") or {}).get("count") or 0) < 1:
                problems.append(f"{operation}: PASSED 但读回条目数为 0")
        if status == FAILED:
            if not str(row.get("detail") or ""):
                problems.append(f"{operation}: FAILED 但没有成因")
            if not row.get("error"):
                problems.append(f"{operation}: FAILED 但没有错误摘要（**不**留空）")
            elif not (row["error"].get("native_reason") or row["error"].get("code")):
                problems.append(f"{operation}: FAILED 但没有原生原因 / 错误码")
        for item in row.get("requests") or []:
            method = str(item.get("method"))
            if method not in READ_METHODS:
                problems.append(f"{operation}: 读路径出现了 {method} 请求")
            if method == "POST" and not str(item.get("path")).endswith(TABLE_URI):
                problems.append(f"{operation}: 读路径的 POST 不在 {TABLE_URI}（{item.get('path')}）")
        if "MAPI-Key" in json.dumps(row.get("requests") or [], ensure_ascii=False):
            problems.append(f"{operation}: 请求记录里出现凭据字样")

    # ---- 每个读类 Tool 都取得**结论**（任务 1 的硬要求）----
    concluded: dict[str, int] = {}
    for row in rows:
        tool = str(row.get("tool"))
        concluded[tool] = concluded.get(tool, 0) + 1
    for tool in sorted({str(item["tool"]) for item in READ_EXERCISES}):
        if concluded.get(tool, 0) < 1:
            problems.append(f"{tool}: 没有取得任何读路径结论（任务 1 的硬要求）")

    # ---- 零写请求 / 哨兵自洽 / 残留披露 ----
    declared_write = document.get("write_requests")
    if declared_write is None or int(declared_write) != 0:
        problems.append(f"{READ_EVIDENCE_RELATIVE}: write_requests = {declared_write!r} ≠ 0")
    for name, count in (document.get("methods") or {}).items():
        if str(name) not in READ_METHODS:
            problems.append(f"{READ_EVIDENCE_RELATIVE}: 出现过 {name}（{count} 次）")
    if document.get("sentinel_before") != document.get("sentinel_after"):
        problems.append(f"{READ_EVIDENCE_RELATIVE}: 跑前 / 跑后哨兵不一致（读路径应零副作用）")
    if document.get("aborted"):
        problems.append(f"{READ_EVIDENCE_RELATIVE}: aborted 非空（{document['aborted']}）")
    if sorted(document.get("sentinel_endpoints") or []) != read_sentinel_keys(repo):
        problems.append(f"{READ_EVIDENCE_RELATIVE}: 哨兵端点集 ≠ 全部被触碰的端点")
    allowed = set(document.get("allowed_residue") or ())
    for key in document.get("residue") or {}:
        if key not in allowed:
            problems.append(f"{READ_EVIDENCE_RELATIVE}: 残留 {key} **未**披露")
    return problems


def check(repo: pathlib.Path) -> int:
    """离线断言：证据与 `operations.py` / `manifest.json` / 判据自洽。"""
    problems: list[str] = []

    # ---- ① 映射缺口清单与数据侧复算一致 ----
    gap_document = _read_json(repo / "registry" / GAP_RELATIVE)
    if not gap_document:
        problems.append(f"缺映射缺口清单 registry/{GAP_RELATIVE}（先跑 --recon）")
    else:
        fresh = mapping_gap(repo)
        for key in (
            "operations",
            "mapped_endpoints",
            "write_capable_endpoints",
            "three_step_endpoints",
            "mapped_inside_three_step",
            "gap_total",
        ):
            if int(gap_document.get(key) or -1) != int(fresh[key]):
                problems.append(
                    f"{GAP_RELATIVE}: {key} = {gap_document.get(key)!r} ≠ 复算 {fresh[key]!r}"
                )
        for name in ("gap_three_step", "gap_no_readback", "mapped"):
            if gap_document.get(name) != fresh[name]:
                problems.append(f"{GAP_RELATIVE}: {name} 与复算不一致")
        keys = [row["key"] for row in gap_document.get("gap_three_step") or []]
        if len(keys) != len(set(keys)):
            problems.append(f"{GAP_RELATIVE}: gap_three_step 有重复 key")

    # ---- ② 接口层证据逐行与 `operations.py` 复算一致 ----
    document = load_evidence(repo)
    rows = document.get("paths") or []
    index = manifest_index(repo)
    if not isinstance(rows, list) or not rows:
        problems.append(f"{EVIDENCE_RELATIVE}: paths 为空")
        rows = []
    per_path: dict[str, int] = {}
    for row in rows:
        path = str(row.get("path"))
        endpoint = str(row.get("endpoint"))
        operation = str(row.get("operation"))
        tool = str(row.get("tool"))
        if path not in PATH_LABELS:
            problems.append(f"{endpoint}/{path}: 未知路径")
        if tool != TOOL_BY_OPERATION_PATH.get(path):
            problems.append(f"{endpoint}/{path}: tool = {tool!r} 与路径声明不符")
        step = _plan_step(repo, operation, endpoint)
        if step is None:
            problems.append(f"{endpoint}/{path}: {operation} 在 operations.py 里不引用该端点")
        else:
            if step["method"] != str(row.get("method")):
                problems.append(
                    f"{endpoint}/{path}: method = {row.get('method')!r} ≠ {step['method']!r}"
                )
            if step["tool"] != tool:
                problems.append(f"{endpoint}/{path}: tool ≠ operations.py 的 {step['tool']!r}")
        entry = index.get(endpoint)
        if entry is None:
            problems.append(f"{endpoint}: manifest 里没有该端点")
        elif str(row.get("uri")) != "/" + str(entry.get("uri") or "").lstrip("/"):
            problems.append(f"{endpoint}: uri = {row.get('uri')!r} ≠ manifest")
        status = str(row.get("status"))
        if status not in {PASSED, FAILED, LEFT_OUT, SKIPPED}:
            problems.append(f"{endpoint}/{path}: 未知 status {status!r}")
        if status == PASSED:
            per_path[path] = per_path.get(path, 0) + 1
            if not row.get("own_id"):
                problems.append(f"{endpoint}/{path}: PASSED 但没有自建编号")
            if not (row.get("recon") or {}).get("read_root_present"):
                problems.append(f"{endpoint}/{path}: PASSED 但只读侦察未确认解包链")
            if not (row.get("cleanup") or {}).get("gone"):
                problems.append(f"{endpoint}/{path}: PASSED 但删除 / 清理未确认")
            if path != PATH_DELETE and not (row.get("readback") or {}).get("present"):
                problems.append(f"{endpoint}/{path}: PASSED 但读回不在")
            if path == PATH_EDIT and not (row.get("edit") or {}).get("effective"):
                problems.append(f"{endpoint}/{path}: PASSED 但编辑未生效")
        if not row.get("requests"):
            problems.append(f"{endpoint}/{path}: 没有接口层实际发出的请求记录")
        if "MAPI-Key" in json.dumps(row.get("requests") or [], ensure_ascii=False):
            problems.append(f"{endpoint}/{path}: 请求记录里出现凭据字样")

    # ---- ③ 三条路径**各至少一条**端到端 PASSED（本轮任务 1）----
    for path in (PATH_ADD, PATH_EDIT, PATH_DELETE):
        if per_path.get(path, 0) < 1:
            problems.append(f"{path}: 没有一条 PASSED 的端到端证据（本轮任务 1 的硬要求）")

    # ---- ③' 计划内的每条路径都**取得结论**（无静默留缺）----
    covered = {(str(row.get("path")), str(row.get("endpoint"))) for row in rows}
    missing = [
        f"{item['path']}/{item['endpoint']}"
        for item in EXERCISES
        if (str(item["path"]), str(item["endpoint"])) not in covered
    ]
    if missing:
        problems.append(f"{EVIDENCE_RELATIVE}: 计划内仍有未取得结论的路径：{missing}")

    # ---- ④ 残留自洽 ----
    residue = document.get("residue") or {}
    allowed = set(document.get("allowed_residue") or ())
    for key in residue:
        if key not in allowed:
            problems.append(f"{EVIDENCE_RELATIVE}: 残留 {key} **未**披露")

    # ---- ⑤ 判据版本 / 声明自洽 ----
    if int(document.get("criterion_version") or 0) != CRITERION_VERSION:
        problems.append(f"{EVIDENCE_RELATIVE}: criterion_version 不符")
    if document.get("aborted"):
        problems.append(f"{EVIDENCE_RELATIVE}: aborted 非空（{document['aborted']}）")
    if sorted(document.get("sentinel_endpoints") or []) != sorted(
        {str(item["endpoint"]) for item in EXERCISES}
    ):
        problems.append(f"{EVIDENCE_RELATIVE}: 哨兵端点集 ≠ 全部被触碰的端点")

    # ---- ⑥ 读路径证据（P153；零写请求）----
    problems.extend(check_read(repo))

    if problems:
        print("❌ 接口层证据与数据侧不一致：")
        for item in problems:
            print(f"  - {item}")
        return 1
    read_document = load_read_evidence(repo)
    read_rows = read_document.get("paths") or []
    print(
        "✅ 接口层证据自洽：映射缺口与 `operations.py` 复算一致（缺口 "
        f"{len(gap_document.get('gap_three_step') or [])} + "
        f"{len(gap_document.get('gap_no_readback') or [])}）；"
        f"{len(rows)} 条写路径逐行与编排一致；三条路径各有 PASSED（{per_path}）；残留如实披露；"
        f"读路径 {len(read_rows)} 条零写请求（{read_document.get('counts')}）"
    )
    return 0


def summary(repo: pathlib.Path) -> int:
    """打印证据摘要（只读）。"""
    document = load_evidence(repo)
    rows = document.get("paths") or []
    print(f"接口层端到端证据：{len(rows)} 条 · 判据版本 {document.get('criterion_version')}")
    print(f"  实例：{document.get('instance')}")
    print(f"  计数：{document.get('counts')} · 按路径：{document.get('by_path')}")
    print(f"  中止：{document.get('aborted')!r} · 残留：{document.get('residue')}")
    for row in rows:
        print(
            f"  [{row.get('path_label')}] {row.get('tool')} / {row.get('operation')} → "
            f"{row.get('endpoint')} {row.get('method')} {row.get('uri')} = {row.get('status')}"
            f" {row.get('detail') or ''}"
        )
    gap = _read_json(repo / "registry" / GAP_RELATIVE)
    if gap:
        print(
            f"映射缺口：可写 {gap.get('write_capable_endpoints')} · 形态齐备 "
            f"{gap.get('three_step_endpoints')} · 已映射 {gap.get('mapped_endpoints')} · "
            f"缺口 {gap.get('gap_total')}（契约外 {len(gap.get('gap_three_step') or [])} / "
            f"无读回 {len(gap.get('gap_no_readback') or [])}）"
        )
    return 0


def read_summary(repo: pathlib.Path) -> int:
    """打印**读路径**证据摘要（只读）。"""
    document = load_read_evidence(repo)
    rows = document.get("paths") or []
    print(f"接口层读路径证据：{len(rows)} 条 · 判据版本 {document.get('criterion_version')}")
    print(f"  实例：{document.get('instance')}")
    print(f"  零写请求：{document.get('write_requests')} · 方法计数：{document.get('methods')}")
    print(f"  计数：{document.get('counts')} · 按 Tool：{document.get('by_tool')}")
    print(f"  中止：{document.get('aborted')!r} · 残留：{document.get('residue')}")
    for row in rows:
        print(
            f"  [{row.get('tool')}] {row.get('operation')} → {','.join(row.get('endpoints') or [])}"
            f" = {row.get('status')} http={row.get('http')} 读回={row.get('readback')}"
            f" {row.get('detail') or ''}"
        )
    return 0


# ===== CLI =====


def main(argv: list[str] | None = None) -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="P152/P153 接口层（app/ 适配层）写 / 读路径判据")
    parser.add_argument("--repo", default=REPO_DEFAULT, help="仓库根目录（默认当前目录）")
    parser.add_argument("--recon", action="store_true", help="离线：写映射缺口清单（零请求）")
    parser.add_argument("--probe", action="store_true", help="经 MCP Tool 契约端到端实测（写路径）")
    parser.add_argument("--probe-read", action="store_true", help="经 MCP Tool 契约实测读路径（零写）")
    parser.add_argument("--check", action="store_true", help="离线：断言证据与数据侧一致")
    parser.add_argument("--summary", action="store_true", help="打印写路径证据摘要")
    parser.add_argument("--read-summary", action="store_true", help="打印读路径证据摘要")
    parser.add_argument("--only", action="append", default=[], help="只跑这些端点 / Operation（可重复）")
    parser.add_argument("--path", action="append", default=[], help="只跑这些路径（add/edit/delete）")
    parser.add_argument("--limit", type=int, default=CHUNK_SIZE, help="本次最多跑多少条")
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE, help="每块条数（≤ 20）")
    parser.add_argument(
        "--allow-residue", action="append", default=[], help="显式放行**已披露**的残留端点"
    )
    args = parser.parse_args(argv)
    repo = pathlib.Path(args.repo).resolve()
    if args.recon:
        return recon(repo)
    if args.probe:
        return probe(
            repo,
            only=tuple(args.only),
            paths=tuple(args.path),
            limit=max(1, int(args.limit)),
            chunk_size=max(1, min(20, int(args.chunk_size))),
            allow_residue=tuple(args.allow_residue),
        )
    if args.probe_read:
        return probe_read(
            repo,
            only=tuple(args.only),
            limit=max(1, int(args.limit)),
            chunk_size=max(1, min(20, int(args.chunk_size))),
            allow_residue=tuple(args.allow_residue),
        )
    if args.check:
        return check(repo)
    if args.summary:
        return summary(repo)
    if args.read_summary:
        return read_summary(repo)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
