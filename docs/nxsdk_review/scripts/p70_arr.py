"""What does the contract declare for REBC vMAIN_BAR and REBB vMAIN_BAR_BOT? And what does /info say?"""
import json
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
SDK = REPO / ".tmp_nxsdk"
ib = json.loads((SDK / "schema" / "info-baseline.json").read_text(encoding="utf-8"))


def contract_items(fname):
    c = yaml.safe_load((SDK / "contracts" / "endpoints" / fname).read_text(encoding="utf-8"))

    def find(node):
        if isinstance(node, dict):
            if node.get("key") == "ITEMS" and isinstance(node.get("properties"), list):
                return node
            for v in node.values():
                r = find(v)
                if r:
                    return r
        elif isinstance(node, list):
            for v in node:
                r = find(v)
                if r:
                    return r
        return None

    return find(c.get("fields", []))


def walk(node, names, path=""):
    for f in node.get("properties") or []:
        p = f"{path}.{f['key']}" if path else f["key"]
        if f["key"] in names:
            print(f"  CONTRACT {p}: type={f.get('type')!r} requirement={f.get('requirement')!r}")
            print(f"      items={json.dumps(f.get('items'), ensure_ascii=False)[:300]}")
            print(f"      properties={[x['key'] for x in (f.get('properties') or []) if isinstance(x, dict)]}")
        walk(f, names, p)


for fname, names in [("db-rebc.yaml", {"vMAIN_BAR"}), ("db-rebb.yaml", {"vMAIN_BAR_BOT", "vMAIN_BAR_TOP"})]:
    print("=" * 80)
    print(fname)
    print("=" * 80)
    walk(contract_items(fname), names)

print()
print("=" * 80)
print("SERVER /info declarations")
print("=" * 80)


def server_props(route):
    e = (ib["endpoints"].get(route) or {}).get("gen") or {}
    s = e.get("schema") or {}
    root = next((v for k, v in s.items() if k != "$schema"), {})
    return (root.get("properties") or {}).get("ITEMS", {}).get("items", {}).get("properties", {})


def show(route, path):
    node = server_props(route)
    for part in path:
        node = (node.get(part) or {})
        if "items" in node and isinstance(node["items"], dict):
            node = node["items"]
        node = node.get("properties", {})
    print(f"  {route} {'.'.join(path)} -> {json.dumps(node, ensure_ascii=False)[:400]}")


show("/db/REBC", ["vMAIN_BAR"])
show("/db/REBB", ["BAR_SECTOR_I", "vMAIN_BAR_BOT"])
show("/db/REBB", ["BAR_SECTOR_I", "SHEAR_BAR"])
