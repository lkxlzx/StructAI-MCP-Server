"""3-way field comparison for /db/PRES: our schema vs server /info vs SDK contract."""
import json
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")

# --- ours ---
d = json.loads((REPO / "registry" / "schema" / "common" / "db" / "PRES.json").read_text(encoding="utf-8"))
ours_root = d["schema"]["PRES"]
ours_item = ours_root["properties"]["ITEMS"]["items"]
print("OURS  ITEMS item keys:", list(ours_item))
print("OURS  required:", ours_item.get("required"))
print("OURS  fields:")
for k, v in ours_item["properties"].items():
    print(f"    {k:18s} type={v.get('type')!s:9s} enum={v.get('enum')} default={v.get('default')!r}")

# --- server /info ---
ib = json.loads((REPO / ".tmp_nxsdk" / "schema" / "info-baseline.json").read_text(encoding="utf-8"))
print()
for prod in ("gen", "civil"):
    e = ib["endpoints"]["/db/PRES"].get(prod)
    sch = (e or {}).get("schema") or {}
    root = next((v for k, v in sch.items() if k != "$schema"), {})
    props = root.get("properties", {})
    items = props.get("ITEMS", {})
    it = items.get("items", {}) if isinstance(items, dict) else {}
    ip = it.get("properties", {})
    print(f"SERVER /info [{prod}] ITEMS item fields ({len(ip)}):")
    for k, v in ip.items():
        print(f"    {k:18s} type={v.get('type')!s:9s} desc={str(v.get('description'))[:52]!r}")

# --- contract ---
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


items = find_items(c.get("fields", []))
print()
print("CONTRACT ITEMS members:", [p["key"] for p in items["properties"]])
print("CONTRACT ITEMS required?:", items.get("requirement"))
for p in items["properties"]:
    if p["key"] in ("DIRECTION", "VECTORS", "PSLT_KEY", "OPT_PROJECTION"):
        print(f"    {p['key']:18s} {json.dumps({k: v for k, v in p.items() if k != 'key'}, ensure_ascii=False)[:330]}")
