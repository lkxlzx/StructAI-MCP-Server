"""P29–P35 验收 · Infrastructure（`docs/07` §12 P29–P35 / §13；`docs/02` §29–§41 / §55–§66）。

门槛（`docs/08` §4 的本批提示词 ①–⑦ / ⑨ / ⑪）
------------------------------------------------
① **Artifact**（`docs/02` §29 / §33 / §55–§56；`docs/07` §4.3 #21）：`ArtifactStorage` 契约
   `put` / `get` / `delete`；写入 → `sha256` checksum → 读回校验
   `checksum(original) == checksum(read)`（§84）；数据库只存
   `artifact_id` / `storage_backend` / `storage_key` / `mime_type` / `size` / `checksum`，
   **不**存内容。
② **Document / Model / Result**（`docs/02` §30 / §32 / §33 / §57）：只做生命周期与**规范化**，
   不承载工程语义；`DocumentService` 的 `lifecycle_state` 取值见 `DocumentStatus`。
③ **Event Bus**（`docs/02` §34 / §38 / §58）：`InProcessEventBus` 满足 Domain 契约 `EventBus`；
   任务类事件由 P22–P28 的 `ProgressReporter` 等发布点接入；为 `docs/02` §45 的
   `TaskProgress → MCP progress notification` 保留**唯一**接入点。
④ **Audit**（`docs/02` §39 / §44 / §65；`docs/07` §4.3 #24）：append-only + **Hash Chain**，
   篡改**可检测**；审计写入与业务写**同一** `UnitOfWork`；**绝不**记录 secret。
⑤ **Trace / Metrics / Health**（`docs/02` §41–§43 / §62–§64）：`trace_id` 贯穿；指标**不落**
   secret；readiness 未就绪 → **不得** READY（`docs/07` §14.4）；`python -m app.main`
   退出码 0 且 **stdout 0 字节**。
⑥ **Quota / Rate Limit**（`docs/02` §36 / §40）+ **Backup / Restore**（§41 / §66）：
   超限一律复用既有 **20 码**（**不新增**）；Backup 最小可用且不写 secret。
⑦ **Secret / Credential Provider**（`docs/02` §21 / §26 / §35）：凭据**只**经运行环境注入，
   **绝不**落库 / 落日志 / 落文件。
⑨ **回归**：建表 **24** 张 + `SELECT 1` → 1；P02 覆盖行为。
⑪ **红线**：`grep -ri midas app/` = 0；`app/domain/` 内无 SQLAlchemy；Application 层不依赖
   `app.infrastructure`；`STRUCTAI-xxxx` 恰好 **20** 码；Settings 字段 ⊆ `.env.example`；
   `commit` / `rollback` 只在 `unit_of_work.py`。

测试风格（沿用 `tests/test_task_engine_p22_p28.py`）：规范原文副本**写在测试文件里**。
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.execution.context import ExecutionContextFactory
from app.application.security.context import IdentityContext
from app.application.services.artifact import ArtifactService
from app.application.services.backup import (
    BACKUP_ARTIFACTS_DIR,
    BACKUP_DATABASE_NAME,
    BACKUP_MANIFEST_NAME,
    BACKUP_VERSION,
    BackupService,
)
from app.application.services.document import (
    DOCUMENT_LIFECYCLE_ORDER,
    DOCUMENT_STATUS_EDGES,
    INFORMATION_ONLY_OPERATION,
    DocumentService,
)
from app.application.services.model import ASSIGN_OPERATIONS, QUERY_OPERATIONS, ModelService
from app.application.services.quota import (
    QUOTA_DIMENSIONS,
    QUOTA_METRICS,
    QuotaLimits,
    QuotaService,
    StaticQuotaPolicySource,
)
from app.application.services.result import ResultService, decode_cursor, encode_cursor, paginate
from app.config.settings import Settings
from app.container import BATCH_ID, build_execution_runtime, register_health_checkers
from app.domain.enums import AuditResult, DocumentStatus, HealthStatus, QuotaDimension
from app.domain.errors import (
    ArtifactError,
    InternalError,
    StructAIError,
    TaskError,
    TenantAccessDeniedError,
)
from app.domain.events import TaskProgress
from app.infrastructure.database.base import Base
from app.infrastructure.database.models.artifact import ArtifactORM
from app.infrastructure.database.models.audit import AuditRecordORM
from app.infrastructure.database.models.document import DocumentORM
from app.infrastructure.database.repositories import (
    build_artifact_store,
    build_audit_store,
    build_document_store,
    build_document_version_store,
)
from app.infrastructure.database.seed import ADMIN_PASSWORD_ENV, seed
from app.infrastructure.database.session import create_engine, create_session_factory
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.infrastructure.events import (
    STANDARD_EVENT_TYPES,
    EventDispatcher,
    InMemoryEventRecordStore,
    InProcessEventBus,
    from_record,
    to_record_draft,
)
from app.infrastructure.locks.in_memory import InMemoryLock
from app.infrastructure.notifications import NotificationService
from app.infrastructure.secrets import EnvironmentCredentialProvider, looks_sensitive
from app.infrastructure.storage import LocalFilesystemStorage, sanitize_filename, sha256_bytes
from app.observability import (
    ALLOWED_LABELS,
    AUDIT_ACTIONS,
    HIGH_CARDINALITY_LABELS,
    LIVENESS_PATH,
    NOT_READY,
    READINESS_CHECKS,
    READY,
    STANDARD_METRICS,
    STANDARD_SPAN_KINDS,
    AuditService,
    CallableHealthChecker,
    HealthRegistry,
    HealthService,
    MetricsService,
    TraceService,
    audit_payload,
    canonical_json,
    compute_entry_hash,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

TENANT_ID = "33333333-3333-4333-8333-333333333333"
OTHER_TENANT_ID = "44444444-4444-4444-8444-444444444444"
PROJECT_ID = "55555555-5555-4555-8555-555555555555"
USER_ID = "66666666-6666-4666-8666-666666666666"

ERROR_CODES_SPEC: frozenset[str] = frozenset(
    {
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
    }
)
"""`docs/07` §11 的 **20** 码契约（逐条抄写；**不**从被测模块导入）。"""

ARTIFACT_COLUMNS_SPEC: frozenset[str] = frozenset(
    {
        "id",
        "task_id",
        "storage_backend",
        "storage_key",
        "mime_type",
        "size",
        "checksum",
        "created_at",
        "updated_at",
    }
)
"""`docs/07` §4.3 #21 的 `artifacts` 冻结列集合（含两个时间列）。"""

DOCUMENT_COLUMNS_SPEC: frozenset[str] = frozenset(
    {
        "id",
        "project_id",
        "model_id",
        "name",
        "path",
        "status",
        "created_at",
        "updated_at",
    }
)
"""`docs/07` §4.3 #15 的 `documents` 冻结列集合（含两个时间列）。"""

AUDIT_COLUMNS_SPEC: frozenset[str] = frozenset(
    {
        "id",
        "tenant_id",
        "user_id",
        "action",
        "resource",
        "result",
        "previous_hash",
        "entry_hash",
        "created_at",
        "updated_at",
    }
)
"""`docs/07` §4.3 #24 的 `audit_records` 冻结列集合（含两个时间列）。"""

TWENTY_FOUR_TABLES_SPEC: tuple[str, ...] = (
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
"""`docs/07` §4.3 的 24 张表（逐条抄写）。"""

AUDIT_ACTIONS_SPEC: tuple[str, ...] = (
    "LOGIN",
    "LOGOUT",
    "DOCUMENT.NEW",
    "DOCUMENT.OPEN",
    "DOCUMENT.SAVE",
    "DOCUMENT.CLOSE",
    "MODEL.CREATE",
    "MODEL.UPDATE",
    "MODEL.DELETE",
    "ANALYSIS.RUN",
    "DESIGN.RUN",
    "TASK.CANCEL",
    "ADAPTER.CONNECT",
    "ADAPTER.DISCONNECT",
    "PERMISSION.DENIED",
    "CONFIRMATION.REQUIRED",
)
"""`docs/02` §8.3 的 16 个必须记录的动作名（逐条抄写）。"""

STANDARD_METRICS_SPEC: tuple[str, ...] = (
    "structai_requests_total",
    "structai_request_duration_seconds",
    "structai_task_total",
    "structai_task_duration_seconds",
    "structai_task_failed_total",
    "structai_active_tasks",
    "structai_adapter_requests_total",
    "structai_adapter_errors_total",
    "structai_adapter_duration_seconds",
    "structai_mcp_connections",
    "structai_artifacts_total",
    "structai_artifact_bytes_total",
    "structai_events_total",
    "structai_event_publish_failed_total",
    "structai_audit_total",
)
"""`docs/02` §14 的 15 个标准指标名（逐条抄写）。"""

VENDOR_NAMES: tuple[str, ...] = ("MIDAS", "CSI", "ANSYS", "SAP2000", "ETABS", "OpenSees")
SECRET_MARKERS: tuple[str, ...] = (
    "password",
    "api_key",
    "api-key",
    "access_token",
    "refresh_token",
    "private_key",
    "secret",
    "credential",
)
"""`docs/02` §9 禁止写入审计的字段（逐条抄写）。"""

SETTINGS_FIELD_SPEC: tuple[str, ...] = (
    "app_name",
    "app_version",
    "environment",
    "debug",
    "log_level",
    "database_url",
    "sql_echo",
    "registry_root",
    "mcp_transport",
    "host",
    "port",
    "task_worker_count",
    "artifact_root",
    "session_expire_seconds",
    "task_default_timeout_seconds",
    "lock_default_timeout_seconds",
    "capability_cache_seconds",
)
"""`docs/02` §5 / §5.1 的 Settings 字段（P02 已冻结；本批**未新增**）。"""

FROZEN_DEPENDENCIES: tuple[str, ...] = (
    "fastapi",
    "uvicorn",
    "pydantic",
    "pydantic-settings",
    "sqlalchemy",
    "alembic",
    "aiosqlite",
    "argon2-cffi",
    "httpx",
    "jsonschema",
    "structlog",
    "mcp",
)
"""`docs/07` §3.1 / §3.2 的冻结依赖清单（本批**不得**扩）。"""


async def _seeded_engine(tmp_path: Path) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """临时库 + 建表 + seed（`docs/02` §15 / §44）。"""

    os.environ.setdefault("STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD", "P29-P35-验收-口令-51a3")
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'p29_p35.db').as_posix()}",
        artifact_root=str(tmp_path / "artifacts"),
    )
    engine = create_engine(settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, create_session_factory(engine)


def _identity(tenant_id: str = TENANT_ID, user_id: str = USER_ID) -> IdentityContext:
    """服务端身份（`docs/02` §26）。"""
    from uuid import UUID

    return IdentityContext(
        user_id=UUID(user_id),
        tenant_id=UUID(tenant_id),
        roles=("system_admin",),
        authentication_method="PASSWORD",
    )


def _context(identity: IdentityContext | None = None) -> object:
    """执行上下文（`docs/02` §5）。"""
    return ExecutionContextFactory().create(identity or _identity())


async def _tenant_of_project(project_id: str) -> str | None:
    """项目 → 租户（`docs/02` §30：文档写入需要租户载体）。"""
    return TENANT_ID


def _run_main(database_url: str) -> subprocess.CompletedProcess[str]:
    """以子进程跑 `python -m app.main`（门槛：退出码 0 + stdout 0 字节）。"""

    environment = dict(os.environ)
    environment["DATABASE_URL"] = database_url
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "app.main"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


# ===== ① Artifact（`docs/02` §29 / §33 / §55–§56 / §84）=====


def test_artifact_write_read_back_and_checksum_round_trip(tmp_path: Path) -> None:
    """门槛 ①（`docs/02` §84）：写入 → sha256 → 读回校验；库里**不**存内容。"""

    async def _run() -> None:
        engine, factory = await _seeded_engine(tmp_path)
        storage = LocalFilesystemStorage(tmp_path / "artifacts")
        payload = b"P29 artifact payload \xe4\xb8\xad\xe6\x96\x87"
        async with UnitOfWork.from_session_factory(factory) as uow:
            service = ArtifactService(build_artifact_store(uow.session), storage)
            record = await service.create(
                tenant_id=TENANT_ID,
                data=payload,
                mime_type="application/json",
                project_id=PROJECT_ID,
            )
            assert record.checksum == sha256_bytes(payload)
            assert record.size == len(payload)
            assert record.storage_backend == "local"
            assert record.storage_key.startswith(f"{TENANT_ID}/{PROJECT_ID}/")
            assert record.storage_key.endswith("/payload")
            assert record.id == record.storage_key.split("/")[2]
            read_back = await service.read(record.id, tenant_id=TENANT_ID)
            assert hashlib.sha256(read_back).hexdigest() == record.checksum
            assert await service.verify(record) is True
            rows = (await uow.session.execute(select(ArtifactORM))).scalars().all()
            assert len(rows) == 1
            assert set(ArtifactORM.__table__.columns.keys()) == ARTIFACT_COLUMNS_SPEC
            blob = "".join(str(getattr(rows[0], column)) for column in ARTIFACT_COLUMNS_SPEC)
            assert "P29 artifact payload" not in blob, "库里不得存产物内容"
            assert await service.delete(record.id, tenant_id=TENANT_ID) is True
            assert not await storage.exists(record.storage_key)
            assert (await uow.session.execute(select(ArtifactORM))).scalars().all() == []
            # 二次删除：行已不存在 → 与 `info()` **同形**的租户拒绝（`docs/02` §48 不泄露存在性）
            with pytest.raises(TenantAccessDeniedError) as second_delete:
                await service.delete(record.id, tenant_id=TENANT_ID)
            assert second_delete.value.code == "STRUCTAI-4200"
        await engine.dispose()

    asyncio.run(_run())


def test_artifact_tenant_isolation_and_path_traversal_are_rejected(tmp_path: Path) -> None:
    """门槛 ①（`docs/02` §48 / §56）：跨租户**同形**拒绝；路径穿越被拒。"""

    async def _run() -> None:
        engine, factory = await _seeded_engine(tmp_path)
        storage = LocalFilesystemStorage(tmp_path / "artifacts")
        async with UnitOfWork.from_session_factory(factory) as uow:
            service = ArtifactService(build_artifact_store(uow.session), storage)
            record = await service.create(
                tenant_id=TENANT_ID,
                data=b"tenant-scoped",
                mime_type="text/plain",
            )
            with pytest.raises(TenantAccessDeniedError) as foreign:
                await service.read(record.id, tenant_id=OTHER_TENANT_ID)
            assert foreign.value.code == "STRUCTAI-4200"
            assert foreign.value.message == "Tenant access denied"
            with pytest.raises(TenantAccessDeniedError) as missing:
                await service.read("99999999-9999-4999-8999-999999999999", tenant_id=TENANT_ID)
            assert missing.value.code == foreign.value.code
            assert missing.value.message == foreign.value.message
            assert missing.value.details == foreign.value.details
            for bad in ("../escape/payload", "/absolute/payload", "a\\b\\payload", "a//payload"):
                with pytest.raises(ArtifactError) as rejected:
                    storage.path_for(bad)
                assert rejected.value.code == "STRUCTAI-6200"
            # 清洗规则（`docs/02` §3.4）：剥目录成分 → 转义 → 剥前导点 → 空串回落
            assert sanitize_filename("../../etc/passwd") == "passwd"
            assert sanitize_filename("..\\..\\windows\\cmd.exe") == "cmd.exe"
            assert sanitize_filename("...") == "artifact"
        await engine.dispose()

    asyncio.run(_run())


# ===== ② Document / Model / Result（`docs/02` §30 / §32 / §33 / §57）=====


def test_document_lifecycle_uses_document_status_and_keeps_versions(tmp_path: Path) -> None:
    """门槛 ②（`docs/02` §30 / §57）：生命周期取值见 `DocumentStatus`；SAVE 只追加版本。"""

    async def _run() -> None:
        engine, factory = await _seeded_engine(tmp_path)
        storage = LocalFilesystemStorage(tmp_path / "artifacts")
        context = _context()
        async with UnitOfWork.from_session_factory(factory) as uow:
            artifacts = ArtifactService(build_artifact_store(uow.session), storage)
            service = DocumentService(
                build_document_store(uow.session),
                build_document_version_store(),
                artifacts=artifacts,
                tenant_of_project=_tenant_of_project,
            )
            created = await service.new(
                context,
                "P30 Document",
                "ENGINEERING_FILE",
                project_id=PROJECT_ID,
            )
            assert created.status == str(DocumentStatus.NEW)
            opened = await service.open(context, created.id)
            assert opened.status == str(DocumentStatus.OPEN)
            version = await service.save(context, created.id, b"first content")
            assert version.version == 1
            assert version.checksum == sha256_bytes(b"first content")
            second = await service.save(context, created.id, b"second content")
            assert second.version == 2
            info = await service.info(context, created.id)
            assert info.current_version == 2
            assert info.status == str(DocumentStatus.OPEN), "SAVE 保持 OPEN"
            assert info.document_type == "ENGINEERING_FILE"
            assert service.lifecycle_order() == DOCUMENT_LIFECYCLE_ORDER
            assert INFORMATION_ONLY_OPERATION == "INFO"
            assert set(DOCUMENT_STATUS_EDGES) == {item.value for item in DocumentStatus}
            await service.close(context, created.id)
            closed = await service.info(context, created.id)
            assert closed.status == str(DocumentStatus.CLOSED)
            assert set(DocumentORM.__table__.columns.keys()) == DOCUMENT_COLUMNS_SPEC
        await engine.dispose()

    asyncio.run(_run())


def test_model_service_never_executes_writes_and_result_service_only_normalizes() -> None:
    """门槛 ②（`docs/02` §48 / §49 / §90）：读走 ModelService，写**只**产出参数；结果只做信封。"""
    calls: list[tuple[str, Mapping[str, object]]] = []

    class _Source:
        async def query(
            self,
            *,
            software_instance_id: str,
            operation: str,
            parameters: Mapping[str, object],
            context: object,
        ) -> Mapping[str, object]:
            calls.append((operation, parameters))
            return {"items": [], "pagination": {"has_more": False, "next_cursor": None}}

    async def _run() -> None:
        models = ModelService(_Source())
        raw = await models.query_node(software_instance_id="i-1", context=_context())
        assert raw["pagination"]["has_more"] is False
        assert calls == [("MODEL.NODE.QUERY", {})]
        assignment = models.assign_load(element_ids=[2], load="AXIAL", fz=-500000)
        assert assignment.operation == "MODEL.LOAD.ASSIGN"
        assert assignment.parameters == {"element_ids": [2], "load": "AXIAL", "fz": -500000}
        assert len(calls) == 1, "assign_* 绝不执行（写必须走 26 步管线）"
        assert models.operations() == QUERY_OPERATIONS + ASSIGN_OPERATIONS
        results = ResultService()
        envelope = paginate([1, 2, 3], limit=2)
        assert set(envelope) == {"data", "pagination"}
        assert envelope["pagination"] == {"has_more": True, "next_cursor": encode_cursor(2)}
        assert decode_cursor(envelope["pagination"]["next_cursor"]) == 2
        assert paginate([1], limit=5)["pagination"]["next_cursor"] is None
        with pytest.raises(StructAIError) as bad_cursor:
            paginate([1], cursor="not-a-cursor")
        assert bad_cursor.value.code == "STRUCTAI-1200"
        normalized = results.normalize("MODEL.NODE.QUERY", {"data": [{"id": 1}]})
        assert normalized.data == [{"id": 1}]
        linked = results.link_artifacts(normalized, ["a", "b", "a"])
        assert linked.artifacts == ("a", "b")

    asyncio.run(_run())


# ===== ③ Event Bus（`docs/02` §34 / §38 / §45 / §58）=====


def test_in_process_event_bus_satisfies_the_domain_contract() -> None:
    """门槛 ③（`docs/02` §34 / §38）：`publish` / `subscribe` 满足 Domain 契约；坏处理器被隔离。"""

    async def _run() -> None:
        bus = InProcessEventBus()
        seen: list[str] = []

        async def _good(event: object) -> None:
            seen.append(type(event).__name__)

        async def _bad(event: object) -> None:
            raise RuntimeError("boom")

        await bus.subscribe(TaskProgress, _good)
        await bus.subscribe("TaskProgress", _bad)
        assert bus.subscriber_count() == 2
        await bus.publish(TaskProgress.create(task_id=None, progress=42))
        assert seen == ["TaskProgress"]
        assert bus.failures() == ("RuntimeError",)
        assert len(bus.published()) == 1
        assert "TaskProgress" in STANDARD_EVENT_TYPES
        strict = InProcessEventBus(raise_on_handler_error=True)
        await strict.subscribe(TaskProgress, _bad)
        with pytest.raises(RuntimeError):
            await strict.publish(TaskProgress.create(task_id=None, progress=1))
        bus.clear()
        assert bus.subscriber_count() == 0

    asyncio.run(_run())


def test_outbox_round_trip_and_dispatcher_retry_semantics() -> None:
    """门槛 ③（`docs/02` §5.4 / §6 / §42）：Outbox 往返 + `attempts++` + dead letter。"""

    async def _run() -> None:
        store = InMemoryEventRecordStore()
        event = TaskProgress.create(task_id=None, progress=10)
        draft = to_record_draft(event, tenant_id=TENANT_ID)
        record = await store.append(draft)
        assert record.status == "PENDING"
        assert record.attempts == 0
        assert record.tenant_id == TENANT_ID
        restored = from_record(record)
        assert isinstance(restored, TaskProgress)
        assert restored.progress == 10
        bus = InProcessEventBus()
        dispatcher = EventDispatcher(store, bus, max_attempts=2)
        report = await dispatcher.dispatch_pending()
        assert report.published == 1, report
        assert await store.pending() == ()
        assert store.records()[0].attempts == 1
        # 处理器永远失败 → 第 2 次尝试后成为 dead letter，不再重投。
        failing_store = InMemoryEventRecordStore()
        await failing_store.append(draft)

        async def _boom(event: object) -> None:
            raise RuntimeError("boom")

        failing_bus = InProcessEventBus(raise_on_handler_error=True)
        await failing_bus.subscribe(TaskProgress, _boom)
        retrying = EventDispatcher(failing_store, failing_bus, max_attempts=2)
        first = await retrying.dispatch_pending()
        assert first.failed == 1 and first.dead_lettered == 0, first
        second = await retrying.dispatch_pending()
        assert second.failed == 1 and second.dead_lettered == 1, second
        third = await retrying.dispatch_pending()
        assert third.skipped == 1 and third.failed == 0, third
        assert len(retrying.dead_letters()) == 1
        assert retrying.failed_count() == 2

    asyncio.run(_run())


def test_task_progress_has_a_single_notification_hook() -> None:
    """门槛 ③（`docs/02` §45）：`TaskProgress → MCP progress notification` 的**唯一**接入点。"""

    async def _run() -> None:
        bus = InProcessEventBus()
        notifications = NotificationService()
        notifications.subscribe(bus)
        await asyncio.sleep(0)  # `subscribe()` 是同步入口，把订阅调度到当前循环（见模块裁决 3）
        await bus.publish(TaskProgress.create(task_id=None, progress=55, message="halfway"))
        delivered = notifications.delivered()
        assert len(delivered) == 1, delivered
        assert delivered[0].event_type == "TaskProgress"
        # 载荷只带 `task_id` / `progress` / `message`（`docs/02` §32）；无任务时 `task_id` 为空串。
        assert delivered[0].payload == {
            "task_id": "",
            "progress": 55,
            "message": "halfway",
        }
        assert await notifications.notify_task_progress(task_id="t-1", progress=80) is True
        assert len(notifications.delivered()) == 2
        assert notifications.failures() == ()

    asyncio.run(_run())


# ===== ④ Audit（`docs/02` §39 / §44 / §65；`docs/07` §4.3 #24）=====


def test_audit_action_vocabulary_is_the_sixteen_required_names() -> None:
    """门槛 ④（`docs/02` §8.3）：必须记录的 16 个动作名**逐字**一致。"""
    assert AUDIT_ACTIONS == AUDIT_ACTIONS_SPEC
    assert len(AUDIT_ACTIONS) == 16


def test_audit_hash_chain_is_recomputable_and_detects_content_tampering(tmp_path: Path) -> None:
    """门槛 ④（`docs/02` §8 / §8.1 / §8.2 / §44）：逐条复算；内容篡改 → `hash_mismatch`。"""

    async def _run() -> None:
        engine, factory = await _seeded_engine(tmp_path)
        async with UnitOfWork.from_session_factory(factory) as uow:
            audit = AuditService(build_audit_store(uow.session), lock=InMemoryLock())
            first = await audit.record(
                action="LOGIN",
                result=str(AuditResult.SUCCESS),
                tenant_id=TENANT_ID,
                user_id=USER_ID,
            )
            second = await audit.record(
                action="DOCUMENT.NEW",
                result=str(AuditResult.SUCCESS),
                tenant_id=TENANT_ID,
                user_id=USER_ID,
                resource_type="document",
                resource_id="d-1",
            )
            third = await audit.record(
                action="PERMISSION.DENIED",
                result=str(AuditResult.DENIED),
                tenant_id=TENANT_ID,
                user_id=USER_ID,
            )
            assert first.previous_hash is None, "链首的 previous_hash 必须为空（`docs/02` §8）"
            assert second.previous_hash == first.entry_hash
            assert third.previous_hash == second.entry_hash
            # 规范原文副本（`docs/02` §8.1 / §8.2）：
            # entry_hash = sha256((previous_hash or "") + canonical_json(payload))
            payload_spec = {
                "action": "LOGIN",
                "resource": None,
                "result": str(AuditResult.SUCCESS),
                "tenant_id": TENANT_ID,
                "user_id": USER_ID,
                "previous_hash": None,
            }
            assert (
                first.entry_hash
                == hashlib.sha256(canonical_json(payload_spec).encode("utf-8")).hexdigest()
            )
            assert first.entry_hash == compute_entry_hash(None, payload_spec)
            assert (
                audit_payload(
                    action="LOGIN",
                    resource=None,
                    result=str(AuditResult.SUCCESS),
                    tenant_id=TENANT_ID,
                    user_id=USER_ID,
                    previous_hash=None,
                )
                == payload_spec
            ), "哈希载荷**恰好**是 `audit_records` 实际存在的列（见模块裁决 1）"
            assert second.resource == "document:d-1", "`resource` 规范化只有一处（见模块裁决 3）"
            verification = await audit.verify_chain(tenant_id=TENANT_ID)
            assert (verification.total, verification.valid, verification.reason) == (3, True, "")
            assert audit.records_written() == 3
            rows = (await uow.session.execute(select(AuditRecordORM))).scalars().all()
            assert len(rows) == 3
            assert set(AuditRecordORM.__table__.columns.keys()) == AUDIT_COLUMNS_SPEC
            # append-only（`docs/02` §65）：本类**不**提供任何修改 / 删除入口。
            for forbidden in ("update", "delete", "remove", "truncate"):
                assert not hasattr(audit, forbidden), forbidden
            await uow.commit()
        # 内容篡改：直接改库行（绕过服务）；用**新**会话复算，避免 identity map 缓存。
        async with UnitOfWork.from_session_factory(factory) as tamper_uow:
            await tamper_uow.session.execute(
                text("UPDATE audit_records SET action = 'TAMPERED' WHERE id = :id"),
                {"id": second.id},
            )
            await tamper_uow.commit()
        async with UnitOfWork.from_session_factory(factory) as verify_uow:
            tampered = await AuditService(build_audit_store(verify_uow.session)).verify_chain(
                tenant_id=TENANT_ID
            )
            assert tampered.total == 3
            assert tampered.valid is False
            assert tampered.first_broken_id == second.id
            assert tampered.reason == "hash_mismatch"
        await engine.dispose()

    asyncio.run(_run())


def test_audit_chain_break_is_detected_when_a_record_is_removed(tmp_path: Path) -> None:
    """门槛 ④（`docs/02` §44）：删掉中间一条 → 链断裂可检测（`chain_break`）。"""

    async def _run() -> None:
        engine, factory = await _seeded_engine(tmp_path)
        async with UnitOfWork.from_session_factory(factory) as uow:
            audit = AuditService(build_audit_store(uow.session))
            written = [
                await audit.record(
                    action=action,
                    result=str(AuditResult.SUCCESS),
                    tenant_id=TENANT_ID,
                    user_id=USER_ID,
                )
                for action in ("LOGIN", "DOCUMENT.OPEN", "LOGOUT")
            ]
            assert (await audit.verify_chain(tenant_id=TENANT_ID)).valid is True
            await uow.commit()
        async with UnitOfWork.from_session_factory(factory) as removal_uow:
            await removal_uow.session.execute(
                text("DELETE FROM audit_records WHERE id = :id"),
                {"id": written[1].id},
            )
            await removal_uow.commit()
        async with UnitOfWork.from_session_factory(factory) as verify_uow:
            broken = await AuditService(build_audit_store(verify_uow.session)).verify_chain(
                tenant_id=TENANT_ID
            )
            assert broken.total == 2
            assert broken.valid is False
            assert broken.first_broken_id == written[2].id
            assert broken.reason == "chain_break"
        await engine.dispose()

    asyncio.run(_run())


def test_audit_shares_the_business_unit_of_work_and_never_records_secrets(tmp_path: Path) -> None:
    """门槛 ④（`docs/02` §9 / §35；`docs/07` §14.3）：审计与业务写同一事务；绝不记 secret。"""

    async def _run() -> None:
        engine, factory = await _seeded_engine(tmp_path)
        secret = "p29-p35-super-secret-value"
        async with UnitOfWork.from_session_factory(factory) as uow:
            artifacts = ArtifactService(
                build_artifact_store(uow.session),
                LocalFilesystemStorage(tmp_path / "artifacts"),
            )
            record = await artifacts.create(
                tenant_id=TENANT_ID,
                data=b"business-write",
                mime_type="text/plain",
            )
            audit = AuditService(build_audit_store(uow.session))
            entry = await audit.record(
                action="MODEL.CREATE",
                result=str(AuditResult.SUCCESS),
                tenant_id=TENANT_ID,
                user_id=USER_ID,
                resource_type="engineering_model_build",
                resource_id=record.id,
                metadata={
                    "password": secret,
                    "api_key": secret,
                    "access_token": secret,
                    "secret_reference": "adapter.primary",
                    "credential_id": "c-1",
                    "authentication_method": "PASSWORD",
                },
            )
            assert entry.resource == f"engineering_model_build:{record.id}"
            rows = (await uow.session.execute(select(AuditRecordORM))).scalars().all()
            assert len(rows) == 1
            blob = "".join(
                str(getattr(row, column)) for row in rows for column in AUDIT_COLUMNS_SPEC
            )
            assert secret not in blob, "审计绝不记录 secret（`docs/07` §14.3）"
            assert "secret_reference" not in blob, "metadata 只做敏感键清洗、不落库（裁决 2）"
            await uow.rollback()
        # 回滚 → 业务写与审计写一起消失（`docs/02` §35 的事务边界）。
        async with UnitOfWork.from_session_factory(factory) as uow:
            assert (await uow.session.execute(select(ArtifactORM))).scalars().all() == []
            assert await build_audit_store(uow.session).count() == 0
        await engine.dispose()

    asyncio.run(_run())


# ===== ⑤ Trace / Metrics / Health（`docs/02` §41–§43 / §62–§64）=====


def test_trace_spans_share_one_trace_id_and_drop_sensitive_attributes() -> None:
    """门槛 ⑤（`docs/02` §10–§12 / §44 / §53 / §63）：`trace_id` 贯穿；属性**不**落 secret。"""

    async def _run() -> None:
        trace = TraceService()
        secret = "p29-p35-trace-secret"
        async with trace.span(
            "mcp_request",
            kind="MCP",
            request_id="req-1",
            attributes={"tool": "model", "api_key": secret},
        ) as root:
            child = await trace.start_span(
                "operation",
                trace_id=root.trace_id,
                parent_span_id=root.id,
                kind="OPERATION",
                attributes={"operation": "MODEL.NODE.QUERY", "authorization": secret},
            )
            finished = await trace.end_span(child)
        assert finished is not None
        assert finished.end_time is not None
        assert finished.status == "OK"
        assert child.trace_id == root.trace_id, "trace_id 必须贯穿父子 span（`docs/02` §54）"
        assert child.parent_span_id == root.id
        assert (root.kind, child.kind) == ("MCP", "OPERATION")
        spans = await trace.spans_for_trace(root.trace_id)
        assert [span.name for span in spans] == ["mcp_request", "operation"]
        assert [span.id for span in await trace.spans_for_request("req-1")] == [root.id]
        assert await trace.span_count() == 2
        for span in spans:
            assert secret not in span.attributes_json, "Trace 属性绝不记录 secret"
            assert "api_key" not in span.attributes_json
            assert "authorization" not in span.attributes_json
        assert '"tool":"model"' in root.attributes_json
        assert len(STANDARD_SPAN_KINDS) == 13
        assert (STANDARD_SPAN_KINDS[0], STANDARD_SPAN_KINDS[-1]) == ("MCP", "AUDIT")
        assert "NATIVE_API" in STANDARD_SPAN_KINDS
        # 异常路径 → `ERROR` 且继续上抛（`docs/02` §53 的 `error status`）。
        with pytest.raises(RuntimeError):
            async with trace.span("failing", kind="TOOL"):
                raise RuntimeError("boom")
        last = trace.store.spans()[-1]
        assert (last.name, last.status) == ("failing", "ERROR")
        with pytest.raises(InternalError) as bad_status:
            await trace.end_span(root, status="NOT_A_STATUS")
        assert bad_status.value.code == "STRUCTAI-7000"

    asyncio.run(_run())


def test_metrics_expose_the_fifteen_standard_names_and_drop_high_cardinality_labels() -> None:
    """门槛 ⑤（`docs/02` §13–§15 / §62）：标准指标名逐条一致；高基数标签被丢弃。"""
    metrics = MetricsService()
    assert STANDARD_METRICS == STANDARD_METRICS_SPEC
    assert len(STANDARD_METRICS) == 15
    assert ALLOWED_LABELS == ("tool", "operation", "software", "product", "adapter", "status")
    assert HIGH_CARDINALITY_LABELS == (
        "tenant_id",
        "user_id",
        "project_id",
        "request_id",
        "task_id",
    )
    metrics.counter("structai_requests_total", labels={"tool": "model", "tenant_id": TENANT_ID})
    metrics.counter("structai_requests_total", labels={"tool": "model"})
    metrics.gauge("structai_active_tasks", 3)
    metrics.observe(
        "structai_request_duration_seconds", 0.25, labels={"operation": "MODEL.NODE.QUERY"}
    )
    assert metrics.value("structai_requests_total", {"tool": "model"}) == 2
    assert metrics.value("structai_active_tasks") == 3
    assert (
        metrics.observation_count(
            "structai_request_duration_seconds", {"operation": "MODEL.NODE.QUERY"}
        )
        == 1
    )
    assert (
        metrics.observation_sum(
            "structai_request_duration_seconds", {"operation": "MODEL.NODE.QUERY"}
        )
        == 0.25
    )
    assert metrics.dropped_labels() == ("tenant_id",)
    assert metrics.names() == (
        "structai_active_tasks",
        "structai_request_duration_seconds",
        "structai_requests_total",
    )
    # 指标**不落** secret / 高基数标识（`docs/07` §14.3）。
    rendered = metrics.render()
    assert TENANT_ID not in rendered
    assert "structai_requests_total" in rendered
    metrics.reset()
    assert metrics.names() == ()


def test_container_health_checkers_never_go_ready_without_a_registry(tmp_path: Path) -> None:
    """门槛 ⑤（`docs/02` §16–§17 / §94；`docs/07` §14.4）：Registry 未装配 → **不得** READY。"""

    async def _run() -> None:
        engine, _ = await _seeded_engine(tmp_path)
        runtime = build_execution_runtime(Settings(artifact_root=str(tmp_path / "artifacts")))
        assert runtime.ready() is False, "未注入 Registry 时运行时不就绪"
        assert READINESS_CHECKS == ("database", "registry", "task_engine")
        assert LIVENESS_PATH == "/livez"
        await register_health_checkers(runtime, engine)
        assert runtime.health_registry.names() == (
            "database",
            "registry",
            "task_engine",
            "adapter_manager",
            "software_instances",
        )
        assert runtime.health.critical_checks == ("database", "registry", "task_engine")
        assert await runtime.health.liveness() == {"status": str(HealthStatus.HEALTHY)}
        readiness = await runtime.health.readiness()
        assert readiness["status"] == NOT_READY, readiness
        assert readiness["checks"]["registry"]["reason"] == "registry_not_assembled"
        assert readiness["checks"]["database"]["status"] == str(HealthStatus.HEALTHY)
        assert readiness["checks"]["task_engine"]["status"] == str(HealthStatus.HEALTHY)
        health = await runtime.health.health()
        assert health["status"] == str(HealthStatus.UNAVAILABLE)
        assert health["adapters"] == {
            "manager": {"status": str(HealthStatus.DEGRADED), "reason": "no_instances"},
            "software_instances": {
                "status": str(HealthStatus.DEGRADED),
                "reason": "no_instances",
            },
        }
        await engine.dispose()

    asyncio.run(_run())


def test_health_service_degrades_for_non_critical_failures_and_never_leaks_messages() -> None:
    """门槛 ⑤（`docs/02` §16.3 / §94）：单个软件不可用 ≠ Core DOWN；检查器**绝不**抛异常。"""

    async def _run() -> None:
        registry = HealthRegistry()
        for name in ("database", "registry", "task_engine"):
            registry.register(
                name,
                CallableHealthChecker(name, lambda: _status(str(HealthStatus.HEALTHY))),
            )
        registry.register(
            "adapter_manager",
            CallableHealthChecker(
                "adapter_manager",
                lambda: _status(str(HealthStatus.DEGRADED)),
                critical=False,
            ),
        )
        service = HealthService(
            registry,
            critical_checks=("database", "task_engine"),
            reported_checks=("database", "adapter_manager"),
        )
        assert service.critical_checks == ("database", "task_engine", "registry")
        assert (await service.readiness())["status"] == READY
        degraded = await service.health()
        assert degraded["status"] == str(HealthStatus.DEGRADED)
        assert degraded["adapters"]["manager"]["status"] == str(HealthStatus.DEGRADED)
        # 关键检查失败 → `UNAVAILABLE` 且 **不** READY。
        broken = HealthRegistry()
        broken.register(
            "database",
            CallableHealthChecker("database", lambda: _status(str(HealthStatus.UNAVAILABLE))),
        )
        broken_service = HealthService(broken, critical_checks=("database",))
        assert broken_service.critical_checks == ("database", "registry")
        assert (await broken_service.readiness())["status"] == NOT_READY
        assert (await broken_service.health())["status"] == str(HealthStatus.UNAVAILABLE)
        # 检查器抛异常 → 只暴露**类名**，绝不暴露异常消息（`docs/07` §14.3）。
        secret = "p29-p35-health-secret"
        raising = HealthRegistry()
        raising.register(
            "database",
            CallableHealthChecker("database", lambda: _raising(secret)),
        )
        raising_service = HealthService(raising, critical_checks=("database",))
        result = (await raising_service.readiness())["checks"]["database"]
        assert result == {"status": str(HealthStatus.UNAVAILABLE), "reason": "RuntimeError"}
        assert secret not in json.dumps(result, default=str)
        # 未注册的名字 → `UNAVAILABLE`，**不**静默当作可用。
        unregistered = await raising.run(["database", "not_registered"])
        assert unregistered["not_registered"] == {
            "status": str(HealthStatus.UNAVAILABLE),
            "reason": "checker_not_registered",
        }

    asyncio.run(_run())


def test_main_exits_zero_with_empty_stdout_on_an_unprovisioned_database(tmp_path: Path) -> None:
    """门槛 ⑤（`docs/02` §7 / §80）：未配备库 → 退出码 0、**stdout 0 字节**。"""
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'p29_p35_main_empty.db').as_posix()}"
    completed = _run_main(database_url)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert f"batch={BATCH_ID}" in completed.stderr
    assert "operation registry is not assembled" in completed.stderr


def test_main_exits_zero_with_empty_stdout_on_a_provisioned_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ⑤（`docs/02` §54 / §80）：已配备库 → 退出码 0、**stdout 0 字节**；Mock 实例可绑定。"""
    database_url = asyncio.run(_provision(tmp_path, monkeypatch, "p29_p35_main.db"))
    completed = _run_main(database_url)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert f"batch={BATCH_ID}" in completed.stderr


# ===== ⑥ Quota / Rate Limit（`docs/02` §36 / §40）+ Backup（§41 / §66）=====


def test_quota_refusal_reuses_structai_5000_and_adds_no_new_code() -> None:
    """门槛 ⑥（`docs/02` §36 / §40；`docs/07` §11）：超限复用既有 20 码（**不新增**）。"""

    async def _run() -> None:
        assert QUOTA_DIMENSIONS == tuple(str(item) for item in QuotaDimension)
        assert QUOTA_DIMENSIONS == ("USER", "TENANT", "AI_AGENT", "SOFTWARE_INSTANCE")
        assert QUOTA_METRICS == (
            "max_tasks",
            "max_concurrent_tasks",
            "max_api_requests",
            "max_storage",
            "max_projects",
        )
        quota = QuotaService(
            StaticQuotaPolicySource(
                QuotaLimits(
                    max_tasks=1,
                    max_concurrent_tasks=1,
                    max_api_requests=1,
                    max_storage=1,
                    max_projects=1,
                    window_seconds=60,
                )
            )
        )
        assert (
            await quota.consume_api_request(tenant_id=TENANT_ID, user_id=USER_ID)
        ).allowed is True
        refused = await quota.consume_api_request(tenant_id=TENANT_ID, user_id=USER_ID)
        assert refused.allowed is False
        with pytest.raises(TaskError) as exceeded:
            await quota.require(refused)
        assert exceeded.value.code == "STRUCTAI-5000"
        assert exceeded.value.retryable is True
        details = exceeded.value.details
        assert set(details) == {"stage", "metric", "dimension", "limit", "used", "reason"}
        assert details["stage"] == "quota"
        assert details["metric"] == refused.metric
        assert details["dimension"] == refused.dimension
        # 超限**不新增**错误码：信封只带判定字段，码本身来自既有 20 码。
        assert "STRUCTAI-5000" in ERROR_CODES_SPEC
        assert re.findall(r"STRUCTAI-\d{4}", json.dumps(details, default=str)) == []
        refusals = (
            (
                await quota.check_storage(
                    tenant_id=TENANT_ID, user_id=USER_ID, additional_bytes=10
                ),
                "max_storage",
            ),
            (
                await quota.check_projects(
                    tenant_id=TENANT_ID, user_id=USER_ID, current_projects=10
                ),
                "max_projects",
            ),
        )
        for decision, metric in refusals:
            assert decision.allowed is False
            with pytest.raises(TaskError) as refusal:
                await quota.require(decision)
            assert refusal.value.code == "STRUCTAI-5000"
            assert refusal.value.details["metric"] == metric

    asyncio.run(_run())


def test_backup_is_minimal_usable_and_writes_no_secrets(tmp_path: Path) -> None:
    """门槛 ⑥（`docs/02` §20 / §22 / §66；`docs/07` §14.3）：备份最小可用且**不写** secret。"""

    async def _run() -> None:
        engine, factory = await _seeded_engine(tmp_path)
        storage = LocalFilesystemStorage(tmp_path / "artifacts")
        async with UnitOfWork.from_session_factory(factory) as uow:
            artifacts = ArtifactService(build_artifact_store(uow.session), storage)
            record = await artifacts.create(
                tenant_id=TENANT_ID,
                data=b"backup-me",
                mime_type="text/plain",
                project_id=PROJECT_ID,
            )
        async with UnitOfWork.from_session_factory(factory) as uow:
            service = BackupService(
                database_path=tmp_path / "p29_p35.db",
                artifact_root=tmp_path / "artifacts",
                artifacts=build_artifact_store(uow.session),
                storage=storage,
                clock=lambda: datetime(2026, 10, 5, 1, 0, 0, tzinfo=UTC),
                schema_revision="rev-1",
            )
            destination = tmp_path / "backup"
            manifest = await service.create_backup(destination)
            backup_dir = destination / manifest.backup_id
            assert (backup_dir / BACKUP_MANIFEST_NAME).is_file()
            assert (backup_dir / BACKUP_DATABASE_NAME).is_file()
            copied = backup_dir / BACKUP_ARTIFACTS_DIR / record.id / "payload"
            assert copied.read_bytes() == b"backup-me"
            assert manifest.version == BACKUP_VERSION
            assert manifest.schema_revision == "rev-1"
            assert manifest.artifacts["count"] == 1
            assert manifest.artifacts["bytes"] == len(b"backup-me")
            verification = await service.verify_backup(backup_dir)
            assert (
                verification.valid,
                verification.database_ok,
                verification.artifacts_ok,
                verification.failures,
            ) == (True, True, True, ())
            # 清单**不得**出现任何凭据标记（`docs/07` §14.3）。
            listing = (backup_dir / BACKUP_MANIFEST_NAME).read_text(encoding="utf-8").lower()
            for marker in SECRET_MARKERS:
                assert marker not in listing, marker
        await engine.dispose()

    asyncio.run(_run())


# ===== ⑦ Secret / Credential Provider（`docs/02` §21 / §26 / §35）=====


def test_environment_credential_provider_injects_from_the_runtime_only() -> None:
    """门槛 ⑦（`docs/02` §26；`docs/07` §8.5 / §14.3）：凭据**只**经运行环境注入。"""

    async def _run() -> None:
        secret = "p29-p35-credential-value"
        provider = EnvironmentCredentialProvider({"STRUCTAI_SECRET_ADAPTER_PRIMARY": secret})
        assert provider.prefix == "STRUCTAI_SECRET_"
        assert (
            EnvironmentCredentialProvider.variable_name_for("adapter.primary")
            == "STRUCTAI_SECRET_ADAPTER_PRIMARY"
        )
        assert await provider.get_secret("adapter.primary") == secret
        assert provider.references() == ("adapter_primary",)
        assert secret not in repr(provider)
        # 缺失 / 空白一律 `STRUCTAI-7000`，**绝不**回落空串（见模块裁决 2）。
        with pytest.raises(InternalError) as missing:
            await provider.get_secret("adapter.secondary")
        assert missing.value.code == "STRUCTAI-7000"
        assert missing.value.details["reason"] == "secret_not_configured"
        assert secret not in json.dumps(missing.value.details, default=str)
        # 敏感引用名不进 `details`（见模块裁决 3）。
        with pytest.raises(InternalError) as sensitive:
            await provider.get_secret("db.password")
        assert looks_sensitive("db.password") is True
        assert "db.password" not in json.dumps(sensitive.value.details, default=str)
        blank = EnvironmentCredentialProvider({"STRUCTAI_SECRET_EMPTY": "   "})
        with pytest.raises(InternalError):
            await blank.get_secret("empty")
        # **没有**任何「写回凭据」的合法路径（见模块裁决 4）。
        with pytest.raises(RuntimeError):
            await provider.set_secret("adapter.primary", secret)
        with pytest.raises(RuntimeError):
            await provider.delete_secret("adapter.primary")

    asyncio.run(_run())


# ===== ⑨ 回归：建表 24 张 + `SELECT 1`（`docs/07` §4.3 / §12 P04）=====


def test_twenty_four_tables_and_select_one_are_not_regressed(tmp_path: Path) -> None:
    """门槛 ⑨（`docs/07` §4.3 / §12 P04）：24 张表**逐项未变** + `SELECT 1` → 1。"""

    async def _run() -> None:
        engine, _ = await _seeded_engine(tmp_path)
        async with engine.connect() as connection:
            names = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_table_names()
            )
            assert sorted(names) == sorted(TWENTY_FOUR_TABLES_SPEC)
            assert len(names) == 24
            result = await connection.exec_driver_sql("SELECT 1")
            assert result.scalar_one() == 1
        assert set(Base.metadata.tables) == set(TWENTY_FOUR_TABLES_SPEC)
        await engine.dispose()

    asyncio.run(_run())


# ===== ⑪ 红线（`docs/07` §2.2 / §11 / §14.1–§14.4）=====


def test_no_vendor_name_appears_under_app() -> None:
    """门槛 ⑪（`docs/07` §14.2）：`grep -ri midas app/` = 0，其余厂商名同样为 0。"""
    hits = sorted(
        f"{path.relative_to(REPO_ROOT).as_posix()}:{vendor}"
        for path in sorted(APP_DIR.rglob("*.py"))
        if not ({"midas", "etabs"} & set(path.parts))  # docs/07 §7.1：厂商专属代码的唯一豁免区
        for vendor in VENDOR_NAMES
        if vendor.lower() in path.read_text(encoding="utf-8").lower()
    )
    assert hits == []


def test_domain_layer_imports_no_framework() -> None:
    """门槛 ⑪（`docs/07` §14.1）：`app/domain/` 内**无** SQLAlchemy / FastAPI / MCP SDK / httpx。"""
    forbidden = {"sqlalchemy", "fastapi", "mcp", "httpx", "alembic", "uvicorn", "pydantic"}
    offenders = sorted(
        f"{path.name} → {name}"
        for path in sorted((APP_DIR / "domain").rglob("*.py"))
        for name in _imported_modules(path)
        if name.split(".")[0] in forbidden
    )
    assert offenders == []


def test_application_layer_imports_no_infrastructure_interfaces_or_observability() -> None:
    """门槛 ⑪（`docs/07` §2.2 / §14.1）：Application 层只依赖 Domain 的收窄契约。"""
    forbidden = ("app.infrastructure", "app.interfaces", "app.observability")
    offenders = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted((APP_DIR / "application").rglob("*.py"))
        if [name for name in _imported_modules(path) if name.startswith(forbidden)]
    )
    assert offenders == []


def test_twenty_error_codes_are_not_extended() -> None:
    """门槛 ⑪（`docs/07` §11）：`app/` 内的 `STRUCTAI-xxxx` 字面量**恰好**那 20 个码。"""
    declared: set[str] = set()
    for path in sorted(APP_DIR.rglob("*.py")):
        declared.update(re.findall(r"STRUCTAI-\d{4}", path.read_text(encoding="utf-8")))
    assert declared == set(ERROR_CODES_SPEC)
    assert len(ERROR_CODES_SPEC) == 20


def test_settings_fields_are_registered_in_env_example() -> None:
    """门槛 ⑪（`docs/02` §5 / §5.1）：Settings 字段 ⊆ `.env.example`（本批**未新增**）。"""
    registered = set(
        re.findall(r"^([A-Z0-9_]+)=", ENV_EXAMPLE.read_text(encoding="utf-8"), flags=re.MULTILINE)
    )
    declared = {name.upper() for name in Settings.model_fields}
    assert declared <= registered
    assert declared == {name.upper() for name in SETTINGS_FIELD_SPEC}


def test_commit_and_rollback_only_in_unit_of_work() -> None:
    """门槛 ⑪（`docs/07` §14.4）：`commit()` / `rollback()` **只**在 `unit_of_work.py`。"""
    committers = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted(APP_DIR.rglob("*.py"))
        if _commit_or_rollback_calls(path)
    )
    assert committers == ["app/infrastructure/database/unit_of_work.py"]


def test_frozen_dependency_list_is_not_extended() -> None:
    """门槛 ⑪（`docs/07` §3.1 / §3.2）：本批**未**新增任何依赖。"""
    declared = set(
        re.findall(
            r'^\s*"([A-Za-z0-9_.\-]+)',
            (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
    )
    for dependency in FROZEN_DEPENDENCIES:
        assert dependency in declared, dependency
    assert not (declared & {"celery", "redis", "nats", "kafka", "opentelemetry"})


# ===== 测试替身（只在验收文件内使用）=====


async def _status(status: str) -> Mapping[str, object]:
    """返回给定状态的检查结果（`HealthChecker` 替身）。"""
    return {"status": status}


async def _raising(message: str) -> Mapping[str, object]:
    """抛异常的检查器替身（只允许暴露异常**类名**）。"""
    raise RuntimeError(message)


async def _provision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> str:
    """建表 + Seed 一个临时库，返回其 `database_url`（`docs/02` §15 / §44）。"""
    monkeypatch.setenv(ADMIN_PASSWORD_ENV, "P29-P35-验收-口令-51a3")
    database_url = f"sqlite+aiosqlite:///{(tmp_path / name).as_posix()}"
    engine = create_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await seed(create_session_factory(engine))
    finally:
        await engine.dispose()
    return database_url


def _imported_modules(path: Path) -> set[str]:
    """`path` 里出现的模块名（AST 级；`import a.b` 与 `from a.b import c` 都算）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _commit_or_rollback_calls(path: Path) -> list[str]:
    """`path` 里对 `commit()` / `rollback()` 的调用（AST 级）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"commit", "rollback"}
    ]
