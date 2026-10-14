"""Drill into specific routes to verify the field diff is real, not a flattening artifact."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SDK = Path(r"E:\MCP\MMCP\.tmp_nxsdk")
LOCAL = Path(r"E:\MCP\MMCP")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


rows = load(LOCAL / ".tmp_analysis" / "field_diff_raw.json")
manifest = load(LOCAL / "registry" / "manifest.json")
by_uri = {}
for ep in manifest["endpoints"]:
    by_uri.setdefault("/" + ep["uri"].strip("/").upper(), []).append(ep)

print("=" * 72)
print("A) LOCAL_SCHEMA_ABSENT pairs — SDK has /info schema, we have no schema file")
print("=" * 72)
absent = [r for r in rows if r["status"] == "LOCAL_SCHEMA_ABSENT"]
for r in absent:
    print(f"  {r['route']:40s} {r['product']:10s} sdk_fields={len(r['sdk_only'])}")
print(f"  total: {len(absent)}")

print()
print("=" * 72)
print("B) Drill-down on 3 biggest DIFF routes")
print("=" * 72)
ib = load(SDK / "schema" / "info-baseline.json")["endpoints"]
for route, prod in [("/db/STCT-M1", "civil"), ("/db/SWIND", "gen"), ("/db/REBB", "gen")]:
    print()
    print("#" * 70)
    print(f"# {route}  ({prod})")
    print("#" * 70)
    entry = ib.get(route)
    if not entry:
        print("  not in baseline"); continue
    e = entry.get(prod)
    if not e:
        print("  no entry for product", prod); continue
    print("  --- SERVER /info schema (raw, first 1800 chars) ---")
    print(json.dumps(e.get("schema"), ensure_ascii=False, indent=1)[:1800])

    # local
    eps = by_uri.get(route.upper(), [])
    for ep in eps:
        if ep.get("schema"):
            p = LOCAL / "registry" / ep["schema"]
            if p.exists():
                d = load(p)
                print(f"  --- LOCAL schema {ep['schema']} (key={d.get('key')}, source={d.get('source')}) ---")
                print(json.dumps(d.get("schema"), ensure_ascii=False, indent=1)[:1800])
                break
    else:
        print("  --- LOCAL: no schema file ---")
