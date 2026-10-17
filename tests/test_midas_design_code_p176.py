"""P176 / **R168 续**：设计规范成为**运行时数据**（接口层去硬编码）。

背景
----
用户指出架构缺陷：**接口层写死了设计规范 / 材料 / 字段集**，而这些应当在实际使用时确定。
触发场景 = `DESIGN.CONCRETE` 跑不通（`BD-ANAL` → `400 failed:LoadCombination`）。
真因 = **设计规范与模型材料规范不匹配**（P176 两相对照实测：
`KDS 41 20 : 2022` ⇒ 0 行；`GB/T50010-10` ⇒ **3 行真实结果**）。

本批的三条实测事实（逐条钉在下面）
----------------------------------
* **F1 路径段是固定路由名**：`/design/RC/GB-T50010-10/DCO` → `404`
  ⇒ 规范码**不能**进 URI；切换只能靠选择器端点的 `DGNCODE` 字段。
* **F2 字段集随规范变化，且自省不反映它**：KDS 接受 12 / 13，`GB/T50010-10` 接受 **0**；
  而 `GET /info/design/RC/KDS-41-20-2022/DCO` 在两种规范下返回**同一份 13 字段**。
* **F3 `DCO` 可选**：为空时设计链照常跑通。

判定 = 本文件（**零请求**；真机证据见 `registry/live/concrete_code_match_probe.json`）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.infrastructure.adapters.midas.adapter import (
    _design_code_items,
    _design_code_of,
    _design_config_endpoint_of,
    _design_material_of,
    _has_payload_for_config,
)
from app.infrastructure.adapters.midas.design_codes import (
    load_design_code_field_sets,
    parse_design_code_field_sets,
)
from app.infrastructure.adapters.midas.errors import MidasConnectionError
from app.infrastructure.adapters.midas.registry import MidasRegistry
from app.infrastructure.adapters.midas.transforms import TRANSFORMER_REGISTRY

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_ROOT = REPO_ROOT / "registry"
FIELD_SETS = REGISTRY_ROOT / "live" / "design_code_field_sets.json"
EVIDENCE = REGISTRY_ROOT / "live" / "concrete_code_match_probe.json"

KDS = "KDS 41 20 : 2022"
GB = "GB/T50010-10"
DCO = "DESIGN.RC.KDS-41-20-2022.DCO"


def _registry() -> MidasRegistry:
    """数据侧 Registry（`registry/` 的唯一权威来源）。"""
    return MidasRegistry.load(REGISTRY_ROOT)


def _document() -> dict[str, Any]:
    """字段集数据文件原文。"""
    return json.loads(FIELD_SETS.read_text(encoding="utf-8"))


# ===== 1. F1：路径段是固定路由名，规范码**不**进 URI =====


def test_p176_the_endpoint_key_path_segment_is_a_route_name_not_the_active_code() -> None:
    """门槛（**F1**）：端点 key 里的规范段是**路由名** —— 实测换码即 `404`。

    ⚠️ 这是本批**方案形状**的依据：端点 key **不**参数化（`operations.py` 里的字面 key 是对的），
    真正要参数化的是**选择器取值**与**配置项字段集**。
    """
    registry = _registry()
    # 只有 KDS 那一族的 key 存在；别的规范码**没有**任何 key（⇒ 无法 resolve）
    assert registry.has(DCO)
    for code in ("GB-T50010-10", "GB50010-02", "ACI318-19"):
        assert not registry.has(f"DESIGN.RC.{code}.DCO"), code
    # 数据文件里记着这条事实（供后人复算）
    note = " ".join(_document().get("note") or [])
    assert "固定路由名" in note
    assert "404" in note


# ===== 2. F2：字段集随规范变化，且**只能**来自实测 =====


def test_p176_the_field_sets_differ_per_code_and_are_measured_only() -> None:
    """门槛（**F2**）：两种规范的 `DCO` 字段集**不同**，且来源**只能是实测**。"""
    sets = load_design_code_field_sets(REGISTRY_ROOT)
    kds = sets.get("RC", KDS, "DCO")
    gb = sets.get("RC", GB, "DCO")
    assert kds is not None and gb is not None
    assert len(kds.fields) == 12, kds.fields
    assert len(gb.fields) == 0, gb.fields
    # 差集恰好是那个被原生拒收的字段
    assert "CONC_STRS_STRN" not in kds.fields
    assert kds.accepts("DESIGN_CD") and not gb.accepts("DESIGN_CD")
    for item in (kds, gb):
        assert item.source == "measured", item.source
        assert item.evidence, "必须留证据指针"
    # ⚠️ 自省**不**能作来源（它返回端点声明的形状，不随规范变）
    text = FIELD_SETS.read_text(encoding="utf-8")
    assert "自省不能作来源" in text


def test_p176_an_uncharacterized_code_has_no_record_and_is_never_fabricated() -> None:
    """门槛：**未实测**的码 ⇒ `None`（**不**臆造字段集）。"""
    sets = load_design_code_field_sets(REGISTRY_ROOT)
    for code in ("ACI318-19", "GB50010-02", "Eurocode2"):
        assert sets.get("RC", code, "DCO") is None, code


def test_p176_the_registry_exposes_the_field_set_lookup() -> None:
    """门槛：`MidasRegistry` 是字段集的**唯一**读取点（Core 里不硬编码）。"""
    registry = _registry()
    kds = registry.design_code_field_set("RC", KDS, "DCO")
    assert kds is not None and len(kds.fields) == 12
    assert registry.design_code_field_set("RC", "ACI318-19", "DCO") is None
    # 缺文件 ⇒ 空集合（**不**静默造假）
    empty = load_design_code_field_sets(REPO_ROOT / "does-not-exist")
    assert len(empty) == 0 and empty.get("RC", KDS, "DCO") is None


# ===== 3. `design_code` 裸字符串归一化（Phase 1）=====


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (GB, [{"dgn_code": GB}]),
        (f"  {GB}  ", [{"dgn_code": GB}]),
        ({"dgn_code": "ACI318-19"}, [{"dgn_code": "ACI318-19"}]),
        ([{"dgn_code": KDS}], [{"dgn_code": KDS}]),
    ],
)
def test_p176_a_bare_design_code_string_is_normalized(value: Any, expected: Any) -> None:
    """门槛：**裸字符串**与既有映射形态**都认**（原先裸串 ⇒ 空载荷 ⇒ 静默跳过）。"""
    assert _design_code_items({"design_code": value}) == expected


@pytest.mark.parametrize("value", ["", "   ", None, 123, True])
def test_p176_a_blank_or_non_string_design_code_yields_nothing(value: Any) -> None:
    """门槛：空 / 非法类型 ⇒ **空**（**不**臆造条目）。"""
    assert _design_code_items({"design_code": value}) == []


def test_p176_the_design_code_of_a_call_reads_the_normalized_value() -> None:
    """门槛：`_design_code_of` 取归一化后的码（没给 → 空串 ⇒ 不注入字段集）。"""
    assert _design_code_of({"design_code": GB}) == GB
    assert _design_code_of({"design_code": f" {GB} "}) == GB
    assert _design_code_of({}) == ""
    assert _design_code_of(None) == ""


# ===== 4. 端点 key 的解析（材料段 / 配置端点）=====


def test_p176_the_endpoint_key_is_split_into_material_and_config_endpoint() -> None:
    """门槛：从 key 取**材料段**与**配置端点末段**（非配置端点 → `None`）。"""
    assert _design_material_of(DCO) == "RC"
    assert _design_material_of("DESIGN.STEEL.KDS-41-30-2022.DCO") == "STEEL"
    assert _design_material_of("DESIGN.SRC.AIK-SRC2K.MEMB") == "SRC"
    # 非 DESIGN / 非三材料 ⇒ None
    assert _design_material_of("DB.NODE") is None
    assert _design_material_of("DESIGN.FOO.BAR") is None
    # ⚠️ 选择器 `DESIGN.RC.DRC` 的**材料段就是** `RC`（它与配置端点同材料）
    #    —— 区分靠 `_design_config_endpoint_of`（`DRC` **不**在配置端点集合里）
    assert _design_material_of("DESIGN.RC.DRC") == "RC"
    assert _design_config_endpoint_of("DESIGN.RC.DRC") is None
    assert _design_config_endpoint_of(DCO) == "DCO"
    # ⚠️ **只有 `DCO`** 的字段集随规范变化（P176 实测）——
    #    `DCTL`（框架控制）/ `MEMB`（构件指派）在**中国规范下同样 `PUT 200`**
    #    ⇒ 它们**不**参与字段集注入（纳入会把本来正确的配置误判为「未实测」，
    #    P176 实测踩到：`MEMB` 被拦 ⇒ 整个设计任务 `FAILED`）。
    for key in (
        "DESIGN.RC.DRC",
        "DESIGN.RC.KDS-41-20-2022.DCTL",
        "DESIGN.RC.KDS-41-20-2022.MEMB",
        "DESIGN.RC.KDS-41-20-2022.BD-ANAL",
        "DESIGN.RC.KDS-41-20-2022.BD-TABLE",
    ):
        assert _design_config_endpoint_of(key) is None, key


def test_p176_the_config_payload_probe_matches_the_parameter_names() -> None:
    """门槛：`_has_payload_for_config` 认得三个配置项的参数名。"""
    assert _has_payload_for_config({"design_option": {"a": 1}}, "DCO")
    assert not _has_payload_for_config({}, "DCO")
    assert _has_payload_for_config({"design_frame": {"a": 1}}, "DCTL")
    assert _has_payload_for_config({"design_members": [{"elements": [1]}]}, "MEMB")
    # 未知末段 ⇒ 不认（**不**臆造）
    assert not _has_payload_for_config({"design_option": {"a": 1}}, "UNKNOWN")


# ===== 5. Transformer 字段集覆盖（Phase 2 的核心机制）=====


def test_p176_a_transformer_takes_an_optional_field_override() -> None:
    """门槛：`fields` 覆盖只走**实例**，**类级默认不变**。

    ⚠️ 类级不变是**硬要求**：`registry/tools/check_canonical_field_gap.py` 与
    `classify_mapping_gap.py` 是**从类上**读 `cls.endpoint` / `cls.fields` 的。
    """
    registry = _registry()
    cls = TRANSFORMER_REGISTRY["midas.design.rc-option.v1"]
    class_level = cls.fields
    assert len(class_level) == 13, len(class_level)

    default = cls(registry)
    assert default.effective_fields == class_level, "不传覆盖 ⇒ 类级默认"
    assert len(default.effective_fields) == 13

    kds = _registry().design_code_field_set("RC", KDS, "DCO")
    assert kds is not None
    kept = tuple(f for f in class_level if f.native in kds.fields)
    overridden = cls(registry, fields=kept)
    assert len(overridden.effective_fields) == 12
    assert all(f.native != "CONC_STRS_STRN" for f in overridden.effective_fields)
    # 类级**仍**是 13（覆盖不污染类）
    assert len(cls.fields) == 13


def test_p176_the_class_endpoint_declares_which_code_its_fields_belong_to() -> None:
    """门槛：每个设计 Transformer 的类级 `fields` 归属**它自己那个规范**。

    ⚠️ 这条判据**防止把本来正确的配置误判为「未实测」**（P176 实测踩到）：
    调用方给的码 == 类级归属码 ⇒ 类级默认即正确，**不**查覆盖、**不**报错。
    """
    from app.infrastructure.adapters.midas.adapter import _code_of_class_endpoint

    cases = {
        "midas.design.rc-option.v1": "KDS 41 20 : 2022",
        "midas.design.rc-frame.v1": "KDS 41 20 : 2022",
        "midas.design.dco.v1": "KDS 41 30 : 2022",
        "midas.design.steel.v1": "KDS 41 30 : 2022",
        "midas.design.src-option.v1": "AIK-SRC2K",
    }
    for name, expected in cases.items():
        factory = TRANSFORMER_REGISTRY[name]
        assert _code_of_class_endpoint(factory) == expected, name
    # 非设计 Transformer ⇒ 空串（**不**臆造归属）
    assert _code_of_class_endpoint(TRANSFORMER_REGISTRY["midas.node.v1"]) == ""


def test_p176_an_empty_override_disables_every_field() -> None:
    """门槛：**空**覆盖 ⇒ 一个字段都不发（`GB/T50010-10` 下 `DCO` 的实测形态）。"""
    registry = _registry()
    cls = TRANSFORMER_REGISTRY["midas.design.rc-option.v1"]
    empty = cls(registry, fields=())
    assert empty.effective_fields == ()
    assert empty.field_for("design_cd") is None


# ===== 6. F3：`DCO` 可选（跳过是安全的）=====


def test_p176_the_evidence_shows_the_two_phase_contrast() -> None:
    """门槛（**F3** 的前提）：真机证据两相可判 —— 规范不匹配 **0 行**、匹配 **3 行**。"""
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    phases = evidence["phases"]
    assert phases["prior"]["design_code"] == KDS
    assert phases["prior"]["design_rows"] == 0
    assert phases["matched"]["design_code"] == GB
    assert phases["matched"]["status"] == 200
    assert phases["matched"]["design_rows"] == 3
    assert evidence["verdict"] == "PASSED"


# ===== 7. 数据文件的解析健壮性（数据缺陷**不**静默忽略）=====


@pytest.mark.parametrize(
    "document",
    [
        [],
        {},
        {"materials": []},
        {"materials": {"RC": []}},
        {"materials": {"RC": {KDS: {"DCO": {"fields": "not-a-list"}}}}},
        {"materials": {"RC": {KDS: {"DCO": {"fields": [], "source": "introspect"}}}}},
        {"materials": {"RC": {KDS: {"DCO": {"fields": []}}}}},
    ],
)
def test_p176_a_malformed_data_file_fails_loudly(document: Any) -> None:
    """门槛：结构不符 / 来源非法（**含 `introspect`**）⇒ 明确报错。"""
    with pytest.raises(MidasConnectionError):
        parse_design_code_field_sets(document)


def test_p176_a_well_formed_document_parses() -> None:
    """门槛（阳性对照）：合法文档能解析，且 `introspect` **不在**允许来源里。"""
    parsed = parse_design_code_field_sets(
        {
            "materials": {
                "RC": {
                    "X": {
                        "DCO": {
                            "fields": ["A"],
                            "source": "measured",
                            "evidence": "e.json",
                        }
                    }
                }
            }
        }
    )
    item = parsed.get("RC", "X", "DCO")
    assert item is not None and item.fields == ("A",) and item.accepts("A")
    assert not item.accepts("B")
    assert item.source == "measured"
