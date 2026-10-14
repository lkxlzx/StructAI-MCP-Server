"""Remove the single extra blank line left where the module-level guard used to sit."""
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
TOOLS = Path(r"E:\MCP\MMCP\registry\tools")

fixed = []
for p in sorted(TOOLS.glob("*.py")):
    text = p.read_text(encoding="utf-8")
    if 'if __name__ == "__main__":' not in text or "cp949/cp936" not in text:
        continue
    # locate the end of the top-level import block
    lines = text.splitlines()
    last_import = -1
    for i, line in enumerate(lines):
        if re.match(r"^(?:import|from) \S", line):
            last_import = i
        elif last_import >= 0 and line.strip() and not line.startswith(("import ", "from ")):
            break
    if last_import < 0:
        continue
    # collapse 2 blank lines right after the import block to 1
    if lines[last_import + 1 : last_import + 3] == ["", ""]:
        del lines[last_import + 2]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        fixed.append(p.name)

print(f"collapsed extra blank line in {len(fixed)} tools")
for name in fixed:
    print("  ", name)
