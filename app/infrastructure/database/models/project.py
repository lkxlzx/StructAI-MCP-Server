"""项目与项目成员（`docs/07` §4.3 #8 / #9；`docs/02` §20）。

表名 `projects` / `project_members`。

字段口径：

- `projects` —— `tenant_id`（Tenant-owned）＋ `name` ＋ `version`
  （`docs/07` §4.3 #8 把 `version` 列为关键字段 → 乐观并发，`docs/02` §12）。
- `project_members` —— 复合主键 `(project_id, user_id)` ＋ `role`
  （`docs/02` §20）。
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionMixin,
)

__all__ = ["ProjectMemberModel", "ProjectMemberORM", "ProjectModel", "ProjectORM"]


class ProjectORM(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    """项目（`docs/07` §4.3 #8；`docs/02` §20）。

    `version` 用于乐观并发：更新时必须 `WHERE version = :expected`
    并 `version = version + 1`（`docs/02` §12）。
    """

    __tablename__ = "projects"

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class ProjectMemberORM(TimestampMixin, Base):
    """项目成员（`docs/07` §4.3 #9；`docs/02` §20）。

    复合主键 `(project_id, user_id)`；`role` 为项目内角色（`docs/07` §8.2）。
    """

    __tablename__ = "project_members"

    project_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    role: Mapped[str] = mapped_column(String(100), nullable=False)


ProjectModel = ProjectORM
"""`docs/07` §4.3 使用的类名；与 `ProjectORM` 是同一个类。"""

ProjectMemberModel = ProjectMemberORM
"""`docs/07` §4.3 使用的类名；与 `ProjectMemberORM` 是同一个类。"""
