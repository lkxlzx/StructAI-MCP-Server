"""角色与角色-权限关联（`docs/07` §4.3 #3 / #6；`docs/02` §19）。

表名 `roles` / `role_permissions`。

字段口径：

- `roles` —— `tenant_id`（`docs/07` §4.3 #3：Tenant-owned）＋ `name`
  （固定集合 `system_admin` / `engineer` / `viewer` / `ai_agent`，取值种子见
  `docs/02` §72 / `docs/07` §5.7，由 P07 Seed 落库）。
- `role_permissions` —— 复合主键 `(role_id, permission_id)`（`docs/02` §19）。

⚠️ 规范**未**给出「角色名在租户内唯一」的约束，本批次不擅自添加；
该完整性由 P07 Seed 的幂等逻辑与 P10–P13 RBAC 保证，
若后续规范明确要求，再以 Alembic 迁移追加（`docs/07` §14.3）。
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

__all__ = ["RoleModel", "RoleORM", "RolePermissionModel", "RolePermissionORM"]


class RoleORM(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """角色（`docs/07` §4.3 #3；`docs/02` §19）。"""

    __tablename__ = "roles"

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class RolePermissionORM(TimestampMixin, Base):
    """角色-权限关联（`docs/07` §4.3 #6；`docs/02` §19）。

    复合主键 `(role_id, permission_id)`。
    """

    __tablename__ = "role_permissions"

    role_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    permission_id: Mapped[str] = mapped_column(String(36), primary_key=True)


RoleModel = RoleORM
"""`docs/07` §4.3 使用的类名；与 `RoleORM` 是同一个类。"""

RolePermissionModel = RolePermissionORM
"""`docs/07` §4.3 使用的类名；与 `RolePermissionORM` 是同一个类。"""
