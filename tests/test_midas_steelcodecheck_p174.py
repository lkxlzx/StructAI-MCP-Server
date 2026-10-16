"""P174 / **R166**：`POST.STEELCODECHECK` **真机实测收口** ⇒ 主指标 **`68 / 71` → `71 / 73`**。

本批做的事
----------
**R165（P172）** 算准了收益（收口它 ⇒ **+1**，解锁 `DESIGN.CODE_CHECK`），但**卡在**「请求体来源
在本仓不成立」；**R166（P173）** 算出它是**我方唯一**杠杆（不依赖崩溃族 `*-ANAL`）。
⇒ 本批（**用户明确授权**一次**有副作用**的写路径测量）**真的**把它拿下了。

判据（**铁律 ⓪**：效果，**不是**状态码）—— 三段对照 + 防回显
-----------------------------------------------------------
| 相 | 期望 | 说明 |
| --- | --- | --- |
| **① 无设计结果** | **0 行** | 同一个请求体（空体 `{}`）在 `CODE-ANAL` **之前** |
| **阳性参照** | `CODE-TABLE` > 0 行（实测 **36**） | 证明**设计结果真的在** |
| **③ 有设计结果** | **> 0 行**（实测 **2**） | ①→③ 的**差**才是效果（`200` 不判别任何东西） |

⚠️ **防回显**（**R157** 的仪器有效性）：取值**不得**等于手册 `json_schema` 的**示例值** ——
手册示例是 `vELEM.ELEM = 10` / `vSECT.RAT = 0.6119…`，而本模型**没有**单元 `10`
⇒ 响应回 `ELEM = 1` / `RAT = 8.0846…` ⇒ **不**是 schema 回显（**真的**读了本模型）。

⚠️ **本端点对 `Argument` 完全不敏感**（实测）：空体 `{}` / 自名 `TABLE_TYPE` /
**逐字照** `CODE-TABLE` 的体 / **伪** `TABLE_TYPE`，四者答复**逐字节同形**
⇒ 「坏取值被拦」这一**形态**的阴性对照**结构上不可用**（如实记录，**不**硬凑假对照）。
⇒ 本批改用**状态对照**（同一个请求体，无/有设计结果 ⇒ 0 行 / >0 行）—— 它**更贴**本端点语义。

本文件钉住的判据
----------------
1. **主指标 `71 / 73`**（被挡 **2** · 挡点端点 **4**；`--check` 退出码 0）；
2. 端点 `availability` 已 `untested → verified`（`verified_on: [gen-local]`）；
3. 证据里的**三段对照**全真：无设计 **0 行** → 有设计 **2 行**；阳性参照 **36 行**；
4. **防回显**成立（取值 ≠ 手册示例）；
5. **伪取值形态如实记为不可用**（`INCONCLUSIVE_BY_DESIGN`）—— **不**伪造成成立；
6. **零残留**：哨兵 **7** 项跑前/跑后一致；
7. `--attribution` 的 `ours` 现在**为空**（我方可拿下项**已全部收口**）。
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
"""仓库根目录。"""

TOOLS = REPO_ROOT / "registry" / "tools"
LIVE = REPO_ROOT / "registry" / "live"

EVIDENCE = LIVE / "steelcodecheck_probe.json"
"""本批的证据（**不含**凭据；只留状态码 / 行数 / 值指纹）。"""

PROBE_TOOL = TOOLS / "probe_steelcodecheck_p174.py"
"""本批的探针（`--probe` 有副作用 / `--check` 零请求）。"""

AVAILABILITY_TOOL = TOOLS / "check_operation_availability.py"
"""主指标 + 收益 + 归因的唯一裁定入口（**只读**）。"""

ENDPOINT_YAML = REPO_ROOT / "registry" / "products" / "gen_nx" / "post" / "STEELCODECHECK.yaml"
"""被收口的端点定义。"""

MANIFEST = REPO_ROOT / "registry" / "manifest.json"
"""端点索引（`availability` 的**落盘**处）。"""

README = REPO_ROOT / "README.md"
REGISTRY_README = REPO_ROOT / "registry" / "README.md"
DOCS_07 = REPO_ROOT / "docs" / "07_开发方案与任务续接_v1.0.md"

TARGET_ENDPOINT = "POST.STEELCODECHECK"
"""本批收口的端点。"""

UNLOCKED_OPERATION = "DESIGN.CODE_CHECK"
"""它挡住的 Operation（**R165** 算出的收益，本批**兑付**）。"""

EXPECTED_AVAILABLE = 71
EXPECTED_TOTAL = 73
EXPECTED_BLOCKED = ("DESIGN.CONCRETE", "DESIGN.SRC")
EXPECTED_BLOCKER_ENDPOINTS = 4

ROWS_WITHOUT_DESIGN = 0
"""**相 ①**：无设计结果时的行数（实测）。"""

ROWS_WITH_DESIGN = 2
"""**相 ③**：有设计结果时的行数（实测）。"""

CODE_TABLE_ROWS = 36
"""**阳性参照** `CODE-TABLE` 的行数（实测）。"""

MANUAL_SAMPLE_ELEM = 10
"""手册 `json_schema` 示例的 `vELEM.ELEM` —— 本模型**没有**这个单元（防回显判据）。"""

SENTINEL_COUNT = 7
"""零残留哨兵项数。"""


def _tool() -> Any:
    """装载主指标工具（**只读**）。"""
    spec = importlib.util.spec_from_file_location("_availability_p174", AVAILABILITY_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _evidence() -> dict[str, Any]:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def _manifest() -> dict[str, str]:
    rows = json.loads(MANIFEST.read_text(encoding="utf-8"))["endpoints"]
    return {str(row["key"]): str(row["availability"]) for row in rows}


# ===== 1. 主指标上抬 =====


def test_p174_the_main_indicator_moves_by_exactly_one() -> None:
    """门槛（**本批的核心结果**）：主指标 `68 / 71` → **`71 / 73`**（**+1**，正好一格）。"""
    document = _tool().compute()
    assert document["total"] == EXPECTED_TOTAL, document["total"]
    assert document["available"] == EXPECTED_AVAILABLE, document["available"]
    assert document["blocked"] == EXPECTED_TOTAL - EXPECTED_AVAILABLE, document["blocked"]
    assert set(document["blocked_operations"]) == set(EXPECTED_BLOCKED), sorted(
        document["blocked_operations"]
    )
    assert document["blocker_endpoint_count"] == EXPECTED_BLOCKER_ENDPOINTS, sorted(
        document["blocker_endpoints"]
    )


def test_p174_the_unlocked_operation_is_the_predicted_one() -> None:
    """门槛：解锁的**正是** `R165` 预测的那个（`DESIGN.CODE_CHECK`）—— **不**多不少。"""
    document = _tool().compute()
    assert UNLOCKED_OPERATION in document["available_operations"], document["available_operations"]
    # ⚠️ **只**它一个 —— 收口**一个**端点只能解锁**一个** Operation（**R165** 的收益 = 1）
    assert set(EXPECTED_BLOCKED) == set(document["blocked_operations"])


def test_p174_design_code_check_is_now_available() -> None:
    """门槛：`DESIGN.CODE_CHECK` 从**被挡**移到**可用**。"""
    document = _tool().compute()
    assert UNLOCKED_OPERATION in document["available_operations"]
    assert UNLOCKED_OPERATION not in document["blocked_operations"]
    # 它的**挡点端点**不再是挡点（钢铁路由的三步全通）
    assert TARGET_ENDPOINT not in document["blocker_endpoints"], document["blocker_endpoints"]


def test_p174_the_endpoint_is_marked_verified_in_the_registry() -> None:
    """门槛（**落盘**）：端点 YAML 与 `manifest.json` 都是 `verified` + `verified_on: [gen-local]`。

    ⚠️ 判据按**字段行**（`availability:` / `verified_on:` 开头的行），**不**按子串 ——
    头部注释里**故意**保留了 `untested → verified` 的**历史**表述（便于回溯）。
    """
    lines = [line for line in ENDPOINT_YAML.read_text(encoding="utf-8").splitlines()]
    fields = [line for line in lines if not line.lstrip().startswith("#")]
    assert "availability: verified" in fields, "端点 YAML 未收口"
    assert "verified_on: [gen-local]" in fields, "缺少实测实例溯源"
    assert not any(line.startswith("availability: untested") for line in fields), (
        "YAML 仍留 untested"
    )
    assert _manifest()[TARGET_ENDPOINT] == "verified", _manifest()[TARGET_ENDPOINT]


def test_p174_the_steel_route_is_fully_closed() -> None:
    """门槛（**R165 的收益成真**）：钢铁路由三步**全部** `VERIFIED`。"""
    sys.path.insert(0, str(REPO_ROOT))
    from app.infrastructure.adapters.midas.registry import (  # noqa: PLC0415
        VERIFIED,
        MidasRegistry,
    )

    registry = MidasRegistry.load(REPO_ROOT / "registry")
    keys = (
        "DESIGN.STEEL.KDS-41-30-2022.CODE-ANAL",
        "DESIGN.STEEL.KDS-41-30-2022.CODE-TABLE",
        TARGET_ENDPOINT,
    )
    statuses = [registry.resolve(key=key, product="GEN_NX").verification_status for key in keys]
    assert statuses == [VERIFIED, VERIFIED, VERIFIED], statuses


# ===== 2. 判据 = 效果（铁律 ⓪）=====


def test_p174_the_effect_criterion_is_row_count_not_status_code() -> None:
    """门槛（**铁律 ⓪**）：效果 = **行数**变化，`200` **不**判别任何东西。

    ⚠️ **本端点在两个相位上**都**回 `200`**（无设计结果 / 有设计结果）——
    若判据是状态码，**两个相位无法区分** ⇒ 那正是 P169 的教训。
    """
    rows = _evidence()["phase_no_design"] + _evidence()["phase_with_design"]
    assert rows, "证据里应有两个相位的记录"
    assert all(row["status"] == 200 for row in rows), [(r["label"], r["status"]) for r in rows]
    assert any(row["rows"] == 0 for row in rows), "应有 200 但 0 行的记录（⇒ 状态码不判别）"


def test_p174_the_state_control_holds() -> None:
    """门槛（**可用的阴性对照**）：**同一个**请求体 —— 无设计 **0 行** → 有设计 **2 行**。"""
    control = _evidence()["state_control"]
    assert control["valid"] is True, control
    assert control["rows_without_design"] == ROWS_WITHOUT_DESIGN, control
    assert control["rows_with_design"] == ROWS_WITH_DESIGN, control


def test_p174_the_positive_reference_has_rows() -> None:
    """门槛（**阳性参照有效**）：`CODE-TABLE` 有 **36** 行 ⇒ 「设计结果真的在」成立。

    ⚠️ 没有这条，「相 ③ 有 2 行」可能只是**别的**来源（而非本模型的设计结果）。
    """
    table = _evidence()["positive_reference_code_table"]
    assert table["status"] == 200, table
    assert table["rows"] == CODE_TABLE_ROWS, table
    assert "Result Table" in table["roots"], table


def test_p174_the_result_shape_carries_both_roots() -> None:
    """门槛：结果块**真的**带 `vSECT` 与 `vELEM` 两个根（与手册声明的结果形状一致）。"""
    effect = _evidence()["effect"]
    assert effect["roots"] == ["vELEM", "vSECT"], effect["roots"]
    assert effect["rows_with_design"] == ROWS_WITH_DESIGN, effect


# ===== 3. 防回显（R157 的仪器有效性）=====


def test_p174_the_values_are_not_a_schema_echo() -> None:
    """门槛（**R157**）：取值**不**等于手册 `json_schema` 的**示例值** ⇒ **不**是静态回显。

    ⚠️ 这是本批**最硬**的一条：它把「端点真的读了模型」与「端点回了手册样例」**区分开**。
    手册示例 `vELEM.ELEM = 10`，而本模型**没有**单元 `10`（只有单元 `1`）。
    """
    echo = _evidence()["echo_control"]
    assert echo["valid"] is True, echo
    assert echo["echoes_manual"] is False, echo
    assert echo["manual_sample_elem"] == MANUAL_SAMPLE_ELEM, echo
    fingerprint = echo["observed_fingerprint"]
    assert fingerprint, "应有值指纹"
    elems = [row.get("ELEM") for row in fingerprint if "ELEM" in row]
    assert elems == [1], f"应回本模型的单元 1（而不是手册示例的 10）：{elems}"
    # 各条 `RAT` 都不等于手册示例值
    manual_rat = echo["manual_sample_rat"]
    assert all(abs(float(row["RAT"]) - manual_rat) > 1e-6 for row in fingerprint if "RAT" in row)


# ===== 4. 伪取值形态**如实记为不可用** =====


def test_p174_the_negative_control_is_recorded_as_inconclusive() -> None:
    """门槛（**诚实边界**）：伪取值与合法体**逐字节同形** ⇒ 该形态的对照**不成立**。

    ⚠️ **不**得伪造成「伪取值被拦」—— 本端点**不**校验 `Argument`
    （且它的 Schema **没有** `properties` ⇒ `spec_guard` 也**一个字段都不检查**，**R165**）。
    """
    negative = _evidence()["negative_control"]
    assert negative["verdict"] == "INCONCLUSIVE_BY_DESIGN", negative
    assert negative["status"] == 200, negative
    # 伪取值**确实**产出了与合法体相同的行数（这就是「不可用」的证据）
    assert negative["rows"] == ROWS_WITH_DESIGN, negative


def test_p174_the_three_candidates_agree() -> None:
    """门槛：三个候选体（空体 / 自名 / 照 `CODE-TABLE`）在**同一相位**上答复一致。

    ⇒ 本端点**不**吃 `Argument` ⇒ 生产路径用**最小体**即可（**不**臆造字段，**R151**）。
    """
    rows = _evidence()["phase_with_design"]
    assert len(rows) == 3, [r["label"] for r in rows]
    assert {row["rows"] for row in rows} == {ROWS_WITH_DESIGN}, rows
    assert {tuple(row["roots"]) for row in rows} == {("vELEM", "vSECT")}, rows


# ===== 5. 零残留 =====


def test_p174_zero_residue() -> None:
    """门槛（**零残留**）：哨兵 **7** 项跑前/跑后一致。"""
    sentinel = _evidence()["sentinel"]
    assert sentinel["unchanged"] is True, sentinel
    assert len(sentinel["keys"]) == SENTINEL_COUNT, sentinel["keys"]
    assert sentinel["before"] == sentinel["after"], (sentinel["before"], sentinel["after"])


def test_p174_only_the_self_built_project_was_touched() -> None:
    """门槛（**副作用受控**）：证据里的项目路径是本工具**自建**的 `.tmp_p164c/*.mgbx`。"""
    project = _evidence()["project"]
    assert project.startswith(".tmp_p164c/"), project
    assert project.endswith(".mgbx"), project


# ===== 6. 归因视图已反映收口 =====


def test_p174_the_attribution_has_no_ours_left() -> None:
    """门槛（**R166 的归因随收口更新**）：`gate_attribution()["ours"]` 现在**为空**。

    ⚠️ 收口前是 `["POST.STEELCODECHECK"]`（我方唯一杠杆）—— 那**算对了**，且已**兑付**。
    """
    table = _tool().gate_attribution()
    assert table["ours"] == [], table["ours"]
    assert len(table["midas"]) == EXPECTED_BLOCKER_ENDPOINTS, table["midas"]


# ===== 7. 工具与文档 =====


def test_p174_the_probe_offline_check_passes() -> None:
    """门槛：探针 `--check` 退出码 0（**零请求**）。"""
    result = subprocess.run(
        [sys.executable, str(PROBE_TOOL), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p174_the_metric_tools_pass_on_the_command_line() -> None:
    """门槛：`--check` / `--benefit` / `--attribution` 退出码 0，且报 `71 / 73`。"""
    for flag in ("--check", "--benefit", "--attribution"):
        result = subprocess.run(
            [sys.executable, str(AVAILABILITY_TOOL), flag],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(REPO_ROOT),
            check=False,
        )
        assert result.returncode == 0, flag + "\n" + result.stdout + result.stderr
    checked = subprocess.run(
        [sys.executable, str(AVAILABILITY_TOOL), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert "71 / 73" in checked.stdout, checked.stdout


def test_p174_the_docs_carry_the_new_number() -> None:
    """门槛（**文档口径**）：`README.md` / `registry/README.md` / `docs/07` 都已更正。"""
    readme = README.read_text(encoding="utf-8")
    registry = REGISTRY_README.read_text(encoding="utf-8")
    docs = DOCS_07.read_text(encoding="utf-8")
    assert "**`71 / 73`**" in readme, "README §1.1 必须写 71 / 73"
    assert "R166" in readme, "README 必须可回溯到 R166"
    assert "8.29" in registry, "registry/README 必须有 §8.29（本批的记录）"
    assert "R166" in docs, "docs/07 必须登记 R166"
    # ⚠️ 时点记录不篡改：R152 / R165 的行仍在
    assert "**R165**" in docs
    assert "**R152**" in docs


def test_p174_the_crash_family_guard_is_intact() -> None:
    """门槛（**R154 红线未被本批破坏**）：崩溃族仍含 **11** 个端点，`BD-ANAL` 仍是**实测**的。"""
    sys.path.insert(0, str(REPO_ROOT))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        NATIVE_CRASH_ENDPOINTS,
        NATIVE_CRASH_MEASURED,
    )

    assert len(NATIVE_CRASH_ENDPOINTS) == 11, sorted(NATIVE_CRASH_ENDPOINTS)
    assert NATIVE_CRASH_MEASURED == frozenset({"DESIGN.RC.KDS-41-20-2022.BD-ANAL"}), (
        NATIVE_CRASH_MEASURED
    )
    # 本批收口的端点**不**在崩溃族里（它从来不是）
    assert TARGET_ENDPOINT not in NATIVE_CRASH_ENDPOINTS
