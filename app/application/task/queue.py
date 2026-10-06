"""Application · Task · Queue（`docs/07` §10.2 / §12 P22–P28；`docs/02` §11–§17 / §38 / §49）。

权威来源
--------
- `docs/02` §49（Task Scheduler）—— Core Alpha 用 `asyncio.Queue`；支持
  `priority` / `concurrency` / `software instance serialization`；未来可换
  Redis / RabbitMQ / NATS / Kafka，但 **Application Interface 不改变**。
- `docs/02` §11 / §13（Task Queue / TaskQueue）—— `asyncio.PriorityQueue`；
  `put(task_id, priority=100)` / `get()` / `task_done()` / `qsize()`；
  **不引入** Redis / Celery / RabbitMQ / Kafka（Core Alpha 先验证执行模型）。
- `docs/02` §12（Queue Item）—— `QueueItem(priority, sequence, task_id)`，
  `@dataclass(order=True, slots=True)`，`sequence` 由 `itertools.count()` 提供。
- `docs/02` §14（Priority）—— 建议映射 `0 CRITICAL / 10 HIGH / 50 NORMAL / 100 LOW`，
  数值越小优先级越高，并提示必须防止 `priority starvation`。
- `docs/02` §17（Task Priority）—— 「Queue 必须按 `priority` + `created_at` 排序」。
- `docs/02` §38（Task Queue）—— `TaskQueue.get()` 的返回与 `shutdown()`。
- `docs/03` §56（`docs/07` §11）—— **Queue Full → `STRUCTAI-5000`**（`retryable = true`）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **排序键 = `(priority, created_at, sequence)`**：`docs/02` §12 的 `QueueItem` 只有
   `sequence`（入队序号，等价于「入队顺序 FIFO」），而 §17 明确要求按
   `priority` + `created_at` 排序。二者在「入队顺序 == 创建顺序」时一致，但
   **恢复 / 重排**会让旧任务晚入队（`docs/02` §42 的 `REQUEUE`）：只按 `sequence`
   排会让「先创建、后重排」的任务插到「后创建」的任务之后，直接违反 §17。
   故排序键为 `(priority, created_at, sequence)` —— `created_at` 先于 `sequence`
   参与比较，`sequence` 只用于**同优先级且同创建时刻**时的 FIFO 兜底
   （即 §17 的「同优先级 FIFO」）。
2. **`get()` 返回 `QueueItem`（不是 `str`）**：`docs/02` §13（源码级写法）返回
   `QueueItem`，§38 的骨架写作 `-> str`。二者不冲突 —— `QueueItem` **包含**
   `task_id`（§12），是 §38 返回值的超集；`TaskWorker`（§15）需要的正是
   `item.task_id`。故保留更丰富的形状。
3. **有界队列 + 队列满落 `STRUCTAI-5000`**：`docs/02` §56 的「Queue Full →
   `STRUCTAI-5000`，`retryable = true`」是 20 码契约内的既有码（`docs/07` §11 的
   `TaskError`，其 `retryable` 已是 `True`）。`maxsize = 0` 表示**不设上限**
   （Core Alpha 默认，§11）；设了上限且已满时**拒绝入队**并抛 `TaskError`
   （**不**阻塞调用方 —— 阻塞会把「队列满」变成「请求挂住」）。
4. **`shutdown()` 不丢数据、不杀进程**：§38 的 `shutdown()` 只把队列标记为关闭
   （`closed`）；等待中的 `get()` 仍可正常取走已有项。`TaskWorker` 用
   `asyncio.wait_for(..., poll_interval)` 轮询 `closed`，因此**优雅停机**不需要
   杀死任何协程（`docs/07` §14.4：取消不得杀 Python 进程）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 SQLAlchemy / FastAPI / MCP SDK /
httpx，**不**依赖 `app.infrastructure`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import count
from types import MappingProxyType
from typing import Final

from app.domain.enums import TaskPriority
from app.domain.errors import TaskError

__all__ = [
    "DEFAULT_TASK_PRIORITY",
    "PRIORITY_LEVELS",
    "QUEUE_FULL_MESSAGE",
    "QueueItem",
    "TaskQueue",
    "priority_value",
]

PRIORITY_LEVELS: Final[Mapping[TaskPriority, int]] = MappingProxyType(
    {
        TaskPriority.CRITICAL: 0,
        TaskPriority.HIGH: 10,
        TaskPriority.NORMAL: 50,
        TaskPriority.LOW: 100,
    }
)
"""`docs/02` §14 的优先级建议映射（逐项照抄；数值越小优先级越高）。

⚠️ 落库口径：`tasks.priority` 是 `Integer`（`docs/07` §4.3 #19），P04 的列默认值
为 `100` —— 与 §14 的 `LOW` **逐值相同**，故本映射同时是「枚举 → 列值」的映射，
`DEFAULT_TASK_PRIORITY` 因此与表默认值一致（不会出现「建表用 100、入队用别的数」）。
"""

DEFAULT_TASK_PRIORITY: Final[int] = PRIORITY_LEVELS[TaskPriority.LOW]
"""默认优先级（`docs/02` §13 的 `priority: int = 100`；与 `tasks.priority` 默认值一致）。"""

QUEUE_FULL_MESSAGE: Final[str] = "Task queue is full"
"""队列满的对外消息（`docs/02` §56；落 `STRUCTAI-5000`）。"""


def priority_value(priority: TaskPriority | int | str) -> int:
    """把优先级规整为**整数**排序键（`docs/02` §14）。

    Args:
        priority: `TaskPriority` / 已映射的整数 / 枚举取值的字符串形式。

    Returns:
        `0` / `10` / `50` / `100` 之一（`TaskPriority` 输入），或原样整数。

    Raises:
        ValueError: 取值不是四个冻结优先级之一，也不是整数
            （装配 / 数据错误，**不**静默回落默认值）。
    """
    if isinstance(priority, TaskPriority):
        return PRIORITY_LEVELS[priority]
    if isinstance(priority, bool):  # bool 是 int 的子类，显式排除以免 True → 1
        raise ValueError(f"unsupported task priority: {priority!r}")
    if isinstance(priority, int):
        return priority
    return PRIORITY_LEVELS[TaskPriority(str(priority))]


@dataclass(order=True, slots=True)
class QueueItem:
    """队列项（`docs/02` §12；排序键见模块裁决 1）。

    比较字段（`order=True` 按声明顺序）：`priority` → `created_at` → `sequence`；
    `task_id` **不参与比较**（`compare=False`）—— 它只承载结果，字符串比较没有
    排序意义，且会让「同键不同任务」产生任意顺序。
    """

    priority: int
    created_at: datetime
    sequence: int
    task_id: str = field(compare=False)

    def __post_init__(self) -> None:
        """保证 `created_at` 为 UTC 感知时间（与 `tasks` 表口径一致）。"""
        if self.created_at.tzinfo is None:
            object.__setattr__(self, "created_at", self.created_at.replace(tzinfo=UTC))


class TaskQueue:
    """进程内优先级队列（`docs/02` §11 / §13 / §17 / §38 / §49）。

    ⚠️ **进程内**状态：Core Alpha 不引入 Redis / Celery / RabbitMQ / Kafka
    （`docs/02` §11）；替换实现时本类的公开接口不变（§49）。
    队列**不**写数据库：持久化状态在 `tasks` 表，队列只是「谁先被取走」的排序器
    （`docs/07` §14.4：Repository 不得自行 commit，队列亦不持有事务）。
    """

    def __init__(self, *, maxsize: int = 0) -> None:
        """初始化队列。

        Args:
            maxsize: 队列上限；`0`（默认）表示不设上限（`docs/02` §11）。
        """
        self._queue: asyncio.PriorityQueue[QueueItem] = asyncio.PriorityQueue(maxsize=maxsize)
        self._sequence = count()
        self._closed = False

    @property
    def closed(self) -> bool:
        """队列是否已关闭（`docs/02` §38 的 `shutdown()` 之后为 `True`）。"""
        return self._closed

    @property
    def maxsize(self) -> int:
        """队列上限（`0` = 不设上限）。"""
        return self._queue.maxsize

    def qsize(self) -> int:
        """当前排队项数（`docs/02` §13）。"""
        return self._queue.qsize()

    def empty(self) -> bool:
        """队列是否为空。"""
        return self._queue.empty()

    def __len__(self) -> int:
        """`qsize()` 的语法糖。"""
        return self._queue.qsize()

    # ===== `docs/02` §13 的接口 =====

    async def put(
        self,
        task_id: str,
        priority: TaskPriority | int | str = DEFAULT_TASK_PRIORITY,
        *,
        created_at: datetime | None = None,
    ) -> QueueItem:
        """入队（`docs/02` §13 的 `put(task_id, priority=100)`）。

        Args:
            task_id: 任务标识（`tasks.id`）。
            priority: 优先级（`TaskPriority` 或 §14 的整数；缺省 `100` = `LOW`）。
            created_at: 任务创建时刻（`docs/02` §17 的排序键）；缺省取当前 UTC 时间。
                恢复 / 重排路径**必须**传入 `tasks.created_at`，否则旧任务会排到
                新任务之后（见模块裁决 1）。

        Returns:
            实际入队的 `QueueItem`（含分配的 `sequence`）。

        Raises:
            TaskError: `STRUCTAI-5000` —— 队列已满（`docs/02` §56；`retryable = true`）。
            RuntimeError: 队列已 `shutdown()`（不再接受新任务；**不**静默丢弃）。
            ValueError: 优先级取值非法。
        """
        if self._closed:
            raise RuntimeError("TaskQueue is shut down; new tasks are not accepted")
        item = QueueItem(
            priority=priority_value(priority),
            created_at=created_at or datetime.now(UTC),
            sequence=next(self._sequence),
            task_id=str(task_id),
        )
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull as error:
            raise TaskError(
                QUEUE_FULL_MESSAGE,
                details={"stage": "queue", "reason": "full"},
                cause=error,
            ) from error
        return item

    async def get(self) -> QueueItem:
        """出队（阻塞直到有项；`docs/02` §13 / §38）。

        Returns:
            排序最小的 `QueueItem`（`priority` → `created_at` → `sequence`）。

        ⚠️ 调用方必须在处理完成后调用 `task_done()`（`docs/02` §13 / §15）。
        """
        return await self._queue.get()

    def get_nowait(self) -> QueueItem | None:
        """非阻塞出队；队列为空返回 `None`（`TaskWorker` 的优雅停机轮询用）。"""
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def task_done(self) -> None:
        """标记一个已取出的项处理完毕（`docs/02` §13）。"""
        self._queue.task_done()

    async def shutdown(self) -> None:
        """关闭队列（`docs/02` §38）。

        - 幂等；只标记关闭，**不**丢弃已有项（等待中的 `get()` 仍能取走它们）。
        - **不**取消任何协程、**不**杀任何进程（`docs/07` §14.4）。
        """
        self._closed = True

    def __repr__(self) -> str:
        """诊断表示（只含尺寸与关闭标志）。"""
        return f"TaskQueue(size={self.qsize()}, closed={self._closed})"
