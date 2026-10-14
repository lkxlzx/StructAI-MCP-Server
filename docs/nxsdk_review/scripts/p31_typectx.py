"""Show the raw JSON text around each field we intend to retype (for minimal-diff patching)."""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REG = Path(r"E:\MCP\MMCP\registry")

TARGETS = [
    (r"schema\products\gen_nx\db\EPSE.json", "LOADING_AREA_GROUP"),
    (r"schema\products\gen_nx\db\EPST.json", "LOADING_AREA_GROUP"),
    (r"schema\products\gen_nx\db\SLANOP.json", "OPT_STRADD"),
    (r"schema\common\db\RPSC.json", "LBAR_INC_FC"),
    (r"schema\common\db\NLLP.json", "SEIS_TYPE"),
    (r"schema\common\db\REBC.json", "HOOP_TYPE"),
    (r"schema\common\db\REBR.json", "HOOP_TYPE"),
]

for rel, field in TARGETS:
    p = REG / rel
    print("=" * 90)
    print(f"{rel}  ::  {field}")
    print("=" * 90)
    if not p.exists():
        print("  MISSING")
        continue
    txt = p.read_text(encoding="utf-8")
    for m in re.finditer(r'"' + re.escape(field) + r'"\s*:', txt):
        start = max(0, m.start() - 80)
        end = min(len(txt), m.end() + 260)
        snippet = txt[start:end]
        line_no = txt[: m.start()].count("\n") + 1
        print(f"  --- occurrence at line {line_no} ---")
        print("  " + snippet.replace("\n", "\n  "))
        print()
