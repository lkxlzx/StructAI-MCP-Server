"""幂等记录（`docs/07` §4.3 #23；`docs/02` §24 / §28 / §31–§35）。

表名 `idempotency_records`。

🔴 原子性硬约束（`docs/02` §28 / §31–§35；`docs/07` §4.3 #23）：

- **唯一键 `(tenant_id, idempotency_key)`** —— 唯一性必须由**数据库约束**保证，
  禁止「先 `SELECT` 不存在再 `INSERT`」的竞态写法（`docs/02` §35）。
  正确做法：直接 `INSERT`，捕获 `IntegrityError` 后回读既有记录。
- `request_hash` 必存：同一 key 配不同请求必须**拒绝**（`docs/02` §32）。
  `request_hash` 为 SHA-256 十六进制串（`docs/02` §33），故长度 64；
  本列给 128 位余量以兼容后续更强的摘要算法。
- `response_json` —— 首次成功执行的响应快照，重放时原样返回。
- 键与租户绑定（`docs/02` §31）。

列名说明：`docs/07` §4.3 #23 写作 `idempotency_key`，`docs/02` §24 源码写作 `key`；
本表采用 `idempotency_key`（与 `docs/07` §4.3 及领域值对象
`app.domain.value_objects.IdempotencyKey` 一致），二者指同一列。
"""

from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

__all__ = ["IdempotencyRecordModel", "IdempotencyRecordORM"]


class IdempotencyRecordORM(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """幂等记录（`docs/07` §4.3 #23；`docs/02` §24）。"""

    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_idempotency_records_tenant_id_idempotency_key",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(300), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    response_json: Mapped[str | None] = mapped_column(String)


IdempotencyRecordModel = IdempotencyRecordORM
"""`docs/07` §4.3 使用的类名；与 `IdempotencyRecordORM` 是同一个类。"""
