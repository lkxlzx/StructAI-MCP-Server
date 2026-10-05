"""产物（`docs/07` §4.3 #21；`docs/02` §24 / §29）。

表名 `artifacts`。

- `task_id` —— 产生产物的任务，可为空（手工上传 / 导出）。
- `storage_backend` —— 存储后端标识（Core Alpha = `local`，`docs/02` §29）。
- `storage_key` —— 后端内的对象键（`docs/02` §29 Storage Key）。
- `checksum` —— 完整性校验值；可为空（尚未计算完成时）。
- `size` —— 字节数。

⚠️ 产物内容**不落数据库**，只存引用（`docs/07` §14.3：禁止无限 payload；
产物走 ArtifactStorage，`docs/02` §29）。本批次只建立 persistence 结构；
存储与生命周期由 P29–P35 实现。
"""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

__all__ = ["ArtifactModel", "ArtifactORM"]


class ArtifactORM(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """产物（`docs/07` §4.3 #21；`docs/02` §24）。"""

    __tablename__ = "artifacts"

    task_id: Mapped[str | None] = mapped_column(String(36), index=True)
    storage_backend: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(2000), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(200), nullable=False)
    size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(200))


ArtifactModel = ArtifactORM
"""`docs/07` §4.3 使用的类名；与 `ArtifactORM` 是同一个类。"""
