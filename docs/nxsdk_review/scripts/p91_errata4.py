"""Update the errata CSV for the fourth batch (MD-60 / MD-03 / MD-16 / MD-29)."""
import csv
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
SRC = Path(r"E:\MCP\MMCP\docs\nxsdk_review\nxsdk_manual_errata.csv")

APPLIED = {
    "MD-60": "✅ 已核对：我方本来就对（三字段在 STR 不在 OPT）；附带发现手册拼写 LARGEBRIDEGE（按 R117 保留）",
    "MD-03": "✅ 已核对：我方本来就对（MATL-M1 用专属 wire key + P_TYPE 0-based），不改数据",
    "MD-16": "✅ 已落地：补 LOAD_ITEMS[].POINT_DIST2 + VEHICLE_LOAD_NUM enum + if/then 条件必填 + 两处如实加注",
    "MD-29": "✅ 已落地：条目按该节自己的三个示例重建（vMAIN_BAR_* 数组 + MAIN_BAR_DC_* + bSAME_SIZE_*）",
    "MD-17": "✅ 已落地：/db/PRES 的 DIRECTION 入 required + enum + 无默认值（第二批）",
    "MD-34": "✅ 已落地：/db/REB* 家族形状按原生短键重建（REBB/REBC/REBR/REBW）",
    "MD-45": "✅ 已落地：SLANop OPT_STRADD→boolean；缺字段已在 Schema 中",
}
PRIORITY = {"MD-04", "MD-33", "MD-49", "MD-51", "MD-61"}
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
