"""Show current products/verified_on/unavailable_on for every endpoint in the civil probe."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
probe = json.loads((REPO / "registry" / "live" / "civil_product_probe.json").read_text(encoding="utf-8"))
man = {e["key"]: e for e in json.loads((REPO / "registry" / "manifest.json").read_text(encoding="utf-8"))["endpoints"]}

print(f"{'key':24s} {'code':>4s} {'verdict':14s} {'products':32s} {'avail':10s} verified_on / unavailable_on")
for key, row in probe["endpoints"].items():
    e = man.get(key)
    if not e:
        print(f"  !! {key} NOT IN MANIFEST")
        continue
    print(f"{key:24s} {row['status_code']:>4d} {row['verdict']:14s} "
          f"{','.join(e['products']):32s} {e['availability']:10s} "
          f"v={e['verified_on']} u={e['unavailable_on']}")
