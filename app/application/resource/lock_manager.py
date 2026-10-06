"""Application · Resource · ResourceLockManager（`docs/07` §12 P14–P18；`docs/02` §36–§42）。

权威来源
--------
- `docs/02` §36（`exec`）—— 资源（`SoftwareInstance` / `Model` / `Document`）与
  `READ` / `WRITE` / `EXCLUSIVE` 三种模式；兼容矩阵见 `lock_policy.py`。
- `docs/02` §37（`exec`）—— `ResourceKey(resource_type, resource_id)`（本模块从
  `lock_policy.py` 复用同一类型，不另造）。
- `docs/02` §38（`exec`）—— **In-Memory Lock Manager**：`LockEntry(readers, writer)` +
  `asyncio.Lock` 互斥；Core Alpha 的实现形态。
- `docs/02` §39（`exec`）—— `acquire(resource, mode)`：`READ` 遇 writer → 拒绝；
  `WRITE` / `EXCLUSIVE` 遇任何持有者 → 拒绝。
- `docs/02` §40（`exec`）—— `release(resource, mode)`：`READ` 递减、其余清 writer；
  无持有者时移除条目。
- `docs/02` §41（`exec`）—— 锁作用域必须是 `Acquire ↓ Execute ↓ Release`，
  且**禁止异常情况下不释放**。
- `docs/02` §13（`impl`）—— `acquire(resource, mode, owner_id, timeout)` 的扩展签名
  （`owner_id` / `timeout` 对应 `docs/07` §4.3 #22 的 `resource_locks` 两列）。
- `docs/07` §9 第 15 步 —— `Concurrency / Resource Lock`；第 21 步 —— `Release Lock`。
- `docs/07` §11 —— 冲突落 **`STRUCTAI-6100` Resource Locked**（20 码契约，不新增码）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **`release` 收 `LockHandle` 而不是 `(resource, mode)`**：`docs/02` §40 的
   `release(resource, mode)` 在「同一资源上有多个 `READ` 持有者」时无法区分是谁在释放，
   也无法阻止「未持有却释放」导致的**锁泄漏反向错误**（把别人的 `READ` 计数减掉）。
   `acquire()` 因此返回 `LockHandle`（资源 + 模式 + 持有者），`release(handle)` 按句柄
   精确释放；`hold()` 上下文管理器保证 `try/finally` 语义（`docs/02` §41 / §65）。
2. **租约（`timeout`）落地为可判定的过期**：`docs/02` §13 要求传入 `timeout`，
   `docs/07` §4.3 #22 的 `resource_locks` 也有 `timeout_seconds` 列。本模块把每个持有者
   的 `acquired_at` + `timeout_seconds` 记在条目上，并提供 `expire_stale()`：
   超租约的持有者在下一次 `acquire` / `release` / `expire_stale` 时被清理
   —— 这样「进程内锁」不会因为调用方崩溃而永久占住（`docs/02` §41 的反面）。
3. **锁状态是进程内状态**：`docs/02` §38 明确 Core Alpha 用 In-Memory 实现；
   `resource_locks` 表是跨进程 / 崩溃恢复的持久化锚点（`docs/07` §4.3 #22），
   其持久化写入属 Task Engine 批次（P22–P28），本批**不**写表、**不**改表。
4. **`owner_id` 默认取空串**：`docs/02` §39 的原文签名没有 `owner_id`，
   §13 的扩展签名有。空串表示「未标注持有者」，不影响判定。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain` / 同层的 `lock_policy`：**不**引用 ORM / Web 框架 /
MCP SDK / httpx，**不**依赖 `app.infrastructure`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import MappingProxyType

from app.application.resource.lock_policy import (
    DEFAULT_LOCK_TIMEOUT_SECONDS,
    ResourceKey,
    ResourceLock,
    locks_are_compatible,
)
from app.domain.enums import LockMode
from app.domain.errors import ResourceLockedError

__all__ = [
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "LockEntry",
    "LockHandle",
    "LockHolder",
    "ResourceLockManager",
]

Clock = Callable[[], datetime]
"""取当前时间的可注入时钟（验收测试据此制造过期租约）。"""


def _utc_now() -> datetime:
    """默认时钟：带时区的 UTC 当前时间。"""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class LockHandle:
    """一次成功 `acquire` 的句柄（见模块裁决 1）。

    `release()` 只接受句柄：句柄即「这次持锁」的凭证，因此不存在
    「未持有却释放」把别人的计数减掉的路径。
    """

    resource: ResourceKey
    mode: LockMode
    owner_id: str = ""


@dataclass(frozen=True, slots=True)
class LockHolder:
    """一个持有者（`docs/02` §38 的 `readers` / `writer` 细化到「谁持有、持到何时」）。"""

    mode: LockMode
    owner_id: str
    acquired_at: datetime
    timeout_seconds: int

    def expires_at(self) -> datetime:
        """租约到期时刻（`docs/02` §13 的 `timeout`；`docs/07` §4.3 #22）。"""
        return self.acquired_at + timedelta(seconds=self.timeout_seconds)

    def is_expired(self, now: datetime) -> bool:
        """在 `now` 是否已超租约。"""
        return self.expires_at() <= now


@dataclass(slots=True)
class LockEntry:
    """一个资源的锁条目（`docs/02` §38 的 `LockEntry(readers, writer)`）。

    `holders` 是持有者明细；`readers` / `writer` 两个属性保留 §38 的语义视图
    （`writer` 对 `WRITE` / `EXCLUSIVE` 都为真，§39 的判定只看「有没有写者」）。
    """

    holders: list[LockHolder] = field(default_factory=list)

    @property
    def readers(self) -> int:
        """`READ` 持有者数量（`docs/02` §38）。"""
        return sum(1 for holder in self.holders if holder.mode is LockMode.READ)

    @property
    def writer(self) -> bool:
        """是否存在 `WRITE` / `EXCLUSIVE` 持有者（`docs/02` §38）。"""
        return any(holder.mode is not LockMode.READ for holder in self.holders)

    @property
    def modes(self) -> tuple[LockMode, ...]:
        """当前持有的模式（去重、稳定顺序），用于冲突诊断。"""
        ordered: list[LockMode] = []
        for holder in self.holders:
            if holder.mode not in ordered:
                ordered.append(holder.mode)
        return tuple(ordered)


class ResourceLockManager:
    """进程内资源锁管理器（`docs/02` §36–§42；`docs/07` §9 第 15 / 21 步）。

    按 `ResourceKey` 互斥：兼容性判定**只**来自 `lock_policy.locks_are_compatible`
    （`docs/02` §36 的矩阵，唯一实现点）；冲突一律抛
    `ResourceLockedError`（**`STRUCTAI-6100`**，`docs/07` §11）。

    ⚠️ 本类是**进程内**状态（`docs/02` §38）；多进程 / 崩溃恢复依赖
    `resource_locks` 表（P22–P28 批次），本批不写表。
    """

    def __init__(
        self,
        *,
        default_timeout_seconds: int = DEFAULT_LOCK_TIMEOUT_SECONDS,
        clock: Clock | None = None,
    ) -> None:
        """构造锁管理器。

        Args:
            default_timeout_seconds: 默认租约（秒）；调用方传
                `settings.lock_default_timeout_seconds`（`docs/07` §3.1）。
            clock: 可注入时钟；缺省用带时区的 UTC 当前时间（见模块裁决 2）。
        """
        self._default_timeout_seconds = default_timeout_seconds
        self._clock: Clock = clock or _utc_now
        self._entries: dict[ResourceKey, LockEntry] = {}
        self._mutex = asyncio.Lock()

    @property
    def default_timeout_seconds(self) -> int:
        """默认租约（秒）。"""
        return self._default_timeout_seconds

    async def acquire(
        self,
        resource: ResourceKey,
        mode: LockMode,
        owner_id: str = "",
        timeout_seconds: int | None = None,
    ) -> LockHandle:
        """获取锁（`docs/02` §39 的 `acquire(resource, mode)`；§13 的扩展签名）。

        Args:
            resource: 资源键（`docs/02` §37）。
            mode: 请求的锁模式。
            owner_id: 持有者标识（`docs/07` §4.3 #22）；空串表示未标注。
            timeout_seconds: 租约（秒）；缺省用构造期默认值。

        Returns:
            释放所需的 `LockHandle`。

        Raises:
            ResourceLockedError: `STRUCTAI-6100`，与已持有的锁不兼容
                （`docs/02` §36 矩阵；`docs/07` §11）。`details` 只含资源标识、
                请求模式与已持有模式，**不含**任何 secret。
        """
        now = self._clock()
        timeout = self._default_timeout_seconds if timeout_seconds is None else timeout_seconds
        async with self._mutex:
            self._purge_expired(now)
            entry = self._entries.get(resource)
            if entry is not None and entry.holders:
                held = entry.modes
                if not all(locks_are_compatible(mode_held, mode) for mode_held in held):
                    raise ResourceLockedError(
                        "Resource is locked",
                        details={
                            "resource_type": resource.resource_type,
                            "resource_id": resource.resource_id,
                            "requested_mode": mode.value,
                            "held_modes": [mode_held.value for mode_held in held],
                            "owner_id": owner_id,
                        },
                    )
            if entry is None:
                entry = LockEntry()
                self._entries[resource] = entry
            entry.holders.append(
                LockHolder(
                    mode=mode,
                    owner_id=owner_id,
                    acquired_at=now,
                    timeout_seconds=timeout,
                )
            )
        return LockHandle(resource=resource, mode=mode, owner_id=owner_id)

    async def acquire_lock(self, lock: ResourceLock) -> LockHandle:
        """按 `lock_policy.ResourceLock` 获取锁（`docs/02` §74 → §39 的桥接）。

        Args:
            lock: `LockPolicy.resolve` 的产物。

        Returns:
            释放所需的 `LockHandle`。

        Raises:
            ResourceLockedError: `STRUCTAI-6100`（同 `acquire`）。
        """
        return await self.acquire(
            lock.resource,
            lock.mode,
            lock.owner_id,
            lock.timeout_seconds,
        )

    async def release(self, handle: LockHandle) -> bool:
        """释放锁（`docs/02` §40；见模块裁决 1 的签名调整）。

        Args:
            handle: `acquire` 返回的句柄。

        Returns:
            `True` 表示本次确实释放了一个持有者；`False` 表示句柄已失效
            （重复释放 / 已被 `expire_stale` 清理）—— 两种情况不做区分，
            且**绝不**影响其他持有者的计数。
        """
        now = self._clock()
        async with self._mutex:
            self._purge_expired(now)
            entry = self._entries.get(handle.resource)
            if entry is None:
                return False
            for index, holder in enumerate(entry.holders):
                if holder.mode is handle.mode and holder.owner_id == handle.owner_id:
                    del entry.holders[index]
                    if not entry.holders:
                        self._entries.pop(handle.resource, None)
                    return True
            return False

    @asynccontextmanager
    async def hold(
        self,
        resource: ResourceKey,
        mode: LockMode,
        owner_id: str = "",
        timeout_seconds: int | None = None,
    ) -> AsyncIterator[LockHandle]:
        """`Acquire ↓ Execute ↓ Release` 的上下文管理器（`docs/02` §41 / §65）。

        退出时**无条件**释放（含异常路径），因此不存在「异常情况下不释放」
        （`docs/02` §41 的禁止项；`docs/07` §9 第 21 步 `Release Lock`）。
        Args:
            resource: 资源键。
            mode: 锁模式。
            owner_id: 持有者标识。
            timeout_seconds: 租约（秒）；缺省用默认值。

        Yields:
            `LockHandle`。

        Raises:
            ResourceLockedError: `STRUCTAI-6100`（同 `acquire`）。
        """
        handle = await self.acquire(resource, mode, owner_id, timeout_seconds)
        try:
            yield handle
        finally:
            await self.release(handle)

    async def expire_stale(self) -> int:
        """清理超租约的持有者（见模块裁决 2）。

        Returns:
            本次被清理的持有者数量。
        """
        async with self._mutex:
            return self._purge_expired(self._clock())

    async def is_locked(self, resource: ResourceKey) -> bool:
        """该资源当前是否有持有者（清理过期租约之后）。"""
        async with self._mutex:
            self._purge_expired(self._clock())
            entry = self._entries.get(resource)
            return entry is not None and bool(entry.holders)

    async def snapshot(self) -> Mapping[ResourceKey, tuple[LockHolder, ...]]:
        """当前锁状态的只读快照（诊断用；清理过期租约之后）。

        Returns:
            `ResourceKey → 持有者元组`；只读映射，调用方无法就地改锁状态。
        """
        async with self._mutex:
            self._purge_expired(self._clock())
            return MappingProxyType(
                {key: tuple(entry.holders) for key, entry in self._entries.items()}
            )

    async def held_count(self) -> int:
        """当前持有者总数（诊断 / 泄漏检查用）。"""
        async with self._mutex:
            self._purge_expired(self._clock())
            return sum(len(entry.holders) for entry in self._entries.values())

    def _purge_expired(self, now: datetime) -> int:
        """清理超租约持有者（**必须**在持有 `self._mutex` 时调用）。

        Args:
            now: 判定基准时间。

        Returns:
            被清理的持有者数量。
        """
        removed = 0
        for key in list(self._entries):
            entry = self._entries[key]
            kept = [holder for holder in entry.holders if not holder.is_expired(now)]
            removed += len(entry.holders) - len(kept)
            if kept:
                entry.holders = kept
            else:
                self._entries.pop(key, None)
        return removed
