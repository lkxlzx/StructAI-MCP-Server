"""Full DB.PRES write template entry + how check_write_templates validates templates."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
d = json.loads((REPO / "registry" / "live" / "write_templates.json").read_text(encoding="utf-8"))
t = d["templates"]["DB.PRES"]
print("=== templates.DB.PRES ===")
print(json.dumps(t, ensure_ascii=False, indent=1)[:2600])

print()
print("=== check_write_templates.py 是否用 Schema 校验 body ===")
src = (REPO / "registry" / "tools" / "check_write_templates.py").read_text(encoding="utf-8")
for i, line in enumerate(src.splitlines(), 1):
    low = line.lower()
    if "schema" in low and ("valid" in low or "check" in low or "engine" in low or "jsonschema" in low):
        print(f"  {i}: {line.strip()[:130]}")
