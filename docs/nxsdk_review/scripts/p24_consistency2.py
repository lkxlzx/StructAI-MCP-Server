"""Internal consistency: endpoint declares a product it is recorded unavailable on.

instances.yaml maps alias -> product (read manually; the file has an unquoted ':' so yaml.safe_load fails).
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
LOCAL = Path(r"E:\MCP\MMCP")
manifest = json.load(open(LOCAL / "registry" / "manifest.json", encoding="utf-8"))

INST_PROD = {"gen-local": "GEN_NX", "civil-cloud": "CIVIL_NX", "designer-cloud": "CIVIL_DESIGNER"}

print("=" * 104)
print("A) ENDPOINTS DECLARING A PRODUCT THEY ARE RECORDED AS UNAVAILABLE ON")
print("   (i.e. every declared product has an instance where the route 404'd)")
print("=" * 104)
bad = []
for e in manifest["endpoints"]:
    prods = set(e["products"])
    unav = e.get("unavailable_on") or []
    if not unav or not prods:
        continue
    unav_prods = {INST_PROD.get(i, i) for i in unav}
    if prods <= unav_prods:
        bad.append(e)
        print(f"  {e['key']:26s} products={','.join(e['products']):22s} solver={(e['solver'] or '-'):9s} "
              f"avail={e['availability']:10s} unavailable_on={e['unavailable_on']}")

print()
print(f"count: {len(bad)}")
print("solver distribution:", dict(Counter(e["solver"] for e in bad)))
print("namespace distribution:", dict(Counter(e["namespace"] for e in bad)))
print("availability distribution:", dict(Counter(e["availability"] for e in bad)))

print()
print("=" * 104)
print("B) ALL 21 -M1 entries")
print("=" * 104)
m1 = sorted([x for x in manifest["endpoints"] if x["uri"].upper().endswith("-M1")], key=lambda x: x["key"])
for e in m1:
    print(f"  {e['key']:24s} prod={','.join(e['products']):10s} solver={(e['solver'] or '-'):9s} "
          f"avail={e['availability']:10s} verified_on={str(e['verified_on']):6s} unavailable_on={e['unavailable_on']}")
print()
print(f"  of {len(m1)}: unavailable_on contains gen-local in "
      f"{sum(1 for e in m1 if 'gen-local' in (e.get('unavailable_on') or []))} entries")

json.dump([{k: e[k] for k in ("key", "uri", "products", "solver", "availability",
                              "verified_on", "unavailable_on", "definition", "schema")} for e in bad],
          open(LOCAL / ".tmp_analysis" / "internal_inconsistency.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print()
print("wrote internal_inconsistency.json  (", len(bad), "entries )")
