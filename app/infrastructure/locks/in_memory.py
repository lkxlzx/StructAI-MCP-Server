"""Infrastructure · Locks · InMemoryLock（`docs/07` §3.3 / §14.4；`docs/02` §8 / §36 / §38）。

权威来源
--------
- `docs/07` §3.3（项目结构，冻结）—— `app/infrastructure/locks/in_memory.py`：
  「**进程内锁（如需持久化形态）**」这一槽位的进程内实现。
- `docs/02` §8（Audit Integrity）—— 审计哈希链的追加是**临界区**：
  `entry_hash = H(previous_hash + canonical_entry)` 要求「读上一个哈希 → 写本行」
  不可交错，否则链会分叉（`docs/02` §44「用于检测篡改」随之失效）。
- `docs/02` §36（Quota / Rate Limit）—— Core Alpha 允许「内存 limiter」，
  与持久化形态的 `resource_locks` 表（`docs/07` §4.3 #22）并存。
- `docs/02` §38（Runtime Configuration）—— 锁租约是运行期配置
  （`Settings.lock_default_timeout_seconds`）。
- `docs/07` §14.4（运行时）—— 「取消不得杀 Python 进程」「单实例失败不得让整个
  服务器不可用」：等待超时必须**如实报错**，而不是挂住或杀进程。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **`DEFAULT_LOCK_TIMEOUT_SECONDS = 300` 与 `Settings.lock_default_timeout_seconds`
   和 `app/application/resource/lock_policy.DEFAULT_LOCK_TIMEOUT_SECONDS` 同值**，
   但**不** import 后者：`docs/07` §14.1 禁止 `Infrastructure → Application` 反向依赖。
   三个常量同值是**冻结契约**（`docs/07` §3.1 的默认值），由验收测试断言。
2. **「进程内锁」不是「资源锁」**：`app/application/resource/lock_manager.py` 管的是
   业务资源（`SoftwareInstance` / `Model` / `Document`）的 `READ` / `WRITE` /
   `EXCLUSIVE` 兼容矩阵（`docs/02` §36 / §74），其持久化形态是 `resource_locks` 表
   （`docs/07` §4.3 #22）。本模块管的是**同一进程内**「不可交错」的临界区
   （审计哈希链追加、产物写入的读改写序列等），**零 SQL**、不落库。
3. **一个键一个 `asyncio.Lock`，等待有上限**：`docs/02` §38 的租约是秒级；
   等待超时 → `ResourceLockedError`（`STRUCTAI-6100`，`docs/07` §11 的
   「资源被锁」）。**不**无限等待：无限等待会让请求永久挂住（`docs/07` §14.4
   的「不得让整个服务器不可用」）。`details` 只放 `stage` / `reason` / `key`。
4. **`release()` 只释放「确实还持有」的锁**：重复释放返回 `False` 且**不得**
   影响其它持有者（`asyncio.Lock` 被多释放一次会让下一个等待者与真正的持有者
   同时进入临界区 —— 那是最危险的静默错误）。带 `owner_id` 的句柄只有与当前
   持有者一致时才释放，避免「过期的句柄把别人的锁放掉」。
5. **`hold()` 无条件 `finally` 释放**：`docs/02` §41 的「禁止异常情况下不释放」
   在进程内锁上的唯一可执行含义是「退出路径只有一条」。`asynccontextmanager`
   在 `asyncio.CancelledError`（`BaseException`）下同样走 `finally`。
6. **`held_keys()` 是只读诊断**：用于验收「无锁泄漏」（`held_count()` 式的断言）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`（`ResourceLockedError`）：**不**引用 SQLAlchemy /
FastAPI / MCP SDK / httpx，**不**依赖 `app.application` / `app.interfaces` /
`app.observability`（因此不 import `lock_policy`），也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Final

from app.domain.errors import ResourceLockedError

__all__ = [
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "LOCK_STAGE",
    "InMemoryLock",
    "InMemoryLockHandle",
]

LOCK_STAGE: Final[str] = "lock"
"""错误信封里的 `stage` 字面量（`docs/07` §11 / §14.3）。"""

DEFAULT_LOCK_TIMEOUT_SECONDS: Final[int] = 300
"""默认锁租约（秒）。与 `Settings.lock_default_timeout_seconds` 及
`app/application/resource/lock_policy.DEFAULT_LOCK_TIMEOUT_SECONDS` **同值**
（`docs/07` §3.1 / §4.3 #22）；本模块**不** import 后者（`docs/07` §14.1 禁止
`Infrastructure → Application`，见模块裁决 1）。"""


@dataclass(frozen=True, slots=True)
class InMemoryLockHandle:
    """一次成功获取的进程内锁（`docs/07` §3.3）。

    Attributes:
        key: 被锁的临界区键（调用方约定，如 `"audit:{tenant_id}"`）。
        owner_id: 持有者标识（任务 ID / worker ID / 请求 ID）；空串表示未声明。
    """

    key: str
    owner_id: str = ""


class InMemoryLock:
    """进程内互斥锁（`docs/07` §3.3；`docs/02` §8 / §36 / §38）。

    用途：串行化**不得交错**的临界区 —— 尤其是审计哈希链追加（`docs/02` §8：
    「读上一个 `entry_hash` → 写本行」必须原子）与产物写入的读改写序列。
    它是 `docs/07` §3.3 的「进程内锁（如需持久化形态）」槽位；持久化形态是
    `resource_locks` 表（`docs/07` §4.3 #22），两者**不是**同一个东西（模块裁决 2）。

    ⚠️ **零 SQL**、不持有事务、不 `commit`（`docs/07` §14.4）；状态只活在当前
    进程 / 事件循环内，进程重启即释放（这正符合「锁是短生命周期」的口径）。
    """

    def __init__(self, *, default_timeout_seconds: int = DEFAULT_LOCK_TIMEOUT_SECONDS) -> None:
        """绑定默认等待上限。

        Args:
            default_timeout_seconds: 默认等待上限（秒）。

        Raises:
            ValueError: `<= 0`（装配错误；无限等待会让请求永久挂住，见模块裁决 3）。
        """
        if default_timeout_seconds <= 0:
            raise ValueError("default_timeout_seconds must be positive")
        self._default_timeout_seconds = default_timeout_seconds
        self._locks: dict[str, asyncio.Lock] = {}
        self._holders: dict[str, str] = {}

    @property
    def default_timeout_seconds(self) -> int:
        """默认等待上限（秒；`docs/02` §38）。"""
        return self._default_timeout_seconds

    async def acquire(
        self,
        key: str,
        *,
        owner_id: str = "",
        timeout_seconds: int | None = None,
    ) -> InMemoryLockHandle:
        """获取键对应的锁（`docs/02` §8 / §36）。

        Args:
            key: 临界区键。
            owner_id: 持有者标识（用于 `release()` 的归属校验，见模块裁决 4）。
            timeout_seconds: 本次等待上限（秒）；`None` → 默认值。

        Returns:
            成功获取的 `InMemoryLockHandle`。

        Raises:
            ValueError: `key` 为空白（装配 / 调用错误）。
            ResourceLockedError: `STRUCTAI-6100`，`details={"stage": "lock",
                "reason": "timeout", "key": key}` —— 等待超时（见模块裁决 3）。
        """
        if not key or not key.strip():
            raise ValueError("lock key must not be blank")
        lock = self._lock_for(key)
        wait = self._default_timeout_seconds if timeout_seconds is None else timeout_seconds
        try:
            await asyncio.wait_for(lock.acquire(), timeout=wait)
        except TimeoutError as error:
            raise ResourceLockedError(
                "resource lock acquisition timed out",
                details={"stage": LOCK_STAGE, "reason": "timeout", "key": key},
                cause=error,
            ) from error
        self._holders[key] = owner_id
        return InMemoryLockHandle(key=key, owner_id=owner_id)

    async def release(self, handle: InMemoryLockHandle) -> bool:
        """释放锁（`docs/02` §41；见模块裁决 4）。

        Args:
            handle: `acquire()` / `hold()` 返回的句柄。

        Returns:
            `True` 仅当本句柄确实持有该锁；重复释放 / 过期句柄 / 别人的锁 → `False`
            （且**不**影响当前持有者）。
        """
        lock = self._locks.get(handle.key)
        if lock is None or not lock.locked():
            return False
        holder = self._holders.get(handle.key)
        if holder is not None and handle.owner_id and holder != handle.owner_id:
            return False
        self._holders.pop(handle.key, None)
        lock.release()
        return True

    @asynccontextmanager
    async def hold(
        self,
        key: str,
        *,
        owner_id: str = "",
        timeout_seconds: int | None = None,
    ) -> AsyncIterator[InMemoryLockHandle]:
        """上下文管理形式的临界区（`docs/02` §41；见模块裁决 5）。

        `try/finally` **无条件**释放：正常退出、异常退出、任务取消都只走这一条
        退出路径。
        """
        handle = await self.acquire(key, owner_id=owner_id, timeout_seconds=timeout_seconds)
        try:
            yield handle
        finally:
            await self.release(handle)

    async def is_locked(self, key: str) -> bool:
        """该键当前是否被持有（只读诊断）。"""
        lock = self._locks.get(key)
        return lock is not None and lock.locked()

    def held_keys(self) -> tuple[str, ...]:
        """当前被持有的键（排序；用于「无锁泄漏」断言，见模块裁决 6）。"""
        return tuple(sorted(key for key, lock in self._locks.items() if lock.locked()))

    # ===== 内部 =====

    def _lock_for(self, key: str) -> asyncio.Lock:
        """取得（必要时创建）键对应的 `asyncio.Lock`。

        ⚠️ 必须在任何 `await` **之前**完成「查 / 建」，否则两个并发 `acquire()`
        会各自建一把新锁，互斥立即失效。
        """
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock
