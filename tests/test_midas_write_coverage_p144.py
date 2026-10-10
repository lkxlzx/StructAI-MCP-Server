"""P144 —— 写路径覆盖继续扩大（第一批：**数据侧模板**即可入候选；R100）。

权威来源
--------
- `docs/07` §16 **R4 / R14 / R97** · §16.1 **R100**（本批新增：候选判据 + 「能建必须能删」）·
  §16.1 **R101**（手册示例与本 build 字段集不一致的 3 个端点，如实留缺）。
- `registry/README.md` §2.3 / §8.7 · `registry/live/write_templates.json`。
- `docs/reports/P144_写路径覆盖推进第一批_v1.0.md`（本批证据）。

本文件的**可执行判定**
--------------------
1. **候选判据（R100）**：能构造**真实**请求体即可入候选 —— `Transformer` **已注册**
   （canonical↔native 映射）**或** 数据侧声明了请求体模板（**模板是数据**，不进 Core）；
   本批据此新增 **7** 个候选：`DB.CCFC` / `DB.CUTL` / `DB.DCON` / `DB.DSTL` /
   `DB.EIGV` / `DB.ETFC` / `DB.GSTP`。
2. **「能建必须能删」（R100）**：该产品没有 `DELETE` 的端点**不**入候选 —— 否则三步链会
   「建了删不掉」，在真实项目里留下残留。
3. **包装键来自数据侧**：端点没有 Transformer 时，包装键取 `registry` 的
   `wrapper.write`（`Assign` / `none`）—— **不**臆造、**不**硬编码。
4. **离线三步链**：7 个新端点逐个跑通「创建 → 读回 → 按路径 key 删除」，发送的请求体**逐字节**
   等于数据侧模板的 `body`（包装为 `{"Assign": {"<实分配编号>": body}}`），跑完**零残留**。
5. **口径不变**：分母仍 **609**；分子 = L5 `PASSED` 去重 key（本批 **18 / 609**，
   `model_write_ratio` **18 / 410**；CIVIL NX **17** 个候选 —— `DB.DSTL` 的产品集只有 `GEN_NX`）。
6. **如实留缺（R101）**：`DB.ACTL` / `DB.CLWP` / `DB.EDMP` 三个端点**没有**模板 ——
   前两个是「手册示例与本 build 自省字段集不一致」（模板机制只能改值、不能改名），
   后一个是「按**构件号**取值」（空项目没有构件）⇒ 均**不**入候选。
"""

from __future__ import annotations

from dataclasses import dataclass

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

WRITE_PATH_TOTAL = 609
"""写路径端点数 —— R4 / R14 的**正式**分母（**不挪**）。"""

MODEL_WRITE_TOTAL = 410
"""分母里的「模型写」子桶（P141 裁决⑤）。"""

TEMPLATE_ONLY_KEYS = (
    "DB.CCFC",
    "DB.CUTL",
    "DB.DCON",
    "DB.DSTL",
    "DB.EIGV",
    "DB.ETFC",
    "DB.GSTP",
)
"""本批新增的 **7** 个「只有数据侧模板、没有 Transformer」的候选（R100）。"""

CANDIDATES_BY_PRODUCT: dict[str, tuple[str, ...]] = {
    "GEN_NX": (
        "DB.BMLD",
        "DB.BODF",
        "DB.CCFC",
        "DB.CNLD",
        "DB.CONS",
        "DB.CUTL",
        "DB.DCON",
        "DB.DSTL",
        "DB.EIGV",
        "DB.ELEM",
        "DB.ETFC",
        "DB.FBLD",
        "DB.GSTP",
        "DB.MATL",
        "DB.NODE",
        "DB.PRES",
        "DB.SECT",
        "DB.STLD",
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
        "DB.ETFC",
        "DB.FBLD",
        "DB.GSTP",
        "DB.MATL",
        "DB.NODE",
        "DB.PRES",
        "DB.SECT",
        "DB.STLD",
    ),
    "CIVIL_DESIGNER": (),
}
"""三产品各自的候选集（**18 / 17 / 0**）。"""

BLOCKED_TOTAL: dict[str, int] = {"GEN_NX": 535, "CIVIL_NX": 465, "CIVIL_DESIGNER": 32}
"""「有写方法 + 非危险形态，但既无 Transformer 又无数据侧模板」的端点数。"""

REJECTED_KEYS = ("DB.ACTL", "DB.CLWP", "DB.EDMP")
"""**如实留缺**的 3 个端点（R101）：手册示例与本 build 字段集不一致 / 按构件号取值。"""

NO_DELETE_SAMPLE = ("DB.BNGR", "DB.GRUP", "DB.UNIT", "DB.STYP")
"""有写方法但**没有** `DELETE` 的端点样例（R100：不入候选 —— 能建必须能删）。"""


@dataclass(frozen=True, slots=True)
class _Row:
    """`midas_api_verifications` 的最小只读投影。"""

    endpoint_key: str
    contract_level: str = "L5"
    status: str = "PASSED"


def _registry() -> MidasRegistry:
    """数据侧 Registry（`registry/` 的唯一权威来源）。"""
    return p139._registry()


def _probe(
    product: str, *, only: tuple[str, ...] = (), transport: object = None
) -> MidasLiveWriteProbe:
    """构造写路径探针（缺省用**空**假传输）。"""
    store = p139._NxStore(codes=()) if transport is None else transport
    return MidasLiveWriteProbe(
        p139._client(store),
        _registry(),
        product=product,
        project=DedicatedTestProject(name="p144"),
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


# ===== 1. 候选判据（判定 1 / 2 / 6）=====


def test_p144_the_candidate_gate_is_a_transformer_or_a_data_side_template() -> None:
    """门槛：候选 = 「Transformer 已注册 **或** 有数据侧模板」；三产品 18 / 17 / 0 可复算。"""
    registry = _registry()
    for product, expected in CANDIDATES_BY_PRODUCT.items():
        derived, blocked = _derived_candidates(registry, product)
        assert derived == expected, product
        assert blocked == BLOCKED_TOTAL[product], product
        assert _probe(product).candidate_keys() == expected, product
    # 本批新增的 7 个**只有模板**（没有 Transformer）—— 这正是 R100 打开的那条路
    for key in TEMPLATE_ONLY_KEYS:
        assert TRANSFORMER_REGISTRY.get(transformer_name_for(key)) is None, key
        assert registry.write_template(key) is not None, key
        assert key in CANDIDATES_BY_PRODUCT["GEN_NX"], key


def test_p144_a_candidate_must_be_deletable() -> None:
    """门槛：每个候选在**该产品**上都有 `DELETE`；没有 `DELETE` 的端点不入候选（R100）。"""
    registry = _registry()
    for product, keys in CANDIDATES_BY_PRODUCT.items():
        for key in keys:
            methods = registry.methods_for(key=key, product=product)
            assert "DELETE" in methods, (product, key)
    for key in NO_DELETE_SAMPLE:
        methods = registry.methods_for(key=key, product="GEN_NX")
        assert "GET" in methods and any(m in methods for m in WRITE_METHODS), key
        assert "DELETE" not in methods, key
        assert key not in _probe("GEN_NX").candidate_keys(), key


def test_p144_the_rejected_endpoints_carry_no_template() -> None:
    """门槛（R101）：3 个如实留缺的端点**没有**模板 ⇒ 不入候选（理由见模块 docstring）。"""
    registry = _registry()
    candidates = set(_probe("GEN_NX").candidate_keys())
    for key in REJECTED_KEYS:
        assert registry.write_template(key) is None, key
        assert key not in candidates, key


# ===== 2. 包装键与离线三步链（判定 3 / 4）=====


def test_p144_the_wrapper_comes_from_the_data_side_when_no_transformer() -> None:
    """门槛：没有 Transformer 的端点，包装键取 `registry` 的 `wrapper.write`（**不**臆造）。"""
    registry = _registry()
    probe = _probe("GEN_NX")
    for key in TEMPLATE_ONLY_KEYS:
        assert TRANSFORMER_REGISTRY.get(transformer_name_for(key)) is None, key
        expected = registry.resolve(key=key, product="GEN_NX", method="POST").wrapper_write
        assert probe._wrapper_for(key) == expected == "Assign", key


async def test_p144_the_seven_template_only_endpoints_run_the_chain_offline() -> None:
    """门槛：7 个新端点逐个「创建 → 读回 → 删除」；请求体**逐字节**等于数据侧模板；零残留。"""
    registry = _registry()
    for key in TEMPLATE_ONLY_KEYS:
        body = registry.write_template(key).body
        transport = p139._NxStore(codes=("DB.NODE", "DB.ELEM", "DB.MATL", "DB.SECT", key))
        probe = _probe("GEN_NX", only=(key,), transport=transport)
        outcome = await probe.probe_key(key)
        assert outcome.outcome == WRITE_PROBE_PASSED, (key, outcome)
        assert outcome.created_id == "1", key
        assert outcome.read_back is True and outcome.deleted is True, key
        assert outcome.payload_source == "manual_example" or outcome.payload_source.endswith(
            "adjusted"
        ), (key, outcome.payload_source)
        posted = [item for method, _path, item in transport.calls if method == "POST"]
        assert posted == [{"Assign": {"1": body}}], key
        assert transport.rows[key.split(".", 1)[1]] == {}, key
        assert transport.paths()[-1] == f"/DB/{key.split('.', 1)[1]}/1", key


# ===== 3. 口径（判定 5）=====


def test_p144_coverage_counts_eighteen_of_609() -> None:
    """门槛：分子 = L5 `PASSED` 去重 key；18 / 609（`model_write_ratio` 18 / 410）。"""
    registry = _registry()
    keys = CANDIDATES_BY_PRODUCT["GEN_NX"]
    coverage = write_path_coverage(registry, [_Row(key) for key in keys])
    assert coverage.total == WRITE_PATH_TOTAL
    assert coverage.covered == len(keys) == 18
    assert coverage.ratio == f"18 / {WRITE_PATH_TOTAL}"
    assert coverage.model_write_ratio == f"18 / {MODEL_WRITE_TOTAL}"
    assert set(coverage.covered_keys) == set(keys)
    # 分子是**数据驱动**的：少一条 L5 行即少一个覆盖
    fewer = write_path_coverage(registry, [_Row(key) for key in keys[:-1]])
    assert fewer.ratio == f"17 / {WRITE_PATH_TOTAL}"
    # CIVIL NX 的候选（17）与 GEN NX 共用同一批 key 去重 → 分母/分子口径不变
    civil = write_path_coverage(registry, [_Row(key) for key in CANDIDATES_BY_PRODUCT["CIVIL_NX"]])
    assert civil.covered == 17
    assert civil.ratio == f"17 / {WRITE_PATH_TOTAL}"
