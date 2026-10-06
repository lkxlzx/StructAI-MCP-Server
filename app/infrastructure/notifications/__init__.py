"""Infrastructure · Notifications 包导出（`docs/07` §3.3；`docs/02` §35 / §45 / §59）。

`docs/07` §3.3 冻结的结构：

    app/infrastructure/notifications/  service.py

本包是「TaskProgress → 通知」的唯一接入点（`docs/02` §45）与通道注册表
（`docs/02` §35 / §59：第一阶段只实现 `InProcess`）。

红线（`docs/07` §14.1 / §14.4）：本包只依赖标准库与 `app.domain`，**不** import
`app.infrastructure.events`（总线经 Domain 契约 `EventBus` 注入）；投递失败
**不得**影响业务结果（`notify()` 永不抛出）；通知载荷**不得**携带 secret。
"""

from __future__ import annotations

from app.infrastructure.notifications.service import (
    IN_PROCESS_CHANNEL,
    NOTIFICATION_STAGE,
    TASK_PROGRESS_EVENT_TYPE,
    InProcessNotificationSink,
    NotificationService,
)

__all__ = [
    "IN_PROCESS_CHANNEL",
    "NOTIFICATION_STAGE",
    "TASK_PROGRESS_EVENT_TYPE",
    "InProcessNotificationSink",
    "NotificationService",
]
