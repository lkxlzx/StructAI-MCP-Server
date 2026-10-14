"""P164-c（事故驱动）—— **原生崩溃护栏**：已实测会打崩宿主程序的端点必须拦在发请求之前。

事故
----
`DESIGN.RC.KDS-41-20-2022.BD-ANAL` 让 **MIDAS Gen NX 26.9.1.1001 直接终止**：

```text
Faulting module : wg_db.dll (1.0.0.1)
Exception code  : 0xc0000005（访问违例）
Fault offset    : 0x2d97e5c      ← 四次实测完全相同
恢复文件        : E:\\MCP\\MMCP\\.tmp_p164c\\p164c-concrete_restore.mgbx
```

**四次**用的请求体**各不相同**（① 小写 canonical 键 · ② `PERFORM_TYPE="ALL"` + `ELEMS`
自相矛盾 · ③ 手册 `BD-ANAL` 文章的逐字示例 · ④ 关掉抗震后的同形体）
⇒ 崩溃**与请求体无关**，是原生设计引擎的缺陷。

本文件钉住的事实
----------------
1. **实测端点只有 1 个**（`NATIVE_CRASH_MEASURED`）—— 其余同族是**推定**，不许混为一谈。
2. 护栏在 **`build_request` 里、发请求之前**生效（`allow_unverified=True` **也**拦得住）。
3. 两个开关**互相独立**：`allow_unverified`（没验过）≠ `allow_native_crash_risk`（验过、验出会崩）。
4. 编排里**确实**引用着被拦的端点（防「常量与编排各说各话」的漂移）。
5. ⚠️ **`build_request` 不是唯一发送面**：`MidasHttpClient` 还有**裸**的
   `post` / `put` / `delete` / `get` / `probe`（直接走 `_raw`）⇒ 护栏**也**挂在
   `_raw()`（唯一的发送汇合点）上，并按**路径**匹配（**实测缺口，已闭合**）。
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.infrastructure.adapters.midas.adapter import MidasAdapter
from app.infrastructure.adapters.midas.client import (
    NATIVE_CRASH_ENDPOINTS,
    NATIVE_CRASH_MEASURED,
    MidasHttpClient,
    guard_native_crash,
    guard_native_crash_path,
    native_crash_key_for_path,
    native_crash_paths,
)
from app.infrastructure.adapters.midas.errors import MidasNativeCrashRisk
from app.infrastructure.adapters.midas.operations import plan_for
from app.infrastructure.adapters.midas.registry import MidasRegistry

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
"""仓库根目录。"""

MEASURED = "DESIGN.RC.KDS-41-20-2022.BD-ANAL"
"""**唯一**实测把 MIDAS Gen NX 打崩的端点（四次，同一偏移）。"""

SUSPECTED_FAMILY: tuple[str, ...] = (
    # RC 设计执行
    "DESIGN.RC.KDS-41-20-2022.CD-ANAL",
    "DESIGN.RC.KDS-41-20-2022.BRD-ANAL",
    "DESIGN.RC.KDS-41-20-2022.WD-ANAL",
    # RC 校核执行（同原生模块、同调用形态）
    "DESIGN.RC.KDS-41-20-2022.BC-ANAL",
    "DESIGN.RC.KDS-41-20-2022.CC-ANAL",
    "DESIGN.RC.KDS-41-20-2022.BRC-ANAL",
    "DESIGN.RC.KDS-41-20-2022.WC-ANAL",
    "DESIGN.RC.KDS-41-20-2022.HCD-ANAL",
    # SRC 执行
    "DESIGN.SRC.AIK-SRC2K.BC-ANAL",
    "DESIGN.SRC.AIK-SRC2K.CC-ANAL",
)
"""同族推定（同一原生设计引擎入口、同一 `Argument` + `PERFORM_TYPE` / `ELEMS` 形态）
—— **10** 个，**未**实测。⚠️ 见 `NATIVE_CRASH_ENDPOINTS` 的「覆盖口径」：
manifest 里恰好 **12** 个 `*-ANAL`，本名单收 **11** 个（含实测的 1 个），
唯一排除的是**真机跑通**的钢铁 `CODE-ANAL`。"""


def _registry() -> MidasRegistry:
    return MidasRegistry.load(REPO_ROOT / "registry")


def _client() -> MidasHttpClient:
    """离线客户端（`http://example.invalid` ⇒ 真发也发不出去，用于证明**零请求**）。"""
    return MidasHttpClient("http://example.invalid", lambda: "unused", "TEST_REF")


# ===== 1. 「实测」与「推定」必须分开 =====


def test_p164c_only_one_endpoint_is_actually_measured() -> None:
    """门槛：`NATIVE_CRASH_MEASURED` **恰好**是四次实测的那一个（不许把推定写成实测）。"""
    assert NATIVE_CRASH_MEASURED == frozenset({MEASURED}), NATIVE_CRASH_MEASURED
    assert set(SUSPECTED_FAMILY) <= NATIVE_CRASH_ENDPOINTS
    assert NATIVE_CRASH_MEASURED.isdisjoint(SUSPECTED_FAMILY)


# ===== 2. 护栏本身：拦在发请求之前，且区分「实测 / 推定」 =====


def test_p164c_the_measured_endpoint_is_blocked_with_measured_true() -> None:
    """门槛：实测端点 ⇒ `MidasNativeCrashRisk`，`details.measured is True`。"""
    resolved = _registry().resolve(key=MEASURED, product="GEN_NX")
    with pytest.raises(MidasNativeCrashRisk) as caught:
        guard_native_crash(resolved)
    details = caught.value.details or {}
    assert details.get("reason") == "native_crash_risk", details
    assert details.get("measured") is True, details
    assert details.get("endpoint") == MEASURED, details
    assert details.get("stage") == "midas_adapter", details


@pytest.mark.parametrize("key", SUSPECTED_FAMILY)
def test_p164c_the_suspected_family_is_blocked_with_measured_false(key: str) -> None:
    """门槛：同族推定 ⇒ **也**拦，但 `details.measured is False`（诚实标注）。"""
    resolved = _registry().resolve(key=key, product="GEN_NX")
    with pytest.raises(MidasNativeCrashRisk) as caught:
        guard_native_crash(resolved)
    details = caught.value.details or {}
    assert details.get("measured") is False, details
    assert details.get("endpoint") == key, details


def test_p164c_a_normal_endpoint_is_not_affected_by_the_guard() -> None:
    """门槛：**窄**规则 —— 不在名单里的端点一律放行（避免误伤）。"""
    registry = _registry()
    for key in ("DB.NODE", "DOC.ANAL", "DESIGN.RC.KDS-41-20-2022.DCO"):
        guard_native_crash(registry.resolve(key=key, product="GEN_NX"))


# ===== 3. 护栏接在 `build_request` 上：**零请求** =====


def test_p164c_the_guard_fires_before_any_request_even_in_contract_test_mode() -> None:
    """门槛（**事故现场复现**）：`allow_unverified=True`（P164-c 用的口径）**也**拦得住。

    ⇒ 这一次**不会**再有请求发到原生设计引擎 ⇒ 用户的 MIDAS **不会**被打崩。
    """
    resolved = _registry().resolve(key=MEASURED, product="GEN_NX")
    with pytest.raises(MidasNativeCrashRisk):
        _client().build_request(
            resolved,
            operation="DESIGN.CONCRETE",
            body={"PERFORM_TYPE": "ELEMS", "ELEMS": {"KEYS": [1, 2, 3]}},
            wrapper="Argument",
            allow_unverified=True,
        )


def test_p164c_the_override_is_a_separate_explicit_switch() -> None:
    """门槛：两个开关**互相独立** —— 放开「没验过」**不**等于放开「验出会崩」。"""
    resolved = _registry().resolve(key=MEASURED, product="GEN_NX")
    client = _client()
    # 只放开 allow_unverified ⇒ **仍**拦
    with pytest.raises(MidasNativeCrashRisk):
        client.build_request(
            resolved,
            operation="DESIGN.CONCRETE",
            wrapper="Argument",
            body={"PERFORM_TYPE": "ELEMS"},
            allow_unverified=True,
        )
    # 显式再放开 allow_native_crash_risk ⇒ 放行（请求**构造**成功，但**不**发）
    request = client.build_request(
        resolved,
        operation="DESIGN.CONCRETE",
        wrapper="Argument",
        body={"PERFORM_TYPE": "ELEMS", "ELEMS": {"KEYS": [1, 2, 3]}},
        allow_unverified=True,
        allow_native_crash_risk=True,
    )
    assert request.endpoint == MEASURED, request.endpoint
    assert request.method == "POST", request.method


def test_p164c_the_adapter_defaults_to_blocking() -> None:
    """门槛：`MidasAdapter` **默认**拦死；`allow_unverified=True` **不**改变这一点。"""
    assert MidasAdapter().allow_native_crash_risk is False
    assert MidasAdapter(allow_unverified=True).allow_native_crash_risk is False
    assert MidasAdapter(allow_native_crash_risk=True).allow_native_crash_risk is True


# ===== 3b. **裸路径**也拦得住（`build_request` **不是**唯一发送面）=====


def test_p164c_the_derived_paths_match_the_registry_uris() -> None:
    """门槛（**防漂移**）：由端点键推导出的路径 == `registry` 里的**实际** `uri`。

    ⚠️ 护栏在裸路径上按 `path` 匹配 ⇒ 推导规则一旦与数据侧不符，护栏**静默失效**。
    """
    registry = _registry()
    derived = native_crash_paths()
    assert len(derived) == len(NATIVE_CRASH_ENDPOINTS), derived
    for key in sorted(NATIVE_CRASH_ENDPOINTS):
        actual = registry.resolve(key=key, product="GEN_NX").uri
        assert f"/{key.replace('.', '/')}" == actual, (key, actual)
        assert actual in derived, (key, actual)
        assert native_crash_key_for_path(actual) == key, actual


def test_p164c_the_path_guard_is_case_and_slash_insensitive() -> None:
    """门槛：路径归一化 —— 大小写 / 多余斜杠 / 空白都**不**能成为绕过手段。"""
    assert native_crash_key_for_path("/DESIGN/RC/KDS-41-20-2022/BD-ANAL") == MEASURED
    assert native_crash_key_for_path("DESIGN/RC/KDS-41-20-2022/BD-ANAL/") == MEASURED
    assert native_crash_key_for_path("  /design/rc/kds-41-20-2022/bd-anal  ") == MEASURED
    assert native_crash_key_for_path("/DB/NODE") is None


@pytest.mark.parametrize("verb", ["post", "put", "delete", "get", "probe"])
async def test_p164c_the_raw_helpers_cannot_bypass_the_guard(verb: str) -> None:
    """门槛（**实测缺口已闭合**）：裸 `post`/`put`/`delete`/`get`/`probe` **同样**被拦。

    ⚠️ 这五条**不**经过 `build_request` ⇒ 修复前一次 `client.post(<崩溃路径>, …)`
    就能把 MIDAS 打崩。判据 = **零请求**：凭据**一次都没取**（说明没走到 `_raw` 的发送体）。
    """
    calls: list[str] = []

    class _CountingCredentials:
        async def get_secret(self, reference: str) -> str:
            calls.append(reference)
            return "unused"

    client = MidasHttpClient("http://example.invalid", _CountingCredentials(), "TEST_REF")
    crash_path = f"/{MEASURED.replace('.', '/')}"
    with pytest.raises(MidasNativeCrashRisk) as caught:
        method = getattr(client, verb)
        if verb in {"post", "put"}:
            await method(crash_path, json_body={"PERFORM_TYPE": "ELEMS"})
        else:
            await method(crash_path)
    details = caught.value.details or {}
    assert details.get("reason") == "native_crash_risk", details
    assert details.get("via") == "raw_path", details
    assert details.get("endpoint") == MEASURED, details
    assert details.get("measured") is True, details
    assert calls == [], f"护栏必须拦在取凭据之前（否则已经走到发送体）：{calls}"


def test_p164c_the_raw_helpers_still_work_for_normal_paths() -> None:
    """门槛（**窄**规则）：非崩溃族路径的裸请求**不**受影响（不误伤 L4 只读探针）。"""
    for path in ("/DB/NODE", "/DOC/ANAL", "/VIEW/CAPTURE", "/DESIGN/RC/KDS-41-20-2022/DCO"):
        guard_native_crash_path(path)


def test_p164c_the_raw_path_guard_has_an_explicit_override() -> None:
    """门槛：裸路径也能被**显式**放开（要重跑实测的唯一入口）。"""
    guard_native_crash_path(f"/{MEASURED.replace('.', '/')}", allow_native_crash_risk=True)


# ===== 4. 常量与编排 / manifest 不许各说各话 =====


def _manifest_anal_keys() -> set[str]:
    """`registry/manifest.json` 里**全部** `*-ANAL` 端点键（覆盖口径的**真源**）。"""
    manifest = json.loads((REPO_ROOT / "registry" / "manifest.json").read_text(encoding="utf-8"))
    endpoints = manifest["endpoints"]
    keys = [entry["key"] for entry in endpoints] if isinstance(endpoints, list) else list(endpoints)
    return {key for key in keys if str(key).endswith("-ANAL")}


def test_p164c_the_guard_covers_every_rc_and_src_anal_endpoint_in_the_manifest() -> None:
    """门槛（**同族全查** —— R153 的教训）：manifest 里 `DESIGN.{RC,SRC}` 的 `*-ANAL`
    **一个不漏**地在本名单里；**唯一**排除的是**真机实测跑通**的钢铁 `CODE-ANAL`。

    ⚠️ 这条把「覆盖口径」变成**可复算**的：日后新增一个 RC/SRC 的 `*-ANAL` 端点
    ⇒ 本用例**先红**，**不**允许静默漏拦（漏拦的代价 = 打崩用户的软件）。
    """
    manifest_keys = _manifest_anal_keys()
    assert len(manifest_keys) == 12, sorted(manifest_keys)
    design_execution = {
        key for key in manifest_keys if key.startswith(("DESIGN.RC.", "DESIGN.SRC."))
    }
    assert design_execution == set(NATIVE_CRASH_ENDPOINTS), sorted(
        design_execution ^ set(NATIVE_CRASH_ENDPOINTS)
    )
    # 反向：钢铁的 `CODE-ANAL` **必须**留在名单外（旗舰链真机 12/12 跑通）
    steel = {key for key in manifest_keys if key.startswith("DESIGN.STEEL.")}
    assert steel == {"DESIGN.STEEL.KDS-41-30-2022.CODE-ANAL"}, steel
    assert steel.isdisjoint(NATIVE_CRASH_ENDPOINTS), "把能用的端点拦掉 = 过度防护"


def test_p164c_every_design_execution_step_in_the_plans_is_guarded() -> None:
    """门槛：编排里**每一个** `DESIGN.RC.*` / `DESIGN.SRC.*` 的 `*-ANAL` 步都在名单里。

    ⚠️ 反向也钉住：**钢铁**的 `CODE-ANAL` **不在**名单里（旗舰链 12/12 实测跑通 ⇒
    把它一起拦掉就是**过度**防护，会把能用的功能关掉）。
    """
    keys: set[str] = set()
    for operation in ("DESIGN.CONCRETE", "DESIGN.SRC", "DESIGN.CODE_CHECK"):
        plan = plan_for(operation)
        assert plan is not None, operation
        for step in plan.steps:
            keys.add(step.key)
        for route in plan.routes.values():
            for step in route:
                keys.add(step.key)

    design_execution = {
        key
        for key in keys
        if key.endswith("-ANAL") and key.startswith(("DESIGN.RC.", "DESIGN.SRC."))
    }
    assert design_execution <= set(NATIVE_CRASH_ENDPOINTS), sorted(
        design_execution - set(NATIVE_CRASH_ENDPOINTS)
    )
    assert "DESIGN.STEEL.KDS-41-30-2022.CODE-ANAL" in keys
    assert "DESIGN.STEEL.KDS-41-30-2022.CODE-ANAL" not in NATIVE_CRASH_ENDPOINTS


def test_p164c_the_endpoint_yamls_record_the_holdback() -> None:
    """门槛：**每一个**被拦端点的数据侧 YAML 头部都写明留缺（数据与代码不许各说各话）。"""
    directory = REPO_ROOT / "registry" / "design"
    files = sorted(directory.rglob("*-ANAL.yaml"))
    assert len(files) == 12, [str(path.name) for path in files]
    documented = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        key = next(
            line.split(":", 1)[1].strip().strip('"')
            for line in text.splitlines()
            if line.startswith("key:")
        )
        if key in NATIVE_CRASH_ENDPOINTS:
            documented += 1
            assert "P164-c" in text, key
            assert "guard_native_crash" in text, key
            assert "availability: untested" in text, key
    assert documented == len(NATIVE_CRASH_ENDPOINTS), documented


def test_p164c_the_data_side_ledger_records_the_holdback() -> None:
    """门槛：`registry/README.md` 的**数据侧账本**也记了这条留缺（§8.19）。

    ⚠️ 三处**必须**一致：`docs/07` §16.1 的裁决（R154）· 端点 YAML 头部 · **本账本**。
    只写一处 = 下一个会话按另一处行事。
    """
    text = (REPO_ROOT / "registry" / "README.md").read_text(encoding="utf-8")
    assert "### 8.19 P164-c / P164-d" in text, "数据侧账本缺 §8.19"
    assert "0x2d97e5c" in text, "崩溃偏移必须留在账本里"
    assert "wg_db.dll" in text, "故障模块必须留在账本里"
    assert "11" in text and "12" in text, "覆盖口径（12 个 *-ANAL 收 11 个）必须写明"
    assert "R154" in text and "R155" in text, "裁决编号必须可回溯"
    assert "availability" in text, "必须写明 availability 一行未改"


def test_p164c_the_report_records_four_identical_crashes() -> None:
    """门槛：留缺报告**如实**写着四次崩溃、同一偏移、`wg_db.dll`（不许写成三次）。"""
    report = (
        REPO_ROOT / "docs" / "reports" / "P164-c_分块2_DESIGN_CONCRETE原生崩溃留缺_v1.0.md"
    ).read_text(encoding="utf-8")
    assert "0x2d97e5c" in report, "崩溃偏移必须留在报告里"
    assert "wg_db.dll" in report, "故障模块必须留在报告里"
    assert "四次" in report, "第 4 次崩溃必须补进报告"
    assert "21:12:30" in report, "第 4 次崩溃的时刻必须留在报告里"
