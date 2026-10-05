#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从官方手册抽取「设计规范（Design Code）」全量枚举，生成 registry/design_codes.yaml。

用法（仓库根目录执行）：
    python registry/tools/extract_design_codes.py

输入（均为只读，不联网）：
    MIDAS_API_Online_Manual_完整API手册_v1.0.md   —— NX 系 /db/DCON、/db/DSTL 枚举表
    <Civil Designer 手册>/md/...JSON手册.md        —— Civil Designer /db/MODULE.DgnCode 枚举表

输出：
    registry/design_codes.yaml

原则：逐行抽取，不改写、不推断。手册没有的规范绝不臆造。
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

# ---------------------------------------------------------------- 解析工具


def parse_enum_table(lines: list[str], start_1based: int, end_1based: int) -> list[tuple[int, str, str]]:
    """解析 `| No. | Design Code | DGNCODE | ...` 形式的枚举表。"""
    rows: list[tuple[int, str, str]] = []
    for i in range(start_1based - 1, end_1based):
        ln = lines[i]
        if not ln.startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) < 3 or not re.fullmatch(r"\d+", cells[0]):
            continue
        rows.append((int(cells[0]), cells[1], cells[2].strip('"')))
    return rows


def parse_module_groups(lines: list[str], start_1based: int, end_1based: int) -> dict[str, list[tuple[int, str]]]:
    """解析 Designer 手册里 <summary>DgnCode-XXX</summary> 之后的 `<br>` 拼接表。"""
    groups: dict[str, list[tuple[int, str]]] = {}
    cur: str | None = None
    for i in range(start_1based - 1, end_1based):
        ln = lines[i]
        m = re.search(r"<summary>DgnCode-(.+?)</summary>", ln)
        if m:
            cur = m.group(1)
            groups[cur] = []
            continue
        if cur and ln.startswith("|"):
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if len(cells) >= 2 and re.fullmatch(r"\d+(\s*<br>\s*\d+)*", cells[0]):
                nos = [int(x.strip()) for x in cells[0].split("<br>")]
                names = [x.strip() for x in cells[1].split("<br>")]
                if len(nos) == len(names):
                    groups[cur].extend(zip(nos, names))
                else:
                    print(f"WARN {cur}: 序号/规范数不匹配 {len(nos)} vs {len(names)}",
                          file=sys.stderr)
    return groups


def yq(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ---------------------------------------------------------------- 主流程


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".", help="仓库根目录（默认当前目录）")
    ap.add_argument("--nx-manual",
                    default="MIDAS_API_Online_Manual_完整API手册_v1.0.md",
                    help="NX 系手册（相对仓库根）")
    ap.add_argument("--designer-manual",
                    default=r"G:\midas Civil Designer - API\md\midas Civil Designer - API JSON手册.md",
                    help="Civil Designer 手册（绝对或相对路径）")
    ap.add_argument("--out", default="registry/design_codes.yaml")
    args = ap.parse_args()

    repo = pathlib.Path(args.repo).resolve()
    nx_path = repo / args.nx_manual
    cd_path = pathlib.Path(args.designer_manual)

    for p in (nx_path, cd_path):
        if not p.exists():
            print(f"ERROR: 找不到手册 {p}", file=sys.stderr)
            return 2

    nx = nx_path.read_text(encoding="utf-8").split("\n")
    cd = cd_path.read_text(encoding="utf-8").split("\n")

    # --- A / B：NX 系两张枚举表（行号锚定；锚点漂移时下面的断言会报错）---
    dcon = parse_enum_table(nx, 6663, 6726)
    dstl = parse_enum_table(nx, 56319, 56384)
    assert len(dcon) == 64, f"/db/DCON 期望 64 条，实得 {len(dcon)}（手册行号可能已漂移）"
    assert len(dstl) == 66, f"/db/DSTL 期望 66 条，实得 {len(dstl)}（手册行号可能已漂移）"

    # --- C：Designer 的 4 个模块组 ---
    mod = parse_module_groups(cd, 716, 752)
    assert sum(len(v) for v in mod.values()) == 22, \
        f"DgnCode 期望 22 条，实得 {sum(len(v) for v in mod.values())}"

    out: list[str] = []
    w = out.append

    w("# StructAI Registry —— 设计规范（Design Code）枚举")
    w("#")
    w("# 本文件是「软件无关」的规范候选集：只描述**候选**，不声称任何实例一定支持。")
    w("# 实例的实际支持集由 Adapter 在连接时通过 API 探测（见文件末尾 discover 块），")
    w("# 探测结果不落盘，仅存于连接会话。")
    w("#")
    w("# 数据来源：MIDAS 官方手册原文枚举表，逐行抽取，未改写、未推断。")
    w("# 重新生成：python registry/tools/extract_design_codes.py")
    w("#")
    w("version: 1.0")
    w('generated_at: "2026-10-05"')
    w("")

    w("# ============================================================================")
    w("# A. NX 系（GEN NX / CIVIL NX）混凝土设计规范")
    w("#    端点：DB.DCON   URI：/db/DCON")
    w('#    字段：Assign["1"].DGNCODE（string）')
    w("# ============================================================================")
    w("nx_rc:")
    w("  endpoint_key: DB.DCON")
    w("  uri: /DB/DCON")
    w("  field: DGNCODE")
    w("  products: [GEN_NX, CIVIL_NX]")
    w("  source:")
    w(f'    manual: {yq(nx_path.name)}')
    w('    lines: "6662-6726"')
    w('    url: "https://support.midasuser.com/hc/en-us/articles/35802155483801"')
    w(f"  count: {len(dcon)}")
    w("  codes:")
    for no, name, code in dcon:
        w(f"    - {{ no: {no}, display: {yq(name)}, code: {yq(code)} }}")
    w("")

    w("# ============================================================================")
    w("# B. NX 系（GEN NX / CIVIL NX）钢设计规范")
    w("#    端点：DB.DSTL   URI：/db/DSTL")
    w('#    字段：Assign["1"].DGNCODE（string）')
    w("# ============================================================================")
    w("nx_steel:")
    w("  endpoint_key: DB.DSTL")
    w("  uri: /DB/DSTL")
    w("  field: DGNCODE")
    w("  products: [GEN_NX, CIVIL_NX]")
    w("  source:")
    w(f'    manual: {yq(nx_path.name)}')
    w('    lines: "56318-56384"')
    w('    url: "https://support.midasuser.com/hc/en-us/articles/35802155483801"')
    w(f"  count: {len(dstl)}")
    w("  codes:")
    for no, name, code in dstl:
        w(f"    - {{ no: {no}, display: {yq(name)}, code: {yq(code)} }}")
    w("")

    w("# ============================================================================")
    w("# C. Civil Designer —— 中国公路/铁路桥涵规范")
    w("#    端点：DB.MODULE   URI：/db/MODULE")
    w("#    字段：DgnCode（integer），配合 Module（0-设计 1-评定 2-试验 3-加固）")
    w("#    注意：这是 integer 编号，与 A/B 的 string DGNCODE 是两套不同机制。")
    w("# ============================================================================")
    w("designer_module:")
    w("  endpoint_key: DB.MODULE")
    w("  uri: /DB/MODULE")
    w("  field: DgnCode")
    w("  field_type: integer")
    w("  companion_field: Module")
    w("  products: [CIVIL_DESIGNER]")
    w("  source:")
    w(f'    manual: {yq(cd_path.name)}')
    w('    lines: "706-751"')
    w("  groups:")
    for gname, module_id in (("设计模块", 0), ("评定模块", 1), ("试验模块", 2), ("加固模块", 3)):
        items = mod.get(gname, [])
        w(f"    - module: {module_id}")
        w(f"      module_name: {yq(gname)}")
        w(f"      count: {len(items)}")
        w("      codes:")
        for no, name in items:
            w(f"        - {{ dgncode: {no}, display: {yq(name)} }}")
    w("")

    w("# ============================================================================")
    w("# D. Civil Designer —— 设计代码命名空间（规范代码编码在 URI 路径段）")
    w("#    URI 形如 /DESIGN/{RC|STEEL|SRC}/{CODE}/...")
    w("#    每个材料的代码选择器是单例端点，字段 DGNCODE（string）")
    w("# ============================================================================")
    w("designer_design:")
    w('  uri_pattern: "/DESIGN/{material}/{code}/{endpoint}"')
    w("  products: [CIVIL_DESIGNER]")
    w("  source:")
    w(f'    manual: {yq(nx_path.name)}')
    w('    note: "由 registry/design/** 的 125 个端点反推；每材料一个代码选择器"')
    w("  selectors:")
    w("    - material: RC")
    w("      selector_key: DESIGN.RC.DRC")
    w("      selector_uri: /DESIGN/RC/DRC")
    w("      response_root: DCON")
    w('      code: "KDS 41 20 : 2022"')
    w('      endpoint_prefix: "DESIGN.RC.KDS-41-20-2022"')
    w("      endpoint_count: 69")
    w("    - material: STEEL")
    w("      selector_key: DESIGN.STEEL.DSTL")
    w("      selector_uri: /DESIGN/STEEL/DSTL")
    w("      response_root: DSTL")
    w('      code: "KDS 41 30 : 2022"')
    w('      endpoint_prefix: "DESIGN.STEEL.KDS-41-30-2022"')
    w("      endpoint_count: 27")
    w("    - material: SRC")
    w("      selector_key: DESIGN.SRC.AIK-SRC2K.DSRC")
    w("      selector_uri: /DESIGN/SRC/AIK-SRC2K/DSRC")
    w("      response_root: DSRC")
    w('      code: "AIK-SRC2K"')
    w('      endpoint_prefix: "DESIGN.SRC.AIK-SRC2K"')
    w("      endpoint_count: 27")
    w("")

    w("# ============================================================================")
    w("# E. 运行时发现机制（Adapter 连接时执行，结果不落盘）")
    w("#")
    w("#   实测结论（2026-10-05，gen-local + civil-cloud）：")
    w("#   1. 「读当前生效的规范」—— 完全可行，零副作用：")
    w('#        GET /db/DCON   -> {"DCON":{"1":{"DGNCODE":"..."}}}')
    w('#        GET /db/DSTL   -> {"DSTL":{"1":{"DGNCODE":"..."}}}')
    w('#        GET /db/MODULE -> {"Module":0,"DgnCode":3}')
    w('#      注意：项目未设置设计时返回 {} 或 {"message":""}（空表），不是错误。')
    w("#   2. 「读全部支持集」—— API 不直接提供：")
    w("#        /info/db/DCON 返回 schema，但 DGNCODE 是 type:string，无 enum")
    w("#        裸路径 /DESIGN、/DESIGN/RC 等一律 404，无法列子节点")
    w("#      => 支持集只能来自本文件的静态枚举（手册来源）")
    w("#   3. 「验证某实例是否支持某规范」—— 可行，探测式：")
    w("#        GET /DESIGN/{material}/{code}/{probe_endpoint} -> 200 支持 / 404 不支持")
    w("#        实测：/DESIGN/RC/KDS-41-20-2022/DCO -> 200")
    w("#              GB50010-2010 / ACI318-19 / AISC360-16 / EN1992-1-1 / AIJ -> 404")
    w("#        交叉约束有效：/DESIGN/RC/KDS-41-30-2022/DCO -> 404（钢规范不能用于 RC）")
    w("#      => Adapter 用本文件的候选集做探测输入，得到该实例的可用子集")
    w("# ============================================================================")
    w("discover:")
    w("  strategy: static_candidates_plus_runtime_probe")
    w("  runtime_probe:")
    w("    method: GET")
    w("    probe_endpoint: DCO")
    w("    ok_status: 200")
    w("    not_supported_status: 404")
    w("    side_effect: none")
    w("    cache_scope: connection_session")
    w("    persist: false")
    w("  static_source_of_truth: this_file")

    out_path = repo / args.out
    out_path.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")

    cn = re.compile(r"GB|JTJ|JTG|CJJ|TB\s?\d|GBJ|JTS", re.I)
    print(f"WROTE {out_path}")
    print(f"  nx_rc            = {len(dcon)}")
    print(f"  nx_steel         = {len(dstl)}")
    print(f"  designer_module  = {sum(len(v) for v in mod.values())} "
          f"({', '.join(f'{k}:{len(v)}' for k, v in mod.items())})")
    print(f"  designer_design  = 3")
    print(f"  中国规范(DCON)   = {[c for _, _, c in dcon if cn.search(c)]}")
    print(f"  中国规范(DSTL)   = {[c for _, _, c in dstl if cn.search(c)]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
