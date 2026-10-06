"""Application · Execution · Pipeline（`docs/07` §9；`docs/02` §30 / §49–§74 / §90–§93）。

为什么单独拆一个 `pipeline.py`（`docs/07` §14.4）
-----------------------------------------------
`docs/07` §14.4 的红线是「**`ExecutionService` 不得变成巨型类**」，`docs/02` §91 要求
「各步骤由独立服务承担（见 §3.3 目录）」。故本模块承载**闸门链**（第 5–16 步）与
**结果链**（第 19–25 步）的编排，`service.py` 只负责「选路（SYNC / ASYNC / DRY_RUN）
+ Task 创建 + 响应组装」，并实现 P22–P28 的 `TaskExecutor` 端口（`worker.py`）。

权威来源
--------
- `docs/07` §9 —— **26 步冻结顺序**（`EXECUTION_PIPELINE_ORDER` 的唯一权威在
  `app/application/execution/__init__.py`）。本模块把该 26 步**按归属分区**，
  分区常量拼接后必须**逐条等于** `EXECUTION_PIPELINE_ORDER`（验收测试断言）。
- `docs/02` §49–§74（`exec`）—— 每一步的判定语义：`Operation Resolve` / `Resource
  Resolve` / `Schema Validation` / `Engineering Validation` / `Permission` /
  `Confirmation` / `Idempotency` / `Lock` / `Capability`。
- `docs/02` §90（`Execution Pipeline 的最终职责划分`）—— 各步职责的划分表。
- `docs/02` §90 / §91 / §92 / §93（`task`）—— `ExecutionService → Idempotency →
  Task Create` 顺序不变；**长任务在 Worker 取到任务后才抢资源锁**；Confirmation 与
  Capability 的基本检查必须在 Task 创建**之前**。
- `docs/07` §11 —— `STRUCTAI-1000`（Tool / Operation 不匹配）、`1200`（工程语义 /
  前置条件 / Dry Run 不支持）、`1300`（幂等冲突）、`3000`（能力）、`4000`（权限）、
  `4100`（确认）、`5000`（后置条件 / 配额）、`6000`（Adapter 返回非规范化结果）、
  `7000`（装配缺失）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **锁的持有者是 Worker，不是 Pipeline**（`docs/02` §91，逐字照抄）：
   「`Task Created ↓ Queued` 时不一定立即持有 Model Write Lock；推荐
   `Worker 获得 Task ↓ Acquire Resource Lock ↓ Execute ↓ Release`，这样队列不会
   长时间占用锁」。故 `gate()` 的 `acquire_lock` 是**显式参数**：
   走 Task Engine 的路径（SYNC 与 ASYNC 都是，`docs/02` §87 / §88）→
   `acquire_lock=False`，第 15 步记为**委派**（`PipelineGate.lock is None`），
   第 21 步由 `TaskWorker` 的 `finally` 释放；**Dry Run** 与直接的管线调用（无 Task）
   → `acquire_lock=True`，本模块在第 15 步抢锁、第 21 步释放。
   **26 步的顺序与数量都不变**，变的只是「谁在第 15 步拿锁」—— 这正是 §91 的规定。
   若两处都抢锁，Worker 会在同一资源键上与自己冲突（`STRUCTAI-6100`），
   即「队列长时间占用锁」的反面。
2. **未配备的 Schema 不是静默通过**（`docs/02` §17 / §30）：69 个 Operation 的
   `input_schema` 是 Core **自有** Schema（`docs/02` §22 的 `schemas/`），本批尚未产出，
   而 P09 的 `SchemaRegistry` 只登记数据侧（外部软件 API）的 616 个 Schema。
   `SchemaEngine.validate` 对未登记 id 抛 `NotFoundError`（**不带** 20 码，
   `docs/07` §11 补充说明）。本模块捕获它并把该 schema id 记进
   `PipelineGate.unprovisioned_schemas`（+ Trace 属性 + Metrics 计数），
   **不**当作校验通过：结构合法性的**缺失**因此是可观测的事实，而不是静默的绿灯。
3. **前置条件的事实只来自已完成步骤**（`docs/07` §16 R29）：`Preconditions`（第 10 步）
   在 `Capability Check`（第 16 步）**之前**，故本模块构造的 `ExecutionFacts` 里
   `supported_capabilities` 一律为 `None`（= **未验证**，既不判通过也不判失败），
   `task_status` / `result_available` 同样为 `None`（Task 尚未创建）。
   事实缺失 → `unverified`，绝不当作通过（`docs/02` §32）。
4. **后置条件在 Task 置 `COMPLETED` 之前求值 → 一律「未验证」**：
   `postconditions` 的 `task_completed` 只接受 `TaskStatus.COMPLETED`
   （`RECOVERING` / `RETRYING` 都算未满足，`docs/07` §14.4），而第 20 步发生在
   `TaskWorker._mark_completed` **之前**。故 `finish()` 传入的
   `ExecutionFacts.task_status` 是 `None`（未验证），并把 `result_available=True`
   如实置上。这不是「跳过」：`docs/02` §32 的三态语义明确「事实缺失时返回未验证」，
   而**顺序**（`Postconditions` 先于 `Release Lock`）由 `POSTCONDITION_STAGE_ORDER`
   与 Worker 的 `finally` 结构性保证。
5. **配额闸门是收窄契约**（`docs/02` §36 / §60）：Application 层不得依赖
   `app.infrastructure`，而 `QuotaService`（`app/application/services/quota.py`）在**同层**，
   故直接用 `QuotaGate` 结构契约调用其 `consume_api_request`。
   决策对象**必须**暴露 `allowed`；缺该属性 = 装配错误 → `STRUCTAI-7000`
   （**不**回落「放行」—— 静默放行会让配额形同虚设）。
6. **`Resolve Tool`（第 5 步）就是 Tool ↔ Operation 一致性检查**（`docs/02` §82
   `Tool Mismatch Test`）：`OperationDefinition.tool` 必须等于请求声明的 `tool`，
   否则 `STRUCTAI-1000`（「未知 Tool / 请求格式非法」）。
7. **幂等键的摘要载荷 = 本请求对象本身**（`docs/02` §33 逐字要求
   `{tool, operation, parameters, context, dry_run}`）：`PipelineRequest` 的这五个字段
   与 §33 一一对应，故直接把它交给 `IdempotencyService.hash_request`
   （`hash_request` 只读这五个字段，多余字段不参与摘要）。
   `priority` / `max_retries` 因此**不**影响摘要 —— 同一 Tool / Operation / 参数 /
   上下文 / dry_run 的请求就是「同一请求」（`docs/02` §33），重放返回首次响应。
8. **重放路径不重复发审计 / Trace / Event**（`docs/02` §86「直接 `return cached
   response`」）：首次执行时已经发过；再发一次会让审计与指标**双计**。
9. **`Adapter` 步骤经收窄契约注入**（`docs/02` §87 / §56）：真实实现是
   `app.infrastructure.adapters.base.manager.AdapterManager`（**进程级**，P19–P20），
   而 Application 层不得依赖 `app.infrastructure`，故本模块只声明
   `AdapterExecutor` 契约，由容器注入实现。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain` / **同层**的 `app.application.*`：
**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖 `app.infrastructure` /
`app.interfaces` / `app.observability`（审计 / Trace / Metrics 经 Domain 收窄契约注入），
也**不**出现任何厂商专属内容。事务边界归调用方的 `UnitOfWork`（`docs/02` §16）——
本模块**从不** `commit` / `rollback`。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from app.application.execution.confirmation import ConfirmationGuard
from app.application.execution.context import ExecutionContext
from app.application.execution.engineering_validator import EngineeringValidator
from app.application.execution.idempotency import IdempotencyDecision, IdempotencyService
from app.application.execution.postconditions import PostconditionEvaluator, PostconditionReport
from app.application.execution.preconditions import ExecutionFacts, PreconditionEvaluator
from app.application.execution.validation import SchemaEngine
from app.application.resource.lock_manager import LockHandle, ResourceLockManager
from app.application.resource.lock_policy import LockPolicy, ResourceKey
from app.application.resource.resolver import ResolvedResource, ResourceResolver
from app.application.security.context import IdentityContext
from app.application.security.permission import EffectivePermissionService
from app.application.services.capability_resolver import CapabilityDecision, CapabilityResolver
from app.domain.enums import ResourceType, TaskPriority
from app.domain.errors import (
    AdapterError,
    InternalError,
    NotFoundError,
    ProtocolError,
    TaskError,
)
from app.domain.protocols import OperationDefinition, OperationRegistry

__all__ = [
    "AdapterExecutor",
    "ExecutionPipeline",
    "MCP_PIPELINE_STEPS",
    "PIPELINE_EXECUTION_STEPS",
    "PIPELINE_GATE_STEPS",
    "PIPELINE_RESPONSE_STEPS",
    "PIPELINE_STAGE",
    "PIPELINE_TASK_STEP",
    "PipelineGate",
    "PipelineRequest",
    "QuotaGate",
    "audit_action_for",
    "quota_allowed",
    "quota_refusal_details",
]

PIPELINE_STAGE: Final[str] = "pipeline"
"""错误 `details.stage` 的固定取值（与各步骤服务的 `stage` 同口径）。"""

# ===== 26 步的**归属分区**（拼接后必须逐条等于 `EXECUTION_PIPELINE_ORDER`）=====

MCP_PIPELINE_STEPS: Final[tuple[str, ...]] = (
    "MCP Request",
    "Authenticate",
    "Build Server IdentityContext",
    "Build ExecutionContext",
)
"""第 1–4 步：MCP 层与身份构造（`docs/07` §9；P37–P39 的 `interfaces/mcp/` 落点）。

本批**不**实现它们（`docs/08` §4：不要提前做 P37–P48）：`ExecutionContext` 必须由
**服务端**认证链构造（`docs/02` §6 / `docs/07` §8.1），本批由调用方传入已构造好的
`ExecutionContext`（`app/application/execution/context.py`）。
"""

PIPELINE_GATE_STEPS: Final[tuple[str, ...]] = (
    "Resolve Tool",
    "Resolve Operation",
    "Resolve Resource",
    "Schema Validation",
    "Engineering Validation",
    "Preconditions",
    "Effective Permission",
    "Quota / Rate Limit",
    "Confirmation",
    "Idempotency",
    "Concurrency / Resource Lock",
    "Capability Check",
)
"""第 5–16 步：本模块的**闸门链**（`ExecutionPipeline.gate`）。"""

PIPELINE_TASK_STEP: Final[str] = "Task / Transaction"
"""第 17 步：Task 创建（`docs/02` §90；由 `ExecutionService` 经 `TaskEngine` 执行）。"""

PIPELINE_EXECUTION_STEPS: Final[tuple[str, ...]] = (
    "Adapter",
    "Result Normalization",
    "Postconditions",
    "Release Lock",
    "Persist Result",
    "Audit",
    "Trace",
    "Event",
)
"""第 18–25 步：执行与收尾（`ExecutionPipeline.finish` / `release`；Adapter 由 Worker 调用）。"""

PIPELINE_RESPONSE_STEPS: Final[tuple[str, ...]] = ("MCP Response",)
"""第 26 步：响应组装（`ExecutionService` 的 `ExecutionResult`）。"""

DEFAULT_QUOTA_ALLOWED_ATTRIBUTE: Final[str] = "allowed"
"""配额决策必须暴露的属性名（见模块裁决 5）。"""

QUOTA_REFUSAL_CODE: Final[str] = "STRUCTAI-5000"
"""配额超限复用的既有码（见模块裁决 5；`docs/07` §11 的 `Task Error`，`retryable=True`）。"""

# ===== 收窄契约（Application 层不得依赖 `app.infrastructure` / `app.observability`）=====


class AdapterExecutor(Protocol):
    """执行第 18 步的 Adapter 端口（`docs/02` §62 / §87；`docs/07` §16 R38 的同一手法）。

    实现 = `app.infrastructure.adapters.base.manager.AdapterManager`
    （P19–P20，**进程级**对象），它已在结构上满足本契约：
    `execute(instance_id, operation, parameters, context) -> Mapping`，
    未绑定 / 未就绪 → `STRUCTAI-3000`，非映射结果 → `STRUCTAI-6000`
    （`adapters/base/adapter.py` 的 `execute_normalized`）。
    ⚠️ 参数名与 `AdapterManager.execute` 的**位置**参数保持一致；调用方一律按位置传参，
    使契约匹配不依赖关键字名。
    """

    async def execute(
        self,
        instance_id: str,
        operation: str,
        parameters: Mapping[str, Any],
        context: ExecutionContext,
    ) -> Mapping[str, Any]: ...


class QuotaGate(Protocol):
    """配额闸门端口（`docs/02` §36 / §60）。

    实现 = `app.application.services.quota.QuotaService`（**同层**，可直接注入）。
    返回对象必须暴露 `allowed`（见模块裁决 5）；`metric` / `limit` / `used` / `reason`
    用于组装 `STRUCTAI-5000` 的 `details`，缺失时按 `None` / `0` 如实记录。
    """

    async def consume_api_request(
        self,
        *,
        tenant_id: str,
        user_id: str,
        agent_id: str | None = None,
        instance_id: str | None = None,
    ) -> object: ...


# ===== 请求 / 闸门产物 =====


@dataclass(frozen=True, slots=True)
class PipelineRequest:
    """一次进入 26 步管线的请求（`docs/02` §27 的 `ToolRequest` + §33 的摘要载荷）。

    前五个字段与 `docs/02` §33 的 `hash_request` 载荷
    （`{tool, operation, parameters, context, dry_run}`）**一一对应**，
    故本对象可直接交给 `IdempotencyService.hash_request`（见模块裁决 7）。

    Attributes:
        tool: MCP Tool 名（`docs/07` §5.1）；必须与 `OperationDefinition.tool` 一致。
        operation: 规范化 Operation 名（`docs/02` §24）。
        parameters: 已规范化参数（`docs/02` §89：Adapter 只接受规范化输入）。
        context: **服务端**构造的执行上下文（`docs/02` §6；客户端不可声明身份）。
        idempotency_key: 可选幂等键（`docs/02` §31）。
        confirmation_token: 可选确认令牌（`docs/07` §8.4）；**绝不**记录 / 回显。
        dry_run: Dry Run 标志（`docs/02` §92）。
        priority: 任务优先级（`docs/02` §14）；**不**参与幂等摘要（见裁决 7）。
        max_retries: 任务重试预算（`docs/02` §77 / §78）；同上。
    """

    tool: str
    operation: str
    parameters: Mapping[str, Any]
    context: ExecutionContext
    idempotency_key: str | None = None
    confirmation_token: str | None = field(default=None, repr=False)
    dry_run: bool = False
    priority: TaskPriority | int | str = TaskPriority.NORMAL
    max_retries: int = 0

    @property
    def identity(self) -> IdentityContext:
        """服务端身份（转发 `context.identity`；`docs/02` §26）。"""
        return self.context.identity


@dataclass(frozen=True, slots=True)
class PipelineGate:
    """第 5–16 步的产物（`docs/02` §49–§74 的判定结果集合）。

    Attributes:
        request: 原请求。
        definition: 解析出的 `OperationDefinition`（`docs/02` §24）。
        resource: 解析出的资源（`docs/07` §9 第 7 步的**唯一**跨租户拦截点）；可为空。
        lock: 第 15 步抢到的锁句柄；`None` 表示**委派给 Worker**（`docs/02` §91）。
        decision: 幂等判定（`docs/02` §32 / §57）；无幂等键时为 `None`。
        capability: 能力判定（`docs/02` §43–§48）。
        replayed: 本次是否为**重放**（`docs/02` §86：直接返回既有响应）。
        replayed_response: 仅重放时有值 —— 首次成功执行的响应快照。
        facts: 供前置 / 后置条件求值的事实（三态，`docs/02` §32）。
        steps: **实际执行过**的步骤名，按冻结顺序排列（供验收逐条断言）。
        unprovisioned_schemas: 未配备（未登记）的 Schema id（见模块裁决 2）。
    """

    request: PipelineRequest
    definition: OperationDefinition
    resource: ResolvedResource | None = None
    lock: LockHandle | None = None
    decision: IdempotencyDecision | None = None
    capability: CapabilityDecision | None = None
    replayed: bool = False
    replayed_response: Mapping[str, Any] | None = None
    facts: ExecutionFacts = ExecutionFacts()
    steps: tuple[str, ...] = ()
    unprovisioned_schemas: tuple[str, ...] = ()

    @property
    def locked_here(self) -> bool:
        """锁是否由**本管线**持有（而非委派给 Worker；见模块裁决 1）。"""
        return self.lock is not None

    def lock_owner(self) -> str:
        """锁的持有者标识（委派时为 `""`；`docs/02` §91）。"""
        return "" if self.lock is None else self.lock.owner_id


# ===== 审计动作解析（`docs/02` §8.3 的动作清单）=====

AUDIT_ACTION_FAMILIES: Final[Mapping[str, str]] = {
    "BUILD": "MODEL.CREATE",
    "MODEL.NODE.CREATE": "MODEL.CREATE",
    "MODEL.ELEMENT.CREATE": "MODEL.CREATE",
    "MODEL.NODE.UPDATE": "MODEL.UPDATE",
    "MODEL.ELEMENT.UPDATE": "MODEL.UPDATE",
    "MODEL.MATERIAL.ASSIGN": "MODEL.UPDATE",
    "MODEL.SECTION.ASSIGN": "MODEL.UPDATE",
    "MODEL.BOUNDARY.ASSIGN": "MODEL.UPDATE",
    "MODEL.LOAD.ASSIGN": "MODEL.UPDATE",
    "MODEL.NODE.DELETE": "MODEL.DELETE",
    "MODEL.ELEMENT.DELETE": "MODEL.DELETE",
    "ANALYSIS": "ANALYSIS.RUN",
    "DESIGN": "DESIGN.RUN",
}
"""Operation → `docs/02` §8.3 动作名的**推导表**（`docs/02` §8.3 未给出映射，故本表是推导项）。

键是 Operation 名或它的**首个点段**（`BUILD.*` / `ANALYSIS.*` / `DESIGN.*` 整族归一到
一个动作）；未命中时 `audit_action_for` 原样返回 Operation 名 —— `audit_records.action`
是 `String(200)` 的自由文本，而 `docs/02` §8.3 的 16 个动作是**必须记录**的最小集合，
不是封闭枚举。因此「未命中的 Operation 用自己的名字入审计」既不遗漏也不臆造。
"""


def audit_action_for(operation: str) -> str:
    """把 Operation 名解析成审计动作名（见 `AUDIT_ACTION_FAMILIES`）。

    Args:
        operation: 规范化 Operation 名（如 `BUILD.COLUMN`）。

    Returns:
        精确命中 → 该动作；否则按首个点段命中 → 该族动作；否则**原样返回** `operation`
        （绝不臆造一个不存在的动作名）。
    """
    if operation in AUDIT_ACTION_FAMILIES:
        return AUDIT_ACTION_FAMILIES[operation]
    family = operation.split(".", 1)[0]
    return AUDIT_ACTION_FAMILIES.get(family, operation)


def quota_refusal_details(decision: object) -> dict[str, Any]:
    """把配额决策组装成 `STRUCTAI-5000` 的 `details`（见模块裁决 5）。

    Args:
        decision: `QuotaGate.consume_api_request` 的返回对象。

    Returns:
        `{"stage": "quota", "metric": ..., "dimension": ..., "limit": ..., "used": ...,
        "reason": ...}`；缺失的属性按 `None` / `0` 如实记录（**不**编造值）。

    Raises:
        InternalError: `STRUCTAI-7000` —— 决策对象**没有** `allowed` 属性
            （装配错误；静默放行会让配额形同虚设）。
    """
    if not hasattr(decision, DEFAULT_QUOTA_ALLOWED_ATTRIBUTE):
        raise InternalError(
            "Quota decision does not expose an `allowed` flag",
            details={"stage": PIPELINE_STAGE, "reason": "invalid_quota_decision"},
        )
    return {
        "stage": "quota",
        "metric": getattr(decision, "metric", None),
        "dimension": getattr(decision, "dimension", None),
        "limit": getattr(decision, "limit", 0),
        "used": getattr(decision, "used", 0),
        "reason": getattr(decision, "reason", ""),
    }


def quota_allowed(decision: object) -> bool:
    """配额决策是否放行（缺 `allowed` 属性 → `STRUCTAI-7000`；见模块裁决 5）。"""
    if not hasattr(decision, DEFAULT_QUOTA_ALLOWED_ATTRIBUTE):
        quota_refusal_details(decision)
    return bool(getattr(decision, DEFAULT_QUOTA_ALLOWED_ATTRIBUTE))


# ===== 管线本体 =====


class ExecutionPipeline:
    """26 步管线的**闸门链与结果链**编排（`docs/07` §9；`docs/02` §49–§74 / §90）。

    ⚠️ 本类**只**编排；每一步的判定语义都在各自的步骤服务里（`docs/02` §91：
    「各步骤由独立服务承担」）。持久化经 Domain 契约注入，事务边界归调用方的
    `UnitOfWork`（`docs/02` §16）—— 本类**从不** `commit` / `rollback`。

    Attributes:
        operations: 运行时 Operation Registry（P08；`docs/02` §28）。
        schema: `SchemaEngine`（P09；`docs/02` §13 / §16）。
        engineering: `EngineeringValidator`（P14–P18；`docs/02` §18–§22）。
        preconditions: 前置条件求值器（`docs/02` §32；三态语义）。
        postconditions: 后置条件求值器（同上）。
        permissions: 有效权限服务（P10–P13；`docs/07` §8.2）。
        confirmation: 确认闸门（P14–P18；`docs/07` §8.4）。
        idempotency: 幂等服务（P21；`docs/07` §10.3）。
        resolver: 资源解析器（P14–P18；`docs/07` §9 第 7 步）。
        locks: 进程内锁管理器（P14–P18；`docs/02` §36–§42）。
        lock_policy: 锁策略（`docs/02` §74）。
        capabilities: 能力解析器（P14–P18 / P19–P20；`docs/02` §43–§48）。
        quota: 配额闸门（`docs/02` §36 / §60；见模块裁决 5）。
        normalizer: 可选的结果规范化函数（`docs/02` §33 / §89 的规范化**信封**）。
    """

    def __init__(
        self,
        *,
        operations: OperationRegistry,
        schema: SchemaEngine,
        engineering: EngineeringValidator,
        preconditions: PreconditionEvaluator,
        postconditions: PostconditionEvaluator,
        permissions: EffectivePermissionService,
        confirmation: ConfirmationGuard,
        idempotency: IdempotencyService,
        resolver: ResourceResolver,
        locks: ResourceLockManager,
        lock_policy: LockPolicy,
        capabilities: CapabilityResolver,
        quota: QuotaGate,
        normalizer: Any = None,
    ) -> None:
        """绑定全部步骤服务（**全部**由调用方注入；本类不自行构造任何依赖）。"""
        self._operations = operations
        self._schema = schema
        self._engineering = engineering
        self._preconditions = preconditions
        self._postconditions = postconditions
        self._permissions = permissions
        self._confirmation = confirmation
        self._idempotency = idempotency
        self._resolver = resolver
        self._locks = locks
        self._lock_policy = lock_policy
        self._capabilities = capabilities
        self._quota = quota
        self._normalizer = normalizer

    # ===== 只读视图（供容器 / 验收断言）=====

    @property
    def operations(self) -> OperationRegistry:
        """被绑定的 Operation Registry（只读用途；Worker 路径需要它解析定义）。"""
        return self._operations

    @property
    def locks(self) -> ResourceLockManager:
        """被绑定的锁管理器（只读用途）。"""
        return self._locks

    @property
    def idempotency(self) -> IdempotencyService:
        """被绑定的幂等服务（只读用途）。"""
        return self._idempotency

    # ===== 第 5–16 步：闸门链 =====

    async def gate(
        self,
        request: PipelineRequest,
        *,
        acquire_lock: bool = False,
    ) -> PipelineGate:
        """执行第 5–16 步（`docs/07` §9 的冻结顺序），返回闸门产物。

        Args:
            request: 管线请求（`docs/02` §27 / §33）。
            acquire_lock: 第 15 步是否**由本管线**抢锁（见模块裁决 1）。
                走 Task Engine 的路径一律 `False`（锁由 Worker 在取到任务后抢，
                `docs/02` §91）；Dry Run 与无 Task 的直接调用传 `True`。

        Returns:
            `PipelineGate`；`replayed is True` 时调用方**必须**直接返回
            `replayed_response`，**不得**执行 Adapter（`docs/02` §86）。

        Raises:
            ProtocolError: `STRUCTAI-1000` —— 未知 Tool / 未知 Operation /
                Tool 与 Operation 不匹配（`docs/02` §82）。
            TenantAccessDeniedError: `STRUCTAI-4200` —— 第 7 步的跨租户拦截。
            SchemaValidationError: `STRUCTAI-1100` —— 第 8 步。
            EngineeringValidationError: `STRUCTAI-1200` —— 第 9 / 10 步。
            PermissionDeniedError: `STRUCTAI-4000` —— 第 11 步。
            TaskError: `STRUCTAI-5000` —— 第 12 步配额超限。
            ConfirmationRequiredError: `STRUCTAI-4100` —— 第 13 步。
            ConcurrencyConflictError: `STRUCTAI-1300` —— 第 14 步幂等冲突。
            ResourceLockedError: `STRUCTAI-6100` —— 第 15 步抢锁失败。
            CapabilityError: `STRUCTAI-3000` —— 第 16 步能力不足 / 无法判定。
            InternalError: `STRUCTAI-7000` —— 装配错误（如配额决策形状非法）。
        """
        steps: list[str] = []

        # ---- 第 5 步：Resolve Tool（`docs/02` §82 的 Tool Mismatch Test）----
        definition = await self._resolve_operation(request)
        steps.append("Resolve Tool")

        # ---- 第 6 步：Resolve Operation（与第 5 步同一次解析，见 `_resolve_operation`）----
        steps.append("Resolve Operation")

        # ---- 第 7 步：Resolve Resource（**唯一**跨租户拦截点，`docs/07` §9）----
        resource = await self._resolver.resolve(request.context)
        steps.append("Resolve Resource")

        # ---- 第 8 步：Schema Validation ----
        unprovisioned = self._validate_schema(definition, request.parameters)
        steps.append("Schema Validation")

        # ---- 第 9 步：Engineering Validation ----
        await self._engineering.validate(definition.name, request.parameters, request.context)
        steps.append("Engineering Validation")

        # ---- 第 10 步：Preconditions（三态；见模块裁决 3）----
        facts = ExecutionFacts(resolved_resource=resource)
        await self._preconditions.require(definition, facts)
        steps.append("Preconditions")

        # ---- 第 11 步：Effective Permission ----
        await self._require_permissions(request, definition, resource)
        steps.append("Effective Permission")

        # ---- 第 12 步：Quota / Rate Limit（见模块裁决 5）----
        await self._enforce_quota(request)
        steps.append("Quota / Rate Limit")

        # ---- 第 13 步：Confirmation（**必须**先于 Task 创建，`docs/02` §92）----
        resource_id = None if resource is None else resource.resource_id
        self._confirmation.require(
            request.identity,
            definition,
            request.confirmation_token,
            resource_id=resource_id,
        )
        steps.append("Confirmation")

        # ---- 第 14 步：Idempotency（**先于** Lock，`docs/07` §9）----
        decision = await self._begin_idempotency(request)
        steps.append("Idempotency")
        if decision is not None and decision.replayed:
            # `docs/02` §86：重放**直接返回**既有响应 —— 不抢锁、不执行 Adapter、不重发审计。
            return PipelineGate(
                request=request,
                definition=definition,
                resource=resource,
                decision=decision,
                replayed=True,
                replayed_response=decision.response,
                facts=facts,
                steps=tuple(steps),
                unprovisioned_schemas=unprovisioned,
            )

        # ---- 第 15 步：Concurrency / Resource Lock（见模块裁决 1）----
        lock = await self._acquire_lock(request, definition, resource) if acquire_lock else None
        steps.append("Concurrency / Resource Lock")

        # ---- 第 16 步：Capability Check ----
        capability = await self._check_capability(request, definition)
        steps.append("Capability Check")

        return PipelineGate(
            request=request,
            definition=definition,
            resource=resource,
            lock=lock,
            decision=decision,
            capability=capability,
            facts=facts,
            steps=tuple(steps),
            unprovisioned_schemas=unprovisioned,
        )

    # ===== 第 19 / 20 / 21 步 =====

    def normalize(
        self,
        definition: OperationDefinition,
        raw: Mapping[str, Any] | object,
    ) -> Mapping[str, Any]:
        """第 19 步：结果规范化（`docs/02` §33 / §89）。

        Adapter 已经做过**原生 → 规范化**的字段映射（P19–P20 的 `execute_normalized`；
        `docs/02` §89），故本步只保证结果是**规范化映射**：非映射一律
        `STRUCTAI-6000`（`docs/02` §32「返回规范化结果」），可选的 `normalizer`
        只用于再套一层规范化**信封**（`docs/02` §90 的 `data` / `pagination`）。

        Args:
            definition: 已解析的 Operation 定义（Worker 路径由调用方解析）。
            raw: Adapter 的返回（`docs/02` §89 的规范化结果）。

        Returns:
            规范化映射。

        Raises:
            AdapterError: `STRUCTAI-6000` —— 返回不是映射（`docs/02` §32）。
            InternalError: `STRUCTAI-7000` —— 注入的 `normalizer` 返回了非映射。
        """
        if not isinstance(raw, Mapping):
            raise AdapterError(
                "Adapter result is not a canonical mapping",
                details={"stage": PIPELINE_STAGE, "reason": "non_canonical_result"},
            )
        if self._normalizer is None:
            return dict(raw)
        normalized: object = self._normalizer(definition.name, dict(raw))
        if not isinstance(normalized, Mapping):
            raise InternalError(
                "Result normalizer did not return a canonical mapping",
                details={"stage": PIPELINE_STAGE, "reason": "invalid_normalized_result"},
            )
        return dict(normalized)

    async def postconditions(
        self,
        definition: OperationDefinition,
        *,
        resource: ResolvedResource | None = None,
        result_available: bool = False,
    ) -> PostconditionReport:
        """第 20 步：后置条件（**先于**第 21 步 `Release Lock`，`docs/07` §9）。

        ⚠️ `task_status` 一律 `None`（未验证，见模块裁决 4）：第 20 步发生在
        `TaskWorker._mark_completed` **之前**，把 `COMPLETED` 写进事实就是伪造。
        `result_available` 如实反映 Adapter 是否返回了结果。
        """
        facts = ExecutionFacts(
            resolved_resource=resource,
            supported_capabilities=None,
            task_status=None,
            result_available=result_available,
        )
        return await self._postconditions.require(definition, facts)

    async def release(self, gate: PipelineGate) -> bool:
        """第 21 步：释放锁（`docs/07` §9）。

        Returns:
            `True` 表示本管线释放了自己持有的锁；`False` 表示**委派**（锁由 Worker
            在取到任务后抢、在 `finally` 里释放，`docs/02` §91）—— 委派时本方法是
            **无操作**，绝不触碰别人的锁。
        """
        if gate.lock is None:
            return False
        return await self._locks.release(gate.lock)

    # ===== 各步实现 =====

    async def _resolve_operation(self, request: PipelineRequest) -> OperationDefinition:
        """第 5–6 步：解析 Tool 与 Operation，并校验二者一致（`docs/02` §82）。

        Raises:
            ProtocolError: `STRUCTAI-1000` —— 未知 Tool / 未知 Operation /
                Tool 与 Operation 不匹配（`docs/02` §82 的 `Tool Mismatch Test`）。
        """
        known_tools = {definition.tool for definition in await self._operations.list()}
        if request.tool not in known_tools:
            raise ProtocolError(
                "Unknown tool",
                details={"stage": PIPELINE_STAGE, "reason": "unknown_tool"},
            )
        definition = await self._operations.get(request.operation)
        if definition is None:
            raise ProtocolError(
                "Unknown operation",
                details={"stage": PIPELINE_STAGE, "reason": "unknown_operation"},
            )
        if definition.tool != request.tool:
            raise ProtocolError(
                "Operation does not belong to the requested tool",
                details={"stage": PIPELINE_STAGE, "reason": "tool_mismatch"},
            )
        return definition

    def _validate_schema(
        self,
        definition: OperationDefinition,
        parameters: Mapping[str, Any],
    ) -> tuple[str, ...]:
        """第 8 步：Schema 校验（见模块裁决 2）。

        Returns:
            未配备（未登记）的 Schema id 元组 —— 结构合法性的**缺失**是可观测的事实，
            而不是静默的绿灯（`docs/07` §14.4：不允许「带病继续」）。
        """
        try:
            self._schema.validate(definition.input_schema, dict(parameters))
        except NotFoundError:
            return (definition.input_schema,)
        return ()

    async def _require_permissions(
        self,
        request: PipelineRequest,
        definition: OperationDefinition,
        resource: ResolvedResource | None,
    ) -> None:
        """第 11 步：逐条校验 `required_permissions`（`docs/07` §8.2）。

        ⚠️ 一次**全部**校验（不短路）：`docs/02` §30 的 `Permission` 步骤要求
        「有效权限不足 → 拒绝」，而逐条校验让 `details.permission` 精确指向缺失的那一条。
        """
        resource_type = None if resource is None else resource.resource_type
        resource_id = None if resource is None else resource.resource_id
        project_id = None if resource is None else resource.project_id
        for permission in definition.required_permissions:
            await self._permissions.require(
                request.identity,
                permission,
                resource_type,
                resource_id,
                project_id=project_id,
            )

    async def _enforce_quota(self, request: PipelineRequest) -> None:
        """第 12 步：配额 / 限流（见模块裁决 5）。

        Raises:
            TaskError: `STRUCTAI-5000` —— 超限（`details.stage = "quota"`，
                `retryable = True`，与「Queue Full → `STRUCTAI-5000`」同族）。
            InternalError: `STRUCTAI-7000` —— 决策对象形状非法（装配错误）。
        """
        instance_id = request.context.software.instance_id
        decision = await self._quota.consume_api_request(
            tenant_id=str(request.identity.tenant_id),
            user_id=str(request.identity.user_id),
            instance_id=None if instance_id is None else str(instance_id),
        )
        if not quota_allowed(decision):
            raise TaskError(
                "Quota exceeded",
                details=quota_refusal_details(decision),
            )

    async def _begin_idempotency(self, request: PipelineRequest) -> IdempotencyDecision | None:
        """第 14 步：幂等抢占 / 重放（`docs/02` §32 / §57；见模块裁决 7）。

        Returns:
            `None` 表示请求**没有**幂等键（该步无判定，`docs/02` §57 的「有 key 才查」）；
            否则为 `IdempotencyDecision`（`RESERVED` 继续执行 / `REPLAY` 直接返回）。
        """
        if not request.idempotency_key:
            return None
        request_hash = self._idempotency.hash_request(request)
        return await self._idempotency.begin(
            tenant_id=str(request.identity.tenant_id),
            idempotency_key=request.idempotency_key,
            request_hash=request_hash,
        )

    async def _acquire_lock(
        self,
        request: PipelineRequest,
        definition: OperationDefinition,
        resource: ResolvedResource | None,
    ) -> LockHandle | None:
        """第 15 步：抢资源锁（仅 `acquire_lock=True` 时调用；见模块裁决 1）。

        锁的对象：解析出的资源优先（最具体），否则退到上下文里的项目；
        两者都没有 → **不**加锁（没有可加锁的对象，`docs/02` §37 的资源键口径）。
        """
        key = self._lock_key(request, resource)
        if key is None:
            return None
        owner_id = str(request.identity.user_id)
        lock = self._lock_policy.resolve(definition, key, owner_id=owner_id)
        return await self._locks.acquire_lock(lock)

    def _lock_key(
        self,
        request: PipelineRequest,
        resource: ResolvedResource | None,
    ) -> ResourceKey | None:
        """算出加锁的资源键（`docs/02` §37 / §74）。"""
        if resource is not None:
            return resource.as_key()
        project_id = request.context.project.project_id
        if project_id is None:
            return None
        return ResourceKey(resource_type=str(ResourceType.PROJECT), resource_id=str(project_id))

    async def _check_capability(
        self,
        request: PipelineRequest,
        definition: OperationDefinition,
    ) -> CapabilityDecision | None:
        """第 16 步：能力检查（`docs/02` §43–§48）。

        ⚠️ 无能力要求的 Operation **不**进入能力判定：`docs/02` §34 的能力来源是
        「实例 + 版本 + 能力码」，没有能力码就没有可判定的问题，强行解析软件实例
        会把「不需要软件的操作」误判为 `STRUCTAI-3000`。判定因此**只**发生在
        `required_capabilities` 非空时（此时「说不清」一律拒绝，`docs/07` §16 R30）。
        """
        if not definition.required_capabilities:
            return None
        return await self._capabilities.check(request.context, definition)
