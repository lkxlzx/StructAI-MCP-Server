#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`POST.TEXT` 的**请求键更正** + `TABLE_TYPE`（实为 `TEXT_TYPE`）枚举收口
（P169 · `docs/07` §16.1 **R162**；**R151** 的同类 + **R151** 的教训）。

问题（两件，一次真机测量同时裁决）
----------------------------------
**① 请求键错了**：上游手册的**示例体**用 `TEXT_TYPE`（**29 / 29** 条），
而手册 `json_schema`（**12** 篇）与**我们的 Schema** 都用 `TABLE_TYPE`。实测：

| 键 | `POST /POST/TEXT` 的答复 |
| --- | --- |
| `TEXT_TYPE` | 合法值 ⇒ **`200`** ∧ **真的产出文件**；**伪**值 ⇒ `400 second query is wrong`（**值**错） |
| `TABLE_TYPE` | **任何**取值 ⇒ `400 Wrong Field`（**键**错） |

⇒ 按**实测**（**铁律 ⓪**）裁决：**契约键 = `TEXT_TYPE`**；`TABLE_TYPE` 是**上游 `json_schema` 的笔误**
（与手册**自己的示例体**矛盾）⇒ 登记**勘误**。

**② 枚举来源太窄**（**R151** 的形态）：我们的枚举只有 **3** 个取值（来自**一篇文章**），
而同一 URI 的 **12** 篇文章在 `json_schema` 里声明了 **29** 个（`TH_*` 20 + `PO_*` 9）。

本工具的裁决（**数据侧**）
--------------------------
* **请求键**：`Argument.properties` 的 `TABLE_TYPE` → **`TEXT_TYPE`**（**重命名**；
  ⚠️ 这不是「枚举收紧」—— `spec_guard` **只**校验**已声明**的字段，
  未声明字段**不**会被拦 ⇒ 重命名**不会**拦任何调用，只是把闸门**挂到正确的键上**）。
* **枚举**：取值 = **两个来源的并集**（**只增不减**）：
  ① **手册声明** = 同一 URI（`post/TEXT`）的**全部**文章 `json_schema` 里
     `TABLE_TYPE.enum` 的并集（**29** 个，逐篇可回溯）；
  ② **已落盘** = 当前 Schema 已写下的取值（护栏 —— 机械结果**丢掉**任何已落盘取值即**拒绝写入**）。
* ⚠️ **真机接受集**（`registry/live/post_text_probe.json` 的 `accepted_types`）**只**用于
  **核对**（`--check` 断言「被接受的取值都在枚举里」），**不**用于**收窄**枚举 ——
  未被接受的取值可能是**本模型无该数据**，**不**是「取值非法」（实测：`STEP` 是必需字段，
  缺它一律 `Wrong Field`，与取值无关）。

⚠️ **R140 的保护照旧**：伪取值（两个来源都不在）**仍**被拦在**发请求之前**（零请求）。
⚠️ `app/**` 一行未改（键与枚举都是**数据**）。

用法
----
    python registry/tools/sync_post_text_enum.py            # 预演（只打印差异）
    python registry/tools/sync_post_text_enum.py --write     # 写回
    python registry/tools/sync_post_text_enum.py --check     # 断言「已落盘 == 机械结果」
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Final

MANUAL_FILENAMES: Final[tuple[str, ...]] = (
    "MIDAS_API_Online_Manual_Gen_NX_v1.0.json",
    "MIDAS_API_Online_Manual_数据_v1.0.json",
)
"""两份上游手册（与 `check_spec_enums.py` 的**同一**口径）。"""

PROBE_FILENAME: Final[str] = "post_text_probe.json"
"""真机裁决证据（**只**用于核对「被接受的取值都在枚举里」）。"""

TARGET_RELATIVE: Final[str] = "schema/common/post/TEXT.json"
URI_SUFFIX: Final[str] = "text"
REQUEST_KEY: Final[str] = "TEXT_TYPE"
"""**实测**的契约键（见模块头部的真机裁决表）。"""

LEGACY_KEY: Final[str] = "TABLE_TYPE"
"""手册 `json_schema` / 我们 Schema 原先用的键（**实测**为**键**错 ⇒ 勘误）。"""

TEXT_TYPE_DESCRIPTION: Final[str] = (
    "文本导出类型（`TEXT_TYPE`，**变体选择子**）。⚠️ **P169 真机裁决**：契约键是 `TEXT_TYPE`"
    "（手册**示例体** 29/29 都用它；合法值原生 `200` 并**真的产出文件**、伪值 ⇒ "
    "`400 second query is wrong`），而 `TABLE_TYPE`（手册 `json_schema` 与**我们的旧 Schema**）"
    "**任何**取值都回 `400 Wrong Field`（**键**错）⇒ 上游 `json_schema` 是**笔误**，已登记勘误。"
    "取值 = **两个可复算来源的并集**：① 同一 URI（`post/TEXT`）的**全部**文章 `json_schema` 里"
    "声明的取值（**29** 个）；② 已落盘枚举（**只增不减**）。"
    "由 `registry/tools/sync_post_text_enum.py` 机械派生（`--check` 断言已落盘 == 机械结果）；"
    "依据 = `docs/07` §16.1 R162。"
)


def manifest_entries(repo: pathlib.Path) -> list[dict[str, Any]]:
    """登记表的端点条目。"""
    document = json.loads((repo / "registry" / "manifest.json").read_text(encoding="utf-8"))
    return list(document["endpoints"])


def _target_file(repo: pathlib.Path) -> pathlib.Path:
    """目标文件路径（登记表驱动）。"""
    for entry in manifest_entries(repo):
        if str(entry.get("key") or "") == "POST.TEXT":
            return repo / "registry" / str(entry["schema"])
    raise SystemExit("❌ 登记表里没有端点 POST.TEXT")


def manual_types(repo: pathlib.Path) -> list[str]:
    """来源①：同一 URI 的**全部**文章 `json_schema` 里 `TABLE_TYPE.enum` 的并集（**逐篇**可回溯）。"""
    found: set[str] = set()
    for filename in MANUAL_FILENAMES:
        path = repo / filename
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        for entry in document.get("endpoints") or []:
            uri = str(entry.get("input_uri") or "")
            if uri.split("/")[-1].lower() != URI_SUFFIX:
                continue
            raw = entry.get("json_schema")
            if not raw:
                continue
            schema = raw if isinstance(raw, dict) else json.loads(str(raw))
            for value in _table_type_enums(schema):
                found.add(value)
    if not found:
        raise SystemExit(f"❌ 手册里没有任何 `{URI_SUFFIX}` 文章的 `TABLE_TYPE.enum`")
    return sorted(found)


def _table_type_enums(node: Any) -> list[str]:
    """递归收集 `TABLE_TYPE.enum`（**任一**层级；两种根形态都认）。"""
    values: list[str] = []
    if isinstance(node, dict):
        for key, child in node.items():
            if key == LEGACY_KEY and isinstance(child, dict):
                enum = child.get("enum")
                if isinstance(enum, list):
                    values.extend(str(item) for item in enum)
            values.extend(_table_type_enums(child))
    elif isinstance(node, list):
        for child in node:
            values.extend(_table_type_enums(child))
    return values


def on_disk_enum(repo: pathlib.Path) -> list[str]:
    """来源②：已落盘的枚举（**只读**；节点 / 枚举缺失 ⇒ 空）。"""
    path = _target_file(repo)
    if not path.is_file():
        return []
    document = json.loads(path.read_text(encoding="utf-8"))
    properties = _argument_properties(document)
    # ⚠️ **重命名后**取 `TEXT_TYPE`；**重命名前**取旧键（同一个函数两种状态都能读 ⇒ `--check` 可判别）。
    node = properties.get(REQUEST_KEY) or properties.get(LEGACY_KEY)
    enum = (node or {}).get("enum") if isinstance(node, dict) else None
    return [str(item) for item in enum] if isinstance(enum, list) else []


def accepted_types(repo: pathlib.Path) -> list[str]:
    """真机**接受**的取值（**只**用于核对，**不**用于收窄枚举）。"""
    path = repo / "registry" / "live" / PROBE_FILENAME
    if not path.is_file():
        return []
    document = json.loads(path.read_text(encoding="utf-8"))
    return [str(item) for item in document.get("accepted_types") or []]


def expected_enum(repo: pathlib.Path) -> list[str]:
    """机械结果：来源① ∪ 来源②（**已落盘**，护栏）—— 排序、去重、确定性。"""
    return sorted(set(manual_types(repo)) | set(on_disk_enum(repo)))


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


def _argument_properties(document: dict[str, Any]) -> dict[str, Any]:
    """取 `properties.Argument.properties`（**不**猜路径）。"""
    node: Any = _unwrap(document)
    for segment in ("properties", "Argument", "properties"):
        if not isinstance(node, dict) or segment not in node:
            raise SystemExit(f"❌ {TARGET_RELATIVE} 里找不到 `{segment}`（数据文件结构变了？）")
        node = node[segment]
    if not isinstance(node, dict):
        raise SystemExit(f"❌ {TARGET_RELATIVE} 的 `Argument.properties` 不是对象")
    return node


def build_document(repo: pathlib.Path) -> dict[str, Any]:
    """装配目标文件（其余键**逐字节**透传；只改 `Argument.properties` 的这一个键）。

    ⚠️ **键重命名**：`TABLE_TYPE` → `TEXT_TYPE`（**实测**裁决）。重命名时**保留**原键的
    `type`（`string`），**不**臆造别的约束。
    """
    path = _target_file(repo)
    document = json.loads(path.read_text(encoding="utf-8"))
    properties = _argument_properties(document)
    legacy = properties.pop(LEGACY_KEY, None)
    node: dict[str, Any] = {"type": "string"}
    if isinstance(legacy, dict) and isinstance(legacy.get("type"), str):
        node["type"] = legacy["type"]
    node["enum"] = expected_enum(repo)
    node["description"] = TEXT_TYPE_DESCRIPTION
    properties[REQUEST_KEY] = node
    return document


def is_applied(repo: pathlib.Path) -> bool:
    """收口是否已落盘（**回归**判据：键已重命名 ∧ 枚举无丢失）。"""
    path = _target_file(repo)
    if not path.is_file():
        return False
    document = json.loads(path.read_text(encoding="utf-8"))
    properties = _argument_properties(document)
    if REQUEST_KEY not in properties or LEGACY_KEY in properties:
        return False
    enum = properties[REQUEST_KEY].get("enum")
    return isinstance(enum, list) and set(expected_enum(repo)) <= {str(item) for item in enum}


def render(document: dict[str, Any]) -> str:
    """落盘文本（与既有 `registry/schema/**` 的写法一致：`indent=2` + 结尾换行）。"""
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="POST.TEXT 的键更正 + 枚举收口（R162）")
    parser.add_argument("--repo", default=".", help="仓库根目录（默认当前目录）")
    parser.add_argument("--write", action="store_true", help="实际写回（默认只预演）")
    parser.add_argument("--check", action="store_true", help="断言已落盘 == 机械结果（CI）")
    args = parser.parse_args(argv)

    repo = pathlib.Path(args.repo).resolve()
    path = _target_file(repo)
    manual = manual_types(repo)
    disk = on_disk_enum(repo)
    accepted = accepted_types(repo)
    enum = expected_enum(repo)
    print(f"来源① 手册声明（同一 URI 的全部文章 `{LEGACY_KEY}.enum` 并集）= {len(manual)} 个取值")
    print(f"来源② 已落盘 = {len(disk)} 个取值 ⇒ 并集 = {len(enum)} 个取值")
    print(f"请求键：`{LEGACY_KEY}` → **`{REQUEST_KEY}`**（**实测**裁决：前者任何取值都 `Wrong Field`）")
    if accepted:
        missing = sorted(set(accepted) - set(enum))
        print(f"真机**接受**的取值 = {len(accepted)} 个 ⇒ **全部**在枚举里：{not missing}")
        if missing:
            print(f"❌ 被原生接受的取值**不在**枚举里：{missing} ⇒ 收口不完整")
            return 1

    lost = sorted(set(disk) - set(enum))
    if lost:
        print(f"❌ 机械结果**丢掉**了已落盘的 {len(lost)} 个取值：{lost[:10]} ⇒ **拒绝写入**（只增不减）")
        return 1

    current = path.read_text(encoding="utf-8")
    text = render(build_document(repo))
    if current == text:
        print(f"✅ {TARGET_RELATIVE} 与机械结果一致（无差异）")
        return 0
    print(f"  需写入 {TARGET_RELATIVE}")
    if args.check:
        print("❌ --check：已落盘内容与机械结果不一致")
        return 1
    if args.write:
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"WROTE registry/{TARGET_RELATIVE}")
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
