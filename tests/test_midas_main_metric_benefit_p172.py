"""P172 / **R165**：把**主指标**（3 个被挡 Operation / 13 个挡点端点）推到底。

本批的**唯一**新发现：**收益映射本身**也曾是**手写**的，于是漂了
--------------------------------------------------------------
`docs/reports/P160e-a_收益映射与POST.TABLE留缺R151_v1.0.md` §1 的「分组收益」表把
`POST.STEELCODECHECK` 记成「**0**（单独收口**不**解锁）」，理由是
「`DESIGN.CODE_CHECK` 还需要 12 个 RC/SRC 端点」。

⚠️ 那句话**把口径读反了**：`check_operation_availability.py` 的**口径第 4 条**写着
「`routes` 是**替代**路线 ⇒ **至少一条**全通即不算被挡」—— 是 **OR**，不是 **AND**。
`DESIGN.CODE_CHECK` 的 `steel` 路由**只有**末步（`POST.STEELCODECHECK`）未收口
（`CODE-ANAL` / `CODE-TABLE` 都已是 `VERIFIED`）⇒ **收口它就解锁 `DESIGN.CODE_CHECK`**。

⇒ 与 **R158** 是**同一类**教训：**手写的指标必然漂**（那次漂的是主指标本身，
这次漂的是**收益映射**）⇒ 本批把它变成**可执行判定**（`benefit_mapping()` +
`minimal_unlock_cost()` + `--benefit` + `EXPECTED_BENEFIT` / `EXPECTED_MINIMAL_COST`）。

⚠️ **本批**零请求**（`gen-local` 实例当时**被 IPv4 探针误判为不可达** —— TCP `127.0.0.1:3030`
**refused**；⚠️ **R167（P174）** 已更正：该实例**只**监听 `::1`，用 `localhost` 一直可达）
⇒ `POST.STEELCODECHECK` 的 `availability` 当时**不变**（仍 `untested`）⇒ 当时主指标仍 `68 / 71`。
本批的价值在**算准收益**与**更正口径**。

🛑 **R166（P174，本文件的下游）**：本批算出的「**收益 +1**」**已经真机兑付** ——
`POST.STEELCODECHECK` 由 `untested` **实测**收口为 `verified` ⇒ 主指标 **`68 / 71` → `69 / 71`**。
⇒ ⚠️ 因此本文件里那些「**主指标不变**」「**恰好 1 个端点有边际收益**」的**现状**断言
**已随收口失效**（它们当时是对的）；本文件现在把它们改为**下游真相**，
但**保留**本批的**方法学**断言（收益映射由 `compute()` 复算、**不**手写）。

本文件钉住的判据
----------------
1. **主指标（R166 收口后）**：`69 / 71` · 被挡 **2** · 挡点端点 **4**（`--check` 退出码 0）；
2. **收益映射可复算**：`benefit_mapping()` 逐端点给出解锁集，**全部由 `compute()` 复算**；
   ⚠️ 收口后**没有**任何端点有边际收益（`zero_benefit` = 那 **4** 个）；
   **历史**：`POST.STEELCODECHECK` 曾是唯一的 `['DESIGN.CODE_CHECK']`（**本批算对的**）；
3. **最小解锁代价**：`DESIGN.CONCRETE` = **2** · `DESIGN.SRC` = **2** · **全部** = **4**
   （**不**是挡点个数 —— 收口前 13、收口后 4，而「全部」代价**始终**是 4）；
   **历史**：`DESIGN.CODE_CHECK` 当时 = **1**（已收口）；
4. **「零边际收益」≠「没用」**：那 4 个**成组**才有收益（`DESIGN.CONCRETE` 的 2 个
   收口 ⇒ 可用 **70**），故**不**能逐个判死；
5. **「值不值」的**代价**那一半**：该端点的**请求体来源**在本仓**不成立** ——
   手册条目的 `sections_present` **没有** `Request Examples` / `Response Examples`
   （**13** 个挡点端点里**唯一**缺的），且手册的 `json_schema` 根键 = `vSECT` / `vELEM`
   （规格表描述的是 Combined Strength Ratio / Slenderness Ratio / Deflection ⇒ **结果量**）
   ⇒ 那是**响应**形状；我们落盘的 Schema 与它**逐字节同形**且**没有** `properties`
   ⇒ `spec_guard` **一个字段都不检查**；
   ⚠️ **阳性对照**：**已**收口的 `POST.TABLE` / `POST.TEXT` **都**有 `Request Examples`
   ⇒ 「缺示例」**不是**手册的普遍形态（**R157 的方法学**：没有阳性对照的「缺失」不算证据）；
6. **文档口径已更正**：`README.md` §5.1 与 `docs/07` §16.1 **R165** 都不再把
   `POST.STEELCODECHECK` 说成「不解锁」；
7. **零请求**：本批**没有**新增任何 `*_probe.json`。
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

AVAILABILITY_TOOL = TOOLS / "check_operation_availability.py"
"""主指标 + 收益映射的唯一裁定入口（**只读**，`--check` / `--benefit` 零请求）。"""

README = REPO_ROOT / "README.md"
DOCS_07 = REPO_ROOT / "docs" / "07_开发方案与任务续接_v1.0.md"

EXPECTED_AVAILABLE = 69
"""⚠️ **R166（P174）**：本批（P172）时是 **68** —— `POST.STEELCODECHECK` 收口后 **+1**。"""
EXPECTED_TOTAL = 71
EXPECTED_BLOCKED = ("DESIGN.CONCRETE", "DESIGN.SRC")
"""⚠️ **R166（P174）**：本批（P172）时是 **3** 个（含 `DESIGN.CODE_CHECK`）—— 现已解锁。"""

R152_WRONG_ENDPOINT = "POST.STEELCODECHECK"
"""**R152** 把它记成「收益 0」的那个端点 —— 本批**更正**为 **+1**。"""

STEEL_ROUTE = (
    "DESIGN.STEEL.KDS-41-30-2022.CODE-ANAL",
    "DESIGN.STEEL.KDS-41-30-2022.CODE-TABLE",
    "POST.STEELCODECHECK",
)
"""`DESIGN.CODE_CHECK` 的 `steel` 路由（**逐字**照 `operations.py`）——
前 **2** 步**已** `VERIFIED` ⇒ **只有**末步挡着（这就是「收益 = 1」的成因）。"""

ZERO_MARGINAL = (
    "DESIGN.RC.KDS-41-20-2022.BD-ANAL",
    "DESIGN.RC.KDS-41-20-2022.BD-TABLE",
    "DESIGN.SRC.AIK-SRC2K.BC-ANAL",
    "DESIGN.SRC.AIK-SRC2K.BC-TABLE",
)
"""单独收口 ⇒ 边际收益 **0** 的**当前**端点（⚠️ **不**等于「没用」—— 它们**成组**才有收益）。

⚠️ **R166（P174）**：本批（P172）时是 **12** 个 —— 收口 `POST.STEELCODECHECK` 后，
`DESIGN.CODE_CHECK` 解锁 ⇒ 它的 **concrete:\\*** / **src:\\*** 路线**不再计入挡点**
⇒ 只剩 **4** 个（`DESIGN.CONCRETE` 与 `DESIGN.SRC` 各自的最短选项）。
"""


def _load(path: pathlib.Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tool() -> Any:
    """主指标工具（**每次**新装 —— 避免模块级状态串味）。"""
    return _load(AVAILABILITY_TOOL, "check_operation_availability_p172")


# ===== 1. 主指标不变 =====


def test_p172_the_main_metric_after_the_r166_closure() -> None:
    """门槛（**R166 收口后**）：`69 / 71` · 被挡 **2** · 挡点端点 **4**。

    ⚠️ 本批（P172）当时钉的是 `68 / 71`（实例被 IPv4 探针误判为不可达 ⇒ 零请求 ⇒ 不动主指标）。
    **R166（P174）** 用**真机实测**收口 `POST.STEELCODECHECK` ⇒ 主指标上抬 **+1**。
    ⚠️ 本用例现在钉**收口后**的真相；若有人偷偷改 `availability`，它**先红**。
    """
    tool = _tool()
    document = tool.compute()
    assert document["total"] == EXPECTED_TOTAL, document["total"]
    assert document["available"] == EXPECTED_AVAILABLE, document["available"]
    assert set(document["blocked_operations"]) == set(EXPECTED_BLOCKED), sorted(
        document["blocked_operations"]
    )
    assert document["blocker_endpoint_count"] == 4, sorted(document["blocker_endpoints"])
    assert tool.check() == 0


# ===== 2. 收益映射可复算（本批的**核心**更正）=====


def test_p172_the_steel_route_is_now_fully_closed() -> None:
    """门槛（**R166 收口后**）：`steel` 路由**三步全通**。

    ⚠️ 本批（P172）时末步是 `PARTIAL` ⇒ 「收益 = **1**」的成因就是**它**。
    **R166（P174）** 把末步**实测**收口 ⇒ 本用例改为钉「**全通**」。
    """
    sys.path.insert(0, str(REPO_ROOT))
    from app.infrastructure.adapters.midas.registry import (  # noqa: PLC0415
        VERIFIED,
        MidasRegistry,
    )

    registry = MidasRegistry.load(REPO_ROOT / "registry")
    statuses = [
        registry.resolve(key=key, product="GEN_NX").verification_status for key in STEEL_ROUTE
    ]
    assert statuses == [VERIFIED, VERIFIED, VERIFIED], statuses


def test_p172_r166_realized_the_prediction() -> None:
    """门槛（**本批的预测已被下游兑付**）：收口 `POST.STEELCODECHECK` ⇒ 解锁 `DESIGN.CODE_CHECK`。

    ⚠️ **R152 的「0」是错的** —— 它把 `routes` 的**替代**语义（OR）读成了 AND。
    ⚠️ 本批的 `pretend_verified` **仿真**已在 **R166（P174）** 用**真机实测**兑现
    ⇒ 现在 `DESIGN.CODE_CHECK` **真的**在 `available_operations` 里
    （**不**再需要仿真），且**被挡数**已含它的解锁。
    """
    tool = _tool()
    base = tool.compute()
    assert "DESIGN.CODE_CHECK" in base["available_operations"], "R166 已解锁它"
    assert "DESIGN.CODE_CHECK" not in base["blocked_operations"], base["blocked_operations"]
    # 仿真「收口末步」（已收口 ⇒ 幂等）⇒ 结果不变（**真的**兑付了，不是还在等）
    after = tool.compute(pretend_verified=frozenset({R152_WRONG_ENDPOINT}))
    assert after["available"] == base["available"], (after["available"], base["available"])
    assert sorted(after["blocked_operations"]) == sorted(base["blocked_operations"])
    # 而**若**它未收口（仿真「未收口」不可直接表达）⇒ 用被挡集反证：它**不**在挡点端点里
    assert R152_WRONG_ENDPOINT not in base["blocker_endpoints"], base["blocker_endpoints"]


def test_p172_the_benefit_mapping_is_computed_not_hand_written() -> None:
    """门槛（**可执行判定**）：`benefit_mapping()` 的每一行都由 `compute()` 复算得出。

    判据 = 逐端点重算「单独收口它」的可用集，与 `benefit_mapping()` 报告的一致。
    """
    tool = _tool()
    base = tool.compute()
    table = tool.benefit_mapping()
    assert set(table["endpoints"]) == set(base["blocker_endpoints"]), sorted(table["endpoints"])
    for endpoint, row in table["endpoints"].items():
        after = tool.compute(pretend_verified=frozenset({endpoint}))
        expected = sorted(set(after["available_operations"]) - set(base["available_operations"]))
        assert row["unlocks"] == expected, (endpoint, row["unlocks"], expected)
        assert row["blocks"] == base["blocker_endpoints"][endpoint], endpoint


def test_p172_no_endpoint_has_marginal_benefit_after_the_closure() -> None:
    """门槛（**R166 收口后**）：**没有**任何端点有边际收益 —— **全部 4 个**都是 **0**。

    ⚠️ 本批（P172）时是「**恰好 1 个**有边际收益」（`POST.STEELCODECHECK` ⇒
    `['DESIGN.CODE_CHECK']`）—— 那个值**算对了**，且已由 **R166（P174）** 真机兑付。
    收口后**唯一**剩下的是那 **2** 条崩溃边（各自的最短选项含一个 `*-ANAL`）
    ⇒ 单独收口**任何一个**都**不**解锁 Operation（**R166** 的归因结论）。
    ⚠️ **不**声称这 **4** 个「没用」—— 见下一条（它们**成组**才有收益）。
    """
    tool = _tool()
    table = tool.benefit_mapping()
    assert table["zero_benefit"] == sorted(ZERO_MARGINAL), table["zero_benefit"]
    assert len(table["zero_benefit"]) == 4
    assert all(not row["unlocks"] for row in table["endpoints"].values()), table["endpoints"]


# ===== 3. 最小解锁代价（**不**是「挡点个数」）=====


def test_p172_the_minimal_unlock_cost_is_not_the_blocker_count() -> None:
    """门槛（**口径**）：挡点**个数** ≠ 解锁**代价**。

    `routes` 是**替代**路线 ⇒ 花 **2** 个（`BD-ANAL` + `BD-TABLE`）就解锁 `DESIGN.CONCRETE`。
    ⚠️ 本批（P172）时「**全部 3 个**只要 **4** 个端点」（挡点个数当时 **13**）。
    **R166（P174）** 收口后：被挡 **2** 个、挡点端点 **4** 个 ⇒ 「全部」代价**仍是 4**
    （⚠️ 此时 `all_count == blocker_endpoint_count` —— 「代价 ≠ 个数」这条
    **只在**收口**前**是**可判别**的）。
    """
    tool = _tool()
    cost = tool.minimal_unlock_cost()
    assert cost["per_operation"] == {
        "DESIGN.CONCRETE": 2,
        "DESIGN.SRC": 2,
    }, cost["per_operation"]
    assert cost["all_count"] == 4, cost["all"]
    assert len(cost["all"]) == cost["all_count"]


def test_p172_the_minimal_unlock_set_really_unlocks_everything() -> None:
    """门槛（**效果**）：把那 **4** 个假设成 `VERIFIED` ⇒ 被挡数 **0**（**真的**解锁）。"""
    tool = _tool()
    cost = tool.minimal_unlock_cost()
    after = tool.compute(pretend_verified=frozenset(cost["all"]))
    assert after["blocked"] == 0, after["blocked_operations"]
    assert after["available"] == EXPECTED_TOTAL, after["available"]
    # 少任何一个都**不**够（最小性）
    for endpoint in cost["all"]:
        smaller = frozenset(cost["all"]) - {endpoint}
        assert tool.compute(pretend_verified=smaller)["blocked"] > 0, endpoint


def test_p172_grouped_endpoints_do_have_benefit() -> None:
    """门槛（**「零边际收益」≠「没用」**）：`DESIGN.CONCRETE` 的那 **2** 个**成组**收口 ⇒ **+1**。

    ⚠️ 逐个判死会得出「这些端点全无价值」的**错**结论 —— 本用例把它钉住。
    ⚠️ 本批（P172）时它「**顺带**也解锁 `DESIGN.CODE_CHECK`」（⇒ 可用 **70**，本批预期 `+2`）；
    **R166（P174）** 已**单独**收口 `DESIGN.CODE_CHECK` ⇒ 成组收口现在**只**解锁 `DESIGN.CONCRETE`
    （可用 **70**，`+1`）—— 断言按**收口后**的事实写。
    """
    tool = _tool()
    base = tool.compute()
    concrete = base["blocked_operations"]["DESIGN.CONCRETE"]
    after = tool.compute(pretend_verified=frozenset(concrete))
    unlocked = sorted(set(after["available_operations"]) - set(base["available_operations"]))
    assert unlocked == ["DESIGN.CONCRETE"], unlocked
    assert after["available"] == EXPECTED_AVAILABLE + 1, after["available"]


# ===== 4. 崩遗族**仍**不可碰 =====


def test_p172_the_crash_family_is_still_guarded() -> None:
    """门槛（**R154 红线**）：**6** 个 `*-ANAL` 仍在 `NATIVE_CRASH_ENDPOINTS` 里。

    ⚠️ 本批**不**碰它们（`BD-ANAL` **实测四次**打崩 `GenNX.exe`）；要跑须**用户明确同意**。
    ⚠️ 而**最小解锁集**（**4** 个）里**含** `BD-ANAL` ⇒ 「花 4 个就能全解锁」在**可实施性**上
    **不成立** —— 卡在**产品侧**，不是「多花几个端点就能绕开」。
    """
    sys.path.insert(0, str(REPO_ROOT))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        NATIVE_CRASH_ENDPOINTS,
        NATIVE_CRASH_MEASURED,
    )

    tool = _tool()
    cost = tool.minimal_unlock_cost()
    crash = sorted(set(cost["all"]) & set(NATIVE_CRASH_ENDPOINTS))
    # 最小集 4 个里有 **2** 个是实测 / 同族推定的崩溃端点 ⇒ 半数的「代价」是**不可实施**的
    assert crash == [
        "DESIGN.RC.KDS-41-20-2022.BD-ANAL",
        "DESIGN.SRC.AIK-SRC2K.BC-ANAL",
    ], crash
    assert len(crash) * 2 == len(cost["all"]), (crash, cost["all"])
    assert "DESIGN.RC.KDS-41-20-2022.BD-ANAL" in NATIVE_CRASH_MEASURED, "BD-ANAL 是实测的"
    # ⚠️ **R166（P174）**：剩下 **4** 个挡点端点**全部**归属 MIDAS 侧（`ours` 已空）
    attribution = tool.gate_attribution()
    assert attribution["ours"] == [], attribution["ours"]
    assert len(attribution["midas"]) == 4, attribution["midas"]


# ===== 5. 「值不值」的**代价**那一半 =====


def test_p172_the_request_body_of_steelcodecheck_is_unknown_offline() -> None:
    """门槛（**代价**）：该端点的**请求体来源**在本仓**不成立** ⇒ 收口**须**一次授权测量。

    三条**可复算**的机械事实（**零请求**）：

    ① 手册条目的 `sections_present` **没有** `Request Examples` / `Response Examples`
       （⚠️ 它是 **13** 个挡点端点里**唯一**缺这两节的 —— 对照 `POST.TABLE` / `POST.TEXT` 都有）；
    ② 手册的 `json_schema` 根键是 `vSECT` / `vELEM`，规格表描述的是
       Combined Strength Ratio / Slenderness Ratio / Deflection ⇒ **结果量** ⇒
       那份 `json_schema` 是**响应**形状，**不**是请求形状；
    ③ 我们**已落盘**的 Schema 与它**逐字节同形** ⇒ 我们手里**同样没有**请求形状；
       且它**没有** `properties` ⇒ `spec_guard` **一个字段都不检查**。

    ⚠️ 结论**不是**「不可收口」，而是「**不**能靠本仓证据收口」——
    与 `R151` 的教训一致：**不**按示例体硬凑（这里连示例体都**没有**）。
    """
    manual = json.loads(
        (REPO_ROOT / "MIDAS_API_Online_Manual_数据_v1.0.json").read_text(encoding="utf-8")
    )
    entry = next(
        item
        for item in manual["endpoints"]
        if "steelcodecheck" in str(item.get("input_uri") or "").lower()
    )
    sections = entry["sections_present"]
    assert "Request Examples" not in sections, sections
    assert "Response Examples" not in sections, sections
    # ② `json_schema` 是**响应**形状（结果量），不是请求形状
    assert sorted(json.loads(entry["json_schema"])) == ["vELEM", "vSECT"]
    # ③ 我们落盘的 Schema 与手册**逐字节同形**，且**没有** properties
    ours = json.loads(
        (
            REPO_ROOT
            / "registry"
            / "schema"
            / "products"
            / "gen_nx"
            / "post"
            / "STEELCODECHECK.json"
        ).read_text(encoding="utf-8")
    )["schema"]
    assert json.dumps(ours, sort_keys=True) == json.dumps(
        json.loads(entry["json_schema"]), sort_keys=True
    ), "手册与我们的 Schema 必须同形（同源）"
    assert "properties" not in ours, sorted(ours)


def test_p172_the_contrast_endpoints_do_have_request_examples() -> None:
    """门槛（**阳性对照**）：**已**收口的同类端点**有** `Request Examples` 节。

    ⚠️ 没有阳性对照的「缺失」不构成证据（**R157 的方法学**）——
    本用例证明「缺 `Request Examples`」**不是**手册的普遍形态，而是本端点的**个别**缺口。
    """
    manual = json.loads(
        (REPO_ROOT / "MIDAS_API_Online_Manual_数据_v1.0.json").read_text(encoding="utf-8")
    )
    for stem in ("table", "text"):
        entry = next(
            item
            for item in manual["endpoints"]
            if str(item.get("input_uri") or "").strip().lower() == f"post/{stem}"
        )
        assert "Request Examples" in entry["sections_present"], stem
        assert entry["request_examples"], stem


# ===== 6. 文档口径已更正 =====


def test_p172_the_docs_no_longer_claim_zero_benefit() -> None:
    """门槛（**只改现状声称**）：README §5.1 与 `docs/07` 都**不再**把该端点说成「不解锁」。

    ⚠️ 判据是「**不再**把它当**现状**」而不是「全文不出现旧说法」——
    `docs/07` 的 **R152 行原文**（时点记录）**必须**保留，由 **R165** 更正。
    """
    readme = README.read_text(encoding="utf-8")
    assert "R165" in readme, "README 必须可回溯到 R165"
    assert "**R152**：单独收口**不**解锁" not in readme, "README 仍把 R152 的错口径当现状"
    assert "**我方**" in readme
    docs = DOCS_07.read_text(encoding="utf-8")
    assert "**R165**" in docs, "R165 必须登记"
    assert "**R152**" in docs, "R152 的历史记录必须保留（时点记录不篡改）"
    assert "check_operation_availability.py" in docs, "裁决里必须留下可复算的工具"


def test_p172_the_tool_check_passes_from_the_command_line() -> None:
    """门槛：`--check` 与 `--benefit` 退出码 0（零请求）。"""
    for flag in ("--check", "--benefit"):
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
    assert "69 / 71" in checked.stdout, checked.stdout


# ===== 6. 零请求 =====


def test_p172_the_batch_ran_no_probes() -> None:
    """门槛（**零请求**）：本批**没有**新增任何 `*_probe.json`。

    ⚠️ 本批**必须**零请求：`gen-local` 实例**不可达**（TCP `127.0.0.1:3030` **refused**）
    ⇒ 真机测量**不**具备条件 ⇒ 只做**离线**复算。
    """
    probes = sorted(path.name for path in LIVE.glob("*probe*.json"))
    assert not any("p172" in name for name in probes), probes
