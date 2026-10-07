"""P42–P48 验收 · 第 6 类：**Recovery**（任务恢复四入口 / 重试 / 死信）。

门槛（`docs/08` §4 的本批提示词；`docs/07` §12 P42–P48 / §13.1；`docs/02` §42 / §45 /
§71 / §67）
------------------------------------------------------------------------------
① 恢复**四入口**（`QUEUED` / `RUNNING` / `PROCESSING` / `RECOVERING`）逐条可判定：
   有效租约 → **等待对账且逐列不变**；失效租约 → `RECOVERING` → 按 `recovery_policy`
   出 `REQUEUE` / `RESUME` / `FAIL`（唯一转换点 = `POLICY_TO_ACTION`）。
② 恢复中的任务**绝不**直接置 `COMPLETED`（转移表结构性保证 + 行为断言）。
③ 重试：预算唯一真源 = 任务行 `max_retries`；预算耗尽 → `STRUCTAI-5000`。
④ 死信：Outbox + Dispatcher 的重投 / 死信语义逐条断言（`docs/02` §6 / §42）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import p42_p48_support as support
from app.application.task.recovery import (
    POLICY_TO_ACTION,
    RECOVERY_ENTRY_STATUSES,
    RecoveryAction,
    RecoveryService,
)
from app.application.task.state_machine import ALLOWED_TRANSITIONS
from app.domain.enums import ExecutionMode, RiskLevel, TaskStatus
from app.domain.events import TaskCompleted
from app.domain.protocols import OperationDefinition, TaskDraft
from app.infrastructure.database.repositories import build_task_store
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.infrastructure.events import (
    EventDispatcher,
    InMemoryEventRecordStore,
    InProcessEventBus,
    to_record_draft,
)
from app.infrastructure.registry.operation_registry import OPERATION_PROFILES

_PATHS: dict[str, tuple[str, ...]] = {
    "QUEUED": ("VALIDATING", "QUEUED"),
    "RUNNING": ("VALIDATING", "QUEUED", "RUNNING"),
    "PROCESSING": ("VALIDATING", "QUEUED", "RUNNING", "PROCESSING"),
    "RECOVERING": ("VALIDATING", "QUEUED", "RECOVERING"),
    "FAILED": ("VALIDATING", "FAILED"),
    "COMPLETED": ("VALIDATING", "QUEUED", "RUNNING", "COMPLETED"),
}


def _operation_for(policy: str) -> str:
    """取一条使用指定恢复策略的落库 Operation（`docs/02` §45）。"""
    for name, profile in OPERATION_PROFILES.items():
        if profile.recovery_policy == policy:
            return name
    raise AssertionError(f"no seeded operation uses recovery policy {policy}")


async def _task_at(
    factory: Any,
    ids: dict[str, str],
    *,
    operation: str,
    status: str,
    max_retries: int = 0,
    lease: str = "none",
) -> str:
    """建一条处于指定状态的任务；`lease` ∈ {`none`, `expired`, `valid`}。"""
    async with UnitOfWork.from_session_factory(factory) as uow:
        store = build_task_store(uow.session)
        record = await store.create(
            TaskDraft(
                tenant_id=ids["tenant_id"],
                request_id=f"req_{status}",
                trace_id=f"trace_{status}",
                tool="engineering_model_query",
                operation=operation,
                max_retries=max_retries,
            )
        )
        task_id = record.id
        current = str(TaskStatus.CREATED)
        for target in _PATHS[status]:
            await store.transition(task_id, expected=current, new=target)
            current = target
        now = datetime.now(UTC)
        if lease == "expired":
            await store.acquire_lease(
                task_id, worker_id="w-old", now=now, lease_until=now - timedelta(seconds=1)
            )
        elif lease == "valid":
            await store.acquire_lease(
                task_id, worker_id="w-live", now=now, lease_until=now + timedelta(hours=1)
            )
        return task_id


async def _snapshot(factory: Any, ids: dict[str, str], task_id: str) -> tuple[Any, ...]:
    """任务行的关键列快照（用于「有效租约必须逐列不变」）。"""
    async with UnitOfWork.from_session_factory(factory) as uow:
        record = await build_task_store(uow.session).get(task_id, ids["tenant_id"])
    assert record is not None
    return (
        record.status,
        record.version,
        record.lease_owner,
        record.lease_until,
        record.heartbeat_at,
        record.progress,
        record.error_json,
    )


# ===== ① 四入口与策略映射（`docs/02` §42 / §45；`docs/07` §16 R45 / R46）=====


def test_recovery_entry_statuses_and_policy_mapping_are_frozen() -> None:
    """门槛 ①（`docs/02` §45；`docs/07` §16 R45）：四入口与策略 → 动作映射逐条冻结。"""
    assert tuple(str(status) for status in RECOVERY_ENTRY_STATUSES) == (
        support.RECOVERY_ENTRY_STATUSES_SPEC
    )
    assert set(POLICY_TO_ACTION) == set(support.RECOVERY_POLICIES_SPEC)
    assert {str(action) for action in POLICY_TO_ACTION.values()} == set(
        support.RECOVERY_ACTIONS_SPEC
    )
    assert POLICY_TO_ACTION["SAFE_RETRY"] is RecoveryAction.REQUEUE
    assert POLICY_TO_ACTION["STATE_RECONCILE"] is RecoveryAction.RESUME
    assert POLICY_TO_ACTION["MANUAL_REVIEW"] is RecoveryAction.FAIL
    assert POLICY_TO_ACTION["FAIL"] is RecoveryAction.FAIL
    assert TaskStatus.COMPLETED not in ALLOWED_TRANSITIONS[TaskStatus.RECOVERING]


async def test_effective_lease_is_waited_for_and_never_touched(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/07` §16 R46）：租约仍有效 → **等待对账**，一行都不改。"""
    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_recovery_wait.db"
    )
    operation = _operation_for("STATE_RECONCILE")
    task_id = await _task_at(factory, ids, operation=operation, status="RUNNING", lease="valid")
    before = await _snapshot(factory, ids, task_id)
    async with UnitOfWork.from_session_factory(factory) as uow:
        service = RecoveryService(build_task_store(uow.session), runtime.operation_registry)
        record = await build_task_store(uow.session).get(task_id, ids["tenant_id"])
        assert record is not None
        outcome = await service.recover_task(record)
    assert outcome.waited is True
    assert outcome.task_id == task_id
    assert outcome.status is TaskStatus.RUNNING
    assert await _snapshot(factory, ids, task_id) == before, "有效租约不得被接管"


async def test_expired_lease_is_recovered_per_policy(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/02` §45 / §81）：失效租约 → 按策略出 `REQUEUE` / `RESUME` / `FAIL`。"""
    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_recovery_policy.db"
    )
    expected = {
        "SAFE_RETRY": (RecoveryAction.REQUEUE, TaskStatus.QUEUED, 1),
        "STATE_RECONCILE": (RecoveryAction.RESUME, TaskStatus.RUNNING, 1),
        "MANUAL_REVIEW": (RecoveryAction.FAIL, TaskStatus.FAILED, 0),
    }
    for policy, (action, status, enqueued_count) in expected.items():
        operation = _operation_for(policy)
        task_id = await _task_at(
            factory, ids, operation=operation, status="QUEUED", lease="expired"
        )
        enqueued: list[str] = []

        async def enqueue(record: Any, sink: list[str] = enqueued) -> None:
            sink.append(record.id)

        async with UnitOfWork.from_session_factory(factory) as uow:
            service = RecoveryService(
                build_task_store(uow.session), runtime.operation_registry, enqueue=enqueue
            )
            record = await build_task_store(uow.session).get(task_id, ids["tenant_id"])
            assert record is not None
            outcome = await service.recover_task(record)
        assert outcome.action is action, (policy, outcome.action)
        assert outcome.status is status, (policy, outcome.status)
        assert outcome.policy == policy
        assert outcome.waited is False
        assert len(enqueued) == enqueued_count, (policy, enqueued)
        after = await _snapshot(factory, ids, task_id)
        assert after[0] == str(status), (policy, after)
        if action is RecoveryAction.FAIL:
            assert after[6] is not None and support.TASK_RECOVERY_CODE in after[6], after[6]


async def test_unknown_policy_falls_back_to_fail(tmp_path: Path, monkeypatch: Any) -> None:
    """门槛 ①（`docs/07` §16 R45）：未知策略一律 `FAIL`（绝不臆测可重试）。"""
    _runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_recovery_unknown.db"
    )
    task_id = await _task_at(
        factory, ids, operation="MODEL.NODE.QUERY", status="QUEUED", lease="expired"
    )

    class _StubOperations:
        """只回答「这条 Operation 的恢复策略」的替身（未知取值）。"""

        def _definition(self, name: str) -> OperationDefinition:
            return OperationDefinition(
                name=name,
                tool="engineering_model_query",
                risk_level=RiskLevel.LOW,
                execution_mode=ExecutionMode.SYNC,
                input_schema="structai://schema/x/v1",
                output_schema="structai://schema/x/result/v1",
                recovery_policy="NOT_A_POLICY",
            )

        async def get(self, name: str) -> OperationDefinition:
            """异步读取定义。"""
            return self._definition(name)

        def require(self, name: str) -> OperationDefinition:
            """同步读取定义。"""
            return self._definition(name)

    async with UnitOfWork.from_session_factory(factory) as uow:
        service = RecoveryService(build_task_store(uow.session), _StubOperations())
        record = await build_task_store(uow.session).get(task_id, ids["tenant_id"])
        assert record is not None
        outcome = await service.recover_task(record)
    assert outcome.action is RecoveryAction.FAIL
    assert outcome.status is TaskStatus.FAILED


async def test_recovery_scans_only_the_four_entry_statuses(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①②（`docs/02` §42；`docs/07` §16 R46）：只扫四入口，且**绝不**置 `COMPLETED`。"""
    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_recovery_scan.db"
    )
    operation = _operation_for("SAFE_RETRY")
    entry: list[str] = []
    for status in support.RECOVERY_ENTRY_STATUSES_SPEC:
        entry.append(
            await _task_at(factory, ids, operation=operation, status=status, lease="expired")
        )
    terminal = await _task_at(factory, ids, operation=operation, status="FAILED")
    completed = await _task_at(factory, ids, operation=operation, status="COMPLETED")
    async with UnitOfWork.from_session_factory(factory) as uow:
        service = RecoveryService(build_task_store(uow.session), runtime.operation_registry)
        outcomes = await service.recover_unfinished_tasks()
    recovered = {outcome.task_id for outcome in outcomes}
    assert recovered == set(entry), (recovered, entry)
    assert terminal not in recovered
    assert completed not in recovered
    assert all(outcome.status is not TaskStatus.COMPLETED for outcome in outcomes)
    for task_id in entry:
        assert (await _snapshot(factory, ids, task_id))[0] != str(TaskStatus.COMPLETED)


# ===== ② 重试预算（`docs/02` §77 / §78；`docs/07` §16 R49 ⑩）=====


async def test_retry_requeues_a_failed_task_and_stops_at_the_budget(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ③（`docs/02` §77）：`retry()` 重新入队；预算唯一真源 = 任务行 `max_retries`。"""
    from app.domain.errors import TaskError

    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_recovery_retry.db"
    )
    task_id = await _task_at(
        factory, ids, operation="MODEL.NODE.QUERY", status="FAILED", max_retries=1
    )
    async with UnitOfWork.from_session_factory(factory) as uow:
        store = build_task_store(uow.session)
        engine = runtime.execution.create(uow.session).engine
        record = await engine.retry(task_id, ids["tenant_id"])
        assert str(record.status) == str(TaskStatus.QUEUED)
        assert record.retry_count == 1
        assert record.max_retries == 1
        await store.transition(
            task_id, expected=str(TaskStatus.QUEUED), new=str(TaskStatus.RUNNING)
        )
        await store.transition(
            task_id, expected=str(TaskStatus.RUNNING), new=str(TaskStatus.FAILED)
        )
        with pytest.raises(TaskError) as exhausted:
            await engine.retry(task_id, ids["tenant_id"])
    assert exhausted.value.code == "STRUCTAI-5000"
    assert exhausted.value.retryable is True
    assert exhausted.value.details == {"stage": "task", "reason": "retry_exhausted"}
    assert (await _snapshot(factory, ids, task_id))[0] == str(TaskStatus.FAILED)


# ===== ③ 死信（`docs/02` §6 / §42 / §44）=====


async def test_outbox_dispatch_publishes_and_dead_letters_failing_records() -> None:
    """门槛 ④（`docs/02` §6 / §44）：Outbox 往返 + `attempts` + 死信语义逐条一致。"""
    from uuid import UUID

    delivered: list[object] = []

    async def handler(event: object) -> None:
        delivered.append(event)

    store = InMemoryEventRecordStore()
    bus = InProcessEventBus()
    await bus.subscribe("TaskCompleted", handler)
    await store.append(to_record_draft(TaskCompleted.create(task_id=UUID(int=1)), tenant_id="t-1"))
    dispatcher = EventDispatcher(store, bus, max_attempts=3, backoff_seconds=0.0)
    report = await dispatcher.dispatch_pending()
    assert report.published == 1, report
    assert len(delivered) == 1
    published = store.records()[0]
    assert str(published.status) == "PUBLISHED"
    assert published.attempts == 1, "首次成功投递 = 1 次尝试"
    assert await store.pending() == (), "已发布记录不得再出现在 pending()"
    assert dispatcher.dead_letters() == ()
    assert bus.failures() == ()

    async def boom(event: object) -> None:
        raise RuntimeError("handler exploded")

    failing_store = InMemoryEventRecordStore()
    failing_bus = InProcessEventBus(raise_on_handler_error=True)
    await failing_bus.subscribe("TaskCompleted", boom)
    await failing_store.append(
        to_record_draft(TaskCompleted.create(task_id=UUID(int=2)), tenant_id="t-1")
    )
    failing = EventDispatcher(failing_store, failing_bus, max_attempts=3, backoff_seconds=0.0)
    for _ in range(5):
        await failing.dispatch_pending()
    letters = failing.dead_letters()
    assert len(letters) == 1, letters
    assert letters[0].attempts == 2, "死信快照记的是触发死信前的尝试数"
    assert failing_store.records()[0].attempts == 3, "库里记满 max_attempts 次尝试"
    assert str(letters[0].status) == "FAILED"
    assert "RuntimeError" in failing_bus.failures(), "坏处理器被隔离（只暴露类名）"
