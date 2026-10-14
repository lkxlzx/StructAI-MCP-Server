"""量化机会：把手册文章声明的 URI 与我方 registry 的 636 端点对一遍。"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
MANUAL = Path(r"E:\MCP\MIDAS-API-Online-Manual")

manifest = json.loads((REPO / "registry" / "manifest.json").read_text(encoding="utf-8"))["endpoints"]
ours_uri = {str(e["uri"]).lstrip("/").upper(): e["key"] for e in manifest}
print(f"我方端点 {len(manifest)} · 不同 URI {len(ours_uri)}")

# 手册：抽出每篇文章声明的 End Point / Input URI
pattern = re.compile(
    r"(?:End Point|Input URI)\**\s*[:：]?\s*\|?\s*\**\s*\{?base url\}?\s*\+?\s*`?/?([A-Za-z0-9_\-/\.]+)",
    re.IGNORECASE,
)
found: dict[str, list[str]] = {}
files = list((MANUAL / "en").rglob("*.md")) + list((MANUAL / "zh").rglob("*.md"))
for path in files:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        continue
    for match in pattern.finditer(text):
        uri = match.group(1).strip().strip("`").lstrip("/").upper()
        if uri and len(uri) > 1:
            found.setdefault(uri, []).append(str(path.relative_to(MANUAL)))
print(f"手册 md 文件 {len(files)} 篇 · 声明出的不同 URI {len(found)}")

manual_uris = set(found)
ours_set = set(ours_uri)
both = manual_uris & ours_set
manual_only = manual_uris - ours_set
ours_only = ours_set - manual_uris

print()
print(f"✅ 两边都有      : {len(both)}")
print(f"📌 手册有、我方无 : {len(manual_only)}")
print(f"❓ 我方有、手册无 : {len(ours_only)}")
print()
print("--- 手册有、我方无（前 40，按命名空间）---")
for uri in sorted(manual_only)[:40]:
    print(f"   {uri:44s} ← {found[uri][0]}")
print()
print("--- 我方有、手册无（前 25）---")
for uri in sorted(ours_only)[:25]:
    print(f"   {uri:44s} ({ours_uri[uri]})")
print()
print("--- 命名空间分布 ---")
print("  手册独有:", dict(Counter(u.split('/')[0] for u in manual_only)))
print("  我方独有:", dict(Counter(u.split('/')[0] for u in ours_only)))
