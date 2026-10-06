"""Infrastructure · Events（`docs/07` §3.3 冻结结构；`docs/02` §5 / §6 / §34 / §38 / §42）。

| 文件 | 内容 | 规范 |
| --- | --- | --- |
| `bus.py` | 标准事件清单、事件 ↔ Outbox 映射、进程内 Outbox | `docs/02` §5–§6 / §34 / §38 |
| `in_process.py` | `InProcessEventBus`（Core Alpha 的唯一总线实现） | `docs/02` §5.2 / §58 |
| `dispatcher.py` | `EventDispatcher`（retry / backoff / dead-letter） | `docs/02` §42 / §54 |

🔴 事件的**定义**在 `app/domain/events.py`（P03 冻结）：替换总线实现
（Redis / NATS / Kafka）**不改** Domain Event（`docs/02` §38），
故本包只提供「投递」与「Outbox」，不定义事件。

分层红线（`docs/07` §14.1 / §14.2）：本包只依赖标准库与 `app.domain`；
**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖 `app.application` /
`app.interfaces`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from app.infrastructure.events.bus import (
    EVENT_CLASSES,
    EVENT_STAGE,
    PAYLOAD_EXCLUDED_FIELDS,
    STANDARD_EVENT_TYPES,
    InMemoryEventRecordStore,
    event_payload,
    event_type_of,
    from_record,
    is_standard,
    to_record_draft,
)
from app.infrastructure.events.dispatcher import (
    DEFAULT_BACKOFF_SECONDS,
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_ATTEMPTS,
    DISPATCHER_STAGE,
    DispatchReport,
    EventDispatcher,
)
from app.infrastructure.events.in_process import IN_PROCESS_STAGE, InProcessEventBus

__all__ = [
    "DEFAULT_BACKOFF_SECONDS",
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_MAX_ATTEMPTS",
    "DISPATCHER_STAGE",
    "EVENT_CLASSES",
    "EVENT_STAGE",
    "IN_PROCESS_STAGE",
    "PAYLOAD_EXCLUDED_FIELDS",
    "STANDARD_EVENT_TYPES",
    "DispatchReport",
    "EventDispatcher",
    "InMemoryEventRecordStore",
    "InProcessEventBus",
    "event_payload",
    "event_type_of",
    "from_record",
    "is_standard",
    "to_record_draft",
]
