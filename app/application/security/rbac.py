"""Application · Security · RBAC（`docs/02` §23 / §19 / §30；`docs/07` §5.7 / §8.2）。

权威来源
--------
- `docs/02` §23（`source7` §23 RBAC Service）—— 文件 `application/security/rbac.py`；
  `RBACService.has_permission(identity, permission, resource=None) -> bool`，逐字照抄。
- `docs/02` §19 / §20（`sec` §19 / §20）—— 会话需要「用户 → 角色名」装载
  （`role_service.get_user_roles(user_id)`）。
- `docs/02` §30（`sec` §30 Effective Permission Algorithm）—— 第 1 / 2 步
  「获取用户角色」「获取角色权限」由本模块的 `RoleService` 承担；第 4 步
  「获取 Project 级权限」复用同一份 `roles` / `role_permissions` 映射
  （项目内角色名同样是 `roles.name`，`docs/02` §20 / §23）。
- `docs/07` §5.7 / `docs/02` §72 —— 4 个角色的权限映射（`system_admin` = ALL、
  `engineer` = 9、`viewer` = 3、`ai_agent` = 动态），落库口径见 P07 Seed。
- `docs/07` §14.3 —— **禁止 AI Agent 提权**。

职责边界（与 `permission.py` 的分工）
-------------------------------------
- 本模块 = **角色层**（RBAC）：用户有哪些角色、角色有哪些权限。
- `permission.py` = **有效权限**（`docs/02` §29；`docs/07` §8.2）：角色权限 ∪
  项目成员权限 − 显式拒绝，再与 Agent 权限求交。
  这样切分使 `RBACService.has_permission`（§23）成为有效权限判定的一层视图，
  而**不是**第二套权限逻辑（`docs/02` §61 / §62：安全判定只允许有一处入口）。

`RBACService` 与 `EffectivePermissionService` 之间的依赖方向
------------------------------------------------------------
`permission.py` 需要 `RoleService`（角色 → 权限），因此**不能**反过来 import
`EffectivePermissionService`，否则形成循环导入。本模块据此把「有效权限来源」
声明为结构化契约 `PermissionResolver`（只有一个 `get_permissions`），
`EffectivePermissionService` 结构上即满足它，由装配期注入
（与 P09 `SchemaLookup` 收窄 `SchemaRegistry` 是同一做法）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：不引用 ORM / Web 框架 / MCP SDK / httpx，
不依赖 `app.infrastructure`，也不出现任何厂商专属内容。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.application.security.context import IdentityContext
from app.domain.enums import RoleName
from app.domain.errors import PermissionDeniedError
from app.domain.protocols import RoleLookup
from app.domain.value_objects import ResourceRef

__all__ = [
    "DEFAULT_ROLE_NAMES",
    "PermissionResolver",
    "RBACService",
    "RoleService",
]

DEFAULT_ROLE_NAMES: tuple[str, ...] = tuple(role.value for role in RoleName)
"""默认角色名 4 条（`docs/07` §5.7；`docs/02` §72）—— 由 `RoleName` 派生，不另写字面量。"""


class PermissionResolver(Protocol):
    """有效权限来源契约（`docs/02` §29 的 `get_permissions`）。

    只声明 RBAC 需要的那一个方法；`EffectivePermissionService` 结构上满足它
    （见模块 docstring 的依赖方向说明）。
    """

    async def get_permissions(
        self,
        identity: IdentityContext,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> set[str]: ...


class RoleService:
    """角色与权限的读取服务（`docs/02` §19 / §23 / §30）。

    只做三件事：取用户角色名、取角色权限集合、取用户（角色层）权限集合。
    **不**做任何授权判定（判定归 `RBACService` / `EffectivePermissionService`），
    也**不**做任何写入 —— 角色 / 权限的写入属管理面（`docs/02` §59 的
    `ROLE_CHANGED` / `PERMISSION_CHANGED` 审计项），不在本批。
    """

    def __init__(self, lookup: RoleLookup) -> None:
        """绑定角色 / 权限来源（`docs/02` §23）。

        Args:
            lookup: 满足 `app.domain.protocols.RoleLookup` 的来源
                （装配期由容器 / 调用方注入；Core Alpha 实现见
                `app.infrastructure.database.repositories.security`）。
        """
        self._lookup = lookup

    async def get_user_roles(self, user_id: str) -> list[str]:
        """用户持有的角色名（`docs/02` §19：`role_service.get_user_roles(user_id)`）。

        Args:
            user_id: 用户标识（**服务端**身份里的值，绝不由客户端提供）。

        Returns:
            角色名列表，按角色名升序、去重；无角色时为空列表。
        """
        names = await self._lookup.role_names_for_user(user_id)
        return _dedupe(names)

    async def get_role_permissions(self, role_names: Sequence[str], tenant_id: str) -> set[str]:
        """角色名集合 → 权限码集合（`docs/02` §30 第 2 步）。

        Args:
            role_names: 角色名（全局角色或项目内角色名）。
            tenant_id: 角色所属租户（`roles` 是 Tenant-owned，`docs/07` §4.3 #3）。

        Returns:
            这些角色在**该租户内**授予的权限码集合；未知角色名不产生任何权限
            （默认拒绝，`docs/02` §28）。
        """
        if not role_names:
            return set()
        return set(await self._lookup.permission_codes_for_roles(_dedupe(role_names), tenant_id))

    async def get_user_permissions(self, user_id: str) -> set[str]:
        """用户角色权限的并集（`docs/02` §30 第 1–2 步）。

        Args:
            user_id: 用户标识。

        Returns:
            该用户全部角色授予的权限码集合（不含项目级 / ACL 调整）。
        """
        return set(await self._lookup.permission_codes_for_user(user_id))

    async def has_role(self, identity: IdentityContext, role_name: str) -> bool:
        """身份是否持有某角色（`docs/02` §32：判定是否为 AI Agent 身份）。

        Args:
            identity: 服务端身份上下文。
            role_name: 角色名（典型用法：`RoleName.AI_AGENT.value`）。

        Returns:
            持有为 `True`。
        """
        return role_name in identity.roles


class RBACService:
    """RBAC 判定（`docs/02` §23；`docs/07` §8.2）。

    `docs/02` §23 的签名是 `has_permission(identity, permission, resource=None)`。
    本实现把它落成**有效权限**的一层视图：判定由注入的 `PermissionResolver`
    完成（Core Alpha 即 `EffectivePermissionService`），因此：
    「有效权限不足 → `STRUCTAI-4000`」这条口径只有一处实现（`docs/02` §61 / §62）。
    """

    def __init__(self, resolver: PermissionResolver) -> None:
        """绑定有效权限来源（`docs/02` §23 / §29）。

        Args:
            resolver: 满足 `PermissionResolver` 的来源（装配期注入）。
        """
        self._resolver = resolver

    async def has_permission(
        self,
        identity: IdentityContext,
        permission: str,
        resource: ResourceRef | None = None,
    ) -> bool:
        """是否具备某权限（`docs/02` §23）。

        Args:
            identity: 服务端身份上下文。
            permission: 权限码（`app.domain.enums.PermissionCode` 的取值）。
            resource: 可选资源引用（`docs/02` §8）；为 `None` 时只按全局 / 租户 /
                用户级判定。

        Returns:
            具备为 `True`，否则 `False`（**不**抛异常）。
        """
        permissions = await self._resolver.get_permissions(
            identity,
            resource.resource_type if resource is not None else None,
            resource.resource_id if resource is not None else None,
        )
        return permission in permissions

    async def require_permission(
        self,
        identity: IdentityContext,
        permission: str,
        resource: ResourceRef | None = None,
    ) -> None:
        """要求具备某权限，否则拒绝（`docs/02` §31 `require` 的 RBAC 视图）。

        Args:
            identity: 服务端身份上下文。
            permission: 权限码。
            resource: 可选资源引用。

        Raises:
            PermissionDeniedError: `STRUCTAI-4000`，有效权限不足（`docs/07` §11）。
        """
        if not await self.has_permission(identity, permission, resource):
            raise PermissionDeniedError(
                f"Permission denied: {permission}",
                details={"permission": permission, "stage": "authorization"},
            )


def _dedupe(values: Sequence[str]) -> list[str]:
    """去重并保持稳定顺序（角色名重复不影响权限并集，但影响输出确定性）。"""
    return list(dict.fromkeys(values))
