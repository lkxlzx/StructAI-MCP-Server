"""主指标**可执行化**：**生产路径可用 Operation**（`docs/07` §15.6.3 的主指标）。

为什么需要这个工具（**R158**）
------------------------------
`README.md` §1.1 的 `62 / 71` 是**手写**的，于是漂了：它把 `DESIGN.CODE_CHECK` 算成**可用**，
而该 Operation 的 **7 条路由全部被挡**（`steel` 路由的末步 `POST.STEELCODECHECK` 是 `PARTIAL`；
`concrete:*` 需 `BD/CD/BRD/WD-ANAL`（**原生崩溃护栏**）；`src:*` 需 `SRC.{BC,CC}-ANAL`（同））。
⇒ 真实值是 **61 / 71**。**手写的指标必然漂** ⇒ 把它变成**可执行判定**（本工具 + `--check`）。

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

EXPECTED_AVAILABLE: Final[int] = 61
"""**已裁定**的可用数（`docs/07` §16.1 **R158**）。改动它 = 改主指标 ⇒ 必须同时改文档。"""

EXPECTED_BLOCKED: Final[tuple[str, ...]] = (
    "DESIGN.CODE_CHECK",
    "DESIGN.CONCRETE",
    "DESIGN.SRC",
    "RESULT.ANALYSIS.SUMMARY",
    "VIEW.DEFORMED_MODEL",
    "VIEW.DISPLACEMENT",
    "VIEW.FORCE",
    "VIEW.MODE_SHAPE",
    "VIEW.REACTION",
    "VIEW.STRESS",
)
"""**已裁定**的被挡 Operation（**10** 个；顺序无关）。"""


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


def compute() -> dict[str, Any]:
    """算主指标（**纯函数**，便于测试复算）。"""
    plans, registry, (verified, crash_endpoints) = _load()

    def blocker_of(step: Any) -> str | None:
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
    parser.add_argument("--json", action="store_true", help="输出结构化结果")
    parser.add_argument("--out", default="", help="把结构化结果写到该路径")
    args = parser.parse_args()
    if args.check:
        return check()
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
