"""Contract-level diff: SDK contracts (fields/requirement/risk) + verification ledger vs our registry."""
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


# ---- SDK contracts ----
cfiles = sorted((SDK / "contracts" / "endpoints").glob("*.yaml"))
contracts = {}
for p in cfiles:
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    contracts[d["endpoint"].upper()] = d

print(f"SDK contracts: {len(contracts)}")
k0 = next(iter(contracts.values()))
print("contract top-level keys:", list(k0.keys()))
print()
print("sample contract (db-node) keys of interest:")
n = contracts.get("/DB/NODE")
for k in ("id", "endpoint", "name", "products", "recordKey", "source", "surface",
          "fields", "requestFields", "risk", "mitigation", "normalize_defaults", "extraction"):
    if k in n:
        v = n[k]
        print(f"  {k}: {json.dumps(v, ensure_ascii=False, default=str)[:300]}")

# ---- field/requirement stats across contracts ----
print()
print("=" * 80)
print("contract field-level metadata availability")
print("=" * 80)
has_fields = sum(1 for c in contracts.values() if c.get("fields") or c.get("requestFields"))
print("contracts with fields/requestFields:", has_fields, "/", len(contracts))
keyc = Counter()
for c in contracts.values():
    for k in c:
        keyc[k] += 1
print("top-level key frequency:", dict(keyc.most_common()))

# ---- SDK products per endpoint vs ours ----
manifest = load(LOCAL / "registry" / "manifest.json")
by_uri = {}
for ep in manifest["endpoints"]:
    by_uri.setdefault(("/" + ep["uri"].strip("/")).upper(), []).append(ep)

PROD = {"gen": "GEN_NX", "civil": "CIVIL_NX"}
print()
print("=" * 80)
print("contract `products` vs registry `products` (disagreements)")
print("=" * 80)
dis = []
for route, c in sorted(contracts.items()):
    sdk_p = {PROD[p] for p in c.get("products", []) if p in PROD}
    ours = by_uri.get(route, [])
    if not ours:
        dis.append((route, sorted(sdk_p), None, "NOT_IN_REGISTRY"))
        continue
    our_p = set()
    for x in ours:
        our_p |= {p for p in x["products"] if p in ("GEN_NX", "CIVIL_NX")}
    if sdk_p and our_p and sdk_p != our_p:
        dis.append((route, sorted(sdk_p), sorted(our_p), "MISMATCH"))
print(f"disagreements: {len(dis)}")
for route, s, o, kind in dis:
    print(f"  {route:34s} sdk={str(s):26s} ours={str(o):26s} {kind}")

# ---- verification ledger ----
print()
print("=" * 80)
print("verification ledger")
print("=" * 80)
led = SDK / "contracts" / "verification" / "ledger.yaml"
print("exists:", led.exists())
if led.exists():
    d = yaml.safe_load(led.read_text(encoding="utf-8"))
    print("top keys:", list(d) if isinstance(d, dict) else type(d))
    recs = d.get("sessions") or d.get("records") or d
    if isinstance(recs, list):
        print("records:", len(recs))
        print("record keys:", list(recs[0].keys()))
        print("sample:", json.dumps(recs[0], ensure_ascii=False, default=str)[:700])
        lvl = Counter()
        eps = set()
        for r in recs:
            lvl[r.get("level")] += 1
            for e in (r.get("endpoints") or []):
                eps.add(e if isinstance(e, str) else str(e))
        print("levels:", dict(lvl))
        print("distinct endpoints covered:", len(eps))
        print("sample endpoints:", sorted(eps)[:20])
