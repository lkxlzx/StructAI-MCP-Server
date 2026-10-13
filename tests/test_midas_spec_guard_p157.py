"""P157 / R140：说明书枚举闸门（`spec_guard`）—— 防「非法枚举把 MIDAS 搞崩」。

⚠️ **事故驱动**：旗舰链曾给 `DESIGN.STEEL.KDS-41-30-2022.CODE-ANAL` 发
**`PERFORM_TYPE: "DESIGN"`**，而该端点只允许 **`ALL` / `ELEMS` / `SECTIONS`**
（枚举写在 `oneOf[].const` 里）。原生对非法枚举回 **`200`**（它不校验），随后
**弹出模态对话框并崩溃** ⇒ 必须拦在**我们这一侧**、**发请求之前**。
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.infrastructure.adapters.midas.errors import MidasValidationError
from app.infrastructure.adapters.midas.spec_guard import check_spec_values, guard_spec_values

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CODE_ANAL_SCHEMA = REPO_ROOT / "registry/schema/design/steel/KDS-41-30-2022/CODE-ANAL.json"


def _schema() -> dict:
    return json.loads(CODE_ANAL_SCHEMA.read_text(encoding="utf-8"))["schema"]


def test_p157_r140_the_illegal_enum_value_is_blocked_before_sending() -> None:
    """门槛：`PERFORM_TYPE: "DESIGN"`（非法）被拦；三个合法值放行。"""
    schema = _schema()
    with pytest.raises(MidasValidationError) as caught:
        guard_spec_values(
            schema,
            {"Argument": {"PERFORM_TYPE": "DESIGN"}},
            endpoint="CODE-ANAL",
            wrapper="Argument",
        )
    details = caught.value.details or {}
    assert details.get("reason") == "value_not_in_spec_enum", details
    problems = " ".join(str(item) for item in details.get("problems") or [])
    assert "DESIGN" in problems, problems
    assert "ALL" in problems and "ELEMS" in problems and "SECTIONS" in problems, problems
    for allowed in ("ALL", "ELEMS", "SECTIONS"):
        guard_spec_values(
            schema,
            {"Argument": {"PERFORM_TYPE": allowed}},
            endpoint="CODE-ANAL",
            wrapper="Argument",
        )


def test_p157_r140_the_guard_only_looks_at_declared_enums() -> None:
    """门槛：**窄**规则 —— 没声明枚举的字段**不**拦（避免误伤机械生成的 Schema）。"""
    schema = _schema()
    assert check_spec_values(schema, {"Argument": {"PERFORM_TYPE": "ALL"}}, endpoint="x") == []
    # `ELEMS` 的 `oneOf` 是 `required` 分支（**不是** `const`）⇒ **不**当枚举拦
    assert check_spec_values(schema, {"Argument": {"ELEMS": {"KEYS": [1]}}}, endpoint="x") == []
    # 未声明的字段**不**参与
    assert check_spec_values(schema, {"Argument": {"NOT_A_FIELD": "whatever"}}, endpoint="x") == []


def test_p157_r140_the_flagship_probe_uses_only_spec_values() -> None:
    """门槛：旗舰链的 `DESIGN` 参数用的是**说明书允许的**枚举。

    （本批已从 `"DESIGN"` 改为 `"ALL"`。）
    """
    tool_path = REPO_ROOT / "registry/tools/probe_flagship_chain.py"
    source = tool_path.read_text(encoding="utf-8")
    # ⚠️ **只**看常量行（注释里会提到那个非法值作为事故记录）
    lines = [line.strip() for line in source.splitlines()]
    assert '"perform_type": "ALL",' in lines, lines[:0]
    assert not any(line.startswith('"perform_type": "DESIGN"') for line in lines)
    # ⚠️ R141 起该步**会**被调用（配置已按手册补齐）⇒ 不再有 `skip`
    assert "product_boundary" not in source
