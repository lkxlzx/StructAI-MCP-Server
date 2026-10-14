"""Compare the whole /db/REB* family: our schema vs server /info vs SDK contract."""
import json
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
SDK = REPO / ".tmp_nxsdk"
ib = json.loads((SDK / "schema" / "info-baseline.json").read_text(encoding="utf-8"))


def props_of(node):
    if not isinstance(node, dict):
        return {}
    return node.get("properties") or {}


def leaf_paths(node, prefix="", out=None, depth=0):
    if out is None:
        out = set()
    if not isinstance(node, dict) or depth > 5:
        return out
    for k, v in props_of(node).items():
        p = f"{prefix}.{k}" if prefix else k
        out.add(p)
        leaf_paths(v, p, out, depth + 1)
    it = node.get("items")
    if isinstance(it, dict):
        leaf_paths(it, f"{prefix}[]", out, depth + 1)
    return out


def our_item(key):
    rel = None
    man = json.loads((REPO / "registry" / "manifest.json").read_text(encoding="utf-8"))
    for e in man["endpoints"]:
        if e["key"] == key:
            rel = e["schema"]
    if not rel:
        return None
    d = json.loads((REPO / "registry" / rel).read_text(encoding="utf-8"))
    sch = d["schema"]
    if "properties" in sch and "Assign" in sch["properties"]:
        a = sch["properties"]["Assign"]
        pp = a.get("patternProperties") or {}
        if pp:
            return next(iter(pp.values()))
        return a.get("additionalProperties")
    return None


def server_item(route):
    e = (ib["endpoints"].get(route) or {}).get("gen")
    if not e or not isinstance(e.get("schema"), dict):
        return None
    root = next((v for k, v in e["schema"].items() if k != "$schema"), {})
    items = props_of(root).get("ITEMS")
    return items.get("items") if isinstance(items, dict) else None


def contract_item(fname):
    p = SDK / "contracts" / "endpoints" / fname
    if not p.exists():
        return None
    c = yaml.safe_load(p.read_text(encoding="utf-8"))

    def find(node):
        if isinstance(node, dict):
            if node.get("key") == "ITEMS" and isinstance(node.get("properties"), list):
                return node
            for v in node.values():
                r = find(v)
                if r:
                    return r
        elif isinstance(node, list):
            for v in node:
                r = find(v)
                if r:
                    return r
        return None

    return find(c.get("fields", []))


for key, route, fname in [
    ("DB.REBB", "/db/REBB", "db-rebb.yaml"),
    ("DB.REBC", "/db/REBC", "db-rebc.yaml"),
    ("DB.REBR", "/db/REBR", "db-rebr.yaml"),
    ("DB.REBW", "/db/REBW", "db-rebw.yaml"),
]:
    print("=" * 96)
    print(f"{key}   {route}")
    print("=" * 96)
    ours = leaf_paths(our_item(key))
    srv = leaf_paths(server_item(route))
    ctr = contract_item(fname)
    ctr_paths = set()

    def walk_c(fields, prefix=""):
        for f in fields or []:
            if not isinstance(f, dict):
                continue
            k = f.get("key")
            if not k:
                continue
            p = f"{prefix}.{k}" if prefix else k
            ctr_paths.add(p)
            walk_c(f.get("properties"), p)
            if isinstance(f.get("items"), dict):
                walk_c([f["items"]], f"{p}[]")
            elif isinstance(f.get("items"), list):
                walk_c(f["items"], f"{p}[]")

    walk_c(ctr.get("properties") if ctr else None)
    print(f"  OURS  ({len(ours)}): {sorted(ours)}")
    print(f"  SERVER({len(srv)}): {sorted(srv)}")
    print(f"  CONTR ({len(ctr_paths)}): {sorted(ctr_paths)}")
    print(f"  server-only (我们缺): {sorted(srv - ours)}")
    print(f"  ours-only   (我们多): {sorted(ours - srv)}")
    print(f"  contract-only: {sorted(ctr_paths - ours)}")
    print(f"  ours-only vs contract: {sorted(ours - ctr_paths)}")
    print()
