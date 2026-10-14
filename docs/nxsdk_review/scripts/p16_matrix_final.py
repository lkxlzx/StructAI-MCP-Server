"""Final product-attribution matrix (treating baseline None as 404 for /info)."""
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
LOCAL = Path(r"E:\MCP\MMCP")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


ib = load(LOCAL / ".tmp_nxsdk" / "schema" / "info-baseline.json")["endpoints"]
manifest = load(LOCAL / "registry" / "manifest.json")
by_uri = {}
for ep in manifest["endpoints"]:
    by_uri.setdefault(("/" + ep["uri"].strip("/")).upper(), []).append(ep)

tier1, tier2_under, tier2_over = [], [], []
for route, e in sorted(ib.items()):
    g = (e.get("gen") or {}).get("status")
    c = (e.get("civil") or {}).get("status")
    srv_gen, srv_civ = (g == 200), (c == 200)
    ours = by_uri.get(route.upper(), [])
    our_gen = any("GEN_NX" in x["products"] for x in ours)
    our_civ = any("CIVIL_NX" in x["products"] for x in ours)
    solver = ours[0]["solver"] if ours else ""
    key = ours[0]["key"] if ours else None
    is_m1 = route.upper().endswith("-M1")
    rec = dict(route=route, key=key, solver=solver, srv_gen=srv_gen, srv_civ=srv_civ,
               our_gen=our_gen, our_civ=our_civ, is_m1=is_m1)
    if is_m1 and solver == "HYPER_S" and srv_civ and not srv_gen and our_gen and not our_civ:
        tier1.append(rec)
    else:
        if srv_civ and not our_civ:
            tier2_under.append(rec)
        if srv_gen and not our_gen:
            tier2_under.append(rec)
        if our_civ and not srv_civ:
            tier2_over.append(rec)
        if our_gen and not srv_gen:
            tier2_over.append(rec)

print("=" * 96)
print(f"TIER 1 — Hyper-S product attribution inverted (high confidence): {len(tier1)}")
print("=" * 96)
for r in tier1:
    print(f"  {r['route']:24s} {r['key']:22s} solver=HYPER_S  ours=GEN_NX  server: gen=404 civil=200")

print()
print("=" * 96)
print(f"TIER 2a — server /info answers a product we do NOT declare: {len(tier2_under)}")
print("=" * 96)
for r in tier2_under:
    print(f"  {r['route']:26s} {str(r['key']):24s} srv(gen={r['srv_gen']!s:5s} civil={r['srv_civ']!s:5s}) ours(gen={r['our_gen']!s:5s} civil={r['our_civ']!s:5s})")

print()
print("=" * 96)
print(f"TIER 2b — we declare a product whose /info 404s: {len(tier2_over)}")
print("=" * 96)
for r in tier2_over:
    print(f"  {r['route']:26s} {str(r['key']):24s} srv(gen={r['srv_gen']!s:5s} civil={r['srv_civ']!s:5s}) ours(gen={r['our_gen']!s:5s} civil={r['our_civ']!s:5s})")

json.dump(dict(tier1=tier1, tier2_under=tier2_under, tier2_over=tier2_over),
          open(LOCAL / ".tmp_analysis" / "product_matrix_final.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print()
print("wrote product_matrix_final.json")
print("counts:", len(tier1), len(tier2_under), len(tier2_over))
