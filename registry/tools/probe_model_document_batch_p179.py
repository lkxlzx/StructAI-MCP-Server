#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P179 · **参数化模型的批量往返**（`docs/07` §16.1 **R173**）。

为什么需要它
------------
**R168**（P176）已证明「单样本端到端可用」：导出 → canonical → 改一个坐标 → 导入 →
读回改后的值。但那是**一个**样本（`Eigen-01`）。参数化建模要能用在**任意**模型上，
必须证明：**不同族 / 不同规模的模型**往返都无损，且序列化**逐字节稳定**。

本工具做的是**离线**部分（零请求）：
    DBG JSON  --native_to_canonical-->  ModelDocument  --to_json-->  稳定文本
                     ^                                              |
                     +---------- from_json / canonical_to_native ---+

判据（**铁律 ⓪**：效果，不是状态码）
------------------------------------
1. **往返无损**：`canonical_to_native(native_to_canonical(p))` 与 `p` **逐字段相同**；
2. **序列化稳定**：`to_json(doc)` 两次调用逐字节相同，且 `to_json(from_json(to_json(doc)))`
   与前者相同；
3. **空表保留**：导出里出现的空表在 canonical 侧仍然出现（模块口径 1）。

用法
----
    python registry/tools/probe_model_document_batch_p179.py            # 预演（扫描样本）
    python registry/tools/probe_model_document_batch_p179.py --write    # 落盘证据
    python registry/tools/probe_model_document_batch_p179.py --check    # 断言证据 == 机械结果

⚠️ **样本来源**：`.tmp_p175/*.json`（P175 的导出产物）。样本目录**只读**；
    本工具**不**发任何请求、**不**碰 MIDAS 实例。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Final

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

SAMPLE_DIR: Final[pathlib.Path] = REPO / ".tmp_p175"
EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "model_document_batch_p179.json"
CRITERION_VERSION: Final[int] = 1


def _load() -> tuple[Any, Any, Any, Any, Any]:
    """延迟导入（让 `--check` 也能在无 app 依赖时给出清晰错误）。"""
    from app.infrastructure.adapters.midas.model_document import (  # noqa: PLC0415
        canonical_to_native,
        from_json,
        native_to_canonical,
        to_json,
    )
    from app.infrastructure.adapters.midas.registry import MidasRegistry  # noqa: PLC0415

    registry = MidasRegistry.load(str(REPO / "registry"))
    return registry, native_to_canonical, canonical_to_native, to_json, from_json


def compute() -> dict[str, Any]:
    """扫描样本目录，逐份做往返与稳定性判定（**零请求**）。"""
    registry, native_to_canonical, canonical_to_native, to_json, from_json = _load()

    rows: list[dict[str, Any]] = []
    for path in sorted(SAMPLE_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            rows.append({"sample": path.name, "skipped": f"unreadable: {exc}"})
            continue
        if not isinstance(payload, dict) or "DBG" not in payload:
            rows.append({"sample": path.name, "skipped": "no DBG root"})
            continue

        document = native_to_canonical(payload, registry)
        restored = canonical_to_native(document, registry)
        lossless = json.dumps(restored, sort_keys=True) == json.dumps(payload, sort_keys=True)

        text = to_json(document)
        stable = text == to_json(from_json(text))
        roundtrip_text = to_json(from_json(text))

        empty_tables = sum(1 for block in payload["DBG"].values() if not block)
        empty_kept = all(
            name in document.native for name, block in payload["DBG"].items() if not block
        )

        rows.append(
            {
                "sample": path.name,
                "tables": len(document.native),
                "canonical_tables": len(document.entities),
                "empty_tables": empty_tables,
                "empty_tables_kept": empty_kept,
                "lossless": lossless,
                "serialization_stable": stable,
                "serialization_roundtrip_stable": text == roundtrip_text,
            }
        )

    usable = [row for row in rows if "skipped" not in row]
    passed = all(
        row["lossless"]
        and row["serialization_stable"]
        and row["serialization_roundtrip_stable"]
        and row["empty_tables_kept"]
        for row in usable
    )
    return {
        "tool": "probe_model_document_batch_p179",
        "criterion_version": CRITERION_VERSION,
        "note": [
            "P179 · 参数化模型的**批量**往返（`docs/07` §16.1 **R173**）。",
            "**零请求**：只读 `.tmp_p175/*.json`（P175 的导出产物），不碰 MIDAS 实例。",
            "判据：① 往返**逐字段无损**；② 序列化**逐字节稳定**（两次调用 + 往返后仍相同）；"
            "③ 空表在 canonical 侧**保留**（模块口径 1）。",
        ],
        "samples": rows,
        "summary": {
            "total": len(rows),
            "usable": len(usable),
            "skipped": len(rows) - len(usable),
            "lossless": sum(1 for row in usable if row["lossless"]),
            "stable": sum(1 for row in usable if row["serialization_stable"]),
        },
        "verdict": "PASSED" if passed and usable else "FAILED",
    }


def render(document: dict[str, Any]) -> str:
    """落盘文本（与其他 `registry/live/*.json` 一致）。"""
    return json.dumps(document, ensure_ascii=False, indent=1) + "\n"


def main() -> int:
    """入口（默认预演 / `--write` / `--check`）。"""
    parser = argparse.ArgumentParser(description="参数化模型批量往返（零请求）")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="落盘证据")
    group.add_argument("--check", action="store_true", help="断言证据 == 机械结果")
    args = parser.parse_args()

    document = compute()
    text = render(document)
    current = EVIDENCE.read_text(encoding="utf-8") if EVIDENCE.is_file() else None

    summary = document["summary"]
    print(
        f"样本 {summary['total']} 份（可用 {summary['usable']} · 跳过 {summary['skipped']}）· "
        f"无损 {summary['lossless']} · 稳定 {summary['stable']} ⇒ **{document['verdict']}**"
    )

    if args.check:
        if current != text:
            print("❌ 已落盘证据与机械结果不一致（或文件缺失）")
            return 1
        print(f"✅ {EVIDENCE.relative_to(REPO)} 与机械结果一致")
        return 0 if document["verdict"] == "PASSED" else 1

    if args.write:
        EVIDENCE.write_text(text, encoding="utf-8", newline="\n")
        print(f"WROTE {EVIDENCE.relative_to(REPO)}")
        return 0 if document["verdict"] == "PASSED" else 1

    print("（预演模式；加 --write 落盘 / --check 断言）")
    return 0 if document["verdict"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
