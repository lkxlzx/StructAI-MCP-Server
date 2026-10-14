"""Field-level diff v4 — handles additionalProperties AND patternProperties. Final."""
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


def map_value(container):
    """Return the item schema from an id-keyed map (additionalProperties / patternProperties)."""
    if not isinstance(container, dict):
        return None
    ap = container.get("additionalProperties")
    if isinstance(ap, dict):
        return ap
    pp = container.get("patternProperties")
    if isinstance(pp, dict) and pp:
        return next(iter(pp.values()))
    return None


def unwrap(owner):
    if not isinstance(owner, dict):
        return None
    props = owner.get("properties")
    if isinstance(props, dict):
        for wrapper in ("Assign", "Argument"):
            if wrapper in props and isinstance(props[wrapper], dict):
                w = props[wrapper]
                inner = map_value(w)
                if isinstance(inner, dict):
                    return inner
                return w
    return owner


def extract_items(root):
    if not isinstance(root, dict):
        return []
    ks = [k for k in root if k != "$schema"]
    if "properties" in root:
        return [unwrap(root)]
    if len(ks) == 1:
        v = root[ks[0]]
        if not isinstance(v, dict):
            return []
        if "properties" in v or map_value(v):
            return [unwrap(v)]
        if any(k in v for k in ("type", "oneOf", "allOf", "anyOf", "items")):
            return [unwrap(v)]
        return [{"properties": v}]
    out = []
    for k in ks:
        v = root[k]
        if isinstance(v, dict):
            out.append(unwrap(v) if ("properties" in v or map_value(v)) else {"properties": v})
    return out


def flatten(schema, prefix="", out=None, depth=0, maxdepth=7):
    if out is None:
        out = {}
    if not isinstance(schema, dict) or depth > maxdepth:
        return out
    props = schema.get("properties")
    if isinstance(props, dict):
        for name, sub in props.items():
            path = f"{prefix}.{name}" if prefix else name
            rec = out.setdefault(path, {})
            if isinstance(sub, dict):
                for f in ("type", "default", "enum", "format"):
                    if sub.get(f) is not None:
                        rec[f] = sub[f]
                if sub.get("description"):
                    rec["desc"] = sub["description"].strip()
            flatten(sub, path, out, depth + 1, maxdepth)
    pp = schema.get("patternProperties")
    if isinstance(pp, dict):
        for _pat, sub in pp.items():
            flatten(sub, prefix, out, depth + 1, maxdepth)
    items = schema.get("items")
    if isinstance(items, dict):
        path = f"{prefix}[]"
        rec = out.setdefault(path, {})
        if items.get("type"):
            rec["type"] = items["type"]
        flatten(items, path, out, depth + 1, maxdepth)
    for comb in ("oneOf", "anyOf", "allOf"):
        if isinstance(schema.get(comb), list):
            for sub in schema[comb]:
                flatten(sub, prefix, out, depth + 1, maxdepth)
    return out


def sdk_item(schema):
    if not isinstance(schema, dict):
        return None
    for k, v in schema.items():
        if k == "$schema":
            continue
        if isinstance(v, dict) and ("properties" in v or "type" in v):
            return v
    return None


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
    items = extract_items(d.get("schema"))
    if not items:
        continue
    merged = {}
    for it in items:
        merged.update(flatten(it))
    route = "/" + ep["uri"].strip("/")
    for prod in ep["products"]:
        local[(route.upper(), prod)] = (merged, rel, ep["key"])

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
                         "sdk_n": len(sf), "local_n": 0, "key": None})
            continue
        lf, rel, key = hit
        sset, lset = set(sf), set(lf)
        s_only = sorted(sset - lset)
        l_only = sorted(lset - sset)
        tm = []
        for f in sorted(sset & lset):
            st, lt = sf[f].get("type"), lf[f].get("type")
            if st and lt and st != lt:
                tm.append({"path": f, "local": lt, "server": st,
                           "local_desc": lf[f].get("desc", ""), "server_desc": sf[f].get("desc", "")})
        if s_only or l_only or tm:
            rows.append({"route": route, "product": lprod, "status": "DIFF", "schema": rel, "key": key,
                         "sdk_only": s_only, "local_only": l_only, "type_mismatch": tm,
                         "sdk_n": len(sf), "local_n": len(lf)})

print(f"compared pairs: {pairs}")
print("status:", Counter(r["status"] for r in rows))
print(f"CLEAN pairs: {pairs - len(rows)}")
print(f"DIFF pairs: {sum(1 for r in rows if r['status']=='DIFF')}")
print(f"NO_LOCAL_SCHEMA pairs: {sum(1 for r in rows if r['status']=='NO_LOCAL_SCHEMA')}")
print(f"fields only on server: {sum(len(r['sdk_only']) for r in rows)}")
print(f"fields only local: {sum(len(r['local_only']) for r in rows)}")
print(f"type mismatches: {sum(len(r['type_mismatch']) for r in rows)}")
print()
print("--- DIFF pairs (non-empty missing) ---")
for r in sorted([r for r in rows if r["status"] == "DIFF" and r["sdk_only"]], key=lambda x: -len(x["sdk_only"])):
    print(f"  {r['route']:24s} {r['product']:9s} miss={len(r['sdk_only']):3d} extra={len(r['local_only']):3d} tmis={len(r['type_mismatch']):2d} sdkN={r['sdk_n']:4d} locN={r['local_n']:4d}  key={r['key']}")
print()
print("--- DIFF pairs (extra / type only, missing==0) ---")
for r in sorted([r for r in rows if r["status"] == "DIFF" and not r["sdk_only"]], key=lambda x: -(len(x["local_only"]) + len(x["type_mismatch"]))):
    print(f"  {r['route']:24s} {r['product']:9s} extra={len(r['local_only']):3d} tmis={len(r['type_mismatch']):2d}  key={r['key']}")
print()
print("--- NO_LOCAL_SCHEMA ---")
for r in rows:
    if r["status"] == "NO_LOCAL_SCHEMA":
        print(f"  {r['route']:24s} {r['product']:9s} server_fields={r['sdk_n']}")

with open(OUT / "field_diff_v4.json", "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=1)
print()
print("wrote", OUT / "field_diff_v4.json")
