"""P135d 验收：加固清单按软件判定 + R88 / R93 裁决。

权威来源
--------
- `docs/04` §149（Adapter Production Checklist）· §151（Production Hardening DoD，**19** 项）·
  §154（第二软件接入原则）。
- `docs/07` §3.2（依赖清单）· §14.5（扩展性口径）· §16（风险表 **R88** / **R93**）。
- `docs/02` §20（实例并发策略 `SERIAL` / `LIMITED` / `PARALLEL`）。

落地裁决（本文件的硬事实，不美化）
--------------------------------
1. **`docs/04` §151 的 19 项按软件分别判定**：MIDAS（`midas/hardening.py`）/
   ETABS（`etabs/hardening.py`）/ Mock（本文件逐条给出）三列**逐条**对应同一份清单；
   每项都有**可执行**判据（常量 / 模块 / 测试名），**不**允许只写「已支持」。
2. **R88 裁决落地**：COM 派发落点 = **独立 entry point 包**（标准库 `importlib.metadata`
   发现，group = `structai.adapters.etabs.dispatch`）**或**由部署方注入工厂；
   **不新增依赖**（`pyproject.toml` 不变）；缺 entry point 时 `connect()` 明确失败
   `STRUCTAI-2000`（`reason = "dispatch_not_configured"`），**不**伪造连接。
3. **R93 裁决落地**：`COM_SESSION_CONCURRENCY_SAFE = False` → `EtabsSerialConcurrencyPolicy`
   把 ETABS 实例的策略**强制**成 `SERIAL`（经**收窄契约**注入 Core 的 `Scheduler`，
   Core 一行未改）；本类**结构上**满足 `InstanceConcurrencyPolicySource`。
"""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from app.infrastructure.adapters.etabs import concurrency as etabs_concurrency
from app.infrastructure.adapters.etabs import dispatch as etabs_dispatch
from app.infrastructure.adapters.etabs.hardening import (
    COM_SESSION_CONCURRENCY_SAFE,
)
from app.infrastructure.adapters.etabs.hardening import (
    HARDENING as ETABS_HARDENING,
)
from app.infrastructure.adapters.etabs.hardening import (
    HARDENING_ITEMS as ETABS_ITEMS,
)
from app.infrastructure.adapters.etabs.hardening import (
    status_of as etabs_status_of,
)
from app.infrastructure.adapters.etabs.lifecycle import ComDispatch, ComSession
from app.infrastructure.adapters.midas.hardening import (
    HARDENING as MIDAS_HARDENING,
)
from app.infrastructure.adapters.midas.hardening import (
    HARDENING_ITEMS as MIDAS_ITEMS,
)
from app.infrastructure.adapters.midas.hardening import (
    status_of as midas_status_of,
)

HARDENING_ITEMS_SPEC: tuple[str, ...] = (
    "Connection pool",
    "Timeout",
    "Retry",
    "Circuit breaker",
    "Rate limit",
    "Concurrency",
    "Resource lock",
    "Credential rotation",
    "Secret redaction",
    "Structured logging",
    "Metrics",
    "Trace",
    "Audit",
    "Recovery",
    "Reconcile",
    "Contract test",
    "E2E",
    "Backup",
    "Version migration",
)
"""`docs/04` §151 的 **19** 项（逐字照抄）。"""

HARDENING_STATUSES_SPEC: frozenset[str] = frozenset({"IMPLEMENTED", "DELEGATED", "NOT_IMPLEMENTED"})
"""三种判定状态（`docs/07` §16 R88 的同一口径）。"""

MOCK_HARDENING: tuple[tuple[str, str], ...] = (
    ("Connection pool", "DELEGATED"),
    ("Timeout", "DELEGATED"),
    ("Retry", "DELEGATED"),
    ("Circuit breaker", "DELEGATED"),
    ("Rate limit", "DELEGATED"),
    ("Concurrency", "DELEGATED"),
    ("Resource lock", "DELEGATED"),
    ("Credential rotation", "DELEGATED"),
    ("Secret redaction", "IMPLEMENTED"),
    ("Structured logging", "DELEGATED"),
    ("Metrics", "DELEGATED"),
    ("Trace", "DELEGATED"),
    ("Audit", "DELEGATED"),
    ("Recovery", "DELEGATED"),
    ("Reconcile", "DELEGATED"),
    ("Contract test", "IMPLEMENTED"),
    ("E2E", "IMPLEMENTED"),
    ("Backup", "DELEGATED"),
    ("Version migration", "DELEGATED"),
)
"""Mock Adapter 一列：**无**网络 / 凭据 / 进程外资源，故绝大多数条目委派给 Core。

`Secret redaction` / `Contract test` / `E2E` 三项由 Mock 自身承担 —— 它的价值正是
让前两项可在 CI 上跑；`E2E` 的 L3 链由 `tests/test_e2e_p42_p48.py` 固定。
"""


class _Dispatcher:
    """最小 `ComDispatch` 实现（四方法齐备；测试替身，不是生产实现）。"""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.secret_seen: str | None = None

    async def attach(self, *, secret: str | None = None) -> None:
        self.calls.append("attach")
        self.secret_seen = secret

    async def detach(self) -> None:
        self.calls.append("detach")

    async def is_attached(self) -> bool:
        return True

    async def invoke(self, *, method: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append(f"invoke:{method}")
        return {"method": method, "argument_keys": len(arguments)}


class _Point:
    """`importlib.metadata.EntryPoint` 的最小替身（只保留 `name` / `load`）。"""

    def __init__(self, name: str, factory: Any) -> None:
        self.name = name
        self._factory = factory

    def load(self) -> Any:
        return self._factory


def _entry_points(*points: _Point) -> Any:
    """构造一个「只按 group 返回给定 entry point」的替身函数（**不**碰真实元数据）。"""

    def _fake(*, group: str) -> tuple[_Point, ...]:
        assert group == etabs_dispatch.DISPATCH_ENTRY_POINT_GROUP
        return points

    return _fake


# ===== P135d：`docs/04` §151 按软件判定 =====


def test_p135d_the_nineteen_items_are_identical_across_every_software() -> None:
    """三列**逐条**对应同一份 19 项清单（顺序不变）。"""
    assert HARDENING_ITEMS_SPEC == MIDAS_ITEMS == ETABS_ITEMS
    assert len(HARDENING_ITEMS_SPEC) == 19
    assert len(MIDAS_HARDENING) == len(ETABS_HARDENING) == 19
    assert tuple(item for item, _status in MOCK_HARDENING) == HARDENING_ITEMS_SPEC


def test_p135d_every_entry_has_a_status_and_a_non_empty_decision() -> None:
    """每项都有三态之一 + **非空**的可执行判据与理由（见裁决 1）。"""
    for entry in (*MIDAS_HARDENING, *ETABS_HARDENING):
        assert entry.status in HARDENING_STATUSES_SPEC, entry
        assert entry.decision.strip(), entry
        assert entry.reason.strip(), entry
        assert "STRUCTAI-" not in entry.decision
    for item, status in MOCK_HARDENING:
        assert status in HARDENING_STATUSES_SPEC, item


def test_p135d_status_lookup_rejects_an_unknown_item() -> None:
    """未知条目名 → **明确拒绝**（`STRUCTAI-1200`），**不**静默回落。"""
    for lookup in (midas_status_of, etabs_status_of):
        with pytest.raises(Exception) as failure:
            lookup("Not An Item")
        assert getattr(failure.value, "code", "") == "STRUCTAI-1200"


def test_p135d_per_software_decisions_are_explicit_where_they_differ() -> None:
    """**逐条**核对三列的差异点（差异必须有理由，不是遗漏）。"""
    assert etabs_status_of("Circuit breaker") == "IMPLEMENTED"
    assert midas_status_of("Circuit breaker") == "NOT_IMPLEMENTED"
    for item in ("Structured logging",):
        assert midas_status_of(item) == etabs_status_of(item) == "NOT_IMPLEMENTED", item
    for item in ("Rate limit", "Resource lock", "Metrics", "Trace", "Audit", "Recovery", "Backup"):
        assert midas_status_of(item) == etabs_status_of(item) == "DELEGATED", item
    for item in ("Credential rotation", "Secret redaction", "Version migration"):
        assert midas_status_of(item) == etabs_status_of(item) == "IMPLEMENTED", item


def test_p135d_adapter_subpackages_do_not_log_or_import_observability() -> None:
    """两个子包**不**写日志、**不**导入 `app.observability`（判据的可执行形式）。"""
    root = Path("app/infrastructure/adapters")
    for vendor in ("midas", "etabs"):
        for path in sorted((root / vendor).glob("*.py")):
            modules = _imported_modules(path)
            assert "logging" not in modules, path
            assert not any(name.startswith("app.observability") for name in modules), path


def _imported_modules(path: Path) -> set[str]:
    """模块级 import 的模块名集合（AST 扫描）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


# ===== P135d：R88 派发落点 =====


def test_p135d_dispatch_entry_point_group_is_the_documented_one() -> None:
    """派发落点 = 标准库 entry point group（见裁决 2；`docs/07` §16 R88）。"""
    assert etabs_dispatch.DISPATCH_ENTRY_POINT_GROUP == "structai.adapters.etabs.dispatch"
    # 本仓库**不**注册任何派发（生产由部署方的独立包注册）→ 发现为空
    assert etabs_dispatch.registered_dispatch_entry_points() == ()
    assert etabs_dispatch.load_dispatch() is None


def test_p135d_missing_dispatch_fails_loudly_instead_of_faking_a_connection() -> None:
    """缺 dispatch → `attach()` 明确失败 `STRUCTAI-2000`（**不**伪造连接）。"""
    import anyio

    session = ComSession(None)
    assert session.state.value == "DETACHED"
    assert session.credential_configured is False
    with pytest.raises(Exception) as failure:
        anyio.run(session.attach)
    assert getattr(failure.value, "code", "") == "STRUCTAI-2000"
    assert failure.value.details["reason"] == "dispatch_not_configured"


def test_p135d_a_registered_dispatch_factory_is_loaded_and_typed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已注册的工厂被**调用**且必须返回 `ComDispatch` 形状（见裁决 2 / 4）。"""
    dispatcher = _Dispatcher()
    monkeypatch.setattr(
        etabs_dispatch, "entry_points", _entry_points(_Point("com", lambda: dispatcher))
    )
    loaded = etabs_dispatch.load_dispatch()
    assert isinstance(loaded, ComDispatch)
    assert isinstance(loaded, _Dispatcher)
    assert loaded is dispatcher
    # 每次调用都**新建**（见裁决 4：Adapter Instance ≠ Software Instance）
    monkeypatch.setattr(etabs_dispatch, "entry_points", _entry_points(_Point("com", _Dispatcher)))
    first = etabs_dispatch.load_dispatch()
    second = etabs_dispatch.load_dispatch()
    assert first is not second


def test_p135d_dispatch_loader_rejects_a_wrong_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """工厂返回非 `ComDispatch` 形状 → `STRUCTAI-2000`（`dispatch_shape_invalid`）。"""
    monkeypatch.setattr(
        etabs_dispatch, "entry_points", _entry_points(_Point("bad", lambda: object()))
    )
    with pytest.raises(Exception) as failure:
        etabs_dispatch.load_dispatch()
    assert getattr(failure.value, "code", "") == "STRUCTAI-2000"
    assert failure.value.details["reason"] == "dispatch_shape_invalid"


def test_p135d_dispatch_loader_rejects_a_non_callable_entry_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """entry point 指向非可调用对象 → 同样明确失败（**不**静默当成实例）。"""
    monkeypatch.setattr(
        etabs_dispatch, "entry_points", _entry_points(_Point("weird", _Dispatcher()))
    )
    with pytest.raises(Exception) as failure:
        etabs_dispatch.load_dispatch()
    assert failure.value.details["reason"] == "dispatch_entry_point_not_callable"


def test_p135d_dispatch_loader_never_echoes_a_third_party_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """加载失败只报 entry point 名与异常**类名**（见裁决 5）。"""
    secret = "p135-third-party-message-must-not-leak"

    def _raise() -> Any:
        raise RuntimeError(secret)

    class _RaisingPoint(_Point):
        """`load()` 自身失败的 entry point（**不**回显第三方 message）。"""

        def load(self) -> Any:
            raise RuntimeError(secret)

    monkeypatch.setattr(
        etabs_dispatch, "entry_points", _entry_points(_RaisingPoint("boom", _raise))
    )
    with pytest.raises(Exception) as failure:
        etabs_dispatch.load_dispatch()
    assert failure.value.details["reason"] == "dispatch_entry_point_unloadable"
    assert failure.value.details["error"] == "RuntimeError"
    assert secret not in json.dumps(failure.value.details, default=str)
    assert secret not in str(failure.value)


def test_p135d_install_uses_the_injected_loader_or_the_entry_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`install()` 缺省路径**先**发现 entry point；发现不到即构造「未注入 dispatch」的 Adapter。"""
    from app.infrastructure.adapters.base.manager import AdapterManager
    from app.infrastructure.adapters.etabs import EtabsAdapter, install

    manager = AdapterManager()
    manifest = install(manager, dispatch_loader=lambda: None)
    assert manifest.vendor == "CSI" and manifest.product == "ETABS"
    assert manager.bound_instance_ids() == ()
    # 缺 dispatch 的 Adapter 在 `connect()` 上明确失败（**不**伪造连接）
    import anyio

    adapter = EtabsAdapter()
    with pytest.raises(Exception) as failure:
        anyio.run(adapter.connect, {})
    assert getattr(failure.value, "code", "") == "STRUCTAI-2000"


# ===== P135d：R93 COM 会话并发 =====


def test_p135d_com_session_is_not_declared_concurrency_safe() -> None:
    """`COM_SESSION_CONCURRENCY_SAFE = False` 是强制 `SERIAL` 的唯一依据（见裁决 3）。"""
    assert COM_SESSION_CONCURRENCY_SAFE is False
    policy = etabs_concurrency.EtabsSerialConcurrencyPolicy()
    assert policy.com_session_concurrency_safe is False
    assert policy.default == etabs_concurrency.CONCURRENCY_SERIAL


async def test_p135d_etabs_instances_are_forced_to_serial_regardless_of_the_delegate() -> None:
    """**不管**委托源怎么说（含 `PARALLEL` / `LIMITED`），ETABS 实例恒为 `SERIAL`。"""
    for declared in ("PARALLEL", "LIMITED"):
        source = etabs_concurrency.policies_for_instances({"etabs-1": declared})
        assert source.etabs_instance_ids == ("etabs-1",)
        assert await source.policy_for("etabs-1") == etabs_concurrency.CONCURRENCY_SERIAL
        assert await source.policy_for("mock-1") == etabs_concurrency.CONCURRENCY_SERIAL


async def test_p135d_serial_policy_delegates_for_non_etabs_instances() -> None:
    """非 ETABS 实例**原样**委托；未注入 delegate 时回落 `SERIAL`（**不**回落 `PARALLEL`）。"""

    class _Delegate:
        async def policy_for(self, software_instance_id: str) -> str:
            return "PARALLEL" if software_instance_id == "other" else "LIMITED"

    source = etabs_concurrency.EtabsSerialConcurrencyPolicy(
        delegate=_Delegate(), etabs_instance_ids=("etabs-1",)
    )
    assert await source.policy_for("other") == "PARALLEL"
    assert await source.policy_for("third") == "LIMITED"
    assert await source.policy_for("etabs-1") == "SERIAL"
    plain = etabs_concurrency.EtabsSerialConcurrencyPolicy(etabs_instance_ids=("etabs-1",))
    assert await plain.policy_for("etabs-1") == "SERIAL"
    assert await plain.policy_for("other") == "SERIAL"


async def test_p135d_an_unexplainable_policy_is_rejected_not_clamped() -> None:
    """无法解释的策略名 → **明确拒绝**（`ValueError`），**不**静默回落。"""

    class _Delegate:
        async def policy_for(self, software_instance_id: str) -> str:
            return "TURBO"

    source = etabs_concurrency.EtabsSerialConcurrencyPolicy(delegate=_Delegate())
    with pytest.raises(ValueError):
        await source.policy_for("other")
    with pytest.raises(ValueError):
        etabs_concurrency.EtabsSerialConcurrencyPolicy(default="TURBO")


def test_p135d_the_policy_source_is_structurally_the_core_contract() -> None:
    """本类**结构上**满足 Core 的收窄契约（`Scheduler(policies=...)` 可直接注入）。

    ⚠️ Core 的 `InstanceConcurrencyPolicySource` 是**普通** `Protocol`（**未**加
    `@runtime_checkable`），故这里按**结构**核对：签名一致 + 本类满足我们自己的
    `runtime_checkable` 收窄契约。**不**改 Core 的声明（`docs/07` §14.1）。
    """
    import inspect

    from app.application.task.scheduler import (
        DefaultInstanceConcurrencyPolicy,
        InstanceConcurrencyPolicySource,
    )

    source = etabs_concurrency.EtabsSerialConcurrencyPolicy(etabs_instance_ids=("etabs-1",))
    assert isinstance(source, etabs_concurrency.InstancePolicySourceLike)
    assert tuple(inspect.signature(InstanceConcurrencyPolicySource.policy_for).parameters) == (
        "self",
        "software_instance_id",
    )
    assert tuple(inspect.signature(source.policy_for).parameters) == ("software_instance_id",)
    assert inspect.iscoroutinefunction(source.policy_for)
    # Core 的缺省实现同样满足该签名（装配方可任选其一注入 `Scheduler`）
    default = DefaultInstanceConcurrencyPolicy()
    assert tuple(inspect.signature(default.policy_for).parameters) == ("software_instance_id",)
    assert inspect.iscoroutinefunction(default.policy_for)
