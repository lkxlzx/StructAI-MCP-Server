"""Application · Execution · ExecutionService（`docs/07` §9 / §12 P36；`docs/02` §86–§94）。

第一个真正的 Core 主干（`docs/07` §12 P36）
-----------------------------------------
本模块把 `pipeline.py` 的闸门链（第 5–16 步）与 P22–P28 的 Task Engine 串成
`docs/07` §9 的 **26 步**（`EXECUTION_PIPELINE_ORDER` 是唯一权威，本批**不得**改顺序、
**不得**删步），并实现 P22–P28 的 `TaskExecutor` 端口（`worker.py`）——
即「Worker 取到任务后真正执行 Adapter」的那一端。

权威来源
--------
- `docs/07` §9 —— 26 步冻结顺序；`docs/02` §86–§94（`task`）—— 与 Task Engine 的接口：
  `docs/02` §86 的 `execute(request, context, operation)`、§87/§88 的
  「**SYNC 也统一走 Task Engine**（`worker_id="sync-worker"`），区别只是等完成还是
  立即返回 `task_id`」、§89 的 ASYNC 响应形状
  （`{"mode": "ASYNC", "status": "QUEUED", "task_id": ...}`）、§90 的
  `ExecutionService → Idempotency → Task Create` 顺序、§91 的「锁由 Worker 在取到任务后抢」、
  §92 的「Confirmation 必须在 Task 创建之前」、§93 的「Capability 基本检查在 Task 创建之前」。
- `docs/02` §45（`ExecutionService`）—— 顺序清单（Schema → … → Event）。
- `docs/02` §30 / §92（`exec`）—— Dry Run：`{"mode": "DRY_RUN", "changes": [], "warnings": []}`，
  **不得**修改真实模型。
- `docs/02` §5.4 —— 事件必须**先写 Outbox 再 COMMIT，最后经 Dispatcher 发布**；
  「如果本阶段暂不实现完整 Outbox，则必须在代码层明确其为 Alpha 限制，并保留迁移接口」。
- `docs/07` §14.4 —— `ExecutionService` **不得**变成巨型类（故闸门链在 `pipeline.py`）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **SYNC 也走 Task Engine**（`docs/02` §87 / §88，逐字照抄）：本服务不自己调 Adapter，
   而是创建 Task 后 `TaskEngine.run_task(task_id, "sync-worker")` 等它完成，
   再读回 `tasks.result_json` 组装响应。ASYNC 则只 `submit` 并立即返回 `task_id`。
   这样「同步」与「异步」共用**同一条**执行链，只有等待方式不同。
2. **`STREAM` 按 ASYNC 处理**（`docs/02` §46）：`ExecutionMode.STREAM` 的传输
   （MCP progress / notification）属 P37–P41（`docs/08` §4：不要提前做），本批**不**实现
   流式响应；故 `STREAM` 与 `ASYNC` 同路（建 Task + 立即返回 `task_id`），
   进度经 `docs/02` §45 的**唯一**接入点（Notification 服务）后续外发。
3. **Worker 路径的参数来自 `task_steps.parameters_json`**（`docs/07` §4.3 #19 / #20）：
   `tasks` 表**没有**参数列，而 `task_steps` 有 `parameters_json`。故 `execute_request`
   在创建 Task 时**总是**带上一个携带参数的步骤（`TaskStepDraft`），
   `execute()` 再按 `operation` 取回参数 —— 参数因此**落库**，跨进程可重建。
4. **Worker 路径的 `ExecutionContext` 落在进程内**（**Alpha 限制**）：`tasks` 表没有
   身份 / 租户 / 项目之外的身份列，而 Adapter 调用与审计都需要**服务端身份**。
   故 `execute_request` 把 `ExecutionContext`（+ 根 Span id）登记进
   `self._sessions[task_id]`，`execute()` 取回它。
   ⚠️ 进程重启后该映射为空 —— 此时 `execute()` 抛 `STRUCTAI-7000`
   （`reason = "context_not_available"`），**绝不**用空身份继续执行。
   恢复路径必须由调用方重新提供上下文（属 P37–P48 的启动恢复，见 `docs/02` §42 / §50）。
5. **审计的唯一性规则**（避免双计）：`ExecutionService` 对
   **每次到达 Adapter 步的尝试**记录**恰好一条**审计（在 `execute()` 里），
   并对**每次在 Task 创建之前被拒绝的请求**记录**恰好一条**审计
   （在 `execute_request` 的异常路径里，且仅在 `task_created is False` 时）。
   重放（`docs/02` §86）**不**记录任何审计 / Trace / Event —— 首次执行时已记录。
6. **Event 步先写 Outbox**（`docs/02` §5.4）：注入了 `EventRecordStore` 时
   **只**追加 Outbox 记录（`PENDING`），发布交给 `EventDispatcher`；
   未注入 Outbox 时才直接 `EventBus.publish` —— 这是 §5.4 明确允许的 Alpha 形态，
   两者都不改变 Domain Event 本身（`docs/02` §38）。
7. **审计动作名经 `audit_action_for` 推导**（`docs/02` §8.3）：§8.3 给出 16 个**必须记录**
   的动作名，但未给出 Operation → 动作的映射；映射表在 `pipeline.py`，
   未命中的 Operation 用自己的名字入审计（`audit_records.action` 是自由文本，
   不臆造不存在的动作名）。
8. **被拒绝的失败落 `AuditResult.DENIED`**：`app.domain.enums.AuditResult` 的定义是
   「因权限 / 能力 / 确认缺失而被拒绝（对应 `STRUCTAI-4000` 等）」，故
   `STRUCTAI-3000` / `4000` / `4100` / `4200` / `6100` 落 `DENIED`，其余落 `FAILURE`。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain` / **同层**的 `app.application.*`：
**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖 `app.infrastructure` /
`app.interfaces` / `app.observability`（Adapter / 审计 / Trace / Metrics / Outbox 全部经
Domain 收窄契约或同层服务注入），也**不**出现任何厂商专属内容。
事务边界归调用方的 `UnitOfWork`（`docs/02` §16）—— 本模块**从不** `commit` / `rollback`。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Final, Protocol
from uuid import UUID

from app.application.execution.context import ExecutionContext
from app.application.execution.idempotency import canonical_payload
from app.application.execution.pipeline import (
    MCP_PIPELINE_STEPS,
    PIPELINE_EXECUTION_STEPS,
    PIPELINE_GATE_STEPS,
    PIPELINE_RESPONSE_STEPS,
    PIPELINE_TASK_STEP,
    AdapterExecutor,
    ExecutionPipeline,
    PipelineGate,
    PipelineRequest,
    audit_action_for,
)
from app.application.task.engine import SYNC_WORKER_ID, TaskEngine, TaskSubmission
from app.domain.enums import AuditResult, ExecutionMode, TaskStatus, TraceSpanKind, TraceStatus
from app.domain.errors import (
    AdapterError,
    ArtifactError,
    CapabilityError,
    ConcurrencyConflictError,
    ConfirmationRequiredError,
    EngineeringValidationError,
    InternalError,
    PermissionDeniedError,
    ProtocolError,
    ResourceLockedError,
    SchemaValidationError,
    SoftwareAPIError,
    SoftwareAuthenticationError,
    SoftwareConnectionError,
    SoftwareTimeoutError,
    StructAIError,
    TaskCancelledError,
    TaskError,
    TaskRecoveryError,
    TaskTimeoutError,
    TenantAccessDeniedError,
)
from app.domain.events import DomainEvent, TaskCompleted, TaskFailed
from app.domain.protocols import (
    AuditRecorder,
    EventBus,
    EventRecordDraft,
    EventRecordStore,
    MetricsRecorder,
    OperationDefinition,
    TaskRecord,
    TaskStepDraft,
    TraceRecorder,
    TraceSpanRecord,
)

__all__ = [
    "ASYNC_MODE",
    "DENIED_ERROR_CODES",
    "DRY_RUN_MODE",
    "DRY_RUN_PAYLOAD",
    "ERROR_CLASSES",
    "EXECUTION_STAGE",
    "EXECUTION_STEPS",
    "SYNC_MODE",
    "ExecutionResult",
    "ExecutionService",
    "ExecutionSession",
    "ResultNormalizerPort",
]

logger = logging.getLogger("structai.execution")

EXECUTION_STAGE: Final[str] = "execution"
"""错误 `details.stage` 的固定取值。"""

SYNC_MODE: Final[str] = str(ExecutionMode.SYNC)
"""同步执行（`docs/02` §46 / §88）。"""

ASYNC_MODE: Final[str] = str(ExecutionMode.ASYNC)
"""异步执行（`docs/02` §46 / §89）。"""

DRY_RUN_MODE: Final[str] = "DRY_RUN"
"""Dry Run 的响应模式（`docs/02` §92 逐字）。"""

DRY_RUN_PAYLOAD: Final[Mapping[str, Any]] = {
    "mode": DRY_RUN_MODE,
    "changes": [],
    "warnings": [],
}
"""Dry Run 的响应体（`docs/02` §92 逐字照抄；`changes` / `warnings` 本批为空列表）。"""

DENIED_ERROR_CODES: Final[frozenset[str]] = frozenset(
    {
        "STRUCTAI-3000",
        "STRUCTAI-4000",
        "STRUCTAI-4100",
        "STRUCTAI-4200",
        "STRUCTAI-6100",
    }
)
"""落 `AuditResult.DENIED` 的错误码（见模块裁决 8）。"""

ERROR_CLASSES: Final[Mapping[str, type[StructAIError]]] = {
    "STRUCTAI-1000": ProtocolError,
    "STRUCTAI-1100": SchemaValidationError,
    "STRUCTAI-1200": EngineeringValidationError,
    "STRUCTAI-1300": ConcurrencyConflictError,
    "STRUCTAI-2000": SoftwareConnectionError,
    "STRUCTAI-2100": SoftwareAuthenticationError,
    "STRUCTAI-2200": SoftwareAPIError,
    "STRUCTAI-2300": SoftwareTimeoutError,
    "STRUCTAI-3000": CapabilityError,
    "STRUCTAI-4000": PermissionDeniedError,
    "STRUCTAI-4100": ConfirmationRequiredError,
    "STRUCTAI-4200": TenantAccessDeniedError,
    "STRUCTAI-5000": TaskError,
    "STRUCTAI-5100": TaskTimeoutError,
    "STRUCTAI-5200": TaskCancelledError,
    "STRUCTAI-5300": TaskRecoveryError,
    "STRUCTAI-6000": AdapterError,
    "STRUCTAI-6100": ResourceLockedError,
    "STRUCTAI-6200": ArtifactError,
    "STRUCTAI-7000": InternalError,
}
"""20 码 → 异常类的**反向**映射（恰好 20 条；验收测试逐条断言）。

⚠️ 唯一的**正向**归一化点仍是 `app/infrastructure/adapters/base/errors.py`
（`docs/07` §11：原生错误 → 20 码只允许一处实现）。本表只做相反方向的事：
把 Worker 落进 `tasks.error_json` 的**归一化信封**还原成异常，
供 SYNC 路径把真实失败如实上抛（`docs/02` §88 的「等完成」必须能等到真实结果）。
**不**新增任何码：表里的 20 个键与 `docs/07` §11 的 20 码逐条一致。
"""

EXECUTION_STEPS: Final[tuple[str, ...]] = (
    MCP_PIPELINE_STEPS
    + PIPELINE_GATE_STEPS
    + (PIPELINE_TASK_STEP,)
    + PIPELINE_EXECUTION_STEPS
    + PIPELINE_RESPONSE_STEPS
)
"""26 步的**全量**拼接（`docs/07` §9）。

验收测试断言它**逐条等于** `app.application.execution.EXECUTION_PIPELINE_ORDER`：
本批把 26 步按归属分区（MCP 层 / 闸门链 / Task / 执行链 / 响应），
分区常量拼接后必须还原整条冻结顺序 —— 分区只是**组织方式**，不改顺序、不删步。
"""

METRIC_REQUESTS_TOTAL: Final[str] = "structai_requests_total"
METRIC_TASK_TOTAL: Final[str] = "structai_task_total"
METRIC_TASK_FAILED_TOTAL: Final[str] = "structai_task_failed_total"
METRIC_AUDIT_TOTAL: Final[str] = "structai_audit_total"
METRIC_REQUEST_DURATION: Final[str] = "structai_request_duration_seconds"
METRIC_EVENTS_TOTAL: Final[str] = "structai_events_total"
"""本服务写入的标准指标名（`docs/02` §14 清单的子集）。"""


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """一次执行的对外结果（`docs/02` §89 的 SYNC / ASYNC 响应形状 ＋ 诊断字段）。

    Attributes:
        mode: `SYNC` / `ASYNC` / `DRY_RUN`（`docs/02` §46 / §92）。
        status: 真实状态（`TaskStatus` 取值，或 `DRY_RUN` / 重放时的 `COMPLETED`）。
        tool: MCP Tool 名（`docs/07` §5.1）。
        operation: 规范化 Operation 名（`docs/02` §24）。
        task_id: 任务标识（`SYNC` / `ASYNC` 都有；Dry Run 为 `None`）。
        result: 规范化结果（`SYNC`）或首次执行的响应快照（重放）。
        replayed: 是否命中幂等重放（`docs/02` §86）。
        steps: 本次**实际执行过**的步骤名，按冻结顺序（供验收逐条断言）。
        unprovisioned_schemas: 未配备的 Schema id（`pipeline.py` 模块裁决 2）。
    """

    mode: str
    status: str
    tool: str
    operation: str
    task_id: str | None = None
    result: Mapping[str, Any] | None = None
    replayed: bool = False
    steps: tuple[str, ...] = ()
    unprovisioned_schemas: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """归一化响应（`docs/02` §89 的键 ＋ 诊断键）。"""
        return {
            "mode": self.mode,
            "status": self.status,
            "tool": self.tool,
            "operation": self.operation,
            "task_id": self.task_id,
            "result": None if self.result is None else dict(self.result),
            "replayed": self.replayed,
            "steps": list(self.steps),
            "unprovisioned_schemas": list(self.unprovisioned_schemas),
        }


@dataclass(frozen=True, slots=True)
class ExecutionSession:
    """一次请求在进程内留下的执行上下文（见模块裁决 4；**Alpha 限制**）。

    Attributes:
        context: 服务端执行上下文（`docs/02` §6）。
        tool_span_id: 根 TOOL Span 的 id，供 Worker 路径把 OPERATION Span 挂到它下面
            （`docs/02` §12 的标准 Trace 树）。
    """

    context: ExecutionContext
    tool_span_id: str | None = None


class ResultNormalizerPort(Protocol):
    """结果规范化端口（`docs/02` §49 / §90）。

    实现 = `app.application.services.result.ResultService`（**同层**）。本服务只要求
    它返回一个带 `data` 属性的对象（或直接返回映射）；`pipeline.py` 的 `normalizer`
    参数接受一个已适配的**函数**，故本服务把两者接起来。
    """

    def normalize(self, operation: str, raw: Mapping[str, Any] | Sequence[Any]) -> object: ...


# ===== 执行服务 =====


class ExecutionService:
    """Core 主干：26 步管线的**选路 + Task 创建 + 响应组装**（`docs/07` §9 / §12 P36）。

    ⚠️ 本类**不是**巨型类（`docs/07` §14.4）：闸门链在 `pipeline.py`，各步判定在各自的
    步骤服务里，本类只做三件事 —— 选路（`docs/02` §46）、建 Task（§90）、组装响应（§89）。
    持久化经 Domain 契约注入，事务边界归调用方的 `UnitOfWork`（`docs/02` §16）——
    本类**从不** `commit` / `rollback`。

    Attributes:
        pipeline: 26 步的闸门 / 结果链编排（`app/application/execution/pipeline.py`）。
        tasks: 任务引擎（P22–P28；`docs/02` §48 / §86–§94）。
        adapters: 第 18 步的 Adapter 端口（收窄契约；实现 = P19–P20 的 `AdapterManager`）。
        audit: 审计写入端口（Domain `AuditRecorder`；实现 = `app/observability/audit.py`）。
        trace: 链路追踪端口（Domain `TraceRecorder`；实现 = `app/observability/tracing.py`）。
        metrics: 指标端口（Domain `MetricsRecorder`；实现 = `app/observability/metrics.py`）。
        events: 事件总线（Domain `EventBus`；未注入 Outbox 时直接发布，见模块裁决 6）。
        outbox: Outbox 存储（Domain `EventRecordStore`；注入时**只**追加，见模块裁决 6）。
        results: 可选的结果规范化服务（`docs/02` §49 / §90）。
        max_retries: 引擎级重试预算缺省值（`docs/02` §77 / §78）。
    """

    def __init__(
        self,
        *,
        pipeline: ExecutionPipeline,
        tasks: TaskEngine,
        adapters: AdapterExecutor | None = None,
        audit: AuditRecorder | None = None,
        trace: TraceRecorder | None = None,
        metrics: MetricsRecorder | None = None,
        events: EventBus | None = None,
        outbox: EventRecordStore | None = None,
        results: ResultNormalizerPort | None = None,
        max_retries: int = 0,
    ) -> None:
        """绑定管线、任务引擎与各可选端口（**全部**由调用方注入）。"""
        self._pipeline = pipeline
        self._tasks = tasks
        self._adapters = adapters
        self._audit = audit
        self._trace = trace
        self._metrics = metrics
        self._events = events
        self._outbox = outbox
        self._results = results
        self._max_retries = max_retries
        self._sessions: dict[str, ExecutionSession] = {}
        self._normalizer = self._build_normalizer(results)

    # ===== 只读视图（供容器 / 验收断言）=====

    @property
    def pipeline(self) -> ExecutionPipeline:
        """被绑定的管线（只读用途）。"""
        return self._pipeline

    @property
    def tasks(self) -> TaskEngine:
        """被绑定的任务引擎（只读用途）。"""
        return self._tasks

    @property
    def outbox(self) -> EventRecordStore | None:
        """被绑定的 Outbox（只读用途；缺省 `None` 表示直接发布事件）。"""
        return self._outbox

    def session_count(self) -> int:
        """进程内登记的上下文条数（见模块裁决 4；诊断用）。"""
        return len(self._sessions)

    # ===== 入口一：26 步请求（MCP 层调用；`docs/02` §86）=====

    async def execute_request(self, request: PipelineRequest) -> ExecutionResult:
        """执行一次请求：闸门链 → Task → （SYNC 等完成 / ASYNC 立即返回）。

        Args:
            request: 管线请求（`docs/02` §27 / §33）。

        Returns:
            `ExecutionResult`（`docs/02` §89 的响应形状）。

        Raises:
            StructAIError: 20 码契约内的任何失败（闸门链的拒绝、任务失败、
                未装配端口等）；失败时**不**吞异常，只补记审计 / Trace / Event。
        """
        started_at = perf_counter()
        mcp_span = await self._start_span(
            str(TraceSpanKind.MCP),
            "MCP",
            request=request,
        )
        tool_span = await self._start_span(
            str(TraceSpanKind.TOOL),
            request.tool,
            request=request,
            parent_span_id=None if mcp_span is None else mcp_span.id,
        )
        gate: PipelineGate | None = None
        task_created = False
        try:
            gate = await self._pipeline.gate(request, acquire_lock=request.dry_run)
            if gate.replayed:
                outcome = self._replayed_result(gate)
            elif request.dry_run:
                outcome = await self._dry_run_result(gate)
            else:
                outcome, task_created = await self._task_result(
                    gate,
                    tool_span_id=None if tool_span is None else tool_span.id,
                )
        except Exception as error:
            await self._finish_spans(
                (tool_span, mcp_span),
                status=str(TraceStatus.ERROR),
            )
            self._observe_request_duration(request, started_at)
            if not task_created:
                # 见模块裁决 5：Task 创建**之前**的拒绝在这里记审计；
                # 已进 Worker 的失败由 `execute()` 记过（避免双计）。
                await self._record_refusal(request, error)
            raise
        await self._finish_spans((tool_span, mcp_span), status=str(TraceStatus.OK))
        # `docs/02` §14 的 `structai_requests_total` / `structai_request_duration_seconds`
        # 必须在**成功**路径上也可见（P135c：真实一次 MCP 调用端到端可见）。
        self._count(
            METRIC_REQUESTS_TOTAL,
            labels={
                "tool": request.tool,
                "operation": request.operation,
                "status": str(AuditResult.SUCCESS),
            },
        )
        self._observe_request_duration(request, started_at)
        return outcome

    # ===== 入口二：TaskExecutor 端口（P22–P28 的 Worker 调用；`docs/02` §88）=====

    async def execute(
        self,
        task: TaskRecord,
        *,
        context: ExecutionContext | None = None,
    ) -> Mapping[str, Any]:
        """Worker 取到任务后的真正执行：第 18–25 步（`docs/02` §88 / §91）。

        Args:
            task: 被 Worker 认领的任务（`docs/02` §10）。
            context: 执行上下文；缺省时从进程内登记里取（见模块裁决 4）。

        Returns:
            规范化结果（`docs/02` §89）；Worker 随后把它落 `tasks.result_json`。

        Raises:
            InternalError: `STRUCTAI-7000` —— 上下文不可得（见模块裁决 4）、
                未装配 Adapter 端口、任务缺少软件实例、参数不可解析、未知 Operation。
            StructAIError: Adapter / 后置条件的失败原样上抛（Worker 会落库并转状态）。
        """
        session = self._sessions.get(task.id)
        execution_context = context or (None if session is None else session.context)
        if execution_context is None:
            raise InternalError(
                "Execution context is not available for this task",
                details={"stage": EXECUTION_STAGE, "reason": "context_not_available"},
            )
        if self._adapters is None:
            raise InternalError(
                "Adapter executor is not configured",
                details={"stage": EXECUTION_STAGE, "reason": "adapter_not_configured"},
            )
        definition = await self._pipeline.operations.get(task.operation)
        if definition is None:
            raise InternalError(
                "Unknown operation for task",
                details={"stage": EXECUTION_STAGE, "reason": "unknown_operation"},
            )
        instance_id = execution_context.software.instance_id
        if instance_id is None:
            raise InternalError(
                "Task has no software instance in its execution context",
                details={"stage": EXECUTION_STAGE, "reason": "software_instance_unresolved"},
            )
        parameters = await self._parameters_for(task)
        operation_span = await self._start_span(
            str(TraceSpanKind.OPERATION),
            task.operation,
            request=None,
            context=execution_context,
            parent_span_id=None if session is None else session.tool_span_id,
            task_id=task.id,
        )
        adapter_span = await self._start_span(
            str(TraceSpanKind.ADAPTER),
            task.operation,
            request=None,
            context=execution_context,
            parent_span_id=None if operation_span is None else operation_span.id,
            task_id=task.id,
        )
        try:
            raw = await self._adapters.execute(
                str(instance_id),
                task.operation,
                parameters,
                execution_context,
            )
        except Exception as error:
            await self._finish_spans((adapter_span, operation_span), status=str(TraceStatus.ERROR))
            await self._record_task_outcome(task, definition, execution_context, error=error)
            raise
        result = self._pipeline.normalize(definition, raw)
        # 第 20 步（Postconditions）先于第 21 步（Release Lock，由 Worker 的 finally 负责）。
        await self._pipeline.postconditions(definition, result_available=True)
        await self._finish_spans((adapter_span, operation_span), status=str(TraceStatus.OK))
        await self._record_task_outcome(task, definition, execution_context, result=result)
        return result

    # ===== 三种路径 =====

    async def _task_result(
        self,
        gate: PipelineGate,
        *,
        tool_span_id: str | None,
    ) -> tuple[ExecutionResult, bool]:
        """第 17–26 步：建 Task → （SYNC 等完成 / ASYNC 立即返回）（`docs/02` §88 / §89）。

        Returns:
            `(ExecutionResult, task_created)`；`task_created` 供 `execute_request`
            判定「失败是否已在 Worker 侧记过审计」（见模块裁决 5）。
        """
        view = await self._tasks.submit(self._submission_for(gate))
        task_id = view.task_id
        # 见模块裁决 4：进程内登记上下文，供 Worker 路径取回。
        self._sessions[task_id] = ExecutionSession(
            context=gate.request.context,
            tool_span_id=tool_span_id,
        )
        mode = self._mode_of(gate.definition)
        if mode != SYNC_MODE:
            queued = ExecutionResult(
                mode=mode,
                status=str(TaskStatus.QUEUED),
                tool=gate.request.tool,
                operation=gate.definition.name,
                task_id=task_id,
                steps=gate.steps + (PIPELINE_TASK_STEP,) + PIPELINE_RESPONSE_STEPS,
                unprovisioned_schemas=gate.unprovisioned_schemas,
            )
            # 第 22 步（`docs/02` §64）：ASYNC 的**首次响应**就是 `{mode, status, task_id}`
            # 信封（§89），故它即幂等快照；`complete()` 只写一次（first writer wins）。
            await self._complete_idempotency(gate, queued.result)
            return (queued, True)
        record = await self._tasks.run_task(task_id, SYNC_WORKER_ID)
        self._raise_for_task_failure(record)
        completed = ExecutionResult(
            mode=SYNC_MODE,
            status=str(record.status),
            tool=gate.request.tool,
            operation=gate.definition.name,
            task_id=task_id,
            result=self._decode_result(record),
            steps=gate.steps
            + (PIPELINE_TASK_STEP,)
            + PIPELINE_EXECUTION_STEPS
            + PIPELINE_RESPONSE_STEPS,
            unprovisioned_schemas=gate.unprovisioned_schemas,
        )
        await self._complete_idempotency(gate, completed.result)
        return (completed, True)

    async def _complete_idempotency(
        self,
        gate: PipelineGate,
        response: Mapping[str, Any] | None,
    ) -> None:
        """第 22 步（`docs/02` §64 / §86）：把首次成功的响应写入幂等记录。

        ⚠️ 只在**本次抢占了幂等键**（`decision.reserved`）且确有响应时写入；
        重放路径不写（`docs/02` §86），`complete()` 本身也只写一次
        （`repositories/idempotency.py` 的 `WHERE response_json IS NULL`）。
        """
        decision = gate.decision
        if decision is None or not decision.reserved or response is None:
            return
        await self._pipeline.idempotency.complete(decision.record.id, dict(response))

    async def _dry_run_result(self, gate: PipelineGate) -> ExecutionResult:
        """Dry Run 路径（`docs/02` §30 / §92）：**不**建 Task、**不**执行 Adapter。

        ⚠️ 第 15 步的锁由本路径自己持有（`acquire_lock=True`），故第 20 步
        （Postconditions）之后必须走第 21 步（Release Lock）—— 见模块裁决 1。
        """
        if not gate.definition.dry_run_supported:
            raise EngineeringValidationError(
                "Operation does not support dry run",
                details={
                    "stage": EXECUTION_STAGE,
                    "reason": "dry_run_not_supported",
                    "operation": gate.definition.name,
                },
            )
        try:
            await self._pipeline.postconditions(gate.definition, resource=gate.resource)
        finally:
            await self._pipeline.release(gate)
        dry_run = ExecutionResult(
            mode=DRY_RUN_MODE,
            status=str(TaskStatus.COMPLETED),
            tool=gate.request.tool,
            operation=gate.definition.name,
            result=dict(DRY_RUN_PAYLOAD),
            steps=gate.steps + ("Postconditions", "Release Lock") + PIPELINE_RESPONSE_STEPS,
            unprovisioned_schemas=gate.unprovisioned_schemas,
        )
        await self._complete_idempotency(gate, dry_run.result)
        return dry_run

    def _replayed_result(self, gate: PipelineGate) -> ExecutionResult:
        """幂等重放路径（`docs/02` §86）：**直接返回**首次响应，不执行 Adapter。

        见模块裁决 5：重放**不**再记审计 / Trace / Event（首次执行时已记）。
        """
        return ExecutionResult(
            mode=self._mode_of(gate.definition),
            status=str(TaskStatus.COMPLETED),
            tool=gate.request.tool,
            operation=gate.definition.name,
            # 重放**不**新建任务（`docs/02` §86：直接返回首次响应）。
            task_id=None,
            result={} if gate.replayed_response is None else dict(gate.replayed_response),
            replayed=True,
            steps=gate.steps + PIPELINE_RESPONSE_STEPS,
            unprovisioned_schemas=gate.unprovisioned_schemas,
        )

    # ===== 请求 → TaskSubmission =====

    def _submission_for(self, gate: PipelineGate) -> TaskSubmission:
        """把闸门产物转成一次任务提交（`docs/02` §9 / §90）。

        参数随 `TaskStepDraft.parameters_json` **落库**（见模块裁决 3），
        使 Worker 路径（甚至另一个进程）能重建参数。
        """
        request = gate.request
        identity = request.identity
        instance_id = request.context.software.instance_id
        step = TaskStepDraft(
            step_key=gate.definition.name,
            operation=gate.definition.name,
            parameters_json=canonical_payload(dict(request.parameters)),
        )
        return TaskSubmission(
            tenant_id=str(identity.tenant_id),
            request_id=request.context.request_id,
            trace_id=request.context.trace_id,
            tool=request.tool,
            operation=gate.definition.name,
            project_id=None if gate.resource is None else gate.resource.project_id,
            software_instance_id=None if instance_id is None else str(instance_id),
            user_id=str(identity.user_id),
            priority=request.priority,
            max_retries=request.max_retries if request.max_retries > 0 else self._max_retries,
            steps=(step,),
        )

    def _mode_of(self, definition: OperationDefinition) -> str:
        """执行模式（`docs/02` §46；`STREAM` 按 `ASYNC` 处理，见模块裁决 2）。"""
        mode = str(definition.execution_mode)
        return ASYNC_MODE if mode == str(ExecutionMode.STREAM) else mode

    async def _parameters_for(self, task: TaskRecord) -> Mapping[str, Any]:
        """从 `task_steps.parameters_json` 取回参数（见模块裁决 3）。

        Raises:
            InternalError: `STRUCTAI-7000` —— 参数 JSON 损坏或不是对象
                （**不**回落空参数：静默用空参数会让一次写操作变成「什么都没做」）。
        """
        steps = list(await self._tasks.store.list_steps(task.id))
        candidates = [step for step in steps if step.operation == task.operation] or steps
        if not candidates:
            return {}
        payload = candidates[0].parameters_json or "{}"
        try:
            parsed: object = json.loads(payload)
        except json.JSONDecodeError as error:
            raise InternalError(
                "Task step parameters are not valid JSON",
                details={"stage": EXECUTION_STAGE, "reason": "corrupt_parameters"},
                cause=error,
            ) from error
        if not isinstance(parsed, Mapping):
            raise InternalError(
                "Task step parameters are not a JSON object",
                details={"stage": EXECUTION_STAGE, "reason": "invalid_parameters"},
            )
        return {str(key): value for key, value in parsed.items()}

    # ===== 结果规范化接线 =====

    @staticmethod
    def _build_normalizer(results: ResultNormalizerPort | None) -> Any:
        """把 `ResultService` 适配成 `pipeline.normalize` 需要的函数（`docs/02` §49 / §90）。

        `ResultService.normalize` 返回 `CanonicalResult`（带 `data`），而管线只要求
        「Operation + 原始映射 → 规范化映射」。适配只取 `data`（`docs/02` §90 的信封
        由 Tool 层组装），因此这里**不**改变 `ResultService` 的任何语义。
        """
        if results is None:
            return None

        def _normalize(operation: str, raw: Mapping[str, Any]) -> Mapping[str, Any]:
            normalized = results.normalize(operation, raw)
            data = getattr(normalized, "data", normalized)
            if isinstance(data, Mapping):
                return {str(key): value for key, value in data.items()}
            return {"data": data}

        return _normalize

    # ===== 观测接线（审计 / Trace / Metrics / Event；`docs/02` §61 / §64 / §65 / §5.4）=====

    async def _start_span(
        self,
        kind: str,
        name: str,
        *,
        request: PipelineRequest | None,
        context: ExecutionContext | None = None,
        parent_span_id: str | None = None,
        task_id: str | None = None,
    ) -> TraceSpanRecord | None:
        """开一个 Span（`docs/02` §10 / §11）；未注入 Trace 端口时返回 `None`。"""
        if self._trace is None:
            return None
        execution_context = (
            context if context is not None else (None if request is None else request.context)
        )
        trace_id = None if execution_context is None else execution_context.trace_id
        request_id = None if execution_context is None else execution_context.request_id
        return await self._trace.start_span(
            name,
            trace_id,
            parent_span_id,
            {"kind": kind},
            kind=kind,
            request_id=request_id,
            task_id=task_id,
        )

    async def _finish_spans(
        self,
        spans: Sequence[TraceSpanRecord | None],
        *,
        status: str,
    ) -> None:
        """结束若干 Span（`docs/02` §11 的 `end_span`）；`None` 一律跳过。"""
        if self._trace is None:
            return
        for span in spans:
            if span is None:
                continue
            await self._trace.end_span(span, status)

    async def _record_task_outcome(
        self,
        task: TaskRecord,
        definition: OperationDefinition,
        context: ExecutionContext,
        *,
        result: Mapping[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        """记录一次「到达 Adapter 步」的尝试（见模块裁决 5）。

        - 审计：**恰好一条**（`docs/02` §8.3 的动作名经 `audit_action_for` 推导）；
        - 指标：`structai_task_total`（＋失败时 `structai_task_failed_total`）；
        - 事件：`TaskCompleted` / `TaskFailed`，先写 Outbox（见模块裁决 6）。
        """
        result_kind = self._result_kind(error)
        await self._audit_now(
            context,
            action=audit_action_for(definition.name),
            result=str(result_kind),
            resource_type=definition.tool,
            resource_id=task.id,
            metadata={
                "operation": definition.name,
                "task_id": task.id,
                "error_code": self._error_code(error),
            },
        )
        self._count(
            METRIC_TASK_TOTAL,
            labels={"operation": definition.name, "status": str(result_kind)},
        )
        if error is not None:
            self._count(METRIC_TASK_FAILED_TOTAL, labels={"operation": definition.name})
        await self._emit(
            self._task_event(task, error),
            tenant_id=task.tenant_id,
            project_id=task.project_id,
            request_id=task.request_id,
            trace_id=task.trace_id,
        )

    async def _record_refusal(self, request: PipelineRequest, error: Exception) -> None:
        """记录一次「Task 创建之前」的拒绝（见模块裁决 5）。"""
        result_kind = self._result_kind(error)
        await self._audit_now(
            request.context,
            action=audit_action_for(request.operation),
            result=str(result_kind),
            resource_type=request.tool,
            resource_id=None,
            metadata={
                "operation": request.operation,
                "error_code": self._error_code(error),
            },
        )
        self._count(
            METRIC_REQUESTS_TOTAL,
            labels={
                "tool": request.tool,
                "operation": request.operation,
                "status": str(result_kind),
            },
        )

    async def _audit_now(
        self,
        context: object,
        *,
        action: str,
        result: str,
        resource_type: str | None,
        resource_id: str | None,
        metadata: Mapping[str, Any] | None,
    ) -> None:
        """写一条审计（`docs/02` §8.3 / §35：与业务写同一 `UnitOfWork`）。"""
        if self._audit is None:
            return
        await self._audit.record_context(
            context,
            action=action,
            result=result,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
        )
        self._count(METRIC_AUDIT_TOTAL)

    def _count(
        self,
        name: str,
        value: float = 1,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        """写一个计数器（`docs/02` §13 / §14）；未注入指标端口时**无操作**。"""
        if self._metrics is None:
            return
        self._metrics.counter(name, value, labels)

    def _observe_request_duration(self, request: PipelineRequest, started_at: float) -> None:
        """记录一次请求的耗时观测（`docs/02` §14 的 `structai_request_duration_seconds`）。

        ⚠️ 只放**低基数**标签（`tool` / `operation`），与 `_count` 同一口径；
        租户 / 用户 / 请求标识一律不进标签（`docs/02` §15 的高基数清单）。
        """
        if self._metrics is None:
            return
        self._metrics.observe(
            METRIC_REQUEST_DURATION,
            max(perf_counter() - started_at, 0.0),
            {"tool": request.tool, "operation": request.operation},
        )

    async def _emit(
        self,
        event: object,
        *,
        tenant_id: str | None,
        project_id: str | None,
        request_id: str | None,
        trace_id: str | None,
    ) -> None:
        """第 25 步：事件（`docs/02` §5.4；见模块裁决 6）。

        注入 Outbox → **只**追加 `PENDING` 记录（发布交给 `EventDispatcher`）；
        未注入 Outbox 且注入了 `EventBus` → 直接发布（§5.4 允许的 Alpha 形态）；
        两者都没有 → 无操作（未装配观测端口不是失败）。
        """
        task_id = self._as_str(getattr(event, "task_id", None))
        if self._outbox is not None:
            await self._outbox.append(
                EventRecordDraft(
                    event_type=type(event).__name__,
                    payload_json=self._event_payload(event),
                    tenant_id=tenant_id,
                    project_id=project_id,
                    request_id=request_id,
                    trace_id=trace_id,
                    task_id=task_id,
                )
            )
            self._count(METRIC_EVENTS_TOTAL)
            return
        if self._events is None:
            return
        if isinstance(event, DomainEvent):
            await self._events.publish(event)
            self._count(METRIC_EVENTS_TOTAL)

    @staticmethod
    def _event_payload(event: object) -> str:
        """事件载荷的 JSON 文本（**只**放非敏感字段；`docs/07` §14.3）。"""
        payload: dict[str, Any] = {}
        event_id = getattr(event, "event_id", None)
        if event_id is not None:
            payload["event_id"] = str(event_id)
        occurred_at = getattr(event, "occurred_at", None)
        if occurred_at is not None:
            payload["occurred_at"] = occurred_at.isoformat()
        task_id = getattr(event, "task_id", None)
        if task_id is not None:
            payload["task_id"] = str(task_id)
        error_code = getattr(event, "error_code", None)
        if error_code is not None:
            payload["error_code"] = str(error_code)
        return canonical_payload(payload)

    def _task_event(self, task: TaskRecord, error: Exception | None) -> object:
        """构造任务类 Domain Event（`docs/02` §34：`TaskCompleted` / `TaskFailed`）。"""
        task_uuid = self._as_uuid(task.id)
        if error is None:
            return TaskCompleted.create(task_id=task_uuid)
        return TaskFailed.create(task_id=task_uuid, error_code=self._error_code(error))

    # ===== 结果 / 错误的还原 =====

    def _raise_for_task_failure(self, record: TaskRecord) -> None:
        """SYNC 路径：任务未完成 → 把 Worker 记录的真实失败如实上抛。

        Raises:
            StructAIError: 落库信封里的 `code` 对应的既有异常（20 码契约）；
                未知 / 缺失 `code` 时回落 `TaskError`（`STRUCTAI-5000`）。
        """
        if str(record.status) == str(TaskStatus.COMPLETED):
            return
        envelope = self._decode_error(record)
        code = None if envelope is None else envelope.get("code")
        error_class = ERROR_CLASSES.get(str(code)) if code is not None else None
        message = (
            str(envelope.get("message"))
            if envelope is not None and envelope.get("message")
            else "Task did not complete"
        )
        details: dict[str, Any] = {
            "stage": EXECUTION_STAGE,
            "reason": "task_not_completed",
            "status": str(record.status),
        }
        if envelope is not None:
            details["task_error"] = envelope
        if error_class is None:
            raise TaskError(message, details=details)
        raise error_class(message, details=details)

    def _decode_result(self, record: TaskRecord) -> Mapping[str, Any] | None:
        """`tasks.result_json` → 规范化结果（`docs/02` §53 / §89）。"""
        if record.result_json is None:
            return None
        parsed = self._decode_json(record.result_json, reason="corrupt_result")
        if not isinstance(parsed, Mapping):
            raise InternalError(
                "Stored task result is not a JSON object",
                details={"stage": EXECUTION_STAGE, "reason": "invalid_result"},
            )
        return {str(key): value for key, value in parsed.items()}

    def _decode_error(self, record: TaskRecord) -> dict[str, Any] | None:
        """`tasks.error_json` → 归一化错误信封（`docs/02` §34；损坏即 `None`）。"""
        if record.error_json is None:
            return None
        try:
            parsed = self._decode_json(record.error_json, reason="corrupt_error")
        except InternalError:
            return None
        if not isinstance(parsed, Mapping):
            return None
        return {str(key): value for key, value in parsed.items()}

    @staticmethod
    def _decode_json(payload: str, *, reason: str) -> object:
        """解析一段落库 JSON 文本。

        Raises:
            InternalError: `STRUCTAI-7000` —— 不是合法 JSON（**不**静默当作空值）。
        """
        try:
            return json.loads(payload)
        except json.JSONDecodeError as error:
            raise InternalError(
                "Stored JSON payload is corrupt",
                details={"stage": EXECUTION_STAGE, "reason": reason},
                cause=error,
            ) from error

    @staticmethod
    def _result_kind(error: Exception | None) -> AuditResult:
        """审计结果（见模块裁决 8）。"""
        if error is None:
            return AuditResult.SUCCESS
        code = error.code if isinstance(error, StructAIError) else None
        return AuditResult.DENIED if code in DENIED_ERROR_CODES else AuditResult.FAILURE

    @staticmethod
    def _error_code(error: Exception | None) -> str | None:
        """异常的 20 码（非 `StructAIError` → `None`，**不**编造码）。"""
        if isinstance(error, StructAIError):
            return error.code
        return None

    @staticmethod
    def _as_uuid(value: str | None) -> UUID | None:
        """UUID 字符串 → `UUID`；非法值返回 `None`（**不**抛异常）。"""
        if not value:
            return None
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_str(value: object) -> str | None:
        """任意标识 → `str | None`（`None` 原样返回）。"""
        return None if value is None else str(value)
