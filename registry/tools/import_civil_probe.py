#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 **CIVIL_NX 产品级只读路由探针**（`registry/live/civil_product_probe.json`）的结论收进端点定义。

为什么需要这个工具
------------------
`registry/README.md` §8.2 的既定口径是「**按实测**收口 `products`」。此前 CIVIL_NX 侧只有
**云实例**可用，且我方对 21 条候选**从未实测过**（`verified_on` 只含 `gen-local`），
故这批「我方少声明 `CIVIL_NX`」的条目一直**未落地**（见 §8.15 的 B 级）。

本工具消费那份探针证据（**只发 GET**、零副作用、含三组对照自检），按同一口径落地：

| 探针结论 | 动作 |
| --- | --- |
| `200`（路由**在** CIVIL_NX 上） | `products` 并上 `CIVIL_NX` · `verified_on` 并上 `civil-cloud` · `availability: → verified` |
| 非 `200`（路由**不在**） | **不**动 `products`；`unavailable_on` 并上 `civil-cloud`（如实记录实例级缺口） |

⚠️ **只升不降**：本工具**不**移除任何 `products` / `verified_on`，**不**把 `availability` 降级。
⚠️ 三组对照（共有端点必须存在 / 阴性对照必须不存在）不符时，证据文件不可用 ⇒ 拒绝执行。

设计约束（沿用本目录既有工具口径）
----------------------------------
* **默认只预演**，`--write` 才落盘；改动逐条打印。
* **幂等**：重复运行不产生新差异。
* **只改 YAML 定义文件**，不碰 manifest —— 落盘后须跑 `sync_manifest.py --write`。
* **保留行尾**（CRLF/LF 原样）与文件其余格式。

用法（仓库根目录执行）
----------------------
    python registry/tools/import_civil_probe.py            # 预演
    python registry/tools/import_civil_probe.py --write    # 落盘
    python registry/tools/import_civil_probe.py --check    # 断言无待处理差异（CI）
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

EVIDENCE_RELATIVE = "live/civil_product_probe.json"
INSTANCE_ALIAS = "civil-cloud"
PRODUCT = "CIVIL_NX"
VERIFIED = "verified"

FLOW_FIELDS = ("products", "verified_on", "unavailable_on")


def _read(path: pathlib.Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _write(path: pathlib.Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _flow_re(field: str) -> re.Pattern[str]:
    return re.compile(rf"^({field}:[ \t]*)(\[[^\]]*\])([ \t]*)$", re.MULTILINE)


def read_flow(text: str, field: str) -> list[str] | None:
    match = _flow_re(field).search(text)
    if not match:
        return None
    inner = match.group(2).strip()[1:-1].strip()
    return [part.strip().strip("'\"") for part in inner.split(",") if part.strip()]


def set_flow(text: str, field: str, values: list[str]) -> str:
    match = _flow_re(field).search(text)
    if not match:
        raise ValueError(f"no top-level `{field}:` flow list")
    rendered = "[" + ", ".join(values) + "]"
    return text[: match.start(2)] + rendered + text[match.end(2) :]


def add_to_flow(text: str, field: str, value: str) -> tuple[str, bool]:
    """把 `value` 并进 `field` 的 flow 列表；**键不存在时**在 `availability:` 之后新建一行。

    ⚠️ 一部分 `OPE.*` / `VIEW.*` 定义**没有** `verified_on:` 键（它们此前从未在任何实例上验证过），
    故必须支持新建 —— 否则会出现「`availability: verified` 但 `verified_on` 缺失」的不一致状态。
    """
    current = read_flow(text, field)
    if current is not None:
        if value in current:
            return text, False
        return set_flow(text, field, sorted({*current, value})), True
    anchor = re.search(r"^availability:[ \t]*\S+[ \t]*$", text, re.MULTILINE)
    if anchor is None:
        raise ValueError(f"no `availability:` anchor to insert `{field}:` after")
    insertion = f"\n{field}: [{value}]"
    return text[: anchor.end()] + insertion + text[anchor.end() :], True


def read_scalar(text: str, field: str) -> str | None:
    match = re.search(rf"^{field}:[ \t]*(\S+)[ \t]*$", text, re.MULTILINE)
    return match.group(1) if match else None


def set_scalar(text: str, field: str, value: str) -> str:
    return re.sub(rf"^{field}:[ \t]*\S+[ \t]*$", f"{field}: {value}", text, count=1, flags=re.MULTILINE)


def load_evidence(repo: pathlib.Path) -> dict:
    path = repo / "registry" / EVIDENCE_RELATIVE
    if not path.is_file():
        raise SystemExit(f"❌ 缺证据文件 registry/{EVIDENCE_RELATIVE}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--write", action="store_true", help="实际写回（默认只预演）")
    parser.add_argument("--check", action="store_true", help="断言无待处理差异（CI）")
    args = parser.parse_args()

    repo = pathlib.Path(args.repo).resolve()
    document = load_evidence(repo)

    # ---- 证据自检：对照组不符 ⇒ 证据不可用 ----
    endpoints = document["endpoints"]
    controls = document.get("controls") or {}
    present = [k for k in controls.get("present_expected", []) if endpoints[k]["status_code"] == 200]
    absent = [k for k in controls.get("absent_expected", []) if endpoints[k]["verdict"] == "ABSENT"]
    ok = len(present) == len(controls.get("present_expected", [])) and len(absent) == len(
        controls.get("absent_expected", [])
    )
    print(f"证据：registry/{EVIDENCE_RELATIVE}（{document['instance']['alias']} / "
          f"{document['instance']['product']} @ {document['instance']['probed_at']}）")
    print(f"自检：共有端点存在 {len(present)}/{len(controls.get('present_expected', []))} · "
          f"阴性对照不存在 {len(absent)}/{len(controls.get('absent_expected', []))} · "
          f"aborted={document.get('aborted')!r}")
    if not ok:
        print("❌ 对照组不符预期 ⇒ 证据不可用，拒绝执行")
        return 2

    manifest = {
        str(item["key"]): item
        for item in json.loads((repo / "registry" / "manifest.json").read_text(encoding="utf-8"))["endpoints"]
    }

    pending: list[tuple[str, pathlib.Path, str, list[str]]] = []
    for key, row in sorted(endpoints.items()):
        if key not in manifest:
            continue
        definition = repo / "registry" / str(manifest[key]["definition"])
        if not definition.is_file():
            continue
        text = _read(definition)
        before = text
        notes: list[str] = []
        status = int(row["status_code"]) if str(row["status_code"]).isdigit() else 0

        if status == 200:
            products = read_flow(text, "products")
            if products is not None and PRODUCT not in products:
                text = set_flow(text, "products", sorted({*products, PRODUCT}))
                notes.append(f"products += {PRODUCT}")
            text, added = add_to_flow(text, "verified_on", INSTANCE_ALIAS)
            if added:
                notes.append(f"verified_on += {INSTANCE_ALIAS}")
            if read_scalar(text, "availability") != VERIFIED:
                text = set_scalar(text, "availability", VERIFIED)
                notes.append("availability → verified")
        elif status != 0:  # 明确非 200 ⇒ 路由不在该产品上
            text, added = add_to_flow(text, "unavailable_on", INSTANCE_ALIAS)
            if added:
                notes.append(f"unavailable_on += {INSTANCE_ALIAS}")

        if text != before:
            pending.append((key, definition, text, notes))

    print("-" * 92)
    for key, definition, _text, notes in pending:
        print(f"  {key:24s} {definition.relative_to(repo)}")
        for note in notes:
            print(f"      {note}")
    print("-" * 92)
    print(f"待写入 {len(pending)} 条")

    if args.check:
        if pending:
            print(f"\n❌ --check 失败：仍有 {len(pending)} 条未收口。", file=sys.stderr)
            return 1
        print("\n✅ --check 通过：CIVIL_NX 探针结论已全部收口。")
        return 0

    if not args.write:
        print("\n（预演模式；加 --write 才会写回 YAML）")
        print("  落盘后请运行： python registry/tools/sync_manifest.py --write")
        return 0

    if not pending:
        print("\n无差异，未写入。")
        return 0

    for _key, definition, text, _notes in pending:
        _write(definition, text)
    print(f"\nWROTE {len(pending)} 个 YAML 定义文件。")
    print("下一步： python registry/tools/sync_manifest.py --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
