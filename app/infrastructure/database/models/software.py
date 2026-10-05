"""软件注册表：Software / Product / Version / Instance（`docs/07` §4.3 #10–#13；`docs/02` §21）。

表名 `software` / `software_products` / `software_versions` / `software_instances`。

设计要点：

- 四张表是**软件无关**的注册表（`docs/07` §14.5：接入新软件只允许新增
  Adapter + Mapping + API Registry 数据，**不得**改 9 Tool Contract）。
  因此本文件不得出现任何厂商专属字段或取值。
- `software_instances.status` 取值见 `app.domain.enums.SoftwareConnectionState`
  （`docs/02` §19 软件实例生命周期）。
- `credential_reference` **只存引用**，绝不存密钥本身（`docs/07` §14.3：
  禁止明文 API Key 入库；`docs/02` §21 Secret / Credential Provider）。
  密钥值只能经运行环境注入。
- `version` 列（`VersionMixin`）用于乐观并发；注意与 `software_versions.version`
  （**软件版本号字符串**）语义完全不同，二者不可混用。
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

__all__ = [
    "SoftwareInstanceModel",
    "SoftwareInstanceORM",
    "SoftwareModel",
    "SoftwareORM",
    "SoftwareProductModel",
    "SoftwareProductORM",
    "SoftwareVersionModel",
    "SoftwareVersionORM",
]


class SoftwareORM(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """软件（厂商级，`docs/07` §4.3 #10）。"""

    __tablename__ = "software"

    vendor: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)


class SoftwareProductORM(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """软件产品（`docs/07` §4.3 #11）。"""

    __tablename__ = "software_products"

    software_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    product: Mapped[str] = mapped_column(String(150), nullable=False)


class SoftwareVersionORM(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """软件版本（`docs/07` §4.3 #12）。

    `version` 是**版本号字符串**（如 `"2024.1"`），不是乐观并发版本号。
    """

    __tablename__ = "software_versions"

    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(100), nullable=False)


class SoftwareInstanceORM(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    """软件实例（`docs/07` §4.3 #13：`instance_id` / `credential_reference` / `version`）。

    字段映射（`docs/07` §4.3 ↔ `docs/02` §21）：

    | `docs/07` §4.3 | 本表 |
    | --- | --- |
    | `instance_id` | 主键 `id`（UUID 字符串） |
    | `credential_reference` | `credential_reference`（**引用**，非密钥值） |
    | `version` | `version`（乐观并发） |

    `endpoint` 为软件实例的访问地址（`docs/02` §21）；`status` 取值见
    `SoftwareConnectionState`。Core Alpha 的 Mock 实例由 P07 Seed 落库。
    """

    __tablename__ = "software_instances"

    version_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    endpoint: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    credential_reference: Mapped[str | None] = mapped_column(String(500))


SoftwareModel = SoftwareORM
"""`docs/07` §4.3 使用的类名；与 `SoftwareORM` 是同一个类。"""

SoftwareProductModel = SoftwareProductORM
"""`docs/07` §4.3 使用的类名；与 `SoftwareProductORM` 是同一个类。"""

SoftwareVersionModel = SoftwareVersionORM
"""`docs/07` §4.3 使用的类名；与 `SoftwareVersionORM` 是同一个类。"""

SoftwareInstanceModel = SoftwareInstanceORM
"""`docs/07` §4.3 使用的类名；与 `SoftwareInstanceORM` 是同一个类。"""
