import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
LOCAL = Path(r"E:\MCP\MMCP")
man = json.load(open(LOCAL / "registry" / "manifest.json", encoding="utf-8"))
keys = ["DB.REBB", "DB.REBC", "DB.REBR", "DB.REBW",
        "DESIGN.RC.KDS-41-20-2022.REBB", "DESIGN.RC.KDS-41-20-2022.REBC",
        "DESIGN.RC.KDS-41-20-2022.REBR", "DESIGN.RC.KDS-41-20-2022.REBW",
        "DESIGN.RC.KDS-41-20-2022.TRFT", "DESIGN.RC.KDS-41-20-2022.ULCT",
        "DESIGN.STEEL.KDS-41-30-2022.ULCT", "OPE.STORYPROP",
        "DB.UFTR", "DB.UTBL", "OPE.STORPROP"]
for e in man["endpoints"]:
    if e["key"] in keys:
        print(f"{e['key']:34s} products={str(e['products']):32s} avail={e['availability']:10s}")
        print(f"{'':34s} verified_on={e['verified_on']}  unavailable_on={e['unavailable_on']}")
        print(f"{'':34s} definition={e['definition']}")

print()
print("=== SDK GEN_ONLY 声明（contracts + coverage）===")
import yaml
for p in sorted((LOCAL / ".tmp_nxsdk" / "contracts" / "endpoints").glob("*.yaml")):
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    if "REB" in d["endpoint"].upper() or "ULCT" in d["endpoint"].upper() or "TRFT" in d["endpoint"].upper():
        print(f"  {d['endpoint']:38s} products={d.get('products')}")
