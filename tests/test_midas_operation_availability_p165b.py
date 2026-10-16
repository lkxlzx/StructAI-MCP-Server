"""P165-b / **R158** + P166 / **R159** + P167 / **R160**：**主指标可执行化** ——
生产路径可用 Operation。

指标怎么来的
-----------
`README.md` §1.1 的 `62 / 71` 曾是**手写**的，于是漂了：它把 `DESIGN.CODE_CHECK` 算成**可用**，
而该 Operation 的 **7 条路由全部被挡**（`steel` 的末步 `POST.STEELCODECHECK` 是 `PARTIAL`；
`concrete:*` 需 `BD/CD/BRD/WD-ANAL`（**原生崩溃护栏**）；`src:*` 需 `SRC.{BC,CC}-ANAL`（同））。
⇒ **R158** 定真实值 = **61 / 71**：被挡 **10** 个 Operation、挡点端点 **15** 个。

**R159（P166）**：`VIEW.RESULTGRAPHIC` 的**纯 API 进结果视图（post）路径**实测找到
（成因 = 原请求体缺 `TYPE_OF_DISPLAY`）⇒ 该端点 `untested → verified`
⇒ 它挡住的 **6** 个 `VIEW.*` Operation **解锁** ⇒ **67 / 71**（被挡 **4** · 挡点端点 **14**）。

**R160（P167）**：`POST.TABLE` 的 `TABLE_TYPE` 枚举收口（来源换成「登记表 ∪ 手册声明」
两个**可复算**来源的并集）⇒ 该端点 `untested → verified` ⇒ 它挡住的 **1** 个 Operation
（`RESULT.ANALYSIS.SUMMARY`，**通用取表入口**）**解锁**
⇒ **68 / 71**（被挡 **3** · 挡点端点 **13**）。

**R166（P174）**：`POST.STEELCODECHECK` **真机实测**收口（判据 = **效果**：无设计结果 **0 行**
→ 有设计结果 **2 行** ∧ 取值**不**等于手册 schema 示例）⇒ 它挡住的 **1** 个 Operation
（`DESIGN.CODE_CHECK`，钢铁路由）**解锁**
⇒ **69 / 71**（被挡 **2** · 挡点端点 **4**）。
⚠️ 节标题 `P165b` 是**时点记录**（不改）；本文件的**裁定值**随每个收口批次上抬。

**手写的指标必然漂** ⇒ 本文件把**裁定值**钉住 —— 改主指标必须同时改
`README.md` §1.1 / §5.1 与 `docs/07` §16.1 的裁决（R158 / R159 / R160 / **R166**）。
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

TOOL = REPO_ROOT / "registry" / "tools" / "check_operation_availability.py"
"""主指标工具（只读；`--check` 零请求）。"""

README = REPO_ROOT / "README.md"
"""主指标的手写落点。"""

DOCS_07 = REPO_ROOT / "docs" / "07_开发方案与任务续接_v1.0.md"
"""裁决表（§16.1）。"""

EXPECTED_AVAILABLE = 69
EXPECTED_TOTAL = 71
EXPECTED_BLOCKER_ENDPOINTS = 4
EXPECTED_BLOCKED = (
    "DESIGN.CONCRETE",
    "DESIGN.SRC",
)
"""已裁定的被挡 Operation（**2** 个；R158 为 10，R159 解锁 6 个 `VIEW.*`，
R160 解锁 1 个 `RESULT.ANALYSIS.SUMMARY`，**R166 解锁 1 个 `DESIGN.CODE_CHECK`**）。"""

UNLOCKED_BY_R159 = (
    "VIEW.DEFORMED_MODEL",
    "VIEW.DISPLACEMENT",
    "VIEW.FORCE",
    "VIEW.MODE_SHAPE",
    "VIEW.REACTION",
    "VIEW.STRESS",
)
"""**R159** 由 `VIEW.RESULTGRAPHIC` 收口而解锁的 **6** 个 Operation。"""

UNLOCKED_BY_R160 = ("RESULT.ANALYSIS.SUMMARY",)
"""**R160** 由 `POST.TABLE` 收口而解锁的 **1** 个 Operation（**通用取表入口**）。"""

ENDPOINT_FREE = ("DESIGN.FOUNDATION", "DESIGN.OPTIMIZE")
"""无 MIDAS 端点的 Operation —— **不**因端点被挡（口径第 2 条）。"""


def _load_tool() -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location("check_operation_availability", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p165b_the_main_indicator_matches_the_ruling() -> None:
    """门槛（**主指标**）：生产路径可用 Operation = **69 / 71**（**R166** 收口后）。"""
    document = _load_tool().compute()
    assert document["total"] == EXPECTED_TOTAL, document["total"]
    assert document["available"] == EXPECTED_AVAILABLE, document["available"]
    assert document["blocked"] == EXPECTED_TOTAL - EXPECTED_AVAILABLE, document["blocked"]
    assert set(document["blocked_operations"]) == set(EXPECTED_BLOCKED), sorted(
        document["blocked_operations"]
    )


def test_p165b_the_blocker_endpoint_count_matches_the_ruling() -> None:
    """门槛：挡点端点 **4** 个（R158 为 15；R159 移除 `VIEW.RESULTGRAPHIC`；
    R160 移除 `POST.TABLE`；**R166** 移除 `POST.STEELCODECHECK`）。"""
    document = _load_tool().compute()
    assert document["blocker_endpoint_count"] == EXPECTED_BLOCKER_ENDPOINTS, sorted(
        document["blocker_endpoints"]
    )
    # R159：`VIEW.RESULTGRAPHIC` **不再**是挡点；它挡过的 6 个 Operation 已可用
    assert "VIEW.RESULTGRAPHIC" not in document["blocker_endpoints"], document["blocker_endpoints"]
    for name in UNLOCKED_BY_R159:
        assert name in document["available_operations"], name
        assert name not in document["blocked_operations"], name
    # R160：`POST.TABLE` **不再**是挡点；它挡过的 1 个 Operation 已可用
    assert "POST.TABLE" not in document["blocker_endpoints"], document["blocker_endpoints"]
    for name in UNLOCKED_BY_R160:
        assert name in document["available_operations"], name
        assert name not in document["blocked_operations"], name


def test_p165b_the_remaining_blockers_are_split_by_recovery_condition() -> None:
    """门槛（**R166 收口后的边界**）：剩余 **4** 个挡点端点**全部**可归因到崩溃边。

    * **实测 / 同族推定的崩溃族**（`NATIVE_CRASH_ENDPOINTS`，**R154**）= **2** 个 `*-ANAL`
      ⇒ 恢复条件 = **MIDAS 侧**修 `wg_db.dll`；
    * **其余 2 个** `*-TABLE` = `availability` 未收口，但**要先有设计结果**
      ⇒ 那结果**只能由**同选项里的崩溃族 `*-ANAL` 产出（**R166**）⇒ 卡在**同一条**崩溃边。
    ⚠️ **R166**：`POST.STEELCODECHECK` **已收口**（不再是挡点）。

    ⚠️ **不**声称「全部在崩溃族里」—— 那是**错的**（本用例就是把它钉住）。
    """
    document = _load_tool().compute()
    sys.path.insert(0, str(REPO_ROOT))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        NATIVE_CRASH_ENDPOINTS,
    )

    endpoints = set(document["blocker_endpoints"])
    crash = sorted(endpoints & set(NATIVE_CRASH_ENDPOINTS))
    rest = sorted(endpoints - set(NATIVE_CRASH_ENDPOINTS))
    assert len(crash) == 2 and all(key.endswith("-ANAL") for key in crash), crash
    assert rest == [
        "DESIGN.RC.KDS-41-20-2022.BD-TABLE",
        "DESIGN.SRC.AIK-SRC2K.BC-TABLE",
    ], rest
    # 非崩溃族的那 2 个 `*-TABLE`：`availability` 仍是 `untested`（要设计先跑起来）
    # ⇒ 而那「设计结果」**只能由**崩溃族 `*-ANAL` 产出（**R166**）⇒ 卡在**同一条**崩溃边。
    manifest = json.loads((REPO_ROOT / "registry" / "manifest.json").read_text(encoding="utf-8"))[
        "endpoints"
    ]
    availability = {str(row["key"]): str(row["availability"]) for row in manifest}
    for key in rest:
        assert availability[key] == "untested", (key, availability[key])
    # **R166**：`POST.STEELCODECHECK` 已**实测收口** ⇒ 不再是挡点（且 `verified`）
    assert "POST.STEELCODECHECK" not in endpoints, endpoints
    assert availability["POST.STEELCODECHECK"] == "verified", availability["POST.STEELCODECHECK"]


def test_p165b_the_endpoint_free_operations_are_not_counted_as_blocked() -> None:
    """门槛（口径第 2 条）：无 MIDAS 端点的 Operation **不**因端点被挡。"""
    document = _load_tool().compute()
    assert tuple(document["endpoint_free_operations"]) == ENDPOINT_FREE, document[
        "endpoint_free_operations"
    ]
    for name in ENDPOINT_FREE:
        assert name in document["available_operations"], name
        assert name not in document["blocked_operations"], name


def test_p165b_only_the_steel_route_of_design_code_check_is_clean() -> None:
    """门槛（**R158 的成因 ⇒ R166 已解**）：`DESIGN.CODE_CHECK` 现在**恰好一条**路由可用。

    ⚠️ **R158 时**：**每一条**路由都有挡点（这是「62 → 61」的**唯一**成因 ——
    README 旧值把它当成可用）。**R166（P174）**：`POST.STEELCODECHECK` **实测收口**
    ⇒ **钢铁路由全通** ⇒ 该 Operation 解锁。
    ⇒ 本用例**从「全部被挡」改为「恰好钢铁路由可用」** —— 是**事实变更**，**不是**放宽断言：
    它仍然**逐条**复算每条路由，且**要求**其余 **6** 条路由**仍然**有挡点。
    """
    sys.path.insert(0, str(REPO_ROOT))
    from app.infrastructure.adapters.midas.operations import plan_for  # noqa: PLC0415
    from app.infrastructure.adapters.midas.registry import (  # noqa: PLC0415
        VERIFIED,
        MidasRegistry,
    )

    registry = MidasRegistry.load(REPO_ROOT / "registry")
    plan = plan_for("DESIGN.CODE_CHECK")
    assert plan is not None and plan.routes, "CODE_CHECK 应当有路由"
    clean: list[str] = []
    for name, steps in plan.routes.items():
        if all(
            registry.resolve(key=step.key, product="GEN_NX", method=step.method).verification_status
            == VERIFIED
            for step in steps
        ):
            clean.append(name)
    assert clean == ["steel"], f"应**恰好**钢铁路由可用：{clean}"
    # **R166**：钢铁路由的末步 `POST.STEELCODECHECK` 现在**是** `VERIFIED`（本批收口）
    steel = registry.resolve(key="POST.STEELCODECHECK", product="GEN_NX")
    assert steel.verification_status == VERIFIED, steel.verification_status
    # ⚠️ 其余 6 条路由（concrete:* / src:*）**仍**被崩溃族挡着 ⇒ 不许悄悄变可用
    assert len(plan.routes) == 7, sorted(plan.routes)


def test_p165b_the_offline_check_passes() -> None:
    """门槛：`--check` 退出码 0（零请求）。"""
    result = subprocess.run(
        [sys.executable, str(TOOL), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "69 / 71" in result.stdout, result.stdout


def test_p165b_the_readme_and_the_ruling_carry_the_corrected_number() -> None:
    """门槛：`README.md` 与 `docs/07` 都已更正（**只改现状声称**，不篡改历史）。

    ⚠️ 判据是「**不再把旧值当成现状**」而不是「全文不出现旧值」——
    更正说明里**必须**保留旧值（否则读者不知道改了什么）。
    """
    readme = README.read_text(encoding="utf-8")
    # 旧的**现状声称**（加粗的形式）必须消失
    assert "**`62 / 71`**" not in readme, "README 仍把 62/71 当成现状"
    assert "**`61 / 71`**" not in readme, "README 仍把 61/71 当成现状（R159 后应为 67/71）"
    assert "**`67 / 71`**" not in readme, "README 仍把 67/71 当成现状（R160 后应为 68/71）"
    # ⚠️ **R166**：`68 / 71` 现在也是**历史值** ⇒ 不得再作**现状声称**（但必须保留便于对照）
    assert "**`69 / 71`**" in readme, "README 必须写明更正后的 69/71"
    assert "`62 / 71`" in readme, "更正说明里应保留旧值 62，便于对照"
    assert "`61 / 71`" in readme, "更正说明里应保留旧值 61，便于对照"
    assert "`67 / 71`" in readme, "更正说明里应保留旧值 67，便于对照"
    assert "`68 / 71`" in readme, "更正说明里应保留旧值 68，便于对照"
    assert "R158" in readme and "R159" in readme and "R160" in readme, "更正必须可回溯到裁决编号"
    assert "R166" in readme, "R166 必须可回溯"
    assert "check_operation_availability.py" in readme, "README 必须指向可执行判定"
    docs = DOCS_07.read_text(encoding="utf-8")
    assert "**R158**" in docs, "R158 必须登记"
    assert "**R159**" in docs, "R159 必须登记"
    assert "**R160**" in docs, "R160 必须登记"
    assert "check_operation_availability.py" in docs, "裁决里必须留下可复算的工具"
