"""任务与任务步骤（`docs/07` §4.3 #19 / #20；`docs/02` §24 / §10 / §52）。

表名 `tasks` / `task_steps`。

字段口径：

- `tasks` —— 照抄 `docs/02` §10「Task ORM」的完整字段集（含 `lease_owner` /
  `lease_until` / `heartbeat_at` / `retry_count` / `max_retries` /
  `cancel_requested` / `priority` / `error_json` / `result_json` /
  `started_at` / `completed_at`），并叠加 `TimestampMixin` 与 `VersionMixin`。
  `docs/07` §4.3 #19 的关键字段与之逐项对应：

  | `docs/07` §4.3 | 本表 |
  | --- | --- |
  | `task_id` | 主键 `id`（UUID 字符串） |
  | `status` / `progress` / `trace_id` / `version` | 同名列 |
  | `lease_owner` / `lease_until` | 同名列 |
  | `last_heartbeat` | `heartbeat_at`（`docs/02` §10 源码级列名） |

- `task_steps` —— 照抄 `docs/02` §52「Task Step ORM」；`docs/07` §4.3 #20 的
  `depends_on`（DAG）对应本表的 `depends_on_json`。

状态机与租约语义（`docs/02` §4 状态转换 / §34 Lease / §40 Recovery）由 P22–P28
实现；本批次只建立 persistence 结构。⚠️ 恢复中的 Task 不得直接标记 `COMPLETED`
（`docs/07` §14.4），该约束由状态机保证，不靠数据库默认值。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionMixin,
)

__all__ = ["TaskModel", "TaskORM", "TaskStepModel", "TaskStepORM"]


class TaskORM(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    """异步任务（`docs/07` §4.3 #19；`docs/02` §10）。

    - `status` 取值见 `app.domain.enums.TaskStatus`（12 态，`docs/07` §10.1）。
    - `priority` 取值见 `app.domain.enums.TaskPriority`；队列按
      `priority` + `created_at` 排序（`docs/02` §17）。
    - `lease_owner` / `lease_until` / `heartbeat_at` 支撑租约与崩溃恢复
      （`docs/02` §34–§38）；租约更新必须是原子条件更新。
    """

    __tablename__ = "tasks"

    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), index=True)

    request_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    trace_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    tool: Mapped[str] = mapped_column(String(100), nullable=False)
    operation: Mapped[str] = mapped_column(String(200), nullable=False)

    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False, index=True)

    error_json: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskStepORM(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """任务步骤（DAG 节点，`docs/07` §4.3 #20；`docs/02` §52）。

    `depends_on_json` 为前置步骤 key 的 JSON 数组；DAG 环检测与并行调度
    见 `docs/02` §46–§51（P22–P28）。
    """

    __tablename__ = "task_steps"

    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    step_key: Mapped[str] = mapped_column(String(100), nullable=False)
    operation: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    parameters_json: Mapped[str] = mapped_column(Text, nullable=False)
    depends_on_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str | None] = mapped_column(Text)
    error_json: Mapped[str | None] = mapped_column(Text)


TaskModel = TaskORM
"""`docs/07` §4.3 使用的类名；与 `TaskORM` 是同一个类。"""

TaskStepModel = TaskStepORM
"""`docs/07` §4.3 使用的类名；与 `TaskStepORM` 是同一个类。"""
