import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
TESTS = Path(r"E:\MCP\MMCP\tests")

for name in ("test_midas_constraint_rw_p157.py", "test_midas_interface_contract_p154.py"):
    p = TESTS / name
    text = p.read_text(encoding="utf-8")
    old = '"needs_product_decision": 213,'
    new = '"needs_product_decision": 192,'
    count = text.count(old)
    if count != 1:
        print(f"  !! {name}: {count} occurrences")
        continue
    p.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    print(f"  WROTE {name}: 213 -> 192")
