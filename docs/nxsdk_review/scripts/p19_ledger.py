"""Compare SDK verification ledger (live evidence) against our registry availability."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")
LOCAL = Path(r"E:\MCP\MMCP")
SDK = LOCAL / ".tmp_nxsdk"


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


led = yaml.safe_load((SDK / "contracts" / "verification" / "ledger.yaml").read_text(encoding="utf-8"))
recs = led["records"]

# resolve best level + dates per endpoint
best = {}
for r in recs:
    for e in r.get("endpoints", []):
        k = e.upper()
        cur = best.get(k)
        lvl = r.get("level")
        rank = {"read": 1, "write": 2}.get(lvl, 0)
        if cur is None or rank > cur["rank"]:
            best[k] = dict(rank=rank, level=lvl, date=r.get("date"),
                           products=r.get("products"), outcome=r.get("outcome"),
                           method=r.get("method"), nx=r.get("nxVersions"))
print(f"ledger records: {len(recs)}")
print(f"endpoints with live evidence: {len(best)}")
print("level distribution:", Counter(v["level"] for v in best.values()))
print("latest evidence date:", max(v["date"] for v in best.values() if v.get("date")))
print()

manifest = load(LOCAL / "registry" / "manifest.json")
by_uri = {}
for ep in manifest["endpoints"]:
    by_uri.setdefault(("/" + ep["uri"].strip("/")).upper(), []).append(ep)

print("=" * 100)
print("Our availability status vs SDK live-evidence level")
print("=" * 100)
cross = Counter()
upgrade = []
for route, v in sorted(best.items()):
    ours = by_uri.get(route)
    if not ours:
        cross[("NOT_IN_REGISTRY", v["level"])] += 1
        continue
    for ep in ours:
        cross[(ep["availability"], v["level"])] += 1
        if ep["availability"] in ("untested", "unverified") and v["level"] in ("read", "write"):
            upgrade.append(dict(route=route, key=ep["key"], ours=ep["availability"],
                                our_verified_on=ep["verified_on"], sdk_level=v["level"],
                                sdk_date=v["date"], sdk_products=v["products"],
                                sdk_outcome=v["outcome"], sdk_method=v["method"]))
for k, n in sorted(cross.items()):
    print(f"  ours={k[0]:12s} sdk_evidence={k[1]:6s} n={n}")

print()
print("=" * 100)
print(f"UPGRADE CANDIDATES — we say untested/unverified, SDK has live evidence: {len(upgrade)}")
print("=" * 100)
seen = set()
for u in sorted(upgrade, key=lambda x: (x["ours"], x["route"])):
    if u["key"] in seen:
        continue
    seen.add(u["key"])
    print(f"  {u['route']:34s} {u['key']:34s} ours={u['ours']:10s} sdk={u['sdk_level']:5s} {u['sdk_date']} {u['sdk_products']} outcome={u['sdk_outcome']}")
print(f"  distinct keys: {len(seen)}")

json.dump(upgrade, open(LOCAL / ".tmp_analysis" / "ledger_upgrade_candidates.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print()
print("wrote ledger_upgrade_candidates.json")
