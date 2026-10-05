"""会话（`docs/07` §4.3 #7；`docs/02` §10「Session ORM」）。

表名 `sessions`。

🔴 安全硬约束（`docs/07` §4.3 / §8.3；`docs/02` §13）：

- **token 只存 hash** —— 本表只有 `token_hash`，**没有**任何明文 token 列；
  明文 token 只在创建会话的那一次响应中返回给客户端，绝不落库、绝不落日志。
- `token_hash` 唯一，认证时以 `hash(token)` 反查（`docs/02` §20 Session Validation）。
- 校验顺序：存在 → 未 `revoked` → 未过期（`docs/02` §20）。

字段与 `docs/02` §10 逐项一致，`created_at` / `updated_at` 由 `TimestampMixin` 提供
（`docs/07` §4.3 通用规则）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

__all__ = ["SessionModel", "SessionORM"]


class SessionORM(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """用户会话（`docs/07` §4.3 #7；`docs/02` §10）。"""

    __tablename__ = "sessions"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # 只存 hash —— 禁止任何明文 token 列（docs/07 §14.3）。
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


SessionModel = SessionORM
"""`docs/07` §4.3 使用的类名；与 `SessionORM` 是同一个类。"""
