"""P164-c 真机实测（分块 1）：RC / SRC **配置端点**的写入 → **读回验效果** → 清理。

纪律
----
* **铁律 ⓪**：判据 = **效果**（`GET` 读回里有那个值），**不是**状态码。
* 只碰**设计配置**端点（模型级设置），**不**碰节点 / 单元 / 材料 / 截面。
* **零残留**：写完全部 `DELETE`，并以「再读一次，该值确实不在」为准。
* 哨兵：跑前 / 跑后只读对比（**只** `GET`）。
* 默认**预演**；`--write` 才真发。

体（**照手册示例**，非臆造）：`registry/live/write_templates.json` 的 `body`，
外层按数据侧 `wrapper.write = "Assign"` + 编号键 `"1"`（与 `DB.CONS` 实测同形）。
"""
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
import httpx  # noqa: E402

REPO = Path(r"E:\MCP\MMCP")
CREDS = Path(os.environ["USERPROFILE"]) / ".structai" / "midas-test.env"
WRITE = "--write" in sys.argv

# (key, uri, 手册示例的模板键)
TARGETS = (
    ("DESIGN.RC.DRC", "DESIGN/RC/DRC", "DESIGN.RC.DRC"),
    ("DESIGN.RC.KDS-41-20-2022.DCO", "DESIGN/RC/KDS-41-20-2022/DCO", "DESIGN.RC.KDS-41-20-2022.DCO"),
    ("DESIGN.SRC.AIK-SRC2K.DSRC", "DESIGN/SRC/AIK-SRC2K/DSRC", "DESIGN.SRC.AIK-SRC2K.DSRC"),
    ("DESIGN.SRC.AIK-SRC2K.DCO", "DESIGN/SRC/AIK-SRC2K/DCO", "DESIGN.SRC.AIK-SRC2K.DCO"),
)
SENTINEL = (
    "DB/NODE", "DB/ELEM", "DB/MATL", "DB/SECT", "DB/STLD", "DB/CNLD", "DB/CONS",
    "DB/LCOM-STEEL", "DB/LCOM-CONC", "DB/GRUP",
    *(uri for _k, uri, _t in TARGETS),
)
# 读回里该「有值」的判据：原生键 → 期望值
EXPECT = {
    "DESIGN.RC.DRC": {"DGNCODE": "KDS 41 20 : 2022"},
    "DESIGN.RC.KDS-41-20-2022.DCO": {"DESIGN_CD": "KDS 41 20 : 2022"},
    "DESIGN.SRC.AIK-SRC2K.DSRC": {"DGNCODE": "AIK-SRC2K"},
    "DESIGN.SRC.AIK-SRC2K.DCO": {"DGNCODE": "AIK-SRC2K", "SEISMIC": True},
}
READ_ROOT = {
    "DESIGN.RC.DRC": "DCON",
    "DESIGN.RC.KDS-41-20-2022.DCO": "DCORC",
    "DESIGN.SRC.AIK-SRC2K.DSRC": "DSRC",
    "DESIGN.SRC.AIK-SRC2K.DCO": "SRCDCO",
}


def load(instance: str) -> tuple[str, str]:
    section, values = "", {}
    for raw in CREDS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue
        if section == instance and "=" in line:
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip()
    return values["MIDAS_BASE_URL"].rstrip("/"), values["MIDAS_MAPI_KEY"]


BASE, KEY = load("gen")
templates = json.loads((REPO / "registry" / "live" / "write_templates.json").read_text(encoding="utf-8"))[
    "templates"
]


def snapshot(client: httpx.Client) -> dict:
    out = {}
    for path in SENTINEL:
        r = client.get("/" + path)
        try:
            payload = r.json()
            top = list(payload) if isinstance(payload, dict) else []
            block = payload.get(top[0]) if top else None
            if isinstance(block, dict) and "ITEMS" in block:
                n = len(block["ITEMS"])
            elif isinstance(block, dict):
                n = len([k for k in block if str(k).isdigit()])
            else:
                n = len(block) if isinstance(block, list) else 0
        except Exception:  # noqa: BLE001
            top, n = ["<非 JSON>"], 0
        out[path] = {"status": r.status_code, "top": top, "count": n}
    return out


def read_config(client: httpx.Client, key: str) -> dict:
    root = READ_ROOT[key]
    payload = client.get("/" + dict((k, u) for k, u, _t in TARGETS)[key]).json()
    block = payload.get(root)
    return block if isinstance(block, dict) else {}


with httpx.Client(base_url=BASE, headers={"MAPI-Key": KEY}, timeout=25.0) as client:
    print(f"实例 {BASE}  模式={'真发' if WRITE else '预演'}")
    before = snapshot(client)
    print(f"哨兵（跑前）：非零项 = "
          f"{ {k: v['count'] for k, v in before.items() if v['count']} or '（无）'}")
    print()

    results = []
    for key, uri, template_key in TARGETS:
        body = (templates.get(template_key) or {}).get("body") or {}
        wire = {"Assign": {"1": dict(body)}}
        print(f"--- {key}")
        print(f"    PUT /{uri}")
        print(f"    体: {json.dumps(wire, ensure_ascii=False)[:200]}")
        if not WRITE:
            print("    （预演，未发）")
            continue
        r = client.put("/" + uri, json=wire)
        print(f"    -> {r.status_code} {r.text[:120]}")
        after_block = read_config(client, key)
        # ⚠️ 铁律 ⓪：判据 = 读回里有那个值
        found = {}
        entry = after_block.get("1") if isinstance(after_block, dict) else None
        if isinstance(entry, dict):
            for native, want in EXPECT[key].items():
                found[native] = entry.get(native)
        ok = bool(entry) and all(found.get(n) == w for n, w in EXPECT[key].items())
        print(f"    读回（{READ_ROOT[key]}）: {json.dumps(after_block, ensure_ascii=False)[:220]}")
        print(f"    效果判据: {'✅ 值已在' if ok else '❌ 值不在'}  {json.dumps(found, ensure_ascii=False)}")
        results.append({"key": key, "put_status": r.status_code, "readback": after_block,
                        "expected": EXPECT[key], "effect_ok": ok, "found": found})
        print()

    # ---- 清理：DELETE + 再读确认 ----
    cleanup = []
    for key, uri, _t in TARGETS:
        block_before = read_config(client, key) if WRITE else {}
        print(f"--- 清理 {key}")
        if not WRITE:
            print("    （预演，未发）")
            continue
        d = client.delete("/" + uri)
        block_after = read_config(client, key)
        gone = not block_after
        print(f"    DELETE -> {d.status_code}   再读: {json.dumps(block_after, ensure_ascii=False)[:150]}"
              f"   {'✅ 已清空' if gone else '⚠️ 仍有'}")
        cleanup.append({"key": key, "delete_status": d.status_code, "before": block_before,
                        "after": block_after, "gone": gone})

    after = snapshot(client) if WRITE else before
    print()
    print(f"哨兵（跑后）：非零项 = { {k: v['count'] for k, v in after.items() if v['count']} or '（无）'}")
    if WRITE:
        changed = [k for k in SENTINEL if before[k] != after[k]]
        print(f"哨兵**变化**的项: {changed or '（无）'}")

    if WRITE:
        out = REPO / ".tmp_analysis" / "p164c_chunk1.json"
        out.write_text(json.dumps({"results": results, "cleanup": cleanup,
                                   "sentinel_before": before, "sentinel_after": after},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"wrote {out}")
