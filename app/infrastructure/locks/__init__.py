"""Infrastructure · Locks 包导出（`docs/07` §3.3；`docs/02` §8 / §36 / §38）。

`docs/07` §3.3 冻结的结构：

    app/infrastructure/locks/  in_memory.py

本包提供「进程内锁（如需持久化形态）」槽位的进程内实现（`docs/07` §3.3）：
串行化**不得交错**的临界区 —— 尤其是审计哈希链追加（`docs/02` §8：
`entry_hash = H(previous_hash + canonical_entry)`）。

红线（`docs/07` §14.1 / §14.4）：本包只依赖标准库与 `app.domain`，**不**反向依赖
`app.application`（因此不 import `lock_policy` 的常量）；**零 SQL**、不持有事务、
不 `commit`。持久化形态是 `resource_locks` 表（`docs/07` §4.3 #22），与进程内锁
**不是**同一个东西。
"""

from __future__ import annotations

from app.infrastructure.locks.in_memory import (
    DEFAULT_LOCK_TIMEOUT_SECONDS,
    LOCK_STAGE,
    InMemoryLock,
    InMemoryLockHandle,
)

__all__ = [
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "LOCK_STAGE",
    "InMemoryLock",
    "InMemoryLockHandle",
]
