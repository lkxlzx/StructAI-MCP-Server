"""Domain 层（`docs/07` §3.3 冻结结构；`docs/02` §6）。

| 文件 | 职责 | 权威来源 |
| --- | --- | --- |
| `enums.py` | 领域枚举（19 个 StrEnum） | `docs/02` §8 / §5 / §17 / §70 / §71 |
| `errors.py` | 统一异常 + 20 码错误契约 | `docs/02` §9；`docs/07` §11 |
| `value_objects.py` | 不可变值对象 | `docs/02` §10 / §8；`docs/07` §4.2 |
| `protocols.py` | `OperationDefinition` + 领域接口 | `docs/02` §11 / §13 |
| `events.py` | 领域事件 | `docs/02` §12 / §34 |

本层是**最内层**：只依赖标准库，不得引用任何 ORM / Web 框架 / MCP SDK / HTTP 客户端，
也不得反向依赖 Infrastructure / Interface（`docs/07` §14.1；`docs/02` §6 / §3.2）。

本文件只做**重导出**，便于 `from app.domain import RiskLevel` 这类用法；
子模块仍是权威定义处（`app.domain.enums` 等始终解析为子模块）。
"""

from __future__ import annotations

from app.domain.enums import (
    ArtifactStatus,
    ArtifactType,
    AuditResult,
    AuthenticationMethod,
    Capability,
    CapabilityStatus,
    DocumentStatus,
    ExecutionMode,
    HealthStatus,
    LockMode,
    Permission,
    PermissionCode,
    PermissionEffect,
    ResourceType,
    RiskLevel,
    SoftwareConnectionState,
    SoftwareStatus,
    TaskPriority,
    TaskStatus,
)
from app.domain.errors import (
    AdapterError,
    ArtifactError,
    CapabilityError,
    ConcurrencyConflictError,
    ConfirmationRequiredError,
    EngineeringValidationError,
    InternalError,
    PermissionDeniedError,
    ProtocolError,
    ResourceLockedError,
    SchemaValidationError,
    SoftwareAPIError,
    SoftwareAuthenticationError,
    SoftwareConnectionError,
    SoftwareTimeoutError,
    StructAIError,
    TaskCancelledError,
    TaskError,
    TaskRecoveryError,
    TaskTimeoutError,
    TenantAccessDeniedError,
)
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
from app.domain.protocols import (
    ArtifactStorage,
    CredentialProvider,
    EventBus,
    EventHandler,
    OperationDefinition,
    OperationRegistry,
    Repository,
    UnitOfWork,
)
from app.domain.value_objects import (
    DEFAULT_PAGE_LIMIT,
    CapabilityName,
    DocumentId,
    DocumentRef,
    IdempotencyKey,
    ModelId,
    ModelRef,
    OperationName,
    Pagination,
    ProjectId,
    ProjectRef,
    RequestIdentity,
    ResourceRef,
    SoftwareInstanceId,
    SoftwareRef,
    TenantId,
    VersionRef,
)

__all__ = [
    # enums
    "ArtifactStatus",
    "ArtifactType",
    "AuditResult",
    "AuthenticationMethod",
    "Capability",
    "CapabilityStatus",
    "DocumentStatus",
    "ExecutionMode",
    "HealthStatus",
    "LockMode",
    "Permission",
    "PermissionCode",
    "PermissionEffect",
    "ResourceType",
    "RiskLevel",
    "SoftwareConnectionState",
    "SoftwareStatus",
    "TaskPriority",
    "TaskStatus",
    # errors
    "AdapterError",
    "ArtifactError",
    "CapabilityError",
    "ConcurrencyConflictError",
    "ConfirmationRequiredError",
    "EngineeringValidationError",
    "InternalError",
    "PermissionDeniedError",
    "ProtocolError",
    "ResourceLockedError",
    "SchemaValidationError",
    "SoftwareAPIError",
    "SoftwareAuthenticationError",
    "SoftwareConnectionError",
    "SoftwareTimeoutError",
    "StructAIError",
    "TaskCancelledError",
    "TaskError",
    "TaskRecoveryError",
    "TaskTimeoutError",
    "TenantAccessDeniedError",
    # events
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
    # protocols
    "ArtifactStorage",
    "CredentialProvider",
    "EventBus",
    "EventHandler",
    "OperationDefinition",
    "OperationRegistry",
    "Repository",
    "UnitOfWork",
    # value objects
    "DEFAULT_PAGE_LIMIT",
    "CapabilityName",
    "DocumentId",
    "DocumentRef",
    "IdempotencyKey",
    "ModelId",
    "ModelRef",
    "OperationName",
    "Pagination",
    "ProjectId",
    "ProjectRef",
    "RequestIdentity",
    "ResourceRef",
    "SoftwareInstanceId",
    "SoftwareRef",
    "TenantId",
    "VersionRef",
]
