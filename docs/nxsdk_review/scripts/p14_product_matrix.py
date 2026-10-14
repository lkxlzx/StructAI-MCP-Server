"""Full product-attribution matrix: server /info availability vs our registry `products`."""
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
LOCAL = Path(r"E:\MCP\MMCP")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


ib = load(LOCAL / ".tmp_nxsdk" / "schema" / "info-baseline.json")
print("baseline coverage:", json.dumps(ib["coverage"], ensure_ascii=False))
eps = ib["endpoints"]

# exact status value distribution
st = Counter()
for r, e in eps.items():
    for p in ("gen", "civil"):
        sub = e.get(p)
        st[(p, None if sub is None else sub.get("status"))] += 1
print("status values:", dict(st))
print("total routes:", len(eps), " total pairs:", 2 * len(eps))

manifest = load(LOCAL / "registry" / "manifest.json")
by_uri = {}
for ep in manifest["endpoints"]:
    by_uri.setdefault(("/" + ep["uri"].strip("/")).upper(), []).append(ep)

print()
print("=" * 100)
print("CONTRADICTIONS: server answers /info on a product our registry does NOT declare")
print("=" * 100)
rows = []
for route, e in sorted(eps.items()):
    g = (e.get("gen") or {}).get("status")
    c = (e.get("civil") or {}).get("status")
    ours = by_uri.get(route.upper(), [])
    our_gen = any("GEN_NX" in x["products"] for x in ours)
    our_civ = any("CIVIL_NX" in x["products"] for x in ours)
    issues = []
    if c == 200 and not our_civ:
        issues.append("server:CIVIL=200  registry:CIVIL_NX absent")
    if g == 200 and not our_gen:
        issues.append("server:GEN=200    registry:GEN_NX absent")
    if c != 200 and our_civ and c is not None:
        issues.append(f"server:CIVIL={c}  registry:CIVIL_NX declared")
    if g != 200 and our_gen and g is not None:
        issues.append(f"server:GEN={g}    registry:GEN_NX declared")
    if issues:
        rows.append((route, g, c, our_gen, our_civ, issues,
                     [x["key"] for x in ours], [x["solver"] for x in ours]))

print(f"routes with a contradiction: {len(rows)}")
for route, g, c, og, oc, issues, keys, solvers in rows:
    print(f"  {route:26s} srv(gen={str(g):>4s},civil={str(c):>4s})  ours(gen={og},civil={oc})  keys={keys} solver={solvers}")
    for i in issues:
        print(f"       -> {i}")

json.dump([{"route": r, "gen": g, "civil": c, "our_gen": og, "our_civil": oc,
            "issues": iss, "keys": k, "solvers": s}
           for r, g, c, og, oc, iss, k, s in rows],
          open(LOCAL / ".tmp_analysis" / "product_contradictions.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print()
print("wrote product_contradictions.json")
