"""P154 / **R126 裁决 A′ 落地 + R128（`DB.CONS` 请求体形状）** —— 接口层写路径的实测判据。

背景
----
P153 把 R126 做成了**裁决输入**（`registry/live/canonical_field_gap.json`）。P154 按
`docs/reports/P0_裁决清单_v1.0.md` 的 **D1 = A′** 落地：**只**扩 `DB.MATL`（**11**）+
`DB.SECT`（**6**）= **17** 个 canonical 字段；`DB.BMLD` / `DB.PRES` 延后。

本文件的判定点
--------------
1. **A′ 落地**（`app/.../transforms.py`）：17 个 `(canonical, native)` 逐条在字段表里，且
   **每一个 native 叶子都已在数据侧请求 Schema 里声明**（⇒ 本改动**不**需要改 `registry/**`）。
2. **接口层产出的 body == 手册示例 body**（**逐叶子路径相同**）—— R126 在**字段级**关闭。
3. **接口层写路径**（`registry/live/interface_path_probe.json`）：**13** 条 = **11** `PASSED` +
   **2** `FAILED`（P152 当时是 `4 / 9`）；`residue` 空、`aborted` 空。
4. **R128**（`registry/live/boundary_shape_probe.json`）：`DB.CONS` 的 `Assign`
   **外层键 = 节点编号**
   ⇒ 接口层当前产出的 `{"Assign": {"ITEMS": […]}}` **`400`**；数据侧形态
   `{"Assign": {"<节点编号>": {"ITEMS": […]}}}` **`200` 且落库**；
   外层键**不是**存在的节点编号时原生**静默 `200` 而什么都不建**（假成功陷阱）。
5. **不变量**：`write_path_coverage()` = `0 / 633`（`model_write_ratio` `0 / 434`）· 映射缺口
   **517** = **271** + **246** · R118 子桶与留缺账本**一行未动**；接口层判据**不**并入覆盖率分子。
6. **实例门控**：缺 `MIDAS_BASE_URL` / `MIDAS_MAPI_KEY` 时，真实用例如实 `skip`。
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.infrastructure.adapters.midas.live import write_path_coverage
from app.infrastructure.adapters.midas.registry import MidasRegistry
from app.infrastructure.adapters.midas.transforms import (
    MaterialTransformer,
    SectionTransformer,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录。"""

WRITE_EVIDENCE = REPO_ROOT / "registry" / "live" / "interface_path_probe.json"
READ_EVIDENCE = REPO_ROOT / "registry" / "live" / "interface_read_probe.json"
FIELD_GAP = REPO_ROOT / "registry" / "live" / "canonical_field_gap.json"
GAP_EVIDENCE = REPO_ROOT / "registry" / "live" / "interface_mapping_gap.json"
CLASSIFICATION = REPO_ROOT / "registry" / "live" / "interface_mapping_classification.json"
BOUNDARY_EVIDENCE = REPO_ROOT / "registry" / "live" / "boundary_shape_probe.json"
TEMPLATES = REPO_ROOT / "registry" / "live" / "write_templates.json"
BOUNDARY_TOOL = REPO_ROOT / "registry" / "tools" / "probe_boundary_shape.py"
PROBE_TOOL = REPO_ROOT / "registry" / "tools" / "probe_interface_paths.py"

APRIME_MATL = (
    ("he_spec", "HE_SPEC"),
    ("he_cond", "HE_COND"),
    ("plmt", "PLMT"),
    ("p_name", "P_NAME"),
    ("bmass_dens", "bMASS_DENS"),
    ("damp_rat", "DAMP_RAT"),
    ("p_type", "PARAM[].P_TYPE"),
    ("standard", "PARAM[].STANDARD"),
    ("code", "PARAM[].CODE"),
    ("db", "PARAM[].DB"),
    ("belast", "PARAM[].bELAST"),
)
"""**A′ 的 11 个 `DB.MATL` 字段**（`canonical` ← `native`；canonical 名 = P153 证据包的 hint）。"""

APRIME_SECT = (
    ("datatype", "SECT_BEFORE.DATATYPE"),
    ("horz_offset_opt", "SECT_BEFORE.HORZ_OFFSET_OPT"),
    ("vert_offset_opt", "SECT_BEFORE.VERT_OFFSET_OPT"),
    ("use_shear_deform", "SECT_BEFORE.USE_SHEAR_DEFORM"),
    ("use_warping_effect", "SECT_BEFORE.USE_WARPING_EFFECT"),
    ("vsize", "SECT_BEFORE.SECT_I.vSIZE"),
)
"""**A′ 的 6 个 `DB.SECT` 字段**（合计 **17**）。"""

EXPECTED_WRITE_ROWS = 13
EXPECTED_WRITE_COUNTS = {"PASSED": 13}
"""⚠️ **P157 同步（有实测依据）**：P154 是 `11 / 2`；**D2 = A 落地**（`BoundaryTransformer`
加第 **7** 个自由度 `rw` ⇒ `CONSTRAINT` 输出 **7** 位）后重测 ⇒ **`13 / 0`**。断言**未**放宽。"""
EXPECTED_WRITE_BY_PATH = {
    "add": {"PASSED": 5},
    "edit": {"PASSED": 2},
    "delete": {"PASSED": 6},
}
EXPECTED_PASSED = (
    ("add", "DB.CONS"),
    ("add", "DB.ELEM"),
    ("add", "DB.MATL"),
    ("add", "DB.NODE"),
    ("add", "DB.SECT"),
    ("delete", "DB.CONS"),
    ("delete", "DB.ELEM"),
    ("delete", "DB.GRUP"),
    ("delete", "DB.MATL"),
    ("delete", "DB.NODE"),
    ("delete", "DB.SECT"),
    ("edit", "DB.ELEM"),
    ("edit", "DB.NODE"),
)
"""**13** 条 `PASSED`（三条路径各有证据；P152 当时只有 4 条，P154 为 11 条）。"""

REMAINING_FAILED: tuple[tuple[str, str], ...] = ()
"""⚠️ **P157**：`DB.CONS` 的添加 / 删除**已** `PASSED`（D2 = A 落地）⇒ **零失败**。"""

EXPECTED_BOUNDARY_VARIANTS = (
    "assign_items",
    "assign_node_keyed_items",
    "assign_node_keyed_items_no_id",
    "assign_node_keyed_item",
    "assign_nonexistent_node_key",
)
EXPECTED_BOUNDARY_VERDICT = "assign_node_keyed_items,assign_node_keyed_items_no_id"
"""被原生接受的形状（**外层键 = 节点编号 + 内层 `ITEMS`**）。"""

EXPECTED_FIELD_GAP = {
    "template_endpoints": 71,
    "with_transformer": 12,
    "without_transformer": 59,
    "field_set_gap": 2,
    "value_gap": 2,
    "no_canonical_model": 59,
    "covered": 8,
}
"""⚠️ **P157 同步（有实测依据）**：**D2 = A 落地**后接口层的 `CONSTRAINT` 由 **6** 位变 **7** 位，
与手册模板 `"1111000"` 的**长度**一致 ⇒ `DB.CONS` 从 `value_gap` 移入 `covered`
（取值缺口 **3 → 2**、已覆盖 **5 → 6**；字段集缺口仍 **2**、模板端点仍 **71 = 10 + 61**）。
依据 = `registry/live/{interface_path_probe,canonical_field_gap}.json`（`--recon` 复算）。"""
EXPECTED_GAP_TOTAL = 510
EXPECTED_GAP_NOT_IN_CONTRACT = 264
EXPECTED_GAP_NO_READBACK = 246
EXPECTED_CLASSIFICATION_ADOPTION = {
    "adoptable_with_existing_canonical_model": 0,
    "adoptable_with_manual_example": 51,
    "needs_product_decision": 213,
}
EXPECTED_WRITE_PATH_TOTAL = 633
EXPECTED_MODEL_WRITE_TOTAL = 434


def _load(path: Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _live_ready() -> bool:
    """真实接口层探针的执行条件（`MIDAS_BASE_URL` + `MIDAS_MAPI_KEY`）。"""
    return bool((os.environ.get("MIDAS_BASE_URL") or "").strip()) and bool(
        (os.environ.get("MIDAS_MAPI_KEY") or "").strip()
    )


def _leaves(value: Any, prefix: str = "") -> set[str]:
    """递归叶子**点路径**集合（数组用 `[]` 归一）。"""
    if isinstance(value, dict):
        rows: set[str] = set()
        for key, item in value.items():
            rows |= _leaves(item, f"{prefix}.{key}" if prefix else str(key))
        return rows
    if isinstance(value, list):
        rows = set()
        for item in value:
            rows |= _leaves(item, f"{prefix}[]")
        return rows
    return {prefix}


# ===== 1. A′ 落地（判定点 = `transforms.py`）=====


def _norm(paths: set[str]) -> set[str]:
    """叶子路径归一（去掉数组后缀 `[]`，便于跨形态比较）。"""
    return {path.replace("[]", "") for path in paths}


def test_p154_aprime_fields_are_declared_with_the_evidence_hints() -> None:
    """门槛：17 个 `(canonical, native)` 逐条在字段表里（canonical 名 = P153 证据包的 hint）。"""
    material = {field.canonical: field.native for field in MaterialTransformer.fields}
    section = {field.canonical: field.native for field in SectionTransformer.fields}
    for canonical, native in APRIME_MATL:
        assert material.get(canonical) == native, (canonical, native)
    for canonical, native in APRIME_SECT:
        assert section.get(canonical) == native, (canonical, native)
    assert len(APRIME_MATL) == 11 and len(APRIME_SECT) == 6
    # canonical 名 = P153 证据包当时给出的 `canonical_hint`（= native 叶子的小写；逐条一致）
    for canonical, native in APRIME_MATL + APRIME_SECT:
        leaf = native.split(".")[-1].replace("[]", "")
        assert canonical == leaf.lower(), (canonical, native)
    # 原有的必填字段**未**被改动
    assert material["name"] == "NAME" and material["type"] == "TYPE"
    assert section["name"] == "SECT_NAME" and section["section_type"] == "SECTTYPE"


def test_p154_aprime_native_fields_are_all_schema_declared() -> None:
    """门槛：17 个 native 叶子**全部**已在数据侧请求 Schema 里声明 ⇒ **不**需要改 `registry/**`。"""
    registry = MidasRegistry.load(REPO_ROOT / "registry")
    for cls, pairs in ((MaterialTransformer, APRIME_MATL), (SectionTransformer, APRIME_SECT)):
        transformer = cls(registry)
        for _canonical, native in pairs:
            leaf = native.split(".")[-1].replace("[]", "")
            assert leaf in transformer.fields_for_path(native), (cls.name, native)


def test_p154_the_field_set_gap_shrinks_by_exactly_the_two_endpoints() -> None:
    """门槛：A′ 后「字段集缺口」只剩 `DB.BMLD` / `DB.PRES`（`DB.MATL` / `DB.SECT` 已关闭）。"""
    gap = _json(FIELD_GAP)
    for key, expected in EXPECTED_FIELD_GAP.items():
        assert int(gap["summary"][key]) == expected, (key, gap["summary"][key])
    assert tuple(gap["buckets"]["field_set_gap"]) == ("DB.BMLD", "DB.PRES")
    assert tuple(gap["options"]["A_extend_canonical_field_set"]["endpoints"]) == (
        "DB.BMLD",
        "DB.PRES",
    )
    index = {str(row["endpoint"]): row for row in gap["endpoints"]}
    assert index["DB.MATL"]["missing_in_canonical"] == []
    assert index["DB.SECT"]["missing_in_canonical"] == []
    assert index["DB.SECT"]["gap_class"] == "covered"
    # ⚠️ **P157**：`DB.CONS` 的**取值**缺口已关闭（`CONSTRAINT` 由 6 位变 **7** 位 ⇒ 与模板一致）
    assert index["DB.CONS"]["gap_class"] == "covered"
    assert tuple(gap["buckets"]["value_gap"]) == ("DB.ELEM", "DB.MATL")
    assert "DB.CONS" not in gap["value_gaps"]


# ===== 2. 接口层产出的 body == 手册示例 body（R126 在字段级关闭）=====


def test_p154_the_interface_body_matches_the_manual_example_field_for_field() -> None:
    """门槛：手册示例用到的**每一个**叶子路径都在接口层 body 里；A′ 的 17 个 native 逐条在。

    ⚠️ 反向**不**要求相等：接口层另有**既有**可选字段（`density` / `poisson_ratio`）会一并出现 ——
    那是 P152 起就有的 canonical 字段，**不**属 R126 的缺口（**不**放宽、也**不**多算）。
    """
    tool = _load(PROBE_TOOL, "structai_probe_interface_paths_p154")
    registry = MidasRegistry.load(REPO_ROOT / "registry")
    templates = _json(TEMPLATES)["templates"]
    for endpoint, cls, parameters, aprime in (
        (
            "DB.MATL",
            MaterialTransformer,
            tool._material_parameters("1")["materials"][0],
            APRIME_MATL,
        ),
        ("DB.SECT", SectionTransformer, tool._section_parameters("1")["sections"][0], APRIME_SECT),
    ):
        item = dict(parameters)
        item.pop("id", None)
        native = _norm(_leaves(cls(registry).to_native(item)))
        manual = _norm(_leaves(templates[endpoint]["body"]))
        assert manual <= native, (endpoint, sorted(manual - native))
        aprime_natives = _norm({native_path for _canonical, native_path in aprime})
        assert aprime_natives <= native, (endpoint, sorted(aprime_natives - native))
        # 手册示例用到的字段**一个不少**（R126 在字段级关闭）
        assert not (manual - native), endpoint


def test_p154_the_manual_example_values_are_not_injected_as_defaults() -> None:
    """门槛（**不**放宽「不臆造字段」）：字段表里**没有**默认值 —— 不给值就**不**出现在 body。"""
    registry = MidasRegistry.load(REPO_ROOT / "registry")
    material = MaterialTransformer(registry).to_native({"name": "M", "type": "STEEL"})
    assert material == {"NAME": "M", "TYPE": "STEEL"}, material
    section = SectionTransformer(registry).to_native({"name": "S", "section_type": "DBUSER"})
    assert section == {"SECT_NAME": "S", "SECTTYPE": "DBUSER"}, section
    # A′ 的字段**未**被声明为必填
    assert not [
        field
        for field in MaterialTransformer.fields
        if field.canonical in dict(APRIME_MATL) and field.required
    ]
    assert not [
        field
        for field in SectionTransformer.fields
        if field.canonical in dict(APRIME_SECT) and field.required
    ]


# ===== 3. 接口层写路径实测（11 / 2）=====


def test_p154_the_interface_write_path_is_thirteen_of_thirteen() -> None:
    """门槛：**13** 条 = **13** `PASSED` + **0** `FAILED`；零残留、未中止。

    ⚠️ **P157 同步（有实测依据）**：P154 为 `11 / 2`；**D2 = A 落地**（`BoundaryTransformer`
    加第 **7** 个自由度 `rw`）后 `DB.CONS` 的添加 / 删除**都** `PASSED` ⇒ **`13 / 0`**。
    断言**未**放宽（`passed` / `failed` 的**集合**判定原样保留）。
    """
    document = _json(WRITE_EVIDENCE)
    rows = document["paths"]
    assert len(rows) == EXPECTED_WRITE_ROWS
    assert document["counts"] == EXPECTED_WRITE_COUNTS
    assert document["by_path"] == EXPECTED_WRITE_BY_PATH
    assert document["residue"] == {}
    assert document["aborted"] == ""
    assert document["sentinel_before"] == document["sentinel_after"]
    passed = {(str(row["path"]), str(row["endpoint"])) for row in rows if row["status"] == "PASSED"}
    failed = {(str(row["path"]), str(row["endpoint"])) for row in rows if row["status"] == "FAILED"}
    assert passed == set(EXPECTED_PASSED)
    assert failed == set(REMAINING_FAILED) == set()


def test_p154_the_boundary_row_now_passes_with_seven_digits() -> None:
    """门槛（**P157**）：`DB.CONS` 的添加行 `PASSED`，body = 已修形状 + **7** 位 `CONSTRAINT`。

    ⚠️ P154 / P156 时该行是 `FAILED`（形状级 → 取值级成因）；**D2 = A 落地**后转为 `PASSED`。
    本用例**保留并加强** P156 的两条判定：① 外层键 = **节点编号**（**不**是字面量 `ITEMS`）；
    ② 条目键集 = `{ID, GROUP_NAME, CONSTRAINT}`；并新增 ③ `CONSTRAINT` 恰为 **7** 位。
    """
    document = _json(WRITE_EVIDENCE)
    add = next(
        row
        for row in document["paths"]
        if row["path"] == "add" and str(row["endpoint"]) == "DB.CONS"
    )
    assert add["status"] == "PASSED", add
    assert add["readback"]["present"] is True, add["readback"]
    assert (add.get("cleanup") or {}).get("gone") is True, add.get("cleanup")
    bodies = [
        item["body"]
        for item in add["requests"]
        if item["method"] == "POST" and str(item["path"]).endswith("/DB/CONS")
    ]
    assert bodies, add["requests"]
    outer_key = next(iter(bodies[0]["Assign"]))
    # 外层键 = **节点编号**（**不**是字面量 `ITEMS`）—— R128 的修复（P155）
    assert outer_key.isdigit(), bodies[0]
    assert outer_key != "ITEMS", bodies[0]
    entry = bodies[0]["Assign"][outer_key]["ITEMS"][0]
    assert set(entry) == {"ID", "GROUP_NAME", "CONSTRAINT"}, entry
    # ⚠️ **P157 / D2 = A**：`CONSTRAINT` **恰好 7 位**（`DX,DY,DZ,RX,RY,RZ,RW`）
    assert len(str(entry["CONSTRAINT"])) == 7, entry
    assert str(entry["CONSTRAINT"]) == "1110000", entry
    # 该行**没有**任何原生拒绝（`>= 400`）
    assert not [item for item in add["requests"] if int(item["status"]) >= 400], add["requests"]


# ===== 4. R128：`DB.CONS` 的请求体形状（新裁决）=====


def test_p154_the_boundary_shape_ab_is_recomputable_and_bounded() -> None:
    """门槛：形状 A/B **恰好 5** 个变体、结论与证据一致、清理逐条确认、请求数有界。"""
    tool = _load(BOUNDARY_TOOL, "structai_probe_boundary_shape_p154")
    document = _json(BOUNDARY_EVIDENCE)
    assert document["criterion_version"] == 1
    assert tuple(str(row["name"]) for row in document["variants"]) == EXPECTED_BOUNDARY_VARIANTS
    assert str(document["verdict"]) == EXPECTED_BOUNDARY_VERDICT
    assert len(document["requests"]) <= tool.MAX_REQUESTS, len(document["requests"])
    assert document["residue"] == {} and document["aborted"] == ""
    assert document["sentinel_before"] == document["sentinel_after"]
    for item in document["cleanup"]:
        assert item["gone"] is True, item


def test_p154_the_interface_layer_shape_is_the_rejected_one() -> None:
    """门槛：接口层当前形状 `{"Assign": {"ITEMS": […]}}` 被原生 `400` 拒。"""
    document = _json(BOUNDARY_EVIDENCE)
    index = {str(row["name"]): row for row in document["variants"]}
    current = index["assign_items"]
    assert current["http"] == 400 and current["status"] == "FAILED"
    assert current["created"] is False
    assert "Wrong Field" in str(current["native_error"]), current
    flat = index["assign_node_keyed_item"]
    assert flat["http"] == 400 and flat["created"] is False, flat


def test_p154_the_accepted_shape_is_node_keyed_with_nested_items() -> None:
    """门槛：被接受的形状 = **外层键为节点编号 + 内层 `ITEMS`**（内层 `ID` 可选）。"""
    document = _json(BOUNDARY_EVIDENCE)
    index = {str(row["name"]): row for row in document["variants"]}
    for name in ("assign_node_keyed_items", "assign_node_keyed_items_no_id"):
        row = index[name]
        assert row["http"] == 200 and row["created"] is True, row
        assert row["status"] == "PASSED", row
        assert row["readback_keys"] == ["CONSTRAINT", "GROUP_NAME", "ID"], row
        assert (row.get("cleanup") or {}).get("gone") is True, row


def test_p154_an_unknown_node_key_is_a_silent_no_op() -> None:
    """门槛（**假成功陷阱**）：外层键**不是**存在的节点编号 ⇒ 原生 `200` 却**什么都不建**。"""
    document = _json(BOUNDARY_EVIDENCE)
    row = next(
        item for item in document["variants"] if item["name"] == "assign_nonexistent_node_key"
    )
    assert row["http"] == 200, row
    assert row["created"] is False, row
    assert row["status"] == "FAILED", row
    assert row["readback_keys"] == [], row


def test_p154_the_boundary_shape_check_mode_agrees_offline() -> None:
    """门槛：`probe_boundary_shape --check` 离线跑通（退出码 0）。"""
    result = subprocess.run(
        [sys.executable, str(BOUNDARY_TOOL), "--check"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "形状证据自洽" in result.stdout


# ===== 5. 不变量（本批**不得**放宽既有判定）=====


def test_p154_the_invariants_are_untouched() -> None:
    """门槛：写路径分母 / 缺口 / 分类 / 读路径子桶**一行未变**（A′ 只动字段表）。"""
    registry = MidasRegistry.load(REPO_ROOT / "registry")
    coverage = write_path_coverage(registry, [])
    assert coverage.ratio == f"0 / {EXPECTED_WRITE_PATH_TOTAL}"
    assert coverage.model_write_ratio == f"0 / {EXPECTED_MODEL_WRITE_TOTAL}"
    gap = _json(GAP_EVIDENCE)
    assert int(gap["gap_total"]) == EXPECTED_GAP_TOTAL
    assert len(gap["gap_three_step"]) == EXPECTED_GAP_NOT_IN_CONTRACT
    assert len(gap["gap_no_readback"]) == EXPECTED_GAP_NO_READBACK
    classification = _json(CLASSIFICATION)
    assert classification["adoption_counts"] == EXPECTED_CLASSIFICATION_ADOPTION
    read = _json(READ_EVIDENCE)
    assert read["counts"] == {"PASSED": 2, "PARTIAL": 7, "FAILED": 6}
    assert read["write_requests"] == 0
    assert read["residue"] == {}


def test_p154_the_read_path_evidence_has_no_credentials() -> None:
    """门槛（`docs/07` §14.3）：两份新证据里**没有**凭据形态。"""
    for path in (WRITE_EVIDENCE, READ_EVIDENCE, BOUNDARY_EVIDENCE, FIELD_GAP):
        raw = path.read_text(encoding="utf-8")
        for marker in ("MAPI-Key", "MAPI_KEY", "mapi-key", "password", "secret"):
            assert marker not in raw, (path.name, marker)


# ===== 6. 实例门控 =====


def test_p154_the_live_probes_are_skipped_without_the_documented_declaration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛（`docs/04` §71–§72）：缺环境声明 ⇒ 真实用例如实 `skip`（**不**失败、**不**伪造）。"""
    for name in ("MIDAS_BASE_URL", "MIDAS_MAPI_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert _live_ready() is False


@pytest.mark.skipif(
    not _live_ready(),
    reason="真实接口层探针需 MIDAS_BASE_URL + MIDAS_MAPI_KEY（见 scripts/load-midas-env.ps1）",
)
def test_p154_the_live_probes_are_bounded_and_read_only_in_shape() -> None:
    """门槛：两个探针**有界**（分块 ≤ 20 / 请求数 ≤ 上限）且形状 A/B 只碰**一个**自建节点。

    ⚠️ 本用例**不**重跑请求（真实结果已落证据）；它只断言「纪律参数可被读出」。
    """
    probe = _load(PROBE_TOOL, "structai_probe_interface_paths_p154_live")
    boundary = _load(BOUNDARY_TOOL, "structai_probe_boundary_shape_p154_live")
    assert probe.CHUNK_SIZE <= 20
    assert boundary.MAX_REQUESTS <= 30
    assert len(boundary.VARIANTS) == len(EXPECTED_BOUNDARY_VARIANTS)
    assert boundary.CONSTRAINT == "1111000"
    for exercise in probe.EXERCISES:
        assert exercise["path"] in {"add", "edit", "delete"}
