"""文档仓储 + 进程内文档版本仓储（`docs/07` §12 P30；`docs/02` §22 / §4.1 / §4.2 / §36）。

权威来源
--------
- `docs/07` §4.3 #15 —— `documents` 表（24 张冻结表之一）：`project_id` / `model_id` /
  `name` / `path` / `status`（§4.3 描述性写作 `lifecycle_state`）+ UUID 主键 +
  `created_at` / `updated_at`。本批**不得改表**，故本模块只使用已落地的列。
- `docs/02` §22（`source9`）—— `DocumentStore` 的持久化语义；`docs/02` §36 要求
  Repository 只做 persistence：**不**承载 MCP / RBAC / capability / adapter / 工程计算。
- `docs/02` §4.1（`blue`）—— `Document` 的 ORM 列集合；`docs/02` §4.4 的 `new` /
  `save` / `save_as` / `close` 是**操作**语义，状态机归 Application 层
  （`app/application/services/document.py`），本模块只读写行。
- `docs/02` §4.2（`blue`）—— `DocumentVersion`：字段 `document_id` / `version` /
  `artifact_id` / `checksum`，唯一约束 `(document_id, version)`。
- `docs/02` §16 / §26 —— `Repository → SQLAlchemy`：Repository **绝不**决定事务边界；
  `docs/07` §14.4 把它固化为红线（只有 `UnitOfWork` 可以 `commit` / `rollback`）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **`DocumentSnapshot.version` 是冻结默认值，不是 `documents` 的列**：`documents` 表
   没有 `version` 列（`docs/07` §4.3 #15），而 Domain 的 `DocumentSnapshot.version`
   默认 `1`。本仓储因此**不**从库里读版本号 —— 权威版本号只来自
   `DocumentVersionStore`（见 `docs/02` §4.2）。这里保留字段默认值，避免伪造第二个来源。
2. **`update()` 的未知列 → 返回 `None`**：`docs/02` §26 的 `update` 只更新**真实存在**
   的列。为满足 Domain 契约的返回类型（`DocumentSnapshot | None`），未知列不抛异常，
   而是与「行不存在」一样返回 `None` —— 两种情况都不改变任何数据。可更新的列被收窄为
   五个业务列 `_MUTABLE_COLUMNS`；`id` / `created_at` / `updated_at` 由 ORM 维护
   （`updated_at` 由 `TimestampMixin.onupdate` 刷新），**不**允许经本入口改写。
3. **`list_for_project()` 是有界的**：`docs/07` §14.4 禁止无限 payload，故默认页大小
   显式取 `limit=100`（与 `docs/02` §31 的分页口径一致），并固定 `ORDER BY created_at`
   使输出确定。
4. **`InMemoryDocumentVersionStore` = Alpha 限制（已登记 `docs/07` §16 R52）**：
   `docs/02` §4.2 的 `document_versions` 表**不在** `docs/07` §4.3 的 24 张表内，
   本批**不得改表**（`docs/07` §14.3：禁止静默 `ALTER TABLE`）。故 Core Alpha 的版本
   注册表是**进程内**的，与 `docs/02` §5.4 对 Outbox 的处理同一口径：在代码里明确记为
   Alpha 限制并**保留迁移接口** —— 需要持久化时以 **Alembic 迁移**新增表并实现同一
   `DocumentVersionStore` 契约。`(document_id, version)` 唯一性在本实现里**仍然强制**
   （`docs/02` §4.2），重复即 `STRUCTAI-7000`（不静默覆盖，也不新增错误码）。
5. **版本行的 `id` / `created_at` 由实现生成**：与 P04 的 `UUIDPrimaryKeyMixin` /
   `TimestampMixin` 同口径（`docs/07` §4.3 的通用字段规则），`append()` 只接收调用方
   决定的值（`document_id` / `version` / `artifact_id` / `checksum`）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只允许落在 `app/infrastructure/database/`：可引用 SQLAlchemy 与 P04 的 ORM；
`app/domain/` 不得反向引用它。它只做 persistence，**绝不** `commit` / `rollback`
（`docs/07` §14.4），也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final, cast
from uuid import uuid4

from sqlalchemy import CursorResult, select
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import InternalError
from app.domain.protocols import (
    DocumentDraft,
    DocumentSnapshot,
    DocumentVersionRecord,
)
from app.infrastructure.database.models.document import DocumentORM

__all__ = [
    "DocumentStoreRepository",
    "InMemoryDocumentVersionStore",
    "build_document_store",
    "build_document_version_store",
]

_MUTABLE_COLUMNS: Final[frozenset[str]] = frozenset(
    {"project_id", "model_id", "name", "path", "status"}
)
"""`update()` 允许写入的列（`docs/02` §22 / §26）。

`id` / `created_at` / `updated_at` **不在**其中：前者是主键、后两者由 ORM 维护
（`updated_at` 经 `TimestampMixin.onupdate` 刷新），见模块裁决 2。
"""

DEFAULT_DOCUMENT_PAGE_SIZE: Final[int] = 100
"""`list_for_project()` 的默认页大小（`docs/07` §14.4：禁止无限 payload）。"""


class DocumentStoreRepository:
    """`DocumentStore` 的 SQLAlchemy 实现（`docs/07` §4.3 #15；`docs/02` §22 / §36）。

    只 `INSERT` / `SELECT` / `UPDATE` / `DELETE` + `flush()`，**绝不** `commit` /
    `rollback`（`docs/02` §16；`docs/07` §14.4）。
    """

    def __init__(self, session: AsyncSession) -> None:
        """绑定一个已存在的会话（`docs/02` §16：会话由上层 / `UnitOfWork` 提供）。"""
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """当前会话（只读用途；事务边界不在此处决定）。"""
        return self._session

    # ===== 契约：`app.domain.protocols.DocumentStore` =====

    async def create(self, draft: DocumentDraft) -> DocumentSnapshot:
        """插入一行文档并 `flush()`（`docs/02` §22 / §4.4）。

        Args:
            draft: 待创建的文档（`docs/02` §22 的列集合，去掉由实现生成的主键 / 时间）。

        Returns:
            新行的快照；`id` / `created_at` / `updated_at` 由 P04 的 Mixin 生成。

        ⚠️ 只 `flush`，**不 `commit`**（`docs/07` §14.4）。
        """
        row = DocumentORM(
            project_id=draft.project_id,
            model_id=draft.model_id,
            name=draft.name,
            path=draft.path,
            status=draft.status,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_snapshot(row)

    async def get(self, document_id: str) -> DocumentSnapshot | None:
        """按主键读取（`docs/02` §22）。

        Returns:
            命中的行；不存在返回 `None`（不抛异常）。
        """
        result = await self._session.execute(
            select(DocumentORM).where(DocumentORM.id == str(document_id))
        )
        row = result.scalar_one_or_none()
        return None if row is None else _to_snapshot(row)

    async def update(
        self,
        document_id: str,
        *,
        fields: Mapping[str, object],
    ) -> DocumentSnapshot | None:
        """按字段更新并 `flush()`（`docs/02` §22 / §26；见模块裁决 2）。

        Args:
            document_id: 目标行的主键。
            fields: 列名 → 新值；只接受 `_MUTABLE_COLUMNS` 中的列。

        Returns:
            更新后的快照；行不存在**或**含未知列时返回 `None`（两种情况都不改数据）。

        ⚠️ 只 `flush`，**不 `commit`**（`docs/07` §14.4）；`updated_at` 由 ORM 的
        `onupdate` 刷新。
        """
        if set(fields) - _MUTABLE_COLUMNS:
            return None

        result = await self._session.execute(
            select(DocumentORM).where(DocumentORM.id == str(document_id))
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None

        for name, value in fields.items():
            setattr(row, name, value)
        await self._session.flush()
        return _to_snapshot(row)

    async def delete(self, document_id: str) -> bool:
        """按主键删除（`docs/02` §22）。

        Returns:
            `True` 表示确实删除了该行；`False` 表示不存在。

        ⚠️ 只 `DELETE`，**不 `commit`**（`docs/07` §14.4）。
        """
        outcome = cast(
            "CursorResult[Any]",
            await self._session.execute(
                sa_delete(DocumentORM).where(DocumentORM.id == str(document_id))
            ),
        )
        return outcome.rowcount == 1

    async def list_for_project(
        self,
        project_id: str,
        *,
        limit: int = DEFAULT_DOCUMENT_PAGE_SIZE,
    ) -> Sequence[DocumentSnapshot]:
        """列出某项目下的文档，按 `created_at` 升序（`docs/02` §22；见模块裁决 3）。

        `limit` 有默认值，故**不存在**「不传就取全表」的语义（`docs/07` §14.4）。
        """
        result = await self._session.execute(
            select(DocumentORM)
            .where(DocumentORM.project_id == str(project_id))
            .order_by(DocumentORM.created_at)
            .limit(limit)
        )
        return tuple(_to_snapshot(row) for row in result.scalars().all())


class InMemoryDocumentVersionStore:
    """进程内的文档版本注册表（`docs/02` §4.2 / §50；见模块裁决 4）。

    ⚠️ **Alpha 限制**：`document_versions` 表不在 `docs/07` §4.3 的 24 张表内，本批
    **不得改表**，故 Core Alpha 的版本注册表是进程内的（与 `docs/02` §5.4 对 Outbox
    的处理同一口径）。它**保留迁移接口**：需要持久化时以 Alembic 迁移新增表并实现同一
    `DocumentVersionStore` 契约。

    `(document_id, version)` 唯一性在本实现里仍然强制（`docs/02` §4.2）：重复追加即
    `InternalError`（`STRUCTAI-7000`），**不**静默覆盖。
    """

    def __init__(self) -> None:
        """创建一个空的进程内注册表（无会话参数 —— 状态只在本进程内）。"""
        self._records: dict[tuple[str, int], DocumentVersionRecord] = {}

    async def append(
        self,
        *,
        document_id: str,
        version: int,
        artifact_id: str,
        checksum: str,
    ) -> DocumentVersionRecord:
        """追加一个版本（`docs/02` §4.2 / §50）。

        Args:
            document_id: 所属文档标识。
            version: 版本号（由调用方计算，通常 = 最新版本 + 1）。
            artifact_id: 承载该版本内容的产物标识（`docs/02` §29 / §33）。
            checksum: 内容摘要；未知时为空串（见 `DocumentService.save`）。

        Returns:
            新写入的版本记录（`id` / `created_at` 由本实现生成，见模块裁决 5）。

        Raises:
            InternalError: `STRUCTAI-7000`，`(document_id, version)` 已存在
                （`docs/02` §4.2 的唯一约束；见模块裁决 4）。
        """
        key = (str(document_id), int(version))
        if key in self._records:
            raise InternalError(
                "document version already exists",
                details={"stage": "document", "reason": "duplicate_version"},
            )
        record = DocumentVersionRecord(
            id=str(uuid4()),
            document_id=key[0],
            version=key[1],
            artifact_id=str(artifact_id),
            checksum=str(checksum),
            created_at=datetime.now(UTC),
        )
        self._records[key] = record
        return record

    async def latest(self, document_id: str) -> DocumentVersionRecord | None:
        """该文档的最新版本（`docs/02` §4.2）。

        Returns:
            版本号最大的记录；从未追加过则返回 `None`。
        """
        target = str(document_id)
        versions = [record for (doc, _), record in self._records.items() if doc == target]
        if not versions:
            return None
        return max(versions, key=lambda record: record.version)

    async def list_for_document(self, document_id: str) -> Sequence[DocumentVersionRecord]:
        """该文档的全部版本，按版本号升序（`docs/02` §4.2）。"""
        target = str(document_id)
        versions = [record for (doc, _), record in self._records.items() if doc == target]
        return tuple(sorted(versions, key=lambda record: record.version))


def _to_snapshot(row: DocumentORM) -> DocumentSnapshot:
    """ORM 行 → Domain 快照（只映射 `documents` 真实存在的列；见模块裁决 1）。"""
    return DocumentSnapshot(
        id=str(row.id),
        project_id=str(row.project_id),
        name=str(row.name),
        status=str(row.status),
        model_id=None if row.model_id is None else str(row.model_id),
        path=None if row.path is None else str(row.path),
    )


def build_document_store(session: AsyncSession) -> DocumentStoreRepository:
    """为一个会话装配文档仓储（`docs/02` §16 / §33）。

    Args:
        session: 已存在的 `AsyncSession`（通常由 P06 `UnitOfWork` 提供）。

    Returns:
        `DocumentStoreRepository`：绑定该会话，因此与同会话的其他仓储共享同一事务。

    ⚠️ 本函数**不**开事务、**不**提交、**不**建立连接（`docs/02` §16；`docs/07` §14.4）。
    """
    return DocumentStoreRepository(session)


def build_document_version_store() -> InMemoryDocumentVersionStore:
    """装配进程内的文档版本注册表（`docs/02` §4.2；见模块裁决 4）。

    **没有** `session` 参数 —— 它是进程本地状态（Alpha 限制），与持久化仓储的装配
    入口形状有意不同，避免被误当作会话级仓储。
    """
    return InMemoryDocumentVersionStore()
