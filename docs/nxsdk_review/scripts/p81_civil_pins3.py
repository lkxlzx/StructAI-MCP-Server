"""Final CIVIL_NX pin fixes: coverage ratio 62 -> 68, and the DB.POSL product fact."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
TESTS = Path(r"E:\MCP\MMCP\tests")
WRITE = "--write" in sys.argv

EDITS = [
    (
        "test_midas_write_coverage_p144.py",
        'assert civil.ratio == f"62 / {WRITE_PATH_TOTAL}"',
        'assert civil.ratio == f"68 / {WRITE_PATH_TOTAL}"',
    ),
    ("test_midas_write_coverage_p146.py", 'assert civil.ratio == "62 / 633"', 'assert civil.ratio == "68 / 633"'),
    ("test_midas_write_coverage_p147.py", 'assert civil.ratio == "62 / 633"', 'assert civil.ratio == "68 / 633"'),
    ("test_midas_write_coverage_p148.py", 'assert civil.ratio == "62 / 633"', 'assert civil.ratio == "68 / 633"'),
    (
        "test_midas_write_coverage_p146.py",
        '"""门槛：子桶口径**不**过滤、**不**隐藏 —— 只给 CIVIL NX 的 62 条时原分子仍为 62。"""',
        '"""门槛：子桶口径**不**过滤、**不**隐藏 —— 只给 CIVIL NX 的 68 条时原分子仍为 68。"""',
    ),
    (
        "test_midas_write_coverage_p148.py",
        '"""门槛：子桶口径**不**过滤、**不**隐藏 —— 只给 CIVIL NX 的 62 条时原分子仍为 62。"""',
        '"""门槛：子桶口径**不**过滤、**不**隐藏 —— 只给 CIVIL NX 的 68 条时原分子仍为 68。"""',
    ),
    (
        "test_midas_write_coverage_p148.py",
        """    # `DB.POSL` / `DB.STOR` 只属 GEN NX（数据侧在 `registry/products/gen_nx/`）
    for key in ("DB.POSL", "DB.STOR"):
        assert key not in CANDIDATES_BY_PRODUCT["CIVIL_NX"], key""",
        """    # ⚠️ **CIVIL_NX 探针（第三批）**：`DB.POSL` 在 CIVIL_NX 上实测存在（`200`）⇒ 已并上
    # `CIVIL_NX` 并成为其候选；`DB.STOR` 仍只属 GEN NX（数据侧在 `registry/products/gen_nx/`）。
    assert "DB.POSL" in CANDIDATES_BY_PRODUCT["CIVIL_NX"]
    for key in ("DB.STOR",):
        assert key not in CANDIDATES_BY_PRODUCT["CIVIL_NX"], key""",
    ),
]

for name, old, new in EDITS:
    p = TESTS / name
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        print(f"  {'!! ' + str(count) + ' hits' if count else 'SKIP'}  {name}: {old[:50]}")
        continue
    if WRITE:
        p.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    print(f"  {'WROTE' if WRITE else 'WOULD'}  {name}")

print()
print("applied" if WRITE else "dry-run")
