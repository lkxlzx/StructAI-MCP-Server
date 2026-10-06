"""安全服务所需的会话级存储（`docs/07` §12 P10–P13；`docs/02` §11 / §19–§23 / §30）。

为什么需要这个模块
------------------
P10–P13 的 Application 安全服务（`app/application/security/`）**不得**依赖
`app.infrastructure`（`docs/07` §14.1 / §2.2）。它们只依赖 Domain 侧的结构化契约：

| 契约（`app.domain.protocols`） | 本模块的实现 |
| --- | --- |
| `UserLookup` | `repositories/user.py` 的 `UserRepository`（P05 已有，本批补 4 个方法） |
| `SessionStore` | `SessionRepository` |
| `RoleLookup` | `RoleRepository` |
| `ProjectMembershipLookup` | `ProjectMembershipRepository` |

`build_security_stores(session)` 把四者装配成一个 `SecurityStores`
（`docs/02` §33 的会话级装配口径，与 P05 的 `build_repositories(session)` 完全同构）。

红线（`docs/07` §14.1 / §14.4）
------------------------------
- 本模块只做 persistence：**不**判定权限、**不**决定租户归属、**不**出现任何厂商内容；
- 全部方法只 `SELECT` / `UPDATE` / `flush`，**绝不** `commit` / `rollback`
  —— 事务边界归 P06 `UnitOfWork`；
- **不得**改表：本模块只使用 P04 已落地的 24 张表（`docs/07` §14.3）。
  `docs/02` §25 的 `resource_acls` 表**不在**其中，故 ACL 的持久化不在本批
  （判定逻辑见 `app/application/security/permission.py` 的裁决）。

时间口径
--------
`docs/07` §4.3 的全部时间列都是 `DateTime(timezone=True)`，但 SQLite 不保存时区，
读回来是 naive datetime。若直接与 `datetime.now(UTC)` 比较会抛 `TypeError`。
故本模块在构造 Domain 记录时统一用 `_as_utc()` 补 `UTC`，
使 `SessionRecord.expires_at` 始终是**带时区**的 UTC 时间。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.protocols import (
    SecurityStores,
    SessionRecord,
    UserLookup,
)
from app.infrastructure.database.models import (
    PermissionORM,
    ProjectMemberORM,
    ProjectORM,
    RoleORM,
    RolePermissionORM,
    SessionORM,
    UserRoleORM,
)
from app.infrastructure.database.repositories.base import BaseRepository
from app.infrastructure.database.repositories.user import UserRepository

__all__ = [
    "ProjectMembershipRepository",
    "RoleRepository",
    "SessionRepository",
    "build_security_stores",
]


def _as_utc(value: datetime) -> datetime:
    """把数据库读回的时间统一为**带时区**的 UTC（见模块的时间口径说明）。

    Args:
        value: `DateTime(timezone=True)` 列的值（SQLite 上可能是 naive）。

    Returns:
        带 `UTC` 时区的同一时刻；已是带时区的值按同一时刻换算。
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _as_utc_optional(value: datetime | None) -> datetime | None:
    """`_as_utc` 的可空版本。"""
    return None if value is None else _as_utc(value)


class SessionRepository(BaseRepository[SessionORM]):
    """会话仓储（`docs/02` §10 / §11 / §19–§21；`docs/07` §4.3 #7）。

    ⚠️ **不**继承 `TenantScopedRepository`：token 校验发生在**任何身份存在之前**
    （`docs/02` §20：`Client Token → Hash → DB lookup`），此时没有 `tenant_id` 可过滤。
    租户隔离由返回记录自带的 `tenant_id` 承载，并由上层
    （`SessionService` → `UserLookup.get_by_id_for_tenant`）继续强制
    （`docs/02` §11 / §22）。会话的**创建**必须显式给出 `tenant_id`，无法凭空产生。

    🔴 本仓储**不**提供任何读取明文 token 的能力：表里只有 `token_hash`
    （`docs/07` §8.3），本模块也只接受 / 返回哈希。
    """

    model = SessionORM

    async def create(
        self,
        *,
        user_id: str,
        tenant_id: str,
        token_hash: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> SessionRecord:
        """新建会话（`docs/02` §19 的 `session_repository.create(...)`）。

        Args:
            user_id: 用户标识。
            tenant_id: 租户标识（会话绑定 User + Tenant，`docs/07` §8.3）。
            token_hash: **只**写哈希（`docs/02` §13）。
            created_at: 创建时间（`docs/02` §10 的列）。
            expires_at: 过期时间（`docs/02` §19 的 `now + lifetime`）。

        Returns:
            新建的会话记录。

        ⚠️ 只 `add` + `flush`，**不 `commit`**（`docs/07` §14.4）。
        """
        session = SessionORM(
            user_id=str(user_id),
            tenant_id=str(tenant_id),
            token_hash=token_hash,
            created_at=created_at,
            expires_at=expires_at,
            revoked=False,
            last_seen_at=None,
        )
        await self.add(session)
        return _to_record(session)

    async def get_by_token_hash(self, token_hash: str) -> SessionRecord | None:
        """按 token 哈希反查会话（`docs/02` §20）。

        Args:
            token_hash: `TokenService.hash(token)` 的产物。

        Returns:
            命中的会话记录；不存在返回 `None`（不抛异常 —— 调用方统一转成
            形状一致的 `STRUCTAI-4000`，见 `session.py` 的失败口径裁决）。
        """
        result = await self.session.execute(
            select(SessionORM).where(SessionORM.token_hash == token_hash)
        )
        session = result.scalar_one_or_none()
        return None if session is None else _to_record(session)

    async def revoke(self, session_id: str) -> bool:
        """把会话置为已撤销（`docs/02` §21）。

        Args:
            session_id: 会话标识。

        Returns:
            `True` 表示本次确实由「未撤销」变为「已撤销」；会话不存在或已撤销为 `False`
            （两种情况**不做区分**，避免存在性泄露，`docs/02` §48）。
        """
        outcome = cast(
            "CursorResult[Any]",
            await self.session.execute(
                sa_update(SessionORM)
                .where(SessionORM.id == str(session_id), SessionORM.revoked.is_(False))
                .values(revoked=True)
                .execution_options(synchronize_session=False)
            ),
        )
        return outcome.rowcount == 1

    async def revoke_all_for_user(self, user_id: str) -> int:
        """撤销某用户的全部会话（`docs/02` §21：改口令 / 安全事件 / 全端登出）。

        Args:
            user_id: 用户标识。

        Returns:
            本次被撤销的会话数。
        """
        outcome = cast(
            "CursorResult[Any]",
            await self.session.execute(
                sa_update(SessionORM)
                .where(SessionORM.user_id == str(user_id), SessionORM.revoked.is_(False))
                .values(revoked=True)
                .execution_options(synchronize_session=False)
            ),
        )
        return int(outcome.rowcount or 0)

    async def touch(self, session_id: str, seen_at: datetime) -> None:
        """记录会话最近活动时间（`docs/02` §10 的 `last_seen_at`；§11 的 `touch`）。

        Args:
            session_id: 会话标识。
            seen_at: 最近活动时间（UTC）。

        ⚠️ 只更新 `last_seen_at`，**不**延长 `expires_at`（`docs/07` §8.3）。
        """
        await self.session.execute(
            sa_update(SessionORM)
            .where(SessionORM.id == str(session_id))
            .values(last_seen_at=seen_at)
            .execution_options(synchronize_session=False)
        )

    async def cleanup_expired(self, now: datetime) -> int:
        """把已过期会话置为撤销（`docs/02` §11 的 `cleanup_expired`）。

        Args:
            now: 判定基准时间（UTC）。

        Returns:
            本次被清理的会话数。

        ⚠️ 采取**标记撤销**而不是删除行：会话是审计对象（`docs/02` §59），
        物理删除属数据保留策略（`docs/02` §40 / §45），不在本批。
        """
        outcome = cast(
            "CursorResult[Any]",
            await self.session.execute(
                sa_update(SessionORM)
                .where(SessionORM.expires_at <= now, SessionORM.revoked.is_(False))
                .values(revoked=True)
                .execution_options(synchronize_session=False)
            ),
        )
        return int(outcome.rowcount or 0)


class RoleRepository(BaseRepository[RoleORM]):
    """角色 / 权限读取仓储（`docs/02` §19 / §23 / §30；`docs/07` §4.3 #3 / #4 / #5 / #6）。

    覆盖四张表：`roles` / `role_permissions` / `permissions` / `user_roles`。
    只读，不写（角色与权限的变更属管理面，`docs/02` §59）。

    ⚠️ `role_names_for_user` / `permission_codes_for_user` 以 `user_id` 为唯一入参：
    `users.id` 是 UUID 主键，本身即全局唯一，且 `user_roles` 只连 `user_id ↔ role_id`
    （`docs/02` §19），不引入跨租户读面。按角色名解析权限时**必须**带 `tenant_id`
    （`roles` 是 Tenant-owned，`docs/07` §4.3 #3）。
    """

    model = RoleORM

    async def role_names_for_user(self, user_id: str) -> list[str]:
        """用户持有的角色名（`docs/02` §19：`get_user_roles(user_id)`）。

        Args:
            user_id: 用户标识。

        Returns:
            角色名，按名称升序；无角色为空列表。
        """
        result = await self.session.execute(
            select(RoleORM.name)
            .join(UserRoleORM, UserRoleORM.role_id == RoleORM.id)
            .where(UserRoleORM.user_id == str(user_id))
            .order_by(RoleORM.name)
        )
        return list(result.scalars().all())

    async def permission_codes_for_user(self, user_id: str) -> set[str]:
        """用户角色权限的并集（`docs/02` §30 第 1–2 步）。

        Args:
            user_id: 用户标识。

        Returns:
            权限码集合（`user_roles → role_permissions → permissions`）。
        """
        result = await self.session.execute(
            select(PermissionORM.code)
            .join(RolePermissionORM, RolePermissionORM.permission_id == PermissionORM.id)
            .join(UserRoleORM, UserRoleORM.role_id == RolePermissionORM.role_id)
            .where(UserRoleORM.user_id == str(user_id))
        )
        return set(result.scalars().all())

    async def permission_codes_for_roles(
        self,
        role_names: Sequence[str],
        tenant_id: str,
    ) -> set[str]:
        """给定角色名在指定租户内的权限集合（`docs/02` §30 第 2 / 4 步）。

        Args:
            role_names: 角色名（全局角色或项目内角色名）。
            tenant_id: 角色所属租户。

        Returns:
            权限码集合；未知角色名不产生任何权限（默认拒绝，`docs/02` §28）。
        """
        if not role_names:
            return set()
        result = await self.session.execute(
            select(PermissionORM.code)
            .join(RolePermissionORM, RolePermissionORM.permission_id == PermissionORM.id)
            .join(RoleORM, RoleORM.id == RolePermissionORM.role_id)
            .where(
                RoleORM.tenant_id == str(tenant_id),
                RoleORM.name.in_(list(role_names)),
            )
        )
        return set(result.scalars().all())


class ProjectMembershipRepository(BaseRepository[ProjectORM]):
    """项目归属与项目内角色读取（`docs/02` §20 / §23 / §30 第 4 步）。

    覆盖 `projects` / `project_members`。只读：跨租户判定由
    `ProjectAccessService` 负责（失败 → `STRUCTAI-4200`，`docs/02` §23 / §48）。
    """

    model = ProjectORM

    async def project_tenant_id(self, project_id: str) -> str | None:
        """项目所属租户（`docs/02` §23）。

        Args:
            project_id: 项目标识。

        Returns:
            项目行上的 `tenant_id`；项目不存在返回 `None`
            （调用方把「不存在」与「别的租户」合并成同一个 `STRUCTAI-4200`）。
        """
        result = await self.session.execute(
            select(ProjectORM.tenant_id).where(ProjectORM.id == str(project_id))
        )
        return result.scalar_one_or_none()

    async def project_role_for_user(self, project_id: str, user_id: str) -> str | None:
        """用户在该项目内的角色名（`docs/02` §23；`project_members.role`）。

        Args:
            project_id: 项目标识。
            user_id: 用户标识。

        Returns:
            项目内角色名；不是成员返回 `None`。
        """
        result = await self.session.execute(
            select(ProjectMemberORM.role).where(
                ProjectMemberORM.project_id == str(project_id),
                ProjectMemberORM.user_id == str(user_id),
            )
        )
        return result.scalar_one_or_none()


def _to_record(session: SessionORM) -> SessionRecord:
    """ORM 行 → Domain 记录（**不带** `token_hash`，见 `SessionRecord` 的说明）。"""
    return SessionRecord(
        id=str(session.id),
        user_id=str(session.user_id),
        tenant_id=str(session.tenant_id),
        expires_at=_as_utc(session.expires_at),
        revoked=bool(session.revoked),
        last_seen_at=_as_utc_optional(session.last_seen_at),
    )


def build_security_stores(session: AsyncSession) -> SecurityStores:
    """为一个会话装配安全存储四件套（`docs/02` §33 / §123）。

    Args:
        session: 已存在的 `AsyncSession`（通常由 P06 `UnitOfWork` 提供）。

    Returns:
        `SecurityStores`：四个存储共享**同一个**会话，因此共享同一个事务
        （与 `build_repositories` 同口径）。

    ⚠️ 本函数**不**开事务、**不**提交、**不**建立连接（`docs/02` §16；`docs/07` §14.4）。
    """
    users: UserLookup = UserRepository(session)
    return SecurityStores(
        users=users,
        sessions=SessionRepository(session),
        roles=RoleRepository(session),
        projects=ProjectMembershipRepository(session),
    )
