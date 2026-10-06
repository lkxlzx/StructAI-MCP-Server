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

    async def update_progress(self, task_id: str, progress: int) -> bool: ...

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
