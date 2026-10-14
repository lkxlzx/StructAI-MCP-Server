"""P164-d / R155：`VIEW.RESULTGRAPHIC` 的 `CURRENT_MODE` **取值表**（**离线**取证）。

本文件钉住的事实
----------------
1. **R150 的成因已定**（**更正**「成因未定」）：`VIEW.RESULTGRAPHIC` 是**多变体端点**，
   由 `Argument.CURRENT_MODE` **选变体**；手册 **34** 篇文章 / **56** 条示例给出 **36** 个取值，
   而 P160d 实测被拒的 `"displacement"` **不在**表里 ⇒ 那一次的 `400`
   （`MIDAS GEN NX second query is wrong`）= **变体选择子取值非法**，
   **不是**「缺分析结果」。
2. **证据由工具生成、可复算**（`registry/tools/extract_result_modes.py`，幂等、零请求）。
3. **数据侧缺口如实记录**：`registry/schema/common/view/RESULTGRAPHIC.json` 的 `Argument`
   **只**声明 `TYPE_OF_DISPLAY`（= **36** 个变体里的**一个**）⇒ **R140 的 `spec_guard`
   抓不到非法的 `CURRENT_MODE`**（没有枚举可查）。⚠️ **本批不修**（补全 36 个变体的
   Schema 是单独一次数据侧作业，须裁决）。
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
"""仓库根目录。"""

TOOL = REPO_ROOT / "registry" / "tools" / "extract_result_modes.py"
"""证据生成器（**离线**、零请求）。"""

EVIDENCE = REPO_ROOT / "registry" / "live" / "view_result_modes.json"
"""已提交的证据。"""

SCHEMA = REPO_ROOT / "registry" / "schema" / "common" / "view" / "RESULTGRAPHIC.json"
"""该端点的**请求** Schema（help_center 来源）。"""

ENDPOINT_YAML = REPO_ROOT / "registry" / "common" / "view" / "RESULTGRAPHIC.yaml"
"""该端点的数据侧条目。"""

DOCS_07 = REPO_ROOT / "docs" / "07_开发方案与任务续接_v1.0.md"
"""裁决 / 留缺登记表（§16.1）。"""

EXPECTED_MODES = 36
EXPECTED_ARTICLES = 34
EXPECTED_EXAMPLES = 56
REJECTED_VALUE = "displacement"
"""P160d 实测被拒的取值（**不在**手册取值表里）。"""

DOCUMENTED_SAMPLES = (
    "beamdiagrams",
    "reactionforces/moments",
    "DeformedShape",
    "DisplacementContour",
    "MVLTRC_Displacements",
    "VibrationModeShapes",
)
"""抽查若干**确有**的取值（含与 `"displacement"` 最接近的两个 `Displacement*`）。"""


def _load_tool() -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location("extract_result_modes", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _evidence() -> dict[str, Any]:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


# ===== 1. 取值表：规模 + 被拒取值 =====


def test_p164d_the_mode_table_is_reproducible_from_the_manual() -> None:
    """门槛：证据**可复算** —— 工具重跑的结果与已提交证据**逐字段一致**（幂等）。"""
    assert _load_tool().build() == _evidence()


def test_p164d_the_endpoint_has_thirty_six_documented_modes() -> None:
    """门槛：`CURRENT_MODE` 取值 **36** 个（手册 34 篇文章 / 56 条示例）。"""
    document = _evidence()
    assert document["mode_count"] == EXPECTED_MODES, document["mode_count"]
    assert len(document["modes"]) == EXPECTED_MODES
    assert document["articles"] == EXPECTED_ARTICLES, document["articles"]
    assert document["examples"] == EXPECTED_EXAMPLES, document["examples"]


def test_p164d_the_rejected_value_is_not_a_documented_mode() -> None:
    """门槛（**R150 的成因**）：`"displacement"` **不在**表里 ⇒ 那一次 `400` = 取值非法。"""
    document = _evidence()
    assert REJECTED_VALUE not in document["modes"], "取值表里出现了被拒取值 ⇒ 结论要重写"
    assert document["rejected"]["in_manual_table"] is False
    for sample in DOCUMENTED_SAMPLES:
        assert sample in document["modes"], sample


def test_p164d_every_mode_traces_back_to_an_article() -> None:
    """门槛：**逐条可回溯** —— 每个取值都带文章标题 + 示例名 + URL（**不**臆造）。"""
    for key, slot in _evidence()["modes"].items():
        assert slot["current_mode"] == key, key
        assert slot["count"] >= 1, key
        assert slot["articles"], key
        for article in slot["articles"]:
            assert article["title"], (key, article)
            assert article["url"].startswith("https://support.midasuser.com/"), (key, article)


# ===== 1b. 变体家族与 `Argument` 键的**实际**覆盖 =====


def test_p164d_the_article_families_are_counted_from_the_titles() -> None:
    """门槛：**34** 篇文章按标题归类 = **20 + 6 + 5 + 2 + 1**（含 1 篇 `Type of Display`）。"""
    families = _evidence()["families"]
    assert families == {
        "- Result Display": 20,
        "- Moving Tracer Display": 6,
        "- Heat of Hydration Display": 5,
        "- Mode Shapes Display": 2,
        "(other) Type of Display": 1,
    }, families
    assert sum(families.values()) == EXPECTED_ARTICLES


def test_p164d_the_argument_key_coverage_is_measured_not_assumed() -> None:
    """门槛：`Argument` 的兄弟键**逐条统计**（**只** `LOAD_CASE_COMB` 是**全 56 条**都有）。

    ⚠️ 这条正是「现有 Schema **只**声明 `TYPE_OF_DISPLAY`」站不住脚的理由 ——
    `TYPE_OF_DISPLAY` 只有 **53/56**（**不是**必填），而 `COMPONENTS` 有 **52/56**、
    `OUTPUT_SECT_LOCATION` **13**、`DISPLAY_OPTIONS` **7**、`CUTTING_NAME` **2**。
    """
    keys = _evidence()["argument_keys"]
    assert keys == {
        "LOAD_CASE_COMB": 56,
        "TYPE_OF_DISPLAY": 53,
        "COMPONENTS": 52,
        "OPTIONS": 25,
        "OUTPUT_SECT_LOCATION": 13,
        "DISPLAY_OPTIONS": 7,
        "CUTTING_NAME": 2,
    }, keys
    assert keys["LOAD_CASE_COMB"] == EXPECTED_EXAMPLES, "只有它才是全示例都有的"


def test_p164d_two_modes_never_carry_type_of_display() -> None:
    """门槛：**2** 个变体（`PlateCuttingLineDiagram` / `Resultant Force Diagram`）的
    **每一条**示例都**没有** `TYPE_OF_DISPLAY`；且**没有**任何变体是「部分有、部分无」。

    ⇒ `TYPE_OF_DISPLAY` **不是**公共必填字段 —— 只按它建 Schema 会**既漏必填、又误设必填**。
    """
    document = _evidence()
    assert document["modes_without_type_of_display"] == [
        "PlateCuttingLineDiagram",
        "Resultant Force Diagram",
    ], document["modes_without_type_of_display"]
    assert document["modes_partially_without_type_of_display"] == [], (
        "出现了「部分示例有、部分无」的变体 ⇒ 需要重新裁决必填性"
    )


# ===== 2. 数据侧缺口：Schema 覆盖不到变体选择子 =====


def test_p164d_the_request_schema_does_not_declare_current_mode() -> None:
    """门槛（**缺口**）：Schema 的 `Argument` **只**声明 `TYPE_OF_DISPLAY`。

    ⇒ `spec_guard`（**R140**）**没有**枚举可查 ⇒ 非法 `CURRENT_MODE` 一路发到原生
    ⇒ 这正是 R150 的 `400` 能发生的原因。⚠️ **本批只登记、不修**。
    """
    document = json.loads(SCHEMA.read_text(encoding="utf-8"))
    argument = document["schema"]["RESULTGRAPHIC"]["properties"]["Argument"]
    assert list(argument.get("properties", {})) == ["TYPE_OF_DISPLAY"], argument
    assert "CURRENT_MODE" not in SCHEMA.read_text(encoding="utf-8")


def test_p164d_the_endpoint_yaml_records_the_corrected_cause() -> None:
    """门槛：端点 YAML 头部写明**更正后的成因**与恢复条件（**不**改 `availability`）。"""
    text = ENDPOINT_YAML.read_text(encoding="utf-8")
    assert "CURRENT_MODE" in text, "必须写明变体选择子"
    assert "36" in text, "必须写明取值表规模"
    assert "displacement" in text, "必须写明被拒取值"
    assert "availability: untested" in text, "本批**不**升级 availability"


def test_p164d_the_ruling_table_registers_r155() -> None:
    """门槛：`docs/07` §16.1 **登记 R155**（成因更正 + 数据侧缺口 + 恢复条件）。"""
    text = DOCS_07.read_text(encoding="utf-8")
    assert "**R155**" in text, "R155 必须登记"
    assert "extract_result_modes.py" in text, "必须留下可复算的工具"
    assert "registry/live/view_result_modes.json" in text, "必须留下证据路径"
