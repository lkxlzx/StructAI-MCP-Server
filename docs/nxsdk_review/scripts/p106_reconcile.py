"""把三本专用手册的**接口总索引**与我方 636 端点对账（只读）。"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
DOCS = Path(r"E:\MCP\MAPI\docs")

MANUALS = (
    ("Gen", "midas Gen API 专用手册.md"),
    ("CivilNX", "midas Civil NX API 专用手册.md"),
    ("CivilDesigner", "midas Civil Designer API 专用手册.md"),
)
ROW = re.compile(
    r"^\|\s*\d+\s*\|\s*`(?P<code>[^`]+)`\s*\|\s*\[(?P<name>[^\]]*)\]\([^)]*\)\s*\|"
    r"\s*`(?P<url>[^`]+)`\s*\|\s*(?P<methods>[^|]+?)\s*\|\s*(?P<section>[^|]*?)\s*\|"
)


def index_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = ROW.match(line)
        if m:
            rows.append(m.groupdict())
    return rows


manifest = json.loads((REPO / "registry" / "manifest.json").read_text(encoding="utf-8"))["endpoints"]
ours: dict[str, list[dict]] = {}
for e in manifest:
    ours.setdefault(str(e["uri"]).strip("/").upper(), []).append(e)
print(f"我方 registry: {len(manifest)} 端点 / {len(ours)} 个不同 URI")
print()

all_manual: dict[str, list[tuple[str, dict]]] = {}
for product, filename in MANUALS:
    rows = index_rows(DOCS / filename)
    print(f"{product:14s} 索引 {len(rows):>4} 条")
    for r in rows:
        all_manual.setdefault(r["url"].strip("/").upper(), []).append((product, r))
print()
print(f"三本手册合计不同 URL: {len(all_manual)}")

both = set(all_manual) & set(ours)
manual_only = set(all_manual) - set(ours)
ours_only = set(ours) - set(all_manual)
print()
print(f"✅ 两边都有       : {len(both)}")
print(f"📌 手册有、我方无  : {len(manual_only)}")
print(f"❓ 我方有、手册无  : {len(ours_only)}")
print()
print("--- 手册有、我方无：按命名空间 ---")
print("  ", dict(Counter(u.split("/")[0] for u in manual_only)))
print("--- 手册有、我方无：按产品（可多重）---")
prod = Counter()
for u in manual_only:
    for p, _r in all_manual[u]:
        prod[p] += 1
print("  ", dict(prod))
print()
print("--- 手册有、我方无（前 45，标注产品）---")
for u in sorted(manual_only)[:45]:
    prods = "/".join(sorted({p for p, _ in all_manual[u]}))
    name = all_manual[u][0][1]["name"]
    print(f"   {u:38s} [{prods:22s}] {name[:44]}")
print()
print("--- 我方有、手册无：按命名空间 ---")
print("  ", dict(Counter(u.split("/")[0] for u in ours_only)))
print("--- 我方有、手册无（前 30）---")
for u in sorted(ours_only)[:30]:
    print(f"   {u:38s} ({ours[u][0]['key']})  methods={ours[u][0]['methods']}")

out = REPO / ".tmp_analysis" / "manual_index_reconciliation.json"
out.write_text(
    json.dumps(
        {
            "ours_endpoints": len(manifest),
            "ours_uris": len(ours),
            "manual_uris": len(all_manual),
            "both": sorted(both),
            "manual_only": {u: [{"product": p, **r} for p, r in all_manual[u]] for u in sorted(manual_only)},
            "ours_only": {u: [e["key"] for e in ours[u]] for u in sorted(ours_only)},
        },
        ensure_ascii=False,
        indent=1,
    ),
    encoding="utf-8",
)
print()
print(f"wrote {out}")
