"""C 批侦察 —— MD-60 (/db/SPFC EURO2004): 三方差比对。"""
import json
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
SDK = REPO / ".tmp_nxsdk"

ib = json.loads((SDK / "schema" / "info-baseline.json").read_text(encoding="utf-8"))


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


# ---- server /info ----
e = ib["endpoints"]["/db/SPFC"]["gen"]
sch = e["schema"]
root = next(v for k, v in sch.items() if k != "$schema")
srv = props(root)
print("=" * 92)
print(f"SERVER /info/db/SPFC  ({len(srv)} paths)")
print("=" * 92)
for k in sorted(srv):
    print(f"  {k:44s} {srv[k]}")

# ---- ours ----
man = json.loads((REPO / "registry" / "manifest.json").read_text(encoding="utf-8"))["endpoints"]
entry = next(x for x in man if x["key"] == "DB.SPFC")
d = json.loads((REPO / "registry" / entry["schema"]).read_text(encoding="utf-8"))
ours = props(next(v for k, v in d["schema"].items() if k != "$schema"))
print()
print("=" * 92)
print(f"OURS {entry['schema']}  ({len(ours)} paths)")
print("=" * 92)
for k in sorted(ours):
    print(f"  {k:44s} {ours[k]}")

print()
print(f"server-only ({len(set(srv) - set(ours))}):")
for k in sorted(set(srv) - set(ours)):
    print(f"   {k:44s} {srv[k]}")
print(f"ours-only ({len(set(ours) - set(srv))}):")
for k in sorted(set(ours) - set(srv)):
    print(f"   {k:44s} {ours[k]}")
print("type diffs:")
for k in sorted(set(srv) & set(ours)):
    if srv[k] and ours[k] and srv[k] != ours[k]:
        print(f"   {k:44s} ours={ours[k]} server={srv[k]}")

# ---- contract ----
c = yaml.safe_load((SDK / "contracts" / "endpoints" / "db-spfc.yaml").read_text(encoding="utf-8"))
print()
print("=" * 92)
print("CONTRACT db-spfc.yaml")
print("=" * 92)
print("products:", c.get("products"))
print("manualDefects:", json.dumps(c.get("manualDefects"), ensure_ascii=False, indent=1)[:1600])


def walk(fields, path="", depth=0):
    for f in fields or []:
        if not isinstance(f, dict):
            continue
        p = f"{path}.{f['key']}" if path else f["key"]
        if any(t in p.upper() for t in ("OPT", "STR", "VAL", "EURO")):
            print(f"  {p:50s} type={f.get('type')!r} req={f.get('requirement')!r} prov={f.get('provenance')!r}")
        walk(f.get("properties"), p, depth + 1)


print("--- contract fields touching OPT/STR/VAL/EURO ---")
walk(c.get("fields"))
