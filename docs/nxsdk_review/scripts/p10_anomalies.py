"""Inspect the 6 zero-field local schemas and the 31 NO_LOCAL_SCHEMA manifest entries."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

LOCAL = Path(r"E:\MCP\MMCP")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


print("=" * 74)
print("A) raw head of the 6 zero-field schemas")
print("=" * 74)
for rel in [
    r"registry\schema\products\gen_nx\db\SWIND.json",
    r"registry\schema\products\gen_nx\db\SSEIS.json",
    r"registry\schema\common\db\REBB.json",
    r"registry\schema\common\db\REBC.json",
    r"registry\schema\common\db\REBW.json",
    r"registry\schema\common\db\REBR.json",
]:
    p = LOCAL / rel
    print(f"\n--- {rel} ---")
    if not p.exists():
        print("  MISSING")
        continue
    txt = p.read_text(encoding="utf-8")
    print(f"  size={len(txt)}")
    print(txt[:1400])

print()
print("=" * 74)
print("B) manifest entries for the 31 NO_LOCAL_SCHEMA routes")
print("=" * 74)
routes = """/db/ACTL-M1 /db/BCGA-M1 /db/BCGD-M1 /db/DCTL /db/DSTL /db/EIGV-M1 /db/EPMT-M1
/db/EPSE /db/ESSF /db/HHCT-M1 /db/IEHG-BEAM-M1 /db/IMFM-M1 /db/LENG /db/LLAN /db/LLANid
/db/LTSR /db/MATL-M1 /db/MBTP /db/MEMB /db/NLCT-M1 /db/NLNK-M1 /db/POGD-M1 /db/POLC-M1
/db/POSL /db/POSP /db/STCT-M1 /db/STYP-M1 /db/THGC-M1 /db/THIS-M1 /db/THOO-M1 /db/WMAK""".split()
want = {r.upper() for r in routes}
manifest = load(LOCAL / "registry" / "manifest.json")
for ep in manifest["endpoints"]:
    u = "/" + ep["uri"].strip("/")
    if u.upper() in want:
        print(f"  {u:28s} key={ep['key']:22s} prod={','.join(ep['products']):22s} schema={ep['schema']!r:60s} src={ep['schema_source']}")
