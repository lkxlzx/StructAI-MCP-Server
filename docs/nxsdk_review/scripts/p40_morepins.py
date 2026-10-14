"""Update the remaining gap pins: every count shifts by exactly -21.

The mapping-gap document is computed with `product_key = GEN_NX`; the 21 Hyper-S endpoints
left the GEN_NX product scope, so every GEN_NX-scoped count drops by 21 and the
`by_availability` "unverified" bucket (which held exactly those 21) disappears.
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
TESTS = Path(r"E:\MCP\MMCP\tests")
WRITE = "--write" in sys.argv

GAP_FILES = [
    "test_midas_constraint_rw_p157.py",
    "test_midas_constraint_value_p156.py",
    "test_midas_flagship_chain_p157.py",
    "test_midas_interface_contract_p154.py",
    "test_midas_interface_shape_p155.py",
]

EDITS = []
for name in GAP_FILES:
    EDITS.append((name, "EXPECTED_GAP_TOTAL = 510", "EXPECTED_GAP_TOTAL = 489"))
    EDITS.append((name, "EXPECTED_GAP_NOT_IN_CONTRACT = 264", "EXPECTED_GAP_NOT_IN_CONTRACT = 243"))

P153 = "test_midas_interface_read_p153.py"
EDITS += [
    (P153, '{"DB": 193, "DESIGN": 68, "OPE": 3}', '{"DB": 172, "DESIGN": 68, "OPE": 3}'),
    (P153, '{"DELETE": 179, "DESIGN": 68, "MODEL": 196, "OPERATION": 3}',
           '{"DELETE": 158, "DESIGN": 68, "MODEL": 175, "OPERATION": 3}'),
    (P153, '{"assign": 263, "delete": 179, "query": 264}',
           '{"assign": 242, "delete": 158, "query": 243}'),
    (P153, '"schema_only": 212,', '"schema_only": 191,'),
    (P153, '{"unverified": 21, "verified": 243}', '{"verified": 243}'),
]

for name, old, new in EDITS:
    p = TESTS / name
    text = p.read_text(encoding="utf-8")
    n = text.count(old)
    if n != 1:
        print(f"  {'!! ' + str(n) + ' occurrences' if n else 'SKIP (not found)'}  {name}: {old[:52]}")
        continue
    if WRITE:
        p.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    print(f"  {'WROTE' if WRITE else 'WOULD'}  {name}: {old[:46]} -> {new[:46]}")

print()
print(f"{'applied' if WRITE else 'dry-run'}: {len(EDITS)} edits")
