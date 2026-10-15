"""NXSDK 外部证据裁决 —— 产品归属更正与 3 处字段类型更正（可执行判定）。

权威来源
--------
- `docs/nxsdk_review/00_评估与查漏补缺报告_v1.0.md`（本批证据与分级）。
- `docs/nxsdk_review/nxsdk_product_corrections.json`（54 条候选，A/B/C 三级 + 逐条证据）。
- `registry/tools/import_nxsdk_evidence.py`（导入工具：默认预演、幂等、`--tier` 分级、`--check`）。
- 外部项目 `Dennis5882/MIDAS-API-NX-SDK`：`docs/CLAUDE.md`、`docs/live_verification_notes.md`、
  `schema/hyper-s-info.json`、`schema/info-baseline.json`、`contracts/endpoints/*.yaml`。

本文件的**可执行判定**
--------------------
1. **Hyper-S 归属（A 级，21 条）**：`solver == HYPER_S` ⇔ `products == ("CIVIL_NX",)`。
   三条独立证据同向：对方 `HYPER_S_ONLY` = 13 implemented + 8 stubs = **21**（live 两次确认
   "civil GET ok, gen GET fails"）· 对方 `hyper-s-info.json` 以 `product: civil` 抓取 ·
   我方 `instances.yaml` 自述 gen-local「缺 21 个 Hyper-S 变体」且 21 条全带
   `unavailable_on: [gen-local]`。
2. **GEN_ONLY 收口（C 级，12 条）**：对方 `GEN_ONLY` 家族（两次独立复现）
   ⇒ `products == ("GEN_NX",)`。
   这 12 条的 `verified_on` **只有** `gen-local`、`unavailable_on` 为空 —— `CIVIL_NX` 从未被实测。
3. **B 级**（21 条「我方少声明 `CIVIL_NX`」）**未**落地：需我方 CIVIL_NX 实例复测，
   故 `DB.POSL` / `DB.POSP` / `POST.STEELCODECHECK` 等**保持** `("GEN_NX",)`。
4. **只升不降**：本批**未**改任何 `availability` / `unavailable_on`（全库
   `verified` = **503**、`unverified` = **23**、`untested` = **110**）。
5. **3 处字段类型更正**（`/info` 与对方**已复核契约**双证据同向）：
   `DB.SLANOP.OPT_STRADD` integer → **boolean** ·
   `DB.REBC` / `DB.REBR` 的 `ITEMS[].HOOP_TYPE` string → **integer**（REBR 带 `enum: [1, 2]`）。
6. **未采纳的 4 处类型分歧**（证据不足或与已复核契约相反）：`DB.EPSE` / `DB.EPST`
   `LOADING_AREA_GROUP`（契约 `provenance: manual` 支持 `integer`）· `DB.RPSC`
   `LBAR_INC_FC`（三方差歧）· `DB.NLLP` `SEIS_TYPE`（单来源）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录。"""

MANIFEST_PATH = REPO_ROOT / "registry" / "manifest.json"
"""端点清单（YAML 的派生物）。"""

HYPER_S_KEYS: tuple[str, ...] = (
    "DB.ACTL-M1",
    "DB.BCGA-M1",
    "DB.BCGD-M1",
    "DB.EIGV-M1",
    "DB.EPMT-M1",
    "DB.HHCT-M1",
    "DB.IEHG-BEAM-M1",
    "DB.IEHG-GL-M1",
    "DB.IEHG-PSS-M1",
    "DB.IEHG-TRUSS-M1",
    "DB.IMFM-M1",
    "DB.MATL-M1",
    "DB.NLCT-M1",
    "DB.NLNK-M1",
    "DB.POGD-M1",
    "DB.POLC-M1",
    "DB.STCT-M1",
    "DB.STYP-M1",
    "DB.THGC-M1",
    "DB.THIS-M1",
    "DB.THOO-M1",
)
"""对方 `HYPER_S_ONLY` = **13 implemented + 8 undocumented-stub** = 21，
与我方 21 条 `-M1` 逐条对齐。"""

GEN_ONLY_KEYS: tuple[str, ...] = (
    "DB.REBB",
    "DB.REBC",
    "DB.REBR",
    "DB.REBW",
    "DESIGN.RC.KDS-41-20-2022.REBB",
    "DESIGN.RC.KDS-41-20-2022.REBC",
    "DESIGN.RC.KDS-41-20-2022.REBR",
    "DESIGN.RC.KDS-41-20-2022.REBW",
    "DESIGN.RC.KDS-41-20-2022.TRFT",
    "DESIGN.RC.KDS-41-20-2022.ULCT",
    "DESIGN.STEEL.KDS-41-30-2022.ULCT",
    "OPE.STORYPROP",
)
"""对方 `GEN_ONLY` 家族里**我方曾声明 `CIVIL_NX`** 的 12 条（其余 9 条我方已如实只标 `GEN_NX`）。"""

TIER_B_PRESENT_ON_CIVIL: tuple[str, ...] = (
    "DB.DCTL",
    "DB.DSTL",
    "DB.EPSE",
    "DB.ESSF",
    "DB.LENG",
    "DB.LLAN",
    "DB.LLANID",
    "DB.LTSR",
    "DB.MBTP",
    "DB.MEMB",
    "DB.POSL",
    "DB.WMAK",
    "OPE.EDMP",
    "OPE.GSBG",
    "OPE.GUSTFACTOR",
    "OPE.MEMB",
    "OPE.SSPS",
    "VIEW.PRECAPTURE",
)
"""B 级候选里 **CIVIL_NX 探针实测存在**（`200`）的 **18** 条 —— 已并上 `CIVIL_NX`。"""

TIER_B_ABSENT_ON_CIVIL: tuple[str, ...] = (
    "DB.POSP",
    "DOC.STAGAS",
    "POST.STEELCODECHECK",
)
"""B 级候选里 **CIVIL_NX 探针实测不存在**（`404`）的 **3** 条 ——
**不**并 `CIVIL_NX`，只记 `unavailable_on`。"""

TIER_B_DEFERRED_KEYS: tuple[str, ...] = TIER_B_PRESENT_ON_CIVIL + TIER_B_ABSENT_ON_CIVIL
"""B 级 21 条的全体（13 个 `/db/*` + 8 个非 `/db/*`）。"""

AVAILABILITY_TOTALS = {"verified": 510, "unverified": 23, "untested": 103}
"""CIVIL_NX 探针把 **6** 个 `OPE.*` / `VIEW.*` 由 `untested` 收口为 `verified`
（`200` ∧ 空表 ⇒ `PARTIAL` ⇒ `verified`，与 P149-E 同一口径）⇒ `verified` 503 → **509**、
`untested` 110 → **104**；`unverified` **不变**（`-M1` 族仍从未验证成功过）。
**P166 / R159**：`VIEW.RESULTGRAPHIC` 由 `untested` 收口为 `verified`（依据 = 效果判据
`PASSED`：`registry/live/view_result_post_probe.json`）
⇒ `verified` **510** · `untested` **103**。"""


def _manifest() -> dict:
    """`registry/manifest.json` 原文。"""
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _entry(key: str) -> dict:
    """按 key 取 manifest 条目。"""
    for item in _manifest()["endpoints"]:
        if item["key"] == key:
            return item
    raise AssertionError(f"{key} not in registry/manifest.json")


def _schema(key: str) -> dict:
    """端点 Schema 文件原文（`schema` 字段指向的相对路径）。"""
    relative = str(_entry(key)["schema"])
    assert relative, f"{key} 没有 Schema 文件"
    return json.loads((REPO_ROOT / "registry" / relative).read_text(encoding="utf-8"))


def _find_property(node: object, name: str) -> dict | None:
    """按属性名递归查找字段定义。

    各端点 Schema 文件的根键形态**不统一**（`Assign` 包装 / `patternProperties` 包装 /
    `Argument` 包装 / code-key 直挂，共 8 种），故按名查找而非写死路径。
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key == name and isinstance(value, dict):
                return value
            found = _find_property(value, name)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_property(item, name)
            if found is not None:
                return found
    return None


# ===== 1. Hyper-S 归属（A 级，21 条）=====


def test_p161_the_hyper_s_family_is_civil_nx_only() -> None:
    """门槛（判定 1）：21 条 `-M1` 全部 `solver == HYPER_S` ∧ `products == ["CIVIL_NX"]`。"""
    for key in HYPER_S_KEYS:
        entry = _entry(key)
        assert entry["solver"] == "HYPER_S", key
        assert entry["products"] == ["CIVIL_NX"], (key, entry["products"])


def test_p161_the_hyper_s_invariant_holds_for_every_endpoint() -> None:
    """门槛（判定 1）：全库不变量 —— `solver == HYPER_S` ⇔ `products == ["CIVIL_NX"]`。

    ⚠️ 这正是本批修掉的**口径漏洞**：`solver` 与 `products` 此前无任何一致性约束，
    21 条 Hyper-S 端点带着 `solver: HYPER_S` 声明了 `[GEN_NX]`，从未被成功实测过
    （`availability: unverified` ∧ `verified_on: []`）。
    """
    manifest = _manifest()["endpoints"]
    hyper = [item for item in manifest if item["solver"] == "HYPER_S"]
    assert len(hyper) == len(HYPER_S_KEYS) == 21
    for item in hyper:
        assert item["products"] == ["CIVIL_NX"], item["key"]
        # 且从未被成功实测（本批只改归属，不改可用性）
        assert item["availability"] == "unverified", item["key"]
        assert item["verified_on"] == [], item["key"]


# ===== 2. GEN_ONLY 收口（C 级，12 条）=====


def test_p161_the_twelve_gen_only_endpoints_lost_civil_nx() -> None:
    """门槛（判定 2）：12 条收为 `["GEN_NX"]`，且它们的 `CIVIL_NX` 声明从未被实测。"""
    for key in GEN_ONLY_KEYS:
        entry = _entry(key)
        assert entry["products"] == ["GEN_NX"], (key, entry["products"])
        assert entry["unavailable_on"] == [], key
        # `verified_on` 只有 `gen-local` —— 从未在 Civil 实例上验证过 `CIVIL_NX`
        assert set(entry["verified_on"]) <= {"gen-local"}, (key, entry["verified_on"])


def test_p161_the_rebar_family_is_gen_only_on_both_namespaces() -> None:
    """门槛（判定 2）：`/db/REB*` 与其 `/DESIGN/RC/...` 同族**一致**收为 `GEN_NX`。

    对方 `docs/live_verification_notes.md` 记载 `/db/REBC` 是第 21 个确认的 `GEN_ONLY`
    端点（POST-only，`/info` 是唯一可用探针），其余 `REBB`/`REBR`/`REBW` 在前 20 条内。
    """
    for key in (
        "DB.REBB",
        "DB.REBC",
        "DB.REBR",
        "DB.REBW",
        "DESIGN.RC.KDS-41-20-2022.REBB",
        "DESIGN.RC.KDS-41-20-2022.REBC",
        "DESIGN.RC.KDS-41-20-2022.REBR",
        "DESIGN.RC.KDS-41-20-2022.REBW",
    ):
        assert _entry(key)["products"] == ["GEN_NX"], key


# ===== 3. B 级：由 CIVIL_NX 探针收口（第三批）=====


def test_p161_the_tier_b_candidates_were_settled_by_the_civil_probe() -> None:
    """门槛（判定 3）：B 级「我方少声明 `CIVIL_NX`」已由 **CIVIL_NX 产品级探针**收口。

    ⚠️ 本用例在第三批**反转**：此前断言的是「**未**落地」（当时只有产品族级证据）。
    现在有了我方自己的实测（`registry/live/civil_product_probe.json`，**只发 GET**、含三组对照），
    故 `TIER_B_DEFERRED_KEYS` 里**在 CIVIL_NX 上存在**的那些必须已并上 `CIVIL_NX`。
    ⚠️ 判定**未**放宽：仍逐条钉住数据事实。
    """
    present = TIER_B_PRESENT_ON_CIVIL
    absent = TIER_B_ABSENT_ON_CIVIL
    for key in present:
        entry = _entry(key)
        assert "CIVIL_NX" in entry["products"], (key, entry["products"])
        assert "civil-cloud" in entry["verified_on"], (key, entry["verified_on"])
        assert entry["availability"] == "verified", key
    for key in absent:
        entry = _entry(key)
        assert entry["products"] == ["GEN_NX"], (key, entry["products"])
        assert "civil-cloud" in entry["unavailable_on"], (key, entry["unavailable_on"])


def test_p161_the_civil_probe_evidence_is_self_validating() -> None:
    """门槛（判定 3）：探针证据必须带**三组对照**且自检通过 —— 否则结论不可用。"""
    path = REPO_ROOT / "registry" / "live" / "civil_product_probe.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["aborted"] == "", "探针被中止 ⇒ 证据不可用"
    controls = document["controls"]
    endpoints = document["endpoints"]
    # 共有端点：路由必须存在（`200`）—— 注意空表也是 `200`（civil-cloud 的语义）
    for key in controls["present_expected"]:
        assert endpoints[key]["status_code"] == 200, key
    # 阴性对照：§8.2 已从 CIVIL_NX 摘除的端点必须不存在
    for key in controls["absent_expected"]:
        assert endpoints[key]["verdict"] == "ABSENT", key
    # 方法必须是只读
    assert "GET only" in document["note"][0] or any("只发 GET" in n for n in document["note"])


def test_p161_the_hyper_s_family_is_absent_on_our_civil_instance() -> None:
    """门槛（判定 3）：**21 条 `-M1` 在我方 CIVIL_NX 上全部 `404`** —— 如实记录，不隐瞒。

    ⚠️ 这是**我方实测与外部证据的一处冲突**：对方（MIDAS IT 在职员工，两产品实测）称
    Hyper-S 是 Civil NX 专属、`civil GET ok`；而我方 `gen-local` 与 `civil-cloud`
    **两个实例都 404**。故第一/二批的 `products: [CIVIL_NX]` **保留**（产品级能力声明，
    依 §8.2 的 `DB.UFTR`/`DB.UTBL` 先例），但**两个实例的缺口都如实入 `unavailable_on`**，
    且 `availability` 仍为 `unverified`（**从未在任何实例上验证成功过**）。
    冲突本身记在 `registry/README.md` §8.17。
    """
    document = json.loads(
        (REPO_ROOT / "registry" / "live" / "civil_product_probe.json").read_text(encoding="utf-8")
    )
    family = document["hyper_s_family"]
    assert len(family) == 21
    for key in family:
        assert document["endpoints"][key]["verdict"] == "ABSENT", key
        entry = _entry(key)
        assert entry["availability"] == "unverified", key
        assert set(entry["unavailable_on"]) == {"gen-local", "civil-cloud"}, (
            key,
            entry["unavailable_on"],
        )


def test_p161_the_deferred_set_is_documented_with_its_reason() -> None:
    """门槛（判定 3）：证据文件仍保留 A/B/C 三级条目（**未**被删除，便于后续追溯）。"""
    path = REPO_ROOT / "docs" / "nxsdk_review" / "nxsdk_product_corrections.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    tiers = {item["tier"] for item in document["corrections"]}
    assert tiers == {"A", "B", "C"}
    by_tier = {tier: [i for i in document["corrections"] if i["tier"] == tier] for tier in tiers}
    assert len(by_tier["A"]) == 21
    assert len(by_tier["B"]) == 21
    assert len(by_tier["C"]) == 12
    # 每条都带证据且要求裁决（工具默认预演）
    for item in document["corrections"]:
        assert item["evidence"], item["key"]
        assert item["requires_adjudication"] is True, item["key"]


# ===== 4. 只升不降 =====


def test_p161_no_availability_was_moved() -> None:
    """门槛（判定 4）：全库 `availability` 三档计数与 P149-E 完全一致。"""
    totals: dict[str, int] = {}
    for item in _manifest()["endpoints"]:
        totals[str(item["availability"])] = totals.get(str(item["availability"]), 0) + 1
    assert totals == AVAILABILITY_TOTALS


# ===== 5. 3 处字段类型更正 =====


def test_p161_slanop_opt_stradd_is_a_boolean() -> None:
    """门槛（判定 5）：`DB.SLANOP.OPT_STRADD` = `boolean`（服务端描述 "…Boolean"）。"""
    prop = _find_property(_schema("DB.SLANOP")["schema"], "OPT_STRADD")
    assert prop is not None
    assert prop["type"] == "boolean"


@pytest.mark.parametrize(
    ("key", "expect_enum"),
    [("DB.REBC", False), ("DB.REBR", True)],
)
def test_p161_hoop_type_is_an_integer(key: str, expect_enum: bool) -> None:
    """门槛（判定 5）：`HOOP_TYPE` = `integer`（1=Tied, 2=Spiral）。

    REBC 与 REBR 的差别是**有意的**，照抄对方已复核契约的理由：
    `/info` 对 REBC 未声明枚举（含义是 description 里的散文，**从散文里读出枚举就是发明门控**），
    而 REBR 的 `/info` 声明了 `enum`。
    """
    prop = _find_property(_schema(key)["schema"], "HOOP_TYPE")
    assert prop is not None
    assert prop["type"] == "integer"
    assert prop.get("description") == "Hoop Type (1=Tied, 2=Spiral)"
    if expect_enum:
        assert prop["enum"] == [1, 2]
    else:
        assert "enum" not in prop
        assert "oneOf" not in prop
    # 手册的字符串默认值 `"Ties"` 在 integer 字段上不成立，**不得**保留
    assert "default" not in prop


def test_p161_the_four_unresolved_type_conflicts_are_left_alone() -> None:
    """门槛（判定 6）：证据不足或与已复核契约相反的 4 处**未**改。

    - `DB.EPSE` / `DB.EPST` 的 `LOADING_AREA_GROUP`：对方契约 `provenance: manual` 支持
      `integer`，与服务端 `/info` 的 `string` 相反 ⇒ 契约站在我方，**不改**。
    - `DB.RPSC` 的 `LBAR_INC_FC`：我方 `number` / 服务端 `boolean` / 契约 `integer` ⇒ 三方差歧。
    - `DB.NLLP` 的 `SEIS_TYPE`：仅在 `/info` 出现，契约无此字段 ⇒ 单来源。
    """
    for key in ("DB.EPSE", "DB.EPST"):
        prop = _find_property(_schema(key)["schema"], "LOADING_AREA_GROUP")
        assert prop is not None, key
        assert prop["type"] == "integer", key

    rpsc = _find_property(_schema("DB.RPSC")["schema"], "LBAR_INC_FC")
    assert rpsc is not None
    assert rpsc["type"] == "number"

    nllp = _find_property(_schema("DB.NLLP")["schema"], "SEIS_TYPE")
    assert nllp is not None
    assert nllp["type"] == "integer"
