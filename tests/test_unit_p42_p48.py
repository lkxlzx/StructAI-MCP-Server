"""P42–P48 验收 · 第 1 类：**Unit**（纯函数 / 值对象 / 状态机）。

门槛（`docs/08` §4 的本批提示词；`docs/07` §12 P42–P48 / §13.1 / §13.6；`docs/02` §51 /
§67 / §68）
------------------------------------------------------------------------------
① 本类只测**纯逻辑**：值对象、错误契约、状态机、DAG、队列、进度、锁、锁策略、
   Schema / 工程 / 前置 / 后置校验、能力判定、资源解析、幂等摘要、Operation Registry。
② 不建库、不起进程、不依赖执行顺序；每个测试自持状态（`docs/08` §4 门槛 ②）。
③ 判定逐条可执行（`docs/07` §13.1：Unit Test 通过）。
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

import p42_p48_support as support
from app.application.execution import EXECUTION_PIPELINE_ORDER
from app.application.execution.engineering_validator import EngineeringValidator
from app.application.execution.idempotency import IdempotencyService
from app.application.execution.postconditions import PostconditionEvaluator
from app.application.execution.preconditions import ExecutionFacts, PreconditionEvaluator
from app.application.execution.service import ERROR_CLASSES
from app.application.execution.validation import (
    DEFAULT_DIALECT,
    DRAFT7_URI,
    SchemaEngine,
    dialect_of,
    validator_for,
)
from app.application.resource.lock_manager import ResourceLockManager
from app.application.resource.lock_policy import (
    LOCK_COMPATIBILITY,
    LockPolicy,
    ResourceKey,
    locks_are_compatible,
)
from app.application.resource.resolver import ResourceResolver
from app.application.services.capability_resolver import CapabilityResolver
from app.application.task.dag import (
    DagPlan,
    TaskGraph,
    TaskStep,
    blocked_steps,
    graph_from_drafts,
    ready_steps,
    step_plan,
    topological_order,
    validate_dag,
)
from app.application.task.progress import sanitize_progress
from app.application.task.queue import TaskQueue
from app.application.task.state_machine import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    TaskStateError,
    TaskStateMachine,
    can_transition,
    transition,
)
from app.domain.enums import (
    CapabilityStatus,
    ExecutionMode,
    LockMode,
    ResourceType,
    RiskLevel,
    SoftwareConnectionState,
    TaskStatus,
)
from app.domain.errors import (
    EngineeringValidationError,
    NotFoundError,
    ResourceLockedError,
    SchemaValidationError,
    StructAIError,
    TaskError,
    TenantAccessDeniedError,
)
from app.domain.protocols import (
    ModelRecord,
    OperationDefinition,
    ProjectRecord,
    SoftwareInstanceRecord,
    TaskStepDraft,
)
from app.domain.value_objects import (
    DEFAULT_PAGE_LIMIT,
    CapabilityName,
    IdempotencyKey,
    ModelId,
    OperationName,
    Pagination,
    RequestIdentity,
    ResourceRef,
    TenantId,
    VersionRef,
)
from app.infrastructure.registry.operation_registry import OperationRegistry

# ===== ① 值对象与错误契约（`docs/02` §10 / §11；`docs/07` §4.2 / §11）=====


def test_value_objects_validate_and_are_immutable() -> None:
    """门槛 ①（`docs/02` §10）：非空 / 正数校验照抄规范，且值对象不可变。"""
    tenant = UUID(int=1)
    assert TenantId(value=tenant).value == tenant
    assert ModelId(value=tenant).value == tenant
    assert OperationName("BUILD.COLUMN").value == "BUILD.COLUMN"
    assert CapabilityName("MODEL.NODE.WRITE").value == "MODEL.NODE.WRITE"
    assert RequestIdentity(request_id="req_1", trace_id="trace_1").trace_id == "trace_1"
    assert ResourceRef(resource_type="MODEL", resource_id="m-1").resource_type == "MODEL"
    assert VersionRef("1.0").value == "1.0"
    assert IdempotencyKey("k-1").value == "k-1"
    assert Pagination().limit == DEFAULT_PAGE_LIMIT

    for factory in (
        lambda: OperationName(""),
        lambda: CapabilityName(""),
        lambda: VersionRef(""),
        lambda: IdempotencyKey(""),
        lambda: Pagination(limit=0),
    ):
        with pytest.raises(ValueError):
            factory()

    with pytest.raises(dataclasses.FrozenInstanceError):
        OperationName("BUILD.COLUMN").value = "OTHER"  # type: ignore[misc]


def test_error_contract_is_exactly_the_twenty_documented_codes() -> None:
    """门槛 ①（`docs/07` §11）：`ERROR_CLASSES` **恰好** 20 码，码 / 类型 / 可重试一致。"""
    assert set(ERROR_CLASSES) == support.ERROR_CODES_SPEC
    assert len(ERROR_CLASSES) == 20
    retryable: set[str] = set()
    for code, error_class in ERROR_CLASSES.items():
        assert issubclass(error_class, StructAIError), code
        instance = error_class("message")
        assert instance.code == code, code
        envelope = instance.to_dict()
        assert tuple(envelope) == support.ERROR_ENVELOPE_KEYS_SPEC, code
        assert envelope["details"] == {}
        if instance.retryable:
            retryable.add(code)
    assert frozenset(retryable) == support.RETRYABLE_CODES_SPEC, retryable


def test_error_details_are_carried_verbatim_and_codes_are_not_extended() -> None:
    """门槛 ①（`docs/07` §11）：`details` 原样承载；`app/` 内不出现第 21 个码。"""
    error = TenantAccessDeniedError("Tenant access denied", details={"stage": "resource"})
    assert error.to_dict()["details"] == {"stage": "resource"}
    assert error.to_dict()["type"] == "TENANT_ACCESS_DENIED"
    assert support.structai_code_literals() == support.ERROR_CODES_SPEC


def test_frozen_pipeline_order_is_the_documented_twenty_six_steps() -> None:
    """门槛 ①（`docs/07` §9）：26 步顺序冻结且逐条等于规范原文。"""
    assert EXECUTION_PIPELINE_ORDER == support.PIPELINE_ORDER_SPEC
    assert len(EXECUTION_PIPELINE_ORDER) == 26


# ===== ② 任务状态机（`docs/07` §10.1；`docs/02` §7 / §8 / §76）=====


def test_state_machine_matches_the_frozen_twelve_state_table() -> None:
    """门槛 ①（`docs/02` §8）：12 态集中实现，终态无出边，`RECOVERING` 不得到 `COMPLETED`。"""
    assert tuple(status.value for status in TaskStatus) == support.TASK_STATUSES_SPEC
    assert len(ALLOWED_TRANSITIONS) == 12
    assert set(ALLOWED_TRANSITIONS) == set(TaskStatus)
    assert TERMINAL_STATUSES == frozenset({TaskStatus.COMPLETED, TaskStatus.CANCELLED})
    for terminal in TERMINAL_STATUSES:
        assert ALLOWED_TRANSITIONS[terminal] == frozenset(), terminal
    assert TaskStatus.COMPLETED not in ALLOWED_TRANSITIONS[TaskStatus.RECOVERING]
    assert ALLOWED_TRANSITIONS[TaskStatus.RECOVERING] == frozenset(
        {TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.FAILED}
    )


def test_illegal_transition_is_rejected_loudly_with_structai_1300() -> None:
    """门槛 ①（`docs/07` §16 R42）：非法转移**拒绝**而非静默忽略，落 `STRUCTAI-1300`。"""
    assert can_transition(TaskStatus.QUEUED, TaskStatus.RUNNING) is True
    assert can_transition(TaskStatus.COMPLETED, TaskStatus.RUNNING) is False
    assert transition(TaskStatus.QUEUED, TaskStatus.RUNNING) is TaskStatus.RUNNING
    with pytest.raises(TaskStateError) as failure:
        transition(TaskStatus.COMPLETED, TaskStatus.RUNNING)
    assert failure.value.code == support.CONFLICT_CODE
    assert failure.value.details["stage"] == "state_machine"
    assert failure.value.details["from"] == "COMPLETED"
    assert failure.value.details["to"] == "RUNNING"

    machine = TaskStateMachine()
    assert machine.status is TaskStatus.CREATED
    machine.transition(TaskStatus.VALIDATING)
    machine.transition(TaskStatus.QUEUED)
    assert machine.allowed() == ALLOWED_TRANSITIONS[TaskStatus.QUEUED]
    assert machine.can(TaskStatus.RUNNING) is True


# ===== ③ DAG（`docs/02` §46–§51 / §82；`docs/07` §16 R44 / R49）=====


def _graph(**steps: tuple[str, tuple[str, ...]]) -> TaskGraph:
    """按 `step_key=(operation, depends_on)` 构造 DAG（测试内自持，不碰库）。"""
    return TaskGraph(
        steps={
            key: TaskStep(step_id=key, operation=operation, depends_on=depends_on)
            for key, (operation, depends_on) in steps.items()
        }
    )


def test_dag_rejects_every_documented_defect_before_any_write() -> None:
    """门槛 ①（`docs/02` §48 / §49）：四类缺陷一律 `STRUCTAI-1200` 且 reason 逐条一致。"""
    with pytest.raises(EngineeringValidationError) as duplicate:
        graph_from_drafts(
            [
                TaskStepDraft(step_key="a", operation="MODEL.NODE.QUERY"),
                TaskStepDraft(step_key="a", operation="MODEL.NODE.QUERY"),
            ]
        )
    assert duplicate.value.code == "STRUCTAI-1200"
    assert duplicate.value.details["reason"] == "duplicate_step"

    with pytest.raises(EngineeringValidationError) as missing:
        validate_dag(_graph(a=("MODEL.NODE.QUERY", ("ghost",))))
    assert missing.value.details["reason"] == "missing_dependency"

    with pytest.raises(EngineeringValidationError) as cycle:
        validate_dag(_graph(a=("MODEL.NODE.QUERY", ("b",)), b=("MODEL.NODE.QUERY", ("a",))))
    assert cycle.value.details["reason"] == "cycle"

    with pytest.raises(EngineeringValidationError) as unknown:
        validate_dag(_graph(a=("NOPE.NOPE", ())), known_operations=("MODEL.NODE.QUERY",))
    assert unknown.value.details["reason"] == "unknown_step"


def test_dag_topological_order_and_parallel_layers_are_explicit() -> None:
    """门槛 ①（`docs/02` §50 / §51 / §82）：拓扑序前置在前；菱形可并行；`pending` 不谎报。"""
    diamond = _graph(
        a=("MODEL.NODE.QUERY", ()),
        b=("MODEL.NODE.QUERY", ("a",)),
        c=("MODEL.NODE.QUERY", ("a",)),
        d=("MODEL.NODE.QUERY", ("b", "c")),
    )
    order = validate_dag(diamond)
    assert topological_order(diamond) == order
    assert order.index("a") == 0
    assert order.index("d") == 3
    assert order.index("b") < order.index("d")
    assert order.index("c") < order.index("d")

    statuses = {"a": "COMPLETED", "b": "PENDING", "c": "PENDING", "d": "PENDING"}
    assert set(ready_steps(diamond, statuses)) == {"b", "c"}
    assert blocked_steps(diamond, statuses) == ()
    blocked = {"a": "COMPLETED", "b": "FAILED", "c": "PENDING", "d": "PENDING"}
    assert blocked_steps(diamond, blocked) == ("d",)
    assert ready_steps(diamond, blocked) == ("c",)

    plan = step_plan(diamond, statuses)
    assert plan.ready == ("b", "c")
    assert plan.pending == ("d",)
    assert plan.complete is False
    assert DagPlan(finished=("a",), pending=("d",)).complete is False
    assert DagPlan(finished=("a",)).complete is True


def test_continue_on_failure_step_is_ready_but_never_reported_complete() -> None:
    """门槛 ①（`docs/07` §16 R49 ⑤）：`continue_on_failure` 步骤既不卡死也不谎报完成。"""
    graph = TaskGraph(
        steps={
            "a": TaskStep(step_id="a", operation="MODEL.NODE.QUERY"),
            "b": TaskStep(
                step_id="b",
                operation="MODEL.NODE.QUERY",
                depends_on=("a",),
                continue_on_failure=True,
            ),
        }
    )
    statuses = {"a": "FAILED", "b": "PENDING"}
    assert ready_steps(graph, statuses) == ("b",)
    assert blocked_steps(graph, statuses) == ()
    plan = step_plan(graph, statuses)
    assert plan.ready == ("b",)
    assert plan.complete is False


# ===== ④ 队列与进度（`docs/02` §13 / §17 / §31–§33；`docs/07` §16 R43 / R48）=====


async def test_queue_orders_by_priority_then_created_at_then_sequence() -> None:
    """门槛 ①（`docs/02` §17；`docs/07` §16 R43）：排序键 = `(priority, created_at, sequence)`。"""
    queue = TaskQueue()
    early = datetime(2024, 1, 1, tzinfo=UTC)
    late = datetime(2024, 1, 2, tzinfo=UTC)
    await queue.put("low-new", 100, created_at=late)
    await queue.put("high", 10, created_at=late)
    await queue.put("low-old", 100, created_at=early)
    taken = [await queue.get(), await queue.get(), await queue.get()]
    assert [item.task_id for item in taken] == ["high", "low-old", "low-new"]
    assert queue.empty() is True


async def test_bounded_queue_rejects_with_structai_5000_and_shutdown_is_safe() -> None:
    """门槛 ①（`docs/02` §56；`docs/07` §14.4）：队列满 → `STRUCTAI-5000`；关闭不丢数据。"""
    queue = TaskQueue(maxsize=1)
    await queue.put("first")
    with pytest.raises(TaskError) as full:
        await queue.put("second")
    assert full.value.code == "STRUCTAI-5000"
    assert full.value.retryable is True
    await queue.shutdown()
    with pytest.raises(RuntimeError):
        await queue.put("third")
    assert (await queue.get()).task_id == "first"


def test_progress_is_clamped_and_untrusted_values_are_rejected() -> None:
    """门槛 ①（`docs/02` §33；`docs/07` §16 R48）：数值夹取，非数值一律 `STRUCTAI-1200`。"""
    assert sanitize_progress(150) == 100
    assert sanitize_progress(-10) == 0
    assert sanitize_progress(42.7) == 42
    assert sanitize_progress(0) == 0
    for untrusted in (None, "42", True, float("nan"), float("inf")):
        with pytest.raises(EngineeringValidationError) as failure:
            sanitize_progress(untrusted)
        assert failure.value.code == "STRUCTAI-1200"
        assert failure.value.details["stage"] == "progress"


# ===== ⑤ 资源锁（`docs/02` §36–§42 / §74；`docs/07` §16 R26 / R27）=====


def test_lock_compatibility_matrix_is_the_documented_nine_cells() -> None:
    """门槛 ①（`docs/02` §36）：兼容矩阵逐格一致（READ 共享；WRITE / EXCLUSIVE 独占）。"""
    assert LOCK_COMPATIBILITY == {
        LockMode.READ: frozenset({LockMode.READ}),
        LockMode.WRITE: frozenset(),
        LockMode.EXCLUSIVE: frozenset(),
    }
    assert locks_are_compatible(LockMode.READ, LockMode.READ) is True
    assert locks_are_compatible(LockMode.READ, LockMode.WRITE) is False
    assert locks_are_compatible(LockMode.WRITE, LockMode.READ) is False
    assert locks_are_compatible(LockMode.EXCLUSIVE, LockMode.EXCLUSIVE) is False


async def test_lock_manager_conflict_release_and_expiry_are_exact() -> None:
    """门槛 ①（`docs/02` §38–§41；`docs/07` §16 R27）：冲突码 / 精确释放 / 租约回收。"""
    manager = ResourceLockManager(default_timeout_seconds=300)
    resource = ResourceKey(resource_type="MODEL", resource_id="m-1")

    first = await manager.acquire(resource, LockMode.READ, owner_id="w-1")
    second = await manager.acquire(resource, LockMode.READ, owner_id="w-2")
    assert await manager.held_count() == 2

    with pytest.raises(ResourceLockedError) as conflict:
        await manager.acquire(resource, LockMode.EXCLUSIVE, owner_id="w-3")
    assert conflict.value.code == "STRUCTAI-6100"
    assert set(conflict.value.details) == {
        "resource_type",
        "resource_id",
        "requested_mode",
        "held_modes",
        "owner_id",
    }

    assert await manager.release(first) is True
    assert await manager.release(first) is False  # 重复释放不影响其他持有者
    assert await manager.held_count() == 1
    assert await manager.release(second) is True
    assert await manager.held_count() == 0

    with pytest.raises(RuntimeError):
        async with manager.hold(resource, LockMode.EXCLUSIVE, owner_id="w-4"):
            assert await manager.is_locked(resource) is True
            raise RuntimeError("boom")
    assert await manager.held_count() == 0, "异常路径必须释放（docs/02 §41）"

    await manager.acquire(resource, LockMode.WRITE, owner_id="w-5", timeout_seconds=0)
    assert await manager.expire_stale() == 1
    assert await manager.held_count() == 0


def test_lock_policy_follows_risk_level_and_query_suffix() -> None:
    """门槛 ①（`docs/02` §74）：HIGH / CRITICAL → `EXCLUSIVE`；`*.QUERY` → `READ`。"""

    def definition(name: str, risk: RiskLevel) -> OperationDefinition:
        return OperationDefinition(
            name=name,
            tool="engineering_model_query",
            risk_level=risk,
            execution_mode=ExecutionMode.SYNC,
            input_schema="structai://schema/x/v1",
            output_schema="structai://schema/x/result/v1",
        )

    policy = LockPolicy()
    assert policy.mode_for(definition("BUILD.COLUMN", RiskLevel.HIGH)) is LockMode.EXCLUSIVE
    assert (
        policy.mode_for(definition("MODEL.NODE.DELETE", RiskLevel.CRITICAL)) is LockMode.EXCLUSIVE
    )
    assert policy.mode_for(definition("MODEL.NODE.QUERY", RiskLevel.LOW)) is LockMode.READ
    assert policy.mode_for(definition("MODEL.NODE.CREATE", RiskLevel.MEDIUM)) is LockMode.WRITE
    lock = policy.resolve(definition("BUILD.COLUMN", RiskLevel.HIGH), ResourceRef("MODEL", "m-1"))
    assert lock.mode is LockMode.EXCLUSIVE
    assert lock.timeout_seconds == policy.timeout_seconds


# ===== ⑥ Schema / 工程 / 前置 / 后置校验（`docs/02` §13–§23 / §32）=====


class _SchemaLookup:
    """最小 `SchemaLookup` 实现（`docs/02` §15；只回答「这一行是什么」）。"""

    def __init__(self, schemas: dict[str, dict[str, Any]]) -> None:
        self._schemas = schemas

    def get(self, schema_id: str) -> dict[str, Any]:
        """未登记 → `NotFoundError`（P09 已冻结的口径）。"""
        if schema_id not in self._schemas:
            raise NotFoundError(f"Schema not found: {schema_id}")
        return dict(self._schemas[schema_id])


def test_schema_engine_selects_the_declared_dialect_and_rejects_invalid_data() -> None:
    """门槛 ①（`docs/02` §16 / §17；`docs/07` §16 R18）：按声明选校验器；非法数据必拒。"""
    draft7: dict[str, Any] = {
        "$schema": DRAFT7_URI,
        "type": "object",
        "properties": {"height": {"type": "number", "exclusiveMinimum": 0}},
        "required": ["height"],
    }
    undeclared: dict[str, Any] = {"type": "object", "required": ["x"]}
    assert dialect_of(draft7) == DRAFT7_URI
    assert dialect_of(undeclared) == DEFAULT_DIALECT
    assert validator_for(draft7).__name__ == "Draft7Validator"

    engine = SchemaEngine(
        _SchemaLookup({"structai://schema/a/v1": draft7, "structai://schema/b/v1": undeclared})
    )
    engine.validate("structai://schema/a/v1", {"height": 6.0})
    engine.check_schema("structai://schema/a/v1")
    assert engine.dialect("structai://schema/b/v1") == DEFAULT_DIALECT

    with pytest.raises(SchemaValidationError) as invalid:
        engine.validate("structai://schema/a/v1", {"height": -1})
    assert invalid.value.code == "STRUCTAI-1100"
    assert invalid.value.details["schema_id"] == "structai://schema/a/v1"
    assert invalid.value.details["errors"][0]["path"]

    with pytest.raises(NotFoundError):
        engine.validate("structai://schema/missing/v1", {})


async def test_engineering_validator_reports_issues_once_and_fails_loudly() -> None:
    """门槛 ①（`docs/02` §18–§22；`docs/07` §16 R28）：语义非法 → `STRUCTAI-1200`。"""
    validator = EngineeringValidator()
    node = {"id": "n-1", "x": 0.0, "y": 0.0, "z": 0.0}
    assert validator.check("MODEL.NODE.CREATE", node) == []
    issues = validator.check("MODEL.NODE.CREATE", {**node, "x": float("nan")})
    assert issues, "非有限坐标必须被报告（docs/02 §21）"

    with pytest.raises(EngineeringValidationError) as failure:
        await validator.validate("MODEL.NODE.CREATE", {**node, "x": float("inf")})
    assert failure.value.code == "STRUCTAI-1200"
    assert failure.value.details["stage"] == "engineering"
    assert failure.value.details["issues"]


async def test_preconditions_are_tri_state_and_failures_are_structai_1200() -> None:
    """门槛 ①（`docs/02` §32；`docs/07` §16 R28 / R29）：事实缺失 = **未验证**，不判失败。"""
    from app.application.resource.resolver import ResolvedResource

    evaluator = PreconditionEvaluator()
    unverified = evaluator.check("BUILD.COLUMN", ExecutionFacts())
    assert unverified.issues == ()
    assert unverified.unverified, "事实缺失必须如实记为未验证"
    assert unverified.ok is True

    only_instance = ExecutionFacts(
        resolved_resource=ResolvedResource(
            resource_type=ResourceType.SOFTWARE_INSTANCE.value,
            resource_id="i-1",
            tenant_id="t-1",
        )
    )
    blocked = evaluator.check("BUILD.COLUMN", only_instance)
    assert blocked.issues, "只解析出软件实例时写操作没有落点（docs/02 §32）"

    definition = OperationDefinition(
        name="BUILD.COLUMN",
        tool="engineering_model_build",
        risk_level=RiskLevel.HIGH,
        execution_mode=ExecutionMode.ASYNC,
        input_schema="structai://schema/build/column/v1",
        output_schema="structai://schema/build/column/result/v1",
    )
    with pytest.raises(EngineeringValidationError) as failure:
        await evaluator.require(definition, only_instance)
    assert failure.value.code == "STRUCTAI-1200"
    assert failure.value.details["stage"] == "preconditions"


async def test_postconditions_failures_are_structai_5000() -> None:
    """门槛 ①（`docs/02` §32；`docs/07` §16 R28 / R55）：后置条件不满足 → `STRUCTAI-5000`。"""
    evaluator = PostconditionEvaluator()
    unverified = evaluator.check("BUILD.COLUMN", ExecutionFacts())
    assert unverified.issues == ()
    assert unverified.unverified

    definition = OperationDefinition(
        name="BUILD.COLUMN",
        tool="engineering_model_build",
        risk_level=RiskLevel.HIGH,
        execution_mode=ExecutionMode.ASYNC,
        input_schema="structai://schema/build/column/v1",
        output_schema="structai://schema/build/column/result/v1",
    )
    with pytest.raises(TaskError) as failure:
        await evaluator.require(
            definition,
            ExecutionFacts(task_status=TaskStatus.RUNNING.value, result_available=False),
        )
    assert failure.value.code == "STRUCTAI-5000"
    assert failure.value.details["stage"] == "postconditions"
    assert failure.value.retryable is True


# ===== ⑦ 能力判定（`docs/02` §34 / §43–§48；`docs/07` §16 R30 / R38）=====


class _CapabilityLookup:
    """最小 `CapabilityLookup`（`docs/02` §44；词表由外部提供，本模块**不**内置）。"""

    def __init__(self, codes: tuple[str, ...]) -> None:
        self._codes = codes

    def codes(self) -> tuple[str, ...]:
        """已知能力码。"""
        return self._codes

    def capabilities_for(self, operation: str) -> tuple[str, ...]:
        """该 Operation 要求的能力码。"""
        if operation == "BUILD.COLUMN":
            return ("MODEL.NODE.WRITE",)
        return ("ANALYSIS.NONLINEAR",) if operation == "ANALYSIS.NONLINEAR" else ()


class _InstanceLookup:
    """最小 `InstanceLookup`（`docs/02` §19）。"""

    def __init__(self, records: dict[str, SoftwareInstanceRecord]) -> None:
        self._records = records

    async def software_instance(self, instance_id: str) -> SoftwareInstanceRecord | None:
        """实例快照。"""
        return self._records.get(instance_id)


class _RuntimeCapabilities:
    """最小 `RuntimeCapabilitySource`（`docs/02` §45；`None` = 清单不可得）。"""

    def __init__(self, available: frozenset[str] | None) -> None:
        self._available = available

    def runtime_capabilities(self, instance_id: str) -> frozenset[str] | None:
        """运行时能力清单。"""
        return self._available


def _instance(status: str) -> SoftwareInstanceRecord:
    return SoftwareInstanceRecord(
        id="i-1",
        name="Mock Instance",
        version_id="v-1",
        status=status,
        vendor="StructAI",
        product="Mock Engineering Software",
        version="1.0",
    )


def test_capability_status_is_per_instance_and_version_with_three_states() -> None:
    """门槛 ①（`docs/02` §34 / §45–§48；`docs/07` §16 R30 / R38）：三态严格区分。"""
    registry = _CapabilityLookup(("MODEL.NODE.WRITE", "ANALYSIS.STATIC"))
    connected = _instance(SoftwareConnectionState.CONNECTED.value)
    instances = _InstanceLookup({"i-1": connected})
    static = CapabilityResolver(registry, instances, cache_ttl_seconds=300)
    assert static.status_of(connected, "MODEL.NODE.WRITE") is CapabilityStatus.SUPPORTED
    assert static.status_of(connected, "NOPE.NOPE") is CapabilityStatus.UNKNOWN
    disconnected = _instance(SoftwareConnectionState.DISCONNECTED.value)
    assert static.status_of(disconnected, "MODEL.NODE.WRITE") is CapabilityStatus.UNKNOWN

    runtime = CapabilityResolver(
        registry,
        instances,
        runtime=_RuntimeCapabilities(frozenset({"MODEL.NODE.WRITE"})),
    )
    assert runtime.status_of(connected, "MODEL.NODE.WRITE") is CapabilityStatus.SUPPORTED
    assert runtime.status_of(connected, "ANALYSIS.STATIC") is CapabilityStatus.UNSUPPORTED

    unknown_runtime = CapabilityResolver(registry, instances, runtime=_RuntimeCapabilities(None))
    assert unknown_runtime.status_of(connected, "ANALYSIS.STATIC") is CapabilityStatus.UNKNOWN
    assert static.known == frozenset({"MODEL.NODE.WRITE", "ANALYSIS.STATIC"})
    with pytest.raises(NotFoundError):
        static.require_known("NOPE.NOPE")

    nonlinear = OperationDefinition(
        name="ANALYSIS.NONLINEAR",
        tool="engineering_analysis",
        risk_level=RiskLevel.HIGH,
        execution_mode=ExecutionMode.ASYNC,
        input_schema="structai://schema/x/v1",
        output_schema="structai://schema/x/result/v1",
        required_capabilities=("ANALYSIS.NONLINEAR",),
    )
    assert static.unknown_codes([nonlinear]) == ("ANALYSIS.NONLINEAR",)
    assert static.registry_required_for("BUILD.COLUMN") == ("MODEL.NODE.WRITE",)
    assert static.required_for(nonlinear) == ("ANALYSIS.NONLINEAR",)


# ===== ⑧ 资源解析（`docs/02` §8–§12 / §71–§73；`docs/07` §16 R24 / R25）=====


class _Namespace:
    """只读字段替身（构造最小执行上下文用）。"""

    def __init__(self, **values: object) -> None:
        self.__dict__.update(values)


class _Context:
    """最小执行上下文替身（`docs/02` §3；只提供解析需要的只读字段）。"""

    def __init__(
        self,
        identity: Any,
        *,
        project_id: str | None = None,
        model_id: str | None = None,
        document_id: str | None = None,
        instance_id: str | None = None,
    ) -> None:
        self.identity = identity
        self.project = _Namespace(project_id=project_id)
        self.resource = _Namespace(model_id=model_id, document_id=document_id)
        self.software = _Namespace(instance_id=instance_id)


class _ResourceStore:
    """最小 `ResourceStore`（`docs/02` §8–§12；只回答「这一行是什么」）。"""

    def __init__(
        self,
        *,
        projects: dict[str, ProjectRecord] | None = None,
        models: dict[str, ModelRecord] | None = None,
        instances: dict[str, SoftwareInstanceRecord] | None = None,
        bindings: dict[str, frozenset[str]] | None = None,
    ) -> None:
        self._projects = projects or {}
        self._models = models or {}
        self._instances = instances or {}
        self._bindings = bindings or {}

    async def project(self, project_id: str) -> ProjectRecord | None:
        """项目快照。"""
        return self._projects.get(project_id)

    async def model(self, model_id: str) -> ModelRecord | None:
        """模型快照。"""
        return self._models.get(model_id)

    async def document(self, document_id: str) -> None:
        """文档快照（本测试不使用）。"""
        return None

    async def software_instance(self, instance_id: str) -> SoftwareInstanceRecord | None:
        """软件实例快照。"""
        return self._instances.get(instance_id)

    async def tenant_ids_binding_instance(self, instance_id: str) -> frozenset[str]:
        """哪些租户的项目链绑定了该实例（`docs/07` §16 R25）。"""
        return self._bindings.get(instance_id, frozenset())


async def test_resource_resolver_denies_missing_and_foreign_identically() -> None:
    """门槛 ①（`docs/02` §48 / §71；`docs/07` §16 R24）：不存在与跨租户**形状完全一致**。"""
    from app.application.security.context import IdentityContext

    mine = str(UUID(int=11))
    other = str(UUID(int=12))
    identity = IdentityContext(user_id=UUID(int=1), tenant_id=UUID(int=11))
    store = _ResourceStore(
        projects={
            "p-mine": ProjectRecord(id="p-mine", tenant_id=mine),
            "p-other": ProjectRecord(id="p-other", tenant_id=other),
        },
        models={
            "m-mine": ModelRecord(id="m-mine", project_id="p-mine"),
            "m-other": ModelRecord(id="m-other", project_id="p-other"),
        },
        instances={"i-1": _instance(SoftwareConnectionState.CONNECTED.value)},
        bindings={"i-1": frozenset({mine})},
    )
    resolver = ResourceResolver(store)

    mine_project = _Context(identity, project_id="p-mine")
    resolved = await resolver.resolve_project(mine_project)
    assert resolved.resource_type == ResourceType.PROJECT.value
    assert resolved.resource_id == "p-mine"
    assert resolved.tenant_id == mine
    assert resolved.as_key() == ResourceKey(resource_type="PROJECT", resource_id="p-mine")

    with pytest.raises(TenantAccessDeniedError) as missing:
        await resolver.resolve_project(_Context(identity, project_id="p-missing"))
    with pytest.raises(TenantAccessDeniedError) as foreign:
        await resolver.resolve_project(_Context(identity, project_id="p-other"))
    assert missing.value.code == support.TENANT_DENIED_CODE
    assert (missing.value.message, missing.value.details) == (
        foreign.value.message,
        foreign.value.details,
    ), "「不存在」与「跨租户」必须不可区分（docs/02 §48）"

    model = await resolver.resolve_model(_Context(identity, project_id="p-mine", model_id="m-mine"))
    assert model.resource_type == ResourceType.MODEL.value
    assert model.project_id == "p-mine"
    assert model.tenant_id == mine
    with pytest.raises(TenantAccessDeniedError):
        await resolver.resolve_model(_Context(identity, model_id="m-other"))

    instance = await resolver.resolve_software_instance(_Context(identity, instance_id="i-1"))
    assert instance.resource_type == ResourceType.SOFTWARE_INSTANCE.value
    with pytest.raises(TenantAccessDeniedError):
        await resolver.resolve_software_instance(_Context(identity, instance_id="i-unbound"))
    assert await resolver.resolve(_Context(identity)) is None


async def test_resource_resolver_rejects_self_contradictory_client_ids() -> None:
    """门槛 ①（`docs/02` §8 / §48；`docs/07` §16 R24）：客户端标识自相矛盾 → `STRUCTAI-1000`。"""
    from app.application.security.context import IdentityContext
    from app.domain.errors import ProtocolError

    mine = str(UUID(int=11))
    identity = IdentityContext(user_id=UUID(int=1), tenant_id=UUID(int=11))
    store = _ResourceStore(
        projects={
            "p-mine": ProjectRecord(id="p-mine", tenant_id=mine),
            "p-other": ProjectRecord(id="p-other", tenant_id=mine),
        },
        models={"m-mine": ModelRecord(id="m-mine", project_id="p-other")},
    )
    resolver = ResourceResolver(store)
    with pytest.raises(ProtocolError) as failure:
        await resolver.resolve_model(_Context(identity, project_id="p-mine", model_id="m-mine"))
    assert failure.value.code == support.PROTOCOL_ERROR_CODE


# ===== ⑨ 幂等摘要与 Operation Registry（`docs/02` §33 / §28；`docs/07` §10.3）=====


class _UnusedStore:
    """占位存储（`hash_request` 是纯函数，不触碰存储）。"""


def test_idempotency_request_hash_is_deterministic_and_strict() -> None:
    """门槛 ①（`docs/02` §33）：摘要稳定、随请求变化、缺字段**不**静默兜底。"""
    service = IdempotencyService(_UnusedStore())  # type: ignore[arg-type]
    request = {
        "tool": "engineering_model_build",
        "operation": "BUILD.COLUMN",
        "parameters": dict(support.BUILD_COLUMN_PARAMETERS),
        "context": {"model_id": "m-1"},
        "dry_run": False,
    }
    digest = service.hash_request(request)
    assert len(digest) == 64
    assert service.hash_request(dict(request)) == digest
    changed = {**request, "operation": "BUILD.BEAM"}
    assert service.hash_request(changed) != digest
    with pytest.raises(TypeError):
        service.hash_request({"operation": "BUILD.COLUMN"})


async def test_operation_registry_indexes_definitions_and_rejects_unknown() -> None:
    """门槛 ①（`docs/07` §12 P08）：定义可按名索引、按 Tool 分组；未知名 → `NotFoundError`。"""
    definition = OperationDefinition(
        name="BUILD.COLUMN",
        tool="engineering_model_build",
        risk_level=RiskLevel.HIGH,
        execution_mode=ExecutionMode.ASYNC,
        input_schema="structai://schema/build/column/v1",
        output_schema="structai://schema/build/column/result/v1",
        required_permissions=("MODEL_WRITE",),
        required_capabilities=("MODEL.NODE.WRITE",),
        transactional=True,
        rollback_supported=True,
        dry_run_supported=True,
        recovery_policy="STATE_RECONCILE",
    )
    registry = OperationRegistry()
    await registry.register(definition)
    assert await registry.get("BUILD.COLUMN") is definition
    assert await registry.get("NOPE") is None
    assert registry.require("BUILD.COLUMN") is definition
    assert registry.names() == ("BUILD.COLUMN",)
    assert registry.for_tool("engineering_model_build") == (definition,)
    assert len(registry) == 1
    assert "BUILD.COLUMN" in registry
    assert registry.summary() == {
        "operations": 1,
        "tools": ["engineering_model_build"],
        "transactional": 1,
        "dry_run_supported": 1,
    }
    with pytest.raises(NotFoundError):
        registry.require("NOPE")
