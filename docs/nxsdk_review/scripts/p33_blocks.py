"""Show the full blocks to be patched for the 3 confirmed type fixes."""
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REG = Path(r"E:\MCP\MMCP\registry")

for rel, field in [
    (r"schema\common\db\SLANOP.json", "OPT_STRADD"),
    (r"schema\common\db\REBC.json", "HOOP_TYPE"),
    (r"schema\common\db\REBR.json", "HOOP_TYPE"),
]:
    p = REG / rel
    txt = p.read_text(encoding="utf-8")
    m = re.search(r'([ \t]*)"' + re.escape(field) + r'"\s*:', txt)
    if not m:
        print(f"{rel}: {field} NOT FOUND")
        continue
    start = m.start()
    # walk forward to the matching closing brace of this property's value object
    i = txt.index("{", m.end())
    depth = 0
    for j in range(i, len(txt)):
        if txt[j] == "{":
            depth += 1
        elif txt[j] == "}":
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    line_no = txt[:start].count("\n") + 1
    print("=" * 92)
    print(f"{rel}  ::  {field}   (lines {line_no}..{txt[:end].count(chr(10))+1})")
    print("=" * 92)
    print(txt[start:end])
    print()
