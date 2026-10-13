"""P157 / **D2 = A 的落地**：`BoundaryTransformer` 的第 **7** 个自由度 `rw`。

裁决与依据
----------
用户裁决 **D2 = A**（`docs/reports/P0_裁决清单_v1.0.md` §7，2026-10-11）：
**扩 canonical，加 `rw`（第 7 个自由度）** —— **不**采用方案 B（固定补 `"0"`，属**臆造**取值）。

依据（`registry/live/constraint_value_probe.json`，**形状固定**为已修的编号键控形态）：

| `CONSTRAINT` | 长度 | 原生 |
| --- | --- | --- |
| `"11100"` | 5 | `400 Unknown Error` |
| `"111000"`（P156 时接口层产出） | 6 | `400 [错误] 约束条件输入有错误。` |
| `"1110000"`（六自由度 + `RW = 0`） | **7** | **`200` + 落库** |
| `"1111000"`（手册示例） | **7** | **`200` + 落库** |

⇒ 原生要求**恰好 7 位**（`DX,DY,DZ,RX,RY,RZ,RW`），而 `BoundaryTransformer` 原先
**结构上**只能产出 **6** 位（`BOUNDARY_FLAGS` 恰好 6 个）⇒ **canonical 少一个自由度**。

本批的落地（`app/**` 的**授权范围 = 1 个文件**）
------------------------------------------------
`app/infrastructure/adapters/midas/transforms.py`：
① `BOUNDARY_FLAGS` **6 → 7**（追加 `rw`，顺序 = Schema 描述 `(DX,DY,DZ,RX,RY,RZ,RW)`）；
② `constraint_string` 文档化「位数 = 传入的自由度个数」（实现本就按 N 拼接）；
③ `constraint_flags` 增 `count`（默认 = `len(BOUNDARY_FLAGS)` = **7**），**不**猜缺失位；
④ `BoundaryTransformer` 的文档串同步。
**调用方显式给 `rw`**（**缺** ⇒ `boundary_flags_incomplete`，**不**给默认值、**不**代填 `"0"`）。
**未**改 canonical 字段表、**未**改 9 Tool Contract、**未**新增依赖、**未**改表。

本文件的判定点
--------------
1. **7 个自由度**：`BOUNDARY_FLAGS` 恰好 7 项、顺序 = Schema 描述、末项 = `rw`。
2. **输出 7 位**：`to_native` 的 `CONSTRAINT` = **7** 位且 = 原生**实测接受**的取值形态。
3. **缺 `rw` ⇒ 显式失败**（`boundary_flags_incomplete`）：**不**给默认值、**不**代填 `"0"`。
4. **解析 7 位**：7 位逐位解析；6 位 ⇒ 第 7 位 `None`（**不**猜成 `False`）。
5. **实测 13 / 13**：接口层写路径**全部** `PASSED`（零残留、未中止、哨兵前后一致）。
6. **取值缺口关闭**：R126 证据包的 `DB.CONS` 由 `value_gap` 移入 `covered`（取值缺口 3 → 2）。
7. **不变量**：`write_path_coverage()` = `0 / 633` · 缺口 `517` = `271` + `246` ·
   分类 `271` = `0` + `51` + `220` · 读路径子桶 `15` = `2` + `7` + `6` ·
   R118 子桶 `71` = `42` + `23` + `6`。
8. **R130（本批**新发现**，如实留缺）**：`ITEMS` 形态端点的**读回**把外层 `ITEMS` 包装体
   当成条目交给 Transformer ⇒ canonical 取值**全 `None`**（**未**修：属 `app/**`、**未**获授权）。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.infrastructure.adapters.midas.errors import MidasValidationError
from app.infrastructure.adapters.midas.live import write_path_coverage
from app.infrastructure.adapters.midas.registry import MidasRegistry
from app.infrastructure.adapters.midas.transforms import (
    BOUNDARY_FLAGS,
    BoundaryTransformer,
    constraint_flags,
    constraint_string,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录。"""

WRITE_EVIDENCE = REPO_ROOT / "registry" / "live" / "interface_path_probe.json"
READ_EVIDENCE = REPO_ROOT / "registry" / "live" / "interface_read_probe.json"
CONSTRAINT_EVIDENCE = REPO_ROOT / "registry" / "live" / "constraint_value_probe.json"
FIELD_GAP = REPO_ROOT / "registry" / "live" / "canonical_field_gap.json"
GAP_EVIDENCE = REPO_ROOT / "registry" / "live" / "interface_mapping_gap.json"
PUT_EDIT_EVIDENCE = REPO_ROOT / "registry" / "live" / "put_edit_probe.json"
PROBE_TOOL = REPO_ROOT / "registry" / "tools" / "probe_interface_paths.py"
CONSTRAINT_TOOL = REPO_ROOT / "registry" / "tools" / "probe_constraint_value.py"
BOUNDARY_TOOL = REPO_ROOT / "registry" / "tools" / "probe_boundary_shape.py"
FIELD_GAP_TOOL = REPO_ROOT / "registry" / "tools" / "check_canonical_field_gap.py"

EXPECTED_FLAGS = ("ux", "uy", "uz", "rx", "ry", "rz", "rw")
"""canonical 的 7 个自由度，顺序 = `DB.CONS` Schema 描述 `(DX,DY,DZ,RX,RY,RZ,RW)`。"""

ACCEPTED_LENGTH = 7
"""原生**实测接受**的 `CONSTRAINT` 长度（
`registry/live/constraint_value_probe.json` 的 `verdict`）。"""

ACCEPTED_CONSTRAINT = "1110000"
"""接口层为探针产出的取值（= 实测 `seven_digits_rw0` 变体；被原生 `200` 接受且落库）。"""

EXPECTED_WRITE_ROWS = 13
EXPECTED_WRITE_COUNTS = {"PASSED": 13}
EXPECTED_WRITE_BY_PATH = {
    "add": {"PASSED": 5},
    "edit": {"PASSED": 2},
    "delete": {"PASSED": 6},
}

EXPECTED_FIELD_GAP = {
    "template_endpoints": 71,
    "with_transformer": 12,
    "without_transformer": 59,
    "field_set_gap": 2,
    "value_gap": 2,
    "no_canonical_model": 59,
    "covered": 8,
}
EXPECTED_GAP_TOTAL = 510
EXPECTED_GAP_NOT_IN_CONTRACT = 264
EXPECTED_GAP_NO_READBACK = 246
EXPECTED_ADOPTION = {
    "adoptable_with_existing_canonical_model": 0,
    "adoptable_with_manual_example": 51,
    "needs_product_decision": 213,
}
EXPECTED_READ_COUNTS = {"PASSED": 2, "PARTIAL": 7, "FAILED": 6}
EXPECTED_PUT_EDIT_COUNTS = {"PASSED": 42, "LEFT_OUT": 23, "FAILED": 6}
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


def _registry() -> Any:
    return MidasRegistry.load(REPO_ROOT / "registry")


def _canonical(**overrides: Any) -> dict[str, Any]:
    """一个**完整**的 7 自由度 canonical 边界（默认全 `False`，只改 `overrides`）。"""
    base: dict[str, Any] = {"node_id": 1, "group_name": ""}
    base.update(dict.fromkeys(BOUNDARY_FLAGS, False))
    base.update(overrides)
    return base


# ===== 1. 7 个自由度（`docs/04` §31 的 Schema 描述逐字）=====


def test_p157_boundary_flags_cover_all_seven_degrees_of_freedom() -> None:
    """门槛：`BOUNDARY_FLAGS` **恰好 7** 项，顺序 = `(DX,DY,DZ,RX,RY,RZ,RW)`，末项 = `rw`。"""
    assert BOUNDARY_FLAGS == EXPECTED_FLAGS, BOUNDARY_FLAGS
    assert len(BOUNDARY_FLAGS) == 7
    # 与 `DB.CONS` 的请求 Schema 描述**逐字**对齐（`registry/schema/common/db/CONS.json`）
    schema = _json(REPO_ROOT / "registry" / "schema" / "common" / "db" / "CONS.json")
    description = str(
        schema["schema"]["CONS"]["properties"]["ITEMS"]["items"]["properties"]["CONSTRAINT"][
            "description"
        ]
    )
    assert description == "(DX,DY,DZ,RX,RY,RZ,RW)", description
    assert len(EXPECTED_FLAGS) == description.count(",") + 1


# ===== 2. 输出恰好 7 位（= 原生实测接受的形态）=====


def test_p157_the_transformer_emits_exactly_seven_digits() -> None:
    """门槛：`to_native` 的 `CONSTRAINT` **恰好 7** 位，且与**实测接受**的取值逐位一致。"""
    transformer = BoundaryTransformer(_registry())
    native = transformer.to_native(_canonical(ux=True, uy=True, uz=True))
    assert set(native) == {"ID", "GROUP_NAME", "CONSTRAINT"}, native
    assert native["CONSTRAINT"] == ACCEPTED_CONSTRAINT, native
    assert len(str(native["CONSTRAINT"])) == ACCEPTED_LENGTH == 7
    # 逐位：`(DX,DY,DZ,RX,RY,RZ,RW)` = `(1,1,1,0,0,0,0)`
    assert str(native["CONSTRAINT"]) == constraint_string(
        True, True, True, False, False, False, False
    )
    # 全 `True` ⇒ 7 个 `1`（不是 6 个）
    all_true = transformer.to_native(_canonical(**dict.fromkeys(BOUNDARY_FLAGS, True)))
    assert all_true["CONSTRAINT"] == "1111111"


def test_p157_the_evidence_verdict_is_the_length_the_interface_layer_emits() -> None:
    """门槛：证据的 `verdict`（被接受的长度）= 接口层产出的长度 = **7**（缺口关闭的判据）。"""
    document = _json(CONSTRAINT_EVIDENCE)
    assert int(document["verdict"]) == ACCEPTED_LENGTH == 7
    accepted = [row for row in document["variants"] if int(row["length"]) == ACCEPTED_LENGTH]
    assert len(accepted) == 2, accepted
    for row in accepted:
        assert row["status"] == "PASSED", row
        assert row["created"] is True, row
    rejected = [row for row in document["variants"] if int(row["length"]) != ACCEPTED_LENGTH]
    assert {int(row["length"]) for row in rejected} == {5, 6}, rejected


# ===== 3. 缺 `rw` ⇒ 显式失败（**不**给默认值、**不**代填 `"0"`）=====


def test_p157_a_missing_rw_is_an_explicit_failure() -> None:
    """门槛：**缺** `rw` ⇒ `STRUCTAI-1200`（`boundary_flags_incomplete`）—— **不**给默认值。

    ⚠️ 这是**方案 B 被否**的落地证据：接口层**不**替调用方补 `"0"`（那是为未建模的自由度
    **臆造取值**）；缺项一律显式失败，由调用方给出**有来源**的取值。
    """
    transformer = BoundaryTransformer(_registry())
    with pytest.raises(MidasValidationError) as failure:
        transformer.to_native({key: value for key, value in _canonical().items() if key != "rw"})
    assert failure.value.code == "STRUCTAI-1200"
    assert failure.value.details["reason"] == "boundary_flags_incomplete"
    assert failure.value.details["flags"] == list(EXPECTED_FLAGS)
    # 其余 6 个自由度**同样**不可省（逐条隔离：缺任意一个都失败）
    for name in BOUNDARY_FLAGS:
        incomplete = {key: value for key, value in _canonical().items() if key != name}
        with pytest.raises(MidasValidationError) as failure:
            transformer.to_native(incomplete)
        assert failure.value.details["reason"] == "boundary_flags_incomplete", name
    # 对照：**给全** 7 个就通过（判定不是「一律拒绝」）
    assert transformer.to_native(_canonical())["CONSTRAINT"] == "0000000"


def test_p157_a_none_valued_flag_is_not_silently_treated_as_false() -> None:
    """门槛：显式传 `None`（= 未知）**不**被当成 `False` ⇒ 仍然显式失败。"""
    transformer = BoundaryTransformer(_registry())
    with pytest.raises(MidasValidationError) as failure:
        transformer.to_native(_canonical(rw=None))
    assert failure.value.details["reason"] == "boundary_flags_incomplete"


# ===== 4. 解析 7 位（**不**猜缺失位）=====


def test_p157_constraint_flags_parses_seven_and_never_guesses() -> None:
    """门槛：7 位逐位解析；6 位 ⇒ 第 7 位 `None`（**不**代填 `False`）；非法字符 ⇒ `None`。"""
    assert constraint_flags("1110000") == (True, True, True, False, False, False, False)
    assert constraint_flags("1111000") == (True, True, True, True, False, False, False)
    assert len(constraint_flags("1110000")) == 7
    # 6 位（P156 时接口层的产出）⇒ 第 7 位 `None`（**不**猜）
    six = constraint_flags("111000")
    assert len(six) == 7
    assert six[:6] == (True, True, True, False, False, False)
    assert six[6] is None
    # 非法字符 ⇒ `None`（该位），**不**当 0
    assert constraint_flags("11x0000")[2] is None
    # 空串 ⇒ 全 `None`
    assert constraint_flags("") == tuple([None] * 7)
    # `count` 可显式收窄（**不**改变默认 = 7）
    assert len(constraint_flags("1110000", count=6)) == 6
    assert len(constraint_flags("1110000")) == 7


def test_p157_from_native_round_trips_seven_digits() -> None:
    """门槛：`from_native` 对 7 位**逐位**回填 7 个 canonical 字段（含 `rw`）。"""
    transformer = BoundaryTransformer(_registry())
    canonical = transformer.from_native({"ID": 4, "GROUP_NAME": "G", "CONSTRAINT": "1111000"})
    assert canonical["node_id"] == 4
    assert canonical["group_name"] == "G"
    assert tuple(canonical[name] for name in BOUNDARY_FLAGS) == (
        True,
        True,
        True,
        True,
        False,
        False,
        False,
    )
    assert canonical["rw"] is False
    # 6 位（旧产出）⇒ `rw` = `None`，其余 6 位照常（**不**猜）
    legacy = transformer.from_native({"ID": 4, "CONSTRAINT": "111000"})
    assert legacy["rw"] is None
    assert tuple(legacy[name] for name in BOUNDARY_FLAGS[:6]) == (
        True,
        True,
        True,
        False,
        False,
        False,
    )


# ===== 5. 接口层写路径实测 **13 / 13** =====


def test_p157_the_write_path_is_thirteen_of_thirteen() -> None:
    """门槛：**13** 条 = **13** `PASSED`；零残留、未中止、哨兵前后一致（有实测依据）。"""
    document = _json(WRITE_EVIDENCE)
    assert len(document["paths"]) == EXPECTED_WRITE_ROWS
    assert document["counts"] == EXPECTED_WRITE_COUNTS
    assert document["by_path"] == EXPECTED_WRITE_BY_PATH
    assert document["residue"] == {}
    assert document["aborted"] == ""
    assert document["sentinel_before"] == document["sentinel_after"]
    assert {str(row["status"]) for row in document["paths"]} == {"PASSED"}
    # 三条路径各有 `PASSED`（任务 1 的硬要求）
    assert {str(row["path"]) for row in document["paths"]} == {"add", "edit", "delete"}


def test_p157_the_boundary_rows_are_green_with_a_seven_digit_constraint() -> None:
    """门槛：`DB.CONS` 的添加 / 删除**都** `PASSED`，body 的 `CONSTRAINT` **恰好 7** 位。"""
    document = _json(WRITE_EVIDENCE)
    rows = [row for row in document["paths"] if str(row["endpoint"]) == "DB.CONS"]
    assert {str(row["path"]) for row in rows} == {"add", "delete"}, rows
    for row in rows:
        assert row["status"] == "PASSED", row
        bodies = [
            item["body"]
            for item in row["requests"]
            if item["method"] == "POST" and str(item["path"]).endswith("/DB/CONS")
        ]
        assert bodies, row["requests"]
        outer = bodies[0]["Assign"]
        assert all(str(key).isdigit() for key in outer), bodies[0]
        entry = outer[next(iter(outer))]["ITEMS"][0]
        assert len(str(entry["CONSTRAINT"])) == ACCEPTED_LENGTH, entry
        assert str(entry["CONSTRAINT"]) == ACCEPTED_CONSTRAINT, entry
        assert not [item for item in row["requests"] if int(item["status"]) >= 400], row["requests"]
    add = next(row for row in rows if row["path"] == "add")
    assert add["readback"]["present"] is True, add["readback"]
    assert (add.get("cleanup") or {}).get("gone") is True, add.get("cleanup")


def test_p157_the_probe_gives_rw_explicitly() -> None:
    """门槛：**调用方**（数据侧探针）**显式**给出 `rw` —— **不**依赖 Transformer 的默认值。"""
    probe = _load(PROBE_TOOL, "structai_probe_interface_paths_p157")
    parameters = probe._boundary_parameters("1", nodes=["1"])  # noqa: SLF001 - 判定点
    boundary = parameters["boundaries"][0]
    assert boundary["rw"] is False, boundary
    assert {name for name in EXPECTED_FLAGS} <= set(boundary), boundary


# ===== 6. R126 证据包：`DB.CONS` 的取值缺口**关闭**（有实测依据）=====


def test_p157_the_db_cons_value_gap_is_closed() -> None:
    """门槛：`DB.CONS` 由 `value_gap` 移入 `covered`（取值缺口 **3 → 2**、已覆盖 **5 → 6**）。"""
    document = _json(FIELD_GAP)
    for key, expected in EXPECTED_FIELD_GAP.items():
        assert int(document["summary"][key]) == expected, (key, document["summary"][key])
    assert tuple(document["buckets"]["value_gap"]) == ("DB.ELEM", "DB.MATL")
    assert "DB.CONS" in document["buckets"]["covered"]
    assert "DB.CONS" not in document["value_gaps"]
    index = {str(row["endpoint"]): row for row in document["endpoints"]}
    assert index["DB.CONS"]["gap_class"] == "covered"
    assert index["DB.CONS"]["missing_in_canonical"] == []
    # ⚠️ 字段集缺口**未**被本批触及（仍 `DB.BMLD` / `DB.PRES`）
    assert tuple(document["buckets"]["field_set_gap"]) == ("DB.BMLD", "DB.PRES")


# ===== 7. 不变量（本批**不得**放宽既有判定）=====


def test_p157_the_invariants_are_untouched() -> None:
    """门槛：数据侧分母 / 缺口 / 分类 / 读路径子桶 / R118 子桶**一行未变**。"""
    registry = _registry()
    coverage = write_path_coverage(registry, [])
    assert coverage.ratio == f"0 / {EXPECTED_WRITE_PATH_TOTAL}"
    assert coverage.model_write_ratio == f"0 / {EXPECTED_MODEL_WRITE_TOTAL}"
    gap = _json(GAP_EVIDENCE)
    assert int(gap["gap_total"]) == EXPECTED_GAP_TOTAL
    assert len(gap["gap_three_step"]) == EXPECTED_GAP_NOT_IN_CONTRACT
    assert len(gap["gap_no_readback"]) == EXPECTED_GAP_NO_READBACK
    read_document = _json(READ_EVIDENCE)
    assert read_document["counts"] == EXPECTED_READ_COUNTS
    assert len(read_document["paths"]) == sum(EXPECTED_READ_COUNTS.values()) == 15
    put_edit = _json(PUT_EDIT_EVIDENCE)
    assert put_edit["counts"] == EXPECTED_PUT_EDIT_COUNTS
    assert sum(EXPECTED_PUT_EDIT_COUNTS.values()) == 71
    classification = _json(
        REPO_ROOT / "registry" / "live" / "interface_mapping_classification.json"
    )
    assert {
        key: int(classification["adoption_counts"][key]) for key in EXPECTED_ADOPTION
    } == EXPECTED_ADOPTION
    assert int(classification["gap_total"]) == EXPECTED_GAP_TOTAL
    assert int(classification["gap_not_in_contract"]) == EXPECTED_GAP_NOT_IN_CONTRACT
    assert int(classification["gap_no_readback"]) == EXPECTED_GAP_NO_READBACK


def test_p157_the_evidence_never_carries_credentials() -> None:
    """门槛（`docs/07` §14.3）：证据里**没有**凭据形态。"""
    for path in (WRITE_EVIDENCE, READ_EVIDENCE, CONSTRAINT_EVIDENCE, FIELD_GAP):
        raw = path.read_text(encoding="utf-8")
        for marker in ("MAPI-Key", "MAPI_KEY", "mapi-key", "password", "secret"):
            assert marker not in raw, (path.name, marker)


def test_p157_the_check_modes_agree_offline() -> None:
    """门槛：四个工具的 `--check` 离线跑通（退出码 0）—— CI 的复算入口。"""
    for tool, marker in (
        (PROBE_TOOL, "接口层证据自洽"),
        (CONSTRAINT_TOOL, "取值证据自洽"),
        (BOUNDARY_TOOL, "形状证据自洽"),
        (FIELD_GAP_TOOL, "证据包自洽"),
    ):
        result = subprocess.run(
            [sys.executable, str(tool), "--check"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0, tool.name + result.stdout + result.stderr
        assert marker in result.stdout, tool.name + result.stdout


# ===== 8. R130：`ITEMS` 形态端点的**读回**退化（本批**新发现**，**未**修）=====


def test_p158_r130_items_style_readback_is_unwrapped_to_the_leaf() -> None:
    """门槛（**R130 ✅ 已闭环**）：`ITEMS` 形态端点读回时，交给 Transformer 的是**叶子**。

    ⚠️ **P157 定位、P158 修复**：`MidasAdapter._read` 用 `_items_of(read_root 块)` 解包；
    对**编号键映射**里的 `{"1": {"ITEMS": [<叶子>]}}`，原先返回 `("1", {"ITEMS": [<叶子>]})`
    —— 即**包装体**，**不是**叶子 ⇒ `BoundaryTransformer.from_native` 拿不到
    `ID` / `GROUP_NAME` / `CONSTRAINT` ⇒ 7 个自由度**全 `None`**（只有由**键**补的 `id` 有值）。
    用户授权后（P158）改为**逐元素展开**（`adapter._explode_items`）。
    **真机实测**：`MODEL.BOUNDARY.QUERY` 读回 `{"id": "1", "node_id": 1, "group_name": "",
    "ux": true, …, "rw": false}` —— 7 个自由度全在。
    """
    from app.infrastructure.adapters.midas.adapter import _items_of  # noqa: PLC0415

    payload = {"1": {"ITEMS": [{"CONSTRAINT": ACCEPTED_CONSTRAINT, "GROUP_NAME": "", "ID": 1}]}}
    items = _items_of(payload)
    assert items == [("1", {"CONSTRAINT": ACCEPTED_CONSTRAINT, "GROUP_NAME": "", "ID": 1})]
    transformer = BoundaryTransformer(_registry())
    canonical = transformer.from_native(items[0][1])
    assert canonical["node_id"] == 1, canonical
    assert canonical["group_name"] == "", canonical
    assert all(canonical[name] is not None for name in EXPECTED_FLAGS), canonical
    # 对照：叶子**直接**作为值（非 `ITEMS` 形态，如 `DB.NODE`）⇒ 逐位解析正常（**不变**）
    leaf = transformer.from_native({"ID": 1, "GROUP_NAME": "", "CONSTRAINT": ACCEPTED_CONSTRAINT})
    assert leaf["node_id"] == 1
    assert all(leaf[name] is not None for name in EXPECTED_FLAGS), leaf
    # ⚠️ 写路径证据的读回**已随修复刷新**（`observed` 不再只有 `id` 有值）
    document = _json(WRITE_EVIDENCE)
    add = next(
        row
        for row in document["paths"]
        if row["path"] == "add" and str(row["endpoint"]) == "DB.CONS"
    )
    observed = add["readback"]["observed"]
    assert observed["id"] == "1", observed
    assert observed["node_id"] == 1, observed
    assert all(observed[name] is not None for name in EXPECTED_FLAGS), observed


@pytest.mark.skipif(
    not CONSTRAINT_EVIDENCE.is_file(),
    reason="缺 `CONSTRAINT` 取值证据",
)
def test_p157_the_landing_matches_the_adjudicated_option_a() -> None:
    """门槛（**裁决的钉子**）：落地 = **D2 的选项 A**（扩 canonical 加 `rw`），**不**是 B。

    ⚠️ 方案 B（固定补 `"0"`）的**取值**已被实测接受（技术上可行），但争点是**纪律**
    （是否为未建模的自由度代填取值）⇒ 裁决选 **A**。本用例证明接口层**没有**代填：
    缺 `rw` 时报错，而**不是**产出 `"1110000"`。
    """
    transformer = BoundaryTransformer(_registry())
    with pytest.raises(MidasValidationError):
        transformer.to_native({key: value for key, value in _canonical().items() if key != "rw"})
    assert "rw" in [field.canonical for field in transformer.fields] or "rw" in BOUNDARY_FLAGS
    document = _json(CONSTRAINT_EVIDENCE)
    assert int(document["verdict"]) == 7
