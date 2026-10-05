"""资源锁（`docs/07` §4.3 #22；`docs/02` §24 / §36–§41）。

表名 `resource_locks`。

- `resource_type` / `resource_id` —— 被锁资源；取值见
  `app.domain.enums.ResourceType`（`SOFTWARE_INSTANCE` / `PROJECT` / `MODEL` /
  `DOCUMENT`），复合语义等价于 `docs/02` §37 的 `ResourceKey`。
- `mode` —— 锁模式，取值见 `app.domain.enums.LockMode`
  （`READ` / `WRITE` / `EXCLUSIVE`）；兼容矩阵见 `docs/02` §36。
- `owner_id` —— 持有者标识（任务 ID / worker ID / 请求 ID）。
- `timeout_seconds` —— 锁的最长持有时间（秒）。`docs/07` §4.3 #22 的关键字段写作
  `timeout`（无单位）；此处显式命名为 `timeout_seconds` 并取整数秒，
  默认值与 `Settings.lock_default_timeout_seconds`（300）一致。

Core Alpha 的锁实现在内存中（`docs/02` §38 In-Memory Lock Manager）；
本表为跨进程 / 崩溃恢复场景的持久化锚点，语义实现放在 P14–P18。
"""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

__all__ = ["ResourceLockModel", "ResourceLockORM"]


class ResourceLockORM(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """资源锁（`docs/07` §4.3 #22；`docs/02` §24）。"""

    __tablename__ = "resource_locks"

    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False)
    mode: Mapped[str] = mapped_column(String(30), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(100), nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)


ResourceLockModel = ResourceLockORM
"""`docs/07` §4.3 使用的类名；与 `ResourceLockORM` 是同一个类。"""
