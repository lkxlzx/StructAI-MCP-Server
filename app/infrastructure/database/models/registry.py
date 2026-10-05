"""Registry 持久化：Capability / Operation / OperationCapability
（`docs/07` §4.3 #16–#18；`docs/02` §23）。

表名 `capabilities` / `operations` / `operation_capabilities`。

- 三张表是**软件无关**的（`docs/07` §14.2：Capability 中禁止出现厂商名；
  §14.5：接入新软件不得改 9 Tool Contract）。取值种子见 `docs/02` §69–§70，
  由 P07 Seed 落库。
- `operations` 只存 `docs/02` §23 给出的 6 个持久化字段。`OperationDefinition`
  的其余字段（`required_permissions` / `required_capabilities` / `transactional` /
  `rollback_supported` / `dry_run_supported` / `recovery_policy`）不在本表，
  由 P08 Registry 与 Capability 关联表表达（`docs/07` §4.2 / §4.3 #17 只要求
  `name` / `tool` / `risk` / `mode` / `schemas`）。
- `operation_capabilities` 复合主键 `(operation_id, capability_id)`（`docs/02` §23）。
- 列名 `risk_level` / `execution_mode` 与 `OperationDefinition` 字段名一致
  （`docs/07` §4.2），取值见 `app.domain.enums.RiskLevel` / `ExecutionMode`。
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

__all__ = [
    "CapabilityModel",
    "CapabilityORM",
    "OperationCapabilityModel",
    "OperationCapabilityORM",
    "OperationModel",
    "OperationORM",
]


class CapabilityORM(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """能力（`docs/07` §4.3 #16；`docs/02` §23）。

    `code` 取值见 `app.domain.enums.Capability`（如 `MODEL.NODE.WRITE`）。
    """

    __tablename__ = "capabilities"

    code: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(500))


class OperationORM(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """操作（`docs/07` §4.3 #17；`docs/02` §23）。

    `name` 形如 `BUILD.COLUMN`；`input_schema` / `output_schema` 为 Schema URI
    （`docs/02` §14 Schema URI）。
    """

    __tablename__ = "operations"

    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    tool: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(30), nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    input_schema: Mapped[str] = mapped_column(String(500), nullable=False)
    output_schema: Mapped[str] = mapped_column(String(500), nullable=False)


class OperationCapabilityORM(TimestampMixin, Base):
    """操作-能力关联（`docs/07` §4.3 #18；`docs/02` §23）。

    复合主键 `(operation_id, capability_id)`；表达「该操作需要哪些能力」。
    """

    __tablename__ = "operation_capabilities"

    operation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    capability_id: Mapped[str] = mapped_column(String(36), primary_key=True)


CapabilityModel = CapabilityORM
"""`docs/07` §4.3 使用的类名；与 `CapabilityORM` 是同一个类。"""

OperationModel = OperationORM
"""`docs/07` §4.3 使用的类名；与 `OperationORM` 是同一个类。"""

OperationCapabilityModel = OperationCapabilityORM
"""`docs/07` §4.3 使用的类名；与 `OperationCapabilityORM` 是同一个类。"""
