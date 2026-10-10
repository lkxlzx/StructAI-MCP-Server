"""P149-A：端点 `methods` 的**实测修正**与写路径分母重算（可执行判定）。

权威来源
--------
- `docs/reports/P149-A_端点方法集实测修正与分母重算_v1.0.md`（本批证据）。
- `docs/07` §16.1 **R108**（本批新增：registry 曾**系统性少声明**端点方法集）。
- `registry/live/live_methods.json`（**实测证据**：只读 `OPTIONS` 的 `Allow` 头）·
  `registry/tools/sync_endpoint_methods.py`（`--probe` / `--write` / `--check`）。

本文件的**可执行判定**
--------------------
1. **证据完整**：证据文件覆盖 **636** 个端点；`live_methods` 为空（本 build 路由不存在）**72** 个。
2. **复算一致**：`sync_endpoint_methods.py --check` 退出码 0（已落盘 == 机械结果，无待写回项）。
3. **只增不减已归零**：对每个 `live_methods` 非空的端点，`registry.methods ⊆ live_methods`
   （即 registry **不再**少声明任何方法）；且 `live_methods` 里的 `HEAD` 一律已剔除。
4. **404 端点未被改动**：`live_methods` 为空的 72 个端点仍保留 registry 里的方法集
   （**不**因为一次探测而清零）。
5. **新基线**：`write_path_keys()` = **633**（原 609）· `write_only_keys()` = **306**（原 368）·
   `result_query_keys()` = **199**（不变）· `model_write_keys()` = **434**（原 410）。
6. **候选集与阻塞数**：GEN NX **58** / CIVIL NX **49** / CD **0**；blocked **515 / 451 / 31**。
7. **`DB.SWIND`** 由「无方法」进入写路径分母（四方法齐全）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.infrastructure.adapters.midas.live import (
    model_write_keys,
    result_query_keys,
    write_only_keys,
    write_path_keys,
)
from app.infrastructure.adapters.midas.transforms import TRANSFORMER_REGISTRY
from app.infrastructure.adapters.midas.write_probe import (
    WRITE_METHODS,
    transformer_name_for,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录（数据侧工具与证据文件都在这里）。"""

EVIDENCE_PATH = REPO_ROOT / "registry" / "live" / "live_methods.json"
"""实测证据文件（只读 `OPTIONS` 的 `Allow` 头）。"""

TOOL_PATH = REPO_ROOT / "registry" / "tools" / "sync_endpoint_methods.py"
"""复算工具（`--probe` / `--write` / `--check`）。"""

EVIDENCE_TOTAL = 636
"""证据文件覆盖的端点数（= `registry/manifest.json` 的条目数）。"""

ROUTE_ABSENT_TOTAL = 72
"""本 build 上路由不存在的端点数（`OPTIONS` 无 `Allow` 且 `HEAD` 404）。"""

WRITE_PATH_TOTAL = 633
"""写路径分母（P149-A 起；P148 为 609 —— 原被漏算 24 个写路径端点）。"""

WRITE_ONLY_TOTAL = 306
"""分母里「连 `GET` 都没有」的部分（P148 为 368）。"""

MODEL_WRITE_TOTAL = 434
"""分母里的「模型写」子桶（P148 为 410）。"""

RESULT_QUERY_TOTAL = 199
"""分母里的「结果表 / 文本查询」子桶（不变）。"""

CANDIDATES_BY_PRODUCT: dict[str, int] = {"GEN_NX": 58, "CIVIL_NX": 49, "CIVIL_DESIGNER": 0}
"""三产品候选集（P149-A **不变** —— 新解锁的端点仍缺数据侧模板）。"""

BLOCKED_TOTAL: dict[str, int] = {"GEN_NX": 515, "CIVIL_NX": 451, "CIVIL_DESIGNER": 31}
"""「有写方法 + 非危险形态，但既无 Transformer 又无数据侧模板」的端点数。"""

SWIND_KEY = "DB.SWIND"
"""P148 时**没有**任何方法（被漏出分母）；P149-A 由实测修正为四方法齐全。"""


def _registry():
    """数据侧 Registry（`registry/` 的唯一权威来源）。"""
    import midas_p119_p126_support as support

    return support.registry()


def _evidence() -> dict[str, object]:
    """实测证据文件原文。"""
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def _candidates(registry, product: str) -> tuple[int, int]:
    """独立复算候选集与 blocked（**不**调用 `candidate_keys`）。"""
    candidates = 0
    blocked = 0
    for key in registry.keys():
        definition = registry.endpoint(key)
        if product not in definition.products or not definition.enabled:
            continue
        methods = registry.methods_for(key=key, product=product)
        if not any(method in methods for method in WRITE_METHODS):
            continue
        try:
            resolved = registry.resolve(key=key, product=product)
        except Exception:  # noqa: BLE001 - 该产品不可得
            continue
        if definition.destructive or resolved.delete_all_via_body:
            continue
        has_source = (
            TRANSFORMER_REGISTRY.get(transformer_name_for(key)) is not None
            or registry.write_template(key) is not None
        )
        if not has_source:
            blocked += 1
            continue
        if "GET" not in methods or not definition.read_root or "DELETE" not in methods:
            continue
        candidates += 1
    return candidates, blocked


# ===== 1. 证据完整（判定 1）=====


def test_p149a_the_evidence_covers_every_endpoint() -> None:
    """门槛：证据文件覆盖 636 个端点；`live_methods` 为空的（本 build 路由不存在）**72** 个。"""
    document = _evidence()
    endpoints = document["endpoints"]
    assert isinstance(endpoints, dict)
    assert len(endpoints) == EVIDENCE_TOTAL
    absent = {key for key, item in endpoints.items() if not item["live_methods"]}
    assert len(absent) == ROUTE_ABSENT_TOTAL
    # 每个 `Allow` 都不含框架自动方法 `HEAD`
    for item in endpoints.values():
        assert "HEAD" not in item["live_methods"], item["uri"]
    # 证据里记了原生状态码（`OPTIONS` 一定被发过）
    assert all(item["options_status"] for item in endpoints.values())


# ===== 2. 复算一致（判定 2）=====


def test_p149a_the_tool_check_is_green() -> None:
    """门槛：`sync_endpoint_methods.py --check` 退出码 0（已落盘 == 机械结果）。"""
    completed = subprocess.run(  # noqa: S603
        [sys.executable, str(TOOL_PATH), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stdout[-800:]
    assert "✅" in completed.stdout


# ===== 3. 只增不减已归零（判定 3 / 4）=====


def test_p149a_no_endpoint_under_declares_its_methods_any_more() -> None:
    """门槛：`live_methods` 非空的端点，registry 的方法集**不再**少声明任何方法。"""
    registry = _registry()
    endpoints = _evidence()["endpoints"]
    offenders: list[tuple[str, list[str], list[str]]] = []
    for key, item in endpoints.items():
        live = set(item["live_methods"])
        if not live:
            continue
        declared = set(registry.methods_for(key=key, product="GEN_NX"))
        if live - declared:
            offenders.append((key, sorted(declared), sorted(live)))
    assert offenders == []


def test_p149a_absent_routes_keep_their_declared_methods() -> None:
    """门槛：路由不存在的 72 个端点**未**被清零（一次探测**不**削掉有据可查的方法集）。"""
    registry = _registry()
    endpoints = _evidence()["endpoints"]
    absent = [key for key, item in endpoints.items() if not item["live_methods"]]
    assert len(absent) == ROUTE_ABSENT_TOTAL
    for key in absent:
        declared = registry.methods_for(key=key, product="GEN_NX")
        assert declared, key


# ===== 4. 新基线（判定 5 / 6 / 7）=====


def test_p149a_the_denominator_and_sub_buckets_are_recounted() -> None:
    """门槛：分母 **633**（`write_only` 306 · `result_query` 199 · `model_write` 434）。"""
    registry = _registry()
    assert len(write_path_keys(registry)) == WRITE_PATH_TOTAL
    assert len(write_only_keys(registry)) == WRITE_ONLY_TOTAL
    assert len(result_query_keys(registry)) == RESULT_QUERY_TOTAL
    assert len(model_write_keys(registry)) == MODEL_WRITE_TOTAL


def test_p149a_swind_enters_the_denominator() -> None:
    """门槛：`DB.SWIND` 由「无方法」变为四方法齐全，因而进入写路径分母。"""
    registry = _registry()
    methods = set(registry.methods_for(key=SWIND_KEY, product="GEN_NX"))
    assert {"POST", "GET", "PUT", "DELETE"} <= methods
    assert SWIND_KEY in set(write_path_keys(registry))
    assert SWIND_KEY in set(model_write_keys(registry))


def test_p149a_the_candidate_gate_is_unchanged_and_blocked_grows() -> None:
    """门槛：候选集仍 **58 / 49 / 0**；blocked 随方法集修正升为 **515 / 451 / 31**。"""
    registry = _registry()
    for product, expected in CANDIDATES_BY_PRODUCT.items():
        candidates, blocked = _candidates(registry, product)
        assert candidates == expected, product
        assert blocked == BLOCKED_TOTAL[product], product
