"""Produce readable detail for the report: top field gaps + type mismatches + extra fields."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
LOCAL = Path(r"E:\MCP\MMCP")
rows = json.load(open(LOCAL / ".tmp_analysis" / "field_diff_v4.json", encoding="utf-8"))


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


ib = load(LOCAL / ".tmp_nxsdk" / "schema" / "info-baseline.json")["endpoints"]


def sdk_fields(route, prod):
    e = (ib.get(route) or {}).get(prod) or {}
    sch = e.get("schema") or {}
    for k, v in sch.items():
        if k == "$schema":
            continue
        if isinstance(v, dict):
            return v.get("properties", {})
    return {}


print("=" * 96)
print("A) Detail for the 6 largest 'missing field' cases (server /info declares, we do not)")
print("=" * 96)
for route, prod in [("/db/SWIND", "gen"), ("/db/SSEIS", "gen"), ("/db/REBB", "gen"),
                    ("/db/REBW", "gen"), ("/db/REBC", "gen"), ("/db/REBR", "gen")]:
    r = next((x for x in rows if x["route"] == route and x["product"] == ("GEN_NX" if prod == "gen" else "CIVIL_NX")), None)
    if not r:
        continue
    props = sdk_fields(route, prod)
    print(f"\n--- {route} [{prod}]  missing={len(r['sdk_only'])} extra={len(r['local_only'])} ---")
    print("  SERVER top-level properties:", list(props)[:30])
    miss_top = sorted({f.split(".")[0].split("[")[0] for f in r["sdk_only"]})
    extra_top = sorted({f.split(".")[0].split("[")[0] for f in r["local_only"]})
    print("  server-only TOP-LEVEL names:", miss_top)
    print("  local-only  TOP-LEVEL names:", extra_top)

print()
print("=" * 96)
print("B) All 20 type mismatches, with descriptions")
print("=" * 96)
for r in rows:
    for t in r.get("type_mismatch", []):
        print(f"  {r['route']:22s} {r['product']:9s} {t['path']:42s} ours={t['local']:9s} server={t['server']:9s}")
        if t.get("server_desc"):
            print(f"        server says: {t['server_desc'][:110]}")
        if t.get("local_desc"):
            print(f"        ours   says: {t['local_desc'][:110]}")

print()
print("=" * 96)
print("C) Endpoints where WE declare MORE than the server's /info (informational, not defects)")
print("=" * 96)
for r in sorted([x for x in rows if x["local_only"]], key=lambda x: -len(x["local_only"])):
    tops = sorted({f.split(".")[0].split("[")[0] for f in r["local_only"]})
    print(f"  {r['route']:22s} {r['product']:9s} extra={len(r['local_only']):3d}  top-level: {tops}")
