"""Application · Security（`docs/07` §3.3；`docs/02` §6–§9 / §24–§33）。

本包是安全能力的 Application 层落点：

| 文件 | 内容 | 批次 |
| --- | --- | --- |
| `password.py` | `PasswordService`：Argon2id 口令哈希（`docs/02` §7） | **P07 ✅** |
| `context.py` | `IdentityContext` / `AuthenticationResult` / `SecurityContext` | **P10–P13 ✅** |
| `token.py` | `TokenService`：token 生成 + sha256 哈希（`docs/02` §12 / §13） | **P10–P13 ✅** |
| `session.py` | `SessionService`：会话创建 / 校验 / 刷新 / 撤销 | **P10–P13 ✅** |
| `rbac.py` | `RoleService` + `RBACService`（`docs/02` §23 / §30） | **P10–P13 ✅** |
| `permission.py` | `EffectivePermissionService` / Tenant / Project Access | **P10–P13 ✅** |
| `authentication.py` | `AuthenticationService` + `SecurityGuard` | **P10–P13 ✅** |
（规范对应：`context.py` → `docs/02` §26 / §42；`token.py` → §12 / §13；
`session.py` → §10 / §19–§21；`rbac.py` → §23 / §30；
`permission.py` → §22–§33；`authentication.py` → §16–§18 / §40–§42。）

装配形状（`docs/02` §33 / §123）
--------------------------------
本包的服务**全部**是**会话级**对象：它们持有 `SessionStore` / `UserLookup` /
`RoleLookup` / `ProjectMembershipLookup`，而这些入口都绑定在一个 `AsyncSession` 上
（与 P05 的 Repository、P06 的 UnitOfWork 同理）。因此：

- `app.container`（进程级）**不**新增字段 —— `docs/02` §33 的冻结形状只放
  `settings` / `engine` / `session_factory` / `operation_registry`（P09 门槛 ⑤ 已固化）；
- 会话级装配由两步完成：
  `app.infrastructure.database.repositories.build_security_stores(session)`（Infrastructure）
  → `build_security_services(stores, password_service=...)`（本包，只依赖 Domain 契约）。
  事务边界仍归 `UnitOfWork`（`docs/07` §14.4）。

安全红线（`docs/07` §14.3）：本包**绝不**记录 secret（password / API key /
token / private key）；口令只以 `password_hash` 形式离开本包，明文 token 只在
`AuthenticationResult` 里返回一次。
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from app.application.security.authentication import (
    MAX_FAILED_LOGIN_ATTEMPTS,
    SECURITY_CHAIN_ORDER,
    AuthenticationService,
    SecurityGuard,
)
from app.application.security.context import (
    AUTHENTICATION_METHOD_LOCAL,
    AUTHENTICATION_METHOD_PASSWORD,
    AUTHENTICATION_METHOD_TOKEN,
    UNKNOWN_AUTHENTICATION_METHOD,
    AuthenticationResult,
    IdentityContext,
    SecurityContext,
)
from app.application.security.password import PasswordService
from app.application.security.permission import (
    AgentPermissionService,
    EffectivePermissionService,
    InMemoryResourceACLLookup,
    NullResourceACLLookup,
    ProjectAccessService,
    TenantAccessService,
)
from app.application.security.rbac import RBACService, RoleService
from app.application.security.session import (
    DEFAULT_SESSION_LIFETIME_SECONDS,
    SessionService,
)
from app.application.security.token import TokenService
from app.domain.protocols import ResourceACLLookup, SecurityStores

__all__ = [
    "AUTHENTICATION_METHOD_LOCAL",
    "AUTHENTICATION_METHOD_PASSWORD",
    "AUTHENTICATION_METHOD_TOKEN",
    "DEFAULT_SESSION_LIFETIME_SECONDS",
    "MAX_FAILED_LOGIN_ATTEMPTS",
    "SECURITY_CHAIN_ORDER",
    "UNKNOWN_AUTHENTICATION_METHOD",
    "AgentPermissionService",
    "AuthenticationResult",
    "AuthenticationService",
    "EffectivePermissionService",
    "IdentityContext",
    "InMemoryResourceACLLookup",
    "NullResourceACLLookup",
    "PasswordService",
    "ProjectAccessService",
    "RBACService",
    "RoleService",
    "SecurityContext",
    "SecurityGuard",
    "SecurityServices",
    "SessionService",
    "TenantAccessService",
    "TokenService",
    "build_security_services",
]


@dataclass(frozen=True, slots=True)
class SecurityServices:
    """一次会话上的全部安全服务（会话级，`docs/02` §33）。

    ⚠️ 生命周期与 `AsyncSession` 绑定：**不得**放进进程级容器或全局单例
    （`docs/02` §33 / §123；`docs/07` §3.3）。

    Attributes:
        roles: 角色 → 权限读取（`docs/02` §23 / §30）。
        rbac: RBAC 判定视图（`docs/02` §23）。
        tenant_access: 租户隔离（`docs/02` §22；失败 → `STRUCTAI-4200`）。
        project_access: 项目归属（`docs/02` §23；失败 → `STRUCTAI-4200`）。
        agents: AI Agent 权限求交（`docs/02` §33；不得提权）。
        sessions: 会话服务（`docs/02` §19–§21）。
        authentication: 口令认证（`docs/02` §16–§18）。
        permissions: 有效权限（`docs/02` §29–§31）。
        guard: 安全唯一入口（`docs/02` §40 / §41 / §61 / §62）。
    """

    roles: RoleService
    rbac: RBACService
    tenant_access: TenantAccessService
    project_access: ProjectAccessService
    agents: AgentPermissionService
    sessions: SessionService
    authentication: AuthenticationService
    permissions: EffectivePermissionService
    guard: SecurityGuard


def build_security_services(
    stores: SecurityStores,
    *,
    password_service: PasswordService,
    session_lifetime_seconds: int = DEFAULT_SESSION_LIFETIME_SECONDS,
    resource_acl: ResourceACLLookup | None = None,
    agent_permissions: Collection[str] | None = None,
    max_failed_attempts: int = MAX_FAILED_LOGIN_ATTEMPTS,
) -> SecurityServices:
    """把安全服务装配到一组会话级存储上（`docs/02` §33 / §123）。

    Args:
        stores: 会话级持久化入口（由
            `app.infrastructure.database.repositories.build_security_stores(session)` 装配；
            本函数只看到 Domain 契约，不依赖 Infrastructure —— `docs/07` §14.1）。
        password_service: Argon2id 口令服务（P07 已落地，**复用不得重写**）。
        session_lifetime_seconds: 会话有效期；调用方传
            `settings.session_expire_seconds`（`docs/07` §3.1）。
        resource_acl: ACL 来源；`None` 时用 `NullResourceACLLookup`
            （`resource_acls` 表不在 24 张表内，见 `permission.py` 裁决）。
        agent_permissions: 默认 Agent 权限集合（`docs/02` §32 / §33）。
        max_failed_attempts: 连续失败锁定阈值（`docs/02` §18）。

    Returns:
        `SecurityServices`：共享同一个会话的九个服务实例。

    ⚠️ 本函数**不**开事务、**不**提交、**不**建立连接（与 `build_repositories` 同口径）。
    """
    role_service = RoleService(stores.roles)
    permission_service = EffectivePermissionService(
        role_service,
        project_memberships=stores.projects,
        resource_acl=resource_acl,
        agent_permissions=agent_permissions,
    )
    session_service = SessionService(
        stores.sessions,
        TokenService(),
        role_service,
        stores.users,
        session_lifetime_seconds,
    )
    authentication_service = AuthenticationService(
        stores.users,
        password_service,
        session_service,
        max_failed_attempts=max_failed_attempts,
    )

    return SecurityServices(
        roles=role_service,
        rbac=RBACService(permission_service),
        tenant_access=TenantAccessService(),
        project_access=ProjectAccessService(stores.projects),
        agents=AgentPermissionService(),
        sessions=session_service,
        authentication=authentication_service,
        permissions=permission_service,
        guard=SecurityGuard(authentication_service, session_service, permission_service),
    )
