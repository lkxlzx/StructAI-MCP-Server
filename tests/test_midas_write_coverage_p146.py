"""P146：写路径覆盖推进**第三批**（10 个端点 → 7 个入候选并跑通；3 个如实留缺 R103）。

权威来源
--------
- `docs/07` §16 **R4 / R14 / R97** · §16.1 **R100**（候选判据 + 「能建必须能删」）·
  §16.1 **R101**（手册示例与本 build 字段集不一致 ⇒ 如实留缺）· §16.1 **R102**（键必须是名字 ⇒
  模板机制无法表达）· §16.1 **R103**（本批新增：手册示例被本 build 拒绝 / 建了读不回 ⇒ 如实留缺）。
- `registry/README.md` §2.3 / §8.7 · `registry/live/write_templates.json`。
- `docs/reports/P146_写路径覆盖推进第三批_v1.0.md`（本批证据）。

本文件的**可执行判定**
--------------------
1. **候选判据（R100 未放宽）**：本批 GEN NX **29 → 36**、CIVIL NX **25 → 32**、
   Civil Designer 仍 **0**；「既无 Transformer 又无模板」的端点数随之 **524 → 517** /
   **457 → 450** / **31**（逐产品可复算）。
2. **本批 7 条模板全部是手册示例的**逐字节**照抄**（`manual_example`、零 adjustments、零前置链）——
   `DB.LDGR` / `DB.PJCF` / `DB.PNLD` / `DB.SMCT` / `DB.SPFC` / `DB.THFC` / `DB.THIK`；
   真实 L5 批量 **36 / 36 `PASSED`**（GEN NX 空项目；逐条「创建 → 读回 → 按路径 key 删除」）。
3. **3 个端点如实留缺（R103）**：`DB.SKEW`（手册 **3** 个变体全 `400 software_api_error`）·
   `DB.HSPT` / `DB.MADO`（`POST 200` 但 `GET` **读不回** —— 与 R101 的 `DB.EDMP` 同形）
   ⇒ 模板**不写**、不入候选；数据侧**未**被改动（端点仍 `enabled` / `verified` / 写方法齐全，
   且手册示例的**每个**字段都在请求 Schema 里声明）。
4. **`DB.SSEIS` 的 Schema 形状（本批**不**纳入）**：其请求 Schema 把条目字段声明在
   `patternProperties`（`^[0-9]+$`）下，而复算工具**只**读 `properties` ⇒ 该端点在本工具口径下
   **不可判** ⇒ **不**改工具、**不**放宽判定、**不**写模板（留待工具支持该形状后再纳入）。
5. **离线三步链**：7 个新端点逐个跑通「创建 → 读回 → 按路径 key 删除」，发送的请求体**逐字节**
   等于数据侧模板 `body`，跑完**零残留**。
6. **口径不变**：分母仍 **609**（`model_write` 子桶 **410**）；分子 = L5 `PASSED` 去重 key
   （本批 **36 / 609**，`model_write_ratio` **36 / 410**）。
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
"""模板复算工具（本批新增 7 条后仍必须 0 错）。"""

WRITE_PATH_TOTAL = 609
"""写路径端点数 —— R4 / R14 的**正式**分母（**不挪**）。"""

MODEL_WRITE_TOTAL = 410
"""分母里的「模型写」子桶（P141 裁决⑤）。"""

NEW_TEMPLATE_KEYS = (
    "DB.LDGR",
    "DB.PJCF",
    "DB.PNLD",
    "DB.SMCT",
    "DB.SPFC",
    "DB.THFC",
    "DB.THIK",
)
"""本批**跑通**的 7 个端点（全部**只有数据侧模板**、没有 Transformer、零前置链）。"""

NEW_TEMPLATE_ORIGINS: dict[str, tuple[str, str, str]] = {
    "DB.LDGR": ("db/LDGR", "Load Group", "1"),
    "DB.PJCF": ("db/PJCF", "Project Information", "1"),
    "DB.PNLD": ("db/PNLD", "Points", "1"),
    "DB.SMCT": ("db/SMCT", "Settlement Analysis Control Data", "1"),
    "DB.SPFC": ("db/SPFC", "User Type", "1"),
    "DB.THFC": ("db/THFC", "Time Function", "4"),
    "DB.THIK": ("db/THIK", "In-plane & Out-of-plane has same value", "1"),
}
"""7 条模板各自的来源定位（上游手册 `input_uri` / 示例名 / 示例条目编号）。"""

LEFT_OUT_KEYS = ("DB.SKEW", "DB.HSPT", "DB.MADO")
"""本批**如实留缺**的 3 个端点（R103）：手册示例被本 build 拒绝 / 建了读不回。"""

LEFT_OUT_CAUSE: dict[str, str] = {
    "DB.SKEW": "manual_example_rejected_by_build",
    "DB.HSPT": "created_but_not_readable",
    "DB.MADO": "created_but_not_readable",
}
"""逐条成因（与 `docs/reports/P146_*` §3 的原生证据一一对应）。"""

SKEW_VARIANTS_TRIED = ("Angle Type", "3 Points Type", "Vector Type")
"""`DB.SKEW` 实测被拒的 **3** 个手册变体（全部 `400 software_api_error`）。"""

PATTERN_PROPERTIES_KEY = "DB.SSEIS"
"""请求 Schema 用 `patternProperties` 声明条目字段 ⇒ 复算工具口径下**不可判**（本批不纳入）。"""

CANDIDATES_BY_PRODUCT: dict[str, tuple[str, ...]] = {
    "GEN_NX": (
        "DB.BMLD",
        "DB.BODF",
        "DB.CCFC",
        "DB.CNLD",
        "DB.CONS",
        "DB.CUTL",
        "DB.DCON",
        "DB.DCTL",
        "DB.DSTL",
        "DB.EIGV",
        "DB.ELEM",
        "DB.EPMT",
        "DB.ETFC",
        "DB.FBLD",
        "DB.FIMP",
        "DB.GSTP",
        "DB.HSFC",
        "DB.IEHC",
        "DB.LDGR",
        "DB.LENG",
        "DB.MATL",
        "DB.MBTP",
        "DB.MLFC",
        "DB.MVCD",
        "DB.MVHLTR",
        "DB.NODE",
        "DB.PDEL",
        "DB.PJCF",
        "DB.PNLD",
        "DB.PRES",
        "DB.SECT",
        "DB.SMCT",
        "DB.SPFC",
        "DB.STLD",
        "DB.THFC",
        "DB.THIK",
    ),
    "CIVIL_NX": (
        "DB.BMLD",
        "DB.BODF",
        "DB.CCFC",
        "DB.CNLD",
        "DB.CONS",
        "DB.CUTL",
        "DB.DCON",
        "DB.EIGV",
        "DB.ELEM",
        "DB.EPMT",
        "DB.ETFC",
        "DB.FBLD",
        "DB.FIMP",
        "DB.GSTP",
        "DB.HSFC",
        "DB.IEHC",
        "DB.LDGR",
        "DB.MATL",
        "DB.MLFC",
        "DB.MVCD",
        "DB.MVHLTR",
        "DB.NODE",
        "DB.PDEL",
        "DB.PJCF",
        "DB.PNLD",
        "DB.PRES",
        "DB.SECT",
        "DB.SMCT",
        "DB.SPFC",
        "DB.STLD",
        "DB.THFC",
        "DB.THIK",
    ),
    "CIVIL_DESIGNER": (),
}
"""三产品各自的候选集（**36 / 32 / 0**；`CIVIL_DESIGNER` = 空，见 R99）。"""

BLOCKED_TOTAL: dict[str, int] = {"GEN_NX": 517, "CIVIL_NX": 450, "CIVIL_DESIGNER": 31}
"""「有写方法 + 非危险形态，但既无 Transformer 又无数据侧模板」的端点数。"""

EXPECTED_TEMPLATES = 35
"""模板条数（P145 的 28 + 本批 7）。"""

EXPECTED_BODIES = 71
"""复算的 body 总数（**71** = 35 个目标 + 36 个前置对象；本批未新增前置）。"""

EXPECTED_REFERENCES = 22
"""`prerequisites[].references` 的条数（本批未变）。"""

EXPECTED_SELF_REFERENCES = 4
"""模板 `self_references` 的条数（本批未变：7 条新模板都**没有**自引用编号）。"""


def _check_tool() -> Any:
    """按路径装载 `registry/tools/check_write_templates.py`（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(
        "structai_check_write_templates_p146", CHECK_TOOL_PATH
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
        project=DedicatedTestProject(name="p146"),
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


def test_p146_the_candidate_gate_counts_36_and_32_and_0() -> None:
    """门槛：三产品候选集 **36 / 32 / 0**、blocked **517 / 450 / 31**，逐产品可复算。"""
    registry = _registry()
    for product, expected in CANDIDATES_BY_PRODUCT.items():
        derived, blocked = _derived_candidates(registry, product)
        assert derived == expected, product
        assert blocked == BLOCKED_TOTAL[product], product
        assert _probe(product).candidate_keys() == expected, product
    # 本批 7 个新端点全部**只有模板**（没有 Transformer）—— 这正是 R100 打开的那条路
    for key in NEW_TEMPLATE_KEYS:
        assert TRANSFORMER_REGISTRY.get(transformer_name_for(key)) is None, key
        assert registry.write_template(key) is not None, key
        assert key in CANDIDATES_BY_PRODUCT["GEN_NX"], key
        assert key in CANDIDATES_BY_PRODUCT["CIVIL_NX"], key
    # 每个候选在该产品上都必须**能删**（R100）
    for product, keys in CANDIDATES_BY_PRODUCT.items():
        for key in keys:
            assert "DELETE" in registry.methods_for(key=key, product=product), (product, key)


# ===== 2. 数据侧模板（判定 2 / 3）=====


def test_p146_the_templates_are_recomputable_from_the_manual() -> None:
    """门槛：模板 35 / body 71 / references 22 / self_references 4，且**0** 错（逐条复算）。"""
    module = _check_tool()
    errors, _notes, counts = module.check(REPO_ROOT)
    assert errors == [], "\n".join(errors)
    assert counts["templates"] == EXPECTED_TEMPLATES
    assert counts["bodies"] == EXPECTED_BODIES
    assert counts["references"] == EXPECTED_REFERENCES
    assert counts["self_references"] == EXPECTED_SELF_REFERENCES
    assert counts["unverifiable"] == 0


def test_p146_the_seven_new_templates_are_verbatim_manual_examples() -> None:
    """门槛：7 条新模板逐字节等于手册示例条目，且零 adjustments / 零前置 / 零自引用。"""
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


def test_p146_skew_hspt_and_mado_are_honestly_left_out_with_native_evidence() -> None:
    """门槛（R103）：3 个端点**没有**模板 ⇒ 不入候选；成因**不是**数据缺陷。"""
    registry = _registry()
    module = _check_tool()
    examples = module.manual_examples(REPO_ROOT)
    assert set(LEFT_OUT_KEYS) == set(LEFT_OUT_CAUSE)
    for key in LEFT_OUT_KEYS:
        assert registry.write_template(key) is None, key
        assert key not in _probe("GEN_NX").candidate_keys(), key
        # 数据侧**未**被改动：端点仍启用、仍可写、仍 `verified`
        definition = registry.endpoint(key)
        assert definition.enabled is True, key
        assert definition.availability == "verified", key
        methods = registry.methods_for(key=key, product="GEN_NX")
        assert {"POST", "GET", "DELETE"} <= set(methods), key
    # `DB.SKEW`：手册的 **3** 个变体全被本 build 拒绝（400 software_api_error）——
    # 成因**不是**「Schema 缺字段」：三个变体的每个字段都在请求 Schema 里声明
    uri = str(registry.endpoint("DB.SKEW").uri)
    assert uri == "/DB/SKEW"
    properties = set((registry.effective_schema("DB.SKEW") or {}).get("properties") or {})
    assert len(SKEW_VARIANTS_TRIED) == 3
    for example, item_id in (
        ("Angle Type", "1"),
        ("3 Points Type", "2"),
        ("Vector Type", "3"),
    ):
        body = module.manual_item(examples, uri="db/SKEW", example=example, item_id=item_id)
        assert body is not None, example
        assert set(body) <= properties, sorted(set(body) - properties)
    # `DB.HSPT` / `DB.MADO`：手册示例的字段同样全在请求 Schema 里声明（POST 被接受但读不回）
    for key, (uri, example, item_id) in (
        ("DB.HSPT", ("db/HSPT", "Prescribed Temperature", "1")),
        ("DB.MADO", ("db/MADO", "Define Domain", "1")),
    ):
        body = module.manual_item(examples, uri=uri, example=example, item_id=item_id)
        assert body is not None, key
        properties = set((registry.effective_schema(key) or {}).get("properties") or {})
        assert set(body) <= properties, (key, sorted(set(body) - properties))


def test_p146_sseis_is_not_admitted_because_its_schema_shape_is_unjudgeable() -> None:
    """门槛（判定 4）：`DB.SSEIS` 的条目字段在 `patternProperties` 下 ⇒ 工具口径下**不可判**。"""
    registry = _registry()
    assert registry.write_template(PATTERN_PROPERTIES_KEY) is None
    assert PATTERN_PROPERTIES_KEY not in _probe("GEN_NX").candidate_keys()
    schema = registry.effective_schema(PATTERN_PROPERTIES_KEY) or {}
    assign = (schema.get("properties") or {}).get("Assign") or {}
    # 复算工具**只**读 `properties`（`request_schema()`），故该形状下 `body` 的字段判定不可判
    assert "properties" not in assign
    assert "^[0-9]+$" in (assign.get("patternProperties") or {})
    # 因此本批**不**纳入它 —— 端点本身仍是可写、已验证的（数据侧未被改动）
    definition = registry.endpoint(PATTERN_PROPERTIES_KEY)
    assert definition.enabled is True
    assert definition.availability == "verified"
    assert {"POST", "GET", "DELETE"} <= set(
        registry.methods_for(key=PATTERN_PROPERTIES_KEY, product="GEN_NX")
    )


# ===== 3. 离线三步链（判定 5）=====


async def test_p146_the_seven_chains_run_offline_with_zero_residue() -> None:
    """门槛：7 个新端点逐个「创建 → 读回 → 按路径 key 删除」，请求体逐字节等于模板。"""
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


def test_p146_coverage_counts_thirty_six_of_609() -> None:
    """门槛：分子 = L5 `PASSED` 去重 key；36 / 609（`model_write_ratio` 36 / 410）。"""
    registry = _registry()
    keys = CANDIDATES_BY_PRODUCT["GEN_NX"]
    coverage = write_path_coverage(registry, [_Row(key) for key in keys])
    assert coverage.total == WRITE_PATH_TOTAL
    assert coverage.covered == len(keys) == 36
    assert coverage.ratio == "36 / 609"
    assert coverage.model_write == MODEL_WRITE_TOTAL
    assert coverage.model_write_covered == 36
    assert coverage.model_write_ratio == "36 / 410"
    assert set(coverage.covered_keys) == set(keys)


def test_p146_the_sub_bucket_never_hides_an_uncovered_endpoint() -> None:
    """门槛：子桶口径**不**过滤、**不**隐藏 —— 只给 CIVIL NX 的 32 条时原分子仍为 32。"""
    registry = _registry()
    civil = write_path_coverage(registry, [_Row(key) for key in CANDIDATES_BY_PRODUCT["CIVIL_NX"]])
    assert civil.covered == len(CANDIDATES_BY_PRODUCT["CIVIL_NX"]) == 32
    assert civil.total == WRITE_PATH_TOTAL
    assert civil.ratio == "32 / 609"


def test_p146_the_seven_new_keys_are_delivered_by_the_data_side_only() -> None:
    """门槛：模板是**数据** —— `app/**` 里 0 处模板取值（红线：Core 不得硬编码数据）。"""
    # 只挑**模板取值本身**（`body` 里独有的字面量）—— 通用术语（如 Load Group）会与领域
    # 文档引用撞车，**不**能当作「Core 硬编码数据」的证据
    literals = (
        "Point_examples",
        "ElCentroSite_Scale",
        "RS_func",
        "CableBridge",
    )
    app_root = REPO_ROOT / "app"
    offenders: list[str] = []
    for path in app_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for literal in literals:
            if literal in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{literal}")
    assert offenders == []
