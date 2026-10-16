"""主指标**可执行化**：**生产路径可用 Operation**（`docs/07` §15.6.3 的主指标）。

为什么需要这个工具（**R158**）
------------------------------
`README.md` §1.1 的 `62 / 71` 是**手写**的，于是漂了：它把 `DESIGN.CODE_CHECK` 算成**可用**，
而该 Operation 的 **7 条路由全部被挡**（`steel` 路由的末步 `POST.STEELCODECHECK` 是 `PARTIAL`；
`concrete:*` 需 `BD/CD/BRD/WD-ANAL`（**原生崩溃护栏**）；`src:*` 需 `SRC.{BC,CC}-ANAL`（同））。
⇒ 真实值是 **61 / 71**。**手写的指标必然漂** ⇒ 把它变成**可执行判定**（本工具 + `--check`）。

**P166 / R159 更新**：`VIEW.RESULTGRAPHIC` 的**纯 API 进结果视图（post）路径**已实测找到
（成因 = 原请求体缺 `TYPE_OF_DISPLAY`）⇒ 该端点 `untested → verified` ⇒ 它挡住的
**6** 个 `VIEW.*` Operation **解锁** ⇒ 主指标 **61 → 67**（被挡 **10 → 4**、挡点端点 **15 → 14**）。
证据 = `registry/live/view_result_post_probe.json`；判定 = `tests/test_midas_view_result_post_p166.py`。

**P167 / R160 更新**：`POST.TABLE` 的 `TABLE_TYPE` 枚举收口（来源换成「登记表 ∪ 手册声明」
两个**可复算**来源的并集，**225** 个取值；生成器 = `registry/tools/sync_table_type_enum.py`）
⇒ 该端点 `untested → verified` ⇒ 它挡住的 **1** 个 Operation（`RESULT.ANALYSIS.SUMMARY`，
**通用取表入口**）**解锁** ⇒ 主指标 **67 → 68**（被挡 **4 → 3**、挡点端点 **14 → 13**）。
证据 = `registry/live/post_table_enum_probe.json`；判定 = `tests/test_midas_post_table_enum_p167.py`。

**P172 / R165 更新**：**收益映射本身**也曾是**手写**的（`docs/reports/P160e-a` §1），
于是漂了 —— 它把 `POST.STEELCODECHECK` 记成「**0**（单独收口**不**解锁）」，
理由「`DESIGN.CODE_CHECK` 还需 12 个 RC/SRC 端点」**把口径读反了**（`routes` 是**替代**
路线 ⇒ **至少一条**全通即可）。实测收益 = **+1**（解锁 `DESIGN.CODE_CHECK`）。
⇒ 新增 `benefit_mapping()` + `--benefit` + `EXPECTED_BENEFIT`（**逐端点**断言）。
⚠️ **本批零请求**（实例不可达）⇒ `POST.STEELCODECHECK` 的 `availability` **不变**
（`untested`），主指标**仍 `68 / 71`** —— 本批价值在**算准收益**与**更正口径**。

口径（**显式**，缺一不可）
--------------------------
1. 遍历 `OPERATION_PLANS` 的**全部 71** 个 Operation。
2. **无 `steps` 且无 `routes`** ⇒ **不**因端点被挡（自研引擎 / MIDAS 无 API，
   如 `DESIGN.FOUNDATION` / `DESIGN.OPTIMIZE`）⇒ 计入**可用**，并**单列**标注。
3. `steps` 必须**全部** `verification_status == VERIFIED`。
4. `routes` 非空 ⇒ **至少一条**路由**全部** `VERIFIED`（routes 是**替代**路线，不是都要跑）。
5. 被挡原因分两类：`native_crash_guard`（在 `NATIVE_CRASH_ENDPOINTS` 里，**留缺**）
   与 `registry_mapping_not_verified`（没实测收口）。

⚠️ 本工具**只读**：不改 `availability`、不发任何请求。
"""

from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import sys
from collections import Counter
from typing import Any, Final

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
"""仓库根目录（`registry/tools/` 的上两级）。"""

PRODUCT: Final[str] = "GEN_NX"
"""主指标按 **GEN NX** 算（与 `README.md` §1.1 同口径）。"""

EXPECTED_AVAILABLE: Final[int] = 68
"""**已裁定**的可用数（`docs/07` §16.1 **R158** 定 61；**R159**（P166）收口 `VIEW.RESULTGRAPHIC`
⇒ **+6** = 67；**R160**（P167）收口 `POST.TABLE` ⇒ **+1** = **68**）。
改动它 = 改主指标 ⇒ 必须同时改文档。"""

EXPECTED_BLOCKED: Final[tuple[str, ...]] = (
    "DESIGN.CODE_CHECK",
    "DESIGN.CONCRETE",
    "DESIGN.SRC",
)
"""**已裁定**的被挡 Operation（**3** 个；顺序无关）。

⚠️ **P166 / R159**：`VIEW.{DEFORMED_MODEL,DISPLACEMENT,FORCE,MODE_SHAPE,REACTION,STRESS}`
（**6** 个）**已解锁** —— 它们的唯一挡点 `VIEW.RESULTGRAPHIC` 由 `untested` 收口为 `verified`
（依据 = 效果判据 **PASSED**：`registry/live/view_result_post_probe.json`）。

⚠️ **P167 / R160**：`RESULT.ANALYSIS.SUMMARY` **已解锁** —— 它的唯一挡点 `POST.TABLE` 由
`untested` 收口为 `verified`（依据 = 效果判据 **PASSED**：核心规范化结果 `data.result.rows`
= **63** 行 ∧ 伪 token **零请求**仍被拦：`registry/live/post_table_enum_probe.json`）。

⚠️ 剩下 **3** 个的被挡端点 **13** 个，**分两组**（`tests/test_midas_operation_availability_p165b.py`
逐条钉住）：**6** 个 `*-ANAL` = **实测崩溃族**（`NATIVE_CRASH_ENDPOINTS`，**R154** ⇒ **MIDAS 侧**修
`wg_db.dll`）；**6** 个 `*-TABLE` = `availability: untested`（要**先有设计结果** ⇒ 依赖那 6 个 `*-ANAL`）
+ **1** 个 `POST.STEELCODECHECK` = `availability: untested`（我方**可**收口）。

⚠️ **P172 / R165 —— R152 的「单独收口**不**解锁任何 Operation」是**错的**（已更正）**：
那句话的理由是「`DESIGN.CODE_CHECK` 还需 12 个 RC/SRC 端点」—— 它把**替代**路线
（口径第 4 条：**至少一条**全通即可）读成了**都要**通。实测：`steel` 路由**只有**末步
未收口 ⇒ 收口 `POST.STEELCODECHECK` ⇒ **解锁 `DESIGN.CODE_CHECK`** ⇒ 主指标 **68 → 69**
（被挡 **3 → 2** · 挡点端点 **13 → 4**）。⚠️ 结论**不**手写 —— 由 `benefit_mapping()` 算。

⚠️ **但**收益 **+1** ≠ **马上能做**（R165 的**代价**那一半，**零请求**可复算）：
`POST.STEELCODECHECK` 的**请求体来源**在本仓**不成立** —— ① 手册条目的 `sections_present`
**没有** `Request Examples` / `Response Examples`（它是 **13** 个挡点端点里**唯一**缺这两节的；
对照 `POST.TABLE` / `POST.TEXT` **都**有）；② 手册的 `json_schema` 根键 = `vSECT` / `vELEM`，
规格表描述的是 Combined Strength Ratio / Slenderness Ratio / Deflection ⇒ **结果量**
⇒ 那份 `json_schema` 是**响应**形状；③ 我们**已落盘**的 Schema 与它**逐字节同形**且
**没有** `properties` ⇒ `spec_guard` 对它**一个字段都不检查**。
⇒ 收口**须**一次**有副作用**的授权测量（且实例**不可达**时**连试都不该试**）。
⚠️ **不**按示例体硬凑（**R151**）—— 这里连示例体都**没有**。

**P173 / R166 更新**：收益算准了，但**收益 ≠ 可实施性** —— 本批把「**卡在谁**」也**算**出来
（`gate_attribution()` + `--attribution`）。机械事实：**`--benefit`** 的**每一条**路线里
**至少含一个** `*-ANAL`（`DESIGN.SRC` 最短选项 = `BC-ANAL` + `BC-TABLE` ⇒ 也含）⇒
**修好整个崩溃族后主指标仍 `68 / 71`**（因为 `*-TABLE` 要**先有设计结果**，
那结果只能由崩溃族的 `*-ANAL` 产出）⇒ **唯一**不依赖 `*-ANAL` 的边是 `steel` 路由
⇒ `POST.STEELCODECHECK` 是**我方**唯一可自己拿下的一格（代价 = 一次授权测量）。
"""

EXPECTED_BENEFIT: Final[dict[str, tuple[str, ...]]] = {
    "POST.STEELCODECHECK": ("DESIGN.CODE_CHECK",),
}
"""**已裁定**的收益映射（**R165**；`--check` 逐条断言）。

⚠️ **只**登记「有收益」的端点 —— 其余 **12** 个（6 个 `*-ANAL` + 6 个 `*-TABLE`）的收益
**恰好为 0**，由 `benefit_mapping()["zero_benefit"]` 机械给出（**不**手写，
因为手写的映射必然漂 —— R158 / R165 是同一类教训）。
⚠️ 改动它 = 改**收益映射** ⇒ 必须同时改 `README.md` §5.1 与 `docs/07` §16.1 R165。
"""

EXPECTED_MINIMAL_COST: Final[dict[str, int]] = {
    "DESIGN.CODE_CHECK": 1,
    "DESIGN.CONCRETE": 2,
    "DESIGN.SRC": 2,
}
"""**已裁定**的「解锁该 Operation 最少要收口几个端点」（**R165**；`--check` 逐条断言）。

⚠️ 与 `EXPECTED_BLOCKED` 的「挡点**个数**」**不是**一回事：`routes` 是**替代**路线
⇒ **花 2 个**（`BD-ANAL` + `BD-TABLE`）就解锁 `DESIGN.CONCRETE`，**顺带**也解锁
`DESIGN.CODE_CHECK` ⇒ 解锁**全部 3 个**只要 **4** 个端点（`minimal_unlock_cost()["all_count"]`），
**不**是 **13** 个。⚠️ 但这 **4** 个里含 `BD-ANAL`（**R154 实测崩溃端点**）⇒ **可实施性**
卡在**产品侧**，不是「多花几个端点就能绕开」。
"""


def _load() -> tuple[Any, Any, Any]:
    """装载 Operation 计划 / Registry / 崩溃族名单（**只读**）。"""
    sys.path.insert(0, str(REPO))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        NATIVE_CRASH_ENDPOINTS,
    )
    from app.infrastructure.adapters.midas.operations import OPERATION_PLANS  # noqa: PLC0415
    from app.infrastructure.adapters.midas.registry import (  # noqa: PLC0415
        VERIFIED,
        MidasRegistry,
    )

    return OPERATION_PLANS, MidasRegistry.load(REPO / "registry"), (
        VERIFIED,
        NATIVE_CRASH_ENDPOINTS,
    )


def compute(*, pretend_verified: frozenset[str] = frozenset()) -> dict[str, Any]:
    """算主指标（**纯函数**，便于测试复算）。

    Args:
        pretend_verified: **假设**这些端点已收口（`VERIFIED`）—— 用于算**收益映射**
            （`benefit_mapping()`）。**只影响本次计算**，**不**改任何落盘数据。

    ⚠️ **P172 / R165**：`routes` 的**替代**语义（口径第 4 条）是**逐条**判定的 ——
    一条路由里**只剩一个**未收口端点时，收口它**就**解锁整个 Operation。
    故「单独收口不解锁」这类结论**必须**由本函数**算**出来，**不能**手写
    （R152 就是这么漂的：把 OR 读成了 AND）。
    """
    plans, registry, (verified, crash_endpoints) = _load()

    def blocker_of(step: Any) -> str | None:
        if step.key in pretend_verified:
            return None
        try:
            resolved = registry.resolve(key=step.key, product=PRODUCT, method=step.method)
        except Exception:
            return "resolve_error"
        if resolved.verification_status == verified:
            return None
        return "native_crash_guard" if step.key in crash_endpoints else (
            "registry_mapping_not_verified"
        )

    available: list[str] = []
    endpoint_free: list[str] = []
    blocked: dict[str, list[dict[str, str]]] = {}
    for name, plan in sorted(plans.items()):
        if not plan.steps and not plan.routes:
            available.append(name)
            endpoint_free.append(name)
            continue
        # ① 公共前置步（`steps`）必须全部可用
        reasons: list[dict[str, str]] = [
            {"endpoint": step.key, "reason": reason}
            for step in plan.steps
            if (reason := blocker_of(step))
        ]
        # ② `routes` 是**替代**路线 ⇒ 只要**有一条**全通，就不算被路由挡住
        route_gaps: list[list[dict[str, str]]] = [
            [
                {"endpoint": step.key, "reason": reason}
                for step in steps
                if (reason := blocker_of(step))
            ]
            for steps in plan.routes.values()
        ]
        if route_gaps and all(gap for gap in route_gaps):
            for gap in route_gaps:
                for item in gap:
                    if item not in reasons:
                        reasons.append(item)
        if reasons:
            blocked[name] = reasons
        else:
            available.append(name)

    per_endpoint = Counter(
        item["endpoint"] for reasons in blocked.values() for item in reasons
    )
    return {
        "product": PRODUCT,
        "total": len(plans),
        "available": len(available),
        "blocked": len(blocked),
        "available_operations": sorted(available),
        "endpoint_free_operations": sorted(endpoint_free),
        "blocked_operations": {
            name: sorted({item["endpoint"] for item in reasons})
            for name, reasons in sorted(blocked.items())
        },
        "blocker_endpoints": dict(sorted(per_endpoint.items(), key=lambda kv: (-kv[1], kv[0]))),
        "blocker_endpoint_count": len(per_endpoint),
        "crash_guard_operations": sorted(
            name
            for name, reasons in blocked.items()
            if any(item["reason"] == "native_crash_guard" for item in reasons)
        ),
    }


def benefit_mapping() -> dict[str, Any]:
    """**逐端点收益**：收口**这一个**端点 ⇒ 解锁哪些 Operation（**可执行复算**）。

    为什么需要它（**R165**）
    ------------------------
    `docs/reports/P160e-a` 的「分组收益」是**手写**的，于是漂了：它把
    `POST.STEELCODECHECK` 记成「**0**（单独收口**不**解锁）」，理由是
    「`DESIGN.CODE_CHECK` 还需 12 个 RC/SRC 端点」。⚠️ 那个理由**把口径读反了**：
    `routes` 是**替代**路线（口径第 4 条：**至少一条**全通即可）⇒ `steel` 路由
    **只有**末步未收口 ⇒ 收口它**就**解锁 `DESIGN.CODE_CHECK`。实测 = **+1**。

    ⇒ 与 R158 同一类教训：**手写的映射必然漂** ⇒ 把它变成**可执行判定**。
    """
    base = compute()
    rows: dict[str, dict[str, Any]] = {}
    for endpoint in sorted(base["blocker_endpoints"]):
        after = compute(pretend_verified=frozenset({endpoint}))
        rows[endpoint] = {
            "blocks": base["blocker_endpoints"][endpoint],
            "unlocks": sorted(
                set(after["available_operations"]) - set(base["available_operations"])
            ),
        }
    return {
        "available": base["available"],
        "blocked": base["blocked"],
        "endpoints": rows,
        "zero_benefit": sorted(key for key, row in rows.items() if not row["unlocks"]),
    }


def _route_options(plan: Any) -> list[frozenset[str]]:
    """该 Operation 的**路线选项**：每个选项 = 「走这条路线时必须**全部**收口」的端点集。

    ⚠️ `steps`（公共前置）**每条**路线都要走 ⇒ **并进每一个选项**；
    `routes` 是**替代**路线 ⇒ 各是一个**独立**选项（这正是 R152 读反的地方）。
    `resolve` 失败 / 非 `VERIFIED` 的步**全部**计入（不区分原因 —— 本函数只回答**数量**）。
    """
    plans, registry, (verified, crash_endpoints) = _load()

    def unclosed(steps: Any) -> frozenset[str]:
        result: set[str] = set()
        for step in steps:
            try:
                resolved = registry.resolve(key=step.key, product=PRODUCT, method=step.method)
            except Exception:
                result.add(step.key)
                continue
            if resolved.verification_status != verified:
                result.add(step.key)
        return frozenset(result)

    common = unclosed(plan.steps)
    if not plan.routes:
        return [common]
    return [common | unclosed(steps) for steps in plan.routes.values()]


def minimal_unlock_cost() -> dict[str, Any]:
    """**最小解锁代价**：解锁每个被挡 Operation（以及**全部**）所需的**最少**端点数。

    为什么需要它（**R165**）
    ------------------------
    `README.md` §5.1 的框架是「**13** 个挡点端点」—— 那是**当前状态**下**挡点**的**个数**，
    **不**是「解锁要花多少个」。因为 `routes` 是**替代**路线，**花 2 个**（BD 对）就能解锁
    `DESIGN.CONCRETE`，而那 **2** 个**顺带**也解锁 `DESIGN.CODE_CHECK` ⇒ 解锁**全部 3 个**
    只需 **4** 个端点，**不**是 **13** 个。⚠️ 但**可实施性**是另一回事：那 **4** 个里含
    `BD-ANAL`（**R154 实测崩溃端点**）⇒ 实际被**产品侧**卡住（见 `EXPECTED_BENEFIT` 的注）。
    """
    plans, _registry, _extra = _load()
    base = compute()
    options = {
        name: _route_options(plans[name])
        for name in base["blocked_operations"]
    }
    per_operation = {
        name: min((len(option) for option in choices), default=0)
        for name, choices in options.items()
    }
    # 全部解锁 = 每个 Operation 各选一个选项、取**并集**最小（选项数很小 ⇒ 直接穷举）
    best: tuple[int, ...] | None = None
    for combo in itertools.product(*options.values()):
        union = frozenset().union(*combo)
        size = len(union)
        if best is None or size < best[0]:
            best = (size, *sorted(union))
    return {
        "per_operation": dict(sorted(per_operation.items())),
        "all": list(best[1:]) if best else [],
        "all_count": best[0] if best else 0,
    }


def gate_attribution() -> dict[str, Any]:
    """「**卡在谁**」：按**机械性质**给每个挡点端点标注责任方（**零请求**，R166）。

    为什么需要它（**R166**）
    -----------------------
    `--benefit` 算清了「收口它 ⇒ 解锁谁」，但**收益 ≠ 可实施性**：`DESIGN.CONCRETE` 与
    `DESIGN.SRC` 的**最短选项各含一个** `*-ANAL`，而那是**实测崩溃族**（R154 登记在
    `NATIVE_CRASH_ENDPOINTS`）⇒ 谁修得动它**决定**了这格的代价。
    ⇒ 把「谁能修」也**算**出来，**不**手写（R158 / R165 的教训）。

    判据（**机械**，逐条可复算）
    ----------------------------
    1. 端点 ∈ `NATIVE_CRASH_ENDPOINTS` ⇒ `midas` 侧（崩溃在 `wg_db.dll`，我方**不**可规避）。
       ⚠️ 区分 `NATIVE_CRASH_MEASURED`（**实测**）与同族推定（`conjectured`）—— **不**混为一谈。
    2. 否则，**最短路线**（`--benefit` 的选项里**最小**的那个）里若有 `*-ANAL` ⇒ 该表的**数据**
       只能由那个 `*-ANAL` 产出（ANAL = 执行分析并写设计结果，`registry/design/rc/…/*-ANAL.yaml` 的
       标题逐字：`RC Beam Design **Perform**`；`BD-TABLE.yaml` = `RC Beam Design **Table**`）
       ⇒ 卡在 `midas`（同一条崩溃边），**不是**「独立的一格代价」。
    3. 其余 ⇒ `ours` 侧（先证明**请求体来源**成立，再**授权测量**）。
       ⚠️ 当前**唯一**待做的我方路径 = `POST.STEELCODECHECK`（`steel` 路由**无** `*-ANAL`）。
    ⚠️ 本函数**只**分类 —— **不**判「值不值得做」（那是裁决，见 `README.md` §8.28）。
    """
    plans, _registry, (_verified, crash_endpoints) = _load()
    sys.path.insert(0, str(REPO))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        NATIVE_CRASH_MEASURED,
    )

    base = compute()
    benefit = benefit_mapping()
    cost = minimal_unlock_cost()
    options = {
        name: _route_options(plans[name]) for name in base["blocked_operations"]
    }
    rows: dict[str, dict[str, Any]] = {}
    for endpoint in sorted(base["blocker_endpoints"]):
        # 该端点**参与**的最短选项（收口它 + 同选项里其余的端点）—— 「代价」的正确口径
        cheapest: frozenset[str] | None = None
        for choices in options.values():
            for option in choices:
                if endpoint not in option:
                    continue
                if cheapest is None or len(option) < len(cheapest):
                    cheapest = option
        if endpoint in crash_endpoints:
            side = "midas"
            reason = (
                "实测崩溃族（R154：GenNX.exe @ wg_db.dll）"
                if endpoint in NATIVE_CRASH_MEASURED
                else "同族推定崩溃族的成员（R154 / R153 的全查口径）"
            )
        elif cheapest is not None and any(step in crash_endpoints for step in cheapest):
            side = "midas"
            reason = (
                "单独收口**不**解锁任何 Operation ⇒ 本格不是独立代价；"
                "其设计结果只能由同选项内的崩溃族 `*-ANAL` 产出（R166）"
            )
        else:
            side = "ours"
            reason = "路由内**无** `*-ANAL`；前置 = 请求体来源成立 + 一次授权测量"
        rows[endpoint] = {
            "side": side,
            "reason": reason,
            "blocked_operations": [
                name
                for name, endpoints in base["blocked_operations"].items()
                if endpoint in endpoints
            ],
            "own_benefit": benefit["endpoints"][endpoint]["unlocks"],
            "minimal_option": sorted(cheapest) if cheapest is not None else [],
            "minimal_option_size": len(cheapest) if cheapest is not None else 0,
        }
    # **唯一**不依赖崩溃族 `*-ANAL` 的边（我方独有杠杆）
    ours = sorted(key for key, row in rows.items() if row["side"] == "ours")
    base_document = compute()
    # 反事实：把崩溃族**全部**修好（假设）⇒ 主指标**仍**不变 ⇒ 证明「卡在 MIDAS 侧」是**结构**性的
    after_crash = compute(pretend_verified=crash_endpoints)
    above = {
        name: {
            "cost": cost["per_operation"][name],
            "option_has_crash": any(
                step in crash_endpoints for option in options[name] for step in option
            ),
        }
        for name in base_document["blocked_operations"]
    }
    return {
        "endpoints": rows,
        "ours": ours,
        "midas": sorted(key for key, row in rows.items() if row["side"] == "midas"),
        "above_operations": above,
        "fixing_all_crash_yields": after_crash["available"],
        "fixing_all_crash_still_blocked": sorted(after_crash["blocked_operations"]),
    }


def check() -> int:
    """`--check`：断言主指标与**已裁定**的值逐条一致（**零请求**）。"""
    document = compute()
    problems: list[str] = []
    if document["available"] != EXPECTED_AVAILABLE:
        problems.append(
            f"可用数 {document['available']} != 已裁定 {EXPECTED_AVAILABLE} "
            "（改动它必须同时改 README §1.1 / §5.1 与 docs/07 R158）"
        )
    blocked = set(document["blocked_operations"])
    if blocked != set(EXPECTED_BLOCKED):
        problems.append(f"被挡清单与裁定不符：多 {sorted(blocked - set(EXPECTED_BLOCKED))} / "
                        f"少 {sorted(set(EXPECTED_BLOCKED) - blocked)}")
    # **P172 / R165**：**收益映射**也必须与裁定一致 —— 它是**算**出来的，不是手写的
    benefit = benefit_mapping()
    for endpoint, expected in EXPECTED_BENEFIT.items():
        actual = benefit["endpoints"].get(endpoint)
        if actual is None:
            problems.append(f"收益映射缺 {endpoint}（它应是被挡端点）")
        elif actual["unlocks"] != sorted(expected):
            problems.append(
                f"{endpoint} 的收益 {actual['unlocks']} != 已裁定 {sorted(expected)}"
                "（改动它必须同时改 README §5.1 与 docs/07 R165）"
            )
    cost = minimal_unlock_cost()
    for name, expected in EXPECTED_MINIMAL_COST.items():
        actual = cost["per_operation"].get(name)
        if actual != expected:
            problems.append(
                f"解锁 {name} 的最小代价 {actual} != 已裁定 {expected}"
                "（改动它必须同时改 README §5.1 与 docs/07 R165）"
            )
    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    print(
        f"✅ 主指标自洽：生产路径可用 Operation **{document['available']} / {document['total']}**"
        f"（被挡 {document['blocked']} · 挡点端点 {document['blocker_endpoint_count']} 个 · "
        f"其中无 MIDAS 端点的 Operation {len(document['endpoint_free_operations'])} 个）"
    )
    return 0


def main() -> int:
    """入口（默认只打印；`--json` 出结构化；`--check` 断言）。"""
    parser = argparse.ArgumentParser(description="主指标：生产路径可用 Operation")
    parser.add_argument("--check", action="store_true", help="断言与裁定一致（零请求）")
    parser.add_argument("--benefit", action="store_true", help="逐端点收益（收口它 ⇒ 解锁谁）")
    parser.add_argument(
        "--attribution", action="store_true", help="逐端点「卡在谁」（我方 / MIDAS 侧 / 产品侧）"
    )
    parser.add_argument("--json", action="store_true", help="输出结构化结果")
    parser.add_argument("--out", default="", help="把结构化结果写到该路径")
    args = parser.parse_args()
    if args.check:
        return check()
    if args.attribution:
        table = gate_attribution()
        if args.json or args.out:
            text = json.dumps(table, ensure_ascii=False, indent=1) + "\n"
            if args.out:
                pathlib.Path(args.out).write_text(text, encoding="utf-8")
                print(f"wrote {args.out}")
            else:
                print(text)
            return 0
        print("=== 逐端点「卡在谁」（我方 / MIDAS 侧）—— 责任方由**机械性质**判，不手写 ===")
        for endpoint, row in table["endpoints"].items():
            side = "我方" if row["side"] == "ours" else "MIDAS 侧"
            own = ", ".join(row["own_benefit"]) or "（无）"
            print(f"  [{side:8s}] {endpoint:44s} 单独收益：{own}")
            print(f"             理由：{row['reason']}")
            print(
                f"             最短选项（{row['minimal_option_size']} 个）："
                + (", ".join(row["minimal_option"]) or "（无）")
            )
        print()
        print("=== 被挡 Operation 的「上方闸门」===")
        for name, row in table["above_operations"].items():
            crash = "含崩溃族 `*-ANAL`" if row["option_has_crash"] else "**不**含崩溃族"
            print(f"  {name:22s} 最短代价 {row['cost']} 个端点 · 最短选项{crash}")
        print()
        print(f"⚠️ 反事实（假设**崩溃族全部修好**；纯内存仿真、**零请求**）"
              f"⇒ 主指标仍 `{table['fixing_all_crash_yields']} / 71`"
              f"（被挡 {len(table['fixing_all_crash_still_blocked'])} 个："
              f"{', '.join(table['fixing_all_crash_still_blocked'])}）")
        print("    ⇒ `*-TABLE` 要**先有设计结果**，而那结果只能由崩溃族的 `*-ANAL` 产出 ⇒ "
              "**不是**独立的一格代价")
        print(f"✅ **我方**唯一不依赖 `*-ANAL` 的可自己拿下的一格：{', '.join(table['ours'])}")
        return 0
    if args.benefit:
        table = benefit_mapping()
        if args.json or args.out:
            text = json.dumps(table, ensure_ascii=False, indent=1) + "\n"
            if args.out:
                pathlib.Path(args.out).write_text(text, encoding="utf-8")
                print(f"wrote {args.out}")
            else:
                print(text)
            return 0
        print("=== 逐端点收益（收口**这一个** ⇒ 解锁哪些 Operation）===")
        for endpoint, row in table["endpoints"].items():
            unlocks = ", ".join(row["unlocks"]) or "（无）"
            print(f"  {row['blocks']:2d} 个 Operation  {endpoint:44s} "
                  f"⇒ {len(row['unlocks'])} 个：{unlocks}")
        print()
        print(f"收益**恰好为 0** 的端点（{len(table['zero_benefit'])} 个）：")
        for endpoint in table["zero_benefit"]:
            print(f"  {endpoint}")
        print()
        cost = minimal_unlock_cost()
        print("=== 最小解锁代价（**不是**「挡点个数」）===")
        for name, size in cost["per_operation"].items():
            print(f"  解锁 {name:22s} 最少要收口 {size} 个端点")
        print(f"  解锁**全部** {len(cost['per_operation'])} 个最少要收口 "
              f"{cost['all_count']} 个：")
        for endpoint in cost["all"]:
            print(f"      {endpoint}")
        return 0
    document = compute()
    if args.json or args.out:
        text = json.dumps(document, ensure_ascii=False, indent=1) + "\n"
        if args.out:
            pathlib.Path(args.out).write_text(text, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(text)
        return 0
    print(f"产品 {document['product']} · Operation 总数 {document['total']}")
    print(f"生产路径**可用** = {document['available']} / {document['total']}"
          f"（被挡 {document['blocked']}）")
    print(f"无 MIDAS 端点的 Operation（不因端点被挡）= {document['endpoint_free_operations']}")
    print()
    print("=== 被挡的 Operation ===")
    for name, endpoints in document["blocked_operations"].items():
        print(f"  {name:26s} <- {len(endpoints)} 个端点")
    print()
    print("=== 挡点端点（→ 挡住几个 Operation）===")
    for endpoint, count in document["blocker_endpoints"].items():
        print(f"  {count:2d}  {endpoint}")
    print()
    cost = minimal_unlock_cost()
    print("=== 最小解锁代价（`routes` 是**替代**路线 ⇒ **不是**「挡点个数」）===")
    for name, size in cost["per_operation"].items():
        print(f"  解锁 {name:22s} 最少要收口 {size} 个端点")
    print(f"  解锁**全部**最少 {cost['all_count']} 个端点"
          f"（挡点**个数** = {document['blocker_endpoint_count']} —— 两者**不是**一回事）")
    print("  逐端点收益见 `--benefit`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
