"""P173 / **R166**：**收益 ≠ 可实施性** —— 把「**卡在谁**」也**算**出来（**零请求**）。

本批要回答的问题
----------------
P172（**R165**）把**收益**算准了（收口 `POST.STEELCODECHECK` ⇒ **+1**），但留下一个**陷阱**：
**收益 > 0 ≠ 能马上做**。⇒ 本批把「**卡在谁**」机械化（`gate_attribution()` + `--attribution`），
**不**新增手写表、**不**改任何裁定数字、**不**发任何请求。

⚠️ **本批零请求**。⚠️ **R167 更正（P174）**：当初的理由「实例不可达」是**错的** ——
`gen-local` **只**监听 **`::1`**（`netstat`：`TCP [::1]:3030 LISTENING`），
而本批用的是 **IPv4 `127.0.0.1`** ⇒ 必然假阴性。用主机名（`instances.yaml` 的
`base_url` = `http://localhost:3030/gen`）只读 `GET /DB/NODE` ⇒ **`200`**。
⇒ ⚠️ 零请求**仍然成立**（本批**确实**只做离线复算），但**理由**改了：
**不是**「实例不可达」，而是「归因是**纯本仓可读**的计算，本轮**不**需要真机」。
⚠️ 本批的**结论**只依赖本仓可读证据 ⇒ **不**受此更正影响。

本文件钉住的判据
----------------
1. **归因是机械的**：`*-ANAL` ⇒ **MIDAS 侧**（崩溃族）· 其余遵循同一条崩溃边的 ⇒ **MIDAS 侧** ·
   只有 `steel` 路由 ⇒ **我方**（**恰好 1** 个 = `POST.STEELCODECHECK`）；
2. **`-TABLE` 不是独立代价**：`-ANAL` = **执行分析并写设计结果**（YAML 标题逐字 `Perform`），
   `-TABLE` = **读**那份结果（`Table`）⇒ 没有 `-ANAL` 跑过就没有 `-TABLE` 要读的东西；
3. **关键反事实**：假设**崩溃族全部修好** ⇒ 主指标**仍 `68 / 71`**（一格都没动）——
   「卡在 MIDAS 侧」是**结构**性的，**不是**「多收口几个端点就能绕开」；
4. **`--benefit` 的每一条路线都至少含一个 `*-ANAL`**（含 `DESIGN.SRC` 的最短选项
   `BC-ANAL` + `BC-TABLE`）⇒ **不碰 `*-ANAL` 就拿不下任何一格**，唯一例外 = `steel` 路由；
5. **主指标与收益映射不变**：`--check` 退出码 0 且输出 `68 / 71`（`EXPECTED_*` 一行未动）；
6. **文档口径**：`README.md` §5.1 与 `registry/README.md` §8.28、`docs/07` §16.1 **R166**
   都留下**可复算的工具**；
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
"""主指标 + 收益映射 + 归因的唯一裁定入口（**只读**，**零请求**）。"""

README = REPO_ROOT / "README.md"
REGISTRY_README = REPO_ROOT / "registry" / "README.md"
DOCS_07 = REPO_ROOT / "docs" / "07_开发方案与任务续接_v1.0.md"

EXPECTED_AVAILABLE = 71
"""⚠️ **R166（P174）**：本批（P173）时是 **68** —— `POST.STEELCODECHECK` 收口后 **+1**。"""
EXPECTED_TOTAL = 73
EXPECTED_BLOCKED = ("DESIGN.CONCRETE", "DESIGN.SRC")
"""⚠️ **R166（P174）**：本批（P173）时是 **3** 个（含 `DESIGN.CODE_CHECK`）—— 现已解锁。"""

OURS_ONLY = "POST.STEELCODECHECK"
"""✅ **R166（P174）已收口** —— 收口前它是「**我方**唯一杠杆」（本批归因**算对了**）。"""

MIDAS_ONLY_ENDPOINTS = 4
"""卡在 **MIDAS 侧**的挡点端点个数（⚠️ 收口前是 **12**：13 个里除 `POST.STEELCODECHECK`）。

⚠️ **R166（P174）**：`POST.STEELCODECHECK` 已收口 ⇒ 它**不再**是挡点端点，
且 `DESIGN.CODE_CHECK` 解锁 ⇒ 它的 `concrete:*` / `src:*` 路线**不再计入**挡点
⇒ 只剩 **4** 个（两条崩溃边各自的最短选项）—— **全部**在 MIDAS 侧。
"""


def _tool() -> Any:
    """装载裁定工具（**只读**；不执行 `main()`）。"""
    spec = importlib.util.spec_from_file_location("_availability_p173", AVAILABILITY_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _manual() -> dict[str, Any]:
    return json.loads(
        (REPO_ROOT / "MIDAS_API_Online_Manual_数据_v1.0.json").read_text(encoding="utf-8")
    )


# ===== 1. 归因是机械的 =====


def test_p173_attribution_splits_the_blockers_by_side() -> None:
    """门槛（**核心**）：**4** 个挡点端点 = **4** 个 MIDAS 侧 + **0** 个我方。

    ⚠️ 归因**不**手写 —— 由端点自身的机械性质（∈ 崩溃族 / 最短选项含崩溃族）判定。
    ⚠️ **R166（P174）**：收口前是「**13** = **12** + **1**」—— 我方那一格已**兑付**，
    现在 `ours` **为空**（本批的归因**算对了**：它指出的唯一我方杠杆正是能拿下的那个）。
    """
    table = _tool().gate_attribution()
    assert len(table["endpoints"]) == 4, sorted(table["endpoints"])
    assert table["ours"] == [], table["ours"]
    assert len(table["midas"]) == MIDAS_ONLY_ENDPOINTS, table["midas"]
    assert sorted(table["endpoints"]) == sorted(table["ours"] + table["midas"])
    # ⚠️ 收口前的「我方唯一杠杆」**不再**是挡点端点（它已 `verified`）
    assert OURS_ONLY not in table["endpoints"], table["endpoints"]


def test_p173_ours_and_midas_are_mutually_exclusive() -> None:
    """门槛：两档**互斥**且**覆盖**（没有第三个 `side` 值）。"""
    table = _tool().gate_attribution()
    sides = {row["side"] for row in table["endpoints"].values()}
    assert sides == {"midas"}, sides


def test_p173_every_crash_family_anal_is_attributed_to_midas() -> None:
    """门槛：**每个** `*-ANAL` 端点都落在 MIDAS 侧（**不**依赖它的单独收益是多少）。

    ⚠️ 这条防的是「按收益分类」的偷懒做法 —— `*-ANAL` 的单独收益**恰好全是 0**，
    如果按收益分类，它们会跟 `*-TABLE` 混成一组，**看不出**谁是**根因**。
    """
    table = _tool().gate_attribution()
    anals = sorted(key for key in table["endpoints"] if key.endswith("-ANAL"))
    # ⚠️ **R166（P174）**：收口前是 **6** 个 —— `DESIGN.CODE_CHECK` 解锁后只剩**两条**崩溃边
    assert len(anals) == 2, anals
    assert all(table["endpoints"][key]["side"] == "midas" for key in anals), anals
    assert all(not table["endpoints"][key]["own_benefit"] for key in anals), "ANAL 单独收益应为 0"


def test_p173_the_measured_crash_endpoint_keeps_its_distinct_reason() -> None:
    """门槛：**实测**崩溃端点（`BD-ANAL`）的理由与**同族推定**的**不**混为一谈（R154）。

    ⚠️ 这是**诚实边界**：`NATIVE_CRASH_MEASURED` 只有 **1** 个（**四次**实测、同一偏移），
    其余 **10** 个是**同族推定** ⇒ 归因理由必须**区分**。
    """
    sys.path.insert(0, str(REPO_ROOT))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        NATIVE_CRASH_MEASURED,
    )

    table = _tool().gate_attribution()
    measured = "DESIGN.RC.KDS-41-20-2022.BD-ANAL"
    assert measured in NATIVE_CRASH_MEASURED
    assert "实测崩溃族" in table["endpoints"][measured]["reason"]
    # ⚠️ **R166（P174）**：收口前同族推定的 `*-ANAL` 有 **5** 个（共 6 个）。
    # 收口后只剩 2 个 `*-ANAL`：**实测**的 `BD-ANAL` + **同族推定**的 `BC-ANAL`
    others = [key for key in table["midas"] if key.endswith("-ANAL") and key != measured]
    assert others == ["DESIGN.SRC.AIK-SRC2K.BC-ANAL"], others
    assert all("同族推定" in table["endpoints"][key]["reason"] for key in others), others


# ===== 2. `-TABLE` **不是**独立代价 =====


def test_p173_the_table_endpoints_are_downstream_of_the_crash_family() -> None:
    """门槛：**2** 个 `*-TABLE` 的归因是「同一条崩溃边的下游」，**不**是独立的一格代价。

    ⚠️ 判据 = 「**最短选项**里含崩溃族 `*-ANAL`」—— 机械可复算（穷举路线选项）。
    ⚠️ **R166（P174）**：收口前是 **6** 个 —— `DESIGN.CODE_CHECK` 解锁后只剩**两条**崩溃边。
    """
    table = _tool().gate_attribution()
    tables = sorted(key for key in table["endpoints"] if key.endswith("-TABLE"))
    assert tables == [
        "DESIGN.RC.KDS-41-20-2022.BD-TABLE",
        "DESIGN.SRC.AIK-SRC2K.BC-TABLE",
    ], tables
    for key in tables:
        row = table["endpoints"][key]
        assert row["side"] == "midas", (key, row)
        assert "不是独立代价" in row["reason"], (key, row["reason"])
        assert row["minimal_option_size"] == 2, (key, row)
        assert any(step.endswith("-ANAL") for step in row["minimal_option"]), row


def test_p173_the_anal_yaml_says_perform_and_the_table_yaml_says_table() -> None:
    """门槛（**文本证据**，零请求）：`-ANAL` = **执行并写结果**；`-TABLE` = **读**那份结果。

    ⇒ 「`-TABLE` 依赖 `-ANAL`」**不**是推断，而是两个端点的**声明语义**。
    ⚠️ 若这两行 YAML 的标题改了，本用例先红（防止语义被静默改写）。
    """
    design = REPO_ROOT / "registry" / "design" / "rc" / "KDS-41-20-2022"
    anal = (design / "BD-ANAL.yaml").read_text(encoding="utf-8")
    table = (design / "BD-TABLE.yaml").read_text(encoding="utf-8")
    assert "Perform" in anal, "BD-ANAL 的标题必须声明它是「执行」"
    assert "Table" in table, "BD-TABLE 的标题必须声明它是「表（读）」"
    assert "Perform" not in table
    assert "Table" not in anal


# ===== 3. 关键反事实：修好崩溃族 ⇒ 主指标**仍**不变 =====


def test_p173_fixing_the_whole_crash_family_moves_nothing() -> None:
    """门槛（**本批的新结论，收口后仍成立**）：假设崩溃族**全部**修好 ⇒ 主指标**仍**不变。

    ⚠️ 这是本批最容易被读错的一条：**修 MIDAS 的崩溃不自动解锁任何东西** ——
    `*-TABLE` 的设计结果只能由（刚被假设修好的）`*-ANAL` **产出**（仍须一次**授权测量**）。
    ⇒ 「卡在 MIDAS 侧」是**结构**性的，**不**是「多收口几个端点就能绕开」。
    ⚠️ **R166（P174）**：收口前「仍 `68 / 71`、挡点端点 13 → 7」；收口后是
    「仍 `71 / 73`、挡点端点 4 → 2」—— **结论不变**，数字随收口上抬。
    """
    tool = _tool()
    sys.path.insert(0, str(REPO_ROOT))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        NATIVE_CRASH_ENDPOINTS,
    )

    after = tool.compute(pretend_verified=NATIVE_CRASH_ENDPOINTS)
    assert after["available"] == EXPECTED_AVAILABLE, after["available"]
    assert sorted(after["blocked_operations"]) == sorted(EXPECTED_BLOCKED), sorted(
        after["blocked_operations"]
    )
    # 但挡点端点**确实**从 4 掉到 2 ⇒ 「修了有变化，只是**还**不够」，不是仿真失灵
    assert after["blocker_endpoint_count"] == 2, after["blocker_endpoint_count"]


def test_p173_the_counterfactual_is_reported_by_the_tool() -> None:
    """门槛：`--attribution` 的**输出**里也报出这个反事实（**不**只存在于测试里）。"""
    table = _tool().gate_attribution()
    assert table["fixing_all_crash_yields"] == EXPECTED_AVAILABLE
    assert sorted(table["fixing_all_crash_still_blocked"]) == sorted(EXPECTED_BLOCKED)


def test_p173_reaching_seventy_one_needs_the_tables_too() -> None:
    """门槛（**阳性对照**，R157 的方法学）：崩溃族 **+** 那 **2** 个 `*-TABLE` ⇒ **真的** `71/71`。

    ⚠️ 这条**不**可省（见下）。

    ⚠️ 没有这条，「修好崩溃族 ⇒ 不变」可能只是**仿真失灵**（`pretend_verified` 根本没生效）。
    ⇒ 必须证明**仪器有效**：再加一组**确实**应该解锁的端点 ⇒ 数字**会**动。
    """
    tool = _tool()
    sys.path.insert(0, str(REPO_ROOT))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        NATIVE_CRASH_ENDPOINTS,
    )

    base = tool.compute()
    tables = frozenset(key for key in base["blocker_endpoints"] if key.endswith("-TABLE"))
    assert len(tables) == 2, sorted(tables)
    after = tool.compute(pretend_verified=NATIVE_CRASH_ENDPOINTS | tables)
    assert after["available"] == EXPECTED_TOTAL, after["available"]
    assert after["blocked_operations"] == {}, after["blocked_operations"]


# ===== 4. 每条路线都含 `*-ANAL`（唯一例外 = steel）=====


def test_p173_every_route_of_every_blocked_operation_contains_an_anal() -> None:
    """门槛：**每个**被挡 Operation 的**最短选项**都含 `*-ANAL`（**不碰它就拿不下任何一格**）。

    ⚠️ `DESIGN.SRC` 也含（`BC-ANAL` + `BC-TABLE`）—— 这一条**反直觉**（容易以为 SRC 能绕开）。
    """
    tool = _tool()
    table = tool.gate_attribution()
    assert sorted(table["above_operations"]) == sorted(EXPECTED_BLOCKED)
    assert all(row["option_has_crash"] for row in table["above_operations"].values()), table[
        "above_operations"
    ]


def test_p173_the_steel_route_was_the_only_anal_free_path() -> None:
    """门槛：`steel` 路由**无** `*-ANAL` ⇒ 收口 `POST.STEELCODECHECK` 是**我方**唯一杠杆。

    ⚠️ 这也是 `DESIGN.CODE_CHECK` 的最小代价 = **1** 的**成因**（**不**是巧合）。
    ✅ **R166（P174）已兑付**：那一格已被收口 ⇒ 该路由**现在全通**
    ⇒ 本用例改为钉「**它是唯一无 `*-ANAL` 的路由** ∧ **它已全通**」。
    """
    tool = _tool()
    plans = tool._load()[0]  # noqa: SLF001
    steel = [step.key for step in plans["DESIGN.CODE_CHECK"].routes["steel"]]
    assert steel == [
        "DESIGN.STEEL.KDS-41-30-2022.CODE-ANAL",
        "DESIGN.STEEL.KDS-41-30-2022.CODE-TABLE",
        "POST.STEELCODECHECK",
    ], steel
    # ⚠️ `CODE-ANAL` **在**崩溃名单里**被排除**（旗舰链真机 12/12 跑通 ⇒ 不拦它）
    sys.path.insert(0, str(REPO_ROOT))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        NATIVE_CRASH_ENDPOINTS,
        NATIVE_CRASH_MEASURED,
    )
    from app.infrastructure.adapters.midas.registry import (  # noqa: PLC0415
        VERIFIED,
        MidasRegistry,
    )

    assert steel[0] not in NATIVE_CRASH_ENDPOINTS, "旗舰链的 CODE-ANAL 必须**不**被拦"
    # ✅ **R166**：三步**全通**（末步已收口）
    registry = MidasRegistry.load(REPO_ROOT / "registry")
    statuses = [registry.resolve(key=key, product="GEN_NX").verification_status for key in steel]
    assert statuses == [VERIFIED, VERIFIED, VERIFIED], statuses
    # ⚠️ 每一条**其余**路线**仍**含一个崩溃族 `*-ANAL`（⇒ 仍卡 MIDAS 侧）
    for name, steps in plans["DESIGN.CODE_CHECK"].routes.items():
        if name == "steel":
            continue
        assert any(step.key in NATIVE_CRASH_ENDPOINTS for step in steps), name
    assert NATIVE_CRASH_ENDPOINTS != NATIVE_CRASH_MEASURED, "崩溃族仍含同族推定成员"


# ===== 5. 主指标与收益映射 =====


def test_p173_the_main_metric_and_benefit_are_consistent() -> None:
    """门槛：`--check` 退出码 0 且输出 `71 / 73`（**R166 收口后**）。

    ⚠️ 本批（P173）当时是「**只加视图，不改裁定**」+ `68 / 71`。
    **R166（P174）** 用真机实测收口 ⇒ 裁定值**确实**改了（`EXPECTED_AVAILABLE` 68 → 69 等）
    ⇒ 本用例改为钉**收口后**的真相（**不**再声称「裁定未动」）。
    """
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


def test_p173_the_attribution_cli_reports_both_sides() -> None:
    """门槛：`--attribution` 的输出里出现「我方」「MIDAS 侧」与那个反事实。

    ⚠️ **R166（P174）**：`ours` 现在**为空** ⇒ 输出会打印「**（已全部收口）**」
    ⇒ 断言改为钉**那一行**（而**不是**某个具体端点名）。
    """
    result = subprocess.run(
        [sys.executable, str(AVAILABILITY_TOOL), "--attribution"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "我方" in result.stdout
    assert "MIDAS 侧" in result.stdout
    assert "71 / 73" in result.stdout, "反事实必须报出主指标"
    assert "已全部收口" in result.stdout, "`ours` 为空时必须以「已全部收口」如实报出"


# ===== 6. 文档口径 =====


def test_p173_the_docs_register_the_attribution() -> None:
    """门槛：`README.md` §5.1 / `registry/README.md` §8.28 / `docs/07` §16.1 **R166** 都登记。"""
    root = README.read_text(encoding="utf-8")
    registry = REGISTRY_README.read_text(encoding="utf-8")
    docs = DOCS_07.read_text(encoding="utf-8")
    assert "R166" in root, "README 必须可回溯到 R166"
    assert "8.28" in registry, "registry/README 必须有 §8.28"
    assert "gate_attribution" in registry, "§8.28 必须留下可复算的工具名"
    assert "**R166**" in docs, "R166 必须登记"
    assert "gate_attribution" in docs, "裁决里必须留下可复算的工具"
    # ⚠️ 历史记录**不**篡改：R152 / R165 的行都还在
    assert "**R165**" in docs
    assert "**R152**" in docs


def test_p173_the_crash_family_guard_wording_is_not_downgraded() -> None:
    """门槛（**红线**）：`DESIGN.{RC,SRC}` 的 `*-ANAL` 仍被登记为**崩溃族**（R154 未被弱化）。

    ⚠️ 本批**新增**了「`-TABLE` 卡在同一条边」的归因 —— 它**不**得被读成
    「所以 `-ANAL` 可以不查了」。
    """
    sys.path.insert(0, str(REPO_ROOT))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        NATIVE_CRASH_ENDPOINTS,
    )

    for key in (
        "DESIGN.RC.KDS-41-20-2022.BD-ANAL",
        "DESIGN.RC.KDS-41-20-2022.CD-ANAL",
        "DESIGN.SRC.AIK-SRC2K.BC-ANAL",
    ):
        assert key in NATIVE_CRASH_ENDPOINTS, key
    registry = REGISTRY_README.read_text(encoding="utf-8")
    assert "R154" in registry


# ===== 7. 零请求 =====


def test_p173_the_batch_ran_no_probes() -> None:
    """门槛（**零请求**）：本批**没有**新增任何 `*_probe.json`。

    ⚠️ **R167 更正（P174）**：原先写的「因为实例不可达」**是错的**（IPv4-only 探针假阴性，
    实例**只**监听 `::1` ⇒ 见 `registry/instances.yaml` 的 `probe_host_warning`）。
    本批零请求**仍然成立**，但**理由**是「归因是纯本仓可读的计算，本轮**不需要**真机」。
    """
    probes = sorted(path.name for path in LIVE.glob("*probe*.json"))
    assert not any("p173" in name for name in probes), probes


# ===== 8. R167：探活**必须**用主机名（IPv6），**不**用 IPv4 =====


def test_r167_the_instance_matrix_warns_against_ipv4_probing() -> None:
    """门槛（**R167**，**结构性防复发**）：`instances.yaml` 的 `gen-local` **必须**带
    `probe_host_warning`，且 `base_url` 用主机名而**非** `127.0.0.1`。

    ⚠️ 本用例**不**做任何网络访问（CI 可能没有实例）—— 它只断言**警告还在**。
    ⚠️ 为什么写在这里：同一个坑已**三次**（P138 自我更正 · P139 记为已知坑 · P172/P173 复发），
    且**前两次都写进了文档仍复发** ⇒ 把警告放进**机器可读**的实例矩阵，并由用例钉住。
    """
    sys.path.insert(0, str(REPO_ROOT))
    import yaml  # noqa: PLC0415

    matrix = yaml.safe_load((REPO_ROOT / "registry" / "instances.yaml").read_text(encoding="utf-8"))
    entries = {item["alias"]: item for item in matrix["instances"]}
    gen = entries["gen-local"]
    assert gen["base_url"] == "http://localhost:3030/gen", gen["base_url"]
    assert "127.0.0.1" not in gen["base_url"], "base_url 不得是 IPv4 回环"
    warning = gen.get("probe_host_warning", "")
    assert warning, "gen-local 必须带 probe_host_warning（R167）"
    assert "127.0.0.1" in warning and "::1" in warning, warning
    assert "R167" in warning, "警告必须可回溯到 R167"


def test_r167_no_doc_claims_the_instance_is_unreachable() -> None:
    """门槛（**R167**）：**现状**文档里**不再**把「实例不可达（`127.0.0.1`）」当**前提**。

    ⚠️ 历史记录（P138 报告、P172/P173 的行）**保留原文**（时点记录不篡改）——
    判据是「**入口/入口前提**不得再教人用 `127.0.0.1` 探活」。
    """
    docs = DOCS_07.read_text(encoding="utf-8")
    prompt = (REPO_ROOT / "docs" / "08_会话交接与续接提示词_v1.0.md").read_text(encoding="utf-8")
    assert "R167" in docs, "docs/07 必须登记 R167"
    # ⚠️ **不**得再出现「用 127.0.0.1 探活」这种**指引**（`localhost` / `[::1]` 才对）
    assert "第一步 = 探活：`127.0.0.1:3030` 是否可连" not in prompt, "提示词仍在教 IPv4 探活"
    assert "TCP `127.0.0.1:3030` 本轮 **timeout**，P172 为 **refused**）。" not in docs, (
        "docs/07 的入口仍把 IPv4 假阴性当现状"
    )
    assert "[::1]" in prompt or "localhost" in prompt, "提示词必须给出正确探活主机"
