#!/usr/bin/env python3
"""
P175 · 把「导出可见但未登记」的 `DB.*` 表落成 **YAML + Schema**（`docs/07` §16.1 **R168**）。

输入 = `registry/live/export_only_tables_probe.json`（**真机自省**的原文，见同目录
`probe_export_only_tables_p175.py`）。本工具**只**做机械转录：

    `Argument.properties`（自省原文） → `registry/schema/common/db/<CODE>.json`
    表名 + 方法集 + 口径            → `registry/common/db/<CODE>.yaml`

⚠️ **不臆造**：字段、类型、描述**逐字**取自自省原文；自省里没有的**一个都不加**。
⚠️ **只增不改**：已存在的 YAML / Schema **跳过**（除非显式 `--force`）—— 本工具**不**碰
   任何既有端点的裁定。
⚠️ **根形态**：与 `DB.CPSETTINGS` / `DB.ULCT` 两个 `instance_introspect` 先例**同形** ——
   `schema` 的根键是 **`Argument`**（**不**是 `properties`）。这正是 **P168 / R161** 记录的
   「两种根形态」之一，`spec_guard` 走 `unwrap_schema()` 能正确下钻。

用法
----
    python registry/tools/sync_export_only_tables_p175.py            # 预演（零请求）
    python registry/tools/sync_export_only_tables_p175.py --write    # 落盘 + 登记 manifest
    python registry/tools/sync_export_only_tables_p175.py --check    # 离线自洽（零请求）
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Final

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]

EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "export_only_tables_probe.json"
YAML_DIR: Final[pathlib.Path] = REPO / "registry" / "common" / "db"
SCHEMA_DIR: Final[pathlib.Path] = REPO / "registry" / "schema" / "common" / "db"

PRODUCTS: Final[str] = "[GEN_NX, CIVIL_NX]"
"""两个 NX 系产品（与同目录既有 `DB.*` 定义同口径；`DOC.EXPORT` 本身也是这两个产品）。"""

DEFAULT_METHODS: Final[str] = "[POST, GET, PUT, DELETE]"
"""`DB.*` 表的**常规**方法集（`registry/common/db/` 里绝大多数是这个）。

⚠️ 自省（`/info/db/<CODE>`）**只**声明**请求体形状**，**不**声明方法集 ⇒ 这里取同族默认值，
并在 YAML 头部**如实注明**「方法集未逐表实测」。**不**声称已实测。
"""

NOTE_HEADER: Final[str] = (
    """# ⚠️ **P175 / R168**：本表**导出可见但此前未登记** —— `DOC.EXPORT` 实测的 `DBG` 里有它
# （218 张表中的一张），而 Registry 里没有定义 ⇒ 本次**补登**。
#
# **字段来源 = 实例自省**（`GET /info/db/{code}`），**逐字**转录（`schema_source:
# instance_introspect`，与 `DB.CPSETTINGS` / `DB.ULCT` 两个先例同口径）。
# ⚠️ **为何不能靠离线推断**（`probe_export_only_tables_p175.py --check` 可复算）：
#   ① 上游手册 **0 / 27** 有对应端点（两处同名命中经查是 `DESIGN.*.CMFT` 这类**同名不同义**）；
#   ② 仓库既有实例证据 **0 / 27**（可能的命中全是**子串误报**，如 `SWIND` 含 `WIND`）；
#   ③ `DOC.EXPORT` 里这些表**全是空表** ⇒ 连一个字段名都拿不到。
#
# ⚠️ **方法集未逐表实测**：自省只声明**请求体形状**，不声明方法 ⇒ 这里用 `DB.*` 的常规值，
# 并如实把 `availability` 留在 `untested`（**不**声称可用；收口需另一次实测）。
"""
)


def _evidence(repo: pathlib.Path) -> dict[str, Any]:
    if not EVIDENCE.is_file():
        raise SystemExit(f"❌ 缺证据 {EVIDENCE.relative_to(REPO)}（先跑 probe --probe）")
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def rows(repo: pathlib.Path) -> dict[str, Any]:
    """自省成功的行（**只**取 `verdict == PASSED` 且**真有字段**的）。"""
    document = _evidence(repo)
    out: dict[str, Any] = {}
    for code, row in (document.get("rows") or {}).items():
        introspect = row.get("introspect")
        if row.get("verdict") != "PASSED" or not isinstance(introspect, dict):
            continue
        if not (introspect.get("properties") or {}):
            continue
        out[str(code)] = row
    return out


def yaml_text(code: str) -> str:
    """生成端点 YAML（**逐字**照同目录既有 `DB.*` 的形状）。"""
    return (
        NOTE_HEADER
        + f"key: DB.{code}\n"
        + "namespace: DB\n"
        + f"uri: /DB/{code}\n"
        + f"methods: {DEFAULT_METHODS}\n"
        + "tool_map:\n"
        + "  query: midas_db_query\n"
        + "  assign: midas_db_assign\n"
        + "wrapper:\n"
        + "  write: Assign\n"
        + f"  read_root: {code}\n"
        + "schema_ref:\n"
        + f"  local: schema/common/db/{code}.json\n"
        + f"  introspect: info/db/{code}\n"
        + "  source: instance_introspect\n"
        + "parser: db_generic\n"
        + f"products: {PRODUCTS}\n"
        + "availability: untested\n"
        + "table_type: null\n"
        + "title: null\n"
        + "risk:\n"
        + "  level: low\n"
        + "  destructive: false\n"
        + "  retry:\n"
        + "    GET: true\n"
        + "    POST: conditional\n"
        + "    PUT: conditional\n"
        + "runtime:\n"
        + "  requires_project: true\n"
        + "  requires_analysis: false\n"
        + "execution:\n"
        + "  mode: FAST\n"
        + "  timeout_ms: 30000\n"
        + "  retryable: true\n"
        + "  idempotent: false\n"
        + "capability: [MODEL]\n"
        + "source:\n"
        + "  url: null\n"
        + "  retrieved_at: null\n"
        + "  provenance: [instance_introspect]\n"
        + "stats:\n"
        + "  spec_rows: 0\n"
        + "  examples: 0\n"
        + "  has_response_head: false\n"
    )


def schema_text(code: str, introspect: dict[str, Any]) -> str:
    """生成 Schema（根键 = **`Argument`**，与两个 `instance_introspect` 先例同形）。"""
    document = {
        "key": f"DB.{code}",
        "uri": f"DB/{code}",
        "source": "instance_introspect",
        "schema": {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "Argument": introspect,
        },
    }
    return json.dumps(document, ensure_ascii=False, indent=1) + "\n"


MANIFEST: Final[pathlib.Path] = REPO / "registry" / "manifest.json"


def manifest_entry(code: str) -> dict[str, Any]:
    """`manifest.json` 的条目（字段顺序 / 形状**逐字**照 `DB.CPSETTINGS` 那条先例）。"""
    return {
        "key": f"DB.{code}",
        "namespace": "DB",
        "uri": f"/DB/{code}",
        "methods": "POST, GET, PUT, DELETE",
        "products": ["GEN_NX", "CIVIL_NX"],
        "definition": f"common/db/{code}.yaml",
        "schema": f"schema/common/db/{code}.json",
        "schema_source": "instance_introspect",
        "table_type": "",
        "title": "",
        "title_zh": "",
        "title_zh_official": None,
        "spec_rows": 0,
        "examples": 0,
        "execution_mode": "FAST",
        "solver": "",
        "availability": "untested",
        "verified_on": [],
        "unavailable_on": [],
        "enabled": True,
        "disable_reason": "",
        "path_key_supported": True,
        "params_ref": "",
        "schema_shape": "",
        "wrapper": {"write": "Assign", "read_root": code},
        "risk": {
            "level": "low",
            "destructive": False,
            "retry": {"GET": True, "POST": "conditional", "PUT": "conditional"},
        },
        "product_overrides": {},
        "provenance": ["instance_introspect"],
    }


def register(write: bool) -> int:
    """把新表登记进 `manifest.json`（**只增**：已存在的一律跳过，不碰任何既有条目）。"""
    data = rows(REPO)
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    existing = {str(entry.get("key")) for entry in document["endpoints"]}
    added: list[str] = []
    for code in sorted(data):
        key = f"DB.{code}"
        if key in existing:
            continue
        if write:
            document["endpoints"].append(manifest_entry(code))
        added.append(key)
    if not added:
        print("✅ manifest 已含全部目标（无需登记）")
        return 0
    if not write:
        print(f"（预演；将登记 {len(added)} 条：{added[:5]} …）")
        return 0
    # ⚠️ 三个计数**一起**更新（只改 keys 会留下不一致的 manifest，实测踩到）。
    document["counts"]["keys"] = len(document["endpoints"])
    document["counts"]["schemas"] = sum(
        1 for entry in document["endpoints"] if entry.get("schema")
    )
    buckets = document["counts"].setdefault("buckets", {})
    buckets["common"] = buckets.get("common", 0) + len(added)
    MANIFEST.write_text(
        json.dumps(document, ensure_ascii=False, indent=1) + chr(10), encoding="utf-8"
    )
    print(f"✅ 已登记 {len(added)} 条 ⇒ manifest 条目 {document['counts']['keys']}")
    return 0


def main() -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="导出可见但未登记的 DB 表的 YAML/Schema 转录")
    parser.add_argument("--write", action="store_true", help="真的写盘（默认只预演）")
    parser.add_argument("--check", action="store_true", help="离线自洽断言（零请求）")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的文件（默认跳过）")
    parser.add_argument("--register", action="store_true", help="把新表登记进 manifest.json")
    args = parser.parse_args()

    if args.check:
        return check_offline()
    if args.register:
        return register(write=False)

    data = rows(REPO)
    if not data:
        print("✅ 无待转录的表（证据里没有 PASSED 行）")
        return 0

    print(f"待转录 **{len(data)}** 张表：{sorted(data)}")
    written = skipped = 0
    for code in sorted(data):
        yaml_path = YAML_DIR / f"{code}.yaml"
        schema_path = SCHEMA_DIR / f"{code}.json"
        exists = yaml_path.exists() or schema_path.exists()
        if exists and not args.force:
            print(f"  跳过 {code}（已存在；`--force` 才覆盖）")
            skipped += 1
            continue
        if not args.write:
            print(f"  [预演] 将写 {yaml_path.relative_to(REPO)} + {schema_path.relative_to(REPO)}")
            written += 1
            continue
        yaml_path.write_text(yaml_text(code), encoding="utf-8")
        schema_path.write_text(schema_text(code, data[code]["introspect"]), encoding="utf-8")
        written += 1
    if not args.write:
        print(f"\n（预演；将写 {written} 张 · 跳过 {skipped} 张。加 --write 才落盘）")
        return 0
    print(f"\n✅ 已写 {written} 张 · 跳过 {skipped} 张")
    # ⚠️ 落盘之后**必须**登记 manifest —— 否则新 YAML 是「孤儿」
    #    （`sync_manifest.py` 只更新**已有**条目，**不**扫目录 ⇒ 不会自动发现）。
    return register(write=True)
    return 0


def check_offline() -> int:
    """`--check`：每个待转录的表都有 YAML + Schema，且字段**逐字**等于自省原文。"""
    data = rows(REPO)
    if not data:
        print("✅ 无待转录的表")
        return 0
    problems: list[str] = []
    for code, row in sorted(data.items()):
        yaml_path = YAML_DIR / f"{code}.yaml"
        schema_path = SCHEMA_DIR / f"{code}.json"
        if not yaml_path.is_file():
            problems.append(f"缺 YAML：{yaml_path.relative_to(REPO)}")
            continue
        if not schema_path.is_file():
            problems.append(f"缺 Schema：{schema_path.relative_to(REPO)}")
            continue
        document = json.loads(schema_path.read_text(encoding="utf-8"))
        if document.get("source") != "instance_introspect":
            problems.append(f"`{code}` 的 `source` 应为 `instance_introspect`")
        written = (document.get("schema") or {}).get("Argument")
        if written != row["introspect"]:
            problems.append(f"`{code}` 的 Schema **与自省原文不一致** ⇒ 被改写过（不臆造原则）")
        text = yaml_path.read_text(encoding="utf-8")
        for needle in ("availability: untested", "source: instance_introspect", f"key: DB.{code}"):
            if needle not in text:
                problems.append(f"`{code}` 的 YAML 缺 `{needle}`")
    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    print(f"✅ 离线自洽：{len(data)} 张表的 YAML + Schema 齐备，且字段与自省原文**逐字一致**")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
