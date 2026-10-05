"""工程模型仓储（`docs/07` §12 P05 最小集；`docs/02` §11 / §12 / §22）。

`models` 表**没有** `tenant_id` 列：它的租户归属经 `project_id → projects.tenant_id`
传递（`docs/02` §22）。因此本仓储必须覆写 `tenant_criteria`，用子查询把租户过滤
追到 `projects` —— 这正是 `docs/02` §11「必须同时限制 `tenant_id` + `resource_id`」
对间接归属实体的要求；**禁止**退化为「不过滤租户」。

`version` 为乐观并发版本号（`docs/07` §4.3 #14；`docs/02` §12），
与 `software_versions.version`（版本号字符串）语义不同。
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import ColumnElement, select

from app.infrastructure.database.models.model import ModelORM
from app.infrastructure.database.models.project import ProjectORM
from app.infrastructure.database.repositories.base import (
    DEFAULT_PAGE_SIZE,
    TenantScopedRepository,
    VersionedRepository,
)

__all__ = ["ModelRepository"]


class ModelRepository(TenantScopedRepository[ModelORM], VersionedRepository[ModelORM]):
    """工程模型仓储（`docs/02` §22；`docs/07` §4.3 #14）。

    能力：`get` / `add` / `remove` / `list_all`（`docs/02` §26）＋
    `get_for_tenant` / `list_for_tenant` / `remove_for_tenant`（`docs/02` §11，租户经
    `projects` 追溯）＋ `list_by_project` ＋ `update`（乐观并发，`docs/02` §12）。
    绝不 `commit`（`docs/07` §14.4）。
    """

    model = ModelORM

    def tenant_criteria(self, tenant_id: str) -> ColumnElement[bool]:
        """租户过滤：`project_id` 必须属于该租户（`docs/02` §11）。

        用 `IN (SELECT projects.id WHERE projects.tenant_id = :tenant_id)` 表达，
        避免 JOIN 造成的行放大，也避免调用方自行拼接租户条件。
        """
        return ModelORM.project_id.in_(
            select(ProjectORM.id).where(ProjectORM.tenant_id == tenant_id)
        )

    async def list_by_project(
        self,
        project_id: str | UUID,
        tenant_id: str,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[ModelORM]:
        """列出某项目下的模型（`docs/02` §11 / §22）。

        `tenant_id` 是**必填**参数：`project_id` 与 `tenant_id` 必须同时限制，
        否则就是跨租户读取（`docs/02` §11；`docs/07` §14.3）。
        """
        stmt = select(ModelORM).where(
            ModelORM.project_id == str(project_id),
            self.tenant_criteria(tenant_id),
        )
        result = await self.session.execute(self._ordered(stmt, limit, offset))
        return list(result.scalars().all())
