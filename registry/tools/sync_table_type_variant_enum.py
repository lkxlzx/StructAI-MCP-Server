#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
**变体端点**的 `TABLE_TYPE` 枚举收口（P168 · `docs/07` §16.1 **R161**；**R151** 的同类）。

问题（P168 普查发现，**两处独立证据一致**）
------------------------------------------
`registry/schema/**` 里有 **6** 个变体端点的 `TABLE_TYPE.enum` **不包含它自己的登记 token**
（`registry/manifest.json` 的 `table_type`）⇒ 用**登记表的 token** 调用会被 `spec_guard`（**R140**）
在**发请求之前**拦成 `STRUCTAI-1200`（**零请求**）：

| 端点 | 登记 token | 收口前的枚举 |
| --- | --- | --- |
| `POST.TABLE.FIBR_ELASTREMAIN` / `_EVENTSTEP` / `_MAXCONTRACT` / `_MEANCOMPCONTRACT` / `_YILEDSTRENGTH` | 各自的 `FIBR_*` | `['THISBEAMFORCE']`（手册那一篇的 `json_schema` 是**别的表**的拷贝） |
| `POST.TABLE.REACTIONLSURFACESPRING` | `REACTIONLSURFACESPRING` | `['REACTIONG','REACTIONL','REACTIONSURFACESPRING']`（漏了带 `L` 的那个） |

⚠️ **证据不是猜的**：上游手册里**这 6 个端点各自的文章**的**示例体**用的**正是**登记表的 token
（`P168` 的普查工具 `check_spec_enums.py` 会把这种「拦住手册自己的示例」逐条列出）。

本工具的裁决（**数据侧**，`docs/07` §16.1 **R161**）
--------------------------------------------------
枚举 = **两个来源的并集**（**只增不减**）：

* ① **登记表**：`registry/manifest.json` 里**本端点**的 `table_type`（**可复算**）；
* ② **已落盘**：当前 Schema 里已经写下的取值（护栏 —— 机械结果**丢掉**任何已落盘取值即**拒绝写入**）。

⚠️ **只碰「已有枚举、但自己的 token 不在里面」的文件**（**6** 个）；其余 **188** 个 `POST.TABLE.*`
变体**一字不改**。⚠️「**没有**枚举」的 **18** 个规格表派生文件（`products/gen_nx/post/TABLE/*`）
**不**在范围内 —— 给它们**新增**枚举是**收紧**闸门，那是**另一件事**（须单独裁决）。
⚠️ `common/post/TABLE.json`（**通用入口**）由 `sync_table_type_enum.py`（**R160**）拥有，
**本工具不碰**。

⚠️ **R140 的保护照旧**：伪 token（登记表里没有）**仍然**被拦在**发请求之前**（零请求）；
`app/**` **未**因本工具而改（枚举是**数据**）。

幂等 / 用法
-----------
只拥有目标文件 `…Argument.properties.TABLE_TYPE` 的 **`enum`** 与 **`description`** 两个键
（其余内容**逐字节**透传）。

    python registry/tools/sync_table_type_variant_enum.py            # 预演（只打印差异）
    python registry/tools/sync_table_type_variant_enum.py --write     # 写回
    python registry/tools/sync_table_type_variant_enum.py --check     # 断言「已落盘 == 机械结果」

只依赖标准库（数据侧工具不引入新依赖）。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Final

MANIFEST_FILENAME: Final[str] = "manifest.json"
TABLE_TYPE_FIELD: Final[str] = "TABLE_TYPE"
"""目标字段名。"""

STRUCTURAL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "properties",
        "patternProperties",
        "items",
        "oneOf",
        "anyOf",
        "allOf",
        "additionalProperties",
        "$defs",
        "definitions",
        "type",
        "required",
        "$schema",
        "title",
        "description",
    }
)
"""非字段名的键（用于识别**包装根键**）。"""

VARIANT_DESCRIPTION: Final[str] = (
    "结果表类型（TABLE_TYPE）。取值 = **两个可复算来源的并集**："
    "① `registry/manifest.json` 里**本端点**的 `table_type`（登记表）；② 已落盘枚举（**只增不减**）。"
    "由 `registry/tools/sync_table_type_variant_enum.py` 机械派生"
    "（`--check` 断言已落盘 == 机械结果）；依据 = `docs/07` §16.1 R161。"
)
"""⚠️ **只**给「本工具的收口对象」写这份说明（其余变体文件的 `description` **一字不动**）。"""


def manifest_entries(repo: pathlib.Path) -> list[dict[str, Any]]:
    """登记表的端点条目（`registry/manifest.json` 的 `endpoints`）。"""
    document = json.loads((repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    return list(document["endpoints"])


def _table_type_node(document: dict[str, Any]) -> dict[str, Any] | None:
    """取目标文件里 `TABLE_TYPE` 的 Schema 节点（**取不到 ⇒ `None`**，**不**猜路径）。

    ⚠️ `registry/schema/**` 的文件有**两种**根形态（**R161** 的普查）：
    `{"properties": {"Argument": …}}`（**228** 个）与 `{"TABLE": {"properties": {"Argument": …}}}`
    （**393** 个，**根键 = 包装键**）⇒ 两种都认；**不**做「猜第几层」的模糊匹配。
    """
    schema = document.get("schema")
    if not isinstance(schema, dict):
        return None
    node: Any = schema
    if not isinstance(node.get("properties"), dict):
        roots = [key for key in schema if key not in STRUCTURAL_KEYS]
        if len(roots) != 1:
            return None
        node = schema[roots[0]]
    for segment in ("properties", "Argument", "properties", TABLE_TYPE_FIELD):
        if not isinstance(node, dict) or segment not in node:
            return None
        node = node[segment]
    return node if isinstance(node, dict) else None


def on_disk_enum(path: pathlib.Path) -> list[str] | None:
    """已落盘的枚举（**只读**；没有 `TABLE_TYPE` 节点 / 没有枚举 ⇒ `None`）。"""
    if not path.is_file():
        return None
    node = _table_type_node(json.loads(path.read_text(encoding="utf-8")))
    if node is None:
        return None
    enum = node.get("enum")
    return [str(item) for item in enum] if isinstance(enum, list) else []


def targets(repo: pathlib.Path) -> list[dict[str, Any]]:
    """收口对象 = **已有 `TABLE_TYPE.enum`，但登记 token 不在里面**的端点（**逐条**可复算）。

    ⚠️ **只**收「**已有枚举**但漏了自己的 token」的（= P168 普查的标志项）；
    「**没有**枚举」的文件（`products/gen_nx/post/TABLE/*` 里由规格表派生的 **18** 个）**不**在范围内 ——
    给它们**新增**枚举是**收紧**闸门，那是另一件事（须单独裁决）。
    """
    found: list[dict[str, Any]] = []
    for entry in manifest_entries(repo):
        token = str(entry.get("table_type") or "")
        schema = str(entry.get("schema") or "")
        if not token or not schema:
            continue
        path = repo / "registry" / schema
        disk = on_disk_enum(path)
        if not disk or token in disk:
            continue
        found.append(
            {
                "key": str(entry.get("key") or ""),
                "token": token,
                "file": schema,
                "on_disk": sorted(set(disk)),
                "expected": sorted(set(disk) | {token}),
            }
        )
    return found


def expected_enum(repo: pathlib.Path, key: str) -> list[str]:
    """机械结果：登记 token ∪ 已落盘枚举（排序、去重、确定性）。"""
    for item in targets(repo):
        if item["key"] == key:
            return list(item["expected"])
    for entry in manifest_entries(repo):
        if str(entry.get("key") or "") == key:
            disk = on_disk_enum(repo / "registry" / str(entry.get("schema") or ""))
            return sorted(set(disk or ()))
    raise SystemExit(f"❌ 登记表里没有端点 {key!r}")


def is_applied(repo: pathlib.Path) -> bool:
    """收口是否已落盘（`check_spec_enums.py` 的**回归**判据：已收口项不可回退）。"""
    return not targets(repo)


def build_document(repo: pathlib.Path, item: dict[str, Any]) -> dict[str, Any]:
    """装配目标文件（其余键**逐字节**透传；只改 `TABLE_TYPE` 的 `enum` / `description`）。"""
    path = repo / "registry" / item["file"]
    document = json.loads(path.read_text(encoding="utf-8"))
    node = _table_type_node(document)
    if node is None:
        raise SystemExit(f"❌ {item['file']} 里找不到 `TABLE_TYPE` 节点")
    node["enum"] = list(item["expected"])
    node["description"] = VARIANT_DESCRIPTION
    return document


def render(document: dict[str, Any]) -> str:
    """落盘文本（与既有 `registry/schema/**` 的写法一致：`indent=2` + 结尾换行）。"""
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="变体端点的 TABLE_TYPE 枚举收口（R161）")
    parser.add_argument("--repo", default=".", help="仓库根目录（默认当前目录）")
    parser.add_argument("--write", action="store_true", help="实际写回（默认只预演）")
    parser.add_argument("--check", action="store_true", help="断言已落盘 == 机械结果（CI）")
    args = parser.parse_args(argv)

    repo = pathlib.Path(args.repo).resolve()
    items = targets(repo)
    print(f"收口对象（**已有枚举**但登记 token 不在里面）= **{len(items)}** 个端点")
    for item in items:
        print(
            f"  {item['key']}  token={item['token']!r}  "
            f"{len(item['on_disk'])} → {len(item['expected'])} 个取值  （{item['file']}）"
        )

    changed: list[str] = []
    for item in items:
        path = repo / "registry" / item["file"]
        text = render(build_document(repo, item))
        if path.read_text(encoding="utf-8") == text:
            continue
        changed.append(item["file"])
        if args.write:
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"WROTE registry/{item['file']}")

    if not items:
        print("✅ 已落盘 == 机械结果（没有需要收口的变体端点）")
        return 0
    if not changed:
        print(f"✅ {len(items)} 个文件与机械结果一致（无差异）")
        return 0
    print(f"  需写入 {len(changed)} 个文件（**只增不减**：登记 token 追加进枚举）")
    if args.check:
        print("❌ --check：已落盘内容与机械结果不一致")
        return 1
    if not args.write:
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
