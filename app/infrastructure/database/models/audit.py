"""审计记录（`docs/07` §4.3 #24；`docs/02` §24 / §39 / §44）。

表名 `audit_records`。

- `action` / `resource` / `result` —— 审计三要素；`result` 取值见
  `app.domain.enums.AuditResult`（`SUCCESS` / `FAILURE` / `DENIED`）。
- `previous_hash` / `entry_hash` —— **Hash Chain**：`entry_hash` 由本条记录内容与
  `previous_hash` 共同计算，使审计链不可静默篡改（`docs/02` §44 / §8）。
  `previous_hash` 可为空（链首），`entry_hash` 必填。
- `tenant_id` 必填、`user_id` 可空（系统动作无用户）。
- ⚠️ 审计记录**不得**包含任何 secret（`docs/07` §14.3：绝不记录 secret）。

列名说明：`docs/07` §4.3 #24 的 `audit_id` 对应本表主键 `id`（`docs/02` §24 源码级命名）。
哈希链计算与查询由 P29–P35（Audit Service）实现，本批次只建立 persistence 结构。
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

__all__ = ["AuditRecordModel", "AuditRecordORM"]


class AuditRecordORM(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """审计记录（`docs/07` §4.3 #24；`docs/02` §24）。"""

    __tablename__ = "audit_records"

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)

    action: Mapped[str] = mapped_column(String(200), nullable=False)
    resource: Mapped[str | None] = mapped_column(String(500))
    result: Mapped[str] = mapped_column(String(30), nullable=False)

    previous_hash: Mapped[str | None] = mapped_column(String(128))
    entry_hash: Mapped[str] = mapped_column(String(128), nullable=False)


AuditRecordModel = AuditRecordORM
"""`docs/07` §4.3 使用的类名；与 `AuditRecordORM` 是同一个类。"""
