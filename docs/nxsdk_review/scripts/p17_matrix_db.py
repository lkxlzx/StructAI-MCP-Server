"""Final product matrix restricted to /db/* (where /info is actually served)."""
import json
import sys
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

# documented /info exceptions: these 404 on BOTH products despite being real routes
INFO_404_EXCEPTIONS = {"/DB/IEHG-GL-M1", "/DB/IEHG-PSS-M1", "/DB/IEHG-TRUSS-M1"}

tier1, under, over = [], [], []
for route, e in sorted(ib.items()):
    u = route.upper()
    if not u.startswith("/DB/"):
        continue
    if u in INFO_404_EXCEPTIONS:
        continue
    srv_gen = (e.get("gen") or {}).get("status") == 200
    srv_civ = (e.get("civil") or {}).get("status") == 200
    ours = by_uri.get(u, [])
    our_gen = any("GEN_NX" in x["products"] for x in ours)
    our_civ = any("CIVIL_NX" in x["products"] for x in ours)
    solver = ours[0]["solver"] if ours else ""
    key = ours[0]["key"] if ours else None
    rec = dict(route=route, key=key, solver=solver, srv_gen=srv_gen, srv_civ=srv_civ,
               our_gen=our_gen, our_civ=our_civ)
    if u.endswith("-M1") and solver == "HYPER_S" and srv_civ and not srv_gen and our_gen and not our_civ:
        tier1.append(rec)
        continue
    if srv_civ and not our_civ:
        under.append(rec)
    if srv_gen and not our_gen:
        under.append(rec)
    if our_civ and not srv_civ:
        over.append(rec)
    if our_gen and not srv_gen:
        over.append(rec)

# the 3 IEHG exceptions are still Hyper-S mis-attributions
for u in sorted(INFO_404_EXCEPTIONS):
    ours = by_uri.get(u, [])
    if ours:
        tier1.append(dict(route=u, key=ours[0]["key"], solver=ours[0]["solver"],
                          srv_gen=False, srv_civ=None, our_gen="GEN_NX" in ours[0]["products"],
                          our_civ="CIVIL_NX" in ours[0]["products"], note="info-404 exception"))

print("=" * 92)
print(f"TIER 1 — Hyper-S (-M1) product attribution inverted: {len(tier1)} endpoints")
print("=" * 92)
for r in sorted(tier1, key=lambda x: x["route"]):
    note = "  [" + r["note"] + "]" if r.get("note") else ""
    print(f"  {r['route']:24s} {str(r['key']):22s} ours=GEN_NX  server: gen=404 civil=200{note}")

print()
print("=" * 92)
print(f"TIER 2a — /db/* where server /info answers a product we don't declare: {len(under)}")
print("=" * 92)
for r in under:
    print(f"  {r['route']:24s} {str(r['key']):22s} srv(gen={r['srv_gen']!s:5s} civil={r['srv_civ']!s:5s}) ours(gen={r['our_gen']!s:5s} civil={r['our_civ']!s:5s})")

print()
print("=" * 92)
print(f"TIER 2b — /db/* where we declare a product whose /info 404s: {len(over)}")
print("=" * 92)
for r in over:
    print(f"  {r['route']:24s} {str(r['key']):22s} srv(gen={r['srv_gen']!s:5s} civil={r['srv_civ']!s:5s}) ours(gen={r['our_gen']!s:5s} civil={r['our_civ']!s:5s})")

json.dump(dict(tier1=tier1, tier2_under=under, tier2_over=over),
          open(LOCAL / ".tmp_analysis" / "product_matrix_db.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print()
print(f"counts: tier1={len(tier1)} tier2a={len(under)} tier2b={len(over)}")
