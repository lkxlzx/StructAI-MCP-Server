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

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.domain.enums import (
    ACLPrincipalType,
    ACLScope,
    ExecutionMode,
    PermissionEffect,
    RiskLevel,
)
from app.domain.events import DomainEvent

__all__ = [
    "ArtifactStorage",
    "CredentialProvider",
    "DocumentRecord",
    "EventHandler",
    "ModelRecord",
    "ProjectRecord",
    "ResourceStore",
    "SoftwareInstanceRecord",
    "ProjectMembershipLookup",
    "ResourceACLEntry",
    "ResourceACLLookup",
    "RoleLookup",
    "SecurityStores",
    "SessionRecord",
    "SessionStore",
    "UserLookup",
    "UserRecord",
    "EventBus",
    "OperationDefinition",
    "OperationRegistry",
    "Repository",
    "UnitOfWork",
    "IdempotencyRecord",
    "IdempotencyReservation",
    "IdempotencyStore",
    "TaskDraft",
    "TaskRecord",
    "TaskStepDraft",
    "TaskStepRecord",
    "TaskStore",
    # ===== P29–P35 Infrastructure =====
    "AdapterResolverSource",
    "ArtifactDraft",
    "ArtifactRecord",
    "ArtifactStore",
    "AuditEntry",
    "AuditEntryDraft",
    "AuditStore",
    "DocumentDraft",
    "DocumentSnapshot",
    "DocumentStore",
    "DocumentVersionRecord",
    "DocumentVersionStore",
    "EventRecordDraft",
    "EventRecordSnapshot",
    "EventRecordStore",
    "HealthChecker",
    "NotificationMessage",
    "NotificationSink",
    "QuotaLimits",
    "QuotaPolicySource",
    "RetentionPolicy",
    "TraceSpanRecord",
    "TraceStore",
    "AuditRecorder",
    "MetricsRecorder",
    "TraceRecorder",
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


# ===== P10–P13 Security（`docs/07` §12 P10–P13；`docs/02` §24–§29）=====
#
# 为什么这些契约在 Domain（`docs/07` §14.1 / §2.2）：
# Application 层**不得**依赖 `app.infrastructure`。安全服务需要读 `users` /
# `sessions` / `roles` / `role_permissions` / `user_roles` / `project_members`，
# 故把「需要什么」收窄为下列结构化契约与记录类型（P03 的 `OperationRegistry`、
# P09 的 `SchemaLookup` 是同一做法的先例），实现落在
# `app/infrastructure/database/repositories/security.py`。
#
# 🔴 记录类型只承载**非敏感**字段：`UserRecord.password_hash` 是唯一例外 ——
#    它必须参与 Argon2id 校验，故以 `repr=False` 声明；任何日志 / 异常 / 响应
#    都不得出现它（`docs/07` §14.3；`docs/02` §8）。


@dataclass(frozen=True, slots=True)
class UserRecord:
    """认证与锁定判定所需的用户快照（`docs/02` §16 / §18 / §20）。

    `docs/02` §16 的 `authenticate` 需要 `password_hash` / `is_active`；
    `docs/02` §18 的失败计数与锁定需要 `locked` / `failed_login_count`。
    本记录只含这几项，**不**携带任何 secret 的明文（`password_hash` 是哈希，
    且 `repr=False`，绝不进日志 —— `docs/07` §14.3）。
    """

    id: str
    tenant_id: str
    username: str
    password_hash: str = field(repr=False)
    is_active: bool = True
    locked: bool = False
    failed_login_count: int = 0


class UserLookup(Protocol):
    """用户读取与登录状态写入契约（`docs/02` §16 / §18 / §20）。

    - `get_by_username` —— 登录路径。`users.username` 在 P04 落地为**全局唯一**
      （`docs/07` §4.3 #2），且认证发生在**任何租户被确定之前**（租户来自
      认证后的 `IdentityContext`，`docs/02` §22），故这里必须是全局按用户名查。
    - `get_by_id_for_tenant` —— 会话路径。会话里已带 `tenant_id`，读取必须
      同时限制 `tenant_id` + `user_id`（`docs/02` §11）。
    - 其余三个方法承载 `docs/02` §18 的失败计数 / 锁定状态写入（策略值由
      `AuthenticationService` 注入，本契约只负责机制）。
    """

    async def get_by_username(self, username: str) -> UserRecord | None: ...

    async def get_by_id_for_tenant(self, user_id: str, tenant_id: str) -> UserRecord | None: ...

    async def record_login_failure(self, user_id: str, *, lock_at: int) -> int: ...

    async def record_login_success(self, user_id: str) -> None: ...

    async def set_locked(self, user_id: str, *, locked: bool) -> None: ...


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """会话快照（`docs/02` §10 / §19 / §20）。

    ⚠️ **不含** `token_hash`：会话校验只需要「存在 / 未撤销 / 未过期」，
    把哈希留在持久层可以少一条 secret 形状的数据在 Application 层流转
    （`docs/07` §14.3：绝不记录 secret）。
    `expires_at` / `last_seen_at` 一律为 **UTC 感知**时间（SQLite 无时区，
    由实现负责补 `UTC`，见 `repositories/security.py`）。
    """

    id: str
    user_id: str
    tenant_id: str
    expires_at: datetime
    revoked: bool = False
    last_seen_at: datetime | None = None


class SessionStore(Protocol):
    """会话持久化契约（`docs/02` §11 / §19 / §20 / §21）。

    方法集即 `docs/02` §11 的 Session 生命周期：`create` / `validate`
    （= `get_by_token_hash`）/ `touch` / `revoke` / `revoke_all` / `cleanup_expired`。
    """

    async def create(
        self,
        *,
        user_id: str,
        tenant_id: str,
        token_hash: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> SessionRecord: ...

    async def get_by_token_hash(self, token_hash: str) -> SessionRecord | None: ...

    async def revoke(self, session_id: str) -> bool: ...

    async def revoke_all_for_user(self, user_id: str) -> int: ...

    async def touch(self, session_id: str, seen_at: datetime) -> None: ...

    async def cleanup_expired(self, now: datetime) -> int: ...


class RoleLookup(Protocol):
    """RBAC 读取契约（`docs/02` §19 / §23 / §30）。

    `permission_codes_for_roles` 需要 `tenant_id`：`roles` 是 Tenant-owned
    （`docs/07` §4.3 #3），项目内角色也必须在**该项目所属租户**的角色表里解析
    （`docs/02` §23 Project Access）。
    """

    async def role_names_for_user(self, user_id: str) -> list[str]: ...

    async def permission_codes_for_user(self, user_id: str) -> set[str]: ...

    async def permission_codes_for_roles(
        self,
        role_names: Sequence[str],
        tenant_id: str,
    ) -> set[str]: ...


class ProjectMembershipLookup(Protocol):
    """项目归属与项目内角色读取契约（`docs/02` §23 / §30）。

    只暴露两个问题：「这个项目属于哪个租户」与「这个用户在这个项目里是什么角色」。
    跨租户判定由 `ProjectAccessService` 负责（失败 → `STRUCTAI-4200`，
    `docs/02` §48）。
    """

    async def project_tenant_id(self, project_id: str) -> str | None: ...

    async def project_role_for_user(self, project_id: str, user_id: str) -> str | None: ...


@dataclass(frozen=True, slots=True)
class ResourceACLEntry:
    """一条资源 ACL 记录（`docs/02` §24–§28）。

    字段取自 `docs/02` §25 的 `ResourceACLORM`（`resource_type` / `resource_id` /
    `principal_type` / `principal_id` / `permission` / `effect`），并补一个
    `scope`（四级取最严格，`docs/07` §8.2）—— `scope` 是**判定逻辑**所需，
    不在 §25 的表结构里（见 `app/application/security/permission.py` 的裁决）。
    """

    principal_type: ACLPrincipalType
    principal_id: str
    permission: str
    effect: PermissionEffect
    scope: ACLScope = ACLScope.RESOURCE
    resource_type: str | None = None
    resource_id: str | None = None


class ResourceACLLookup(Protocol):
    """资源 ACL 来源契约（`docs/02` §24 / §29）。

    `tenant_id` 必填：ACL 不得跨租户泄漏（`docs/02` §48）。
    `resource_type` / `resource_id` 为 `None` 时表示「只取与具体资源无关的条目」
    （全局 / 租户 / 用户级），实现必须如实过滤。
    """

    async def entries_for(
        self,
        *,
        tenant_id: str,
        resource_type: str | None,
        resource_id: str | None,
    ) -> Sequence[ResourceACLEntry]: ...


@dataclass(frozen=True, slots=True)
class SecurityStores:
    """安全服务需要的持久化入口集合（会话级，`docs/02` §33）。

    由 `app.infrastructure.database.repositories.build_security_stores(session)`
    装配；Application 层只依赖本 Domain 契约，**不**依赖 Infrastructure
    （`docs/07` §14.1）。
    """

    users: UserLookup
    sessions: SessionStore
    roles: RoleLookup
    projects: ProjectMembershipLookup


# ===== P14–P18 Execution Foundation（`docs/07` §12 P14–P18；`docs/02` §8–§12 / §25）=====
#
# 为什么这些契约在 Domain（`docs/07` §14.1 / §2.2）：
# `ResourceResolver` 需要读 `projects` / `models` / `documents` /
# `software_instances` 四张表（`docs/02` §8–§12 / §25 / §71–§73），而 Application 层
# **不得**依赖 `app.infrastructure`。故把「需要什么」收窄为下列结构化记录与契约
# （P03 的 `OperationRegistry`、P09 的 `SchemaLookup`、P10–P13 的 `SecurityStores`
# 是同一做法的先例），实现落在
# `app/infrastructure/database/repositories/resource.py`。
#
# 🔴 记录类型只承载**非敏感**字段：`SoftwareInstanceRecord` 刻意**不含**
#    `credential_reference`（`docs/02` §21；`docs/07` §8.5 / §14.3）—— 凭据引用是
#    Adapter / CredentialProvider 的内部字段，绝不进入执行上下文，从源头收掉 secret 外泄面。


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    """项目快照（`docs/02` §8 / §20 / §71）。

    只承载租户边界判定所需的字段：`projects` 是 Tenant-owned（`docs/07` §4.3 #8），
    `tenant_id` 是 `docs/02` §10 的**唯一**跨租户判定依据。
    `version` 是乐观并发版本号（`docs/02` §12），供执行层回传 `expected_version`。
    """

    id: str
    tenant_id: str
    version: int = 1


@dataclass(frozen=True, slots=True)
class ModelRecord:
    """工程模型快照（`docs/02` §8 / §22 / §71–§72）。

    `models` **没有** `tenant_id` 列：租户归属经 `project_id → projects.tenant_id` 传递
    （`docs/02` §11 / §22），因此解析模型时**必须**追到项目再追到租户
    （`docs/02` §11 的 `Model ↓ Project ↓ Tenant`）。
    """

    id: str
    project_id: str
    software_instance_id: str | None = None
    version: int = 1


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    """文档快照（`docs/02` §8 / §22）。

    与模型同理：租户归属经 `project_id → projects.tenant_id` 传递。
    `status` 取值见 `app.domain.enums.DocumentStatus`。
    """

    id: str
    project_id: str
    model_id: str | None = None
    status: str = ""


@dataclass(frozen=True, slots=True)
class SoftwareInstanceRecord:
    """软件实例快照（`docs/02` §12 / §19 / §21）。

    ⚠️ **不含** `credential_reference`（见本节说明）。

    `software_instances` 属 `docs/07` §4.3 #10–#13 的**软件注册表**，没有 `tenant_id`
    列；`docs/02` §12 因此要求「如果当前 Schema 还没有该字段，本批次必须通过所属
    Project / Registry 关系补齐，**不能允许跨租户实例被直接执行**」。实例的租户归属
    由 `ResourceStore.tenant_ids_binding_instance` 回答（见下）。
    """

    id: str
    name: str
    version_id: str = ""
    status: str = ""
    vendor: str = ""
    product: str = ""
    version: str = ""


class ResourceStore(Protocol):
    """执行期资源读取契约（`docs/02` §8–§12 / §25 / §71–§73）。

    - 四个读取方法只回答「这一行是什么」，**不**做租户判定 —— 跨租户拦截是
      `ResourceResolver` 的**唯一**职责（`docs/07` §9 第 7 步：「跨租户唯一拦截点，
      必须最先」），判定只允许一处实现。
    - `tenant_ids_binding_instance` 回答「哪些租户的项目链绑定了这个软件实例」，
      用于在**不改表**的前提下补齐 `software_instances` 缺失的租户归属
      （`docs/02` §12：经「所属 Project / Registry 关系」补齐）。
    """

    async def project(self, project_id: str) -> ProjectRecord | None: ...

    async def model(self, model_id: str) -> ModelRecord | None: ...

    async def document(self, document_id: str) -> DocumentRecord | None: ...

    async def software_instance(self, instance_id: str) -> SoftwareInstanceRecord | None: ...

    async def tenant_ids_binding_instance(self, instance_id: str) -> frozenset[str]: ...


# ===== P21 Idempotency（`docs/07` §12 P21 / §10.3；`docs/02` §28 / §31–§35）=====
#
# 为什么这些契约在 Domain（`docs/07` §14.1 / §2.2）：
# `IdempotencyService`（Application 层，`app/application/execution/idempotency.py`）
# **不得**依赖 `app.infrastructure`，而「原子 `INSERT` 抢占 + 冲突回读」必须落在
# `idempotency_records` 表上（P04 已落地 24 张表之一）。故把「需要什么」收窄为
# 下列结构化记录与契约（P09 的 `SchemaLookup`、P10–P13 的 `SecurityStores`、
# P14–P18 的 `ResourceStore` 是同一做法的先例），实现落在
# `app/infrastructure/database/repositories/idempotency.py`。
#
# 🔴 记录类型只承载**非敏感**字段：`request_hash` 是 SHA-256 摘要（`docs/02` §33）、
#    `response_json` 是**业务响应**快照。二者都**不含**任何 secret —— 幂等键与响应
#    里不得出现 password / API key / token / private key（`docs/07` §14.3）。


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    """一条幂等记录的快照（`docs/07` §4.3 #23；`docs/02` §24 / §31–§35）。

    字段与 P04 落地的 `idempotency_records` 表**逐列对应**（本批只**用**它，
    **不得**改表 —— `docs/07` §14.3 / §14.3 的「禁止启动时静默 `ALTER TABLE`」）：

    - `tenant_id` + `idempotency_key` —— 数据库唯一键
      （`UNIQUE(tenant_id, idempotency_key)`，`docs/02` §28 / §31 / §35）；
    - `request_hash` —— 请求摘要；同键不同摘要**必须拒绝**（`docs/02` §32）；
    - `response_json` —— 首次成功执行的响应快照；`None` 表示「已抢占、尚未完成」
      （`docs/02` §28 的 `reserve` → `complete` 之间）。

    列名口径：`docs/07` §4.3 #23 写作 `idempotency_key`，`docs/02` §24 的源码写作
    `key`；本记录采用 `idempotency_key`（与表列名、领域值对象
    `app.domain.value_objects.IdempotencyKey` 一致），二者指同一列。
    """

    id: str
    tenant_id: str
    idempotency_key: str
    request_hash: str
    response_json: str | None = None


@dataclass(frozen=True, slots=True)
class IdempotencyReservation:
    """一次「抢占」的结果（`docs/02` §28 的 `reserve` / §35 的冲突回读）。

    - `created is True` —— 本次 `INSERT` **抢占成功**，`record` 即刚插入的那一行
      （`response_json` 为 `None`）；调用方继续执行，结束后 `complete()`。
    - `created is False` —— 唯一键冲突（`IntegrityError`）后**回读**到的既有记录
      （`docs/02` §35：`UNIQUE(tenant_id, key)` → 捕获 `IntegrityError` → 重新读取）。

    两种情形的 `record` 都**必然**存在：调用方不需要（也**不允许**）在 `reserve`
    之前先 `SELECT` 判断存在性（`docs/02` §28 / §32 / §35 明确禁止 `SELECT → INSERT`）。
    """

    record: IdempotencyRecord
    created: bool


class IdempotencyStore(Protocol):
    """幂等记录的持久化契约（`docs/02` §28 / §34 / §35）。

    🔴 **原子性由实现负责**（`docs/07` §10.3；`docs/02` §28 / §32 / §35）：

    - `reserve` **必须**直接 `INSERT` 抢占（唯一键由**数据库约束**保证），
      捕获 `IntegrityError` 后**回读**既有记录并返回 `created=False`；
      **禁止**先 `SELECT` 判断「不存在」再 `INSERT`（那是 race condition）。
    - 实现只 `INSERT` / `UPDATE` / `SELECT`，**绝不** `commit` / `rollback`
      ——事务边界归 P06 `UnitOfWork`（`docs/02` §16；`docs/07` §14.4）。
    - `reserve` **不**在同一事务里替调用方决定提交；因此「抢占」与「执行」之间的
      可见性完全由调用方的 `UnitOfWork` 决定。
    """

    async def reserve(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> IdempotencyReservation: ...

    async def existing(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
    ) -> IdempotencyRecord | None: ...

    async def complete(self, record_id: str, response_json: str) -> bool: ...


# ===== P22–P28 Task Engine（`docs/07` §12 P22–P28 / §10.1–§10.2；`docs/02` §7–§20 / §34–§54）=====
#
# 为什么这些契约在 Domain（`docs/07` §14.1 / §2.2）：
# 任务引擎（`app/application/task/`）需要读写 `tasks` / `task_steps` 两张表
# （P04 已落地，本批只**用**它们，**不得改表**），而 Application 层**不得**依赖
# `app.infrastructure`。故把「需要什么」收窄为下列结构化记录与契约
# （P09 的 `SchemaLookup`、P10–P13 的 `SecurityStores`、P14–P18 的 `ResourceStore`、
# P21 的 `IdempotencyStore` 是同一做法的先例），实现落在
# `app/infrastructure/database/repositories/task.py`。
#
# 🔴 记录类型只承载**非敏感**字段：`tasks` / `task_steps` 两表没有任何凭据列；
#    `result_json` / `error_json` 是**业务**结果与**归一化**错误信封，二者都不得
#    写入 password / API key / token / private key（`docs/07` §14.3）。


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """一条任务的快照（`docs/07` §4.3 #19；`docs/02` §9 / §34）。

    字段与 P04 落地的 `tasks` 表**逐列对应**（本批只**用**它，**不得**改表 ——
    `docs/07` §14.3）。口径：

    - `status` 取值见 `app.domain.enums.TaskStatus`（12 态，`docs/07` §10.1）；
    - `lease_owner` / `lease_until` / `heartbeat_at` 支撑租约与崩溃恢复
      （`docs/02` §34–§38）；`last_heartbeat` 的落库列名是 `heartbeat_at`
      （`docs/02` §10 / §34）；
    - `priority` 是**整数**（`docs/02` §14 的建议映射：`0` CRITICAL / `10` HIGH /
      `50` NORMAL / `100` LOW），队列按 `priority` + `created_at` 出队（§17）；
    - `created_at` 参与队列排序（`docs/02` §17），故必须随记录返回；
    - `version` 是乐观并发版本号（`docs/02` §12；`docs/07` §4.3 #19）。

    时间一律为 **UTC 感知**时间（SQLite 无时区，由实现负责补 `UTC`，
    与 `repositories/security.py` 同口径）。
    """

    id: str
    tenant_id: str
    request_id: str
    trace_id: str
    tool: str
    operation: str
    status: str
    created_at: datetime
    project_id: str | None = None
    progress: int = 0
    retry_count: int = 0
    max_retries: int = 0
    cancel_requested: bool = False
    lease_owner: str | None = None
    lease_until: datetime | None = None
    heartbeat_at: datetime | None = None
    priority: int = 100
    error_json: str | None = None
    result_json: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    version: int = 1

    def lease_is_expired(self, now: datetime) -> bool:
        """租约是否已失效（`docs/02` §36 / §40）。

        「无租约」（`lease_owner is None`）与「租约到期」（`lease_until <= now`）
        **都**算失效 —— 前者是可抢占，后者是可恢复（`docs/02` §40 的
        `lease_owner IS NULL OR lease_until < now`）。
        """
        if self.lease_owner is None or self.lease_until is None:
            return True
        return self.lease_until <= now


@dataclass(frozen=True, slots=True)
class TaskStepRecord:
    """一个 DAG 步骤的快照（`docs/07` §4.3 #20；`docs/02` §47 / §52）。

    字段与 P04 落地的 `task_steps` 表**逐列对应**；`depends_on_json` 是前置步骤
    `step_key` 的 JSON 数组（`docs/07` §4.3 #20 的 `depends_on`）。
    `status` 取值见 `app.domain.enums.TaskStepStatus`（`docs/02` §50）。
    """

    id: str
    task_id: str
    step_key: str
    operation: str
    status: str
    parameters_json: str
    depends_on_json: str
    result_json: str | None = None
    error_json: str | None = None


@dataclass(frozen=True, slots=True)
class TaskDraft:
    """待创建的任务（`docs/02` §9 的 `Task Repository` 字段扩展）。

    ⚠️ **本契约只做 persistence**：`status` 的合法性由
    `app/application/task/state_machine.py` 判定（`docs/07` §10.1：
    状态机必须集中实现）；`created_at` / `id` / `version` 由实现生成。
    """

    tenant_id: str
    request_id: str
    trace_id: str
    tool: str
    operation: str
    project_id: str | None = None
    priority: int = 100
    max_retries: int = 0
    status: str = "CREATED"


@dataclass(frozen=True, slots=True)
class TaskStepDraft:
    """待创建的 DAG 步骤（`docs/02` §47 的 `TaskStep`）。"""

    step_key: str
    operation: str
    parameters_json: str = "{}"
    depends_on: tuple[str, ...] = ()


class TaskStore(Protocol):
    """任务 / 任务步骤的持久化契约（`docs/02` §9 / §11 / §34 / §36）。

    🔴 **原子性由实现负责**（`docs/02` §36「Lease 原子更新」；`docs/07` §10.2）：

    - `acquire_lease` **必须**是单条条件 `UPDATE`（`WHERE lease_owner IS NULL OR
      lease_until < now`），影响行数为 **1** 才算获得租约，否则返回 `None`；
      **禁止** `SELECT → UPDATE`（否则两个 Worker 会同时抢到同一任务）；
    - `heartbeat` / `release_lease` 同样是**条件更新**（`WHERE lease_owner = :worker`），
      影响 0 行即失败（不得续到别人手里的租约）；
    - `transition` 是**状态的条件更新**（`WHERE status = :expected`），
      影响 0 行即失败 —— 调用方据此判定「状态已被别人改过」。

    实现只 `INSERT` / `UPDATE` / `SELECT`，**绝不** `commit` / `rollback`
    —— 事务边界归 P06 `UnitOfWork`（`docs/02` §16；`docs/07` §14.4）。
    """

    async def create(
        self,
        draft: TaskDraft,
        steps: Sequence[TaskStepDraft] = (),
    ) -> TaskRecord: ...

    async def get(self, task_id: str, tenant_id: str) -> TaskRecord | None: ...

    async def transition(
        self,
        task_id: str,
        *,
        expected: str,
        new: str,
        fields: Mapping[str, object] | None = None,
    ) -> bool: ...

    async def acquire_lease(
        self,
        task_id: str,
        *,
        worker_id: str,
        now: datetime,
        lease_until: datetime,
    ) -> TaskRecord | None: ...

    async def heartbeat(
        self,
        task_id: str,
        *,
        worker_id: str,
        heartbeat_at: datetime,
        lease_until: datetime,
    ) -> bool: ...

    async def release_lease(self, task_id: str, *, worker_id: str) -> bool: ...

    async def record_error(
        self,
        task_id: str,
        *,
        error_json: str,
        expected_status: str | None = None,
    ) -> bool:
        """只写 `error_json`、**不**改状态的条件更新（`docs/02` §30 / §34）。

        🔴 **这不是状态转移**：`tasks.status` 保持原值（因此冻结的转移表在这里**不**适用），
        实现是**单条** `UPDATE tasks SET error_json = :e, version = version + 1
        WHERE id = :id AND (:expected IS NULL OR status = :expected)`，`rowcount == 1`
        才算成功；**禁止** `SELECT → UPDATE`（`docs/02` §36 的同理）。

        用途：取消路径在「软件不支持真正取消」时必须**保持** `CANCEL_REQUESTED` 并把
        归一化错误落 `error_json`（`docs/02` §30「最终真实状态必须可追踪」）—— 若走
        `transition`，`CANCEL_REQUESTED → CANCEL_REQUESTED` 是自转移，冻结表里该态
        出边为空集，状态机会拒绝。

        Args:
            task_id: 任务标识。
            error_json: 归一化错误信封的 JSON 文本（**只**放 20 码字段，`docs/07` §14.3）。
            expected_status: 给了就要求当前状态**恰为**该值（否则影响 0 行）。

        Returns:
            `True` 表示影响 1 行；`False` 表示影响 0 行（不存在 / 状态不符）——
            本层**不**抛异常，由调用方判定。
        """
        ...

    async def update_progress(
        self,
        task_id: str,
        progress: int,
        *,
        tenant_id: str | None = None,
    ) -> bool:
        """写入进度（`docs/02` §31；`docs/07` §10.2 的**唯一**进度写入口）。

        ⚠️ `tenant_id` 是**新增的关键字**（`docs/02` §31 的
        `report(task_id, progress, message)` 三个位置参数**不变**）：给了就追加
        `AND tenant_id = :tenant`，与同契约的 `get(task_id, tenant_id)` 口径一致
        （`docs/02` §11 的租户隔离）；**不给**时保持原行为（只按主键），以便
        P29+ 的跨租户调用方不受影响。

        Args:
            task_id: 任务标识。
            progress: 已规整到 `[0, 100]` 的进度值（规整由 `progress.py` 负责）。
            tenant_id: 可选租户限制（`docs/02` §11）；缺省 `None` 表示不追加该条件。

        Returns:
            `True` 表示影响 1 行；`False` 表示该任务不存在（或不属于该租户）。
        """
        ...

    async def unfinished(
        self,
        *,
        statuses: Sequence[str],
        limit: int = 100,
    ) -> Sequence[TaskRecord]: ...

    async def list_steps(self, task_id: str) -> Sequence[TaskStepRecord]: ...

    async def update_step(
        self,
        step_id: str,
        *,
        status: str,
        result_json: str | None = None,
        error_json: str | None = None,
    ) -> bool: ...


# ===== P29–P35 Infrastructure（`docs/07` §12 P29–P35；`docs/02` §29–§41 / §55–§66）=====
#
# 为什么这些契约在 Domain（`docs/07` §14.1 / §2.2）：
# 本批的 Artifact / Document / Event / Audit / Trace 服务都落在 Application 层，
# 而它们需要读写 `artifacts` / `documents` / `audit_records`（P04 已落地的 24 张表之一）
# 与**尚未建表**的 `document_versions` / `event_records` / `trace_spans`
# （`docs/02` §39 列出，但不在 `docs/07` §4.3 的 24 张表内 —— 本批**不得改表**）。
# 故把「需要什么」收窄为下列结构化记录与契约（P03 的 `OperationRegistry`、
# P09 的 `SchemaLookup`、P10–P13 的 `SecurityStores`、P14–P18 的 `ResourceStore`、
# P21 的 `IdempotencyStore`、P22–P28 的 `TaskStore` 是同一做法的先例），
# 实现落在 `app/infrastructure/database/repositories/` 与 `app/observability/`。
#
# 🔴 记录类型只承载**非敏感**字段：本节的任何记录**都不得**携带
#    password / API key / access token / refresh token / private key / secret / credential
#    （`docs/07` §14.3；`docs/02` §9）。凭据只经运行环境注入，绝不落库 / 落日志 / 落文件。


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    """一条产物元数据的快照（`docs/07` §4.3 #21；`docs/02` §29 / §3.2）。

    字段与 P04 落地的 `artifacts` 表**逐列对应**（本批只**用**它，**不得**改表）：
    `storage_backend` / `storage_key` / `mime_type` / `size` / `checksum` / `task_id`。

    ⚠️ 产物**内容不落数据库**（`docs/07` §14.3：禁止无限 payload；`docs/02` §29 / §33）：
    库里只有 `artifact_id` / `storage_backend` / `storage_key` / `mime_type` / `size` /
    `checksum`，字节流经 `ArtifactStorage` 落在后端（Core Alpha = 本地文件系统）。

    ⚠️ `artifacts` 表**没有** `tenant_id` / `project_id` / `document_id` 列（`docs/07` §4.3 #21
    的 6 个关键字段里没有它们），本批**不得改表**。租户归属因此由 `storage_key` 的
    路径口径承载（`docs/02` §3.5：`{tenant_id}/{project_id}/{artifact_id}/payload`），
    由 `ArtifactService` 在**读写两侧**校验 —— 见该模块的裁决 2。
    """

    id: str
    storage_backend: str
    storage_key: str
    mime_type: str
    size: int
    checksum: str | None = None
    task_id: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ArtifactDraft:
    """待落库的产物元数据（`docs/02` §3.2 的列集合，去掉由实现生成的主键 / 时间）。

    `id` / `created_at` 由实现生成（P04 的 `UUIDPrimaryKeyMixin` / `TimestampMixin`）；
    本契约**只**承载调用方决定的值。
    """

    storage_backend: str
    storage_key: str
    mime_type: str
    size: int
    checksum: str
    task_id: str | None = None


class ArtifactStore(Protocol):
    """产物**元数据**的持久化契约（`docs/02` §3.2 / §36）。

    实现只 `INSERT` / `SELECT` / `DELETE`，**绝不** `commit` / `rollback`
    —— 事务边界归 P06 `UnitOfWork`（`docs/02` §16；`docs/07` §14.4）。
    字节流**不**经本契约（那是 `ArtifactStorage` 的职责，`docs/02` §29 / §33）。
    """

    async def create(self, draft: ArtifactDraft) -> ArtifactRecord: ...

    async def get(self, artifact_id: str) -> ArtifactRecord | None: ...

    async def delete(self, artifact_id: str) -> bool: ...

    async def list_for_task(self, task_id: str) -> Sequence[ArtifactRecord]: ...

    async def list_all(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ArtifactRecord]:
        """有界遍历全部产物（`docs/02` §22 Artifact Backup / §31 Artifact GC / §26 完整性检查）。

        `docs/07` §14.4 禁止无限 payload，故 `limit` 必填默认值、`offset` 显式分页。
        """
        ...


# ===== P30 Document（`docs/02` §30 / §57 / §4.1–§4.4）=====


@dataclass(frozen=True, slots=True)
class DocumentSnapshot:
    """一份文档的快照（`docs/07` §4.3 #15；`docs/02` §22 / §4.1）。

    字段与 P04 落地的 `documents` 表**逐列对应**：`project_id` / `model_id` / `name` /
    `path` / `status`（`docs/07` §4.3 #15 把该列写作 `lifecycle_state`，描述性写法；
    `docs/02` §22 的源码级列名是 `status`）。

    ⚠️ `documents` 表**没有** `tenant_id` 列：租户归属经 `project_id → projects.tenant_id`
    传递（`docs/02` §11 / §22），与 `ModelRecord` 同口径。
    ⚠️ `documents` 表**没有** `document_type` / `current_version` / `created_by` 列
    （`docs/02` §4.1 的 `Document` ORM 有，但不在 `docs/07` §4.3 的 24 张表内）——
    本批**不得改表**，故 `version` 由 `DocumentVersionStore` 提供，见该契约的说明。
    """

    id: str
    project_id: str
    name: str
    status: str
    model_id: str | None = None
    path: str | None = None
    version: int = 1


@dataclass(frozen=True, slots=True)
class DocumentDraft:
    """待创建的文档（`docs/02` §22 的列集合，去掉由实现生成的主键 / 时间）。"""

    project_id: str
    name: str
    status: str
    model_id: str | None = None
    path: str | None = None


class DocumentStore(Protocol):
    """文档的持久化契约（`docs/02` §22 / §4.4 / §36）。

    实现只 `INSERT` / `SELECT` / `UPDATE`，**绝不** `commit` / `rollback`
    （`docs/02` §16；`docs/07` §14.4）。
    """

    async def create(self, draft: DocumentDraft) -> DocumentSnapshot: ...

    async def get(self, document_id: str) -> DocumentSnapshot | None: ...

    async def update(
        self,
        document_id: str,
        *,
        fields: Mapping[str, object],
    ) -> DocumentSnapshot | None: ...

    async def delete(self, document_id: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class DocumentVersionRecord:
    """一个文档版本的快照（`docs/02` §4.2 的 `DocumentVersion`）。

    `docs/02` §4.2 给出的唯一约束是 `(document_id, version)`；本契约照抄该字段集合
    （`document_id` / `version` / `artifact_id` / `checksum`）。
    """

    id: str
    document_id: str
    version: int
    artifact_id: str
    checksum: str
    created_at: datetime | None = None


class DocumentVersionStore(Protocol):
    """文档版本的持久化契约（`docs/02` §4.2 / §50）。

    ⚠️ **Alpha 限制（已登记 `docs/07` §16 R52）**：`docs/02` §4.2 的 `document_versions`
    表**不在** `docs/07` §4.3 的 24 张表内，本批**不得改表**，故 Core Alpha 的实现是
    **进程内**的（与 `docs/02` §5.4 对 Outbox 的处理同一口径：明确记为 Alpha 限制并
    保留迁移接口）。需要持久化时以 **Alembic 迁移**新增表并实现本契约，
    **不得**静默改表（`docs/07` §14.3）。

    实现必须保证 `(document_id, version)` 唯一（`docs/02` §4.2）。
    """

    async def append(
        self,
        *,
        document_id: str,
        version: int,
        artifact_id: str,
        checksum: str,
    ) -> DocumentVersionRecord: ...

    async def latest(self, document_id: str) -> DocumentVersionRecord | None: ...

    async def list_for_document(self, document_id: str) -> Sequence[DocumentVersionRecord]: ...


# ===== P31 Event Bus / Outbox（`docs/02` §34 / §38 / §5–§6 / §42 / §58）=====


@dataclass(frozen=True, slots=True)
class EventRecordDraft:
    """待写入 Outbox 的一条事件（`docs/02` §6 的 `EventRecord` 列集合）。

    `payload_json` 是**业务**载荷的 JSON 文本；**不得**包含任何 secret
    （`docs/07` §14.3）。
    """

    event_type: str
    payload_json: str
    tenant_id: str | None = None
    project_id: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    task_id: str | None = None


@dataclass(frozen=True, slots=True)
class EventRecordSnapshot:
    """Outbox 中一条事件的快照（`docs/02` §6）。

    `status` 取值见 `app.domain.enums.EventRecordStatus`；`attempts` 是投递尝试次数
    （`docs/02` §42：`attempts++` / `retry` / `backoff` / `dead-letter`）。
    """

    id: str
    event_type: str
    payload_json: str
    status: str
    attempts: int
    created_at: datetime
    published_at: datetime | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    task_id: str | None = None


class EventRecordStore(Protocol):
    """Outbox 的持久化契约（`docs/02` §6 / §42 / §58）。

    ⚠️ **Alpha 限制（已登记 `docs/07` §16 R51）**：`docs/02` §6 的 `event_records` 表
    **不在** `docs/07` §4.3 的 24 张表内，本批**不得改表**；`docs/02` §5.4 明确允许
    「本阶段暂不实现完整 Outbox，但必须在代码层明确其为 Alpha 限制，并保留迁移接口」。
    Core Alpha 的实现是**进程内**的；需要持久化时以 **Alembic 迁移**新增表并实现本契约。

    实现只读写自身状态，**绝不** `commit` / `rollback`（`docs/02` §16）。
    """

    async def append(self, draft: EventRecordDraft) -> EventRecordSnapshot: ...

    async def pending(self, *, limit: int = 100) -> Sequence[EventRecordSnapshot]: ...

    async def mark_published(self, record_id: str) -> bool: ...

    async def mark_failed(self, record_id: str) -> bool: ...

    async def count(self) -> int: ...


# ===== P32 Audit（`docs/02` §39 / §44 / §65 / §7–§9）=====


@dataclass(frozen=True, slots=True)
class AuditEntryDraft:
    """待写入的一条审计记录（`docs/07` §4.3 #24；`docs/02` §7.1）。

    字段与 P04 落地的 `audit_records` 表**逐列对应**：`tenant_id` / `user_id` /
    `action` / `resource` / `result` / `previous_hash` / `entry_hash`。

    ⚠️ `audit_records` 表**没有** `request_id` / `trace_id` / `task_id` / `metadata_json`
    列（`docs/02` §7.1 有，但不在 `docs/07` §4.3 的 24 张表内）—— 本批**不得改表**，
    故哈希链的规范化载荷**只**由本契约的字段构成（见 `app/observability/audit.py`）。

    🔴 **绝不记录 secret**（`docs/07` §14.3；`docs/02` §9）：`resource` 只放资源标识，
    **不**放 payload / 凭据 / token。
    """

    tenant_id: str | None
    user_id: str | None
    action: str
    resource: str | None
    result: str
    previous_hash: str | None
    entry_hash: str


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """一条已落库的审计记录（`docs/02` §44 / §65 的字段清单）。

    `previous_hash` 为 `None` 表示链首；`entry_hash` 必填（`docs/02` §8.2）。
    """

    id: str
    tenant_id: str | None
    user_id: str | None
    action: str
    resource: str | None
    result: str
    previous_hash: str | None
    entry_hash: str
    created_at: datetime


class AuditStore(Protocol):
    """审计记录的持久化契约（`docs/02` §7 / §8 / §43）。

    🔴 **append-only**：实现**只**提供 `append` 与读取，**不得**提供 `update` /
    `delete`（`docs/02` §65「普通用户不得删除」；§44「用于检测篡改」）。

    ⚠️ 审计写入必须与业务写**同一** `UnitOfWork`（`docs/02` §35；`docs/07` §14.3）：
    实现持有调用方给的会话，**绝不** `commit` / `rollback`，因此「业务失败 → 审计一起回滚」
    是**结构性**的，而不是靠调用方记得清理。
    """

    async def append(self, draft: AuditEntryDraft) -> AuditEntry: ...

    async def last_hash(self, *, tenant_id: str | None = None) -> str | None: ...

    async def chain(
        self,
        *,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> Sequence[AuditEntry]: ...

    async def count(self) -> int: ...


# ===== P33 Trace（`docs/02` §61 / §63 / §11–§12 / §44）=====


@dataclass(frozen=True, slots=True)
class TraceSpanRecord:
    """一个 Span 的快照（`docs/02` §11 的 `TraceSpan`）。

    `name` / `kind` 取值见 `app.domain.enums.TraceSpanKind`（`docs/02` §63 的标准 Span
    清单）；`status` 取值见 `app.domain.enums.TraceStatus`。

    ⚠️ `trace_spans` 表**不在** `docs/07` §4.3 的 24 张表内（`docs/02` §11 有），
    本批**不得改表**；Core Alpha 的实现是**进程内**的（Alpha 限制，见
    `EventRecordStore` 的同口径说明），保留迁移接口。
    """

    id: str
    trace_id: str
    name: str
    kind: str
    status: str
    start_time: datetime
    end_time: datetime | None = None
    parent_span_id: str | None = None
    request_id: str | None = None
    task_id: str | None = None
    attributes_json: str = "{}"


class TraceStore(Protocol):
    """Span 的持久化契约（`docs/02` §11 / §44 / §53）。

    🔴 **Trace 数据不允许修改**（`docs/02` §44）：实现只提供追加与「结束 Span」
    （写 `end_time` / `status`），**不得**提供任意字段的更新 / 删除。
    """

    async def append(self, record: TraceSpanRecord) -> TraceSpanRecord: ...

    async def finish(self, span_id: str, *, status: str, end_time: datetime) -> bool: ...

    async def by_trace(self, trace_id: str) -> Sequence[TraceSpanRecord]: ...

    async def by_request(self, request_id: str) -> Sequence[TraceSpanRecord]: ...

    async def by_task(self, task_id: str) -> Sequence[TraceSpanRecord]: ...

    async def count(self) -> int: ...


# ===== P34 Health（`docs/02` §41 / §17 / §46 / §94）=====


class HealthChecker(Protocol):
    """健康检查器（`docs/02` §17，逐字照抄签名）。

    返回的映射**必须**含 `status`（取值见 `app.domain.enums.HealthStatus`），
    其余键由检查器自定（`docs/02` §16.3 的 `/health` 返回形状）。

    🔴 单个软件不可用 **≠** Core DOWN（`docs/02` §16.3 / §94；`docs/07` §14.4）：
    检查器**不得**抛出 —— 失败必须如实表达为 `UNAVAILABLE` / `DEGRADED` 的**数据**。
    """

    async def check(self) -> Mapping[str, Any]: ...


# ===== P35 Quota / Rate Limit（`docs/02` §36 / §40 / §60）=====


@dataclass(frozen=True, slots=True)
class QuotaLimits:
    """一个维度的配额上限（`docs/02` §36 / §60 的五个指标）。

    ⚠️ `0` 表示**不限**（与 P22–P28 `ConcurrencyLimits.global_limit = 0` 同口径）；
    负数是装配错误，由 `QuotaService` 拒绝。

    `docs/02` §36 的「Core Alpha 可使用内存 limiter + DB quota definition」：
    `quota` 的 DB 定义表不在 24 张表内，故本批的上限经 `QuotaPolicySource` 注入
    （见 `app/application/services/quota.py` 的裁决）。
    """

    max_tasks: int = 0
    max_concurrent_tasks: int = 0
    max_api_requests: int = 0
    max_storage: int = 0
    max_projects: int = 0
    window_seconds: int = 60


class QuotaPolicySource(Protocol):
    """配额上限的来源（`docs/02` §36 / §60）。

    Application 层**不**依赖 `app.infrastructure`，故上限经本收窄契约注入；
    缺省实现返回全 `0`（不限），与「未配备配额表」的事实一致。
    """

    def limits_for(
        self,
        *,
        tenant_id: str,
        user_id: str,
        agent_id: str | None = None,
    ) -> QuotaLimits: ...


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """数据保留策略（`docs/02` §27；默认值照抄 §28 的「默认策略」表）。

    ⚠️ **Audit 不允许普通 retention job 直接删除**（`docs/02` §29 / §45）：
    本策略里的 `audit_days` 只是**登记**值，`RetentionService` 不提供清理审计的方法。
    """

    task_days: int = 30
    trace_days: int = 14
    audit_days: int = 365
    artifact_days: int = 90
    event_days: int = 30
    session_days: int = 7


# ===== P35 Notification（`docs/02` §35 / §45 / §59）=====


@dataclass(frozen=True, slots=True)
class NotificationMessage:
    """一条待投递的通知（`docs/02` §35 / §59）。

    ⚠️ `payload` **不得**包含任何 secret（`docs/07` §14.3）；Notification 不成为 Core Tool
    （`docs/02` §35），故本契约只存在于进程内。
    """

    channel: str
    event_type: str
    payload: Mapping[str, Any]
    trace_id: str | None = None
    task_id: str | None = None


class NotificationSink(Protocol):
    """通知投递出口（`docs/02` §35 / §59：MCP Notification / Webhook / WebSocket / UI / Email）。

    Core Alpha 只实现 `InProcess`（`docs/02` §59）；其余通道经本契约预留。
    实现**不得**抛出 —— 通知失败不得影响业务结果（`docs/07` §14.4：
    单实例 / 单通道失败不得让整个服务器不可用）。
    """

    async def deliver(self, message: NotificationMessage) -> None: ...


# ===== P35 Adapter Resolution（`docs/02` §87 / §13 / §56）=====


class AdapterResolverSource(Protocol):
    """`AdapterResolver` 的数据源收窄契约（`docs/02` §87 / §56）。

    `docs/02` §87 的解析链是
    `Software Instance → Vendor/Product/Version → Adapter Manifest → Capability →
    API Registry → Adapter`。Core Alpha 的该链条由 P19–P20 的 `AdapterManager`
    结构上满足（`resolve_for_instance` / `registered_keys` / `manifests`），
    而 Application 层**不得**依赖 `app.infrastructure`，故只声明这三个问题。
    """

    async def resolve_for_instance(self, software_instance_id: str) -> object: ...

    def adapter_for_instance(self, software_instance_id: str) -> object | None: ...

    def registered_keys(self) -> Sequence[tuple[str, str]]: ...


# ===== P29–P35 Observability 的 Application 侧收窄契约 =====
#
# `docs/07` §2.2 的冻结依赖方向是 `Interface → Application → Domain`，本项目的既有红线
# 进一步禁止 `app/application/**` 依赖 `app.infrastructure`（P03–P22 的测试逐条断言）。
# `app/observability/` 是 app 根下的**旁路支撑层**（`docs/07` §3.3），因此执行主干
# **不**直接引用它，而是依赖下列收窄契约 —— 实现由 `app/observability/` 的三个服务
# **结构上**满足（与 R38 的 `RuntimeCapabilitySource` 同一做法）。


class AuditRecorder(Protocol):
    """审计写入的收窄契约（`docs/02` §8.3 的 `AuditService.record`）。

    `context` 声明为 `object`：实现只经 `getattr` 读取 `context.identity.tenant_id` /
    `user_id`（与 `app/application/resource/resolver.py` 同一手法），
    使本契约不依赖 `app.application.execution.context`（避免环状依赖）。

    🔴 实现必须与业务写**同一** `UnitOfWork`（`docs/02` §35），且**绝不**记录 secret
    （`docs/07` §14.3）。
    """

    async def record_context(
        self,
        context: object,
        *,
        action: str,
        result: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> AuditEntry: ...


class TraceRecorder(Protocol):
    """链路追踪的收窄契约（`docs/02` §10 / §11）。

    签名即 `docs/02` §10 的 `TraceService`（`start_span` / `end_span`），
    并按 §11 的 `TraceSpan` 字段补足关键字参数。
    """

    async def start_span(
        self,
        name: str,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
        attributes: Mapping[str, Any] | None = None,
        *,
        kind: str = "TOOL",
        request_id: str | None = None,
        task_id: str | None = None,
    ) -> TraceSpanRecord: ...

    async def end_span(
        self,
        span: TraceSpanRecord,
        status: str = "OK",
    ) -> TraceSpanRecord | None: ...


class MetricsRecorder(Protocol):
    """指标写入的收窄契约（`docs/02` §13 的 `MetricsService`，三个方法逐字照抄）。

    ⚠️ 标签里**不得**出现 secret（`docs/07` §14.3）；高基数 ID 不应作为 label
    （`docs/02` §15）。
    """

    def counter(
        self,
        name: str,
        value: float = 1,
        labels: Mapping[str, str] | None = None,
    ) -> None: ...

    def gauge(
        self,
        name: str,
        value: float,
        labels: Mapping[str, str] | None = None,
    ) -> None: ...

    def observe(
        self,
        name: str,
        value: float,
        labels: Mapping[str, str] | None = None,
    ) -> None: ...
