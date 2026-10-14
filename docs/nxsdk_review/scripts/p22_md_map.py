"""Cross-map each MD defect item against our registry: does the endpoint exist, what does our data say?"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
LOCAL = Path(r"E:\MCP\MMCP")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


manifest = load(LOCAL / "registry" / "manifest.json")
by_uri = {}
for ep in manifest["endpoints"]:
    by_uri.setdefault(("/" + ep["uri"].strip("/")).upper(), []).append(ep)

# MD -> endpoint(s) of interest
MD = {
    "MD-01": ["/DB/STYP-M1"], "MD-02": ["/DB/POLC-M1"], "MD-03": ["/DB/MATL-M1"],
    "MD-04": ["/DB/IEHC"], "MD-05": ["/DOC/SAVEAS", "/DOC/STAGAS"],
    "MD-06": ["/DB/ELEM"], "MD-07": ["/DB/FIMP"], "MD-08": ["/DB/CO_S", "/DB/CO_T"],
    "MD-09": ["/DESIGN/RC/KDS-41-20-2022/DCRM-BEAM", "/DESIGN/SRC/AIK-SRC2K/LLRF"],
    "MD-10": ["/DB/EPMT", "/DB/ELEM", "/DB/RCHK", "/DB/FIMP"],
    "MD-11": ["/DB/SBDO", "/DB/MATL", "/OPE/AUTOMESH", "/DB/RCHK"],
    "MD-12": ["/DB/STYP-M1", "/DB/MATL-M1", "/DB/EPMT-M1"],
    "MD-13": ["/DB/TDME"], "MD-14": ["/DB/TDME"], "MD-15": ["/DB/SECT", "/DB/SPFC"],
    "MD-16": ["/DB/MVHL"], "MD-17": ["/DB/PRES"], "MD-18": ["/DB/THGC-M1"],
    "MD-19": ["/DB/THGC-M1"], "MD-20": ["/DB/THGC-M1"], "MD-21": ["/DB/STCT-M1"],
    "MD-22": ["/DB/STCT-M1"], "MD-23": ["/DB/THIS-M1"],
    "MD-24": ["/DESIGN/RC/KDS-41-20-2022/BRD-TABLE", "/DESIGN/RC/KDS-41-20-2022/CD-TABLE"],
    "MD-25": ["/DB/MVLDEU"], "MD-26": ["/DB/REBR"], "MD-27": ["/DB/RCHK"],
    "MD-28": ["/OPE/AUTOMESH"], "MD-29": ["/DESIGN/RC/KDS-41-20-2022/REBB"],
    "MD-30": ["/DESIGN/RC/KDS-41-20-2022/REBR"],
    "MD-31": ["/DESIGN/RC/KDS-41-20-2022/TABLE"],
    "MD-32": ["/DESIGN/SRC/AIK-SRC2K/OCHECK", "/TEMP/DESIGN/SRC/AIK-SRC2K/OCHECK"],
    "MD-33": ["/DESIGN/RC/KDS-41-20-2022/CD-TABLE", "/DESIGN/RC/KDS-41-20-2022/BRD-TABLE"],
    "MD-34": ["/DB/REBR"], "MD-35": ["/DB/LCOM-GEN", "/DB/LCOM-STEEL", "/DB/LCOM-SRC", "/DB/LCOM-CONC"],
    "MD-36": ["/DB/LCOM-GEN", "/DB/POGD"], "MD-37": ["/DB/POGD-M1"], "MD-38": ["/DB/STRPSSM"],
    "MD-39": ["/DB/STOR"], "MD-40": ["/DB/RPSC"], "MD-41": [],
    "MD-42": ["/DB/GRDP"], "MD-43": ["/DB/SLANCH"], "MD-44": ["/DB/SLAN", "/DB/POLC", "/DB/ACTL-M1", "/DB/NLNK", "/DB/NLNK-M1"],
    "MD-45": ["/DB/LLANTR", "/DB/SLANOP"], "MD-46": [], "MD-47": ["/DB/TDMT"],
    "MD-48": ["/DB/MVHL"], "MD-49": ["/POST/TABLE"], "MD-50": ["/DB/MVCTCH"],
    "MD-51": ["/OPE/MEMB"], "MD-52": ["/OPE/MEMB"], "MD-53": ["/DB/MATD"],
    "MD-54": ["/DB/FIMP"], "MD-55": ["/DB/TDMF"], "MD-56": ["/DB/EPMT"],
    "MD-57": ["/DB/SPLC"], "MD-58": ["/DB/STCT"], "MD-59": ["/DB/ELEM"],
    "MD-60": ["/DB/SPFC"], "MD-61": ["/DB/MVHL"], "MD-62": ["/OPE/DIVIDEELEM"],
}

out = []
print(f"{'MD':7s} {'endpoint':34s} {'our key':26s} {'products':28s} {'avail':10s}")
print("-" * 112)
for md, routes in MD.items():
    if not routes:
        out.append(dict(md=md, route="(多端点)", key="", products="", availability="", note="跨多节，见报告 §3.7"))
        continue
    for r in routes:
        eps = by_uri.get(r)
        if not eps:
            print(f"{md:7s} {r:34s} *** 我方注册表无此端点 ***")
            out.append(dict(md=md, route=r, key="", products="", availability="", note="我方无此端点"))
            continue
        for e in eps:
            print(f"{md:7s} {r:34s} {e['key']:26s} {','.join(e['products']):28s} {e['availability']:10s}")
            out.append(dict(md=md, route=r, key=e["key"], products=",".join(e["products"]),
                            availability=e["availability"],
                            unavailable_on=",".join(e["unavailable_on"]),
                            verified_on=",".join(e["verified_on"]), note=""))
json.dump(out, open(LOCAL / ".tmp_analysis" / "md_registry_map.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print()
print("wrote md_registry_map.json  rows:", len(out))
