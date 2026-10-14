"""Hyper-S (-M1) attribution audit + solver vs products consistency across the registry."""
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
eps = manifest["endpoints"]

print("=" * 96)
print("A) solver x products cross-tab (manifest)")
print("=" * 96)
ct = Counter((e["solver"] or "(none)", tuple(sorted(e["products"]))) for e in eps)
for (solver, prods), n in sorted(ct.items(), key=lambda x: (-x[1], x[0])):
    print(f"  solver={solver:12s} products={str(list(prods)):45s} n={n}")

print()
print("=" * 96)
print("B) every -M1 endpoint in our registry")
print("=" * 96)
m1 = [e for e in eps if e["uri"].upper().endswith("-M1")]
print(f"count: {len(m1)}")
print(f"{'key':24s} {'products':30s} {'solver':10s} {'avail':11s} {'verified_on':22s} {'schema_source'}")
for e in sorted(m1, key=lambda x: x["key"]):
    print(f"  {e['key']:24s} {','.join(e['products']):30s} {(e['solver'] or '-'):10s} {e['availability']:11s} {','.join(e['verified_on']):22s} {e['schema_source']}")

print()
print("=" * 96)
print("C) SDK: which endpoints does the SDK declare as Hyper-S / civil-only?")
print("=" * 96)
hs = load(LOCAL / ".tmp_nxsdk" / "schema" / "hyper-s-info.json")
print("hyper-s-info endpoints:", list(hs["endpoints"]))
print("product:", hs["product"], "| capturedAt:", hs["capturedAt"])
print("method:", hs["method"])
print()
cov = load(LOCAL / ".tmp_nxsdk" / "docs" / "coverage.json")["endpoints"]
m1sdk = [e for e in cov if e["endpoint"].upper().endswith("-M1")]
print(f"SDK coverage -M1 endpoints: {len(m1sdk)}")
for e in sorted(m1sdk, key=lambda x: x["endpoint"]):
    print(f"  {e['endpoint']:26s} products={e['products']}  name={e['name'][:40]}")
print()
print("SDK -M1 endpoints declaring GEN in products (should be none if Hyper-S is civil-only):")
for e in m1sdk:
    if "gen" in e["products"]:
        print("   !!", e["endpoint"], e["products"])
print("   (none above = consistent with 'Hyper-S is Civil NX only')")
