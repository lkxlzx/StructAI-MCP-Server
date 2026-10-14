"""Inspect the DB.PRES write template — does it send DIRECTION?"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
d = json.loads((REPO / "registry" / "live" / "write_templates.json").read_text(encoding="utf-8"))

print("top keys:", list(d)[:12])


def walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            if "PRES" in str(k):
                print(f"  [{path}.{k}] {json.dumps(v, ensure_ascii=False)[:900]}")
            walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk(v, f"{path}[{i}]")


walk(d)
print()
print("=== grep PRES keys ===")
raw = json.dumps(d, ensure_ascii=False)
import re

for m in re.finditer(r'"[^"]*PRES[^"]*"\s*:', raw):
    print("  ", raw[max(0, m.start() - 60):m.end() + 300].replace("\n", " ")[:360])
