"""项目仓储（`docs/07` §12 P05 最小集；`docs/02` §11 / §12 / §20）。

`projects` 同时具备两个横切属性：

- **Tenant-owned**（`tenant_id` 列，`docs/07` §4.3 #8）→ 继承 `TenantScopedRepository`，
  所有按租户的读取必须同时限制 `tenant_id` + `project_id`（`docs/02` §11）。
- **可变资源**（`version` 列）→ 继承 `VersionedRepository`，更新走
  `WHERE version = :expected` 条件更新，冲突抛 `STRUCTAI-1300`（`docs/02` §12）。
"""

from __future__ import annotations

from app.infrastructure.database.models.project import ProjectORM
from app.infrastructure.database.repositories.base import (
    TenantScopedRepository,
    VersionedRepository,
)

__all__ = ["ProjectRepository"]


class ProjectRepository(TenantScopedRepository[ProjectORM], VersionedRepository[ProjectORM]):
    """项目仓储（`docs/02` §20；`docs/07` §4.3 #8）。

    能力：`get` / `add` / `remove` / `list_all`（`docs/02` §26）＋
    `get_for_tenant` / `list_for_tenant` / `remove_for_tenant`（`docs/02` §11）＋
    `update`（乐观并发，`docs/02` §12）。绝不 `commit`（`docs/07` §14.4）。
    """

    model = ProjectORM
