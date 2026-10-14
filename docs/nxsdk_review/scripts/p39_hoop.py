"""Locate HOOP_TYPE's exact path in REBC/REBR so the new test can assert on it."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REG = Path(r"E:\MCP\MMCP\registry")


def walk(node, path="", depth=0):
    if depth > 8:
        return
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else k
            if k == "HOOP_TYPE":
                print(f"  PATH: {p}")
                print(f"    {json.dumps(v, ensure_ascii=False)}")
            walk(v, p, depth + 1)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk(v, f"{path}[{i}]", depth + 1)


for key, rel in [("DB.REBC", r"schema\common\db\REBC.json"),
                 ("DB.REBR", r"schema\common\db\REBR.json")]:
    print("=" * 80)
    print(key)
    print("=" * 80)
    d = json.loads((REG / rel).read_text(encoding="utf-8"))
    walk(d["schema"])
    # also show the Assign wrapper shape
    props = d["schema"]["properties"]["Assign"]
    print("  Assign keys:", list(props))
