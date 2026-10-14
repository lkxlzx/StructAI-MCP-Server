"""Full 3-way shape comparison for /db/REBR (MD-34)."""
import json
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")


def dump_schema(node, indent=0, depth=0, maxdepth=4):
    if depth > maxdepth or not isinstance(node, dict):
        return
    props = node.get("properties")
    if isinstance(props, dict):
        for k, v in props.items():
            t = v.get("type") if isinstance(v, dict) else None
            extra = ""
            if isinstance(v, dict):
                if v.get("enum"):
                    extra += f" enum={v['enum']}"
                if v.get("default") is not None:
                    extra += f" default={v['default']!r}"
                if v.get("minItems") is not None:
                    extra += f" minItems={v['minItems']}"
                if v.get("maxItems") is not None:
                    extra += f" maxItems={v['maxItems']}"
            print("  " * (indent + 1) + f"{k}: {t}{extra}")
            dump_schema(v, indent + 1, depth + 1, maxdepth)
    items = node.get("items")
    if isinstance(items, dict):
        dump_schema(items, indent, depth + 1, maxdepth)
    for comb in ("oneOf", "anyOf", "allOf"):
        for sub in node.get(comb) or []:
            dump_schema(sub, indent, depth + 1, maxdepth)


# ---- ours ----
d = json.loads((REPO / "registry" / "schema" / "common" / "db" / "REBR.json").read_text(encoding="utf-8"))
print("=" * 96)
print("OURS  schema/common/db/REBR.json")
print("=" * 96)
sch = d["schema"]
print("root keys:", list(sch))
assign = sch["properties"]["Assign"]
print("Assign keys:", list(assign))
pp = assign.get("patternProperties") or {}
item = next(iter(pp.values())) if pp else assign.get("additionalProperties")
print("item keys:", list(item) if isinstance(item, dict) else item)
print("item required:", item.get("required") if isinstance(item, dict) else None)
dump_schema(item, 0, 0, 4)

# ---- server /info ----
ib = json.loads((REPO / ".tmp_nxsdk" / "schema" / "info-baseline.json").read_text(encoding="utf-8"))
print()
print("=" * 96)
print("SERVER /info/db/REBR")
print("=" * 96)
for prod in ("gen", "civil"):
    e = ib["endpoints"]["/db/REBR"].get(prod)
    if not e or not isinstance(e.get("schema"), dict):
        print(f"  [{prod}] (no schema entry)")
        continue
    s = e["schema"]
    root = next(v for k, v in s.items() if k != "$schema")
    print(f"  [{prod}] status={e.get('status')} root props:", list(root.get("properties", {})))
    dump_schema(root, 1, 0, 5)

# ---- contract ----
c = yaml.safe_load((REPO / ".tmp_nxsdk" / "contracts" / "endpoints" / "db-rebr.yaml").read_text(encoding="utf-8"))
print()
print("=" * 96)
print("CONTRACT db-rebr.yaml")
print("=" * 96)
print("products:", c.get("products"))
print("verification:", json.dumps(c.get("verification"), ensure_ascii=False)[:300])


def dump_contract(fields, indent=0, depth=0):
    if depth > 5:
        return
    for f in fields or []:
        if not isinstance(f, dict):
            continue
        extra = ""
        for k in ("type", "enum", "requirement", "documentedDefault", "safeToOmit", "provenance"):
            if f.get(k) is not None:
                extra += f" {k}={f[k]!r}"
        print("  " * (indent + 1) + f"{f.get('key')}:{extra}")
        dump_contract(f.get("properties"), indent + 1, depth + 1)
        if isinstance(f.get("items"), dict):
            dump_contract([f["items"]], indent + 1, depth + 1)
        elif isinstance(f.get("items"), list):
            dump_contract(f["items"], indent + 1, depth + 1)


dump_contract(c.get("fields"))
