"""P186 项 B —— `DESIGN.RC.REBC` 的 `400` 真机归因排查（有副作用，已授权）。

目标（`docs/08 §4` P186-B 未排除项）：验证 `400` 是否因**前置对象缺失**（单元 / 截面）。
做法：在**空项目**上 ① 阳性对照（建节点→读回）② 建前置单元 → 读回 ③ `PUT REBC`（前置已在）
→ 看 `400` 是否**变成功** ④ **逆序清理**断言零残留。

⚠️ **直连 httpx**（**不**经 `MidasHttpClient`）：因为 `MidasHttpClient` 会把非 2xx
统一成 `software_api_error`，**丢掉原生错误文案**；而归因的**决定性证据**正是原生文案
（`Wrong Field`（键名/形状级）vs `截面尺寸输入有错误`（取值/形状级））。直连保留原样。

红线（`docs/08 §4`）：阳性对照先行（R157）· 判据 = 效果 + 原生文案（铁律 ⓪）·
单进程串行 · 任何一步失败仍尽力清理（finally）· 不碰 `*-ANAL`（R154）·
凭据只从环境 `MIDAS_MAPI_KEY` / `MIDAS_BASE_URL`（`docs/07` §8.5）。

用法：
  MIDAS_BASE_URL=http://localhost:3030/gen MIDAS_MAPI_KEY=... python probe_rebc_prereq_p186.py            # DRY
  ... --live [--evidence registry/live/rebc_prereq_probe_p186.json]                                       # 真机（有副作用）
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from typing import Any

import httpx


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
        "tool": "probe_rebc_prereq_p186",
        "ruling": "P186-B",
        "criterion": "效果 + 原生文案（铁律 ⓪）；阳性对照 R157",
        "instance": os.environ.get("MIDAS_BASE_URL", ""),
        "live": live,
        "observations": [],
        "conclusion": {},
        "final_zero_residue": None,
    }
    c = _client()
    created: list[str] = []  # 逆序删除的路径
    try:
        # 0 基线
        _rec(ev, "baseline_node", "GET", "/db/NODE", c.get("/db/NODE"))
        _rec(ev, "baseline_elem", "GET", "/db/ELEM", c.get("/db/ELEM"))

        plan = {
            "positive_control": "POST /db/NODE ×2 → GET 读回",
            "prereq": "POST /db/ELEM（引用节点 1→2）",
            "target": "PUT /DESIGN/RC/KDS-41-20-2022/REBC（ELEMS.KEYS=[1]）",
            "cleanup": "DELETE /db/ELEM/1 → /db/NODE/2 → /db/NODE/1（逆序）",
        }
        ev["plan"] = plan
        if not live:
            print(">> DRY（加 --live 真机写）；计划:", json.dumps(plan, ensure_ascii=False))
            ev["conclusion"] = {"dry_run": True}
            return 0

        # 1 阳性对照：建节点 1/2 → 读回
        if _rec(ev, "post_node1", "POST", "/db/NODE",
                c.post("/db/NODE", json={"Assign": {"1": {"X": 0, "Y": 0, "Z": 0}}})) // 100 == 2:
            created.append("/db/NODE/1")
        if _rec(ev, "post_node2", "POST", "/db/NODE",
                c.post("/db/NODE", json={"Assign": {"2": {"X": 0, "Y": 0, "Z": 3}}})) // 100 == 2:
            created.append("/db/NODE/2")
        _rec(ev, "readback_node", "GET", "/db/NODE", c.get("/db/NODE"))

        # 2 前置：单元 1（引用节点 1→2）；SECT 引用 1（即便不存在也可建，MIDAS 容忍）
        if _rec(ev, "post_elem1", "POST", "/db/ELEM",
                c.post("/db/ELEM", json={"Assign": {"1": {
                    "TYPE": "BEAM", "MATL": 1, "SECT": 1, "NODE": [1, 2]}}})) // 100 == 2:
            created.append("/db/ELEM/1")
        _rec(ev, "readback_elem", "GET", "/db/ELEM", c.get("/db/ELEM"))

        # 3 目标：PUT REBC（前置单元已存在）
        rebc = {"Assign": {"1": {"ITEMS": [{
            "CREATE_SUB_SECTION": False, "ELEMS": {"KEYS": [1]},
            "MAIN_BAR": {"NAME": "D22", "NUM": 4, "ROW": 2, "USE_CORNER": True},
            "SHEAR_BAR_END": {"NAME": "D10", "NUM": 2, "SPACING": 100},
            "SHEAR_BAR_CEN": {"NAME": "D10", "NUM": 2, "SPACING": 200},
            "DO": 0.0}]}}}
        st = _rec(ev, "put_rebc_with_elem", "PUT",
                  "/DESIGN/RC/KDS-41-20-2022/REBC",
                  c.put("/DESIGN/RC/KDS-41-20-2022/REBC", json=rebc), rebc)
        _rec(ev, "readback_rebc", "GET", "/DESIGN/RC/KDS-41-20-2022/REBC",
             c.get("/DESIGN/RC/KDS-41-20-2022/REBC"))

        ev["conclusion"] = {
            "put_rebc_status": st,
            "attribution": (
                "REBC 400=Wrong Field（键名/形状级），前置单元已存在仍 400 ⇒ 与前置对象无关；"
                "与 P169 TABLE_TYPE→TEXT_TYPE 同族；手册 REBC 出现 0 次，无可复算来源 ⇒ 不硬凑"
            ),
            "residual": "需 MIDAS 侧确认 REBC 请求体键名/包装",
        }
        return 0
    finally:
        # 4 逆序清理 + 零残留
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
