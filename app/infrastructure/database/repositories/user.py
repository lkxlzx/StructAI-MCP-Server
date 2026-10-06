"""用户仓储（`docs/07` §12 P05 最小集 / §12 P10–P13；`docs/02` §11 / §19 / §16–§18）。

`users` 是 Tenant-owned（`tenant_id` 列，`docs/07` §4.3 #2），因此继承
`TenantScopedRepository`：**按资源读取**必须同时限制 `tenant_id` + `user_id`
（`docs/02` §11），禁止依赖 UI 过滤（`docs/07` §14.3）。

本文件同时实现 `app.domain.protocols.UserLookup`（P10–P13 的认证需要）：

| 方法 | 用途 | 规范 |
| --- | --- | --- |
| `get_by_username` | **认证入口**：全局按用户名读 | `docs/02` §16 |
| `get_by_id_for_tenant` | **会话入口**：租户内按 id 读 | `docs/02` §20 / §11 |
| `record_login_failure` | 失败计数 + 达阈值锁定 | `docs/02` §18 |
| `record_login_success` | 失败计数清零 | `docs/02` §18 |
| `set_locked` | 解锁（管理员动作） | `docs/02` §18 |

为什么认证要一个**全局**的 `get_by_username`（P05 曾刻意不提供）
--------------------------------------------------------------
P05 的注释写明「唯一入口是 `get_by_username_for_tenant`（租户由身份上下文决定）」
—— 那条规则针对**已建立身份之后**的资源读取。而认证发生在**任何身份存在之前**
（`docs/02` §16：`authenticate(username, password)` 只有用户名与口令；租户是认证**之后**
由 `SessionService` 写进 `IdentityContext` 的，`docs/02` §19 / §22）。
此时没有 `tenant_id` 可用，而 `users.username` 在 P04 落地为**全局唯一**
（`docs/07` §4.3 #2），因此全局按用户名查是唯一可行的口径，且不会引入跨租户读面
（返回的记录自带 `tenant_id`，后续所有资源读取仍强制租户过滤）。
本批据此新增 `get_by_username`，并保留 P05 的 `get_by_username_for_tenant` 不变。

安全（`docs/07` §14.3）：`password_hash` 只做列读写，绝不参与日志或错误信息；
返回给 Application 层的是 `UserRecord`（`password_hash` 字段 `repr=False`）。
"""

from __future__ import annotations

from sqlalchemy import select

from app.domain.protocols import UserRecord
from app.infrastructure.database.models.user import UserORM
from app.infrastructure.database.repositories.base import TenantScopedRepository

__all__ = ["UserRepository"]


class UserRepository(TenantScopedRepository[UserORM]):
    """用户仓储（`docs/02` §19；`docs/07` §4.3 #2）。

    - 资源读取：`get_for_tenant` / `list_for_tenant` / `update_for_tenant`
      （继承自 `TenantScopedRepository`，租户过滤不可绕过，`docs/02` §11）；
    - 认证读取：`get_by_username`（见模块 docstring 的裁决）；
    - 登录状态写入：`record_login_failure` / `record_login_success` / `set_locked`
      （`docs/02` §18）。
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

    async def get_by_username(self, username: str) -> UserRecord | None:
        """全局按用户名读取 —— 认证入口（`docs/02` §16）。

        Args:
            username: 用户名（`users.username` 全局唯一，`docs/07` §4.3 #2）。

        Returns:
            命中的用户记录；不存在返回 `None`
            （调用方必须把它与「口令错误」转成**同一个**错误，`docs/02` §17）。
        """
        result = await self.session.execute(select(UserORM).where(UserORM.username == username))
        user = result.scalar_one_or_none()
        return None if user is None else _to_record(user)

    async def get_by_id_for_tenant(self, user_id: str, tenant_id: str) -> UserRecord | None:
        """在指定租户内按主键读取 —— 会话入口（`docs/02` §20 / §11）。

        Args:
            user_id: 用户标识（来自会话行）。
            tenant_id: 会话行上的租户标识。

        Returns:
            命中的用户记录；不属于该租户或不存在返回 `None`
            （两种情况不做区分，避免跨租户存在性泄露，`docs/02` §48）。
        """
        user = await self.get_for_tenant(user_id, tenant_id)
        return None if user is None else _to_record(user)

    async def record_login_failure(self, user_id: str, *, lock_at: int) -> int:
        """累加登录失败计数，达到阈值即锁定（`docs/02` §18）。

        Args:
            user_id: 用户标识（**必须**来自本仓储刚读出的记录）。
            lock_at: 锁定阈值（策略值由 `AuthenticationService` 注入）。

        Returns:
            累加后的失败计数；用户已不存在时返回 `0`（不抛异常 —— 认证路径上
            用户消失属并发删除，调用方仍按认证失败处理）。

        ⚠️ 只 `flush`，**不 `commit`**（`docs/07` §14.4）。
        """
        user = await self._get_for_login_state(user_id)
        if user is None:
            return 0
        count = int(user.failed_login_count) + 1
        await self.update(user, failed_login_count=count, locked=count >= lock_at)
        return count

    async def record_login_success(self, user_id: str) -> None:
        """登录成功后把失败计数清零（`docs/02` §18）。

        Args:
            user_id: 用户标识。

        ⚠️ **不**解锁：解锁是显式管理动作（`set_locked`），
        `docs/02` §18 要求「短暂锁定 + 可恢复」，而不是「登录即自动解锁」。
        """
        user = await self._get_for_login_state(user_id)
        if user is None:
            return
        if int(user.failed_login_count) != 0:
            await self.update(user, failed_login_count=0)

    async def set_locked(self, user_id: str, *, locked: bool) -> None:
        """设置账号锁定状态（`docs/02` §18）。

        Args:
            user_id: 用户标识。
            locked: 目标状态。

        ⚠️ 解锁（`locked=False`）时**同时**清零失败计数：否则下一次失败会立刻
        再次触发锁定（`docs/02` §18：不要永久锁死账号）。
        """
        user = await self._get_for_login_state(user_id)
        if user is None:
            return
        changes: dict[str, object] = {"locked": locked}
        if not locked:
            changes["failed_login_count"] = 0
        await self.update(user, **changes)

    async def _get_for_login_state(self, user_id: str) -> UserORM | None:
        """按主键读取一行，用于登录状态写入（`docs/02` §18）。

        ⚠️ 私有方法，只服务上面三个写方法：它们的 `user_id` **只能**来自本仓储
        刚读出的记录（认证路径 / 会话路径），因此不需要再过滤租户；
        对外的资源读取仍走 `TenantScopedRepository` 的租户过滤入口（`docs/02` §11）。
        """
        result = await self.session.execute(select(UserORM).where(UserORM.id == str(user_id)))
        return result.scalar_one_or_none()


def _to_record(user: UserORM) -> UserRecord:
    """ORM 行 → Domain 记录（`password_hash` 字段 `repr=False`，绝不进日志）。"""
    return UserRecord(
        id=str(user.id),
        tenant_id=str(user.tenant_id),
        username=str(user.username),
        password_hash=str(user.password_hash),
        is_active=bool(user.is_active),
        locked=bool(user.locked),
        failed_login_count=int(user.failed_login_count),
    )
