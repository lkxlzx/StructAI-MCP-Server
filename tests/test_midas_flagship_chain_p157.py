"""P157：`docs/07` §13.5 的**旗舰五步链**在**真机**上的实测结论（**未跑通**，成因逐条钉住）。

一句话
------
**旗舰五步链在真机上仍未跑通** —— 而且这次**定位到了两处结构成因**（都**不是**探针问题）：

| 阶段 | 步 | 结果 | 原生成因 |
| --- | --- | --- | --- |
| **A（§13.5 逐字）** | ① `BUILD.COLUMN` | `FAILED` | `POST /DB/MATL` → **`400 Wrong Field`** |
| **B（替代前缀 ①′ + ②–⑤）** | ①′ 四个原子 Operation | **`PASSED` ×5** | —— |
| | ② `MODEL.LOAD.ASSIGN` | `FAILED` | `POST /DB/CNLD` → **`400 Not Found Key`** |
| | ③④⑤ | `NOT_RUN` | 链在 ② 停止（**有界**，不硬跑） |

⚠️ **两条都是 `app/**` 的结构缺口，本批未获授权 ⇒ 如实留缺、不修、不硬凑。**

* **R131（新）**：`BUILD.COLUMN` 的**材质**子步**结构上**发不出可被接受的 body ——
  `adapter._column_payloads` 只填 `name` / `type` / `elastic_modulus` / `poisson_ratio` /
  `density`，而原生**拒绝**这个字段集（`400 Wrong Field`）；**同一端点**在
  `MODEL.MATERIAL.ASSIGN` 下、**补齐 A′ 的 11 个原生字段**后**实测可用**
  （P154 / P157 写路径）。⇒ **`docs/07` §13.5 的参数集不足以在 GEN NX 上建材质**。
* **R132（新）**：`MODEL.LOAD.ASSIGN` **结构上**无法在**没有工况**的项目上成功 ——
  `DB.CNLD` 要求 `LCNAME` 指向**已存在**的工况（`400 Not Found Key`），而接口层
  **没有**任何 Operation 能**创建**工况：`MODEL.LOAD.ASSIGN` 的编排里**声明**了
  `DB.STLD` 的 `write_load_case` 步，但 `select_steps` **只**选出该荷载类型对应的那一步
  （`DB.STLD` 永不被执行）；`MODEL.LOAD.DELETE` 却**能删** `DB.STLD`（**不对称**）。

⚠️ **残留 = 0**：本批**自建**的编号**全部**逆序删除并**再读确认不在**（R119）；
跑前 / 跑后哨兵**一致且全空** ⇒ **项目未被弄脏**（`analysis_result_persists = None`：
③ 未运行，**没有**产生分析结果）。

⚠️ **R128 的判据在本批被**再验证**一次**：② 的 `2xx` **不**被当作通过 —— 它**是** `400`；
而 ①′ 的每一步都以**再读**为准（外层键无效时原生**静默 `200` 却不建**）。

本文件的判定点
--------------
1. **阶段 A 未通过**，且成因是 `DB.MATL` 的 `Wrong Field`（不是探针 / 不是端点不存在）。
2. **阶段 B 的 ①′ 通过 5 步**（建模链本身是通的）。
3. **阶段 B 的 ② 未通过**，成因是 `DB.CNLD` 的 `Not Found Key`（工况不存在）。
4. **R131 / R132 是结构事实**：离线**可复算**（不依赖证据文件）。
5. **零残留 + 哨兵一致**（项目未被弄脏）。
6. **不变量**：`write_path_coverage()` = `0 / 633` · 缺口 `517` = `271` + `246` ·
   分类 `271` = `0` + `51` + `220` · 写路径子桶 `13` = `13` · 读路径子桶 `15` = `2` + `7` + `6`。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.infrastructure.adapters.midas.live import write_path_coverage
from app.infrastructure.adapters.midas.operations import (
    LOAD_STEP_BY_TYPE,
    OPERATION_PLANS,
    plan_for,
    select_steps,
)
from app.infrastructure.adapters.midas.registry import MidasRegistry

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录。"""

CHAIN_EVIDENCE = REPO_ROOT / "registry" / "live" / "flagship_chain_probe.json"
WRITE_EVIDENCE = REPO_ROOT / "registry" / "live" / "interface_path_probe.json"
READ_EVIDENCE = REPO_ROOT / "registry" / "live" / "interface_read_probe.json"
GAP_EVIDENCE = REPO_ROOT / "registry" / "live" / "interface_mapping_gap.json"
CHAIN_TOOL = REPO_ROOT / "registry" / "tools" / "probe_flagship_chain.py"

SPEC_OPERATIONS = (
    "BUILD.COLUMN",
    "MODEL.LOAD.ASSIGN",
    "ANALYSIS.STATIC",
    "RESULT.NODE.DISPLACEMENT",
    "DESIGN.STEEL",
)
"""`docs/07` §13.5 的五步链（阶段 A 的步集）。"""

SUBSTITUTE_OPERATIONS = (
    "MODEL.MATERIAL.ASSIGN",
    "MODEL.SECTION.ASSIGN",
    "MODEL.NODE.CREATE",
    "MODEL.NODE.CREATE",
    "MODEL.ELEMENT.CREATE",
    "MODEL.LOAD.ASSIGN",
    "ANALYSIS.STATIC",
    "RESULT.NODE.DISPLACEMENT",
    "DESIGN.STEEL",
)
"""阶段 B 的步集（①′ 的 5 步 + ②–⑤）。"""

APRIME_MATERIAL_FIELDS = (
    "he_spec",
    "he_cond",
    "plmt",
    "p_name",
    "bmass_dens",
    "damp_rat",
    "p_type",
    "standard",
    "code",
    "db",
    "belast",
)
"""**R131 的关键**：`DB.MATL` 的 **11** 个 A′ 字段（`docs/07` §16.1 的 R126 行）。"""

SENTINEL_ENDPOINTS = (
    "DB.CNLD",
    "DB.CONS",
    "DB.ELEM",
    "DB.GRUP",
    "DB.MATL",
    "DB.NODE",
    "DB.SECT",
    "DB.STLD",
)

EXPECTED_WRITE_COUNTS = {"PASSED": 13}
EXPECTED_READ_COUNTS = {"PASSED": 2, "PARTIAL": 7, "FAILED": 6}
EXPECTED_GAP_TOTAL = 517
EXPECTED_GAP_NOT_IN_CONTRACT = 271
EXPECTED_GAP_NO_READBACK = 246
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


def _chain() -> dict[str, Any]:
    return _json(CHAIN_EVIDENCE)


def _step(document: dict[str, Any], key: str, operation: str) -> dict[str, Any]:
    rows = document.get(key) or []
    for row in rows:
        if str(row["operation"]) == operation:
            return row
    raise AssertionError(f"{operation} not in {key}")


def _rejections(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in row["requests"] if int(item["status"]) >= 400]


# ===== 1. 阶段 A：`docs/07` §13.5 逐字 —— **未通过** =====


def test_p157_the_spec_chain_does_not_pass_and_stops_at_the_first_step() -> None:
    """门槛：阶段 A **未通过**，且**首个失败即停**（其余记 `NOT_RUN`，**不**硬跑）。"""
    document = _chain()
    assert document["criterion_version"] == 1
    assert [str(row["operation"]) for row in document["steps"]] == list(SPEC_OPERATIONS)
    assert document["verdict"] == "NOT_PASSED"
    assert document["counts"] == {"FAILED": 1, "NOT_RUN": 4}
    assert document["aborted"] == ""
    build = document["steps"][0]
    assert build["status"] == "FAILED", build
    assert build["detail"] == "readback_absent", build
    for row in document["steps"][1:]:
        assert row["status"] == "NOT_RUN", row
        assert row["detail"] == "chain_stopped_at_previous_failure", row


def test_p157_the_spec_chain_is_blocked_by_the_material_field_set() -> None:
    """门槛（**R131**）：① 的成因 = `POST /DB/MATL` 的 **`400 Wrong Field`**（取值级 / 字段集）。

    ⚠️ **不是**端点不存在、**不是**形状（外层键是编号 `"1"`）、**不是**探针参数缺失 ——
    节点 / 单元**都**已建成（再读确认），只有材质被拒。
    """
    build = _chain()["steps"][0]
    assert build["readback"]["DB.NODE"]["present"] is True, build["readback"]
    assert build["readback"]["DB.ELEM"]["present"] is True, build["readback"]
    assert build["readback"]["DB.MATL"]["present"] is False, build["readback"]
    assert build["readback"]["DB.SECT"]["present"] is False, build["readback"]
    rejected = _rejections(build)
    assert len(rejected) == 1, rejected
    assert rejected[0]["method"] == "POST", rejected[0]
    assert str(rejected[0]["path"]).endswith("/DB/MATL"), rejected[0]
    assert "Wrong Field" in str(rejected[0]["native_error"]), rejected[0]
    body = rejected[0]["body"]["Assign"]
    assert list(body) == ["1"], body  # 外层键 = **编号**（形状是对的）
    entry = body["1"]
    assert entry["NAME"] == "Q355B" and entry["TYPE"] == "STEEL", entry
    # ⚠️ 被拒的 body **只**有 3 个顶层键 + `PARAM` 的 3 个叶子 —— 与 A′ 后的 11 个字段的差集
    assert set(entry) == {"NAME", "TYPE", "PARAM"}, entry
    assert set(entry["PARAM"][0]) == {"ELAST", "POISN", "DEN"}, entry["PARAM"][0]


def test_p157_r131_the_build_column_material_payload_cannot_express_the_aprime_fields() -> None:
    """门槛（**R131**，离线可复算）：`BUILD.COLUMN` 的材质载荷**结构上**发不出 A′ 的 11 字段。"""
    from app.infrastructure.adapters.midas.adapter import _column_payloads  # noqa: PLC0415

    tool = _load(CHAIN_TOOL, "structai_probe_flagship_chain_p157")
    parameters = dict(tool.COLUMN_PARAMETERS)
    payloads = _column_payloads(parameters)
    material = payloads["write_material"][0]
    assert material["name"] == "Q355B"
    # 这 5 个是 `_column_payloads` **能**表达的；A′ 的 11 个**一个都不在**（**不**臆造）
    assert set(material) == {
        "id",
        "name",
        "type",
        "elastic_modulus",
        "poisson_ratio",
        "density",
    }, material
    for field in APRIME_MATERIAL_FIELDS:
        assert field not in material, field
    # ⇒ 同一端点用**补齐 A′** 的载荷时**实测可用**（P154 / P157 写路径的 `DB.MATL` 行）
    write = _json(WRITE_EVIDENCE)
    add = next(
        row for row in write["paths"] if row["path"] == "add" and str(row["endpoint"]) == "DB.MATL"
    )
    assert add["status"] == "PASSED", add
    accepted = next(
        item
        for item in add["requests"]
        if item["method"] == "POST" and str(item["path"]).endswith("/DB/MATL")
    )
    assert int(accepted["status"]) == 200, accepted
    entry = accepted["body"]["Assign"]["1"]
    assert set(entry["PARAM"][0]) >= {"ELAST", "POISN", "DEN", "DB", "STANDARD", "P_TYPE"}, entry


# ===== 2. 阶段 B：①′ 通过（建模链是通的）=====


def test_p157_the_substituted_prefix_builds_the_model() -> None:
    """门槛：①′ 的 **5** 步**全部** `PASSED`（材质 / 截面 / 2 节点 / 单元，逐条**再读**确认）。"""
    document = _chain()
    assert [str(row["operation"]) for row in document["substituted"]] == list(SUBSTITUTE_OPERATIONS)
    assert document["substitute_reason"], document
    prefix = document["substituted"][:5]
    assert [str(row["status"]) for row in prefix] == ["PASSED"] * 5, prefix
    for row in prefix:
        assert not row["error"], row
        assert not _rejections(row), row
        for endpoint, snapshot in row["readback"].items():
            assert snapshot["present"] is True, (endpoint, snapshot)
    assert document["substituted_counts"] == {"PASSED": 5, "FAILED": 1, "NOT_RUN": 3}
    assert document["substituted_verdict"] == "NOT_PASSED"


# ===== 3. 阶段 B：② 未通过（工况不存在）=====


def test_p157_the_load_assignment_is_blocked_by_the_missing_load_case() -> None:
    """门槛（**R132**）：② 的成因 = `POST /DB/CNLD` 的 **`400 Not Found Key`**（工况不存在）。

    ⚠️ 判据**以再读为准**（R128）：`DB.CNLD` 的再读**为空** ⇒ **不**因接口层 `2xx` 而通过
    （本行原生 `400`，接口层如实上抛 `STRUCTAI-2200`）。
    """
    load = _step(_chain(), "substituted", "MODEL.LOAD.ASSIGN")
    assert load["status"] == "FAILED", load
    assert load["error"]["code"] == "STRUCTAI-2200", load["error"]
    assert load["error"]["details"]["reason"] == "task_not_completed", load["error"]
    assert load["readback"]["DB.CNLD"] == {"ids": [], "present": False}, load["readback"]
    rejected = _rejections(load)
    assert len(rejected) == 1, rejected
    assert rejected[0]["method"] == "POST", rejected[0]
    assert str(rejected[0]["path"]).endswith("/DB/CNLD"), rejected[0]
    assert "Not Found Key" in str(rejected[0]["native_error"]), rejected[0]
    entry = rejected[0]["body"]["Assign"]["2"]["ITEMS"][0]
    assert entry["LCNAME"] == "AXIAL", entry


def test_p157_r132_no_operation_creates_a_load_case() -> None:
    """门槛（**R132**，**离线可复算**）：**没有**任何 Operation 会**执行**创建工况的那一步。

    `MODEL.LOAD.ASSIGN` 的编排**声明**了 `DB.STLD` 的 `write_load_case` 步，
    但 `select_steps` 对**每一种**已映射荷载类型都**只**返回该类型对应的那一步
    ⇒ `DB.STLD` **永不**被执行；而 `MODEL.LOAD.DELETE` **能删** `DB.STLD`（**不对称**）。
    """
    plan = plan_for("MODEL.LOAD.ASSIGN")
    declared = {str(step.key): str(step.intent) for step in plan.steps}
    assert declared.get("DB.STLD") == "write_load_case", declared
    for load_type, endpoint in LOAD_STEP_BY_TYPE.items():
        steps = select_steps("MODEL.LOAD.ASSIGN", {"load_type": load_type})
        assert len(steps) == 1, (load_type, steps)
        assert str(steps[0].key) == endpoint, (load_type, steps)
        assert str(steps[0].key) != "DB.STLD", (load_type, steps)
    # 全库范围：**没有**任何 Operation 的**声明**步里有第二个 `write_load_case` 端点
    creators = {
        name: [
            str(step.key)
            for step in OPERATION_PLANS[name].steps
            if step.intent == "write_load_case"
        ]
        for name in OPERATION_PLANS
    }
    assert {name: keys for name, keys in creators.items() if keys} == {
        "MODEL.LOAD.ASSIGN": ["DB.STLD"]
    }, creators
    # 删除侧**不对称**：`MODEL.LOAD.DELETE` 能删 `DB.STLD`
    delete_steps = {str(step.key): str(step.intent) for step in plan_for("MODEL.LOAD.DELETE").steps}
    assert delete_steps.get("DB.STLD") == "delete_load", delete_steps


# ===== 4. 零残留 + 哨兵一致（**项目未被弄脏**）=====


def test_p157_the_run_left_no_residue_and_the_sentinels_agree() -> None:
    """门槛：**零残留** + 跑前 / 跑后哨兵**一致且全空**（R119；**不**声称未验证的状态）。"""
    document = _chain()
    assert document["residue"] == {}, document["residue"]
    assert tuple(document["sentinel_endpoints"]) == SENTINEL_ENDPOINTS
    for key in ("sentinel_before", "sentinel_mid", "sentinel_after"):
        snapshot = document[key]
        assert sorted(snapshot) == sorted(SENTINEL_ENDPOINTS), key
        for endpoint, value in snapshot.items():
            assert int(value["status"]) == 200, (key, endpoint, value)
            assert value["ids"] == [], (key, endpoint, value)
    assert document["sentinel_before"] == document["sentinel_after"]
    # 两轮清理（阶段 A 后 + 收尾）**逐条**确认
    for phase in ("cleanup_mid", "cleanup"):
        for item in document[phase]:
            assert item["gone"] is True, (phase, item)
    # ③ **未**运行 ⇒ **没有**分析结果（**不**声称「已清掉」）
    assert document["analysis_result_persists"] is None, document["analysis_result_persists"]
    assert all(
        row["status"] == "NOT_RUN"
        for row in (*document["steps"], *document["substituted"])
        if row["operation"] == "ANALYSIS.STATIC"
    )


def test_p157_the_evidence_never_carries_credentials() -> None:
    """门槛（`docs/07` §14.3）：证据里**没有**凭据形态。"""
    raw = CHAIN_EVIDENCE.read_text(encoding="utf-8")
    for marker in ("MAPI-Key", "MAPI_KEY", "mapi-key", "password", "secret"):
        assert marker not in raw, marker


def test_p157_the_check_mode_agrees_offline() -> None:
    """门槛：`probe_flagship_chain --check` 离线跑通（退出码 0）。"""
    result = subprocess.run(
        [sys.executable, str(CHAIN_TOOL), "--check"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "旗舰链证据自洽" in result.stdout


# ===== 5. 不变量（本批**不得**放宽既有判定）=====


def test_p157_the_invariants_are_untouched() -> None:
    """门槛：数据侧分母 / 缺口 / 写路径与读路径子桶**一行未变**。"""
    registry = MidasRegistry.load(REPO_ROOT / "registry")
    coverage = write_path_coverage(registry, [])
    assert coverage.ratio == f"0 / {EXPECTED_WRITE_PATH_TOTAL}"
    assert coverage.model_write_ratio == f"0 / {EXPECTED_MODEL_WRITE_TOTAL}"
    gap = _json(GAP_EVIDENCE)
    assert int(gap["gap_total"]) == EXPECTED_GAP_TOTAL
    assert len(gap["gap_three_step"]) == EXPECTED_GAP_NOT_IN_CONTRACT
    assert len(gap["gap_no_readback"]) == EXPECTED_GAP_NO_READBACK
    assert _json(WRITE_EVIDENCE)["counts"] == EXPECTED_WRITE_COUNTS
    assert _json(READ_EVIDENCE)["counts"] == EXPECTED_READ_COUNTS


def test_p157_the_chain_probe_is_bounded_and_declares_its_cleanup_order() -> None:
    """门槛：探针**有界**且**逆序**清理 —— 纪律参数可被**读出**（本用例**不**重跑请求）。"""
    tool = _load(CHAIN_TOOL, "structai_probe_flagship_chain_p157_bounded")
    assert tool.MAX_REQUESTS <= 200
    assert len(tool.SPEC_STEPS) == 5
    assert [str(step["operation"]) for step in tool.SPEC_STEPS] == list(SPEC_OPERATIONS)
    assert tool.PASSED == "PASSED"
    # 逆序：依赖方在前、被依赖方在后
    order = [endpoint for endpoint, _operation in tool.CLEANUP_ORDER]
    assert order == [
        "DB.CNLD",
        "DB.CONS",
        "DB.ELEM",
        "DB.NODE",
        "DB.MATL",
        "DB.SECT",
        "DB.STLD",
    ], order
    # ⚠️ 工况**没有**接口层创建路径（R132）⇒ 清理里**有**它（删除侧存在）
    assert "DB.STLD" in order
    assert tool.SENTINEL_ENDPOINTS == SENTINEL_ENDPOINTS
