"""Application · Security · SessionService（`docs/02` §10 / §19 / §20 / §21；`docs/07` §8.3）。

权威来源
--------
- `docs/02` §19（`sec` §19）—— `SessionService.create_session(user_id, tenant_id)`：
  生成明文 token → 只把 `token_service.hash(raw_token)` 落库 → 装载角色 →
  构造 `IdentityContext` → 返回 `AuthenticationResult`；`lifetime_seconds` 默认 86400。
- `docs/02` §20（`sec` §20）—— `validate_token(token) -> IdentityContext` 的校验顺序
  **冻结**为：`hash → 按 hash 反查 → 存在 → 未 revoked → 未过期 → 装载角色`；
  任一不满足 → `AuthenticationError("Invalid session")`，**不得**构造 `IdentityContext`。
- `docs/02` §21（`sec` §21）—— `revoke(session_id)` / `revoke_all(user_id)`；
  用途：改口令 / 安全事件 / 全端登出 / 管理员禁用。
- `docs/02` §11（`sec` §11）—— Session 生命周期能力：`create` / `validate` / `touch` /
  `revoke` / `revoke_all` / `cleanup_expired`。
- `docs/02` §13（`sec` §13）—— 库中只存 hash：明文 token 只在 `AuthenticationResult`
  里返回一次，绝不落库 / 落日志（`docs/07` §14.3）。
- `docs/02` §53（`sec` §53 Session Expiration Test）—— 过期会话必须被拒，且
  **不得**产生 `IdentityContext`。
- `docs/07` §8.3 —— Session 有 `expires_at`、可撤销、绑定 User + Tenant；
  失效条件 = 过期 / 撤销 / 用户锁定 → 立即失效。

失败口径裁决（`docs/02` §24–§26；门槛 ②）
------------------------------------------
`docs/02` §56 为安全域**新列**了 4 个码（`STRUCTAI-` 4xxx 段：Authentication Failed /
Session Invalid / Session Expired / Session Revoked），但它们
「不新增 `STRUCTAI-xxxx` 码（20 码契约不扩）」。故本批裁决：

- 会话类失败（不存在 / 已撤销 / 已过期 / 用户被锁）**一律**以既有的
  **`STRUCTAI-4000` `PermissionDeniedError`** 对外（`docs/07` §11：4xxx = 安全域）；
- **错误形状完全一致**：同一 `message`（`Invalid session`）+ 同一 `details` 键集合
  （`{"stage": "session", "reason": <机器可读原因>}`）—— 只有 `reason` 的取值不同，
  它属服务端诊断信息，便于区分过期 / 撤销而不改变对外形状；
- 客户端**无法**据此判断会话是否存在（`docs/02` §48：不得返回
  `Tenant B exists` / `Project B exists` 之类的存在性提示）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：不引用 ORM / Web 框架 / MCP SDK / httpx，
不依赖 `app.infrastructure`（持久化经 `SessionStore` / `UserLookup` 结构化契约注入），
也不出现任何厂商专属内容。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final, Protocol
from uuid import UUID

from app.application.security.context import (
    AUTHENTICATION_METHOD_PASSWORD,
    AUTHENTICATION_METHOD_TOKEN,
    AuthenticationResult,
    IdentityContext,
)
from app.application.security.token import TokenService
from app.domain.errors import PermissionDeniedError
from app.domain.protocols import SessionStore, UserLookup

__all__ = [
    "DEFAULT_SESSION_LIFETIME_SECONDS",
    "INVALID_SESSION_MESSAGE",
    "SESSION_FAILURE_REASONS",
    "SessionService",
    "UserRoleLookup",
]

DEFAULT_SESSION_LIFETIME_SECONDS: Final[int] = 86400
"""会话默认有效期（`docs/02` §19 的 `lifetime_seconds: int = 86400`）。"""

INVALID_SESSION_MESSAGE: Final[str] = "Invalid session"
"""会话失败的**统一**消息（`docs/02` §20 原文；不区分存在 / 撤销 / 过期）。"""

SESSION_FAILURE_REASONS: Final[tuple[str, ...]] = (
    "unknown_session",
    "session_revoked",
    "session_expired",
    "user_inactive",
)
"""`details["reason"]` 的全部取值（服务端诊断用；**不改变**对外错误形状）。"""


class UserRoleLookup(Protocol):
    """会话装载角色所需的最小契约（`docs/02` §19 / §20）。

    只声明 `get_user_roles` —— `SessionService` 不需要角色 → 权限的展开
    （那是 `RBACService` / `EffectivePermissionService` 的职责），
    `app.application.security.rbac.RoleService` 结构上即满足本契约。
    """

    async def get_user_roles(self, user_id: str) -> list[str]: ...


class SessionService:
    """会话的创建 / 校验 / 刷新 / 撤销（`docs/02` §19–§21）。

    🔴 安全硬约束（`docs/07` §8.3 / §14.3）：

    - 明文 token **只**在 `create_session` 的返回值里出现一次，库中只写
      `token_service.hash(raw_token)`（`docs/02` §13）；
    - 本类**不产生任何日志**：既不记 token、也不记 token hash
      （`docs/02` §58 的安全日志白名单里两者都不在；只允许 `fingerprint`）。
    """

    def __init__(
        self,
        session_store: SessionStore,
        token_service: TokenService,
        role_lookup: UserRoleLookup,
        user_lookup: UserLookup,
        lifetime_seconds: int = DEFAULT_SESSION_LIFETIME_SECONDS,
    ) -> None:
        """绑定会话存储、token 服务、角色来源与用户来源（`docs/02` §19）。

        Args:
            session_store: 会话持久化（`app.domain.protocols.SessionStore`）。
            token_service: token 生成 / 哈希（`docs/02` §12）。
            role_lookup: 用户 → 角色名（`docs/02` §19）。
            user_lookup: 用户状态读取（校验「用户锁定 → 会话立即失效」，`docs/07` §8.3）。
            lifetime_seconds: 会话有效期秒数；由 `Settings.session_expire_seconds`
                注入（`docs/07` §3.1 的冻结配置项），默认值与 `docs/02` §19 一致。
        """
        self._sessions = session_store
        self._tokens = token_service
        self._roles = role_lookup
        self._users = user_lookup
        self.lifetime_seconds = lifetime_seconds

    async def create_session(self, user_id: str, tenant_id: str) -> AuthenticationResult:
        """创建会话并返回一次性明文 token（`docs/02` §19）。

        Args:
            user_id: 服务端确认的用户标识。
            tenant_id: 服务端确认的租户标识（会话绑定 User + Tenant，`docs/07` §8.3）。

        Returns:
            `AuthenticationResult`：`identity` 已装载角色、`access_token` 为明文
            token（只返回一次，绝不落库）。

        ⚠️ 本方法**不** `commit`：事务边界归 `UnitOfWork`（`docs/07` §14.4）。
        """
        raw_token = self._tokens.generate()
        token_hash = self._tokens.hash(raw_token)

        now = _utcnow()
        session = await self._sessions.create(
            user_id=user_id,
            tenant_id=tenant_id,
            token_hash=token_hash,
            created_at=now,
            expires_at=now + timedelta(seconds=self.lifetime_seconds),
        )

        roles = await self._roles.get_user_roles(user_id)
        identity = IdentityContext(
            user_id=_as_uuid(session.user_id),
            tenant_id=_as_uuid(session.tenant_id),
            session_id=_as_uuid(session.id),
            roles=tuple(roles),
            authentication_method=AUTHENTICATION_METHOD_PASSWORD,
        )

        return AuthenticationResult(
            identity=identity,
            session_id=session.id,
            access_token=raw_token,
        )

    async def validate_token(self, token: str) -> IdentityContext:
        """校验明文 token 并构造身份（`docs/02` §20；顺序冻结）。

        Args:
            token: 客户端持有的明文 token。

        Returns:
            校验通过的服务端身份上下文（`authentication_method = TOKEN`）。

        Raises:
            PermissionDeniedError: `STRUCTAI-4000`（见模块的失败口径裁决）。
                四种失败原因在 `details["reason"]` 中区分，对外形状完全一致；
                **不**构造任何 `IdentityContext`（`docs/02` §53）。
        """
        token_hash = self._tokens.hash(token)
        session = await self._sessions.get_by_token_hash(token_hash)
        if session is None:
            raise _invalid_session("unknown_session")

        if session.revoked:
            raise _invalid_session("session_revoked")

        if session.expires_at <= _utcnow():
            raise _invalid_session("session_expired")

        user = await self._users.get_by_id_for_tenant(session.user_id, session.tenant_id)
        if user is None or not user.is_active or user.locked:
            raise _invalid_session("user_inactive")

        roles = await self._roles.get_user_roles(session.user_id)
        return IdentityContext(
            user_id=_as_uuid(session.user_id),
            tenant_id=_as_uuid(session.tenant_id),
            session_id=_as_uuid(session.id),
            roles=tuple(roles),
            authentication_method=AUTHENTICATION_METHOD_TOKEN,
        )

    async def refresh(self, session_id: str) -> None:
        """记录会话最近活动时间（`docs/02` §11 的 `touch` / §22 的 `refresh`）。

        Args:
            session_id: 会话标识。

        ⚠️ 本方法**不延长**有效期：`expires_at` 在创建时即固定（`docs/07` §8.3），
        续期属显式策略，不在本批。
        """
        await self._sessions.touch(session_id, _utcnow())

    async def revoke(self, session_id: str) -> bool:
        """注销单个会话（`docs/02` §21）。

        Args:
            session_id: 会话标识。

        Returns:
            确实撤销了行为 `True`；会话不存在或已撤销为 `False`。

        ⚠️ 撤销**立即**生效：下一次 `validate_token` 即被拒（`docs/02` §11：
        `ACTIVE → REVOKED`）。
        """
        return await self._sessions.revoke(session_id)

    async def revoke_all(self, user_id: str) -> int:
        """注销某用户的全部会话（`docs/02` §21）。

        Args:
            user_id: 用户标识。

        Returns:
            本次被撤销的会话数（用于审计 `SESSION_REVOKED`，`docs/02` §59）。
        """
        return await self._sessions.revoke_all_for_user(user_id)

    async def cleanup_expired(self, now: datetime | None = None) -> int:
        """把已过期会话置为撤销（`docs/02` §11 的 `cleanup_expired`）。

        Args:
            now: 判定基准时间；默认取当前 UTC 时间（便于测试注入）。

        Returns:
            本次被清理的会话数。

        ⚠️ 采取「标记撤销」而非删除：会话行是审计对象（`docs/02` §59），
        物理清理属数据保留策略（`docs/02` §40 / §45），不在本批。
        """
        return await self._sessions.cleanup_expired(now if now is not None else _utcnow())


def _utcnow() -> datetime:
    """当前 UTC 时间（**带时区**）。

    ⚠️ 不在本层引入任何数据库 / 框架的时间工具：Application 不得依赖
    `app.infrastructure`（`docs/07` §14.1），故此处直接用标准库 `datetime.UTC`。
    """
    return datetime.now(UTC)


def _as_uuid(value: str) -> UUID:
    """把持久层的字符串标识转为 `UUID`（`docs/02` §26 的字段类型是 `UUID`）。

    ⚠️ 主键在 P04 落地为 `String(36)` 的 UUID 字符串；这里做一次显式转换，
    使 `IdentityContext` 的类型与 `docs/02` §26 一致（非法值会在此**立即**失败，
    而不是等到下游拼 SQL 时才暴露）。
    """
    return UUID(str(value))


def _invalid_session(reason: str) -> PermissionDeniedError:
    """构造**形状一致**的会话失败异常（见模块的失败口径裁决）。

    Args:
        reason: `SESSION_FAILURE_REASONS` 中的一个取值。

    Returns:
        `PermissionDeniedError`（`STRUCTAI-4000`），消息与 `details` 键集合固定。
    """
    if reason not in SESSION_FAILURE_REASONS:  # pragma: no cover - 编程错误，不是数据错误
        raise ValueError(f"unknown session failure reason: {reason}")
    return PermissionDeniedError(
        INVALID_SESSION_MESSAGE,
        details={"stage": "session", "reason": reason},
    )
