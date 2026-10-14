import json
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")
LOCAL = Path(r"E:\MCP\MMCP")
SDK = LOCAL / ".tmp_nxsdk"

ib = json.load(open(SDK / "schema" / "info-baseline.json", encoding="utf-8"))
print("capturedAt:", ib["capturedAt"])
for r in ("/db/POSP", "/db/RPSC", "/db/STBK", "/db/ACTL-M1"):
    e = ib["endpoints"].get(r)
    print(f"\n--- {r} ---")
    if not e:
        print("  absent")
        continue
    for p in ("gen", "civil"):
        sub = e.get(p)
        if sub is None:
            print(f"  {p}: (no entry)")
            continue
        sch = sub.get("schema") or {}
        keys = [k for k in sch if k != "$schema"]
        props = []
        for k in keys:
            if isinstance(sch[k], dict):
                props = list((sch[k].get("properties") or {}))
        print(f"  {p}: status={sub.get('status')} root={keys} nprops={len(props)} {props[:12]}")

c = yaml.safe_load((SDK / "contracts" / "endpoints" / "db-posp.yaml").read_text(encoding="utf-8"))
print("\ncontract db-posp.yaml: products =", c.get("products"))
print("  verification:", json.dumps(c.get("verification"), ensure_ascii=False)[:400])
print("  productsEvidence:", json.dumps(c.get("productsEvidence"), ensure_ascii=False)[:500])

man = json.load(open(LOCAL / "registry" / "manifest.json", encoding="utf-8"))
for e in man["endpoints"]:
    if e["key"] in ("DB.POSP", "DB.RPSC"):
        print(f"\nours {e['key']}: products={e['products']} avail={e['availability']} "
              f"verified_on={e['verified_on']} unavailable_on={e['unavailable_on']}")
