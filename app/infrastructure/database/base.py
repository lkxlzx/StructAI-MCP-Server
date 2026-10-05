"""SQLAlchemy Base 与命名约定（`docs/02` §14；`docs/07` §4.3）。

权威来源：

- `docs/02` §14（`source9` §14）—— `NAMING_CONVENTION` 与
  `class Base(DeclarativeBase): metadata = MetaData(naming_convention=...)`，逐字照抄。
- `docs/02` §17 —— ORM 只负责 persistence / indexes / foreign keys / unique constraints /
  database-level consistency；**不负责** MCP protocol、permission decision、
  capability decision、adapter logic、engineering calculation、AI logic。
- `docs/07` §4.3 —— 全部 24 张表共用的字段规则：
  **UUID 主键 + `created_at` + `updated_at`**；可变资源带 `version`。

规范之上的落地补充（只提供**实现手段**，不改变任何字段名 / 类型 / 语义）：

- `UUIDPrimaryKeyMixin` —— 单主键表的 UUID 主键（`String(36)` + `uuid4` 默认值）。
  `docs/02` §18.1 只给 `TenantORM` 写了默认值；本文件把同一写法推广到全部单主键表，
  否则任何 `INSERT` 都必须由调用方显式提供主键。
  ⚠️ 主键列类型沿用 `docs/02` §18（本批次的源码级权威）的 `String(36)`；`docs/02` §3.2
  （Artifact 批次）写作 `Mapped[UUID]`，二者语义等价（UUID 字符串）。待 P29 落地时若统一
  为 `Uuid` 类型，以 Alembic 迁移承接，不在本批次静默改表（`docs/07` §14.3）。
- `TimestampMixin` —— `created_at` / `updated_at`。`docs/07` §4.3 把它列为全部表的硬性规则，
  而 `docs/02` §18–§24 未逐表写出，故在此集中实现一次，避免 24 张表重复 3 行。
- `VersionMixin` —— 乐观并发 `version`（`docs/02` §12 / §36）。`docs/07` §4.3 只对
  **可变资源** 要求该列：`projects` / `software_instances` / `models` / `tasks`。

分层红线（`docs/07` §14.1）：ORM 只允许出现在 `app/infrastructure/database/`；
`app/domain/` 不得引用本模块，本模块也不得引用 Interface 层。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final
from uuid import uuid4

from sqlalchemy import DateTime, Integer, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = [
    "NAMING_CONVENTION",
    "Base",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "VersionMixin",
    "utcnow",
]

NAMING_CONVENTION: Final[dict[str, str]] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
"""约束命名约定（`docs/02` §14，逐字照抄）。

显式命名是 Alembic 可迁移性的前提：匿名约束在 SQLite → PostgreSQL 的迁移中无法稳定比对。
"""


def utcnow() -> datetime:
    """返回带时区的当前 UTC 时间（`docs/02` §18.1；Python ≥3.12 用 `datetime.UTC`）。"""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """全部 ORM Model 的声明式基类（`docs/02` §14）。"""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """单主键表的 UUID 主键（`docs/07` §4.3：UUID 主键）。

    列类型与默认值写法照抄 `docs/02` §18.1 `TenantORM.id`。
    复合主键的关联表（`user_roles` / `role_permissions` / `project_members` /
    `operation_capabilities`）**不**继承本 Mixin。
    """

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )


class TimestampMixin:
    """`created_at` / `updated_at`（`docs/07` §4.3 的通用字段规则）。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class VersionMixin:
    """乐观并发版本号（`docs/02` §12 / §36；`docs/07` §4.3）。

    只用于**可变资源**；每次成功更新必须 `version = version + 1`
    且以 `WHERE version = :expected` 做条件更新（`docs/02` §12）。
    """

    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )
