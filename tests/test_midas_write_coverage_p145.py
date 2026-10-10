"""P145：写路径覆盖推进**第二批**（12 个端点 → 11 个入候选并跑通，`DB.HPCE` 如实留缺）。

权威来源
--------
- `docs/07` §16 **R4 / R14 / R97** · §16.1 **R100**（候选判据 + 「能建必须能删」）·
  §16.1 **R101**（手册示例与本 build 不一致 ⇒ 如实留缺）· §16.1 **R102**（本批新增：
  目标编号必须是**名字**（或手册示例缺必填字段）时，模板机制**无法表达** ⇒ 如实留缺）。
- `registry/README.md` §2.3 / §8.7 · `registry/live/write_templates.json`。
- `docs/reports/P145_写路径覆盖推进第二批_v1.0.md`（本批证据）。

本文件的**可执行判定**
--------------------
1. **候选判据（R100 未放宽）**：候选 = 「有写方法 ∧ 有读路径 ∧（Transformer 已注册 ∨
   有数据侧模板）∧ 有 `DELETE` ∧ 非危险 ∧ 产品可得」；本批 GEN NX **18 → 29**、
   CIVIL NX **17 → 25**、Civil Designer 仍 **0**；「既无 Transformer 又无模板」的端点数
   随之 **535 → 524** / **465 → 457** / **32 → 31**（逐产品可复算）。
2. **本批 12 条模板的**三种**结局（每条都有原生证据）**：
   - **11 条跑通**（`DB.DCTL` / `DB.EPMT` / `DB.FIMP` / `DB.HSFC` / `DB.IEHC` / `DB.LENG` /
     `DB.MBTP` / `DB.MLFC` / `DB.MVCD` / `DB.MVHLTR` / `DB.PDEL`）—— 均为**只有数据侧模板**、
     没有 Transformer 的端点（R100 打开的那条路）；
   - **`DB.LENG` / `DB.MBTP`**：**按构件号取值**的端点（空项目没有构件 ⇒ 手册形态 400
     `Not Found Key`）→ 用**声明式前置链**救回：`DB.MATL#1` + `DB.SECT#1` +
     `DB.NODE#1/#2` + `DB.ELEM#1`，并让**目标自身**的 `Assign` 键取该单元的编号
     （`target_id_source = "DB.ELEM#1"`，R96 的反向依赖）—— 请求体**原样**照抄手册；
   - **`DB.MVHLTR`**：手册示例**条目 1** 缺 3 个必填字段（`ML` / `MW` / `LEFT_LANES`）
     ⇒ 400 `Wrong Field`；**条目 2** 自带这三个字段 ⇒ 把 `source.example_id` 由 `"1"` 改为
     `"2"` 即可（**仍是** `manual_example`，无 adjustments）。
3. **`DB.HPCE` 如实留缺（R102）**：手册形态在本 build（`gen-local`）上**六种**键形态全部
   被拒或静默 no-op —— `Assign` 数字键 → `400 Wrong Key`（键 1 / 2、带/不带
   `START_TIME` / `END_TIME`、空 `ITEMS` 均同）；`Assign` **名字键** → `200` 但**不落库**
   （GET 仍空，即使 `ITEMS` 指向**已建**节点）；顶层 `HPCE` / `Argument` → `400 Wrong Field`。
   ⇒ 该端点的 `Assign` 键**不是**编号，而模板机制只写回**整数**编号 ⇒ **无法表达**；
   模板**不写**、不入候选（判定**不**放宽）。⚠️ 与 R101 的三条并列，共 **4** 个留缺端点。
4. **离线三步链**：`DB.LENG` / `DB.MBTP` / `DB.MVHLTR` 逐个跑通「建前置 → 创建 → 读回 →
   按路径 key 删除」，发送的请求体**逐字节**等于数据侧模板 `body`，跑完**零残留**。
5. **口径不变**：分母仍 `write_path_keys()`（P149-A 起 **633**，`model_write` 子桶 **434**；
   P148 为 609 / 410）；分子 = L5 `PASSED` 去重 key（P145 时 **29 / 609**、
   `model_write_ratio` **29 / 410**；P149-B2 续跑起 **70 / 633** / **70 / 434**）。
6. **跨产品**：CIVIL NX **25 / 25 `PASSED`**（云端 `201`）—— 分子按 **registry key** 去重，
   故**不**增加分子（跨产品是另一条证据）。
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import test_midas_write_templates_p139 as p139
from app.infrastructure.adapters.midas.live import DedicatedTestProject, write_path_coverage
from app.infrastructure.adapters.midas.registry import MidasRegistry
from app.infrastructure.adapters.midas.transforms import TRANSFORMER_REGISTRY
from app.infrastructure.adapters.midas.write_probe import (
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
    "DB.DCTL",
    "DB.EPMT",
    "DB.FIMP",
    "DB.HSFC",
    "DB.IEHC",
    "DB.LENG",
    "DB.MBTP",
    "DB.MLFC",
    "DB.MVCD",
    "DB.MVHLTR",
    "DB.PDEL",
)
"""本批**跑通**的 11 个端点（全部**只有数据侧模板**、没有 Transformer）。"""

ELEMENT_CHAIN_KEYS = ("DB.LENG", "DB.MBTP")
"""按**构件号**取值、用声明式前置链救回的两个端点。"""

ELEMENT_CHAIN_LABELS = (
    "DB.MATL#1",
    "DB.SECT#1",
    "DB.NODE#1",
    "DB.NODE#2",
    "DB.ELEM#1",
)
"""两个端点共用的前置链（材质 → 截面 → 两节点 → 一个梁单元）。"""

MVHLTR_KEY = "DB.MVHLTR"
"""手册示例**条目 1** 缺必填字段、改用**条目 2** 的端点。"""

MVHLTR_MISSING_FIELDS = ("ML", "MW", "LEFT_LANES")
"""条目 1 缺、条目 2 自带的三个**必填**字段（规格表 Required）。"""

HPCE_KEY = "DB.HPCE"
"""本批**如实留缺**的端点（R102：`Assign` 键必须是名字 ⇒ 模板机制无法表达）。"""

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
"""三产品各自的候选集（**70 / 60 / 0**；P149-B2 续跑起；`CIVIL_DESIGNER` = 空，见 R99）。"""

BLOCKED_TOTAL: dict[str, int] = {"GEN_NX": 503, "CIVIL_NX": 440, "CIVIL_DESIGNER": 31}
"""「有写方法 + 非危险形态，但既无 Transformer 又无数据侧模板」的端点数。

P149-B2 续跑起 **503 / 440 / 31**（P149-B2 首轮 512 / 448 / 31；P149-A 为 515 / 451 / 31）。"""

EXPECTED_TEMPLATES = 69
"""模板条数（P149-B2 续跑起 **69** = P149-B2 首轮的 60 + 本批 9）。"""

EXPECTED_BODIES = 113
"""复算的 body 总数（P149-B2 续跑起 **113** = 69 个目标 + 44 个前置对象）。"""

EXPECTED_REFERENCES = 23
"""`prerequisites[].references` 的条数（P148 起 **23** = P147 的 22 + P148 的 1）。"""

EXPECTED_SELF_REFERENCES = 4
"""模板 `self_references` 的条数（P148 起仍为 **4**：目标编号由 `target_id_source` 承担）。"""


def _check_tool() -> Any:
    """按路径装载 `registry/tools/check_write_templates.py`（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(
        "structai_check_write_templates_p145", CHECK_TOOL_PATH
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
        project=DedicatedTestProject(name="p145"),
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


@dataclass(frozen=True, slots=True)
class _Row:
    """`midas_api_verifications` 的最小只读投影（覆盖率只读 `endpoint_key` / 级别 / 结论）。"""

    endpoint_key: str
    contract_level: str = "L5"
    product: str = "GEN_NX"
    status: str = "PASSED"


# ===== 1. 候选判据（判定 1）=====


def test_p145_the_candidate_gate_counts_29_and_25_and_0() -> None:
    """门槛：三产品候选集 **70 / 60 / 0**、blocked **503 / 440 / 31**（P149-B2 续跑：分块补测 67
    条 → 再 +9 真实 L5 `PASSED`），逐产品可复算。"""
    registry = _registry()
    for product, expected in CANDIDATES_BY_PRODUCT.items():
        derived, blocked = _derived_candidates(registry, product)
        assert derived == expected, product
        assert blocked == BLOCKED_TOTAL[product], product
        assert _probe(product).candidate_keys() == expected, product
    # 本批 11 个新端点全部**只有模板**（没有 Transformer）—— 这正是 R100 打开的那条路
    for key in NEW_TEMPLATE_KEYS:
        assert TRANSFORMER_REGISTRY.get(transformer_name_for(key)) is None, key
        assert registry.write_template(key) is not None, key
        assert key in CANDIDATES_BY_PRODUCT["GEN_NX"], key
    # 每个候选在该产品上都必须**能删**（R100）
    for product, keys in CANDIDATES_BY_PRODUCT.items():
        for key in keys:
            assert "DELETE" in registry.methods_for(key=key, product=product), (product, key)


# ===== 2. 数据侧模板（判定 2 / 3）=====


def test_p145_the_templates_are_recomputable_from_the_manual() -> None:
    """门槛：模板 69 / body 113 / references 23 / self_references 4，且**0** 错（逐条复算）。"""
    module = _check_tool()
    errors, _notes, counts = module.check(REPO_ROOT)
    assert errors == [], "\n".join(errors)
    assert counts["templates"] == EXPECTED_TEMPLATES
    assert counts["bodies"] == EXPECTED_BODIES
    assert counts["references"] == EXPECTED_REFERENCES
    assert counts["self_references"] == EXPECTED_SELF_REFERENCES
    assert counts["unverifiable"] == 0
    for key in NEW_TEMPLATE_KEYS:
        assert _registry().write_template(key) is not None, key


def test_p145_leng_and_mbtp_take_the_element_id_via_the_declared_chain() -> None:
    """门槛：`DB.LENG` / `DB.MBTP` 的 body **原样**照抄手册；前置链 = 材质/截面/两节点/一单元。"""
    registry = _registry()
    module = _check_tool()
    examples = module.manual_examples(REPO_ROOT)
    for key, uri, example, item_id in (
        ("DB.LENG", "db/LENG", "Import to Json", "21"),
        ("DB.MBTP", "db/MBTP", "Import to Json", "160"),
    ):
        template = registry.write_template(key)
        assert template is not None, key
        assert template.source == "manual_example", key
        assert template.prerequisite_labels() == ELEMENT_CHAIN_LABELS, key
        # 目标自身编号**取前置单元**的编号（R96 的反向依赖；否则空项目上没有该构件）
        assert template.target_id_source == "DB.ELEM#1", key
        assert template.self_references == (), key
        # 每个前置的编号引用都指向 `DB.ELEM#1` 的 body（单元引用材质/截面/两节点）
        for prerequisite in template.prerequisites:
            if prerequisite.label() == "DB.ELEM#1":
                assert prerequisite.references == (), prerequisite.label()
                continue
            assert [reference.in_label for reference in prerequisite.references] == ["DB.ELEM#1"], (
                prerequisite.label()
            )
        # body 逐字节等于手册示例条目（**无** adjustments）
        manual = module.manual_item(examples, uri=uri, example=example, item_id=item_id)
        assert manual is not None, key
        assert template.body == manual, key


def test_p145_mvhltr_uses_the_second_manual_item_with_the_required_fields() -> None:
    """门槛：`DB.MVHLTR` 改用手册示例**条目 2**（自带 3 个必填字段），仍 `manual_example`。"""
    registry = _registry()
    module = _check_tool()
    examples = module.manual_examples(REPO_ROOT)
    template = registry.write_template(MVHLTR_KEY)
    assert template is not None
    assert template.source == "manual_example"
    assert template.origin == "db/MVHLtr#Vehicle - User Defined"
    first = module.manual_item(
        examples, uri="db/MVHLtr", example="Vehicle - User Defined", item_id="1"
    )
    second = module.manual_item(
        examples, uri="db/MVHLtr", example="Vehicle - User Defined", item_id="2"
    )
    assert first is not None and second is not None
    # 条目 1 缺三个必填字段（这就是 400 `Wrong Field` 的成因），条目 2 自带
    for field in MVHLTR_MISSING_FIELDS:
        assert field not in first, field
        assert field in second, field
    assert template.body == second
    assert template.prerequisites == ()
    assert template.target_id_source == ""


def test_p145_hpce_is_honestly_left_out_with_native_evidence() -> None:
    """门槛（R102）：`DB.HPCE` **没有**模板 ⇒ 不入候选；成因是键形态，**不是**数据缺陷。"""
    registry = _registry()
    assert registry.write_template(HPCE_KEY) is None
    assert HPCE_KEY not in _probe("GEN_NX").candidate_keys()
    # 数据侧**未**被改动：端点仍启用、仍可写（POST/PUT/DELETE 齐全）、仍 `verified`
    definition = registry.endpoint(HPCE_KEY)
    assert definition.enabled is True
    assert definition.availability == "verified"
    methods = registry.methods_for(key=HPCE_KEY, product="GEN_NX")
    assert {"POST", "GET", "DELETE"} <= set(methods)
    # 成因**不是**「Schema 缺字段」：手册示例的每个字段都在请求 Schema 里声明
    module = _check_tool()
    examples = module.manual_examples(REPO_ROOT)
    body = module.manual_item(examples, uri="db/HPCE", example="Pipe Cooling", item_id="1")
    assert body is not None
    properties = (_registry().effective_schema(HPCE_KEY) or {}).get("properties") or {}
    assert set(body) <= set(properties), sorted(set(body) - set(properties))


# ===== 3. 离线三步链（判定 4）=====


async def test_p145_the_three_chains_run_offline_with_zero_residue() -> None:
    """门槛：`DB.LENG` / `DB.MBTP` / `DB.MVHLTR` 逐个「建前置 → 创建 → 读回 → 删除」。"""
    registry = _registry()
    codes = ("DB.MATL", "DB.SECT", "DB.NODE", "DB.ELEM", "DB.LENG", "DB.MBTP", "DB.MVHLTR")
    for key in ("DB.LENG", "DB.MBTP", MVHLTR_KEY):
        body = registry.write_template(key).body
        transport = p139._NxStore(codes=codes)
        probe = _probe("GEN_NX", only=(key,), transport=transport)
        outcome = await probe.probe_key(key)
        assert outcome.outcome == WRITE_PROBE_PASSED, (key, outcome)
        assert outcome.created_id == "1", key
        assert outcome.read_back is True and outcome.deleted is True, key
        assert outcome.payload_source == "manual_example", (key, outcome.payload_source)
        # 目标请求体**逐字节**等于数据侧模板（包装为 `Assign` + 实分配编号）
        assert (
            "POST",
            f"/DB/{key.split('.', 1)[1]}",
            {"Assign": {"1": body}},
        ) in transport.calls, key
        # 前置链按声明顺序创建（`DB.ELEM` 取实分配编号 1）
        if key in ELEMENT_CHAIN_KEYS:
            assert outcome.prerequisites == ELEMENT_CHAIN_LABELS, key
        code = key.split(".", 1)[1]
        assert transport.rows[code] == {}, key
        assert f"/DB/{code}/1" in transport.paths(), key
        # 前置对象也按**逆序**删除：所有被触碰端点在收尾时都为空（零残留）
        for touched in ("DB.MATL", "DB.SECT", "DB.NODE", "DB.ELEM"):
            assert transport.rows[touched.split(".", 1)[1]] == {}, (key, touched)


# ===== 4. 口径（判定 5 / 6）=====


def test_p145_coverage_counts_thirty_six_of_609() -> None:
    """门槛：分子 = L5 `PASSED` 去重 key；70 / 633（`model_write_ratio` 70 / 434）。
    P149-B2 续跑起（分块补测 67 条 → 再 +9 真实 L5 `PASSED`）。"""
    registry = _registry()
    keys = CANDIDATES_BY_PRODUCT["GEN_NX"]
    coverage = write_path_coverage(registry, [_Row(key) for key in keys])
    assert coverage.total == WRITE_PATH_TOTAL
    assert coverage.covered == len(keys) == 70
    assert coverage.ratio == f"70 / {WRITE_PATH_TOTAL}"
    assert coverage.model_write_ratio == f"70 / {MODEL_WRITE_TOTAL}"
    assert set(coverage.covered_keys) == set(keys)
    # CIVIL NX 的候选（60）与 GEN NX 共用同一批 key 去重 ⇒ 分子**不**因跨产品而翻倍
    civil = write_path_coverage(
        registry, [_Row(key, product="CIVIL_NX") for key in CANDIDATES_BY_PRODUCT["CIVIL_NX"]]
    )
    assert civil.covered == 60
    assert civil.ratio == f"60 / {WRITE_PATH_TOTAL}"
    # 非 `L5` / 非 `PASSED` 行**不**计入（判据未放宽）
    assert write_path_coverage(registry, [_Row("DB.NODE", contract_level="L4")]).covered == 0
    assert write_path_coverage(registry, [_Row("DB.NODE", status="FAILED")]).covered == 0
