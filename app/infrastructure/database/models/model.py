"""工程模型（`docs/07` §4.3 #14；`docs/02` §22）。

表名 `models`。

- `project_id` —— 归属项目（Tenant-owned 链：tenant → project → model）。
- `software_instance_id` —— 该模型当前绑定的软件实例；可为空（未绑定）。
- `version` —— 乐观并发版本号（`docs/07` §4.3 #14 明写 `version`；`docs/02` §12）。
  ⚠️ 这不是「模型版本历史」表；版本历史由 `documents` / Artifact 批次承接。
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

__all__ = ["ModelModel", "ModelORM"]


class ModelORM(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    """工程模型（`docs/07` §4.3 #14；`docs/02` §22）。"""

    __tablename__ = "models"

    project_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    software_instance_id: Mapped[str | None] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


ModelModel = ModelORM
"""`docs/07` §4.3 使用的类名；与 `ModelORM` 是同一个类。"""
