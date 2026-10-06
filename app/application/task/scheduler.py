"""Application · Task · Scheduler（`docs/07` §10.2 / §12 P22–P28）。

覆盖 `docs/02` §18 / §20 / §38 / §49 的四级并发语义。

权威来源
--------
- `docs/02` §18（`task`）—— Task Engine **必须**支持四级并发：`global concurrency` /
  `tenant concurrency` / `user concurrency` / `software-instance concurrency`；
  示例 `Tenant A = 10` / `User A = 4` / `CIVIL-01 = 1`；**最终取最严格限制**。
- `docs/02` §20（`task`）—— 每个软件实例定义 `SERIAL` / `LIMITED` / `PARALLEL`，
  默认 `SERIAL`（「特别是桌面型有限元软件」）。
- `docs/02` §49（`task`）—— Core Alpha 用 `asyncio.Queue` 作为调度载体，支持
  `priority` / `concurrency` / `software instance serialization`；未来可换
  Redis / RabbitMQ / NATS / Kafka，但 **Application Interface 不改变**。
- `docs/02` §38（`exec`）—— 进程内实现形态的先例（`ResourceLockManager` 同理）。
- `docs/07` §10.2 —— 「并发：四级（global / tenant / user / software-instance）取
  **最严格**；实例策略 `SERIAL`（默认）/ `LIMITED` / `PARALLEL`」。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **默认上限取自 §18 的示例**：`DEFAULT_TENANT_CONCURRENCY = 10` /
   `DEFAULT_USER_CONCURRENCY = 4` / `DEFAULT_INSTANCE_CONCURRENCY = 1`
   （`docs/02` §18 的 `Tenant A = 10` / `User A = 4` / `CIVIL-01 = 1`），
   `global_limit = 0` 表示**不设限**（§18 未给出全局示例值，Core Alpha 默认放开）。
2. **实例策略由配置注入，不落库**：`docs/02` §20 要求「每个软件实例定义」策略，而
   `software_instances` 表**没有**该列（`docs/07` §4.3 #10–#13），本批**不得改表**
   （`docs/07` §14.3）。故策略经收窄契约 `InstanceConcurrencyPolicySource` 注入：
   `DefaultInstanceConcurrencyPolicy` 的未知实例一律回落 `SERIAL`（§20 的「默认」），
   **不**回落 `PARALLEL` —— 桌面软件并发执行会互相破坏模型状态，默认必须最保守。
3. **`SERIAL → 1`、`LIMITED → limits.instance_limit`、`PARALLEL → 不设限`**：
   `SERIAL` 的语义是「同一实例同时只允许一个任务」（`docs/02` §20），故**不**取
   `instance_limit`（若调用方把 `instance_limit` 配成 `4`，`SERIAL` 必须仍然是 `1`，
   否则「串行」名不副实）；`PARALLEL` 表示实例级不再额外限制，只受其余三级约束。
4. **触限时**不**占用额度**：`docs/02` §18 的「最终取最严格限制」是**准入**语义。
   `try_acquire` 在任一级计数 `>=` 生效上限时返回 `admitted=False` 并**不**登记占用
   —— 否则「被拒一次」会永久吃掉一个额度（拒绝路径必须无副作用）。
5. **状态是进程内状态**（`docs/02` §38 的同理）：本模块**零 SQL**、**不**依赖
   `app.infrastructure`，也**不**写 `tasks` 表 —— 持久化的并发状态是 P29+ 的议题。
   替换为 Redis / NATS 等实现时本类的公开接口不变（§49）。
6. **`counts` 只含非敏感计数**：`docs/07` §14.3 要求绝不记录 secret，故
   `SchedulerDecision.counts` 只放四级计数的**整数**，**不**放租户 / 用户 / 实例标识。
7. **准入按维度键计数，不是全局总数**：`docs/02` §18 的「四级取最严格」是**按维度**的
   限制（`Tenant A = 10` / `User A = 4` / `CIVIL-01 = 1`），**不**是「全局任务数不超过
   最小值」。故 `try_acquire` 用 `count_for(request, level)` 取**该请求自己的维度键**在
   该级的计数，而**不是**各级总数：否则 `SERIAL` 下「另一个实例上的任务」也会被以
   `level="software-instance"` 拒绝（那个实例其实一个任务都没有）。各级**总数**只用于
   诊断（`Scheduler.totals()`），**不**参与准入判定。
分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，
**不**依赖 `app.infrastructure`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Protocol

from app.domain.enums import SoftwareInstanceConcurrencyPolicy

__all__ = [
    "CONCURRENCY_LEVELS",
    "DEFAULT_CONCURRENCY_LIMITS",
    "DEFAULT_INSTANCE_CONCURRENCY",
    "DEFAULT_TENANT_CONCURRENCY",
    "DEFAULT_USER_CONCURRENCY",
    "SCHEDULER_STAGE",
    "ConcurrencyLimits",
    "ConcurrencyRequest",
    "DefaultInstanceConcurrencyPolicy",
    "InstanceConcurrencyPolicySource",
    "Scheduler",
    "SchedulerDecision",
]

SCHEDULER_STAGE: Final[str] = "scheduler"
"""错误 / 诊断的 `stage` 取值（与 `lease` / `progress` 同口径）。"""

DEFAULT_TENANT_CONCURRENCY: Final[int] = 10
"""默认租户级上限 —— `docs/02` §18 示例 `Tenant A = 10`。"""

DEFAULT_USER_CONCURRENCY: Final[int] = 4
"""默认用户级上限 —— `docs/02` §18 示例 `User A = 4`。"""

DEFAULT_INSTANCE_CONCURRENCY: Final[int] = 1
"""默认软件实例级上限 —— `docs/02` §18 示例 `CIVIL-01 = 1`，§20 的「默认 `SERIAL`」。"""

CONCURRENCY_LEVELS: Final[tuple[str, ...]] = (
    "global",
    "tenant",
    "user",
    "software-instance",
)
"""四级并发的级别名（`docs/02` §18；顺序即「取最严格」时的比较顺序）。"""


@dataclass(frozen=True, slots=True)
class ConcurrencyLimits:
    """四级并发的上限配置（`docs/02` §18 / §20）。

    Attributes:
        global_limit: 全局上限；`0` 表示**不设限**（§18 未给出全局示例值）。
        tenant_limit: 租户级上限（§18 示例 `10`）。
        user_limit: 用户级上限（§18 示例 `4`）。
        instance_limit: 软件实例级上限（§18 示例 `1`）；**仅**在实例策略为
            `LIMITED` 时生效（`SERIAL` 恒为 `1`，`PARALLEL` 不设限 —— 见模块裁决 3）。
    """

    global_limit: int = 0
    tenant_limit: int = DEFAULT_TENANT_CONCURRENCY
    user_limit: int = DEFAULT_USER_CONCURRENCY
    instance_limit: int = DEFAULT_INSTANCE_CONCURRENCY


DEFAULT_CONCURRENCY_LIMITS: Final[ConcurrencyLimits] = ConcurrencyLimits()
"""默认四级上限的**模块级单例**（`docs/02` §18）。

⚠️ 用模块级常量而不是在函数签名里直接调用构造器：后者会在**每次调用**时新建一个
默认对象（`ruff` 的 `B008`），且让「默认值」在签名与实现之间漂移
（`ConcurrencyLimits` 是 frozen dataclass，本身不可变，故单例是安全的）。
"""


@dataclass(frozen=True, slots=True)
class ConcurrencyRequest:
    """一次并发准入请求（`docs/02` §18 的四级维度）。

    ⚠️ 本记录只承载**判定所需的维度标识**；`SchedulerDecision.counts` **不**回显它们
    （`docs/07` §14.3：绝不记录 secret —— 标识不属于计数）。

    Attributes:
        task_id: 任务标识（用于 `release` 精确释放，见模块裁决 4）。
        tenant_id: 租户维度。
        user_id: 用户维度。
        software_instance_id: 软件实例维度；`None` 表示**不参与**实例级判定。
    """

    task_id: str
    tenant_id: str
    user_id: str
    software_instance_id: str | None = None


class InstanceConcurrencyPolicySource(Protocol):
    """软件实例并发策略来源（`docs/02` §20）。

    实现由调用方注入：`software_instances` 表**没有**策略列（`docs/07` §4.3 #10–#13），
    本批**不得改表**（`docs/07` §14.3），故策略必须来自配置 / 装配（见模块裁决 2）。
    """

    async def policy_for(self, software_instance_id: str) -> SoftwareInstanceConcurrencyPolicy:
        """该实例的并发策略（`docs/02` §20 的 `SERIAL` / `LIMITED` / `PARALLEL`）。"""
        ...


class DefaultInstanceConcurrencyPolicy:
    """基于配置映射的实例策略来源（`docs/02` §20 的落地形态）。

    ⚠️ 未知实例一律回落 `SERIAL`（§20 的「默认：`SERIAL`」，见模块裁决 2），
    **不**回落 `PARALLEL`：桌面工程软件并发执行会互相破坏模型状态。
    """

    def __init__(
        self,
        policies: Mapping[str, SoftwareInstanceConcurrencyPolicy] | None = None,
        *,
        default: SoftwareInstanceConcurrencyPolicy = SoftwareInstanceConcurrencyPolicy.SERIAL,
    ) -> None:
        """绑定策略映射与缺省策略。

        Args:
            policies: 实例标识 → 策略；缺省空映射（全部实例走 `default`）。
            default: 未知实例的策略；缺省 `SERIAL`（`docs/02` §20）。
        """
        self._policies = dict(policies or {})
        self._default = default

    @property
    def default(self) -> SoftwareInstanceConcurrencyPolicy:
        """未知实例的策略。"""
        return self._default

    async def policy_for(self, software_instance_id: str) -> SoftwareInstanceConcurrencyPolicy:
        """该实例的并发策略；未知实例 → `default`（`docs/02` §20）。"""
        return self._policies.get(str(software_instance_id), self._default)


@dataclass(frozen=True, slots=True)
class SchedulerDecision:
    """一次并发准入的结果（`docs/02` §18 的「取最严格限制」）。

    Attributes:
        admitted: 是否准入（`False` 表示任一级触限）。
        limit: 生效上限（四级中最严格者）；`0` 表示**不设限**。
        level: 触限的那一级（`CONCURRENCY_LEVELS` 之一）；未触限时是最严格的那一级。
        counts: 各级当前并发数（**只含整数计数**，不含标识 —— 见模块裁决 6）。
        reason: 未准入时为触限级别名（`docs/07` §14.3：只放非敏感诊断信息）；
            准入时为空串。
    """

    admitted: bool
    limit: int
    level: str
    counts: Mapping[str, int]
    reason: str = ""


class Scheduler:
    """进程内四级并发准入（`docs/02` §18 / §20 / §49）。

    ⚠️ 状态是**进程内**状态（`docs/02` §38 的同理）：本类**零 SQL**、**不**写库、
    **不**依赖 `app.infrastructure`（`docs/07` §14.1）。替换为分布式实现时本类的
    公开接口不变（`docs/02` §49）。
    """

    def __init__(
        self,
        *,
        limits: ConcurrencyLimits = DEFAULT_CONCURRENCY_LIMITS,
        policies: InstanceConcurrencyPolicySource | None = None,
    ) -> None:
        """绑定上限配置与实例策略来源。

        Args:
            limits: 四级上限（`docs/02` §18）。
            policies: 实例策略来源（`docs/02` §20）；缺省
                `DefaultInstanceConcurrencyPolicy()`（全部实例 `SERIAL`）。
        """
        self._limits = limits
        self._policies = policies or DefaultInstanceConcurrencyPolicy()
        # 每级一个「维度键 → 计数」字典；键只用于内部计数，绝不外泄（见模块裁决 6）。
        self._counters: dict[str, dict[str, int]] = {level: {} for level in CONCURRENCY_LEVELS}
        # 任务标识 → 本次实际占用的维度键（`release` 据此精确释放，见模块裁决 4）。
        self._acquired: dict[str, tuple[tuple[str, str], ...]] = {}

    # ===== 只读视图 =====

    @property
    def limits(self) -> ConcurrencyLimits:
        """四级上限配置（只读）。"""
        return self._limits

    @property
    def policies(self) -> InstanceConcurrencyPolicySource:
        """实例策略来源（只读）。"""
        return self._policies

    # ===== `docs/02` §18：取最严格限制 =====

    async def effective_limit(self, request: ConcurrencyRequest) -> tuple[int, str]:
        """四级中最严格的生效上限与级别名（`docs/02` §18）。

        Args:
            request: 并发准入请求。

        Returns:
            `(上限, 级别名)`：`0` 表示**不设限**（四级都不设限时返回
            `(0, "global")`）；实例级上限由策略决定（`SERIAL → 1`、
            `LIMITED → limits.instance_limit`、`PARALLEL → 不设限` —— 见模块裁决 3）。
        """
        candidates: list[tuple[str, int]] = [("global", self._limits.global_limit)]
        candidates.append(("tenant", self._limits.tenant_limit))
        candidates.append(("user", self._limits.user_limit))
        if request.software_instance_id is not None:
            policy = await self._policies.policy_for(request.software_instance_id)
            if policy is SoftwareInstanceConcurrencyPolicy.SERIAL:
                candidates.append(("software-instance", 1))
            elif policy is SoftwareInstanceConcurrencyPolicy.LIMITED:
                candidates.append(("software-instance", self._limits.instance_limit))
            # `PARALLEL` → 实例级不设限：不加入候选（只受其余三级约束）。
        return _strictest(candidates)

    # ===== `docs/02` §18：准入与释放 =====

    async def try_acquire(self, request: ConcurrencyRequest) -> SchedulerDecision:
        """尝试占用并发额度（`docs/02` §18 的「取最严格限制」）。

        Args:
            request: 并发准入请求。

        Returns:
            `SchedulerDecision`：`admitted=True` 表示已登记占用（调用方**必须**
            在结束时 `release`）；`admitted=False` 表示任一级触限，且**不**占用额度
            （见模块裁决 4），`reason` 为触限级别名。

        ⚠️ 已占用的同一 `task_id` 再次调用是幂等的（不重复计数）。
        """
        limit, level = await self.effective_limit(request)
        # 见模块裁决 7：准入按**该请求自己的维度键**计数，而不是各级总数。
        counts = self._counts_for(request)
        if str(request.task_id) in self._acquired:
            # 幂等：已占用的任务再次 `try_acquire` **不**重复计数、**不**被自己的额度拒绝。
            return SchedulerDecision(
                admitted=True,
                limit=limit,
                level=level,
                counts=counts,
            )
        if limit > 0 and counts[level] >= limit:
            return SchedulerDecision(
                admitted=False,
                limit=limit,
                level=level,
                counts=counts,
                reason=level,
            )
        self._register(request)
        return SchedulerDecision(
            admitted=True,
            limit=limit,
            level=level,
            counts=self._counts_for(request),
        )

    async def release(self, request: ConcurrencyRequest) -> None:
        """释放并发额度（幂等；见模块裁决 4）。

        Args:
            request: 与 `try_acquire` 相同的请求（按 `task_id` 精确释放）。

        ⚠️ 未占用时**不**抛错、**不**产生负数：重复 `release` 与「从未占用」都安全。
        """
        keys = self._acquired.pop(str(request.task_id), None)
        if keys is None:
            return
        for level, key in keys:
            counter = self._counters[level]
            remaining = counter.get(key, 0) - 1
            if remaining > 0:
                counter[key] = remaining
            else:
                counter.pop(key, None)

    def active(self, request: ConcurrencyRequest) -> int:
        """该请求**自己的维度键**上各级计数的最大值（便于断言；`docs/02` §18）。

        ⚠️ 按**维度键**取值（见模块裁决 7）：只统计该请求涉及的维度，**不**取各级总数
        —— 否则「别的实例上的任务」会被算进本请求的计数。

        Args:
            request: 并发准入请求。

        Returns:
            该请求各级计数中的最大值；全部为 `0` 时返回 `0`。
        """
        counts = self._counts_for(request)
        return max(counts.values(), default=0)

    def count_for(self, request: ConcurrencyRequest, level: str) -> int:
        """该请求在某一级的并发数（`docs/02` §18 的**按维度**计数，见模块裁决 7）。

        Args:
            request: 并发准入请求。
            level: 级别名（`CONCURRENCY_LEVELS` 之一）。

        Returns:
            `global` → 全局键（该级只有一个键 `""`）的计数；
            `tenant` → `str(request.tenant_id)` 键的计数；
            `user` → `str(request.user_id)` 键的计数；
            `software-instance` → `request.software_instance_id` 非空时其键的计数，
            否则 `0`（该请求**不参与**实例级判定）。

        Raises:
            ValueError: `level` 不在 `CONCURRENCY_LEVELS` 内。
        """
        if level == "global":
            # 该级只有一个键 `""`（见 `_register`）。
            return self._counters["global"].get("", 0)
        if level == "tenant":
            return self._counters["tenant"].get(str(request.tenant_id), 0)
        if level == "user":
            return self._counters["user"].get(str(request.user_id), 0)
        if level == "software-instance":
            if request.software_instance_id is None:
                return 0
            return self._counters["software-instance"].get(str(request.software_instance_id), 0)
        raise ValueError(f"unknown concurrency level: {level}")

    def active_total(self) -> int:
        """当前已登记占用的任务数（诊断 / 泄漏检查用）。"""
        return len(self._acquired)

    # ===== 内部 =====

    def _register(self, request: ConcurrencyRequest) -> None:
        """登记本次占用（已占用的 `task_id` 直接返回 —— 幂等）。"""
        task_id = str(request.task_id)
        if task_id in self._acquired:
            return
        keys: list[tuple[str, str]] = [("global", "")]
        if self._limits.tenant_limit > 0:
            keys.append(("tenant", str(request.tenant_id)))
        if self._limits.user_limit > 0:
            keys.append(("user", str(request.user_id)))
        if request.software_instance_id is not None:
            keys.append(("software-instance", str(request.software_instance_id)))
        for level, key in keys:
            counter = self._counters[level]
            counter[key] = counter.get(key, 0) + 1
        self._acquired[task_id] = tuple(keys)

    def totals(self) -> Mapping[str, int]:
        """各级当前并发数的**总数**（只含整数 —— 见模块裁决 6）。

        ⚠️ **仅供诊断**（泄漏检查 / 观测）：各级总数**不**用于准入判定 ——
        准入按**维度键**计数（`count_for`，见模块裁决 7）。用总数判定会让
        「另一个实例 / 另一个租户上的任务」误伤本请求。
        """
        return MappingProxyType(
            {level: sum(self._counters[level].values()) for level in CONCURRENCY_LEVELS}
        )

    def _counts_for(self, request: ConcurrencyRequest) -> Mapping[str, int]:
        """该请求**自己的维度键**上各级的计数（`docs/02` §18；见模块裁决 7）。

        Args:
            request: 并发准入请求。

        Returns:
            四级 → 该请求对应维度键的计数（不涉及该级的请求记 `0`）。
        """
        return MappingProxyType(
            {level: self.count_for(request, level) for level in CONCURRENCY_LEVELS}
        )


def _strictest(candidates: list[tuple[str, int]]) -> tuple[int, str]:
    """四级候选中取**最严格**者（`docs/02` §18）。

    Args:
        candidates: `(级别名, 上限)` 列表；`0` 表示该级不设限。

    Returns:
        `(上限, 级别名)`：不设限的级被忽略；若全部不设限则返回 `(0, "global")`。
        并列时取**更靠后**的级（`CONCURRENCY_LEVELS` 的顺序即「越靠后越具体」，
        故 `software-instance` 优先于 `tenant` —— 桌面实例的 `SERIAL` 语义最具体）。
    """
    finite = [(index, level, limit) for index, (level, limit) in enumerate(candidates) if limit > 0]
    if not finite:
        return (0, CONCURRENCY_LEVELS[0])
    # 并列时取**更靠后**的级：次键用 `-index`，使 `software-instance` 优先于 `tenant`
    # （`CONCURRENCY_LEVELS` 越靠后越具体 —— 见本函数的 Returns）。
    _, level, limit = min(finite, key=lambda item: (item[2], -item[0]))
    return (limit, level)
