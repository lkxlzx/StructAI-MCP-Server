#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P154：`DB.CONS` 的**请求体形状**裁决输入 —— 接口层产出的 `{"Assign": {"ITEMS": […]}}`
vs 数据侧实测可用的 `{"Assign": {"<编号>": <条目>}}`（**有界 A/B**）。

为什么需要这个工具（**R128 的证据**）
------------------------------------
P153 把 `DB.CONS` 归入 **R126** 的「取值缺口」（`GROUP_NAME` 未填 + `CONSTRAINT` 6 位 vs 手册 7 位）。
P154 把 `GROUP_NAME` 补上后接口层**仍然** `400 Wrong Field`；随后按 D2 的「先测后裁」做了
**位数 A/B**：**6 位与 7 位都被拒** ⇒ 位数**不是**成因。

真正的差异在**请求体形状**：

| 来源 | 请求体 |
| --- | --- |
| 接口层（`client.build_request` + `is_items_style()`） | `{"Assign": {"ITEMS": [{"ID": 1, …}]}}` |
| 数据侧实测可用（`probe_put_edits._wrap(SHAPE_ASSIGN_ITEM, body, own_id)`） | `{"Assign": {"1": {"ITEMS": [{"ID": 1, …}]}}}` |

⇒ 本工具用**有界 A/B** 判定哪一种形状被原生接受，并**读回**该编号是否真的落库
（只记**键名**，不记取值）。

判据（**先写清楚再动手**）
--------------------------
| 取值 | 判据 |
| --- | --- |
| `PASSED` | `POST /DB/CONS` 返回 `2xx` **且** 再读时该编号**在** |
| `FAILED` | 非 `2xx`（逐条留原生 `error.message` 前 200 字）或 `2xx` 但读回**不在** |

* **只碰自建编号**：编号 = 既有编号的 `max + 1`（专用空项目 ⇒ `1` …）。
* **跑前 / 跑后只读哨兵**：`GET /DB/NODE` + `GET /DB/CONS`；跑前非空 ⇒ **一个请求都不发**。
* **清理**：`DELETE /DB/CONS/{id}`（**必带路径 key**）→ `DELETE /DB/NODE/{id}`；
  以「**再读确认不在**」为准（R119：本 build 的 `DELETE` 会返回 `200` 并回显被删记录却**不真正删除**）。
* **有界**：**恰好 4** 个形状变体 + **1** 个前置节点；变体间**先清理再下一个**
  （因为外层键共用同一个节点编号 ⇒ 不清理会互相污染）⇒ 请求数 ≤ `MAX_REQUESTS`（**不**逐端点连发试探）。
* 证据里**绝不**出现凭据；**成功**响应**只**留**键名**（不记取值），**失败**响应只留
  `error.message` 前 200 字。

用法
----
    python registry/tools/probe_boundary_shape.py --probe     # 有界 A/B（需要 MIDAS_* 环境）
    python registry/tools/probe_boundary_shape.py --check     # 离线复算
    python registry/tools/probe_boundary_shape.py --summary
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
from typing import Any

import httpx

REPO_DEFAULT = "."
EVIDENCE_RELATIVE = "live/boundary_shape_probe.json"
CRITERION_VERSION = 1
PROBED_AT = "2026-10-11"
INSTANCE_ALIAS = "gen-local"
INSTANCE_PRODUCT = "GEN NX"

CONS_URI = "/DB/CONS"
NODE_URI = "/DB/NODE"
HEALTH_PATH = "/DB/NODE"
READ_ROOT = "CONS"
MAX_NATIVE_ERROR = 200
CONSTRAINT = "1111000"
"""手册示例的 7 位形态（位数**已由 P154 的位数 A/B 排除**，见模块 docstring）。"""

NONEXISTENT_NODE_KEY = "999999"
"""一个**不存在**的节点编号（用于验证「外层键无效 ⇒ 静默 `200` 而不落库」，见 R128）。"""


def _variants() -> tuple[dict[str, Any], ...]:
    """**恰好 4** 个形状变体（只改**包装形状**；位数固定为手册示例的 7 位）。

    ⚠️ **P154 的关键发现（R128）**：`DB.CONS` 的 `Assign` **外层键 = 该支承所在的节点编号**
    （不是任意自建编号）——
    `{"Assign": {"7": …}}`（节点 7 不存在）返回 **`200` 却什么都不建**，
    而 `{"Assign": {"1": …}}`（节点 1 存在）才真的落库。
    ⇒ 每个变体**必须**用一个**存在的**节点编号当外层键，否则 A/B 被**混淆**（P154 首轮即踩到）。
    """

    def item(node_id: str) -> dict[str, Any]:
        return {"ID": int(node_id), "GROUP_NAME": "", "CONSTRAINT": CONSTRAINT}

    return (
        {
            "name": "assign_items",
            "note": "**接口层当前**产出的形状（外层键是字面量 `ITEMS`）—— P152 / P154 均 `400`",
            "build": lambda node_id: {"Assign": {"ITEMS": [item(node_id)]}},
        },
        {
            "name": "assign_node_keyed_items",
            "note": "**数据侧实测可用**的形状：外层键 = **节点编号** + 内层再套 `ITEMS`（含 `ID`）",
            "build": lambda node_id: {"Assign": {node_id: {"ITEMS": [item(node_id)]}}},
        },
        {
            "name": "assign_node_keyed_items_no_id",
            "note": "同上但内层 `ITEMS` 条目**省略** `ID`（隔离「条目内 `ID` 是否必需」）",
            "build": lambda node_id: {
                "Assign": {
                    node_id: {"ITEMS": [{"GROUP_NAME": "", "CONSTRAINT": CONSTRAINT}]}
                }
            },
        },
        {
            "name": "assign_node_keyed_item",
            "note": "外层键 = **节点编号** + 条目**平铺**（**不**套 `ITEMS`）",
            "build": lambda node_id: {
                "Assign": {node_id: {"GROUP_NAME": "", "CONSTRAINT": CONSTRAINT}}
            },
        },
        {
            "name": "assign_nonexistent_node_key",
            "note": "外层键 = **不存在的**节点编号 ⇒ 预期**静默 `200` 而不落库**（假成功陷阱，R128）",
            "build": lambda node_id: {
                "Assign": {NONEXISTENT_NODE_KEY: {"ITEMS": [item(node_id)]}}
            },
        },
    )


VARIANTS: tuple[dict[str, Any], ...] = _variants()
"""**恰好 5** 个形状变体（判定点唯一：形状表只在本处声明）。"""

MAX_REQUESTS = 30
"""请求数上限（**有界**：1 个前置节点 + 5 × (创建 + 读回 + 删除 + 确认) + 哨兵）。"""


def _read_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


def _ids(client: httpx.Client, uri: str) -> tuple[str, ...]:
    """只读 `GET` → 既有**编号**（只认数字键）。"""
    response = client.get(uri)
    if response.status_code != 200:
        return ()
    try:
        payload = response.json()
    except ValueError:
        return ()
    root = payload.get(READ_ROOT) if uri == CONS_URI else next(iter(payload.values()), None)
    if not isinstance(root, dict):
        return ()
    nested = root.get("ITEMS")
    if isinstance(nested, list):
        return tuple(sorted(str(entry.get("ID")) for entry in nested if isinstance(entry, dict)))
    return tuple(sorted(str(key) for key in root if str(key).isdigit()))


def _entry_keys(client: httpx.Client, own_id: str) -> list[str]:
    """该编号的**键名**（**不**记取值；取不到 ⇒ 空）。

    ⚠️ `DB.CONS` 落库后的形态是 `{"CONS": {"<节点编号>": {"ITEMS": [<条目>]}}}` ⇒
    这里**下钻一层**取 `ITEMS[0]` 的键名，否则只会看到字面量 `ITEMS`（判不出条目内容）。
    """
    response = client.get(CONS_URI)
    if response.status_code != 200:
        return []
    try:
        payload = response.json()
    except ValueError:
        return []
    root = payload.get(READ_ROOT)
    if not isinstance(root, dict):
        return []
    entry = root.get(str(own_id))
    if not isinstance(entry, dict):
        return []
    nested = entry.get("ITEMS")
    if isinstance(nested, list):
        for candidate in nested:
            if isinstance(candidate, dict):
                return sorted(str(key) for key in candidate)
    return sorted(str(key) for key in entry)


def _next_id(client: httpx.Client, uri: str) -> str:
    """自建编号 = 既有编号的 `max + 1`（空 ⇒ `1`）。"""
    existing = [int(value) for value in _ids(client, uri) if str(value).isdigit()]
    return str(max(existing) + 1) if existing else "1"


def _sentinel(client: httpx.Client) -> dict[str, dict[str, Any]]:
    """跑前 / 跑后只读哨兵（只发 `GET`）。"""
    snapshot: dict[str, dict[str, Any]] = {}
    for uri in (NODE_URI, CONS_URI):
        try:
            response = client.get(uri)
        except Exception as error:  # noqa: BLE001 - 传输失败如实记录
            snapshot[uri] = {"status": 0, "ids": [], "error": type(error).__name__}
            continue
        snapshot[uri] = {"status": int(response.status_code), "ids": list(_ids(client, uri))}
    return snapshot


def probe(repo: pathlib.Path, *, allow_residue: tuple[str, ...] = ()) -> int:
    """有界形状 A/B（**只**碰自建编号；跑前 / 跑后只读哨兵；逆序清理 + 再读确认）。"""
    base_url = os.environ.get("MIDAS_BASE_URL", "").rstrip("/")
    key_value = os.environ.get("MIDAS_MAPI_KEY", "")
    if not base_url or not key_value:
        print("❌ --probe 需要 MIDAS_BASE_URL / MIDAS_MAPI_KEY（见 scripts/load-midas-env.ps1）")
        return 1

    requests: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    aborted = ""
    with httpx.Client(
        base_url=base_url, headers={"MAPI-Key": key_value}, timeout=60.0
    ) as client:
        before = _sentinel(client)
        blocked = {
            uri: value["ids"]
            for uri, value in before.items()
            if value.get("ids") and uri not in allow_residue
        }
        if blocked:
            aborted = f"跑前哨兵**非空** ⇒ 一个请求都不发（{blocked}）"
            print(f"⚠️ {aborted}")
            return _write(repo, rows, before, before, requests, aborted, allow_residue)
        # ⚠️ **P155 加固（实测事故驱动）**：哨兵**读不到**（实例不可达）⇒ **绝不盲写**。
        unreadable = sorted(
            uri
            for uri, value in before.items()
            if int(value.get("status") or 0) == 0 or value.get("error")
        )
        if unreadable:
            aborted = f"跑前哨兵**不可读**（实例不可达 / 传输失败）⇒ 一个请求都不发：{unreadable}"
            print(f"⚠️ {aborted}")
            return _write(repo, rows, before, before, requests, aborted, allow_residue)

        node_id = _next_id(client, NODE_URI)
        node_body = {"Assign": {node_id: {"X": 0.0, "Y": 0.0, "Z": 0.0}}}
        node_response = client.post(NODE_URI, json=node_body)
        requests.append(
            {
                "method": "POST",
                "path": NODE_URI,
                "status": int(node_response.status_code),
                "body": node_body,
            }
        )
        node_ok = 200 <= node_response.status_code < 300

        # ---- 每个变体：同一节点当外层键 ⇒ 变体间**必须**先清理再下一个（隔离变量）----
        for variant in VARIANTS:
            body = variant["build"](node_id)
            response = client.post(CONS_URI, json=body)
            status = int(response.status_code)
            record: dict[str, Any] = {
                "method": "POST",
                "path": CONS_URI,
                "status": status,
                "body": body,
            }
            if status >= 400:
                record["native_error"] = response.text[:MAX_NATIVE_ERROR]
            requests.append(record)
            keys = _entry_keys(client, node_id) if 200 <= status < 300 else []
            created = bool(keys)
            removed: dict[str, Any] = {}
            if 200 <= status < 300:
                uri = f"{CONS_URI}/{node_id}"
                delete_response = client.delete(uri)
                requests.append(
                    {"method": "DELETE", "path": uri, "status": int(delete_response.status_code)}
                )
                removed = {
                    "uri": uri,
                    "status": int(delete_response.status_code),
                    "gone": node_id not in _ids(client, CONS_URI),
                }
            rows.append(
                {
                    "name": str(variant["name"]),
                    "note": str(variant["note"]),
                    "outer_key": node_id,
                    "http": status,
                    "created": created,
                    "readback_keys": keys,
                    "cleanup": removed,
                    "status": "PASSED" if (200 <= status < 300 and created) else "FAILED",
                    "native_error": record.get("native_error", ""),
                }
            )
            print(
                f"  {variant['name']:30s} → {status} 落库={created} 读回键={keys}"
            )

        # ---- 收尾：删前置节点（**必带路径 key**；以再读确认为准）----
        cleanup: list[dict[str, Any]] = []
        if node_ok:
            uri = f"{NODE_URI}/{node_id}"
            response = client.delete(uri)
            requests.append({"method": "DELETE", "path": uri, "status": int(response.status_code)})
            cleanup.append(
                {
                    "uri": uri,
                    "status": int(response.status_code),
                    "gone": node_id not in _ids(client, NODE_URI),
                }
            )
        for row in rows:
            item = row.get("cleanup") or {}
            if item:
                cleanup.append(item)

        after = _sentinel(client)
        residue = {uri: value["ids"] for uri, value in after.items() if value.get("ids")}
        try:
            health = int(client.get(HEALTH_PATH).status_code)
        except Exception as error:  # noqa: BLE001 - 传输失败如实中止（**不**让异常把整批打崩）
            aborted = f"健康检查 {HEALTH_PATH} **传输失败**（{type(error).__name__}）⇒ 立即中止"
            print(f"  ⚠️ {aborted}")
            health = 0
    return _write(
        repo, rows, before, after, requests, aborted, allow_residue, residue, cleanup, health
    )


def _verdict(rows: list[dict[str, Any]]) -> str:
    """结论：被接受且读回在的形状（升序、逗号分隔；无 ⇒ `none_accepted`）。"""
    accepted = sorted(str(row["name"]) for row in rows if str(row["status"]) == "PASSED")
    return ",".join(accepted) if accepted else "none_accepted"


def _write(
    repo: pathlib.Path,
    rows: list[dict[str, Any]],
    before: dict[str, Any],
    after: dict[str, Any],
    requests: list[dict[str, Any]],
    aborted: str,
    allow_residue: tuple[str, ...],
    residue: dict[str, Any] | None = None,
    cleanup: list[dict[str, Any]] | None = None,
    health: int = 0,
) -> int:
    """落证据并给出结论。"""
    residue = residue if residue is not None else {}
    cleanup = cleanup if cleanup is not None else []
    counts: dict[str, int] = {}
    for row in rows:
        counts[str(row["status"])] = counts.get(str(row["status"]), 0) + 1
    document = {
        "note": [
            "P154 / **R128 的裁决输入**：`DB.CONS` 的**请求体形状** A/B —— "
            "**同一端点、同一字段集、同一位数**（`1111000`），**只改包装形状**。",
            "背景：P153 把 `DB.CONS` 归入 R126 的「取值缺口」；P154 补上 `GROUP_NAME` 后仍 `400`，"
            "**位数 A/B 也已排除位数**（6 位 / 7 位**都**被拒）⇒ 成因是**形状**：接口层发 "
            "`{\"Assign\": {\"ITEMS\": […]}}`，而数据侧实测可用的是 `{\"Assign\": {\"<编号>\": <条目>}}`。",
            "判定：`PASSED` = `2xx` **且**再读时该编号**在**（只记**键名**，不记取值）；"
            "`FAILED` = 非 `2xx`，或 `2xx` 但**没落库**"
            "（⚠️ `Assign` 的外层键**不是**存在的节点编号时，原生会**静默 `200` 而不建**）。",
            "纪律：只碰自建编号 · `DELETE` 必带路径 key · 删除以「再读确认不在」为准（R119）· "
            "跑前 / 跑后只读哨兵 · **恰好 4** 个形状变体 + **1** 个前置节点"
            f"（请求数 ≤ {MAX_REQUESTS}，有界，**不**逐端点连发试探）。",
            "证据里**绝不**出现凭据；**成功**响应只留**键名**，**失败**响应只留 `error.message` 前 200 字。",
            "生成器 = `registry/tools/probe_boundary_shape.py --probe`。",
        ],
        "criterion_version": CRITERION_VERSION,
        "instance": {
            "alias": INSTANCE_ALIAS,
            "product": INSTANCE_PRODUCT,
            "base_url": os.environ.get("MIDAS_BASE_URL", ""),
            "probed_at": PROBED_AT,
        },
        "constraint": CONSTRAINT,
        "variants": rows,
        "counts": counts,
        "verdict": _verdict(rows),
        "aborted": aborted,
        "health_status": health,
        "sentinel_before": before,
        "sentinel_after": after,
        "cleanup": cleanup,
        "residue": residue,
        "allowed_residue": sorted(allow_residue),
        "requests": requests,
    }
    path = repo / "registry" / EVIDENCE_RELATIVE
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    undisclosed = {uri for uri in residue if uri not in allow_residue}
    print(
        "verdict =",
        document["verdict"],
        " counts =",
        counts,
        " 中止 =",
        bool(aborted),
        " 残留 =",
        sorted(residue),
        " 未披露残留 =",
        sorted(undisclosed),
    )
    print(f"已写入 registry/{EVIDENCE_RELATIVE}")
    return 1 if (aborted or undisclosed) else 0


def check(repo: pathlib.Path) -> int:
    """离线断言：证据自洽（5 个变体 · `PASSED` 必有读回键 · 清理已确认 · 结论与数据一致）。"""
    document = _read_json(repo / "registry" / EVIDENCE_RELATIVE)
    if not document:
        print(f"❌ 缺证据 registry/{EVIDENCE_RELATIVE}（先跑 --probe）")
        return 1
    problems: list[str] = []
    if int(document.get("criterion_version") or 0) != CRITERION_VERSION:
        problems.append(f"{EVIDENCE_RELATIVE}: criterion_version 不符")
    rows = document.get("variants") or []
    if [str(row["name"]) for row in rows] != [str(item["name"]) for item in VARIANTS]:
        problems.append(f"{EVIDENCE_RELATIVE}: 变体集 ≠ 声明（判定点唯一）")
    if str(document.get("constraint") or "") != CONSTRAINT:
        problems.append(f"{EVIDENCE_RELATIVE}: 位数不是 {CONSTRAINT}（位数已排除，**必须**固定）")
    for row in rows:
        http = int(row["http"])
        expected = "PASSED" if (200 <= http < 300 and row.get("created")) else "FAILED"
        if str(row["status"]) != expected:
            problems.append(f"{row['name']}: status 与 http / 落库不符")
        if expected == "FAILED" and http >= 400 and not str(row.get("native_error") or ""):
            problems.append(f"{row['name']}: 原生拒绝但没有原生原因")
        if expected == "FAILED" and 200 <= http < 300 and row.get("created"):
            problems.append(f"{row['name']}: `200` 且已落库却判 `FAILED`")
        if expected == "PASSED" and row.get("native_error"):
            problems.append(f"{row['name']}: PASSED 却留了原生原文")
        if expected == "PASSED" and not (row.get("cleanup") or {}).get("gone"):
            problems.append(f"{row['name']}: PASSED 但该编号的清理未确认")
        for item in row.get("readback_keys") or []:
            if not isinstance(item, str):
                problems.append(f"{row['name']}: 读回键名不是字符串")
    if len(document.get("requests") or []) > MAX_REQUESTS:
        problems.append(
            f"{EVIDENCE_RELATIVE}: 请求数 {len(document['requests'])} > {MAX_REQUESTS}（有界性被破）"
        )
    for item in document.get("cleanup") or []:
        if not item.get("gone"):
            problems.append(f"清理未确认：{item.get('uri')}")
    if document.get("sentinel_before") != document.get("sentinel_after"):
        problems.append(f"{EVIDENCE_RELATIVE}: 跑前 / 跑后哨兵不一致")
    if document.get("aborted"):
        problems.append(f"{EVIDENCE_RELATIVE}: aborted 非空（{document['aborted']}）")
    allowed = set(document.get("allowed_residue") or ())
    for uri in document.get("residue") or {}:
        if uri not in allowed:
            problems.append(f"{EVIDENCE_RELATIVE}: 残留 {uri} **未**披露")
    if problems:
        print("❌ `DB.CONS` 形状证据不自洽：")
        for item in problems:
            print(f"  - {item}")
        return 1
    print(
        f"✅ `DB.CONS` 形状证据自洽：{len(rows)} 个变体（{document.get('counts')}）· "
        f"结论 = `{document.get('verdict')}` · 清理已逐条确认 · 残留如实披露"
    )
    return 0


def summary(repo: pathlib.Path) -> int:
    """打印摘要（只读）。"""
    document = _read_json(repo / "registry" / EVIDENCE_RELATIVE)
    if not document:
        print(f"❌ 缺证据 registry/{EVIDENCE_RELATIVE}（先跑 --probe）")
        return 1
    print(f"`DB.CONS` 请求体形状 A/B：判据版本 {document.get('criterion_version')}")
    print(f"  实例：{document.get('instance')}")
    print(f"  计数：{document.get('counts')} · **结论 = {document.get('verdict')}**")
    for row in document.get("variants") or []:
        print(
            f"  {row['name']:28s} → {row['http']} {row['status']} "
            f"读回键={row.get('readback_keys')} {row.get('native_error') or ''}"
        )
    print(f"  清理：{document.get('cleanup')} · 残留：{document.get('residue')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="P154：DB.CONS 请求体形状 A/B（R128）")
    parser.add_argument("--repo", default=REPO_DEFAULT, help="仓库根目录（默认当前目录）")
    parser.add_argument("--probe", action="store_true", help="有界 A/B（需要 MIDAS_* 环境）")
    parser.add_argument("--check", action="store_true", help="离线：断言证据自洽")
    parser.add_argument("--summary", action="store_true", help="打印摘要")
    parser.add_argument("--allow-residue", action="append", default=[], help="显式放行已披露的残留")
    args = parser.parse_args(argv)
    repo = pathlib.Path(args.repo).resolve()
    if args.probe:
        return probe(repo, allow_residue=tuple(args.allow_residue))
    if args.check:
        return check(repo)
    if args.summary:
        return summary(repo)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
