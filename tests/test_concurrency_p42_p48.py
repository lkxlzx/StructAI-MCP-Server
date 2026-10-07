"""P42–P48 验收 · 第 5 类：**Concurrency**（并发同键 / 抢锁 / 抢租约 / 串行写）。

门槛（`docs/08` §4 的本批提示词；`docs/07` §12 P42–P48 / §13.1；`docs/02` §72 / §67）
------------------------------------------------------------------------------
① 并发同键（幂等）：`asyncio.gather` 同键并发**恰好一个赢家**，库里恰好一行。
② 抢锁：同一资源键的 `EXCLUSIVE` 并发**恰好一个**持有者，冲突 → `STRUCTAI-6100`。
③ 抢租约：两个 Worker 抢同一任务**恰好一个**赢家，另一个 → `STRUCTAI-1300`。
④ 串行写 / 并行读：四级并发按**维度键**计数（取最严格），并发读不互相阻塞。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select

import p42_p48_support as support
from app.application.execution.idempotency import IdempotencyService
from app.application.execution.pipeline import PipelineRequest
from app.application.resource.lock_manager import ResourceLockManager
from app.application.resource.lock_policy import ResourceKey
from app.application.task.lease import LeaseService, TaskLeaseError
from app.application.task.scheduler import (
    ConcurrencyLimits,
    ConcurrencyRequest,
    Scheduler,
)
from app.domain.enums import LockMode
from app.domain.errors import ConcurrencyConflictError, ResourceLockedError
from app.domain.protocols import TaskDraft
from app.infrastructure.database.models.task import TaskORM
from app.infrastructure.database.repositories import (
    build_idempotency_store,
    build_task_store,
)
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.interfaces.mcp import MCPContextFactory


async def _task_total(factory: Any) -> int:
    """任务行数（并发写只允许产生一行 / 一行一任务）。"""
    async with factory() as session:
        return len(list((await session.execute(select(TaskORM))).scalars().all()))


async def _new_task(factory: Any, ids: dict[str, str], *, key: str = "task") -> str:
    """在独立事务里建一条任务行（`docs/02` §9；**不**经管线，用于并发抢租约）。"""
    async with UnitOfWork.from_session_factory(factory) as uow:
        store = build_task_store(uow.session)
        record = await store.create(
            TaskDraft(
                tenant_id=ids["tenant_id"],
                request_id=f"req_{key}",
                trace_id=f"trace_{key}",
                tool="engineering_model_query",
                operation="MODEL.NODE.QUERY",
            )
        )
        return record.id


# ===== ① 并发同键（幂等原子抢占；`docs/02` §35；`docs/07` §10.3）=====


async def test_concurrent_reserve_of_the_same_key_allows_exactly_one_winner(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/02` §35）：同键并发**恰好一个**赢家，其余一律 `STRUCTAI-1300`。"""
    name = "p42_concurrency_idempotency.db"
    settings = support.seeded_settings(tmp_path, name=name)
    _runtime, factory, ids = await support.seeded_runtime(tmp_path, monkeypatch, name=name)

    async def reserve() -> str:
        async with UnitOfWork.from_session_factory(factory) as uow:
            service = IdempotencyService(build_idempotency_store(uow.session))
            decision = await service.begin(
                tenant_id=ids["tenant_id"],
                idempotency_key="race-key",
                request_hash="race-hash",
            )
            return "RESERVED" if decision.reserved else "REPLAY"

    outcomes = await asyncio.gather(*(reserve() for _ in range(5)), return_exceptions=True)
    winners = [item for item in outcomes if item == "RESERVED"]
    conflicts = [item for item in outcomes if isinstance(item, ConcurrencyConflictError)]
    assert len(winners) == 1, outcomes
    assert len(conflicts) == 4, outcomes
    assert {item.code for item in conflicts} == {support.CONFLICT_CODE}
    assert {item.details["reason"] for item in conflicts} == {"in_flight"}
    engine = support.engine_for(settings)
    try:
        assert await support.row_count(engine, "idempotency_records") == 1
    finally:
        await engine.dispose()


async def test_concurrent_execution_with_the_same_key_executes_once(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/02` §32 / §86）：跨请求同键并发**只执行一次**（另一个明确冲突）。"""
    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_concurrency_execution.db"
    )
    identity = support.identity_context(ids)
    context = support.client_context(ids)

    async def run() -> str:
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            execution_context = (
                MCPContextFactory().create(identity, client_context=context).execution
            )
            try:
                await bundle.service.execute_request(
                    PipelineRequest(
                        tool="engineering_model_query",
                        operation="MODEL.NODE.QUERY",
                        parameters={},
                        context=execution_context,
                        idempotency_key="race-exec-key",
                    )
                )
            except ConcurrencyConflictError as error:
                return f"CONFLICT:{error.code}"
            return "OK"

    outcomes = await asyncio.gather(run(), run())
    assert sorted(outcomes) == [f"CONFLICT:{support.CONFLICT_CODE}", "OK"], outcomes
    assert await _task_total(factory) == 1, "冲突方不得建第二个任务"


# ===== ② 抢锁（`docs/02` §36–§41）=====


async def test_lock_race_admits_exactly_one_exclusive_holder() -> None:
    """门槛 ②（`docs/02` §36 / §39）：同一资源键的 `EXCLUSIVE` 并发**恰好一个**持有者。"""
    manager = ResourceLockManager(default_timeout_seconds=300)
    resource = ResourceKey(resource_type="MODEL", resource_id="m-race")

    async def acquire(owner: str) -> str:
        try:
            await manager.acquire(resource, LockMode.EXCLUSIVE, owner_id=owner)
        except ResourceLockedError as error:
            assert error.code == support.LOCK_CONFLICT_CODE
            return "CONFLICT"
        return "OK"

    outcomes = await asyncio.gather(*(acquire(f"w-{index}") for index in range(5)))
    assert outcomes.count("OK") == 1, outcomes
    assert outcomes.count("CONFLICT") == 4, outcomes
    assert await manager.held_count() == 1


# ===== ③ 抢租约（`docs/02` §34–§38；`docs/07` §16 R42）=====


async def test_two_workers_cannot_hold_the_same_lease(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ③（`docs/02` §35）：两个 Worker 抢同一任务**恰好一个**赢家（另一个 1300）。"""
    _runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_concurrency_lease.db"
    )
    task_id = await _new_task(factory, ids, key="lease")

    async def acquire(worker: str) -> str:
        async with UnitOfWork.from_session_factory(factory) as uow:
            lease = LeaseService(build_task_store(uow.session))
            try:
                await lease.acquire(task_id, worker)
            except TaskLeaseError as error:
                assert error.code == support.CONFLICT_CODE
                return "CONFLICT"
            return "OK"

    outcomes = await asyncio.gather(acquire("worker-1"), acquire("worker-2"))
    assert sorted(outcomes) == ["CONFLICT", "OK"], outcomes
    async with UnitOfWork.from_session_factory(factory) as uow:
        record = await build_task_store(uow.session).get(task_id, ids["tenant_id"])
    assert record is not None
    assert record.lease_owner in {"worker-1", "worker-2"}
    assert record.version >= 2, "抢租约必须是条件更新（version 递增）"


# ===== ④ 串行写 / 并行读（`docs/02` §18 / §20 / §49；`docs/07` §16 R47 / R49）=====


async def test_scheduler_admission_counts_by_dimension_key() -> None:
    """门槛 ④（`docs/02` §18；`docs/07` §16 R49 ①）：按**维度键**计数，取最严格限制。"""
    scheduler = Scheduler(
        limits=ConcurrencyLimits(global_limit=0, tenant_limit=10, user_limit=4, instance_limit=1)
    )
    first = ConcurrencyRequest(
        task_id="task-1", tenant_id="t-1", user_id="u-1", software_instance_id="i-1"
    )
    other_instance = ConcurrencyRequest(
        task_id="task-2", tenant_id="t-1", user_id="u-1", software_instance_id="i-2"
    )
    same_instance = ConcurrencyRequest(
        task_id="task-3", tenant_id="t-1", user_id="u-1", software_instance_id="i-1"
    )
    assert (await scheduler.try_acquire(first)).admitted is True
    assert (await scheduler.try_acquire(other_instance)).admitted is True, "不同实例不得互相阻塞"
    decision = await scheduler.try_acquire(same_instance)
    assert decision.admitted is False
    assert decision.level == "software-instance"
    assert decision.reason == "software-instance"
    assert decision.limit == 1, "SERIAL 实例上限 = 1（docs/02 §20）"
    assert (await scheduler.try_acquire(first)).admitted is True, "重复准入必须幂等"
    assert scheduler.active_total() == 2
    await scheduler.release(first)
    assert (await scheduler.try_acquire(same_instance)).admitted is True
    await scheduler.release(other_instance)
    await scheduler.release(same_instance)
    assert scheduler.active_total() == 0


async def test_parallel_reads_do_not_block_each_other(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ④（`docs/02` §17；`docs/07` §16 R40）：并发读在同一 SQLite 上互不阻塞。"""
    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_concurrency_reads.db"
    )
    identity = support.identity_context(ids)
    context = support.client_context(ids)

    async def read() -> str:
        async with UnitOfWork.from_session_factory(factory) as uow:
            bundle = runtime.execution.create(uow.session)
            execution_context = (
                MCPContextFactory().create(identity, client_context=context).execution
            )
            result = await bundle.service.execute_request(
                PipelineRequest(
                    tool="engineering_model_query",
                    operation="MODEL.NODE.QUERY",
                    parameters={},
                    context=execution_context,
                )
            )
            assert result.status == "COMPLETED", result.status
            return str(result.status)

    outcomes = await asyncio.gather(*(read() for _ in range(4)))
    assert outcomes == ["COMPLETED"] * 4, outcomes
    assert await _task_total(factory) == 4
    assert str(UUID(ids["tenant_id"])) == ids["tenant_id"]
