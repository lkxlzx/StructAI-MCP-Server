"""Regenerate the errata CSV with an explicit 落地状态 column."""
import csv
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path(r"E:\MCP\MMCP\docs\nxsdk_review")
SRC = OUT / "nxsdk_manual_errata.csv"

APPLIED = {
    "MD-34": "部分落地：HOOP_TYPE integer 已改；item 形状（vMAIN_BAR/D0）待实测",
    "MD-45": "部分落地：OPT_STRADD boolean 已改；SPECIAL_LANE_ITEMS/CHINA_ITEMS 待核对",
}
DEFERRED_PRIORITY = {"MD-17", "MD-29"}
TOOL_DEFECT = {"MD-36", "MD-42", "MD-44", "MD-50"}
RETRACTED = {"MD-14"}  # 见勘误文 §2：/db/TDME 的 KDS2016 等已撤回（MD-14 为码表混入，保留）

rows = list(csv.DictReader(SRC.open(encoding="utf-8-sig")))
fields = list(rows[0].keys())
if "落地状态" not in fields:
    fields.insert(1, "落地状态")

for row in rows:
    md = row["MD"]
    if md in APPLIED:
        status = f"✅ {APPLIED[md]}"
    elif md in TOOL_DEFECT:
        status = "⚪ 不改（对方工具缺陷，手册内容正确）"
    elif md in DEFERRED_PRIORITY:
        status = "📌 待我方复测（证据最硬，建议优先）"
    else:
        status = "📌 已登记，待实测/裁决"
    row["落地状态"] = status

with SRC.open("w", encoding="utf-8-sig", newline="") as fh:
    writer = csv.DictWriter(fh, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

print(f"rewrote {SRC.name}: {len(rows)} rows, columns={fields}")
from collections import Counter

for status, count in Counter(r["落地状态"] for r in rows).most_common():
    print(f"  {count:3d}  {status}")
