"""租户仓储（`docs/07` §12 P05 最小集；`docs/02` §11 / §18.1）。

`tenants` 是**租户根实体**：它自身不是 Tenant-owned（没有 `tenant_id` 列），
而是全部 Tenant-owned 数据的隔离边界（`docs/02` §11）。因此本仓储不继承
`TenantScopedRepository`；按名称查租户属于平台级运维动作，不构成跨租户读取。
"""

from __future__ import annotations

from sqlalchemy import select

from app.infrastructure.database.models.tenant import TenantORM
from app.infrastructure.database.repositories.base import BaseRepository

__all__ = ["TenantRepository"]


class TenantRepository(BaseRepository[TenantORM]):
    """租户仓储（`docs/02` §18.1；`docs/07` §4.3 #1）。

    提供 `get` / `add` / `remove` / `list_all`（`docs/02` §26）＋ 按名称查。
    绝不 `commit`（`docs/07` §14.4）。
    """

    model = TenantORM

    async def get_by_name(self, name: str) -> TenantORM | None:
        """按租户名读取（`tenants.name` 唯一，`docs/02` §18.1）。

        Returns:
            命中的租户；不存在返回 `None`。
        """
        result = await self.session.execute(select(TenantORM).where(TenantORM.name == name))
        return result.scalar_one_or_none()
