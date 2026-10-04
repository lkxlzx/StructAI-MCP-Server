# -*- coding: utf-8 -*-
"""按 Registry 逐端点做冒烟测试。

默认 dry-run：只校验 Registry 定义（YAML 可解析、方法集非空、tool_map 合法、schema 文件存在），不发请求。
--live            ：对所有含 GET 的端点发起真实调用，记录结构化结果。
--expect-product  ：声明目标实例的产品，调用前过滤掉不匹配的端点（避免预期内的假失败）。

用法：
    python smoke_test.py                                   # dry-run
    python smoke_test.py --live --base-url ... --expect-product GEN_NX
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REG = os.path.join(HERE, "..", "registry")

try:
    import yaml
except ImportError:  # dry-run 仍可用，只是跳过 YAML 深度校验
    yaml = None


def load_manifest():
    with open(os.path.join(REG, "manifest.json"), encoding="utf-8") as fh:
        return json.load(fh)


def dry_run(mf, product=None):
    """不连 MIDAS 的结构校验。"""
    problems = []
    checked = 0
    for e in mf["endpoints"]:
        if product and product not in e["products"]:
            continue
        checked += 1
        if e.get("enabled") is False:
            continue  # 显式禁用的端点不计入问题
        p = os.path.join(REG, e["definition"].replace("/", os.sep))
        if not os.path.exists(p):
            problems.append(("DEFINITION_MISSING", e["key"], p))
            continue
        if yaml:
            try:
                d = yaml.safe_load(open(p, encoding="utf-8"))
            except Exception as ex:  # noqa: BLE001
                problems.append(("YAML_INVALID", e["key"], str(ex)))
                continue
            for f in ("key", "uri", "tool_map", "execution", "products"):
                if not d.get(f):
                    problems.append(("FIELD_EMPTY", e["key"], f))
            if not d.get("methods"):
                if d.get("methods_unknown"):
                    problems.append(("METHODS_UNKNOWN", e["key"],
                                     "源手册未标注方法，已标记 methods_unknown"))
                else:
                    problems.append(("NO_METHOD", e["key"], ""))
            if not d.get("wrapper"):
                problems.append(("WRAPPER_MISSING", e["key"], ""))
            if not str(d.get("uri", "")).startswith("/"):
                problems.append(("URI_NO_SLASH", e["key"], d.get("uri")))
        if e["schema"] and not os.path.exists(os.path.join(REG, e["schema"].replace("/", os.sep))):
            problems.append(("SCHEMA_MISSING", e["key"], e["schema"]))
    return checked, problems


def parse_methods(raw):
    """manifest 的 methods 多为逗号串（少数用 '/' 分隔）；YAML 定义里是 list。"""
    if not raw:
        return []
    if isinstance(raw, str):
        return [m.upper() for m in re.split(r"[,/\s]+", raw) if m.strip()]
    return [str(m).strip().upper() for m in raw if str(m).strip()]


def live_run(mf, base_url, mapi_key, product=None, expect_product=None, only_get=True):
    """真实调用（默认只调 GET，不改模型）。"""
    sys.path.insert(0, HERE)
    from midas_client import MidasClient, MidasError, classify_response
    c = MidasClient(base_url=base_url, mapi_key=mapi_key)
    results = []
    skipped_by_product = collections.Counter()
    skipped_disabled = []
    for e in mf["endpoints"]:
        if e.get("enabled") is False:
            skipped_disabled.append(e["key"])
            continue
        if product and product not in e["products"]:
            continue
        if expect_product and expect_product not in e["products"]:
            skipped_by_product["|".join(e["products"])] += 1
            continue
        if only_get and "GET" not in parse_methods(e["methods"]):
            continue
        try:
            r = c.call(e["key"], "GET", product=product)
            st, _code, detail = classify_response(e["key"], r)
            results.append([e["key"], st, detail])
        except MidasError as ex:
            results.append([e["key"], ex.code, ex.message[:120]])
        except Exception as ex:  # noqa: BLE001
            results.append([e["key"], "EXCEPTION", str(ex)[:120]])
    return results, dict(skipped_by_product), skipped_disabled, c.profile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="真实调用 MIDAS")
    ap.add_argument("--base-url", default=os.environ.get("MIDAS_BASE_URL", ""))
    ap.add_argument("--mapi-key", default=os.environ.get("MIDAS_MAPI_KEY", ""))
    ap.add_argument("--product", default="",
                    choices=["", "GEN_NX", "CIVIL_NX", "CIVIL_DESIGNER"])
    ap.add_argument("--expect-product", default="ANY",
                    choices=["ANY", "GEN_NX", "CIVIL_NX", "CIVIL_DESIGNER"],
                    help="声明目标实例的产品；非 ANY 时跳过不匹配的端点，避免预期内假失败")
    ap.add_argument("--all-methods", action="store_true",
                    help="live 时也调用非 GET 端点（会修改模型，危险）")
    ap.add_argument("--out", default="smoke_report.json")
    a = ap.parse_args()

    mf = load_manifest()
    print(f"registry keys: {mf['counts']['keys']} | schemas: {mf['counts']['schemas']}")

    checked, problems = dry_run(mf, a.product or None)
    print(f"dry-run: 校验 {checked} 个端点, 发现 {len(problems)} 个问题")
    for p in problems[:25]:
        print("   ", p)

    report = {"registry": {"keys": mf["counts"]["keys"], "schemas": mf["counts"]["schemas"]},
              "dry_run": {"checked": checked, "problem_count": len(problems),
                          "problems": problems}}

    rc = 0
    if a.live:
        if not a.base_url or not a.mapi_key:
            print("!! --live 需要 --base-url 与 --mapi-key（或环境变量 "
                  "MIDAS_BASE_URL / MIDAS_MAPI_KEY）")
            return 2
        expect = None if a.expect_product == "ANY" else a.expect_product
        res, skipped, disabled, profile = live_run(
            mf, a.base_url, a.mapi_key, a.product or None, expect,
            only_get=not a.all_methods)
        cnt = collections.Counter(r[1] for r in res)
        print(f"live: 调用 {len(res)} 次 -> {dict(cnt)}")
        print(f"      profile={profile} | 按产品跳过 {sum(skipped.values())} 个 "
              f"| 禁用跳过 {len(disabled)} 个")
        for r in res:
            if r[1] not in ("OK", "OK_EMPTY"):
                print("   ", r)
        report["live"] = {"base_url": a.base_url, "product": a.product,
                          "expected_product": a.expect_product, "profile": profile,
                          "calls": len(res), "summary": dict(cnt), "results": res,
                          "skipped_by_product": skipped, "skipped_disabled": disabled}
        routed = cnt.get("OK", 0) + cnt.get("OK_EMPTY", 0)
        rc = 0 if routed == len(res) else 1

    with open(os.path.join(HERE, a.out), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print("report ->", a.out)
    return rc


if __name__ == "__main__":
    sys.exit(main())
