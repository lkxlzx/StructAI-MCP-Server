"""P21 验收测试：Idempotency（`docs/07` §12 P21 / §10.3；`docs/02` §28–§35 / §57 / §86 / §87）。

验收点（与续接提示词的 ①–⑧ 一一对应）：

① 原子性（`docs/07` §10.3；`docs/02` §28 / §32 / §35）：**必须** `INSERT` 抢占，
   **禁止** `SELECT → INSERT`；唯一键 `(tenant_id, idempotency_key)` 由**数据库约束**
   保证；并发同键只允许一个成功（SQL 级钩子断言语句顺序与写动词）；
② 重放（`docs/02` §33 / §34 / §57 / §86）：同键 + 同 `request_hash` → 返回**已有**响应，
   **不**重复执行 Adapter（用 MockAdapter 的调用计数 + store 版本证明）；
③ 冲突（`docs/02` §32 / §35 / §87；`docs/07` §10.3 / §11）：同键 + 不同 `request_hash` →
   **`STRUCTAI-1300`**（Concurrency Conflict）；
④ 顺序冻结（`docs/07` §9）：**Idempotency（第 14 步）先于 Lock（第 15 步）**，
   `EXECUTION_PIPELINE_ORDER` 不得改动；
⑤ 事务边界（`docs/02` §16）：只有 `UnitOfWork` 能 commit / rollback；
   失败路径不得留下半条记录（`reserve` 失败 / 冲突 / 异常后逐条核验）；
⑥ 回归：既有 **292 项 pytest 不得回退**（由整轮 `pytest -q` 覆盖；本文件只补
   `app.main` 两条 + P04 建表 / `SELECT 1` + P02 覆盖行为）；
⑦ 质量：`ruff` / `mypy` 覆盖；本文件额外断言依赖清单**未扩**、容器形状**未变**、
   Application 层**不依赖** `app.infrastructure`、新模块**不得 `commit`**；
⑧ 红线：`app/` 内厂商名 0 处、`app/domain/` 无 SQLAlchemy、不新增 `STRUCTAI-xxxx` 码、
   **绝不记录 secret**、Settings 字段全部登记于 `.env.example`。

⚠️ 本文件里的「规范原文副本」（§33 的摘要配方 / §28 的三方法 / §9 的 26 步顺序 /
20 码清单 / 依赖清单）**故意不**从被测模块取：若断言只与被测常量比较，
「常量被改错」与「实现被改错」会一起通过（同源循环）。
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import inspect
import json
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import event, func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.execution import (
    EXECUTION_PIPELINE_ORDER,
    ExecutionContext,
    ExecutionContextFactory,
    IdempotencyOutcome,
    IdempotencyService,
    canonical_payload,
    decode_response,
    encode_response,
    hash_payload,
)
from app.application.security.context import IdentityContext
from app.config.settings import Settings
from app.container import BATCH_ID, AppContainer
from app.domain.errors import ConcurrencyConflictError, StructAIError
from app.domain.protocols import (
    IdempotencyRecord,
    IdempotencyReservation,
    IdempotencyStore,
)
from app.infrastructure.adapters import MockAdapter
from app.infrastructure.database import Base, create_engine, create_session_factory
from app.infrastructure.database.models import IdempotencyRecordORM, TenantORM
from app.infrastructure.database.repositories import build_idempotency_store
from app.infrastructure.database.seed import ADMIN_PASSWORD_ENV, seed
from app.infrastructure.database.unit_of_work import UnitOfWork

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
EXECUTION_DIR = APP_DIR / "application" / "execution"
REPOSITORIES_DIR = APP_DIR / "infrastructure" / "database" / "repositories"

VENDOR_NAMES = ("MIDAS", "CSI", "ANSYS")
"""`docs/07` §14.2：`app/` 内禁止出现的厂商名。"""

TEST_PASSWORD = "P21-Idempotency-验收-口令-9f2c"
"""测试用口令（非真实 secret，仅存在于测试进程内）。"""

TENANT_ID = "11111111-1111-4111-8111-111111111111"
"""本文件使用的租户标识（`docs/02` §31：幂等键与租户绑定）。"""

OTHER_TENANT_ID = "22222222-2222-4222-8222-222222222222"
"""第二个租户：用于证明幂等键**不跨租户**串用（`docs/02` §31）。"""

SessionFactory = async_sessionmaker[AsyncSession]
"""会话工厂类型别名（`docs/02` §15）。"""


# ===== 规范原文副本（`docs/02` §28 / §31 / §33 / §86 / §87；`docs/07` §9 / §11）=====

IDEMPOTENCY_HASH_FIELDS_SPEC = ("tool", "operation", "parameters", "context", "dry_run")
"""`docs/02` §33 的 `hash_request` 载荷字段（逐字抄写）。"""

IDEMPOTENCY_STORE_METHODS_SPEC = ("reserve", "existing", "complete")
"""`docs/02` §28（`source9`）的 `IdempotencyService` 方法集 + §34 / §35 的读取口径。"""

IDEMPOTENCY_UNIQUE_KEY_SPEC = ("tenant_id", "idempotency_key")
"""`docs/02` §28 / §31 / §35 与 `docs/07` §10.3 的唯一键（逐字抄写）。"""

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

PIPELINE_STEP_NUMBERS_SPEC = {
    "Confirmation": 13,
    "Idempotency": 14,
    "Concurrency / Resource Lock": 15,
}
"""`docs/07` §9 的第 13–15 步（门槛 ④ 的判据）。"""

IDEMPOTENCY_RECORD_COLUMNS_SPEC = (
    "id",
    "tenant_id",
    "idempotency_key",
    "request_hash",
    "response_json",
)
"""P04 落地的 `idempotency_records` 契约列（`docs/07` §4.3 #23）。"""

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

TWENTY_CODE_CONTRACT = (
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

CONFLICT_CODE_SPEC = "STRUCTAI-1300"
"""`docs/07` §10.3 / §11：幂等键冲突的码（「乐观锁失败 / **幂等键冲突**」）。"""

REPLAY_SCENARIO_SPEC = ("same key", "same request", "只执行一次")
"""`docs/02` §98 / §86 的重放场景与期望（逐字抄写）。"""

CONFLICT_SCENARIO_SPEC = ("same key", "different request", "拒绝")
"""`docs/02` §98 / §87 的冲突场景与期望（逐字抄写）。"""

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

P21_MODULES = (
    "app/application/execution/idempotency.py",
    "app/infrastructure/database/repositories/idempotency.py",
)
"""本批新增的两个模块（`docs/02` §37 给出前者的路径；后者是它的持久化实现）。"""

FORBIDDEN_FRAMEWORK_ROOTS = ("sqlalchemy", "fastapi", "mcp", "httpx")
"""`docs/07` §14.1：`app/domain/` 与 Application 层不得依赖的框架 / SDK。"""


# ===== 夹具与辅助 =====


@pytest.fixture
async def seeded_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncEngine]:
    """临时 SQLite + 建表 + 真实 Seed（`docs/02` §15 / §36 / §43–§46）。"""
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, TEST_PASSWORD)
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p21_idempotency.db').as_posix()}"
    engine = create_engine(database_url, echo=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await seed(create_session_factory(engine))
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def sessions(seeded_engine: AsyncEngine) -> SessionFactory:
    """已配备库上的会话工厂（`docs/02` §15）。"""
    return create_session_factory(seeded_engine)


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


def _idempotency_statements(statements: Sequence[str]) -> list[str]:
    """只保留作用于 `idempotency_records` 的语句（去掉 SAVEPOINT 等事务控制语句）。"""
    return [
        statement.lstrip().split(None, 1)[0].upper()
        for statement in statements
        if "idempotency_records" in statement.lower()
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
    name: str = "p21_main.db",
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


def _service(session: AsyncSession) -> IdempotencyService:
    """装配一个绑定给定会话的幂等服务（`docs/02` §28 / §33）。"""
    return IdempotencyService(build_idempotency_store(session))


def _identity(*, user_id: str, tenant_id: str) -> IdentityContext:
    """构造服务端身份（`docs/02` §26）。"""
    return IdentityContext(user_id=UUID(user_id), tenant_id=UUID(tenant_id))


def _context(identity: IdentityContext) -> ExecutionContext:
    """由服务端身份构造执行上下文（`docs/02` §5）。"""
    return ExecutionContextFactory().create(identity)


def _request(**overrides: Any) -> dict[str, Any]:
    """构造一个 §33 口径的请求（`tool` / `operation` / `parameters` / `context` / `dry_run`）。"""
    identity = _identity(user_id=TENANT_ID, tenant_id=TENANT_ID)
    request: dict[str, Any] = {
        "tool": "engineering_model_build",
        "operation": "BUILD.COLUMN",
        "parameters": {"base_node": {"x": 0.0, "y": 0.0, "z": 0.0}, "height": 6.0},
        "context": _context(identity),
        "dry_run": False,
    }
    request.update(overrides)
    return request


class _CountingAdapter(MockAdapter):
    """记录 `execute` 调用次数的 Mock Adapter（`docs/02` §86 的「不执行 Adapter」证据）。"""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    async def execute(
        self,
        operation: str,
        parameters: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """计数后委托真实 handler（`docs/02` §48）。"""
        self.calls.append(str(operation))
        return await super().execute(operation, parameters, context)


async def _pipeline_attempt(
    session: AsyncSession,
    adapter: _CountingAdapter,
    *,
    tenant_id: str,
    key: str,
    request: Mapping[str, Any],
) -> tuple[str, Mapping[str, Any] | None]:
    """模拟「第 14 步 Idempotency → 第 18 步 Adapter → 第 22 步 Persist Result」。

    Returns:
        `(outcome, response)`：`outcome` 为 `RESERVED` / `REPLAY`。
    """
    service = _service(session)
    request_hash = service.hash_request(request)
    decision = await service.begin(
        tenant_id=tenant_id,
        idempotency_key=key,
        request_hash=request_hash,
    )
    if decision.replayed:
        return (decision.outcome.value, decision.response)

    result = await adapter.execute(
        str(request["operation"]),
        dict(request["parameters"]),  # type: ignore[arg-type]
        _context(_identity(user_id=tenant_id, tenant_id=tenant_id)),
    )
    await service.complete(decision.record.id, result)
    return (decision.outcome.value, result)


async def _row_count(session: AsyncSession) -> int:
    """`idempotency_records` 当前行数。"""
    result = await session.execute(select(func.count()).select_from(IdempotencyRecordORM))
    return int(result.scalar_one())


async def _seeded_tenant_id(session: AsyncSession) -> str:
    """Seed 落库的唯一租户 id。"""
    result = await session.execute(select(TenantORM.id))
    return str(result.scalars().first())


# ===== ① 原子性（`docs/07` §10.3；`docs/02` §28 / §32 / §35）=====


def test_unique_key_is_the_frozen_tenant_and_key_pair(seeded_engine: AsyncEngine) -> None:
    """门槛 ①：唯一键由**数据库约束**保证，且列名与 P04 契约逐列一致。"""

    async def _run() -> None:
        async with seeded_engine.connect() as connection:
            unique_keys = set(
                await connection.run_sync(
                    lambda sync_connection: [
                        tuple(item["column_names"])
                        for item in sa_inspect(sync_connection).get_unique_constraints(
                            "idempotency_records"
                        )
                    ]
                )
            )
        assert IDEMPOTENCY_UNIQUE_KEY_SPEC in unique_keys, unique_keys

        columns = tuple(column.name for column in IdempotencyRecordORM.__table__.columns)
        assert set(IDEMPOTENCY_RECORD_COLUMNS_SPEC) <= set(columns)
        assert tuple(field.name for field in fields(IdempotencyRecord)) == (
            IDEMPOTENCY_RECORD_COLUMNS_SPEC
        )

    asyncio.run(_run())


def test_reserve_issues_insert_without_a_preceding_select(seeded_engine: AsyncEngine) -> None:
    """门槛 ①：`reserve` **必须**先 `INSERT` 抢占 —— 禁止 `SELECT → INSERT`（§35）。"""

    async def _run() -> None:
        statements = _recorded_statements(seeded_engine)
        async with UnitOfWork.from_session_factory(create_session_factory(seeded_engine)) as uow:
            service = _service(uow.session)
            reservation = await service.reserve(TENANT_ID, "atomic-key", "hash-a")
            assert reservation.created is True
            assert reservation.record.response_json is None

        verbs = _idempotency_statements(statements)
        assert verbs == ["INSERT"], verbs
        assert "SELECT" not in verbs
        assert _write_verbs(statements) == ["INSERT"]

    asyncio.run(_run())


def test_reserve_reads_back_the_existing_record_on_conflict(
    seeded_engine: AsyncEngine,
) -> None:
    """门槛 ①（§35）：唯一键冲突 → 捕获 `IntegrityError` → 回读既有记录。"""

    async def _run() -> None:
        factory = create_session_factory(seeded_engine)
        async with UnitOfWork.from_session_factory(factory) as first:
            service = _service(first.session)
            created = await service.reserve(TENANT_ID, "conflict-key", "hash-a")
            assert created.created is True
            record_id = created.record.id

        statements = _recorded_statements(seeded_engine)
        async with UnitOfWork.from_session_factory(factory) as second:
            service = _service(second.session)
            existing = await service.reserve(TENANT_ID, "conflict-key", "hash-a")
            assert existing.created is False
            assert existing.record.id == record_id
            assert existing.record.request_hash == "hash-a"
            assert existing.record.request_hash == "hash-a"
            # 回读路径的语句顺序：INSERT（被唯一约束拒绝）→ SELECT（回读）。
            verbs = _idempotency_statements(statements)
            assert verbs == ["INSERT", "SELECT"], verbs
            assert await _row_count(second.session) == 1

    asyncio.run(_run())


def test_concurrent_reserve_of_the_same_key_allows_exactly_one_winner(
    seeded_engine: AsyncEngine,
) -> None:
    """门槛 ①：两个协程并发抢同一个键 → **只允许一个成功**（`docs/02` §99 / §108）。"""

    async def _run() -> None:
        factory = create_session_factory(seeded_engine)
        statements = _recorded_statements(seeded_engine)
        barrier = asyncio.Barrier(2)

        async def _attempt() -> bool:
            async with UnitOfWork.from_session_factory(factory) as uow:
                service = _service(uow.session)
                await barrier.wait()
                reservation = await service.reserve(TENANT_ID, "race-key", "hash-a")
                return reservation.created

        outcomes = await asyncio.gather(_attempt(), _attempt())
        assert outcomes.count(True) == 1, outcomes
        assert outcomes.count(False) == 1, outcomes

        # 两条路径都**先** `INSERT`；只有输家回读（`SELECT` 出现在 `INSERT` 之后）。
        verbs = _idempotency_statements(statements)
        # 首条针对 `idempotency_records` 的语句**必须**是 `INSERT`（无 `SELECT` 先行）。
        assert verbs[0] == "INSERT", verbs
        assert verbs.count("INSERT") == 2, verbs

        async with factory() as session:
            assert await _row_count(session) == 1

    asyncio.run(_run())


def test_idempotency_key_is_scoped_to_the_tenant(seeded_engine: AsyncEngine) -> None:
    """门槛 ①（`docs/02` §31）：Key 与 `tenant` 绑定 —— 同键不同租户互不影响。"""

    async def _run() -> None:
        factory = create_session_factory(seeded_engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            service = _service(uow.session)
            first = await service.reserve(TENANT_ID, "shared-key", "hash-a")
            second = await service.reserve(OTHER_TENANT_ID, "shared-key", "hash-b")
            assert first.created is True
            assert second.created is True
            assert first.record.id != second.record.id
            assert await _row_count(uow.session) == 2

    asyncio.run(_run())


# ===== ② 重放（`docs/02` §33 / §34 / §57 / §86）=====


def test_replay_returns_the_stored_response_without_executing_the_adapter(
    seeded_engine: AsyncEngine,
) -> None:
    """门槛 ②（`docs/02` §86）：同键 + 同请求 → 返回既有响应，**不执行** Adapter。"""

    async def _run() -> None:
        factory = create_session_factory(seeded_engine)
        adapter = _CountingAdapter()
        request = _request()

        async with UnitOfWork.from_session_factory(factory) as first:
            outcome, response = await _pipeline_attempt(
                first.session,
                adapter,
                tenant_id=TENANT_ID,
                key="column-001",
                request=request,
            )
            assert outcome == IdempotencyOutcome.RESERVED.value
            assert response == {"node_ids": [1, 2], "element_ids": [1]}
            nodes_after_first = len(adapter.store.all_nodes())

        async with UnitOfWork.from_session_factory(factory) as second:
            replay, cached = await _pipeline_attempt(
                second.session,
                adapter,
                tenant_id=TENANT_ID,
                key="column-001",
                request=request,
            )
            assert replay == IdempotencyOutcome.REPLAY.value
            assert cached == response

        assert adapter.calls == ["BUILD.COLUMN"], adapter.calls
        assert len(adapter.store.all_nodes()) == nodes_after_first
        assert REPLAY_SCENARIO_SPEC == ("same key", "same request", "只执行一次")

    asyncio.run(_run())


def test_check_returns_the_stored_response_only_for_a_matching_request(
    seeded_engine: AsyncEngine,
) -> None:
    """门槛 ②（`docs/02` §34）：`check` 只读；不存在 → `None`，命中 → 既有响应。"""

    async def _run() -> None:
        factory = create_session_factory(seeded_engine)
        request = _request()
        async with UnitOfWork.from_session_factory(factory) as uow:
            service = _service(uow.session)
            digest = service.hash_request(request)
            assert await service.check(TENANT_ID, "check-key", digest) is None

            reservation = await service.reserve(TENANT_ID, "check-key", digest)
            assert reservation.created is True
            assert await service.check(TENANT_ID, "check-key", digest) is None  # 尚未完成
            assert await service.complete(reservation.record.id, {"ok": True}) is True
            assert await service.check(TENANT_ID, "check-key", digest) == {"ok": True}
            assert await service.get_existing(TENANT_ID, "check-key") is not None

    asyncio.run(_run())


def test_hash_request_follows_the_docs_02_section_33_recipe() -> None:
    """门槛 ②（`docs/02` §33）：摘要 = `sha256(json.dumps(payload, sort_keys, separators))`。"""
    service = IdempotencyService(_NullStore())
    request = _request()

    assert IDEMPOTENCY_HASH_FIELDS_SPEC == ("tool", "operation", "parameters", "context", "dry_run")

    digest = service.hash_request(request)
    assert len(digest) == 64
    assert re.fullmatch(r"[0-9a-f]{64}", digest) is not None

    # 独立复算：只用标准库按 `docs/02` §33 的配方重算一遍（规范化口径见本批裁决 2）。
    def _spec_default(value: Any) -> Any:
        """把 dataclass / `Enum` / `UUID` / 集合转成 `json` 可序列化的形式。"""
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, (set, frozenset)):
            return sorted(str(item) for item in value)
        if is_dataclass(value) and not isinstance(value, type):
            return {field.name: getattr(value, field.name) for field in fields(value)}
        raise TypeError(f"not canonical: {type(value).__name__}")

    payload = {name: request[name] for name in IDEMPOTENCY_HASH_FIELDS_SPEC}
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_spec_default,
    )
    assert digest == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert '"context"' in canonical

    # 规范化是**确定性**的：键序不同、`context` 是 dataclass 而不是 dict，摘要都必须一致。
    reordered = {name: request[name] for name in reversed(list(request))}
    assert service.hash_request(reordered) == digest
    assert hash_payload({"b": 1, "a": [1, {"d": 2, "c": 3}]}) == hash_payload(
        {"a": [1, {"c": 3, "d": 2}], "b": 1}
    )
    assert canonical_payload({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_hash_request_changes_when_the_request_changes() -> None:
    """门槛 ②（`docs/02` §32）：`height` 6 → 8 必须产生不同摘要（§87 的场景）。"""
    service = IdempotencyService(_NullStore())
    base = _request()
    taller = _request(parameters={"base_node": {"x": 0.0, "y": 0.0, "z": 0.0}, "height": 8.0})

    assert service.hash_request(base) != service.hash_request(taller)
    assert service.hash_request(base) != service.hash_request(_request(dry_run=True))
    assert service.hash_request(base) != service.hash_request(
        _request(operation="MODEL.NODE.QUERY")
    )


def test_hash_request_rejects_a_request_missing_a_frozen_field() -> None:
    """门槛 ②（`docs/02` §33）：缺字段**不得**静默兜底成空值。"""
    service = IdempotencyService(_NullStore())
    incomplete = {"tool": "t", "operation": "BUILD.COLUMN", "parameters": {}}
    with pytest.raises(TypeError) as excinfo:
        service.hash_request(incomplete)
    assert "context" in str(excinfo.value)


def test_response_encoding_round_trips_and_is_stable() -> None:
    """门槛 ②（`docs/02` §64）：响应快照 → JSON → 重放，逐字段稳定。"""
    response = {"element_ids": [1], "node_ids": [1, 2], "meta": {"z": 6.0, "x": 0.0}}
    encoded = encode_response(response)
    assert encoded == '{"element_ids":[1],"meta":{"x":0.0,"z":6.0},"node_ids":[1,2]}'
    assert decode_response(encoded) == {
        "element_ids": [1],
        "meta": {"x": 0.0, "z": 6.0},
        "node_ids": [1, 2],
    }
    assert encode_response(decode_response(encoded)) == encoded


# ===== ③ 冲突（`docs/02` §32 / §35 / §87；`docs/07` §10.3 / §11）=====


def test_conflict_on_the_same_key_with_a_different_request_is_structai_1300(
    seeded_engine: AsyncEngine,
) -> None:
    """门槛 ③（`docs/02` §87）：同键 + 不同请求 → `STRUCTAI-1300`，且 Adapter 不得执行。"""

    async def _run() -> None:
        factory = create_session_factory(seeded_engine)
        adapter = _CountingAdapter()
        first_request = _request()

        async with UnitOfWork.from_session_factory(factory) as uow:
            outcome, response = await _pipeline_attempt(
                uow.session,
                adapter,
                tenant_id=TENANT_ID,
                key="column-001",
                request=first_request,
            )
            assert outcome == IdempotencyOutcome.RESERVED.value
            assert response is not None

        # `docs/02` §87：第一次 height = 6，第二次 height = 8。
        second_request = _request(
            parameters={"base_node": {"x": 0.0, "y": 0.0, "z": 0.0}, "height": 8.0}
        )
        async with UnitOfWork.from_session_factory(factory) as uow:
            service = _service(uow.session)
            digest = service.hash_request(second_request)
            assert digest != service.hash_request(first_request)
            with pytest.raises(ConcurrencyConflictError) as excinfo:
                await service.begin(
                    tenant_id=TENANT_ID,
                    idempotency_key="column-001",
                    request_hash=digest,
                )
            error = excinfo.value
            assert error.code == CONFLICT_CODE_SPEC
            assert error.to_dict()["code"] == "STRUCTAI-1300"
            assert isinstance(error, StructAIError)
            assert error.details == {"stage": "idempotency", "reason": "request_hash_mismatch"}
            # 绝不回显幂等键原文 / 绝不出现 secret（`docs/07` §14.3）。
            assert "column-001" not in json.dumps(error.to_dict(), ensure_ascii=False)
            assert await _row_count(uow.session) == 1

            stored = await service.get_existing(TENANT_ID, "column-001")
            assert stored is not None
            assert stored.request_hash == service.hash_request(first_request)
            assert stored.response_json == encode_response(dict(response or {}))

        assert adapter.calls == ["BUILD.COLUMN"], adapter.calls
        assert CONFLICT_SCENARIO_SPEC == ("same key", "different request", "拒绝")

    asyncio.run(_run())


def test_check_raises_structai_1300_on_a_request_hash_mismatch(
    seeded_engine: AsyncEngine,
) -> None:
    """门槛 ③（`docs/02` §34）：`check` 的摘要不匹配同样落 `STRUCTAI-1300`。"""

    async def _run() -> None:
        factory = create_session_factory(seeded_engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            service = _service(uow.session)
            await service.reserve(TENANT_ID, "check-conflict", "hash-a")
            with pytest.raises(ConcurrencyConflictError) as excinfo:
                await service.check(TENANT_ID, "check-conflict", "hash-b")
            assert excinfo.value.code == CONFLICT_CODE_SPEC
            assert excinfo.value.details["reason"] == "request_hash_mismatch"

    asyncio.run(_run())


def test_in_flight_duplicate_is_structai_1300_and_never_executes(
    seeded_engine: AsyncEngine,
) -> None:
    """门槛 ③（本批裁决 3）：同键同摘要但尚无响应 → `STRUCTAI-1300`（`in_flight`）。"""

    async def _run() -> None:
        factory = create_session_factory(seeded_engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            service = _service(uow.session)
            first = await service.begin(
                tenant_id=TENANT_ID,
                idempotency_key="in-flight",
                request_hash="hash-a",
            )
            assert first.reserved is True
            assert first.replayed is False

            with pytest.raises(ConcurrencyConflictError) as excinfo:
                await service.begin(
                    tenant_id=TENANT_ID,
                    idempotency_key="in-flight",
                    request_hash="hash-a",
                )
            assert excinfo.value.code == CONFLICT_CODE_SPEC
            assert excinfo.value.details["reason"] == "in_flight"
            assert await _row_count(uow.session) == 1

            stored = await service.get_existing(TENANT_ID, "in-flight")
            assert stored is not None
            assert stored.response_json is None

    asyncio.run(_run())


def test_complete_never_overwrites_an_existing_response(seeded_engine: AsyncEngine) -> None:
    """门槛 ③：响应一经写入不可覆盖 —— 否则先后两次重放会返回不同结果（§64）。"""

    async def _run() -> None:
        factory = create_session_factory(seeded_engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            service = _service(uow.session)
            reservation = await service.reserve(TENANT_ID, "complete-once", "hash-a")
            assert await service.complete(reservation.record.id, {"first": True}) is True
            assert await service.complete(reservation.record.id, {"second": True}) is False
            assert await service.complete("missing-record", {"x": True}) is False

            stored = await service.get_existing(TENANT_ID, "complete-once")
            assert stored is not None
            assert stored.response_json == '{"first":true}'

    asyncio.run(_run())


class _NullStore:
    """最小 `IdempotencyStore` 替身（只用于不触库的纯函数用例）。"""

    async def reserve(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> IdempotencyReservation:
        """本替身不实现抢占（纯函数用例不会调用它）。"""
        raise NotImplementedError

    async def existing(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
    ) -> IdempotencyRecord | None:
        """本替身不实现读取。"""
        raise NotImplementedError

    async def complete(self, record_id: str, response_json: str) -> bool:
        """本替身不实现完成。"""
        raise NotImplementedError


# ===== ④ 顺序冻结（`docs/07` §9）=====


def test_pipeline_order_is_frozen_and_keeps_idempotency_before_the_lock() -> None:
    """门槛 ④：`EXECUTION_PIPELINE_ORDER` 与 `docs/07` §9 的 26 步逐条一致。"""
    assert EXECUTION_PIPELINE_ORDER == PIPELINE_ORDER_SPEC
    assert len(EXECUTION_PIPELINE_ORDER) == 26

    for step, number in PIPELINE_STEP_NUMBERS_SPEC.items():
        assert EXECUTION_PIPELINE_ORDER.index(step) == number - 1, step

    idempotency = EXECUTION_PIPELINE_ORDER.index("Idempotency")
    assert idempotency < EXECUTION_PIPELINE_ORDER.index("Concurrency / Resource Lock")
    assert EXECUTION_PIPELINE_ORDER.index("Confirmation") < idempotency
    assert idempotency < EXECUTION_PIPELINE_ORDER.index("Capability Check")
    assert EXECUTION_PIPELINE_ORDER.index("Postconditions") < EXECUTION_PIPELINE_ORDER.index(
        "Release Lock"
    )


def test_idempotency_step_never_reaches_for_the_lock_or_the_adapter() -> None:
    """门槛 ④：幂等步骤**不**抢锁、**不**碰 Adapter（依赖方向与顺序一致）。"""
    modules = _imported_modules(EXECUTION_DIR / "idempotency.py")
    assert [name for name in modules if "lock" in name] == []
    assert [name for name in modules if name.startswith("app.infrastructure")] == []


# ===== ⑤ 事务边界（`docs/02` §16；`docs/07` §14.4）=====


def test_only_unit_of_work_commits_or_rollbacks() -> None:
    """门槛 ⑤：`app/` 内 `commit()` / `rollback()` 调用**只**允许出现在 `UnitOfWork`。"""
    committers = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in APP_DIR.rglob("*.py")
        if _commit_or_rollback_calls(path)
    )
    assert committers == ["app/infrastructure/database/unit_of_work.py"]


def test_p21_modules_never_commit_or_rollback() -> None:
    """门槛 ⑤：本批两个新模块不得自己决定事务（边界归 `UnitOfWork`）。"""
    for relative in P21_MODULES:
        assert _commit_or_rollback_calls(_relative_path(relative)) == [], relative


def test_rollback_after_a_reserve_leaves_no_half_record(seeded_engine: AsyncEngine) -> None:
    """门槛 ⑤：抢占后异常 → 回滚 → 库里**没有**半条记录（`docs/02` §43 Rollback Test）。"""

    async def _run() -> None:
        factory = create_session_factory(seeded_engine)
        with pytest.raises(RuntimeError, match="adapter exploded"):
            async with UnitOfWork.from_session_factory(factory) as uow:
                service = _service(uow.session)
                reservation = await service.reserve(TENANT_ID, "rollback-key", "hash-a")
                assert reservation.created is True
                raise RuntimeError("adapter exploded")

        async with factory() as session:
            assert await _row_count(session) == 0

    asyncio.run(_run())


def test_rollback_after_a_completion_keeps_the_reservation_without_a_response(
    seeded_engine: AsyncEngine,
) -> None:
    """门槛 ⑤：已完成但后置步骤失败 → 回滚 → 只留「已抢占、无响应」的干净状态。"""

    async def _run() -> None:
        factory = create_session_factory(seeded_engine)
        async with UnitOfWork.from_session_factory(factory) as first:
            service = _service(first.session)
            reservation = await service.reserve(TENANT_ID, "half-key", "hash-a")
            assert reservation.created is True
            record_id = reservation.record.id

        with pytest.raises(RuntimeError, match="postconditions failed"):
            async with UnitOfWork.from_session_factory(factory) as second:
                service = _service(second.session)
                assert await service.complete(record_id, {"ok": True}) is True
                raise RuntimeError("postconditions failed")

        async with factory() as session:
            service = _service(session)
            stored = await service.get_existing(TENANT_ID, "half-key")
            assert stored is not None
            assert stored.response_json is None
            assert await _row_count(session) == 1

    asyncio.run(_run())


def test_conflict_path_leaves_no_half_record(seeded_engine: AsyncEngine) -> None:
    """门槛 ⑤：冲突路径只回读 —— 行数不变、既有记录逐列不变（`docs/02` §35）。"""

    async def _run() -> None:
        factory = create_session_factory(seeded_engine)
        async with UnitOfWork.from_session_factory(factory) as first:
            service = _service(first.session)
            reservation = await service.reserve(TENANT_ID, "conflict-clean", "hash-a")
            record_id = reservation.record.id

        with pytest.raises(ConcurrencyConflictError):
            async with UnitOfWork.from_session_factory(factory) as second:
                service = _service(second.session)
                await service.begin(
                    tenant_id=TENANT_ID,
                    idempotency_key="conflict-clean",
                    request_hash="hash-b",
                )

        async with factory() as session:
            service = _service(session)
            stored = await service.get_existing(TENANT_ID, "conflict-clean")
            assert stored is not None
            assert stored.id == record_id
            assert stored.request_hash == "hash-a"
            assert stored.response_json is None
            assert await _row_count(session) == 1

    asyncio.run(_run())


# ===== ⑥ 回归（`docs/07` §12 P01 / P02 / P04；`docs/08` §3）=====


def test_batch_id_is_the_p21_batch_marker() -> None:
    """门槛 ⑥：容器批次号已推进到 P21。"""
    assert BATCH_ID == "P21"


def test_main_exits_zero_with_empty_stdout_on_an_unprovisioned_database(
    tmp_path: Path,
) -> None:
    """门槛 ⑥：未配备库上 `python -m app.main` 退出码 0 且 **stdout 0 字节**。"""
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p21_unprovisioned.db').as_posix()}"
    result = _run_main(database_url)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_main_exits_zero_with_empty_stdout_on_a_provisioned_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ⑥：已配备库上同样退出码 0 且 **stdout 0 字节**（`registry ready`）。"""
    database_url = asyncio.run(_provision(tmp_path, monkeypatch))
    result = _run_main(database_url)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_p04_tables_and_select_one_are_not_regressed(seeded_engine: AsyncEngine) -> None:
    """门槛 ⑥（P04）：建表 **24** 张（本批**未改表**）+ `SELECT 1` → 1。"""

    async def _run() -> None:
        async with seeded_engine.connect() as connection:
            names = set(
                await connection.run_sync(
                    lambda sync_connection: sa_inspect(sync_connection).get_table_names()
                )
            )
            assert names == set(TWENTY_FOUR_TABLES_SPEC)
            assert len(Base.metadata.tables) == 24
            result = await connection.exec_driver_sql("SELECT 1")
            assert result.scalar_one() == 1

    asyncio.run(_run())


def test_p02_settings_override_is_not_regressed(monkeypatch: pytest.MonkeyPatch) -> None:
    """门槛 ⑥（P02）：环境变量覆盖默认值（本批**未**新增 Settings 字段）。"""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./data/p21_gate.db")
    monkeypatch.setenv("LOCK_DEFAULT_TIMEOUT_SECONDS", "77")

    overridden = Settings()

    assert overridden.log_level == "DEBUG"
    assert overridden.database_url == "sqlite+aiosqlite:///./data/p21_gate.db"
    assert overridden.lock_default_timeout_seconds == 77


# ===== ⑦ 质量与结构（`docs/07` §3.1 / §3.3 / §14）=====


def test_technology_stack_is_frozen() -> None:
    """门槛 ⑦：依赖清单未扩（`docs/07` §3.1 / §3.2：不得引入新依赖）。"""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = {
        re.split(r"[<>=!\[;]", dependency.strip())[0].strip().lower()
        for dependency in pyproject["project"]["dependencies"]
    }
    assert declared == set(FROZEN_DEPENDENCIES)


def test_container_shape_stays_frozen() -> None:
    """门槛 ⑦：容器字段仍为 `docs/02` §33 的冻结形状（幂等**不**进容器）。"""
    names = [field.name for field in fields(AppContainer)]
    assert names == [
        "settings",
        "runtime_config",
        "engine",
        "session_factory",
        "operation_registry",
        "execution_service",
        "started",
    ]
    assert [name for name in names if "idempot" in name] == []


def test_p21_modules_exist_and_are_exported() -> None:
    """门槛 ⑦：本批两个模块落在 `docs/07` §3.3 的冻结结构里并已导出。"""
    for relative in P21_MODULES:
        assert _relative_path(relative).is_file(), relative

    assert {path.name for path in EXECUTION_DIR.glob("*.py")} >= {"idempotency.py"}
    assert {path.name for path in REPOSITORIES_DIR.glob("*.py")} >= {"idempotency.py"}

    from app.infrastructure.database.repositories import (
        IdempotencyStoreRepository,
        build_idempotency_store,
    )

    assert IdempotencyStoreRepository.__name__ == "IdempotencyStoreRepository"
    assert callable(build_idempotency_store)


def test_application_layer_does_not_depend_on_infrastructure() -> None:
    """门槛 ⑦（`docs/07` §14.1）：Application 层不得依赖 `app.infrastructure`。"""
    offenders = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in (APP_DIR / "application").rglob("*.py")
        if [name for name in _imported_modules(path) if name.startswith("app.infrastructure")]
    )
    assert offenders == []


def test_idempotency_store_contract_is_structurally_satisfied() -> None:
    """门槛 ⑦：`IdempotencyStore` 契约恰好是 §28 / §34 的三个方法，且实现逐一对上。"""
    declared = {name for name in vars(IdempotencyStore) if not name.startswith("_")}
    assert declared == set(IDEMPOTENCY_STORE_METHODS_SPEC)

    store = build_idempotency_store(object())  # type: ignore[arg-type]
    for name in IDEMPOTENCY_STORE_METHODS_SPEC:
        assert inspect.iscoroutinefunction(getattr(type(store), name)), name


# ===== ⑧ 红线（`docs/07` §11 / §14）=====


def test_twenty_code_contract_is_not_extended() -> None:
    """门槛 ⑧：`app/` 内出现的 `STRUCTAI-xxxx` 字面量恰好是那 20 个码。"""
    declared: set[str] = set()
    for path in sorted(APP_DIR.rglob("*.py")):
        declared.update(re.findall(r"STRUCTAI-\d{4}", path.read_text(encoding="utf-8")))
    assert declared == set(TWENTY_CODE_CONTRACT)
    assert len(TWENTY_CODE_CONTRACT) == 20
    assert CONFLICT_CODE_SPEC in TWENTY_CODE_CONTRACT


def test_red_lines_vendor_names_and_domain_purity() -> None:
    """门槛 ⑧：`app/` 内厂商名 0 处；`app/domain/` 内无 SQLAlchemy。"""
    vendor_hits = [
        f"{path.relative_to(REPO_ROOT).as_posix()}:{vendor}"
        for path in sorted(APP_DIR.rglob("*.py"))
        for vendor in VENDOR_NAMES
        if vendor.lower() in path.read_text(encoding="utf-8").lower()
    ]
    assert vendor_hits == []

    domain_hits = [
        path.name
        for path in sorted((APP_DIR / "domain").glob("*.py"))
        if "sqlalchemy" in path.read_text(encoding="utf-8").lower()
    ]
    assert domain_hits == []


def test_domain_stays_free_of_frameworks() -> None:
    """门槛 ⑧（`docs/07` §14.1）：`app/domain/` 不得引用框架 / SDK。"""
    for path in sorted((APP_DIR / "domain").glob("*.py")):
        modules = _imported_modules(path)
        assert [
            name for name in modules if name.split(".")[0] in FORBIDDEN_FRAMEWORK_ROOTS
        ] == [], path.name


def test_settings_fields_are_registered_in_env_example() -> None:
    """门槛 ⑧：每个 Settings 字段都在 `.env.example` 登记（本批未新增字段）。"""
    registered = set(
        re.findall(
            r"^([A-Z0-9_]+)=",
            (REPO_ROOT / ".env.example").read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
    )
    declared = {name.upper() for name in Settings.model_fields}
    assert declared <= registered


def test_idempotency_records_never_store_secrets(seeded_engine: AsyncEngine) -> None:
    """门槛 ⑧：**绝不记录 secret**（`docs/07` §14.3）—— 全表文本逐列扫描。"""

    async def _run() -> None:
        factory = create_session_factory(seeded_engine)
        adapter = _CountingAdapter()
        async with UnitOfWork.from_session_factory(factory) as uow:
            outcome, _ = await _pipeline_attempt(
                uow.session,
                adapter,
                tenant_id=TENANT_ID,
                key="scan-key-001",
                request=_request(),
            )
            assert outcome == IdempotencyOutcome.RESERVED.value

        async with factory() as session:
            rows = (await session.execute(select(IdempotencyRecordORM))).scalars().all()
            assert len(rows) == 1
            dumped = json.dumps(
                [
                    {
                        column.name: str(getattr(row, column.name))
                        for column in IdempotencyRecordORM.__table__.columns
                    }
                    for row in rows
                ],
                ensure_ascii=False,
            )
            lowered = dumped.lower()
            assert TEST_PASSWORD not in dumped
            for marker in ("password", "token", "api_key", "api-key", "secret", "private"):
                assert marker not in lowered, marker
            assert re.fullmatch(r"[0-9a-f]{64}", rows[0].request_hash) is not None

    asyncio.run(_run())
