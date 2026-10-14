"""MD-29 (/DESIGN/RC/KDS-41-20-2022/REBB) 侦察：契约怎么说、我方 schema 什么形状。"""
import json
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
SDK = REPO / ".tmp_nxsdk"

c = yaml.safe_load((SDK / "contracts" / "endpoints" / "design-rc-kds-41-20-2022-rebb.yaml").read_text(encoding="utf-8"))
print("contract id:", c.get("id"), "| endpoint:", c.get("endpoint"), "| products:", c.get("products"))
print("verification:", json.dumps(c.get("verification"), ensure_ascii=False)[:200])
print()
print("=== manualDefects ===")
print(json.dumps(c.get("manualDefects"), ensure_ascii=False, indent=1)[:3000])
print()
print("=== fields ===")


def walk(fields, path="", depth=0):
    for f in fields or []:
        if not isinstance(f, dict):
            continue
        p = f"{path}.{f['key']}" if path else f["key"]
        extra = ""
        for k in ("type", "requirement", "provenance", "documentedOptional"):
            if f.get(k) is not None:
                extra += f" {k}={f[k]!r}"
        print(f"  {'  ' * depth}{p}:{extra}")
        walk(f.get("properties"), p, depth + 1)
        if isinstance(f.get("items"), list):
            walk(f["items"], f"{p}[]", depth + 1)


walk(c.get("fields"))

print()
print("=== ours ===")
man = {e["key"]: e for e in json.loads((REPO / "registry" / "manifest.json").read_text(encoding="utf-8"))["endpoints"]}
key = "DESIGN.RC.KDS-41-20-2022.REBB"
entry = man[key]
print("schema:", entry.get("schema"), "| products:", entry["products"], "| avail:", entry["availability"])
if entry.get("schema"):
    d = json.loads((REPO / "registry" / entry["schema"]).read_text(encoding="utf-8"))
    print(json.dumps(d.get("schema"), ensure_ascii=False, indent=1)[:2200])
