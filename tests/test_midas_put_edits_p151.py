"""P151 / **R118 续跑** + **R120 工具化** —— 写路径「编辑（PUT）」判据的**前置链**部分。

背景
----
P150 把 R118 的判据（只读哨兵 → 创建 → 读回 → **PUT 改动过的值** → 读回确认 → 删除 → 读回消失 →
**无副作用观察**）落成可执行判定，但**只**处理了**零前置链**的 **56** 个端点；带前置链的 **15** 个
如实留缺（`prerequisite_chain_out_of_scope`）。本批（P151）**同一判据、同一证据**续跑那 **15** 个。

1. **前置链沿用 L5 的机制**（`app/infrastructure/adapters/midas/write_probe.py` 的 `_plan` 规则）：
   前置编号 = 该端点既有编号的 `max + 1`（`id_source = "target"` 的前置取**目标**编号；目标可用
   `target_id_source` **反向**取某个前置的编号），按模板声明的 `references` / `self_references`
   写回，**按声明顺序创建**、**逆序删除**，**只**碰自建编号。
   本文件的等价性用例把工具 `plan_chain()` 与 L5 `_plan()` **逐条**比对（空项目 + **非空**快照）。
2. **证据诚实**：**71** 行（56 + 15）；`verdict` = **42** `PASSED` + **23** `LEFT_OUT` +
   **6** `FAILED`；
   `aborted` 为空；`criterion_version` = **3**（判据**未**变）；`left_out_prerequisite_chain` **空**
   （带链的端点**全部**取得结论）。
3. **残留如实披露**：跑前 / 跑后只读哨兵覆盖**全部目标 ∪ 全部前置端点**（**72** 个，含 `DB.NODE`）；
   跑后非空**只有**已披露的 `DESIGN.SRC.AIK-SRC2K.DSRC`（**R121**）。
4. **R120（别名路由）工具化**：`DESIGN.*` 别名路由的 `DELETE` **不生效**（返回 `200` 而记录仍在）⇒
   清理路径 = **同表 `DB.*` 路由**。映射**必须来自实测**：`--probe-aliases` 用**自建编号**经别名路由
   创建 ⇒ 该编号出现在同表 `DB.*` 路由的读回块里（`same_table_observed`）⇒ `DB.*` 路由 `DELETE` 后
   **两个**路由再读均不在（`delete_confirmed`）。证据里**区分**「删除已确认」/「别名清理已确认」/
   「删除未确认」。
5. **数据侧一行未改**：模板 / 端点 YAML / `check_write_templates.py` 相对 `HEAD` 一字未改
   （本批只改**工具**与**证据**）。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import test_midas_write_templates_p139 as p139
from app.infrastructure.adapters.midas.live import DedicatedTestProject
from app.infrastructure.adapters.midas.write_probe import MidasLiveWriteProbe
from app.infrastructure.adapters.midas.write_templates import load_write_templates

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录。"""

TOOL_PATH = REPO_ROOT / "registry" / "tools" / "probe_put_edits.py"
"""R118 的复算工具（`--probe` / `--probe-aliases` / `--check` / `--summary`）。"""

EVIDENCE_PATH = REPO_ROOT / "registry" / "live" / "put_edit_probe.json"
"""R118 的证据（**71** 行；**不含**凭据、**不含**响应体原文）。"""

TEMPLATES_PATH = REPO_ROOT / "registry" / "live" / "write_templates.json"
CHECK_TOOL_PATH = REPO_ROOT / "registry" / "tools" / "check_write_templates.py"
MANIFEST_PATH = REPO_ROOT / "registry" / "manifest.json"

CRITERION_VERSION = 3
"""判据版本（P151 **未**改判据 ⇒ 与 P150 同一版本）。"""

EXPECTED_TARGETS = 71
EXPECTED_ZERO_PREREQUISITE = 56
EXPECTED_CHAIN = 15
EXPECTED_COUNTS = {"PASSED": 42, "LEFT_OUT": 23, "FAILED": 6}

EXPECTED_CHAIN_KEYS = (
    "DB.BMLD",
    "DB.BODF",
    "DB.CNLD",
    "DB.CONS",
    "DB.EFCT",
    "DB.ELEM",
    "DB.EXLD",
    "DB.FBLD",
    "DB.LDSQ",
    "DB.LENG",
    "DB.MBTP",
    "DB.NMAS",
    "DB.PDEL",
    "DB.PRES",
    "DB.TDNT",
)
"""本批续跑的 **15** 个带前置链端点（P150 的留缺集）。"""

EXPECTED_CHAIN_PASSED = ("DB.ELEM", "DB.LENG", "DB.NMAS", "DB.PDEL", "DB.TDNT")
"""六步全成立（创建 → 读回 → 编辑 → 读回确认 → 删除 → 读回消失）。"""

EXPECTED_CHAIN_LEFT_OUT = (
    "DB.BMLD",
    "DB.BODF",
    "DB.CNLD",
    "DB.CONS",
    "DB.EXLD",
    "DB.FBLD",
    "DB.LDSQ",
    "DB.MBTP",
    "DB.PRES",
)
"""请求体里**没有**可机械改动的标量（`no_editable_scalar`）；仍走创建 → 读回 → 删除 + 逆序回收。"""

EXPECTED_CHAIN_FAILED = ("DB.EFCT",)
"""**R124**：`DB.EFCT` 的 `PUT` 三种形状**全部**被 `400` 拒绝（创建同一 body 成功）。"""

EXPECTED_ALIAS_KEYS = (
    "DESIGN.RC.DRC",
    "DESIGN.RC.KDS-41-20-2022.DCTL",
    "DESIGN.STEEL.DSTL",
)
"""R120 的**实测**候选配对（`DESIGN.*` 别名路由 → 同表 `DB.*` 路由）。"""

EXPECTED_RESIDUE = {"DESIGN.SRC.AIK-SRC2K.DSRC": ["1"]}
"""**如实披露**的残留（R121：无 `DB.*` 别名、实测删不掉 ⇒ `delete_unconfirmed`）。"""

EXPECTED_SENTINEL_EXTRA = ("DB.NODE",)
"""**只**作为前置出现、本身不在目标集里的端点 —— 哨兵必须一并覆盖（P151 新增）。"""


def _load(path: Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tool() -> Any:
    return _load(TOOL_PATH, "structai_probe_put_edits_p151")


def _evidence() -> dict[str, Any]:
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def _templates() -> Any:
    return load_write_templates(REPO_ROOT / "registry")


def _unchanged_since_head(path: Path) -> bool:
    result = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", str(path)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def _manifest_entry(key: str) -> dict[str, Any]:
    document = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for entry in document["endpoints"]:
        if str(entry["key"]) == key:
            return entry
    raise AssertionError(f"{key} not in registry/manifest.json")


# ===== 1. 目标集与留缺（判定 1 / 2）=====


def test_p151_the_fifteen_chain_targets_are_probed_and_nothing_is_left_out() -> None:
    """门槛：带链端点 **15** 个**全部**取得结论 ⇒ `left_out_prerequisite_chain` **空**。"""
    tool = _tool()
    document = _evidence()
    assert tuple(tool.prerequisite_chain_targets(REPO_ROOT)) == EXPECTED_CHAIN_KEYS
    assert len(tool.zero_prerequisite_targets(REPO_ROOT)) == EXPECTED_ZERO_PREREQUISITE
    assert len(tool.targets(REPO_ROOT)) == EXPECTED_TARGETS
    assert tool.left_out_prerequisite_chains(REPO_ROOT) == []
    assert document["criterion_version"] == CRITERION_VERSION
    assert document["targets"] == EXPECTED_TARGETS
    assert document["probeable"] == EXPECTED_TARGETS
    assert document["zero_prerequisite"] == EXPECTED_ZERO_PREREQUISITE
    assert tuple(document["prerequisite_chain_targets"]) == EXPECTED_CHAIN_KEYS
    assert document["left_out_prerequisite_chain"] == []
    assert document["aborted"] == ""
    # 逐行：`prerequisites` 与数据侧模板声明**逐条**一致（**不**放宽）
    for key, row in sorted(document["endpoints"].items()):
        declared = len(tool.prerequisite_keys(REPO_ROOT, key))
        assert int(row["prerequisites"]) == declared, key


def test_p151_the_chain_rows_carry_the_pinned_verdicts() -> None:
    """门槛（判定 2）：**42** `PASSED` + **23** `LEFT_OUT` + **6** `FAILED`；15 行逐条钉住。"""
    document = _evidence()
    assert document["counts"] == EXPECTED_COUNTS
    assert len(document["endpoints"]) == EXPECTED_TARGETS
    for key in EXPECTED_CHAIN_KEYS:
        assert key in document["endpoints"], key
    for group, verdict in (
        (EXPECTED_CHAIN_PASSED, "PASSED"),
        (EXPECTED_CHAIN_LEFT_OUT, "LEFT_OUT"),
        (EXPECTED_CHAIN_FAILED, "FAILED"),
    ):
        for key in group:
            assert document["endpoints"][key]["verdict"] == verdict, key


# ===== 2. 前置链可离线复算（判定 3）=====


def test_p151_the_chain_plan_is_recomputable_offline() -> None:
    """门槛：`plan_chain()` 用「模板 + `own_id` + `scope_before`」**逐条**复算证据里的编号。"""
    tool = _tool()
    document = _evidence()
    for key in EXPECTED_CHAIN_KEYS:
        row = document["endpoints"][key]
        template = _templates().get(key)
        assert template is not None, key
        _body, planned, target_id = tool.plan_chain(
            template, template.body, row["own_id"], row["scope_before"]
        )
        assert row["target_id"] == target_id, key
        assert row["created_id"] == target_id, key
        assert [(item["key"], item["item_id"]) for item in row["prerequisite_chain"]] == [
            (prereq_key, item_id) for prereq_key, item_id, _body in planned
        ], key
        # 编号一律**重新分配**：不得照抄模板里的字面编号
        assert row["own_id"].isdigit() and int(row["own_id"]) >= 1, key
        for item in row["prerequisite_chain"]:
            assert int(item["item_id"]) >= 1, key
            assert item["create_status"] in (200, 400), key
        # 前置端点的既有编号快照**只读**、逐条记进证据（编号分配的依据）
        for prereq_key in tool.prerequisite_keys(REPO_ROOT, key):
            assert prereq_key in row["scope_before"], (key, prereq_key)
        assert key in row["scope_before"], key


async def test_p151_the_chain_planning_is_equivalent_to_l5() -> None:
    """门槛（判定 1）：工具 `plan_chain()` 与 L5 `_plan()` **逐条等价**（空项目 + 非空快照）。

    离线假传输按数据侧解包链回放 —— **不**发任何真实请求。
    """
    tool = _tool()
    templates = _templates()
    registry = p139._registry()
    for key in EXPECTED_CHAIN_KEYS:
        template = templates.get(key)
        assert template is not None, key
        codes = (*(f"DB.{item}" for item in ("NODE", "ELEM", "MATL", "SECT", "STLD")), key)
        for initial, own_id in (
            ({}, "1"),
            (
                {
                    "DB.STLD": {"5": {}},
                    "DB.NODE": {"3": {}, "4": {}},
                    "DB.MATL": {"7": {}},
                    "DB.SECT": {"9": {}},
                    "DB.ELEM": {"2": {}},
                },
                "8",
            ),
        ):
            store = p139._NxStore(codes=codes, initial=initial)
            probe = MidasLiveWriteProbe(
                p139._client(store),
                registry,
                product="GEN_NX",
                project=DedicatedTestProject(name="p151"),
                limit=0,
                only=(key,),
            )
            scope: dict[str, tuple[str, ...]] = {}
            body, planned, target_id = await probe._plan(template, template.body, own_id, scope)
            existing = {
                str(name): tuple(str(item) for item in values)
                for name, values in (scope or {}).items()
            }
            mine_body, mine_planned, mine_target = tool.plan_chain(
                template, template.body, own_id, existing
            )
            assert mine_target == target_id, (key, initial)
            assert mine_body == body, (key, initial)
            assert [
                (item.prerequisite.key, item.item_id, item.body) for item in planned
            ] == mine_planned, (key, initial)
            # 非空快照下必须**真的**用上了既有编号（否则等价性没被检验到）
            if initial:
                assert any(int(item.item_id) > 1 for item in planned), (key, "既有编号未被计入")


# ===== 3. 编辑可复算 + 逆序回收（判定 4 / 5）=====


def test_p151_the_edit_is_recomputable_on_the_planned_body() -> None:
    """门槛（判定 4）：`edit` == `editable_change(改写后的 body, 条目 Schema)`（离线可复算）。"""
    tool = _tool()
    check_tool = _load(CHECK_TOOL_PATH, "structai_check_write_templates_p151")
    document = _evidence()
    for key in EXPECTED_CHAIN_KEYS:
        row = document["endpoints"][key]
        template = _templates().get(key)
        assert template is not None, key
        body, _planned, _target = tool.plan_chain(
            template, template.body, row["own_id"], row["scope_before"]
        )
        item_schema = check_tool.request_schema(REPO_ROOT, str(_manifest_entry(key)["schema"]), key)
        expected = tool.editable_change(body, item_schema)
        if row["edit"] is None:
            assert expected is None, key
            assert row["detail"].startswith("no_editable_scalar"), key
            continue
        assert expected is not None, key
        assert {name: row["edit"][name] for name in ("path", "from", "to")} == {
            name: expected[name] for name in ("path", "from", "to")
        }, key


def test_p151_the_chain_is_cleaned_up_in_reverse_and_confirmed() -> None:
    """门槛（判定 5）：`PASSED` 的行目标 + **全部**前置都「再读确认不在」；哨兵无新残留。"""
    document = _evidence()
    for key in EXPECTED_CHAIN_PASSED:
        row = document["endpoints"][key]
        assert row["read_back"] is True, key
        assert row["edit_confirmed"] is True, key
        assert row["deleted"] is True, key
        assert row["delete_state"] == "delete_confirmed", key
        assert row["put_shape"] == "assign_keyed_item", key
        assert row["requires_existing_record"] is False, key
        assert row["prerequisite_chain"], key
        assert all(item["deleted"] for item in row["prerequisite_chain"]), key
        assert all(item["delete_status"] == 200 for item in row["prerequisite_chain"]), key
    for key in EXPECTED_CHAIN_LEFT_OUT:
        row = document["endpoints"][key]
        assert row["read_back"] is True, key
        assert row["deleted"] is True, key
        assert all(item["deleted"] for item in row["prerequisite_chain"]), key
    # 哨兵：跑后非空**只有**已披露的残留
    nonempty = {
        name: value["ids"] for name, value in document["sentinel_after"].items() if value["ids"]
    }
    assert nonempty == EXPECTED_RESIDUE
    assert set(document["residue"]) <= set(document["allowed_residue"])
    # 哨兵覆盖**前置**端点（`DB.NODE` **只**作为前置出现 ⇒ 旧口径会漏掉它）
    assert set(EXPECTED_SENTINEL_EXTRA) <= set(document["sentinel_endpoints"])
    assert len(document["sentinel_endpoints"]) == 72
    assert set(document["sentinel_endpoints"]) >= set(document["endpoints"])


# ===== 4. R120：别名路由的实测与收尾（判定 6）=====


def test_p151_the_alias_map_is_measured_and_the_cleanup_is_confirmed() -> None:
    """门槛（判定 6）：别名映射**实测**（`same_table_observed`）+ 同表 `DB.*` 路由清理**确认**。"""
    tool = _tool()
    document = _evidence()
    cleanup = document["alias_cleanup"]
    assert tuple(sorted(cleanup)) == tuple(sorted(EXPECTED_ALIAS_KEYS))
    assert tuple(sorted(tool.ALIAS_ROUTES)) == tuple(sorted(EXPECTED_ALIAS_KEYS))
    for key, entry in sorted(cleanup.items()):
        candidate = tool.ALIAS_ROUTES[key]
        assert entry["measured"] is True, key
        assert entry["alias_uri"] == candidate["alias_uri"], key
        assert entry["db_key"] == candidate["db_key"], key
        assert entry["db_uri"] == candidate["db_uri"], key
        # R120 的判据本身：别名路由 `DELETE` **不生效**，同表 `DB.*` 路由**生效**
        assert entry["same_table_observed"] is True, key
        assert entry["alias_delete_status"] == 200, key
        assert entry["alias_delete_effective"] is False, key
        assert entry["db_delete_status"] == 200, key
        assert entry["db_delete_effective"] is True, key
        assert entry["delete_confirmed"] is True, key
        row = document["endpoints"][key]
        assert row["deleted"] is False, key
        assert row["delete_state"] == "delete_confirmed_via_alias", key
        assert key not in document["residue"], key
    # R121：**无**别名的残留 ⇒ 如实记「删除未确认」
    residue_key = next(iter(EXPECTED_RESIDUE))
    assert document["endpoints"][residue_key]["delete_state"] == "delete_unconfirmed"
    assert document["residue"] == EXPECTED_RESIDUE
    assert document["allowed_residue"] == sorted(EXPECTED_RESIDUE)


# ===== 5. 工具纪律 + 数据侧一行未改（判定 7）=====


def test_p151_the_tool_is_recomputable_chunked_and_leaks_nothing() -> None:
    """门槛（判定 7）：`--check` 退出码 **0**；分块 ≤ **10** + 只读健康检查；证据里无凭据。"""
    tool = _tool()
    assert tool.check(REPO_ROOT) == 0
    assert tool.CHUNK_SIZE == 10
    assert tool.CHUNK_SIZE <= 20
    assert tool.HEALTH_PATH == "/DB/NODE"
    assert tool.CRITERION_VERSION == CRITERION_VERSION
    assert tool.ID_SOURCE_TARGET == "target"
    assert tool.OWNER_BODY_LABEL == "owner"
    document = _evidence()
    allowed_top = {
        "note",
        "criterion_version",
        "instance",
        "targets",
        "probeable",
        "zero_prerequisite",
        "prerequisite_chain_targets",
        "left_out_prerequisite_chain",
        "counts",
        "aborted",
        "sentinel_endpoints",
        "sentinel_before",
        "sentinel_after",
        "residue",
        "allowed_residue",
        "alias_cleanup",
        "endpoints",
    }
    assert set(document) == allowed_top
    allowed_row = {
        "uri",
        "read_root",
        "wrapper",
        "write_method",
        "products",
        "prerequisites",
        "created_id",
        "own_id",
        "target_id",
        "scope_before",
        "prerequisite_chain",
        "read_back",
        "edit",
        "edit_confirmed",
        "deleted",
        "delete_state",
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
        assert set(row) <= allowed_row, key
        assert str(row["created_id"]).isdigit(), key
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


def test_p151_the_data_side_is_untouched() -> None:
    """门槛（判定 7）：本批只改**工具**与**证据** —— 模板 / 端点 YAML / 复算工具一字未改。"""
    document = _evidence()
    assert _unchanged_since_head(TEMPLATES_PATH)
    assert _unchanged_since_head(CHECK_TOOL_PATH)
    for key in document["endpoints"]:
        definition = REPO_ROOT / "registry" / str(_manifest_entry(key)["definition"])
        assert _unchanged_since_head(definition), key
    # 证据里**没有** `availability` / `verification_status`（不碰判定口径）
    for key, row in document["endpoints"].items():
        assert "availability" not in row, key
        assert "verification_status" not in row, key
    # 本桶**不**并入 L5 三步链的覆盖率分子
    assert not [name for name in dir(_tool()) if "coverage" in name.lower()]


if __name__ == "__main__":  # pragma: no cover - 便于手工单跑
    raise SystemExit(pytest.main([__file__, "-q"]))
