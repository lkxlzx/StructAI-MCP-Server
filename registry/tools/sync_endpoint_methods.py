#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同步端点 `methods`（P149：以 **live OPTIONS 实测**为真值来源）。

为什么需要这个工具
------------------
P149 的只读 OPTIONS 扫描（`--probe`，零副作用：只发 `OPTIONS`，必要时补一次 `HEAD`）拿到
每个端点的 `Allow` 头 —— 它就是该路由**真实**支持的方法集。与 registry 逐条比对的结果：

* `registry == live` **513** 个；
* `registry **少**声明` **90** 个（+DELETE 88 / +PUT 80 / +GET 62 / +POST 6）；
* `registry **多**声明` **0** 个（registry 只漏不夸）；
* `live` 路由不存在（无 `Allow`，`HEAD` 也 404）**72** 个 —— **不**改它们的 `methods`
  （它们仍是有据可查的端点定义；「本 build 不可得」只如实记录在证据文件与报告里）。

上游交叉验证：`MIDAS-API-Online-Manual/manual/midas Gen API 使用手册.md` 的 `Active Methods`
与 live `Allow` 在 **541** 个可比端点里 **532** 个完全一致（差异 9 条，逐条记录在报告里）。

用法（仓库根目录执行；本工具**只依赖标准库**）
--------------------------------------------
    # 1) 只读探测：用当前运行环境（MIDAS_BASE_URL / MIDAS_MAPI_KEY）重新生成证据文件
    python registry/tools/sync_endpoint_methods.py --probe

    # 2) 预演：按证据文件列出「改动前 → 改动后」（不写盘）
    python registry/tools/sync_endpoint_methods.py

    # 3) 写回端点定义（只改 `methods:` 一行，**不**动其它任何字段）
    python registry/tools/sync_endpoint_methods.py --write

    # 4) 断言：已落盘 == 机械结果（CI 用）
    python registry/tools/sync_endpoint_methods.py --check

纪律
----
* **只增不减**：只有当 live 方法集是 registry 方法集的**真超集**时才改；live 是子集时如实报出、
  **不**改（避免用一次探测把有据可查的方法集削掉）。
* **只改一行**：`methods: [...]` 的整行替换；其它字段（`availability` / `verified_on` /
  `products` / `enabled` / `risk`）**一律不动**。
* 404（无 `Allow`）的端点**不改**。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

EVIDENCE_RELATIVE = "live/live_methods.json"
MANIFEST_FILENAME = "manifest.json"
METHOD_ORDER = ("POST", "GET", "PUT", "DELETE", "PATCH")
METHOD_LINE = re.compile(r"^methods:\s*\[(?P<items>[^\]]*)\]\s*$")
PROBE_TIMEOUT_SECONDS = 30.0


# ===== 证据文件 =====


def load_evidence(repo: Path) -> dict[str, Any]:
    """读证据文件（`registry/live/live_methods.json`）。"""
    path = repo / "registry" / EVIDENCE_RELATIVE
    return json.loads(path.read_text(encoding="utf-8"))


def probe(repo: Path, base_url: str, api_key: str) -> dict[str, Any]:
    """只读 OPTIONS 扫描（必要时补一次 HEAD），生成证据文件内容。

    只发 `OPTIONS` / `HEAD` —— **零副作用**（不发任何写动词、不带 body）。
    """
    manifest = json.loads((repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    endpoints: dict[str, dict[str, Any]] = {}
    for entry in manifest["endpoints"]:
        key = str(entry["key"])
        uri = str(entry["uri"])
        allow = ""
        options_status = 0
        head_status = 0
        try:
            request = urllib.request.Request(base_url.rstrip("/") + uri, method="OPTIONS")
            request.add_header("MAPI-Key", api_key)
            with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT_SECONDS) as response:
                options_status = int(response.status)
                allow = response.headers.get("Allow") or ""
        except urllib.error.HTTPError as error:
            options_status = int(error.code)
            allow = error.headers.get("Allow") or ""
        except Exception:  # noqa: BLE001 - 连不上就如实记 0
            options_status = 0
        if not allow:
            try:
                request = urllib.request.Request(base_url.rstrip("/") + uri, method="HEAD")
                request.add_header("MAPI-Key", api_key)
                with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT_SECONDS) as response:
                    head_status = int(response.status)
            except urllib.error.HTTPError as error:
                head_status = int(error.code)
            except Exception:  # noqa: BLE001
                head_status = 0
        live = sorted(
            (part.strip().upper() for part in allow.split(",") if part.strip() and part.strip().upper() != "HEAD"),
            key=lambda method: METHOD_ORDER.index(method) if method in METHOD_ORDER else 99,
        )
        endpoints[key] = {
            "uri": uri,
            "live_methods": live,
            "options_status": options_status,
            "head_status": head_status,
        }
    return {
        "version": 1,
        "note": [
            "P149：端点方法集的**实测证据**（live `OPTIONS` 的 `Allow` 头 = 该路由真实支持的方法集）。",
            "只读：探测只发 `OPTIONS`，无 `Allow` 时补一次 `HEAD`；**不**发任何写动词、不带 body。",
            "用法：python registry/tools/sync_endpoint_methods.py --probe（重测）· --write（写回 methods）· --check（断言一致）。",
            "`live_methods` 为空 = 该路由在本实例上不存在（`HEAD` 亦 404）⇒ **不**改 `methods`，只如实记录。",
        ],
        "measured_on": {
            "instance": "gen-local (GEN NX)",
            "base_url": base_url.rstrip("/"),
            "method": "HTTP OPTIONS（零副作用）；无 Allow 时补 HEAD",
        },
        "endpoints": endpoints,
    }


# ===== 端点定义（YAML 的 methods 行）=====


def definition_paths(repo: Path) -> dict[str, str]:
    """key → 端点定义相对路径（取自 `registry/manifest.json` 的 `definition`）。"""
    manifest = json.loads((repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    return {str(entry["key"]): str(entry["definition"]) for entry in manifest["endpoints"]}


def current_methods(text: str) -> list[str] | None:
    """YAML 里的 `methods:` 行 → 方法列表（没有该行 → `None`）。"""
    for line in text.splitlines():
        match = METHOD_LINE.match(line)
        if match:
            return [part.strip().upper() for part in match.group("items").split(",") if part.strip()]
    return None


def render_methods(methods: list[str]) -> str:
    """方法列表 → `methods: [POST, GET, PUT, DELETE]`（固定顺序，与既有数据一致）。"""
    ordered = sorted(
        methods, key=lambda method: METHOD_ORDER.index(method) if method in METHOD_ORDER else 99
    )
    return "methods: [" + ", ".join(ordered) + "]"


def plan(repo: Path, evidence: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """计算「应改」与「如实报出但不改」两组（只读）。

    Returns:
        `(changes, notes)`：`changes` = 需要写回的行级改动；`notes` = 只报不改的（live 为子集 /
        live 路由不存在 / 端点定义缺 `methods:` 行）。
    """
    paths = definition_paths(repo)
    changes: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []
    for key, record in sorted(evidence["endpoints"].items()):
        relative = paths.get(key)
        if relative is None:
            notes.append({"key": key, "reason": "not_in_manifest"})
            continue
        path = repo / "registry" / relative
        text = path.read_text(encoding="utf-8")
        before = current_methods(text)
        live = list(record["live_methods"])
        if before is None:
            notes.append({"key": key, "reason": "definition_has_no_methods_line", "path": relative})
            continue
        if not live:
            notes.append({"key": key, "reason": "route_absent_on_this_build", "path": relative, "before": before})
            continue
        if set(live) == set(before):
            continue
        if not set(live) > set(before):
            notes.append(
                {
                    "key": key,
                    "reason": "live_is_not_a_superset",
                    "path": relative,
                    "before": before,
                    "live": live,
                }
            )
            continue
        changes.append(
            {
                "key": key,
                "path": relative,
                "before": before,
                "after": live,
                "line": render_methods(live),
            }
        )
    return changes, notes


def apply_changes(repo: Path, changes: list[dict[str, Any]]) -> int:
    """把 `changes` 写回端点定义（逐文件整行替换；当前值必须与预演一致）。"""
    written = 0
    for change in changes:
        path = repo / "registry" / change["path"]
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        replaced = False
        for index, line in enumerate(lines):
            match = METHOD_LINE.match(line.rstrip("\r\n"))
            if match is None:
                continue
            before = [part.strip().upper() for part in match.group("items").split(",") if part.strip()]
            if before != change["before"]:
                raise SystemExit(
                    f"{change['path']}: methods 行已变化（预期 {change['before']}，实际 {before}）—— 请重跑预演"
                )
            newline = "\n" if line.endswith("\n") else ""
            lines[index] = change["line"] + newline
            replaced = True
            break
        if not replaced:
            raise SystemExit(f"{change['path']}: 找不到 methods 行")
        path.write_text("".join(lines), encoding="utf-8")
        written += 1
    return written


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--probe", action="store_true", help="只读 OPTIONS 扫描并重写证据文件")
    parser.add_argument("--write", action="store_true", help="按证据文件写回端点定义的 methods")
    parser.add_argument("--check", action="store_true", help="断言已落盘 == 机械结果")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()

    if args.probe:
        base_url = os.environ.get("MIDAS_BASE_URL", "")
        api_key = os.environ.get("MIDAS_MAPI_KEY", "")
        if not base_url or not api_key:
            print("缺少 MIDAS_BASE_URL / MIDAS_MAPI_KEY（凭据只经环境变量）", file=sys.stderr)
            return 2
        document = probe(repo, base_url, api_key)
        target = repo / "registry" / EVIDENCE_RELATIVE
        target.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        total = len(document["endpoints"])
        absent = sum(1 for item in document["endpoints"].values() if not item["live_methods"])
        print(f"证据文件已写入 registry/{EVIDENCE_RELATIVE}：端点 {total}，路由不存在 {absent}")

    evidence = load_evidence(repo)
    changes, notes = plan(repo, evidence)
    print(f"证据文件 = registry/{EVIDENCE_RELATIVE}（端点 {len(evidence['endpoints'])}）")
    print(f"应改 methods = {len(changes)}；只报不改 = {len(notes)}")
    for change in changes:
        print(f"  {change['key']:40s} {change['before']} -> {change['after']}")
    for note in notes:
        print(f"  NOTE {note['key']}: {note['reason']}")

    if args.write:
        written = apply_changes(repo, changes)
        print(f"已写回 {written} 个端点定义")
    if args.check:
        pending = [change for change in changes]
        if pending:
            print(f"\n❌ 有 {len(pending)} 个端点定义与证据文件不一致（未写回）")
            return 1
        print("\n✅ 端点 methods 与证据文件一致（无待写回项）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
