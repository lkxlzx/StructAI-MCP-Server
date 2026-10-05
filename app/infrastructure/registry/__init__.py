"""Registry 层（`docs/07` §3.3 / §12 P08；`docs/02` §18–§23 / §28）。

构成（P08）：

| 文件 | 内容 | 规范 |
| --- | --- | --- |
| `operation_registry.py` | `OperationRegistry` + `OPERATION_PROFILES` + `sync_operation_capabilities` | `docs/02` §21 / §28；`docs/07` §4.2 / §5.1 / §5.4 / §5.5 |
| `capability_registry.py` | `CapabilityRegistry`（41 条能力码 + Operation ↔ Capability 关系） | `docs/02` §20 / §27 / §31 |
| `software_registry.py` | `SoftwareRegistry`（Vendor / Product / Version / Instance） | `docs/02` §19 / §21 |
| `schema_registry.py` | `SchemaRegistry`（`register` / `get`；未注册 → `NotFoundError`；P09 用 `registry/schema/` 的 616 个文件填充） | `docs/02` §14 / §15 / §22；`docs/07` §12 P09 |
| `api_registry.py` | `ApiRegistry`（九字段映射；数据源 = `registry/`） | `docs/02` §23；`registry/README.md` |

分层红线（`docs/07` §14.1）：本包只允许落在 `app/infrastructure/registry/`；
`app/domain/` 不得引用本包，本包也不得反向依赖 Interface 层。

事务边界（`docs/02` §16；`docs/07` §14.4）：Registry **只读装配**；
唯一写路径是 `sync_operation_capabilities()`（只 `flush()`，由 `UnitOfWork` 决定提交）。

失败即不就绪（`docs/07` §14.4）：`OperationRegistry.load()` 的校验失败 → `InternalError`
（`STRUCTAI-7000`，20 码内的既有兜底码）→ 调用方（`app.container.startup`）**不得**进入 READY。

命令行：

    python -m app.infrastructure.registry.operation_registry   # 落库 Operation ↔ Capability
"""

from __future__ import annotations

from app.infrastructure.registry.api_registry import (
    API_REGISTRY_FIELDS,
    ApiRegistry,
    ApiRegistryEntry,
)
from app.infrastructure.registry.capability_registry import (
    CapabilityDefinition,
    CapabilityRegistry,
)
from app.infrastructure.registry.operation_registry import (
    OPERATION_CAPABILITIES,
    OPERATION_COUNT,
    OPERATION_PROFILES,
    RECOVERY_POLICIES,
    OperationCapabilitySyncReport,
    OperationProfile,
    OperationRegistry,
    sync_operation_capabilities,
)
from app.infrastructure.registry.schema_registry import (
    SCHEMA_DIR,
    SCHEMA_URI_PREFIX,
    UNDECLARED_DIALECT,
    SchemaLoadReport,
    SchemaRegistry,
    schema_id_for,
)
from app.infrastructure.registry.software_registry import (
    SoftwareInstanceView,
    SoftwareProductView,
    SoftwareRegistry,
    SoftwareVersionView,
)

__all__ = [
    "API_REGISTRY_FIELDS",
    "OPERATION_CAPABILITIES",
    "OPERATION_COUNT",
    "OPERATION_PROFILES",
    "RECOVERY_POLICIES",
    "SCHEMA_DIR",
    "SCHEMA_URI_PREFIX",
    "UNDECLARED_DIALECT",
    "ApiRegistry",
    "ApiRegistryEntry",
    "CapabilityDefinition",
    "CapabilityRegistry",
    "OperationCapabilitySyncReport",
    "OperationProfile",
    "OperationRegistry",
    "SchemaLoadReport",
    "SchemaRegistry",
    "SoftwareInstanceView",
    "SoftwareProductView",
    "SoftwareRegistry",
    "SoftwareVersionView",
    "schema_id_for",
    "sync_operation_capabilities",
]
