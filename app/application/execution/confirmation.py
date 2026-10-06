"""Application · Execution · ConfirmationService（`docs/07` §8.4；`docs/02` §34–§39）。

权威来源
--------
- `docs/07` §8.4 —— Confirmation Token **必须**：server-generated / 短期 / 绑定 user /
  绑定 tenant / 绑定 operation / 绑定 resource / **一次性**；
  **禁止**用固定字符串（`CONFIRM` / `YES` / `true`）作为确认；缺 Token → `STRUCTAI-4100`。
- `docs/02` §35（`exec`）—— `Confirmation(token, user_id, tenant_id, operation,
  resource_id, expires_at)`（逐字段照抄）。
- `docs/02` §36（`exec`）—— `ConfirmationService(ttl_seconds=300)` +
  `issue(user_id, tenant_id, operation, resource_id=None) -> Confirmation`；
  token 由 `secrets.token_urlsafe(32)` 生成。
- `docs/02` §37（`exec`）—— `verify(token, user_id, tenant_id, operation,
  resource_id=None)`：不存在 / 过期 / 跨用户 / 跨租户 / 跨 operation / 跨 resource
  全部拒绝；**过期即删除**。
- `docs/02` §38（`exec`）—— 验证成功即消费（`pop`），第二次 verify 必须失败。
- `docs/02` §39（`exec`）—— Confirmation 与 Dry Run：高风险操作推荐
  `dry_run → 返回计划 → 用户确认 → issue confirmation → 真正执行`。
- `docs/02` §28 / §29（`exec`）—— `ConfirmationGuard.require(...)` 与风险策略：
  `LOW` / `MEDIUM` 无需确认；`HIGH` / `CRITICAL` 必须确认。
- `docs/07` §9 第 13 步 —— `Confirmation`（**先于** `Idempotency`（14）/ `Lock`（15））。
- `docs/07` §11 —— 缺 Token 落 **`STRUCTAI-4100` Confirmation Required**（20 码契约）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **token 绝不进 `repr` / 日志 / 异常**：`Confirmation.token` 以 `repr=False` 声明
   （`docs/07` §14.3：绝不记录 secret，confirmation token 在列）；`details` 里只出现
   `stage` / `reason` / `operation`，**不含** token 本身。
2. **固定字符串在**查询前**就被拒绝**：`docs/07` §8.4 的禁止项不能只靠「查不到」实现
   —— 那样 `CONFIRM` 会退化成 `invalid_token`，语义含糊且将来若有人把固定串塞进存储
   就会被接受。本模块先做 `FORBIDDEN_CONFIRMATION_TOKENS` 判定（大小写与空白无关），
   命中即按 `forbidden_token` 拒绝；`issue()` 同样拒绝铸造这类 token。
3. **失败原因按 `docs/02` §37 逐一区分**：`missing_token` / `forbidden_token` /
   `invalid_token` / `expired` / `user_mismatch` / `tenant_mismatch` /
   `operation_mismatch` / `resource_mismatch`。§37 原文即给出各情形的不同说明
   （「Confirmation does not belong to user」等），故本模块如实区分阶段与原因；
   消息统一为 `Confirmation required`（对外形状一致，`STRUCTAI-4100`）。
4. **`resource_id` 用「精确相等」判定**（含 `None`）：`docs/02` §37 原文是
   `confirmation.resource_id != resource_id`，即 `None` 只与 `None` 匹配。
   这与「绑定 resource」的字面要求一致（未绑定资源的 token 不能被用于指定资源的操作）。
5. **`ttl_seconds` 必须为正**：非正 TTL 会立刻过期，属装配错误，构造时直接拒绝
   （`ValueError`），而不是运行期静默失败。
6. **存储是进程内的**：`docs/02` §36 的原文实现即 `dict[str, Confirmation]`。
   跨进程 / 重启后的确认属持久化议题（`docs/07` §4.3 的 24 张表里没有 confirmation 表，
   本批**不改表**），故本批保持进程内实现，并如实说明其边界。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库、`app.domain` 与**同层**的 `app.application.security`
（`IdentityContext`）：**不**引用 ORM / Web 框架 / MCP SDK / httpx，
**不**依赖 `app.infrastructure`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final

from app.application.security.context import IdentityContext
from app.domain.enums import RiskLevel
from app.domain.errors import ConfirmationRequiredError
from app.domain.protocols import OperationDefinition

__all__ = [
    "CONFIRMATION_FAILURE_REASONS",
    "CONFIRMATION_REQUIRED_RISK_LEVELS",
    "DEFAULT_CONFIRMATION_TTL_SECONDS",
    "FORBIDDEN_CONFIRMATION_TOKENS",
    "INVALID_CONFIRMATION_MESSAGE",
    "Confirmation",
    "ConfirmationBinding",
    "ConfirmationGuard",
    "ConfirmationService",
]

DEFAULT_CONFIRMATION_TTL_SECONDS: Final[int] = 300
"""默认有效期（秒）—— `docs/02` §36 原文的 `ttl_seconds: int = 300`。

`docs/07` §8.4 只要求「短期」，本模块取规范给出的默认值。**不**新增 Settings 字段
（该值目前没有对应的环境变量；`docs/07` §3.1 的字段清单里也没有它）。
"""

CONFIRMATION_REQUIRED_RISK_LEVELS: Final[frozenset[RiskLevel]] = frozenset(
    {RiskLevel.HIGH, RiskLevel.CRITICAL}
)
"""需要确认的风险等级（`docs/02` §29 / §28：`HIGH` / `CRITICAL`）。"""

FORBIDDEN_CONFIRMATION_TOKENS: Final[frozenset[str]] = frozenset(
    {"CONFIRM", "YES", "TRUE", "OK", "Y", "1"}
)
"""**禁止**用作确认的固定字符串（`docs/07` §8.4 明列 `CONFIRM` / `YES` / `true`）。

比较口径：先 `strip()` 再去大小写（见模块裁决 2），因此 `"confirm"` / `" Yes "`
同样被拒。
"""

CONFIRMATION_FAILURE_REASONS: Final[tuple[str, ...]] = (
    "missing_token",
    "forbidden_token",
    "invalid_token",
    "expired",
    "user_mismatch",
    "tenant_mismatch",
    "operation_mismatch",
    "resource_mismatch",
)
"""失败原因词表（`docs/02` §37 的六种不匹配 + 缺失 / 固定串，见模块裁决 3）。"""

INVALID_CONFIRMATION_MESSAGE: Final[str] = "Confirmation required"
"""对外统一消息（`docs/07` §11 的 `STRUCTAI-4100`；形状一致，见模块裁决 3）。"""

TokenFactory = Callable[[], str]
"""token 生成器（`docs/02` §36 原文用 `secrets.token_urlsafe(32)`）。"""

Clock = Callable[[], datetime]
"""可注入时钟（验收测试据此制造过期 token）。"""


def _utc_now() -> datetime:
    """默认时钟：带时区的 UTC 当前时间。"""
    return datetime.now(UTC)


def _default_token_factory() -> str:
    """默认 token 生成器（`docs/02` §36 原文）。"""
    return secrets.token_urlsafe(32)


def _is_forbidden(token: str) -> bool:
    """该字符串是否属禁止的固定串（见模块裁决 2）。"""
    return token.strip().upper() in FORBIDDEN_CONFIRMATION_TOKENS


@dataclass(frozen=True, slots=True)
class ConfirmationBinding:
    """一次确认的绑定四元组（`docs/07` §8.4：user + tenant + operation + resource）。"""

    user_id: str
    tenant_id: str
    operation: str
    resource_id: str | None = None


@dataclass(frozen=True, slots=True)
class Confirmation:
    """一次签发的确认（`docs/02` §35，逐字段照抄）。

    🔴 `token` 以 `repr=False` 声明：它是 **secret**（`docs/07` §14.3 / §8.4），
    绝不进日志 / 审计 / 异常信息。
    """

    token: str = field(repr=False)
    user_id: str
    tenant_id: str
    operation: str
    resource_id: str | None
    expires_at: datetime

    @property
    def binding(self) -> ConfirmationBinding:
        """绑定的四元组视图（`docs/07` §8.4）。"""
        return ConfirmationBinding(
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            operation=self.operation,
            resource_id=self.resource_id,
        )

    def is_expired(self, now: datetime) -> bool:
        """在 `now` 是否已过期（`docs/02` §37 的 `expires_at <= now`）。"""
        return self.expires_at <= now


class ConfirmationService:
    """确认令牌的签发 / 校验 / 消费（`docs/02` §36–§39；`docs/07` §8.4）。

    ⚠️ 存储是**进程内**的（`docs/02` §36 的原文实现，见模块裁决 6）；本批**不**改表。
    """

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_CONFIRMATION_TTL_SECONDS,
        *,
        token_factory: TokenFactory | None = None,
        clock: Clock | None = None,
    ) -> None:
        """构造确认服务。

        Args:
            ttl_seconds: 有效期（秒）；必须为正（见模块裁决 5）。
            token_factory: token 生成器；缺省 `secrets.token_urlsafe(32)`（`docs/02` §36）。
            clock: 可注入时钟；缺省带时区的 UTC 当前时间。

        Raises:
            ValueError: `ttl_seconds` 非正（装配错误）。
        """
        if ttl_seconds <= 0:
            raise ValueError("confirmation ttl_seconds must be positive")
        self._ttl_seconds = ttl_seconds
        self._token_factory: TokenFactory = token_factory or _default_token_factory
        self._clock: Clock = clock or _utc_now
        self._tokens: dict[str, Confirmation] = {}

    @property
    def ttl_seconds(self) -> int:
        """有效期（秒）。"""
        return self._ttl_seconds

    def issue(
        self,
        *,
        user_id: str,
        tenant_id: str,
        operation: str,
        resource_id: str | None = None,
    ) -> Confirmation:
        """签发确认令牌（`docs/02` §36 原文签名）。

        Args:
            user_id: 绑定的用户（服务端身份，`docs/07` §8.4）。
            tenant_id: 绑定的租户。
            operation: 绑定的 Operation 名。
            resource_id: 绑定的资源标识；`None` 表示只绑定前四项。

        Returns:
            新签发的 `Confirmation`（含**明文** token —— 只允许返回给客户端一次）。

        Raises:
            RuntimeError: token 生成器返回了禁止的固定串（见模块裁决 2）——
                这是装配错误：生成器必须产出**不可预测**的随机串。
        """
        token = self._token_factory()
        if not token or _is_forbidden(token):
            raise RuntimeError("confirmation token factory produced a forbidden or empty token")
        confirmation = Confirmation(
            token=token,
            user_id=str(user_id),
            tenant_id=str(tenant_id),
            operation=str(operation),
            resource_id=None if resource_id is None else str(resource_id),
            expires_at=self._clock() + timedelta(seconds=self._ttl_seconds),
        )
        self._tokens[token] = confirmation
        return confirmation

    def verify(
        self,
        token: str | None,
        user_id: str,
        tenant_id: str,
        operation: str,
        resource_id: str | None = None,
    ) -> Confirmation:
        """校验并**消费**确认令牌（`docs/02` §37 / §38）。

        Args:
            token: 客户端提交的 token；`None` / 空 → 缺失。
            user_id: 当前**服务端**用户标识。
            tenant_id: 当前**服务端**租户标识。
            operation: 本次要执行的 Operation 名。
            resource_id: 本次的资源标识（可为 `None`；见模块裁决 4）。

        Returns:
            被消费掉的 `Confirmation`（已从存储中移除，§38）。

        Raises:
            ConfirmationRequiredError: `STRUCTAI-4100`（`docs/07` §11 / §8.4）。
                `details = {stage: "confirmation", reason: <词表取值>, operation}`
                —— **不含** token（见模块裁决 1）。
        """
        if not token:
            raise self._invalid("missing_token", operation)
        if _is_forbidden(token):
            raise self._invalid("forbidden_token", operation)

        confirmation = self._tokens.get(token)
        if confirmation is None:
            raise self._invalid("invalid_token", operation)

        now = self._clock()
        if confirmation.is_expired(now):
            self._tokens.pop(token, None)  # §37：过期即删除
            raise self._invalid("expired", operation)

        if confirmation.user_id != str(user_id):
            raise self._invalid("user_mismatch", operation)
        if confirmation.tenant_id != str(tenant_id):
            raise self._invalid("tenant_mismatch", operation)
        if confirmation.operation != str(operation):
            raise self._invalid("operation_mismatch", operation)
        expected_resource = None if resource_id is None else str(resource_id)
        if confirmation.resource_id != expected_resource:
            raise self._invalid("resource_mismatch", operation)

        self._tokens.pop(token, None)  # §38：验证成功即消费
        return confirmation

    def revoke(self, token: str) -> bool:
        """主动撤销一个未消费的令牌（`docs/02` §38 的「不得重复使用」的强化入口）。

        Returns:
            `True` 表示本次确实移除了一条令牌；不存在为 `False`（不做区分）。
        """
        return self._tokens.pop(token, None) is not None

    def pending(self) -> int:
        """当前未消费的令牌数量（诊断用；**不含**任何 token 内容）。"""
        return len(self._tokens)

    def purge_expired(self) -> int:
        """清理已过期令牌（`docs/02` §37 的「过期即删除」的批量入口）。

        Returns:
            本次清理的令牌数量。
        """
        now = self._clock()
        expired = [token for token, item in self._tokens.items() if item.is_expired(now)]
        for token in expired:
            self._tokens.pop(token, None)
        return len(expired)

    def requires_confirmation(self, risk_level: RiskLevel) -> bool:
        """该风险等级是否需要确认（`docs/02` §29 的策略）。"""
        return risk_level in CONFIRMATION_REQUIRED_RISK_LEVELS

    def _invalid(self, reason: str, operation: str) -> ConfirmationRequiredError:
        """构造形状一致的 `STRUCTAI-4100`（见模块裁决 1 / 3）。"""
        return ConfirmationRequiredError(
            INVALID_CONFIRMATION_MESSAGE,
            details={
                "stage": "confirmation",
                "reason": reason,
                "operation": str(operation),
            },
        )


class ConfirmationGuard:
    """执行管线上的确认守卫（`docs/02` §28；`docs/07` §9 第 13 步）。

    ⚠️ 只有 `HIGH` / `CRITICAL` 风险的操作才要求确认（`docs/02` §29）；
    其余风险等级**直接放行**，不消费任何 token（`docs/02` §28 的 `return`）。
    """

    def __init__(self, confirmation_service: ConfirmationService) -> None:
        """绑定确认服务。

        Args:
            confirmation_service: `docs/02` §36 的确认服务。
        """
        self._service = confirmation_service

    @property
    def service(self) -> ConfirmationService:
        """被包装的确认服务（只读用途）。"""
        return self._service

    def requires_confirmation(self, operation: OperationDefinition) -> bool:
        """该 Operation 是否需要确认（`docs/02` §29 / §28）。"""
        return self._service.requires_confirmation(operation.risk_level)

    def require(
        self,
        identity: IdentityContext,
        operation: OperationDefinition,
        token: str | None,
        resource_id: str | None = None,
    ) -> Confirmation | None:
        """高风险操作必须带有效 token（`docs/02` §28 原文流程）。

        Args:
            identity: 服务端身份（`docs/02` §26）。
            operation: 操作定义（`docs/02` §24）。
            token: 客户端提交的 confirmation token。
            resource_id: 已解析资源标识（`docs/02` §73）。

        Returns:
            被消费的 `Confirmation`；风险等级不需要确认时返回 `None`。

        Raises:
            ConfirmationRequiredError: `STRUCTAI-4100`，缺 token（`docs/07` §8.4）
                或 token 与 user / tenant / operation / resource 不匹配。
        """
        if not self.requires_confirmation(operation):
            return None
        return self._service.verify(
            token,
            str(identity.user_id),
            str(identity.tenant_id),
            operation.name,
            resource_id,
        )
