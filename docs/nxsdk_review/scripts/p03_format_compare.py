"""Compare local registry definition YAML format vs SDK contract YAML format."""
import sys
import json
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")

LOCAL = Path(r"E:\MCP\MMCP")
SDK = Path(r"E:\MCP\MMCP\.tmp_nxsdk")

print("=" * 72)
print("LOCAL registry definition YAML sample")
print("=" * 72)
for rel in [r"registry\common\db\NODE.yaml", r"registry\products\gen_nx\db\GALD.yaml"]:
    p = LOCAL / rel
    if not p.exists():
        # find any
        continue
    print("---", rel, "---")
    print(p.read_text(encoding="utf-8")[:2200])

print()
print("=" * 72)
print("SDK contract YAML sample")
print("=" * 72)
for rel in [r"contracts\endpoints\db-node.yaml", r"contracts\endpoints\db-nmas.yaml"]:
    p = SDK / rel
    if p.exists():
        print("---", rel, "---")
        print(p.read_text(encoding="utf-8")[:3500])
    else:
        print("missing", rel)

print()
print("all db-*.yaml sample list:", [p.name for p in sorted((SDK / "contracts" / "endpoints").glob("*.yaml"))[:8]])
print("contracts subdirs:", [d.name for d in (SDK / "contracts").iterdir()])
