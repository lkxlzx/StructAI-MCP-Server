"""Repository 层导出（`docs/07` §12 P05；`docs/02` §26）。

本包是 P05「最小集 6 个仓储」的唯一入口（`docs/07` §12 P05：
Tenant / User / Project / Software / Model / Task），并提供**会话级**装配函数
`build_repositories(session)`。

为什么装配是会话级而不是进程级（`docs/02` §16 / §33）：

- Repository 持有 `AsyncSession`，而会话是**短生命周期**对象；
- 进程级容器（`app.container`）只持有 `session_factory`（P04 已装配）；
- 事务边界归 P06 UnitOfWork —— `build_repositories` 只把同一个 session 绑给各仓储，
  **不**开事务、**不**提交。

| 文件 | 仓储 | 表 | 规范 |
| --- | --- | --- | --- |
| `base.py` | 通用基类：`BaseRepository` / 租户隔离 / 乐观并发 | — | `docs/02` §26 / §11 / §12 |
| `tenant.py` | `TenantRepository` | `tenants` | `docs/02` §18.1 |
| `user.py` | `UserRepository` | `users` | `docs/02` §19 |
| `project.py` | `ProjectRepository` | `projects` | `docs/02` §20 |
| `software.py` | `SoftwareRepository` | `software` | `docs/02` §21 |
| `model.py` | `ModelRepository` | `models` | `docs/02` §22 |
| `task.py` | `TaskRepository` | `tasks` | `docs/02` §24 |
| `security.py` | `SessionRepository` / `RoleRepository` / `ProjectMembershipRepository`（P10） |
| `idempotency.py` | `IdempotencyStoreRepository`（P21） | `idempotency_records` | `docs/02` §28 |

红线（`docs/07` §14.1 / §14.4）：本包只允许被 `app/infrastructure/database/` 与
上层（Application / Interface）引用；**不得反向依赖 Interface 层**；
**Repository 不得自行 `commit`**。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.repositories.base import (
    DEFAULT_PAGE_SIZE,
    BaseRepository,
    TenantScopedRepository,
    VersionedRepository,
)
from app.infrastructure.database.repositories.idempotency import (
    IdempotencyStoreRepository,
    build_idempotency_store,
)
from app.infrastructure.database.repositories.model import ModelRepository
from app.infrastructure.database.repositories.project import ProjectRepository
from app.infrastructure.database.repositories.resource import (
    ResourceStoreRepository,
    build_resource_store,
)
from app.infrastructure.database.repositories.security import (
    ProjectMembershipRepository,
    RoleRepository,
    SessionRepository,
    build_security_stores,
)
from app.infrastructure.database.repositories.software import SoftwareRepository
from app.infrastructure.database.repositories.task import TaskRepository
from app.infrastructure.database.repositories.tenant import TenantRepository
from app.infrastructure.database.repositories.user import UserRepository

__all__ = [
    "BaseRepository",
    "DEFAULT_PAGE_SIZE",
    "IdempotencyStoreRepository",
    "ModelRepository",
    "ProjectMembershipRepository",
    "ProjectRepository",
    "ResourceStoreRepository",
    "RepositoryBundle",
    "RoleRepository",
    "SessionRepository",
    "SoftwareRepository",
    "TaskRepository",
    "TenantRepository",
    "TenantScopedRepository",
    "UserRepository",
    "VersionedRepository",
    "build_idempotency_store",
    "build_repositories",
    "build_resource_store",
    "build_security_stores",
]


@dataclass(frozen=True, slots=True)
class RepositoryBundle:
    """一组绑定在同一 `AsyncSession` 上的仓储（P05 最小集）。

    ⚠️ 这是**会话级**对象：生命周期与 `session` 绑定，不得放进进程级容器或全局单例
    （`blue` §123；`docs/02` §33）。事务由 P06 UnitOfWork 统一提交 / 回滚。
    """

    tenant: TenantRepository
    user: UserRepository
    project: ProjectRepository
    software: SoftwareRepository
    model: ModelRepository
    task: TaskRepository


def build_repositories(session: AsyncSession) -> RepositoryBundle:
    """为给定会话装配最小集仓储（`docs/02` §16 / §33）。

    Args:
        session: 已存在的 `AsyncSession`（通常由 P06 UnitOfWork 提供）。

    Returns:
        `RepositoryBundle`：6 个仓储共享同一个会话，因此共享同一个事务。

    ⚠️ 本函数**不**开启事务、**不**提交、**不**建立连接。
    """
    return RepositoryBundle(
        tenant=TenantRepository(session),
        user=UserRepository(session),
        project=ProjectRepository(session),
        software=SoftwareRepository(session),
        model=ModelRepository(session),
        task=TaskRepository(session),
    )
