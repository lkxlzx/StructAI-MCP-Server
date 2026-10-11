"""P150 / **R118** —— 写路径「编辑（PUT）」的判据（`registry/tools/probe_put_edits.py`）。

背景
----
L5 三步链只覆盖「**创建** → 读回 → 按路径 key **删除**」（`docs/07` §16 R4 / R14），
**PUT（编辑）没有判据**。本文件把 R118 的判据与证据钉成**可执行**的：

1. **目标集逐条可复算**：**71** 个「有数据侧模板 ∧ GEN NX 有 `PUT` ∧ 有 `DELETE` / `GET` /
   `read_root` ∧ 已启用」的端点；其中**零前置链 56** 个本批可探、**15** 个带前置链如实留缺
   （`prerequisite_chain_out_of_scope`；前置链与 L5 同一机制，本批不重复实现）。
2. **证据诚实**：**56** 行；`verdict` = **37** `PASSED` + **14** `LEFT_OUT` + **5** `FAILED`；
   `aborted` 为空；`criterion_version` = **3**；实例 = `gen-local` / `GEN_NX` / `2026-10-11`。
3. **侦察问题①（PUT 的 body 形状）**：**37 / 37** `PASSED` 都用 `assign_keyed_item`
   （`{"Assign": {"<自建编号>": <条目>}}`，**与 POST 同一形状**）⇒ 记录 `put_shape`。
4. **侦察问题②（是否要求记录已存在）**：**37 / 37** `PASSED` 的 `requires_existing_record`
   都是 **`False`** —— 记录删除后对**同一编号**再发一次同一 `PUT`，记录**重新出现**
   ⇒ **`PUT` 是 upsert（不要求记录已存在）**。⚠️ 这与 **R116**（无 `DELETE` 的端点上 `PUT`
   会留下**不可删**的记录）**互相印证**。
5. **改动逐条机械可复算**：`edit` = `{path, from, to, why}`，由 `editable_change()`
   （`boolean` 翻面 / 无 `enum` 的 `number`·`integer` `+1`，按 body 声明顺序取第一个）**唯一**决定。
6. **`FAILED` 逐条**：**4** 个 `put_rejected:400`（`DB.IEHC` / `DB.MLFC` / `DB.SDVI` / `DB.THIK`
   —— 三种形状**全部**被拒，**不**放宽）+ **1** 个 `delete_failed`
   （`DESIGN.RC.KDS-41-20-2022.DCTL`）。
7. **残留如实披露（**不**声称零残留）**：`DELETE` 在本 build 上会**返回 `200` 并回显被删记录**
   却**不真正删除** ⇒ 判据以「再读确认不在」为准；`DESIGN.*` 别名路由（`DESIGN.RC.DRC` /
   `DESIGN.RC.KDS-41-20-2022.DCTL` / `DESIGN.STEEL.DSTL`）实测**删不掉**
   （已按同表 `DB.*` 路由清理），
   `/DESIGN/SRC/AIK-SRC2K/DSRC` **无** `DB.*` 别名、**删不掉** ⇒ 记进 `residue` 并由
   `allowed_residue` 披露；`residue ⊄ allowed_residue` ⇒ 退出码 1。
8. **与 R107 分桶**：本桶**不**并入 L5 三步链的覆盖率分子；**数据侧一行未改**
   （`write_templates.json` / 端点 YAML 相对 `HEAD` 一字未改）。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录。"""

TOOL_PATH = REPO_ROOT / "registry" / "tools" / "probe_put_edits.py"
"""R118 的复算工具（`--probe` 有界侦察 / `--check` / `--summary`）。"""

CHECK_TOOL_PATH = REPO_ROOT / "registry" / "tools" / "check_write_templates.py"
"""条目形状的**唯一**判定点（探针与 `--check` 同源）。"""

EVIDENCE_PATH = REPO_ROOT / "registry" / "live" / "put_edit_probe.json"
"""R118 的证据（56 行；**不含**凭据、**不含**响应体原文）。"""

MANIFEST_PATH = REPO_ROOT / "registry" / "manifest.json"
TEMPLATES_PATH = REPO_ROOT / "registry" / "live" / "write_templates.json"

INSTANCE_ALIAS = "gen-local"
INSTANCE_PRODUCT = "GEN_NX"
PROBED_AT = "2026-10-11"
CRITERION_VERSION = 3

EXPECTED_TARGETS = 71
EXPECTED_PROBEABLE = 56
EXPECTED_PREREQUISITE_CHAIN = 15
EXPECTED_COUNTS = {"PASSED": 37, "LEFT_OUT": 14, "FAILED": 5}

EXPECTED_PASSED = (
    "DB.BNGR",
    "DB.CCFC",
    "DB.CUTL",
    "DB.DCTL",
    "DB.EIGV",
    "DB.EPMT",
    "DB.ETFC",
    "DB.FIMP",
    "DB.GRUP",
    "DB.GSTP",
    "DB.HHCT",
    "DB.HSFC",
    "DB.MATL",
    "DB.MVCTBS",
    "DB.MVCTCH",
    "DB.MVCTID",
    "DB.MVCTTR",
    "DB.MVHLTR",
    "DB.NPLN",
    "DB.PNLD",
    "DB.POGD",
    "DB.POSL",
    "DB.POSP",
    "DB.SDHY",
    "DB.SDIS",
    "DB.SDST",
    "DB.SDVE",
    "DB.SECT",
    "DB.SMCT",
    "DB.SPFC",
    "DB.STOR",
    "DB.TDME",
    "DB.TDMT",
    "DB.THFC",
    "DESIGN.RC.KDS-41-20-2022.DCO",
    "DESIGN.SRC.AIK-SRC2K.DCO",
    "DESIGN.STEEL.KDS-41-30-2022.DCO",
)

EXPECTED_LEFT_OUT = (
    "DB.DCON",
    "DB.DSTL",
    "DB.LDGR",
    "DB.MVCD",
    "DB.PJCF",
    "DB.PSLT",
    "DB.STLD",
    "DB.TDGR",
    "DB.VSEC",
    "DB.WMAK",
    "DESIGN.RC.DRC",
    "DESIGN.RC.KDS-41-20-2022.WMAK",
    "DESIGN.SRC.AIK-SRC2K.DSRC",
    "DESIGN.STEEL.DSTL",
)

EXPECTED_FAILED_PUT_REJECTED = ("DB.IEHC", "DB.MLFC", "DB.SDVI", "DB.THIK")
"""三种形状**全部**被 `400` 拒绝（**不**放宽）。"""

EXPECTED_FAILED_DELETE = ("DESIGN.RC.KDS-41-20-2022.DCTL",)
"""`PUT` 成功、读回确认，但**删不掉**（`DELETE` 返回 `200` 而记录仍在）。"""

EXPECTED_DELETE_UNCONFIRMED = (
    "DESIGN.RC.DRC",
    "DESIGN.RC.KDS-41-20-2022.DCTL",
    "DESIGN.STEEL.DSTL",
)
"""`DELETE` **未**确认生效的三个 `DESIGN.*` 别名端点（同表 `DB.*` 路由可清理）。"""

EXPECTED_RESIDUE = {"DESIGN.SRC.AIK-SRC2K.DSRC": ["1"]}
"""**如实披露**的残留：无 `DB.*` 别名、实测**删不掉**（成因需 MIDAS 侧）。"""

EXPECTED_PUT_SHAPE = "assign_keyed_item"


def _load(path: Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tool() -> Any:
    return _load(TOOL_PATH, "structai_probe_put_edits_p150")


def _check_tool() -> Any:
    return _load(CHECK_TOOL_PATH, "structai_check_write_templates_p150r118")


def _evidence() -> dict[str, Any]:
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def _manifest() -> dict[str, dict[str, Any]]:
    document = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {str(entry["key"]): entry for entry in document["endpoints"]}


def _unchanged_since_head(path: Path) -> bool:
    result = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", str(path)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


# ===== 1. 目标集 =====


def test_p150r118_the_target_set_is_recomputed_by_measurement() -> None:
    """门槛（判定 1）：目标 **71** · 零前置链 **56** · 带前置链留缺 **15**。"""
    tool = _tool()
    rows = tool.targets(REPO_ROOT)
    assert len(rows) == EXPECTED_TARGETS
    probeable = tool.zero_prerequisite_targets(REPO_ROOT)
    assert len(probeable) == EXPECTED_PROBEABLE
    assert len(tool.left_out_prerequisite_chains(REPO_ROOT)) == EXPECTED_PREREQUISITE_CHAIN
    document = _evidence()
    assert document["targets"] == EXPECTED_TARGETS
    assert document["probeable"] == EXPECTED_PROBEABLE
    assert len(document["left_out_prerequisite_chain"]) == EXPECTED_PREREQUISITE_CHAIN
    assert set(document["left_out_prerequisite_chain"]) == set(
        tool.left_out_prerequisite_chains(REPO_ROOT)
    )
    # 本批**只**处理零前置链的端点（证据里逐行断言）
    for key, row in document["endpoints"].items():
        assert int(row["prerequisites"]) == 0, key
    # 写入方法 = `POST` 优先、否则 `PUT`（与 L5 同一判定）
    for row in rows:
        methods = tool._methods(_manifest()[str(row["key"])]["methods"])
        assert row["write_method"] == ("POST" if "POST" in methods else "PUT"), row["key"]


# ===== 2. 证据 =====


def test_p150r118_the_evidence_is_honest_and_the_counts_are_pinned() -> None:
    """门槛（判定 2）：**56** 行；**37** `PASSED` + **14** `LEFT_OUT` + **5** `FAILED`；未中止。"""
    document = _evidence()
    assert document["criterion_version"] == CRITERION_VERSION
    assert document["instance"]["alias"] == INSTANCE_ALIAS
    assert document["instance"]["product"] == INSTANCE_PRODUCT
    assert document["instance"]["probed_at"] == PROBED_AT
    assert document["aborted"] == ""
    assert len(document["endpoints"]) == EXPECTED_PROBEABLE
    assert document["counts"] == EXPECTED_COUNTS
    assert tuple(
        sorted(k for k, r in document["endpoints"].items() if r["verdict"] == "PASSED")
    ) == (EXPECTED_PASSED)
    assert (
        tuple(sorted(k for k, r in document["endpoints"].items() if r["verdict"] == "LEFT_OUT"))
        == EXPECTED_LEFT_OUT
    )
    assert tuple(
        sorted(k for k, r in document["endpoints"].items() if r["verdict"] == "FAILED")
    ) == tuple(sorted((*EXPECTED_FAILED_PUT_REJECTED, *EXPECTED_FAILED_DELETE)))


# ===== 3. 侦察问题①②（判定 3 / 4）=====


def test_p150r118_the_put_body_shape_is_the_same_as_the_create_shape() -> None:
    """门槛（判定 3）：**37 / 37** `PASSED` 都用 `assign_keyed_item`（与 POST 同一形状）。"""
    document = _evidence()
    shapes = {
        row["put_shape"] for row in document["endpoints"].values() if row["verdict"] == "PASSED"
    }
    assert shapes == {EXPECTED_PUT_SHAPE}
    for key in EXPECTED_PASSED:
        row = document["endpoints"][key]
        assert row["put_status_code"] == 200, key
        assert row["put_attempts"][0]["shape"] == EXPECTED_PUT_SHAPE, key
        assert row["put_attempts"][0]["status_code"] == 200, key


def test_p150r118_put_does_not_require_the_record_to_exist() -> None:
    """门槛（判定 4）：**37 / 37** `PASSED` 的 `requires_existing_record` = **`False`**
    （删除后对同一编号再发同一 `PUT`，记录**重新出现**）⇒ `PUT` 是 upsert。
    """
    document = _evidence()
    for key in EXPECTED_PASSED:
        row = document["endpoints"][key]
        assert row["put_absent_recreated"] is True, key
        assert row["requires_existing_record"] is False, key
        assert row["put_absent_status"] == 200, key


# ===== 4. 改动可复算 + 失败逐条（判定 5 / 6）=====


def test_p150r118_the_edits_are_mechanically_recomputable() -> None:
    """门槛（判定 5）：每行的 `edit` == `editable_change(body, item_schema)`（离线可复算）。"""
    tool = _tool()
    check_tool = _check_tool()
    document = _evidence()
    for key, row in sorted(document["endpoints"].items()):
        if row["verdict"] == "LEFT_OUT":
            assert row["edit"] is None, key
            assert row["detail"].startswith("no_editable_scalar"), key
            continue
        relative = str(_manifest()[key]["schema"])
        item_schema = check_tool.request_schema(REPO_ROOT, relative, key)
        body = tool._template_body(REPO_ROOT, key)
        expected = tool.editable_change(body, item_schema)
        assert expected is not None, key
        assert {name: row["edit"][name] for name in ("path", "from", "to")} == {
            name: expected[name] for name in ("path", "from", "to")
        }, key
        # 改动**确实**生效（`PASSED`）或**被拒**（`FAILED`）—— 逐条如实
        if row["verdict"] == "PASSED":
            assert row["edit_confirmed"] is True, key
            assert row["read_back"] is True, key


def test_p150r118_the_five_failures_are_recorded_per_endpoint() -> None:
    """门槛（判定 6）：**4** 个 `put_rejected:400`（三种形状全试过）+ **1** 个 `delete_failed`。"""
    document = _evidence()
    for key in EXPECTED_FAILED_PUT_REJECTED:
        row = document["endpoints"][key]
        assert row["detail"].startswith("put_rejected:400"), key
        assert row["put_shape"] == "", key
        assert len(row["put_attempts"]) == 3, key
        assert {attempt["shape"] for attempt in row["put_attempts"]} == set(tool_shapes())
        assert row["read_back"] is True, key
        assert row["deleted"] is True, key
    for key in EXPECTED_FAILED_DELETE:
        row = document["endpoints"][key]
        assert row["detail"] == "delete_failed", key
        assert row["put_shape"] == EXPECTED_PUT_SHAPE, key
        assert row["edit_confirmed"] is True, key
        assert row["deleted"] is False, key


def tool_shapes() -> tuple[str, ...]:
    """工具声明的 PUT 形状集合（**唯一**来源）。"""
    return tuple(_tool().PUT_SHAPES)


# ===== 5. 残留如实披露（判定 7）=====


def test_p150r118_the_residue_is_disclosed_and_the_delete_verification_is_honest() -> None:
    """门槛（判定 7）：`DELETE` 会「假成功」⇒ 判据以**再读确认**为准；残留**如实**披露。"""
    tool = _tool()
    document = _evidence()
    assert document["residue"] == EXPECTED_RESIDUE
    assert set(document["residue"]) <= set(document["allowed_residue"])
    assert document["allowed_residue"] == sorted(EXPECTED_RESIDUE)
    for key in EXPECTED_DELETE_UNCONFIRMED:
        row = document["endpoints"][key]
        assert row["deleted"] is False, key
        assert row["write_method"] == "PUT", key
    # `--check` 必须**通过**（残留 ⊆ 已披露）—— 不得靠放宽判定让它变绿
    assert tool.check(REPO_ROOT) == 0
    # 工具**必须**以再读为准（源码里存在保守判定的辅助函数）
    source = TOOL_PATH.read_text(encoding="utf-8")
    assert "def _gone(" in source
    assert "保守**判定「该编号已不在」" in source


# ===== 6. 与 R107 分桶 + 数据侧一行未改（判定 8）=====


def test_p150r118_the_bucket_is_separate_and_the_data_side_is_untouched() -> None:
    """门槛（判定 8）：本桶**不**并入 L5 三步链的分子；数据侧**一行未改**。"""
    tool = _tool()
    document = _evidence()
    note = " ".join(document["note"])
    assert "R107" in note and "write_path_coverage" in note
    # 证据里**没有** `availability` / `verification_status`（不碰判定口径）
    for key, row in document["endpoints"].items():
        assert "availability" not in row, key
        assert "verification_status" not in row, key
    # 工具**不**触碰任何覆盖率口径（只在说明文字里**提到**它 ⇒ 检查命名空间而非源码）
    assert not [name for name in dir(tool) if "coverage" in name.lower()]
    assert _unchanged_since_head(TEMPLATES_PATH)
    # 数据侧：模板文件与端点 YAML **一字未改**
    for key in document["endpoints"]:
        definition = REPO_ROOT / "registry" / str(_manifest()[key]["definition"])
        assert _unchanged_since_head(definition), key


# ===== 7. 工具纪律 =====


def test_p150r118_the_tool_chunks_health_checks_and_leaks_nothing() -> None:
    """门槛：分块 ≤ **10** + 块间只读健康检查；证据里**没有**凭据 / 响应体原文。"""
    tool = _tool()
    assert tool.CHUNK_SIZE == 10
    assert tool.CHUNK_SIZE <= 20
    assert tool.HEALTH_PATH == "/DB/NODE"
    assert tool.CRITERION_VERSION == CRITERION_VERSION
    assert tool.SHAPE_ASSIGN_ITEM in tool.PUT_SHAPES
    document = _evidence()
    assert set(document) == {
        "note",
        "criterion_version",
        "instance",
        "targets",
        "probeable",
        "left_out_prerequisite_chain",
        "counts",
        "aborted",
        "sentinel_before",
        "sentinel_after",
        "residue",
        "allowed_residue",
        "endpoints",
    }
    allowed = {
        "uri",
        "read_root",
        "wrapper",
        "write_method",
        "products",
        "prerequisites",
        "created_id",
        "read_back",
        "edit",
        "edit_confirmed",
        "deleted",
        "put_shape",
        "put_status_code",
        "put_attempts",
        "put_absent_status",
        "put_absent_recreated",
        "requires_existing_record",
        "detail",
        "payload_source",
        "status_code",
        "verdict",
    }
    for key, row in document["endpoints"].items():
        assert set(row) <= allowed, key
        # **只碰自建编号**：编号必须是正整数（空项目 ⇒ `1`）
        assert str(row["created_id"]).isdigit() and int(row["created_id"]) >= 1, key
    # 凭据**取值**绝不落盘：逐条断言「证据里**没有**任何键名像凭据」
    forbidden = {
        "mapi-key",
        "mapi_key",
        "authorization",
        "bearer",
        "token",
        "password",
        "secret",
        "credential",
        "api_key",
        "apikey",
    }
    found: list[str] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for name, value in node.items():
                if str(name).strip().lower() in forbidden:
                    found.append(str(name))
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(document)
    assert found == []
