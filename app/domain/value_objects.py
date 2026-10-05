"""Value Objects —— 不可变值对象（`docs/02` §10；`docs/07` §4.2）。

权威来源：

- `docs/02` §10（`source7` §10）—— `TenantId` / `ProjectId` / `ModelId` /
  `DocumentId` / `SoftwareInstanceId` / `OperationName` / `CapabilityName`，
  字段与 `__post_init__` 校验逐项照抄。
- `docs/02` §8（`blue` §8）—— `RequestIdentity(request_id, trace_id)`，以及
  `ResourceRef` / `VersionRef` / `Pagination` / `IdempotencyKey` /
  `SoftwareRef` / `ProjectRef` / `ModelRef` / `DocumentRef`；规范只给出名字，
  字段按同一份规范的其他章节推导（见各类注释）。
- `docs/02` §8 / §9（`impl` / `py`）—— `ResourceRef(resource_type, resource_id)` 的字段。
- `docs/02` §31 / §35 —— 分页参数为 `limit` / `cursor`（`has_more` / `next_cursor`
  属**响应**信封，由 Application 层在 P37+ 组装，不在值对象里）。
- `docs/07` §4.2 —— 上述名单的冻结摘要。

不放进本文件的对象（避免与后续批次重复定义）：

- `IdentityContext` / `SoftwareContext` / `ProjectContext` / `ResourceContext` /
  `ExecutionContext` —— 规范把执行上下文归到应用层
  （`docs/02` §10 / `docs/02` §29，文件 `app/application/execution/context.py`，P14 批次）。
- `OperationDefinition` —— 按 `docs/02` §11（`source7` §11）放在
  `app/domain/protocols.py`（P03 同批产出）。

分层红线（`docs/07` §14.1；`docs/02` §6）：只依赖标准库，不得引用任何 ORM / Web 框架 /
MCP SDK / HTTP 客户端，也不得出现厂商专属内容。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from uuid import UUID

__all__ = [
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

DEFAULT_PAGE_LIMIT: Final[int] = 50
"""默认分页大小（`docs/07` §14.4：禁止无限 payload，必须分页）。"""


# ===== `docs/02` §10（source7 §10）—— 身份包装 =====


@dataclass(frozen=True, slots=True)
class TenantId:
    """租户标识（`docs/02` §10）。"""

    value: UUID


@dataclass(frozen=True, slots=True)
class ProjectId:
    """项目标识（`docs/02` §10）。"""

    value: UUID


@dataclass(frozen=True, slots=True)
class ModelId:
    """模型标识（`docs/02` §10）。"""

    value: UUID


@dataclass(frozen=True, slots=True)
class DocumentId:
    """文档标识（`docs/02` §10）。"""

    value: UUID


@dataclass(frozen=True, slots=True)
class SoftwareInstanceId:
    """软件实例标识（`docs/02` §10）。"""

    value: UUID


@dataclass(frozen=True, slots=True)
class OperationName:
    """操作名（`docs/02` §10）。

    取值形如 `BUILD.COLUMN`（`docs/07` §1.1：Tool ≠ API）；非空校验照抄规范。
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("Operation name cannot be empty")


@dataclass(frozen=True, slots=True)
class CapabilityName:
    """能力名（`docs/02` §10）。

    取值形如 `MODEL.NODE.WRITE`（`docs/07` §5.6）；非空校验照抄规范。
    能力是软件无关的，取值中不得出现厂商名（`docs/07` §14.2）。
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("Capability name cannot be empty")


# ===== `docs/02` §8（blue §8）+ §8/§9（impl/py §8）=====


@dataclass(frozen=True, slots=True)
class RequestIdentity:
    """请求身份（`docs/02` §8）。

    只承载服务端生成的关联标识；**客户端不得**用它声明 `user_id` /
    `tenant_id` / `roles` / `permissions`（`docs/07` §14.3）。
    """

    request_id: str
    trace_id: str


@dataclass(frozen=True, slots=True)
class ResourceRef:
    """资源引用（`docs/02` §8 / §9）。

    字段照抄规范（`resource_type: str` / `resource_id: str`）；`resource_type`
    的取值集合见 `app.domain.enums.ResourceType`。
    """

    resource_type: str
    resource_id: str


@dataclass(frozen=True, slots=True)
class VersionRef:
    """版本引用（`docs/02` §8；`docs/07` §10.4 乐观并发）。

    用于乐观并发的 `version` 与软件版本区间的字符串表示；
    规范未给出字段，此处取单一字符串值并做非空校验。
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("Version reference cannot be empty")


@dataclass(frozen=True, slots=True)
class Pagination:
    """分页参数（`docs/02` §31 / §35）。

    - `limit` 必须为正：规范禁止无限 payload（`docs/07` §14.4）。
    - `cursor` 为不透明游标；`None` 表示从头开始。
    - `has_more` / `next_cursor` 属响应信封，不在本对象内。
    """

    limit: int = DEFAULT_PAGE_LIMIT
    cursor: str | None = None

    def __post_init__(self) -> None:
        if self.limit <= 0:
            raise ValueError("Pagination limit must be positive")


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    """幂等键（`docs/02` §8 / §28）。

    唯一性由 `(tenant_id, idempotency_key)` 数据库唯一约束保证，且必须
    原子 `INSERT` 而非 `SELECT` 后 `INSERT`（`docs/02` §28 / §32）。
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("Idempotency key cannot be empty")


@dataclass(frozen=True, slots=True)
class SoftwareRef:
    """软件实例引用（`docs/02` §8；`docs/07` §4.2）。

    规范只给出名字；按 `SoftwareInstanceId` 同构，包装软件实例 UUID。
    """

    value: UUID


@dataclass(frozen=True, slots=True)
class ProjectRef:
    """项目引用（`docs/02` §8；`docs/07` §4.2）。

    与 `ProjectId` 同构的引用语义包装，规范给出两个名字，二者都保留。
    """

    value: UUID


@dataclass(frozen=True, slots=True)
class ModelRef:
    """模型引用（`docs/02` §8；`docs/07` §4.2）。"""

    value: UUID


@dataclass(frozen=True, slots=True)
class DocumentRef:
    """文档引用（`docs/02` §8；`docs/07` §4.2）。"""

    value: UUID
