"""Endpoint-inventory diff: local registry manifest vs SDK inventories."""
import json
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")

SDK = r"E:\MCP\MMCP\.tmp_nxsdk"
LOCAL = r"E:\MCP\MMCP"


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


man = load(LOCAL + r"\registry\manifest.json")
eps = man["endpoints"]

# ---- local inventory: normalized "NAMESPACE/CODE" tokens ----
def norm_uri(u: str) -> str:
    u = (u or "").strip()
    u = u.lstrip("/")
    return u.upper()


local = {}
for e in eps:
    u = norm_uri(e["uri"])
    if u:
        local.setdefault(u, []).append(e)

print("local manifest endpoints:", len(eps))
print("local distinct URIs:", len(local))
print("counts block:", json.dumps(man.get("counts"), ensure_ascii=False))

# ---- SDK inventories ----
ib = load(SDK + r"\schema\info-baseline.json")["endpoints"]
cov = load(SDK + r"\docs\coverage.json")["endpoints"]
hs = load(SDK + r"\schema\hyper-s-info.json")["endpoints"]

sdk_uri = set()
for k in ib:
    sdk_uri.add(norm_uri(k))
for e in cov:
    sdk_uri.add(norm_uri(e["endpoint"]))
for k in hs:
    sdk_uri.add(norm_uri(k))

print()
print("SDK info-baseline URIs:", len(ib))
print("SDK coverage URIs:", len({norm_uri(e['endpoint']) for e in cov}))
print("SDK union URIs:", len(sdk_uri))

local_set = set(local)
only_local = sorted(local_set - sdk_uri)
only_sdk = sorted(sdk_uri - local_set)

print()
print("=" * 70)
print(f"ONLY IN LOCAL REGISTRY (not in SDK): {len(only_local)}")
for u in only_local:
    e = local[u][0]
    print(f"  {u:60s} ns={e['namespace']:7s} prod={','.join(e['products'])}")
print()
print(f"ONLY IN SDK (not in local registry): {len(only_sdk)}")
for u in only_sdk:
    print("  ", u)

# ---- contracts ----
import glob
import os

cy = sorted(glob.glob(SDK + r"\contracts\endpoints\*.yaml"))
print()
print("contract files:", len(cy))
print("sample names:", [os.path.basename(x) for x in cy[:15]])
