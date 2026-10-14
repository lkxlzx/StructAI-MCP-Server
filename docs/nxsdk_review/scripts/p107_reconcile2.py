"""更稳的索引抽取：容忍 代码列缺省（`—`）、URL 前导 `/`、方法列多种写法。"""
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
HEADER = re.compile(r"^\|\s*#\s*\|\s*接口代码\s*\|\s*接口名称\s*\|\s*URL\s*\|\s*方法\s*\|")
ROW = re.compile(
    r"^\|\s*(?P<n>\d+)\s*\|\s*(?:`(?P<code>[^`]*)`|(?P<dash>[—\-–]+))\s*\|"
    # ⚠️ 名称列**可能自带方括号**（如 `[新项目[NEW]New Project](#…)`）⇒ 非贪婪匹配到 `](#`
    r"\s*\[(?P<name>.+?)\]\(#[^)]*\)\s*\|"
    r"\s*`?(?P<url>[^`|]+?)`?\s*\|\s*(?P<methods>[^|]+?)\s*\|"
)


def extract(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    rows: list[dict] = []
    for i, line in enumerate(lines):
        if not HEADER.match(line):
            continue
        for follow in lines[i + 2 :]:
            m = ROW.match(follow)
            if m:
                url = m.group("url").strip().strip("/")
                name = m.group("name").strip()
                # ⚠️ 若干行（章节 =「英文数据手册（未编入索引）」）的 **URL 列是 `—`**，
                # 真正的 URI 写在**名称列**里（形如 `DESIGN/RC/KDS-41-20-2022/SDGN : 名称`）⇒ 从这里回捞。
                if not url or url in {"—", "-", "–"}:
                    guess = re.match(r"^([A-Za-z][A-Za-z0-9_\-]*(?:/[A-Za-z0-9_\-.]+)+)\s*:", name)
                    url = guess.group(1).strip("/") if guess else ""
                rows.append(
                    {
                        "code": (m.group("code") or "").strip(),
                        "name": name,
                        "url": url,
                        "methods": " ".join(m.group("methods").split()),
                    }
                )
            elif follow.startswith("|") and re.match(r"^\|\s*\d+\s*\|", follow):
                rows.append({"code": "", "name": "", "url": "", "methods": "", "raw": follow[:120]})
            elif rows and not follow.startswith("|"):
                break
    return rows


manifest = json.loads((REPO / "registry" / "manifest.json").read_text(encoding="utf-8"))["endpoints"]
ours: dict[str, list[dict]] = {}
for e in manifest:
    ours.setdefault(str(e["uri"]).strip("/").upper(), []).append(e)

all_manual: dict[str, list[tuple[str, dict]]] = {}
for product, filename in MANUALS:
    rows = extract(DOCS / filename)
    bad = [r for r in rows if not r.get("url")]
    print(f"{product:14s} 索引 {len(rows):>4} 条（解析失败 {len(bad)}）")
    for r in rows:
        if r.get("url"):
            all_manual.setdefault(r["url"].upper(), []).append((product, r))
print()
print(f"三本手册合计不同 URL: {len(all_manual)}")

both = set(all_manual) & set(ours)
manual_only = set(all_manual) - set(ours)
ours_only = set(ours) - set(all_manual)
print()
print(f"我方 registry: {len(manifest)} 端点 / {len(ours)} URI")
print(f"✅ 两边都有       : {len(both)}")
print(f"📌 手册有、我方无  : {len(manual_only)}")
print(f"❓ 我方有、手册无  : {len(ours_only)}")
print()
print("--- 手册有、我方无：按产品 ---")
prod = Counter()
for u in manual_only:
    for p, _r in all_manual[u]:
        prod[p] += 1
print("  ", dict(prod))
print("--- 手册有、我方无：按命名空间 ---")
print("  ", dict(Counter(u.split("/")[0] for u in manual_only)))
print()
print("--- 手册有、我方无（全部，标注产品）---")
for u in sorted(manual_only):
    prods = "/".join(sorted({p for p, _ in all_manual[u]}))
    print(f"   {u:40s} [{prods:22s}] {all_manual[u][0][1]['name'][:46]}")
print()
print("--- 我方有、手册无：按命名空间 ---")
print("  ", dict(Counter(u.split("/")[0] for u in ours_only)))
print("  样例（前 20）:")
for u in sorted(ours_only)[:20]:
    print(f"   {u:40s} ({ours[u][0]['key']})")

(REPO / ".tmp_analysis" / "manual_index_reconciliation.json").write_text(
    json.dumps(
        {
            "ours_endpoints": len(manifest),
            "ours_uris": len(ours),
            "manual_uris": len(all_manual),
            "counts": {"both": len(both), "manual_only": len(manual_only), "ours_only": len(ours_only)},
            "manual_only": {u: [{"product": p, **r} for p, r in all_manual[u]] for u in sorted(manual_only)},
            "ours_only": {u: [e["key"] for e in ours[u]] for u in sorted(ours_only)},
        },
        ensure_ascii=False,
        indent=1,
    ),
    encoding="utf-8",
)
print("\nwrote .tmp_analysis/manual_index_reconciliation.json")
