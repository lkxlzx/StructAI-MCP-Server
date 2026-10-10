"""P143 —— 候选集的**产品级方法覆盖**保真度修复（`CIVIL_DESIGNER` 候选集 **2 → 0**）+ 跨产品证据。

权威来源
--------
- `docs/07` §7.6（产品差异**先查** `product_overrides` 再回落主定义）· §16 **R4 / R14 / R97** ·
  §16.1 **R98**（P142 的 `FLOOR_LOAD` 收口）+ **R99**（本批新增：候选集曾忽略产品级方法覆盖）。
- `registry/README.md` §4（`product_overrides`）/ §5 第 2–3 步（解析顺序）/ §8.7（P142 裁决）。
- `docs/reports/P143_*.md`（本批证据）。

本文件的**可执行判定**
--------------------
1. **候选集必须按产品解析方法**：`candidate_keys()` 用 `registry.methods_for(key, product)`
   （先 `product_overrides.<产品>.methods`，再回落主定义）—— 数据侧对 `CIVIL_DESIGNER` 的
   `DB.NODE` / `DB.ELEM` 只声明 `GET` ⇒ 它们**不是**候选（P142 记的 **2** 是伪的，已更正为 **0**）。
2. **解析层早已正确**：`resolve(key, product="CIVIL_DESIGNER", method="POST")` → 拒绝
   `method_not_available_for_product`（缺陷只在候选集/写方法选择那一层）。
3. **如实记原因**：对「该产品没有写方法」的端点，`probe_key()` 记
   `NO_PAYLOAD_TEMPLATE` + `detail = no_write_method_for_product`，且**零**写请求
   （与「Transformer 未注册」的 `no_transformer_for_endpoint` 区分开）。
4. **口径不变**：覆盖率的分子是 **registry key**（去重）∩ 写路径端点，**不**按「端点 × 产品」——
   故 `CIVIL_NX` 的 11 条 `PASSED` 行**不**改变 `11 / 633`（P149-A 起；P143 当时为 `11 / 609`）；
   它们证明的是「同一批端点在第二个产品上也通」（跨产品证据），而不是新的覆盖数。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

import test_midas_write_templates_p139 as p139
from app.infrastructure.adapters.midas.errors import MidasCapabilityError
from app.infrastructure.adapters.midas.live import (
    DedicatedTestProject,
    write_path_coverage,
    write_path_keys,
)
from app.infrastructure.adapters.midas.registry import MidasRegistry
from app.infrastructure.adapters.midas.write_probe import (
    WRITE_PROBE_NO_PAYLOAD,
    WRITE_PROBE_NO_READBACK,
    MidasLiveWriteProbe,
)

WRITE_PATH_TOTAL = 633
"""写路径端点数 —— R4 / R14 的**正式**分母（**不挪**口径；P149-A 起 **633**，P148 为 609）。"""

DB_CODES = (
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
)
"""`GEN_NX` 上的 **61** 个候选（12 个有 Transformer + 49 个只有数据侧模板；P149-B2 +3）。"""

CIVIL_CODES = (
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
)
"""`CIVIL_NX` 上的 **52** 个候选（9 个 GEN NX 独有的端点不含 `CIVIL_NX`；P149-B2 +3）。"""

CANDIDATES_BY_PRODUCT: dict[str, tuple[str, ...]] = {
    "GEN_NX": DB_CODES,
    "CIVIL_NX": CIVIL_CODES,
    "CIVIL_DESIGNER": (),
}
"""三产品各自的候选集（`CIVIL_DESIGNER` = 空：其 `DB.NODE` / `DB.ELEM` 数据侧只有 `GET`）。"""

DESIGNER_READ_ONLY_KEYS = ("DB.NODE", "DB.ELEM")
"""`CIVIL_DESIGNER` 的 `product_overrides` 把方法集覆盖成 `GET` 的两个端点（P143 修复的对象）。"""


@dataclass(frozen=True, slots=True)
class _Row:
    """`midas_api_verifications` 的最小只读投影（覆盖率只读 `endpoint_key` / 级别 / 结论）。"""

    endpoint_key: str
    contract_level: str = "L5"
    status: str = "PASSED"
    product: str = "GEN_NX"


def _registry() -> MidasRegistry:
    """数据侧 Registry（`registry/` 的唯一权威来源）。"""
    return p139._registry()


def _probe(
    product: str, *, only: tuple[str, ...] = (), transport: object = None
) -> MidasLiveWriteProbe:
    """构造写路径探针（缺省用**空**假传输；候选集只看 Registry，**不**做 I/O）。"""
    store = p139._NxStore(codes=()) if transport is None else transport
    return MidasLiveWriteProbe(
        p139._client(store),
        _registry(),
        product=product,
        project=DedicatedTestProject(name="p143"),
        limit=0,
        only=only,
    )


# ===== 1. 候选集按产品解析方法（判定 1 / 2）=====


def test_p143_candidates_respect_product_level_method_overrides() -> None:
    """门槛：候选集与 `methods_for` 一致；`CIVIL_DESIGNER` 的只读端点**不**入候选。"""
    registry = _registry()
    for product, expected in CANDIDATES_BY_PRODUCT.items():
        assert _probe(product).candidate_keys() == expected, product
    for key in DESIGNER_READ_ONLY_KEYS:
        assert registry.methods_for(key=key, product="CIVIL_DESIGNER") == ("GET",), key
        assert key not in _probe("CIVIL_DESIGNER").candidate_keys(), key
        # 基础定义仍是读写（差异**只**由产品覆盖引入）—— 故 `GEN_NX` / `CIVIL_NX` 不受影响
        assert key in _probe("GEN_NX").candidate_keys(), key
        assert key in _probe("CIVIL_NX").candidate_keys(), key


def test_p143_resolve_rejects_write_methods_the_product_does_not_declare() -> None:
    """门槛：解析层**早已**正确拒绝产品未声明的方法（缺陷只在候选集那一层）。"""
    registry = _registry()
    for key in DESIGNER_READ_ONLY_KEYS:
        for method in ("POST", "PUT", "DELETE"):
            with pytest.raises(MidasCapabilityError) as failure:
                registry.resolve(key=key, product="CIVIL_DESIGNER", method=method)
            assert failure.value.details["reason"] == "method_not_available_for_product", key
        assert registry.resolve(key=key, product="CIVIL_DESIGNER", method="GET").method == "GET"


def test_p143_methods_for_prefers_the_override_and_falls_back_to_the_definition() -> None:
    """门槛：`methods_for` 先产品覆盖、再回落主定义（无覆盖的端点两产品一致）。"""
    registry = _registry()
    definition = registry.endpoint("DB.NODE")
    assert registry.methods_for(key="DB.NODE", product="GEN_NX") == definition.methods
    assert registry.methods_for(key="DB.NODE", product="CIVIL_NX") == definition.methods
    # `DB.STLD` 没有 `CIVIL_DESIGNER` 覆盖 → 回落主定义
    stld = registry.endpoint("DB.STLD")
    assert registry.methods_for(key="DB.STLD", product="CIVIL_DESIGNER") == stld.methods


async def test_p143_probe_key_reports_the_missing_write_method_without_writing() -> None:
    """门槛：产品没有写方法 → `NO_PAYLOAD_TEMPLATE` + `no_write_method_for_product` + 零写请求。"""
    key = "DB.NODE"
    transport = p139._NxStore(codes=("DB.NODE", "DB.ELEM", "DB.MATL", "DB.SECT"))
    probe = _probe("CIVIL_DESIGNER", only=(key,), transport=transport)
    outcome = await probe.probe_key(key)
    assert outcome.outcome == WRITE_PROBE_NO_PAYLOAD, outcome
    assert outcome.detail == "no_write_method_for_product", outcome
    assert outcome.method == ""
    assert transport.write_calls() == []
    # 与「Transformer 未注册」区分：那是另一条原因
    assert outcome.detail != "no_transformer_for_endpoint"


# ===== 2. 覆盖口径（判定 4）=====


def test_p143_the_coverage_numerator_is_key_based_not_product_based() -> None:
    """门槛：分子是 **registry key** 去重 —— 换产品跑**不**改变 `covered`（跨产品是另一条证据）。"""
    registry = _registry()
    keys = CANDIDATES_BY_PRODUCT["GEN_NX"]
    gen = write_path_coverage(registry, [_Row(key, product="GEN_NX") for key in keys])
    civil = write_path_coverage(registry, [_Row(key, product="CIVIL_NX") for key in keys])
    assert len(write_path_keys(registry)) == WRITE_PATH_TOTAL
    assert gen.covered == civil.covered == len(keys) == 61
    assert gen.ratio == civil.ratio == f"61 / {WRITE_PATH_TOTAL}"
    assert set(civil.covered_keys) == set(keys)
    # 非 `L5` / 非 `PASSED` 行**不**计入（判据未放宽）
    assert write_path_coverage(registry, [_Row("DB.NODE", contract_level="L4")]).covered == 0
    assert write_path_coverage(registry, [_Row("DB.NODE", status="FAILED")]).covered == 0
    assert WRITE_PROBE_NO_READBACK != WRITE_PROBE_NO_PAYLOAD
