"""P178 / **R170 收口**：`spec_guard` 必须认识 `patternProperties`（**核心闸门改动**）。

背景（P177 实测）
-----------------
**R161**（P168）修过**一处**盲区：闸门原先按 `schema["properties"][包装键]` 下钻，
对「根键就是包装键」的 **393** 个文件**一个字段都不检查**；改用 `effective_schema()`
（`unwrap_schema()`）后**可下钻 121 → 225 · 盲区 104 → 0**。

⚠️ **但** `unwrap_schema()` **只**剥**根**包装键，**不**处理**条目级**的 `patternProperties` ——
而「键控对象」形状的 Schema 正是这样声明条目字段的：

```
properties.Assign.patternProperties["^[0-9]+$"].properties.DGNCODE.enum
```

`check_spec_values()` 原先**只**走 `properties` 与 `items` ⇒ 这些枚举**全部**在视野之外：
**21** 个文件 / **90** 个枚举节点 **100% 盲区**。

判定口径（**R157** 的方法学：说「修好了」前先证明**仪器有效**）
------------------------------------------------------------
1. **修前**伪值**不拦**（P177 已实测，本文件以「对照端点」形式保留这条事实）；
2. **修后**伪值**拦**；
3. **合法值仍放行**（⚠️ 缺这条就分不清「修好了」与「把闸门焊死了」）；
4. `properties` 形状的端点（`OPE.LCOM-CONC`）**零回归**；
5. **21** 个受影响文件的枚举**全部**变得可检查。

⚠️ **JSON Schema 语义**：`properties` 与 `patternProperties` **并存**，两者命中时**都**要查。
⚠️ **非法正则不崩**：`patternProperties` 的键是正则；写坏了只能**跳过**该条，
**不**得让闸门抛异常（那会把「数据瑕疵」变成「所有请求都失败」）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Final

import pytest

from app.infrastructure.adapters.midas.errors import MidasValidationError
from app.infrastructure.adapters.midas.spec_guard import check_spec_values, guard_spec_values

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
SCHEMA_ROOT: Final[Path] = REPO_ROOT / "registry" / "schema"

BOGUS: Final[str] = "TOTALLY-BOGUS-DESIGN-CODE"
LEGIT_KDS: Final[str] = "KDS 41 20 : 2022"
LEGIT_GB: Final[str] = "GB/T50010-10"


def _schema(relative: str) -> dict[str, Any]:
    """读 `registry/schema/**` 的 `schema` 体（文件外层还有 `key` / `uri` / `source`）。"""
    document = json.loads((SCHEMA_ROOT / relative).read_text(encoding="utf-8"))
    return document["schema"]


# ===== 1. 核心判据：伪值**现在**被拦 =====


@pytest.mark.parametrize(
    ("relative", "endpoint", "wrapper"),
    [
        ("design/rc/DRC.json", "DESIGN.RC.DRC", "Assign"),
        ("design/steel/DSTL.json", "DESIGN.STEEL.DSTL", "Assign"),
    ],
)
def test_p178_a_bogus_value_is_now_blocked_through_pattern_properties(
    relative: str, endpoint: str, wrapper: str
) -> None:
    """门槛：**修后**伪值被拦 —— 这是 R170 的**定义性判据**。

    ⚠️ 修前这条是**绿的**（`problems == []`）；现在必须**红**（抛 `MidasValidationError`）。
    """
    schema = _schema(relative)
    with pytest.raises(MidasValidationError) as error:
        guard_spec_values(
            schema, {wrapper: {"1": {"DGNCODE": BOGUS}}}, endpoint=endpoint, wrapper=wrapper
        )
    assert "value_not_in_spec_enum" in str(error.value) or "spec_enum" in str(error.value)


@pytest.mark.parametrize(
    ("relative", "endpoint", "wrapper", "code"),
    [
        ("design/rc/DRC.json", "DESIGN.RC.DRC", "Assign", LEGIT_KDS),
        # ⚠️ P176 实测：`GB/T50010-10` 在 `DESIGN.CONCRETE` 上**真的**能跑出设计结果
        ("design/rc/DRC.json", "DESIGN.RC.DRC", "Assign", LEGIT_GB),
        ("design/steel/DSTL.json", "DESIGN.STEEL.DSTL", "Assign", "KDS 41 30 : 2022"),
        ("design/steel/DSTL.json", "DESIGN.STEEL.DSTL", "Assign", "AISC(16th)-LRFD22"),
    ],
)
def test_p178_a_legit_value_still_passes(
    relative: str, endpoint: str, wrapper: str, code: str
) -> None:
    """门槛（**R157**）：**合法值仍放行** —— 证明闸门**有效**，不是「焊死了」。

    ⚠️ 没有这条，「伪值被拦」与「闸门把**所有**取值都拦了」**无法区分**。
    """
    guard_spec_values(
        _schema(relative), {wrapper: {"1": {"DGNCODE": code}}}, endpoint=endpoint, wrapper=wrapper
    )


# ===== 2. 零回归：`properties` 形状的端点 =====


def test_p178_the_properties_shaped_endpoint_has_zero_regression() -> None:
    """门槛：`OPE.LCOM-CONC`（枚举在 `properties` 下）**行为不变** —— 合法过、伪值拦。"""
    schema = _schema("products/gen_nx/ope/LCOM-CONC.json")
    guard_spec_values(
        schema, {"Argument": {"DGNCODE": LEGIT_KDS}}, endpoint="OPE.LCOM-CONC", wrapper="Argument"
    )
    with pytest.raises(MidasValidationError):
        guard_spec_values(
            schema, {"Argument": {"DGNCODE": BOGUS}}, endpoint="OPE.LCOM-CONC", wrapper="Argument"
        )


# ===== 3. 语义细节：`properties` 与 `patternProperties` **并存** =====


def test_p178_properties_and_pattern_properties_are_both_checked() -> None:
    """门槛：两者**并存**时**都**要查（JSON Schema 语义）。

    ⚠️ 只查 `patternProperties` 会**漏掉** `properties` 里的约束；反过来就是本 bug。
    """
    schema = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["A", "B"]},
        },
        "patternProperties": {
            "^[0-9]+$": {
                "type": "object",
                "properties": {"code": {"type": "string", "enum": ["X"]}},
            }
        },
    }
    # 两侧**都**合法 ⇒ 通过
    assert check_spec_values(schema, {"kind": "A", "1": {"code": "X"}}, endpoint="t") == []
    # `properties` 侧违规
    assert check_spec_values(schema, {"kind": "Z"}, endpoint="t")
    # `patternProperties` 侧违规
    assert check_spec_values(schema, {"1": {"code": "Y"}}, endpoint="t")


def test_p178_a_key_matching_both_is_checked_against_both_without_duplicates() -> None:
    """门槛：同时命中 `properties` 与 `patternProperties` ⇒ **都**查，且**不重复报同一条**。"""
    schema = {
        "type": "object",
        "properties": {"1": {"type": "object", "properties": {"a": {"enum": ["ok"]}}}},
        "patternProperties": {
            "^[0-9]+$": {"type": "object", "properties": {"a": {"enum": ["ok"]}}},
        },
    }
    problems = check_spec_values(schema, {"1": {"a": "bad"}}, endpoint="t")
    # 两侧都违规，但路径相同 ⇒ 去重后只报 **1** 条
    assert len(problems) == 1, problems


def test_p178_non_matching_keys_are_not_checked_by_the_pattern() -> None:
    """门槛：**不**匹配正则的键 ⇒ 该 `patternProperties` 分支**不**适用（不误报）。"""
    schema = {
        "type": "object",
        "patternProperties": {
            "^[0-9]+$": {"type": "object", "properties": {"code": {"enum": ["X"]}}},
        },
    }
    # `abc` 不匹配 `^[0-9]+$` ⇒ 即使 `code` 非法也**不**由这条约束判定
    assert check_spec_values(schema, {"abc": {"code": "Y"}}, endpoint="t") == []


def test_p178_an_invalid_pattern_is_skipped_without_crashing() -> None:
    """门槛：`patternProperties` 的键是**正则**；写坏了 ⇒ **跳过**该条，**不**抛异常。

    ⚠️ 数据瑕疵**不**得升级成「所有请求都失败」。
    """
    schema = {
        "type": "object",
        "patternProperties": {"[": {"properties": {"code": {"enum": ["X"]}}}},
    }
    assert check_spec_values(schema, {"1": {"code": "Y"}}, endpoint="t") == []


# ===== 4. 规模：受影响文件的枚举**全部**变得可检查 =====


def test_p178_every_enum_under_pattern_properties_is_now_enforced() -> None:
    """门槛：**每一条** `patternProperties` 下的枚举约束都**真的**在拦。

    普查口径（与 `docs/07` **R170** 的机械计数**逐条对齐**）：
    · `enum` 节点 **86** 个（**20** 个文件）—— 原始机械计数是 **90**，排除 **4** 条
      **不属于闸门检查面**的：`if` / `then` / `else` / `not` 里的**条件约束**（**2** 条）
      与 `anyOf[0]` 里的**备选类型**（**2** 条）—— 前者是收窄、后者 `_allowed_values()`
      根本不读；纳入会让「合法值」被误拦（**R151** 同一类事故）；
    · `oneOf[].const` 节点 **67** 个 —— **同一类盲区**，一并覆盖。

    做法（**机械**）：对每条约束，造一个**不在**取值表里的值 ⇒ 断言 `check_spec_values`
    返回非空。⚠️ 只抽查几个不算数 —— 盲区的定义是「**全部**没检查」。
    """
    cases = _pattern_enum_cases()
    enums = [case for case in cases if case[2] == "enum"]
    consts = [case for case in cases if case[2] == "oneOf.const"]
    assert len(enums) == 86, f"`enum` 节点应为 86，实际 {len(enums)}"
    assert len(consts) == 67, f"`oneOf.const` 节点应为 67，实际 {len(consts)}"
    for relative, schema, _kind, pointer, _key_path, values in cases:
        body = _nest(pointer, _unused_value(values))
        assert check_spec_values(schema, body, endpoint="probe"), (relative, pointer)


def _pattern_enum_cases() -> list[tuple[str, dict[str, Any], str, str, tuple[str, ...], list[Any]]]:
    """普查：`patternProperties` 之下的**每一个**枚举约束。

    Returns:
        `(文件相对路径, schema 体, 种类, JSON 指针, 从根到该字段的键路径, 取值)`。

    ⚠️ **含嵌套**：约束可能在**更深的** `properties` 下
    （如 `DCRE` 的 `MAIN_REBAR[].REBAR_DIAMETER`），故递归整个条目子树。
    """
    found: list[tuple[str, dict[str, Any], str, str, tuple[str, ...], list[Any]]] = []
    for path in sorted(SCHEMA_ROOT.rglob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        schema = document.get("schema")
        if not isinstance(schema, dict):
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        _walk_enums(schema, relative, schema, "", (), found, under_pattern=False)
    return found


def _walk_enums(
    node: Any,
    relative: str,
    root: dict[str, Any],
    pointer: str,
    keys: tuple[str, ...],
    sink: list[tuple[str, dict[str, Any], str, str, tuple[str, ...], list[Any]]],
    *,
    under_pattern: bool,
) -> None:
    """递归收集枚举约束；`under_pattern` 一旦置真，**整棵子树**都算盲区。"""
    if isinstance(node, dict):
        if under_pattern and not _is_conditional(pointer):
            values = _enum_of(node)
            if values:
                kind = "enum" if isinstance(node.get("enum"), list) else "oneOf.const"
                sink.append((relative, root, kind, pointer, keys, values))
        for key, value in node.items():
            child_pointer = f"{pointer}/{key}"
            child_under = under_pattern or key == "patternProperties"
            if key in ("properties", "patternProperties") and isinstance(value, dict):
                for name, child in value.items():
                    _walk_enums(
                        child,
                        relative,
                        root,
                        f"{child_pointer}/{name}",
                        keys + (_concrete_key(name),),
                        sink,
                        under_pattern=child_under,
                    )
            else:
                # `items` / `oneOf` / `allOf` **不**产生键；其余非对象值也一并下钻
                _walk_enums(
                    value, relative, root, child_pointer, keys, sink, under_pattern=child_under
                )
    elif isinstance(node, list):
        for index, child in enumerate(node):
            _walk_enums(
                child,
                relative,
                root,
                f"{pointer}/{index}",
                keys,
                sink,
                under_pattern=under_pattern,
            )


_CONDITIONAL_KEYS: frozenset[str] = frozenset({"if", "then", "else", "not", "anyOf"})
"""**不**纳入普查的分支键。

* `if` / `then` / `else` / `not` —— 这些分支里的枚举是**收窄条件**
  （「当 `FRAME_TYPE` ∈ {…} 时 `CHECK_OPTION` 必须为 false」），**不是**取值表。
* `anyOf` —— 是**备选类型**（`anyOf[0].enum` 只是其中一种可能的形状），
  `_allowed_values()` **不**读它（它只认 `enum` 与 `oneOf[].const`）⇒ 不属于闸门的检查面。
  ⚠️ 纳入会让「合法值」被误拦 —— 与 **R151** 同一类事故。
"""


def _is_conditional(pointer: str) -> bool:
    """枚举节点是否落在**条件分支**里。"""
    return any(part in _CONDITIONAL_KEYS for part in pointer.split("/"))


def _concrete_key(name: str) -> str:
    """把 Schema 的**模式键**换成可用的**实例键**（本仓的模式都是 `^[0-9]+$` 一类）。"""
    try:
        if re.search(name, "1"):
            return "1"
    except re.error:
        pass
    return name


def _nest(pointer: str, leaf: Any) -> dict[str, Any]:
    """按**指针路径**把叶子值包成嵌套体（`items` ⇒ 包成**单元素列表**）。

    先把路径**归一成「包装步骤」序列**，再**正向**折叠 —— 避免反向遍历时
    `properties / <名>` 这两段被重复消费。
    """
    tokens = [token for token in pointer.split("/") if token]
    steps: list[tuple[str, str]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "properties" and index + 1 < len(tokens):
            steps.append(("key", tokens[index + 1]))
            index += 2
        elif token == "patternProperties" and index + 1 < len(tokens):
            steps.append(("key", _concrete_key(tokens[index + 1])))
            index += 2
        elif token == "items":
            steps.append(("list", ""))
            index += 1
        else:
            steps.append(("key", token))
            index += 1
    body: Any = leaf
    for kind, name in reversed(steps):
        body = [body] if kind == "list" else {name: body}
    return body


def _enum_of(node: Any) -> list[Any]:
    """节点的枚举取值（`enum` 或 `oneOf[].const`）。"""
    if not isinstance(node, dict):
        return []
    if isinstance(node.get("enum"), list) and node["enum"]:
        return list(node["enum"])
    branches = node.get("oneOf")
    if isinstance(branches, list):
        consts = [b["const"] for b in branches if isinstance(b, dict) and "const" in b]
        if consts and len(consts) == len(branches):
            return consts
    return []


def _unused_value(values: list[Any]) -> str:
    """造一个**不在**枚举里的字符串取值。"""
    candidate = "ZZ-BOGUS-P178"
    while candidate in values:
        candidate += "X"
    return candidate


def _body_for(
    schema: dict[str, Any], pattern: str, entry: dict[str, Any], bogus: str
) -> dict[str, Any]:
    """按 `pattern` 造一个**匹配**的条目键，并把第一个带枚举的字段设成伪值。"""
    wrapper = next(
        key
        for key, value in (schema.get("properties") or {}).items()
        if isinstance(value, dict) and pattern in (value.get("patternProperties") or {})
    )
    # 条目键：取正则的一个**可满足**实例（本仓的 pattern 都是 `^[0-9]+$` 这类简单形式）
    entry_key = "1"
    try:
        assert re.search(pattern, entry_key)
    except (AssertionError, re.error):  # pragma: no cover —— 若将来出现别的形状，显式失败
        raise AssertionError(f"无法为 pattern {pattern!r} 造条目键") from None
    field = next(name for name, node in (entry.get("properties") or {}).items() if _enum_of(node))
    return {wrapper: {entry_key: {field: bogus}}}
