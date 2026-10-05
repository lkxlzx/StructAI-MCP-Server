"""租户（`docs/07` §4.3 #1；`docs/02` §18.1）。

表名 `tenants`。规范源码类名 `TenantORM`（`docs/02` §18.1），
并给出 `docs/07` §4.3 使用的名字 `TenantModel` 作为**同一类**的别名。
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

__all__ = ["TenantModel", "TenantORM"]


class TenantORM(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """租户根实体（`docs/07` §4.3 #1：`tenant_id` / `name`）。

    租户是全部 Tenant-owned 数据的隔离边界（`docs/02` §11；`docs/07` §14.3：
    禁止依赖 UI 过滤做租户隔离）。
    """

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        unique=True,
    )


TenantModel = TenantORM
"""`docs/07` §4.3 使用的类名；与 `TenantORM` 是同一个类，不是新模型。"""
