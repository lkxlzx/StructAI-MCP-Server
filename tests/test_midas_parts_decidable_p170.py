"""P170 / **R163**：P169 判为「不可判别」的 **3** 个 `PARTS` 端点 ⇒ **可判别化**。

本批的一件事（`docs/07` §15.5 的 P170 入口 A 组）
------------------------------------------------
P169 在**纯梁**模型上判定 `RESULTANT_FORCES` / `_VBM` / `DESIGN.STEEL.…TABLE` 的
**基线就是空块** ⇒ 无法区分「取值无效」与「模型无数据」⇒ **如实留缺**。
本批建了一个**带相应结果**的自建模型（`registry/tools/build_parts_discriminator_p170.py`）
⇒ 重跑 P169 的探针（判据已就位）⇒ **6 / 6** 个端点**可判别**。

⚠️ **P170 更正 P169 的「需要什么」**：`RESULTANT_FORCES` **不是**要**板 / 实体**单元，
而是要**虚拟截面**（手册 `db/VSEC` + `db/VBEM`）—— 本批**两样都建**以一次消除疑点。

本文件钉住的判据（**铁律 ⓪**：效果，**不**是状态码）
-------------------------------------------------
1. **可判别化可复算**：建模器的 `--check` 断言「3 个原不可判别端点**都有数据行**」；
2. **建模构成**：板网格 + 1 根梁 + 虚拟截面 ×2 + 虚拟梁 ×1（**逐条**读回验证）；
3. **设计链顺序**（**R141**）：`DSTL → DCO → DCTL → MEMB → LCOM-STEEL → CODE-ANAL`；
4. **P169 的证据未被覆盖**（P170 写**另一份**文件）；
5. **台账**：3 个端点 `closed`（**R163**），且生成器与已落盘一致。
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
"""仓库根目录。"""

TOOLS = REPO_ROOT / "registry" / "tools"
LIVE = REPO_ROOT / "registry" / "live"

BUILDER_TOOL = TOOLS / "build_parts_discriminator_p170.py"
BUILDER_EVIDENCE = LIVE / "parts_discriminator_p170.json"

PARTS_PROBE_EVIDENCE_P170 = LIVE / "parts_disposition_probe_p170.json"
PARTS_PROBE_EVIDENCE_P169 = LIVE / "parts_disposition_probe.json"

PARTS_TOOL = TOOLS / "sync_parts_enum.py"
CENSUS_TOOL = TOOLS / "check_spec_enums.py"
AUDIT = LIVE / "spec_enum_audit.json"

DECIDED = (
    "POST.TABLE.RESULTANT_FORCES",
    "POST.TABLE.RESULTANT_FORCESVBM",
    "DESIGN.STEEL.KDS-41-30-2022.TABLE",
)
"""P169 判为**不可判别**、P170 **可判别化**的 **3** 个端点。"""

STEEL_TOKEN = "STEELMEMBERDESIGNFORCES"
FAKE_PART = "PartZ"
BEAM_ELEM = 25
PLATE_COUNT = 24
NODE_COUNT = 37

EXPECTED_DESIGN_ORDER = [
    "/DESIGN/STEEL/DSTL",
    "/DESIGN/STEEL/KDS-41-30-2022/DCO",
    "/DESIGN/STEEL/KDS-41-30-2022/DCTL",
    "/DESIGN/STEEL/KDS-41-30-2022/MEMB",
    "/DB/LCOM-STEEL",
    "/DESIGN/STEEL/KDS-41-30-2022/CODE-ANAL",
]
"""`app/infrastructure/adapters/midas/operations.py` 的 `DESIGN.STEEL` 编排（**R141**）。"""


def _load(path: pathlib.Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ===== 1. 可判别化 =====


def test_p170_the_builder_is_offline_self_consistent() -> None:
    """门槛（**可复算**）：建模器的 `--check` 通过（判据全真，**零请求**）。"""
    tool = _load(BUILDER_TOOL, "build_parts_discriminator_p170")
    assert tool.main(["--check"]) == 0


def test_p170_the_three_endpoints_now_have_baseline_rows() -> None:
    """门槛（**可判别化的定义**）：3 个端点**都有数据行**（P169 时基线是**空块**）。"""
    rows = _json(BUILDER_EVIDENCE)["table_rows"]
    for token in ("RESULTANT_FORCES", "RESULTANT_FORCESVBM", STEEL_TOKEN):
        assert rows.get(token), f"{token} 的基线仍是空块 ⇒ 未实现可判别化"
    assert _json(BUILDER_EVIDENCE)["verdict"] == "PASSED"


def test_p170_the_model_composition_is_read_back_verified() -> None:
    """门槛（**建模构成**）：板网格 + 1 根梁 + 虚拟截面 ×2 + 虚拟梁 ×1（**逐条**读回）。"""
    document = _json(BUILDER_EVIDENCE)
    model = {str(item["uri"]): item for item in document["model"]}
    for uri in ("/db/node", "/db/elem", "/db/thik", "/db/vsec", "/db/vbem"):
        assert uri in model, f"{uri} 未建模"
        assert model[uri]["ok"], f"{uri} 的写入未通过读回验证"
    # 单元 = 24 板 + 1 梁
    assert model["/db/elem"]["expected"] == PLATE_COUNT + 1
    assert model["/db/node"]["expected"] == NODE_COUNT
    # 虚拟截面 2 个（分两次写 ⇒ 读回 2）；虚拟梁 1 个
    assert model["/db/vsec"]["readback"] == 2
    assert model["/db/vbem"]["readback"] == 1


def test_p170_the_design_chain_follows_the_operation_plan_order() -> None:
    """门槛（**R141**）：设计链的顺序与 `operations.py` 的 `DESIGN.STEEL` **逐条**一致。

    ⚠️ 前四步是**配置**（手册方法 `GET, PUT, DELETE`）⇒ 用 `PUT`，**不是** `GET`。
    """
    document = _json(BUILDER_EVIDENCE)
    assert [str(item["uri"]) for item in document["design"]] == EXPECTED_DESIGN_ORDER
    methods = {str(item["uri"]): item for item in document["design"]}
    for uri in EXPECTED_DESIGN_ORDER[:4]:
        assert methods[uri]["status"] < 500
    # ⑥ 设计执行**真的**产出结果
    assert document["table_rows"][STEEL_TOKEN] > 0


def test_p170_the_builder_declares_the_dstl_wrong_field_finding() -> None:
    """门槛（**如实登记**）：`DSTL` 实测 `400 Wrong Field`（**E-06**）**不**被当成成功。"""
    document = _json(BUILDER_EVIDENCE)
    dstl = next(item for item in document["design"] if item["uri"].endswith("/DSTL"))
    assert dstl["status"] == 400, "DSTL 的实测结论变了 ⇒ 勘误 E-06 需复核"
    assert "E-06" in str(document.get("note") or ""), "证据里应登记 E-06"


# ===== 2. P169 的证据未被覆盖 =====


def test_p170_the_p169_evidence_is_not_overwritten() -> None:
    """门槛（**不覆盖既有证据**）：P169 的证据仍是**纯梁**模型上的 **3 / 6** 可判别。"""
    document = _json(PARTS_PROBE_EVIDENCE_P169)
    assert str(document["project"]).endswith("p164c-concrete.mgbx")
    assert document["verdict"] == "PASSED"
    assert set(document["decided_endpoints"]) == {
        "POST.TABLE.BEAMFORCE",
        "POST.TABLE.BEAMFORCEVBM",
        "POST.TABLE.THISBEAMFORCE",
    }
    assert set(document["undecidable_endpoints"]) == set(DECIDED)


def test_p170_the_p170_evidence_is_on_the_discriminator_model() -> None:
    """门槛（**可判别化可复算**）：P170 的证据在**可判别**模型上，且 **6 / 6** 可判别。"""
    document = _json(PARTS_PROBE_EVIDENCE_P170)
    assert str(document["project"]).endswith("p170-discriminator.mgbx")
    assert document["undecidable_endpoints"] == []
    assert set(document["decided_endpoints"]) == set(DECIDED) | {
        "POST.TABLE.BEAMFORCE",
        "POST.TABLE.BEAMFORCEVBM",
        "POST.TABLE.THISBEAMFORCE",
    }
    assert document["sentinel"]["unchanged"] is True


# ===== 3. 判据（**真的过滤**）=====


def test_p170_the_three_endpoints_are_decided_by_real_filtering() -> None:
    """门槛（**铁律 ⓪**）：3 个端点的取值判据 = **有数据行且少于基线**（**不**是状态码）。"""
    document = _json(PARTS_PROBE_EVIDENCE_P170)
    rows = {str(row["endpoint"]): row for row in document["targets"]}
    for endpoint in DECIDED:
        row = rows[endpoint]
        verdict = row["verdict"]
        assert verdict["decidable"] is True, endpoint
        baseline = verdict["baseline_rows"]
        measured = row["measured"]
        for value, info in measured.items():
            if not info["valid"]:
                continue
            assert info["data_rows"] < baseline, f"{endpoint}/{value} 未真的过滤"
        # 伪取值**空块**（与无效取值**同形**）⇒ 负向对照成立
        assert verdict["fake_empty"] is True, endpoint


def test_p170_the_steel_parts_default_is_measurably_invalid() -> None:
    """门槛（**E-05**）：`DESIGN.STEEL.…TABLE` 的 `PARTS.default = ['All']` 实测**空块**。

    ⚠️ **不**据此删 `All`（**只增不减**）—— 只登记「声明可疑」。
    """
    document = _json(PARTS_PROBE_EVIDENCE_P170)
    row = next(
        item
        for item in document["targets"]
        if item["endpoint"] == "DESIGN.STEEL.KDS-41-30-2022.TABLE"
    )
    assert row["example_value"] == "All"
    assert row["measured"]["All"]["valid"] is False, "`All` 的实测结论变了 ⇒ E-05 需复核"
    # 而 `PartI` 等**真的过滤**
    assert row["measured"]["PartI"]["valid"] is True
    assert row["measured"]["PartI"]["data_rows"] < row["verdict"]["baseline_rows"]


def test_p170_the_beam_element_is_declared_in_the_builder() -> None:
    """门槛（**设计链的输入**）：`MEMB` 指派的正是建模器写下的**梁**单元。"""
    tool = _load(BUILDER_TOOL, "build_parts_discriminator_p170_beam")
    memb = next(item for item in tool.design_bodies() if item["uri"].endswith("/MEMB"))
    assert memb["body"]["Assign"]["1"]["AELEM"] == [BEAM_ELEM]
    assert tool.ELEM_BEAM == BEAM_ELEM, "梁单元编号与建模器不一致"


# ===== 4. 台账与收口 =====


def test_p170_the_ledger_closes_the_three_endpoints() -> None:
    """门槛（**台账**）：3 个端点 `closed`（**R163**）+ 生成器一致。

    ⚠️ **P178 / R171（事实变更）**：`DESIGN.STEEL.KDS-41-30-2022.TABLE::PARTS` 由
    `closed` 改 **`left_open`** —— **R170** 修好闸门后，它**第一次**被真正检查，
    暴露手册示例的 `"All"` 被拦。
    ⚠️ **P179 / R172（事实变更，并更正 P178 的记法）**：P178 写「P170 从未实测过 `"All"`」
    **是错的** —— `registry/live/parts_disposition_probe_p170.json` 的 `measured.All`
    明确记录 `status=200` · `empty_block=true` · `valid=false`（**发过、回空块**）。
    ⇒ `"All"` **不是**合法取值 ⇒ 台账 **`closed`**（收口依据 = **实测证据**，不是生成器）。
    ⚠️ **P170 的方法学结论不变**：`PartI`/`PartJ`/`Part1/4`… 的**过滤效果**仍成立。
    """
    document = _json(AUDIT)
    dispositions = {str(item["key"]): item for item in document["dispositions"]}
    for endpoint in DECIDED:
        key = f"{endpoint}::PARTS"
        assert key in dispositions, f"台账缺 {key}"
        item = dispositions[key]
        assert item["status"] == "closed", f"{key} 应已收口"
        if key in _EVIDENCE_CLOSED_P179:
            assert item["ruling"] == "R172", f"{key} 的裁决号应为 R172（P179 收口）"
            assert item["evidence"], f"{key} 的收口依据必须是实测证据"
            assert item.get("generator_agrees") is True, f"{key} 的证据文件不存在"
            continue
        assert item["ruling"] == "R163", f"{key} 的裁决号应为 R163"
        assert item.get("generator_agrees") is True, f"{key} 的生成器不一致"


_EVIDENCE_CLOSED_P179 = frozenset({"DESIGN.STEEL.KDS-41-30-2022.TABLE::PARTS"})
"""**P179** 用**实测证据**（而非生成器）收口的项（见上方用例的说明）。"""


def test_p170_the_parts_generator_merges_both_evidence_files() -> None:
    """门槛（**来源可复算**）：生成器**合并**两份证据（纯梁 + 可判别模型），**只增不减**。"""
    tool = _load(PARTS_TOOL, "sync_parts_enum_p170")
    assert "parts_disposition_probe_p170.json" in tool.PROBE_FILENAMES
    assert "parts_disposition_probe.json" in tool.PROBE_FILENAMES
    assert tool.main(["--repo", str(REPO_ROOT), "--check"]) == 0
    for item in tool.targets(REPO_ROOT):
        assert set(item["on_disk"]) <= set(item["expected"]), item["key"]


def test_p170_the_decidable_endpoints_only_gain_measured_values() -> None:
    """门槛（**R151 的镜像**）：可判别端点的收口来源**只**来自**实测有效**的取值。

    ⚠️ 生成器**不**能把**实测无效**的示例体取值（`All`）当成收口来源。
    """
    tool = _load(PARTS_TOOL, "sync_parts_enum_p170_sources")
    for item in tool.targets(REPO_ROOT):
        if not item["probed"]:
            continue  # 不可判别的端点**没有**实测来源（如实留缺）
        valid = set(item["probed"])
        assert set(item["manual"]) <= valid, (
            f"{item['key']} 的手册示例体取值里有**未实测有效**的 ⇒ 按示例体硬凑"
        )
