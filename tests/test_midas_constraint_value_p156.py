"""P156 / **D2 的更正**：`DB.CONS` 的 `CONSTRAINT` **必须是 7 位**（位数**是**成因）。

背景（一次**如实更正**）
------------------------
P154 做了「位数 A/B」并据以**收口 D2**（结论：**位数不是成因**）。⚠️ **该结论是错的**：
那次 A/B 的**三个变体都用了当时（未修）的请求体形状** `{"Assign": {"ITEMS": […]}}` ——
而该形状**无论位数都被 `400` 拒** ⇒ 位数这个变量被**形状混淆**（confounded）。

P155 修好**形状**（外层**编号键**）后，P156 重跑接口层：仍 `400`，但原生文案从
`Wrong Field`（**形状级**）变成 **`[错误] 约束条件输入有错误。`**（**取值级**）
⇒ 用**已修的形状**重测位数，结论**反转**（证据 = `registry/live/constraint_value_probe.json`）：

| `CONSTRAINT` | 长度 | 原生 |
| --- | --- | --- |
| `"11100"` | 5 | `400` |
| `"111000"`（**接口层当前产出**） | 6 | `400` `[错误] 约束条件输入有错误。` |
| `"1110000"`（六自由度 + `RW=0`） | 7 | **`200` + 落库** |
| `"1111000"`（**手册示例**） | 7 | **`200` + 落库** |

⇒ 原生要求 **恰好 7 位**（`DX,DY,DZ,RX,RY,RZ,RW`）；`RX` 取值无关（0 / 1 都可）。
而 `BoundaryTransformer` 的 `CONSTRAINT` 由 **六个**自由度合成（`transforms.py` §31：`RW`
**明确不臆造**）⇒ 接口层**结构上**只能产出 6 位 ⇒ **必须**由契约侧裁决（D2 **重开**）。

本文件的判定点
--------------
1. **位数是成因**：证据里**只有 7 位**被接受（5 / 6 位全 `400`）。
2. **形状已修**：4 个变体**全部**用编号键控形状（`{"Assign": {"<节点编号>": {"ITEMS": […]}}}`）。
3. **接口层当前只能产出 6 位**（`BoundaryTransformer` 的字段表里**没有** `rw`）⇒ 这是
   **契约缺口**，**不**在端点 / 护栏 / 形状。
4. **不变量**：`write_path_coverage()` = `0 / 633` · 缺口 `517` = `271` + `246` · R118 子桶未动。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from app.infrastructure.adapters.midas.live import write_path_coverage
from app.infrastructure.adapters.midas.registry import MidasRegistry
from app.infrastructure.adapters.midas.transforms import (
    BOUNDARY_FLAGS,
    BoundaryTransformer,
    constraint_string,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录。"""

CONSTRAINT_EVIDENCE = REPO_ROOT / "registry" / "live" / "constraint_value_probe.json"
SHAPE_EVIDENCE = REPO_ROOT / "registry" / "live" / "boundary_shape_probe.json"
WRITE_EVIDENCE = REPO_ROOT / "registry" / "live" / "interface_path_probe.json"
GAP_EVIDENCE = REPO_ROOT / "registry" / "live" / "interface_mapping_gap.json"
CONSTRAINT_TOOL = REPO_ROOT / "registry" / "tools" / "probe_constraint_value.py"

EXPECTED_VARIANTS = (
    "six_digits",
    "five_digits_control",
    "seven_digits_rw0",
    "seven_digits_rx1",
)
ACCEPTED_LENGTH = 7
"""被原生接受的 `CONSTRAINT` 长度（**恰好 7**：`DX,DY,DZ,RX,RY,RZ,RW`）。"""

EXPECTED_COUNTS = {"PASSED": 2, "FAILED": 2}
INTERFACE_LAYER_LENGTH = 6
"""接口层当前产出的长度（`BoundaryTransformer` 只覆盖**六个**自由度）。"""

EXPECTED_WRITE_PATH_TOTAL = 633
EXPECTED_MODEL_WRITE_TOTAL = 434
EXPECTED_GAP_TOTAL = 517
EXPECTED_GAP_NOT_IN_CONTRACT = 271
EXPECTED_GAP_NO_READBACK = 246


def _load(path: Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# ===== 1. 位数是成因（D2 的更正）=====


def test_p156_only_seven_digits_are_accepted() -> None:
    """门槛：证据里**只有 7 位**被接受（5 位 / 6 位全 `400`）⇒ **位数是成因**。"""
    document = _json(CONSTRAINT_EVIDENCE)
    assert document["criterion_version"] == 1
    assert tuple(str(row["name"]) for row in document["variants"]) == EXPECTED_VARIANTS
    assert document["counts"] == EXPECTED_COUNTS
    assert int(document["verdict"]) == ACCEPTED_LENGTH
    for row in document["variants"]:
        accepted = int(row["length"]) == ACCEPTED_LENGTH
        assert (str(row["status"]) == "PASSED") is accepted, row
        assert bool(row["created"]) is accepted, row
        if accepted:
            assert row["readback_keys"] == ["CONSTRAINT", "GROUP_NAME", "ID"], row
        else:
            assert int(row["http"]) == 400, row
            assert str(row.get("native_error") or ""), row
    # **接口层当前产出的 6 位**：原生文案是**取值级**的「约束条件输入有错误」
    six = next(row for row in document["variants"] if row["name"] == "six_digits")
    assert "约束条件输入有错误" in str(six["native_error"]), six
    # 5 位（更短）是**另一种**原生拒绝文案（`Unknown Error`）⇒ 如实分别记录，**不**强行统一
    five = next(row for row in document["variants"] if row["name"] == "five_digits_control")
    assert "Unknown Error" in str(five["native_error"]), five


def test_p156_every_variant_uses_the_fixed_node_keyed_shape() -> None:
    """门槛：**形状**已是修好的编号键控形态（位数与形状**不再混淆**）。"""
    document = _json(CONSTRAINT_EVIDENCE)
    for row in document["variants"]:
        assert str(row["outer_key"]).isdigit(), row
        assert str(row["outer_key"]) != "ITEMS", row
    for item in document["requests"]:
        body = item.get("body")
        if not isinstance(body, dict) or "Assign" not in body:
            continue
        assert list(body["Assign"]) != ["ITEMS"], item
        assert all(str(key).isdigit() for key in body["Assign"]), item


def test_p156_the_probe_is_bounded_and_leaves_no_residue() -> None:
    """门槛：**有界**（请求数 ≤ 上限）+ 零残留 + 清理逐条确认 + 哨兵前后一致。"""
    tool = _load(CONSTRAINT_TOOL, "structai_probe_constraint_value_p156")
    document = _json(CONSTRAINT_EVIDENCE)
    assert len(document["requests"]) <= tool.MAX_REQUESTS, len(document["requests"])
    assert document["aborted"] == ""
    assert document["residue"] == {}
    assert document["sentinel_before"] == document["sentinel_after"]
    for item in document["cleanup"]:
        assert item["gone"] is True, item


# ===== 2. 接口层**结构上**只能产出 6 位（契约缺口，**不**在形状）=====


def test_p156_the_interface_layer_can_only_produce_six_digits() -> None:
    """门槛：`BoundaryTransformer` 的字段表**没有** `rw` ⇒ 合成的 `CONSTRAINT` 只有 **6** 位。"""
    registry = MidasRegistry.load(REPO_ROOT / "registry")
    transformer = BoundaryTransformer(registry)
    canonical = dict.fromkeys(BOUNDARY_FLAGS, True)
    assert len(BOUNDARY_FLAGS) == 6, BOUNDARY_FLAGS
    assert "rw" not in [field.canonical for field in transformer.fields]
    native = transformer.to_native({"node_id": 1, **canonical})
    assert len(str(native["CONSTRAINT"])) == INTERFACE_LAYER_LENGTH, native
    assert str(native["CONSTRAINT"]) == constraint_string(True, True, True, True, True, True)
    # 第 7 位（`RW`）**无从表达** ⇒ 这是**契约缺口**（D2 重开），**不**是形状 / 端点 / 护栏问题
    assert len(str(native["CONSTRAINT"])) < ACCEPTED_LENGTH


def test_p156_the_write_evidence_shows_the_value_level_failure() -> None:
    """门槛：接口层 `DB.CONS` 的原生文案已**下沉到取值级**（不再是形状级 `Wrong Field`）。"""
    document = _json(WRITE_EVIDENCE)
    failures = [row for row in document["paths"] if row["status"] == "FAILED"]
    assert {str(row["endpoint"]) for row in failures} == {"DB.CONS"}
    texts = {
        str(item.get("native_error"))
        for row in failures
        for item in row["requests"]
        if int(item["status"]) >= 400
    }
    assert any("约束条件输入有错误" in text for text in texts), texts
    assert not any("Wrong Field" in text for text in texts), texts


def test_p156_the_shape_fix_is_verified_by_the_shape_evidence() -> None:
    """门槛（P155 的修复**已被实测确认**）：形状 A/B 里**只有**编号键控形态被接受。"""
    document = _json(SHAPE_EVIDENCE)
    index = {str(row["name"]): row for row in document["variants"]}
    assert index["assign_items"]["status"] == "FAILED", index["assign_items"]
    assert index["assign_items"]["http"] == 400, index["assign_items"]
    for name in ("assign_node_keyed_items", "assign_node_keyed_items_no_id"):
        assert index[name]["status"] == "PASSED", index[name]
        assert index[name]["created"] is True, index[name]


# ===== 3. 不变量 =====


def test_p156_the_invariants_are_untouched() -> None:
    """门槛：写路径分母 / 缺口**一行未变**（本批只新增证据与判定）。"""
    registry = MidasRegistry.load(REPO_ROOT / "registry")
    coverage = write_path_coverage(registry, [])
    assert coverage.ratio == f"0 / {EXPECTED_WRITE_PATH_TOTAL}"
    assert coverage.model_write_ratio == f"0 / {EXPECTED_MODEL_WRITE_TOTAL}"
    gap = _json(GAP_EVIDENCE)
    assert int(gap["gap_total"]) == EXPECTED_GAP_TOTAL
    assert len(gap["gap_three_step"]) == EXPECTED_GAP_NOT_IN_CONTRACT
    assert len(gap["gap_no_readback"]) == EXPECTED_GAP_NO_READBACK


def test_p156_the_evidence_never_carries_credentials() -> None:
    """门槛（`docs/07` §14.3）：证据里**没有**凭据形态。"""
    for path in (CONSTRAINT_EVIDENCE, SHAPE_EVIDENCE, WRITE_EVIDENCE):
        raw = path.read_text(encoding="utf-8")
        for marker in ("MAPI-Key", "MAPI_KEY", "mapi-key", "password", "secret"):
            assert marker not in raw, (path.name, marker)


def test_p156_the_check_mode_agrees_offline() -> None:
    """门槛：`probe_constraint_value --check` 离线跑通（退出码 0）。"""
    import subprocess  # noqa: PLC0415
    import sys  # noqa: PLC0415

    result = subprocess.run(
        [sys.executable, str(CONSTRAINT_TOOL), "--check"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "取值证据自洽" in result.stdout


@pytest.mark.skipif(
    not (CONSTRAINT_EVIDENCE.is_file()),
    reason="缺 `CONSTRAINT` 取值证据",
)
def test_p156_the_verdict_is_seven_not_six() -> None:
    """门槛（**D2 更正的钉子**）：结论是 **7**，而**不是** P154 声称的「位数无关」。"""
    document = _json(CONSTRAINT_EVIDENCE)
    assert int(document["verdict"]) == ACCEPTED_LENGTH == 7
    assert INTERFACE_LAYER_LENGTH == 6
    assert ACCEPTED_LENGTH != INTERFACE_LAYER_LENGTH
