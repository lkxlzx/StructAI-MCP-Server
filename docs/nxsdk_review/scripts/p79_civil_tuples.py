"""Insert the 6 new CIVIL_NX candidate keys into every test file that pins the CIVIL_NX tuple.

Two shapes exist:
  * p142  -> `CIVIL_CODES = ( ... )` referenced as `"CIVIL_NX": CIVIL_CODES`
  * p144-148 -> an inline `"CIVIL_NX": ( ... )` block
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
TESTS = Path(r"E:\MCP\MMCP\tests")
WRITE = "--write" in sys.argv
NEW_KEYS = ["DB.DCTL", "DB.DSTL", "DB.LENG", "DB.MBTP", "DB.POSL", "DB.WMAK"]


def block_bounds(lines: list[str], start: int) -> tuple[int, int]:
    """Return (first_entry_index, closing_paren_index) for the tuple opened at/after `start`."""
    open_idx = next(i for i in range(start, len(lines)) if "(" in lines[i])
    depth = 0
    for i in range(open_idx, len(lines)):
        depth += lines[i].count("(") - lines[i].count(")")
        if depth == 0:
            return open_idx + 1, i
    raise AssertionError("unbalanced tuple")


def insert_keys(lines: list[str], first: int, close: int) -> tuple[list[str], list[str]]:
    existing = {
        lines[i].strip().strip(",").strip('"')
        for i in range(first, close)
        if lines[i].strip().startswith('"')
    }
    added = []
    for key in NEW_KEYS:
        if key in existing:
            continue
        target = next(
            (
                i
                for i in range(first, close)
                if lines[i].strip().startswith('"') and lines[i].strip().strip(",").strip('"') > key
            ),
            close,
        )
        lines.insert(target, f'    "{key}",\n')
        close += 1
        added.append(key)
    return lines, added


TARGETS = [
    ("test_midas_write_coverage_p142.py", "CIVIL_CODES = ("),
    ("test_midas_write_coverage_p144.py", '"CIVIL_NX": ('),
    ("test_midas_write_coverage_p145.py", '"CIVIL_NX": ('),
    ("test_midas_write_coverage_p146.py", '"CIVIL_NX": ('),
    ("test_midas_write_coverage_p147.py", '"CIVIL_NX": ('),
    ("test_midas_write_coverage_p148.py", '"CIVIL_NX": ('),
]

for name, anchor in TARGETS:
    p = TESTS / name
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.strip().startswith(anchor)), None)
    if start is None:
        print(f"  !! {name}: anchor {anchor!r} not found")
        continue
    first, close = block_bounds(lines, start)
    lines, added = insert_keys(lines, first, close)
    if added:
        if WRITE:
            p.write_text("".join(lines), encoding="utf-8", newline="\n")
        print(f"  {'WROTE' if WRITE else 'WOULD'}  {name}: += {added}")
    else:
        print(f"  (already present)  {name}")

print()
print("applied" if WRITE else "dry-run")
