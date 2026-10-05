"""软件仓储（`docs/07` §12 P05 最小集；`docs/02` §21）。

`software` 是**软件无关**的厂商级注册表（`docs/07` §14.5）：本文件不得出现任何
厂商专属字段或取值，也不得承载 Adapter / capability 判定（`docs/02` §17）。

本仓储只覆盖 `docs/07` §12 P05 最小集里的 `software` 表；
`software_products` / `software_versions` / `software_instances` 的仓储
由后续批次（P07 Seed / P08 Registry / P14 ResourceResolver）按需新增。
"""

from __future__ import annotations

from sqlalchemy import select

from app.infrastructure.database.models.software import SoftwareORM
from app.infrastructure.database.repositories.base import DEFAULT_PAGE_SIZE, BaseRepository

__all__ = ["SoftwareRepository"]


class SoftwareRepository(BaseRepository[SoftwareORM]):
    """软件仓储（`docs/02` §21；`docs/07` §4.3 #10）。

    提供 `get` / `add` / `remove` / `list_all`（`docs/02` §26）＋ 按厂商查。
    绝不 `commit`（`docs/07` §14.4）。
    """

    model = SoftwareORM

    async def list_by_vendor(
        self,
        vendor: str,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[SoftwareORM]:
        """按厂商列出软件（`docs/02` §21：`vendor` 为厂商级标识）。

        `software.name` 未声明唯一（`docs/07` §4.3 #10 只列 `vendor`），故按列表返回。
        """
        stmt = select(SoftwareORM).where(SoftwareORM.vendor == vendor)
        result = await self.session.execute(self._ordered(stmt, limit, offset))
        return list(result.scalars().all())
