"""Application · Security · IdentityContext / SecurityContext（`docs/02` §26 / §42）。

权威来源
--------
- `docs/02` §26（`blue` §26）—— 文件 `app/application/security/context.py`；
  `IdentityContext(user_id, tenant_id, session_id, roles, authentication_method)`
  逐字照抄（含 `authentication_method` 的默认值 `"unknown"`）。
- `docs/02` §14（`sec` §14）—— 同一结构的第二份原文（字段与顺序一致）。
- `docs/02` §42（`sec` §42）—— `SecurityContext(identity, permissions)`，并给出
  扩展形态 `agent_id` / `authenticated`；本文件采用扩展形态（§42 原文即列为
  「可进一步扩展」的正式形态）。
- `docs/02` §15（`sec` §15）—— `AuthenticationResult(identity, session_id, access_token)`。
- `docs/07` §8.1 —— 身份**必须由服务器生成**：客户端提供的 `user_id` /
  `tenant_id` / `roles` / `permissions` / `session_id` 一律忽略（`docs/07` §14.3）。
- `docs/07` §9 —— 执行流水线第 2–4 步（Authenticate → IdentityContext →
  ExecutionContext）与第 11 步（Effective Permission）的**顺序冻结**。

规范之上的落地裁决（只补实现手段，不改字段名 / 类型 / 语义）
------------------------------------------------------------
1. **`authentication_method` 的取值口径**：`docs/02` §26 的默认值是字面量
   `"unknown"`（照抄保留）；而 §19 / §20 的示例写 `"password"` / `"session"`。
   本项目唯一冻结的认证方式枚举是 `app.domain.enums.AuthenticationMethod`
   （`PASSWORD` / `LOCAL` / `TOKEN`，`docs/02` §5；`docs/07` §4.1），其中
   **没有** `"password"` / `"session"` 这两个小写值。本模块据此裁决：
   认证成功后的取值一律取自该枚举 —— 口令登录 → `AUTHENTICATION_METHOD_PASSWORD`
   （`PASSWORD`）、会话 / Token 校验 → `AUTHENTICATION_METHOD_TOKEN`（`TOKEN`）、
   STDIO 本地可信身份 → `AUTHENTICATION_METHOD_LOCAL`（`LOCAL`，`docs/07` §8.1）。
   不新造第 4 个取值。
2. **`roles` 规整为 `tuple`**：`docs/02` §26 的类型是 `tuple[str, ...]`。为了让
   调用方（Repository 返回 `list[str]`）不必先手工转换，`__post_init__` 会把传入的
   任何可迭代序列规整为 `tuple`；值本身不做任何增删。
3. **`access_token` 不参与 `repr`**：`AuthenticationResult.access_token` 是**明文**
   token（`docs/02` §13 / §15），只允许出现在「返回给客户端的那一次」里。
   字段以 `repr=False` 声明，避免它被 `%r` / 日志 / 异常信息带出去
   （`docs/07` §14.3：绝不记录 secret；`docs/02` §58 的安全日志白名单里也没有它）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：不引用 SQLAlchemy / FastAPI / MCP SDK / httpx，
不依赖 `app.infrastructure`，也不出现任何厂商专属内容。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final
from uuid import UUID

from app.domain.enums import AuthenticationMethod

__all__ = [
    "AUTHENTICATION_METHOD_LOCAL",
    "AUTHENTICATION_METHOD_PASSWORD",
    "AUTHENTICATION_METHOD_TOKEN",
    "UNKNOWN_AUTHENTICATION_METHOD",
    "AuthenticationResult",
    "IdentityContext",
    "SecurityContext",
]

UNKNOWN_AUTHENTICATION_METHOD: Final[str] = "unknown"
"""未认证 / 未标注的认证方式（`docs/02` §26 的默认值，照抄规范字面量）。"""

AUTHENTICATION_METHOD_PASSWORD: Final[str] = AuthenticationMethod.PASSWORD.value
"""口令认证（`docs/02` §19；取值取自 `AuthenticationMethod`，见模块裁决 1）。"""

AUTHENTICATION_METHOD_TOKEN: Final[str] = AuthenticationMethod.TOKEN.value
"""会话 / Token 认证（`docs/02` §20；`docs/07` §8.1：HTTP 必须鉴权）。"""

AUTHENTICATION_METHOD_LOCAL: Final[str] = AuthenticationMethod.LOCAL.value
"""本地可信身份（`docs/07` §8.1：STDIO 可用 local trusted identity）。"""


@dataclass(frozen=True, slots=True)
class IdentityContext:
    """服务端构造的身份上下文（`docs/02` §26 / §14；`docs/07` §8.1）。

    🔴 **绝不由客户端提供**：`user_id` / `tenant_id` / `roles` 只能由
    `AuthenticationService` / `SessionService` 在认证之后填充；客户端发来的同名字段
    一律忽略（`docs/07` §8.1 / §14.3）。本类型本身**不可变**（`frozen=True`），
    下游服务无法就地提权。

    Attributes:
        user_id: 服务端确认的用户标识。
        tenant_id: 服务端确认的租户标识（第一层隔离，`docs/02` §22）。
        session_id: 会话标识；`LOCAL` 身份等无会话场景为 `None`。
        roles: 服务端装载的角色名（**不是**权限，更不是客户端输入，`docs/02` §26）。
        authentication_method: 认证方式，取值见 `AUTHENTICATION_METHOD_*`。
    """

    user_id: UUID
    tenant_id: UUID
    session_id: UUID | None = None
    roles: tuple[str, ...] = ()
    authentication_method: str = UNKNOWN_AUTHENTICATION_METHOD

    def __post_init__(self) -> None:
        """把 `roles` 规整为 `tuple`（见模块裁决 2）；不做任何增删。"""
        if not isinstance(self.roles, tuple):
            object.__setattr__(self, "roles", tuple(self.roles))


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    """一次成功认证的产物（`docs/02` §15 / §19）。

    Attributes:
        identity: 服务端构造的身份上下文（`docs/02` §26）。
        session_id: 新建会话的标识。
        access_token: **明文** token —— 只返回给客户端一次（`docs/02` §13：
            「Raw Token → Client，Hash(Token) → DB」）。字段 `repr=False`，
            绝不进日志 / 审计 / 任何持久化结构（`docs/07` §14.3）。
    """

    identity: IdentityContext
    session_id: str
    access_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class SecurityContext:
    """认证 + 有效权限的合并视图（`docs/02` §42）。

    `docs/02` §40 / §41 要求执行管线**只**从这一个入口拿身份与权限：
    `Authenticate → IdentityContext → Tenant Isolation → Resolve Resource →
    Effective Permission → Confirmation`（顺序冻结）。

    Attributes:
        identity: 服务端身份（`docs/02` §26）。
        permissions: **有效权限**快照（`docs/02` §29；`docs/07` §8.2 的四级链结果）。
        agent_id: 调用方是 AI Agent 时的 Agent 标识（`docs/02` §42）。
        authenticated: 是否已完成认证（`docs/02` §42）。
    """

    identity: IdentityContext
    permissions: frozenset[str]
    agent_id: str | None = None
    authenticated: bool = True
