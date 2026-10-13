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


def check_spec_values(schema: Any, value: Any, *, endpoint: str, path: str = "") -> list[str]:
    """递归比对 `value` 与 Schema 的枚举约束；返回违规描述（**不**抛）。"""
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
            node = (schema.get("properties") or {}).get(key)
            if node is None:
                continue
            problems.extend(
                check_spec_values(
                    node, child, endpoint=endpoint, path=f"{path}.{key}" if path else str(key)
                )
            )
    elif isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for index, child in enumerate(value):
                problems.extend(
                    check_spec_values(items, child, endpoint=endpoint, path=f"{path}[{index}]")
                )
    return problems


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
