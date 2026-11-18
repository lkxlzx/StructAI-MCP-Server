"""P188 —— `DESIGN.RC.REBR` 的 `400` 真机归因排查（REBC 同族；有副作用，延续 B 授权）。

目标（`docs/08 §4` P188 候选②）：REBR 是 REBC 的**同族**（`Assign → 截面号 → ITEMS[]`）。
验证其 `400` 是否也**与前置对象无关**、归因 = **键名/形状层**（若同族同因，则 P186-B 的
结论可复用，无需再单独向产品侧提第 6 问 —— REBC 与 REBR 合并为一问）。

做法（同 P186-B）：空项目 ① 阳性对照（建节点→读回）② 建前置单元 → 读回
③ `PUT REBR`（前置已在）→ 看是否 `400` ④ 逆序清理 → 断言零残留。
直连 httpx 保留**原生文案**（`Wrong Field` 等）。不碰 `*-ANAL`（R154）。

用法：
  MIDAS_BASE_URL=... MIDAS_MAPI_KEY=... python probe_rebr_prereq_p188.py            # DRY
  ... --live [--evidence registry/live/rebr_prereq_probe_p188.json]                 # 真机（有副作用）
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from typing import Any

import httpx

ENDPOINT = "/DESIGN/RC/KDS-41-20-2022/REBR"


def _client() -> httpx.Client:
    base = os.environ.get("MIDAS_BASE_URL", "").strip()
    key = os.environ.get("MIDAS_MAPI_KEY", "").strip()
    if not base or not key:
        print("MIDAS_BASE_URL / MIDAS_MAPI_KEY 未设置", file=sys.stderr)
        raise SystemExit(2)
    return httpx.Client(
        base_url=base,
        headers={"MAPI-Key": key, "Content-Type": "application/json", "Accept": "application/json"},
        timeout=30.0,
    )


def _rec(ev: dict[str, Any], label: str, method: str, path: str,
         r: Any, request_body: Any = None) -> int:
    try:
        native = r.text[:300]
    except Exception:  # noqa: BLE001
        native = ""
    entry: dict[str, Any] = {"step": label, "method": method, "path": path,
                             "status": int(r.status_code), "native": native}
    if request_body is not None:
        entry["request_body"] = request_body
    ev["observations"].append(entry)
    print(f"[{label}] {r.status_code} :: {native}")
    return int(r.status_code)


def run(live: bool, evidence_path: str | None) -> int:
    ev: dict[str, Any] = {
        "tool": "probe_rebr_prereq_p188",
        "ruling": "P188",
        "criterion": "效果 + 原生文案（铁律 ⓪）；阳性对照 R157",
        "endpoint": ENDPOINT,
        "instance": os.environ.get("MIDAS_BASE_URL", ""),
        "live": live,
        "observations": [],
        "conclusion": {},
        "final_zero_residue": None,
    }
    c = _client()
    created: list[str] = []
    try:
        _rec(ev, "baseline_node", "GET", "/db/NODE", c.get("/db/NODE"))
        _rec(ev, "baseline_elem", "GET", "/db/ELEM", c.get("/db/ELEM"))
        if not live:
            print(">> DRY（加 --live 真机写）；端点:", ENDPOINT)
            ev["conclusion"] = {"dry_run": True}
            return 0

        # 1 阳性对照：节点 1/2 → 读回 → 单元 1
        if _rec(ev, "post_node1", "POST", "/db/NODE",
                c.post("/db/NODE", json={"Assign": {"1": {"X": 0, "Y": 0, "Z": 0}}})) // 100 == 2:
            created.append("/db/NODE/1")
        if _rec(ev, "post_node2", "POST", "/db/NODE",
                c.post("/db/NODE", json={"Assign": {"2": {"X": 0, "Y": 0, "Z": 3}}})) // 100 == 2:
            created.append("/db/NODE/2")
        _rec(ev, "readback_node", "GET", "/db/NODE", c.get("/db/NODE"))
        if _rec(ev, "post_elem1", "POST", "/db/ELEM",
                c.post("/db/ELEM", json={"Assign": {"1": {
                    "TYPE": "BEAM", "MATL": 1, "SECT": 1, "NODE": [1, 2]}}})) // 100 == 2:
            created.append("/db/ELEM/1")
        _rec(ev, "readback_elem", "GET", "/db/ELEM", c.get("/db/ELEM"))

        # 3 目标：PUT REBR（前置单元已存在）—— 按 REBR schema 构造（MAIN_BAR: NAME/NUM/ROW；
        #   SHEAR_BAR_END: NAME/LEG_Y/LEG_Z/DIST；DO: number）
        rebr = {"Assign": {"1": {"ITEMS": [{
            "CREATE_SUB_SECTION": False, "ELEMS": {"KEYS": [1]},
            "MAIN_BAR": {"NAME": "D22", "NUM": 4, "ROW": 2},
            "SHEAR_BAR_END": {"NAME": "D10", "LEG_Y": 2, "LEG_Z": 2, "DIST": 100},
            "SHEAR_BAR_CEN": {"NAME": "D10", "LEG_Y": 2, "LEG_Z": 2, "DIST": 200},
            "DO": 0.0}]}}}
        st = _rec(ev, "put_rebr_with_elem", "PUT", ENDPOINT, c.put(ENDPOINT, json=rebr), rebr)
        _rec(ev, "readback_rebr", "GET", ENDPOINT, c.get(ENDPOINT))

        ev["conclusion"] = {
            "put_rebr_status": st,
            "same_family_as_rebc": True,
            "attribution": (
                "REBR 与 REBC 同族（Assign→截面号→ITEMS[]、同 required）；"
                "本批测其在「前置单元已存在」下的状态码/原生文案，判断是否同为 Wrong Field ⇒ 合并为一问"
            ),
        }
        return 0
    finally:
        try:
            for path in reversed(created):
                r = c.delete(path)
                print(f"[cleanup] {path} -> {r.status_code}")
            fn = c.get("/db/NODE")
            fe = c.get("/db/ELEM")
            ev["final_zero_residue"] = (
                fn.text.strip() == '{"message":""}' and fe.text.strip() == '{"message":""}'
            )
            ev["final_state"] = {"nodes": fn.text, "elems": fe.text}
            print("ZERO_RESIDUE:", ev["final_zero_residue"])
        finally:
            c.close()
            if evidence_path:
                with io.open(evidence_path, "w", encoding="utf-8") as f:
                    json.dump(ev, f, ensure_ascii=False, indent=1)
                print("evidence ->", evidence_path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="真机执行（有副作用）")
    ap.add_argument("--evidence", default=None, help="证据 JSON 落盘路径")
    args = ap.parse_args()
    if not args.live:
        print(">> DRY：只探活 + 打印计划（加 --live 才真机写）")
    return run(args.live, args.evidence)


if __name__ == "__main__":
    raise SystemExit(main())
