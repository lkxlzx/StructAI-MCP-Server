"""Fix the remaining CIVIL_NX pins: covered 62 -> 68, and p151's field scoping."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
TESTS = Path(r"E:\MCP\MMCP\tests")
WRITE = "--write" in sys.argv

EDITS = [
    ("test_midas_write_coverage_p144.py", "assert civil.covered == 62", "assert civil.covered == 68"),
    ("test_midas_write_coverage_p145.py", "assert civil.covered == 62", "assert civil.covered == 68"),
    (
        "test_midas_write_coverage_p146.py",
        'assert civil.covered == len(_measured(CANDIDATES_BY_PRODUCT["CIVIL_NX"])) == 62',
        'assert civil.covered == len(_measured(CANDIDATES_BY_PRODUCT["CIVIL_NX"])) == 68',
    ),
    (
        "test_midas_write_coverage_p147.py",
        'assert civil.covered == len(_measured(CANDIDATES_BY_PRODUCT["CIVIL_NX"])) == 62',
        'assert civil.covered == len(_measured(CANDIDATES_BY_PRODUCT["CIVIL_NX"])) == 68',
    ),
    (
        "test_midas_write_coverage_p148.py",
        "assert civil.covered == len(civil_keys) == 62",
        "assert civil.covered == len(civil_keys) == 68",
    ),
    (
        "test_midas_put_edits_p151.py",
        'AVAILABILITY_FIELDS = ("availability", "unavailable_on")',
        'AVAILABILITY_FIELDS = ("availability",)',
    ),
]

for name, old, new in EDITS:
    p = TESTS / name
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        print(f"  {'!! ' + str(count) + ' hits' if count else 'SKIP'}  {name}: {old[:52]}")
        continue
    if WRITE:
        p.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    print(f"  {'WROTE' if WRITE else 'WOULD'}  {name}: {old[:44]} -> {new[:44]}")

print()
print("applied" if WRITE else "dry-run")
