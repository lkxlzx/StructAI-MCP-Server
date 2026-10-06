"""Application · Task —— 任务引擎包（`docs/07` §3.3 冻结结构；§10.1 / §10.2；§12 P22–P28）。
对应 `docs/02` §7–§20 / §34–§54 / §75–§91。

本包就是 `docs/07` §3.3 冻结结构里的 `app/application/task/`（10 个文件），
与 `docs/02` §46 给出的目录**逐项一致**：

- `state_machine.py` —— 12 态与冻结转移表（**唯一**实现点）：
  `docs/07` §10.1；`docs/02` §7 / §8 / §47 / §76。
- `queue.py` —— 进程内优先级队列（`priority` + `created_at`）：
  `docs/02` §11–§17 / §38 / §49 / §56。
- `dag.py` —— DAG 校验 / 拓扑序 / 步骤调度：`docs/02` §19 / §46–§51 / §82 / §83。
- `lease.py` —— 租约抢占 / 续租 / 释放 / 过期判定：`docs/02` §18 / §34–§38 / §40 / §80。
- `progress.py` —— 进度**唯一**写入口（0–100，Adapter 进度不可信）：
  `docs/02` §31–§33 / §44。
- `scheduler.py` —— 四级并发取最严格（global / tenant / user / software-instance）：
  `docs/02` §18 / §20 / §38 / §49。
- `cancellation.py` —— 取消请求 → `CANCEL_REQUESTED` → Adapter → `CANCELLED`：
  `docs/02` §28–§30 / §43 / §53 / §79。
- `recovery.py` —— 启动恢复（`REQUEUE` / `RESUME` / `FAIL`）：
  `docs/02` §18 / §40–§45 / §52 / §66 / §81。
- `engine.py` —— `TaskEngine`：**唯一**的 Task 创建点与编排入口：
  `docs/02` §9 / §15 / §47 / §48 / §54 / §77 / §78 / §88 / §90。
- `worker.py` —— `TaskWorker`：租约 → 准入 → 锁 → 执行 → 落库 → 释放：
  `docs/02` §15 / §39–§41 / §50 / §65 / §77 / §78 / §91。

红线（`docs/07` §14）：
- 本包**只**依赖标准库与 `app.domain`（以及**同层**的 `app.application.execution` /
  `app.application.resource`）；**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，
  **不**依赖 `app.infrastructure`（持久化一律经 Domain 契约 `TaskStore` 注入）；
- **状态机集中实现**（`docs/07` §10.1）：12 态与转移只定义在 `state_machine.py`，
  其它模块**不得**再写一份转移表；
- **进度只有一个写入口**（`docs/07` §10.2）：`tasks.progress` 只能经 `progress.py` 写；
- **`engine.py` 是唯一的 Task 创建点**（`docs/02` §90），且**不得** import
  `app.application.execution.idempotency`（幂等是它的**上游**）；
- 恢复**绝不**把任务置 `COMPLETED`；取消**绝不**杀 Python 进程（`docs/07` §14.4）。
"""

from __future__ import annotations

from app.application.task.cancellation import (
    CANCEL_UNSUPPORTED_MESSAGE,
    CANCELLATION_STAGE,
    FALLBACK_CANCELLATION_CODE,
    AdapterCancellation,
    CancellationOutcome,
    CancellationService,
)
from app.application.task.dag import (
    DAG_STAGE,
    DAG_VALIDATION_REASONS,
    TERMINAL_STEP_STATUSES,
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
from app.application.task.engine import (
    DEFAULT_MAX_RETRIES,
    RETRYABLE_STATUSES,
    SYNC_WORKER_ID,
    TASK_CREATE_ORDER,
    TASK_ENGINE_STAGE,
    TaskEngine,
    TaskSubmission,
    TaskView,
)
from app.application.task.lease import (
    DEFAULT_HEARTBEAT_SECONDS,
    DEFAULT_LEASE_SECONDS,
    LEASE_STAGE,
    TASK_LEASE_MESSAGE,
    LeaseService,
    TaskLeaseError,
    heartbeat_is_within_lease,
)
from app.application.task.progress import (
    PROGRESS_MAX,
    PROGRESS_MIN,
    PROGRESS_STAGE,
    PROGRESS_UNTRUSTED_REASONS,
    ProgressReporter,
    ProgressUpdate,
    sanitize_progress,
)
from app.application.task.queue import (
    DEFAULT_TASK_PRIORITY,
    PRIORITY_LEVELS,
    QUEUE_FULL_MESSAGE,
    QueueItem,
    TaskQueue,
    priority_value,
)
from app.application.task.recovery import (
    POLICY_TO_ACTION,
    RECOVERY_ENTRY_STATUSES,
    RECOVERY_STAGE,
    UNKNOWN_POLICY_FALLBACK,
    RecoveryAction,
    RecoveryOutcome,
    RecoveryService,
)
from app.application.task.scheduler import (
    CONCURRENCY_LEVELS,
    DEFAULT_CONCURRENCY_LIMITS,
    DEFAULT_INSTANCE_CONCURRENCY,
    DEFAULT_TENANT_CONCURRENCY,
    DEFAULT_USER_CONCURRENCY,
    SCHEDULER_STAGE,
    ConcurrencyLimits,
    ConcurrencyRequest,
    DefaultInstanceConcurrencyPolicy,
    InstanceConcurrencyPolicySource,
    Scheduler,
    SchedulerDecision,
)
from app.application.task.state_machine import (
    ALLOWED_TRANSITIONS,
    STATE_MACHINE_STAGE,
    TASK_STATE_SEQUENCE,
    TASK_STATUSES,
    TERMINAL_STATUSES,
    TaskStateError,
    TaskStateMachine,
    can_transition,
    transition,
)
from app.application.task.worker import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_TASK_TIMEOUT_SECONDS,
    WORKER_STAGE,
    TaskExecutor,
    TaskWorker,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "AdapterCancellation",
    "CANCELLATION_STAGE",
    "CANCEL_UNSUPPORTED_MESSAGE",
    "CONCURRENCY_LEVELS",
    "CancellationOutcome",
    "CancellationService",
    "ConcurrencyLimits",
    "ConcurrencyRequest",
    "DAG_STAGE",
    "DAG_VALIDATION_REASONS",
    "DEFAULT_CONCURRENCY_LIMITS",
    "DEFAULT_HEARTBEAT_SECONDS",
    "DEFAULT_INSTANCE_CONCURRENCY",
    "DEFAULT_LEASE_SECONDS",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "DEFAULT_TASK_PRIORITY",
    "DEFAULT_TASK_TIMEOUT_SECONDS",
    "DEFAULT_TENANT_CONCURRENCY",
    "DEFAULT_USER_CONCURRENCY",
    "DagPlan",
    "DefaultInstanceConcurrencyPolicy",
    "FALLBACK_CANCELLATION_CODE",
    "InstanceConcurrencyPolicySource",
    "LEASE_STAGE",
    "LeaseService",
    "POLICY_TO_ACTION",
    "PRIORITY_LEVELS",
    "PROGRESS_MAX",
    "PROGRESS_MIN",
    "PROGRESS_STAGE",
    "PROGRESS_UNTRUSTED_REASONS",
    "ProgressReporter",
    "ProgressUpdate",
    "QUEUE_FULL_MESSAGE",
    "QueueItem",
    "RECOVERY_ENTRY_STATUSES",
    "RECOVERY_STAGE",
    "RETRYABLE_STATUSES",
    "RecoveryAction",
    "RecoveryOutcome",
    "RecoveryService",
    "SCHEDULER_STAGE",
    "STATE_MACHINE_STAGE",
    "SYNC_WORKER_ID",
    "Scheduler",
    "SchedulerDecision",
    "TASK_CREATE_ORDER",
    "TASK_ENGINE_STAGE",
    "TASK_LEASE_MESSAGE",
    "TASK_STATE_SEQUENCE",
    "TASK_STATUSES",
    "TERMINAL_STATUSES",
    "TERMINAL_STEP_STATUSES",
    "TaskEngine",
    "TaskExecutor",
    "TaskGraph",
    "TaskLeaseError",
    "TaskQueue",
    "TaskStateError",
    "TaskStateMachine",
    "TaskStep",
    "TaskSubmission",
    "TaskView",
    "TaskWorker",
    "UNKNOWN_POLICY_FALLBACK",
    "WORKER_STAGE",
    "blocked_steps",
    "can_transition",
    "graph_from_drafts",
    "heartbeat_is_within_lease",
    "priority_value",
    "ready_steps",
    "sanitize_progress",
    "step_plan",
    "topological_order",
    "transition",
    "validate_dag",
]
