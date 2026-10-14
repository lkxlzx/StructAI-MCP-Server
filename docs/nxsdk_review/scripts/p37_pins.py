"""Update the regression pins that legitimately shift when 21 endpoints move GEN_NX -> CIVIL_NX
and 12 lose CIVIL_NX.

Derived (not guessed) by replicating each test's own computation against the project's registry:
    GEN_NX   candidates=78  blocked=474   (was 495; -21)
    CIVIL_NX candidates=68  blocked=440   (was 431; +21 -12 = +9)
    CIVIL_DESIGNER candidates=0 blocked=31 (unchanged)
Candidates are unchanged because none of the moved endpoints ever qualified as a candidate.
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
TESTS = Path(r"E:\MCP\MMCP\tests")
WRITE = "--write" in sys.argv

OLD_FLAT = '{"GEN_NX": 495, "CIVIL_NX": 431, "CIVIL_DESIGNER": 31}'
NEW_FLAT = '{"GEN_NX": 474, "CIVIL_NX": 440, "CIVIL_DESIGNER": 31}'

EDITS = [
    # (file, old, new)
    ("test_midas_write_coverage_p142.py", '"GEN_NX": 495,', '"GEN_NX": 474,'),
    ("test_midas_write_coverage_p142.py", '"CIVIL_NX": 431,', '"CIVIL_NX": 440,'),
    ("test_midas_write_coverage_p144.py", OLD_FLAT, NEW_FLAT),
    ("test_midas_write_coverage_p145.py", OLD_FLAT, NEW_FLAT),
    ("test_midas_write_coverage_p146.py", OLD_FLAT, NEW_FLAT),
    ("test_midas_write_coverage_p147.py", OLD_FLAT, NEW_FLAT),
    ("test_midas_write_coverage_p148.py", OLD_FLAT, NEW_FLAT),
    ("test_midas_endpoint_methods_p149.py", OLD_FLAT, NEW_FLAT),
]

for name, old, new in EDITS:
    p = TESTS / name
    text = p.read_text(encoding="utf-8")
    n = text.count(old)
    if n == 0:
        print(f"  SKIP (not found)  {name}: {old[:40]}")
        continue
    if n > 1:
        print(f"  !! {n} occurrences in {name}: {old[:40]}")
    if WRITE:
        p.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    print(f"  {'WROTE' if WRITE else 'WOULD'}  {name}: {old[:34]} -> {new[:34]}")

print()
print(f"{'applied' if WRITE else 'dry-run'}: {len(EDITS)} edits")
