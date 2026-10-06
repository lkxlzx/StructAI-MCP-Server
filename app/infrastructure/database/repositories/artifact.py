"""产物元数据仓储（`docs/02` §3.2；`docs/07` §4.3 #21）。

权威来源
--------
- `docs/02` §3.2（Artifact ORM）—— `artifacts` 的列集合：`storage_backend` /
  `storage_key` / `mime_type` / `size` / `checksum`（外加 P04 的主键与时间戳）。
- `docs/07` §4.3 #21（`ArtifactModel`）—— 关键字段
  `artifact_id, storage_backend/key, mime_type, size, checksum`；
  24 张表**冻结**，本批只**用**它，**不得**改表。
- `docs/02` §29 / §33（Artifact Storage / Result）—— **产物内容不落数据库**：
  库里只有元数据，字节流经 `ArtifactStorage` 落在后端。
- `docs/02` §16（UnitOfWork）—— `Application Service → UnitOfWork → Repository`：
  仓储只 `INSERT` / `SELECT` / `DELETE`（+ `flush`），**绝不** `commit` / `rollback`
  （`docs/07` §14.4）。
- `docs/07` §14.4 —— 禁止无限 payload：列表查询一律**有界**（默认页大小 + 显式分页）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **本类不继承仓储基类**：`ArtifactStore`（P03 冻结的 Domain 契约）的方法签名与返回
   类型（`ArtifactDraft` → `ArtifactRecord`）与 `BaseRepository`（ORM 实体进出）不同，
   靠 `# type: ignore[override]` 消音会掩盖真实的契约不一致（P22–P28 的
   `TaskStoreRepository` 同一裁决）。故本类自带 `__init__` / `session`，
   **不**声明任何 `type: ignore`。
2. **`artifacts` 表没有 `tenant_id` 列**（`docs/07` §4.3 #21 的 6 个关键字段里没有它），
   本批**不得改表**，故本仓储**不**做租户过滤：租户归属由 `storage_key` 的路径口径
   承载（`docs/02` §3.5），由 `ArtifactService` 在读写两侧校验
   （见 `app/application/services/artifact.py` 的裁决 2）。此处**不**假装有租户列。
3. **时间口径**：SQLite 不保存时区，`DateTime(timezone=True)` 读回来是 naive；
   本类在构造 Domain 记录时统一用 `_as_utc()` 补 `UTC`（照抄
   `repositories/task.py` / `repositories/security.py` 的既有做法）。
4. **`delete()` 返回「是否删掉了行」**：不存在 → `False`（**不**抛），因为
   `docs/02` §30 的重试语义要求删除路径幂等；存在 → `DELETE` + `flush` → `True`。
5. **`create()` 把 `storage_key` 里的产物 id 作为主键**（`docs/02` §3.5）：键形状是
   `{tenant_id}/{project_id}/{artifact_id}/payload`，而 P03 冻结的 `ArtifactDraft`
   **不**携带 `id`（Domain 契约不得改）。若不显式落主键，ORM 的列默认值会另生成一个
   UUID，于是「库里的 `artifacts.id`」与「路径里的 `artifact_id`」指向**两个不同对象**
   —— `ArtifactStorage.get(artifact_id)`（`docs/02` §11 / §29）与产物 GC 的孤儿判定
   都会失准。故本类在 `create()` 里把键中 `payload` 前的那一段作为主键；键不是
   规范形状时回落列默认值（保持仓储可被手工草稿使用）。
6. **`create()` 只 `flush()`**：`created_at` / `updated_at` 由 P04 的列默认值在 `flush`
   时落到当前事务（`repositories/base.py` 的同一做法）。`flush` **不是** `commit`：
   事务边界归 `UnitOfWork`。

分层红线（`docs/07` §14.1）
----------------------------------
本模块只落在 `app/infrastructure/database/repositories/`：**不**反向依赖 Interface
层，**不**出现任何厂商专属内容，**不**记录 secret（`artifacts` 里没有任何凭据列）。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.protocols import ArtifactDraft, ArtifactRecord
from app.infrastructure.database.models.artifact import ArtifactORM
from app.infrastructure.storage.base import artifact_of_storage_key

__all__ = ["ArtifactStoreRepository", "build_artifact_store"]

DEFAULT_LIST_LIMIT: Final[int] = 100
"""`list_for_task()` 的默认页大小（`docs/07` §14.4：禁止无限 payload）。"""


class ArtifactStoreRepository:
    """`ArtifactStore` 的 SQLAlchemy 实现（`docs/02` §3.2 / §29 / §33；`docs/07` §4.3 #21）。

    只做 persistence：**不**决定事务（那是 `UnitOfWork`）、**不**做租户校验
    （`artifacts` 表没有 `tenant_id` 列，见模块裁决 2）、**不**碰字节流
    （那是 `ArtifactStorage` 的职责）。全部方法**绝不** `commit` / `rollback`。
    """

    def __init__(self, session: AsyncSession) -> None:
        """绑定一个已存在的会话（`docs/02` §16：会话由 `UnitOfWork` 提供）。

        Args:
            session: 已存在的 `AsyncSession`（本类**不**开事务、**不** `commit`）。
        """
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """当前会话（只读用途；事务边界不在此处决定）。"""
        return self._session

    # ===== Domain 契约 `ArtifactStore`（`docs/02` §3.2 / §36）=====

    async def create(self, draft: ArtifactDraft) -> ArtifactRecord:
        """落一行产物元数据（`docs/02` §3.2）。

        Args:
            draft: 待落库的元数据（`created_at` 由实现生成；主键取自
                `storage_key` 里的产物 id，见模块裁决 5）。

        Returns:
            落库后的 `ArtifactRecord`（`created_at` 已由列默认值填充）。

        ⚠️ 只 `flush()`，**不** `commit()`（`docs/07` §14.4）。
        """
        row = ArtifactORM(
            task_id=draft.task_id,
            storage_backend=draft.storage_backend,
            storage_key=draft.storage_key,
            mime_type=draft.mime_type,
            size=draft.size,
            checksum=draft.checksum,
        )
        artifact_id = artifact_of_storage_key(draft.storage_key)
        if artifact_id is not None:
            row.id = artifact_id
        self._session.add(row)
        await self._session.flush()
        return _to_record(row)

    async def get(self, artifact_id: str) -> ArtifactRecord | None:
        """按主键读取（`docs/02` §3.2）。

        Returns:
            命中的 `ArtifactRecord`；不存在返回 `None`（**不**抛）。
        """
        row = await self._session.get(ArtifactORM, str(artifact_id))
        return None if row is None else _to_record(row)

    async def delete(self, artifact_id: str) -> bool:
        """删除一行元数据（`docs/02` §30 的幂等语义；见模块裁决 4）。

        Returns:
            `True` 表示确实删掉了一行；`False` 表示该行不存在。
        """
        row = await self._session.get(ArtifactORM, str(artifact_id))
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True

    async def list_for_task(
        self,
        task_id: str,
        *,
        limit: int = DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> Sequence[ArtifactRecord]:
        """列出某任务产生的产物（`docs/02` §3.2 / §22；`docs/07` §14.4）。

        Args:
            task_id: 任务标识（`artifacts.task_id`；手工上传的产物该列为空）。
            limit: 页大小（有界，见模块裁决 3 / `docs/07` §14.4）。
            offset: 分页偏移。

        Returns:
            按 `created_at` 升序的 `ArtifactRecord` 序列。
        """
        statement = (
            select(ArtifactORM)
            .where(ArtifactORM.task_id == str(task_id))
            .order_by(ArtifactORM.created_at)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return [_to_record(row) for row in result.scalars().all()]

    async def list_all(
        self,
        *,
        limit: int = DEFAULT_LIST_LIMIT,
        offset: int = 0,
    ) -> Sequence[ArtifactRecord]:
        """有界遍历全部产物（`docs/02` §22 / §31 / §26；`docs/07` §14.4）。

        `docs/07` §14.4 禁止无限 payload，故 `limit` 有默认值、`offset` 显式分页；
        **不存在**「不传 limit 就取全表」的语义。
        """
        statement = select(ArtifactORM).order_by(ArtifactORM.created_at).offset(offset).limit(limit)
        result = await self._session.execute(statement)
        return [_to_record(row) for row in result.scalars().all()]


def build_artifact_store(session: AsyncSession) -> ArtifactStoreRepository:
    """为给定会话装配产物仓储（`docs/02` §16 / §33）。

    Args:
        session: 已存在的 `AsyncSession`（通常由 P06 `UnitOfWork` 提供）。

    Returns:
        绑定该会话的 `ArtifactStoreRepository`。

    ⚠️ 本函数**不**开事务、**不**提交、**不**建立连接。
    """
    return ArtifactStoreRepository(session)


def _as_utc(value: datetime) -> datetime:
    """把数据库读回的时间统一为**带时区**的 UTC（见模块裁决 3）。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_record(row: ArtifactORM) -> ArtifactRecord:
    """ORM 行 → Domain 记录（只映射契约里的列；时间补 `UTC`）。"""
    return ArtifactRecord(
        id=str(row.id),
        storage_backend=str(row.storage_backend),
        storage_key=str(row.storage_key),
        mime_type=str(row.mime_type),
        size=int(row.size),
        checksum=None if row.checksum is None else str(row.checksum),
        task_id=None if row.task_id is None else str(row.task_id),
        created_at=_as_utc(row.created_at),
    )
