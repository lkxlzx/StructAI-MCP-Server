"""Consolidate every gap finding into machine-readable deliverables under docs/nxsdk_review/."""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
LOCAL = Path(r"E:\MCP\MMCP")
SDK = LOCAL / ".tmp_nxsdk"
OUT = LOCAL / "docs" / "nxsdk_review"
OUT.mkdir(parents=True, exist_ok=True)


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def wcsv(name, rows, cols):
    p = OUT / name
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("; ".join(map(str, r[c])) if isinstance(r.get(c), list) else r.get(c, "")) for c in cols})
    print(f"  wrote {p.name}  ({len(rows)} rows)")


manifest = load(LOCAL / "registry" / "manifest.json")
by_uri = {}
for ep in manifest["endpoints"]:
    by_uri.setdefault(("/" + ep["uri"].strip("/")).upper(), []).append(ep)

summary = {}

# ---------- 1. endpoint inventory diff ----------
def norm(u):
    return u.strip().lstrip("/").upper()


sdk_cov = load(SDK / "docs" / "coverage.json")["endpoints"]
sdk_ib = load(SDK / "schema" / "info-baseline.json")["endpoints"]
sdk_hs = load(SDK / "schema" / "hyper-s-info.json")["endpoints"]
import glob, os
contracts = {}
import yaml
for p in sorted((SDK / "contracts" / "endpoints").glob("*.yaml")):
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    contracts[d["endpoint"].upper()] = d

local_uris = {norm(e["uri"]) for e in manifest["endpoints"] if e["uri"]}
sdk_uris = {norm(k) for k in sdk_ib} | {norm(e["endpoint"]) for e in sdk_cov} | {norm(k) for k in sdk_hs}
only_local = sorted(local_uris - sdk_uris)
only_sdk = sorted(sdk_uris - local_uris)
summary["inventory"] = {
    "local_endpoint_keys": len(manifest["endpoints"]),
    "local_distinct_uris": len(local_uris),
    "sdk_coverage_endpoints": len(sdk_cov),
    "sdk_info_baseline_endpoints": len(sdk_ib),
    "sdk_contracts": len(contracts),
    "sdk_distinct_uris": len(sdk_uris),
    "only_local": len(only_local),
    "only_sdk": len(only_sdk),
}
wcsv("nxsdk_inventory_only_local.csv",
     [{"uri": u, "products": ",".join(by_uri.get("/" + u, [{}])[0].get("products", [])),
       "keys": ",".join(x["key"] for x in by_uri.get("/" + u, [])),
       "reason": "CIVIL_DESIGNER (SDK 不覆盖)" if all("CIVIL_DESIGNER" in x["products"] for x in by_uri.get("/" + u, [{}])) else "SDK 未实现/聚合行"}
      for u in only_local],
     ["uri", "products", "keys", "reason"])
wcsv("nxsdk_inventory_only_sdk.csv", [{"uri": u} for u in only_sdk], ["uri"])

# ---------- 2. product matrix ----------
pm = load(LOCAL / ".tmp_analysis" / "product_matrix_v2.json")
corr = load(LOCAL / "docs" / "nxsdk_review" / "nxsdk_product_corrections.json")["corrections"]
by_key_c = {c["key"]: c for c in corr}
prod_rows = []
for r in pm["tier1"]:
    prod_rows.append({"tier": "A-归属倒置", "route": r["route"], "registry_key": r["key"],
                      "solver": r["solver"],
                      "server_gen_schema": "有" if r["srv_gen"] else "无",
                      "server_civil_schema": "有" if r["srv_civ"] else "无",
                      "registry_gen": "Y" if r["our_gen"] else "",
                      "registry_civil": "Y" if r["our_civ"] else "",
                      "availability": r["availability"], "note": ""})
for tier, key in (("B-我方少声明", "tier2_under"), ("C-我方多声明", "tier2_over")):
    for r in pm[key]:
        prod_rows.append({"tier": tier, "route": r["route"], "registry_key": r["key"],
                          "solver": r["solver"],
                          "server_gen_schema": "有" if r["srv_gen"] else "无",
                          "server_civil_schema": "有" if r["srv_civ"] else "无",
                          "registry_gen": "Y" if r["our_gen"] else "",
                          "registry_civil": "Y" if r["our_civ"] else "",
                          "availability": r["availability"], "note": ""})
# 3 IEHG exceptions + the 8 non-/db contract-based rows come from the corrections file
have = {r["registry_key"] for r in prod_rows}
for c in corr:
    if c["key"] in have:
        continue
    e = next((x for x in manifest["endpoints"] if x["key"] == c["key"]), None)
    prod_rows.append({"tier": {"A": "A-归属倒置", "B": "B-我方少声明", "C": "C-我方多声明"}[c["tier"]],
                      "route": ("/" + e["uri"].strip("/")) if e else "",
                      "registry_key": c["key"], "solver": c.get("solver", ""),
                      "server_gen_schema": "n/a", "server_civil_schema": "n/a",
                      "registry_gen": "Y" if e and "GEN_NX" in e["products"] else "",
                      "registry_civil": "Y" if e and "CIVIL_NX" in e["products"] else "",
                      "availability": c.get("availability", ""),
                      "note": "; ".join(c["evidence"][-1:])})
wcsv("nxsdk_product_disagreements.csv", prod_rows,
     ["tier", "route", "registry_key", "solver", "server_gen_schema", "server_civil_schema",
      "registry_gen", "registry_civil", "availability", "note"])
summary["product"] = {
    "tier_A_hyper_s_inverted": sum(1 for r in prod_rows if r["tier"] == "A-归属倒置"),
    "tier_B_under_declared": sum(1 for r in prod_rows if r["tier"] == "B-我方少声明"),
    "tier_C_over_declared": sum(1 for r in prod_rows if r["tier"] == "C-我方多声明"),
    "total": len(prod_rows),
    "basis": "server /info SCHEMA PRESENCE (not HTTP status)",
}

# ---------- 3. field gaps ----------
fd = load(LOCAL / ".tmp_analysis" / "field_diff_v4.json")
field_rows, type_rows = [], []
for r in fd:
    for f in r["sdk_only"]:
        field_rows.append({"route": r["route"], "product": r["product"], "registry_key": r.get("key", ""),
                           "direction": "server_only", "path": f, "schema": r.get("schema", "")})
    for f in r["local_only"]:
        field_rows.append({"route": r["route"], "product": r["product"], "registry_key": r.get("key", ""),
                           "direction": "local_only", "path": f, "schema": r.get("schema", "")})
    for t in r.get("type_mismatch", []):
        type_rows.append({"route": r["route"], "product": r["product"], "registry_key": r.get("key", ""),
                          "path": t["path"], "ours": t["local"], "server": t["server"],
                          "server_description": t.get("server_desc", ""),
                          "our_description": t.get("local_desc", ""), "schema": r.get("schema", "")})
wcsv("nxsdk_field_gaps.csv", field_rows,
     ["route", "product", "registry_key", "direction", "path", "schema"])
wcsv("nxsdk_type_mismatches.csv", type_rows,
     ["route", "product", "registry_key", "path", "ours", "server", "server_description",
      "our_description", "schema"])
summary["field_diff"] = {
    "pairs_compared": 400,
    "pairs_clean": 400 - len(fd),
    "pairs_diff": sum(1 for r in fd if r["status"] == "DIFF"),
    "pairs_no_local_schema": sum(1 for r in fd if r["status"] == "NO_LOCAL_SCHEMA"),
    "fields_server_only": sum(len(r["sdk_only"]) for r in fd),
    "fields_local_only": sum(len(r["local_only"]) for r in fd),
    "type_mismatches": len(type_rows),
}

# ---------- 4. ledger upgrade candidates ----------
up = load(LOCAL / ".tmp_analysis" / "ledger_upgrade_candidates.json")
wcsv("nxsdk_availability_upgrade.csv", up,
     ["route", "key", "ours", "our_verified_on", "sdk_level", "sdk_date", "sdk_products",
      "sdk_outcome", "sdk_method"])
summary["availability"] = {
    "upgrade_candidates_rows": len(up),
    "upgrade_candidates_distinct_keys": len({u["key"] for u in up}),
    "sdk_ledger_records": 249,
    "sdk_endpoints_with_evidence": 397,
}

json.dump(summary, open(OUT / "nxsdk_gap_summary.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print()
print(json.dumps(summary, ensure_ascii=False, indent=1))
print()
print("summary written to", OUT / "nxsdk_gap_summary.json")
