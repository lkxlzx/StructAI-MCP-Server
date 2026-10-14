"""Update the errata CSV: MD-17 / MD-34 / MD-45 are now fully landed (batch 2)."""
import csv
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path(r"E:\MCP\MMCP\docs\nxsdk_review")
SRC = OUT / "nxsdk_manual_errata.csv"

APPLIED = {
    "MD-17": "✅ 已落地：/db/PRES 的 DIRECTION 入 required + enum + 无默认值（第二批）",
    "MD-34": "✅ 已落地：/db/REB* 家族形状按原生短键重建（REBB/REBC/REBR/REBW，第二批）",
    "MD-45": "✅ 已落地：SLANop OPT_STRADD→boolean；LLANtr/SLANop 缺字段已在 Schema 中（第一/二批）",
    "MD-04": "🟡 部分：/db/IEHC WAreaSize 待复核类型",
}
PRIORITY = {"MD-29", "MD-03", "MD-16", "MD-60"}
TOOL_DEFECT = {"MD-36", "MD-42", "MD-44", "MD-50"}

rows = list(csv.DictReader(SRC.open(encoding="utf-8-sig")))
fields = list(rows[0].keys())

for row in rows:
    md = row["MD"]
    if md in APPLIED:
        row["落地状态"] = APPLIED[md]
    elif md in TOOL_DEFECT:
        row["落地状态"] = "⚪ 不改（对方工具缺陷，手册内容正确）"
    elif md in PRIORITY:
        row["落地状态"] = "📌 待我方复测（证据较硬，建议优先）"
    else:
        row["落地状态"] = "📌 已登记，待实测/裁决"

with SRC.open("w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)

print(f"rewrote {SRC.name}: {len(rows)} rows")
for status, n in Counter(r["落地状态"] for r in rows).most_common():
    print(f"  {n:3d}  {status}")
