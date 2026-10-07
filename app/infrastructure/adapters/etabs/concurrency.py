"""Infrastructure · Adapters · CSI ETABS · Instance concurrency policy（P135，R93 裁决落地）。

权威来源
--------
- `docs/07` §16 **R93** —— 「COM 会话声明为**非**并发安全，但未接线到 Core 的实例并发策略。
  **建议**显式裁决把该常量接到 `InstanceConcurrencyPolicySource`（缺省 `SERIAL` 之外的
  强制），或由部署方在实例配置侧约束」。
- `docs/02` §20 —— 每个软件实例定义 `SERIAL` / `LIMITED` / `PARALLEL`，默认 `SERIAL`
  （「特别是桌面型有限元软件」）。
- `docs/07` §16 R47 —— 四级并发取**最严格**；实例策略经收窄契约
  `InstanceConcurrencyPolicySource` 注入（`app/application/task/scheduler.py`）。
- `hardening.py` 裁决 3 —— `COM_SESSION_CONCURRENCY_SAFE = False`。

落地裁决（P135d 的 R93 裁决）
------------------------------
1. **落点 = 本子包提供一个可注入的策略源**（`EtabsSerialConcurrencyPolicy`），
   **不**改 Core：Core 的 `Scheduler` 仍只认收窄契约
   `InstanceConcurrencyPolicySource.policy_for(software_instance_id)`
   （`app/application/task/scheduler.py`）。本类**结构上**满足它 ——
   `policy_for` 是异步方法且返回该契约的取值词（`"SERIAL"` / `"LIMITED"` / `"PARALLEL"`），
   故**不**需要 import `app.application`（`docs/07` §14.1 的分层红线因此不被破坏）。
2. **强制语义**：`COM_SESSION_CONCURRENCY_SAFE is False` → 该实例的策略**恒为** `SERIAL`，
   **不管**委托源怎么说（含 `PARALLEL` / `LIMITED`）。理由是 COM 会话不声明并发安全，
   并发调用会互相破坏模型状态 —— 这是「取最严格」的直接推论（`docs/02` §20 + R47）。
3. **只对自己认识的实例强制**：`etabs_instance_ids` 之外的实例**原样**委托给注入的
   `delegate`（缺省 = Core 的缺省口径 `SERIAL`），因此本类**不**改变其它软件的行为，
   也**不**形成第二套并发判定。
4. **未注入 delegate 时的行为 = Core 的缺省**：`SERIAL`。**不**回落 `PARALLEL`。
5. **`software_instances` 表没有并发策略列**（`docs/07` §4.3 #10–#13），本批**不**改表：
   「哪些实例是 ETABS」由装配方经 `etabs_instance_ids` 显式给出（与 R25 / R47 的
   「经注入补齐」同一口径）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与同包的 `hardening.py`；**不**引用 SQLAlchemy / FastAPI / MCP SDK /
httpx，**不**依赖 `app.application` / `app.interfaces`，也**不**写任何数据库。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Final, Protocol, runtime_checkable

from app.infrastructure.adapters.etabs.hardening import COM_SESSION_CONCURRENCY_SAFE

__all__ = [
    "CONCURRENCY_LIMITED",
    "CONCURRENCY_PARALLEL",
    "CONCURRENCY_SERIAL",
    "InstancePolicySourceLike",
    "EtabsSerialConcurrencyPolicy",
]

CONCURRENCY_SERIAL: Final[str] = "SERIAL"
CONCURRENCY_LIMITED: Final[str] = "LIMITED"
CONCURRENCY_PARALLEL: Final[str] = "PARALLEL"
"""`docs/02` §20 的三个实例策略取值（逐字；**不**另造取值）。"""


@runtime_checkable
class InstancePolicySourceLike(Protocol):
    """Core 的收窄契约 `InstanceConcurrencyPolicySource` 的**结构**形状。

    ⚠️ 本模块刻意**不** import `app.application.task.scheduler`（分层红线）：
    只按结构声明 `policy_for` 的签名。Core 侧的实现与本类都满足它，
    因此装配方可以任选其一注入 `Scheduler(policies=...)`。
    """

    async def policy_for(self, software_instance_id: str) -> Any:
        """该实例的并发策略（`docs/02` §20 的 `SERIAL` / `LIMITED` / `PARALLEL`）。"""
        ...


class EtabsSerialConcurrencyPolicy:
    """把 COM 会话的非并发安全**强制**成实例级 `SERIAL`（见裁决 1–5）。

    Attributes:
        delegate: 其它实例的策略来源（缺省 = 本类的缺省 `SERIAL` 口径）。
        etabs_instance_ids: 需要强制 `SERIAL` 的实例标识（装配方给出；见裁决 5）。
    """

    def __init__(
        self,
        *,
        delegate: InstancePolicySourceLike | None = None,
        etabs_instance_ids: Iterable[str] = (),
        default: str = CONCURRENCY_SERIAL,
    ) -> None:
        """绑定委托源与需要强制的实例集合（**不**做 I/O）。

        Args:
            delegate: 其它实例的策略来源；`None` → 一律返回 `default`。
            etabs_instance_ids: ETABS 实例标识集合（`docs/02` §20 的实例粒度）。
            default: 委托源未覆盖 / 未注入时的取值；缺省 `SERIAL`（**不**回落 `PARALLEL`）。

        Raises:
            ValueError: `default` 不是 `docs/02` §20 的三个取值之一
                （**不**静默接受一个无法解释的策略名）。
        """
        if default not in {CONCURRENCY_SERIAL, CONCURRENCY_LIMITED, CONCURRENCY_PARALLEL}:
            raise ValueError(f"unknown concurrency policy: {default!r}")
        self._delegate = delegate
        self._etabs_ids = frozenset(str(value) for value in etabs_instance_ids)
        self._default = str(default)

    @property
    def delegate(self) -> InstancePolicySourceLike | None:
        """委托源（只读）。"""
        return self._delegate

    @property
    def etabs_instance_ids(self) -> tuple[str, ...]:
        """需要强制 `SERIAL` 的实例标识（排序后的只读快照）。"""
        return tuple(sorted(self._etabs_ids))

    @property
    def default(self) -> str:
        """未覆盖实例的缺省策略（缺省 `SERIAL`）。"""
        return self._default

    @property
    def com_session_concurrency_safe(self) -> bool:
        """被强制的常量（`hardening.COM_SESSION_CONCURRENCY_SAFE`；见裁决 2）。"""
        return COM_SESSION_CONCURRENCY_SAFE

    async def policy_for(self, software_instance_id: str) -> str:
        """该实例的并发策略（见裁决 2 / 3）。

        Returns:
            ETABS 实例 → 恒 `SERIAL`；其它实例 → 委托源的取值，缺省 `SERIAL`。
            委托源返回非法取值时**明确拒绝**（`ValueError`），**不**静默回落 ——
            一个无法解释的策略名比 `SERIAL` 更危险（同 `hardening.py` 裁决 1 的口径）。
        """
        instance = str(software_instance_id)
        if not COM_SESSION_CONCURRENCY_SAFE and instance in self._etabs_ids:
            return CONCURRENCY_SERIAL
        if self._delegate is None:
            return self._default
        resolved = str(await self._delegate.policy_for(instance))
        if resolved not in {CONCURRENCY_SERIAL, CONCURRENCY_LIMITED, CONCURRENCY_PARALLEL}:
            raise ValueError(f"unknown concurrency policy: {resolved!r}")
        return resolved


def policies_for_instances(
    policies: Mapping[str, str],
) -> EtabsSerialConcurrencyPolicy:
    """便捷构造：从「实例标识 → 策略」映射得到强制源（验收 / 装配用）。

    Args:
        policies: 委托源侧的静态策略映射（`SERIAL` / `LIMITED` / `PARALLEL`）。

    Returns:
        `EtabsSerialConcurrencyPolicy`，其 `etabs_instance_ids` 取映射里策略为
        `PARALLEL` / `LIMITED` 的实例 —— 即「**声明**了并发、但实际非并发安全」的那些，
        正是 R93 指出的风险面。
    """
    risky = tuple(
        instance
        for instance, policy in policies.items()
        if str(policy) in {CONCURRENCY_PARALLEL, CONCURRENCY_LIMITED}
    )
    return EtabsSerialConcurrencyPolicy(
        delegate=_StaticPolicySource(policies),
        etabs_instance_ids=risky,
    )


class _StaticPolicySource:
    """静态映射的委托源（**只**用于 `policies_for_instances`；不导出）。"""

    def __init__(self, policies: Mapping[str, str]) -> None:
        """绑定映射（键 = 实例标识，值 = 策略）。"""
        self._policies = {str(key): str(value) for key, value in policies.items()}

    async def policy_for(self, software_instance_id: str) -> str:
        """该实例的静态策略；未登记 → `SERIAL`（`docs/02` §20 的缺省）。"""
        return self._policies.get(str(software_instance_id), CONCURRENCY_SERIAL)
