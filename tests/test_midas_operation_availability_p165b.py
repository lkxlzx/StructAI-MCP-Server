"""P165-b / **R158** + P166 / **R159**：**主指标可执行化** —— 生产路径可用 Operation。

指标怎么来的
-----------
`README.md` §1.1 的 `62 / 71` 曾是**手写**的，于是漂了：它把 `DESIGN.CODE_CHECK` 算成**可用**，
而该 Operation 的 **7 条路由全部被挡**（`steel` 的末步 `POST.STEELCODECHECK` 是 `PARTIAL`；
`concrete:*` 需 `BD/CD/BRD/WD-ANAL`（**原生崩溃护栏**）；`src:*` 需 `SRC.{BC,CC}-ANAL`（同））。
⇒ **R158** 定真实值 = **61 / 71**：被挡 **10** 个 Operation、挡点端点 **15** 个。

**R159（P166）**：`VIEW.RESULTGRAPHIC` 的**纯 API 进结果视图（post）路径**实测找到
（成因 = 原请求体缺 `TYPE_OF_DISPLAY`）⇒ 该端点 `untested → verified`
⇒ 它挡住的 **6** 个 `VIEW.*` Operation **解锁** ⇒ **67 / 71**（被挡 **4** · 挡点端点 **14**）。

**手写的指标必然漂** ⇒ 本文件把**裁定值**钉住 —— 改主指标必须同时改
`README.md` §1.1 / §5.1 与 `docs/07` §16.1 的裁决（R158 / R159）。
"""

from __future__ import annotations

import importlib.util
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

EXPECTED_AVAILABLE = 67
EXPECTED_TOTAL = 71
EXPECTED_BLOCKER_ENDPOINTS = 14
EXPECTED_BLOCKED = (
    "DESIGN.CODE_CHECK",
    "DESIGN.CONCRETE",
    "DESIGN.SRC",
    "RESULT.ANALYSIS.SUMMARY",
)
"""已裁定的被挡 Operation（**4** 个；R158 为 10，R159 解锁了 6 个 `VIEW.*`）。"""

UNLOCKED_BY_R159 = (
    "VIEW.DEFORMED_MODEL",
    "VIEW.DISPLACEMENT",
    "VIEW.FORCE",
    "VIEW.MODE_SHAPE",
    "VIEW.REACTION",
    "VIEW.STRESS",
)
"""**R159** 由 `VIEW.RESULTGRAPHIC` 收口而解锁的 **6** 个 Operation。"""

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
    """门槛（**主指标**）：生产路径可用 Operation = **67 / 71**（R159 收口后）。"""
    document = _load_tool().compute()
    assert document["total"] == EXPECTED_TOTAL, document["total"]
    assert document["available"] == EXPECTED_AVAILABLE, document["available"]
    assert document["blocked"] == EXPECTED_TOTAL - EXPECTED_AVAILABLE, document["blocked"]
    assert set(document["blocked_operations"]) == set(EXPECTED_BLOCKED), sorted(
        document["blocked_operations"]
    )


def test_p165b_the_blocker_endpoint_count_matches_the_ruling() -> None:
    """门槛：挡点端点 **14** 个（R158 为 15；R159 移除了 `VIEW.RESULTGRAPHIC`）。"""
    document = _load_tool().compute()
    assert document["blocker_endpoint_count"] == EXPECTED_BLOCKER_ENDPOINTS, sorted(
        document["blocker_endpoints"]
    )
    # R159：`VIEW.RESULTGRAPHIC` **不再**是挡点；它挡过的 6 个 Operation 已可用
    assert "VIEW.RESULTGRAPHIC" not in document["blocker_endpoints"], document["blocker_endpoints"]
    for name in UNLOCKED_BY_R159:
        assert name in document["available_operations"], name
        assert name not in document["blocked_operations"], name


def test_p165b_the_endpoint_free_operations_are_not_counted_as_blocked() -> None:
    """门槛（口径第 2 条）：无 MIDAS 端点的 Operation **不**因端点被挡。"""
    document = _load_tool().compute()
    assert tuple(document["endpoint_free_operations"]) == ENDPOINT_FREE, document[
        "endpoint_free_operations"
    ]
    for name in ENDPOINT_FREE:
        assert name in document["available_operations"], name
        assert name not in document["blocked_operations"], name


def test_p165b_every_route_of_design_code_check_is_blocked() -> None:
    """门槛（**R158 的成因**）：`DESIGN.CODE_CHECK` 的**每一条**路由都有挡点。

    ⚠️ 这是「62 → 61」的**唯一**成因：README 旧值把它当成可用。
    R159 解锁的是 `VIEW.*`，与它无关 ⇒ 这条**必须**仍然成立。
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
    assert clean == [], f"出现了可用的路由 ⇒ 67 要重算：{clean}"
    # 关键一条：钢铁路由的**末步** `POST.STEELCODECHECK` 仍是 `PARTIAL`
    steel = registry.resolve(key="POST.STEELCODECHECK", product="GEN_NX")
    assert steel.verification_status != VERIFIED, steel.verification_status


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
    assert "67 / 71" in result.stdout, result.stdout


def test_p165b_the_readme_and_the_ruling_carry_the_corrected_number() -> None:
    """门槛：`README.md` 与 `docs/07` 都已更正（**只改现状声称**，不篡改历史）。

    ⚠️ 判据是「**不再把旧值当成现状**」而不是「全文不出现旧值」——
    更正说明里**必须**保留旧值（否则读者不知道改了什么）。
    """
    readme = README.read_text(encoding="utf-8")
    # 旧的**现状声称**（加粗的形式）必须消失
    assert "**`62 / 71`**" not in readme, "README 仍把 62/71 当成现状"
    assert "**`61 / 71`**" not in readme, "README 仍把 61/71 当成现状（R159 后应为 67/71）"
    assert "**`67 / 71`**" in readme, "README 必须写明更正后的 67/71"
    assert "`62 / 71`" in readme, "更正说明里应保留旧值 62，便于对照"
    assert "`61 / 71`" in readme, "更正说明里应保留旧值 61，便于对照"
    assert "R158" in readme and "R159" in readme, "更正必须可回溯到裁决编号"
    assert "check_operation_availability.py" in readme, "README 必须指向可执行判定"
    docs = DOCS_07.read_text(encoding="utf-8")
    assert "**R158**" in docs, "R158 必须登记"
    assert "**R159**" in docs, "R159 必须登记"
    assert "check_operation_availability.py" in docs, "裁决里必须留下可复算的工具"
