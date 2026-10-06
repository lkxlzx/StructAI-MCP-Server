"""Application · Services（`docs/07` §3.3 冻结结构；`docs/02` §43–§60 / §66 / §87）。

本包是跨执行流程的 Application 层服务落点（`docs/07` §3.3 的 `services/`）：

| 文件 | 内容 | 批次 |
| --- | --- | --- |
| `capability_resolver.py` | `CapabilityResolver`（`docs/02` §43–§48） | **P14–P18 ✅** |
| `artifact.py` | `ArtifactService`（`docs/02` §29 / §33 / §49 / §84） | **P29 ✅** |
| `document.py` · `model.py` · `result.py` | 文档 / 模型 / 结果服务 | **P30 ✅** |
| `quota.py` | `QuotaService`（第 12 步；`docs/02` §36 / §60） | **P35 ✅** |
| `backup.py` | 备份 / 恢复 / 保留（`docs/02` §41 / §46 / §66 / §81） | **P35 ✅** |
| `adapter_resolver.py` | `AdapterResolver`（`docs/02` §87） | **P35 ✅** |

装配形状（`docs/02` §33 / §123）
--------------------------------
本包的每个服务都是**会话级 / 请求级**对象（依赖会话级的 `*Store` 或进程级的
`AdapterManager`），因此**都不**进进程级容器 —— 与 P10–P13 的安全服务、
P14–P18 的资源服务、P19–P20 的 `AdapterManager` 同一口径
（`docs/02` §33 的冻结容器形状因此**不变**）。P36 的 `ExecutionService`
按会话 / 进程装配它们。

`CapabilityResolver` 的可选 `runtime=` 参数（`RuntimeCapabilitySource`，
`docs/02` §21 / §23 / §57；`docs/07` §16 R30 的接入点）由
`app/infrastructure/adapters/base/manager.py` 的
`AdapterManager.runtime_capabilities()` 提供；`AdapterResolver`
（`docs/07` §3.3 的 `services/adapter_resolver.py`）在 P35 补齐，
它把 `docs/02` §87 的解析链收窄为三个问题（见该模块的裁决）。

命名冲突说明：`capability_resolver.InstanceLookup` 与
`adapter_resolver.InstanceLookup` 是**两个不同**的收窄契约（前者问「实例的能力清单」，
后者问「实例的 vendor / product / version」），因此本 `__init__` 只导出前者的名字，
后者经 `app.application.services.adapter_resolver.InstanceLookup` 显式导入。

分层红线（`docs/07` §14.1 / §2.2）：本包只依赖标准库与 `app.domain`；
**不得**依赖 `app.infrastructure` / `app.interfaces` / `app.observability`，
也不得出现任何厂商专属内容。
"""

from __future__ import annotations

from app.application.services.adapter_resolver import (
    ADAPTER_RESOLVER_STAGE,
    AdapterResolution,
    AdapterResolver,
)
from app.application.services.artifact import (
    ARTIFACT_BACKEND_LOCAL,
    ARTIFACT_STAGE,
    ArtifactService,
)
from app.application.services.backup import (
    ARTIFACT_BACKUP_DIR,
    ARTIFACT_CHECKSUMS_KEY,
    BACKUP_ARTIFACTS_DIR,
    BACKUP_DATABASE_NAME,
    BACKUP_MANIFEST_NAME,
    BACKUP_STAGE,
    BACKUP_VERSION,
    DATABASE_SUFFIX,
    DEFAULT_RETENTION_POLICY,
    QUARANTINE_DIR,
    RESTORE_PRE_BACKUP_DIR,
    RESTORE_STAGE,
    ArtifactStorageReader,
    BackupManifest,
    BackupService,
    BackupVerification,
    RestoreReport,
    RestoreService,
    RetentionReport,
    RetentionService,
    SessionRetentionSource,
    TaskRetentionSource,
    backup_database,
)
from app.application.services.capability_resolver import (
    DEFAULT_CAPABILITY_CACHE_SECONDS,
    CapabilityDecision,
    CapabilityLookup,
    CapabilityResolver,
    CapabilitySupport,
    InstanceLookup,
    RuntimeCapabilitySource,
)
from app.application.services.document import (
    DOCUMENT_LIFECYCLE_ORDER,
    DOCUMENT_STAGE,
    DOCUMENT_STATUS_EDGES,
    INFORMATION_ONLY_OPERATION,
    DocumentArtifactWriter,
    DocumentInfo,
    DocumentService,
)
from app.application.services.model import (
    ASSIGN_OPERATIONS,
    MODEL_SERVICE_STAGE,
    QUERY_OPERATIONS,
    ModelAssignment,
    ModelQuerySource,
    ModelService,
)
from app.application.services.quota import (
    QUOTA_DIMENSIONS,
    QUOTA_METRICS,
    QUOTA_STAGE,
    QuotaDecision,
    QuotaService,
    StaticQuotaPolicySource,
)
from app.application.services.result import (
    ARTIFACTS_KEY,
    DATA_KEY,
    DEFAULT_RESULT_LIMIT,
    HAS_MORE_KEY,
    NEXT_CURSOR_KEY,
    PAGINATION_KEY,
    RESULT_STAGE,
    CanonicalResult,
    ResultService,
    decode_cursor,
    encode_cursor,
    envelope,
    paginate,
)

__all__ = [
    "ADAPTER_RESOLVER_STAGE",
    "ARTIFACTS_KEY",
    "ARTIFACT_BACKEND_LOCAL",
    "ARTIFACT_BACKUP_DIR",
    "ARTIFACT_CHECKSUMS_KEY",
    "ARTIFACT_STAGE",
    "ASSIGN_OPERATIONS",
    "BACKUP_ARTIFACTS_DIR",
    "BACKUP_DATABASE_NAME",
    "BACKUP_MANIFEST_NAME",
    "BACKUP_STAGE",
    "BACKUP_VERSION",
    "DATA_KEY",
    "DATABASE_SUFFIX",
    "DEFAULT_CAPABILITY_CACHE_SECONDS",
    "DEFAULT_RESULT_LIMIT",
    "DEFAULT_RETENTION_POLICY",
    "DOCUMENT_LIFECYCLE_ORDER",
    "DOCUMENT_STAGE",
    "DOCUMENT_STATUS_EDGES",
    "HAS_MORE_KEY",
    "INFORMATION_ONLY_OPERATION",
    "MODEL_SERVICE_STAGE",
    "NEXT_CURSOR_KEY",
    "PAGINATION_KEY",
    "QUARANTINE_DIR",
    "QUOTA_DIMENSIONS",
    "QUOTA_METRICS",
    "QUOTA_STAGE",
    "QUERY_OPERATIONS",
    "RESULT_STAGE",
    "RESTORE_PRE_BACKUP_DIR",
    "RESTORE_STAGE",
    "AdapterResolution",
    "AdapterResolver",
    "ArtifactService",
    "ArtifactStorageReader",
    "BackupManifest",
    "BackupService",
    "BackupVerification",
    "CanonicalResult",
    "CapabilityDecision",
    "CapabilityLookup",
    "CapabilityResolver",
    "CapabilitySupport",
    "DocumentArtifactWriter",
    "DocumentInfo",
    "DocumentService",
    "InstanceLookup",
    "ModelAssignment",
    "ModelQuerySource",
    "ModelService",
    "QuotaDecision",
    "QuotaService",
    "RestoreReport",
    "RestoreService",
    "ResultService",
    "RetentionReport",
    "RetentionService",
    "RuntimeCapabilitySource",
    "SessionRetentionSource",
    "StaticQuotaPolicySource",
    "TaskRetentionSource",
    "backup_database",
    "decode_cursor",
    "encode_cursor",
    "envelope",
    "paginate",
]
