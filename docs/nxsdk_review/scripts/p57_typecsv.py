"""Enrich nxsdk_type_mismatches.csv with the SDK contract's own type and a verdict column."""
import csv
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
OUT = REPO / "docs" / "nxsdk_review"
SDK = REPO / ".tmp_nxsdk"

# endpoint -> contract file
CONTRACT = {
    "/db/EPSE": "db-epse.yaml", "/db/EPST": "db-epst.yaml",
    "/db/SLANOP": "db-slanop.yaml", "/db/RPSC": "db-rpsc.yaml",
    "/db/NLLP": "db-nllp.yaml", "/db/REBC": "db-rebc.yaml",
    "/db/REBR": "db-rebr.yaml",
}


def find(node, field):
    if isinstance(node, dict):
        if node.get("key") == field:
            yield node
        for v in node.values():
            yield from find(v, field)
    elif isinstance(node, list):
        for v in node:
            yield from find(v, field)


CONTRACT_TYPES = {}
for route, fname in CONTRACT.items():
    p = SDK / "contracts" / "endpoints" / fname
    if not p.exists():
        continue
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    for f in d.get("fields", []):
        for prop in find(f, "HOOP_TYPE") if "REB" in route else []:
            CONTRACT_TYPES[(route, "ITEMS[].HOOP_TYPE")] = prop
        for prop in find(f, "OPT_STRADD") if "SLANOP" in route else []:
            CONTRACT_TYPES[(route, "OPT_STRADD")] = prop
        for prop in find(f, "LBAR_INC_FC") if "RPSC" in route else []:
            CONTRACT_TYPES[(route, "SBAR_ITEMS[].LBAR_INC_FC")] = prop
        for prop in find(f, "LOADING_AREA_GROUP") if "EPSE" in route or "EPST" in route else []:
            CONTRACT_TYPES[(route, "LOADING_AREA_GROUP")] = prop
        for prop in find(f, "SEIS_TYPE") if "NLLP" in route else []:
            CONTRACT_TYPES[(route, "SEIS_TYPE")] = prop

APPLIED = {
    ("/db/SLANop", "OPT_STRADD"),
    ("/db/REBC", "ITEMS[].HOOP_TYPE"),
    ("/db/REBR", "ITEMS[].HOOP_TYPE"),
}

src = OUT / "nxsdk_type_mismatches.csv"
rows = list(csv.DictReader(src.open(encoding="utf-8-sig")))
fields = list(rows[0].keys())
for col in ("sdk_contract_type", "sdk_contract_provenance", "verdict"):
    if col not in fields:
        fields.append(col)

for row in rows:
    key = (row["route"], row["path"])
    prop = CONTRACT_TYPES.get(key)
    if prop:
        row["sdk_contract_type"] = prop.get("type", "")
        row["sdk_contract_provenance"] = prop.get("provenance", "")
    else:
        row["sdk_contract_type"] = "(契约无此字段)"
        row["sdk_contract_provenance"] = ""
    if (row["route"], row["path"]) in APPLIED:
        row["verdict"] = "✅ 已落地（/info 与契约同向）"
    elif prop and prop.get("type") == row["ours"]:
        row["verdict"] = "⏸ 不改（契约支持我方）"
    elif prop and prop.get("type") != row["server"]:
        row["verdict"] = "⏸ 不改（三方差歧）"
    else:
        row["verdict"] = "🟡 待我方复测"

with src.open("w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)

print(f"enriched {src.name}: {len(rows)} rows")
from collections import Counter

for v, n in Counter(r["verdict"] for r in rows).most_common():
    print(f"  {n:3d}  {v}")
