"""任务仓储（`docs/07` §12 P05 最小集；`docs/02` §11 / §12 / §24）。

`tasks` 是 Tenant-owned（`tenant_id` 列，`docs/07` §4.3 #19）＋ 可变资源
（`version` 列）→ 同时继承 `TenantScopedRepository` 与 `VersionedRepository`。

本仓储**只做 persistence**：状态机（12 态）、队列、租约、恢复、取消全部属于
P22–P28（`docs/02` §10 / §34 / §40；`docs/07` §10）。因此这里**不**做状态校验、
**不**改 `status` 以外的业务语义、**不**把恢复中的任务标记为 `COMPLETED`
（`docs/07` §14.4）。
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.infrastructure.database.models.task import TaskORM
from app.infrastructure.database.repositories.base import (
    DEFAULT_PAGE_SIZE,
    TenantScopedRepository,
    VersionedRepository,
)

__all__ = ["TaskRepository"]


class TaskRepository(TenantScopedRepository[TaskORM], VersionedRepository[TaskORM]):
    """任务仓储（`docs/02` §24；`docs/07` §4.3 #19）。

    能力：`get` / `add` / `remove` / `list_all`（`docs/02` §26）＋
    `get_for_tenant` / `list_for_tenant` / `remove_for_tenant`（`docs/02` §11）＋
    `list_by_project` / `list_by_status` ＋ `update`（乐观并发，`docs/02` §12）。
    绝不 `commit`（`docs/07` §14.4）。
    """

    model = TaskORM

    async def list_by_project(
        self,
        project_id: str | UUID,
        tenant_id: str,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[TaskORM]:
        """列出某项目下的任务（`docs/02` §11：`tenant_id` + `project_id` 同时限制）。"""
        stmt = select(TaskORM).where(
            TaskORM.project_id == str(project_id),
            self.tenant_criteria(tenant_id),
        )
        result = await self.session.execute(self._ordered(stmt, limit, offset))
        return list(result.scalars().all())

    async def list_by_status(
        self,
        status: str,
        tenant_id: str,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[TaskORM]:
        """列出某租户下指定状态的任务（`docs/02` §11；状态取值见 `TaskStatus`）。

        `status` 只作为**列过滤**，本仓储不判断状态迁移是否合法
        （状态机归 P22，`docs/02` §4 / §10）。
        """
        stmt = select(TaskORM).where(
            TaskORM.status == status,
            self.tenant_criteria(tenant_id),
        )
        result = await self.session.execute(self._ordered(stmt, limit, offset))
        return list(result.scalars().all())
