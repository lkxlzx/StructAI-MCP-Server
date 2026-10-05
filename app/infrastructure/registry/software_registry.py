"""Registry · SoftwareRegistry —— 软件注册表（`docs/07` §12 P08；`docs/02` §19 / §21 / §100–§101）。

权威来源
--------
- `docs/02` §19（SoftwareRegistry）—— 查询集：`get_instance` / `get_product` / `get_version` /
  `list_instances`；覆盖 Vendor / Product / Version / Instance 四级。
- `docs/07` §4.3 #10–#13 —— 四张表：`software` / `software_products` / `software_versions` /
  `software_instances`。
- `docs/02` §100 / §101 —— Mock 软件链：`StructAI` / `Mock Engineering Software` / `1.0` /
  `Mock Instance`（P07 已落库）。
- `docs/07` §14.5 —— 接入新软件只允许新增 Adapter + Mapping + API Registry 数据；
  本模块是**软件无关**的注册表，不得出现任何厂商专属逻辑。

落地补充（只补实现手段，不改字段名 / 取值）
------------------------------------------
- 返回**不可变视图**（frozen dataclass）而非 ORM 实体：注册表在会话关闭后仍被使用，
  视图可避免「已过期 / 已分离实体」的隐式 I/O。
- **不下发 `credential_reference`**：凭据引用是 Adapter / CredentialProvider 的内部字段
  （`docs/02` §21；`docs/07` §8.5），注册表视图不暴露它，从源头避免 secret 外泄面
  （`docs/07` §14.3）。
- 只读装配：不写任何行、不提交事务（`docs/07` §14.4）。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.domain.errors import NotFoundError
from app.infrastructure.database.models import (
    SoftwareInstanceORM,
    SoftwareORM,
    SoftwareProductORM,
    SoftwareVersionORM,
)

__all__ = [
    "SoftwareInstanceView",
    "SoftwareProductView",
    "SoftwareRegistry",
    "SoftwareVersionView",
]

logger = logging.getLogger("structai.registry")


@dataclass(frozen=True, slots=True)
class SoftwareInstanceView:
    """软件实例视图（`docs/07` §4.3 #13；`docs/02` §19）。

    ⚠️ 不含 `credential_reference`（见模块 docstring）。
    """

    instance_id: str
    name: str
    endpoint: str | None
    status: str
    vendor: str
    product: str
    version: str


@dataclass(frozen=True, slots=True)
class SoftwareProductView:
    """软件产品视图（`docs/07` §4.3 #11；`docs/02` §19）。"""

    product_id: str
    software_id: str
    vendor: str
    product: str


@dataclass(frozen=True, slots=True)
class SoftwareVersionView:
    """软件版本视图（`docs/07` §4.3 #12；`docs/02` §19）。

    `version` 是**软件版本号字符串**（如 `1.0`），不是乐观并发版本号。
    """

    version_id: str
    product_id: str
    vendor: str
    product: str
    version: str


class SoftwareRegistry:
    """软件注册表（`docs/02` §19；`docs/07` §12 P08 门槛 ⑤）。

    **只读**：不写任何行、不提交事务（`docs/07` §14.4）。
    """

    def __init__(
        self,
        *,
        instances: Iterable[SoftwareInstanceView] = (),
        products: Iterable[SoftwareProductView] = (),
        versions: Iterable[SoftwareVersionView] = (),
    ) -> None:
        """由四级视图构造（Vendor 信息随 Product 一起下发）。"""
        self._instances: dict[str, SoftwareInstanceView] = {
            item.instance_id: item for item in instances
        }
        self._products: dict[str, SoftwareProductView] = {item.product_id: item for item in products}
        self._versions: dict[str, SoftwareVersionView] = {
            item.version_id: item for item in versions
        }

    # ===== 查询（`docs/02` §19）=====

    async def get_instance(self, instance_id: str) -> SoftwareInstanceView | None:
        """按实例 id 读取；不存在返回 `None`（`docs/02` §19）。"""
        return self._instances.get(instance_id)

    async def get_product(self, product_id: str) -> SoftwareProductView | None:
        """按产品 id 读取；不存在返回 `None`（`docs/02` §19）。"""
        return self._products.get(product_id)

    async def get_version(self, version_id: str) -> SoftwareVersionView | None:
        """按版本 id 读取；不存在返回 `None`（`docs/02` §19）。"""
        return self._versions.get(version_id)

    async def list_instances(self) -> list[SoftwareInstanceView]:
        """列出全部实例，按 `name` 升序（`docs/02` §19；输出确定性）。"""
        return [self._instances[key] for key in sorted(self._instances, key=self._sort_key)]

    # ===== 只读便捷入口 =====

    def require_instance(self, instance_id: str) -> SoftwareInstanceView:
        """按实例 id 读取；不存在 → `NotFoundError`（`docs/02` §15 的查找失败口径）。"""
        instance = self._instances.get(instance_id)
        if instance is None:
            raise NotFoundError(f"Software instance not found: {instance_id}")
        return instance

    def instances(self) -> tuple[SoftwareInstanceView, ...]:
        """全部实例（按 `name` 升序）。"""
        return tuple(self._instances[key] for key in sorted(self._instances, key=self._sort_key))

    def products(self) -> tuple[SoftwareProductView, ...]:
        """全部产品（按 `product` 升序）。"""
        return tuple(self._products[key] for key in sorted(self._products, key=self._sort_key))

    def versions(self) -> tuple[SoftwareVersionView, ...]:
        """全部版本（按 `version` 升序）。"""
        return tuple(self._versions[key] for key in sorted(self._versions, key=self._sort_key))

    def summary(self) -> dict[str, Any]:
        """装配摘要（供启动日志与验收证据；**不含**任何 secret，`docs/07` §14.3）。"""
        return {
            "instances": len(self._instances),
            "products": len(self._products),
            "versions": len(self._versions),
            "vendors": sorted({item.vendor for item in self._products.values()}),
        }

    def __len__(self) -> int:
        return len(self._instances)

    def _sort_key(self, identifier: str) -> str:
        """统一排序键：视图的 `name` / `product` / `version` 字段（取不到则退回 id）。"""
        for source in (self._instances, self._products, self._versions):
            item = source.get(identifier)
            if item is not None:
                for attribute in ("name", "product", "version"):
                    value = getattr(item, attribute, None)
                    if isinstance(value, str):
                        return value
        return identifier

    # ===== 装配 =====

    @classmethod
    async def load(
        cls,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> SoftwareRegistry | None:
        """从数据库装配软件注册表（`docs/02` §19）。

        Args:
            engine: 只用于只读地探查表是否存在（不建表、不改表）。
            session_factory: `create_session_factory(engine)` 的产物（P04）。

        Returns:
            已装配的注册表；`software` 表不存在时返回 `None`（数据库未配备）。
        """
        tables = await _table_names(engine)
        if "software" not in tables:
            logger.warning(
                "software registry not provisioned: table 'software' is absent; "
                "run `python -m app.infrastructure.database.seed`"
            )
            return None

        async with session_factory() as session:
            software = list((await session.execute(select(SoftwareORM))).scalars().all())
            products = (
                list((await session.execute(select(SoftwareProductORM))).scalars().all())
                if "software_products" in tables
                else []
            )
            versions = (
                list((await session.execute(select(SoftwareVersionORM))).scalars().all())
                if "software_versions" in tables
                else []
            )
            instances = (
                list((await session.execute(select(SoftwareInstanceORM))).scalars().all())
                if "software_instances" in tables
                else []
            )

        vendor_by_software = {row.id: row.vendor for row in software}
        product_by_id = {row.id: row for row in products}
        version_by_id = {row.id: row for row in versions}
        product_by_version = {
            row.id: product_by_id.get(row.product_id) for row in versions
        }

        def instance_view(row: SoftwareInstanceORM) -> SoftwareInstanceView:
            """把实例行与产品 / 版本链拼成视图（缺失链路时字段留空，不抛异常）。"""
            version_row = version_by_id.get(row.version_id)
            product_row = product_by_version.get(row.version_id)
            software_id = product_row.software_id if product_row is not None else ""
            return SoftwareInstanceView(
                instance_id=row.id,
                name=row.name,
                endpoint=row.endpoint,
                status=row.status,
                vendor=vendor_by_software.get(software_id, ""),
                product=product_row.product if product_row is not None else "",
                version=version_row.version if version_row is not None else "",
            )

        registry = cls(
            products=[
                SoftwareProductView(
                    product_id=row.id,
                    software_id=row.software_id,
                    vendor=vendor_by_software.get(row.software_id, ""),
                    product=row.product,
                )
                for row in products
            ],
            versions=[
                SoftwareVersionView(
                    version_id=row.id,
                    product_id=row.product_id,
                    vendor=vendor_by_software.get(
                        getattr(product_by_id.get(row.product_id), "software_id", ""), ""
                    ),
                    product=getattr(product_by_id.get(row.product_id), "product", ""),
                    version=row.version,
                )
                for row in versions
            ],
            instances=[instance_view(row) for row in instances],
        )
        logger.info("software registry assembled: %s", registry.summary())
        return registry


async def _table_names(engine: AsyncEngine) -> set[str]:
    """只读地取库中表名（**不**建表 / 不改表，`docs/07` §14.3）。"""
    async with engine.connect() as connection:
        return set(
            await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_table_names()
            )
        )
