"""Probe the SDK repo's core data files."""
import json
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

SDK = r"E:\MCP\MMCP\.tmp_nxsdk"


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


ib = load(SDK + r"\schema\info-baseline.json")
print("=== info-baseline.json ===")
print("comment:", ib["$comment"][:700])
print("capturedAt:", ib["capturedAt"])
print("method:", ib["method"][:400])
print("nxVersions:", json.dumps(ib["nxVersions"], ensure_ascii=False)[:500])
print("coverage:", json.dumps(ib["coverage"], ensure_ascii=False, indent=1)[:1200])
eps = ib["endpoints"]
print("endpoint count:", len(eps))
print("sample entry /db/NODE:")
print(json.dumps(eps.get("/db/NODE"), ensure_ascii=False, indent=1)[:2000])
# structure of one entry
k0 = next(iter(eps))
print("entry keys:", list(eps[k0].keys()))

cov = load(SDK + r"\docs\coverage.json")
print()
print("=== coverage.json ===")
print("vendored_from:", cov["vendored_from"])
print("vendored_at_commit:", cov["vendored_at_commit"])
print("source_note:", str(cov["source_note"])[:400])
ce = cov["endpoints"]
print("count:", len(ce))
print("keys:", list(ce[0].keys()))
print("status:", Counter(e.get("status") for e in ce))
print("products:", Counter(p for e in ce for p in e.get("products", [])))
print("chapter:", Counter(e.get("chapter_file") for e in ce))
