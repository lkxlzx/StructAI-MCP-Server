#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用端点 YAML 定义重建 registry/manifest.json 的派生字段。

背景（重要）：
    原生成器把 `wrapper.read_root` **从 URI 末段猜出来**
    （`e["uri"].split("/")[-1].upper()`），既不是手册 Response 示例、也不是实测值。
    实测证明它错了至少 8 处（见 docs/07 §6.12 与 §16 R14）。
    因此**端点 YAML 定义文件是唯一真源**，manifest.json 只是派生索引。

本工具只更新「YAML 里存在的字段」，不改动 definition / schema / schema_source 与条目顺序。
改动会被逐条打印，便于人工复核。

用法（仓库根目录执行）：
    python registry/tools/sync_manifest.py            # 预演，只打印差异
    python registry/tools/sync_manifest.py --write    # 实际写回
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import yaml

# 从 YAML 覆盖到 manifest 的字段（manifest 字段名 -> YAML 字段名）
SIMPLE_FIELDS = {
    "products": "products",
    "availability": "availability",
    "verified_on": "verified_on",
    "unavailable_on": "unavailable_on",
    "enabled": "enabled",
    "disable_reason": "disable_reason",
    "table_type": "table_type",
    "path_key_supported": "path_key_supported",
    "solver": "solver",
    "params_ref": "params_ref",
    "title": "title",
    "title_zh": "title_zh",
    "title_zh_official": "title_zh_official",
}


def norm(v):
    """把 YAML 值规整成 manifest 的表示。"""
    if v is None:
        return ""
    return v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--write", action="store_true", help="实际写回（默认只预演）")
    args = ap.parse_args()

    repo = pathlib.Path(args.repo).resolve()
    reg = repo / "registry"
    man_path = reg / "manifest.json"
    man = json.loads(man_path.read_text(encoding="utf-8"))

    changed: list[tuple[str, str, object, object]] = []
    missing_yaml: list[str] = []

    for e in man["endpoints"]:
        defrel = e.get("definition")
        if not defrel:
            continue
        p = reg / defrel
        if not p.exists():
            missing_yaml.append(e["key"])
            continue
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

        # methods：YAML 是列表，manifest 是 ", " 连接的字符串
        if isinstance(d.get("methods"), list):
            new_m = ", ".join(str(x).strip() for x in d["methods"] if str(x).strip())
            if e.get("methods") != new_m:
                changed.append((e["key"], "methods", e.get("methods"), new_m))
                e["methods"] = new_m

        for mkey, ykey in SIMPLE_FIELDS.items():
            if ykey not in d:
                continue
            new_v = norm(d[ykey])
            old_v = e.get(mkey)
            if old_v != new_v:
                changed.append((e["key"], mkey, old_v, new_v))
                e[mkey] = new_v

        # wrapper：只取 YAML 显式声明的 write / read_root，不推断
        w = d.get("wrapper")
        if isinstance(w, dict):
            new_w = dict(e.get("wrapper") or {})
            for k in ("write", "read_root"):
                if k in w and new_w.get(k) != w[k]:
                    changed.append((e["key"], f"wrapper.{k}", new_w.get(k), w[k]))
                    new_w[k] = w[k]
            e["wrapper"] = new_w

        # risk：整块替换
        if isinstance(d.get("risk"), dict) and e.get("risk") != d["risk"]:
            changed.append((e["key"], "risk", e.get("risk"), d["risk"]))
            e["risk"] = d["risk"]

        # execution.mode -> execution_mode
        ex = d.get("execution")
        if isinstance(ex, dict) and "mode" in ex and e.get("execution_mode") != ex["mode"]:
            changed.append((e["key"], "execution_mode", e.get("execution_mode"), ex["mode"]))
            e["execution_mode"] = ex["mode"]

        # product_overrides
        if "product_overrides" in d and e.get("product_overrides") != d["product_overrides"]:
            changed.append((e["key"], "product_overrides",
                            e.get("product_overrides"), d["product_overrides"]))
            e["product_overrides"] = d["product_overrides"]

        # stats
        st = d.get("stats")
        if isinstance(st, dict):
            for mk, yk in (("spec_rows", "spec_rows"), ("examples", "examples")):
                if yk in st and e.get(mk) != st[yk]:
                    changed.append((e["key"], mk, e.get(mk), st[yk]))
                    e[mk] = st[yk]

        # source.provenance
        src = d.get("source")
        if isinstance(src, dict) and "provenance" in src:
            if e.get("provenance") != src["provenance"]:
                changed.append((e["key"], "provenance", e.get("provenance"), src["provenance"]))
                e["provenance"] = src["provenance"]

        # schema_ref.local / source（manifest 的 schema / schema_source）
        sr = d.get("schema_ref")
        if isinstance(sr, dict):
            if sr.get("local") and e.get("schema") != sr["local"]:
                changed.append((e["key"], "schema", e.get("schema"), sr["local"]))
                e["schema"] = sr["local"]
            if sr.get("source") and e.get("schema_source") != sr["source"]:
                changed.append((e["key"], "schema_source", e.get("schema_source"), sr["source"]))
                e["schema_source"] = sr["source"]

    print(f"manifest 条目数 = {len(man['endpoints'])}")
    if missing_yaml:
        print(f"⚠️ 找不到 YAML 的条目 {len(missing_yaml)}: {missing_yaml[:10]}")
    print(f"字段差异总数 = {len(changed)}")
    if changed:
        print("-" * 90)
        for key, field, old, new in changed:
            print(f"  {key}")
            print(f"      {field}: {old!r} -> {new!r}")

    if args.write:
        if not changed:
            print("无差异，未写入。")
            return 0
        man_path.write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8", newline="\n")
        print(f"\nWROTE {man_path}（{len(changed)} 处字段更新）")
    else:
        print("\n（预演模式；加 --write 才会写回）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
