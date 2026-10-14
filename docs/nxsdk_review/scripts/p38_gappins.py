"""Update p152/p153 gap pins: every count shifts by exactly -21 (the 21 Hyper-S endpoints
left the GEN_NX product scope, and the gap document is computed with product_key = GEN_NX).
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
TESTS = Path(r"E:\MCP\MMCP\tests")
WRITE = "--write" in sys.argv

EDITS = [
    ("test_midas_interface_paths_p152.py", '"write_capable_endpoints": 577,', '"write_capable_endpoints": 556,'),
    ("test_midas_interface_paths_p152.py", '"three_step_endpoints": 301,', '"three_step_endpoints": 280,'),
    ("test_midas_interface_paths_p152.py", '"gap_total": 510,', '"gap_total": 489,'),
    ("test_midas_interface_paths_p152.py", "EXPECTED_GAP_THREE_STEP = 264", "EXPECTED_GAP_THREE_STEP = 243"),
    ("test_midas_interface_read_p153.py", "EXPECTED_GAP_TOTAL = 510", "EXPECTED_GAP_TOTAL = 489"),
    ("test_midas_interface_read_p153.py", "EXPECTED_GAP_NOT_IN_CONTRACT = 264", "EXPECTED_GAP_NOT_IN_CONTRACT = 243"),
    ("test_midas_interface_read_p153.py", '"gap_total": 510,', '"gap_total": 489,'),
    ("test_midas_interface_read_p153.py", '"gap_not_in_contract": 264,', '"gap_not_in_contract": 243,'),
    ("test_midas_interface_read_p153.py", '"needs_product_decision": 213,', '"needs_product_decision": 192,'),
]

for name, old, new in EDITS:
    p = TESTS / name
    text = p.read_text(encoding="utf-8")
    n = text.count(old)
    if n == 0:
        print(f"  SKIP (not found)  {name}: {old}")
        continue
    if n > 1:
        print(f"  !! {n} occurrences  {name}: {old}")
        continue
    if WRITE:
        p.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    print(f"  {'WROTE' if WRITE else 'WOULD'}  {name}: {old} -> {new}")

print()
print(f"{'applied' if WRITE else 'dry-run'}: {len(EDITS)} edits")
