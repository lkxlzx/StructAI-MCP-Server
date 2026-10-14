"""Field-level diff v2 — canonical item-level comparison.

Server /info returns:  {"$schema":..., "Argument": {<ITEM SCHEMA>}}
Local registry schema: {"<CODE>": {"properties": {"Assign": {"additionalProperties": <ITEM SCHEMA>}}}}
                   or: {"<CODE>": {"properties": {"Argument": <ITEM SCHEMA>}}}
So compare ITEM against ITEM.
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SDK = Path(r"E:\MCP\MMCP\.tmp_nxsdk")
LOCAL = Path(r"E:\MCP\MMCP")
OUT = LOCAL / ".tmp_analysis"


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def flatten(schema, prefix="", out=None, depth=0, maxdepth=6):
    if out is None:
        out = {}
    if not isinstance(schema, dict) or depth > maxdepth:
        return out
    props = schema.get("properties")
    if isinstance(props, dict):
        for name, sub in props.items():
            path = f"{prefix}.{name}" if prefix else name
            out.setdefault(path, {})
            if isinstance(sub, dict):
                if sub.get("type"):
                    out[path]["type"] = sub["type"]
                if sub.get("description"):
                    out[path]["desc"] = sub["description"].strip()
                if sub.get("default") is not None:
                    out[path]["default"] = sub["default"]
                if sub.get("enum"):
                    out[path]["enum"] = sub["enum"]
            flatten(sub, path, out, depth + 1, maxdepth)
    items = schema.get("items")
    if isinstance(items, dict):
        path = f"{prefix}[]"
        out.setdefault(path, {})
        if items.get("type"):
            out[path]["type"] = items["type"]
        flatten(items, path, out, depth + 1, maxdepth)
    for comb in ("oneOf", "anyOf", "allOf"):
        if isinstance(schema.get(comb), list):
            for sub in schema[comb]:
                flatten(sub, prefix, out, depth + 1, maxdepth)
    return out


def sdk_item(schema):
    """Server /info: unwrap the 'Argument' root."""
    if not isinstance(schema, dict):
        return None
    for k, v in schema.items():
        if k == "$schema":
            continue
        if isinstance(v, dict) and ("properties" in v or "type" in v):
            return v
    return None


def local_item(schema_root):
    """Local: schema_root is the dict under the top-level code key."""
    if not isinstance(schema_root, dict):
        return None
    props = schema_root.get("properties")
    if isinstance(props, dict):
        if "Assign" in props and isinstance(props["Assign"], dict):
            ap = props["Assign"].get("additionalProperties")
            if isinstance(ap, dict):
                return ap
        if "Argument" in props and isinstance(props["Argument"], dict):
            return props["Argument"]
        # already an item-level schema (has real field props)
        return schema_root
    return schema_root


# ---------------- SDK ----------------
ib = load(SDK / "schema" / "info-baseline.json")["endpoints"]
sdk = {}
for route, entry in ib.items():
    per = {}
    for prod in ("gen", "civil"):
        e = entry.get(prod)
        if not isinstance(e, dict):
            continue
        it = sdk_item(e.get("schema"))
        if it is None:
            continue
        per[prod] = flatten(it)
    if per:
        sdk[route] = per

# ---------------- local ----------------
manifest = load(LOCAL / "registry" / "manifest.json")
local = {}
for ep in manifest["endpoints"]:
    rel = ep.get("schema")
    if not rel:
        continue
    p = LOCAL / "registry" / rel
    if not p.exists():
        continue
    d = load(p)
    root = d.get("schema")
    if not isinstance(root, dict):
        continue
    # top-level code key
    inner = None
    for k, v in root.items():
        if isinstance(v, dict):
            inner = v
            break
    if inner is None:
        continue
    it = local_item(inner)
    if it is None:
        continue
    flat = flatten(it)
    route = "/" + ep["uri"].strip("/")
    for prod in ep["products"]:
        local[(route.upper(), prod)] = (flat, rel)

PRODMAP = {"gen": "GEN_NX", "civil": "CIVIL_NX"}
rows = []
pairs = 0
for route, per in sorted(sdk.items()):
    for sprod, sf in per.items():
        lprod = PRODMAP[sprod]
        pairs += 1
        hit = local.get((route.upper(), lprod))
        if hit is None:
            rows.append({"route": route, "product": lprod, "status": "NO_LOCAL_SCHEMA",
                         "sdk_only": sorted(sf), "local_only": [], "type_mismatch": [],
                         "desc_only": [], "sdk_n": len(sf)})
            continue
        lf, rel = hit
        sset, lset = set(sf), set(lf)
        s_only = sorted(sset - lset)
        l_only = sorted(lset - sset)
        tm, donly = [], []
        for f in sorted(sset & lset):
            st = sf[f].get("type"); lt = lf[f].get("type")
            if st and lt and st != lt:
                tm.append({"path": f, "local": lt, "server": st})
            if sf[f].get("desc") and not lf[f].get("desc"):
                donly.append(f)
        if s_only or l_only or tm:
            rows.append({"route": route, "product": lprod, "status": "DIFF",
                         "schema": rel, "sdk_only": s_only, "local_only": l_only,
                         "type_mismatch": tm, "desc_only": donly, "sdk_n": len(sf),
                         "local_n": len(lf)})

print(f"compared pairs: {pairs}")
print("status:", Counter(r["status"] for r in rows))
print(f"clean pairs: {pairs - len(rows)}")
print(f"pairs with diff: {sum(1 for r in rows if r['status']=='DIFF')}")
print(f"pairs with NO local schema: {sum(1 for r in rows if r['status']=='NO_LOCAL_SCHEMA')}")
print(f"fields only on server (/info): {sum(len(r['sdk_only']) for r in rows)}")
print(f"fields only local: {sum(len(r['local_only']) for r in rows)}")
print(f"type mismatches: {sum(len(r['type_mismatch']) for r in rows)}")
print(f"descriptions available only from server: {sum(len(r['desc_only']) for r in rows)}")
print()
print("--- NO_LOCAL_SCHEMA pairs ---")
for r in rows:
    if r["status"] == "NO_LOCAL_SCHEMA":
        print(f"  {r['route']:40s} {r['product']:10s} server_fields={r['sdk_n']}")
print()
print("--- top 30 DIFF by missing ---")
for r in sorted([r for r in rows if r["status"] == "DIFF"], key=lambda x: -len(x["sdk_only"]))[:30]:
    print(f"  {r['route']:32s} {r['product']:9s} miss={len(r['sdk_only']):3d} extra={len(r['local_only']):3d} tmis={len(r['type_mismatch']):2d} descgap={len(r['desc_only']):3d}  {r.get('schema','')}")

with open(OUT / "field_diff_v2.json", "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=1)
print()
print("wrote", OUT / "field_diff_v2.json")
