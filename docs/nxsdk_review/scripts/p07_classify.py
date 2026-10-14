"""Inspect raw schemas for the biggest remaining diffs to classify real vs artifact."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SDK = Path(r"E:\MCP\MMCP\.tmp_nxsdk")
LOCAL = Path(r"E:\MCP\MMCP")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


ib = load(SDK / "schema" / "info-baseline.json")["endpoints"]

CASES = [
    ("/db/SWIND", "gen", r"registry\schema\products\gen_nx\db\SWIND.json"),
    ("/db/VSEC", "gen", r"registry\schema\common\db\VSEC.json"),
    ("/db/REBB", "gen", r"registry\schema\common\db\REBB.json"),
    ("/db/STRPSSM", "civil", r"registry\schema\common\db\STRPSSM.json"),
    ("/db/SPLC", "civil", r"registry\schema\common\db\SPLC.json"),
]

for route, prod, rel in CASES:
    print("#" * 74)
    print(f"# {route} [{prod}]")
    print("#" * 74)
    e = ib.get(route, {}).get(prod)
    if e:
        s = e["schema"]
        keys = [k for k in s if k != "$schema"]
        print("  SERVER /info root keys:", keys)
        for k in keys:
            v = s[k]
            props = v.get("properties", {}) if isinstance(v, dict) else {}
            print(f"    {k}: {len(props)} top-level props -> {list(props)[:20]}")
    else:
        print("  SERVER: no entry")
    p = LOCAL / rel
    if p.exists():
        d = load(p)
        root = d.get("schema", {})
        print("  LOCAL root keys:", list(root))
        for k, v in root.items():
            if not isinstance(v, dict):
                continue
            props = v.get("properties", {})
            print(f"    {k}: keys={list(v)[:8]}")
            print(f"       top-level props ({len(props)}): {list(props)[:20]}")
            if "Assign" in props:
                ap = props["Assign"].get("additionalProperties")
                if isinstance(ap, dict):
                    print(f"       Assign.additionalProperties keys: {list(ap)[:10]}")
                    print(f"       Assign item props ({len(ap.get('properties', {}))}): {list(ap.get('properties', {}))[:25]}")
    else:
        print("  LOCAL: file missing", rel)
    print()
