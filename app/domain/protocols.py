"""Domain Protocols —— `OperationDefinition` 与领域接口（`docs/02` §11 / §13）。

权威来源：

- `docs/02` §11（`source7` §11）—— `OperationDefinition`（12 字段），本文件照抄；
  `docs/02` §10（`impl`）与 `docs/07` §4.2 的三处定义一致。
- `docs/02` §13（`source7` §13）—— `OperationRegistry` / `EventBus` /
  `CredentialProvider`，方法签名照抄并补全类型标注。
- `docs/02` §11（`blue` §11）—— `Repository` / `UnitOfWork` / `ArtifactStorage`；
  规范只给方法骨架，此处补全类型标注，并注明最小方法集。
- `docs/02` §34（`impl`）—— `EventBus.subscribe(event_type, handler)`。

为什么放在 Domain：`docs/02` §11 明确「这样 Domain/Application 不依赖具体数据库和
文件系统」——接口定义在 Domain，实现落在 Infrastructure（`docs/07` §2.2 依赖方向）。

分层红线（`docs/07` §14.1；`docs/02` §6）：只依赖标准库与本包，不得引用
任何 ORM / Web 框架 / MCP SDK / HTTP 客户端，也不得出现厂商专属内容。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.domain.enums import ExecutionMode, RiskLevel
from app.domain.events import DomainEvent

__all__ = [
    "ArtifactStorage",
    "CredentialProvider",
    "EventHandler",
    "EventBus",
    "OperationDefinition",
    "OperationRegistry",
    "Repository",
    "UnitOfWork",
]


# ===== `docs/02` §11（source7 §11）=====


@dataclass(frozen=True, slots=True)
class OperationDefinition:
    """操作定义（`docs/02` §11；`docs/07` §4.2）。

    - `input_schema` / `output_schema` 是 Schema 的引用（`docs/02` §12），不是内联 JSON。
    - `recovery_policy` 默认 `"FAIL"`，照抄规范。
    - 12 个字段的名称与顺序与规范一致，供 P08 OperationRegistry 逐项消费。
    """

    name: str
    tool: str
    risk_level: RiskLevel
    execution_mode: ExecutionMode
    input_schema: str
    output_schema: str
    required_permissions: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    transactional: bool = False
    rollback_supported: bool = False
    dry_run_supported: bool = False
    recovery_policy: str = "FAIL"


# ===== `docs/02` §13（source7 §13）=====


class OperationRegistry(Protocol):
    """操作注册表（`docs/02` §13）。

    P08 提供实现；`docs/07` §12 P08 的门槛即
    `operation_registry.get("BUILD.COLUMN")` 返回定义。
    """

    async def register(self, definition: OperationDefinition) -> None: ...

    async def get(self, name: str) -> OperationDefinition | None: ...

    async def list(self) -> list[OperationDefinition]: ...


EventHandler = Callable[[DomainEvent], Awaitable[None]]
"""事件处理器签名（`docs/02` §34）。"""


class EventBus(Protocol):
    """事件总线（`docs/02` §13 / §34）。

    事件本身定义在 `app.domain.events`；实现（`InProcessEventBus`）在 Infrastructure，
    可替换为 Redis / NATS / Kafka 而不修改 Domain Event（`docs/02` §38）。
    """

    async def publish(self, event: DomainEvent) -> None: ...

    async def subscribe(self, event_type: type[DomainEvent], handler: EventHandler) -> None: ...


class CredentialProvider(Protocol):
    """凭据提供者（`docs/02` §13 / §21）。

    ⚠️ 凭据只经运行环境注入，绝不落库、落日志、落文件（`docs/07` §8.5 / §14.3）；
    本接口只返回引用对应的值，不得把值写入任何持久化结构。
    """

    async def get_secret(self, reference: str) -> str: ...

    async def set_secret(self, reference: str, value: str) -> None: ...

    async def delete_secret(self, reference: str) -> None: ...


# ===== `docs/02` §11（blue §11）=====


class Repository(Protocol):
    """实体仓储接口（`docs/02` §11）。

    规范只给出 `get`；`add` / `remove` 是 P05「最小集 CRUD」所需的最小补齐。
    ⚠️ **Repository 不得自行 `commit`**（`docs/07` §14.4）——事务边界归 `UnitOfWork`。
    """

    async def get(self, entity_id: UUID) -> object | None: ...

    async def add(self, entity: object) -> None: ...

    async def remove(self, entity: object) -> None: ...


class UnitOfWork(Protocol):
    """工作单元（`docs/02` §11 / §16；`docs/07` §12 P06）。

    只暴露 `commit` / `rollback`；上下文管理与 `close` 由 P06 的具体实现负责。
    """

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class ArtifactStorage(Protocol):
    """产物存储（`docs/02` §11 / §29 / §33）。

    - 数据库只保存 `artifact_id` / `storage_backend` / `storage_key` / `mime_type` /
      `size` / `checksum`（`docs/02` §33），不保存内容。
    - `put` 返回 `storage_key`；Core Alpha 实现为本地文件系统（P29）。
    """

    async def put(self, data: bytes, metadata: Mapping[str, Any]) -> str: ...

    async def get(self, artifact_id: str) -> bytes: ...

    async def delete(self, artifact_id: str) -> None: ...
