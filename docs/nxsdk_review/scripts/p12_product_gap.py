"""Are the NO_LOCAL_SCHEMA pairs a product-coverage gap in our registry?"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
LOCAL = Path(r"E:\MCP\MMCP")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


manifest = load(LOCAL / "registry" / "manifest.json")
rows = load(LOCAL / ".tmp_analysis" / "field_diff_v4.json")
absent = {r["route"].upper(): r for r in rows if r["status"] == "NO_LOCAL_SCHEMA"}

by_uri = {}
for ep in manifest["endpoints"]:
    by_uri.setdefault(("/" + ep["uri"].strip("/")).upper(), []).append(ep)

print("=" * 78)
print("Manifest entries for the 31 routes where the SERVER answers CIVIL_NX /info")
print("=" * 78)
n_prod_gap = 0
for route in sorted(absent):
    eps = by_uri.get(route)
    if not eps:
        print(f"  {route:24s} *** NOT IN MANIFEST AT ALL ***")
        continue
    for ep in eps:
        prods = ep["products"]
        has_civil = "CIVIL_NX" in prods
        flag = "" if has_civil else "   <== CIVIL_NX NOT DECLARED"
        if not has_civil:
            n_prod_gap += 1
        print(f"  {route:24s} key={ep['key']:22s} products={','.join(prods):30s} schema={ep['schema']!r:55s} avail={ep['availability']}{flag}")

print()
print(f"entries missing CIVIL_NX in products: {n_prod_gap}")

# cross-check: SDK says which products each endpoint answers on
ib = load(LOCAL / ".tmp_nxsdk" / "schema" / "info-baseline.json")["endpoints"]
print()
print("=" * 78)
print("Server /info product matrix for these routes (status per product)")
print("=" * 78)
for route in sorted(absent):
    e = ib.get(route, {})
    st = {p: (e.get(p) or {}).get("status") for p in ("gen", "civil")}
    print(f"  {route:24s} gen={st['gen']}  civil={st['civil']}")
