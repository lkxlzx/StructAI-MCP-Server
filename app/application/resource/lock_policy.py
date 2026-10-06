"""Application · Resource · LockPolicy（`docs/07` §12 P14–P18；`docs/02` §36 / §74）。

权威来源
--------
- `docs/02` §36（`exec`）—— 资源（`SoftwareInstance` / `Model` / `Document`）与锁模式
  （`READ` / `WRITE` / `EXCLUSIVE`）的**兼容矩阵**：

  ```text
               READ     WRITE     EXCLUSIVE
  READ          ✓        ✗          ✗
  WRITE         ✗        ✗          ✗
  EXCLUSIVE     ✗        ✗          ✗
  ```

- `docs/02` §74（`exec`）—— `LockPolicy.resolve(operation, resource) -> ResourceLock`：
  `*.QUERY` → `READ`；`risk_level ∈ {HIGH, CRITICAL}` → `EXCLUSIVE`；其余 → `WRITE`。
- `docs/02` §58（`exec`）—— 流水线第 8 步的锁映射建议：
  `Analysis = EXCLUSIVE Model` / `Design = EXCLUSIVE Model` / `Build = WRITE Model` /
  `Delete = WRITE Model` / `Query = READ Model`。
- `docs/02` §35 / §75（`blue` / `exec`）—— 桌面工程软件默认 `SERIAL`；锁层次
  `SoftwareInstance ↓ Model ↓ Document`。
- `docs/07` §9 第 15 步 —— `Concurrency / Resource Lock`（在 `Capability` 之前）。
- `docs/07` §11 —— 冲突必须落 **`STRUCTAI-6100` Resource Locked**（20 码契约）。

落地裁决（只补实现手段，不改取值 / 语义）
----------------------------------------
1. **`docs/02` §74 与 §58 的关系**：§74 的规则是 §58 建议的**精确化**。两者在
   `ANALYSIS.*` / `DESIGN.*`（HIGH → `EXCLUSIVE`）与 `*.QUERY`（`READ`）上一致；
   但在 `BUILD.*` 与 `MODEL.*.DELETE` 上**不一致** —— §58 建议 `WRITE`，而
   `engineering_model_build` / `engineering_model_delete` 在 `docs/07` §5.1 里**都是
   `HIGH`**，故 §74 的第 2 条规则给出 `EXCLUSIVE`。本模块以 §74 为准（它是
   `LockPolicy` 的原文实现），即**取更严格者**（安全方向）。§58 的映射写成
   `PIPELINE_LOCK_HINTS` 供对照与验收断言，**不**作为第二套判定。
2. **兼容矩阵的唯一实现点**：`LOCK_COMPATIBILITY` / `locks_are_compatible()` 在本模块；
   `lock_manager.py` 只消费它，不另写一份判定（`docs/02` §28 的「只允许一处实现」同理）。
3. **`ResourceLock` 的字段**：`docs/02` §74 原文用 `ResourceLock(resource, mode)`，
   `resource` 是 §37 的 `ResourceKey(resource_type, resource_id)`；本模块照抄该形状，
   并额外携带 `owner_id` / `timeout_seconds`（§13 的 `acquire(resource, mode, owner_id,
   timeout)` 需要它们；`docs/07` §4.3 #22 的 `resource_locks` 表也有这两列）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 ORM / Web 框架 / MCP SDK / httpx，
**不**依赖 `app.infrastructure`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from app.domain.enums import LockMode, RiskLevel
from app.domain.protocols import OperationDefinition

__all__ = [
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "EXCLUSIVE_RISK_LEVELS",
    "LOCK_COMPATIBILITY",
    "PIPELINE_LOCK_HINTS",
    "QUERY_SUFFIX",
    "LockPolicy",
    "ResourceKey",
    "ResourceLock",
    "locks_are_compatible",
]

DEFAULT_LOCK_TIMEOUT_SECONDS: Final[int] = 300
"""默认锁租约（秒）。与 `Settings.lock_default_timeout_seconds` 及
`resource_locks.timeout_seconds` 的落库默认值一致（`docs/07` §4.3 #22 / §3.1）。"""

EXCLUSIVE_RISK_LEVELS: Final[frozenset[RiskLevel]] = frozenset({RiskLevel.HIGH, RiskLevel.CRITICAL})
"""需要独占锁的风险等级（`docs/02` §74：`HIGH` / `CRITICAL` → `EXCLUSIVE`）。"""

QUERY_SUFFIX: Final[str] = ".QUERY"
"""只读 Operation 的后缀（`docs/02` §74 原文 `operation.name.endswith(".QUERY")`）。

⚠️ `docs/07` §5.1 的 `engineering_doc` 六个 Operation 名不带命名空间前缀
（`NEW` / `OPEN` / `SAVE` / `SAVE_AS` / `CLOSE` / `INFO`），故 `INFO` 这类只读操作
**不会**被本后缀命中 —— 它们按风险等级落 `MEDIUM` → `WRITE`（`docs/02` §74 的
第二条规则），与 §58 的 `Query = READ Model` 不冲突：§58 只列了 `QUERY` 一族。
"""

LOCK_COMPATIBILITY: Final[Mapping[LockMode, frozenset[LockMode]]] = MappingProxyType(
    {
        LockMode.READ: frozenset({LockMode.READ}),
        LockMode.WRITE: frozenset(),
        LockMode.EXCLUSIVE: frozenset(),
    }
)
"""锁兼容矩阵（`docs/02` §36，逐格照抄）。

语义：`LOCK_COMPATIBILITY[held]` = 在**已持有** `held` 的情况下**仍可授予**的模式集合。
因此 `READ` 只兼容 `READ`（矩阵第一行 ✓ / ✗ / ✗），`WRITE` / `EXCLUSIVE` 不兼容任何模式
（矩阵第二、三行全 ✗）。
"""

PIPELINE_LOCK_HINTS: Final[Mapping[str, LockMode]] = MappingProxyType(
    {
        "ANALYSIS": LockMode.EXCLUSIVE,
        "DESIGN": LockMode.EXCLUSIVE,
        "BUILD": LockMode.WRITE,
        "DELETE": LockMode.WRITE,
        "QUERY": LockMode.READ,
    }
)
"""`docs/02` §58 的流水线锁映射建议（**仅供对照与验收断言**，判定以 §74 的
`LockPolicy.resolve` 为唯一实现；见模块裁决 1）。"""


@dataclass(frozen=True, slots=True)
class ResourceKey:
    """资源锁的键（`docs/02` §37）。

    等价于 `docs/07` §4.3 #22 的 `resource_locks(resource_type, resource_id)`
    复合语义；`resource_type` 取值见 `app.domain.enums.ResourceType`。
    """

    resource_type: str
    resource_id: str


@dataclass(frozen=True, slots=True)
class ResourceLock:
    """一次锁请求（`docs/02` §74）。

    Attributes:
        resource: 被锁资源键（`docs/02` §37）。
        mode: 锁模式（`docs/02` §36 / §39）。
        owner_id: 持有者标识（任务 ID / worker ID / 请求 ID，`docs/07` §4.3 #22）。
        timeout_seconds: 锁租约（秒，`docs/07` §4.3 #22；见模块裁决 3）。
    """

    resource: ResourceKey
    mode: LockMode
    owner_id: str = ""
    timeout_seconds: int = DEFAULT_LOCK_TIMEOUT_SECONDS


def locks_are_compatible(held: LockMode, requested: LockMode) -> bool:
    """在**已持有** `held` 时能否再授予 `requested`（`docs/02` §36）。

    Args:
        held: 已持有的锁模式。
        requested: 新请求的锁模式。

    Returns:
        仅当两者都是 `READ` 时为 `True`；其余组合一律 `False`（矩阵逐格照抄）。
    """
    return requested in LOCK_COMPATIBILITY[held]


class LockPolicy:
    """锁策略：由 Operation + 已解析资源推出锁请求（`docs/02` §74）。

    规则（照抄 §74 的三条分支，顺序不可换）：

    1. `operation.name` 以 `.QUERY` 结尾 → `READ`（只读操作不互斥）。
    2. `operation.risk_level ∈ {HIGH, CRITICAL}` → `EXCLUSIVE`。
    3. 其余 → `WRITE`。
    """

    def __init__(self, *, timeout_seconds: int = DEFAULT_LOCK_TIMEOUT_SECONDS) -> None:
        """绑定默认租约。

        Args:
            timeout_seconds: 锁租约（秒）；调用方传
                `settings.lock_default_timeout_seconds`（`docs/07` §3.1）。
        """
        self._timeout_seconds = timeout_seconds

    @property
    def timeout_seconds(self) -> int:
        """默认锁租约（秒）。"""
        return self._timeout_seconds

    def mode_for(self, operation: OperationDefinition) -> LockMode:
        """该 Operation 需要的锁模式（`docs/02` §74 的三条分支）。

        Args:
            operation: 操作定义（`docs/02` §24）。

        Returns:
            `READ` / `WRITE` / `EXCLUSIVE`。
        """
        if operation.name.endswith(QUERY_SUFFIX):
            return LockMode.READ
        if operation.risk_level in EXCLUSIVE_RISK_LEVELS:
            return LockMode.EXCLUSIVE
        return LockMode.WRITE

    def resolve(
        self,
        operation: OperationDefinition,
        resource: object,
        *,
        owner_id: str = "",
    ) -> ResourceLock:
        """解析出锁请求（`docs/02` §74 原文签名 `resolve(operation, resource)`）。

        Args:
            operation: 操作定义（`docs/02` §24）。
            resource: 已解析资源（`docs/02` §73 的 `ResolvedResource`）；只读取
                `resource_type` / `resource_id` 两个属性，因此本模块**不**依赖
                `app.application.resource.resolver`（避免同层环状导入）。
            owner_id: 持有者标识（`docs/07` §4.3 #22）。

        Returns:
            `ResourceLock`：资源键 + 模式 + 持有者 + 租约。

        Raises:
            TypeError: `resource` 未提供 `resource_type` / `resource_id`
                （装配错误，不是数据错误）。
        """
        resource_type = getattr(resource, "resource_type", None)
        resource_id = getattr(resource, "resource_id", None)
        if not isinstance(resource_type, str) or not isinstance(resource_id, str):
            raise TypeError(
                "LockPolicy.resolve requires a resource with 'resource_type' and "
                "'resource_id' string attributes (docs/02 §73)"
            )
        return ResourceLock(
            resource=ResourceKey(resource_type=resource_type, resource_id=resource_id),
            mode=self.mode_for(operation),
            owner_id=owner_id,
            timeout_seconds=self._timeout_seconds,
        )
