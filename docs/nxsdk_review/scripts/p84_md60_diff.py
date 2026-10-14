"""MD-60 focused: the server-only / ours-only diff and the contract's EURO2004 statement."""
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


root = next(v for k, v in ib["endpoints"]["/db/SPFC"]["gen"]["schema"].items() if k != "$schema")
srv = props(root)
man = json.loads((REPO / "registry" / "manifest.json").read_text(encoding="utf-8"))["endpoints"]
entry = next(x for x in man if x["key"] == "DB.SPFC")
d = json.loads((REPO / "registry" / entry["schema"]).read_text(encoding="utf-8"))
ours = props(next(v for k, v in d["schema"].items() if k != "$schema"))

print(f"server={len(srv)}  ours={len(ours)}")
print("\n--- server-only (我们缺) ---")
for k in sorted(set(srv) - set(ours)):
    print(f"   {k:44s} {srv[k]}")
print("\n--- ours-only (我们多) ---")
for k in sorted(set(ours) - set(srv)):
    print(f"   {k:44s} {ours[k]}")
print("\n--- type diffs ---")
for k in sorted(set(srv) & set(ours)):
    if srv[k] and ours[k] and srv[k] != ours[k]:
        print(f"   {k:44s} ours={ours[k]} server={srv[k]}")

c = yaml.safe_load((SDK / "contracts" / "endpoints" / "db-spfc.yaml").read_text(encoding="utf-8"))
print("\n=== contract manualDefects ===")
print(json.dumps(c.get("manualDefects"), ensure_ascii=False, indent=1)[:2600])
print("\n=== contract sdkRules ===")
print(json.dumps(c.get("sdkRules"), ensure_ascii=False, indent=1)[:1200])
print("\n=== contract: EURO / STR / OPT 相关字段 ===")


def walk(fields, path=""):
    for f in fields or []:
        if not isinstance(f, dict):
            continue
        p = f"{path}.{f['key']}" if path else f["key"]
        if f["key"] in ("EURO2004", "NATIONALANNEX", "GROUND", "SPEC", "BT", "DIV", "EQ_", "ZM", "SI", "ST", "PARATYPE", "REGION", "RESIONTYPE", "GROUTYPE", "METHOD", "SPECTYPE", "SPEC_CODE"):
            print(f"   {p:46s} type={f.get('type')!r} req={f.get('requirement')!r} prov={f.get('provenance')!r}")
        walk(f.get("properties"), p)


walk(c.get("fields"))
