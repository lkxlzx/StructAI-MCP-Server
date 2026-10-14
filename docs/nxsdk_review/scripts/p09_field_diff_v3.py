"""Field-level diff v3 — definitive item extraction across all 7 local schema shapes."""
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


def unwrap(props_owner):
    """Given a dict that may hold 'properties', return the ITEM schema."""
    if not isinstance(props_owner, dict):
        return None
    props = props_owner.get("properties")
    if isinstance(props, dict):
        if "Assign" in props and isinstance(props["Assign"], dict):
            ap = props["Assign"].get("additionalProperties")
            if isinstance(ap, dict):
                return ap
            return props["Assign"]
        if "Argument" in props and isinstance(props["Argument"], dict):
            return props["Argument"]
    return props_owner


def extract_items(root):
    """Return list of item schemas from a local schema file's 'schema' value."""
    if not isinstance(root, dict):
        return []
    ks = [k for k in root if k != "$schema"]
    # bare JSON Schema at root
    if "properties" in root:
        return [unwrap(root)]
    if len(ks) == 1:
        v = root[ks[0]]
        if not isinstance(v, dict):
            return []
        if "properties" in v:
            return [unwrap(v)]
        if any(k in v for k in ("type", "oneOf", "allOf", "anyOf", "items")):
            return [unwrap(v)]
        # shorthand: fields directly
        return [{"properties": v}]
    out = []
    for k in ks:
        v = root[k]
        if isinstance(v, dict):
            if "properties" in v:
                out.append(unwrap(v))
            else:
                out.append({"properties": v})
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
    items = extract_items(d.get("schema"))
    if not items:
        continue
    merged = {}
    for it in items:
        merged.update(flatten(it))
    route = "/" + ep["uri"].strip("/")
    for prod in ep["products"]:
        local[(route.upper(), prod)] = (merged, rel)

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
                         "sdk_n": len(sf), "local_n": 0})
            continue
        lf, rel = hit
        sset, lset = set(sf), set(lf)
        s_only = sorted(sset - lset)
        l_only = sorted(lset - sset)
        tm = []
        for f in sorted(sset & lset):
            st, lt = sf[f].get("type"), lf[f].get("type")
            if st and lt and st != lt:
                tm.append({"path": f, "local": lt, "server": st})
        if s_only or l_only or tm:
            rows.append({"route": route, "product": lprod, "status": "DIFF", "schema": rel,
                         "sdk_only": s_only, "local_only": l_only, "type_mismatch": tm,
                         "sdk_n": len(sf), "local_n": len(lf)})

print(f"compared pairs: {pairs}")
print("status:", Counter(r["status"] for r in rows))
print(f"clean pairs: {pairs - len(rows)}")
print(f"DIFF pairs: {sum(1 for r in rows if r['status']=='DIFF')}")
print(f"NO_LOCAL_SCHEMA pairs: {sum(1 for r in rows if r['status']=='NO_LOCAL_SCHEMA')}")
print(f"fields only server: {sum(len(r['sdk_only']) for r in rows)}")
print(f"fields only local: {sum(len(r['local_only']) for r in rows)}")
print(f"type mismatches: {sum(len(r['type_mismatch']) for r in rows)}")
print()
print("--- NO_LOCAL_SCHEMA (31 max) ---")
for r in rows:
    if r["status"] == "NO_LOCAL_SCHEMA":
        print(f"  {r['route']:34s} {r['product']:10s} server_fields={r['sdk_n']}")
print()
print("--- DIFF, sorted by missing ---")
for r in sorted([r for r in rows if r["status"] == "DIFF"], key=lambda x: -len(x["sdk_only"])):
    print(f"  {r['route']:30s} {r['product']:9s} miss={len(r['sdk_only']):3d} extra={len(r['local_only']):3d} tmis={len(r['type_mismatch']):2d} sdkN={r['sdk_n']:3d} locN={r['local_n']:3d}")
print()
print("--- TYPE MISMATCHES (all) ---")
for r in rows:
    for t in r.get("type_mismatch", []):
        print(f"  {r['route']:30s} {r['product']:9s} {t['path']:40s} local={t['local']:10s} server={t['server']}")

with open(OUT / "field_diff_v3.json", "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=1)
print()
print("wrote", OUT / "field_diff_v3.json")
