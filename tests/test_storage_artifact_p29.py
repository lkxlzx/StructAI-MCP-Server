"""P29 验收：Artifact Storage（`docs/07` §12 P29；`docs/02` §3.3–§3.6 / §29 / §33 / §49 / §55）。

验收点（与任务卡的断言清单一一对应）：

① **完整性**（`docs/02` §3.6 / §84）：`put` → `sha256_bytes` → 读回 → 文件级 `checksum()`
   与内存级摘要**同值**（`checksum(original) == checksum(read)`）；`sha256_stream` 与
   `sha256_bytes` 一致。
② **元数据与内容分离**（`docs/07` §4.3 #21；`docs/02` §29 / §33）：DB 行里**没有** payload
   字节，且列集合**恰好**是冻结的 `artifacts` 列集合（9 列，未改表）。
③ **失败语义**（`docs/02` §49）：missing payload → `STRUCTAI-6200` `missing_payload`；
   corrupted payload → `verify()` 返回 `False`；orphan payload（有文件无库行）可被检出。
④ **租户隔离**（`docs/02` §48 / §49）：跨租户 → `STRUCTAI-4200`，且与「不存在」**同形**
   （`to_dict()` 逐字段相等，不泄露存在性）。
⑤ **路径安全**（`docs/02` §3.4 / §56）：`..` / 绝对键 / 反斜杠 → `STRUCTAI-6200`；
   用户提供的文件名**绝不**成为路径。
⑥ **唯一性**（`docs/02` §49 的 `duplicate`）：同样字节的两次 `create` 得到不同
   `artifact_id` / 不同 `storage_key`。
⑦ **生命周期**（`docs/02` §30 / §49）：`exists`；`delete` 幂等（存储层）；`delete` 顺序
   = **DB 行 → 载荷**。
⑧ **凭据**（`docs/07` §8.5 / §14.3）：缺失 → `STRUCTAI-7000`；`repr` 不含值；
   `references()` 只给名字；`set_secret` / `delete_secret` → `RuntimeError`；
   `sanitize_mapping` 递归丢弃敏感键。
⑨ **进程内锁**（`docs/02` §8 / §36 / §38）：`asyncio.gather` 下**恰好一个**赢家；
   超时 → `STRUCTAI-6100`；`hold()` 在异常路径也释放；重复释放无害。
⑩ **通知**（`docs/02` §35 / §45 / §59）：未知通道 → `False` 且**不抛**；
   `subscribe(bus)` + `bus.publish(TaskProgress(...))` → **恰好一条**投递。
⑪ **红线**：`commit` / `rollback` 只出现在 `unit_of_work.py`（AST 级）；`app/` 内
   厂商名 0 处；`STRUCTAI-xxxx` 恰好 **20** 码；`artifacts` 列集合与 24 张表均未变；
   `app/application/**` **不**依赖 `app.infrastructure`。

⚠️ 本文件里的「规范原文副本」（存储键模板 / `artifacts` 列集合 / 24 张表 / 20 码清单 /
敏感键词表 / 常量 300 秒）**故意不**从被测模块取：若断言只与被测常量比较，
「常量被改错」与「实现被改错」会一起通过（同源循环）。
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import io
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.resource.lock_policy import (
    DEFAULT_LOCK_TIMEOUT_SECONDS as POLICY_LOCK_TIMEOUT_SECONDS,
)
from app.application.services.artifact import ARTIFACT_BACKEND_LOCAL, ArtifactService
from app.config.settings import Settings
from app.domain.errors import (
    ArtifactError,
    InternalError,
    ResourceLockedError,
    TenantAccessDeniedError,
)
from app.domain.events import DomainEvent, TaskProgress
from app.domain.protocols import (
    ArtifactDraft,
    ArtifactRecord,
    ArtifactStorage,
    ArtifactStore,
    EventBus,
    EventHandler,
    NotificationMessage,
    NotificationSink,
)
from app.infrastructure.database import Base, create_session_factory
from app.infrastructure.database.models.artifact import ArtifactORM
from app.infrastructure.database.repositories.artifact import build_artifact_store
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.infrastructure.locks.in_memory import (
    DEFAULT_LOCK_TIMEOUT_SECONDS,
    InMemoryLock,
    InMemoryLockHandle,
)
from app.infrastructure.notifications.service import (
    IN_PROCESS_CHANNEL,
    TASK_PROGRESS_EVENT_TYPE,
    InProcessNotificationSink,
    NotificationService,
)
from app.infrastructure.secrets.base import (
    REDACTION_MARKER,
    SENSITIVE_KEY_PARTS,
    looks_sensitive,
    redact_value,
    sanitize_mapping,
)
from app.infrastructure.secrets.environment import (
    ENVIRONMENT_REFERENCE_PREFIX,
    EnvironmentCredentialProvider,
)
from app.infrastructure.storage.base import (
    CHECKSUM_LENGTH,
    MISSING_PROJECT_SEGMENT,
    PAYLOAD_FILENAME,
    STORAGE_STAGE,
    artifact_of_storage_key,
    relative_storage_path,
    sanitize_filename,
    sha256_bytes,
    sha256_stream,
    storage_key_for,
    storage_key_segments,
    tenant_of_storage_key,
)
from app.infrastructure.storage.local import BACKEND_NAME, LocalFilesystemStorage
from app.infrastructure.storage.manager import (
    DEFAULT_BACKEND_NAME,
    ArtifactStorageManager,
    build_local_storage,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
APPLICATION_DIR = APP_DIR / "application"

# ===== 规范原文副本（`docs/02` §3.5 / §49；`docs/07` §4.3 #21 / §11）=====

TENANT_ID = "11111111-1111-4111-8111-111111111111"
OTHER_TENANT_ID = "22222222-2222-4222-8222-222222222222"
PROJECT_ID = "33333333-3333-4333-8333-333333333333"
TASK_ID = "44444444-4444-4444-8444-444444444444"

PAYLOAD_BYTES = b'{"marker":"artifact payload 7c41","values":[1,2,3]}'
"""带特征串的产物字节（用于证明「payload 不进数据库」）。"""

PAYLOAD_MARKER = "artifact payload 7c41"

STORAGE_KEY_TEMPLATE_SPEC = "{tenant_id}/{project_id}/{artifact_id}/payload"
"""`docs/02` §3.5 的存储键模板（逐字抄写）。"""

STORAGE_KEY_MISSING_PROJECT_SPEC = "{tenant_id}/-/{artifact_id}/payload"
"""`project_id` 缺失时的键形状（`docs/02` §3.5 + 本批裁决的 `-` 占位）。"""

ARTIFACT_COLUMNS_SPEC = (
    "id",
    "task_id",
    "storage_backend",
    "storage_key",
    "mime_type",
    "size",
    "checksum",
    "created_at",
    "updated_at",
)
"""`docs/07` §4.3 #21 的 `artifacts` 列集合（逐列抄写；本批**不得改表**）。"""

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

SENSITIVE_KEY_PARTS_SPEC = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "api-key",
    "private_key",
    "privatekey",
    "credential",
    "mapi",
    "mcp_key",
    "authorization",
)
"""`docs/07` §8.5 / §14.3 的敏感键词表（逐字抄写）。"""

VENDOR_NAMES = ("MIDAS", "CSI", "ANSYS", "SAP2000", "ETABS", "OpenSees")
"""`docs/07` §14.2：`app/` 内不得出现的厂商名。"""

LOCK_TIMEOUT_SPEC = 300
"""`docs/07` §3.1 / §4.3 #22 的默认锁租约（秒；逐字抄写）。"""


# ===== 夹具与辅助 =====


def _storage(tmp_path: Path) -> LocalFilesystemStorage:
    """一个绑定临时目录的本地后端（`docs/02` §3.4）。"""
    return LocalFilesystemStorage(tmp_path / "artifacts")


def _session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """`tests/conftest.py` 同一口径的会话工厂（`docs/02` §15）。"""
    return create_session_factory(engine)


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


class _OrderLog:
    """记录跨层调用顺序的日志（用于 `delete` 顺序断言）。"""

    def __init__(self) -> None:
        self.entries: list[str] = []


class _OrderLogStore:
    """`ArtifactStore` 的顺序日志包装（`docs/02` §3.2）。"""

    def __init__(self, inner: ArtifactStore, log: _OrderLog) -> None:
        self._inner = inner
        self._log = log

    async def create(self, draft: ArtifactDraft) -> ArtifactRecord:
        """透传创建。"""
        return await self._inner.create(draft)

    async def get(self, artifact_id: str) -> ArtifactRecord | None:
        """透传读取。"""
        return await self._inner.get(artifact_id)

    async def delete(self, artifact_id: str) -> bool:
        """记录后透传删除（`docs/02` §30 的「DB 行先删」）。"""
        self._log.entries.append("store.delete")
        return await self._inner.delete(artifact_id)

    async def list_for_task(self, task_id: str) -> Sequence[ArtifactRecord]:
        """透传按任务列出。"""
        return await self._inner.list_for_task(task_id)

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> Sequence[ArtifactRecord]:
        """透传分页列出。"""
        return await self._inner.list_all(limit=limit, offset=offset)


class _OrderLogStorage:
    """`ArtifactStorage` 的顺序日志包装（`docs/02` §29 / §33）。"""

    def __init__(self, inner: ArtifactStorage, log: _OrderLog) -> None:
        self._inner = inner
        self._log = log

    async def put(self, data: bytes, metadata: Mapping[str, Any]) -> str:
        """透传写入。"""
        return await self._inner.put(data, metadata)

    async def get(self, artifact_id: str) -> bytes:
        """透传读取。"""
        return await self._inner.get(artifact_id)

    async def delete(self, artifact_id: str) -> None:
        """记录后透传删除（`docs/02` §30 的「载荷后删」）。"""
        self._log.entries.append("storage.delete")
        await self._inner.delete(artifact_id)


class _RecordingBus:
    """记录订阅的假事件总线（`docs/02` §34 的 Domain `EventBus` 结构替身）。"""

    def __init__(self) -> None:
        self.handlers: dict[type[DomainEvent], EventHandler] = {}

    async def publish(self, event: DomainEvent) -> None:
        """把事件交给已注册的处理器（无处理器则丢弃）。"""
        handler = self.handlers.get(type(event))
        if handler is not None:
            await handler(event)

    async def subscribe(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        """登记处理器（`docs/02` §34）。"""
        self.handlers[event_type] = handler


class _FailingSink:
    """投递必失败的出口（用于「通知失败不得影响业务结果」，`docs/07` §14.4）。"""

    def __init__(self) -> None:
        self.calls: list[NotificationMessage] = []

    async def deliver(self, message: NotificationMessage) -> None:
        """记录后抛出。"""
        self.calls.append(message)
        raise RuntimeError("sink is down")


# ===== ① 摘要与存储键（`docs/02` §3.5 / §3.6）=====


def test_sha256_stream_matches_the_spec_implementation() -> None:
    """门槛 ①（`docs/02` §3.6）：`sha256_stream` 是分块实现，结果与 `hashlib` 逐字一致。"""
    expected = hashlib.sha256(PAYLOAD_BYTES).hexdigest()
    assert sha256_stream(io.BytesIO(PAYLOAD_BYTES)) == expected
    assert len(expected) == CHECKSUM_LENGTH
    assert sha256_bytes(PAYLOAD_BYTES) == expected


def test_storage_key_follows_the_frozen_template() -> None:
    """门槛 ①/⑤（`docs/02` §3.5）：存储键逐段等于规范模板，且末段固定是 `payload`。"""
    key = storage_key_for(tenant_id=TENANT_ID, project_id=PROJECT_ID, artifact_id="artifact-1")
    assert key == STORAGE_KEY_TEMPLATE_SPEC.format(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        artifact_id="artifact-1",
    )
    assert key.endswith(f"/{PAYLOAD_FILENAME}")
    assert PAYLOAD_FILENAME == "payload"
    assert storage_key_segments(key) == (TENANT_ID, PROJECT_ID, "artifact-1", PAYLOAD_FILENAME)
    assert tenant_of_storage_key(key) == TENANT_ID
    assert artifact_of_storage_key(key) == "artifact-1"


def test_storage_key_uses_the_missing_project_segment() -> None:
    """门槛 ①（`docs/02` §3.5）：`project_id = None` → `-` 占位段（不留空段）。"""
    key = storage_key_for(tenant_id=TENANT_ID, project_id=None, artifact_id="artifact-2")
    assert key == STORAGE_KEY_MISSING_PROJECT_SPEC.format(
        tenant_id=TENANT_ID,
        artifact_id="artifact-2",
    )
    assert MISSING_PROJECT_SEGMENT == "-"
    assert "//" not in key
    assert artifact_of_storage_key("tenant/payload") == "tenant"
    assert artifact_of_storage_key("payload") is None
    assert artifact_of_storage_key("tenant/artifact/other") is None
    assert artifact_of_storage_key("tenant/artifact/payload") == "artifact"
    assert tenant_of_storage_key("") is None


def test_sanitize_filename_strips_paths_and_unsafe_characters() -> None:
    """门槛 ⑤（`docs/02` §3.4 / §56）：用户文件名被清洗为安全标签，绝不带路径。"""
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\windows\\system32\\config") == "config"
    assert sanitize_filename("my report (final).pdf") == "my_report__final_.pdf"
    assert sanitize_filename("....") == "artifact"
    assert sanitize_filename("") == "artifact"
    for dirty in ("../x", "/etc/passwd", "a\\b", "..", ".hidden", "a b/c d"):
        cleaned = sanitize_filename(dirty)
        assert "/" not in cleaned
        assert "\\" not in cleaned
        assert not cleaned.startswith(".")


def test_sanitize_filename_caps_length() -> None:
    """门槛 ⑤（`docs/02` §56）：清洗结果被截断到 128 字符。"""
    cleaned = sanitize_filename("a" * 500 + ".txt")
    assert len(cleaned) == 128
    assert cleaned == "a" * 128


def test_relative_storage_path_rejects_traversal() -> None:
    """门槛 ⑤（`docs/02` §3.4 / §56）：`..` / 绝对键 / 反斜杠 / 空段 → `STRUCTAI-6200`。"""
    assert relative_storage_path("a/b/payload").as_posix() == "a/b/payload"
    for bad in (
        "../outside/payload",
        "tenant/../../etc/passwd",
        "/etc/passwd",
        "tenant\\artifact\\payload",
        "tenant//payload",
        "",
    ):
        with pytest.raises(ArtifactError) as excinfo:
            relative_storage_path(bad)
        assert excinfo.value.code == "STRUCTAI-6200"
        assert excinfo.value.details == {
            "stage": STORAGE_STAGE,
            "reason": "invalid_storage_key",
        }


# ===== ② 本地后端（`docs/02` §3.3 / §3.4 / §3.6 / §56）=====


def test_local_backend_put_read_checksum_roundtrip(tmp_path: Path) -> None:
    """门槛 ①（`docs/02` §3.6 / §84）：`put` → 读回 → 文件级校验值 == 内存级摘要。"""

    async def _run() -> None:
        storage = _storage(tmp_path)
        key = await storage.put(
            PAYLOAD_BYTES,
            {"tenant_id": TENANT_ID, "project_id": PROJECT_ID, "artifact_id": "artifact-1"},
        )
        assert key == storage_key_for(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            artifact_id="artifact-1",
        )
        assert await storage.get(key) == PAYLOAD_BYTES
        assert await storage.get("artifact-1") == PAYLOAD_BYTES
        assert await storage.checksum(key) == sha256_bytes(PAYLOAD_BYTES)
        assert await storage.exists(key) is True
        assert await storage.exists("artifact-1") is True
        assert await storage.exists("nope") is False

    asyncio.run(_run())


def test_local_backend_constructor_does_not_create_directories(tmp_path: Path) -> None:
    """门槛 ⑤（`docs/02` §3.4）：构造后端**不**做 I/O、**不**建目录。"""
    root = tmp_path / "artifacts"
    storage = _storage(tmp_path)
    assert storage.root == root.resolve()
    assert not root.exists()
    assert storage.chunk_size > 0
    assert PAYLOAD_MARKER not in repr(storage)
    with pytest.raises(ValueError):
        LocalFilesystemStorage(root, chunk_size=0)


def test_local_backend_put_stream_and_get_stream(tmp_path: Path) -> None:
    """门槛 ①（`docs/02` §3.3）：流式写入返回键；流式读取可读回同一字节。"""

    async def _run() -> None:
        storage = LocalFilesystemStorage(tmp_path / "artifacts", chunk_size=4)
        key = storage_key_for(tenant_id=TENANT_ID, project_id=None, artifact_id="artifact-3")
        returned = await storage.put_stream(key, io.BytesIO(PAYLOAD_BYTES))
        assert returned == key
        handle = await storage.get_stream(key)
        try:
            assert handle.read() == PAYLOAD_BYTES
        finally:
            handle.close()
        assert await storage.checksum(key) == sha256_bytes(PAYLOAD_BYTES)
        assert storage.chunk_size == 4

    asyncio.run(_run())


def test_local_backend_missing_payload_is_structai_6200(tmp_path: Path) -> None:
    """门槛 ③（`docs/02` §49）：missing payload → `STRUCTAI-6200` `missing_payload`。"""

    async def _run() -> None:
        storage = _storage(tmp_path)
        for call in (
            storage.get("absent-artifact"),
            storage.checksum("absent-artifact"),
            storage.get(f"{TENANT_ID}/{PROJECT_ID}/absent/{PAYLOAD_FILENAME}"),
        ):
            with pytest.raises(ArtifactError) as excinfo:
                await call
            assert excinfo.value.code == "STRUCTAI-6200"
            assert excinfo.value.details == {
                "stage": STORAGE_STAGE,
                "reason": "missing_payload",
            }

    asyncio.run(_run())


def test_local_backend_requires_metadata(tmp_path: Path) -> None:
    """门槛 ②/⑤（`docs/02` §33）：元数据不足以定位键 → `STRUCTAI-6200` `invalid_metadata`。"""

    async def _run() -> None:
        storage = _storage(tmp_path)
        for metadata in ({}, {"tenant_id": TENANT_ID}, {"artifact_id": "artifact-1"}):
            with pytest.raises(ArtifactError) as excinfo:
                await storage.put(PAYLOAD_BYTES, metadata)
            assert excinfo.value.details["reason"] == "invalid_metadata"

    asyncio.run(_run())


def test_local_backend_delete_is_idempotent_and_prunes_directories(tmp_path: Path) -> None:
    """门槛 ⑦（`docs/02` §30）：删除幂等，并剪掉空目录（不含 root）。"""

    async def _run() -> None:
        storage = _storage(tmp_path)
        key = await storage.put(
            PAYLOAD_BYTES,
            {"tenant_id": TENANT_ID, "project_id": PROJECT_ID, "artifact_id": "artifact-1"},
        )
        path = storage.path_for(key)
        assert path.is_file()
        await storage.delete(key)
        assert not path.is_file()
        assert not path.parent.exists()
        assert storage.root.exists()
        # 幂等：第二次删除（键形式与裸 id 形式）都不抛。
        await storage.delete(key)
        await storage.delete("artifact-1")
        assert await storage.exists(key) is False

    asyncio.run(_run())


def test_local_backend_path_for_rejects_traversal(tmp_path: Path) -> None:
    """门槛 ⑤（`docs/02` §3.4 / §56）：`path_for` 拒绝一切逃出 root 的键。"""
    storage = _storage(tmp_path)
    for bad in ("../x/payload", "/etc/passwd", "a\\b\\payload"):
        with pytest.raises(ArtifactError) as excinfo:
            storage.path_for(bad)
        assert excinfo.value.code == "STRUCTAI-6200"
    assert storage.path_for(f"{TENANT_ID}/{PROJECT_ID}/a/{PAYLOAD_FILENAME}").is_relative_to(
        storage.root
    )


# ===== ③ 存储后端注册表（`docs/02` §29 / §33）=====


def test_storage_manager_registers_and_routes(tmp_path: Path) -> None:
    """门槛 ⑦（`docs/02` §29 / §33）：注册表按名字路由，直通 put/get/exists/checksum。"""

    async def _run() -> None:
        manager = build_local_storage(tmp_path / "artifacts")
        assert manager.default_backend == DEFAULT_BACKEND_NAME == BACKEND_NAME == "local"
        assert manager.backend_names() == ("local",)
        key = await manager.put(
            PAYLOAD_BYTES,
            {
                "storage_key": storage_key_for(
                    tenant_id=TENANT_ID, project_id=None, artifact_id="a1"
                )
            },
        )
        assert await manager.exists(key, backend="local") is True
        assert await manager.get(key) == PAYLOAD_BYTES
        assert await manager.checksum(key) == sha256_bytes(PAYLOAD_BYTES)
        await manager.delete(key)
        assert await manager.exists(key) is False

    asyncio.run(_run())


def test_storage_manager_rejects_blank_duplicate_and_unknown(tmp_path: Path) -> None:
    """门槛 ⑦（`docs/07` §11）：空白 / 重复 / 未知后端一律 `STRUCTAI-7000`，不静默回落。"""
    manager = ArtifactStorageManager()
    backend = LocalFilesystemStorage(tmp_path / "artifacts")
    manager.register("local", backend)
    with pytest.raises(InternalError) as blank:
        manager.register("  ", backend)
    assert blank.value.code == "STRUCTAI-7000"
    assert blank.value.details["reason"] == "invalid_backend"
    with pytest.raises(InternalError) as duplicate:
        manager.register("local", backend)
    assert duplicate.value.details["reason"] == "duplicate_backend"
    with pytest.raises(InternalError) as unknown:
        manager.backend("object-store")
    assert unknown.value.details["reason"] == "unknown_backend"
    with pytest.raises(InternalError):
        ArtifactStorageManager(default_backend="absent").backend()


# ===== ④ 产物服务（`docs/02` §29 / §33 / §49 / §84）=====


def test_artifact_service_create_roundtrip(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """门槛 ①/⑥（`docs/02` §33 / §84）：创建 → 读回 → 校验，且键与规范模板一致。"""

    async def _run() -> None:
        async with UnitOfWork.from_session_factory(session_factory) as uow:
            storage = _storage(tmp_path)
            service = ArtifactService(build_artifact_store(uow.session), storage)
            record = await service.create(
                tenant_id=TENANT_ID,
                data=PAYLOAD_BYTES,
                mime_type="application/json",
                project_id=PROJECT_ID,
                task_id=TASK_ID,
            )
            assert record.id
            assert record.storage_backend == ARTIFACT_BACKEND_LOCAL == BACKEND_NAME
            assert record.storage_key == storage_key_for(
                tenant_id=TENANT_ID,
                project_id=PROJECT_ID,
                artifact_id=record.id,
            )
            assert record.mime_type == "application/json"
            assert record.size == len(PAYLOAD_BYTES)
            assert record.checksum == sha256_bytes(PAYLOAD_BYTES)
            assert record.task_id == TASK_ID
            assert record.created_at is not None
            assert record.id == artifact_of_storage_key(record.storage_key)
            # ① 文件级校验值 == 记录里的校验值 == 内存级摘要。
            assert await storage.checksum(record.storage_key) == record.checksum
            assert await service.verify(record) is True
            assert await service.read(record.id, tenant_id=TENANT_ID) == PAYLOAD_BYTES
            assert (await service.info(record.id, tenant_id=TENANT_ID)).id == record.id

    asyncio.run(_run())


def test_artifact_row_holds_no_payload_bytes_and_the_frozen_columns(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """门槛 ②（`docs/07` §4.3 #21；`docs/02` §29 / §33）：DB 行只有元数据，列集合冻结。"""

    async def _run() -> None:
        factory = _session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            storage = _storage(tmp_path)
            service = ArtifactService(build_artifact_store(uow.session), storage)
            await service.create(
                tenant_id=TENANT_ID,
                data=PAYLOAD_BYTES,
                mime_type="application/json",
                project_id=PROJECT_ID,
            )
            result = await uow.session.execute(select(ArtifactORM))
            row = result.scalars().one()
            assert set(ArtifactORM.__table__.columns.keys()) == set(ARTIFACT_COLUMNS_SPEC)
            values = [str(getattr(row, name)) for name in ARTIFACT_COLUMNS_SPEC]
            assert all(PAYLOAD_MARKER not in value for value in values)
            assert row.size == len(PAYLOAD_BYTES)
            assert row.storage_backend == ARTIFACT_BACKEND_LOCAL
            assert row.storage_key.endswith(f"/{PAYLOAD_FILENAME}")

    asyncio.run(_run())


def test_artifact_service_create_without_project_uses_the_placeholder_segment(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """门槛 ①（`docs/02` §3.5）：无项目的产物（手工上传 / 导出）用 `-` 占位段。"""

    async def _run() -> None:
        factory = _session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            storage = _storage(tmp_path)
            service = ArtifactService(build_artifact_store(uow.session), storage)
            record = await service.create(
                tenant_id=TENANT_ID,
                data=PAYLOAD_BYTES,
                mime_type="application/octet-stream",
            )
            assert record.storage_key == storage_key_for(
                tenant_id=TENANT_ID,
                project_id=None,
                artifact_id=record.id,
            )
            assert f"/{MISSING_PROJECT_SEGMENT}/" in record.storage_key
            assert record.task_id is None
            assert service.tenant_of(record) == TENANT_ID

    asyncio.run(_run())


def test_duplicate_bytes_get_distinct_ids_and_keys(engine: AsyncEngine, tmp_path: Path) -> None:
    """门槛 ⑥（`docs/02` §49 的 `duplicate`）：同样字节的两次创建不共享 id / key。"""

    async def _run() -> None:
        factory = _session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            storage = _storage(tmp_path)
            service = ArtifactService(build_artifact_store(uow.session), storage)
            first = await service.create(
                tenant_id=TENANT_ID,
                data=PAYLOAD_BYTES,
                mime_type="application/json",
                project_id=PROJECT_ID,
            )
            second = await service.create(
                tenant_id=TENANT_ID,
                data=PAYLOAD_BYTES,
                mime_type="application/json",
                project_id=PROJECT_ID,
            )
            assert first.id != second.id
            assert first.storage_key != second.storage_key
            assert first.checksum == second.checksum == sha256_bytes(PAYLOAD_BYTES)
            assert await service.read(first.id, tenant_id=TENANT_ID) == PAYLOAD_BYTES
            assert await service.read(second.id, tenant_id=TENANT_ID) == PAYLOAD_BYTES

    asyncio.run(_run())


def test_missing_payload_is_structai_6200(engine: AsyncEngine, tmp_path: Path) -> None:
    """门槛 ③（`docs/02` §49）：库行还在但载荷被删 → 读 / 校验都落 `6200`。"""

    async def _run() -> None:
        factory = _session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            storage = _storage(tmp_path)
            service = ArtifactService(build_artifact_store(uow.session), storage)
            record = await service.create(
                tenant_id=TENANT_ID,
                data=PAYLOAD_BYTES,
                mime_type="application/json",
                project_id=PROJECT_ID,
            )
            storage.path_for(record.storage_key).unlink()
            with pytest.raises(ArtifactError) as read_error:
                await service.read(record.id, tenant_id=TENANT_ID)
            assert read_error.value.code == "STRUCTAI-6200"
            assert read_error.value.details["reason"] == "missing_payload"
            with pytest.raises(ArtifactError) as verify_error:
                await service.verify(record)
            assert verify_error.value.details["reason"] == "missing_payload"

    asyncio.run(_run())


def test_corrupted_payload_makes_verify_false(engine: AsyncEngine, tmp_path: Path) -> None:
    """门槛 ③（`docs/02` §49 / §84）：载荷被篡改 → `verify()` 返回 `False`（不抛）。"""

    async def _run() -> None:
        factory = _session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            storage = _storage(tmp_path)
            service = ArtifactService(build_artifact_store(uow.session), storage)
            record = await service.create(
                tenant_id=TENANT_ID,
                data=PAYLOAD_BYTES,
                mime_type="application/json",
                project_id=PROJECT_ID,
            )
            path = storage.path_for(record.storage_key)
            path.write_bytes(PAYLOAD_BYTES + b"tampered")
            assert await service.verify(record) is False
            assert await storage.checksum(record.storage_key) != record.checksum

    asyncio.run(_run())


def test_orphan_payload_is_detectable(engine: AsyncEngine, tmp_path: Path) -> None:
    """门槛 ③（`docs/02` §49 的 `orphan payload`）：有文件无库行可被检出（GC 依据）。"""

    async def _run() -> None:
        factory = _session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            storage = _storage(tmp_path)
            store = build_artifact_store(uow.session)
            orphan_id = str(uuid4())
            key = await storage.put(
                PAYLOAD_BYTES,
                {"tenant_id": TENANT_ID, "project_id": PROJECT_ID, "artifact_id": orphan_id},
            )
            assert await storage.exists(key) is True
            assert await store.get(orphan_id) is None
            result = await uow.session.execute(select(ArtifactORM))
            assert list(result.scalars().all()) == []
            assert await store.list_all() == []

    asyncio.run(_run())


def test_tenant_isolation_is_indistinguishable_from_not_found(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """门槛 ④（`docs/02` §48 / §49）：跨租户与不存在**同形**（`4200`，逐字段相同）。"""

    async def _run() -> None:
        factory = _session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            storage = _storage(tmp_path)
            service = ArtifactService(build_artifact_store(uow.session), storage)
            record = await service.create(
                tenant_id=TENANT_ID,
                data=PAYLOAD_BYTES,
                mime_type="application/json",
                project_id=PROJECT_ID,
            )
            with pytest.raises(TenantAccessDeniedError) as foreign:
                await service.info(record.id, tenant_id=OTHER_TENANT_ID)
            with pytest.raises(TenantAccessDeniedError) as absent:
                await service.info(str(uuid4()), tenant_id=OTHER_TENANT_ID)
            assert foreign.value.code == "STRUCTAI-4200"
            assert foreign.value.message == "Tenant access denied"
            assert foreign.value.details == {"stage": "artifact", "reason": "tenant_mismatch"}
            assert foreign.value.to_dict() == absent.value.to_dict()
            with pytest.raises(TenantAccessDeniedError):
                await service.read(record.id, tenant_id=OTHER_TENANT_ID)
            with pytest.raises(TenantAccessDeniedError):
                await service.delete(record.id, tenant_id=OTHER_TENANT_ID)
            with pytest.raises(TenantAccessDeniedError):
                await service.info(record.id, tenant_id="")
            # 归属租户仍然可读（隔离不是「一律拒绝」）。
            assert await service.read(record.id, tenant_id=TENANT_ID) == PAYLOAD_BYTES

    asyncio.run(_run())


def test_artifact_service_delete_removes_row_first_then_payload(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """门槛 ⑦（`docs/02` §30）：删除顺序 = **DB 行 → 载荷**（顺序日志逐条断言）。"""

    async def _run() -> None:
        factory = _session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            log = _OrderLog()
            storage = _storage(tmp_path)
            service = ArtifactService(
                _OrderLogStore(build_artifact_store(uow.session), log),
                _OrderLogStorage(storage, log),
            )
            record = await service.create(
                tenant_id=TENANT_ID,
                data=PAYLOAD_BYTES,
                mime_type="application/json",
                project_id=PROJECT_ID,
            )
            log.entries.clear()
            assert await service.delete(record.id, tenant_id=TENANT_ID) is True
            assert log.entries == ["store.delete", "storage.delete"]
            assert not storage.path_for(record.storage_key).exists()
            assert await service.store.get(record.id) is None

    asyncio.run(_run())


def test_artifact_repository_lists_are_bounded_and_ordered(
    engine: AsyncEngine,
    tmp_path: Path,
) -> None:
    """门槛 ⑦（`docs/02` §3.2 / §22；`docs/07` §14.4）：列表有界、按 `created_at` 升序。"""

    async def _run() -> None:
        factory = _session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            storage = _storage(tmp_path)
            store = build_artifact_store(uow.session)
            service = ArtifactService(store, storage)
            first = await service.create(
                tenant_id=TENANT_ID,
                data=PAYLOAD_BYTES,
                mime_type="application/json",
                project_id=PROJECT_ID,
                task_id=TASK_ID,
            )
            second = await service.create(
                tenant_id=TENANT_ID,
                data=PAYLOAD_BYTES,
                mime_type="application/json",
                project_id=PROJECT_ID,
                task_id=TASK_ID,
            )
            for_task = await store.list_for_task(TASK_ID)
            assert {row.id for row in for_task} == {first.id, second.id}
            stamps = [str(row.created_at) for row in for_task]
            assert stamps == sorted(stamps)
            assert await store.list_for_task(str(uuid4())) == []
            assert len(await store.list_all(limit=1)) == 1
            assert len(await store.list_all()) == 2
            assert await store.delete(str(uuid4())) is False

    asyncio.run(_run())


def test_user_file_name_never_becomes_the_path(engine: AsyncEngine, tmp_path: Path) -> None:
    """门槛 ⑤（`docs/02` §3.4 / §56）：用户文件名只被清洗为标签，绝不进入路径。"""

    async def _run() -> None:
        factory = _session_factory(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            storage = _storage(tmp_path)
            service = ArtifactService(build_artifact_store(uow.session), storage)
            dirty = "../../etc/passwd"
            record = await service.create(
                tenant_id=TENANT_ID,
                data=PAYLOAD_BYTES,
                mime_type="application/octet-stream",
                project_id=PROJECT_ID,
            )
            cleaned = sanitize_filename(dirty)
            assert dirty not in record.storage_key
            assert cleaned not in record.storage_key
            assert record.storage_key == storage_key_for(
                tenant_id=TENANT_ID,
                project_id=PROJECT_ID,
                artifact_id=record.id,
            )
            path = storage.path_for(record.storage_key)
            assert path.name == PAYLOAD_FILENAME
            assert path.is_relative_to(storage.root)
            # 服务端签名里**没有** name 参数（`docs/02` §3.4；见服务模块裁决 3）。
            assert "name" not in ArtifactService.create.__annotations__

    asyncio.run(_run())


# ===== ⑤ 凭据（`docs/07` §8.5 / §14.3；`docs/02` §26）=====


def test_secret_provider_returns_values_and_names_only() -> None:
    """门槛 ⑧（`docs/02` §26）：已配置的引用返回值；`references()` 只给名字。"""
    secret_value = "s3cr3t-value-7c41"
    environ = {
        f"{ENVIRONMENT_REFERENCE_PREFIX}ALPHA": secret_value,
        f"{ENVIRONMENT_REFERENCE_PREFIX}ALPHA_BETA": "other",
        "UNRELATED": "ignored",
    }
    provider = EnvironmentCredentialProvider(environ)

    async def _run() -> None:
        assert await provider.get_secret("alpha") == secret_value
        assert await provider.get_secret("alpha.beta") == "other"
        assert provider.references() == ("alpha", "alpha_beta")
        assert secret_value not in provider.references()

    asyncio.run(_run())
    assert provider.prefix == ENVIRONMENT_REFERENCE_PREFIX
    assert EnvironmentCredentialProvider.variable_name_for("db.password") == (
        f"{ENVIRONMENT_REFERENCE_PREFIX}DB_PASSWORD"
    )


def test_secret_provider_missing_is_structai_7000_without_leaking() -> None:
    """门槛 ⑧（`docs/07` §8.5 / §14.3）：缺失 → `STRUCTAI-7000`，不回落空串、不带值。"""
    provider = EnvironmentCredentialProvider({f"{ENVIRONMENT_REFERENCE_PREFIX}EMPTY": "   "})

    async def _run() -> None:
        with pytest.raises(InternalError) as missing:
            await provider.get_secret("alpha")
        assert missing.value.code == "STRUCTAI-7000"
        assert missing.value.details == {
            "stage": "credentials",
            "reason": "secret_not_configured",
            "reference": "alpha",
        }
        # 空白等价于未配置。
        with pytest.raises(InternalError):
            await provider.get_secret("empty")
        # 引用名本身敏感时不回显引用名（只保留 stage / reason）。
        with pytest.raises(InternalError) as sensitive:
            await provider.get_secret("db.password")
        assert sensitive.value.details == {
            "stage": "credentials",
            "reason": "secret_not_configured",
        }

    asyncio.run(_run())


def test_secret_provider_repr_never_contains_the_value() -> None:
    """门槛 ⑧（`docs/07` §14.3）：`repr()` 只含前缀与数量，**绝不**含值。"""
    secret_value = "s3cr3t-value-7c41"
    provider = EnvironmentCredentialProvider({f"{ENVIRONMENT_REFERENCE_PREFIX}ALPHA": secret_value})
    text = repr(provider)
    assert secret_value not in text
    assert ENVIRONMENT_REFERENCE_PREFIX in text
    assert "1" in text
    assert redact_value(secret_value) == REDACTION_MARKER == "<redacted>"


def test_secret_provider_refuses_to_write_credentials() -> None:
    """门槛 ⑧（`docs/07` §8.5）：`set_secret` / `delete_secret` **显式拒绝**。"""
    provider = EnvironmentCredentialProvider({})

    async def _run() -> None:
        with pytest.raises(RuntimeError):
            await provider.set_secret("alpha", "value")
        with pytest.raises(RuntimeError):
            await provider.delete_secret("alpha")

    asyncio.run(_run())


def test_sensitive_key_parts_match_the_spec_and_sanitize_mapping_drops_them() -> None:
    """门槛 ⑧（`docs/07` §8.5 / §14.3）：敏感键词表逐条命中，清洗递归丢弃。"""
    assert SENSITIVE_KEY_PARTS == SENSITIVE_KEY_PARTS_SPEC
    for part in SENSITIVE_KEY_PARTS_SPEC:
        assert looks_sensitive(f"prefix_{part}_suffix") is True
        assert looks_sensitive(part.upper()) is True
    assert looks_sensitive("harmless") is False
    payload = {
        "tenant_id": TENANT_ID,
        "password": "p",
        "nested": {"api_key": "k", "keep": 1},
        "items": [{"authorization": "a", "keep": 2}, 3],
        "scalars": ["x", "y"],
    }
    cleaned = sanitize_mapping(payload)
    assert cleaned == {
        "tenant_id": TENANT_ID,
        "nested": {"keep": 1},
        "items": [{"keep": 2}, 3],
        "scalars": ["x", "y"],
    }
    rendered = str(cleaned)
    for marker in ("password", "api_key", "authorization"):
        assert marker not in rendered


# ===== ⑥ 进程内锁（`docs/02` §8 / §36 / §38）=====


def test_in_memory_lock_has_exactly_one_winner() -> None:
    """门槛 ⑨（`docs/02` §8 / §36）：`asyncio.gather` 下**恰好一个**赢家，其余超时。"""

    async def _run() -> None:
        lock = InMemoryLock()
        results = await asyncio.gather(
            *(
                lock.acquire("audit:tenant", owner_id=f"o{index}", timeout_seconds=1)
                for index in range(5)
            ),
            return_exceptions=True,
        )
        winners = [item for item in results if isinstance(item, InMemoryLockHandle)]
        losers = [item for item in results if isinstance(item, ResourceLockedError)]
        assert len(winners) == 1
        assert len(losers) == 4
        assert all(item.code == "STRUCTAI-6100" for item in losers)
        assert lock.held_keys() == ("audit:tenant",)
        assert await lock.is_locked("audit:tenant") is True
        assert await lock.release(winners[0]) is True
        assert lock.held_keys() == ()

    asyncio.run(_run())


def test_in_memory_lock_timeout_is_structai_6100() -> None:
    """门槛 ⑨（`docs/02` §38）：等待超时 → `STRUCTAI-6100` `timeout`（含键名）。"""

    async def _run() -> None:
        lock = InMemoryLock(default_timeout_seconds=30)
        first = await lock.acquire("audit:tenant", owner_id="owner-a")
        with pytest.raises(ResourceLockedError) as timeout:
            await lock.acquire("audit:tenant", owner_id="owner-b", timeout_seconds=0)
        assert timeout.value.code == "STRUCTAI-6100"
        assert timeout.value.details == {
            "stage": "lock",
            "reason": "timeout",
            "key": "audit:tenant",
        }
        assert await lock.release(first) is True

    asyncio.run(_run())


def test_in_memory_lock_hold_releases_on_exception() -> None:
    """门槛 ⑨（`docs/02` §41）：`hold()` 在异常路径也释放（无锁泄漏）。"""

    async def _run() -> None:
        lock = InMemoryLock()
        with pytest.raises(RuntimeError):
            async with lock.hold("audit:tenant", owner_id="owner-a") as handle:
                assert handle.key == "audit:tenant"
                raise RuntimeError("boom")
        assert await lock.is_locked("audit:tenant") is False
        assert lock.held_keys() == ()
        # 异常之后仍可重新获取（锁没有被「卡死」）。
        async with lock.hold("audit:tenant", owner_id="owner-b"):
            assert await lock.is_locked("audit:tenant") is True

    asyncio.run(_run())


def test_in_memory_lock_release_is_idempotent_and_never_frees_others() -> None:
    """门槛 ⑨（`docs/02` §41）：重复释放无害；过期句柄**不得**放掉别人的锁。"""

    async def _run() -> None:
        lock = InMemoryLock()
        handle = await lock.acquire("audit:tenant", owner_id="owner-a")
        stale = InMemoryLockHandle(key="audit:tenant", owner_id="owner-b")
        assert await lock.release(stale) is False
        assert await lock.is_locked("audit:tenant") is True
        assert await lock.release(handle) is True
        assert await lock.release(handle) is False
        assert await lock.is_locked("audit:tenant") is False

    asyncio.run(_run())


def test_in_memory_lock_rejects_blank_keys_and_non_positive_timeout() -> None:
    """门槛 ⑨（`docs/07` §11）：空白键 → `ValueError`；非正租约 → `ValueError`（装配错误）。"""
    with pytest.raises(ValueError):
        InMemoryLock(default_timeout_seconds=0)
    with pytest.raises(ValueError):
        InMemoryLock(default_timeout_seconds=-1)

    async def _run() -> None:
        lock = InMemoryLock()
        with pytest.raises(ValueError):
            await lock.acquire("   ")
        assert lock.default_timeout_seconds == DEFAULT_LOCK_TIMEOUT_SECONDS

    asyncio.run(_run())


def test_lock_timeout_constants_match_the_frozen_defaults() -> None:
    """门槛 ⑨（`docs/07` §3.1 / §4.3 #22）：三个 300 秒常量同值，且不跨层 import。"""
    assert DEFAULT_LOCK_TIMEOUT_SECONDS == LOCK_TIMEOUT_SPEC == 300
    assert POLICY_LOCK_TIMEOUT_SECONDS == LOCK_TIMEOUT_SPEC
    assert Settings.model_fields["lock_default_timeout_seconds"].default == LOCK_TIMEOUT_SPEC


# ===== ⑦ 通知（`docs/02` §35 / §45 / §59）=====


def test_notification_service_unknown_channel_returns_false_and_never_raises() -> None:
    """门槛 ⑩（`docs/02` §35；`docs/07` §14.4）：未知通道 → `False`，**不抛**。"""

    async def _run() -> None:
        service = NotificationService()
        message = NotificationMessage(
            channel="WEBHOOK",
            event_type=TASK_PROGRESS_EVENT_TYPE,
            payload={"task_id": "t1", "progress": 10},
        )
        assert await service.notify(message) is False
        assert service.failures() == ("WEBHOOK",)
        assert service.delivered() == ()
        assert service.channels() == (IN_PROCESS_CHANNEL,)

    asyncio.run(_run())


def test_notification_service_delivers_task_progress_payload() -> None:
    """门槛 ⑩（`docs/02` §45）：进度通知载荷恰为 `task_id` / `progress` / `message`。"""

    async def _run() -> None:
        sink = InProcessNotificationSink()
        service = NotificationService(sink=sink)
        assert (
            await service.notify_task_progress(task_id=TASK_ID, progress=42, message="half") is True
        )
        delivered = service.delivered()
        assert len(delivered) == 1
        assert delivered[0].channel == IN_PROCESS_CHANNEL
        assert delivered[0].event_type == TASK_PROGRESS_EVENT_TYPE == "TaskProgress"
        assert delivered[0].task_id == TASK_ID
        assert dict(delivered[0].payload) == {
            "task_id": TASK_ID,
            "progress": 42,
            "message": "half",
        }
        assert sink.delivered == delivered
        assert service.failures() == ()

    asyncio.run(_run())


def test_notification_service_subscribes_and_forwards_task_progress() -> None:
    """门槛 ⑩（`docs/02` §45）：`subscribe(bus)` 后发布 `TaskProgress` → **恰好一条**。"""

    async def _run() -> None:
        bus: EventBus = _RecordingBus()
        service = NotificationService()
        service.subscribe(bus)
        await asyncio.sleep(0)  # 让同步入口调度出去的订阅跑完
        event = TaskProgress.create(task_id=uuid4(), progress=7, message="started")
        await bus.publish(event)
        assert len(service.delivered()) == 1
        assert service.delivered()[0].event_type == TASK_PROGRESS_EVENT_TYPE
        assert dict(service.delivered()[0].payload)["progress"] == 7

    asyncio.run(_run())


def test_notification_service_registration_rules() -> None:
    """门槛 ⑩（`docs/07` §11）：空白 / 重复通道 → `STRUCTAI-7000`。"""
    sink: NotificationSink = InProcessNotificationSink()
    service = NotificationService(sink=sink)
    with pytest.raises(InternalError) as blank:
        service.register(" ", sink)
    assert blank.value.code == "STRUCTAI-7000"
    assert blank.value.details["reason"] == "invalid_channel"
    with pytest.raises(InternalError) as duplicate:
        service.register(IN_PROCESS_CHANNEL, sink)
    assert duplicate.value.details["reason"] == "duplicate_channel"
    with pytest.raises(InternalError):
        NotificationService(sink=sink, channel="   ")


def test_notification_service_survives_a_failing_sink() -> None:
    """门槛 ⑩（`docs/07` §14.4）：出口抛异常 → `False` + 记失败，**不**影响调用方。"""

    async def _run() -> None:
        failing = _FailingSink()
        service = NotificationService(sink=failing)
        assert await service.notify_task_progress(task_id=TASK_ID, progress=1) is False
        assert service.failures() == (IN_PROCESS_CHANNEL,)
        assert service.delivered() == ()
        assert len(failing.calls) == 1

    asyncio.run(_run())


# ===== ⑧ 红线（`docs/07` §11 / §14.1 / §14.2 / §14.4）=====

NEW_MODULES = (
    "app/infrastructure/storage/base.py",
    "app/infrastructure/storage/local.py",
    "app/infrastructure/storage/manager.py",
    "app/infrastructure/storage/__init__.py",
    "app/infrastructure/secrets/base.py",
    "app/infrastructure/secrets/environment.py",
    "app/infrastructure/secrets/__init__.py",
    "app/infrastructure/notifications/service.py",
    "app/infrastructure/notifications/__init__.py",
    "app/infrastructure/locks/in_memory.py",
    "app/infrastructure/locks/__init__.py",
    "app/infrastructure/database/repositories/artifact.py",
    "app/application/services/artifact.py",
)
"""本批（P29 / P35 模块组 A）新增的模块（用于红线断言）。"""


def test_no_vendor_names_in_app() -> None:
    """门槛 ⑪（`docs/07` §14.2）：`app/` 内厂商名 0 处（大小写不敏感）。"""
    hits = [
        f"{path.relative_to(REPO_ROOT).as_posix()}:{vendor}"
        for path in sorted(APP_DIR.rglob("*.py"))
        for vendor in VENDOR_NAMES
        if vendor.lower() in path.read_text(encoding="utf-8").lower()
    ]
    assert hits == []


def test_application_layer_does_not_depend_on_infrastructure() -> None:
    """门槛 ⑪（`docs/07` §14.1）：Application 层不得依赖 `app.infrastructure`。"""
    offenders = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in APPLICATION_DIR.rglob("*.py")
        if [name for name in _imported_modules(path) if name.startswith("app.infrastructure")]
    )
    assert offenders == []


def test_new_infrastructure_modules_do_not_touch_the_database() -> None:
    """门槛 ⑪（`docs/07` §14.1 / §14.4）：存储 / 凭据 / 通知 / 锁模块**零 SQL**。"""
    for relative in NEW_MODULES:
        if "repositories" in relative:
            continue
        path = REPO_ROOT / relative
        assert "sqlalchemy" not in _imported_modules(path), relative


def test_twenty_error_codes_are_not_extended() -> None:
    """门槛 ⑪（`docs/07` §11）：`app/` 内的 `STRUCTAI-xxxx` 字面量恰好是那 20 个码。"""
    declared: set[str] = set()
    for path in sorted(APP_DIR.rglob("*.py")):
        declared.update(re.findall(r"STRUCTAI-\d{4}", path.read_text(encoding="utf-8")))
    assert declared == set(ERROR_CODES_SPEC)
    assert len(ERROR_CODES_SPEC) == 20


def test_commit_and_rollback_only_in_unit_of_work() -> None:
    """门槛 ⑪（`docs/07` §14.4）：`commit()` / `rollback()` 只在 `unit_of_work.py`。"""
    committers = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in APP_DIR.rglob("*.py")
        if _commit_or_rollback_calls(path)
    )
    assert committers == ["app/infrastructure/database/unit_of_work.py"]
    for relative in NEW_MODULES:
        assert _commit_or_rollback_calls(REPO_ROOT / relative) == [], relative


def test_artifacts_table_and_the_twenty_four_tables_are_unchanged() -> None:
    """门槛 ②/⑪（`docs/07` §4.3）：`artifacts` 列集合与 24 张表**逐项未变**。"""
    tables = set(Base.metadata.tables)
    assert tables == set(TWENTY_FOUR_TABLES_SPEC)
    assert len(TWENTY_FOUR_TABLES_SPEC) == 24
    assert set(Base.metadata.tables["artifacts"].columns.keys()) == set(ARTIFACT_COLUMNS_SPEC)
    assert ArtifactORM.__tablename__ == "artifacts"
