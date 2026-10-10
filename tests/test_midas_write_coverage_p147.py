"""P147：写路径覆盖推进**第四批**（13 个端点 → 10 个入候选并跑通；3 个如实留缺 R104）。

权威来源
--------
- `docs/07` §16 **R4 / R14 / R97** · §16.1 **R100**（候选判据 + 「能建必须能删」）·
  §16.1 **R101**（手册示例与本 build 字段集不一致 ⇒ 如实留缺）· §16.1 **R102**（键必须是名字 ⇒
  模板机制无法表达）· §16.1 **R103**（手册示例被本 build 拒绝 / 建了读不回 ⇒ 如实留缺）·
  §16.1 **R104**（本批新增：**只读**自省先行 + 一次批量定位，手册示例仍被拒 ⇒ 如实留缺）。
- `registry/README.md` §2.3 / §8.7 · `registry/live/write_templates.json`。
- `docs/reports/P147_写路径覆盖推进第四批_v1.0.md`（本批证据）。

本文件的**可执行判定**
--------------------
1. **候选判据（R100 未放宽）**：本批 GEN NX **36 → 46**、CIVIL NX **32 → 39**、
   Civil Designer 仍 **0**；「既无 Transformer 又无模板」的端点数随之 **517 → 507** /
   **450 → 443** / **31**（逐产品可复算）。
2. **本批 10 条模板全部是手册示例的**逐字节**照抄**（`manual_example`、零 adjustments、零前置链）——
   `DB.POGD` / `DB.POSP` / `DB.SDHY` / `DB.SDIS` / `DB.SDST` / `DB.SDVE` / `DB.SDVI` /
   `DB.TDGR` / `DB.TDME` / `DB.TDMT`；真实 L5 批量 **46 / 46 `PASSED`**（GEN NX 空项目；
   逐条「创建 → 读回 → 按路径 key 删除」）。
3. **3 个端点如实留缺（R104）**：`DB.MVCT` / `DB.TDMF` / `DB.THGC` 的手册示例被本 build
   **拒绝**（`POST` → `400 software_api_error`，与 R103 的 `DB.SKEW` 同形）⇒ 模板**不写**、
   不入候选；数据侧**未**被改动（端点仍 `enabled` / `verified` / 写方法齐全，且手册示例的
   **每个**字段都在请求 Schema 里声明 —— 成因**不是**数据缺陷）。
4. **落盘前的只读自省**：10 条新模板与 3 条留缺端点**全部**先用**只读**
   `GET /info/db/<CODE>` 核对「手册示例字段 ⊆ 本 build 接受字段」；本批 13 个端点的
   `unknown` 字段数 = **0**（`DB.ACTL` 的 `CLATS` 是 R101 的对照物，仍**不**纳入）。
5. **离线三步链**：10 个新端点逐个跑通「创建 → 读回 → 按路径 key 删除」，发送的请求体**逐字节**
   等于数据侧模板 `body`，跑完**零残留**。
6. **口径不变**：分母仍 `write_path_keys()`（P149-A 起 **633**，`model_write` 子桶 **434**；
   P148 为 609 / 410）；分子 = L5 `PASSED` 去重 key（P147 时 **46 / 609**、
   `model_write_ratio` **46 / 410**；P149-B2 起 **61 / 633** / **61 / 434**）。
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
    EMPTINESS_GATE_KEYS,
    WRITE_METHODS,
    WRITE_PROBE_PASSED,
    MidasLiveWriteProbe,
    transformer_name_for,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录（数据侧工具与上游手册都在这里）。"""

CHECK_TOOL_PATH = REPO_ROOT / "registry" / "tools" / "check_write_templates.py"
"""模板复算工具（本批新增 10 条后仍必须 0 错）。"""

WRITE_PATH_TOTAL = 633
"""写路径端点数 —— R4 / R14 的**正式**分母（**不挪**口径；P149-A 起 **633**，P148 为 609）。"""

MODEL_WRITE_TOTAL = 434
"""分母里的「模型写」子桶（P141 裁决⑤；P148 为 410）。"""

NEW_TEMPLATE_KEYS = (
    "DB.POGD",
    "DB.POSP",
    "DB.SDHY",
    "DB.SDIS",
    "DB.SDST",
    "DB.SDVE",
    "DB.SDVI",
    "DB.TDGR",
    "DB.TDME",
    "DB.TDMT",
)
"""本批**跑通**的 10 个端点（全部**只有数据侧模板**、没有 Transformer、零前置链）。"""

NEW_TEMPLATE_ORIGINS: dict[str, tuple[str, str, str]] = {
    "DB.POGD": ("db/POGD", "Pushover Analysis Control Data", "1"),
    "DB.POSP": ("db/POSP", "Import to Json", "1"),
    "DB.SDHY": ("db/SDHY", "Hysteretic Isolator(MSS)", "1"),
    "DB.SDIS": ("db/SDIS", "Isolator(MSS)", "1"),
    "DB.SDST": ("db/SDST", "Steel Damper", "1"),
    "DB.SDVE": ("db/SDVE", "Viscoelastic Damper", "1"),
    "DB.SDVI": ("db/SDVI", "Viscous Damper/Oil Damper", "1"),
    "DB.TDGR": ("db/TDGR", "Tendon Group", "1"),
    "DB.TDME": ("db/TDME", "ACI", "1"),
    "DB.TDMT": ("db/TDMT", "CEB-FIP 2010, 1990, 1978", "1"),
}
"""10 条模板各自的来源定位（上游手册 `input_uri` / 示例名 / 示例条目编号）。"""

LEFT_OUT_KEYS = ("DB.MVCT", "DB.TDMF", "DB.THGC")
"""本批**如实留缺**的 3 个端点（R104）：手册示例被本 build 拒绝（`400 software_api_error`）。"""

LEFT_OUT_CAUSE: dict[str, str] = {
    "DB.MVCT": "manual_example_rejected_by_build",
    "DB.TDMF": "manual_example_rejected_by_build",
    "DB.THGC": "manual_example_rejected_by_build",
}
"""逐条成因（与 `docs/reports/P147_*` §3 的原生证据一一对应）。"""

LEFT_OUT_ORIGINS: dict[str, tuple[str, str, str]] = {
    "DB.MVCT": ("db/MVCT", "General", "1"),
    "DB.TDMF": ("db/TDMF", "Creep Coefficient", "1"),
    "DB.THGC": ("db/THGC", "Time History Global Control", "1"),
}
"""留缺端点被拒的**具体**手册条目（同样逐条可复算）。"""

INTROSPECTED_KEYS = NEW_TEMPLATE_KEYS + LEFT_OUT_KEYS
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
    ),
    "CIVIL_DESIGNER": (),
}
"""三产品各自的候选集（**61 / 52 / 0**；P149-B2 起；`CIVIL_DESIGNER` = 空，见 R99）。"""

BLOCKED_TOTAL: dict[str, int] = {"GEN_NX": 512, "CIVIL_NX": 448, "CIVIL_DESIGNER": 31}
"""「有写方法 + 非危险形态，但既无 Transformer 又无数据侧模板」的端点数。

P149-B2 起 **512 / 448 / 31**（P149-A 为 515 / 451 / 31；P148 为 495 / 433 / 31）。"""

EXPECTED_TEMPLATES = 60
"""模板条数（P149-B2 起 **60** = P148 的 57 + P149-B2 的 3）。"""

EXPECTED_BODIES = 104
"""复算的 body 总数（P149-B2 起 **104** = 60 个目标 + 44 个前置对象）。"""

EXPECTED_REFERENCES = 23
"""`prerequisites[].references` 的条数（P148 起 **23** = P147 的 22 + P148 的 1）。"""

EXPECTED_SELF_REFERENCES = 4
"""模板 `self_references` 的条数（P148 起仍为 **4**：目标编号由 `target_id_source` 承担）。"""


def _check_tool() -> Any:
    """按路径装载 `registry/tools/check_write_templates.py`（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(
        "structai_check_write_templates_p147", CHECK_TOOL_PATH
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
        project=DedicatedTestProject(name="p147"),
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


def test_p147_the_candidate_gate_counts_46_and_39_and_0() -> None:
    """门槛：三产品候选集 **61 / 52 / 0**、blocked **512 / 448 / 31**（P149-B2：+3 个真实 L5
    `PASSED` 候选 `DB.BNGR` / `DB.GRUP` / `DB.NPLN`），逐产品可复算。"""
    registry = _registry()
    for product, expected in CANDIDATES_BY_PRODUCT.items():
        derived, blocked = _derived_candidates(registry, product)
        assert derived == expected, product
        assert blocked == BLOCKED_TOTAL[product], product
        assert _probe(product).candidate_keys() == expected, product
    # 本批 10 个新端点全部**只有模板**（没有 Transformer）—— 这正是 R100 打开的那条路
    for key in NEW_TEMPLATE_KEYS:
        assert TRANSFORMER_REGISTRY.get(transformer_name_for(key)) is None, key
        assert registry.write_template(key) is not None, key
        assert key in CANDIDATES_BY_PRODUCT["GEN_NX"], key
    # 每个候选在该产品上都必须**能删**（R100）
    for product, keys in CANDIDATES_BY_PRODUCT.items():
        for key in keys:
            assert "DELETE" in registry.methods_for(key=key, product=product), (product, key)


# ===== 2. 数据侧模板（判定 2 / 3）=====


def test_p147_the_templates_are_recomputable_from_the_manual() -> None:
    """门槛：模板 60 / body 104 / references 23 / self_references 4，且**0** 错（逐条复算）。"""
    module = _check_tool()
    errors, _notes, counts = module.check(REPO_ROOT)
    assert errors == [], "\n".join(errors)
    assert counts["templates"] == EXPECTED_TEMPLATES
    assert counts["bodies"] == EXPECTED_BODIES
    assert counts["references"] == EXPECTED_REFERENCES
    assert counts["self_references"] == EXPECTED_SELF_REFERENCES
    assert counts["unverifiable"] == 0


def test_p147_the_ten_new_templates_are_verbatim_manual_examples() -> None:
    """门槛：10 条新模板逐字节等于手册示例条目，且零 adjustments / 零前置 / 零自引用。"""
    registry = _registry()
    module = _check_tool()
    examples = module.manual_examples(REPO_ROOT)
    assert set(NEW_TEMPLATE_ORIGINS) == set(NEW_TEMPLATE_KEYS)
    for key, (uri, example, item_id) in NEW_TEMPLATE_ORIGINS.items():
        template = registry.write_template(key)
        assert template is not None, key
        assert template.source == "manual_example", key
        assert template.origin == f"{uri}#{example}", key
        assert template.prerequisites == (), key
        assert template.self_references == (), key
        assert template.target_id_source == "", key
        assert template.wrapper == "Assign", key
        manual = module.manual_item(examples, uri=uri, example=example, item_id=item_id)
        assert manual is not None, key
        assert template.body == manual, key


def test_p147_mvct_tdmf_and_thgc_are_honestly_left_out_with_native_evidence() -> None:
    """门槛（R104）：3 个端点**没有**模板 ⇒ 不入候选；成因**不是**数据缺陷。"""
    registry = _registry()
    module = _check_tool()
    examples = module.manual_examples(REPO_ROOT)
    assert set(LEFT_OUT_KEYS) == set(LEFT_OUT_CAUSE)
    assert set(LEFT_OUT_KEYS) == set(LEFT_OUT_ORIGINS)
    for key in LEFT_OUT_KEYS:
        assert registry.write_template(key) is None, key
        assert key not in _probe("GEN_NX").candidate_keys(), key
        # 数据侧**未**被改动：端点仍启用、仍可写、仍 `verified`
        definition = registry.endpoint(key)
        assert definition.enabled is True, key
        assert definition.availability == "verified", key
        methods = registry.methods_for(key=key, product="GEN_NX")
        assert {"POST", "GET", "DELETE"} <= set(methods), key
        # 成因**不是**「Schema 缺字段」：被拒条目的每个字段都在请求 Schema 里声明
        uri, example, item_id = LEFT_OUT_ORIGINS[key]
        body = module.manual_item(examples, uri=uri, example=example, item_id=item_id)
        assert body is not None, key
        properties = set((registry.effective_schema(key) or {}).get("properties") or {})
        assert set(body) <= properties, (key, sorted(set(body) - properties))


def test_p147_the_introspection_first_gate_has_no_unknown_field() -> None:
    """门槛（判定 4）：本批 13 个端点的「手册示例字段 ∉ 本 build 接受字段」计数全为 **0**。"""
    registry = _registry()
    module = _check_tool()
    examples = module.manual_examples(REPO_ROOT)
    assert set(INTROSPECTED_KEYS) == set(INTROSPECT_UNKNOWN_FIELDS)
    assert set(INTROSPECT_UNKNOWN_FIELDS.values()) == {0}
    # 对照物（R101 的 `DB.ACTL`）：手册示例用 `CLATS`，而 P144 的**只读自省**（`GET /info/db/ACTL`）
    # 记录本 build 接受的字段集里是 `ACWC` —— 数据侧 Schema 里**也有** `CLATS`（来自 help_center），
    # 所以「Schema 声明」不足以判定 build 是否接受 —— 这正是本批「先只读自省再落模板」要拦的形态，
    # 本批 13 个端点**无一**命中（见 `docs/reports/P144_*` §2）。
    actl = module.manual_item(examples, uri="db/ACTL", example="Main Control Data", item_id="1")
    assert actl is not None
    assert "CLATS" in set(actl)
    assert registry.write_template("DB.ACTL") is None
    actl_properties = set((registry.effective_schema("DB.ACTL") or {}).get("properties") or {})
    assert "CLATS" in actl_properties
    p144_report = (REPO_ROOT / "docs" / "reports" / "P144_写路径覆盖推进第一批_v1.0.md").read_text(
        encoding="utf-8"
    )
    assert "ACWC" in p144_report
    assert "CLATS" in p144_report
    for key in INTROSPECTED_KEYS:
        assert key != "DB.ACTL", key


# ===== 3. 离线三步链（判定 5）=====


async def test_p147_the_ten_chains_run_offline_with_zero_residue() -> None:
    """门槛：10 个新端点逐个「创建 → 读回 → 按路径 key 删除」，请求体逐字节等于模板。"""
    registry = _registry()
    for key in NEW_TEMPLATE_KEYS:
        template = registry.write_template(key)
        assert template is not None, key
        code = key.split(".", 1)[1]
        transport = p139._NxStore(codes=("DB.NODE", "DB.ELEM", "DB.MATL", "DB.SECT", key))
        probe = _probe("GEN_NX", only=(key,), transport=transport)
        outcome = await probe.probe_key(key)
        assert outcome.outcome == WRITE_PROBE_PASSED, (key, outcome)
        assert outcome.created_id == "1", key
        assert outcome.read_back is True and outcome.deleted is True, key
        assert outcome.payload_source == "manual_example", (key, outcome.payload_source)
        assert outcome.prerequisites == (), key
        # 目标请求体**逐字节**等于数据侧模板（包装为 `Assign` + 自建编号）
        assert ("POST", f"/DB/{code}", {"Assign": {"1": template.body}}) in transport.calls, key
        assert f"/DB/{code}/1" in transport.paths(), key
        # 删除**带路径 key**，收尾时该端点为空（零残留）
        assert transport.rows[code] == {}, key
        for sentinel in EMPTINESS_GATE_KEYS:
            assert transport.rows[sentinel.split(".", 1)[1]] == {}, (key, sentinel)


# ===== 4. 口径（判定 6）=====


def test_p147_coverage_counts_forty_six_of_609() -> None:
    """门槛：分子 = L5 `PASSED` 去重 key；61 / 633（`model_write_ratio` 61 / 434；P149-B2 起）。"""
    registry = _registry()
    keys = CANDIDATES_BY_PRODUCT["GEN_NX"]
    coverage = write_path_coverage(registry, [_Row(key) for key in keys])
    assert coverage.total == WRITE_PATH_TOTAL
    assert coverage.covered == len(keys) == 61
    assert coverage.ratio == "61 / 633"
    assert coverage.model_write == MODEL_WRITE_TOTAL
    assert coverage.model_write_covered == 61
    assert coverage.model_write_ratio == "61 / 434"
    assert set(coverage.covered_keys) == set(keys)


def test_p147_the_sub_bucket_never_hides_an_uncovered_endpoint() -> None:
    """门槛：子桶口径**不**过滤、**不**隐藏 —— 只给 CIVIL NX 的 52 条时原分子仍为 52。"""
    registry = _registry()
    civil = write_path_coverage(registry, [_Row(key) for key in CANDIDATES_BY_PRODUCT["CIVIL_NX"]])
    assert civil.covered == len(CANDIDATES_BY_PRODUCT["CIVIL_NX"]) == 52
    assert civil.total == WRITE_PATH_TOTAL
    assert civil.ratio == "52 / 633"


def test_p147_the_ten_new_keys_are_delivered_by_the_data_side_only() -> None:
    """门槛：模板是**数据** —— `app/**` 里 0 处模板取值（红线：Core 不得硬编码数据）。"""
    # 只挑**模板取值本身**（`body` 里独有的字面量）—— 通用术语（如 Soil-1 / SteelDamper01）
    # 会与领域文档引用撞车，**不**能当作「Core 硬编码数据」的证据
    literals = (
        "SteelDamper01",
        "Viscoelastic01",
        "VisDamper01",
        "HystereticIsolater01",
        "Isolator01",
        "In_Pre_Magura",
    )
    app_root = REPO_ROOT / "app"
    offenders: list[str] = []
    for path in app_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for literal in literals:
            if literal in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{literal}")
    assert offenders == []
