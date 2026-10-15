#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`OPE.LCOM-SRC` 的 `DGNCODE` 枚举收口（P169 · `docs/07` §16.1 **R162**；**R151** 的同类）。

问题
----
`OPE.LCOM-SRC` 的枚举只有 `['KDS 41 SRC : 2022']`（**一篇文章**的 `json_schema` 声明），
而同 URI 的**另一篇**文章的**示例体**用 `AIK-SRC2K`（`MIDAS_API_Online_Manual_Gen_NX_v1.0.json#519`）
⇒ 那是 **R151 的形态**（来源太窄），也是普查的 `example_blocked` 逐条列出的项。

**P169 真机裁决**（**用户已授权**一次**写路径**测量；证据 = `registry/live/lcom_dgncode_probe.json`）
------------------------------------------------------------------------------------------------
`POST /OPE/LCOM-SRC {"Argument": {"OPTION": "ADD", "DGNCODE": <码>}}` 的答复分**三档**：

| 码 | 原生答复 | 档 |
| --- | --- | --- |
| `KDS 41 SRC : 2022`（**声明**的合法值） | `400 Set_DefaultLoadComb failed; check CheckLcom history …` | **业务级**（取值**通过**了规范校验、走到**下游**） |
| `AIK-SRC2K`（**示例体**的值） | **同一条**业务级文案 | **业务级** ⇒ **合法** |
| `NONSENSE-CODE`（**伪**值） | `400 Unknown Error` | **取值非法** |

⇒ `AIK-SRC2K` 与**声明**的合法值**同档**、与**伪**值**不同档** ⇒ **合法** ⇒ 按实测**收口**。

本工具的裁决（**数据侧**）
--------------------------
枚举 = **两个来源的并集**（**只增不减**）：

* ① **登记 / 手册声明**：`registry/schema/products/gen_nx/ope/LCOM-SRC.json` 里**已落盘**的取值
  （= 上游那一篇文章的 `json_schema` 声明，**护栏**）；
* ② **真机实测合法**：`registry/live/lcom_dgncode_probe.json` 里被判为**合法**的待裁决候选
  （与声明值**同档**、与伪值**不同档**）。

⚠️ **只碰** `registry/schema/products/gen_nx/ope/LCOM-SRC.json` 的
`Argument.properties.DGNCODE.enum` / `description` 两个键。
⚠️ **不碰** `OPE.LCOM-GEN`：本 build 对它的**任何**取值都回 `Wrong Field`（形状 / 键错）
⇒ **不可判别**（台账里**如实留缺**）。
⚠️ **R140** 的保护照旧：伪取值**仍**被拦在**发请求之前**（零请求）；`app/**` 一行未改。

用法
----
    python registry/tools/sync_lcom_src_dgncode_enum.py            # 预演
    python registry/tools/sync_lcom_src_dgncode_enum.py --write     # 写回
    python registry/tools/sync_lcom_src_dgncode_enum.py --check     # 断言「已落盘 == 机械结果」
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Final

PROBE_FILENAME: Final[str] = "lcom_dgncode_probe.json"
"""真机裁决证据（**不含**凭据 / 响应原文）。"""

TARGET_KEY: Final[str] = "OPE.LCOM-SRC"
FIELD: Final[str] = "DGNCODE"

DGNCODE_DESCRIPTION: Final[str] = (
    "设计规范码（`DGNCODE`）。取值 = **两个可复算来源的并集**：① 已落盘（上游那一篇文章的 "
    "`json_schema` 声明，**只增不减**）；② **P169 真机实测合法**的取值"
    "（`registry/live/lcom_dgncode_probe.json`：与**声明**的合法值**同档**（业务级 "
    "`Set_DefaultLoadComb failed`）、与**伪**值**不同档**（`Unknown Error`））。"
    "⚠️ `AIK-SRC2K` 原先**只在手册示例体**里（同一 URI 的**另一篇**文章）"
    "⇒ 按 **R151** 的教训**不**直接采信，**实测通过**后才收口。"
    "由 `registry/tools/sync_lcom_src_dgncode_enum.py` 机械派生（`--check` 断言已落盘 == 机械结果）；"
    "依据 = `docs/07` §16.1 R162。"
)


def _target_file(repo: pathlib.Path) -> pathlib.Path:
    """目标文件路径（登记表驱动）。"""
    document = json.loads((repo / "registry" / "manifest.json").read_text(encoding="utf-8"))
    for entry in document["endpoints"]:
        if str(entry.get("key") or "") == TARGET_KEY:
            return repo / "registry" / str(entry["schema"])
    raise SystemExit(f"❌ 登记表里没有端点 {TARGET_KEY}")


def _unwrap(document: dict[str, Any]) -> dict[str, Any] | None:
    """剥掉**包装根键**（两种根形态都认；**不**猜路径）。"""
    schema = document.get("schema")
    if not isinstance(schema, dict):
        return None
    if isinstance(schema.get("properties"), dict):
        return schema
    roots = [key for key in schema if key not in {"$schema", "title", "type"}]
    if len(roots) != 1 or not isinstance(schema[roots[0]], dict):
        return None
    return schema[roots[0]]


def _dgncode_node(document: dict[str, Any]) -> dict[str, Any] | None:
    """取 `Argument.properties.DGNCODE` 的节点（**不**猜路径）。"""
    node: Any = _unwrap(document)
    for segment in ("properties", "Argument", "properties", FIELD):
        if not isinstance(node, dict) or segment not in node:
            return None
        node = node[segment]
    return node if isinstance(node, dict) else None


def on_disk_enum(repo: pathlib.Path) -> list[str]:
    """来源①：已落盘的枚举（**只读**；缺失 ⇒ 空）。"""
    path = _target_file(repo)
    if not path.is_file():
        return []
    node = _dgncode_node(json.loads(path.read_text(encoding="utf-8")))
    enum = (node or {}).get("enum")
    return [str(item) for item in enum] if isinstance(enum, list) else []


def measured_legal(repo: pathlib.Path) -> list[str]:
    """来源②：真机实测**合法**的取值（与声明值**同档**、与伪值**不同档**）。"""
    path = repo / "registry" / "live" / PROBE_FILENAME
    if not path.is_file():
        return []
    document = json.loads(path.read_text(encoding="utf-8"))
    verdict = (document.get("verdicts") or {}).get(TARGET_KEY) or {}
    if not (verdict.get("decidable") and verdict.get("pending_legitimate")):
        return []
    legal: list[str] = []
    for row in document.get("rows") or []:
        if str(row.get("key") or "") != TARGET_KEY:
            continue
        legal.extend(str(item["code"]) for item in row.get("pending_rows") or [])
    return sorted(set(legal))


def expected_enum(repo: pathlib.Path) -> list[str]:
    """机械结果：来源① ∪ 来源②（**只增不减**）—— 排序、去重、确定性。"""
    return sorted(set(on_disk_enum(repo)) | set(measured_legal(repo)))


def is_applied(repo: pathlib.Path) -> bool:
    """收口是否已落盘（**回归**判据：机械结果 ⊆ 已落盘）。"""
    return set(expected_enum(repo)) <= set(on_disk_enum(repo))


def build_document(repo: pathlib.Path) -> dict[str, Any]:
    """装配目标文件（其余键**逐字节**透传；只改 `DGNCODE` 的 `enum` / `description`）。"""
    path = _target_file(repo)
    document = json.loads(path.read_text(encoding="utf-8"))
    node = _dgncode_node(document)
    if node is None:
        raise SystemExit(f"❌ {TARGET_KEY} 的 Schema 里找不到 `Argument.properties.{FIELD}`")
    node["enum"] = expected_enum(repo)
    node["description"] = DGNCODE_DESCRIPTION
    return document


def render(document: dict[str, Any]) -> str:
    """落盘文本（与既有 `registry/schema/**` 的写法一致：`indent=2` + 结尾换行）。"""
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OPE.LCOM-SRC 的 DGNCODE 枚举收口（R162）")
    parser.add_argument("--repo", default=".", help="仓库根目录（默认当前目录）")
    parser.add_argument("--write", action="store_true", help="实际写回（默认只预演）")
    parser.add_argument("--check", action="store_true", help="断言已落盘 == 机械结果（CI）")
    args = parser.parse_args(argv)

    repo = pathlib.Path(args.repo).resolve()
    path = _target_file(repo)
    disk = on_disk_enum(repo)
    measured = measured_legal(repo)
    enum = expected_enum(repo)
    print(f"来源① 已落盘（上游那一篇文章的声明）= {disk}")
    print(f"来源② 真机实测合法（P169 的写路径裁决）= {measured}")
    print(f"并集 = {enum}")
    if not measured:
        print("⚠️ 没有实测合法的候选取值 ⇒ 机械结果 == 已落盘（**不**收口）")
    lost = sorted(set(disk) - set(enum))
    if lost:
        print(f"❌ 机械结果**丢掉**了已落盘的取值 {lost} ⇒ **拒绝写入**（只增不减）")
        return 1

    current = path.read_text(encoding="utf-8")
    text = render(build_document(repo))
    if current == text:
        print(f"✅ {path.relative_to(repo)} 与机械结果一致（无差异）")
        return 0
    print(f"  需写入 {path.relative_to(repo)}")
    if args.check:
        print("❌ --check：已落盘内容与机械结果不一致")
        return 1
    if args.write:
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"WROTE {path.relative_to(repo)}")
    else:
        print("（预演模式；加 --write 才会写回）")
    return 0


if __name__ == "__main__":
    # Windows 控制台默认 cp949/cp936：本工具会打印中文/符号，不重设编码会 UnicodeEncodeError。
    # ⚠️ 必须在 `__main__` 块内：测试用 `exec_module()` 装载本模块，模块级调用会改写
    #    **pytest 的捕获流**，破坏其后所有用例的 capture。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
