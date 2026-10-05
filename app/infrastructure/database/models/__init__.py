"""ORM Model 导出（`docs/02` §25；`docs/07` §4.3）。

本包是 24 个 ORM Model 的**唯一注册入口**：只有被本文件导入的 ORM 类才会登记进
`Base.metadata`。因此任何需要 `create_all` / Alembic `target_metadata` 的调用方
都必须先 `import app.infrastructure.database.models`（`app.infrastructure.database`
的 `__init__` 已代为导入）。

命名：本包按 `docs/02` §18–§24（源码级规范）给出 `*ORM` 类名，并为每个类提供
`docs/07` §4.3 使用的 `*Model` 别名（**同一对象**，不是新模型）。
两套名字都进 `__all__`，后续批次任选其一均可。

表清单（24 张，与 `docs/07` §4.3 一一对应）：

| # | Model | 表名 | 模块 |
| --- | --- | --- | --- |
| 1 | `TenantModel` | `tenants` | `tenant.py` |
| 2 | `UserModel` | `users` | `user.py` |
| 3 | `RoleModel` | `roles` | `role.py` |
| 4 | `PermissionModel` | `permissions` | `permission.py` |
| 5 | `UserRoleModel` | `user_roles` | `user.py` |
| 6 | `RolePermissionModel` | `role_permissions` | `role.py` |
| 7 | `SessionModel` | `sessions` | `session.py` |
| 8 | `ProjectModel` | `projects` | `project.py` |
| 9 | `ProjectMemberModel` | `project_members` | `project.py` |
| 10 | `SoftwareModel` | `software` | `software.py` |
| 11 | `SoftwareProductModel` | `software_products` | `software.py` |
| 12 | `SoftwareVersionModel` | `software_versions` | `software.py` |
| 13 | `SoftwareInstanceModel` | `software_instances` | `software.py` |
| 14 | `ModelModel` | `models` | `model.py` |
| 15 | `DocumentModel` | `documents` | `document.py` |
| 16 | `CapabilityModel` | `capabilities` | `registry.py` |
| 17 | `OperationModel` | `operations` | `registry.py` |
| 18 | `OperationCapabilityModel` | `operation_capabilities` | `registry.py` |
| 19 | `TaskModel` | `tasks` | `task.py` |
| 20 | `TaskStepModel` | `task_steps` | `task.py` |
| 21 | `ArtifactModel` | `artifacts` | `artifact.py` |
| 22 | `ResourceLockModel` | `resource_locks` | `resource_lock.py` |
| 23 | `IdempotencyRecordModel` | `idempotency_records` | `idempotency.py` |
| 24 | `AuditRecordModel` | `audit_records` | `audit.py` |

⚠️ `docs/02` §3.2（Artifact 批次）新增 `document_versions` / `event_records` /
`trace_spans` 等表，不属本批次；`docs/07` §4.3 的 24 张表是本批次的冻结口径。
"""

from __future__ import annotations

from app.infrastructure.database.models.artifact import ArtifactModel, ArtifactORM
from app.infrastructure.database.models.audit import AuditRecordModel, AuditRecordORM
from app.infrastructure.database.models.document import DocumentModel, DocumentORM
from app.infrastructure.database.models.idempotency import (
    IdempotencyRecordModel,
    IdempotencyRecordORM,
)
from app.infrastructure.database.models.model import ModelModel, ModelORM
from app.infrastructure.database.models.permission import PermissionModel, PermissionORM
from app.infrastructure.database.models.project import (
    ProjectMemberModel,
    ProjectMemberORM,
    ProjectModel,
    ProjectORM,
)
from app.infrastructure.database.models.registry import (
    CapabilityModel,
    CapabilityORM,
    OperationCapabilityModel,
    OperationCapabilityORM,
    OperationModel,
    OperationORM,
)
from app.infrastructure.database.models.resource_lock import (
    ResourceLockModel,
    ResourceLockORM,
)
from app.infrastructure.database.models.role import (
    RoleModel,
    RoleORM,
    RolePermissionModel,
    RolePermissionORM,
)
from app.infrastructure.database.models.session import SessionModel, SessionORM
from app.infrastructure.database.models.software import (
    SoftwareInstanceModel,
    SoftwareInstanceORM,
    SoftwareModel,
    SoftwareORM,
    SoftwareProductModel,
    SoftwareProductORM,
    SoftwareVersionModel,
    SoftwareVersionORM,
)
from app.infrastructure.database.models.task import (
    TaskModel,
    TaskORM,
    TaskStepModel,
    TaskStepORM,
)
from app.infrastructure.database.models.tenant import TenantModel, TenantORM
from app.infrastructure.database.models.user import UserModel, UserORM, UserRoleModel, UserRoleORM

__all__ = [
    # 1
    "TenantModel",
    "TenantORM",
    # 2 / 5
    "UserModel",
    "UserORM",
    "UserRoleModel",
    "UserRoleORM",
    # 3 / 6
    "RoleModel",
    "RoleORM",
    "RolePermissionModel",
    "RolePermissionORM",
    # 4
    "PermissionModel",
    "PermissionORM",
    # 7
    "SessionModel",
    "SessionORM",
    # 8 / 9
    "ProjectModel",
    "ProjectORM",
    "ProjectMemberModel",
    "ProjectMemberORM",
    # 10–13
    "SoftwareModel",
    "SoftwareORM",
    "SoftwareProductModel",
    "SoftwareProductORM",
    "SoftwareVersionModel",
    "SoftwareVersionORM",
    "SoftwareInstanceModel",
    "SoftwareInstanceORM",
    # 14 / 15
    "ModelModel",
    "ModelORM",
    "DocumentModel",
    "DocumentORM",
    # 16–18
    "CapabilityModel",
    "CapabilityORM",
    "OperationModel",
    "OperationORM",
    "OperationCapabilityModel",
    "OperationCapabilityORM",
    # 19 / 20
    "TaskModel",
    "TaskORM",
    "TaskStepModel",
    "TaskStepORM",
    # 21
    "ArtifactModel",
    "ArtifactORM",
    # 22
    "ResourceLockModel",
    "ResourceLockORM",
    # 23
    "IdempotencyRecordModel",
    "IdempotencyRecordORM",
    # 24
    "AuditRecordModel",
    "AuditRecordORM",
]
