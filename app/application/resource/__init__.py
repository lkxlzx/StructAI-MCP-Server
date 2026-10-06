"""Application · Resource（`docs/07` §3.3 冻结结构；`docs/02` §8–§12 / §36–§42 / §74）。

本包是资源解析与资源锁的 Application 层落点（`docs/07` §9 流水线的第 7 / 15 / 21 步）：

| 文件 | 内容 | 批次 |
| --- | --- | --- |
| `resolver.py` | `ResourceResolver` + `ResolvedResource`（§8–§12 / §73） | **P14 ✅** |
| `lock_manager.py` | `ResourceLockManager`（`docs/02` §36–§42） | **P14–P18 ✅** |
| `lock_policy.py` | `LockPolicy` + 兼容矩阵（`docs/02` §36 / §74） | **P14–P18 ✅** |

顺序红线（`docs/07` §9）：`Resolve Resource`（第 7 步）**先于** Schema / Engineering /
Permission / Lock —— 它是**跨租户唯一拦截点，必须最先**；`Release Lock`（第 21 步）
**后于** `Postconditions`（第 20 步）。

装配形状（`docs/02` §33 / §123）
--------------------------------
本包的服务与 P10–P13 的安全服务同口径：`ResourceResolver` 持有会话级的
`ResourceStore`（由 `build_resource_store(session)` 装配），因此**不**进进程级容器；
`ResourceLockManager` 是**进程内**状态（`docs/02` §38），由调用方（P36 的
`ExecutionService`）持有，同样**不**进容器 —— `docs/02` §33 的冻结容器形状
（7 字段）不因此改变。

分层红线（`docs/07` §14.1 / §2.2）：本包只依赖标准库、`app.domain` 与**同层**的
`app.application.security`；**不得**依赖 `app.infrastructure` / `app.interfaces`，
也不得出现任何厂商专属内容。
"""

from __future__ import annotations

from app.application.resource.lock_manager import (
    DEFAULT_LOCK_TIMEOUT_SECONDS,
    LockEntry,
    LockHandle,
    LockHolder,
    ResourceLockManager,
)
from app.application.resource.lock_policy import (
    EXCLUSIVE_RISK_LEVELS,
    LOCK_COMPATIBILITY,
    PIPELINE_LOCK_HINTS,
    QUERY_SUFFIX,
    LockPolicy,
    ResourceKey,
    ResourceLock,
    locks_are_compatible,
)
from app.application.resource.resolver import (
    RESOLUTION_PRECEDENCE,
    ResolvedResource,
    ResourceResolver,
    with_resolved_software,
)

__all__ = [
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "EXCLUSIVE_RISK_LEVELS",
    "LOCK_COMPATIBILITY",
    "PIPELINE_LOCK_HINTS",
    "QUERY_SUFFIX",
    "RESOLUTION_PRECEDENCE",
    "LockEntry",
    "LockHandle",
    "LockHolder",
    "LockPolicy",
    "ResourceKey",
    "ResourceLock",
    "ResourceLockManager",
    "ResolvedResource",
    "ResourceResolver",
    "locks_are_compatible",
    "with_resolved_software",
]
