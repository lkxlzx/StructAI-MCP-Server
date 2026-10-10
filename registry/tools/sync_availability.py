#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按**只读** L4 实测收口 `availability`（P149-C / R111 的恢复条件）。

为什么需要这个工具
------------------
`availability` 的语义是**实测可用性**：`registry/README.md` §4 ——「`availability == verified`
（**至少一个实例 GET 成功**）」。而写路径三步链的**第 1 步**（只读 `LIST`）会被
`client.guard_verified()` 拦下：`verification_status != VERIFIED` → `registry_mapping_not_verified`
（`app/infrastructure/adapters/midas/client.py`）。故 `availability: untested` 的写端点**根本无法**进入
写路径实测 —— R111 记录的 **49** 个 `DESIGN.*` 正是被这一条卡住。

恢复条件 = **先做只读 L4 实测**（零副作用）再据实收口。本工具把这一步**机械化 + 可复算**：

1. `--probe`：对「未验证（`availability != verified`）∧ 有 `GET` ∧ 有 `read_root`」的端点逐条
   发**只读** `GET`，判据与 P134 的 L4 同一口径 —— **响应顶层键 == `read_root`** ⇒ `PASSED`
   （块非空）/ `PARTIAL`（块为空，空项目下的正常形态）；非 200 或顶层键不符 ⇒ `FAILED`。
   结果落 `registry/live/live_read_probe.json`（含实例别名 / 产品 / 日期；**不含任何凭据**）。
2. `--write`：把证据里 `PASSED` / `PARTIAL` 的端点**只升不降**地收口到 YAML ——
   `availability: verified` + `verified_on` 合并进该实例别名（已 `verified` 的不动、
   `unverified` 的**不**动）。改完请跑 `registry/tools/sync_manifest.py --write` 重派生 manifest。
3. `--check`：断言「证据里可用的端点 ⇒ YAML 已 `verified` 且 `verified_on` 含该别名」，否则退出码 1。

用法（仓库根目录执行；`--probe` 需要 `MIDAS_BASE_URL` / `MIDAS_MAPI_KEY`）
--------------------------------------------------------------------
    # 只读实测（可只测一部分：--only KEY1,KEY2）
    python registry/tools/sync_availability.py --probe
    python registry/tools/sync_availability.py --probe --only DESIGN.RC.DRC,DB.REBB

    # 据证据收口 YAML（只升不降）
    python registry/tools/sync_availability.py --write

    # 断言一致（CI 用）
    python registry/tools/sync_availability.py --check

纪律
----
* **只发 `GET`**（零副作用）：本工具**不**构造、**不**发送任何写请求。
* **只升不降**：`availability` 只会 `untested → verified`；`unverified`（实测不可用）与
  `unavailable_on` **一律不碰** —— 「不可用」的判定需要另一方向的证据。
* **不臆造**：只对**实际拿到 200 且顶层键 == `read_root`** 的端点收口；`FAILED` 的如实留在原地。
* 证据文件与 YAML 里**绝不**出现凭据（`MAPI-Key` 只经环境变量注入）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_DEFAULT = "."
EVIDENCE_RELATIVE = "live/live_read_probe.json"
MANIFEST_FILENAME = "manifest.json"
INSTANCE_ALIAS = "gen-local"
INSTANCE_PRODUCT = "GEN_NX"
PROBED_AT = "2026-10-10"
VERIFIED = "verified"
UPGRADABLE = ("PASSED", "PARTIAL")


def _load_yaml_module() -> Any:
    """PyYAML（仓库既有依赖，不新增）。"""
    import yaml  # noqa: PLC0415

    return yaml


def endpoint_files(repo: Path) -> dict[str, Path]:
    """`key → YAML 路径`（按 `manifest.json` 的 `definition` 字段，唯一权威）。"""
    manifest = json.loads((repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    return {
        str(item["key"]): repo / "registry" / str(item["definition"]) for item in manifest["endpoints"]
    }


def read_availability(path: Path) -> tuple[str, list[str]]:
    """YAML 里的 `(availability, verified_on)`。"""
    yaml = _load_yaml_module()
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    verified_on = document.get("verified_on") or []
    return str(document.get("availability") or ""), [str(item) for item in verified_on]


def probe_targets(repo: Path, only: tuple[str, ...]) -> list[str]:
    """默认目标 = 「`availability != verified` ∧ 有 `GET` ∧ 有 `read_root` ∧ 已启用」的端点。"""
    files = endpoint_files(repo)
    manifest = json.loads((repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    selected: list[str] = []
    for item in manifest["endpoints"]:
        key = str(item["key"])
        if only and key not in only:
            continue
        if not bool(item.get("enabled", True)):
            continue
        methods = {part.strip().upper() for part in str(item.get("methods") or "").split(",")}
        if "GET" not in methods:
            continue
        if not str((item.get("wrapper") or {}).get("read_root") or ""):
            continue
        availability, _ = read_availability(files[key])
        if availability == VERIFIED:
            continue
        selected.append(key)
    return sorted(selected)


def probe(repo: Path, only: tuple[str, ...]) -> int:
    """只读 L4 实测 → 证据文件（零副作用）。"""
    import httpx  # noqa: PLC0415

    base = os.environ.get("MIDAS_BASE_URL", "").rstrip("/")
    key_value = os.environ.get("MIDAS_MAPI_KEY", "")
    if not base or not key_value:
        print("❌ --probe 需要 MIDAS_BASE_URL / MIDAS_MAPI_KEY（见 scripts/load-midas-env.ps1）")
        return 1
    files = endpoint_files(repo)
    manifest = {
        str(item["key"]): item
        for item in json.loads(
            (repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8")
        )["endpoints"]
    }
    targets = probe_targets(repo, only)
    print(f"只读 L4 实测：{len(targets)} 个端点（实例 {INSTANCE_ALIAS} / {INSTANCE_PRODUCT}）")
    endpoints: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    with httpx.Client(base_url=base, headers={"MAPI-Key": key_value}, timeout=30.0) as client:
        for key in targets:
            item = manifest[key]
            read_root = str((item.get("wrapper") or {}).get("read_root") or "")
            uri = "/" + str(item.get("uri") or "").lstrip("/")
            response = client.get(uri)
            top: list[str] = []
            verdict = "FAILED"
            if response.status_code == 200:
                try:
                    payload = response.json()
                except ValueError:
                    payload = None
                if isinstance(payload, dict):
                    top = [str(name) for name in payload]
                    block = payload.get(read_root)
                    if read_root in top:
                        verdict = "PARTIAL" if isinstance(block, dict) and not block else "PASSED"
            endpoints[key] = {
                "uri": str(item.get("uri") or ""),
                "read_root": read_root,
                "status_code": response.status_code,
                "top_keys": top,
                "verdict": verdict,
            }
            counts[verdict] = counts.get(verdict, 0) + 1
    document = {
        "note": [
            "P149-C（R111 的恢复条件）：`availability: verified` 的语义 = 「至少一个实例 GET 成功」"
            "（registry/README.md §4），故本证据 = **只读** L4 实测（**只发 GET**，零副作用）。",
            "判据（与 P134 的 L4 同一口径）：响应顶层键 == `read_root` ⇒ `PASSED`（块非空）/ "
            "`PARTIAL`（块为空 —— 空项目下的正常形态）；非 200 或顶层键不符 ⇒ `FAILED`。",
            "生成器 = `registry/tools/sync_availability.py --probe`；收口 = `--write`（**只升不降**），"
            "随后跑 `registry/tools/sync_manifest.py --write` 重派生 manifest；`--check` 断言一致。",
            "凭据**绝不**写入本文件（MAPI-Key 只经环境变量注入）。",
        ],
        "instance": {
            "alias": INSTANCE_ALIAS,
            "product": INSTANCE_PRODUCT,
            "base_url": base,
            "probed_at": PROBED_AT,
            "scope": "untested ∧ GET ∧ read_root ∧ enabled",
        },
        "counts": counts,
        "endpoints": dict(sorted(endpoints.items())),
    }
    (repo / "registry" / EVIDENCE_RELATIVE).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("汇总 =", counts)
    print(f"已写入 registry/{EVIDENCE_RELATIVE}")
    return 0


def load_evidence(repo: Path) -> dict[str, dict[str, Any]]:
    path = repo / "registry" / EVIDENCE_RELATIVE
    if not path.is_file():
        raise SystemExit(f"❌ 缺证据文件 registry/{EVIDENCE_RELATIVE}（先跑 --probe）")
    return json.loads(path.read_text(encoding="utf-8"))["endpoints"]


def upgrade_lines(text: str, alias: str) -> tuple[str, bool]:
    """YAML 文本 → 收口后的文本（`availability: untested → verified` + `verified_on` 合并）。

    Returns:
        `(新文本, 是否改动)`；`unverified`（实测不可用）**不**动。
    """
    lines = text.splitlines(keepends=True)
    availability_index = None
    verified_index = None
    for index, line in enumerate(lines):
        if line.startswith("availability:"):
            availability_index = index
        elif line.startswith("verified_on:"):
            verified_index = index
    if availability_index is None:
        return text, False
    if lines[availability_index].strip() != "availability: untested":
        return text, False  # 已 verified / unverified ⇒ 只升不降
    lines[availability_index] = "availability: verified\n"
    if verified_index is None:
        lines.insert(availability_index + 1, f'verified_on: ["{alias}"]\n')
    else:
        yaml = _load_yaml_module()
        current = yaml.safe_load("".join(lines))["verified_on"]
        names = [str(item) for item in current]
        if alias not in names:
            names.append(alias)
            rendered = ", ".join(f'"{name}"' for name in names)
            lines[verified_index] = f"verified_on: [{rendered}]\n"
    return "".join(lines), True


def write_back(repo: Path) -> int:
    """按证据收口 YAML（只升不降）。"""
    evidence = load_evidence(repo)
    files = endpoint_files(repo)
    changed: list[str] = []
    for key, row in sorted(evidence.items()):
        if str(row.get("verdict")) not in UPGRADABLE:
            continue
        path = files[key]
        text, modified = upgrade_lines(path.read_text(encoding="utf-8"), INSTANCE_ALIAS)
        if modified:
            path.write_text(text, encoding="utf-8")
            changed.append(key)
    print(f"收口 {len(changed)} 个端点（证据里可用 = "
          f"{sum(1 for row in evidence.values() if row.get('verdict') in UPGRADABLE)}）")
    for key in changed:
        print("  ", key)
    print("⚠️ 请接着跑：python registry/tools/sync_manifest.py --write")
    return 0


def check(repo: Path) -> int:
    """断言：证据里可用的端点 ⇒ YAML 已 `verified` 且 `verified_on` 含该别名。"""
    evidence = load_evidence(repo)
    files = endpoint_files(repo)
    errors: list[str] = []
    for key, row in sorted(evidence.items()):
        if str(row.get("verdict")) not in UPGRADABLE:
            continue
        availability, verified_on = read_availability(files[key])
        if availability != VERIFIED:
            errors.append(f"{key}: availability = {availability!r}（证据 verdict = {row['verdict']}）")
        elif INSTANCE_ALIAS not in verified_on:
            errors.append(f"{key}: verified_on = {verified_on}（缺 {INSTANCE_ALIAS!r}）")
    if errors:
        print("❌ 与只读证据不一致：")
        for line in errors:
            print("  ", line)
        return 1
    print(f"✅ 与只读证据一致（{sum(1 for r in evidence.values() if r.get('verdict') in UPGRADABLE)} 个可用端点已收口）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=REPO_DEFAULT)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    only = tuple(part.strip() for part in args.only.split(",") if part.strip())

    status = 0
    if args.probe:
        status = probe(repo, only)
    if args.write:
        status = max(status, write_back(repo))
    if args.check:
        status = max(status, check(repo))
    if not (args.probe or args.write or args.check):
        print(__doc__)
    return status


if __name__ == "__main__":
    sys.exit(main())
