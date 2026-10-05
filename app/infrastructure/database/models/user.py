"""用户与用户-角色关联（`docs/07` §4.3 #2 / #5；`docs/02` §19）。

表名 `users` / `user_roles`。

字段口径：

- `users` —— 照抄 `docs/02` §19（`UserORM`）的 `tenant_id` / `username` /
  `password_hash` / `is_active`，并补齐 `docs/07` §4.3 #2 明确要求的
  `locked` 与 `failed_login_count`（`docs/02` §18「Failed Login」把它们列为
  「后续可增加字段」；本批次一次性落地，避免 P10 再改表）。
- `username` 唯一 —— `docs/07` §4.3 #2 明写 `username(唯一)`，此处照抄为**全局唯一**。
  ⚠️ 若后续需要「同一 username 在多个租户复用」，必须以 Alembic 迁移改为
  `UNIQUE(tenant_id, username)`，不得静默改表（`docs/07` §14.3）。
- `password_hash` **只存哈希**，绝不存明文（`docs/07` §14.3：绝不记录 secret）。
- `user_roles` —— 复合主键 `(user_id, role_id)`（`docs/02` §19），不继承
  `UUIDPrimaryKeyMixin`。

本批次只建立 persistence 结构；认证 / RBAC 判定放在 P10–P13（`docs/02` §19 末注）。
"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

__all__ = ["UserModel", "UserORM", "UserRoleModel", "UserRoleORM"]


class UserORM(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """用户（`docs/07` §4.3 #2；`docs/02` §19）。"""

    __tablename__ = "users"

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class UserRoleORM(TimestampMixin, Base):
    """用户-角色关联（`docs/07` §4.3 #5；`docs/02` §19）。

    复合主键 `(user_id, role_id)`；同一用户可持有多角色（`docs/02` §23 RBAC）。
    """

    __tablename__ = "user_roles"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    role_id: Mapped[str] = mapped_column(String(36), primary_key=True)


UserModel = UserORM
"""`docs/07` §4.3 使用的类名；与 `UserORM` 是同一个类。"""

UserRoleModel = UserRoleORM
"""`docs/07` §4.3 使用的类名；与 `UserRoleORM` 是同一个类。"""
