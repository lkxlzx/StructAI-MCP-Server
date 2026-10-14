"""Update the regression pins for the CIVIL_NX probe batch.

Derived values (computed with each test's own logic against the project's registry):
    CIVIL_NX candidates 68 -> 74   (the 6 new CIVIL_NX endpoints that are candidates)
    CIVIL_NX blocked   440 -> 452  (+18 gained CIVIL_NX - 6 candidates)
    availability verified 503 -> 509, untested 110 -> 104 (6 OPE/VIEW upgraded)
    NO_GET 109 -> 103 (those 6 have no GET, and are now `verified` so no longer counted)
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
TESTS = Path(r"E:\MCP\MMCP\tests")
WRITE = "--write" in sys.argv

FLAT_OLD = '{"GEN_NX": 474, "CIVIL_NX": 440, "CIVIL_DESIGNER": 31}'
FLAT_NEW = '{"GEN_NX": 474, "CIVIL_NX": 452, "CIVIL_DESIGNER": 31}'

EDITS: list[tuple[str, str, str]] = [
    ("test_midas_write_coverage_p142.py", '"CIVIL_NX": 440,', '"CIVIL_NX": 452,'),
    ("test_midas_write_coverage_p144.py", FLAT_OLD, FLAT_NEW),
    ("test_midas_write_coverage_p145.py", FLAT_OLD, FLAT_NEW),
    ("test_midas_write_coverage_p146.py", FLAT_OLD, FLAT_NEW),
    ("test_midas_write_coverage_p147.py", FLAT_OLD, FLAT_NEW),
    ("test_midas_write_coverage_p148.py", FLAT_OLD, FLAT_NEW),
    ("test_midas_endpoint_methods_p149.py", FLAT_OLD, FLAT_NEW),
    (
        "test_midas_endpoint_methods_p149.py",
        'CANDIDATES_BY_PRODUCT: dict[str, int] = {"GEN_NX": 78, "CIVIL_NX": 68, "CIVIL_DESIGNER": 0}',
        'CANDIDATES_BY_PRODUCT: dict[str, int] = {"GEN_NX": 78, "CIVIL_NX": 74, "CIVIL_DESIGNER": 0}',
    ),
    ("test_midas_availability_p149c.py", "EXPECTED_VERIFIED_TOTAL = 503", "EXPECTED_VERIFIED_TOTAL = 509"),
    ("test_midas_availability_p149e.py", "EXPECTED_VERIFIED_TOTAL = 503", "EXPECTED_VERIFIED_TOTAL = 509"),
    ("test_midas_result_tables_p149d.py", "EXPECTED_VERIFIED_TOTAL = 503", "EXPECTED_VERIFIED_TOTAL = 509"),
    ("test_midas_availability_p149e.py", "NO_GET = 109", "NO_GET = 103"),
    ("test_midas_request_schemas_p141.py", '"OPE.MEMB": "PARTIAL",', '"OPE.MEMB": "VERIFIED",'),
    (
        "test_midas_p119_p123.py",
        'assert registry.endpoint("DB.POSL").products == ("GEN_NX",)',
        'assert registry.endpoint("DB.POSL").products == ("CIVIL_NX", "GEN_NX")',
    ),
    # `_unchanged_since_head` scoping: `unavailable_on` was extended by this adjudicated batch
    (
        "test_midas_availability_p149e.py",
        'AVAILABILITY_FIELDS = ("availability", "unavailable_on")',
        'AVAILABILITY_FIELDS = ("availability",)',
    ),
    (
        "test_midas_introspect_fields_p150.py",
        'AVAILABILITY_FIELDS = ("availability", "unavailable_on")',
        'AVAILABILITY_FIELDS = ("availability",)',
    ),
]

for name, old, new in EDITS:
    p = TESTS / name
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        print(f"  {'!! ' + str(count) + ' hits' if count else 'SKIP (not found)'}  {name}: {old[:56]}")
        continue
    if WRITE:
        p.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    print(f"  {'WROTE' if WRITE else 'WOULD'}  {name}: {old[:44]} -> {new[:44]}")

# ---- p143: insert the 6 new CIVIL_NX candidates in sorted position ----
p143 = TESTS / "test_midas_write_coverage_p143.py"
text = p143.read_text(encoding="utf-8")
NEW_KEYS = ["DB.DCTL", "DB.DSTL", "DB.LENG", "DB.MBTP", "DB.POSL", "DB.WMAK"]
added = []
for key in NEW_KEYS:
    if f'    "{key}",\n' in text:
        continue
    # insert before the first existing entry that sorts after `key`
    lines = text.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.startswith("CIVIL_CODES = ("))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == ")")
    entries = [i for i in range(start + 1, end) if lines[i].strip().startswith('"')]
    target = next((i for i in entries if lines[i].strip().strip(',').strip('"') > key), end)
    lines.insert(target, f'    "{key}",\n')
    text = "".join(lines)
    added.append(key)
if added:
    if WRITE:
        p143.write_text(text, encoding="utf-8", newline="\n")
    print(f"  {'WROTE' if WRITE else 'WOULD'}  test_midas_write_coverage_p143.py: CIVIL_CODES += {added}")
else:
    print("  (p143 CIVIL_CODES already has the 6 keys)")

print()
print("applied" if WRITE else "dry-run")
