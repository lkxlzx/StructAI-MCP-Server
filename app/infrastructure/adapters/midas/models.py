"""Infrastructure · Adapters · MIDAS · Models —— 7 张 MIDAS 专属表（`docs/07` §4.4）。

权威来源
--------
- `docs/04` §9（Registry 数据模型）—— **7** 张表名：`midas_api_sources` /
  `midas_api_endpoints` / `midas_api_schemas` / `midas_api_versions` /
  `midas_api_mappings` / `midas_api_verifications` / `midas_capability_mappings`。
- `docs/04` §10（`MidasApiSource`）/ §11（`MidasApiEndpoint`）/ §12（`MidasApiSchema`）——
  三张表的字段**逐字**照抄。
- `docs/04` §17（`MidasApiMapping`）—— `operation` / `product` / `version_range` /
  `method` / `path` / `request_schema` / `response_schema` / `transformer` /
  `verification_status`（本模块据此设计 `midas_api_mappings` 的列）。
- `docs/07` §4.4 —— 另外 4 张表「字段自行设计并回填本文档 §4.4」（§16 R12）。
- `docs/07` §7.2 —— `availability → verification_status` 与 `schema_uri` 的映射规则。

落地裁决（只补实现手段，不改字段名 / 语义）
------------------------------------------
1. **7 张表用**独立**的声明式基类**：Core 的 `docs/07` §4.3 冻结的是 **24** 张表
   （`Base.metadata`），而 §4.4 的 7 张是 **Adapter 专属**表。把 MIDAS 表挂到同一个
   `Base.metadata` 上会让「Core 建表恰好 24 张」这条既有门槛失效，且 Core 就必须
   引用 MIDAS 模块（违反 §14.2 的 `grep -ri midas app/` = 0）。因此本模块自建
   `MIDAS_METADATA`（**复用** Core 的 `NAMING_CONVENTION` 以保证约束命名一致），
   两张表集**互不干扰**；建表由 **Alembic 迁移**完成（`docs/07` §12 P119 门槛 ⑦）。
2. **`midas_api_endpoints` 增加 `read_root` 列**：`docs/07` §12 P119 门槛 ② 要求
   「`path` / `method` / `read_root` / `verification_status` 可回查」，而 §4.4 的字段表
   没有 `read_root`。裁决：**加列**（数据里 `wrapper.read_root` 确实存在，
   `registry/README.md` §8.1），并在 `docs/07` §4.4 回填。
3. **4 张无定义的表的字段设计**（`docs/07` §16 R12）—— 只放**已存在的数据**，
   不新增语义：
   - `midas_api_versions`：`product` / `product_family` / `version` / `version_range` /
     `solver` / `supported` / `source_id`；
   - `midas_api_mappings`：`operation` / `product` / `version_range` / `method` / `path` /
     `endpoint_key` / `sequence` / `composite` / `request_schema` / `response_schema` /
     `transformer` / `verification_status`（列名照抄 `docs/04` §17 的 dataclass）；
   - `midas_api_verifications`：`endpoint_key` / `contract_level`（L1–L5，`docs/04` §71）/
     `product` / `version_range` / `method` / `path` / `status` / `schema_hash` /
     `detail` / `verified_at`（对应 `docs/04` §18 的 Contract Snapshot 字段）；
   - `midas_capability_mappings`：`capability` / `operation` / `product` / `version_range` /
     `endpoint_key` / `supported` / `source`。
4. **唯一键照抄规范**：`midas_api_endpoints` = `(product, version_range, method, path)`
   （§11 原文）；`midas_api_schemas.schema_uri` 唯一（§12 原文）；其余 4 张表的唯一键
   由本模块按「数据本身天然唯一」的维度选取（见各表 docstring）。
5. **`midas_api_endpoints` 的唯一键**加** `table_type`**（**显式偏离** §11 的
   `(product, version_range, method, path)`）：数据里 **199** 个 `POST.TABLE.*` 端点
   共用 `path=/POST/TABLE` + `method=POST`，仅靠 §11 的键会互相覆盖（实测：只能落
   **439** 个 key）。故唯一键扩为 `(product, version_range, method, path, table_type)`，
   非 POST 端点的 `table_type` 为空串；该偏离已回填 `docs/07` §4.4 与 §16。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
ORM 只允许出现在 Infrastructure 层；本模块位于 MIDAS 子包内（该子包是
`grep -ri midas app/` 的**唯一**豁免区），**不**被 Core 引用，**不**依赖
`app.interfaces`。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final

from sqlalchemy import JSON, Boolean, DateTime, Integer, MetaData, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.infrastructure.database.base import (
    NAMING_CONVENTION,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    utcnow,
)

__all__ = [
    "MIDAS_METADATA",
    "MIDAS_TABLE_NAMES",
    "MidasApiEndpointORM",
    "MidasApiMappingORM",
    "MidasApiSchemaORM",
    "MidasApiSourceORM",
    "MidasApiVerificationORM",
    "MidasApiVersionORM",
    "MidasBase",
    "MidasCapabilityMappingORM",
]

MIDAS_METADATA: Final[MetaData] = MetaData(naming_convention=NAMING_CONVENTION)
"""MIDAS 专属表的 MetaData（见裁决 1；与 Core 的 `Base.metadata` 分开）。"""


class MidasBase(DeclarativeBase):
    """MIDAS 专属 ORM 基类（`docs/04` §10–§12；见裁决 1）。"""

    metadata = MIDAS_METADATA


class MidasApiSourceORM(UUIDPrimaryKeyMixin, MidasBase):
    """`midas_api_sources`（`docs/04` §10，字段逐字照抄）。"""

    __tablename__ = "midas_api_sources"

    source_url: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    source_title: Mapped[str | None] = mapped_column(String(500))
    product: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str | None] = mapped_column(String(50))
    manual_revision: Mapped[str | None] = mapped_column(String(100))
    source_hash: Mapped[str | None] = mapped_column(String(128))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class MidasApiEndpointORM(UUIDPrimaryKeyMixin, MidasBase):
    """`midas_api_endpoints`（`docs/04` §11；唯一键 `(product, version_range, method, path)`）。"""

    __tablename__ = "midas_api_endpoints"
    __table_args__ = (
        UniqueConstraint(
            "product",
            "version_range",
            "method",
            "path",
            "table_type",
            "operation",
            name="uq_midas_api_endpoints_identity",
        ),
    )

    product: Mapped[str] = mapped_column(String(100), nullable=False)
    product_family: Mapped[str | None] = mapped_column(String(100))
    version_range: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    operation: Mapped[str | None] = mapped_column(String(200))
    request_schema_id: Mapped[str | None] = mapped_column(String(36))
    response_schema_id: Mapped[str | None] = mapped_column(String(36))
    verification_status: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(36))
    deprecated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_root: Mapped[str | None] = mapped_column(String(200))
    """见裁决 2（`docs/07` §12 P119 门槛 ② 要求可回查 `read_root`）。"""
    table_type: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    """POST 命名空间的 `Argument.TABLE_TYPE`（见裁决 5；空串 = 非 POST 表端点）。"""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class MidasApiSchemaORM(UUIDPrimaryKeyMixin, MidasBase):
    """`midas_api_schemas`（`docs/04` §12；`schema_uri` 唯一，`schema_json` **原样**）。"""

    __tablename__ = "midas_api_schemas"

    schema_uri: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    direction: Mapped[str | None] = mapped_column(String(20))
    product: Mapped[str | None] = mapped_column(String(100))
    version_range: Mapped[str | None] = mapped_column(String(100))
    schema_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    verification_status: Mapped[str | None] = mapped_column(String(30))
    source_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class MidasApiVersionORM(UUIDPrimaryKeyMixin, TimestampMixin, MidasBase):
    """`midas_api_versions`（字段自行设计，见裁决 3；唯一键 `(product, version)`）。"""

    __tablename__ = "midas_api_versions"
    __table_args__ = (
        UniqueConstraint("product", "version", name="uq_midas_api_versions_identity"),
    )

    product: Mapped[str] = mapped_column(String(100), nullable=False)
    product_family: Mapped[str | None] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    version_range: Mapped[str | None] = mapped_column(String(100))
    solver: Mapped[str | None] = mapped_column(String(50))
    supported: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(36))


class MidasApiMappingORM(UUIDPrimaryKeyMixin, TimestampMixin, MidasBase):
    """`midas_api_mappings`（字段照抄 `docs/04` §17 的 dataclass；见裁决 3）。

    唯一键 `(operation, product, version_range, sequence)` —— 组合 Operation 的每一步
    各占一行（`docs/07` §6.5 的多步编排因此可回查）。
    """

    __tablename__ = "midas_api_mappings"
    __table_args__ = (
        UniqueConstraint(
            "operation",
            "product",
            "version_range",
            "sequence",
            name="uq_midas_api_mappings_identity",
        ),
    )

    operation: Mapped[str] = mapped_column(String(200), nullable=False)
    product: Mapped[str] = mapped_column(String(100), nullable=False)
    version_range: Mapped[str] = mapped_column(String(100), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    endpoint_key: Mapped[str] = mapped_column(String(200), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    composite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    request_schema: Mapped[str | None] = mapped_column(String(500))
    response_schema: Mapped[str | None] = mapped_column(String(500))
    transformer: Mapped[str | None] = mapped_column(String(100))
    verification_status: Mapped[str] = mapped_column(String(30), nullable=False)


class MidasApiVerificationORM(UUIDPrimaryKeyMixin, MidasBase):
    """`midas_api_verifications`（字段自行设计，见裁决 3；Contract Test 记录）。

    唯一键 `(endpoint_key, contract_level, product, version_range)` —— 一个端点在
    某一分层（L1–L5，`docs/04` §71）上只保留一条**最新**结论。
    """

    __tablename__ = "midas_api_verifications"
    __table_args__ = (
        UniqueConstraint(
            "endpoint_key",
            "contract_level",
            "product",
            "version_range",
            name="uq_midas_api_verifications_identity",
        ),
    )

    endpoint_key: Mapped[str] = mapped_column(String(200), nullable=False)
    contract_level: Mapped[str] = mapped_column(String(10), nullable=False)
    product: Mapped[str] = mapped_column(String(100), nullable=False)
    version_range: Mapped[str] = mapped_column(String(100), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    schema_hash: Mapped[str | None] = mapped_column(String(128))
    detail: Mapped[str | None] = mapped_column(String(500))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class MidasCapabilityMappingORM(UUIDPrimaryKeyMixin, TimestampMixin, MidasBase):
    """`midas_capability_mappings`（字段自行设计，见裁决 3）。

    唯一键 `(capability, endpoint_key, product, version_range)` —— 一条能力可由
    多个端点支撑，逐对登记。
    """

    __tablename__ = "midas_capability_mappings"
    __table_args__ = (
        UniqueConstraint(
            "capability",
            "endpoint_key",
            "product",
            "version_range",
            name="uq_midas_capability_mappings_identity",
        ),
    )

    capability: Mapped[str] = mapped_column(String(100), nullable=False)
    endpoint_key: Mapped[str] = mapped_column(String(200), nullable=False)
    operation: Mapped[str | None] = mapped_column(String(200))
    product: Mapped[str] = mapped_column(String(100), nullable=False)
    version_range: Mapped[str] = mapped_column(String(100), nullable=False)
    supported: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source: Mapped[str | None] = mapped_column(String(100))


MIDAS_TABLE_NAMES: Final[tuple[str, ...]] = tuple(sorted(MIDAS_METADATA.tables))
"""7 张 MIDAS 专属表名（`docs/07` §4.4；供迁移与验收断言）。"""
