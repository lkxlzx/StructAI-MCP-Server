"""P22–P28 验收测试：Task Engine。

验收点（与续接提示词的 ①–⑫ 一一对应）：

① 状态机（`docs/07` §10.1；`docs/02` §7 / §8 / §76）：12 态**集中实现**在
   `state_machine.py`，不得散落；12×12 = **144 格**逐格断言允许与禁止；非法转移**必须拒绝**
   （不得静默忽略 / 不得自动纠正）；两个终态无出边；`RECOVERING` 绝不直达 `COMPLETED`。
② Lease（`docs/02` §34–§38 / §80）：`lease_owner` / `lease_until` / `heartbeat_at`
   **原子更新**（**单条**条件 `UPDATE`，**无**前置 `SELECT`）；两个 Worker 抢同一任务只允许
   一个成功；续租；非持有者不得续租；过期可回收；`heartbeat < lease / 2`。
③ Recovery（`docs/02` §42 / §45 / §52 / §66 / §81；`docs/07` §14.4）：四条入口状态 → 查 lease
   → **有效则等待 / 对账（零状态变更）**，否则 `RECOVERING` → `REQUEUE` / `RESUME` / `FAIL`；
   两个词表之间的**唯一**转换点；**禁止**把恢复中的 Task 置 `COMPLETED`。
④ DAG（`docs/02` §46–§51 / §82 / §83）：`depends_on`；**循环依赖必须在提交前拒绝**
   （SQL 级钩子证明零 `INSERT`）；拓扑序；并行层；前置失败 → `SKIPPED`。
⑤ 优先级与队列（`docs/02` §12–§17）：`priority` + `created_at` 出队（同优先级 FIFO）；
   有界队列 → `STRUCTAI-5000`；`shutdown()` 不丢数据、不杀进程。
⑥ 并发（`docs/02` §18 / §20）：四级（global / tenant / user / software-instance）取**最严格**；
   实例策略 `SERIAL`（默认）/ `LIMITED` / `PARALLEL`；`Scheduler` **零 SQL**。
⑦ Cancellation（`docs/02` §30 / §43 / §53 / §79）：`cancel()` → `CANCEL_REQUESTED` →
   `Adapter.cancel()` → `CANCELLED`；不支持时**保持** `CANCEL_REQUESTED`；**不得杀 Python
   进程**、**不得伪造 `CANCELLED`**。
⑧ Progress（`docs/02` §31–§33）：唯一来源是 Task Engine；范围 0–100；**Adapter 进度不可信**。
⑨ 顺序（`docs/02` §90 / §91）：`ExecutionService → Idempotency → Task Create`；26 步流水线
   不变；`app/application/task/**` **不** import 幂等模块；`engine.py` 是**唯一**创建点。
⑩ 回归：既有 **329 项 pytest 不得回退**（由整轮 `pytest -q` 覆盖；本文件只补
   `app.main` 两条 + P04 建表 / `SELECT 1` + P02 覆盖行为 + `BATCH_ID`）。
⑪ 质量：`ruff` / `mypy` 覆盖；本文件额外断言依赖清单**未扩**、容器形状**未变**、
   Application 层**不依赖** `app.infrastructure`、新模块**不得 `commit`**。
⑫ 红线：`app/` 内厂商名 0 处、`app/domain/` 无 SQLAlchemy、不新增 `STRUCTAI-xxxx` 码、
   **绝不记录 secret**、Settings 字段全部登记于 `.env.example`、**未改表**。

⚠️ 本文件里的「规范原文副本」（12 态与转移表 / 四级并发 / 优先级 / 恢复策略与动作 /
20 码清单 / 26 步顺序 / 两张表的列集合）**故意不**从被测模块取：若断言只与被测常量比较，
「常量被改错」与「实现被改错」会一起通过（同源循环）。
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.resource.lock_manager import ResourceLockManager
from app.application.resource.lock_policy import LockPolicy
from app.application.task import (
    ALLOWED_TRANSITIONS,
    CONCURRENCY_LEVELS,
    DAG_VALIDATION_REASONS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TASK_PRIORITY,
    POLICY_TO_ACTION,
    PRIORITY_LEVELS,
    PROGRESS_UNTRUSTED_REASONS,
    RECOVERY_ENTRY_STATUSES,
    RETRYABLE_STATUSES,
    TASK_CREATE_ORDER,
    TASK_STATE_SEQUENCE,
    TERMINAL_STATUSES,
    TERMINAL_STEP_STATUSES,
    CancellationService,
    ConcurrencyLimits,
    ConcurrencyRequest,
    DagPlan,
    DefaultInstanceConcurrencyPolicy,
    LeaseService,
    ProgressReporter,
    RecoveryAction,
    RecoveryService,
    Scheduler,
    TaskEngine,
    TaskGraph,
    TaskLeaseError,
    TaskQueue,
    TaskStateError,
    TaskStateMachine,
    TaskStep,
    TaskSubmission,
    TaskWorker,
    blocked_steps,
    can_transition,
    graph_from_drafts,
    heartbeat_is_within_lease,
    priority_value,
    ready_steps,
    sanitize_progress,
    step_plan,
    topological_order,
    transition,
    validate_dag,
)
from app.config.settings import Settings
from app.container import BATCH_ID, AppContainer
from app.domain.enums import (
    ExecutionMode,
    RiskLevel,
    SoftwareInstanceConcurrencyPolicy,
    TaskPriority,
    TaskStatus,
    TaskStepStatus,
)
from app.domain.errors import (
    AdapterError,
    ConcurrencyConflictError,
    EngineeringValidationError,
    InternalError,
    StructAIError,
    TaskError,
    TaskRecoveryError,
)
from app.domain.events import TaskProgress
from app.domain.protocols import (
    OperationDefinition,
    TaskDraft,
    TaskRecord,
    TaskStepDraft,
    TaskStepRecord,
)
from app.infrastructure.database import Base, create_engine, create_session_factory
from app.infrastructure.database.models.task import TaskORM, TaskStepORM
from app.infrastructure.database.repositories import (
    TaskStoreRepository,
    build_task_store,
)
from app.infrastructure.database.seed import ADMIN_PASSWORD_ENV, seed
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.infrastructure.registry.operation_registry import OperationRegistry

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
TASK_DIR = APP_DIR / "application" / "task"
REPOSITORIES_DIR = APP_DIR / "infrastructure" / "database" / "repositories"

VENDOR_NAMES = ("MIDAS", "CSI", "ANSYS")
"""`docs/07` §14.2：`app/` 内禁止出现的厂商名。"""

TEST_PASSWORD = "P22-Task-Engine-验收-口令-7c41"
"""测试用口令（非真实 secret，仅存在于测试进程内）。"""

TENANT_ID = "33333333-3333-4333-8333-333333333333"
"""本文件使用的租户标识（`docs/02` §11：Task 是 Tenant-owned）。"""

OTHER_TENANT_ID = "44444444-4444-4444-8444-444444444444"
"""第二个租户：用于证明任务读取**不跨租户**（`docs/02` §11 / §48）。"""

PROJECT_ID = "55555555-5555-4555-8555-555555555555"
"""本文件使用的项目标识（`docs/02` §91 的资源锁对象）。"""

INSTANCE_ID = "66666666-6666-4666-8666-666666666666"
"""本文件使用的软件实例标识（`docs/02` §20 的并发策略对象）。"""

SessionFactory = async_sessionmaker[AsyncSession]
"""会话工厂类型别名（`docs/02` §15）。"""


# ===== 规范原文副本（`docs/07` §10 / §11 / §3.1；`docs/02` §8 / §14 / §18 / §45 / §50 / §90）===

TASK_STATES_SPEC = (
    "CREATED",
    "VALIDATING",
    "QUEUED",
    "RUNNING",
    "PROCESSING",
    "COMPLETED",
    "FAILED",
    "CANCEL_REQUESTED",
    "CANCELLED",
    "TIMEOUT",
    "RETRYING",
    "RECOVERING",
)
"""`docs/07` §10.1 / `docs/02` §8：**12 态**的规范顺序（逐字抄写）。"""

ALLOWED_TRANSITIONS_SPEC: Mapping[str, frozenset[str]] = {
    "CREATED": frozenset({"VALIDATING", "CANCELLED"}),
    "VALIDATING": frozenset({"QUEUED", "FAILED", "CANCELLED"}),
    "QUEUED": frozenset({"RUNNING", "CANCELLED", "RECOVERING"}),
    "RUNNING": frozenset(
        {"PROCESSING", "COMPLETED", "FAILED", "CANCEL_REQUESTED", "TIMEOUT", "RECOVERING"}
    ),
    "PROCESSING": frozenset({"COMPLETED", "FAILED", "CANCEL_REQUESTED", "TIMEOUT", "RECOVERING"}),
    "COMPLETED": frozenset(),
    "FAILED": frozenset({"RETRYING"}),
    "CANCEL_REQUESTED": frozenset({"CANCELLED", "FAILED", "RECOVERING"}),
    "CANCELLED": frozenset(),
    "TIMEOUT": frozenset({"RETRYING", "FAILED", "RECOVERING"}),
    "RETRYING": frozenset({"QUEUED", "FAILED"}),
    "RECOVERING": frozenset({"QUEUED", "RUNNING", "FAILED"}),
}
"""`docs/02` §8 ∪ §7 的冻结转移表（12 键；逐格抄写，见 `docs/07` §16 R41）。"""

TERMINAL_STATES_SPEC = ("COMPLETED", "CANCELLED")
"""`docs/07` §10.1 / `docs/02` §7：**终态**（无出边）。"""

PRIORITY_LEVELS_SPEC: Mapping[str, int] = {
    "CRITICAL": 0,
    "HIGH": 10,
    "NORMAL": 50,
    "LOW": 100,
}
"""`docs/02` §14 的优先级建议映射（逐项抄写；数值越小优先级越高）。"""

PRIORITY_NAMES_SPEC = ("LOW", "NORMAL", "HIGH", "CRITICAL")
"""`docs/02` §17 的优先级枚举（`TaskPriority` 的声明顺序）。"""

INSTANCE_POLICIES_SPEC = ("SERIAL", "LIMITED", "PARALLEL")
"""`docs/02` §20 的软件实例并发策略（`SERIAL` 为默认）。"""

STEP_STATUSES_SPEC = ("PENDING", "READY", "RUNNING", "COMPLETED", "FAILED", "SKIPPED")
"""`docs/02` §50 的 DAG 步骤状态（逐项抄写）。"""

RECOVERY_POLICIES_SPEC = ("SAFE_RETRY", "STATE_RECONCILE", "MANUAL_REVIEW", "FAIL")
"""`docs/02` §45 的 `recovery_policy` 分类（逐项抄写）。"""

RECOVERY_ACTIONS_SPEC = ("REQUEUE", "RESUME", "FAIL")
"""`docs/02` §18 / §42 / §52 的**恢复动作**词表（逐项抄写）。"""

RECOVERY_ENTRY_STATUSES_SPEC = ("QUEUED", "RUNNING", "PROCESSING", "RECOVERING")
"""`docs/02` §52 / §66 / §18：启动恢复只扫描的四条入口状态（逐项抄写）。"""

CONCURRENCY_LEVELS_SPEC = ("global", "tenant", "user", "software-instance")
"""`docs/02` §18 的四级并发维度（逐项抄写）。"""

CONCURRENCY_EXAMPLE_SPEC = {"tenant": 10, "user": 4, "software-instance": 1}
"""`docs/02` §18 的示例值（`Tenant A = 10` / `User A = 4` / `CIVIL-01 = 1`）。"""

ERROR_CODES_SPEC = (
    "STRUCTAI-1000",
    "STRUCTAI-1100",
    "STRUCTAI-1200",
    "STRUCTAI-1300",
    "STRUCTAI-2000",
    "STRUCTAI-2100",
    "STRUCTAI-2200",
    "STRUCTAI-2300",
    "STRUCTAI-3000",
    "STRUCTAI-4000",
    "STRUCTAI-4100",
    "STRUCTAI-4200",
    "STRUCTAI-5000",
    "STRUCTAI-5100",
    "STRUCTAI-5200",
    "STRUCTAI-5300",
    "STRUCTAI-6000",
    "STRUCTAI-6100",
    "STRUCTAI-6200",
    "STRUCTAI-7000",
)
"""`docs/07` §11：**20 码**错误契约（逐字抄写；本批不得扩）。"""

PIPELINE_ORDER_SPEC = (
    "MCP Request",
    "Authenticate",
    "Build Server IdentityContext",
    "Build ExecutionContext",
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
    "Task / Transaction",
    "Adapter",
    "Result Normalization",
    "Postconditions",
    "Release Lock",
    "Persist Result",
    "Audit",
    "Trace",
    "Event",
    "MCP Response",
)
"""`docs/07` §9 的 **26 步**执行流水线（逐字抄写；本批不得改动）。"""

TASK_CREATE_ORDER_SPEC = ("ExecutionService", "Idempotency", "Task Create")
"""`docs/02` §90 的顺序（逐字抄写；**不得**反序）。"""

TASK_TABLE_COLUMNS_SPEC = (
    "id",
    "tenant_id",
    "project_id",
    "request_id",
    "trace_id",
    "tool",
    "operation",
    "status",
    "progress",
    "retry_count",
    "max_retries",
    "cancel_requested",
    "lease_owner",
    "lease_until",
    "heartbeat_at",
    "priority",
    "error_json",
    "result_json",
    "started_at",
    "completed_at",
    "created_at",
    "updated_at",
    "version",
)
"""`docs/07` §4.3 #19 的 `tasks` 列集合（`last_heartbeat` 落库为 `heartbeat_at`）。

⚠️ §4.3 #19 的摘要只列关键字段，而 §4.3 的通用规则要求「UUID 主键 + `created_at` +
`updated_at`」、可变资源带 `version`；本常量是**逐列**的完整副本，用于证明**未改表**。
"""

TASK_STEP_TABLE_COLUMNS_SPEC = (
    "id",
    "task_id",
    "step_key",
    "operation",
    "status",
    "parameters_json",
    "depends_on_json",
    "result_json",
    "error_json",
    "created_at",
    "updated_at",
)
"""`docs/07` §4.3 #20 的 `task_steps` 列集合（`depends_on` 落库为 `depends_on_json`）。"""

TWENTY_FOUR_TABLES_SPEC = (
    "tenants",
    "users",
    "roles",
    "permissions",
    "user_roles",
    "role_permissions",
    "sessions",
    "projects",
    "project_members",
    "software",
    "software_products",
    "software_versions",
    "software_instances",
    "models",
    "documents",
    "capabilities",
    "operations",
    "operation_capabilities",
    "tasks",
    "task_steps",
    "artifacts",
    "resource_locks",
    "idempotency_records",
    "audit_records",
)
"""`docs/07` §4.3 的 **24 张表**（逐字抄写；本批**不得改表**）。"""

CONTAINER_FIELDS_SPEC = (
    "settings",
    "runtime_config",
    "engine",
    "session_factory",
    "operation_registry",
    "execution_service",
    "started",
)
"""`docs/02` §33 的冻结容器形状（逐字段抄写；本批**不得**扩展）。"""

FROZEN_DEPENDENCIES = (
    "aiosqlite",
    "alembic",
    "argon2-cffi",
    "fastapi",
    "httpx",
    "jsonschema",
    "mcp",
    "pydantic",
    "pydantic-settings",
    "sqlalchemy",
    "structlog",
    "uvicorn",
)
"""`docs/07` §3.1 / §3.2 冻结的运行期依赖（本批不得引入新依赖）。"""

TASK_MODULES = (
    "state_machine.py",
    "queue.py",
    "dag.py",
    "lease.py",
    "progress.py",
    "scheduler.py",
    "cancellation.py",
    "recovery.py",
    "engine.py",
    "worker.py",
)
"""`docs/07` §3.3 冻结结构里的 `app/application/task/`（`docs/02` §46 的目录）。"""

TASK_PACKAGE_MODULES = (
    "app/application/task/lease.py",
    "app/application/task/progress.py",
    "app/application/task/scheduler.py",
    "app/application/task/cancellation.py",
    "app/application/task/recovery.py",
    "app/application/task/engine.py",
    "app/application/task/worker.py",
    "app/application/task/__init__.py",
    "app/infrastructure/database/repositories/task.py",
)
"""本批新增 / 追加的模块（用于「不得 commit / 不得依赖 infrastructure」的红线断言）。"""

FORBIDDEN_FRAMEWORK_ROOTS = ("sqlalchemy", "fastapi", "mcp", "httpx")
"""`docs/07` §14.1：`app/domain/` 与 Application 层不得依赖的框架 / SDK。"""

SECRET_MARKERS = ("password", "api_key", "api-key", "token", "private_key", "secret")
"""`docs/07` §14.3：不得出现在 `details` / 记录 / 库中的 secret 形态词。"""


# ===== 夹具与辅助 =====


@pytest.fixture
async def seeded_engine(
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncEngine:
    """`tests/conftest.py` 的临时库 ＋ 真实 Seed（`docs/02` §43–§46；P07）。

    ⚠️ `seed()` 需要 `STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD`（`docs/02` §44），
    故此处用 `monkeypatch` 注入测试口令（仅存在于测试进程内）。
    """
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    await seed(create_session_factory(engine))
    return engine


def _relative_path(relative: str) -> Path:
    """仓库内相对路径 → 绝对路径。"""
    return REPO_ROOT / relative


def _imported_modules(path: Path) -> set[str]:
    """文件里 `import` / `from … import` 的模块名（AST 级）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _commit_or_rollback_calls(path: Path) -> list[str]:
    """文件内 `.commit()` / `.rollback()` 调用的属性名（AST 级，忽略文档字符串）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"commit", "rollback"}
    ]


def _module_level_names(path: Path) -> set[str]:
    """文件**模块级**赋值 / 函数 / 类名（AST 级；用于「常量只在某处定义」的断言）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
    return names


def _recorded_statements(engine: AsyncEngine) -> list[str]:
    """录制引擎上执行过的 SQL 语句（验收用 SQL 级钩子）。"""
    statements: list[str] = []

    def _capture(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _capture)
    return statements


def _write_verbs(statements: Sequence[str]) -> list[str]:
    """语句里的写动词（INSERT / UPDATE / DELETE / REPLACE）。"""
    verbs: list[str] = []
    for statement in statements:
        head = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
        if head in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
            verbs.append(head)
    return verbs


def _table_verbs(statements: Sequence[str], table: str) -> list[str]:
    """只保留作用于指定表的语句的写动词（按表名过滤，**不**含 `task_steps` 等其它表）。"""
    verbs: list[str] = []
    for statement in statements:
        lowered = statement.lower()
        if f" {table} " not in lowered and f" {table}(" not in lowered:
            continue
        head = statement.lstrip().split(None, 1)[0].upper()
        verbs.append(head)
    return verbs


def _table_statements(statements: Sequence[str], table: str) -> list[str]:
    """作用于指定表的**全部**语句（含 `SELECT`），按执行顺序。"""
    return [
        statement
        for statement in statements
        if f" {table} " in statement.lower() or f" {table}(" in statement.lower()
    ]


def _run_main(database_url: str) -> subprocess.CompletedProcess[str]:
    """以指定库运行 `python -m app.main`（`docs/07` §12 P01 / P04 的回归入口）。"""
    environment = {**os.environ, "DATABASE_URL": database_url, "LOG_LEVEL": "INFO"}
    return subprocess.run(
        [sys.executable, "-m", "app.main"],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )


async def _provision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str = "p22_main.db",
) -> str:
    """建表 + Seed 一个临时库，返回其 `database_url`。"""
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    database_url = f"sqlite+aiosqlite:///{(tmp_path / name).as_posix()}"
    engine = create_engine(database_url, echo=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await seed(create_session_factory(engine))
    finally:
        await engine.dispose()
    return database_url


def _draft(**overrides: Any) -> TaskDraft:
    """构造一个 `TaskDraft`（`docs/02` §9）。"""
    values: dict[str, Any] = {
        "tenant_id": TENANT_ID,
        "request_id": f"req_{uuid4().hex}",
        "trace_id": f"trace_{uuid4().hex}",
        "tool": "engineering_model_build",
        "operation": "BUILD.COLUMN",
        "project_id": PROJECT_ID,
        "priority": DEFAULT_TASK_PRIORITY,
        "max_retries": 0,
        "status": str(TaskStatus.CREATED),
    }
    values.update(overrides)
    return TaskDraft(**values)


def _submission(**overrides: Any) -> TaskSubmission:
    """构造一个 `TaskSubmission`（`docs/02` §9 / §47）。"""
    values: dict[str, Any] = {
        "tenant_id": TENANT_ID,
        "request_id": f"req_{uuid4().hex}",
        "trace_id": f"trace_{uuid4().hex}",
        "tool": "engineering_model_build",
        "operation": "BUILD.COLUMN",
        "project_id": PROJECT_ID,
        "software_instance_id": INSTANCE_ID,
        "user_id": "user-a",
        "priority": TaskPriority.NORMAL,
        "max_retries": 0,
    }
    values.update(overrides)
    return TaskSubmission(**values)


def _step(
    step_key: str,
    *,
    operation: str = "BUILD.COLUMN",
    depends_on: tuple[str, ...] = (),
) -> TaskStepDraft:
    """构造一个 DAG 步骤草稿（`docs/02` §47）。"""
    return TaskStepDraft(
        step_key=step_key,
        operation=operation,
        parameters_json=json.dumps({"height": 6.0}, sort_keys=True),
        depends_on=depends_on,
    )


def _definition(name: str, *, recovery_policy: str = "SAFE_RETRY") -> OperationDefinition:
    """构造一条 Operation 定义（`docs/02` §11 的 12 字段；只需其中几项参与本批判定）。"""
    return OperationDefinition(
        name=name,
        tool="engineering_model_build",
        risk_level=RiskLevel.MEDIUM,
        execution_mode=ExecutionMode.ASYNC,
        input_schema="structai://schema/build/column/v1",
        output_schema="structai://schema/build/column/v1",
        recovery_policy=recovery_policy,
    )


def _registry(*definitions: OperationDefinition) -> OperationRegistry:
    """运行时 Operation Registry（`docs/02` §28；P08 的实现）。"""
    return OperationRegistry(definitions or (_definition("BUILD.COLUMN"),))


async def _task_in(
    session: AsyncSession,
    *,
    status: str = str(TaskStatus.QUEUED),
    fields: Mapping[str, object] | None = None,
    tenant_id: str = TENANT_ID,
    steps: Sequence[TaskStepDraft] = (),
    **draft_overrides: Any,
) -> TaskRecord:
    """落一个**指定状态**的任务（`TaskStore` 只做 persistence，不做状态校验）。

    ⚠️ 这是**测试专用**的构造手法：直接经 `transition` 把任务摆到目标状态，
    从而能在不跑完整引擎的情况下验证租约 / 恢复 / 取消的边界。
    """
    store = build_task_store(session)
    created = await store.create(_draft(tenant_id=tenant_id, **draft_overrides), steps)
    if str(status) != created.status or fields:
        moved = await store.transition(
            created.id,
            expected=created.status,
            new=str(status),
            fields=dict(fields) if fields else None,
        )
        assert moved is True
    latest = await store.get(created.id, tenant_id)
    assert latest is not None
    return latest


def _expired_lease(now: datetime | None = None) -> dict[str, object]:
    """一个**已过期**的租约（`docs/02` §40 / §81 的崩溃场景）。"""
    moment = now or datetime.now(UTC)
    return {
        "lease_owner": "worker-gone",
        "lease_until": moment - timedelta(seconds=60),
        "heartbeat_at": moment - timedelta(seconds=90),
    }


def _live_lease(worker_id: str = "worker-alive") -> dict[str, object]:
    """一个**仍有效**的租约（`docs/02` §41 的 `lease expired? NO → leave running`）。"""
    moment = datetime.now(UTC)
    return {
        "lease_owner": worker_id,
        "lease_until": moment + timedelta(seconds=300),
        "heartbeat_at": moment,
    }


class _RecordingExecutor:
    """记录调用顺序的 `TaskExecutor` 替身（`docs/02` §48；P36 才落地真实实现）。"""

    def __init__(
        self,
        result: Mapping[str, Any] | None = None,
        *,
        error: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        self.calls: list[str] = []
        self.statuses: list[str] = []
        self._result: Mapping[str, Any] = {"ok": True} if result is None else result
        self._error = error
        self._delay = delay

    async def execute(
        self,
        task: TaskRecord,
        *,
        context: object | None = None,
    ) -> Mapping[str, Any]:
        """记录调用（含任务状态）后返回固定结果或抛出预设异常。"""
        self.calls.append(task.id)
        self.statuses.append(str(task.status))
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error is not None:
            raise self._error
        return self._result


class _FakeCancellation:
    """记录取消调用的假取消端口（`docs/02` §53；`AdapterManager.cancel` 的结构替身）。"""

    def __init__(self, *, error: Exception | None = None, status_of: Any = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.observed: list[str] = []
        self._error = error
        self._status_of = status_of

    async def cancel(self, software_instance_id: str, task_id: str) -> None:
        """记录调用；在回调里读一次库状态（用于证明中间态是 `CANCEL_REQUESTED`）。"""
        self.calls.append((software_instance_id, task_id))
        if self._status_of is not None:
            task = await self._status_of(task_id)
            self.observed.append("" if task is None else str(task.status))
        if self._error is not None:
            raise self._error


class _RecordingBus:
    """记录发布事件的假事件总线（`docs/02` §32 / §34）。"""

    def __init__(self) -> None:
        self.events: list[object] = []

    async def publish(self, event: object) -> None:
        """记录一条事件。"""
        self.events.append(event)

    async def subscribe(self, event_type: object, handler: object) -> None:
        """本替身不支持订阅（本批不验证订阅路径）。"""
        return None


# ===== ① 状态机（`docs/07` §10.1；`docs/02` §7 / §8 / §76）=====


def test_state_machine_is_centralized_in_one_module() -> None:
    """门槛 ①（`docs/07` §10.1）：12 态与转移表**只在** `state_machine.py` 定义。"""
    defining = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in APP_DIR.rglob("*.py")
        if {"ALLOWED_TRANSITIONS", "TASK_STATE_SEQUENCE"} & _module_level_names(path)
    )
    assert defining == ["app/application/task/state_machine.py"], defining

    # 其它文件里不得出现「字典字面量形式的转移表」（散落的第二份判定）。
    offenders: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        if path.name == "state_machine.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any("TRANSITION" in name.upper() for name in targets):
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []


def test_twelve_states_match_the_frozen_sequence() -> None:
    """门槛 ①：`TASK_STATE_SEQUENCE` 与 `docs/07` §10.1 的 12 态**逐项**一致。"""
    assert tuple(str(status) for status in TASK_STATE_SEQUENCE) == TASK_STATES_SPEC
    assert len(TASK_STATES_SPEC) == 12
    assert set(ALLOWED_TRANSITIONS_SPEC) == set(TASK_STATES_SPEC)
    assert {str(status) for status in TERMINAL_STATUSES} == set(TERMINAL_STATES_SPEC)


def test_every_transition_cell_is_asserted() -> None:
    """门槛 ①：12×12 = **144 格**逐格断言 `can_transition`（`docs/07` §16 R41）。"""
    checked = 0
    for current in TASK_STATES_SPEC:
        for target in TASK_STATES_SPEC:
            expected = target in ALLOWED_TRANSITIONS_SPEC[current]
            assert can_transition(current, target) is expected, (current, target)
            checked += 1
    assert checked == 144

    # 表本身也逐键核对（12 个键、含两个终态空集）。
    assert len(ALLOWED_TRANSITIONS) == 12
    for current, allowed in ALLOWED_TRANSITIONS_SPEC.items():
        assert {str(item) for item in ALLOWED_TRANSITIONS[TaskStatus(current)]} == set(allowed)


def test_legal_chain_succeeds_and_illegal_transition_is_rejected() -> None:
    """门槛 ①（`docs/02` §76）：合法链全通；`COMPLETED` 上再转移必须**拒绝**且状态不变。"""
    machine = TaskStateMachine()
    for step in ("VALIDATING", "QUEUED", "RUNNING", "PROCESSING", "COMPLETED"):
        assert str(machine.transition(step)) == step
    assert machine.status is TaskStatus.COMPLETED

    with pytest.raises(TaskStateError) as excinfo:
        machine.transition(TaskStatus.RUNNING)
    error = excinfo.value
    assert error.code == "STRUCTAI-1300"
    assert isinstance(error, ConcurrencyConflictError)
    assert error.details["stage"] == "state_machine"
    assert error.details["from"] == "COMPLETED"
    assert error.details["to"] == "RUNNING"
    # 拒绝 ≠ 静默忽略、≠ 自动纠正：状态**保持不变**（`docs/07` §10.2）。
    assert machine.status is TaskStatus.COMPLETED
    assert machine.allowed() == frozenset()

    # 纯函数形态与值对象形态共用同一张表（不存在第二份判定）。
    assert transition("VALIDATING", "QUEUED") is TaskStatus.QUEUED
    with pytest.raises(TaskStateError):
        transition("CANCELLED", "QUEUED")


def test_terminal_states_have_no_outgoing_edges() -> None:
    """门槛 ①（`docs/07` §10.1）：`COMPLETED` / `CANCELLED` 无出边；`FAILED` 不是终态。"""
    for terminal in TERMINAL_STATES_SPEC:
        assert ALLOWED_TRANSITIONS[TaskStatus(terminal)] == frozenset()
        assert not any(can_transition(terminal, target) for target in TASK_STATES_SPEC)

    # `FAILED` / `TIMEOUT` 还有 `RETRYING` 出边（`docs/02` §7 / §77 / §78）。
    assert can_transition("FAILED", "RETRYING")
    assert can_transition("TIMEOUT", "RETRYING")
    assert {str(item) for item in RETRYABLE_STATUSES} == {"FAILED", "TIMEOUT"}


def test_recovering_never_reaches_completed_directly() -> None:
    """门槛 ①（`docs/07` §14.4）：`RECOVERING` 的出边里**没有** `COMPLETED`。"""
    assert can_transition("RECOVERING", "COMPLETED") is False
    assert "COMPLETED" not in ALLOWED_TRANSITIONS_SPEC["RECOVERING"]
    assert {str(item) for item in ALLOWED_TRANSITIONS[TaskStatus.RECOVERING]} == {
        "QUEUED",
        "RUNNING",
        "FAILED",
    }


def test_task_state_error_does_not_extend_the_twenty_code_contract() -> None:
    """门槛 ①（`docs/07` §16 R42）：`TaskStateError` 是既有 `STRUCTAI-1300` 的子类。"""
    assert issubclass(TaskStateError, ConcurrencyConflictError)
    assert TaskStateError.code == "STRUCTAI-1300"
    assert TaskStateError.code in ERROR_CODES_SPEC
    # 同族：租约错误同样不新增码（R42 的同类裁决）。
    assert issubclass(TaskLeaseError, ConcurrencyConflictError)
    assert TaskLeaseError.code == "STRUCTAI-1300"


# ===== 服务装配辅助（会话级；`docs/02` §33）=====


def _lease(session: AsyncSession, **overrides: Any) -> LeaseService:
    """装配租约服务（`docs/02` §34–§38）；缺省取规范默认值 `30s` / `10s`。"""
    values: dict[str, Any] = {"lease_seconds": 30, "heartbeat_seconds": 10}
    values.update(overrides)
    return LeaseService(build_task_store(session), **values)


def _cancellation(session: AsyncSession, port: Any = None) -> CancellationService:
    """装配取消服务（`docs/02` §43）。"""
    return CancellationService(build_task_store(session), port)


def _recovery(
    session: AsyncSession,
    operations: OperationRegistry | None = None,
    *,
    enqueue: Any = None,
) -> RecoveryService:
    """装配启动恢复服务（`docs/02` §42）。"""
    return RecoveryService(
        build_task_store(session),
        operations or _registry(),
        enqueue=enqueue,
    )


def _progress(session: AsyncSession, bus: Any = None) -> ProgressReporter:
    """装配进度上报器（`docs/02` §31–§33）。"""
    return ProgressReporter(build_task_store(session), bus=bus)


# ===== ② Lease（`docs/02` §34–§38 / §80）=====


def test_lease_acquire_heartbeat_and_release_are_conditional_updates(
    engine: AsyncEngine,
) -> None:
    """门槛 ②（`docs/02` §36）：三个租约操作**各只有一条** `UPDATE`，且**无前置 `SELECT`**。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            task = await _task_in(uow.session, status=str(TaskStatus.QUEUED))
            lease = _lease(uow.session)
            statements = _recorded_statements(engine)

            await lease.acquire(task.id, "worker-a")
            acquire_verbs = _table_verbs(statements, "tasks")
            assert acquire_verbs.count("UPDATE") == 1, acquire_verbs
            # **第一条**针对 `tasks` 的语句就是 `UPDATE`：没有 `SELECT → UPDATE` 竞态。
            assert acquire_verbs[0] == "UPDATE", acquire_verbs
            acquire_sql = _first_update(statements, "tasks")
            assert "lease_owner is null" in acquire_sql
            assert "lease_until <" in acquire_sql
            assert "or" in acquire_sql

            statements.clear()
            await lease.heartbeat(task.id, "worker-a", tenant_id=TENANT_ID)
            heartbeat_verbs = _table_verbs(statements, "tasks")
            assert heartbeat_verbs.count("UPDATE") == 1, heartbeat_verbs
            assert heartbeat_verbs[0] == "UPDATE", heartbeat_verbs
            heartbeat_sql = _first_update(statements, "tasks")
            assert "lease_owner =" in heartbeat_sql
            assert "heartbeat_at=" in heartbeat_sql
            assert "lease_until=" in heartbeat_sql

            statements.clear()
            assert await lease.release(task.id, "worker-a") is True
            release_verbs = _table_verbs(statements, "tasks")
            assert release_verbs.count("UPDATE") == 1, release_verbs
            assert release_verbs[0] == "UPDATE", release_verbs
            release_sql = _first_update(statements, "tasks")
            assert "lease_owner=" in release_sql
            assert "lease_until=" in release_sql
            assert "lease_owner =" in release_sql

    asyncio.run(_run())


def test_two_workers_cannot_hold_the_same_lease(engine: AsyncEngine) -> None:
    """门槛 ②（`docs/02` §80）：两个 Worker 并发抢同一任务 → **恰好一个**成功。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            task = await _task_in(uow.session, status=str(TaskStatus.QUEUED))
            lease = _lease(uow.session)
            barrier = asyncio.Barrier(2)

            async def _attempt(worker_id: str) -> str:
                await barrier.wait()
                try:
                    record = await lease.acquire(task.id, worker_id)
                except TaskLeaseError as error:
                    assert error.code == "STRUCTAI-1300"
                    assert error.details == {"stage": "lease", "reason": "unavailable"}
                    return f"rejected:{worker_id}"
                return f"acquired:{record.lease_owner}"

            outcomes = await asyncio.gather(_attempt("worker-a"), _attempt("worker-b"))
            acquired = [item for item in outcomes if item.startswith("acquired:")]
            rejected = [item for item in outcomes if item.startswith("rejected:")]
            assert len(acquired) == 1, outcomes
            assert len(rejected) == 1, outcomes

            latest = await build_task_store(uow.session).get(task.id, TENANT_ID)
            assert latest is not None
            assert latest.lease_owner == acquired[0].split(":", 1)[1]
            assert latest.lease_until is not None

    asyncio.run(_run())


def test_heartbeat_extends_lease_and_rejects_non_owner(engine: AsyncEngine) -> None:
    """门槛 ②（`docs/02` §38）：续租延长 `lease_until` 并刷新 `heartbeat_at`；非持有者被拒。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            task = await _task_in(uow.session, status=str(TaskStatus.QUEUED))
            lease = _lease(uow.session, lease_seconds=300, heartbeat_seconds=10)
            acquired = await lease.acquire(task.id, "worker-a")
            assert acquired.lease_owner == "worker-a"
            first_until = acquired.lease_until
            first_heartbeat = acquired.heartbeat_at
            assert first_until is not None
            assert first_heartbeat is not None

            renewed = await lease.heartbeat(task.id, "worker-a", tenant_id=TENANT_ID)
            assert renewed is not None
            assert renewed.lease_owner == "worker-a"
            assert renewed.lease_until is not None
            assert renewed.heartbeat_at is not None
            # 时间口径：读回来的时间必须是**带时区**的 UTC（`docs/02` §36）。
            assert renewed.lease_until.tzinfo is not None
            assert renewed.heartbeat_at.tzinfo is not None

            with pytest.raises(TaskLeaseError) as excinfo:
                await lease.heartbeat(task.id, "worker-b", tenant_id=TENANT_ID)
            assert excinfo.value.details == {"stage": "lease", "reason": "not_owner"}
            assert excinfo.value.code == "STRUCTAI-1300"

            after = await build_task_store(uow.session).get(task.id, TENANT_ID)
            assert after is not None
            assert after.lease_owner == "worker-a"

    asyncio.run(_run())


def test_expired_lease_is_reclaimable(engine: AsyncEngine) -> None:
    """门槛 ②（`docs/02` §40）：租约过期后另一个 Worker 能重新抢占。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            task = await _task_in(
                uow.session,
                status=str(TaskStatus.RUNNING),
                fields=_expired_lease(),
            )
            assert task.lease_owner == "worker-gone"
            lease = _lease(uow.session)
            assert lease.is_expired(task) is True

            reclaimed = await lease.acquire(task.id, "worker-b")
            assert reclaimed.lease_owner == "worker-b"
            assert reclaimed.lease_until is not None
            assert lease.is_expired(reclaimed) is False

    asyncio.run(_run())


def test_release_lease_clears_owner(engine: AsyncEngine) -> None:
    """门槛 ②（`docs/02` §40）：释放清空 `lease_owner` / `lease_until`；非持有者释放无效。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            task = await _task_in(uow.session, status=str(TaskStatus.QUEUED))
            lease = _lease(uow.session)
            await lease.acquire(task.id, "worker-a")

            # 非持有者不得释放别人手里的租约。
            assert await lease.release(task.id, "worker-b") is False
            still = await build_task_store(uow.session).get(task.id, TENANT_ID)
            assert still is not None
            assert still.lease_owner == "worker-a"

            assert await lease.release(task.id, "worker-a") is True
            released = await build_task_store(uow.session).get(task.id, TENANT_ID)
            assert released is not None
            assert released.lease_owner is None
            assert released.lease_until is None
            # 幂等：再次释放不抛错、不产生副作用。
            assert await lease.release(task.id, "worker-a") is False

    asyncio.run(_run())


def test_heartbeat_must_be_less_than_half_the_lease() -> None:
    """门槛 ②（`docs/02` §37）：`heartbeat < lease / 2` 是**构造期**校验（装配错误即拒绝）。"""
    assert heartbeat_is_within_lease(30, 10) is True
    assert heartbeat_is_within_lease(30, 14) is True
    assert heartbeat_is_within_lease(30, 15) is False
    assert heartbeat_is_within_lease(30, 16) is False

    store = build_task_store(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="half the lease"):
        LeaseService(store, lease_seconds=30, heartbeat_seconds=15)
    with pytest.raises(ValueError, match="lease_seconds must be positive"):
        LeaseService(store, lease_seconds=0, heartbeat_seconds=10)
    with pytest.raises(ValueError, match="heartbeat_seconds must be positive"):
        LeaseService(store, lease_seconds=30, heartbeat_seconds=0)

    service = LeaseService(store, lease_seconds=30, heartbeat_seconds=10)
    assert service.lease_seconds == 30
    assert service.heartbeat_seconds == 10
    assert service.store is store
    assert service.now().tzinfo is not None


def _first_update(statements: Sequence[str], table: str) -> str:
    """作用于指定表的第一条 `UPDATE` 语句（空白归一化 + 小写，便于断言 `WHERE` 子句）。"""
    for statement in _table_statements(statements, table):
        if statement.lstrip().upper().startswith("UPDATE"):
            return " ".join(statement.split()).lower()
    raise AssertionError(f"no UPDATE statement against {table}: {list(statements)}")


# ===== ③ Recovery（`docs/02` §42 / §45 / §52 / §66 / §81；`docs/07` §14.4）=====


def test_effective_lease_is_waited_for_and_never_touched(engine: AsyncEngine) -> None:
    """门槛 ③（`docs/02` §41）：租约**有效** → `waited=True` 且状态 / 版本**逐列不变**。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            task = await _task_in(
                uow.session,
                status=str(TaskStatus.RUNNING),
                fields=_live_lease(),
            )
            statements = _recorded_statements(engine)
            service = _recovery(uow.session)
            outcome = await service.recover_task(task)

            assert outcome.waited is True
            assert outcome.status is TaskStatus.RUNNING
            assert outcome.reason == ""
            assert outcome.policy == "SAFE_RETRY"
            assert outcome.action is RecoveryAction.REQUEUE

            # 「对账」不等于「改状态」：整条恢复路径**零写动词**。
            assert _write_verbs(statements) == [], statements

            after = await build_task_store(uow.session).get(task.id, TENANT_ID)
            assert after is not None
            assert after.status == task.status
            assert after.version == task.version
            assert after.lease_owner == task.lease_owner
            assert after.lease_until == task.lease_until
            assert after.retry_count == task.retry_count
            assert after.progress == task.progress

    asyncio.run(_run())


def test_expired_lease_enters_recovering_then_requeues(engine: AsyncEngine) -> None:
    """门槛 ③（`docs/02` §42 / §81）：`RUNNING` + 过期租约 + `SAFE_RETRY` → `QUEUED`。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        enqueued: list[str] = []

        async def _enqueue(record: TaskRecord) -> None:
            enqueued.append(record.id)
            assert record.status == str(TaskStatus.QUEUED)

        async with UnitOfWork.from_session_factory(factory) as uow:
            task = await _task_in(
                uow.session,
                status=str(TaskStatus.RUNNING),
                fields=_expired_lease(),
            )
            service = _recovery(
                uow.session,
                _registry(_definition("BUILD.COLUMN")),
                enqueue=_enqueue,
            )
            outcome = await service.recover_task(task)

            assert outcome.action is RecoveryAction.REQUEUE
            assert outcome.status is TaskStatus.QUEUED
            assert outcome.waited is False
            assert outcome.reason == ""
            assert enqueued == [task.id]

            after = await build_task_store(uow.session).get(task.id, TENANT_ID)
            assert after is not None
            assert after.status == str(TaskStatus.QUEUED)
            # 恢复不置 `COMPLETED`（`docs/07` §14.4）。
            assert after.status != str(TaskStatus.COMPLETED)

    asyncio.run(_run())


def test_recovery_policy_mapping_is_the_only_conversion_point() -> None:
    """门槛 ③（`docs/02` §45 / §18；`docs/07` §16 R15）：两个词表之间的**唯一**转换点。"""
    assert tuple(sorted(RECOVERY_POLICIES_SPEC)) == tuple(sorted(POLICY_TO_ACTION))
    expected = {
        "SAFE_RETRY": RecoveryAction.REQUEUE,
        "STATE_RECONCILE": RecoveryAction.RESUME,
        "MANUAL_REVIEW": RecoveryAction.FAIL,
        "FAIL": RecoveryAction.FAIL,
    }
    for policy, action in expected.items():
        assert POLICY_TO_ACTION[policy] is action, policy

    # 恢复动作词表**恰好**三个（与 `recovery_policy` 的四值不同 —— 两套词表）。
    assert tuple(item.value for item in RecoveryAction) == RECOVERY_ACTIONS_SPEC
    assert len(RECOVERY_ACTIONS_SPEC) == 3
    assert len(RECOVERY_POLICIES_SPEC) == 4
    assert set(RECOVERY_POLICIES_SPEC) != set(RECOVERY_ACTIONS_SPEC)
    # 未知策略**不在**映射内 → 调用方必须显式回落 `FAIL`（不臆测可重试）。
    assert "RETRY_SAFE" not in POLICY_TO_ACTION
    assert "MANUAL" not in POLICY_TO_ACTION


def test_unknown_policy_falls_back_to_fail(engine: AsyncEngine) -> None:
    """门槛 ③（`docs/02` §44；`docs/07` §16 R15）：未知 / 未登记策略一律 `FAIL`。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            task = await _task_in(
                uow.session,
                status=str(TaskStatus.QUEUED),
                fields=_expired_lease(),
                operation="UNKNOWN.OPERATION",
            )
            # 注册表里**没有**这个 Operation → 策略回落 `FAIL`（不臆测可重试）。
            service = _recovery(uow.session, _registry(_definition("BUILD.COLUMN")))
            outcome = await service.recover_task(task)
            assert outcome.policy == "FAIL"
            assert outcome.action is RecoveryAction.FAIL
            assert outcome.status is TaskStatus.FAILED

            # 已登记但策略不在词表内（例如 `RETRY_SAFE`）→ 同样 `FAIL`。
            weird = await _task_in(
                uow.session,
                status=str(TaskStatus.QUEUED),
                fields=_expired_lease(),
                operation="WEIRD.OPERATION",
            )
            service = _recovery(
                uow.session,
                _registry(_definition("WEIRD.OPERATION", recovery_policy="RETRY_SAFE")),
            )
            outcome = await service.recover_task(weird)
            assert outcome.policy == "RETRY_SAFE"
            assert outcome.action is RecoveryAction.FAIL
            assert outcome.status is TaskStatus.FAILED

    asyncio.run(_run())


def test_resume_policy_returns_the_task_to_running(engine: AsyncEngine) -> None:
    """门槛 ③（`docs/02` §45 / §41）：`STATE_RECONCILE → RESUME` → `RECOVERING → RUNNING`。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            task = await _task_in(
                uow.session,
                status=str(TaskStatus.PROCESSING),
                fields=_expired_lease(),
            )
            service = _recovery(
                uow.session,
                _registry(_definition("BUILD.COLUMN", recovery_policy="STATE_RECONCILE")),
            )
            outcome = await service.recover_task(task)
            assert outcome.policy == "STATE_RECONCILE"
            assert outcome.action is RecoveryAction.RESUME
            assert outcome.status is TaskStatus.RUNNING
            assert outcome.waited is False

            after = await build_task_store(uow.session).get(task.id, TENANT_ID)
            assert after is not None
            assert after.status == str(TaskStatus.RUNNING)

    asyncio.run(_run())


def test_fail_policy_marks_failed_with_structai_5300(engine: AsyncEngine) -> None:
    """门槛 ③（`docs/07` §11）：`MANUAL_REVIEW → FAIL` 并落 `STRUCTAI-5300` 的 `to_dict()`。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            task = await _task_in(
                uow.session,
                status=str(TaskStatus.QUEUED),
                fields=_expired_lease(),
            )
            service = _recovery(
                uow.session,
                _registry(_definition("BUILD.COLUMN", recovery_policy="MANUAL_REVIEW")),
            )
            outcome = await service.recover_task(task)
            assert outcome.action is RecoveryAction.FAIL
            assert outcome.status is TaskStatus.FAILED

            after = await build_task_store(uow.session).get(task.id, TENANT_ID)
            assert after is not None
            assert after.error_json is not None
            payload = json.loads(after.error_json)
            assert (
                payload
                == TaskRecoveryError(
                    "Task recovery failed",
                    details={
                        "stage": "recovery",
                        "reason": "policy_fail",
                        "policy": "MANUAL_REVIEW",
                    },
                ).to_dict()
            )
            assert payload["code"] == "STRUCTAI-5300"
            assert payload["retryable"] is False

    asyncio.run(_run())


def test_recovery_never_marks_a_task_completed(engine: AsyncEngine) -> None:
    """门槛 ③（`docs/07` §14.4）：四条入口 × 四种策略 → 结果状态**从不是** `COMPLETED`。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            for entry in RECOVERY_ENTRY_STATUSES_SPEC:
                for policy in RECOVERY_POLICIES_SPEC:
                    task = await _task_in(
                        uow.session,
                        status=entry,
                        fields=_expired_lease(),
                    )
                    service = _recovery(
                        uow.session,
                        _registry(_definition("BUILD.COLUMN", recovery_policy=policy)),
                    )
                    outcome = await service.recover_task(task)
                    assert outcome.status is not TaskStatus.COMPLETED, (entry, policy)
                    assert outcome.status in {
                        TaskStatus.QUEUED,
                        TaskStatus.RUNNING,
                        TaskStatus.FAILED,
                        TaskStatus.RECOVERING,
                    }, (entry, policy, outcome.status)
                    after = await build_task_store(uow.session).get(task.id, TENANT_ID)
                    assert after is not None
                    assert after.status != str(TaskStatus.COMPLETED), (entry, policy)
        assert len(RECOVERY_ENTRY_STATUSES_SPEC) * len(RECOVERY_POLICIES_SPEC) == 16

    asyncio.run(_run())


def test_recovery_only_scans_the_four_entry_statuses(engine: AsyncEngine) -> None:
    """门槛 ③（`docs/02` §52 / §66）：扫描语句的 `WHERE status IN (...)` 恰为那四态。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            await _task_in(uow.session, status=str(TaskStatus.QUEUED), fields=_expired_lease())
            executions = _recorded_executions(engine)
            service = _recovery(uow.session)
            outcomes = await service.recover_unfinished_tasks()
            assert len(outcomes) == 1
            assert outcomes[0].status is TaskStatus.QUEUED

            selects = [
                " ".join(statement.split()).lower()
                for statement, _ in executions
                if statement.lstrip().upper().startswith("SELECT")
                and "from tasks" in " ".join(statement.split()).lower()
            ]
            assert len(selects) == 1, selects
            scanned = selects[0]
            assert "status in" in scanned
            # 状态名只在**绑定参数**里（`IN (...)` 渲染为占位符）：恰为 §42 的四态。
            bound = _scanned_statuses(executions)
            assert set(RECOVERY_ENTRY_STATUSES_SPEC) <= bound, bound
            assert (
                bound
                & {
                    "CREATED",
                    "VALIDATING",
                    "COMPLETED",
                    "FAILED",
                    "CANCEL_REQUESTED",
                    "CANCELLED",
                    "TIMEOUT",
                    "RETRYING",
                }
                == set()
            ), bound
            assert "status in (?, ?, ?, ?)" in scanned
            # 有界：`LIMIT` 必须存在（`docs/07` §14.4 禁止无限 payload）。
            assert "limit" in scanned
            # `WHERE` 子句里不得出现任何非入口状态（逐词核对，避开列名 `completed_at`）。
            where_clause = scanned.split(" where ", 1)[1]
            for excluded in ("completed", "cancelled", "failed", "retrying"):
                assert excluded not in where_clause, excluded
            # 排序与队列一致：`priority` + `created_at`（`docs/02` §17）。
            assert "order by" in scanned
            assert "priority" in scanned
            assert "created_at" in scanned

    asyncio.run(_run())


def test_recovery_entry_statuses_are_the_frozen_four() -> None:
    """门槛 ③（`docs/02` §52 / §66）：`RECOVERY_ENTRY_STATUSES` 恰为那四态。"""
    assert tuple(str(item) for item in RECOVERY_ENTRY_STATUSES) == RECOVERY_ENTRY_STATUSES_SPEC
    assert "COMPLETED" not in RECOVERY_ENTRY_STATUSES_SPEC
    assert "CANCELLED" not in RECOVERY_ENTRY_STATUSES_SPEC


def test_recovery_is_structural_about_never_reaching_completed() -> None:
    """门槛 ③（`docs/07` §14.4）：源码里**没有**任何把状态写成 `COMPLETED` 的恢复路径。"""
    source = (TASK_DIR / "recovery.py").read_text(encoding="utf-8")
    assert "TaskStatus.COMPLETED" not in source
    assert "COMPLETED" not in {str(action.value) for action in RecoveryAction}
    # `RECOVERING` 的出边里也没有 `COMPLETED`（结构性保证）。
    assert "COMPLETED" not in ALLOWED_TRANSITIONS_SPEC["RECOVERING"]


def _recorded_executions(engine: AsyncEngine) -> list[tuple[str, tuple[str, ...]]]:
    """录制 `(语句, 绑定参数值)`（用于断言 `IN (...)` 的**实际**取值）。

    ⚠️ SQLAlchemy 把 `IN (...)` 渲染成占位符（`status in (?, ?, ?, ?)`），
    状态名只出现在**绑定参数**里；故断言必须同时看参数（`docs/02` §52 的四态）。
    """
    executions: list[tuple[str, tuple[str, ...]]] = []

    def _capture(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        executions.append((statement, _flatten_parameters(parameters)))

    event.listen(engine.sync_engine, "before_cursor_execute", _capture)
    return executions


def _scanned_statuses(executions: Sequence[tuple[str, tuple[str, ...]]]) -> set[str]:
    """从录制的执行里取出 `SELECT ... FROM tasks WHERE status IN (...)` 的**绑定值**。"""
    for statement, bound in executions:
        normalized = " ".join(statement.split()).lower()
        if not normalized.startswith("select"):
            continue
        if "from tasks" not in normalized or "status in" not in normalized:
            continue
        return set(bound)
    raise AssertionError(f"no recovery scan statement: {[item[0] for item in executions]}")


def _flatten_parameters(parameters: object) -> tuple[str, ...]:
    """把 `before_cursor_execute` 的绑定参数摊平成字符串元组（`Mapping` / 序列都支持）。"""
    if isinstance(parameters, Mapping):
        values: Sequence[object] = list(parameters.values())
    elif isinstance(parameters, list | tuple):
        values = list(parameters)
    else:
        values = []
    return tuple(str(value) for value in values)


# ===== ④ DAG（`docs/02` §19 / §46–§51 / §82 / §83）=====


def test_topological_order_follows_dependencies() -> None:
    """门槛 ④（`docs/02` §82）：`A → B → C` 的拓扑序**恰为** `("A", "B", "C")`。"""
    graph = graph_from_drafts(
        (
            _step("C", depends_on=("B",)),
            _step("B", depends_on=("A",)),
            _step("A"),
        )
    )
    assert topological_order(graph) == ("A", "B", "C")
    assert validate_dag(graph) == ("A", "B", "C")
    # 依赖未满足时 B / C 都不可执行（`docs/02` §54「依赖满足后才能执行」）。
    assert ready_steps(graph, {}) == ("A",)


def test_diamond_dag_allows_parallel_steps() -> None:
    """门槛 ④（`docs/02` §51 / §83）：`A → {B, C} → D`：B、C **同时** ready。"""
    graph = graph_from_drafts(
        (
            _step("A"),
            _step("B", depends_on=("A",)),
            _step("C", depends_on=("A",)),
            _step("D", depends_on=("B", "C")),
        )
    )
    assert validate_dag(graph) == ("A", "B", "C", "D")
    assert ready_steps(graph, {}) == ("A",)

    after_a = {"A": TaskStepStatus.COMPLETED}
    assert ready_steps(graph, after_a) == ("B", "C")

    after_bc = {
        "A": TaskStepStatus.COMPLETED,
        "B": TaskStepStatus.COMPLETED,
        "C": TaskStepStatus.COMPLETED,
    }
    assert ready_steps(graph, after_bc) == ("D",)
    # 只完成一个分支时 D 仍不可执行（汇聚步骤等待**全部**前置）。
    assert ready_steps(
        graph,
        {"A": TaskStepStatus.COMPLETED, "B": TaskStepStatus.COMPLETED},
    ) == ("C",)

    plan = step_plan(graph, after_a)
    assert isinstance(plan, DagPlan)
    assert plan.ready == ("B", "C")
    assert plan.complete is False


def test_cycle_is_rejected_before_any_row_is_written(engine: AsyncEngine) -> None:
    """门槛 ④（`docs/02` §19 / §49）：`A→B→A` 在**提交前**拒绝，SQL 钩子证明零 `INSERT`。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            statements = _recorded_statements(engine)
            engine_ = TaskEngine(build_task_store(uow.session))
            submission = _submission(
                steps=(
                    _step("A", depends_on=("B",)),
                    _step("B", depends_on=("A",)),
                )
            )
            with pytest.raises(EngineeringValidationError) as excinfo:
                await engine_.create(submission)
            error = excinfo.value
            assert error.code == "STRUCTAI-1200"
            assert error.details["stage"] == "dag"
            assert error.details["reason"] == "cycle"

            # 「提交前拒绝」是**结构性**的：一条写语句都没发生。
            assert _write_verbs(statements) == [], statements
            assert _table_verbs(statements, "tasks") == []
            assert _table_verbs(statements, "task_steps") == []

    asyncio.run(_run())


def test_missing_dependency_and_duplicate_step_and_unknown_operation_are_rejected() -> None:
    """门槛 ④（`docs/02` §48）：缺依赖 / 重复步骤 / 未知 Operation 三个 `reason` 各一条。"""
    # ① 缺依赖。
    with pytest.raises(EngineeringValidationError) as missing:
        validate_dag(graph_from_drafts((_step("A", depends_on=("NOPE",)),)))
    assert missing.value.details["reason"] == "missing_dependency"
    assert missing.value.code == "STRUCTAI-1200"

    # ② 重复步骤（`graph_from_drafts` 在构造期就拒绝）。
    with pytest.raises(EngineeringValidationError) as duplicate:
        graph_from_drafts((_step("A"), _step("A")))
    assert duplicate.value.details["reason"] == "duplicate_step"

    # ③ 未知 Operation（只在传入 `known_operations` 时检查）。
    graph = graph_from_drafts((_step("A", operation="NOPE.OPERATION"),))
    with pytest.raises(EngineeringValidationError) as unknown:
        validate_dag(graph, known_operations=("BUILD.COLUMN",))
    assert unknown.value.details["reason"] == "unknown_step"
    # 不传 `known_operations` 时**不**检查（`docs/02` §48 的口径）。
    assert validate_dag(graph) == ("A",)

    assert set(DAG_VALIDATION_REASONS) == {
        "duplicate_step",
        "missing_dependency",
        "cycle",
        "unknown_step",
    }


def test_engine_create_rejects_unknown_operation_with_the_registry() -> None:
    """门槛 ④（`docs/02` §48 / §54）：`TaskEngine.create` 用 Registry 拒绝未登记的 Operation。"""

    async def _run() -> None:
        engine_ = create_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine_.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            factory = create_session_factory(engine_)
            async with UnitOfWork.from_session_factory(factory) as uow:
                registry = _registry(_definition("BUILD.COLUMN"))
                service = TaskEngine(build_task_store(uow.session), operations=registry)
                with pytest.raises(EngineeringValidationError) as excinfo:
                    await service.create(
                        _submission(steps=(_step("A", operation="NOPE.OPERATION"),))
                    )
                assert excinfo.value.details["reason"] == "unknown_step"
                assert excinfo.value.code == "STRUCTAI-1200"

                # 登记的 Operation 可以通过校验（并推进到 `QUEUED`）。
                record = await service.create(
                    _submission(steps=(_step("A", operation="BUILD.COLUMN"),))
                )
                assert record.status == str(TaskStatus.QUEUED)
        finally:
            await engine_.dispose()

    asyncio.run(_run())


def test_failed_dependency_skips_dependents_unless_continue_on_failure() -> None:
    """门槛 ④（`docs/02` §50）：前置 `FAILED` → 默认 `SKIPPED`；显式配置则继续。"""
    graph = TaskGraph(
        steps={
            "A": TaskStep(step_id="A", operation="BUILD.COLUMN"),
            "B": TaskStep(step_id="B", operation="BUILD.COLUMN", depends_on=("A",)),
            "C": TaskStep(
                step_id="C",
                operation="BUILD.COLUMN",
                depends_on=("A",),
                continue_on_failure=True,
            ),
        }
    )
    statuses = {"A": TaskStepStatus.FAILED}
    assert blocked_steps(graph, statuses) == ("B",)
    plan = step_plan(graph, statuses)
    assert plan.skipped == ("B",)
    assert "C" not in plan.skipped
    assert plan.has_failure is True

    # 被跳过的步骤同样阻塞其后继（递归传播）。
    chained = TaskGraph(
        steps={
            "A": TaskStep(step_id="A", operation="BUILD.COLUMN"),
            "B": TaskStep(step_id="B", operation="BUILD.COLUMN", depends_on=("A",)),
            "C": TaskStep(step_id="C", operation="BUILD.COLUMN", depends_on=("B",)),
        }
    )
    assert blocked_steps(chained, {"A": TaskStepStatus.FAILED}) == ("B", "C")
    assert tuple(sorted(str(item) for item in TERMINAL_STEP_STATUSES)) == (
        "COMPLETED",
        "FAILED",
        "SKIPPED",
    )
    assert {str(item) for item in TERMINAL_STEP_STATUSES} == {
        "COMPLETED",
        "FAILED",
        "SKIPPED",
    }


def test_dag_steps_are_persisted_in_task_steps(engine: AsyncEngine) -> None:
    """门槛 ④（`docs/07` §4.3 #20）：步骤落 `task_steps`，`depends_on_json` 是排序 JSON。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            store = build_task_store(uow.session)
            created = await store.create(
                _draft(),
                (
                    _step("A"),
                    _step("B", depends_on=("A",)),
                    # 逆序 + 重复：`encode_depends_on` 必须排序 + 去重。
                    _step("D", depends_on=("B", "A", "B")),
                ),
            )
            steps = await store.list_steps(created.id)
            assert [item.step_key for item in steps] == ["A", "B", "D"]
            assert all(item.status == "PENDING" for item in steps)
            assert all(item.task_id == created.id for item in steps)
            by_key = {item.step_key: item for item in steps}
            assert json.loads(by_key["A"].depends_on_json) == []
            assert json.loads(by_key["B"].depends_on_json) == ["A"]
            assert json.loads(by_key["D"].depends_on_json) == ["A", "B"]
            assert by_key["D"].depends_on_json == '["A", "B"]'
            assert json.loads(by_key["A"].parameters_json) == {"height": 6.0}
            assert isinstance(steps[0], TaskStepRecord)

            # `update_step` 是条件更新：存在 → True；不存在 → False。
            assert await store.update_step(by_key["A"].id, status="READY") is True
            assert await store.update_step("missing-step", status="READY") is False
            assert (
                await store.update_step(
                    by_key["B"].id,
                    status="FAILED",
                    error_json='{"code": "STRUCTAI-5000"}',
                )
                is True
            )
            refreshed = {item.step_key: item for item in await store.list_steps(created.id)}
            assert refreshed["A"].status == "READY"
            assert refreshed["B"].status == "FAILED"
            assert refreshed["B"].error_json == '{"code": "STRUCTAI-5000"}'

    asyncio.run(_run())


# ===== ⑤ 优先级与队列（`docs/02` §12–§17）=====


def test_queue_orders_by_priority_then_created_at() -> None:
    """门槛 ⑤（`docs/02` §17）：先入队的低优先级任务后出队；同优先级按 `created_at` 升序。"""

    async def _run() -> None:
        queue = TaskQueue()
        base = datetime.now(UTC)
        # 低优先级先入队（`priority` 数值越大越不紧急）。
        await queue.put("low", 100, created_at=base)
        await queue.put("high", 0, created_at=base)
        await queue.put("normal-early", 50, created_at=base - timedelta(seconds=5))
        await queue.put("normal-late", 50, created_at=base)

        order = [item.task_id for item in [await queue.get() for _ in range(4)]]
        assert order == ["high", "normal-early", "normal-late", "low"]
        assert queue.empty() is True

        # 同优先级 + 同 `created_at` → 按入队 FIFO（`sequence` 兜底）。
        for index in range(3):
            await queue.put(f"same-{index}", 50, created_at=base)
        fifo = [item.task_id for item in [await queue.get() for _ in range(3)]]
        assert fifo == ["same-0", "same-1", "same-2"]

    asyncio.run(_run())


def test_requeued_old_task_precedes_newer_one_at_the_same_priority() -> None:
    """门槛 ⑤（`docs/02` §17）：先创建（早 `created_at`）但**后**入队 → 仍先出队。"""

    async def _run() -> None:
        queue = TaskQueue()
        base = datetime.now(UTC)
        await queue.put("newer", 50, created_at=base)
        # 恢复 / 重排路径：旧任务晚入队，但 `created_at` 更早。
        await queue.put("older-requeued", 50, created_at=base - timedelta(minutes=10))

        first = await queue.get()
        second = await queue.get()
        assert first.task_id == "older-requeued"
        assert second.task_id == "newer"
        assert first.sequence > second.sequence  # 入队更晚，但排序更靠前（§17 的排序键）。

    asyncio.run(_run())


def test_priority_levels_match_the_frozen_mapping() -> None:
    """门槛 ⑤（`docs/02` §14）：0 / 10 / 50 / 100；默认 100 = `tasks.priority` 列默认值。"""
    assert {str(name): value for name, value in PRIORITY_LEVELS.items()} == PRIORITY_LEVELS_SPEC
    assert tuple(item.name for item in TaskPriority) == PRIORITY_NAMES_SPEC
    assert DEFAULT_TASK_PRIORITY == PRIORITY_LEVELS_SPEC["LOW"] == 100
    assert TaskORM.__table__.columns["priority"].default.arg == 100

    for name, value in PRIORITY_LEVELS_SPEC.items():
        assert priority_value(TaskPriority(name)) == value
        assert priority_value(name) == value
        assert priority_value(value) == value
    with pytest.raises(ValueError):
        priority_value("NOPE")
    with pytest.raises(ValueError):
        priority_value(True)


def test_bounded_queue_rejects_with_structai_5000() -> None:
    """门槛 ⑤（`docs/02` §56）：`maxsize=1` 时第二次 `put` → `STRUCTAI-5000`（可重试）。"""

    async def _run() -> None:
        queue = TaskQueue(maxsize=1)
        await queue.put("first", 100)
        with pytest.raises(TaskError) as excinfo:
            await queue.put("second", 100)
        error = excinfo.value
        assert error.code == "STRUCTAI-5000"
        assert error.retryable is True
        assert error.details == {"stage": "queue", "reason": "full"}
        # 队列满时**不**阻塞调用方、**不**丢弃已有项。
        assert queue.qsize() == 1
        assert (await queue.get()).task_id == "first"

    asyncio.run(_run())


def test_shutdown_marks_closed_and_keeps_pending_items() -> None:
    """门槛 ⑤（`docs/02` §38）：`shutdown()` 不丢数据、不杀进程；等待中的 `get()` 仍可取走。"""

    async def _run() -> None:
        queue = TaskQueue()
        await queue.put("pending", 100)
        await queue.shutdown()
        assert queue.closed is True
        # 已入队的项**不**被丢弃。
        assert queue.qsize() == 1
        item = await queue.get()
        assert item.task_id == "pending"
        queue.task_done()
        # 关闭后不再接受新任务（**不**静默丢弃）。
        with pytest.raises(RuntimeError, match="shut down"):
            await queue.put("later", 100)
        # 幂等。
        await queue.shutdown()
        assert queue.closed is True

    asyncio.run(_run())


# ===== ⑥ 并发（`docs/02` §18 / §20）=====


def test_strictest_of_four_levels_wins() -> None:
    """门槛 ⑥（`docs/02` §18）：四级取**最严格**；任一级更小都会收紧。"""

    async def _run() -> None:
        request = ConcurrencyRequest(
            task_id="t1",
            tenant_id="tenant-a",
            user_id="user-a",
            software_instance_id=INSTANCE_ID,
        )
        limits = ConcurrencyLimits(global_limit=5, tenant_limit=10, user_limit=4, instance_limit=1)
        scheduler = Scheduler(limits=limits)
        assert await scheduler.effective_limit(request) == (1, "software-instance")

        # 收紧任一级都会成为新的生效上限。
        cases = {
            "global": (ConcurrencyLimits(global_limit=1), (1, "software-instance")),
            "tenant": (
                ConcurrencyLimits(global_limit=5, tenant_limit=1, user_limit=4, instance_limit=1),
                (1, "software-instance"),
            ),
            "user": (
                ConcurrencyLimits(global_limit=5, tenant_limit=10, user_limit=1, instance_limit=1),
                (1, "software-instance"),
            ),
            "software-instance": (
                ConcurrencyLimits(global_limit=5, tenant_limit=10, user_limit=4, instance_limit=1),
                (1, "software-instance"),
            ),
        }
        for name, (candidate, expected) in cases.items():
            assert await Scheduler(limits=candidate).effective_limit(request) == expected, name

        # 实例策略为 `PARALLEL` 时实例级不参与 → 全局级成为最严格者。
        global_first = Scheduler(
            limits=ConcurrencyLimits(global_limit=1, tenant_limit=10, user_limit=4),
            policies=DefaultInstanceConcurrencyPolicy(
                {INSTANCE_ID: SoftwareInstanceConcurrencyPolicy.PARALLEL}
            ),
        )
        assert await global_first.effective_limit(request) == (1, "global")

        # `SERIAL` 语义下实例级恒为 1（即使 `instance_limit` 配得更大）。
        serial = Scheduler(
            limits=ConcurrencyLimits(global_limit=9, tenant_limit=9, user_limit=9, instance_limit=9)
        )
        assert await serial.effective_limit(request) == (1, "software-instance")

        # 默认值取自 §18 的示例。
        assert limits.tenant_limit == CONCURRENCY_EXAMPLE_SPEC["tenant"]
        assert limits.user_limit == CONCURRENCY_EXAMPLE_SPEC["user"]
        assert limits.instance_limit == CONCURRENCY_EXAMPLE_SPEC["software-instance"]
        assert ConcurrencyLimits().global_limit == 0
        assert tuple(CONCURRENCY_LEVELS) == CONCURRENCY_LEVELS_SPEC

    asyncio.run(_run())


def test_instance_policy_serial_limited_parallel() -> None:
    """门槛 ⑥（`docs/02` §20）：`SERIAL → 1`、`LIMITED → instance_limit`、`PARALLEL → 不设限`。"""

    async def _run() -> None:
        request = ConcurrencyRequest(
            task_id="t1",
            tenant_id="tenant-a",
            user_id="user-a",
            software_instance_id=INSTANCE_ID,
        )
        limits = ConcurrencyLimits(global_limit=0, tenant_limit=10, user_limit=4, instance_limit=3)

        serial = Scheduler(
            limits=limits,
            policies=DefaultInstanceConcurrencyPolicy(
                {INSTANCE_ID: SoftwareInstanceConcurrencyPolicy.SERIAL}
            ),
        )
        assert await serial.effective_limit(request) == (1, "software-instance")

        limited = Scheduler(
            limits=limits,
            policies=DefaultInstanceConcurrencyPolicy(
                {INSTANCE_ID: SoftwareInstanceConcurrencyPolicy.LIMITED}
            ),
        )
        assert await limited.effective_limit(request) == (3, "software-instance")

        parallel = Scheduler(
            limits=limits,
            policies=DefaultInstanceConcurrencyPolicy(
                {INSTANCE_ID: SoftwareInstanceConcurrencyPolicy.PARALLEL}
            ),
        )
        # 实例级不设限 → 生效上限退回其余三级中最严格者（此处 user=4）。
        assert await parallel.effective_limit(request) == (4, "user")

        # 没有实例维度时不参与实例级判定。
        without_instance = ConcurrencyRequest(task_id="t2", tenant_id="tenant-a", user_id="user-a")
        assert await parallel.effective_limit(without_instance) == (4, "user")

        assert tuple(item.value for item in SoftwareInstanceConcurrencyPolicy) == (
            INSTANCE_POLICIES_SPEC
        )

    asyncio.run(_run())


def test_default_instance_policy_is_serial() -> None:
    """门槛 ⑥（`docs/02` §20）：未知实例的策略一律回落 `SERIAL`（默认，桌面软件）。"""

    async def _run() -> None:
        default = DefaultInstanceConcurrencyPolicy()
        assert default.default is SoftwareInstanceConcurrencyPolicy.SERIAL
        assert (
            await default.policy_for("unknown-instance") is SoftwareInstanceConcurrencyPolicy.SERIAL
        )
        # 显式映射优先。
        mapped = DefaultInstanceConcurrencyPolicy(
            {INSTANCE_ID: SoftwareInstanceConcurrencyPolicy.PARALLEL}
        )
        assert await mapped.policy_for(INSTANCE_ID) is SoftwareInstanceConcurrencyPolicy.PARALLEL
        assert await mapped.policy_for("other") is SoftwareInstanceConcurrencyPolicy.SERIAL
        # `Scheduler` 的缺省策略来源也是 `SERIAL`（§20 的「默认」）。
        scheduler = Scheduler()
        assert isinstance(scheduler.policies, DefaultInstanceConcurrencyPolicy)
        assert scheduler.policies.default is SoftwareInstanceConcurrencyPolicy.SERIAL

    asyncio.run(_run())


def test_scheduler_admits_and_releases_idempotently() -> None:
    """门槛 ⑥（`docs/02` §18）：准入 / 拒绝 / 释放；拒绝**不**占额度、释放幂等。"""

    async def _run() -> None:
        scheduler = Scheduler(limits=ConcurrencyLimits(global_limit=1))
        first = ConcurrencyRequest(task_id="t1", tenant_id="tenant-a", user_id="user-a")
        second = ConcurrencyRequest(task_id="t2", tenant_id="tenant-a", user_id="user-a")

        admitted = await scheduler.try_acquire(first)
        assert admitted.admitted is True
        assert admitted.limit == 1
        assert admitted.level == "global"
        assert admitted.reason == ""
        assert scheduler.active(first) == 1

        rejected = await scheduler.try_acquire(second)
        assert rejected.admitted is False
        assert rejected.limit == 1
        assert rejected.level == "global"
        assert rejected.reason == "global"
        # 被拒**不**占用额度（拒绝路径无副作用）。
        assert scheduler.active(second) == 0
        assert scheduler.active_total() == 1

        # 幂等：重复 `try_acquire` 同一任务不重复计数。
        again = await scheduler.try_acquire(first)
        assert again.admitted is True
        assert scheduler.active_total() == 1

        await scheduler.release(first)
        assert scheduler.active(first) == 0
        assert scheduler.active_total() == 0
        # 释放幂等：重复释放不抛错、不产生负数。
        await scheduler.release(first)
        await scheduler.release(second)
        assert scheduler.active_total() == 0

        # 释放后第二个任务可以准入。
        assert (await scheduler.try_acquire(second)).admitted is True

    asyncio.run(_run())


def test_scheduler_does_not_touch_the_database(engine: AsyncEngine) -> None:
    """门槛 ⑥（`docs/02` §38）：`Scheduler` 是**进程内**状态 —— **零 SQL**。"""

    async def _run() -> None:
        statements = _recorded_statements(engine)
        scheduler = Scheduler(
            limits=ConcurrencyLimits(
                global_limit=2, tenant_limit=10, user_limit=4, instance_limit=1
            )
        )
        request = ConcurrencyRequest(
            task_id="t1",
            tenant_id="tenant-a",
            user_id="user-a",
            software_instance_id=INSTANCE_ID,
        )
        await scheduler.effective_limit(request)
        await scheduler.try_acquire(request)
        scheduler.active(request)
        await scheduler.release(request)
        assert statements == [], statements

        # 源码层面也没有 `app.infrastructure` 依赖（`docs/07` §14.1）。
        modules = _imported_modules(TASK_DIR / "scheduler.py")
        assert [name for name in modules if name.startswith("app.infrastructure")] == []

    asyncio.run(_run())


# ===== ⑦ Cancellation（`docs/02` §30 / §43 / §53 / §79）=====


def test_cancel_running_task_reaches_cancelled_through_the_adapter(engine: AsyncEngine) -> None:
    """门槛 ⑦（`docs/02` §53 / §79）：Adapter **恰好被调用一次**，中间态是 `CANCEL_REQUESTED`。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            store = build_task_store(uow.session)
            task = await _task_in(uow.session, status=str(TaskStatus.RUNNING))
            port = _FakeCancellation(status_of=lambda tid: store.get(tid, TENANT_ID))
            service = _cancellation(uow.session, port)

            outcome = await service.cancel(
                task.id,
                TENANT_ID,
                software_instance_id=INSTANCE_ID,
            )
            assert outcome.cancelled is True
            assert outcome.status is TaskStatus.CANCELLED
            assert outcome.reason == ""
            assert outcome.error_code is None
            assert port.calls == [(INSTANCE_ID, task.id)]
            # 中间态：Adapter 回调里读库看到的是 `CANCEL_REQUESTED`（`docs/02` §79）。
            assert port.observed == [str(TaskStatus.CANCEL_REQUESTED)]

            after = await store.get(task.id, TENANT_ID)
            assert after is not None
            assert after.status == str(TaskStatus.CANCELLED)
            assert after.cancel_requested is True

    asyncio.run(_run())


def test_cancel_without_adapter_support_keeps_cancel_requested(engine: AsyncEngine) -> None:
    """门槛 ⑦（`docs/02` §30）：Adapter 报错 → 状态**保持** `CANCEL_REQUESTED`，绝不伪造。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            store = build_task_store(uow.session)
            task = await _task_in(uow.session, status=str(TaskStatus.RUNNING))
            failure = AdapterError(
                "cannot cancel native operation",
                details={"stage": "adapter", "reason": "unsupported"},
            )
            port = _FakeCancellation(error=failure)
            service = _cancellation(uow.session, port)

            outcome = await service.cancel(
                task.id,
                TENANT_ID,
                software_instance_id=INSTANCE_ID,
            )
            assert outcome.cancelled is False
            assert outcome.status is TaskStatus.CANCEL_REQUESTED
            assert outcome.reason == "cancel_unsupported"
            assert outcome.error_code == "STRUCTAI-6000"
            assert port.calls == [(INSTANCE_ID, task.id)]

            after = await store.get(task.id, TENANT_ID)
            assert after is not None
            assert after.status == str(TaskStatus.CANCEL_REQUESTED)
            assert after.status != str(TaskStatus.CANCELLED)
            assert after.error_json is not None
            assert json.loads(after.error_json) == failure.to_dict()

    asyncio.run(_run())


def test_cancel_without_a_port_keeps_cancel_requested(engine: AsyncEngine) -> None:
    """门槛 ⑦（`docs/02` §30）：没有取消端口时同样**保持** `CANCEL_REQUESTED`。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            task = await _task_in(uow.session, status=str(TaskStatus.PROCESSING))
            service = _cancellation(uow.session)
            outcome = await service.cancel(
                task.id,
                TENANT_ID,
                software_instance_id=INSTANCE_ID,
            )
            assert outcome.cancelled is False
            assert outcome.status is TaskStatus.CANCEL_REQUESTED
            assert outcome.reason == "cancel_unsupported"
            assert outcome.error_code is None

    asyncio.run(_run())


def test_cancel_queued_task_goes_straight_to_cancelled_without_adapter(
    engine: AsyncEngine,
) -> None:
    """门槛 ⑦（`docs/02` §43）：未执行的任务直接 `CANCELLED`，**不**调 Adapter（`not_running`）。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            store = build_task_store(uow.session)
            port = _FakeCancellation()
            service = _cancellation(uow.session, port)
            for entry in ("CREATED", "VALIDATING", "QUEUED"):
                task = await _task_in(uow.session, status=entry)
                outcome = await service.cancel(
                    task.id,
                    TENANT_ID,
                    software_instance_id=INSTANCE_ID,
                )
                assert outcome.cancelled is True, entry
                assert outcome.status is TaskStatus.CANCELLED, entry
                assert outcome.reason == "not_running", entry
                after = await store.get(task.id, TENANT_ID)
                assert after is not None
                assert after.status == str(TaskStatus.CANCELLED)
            # 三条路径都**不**调 Adapter（没有 native 操作可停）。
            assert port.calls == []

    asyncio.run(_run())


def test_cancel_terminal_task_is_rejected(engine: AsyncEngine) -> None:
    """门槛 ⑦（`docs/02` §30）：终态 / `RECOVERING` / `RETRYING` 一律**拒绝**且状态不变。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            store = build_task_store(uow.session)
            service = _cancellation(uow.session, _FakeCancellation())
            for entry in (
                "COMPLETED",
                "CANCELLED",
                "FAILED",
                "TIMEOUT",
                "RECOVERING",
                "RETRYING",
                "CANCEL_REQUESTED",
            ):
                task = await _task_in(uow.session, status=entry)
                with pytest.raises(TaskStateError) as excinfo:
                    await service.cancel(task.id, TENANT_ID)
                error = excinfo.value
                assert error.code == "STRUCTAI-1300", entry
                assert error.details["to"] == str(TaskStatus.CANCEL_REQUESTED), entry
                after = await store.get(task.id, TENANT_ID)
                assert after is not None
                assert after.status == entry, entry

            with pytest.raises(TaskError) as missing:
                await service.cancel("no-such-task", TENANT_ID)
            assert missing.value.code == "STRUCTAI-5000"
            assert missing.value.details == {
                "stage": "cancellation",
                "reason": "unknown_task",
            }

    asyncio.run(_run())


def test_cancellation_never_kills_a_process() -> None:
    """门槛 ⑦（`docs/07` §14.4）：源码里**没有** `os.kill` / `signal` / `subprocess`。"""
    path = TASK_DIR / "cancellation.py"
    source = path.read_text(encoding="utf-8")
    # AST 级：**不**把文档字符串里的「禁止项清单」当成违规（否则自查文档会自我否定）。
    tree = ast.parse(source)
    attribute_names = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert attribute_names & {"kill", "killpg", "terminate", "system", "popen", "execv"} == set()
    modules = _imported_modules(path)
    for forbidden in ("subprocess", "signal", "os"):
        assert forbidden not in modules, forbidden
    # `CANCEL_UNSUPPORTED_MESSAGE` 是 `docs/02` §30 的原文消息。
    assert "cannot cancel native operation" in source
    assert issubclass(CancellationService, object)
    assert inspect.iscoroutinefunction(CancellationService.cancel)


def test_worker_does_not_overwrite_a_cancel_requested_task(engine: AsyncEngine) -> None:
    """门槛 ⑦（`docs/07` §14.4）：执行期间被取消 → Worker 的 CAS 失败 → **不是** `COMPLETED`。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            store = build_task_store(uow.session)
            task = await _task_in(uow.session, status=str(TaskStatus.RUNNING))
            # 模拟「执行中被取消」：直接把状态改成 `CANCEL_REQUESTED`。
            assert (
                await store.transition(
                    task.id,
                    expected=str(TaskStatus.RUNNING),
                    new=str(TaskStatus.CANCEL_REQUESTED),
                    fields={"cancel_requested": True},
                )
                is True
            )
            current = await store.get(task.id, TENANT_ID)
            assert current is not None
            worker = TaskWorker(
                worker_id="worker-a",
                queue=TaskQueue(),
                store=store,
                lease=_lease(uow.session),
                executor=_RecordingExecutor(),
            )
            # `RUNNING → PROCESSING` 的 CAS 必然失败（状态已是 `CANCEL_REQUESTED`）。
            returned = await worker._mark_completed(current, '{"ok": true}')  # noqa: SLF001
            assert returned.status == str(TaskStatus.CANCEL_REQUESTED)
            assert returned.status != str(TaskStatus.COMPLETED)
            after = await store.get(task.id, TENANT_ID)
            assert after is not None
            assert after.result_json is None

    asyncio.run(_run())


# ===== ⑧ Progress（`docs/02` §31–§33）=====


def test_progress_is_clamped_to_zero_one_hundred() -> None:
    """门槛 ⑧（`docs/02` §31 / §33）：`150 → 100`、`-10 → 0`、`42 → 42`、`42.7 → 42`。"""
    assert sanitize_progress(150) == 100
    assert sanitize_progress(-10) == 0
    assert sanitize_progress(42) == 42
    assert sanitize_progress(42.7) == 42
    assert sanitize_progress(0) == 0
    assert sanitize_progress(100) == 100
    assert sanitize_progress(0.4) == 0
    assert sanitize_progress(-0.4) == 0


def test_untrusted_adapter_progress_is_rejected_loudly() -> None:
    """门槛 ⑧（`docs/02` §33；`docs/07` §16 R48）：不可信进度 → `STRUCTAI-1200`。"""
    untrusted = (
        None,
        "80",
        True,
        False,
        float("nan"),
        float("inf"),
        float("-inf"),
        [80],
        {"progress": 80},
        object(),
    )
    for value in untrusted:
        with pytest.raises(EngineeringValidationError) as excinfo:
            sanitize_progress(value)
        error = excinfo.value
        assert error.code == "STRUCTAI-1200", value
        assert error.details["stage"] == "progress", value
        assert error.details["reason"] in PROGRESS_UNTRUSTED_REASONS, value
    assert PROGRESS_UNTRUSTED_REASONS == ("not_a_number", "not_finite")


def test_progress_is_written_only_by_the_reporter() -> None:
    """门槛 ⑧（`docs/07` §10.2）：`tasks.progress` 的写入只经 `progress.py` / 仓储。"""
    writers = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in APP_DIR.rglob("*.py")
        if re.search(r"\.\s*update_progress\(", path.read_text(encoding="utf-8"))
    )
    assert writers == ["app/application/task/progress.py"], writers


def test_progress_event_is_published(engine: AsyncEngine) -> None:
    """门槛 ⑧（`docs/02` §32）：`TaskProgress` 事件被发布，`progress` 与库中一致。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            store = build_task_store(uow.session)
            task = await _task_in(uow.session, status=str(TaskStatus.RUNNING))
            bus = _RecordingBus()
            reporter = _progress(uow.session, bus)

            update = await reporter.report(task.id, 150, "working")
            assert update.progress == 100
            assert update.task_id == task.id
            assert update.message == "working"
            assert len(bus.events) == 1
            event = bus.events[0]
            assert isinstance(event, TaskProgress)
            assert event.progress == 100
            assert event.message == "working"
            assert str(event.task_id) == task.id

            after = await store.get(task.id, TENANT_ID)
            assert after is not None
            assert after.progress == 100

            # Adapter 进度的**唯一**入口也走同一条写库路径。
            from_adapter = await reporter.report_from_adapter(task.id, 42.7, "adapter")
            assert from_adapter.progress == 42
            assert len(bus.events) == 2
            assert bus.events[1].progress == 42

    asyncio.run(_run())


def test_progress_for_unknown_task_is_structai_5000(engine: AsyncEngine) -> None:
    """门槛 ⑧（`docs/07` §11）：进度写到不存在的任务 → `STRUCTAI-5000`。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            reporter = _progress(uow.session)
            with pytest.raises(TaskError) as excinfo:
                await reporter.report("no-such-task", 50)
            error = excinfo.value
            assert error.code == "STRUCTAI-5000"
            assert error.details == {"stage": "progress", "reason": "unknown_task"}
            assert error.retryable is True
            # 不可信进度**先**被拒绝（不触库、不产生 `STRUCTAI-5000`）。
            with pytest.raises(EngineeringValidationError):
                await reporter.report("no-such-task", None)

    asyncio.run(_run())


def test_engine_update_progress_delegates_to_the_reporter(engine: AsyncEngine) -> None:
    """门槛 ⑧（`docs/02` §31）：`TaskEngine.update_progress` 是唯一入口的转发。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            task = await _task_in(uow.session, status=str(TaskStatus.RUNNING))
            reporter = _progress(uow.session)
            engine_ = TaskEngine(build_task_store(uow.session), progress=reporter)
            update = await engine_.update_progress(task.id, 55, "half")
            assert update.progress == 55

            # 未装配端口 → `STRUCTAI-7000`（装配错误必须显式暴露）。
            bare = TaskEngine(build_task_store(uow.session))
            with pytest.raises(InternalError) as excinfo:
                await bare.update_progress(task.id, 55)
            assert excinfo.value.code == "STRUCTAI-7000"
            assert excinfo.value.details["reason"] == "progress_not_configured"

    asyncio.run(_run())


# ===== ⑨ 顺序（`docs/02` §90 / §91）=====


def test_task_create_comes_after_idempotency_in_the_frozen_pipeline() -> None:
    """门槛 ⑨（`docs/02` §90）：`Idempotency` 先于 `Task / Transaction`；26 步逐条不变。"""
    from app.application.execution import EXECUTION_PIPELINE_ORDER

    assert EXECUTION_PIPELINE_ORDER == PIPELINE_ORDER_SPEC
    assert len(EXECUTION_PIPELINE_ORDER) == 26
    assert EXECUTION_PIPELINE_ORDER.index("Idempotency") < EXECUTION_PIPELINE_ORDER.index(
        "Task / Transaction"
    )
    assert TASK_CREATE_ORDER == TASK_CREATE_ORDER_SPEC
    assert TASK_CREATE_ORDER.index("Idempotency") < TASK_CREATE_ORDER.index("Task Create")
    assert TASK_CREATE_ORDER[0] == "ExecutionService"


def test_task_package_never_imports_the_idempotency_module() -> None:
    """门槛 ⑨（`docs/02` §90）：`app/application/task/**` **不** import 幂等模块。"""
    for path in sorted(TASK_DIR.glob("*.py")):
        modules = _imported_modules(path)
        offenders = [name for name in modules if "idempotency" in name]
        assert offenders == [], (path.name, offenders)
    source = (TASK_DIR / "engine.py").read_text(encoding="utf-8")
    assert "TASK_CREATE_ORDER" in source
    assert "ExecutionService → Idempotency → Task Create" in source


def test_task_engine_is_the_only_task_creation_point() -> None:
    """门槛 ⑨（`docs/02` §90）：`TaskDraft(` 只在 `engine.py` 构造；`store.create` 只被它调用。"""
    draft_builders = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in APP_DIR.rglob("*.py")
        if "TaskDraft(" in path.read_text(encoding="utf-8")
    )
    assert draft_builders == ["app/application/task/engine.py"], draft_builders

    create_callers = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in APP_DIR.rglob("*.py")
        if "self._store.create(" in path.read_text(encoding="utf-8")
    )
    assert create_callers == ["app/application/task/engine.py"], create_callers


# ===== ⑩ 回归（`docs/07` §12 P01 / P02 / P04；`docs/08` §3）=====


def test_batch_id_is_p22() -> None:
    """门槛 ⑩：容器批次号已推进到 **P22**（本批 = P22–P28 Task Engine）。"""
    assert BATCH_ID == "P22"


def test_p04_tables_and_select_one_are_not_regressed(engine: AsyncEngine) -> None:
    """门槛 ⑩（P04）：建表 **24** 张 + `SELECT 1` → 1；两张任务表**未改表**。"""

    async def _run() -> None:
        async with engine.connect() as connection:
            names = set(
                await connection.run_sync(
                    lambda sync_connection: sa_inspect(sync_connection).get_table_names()
                )
            )
            assert names == set(TWENTY_FOUR_TABLES_SPEC)
            assert len(Base.metadata.tables) == 24
            result = await connection.exec_driver_sql("SELECT 1")
            assert result.scalar_one() == 1
        assert set(TaskORM.__table__.columns.keys()) == set(TASK_TABLE_COLUMNS_SPEC)
        assert set(TaskStepORM.__table__.columns.keys()) == set(TASK_STEP_TABLE_COLUMNS_SPEC)
        assert len(TASK_TABLE_COLUMNS_SPEC) == 23
        assert len(TASK_STEP_TABLE_COLUMNS_SPEC) == 11

    asyncio.run(_run())


def test_main_exits_zero_with_empty_stdout_when_unprovisioned(tmp_path: Path) -> None:
    """门槛 ⑩：未配备库上 `python -m app.main` 退出码 0 且 **stdout 0 字节**。"""
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p22_unprovisioned.db').as_posix()}"
    result = _run_main(database_url)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert f"batch={BATCH_ID}" in result.stderr


def test_main_exits_zero_with_empty_stdout_when_provisioned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ⑩：已配备库（建表 + Seed）上同样退出码 0 且 **stdout 0 字节**。"""
    database_url = asyncio.run(_provision(tmp_path, monkeypatch))
    result = _run_main(database_url)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert f"batch={BATCH_ID}" in result.stderr
    assert "registry ready" in result.stderr


def test_p02_settings_override_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """门槛 ⑩（P02）：环境变量覆盖默认值（本批**未**新增 Settings 字段）。"""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./data/p22_gate.db")
    overridden = Settings()
    assert overridden.log_level == "DEBUG"
    assert overridden.database_url == "sqlite+aiosqlite:///./data/p22_gate.db"


def test_task_store_is_tenant_scoped(engine: AsyncEngine) -> None:
    """门槛 ⑩（`docs/02` §11 / §48）：`store.get(task_id, other_tenant)` → `None`。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            store = build_task_store(uow.session)
            task = await _task_in(uow.session, status=str(TaskStatus.QUEUED))
            assert isinstance(store, TaskStoreRepository)
            assert await store.get(task.id, OTHER_TENANT_ID) is None
            assert await store.get(task.id, TENANT_ID) is not None
            assert await store.get("no-such-task", TENANT_ID) is None

    asyncio.run(_run())


# ===== ⑪ 质量与结构（`docs/07` §3.1 / §3.3 / §14）=====


def test_no_vendor_names_in_app() -> None:
    """门槛 ⑪（`docs/07` §14.2）：`app/` 内厂商名 0 处（大小写不敏感）。"""
    hits = [
        f"{path.relative_to(REPO_ROOT).as_posix()}:{vendor}"
        for path in sorted(APP_DIR.rglob("*.py"))
        for vendor in VENDOR_NAMES
        if vendor.lower() in path.read_text(encoding="utf-8").lower()
    ]
    assert hits == []


def test_domain_layer_has_no_sqlalchemy() -> None:
    """门槛 ⑪（`docs/07` §14.1）：`app/domain/` 不得引用框架 / SDK。"""
    for path in sorted((APP_DIR / "domain").glob("*.py")):
        modules = _imported_modules(path)
        assert [
            name for name in modules if name.split(".")[0] in FORBIDDEN_FRAMEWORK_ROOTS
        ] == [], path.name
        assert "sqlalchemy" not in path.read_text(encoding="utf-8").lower(), path.name


def test_application_layer_does_not_depend_on_infrastructure() -> None:
    """门槛 ⑪（`docs/07` §14.1）：Application 层不得依赖 `app.infrastructure`。"""
    offenders = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in (APP_DIR / "application").rglob("*.py")
        if [name for name in _imported_modules(path) if name.startswith("app.infrastructure")]
    )
    assert offenders == []


def test_twenty_error_codes_are_not_extended() -> None:
    """门槛 ⑪（`docs/07` §11）：`app/` 内的 `STRUCTAI-xxxx` 字面量恰好是那 20 个码。"""
    declared: set[str] = set()
    for path in sorted(APP_DIR.rglob("*.py")):
        declared.update(re.findall(r"STRUCTAI-\d{4}", path.read_text(encoding="utf-8")))
    assert declared == set(ERROR_CODES_SPEC)
    assert len(ERROR_CODES_SPEC) == 20
    # 本批新增的三个异常**不**携带新码。
    for error in (TaskStateError, TaskLeaseError):
        assert error.code in ERROR_CODES_SPEC
    assert issubclass(TaskRecoveryError, StructAIError)
    assert TaskRecoveryError.code in ERROR_CODES_SPEC


def test_commit_and_rollback_only_in_unit_of_work() -> None:
    """门槛 ⑪（`docs/07` §14.4）：`commit()` / `rollback()` 只在 `unit_of_work.py`。"""
    committers = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in APP_DIR.rglob("*.py")
        if _commit_or_rollback_calls(path)
    )
    assert committers == ["app/infrastructure/database/unit_of_work.py"]
    for relative in TASK_PACKAGE_MODULES:
        assert _commit_or_rollback_calls(_relative_path(relative)) == [], relative


def test_new_task_modules_never_record_secrets() -> None:
    """门槛 ⑪（`docs/07` §14.3）：新模块**绝不**记录 secret；记录字段名不含敏感词。"""
    for relative in TASK_PACKAGE_MODULES:
        text = _relative_path(relative).read_text(encoding="utf-8").lower()
        for marker in SECRET_MARKERS:
            if marker not in text:
                continue
            # 只允许出现在**否定式**说明里（本批源码无任何敏感字段）。
            assert "不得" in text or "绝不" in text or "没有" in text, (relative, marker)
    for record in (TaskRecord, TaskStepRecord, TaskDraft, TaskStepDraft):
        names = {field.name.lower() for field in fields(record)}
        assert not (names & set(SECRET_MARKERS)), record.__name__


def test_settings_fields_are_registered_in_env_example() -> None:
    """门槛 ⑪：每个 Settings 字段都在 `.env.example` 登记（本批**未**新增字段）。"""
    registered = set(
        re.findall(
            r"^([A-Z0-9_]+)=",
            (REPO_ROOT / ".env.example").read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
    )
    declared = {name.upper() for name in Settings.model_fields}
    assert declared <= registered


def test_dependency_list_is_not_extended() -> None:
    """门槛 ⑪（`docs/07` §3.1）：依赖清单仍是既有 12 项。"""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = {
        re.split(r"[<>=!\[;]", dependency.strip())[0].strip().lower()
        for dependency in pyproject["project"]["dependencies"]
    }
    assert declared == set(FROZEN_DEPENDENCIES)


def test_container_shape_is_unchanged() -> None:
    """门槛 ⑪（`docs/02` §33）：容器字段仍为冻结形状（任务引擎**不**进容器）。"""
    names = [field.name for field in fields(AppContainer)]
    assert tuple(names) == CONTAINER_FIELDS_SPEC
    assert [name for name in names if "task" in name] == []
    assert DEFAULT_MAX_RETRIES == 0


def test_task_package_matches_the_frozen_directory() -> None:
    """门槛 ⑪（`docs/07` §3.3）：`app/application/task/` 的文件集合与规范目录一致。"""
    present = {path.name for path in TASK_DIR.glob("*.py")}
    assert present == set(TASK_MODULES) | {"__init__.py"}
    for relative in TASK_PACKAGE_MODULES:
        assert _relative_path(relative).is_file(), relative
    assert REPOSITORIES_DIR.joinpath("task.py").is_file()


# ===== ⑫ Worker 执行链（`docs/02` §15 / §40 / §50 / §77 / §78 / §91；`docs/07` §10.2）=====


class _TimeoutThenSucceedExecutor:
    """前 `fail_first` 次执行「挂住」、之后成功的 `TaskExecutor` 替身（`docs/02` §78）。

    用于验证 `docs/02` §77 / §78 的重试链：`attempt 1 → timeout`、`attempt 2 → timeout`、
    `attempt 3 → success`（`max_retries = 2` 时共 **3** 次尝试）。
    """

    def __init__(self, *, fail_first: int = 2, delay: float = 1.5) -> None:
        """绑定「挂住」的尝试次数与单次挂住时长（秒）。"""
        self.calls: list[str] = []
        self._fail_first = fail_first
        self._delay = delay

    async def execute(
        self,
        task: TaskRecord,
        *,
        context: object | None = None,
    ) -> Mapping[str, Any]:
        """前若干次睡过等待上限（触发 `asyncio.wait_for` 超时），之后立即返回结果。"""
        self.calls.append(task.id)
        if len(self.calls) <= self._fail_first:
            await asyncio.sleep(self._delay)
        return {"ok": True}


def test_worker_executes_a_queued_task_to_completion(engine: AsyncEngine) -> None:
    """门槛 ⑫（`docs/02` §40 / §50 / §91）：租约 → `RUNNING` → 执行 → 100 → `COMPLETED` → 释放。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            store = build_task_store(uow.session)
            queue = TaskQueue()
            executor = _RecordingExecutor()
            worker = TaskWorker(
                worker_id="worker-a",
                queue=queue,
                store=store,
                lease=_lease(uow.session),
                executor=executor,
                progress=_progress(uow.session),
            )
            task = await _task_in(uow.session, status=str(TaskStatus.QUEUED))
            worker.register(task)

            returned = await worker.run_task(task.id, "worker-a")

            assert returned.status == str(TaskStatus.COMPLETED)
            assert returned.progress == 100
            assert returned.result_json is not None
            assert json.loads(returned.result_json) == {"ok": True}
            assert returned.started_at is not None
            assert returned.completed_at is not None
            # 执行时任务**已经**是 `RUNNING`（`docs/02` §50：先 RUNNING 再 Adapter）。
            assert executor.statuses == [str(TaskStatus.RUNNING)]
            assert executor.calls == [task.id]
            # 租约已释放（`docs/02` §51 的 `release()`；回读以避开 `finally` 之前的快照）。
            after = await store.get(task.id, TENANT_ID)
            assert after is not None
            assert after.lease_owner is None
            assert after.lease_until is None
            assert worker.registered_tenants() == {task.id: TENANT_ID}

    asyncio.run(_run())


def test_worker_releases_lock_and_lease_on_exception(engine: AsyncEngine) -> None:
    """门槛 ⑫（`docs/02` §41 / §50 / §65）：执行抛异常 → `FAILED` + 归一化信封 + **无**锁泄漏。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            store = build_task_store(uow.session)
            locks = ResourceLockManager()
            worker = TaskWorker(
                worker_id="worker-a",
                queue=TaskQueue(),
                store=store,
                lease=_lease(uow.session),
                executor=_RecordingExecutor(error=AdapterError("native failure")),
                locks=locks,
                lock_policy=LockPolicy(),
                operations=_registry(),
            )
            task = await _task_in(uow.session, status=str(TaskStatus.QUEUED))
            worker.register(task)

            returned = await worker.run_task(task.id, "worker-a")

            assert returned.status == str(TaskStatus.FAILED)
            assert returned.error_json is not None
            envelope = json.loads(returned.error_json)
            assert envelope["code"] == "STRUCTAI-6000"
            assert envelope["type"] == "ADAPTER_ERROR"
            # `AdapterError.retryable` 为 False → 不进入重试链（`docs/03` §124）。
            assert returned.retry_count == 0
            # 异常路径**必须**释放锁与租约（`docs/02` §41：「禁止异常情况下不释放」）。
            assert await locks.held_count() == 0
            after = await store.get(task.id, TENANT_ID)
            assert after is not None
            assert after.lease_owner is None

    asyncio.run(_run())


def test_worker_times_out_and_retries_until_success(engine: AsyncEngine) -> None:
    """门槛 ⑫（`docs/02` §77 / §78）：`timeout`、`timeout`、成功 → 共 3 次尝试后 `COMPLETED`。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            store = build_task_store(uow.session)
            queue = TaskQueue()
            executor = _TimeoutThenSucceedExecutor(fail_first=2, delay=1.5)
            worker = TaskWorker(
                worker_id="worker-a",
                queue=queue,
                store=store,
                lease=_lease(uow.session),
                executor=executor,
                default_timeout_seconds=1,
            )
            task = await _task_in(
                uow.session,
                status=str(TaskStatus.QUEUED),
                max_retries=2,
            )
            worker.register(task)

            record = task
            for _ in range(4):  # 上限 3 次尝试；多一次用于暴露「重试链未收敛」
                record = await worker.run_task(task.id, "worker-a")
                if record.status == str(TaskStatus.COMPLETED):
                    break

            assert record.status == str(TaskStatus.COMPLETED)
            assert len(executor.calls) == 3
            assert record.retry_count == 2
            assert record.result_json is not None
            assert json.loads(record.result_json) == {"ok": True}
            # 重试链每次都会把任务放回队列（`docs/02` §42 的「重排」）。
            assert queue.qsize() == 2

    asyncio.run(_run())


def test_retry_exhaustion_ends_in_failed(engine: AsyncEngine) -> None:
    """门槛 ⑫（`docs/02` §77 / §78）：`max_retries = 0` 时超时**不得**无限重试 → `FAILED`。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            store = build_task_store(uow.session)
            executor = _TimeoutThenSucceedExecutor(fail_first=9, delay=1.5)
            worker = TaskWorker(
                worker_id="worker-a",
                queue=TaskQueue(),
                store=store,
                lease=_lease(uow.session),
                executor=executor,
                default_timeout_seconds=1,
            )
            task = await _task_in(uow.session, status=str(TaskStatus.QUEUED), max_retries=0)
            worker.register(task)

            returned = await worker.run_task(task.id, "worker-a")

            assert returned.status == str(TaskStatus.FAILED)
            assert returned.retry_count == 0
            assert len(executor.calls) == 1
            assert returned.error_json is not None
            envelope = json.loads(returned.error_json)
            assert envelope["code"] == "STRUCTAI-5100"
            assert envelope["type"] == "TASK_TIMEOUT"
            after = await store.get(task.id, TENANT_ID)
            assert after is not None
            assert after.lease_owner is None

    asyncio.run(_run())


def test_engine_retry_requeues_a_failed_task(engine: AsyncEngine) -> None:
    """门槛 ⑫（`docs/02` §77）：`TaskEngine.retry` → `FAILED → RETRYING → QUEUED` 并重新入队。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            store = build_task_store(uow.session)
            queue = TaskQueue()
            task_engine = TaskEngine(store, queue=queue, operations=_registry())
            task = await _task_in(
                uow.session,
                status=str(TaskStatus.FAILED),
                max_retries=1,
            )

            record = await task_engine.retry(task.id, TENANT_ID)

            assert record.status == str(TaskStatus.QUEUED)
            assert record.retry_count == 1
            assert queue.qsize() == 1
            item = await queue.get()
            assert item.task_id == task.id
            # 排序键用**原始** `created_at`（`docs/02` §17：priority + created_at）。
            assert item.created_at == task.created_at

    asyncio.run(_run())


def test_engine_retry_stops_at_the_budget(engine: AsyncEngine) -> None:
    """门槛 ⑫（`docs/02` §77）：重试预算耗尽 → `STRUCTAI-5000`（`retry_exhausted`），不无限重试。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            store = build_task_store(uow.session)
            queue = TaskQueue()
            task_engine = TaskEngine(store, queue=queue, operations=_registry())
            task = await _task_in(
                uow.session,
                status=str(TaskStatus.FAILED),
                fields={"retry_count": 1},
                max_retries=1,
            )

            with pytest.raises(TaskError) as excinfo:
                await task_engine.retry(task.id, TENANT_ID)

            assert excinfo.value.code == "STRUCTAI-5000"
            assert excinfo.value.details["reason"] == "retry_exhausted"
            assert queue.qsize() == 0
            after = await store.get(task.id, TENANT_ID)
            assert after is not None
            assert after.status == str(TaskStatus.FAILED)
            assert after.retry_count == 1

    asyncio.run(_run())


def test_worker_respects_the_scheduler_admission(engine: AsyncEngine) -> None:
    """门槛 ⑫（`docs/02` §18）：并发额度已满 → **不**执行（状态保持 `QUEUED`，租约被释放）。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            store = build_task_store(uow.session)
            scheduler = Scheduler(limits=ConcurrencyLimits(global_limit=1))
            holder = ConcurrencyRequest(task_id="holder-task", tenant_id=TENANT_ID, user_id="")
            assert (await scheduler.try_acquire(holder)).admitted is True

            executor = _RecordingExecutor()
            worker = TaskWorker(
                worker_id="worker-a",
                queue=TaskQueue(),
                store=store,
                lease=_lease(uow.session),
                executor=executor,
                scheduler=scheduler,
            )
            task = await _task_in(uow.session, status=str(TaskStatus.QUEUED))
            worker.register(task)

            returned = await worker.run_task(task.id, "worker-a")

            assert returned.status == str(TaskStatus.QUEUED)
            assert executor.calls == []
            after = await store.get(task.id, TENANT_ID)
            assert after is not None
            assert after.lease_owner is None
            assert after.started_at is None
            await scheduler.release(holder)

    asyncio.run(_run())


def test_worker_loop_stops_gracefully_on_shutdown(engine: AsyncEngine) -> None:
    """门槛 ⑫（`docs/02` §15 / §38）：`stop()` + `queue.shutdown()` → `run()` **自然返回**。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            store = build_task_store(uow.session)
            queue = TaskQueue()
            worker = TaskWorker(
                worker_id="worker-a",
                queue=queue,
                store=store,
                lease=_lease(uow.session),
                executor=_RecordingExecutor(),
                poll_interval=0.01,
            )
            task = await _task_in(uow.session, status=str(TaskStatus.QUEUED))
            worker.register(task)
            await queue.put(task.id, task.priority, created_at=task.created_at)

            runner = asyncio.create_task(worker.run())
            for _ in range(300):
                await asyncio.sleep(0.01)
                current = await store.get(task.id, TENANT_ID)
                if current is not None and current.status == str(TaskStatus.COMPLETED):
                    break

            worker.stop()
            await queue.shutdown()
            await asyncio.wait_for(runner, timeout=5)

            assert runner.done()
            assert runner.exception() is None
            assert worker.running is False
            after = await store.get(task.id, TENANT_ID)
            assert after is not None
            assert after.status == str(TaskStatus.COMPLETED)

    asyncio.run(_run())


def test_worker_rejects_an_unregistered_task(engine: AsyncEngine) -> None:
    """门槛 ⑫（`docs/02` §11）：未登记的 `task_id` → `STRUCTAI-5000`（**不**静默跳过）。"""

    async def _run() -> None:
        factory = create_session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            worker = TaskWorker(
                worker_id="worker-a",
                queue=TaskQueue(),
                store=build_task_store(uow.session),
                lease=_lease(uow.session),
                executor=_RecordingExecutor(),
            )
            with pytest.raises(TaskError) as excinfo:
                await worker.run_task("00000000-0000-4000-8000-000000000000", "worker-a")
            assert excinfo.value.code == "STRUCTAI-5000"
            assert excinfo.value.details["reason"] == "unknown_task"

    asyncio.run(_run())
