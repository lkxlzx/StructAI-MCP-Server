"""Application · Services · QuotaService（`docs/07` §12 P29–P35；`docs/02` §36 / §40 / §60 / §42）。

权威来源
--------
- `docs/02` §36（`blue`）—— 配额 / 限流必须区分四个维度：`User` / `Tenant` /
  `AI Agent` / `Software Instance`。
- `docs/02` §40（`blue`）—— 至少预留五个指标：`max_tasks` /
  `max_concurrent_tasks` / `max_api_requests` / `max_storage` / `max_projects`。
- `docs/02` §60（`impl`）—— Core Alpha 的限流实现是 **In-memory limiter**，
  未来替换为 Redis；`docs/02` §36 的「Core Alpha：In-memory limiter + DB quota
  definition」同义。
- `docs/02` §42（`impl`）—— Metrics 只是观测出口，**不**参与准入判定。
- `docs/07` §11 —— 20 码错误契约；超配额是**容量拒绝**，复用 `STRUCTAI-5000`
  （见裁决 2），**不**新增错误码。
- `docs/07` §14.1 / §14.2 —— Application 层不得依赖 `app.infrastructure` /
  `app.interfaces` / `app.observability`，也不得出现任何厂商专属内容。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **上限经收窄契约注入，不落库**：`docs/02` §36 的「DB quota definition」对应的
   `quota` 表**不在** `docs/07` §4.3 的 24 张表内，本批**不得改表**
   （`docs/07` §14.3）。故上限经 `app.domain.protocols.QuotaPolicySource` 注入：
   缺省 `StaticQuotaPolicySource()` 返回**全 0**（不限），与「未配备配额表」的事实一致
   —— 这也是 `ConcurrencyLimits.global_limit = 0` 的同一口径（P22–P28 裁决 1）。
2. **超配额复用 `STRUCTAI-5000`**：20 码契约里**没有**配额码，本批**不得**新增
   （`docs/07` §14.2 / §11）。超配额是**容量拒绝**，与 `docs/03` §56 /
   `docs/07` §11 的「Queue Full → STRUCTAI-5000，retryable = true」**同类**，
   故 `require()` 抛 `TaskError`（5000，`retryable=True`）并带
   `details["stage"] = "quota"`。它**不是** `STRUCTAI-4000`：4000 是**授权**判定
   （有效权限不足），而这里是**容量**判定 —— 二者不得混用。
3. **计数按维度键，不是全局总数**（P22–P28 R49 的教训）：`docs/02` §36 的四维度是
   **各自**的额度，故每个指标都按「该请求自己的维度键」计数；用全局总数判定会让
   「另一个租户 / 另一个 Agent 的用量」误伤本请求。全局总数**只**出现在 `usage()`
   的诊断输出里，**不**参与准入（同 `Scheduler.totals()`）。
4. **维度解析顺序：Agent → User → Tenant → Software Instance**（最具体者优先）：
   `agent_id` 非空时用它，否则 `user_id`，再否则 `tenant_id`，都没有时用
   `instance_id`。这与 `docs/02` §36 把 `AI Agent` 与 `User` 并列为独立维度一致
   —— Agent 的额度比其宿主用户更具体，故更优先。
5. **拒绝路径零副作用**：触限时**不**登记占用（不推进窗口、不递增计数），否则
   「被拒一次」会永久吃掉一个额度（`Scheduler.try_acquire` 的同一条约束）。
6. **窗口是有界滑动窗口**：`max_api_requests` 的计数只保留 `window_seconds` 内的
   时间戳，且每键的时间戳**有界**（`docs/07` §14.4：禁止无限 payload）——
   记录上限即 `limit + 1` 条，越界即拒绝且不再追加。
7. **负数是装配错误，绝不静默钳位**：`QuotaLimits` 的任何负字段 →
   `InternalError`（7000）`reason="invalid_limits"`。静默改成 0（不限）会把
   「配置写错」变成「配额消失」，是最危险的一类静默降级（`docs/07` §14.3 的同源原则）。
8. **`max_storage` / `max_projects` 的 `used` 由调用方给出**：`artifacts` 表没有
   租户归属列、`projects` 的归属要经 `tenant_id` 传递（`docs/07` §4.3），本模块
   **零 SQL**、不读库，故这两个指标的「当前值」由调用方作为入参传入
   （`check_storage(additional_bytes=...)` / `check_projects(current_projects=...)`），
   模块自身只维护**自己登记过**的增量（`register_task(storage_bytes=...)`）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 SQLAlchemy / FastAPI / MCP SDK /
httpx，**不**依赖 `app.infrastructure` / `app.interfaces` / `app.observability`，
也**不**出现任何厂商专属内容。状态是**进程内**状态（`docs/02` §60），零 SQL；
替换为 Redis 等分布式实现时本类的公开接口不变。
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Final

from app.domain.enums import QuotaDimension, QuotaMetric
from app.domain.errors import InternalError, TaskError
from app.domain.protocols import QuotaLimits, QuotaPolicySource

__all__ = [
    "QUOTA_DIMENSIONS",
    "QUOTA_METRICS",
    "QUOTA_STAGE",
    "QuotaDecision",
    "QuotaService",
    "StaticQuotaPolicySource",
]

QUOTA_STAGE: Final[str] = "quota"
"""错误 `details["stage"]` 的固定取值（`docs/07` §11；本模块所有 raise 都用它）。"""

QUOTA_DIMENSIONS: Final[tuple[str, ...]] = tuple(dimension.value for dimension in QuotaDimension)
"""`docs/02` §36 / §60 的四个配额维度（逐字取自 `QuotaDimension`）。

⚠️ 取值**只**来自 `app.domain.enums.QuotaDimension`，本模块**不**另造维度名
（`docs/07` §14.2 的同源原则）。
"""

QUOTA_METRICS: Final[tuple[str, ...]] = tuple(metric.value for metric in QuotaMetric)
"""`docs/02` §36 / §60 的五个配额指标（逐字取自 `QuotaMetric`）。

⚠️ 取值 = `QuotaLimits` 的字段名，二者一一对应（`app.domain.enums.QuotaMetric`
的说明）；本模块**不**另造指标名。
"""

_UNLIMITED: Final[int] = 0
"""`QuotaLimits` 的 `0` 表示**不限**（`app.domain.protocols.QuotaLimits` 的口径）。"""

Clock = Callable[[], datetime]
"""可注入时钟（验收测试据此推进 `max_api_requests` 的滑动窗口）。"""


def _utc_now() -> datetime:
    """默认时钟：带时区的 UTC 当前时间。"""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class QuotaDecision:
    """一次配额判定（`docs/02` §36 / §40 的四维度 × 五指标）。

    Attributes:
        allowed: 是否准入；`False` 表示触限。
        dimension: 生效维度（`QUOTA_DIMENSIONS` 之一）。
        metric: 生效指标（`QUOTA_METRICS` 之一）。
        limit: 生效上限；`0` 表示**不限**。
        used: 判定时的用量（触限时是**已达**的值）。
        remaining: 剩余额度；不限时为 `-1`（哨兵值 —— `0` 会被误读为「刚好用完」）。
        reason: 触限原因（只放非敏感诊断词）；准入时为空串。
    """

    allowed: bool
    dimension: str
    metric: str
    limit: int
    used: int
    remaining: int
    reason: str = ""

    @property
    def ok(self) -> bool:
        """是否准入（`allowed` 的别名，便于 `if decision.ok:` 的读法）。"""
        return self.allowed


@dataclass(frozen=True, slots=True)
class _DimensionKey:
    """一个配额维度键（见模块裁决 3 / 4）。

    Attributes:
        dimension: 维度名（`QUOTA_DIMENSIONS` 之一）。
        value: 该维度上的标识（如 `user-1`）；空串表示「该维度未参与」。
    """

    dimension: str
    value: str

    def __str__(self) -> str:
        """内部计数字典的键（`<dimension>:<value>`；只用于进程内计数）。"""
        return f"{self.dimension}:{self.value}"


def _dimension_key(
    *,
    tenant_id: str,
    user_id: str,
    agent_id: str | None,
    instance_id: str | None,
) -> _DimensionKey:
    """解析该请求的**最具体**维度键（见模块裁决 4）。

    Args:
        tenant_id: 租户维度。
        user_id: 用户维度。
        agent_id: AI Agent 维度；`None` / 空串表示未参与。
        instance_id: 软件实例维度；`None` / 空串表示未参与。

    Returns:
        `agent → user → tenant → instance` 中最先有值的维度键。
    """
    if agent_id:
        return _DimensionKey(str(QuotaDimension.AI_AGENT), str(agent_id))
    if user_id:
        return _DimensionKey(str(QuotaDimension.USER), str(user_id))
    if tenant_id:
        return _DimensionKey(str(QuotaDimension.TENANT), str(tenant_id))
    return _DimensionKey(str(QuotaDimension.SOFTWARE_INSTANCE), str(instance_id or ""))


def _remaining(limit: int, used: int) -> int:
    """剩余额度；不限（`limit == 0`）时返回 `-1` 哨兵值。"""
    if limit <= _UNLIMITED:
        return -1
    return max(limit - used, 0)


def _prune(timestamps: deque[datetime], cutoff: datetime) -> None:
    """丢掉滑动窗口之外的旧时间戳（`docs/07` §14.4：计数必须有界）。"""
    while timestamps and timestamps[0] <= cutoff:
        timestamps.popleft()


def _validate_limits(limits: QuotaLimits) -> None:
    """校验一个上限集合没有负字段（见模块裁决 7）。

    Args:
        limits: 待校验的上限。

    Raises:
        InternalError: `STRUCTAI-7000`，存在负字段；`details` 只含字段名，
            **不**回显任何 secret。
    """
    negative = sorted(field.name for field in fields(limits) if getattr(limits, field.name) < 0)
    if negative:
        raise InternalError(
            "Quota limits must not be negative",
            details={
                "stage": QUOTA_STAGE,
                "reason": "invalid_limits",
                "fields": negative,
            },
        )


class StaticQuotaPolicySource:
    """基于静态映射的配额来源（`docs/02` §36 / §60 的落地形态）。

    解析顺序是**最具体者优先**：`by_user[user_id]` → `by_tenant[tenant_id]` →
    `default`（见模块裁决 4）。

    ⚠️ 任何字段为负数 → `InternalError`（7000）`reason="invalid_limits"`：
    负数是装配错误，**绝不**静默钳位为 `0`（见模块裁决 7）。
    """

    def __init__(
        self,
        default: QuotaLimits | None = None,
        *,
        by_tenant: Mapping[str, QuotaLimits] | None = None,
        by_user: Mapping[str, QuotaLimits] | None = None,
    ) -> None:
        """绑定缺省上限与按租户 / 按用户的上限。

        Args:
            default: 缺省上限；缺省 `QuotaLimits()`（全 0 = 不限，见模块裁决 1）。
            by_tenant: 租户标识 → 上限。
            by_user: 用户标识 → 上限（比租户更具体）。

        Raises:
            InternalError: `STRUCTAI-7000`，任一上限含负字段（见模块裁决 7）。
        """
        self._default = default if default is not None else QuotaLimits()
        self._by_tenant = dict(by_tenant or {})
        self._by_user = dict(by_user or {})
        for limits in (self._default, *self._by_tenant.values(), *self._by_user.values()):
            _validate_limits(limits)

    @property
    def default(self) -> QuotaLimits:
        """缺省上限（全 0 = 不限）。"""
        return self._default

    def limits_for(
        self,
        *,
        tenant_id: str,
        user_id: str,
        agent_id: str | None = None,
    ) -> QuotaLimits:
        """该请求的生效上限（`docs/02` §36 / §60）。

        Args:
            tenant_id: 租户维度。
            user_id: 用户维度。
            agent_id: AI Agent 维度；本实现下**不**改变解析结果
                （Agent 的上限经 `by_user[agent_id]` 表达 —— 见模块裁决 4）。

        Returns:
            最具体的已登记上限；都没有时返回 `default`。
        """
        del agent_id
        user_limits = self._by_user.get(str(user_id))
        if user_limits is not None:
            return user_limits
        tenant_limits = self._by_tenant.get(str(tenant_id))
        if tenant_limits is not None:
            return tenant_limits
        return self._default


class QuotaService:
    """进程内配额 / 限流（`docs/02` §36 / §40 / §60；`docs/07` §11）。

    ⚠️ 状态是**进程内**状态（`docs/02` §60 的 In-memory limiter）：本类**零 SQL**、
    **不**依赖 `app.infrastructure`（`docs/07` §14.1）。替换为 Redis 时公开接口不变。

    ⚠️ 所有计数按**维度键**（见模块裁决 3）；`usage()` 的全局总数**只**用于诊断。
    """

    def __init__(
        self,
        policy: QuotaPolicySource | None = None,
        *,
        clock: Clock | None = None,
    ) -> None:
        """绑定上限来源与时钟。

        Args:
            policy: 上限来源；缺省 `StaticQuotaPolicySource()`（全 0 = 不限，
                见模块裁决 1）。
            clock: 可注入时钟；缺省带时区的 UTC 当前时间。
        """
        self._policy: QuotaPolicySource = (
            policy if policy is not None else StaticQuotaPolicySource()
        )
        self._clock: Clock = clock if clock is not None else _utc_now
        # 每指标一个「维度键 → 计数 / 时间戳窗口」字典；键只用于内部计数，绝不外泄。
        self._api_window: dict[str, deque[datetime]] = {}
        self._concurrent: dict[str, int] = {}
        self._lifetime_tasks: dict[str, int] = {}
        self._storage_bytes: dict[str, int] = {}
        # 任务标识 → 登记时的维度键（`release_task` 据此精确释放，见模块裁决 5）。
        self._task_keys: dict[str, str] = {}

    @property
    def policy(self) -> QuotaPolicySource:
        """上限来源（只读）。"""
        return self._policy

    # ===== `docs/02` §36 / §40：`max_api_requests` 滑动窗口 =====

    async def consume_api_request(
        self,
        *,
        tenant_id: str,
        user_id: str,
        agent_id: str | None = None,
        instance_id: str | None = None,
    ) -> QuotaDecision:
        """消费一次 API 请求额度（`docs/02` §40 的 `max_api_requests`）。

        Args:
            tenant_id: 租户维度。
            user_id: 用户维度。
            agent_id: AI Agent 维度（最具体，见模块裁决 4）。
            instance_id: 软件实例维度（仅在无更具体维度时生效）。

        Returns:
            `QuotaDecision`：`allowed=True` 表示本次请求已计入滑动窗口；
            `allowed=False` 表示窗口内已达上限，且**不**改变窗口（见模块裁决 5）。
        """
        limits = self._limits_for(tenant_id=tenant_id, user_id=user_id, agent_id=agent_id)
        limit = limits.max_api_requests
        key = _dimension_key(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            instance_id=instance_id,
        )
        now = self._clock()
        timestamps = self._api_window.setdefault(str(key), deque())
        _prune(timestamps, now - timedelta(seconds=max(limits.window_seconds, 0)))
        used = len(timestamps)
        if limit > _UNLIMITED and used >= limit:
            return QuotaDecision(
                allowed=False,
                dimension=key.dimension,
                metric=str(QuotaMetric.MAX_API_REQUESTS),
                limit=limit,
                used=used,
                remaining=0,
                reason="api_request_rate_limited",
            )
        # 见模块裁决 6：窗口**有界** —— 每键最多保留 `limit + 1` 条时间戳。
        if limit <= _UNLIMITED or used < limit:
            timestamps.append(now)
        return QuotaDecision(
            allowed=True,
            dimension=key.dimension,
            metric=str(QuotaMetric.MAX_API_REQUESTS),
            limit=limit,
            used=used + 1,
            remaining=_remaining(limit, used + 1),
        )

    # ===== `docs/02` §40：`max_concurrent_tasks` =====

    async def register_task(
        self,
        *,
        tenant_id: str,
        user_id: str,
        agent_id: str | None = None,
        instance_id: str | None = None,
        task_id: str | None = None,
        storage_bytes: int = 0,
    ) -> QuotaDecision:
        """登记一个开始执行的任务（`docs/02` §40 的 `max_concurrent_tasks`）。

        Args:
            tenant_id: 租户维度。
            user_id: 用户维度。
            agent_id: AI Agent 维度（最具体，见模块裁决 4）。
            instance_id: 软件实例维度（仅在无更具体维度时生效）。
            task_id: 任务标识；非空时用于 `release_task` 的**精确**释放。
            storage_bytes: 该任务预计产生的产物字节数（累加到 `max_storage` 用量）。

        Returns:
            `QuotaDecision`：`allowed=False` 表示该维度键的并发数已达上限，
            且**不**消耗任何额度（见模块裁决 5）；`allowed=True` 表示已登记占用
            （调用方**必须**在任务结束时 `release_task`）。
        """
        limits = self._limits_for(tenant_id=tenant_id, user_id=user_id, agent_id=agent_id)
        limit = limits.max_concurrent_tasks
        key = _dimension_key(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            instance_id=instance_id,
        )
        counter_key = str(key)
        used = self._concurrent.get(counter_key, 0)
        if limit > _UNLIMITED and used >= limit:
            return QuotaDecision(
                allowed=False,
                dimension=key.dimension,
                metric=str(QuotaMetric.MAX_CONCURRENT_TASKS),
                limit=limit,
                used=used,
                remaining=0,
                reason="concurrent_task_limit_reached",
            )
        self._concurrent[counter_key] = used + 1
        self._lifetime_tasks[counter_key] = self._lifetime_tasks.get(counter_key, 0) + 1
        if storage_bytes > 0:
            self._storage_bytes[counter_key] = (
                self._storage_bytes.get(counter_key, 0) + storage_bytes
            )
        if task_id:
            self._task_keys[str(task_id)] = counter_key
        return QuotaDecision(
            allowed=True,
            dimension=key.dimension,
            metric=str(QuotaMetric.MAX_CONCURRENT_TASKS),
            limit=limit,
            used=used + 1,
            remaining=_remaining(limit, used + 1),
        )

    async def release_task(
        self,
        *,
        tenant_id: str,
        user_id: str,
        agent_id: str | None = None,
        instance_id: str | None = None,
        task_id: str | None = None,
    ) -> QuotaDecision:
        """释放一个任务的并发额度（`docs/02` §40）。

        Args:
            tenant_id: 租户维度。
            user_id: 用户维度。
            agent_id: AI Agent 维度。
            instance_id: 软件实例维度。
            task_id: `register_task` 时给出的任务标识；给出时按其登记的维度键
                精确释放，否则按本次入参解析出的维度键释放。

        Returns:
            `QuotaDecision`：`allowed=True` 且 `used` 为释放后的并发数。
            重复释放 / 从未登记**不**抛错、**不**产生负数（幂等）。
        """
        limits = self._limits_for(tenant_id=tenant_id, user_id=user_id, agent_id=agent_id)
        limit = limits.max_concurrent_tasks
        key = _dimension_key(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            instance_id=instance_id,
        )
        counter_key = self._task_keys.pop(str(task_id), None) if task_id else None
        if counter_key is None:
            counter_key = str(key)
        used = self._concurrent.get(counter_key, 0)
        remaining_used = used - 1 if used > 0 else 0
        if remaining_used > 0:
            self._concurrent[counter_key] = remaining_used
        else:
            self._concurrent.pop(counter_key, None)
        return QuotaDecision(
            allowed=True,
            dimension=key.dimension,
            metric=str(QuotaMetric.MAX_CONCURRENT_TASKS),
            limit=limit,
            used=remaining_used,
            remaining=_remaining(limit, remaining_used),
        )

    # ===== `docs/02` §40：其余三个指标 =====

    async def check_tasks(
        self,
        *,
        tenant_id: str,
        user_id: str,
        agent_id: str | None = None,
    ) -> QuotaDecision:
        """检查**累计**任务数（`docs/02` §40 的 `max_tasks`，终身计数器）。

        Args:
            tenant_id: 租户维度。
            user_id: 用户维度。
            agent_id: AI Agent 维度。

        Returns:
            `QuotaDecision`：`used` 是该维度键上 `register_task` 的**累计**次数
            （不随 `release_task` 回落 —— 这正是「累计」与「并发」的区别）。
        """
        limits = self._limits_for(tenant_id=tenant_id, user_id=user_id, agent_id=agent_id)
        limit = limits.max_tasks
        key = _dimension_key(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            instance_id=None,
        )
        used = self._lifetime_tasks.get(str(key), 0)
        if limit > _UNLIMITED and used >= limit:
            return QuotaDecision(
                allowed=False,
                dimension=key.dimension,
                metric=str(QuotaMetric.MAX_TASKS),
                limit=limit,
                used=used,
                remaining=0,
                reason="task_quota_exhausted",
            )
        return QuotaDecision(
            allowed=True,
            dimension=key.dimension,
            metric=str(QuotaMetric.MAX_TASKS),
            limit=limit,
            used=used,
            remaining=_remaining(limit, used),
        )

    async def check_storage(
        self,
        *,
        tenant_id: str,
        user_id: str,
        additional_bytes: int = 0,
    ) -> QuotaDecision:
        """检查存储用量（`docs/02` §40 的 `max_storage`）。

        Args:
            tenant_id: 租户维度。
            user_id: 用户维度。
            additional_bytes: 本次预计**新增**的字节数（见模块裁决 8：
                「当前用量」由本模块登记的增量提供，其余由调用方给出）。

        Returns:
            `QuotaDecision`：`used = 已登记字节 + additional_bytes`。
        """
        limits = self._limits_for(tenant_id=tenant_id, user_id=user_id, agent_id=None)
        limit = limits.max_storage
        key = _dimension_key(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=None,
            instance_id=None,
        )
        used = self._storage_bytes.get(str(key), 0) + max(additional_bytes, 0)
        if limit > _UNLIMITED and used > limit:
            return QuotaDecision(
                allowed=False,
                dimension=key.dimension,
                metric=str(QuotaMetric.MAX_STORAGE),
                limit=limit,
                used=used,
                remaining=0,
                reason="storage_quota_exceeded",
            )
        return QuotaDecision(
            allowed=True,
            dimension=key.dimension,
            metric=str(QuotaMetric.MAX_STORAGE),
            limit=limit,
            used=used,
            remaining=_remaining(limit, used),
        )

    async def check_projects(
        self,
        *,
        tenant_id: str,
        user_id: str,
        current_projects: int,
    ) -> QuotaDecision:
        """检查项目数（`docs/02` §40 的 `max_projects`）。

        Args:
            tenant_id: 租户维度。
            user_id: 用户维度。
            current_projects: 当前项目数（见模块裁决 8：由调用方给出，本模块零 SQL）。

        Returns:
            `QuotaDecision`：`current_projects` **超过**上限即拒绝
            （「不超过上限」是允许的，故用 `>` 而不是 `>=`）。
        """
        limits = self._limits_for(tenant_id=tenant_id, user_id=user_id, agent_id=None)
        limit = limits.max_projects
        key = _dimension_key(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=None,
            instance_id=None,
        )
        used = max(current_projects, 0)
        if limit > _UNLIMITED and used > limit:
            return QuotaDecision(
                allowed=False,
                dimension=key.dimension,
                metric=str(QuotaMetric.MAX_PROJECTS),
                limit=limit,
                used=used,
                remaining=0,
                reason="project_quota_exceeded",
            )
        return QuotaDecision(
            allowed=True,
            dimension=key.dimension,
            metric=str(QuotaMetric.MAX_PROJECTS),
            limit=limit,
            used=used,
            remaining=_remaining(limit, used),
        )

    # ===== `docs/07` §11：容量拒绝 =====

    async def require(self, decision: QuotaDecision) -> QuotaDecision:
        """把一次判定变成**强制**（`docs/07` §11）。

        Args:
            decision: 任一 `check_*` / `consume_*` / `register_*` 的产物。

        Returns:
            原样返回 `decision`（便于 `decision = await quota.require(decision)`）。

        Raises:
            TaskError: `STRUCTAI-5000`（`retryable=True`），`allowed` 为 `False` 时
                （见模块裁决 2）。`details` 只含判定字段（上限 / 用量 / 维度 /
                指标 / 原因），**不**含任何 secret。
        """
        if decision.allowed:
            return decision
        raise TaskError(
            "Quota exceeded",
            details={
                "stage": QUOTA_STAGE,
                "metric": decision.metric,
                "dimension": decision.dimension,
                "limit": decision.limit,
                "used": decision.used,
                "reason": decision.reason,
            },
        )

    # ===== 诊断 =====

    def usage(
        self,
        *,
        tenant_id: str,
        user_id: str,
        agent_id: str | None = None,
    ) -> Mapping[str, int]:
        """该维度键上的用量快照（`docs/02` §42）。

        ⚠️ **仅供诊断**（观测 / 泄漏检查）：本映射是**全局总数**口径，
        **不**用于准入判定 —— 准入按**维度键**计数（见模块裁决 3）。
        用总数判定会让「另一个租户 / 另一个 Agent 的用量」误伤本请求。

        Args:
            tenant_id: 租户维度。
            user_id: 用户维度。
            agent_id: AI Agent 维度。

        Returns:
            指标名 → 整数计数（只含整数，**不**含租户 / 用户 / 任务标识 ——
            `docs/07` §14.3：绝不记录 secret / 标识）。
        """
        key = _dimension_key(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            instance_id=None,
        )
        counter_key = str(key)
        return MappingProxyType(
            {
                str(QuotaMetric.MAX_TASKS): self._lifetime_tasks.get(counter_key, 0),
                str(QuotaMetric.MAX_CONCURRENT_TASKS): self._concurrent.get(counter_key, 0),
                str(QuotaMetric.MAX_API_REQUESTS): len(self._api_window.get(counter_key, deque())),
                str(QuotaMetric.MAX_STORAGE): self._storage_bytes.get(counter_key, 0),
                str(QuotaMetric.MAX_PROJECTS): 0,
            }
        )

    # ===== 内部 =====

    def _limits_for(
        self,
        *,
        tenant_id: str,
        user_id: str,
        agent_id: str | None,
    ) -> QuotaLimits:
        """该请求的生效上限（经 `QuotaPolicySource`；装配期已校验非负）。"""
        return self._policy.limits_for(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
        )
