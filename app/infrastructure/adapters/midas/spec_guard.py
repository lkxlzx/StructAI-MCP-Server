"""说明书枚举预检（`docs/07` §16.1 **R140**）。

⚠️ **为什么存在（事故驱动）**：P157 的旗舰链给
`DESIGN.STEEL.KDS-41-30-2022.CODE-ANAL` 发了 **`PERFORM_TYPE: "DESIGN"`** ——
而该端点的请求 Schema 只允许 **`ALL` / `ELEMS` / `SECTIONS`**（枚举写在 `oneOf[].const` 里）。
原生对这个**非法枚举**回了 `200`（它不校验），随后**弹出模态对话框并崩溃**。
⇒ 发请求**之前**必须把「值必须来自说明书」这条闸门拦在**我们这一侧**。

本模块**只**做枚举 / 常量这一件事（**不**做完整 JSON Schema 校验 —— 那会引入未声明的依赖，
且 schema 是机械生成的、可能有瑕疵；**窄**规则才既防事故又不误伤）。
"""

from __future__ import annotations

import re
from typing import Any, Final

from app.infrastructure.adapters.midas.errors import MidasValidationError

_LEAF_TYPES: Final[tuple[type, ...]] = (str, int, float, bool)


def _allowed_values(node: Any) -> tuple[Any, ...]:
    """该 Schema 节点声明的**允许取值**（`enum` 或 `oneOf[].const`；没有 ⇒ 空元组）。"""
    if not isinstance(node, dict):
        return ()
    enum = node.get("enum")
    if isinstance(enum, list) and enum:
        return tuple(enum)
    branches = node.get("oneOf")
    if isinstance(branches, list) and branches:
        consts = [
            branch.get("const")
            for branch in branches
            if isinstance(branch, dict) and "const" in branch
        ]
        if len(consts) == len(branches):
            return tuple(consts)
    return ()


def _child_nodes(schema: Any, key: str) -> list[Any]:
    """该键在 Schema 下**全部**适用的子 Schema（`properties` + 匹配的 `patternProperties`）。

    ⚠️ **R170（P178）**：原先**只**取 `properties` ⇒ 「键控对象」形状
    （`properties.Assign.patternProperties["^[0-9]+$"].properties.DGNCODE`）的枚举
    **一个都检查不到**（**21** 个文件 / **90** 个枚举节点）。JSON Schema 的语义是
    **两者并存、都适用** ⇒ 这里**两路都**返回。

    ⚠️ **非法正则**（数据瑕疵）⇒ **跳过**该条，**不**抛 —— 否则一个写坏的 pattern
    会让**所有**请求都失败（数据瑕疵不得升级成全局故障）。
    """
    if not isinstance(schema, dict):
        return []
    nodes: list[Any] = []
    direct = (schema.get("properties") or {}).get(key)
    if isinstance(direct, dict):
        nodes.append(direct)
    for pattern, node in (schema.get("patternProperties") or {}).items():
        if not isinstance(node, dict):
            continue
        try:
            matched = re.search(str(pattern), key) is not None
        except re.error:
            continue
        if matched:
            nodes.append(node)
    return nodes


def check_spec_values(schema: Any, value: Any, *, endpoint: str, path: str = "") -> list[str]:
    """递归比对 `value` 与 Schema 的枚举约束；返回违规描述（**不**抛）。

    ⚠️ **R170（P178）**：下钻走 `_child_nodes()` —— `properties` 与匹配的
    `patternProperties` **都**适用（JSON Schema 语义），且**不重复**报同一路径。
    """
    problems: list[str] = []
    allowed = _allowed_values(schema)
    if allowed and isinstance(value, _LEAF_TYPES):
        if value not in allowed:
            problems.append(f"{path or '<root>'}={value!r} 不在说明书允许值 {list(allowed)} 内")
        return problems
    if not isinstance(schema, dict):
        return problems
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            for node in _child_nodes(schema, key):
                problems.extend(check_spec_values(node, child, endpoint=endpoint, path=child_path))
    elif isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for index, child in enumerate(value):
                problems.extend(
                    check_spec_values(items, child, endpoint=endpoint, path=f"{path}[{index}]")
                )
    # 同一键同时命中 `properties` 与 `patternProperties` ⇒ 可能报出**逐字相同**的一条
    # （两份 Schema 的约束一样时）⇒ 按出现顺序去重，保留**首次**出现的描述。
    return list(dict.fromkeys(problems))


def guard_spec_values(schema: Any, body: Any, *, endpoint: str, wrapper: str = "none") -> None:
    """发请求**之前**的枚举闸门（违例 ⇒ `STRUCTAI-1200`，**不**发请求）。

    ⚠️ Schema 是**包好的**体（根键 = 信封名）⇒ 先按 `wrapper` 下钻一层再比。
    """
    if not isinstance(schema, dict) or body is None:
        return
    root = schema.get("properties") or {}
    target: Any = schema
    inner = body
    if wrapper in root:
        target = root[wrapper]
        if isinstance(body, dict) and wrapper in body:
            inner = body[wrapper]
    problems = check_spec_values(target, inner, endpoint=endpoint)
    if problems:
        raise MidasValidationError(
            "value_not_in_spec_enum",
            endpoint=endpoint,
            problems=problems[:5],
        )
