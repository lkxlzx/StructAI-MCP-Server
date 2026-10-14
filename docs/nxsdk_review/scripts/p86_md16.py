"""MD-16 (/db/MVHL) 细节：分支字段、VEH_CA 的 DYNA、缺的 POINT_DIST2。"""
import json
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
SDK = REPO / ".tmp_nxsdk"
ib = json.loads((SDK / "schema" / "info-baseline.json").read_text(encoding="utf-8"))
man = {e["key"]: e for e in json.loads((REPO / "registry" / "manifest.json").read_text(encoding="utf-8"))["endpoints"]}

d = json.loads((REPO / "registry" / man["DB.MVHL"]["schema"]).read_text(encoding="utf-8"))
sch = d["schema"]
inner = sch["MVHL"] if "MVHL" in sch else sch
props = inner["properties"]
print("MVHL 顶层字段（%d）:" % len(props), sorted(props))

print("\n=== 分支相关 ===")
for k in ("VEHICLE_LOAD_NUM", "VEHICLE_TYPE_NAME", "STANDARD_CODE", "USER_LOAD_TYPE", "MVLD_CODE"):
    v = props.get(k)
    print(f"  {k:20s} {json.dumps(v, ensure_ascii=False)[:220] if v else '(缺)'}")
print("  顶层 required:", inner.get("required"))

print("\n=== VEH_CA ===")
veh = props.get("VEH_CA")
print(json.dumps(veh, ensure_ascii=False, indent=1)[:900] if veh else "  (缺)")

print("\n=== LOAD_ITEMS[].POINT_DIST2（服务端有、我方缺）===")
srv = ib["endpoints"]["/db/MVHL"]["gen"]["schema"]
root = next(v for k, v in srv.items() if k != "$schema")
li = root["properties"]["LOAD_ITEMS"]["items"]["properties"]
print("  server LOAD_ITEMS item:", sorted(li))
print("  POINT_DIST2 =", json.dumps(li.get("POINT_DIST2"), ensure_ascii=False))
ours_li = props["LOAD_ITEMS"]["items"]["properties"]
print("  ours   LOAD_ITEMS item:", sorted(ours_li))

print("\n=== contract: 分支与 VEH_CA 的字段级证据 ===")
c = yaml.safe_load((SDK / "contracts" / "endpoints" / "db-mvhl.yaml").read_text(encoding="utf-8"))


def walk(fields, path=""):
    for f in fields or []:
        if not isinstance(f, dict):
            continue
        p = f"{path}.{f['key']}" if path else f["key"]
        if f["key"] in ("VEHICLE_LOAD_NUM", "VEHICLE_TYPE_NAME", "STANDARD_CODE", "USER_LOAD_TYPE",
                        "VEH_CA", "DYNA", "DYNA_FACTOR", "POINT_DIST2", "MVLD_CODE"):
            print(f"  {p:34s} type={f.get('type')!r} req={f.get('requirement')!r} "
                  f"prov={f.get('provenance')!r}")
            for extra in ("appliesWhen", "condition", "enum", "note"):
                if f.get(extra) is not None:
                    print(f"        {extra}: {json.dumps(f[extra], ensure_ascii=False)[:200]}")
        walk(f.get("properties"), p)


walk(c.get("fields"))
