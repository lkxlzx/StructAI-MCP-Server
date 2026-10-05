"""权限码（`docs/07` §4.3 #4；`docs/02` §19）。

表名 `permissions`。字段只有 `code`（`docs/07` §4.3 #4 明写「code」）。

权限码是**软件无关**的全局集合（12 码，`docs/02` §71 / `docs/07` §5.7），
不属任何租户，因此**不带** `tenant_id`。取值由 P07 Seed 落库，
类型化视图见 `app.domain.enums.PermissionCode`。
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

__all__ = ["PermissionModel", "PermissionORM"]


class PermissionORM(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """权限码（`docs/07` §4.3 #4；`docs/02` §19）。"""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        unique=True,
    )


PermissionModel = PermissionORM
"""`docs/07` §4.3 使用的类名；与 `PermissionORM` 是同一个类。"""
