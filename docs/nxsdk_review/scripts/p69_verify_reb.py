"""Verify each generated REB* item schema matches GET /info's path set exactly."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
ib = json.loads((REPO / ".tmp_nxsdk" / "schema" / "info-baseline.json").read_text(encoding="utf-8"))


def paths(node, prefix="", out=None, depth=0):
    if out is None:
        out = set()
    if not isinstance(node, dict) or depth > 6:
        return out
    for k, v in (node.get("properties") or {}).items():
        p = f"{prefix}.{k}" if prefix else k
        out.add(p)
        paths(v, p, out, depth + 1)
    it = node.get("items")
    if isinstance(it, dict):
        paths(it, f"{prefix}[]", out, depth + 1)
    return out


def server_item(route):
    e = (ib["endpoints"].get(route) or {}).get("gen") or {}
    s = e.get("schema")
    if not isinstance(s, dict):
        return None
    root = next((v for k, v in s.items() if k != "$schema"), {})
    items = (root.get("properties") or {}).get("ITEMS")
    return items.get("items") if isinstance(items, dict) else None


ok = True
for key, route in [("DB.REBB", "/db/REBB"), ("DB.REBC", "/db/REBC"),
                   ("DB.REBR", "/db/REBR"), ("DB.REBW", "/db/REBW")]:
    p = REPO / ".tmp_analysis" / f"generated_{key.replace('.', '_')}.json"
    if p.exists():
        gen = json.loads(p.read_text(encoding="utf-8"))["items_schema"]
    else:
        # REBR already applied in the registry
        d = json.loads((REPO / "registry" / "schema" / "common" / "db" / "REBR.json").read_text(encoding="utf-8"))
        pp = d["schema"]["properties"]["Assign"]["patternProperties"]
        gen = next(iter(pp.values()))["properties"]["ITEMS"]["items"]
    g, s = paths(gen), paths(server_item(route))
    same = g == s
    ok &= same
    print(f"{key}: generated={len(g)} server={len(s)}  {'✅ identical' if same else '❌ MISMATCH'}")
    if not same:
        print(f"    gen-only   : {sorted(g - s)}")
        print(f"    server-only: {sorted(s - g)}")

print()
print("ALL MATCH" if ok else "MISMATCHES PRESENT")
