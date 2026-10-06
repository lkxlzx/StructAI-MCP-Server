"""Application · Artifact Service（`docs/02` §29 / §33 / §49 / §55 / §56 / §84；`docs/07` §14.3）。

权威来源
--------
- `docs/02` §29（Artifact Storage）—— 数据库只保存 metadata；字节流落
  `ArtifactStorage`（Core Alpha = 本地文件系统）。
- `docs/02` §33（Artifact Service）—— 存储键由**服务端**生成
  （`{tenant_id}/{project_id}/{artifact_id}/payload`，§3.5），调用方不提供路径。
- `docs/02` §55（Core Alpha Implementation Order）第 24 项 = Artifact Storage；
  §56（Definition of Done）的 `[ ] Artifact Storage` 与安全验收
  （`artifact path traversal protection` / `artifact filename sanitization`）。
- `docs/02` §84（Final Architecture）—— 完整性验证：
  `checksum(original) == checksum(read)`。
- `docs/02` §30（Document Service / Retry）—— 删除必须幂等；顺序为
  「DB Artifact ↓ Storage Payload」（先删库行，再删载荷）。
- `docs/02` §49（Artifact Test Matrix）—— create / get / delete / exists / checksum /
  duplicate / missing payload / corrupted payload / orphan payload / tenant isolation。
- `docs/07` §14.3（安全与数据）—— 禁止依赖 UI 过滤做租户隔离；绝不记录 secret。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **存储键形状在本模块「照抄」一份，唯一权威仍是 `app/infrastructure/storage/base.py`**：
   `docs/07` §14.1 禁止 `app/application/**` 依赖 `app.infrastructure`，而
   `docs/02` §3.5 的键形状是**冻结契约**
   （`{tenant_id}/{project_id or "-"}/{artifact_id}/payload`）。两者不可同时满足，故
   Application 侧只保留**构造 / 解析**两件最小实现（`_storage_key_for()` /
   `_tenant_of_storage_key()`），并**不**实现任何文件系统逻辑；跨模块一致性由验收
   测试断言（同一组输入下两边给出同一字符串）。这是「分层红线优先于 DRY」的取舍，
   已登记 `docs/07` §16。
2. **租户归属由 `storage_key` 的第一段承载，且在**读写两侧**校验**：
   `artifacts` 表没有 `tenant_id` 列（`docs/07` §4.3 #21），本批不得改表，故
   `tenant_of(record)` 解析键的第一段。`info` / `read` / `delete` 一律先取记录再比对
   租户；**不匹配、键不可解析、行不存在**三种情形**同形**落 `TenantAccessDeniedError`
   （`STRUCTAI-4200`，`message="Tenant access denied"`，
   `details={"stage": "artifact", "reason": "tenant_mismatch"}`）—— 与 `docs/02` §48
   的「不泄露存在性」一致：调用方**无法**区分「不存在」与「别的租户的」。
3. **`create()` 刻意没有 `name` 参数**：`artifacts` 表没有 name 列
   （`docs/07` §4.3 #21），而 `docs/02` §3.4 明确「禁止直接使用用户提供的文件名作为
   最终路径」。把 name 放进签名会诱使调用方以为「名字会进路径 / 会落库」；真正需要
   人可读名字的是 Document 层（`docs/02` §30），由 `documents.name` 承载。
4. **`create()` 写入后**必须**读回校验**：`docs/02` §84 的
   `checksum(original) == checksum(read)` 是产物的完整性门槛；不校验就等于「写成功」
   只证明了 `write()` 没抛异常（磁盘满 / 权限 / 截断都可能静默成功）。校验失败落
   `STRUCTAI-6200`，`reason="checksum_mismatch"`。⚠️ 此时**不**自动删除已写下的载荷：
   删除本身可能失败并掩盖原始错误；调用方（或 `docs/02` §31 的 Artifact GC）负责清理。
5. **`delete()` 的顺序是「DB 行 → 载荷」**（`docs/02` §30 的「必须：DB Artifact ↓
   Storage Payload」）：先删元数据行，再删字节流。反向顺序在「删了字节流但库行删除
   失败」时会留下**指向不存在载荷的行**（不可恢复的坏引用）；当前顺序最坏留下
   **孤儿载荷**（`docs/02` §49 的 `orphan payload` 用例，可被 GC 检出并回收）。
   ⚠️ **Alpha 限制**：`docs/02` §30 推荐的 `DELETE_PENDING` 中间态需要一个 status 列，
   而冻结的 `artifacts` 表**没有**该列（`docs/07` §4.3 #21，本批不得改表），故 Core
   Alpha 只提供「顺序 + 幂等」两件保证；需要真正两阶段删除时以 Alembic 迁移加列后
   再实现（`docs/07` §14.3 禁止静默改表）。
6. **`verify()` 不吞存储异常**：载荷**不存在**是存储层事实（`STRUCTAI-6200`
   `missing_payload`），必须如实上抛；`verify()` 只回答「读回来的字节与记录的校验值
   是否一致」（不一致 → `False`）。把「文件没了」混同为「校验失败」会让运维无法区分
   「磁盘损坏」与「文件被删」。
7. **本模块不 `commit` / `rollback`**：事务边界归 `UnitOfWork`（`docs/02` §16；
   `docs/07` §14.4）。`create` / `delete` 因此是「同一事务内的一串仓储 + 存储操作」，
   由调用方（`ExecutionService` / 接口层）决定何时提交。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`（`ArtifactStore` / `ArtifactStorage` 契约、
`ArtifactDraft` / `ArtifactRecord`、`ArtifactError` / `TenantAccessDeniedError`）：
**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖 `app.infrastructure` /
`app.interfaces` / `app.observability`（存储经 Domain 契约注入），也**不**出现任何
厂商专属内容。
"""

from __future__ import annotations

import hashlib
from typing import Final
from uuid import uuid4

from app.domain.errors import ArtifactError, TenantAccessDeniedError
from app.domain.protocols import (
    ArtifactDraft,
    ArtifactRecord,
    ArtifactStorage,
    ArtifactStore,
)

__all__ = [
    "ARTIFACT_BACKEND_LOCAL",
    "ARTIFACT_STAGE",
    "ArtifactService",
]

ARTIFACT_STAGE: Final[str] = "artifact"
"""错误信封里的 `stage` 字面量（`docs/07` §11 / §14.3）。"""

ARTIFACT_BACKEND_LOCAL: Final[str] = "local"
"""Core Alpha 的存储后端名（`docs/02` §29；落 `artifacts.storage_backend`）。"""

_MISSING_PROJECT_SEGMENT: Final[str] = "-"
"""`project_id` 缺失时的路径段占位（与 `storage.base` 同值，见模块裁决 1）。"""

_PAYLOAD_FILENAME: Final[str] = "payload"
"""产物字节流的文件名（`docs/02` §3.4 / §3.5；**不是**用户文件名）。"""

_TENANT_DENIED_MESSAGE: Final[str] = "Tenant access denied"
"""跨租户 / 不存在时的统一对外消息（`docs/02` §48：不泄露存在性；见模块裁决 2）。"""


class ArtifactService:
    """产物的读写编排（`docs/02` §29 / §33 / §49）。

    ⚠️ 本类**不** `commit` / `rollback`（`docs/02` §16；`docs/07` §14.4）：
    它只是「同一个 `UnitOfWork` 内」的仓储 + 存储编排。
    """

    def __init__(
        self,
        store: ArtifactStore,
        storage: ArtifactStorage,
        *,
        storage_backend: str = ARTIFACT_BACKEND_LOCAL,
    ) -> None:
        """绑定元数据仓储与存储后端（`docs/02` §33）。

        Args:
            store: `ArtifactStore` 实现（P29 的 `ArtifactStoreRepository`）。
            storage: `ArtifactStorage` 实现（P29 的 `LocalFilesystemStorage`）。
            storage_backend: 后端名（落 `artifacts.storage_backend`）。
        """
        self._artifacts = store
        self._storage = storage
        self._storage_backend = storage_backend

    @property
    def store(self) -> ArtifactStore:
        """产物元数据仓储（`docs/02` §3.2）。"""
        return self._artifacts

    @property
    def storage(self) -> ArtifactStorage:
        """产物存储后端（`docs/02` §29 / §33）。"""
        return self._storage

    @property
    def storage_backend(self) -> str:
        """后端名（落 `artifacts.storage_backend`，`docs/07` §4.3 #21）。"""
        return self._storage_backend

    # ===== `docs/02` §33 的接口 =====

    async def create(
        self,
        *,
        tenant_id: str,
        data: bytes,
        mime_type: str,
        project_id: str | None = None,
        task_id: str | None = None,
    ) -> ArtifactRecord:
        """写入产物（字节流 + 元数据）并校验（`docs/02` §33 / §84）。

        Args:
            tenant_id: 租户标识（键的第一段；见模块裁决 2）。
            data: 产物字节。
            mime_type: MIME 类型（落 `artifacts.mime_type`）。
            project_id: 项目标识；`None` → 占位段（§3.5）。
            task_id: 产生产物的任务；手工上传 / 导出时为 `None`（`docs/02` §29）。

        Returns:
            落库的 `ArtifactRecord`（`checksum` 已校验）。

        Raises:
            ArtifactError: `STRUCTAI-6200` —— 存储层错误（`invalid_metadata` /
                `invalid_storage_key` / `path_traversal`）或写后读回校验失败
                （`reason="checksum_mismatch"`，见模块裁决 4）。

        ⚠️ 刻意**没有** `name` 参数（见模块裁决 3）；本方法**不** `commit`
        （`docs/07` §14.4）。
        """
        artifact_id = str(uuid4())
        key = _storage_key_for(
            tenant_id=tenant_id,
            project_id=project_id,
            artifact_id=artifact_id,
        )
        await self._storage.put(
            data,
            {
                "storage_key": key,
                "artifact_id": artifact_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
            },
        )
        checksum = _sha256_bytes(data)
        record = await self._artifacts.create(
            ArtifactDraft(
                storage_backend=self._storage_backend,
                storage_key=key,
                mime_type=mime_type,
                size=len(data),
                checksum=checksum,
                task_id=task_id,
            )
        )
        if not await self.verify(record):
            raise ArtifactError(
                "artifact checksum mismatch after write",
                details={"stage": ARTIFACT_STAGE, "reason": "checksum_mismatch"},
            )
        return record

    async def info(self, artifact_id: str, *, tenant_id: str) -> ArtifactRecord:
        """读取产物元数据（`docs/02` §33 / §49）。

        Args:
            artifact_id: 产物标识。
            tenant_id: 调用方声明的租户。

        Returns:
            该产物的 `ArtifactRecord`。

        Raises:
            TenantAccessDeniedError: `STRUCTAI-4200` —— 行不存在 / 键不可解析 /
                属于别的租户，三种情形**同形**（见模块裁决 2）。
        """
        record = await self._artifacts.get(artifact_id)
        if record is None or not tenant_id or self.tenant_of(record) != tenant_id:
            raise _tenant_denied()
        return record

    async def read(self, artifact_id: str, *, tenant_id: str) -> bytes:
        """读取产物字节流（`docs/02` §33 / §49）。

        Raises:
            TenantAccessDeniedError: `STRUCTAI-4200`（同 `info()`）。
            ArtifactError: `STRUCTAI-6200`，`reason="missing_payload"` —— 元数据行
                存在但载荷已不在（`docs/02` §49 的 `missing payload`）。
        """
        record = await self.info(artifact_id, tenant_id=tenant_id)
        return await self._storage.get(record.storage_key)

    async def verify(self, record: ArtifactRecord) -> bool:
        """读回载荷并比对校验值（`docs/02` §84）。

        Args:
            record: 待校验的产物元数据（`checksum` 为 `None` 视为不可校验）。

        Returns:
            `True` 仅当读回的字节的 SHA-256 与 `record.checksum` 相等。

        Raises:
            ArtifactError: `STRUCTAI-6200` —— 载荷不存在（见模块裁决 6；**不**吞掉
                存储层事实）。

        ⚠️ 本方法**不**做租户校验：它只回答「字节与校验值是否一致」。租户校验属于
        `info()` / `read()` / `delete()`（见模块裁决 2）。
        """
        if not record.checksum:
            return False
        payload = await self._storage.get(record.storage_key)
        return _sha256_bytes(payload) == record.checksum

    async def delete(self, artifact_id: str, *, tenant_id: str) -> bool:
        """删除产物（顺序：**DB 行 → 载荷**；`docs/02` §30）。

        Args:
            artifact_id: 产物标识。
            tenant_id: 调用方声明的租户。

        Returns:
            `True` 表示元数据行已删除（载荷删除是幂等的）；`False` 表示仓储报告
            该行不存在（正常情况下 `info()` 已先拒绝，见模块裁决 2）。

        Raises:
            TenantAccessDeniedError: `STRUCTAI-4200`（同 `info()`）。

        ⚠️ `docs/02` §30 的 `DELETE_PENDING` 两阶段删除需要一个 status 列，而冻结的
        `artifacts` 表没有它（见模块裁决 5）。
        """
        record = await self.info(artifact_id, tenant_id=tenant_id)
        deleted = await self._artifacts.delete(record.id)
        if not deleted:
            return False
        await self._storage.delete(record.storage_key)
        return True

    def tenant_of(self, record: ArtifactRecord) -> str | None:
        """解析 `storage_key` 第一段作为租户（见模块裁决 2）。

        `artifacts` 表没有 `tenant_id` 列，`storage_key` 是**唯一**的租户载体
        （`docs/02` §3.5）。键不可解析 → `None`（调用方必须视为拒绝）。
        """
        return _tenant_of_storage_key(record.storage_key)


def _sha256_bytes(data: bytes) -> str:
    """SHA-256 十六进制摘要（`docs/02` §3.6；与存储后端同一算法）。

    见模块裁决 1：Application 层**不得**依赖 `app.infrastructure`，故此处直接使用
    标准库 `hashlib`（`docs/02` §3.6 的原文实现）。两边必须给出同一校验值，
    由验收测试断言。
    """
    return hashlib.sha256(data).hexdigest()


def _storage_key_for(*, tenant_id: str, project_id: str | None, artifact_id: str) -> str:
    """构造存储键（`docs/02` §3.5；见模块裁决 1）。"""
    project_segment = project_id or _MISSING_PROJECT_SEGMENT
    return f"{tenant_id}/{project_segment}/{artifact_id}/{_PAYLOAD_FILENAME}"


def _tenant_of_storage_key(key: str) -> str | None:
    """取存储键第一段作为租户（`docs/02` §3.5；见模块裁决 1 / 2）。"""
    segments = tuple(part for part in str(key).split("/") if part)
    return segments[0] if segments else None


def _tenant_denied() -> TenantAccessDeniedError:
    """统一的租户拒绝错误（`STRUCTAI-4200`；见模块裁决 2）。"""
    return TenantAccessDeniedError(
        _TENANT_DENIED_MESSAGE,
        details={"stage": ARTIFACT_STAGE, "reason": "tenant_mismatch"},
    )
