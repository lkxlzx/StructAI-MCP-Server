"""Inverse check: our CIVIL_NX-only endpoints vs SDK claims that they answer on Gen NX.

Subagent B reported (from docs/live_verification_notes.md D-06): '32 declared-Civil-only endpoints
answer on Gen NX too' — a route-level GET finding, not /info-based.
"""
import json
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")
LOCAL = Path(r"E:\MCP\MMCP")
SDK = LOCAL / ".tmp_nxsdk"

manifest = json.load(open(LOCAL / "registry" / "manifest.json", encoding="utf-8"))
civil_only = [e for e in manifest["endpoints"] if e["products"] == ["CIVIL_NX"]]
gen_only = [e for e in manifest["endpoints"] if e["products"] == ["GEN_NX"]]
print(f"our CIVIL_NX-only endpoints: {len(civil_only)}")
print(f"our GEN_NX-only   endpoints: {len(gen_only)}")
print()

# SDK claims: coverage.json products + contracts products
cov = {e["endpoint"].upper(): e for e in json.load(open(SDK / "docs" / "coverage.json", encoding="utf-8"))["endpoints"]}
con = {}
for p in sorted((SDK / "contracts" / "endpoints").glob("*.yaml")):
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    con[d["endpoint"].upper()] = d
ib = json.load(open(SDK / "schema" / "info-baseline.json", encoding="utf-8"))["endpoints"]

print("=" * 104)
print("A) our CIVIL_NX-only endpoints where the SDK claims GEN too (=> we may under-declare GEN_NX)")
print("=" * 104)
n = 0
for e in sorted(civil_only, key=lambda x: x["key"]):
    route = ("/" + e["uri"].strip("/")).upper()
    reasons = []
    c = con.get(route)
    if c and "gen" in (c.get("products") or []):
        reasons.append(f"契约 products={c['products']}")
    cv = cov.get(route)
    if cv and "gen" in (cv.get("products") or []):
        reasons.append(f"coverage products={cv['products']}")
    ent = ib.get(route) or ib.get(route.lower())
    if ent and (ent.get("gen") or {}).get("status") == 200:
        reasons.append("/info gen=200")
    if reasons:
        n += 1
        print(f"  {e['key']:34s} avail={e['availability']:10s} unavail={str(e['unavailable_on']):20s} | {'; '.join(reasons)}")
print(f"  count: {n}")

print()
print("=" * 104)
print("B) our GEN_NX-only endpoints where the SDK claims CIVIL too (=> we may under-declare CIVIL_NX)")
print("=" * 104)
m = 0
for e in sorted(gen_only, key=lambda x: x["key"]):
    route = ("/" + e["uri"].strip("/")).upper()
    reasons = []
    c = con.get(route)
    if c and "civil" in (c.get("products") or []):
        reasons.append(f"契约 products={c['products']}")
    cv = cov.get(route)
    if cv and "civil" in (cv.get("products") or []):
        reasons.append(f"coverage products={cv['products']}")
    ent = ib.get(route) or ib.get(route.lower())
    if ent and (ent.get("civil") or {}).get("status") == 200:
        reasons.append("/info civil=200")
    if reasons:
        m += 1
        print(f"  {e['key']:34s} solver={(e['solver'] or '-'):9s} avail={e['availability']:10s} | {'; '.join(reasons)}")
print(f"  count: {m}")
