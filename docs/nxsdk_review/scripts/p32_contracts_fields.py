"""Dump the SDK contracts' reviewed field definitions for the 7 type-fix targets."""
import json
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")
SDK = Path(r"E:\MCP\MMCP\.tmp_nxsdk")
REG = Path(r"E:\MCP\MMCP\registry")

CASES = [
    ("db-epse.yaml", "LOADING_AREA_GROUP"),
    ("db-epst.yaml", "LOADING_AREA_GROUP"),
    ("db-slanop.yaml", "OPT_STRADD"),
    ("db-rpsc.yaml", "LBAR_INC_FC"),
    ("db-nllp.yaml", "SEIS_TYPE"),
    ("db-rebc.yaml", "HOOP_TYPE"),
    ("db-rebr.yaml", "HOOP_TYPE"),
]


def find(node, field, path=""):
    """Yield (path, dict) for every mapping whose 'key' == field."""
    if isinstance(node, dict):
        if node.get("key") == field:
            yield path, node
        for k, v in node.items():
            yield from find(v, field, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from find(v, field, f"{path}[{i}]")


for fname, field in CASES:
    p = SDK / "contracts" / "endpoints" / fname
    print("=" * 92)
    print(f"{fname}  ::  {field}")
    print("=" * 92)
    if not p.exists():
        print("  contract MISSING")
        continue
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    print(f"  endpoint={d.get('endpoint')} products={d.get('products')}")
    hits = list(find(d, field))
    if not hits:
        print("  (field not present in contract)")
        # print top-level keys for orientation
        print("  top keys:", list(d))
    for path, node in hits:
        print(f"  --- {path} ---")
        print("   ", json.dumps(node, ensure_ascii=False)[:700])

print()
print("=" * 92)
print("locate our SLANop / EPSE / EPST / RPSC / NLLP schema files")
print("=" * 92)
for pat in ("*SLANOP*", "*SLANop*", "*EPSE*", "*EPST*", "*RPSC*", "*NLLP*"):
    for f in sorted(REG.rglob(pat)):
        print("  ", f.relative_to(REG))
