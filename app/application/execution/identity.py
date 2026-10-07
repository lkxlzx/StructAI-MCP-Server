"""Application · Execution · 传输层鉴权端口（`docs/03` §10–§12；`docs/07` §8.1）。

权威来源
--------
- `docs/03` §10（IdentityContext）—— Transport **不**直接相信客户端传入的
  `user_id` / `tenant_id` / `roles` / `permissions`，必须经
  `Transport → Authentication → IdentityContext`。
- `docs/03` §11（STDIO Identity）—— 本地 STDIO 可配置 *local trusted identity*
  （`STRUCTAI_LOCAL_USER_ID` / `STRUCTAI_LOCAL_TENANT_ID`），但仍必须构造**标准**
  `IdentityContext`，**不得**因为「本地连接」就绕过 RBAC / Tenant Isolation / Audit。
- `docs/03` §12（HTTP Authentication）—— Streamable HTTP 必须经
  `HTTP Request → Authentication Middleware → IdentityContext → MCP Session`，
  第一阶段用 **Bearer Token**。
- `docs/07` §8.1 —— 身份**必须由服务器生成**；客户端不可提供
  `user_id` / `tenant_id` / `roles` / `permissions` / `session_id`。
- `docs/07` §9 第 2–4 步 —— `Authenticate` → `Build Server IdentityContext` →
  `Build ExecutionContext`；本模块是第 2 步在**传输层**的落点（P40 / P41）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **端口放在 Application 层**：传输层（`app/interfaces/mcp/transport/`）必须调用
   「认证 → 身份 + 有效权限」，而这一能力由**会话级**安全服务提供
   （`app/application/security`，P10–P13）。若端口声明在接口层，容器就要反向
   import 接口层，违反 `docs/07` §2.2 的依赖方向；故端口与其产物
   `MCPIdentity` 落在 Application 层，接口层只**消费**它。
2. **`MCPIdentity` 只承载服务端已经确认的事实**：身份（`IdentityContext`）与
   有效权限快照（`docs/02` §29 / §42）。它是 `MCPContextFactory.create()` 的
   入参形状，**不**含任何客户端输入 —— 传输层因此**没有**第二条路径能影响身份。
3. **认证失败沿用 `STRUCTAI-4000`**（`docs/07` §11 的既有 20 码；`docs/02` §17
   「不泄露用户是否存在」）：本批**不**新增码。会话无效 / Token 无效 / 已撤销 /
   已过期一律同一错误形状（由 P10–P13 的 `SessionService.validate_token` 保证）。
4. **有效权限取**服务端**计算结果**：`docs/02` §32 / §51 —— 未提供 Agent 权限时
   按**空集**（不得提权）。本端口**不**做任何权限求交，只搬运
   `SecurityContext.permissions`。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain` / `app.application.security`（同层）：
**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖
`app.infrastructure` / `app.interfaces` / `app.observability`，
也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.application.security.context import IdentityContext, SecurityContext

__all__ = [
    "MCPAuthenticator",
    "MCPIdentity",
    "identity_from_security",
    "local_identity",
]


@dataclass(frozen=True, slots=True)
class MCPIdentity:
    """一次传输层鉴权的产物：**服务端**身份 ＋ 有效权限（见模块裁决 1 / 2）。

    Attributes:
        identity: 服务端构造的身份上下文（`docs/02` §26；`docs/03` §10）。
        permissions: 有效权限快照（`docs/02` §29 / §42）；缺省空集（见模块裁决 4）。
        agent_id: 调用方是 AI Agent 时的 Agent 标识（`docs/02` §42）。
    """

    identity: IdentityContext
    permissions: frozenset[str] = frozenset()
    agent_id: str | None = None

    def __post_init__(self) -> None:
        """把 `permissions` 规整为 `frozenset[str]`（不改取值）。"""
        if not isinstance(self.permissions, frozenset):
            object.__setattr__(
                self,
                "permissions",
                frozenset(str(item) for item in self.permissions),
            )

    @property
    def session_id(self) -> str | None:
        """认证会话标识（`docs/02` §19）；无会话场景为 `None`。"""
        return None if self.identity.session_id is None else str(self.identity.session_id)


@runtime_checkable
class MCPAuthenticator(Protocol):
    """传输层的认证端口（`docs/03` §12；见模块裁决 1）。

    ⚠️ 实现方是**会话级**安全服务的装配产物（`ExecutionServiceFactory.authenticator`）：
    每次调用都会开一个自己的数据库会话，因此**可以**在请求级并发使用。
    """

    async def authenticate(self, token: str) -> MCPIdentity:
        """把客户端持有的凭据换成服务端身份（`docs/02` §20；`docs/03` §12）。

        Args:
            token: 客户端提交的**明文**凭据（Bearer Token）。绝不记录 / 回显。

        Returns:
            `MCPIdentity`（身份 ＋ 有效权限）。

        Raises:
            PermissionDeniedError: `STRUCTAI-4000` —— 凭据无效 / 会话失效。
        """
        ...


def local_identity(
    identity: IdentityContext,
    *,
    permissions: Iterable[str] = (),
) -> MCPIdentity:
    """构造本地可信身份（`docs/03` §11 的 *local trusted identity*）。

    ⚠️ 这**不是**绕过鉴权：调用方必须自己先确认本地身份（`docs/02` §43 的种子管理员），
    且 `IdentityContext.authentication_method` 必须如实标注 `LOCAL`
    （`app.application.security.context.AUTHENTICATION_METHOD_LOCAL`），
    审计链因此能区分「本地可信」与「已认证会话」。

    Args:
        identity: 服务端确认的本地身份（`docs/02` §26）。
        permissions: 有效权限快照；缺省空集（见模块裁决 4）。

    Returns:
        `MCPIdentity`（`authentication_method` 由调用方如实填写）。
    """
    return MCPIdentity(identity=identity, permissions=frozenset(str(item) for item in permissions))


def identity_from_security(security: SecurityContext) -> MCPIdentity:
    """由 `SecurityContext` 构造传输层身份（`docs/02` §42）。

    `docs/02` §40 / §41 要求执行链**只**从 `SecurityContext` 这一个入口拿身份与权限，
    故这是 HTTP 鉴权的推荐映射（行为与 `MCPIdentity(...)` 完全一致）。
    """
    return MCPIdentity(
        identity=security.identity,
        permissions=frozenset(str(item) for item in security.permissions),
        agent_id=security.agent_id,
    )
