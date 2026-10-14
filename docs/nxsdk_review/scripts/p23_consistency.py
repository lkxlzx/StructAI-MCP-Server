"""Check internal consistency: does an endpoint declare a product it is recorded as unavailable on?"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
LOCAL = Path(r"E:\MCP\MMCP")
manifest = json.load(open(LOCAL / "registry" / "manifest.json", encoding="utf-8"))

# instances.yaml gives instance -> product mapping
import yaml
inst = yaml.safe_load((LOCAL / "registry" / "instances.yaml").read_text(encoding="utf-8"))
print("instances.yaml:")
print(json.dumps(inst, ensure_ascii=False, indent=1)[:1500])
print()

# map instance name -> product
inst_prod = {}
if isinstance(inst, dict):
    for k, v in inst.items():
        if isinstance(v, dict):
            inst_prod[k] = v.get("product") or v.get("products") or v.get("kind")
print("instance -> product:", inst_prod)
print()

print("=" * 100)
print("ENDPOINTS DECLARING A PRODUCT THEY ARE RECORDED AS UNAVAILABLE ON")
print("=" * 100)
bad = []
for e in manifest["endpoints"]:
    prods = set(e["products"])
    unav = e.get("unavailable_on") or []
    if not unav:
        continue
    # is every declared product covered by an unavailable instance?
    unav_prods = {inst_prod.get(i, i) for i in unav}
    if prods and prods <= unav_prods:
        bad.append(e)
        print(f"  {e['key']:26s} products={','.join(e['products']):30s} unavailable_on={unav}  avail={e['availability']} verified_on={e['verified_on']}")

print()
print(f"count: {len(bad)}")
print()
print("solver distribution among these:", Counter(e["solver"] for e in bad))
print("namespace distribution:", Counter(e["namespace"] for e in bad))

print()
print("=" * 100)
print("ALL 21 -M1 entries: products / solver / availability / verified_on / unavailable_on")
print("=" * 100)
for e in sorted([x for x in manifest["endpoints"] if x["uri"].upper().endswith("-M1")], key=lambda x: x["key"]):
    print(f"  {e['key']:24s} prod={','.join(e['products']):10s} solver={(e['solver'] or '-'):9s} avail={e['availability']:10s} verified_on={str(e['verified_on']):12s} unavailable_on={e['unavailable_on']}")

json.dump([{k: e[k] for k in ("key", "uri", "products", "solver", "availability",
                              "verified_on", "unavailable_on", "definition")} for e in bad],
          open(LOCAL / ".tmp_analysis" / "internal_inconsistency.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print()
print("wrote internal_inconsistency.json")
