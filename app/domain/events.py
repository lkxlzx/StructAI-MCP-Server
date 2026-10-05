"""Domain Events —— 领域事件（`docs/02` §12；`docs/02` §34 / §38）。

权威来源：

- `docs/02` §12（`source7` §12）—— `DomainEvent(event_id, occurred_at)` 与
  `create()` 工厂，以及 `ModelChanged` / `AdapterConnected` / `AdapterDisconnected`，
  字段逐项照抄。
- `docs/02` §34（`impl`）/ §38（`py`）—— Core Alpha 事件清单：
  `TaskCreated` / `TaskStarted` / `TaskProgress` / `TaskCompleted` / `TaskFailed` /
  `TaskCancelled` / `AdapterConnected` / `AdapterDisconnected` / `ModelChanged`。
  规范只给出事件名，未给出字段；任务类事件的字段按最小需求推导（见各类注释）。
- `docs/02` §38 —— 事件总线实现（`InProcessEventBus`）可被替换为 Redis / NATS / Kafka
  **而不修改 Domain Event**，故本文件只定义数据，不定义分发。

分层红线（`docs/07` §14.1；`docs/02` §6）：只依赖标准库，不得引用任何 ORM / Web 框架 /
MCP SDK / HTTP 客户端，也不得出现厂商专属内容。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Self
from uuid import UUID, uuid4

__all__ = [
    "AdapterConnected",
    "AdapterDisconnected",
    "DomainEvent",
    "ModelChanged",
    "TaskCancelled",
    "TaskCompleted",
    "TaskCreated",
    "TaskFailed",
    "TaskProgress",
    "TaskStarted",
]


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """所有领域事件的基类（`docs/02` §12）。

    事件是不可变的（`frozen=True`）：`event_id` / `occurred_at` 由 `create()`
    在服务端生成，客户端不得构造。
    """

    event_id: UUID
    occurred_at: datetime

    @classmethod
    def create(cls, **payload: Any) -> Self:
        """生成带新 `event_id` 与当前 UTC 时间的事件（`docs/02` §12）。

        规范签名为 `create(cls)`；此处**向前兼容地**接受 `**payload`，把子类
        新增字段（如 `ModelChanged.model_id`）一并传入——否则冻结的 payload
        字段无法在工厂中赋值。`DomainEvent.create()` 的原有调用形式不变。
        """
        return cls(
            event_id=uuid4(),
            occurred_at=datetime.now(UTC),
            **payload,
        )


@dataclass(frozen=True, slots=True)
class ModelChanged(DomainEvent):
    """模型发生变更（`docs/02` §12）。"""

    model_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AdapterConnected(DomainEvent):
    """Adapter 连接成功（`docs/02` §12）。"""

    software_instance_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AdapterDisconnected(DomainEvent):
    """Adapter 断开（`docs/02` §12）。"""

    software_instance_id: UUID | None = None


# ===== 任务事件（`docs/02` §34 / §38 只给出事件名，字段为最小推导）=====


@dataclass(frozen=True, slots=True)
class TaskCreated(DomainEvent):
    """任务已创建（`docs/02` §34）。"""

    task_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class TaskStarted(DomainEvent):
    """任务开始执行（`docs/02` §34）。"""

    task_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class TaskProgress(DomainEvent):
    """任务进度更新（`docs/02` §34）。

    `progress` 为 0–100 的百分比，与 `TaskModel.progress` 同口径（`docs/07` §4.3）。
    """

    task_id: UUID | None = None
    progress: int = 0


@dataclass(frozen=True, slots=True)
class TaskCompleted(DomainEvent):
    """任务完成（`docs/02` §34）。"""

    task_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class TaskFailed(DomainEvent):
    """任务失败（`docs/02` §34）。

    `error_code` 取 20 码契约之一（`docs/07` §11）；不得携带 secret
    （`docs/07` §14.3）。
    """

    task_id: UUID | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class TaskCancelled(DomainEvent):
    """任务被取消（`docs/02` §34）。"""

    task_id: UUID | None = None
