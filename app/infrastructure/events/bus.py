"""Infrastructure · Events · 事件类型与 Outbox（`docs/02` §5.1–§5.4 / §6 / §34 / §38 / §42 / §58）。

权威来源
--------
- `docs/02` §5.1（`DomainEvent`）/ §5.3 / §34 / §38 —— 标准事件清单（9 个）：
  `TaskCreated` / `TaskStarted` / `TaskProgress` / `TaskCompleted` / `TaskFailed` /
  `TaskCancelled` / `AdapterConnected` / `AdapterDisconnected` / `ModelChanged`。
  事件类本身在 `app/domain/events.py`（Domain 层，**不**因总线实现变化而改，§38）。
- `docs/02` §5.4（Event 与事务）—— **禁止**「DB COMMIT ↓ publish」；推荐
  「事务 ↓ 写业务数据 ↓ 写 Outbox / Event Record ↓ COMMIT ↓ Event Dispatcher ↓ publish」。
  原文明确：「如果本阶段暂不实现完整 Outbox，则必须在代码层明确其为 Alpha 限制，
  并保留迁移接口」。
- `docs/02` §6（Event Record / Outbox）—— `EventRecord` 的列集合与三态
  `PENDING` / `PUBLISHED` / `FAILED`（`app.domain.enums.EventRecordStatus`）。
- `docs/02` §42（Event Dispatcher）—— `pending(limit)` / `mark_published` /
  `mark_failed`，以及 `attempts++` / `retry` / `backoff` / `dead-letter`。
- `docs/02` §58（Event Bus）—— 第一阶段只用进程内实现。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **`event_records` 表不建**（**Alpha 限制**）：`docs/02` §6 的 `event_records` 不在
   `docs/07` §4.3 的 **24 张表**内，而本批「**不得改表**」（`docs/07` §14.3）。
   `docs/02` §5.4 恰好允许「暂不实现完整 Outbox，但必须明确记为 Alpha 限制并保留迁移接口」，
   故 `InMemoryEventRecordStore` 是本批的 Core Alpha 实现：进程内、接口与 §6 的列
   一一对应，需要持久化时以 **Alembic 迁移**新增表并实现同一个 Domain 契约
   `EventRecordStore`（`app/domain/protocols.py`）。
2. **`payload_json` 只放非敏感字段**（`docs/07` §14.3）：`event_payload` 从事件的
   dataclass 字段生成，**丢弃**任何键名敏感（`looks_sensitive`）的字段；
   `event_id` / `occurred_at` / `task_id` / `error_code` 是允许的记录项。
3. **`attempts` 在每次投递尝试时 +1**（`docs/02` §42 的 `attempts++`）：`mark_published`
   与 `mark_failed` 都递增 —— 一次成功的首次投递后 `attempts == 1`。
4. **`pending` 排除 `PUBLISHED`**（`docs/02` §6）：`FAILED` 记录**仍**会被重投，
   直到 `attempts` 达到 `EventDispatcher.max_attempts` 才成为 dead letter ——
   「失败即永久放弃」会让一次瞬时故障永久丢事件。
5. **`to_record_draft` 的五个可选 id 可回落到事件自身**：`DomainEvent`（P03 冻结）
   只有 `event_id` / `occurred_at`，租户 / 请求 / 链路标识在事件**没有**这些字段时
   只能是 `None`（**不**编造）。调用方（`ExecutionService`）显式传入时以调用方为准。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，
**不**依赖 `app.application` / `app.interfaces`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Final
from uuid import UUID, uuid4

from app.domain.enums import EventRecordStatus
from app.domain.errors import InternalError
from app.domain.events import (
    AdapterConnected,
    AdapterDisconnected,
    DomainEvent,
    ModelChanged,
    TaskCancelled,
    TaskCompleted,
    TaskCreated,
    TaskFailed,
    TaskProgress,
    TaskStarted,
)
from app.domain.protocols import EventRecordDraft, EventRecordSnapshot

__all__ = [
    "EVENT_CLASSES",
    "EVENT_STAGE",
    "PAYLOAD_EXCLUDED_FIELDS",
    "STANDARD_EVENT_TYPES",
    "InMemoryEventRecordStore",
    "event_payload",
    "event_type_of",
    "from_record",
    "is_standard",
    "to_record_draft",
]

EVENT_STAGE: Final[str] = "event"
"""错误 `details.stage` 的固定取值。"""

STANDARD_EVENT_TYPES: Final[tuple[str, ...]] = (
    "TaskCreated",
    "TaskStarted",
    "TaskProgress",
    "TaskCompleted",
    "TaskFailed",
    "TaskCancelled",
    "AdapterConnected",
    "AdapterDisconnected",
    "ModelChanged",
)
"""Core Alpha 的标准事件清单（`docs/02` §5.3 / §34 / §38，逐字照抄，共 9 个）。"""

EVENT_CLASSES: Final[Mapping[str, type[DomainEvent]]] = {
    "TaskCreated": TaskCreated,
    "TaskStarted": TaskStarted,
    "TaskProgress": TaskProgress,
    "TaskCompleted": TaskCompleted,
    "TaskFailed": TaskFailed,
    "TaskCancelled": TaskCancelled,
    "AdapterConnected": AdapterConnected,
    "AdapterDisconnected": AdapterDisconnected,
    "ModelChanged": ModelChanged,
}
"""事件名 → 事件类（`docs/02` §5.3 的清单与 `app/domain/events.py` 的类一一对应）。"""

PAYLOAD_EXCLUDED_FIELDS: Final[tuple[str, ...]] = ("event_id",)
"""不进入 `payload_json` 的字段（`event_id` 由 `to_record_draft` 单独承载为 `id` 之外的元数据）。

⚠️ 这里排除的是**冗余**而非敏感字段：`event_id` 与 Outbox 主键语义重叠，
保留它只会让同一事件有两种标识；`occurred_at` 反而**必须**保留（`docs/02` §5.1）。
"""


def event_type_of(event: DomainEvent) -> str:
    """事件类型名（= 类名；`docs/02` §5.1 的 `event_type: str`）。"""
    return type(event).__name__


def is_standard(event_type: str) -> bool:
    """该事件名是否在 `docs/02` §5.3 的标准清单内。"""
    return event_type in EVENT_CLASSES


def _jsonable(value: Any) -> Any:
    """把值确定性地转成 JSON 可序列化形式（只做类型转换，不改取值）。"""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_jsonable(item) for item in value]
    return str(value)


def _sensitive(name: str) -> bool:
    """键名是否敏感（`docs/07` §14.3；延迟导入以免 Infrastructure 反向依赖）。

    `app.infrastructure.secrets.base` 与本模块同层，故直接导入即可；
    但它**不**依赖本模块，因此没有环。
    """
    from app.infrastructure.secrets.base import looks_sensitive

    return looks_sensitive(name)


def event_payload(event: DomainEvent) -> dict[str, Any]:
    """事件 → 可落库的载荷映射（`docs/02` §6 的 `payload_json` 内容）。

    只包含事件的 dataclass 字段（`event_id` 除外），**丢弃**任何键名敏感的字段
    （`docs/07` §14.3：绝不记录 secret）。
    """
    payload: dict[str, Any] = {"event_id": str(event.event_id)}
    occurred_at = getattr(event, "occurred_at", None)
    if occurred_at is not None:
        payload["occurred_at"] = _jsonable(occurred_at)
    if is_dataclass(event):
        for field in fields(event):
            if field.name in PAYLOAD_EXCLUDED_FIELDS or field.name == "occurred_at":
                continue
            if _sensitive(field.name):
                continue
            payload[field.name] = _jsonable(getattr(event, field.name))
    return payload


def to_record_draft(
    event: DomainEvent,
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
    task_id: str | None = None,
) -> EventRecordDraft:
    """事件 → Outbox 草稿（`docs/02` §6 / §5.4）。

    五个可选 id 缺省时回落到事件自身的同名属性（`getattr`），事件没有该字段就是
    `None` —— **不**编造标识（见模块裁决 5）。
    """
    return EventRecordDraft(
        event_type=event_type_of(event),
        payload_json=json.dumps(
            event_payload(event),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ),
        tenant_id=_resolve_id(tenant_id, event, "tenant_id"),
        project_id=_resolve_id(project_id, event, "project_id"),
        request_id=_resolve_id(request_id, event, "request_id"),
        trace_id=_resolve_id(trace_id, event, "trace_id"),
        task_id=_resolve_id(task_id, event, "task_id"),
    )


def _resolve_id(explicit: str | None, event: DomainEvent, name: str) -> str | None:
    """解析 Outbox 记录的一个标识：显式值优先，否则回落到事件自身（见模块裁决 5）。"""
    if explicit is not None:
        return explicit
    return _as_str(getattr(event, name, None))


def from_record(record: EventRecordSnapshot) -> DomainEvent:
    """Outbox 记录 → 事件（`docs/02` §42 的 `to_domain_event`）。

    Raises:
        InternalError: `STRUCTAI-7000` —— 事件名不在标准清单内
            （`reason = "unknown_event_type"`），或载荷不是合法 JSON 对象
            （`reason = "corrupt_payload"`）。**不**静默丢弃、**不**臆造事件。
    """
    event_class = EVENT_CLASSES.get(record.event_type)
    if event_class is None:
        raise InternalError(
            "Event record carries an unknown event type",
            details={"stage": EVENT_STAGE, "reason": "unknown_event_type"},
        )
    try:
        parsed: Any = json.loads(record.payload_json)
    except json.JSONDecodeError as error:
        raise InternalError(
            "Event record payload is not valid JSON",
            details={"stage": EVENT_STAGE, "reason": "corrupt_payload"},
            cause=error,
        ) from error
    if not isinstance(parsed, Mapping):
        raise InternalError(
            "Event record payload is not a JSON object",
            details={"stage": EVENT_STAGE, "reason": "corrupt_payload"},
        )
    kwargs: dict[str, Any] = {}
    if is_dataclass(event_class):
        declared = {field.name for field in fields(event_class)}
        for key, value in parsed.items():
            name = str(key)
            if name in declared and name not in {"event_id", "occurred_at"}:
                kwargs[name] = _coerce(value, event_class, name)
    event_id = _as_uuid(parsed.get("event_id"))
    occurred_at = _as_datetime(parsed.get("occurred_at"))
    return event_class(
        event_id=event_id or uuid4(),
        occurred_at=occurred_at or datetime.now(UTC),
        **kwargs,
    )


def _coerce(value: Any, event_class: type[DomainEvent], name: str) -> Any:
    """把载荷值还原成声明类型（只处理 UUID / int / str 三种实际出现的形态）。"""
    declared = {field.name: field.type for field in fields(event_class)}
    annotation = str(declared.get(name, ""))
    if "UUID" in annotation and isinstance(value, str):
        return _as_uuid(value) or value
    if "int" in annotation and isinstance(value, str) and value.isdigit():
        return int(value)
    return value


def _as_str(value: Any) -> str | None:
    """任意标识 → `str | None`（`None` 原样返回）。"""
    return None if value is None else str(value)


def _as_uuid(value: Any) -> UUID | None:
    """UUID 字符串 → `UUID`；非法 / 缺失 → `None`（**不**抛异常）。"""
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _as_datetime(value: Any) -> datetime | None:
    """ISO-8601 文本 → **带时区**的 `datetime`；非法 / 缺失 → `None`。"""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


class InMemoryEventRecordStore:
    """Outbox 的**进程内**实现（`docs/02` §6 / §42；见模块裁决 1 的 Alpha 限制）。

    ⚠️ 只读 / 只写自身状态，**从不** `commit` / `rollback`（`docs/02` §16）。
    """

    def __init__(self, *, clock: Any = None) -> None:
        """建立空 Outbox。

        Args:
            clock: 可选的 `Callable[[], datetime]`（测试注入用）；缺省用 UTC 当前时间。
        """
        self._clock = clock if clock is not None else (lambda: datetime.now(UTC))
        self._records: list[EventRecordSnapshot] = []

    async def append(self, draft: EventRecordDraft) -> EventRecordSnapshot:
        """追加一条 `PENDING` 记录（`docs/02` §6）。"""
        record = EventRecordSnapshot(
            id=str(uuid4()),
            event_type=draft.event_type,
            payload_json=draft.payload_json,
            status=str(EventRecordStatus.PENDING),
            attempts=0,
            created_at=self._clock(),
            published_at=None,
            tenant_id=draft.tenant_id,
            project_id=draft.project_id,
            request_id=draft.request_id,
            trace_id=draft.trace_id,
            task_id=draft.task_id,
        )
        self._records.append(record)
        return record

    async def pending(self, *, limit: int = 100) -> Sequence[EventRecordSnapshot]:
        """待投递记录（**排除** `PUBLISHED`；`docs/02` §6 / §42）。"""
        pending = [
            record for record in self._records if record.status != str(EventRecordStatus.PUBLISHED)
        ]
        pending.sort(key=lambda record: (record.created_at, record.id))
        return tuple(pending[:limit])

    async def mark_published(self, record_id: str) -> bool:
        """标记为 `PUBLISHED` 并 `attempts += 1`（`docs/02` §42）。"""
        return self._replace(
            record_id,
            status=str(EventRecordStatus.PUBLISHED),
            published_at=self._clock(),
        )

    async def mark_failed(self, record_id: str) -> bool:
        """标记为 `FAILED` 并 `attempts += 1`（`docs/02` §42）。"""
        return self._replace(record_id, status=str(EventRecordStatus.FAILED))

    async def count(self) -> int:
        """记录总数（健康 / 诊断用）。"""
        return len(self._records)

    def records(self) -> tuple[EventRecordSnapshot, ...]:
        """全部记录的只读快照（验收断言用）。"""
        return tuple(self._records)

    def _replace(
        self,
        record_id: str,
        *,
        status: str,
        published_at: datetime | None = None,
    ) -> bool:
        """按主键替换一条记录的状态（**唯一**的写路径）。"""
        for index, record in enumerate(self._records):
            if record.id != record_id:
                continue
            self._records[index] = EventRecordSnapshot(
                id=record.id,
                event_type=record.event_type,
                payload_json=record.payload_json,
                status=status,
                attempts=record.attempts + 1,
                created_at=record.created_at,
                published_at=published_at if published_at is not None else record.published_at,
                tenant_id=record.tenant_id,
                project_id=record.project_id,
                request_id=record.request_id,
                trace_id=record.trace_id,
                task_id=record.task_id,
            )
            return True
        return False
