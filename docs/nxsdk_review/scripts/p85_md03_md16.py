"""C 批侦察 —— MD-03 (/db/MATL-M1) 与 MD-16 (/db/MVHL)：三方差比对。"""
import json
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
SDK = REPO / ".tmp_nxsdk"
ib = json.loads((SDK / "schema" / "info-baseline.json").read_text(encoding="utf-8"))
man = json.loads((REPO / "registry" / "manifest.json").read_text(encoding="utf-8"))["endpoints"]
by_key = {e["key"]: e for e in man}


def props(node, path=""):
    out = {}
    if not isinstance(node, dict):
        return out
    for k, v in (node.get("properties") or {}).items():
        p = f"{path}.{k}" if path else k
        out[p] = v.get("type") if isinstance(v, dict) else None
        out.update(props(v, p))
    it = node.get("items")
    if isinstance(it, dict):
        out.update(props(it, f"{path}[]"))
    return out


def ours(key):
    entry = by_key[key]
    if not entry.get("schema"):
        return {}
    d = json.loads((REPO / "registry" / entry["schema"]).read_text(encoding="utf-8"))
    root = d["schema"]
    # unwrap code-key / Assign / Argument
    if "properties" in root and "Assign" in root["properties"]:
        a = root["properties"]["Assign"]
        pp = a.get("patternProperties") or {}
        inner = next(iter(pp.values())) if pp else a.get("additionalProperties")
        return props(inner)
    if "properties" in root and "Argument" in root["properties"]:
        return props(root["properties"]["Argument"])
    for k, v in root.items():
        if isinstance(v, dict) and "properties" in v:
            return props(v)
    return props(root)


def server(route, prod="gen"):
    e = (ib["endpoints"].get(route) or {}).get(prod) or {}
    s = e.get("schema")
    if not isinstance(s, dict):
        return {}
    return props(next(v for k, v in s.items() if k != "$schema"))


def contract(fname):
    p = SDK / "contracts" / "endpoints" / fname
    if not p.exists():
        return None
    return yaml.safe_load(p.read_text(encoding="utf-8"))


for key, route, fname in [("DB.MATL-M1", "/db/MATL-M1", "db-matl-m1.yaml"),
                          ("DB.MVHL", "/db/MVHL", "db-mvhl.yaml")]:
    o, s = ours(key), server(route)
    print("=" * 96)
    print(f"{key}   {route}")
    print("=" * 96)
    print(f"  OURS {len(o)} paths · SERVER /info {len(s)} paths")
    print(f"  server-only ({len(set(s) - set(o))}): {sorted(set(s) - set(o))[:24]}")
    print(f"  ours-only   ({len(set(o) - set(s))}): {sorted(set(o) - set(s))[:24]}")
    tdiff = [(k, o[k], s[k]) for k in sorted(set(o) & set(s)) if o[k] and s[k] and o[k] != s[k]]
    print(f"  type diffs  ({len(tdiff)}): {tdiff[:12]}")
    c = contract(fname)
    if c:
        print(f"  contract products={c.get('products')} · verification={json.dumps(c.get('verification'), ensure_ascii=False)[:120]}")
        print("  manualDefects:")
        print("   ", json.dumps(c.get("manualDefects"), ensure_ascii=False, indent=1)[:1800].replace("\n", "\n    "))
    print()
