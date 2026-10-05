"""用户仓储（`docs/07` §12 P05 最小集；`docs/02` §11 / §19）。

`users` 是 Tenant-owned（`tenant_id` 列，`docs/07` §4.3 #2），因此继承
`TenantScopedRepository`：所有按租户的读取都必须**同时**限制
`tenant_id` + `user_id`（`docs/02` §11），禁止依赖 UI 过滤（`docs/07` §14.3）。

本仓储只做 persistence；认证 / RBAC 判定在 P10–P13（`docs/02` §19 末注）。
`password_hash` 只做列读写，绝不参与日志或错误信息（`docs/07` §14.3）。
"""

from __future__ import annotations

from sqlalchemy import select

from app.infrastructure.database.models.user import UserORM
from app.infrastructure.database.repositories.base import TenantScopedRepository

__all__ = ["UserRepository"]


class UserRepository(TenantScopedRepository[UserORM]):
    """用户仓储（`docs/02` §19；`docs/07` §4.3 #2）。

    `username` 在 P04 落地为**全局唯一**（`docs/07` §4.3 #2 的「`username(唯一)`」），
    但本仓储**不提供**不带租户的用户名查：全局唯一查会把租户过滤推给调用方，
    违反 `docs/02` §11 / `docs/07` §14.3（禁止依赖 UI / 上层过滤）。
    唯一入口是 `get_by_username_for_tenant`（租户由身份上下文决定，`docs/02` §22）。
    """

    model = UserORM

    async def get_by_username_for_tenant(self, username: str, tenant_id: str) -> UserORM | None:
        """在指定租户内按用户名读取（`docs/02` §11：`tenant_id` + 资源标识）。"""
        result = await self.session.execute(
            select(UserORM).where(
                UserORM.username == username,
                self.tenant_criteria(tenant_id),
            )
        )
        return result.scalar_one_or_none()
