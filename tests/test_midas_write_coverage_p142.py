"""P142 —— 写路径覆盖的**上限裁决** + 契约内缺口 `FLOOR_LOAD` / `DB.FBLD` 收口。

权威来源
--------
- `docs/07` §6.3（`MODEL.LOAD.ASSIGN` 的端点表**含** `DB.FBLD`）· §16 **R4 / R14 / R97** ·
  §16.1 **R98**（本批裁决：`FLOOR_LOAD` 是**已声明**的 canonical 荷载类型，缺的是**实现**）。
- `registry/README.md` §2.3 / §8.1 / §8.6 · `registry/live/write_templates.json`。
- `docs/reports/P142_写路径候选集上限与FLOOR_LOAD收口_v1.0.md`（本批证据）。

本文件的**可执行判定**
--------------------
1. **候选集上限**：`candidate_keys()` = 「有写方法 + 有读路径 + Transformer **已注册** +
   非危险形态」∩ 产品可得性 —— GEN NX / CIVIL NX = **11**、Civil Designer = **0**（P143 更正）；
   被「Transformer 未注册」挡住的写端点 = **542 / 471 / 32**（P142 前为 543 / 472 / 32）。
2. **加模板不能新增候选**：模板只改变**已候选**端点的请求体 —— 给未候选端点（`DB.ELNK`）
   注入模板，候选集**不变**，`probe_key()` 如实记 `NO_PAYLOAD_TEMPLATE` 且**零**写请求。
3. **契约内缺口已收口**：`operations.LOAD_STEP_BY_TYPE["FLOOR_LOAD"] = "DB.FBLD"` 早已声明，
   本批补 `FloorLoadTransformer`（`midas.fbld.v1`）+ `LOAD_TRANSFORMERS["FLOOR_LOAD"]`，
   于是 `DB.FBLD` 进入候选集，`MODEL.LOAD.ASSIGN` 的楼面荷载不再 `load_type_not_mapped`。
4. **canonical 字段只来自数据侧 Schema**（`NAME` / `DESC` / `ITEM[]{LCNAME, FLOOR_LOAD,
   OPT_SUB_BEAM_WEIGHT}`）；`TEMPERATURE` 仍**明确拒绝**（本批**未**放宽）。
5. **数据侧模板 + 前置链**：`DB.FBLD` 的 body **原样**等于手册示例（零 `adjustments`），
   前置链 = 两条 `DB.STLD`（`DC` / `DW`，即手册示例 `ITEM[].LCNAME` 引用的工况名）。
6. **离线三步链**：前置**先建**、目标后建、读回、**逆序**清理；只碰自建编号；跑完**零残留**。
7. **口径不变**：分母仍 `write_path_keys()` —— P149-A 起 **633**（`write_only` **306** ·
   `result_query` **199** · `model_write` **434**；P148 为 609 / 368 / 199 / 410，方法集按只读
   `OPTIONS` 实测修正后重算）；分子 = L5 `PASSED` 去重 key，P142 本批真实实测 = **11 / 609**
   （`model_write_ratio` = **11 / 410**）。
8. **契约内不再有「仅缺 Transformer」的写端点**：`operations.py` 声明的写步骤里，
   凡是三步链适用的端点**全部**已在候选集内（故加模板**不可能**再增加分子）。
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest

import test_midas_write_templates_p139 as p139
from app.infrastructure.adapters.midas.errors import MidasValidationError
from app.infrastructure.adapters.midas.live import (
    DedicatedTestProject,
    model_write_keys,
    result_query_keys,
    write_only_keys,
    write_path_coverage,
    write_path_keys,
)
from app.infrastructure.adapters.midas.operations import LOAD_STEP_BY_TYPE, OPERATION_PLANS
from app.infrastructure.adapters.midas.registry import MidasRegistry
from app.infrastructure.adapters.midas.transforms import (
    LOAD_TRANSFORMERS,
    TRANSFORMER_REGISTRY,
    FloorLoadTransformer,
    LoadTransformer,
)
from app.infrastructure.adapters.midas.write_probe import (
    WRITE_METHODS,
    WRITE_PROBE_PASSED,
    MidasLiveWriteProbe,
    transformer_name_for,
)
from app.infrastructure.adapters.midas.write_templates import WritePayloadTemplate

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录（数据侧工具与上游手册都在这里）。"""

CHECK_TOOL_PATH = REPO_ROOT / "registry" / "tools" / "check_write_templates.py"
"""模板复算工具（本批新增 `DB.FBLD` 后仍必须 0 错）。"""

WRITE_PATH_TOTAL = 633
"""写路径端点数 —— R4 / R14 的**正式**分母（**不挪**口径）。

P149-A 起 **633**（P148 为 609）：只读 `OPTIONS` 实测修正方法集后，原先被漏算的 24 个写路径
端点进入分母。"""

WRITE_ONLY_TOTAL = 306
"""分母里**连 `GET` 都没有**的端点数（只读探针**完全**覆盖不到；P148 为 368）。"""

RESULT_QUERY_TOTAL = 199
"""分母里的「结果表 / 文本查询」子桶（`POST.` 命名空间）。"""

MODEL_WRITE_TOTAL = 434
"""分母里的「模型写」子桶（P141 裁决⑤：**同时**报两个比率；P148 为 410）。"""

FLOOR_LOAD_KEY = "DB.FBLD"
"""本批收口的端点（`docs/07` §6.3 的 `MODEL.LOAD.ASSIGN` 端点表里的楼面荷载类型）。"""

FLOOR_LOAD_TYPE = "FLOOR_LOAD"
"""canonical 荷载类型（`operations.LOAD_STEP_BY_TYPE` 早已声明的键）。"""

DB_CODES = (
    "DB.BMLD",
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
"""GEN NX 上的 **58** 个可探候选（P148 起；P147 的 46 + 本批 12）。"""

CIVIL_CODES = (
    "DB.BMLD",
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
"""CIVIL NX 上的 **49** 个候选（P148 起；9 个 GEN NX 独有的端点不含 `CIVIL_NX`）。"""

CANDIDATES_BY_PRODUCT: dict[str, tuple[str, ...]] = {
    "GEN_NX": DB_CODES,
    "CIVIL_NX": CIVIL_CODES,
    "CIVIL_DESIGNER": (),
}
"""三产品各自的候选集（`CIVIL_DESIGNER` = 空：其 `DB.NODE`/`DB.ELEM` 只有 `GET`）。"""

BLOCKED_BY_UNREGISTERED_TRANSFORMER: dict[str, int] = {
    "GEN_NX": 515,
    "CIVIL_NX": 451,
    "CIVIL_DESIGNER": 31,
}
"""「有写方法 + 非危险形态，但既无 Transformer 又无模板」的端点数。

P149-A 起 **515 / 451 / 31**（P147–P148 为 495 / 433 / 31）：只读 `OPTIONS` 实测修正方法集后，
新进入「有写方法」集合的端点（20 个 `DESIGN.*` / `DB.SWIND` / `OPE.SECTPROP` 等）绝大多数既无
Transformer 又无模板 ⇒ 如实计入 blocked。"""

REGISTERED_TRANSFORMERS = 20
"""`TRANSFORMER_REGISTRY` 的条数（P139 起 19，本批 +1）。"""

BLOCKED_CONTRACT_WRITE_KEYS = ("DESIGN.SRC.AIK-SRC2K.DSRC",)
"""`operations.py` 声明的写步骤里，三步链**结构适用**（有写方法 + `GET`/`read_root` + `DELETE`）
却**既无** Transformer **又无**数据侧模板的端点 —— P149-A 起 **1** 个。

`DESIGN.SRC.AIK-SRC2K.DSRC` 的方法集经只读 `OPTIONS` 实测（`Allow` 头）由 `[PUT]` 修正为
`[GET, PUT, DELETE]`，于是它从「三步链**不**适用」变成「适用但缺请求体来源」；契约里其余写步骤
**全部**已在候选集内（判定 8）。"""

NON_CANDIDATE_WRITE_KEY = "DB.ELNK"
"""有写方法 + 有读路径 + 有 `DELETE`，但 `midas.elnk.v1` **未**注册且**没有**模板 → 不入候选。"""


# ===== 辅助 =====


def _registry() -> MidasRegistry:
    """数据侧 Registry（`registry/` 的唯一权威来源）。"""
    return p139._registry()


def _probe(
    product: str = "GEN_NX",
    *,
    only: tuple[str, ...] = (),
    templates: dict[str, WritePayloadTemplate] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> MidasLiveWriteProbe:
    """构造写路径探针（缺省用**空**假传输；候选集只看 Registry，**不**做 I/O）。"""
    return MidasLiveWriteProbe(
        p139._client(p139._NxStore(codes=()) if transport is None else transport),
        _registry(),
        product=product,
        project=DedicatedTestProject(name="p142"),
        limit=0,
        only=only,
        templates=templates,
    )


def _check_tool() -> Any:
    """按路径装载 `registry/tools/check_write_templates.py`（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(
        "structai_check_write_templates_p142", CHECK_TOOL_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        if "GET" not in methods or not definition.read_root:
            continue
        if "DELETE" not in methods:
            continue
        candidates.append(key)
    return tuple(candidates), blocked


def _schema_fields(registry: MidasRegistry, key: str) -> set[str]:
    """端点请求 Schema 声明的**根级 + `ITEM[]` 元素级**字段名（白名单的唯一来源）。"""
    schema = registry.effective_schema(key) or {}
    properties = schema.get("properties")
    assert isinstance(properties, dict), key
    fields = {str(name) for name in properties}
    items = properties.get("ITEM")
    if isinstance(items, dict):
        element = items.get("items")
        if isinstance(element, dict) and isinstance(element.get("properties"), dict):
            fields |= {str(name) for name in element["properties"]}
    return fields


def _declared_write_keys() -> set[str]:
    """`operations.py` 里**声明为写步骤**的端点 key（`steps` + 组合编排的 `routes`）。"""
    keys: set[str] = set()
    for plan in OPERATION_PLANS.values():
        for steps in (plan.steps, *plan.routes.values()):
            for step in steps:
                if step.method in WRITE_METHODS:
                    keys.add(step.key)
    return keys


@dataclass(frozen=True, slots=True)
class _Row:
    """`midas_api_verifications` 的最小只读投影（覆盖率的分子来源）。"""

    endpoint_key: str
    contract_level: str = "L5"
    status: str = "PASSED"


# ===== 1. 候选集上限（判定 1 / 8）=====


def test_p142_the_candidate_set_is_the_registered_transformer_intersection() -> None:
    """门槛：候选集 = 独立复算结果；被「既无 Transformer 又无模板」挡住的端点数逐产品可复算。"""
    registry = _registry()
    for product, expected in CANDIDATES_BY_PRODUCT.items():
        derived, blocked = _derived_candidates(registry, product)
        assert derived == expected, product
        assert blocked == BLOCKED_BY_UNREGISTERED_TRANSFORMER[product], product
        assert _probe(product).candidate_keys() == expected, product
    assert len(TRANSFORMER_REGISTRY) == REGISTERED_TRANSFORMERS


def test_p142_no_contract_write_endpoint_is_blocked_by_a_missing_transformer() -> None:
    """门槛：契约声明的写步骤里，凡三步链**结构适用且已有请求体来源**的端点**全部**已在候选集内；
    候选集**可以**超出契约（R100：数据侧模板即可入候选 —— P144 起新增 7 个）。

    **P149-A 更正**：方法集按只读 `OPTIONS` 实测（`Allow` 头）修正后重算 ——
    `DESIGN.SRC.AIK-SRC2K.DSRC` 由 `[PUT]` 变为 `[GET, PUT, DELETE]`，三步链**结构上适用**了，
    但它**既无** Transformer **又无**数据侧模板 ⇒ 契约内**唯一**被「缺 Transformer」挡住的写端点，
    如实单独记入 `BLOCKED_CONTRACT_WRITE_KEYS`（**不**再混进 `inapplicable`，也**不**当作已候选）。
    """
    registry = _registry()
    candidates = set(_probe("GEN_NX").candidate_keys())
    eligible: set[str] = set()
    inapplicable: set[str] = set()
    blocked: set[str] = set()
    for key in sorted(_declared_write_keys()):
        definition = registry.endpoint(key)
        if "GEN_NX" not in definition.products or not definition.enabled:
            continue
        if "GET" not in definition.methods or not definition.read_root:
            inapplicable.add(key)
            continue
        if (
            TRANSFORMER_REGISTRY.get(transformer_name_for(key)) is None
            and registry.write_template(key) is None
        ):
            blocked.add(key)
            continue
        eligible.add(key)
    assert eligible <= candidates, sorted(eligible - candidates)
    assert blocked == set(BLOCKED_CONTRACT_WRITE_KEYS), sorted(blocked)
    assert not (blocked & candidates), sorted(blocked & candidates)
    # 契约**外**的候选必须都有数据侧模板（R100 新增的类别，逐个可查）
    extra = candidates - eligible
    assert extra, "R100 之后应存在「契约外但可探」的端点"
    assert all(registry.write_template(key) is not None for key in extra), sorted(extra)
    # 三步链**结构上不适用**的写步骤（DOC / VIEW / DESIGN / POST）不得因模板而进入候选
    assert inapplicable
    assert not (inapplicable & candidates), sorted(inapplicable & candidates)
    assert all(key.startswith(("DOC.", "VIEW.", "DESIGN.", "POST.")) for key in inapplicable), (
        sorted(inapplicable)
    )


async def test_p142_a_template_adds_a_candidate_only_with_a_complete_chain() -> None:
    """R100（P144）：数据侧模板**可以**把端点变成候选 —— 前提是
    「有写方法 + `GET`/`read_root` + `DELETE`」。

    ⚠️ P138c 的「未注册 Transformer 即排除」**已被 R100 取代**（`docs/07` §16.1）。
    """
    key = NON_CANDIDATE_WRITE_KEY  # `DB.ELNK`：有 POST/GET/DELETE，但没有 Transformer
    registry = _registry()
    definition = registry.endpoint(key)
    assert TRANSFORMER_REGISTRY.get(transformer_name_for(key)) is None, key
    assert "GET" in definition.methods and definition.read_root, key
    assert "DELETE" in definition.methods, key
    # 没有模板时**不**入候选（否则只会白占 `limit` 并记 `NO_PAYLOAD_TEMPLATE`）
    assert key not in _probe("GEN_NX").candidate_keys()
    template = WritePayloadTemplate(
        key=key,
        body={"ITEMS": [{"ID": 1}]},
        source="explicit_injection",
        origin="unit-test",
    )
    transport = p139._NxStore(codes=("DB.NODE", "DB.ELEM", "DB.MATL", "DB.SECT", key))
    probe = _probe("GEN_NX", templates={key: template}, transport=transport)
    assert key in probe.candidate_keys(), "R100：有模板即可入候选"
    outcome = await probe.probe_key(key)
    assert outcome.outcome == WRITE_PROBE_PASSED, outcome
    assert outcome.payload_source == "explicit_injection", outcome
    # 包装键来自**数据侧**（该端点没有 Transformer）：`Assign` + 实分配编号
    posted = [body for method, _path, body in transport.calls if method == "POST"]
    assert posted == [{"Assign": {"1": {"ITEMS": [{"ID": 1}]}}}]


# ===== 2. 契约内缺口 `FLOOR_LOAD`（判定 3 / 4）=====


def test_p142_fbld_closes_the_declared_floor_load_gap() -> None:
    """门槛：`FLOOR_LOAD` 早已声明（缺的是实现），本批补齐后 `DB.FBLD` 进入候选集。"""
    assert LOAD_STEP_BY_TYPE[FLOOR_LOAD_TYPE] == FLOOR_LOAD_KEY
    assert TRANSFORMER_REGISTRY["midas.fbld.v1"] is FloorLoadTransformer
    assert LOAD_TRANSFORMERS[FLOOR_LOAD_TYPE] is FloorLoadTransformer
    assert FloorLoadTransformer.name == "midas.fbld.v1"
    assert FloorLoadTransformer.endpoint == FLOOR_LOAD_KEY
    assert FLOOR_LOAD_KEY in CANDIDATES_BY_PRODUCT["GEN_NX"]
    assert FLOOR_LOAD_KEY in _probe("GEN_NX").candidate_keys()
    assert FLOOR_LOAD_KEY in model_write_keys(_registry())
    assert FLOOR_LOAD_KEY not in result_query_keys(_registry())


def test_p142_floor_load_dispatch_uses_only_schema_declared_fields() -> None:
    """门槛：`FLOOR_LOAD` 分派产出的原生字段**只**来自数据侧 Schema；`TEMPERATURE` 仍拒绝。"""
    registry = _registry()
    canonical = {
        "load_type": FLOOR_LOAD_TYPE,
        "name": "Floor_example",
        "desc": "",
        "load_case": "DC",
        "floor_load": 10,
        "sub_beam_weight": True,
    }
    native = LoadTransformer(registry).to_native(canonical)
    assert native == {
        "NAME": "Floor_example",
        "DESC": "",
        "ITEM": [{"LCNAME": "DC", "FLOOR_LOAD": 10, "OPT_SUB_BEAM_WEIGHT": True}],
    }
    declared = _schema_fields(registry, FLOOR_LOAD_KEY)
    assert declared == {"NAME", "DESC", "ITEM", "LCNAME", "FLOOR_LOAD", "OPT_SUB_BEAM_WEIGHT"}
    assert set(native) <= declared
    assert set(native["ITEM"][0]) <= declared
    # canonical 只覆盖 `ITEM[]` 的**首行**（与 `MaterialTransformer` 的 `PARAM[]` 同约定）
    assert len(native["ITEM"]) == 1
    # `TEMPERATURE` **故意**缺席（`docs/04` §32）—— 本批**未**放宽
    assert "TEMPERATURE" not in LOAD_TRANSFORMERS
    with pytest.raises(MidasValidationError) as failure:
        LoadTransformer(registry).to_native({"load_type": "TEMPERATURE", "load_case": "T"})
    assert failure.value.details["reason"] == "load_type_not_mapped"


# ===== 3. 数据侧模板 + 前置链（判定 5 / 6）=====


def test_p142_the_data_side_declares_the_fbld_template_with_the_stld_chain() -> None:
    """门槛：`DB.FBLD` 的 body **原样**等于手册示例；前置链 = 两条 `DB.STLD`（`DC` / `DW`）。"""
    module = _check_tool()
    errors, _notes, counts = module.check(REPO_ROOT)
    assert errors == [], "\n".join(errors)
    assert counts["templates"] == 57
    assert counts["bodies"] == 101
    assert counts["unverifiable"] == 0
    template = _registry().write_template(FLOOR_LOAD_KEY)
    assert template is not None
    assert template.source == "manual_example"
    assert template.origin == "db/FBLD#Define Floor Load Type"
    examples = module.manual_examples(REPO_ROOT)
    example = module.manual_item(
        examples, uri="db/FBLD", example="Define Floor Load Type", item_id="1"
    )
    assert example is not None
    assert template.body == example
    assert template.self_references == ()
    assert template.target_id_source == ""
    assert [(item.key, item.item_id) for item in template.prerequisites] == [
        ("DB.STLD", "1"),
        ("DB.STLD", "2"),
    ]
    assert [item.body["NAME"] for item in template.prerequisites] == ["DC", "DW"]
    assert {entry["LCNAME"] for entry in template.body["ITEM"]} == {"DC", "DW"}


async def test_p142_the_fbld_chain_creates_reads_back_and_deletes_only_its_own_ids() -> None:
    """门槛：前置先建 → 目标后建 → 读回 → 目标删除 → 前置**逆序**删除；跑完零残留。"""
    transport = p139._NxStore(
        codes=("DB.NODE", "DB.ELEM", "DB.MATL", "DB.SECT", FLOOR_LOAD_KEY, "DB.STLD")
    )
    probe = _probe("GEN_NX", only=(FLOOR_LOAD_KEY,), transport=transport)
    outcome = await probe.probe_key(FLOOR_LOAD_KEY)
    assert outcome.outcome == WRITE_PROBE_PASSED, outcome
    assert outcome.created_id == "1"
    assert outcome.read_back is True and outcome.deleted is True
    assert outcome.status_code == 200
    assert outcome.payload_source == "manual_example"
    assert outcome.prerequisites == ("DB.STLD#1", "DB.STLD#2")
    assert transport.paths() == [
        "/DB/NODE",
        "/DB/ELEM",
        "/DB/MATL",
        "/DB/SECT",
        "/DB/FBLD",
        "/DB/STLD",
        "/DB/STLD",
        "/DB/STLD",
        "/DB/FBLD",
        "/DB/FBLD",
        "/DB/FBLD/1",
        "/DB/STLD/2",
        "/DB/STLD/1",
    ]
    posted = [body for method, _path, body in transport.calls if method == "POST"]
    assert posted[0] == {"Assign": {"1": {"NAME": "DC", "TYPE": "D", "DESC": "DeadLoads"}}}
    assert posted[1] == {"Assign": {"2": {"NAME": "DW", "TYPE": "D", "DESC": "DeadLoads"}}}
    assert posted[2] == {
        "Assign": {
            "1": {
                "NAME": "Floor_example",
                "DESC": "",
                "ITEM": [
                    {"LCNAME": "DC", "FLOOR_LOAD": 10, "OPT_SUB_BEAM_WEIGHT": True},
                    {"LCNAME": "DW", "FLOOR_LOAD": 20, "OPT_SUB_BEAM_WEIGHT": True},
                ],
            }
        }
    }
    for code in ("NODE", "ELEM", "MATL", "SECT", "FBLD", "STLD"):
        assert transport.rows[code] == {}, code


# ===== 4. 口径不变（判定 7）=====


def test_p142_the_denominator_and_sub_buckets_are_unchanged() -> None:
    """门槛：分母仍 `write_path_keys()` —— P149-A 起 633（306 / 199 / 434；P148 为
    609 / 368 / 199 / 410）；分子 = L5 `PASSED` 去重 key（**数据驱动**）。"""
    registry = _registry()
    assert len(write_path_keys(registry)) == WRITE_PATH_TOTAL
    assert len(write_only_keys(registry)) == WRITE_ONLY_TOTAL
    assert len(result_query_keys(registry)) == RESULT_QUERY_TOTAL
    assert len(model_write_keys(registry)) == MODEL_WRITE_TOTAL
    keys = CANDIDATES_BY_PRODUCT["GEN_NX"]
    coverage = write_path_coverage(registry, [_Row(key) for key in keys])
    assert coverage.total == WRITE_PATH_TOTAL
    assert coverage.covered == len(keys) == 58
    assert coverage.ratio == f"58 / {WRITE_PATH_TOTAL}"
    assert coverage.model_write_ratio == f"58 / {MODEL_WRITE_TOTAL}"
    assert set(coverage.covered_keys) == set(keys)
    # 少一条 L5 行即少一个覆盖（**不**硬编码分子）
    fewer = write_path_coverage(registry, [_Row(key) for key in keys if key != FLOOR_LOAD_KEY])
    assert fewer.ratio == f"57 / {WRITE_PATH_TOTAL}"
    assert FLOOR_LOAD_KEY not in fewer.covered_keys
    # 非 `L5` 行 / 非 `PASSED` 行**不**计入分子
    assert write_path_coverage(registry, [_Row(FLOOR_LOAD_KEY, contract_level="L4")]).covered == 0
    assert write_path_coverage(registry, [_Row(FLOOR_LOAD_KEY, status="FAILED")]).covered == 0
