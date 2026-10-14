"""Inspect /info shapes for PRES FORCES / EDGE_LOADS / VECTORS, and the contract's own definitions."""
import json
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")

ib = json.loads((REPO / ".tmp_nxsdk" / "schema" / "info-baseline.json").read_text(encoding="utf-8"))
e = ib["endpoints"]["/db/PRES"]["gen"]
sch = e["schema"]
root = next(v for k, v in sch.items() if k != "$schema")
ip = root["properties"]["ITEMS"]["items"]["properties"]
for f in ("VECTORS", "FORCES", "EDGE_LOADS", "EDGE_FACE", "CMD", "ELEM_TYPE", "FACE_EDGE_TYPE"):
    print(f"/info {f}: {json.dumps(ip.get(f), ensure_ascii=False)[:320]}")

print()
c = yaml.safe_load((REPO / ".tmp_nxsdk" / "contracts" / "endpoints" / "db-pres.yaml").read_text(encoding="utf-8"))


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
print("--- contract ITEMS.properties ---")
for p in items["properties"]:
    print(f"  {p['key']:16s} {json.dumps({k: v for k, v in p.items() if k != 'key'}, ensure_ascii=False)[:400]}")

print()
print("--- our PRES.json ITEMS item (full) ---")
d = json.loads((REPO / "registry" / "schema" / "common" / "db" / "PRES.json").read_text(encoding="utf-8"))
print(json.dumps(d["schema"]["PRES"]["properties"]["ITEMS"], ensure_ascii=False, indent=1))
