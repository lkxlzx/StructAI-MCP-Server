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

⚠️ **P157 更新（D2 = A 已落地）**
--------------------------------
用户裁决 **D2 = A**（`docs/reports/P0_裁决清单_v1.0.md` §7）⇒ P157 给 `BoundaryTransformer`
加第 **7** 个自由度 `rw`（`BOUNDARY_FLAGS` **7** 项、`CONSTRAINT` 输出 **7** 位、
`constraint_flags` 解析 **7** 位；调用方**显式**给 `rw`，**缺** ⇒ `boundary_flags_incomplete`，
**不**给默认值、**不**用方案 B 补 `"0"`）。
⇒ 上表第 3 条**已关闭**：接口层现在产出 **7** 位（`INTERFACE_LAYER_LENGTH = 7`），
实测 `DB.CONS` 的添加 / 删除**都** `PASSED`（`registry/live/interface_path_probe.json`）。
本文件的**历史证据**（4 变体、被接受长度 = 7、5 / 6 位被拒）**原样保留**（判定**未**放宽）。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from app.infrastructure.adapters.midas.errors import MidasValidationError
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
INTERFACE_LAYER_LENGTH = 7
"""接口层**当前**产出的长度（⚠️ **P157 / D2 = A 落地**：`BoundaryTransformer` 覆盖**七**个自由度）。

P156 时该值是 **6**（`BOUNDARY_FLAGS` 恰好 6 个、`rw` **不**臆造）⇒ 与原生要求的 **7** 位
**不一致** ⇒ 接口层**结构上**发不出可被接受的取值（= D2 的契约缺口）。
**P157 落地 D2 = A** 后该值 = **7** = `ACCEPTED_LENGTH` ⇒ 缺口关闭（有实测依据：
`registry/live/interface_path_probe.json` 的 `DB.CONS` 添加 / 删除**都** `PASSED`）。
"""

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


def test_p156_the_interface_layer_now_produces_seven_digits() -> None:
    """门槛（⚠️ **P157 / D2 = A 落地**）：`BoundaryTransformer` 的 `CONSTRAINT` = **7** 位。

    P156 时此处断言「**没有** `rw` ⇒ 只能产出 **6** 位」（= 契约缺口）。**D2 = A 落地**后
    该断言**不再成立** ⇒ 改为**更强**的判定：`BOUNDARY_FLAGS` **恰好 7** 个、第 7 个是 `rw`、
    合成的 `CONSTRAINT` **恰好 7** 位且**等于**原生接受的长度；**缺 `rw`** ⇒ 显式报错。
    """
    registry = MidasRegistry.load(REPO_ROOT / "registry")
    transformer = BoundaryTransformer(registry)
    canonical = dict.fromkeys(BOUNDARY_FLAGS, True)
    assert len(BOUNDARY_FLAGS) == 7, BOUNDARY_FLAGS
    assert BOUNDARY_FLAGS[-1] == "rw", BOUNDARY_FLAGS
    native = transformer.to_native({"node_id": 1, **canonical})
    assert len(str(native["CONSTRAINT"])) == INTERFACE_LAYER_LENGTH == 7, native
    assert str(native["CONSTRAINT"]) == constraint_string(*([True] * 7))
    assert len(str(native["CONSTRAINT"])) == ACCEPTED_LENGTH
    # ⚠️ **不**给默认值、**不**代填 `"0"`（方案 B 被否）：缺 `rw` ⇒ 显式报错
    incomplete = {key: value for key, value in canonical.items() if key != "rw"}
    with pytest.raises(MidasValidationError) as failure:
        transformer.to_native({"node_id": 1, **incomplete})
    assert failure.value.details["reason"] == "boundary_flags_incomplete"
    assert failure.value.details["flags"] == list(BOUNDARY_FLAGS)
    # 读回：7 位逐位解析；6 位（旧接口层产出）⇒ 第 7 位 `None`（**不**猜成 `False`）
    seven = transformer.from_native({"ID": 1, "CONSTRAINT": "1110000"})
    assert seven["rw"] is False
    assert all(seven[name] is not None for name in BOUNDARY_FLAGS)
    six = transformer.from_native({"ID": 1, "CONSTRAINT": "111000"})
    assert six["rw"] is None, six


def test_p156_the_write_evidence_shows_the_value_level_failure_is_closed() -> None:
    """门槛（⚠️ **P157 / D2 = A 落地**）：接口层 `DB.CONS` 的**取值级**拒绝**已关闭**。

    P156 时此处断言「`DB.CONS` 仍 `FAILED` 且原生文案是 `约束条件输入有错误`」。
    落地后该行 `PASSED` ⇒ 改为**更强**的判定：**没有**任何 `FAILED` 行、**没有**任何拒绝文案。
    """
    document = _json(WRITE_EVIDENCE)
    failures = [row for row in document["paths"] if row["status"] == "FAILED"]
    assert failures == [], failures
    texts = {
        str(item.get("native_error"))
        for row in document["paths"]
        for item in row["requests"]
        if int(item["status"]) >= 400
    }
    assert texts == set(), texts
    assert not any("约束条件输入有错误" in text for text in texts), texts
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
    """门槛（**D2 更正的钉子**）：结论是 **7**，而**不是** P154 声称的「位数无关」。

    ⚠️ **P157**：接口层现在**也**是 **7**（D2 = A 落地）⇒ 本用例改为断言
    「被接受的长度 = 接口层产出的长度 = **7**」（P156 时两者是 `7 ≠ 6`）。
    """
    document = _json(CONSTRAINT_EVIDENCE)
    assert int(document["verdict"]) == ACCEPTED_LENGTH == 7
    assert INTERFACE_LAYER_LENGTH == 7
    assert ACCEPTED_LENGTH == INTERFACE_LAYER_LENGTH
