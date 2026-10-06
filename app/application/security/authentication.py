"""Application · Security · AuthenticationService（`docs/02` §16–§18；`docs/07` §8.3）。

权威来源
--------
- `docs/02` §16（`sec` §16）—— `AuthenticationService(user_repository, password_service,
  session_service)` + `authenticate(username, password) -> AuthenticationResult`：
  取用户 → 不存在即失败 → 非活跃即失败 → `password_service.verify(...)` → 失败即失败 →
  `session_service.create_session(user_id, tenant_id)`，逐条照抄。
- `docs/02` §20（`source7` §20 Authentication Service）—— 流程：
  `Find User → Check Locked → Verify Password → Update Login State → Create Session →
  Build IdentityContext → Audit Login`。
- `docs/02` §17（`sec` §17）—— **不泄露用户是否存在**：「用户不存在」与「口令错误」
  必须返回同一个错误；禁止出现 `User does not exist` / `Wrong password` 这类可枚举的差异。
- `docs/02` §18（`sec` §18）—— 登录失败计数与短暂锁定、指数退避，
  **不要永久锁死账号**（`locked` / `failed_login_count` 两列已在 P04 落表）。
- `docs/02` §47（`sec` §47）—— Authentication E2E：得到 token → hash → 查 session →
  构造 `IdentityContext` → 取角色 → 取 Effective Permission。
- `docs/07` §8.3 —— 口令哈希 = Argon2id（P07 的 `PasswordService`，**不得**重写）；
  登录失败 → 计数 + 账号锁定；**不泄露用户是否存在**。
- `docs/07` §9 —— 执行流水线第 2 步 `Authenticate` 必须先于任何写操作。

失败口径裁决（门槛 ②）
----------------------
`docs/02` §56 新列的安全域码（`STRUCTAI-` 4xxx 段：Authentication Failed / Session
Invalid / Session Expired / Session Revoked）**不在** `docs/07` §11 的

- 认证失败一律以既有的 **`STRUCTAI-4000` `PermissionDeniedError`** 对外；
- **同一错误形状**：同一 `message`（`Invalid username or password`，`docs/02` §17 原文）
  + 同一 `details` 键集合（`{"stage": "authentication", "reason": "invalid_credentials"}`）。
  「用户不存在」「口令错误」「账号停用 / 锁定」三种情形的**响应完全一致**；
- **同一耗时口径**：每条失败路径都**恰好执行一次** Argon2 校验 —— 用户不存在时用
  一个随机口令的哑哈希（`_dummy_password_hash`）代替真实哈希，
  使「查不到用户」不会因跳过哈希而变快（`docs/02` §17 的反枚举要求）。

规范之上的落地说明（只补实现手段）
----------------------------------
- **不另造 `LoginAttemptService`**：`docs/02` §18 列出的 `record_failure` /
  `record_success` / `is_locked` 三个动作，在本实现中由
  `UserLookup`（机制：读写 `users.failed_login_count` / `users.locked`）
  + 本服务（策略：`MAX_FAILED_LOGIN_ATTEMPTS`）共同承担。理由：`docs/02` §61 / §62
  要求安全判定只有**一个**入口，再包一层纯转发类只会制造第二个入口。
  `is_locked` 语义落在 `UserRecord.locked` 上（由 `UserLookup` 读出）。
- **口令只在 `PasswordService` 内校验**：本模块**不** import `argon2` / `hashlib`，
  也不自行比较任何哈希（`docs/02` §7 / §8）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`（+ 同包的 `password` / `session` / `context` / `rbac`）：
不引用 ORM / Web 框架 / MCP SDK / httpx，不依赖 `app.infrastructure`，
也不出现任何厂商专属内容。
"""

from __future__ import annotations

import logging
import secrets
from typing import Final, Protocol

from app.application.security.context import (
    AuthenticationResult,
    IdentityContext,
    SecurityContext,
)
from app.application.security.password import PasswordService
from app.application.security.session import SessionService
from app.domain.errors import PermissionDeniedError
from app.domain.protocols import UserLookup

__all__ = [
    "INVALID_CREDENTIALS_MESSAGE",
    "MAX_FAILED_LOGIN_ATTEMPTS",
    "SECURITY_CHAIN_ORDER",
    "AuthenticationService",
    "PermissionChecker",
    "SecurityGuard",
]

MAX_FAILED_LOGIN_ATTEMPTS: Final[int] = 5
"""连续失败达到该次数即锁定账号（`docs/02` §18：连续失败 → 短暂锁定 → 指数退避）。

⚠️ 锁定是**可解除**的（`AuthenticationService.unlock`），
`docs/02` §18 明写「不要永久锁死账号」。
"""

INVALID_CREDENTIALS_MESSAGE: Final[str] = "Invalid username or password"
"""认证失败的**统一**消息（`docs/02` §16 / §17 原文；不得区分不存在 / 口令错误）。"""

SECURITY_CHAIN_ORDER: Final[tuple[str, ...]] = (
    "Authentication",
    "Session",
    "RBAC",
    "Effective Permission",
)
"""门槛 ① 的四步安全链（顺序冻结）。

对应 `docs/07` §9 执行流水线的第 2–4 步（Authenticate → Build Server IdentityContext →
Build ExecutionContext）与第 11 步（Effective Permission）：**必须先于任何写操作**
（`docs/07` §12 P10–P13 的门槛原文）。`SecurityGuard` 即这条链的唯一入口。
"""

logger = logging.getLogger("structai.security")


class PermissionChecker(Protocol):
    """`SecurityGuard` 需要的有效权限契约（`docs/02` §29 / §31 / §40）。

    同时声明 `get_permissions` 与 `require`；`EffectivePermissionService` 结构上满足
    （它的两个方法都接受额外的可选参数，见 `app/application/security/permission.py`）。
    """

    async def get_permissions(
        self,
        identity: IdentityContext,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> set[str]: ...

    async def require(
        self,
        identity: IdentityContext,
        permission: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> None: ...


class AuthenticationService:
    """口令认证（`docs/02` §16 / §17 / §18；`docs/07` §8.3）。

    🔴 安全硬约束：

    - 口令**只**经 `PasswordService`（Argon2id）校验（`docs/02` §7；`docs/07` §8.3）；
    - 失败时**不泄露用户是否存在**（同一错误形状 + 同一耗时口径，见模块裁决）；
    - 本类**不记录任何 secret**：日志里只有用户名、失败计数与锁定事件
      （`docs/02` §58 允许 `login_success` / `login_failure`），
      绝不出现口令 / 哈希 / token（`docs/07` §14.3）。
    """

    def __init__(
        self,
        user_lookup: UserLookup,
        password_service: PasswordService,
        session_service: SessionService,
        *,
        max_failed_attempts: int = MAX_FAILED_LOGIN_ATTEMPTS,
    ) -> None:
        """绑定用户来源、口令服务与会话服务（`docs/02` §16）。

        Args:
            user_lookup: 用户读取与登录状态写入（`app.domain.protocols.UserLookup`）。
            password_service: Argon2id 口令服务（P07 已落地，**复用不得重写**）。
            session_service: 会话服务（认证成功即建会话，`docs/02` §16 / §19）。
            max_failed_attempts: 连续失败达到该次数即锁定（`docs/02` §18）。
        """
        self._users = user_lookup
        self._passwords = password_service
        self._sessions = session_service
        self.max_failed_attempts = max_failed_attempts
        self._dummy_password_hash: str | None = None

    async def authenticate(self, username: str, password: str) -> AuthenticationResult:
        """口令认证并创建会话（`docs/02` §16）。

        Args:
            username: 用户名（`users.username` 全局唯一，`docs/07` §4.3 #2）。
            password: 明文口令（**只**传给 `PasswordService`，不缓存、不记录）。

        Returns:
            `AuthenticationResult`：服务端身份 + 会话 + 一次性明文 token。

        Raises:
            PermissionDeniedError: `STRUCTAI-4000`（§56 的 4xxx 段新码不在 20 码契约内，
                见模块裁决）。三种失败情形形状一致。

        ⚠️ 本方法**不** `commit`：事务边界归 `UnitOfWork`（`docs/07` §14.4）。
        """
        user = await self._users.get_by_username(username)

        # 统一耗时口径：用户不存在时也用哑哈希跑一次 Argon2 校验（docs/02 §17）。
        candidate_hash = user.password_hash if user is not None else self._dummy_hash()
        valid = self._passwords.verify(candidate_hash, password)

        if user is None:
            logger.warning("login failure (unknown user)")
            raise _invalid_credentials()

        if not valid:
            count = await self._users.record_login_failure(
                user.id,
                lock_at=self.max_failed_attempts,
            )
            logger.warning("login failure (invalid credentials) failed_count=%d", count)
            raise _invalid_credentials()

        if not user.is_active or user.locked:
            # ⚠️ 不累加失败计数：对已停用 / 已锁定账号继续计数会把锁定无限延长
            #    （docs/02 §18：不要永久锁死账号）。
            logger.warning("login failure (account unavailable)")
            raise _invalid_credentials()

        await self._users.record_login_success(user.id)
        result = await self._sessions.create_session(user.id, user.tenant_id)
        logger.info("login success")
        return result

    async def unlock(self, user_id: str) -> None:
        """解除账号锁定（`docs/02` §18：不要永久锁死账号）。

        Args:
            user_id: 用户标识。

        ⚠️ 这是管理面动作（`docs/02` §59 的 `LOGIN_FAILURE` 审计族）；
        本批只提供机制，调用方（未来的管理 API）负责鉴权与审计。
        """
        await self._users.set_locked(user_id, locked=False)
        logger.info("account unlocked")

    def _dummy_hash(self) -> str:
        """与真实哈希同参数的哑哈希（`docs/02` §17 的反枚举手段）。

        首次使用时生成一次并缓存：它由 `PasswordService` 对**随机**口令生成，
        因此 `verify(哑哈希, 任意口令)` 必然为 `False`，但耗时与真实校验一致。

        Returns:
            `$argon2id$…` 形式的哈希串（随机口令，非任何用户的哈希）。

        ⚠️ 随机口令与哑哈希都不进日志（`docs/07` §14.3）。
        """
        if self._dummy_password_hash is None:
            self._dummy_password_hash = self._passwords.hash(secrets.token_urlsafe(32))
        return self._dummy_password_hash


class SecurityGuard:
    """安全入口（`docs/02` §40 / §41 / §60 / §61 / §62）。

    `docs/02` §41 冻结的顺序：

        Authenticate → IdentityContext → Tenant Isolation → Resolve Resource
        → Effective Permission → Confirmation

    本类承载其中的 **Authenticate → IdentityContext → Effective Permission**；
    Tenant Isolation / Resolve Resource 由 P14–P18 的 `ResourceResolver` 承担
    （它必须最先拦截跨租户，`docs/07` §9 第 7 步），Confirmation 归 P14–P18 的
    `confirmation.py`（`docs/07` §8.4）—— 因此本批**不**提供 `confirm()`。

    🔴 `docs/02` §61 / §62：MCP / HTTP / CLI / AI / UI **不得**各自实现一套权限逻辑，
    一律经本入口（`ExecutionService` 在 P36 会持有它）。
    """

    def __init__(
        self,
        authentication: AuthenticationService,
        sessions: SessionService,
        permissions: PermissionChecker,
    ) -> None:
        """绑定认证、会话与有效权限三件套（`docs/02` §40）。

        Args:
            authentication: 口令认证（`docs/02` §16）。
            sessions: 会话校验 / 注销（`docs/02` §19–§21）。
            permissions: 有效权限判定（`docs/02` §29）。
        """
        self._authentication = authentication
        self._sessions = sessions
        self._permissions = permissions

    @property
    def chain_order(self) -> tuple[str, ...]:
        """本入口实现的四步链顺序（门槛 ① 的机器可读口径）。"""
        return SECURITY_CHAIN_ORDER

    async def login(self, username: str, password: str) -> AuthenticationResult:
        """第 1–2 步：Authenticate → IdentityContext（`docs/02` §16 / §19）。

        Args:
            username: 用户名。
            password: 明文口令。

        Returns:
            `AuthenticationResult`（含服务端身份与一次性明文 token）。

        Raises:
            PermissionDeniedError: `STRUCTAI-4000`，认证失败（见模块裁决）。
        """
        return await self._authentication.authenticate(username, password)

    async def authenticate(self, token: str) -> IdentityContext:
        """第 2 步：Token → IdentityContext（`docs/02` §20）。

        Args:
            token: 客户端持有的明文 token。

        Returns:
            服务端身份上下文。

        Raises:
            PermissionDeniedError: `STRUCTAI-4000`，会话无效（见 `session.py` 裁决）。
        """
        return await self._sessions.validate_token(token)

    async def build_context(self, token: str) -> SecurityContext:
        """第 2–4 步：认证 + 有效权限，产出唯一的安全上下文（`docs/02` §42）。

        Args:
            token: 客户端持有的明文 token。

        Returns:
            `SecurityContext`（身份 + 有效权限快照）。

        Raises:
            PermissionDeniedError: `STRUCTAI-4000`，会话无效。
        """
        identity = await self.authenticate(token)
        permissions = await self._permissions.get_permissions(identity)
        return SecurityContext(identity=identity, permissions=frozenset(permissions))

    async def authorize(
        self,
        identity: IdentityContext,
        permission: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> None:
        """第 4 步：Effective Permission（`docs/02` §29 / §31；`docs/07` §9 第 11 步）。

        Args:
            identity: 服务端身份上下文（**只能**来自 `authenticate` / `build_context`）。
            permission: 权限码。
            resource_type: 资源类型（可为 `None`）。
            resource_id: 资源标识（可为 `None`）。

        Raises:
            PermissionDeniedError: `STRUCTAI-4000`，有效权限不足（`docs/07` §11）。
        """
        await self._permissions.require(identity, permission, resource_type, resource_id)

    async def logout(self, session_id: str) -> bool:
        """注销当前会话（`docs/02` §21；审计项 `LOGOUT` / `SESSION_REVOKED`）。

        Args:
            session_id: 会话标识。

        Returns:
            确实撤销了行为 `True`。
        """
        return await self._sessions.revoke(session_id)


def _invalid_credentials() -> PermissionDeniedError:
    """构造**形状一致**的认证失败异常（见模块的失败口径裁决）。

    Returns:
        `PermissionDeniedError`（`STRUCTAI-4000`），消息与 `details` 固定不变 ——
        无论用户是否存在、口令是否错误、账号是否停用 / 锁定。
    """
    return PermissionDeniedError(
        INVALID_CREDENTIALS_MESSAGE,
        details={"stage": "authentication", "reason": "invalid_credentials"},
    )
