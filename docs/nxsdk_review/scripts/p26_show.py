import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
d = json.load(open(r"E:\MCP\MMCP\docs\nxsdk_review\nxsdk_product_corrections.json", encoding="utf-8"))
cs = d["corrections"]
print("total:", len(cs))
for t in ("A", "B", "C"):
    n = sum(1 for c in cs if c["tier"] == t)
    print(f"tier {t}: {n}")
print()
for c in cs:
    if c["tier"] != "A":
        print(f"  tier={c['tier']} {c['key']:36s} {str(c['from']):34s} -> {c['to']}")
