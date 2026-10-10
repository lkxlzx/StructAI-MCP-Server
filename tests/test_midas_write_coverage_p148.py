"""P148：写路径覆盖推进**第五批**（13 个端点 → 12 条模板跑通；1 条如实留缺 R105）。

权威来源
--------
- `docs/07` §16 **R4 / R14 / R97** · §16.1 **R100**（候选判据 + 「能建必须能删」）·
  §16.1 **R101 / R102 / R103 / R104**（如实留缺的四种形态）· §16.1 **R105**（本批新增：
  `DB.IMFM` 的手册**两个**条目都被本 build 拒绝 ⇒ 模板**不写**、不入候选）。
- `registry/README.md` §2.3 / §8.8（⑨）· `registry/live/write_templates.json`。
- `docs/reports/P148_写路径覆盖推进第五批_v1.0.md`（本批证据）。

本文件的**可执行判定**
--------------------
1. **候选判据（R100 未放宽）**：GEN NX 58 → 61 → 70、CIVIL NX 49 → 52 → 60、Civil Designer 仍
   **0**；「既无 Transformer 又无模板」的端点数随之 **495** / **433** / **31**（P148 时；P149-A 只读
   `OPTIONS` 实测修正后为 **512** / **448** / **31**，**P149-B2 续跑**再降至 **503** / **440** /
   **31**，逐产品可复算）。（P149-B2 续跑：分块补测 67 条 → 再 +9 真实 L5 `PASSED`）
2. **本批 12 条模板全部是手册示例的**逐字节**照抄**（`manual_example`、**零** adjustments）；
   其中 **7** 条零前置链，**5** 条用**既有**前置机制（`DB.EXLD` / `DB.LDSQ` / `DB.EFCT` 补
   `DB.STLD` 工况名；`DB.NMAS` 用 `target_id_source`；`DB.TDNT` 用 `references` 写回 `MATL`）。
3. **`DB.IMFM` 如实留缺（R105）**：手册条目 7 / 条目 8 **逐个**被本 build 拒绝
   （`POST` → `400 software_api_error`）⇒ 模板**不写**、不入候选；数据侧**未**被改动
   （端点仍 `enabled` / `verified` / 写方法齐全，且被拒条目的每个字段都在请求 Schema 里声明）。
4. **落盘前的只读自省**：13 个端点**全部**先用**只读** `GET /info/db/<CODE>` 核对
   「手册示例字段 ⊆ 本 build 接受字段」（`unknown` = **0**；`DB.ACTL` 的 `CLATS` 是 R101 对照物）。
5. **离线三步链**：12 个新端点逐个跑通「创建 → 读回 → 按路径 key 删除」，发送的请求体**逐字节**
   等于数据侧模板 `body`，跑完**零残留**。
6. **口径不变**：分母仍 `write_path_keys()`（P149-A 起 **633**，`model_write` 子桶 **434**；
   P148 为 609 / 410）；分子 = L5 `PASSED` 去重 key（本批 **58 / 609**，
   `model_write_ratio` **58 / 410**；P149-B2 续跑起 **70 / 633** / **70 / 434**）。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import test_midas_write_templates_p139 as p139
from app.infrastructure.adapters.midas.live import DedicatedTestProject, write_path_coverage
from app.infrastructure.adapters.midas.registry import MidasRegistry
from app.infrastructure.adapters.midas.transforms import TRANSFORMER_REGISTRY
from app.infrastructure.adapters.midas.write_probe import (
    EMPTINESS_GATE_KEYS,
    WRITE_METHODS,
    WRITE_PROBE_PASSED,
    MidasLiveWriteProbe,
    transformer_name_for,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录（数据侧工具与上游手册都在这里）。"""

CHECK_TOOL_PATH = REPO_ROOT / "registry" / "tools" / "check_write_templates.py"
"""模板复算工具（本批新增 12 条后仍必须 0 错）。"""

WRITE_PATH_TOTAL = 633
"""写路径端点数 —— R4 / R14 的**正式**分母（**不挪**口径；P149-A 起 **633**，P148 为 609）。"""

MODEL_WRITE_TOTAL = 434
"""分母里的「模型写」子桶（P141 裁决⑤；P148 为 410）。"""

NEW_TEMPLATE_KEYS = (
    "DB.EXLD",
    "DB.LDSQ",
    "DB.HHCT",
    "DB.MVCTBS",
    "DB.MVCTCH",
    "DB.MVCTID",
    "DB.MVCTTR",
    "DB.POSL",
    "DB.STOR",
    "DB.EFCT",
    "DB.NMAS",
    "DB.TDNT",
)
"""本批**跑通**的 12 个端点（全部只有数据侧模板、没有 Transformer）。"""

ZERO_PREREQUISITE_KEYS = (
    "DB.HHCT",
    "DB.MVCTBS",
    "DB.MVCTCH",
    "DB.MVCTID",
    "DB.MVCTTR",
    "DB.POSL",
    "DB.STOR",
)
"""**零前置链**的 7 条（请求体不引用任何既有对象）。"""

STLD_CHAIN_KEYS = ("DB.EXLD", "DB.LDSQ", "DB.EFCT")
"""请求体**引用荷载工况名** ⇒ 按**既有**机制补两条 `DB.STLD` 前置（工况名逐条对齐）。"""

NODE_TARGET_KEY = "DB.NMAS"
"""`Assign` 键就是**自建节点号** ⇒ `target_id_source = "DB.NODE#1"`（P141 / R96 的反向依赖）。"""

MATL_REFERENCE_KEY = "DB.TDNT"
"""请求体按材质号取值 ⇒ `prerequisites[].references` 把自建材质号写回 body 的 `MATL`。"""

NEW_TEMPLATE_ORIGINS: dict[str, tuple[str, str, str]] = {
    "DB.EXLD": ("db/EXLD", "External Type Load Case for Pretension", "1"),
    "DB.LDSQ": ("db/LDSQ", "Load Sequence for Nonlinear", "1"),
    "DB.HHCT": ("db/HHCT", "General", "1"),
    "DB.MVCTBS": ("db/MVCTbs", "Moving Load Analysis Control", "1"),
    "DB.MVCTCH": ("db/MVCTch", "Moving Load Analysis Control", "1"),
    "DB.MVCTID": ("db/MVCTid", "Moving Load Analysis Control", "1"),
    "DB.MVCTTR": ("db/MVCTtr", "Moving Load Analysis Control", "1"),
    "DB.POSL": ("db/POSL", "", "1"),
    "DB.STOR": ("db/STOR", "Import to Json", "1"),
    "DB.EFCT": ("db/EFCT", "Small Displacement/Initial Force Control Data", "1"),
    "DB.NMAS": ("db/NMAS", "Nodal Masses", "1"),
    "DB.TDNT": ("db/TDNT", "Magura", "1"),
}
"""12 条模板各自的来源定位（上游手册 `input_uri` / 示例名 / 示例条目编号）。"""

LEFT_OUT_KEY = "DB.IMFM"
"""本批**如实留缺**的端点（R105）：手册**两个**条目都被本 build 拒绝。"""

LEFT_OUT_ORIGINS: tuple[tuple[str, str, str], ...] = (
    ("db/IMFM", "Inelastic Material Properties for Fiber Model", "7"),
    ("db/IMFM", "Inelastic Material Properties for Fiber Model", "8"),
)
"""被拒的**两个**手册条目（同样逐条可复算）。"""

INTROSPECTED_KEYS = NEW_TEMPLATE_KEYS + (LEFT_OUT_KEY,)
"""本批落盘前逐个做过**只读**自省（`GET /info/db/<CODE>`）的端点（13 个）。"""

INTROSPECT_UNKNOWN_FIELDS: dict[str, int] = dict.fromkeys(INTROSPECTED_KEYS, 0)
"""逐端点的「手册示例字段 ∉ 本 build 接受字段」计数（本批全部 **0**）。"""

CANDIDATES_BY_PRODUCT: dict[str, tuple[str, ...]] = {
    "GEN_NX": (
        "DB.BMLD",
        "DB.BNGR",
        "DB.BODF",
        "DB.CCFC",
        "DB.CNLD",
        "DB.CONS",
        "DB.CUTL",
        "DB.DCON",
        "DB.DCTL",
        "DB.DSTL",
        "DB.EFCT",
        "DB.EIGV",
        "DB.ELEM",
        "DB.EPMT",
        "DB.ETFC",
        "DB.EXLD",
        "DB.FBLD",
        "DB.FIMP",
        "DB.GRUP",
        "DB.GSTP",
        "DB.HHCT",
        "DB.HSFC",
        "DB.IEHC",
        "DB.LDGR",
        "DB.LDSQ",
        "DB.LENG",
        "DB.MATL",
        "DB.MBTP",
        "DB.MLFC",
        "DB.MVCD",
        "DB.MVCTBS",
        "DB.MVCTCH",
        "DB.MVCTID",
        "DB.MVCTTR",
        "DB.MVHLTR",
        "DB.NMAS",
        "DB.NODE",
        "DB.NPLN",
        "DB.PDEL",
        "DB.PJCF",
        "DB.PNLD",
        "DB.POGD",
        "DB.POSL",
        "DB.POSP",
        "DB.PRES",
        "DB.PSLT",
        "DB.SDHY",
        "DB.SDIS",
        "DB.SDST",
        "DB.SDVE",
        "DB.SDVI",
        "DB.SECT",
        "DB.SMCT",
        "DB.SPFC",
        "DB.STLD",
        "DB.STOR",
        "DB.TDGR",
        "DB.TDME",
        "DB.TDMT",
        "DB.TDNT",
        "DB.THFC",
        "DB.THIK",
        "DB.VSEC",
        "DB.WMAK",
        "DESIGN.RC.DRC",
        "DESIGN.RC.KDS-41-20-2022.DCO",
        "DESIGN.RC.KDS-41-20-2022.DCTL",
        "DESIGN.SRC.AIK-SRC2K.DCO",
        "DESIGN.STEEL.DSTL",
        "DESIGN.STEEL.KDS-41-30-2022.DCO",
    ),
    "CIVIL_NX": (
        "DB.BMLD",
        "DB.BNGR",
        "DB.BODF",
        "DB.CCFC",
        "DB.CNLD",
        "DB.CONS",
        "DB.CUTL",
        "DB.DCON",
        "DB.EFCT",
        "DB.EIGV",
        "DB.ELEM",
        "DB.EPMT",
        "DB.ETFC",
        "DB.EXLD",
        "DB.FBLD",
        "DB.FIMP",
        "DB.GRUP",
        "DB.GSTP",
        "DB.HHCT",
        "DB.HSFC",
        "DB.IEHC",
        "DB.LDGR",
        "DB.LDSQ",
        "DB.MATL",
        "DB.MLFC",
        "DB.MVCD",
        "DB.MVCTBS",
        "DB.MVCTCH",
        "DB.MVCTID",
        "DB.MVCTTR",
        "DB.MVHLTR",
        "DB.NMAS",
        "DB.NODE",
        "DB.NPLN",
        "DB.PDEL",
        "DB.PJCF",
        "DB.PNLD",
        "DB.POGD",
        "DB.PRES",
        "DB.PSLT",
        "DB.SDST",
        "DB.SDVE",
        "DB.SDVI",
        "DB.SECT",
        "DB.SMCT",
        "DB.SPFC",
        "DB.STLD",
        "DB.TDGR",
        "DB.TDME",
        "DB.TDMT",
        "DB.TDNT",
        "DB.THFC",
        "DB.THIK",
        "DB.VSEC",
        "DESIGN.RC.DRC",
        "DESIGN.RC.KDS-41-20-2022.DCO",
        "DESIGN.RC.KDS-41-20-2022.DCTL",
        "DESIGN.SRC.AIK-SRC2K.DCO",
        "DESIGN.STEEL.DSTL",
        "DESIGN.STEEL.KDS-41-30-2022.DCO",
    ),
    "CIVIL_DESIGNER": (),
}
"""三产品各自的候选集（**70 / 60 / 0**；P149-B2 续跑：分块补测 67 条 → 再 +9 真实 L5 `PASSED`）。"""

BLOCKED_TOTAL: dict[str, int] = {"GEN_NX": 503, "CIVIL_NX": 440, "CIVIL_DESIGNER": 31}
"""「有写方法 + 非危险形态，但既无 Transformer 又无数据侧模板」的端点数。

P149-B2 续跑起 **503 / 440 / 31**（P149-B2 首轮 512 / 448 / 31；P149-A 为 515 / 451 / 31）。"""

EXPECTED_TEMPLATES = 69
"""模板条数（P149-B2 首轮的 60 + 续跑 9 = **69**）。"""

EXPECTED_BODIES = 113
"""复算的 body 总数（**113** = 69 个目标 + 44 个前置对象；P149-B2 续跑新增 9 目标）。"""

EXPECTED_REFERENCES = 23
"""`prerequisites[].references` 的条数（P147 的 22 + 本批 `DB.TDNT` 的 1）。"""

EXPECTED_SELF_REFERENCES = 4
"""模板 `self_references` 的条数（本批未变：12 条新模板都**没有**自引用编号）。"""

CORE_FORBIDDEN_LITERALS = (
    "In_Pre_Magura",
    "KDS(41-17-00:2019)",
    "PrS1",
    "DL(BC)4",
)
"""本批模板的**特征取值**（`app/**` 里出现即等于把模板硬编码进 Core）。"""


def _check_tool() -> Any:
    """按路径装载 `registry/tools/check_write_templates.py`（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(
        "structai_check_write_templates_p148", CHECK_TOOL_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _registry() -> MidasRegistry:
    """数据侧 Registry（`registry/` 的唯一权威来源）。"""
    return p139._registry()


def _probe(product: str, *, only: tuple[str, ...] = (), transport: object = None):
    """构造写路径探针（缺省用**空**假传输）。"""
    store = p139._NxStore(codes=()) if transport is None else transport
    return MidasLiveWriteProbe(
        p139._client(store),
        _registry(),
        product=product,
        project=DedicatedTestProject(name="p148"),
        limit=0,
        only=only,
    )


def _derived_candidates(registry: MidasRegistry, product: str) -> tuple[tuple[str, ...], int]:
    """独立复算候选集与「既无 Transformer 又无模板」的端点数（**不**调用 `candidate_keys`）。"""
    candidates: list[str] = []
    blocked = 0
    for key in registry.keys():
        definition = registry.endpoint(key)
        if product not in definition.products or not definition.enabled:
            continue
        methods = registry.methods_for(key=key, product=product)
        if not any(method in methods for method in WRITE_METHODS):
            continue
        resolved = registry.resolve(key=key, product=product)
        if definition.destructive or resolved.delete_all_via_body:
            continue
        has_source = (
            TRANSFORMER_REGISTRY.get(transformer_name_for(key)) is not None
            or registry.write_template(key) is not None
        )
        if not has_source:
            blocked += 1
            continue
        if "GET" not in methods or not definition.read_root or "DELETE" not in methods:
            continue
        candidates.append(key)
    return tuple(candidates), blocked


class _Row:
    """`midas_api_verifications` 的最小只读投影（覆盖率只读 `endpoint_key` / 级别 / 结论）。"""

    __slots__ = ("contract_level", "endpoint_key", "product", "status")

    def __init__(self, endpoint_key: str) -> None:
        self.endpoint_key = endpoint_key
        self.contract_level = "L5"
        self.product = "GEN_NX"
        self.status = "PASSED"


# ===== 1. 候选判据（判定 1）=====


def test_p148_the_candidate_gate_counts_58_and_49_and_0() -> None:
    """门槛：三产品候选集 **70 / 60 / 0**、blocked **503 / 440 / 31**（P149-B2 续跑：分块补测 67
    条 → 再 +9 真实 L5 `PASSED`），逐产品可复算。"""
    registry = _registry()
    for product, expected in CANDIDATES_BY_PRODUCT.items():
        derived, blocked = _derived_candidates(registry, product)
        assert derived == expected, product
        assert blocked == BLOCKED_TOTAL[product], product
        assert _probe(product).candidate_keys() == expected, product
    # 本批 12 个新端点全部**只有模板**（没有 Transformer）—— 这正是 R100 打开的那条路
    for key in NEW_TEMPLATE_KEYS:
        assert TRANSFORMER_REGISTRY.get(transformer_name_for(key)) is None, key
        assert registry.write_template(key) is not None, key
        assert key in CANDIDATES_BY_PRODUCT["GEN_NX"], key
    # `DB.POSL` / `DB.STOR` 只属 GEN NX（数据侧在 `registry/products/gen_nx/`）
    for key in ("DB.POSL", "DB.STOR"):
        assert key not in CANDIDATES_BY_PRODUCT["CIVIL_NX"], key
    # 每个候选在该产品上都必须**能删**（R100）
    for product, keys in CANDIDATES_BY_PRODUCT.items():
        for key in keys:
            assert "DELETE" in registry.methods_for(key=key, product=product), (product, key)


# ===== 2. 数据侧模板（判定 2 / 3）=====


def test_p148_the_templates_are_recomputable_from_the_manual() -> None:
    """门槛：模板 69 / body 113 / references 23 / self_references 4，且**0** 错（逐条复算）。"""
    module = _check_tool()
    errors, _notes, counts = module.check(REPO_ROOT)
    assert errors == [], "\n".join(errors)
    assert counts["templates"] == EXPECTED_TEMPLATES
    assert counts["bodies"] == EXPECTED_BODIES
    assert counts["references"] == EXPECTED_REFERENCES
    assert counts["self_references"] == EXPECTED_SELF_REFERENCES
    assert counts["unverifiable"] == 0


def test_p148_the_twelve_new_templates_are_verbatim_manual_examples() -> None:
    """门槛：12 条新模板逐字节等于手册示例条目，且零 adjustments。"""
    registry = _registry()
    module = _check_tool()
    examples = module.manual_examples(REPO_ROOT)
    assert set(NEW_TEMPLATE_ORIGINS) == set(NEW_TEMPLATE_KEYS)
    for key, (uri, example, item_id) in NEW_TEMPLATE_ORIGINS.items():
        template = registry.write_template(key)
        assert template is not None, key
        assert template.source == "manual_example", key
        assert template.origin == (f"{uri}#{example}" if example else uri), key
        assert template.wrapper == "Assign", key
        manual = module.manual_item(examples, uri=uri, example=example, item_id=item_id)
        assert manual is not None, key
        assert template.body == manual, key


def test_p148_the_new_chains_declare_only_the_documented_prerequisites() -> None:
    """门槛：7 条零前置链 + 5 条**既有**机制（`DB.STLD` 工况 / 反向依赖 / `references`）。"""
    registry = _registry()
    for key in ZERO_PREREQUISITE_KEYS:
        template = registry.write_template(key)
        assert template is not None, key
        assert template.prerequisites == (), key
        assert template.self_references == (), key
        assert template.target_id_source == "", key
    for key in STLD_CHAIN_KEYS:
        template = registry.write_template(key)
        assert template is not None, key
        assert [(item.key, item.item_id) for item in template.prerequisites] == [
            ("DB.STLD", "1"),
            ("DB.STLD", "2"),
        ], key
        assert all(item.id_source == "allocated" for item in template.prerequisites), key
        # 前置工况名必须与目标请求体里引用的工况名**逐条**对齐
        names = [str(item.body["NAME"]) for item in template.prerequisites]
        assert all(name in str(template.body) for name in names), key
    node_template = registry.write_template(NODE_TARGET_KEY)
    assert node_template is not None
    assert node_template.target_id_source == "DB.NODE#1"
    assert node_template.target_id_source in {item.label() for item in node_template.prerequisites}
    assert [item.key for item in node_template.prerequisites] == ["DB.NODE"]
    matl_template = registry.write_template(MATL_REFERENCE_KEY)
    assert matl_template is not None
    assert [item.key for item in matl_template.prerequisites] == ["DB.MATL"]
    assert [
        (reference.in_label, reference.path)
        for reference in matl_template.prerequisites[0].references
    ] == [("owner", ("MATL",))]


def test_p148_imfm_is_honestly_left_out_with_native_evidence() -> None:
    """门槛（R105）：`DB.IMFM` **没有**模板 ⇒ 不入候选；成因**不是**数据缺陷。"""
    registry = _registry()
    module = _check_tool()
    examples = module.manual_examples(REPO_ROOT)
    assert registry.write_template(LEFT_OUT_KEY) is None
    assert LEFT_OUT_KEY not in _probe("GEN_NX").candidate_keys()
    # 数据侧**未**被改动：端点仍启用、仍可写、仍 `verified`
    definition = registry.endpoint(LEFT_OUT_KEY)
    assert definition.enabled is True
    assert definition.availability == "verified"
    methods = registry.methods_for(key=LEFT_OUT_KEY, product="GEN_NX")
    assert {"POST", "GET", "DELETE"} <= set(methods)
    # 成因**不是**「Schema 缺字段」：被拒的**两个**条目的每个字段都在请求 Schema 里声明
    for uri, example, item_id in LEFT_OUT_ORIGINS:
        body = module.manual_item(examples, uri=uri, example=example, item_id=item_id)
        assert body is not None, item_id
        properties = set((registry.effective_schema(LEFT_OUT_KEY) or {}).get("properties") or {})
        wrapper = (registry.effective_schema(LEFT_OUT_KEY) or {}).get("properties") or {}
        accepted = set(properties) | set((wrapper.get("Argument") or {}).get("properties") or {})
        assert set(body) <= accepted, (item_id, sorted(set(body) - accepted))


def test_p148_the_introspection_first_gate_has_no_unknown_field() -> None:
    """门槛（判定 4）：本批 13 个端点的「手册示例字段 ∉ 本 build 接受字段」计数全为 **0**。"""
    module = _check_tool()
    examples = module.manual_examples(REPO_ROOT)
    assert set(INTROSPECTED_KEYS) == set(INTROSPECT_UNKNOWN_FIELDS)
    assert set(INTROSPECT_UNKNOWN_FIELDS.values()) == {0}
    # 对照物（R101 的 `DB.ACTL`）：手册示例用 `CLATS`，而本 build 的只读自省记录的是 `ACWC`
    actl = module.manual_item(examples, uri="db/ACTL", example="Main Control Data", item_id="1")
    assert actl is not None
    assert "CLATS" in set(actl)
    assert _registry().write_template("DB.ACTL") is None
    for key in INTROSPECTED_KEYS:
        assert key != "DB.ACTL", key


# ===== 3. 离线三步链（判定 5）=====


async def test_p148_the_twelve_chains_run_offline_with_zero_residue() -> None:
    """门槛：12 个新端点逐个「创建 → 读回 → 按路径 key 删除」，请求体逐字节等于模板。"""
    registry = _registry()
    for key in NEW_TEMPLATE_KEYS:
        template = registry.write_template(key)
        assert template is not None, key
        code = key.split(".", 1)[1]
        transport = p139._NxStore(
            codes=("DB.NODE", "DB.ELEM", "DB.MATL", "DB.SECT", "DB.STLD", key)
        )
        probe = _probe("GEN_NX", only=(key,), transport=transport)
        outcome = await probe.probe_key(key)
        assert outcome.outcome == WRITE_PROBE_PASSED, (key, outcome)
        assert outcome.created_id == "1", key
        assert outcome.read_back is True and outcome.deleted is True, key
        assert outcome.payload_source == "manual_example", (key, outcome.payload_source)
        # 目标请求体**逐字节**等于数据侧模板（包装为 `Assign` + 自建编号）
        assert ("POST", f"/DB/{code}", {"Assign": {"1": template.body}}) in transport.calls, key
        assert f"/DB/{code}/1" in transport.paths(), key
        # 删除**带路径 key**，收尾时该端点为空（零残留）
        assert transport.rows[code] == {}, key
        for sentinel in EMPTINESS_GATE_KEYS:
            assert transport.rows[sentinel.split(".", 1)[1]] == {}, (key, sentinel)
        for prerequisite in template.prerequisites:
            prereq_code = prerequisite.key.split(".", 1)[1]
            assert transport.rows[prereq_code] == {}, (key, prerequisite.label())


# ===== 4. 口径（判定 6）=====


def test_p148_coverage_counts_fifty_eight_of_609() -> None:
    """门槛：分子 = L5 `PASSED` 去重 key；70 / 633（`model_write_ratio` 70 / 434）。
    P149-B2 续跑起（分块补测 67 条 → 再 +9 真实 L5 `PASSED`）。"""
    registry = _registry()
    keys = CANDIDATES_BY_PRODUCT["GEN_NX"]
    coverage = write_path_coverage(registry, [_Row(key) for key in keys])
    assert coverage.total == WRITE_PATH_TOTAL
    assert coverage.covered == len(keys) == 70
    assert coverage.ratio == "70 / 633"
    assert coverage.model_write == MODEL_WRITE_TOTAL
    assert coverage.model_write_covered == 70
    assert coverage.model_write_ratio == "70 / 434"
    assert set(coverage.covered_keys) == set(keys)


def test_p148_the_sub_bucket_never_hides_an_uncovered_endpoint() -> None:
    """门槛：子桶口径**不**过滤、**不**隐藏 —— 只给 CIVIL NX 的 60 条时原分子仍为 60。"""
    registry = _registry()
    civil_keys = CANDIDATES_BY_PRODUCT["CIVIL_NX"]
    civil = write_path_coverage(registry, [_Row(key) for key in civil_keys])
    assert civil.covered == len(civil_keys) == 60
    assert civil.total == WRITE_PATH_TOTAL
    assert civil.ratio == "60 / 633"


def test_p148_the_twelve_new_keys_are_delivered_by_the_data_side_only() -> None:
    """门槛：模板是**数据** —— `app/**` 里 0 处模板取值（红线：Core 不得硬编码数据）。"""
    app_root = REPO_ROOT / "app"
    offenders: list[str] = []
    for path in app_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for literal in CORE_FORBIDDEN_LITERALS:
            if literal in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{literal}")
    assert offenders == []
