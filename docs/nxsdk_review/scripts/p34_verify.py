import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
LOCAL = Path(r"E:\MCP\MMCP")
man = json.load(open(LOCAL / "registry" / "manifest.json", encoding="utf-8"))
eps = man["endpoints"]

print("products 分布:", dict(Counter(p for e in eps for p in e["products"])))
print("availability 分布:", dict(Counter(e["availability"] for e in eps)))
print("counts 块:", json.dumps(man.get("counts"), ensure_ascii=False))
print()

m1 = [e for e in eps if e["uri"].upper().endswith("-M1")]
print(f"--- 21 个 -M1 现状（{len(m1)} 条）---")
for e in sorted(m1, key=lambda x: x["key"]):
    flag = "OK " if e["products"] == ["CIVIL_NX"] else "!! "
    print(f"  {flag}{e['key']:24s} products={e['products']} solver={e['solver']}")

print()
tierc = ["DB.REBB", "DB.REBC", "DB.REBR", "DB.REBW",
         "DESIGN.RC.KDS-41-20-2022.REBB", "DESIGN.RC.KDS-41-20-2022.REBC",
         "DESIGN.RC.KDS-41-20-2022.REBR", "DESIGN.RC.KDS-41-20-2022.REBW",
         "DESIGN.RC.KDS-41-20-2022.TRFT", "DESIGN.RC.KDS-41-20-2022.ULCT",
         "DESIGN.STEEL.KDS-41-30-2022.ULCT", "OPE.STORYPROP"]
print(f"--- tier C 现状（{len(tierc)} 条）---")
by = {e["key"]: e for e in eps}
for k in tierc:
    e = by.get(k)
    if not e:
        print(f"  !! {k} 不存在")
        continue
    flag = "OK " if e["products"] == ["GEN_NX"] else "!! "
    print(f"  {flag}{k:34s} products={e['products']}")

print()
print("--- 未改动的应保持原样（tier B 抽样）---")
for k in ["DB.POSL", "DB.POSP", "DB.LLAN", "DB.DCTL", "POST.STEELCODECHECK", "DB.UFTR", "DB.UTBL"]:
    e = by.get(k)
    if e:
        print(f"  {k:24s} products={e['products']}")
