"""Infrastructure · Events · 进程内事件总线（`docs/02` §5.2 / §34 / §38 / §51；`docs/07` §14.4）。

权威来源
--------
- `docs/02` §5.2 / §34 / §58 —— `EventBus` 契约（`publish` / `subscribe`）与
  Core Alpha 的唯一实现 `InProcessEventBus`；`docs/02` §38 明确「替换实现
  （Redis / NATS / Kafka）**不改** Domain Event」。
- `docs/02` §5.2 的原文实现（逐字照抄语义）：`subscribe(event_type, handler)` 追加到
  `self._handlers[event_type]`；`publish(event)` 取出 `handlers` 后**顺序** `await`。
- `docs/02` §51（Event Test Matrix）—— 必须覆盖 `publish` / `subscribe` /
  `multiple subscribers` / `handler failure` / `retry` / `event persistence` /
  `duplicate delivery`。重试与持久化归 `EventDispatcher`（§42），本模块只负责
  「一次投递」与「处理器隔离」。
- `docs/07` §14.4 —— 「单实例失败不得让整个服务器不可用」。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **`subscribe` 同时接受类与名字**：P03 冻结的 Domain 契约是
   `subscribe(event_type: type[DomainEvent], handler)`，而 `docs/02` §5.2 / §34 的原文是
   `subscribe(event_type: str, handler)`。两者都接受（统一按**类名**登记），
   使 Domain 契约与规范原文都能原样使用；`handlers_for` 因此只按名字查。
2. **处理器异常被隔离，`publish` 默认不抛**（`docs/02` §51 的 `handler failure`；
   `docs/07` §14.4）：一个坏订阅者不得让整条流水线失败。异常被记录（`failures()`）
   并写入 `structai.events` 日志（stderr），**不**吞掉计数。
   `raise_on_handler_error=True` 供测试 / 严格装配场景还原「裸」行为。
3. **顺序投递、无并发**（`docs/02` §5.2 的 `for handler in handlers: await handler(event)`）：
   顺序投递让「同一事件的处理顺序」可预测（审计 / 通知的先后因此确定）；
   需要并行时由订阅者自行 `gather`。
4. **`published()` 只记录**投递过的事件（诊断 / 验收用），**不**是持久化 ——
   持久化归 Outbox（`docs/02` §5.4 / §6，见 `bus.py`）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，
**不**依赖 `app.application` / `app.interfaces`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import logging
from typing import Final

from app.domain.errors import InternalError
from app.domain.events import DomainEvent
from app.domain.protocols import EventHandler

__all__ = ["IN_PROCESS_STAGE", "InProcessEventBus"]

IN_PROCESS_STAGE: Final[str] = "event_bus"
"""错误 `details.stage` 的固定取值。"""

logger = logging.getLogger("structai.events")
"""事件日志（走 stderr；`docs/02` §7 的 stdout 保留给 MCP 协议）。"""


class InProcessEventBus:
    """进程内事件总线（`docs/02` §5.2 / §58）。

    ⚠️ 只持有进程内状态，**从不** `commit` / `rollback`（`docs/02` §16）。
    """

    def __init__(self, *, raise_on_handler_error: bool = False) -> None:
        """建立空总线。

        Args:
            raise_on_handler_error: `True` 时处理器异常沿 `publish` 上抛
                （测试 / 严格装配场景）；缺省 `False`（见模块裁决 2）。
        """
        self._handlers: dict[str, list[EventHandler]] = {}
        self._published: list[DomainEvent] = []
        self._failures: list[str] = []
        self._raise_on_handler_error = raise_on_handler_error

    # ===== 契约：`app.domain.protocols.EventBus` =====

    async def subscribe(
        self,
        event_type: type[DomainEvent] | str,
        handler: EventHandler,
    ) -> None:
        """订阅某类事件（`docs/02` §5.2 / §34；见模块裁决 1）。

        Raises:
            InternalError: `STRUCTAI-7000` —— 处理器不可调用
                （`details.reason = "invalid_handler"`）。**不**静默忽略：
                一个订阅不上却不报错的处理器等于没订阅。
        """
        if not callable(handler):
            raise InternalError(
                "Event handler is not callable",
                details={"stage": IN_PROCESS_STAGE, "reason": "invalid_handler"},
            )
        self._handlers.setdefault(_type_name(event_type), []).append(handler)

    async def publish(self, event: DomainEvent) -> None:
        """投递事件给全部订阅者（`docs/02` §5.2，逐字语义）。

        Raises:
            Exception: 仅当 `raise_on_handler_error=True` 且某处理器抛错时
                （原异常对象原样上抛，见模块裁决 2）。
        """
        self._published.append(event)
        for handler in tuple(self._handlers.get(type(event).__name__, ())):
            try:
                await handler(event)
            except Exception as error:
                self._failures.append(f"{type(error).__name__}")
                logger.exception(
                    "event handler failed: event_type=%s handler=%s",
                    type(event).__name__,
                    getattr(handler, "__qualname__", repr(handler)),
                )
                if self._raise_on_handler_error:
                    raise

    # ===== 诊断 / 验收 =====

    def handlers_for(self, event_type: type[DomainEvent] | str) -> tuple[EventHandler, ...]:
        """某类事件的订阅者（按订阅顺序）。"""
        return tuple(self._handlers.get(_type_name(event_type), ()))

    def subscriber_count(self) -> int:
        """订阅者总数（跨全部事件类型）。"""
        return sum(len(handlers) for handlers in self._handlers.values())

    def published(self) -> tuple[DomainEvent, ...]:
        """投递过的事件（见模块裁决 4；诊断用）。"""
        return tuple(self._published)

    def failures(self) -> tuple[str, ...]:
        """失败处理器的异常**类名**（只放类名：异常消息可能带连接串，`docs/07` §14.3）。"""
        return tuple(self._failures)

    def clear(self) -> None:
        """清空订阅与诊断记录（测试 / 装配隔离用）。"""
        self._handlers.clear()
        self._published.clear()
        self._failures.clear()

    @property
    def raise_on_handler_error(self) -> bool:
        """处理器异常是否上抛（见模块裁决 2）。"""
        return self._raise_on_handler_error


def _type_name(event_type: type[DomainEvent] | str) -> str:
    """把「事件类或事件名」统一成事件名（`docs/02` §5.1 的 `event_type`）。"""
    if isinstance(event_type, str):
        return event_type
    return event_type.__name__
