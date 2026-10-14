"""Field-level diff: SDK server-side /info baseline vs local registry JSON Schemas.

SDK: .tmp_nxsdk/schema/info-baseline.json
     endpoints["/db/NODE"]["gen"|"civil"]["schema"] -> {"$schema":..., "Argument"|"<CODE>": {properties:{...}}}
Local: registry/schema/**/*.json -> {"key","uri","source","schema":{"<ROOT>":{...}},"response":{...}}
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SDK = Path(r"E:\MCP\MMCP\.tmp_nxsdk")
LOCAL = Path(r"E:\MCP\MMCP")
OUT = Path(r"E:\MCP\MMCP\.tmp_analysis")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def find_props_container(node, depth=0):
    """Return the dict that holds 'properties' at the top of an /info schema."""
    if not isinstance(node, dict) or depth > 3:
        return None
    if "properties" in node and isinstance(node["properties"], dict):
        return node
    for k, v in node.items():
        if k == "$schema":
            continue
        r = find_props_container(v, depth + 1)
        if r is not None:
            return r
    return None


def flatten(schema, prefix="", out=None, depth=0, maxdepth=8):
    """Flatten a JSON-schema-ish object into {path: type} using properties/items."""
    if out is None:
        out = {}
    if not isinstance(schema, dict) or depth > maxdepth:
        return out
    props = schema.get("properties")
    if isinstance(props, dict):
        for name, sub in props.items():
            path = f"{prefix}.{name}" if prefix else name
            t = sub.get("type") if isinstance(sub, dict) else None
            out[path] = t
            flatten(sub, path, out, depth + 1, maxdepth)
    items = schema.get("items")
    if isinstance(items, dict):
        path = f"{prefix}[]"
        t = items.get("type")
        out[path] = t
        flatten(items, path, out, depth + 1, maxdepth)
    for comb in ("oneOf", "anyOf", "allOf"):
        if isinstance(schema.get(comb), list):
            for i, sub in enumerate(schema[comb]):
                flatten(sub, prefix, out, depth + 1, maxdepth)
    return out


# ---------- SDK side ----------
ib = load(SDK / "schema" / "info-baseline.json")
sdk_eps = ib["endpoints"]
sdk = {}  # route -> {product: {path: type}}
for route, entry in sdk_eps.items():
    per = {}
    for prod in ("gen", "civil"):
        e = entry.get(prod)
        if not e or not isinstance(e, dict):
            continue
        sch = e.get("schema")
        if not isinstance(sch, dict):
            continue
        cont = find_props_container(sch)
        if cont is None:
            continue
        per[prod] = flatten(cont)
    if per:
        sdk[route] = per

print(f"SDK /info endpoints with usable schema: {len(sdk)}")
print(f"SDK total /info endpoints: {len(sdk_eps)}")

# ---------- local side ----------
local = {}  # (route_upper, product) -> {path: type} ; route_upper like DB/NODE
manifest = load(LOCAL / "registry" / "manifest.json")
missing_files = []
for ep in manifest["endpoints"]:
    rel = ep.get("schema")
    if not rel:
        continue
    p = LOCAL / "registry" / rel
    if not p.exists():
        missing_files.append(rel)
        continue
    d = load(p)
    sch = d.get("schema")
    if not isinstance(sch, dict):
        continue
    cont = find_props_container(sch)
    if cont is None:
        continue
    flat = flatten(cont)
    route = "/" + ep["uri"].strip("/")
    for prod in ep["products"]:
        local[(route.upper(), prod)] = flat

print(f"local schema files present: {len(local)} (route,product) pairs")
if missing_files:
    print(f"WARNING missing schema files referenced by manifest: {len(missing_files)}")
    for m in missing_files[:10]:
        print("   ", m)

# ---------- compare ----------
PRODMAP = {"gen": "GEN_NX", "civil": "CIVIL_NX"}
rows = []
for route, per in sorted(sdk.items()):
    for sprod, sfields in per.items():
        lprod = PRODMAP[sprod]
        key = (route.upper(), lprod)
        lfields = local.get(key)
        if lfields is None:
            rows.append({
                "route": route, "product": lprod,
                "status": "LOCAL_SCHEMA_ABSENT",
                "sdk_only": sorted(sfields), "local_only": [],
            })
            continue
        sset, lset = set(sfields), set(lfields)
        s_only = sorted(sset - lset)
        l_only = sorted(lset - sset)
        # type mismatches on shared paths
        tmismatch = []
        for f in sorted(sset & lset):
            st, lt = sfields[f], lfields[f]
            if st and lt and st != lt:
                tmismatch.append((f, lt, st))
        if s_only or l_only or tmismatch:
            rows.append({
                "route": route, "product": lprod, "status": "DIFF",
                "sdk_only": s_only, "local_only": l_only,
                "type_mismatch": tmismatch,
            })

print()
print("=" * 72)
from collections import Counter

print("status:", Counter(r["status"] for r in rows))
print(f"compared (route,product) pairs: {sum(len(v) for v in sdk.values())}")
print(f"pairs with any difference: {len(rows)}")

with open(OUT / "field_diff_raw.json", "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=1)
print("wrote", OUT / "field_diff_raw.json")

# summary
tot_sdk_only = sum(len(r["sdk_only"]) for r in rows)
tot_local_only = sum(len(r["local_only"]) for r in rows)
tot_tm = sum(len(r.get("type_mismatch", [])) for r in rows)
print(f"fields only in server /info (we lack): {tot_sdk_only}")
print(f"fields only in our schema (server /info lacks): {tot_local_only}")
print(f"type mismatches: {tot_tm}")
print()
print("top 25 routes by #missing-fields:")
for r in sorted(rows, key=lambda x: -len(x["sdk_only"]))[:25]:
    print(f"  {r['route']:45s} {r['product']:9s} missing={len(r['sdk_only']):3d} extra={len(r['local_only']):3d} tmis={len(r.get('type_mismatch',[])):3d}")
