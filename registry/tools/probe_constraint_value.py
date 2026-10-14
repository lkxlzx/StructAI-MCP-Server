#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P156：`DB.CONS` 的 `CONSTRAINT` **取值要求**的裁决输入 —— 位数 / 自由度的**有界 A/B**。

为什么需要这个工具（**R128 的连带面 + D2 的更正**）
--------------------------------------------------
P154 的「位数 A/B」结论是「**位数不是成因**」—— ⚠️ **该结论是错的**：那次 A/B 的**三个变体都用了
当时（未修）的请求体形状** `{"Assign": {"ITEMS": […]}}`，而该形状**无论位数都会被 `400` 拒**
⇒ 位数这个变量被**形状**混淆了（confounded）。

P155 修好**形状**（外层编号键）之后，P156 重跑：接口层仍 `400`，但原生文案从
`Wrong Field`（形状级）变成 **`[错误] 约束条件输入有错误。`**（**取值级**）⇒ 必须**重测位数**。

本工具用**已修的正确形状**（`{"Assign": {"<节点编号>": {"ITEMS": [<条目>]}}}`）逐条测
`CONSTRAINT` 的**长度 / 取值**，并**读回**该编号是否真的落库（只记**键名**，不记取值）。

判据（**先写清楚再动手**）
--------------------------
| 取值 | 判据 |
| --- | --- |
| `PASSED` | `POST /DB.CONS` 返回 `2xx` **且** 再读时该编号**在** |
| `FAILED` | 非 `2xx`（逐条留原生 `error.message` 前 200 字），或 `2xx` 但读回**不在** |

* **只碰自建编号**：节点编号 = 既有编号的 `max + 1`（专用空项目 ⇒ `1`）。
* **跑前 / 跑后只读哨兵**：`GET /DB/NODE` + `GET /DB/CONS`；**读不到 ⇒ 一个请求都不发**（P155 加固）。
* **变体间先清理再下一个**（同一个节点编号当外层键 ⇒ 不清理会互相污染）。
* **清理**：`DELETE /DB/CONS/{id}`（**必带路径 key**）→ `DELETE /DB/NODE/{id}`；以「**再读确认不在**」为准（R119）。
* **有界**：**恰好 4** 个变体 + **1** 个前置节点 ⇒ 请求数 ≤ `MAX_REQUESTS`（**不**逐端点连发试探）。
* 证据里**绝不**出现凭据；**成功**响应**只**留**键名**，**失败**响应只留 `error.message` 前 200 字。

用法
----
    python registry/tools/probe_constraint_value.py --probe     # 有界 A/B（需要 MIDAS_* 环境）
    python registry/tools/probe_constraint_value.py --check     # 离线复算
    python registry/tools/probe_constraint_value.py --summary
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from typing import Any

import httpx

REPO_DEFAULT = "."
EVIDENCE_RELATIVE = "live/constraint_value_probe.json"
CRITERION_VERSION = 1
PROBED_AT = "2026-10-11"
INSTANCE_ALIAS = "gen-local"
INSTANCE_PRODUCT = "GEN NX"

CONS_URI = "/DB/CONS"
NODE_URI = "/DB/NODE"
HEALTH_PATH = "/DB/NODE"
READ_ROOT = "CONS"
MAX_NATIVE_ERROR = 200
MAX_REQUESTS = 26

VARIANTS: tuple[dict[str, Any], ...] = (
    {
        "name": "six_digits",
        "constraint": "111000",
        "note": (
            "**P156 时点**接口层产出（canonical 只覆盖六个自由度 `ux..rz`；`RW` 明确不臆造）"
            " —— ⚠️ **P157 / D2 = A 起**接口层产出 **7** 位（本变体保留为「6 位被拒」的对照）"
        ),
    },
    {
        "name": "five_digits_control",
        "constraint": "11100",
        "note": "对照：更短（隔离「长度」这一变量）",
    },
    {
        "name": "seven_digits_rw0",
        "constraint": "1110000",
        "note": "六自由度 + 第 7 位 `RW = 0`（**不**约束翘曲）",
    },
    {
        "name": "seven_digits_rx1",
        "constraint": "1111000",
        "note": "**手册示例**的取值（`registry/live/write_templates.json` 的 `DB.CONS.body`）",
    },
)
"""**恰好 4** 个变体（只改 `CONSTRAINT` 的**长度 / 取值**；形状**固定**为已修的编号键控形态）。"""


def _read_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


def _ids(client: httpx.Client, uri: str, root_key: str) -> tuple[str, ...]:
    """只读 `GET` → 既有**编号**（只认数字键）。"""
    response = client.get(uri)
    if response.status_code != 200:
        return ()
    try:
        payload = response.json()
    except ValueError:
        return ()
    root = payload.get(root_key)
    if not isinstance(root, dict):
        return ()
    nested = root.get("ITEMS")
    if isinstance(nested, list):
        return tuple(sorted(str(item.get("ID")) for item in nested if isinstance(item, dict)))
    return tuple(sorted(str(key) for key in root if str(key).isdigit()))


def _entry_keys(client: httpx.Client, own_id: str) -> list[str]:
    """该编号的**键名**（**不**记取值）。"""
    response = client.get(CONS_URI)
    if response.status_code != 200:
        return []
    try:
        root = response.json().get(READ_ROOT)
    except ValueError:
        return []
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


def _sentinel(client: httpx.Client) -> dict[str, dict[str, Any]]:
    """跑前 / 跑后只读哨兵（只发 `GET`）。"""
    snapshot: dict[str, dict[str, Any]] = {}
    for uri, root_key in ((NODE_URI, "NODE"), (CONS_URI, READ_ROOT)):
        try:
            response = client.get(uri)
        except Exception as error:  # noqa: BLE001 - 传输失败如实记录
            snapshot[uri] = {"status": 0, "ids": [], "error": type(error).__name__}
            continue
        snapshot[uri] = {"status": int(response.status_code), "ids": list(_ids(client, uri, root_key))}
    return snapshot


def probe(repo: pathlib.Path, *, allow_residue: tuple[str, ...] = ()) -> int:
    """有界 A/B（**只**碰自建编号；跑前 / 跑后只读哨兵；变体间清理 + 再读确认）。"""
    base_url = os.environ.get("MIDAS_BASE_URL", "").rstrip("/")
    key_value = os.environ.get("MIDAS_MAPI_KEY", "")
    if not base_url or not key_value:
        print("❌ --probe 需要 MIDAS_BASE_URL / MIDAS_MAPI_KEY（见 scripts/load-midas-env.ps1）")
        return 1

    requests: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    cleanup: list[dict[str, Any]] = []
    aborted = ""
    with httpx.Client(base_url=base_url, headers={"MAPI-Key": key_value}, timeout=60.0) as client:
        before = _sentinel(client)
        unreadable = sorted(
            uri
            for uri, value in before.items()
            if int(value.get("status") or 0) == 0 or value.get("error")
        )
        if unreadable:
            aborted = f"跑前哨兵**不可读**（实例不可达 / 传输失败）⇒ 一个请求都不发：{unreadable}"
            print(f"⚠️ {aborted}")
            return _write(repo, rows, before, before, requests, aborted, allow_residue)
        blocked = {
            uri: value["ids"]
            for uri, value in before.items()
            if value.get("ids") and uri not in allow_residue
        }
        if blocked:
            aborted = f"跑前哨兵**非空** ⇒ 一个请求都不发（{blocked}）"
            print(f"⚠️ {aborted}")
            return _write(repo, rows, before, before, requests, aborted, allow_residue)

        existing = [int(v) for v in _ids(client, NODE_URI, "NODE") if str(v).isdigit()]
        node_id = str(max(existing) + 1) if existing else "1"
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

        for variant in VARIANTS:
            constraint = str(variant["constraint"])
            body = {
                "Assign": {
                    node_id: {
                        "ITEMS": [
                            {"ID": int(node_id), "GROUP_NAME": "", "CONSTRAINT": constraint}
                        ]
                    }
                }
            }
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
                deleted = client.delete(uri)
                requests.append(
                    {"method": "DELETE", "path": uri, "status": int(deleted.status_code)}
                )
                gone = node_id not in _ids(client, CONS_URI, READ_ROOT)
                removed = {"uri": uri, "status": int(deleted.status_code), "gone": gone}
                cleanup.append(removed)
            rows.append(
                {
                    "name": str(variant["name"]),
                    "note": str(variant["note"]),
                    "constraint": constraint,
                    "length": len(constraint),
                    "outer_key": node_id,
                    "http": status,
                    "created": created,
                    "readback_keys": keys,
                    "cleanup": removed,
                    "status": "PASSED" if (200 <= status < 300 and created) else "FAILED",
                    "native_error": record.get("native_error", ""),
                }
            )
            print(f"  {variant['name']:22s} CONSTRAINT={constraint!r}({len(constraint)}) → {status} 落库={created}")

        if node_ok:
            uri = f"{NODE_URI}/{node_id}"
            deleted = client.delete(uri)
            requests.append({"method": "DELETE", "path": uri, "status": int(deleted.status_code)})
            cleanup.append(
                {
                    "uri": uri,
                    "status": int(deleted.status_code),
                    "gone": node_id not in _ids(client, NODE_URI, "NODE"),
                }
            )
        after = _sentinel(client)
        residue = {uri: value["ids"] for uri, value in after.items() if value.get("ids")}
        try:
            health = int(client.get(HEALTH_PATH).status_code)
        except Exception as error:  # noqa: BLE001 - 传输失败如实中止
            aborted = f"健康检查 {HEALTH_PATH} **传输失败**（{type(error).__name__}）⇒ 立即中止"
            print(f"  ⚠️ {aborted}")
            health = 0
    return _write(
        repo, rows, before, after, requests, aborted, allow_residue, residue, cleanup, health
    )


def _verdict(rows: list[dict[str, Any]]) -> str:
    """结论：被接受的**长度**（升序、逗号分隔；无 ⇒ `none_accepted`）。"""
    lengths = sorted({int(row["length"]) for row in rows if str(row["status"]) == "PASSED"})
    return ",".join(str(value) for value in lengths) if lengths else "none_accepted"


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
            "P156：`DB.CONS` 的 `CONSTRAINT` **取值要求**的裁决输入 —— 位数 / 自由度的有界 A/B。",
            "⚠️ **更正 P154 的 D2 结论**：P154 那次「位数 A/B」的**三个变体都用了当时（未修）的形状** "
            "`{\"Assign\": {\"ITEMS\": […]}}`，而该形状**无论位数都被 `400` 拒** ⇒ 位数被**形状混淆**，"
            "「位数不是成因」**不成立**。本工具用**已修的正确形状**（外层**编号键**）重测。",
            "判定：`PASSED` = `2xx` **且**再读时该编号**在**（只记**键名**，不记取值）；"
            "`FAILED` = 非 `2xx`，或 `2xx` 但**没落库**。",
            "纪律：只碰自建编号 · `DELETE` 必带路径 key · 删除以「再读确认不在」为准（R119）· "
            "跑前 / 跑后只读哨兵（**读不到就不盲写**）· **变体间先清理** · "
            f"**恰好 {len(VARIANTS)}** 个变体 + **1** 个前置节点（请求数 ≤ {MAX_REQUESTS}）。",
            "证据里**绝不**出现凭据；**成功**响应只留**键名**，**失败**响应只留 `error.message` 前 200 字。",
            "生成器 = `registry/tools/probe_constraint_value.py --probe`（**零** `app/**` 改动）。",
        ],
        "criterion_version": CRITERION_VERSION,
        "instance": {
            "alias": INSTANCE_ALIAS,
            "product": INSTANCE_PRODUCT,
            "base_url": os.environ.get("MIDAS_BASE_URL", ""),
            "probed_at": PROBED_AT,
        },
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
    if aborted and path.is_file():
        print(f"⚠️ 本次中止（{aborted[:80]}）⇒ **不覆盖**既有证据 registry/{EVIDENCE_RELATIVE}")
    else:
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
    """离线断言：证据自洽（变体集 · 长度与取值一致 · 清理确认 · 结论与数据一致）。"""
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
    for row in rows:
        if len(str(row["constraint"])) != int(row["length"]):
            problems.append(f"{row['name']}: length 与取值不符")
        http = int(row["http"])
        expected = "PASSED" if (200 <= http < 300 and row.get("created")) else "FAILED"
        if str(row["status"]) != expected:
            problems.append(f"{row['name']}: status 与 http / 落库不符")
        if expected == "FAILED" and http >= 400 and not str(row.get("native_error") or ""):
            problems.append(f"{row['name']}: 原生拒绝但没有原生原因")
        if expected == "PASSED" and row.get("native_error"):
            problems.append(f"{row['name']}: PASSED 却留了原生原文")
        if expected == "PASSED" and not (row.get("cleanup") or {}).get("gone"):
            problems.append(f"{row['name']}: PASSED 但该编号的清理未确认")
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
    if len(document.get("requests") or []) > MAX_REQUESTS:
        problems.append(f"{EVIDENCE_RELATIVE}: 请求数 {len(document['requests'])} > {MAX_REQUESTS}")
    if problems:
        print("❌ `CONSTRAINT` 取值证据不自洽：")
        for item in problems:
            print(f"  - {item}")
        return 1
    print(
        f"✅ `CONSTRAINT` 取值证据自洽：{len(rows)} 个变体（{document.get('counts')}）· "
        f"被接受的长度 = `{document.get('verdict')}` · 清理逐条确认 · 残留如实披露"
    )
    return 0


def summary(repo: pathlib.Path) -> int:
    """打印摘要（只读）。"""
    document = _read_json(repo / "registry" / EVIDENCE_RELATIVE)
    if not document:
        print(f"❌ 缺证据 registry/{EVIDENCE_RELATIVE}（先跑 --probe）")
        return 1
    print(f"`DB.CONS` 的 `CONSTRAINT` 取值 A/B：判据版本 {document.get('criterion_version')}")
    print(f"  实例：{document.get('instance')}")
    print(f"  计数：{document.get('counts')} · **被接受的长度 = {document.get('verdict')}**")
    for row in document.get("variants") or []:
        print(
            f"  {row['name']:22s} {row['constraint']!r}({row['length']}) → {row['http']} "
            f"{row['status']} {row.get('native_error') or ''}"
        )
    print(f"  清理：{document.get('cleanup')} · 残留：{document.get('residue')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="P156：DB.CONS 的 CONSTRAINT 取值 A/B（D2 更正）")
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
    # Windows 控制台默认 cp949/cp936：本工具会打印中文/符号，不重设编码会 UnicodeEncodeError。
    # ⚠️ 必须在 `__main__` 块内：测试用 `exec_module()` 装载本模块，模块级调用会改写
    #    **pytest 的捕获流**，破坏其后所有用例的 capture。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
