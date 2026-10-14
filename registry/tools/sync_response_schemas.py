#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为**已实测**的端点补 `direction: response` 的响应 Schema（`docs/07` §16 R87 / R90）。

背景（重要）：
    数据侧 `registry/schema/**` 原本**只有**请求方向 Schema
    （`midas_api_schemas.direction = "request"`），因此 `docs/04` §8 的 7 项 AND 里
    「Response Schema 已确认」**恒为假** —— 任何端点都**不**得升 `VERIFIED`
    （`docs/07` §16 R78 / R87）。本工具把「实测过的响应信封」落成数据，
    让同一判定点（`live.py` 的 `seven_and_verdict` / `registry_evidence`）可以如实升级。

「已实测」的判定口径（**不**臆造）
--------------------------------
`registry/README.md` §4：`availability: verified` = **至少一个实例 GET 成功**。
本工具据此只处理满足**全部**下列条件的端点：

    1. `availability == "verified"`            —— 实测成功过（不是 untested / unverified）；
    2. `methods` 含 `GET`                       —— 响应信封来自只读探测；
    3. 该端点有可读的 Schema 文件                —— 响应块补进**同一个**文件（不新增文件）；
    4. 声明了解包链（`wrapper.read_root` 或 `wrapper.read_root_path`，
       含 `product_overrides.<产品>.wrapper.read_root_path`）—— 链为空即无实测依据，跳过。
       ⚠️ **P149-D / R106**：`POST.*` 取报表端点**没有** `GET`，其信封键来自**取报表判据实测**
       （`registry/live/result_table_probe.json`，见 `measured_envelope_keys()`）——
       该证据非空时第 2 / 4 条按它成立（**同一** `response_block()` 构造点，**不**另写判定）。

写入的 `response` 块**只**描述实测到的**信封**，不含任何未经实测的载荷字段：

    NX 系（`{<read_root>: {...}}`，`registry/README.md` §4 的实测口径）
        -> {"required": [read_root], "properties": {read_root: {"type": "object"}}}
    声明了解包链的产品（`CIVIL_DESIGNER` 实测在 `result.return_value`，R83）
        -> 按链逐层 `required` / `properties`，**叶子类型留空**（未实测 → 不猜）

一个端点若有多个产品用不同信封（如 `DB.NODE`），`schema` 用 `oneOf` 列出各分支。

⚠️ **不改写任何既有取值**：请求方向的 `schema` 原样保留，只在同一文件里**追加** `response`。

用法（仓库根目录执行，先跑 `sync_manifest.py`）：
    python registry/tools/sync_manifest.py --write
    python registry/tools/sync_response_schemas.py            # 预演，只打印差异
    python registry/tools/sync_response_schemas.py --write    # 实际写回
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

RESULT_TABLE_EVIDENCE_RELATIVE = "live/result_table_probe.json"
"""**R106**（P149-D）取报表判据的实测证据（`registry/tools/probe_result_tables.py --probe` 的产物）。"""


def measured_envelope_keys(repo: pathlib.Path) -> dict[str, str]:
    """`key → 实测信封键`（**R106**：取报表端点的**有数据**响应顶层键；缺证据 ⇒ 空）。

    这些端点**没有** `GET`（只有 `POST` 取表），其响应信封**无法**从 `wrapper.read_root` /
    `read_root_path` 推出，只能来自**取报表判据实测**（`registry/README.md` §8.13）——
    本函数把那份证据接进同一条生成链，使 `envelope_chains()` / `is_measured()` 对它们**同样**成立
    （**不**另写一套判定）。
    """
    path = repo / "registry" / RESULT_TABLE_EVIDENCE_RELATIVE
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = document.get("endpoints")
    if not isinstance(rows, dict):
        return {}
    return {
        str(key): str(row.get("envelope_key") or "")
        for key, row in rows.items()
        if str(row.get("verdict") or "") == "PASSED" and str(row.get("envelope_key") or "")
    }


RESPONSE_SOURCE = "l4_measured_envelope"
"""`response.source` 的固定取值：信封来自 L4 只读实测（P134 / P136）。"""

DIALECT = "https://json-schema.org/draft/2020-12/schema"
"""`registry/README.md` §2.1（`docs/07` §16 R18）：本仓库自有的 Schema 一律 2020-12。"""


def envelope_chains(
    entry: dict[str, Any], measured_key: str = ""
) -> tuple[tuple[str, ...], ...]:
    """该端点在**各产品**上的实测解包链（去重、排序；空链丢弃）。

    `registry/README.md` §4：优先级 = `product_overrides.<产品>.wrapper.read_root_path`
    → 端点 `wrapper.read_root_path` → `wrapper.read_root`。

    `measured_key`（**R106** / P149-D）：取报表端点**没有** `GET` 解包链，其信封键来自
    `registry/live/result_table_probe.json` 的**实测**（`measured_envelope_keys()`）——
    非空时作为一条链并入（**同一** `response_block()` 构造点，**不**另写判定）。
    """
    wrapper = entry.get("wrapper") or {}
    read_root = str(wrapper.get("read_root") or "").strip()
    declared = tuple(str(part).strip() for part in (wrapper.get("read_root_path") or []))
    chains: set[tuple[str, ...]] = set()
    if read_root:
        chains.add((read_root,))
    if measured_key:
        chains.add((measured_key,))
    if declared:
        chains.add(tuple(part for part in declared if part))
    for override in (entry.get("product_overrides") or {}).values():
        override_wrapper = (override or {}).get("wrapper") or {}
        chain = tuple(
            str(part).strip() for part in (override_wrapper.get("read_root_path") or [])
        )
        if chain and all(chain):
            chains.add(chain)
    return tuple(sorted(chain for chain in chains if chain))


def envelope_branch(chain: tuple[str, ...]) -> dict[str, Any]:
    """一条解包链 → JSON Schema 分支（只断言「实测到的信封层级」）。

    单段链（`(read_root,)`）来自 `wrapper.read_root`，其值按 `registry/README.md` §4
    的实测口径是**对象**（`{<read_root>: {...}}`）；多段链来自显式声明
    （`CIVIL_DESIGNER` 的 `result.return_value`，R83），中间层按实测是对象，
    **叶子类型不猜**（`{}` = 任意）。
    """
    if len(chain) == 1:
        return {
            "required": [chain[0]],
            "properties": {chain[0]: {"type": "object"}},
        }
    node: dict[str, Any] = {}
    for name in reversed(chain):
        node = {"type": "object", "required": [name], "properties": {name: node}}
    return node


def response_block(chains: tuple[tuple[str, ...], ...]) -> dict[str, Any]:
    """解包链集合 → 端点 `response` 块（**唯一**构造点）。"""
    branches = [envelope_branch(chain) for chain in chains]
    schema: dict[str, Any] = {"$schema": DIALECT, "type": "object"}
    if len(branches) == 1:
        schema.update(branches[0])
    else:
        schema["oneOf"] = branches
    return {"direction": "response", "source": RESPONSE_SOURCE, "schema": schema}


def is_measured(entry: dict[str, Any], measured_key: str = "") -> bool:
    """该端点是否满足「已实测」的四条判定（见模块文档）。

    `measured_key`（**R106** / P149-D）：取报表端点**只**有 `POST`（没有 `GET`），
    其信封来自取报表判据实测 ⇒ 非空时同样算「已实测」（**不**放宽：仍是「实测成功过」）。
    """
    if str(entry.get("availability") or "") != "verified":
        return False
    if measured_key:
        return True
    methods = [part.strip().upper() for part in str(entry.get("methods") or "").split(",")]
    return "GET" in methods


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--write", action="store_true", help="实际写回（默认只预演）")
    args = parser.parse_args()

    repo = pathlib.Path(args.repo).resolve()
    reg = repo / "registry"
    manifest = json.loads((reg / "manifest.json").read_text(encoding="utf-8"))

    changed: list[tuple[str, tuple[tuple[str, ...], ...]]] = []
    skipped_no_schema: list[str] = []
    skipped_no_chain: list[str] = []
    considered = 0

    measured_keys = measured_envelope_keys(repo)
    for entry in manifest["endpoints"]:
        measured_key = measured_keys.get(str(entry["key"]), "")
        if not is_measured(entry, measured_key):
            continue
        considered += 1
        chains = envelope_chains(entry, measured_key)
        if not chains:
            skipped_no_chain.append(entry["key"])
            continue
        relative = str(entry.get("schema") or "")
        path = reg / relative
        if not relative or not path.is_file():
            skipped_no_schema.append(entry["key"])
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        block = response_block(chains)
        if document.get("response") == block:
            continue
        document["response"] = block
        if args.write:
            path.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        changed.append((entry["key"], chains))

    print(f"已实测端点（availability=verified ∧（GET ∨ R106 取报表实测信封））= {considered}")
    print(f"补 response Schema 的端点 = {len(changed)}")
    print(f"跳过（无 Schema 文件）= {len(skipped_no_schema)} {skipped_no_schema[:10]}")
    print(f"跳过（未声明解包链）= {len(skipped_no_chain)} {skipped_no_chain[:10]}")
    if changed:
        print("-" * 90)
        for key, chains in changed:
            print(f"  {key}")
            for chain in chains:
                print(f"      envelope: {' -> '.join(chain)}")
    if args.write:
        if not changed:
            print("\n无差异，未写入。")
            return 0
        print(f"\nWROTE {len(changed)} 个 Schema 文件（只追加 response 块）")
    else:
        print("\n（预演模式；加 --write 才会写回）")
    return 0


if __name__ == "__main__":
    # Windows 控制台默认 cp949/cp936：本工具会打印中文/符号，不重设编码会 UnicodeEncodeError。
    # ⚠️ 必须在 `__main__` 块内：测试用 `exec_module()` 装载本模块，模块级调用会改写
    #    **pytest 的捕获流**，破坏其后所有用例的 capture。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
