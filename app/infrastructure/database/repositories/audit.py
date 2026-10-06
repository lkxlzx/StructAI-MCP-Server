"""Infrastructure · Repository · Audit（`docs/02` §7.1 / §8 / §43；`docs/07` §4.3 #24）。

权威来源
--------
- `docs/02` §7.1（AuditRecord）—— 审计记录列集合；§43（Audit 查询）—— 按用户 / action /
  resource / 时间 / `request_id` / `trace_id` / `task_id` 查询。
- `docs/02` §8（Audit Hash Chain）—— `previous_hash` / `entry_hash` 的落库列。
- `docs/02` §65（Audit）—— 「普通用户不得删除」：**append-only**。
- `docs/07` §4.3 #24 —— `audit_records` 的冻结列集合（本批只**用**它，**不得改表**）。
- `docs/02` §16 —— 仓储只 `INSERT` / `SELECT`，**绝不** `commit` / `rollback`。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **`tenant_id` 的「无租户」用空串哨兵**：`docs/02` §7.1 允许 `tenant_id` 为空
   （系统动作无租户），而 P04 落地的 `audit_records.tenant_id` 是 `nullable=False`
   （`docs/07` §4.3 #24 的冻结列）。本批**不得改表**，故用 `NO_TENANT = ""` 作为
   「无租户」哨兵：写入时 `None → ""`，读出时 `"" → None`。
   `""` 不是合法租户标识（UUID 字符串），因此该哨兵不会与真实租户冲突。
2. **append-only**：本类**只**提供 `append` 与读取，**不**提供 `update` / `delete`
   （`docs/02` §65）。篡改检测（`verify_chain`）因此能读到真实的历史。
3. **链的顺序**：`created_at` 升序 + `id` 升序兜底（同一时刻的两条记录需要确定性顺序，
   否则复算链会得到两种结果）。
4. **有界读**：`chain` 的 `limit` 有默认值（`docs/07` §14.4 禁止无限 payload）。
5. **绝不记录 secret**（`docs/07` §14.3）：本类只搬运调用方给的非敏感列，
   不做任何拼接 / 格式化，因此不会把 secret 引入审计。

分层红线（`docs/07` §14.1）：本模块只允许被 `app/infrastructure/database/` 与上层引用；
**不得**反向依赖 Interface 层，也**不**得自行 `commit`。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.protocols import AuditEntry, AuditEntryDraft
from app.infrastructure.database.models.audit import AuditRecordORM

__all__ = ["NO_TENANT", "AuditStoreRepository", "build_audit_store"]

NO_TENANT: Final[str] = ""
"""「无租户」哨兵（见模块裁决 1）：`docs/02` §7.1 允许空租户，而冻结列非空。"""

DEFAULT_CHAIN_LIMIT: Final[int] = 1000
"""链查询的默认上限（`docs/07` §14.4 的有界读）。"""


class AuditStoreRepository:
    """`AuditStore` 的 SQLAlchemy 实现（`docs/02` §7 / §8；`docs/07` §4.3 #24）。

    ⚠️ **不**继承仓储基类：基类提供 `update` / `remove`，而审计是 **append-only**
    （`docs/02` §65）。自带 `__init__` / `session`，只暴露追加与读取。
    """

    def __init__(self, session: AsyncSession) -> None:
        """绑定一个已存在的会话（`docs/02` §16：会话由 `UnitOfWork` 提供）。"""
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """当前会话（只读用途；事务边界不在此处决定）。"""
        return self._session

    # ===== `docs/02` §8：追加 =====

    async def append(self, draft: AuditEntryDraft) -> AuditEntry:
        """追加一条审计记录（`docs/02` §7.1；见模块裁决 1 / 2）。

        Args:
            draft: 已算好 `entry_hash` 的记录（链的推进由 `AuditService` 负责）。

        Returns:
            已落库的 `AuditEntry`（含实现生成的 `id` / `created_at`）。
        """
        row = AuditRecordORM(
            tenant_id=draft.tenant_id if draft.tenant_id is not None else NO_TENANT,
            user_id=draft.user_id,
            action=draft.action,
            resource=draft.resource,
            result=draft.result,
            previous_hash=draft.previous_hash,
            entry_hash=draft.entry_hash,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_entry(row)

    # ===== `docs/02` §8 / §43：读取 =====

    async def last_hash(self, *, tenant_id: str | None = None) -> str | None:
        """该链上最后一条记录的 `entry_hash`（`docs/02` §8 的 `previous_hash`）。

        Args:
            tenant_id: 链的租户（见模块裁决 1）；`None` 表示系统链。

        Returns:
            `None` 表示该链还没有记录（链首）。
        """
        result = await self._session.execute(
            select(AuditRecordORM.entry_hash)
            .where(AuditRecordORM.tenant_id == _chain_tenant(tenant_id))
            .order_by(AuditRecordORM.created_at.desc(), AuditRecordORM.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def chain(
        self,
        *,
        tenant_id: str | None = None,
        limit: int = DEFAULT_CHAIN_LIMIT,
    ) -> list[AuditEntry]:
        """按链顺序读取记录（`docs/02` §8 / §43；见模块裁决 3 / 4）。"""
        result = await self._session.execute(
            select(AuditRecordORM)
            .where(AuditRecordORM.tenant_id == _chain_tenant(tenant_id))
            .order_by(AuditRecordORM.created_at.asc(), AuditRecordORM.id.asc())
            .limit(limit)
        )
        return [_to_entry(row) for row in result.scalars().all()]

    async def count(self) -> int:
        """审计记录总数（健康 / 诊断用）。"""
        result = await self._session.execute(select(func.count()).select_from(AuditRecordORM))
        return int(result.scalar_one())


def build_audit_store(session: AsyncSession) -> AuditStoreRepository:
    """为给定会话装配审计仓储（`docs/02` §16 / §33）。"""
    return AuditStoreRepository(session)


def _chain_tenant(tenant_id: str | None) -> str:
    """Domain 的 `None` → 落库哨兵（见模块裁决 1）。"""
    return tenant_id if tenant_id is not None else NO_TENANT


def _to_entry(row: AuditRecordORM) -> AuditEntry:
    """ORM 行 → Domain 记录（只映射冻结列；时间补 `UTC`）。"""
    return AuditEntry(
        id=str(row.id),
        tenant_id=row.tenant_id or None,
        user_id=row.user_id or None,
        action=str(row.action),
        resource=row.resource,
        result=str(row.result),
        previous_hash=row.previous_hash,
        entry_hash=str(row.entry_hash),
        created_at=_as_utc(row.created_at),
    )


def _as_utc(value: Any) -> datetime:
    """把数据库读回的时间统一为**带时区**的 UTC（SQLite 不存时区）。"""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return datetime.now(UTC)
