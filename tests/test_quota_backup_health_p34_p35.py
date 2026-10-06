"""P34 / P35 验收测试：Health（`docs/02` §16–§17 / §41 / §46 / §94）与
Quota / Backup / Restore / Retention（`docs/02` §18–§31 / §40 / §46 / §66）。

验收点（与 brief D 的门槛一一对应）：

① 配额（`docs/02` §36 / §40 / §60；`docs/07` §11）：全 0 上限**放行一切**；
   `max_api_requests` 的滑动窗口**恰好**放行 N 次后拒绝；`max_concurrent_tasks`
   按**维度键**计数（第二个租户不被第一个拖累 —— P22–P28 R49 的教训）；
   被拒的登记**不消耗**额度；`release_task` 归还容量；`require` 抛
   `STRUCTAI-5000`（`retryable is True`）且 `details` 逐字段匹配；
   负上限 → 7000；`usage()` 只作诊断；**零 SQL**（SQL 级钩子）。
② 备份（`docs/02` §19–§22）：`create_backup` 产出 §20 的目录布局；
   清单键集合**恰好**是 §19 的六个；数据库经 **SQLite backup API** 复制
   （monkeypatch `backup_database` 观察调用，且源库仍可打开）；每个产物载荷
   被复制且校验和一致；损坏载荷 → 6200 `artifact_backup_failed` 且**不写清单**；
   `verify_backup` 对干净备份 `valid=True`、对篡改后的库 / 载荷 `valid=False`；
   清单不含凭据标记。
③ 恢复（`docs/02` §23–§26）：`restore` **先**创建紧急备份；损坏备份被拒；
   部分失败 → `restored=False`；`integrity_check` 返回 `PRAGMA integrity_check`
   的原始结果。
④ 保留（`docs/02` §27–§31）：`cleanup_audit` **不存在**（`hasattr`）；
   Artifact GC **隔离**而不删除；`RetentionPolicy` 默认值 = §28 的规范副本，
   且 `audit_days > trace_days`。
⑤ 健康（`docs/02` §16.1–§16.3 / §94；`docs/07` §14.4）：`liveness` **绝不**咨询
   注册表；`registry` 不 HEALTHY → `NOT_READY`（字面量）；三个关键检查全 HEALTHY
   → `READY`；只有 Adapter DOWN → `DEGRADED`；数据库 DOWN → `UNAVAILABLE`；
   抛异常的检查器只暴露**异常类名**（无消息、无连接串）；未注册名 →
   `checker_not_registered`；重名注册 → 7000；路径常量与两个检查元组匹配规范副本；
   三个处理器**不启动 HTTP 服务器**即可验收。
⑥ 红线（`docs/07` §14.1 / §14.2 / §14.4）：`commit` / `rollback` 只在
   `unit_of_work.py`（AST）；`app/` 内无厂商名；`app/` 内 `STRUCTAI-xxxx` 恰好
   20 个；`app/observability/**` 不 import SQLAlchemy / FastAPI；
   `app/interfaces/**` 不 import SQLAlchemy。

⚠️ 本文件里的「规范原文副本」（维度 / 指标 / 清单键 / 目录常量 / 保留默认值 /
路径与检查元组 / 20 码清单）**故意不**从被测模块取：若断言只与被测常量比较，
「常量被改错」与「实现被改错」会一起通过（同源循环）。
"""

from __future__ import annotations

import ast
import asyncio
import json
import re
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.services.backup import (
    ARTIFACT_BACKUP_DIR,
    BACKUP_ARTIFACTS_DIR,
    BACKUP_DATABASE_NAME,
    BACKUP_MANIFEST_NAME,
    BACKUP_VERSION,
    QUARANTINE_DIR,
    RESTORE_PRE_BACKUP_DIR,
    BackupManifest,
    BackupService,
    RestoreService,
    RetentionService,
    backup_database,
)
from app.application.services.quota import (
    QUOTA_DIMENSIONS,
    QUOTA_METRICS,
    QUOTA_STAGE,
    QuotaService,
    StaticQuotaPolicySource,
)
from app.domain.enums import HealthStatus, QuotaDimension, QuotaMetric
from app.domain.errors import ArtifactError, InternalError, StructAIError, TaskError
from app.domain.protocols import ArtifactRecord, QuotaLimits, RetentionPolicy
from app.infrastructure.database import Base
from app.interfaces.http.health import (
    HEALTH_ROUTER_PREFIX,
    HEALTH_ROUTER_TAG,
    INTERFACE_STAGE,
    create_health_router,
    health_report,
    livez,
    readyz,
)
from app.observability.health import (
    HEALTH_CHECKS,
    HEALTH_PATH,
    HEALTH_STAGE,
    LIVENESS_PATH,
    NOT_READY,
    READINESS_CHECKS,
    READINESS_PATH,
    READY,
    STATUS_KEY,
    CallableHealthChecker,
    HealthRegistry,
    HealthService,
    is_ready_status,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
OBSERVABILITY_DIR = APP_DIR / "observability"
INTERFACES_DIR = APP_DIR / "interfaces"

VENDOR_NAMES = ("midas", "csi", "ansys", "sap2000", "etabs", "opensees")
"""`docs/07` §14.2：`app/` 内禁止出现的厂商名（大小写不敏感）。"""

SECRET_MARKERS = ("password", "api_key", "api-key", "token", "private_key", "secret")
"""`docs/07` §14.3：不得出现在清单 / `details` / 日志里的 secret 形态词。"""

SessionFactory = async_sessionmaker[AsyncSession]
"""会话工厂类型别名（`docs/02` §15）。"""


# ===== 规范原文副本（`docs/02` §16 / §19 / §20 / §28 / §36 / §40 / §94；`docs/07` §11）=====

QUOTA_DIMENSIONS_SPEC = ("USER", "TENANT", "AI_AGENT", "SOFTWARE_INSTANCE")
"""`docs/02` §36 / §60：四个配额维度（逐项抄写）。"""

QUOTA_METRICS_SPEC = (
    "max_tasks",
    "max_concurrent_tasks",
    "max_api_requests",
    "max_storage",
    "max_projects",
)
"""`docs/02` §36 / §40：五个配额指标（逐项抄写）。"""

MANIFEST_KEYS_SPEC = (
    "backup_id",
    "created_at",
    "database",
    "artifacts",
    "version",
    "schema_revision",
)
"""`docs/02` §19：Backup Manifest 的**六个**顶层键（逐项抄写）。"""

BACKUP_DIR_ENTRIES_SPEC = (BACKUP_MANIFEST_NAME, BACKUP_DATABASE_NAME, BACKUP_ARTIFACTS_DIR)
"""`docs/02` §20：备份目录里必须出现的三项（`manifest.json` / 库 / `artifacts/`）。"""

RESTORE_PRE_BACKUP_DIR_SPEC = "pre_restore_backup"
"""`docs/02` §24：恢复前紧急备份的目录名（逐字抄写）。"""

QUARANTINE_DIR_SPEC = "quarantine"
"""`docs/02` §31：Artifact GC 的隔离目录（逐字抄写）。"""

BACKUP_VERSION_SPEC = "2.0"
"""`docs/02` §19：清单的 `version`（逐字抄写）。"""

RETENTION_DEFAULTS_SPEC: Mapping[str, int] = {
    "task_days": 30,
    "trace_days": 14,
    "audit_days": 365,
    "artifact_days": 90,
    "event_days": 30,
    "session_days": 7,
}
"""`docs/02` §28 的默认策略表（逐项抄写：Task 30 / Trace 14 / Event 30 /
Artifact 90 / Session 7 / Audit 365）。"""

READINESS_CHECKS_SPEC = ("database", "registry", "task_engine")
"""`docs/02` §16.2 / §94：`readyz = Core DB + Registry + Task Engine`。"""

HEALTH_CHECKS_SPEC = (
    "database",
    "registry",
    "task_engine",
    "adapter_manager",
    "software_instances",
)
"""`docs/02` §94：`health = DB + Registry + Task Engine + Adapter Manager +
Software Instances`。"""

HEALTH_PATHS_SPEC: Mapping[str, str] = {
    "liveness": "/livez",
    "readiness": "/readyz",
    "health": "/health",
}
"""`docs/02` §16 / §41 / §94 的三个绝对路径（逐字抄写）。"""

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

MODULE_PATHS = (
    "app/application/services/quota.py",
    "app/application/services/backup.py",
    "app/observability/health.py",
    "app/interfaces/__init__.py",
    "app/interfaces/http/__init__.py",
    "app/interfaces/http/health.py",
)
"""本批（brief D）新增的模块（用于红线断言）。"""


# ===== 替身（只满足**结构**契约；不 import 其它 agent 的模块）=====


class _FakeArtifactStore:
    """`ArtifactStore` 结构替身（`docs/02` §3.2 / §29；只实现本文件需要的方法）。"""

    def __init__(self, records: Sequence[ArtifactRecord] = ()) -> None:
        self._records: dict[str, ArtifactRecord] = {record.id: record for record in records}
        self.pages: list[tuple[int, int]] = []

    def add(self, record: ArtifactRecord) -> None:
        self._records[record.id] = record

    async def create(self, draft: object) -> ArtifactRecord:
        raise NotImplementedError

    async def get(self, artifact_id: str) -> ArtifactRecord | None:
        return self._records.get(artifact_id)

    async def delete(self, artifact_id: str) -> bool:
        return self._records.pop(artifact_id, None) is not None

    async def list_for_task(self, task_id: str) -> Sequence[ArtifactRecord]:
        return [record for record in self._records.values() if record.task_id == task_id]

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> Sequence[ArtifactRecord]:
        self.pages.append((limit, offset))
        ordered = sorted(self._records.values(), key=lambda record: record.id)
        return ordered[offset : offset + limit]

    def ids(self) -> tuple[str, ...]:
        """当前记录 id（诊断 / 断言用）。"""
        return tuple(sorted(self._records))


class _FakeStorage:
    """`ArtifactStorageReader` 结构替身 + 存储根（`docs/02` §3.5 / §31）。

    `root` 属性使 `RetentionService(storage=…)` 能定位扫描根（`docs/02` §31）；
    `fail_put` 用于制造「部分恢复」的失败路径。
    """

    def __init__(self, root: Path, payloads: Mapping[str, bytes] | None = None) -> None:
        self.root = root
        self.payloads: dict[str, bytes] = dict(payloads or {})
        self.fail_put = False
        self.puts: list[str] = []

    async def get(self, reference: str) -> bytes:
        if reference not in self.payloads:
            raise FileNotFoundError(reference)
        return self.payloads[reference]

    async def put(self, data: bytes, metadata: Mapping[str, Any]) -> str:
        if self.fail_put:
            raise OSError("storage is read-only")
        artifact_id = str(metadata.get("artifact_id", ""))
        reference = f"{artifact_id}/{ARTIFACT_BACKUP_DIR}"
        self.payloads[reference] = data
        self.puts.append(reference)
        target = self.root / reference
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return reference

    async def exists(self, reference: str) -> bool:
        return reference in self.payloads


def _record(
    artifact_id: str,
    *,
    created_at: datetime | None = None,
    size: int = 0,
) -> ArtifactRecord:
    """构造一条产物元数据（`docs/02` §3.2 的列集合）。"""
    return ArtifactRecord(
        id=artifact_id,
        storage_backend="local",
        storage_key=f"tenant/project/{artifact_id}/{ARTIFACT_BACKUP_DIR}",
        mime_type="application/octet-stream",
        size=size,
        checksum=None,
        task_id=None,
        created_at=created_at,
    )


async def _seeded_database(engine: AsyncEngine) -> Path:
    """建表并返回该引擎对应的**数据库文件路径**（`docs/02` §20 的 `structai.db`）。"""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return Path(engine.url.database or "")


def _recorded_statements(engine: AsyncEngine) -> list[str]:
    """录制引擎上执行过的 SQL 语句（SQL 级钩子）。"""
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
    """文件内 `.commit()` / `.rollback()` 调用的属性名（AST 级）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"commit", "rollback"}
    ]


def _python_files(directory: Path) -> list[Path]:
    """目录下的 `*.py`；目录不存在时返回空列表（另一 agent 可能尚未建包）。"""
    if not directory.is_dir():
        return []
    return sorted(directory.rglob("*.py"))


async def _healthy() -> Mapping[str, Any]:
    """恒 `HEALTHY` 的检查结果（`docs/02` §17）。"""
    return {STATUS_KEY: HealthStatus.HEALTHY}


def _checker(name: str, status: HealthStatus | str, *, critical: bool = True) -> Any:
    """构造一个恒返回指定状态的检查器（`docs/02` §17）。"""

    async def _check() -> Mapping[str, Any]:
        return {STATUS_KEY: status}

    return CallableHealthChecker(name, _check, critical=critical)


# ===== ① 配额（`docs/02` §36 / §40 / §60；`docs/07` §11）=====


def test_quota_dimensions_and_metrics_match_the_spec_copies() -> None:
    """门槛 ①（`docs/02` §36 / §40）：四维度 × 五指标逐字匹配规范副本。"""
    assert tuple(dimension.value for dimension in QuotaDimension) == QUOTA_DIMENSIONS_SPEC
    assert tuple(metric.value for metric in QuotaMetric) == QUOTA_METRICS_SPEC
    assert QUOTA_DIMENSIONS == QUOTA_DIMENSIONS_SPEC
    assert QUOTA_METRICS == QUOTA_METRICS_SPEC
    assert QUOTA_STAGE == "quota"


def test_quota_policy_resolution_is_most_specific_first() -> None:
    """门槛 ①（`docs/02` §36）：上限解析是 `user → tenant → default`（最具体优先）。"""
    default = QuotaLimits(max_api_requests=1)
    policy = StaticQuotaPolicySource(
        default,
        by_tenant={"t1": QuotaLimits(max_api_requests=2)},
        by_user={"u1": QuotaLimits(max_api_requests=3)},
    )
    assert policy.default is default
    assert policy.limits_for(tenant_id="t1", user_id="u1").max_api_requests == 3
    assert policy.limits_for(tenant_id="t1", user_id="u9").max_api_requests == 2
    assert policy.limits_for(tenant_id="t9", user_id="u9").max_api_requests == 1
    # 缺省策略 = 全 0 = 不限（与「未配备配额表」一致，`docs/02` §36）。
    assert StaticQuotaPolicySource().default == QuotaLimits()


def test_unlimited_policy_admits_everything() -> None:
    """门槛 ①（`docs/02` §36 / §60）：全 0 上限**放行一切**，`remaining` 为哨兵 `-1`。"""

    async def _run() -> None:
        service = QuotaService()
        for _ in range(50):
            decision = await service.consume_api_request(tenant_id="t", user_id="u")
            assert decision.allowed is True
            assert decision.limit == 0
            assert decision.remaining == -1
            assert decision.ok is True
        for _ in range(50):
            assert (await service.register_task(tenant_id="t", user_id="u")).allowed is True
        assert (await service.check_tasks(tenant_id="t", user_id="u")).allowed is True
        assert (
            await service.check_storage(tenant_id="t", user_id="u", additional_bytes=10**12)
        ).allowed is True
        assert (
            await service.check_projects(tenant_id="t", user_id="u", current_projects=10**6)
        ).allowed is True
        assert isinstance(service.policy, StaticQuotaPolicySource)

    asyncio.run(_run())


def test_api_request_window_admits_exactly_the_limit() -> None:
    """门槛 ①（`docs/02` §40）：滑动窗口**恰好**放行 N 次，第 N+1 次拒绝且不推进窗口。"""

    async def _run() -> None:
        service = QuotaService(StaticQuotaPolicySource(QuotaLimits(max_api_requests=3)))
        decisions = [
            await service.consume_api_request(tenant_id="t", user_id="u") for _ in range(4)
        ]
        assert [decision.allowed for decision in decisions] == [True, True, True, False]
        refused = decisions[-1]
        assert refused.metric == "max_api_requests"
        assert refused.dimension == "USER"
        assert refused.limit == 3
        assert refused.used == 3
        assert refused.remaining == 0
        assert refused.reason == "api_request_rate_limited"
        assert refused.ok is False
        # 拒绝路径零副作用：窗口仍是 3 条。
        assert service.usage(tenant_id="t", user_id="u")["max_api_requests"] == 3

    asyncio.run(_run())


def test_api_request_window_expires_with_the_clock() -> None:
    """门槛 ①（`docs/02` §40）：窗口按 `window_seconds` 滑动（可注入时钟）。"""
    now = datetime(2026, 1, 1, tzinfo=UTC)

    async def _run() -> None:
        ticks = [now]

        def clock() -> datetime:
            return ticks[0]

        service = QuotaService(
            StaticQuotaPolicySource(QuotaLimits(max_api_requests=1, window_seconds=60)),
            clock=clock,
        )
        assert (await service.consume_api_request(tenant_id="t", user_id="u")).allowed is True
        assert (await service.consume_api_request(tenant_id="t", user_id="u")).allowed is False
        ticks[0] = now + timedelta(seconds=61)
        assert (await service.consume_api_request(tenant_id="t", user_id="u")).allowed is True

    asyncio.run(_run())


def test_concurrent_tasks_are_counted_per_dimension_key() -> None:
    """门槛 ①（R49 的教训）：并发计数按**维度键**，第二个租户不被第一个拖累。"""

    async def _run() -> None:
        service = QuotaService(StaticQuotaPolicySource(QuotaLimits(max_concurrent_tasks=1)))
        first = await service.register_task(tenant_id="t1", user_id="u1")
        second = await service.register_task(tenant_id="t1", user_id="u1")
        other_tenant = await service.register_task(tenant_id="t2", user_id="u2")
        assert first.allowed is True
        assert second.allowed is False
        assert second.reason == "concurrent_task_limit_reached"
        # 🔴 另一个租户**不**被第一个拖累（按维度键计数，不是全局总数）。
        assert other_tenant.allowed is True
        # 被拒的登记不消耗额度：并发数仍是 1。
        assert service.usage(tenant_id="t1", user_id="u1")["max_concurrent_tasks"] == 1

    asyncio.run(_run())


def test_release_task_restores_capacity() -> None:
    """门槛 ①（`docs/02` §40）：`release_task` 归还容量；重复释放幂等且不产生负数。"""

    async def _run() -> None:
        service = QuotaService(StaticQuotaPolicySource(QuotaLimits(max_concurrent_tasks=1)))
        assert (await service.register_task(tenant_id="t", user_id="u")).allowed is True
        assert (await service.register_task(tenant_id="t", user_id="u")).allowed is False
        released = await service.release_task(tenant_id="t", user_id="u")
        assert released.allowed is True
        assert released.used == 0
        assert (await service.register_task(tenant_id="t", user_id="u")).allowed is True
        # 重复释放：不抛错、不产生负数。
        await service.release_task(tenant_id="t", user_id="u")
        again = await service.release_task(tenant_id="t", user_id="u")
        assert again.used == 0

    asyncio.run(_run())


def test_lifetime_task_counter_does_not_fall_with_release() -> None:
    """门槛 ①（`docs/02` §40）：`max_tasks` 是**终身**计数，不随 `release_task` 回落。"""

    async def _run() -> None:
        service = QuotaService(StaticQuotaPolicySource(QuotaLimits(max_tasks=2)))
        assert (await service.register_task(tenant_id="t", user_id="u")).allowed is True
        await service.release_task(tenant_id="t", user_id="u")
        assert (await service.check_tasks(tenant_id="t", user_id="u")).used == 1
        assert (await service.register_task(tenant_id="t", user_id="u")).allowed is True
        decision = await service.check_tasks(tenant_id="t", user_id="u")
        assert decision.allowed is False
        assert decision.metric == "max_tasks"
        assert decision.used == 2

    asyncio.run(_run())


def test_storage_and_project_checks_use_the_caller_supplied_usage() -> None:
    """门槛 ①（`docs/02` §40）：`max_storage` / `max_projects` 的用量由调用方给出。"""

    async def _run() -> None:
        service = QuotaService(
            StaticQuotaPolicySource(QuotaLimits(max_storage=100, max_projects=3))
        )
        assert (
            await service.check_storage(tenant_id="t", user_id="u", additional_bytes=100)
        ).allowed is True
        assert (
            await service.check_storage(tenant_id="t", user_id="u", additional_bytes=101)
        ).allowed is False
        # 已登记增量参与判定（`register_task(storage_bytes=…)`）。
        await service.register_task(tenant_id="t", user_id="u", storage_bytes=60)
        assert (
            await service.check_storage(tenant_id="t", user_id="u", additional_bytes=50)
        ).allowed is False
        assert (
            await service.check_projects(tenant_id="t", user_id="u", current_projects=3)
        ).allowed is True
        assert (
            await service.check_projects(tenant_id="t", user_id="u", current_projects=4)
        ).allowed is False

    asyncio.run(_run())


def test_require_raises_structai_5000_with_the_full_details_dict() -> None:
    """门槛 ①（`docs/07` §11）：`require` 抛 5000，`retryable is True`，`details` 全字段。"""

    async def _run() -> None:
        service = QuotaService(StaticQuotaPolicySource(QuotaLimits(max_api_requests=1)))
        allowed = await service.consume_api_request(tenant_id="t", user_id="u")
        assert await service.require(allowed) is allowed
        refused = await service.consume_api_request(tenant_id="t", user_id="u")
        with pytest.raises(TaskError) as caught:
            await service.require(refused)
        error = caught.value
        assert error.code == "STRUCTAI-5000"
        assert error.retryable is True
        assert error.details == {
            "stage": "quota",
            "metric": "max_api_requests",
            "dimension": "USER",
            "limit": 1,
            "used": 1,
            "reason": "api_request_rate_limited",
        }
        # 它**不是** 4000（4000 是授权判定，配额是容量判定）。
        assert error.code != "STRUCTAI-4000"
        assert isinstance(error, StructAIError)

    asyncio.run(_run())


def test_negative_limits_raise_7000_and_are_never_clamped() -> None:
    """门槛 ①（`docs/07` §14.3）：负上限 → 7000 `invalid_limits`，绝不静默钳位。"""
    with pytest.raises(InternalError) as caught:
        StaticQuotaPolicySource(QuotaLimits(max_api_requests=-1))
    assert caught.value.code == "STRUCTAI-7000"
    assert caught.value.details == {
        "stage": "quota",
        "reason": "invalid_limits",
        "fields": ["max_api_requests"],
    }
    with pytest.raises(InternalError):
        StaticQuotaPolicySource(QuotaLimits(), by_user={"u": QuotaLimits(max_storage=-5)})
    with pytest.raises(InternalError):
        StaticQuotaPolicySource(QuotaLimits(), by_tenant={"t": QuotaLimits(max_projects=-1)})


def test_usage_is_diagnostics_only_and_contains_no_identifiers() -> None:
    """门槛 ①（`docs/02` §42）：`usage()` 只作诊断，且只含整数计数（无标识）。"""

    async def _run() -> None:
        service = QuotaService(StaticQuotaPolicySource(QuotaLimits(max_api_requests=5)))
        await service.consume_api_request(tenant_id="tenant-x", user_id="user-y")
        usage = service.usage(tenant_id="tenant-x", user_id="user-y")
        assert set(usage) == set(QUOTA_METRICS_SPEC)
        assert all(isinstance(value, int) for value in usage.values())
        # 只含整数计数 —— 绝不回显租户 / 用户标识（`docs/07` §14.3）。
        assert "tenant-x" not in str(dict(usage))
        assert "user-y" not in str(dict(usage))

    asyncio.run(_run())


def test_quota_service_issues_zero_sql(engine: AsyncEngine) -> None:
    """门槛 ①（`docs/02` §60）：`QuotaService` 是**进程内**状态 —— **零 SQL**。"""

    async def _run() -> None:
        statements = _recorded_statements(engine)
        service = QuotaService(
            StaticQuotaPolicySource(QuotaLimits(max_api_requests=2, max_concurrent_tasks=2))
        )
        await service.consume_api_request(tenant_id="t", user_id="u")
        await service.consume_api_request(tenant_id="t", user_id="u")
        await service.consume_api_request(tenant_id="t", user_id="u")
        await service.register_task(tenant_id="t", user_id="u")
        await service.release_task(tenant_id="t", user_id="u")
        await service.check_tasks(tenant_id="t", user_id="u")
        await service.check_storage(tenant_id="t", user_id="u", additional_bytes=1)
        await service.check_projects(tenant_id="t", user_id="u", current_projects=1)
        service.usage(tenant_id="t", user_id="u")
        assert statements == [], statements
        # 源码层面也没有 `app.infrastructure` 依赖（`docs/07` §14.1）。
        modules = _imported_modules(APP_DIR / "application" / "services" / "quota.py")
        assert [name for name in modules if name.startswith("app.infrastructure")] == []

    asyncio.run(_run())


# ===== ② 备份（`docs/02` §19–§22）=====


def test_backup_database_uses_the_sqlite_backup_api(engine: AsyncEngine, tmp_path: Path) -> None:
    """门槛 ②（`docs/02` §21）：用 SQLite backup API 复制；连接无条件关闭；源库仍可打开。"""

    async def _run() -> None:
        database = await _seeded_database(engine)
        destination = tmp_path / "copied.db"
        backup_database(database, destination)
        assert destination.is_file()
        assert destination.stat().st_size > 0
        # 源库仍可打开且可用（未因句柄 / 锁而损坏）。
        source = sqlite3.connect(str(database))
        try:
            assert source.execute("SELECT 1").fetchone() == (1,)
        finally:
            source.close()
        copied = sqlite3.connect(str(destination))
        try:
            assert copied.execute("SELECT 1").fetchone() == (1,)
        finally:
            copied.close()

    asyncio.run(_run())


def test_create_backup_writes_the_docs_02_section_20_layout(
    engine: AsyncEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛 ②（`docs/02` §20）：时间戳目录 + 清单 + 库 + `artifacts/`；清单键 = §19 的六个。"""
    calls: list[tuple[str, str]] = []
    original = backup_database

    def _spy(source: str | Path, destination: str | Path) -> None:
        calls.append((str(source), str(destination)))
        original(source, destination)

    monkeypatch.setattr("app.application.services.backup.backup_database", _spy)
    moment = datetime(2026, 10, 5, 1, 0, 0, tzinfo=UTC)

    async def _run() -> None:
        database = await _seeded_database(engine)
        service = BackupService(
            database_path=database,
            artifact_root=tmp_path / "storage",
            clock=lambda: moment,
            schema_revision="rev-1",
        )
        destination = tmp_path / "backup"
        manifest = await service.create_backup(destination)
        backup_dir = destination / "20261005T010000"
        assert backup_dir.is_dir()
        assert manifest.backup_id == "20261005T010000"
        for entry in BACKUP_DIR_ENTRIES_SPEC:
            assert (backup_dir / entry).exists(), entry
        # 数据库确实经 SQLite backup API 复制（而不是字节拷贝）。
        assert calls == [(str(database), str(backup_dir / BACKUP_DATABASE_NAME))]
        payload = json.loads((backup_dir / BACKUP_MANIFEST_NAME).read_text(encoding="utf-8"))
        assert tuple(sorted(payload)) == tuple(sorted(MANIFEST_KEYS_SPEC))
        assert payload["version"] == BACKUP_VERSION_SPEC
        assert payload["schema_revision"] == "rev-1"
        assert payload["created_at"] == "2026-10-05T01:00:00Z"
        assert payload["database"]["file"] == BACKUP_DATABASE_NAME
        assert payload["artifacts"]["count"] == 0
        assert payload["artifacts"]["bytes"] == 0
        assert BackupManifest.from_dict(payload).backup_id == manifest.backup_id

    asyncio.run(_run())


def _payloads(records: Sequence[ArtifactRecord]) -> dict[str, bytes]:
    """为给定产物构造「存储键 → 载荷」映射（`docs/02` §22 的读取源）。"""
    return {record.storage_key: f"payload-{record.id}".encode() for record in records}


def test_create_backup_copies_every_artifact_payload_and_verifies_checksums(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """门槛 ②（`docs/02` §22）：读取 → SHA-256 → 复制 → 再次 SHA-256 → 比较。"""

    async def _run() -> None:
        database = await _seeded_database(engine)
        storage_root = tmp_path / "storage"
        records = [_record(f"artifact-{index}") for index in range(3)]
        store = _FakeArtifactStore(records)
        storage = _FakeStorage(storage_root, _payloads(records))
        service = BackupService(
            database_path=database,
            artifact_root=storage_root,
            artifacts=store,
            storage=storage,
            clock=lambda: datetime(2026, 10, 5, 2, 0, 0, tzinfo=UTC),
        )
        manifest = await service.create_backup(tmp_path / "backup")
        assert manifest.artifacts["count"] == 3
        assert manifest.artifacts["bytes"] == sum(
            len(f"payload-{record.id}".encode()) for record in records
        )
        # 分页遍历是**有界**的（`docs/07` §14.4）。
        assert all(limit <= 100 for limit, _ in store.pages)
        backup_dir = tmp_path / "backup" / manifest.backup_id
        for record in records:
            copied = backup_dir / BACKUP_ARTIFACTS_DIR / record.id / ARTIFACT_BACKUP_DIR
            assert copied.read_bytes() == storage.payloads[record.storage_key]
        verification = await service.verify_backup(backup_dir)
        assert verification.valid is True
        assert verification.database_ok is True
        assert verification.artifacts_ok is True
        assert verification.checked == 3
        assert verification.failures == ()

    asyncio.run(_run())


def test_corrupt_artifact_payload_fails_the_whole_backup_with_6200(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """门槛 ②（`docs/02` §22）：载荷缺失 → 6200 `artifact_backup_failed`，且**不写清单**。"""

    async def _run() -> None:
        database = await _seeded_database(engine)
        storage_root = tmp_path / "storage"
        records = [_record("artifact-1"), _record("artifact-2")]
        store = _FakeArtifactStore(records)
        # 只提供第一条的载荷：第二条缺失 → 备份整体失败。
        partial = {records[0].storage_key: b"payload"}
        storage = _FakeStorage(storage_root, partial)
        service = BackupService(
            database_path=database,
            artifact_root=storage_root,
            artifacts=store,
            storage=storage,
            clock=lambda: datetime(2026, 10, 5, 3, 0, 0, tzinfo=UTC),
        )
        with pytest.raises(ArtifactError) as caught:
            await service.create_backup(tmp_path / "backup")
        assert caught.value.code == "STRUCTAI-6200"
        assert caught.value.details == {
            "stage": "backup",
            "reason": "artifact_backup_failed",
        }
        backup_dir = tmp_path / "backup" / "20261005T030000"
        # 🔴 清单**不**存在：整个备份不得被标记为完整成功（`docs/02` §22）。
        assert not (backup_dir / BACKUP_MANIFEST_NAME).exists()

    asyncio.run(_run())


def test_backup_without_storage_fails_when_artifacts_exist(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """门槛 ②（`docs/02` §22）：有产物行但未注入 storage → 同一 6200 信号。"""

    async def _run() -> None:
        database = await _seeded_database(engine)
        store = _FakeArtifactStore([_record("artifact-1")])
        service = BackupService(
            database_path=database,
            artifact_root=tmp_path / "storage",
            artifacts=store,
            storage=None,
        )
        with pytest.raises(ArtifactError) as caught:
            await service.create_backup(tmp_path / "backup")
        assert caught.value.details["reason"] == "artifact_backup_failed"

    asyncio.run(_run())


def test_verify_backup_detects_tampering(engine: AsyncEngine, tmp_path: Path) -> None:
    """门槛 ②（`docs/02` §22 / §23）：篡改数据库或产物载荷后 `valid=False`（不抛异常）。"""

    async def _run() -> None:
        database = await _seeded_database(engine)
        storage_root = tmp_path / "storage"
        record = _record("artifact-1")
        storage = _FakeStorage(storage_root, _payloads([record]))
        service = BackupService(
            database_path=database,
            artifact_root=storage_root,
            artifacts=_FakeArtifactStore([record]),
            storage=storage,
            clock=lambda: datetime(2026, 10, 5, 4, 0, 0, tzinfo=UTC),
        )
        manifest = await service.create_backup(tmp_path / "backup")
        backup_dir = tmp_path / "backup" / manifest.backup_id
        assert (await service.verify_backup(backup_dir)).valid is True
        # 篡改产物载荷。
        payload = backup_dir / BACKUP_ARTIFACTS_DIR / record.id / ARTIFACT_BACKUP_DIR
        payload.write_bytes(b"tampered")
        verification = await service.verify_backup(backup_dir)
        assert verification.valid is False
        assert verification.artifacts_ok is False
        assert any("artifact_checksum_mismatch" in failure for failure in verification.failures)
        # 篡改数据库文件。
        payload.write_bytes(b"payload")
        with (backup_dir / BACKUP_DATABASE_NAME).open("ab") as handle:
            handle.write(b"\x00tampered")
        verification = await service.verify_backup(backup_dir)
        assert verification.valid is False
        assert verification.database_ok is False
        assert "database_checksum_mismatch" in verification.failures
        # 缺清单也是「不合法」而不是异常。
        (backup_dir / BACKUP_MANIFEST_NAME).unlink()
        missing = await service.verify_backup(backup_dir)
        assert missing.valid is False
        assert missing.failures == ("manifest_missing",)

    asyncio.run(_run())


def test_manifest_and_logs_contain_no_credential_marker(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """门槛 ②（`docs/02` §47；`docs/07` §14.3）：清单**绝不**含凭据 / 载荷内容。"""

    async def _run() -> None:
        database = await _seeded_database(engine)
        storage_root = tmp_path / "storage"
        record = _record("artifact-1")
        storage = _FakeStorage(storage_root, {record.storage_key: b"payload-bytes"})
        service = BackupService(
            database_path=database,
            artifact_root=storage_root,
            artifacts=_FakeArtifactStore([record]),
            storage=storage,
            clock=lambda: datetime(2026, 10, 5, 5, 0, 0, tzinfo=UTC),
        )
        manifest = await service.create_backup(tmp_path / "backup")
        raw = (tmp_path / "backup" / manifest.backup_id / BACKUP_MANIFEST_NAME).read_text(
            encoding="utf-8"
        )
        lowered = raw.lower()
        for marker in SECRET_MARKERS:
            assert marker not in lowered, marker
        # 清单里**没有**载荷内容，只有标识 / 校验和 / 计数 / 大小。
        assert "payload-bytes" not in raw
        assert len(str(manifest.database["checksum"])) == 64

    asyncio.run(_run())


def test_manifest_from_dict_rejects_malformed_payloads() -> None:
    """门槛 ②（`docs/02` §19）：畸形清单 → 7000 `invalid_manifest`。"""
    with pytest.raises(InternalError) as caught:
        BackupManifest.from_dict({"backup_id": "b1"})
    assert caught.value.code == "STRUCTAI-7000"
    assert caught.value.details == {"stage": "backup", "reason": "invalid_manifest"}
    with pytest.raises(InternalError):
        BackupManifest.from_dict(
            {
                "backup_id": "b1",
                "created_at": "not-a-timestamp",
                "database": {},
                "artifacts": {},
                "version": "2.0",
            }
        )


def test_missing_source_database_raises_7000(tmp_path: Path) -> None:
    """门槛 ②（`docs/02` §20）：源库不存在 → 7000 `database_missing`（不产出空备份）。"""

    async def _run() -> None:
        service = BackupService(
            database_path=tmp_path / "absent.db",
            artifact_root=tmp_path / "storage",
        )
        with pytest.raises(InternalError) as caught:
            await service.create_backup(tmp_path / "backup")
        assert caught.value.details == {"stage": "backup", "reason": "database_missing"}

    asyncio.run(_run())
    # 失败时**不**产出任何备份目录（`docs/02` §22：不得留下半成品）。
    assert sorted(tmp_path.glob("backup/*")) == []


# ===== ③ 恢复（`docs/02` §23–§26）=====


async def _registry_ok() -> bool:
    """恒通过的 Registry 校验钩子（`docs/02` §26）。"""
    return True


def test_restore_creates_the_pre_restore_backup_first(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """门槛 ③（`docs/02` §24）：恢复前**必须**先创建当前状态紧急备份。"""

    async def _run() -> None:
        database = await _seeded_database(engine)
        storage_root = tmp_path / "storage"
        record = _record("artifact-1")
        storage = _FakeStorage(storage_root, _payloads([record]))
        backup = BackupService(
            database_path=database,
            artifact_root=storage_root,
            artifacts=_FakeArtifactStore([record]),
            storage=storage,
            clock=lambda: datetime(2026, 10, 5, 6, 0, 0, tzinfo=UTC),
        )
        manifest = await backup.create_backup(tmp_path / "backup")
        backup_dir = tmp_path / "backup" / manifest.backup_id
        restore = RestoreService(
            backup=backup,
            database_path=database,
            artifact_root=storage_root,
            storage=storage,
            registry_validator=_registry_ok,
        )
        report = await restore.restore(backup_dir)
        assert report.restored is True
        assert report.backup_id == manifest.backup_id
        assert report.database_restored is True
        assert report.artifacts_restored == 1
        assert report.integrity_ok is True
        assert report.registry_ok is True
        assert report.failures == ()
        # 紧急备份落在 `<restore_root>/pre_restore_backup/<时间戳>/`，且**先于**覆盖生成。
        assert report.pre_restore_backup is not None
        emergency = database.parent / report.pre_restore_backup
        assert (emergency / BACKUP_MANIFEST_NAME).is_file()
        assert (emergency / BACKUP_DATABASE_NAME).is_file()
        assert (await backup.verify_backup(emergency)).valid is True
        assert storage.puts == [f"artifact-1/{ARTIFACT_BACKUP_DIR}"]

    asyncio.run(_run())


def test_restore_refuses_a_corrupt_backup(engine: AsyncEngine, tmp_path: Path) -> None:
    """门槛 ③（`docs/02` §23 / §24）：损坏备份被拒，且**不**覆盖数据库。"""

    async def _run() -> None:
        database = await _seeded_database(engine)
        original_bytes = database.read_bytes()
        storage_root = tmp_path / "storage"
        backup = BackupService(
            database_path=database,
            artifact_root=storage_root,
            clock=lambda: datetime(2026, 10, 5, 7, 0, 0, tzinfo=UTC),
        )
        manifest = await backup.create_backup(tmp_path / "backup")
        backup_dir = tmp_path / "backup" / manifest.backup_id
        with (backup_dir / BACKUP_DATABASE_NAME).open("ab") as handle:
            handle.write(b"\x00tampered")
        restore = RestoreService(
            backup=backup,
            database_path=database,
            artifact_root=storage_root,
        )
        verification = await restore.validate(backup_dir)
        assert verification.valid is False
        report = await restore.restore(backup_dir)
        assert report.restored is False
        assert report.database_restored is False
        assert report.pre_restore_backup is None
        assert "database_checksum_mismatch" in report.failures
        # 未校验通过 → **绝不**直接覆盖（`docs/02` §24）。
        assert database.read_bytes() == original_bytes
        assert not (database.parent / RESTORE_PRE_BACKUP_DIR).exists()

    asyncio.run(_run())


def test_restore_reports_false_on_a_partial_failure(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """门槛 ③（`docs/02` §24）：部分恢复**绝不**被报告为成功。"""

    async def _run() -> None:
        database = await _seeded_database(engine)
        storage_root = tmp_path / "storage"
        record = _record("artifact-1")
        storage = _FakeStorage(storage_root, _payloads([record]))
        backup = BackupService(
            database_path=database,
            artifact_root=storage_root,
            artifacts=_FakeArtifactStore([record]),
            storage=storage,
            clock=lambda: datetime(2026, 10, 5, 8, 0, 0, tzinfo=UTC),
        )
        manifest = await backup.create_backup(tmp_path / "backup")
        backup_dir = tmp_path / "backup" / manifest.backup_id
        storage.fail_put = True
        restore = RestoreService(
            backup=backup,
            database_path=database,
            artifact_root=storage_root,
            storage=storage,
        )
        report = await restore.restore(backup_dir)
        assert report.restored is False
        assert report.database_restored is True
        assert report.artifacts_restored == 0
        assert "artifact_restore_failed:artifact-1" in report.failures
        # 紧急备份**仍然**存在（回退路径没有被跳过）。
        assert report.pre_restore_backup is not None

    asyncio.run(_run())


def test_restore_validate_rejects_a_schema_mismatch(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """门槛 ③（`docs/02` §23）：schema 版本不符 → 7000 `schema_mismatch`。"""

    async def _run() -> None:
        database = await _seeded_database(engine)
        storage_root = tmp_path / "storage"
        backup = BackupService(
            database_path=database,
            artifact_root=storage_root,
            clock=lambda: datetime(2026, 10, 5, 9, 0, 0, tzinfo=UTC),
            schema_revision="rev-old",
        )
        manifest = await backup.create_backup(tmp_path / "backup")
        backup_dir = tmp_path / "backup" / manifest.backup_id
        # 当前 schema 已前进到 rev-new → 该备份不可恢复。
        newer = BackupService(
            database_path=database,
            artifact_root=storage_root,
            clock=lambda: datetime(2026, 10, 5, 9, 0, 1, tzinfo=UTC),
            schema_revision="rev-new",
        )
        restore = RestoreService(
            backup=newer,
            database_path=database,
            artifact_root=storage_root,
        )
        with pytest.raises(InternalError) as caught:
            await restore.validate(backup_dir)
        assert caught.value.code == "STRUCTAI-7000"
        assert caught.value.details == {"stage": "restore", "reason": "schema_mismatch"}

    asyncio.run(_run())


def test_integrity_check_returns_the_pragma_result(engine: AsyncEngine, tmp_path: Path) -> None:
    """门槛 ③（`docs/02` §26）：`integrity_check` 返回 `PRAGMA integrity_check` 的原始结果。"""

    record = _record("artifact-1")
    payload_bytes = _payloads([record])[record.storage_key]
    # 存储里**已有**该载荷（`docs/02` §3.5 的 `{tenant}/{project}/{artifact_id}/payload`）。
    payload_path = tmp_path / "storage" / record.id / ARTIFACT_BACKUP_DIR
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_bytes(payload_bytes)

    async def _run() -> None:
        database = await _seeded_database(engine)
        storage_root = tmp_path / "storage"
        storage = _FakeStorage(storage_root, _payloads([record]))
        backup = BackupService(
            database_path=database,
            artifact_root=storage_root,
            artifacts=_FakeArtifactStore([record]),
            storage=storage,
        )
        restore = RestoreService(
            backup=backup,
            database_path=database,
            artifact_root=storage_root,
            storage=storage,
        )
        result = await restore.integrity_check()
        assert result["database_ok"] is True
        assert result["database"] == "ok"
        assert result["artifacts_ok"] is True
        # 未注入 validator → `None`（「未校验」与「校验失败」必须可区分）。
        assert result["registry"] is None
        with_validator = RestoreService(
            backup=backup,
            database_path=database,
            artifact_root=storage_root,
            storage=storage,
            registry_validator=_registry_ok,
        )
        assert (await with_validator.integrity_check())["registry"] is True

    asyncio.run(_run())


# ===== ④ 保留（`docs/02` §27–§31）=====


def test_retention_policy_defaults_match_the_spec_copy() -> None:
    """门槛 ④（`docs/02` §28）：默认策略 = 规范副本；`audit_days > trace_days`。"""
    policy = RetentionPolicy()
    for name, expected in RETENTION_DEFAULTS_SPEC.items():
        assert getattr(policy, name) == expected, name
    assert policy.audit_days > policy.trace_days
    assert QUARANTINE_DIR == QUARANTINE_DIR_SPEC
    assert RESTORE_PRE_BACKUP_DIR == RESTORE_PRE_BACKUP_DIR_SPEC
    assert BACKUP_VERSION == BACKUP_VERSION_SPEC


def test_retention_has_no_cleanup_audit_and_reports_configured_sources() -> None:
    """门槛 ④（`docs/02` §29 / §45）：**没有** `cleanup_audit`；未装配的源可区分。"""
    service = RetentionService()
    assert hasattr(service, "cleanup_tasks") is True
    assert hasattr(service, "cleanup_traces") is True
    assert hasattr(service, "cleanup_events") is True
    assert hasattr(service, "cleanup_artifacts") is True
    assert hasattr(service, "cleanup_sessions") is True
    # 🔴 审计记录的删除需要「策略 + 管理员授权 + 删除审计」，故本模块**不提供**该方法。
    assert hasattr(service, "cleanup_audit") is False
    assert hasattr(service, "cleanup_all") is True
    assert service.configured() == ()

    async def _run() -> None:
        # 未装配的保留源**不是**「成功清理 0 行」——它如实返回 0。
        assert await service.cleanup_tasks() == 0
        assert await service.cleanup_traces() == 0
        assert await service.cleanup_events() == 0
        assert await service.cleanup_artifacts() == 0
        assert await service.cleanup_sessions() == 0
        report = await service.cleanup_all()
        assert report.cleaned == {
            "tasks": 0,
            "traces": 0,
            "events": 0,
            "artifacts": 0,
            "sessions": 0,
        }
        assert "audit" not in report.cleaned

    asyncio.run(_run())


# ===== ④ 保留：Artifact GC 与清理（`docs/02` §29 / §31）=====


def test_artifact_gc_quarantines_instead_of_deleting(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """门槛 ④（`docs/02` §31）：孤儿载荷被**隔离**，绝不扫描后立即删除。"""

    async def _run() -> None:
        await _seeded_database(engine)
        root = tmp_path / "storage"
        known = root / "tenant-a" / "project-a" / "artifact-known"
        orphan = root / "tenant-a" / "project-a" / "artifact-orphan"
        for directory in (known, orphan):
            directory.mkdir(parents=True, exist_ok=True)
            (directory / ARTIFACT_BACKUP_DIR).write_bytes(b"payload")
        service = RetentionService(
            artifacts=_FakeArtifactStore([_record("artifact-known")]),
            storage=root,
        )
        quarantined = await service.collect_garbage()
        assert quarantined == 1
        # 孤儿被**移动**（不是删除）到 quarantine/ 下。
        assert not (orphan / ARTIFACT_BACKUP_DIR).exists()
        moved = root / QUARANTINE_DIR / "tenant-a" / "project-a" / "artifact-orphan"
        assert (moved / ARTIFACT_BACKUP_DIR).read_bytes() == b"payload"
        # 有记录的产物**不**被动。
        assert (known / ARTIFACT_BACKUP_DIR).is_file()
        # 重复运行是幂等的（quarantine/ 不再被扫描）。
        assert await service.collect_garbage() == 0
        assert (moved / ARTIFACT_BACKUP_DIR).is_file()

    asyncio.run(_run())


def test_retention_cleanup_deletes_only_expired_artifact_rows(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """门槛 ④（`docs/02` §29）：只删过期产物**元数据行**；未装配的源返回 0。"""
    now = datetime(2026, 10, 5, tzinfo=UTC)

    async def _run() -> None:
        await _seeded_database(engine)
        store = _FakeArtifactStore(
            [
                _record("artifact-old", created_at=now - timedelta(days=400)),
                _record("artifact-fresh", created_at=now - timedelta(days=1)),
            ]
        )
        service = RetentionService(
            artifacts=store,
            storage=tmp_path / "storage",
            clock=lambda: now,
        )
        assert service.configured() == ("artifacts",)
        assert await service.cleanup_artifacts() == 1
        assert store.ids() == ("artifact-fresh",)
        # 未装配的类别仍然返回 0（`docs/02` §29 的逐类方法都要存在）。
        assert await service.cleanup_tasks() == 0
        assert await service.cleanup_traces() == 0
        assert await service.cleanup_events() == 0
        assert await service.cleanup_sessions() == 0
        report = await service.cleanup_all()
        assert set(report.cleaned) == {"tasks", "traces", "events", "artifacts", "sessions"}
        assert report.cleaned["artifacts"] == 0

    asyncio.run(_run())


class _FakeTaskRetention:
    """`TaskRetentionSource` 结构替身（`docs/02` §29）。"""

    def __init__(self, removed: int) -> None:
        self.removed = removed
        self.cutoffs: list[datetime] = []

    async def delete_finished_before(self, cutoff: datetime) -> int:
        self.cutoffs.append(cutoff)
        return self.removed


class _FakeSessionRetention:
    """`SessionRetentionSource` 结构替身（`docs/02` §29）。"""

    def __init__(self, removed: int) -> None:
        self.removed = removed
        self.cutoffs: list[datetime] = []

    async def delete_expired_before(self, cutoff: datetime) -> int:
        self.cutoffs.append(cutoff)
        return self.removed


def test_retention_uses_the_policy_cutoff_for_tasks_and_sessions() -> None:
    """门槛 ④（`docs/02` §27 / §29）：截止时刻 = now − `retention_days`。"""
    now = datetime(2026, 10, 5, tzinfo=UTC)

    async def _run() -> None:
        tasks = _FakeTaskRetention(removed=4)
        sessions = _FakeSessionRetention(removed=2)
        service = RetentionService(
            policy=RetentionPolicy(task_days=30, session_days=7),
            tasks=tasks,
            clock=lambda: now,
        )
        assert service.policy.task_days == 30
        assert await service.cleanup_tasks() == 4
        assert tasks.cutoffs == [now - timedelta(days=30)]
        assert await service.cleanup_sessions(sessions=sessions) == 2
        assert sessions.cutoffs == [now - timedelta(days=7)]
        # 未传 sessions → 0（不假装清理过）。
        assert await service.cleanup_sessions() == 0

    asyncio.run(_run())


# ===== ⑤ 健康（`docs/02` §16.1–§16.3 / §94；`docs/07` §14.4）=====


def test_health_paths_and_check_tuples_match_the_spec_copies() -> None:
    """门槛 ⑤（`docs/02` §16 / §94）：三个绝对路径与两个检查元组逐字匹配规范副本。"""
    assert LIVENESS_PATH == HEALTH_PATHS_SPEC["liveness"]
    assert READINESS_PATH == HEALTH_PATHS_SPEC["readiness"]
    assert HEALTH_PATH == HEALTH_PATHS_SPEC["health"]
    assert READINESS_CHECKS == READINESS_CHECKS_SPEC
    assert HEALTH_CHECKS == HEALTH_CHECKS_SPEC
    assert HEALTH_STAGE == "health"
    assert READY == "READY"
    assert NOT_READY == "NOT_READY"
    assert STATUS_KEY == "status"
    # 就绪词表与 HealthStatus 词表**不**混用（`docs/02` §16.2 vs §94）。
    statuses = {status.value for status in HealthStatus}
    assert statuses == {"HEALTHY", "DEGRADED", "UNAVAILABLE"}
    assert READY not in statuses
    assert NOT_READY not in statuses


def test_liveness_never_consults_the_registry() -> None:
    """门槛 ⑤（`docs/02` §16.1）：注册表全挂，`liveness` 仍然 `HEALTHY`。"""
    registry = HealthRegistry()

    async def _boom() -> Mapping[str, Any]:
        raise RuntimeError("connection refused: sqlite:///secret.db")

    for name in READINESS_CHECKS_SPEC:
        registry.register(name, CallableHealthChecker(name, _boom))
    service = HealthService(registry)

    async def _run() -> None:
        assert await service.liveness() == {STATUS_KEY: HealthStatus.HEALTHY}
        # 反过来：/readyz 与 /health 会如实反映失败（不是被 liveness 掩盖）。
        assert (await service.readiness())[STATUS_KEY] == NOT_READY
        assert (await service.health())[STATUS_KEY] == HealthStatus.UNAVAILABLE

    asyncio.run(_run())


def test_readiness_is_not_ready_when_registry_is_not_healthy() -> None:
    """门槛 ⑤（`docs/07` §14.4）：Registry 不 HEALTHY → **MUST NOT** become READY。"""
    registry = HealthRegistry()
    registry.register("database", _checker("database", HealthStatus.HEALTHY))
    registry.register("task_engine", _checker("task_engine", HealthStatus.HEALTHY))
    registry.register("registry", _checker("registry", HealthStatus.UNAVAILABLE))
    service = HealthService(registry)

    async def _run() -> None:
        payload = await service.readiness()
        assert payload[STATUS_KEY] == NOT_READY
        assert is_ready_status(payload) is False
        assert payload["checks"]["registry"][STATUS_KEY] == HealthStatus.UNAVAILABLE

    asyncio.run(_run())


def test_readiness_is_ready_only_when_all_critical_checks_are_healthy() -> None:
    """门槛 ⑤（`docs/02` §16.2 / §94）：三个关键检查全 HEALTHY → `READY`。"""
    registry = HealthRegistry()
    for name in READINESS_CHECKS_SPEC:
        registry.register(name, _checker(name, HealthStatus.HEALTHY))
    service = HealthService(registry)

    async def _run() -> None:
        payload = await service.readiness()
        assert payload == {STATUS_KEY: READY}
        assert is_ready_status(payload) is True
        # 任一关键检查 DEGRADED 也不算就绪。
        broken = HealthRegistry()
        for name in READINESS_CHECKS_SPEC:
            status = HealthStatus.DEGRADED if name == "task_engine" else HealthStatus.HEALTHY
            broken.register(name, _checker(name, status))
        assert (await HealthService(broken).readiness())[STATUS_KEY] == NOT_READY

    asyncio.run(_run())


def test_readiness_treats_registry_as_critical_even_if_not_passed() -> None:
    """门槛 ⑤（`docs/07` §14.4）：`registry` 恒为关键检查（调用方漏传也不失效）。"""
    registry = HealthRegistry()
    registry.register("database", _checker("database", HealthStatus.HEALTHY))
    registry.register("registry", _checker("registry", HealthStatus.UNAVAILABLE))
    service = HealthService(registry, critical_checks=("database",))

    async def _run() -> None:
        assert "registry" in service.critical_checks
        assert (await service.readiness())[STATUS_KEY] == NOT_READY

    asyncio.run(_run())


def test_health_reports_degraded_when_only_an_adapter_is_down() -> None:
    """门槛 ⑤（`docs/02` §16.3 / §94）：🔴「单个软件不可用 ≠ Core DOWN」→ `DEGRADED`。"""
    registry = HealthRegistry()
    for name in READINESS_CHECKS_SPEC:
        registry.register(name, _checker(name, HealthStatus.HEALTHY))
    registry.register(
        "adapter_manager",
        CallableHealthChecker("adapter_manager", _healthy, critical=False),
    )
    registry.register(
        "software_instances",
        _checker("software_instances", HealthStatus.UNAVAILABLE, critical=False),
    )
    service = HealthService(registry)

    async def _run() -> None:
        payload = await service.health()
        assert payload[STATUS_KEY] == HealthStatus.DEGRADED
        assert payload["database"][STATUS_KEY] == HealthStatus.HEALTHY
        assert payload["task_engine"][STATUS_KEY] == HealthStatus.HEALTHY
        assert payload["registry"][STATUS_KEY] == HealthStatus.HEALTHY
        # `docs/02` §16.3 的三组键都在；`docs/02` §94 的五项检查里
        # `adapter_manager` / `software_instances` 归在 `adapters` 下。
        assert set(payload["adapters"]) == {"manager", "software_instances"}
        unavailable = payload["adapters"]["software_instances"][STATUS_KEY]
        assert unavailable == HealthStatus.UNAVAILABLE
        # 单个软件不可用**不**让整体不可用。
        assert payload[STATUS_KEY] != HealthStatus.UNAVAILABLE
        # `/readyz` 仍然是 READY（适配器不是关键依赖）。
        assert (await service.readiness())[STATUS_KEY] == READY

    asyncio.run(_run())


def test_health_reports_unavailable_when_the_database_is_down() -> None:
    """门槛 ⑤（`docs/02` §16.3 / §94）：关键检查失败 → `UNAVAILABLE`。"""
    registry = HealthRegistry()
    for name in READINESS_CHECKS_SPEC:
        status = HealthStatus.UNAVAILABLE if name == "database" else HealthStatus.HEALTHY
        registry.register(name, _checker(name, status))
    for name in ("adapter_manager", "software_instances"):
        registry.register(name, _checker(name, HealthStatus.HEALTHY, critical=False))
    service = HealthService(registry)

    async def _run() -> None:
        payload = await service.health()
        assert payload[STATUS_KEY] == HealthStatus.UNAVAILABLE
        assert payload["database"][STATUS_KEY] == HealthStatus.UNAVAILABLE
        assert (await service.readiness())[STATUS_KEY] == NOT_READY

    asyncio.run(_run())


def test_raising_checker_exposes_only_the_exception_class_name() -> None:
    """门槛 ⑤（`docs/07` §14.3）：抛异常的检查器只暴露**类名**（无消息、无连接串）。"""
    secret = "sqlite:///user:password@/data/structai.db"

    async def _boom() -> Mapping[str, Any]:
        raise RuntimeError(f"cannot open {secret}")

    registry = HealthRegistry()
    registry.register("database", CallableHealthChecker("database", _boom))
    service = HealthService(registry)

    async def _run() -> None:
        payload = await service.readiness()
        assert payload[STATUS_KEY] == NOT_READY
        database = payload["checks"]["database"]
        assert database[STATUS_KEY] == HealthStatus.UNAVAILABLE
        assert database["reason"] == "RuntimeError"
        # 🔴 异常消息（可能带连接串 / 口令）**绝不**进入响应体。
        raw = json.dumps(payload, default=str)
        assert secret not in raw
        assert "password" not in raw.lower()

    asyncio.run(_run())


def test_unregistered_checker_is_unavailable_not_silently_up() -> None:
    """门槛 ⑤（`docs/02` §16.2）：未装配的检查名 → `checker_not_registered`。"""
    registry = HealthRegistry()
    registry.register("database", _checker("database", HealthStatus.HEALTHY))
    service = HealthService(registry)

    async def _run() -> None:
        payload = await service.readiness()
        assert payload[STATUS_KEY] == NOT_READY
        missing = payload["checks"]["task_engine"]
        assert missing[STATUS_KEY] == HealthStatus.UNAVAILABLE
        assert missing["reason"] == "checker_not_registered"
        # 注册表层面同样如实报告。
        results = await registry.run(["nope"])
        assert results["nope"]["reason"] == "checker_not_registered"
        assert registry.get("nope") is None
        assert registry.names() == ("database",)

    asyncio.run(_run())


def test_health_registry_rejects_blank_and_duplicate_names() -> None:
    """门槛 ⑤（`docs/07` §11）：空名 / 重名 → 7000 `invalid_checker` / `duplicate_checker`。"""
    registry = HealthRegistry()
    with pytest.raises(InternalError) as blank:
        registry.register("   ", _checker("x", HealthStatus.HEALTHY))
    assert blank.value.code == "STRUCTAI-7000"
    assert blank.value.details == {"stage": "health", "reason": "invalid_checker"}
    registry.register("database", _checker("database", HealthStatus.HEALTHY))
    with pytest.raises(InternalError) as duplicate:
        registry.register("database", _checker("database", HealthStatus.HEALTHY))
    assert duplicate.value.details == {"stage": "health", "reason": "duplicate_checker"}


def test_health_registry_runs_checks_concurrently_and_never_raises() -> None:
    """门槛 ⑤（`docs/02` §17 / §94）：并发执行且**绝不**抛出；缺 `status` 视为不可用。"""

    async def _slow() -> Mapping[str, Any]:
        await asyncio.sleep(0.05)
        return {STATUS_KEY: HealthStatus.HEALTHY}

    async def _no_status() -> Mapping[str, Any]:
        return {"detail": "no status key"}

    registry = HealthRegistry()
    registry.register("database", CallableHealthChecker("database", _slow))
    registry.register("task_engine", CallableHealthChecker("task_engine", _slow))
    registry.register("registry", CallableHealthChecker("registry", _no_status))

    async def _run() -> None:
        loop = asyncio.get_running_loop()
        begin = loop.time()
        results = await registry.run(READINESS_CHECKS_SPEC)
        elapsed = loop.time() - begin
        assert set(results) == set(READINESS_CHECKS_SPEC)
        # 并发（两个 50ms 的检查串行会是 100ms 以上）。
        assert elapsed < 0.095, elapsed
        assert results["registry"][STATUS_KEY] == HealthStatus.UNAVAILABLE
        assert results["registry"]["reason"] == "status_missing"

    asyncio.run(_run())


def test_http_handlers_return_the_expected_dicts_without_a_server() -> None:
    """门槛 ⑤（`docs/02` §16 / §41 / §95）：三个处理器**不启动 HTTP 服务器**即可验收。"""
    registry = HealthRegistry()
    for name in READINESS_CHECKS_SPEC:
        registry.register(name, _checker(name, HealthStatus.HEALTHY))
    registry.register(
        "adapter_manager",
        CallableHealthChecker("adapter_manager", _healthy, critical=False),
    )
    registry.register(
        "software_instances",
        _checker("software_instances", HealthStatus.HEALTHY, critical=False),
    )
    service = HealthService(registry)

    async def _run() -> None:
        assert await livez(service) == {STATUS_KEY: HealthStatus.HEALTHY}
        assert await readyz(service) == {STATUS_KEY: READY}
        report = await health_report(service)
        assert report[STATUS_KEY] == HealthStatus.HEALTHY
        assert {"database", "task_engine", "adapters"} <= set(report)
        # 路由：三条绝对路径、全部 200（`NOT_READY` **不**映射成 HTTP 错误码）。
        router = create_health_router(service)
        assert HEALTH_ROUTER_PREFIX == ""
        assert HEALTH_ROUTER_TAG == "health"
        assert INTERFACE_STAGE == "health_api"
        routes = {str(getattr(route, "path", "")): route for route in router.routes}
        assert set(routes) == set(HEALTH_PATHS_SPEC.values())
        for route in routes.values():
            assert "GET" in getattr(route, "methods", set())
            assert getattr(route, "status_code", None) == 200
        # 未就绪时 `/readyz` 仍返回 200 + `NOT_READY` 体（负载均衡器读的是**体**）。
        broken = HealthRegistry()
        broken.register("database", _checker("database", HealthStatus.UNAVAILABLE))
        not_ready = await readyz(HealthService(broken))
        assert not_ready[STATUS_KEY] == NOT_READY
        for route in create_health_router(HealthService(broken)).routes:
            assert getattr(route, "status_code", None) == 200

    asyncio.run(_run())


def test_health_service_never_reports_a_connection_string() -> None:
    """门槛 ⑤（`docs/02` §46；`docs/07` §14.3）：响应体只含状态 / 原因 / 计数。"""
    registry = HealthRegistry()

    async def _task_engine() -> Mapping[str, Any]:
        return {STATUS_KEY: HealthStatus.HEALTHY, "active_tasks": 2}

    registry.register("database", _checker("database", HealthStatus.HEALTHY))
    registry.register("task_engine", CallableHealthChecker("task_engine", _task_engine))
    registry.register("registry", _checker("registry", HealthStatus.HEALTHY))
    service = HealthService(registry)

    async def _run() -> None:
        raw = json.dumps(await service.health(), default=str)
        lowered = raw.lower()
        for marker in SECRET_MARKERS:
            assert marker not in lowered, marker
        assert "://" not in raw

    asyncio.run(_run())


# ===== ⑥ 红线（`docs/07` §14.1 / §14.2 / §14.4）=====


def test_commit_and_rollback_only_in_unit_of_work() -> None:
    """门槛 ⑥（`docs/07` §14.4）：`commit()` / `rollback()` 只在 `unit_of_work.py`（AST）。"""
    committers = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in APP_DIR.rglob("*.py")
        if _commit_or_rollback_calls(path)
    )
    assert committers == ["app/infrastructure/database/unit_of_work.py"]
    for relative in MODULE_PATHS:
        assert _commit_or_rollback_calls(REPO_ROOT / relative) == [], relative


def test_no_vendor_name_appears_under_app() -> None:
    """门槛 ⑥（`docs/07` §14.2）：`app/` 内厂商名 0 处（大小写不敏感）。"""
    offenders: list[tuple[str, str]] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for vendor in VENDOR_NAMES:
            if vendor in text:
                offenders.append((path.relative_to(REPO_ROOT).as_posix(), vendor))
    assert offenders == []


def test_twenty_error_codes_are_not_extended() -> None:
    """门槛 ⑥（`docs/07` §11）：`app/` 内的 `STRUCTAI-xxxx` 字面量恰好是那 20 个码。"""
    declared: set[str] = set()
    for path in sorted(APP_DIR.rglob("*.py")):
        declared.update(re.findall(r"STRUCTAI-\d{4}", path.read_text(encoding="utf-8")))
    assert declared == set(ERROR_CODES_SPEC)
    assert len(ERROR_CODES_SPEC) == 20
    # 本批新增的异常都**不**携带新码。
    for error in (ArtifactError, InternalError, TaskError):
        assert error.code in ERROR_CODES_SPEC
    assert issubclass(ArtifactError, StructAIError)
    assert issubclass(TaskError, StructAIError)


def test_observability_layer_imports_no_framework() -> None:
    """门槛 ⑥（`docs/07` §14.1）：`app/observability/**` 不 import SQLAlchemy / FastAPI。"""
    forbidden = ("sqlalchemy", "fastapi", "mcp", "httpx")
    offenders: list[tuple[str, str]] = []
    for path in _python_files(OBSERVABILITY_DIR):
        if path.name == "__init__.py":
            continue
        for name in _imported_modules(path):
            if name.split(".")[0] in forbidden:
                offenders.append((path.name, name))
    assert offenders == []
    # 本批的 `health.py` 只依赖标准库与 `app.domain`。
    modules = _imported_modules(OBSERVABILITY_DIR / "health.py")
    modules = _imported_modules(OBSERVABILITY_DIR / "health.py")
    assert sorted(name for name in modules if name.startswith("app.")) == [
        "app.domain.enums",
        "app.domain.errors",
        "app.domain.protocols",
    ]


def test_interfaces_layer_imports_no_sqlalchemy() -> None:
    """门槛 ⑥（`docs/07` §14.1）：`app/interfaces/**` 不 import SQLAlchemy。"""
    offenders: list[tuple[str, str]] = []
    for path in _python_files(INTERFACES_DIR):
        for name in _imported_modules(path):
            if name.split(".")[0] in ("sqlalchemy", "app.infrastructure"):
                offenders.append((path.name, name))
    assert offenders == []
    # Interface 层**允许** FastAPI（`docs/07` §3.1），且确实用了它。
    assert "fastapi" in _imported_modules(INTERFACES_DIR / "http" / "health.py")


def test_new_modules_do_not_depend_on_infrastructure_or_interfaces() -> None:
    """门槛 ⑥（`docs/07` §14.1）：Application 服务不依赖 infrastructure / interfaces。"""
    for relative in (
        "app/application/services/quota.py",
        "app/application/services/backup.py",
    ):
        modules = _imported_modules(REPO_ROOT / relative)
        forbidden = [
            name
            for name in modules
            if name.startswith(("app.infrastructure", "app.interfaces", "app.observability"))
        ]
        assert forbidden == [], relative


def test_new_modules_never_record_secrets() -> None:
    """门槛 ⑥（`docs/07` §14.3）：新模块的记录字段名不含敏感词；提及只出现在否定式说明里。"""
    for relative in MODULE_PATHS:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8").lower()
        for marker in SECRET_MARKERS:
            if marker not in text:
                continue
            assert "不得" in text or "绝不" in text or "没有" in text, (relative, marker)
