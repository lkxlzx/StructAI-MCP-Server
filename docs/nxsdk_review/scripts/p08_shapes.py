"""Classify every local registry schema file by structural shape, and show samples."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

LOCAL = Path(r"E:\MCP\MMCP")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


manifest = load(LOCAL / "registry" / "manifest.json")
shapes = Counter()
examples = defaultdict(list)
files = set()

for ep in manifest["endpoints"]:
    rel = ep.get("schema")
    if not rel or rel in files:
        continue
    files.add(rel)
    p = LOCAL / "registry" / rel
    if not p.exists():
        shapes["MISSING_FILE"] += 1
        continue
    d = load(p)
    root = d.get("schema")
    if not isinstance(root, dict):
        shapes["NO_SCHEMA_KEY"] += 1
        examples["NO_SCHEMA_KEY"].append(rel)
        continue
    ks = [k for k in root if k != "$schema"]
    if any(k in root for k in ("type", "properties", "oneOf", "allOf", "anyOf")) and "properties" in root:
        # bare JSON Schema at root
        props = root.get("properties", {})
        if "Assign" in props:
            shapes["BARE_ASSIGN"] += 1
            examples["BARE_ASSIGN"].append(rel)
        elif "Argument" in props:
            shapes["BARE_ARGUMENT"] += 1
            examples["BARE_ARGUMENT"].append(rel)
        else:
            shapes["BARE_OTHER"] += 1
            examples["BARE_OTHER"].append(rel)
        continue
    if len(ks) == 1:
        code = ks[0]
        v = root[code]
        if not isinstance(v, dict):
            shapes["CODEKEY_NONDICT"] += 1
            examples["CODEKEY_NONDICT"].append(rel)
            continue
        if "properties" in v:
            props = v["properties"]
            if "Assign" in props:
                shapes["CODEKEY_JSONSCHEMA_ASSIGN"] += 1
                examples["CODEKEY_JSONSCHEMA_ASSIGN"].append(rel)
            elif "Argument" in props:
                shapes["CODEKEY_JSONSCHEMA_ARGUMENT"] += 1
                examples["CODEKEY_JSONSCHEMA_ARGUMENT"].append(rel)
            else:
                shapes["CODEKEY_JSONSCHEMA_FLAT"] += 1
                examples["CODEKEY_JSONSCHEMA_FLAT"].append(rel)
        elif any(k in v for k in ("type", "oneOf", "allOf", "anyOf", "$ref")):
            shapes["CODEKEY_MIXED"] += 1
            examples["CODEKEY_MIXED"].append(rel)
        else:
            shapes["CODEKEY_SHORTHAND"] += 1
            examples["CODEKEY_SHORTHAND"].append(rel)
        continue
    shapes["MULTIKEY"] += 1
    examples["MULTIKEY"].append((rel, ks))

print("total distinct schema files referenced:", len(files))
print()
for k, n in shapes.most_common():
    print(f"  {k:34s} {n:5d}")
print()
for k, v in examples.items():
    print(f"--- {k} examples ---")
    for x in v[:6]:
        print("   ", x)
    print()
