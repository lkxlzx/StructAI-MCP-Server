"""Infrastructure · Events · Outbox 投递器（`docs/02` §42 / §58 / §6 / §54 / §51）。

权威来源
--------
- `docs/02` §42（Event Dispatcher）—— 原文循环：
  `while True: events = await repository.pending(limit=100); for event in events:
  try: await bus.publish(to_domain_event(event)); await repository.mark_published(event.id)
  except Exception: await repository.mark_failed(event.id)`。
  同节要求「必须支持 `attempts++` / `retry` / `backoff` / `dead-letter`」，
  并说明「Core Alpha 可以先使用简单 exponential backoff」。
- `docs/02` §5.4（Event 与事务）—— 投递发生在 **COMMIT 之后**
  （「写 Outbox / Event Record ↓ COMMIT ↓ Event Dispatcher ↓ publish」），
  故本模块**不**参与业务事务，也**不** `commit` / `rollback`（`docs/02` §16）。
- `docs/02` §54（Graceful Shutdown）—— 关闭时投递循环必须能退出（`stop_event`）。
- `docs/02` §51（Event Test Matrix）—— `retry` / `duplicate delivery` / `event persistence`。
- `docs/07` §14.4 —— 「单实例失败不得让整个服务器不可用」：投递失败**不得**逃出
  `dispatch_pending` / `run`。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **一次投递 = 一次尝试**（`docs/02` §42 的 `attempts++`）：失败时 `mark_failed`
   递增 `attempts`；当 `attempts + 1 >= max_attempts` 时该记录计入 **dead letter**，
   之后 `dispatch_pending` **不再**投递它（`docs/02` §6 的 `FAILED` 是**终态候选**，
   但重投由本模块的预算决定 —— 见裁决 2）。
2. **`FAILED` 仍可重投，直到预算耗尽**（见 `bus.py` 裁决 4）：`pending` 只排除
   `PUBLISHED`，因此 `FAILED` 记录会被再次取出；本模块用
   `record.attempts >= max_attempts` 判定 dead letter 并**跳过**，
   使「瞬时故障可恢复」与「永久故障不无限重试」同时成立。
3. **`dead_letters()` 是**推导**而非另一份状态**：它按同一判据从
   `store.pending(...)` 的**全集**（`limit` 放宽到 `batch_size` 之外）计算 ——
   为避免与存储层耦合，本模块只记录**本次运行**遇到的 dead letter
   （`self._dead_letters`），并把它作为诊断视图。
4. **`run()` 永不抛出**（`docs/07` §14.4）：单条记录失败只 `mark_failed` + 计数；
   存储或总线整体不可用时记日志并退避，让循环继续 —— 否则一个坏事件会打死
   整个进程的事件投递。
5. **`backoff_seconds` 是**指数**退避的底数**（`docs/02` §42「简单 exponential backoff」）：
   连续空转时按 `backoff_seconds * 2 ** streak` 退避，上限 `max_backoff_seconds`
   （缺省 `backoff_seconds * 32`），避免「空转即忙等」。
6. **`sleep` 可注入**：测试用假 sleep 精确断言退避，避免真实等待。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，
**不**依赖 `app.application` / `app.interfaces`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final

from app.domain.protocols import EventBus, EventRecordSnapshot, EventRecordStore
from app.infrastructure.events.bus import from_record

__all__ = [
    "DEFAULT_BACKOFF_SECONDS",
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_MAX_ATTEMPTS",
    "DISPATCHER_STAGE",
    "DispatchReport",
    "EventDispatcher",
]

DISPATCHER_STAGE: Final[str] = "event_dispatcher"
"""错误 `details.stage` 的固定取值。"""

DEFAULT_BATCH_SIZE: Final[int] = 100
"""每次取出的待投递条数（`docs/02` §42 原文 `limit=100`）。"""

DEFAULT_MAX_ATTEMPTS: Final[int] = 3
"""单条记录的最大投递尝试次数（`docs/02` §42 的 `attempts++` / `dead-letter`）。"""

DEFAULT_BACKOFF_SECONDS: Final[float] = 0.5
"""指数退避的底数（`docs/02` §42「简单 exponential backoff」）。"""

logger = logging.getLogger("structai.events")
"""投递日志（走 stderr；`docs/02` §7）。"""


@dataclass(frozen=True, slots=True)
class DispatchReport:
    """一次投递扫描的结果（`docs/02` §42 的循环体统计）。

    Attributes:
        published: 成功投递并标记 `PUBLISHED` 的条数。
        failed: 投递失败并标记 `FAILED` 的条数。
        dead_lettered: 本次达到 `max_attempts` 的条数（**不再**重投）。
        skipped: 因预算耗尽被跳过的条数（上一轮已成为 dead letter）。
    """

    published: int = 0
    failed: int = 0
    dead_lettered: int = 0
    skipped: int = 0


class EventDispatcher:
    """Outbox → `EventBus` 的投递器（`docs/02` §42）。

    ⚠️ 只读写 Outbox 自身状态与总线，**从不** `commit` / `rollback`（`docs/02` §16）：
    投递发生在业务事务 **COMMIT 之后**（`docs/02` §5.4）。
    """

    def __init__(
        self,
        store: EventRecordStore,
        bus: EventBus,
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        max_backoff_seconds: float | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        """绑定 Outbox 与事件总线。

        Args:
            store: Outbox（`docs/02` §6）。
            bus: 事件总线（`docs/02` §5.2）。
            batch_size: 每轮取出的待投递条数。
            max_attempts: 单条记录的最大尝试次数（`<= 0` → `ValueError`）。
            backoff_seconds: 指数退避底数（`< 0` → `ValueError`）。
            max_backoff_seconds: 退避上限；缺省 `backoff_seconds * 32`。
            sleep: 可注入的等待函数（测试用假 sleep）；缺省 `asyncio.sleep`。
        """
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if backoff_seconds < 0:
            raise ValueError("backoff_seconds must not be negative")
        self._store = store
        self._bus = bus
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._max_backoff_seconds = (
            max_backoff_seconds if max_backoff_seconds is not None else backoff_seconds * 32
        )
        self._sleep = sleep if sleep is not None else asyncio.sleep
        self._dead_letters: list[EventRecordSnapshot] = []
        self._published = 0
        self._failed = 0

    # ===== 只读视图 =====

    @property
    def store(self) -> EventRecordStore:
        """被绑定的 Outbox（只读用途）。"""
        return self._store

    @property
    def bus(self) -> EventBus:
        """被绑定的事件总线（只读用途）。"""
        return self._bus

    @property
    def max_attempts(self) -> int:
        """单条记录的最大尝试次数。"""
        return self._max_attempts

    @property
    def backoff_seconds(self) -> float:
        """指数退避底数。"""
        return self._backoff_seconds

    # ===== `docs/02` §42：一轮投递 =====

    async def dispatch_pending(self) -> DispatchReport:
        """投递当前全部待投递记录（`docs/02` §42 的循环体，**一轮**）。

        Returns:
            `DispatchReport`。

        🔴 本方法**永不**抛出（`docs/07` §14.4）：单条失败只 `mark_failed` + 计数；
        存储整体不可用也只记日志（否则一个坏事件会打死整个投递循环）。
        """
        try:
            records = list(await self._store.pending(limit=self._batch_size))
        except Exception:
            logger.exception("event dispatcher could not read the outbox")
            return DispatchReport()

        published = 0
        failed = 0
        dead_lettered = 0
        skipped = 0
        for record in records:
            if record.attempts >= self._max_attempts:
                # 见模块裁决 2：预算耗尽 → 不再投递（dead letter）。
                skipped += 1
                if all(item.id != record.id for item in self._dead_letters):
                    self._dead_letters.append(record)
                continue
            try:
                await self._bus.publish(from_record(record))
            except Exception:
                failed += 1
                self._failed += 1
                logger.exception(
                    "event delivery failed: event_type=%s attempts=%s",
                    record.event_type,
                    record.attempts,
                )
                await self._safe_mark(self._store.mark_failed, record.id)
                if record.attempts + 1 >= self._max_attempts:
                    dead_lettered += 1
                    if all(item.id != record.id for item in self._dead_letters):
                        self._dead_letters.append(record)
                continue
            published += 1
            self._published += 1
            await self._safe_mark(self._store.mark_published, record.id)

        return DispatchReport(
            published=published,
            failed=failed,
            dead_lettered=dead_lettered,
            skipped=skipped,
        )

    async def run(self, stop_event: asyncio.Event | None = None) -> None:
        """持续投递直到 `stop_event` 置位（`docs/02` §42 / §54）。

        Args:
            stop_event: 关闭信号（`docs/02` §54）；`None` 表示只投递一轮
                （「不传即不循环」—— 与「不传即无限循环」相反，避免测试挂死）。

        🔴 本方法**永不**抛出（`docs/07` §14.4）。
        """
        if stop_event is None:
            await self.dispatch_pending()
            return
        streak = 0
        while not stop_event.is_set():
            try:
                report = await self.dispatch_pending()
            except Exception:  # pragma: no cover - `dispatch_pending` 已自兜底
                logger.exception("event dispatcher loop error")
                report = DispatchReport()
            if report.published == 0:
                streak += 1
                await self._backoff(streak)
            else:
                streak = 0

    # ===== 诊断 =====

    def dead_letters(self) -> tuple[EventRecordSnapshot, ...]:
        """**本次运行**观察到的 dead letter（见模块裁决 3）。"""
        return tuple(self._dead_letters)

    def published_count(self) -> int:
        """本次运行成功投递的总条数。"""
        return self._published

    def failed_count(self) -> int:
        """本次运行投递失败的总条数。"""
        return self._failed

    # ===== 内部 =====

    async def _safe_mark(
        self,
        mark: Callable[[str], Awaitable[bool]],
        record_id: str,
    ) -> None:
        """标记状态；标记本身失败也**不**抛出（见模块裁决 4）。"""
        try:
            await mark(record_id)
        except Exception:
            logger.exception("event dispatcher could not update the outbox record")

    async def _backoff(self, streak: int) -> None:
        """指数退避（`docs/02` §42；见模块裁决 5 / 6）。"""
        delay = min(self._backoff_seconds * (2 ** max(streak - 1, 0)), self._max_backoff_seconds)
        if delay <= 0:
            return
        try:
            await self._sleep(delay)
        except Exception:  # pragma: no cover - 注入的假 sleep 不应抛错
            logger.exception("event dispatcher backoff failed")
