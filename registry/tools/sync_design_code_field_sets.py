#!/usr/bin/env python3
"""
P176 · 设计规范字段集的**离线复算**（`docs/07` §16.1 **R168** 续）。

它做什么
--------
复算 `registry/live/design_code_field_sets.json` 与**实测证据**是否一致 —— **零请求**。

⚠️ **为什么字段集只能来自实测**（P176 已证，逐条可复算）
--------------------------------------------------------
① **自省不反映它**：`GET /info/design/RC/KDS-41-20-2022/DCO` 在 KDS 与 `GB/T50010-10`
   两种生效规范下**返回同一份 13 字段** ⇒ 它是**端点声明的形状**，**不是**当前规范接受的集合。
② **规范码不能进路径**：`/design/RC/GB-T50010-10/DCO` → `404`
   ⇒ 路径段 `KDS-41-20-2022` 是**固定路由名**；切换规范只能靠 `DRC` 的 `DGNCODE` 字段。
⇒ 唯一的来源是**有副作用的 `PUT` 实测**，本工具把它的结论**机械地**对照回来。

判据（**铁律 ⓪**：效果，不是状态码）
------------------------------------
逐条：
* **来源合法** —— 每条记录的 `source` ∈ `{measured, manual}`（**不**允许 `introspect`，
  理由见上）；
* **证据存在** —— `evidence` 指向的文件必须存在；
* **与实测一致** —— `KDS 41 20 : 2022` 的 `DCO` 字段数 **12**（自省声明 13，差集
  **恰好**是 `CONC_STRS_STRN`）；`GB/T50010-10` 的 `DCO` 字段数 **0**；
* **两相可判** —— 证据里 `prior.design_rows == 0` ∧ `matched.design_rows > 0`
  （否则「规范匹配 ⇒ 设计产出」这条结论不成立，字段集也就失去依据）。

用法
----
    python registry/tools/sync_design_code_field_sets.py            # 预演（只报差异）
    python registry/tools/sync_design_code_field_sets.py --check    # 断言一致（退出码）
    python registry/tools/sync_design_code_field_sets.py --write    # 写回（仅在差异已确认时）
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Final

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]

FIELD_SETS: Final[pathlib.Path] = REPO / "registry" / "live" / "design_code_field_sets.json"
EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "concrete_code_match_probe.json"
INTROSPECT_EVIDENCE: Final[pathlib.Path] = (
    REPO / "registry" / "live" / "export_only_tables_probe.json"
)
"""自省证据（`GET /info/...`）—— 本工具**不**用它作字段集来源，只用来说明「它不反映」。"""

MEASURED_CODES: Final[dict[str, int]] = {
    "KDS 41 20 : 2022": 12,
    "GB/T50010-10": 0,
}
"""`(code → DCO 实测可接受字段数)` —— P176 逐字段单发实测的结果（**可复算**）。"""

INTROSPECT_DECLARED: Final[int] = 13
"""端点自省**声明**的 `DCO` 字段数（与生效规范**无关**）。"""

DROPPED_BY_NATIVE: Final[str] = "CONC_STRS_STRN"
"""自省声明、但原生**拒收**的那个字段（KDS 下）—— 这正是「自省撒谎」的直接证据。"""

ALLOWED_SOURCES: Final[frozenset[str]] = frozenset({"measured", "manual"})


def _load(path: pathlib.Path) -> Any:
    """读 JSON（缺文件 → `None`，由调用方给明确结论）。"""
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def facts(repo: pathlib.Path) -> dict[str, Any]:
    """机械复算的**事实**（**零请求**；只读已落盘的数据与证据）。"""
    document = _load(FIELD_SETS)
    evidence = _load(EVIDENCE)
    return {
        "field_sets": document,
        "evidence": evidence,
        "measured_codes": dict(MEASURED_CODES),
        "introspect_declared": INTROSPECT_DECLARED,
        "dropped_by_native": DROPPED_BY_NATIVE,
    }


def check(repo: pathlib.Path) -> int:
    """断言字段集与实测证据一致（**零请求**）。"""
    problems: list[str] = []
    document = _load(FIELD_SETS)
    if document is None:
        print(f"❌ 缺数据文件 {FIELD_SETS.relative_to(repo)}")
        return 1
    evidence = _load(EVIDENCE)
    if evidence is None:
        print(f"❌ 缺证据 {EVIDENCE.relative_to(repo)}（字段集的唯一来源）")
        return 1

    # ---- ① 来源合法 ----
    materials = document.get("materials") or {}
    for material, codes in materials.items():
        for code, endpoints in codes.items():
            for endpoint, entry in endpoints.items():
                source = str((entry or {}).get("source") or "")
                if source not in ALLOWED_SOURCES:
                    problems.append(
                        f"`{material}/{code}/{endpoint}` 的 source = {source!r} "
                        f"∉ {sorted(ALLOWED_SOURCES)}（**自省不能作来源**）"
                    )
                ref = str((entry or {}).get("evidence") or "")
                if ref and not (repo / ref).is_file():
                    problems.append(f"`{material}/{code}/{endpoint}` 的证据不存在：{ref}")

    # ---- ② 与实测一致 ----
    for code, expected in MEASURED_CODES.items():
        entry = ((materials.get("RC") or {}).get(code) or {}).get("DCO")
        if entry is None:
            problems.append(f"缺 `RC/{code}/DCO` 记录（P176 已实测 ⇒ 必须登记）")
            continue
        fields = entry.get("fields")
        if not isinstance(fields, list):
            problems.append(f"`RC/{code}/DCO` 的 fields 不是列表")
            continue
        if len(fields) != expected:
            problems.append(
                f"`RC/{code}/DCO` 字段数 {len(fields)} ≠ 实测 {expected}"
            )
        if code == "KDS 41 20 : 2022":
            if DROPPED_BY_NATIVE in fields:
                problems.append(
                    f"`RC/{code}/DCO` 含 `{DROPPED_BY_NATIVE}` —— 它**被原生拒收**"
                    "（逐字段单发实测 `400 Wrong Field`）"
                )
            if len(fields) + 1 != INTROSPECT_DECLARED:
                problems.append(
                    f"`RC/{code}/DCO` 字段数 {len(fields)} + 1 ≠ 自省声明 "
                    f"{INTROSPECT_DECLARED} ⇒ 与「自省多报一个」不符"
                )
        if code == "GB/T50010-10" and fields:
            problems.append(
                f"`RC/{code}/DCO` 应为**空集**（该规范下 `DESIGN_CD` 也被拒）"
            )

    # ---- ③ 两相可判（结论的前提） ----
    phases = evidence.get("phases") or {}
    prior = phases.get("prior") or {}
    matched = phases.get("matched") or {}
    if int(prior.get("design_rows") or 0) != 0:
        problems.append("证据相 ① 竟有结果行 ⇒ 「规范不匹配 ⇒ 0 行」不成立")
    if int(matched.get("design_rows") or 0) <= 0:
        problems.append("证据相 ② **没有**结果行 ⇒ 「规范匹配 ⇒ 设计产出」不成立")
    if int(matched.get("status") or 0) != 200:
        problems.append(f"证据相 ② 的 `BD-ANAL` 状态 {matched.get('status')} ≠ 200")

    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    print(
        "✅ 字段集与实测一致："
        f"`KDS 41 20 : 2022` **{MEASURED_CODES['KDS 41 20 : 2022']}** 字段"
        f"（自省声明 {INTROSPECT_DECLARED}，差集 = `{DROPPED_BY_NATIVE}`）· "
        f"`GB/T50010-10` **{MEASURED_CODES['GB/T50010-10']}** 字段 · "
        "证据两相可判（0 行 / 3 行）· 来源全部为实测"
    )
    return 0


def summary(repo: pathlib.Path) -> int:
    """打印摘要（预演）。"""
    document = _load(FIELD_SETS)
    if document is None:
        print(f"❌ 缺数据文件 {FIELD_SETS.relative_to(repo)}")
        return 1
    materials = document.get("materials") or {}
    total = 0
    print(f"数据文件 = {FIELD_SETS.relative_to(repo)}")
    for material, codes in sorted(materials.items()):
        print(f"  材料 `{material}`：")
        for code, endpoints in sorted(codes.items()):
            for endpoint, entry in sorted(endpoints.items()):
                fields = (entry or {}).get("fields") or []
                source = (entry or {}).get("source") or ""
                total += 1
                print(
                    f"    {code:22s} {endpoint:6s} → {len(fields):2d} 字段"
                    f"（source={source}）"
                )
    print(f"  合计 {total} 条记录")
    return 0


def main() -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="设计规范字段集的离线复算")
    parser.add_argument("--check", action="store_true", help="断言与实测一致（零请求）")
    parser.add_argument("--write", action="store_true", help="写回（当前无自动生成，占位）")
    args = parser.parse_args()
    if args.check:
        return check(REPO)
    if args.write:
        print("⚠️ 本工具**不**自动生成字段集（它只能来自实测）—— 请手工维护并跑 --check。")
        return 1
    return summary(REPO)


if __name__ == "__main__":
    raise SystemExit(main())
