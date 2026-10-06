"""Application · Security · Effective Permission（`docs/02` §24–§33；`docs/07` §8.2）。

权威来源
--------
- `docs/02` §29（`sec` §29）—— `EffectivePermissionService.get_permissions(
  identity, resource_type=None, resource_id=None) -> set[str]`；计算来源 =
  `Global Roles + Tenant Membership + Project Membership + Resource ACL − Explicit Deny`。
- `docs/02` §30（`sec` §30）—— 算法 8 步：取用户角色 → 取角色权限 → 取 Tenant 级权限 →
  取 Project 级权限 → 取 Resource ACL → 加入 ALLOW → 删除 DENY → 返回最终集合。
- `docs/02` §31（`sec` §31）—— `require(identity, permission, resource_type, resource_id)`：
  不足即 `PermissionDeniedError(f"Permission denied: {permission}")`。
- `docs/02` §28（`sec` §28）—— 判定优先级**冻结**：
  `Explicit DENY > Explicit ALLOW > Inherited ALLOW > Default DENY`，即 **Deny wins**。
- `docs/02` §32 / §33（`sec` §32 / §33）—— AI Agent 有效权限
  = 用户有效权限 **∩** Agent 权限；Agent 只能减少权限，不能增加。
- `docs/02` §22 / §23（`sec` §22 / §23）—— Tenant Access / Project Access：
  `identity.tenant_id` 是唯一权威来源，客户端提供的 `tenant_id` **不参与**授权判断；
  项目必须属于当前租户。
- `docs/02` §48（`sec` §48）—— 跨租户拒绝**不得**泄露存在性（统一
  `Tenant access denied`）。
- `docs/07` §8.2 —— 权限链与「四级取最严格」；`docs/07` §14.3 —— 禁止 AI Agent 提权、
  禁止依赖 UI 过滤做租户隔离。

本批的两条落地裁决（只补实现手段，不改语义）
--------------------------------------------
1. **ACL 的判定逻辑在本批落地，ACL 的持久化不在本批。**
   `docs/02` §25 定义了一张 `resource_acls` 表，但 `docs/07` §4.3 冻结的是
   **24 张表**（P04 已逐一核对），本批次又明确「不得改表」（`docs/07` §14.3：
   禁止启动时静默 `ALTER TABLE`）。故：
   - 本模块完整实现 §24–§28 的**判定逻辑**（ALLOW / DENY、四种主体、
     `Deny wins`、四级取最严格）；
   - ACL 的**来源**经 `app.domain.protocols.ResourceACLLookup` 注入
     （结构化契约，`docs/07` §2.2：Application 不依赖 Infrastructure）；
   - 未注入任何来源时用 `NullResourceACLLookup`（返回空集）——
     即「没有 ACL 记录」= 默认拒绝之外不产生任何额外影响（§28 的 Default DENY）。
2. **`ACLScope` 的语义**：`docs/02` §28 只冻结优先级，`docs/07` §8.2 才列出四级来源。
   `GLOBAL` / `TENANT` / `USER` / `RESOURCE` 四级**取最严格**：同一权限在四级中
   任一级出现 `DENY`，最终即 `DENY`（`_stricter_effect`）。
   ⚠️ 四级是**判定层级**，不是跨租户通道：ACL 查询一律带 `tenant_id`，
   `GLOBAL` 只表示「本租户内的全局策略」，绝不跨租户（`docs/02` §48）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：不引用 ORM / Web 框架 / MCP SDK / httpx，
不依赖 `app.infrastructure`，也不出现任何厂商专属内容。
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Final

from app.application.security.context import IdentityContext
from app.application.security.rbac import RoleService
from app.domain.enums import ACLPrincipalType, ACLScope, PermissionEffect, RoleName
from app.domain.errors import PermissionDeniedError, TenantAccessDeniedError
from app.domain.protocols import ProjectMembershipLookup, ResourceACLEntry, ResourceACLLookup
from app.domain.value_objects import ResourceRef

__all__ = [
    "ACL_DECISION_PRIORITY",
    "ACL_SCOPES_STRICTEST_FIRST",
    "TENANT_ACCESS_DENIED_MESSAGE",
    "AgentPermissionService",
    "EffectivePermissionService",
    "InMemoryResourceACLLookup",
    "NullResourceACLLookup",
    "ProjectAccessService",
    "TenantAccessService",
    "acl_decision_for",
    "entry_applies_to",
    "entry_matches_resource",
]

ACL_DECISION_PRIORITY: Final[tuple[PermissionEffect, ...]] = (
    PermissionEffect.DENY,
    PermissionEffect.ALLOW,
)
"""ACL 判定优先级（`docs/02` §28：`Explicit DENY > Explicit ALLOW > Inherited ALLOW >
Default DENY`）—— 取最严格时按本顺序比较，**DENY 永远压过 ALLOW**。"""

ACL_SCOPES_STRICTEST_FIRST: Final[tuple[ACLScope, ...]] = (
    ACLScope.RESOURCE,
    ACLScope.USER,
    ACLScope.TENANT,
    ACLScope.GLOBAL,
)
"""四级作用域（`docs/07` §8.2）—— 仅用于**诊断 / 报告**的顺序展示。

⚠️ 判定本身**不**依赖「谁更具体」：按 `docs/02` §28，任何一级的 `DENY` 都直接生效，
不存在「更具体的 ALLOW 覆盖上层 DENY」的规则。
"""

TENANT_ACCESS_DENIED_MESSAGE: Final[str] = "Tenant access denied"
"""跨租户拒绝的统一消息（`docs/02` §22 / §48；**不**区分「不存在」与「属于别的租户」）。"""


def entry_applies_to(entry: ResourceACLEntry, identity: IdentityContext) -> bool:
    """该 ACL 条目是否作用于这个身份（`docs/02` §27 的三种主体）。

    Args:
        entry: ACL 条目。
        identity: 服务端身份上下文（`user_id` / `tenant_id` / `roles` 全部来自服务端）。

    Returns:
        命中主体为 `True`：

        - `USER` —— `principal_id == str(identity.user_id)`
        - `ROLE` —— `principal_id ∈ identity.roles`
        - `TENANT` —— `principal_id == str(identity.tenant_id)`
    """
    if entry.principal_type is ACLPrincipalType.USER:
        return entry.principal_id == str(identity.user_id)
    if entry.principal_type is ACLPrincipalType.ROLE:
        return entry.principal_id in identity.roles
    return entry.principal_id == str(identity.tenant_id)


def entry_matches_resource(
    entry: ResourceACLEntry,
    resource_type: str | None,
    resource_id: str | None,
) -> bool:
    """该 ACL 条目是否覆盖本次请求的资源（`docs/02` §24 的资源种类）。

    规则：

    - 请求**未**指定资源（`resource_type` 与 `resource_id` 均为 `None`）时，
      只有**不带资源限定**的条目命中（即全局 / 租户 / 用户级策略）；
    - 请求指定了资源时，`RESOURCE` 作用域的条目必须 `resource_type` +
      `resource_id` **同时**相等才命中；其余作用域的条目按其自身是否带资源限定判断。

    Args:
        entry: ACL 条目。
        resource_type: 本次请求的资源类型；`None` 表示不限定。
        resource_id: 本次请求的资源标识；`None` 表示不限定。

    Returns:
        命中为 `True`。
    """
    if resource_type is None and resource_id is None:
        return entry.resource_type is None and entry.resource_id is None
    if entry.scope is ACLScope.RESOURCE:
        return entry.resource_type == resource_type and entry.resource_id == resource_id
    return entry.resource_type is None and entry.resource_id is None


def acl_decision_for(
    entries: Sequence[ResourceACLEntry],
    identity: IdentityContext,
    resource_type: str | None,
    resource_id: str | None,
) -> dict[str, PermissionEffect]:
    """把 ACL 条目归约成「权限码 → 最终判定」（`docs/02` §28 / §30）。

    四级取最严格：同一权限出现任意一条 `DENY`，最终即 `DENY`
    （`_stricter_effect`），与条目的出现顺序、作用域层级无关。

    Args:
        entries: 本次查询命中的 ACL 条目。
        identity: 服务端身份上下文。
        resource_type: 本次请求的资源类型（可为 `None`）。
        resource_id: 本次请求的资源标识（可为 `None`）。

    Returns:
        `permission -> PermissionEffect`；只含至少有一条命中条目的权限。
    """
    decisions: dict[str, PermissionEffect] = {}
    for entry in entries:
        if not entry_applies_to(entry, identity):
            continue
        if not entry_matches_resource(entry, resource_type, resource_id):
            continue
        decisions[entry.permission] = _stricter_effect(
            decisions.get(entry.permission),
            entry.effect,
        )
    return decisions


def _stricter_effect(
    current: PermissionEffect | None,
    candidate: PermissionEffect,
) -> PermissionEffect:
    """取两者中更严格的判定（`docs/02` §28：Deny wins）。

    Args:
        current: 已累计的判定；`None` 表示尚无判定。
        candidate: 新读到的判定。

    Returns:
        若任一方为 `DENY` → `DENY`；否则 `ALLOW`。
    """
    if current is None:
        return candidate
    if PermissionEffect.DENY in (current, candidate):
        return PermissionEffect.DENY
    return PermissionEffect.ALLOW


class NullResourceACLLookup:
    """空 ACL 来源（`docs/02` §24：没有 ACL 记录时的默认实现）。

    Core Alpha 的 `resource_acls` 表不在 `docs/07` §4.3 的 24 张表内
    （见模块裁决 1），因此「未配置 ACL 来源」是**正常**状态而不是错误：
    此时有效权限 = 角色权限 ∪ 项目成员权限（`docs/02` §29 的前三项），
    `Default DENY`（`docs/02` §28）由 `EffectivePermissionService.require` 兜底。
    """

    async def entries_for(
        self,
        *,
        tenant_id: str,
        resource_type: str | None,
        resource_id: str | None,
    ) -> Sequence[ResourceACLEntry]:
        """始终返回空集（不产生任何 ALLOW / DENY）。

        Args:
            tenant_id: 租户标识（本实现不区分）。
            resource_type: 资源类型（本实现不区分）。
            resource_id: 资源标识（本实现不区分）。

        Returns:
            空元组。
        """
        return ()


class InMemoryResourceACLLookup:
    """进程内 ACL 来源（`docs/02` §24–§28 判定逻辑的可用实现）。

    用途：验收测试与单实例部署。它**只**做租户内的条目过滤，
    不做任何判定 —— 判定统一在 `acl_decision_for` 里（`docs/02` §28 只允许一处实现）。

    ⚠️ 构造时必须显式给出 `tenant_id`：本实现只服务于一个租户的条目集合，
    从根本上排除跨租户串号（`docs/02` §48 / `docs/07` §14.3）。
    """

    def __init__(self, tenant_id: str, entries: Sequence[ResourceACLEntry] = ()) -> None:
        """绑定租户与条目。

        Args:
            tenant_id: 本实例服务的租户（必填，见类 docstring）。
            entries: 该租户的 ACL 条目。
        """
        self._tenant_id = str(tenant_id)
        self._entries: tuple[ResourceACLEntry, ...] = tuple(entries)

    async def entries_for(
        self,
        *,
        tenant_id: str,
        resource_type: str | None,
        resource_id: str | None,
    ) -> Sequence[ResourceACLEntry]:
        """返回**本租户**内与资源匹配的条目（`docs/02` §24）。

        Args:
            tenant_id: 调用方声明的租户；与本实例租户不符时返回空集
                （跨租户**不**产生任何判定，`docs/02` §48）。
            resource_type: 资源类型（可为 `None`）。
            resource_id: 资源标识（可为 `None`）。

        Returns:
            命中的条目（保持构造时的顺序）。
        """
        if str(tenant_id) != self._tenant_id:
            return ()
        return tuple(
            entry
            for entry in self._entries
            if entry_matches_resource(entry, resource_type, resource_id)
        )


class TenantAccessService:
    """租户访问判定（`docs/02` §22）。

    `docs/02` §22 的原文实现是 `ensure_access(identity, tenant_id)`：不一致即
    `TenantAccessDeniedError`。本类照抄，并补一个 `ensure_resource_access`
    用于「资源自带 `tenant_id`」的常见场景（Model / Document / SoftwareInstance）。

    🔴 唯一权威来源是 `identity.tenant_id`（服务端生成）；客户端 context 里的
    `tenant_id` **不参与**判断（`docs/02` §22；`docs/07` §14.3）。
    """

    def ensure_access(self, identity: IdentityContext, tenant_id: str) -> None:
        """要求身份属于指定租户（`docs/02` §22）。

        Args:
            identity: 服务端身份上下文。
            tenant_id: 被访问对象所属的租户。

        Raises:
            TenantAccessDeniedError: `STRUCTAI-4200`，跨租户（`docs/07` §11）。
                消息固定为 `Tenant access denied`，**不**泄露对象是否存在
                （`docs/02` §48）。
        """
        if str(identity.tenant_id) != str(tenant_id):
            raise TenantAccessDeniedError(TENANT_ACCESS_DENIED_MESSAGE)

    def ensure_resource_access(
        self, identity: IdentityContext, resource_tenant_id: str | None
    ) -> None:
        """要求资源所属租户与身份一致（`docs/02` §22 的推广写法）。

        Args:
            identity: 服务端身份上下文。
            resource_tenant_id: 资源行上的 `tenant_id`；`None` 表示资源不存在。

        Raises:
            TenantAccessDeniedError: `STRUCTAI-4200`。**「不存在」与「属于别的租户」
                返回同一个错误**（`docs/02` §48：不得泄露存在性）。
        """
        if resource_tenant_id is None or str(identity.tenant_id) != str(resource_tenant_id):
            raise TenantAccessDeniedError(TENANT_ACCESS_DENIED_MESSAGE)


class ProjectAccessService:
    """项目访问判定（`docs/02` §23）。

    项目必须属于当前租户：`Identity.tenant_id ↓ Project.tenant_id`。
    不满足即 `TenantAccessDeniedError`（`STRUCTAI-4200`），且不区分
    「项目不存在」与「项目属于别的租户」（`docs/02` §48）。
    """

    def __init__(self, lookup: ProjectMembershipLookup) -> None:
        """绑定项目归属来源（`docs/02` §23）。

        Args:
            lookup: 满足 `app.domain.protocols.ProjectMembershipLookup` 的来源。
        """
        self._lookup = lookup

    async def ensure_access(self, identity: IdentityContext, project_id: str) -> None:
        """要求项目属于身份的租户（`docs/02` §23）。

        Args:
            identity: 服务端身份上下文。
            project_id: 项目标识。

        Raises:
            TenantAccessDeniedError: `STRUCTAI-4200`（`docs/07` §14.3：跨租户唯一拦截点）。
        """
        project_tenant_id = await self._lookup.project_tenant_id(str(project_id))
        if project_tenant_id is None or str(project_tenant_id) != str(identity.tenant_id):
            raise TenantAccessDeniedError(TENANT_ACCESS_DENIED_MESSAGE)

    async def project_role(self, identity: IdentityContext, project_id: str) -> str | None:
        """项目内角色（`docs/02` §23 / §30 第 4 步）。

        Args:
            identity: 服务端身份上下文（必须已通过 `ensure_access`）。
            project_id: 项目标识。

        Returns:
            项目内角色名；不是成员时为 `None`（不是成员 ≠ 报错：
            `docs/02` §49「同一租户内跨项目默认 DENY」，由权限集合的自然结果体现）。
        """
        return await self._lookup.project_role_for_user(str(project_id), str(identity.user_id))


class AgentPermissionService:
    """AI Agent 权限求交（`docs/02` §33；`docs/07` §5.7 / §14.3）。

    `Effective User Permission ∩ AI Agent Permission = Effective AI Permission`：
    Agent **只能减少**权限，不能增加（`docs/02` §33）。
    """

    async def intersect(
        self,
        user_permissions: Collection[str],
        agent_permissions: Collection[str],
    ) -> set[str]:
        """求交集（`docs/02` §33 原文实现）。

        Args:
            user_permissions: 用户的有效权限。
            agent_permissions: Agent Scope 声明的权限。

        Returns:
            两者交集；`agent_permissions` 为空集时结果必为空集
            （**不得**退化为用户权限 —— 那就是提权）。
        """
        return set(user_permissions) & set(agent_permissions)


class EffectivePermissionService:
    """有效权限判定（`docs/02` §29 / §30 / §31；`docs/07` §8.2）。

    计算链（顺序照抄 `docs/02` §30）：

        Global Roles → Tenant Roles（角色权限）
        → Project Roles（项目成员角色权限）
        → Resource ACL（ALLOW / DENY，四级取最严格）
        → AI Agent 求交（仅在 Agent 身份 / 显式提供 Agent 权限时）
        → 最终权限集合

    ⚠️ 本服务**只读**：不写任何表、不产生任何日志，也不 `commit`
    （`docs/07` §14.4）。这也使 `docs/07` §9 的第 11 步（Effective Permission）
    可以安全地排在写操作之前。
    """

    def __init__(
        self,
        role_service: RoleService,
        *,
        project_memberships: ProjectMembershipLookup | None = None,
        resource_acl: ResourceACLLookup | None = None,
        agent_permissions: Collection[str] | None = None,
    ) -> None:
        """装配有效权限链的各环节（`docs/02` §29 / §30）。

        Args:
            role_service: 角色 → 权限（`docs/02` §30 第 1–2 步）。
            project_memberships: 项目归属与项目内角色（§30 第 4 步）；
                `None` 表示本服务不支持项目级权限（此时传 `project_id` 会失败）。
            resource_acl: ACL 来源（§30 第 5 步）；`None` 时用 `NullResourceACLLookup`。
            agent_permissions: 默认的 Agent 权限集合（§32 / §33）；按次调用可用
                `get_permissions(..., agent_permissions=...)` 覆盖。
        """
        self._roles = role_service
        self._memberships = project_memberships
        self._project_access = (
            ProjectAccessService(project_memberships) if project_memberships is not None else None
        )
        self._acl = resource_acl if resource_acl is not None else NullResourceACLLookup()
        self._agent_permissions = (
            frozenset(agent_permissions) if agent_permissions is not None else None
        )
        self._agents = AgentPermissionService()

    async def get_permissions(
        self,
        identity: IdentityContext,
        resource_type: str | None = None,
        resource_id: str | None = None,
        *,
        project_id: str | None = None,
        agent_permissions: Collection[str] | None = None,
    ) -> set[str]:
        """计算有效权限集合（`docs/02` §29 / §30）。

        Args:
            identity: 服务端身份上下文（`user_id` / `tenant_id` / `roles`）。
            resource_type: 本次访问的资源类型（`docs/02` §8；可为 `None`）。
            resource_id: 本次访问的资源标识（可为 `None`）。
            project_id: 本次访问所属项目（可选）；给出即纳入项目成员权限，
                并**先**做租户归属校验（`docs/02` §23）。
            agent_permissions: 本次调用的 Agent 权限（可选）；覆盖构造期默认值。

        Returns:
            有效权限码集合（`docs/02` §30 第 8 步）。

        Raises:
            TenantAccessDeniedError: `STRUCTAI-4200`，`project_id` 不属于身份的租户
                （`docs/02` §23 / §48；**先**于任何权限判定）。
            ValueError: 传入了 `project_id` 但本服务未装配项目归属来源（装配错误，
                不是数据错误）。
        """
        permissions = await self._roles.get_user_permissions(str(identity.user_id))

        if project_id is not None:
            if self._project_access is None:
                raise ValueError(
                    "project scoped permissions require a ProjectMembershipLookup "
                    "(EffectivePermissionService was built without one)"
                )
            await self._project_access.ensure_access(identity, project_id)
            project_role = await self._project_access.project_role(identity, project_id)
            if project_role is not None:
                permissions |= await self._roles.get_role_permissions(
                    [project_role],
                    str(identity.tenant_id),
                )

        entries = await self._acl.entries_for(
            tenant_id=str(identity.tenant_id),
            resource_type=resource_type,
            resource_id=resource_id,
        )
        permissions = _apply_acl(permissions, entries, identity, resource_type, resource_id)

        scope = agent_permissions if agent_permissions is not None else self._agent_permissions
        if scope is not None or RoleName.AI_AGENT.value in identity.roles:
            permissions = await self._agents.intersect(permissions, scope if scope else ())

        return permissions

    async def resolve(
        self, identity: IdentityContext, resource: ResourceRef | None = None
    ) -> set[str]:
        """`docs/07` §8.2 的签名：`resolve(identity, resource) -> set[str]`。

        Args:
            identity: 服务端身份上下文。
            resource: 资源引用（`docs/02` §8）；`None` 时只按全局 / 租户 / 用户级判定。

        Returns:
            有效权限码集合。
        """
        return await self.get_permissions(
            identity,
            resource.resource_type if resource is not None else None,
            resource.resource_id if resource is not None else None,
        )

    async def require(
        self,
        identity: IdentityContext,
        permission: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        *,
        project_id: str | None = None,
        agent_permissions: Collection[str] | None = None,
    ) -> None:
        """要求具备某权限，否则拒绝（`docs/02` §31 原文）。

        Args:
            identity: 服务端身份上下文。
            permission: 权限码（`app.domain.enums.PermissionCode` 的取值）。
            resource_type: 资源类型（可为 `None`）。
            resource_id: 资源标识（可为 `None`）。
            project_id: 所属项目（可选）。
            agent_permissions: 本次调用的 Agent 权限（可选）。

        Raises:
            PermissionDeniedError: `STRUCTAI-4000`，有效权限不足（`docs/07` §11）。
            TenantAccessDeniedError: `STRUCTAI-4200`，跨租户（`docs/02` §23）。
        """
        permissions = await self.get_permissions(
            identity,
            resource_type,
            resource_id,
            project_id=project_id,
            agent_permissions=agent_permissions,
        )
        if permission not in permissions:
            raise PermissionDeniedError(
                f"Permission denied: {permission}",
                details={"permission": permission, "stage": "authorization"},
            )


def _apply_acl(
    permissions: set[str],
    entries: Sequence[ResourceACLEntry],
    identity: IdentityContext,
    resource_type: str | None,
    resource_id: str | None,
) -> set[str]:
    """把 ACL 判定施加到权限集合上（`docs/02` §30 第 6–7 步）。

    Args:
        permissions: 角色 / 项目权限的并集（原地不改，返回新集合）。
        entries: 本次命中的 ACL 条目。
        identity: 服务端身份上下文。
        resource_type: 资源类型（可为 `None`）。
        resource_id: 资源标识（可为 `None`）。

    Returns:
        施加 ALLOW（加入）与 DENY（删除）之后的权限集合。
        ⚠️ 先算判定再统一施加：若边遍历边施加，一条 `ALLOW` 可能把更早的 `DENY`
        又加回来，违反 `docs/02` §28 的「Deny wins」。
    """
    decisions = acl_decision_for(entries, identity, resource_type, resource_id)
    result = set(permissions)
    for permission, effect in decisions.items():
        if effect is PermissionEffect.DENY:
            result.discard(permission)
        else:
            result.add(permission)
    return result
