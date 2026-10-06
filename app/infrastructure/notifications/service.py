"""Infrastructure · Notifications · Service（`docs/02` §35 / §45 / §59；`docs/07` §14.4）。

权威来源
--------
- `docs/02` §35（Notification Extension）—— 未来支持的通道：
  `MCP Notification` / `Webhook` / `WebSocket` / `UI` / `Email`；
  「Notification 不成为 Core Tool」。
- `docs/02` §45（MCP Progress / Cancellation）—— 流水线：
  `TaskEngine → MCP progress notification`；本模块的 `notify_task_progress()`
  是这条链**唯一**的接入点。
- `docs/02` §59（Notification Service）—— 第一阶段**只**实现 `InProcess`。
- `docs/02` §34（Event Bus）—— 事件清单含 `TaskProgress`；总线实现可替换而
  Domain Event 不变，故本模块只依赖 Domain 的 `EventBus` 协议。
- `docs/07` §14.4（运行时）—— 「单实例 / 单通道失败不得让整个服务器不可用」：
  通知失败**绝不**影响业务结果，故 `notify()` **永不抛出**。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **`notify()` 永不抛出，失败以返回值 + `failures()` 表达**：`docs/07` §14.4 的
   「单通道失败不得让整个服务器不可用」在通知路径上的唯一可执行含义是
   「投递失败不得向上抛异常」。未知通道与投递异常都记进 `failures()` 并返回
   `False` —— 调用方仍可决定是否记日志，但业务结果不受影响。
2. **通道 → sink 的注册表在进程内，重复 / 空白注册落 `STRUCTAI-7000`**：
   `docs/02` §35 的通道清单是**部署期**事实（MCP Notification / Webhook / …），
   重复注册说明装配代码有 bug；静默覆盖会让「谁在收通知」不可预测。
   20 码契约里没有「通知通道」专用码，故用兜底 `InternalError`（`docs/07` §11）。
3. **`subscribe()` 是**同步**入口，内部把 Domain 的异步 `EventBus.subscribe()`
   调度到当前事件循环**：`docs/02` §45 的接入点写在装配代码里
   （`TaskEngine → MCP progress notification`），而 `app.domain.protocols.EventBus.subscribe`
   是 `async def`（P03 冻结）。同步入口因此把返回的 awaitable 交给运行中的事件循环
   （无运行中的循环时用 `asyncio.run` 立即执行）。**唯一**的订阅点是本方法，
   转发逻辑只有 `_handle_task_progress()` 一处（`docs/02` §28 的「只允许一处实现」）。
4. **`TaskProgress` 载荷只带 `task_id` / `progress` / `message`**：`docs/02` §32 的
   事件字段就是这三个；`docs/07` §14.3 要求通知载荷**不得**携带 secret，
   故本模块不追加任何上下文（身份 / 凭据 / 令牌一律不进载荷）。
5. **`InProcessNotificationSink` 是 `docs/02` §59 的「第一阶段只实现 InProcess」**：
   进程内列表即可验收（`delivered` 属性），替换为 MCP / Webhook 时只换 sink，
   不改 `NotificationService`。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`（`EventBus` / `NotificationSink` /
`NotificationMessage` / `TaskProgress` / `NotificationChannel`）：**不**引用
SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖 `app.application` /
`app.interfaces` / `app.observability`，**不** import `app.infrastructure.events`
（总线经 Domain 契约注入），也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable
from typing import Any, Final

from app.domain.enums import NotificationChannel
from app.domain.errors import InternalError
from app.domain.events import DomainEvent, TaskProgress
from app.domain.protocols import EventBus, NotificationMessage, NotificationSink

__all__ = [
    "IN_PROCESS_CHANNEL",
    "NOTIFICATION_STAGE",
    "TASK_PROGRESS_EVENT_TYPE",
    "InProcessNotificationSink",
    "NotificationService",
]

NOTIFICATION_STAGE: Final[str] = "notification"
"""错误信封里的 `stage` 字面量（`docs/07` §11 / §14.3）。"""

IN_PROCESS_CHANNEL: Final[str] = str(NotificationChannel.IN_PROCESS)
"""Core Alpha 的默认通道（`docs/02` §59「第一阶段只实现 InProcess」）。"""

TASK_PROGRESS_EVENT_TYPE: Final[str] = "TaskProgress"
"""任务进度通知的事件名（`docs/02` §34 / §45；`app.domain.events.TaskProgress`）。"""


class InProcessNotificationSink:
    """进程内通知出口（`docs/02` §59）。

    ⚠️ 只存在于进程内（`docs/02` §35：Notification 不成为 Core Tool）；
    `docs/07` §14.4 要求出口**不得抛出** —— 本实现只是 `list.append`，不会失败。
    """

    def __init__(self) -> None:
        """建立空投递列表。"""
        self._messages: list[NotificationMessage] = []

    @property
    def delivered(self) -> tuple[NotificationMessage, ...]:
        """已投递的通知（按投递顺序；只读快照）。"""
        return tuple(self._messages)

    async def deliver(self, message: NotificationMessage) -> None:
        """记录一条通知（`app.domain.protocols.NotificationSink`）。"""
        self._messages.append(message)


class NotificationService:
    """按通道路由通知，并**永不抛出**（`docs/02` §35 / §45 / §59；`docs/07` §14.4）。

    ⚠️ 通道注册表是**进程内**的（见模块裁决 2）；本类不持有事务、不 `commit`。
    """

    def __init__(
        self,
        *,
        sink: NotificationSink | None = None,
        channel: str = IN_PROCESS_CHANNEL,
    ) -> None:
        """建立注册表并登记默认通道。

        Args:
            sink: 默认通道的出口；`None` → `InProcessNotificationSink()`
                （`docs/02` §59）。
            channel: 默认通道名（取值见 `app.domain.enums.NotificationChannel`）。

        Raises:
            InternalError: `STRUCTAI-7000`，`reason="invalid_channel"`（通道名为空白）。
        """
        self._sinks: dict[str, NotificationSink] = {}
        self._channel = channel
        self._delivered: list[NotificationMessage] = []
        self._failures: list[str] = []
        self.register(channel, InProcessNotificationSink() if sink is None else sink)

    @property
    def channel(self) -> str:
        """默认通道（`docs/02` §35 / §59）。"""
        return self._channel

    def register(self, channel: str, sink: NotificationSink) -> None:
        """登记一个通道出口（装配期调用；`docs/02` §35）。

        Args:
            channel: 通道名（`docs/02` §35 的清单）。
            sink: 出口实现（`app.domain.protocols.NotificationSink`）。

        Raises:
            InternalError: `STRUCTAI-7000` —— 通道名为空白
                （`reason="invalid_channel"`）或重复注册
                （`reason="duplicate_channel"`）；见模块裁决 2。
        """
        if not channel or not channel.strip():
            raise InternalError(
                "notification channel must not be blank",
                details={"stage": NOTIFICATION_STAGE, "reason": "invalid_channel"},
            )
        if channel in self._sinks:
            raise InternalError(
                "notification channel is already registered",
                details={"stage": NOTIFICATION_STAGE, "reason": "duplicate_channel"},
            )
        self._sinks[channel] = sink

    def channels(self) -> tuple[str, ...]:
        """已登记的通道名（排序；只读诊断）。"""
        return tuple(sorted(self._sinks))

    async def notify(self, message: NotificationMessage) -> bool:
        """按 `message.channel` 投递，**永不抛出**（`docs/02` §35；`docs/07` §14.4）。

        Args:
            message: 待投递通知（`docs/02` §35 / §59）。

        Returns:
            `True` 表示出口已接受；`False` 表示通道未登记或出口抛异常
            （两种情况都记进 `failures()`，见模块裁决 1）。
        """
        sink = self._sinks.get(message.channel)
        if sink is None:
            self._failures.append(message.channel)
            return False
        try:
            await sink.deliver(message)
        except Exception:  # noqa: BLE001 —— 通知失败绝不影响业务结果（见模块裁决 1）
            self._failures.append(message.channel)
            return False
        self._delivered.append(message)
        return True

    async def notify_task_progress(
        self,
        *,
        task_id: str,
        progress: int,
        message: str | None = None,
        trace_id: str | None = None,
    ) -> bool:
        """把任务进度转成通知（`docs/02` §45 的**唯一**接入点）。

        Args:
            task_id: 任务标识（`tasks.id`）。
            progress: 0–100 的进度（唯一来源是 Task Engine，`docs/07` §10.2）。
            message: 可选的人类可读说明（`docs/02` §32）。
            trace_id: 可选链路标识（`docs/02` §12）。

        Returns:
            同 `notify()`：投递成功 `True`，否则 `False`（**不**抛出）。
        """
        payload: dict[str, Any] = {
            "task_id": task_id,
            "progress": progress,
            "message": message,
        }
        return await self.notify(
            NotificationMessage(
                channel=self._channel,
                event_type=TASK_PROGRESS_EVENT_TYPE,
                payload=payload,
                trace_id=trace_id,
                task_id=task_id,
            )
        )

    def subscribe(self, bus: EventBus) -> None:
        """订阅 Domain 的 `TaskProgress` 事件（`docs/02` §45；见模块裁决 3）。

        Args:
            bus: Domain 契约 `EventBus`（`docs/02` §34）；实现可替换为 Redis /
                NATS / Kafka 而不改本方法。

        ⚠️ 这是「TaskProgress → 通知」的**唯一**订阅点：任何其它模块都**不得**
        再订阅同一事件做通知，否则会出现重复投递（`docs/02` §28 的
        「只允许一处实现」同理）。
        """
        outcome = bus.subscribe(TaskProgress, self._handle_task_progress)
        if inspect.isawaitable(outcome):
            _schedule(outcome)

    def delivered(self) -> tuple[NotificationMessage, ...]:
        """已成功投递的通知（按投递顺序；见模块裁决 1）。"""
        return tuple(self._delivered)

    def failures(self) -> tuple[str, ...]:
        """失败的通道名（按发生顺序；未知通道与出口异常都记在这里）。"""
        return tuple(self._failures)

    async def _handle_task_progress(self, event: DomainEvent) -> None:
        """把 `TaskProgress` 事件转成通知（唯一转发实现；见模块裁决 3 / 4）。"""
        if not isinstance(event, TaskProgress):
            return
        await self.notify_task_progress(
            task_id="" if event.task_id is None else str(event.task_id),
            progress=event.progress,
            message=event.message,
        )


async def _await_outcome(outcome: Awaitable[None]) -> None:
    """把 `EventBus.subscribe()` 的 awaitable 跑完（见模块裁决 3）。"""
    await outcome


def _schedule(outcome: Awaitable[None]) -> None:
    """在当前事件循环上调度订阅（无运行中的循环时立即执行；见模块裁决 3）。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_await_outcome(outcome))
        return
    loop.create_task(_await_outcome(outcome))
