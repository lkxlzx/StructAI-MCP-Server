#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 **外部证据**（Dennis5882/MIDAS-API-NX-SDK）导入 registry 的 `products` 字段。

背景
----
`docs/nxsdk_review/00_评估与查漏补缺报告_v1.0.md` 记录了与外部 SDK 的逐端点、逐字段比对结果。
其中「产品归属分歧」共 **53** 条，分三级：

    tier A（21 条）Hyper-S `-M1` 族 `products` 归属倒置：我方 [GEN_NX]，证据指向 [CIVIL_NX]
    tier B（20 条）我方少声明 CIVIL_NX（服务端 /info 或对方契约含 civil）
    tier C（12 条）我方多声明 CIVIL_NX（服务端 /info 404 或对方契约不含 civil）

**证据强度**：tier A 有三条独立证据同向（`instances.yaml` 自述 gen-local 缺 21 个 Hyper-S 变体；
服务端 `GET /info` gen=404 / civil=200；对方 `docs/CLAUDE.md` 明载 Hyper-S 是 Civil NX 专属，
并在 `db/base.py` 设 `HYPER_S_ONLY`）。tier B / C 依赖产品族级声明，**须先在我方实例上复测路由**。

设计约束（沿用本目录既有工具口径）
----------------------------------
* **默认只预演**，`--write` 才落盘；改动逐条打印，便于人工复核。
* **幂等**：重复运行不产生新差异。
* **只改 YAML 定义文件**的 `products` 行，不碰 manifest —— manifest 是派生索引，
  落盘后须自行运行 `python registry/tools/sync_manifest.py --write`。
* **不动** `availability` / `verified_on` / `unavailable_on` / `enabled`（与 P136a 口径一致）。
* **不臆造**：只消费证据文件里已列出的条目。

用法（仓库根目录执行）
----------------------
    # 预演（默认只处理 tier A，即证据最硬的一级）
    python registry/tools/import_nxsdk_evidence.py

    # 看 tier A + B + C 的全部差异
    python registry/tools/import_nxsdk_evidence.py --tier all

    # 落盘 tier A
    python registry/tools/import_nxsdk_evidence.py --tier A --write

    # 断言：指定 tier 已无待处理差异（CI 用）
    python registry/tools/import_nxsdk_evidence.py --tier A --check

    # 指定另一份证据文件
    python registry/tools/import_nxsdk_evidence.py --evidence path/to/evidence.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

DEFAULT_EVIDENCE = "docs/nxsdk_review/nxsdk_product_corrections.json"

# 顶层 `products: [A, B]`（flow 形式）
FLOW_RE = re.compile(r"^(products:[ \t]*)(\[[^\]]*\])([ \t]*)$", re.MULTILINE)


def render_flow(values: list[str]) -> str:
    return "[" + ", ".join(values) + "]"


def parse_flow(text: str) -> list[str]:
    inner = text.strip()[1:-1].strip()
    if not inner:
        return []
    return [x.strip().strip("'\"") for x in inner.split(",") if x.strip()]


def _read_text_preserving(path: pathlib.Path) -> str:
    """按原样读取（**不**做 universal-newline 转换）—— 保留 CRLF，避免整文件 diff。"""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _write_text_preserving(path: pathlib.Path, text: str) -> None:
    """按原样写回（**不**做换行转换）—— 与 `_read_text_preserving` 配对。"""
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def read_products(text: str):
    """Return (kind, payload) where kind is 'flow' | 'block' | None."""
    m = FLOW_RE.search(text)
    if m:
        return "flow", (m, parse_flow(m.group(2)))
    bm = re.search(r"^products:[ \t]*\r?\n((?:[ \t]*-[ \t]*[^\r\n]*\r?\n)+)", text, re.MULTILINE)
    if bm:
        vals = [ln.strip()[1:].strip().strip("'\"")
                for ln in bm.group(1).splitlines() if ln.strip().startswith("-")]
        return "block", (bm, vals)
    return None, None


def set_products(text: str, new_values: list[str]) -> str:
    kind, payload = read_products(text)
    if kind == "flow":
        m, _ = payload
        return text[:m.start(2)] + render_flow(new_values) + text[m.end(2):]
    if kind == "block":
        bm, _ = payload
        eol = "\r\n" if "\r\n" in text else "\n"
        lines = "".join(f"  - {v}{eol}" for v in new_values)
        return text[:bm.start()] + f"products:{eol}" + lines + text[bm.end():]
    raise ValueError("no top-level `products:` key found")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="仓库根目录（默认当前目录）")
    ap.add_argument("--evidence", default=None, help=f"证据文件（默认 {DEFAULT_EVIDENCE}）")
    ap.add_argument("--tier", default="A", choices=["A", "B", "C", "all"],
                    help="处理哪一级（默认 A：证据最硬）")
    ap.add_argument("--write", action="store_true", help="实际写回（默认只预演）")
    ap.add_argument("--check", action="store_true",
                    help="断言已无待处理差异；有则退出码 1（CI 用）")
    args = ap.parse_args()

    repo = pathlib.Path(args.repo).resolve()
    ev_path = repo / (args.evidence or DEFAULT_EVIDENCE)
    if not ev_path.exists():
        print(f"⚠️ 证据文件不存在: {ev_path}", file=sys.stderr)
        print("   先运行 .tmp_analysis/p25_evidence.py 生成，或用 --evidence 指定。", file=sys.stderr)
        return 2

    ev = json.loads(ev_path.read_text(encoding="utf-8"))
    tiers = {"A", "B", "C"} if args.tier == "all" else {args.tier}
    todo = [c for c in ev["corrections"] if c["tier"] in tiers]

    print(f"证据文件: {ev_path.relative_to(repo)}")
    print(f"来源    : {ev.get('source', '?')}")
    print(f"tier    : {args.tier}（{len(todo)} 条候选，总 {len(ev['corrections'])} 条）")
    print("-" * 92)

    pending, applied, skipped = [], [], []
    for c in todo:
        p = repo / "registry" / c["definition"]
        if not p.exists():
            skipped.append((c["key"], f"定义文件不存在: {c['definition']}"))
            continue
        text = _read_text_preserving(p)
        kind, payload = read_products(text)
        if kind is None:
            skipped.append((c["key"], "未找到顶层 products: 键"))
            continue
        current = payload[1]
        target = c["to"]
        if current == target:
            continue  # 幂等：已一致
        if current != c["from"]:
            skipped.append((c["key"], f"当前值 {current} 与证据 from {c['from']} 不符（可能已被改过）"))
            continue
        new_text = set_products(text, target)
        pending.append((c, p, new_text))
        print(f"  {c['key']}")
        print(f"      tier {c['tier']}  products: {current} -> {target}")
        print(f"      {c['definition']}")
        if c.get("solver"):
            print(f"      solver={c['solver']}  availability={c['availability']}  "
                  f"unavailable_on={c['unavailable_on']}")

    print("-" * 92)
    print(f"待写入 {len(pending)} 条 · 已一致（幂等跳过） {len(todo) - len(pending) - len(skipped)} 条 · "
          f"跳过 {len(skipped)} 条")
    if skipped:
        print("\n跳过的条目：")
        for key, why in skipped:
            print(f"  {key}: {why}")

    if args.check:
        if pending:
            print(f"\n❌ --check 失败：tier {args.tier} 仍有 {len(pending)} 条未处理。", file=sys.stderr)
            return 1
        print(f"\n✅ --check 通过：tier {args.tier} 无待处理差异。")
        return 0

    if not args.write:
        print("\n（预演模式；加 --write 才会写回 YAML）")
        print("  落盘后请运行： python registry/tools/sync_manifest.py --write")
        return 0

    if not pending:
        print("\n无差异，未写入。")
        return 0

    for c, p, new_text in pending:
        _write_text_preserving(p, new_text)
    print(f"\nWROTE {len(pending)} 个 YAML 定义文件。")
    print("下一步： python registry/tools/sync_manifest.py --write")
    return 0


if __name__ == "__main__":
    # Windows 控制台默认 cp949/cp936：本工具会打印中文/符号，不重设编码会 UnicodeEncodeError。
    # ⚠️ 必须在 `__main__` 块内：测试用 `exec_module()` 装载本模块，模块级调用会改写
    #    **pytest 的捕获流**，破坏其后所有用例的 capture。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
