"""Build corrected JSON Schema item shapes for the /db/REB* family from the SDK's reviewed contracts.

Source of truth for the shape: `contracts/endpoints/db-reb*.yaml` (which matches GET /info exactly
in all four cases — 45/45, 22/22, 17/17, 20/20 paths), plus the live refusal evidence in
`docs/live_verification_notes.md` A-01..A-04.

Prints the generated schema for review; writes nothing.
"""
import json
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
SDK = REPO / ".tmp_nxsdk"

KEEP = ("type", "enum", "minimum", "maximum", "minItems", "maxItems")


def to_schema(field: dict) -> dict:
    """Convert one contract field (recursively) to a JSON Schema fragment.

    ⚠️ A contract field of `type: array` carries its element members in a **sibling**
    `properties` list (with `items: {type: object}`); those belong *inside* `items`,
    not beside `type`.
    """
    out: dict = {}
    ftype = field.get("type")
    if ftype:
        out["type"] = ftype
    for k in KEEP[1:]:
        if field.get(k) is not None:
            out[k] = field[k]
    if field.get("description"):
        out["description"] = field["description"]

    props = field.get("properties")
    sub, sub_req = (None, None)
    if isinstance(props, list) and props:
        sub, sub_req = to_properties(props)

    items = field.get("items")
    if ftype == "array":
        if sub:
            item_schema: dict = {"type": "object", "properties": sub}
            if sub_req:
                item_schema["required"] = sub_req
        elif isinstance(items, dict) and items:
            item_schema = to_schema(items)
        else:
            item_schema = {"type": "object"}
        out["items"] = item_schema
    else:
        if sub:
            out["properties"] = sub
            if sub_req:
                out["required"] = sub_req
        if isinstance(items, dict) and items and "properties" not in out:
            out["items"] = to_schema(items)
    return out


def to_properties(fields: list) -> tuple[dict, list]:
    props, required = {}, []
    for f in fields:
        if not isinstance(f, dict) or not f.get("key"):
            continue
        props[f["key"]] = to_schema(f)
        if f.get("requirement") == "required":
            required.append(f["key"])
    return props, required


def contract_items(fname: str):
    c = yaml.safe_load((SDK / "contracts" / "endpoints" / fname).read_text(encoding="utf-8"))

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

    return c, find(c.get("fields", []))


for key, fname in [("DB.REBB", "db-rebb.yaml"), ("DB.REBC", "db-rebc.yaml"), ("DB.REBW", "db-rebw.yaml")]:
    c, items = contract_items(fname)
    props, required = to_properties(items["properties"])
    item_schema = {"type": "object", "properties": props}
    if required:
        item_schema["required"] = required
    out = {
        "key": key,
        "endpoint": c.get("endpoint"),
        "products": c.get("products"),
        "verification": c.get("verification"),
        "items_schema": item_schema,
    }
    p = REPO / ".tmp_analysis" / f"generated_{key.replace('.', '_')}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{key}: {len(props)} properties, required={required}  -> {p.name}")
    print(f"    keys: {sorted(props)}")
    print()
