"""Insert the 6 new CIVIL_NX candidates into p143's CIVIL_CODES tuple (sorted)."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
p143 = Path(r"E:\MCP\MMCP\tests\test_midas_write_coverage_p143.py")
WRITE = "--write" in sys.argv
NEW_KEYS = ["DB.DCTL", "DB.DSTL", "DB.LENG", "DB.MBTP", "DB.POSL", "DB.WMAK"]

lines = p143.read_text(encoding="utf-8").splitlines(keepends=True)
start = next(i for i, line in enumerate(lines) if line.startswith("CIVIL_CODES = ("))
end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == ")")
existing = {lines[i].strip().strip(",").strip('"') for i in range(start + 1, end) if lines[i].strip().startswith('"')}
print(f"CIVIL_CODES currently has {len(existing)} entries; block lines {start + 1}..{end + 1}")

added = []
for key in NEW_KEYS:
    if key in existing:
        print(f"  already present: {key}")
        continue
    target = next(
        (i for i in range(start + 1, end)
         if lines[i].strip().startswith('"') and lines[i].strip().strip(",").strip('"') > key),
        end,
    )
    lines.insert(target, f'    "{key}",\n')
    end += 1
    added.append(key)

if added:
    if WRITE:
        p143.write_text("".join(lines), encoding="utf-8", newline="\n")
    print(f"{'WROTE' if WRITE else 'WOULD WRITE'} CIVIL_CODES += {added}")
else:
    print("nothing to add")
