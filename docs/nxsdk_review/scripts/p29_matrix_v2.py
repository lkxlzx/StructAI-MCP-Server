"""Product matrix v2 — use SCHEMA PRESENCE as the availability signal, not `status`.

Correction: /db/POSP has a civil schema with status=None. So status None != 404.
coverage: pairsWithSchema=400, pairsAnswering404=210, 610-400=210 -> pairs WITHOUT schema are the 404s.
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
LOCAL = Path(r"E:\MCP\MMCP")
SDK = LOCAL / ".tmp_nxsdk"


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


ib = load(SDK / "schema" / "info-baseline.json")["endpoints"]
manifest = load(LOCAL / "registry" / "manifest.json")
by_uri = {}
for ep in manifest["endpoints"]:
    by_uri.setdefault(("/" + ep["uri"].strip("/")).upper(), []).append(ep)


def has_schema(entry, prod):
    sub = entry.get(prod)
    if not isinstance(sub, dict):
        return False
    sch = sub.get("schema")
    if not isinstance(sch, dict):
        return False
    return any(k != "$schema" for k in sch)


INFO_404_EXCEPTIONS = {"/DB/IEHG-GL-M1", "/DB/IEHG-PSS-M1", "/DB/IEHG-TRUSS-M1"}
PRODMAP = {"gen": "GEN_NX", "civil": "CIVIL_NX"}

tier1, under, over, no_probe = [], [], [], []
for route, entry in sorted(ib.items()):
    u = route.upper()
    if not u.startswith("/DB/") or u in INFO_404_EXCEPTIONS:
        continue
    srv_gen, srv_civ = has_schema(entry, "gen"), has_schema(entry, "civil")
    ours = by_uri.get(u, [])
    if not ours:
        continue
    our_gen = any("GEN_NX" in x["products"] for x in ours)
    our_civ = any("CIVIL_NX" in x["products"] for x in ours)
    e = ours[0]
    rec = dict(route=route, key=e["key"], solver=e["solver"], srv_gen=srv_gen, srv_civ=srv_civ,
               our_gen=our_gen, our_civ=our_civ, availability=e["availability"],
               unavailable_on=e["unavailable_on"])
    if u.endswith("-M1") and e["solver"] == "HYPER_S" and srv_civ and not srv_gen and our_gen and not our_civ:
        tier1.append(rec)
    elif srv_civ and not our_civ:
        under.append(rec)
    elif srv_gen and not our_gen:
        under.append(rec)
    elif our_civ and not srv_civ and not srv_gen:
        # both products 404 on /info -> no evidence either way, skip
        no_probe.append(rec)
    elif our_civ and not srv_civ:
        over.append(rec)
    elif our_gen and not srv_gen:
        over.append(rec)

print("=" * 100)
print(f"TIER 1 (schema-presence basis) — Hyper-S inverted: {len(tier1)}")
print("=" * 100)
for r in tier1:
    print(f"  {r['route']:24s} {r['key']:22s} ours=GEN_NX  server: gen=no-schema civil=schema")
print()
print("=" * 100)
print(f"TIER 2a — server has a schema for a product we do NOT declare: {len(under)}")
print("=" * 100)
for r in under:
    print(f"  {r['route']:24s} {r['key']:22s} srv(gen={str(r['srv_gen']):5s} civil={str(r['srv_civ']):5s}) "
          f"ours(gen={str(r['our_gen']):5s} civil={str(r['our_civ']):5s}) avail={r['availability']}")
print()
print("=" * 100)
print(f"TIER 2b — we declare a product with no server schema (and the other product HAS one): {len(over)}")
print("=" * 100)
for r in over:
    print(f"  {r['route']:24s} {r['key']:22s} srv(gen={str(r['srv_gen']):5s} civil={str(r['srv_civ']):5s}) "
          f"ours(gen={str(r['our_gen']):5s} civil={str(r['our_civ']):5s}) avail={r['availability']}")
print()
print(f"skipped (no schema on either product): {len(no_probe)}")

json.dump(dict(tier1=tier1, tier2_under=under, tier2_over=over, skipped=no_probe),
          open(LOCAL / ".tmp_analysis" / "product_matrix_v2.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\nwrote product_matrix_v2.json")
