"""Compare our /db/PRES schema against the SDK's reviewed contract (MD-17)."""
import json
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")

# ---- SDK contract ----
c = yaml.safe_load((REPO / ".tmp_nxsdk" / "contracts" / "endpoints" / "db-pres.yaml")
                   .read_text(encoding="utf-8"))
print("=" * 92)
print("SDK contract db-pres.yaml")
print("=" * 92)
print("products:", c.get("products"))
print("manualDefects:", json.dumps(c.get("manualDefects"), ensure_ascii=False, indent=1)[:1500])
print()
print("sdkRules:", json.dumps(c.get("sdkRules"), ensure_ascii=False, indent=1)[:1200])
print()
print("normalize_defaults:", json.dumps(c.get("normalize_defaults"), ensure_ascii=False)[:600])


def walk(node, path="", depth=0):
    if depth > 6:
        return
    if isinstance(node, dict):
        key = node.get("key")
        if key in ("DIRECTION", "TYPE", "FORCES", "VECTORS", "PROJECTION"):
            print(f"  [{path}] {json.dumps({k: v for k, v in node.items() if k != 'fields'}, ensure_ascii=False)[:400]}")
        for k, v in node.items():
            walk(v, f"{path}.{k}" if path else str(k), depth + 1)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk(v, f"{path}[{i}]", depth + 1)


print()
print("--- contract fields of interest ---")
for f in c.get("fields", []):
    walk(f, f.get("key", ""))

# ---- our schema ----
d = json.loads((REPO / "registry" / "schema" / "common" / "db" / "PRES.json").read_text(encoding="utf-8"))
print()
print("=" * 92)
print("our PRES.json")
print("=" * 92)
print("top keys:", list(d))
sch = d["schema"]
print("schema root keys:", list(sch))
print(json.dumps(sch, ensure_ascii=False, indent=1)[:2600])
