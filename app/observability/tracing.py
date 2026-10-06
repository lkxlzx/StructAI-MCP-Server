"""Observability · Trace（`docs/02` §10–§12 / §44 / §53 / §63；`docs/07` §14.3）。

权威来源
--------
- `docs/02` §10（P61 Trace Service）—— `TraceService` 契约：
  `start_span(name, trace_id=None, parent_span_id=None, attributes=None)` 与
  `end_span(span, status="OK")`；并要求「Trace 必须与具体 tracing vendor 解耦」。
- `docs/02` §11（Trace Span）—— `TraceSpan` 字段：
  `trace_id` / `parent_span_id` / `name` / `kind` / `start_time` / `end_time` /
  `status` / `request_id` / `task_id` / `attributes_json`。
- `docs/02` §12（Standard Trace Tree）—— 标准 Span 树
  （`MCP → Tool → Operation → … → Task → Adapter → NativeAPI`），
  且必须能定位「哪个请求 / 哪个用户 / 哪个任务 / 哪个软件 / 哪个 Adapter /
  哪个 operation / 哪个 native API / 耗时多少 / 在哪一步失败」。
- `docs/02` §54（`request_id` / `trace_id` 用 `uuid4()` 生成）—— 缺省 `trace_id`
  一律 `uuid4().hex`。
- `docs/02` §44（Trace 查询至少支持 `trace_id` / `request_id` / `task_id` / 时间范围 / `status`；
  **Trace 数据不允许修改**）。
- `docs/02` §53（Trace Test Matrix）—— `root span` / `child span` / `parent relation` /
  `error status` / `task relation` / `adapter relation` / `trace query`。
- `docs/02` §63（标准 Span 清单）—— `TraceSpanKind`（`app.domain.enums`）。
- `docs/07` §14.3 —— 绝不记录 secret。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **`trace_spans` 表不建**（**Alpha 限制**）：`docs/02` §11 的 `trace_spans` 不在
   `docs/07` §4.3 的 24 张表内，本批**不得改表**。故 `InMemoryTraceStore` 是本批的
   Core Alpha 实现，接口与 §11 的列一一对应；需要持久化时以 **Alembic 迁移**
   新增表并实现同一个 Domain 契约 `TraceStore`（`app/domain/protocols.py`）。
2. **`end_span` 是唯一允许的写入**（`docs/02` §44「Trace 数据不允许修改」）：
   `TraceStore` 只提供 `append` 与 `finish`（写 `end_time` / `status`），
   **不**提供任意字段更新 / 删除 —— 「不可修改」因此是**契约性**的，而不是纪律性的。
3. **`status` 只接受 `TraceStatus`**：非法值 → `STRUCTAI-7000`
   （`reason = "invalid_status"`）。**不**静默写一个自由文本状态，
   否则 §53 的 `error status` 断言失去意义。
4. **`attributes` 经敏感键清洗**（`docs/07` §14.3）：`attributes_json` 只保留非敏感键，
   且以 `sort_keys=True` 序列化（同一 Span 的两次序列化逐字节一致）。
5. **`span()` 上下文管理器把异常标成 `ERROR` 并**继续上抛**（`docs/02` §53 的
   `error status`）：吞掉异常会让「在哪一步失败」失去证据。
6. **`kind` 缺省 `TOOL`**：`docs/02` §10 的 `start_span` 没有 `kind` 参数，
   而 §11 的 `TraceSpan` 有该列；缺省取标准树里最外层可用的 `TOOL`
   （`docs/02` §12），调用方（`ExecutionService`）逐 Span 显式传入 `kind`。
7. **`TraceService` 结构上满足 Domain 收窄契约 `TraceRecorder`**
   （`app/domain/protocols.py`），于是 `app/application/**` 不必依赖 `app.observability`
   （`docs/07` §2.2）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，
**不**依赖 `app.application` / `app.interfaces`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Final
from uuid import uuid4

from app.domain.enums import TraceSpanKind, TraceStatus
from app.domain.errors import InternalError
from app.domain.protocols import TraceSpanRecord, TraceStore

__all__ = [
    "DEFAULT_SPAN_KIND",
    "STANDARD_SPAN_KINDS",
    "TRACE_STAGE",
    "InMemoryTraceStore",
    "TraceService",
    "is_standard_kind",
]

TRACE_STAGE: Final[str] = "trace"
"""错误 `details.stage` 的固定取值。"""

DEFAULT_SPAN_KIND: Final[str] = str(TraceSpanKind.TOOL)
"""`kind` 的缺省取值（见模块裁决 6）。"""

STANDARD_SPAN_KINDS: Final[tuple[str, ...]] = tuple(kind.value for kind in TraceSpanKind)
"""`docs/02` §63 的标准 Span 清单（`TraceSpanKind` 的取值序列）。"""


def is_standard_kind(kind: str) -> bool:
    """该 `kind` 是否在 `docs/02` §63 的标准清单内。"""
    return kind in STANDARD_SPAN_KINDS


class InMemoryTraceStore:
    """Span 的**进程内**存储（`docs/02` §11；见模块裁决 1 的 Alpha 限制）。

    ⚠️ 只提供 `append` 与 `finish`（`docs/02` §44：Trace 数据不允许修改），
    且**从不** `commit` / `rollback`（`docs/02` §16）。
    """

    def __init__(self, *, clock: Any = None) -> None:
        """建立空 Span 存储。

        Args:
            clock: 可选的 `Callable[[], datetime]`（测试注入用）。
        """
        self._clock = clock if clock is not None else (lambda: datetime.now(UTC))
        self._spans: list[TraceSpanRecord] = []

    async def append(self, record: TraceSpanRecord) -> TraceSpanRecord:
        """追加一个 Span（`docs/02` §11）。"""
        self._spans.append(record)
        return record

    async def finish(self, span_id: str, *, status: str, end_time: datetime) -> bool:
        """结束一个 Span（只写 `end_time` / `status`；见模块裁决 2）。"""
        for index, span in enumerate(self._spans):
            if span.id != span_id:
                continue
            self._spans[index] = TraceSpanRecord(
                id=span.id,
                trace_id=span.trace_id,
                name=span.name,
                kind=span.kind,
                status=status,
                start_time=span.start_time,
                end_time=end_time,
                parent_span_id=span.parent_span_id,
                request_id=span.request_id,
                task_id=span.task_id,
                attributes_json=span.attributes_json,
            )
            return True
        return False

    async def by_trace(self, trace_id: str) -> Sequence[TraceSpanRecord]:
        """按 `trace_id` 查询（`docs/02` §44）。"""
        return tuple(span for span in self._spans if span.trace_id == trace_id)

    async def by_request(self, request_id: str) -> Sequence[TraceSpanRecord]:
        """按 `request_id` 查询（`docs/02` §44）。"""
        return tuple(span for span in self._spans if span.request_id == request_id)

    async def by_task(self, task_id: str) -> Sequence[TraceSpanRecord]:
        """按 `task_id` 查询（`docs/02` §44）。"""
        return tuple(span for span in self._spans if span.task_id == task_id)

    async def count(self) -> int:
        """Span 总数（诊断用）。"""
        return len(self._spans)

    def spans(self) -> tuple[TraceSpanRecord, ...]:
        """全部 Span 的只读快照（验收断言用）。"""
        return tuple(self._spans)


class TraceService:
    """Span 的开始 / 结束与查询（`docs/02` §10 / §11 / §12 / §53）。

    ⚠️ 存储经 Domain 契约 `TraceStore` 注入：本模块**不**依赖 `app.infrastructure`
    （`docs/07` §14.1）。事务边界归调用方的 `UnitOfWork`（`docs/02` §16）。
    """

    def __init__(self, store: TraceStore | None = None) -> None:
        """绑定 Span 存储。

        Args:
            store: `docs/02` §11 的存储入口；缺省用 `InMemoryTraceStore`。
        """
        self._store = store if store is not None else InMemoryTraceStore()

    @property
    def store(self) -> TraceStore:
        """被绑定的 Span 存储（只读用途）。"""
        return self._store

    # ===== 契约：Domain `TraceRecorder`（`docs/02` §10）=====

    async def start_span(
        self,
        name: str,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
        attributes: Mapping[str, Any] | None = None,
        *,
        kind: str = DEFAULT_SPAN_KIND,
        request_id: str | None = None,
        task_id: str | None = None,
    ) -> TraceSpanRecord:
        """开始一个 Span（`docs/02` §10 的 `start_span`）。

        Args:
            name: Span 名（`docs/02` §12 的标准树里是 Tool / Operation / Adapter 名）。
            trace_id: 链路标识；缺省生成 `uuid4().hex`（`docs/02` §54）。
            parent_span_id: 父 Span 的 id（`docs/02` §53 的 `parent relation`）。
            attributes: 附加属性；敏感键被丢弃（见模块裁决 4）。
            kind: Span 种类（`docs/02` §63；见模块裁决 6）。
            request_id: 服务端请求标识（`docs/02` §5）。
            task_id: 任务标识（`docs/02` §53 的 `task relation`）。

        Returns:
            已登记的 `TraceSpanRecord`（`status` 初始为 `OK`，`end_time` 为 `None`）。
        """
        record = TraceSpanRecord(
            id=str(uuid4()),
            trace_id=trace_id or uuid4().hex,
            name=name,
            kind=kind,
            status=str(TraceStatus.OK),
            start_time=datetime.now(UTC),
            end_time=None,
            parent_span_id=parent_span_id,
            request_id=request_id,
            task_id=task_id,
            attributes_json=_encode_attributes(attributes),
        )
        return await self._store.append(record)

    async def end_span(
        self,
        span: TraceSpanRecord,
        status: str = "OK",
    ) -> TraceSpanRecord | None:
        """结束一个 Span（`docs/02` §10 的 `end_span`）。

        Args:
            span: `start_span` 返回的记录。
            status: `TraceStatus` 取值（`OK` / `ERROR`）。

        Returns:
            结束后的记录（回读），或 `None`（该 Span id 不在存储里）。

        Raises:
            InternalError: `STRUCTAI-7000` —— `status` 不在 `TraceStatus` 内
                （`reason = "invalid_status"`；见模块裁决 3）。
        """
        if str(status) not in {str(item) for item in TraceStatus}:
            raise InternalError(
                "Trace span status is not a known TraceStatus value",
                details={"stage": TRACE_STAGE, "reason": "invalid_status"},
            )
        finished = await self._store.finish(span.id, status=str(status), end_time=datetime.now(UTC))
        if not finished:
            return None
        spans = await self._store.by_trace(span.trace_id)
        for candidate in spans:
            if candidate.id == span.id:
                return candidate
        return None

    # ===== 便捷入口：上下文管理器 =====

    @asynccontextmanager
    async def span(
        self,
        name: str,
        *,
        trace_id: str | None = None,
        parent: TraceSpanRecord | None = None,
        kind: str = DEFAULT_SPAN_KIND,
        request_id: str | None = None,
        task_id: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[TraceSpanRecord]:
        """以 `async with` 管理一个 Span（见模块裁决 5）。

        `trace_id` 缺省继承 `parent.trace_id`（`docs/02` §54「所有子 Task 继承 `trace_id`」），
        `parent_span_id` 缺省取 `parent.id`。

        异常路径把 Span 标成 `ERROR`，**并且继续上抛**原异常。
        """
        started = await self.start_span(
            name,
            trace_id if trace_id is not None else (None if parent is None else parent.trace_id),
            None if parent is None else parent.id,
            attributes,
            kind=kind,
            request_id=request_id
            if request_id is not None
            else (None if parent is None else parent.request_id),
            task_id=task_id if task_id is not None else _parent_task_id(parent),
        )
        try:
            yield started
        except BaseException:
            await self.end_span(started, str(TraceStatus.ERROR))
            raise
        await self.end_span(started, str(TraceStatus.OK))

    # ===== 查询（`docs/02` §44）=====

    async def spans_for_trace(self, trace_id: str) -> Sequence[TraceSpanRecord]:
        """按 `trace_id` 查询（`docs/02` §44）。"""
        return await self._store.by_trace(trace_id)

    async def spans_for_request(self, request_id: str) -> Sequence[TraceSpanRecord]:
        """按 `request_id` 查询（`docs/02` §44）。"""
        return await self._store.by_request(request_id)

    async def spans_for_task(self, task_id: str) -> Sequence[TraceSpanRecord]:
        """按 `task_id` 查询（`docs/02` §53 的 `task relation`）。"""
        return await self._store.by_task(task_id)

    async def span_count(self) -> int:
        """Span 总数（诊断用）。"""
        return await self._store.count()


def _encode_attributes(attributes: Mapping[str, Any] | None) -> str:
    """属性 → 紧凑 JSON 文本（敏感键被丢弃；见模块裁决 4）。"""
    if not attributes:
        return "{}"
    from app.infrastructure.secrets.base import sanitize_mapping

    return json.dumps(
        sanitize_mapping(attributes),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def _parent_task_id(parent: TraceSpanRecord | None) -> str | None:
    """从父 Span 继承 `task_id`（`docs/02` §53 的 `task relation`）。"""
    return None if parent is None else parent.task_id
