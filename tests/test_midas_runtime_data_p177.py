"""P177 / **R169 + R170**：把 P176 的成果收口成**机器可读**的判定（**零请求**）。

为什么需要它（**R167 的教训**）
------------------------------
**R167**（P174）的结论是：**「文档里的坑不是机器可读的坑」** ——
`gen-local` 只监听 `::1` 这件事**被写进文档两次**（P138 自我更正 · P139 记为已知坑），
而 **P172 / P173 仍然复发**。⇒ 教训**不是**「要记得看文档」，而是**把事实钉进用例**。

本文件按同一口径，把 P176 的**四条**事实钉成判定：

| # | 事实 | 为什么必须机器可读 |
| --- | --- | --- |
| 1 | **设计规范三处必须同族** | 「只切一处 ⇒ 跳过所有单元」**不崩**，易被误读成「产品不支持」 |
| 2 | **`MATL.STANDARD` 是材料库名，不是规范码** | 两套码表长得像 ⇒ 填错只回 `400 Unknown Error` |
| 3 | **路径段是固定路由名，规范码不进 URI** | 会诱使后人把规范码拼进 URI（→ `404`） |
| 4 | **`spec_guard` 不看 `patternProperties`** | ⚠️ 最危险：**看起来在保护，实际没看**（R170） |

⚠️ **本批不改任何裁定**：主指标仍 **`71 / 73`**（`EXPECTED_AVAILABLE` / `EXPECTED_BLOCKED`
一行未动）⇒ 本文件**不**断言主指标数值（那由
`registry/tools/check_operation_availability.py --check` 独占）。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Final

import pytest

from app.infrastructure.adapters.midas.design_codes import load_design_code_field_sets
from app.infrastructure.adapters.midas.registry import MidasRegistry
from app.infrastructure.adapters.midas.spec_guard import guard_spec_values

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
REGISTRY_ROOT: Final[Path] = REPO_ROOT / "registry"
SCHEMA_ROOT: Final[Path] = REGISTRY_ROOT / "schema"

KDS: Final[str] = "KDS 41 20 : 2022"
GB: Final[str] = "GB/T50010-10"

DOC_07: Final[Path] = REPO_ROOT / "docs" / "07_开发方案与任务续接_v1.0.md"
REGISTRY_README: Final[Path] = REGISTRY_ROOT / "README.md"
README: Final[Path] = REPO_ROOT / "README.md"


def _text(path: Path) -> str:
    """文件原文（**只读**）。"""
    return path.read_text(encoding="utf-8")


# ===== 1. 事实 ①：设计规范三处必须同族 =====


def test_p177_the_three_same_family_slots_are_named_in_the_decision() -> None:
    """门槛（事实 ①）：**三处同族**必须逐字记在裁决里 —— 否则后人只切一处。"""
    ruling = _text(DOC_07)
    for slot in ("DRC.DGNCODE", "MATL.STANDARD", "MDGN.CONC_CODE"):
        assert slot in ruling, f"裁决里必须点名 {slot}"
    # ⚠️ 关键语义：不同族 ⇒ **跳过所有单元**（**不崩**）—— 这个「不崩」是误判的根源
    assert "跳过所有单元" in ruling
    assert "failed:LoadCombination" in ruling


def test_p177_matl_standard_is_a_material_library_name_not_a_design_code() -> None:
    """门槛（事实 ②）：`MATL.STANDARD` 收**材料库名**；填规范码 ⇒ 原生 `400 Unknown Error`。

    ⚠️ 两套码表**长得像**（`GB/T10(RC)` vs `GB/T50010-10`）⇒ 这是最容易填错的一格。
    """
    section = _text(REGISTRY_README)
    assert "MATL.STANDARD" in section
    assert "材料库名" in section
    assert "GB/T10(RC)" in section
    assert "Unknown Error" in section


def test_p177_the_two_phase_contrast_is_recorded_as_effect_not_status_code() -> None:
    """门槛（铁律 ⓪）：两相对照的**落点**是「`BD-TABLE` **行数**」，**不是**状态码。

    ⚠️ 两个相位的 `BD-ANAL` 状态码**不同**（`400` / `200`），但真正判别的是**行数** `0` / `3` ——
    与 **R135**（`DOC.ANAL` 的 `200` **不**代表算完）同源。
    """
    evidence = json.loads(
        (REGISTRY_ROOT / "live" / "concrete_code_match_probe.json").read_text(encoding="utf-8")
    )
    prior = evidence["phases"]["prior"]
    matched = evidence["phases"]["matched"]
    assert prior["design_code"] == KDS
    assert prior["design_rows"] == 0
    assert matched["design_code"] == GB
    assert matched["design_rows"] > 0, "匹配相位必须真的产出结果行"
    assert len(matched["sample_rows"]) == matched["design_rows"]
    assert evidence["verdict"] == "PASSED"


# ===== 2. 事实 ③：路径段是固定路由名 =====


def test_p177_the_path_segment_is_a_route_name_and_the_code_cannot_enter_the_uri() -> None:
    """门槛（事实 ③）：规范码**不能**进 URI —— 只有 KDS 那一族的 key 存在。

    ⇒ 切换规范的**唯一**手段是**选择器端点** `DESIGN.RC.DRC` 的 `DGNCODE` 字段。
    """
    registry = MidasRegistry.load(REGISTRY_ROOT)
    assert registry.has("DESIGN.RC.KDS-41-20-2022.DCO")
    for code in ("GB-T50010-10", "GB50010-02", "ACI318-19"):
        assert not registry.has(f"DESIGN.RC.{code}.DCO"), code
    # 选择器端点**存在**，且它就是切换规范的入口
    assert registry.has("DESIGN.RC.DRC")


def test_p177_the_field_sets_stay_measured_only_after_this_batch() -> None:
    """门槛：**未**新增臆造记录 —— 字段集仍**只**来自实测（`measured`）。"""
    sets = load_design_code_field_sets(REGISTRY_ROOT)
    kds = sets.get("RC", KDS, "DCO")
    gb = sets.get("RC", GB, "DCO")
    assert kds is not None and gb is not None
    assert len(kds.fields) == 12
    assert len(gb.fields) == 0
    for item in (kds, gb):
        assert item.source == "measured", item.source
        assert item.evidence, "必须留证据指针"


# ===== 3. 事实 ④：`spec_guard` 的 `patternProperties` 盲区（**R170**）=====


def _count_enums(node: Any, trail: str = "") -> tuple[int, int]:
    """递归统计 `(枚举节点数, 其中落在 patternProperties 之下的个数)`（**机械**）。"""
    total = 0
    under_pattern = 0
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "enum" and isinstance(value, list) and value:
                total += 1
                if "patternProperties" in trail:
                    under_pattern += 1
            child_total, child_under = _count_enums(value, f"{trail}/{key}")
            total += child_total
            under_pattern += child_under
    elif isinstance(node, list):
        for index, value in enumerate(node):
            child_total, child_under = _count_enums(value, f"{trail}/{index}")
            total += child_total
            under_pattern += child_under
    return total, under_pattern


def _enum_nodes() -> tuple[int, int, list[str]]:
    """`registry/schema/**` 的枚举节点普查（**机械**，零请求）。

    Returns:
        `(枚举节点总数, 落在 patternProperties 之下的个数, 受影响文件列表)`。
    """
    total = 0
    under_pattern = 0
    files: set[str] = set()

    for path in sorted(SCHEMA_ROOT.rglob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        file_total, file_under = _count_enums(document)
        total += file_total
        under_pattern += file_under
        if file_under:
            files.add(path.relative_to(REPO_ROOT).as_posix())
    return total, under_pattern, sorted(files)


def test_p177_the_guard_blind_spot_is_counted_mechanically() -> None:
    """门槛（**R170**）：盲区规模**可复算** —— 且**这 21 个文件的枚举全在盲区里**。

    ⚠️ 「**全在**」是关键：若某文件**同时**有 `properties` 与 `patternProperties` 的枚举，
    它只是**部分**盲；本批实测**没有**这种混合文件 ⇒ 受影响文件的枚举约束 **100%** 不被检查。
    """
    total, under_pattern, files = _enum_nodes()
    assert total > 0
    assert under_pattern > 0, "盲区若归零，说明闸门已修 —— 那时应更新本用例与 R170"
    assert len(files) == 21, files
    # 每一个受影响文件的**全部**枚举都在 patternProperties 下（无混合文件）
    for name in files:
        document = json.loads((REPO_ROOT / name).read_text(encoding="utf-8"))
        file_total, file_under = _count_enums(document)
        assert file_total == file_under, (name, file_total, file_under)


def test_p177_the_blind_spot_is_proven_by_a_two_way_contrast() -> None:
    """门槛（**R170** 的**历史**两相对照 —— ⚠️ **P178 已修好，本用例改为断言「已收口」**）。

    **历史**（P177）：同一非法取值在 `DESIGN.RC.DRC`（枚举在 `patternProperties` 下）**不拦**、
    在 `OPE.LCOM-CONC`（枚举在 `properties` 下）**拦** ⇒ 证明「不是取值合法，是闸门没看」。

    **现状**（P178 / **R170 收口**）：两侧**都**拦 ⇒ 盲区已归零。
    ⚠️ 本用例**保留**两相对照的**形状**（同一组件、同一取值），只是把**期望**从
    「一处拦一处不拦」改成「**两处都拦**」—— 这样一旦回归，**立刻**红。
    """
    blind = json.loads((SCHEMA_ROOT / "design" / "rc" / "DRC.json").read_text(encoding="utf-8"))
    seen = json.loads(
        (SCHEMA_ROOT / "products" / "gen_nx" / "ope" / "LCOM-CONC.json").read_text(encoding="utf-8")
    )
    bogus = "TOTALLY-BOGUS-DESIGN-CODE"

    # 原先的**盲区**：枚举在 patternProperties 下 —— 现在**必须**拦（R170 已收口）
    with pytest.raises(Exception) as blind_error:  # noqa: B017 —— 只断言「被拦」
        guard_spec_values(
            blind["schema"],
            {"Assign": {"1": {"DGNCODE": bogus}}},
            endpoint="DESIGN.RC.DRC",
            wrapper="Assign",
        )
    assert "spec_enum" in str(blind_error.value)

    # 对照：枚举在 properties 下 —— 一直**拦**
    with pytest.raises(Exception) as seen_error:  # noqa: B017 —— 只断言「被拦」
        guard_spec_values(
            seen["schema"],
            {"Argument": {"DGNCODE": bogus}},
            endpoint="OPE.LCOM-CONC",
            wrapper="Argument",
        )
    assert "spec_enum" in str(seen_error.value)


def test_p177_the_legit_value_still_passes_through_the_guarded_endpoint() -> None:
    """门槛（**R157** 的方法学）：说「盲区」前先证明**仪器有效** —— 合法值在**同一**端点照常放行。

    ⚠️ 若不加这条，`test_p177_the_blind_spot_is_proven_by_a_two_way_contrast` 的
    「对照组被拦」可能被误读成「闸门把**所有**取值都拦了」。
    """
    seen = json.loads(
        (SCHEMA_ROOT / "products" / "gen_nx" / "ope" / "LCOM-CONC.json").read_text(encoding="utf-8")
    )
    guard_spec_values(
        seen["schema"],
        {"Argument": {"DGNCODE": KDS}},
        endpoint="OPE.LCOM-CONC",
        wrapper="Argument",
    )


# ===== 4. 收口（**R169** / **R170**）在文档里可追溯 =====


def test_p177_the_decision_and_the_record_exist_in_the_docs() -> None:
    """门槛：裁决与记录**都在** —— `docs/07` §16.1 R169 / R170 + `registry/README.md` §8.31。"""
    ruling = _text(DOC_07)
    assert "| **R169** |" in ruling
    assert "| **R170** |" in ruling
    assert "### 8.31 P176" in _text(REGISTRY_README)
    assert "§8.31" in ruling
    # README 的两个指标节都要提到「设计规范是运行时数据」
    readme = _text(README)
    assert "运行时数据" in readme
    assert "R169" in readme and "R170" in readme


def test_p177_this_batch_does_not_touch_any_verdict() -> None:
    """门槛：**本批不改任何裁定** —— 主指标由工具独占，本文件**不**重复断言那个数值。

    ⚠️ 只扫**断言语句**（`ast`），**不**扫文档串 —— 说明文字里提到数值是**引用**，不是**真相来源**。
    ⚠️ 跳过**本用例自己**（它的判据**就是**那两个数值，自指会让断言恒假）。
    """
    tree = ast.parse(_text(Path(__file__)))
    literals: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        if node.name == "test_p177_this_batch_does_not_touch_any_verdict":
            continue  # 本用例自身的判据**就是**那两个数值（自指会让断言恒假）
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Assert):
                continue
            for leaf in ast.walk(inner.test):
                if isinstance(leaf, ast.Constant) and isinstance(leaf.value, int):
                    literals.append(leaf.value)
    # 主指标的分子 / 分母**不**得出现在本文件的任何**断言**里（避免第二个真相来源）
    assert 71 not in literals, literals
    assert 73 not in literals, literals
