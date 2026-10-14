"""Verify the /info status codes for the 31 routes: does CIVIL_NX really answer?"""
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
routes = """/db/ACTL-M1 /db/BCGA-M1 /db/BCGD-M1 /db/DCTL /db/DSTL /db/EIGV-M1 /db/EPMT-M1
/db/EPSE /db/ESSF /db/HHCT-M1 /db/IEHG-BEAM-M1 /db/IMFM-M1 /db/LENG /db/LLAN /db/LLANid
/db/LTSR /db/MATL-M1 /db/MBTP /db/MEMB /db/NLCT-M1 /db/NLNK-M1 /db/POGD-M1 /db/POLC-M1
/db/POSL /db/POSP /db/STCT-M1 /db/STYP-M1 /db/THGC-M1 /db/THIS-M1 /db/THOO-M1 /db/WMAK""".split()

print(f"{'route':24s} {'gen_status':>10s} {'civil_status':>12s}  civil_schema?")
for r in routes:
    e = ib.get(r)
    if e is None:
        print(f"  {r:24s} *** not in baseline ***")
        continue
    g = (e.get("gen") or {}).get("status")
    c = (e.get("civil") or {}).get("status")
    cs = (e.get("civil") or {}).get("schema")
    has = "yes" if isinstance(cs, dict) and any(k != "$schema" for k in cs) else "no"
    print(f"  {r:24s} {str(g):>10s} {str(c):>12s}  {has}")

# global status distribution
allst = Counter()
for route, e in ib.items():
    for p in ("gen", "civil"):
        allst[(p, (e.get(p) or {}).get("status"))] += 1
print()
print("global /info status distribution:", dict(allst))

# How many routes answer civil but not gen, and vice versa
cg = [r for r, e in ib.items() if (e.get("civil") or {}).get("status") == 200 and (e.get("gen") or {}).get("status") != 200]
gc = [r for r, e in ib.items() if (e.get("gen") or {}).get("status") == 200 and (e.get("civil") or {}).get("status") != 200]
print(f"routes answering /info on CIVIL only: {len(cg)}")
print(f"routes answering /info on GEN only:   {len(gc)}")
print("  CIVIL-only:", cg[:40])
print("  GEN-only:  ", gc[:40])
