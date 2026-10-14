"""Read the full db-pres.yaml DIRECTION entry, sdkRules and any required-set statement."""
import json
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
c = yaml.safe_load((REPO / ".tmp_nxsdk" / "contracts" / "endpoints" / "db-pres.yaml")
                   .read_text(encoding="utf-8"))


def find_items(node):
    if isinstance(node, dict):
        if node.get("key") == "ITEMS" and isinstance(node.get("properties"), list):
            return node
        for v in node.values():
            r = find_items(v)
            if r:
                return r
    elif isinstance(node, list):
        for v in node:
            r = find_items(v)
            if r:
                return r
    return None


items = find_items(c["fields"])
print("=== ITEMS entry (non-properties) ===")
print(json.dumps({k: v for k, v in items.items() if k != "properties"}, ensure_ascii=False, indent=1))
print()
print("=== DIRECTION full ===")
for p in items["properties"]:
    if p["key"] == "DIRECTION":
        print(json.dumps(p, ensure_ascii=False, indent=1))
print()
print("=== requirement per member ===")
for p in items["properties"]:
    print(f"  {p['key']:16s} requirement={p.get('requirement')!r:12s} safeToOmit={p.get('safeToOmit')!r} documentedOptional={p.get('documentedOptional')!r}")
print()
print("=== sdkRules (all) ===")
print(json.dumps(c.get("sdkRules"), ensure_ascii=False, indent=1))
print()
print("=== top-level keys ===", list(c))
print("recordKey:", json.dumps(c.get("recordKey"), ensure_ascii=False))
print("knownDefects:", json.dumps(c.get("knownDefects"), ensure_ascii=False)[:400])
