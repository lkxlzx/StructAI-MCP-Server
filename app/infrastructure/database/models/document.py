"""文档（`docs/07` §4.3 #15；`docs/02` §22）。

表名 `documents`。

- `project_id` —— 归属项目；`model_id` —— 可选关联的工程模型。
- `status` —— 文档生命周期状态，取值见 `app.domain.enums.DocumentStatus`
  （`NEW` / `OPEN` / `CLOSED`，`docs/02` §8 / §30）。
  `docs/07` §4.3 #15 把该列写作 `lifecycle_state`（描述性写法），
  本表沿用源码级规范 `docs/02` §22 的列名 `status`；两者语义一致。
- `path` —— 文档在软件实例侧的路径，可为空。
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

__all__ = ["DocumentModel", "DocumentORM"]


class DocumentORM(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """文档（`docs/07` §4.3 #15；`docs/02` §22）。"""

    __tablename__ = "documents"

    project_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    model_id: Mapped[str | None] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    path: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(30), nullable=False)


DocumentModel = DocumentORM
"""`docs/07` §4.3 使用的类名；与 `DocumentORM` 是同一个类。"""
