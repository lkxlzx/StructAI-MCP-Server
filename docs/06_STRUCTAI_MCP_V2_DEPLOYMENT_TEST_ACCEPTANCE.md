# 06_STRUCTAI_MCP_V2_DEPLOYMENT_TEST_ACCEPTANCE.md — 部署、测试与最终验收

V2.0 Consolidated Deployment / Test / Acceptance Baseline。汇总已有规范中的 Definition of Done、Unit/Contract/Integration/Security/Concurrency/Recovery/E2E、Generic AI Client、CIVIL/GEN E2E、Health、Backup/Restore、Security 与 Production Hardening。并作为后续部署实施与发布 Gate 的统一入口。

---

# 内容保全说明

本主文档按六文档体系重新组织。**原有内容不删除**；各来源规范以完整原文收录在对应章节，确保代码、字段、状态、测试要求和实现约束均可追溯。


# 完整收录：source9

# StructAI MCP Server V2.0
# 第九份文档：Core Alpha 实际源码第一批（P01-P07）
## Core Bootstrap / Config / Domain / Database / Repository / UnitOfWork / Registry

> 文档定位：从“设计规范”进入“可直接落地源码”的第一批实现。
>
> 本批次只实现 Core Alpha 的基础骨架与数据访问层，不实现 MIDAS，不实现 MCP Tool，不实现 Task Engine，不实现 HTTP/STDIO。
>
> 目标：完成后可以启动项目、初始化 SQLite、执行 Alembic、创建基础数据库结构、运行 Domain/Repository/Registry 测试，为后续 Security、Execution、Task、Adapter、MCP 奠定稳定基础。

---

# 1. 本批次范围

## 1.1 实现范围

```text
P01 Project Bootstrap
P02 Config
P03 Domain
P04 Database
P05 Repository
P06 UnitOfWork
P07 Registry
```

对应：

```text
pyproject.toml
README.md
.env.example

app/main.py
app/container.py

app/config/*
app/domain/*

app/infrastructure/database/*
app/infrastructure/registry/*

tests/unit/*
tests/integration/*
```

## 1.2 明确不实现

本批次不实现：

- MIDAS Adapter
- CSI Adapter
- MCP Server
- 9 MCP Tools
- Authentication
- Session
- RBAC
- Task Engine
- Scheduler
- Artifact Storage
- HTTP API
- Streamable HTTP
- STDIO
- AI Client
- UI

这些功能必须建立在本批次完成并测试通过之后。

---

# 2. 技术基线

```text
Python >= 3.12
SQLAlchemy 2.x
aiosqlite
Alembic
Pydantic 2.x
pydantic-settings
pytest
pytest-asyncio
httpx
```

数据库：

```text
SQLite
```

Core Alpha 默认：

```text
sqlite+aiosqlite:///./data/structai.db
```

原则：

1. SQLite 是第一阶段真实数据库。
2. 所有数据库访问统一异步。
3. Domain 不依赖 SQLAlchemy。
4. Repository 隔离 ORM。
5. UnitOfWork 统一事务边界。
6. Registry 是软件无关的。
7. 不允许在 Core 中出现 MIDAS endpoint。
8. 不允许把 vendor API 名称作为 Operation 名称。

---

# 3. 目录

```text
structai-mcp/
├── pyproject.toml
├── README.md
├── .env.example
├── .gitignore
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── container.py
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py
│   │   ├── runtime_config.py
│   │   └── logging.py
│   │
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── enums.py
│   │   ├── errors.py
│   │   ├── value_objects.py
│   │   ├── events.py
│   │   └── protocols.py
│   │
│   └── infrastructure/
│       ├── __init__.py
│       ├── database/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── session.py
│       │   ├── unit_of_work.py
│       │   ├── models/
│       │   ├── repositories/
│       │   └── seed.py
│       │
│       └── registry/
│           ├── __init__.py
│           ├── registry.py
│           └── repository.py
│
├── migrations/
│   ├── env.py
│   └── versions/
│
├── tests/
│   ├── unit/
│   │   ├── test_domain.py
│   │   └── test_registry.py
│   └── integration/
│       └── test_database.py
│
└── data/
```

---

# 4. pyproject.toml

```toml
[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "structai-mcp-server"
version = "2.0.0a1"
description = "StructAI MCP Server Core Alpha"
requires-python = ">=3.12"
dependencies = [
    "SQLAlchemy>=2.0,<3.0",
    "aiosqlite>=0.20,<1.0",
    "alembic>=1.14,<2.0",
    "pydantic>=2.9,<3.0",
    "pydantic-settings>=2.6,<3.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0,<9.0",
    "pytest-asyncio>=0.24,<1.0",
    "httpx>=0.27,<1.0",
    "ruff>=0.8,<1.0",
    "mypy>=1.13,<2.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.setuptools.packages.find]
include = ["app*"]
```

---

# 5. 配置

## 5.1 settings.py

```python
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "StructAI MCP Server"
    app_version: str = "2.0.0-alpha"

    environment: str = "development"
    debug: bool = True

    database_url: str = "sqlite+aiosqlite:///./data/structai.db"

    sql_echo: bool = False

    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def data_dir(self) -> Path:
        if self.database_url.startswith("sqlite"):
            return Path("./data")
        return Path("./data")


settings = Settings()
```

---

# 6. Runtime Config

```python
from dataclasses import dataclass


@dataclass(slots=True)
class RuntimeConfig:
    environment: str
    debug: bool
    database_url: str
    log_level: str
```

构造：

```python
from app.config.settings import settings
from app.config.runtime_config import RuntimeConfig


def build_runtime_config() -> RuntimeConfig:
    return RuntimeConfig(
        environment=settings.environment,
        debug=settings.debug,
        database_url=settings.database_url,
        log_level=settings.log_level,
    )
```

---

# 7. Logging

```python
import logging


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=(
            "%(asctime)s %(levelname)s "
            "%(name)s %(message)s"
        ),
    )
```

后续 Trace/Audit 阶段再扩展结构化字段：

```text
trace_id
request_id
task_id
user_id
tenant_id
project_id
tool
operation
software
adapter
```

本阶段不提前耦合。

---

# 8. Domain Enums

`app/domain/enums.py`

```python
from enum import StrEnum


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ExecutionMode(StrEnum):
    SYNC = "SYNC"
    ASYNC = "ASYNC"
    STREAM = "STREAM"


class TaskStatus(StrEnum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    RETRYING = "RETRYING"
    RECOVERING = "RECOVERING"


class ResourceType(StrEnum):
    SOFTWARE_INSTANCE = "SOFTWARE_INSTANCE"
    PROJECT = "PROJECT"
    MODEL = "MODEL"
    DOCUMENT = "DOCUMENT"


class LockMode(StrEnum):
    READ = "READ"
    WRITE = "WRITE"
    EXCLUSIVE = "EXCLUSIVE"


class CapabilityStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


class SoftwareStatus(StrEnum):
    REGISTERED = "REGISTERED"
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


class DocumentStatus(StrEnum):
    NEW = "NEW"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class ArtifactStatus(StrEnum):
    CREATED = "CREATED"
    READY = "READY"
    DELETED = "DELETED"
```

---

# 9. Domain Errors

`app/domain/errors.py`

```python
class StructAIError(Exception):
    code = "STRUCTAI-7000"

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(StructAIError):
    code = "STRUCTAI-1100"


class EngineeringValidationError(StructAIError):
    code = "STRUCTAI-1200"


class ConcurrencyError(StructAIError):
    code = "STRUCTAI-1300"


class CapabilityError(StructAIError):
    code = "STRUCTAI-3000"


class PermissionDeniedError(StructAIError):
    code = "STRUCTAI-4000"


class ConfirmationRequiredError(StructAIError):
    code = "STRUCTAI-4100"


class ResourceLockedError(StructAIError):
    code = "STRUCTAI-6100"


class NotFoundError(StructAIError):
    code = "STRUCTAI-7001"


class DuplicateError(StructAIError):
    code = "STRUCTAI-7002"


class ConfigurationError(StructAIError):
    code = "STRUCTAI-7003"
```

---

# 10. Value Objects

`app/domain/value_objects.py`

```python
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TenantId:
    value: UUID


@dataclass(frozen=True, slots=True)
class ProjectId:
    value: UUID


@dataclass(frozen=True, slots=True)
class ModelId:
    value: UUID


@dataclass(frozen=True, slots=True)
class DocumentId:
    value: UUID


@dataclass(frozen=True, slots=True)
class SoftwareInstanceId:
    value: UUID


@dataclass(frozen=True, slots=True)
class OperationName:
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("Operation name cannot be empty")


@dataclass(frozen=True, slots=True)
class CapabilityName:
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("Capability name cannot be empty")
```

---

# 11. Operation Definition

放入 `app/domain/protocols.py`

```python
from dataclasses import dataclass

from .enums import ExecutionMode, RiskLevel


@dataclass(frozen=True, slots=True)
class OperationDefinition:
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
```

---

# 12. Domain Events

`app/domain/events.py`

```python
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class DomainEvent:
    event_id: UUID
    occurred_at: datetime

    @classmethod
    def create(cls):
        return cls(
            event_id=uuid4(),
            occurred_at=datetime.now(timezone.utc),
        )


@dataclass(frozen=True, slots=True)
class ModelChanged(DomainEvent):
    model_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AdapterConnected(DomainEvent):
    software_instance_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AdapterDisconnected(DomainEvent):
    software_instance_id: UUID | None = None
```

---

# 13. Domain Protocols

```python
from typing import Protocol, Any

from .protocols import OperationDefinition


class OperationRegistry(Protocol):
    async def register(self, definition: OperationDefinition) -> None:
        ...

    async def get(self, name: str) -> OperationDefinition | None:
        ...

    async def list(self) -> list[OperationDefinition]:
        ...


class EventBus(Protocol):
    async def publish(self, event: Any) -> None:
        ...


class CredentialProvider(Protocol):
    async def get_secret(self, reference: str) -> str:
        ...

    async def set_secret(self, reference: str, value: str) -> None:
        ...

    async def delete_secret(self, reference: str) -> None:
        ...
```

---

# 14. SQLAlchemy Base

`app/infrastructure/database/base.py`

```python
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
```

---

# 15. Database Session

`app/infrastructure/database/session.py`

```python
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    return create_async_engine(
        database_url,
        echo=echo,
        future=True,
    )


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine,
        expire_on_commit=False,
        autoflush=False,
    )
```

---

# 16. UnitOfWork

`app/infrastructure/database/unit_of_work.py`

```python
from sqlalchemy.ext.asyncio import AsyncSession


class UnitOfWork:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type:
            await self.session.rollback()
        else:
            await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def commit(self) -> None:
        await self.session.commit()
```

规则：

```text
Application Service
      ↓
UnitOfWork
      ↓
Repository
      ↓
SQLAlchemy
```

Repository 不负责决定事务何时提交。

---

# 17. ORM 模型原则

ORM 只负责：

- persistence
- indexes
- foreign keys
- unique constraints
- database-level consistency

ORM 不负责：

- MCP protocol
- permission decision
- capability decision
- adapter logic
- engineering calculation
- AI logic

---

# 18. 核心 ORM 模型

## 18.1 Tenant

```python
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class TenantORM(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        unique=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
```

---

# 19. User / Role / Permission

## User

```python
class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
```

## Role

```python
class RoleORM(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
```

## Permission

```python
class PermissionORM(Base):
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        unique=True,
    )
```

## UserRole

```python
class UserRoleORM(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )

    role_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )
```

## RolePermission

```python
class RolePermissionORM(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )

    permission_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )
```

> 本批次只建立 persistence 结构；真正的认证/RBAC逻辑放在后续 Security 批次。

---

# 20. Project / ProjectMember

```python
class ProjectORM(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class ProjectMemberORM(Base):
    __tablename__ = "project_members"

    project_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    role: Mapped[str] = mapped_column(String(100), nullable=False)
```

---

# 21. Software Registry ORM

## Software

```python
class SoftwareORM(Base):
    __tablename__ = "software"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    vendor: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
```

## SoftwareProduct

```python
class SoftwareProductORM(Base):
    __tablename__ = "software_products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    software_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    product: Mapped[str] = mapped_column(String(150), nullable=False)
```

## SoftwareVersion

```python
class SoftwareVersionORM(Base):
    __tablename__ = "software_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
```

## SoftwareInstance

```python
class SoftwareInstanceORM(Base):
    __tablename__ = "software_instances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    endpoint: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
```

---

# 22. Model / Document

## Model

```python
class ModelORM(Base):
    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    software_instance_id: Mapped[str | None] = mapped_column(
        String(36),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
```

## Document

```python
class DocumentORM(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    model_id: Mapped[str | None] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    path: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
```

---

# 23. Capability / Operation

## Capability

```python
class CapabilityORM(Base):
    __tablename__ = "capabilities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(
        String(200),
        unique=True,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(String(500))
```

## Operation

```python
class OperationORM(Base):
    __tablename__ = "operations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(
        String(200),
        unique=True,
        nullable=False,
    )
    tool: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(30), nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    input_schema: Mapped[str] = mapped_column(String(500), nullable=False)
    output_schema: Mapped[str] = mapped_column(String(500), nullable=False)
```

## OperationCapability

```python
class OperationCapabilityORM(Base):
    __tablename__ = "operation_capabilities"

    operation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    capability_id: Mapped[str] = mapped_column(String(36), primary_key=True)
```

---

# 24. Task / Artifact / Lock / Idempotency / Audit

这些表先建立最小 persistence contract，具体业务在后续批次实现。

## Task

```python
class TaskORM(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), index=True)

    request_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    trace_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    tool: Mapped[str] = mapped_column(String(100), nullable=False)
    operation: Mapped[str] = mapped_column(String(200), nullable=False)

    status: Mapped[str] = mapped_column(String(40), nullable=False)
    progress: Mapped[int] = mapped_column(default=0, nullable=False)
```

## Artifact

```python
class ArtifactORM(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str | None] = mapped_column(String(36), index=True)
    storage_backend: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(2000), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(200), nullable=False)
    size: Mapped[int] = mapped_column(default=0, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(200))
```

## ResourceLock

```python
class ResourceLockORM(Base):
    __tablename__ = "resource_locks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False)
    mode: Mapped[str] = mapped_column(String(30), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(100), nullable=False)
```

## Idempotency

```python
class IdempotencyRecordORM(Base):
    __tablename__ = "idempotency_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(300), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    response_json: Mapped[str | None] = mapped_column(String)
```

## Audit

```python
class AuditRecordORM(Base):
    __tablename__ = "audit_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)

    action: Mapped[str] = mapped_column(String(200), nullable=False)
    resource: Mapped[str | None] = mapped_column(String(500))
    result: Mapped[str] = mapped_column(String(30), nullable=False)

    previous_hash: Mapped[str | None] = mapped_column(String(128))
    entry_hash: Mapped[str] = mapped_column(String(128), nullable=False)
```

---

# 25. ORM Model Export

`app/infrastructure/database/models/__init__.py`

```python
from .tenant import TenantORM
from .user import UserORM
from .role import RoleORM
from .permission import PermissionORM
from .project import ProjectORM
from .software import (
    SoftwareORM,
    SoftwareProductORM,
    SoftwareVersionORM,
    SoftwareInstanceORM,
)
from .model import ModelORM
from .document import DocumentORM
from .registry import CapabilityORM, OperationORM, OperationCapabilityORM
from .task import TaskORM
from .artifact import ArtifactORM
from .resource_lock import ResourceLockORM
from .idempotency import IdempotencyRecordORM
from .audit import AuditRecordORM

__all__ = [
    "TenantORM",
    "UserORM",
    "RoleORM",
    "PermissionORM",
    "ProjectORM",
    "SoftwareORM",
    "SoftwareProductORM",
    "SoftwareVersionORM",
    "SoftwareInstanceORM",
    "ModelORM",
    "DocumentORM",
    "CapabilityORM",
    "OperationORM",
    "OperationCapabilityORM",
    "TaskORM",
    "ArtifactORM",
    "ResourceLockORM",
    "IdempotencyRecordORM",
    "AuditRecordORM",
]
```

实际工程中每个 ORM 类建议独立文件，避免单文件过大。

---

# 26. Repository Contract

`app/infrastructure/database/repositories/base.py`

```python
from typing import Generic, TypeVar

T = TypeVar("T")


class Repository(Generic[T]):
    async def get(self, entity_id: str) -> T | None:
        raise NotImplementedError

    async def add(self, entity: T) -> T:
        raise NotImplementedError

    async def delete(self, entity: T) -> None:
        raise NotImplementedError
```

---

# 27. Registry Repository

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CapabilityORM, OperationORM


class CapabilityRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_code(self, code: str):
        result = await self.session.execute(
            select(CapabilityORM).where(
                CapabilityORM.code == code
            )
        )
        return result.scalar_one_or_none()

    async def list_all(self):
        result = await self.session.execute(
            select(CapabilityORM).order_by(CapabilityORM.code)
        )
        return list(result.scalars().all())


class OperationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_name(self, name: str):
        result = await self.session.execute(
            select(OperationORM).where(
                OperationORM.name == name
            )
        )
        return result.scalar_one_or_none()

    async def list_all(self):
        result = await self.session.execute(
            select(OperationORM).order_by(OperationORM.name)
        )
        return list(result.scalars().all())
```

---

# 28. Core Operation Registry

`app/infrastructure/registry/registry.py`

```python
from app.domain.protocols import OperationDefinition


class InMemoryOperationRegistry:
    def __init__(self):
        self._operations: dict[str, OperationDefinition] = {}

    async def register(self, definition: OperationDefinition) -> None:
        self._operations[definition.name] = definition

    async def get(self, name: str) -> OperationDefinition | None:
        return self._operations.get(name)

    async def list(self) -> list[OperationDefinition]:
        return list(self._operations.values())
```

Core Alpha 使用：

```text
Database Registry
+
Runtime Registry
```

数据库保存：

```text
operation
capability
software
product
version
mapping
```

运行时保存：

```text
OperationDefinition
compiled lookup
adapter implementation
```

---

# 29. Operation Seed

建立：

```text
scripts/seed_operations.py
```

第一阶段至少注册：

```text
engineering_doc:
NEW
OPEN
SAVE
SAVE_AS
CLOSE
INFO

engineering_model_query:
MODEL.QUERY
MODEL.NODE.QUERY
MODEL.ELEMENT.QUERY
MODEL.MATERIAL.QUERY
MODEL.SECTION.QUERY
MODEL.BOUNDARY.QUERY
MODEL.LOAD.QUERY
MODEL.GROUP.QUERY

engineering_model_assign:
MODEL.NODE.CREATE
MODEL.NODE.UPDATE
MODEL.ELEMENT.CREATE
MODEL.ELEMENT.UPDATE
MODEL.MATERIAL.ASSIGN
MODEL.SECTION.ASSIGN
MODEL.BOUNDARY.ASSIGN
MODEL.LOAD.ASSIGN

engineering_model_delete:
MODEL.NODE.DELETE
MODEL.ELEMENT.DELETE
MODEL.LOAD.DELETE
MODEL.BOUNDARY.DELETE
MODEL.GROUP.DELETE
MODEL.MATERIAL.DELETE
MODEL.SECTION.DELETE

engineering_model_build:
BUILD.NODE_GRID
BUILD.BEAM
BUILD.COLUMN
BUILD.FRAME
BUILD.TRUSS
BUILD.SLAB
BUILD.WALL
BUILD.FOUNDATION
BUILD.STEEL_FRAME
MODEL.COPY
MODEL.MOVE
MODEL.MIRROR
MODEL.PATTERN
MODEL.GENERATE_GRID

engineering_view:
VIEW.MODEL
VIEW.DEFORMED_MODEL
VIEW.REACTION
VIEW.DISPLACEMENT
VIEW.STRESS
VIEW.FORCE
VIEW.MODE_SHAPE

engineering_result:
RESULT.NODE.DISPLACEMENT
RESULT.NODE.REACTION
RESULT.ELEMENT.FORCE
RESULT.ELEMENT.STRESS
RESULT.MODE.SHAPE
RESULT.ANALYSIS.SUMMARY

engineering_design:
DESIGN.STEEL
DESIGN.CONCRETE
DESIGN.SRC
DESIGN.FOUNDATION
DESIGN.CODE_CHECK
DESIGN.OPTIMIZE

engineering_analysis:
ANALYSIS.STATIC
ANALYSIS.MODAL
ANALYSIS.SEISMIC
ANALYSIS.SPECTRUM
ANALYSIS.BUCKLING
ANALYSIS.TIME_HISTORY
ANALYSIS.NONLINEAR
```

---

# 30. Capability Seed

至少：

```text
MODEL.NODE.READ
MODEL.NODE.WRITE
MODEL.NODE.DELETE
MODEL.ELEMENT.READ
MODEL.ELEMENT.WRITE
MODEL.ELEMENT.DELETE
MODEL.MATERIAL.READ
MODEL.MATERIAL.WRITE
MODEL.SECTION.READ
MODEL.SECTION.WRITE
MODEL.BOUNDARY.READ
MODEL.BOUNDARY.WRITE
MODEL.LOAD.READ
MODEL.LOAD.WRITE
MODEL.LOAD.DELETE

ANALYSIS.STATIC
ANALYSIS.MODAL
ANALYSIS.SEISMIC
ANALYSIS.SPECTRUM
ANALYSIS.BUCKLING
ANALYSIS.TIME_HISTORY
ANALYSIS.NONLINEAR

RESULT.DISPLACEMENT
RESULT.REACTION
RESULT.ELEMENT_FORCE
RESULT.STRESS
RESULT.MODE_SHAPE

DESIGN.STEEL
DESIGN.CONCRETE
DESIGN.SRC
DESIGN.FOUNDATION
DESIGN.OPTIMIZATION
```

---

# 31. Operation → Capability 映射

例如：

```text
MODEL.NODE.QUERY
    → MODEL.NODE.READ

MODEL.NODE.CREATE
    → MODEL.NODE.WRITE

MODEL.NODE.UPDATE
    → MODEL.NODE.WRITE

MODEL.NODE.DELETE
    → MODEL.NODE.DELETE

MODEL.ELEMENT.QUERY
    → MODEL.ELEMENT.READ

MODEL.ELEMENT.CREATE
    → MODEL.ELEMENT.WRITE

MODEL.ELEMENT.DELETE
    → MODEL.ELEMENT.DELETE

ANALYSIS.STATIC
    → ANALYSIS.STATIC

RESULT.NODE.DISPLACEMENT
    → RESULT.DISPLACEMENT

DESIGN.STEEL
    → DESIGN.STEEL
```

原则：

```text
Operation
    ≠
Capability
```

Operation 是用户请求的动作。

Capability 是当前软件实例能够提供的能力。

---

# 32. Risk Seed

固定：

```text
engineering_doc            MEDIUM
engineering_model_query    LOW
engineering_model_assign   MEDIUM
engineering_model_delete   HIGH
engineering_model_build    HIGH
engineering_view           LOW
engineering_result         LOW
engineering_design         HIGH
engineering_analysis       HIGH
```

Execution：

```text
engineering_doc            SYNC / ASYNC
engineering_model_query    SYNC
engineering_model_assign   SYNC / ASYNC
engineering_model_delete   ASYNC
engineering_model_build    ASYNC
engineering_view           SYNC
engineering_result         SYNC
engineering_design         ASYNC
engineering_analysis       ASYNC
```

---

# 33. Bootstrap Container

`app/container.py`

```python
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.config.settings import Settings
from app.infrastructure.database.session import (
    create_engine,
    create_session_factory,
)
from app.infrastructure.registry.registry import (
    InMemoryOperationRegistry,
)


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    operation_registry: InMemoryOperationRegistry


def build_container(settings: Settings) -> AppContainer:
    engine = create_engine(
        settings.database_url,
        echo=settings.sql_echo,
    )

    session_factory = create_session_factory(engine)

    return AppContainer(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        operation_registry=InMemoryOperationRegistry(),
    )
```

---

# 34. main.py

```python
import asyncio
import logging

from app.config.logging import configure_logging
from app.config.settings import settings
from app.container import build_container


async def async_main() -> None:
    configure_logging(settings.log_level)

    logger = logging.getLogger("structai")
    container = build_container(settings)

    logger.info(
        "StructAI MCP Server initialized: version=%s",
        settings.app_version,
    )

    await container.engine.dispose()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
```

---

# 35. Alembic

初始化：

```bash
alembic init migrations
```

`migrations/env.py` 必须导入：

```python
from app.infrastructure.database.base import Base
from app.infrastructure.database import models

target_metadata = Base.metadata
```

生成迁移：

```bash
alembic revision --autogenerate -m "initial core schema"
```

执行：

```bash
alembic upgrade head
```

检查：

```bash
alembic current
```

---

# 36. SQLite 特别处理

SQLite 开发环境启用：

```sql
PRAGMA foreign_keys=ON;
```

SQLAlchemy event：

```python
from sqlalchemy import event


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
```

SQLite 初期：

```text
WAL
foreign_keys
busy_timeout
```

后续可加入：

```sql
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
```

不要在每个 Repository 中重复设置。

---

# 37. Database Integration Test

```python
import pytest

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_sqlite_connection():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:"
    )

    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar_one() == 1

    await engine.dispose()
```

---

# 38. Domain Test

```python
from app.domain.enums import ExecutionMode, RiskLevel
from app.domain.protocols import OperationDefinition


def test_operation_definition():
    definition = OperationDefinition(
        name="MODEL.NODE.QUERY",
        tool="engineering_model_query",
        risk_level=RiskLevel.LOW,
        execution_mode=ExecutionMode.SYNC,
        input_schema="structai://schema/model/node/query/v1",
        output_schema="structai://schema/model/node/result/v1",
        required_permissions=("MODEL_READ",),
        required_capabilities=("MODEL.NODE.READ",),
    )

    assert definition.name == "MODEL.NODE.QUERY"
    assert definition.tool == "engineering_model_query"
```

---

# 39. Registry Test

```python
import pytest

from app.domain.enums import ExecutionMode, RiskLevel
from app.domain.protocols import OperationDefinition
from app.infrastructure.registry.registry import (
    InMemoryOperationRegistry,
)


@pytest.mark.asyncio
async def test_registry_register_and_get():
    registry = InMemoryOperationRegistry()

    definition = OperationDefinition(
        name="MODEL.NODE.QUERY",
        tool="engineering_model_query",
        risk_level=RiskLevel.LOW,
        execution_mode=ExecutionMode.SYNC,
        input_schema="node-query-v1",
        output_schema="node-result-v1",
    )

    await registry.register(definition)

    result = await registry.get("MODEL.NODE.QUERY")

    assert result is not None
    assert result.name == "MODEL.NODE.QUERY"
```

---

# 40. Repository Test

```python
import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.infrastructure.database.base import Base
from app.infrastructure.database.models import CapabilityORM
from app.infrastructure.database.repositories.registry import (
    CapabilityRepository,
)


@pytest.mark.asyncio
async def test_capability_repository():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:"
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )

    async with factory() as session:
        item = CapabilityORM(
            id="cap-001",
            code="MODEL.NODE.READ",
        )

        session.add(item)
        await session.commit()

        repo = CapabilityRepository(session)

        result = await repo.get_by_code(
            "MODEL.NODE.READ"
        )

        assert result is not None
        assert result.code == "MODEL.NODE.READ"

    await engine.dispose()
```

---

# 41. 第一批测试要求

执行：

```bash
pytest -q
```

至少验证：

```text
[PASS] settings import
[PASS] domain enums
[PASS] OperationDefinition
[PASS] in-memory registry
[PASS] SQLite connection
[PASS] ORM metadata creation
[PASS] CapabilityRepository
[PASS] OperationRepository
[PASS] UnitOfWork commit
[PASS] UnitOfWork rollback
```

---

# 42. UnitOfWork Commit Test

```python
@pytest.mark.asyncio
async def test_uow_commit():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:"
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )

    async with factory() as session:
        async with UnitOfWork(session):
            session.add(
                CapabilityORM(
                    id="cap-commit",
                    code="MODEL.TEST.COMMIT",
                )
            )

    async with factory() as session:
        repo = CapabilityRepository(session)

        result = await repo.get_by_code(
            "MODEL.TEST.COMMIT"
        )

        assert result is not None

    await engine.dispose()
```

---

# 43. Rollback Test

```python
@pytest.mark.asyncio
async def test_uow_rollback():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:"
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )

    async with factory() as session:
        try:
            async with UnitOfWork(session):
                session.add(
                    CapabilityORM(
                        id="cap-rollback",
                        code="MODEL.TEST.ROLLBACK",
                    )
                )
                raise RuntimeError("force rollback")
        except RuntimeError:
            pass

    async with factory() as session:
        repo = CapabilityRepository(session)

        result = await repo.get_by_code(
            "MODEL.TEST.ROLLBACK"
        )

        assert result is None

    await engine.dispose()
```

---

# 44. 第一阶段禁止事项

以下代码不得进入 Core：

```python
# 禁止
if software == "MIDAS":
    ...

# 禁止
"/anal/STATIC"

# 禁止
midas_client.post(...)

# 禁止
from structai_midas import ...

# 禁止
tool_name = "midas_run_analysis"
```

正确：

```python
operation = "ANALYSIS.STATIC"

adapter = adapter_manager.resolve(
    software_context
)

await adapter.execute(
    operation,
    parameters,
    context,
)
```

---

# 45. Registry 最终边界

Registry 不执行 API。

Registry 只负责：

```text
Operation
Capability
Software
Product
Version
Instance
API Mapping
Schema
```

Adapter 才负责：

```text
HTTP
COM
REST
SOAP
Script
Native SDK
Parameter Transform
Response Transform
Native Error
```

---

# 46. 第一批完成标准

必须满足：

```text
[✓] Python 3.12+
[✓] 项目可安装
[✓] Settings 可加载
[✓] SQLite 可连接
[✓] SQLAlchemy Async 可工作
[✓] Alembic 可生成 migration
[✓] Alembic upgrade head 成功
[✓] Domain 无数据库依赖
[✓] Repository 可查询
[✓] UnitOfWork 可 commit
[✓] UnitOfWork 可 rollback
[✓] Runtime Operation Registry 可工作
[✓] Operation/Capability 边界明确
[✓] 无 MIDAS 依赖
```

---

# 47. 实际执行顺序

不要一次生成全部代码。

执行：

```text
Step 1
创建项目目录

Step 2
写 pyproject.toml

Step 3
pip install -e ".[dev]"

Step 4
实现 config

Step 5
实现 domain

Step 6
实现 database base/session

Step 7
实现 ORM

Step 8
alembic revision --autogenerate

Step 9
alembic upgrade head

Step 10
实现 repository

Step 11
实现 UnitOfWork

Step 12
实现 Registry

Step 13
实现测试

Step 14
pytest -q

Step 15
ruff check .

Step 16
git commit
```

---

# 48. 推荐 Git 提交点

```text
feat(core): bootstrap project
feat(core): add configuration
feat(core): add domain contracts
feat(db): add async sqlite infrastructure
feat(db): add initial schema
feat(repository): add core repositories
feat(core): add unit of work
feat(registry): add operation registry
test(core): add alpha foundation tests
```

每完成一个阶段就提交。

不要把：

```text
Core
+
MIDAS
+
MCP
+
Task Engine
```

一次性提交。

---

# 49. 下一批

第十份文档进入：

```text
Core Alpha Security
```

范围：

```text
P08 Seed
P09 Authentication
P10 Password Service
P11 Session
P12 Token
P13 RBAC
P14 Effective Permission
P15 Tenant Isolation
P16 Resource ACL
P17 Confirmation
```

重点实现：

```text
AuthenticationService
PasswordService
SessionService
TokenService
RoleService
PermissionService
EffectivePermissionService
TenantAccessService
ResourceACLService
ConfirmationService
```

并建立：

```text
User
 ↓
Authentication
 ↓
IdentityContext
 ↓
Tenant
 ↓
Project
 ↓
Resource
 ↓
Effective Permission
```

之后才能正式进入：

```text
Execution Pipeline
```

即：

```text
Authenticate
 ↓
Identity
 ↓
Resolve
 ↓
Schema
 ↓
Engineering Validation
 ↓
Permission
 ↓
Confirmation
 ↓
Idempotency
 ↓
Lock
 ↓
Capability
 ↓
Task
 ↓
Adapter
```

---

# 50. 本文档的工程结论

这一批不是“示例代码”。

它定义的是 StructAI MCP Server V2.0 Core Alpha 的**第一组可执行源代码边界**：

```text
Config
    ↓
Domain
    ↓
Database
    ↓
Repository
    ↓
UnitOfWork
    ↓
Registry
```

以后所有：

```text
Security
Execution
Task
Adapter
MCP
AI
UI
```

都必须建立在这个边界之上。

尤其必须保持：

```text
Core ≠ MIDAS
Operation ≠ Native API
Capability ≠ Operation
Repository ≠ Business Service
MCP Tool ≠ Adapter
Identity ≠ Client Input
```

这是后续 StructAI 能否真正做到“多工程软件统一 MCP”的基础。



# 完整收录：sec

# StructAI MCP Server V2.0
# 第十份文档：Core Alpha Security 实际源码级实现
## P08 Seed / Authentication / Session / Token / RBAC / Effective Permission / Tenant Isolation / Resource ACL / Confirmation

> 本文档承接第九份《Core Alpha 实际源码第一批（P01-P07）》。
>
> 本批次正式把 StructAI 的安全边界从“数据库表结构”推进到“可执行安全链”。
>
> 本批次仍然不实现 MIDAS、不实现 MCP Tool、不实现 Task Engine。
>
> 完成后，Core 将具备：
>
> ```text
> Authentication
> ↓
> IdentityContext
> ↓
> Tenant Isolation
> ↓
> Project Membership
> ↓
> Resource ACL
> ↓
> Effective Permission
> ↓
> Confirmation
> ```
>
> 为下一批 Execution Pipeline 提供可靠安全基础。

---

# 1. 本批次范围

```text
P08 Seed
P09 Authentication
P10 Password Service
P11 Session
P12 Token
P13 RBAC
P14 Effective Permission
P15 Tenant Isolation
P16 Resource ACL
P17 Confirmation
```

实现：

```text
AuthenticationService
PasswordService
SessionService
TokenService
RoleService
PermissionService
EffectivePermissionService
TenantAccessService
ResourceACLService
ConfirmationService
```

---

# 2. 本批次安全目标

必须建立以下不可绕过的链：

```text
Client
  ↓
Authentication
  ↓
Authenticated Identity
  ↓
Tenant
  ↓
Project
  ↓
Resource
  ↓
Role
  ↓
Permission
  ↓
Explicit Deny
  ↓
Effective Permission
  ↓
Confirmation
```

核心原则：

```text
客户端不能声明自己的权限
客户端不能声明自己的 user_id
客户端不能声明自己的 tenant_id
客户端不能声明自己的 roles
客户端不能声明 effective_permissions
AI Agent 不能提升用户权限
```

---

# 3. 安全边界

## 3.1 Client 可提供

```json
{
  "software_instance_id": "uuid",
  "project_id": "uuid",
  "model_id": "uuid",
  "document_id": "uuid"
}
```

## 3.2 Client 不可信字段

以下字段即使客户端发送，也必须忽略：

```json
{
  "user_id": "attacker-controlled",
  "tenant_id": "attacker-controlled",
  "roles": ["SYSTEM_ADMIN"],
  "permissions": ["SYSTEM_ADMIN"],
  "effective_permissions": ["*"]
}
```

最终身份必须来自：

```text
AuthenticationService
        ↓
Session / Token
        ↓
Server-side identity
        ↓
IdentityContext
```

---

# 4. 安全对象模型

```text
Tenant
 ├── User
 │    └── UserRole
 │          └── Role
 │                └── RolePermission
 │                      └── Permission
 │
 └── Project
      └── ProjectMember
            └── Project Role
```

资源：

```text
Tenant
Project
Model
Document
SoftwareInstance
```

资源 ACL：

```text
Principal
 ↓
Resource
 ↓
Allow / Deny
 ↓
Permission
```

---

# 5. Permission 固定集合

第一阶段：

```text
MODEL_READ
MODEL_WRITE
MODEL_DELETE

ANALYSIS_EXECUTE

DESIGN_EXECUTE
DESIGN_MODIFY

RESULT_READ

DOCUMENT_READ
DOCUMENT_WRITE

SYSTEM_ADMIN

TOOL_TEST
API_TEST
```

代码：

```python
from enum import StrEnum


class PermissionCode(StrEnum):
    MODEL_READ = "MODEL_READ"
    MODEL_WRITE = "MODEL_WRITE"
    MODEL_DELETE = "MODEL_DELETE"

    ANALYSIS_EXECUTE = "ANALYSIS_EXECUTE"

    DESIGN_EXECUTE = "DESIGN_EXECUTE"
    DESIGN_MODIFY = "DESIGN_MODIFY"

    RESULT_READ = "RESULT_READ"

    DOCUMENT_READ = "DOCUMENT_READ"
    DOCUMENT_WRITE = "DOCUMENT_WRITE"

    SYSTEM_ADMIN = "SYSTEM_ADMIN"

    TOOL_TEST = "TOOL_TEST"
    API_TEST = "API_TEST"
```

---

# 6. Role 固定集合

Core Alpha：

```text
SYSTEM_ADMIN
ENGINEER
VIEWER
AI_AGENT
```

建议权限：

## SYSTEM_ADMIN

```text
全部权限
```

## ENGINEER

```text
MODEL_READ
MODEL_WRITE
MODEL_DELETE
ANALYSIS_EXECUTE
DESIGN_EXECUTE
DESIGN_MODIFY
RESULT_READ
DOCUMENT_READ
DOCUMENT_WRITE
```

## VIEWER

```text
MODEL_READ
RESULT_READ
DOCUMENT_READ
```

## AI_AGENT

```text
MODEL_READ
MODEL_WRITE
ANALYSIS_EXECUTE
DESIGN_EXECUTE
RESULT_READ
DOCUMENT_READ
```

注意：

```text
AI_AGENT
```

不是系统管理员。

---

# 7. Password Service

文件：

```text
app/application/security/password.py
```

第一实现必须使用：

```text
Argon2id
```

依赖：

```toml
argon2-cffi>=23.1,<26
```

实现：

```python
from argon2 import PasswordHasher


class PasswordService:
    def __init__(self):
        self._hasher = PasswordHasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(
        self,
        password_hash: str,
        password: str,
    ) -> bool:
        try:
            return self._hasher.verify(
                password_hash,
                password,
            )
        except Exception:
            return False

    def needs_rehash(
        self,
        password_hash: str,
    ) -> bool:
        try:
            return self._hasher.check_needs_rehash(
                password_hash
            )
        except Exception:
            return False
```

---

# 8. Password 安全要求

禁止：

```text
MD5
SHA1
SHA256(password)
明文密码
可逆加密密码
```

密码数据库字段只能保存：

```text
password_hash
```

永远不能保存：

```text
password
```

日志禁止：

```text
password
password_hash
```

---

# 9. Password Policy

第一阶段：

```python
class PasswordPolicy:
    min_length = 12
    max_length = 128

    def validate(self, password: str) -> None:
        if not (
            self.min_length
            <= len(password)
            <= self.max_length
        ):
            raise ValueError(
                "Password length must be between "
                f"{self.min_length} and {self.max_length}"
            )
```

后续可增加：

```text
breached-password check
history
expiration
complexity
```

Core Alpha 不强制复杂密码字符组合，以避免错误安全规则导致可用性问题。

---

# 10. Session ORM

新增：

```text
app/infrastructure/database/models/session.py
```

```python
from datetime import datetime
from sqlalchemy import DateTime, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class SessionORM(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )

    tenant_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )

    token_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    revoked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
```

---

# 11. Session 生命周期

```text
CREATED
  ↓
ACTIVE
  ↓
EXPIRED
```

或：

```text
ACTIVE
  ↓
REVOKED
```

Session 必须支持：

```text
create
validate
touch
revoke
revoke_all
cleanup_expired
```

---

# 12. Token Service

原则：

```text
客户端持有 token
数据库只保存 token hash
```

不要把明文 token 写数据库。

实现：

```python
import hashlib
import secrets


class TokenService:
    def generate(self) -> str:
        return secrets.token_urlsafe(48)

    def hash(self, token: str) -> str:
        return hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest()
```

---

# 13. 为什么 Session 保存 Hash

数据库泄露时：

```text
DB
 ↓
token_hash
```

攻击者不能直接拿数据库值作为 session token。

原则：

```text
Raw Token
    ↓
Hash
    ↓
DB
```

登录成功：

```text
Raw Token → Client
Hash(Token) → DB
```

验证：

```text
Client Token
 ↓
Hash
 ↓
DB lookup
```

---

# 14. IdentityContext

使用此前确定的结构：

```python
from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class IdentityContext:
    user_id: UUID
    tenant_id: UUID
    session_id: UUID | None
    roles: tuple[str, ...] = ()
    authentication_method: str = "unknown"
```

注意：

```text
IdentityContext.roles
```

只是认证后由服务器装载的身份上下文。

不是客户端输入。

---

# 15. Authentication Result

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    identity: IdentityContext
    session_id: str
    access_token: str
```

---

# 16. AuthenticationService

```python
class AuthenticationService:
    def __init__(
        self,
        user_repository,
        password_service,
        session_service,
    ):
        self.user_repository = user_repository
        self.password_service = password_service
        self.session_service = session_service

    async def authenticate(
        self,
        username: str,
        password: str,
    ) -> AuthenticationResult:
        user = await self.user_repository.get_by_username(
            username
        )

        if user is None:
            raise AuthenticationError(
                "Invalid username or password"
            )

        if not user.is_active:
            raise AuthenticationError(
                "Invalid username or password"
            )

        valid = self.password_service.verify(
            user.password_hash,
            password,
        )

        if not valid:
            raise AuthenticationError(
                "Invalid username or password"
            )

        return await self.session_service.create_session(
            user_id=user.id,
            tenant_id=user.tenant_id,
        )
```

---

# 17. 不泄露用户是否存在

禁止：

```text
User does not exist
```

与：

```text
Wrong password
```

返回不同错误。

统一：

```text
Invalid username or password
```

避免 username enumeration。

---

# 18. Failed Login

后续可增加字段：

```text
failed_login_count
last_failed_login_at
locked_until
```

第一阶段至少定义：

```python
class LoginAttemptService:
    async def record_failure(self, username: str):
        ...

    async def record_success(self, username: str):
        ...

    async def is_locked(self, username: str) -> bool:
        ...
```

策略：

```text
连续失败
 ↓
短暂锁定
 ↓
指数退避
```

不要永久锁死账号。

---

# 19. Session Service

```python
from datetime import datetime, timedelta, timezone


class SessionService:
    def __init__(
        self,
        session_repository,
        token_service,
        role_service,
        lifetime_seconds: int = 86400,
    ):
        self.session_repository = session_repository
        self.token_service = token_service
        self.role_service = role_service
        self.lifetime_seconds = lifetime_seconds

    async def create_session(
        self,
        user_id: str,
        tenant_id: str,
    ):
        raw_token = self.token_service.generate()

        token_hash = self.token_service.hash(
            raw_token
        )

        now = datetime.now(timezone.utc)

        session = await self.session_repository.create(
            user_id=user_id,
            tenant_id=tenant_id,
            token_hash=token_hash,
            created_at=now,
            expires_at=now + timedelta(
                seconds=self.lifetime_seconds
            ),
        )

        roles = await self.role_service.get_user_roles(
            user_id
        )

        identity = IdentityContext(
            user_id=user_id,
            tenant_id=tenant_id,
            session_id=session.id,
            roles=tuple(roles),
            authentication_method="password",
        )

        return AuthenticationResult(
            identity=identity,
            session_id=session.id,
            access_token=raw_token,
        )
```

---

# 20. Session Validation

```python
async def validate_token(
    self,
    token: str,
) -> IdentityContext:
    token_hash = self.token_service.hash(token)

    session = await self.session_repository.get_by_token_hash(
        token_hash
    )

    if session is None:
        raise AuthenticationError("Invalid session")

    if session.revoked:
        raise AuthenticationError("Invalid session")

    now = datetime.now(timezone.utc)

    if session.expires_at <= now:
        raise AuthenticationError("Invalid session")

    roles = await self.role_service.get_user_roles(
        session.user_id
    )

    return IdentityContext(
        user_id=session.user_id,
        tenant_id=session.tenant_id,
        session_id=session.id,
        roles=tuple(roles),
        authentication_method="session",
    )
```

---

# 21. Session Revoke

```python
async def revoke(self, session_id: str) -> None:
    await self.session_repository.revoke(
        session_id
    )
```

全部退出：

```python
async def revoke_all(
    self,
    user_id: str,
) -> None:
    await self.session_repository.revoke_all_for_user(
        user_id
    )
```

用于：

```text
password change
security incident
logout all
administrator disable
```

---

# 22. Tenant Access Service

Tenant 是第一层隔离。

```python
class TenantAccessService:
    def ensure_access(
        self,
        identity: IdentityContext,
        tenant_id: str,
    ) -> None:
        if str(identity.tenant_id) != str(tenant_id):
            raise TenantAccessDeniedError(
                "Tenant access denied"
            )
```

禁止：

```python
# 错误
tenant_id = request.context["tenant_id"]
```

正确：

```python
tenant_id = identity.tenant_id
```

客户端 context 中的 tenant_id 不参与授权判断。

---

# 23. Project Access

项目必须属于当前 Tenant：

```text
Identity.tenant_id
      ↓
Project.tenant_id
```

验证：

```python
class ProjectAccessService:
    async def ensure_access(
        self,
        identity: IdentityContext,
        project,
    ) -> None:
        if str(project.tenant_id) != str(
            identity.tenant_id
        ):
            raise TenantAccessDeniedError(
                "Project belongs to another tenant"
            )
```

---

# 24. Resource ACL

资源 ACL 必须支持：

```text
ALLOW
DENY
```

主体：

```text
USER
ROLE
TENANT
```

资源：

```text
PROJECT
MODEL
DOCUMENT
SOFTWARE_INSTANCE
```

---

# 25. Resource ACL ORM

```python
class ResourceACLORM(Base):
    __tablename__ = "resource_acls"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )

    tenant_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )

    resource_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    resource_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    principal_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    principal_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    permission: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    effect: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
```

---

# 26. ACL Effect

```python
from enum import StrEnum


class ACLEffect(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
```

---

# 27. ACL Principal

```python
class ACLPrincipalType(StrEnum):
    USER = "USER"
    ROLE = "ROLE"
    TENANT = "TENANT"
```

---

# 28. ACL Decision

优先级：

```text
Explicit DENY
    >
Explicit ALLOW
    >
Inherited ALLOW
    >
Default DENY
```

因此：

```text
Deny wins.
```

---

# 29. Effective Permission

核心函数：

```python
class EffectivePermissionService:
    async def get_permissions(
        self,
        identity: IdentityContext,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> set[str]:
        ...
```

计算来源：

```text
Global Roles
+
Tenant Membership
+
Project Membership
+
Resource ACL
-
Explicit Deny
```

---

# 30. Effective Permission Algorithm

```text
1. 获取用户角色
2. 获取角色权限
3. 获取 Tenant 级权限
4. 获取 Project 级权限
5. 获取 Resource ACL
6. 加入 ALLOW
7. 删除 DENY
8. 返回最终集合
```

伪代码：

```python
permissions = set()

permissions |= role_permissions
permissions |= tenant_permissions
permissions |= project_permissions

for acl in resource_acls:
    if acl.effect == "ALLOW":
        permissions.add(acl.permission)

for acl in resource_acls:
    if acl.effect == "DENY":
        permissions.discard(acl.permission)

return permissions
```

---

# 31. Permission Check

```python
async def require(
    self,
    identity: IdentityContext,
    permission: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
) -> None:
    permissions = await self.get_permissions(
        identity,
        resource_type,
        resource_id,
    )

    if permission not in permissions:
        raise PermissionDeniedError(
            f"Permission denied: {permission}"
        )
```

---

# 32. AI Agent 权限

这是 StructAI 必须严格保持的安全原则：

```text
Effective User Permission
            ∩
AI Agent Permission
            =
Effective AI Permission
```

例如：

用户：

```text
MODEL_READ
MODEL_WRITE
ANALYSIS_EXECUTE
DESIGN_EXECUTE
```

AI Agent：

```text
MODEL_READ
MODEL_WRITE
ANALYSIS_EXECUTE
```

最终：

```text
MODEL_READ
MODEL_WRITE
ANALYSIS_EXECUTE
```

即使 Agent 自己请求：

```text
SYSTEM_ADMIN
```

也必须拒绝。

---

# 33. AI Agent Permission Service

```python
class AgentPermissionService:
    async def intersect(
        self,
        user_permissions: set[str],
        agent_permissions: set[str],
    ) -> set[str]:
        return user_permissions & agent_permissions
```

原则：

```text
Agent 只能减少权限
不能增加权限
```

---

# 34. Confirmation Service

高风险操作不能仅靠 RBAC。

例如：

```text
MODEL.NODE.DELETE
MODEL.ELEMENT.DELETE
BUILD.COLUMN
BUILD.FRAME
ANALYSIS.STATIC
DESIGN.STEEL
DESIGN.OPTIMIZE
```

可能要求：

```text
Confirmation Token
```

---

# 35. Confirmation Token

数据结构：

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Confirmation:
    token: str
    user_id: str
    tenant_id: str
    operation: str
    resource_id: str | None
    expires_at: datetime
```

---

# 36. ConfirmationService

```python
import secrets
from datetime import datetime, timedelta, timezone


class ConfirmationService:
    def __init__(self, ttl_seconds: int = 300):
        self.ttl_seconds = ttl_seconds
        self._tokens: dict[str, Confirmation] = {}

    def issue(
        self,
        user_id: str,
        tenant_id: str,
        operation: str,
        resource_id: str | None = None,
    ) -> Confirmation:
        token = secrets.token_urlsafe(32)

        confirmation = Confirmation(
            token=token,
            user_id=user_id,
            tenant_id=tenant_id,
            operation=operation,
            resource_id=resource_id,
            expires_at=(
                datetime.now(timezone.utc)
                + timedelta(
                    seconds=self.ttl_seconds
                )
            ),
        )

        self._tokens[token] = confirmation

        return confirmation
```

---

# 37. Confirmation Verify

```python
def verify(
    self,
    token: str,
    user_id: str,
    tenant_id: str,
    operation: str,
    resource_id: str | None = None,
) -> None:
    confirmation = self._tokens.get(token)

    if confirmation is None:
        raise ConfirmationRequiredError(
            "Confirmation required"
        )

    now = datetime.now(timezone.utc)

    if confirmation.expires_at <= now:
        self._tokens.pop(token, None)

        raise ConfirmationRequiredError(
            "Confirmation expired"
        )

    if confirmation.user_id != user_id:
        raise ConfirmationRequiredError(
            "Confirmation does not belong to user"
        )

    if confirmation.tenant_id != tenant_id:
        raise ConfirmationRequiredError(
            "Confirmation does not belong to tenant"
        )

    if confirmation.operation != operation:
        raise ConfirmationRequiredError(
            "Confirmation operation mismatch"
        )

    if confirmation.resource_id != resource_id:
        raise ConfirmationRequiredError(
            "Confirmation resource mismatch"
        )

    self._tokens.pop(token, None)
```

---

# 38. Confirmation 必须一次性使用

成功验证后：

```python
self._tokens.pop(token, None)
```

因此：

```text
Token
 ↓
Verify
 ↓
Consume
```

不能：

```text
Verify
 ↓
Token remains valid
```

否则同一个 confirmation 可以重复执行危险操作。

---

# 39. Confirmation 与 Dry Run

高风险操作推荐：

```text
Request
 ↓
dry_run=true
 ↓
返回计划
 ↓
用户确认
 ↓
issue confirmation
 ↓
真正执行
```

例如：

```json
{
  "operation": "BUILD.COLUMN",
  "parameters": {
    "height": 6
  },
  "dry_run": true
}
```

返回：

```json
{
  "success": true,
  "execution": {
    "mode": "DRY_RUN",
    "status": "PLANNED"
  },
  "data": {
    "changes": [
      "CREATE NODE",
      "CREATE ELEMENT",
      "ASSIGN SECTION",
      "ASSIGN MATERIAL"
    ]
  }
}
```

---

# 40. Security Middleware / Guard

后续 Execution Pipeline 统一使用：

```python
class SecurityGuard:
    async def authenticate(
        self,
        token: str,
    ) -> IdentityContext:
        ...

    async def authorize(
        self,
        identity: IdentityContext,
        operation: OperationDefinition,
        resource_type: str | None,
        resource_id: str | None,
    ) -> None:
        ...

    async def confirm(
        self,
        identity: IdentityContext,
        operation: OperationDefinition,
        confirmation_token: str | None,
        resource_id: str | None,
    ) -> None:
        ...
```

---

# 41. Security Guard 执行顺序

必须：

```text
Authenticate
 ↓
IdentityContext
 ↓
Tenant Isolation
 ↓
Resolve Resource
 ↓
Effective Permission
 ↓
Confirmation
```

不能：

```text
Client Permission
 ↓
Operation
```

也不能：

```text
Confirmation
 ↓
Authentication
```

因为 confirmation 本身必须绑定真实身份。

---

# 42. Security Context

后续统一：

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SecurityContext:
    identity: IdentityContext
    permissions: frozenset[str]
```

可进一步扩展：

```python
@dataclass(frozen=True, slots=True)
class SecurityContext:
    identity: IdentityContext
    permissions: frozenset[str]
    agent_id: str | None = None
    authenticated: bool = True
```

---

# 43. Seed

必须创建：

```text
1 Tenant
1 System Admin
1 Engineer
1 Viewer
1 AI Agent
```

权限：

```text
Permission rows
Role rows
RolePermission rows
User rows
UserRole rows
```

开发环境管理员：

```text
username = admin
```

密码必须通过环境变量提供：

```text
STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD
```

禁止把真实密码写入 seed.py。

---

# 44. Seed Admin

```python
import os

password = os.getenv(
    "STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD"
)

if not password:
    raise RuntimeError(
        "STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD is required"
    )
```

生成：

```python
password_hash = password_service.hash(
    password
)
```

数据库只写：

```text
password_hash
```

---

# 45. Seed 幂等

Seed 必须支持重复运行：

```bash
python -m app.infrastructure.database.seed
python -m app.infrastructure.database.seed
python -m app.infrastructure.database.seed
```

结果：

```text
不会创建重复 Tenant
不会创建重复 Role
不会创建重复 Permission
不会创建重复 User
不会重复 UserRole
```

原则：

```text
natural key / unique constraint
+
upsert / get-or-create
```

---

# 46. Seed 顺序

```text
Tenant
 ↓
Permission
 ↓
Role
 ↓
RolePermission
 ↓
User
 ↓
UserRole
 ↓
Project
 ↓
ProjectMember
```

不能反过来。

---

# 47. Authentication E2E

测试：

```text
1. Seed admin
2. POST/Login
3. 得到 token
4. Hash token
5. 查询 session
6. 构建 IdentityContext
7. 获取角色
8. 获取 Effective Permission
```

期望：

```text
authenticated = true
tenant_id = server-side tenant
user_id = server-side user
roles = SYSTEM_ADMIN
```

---

# 48. Tenant Isolation Test

建立：

```text
Tenant A
User A

Tenant B
User B
```

User A 请求 Tenant B：

```text
DENY
```

错误：

```text
STRUCTAI-4200
```

禁止返回：

```text
Tenant B exists
Project B exists
Model B exists
```

可以统一：

```text
Tenant access denied
```

---

# 49. Cross-Project Test

同一 Tenant：

```text
Project A
Project B
```

用户：

```text
Project A member
```

访问：

```text
Project B resource
```

必须由：

```text
ProjectMember
+
ACL
```

决定。

默认：

```text
DENY
```

---

# 50. Explicit Deny Test

用户拥有：

```text
ENGINEER
```

因此：

```text
MODEL_WRITE
```

但资源 ACL：

```text
USER:userA
MODEL_WRITE
DENY
```

最终：

```text
MODEL_WRITE
```

必须被移除。

结果：

```text
PermissionDenied
```

---

# 51. AI Agent Intersection Test

User：

```text
MODEL_READ
MODEL_WRITE
ANALYSIS_EXECUTE
DESIGN_EXECUTE
SYSTEM_ADMIN
```

Agent：

```text
MODEL_READ
MODEL_WRITE
ANALYSIS_EXECUTE
```

结果：

```text
MODEL_READ
MODEL_WRITE
ANALYSIS_EXECUTE
```

不得包含：

```text
DESIGN_EXECUTE
SYSTEM_ADMIN
```

---

# 52. Confirmation Test

流程：

```text
issue
 ↓
verify
 ↓
consume
 ↓
second verify
```

第二次必须：

```text
STRUCTAI-4100
```

测试：

```python
confirmation_service.verify(...)
confirmation_service.verify(...)
```

第二次失败。

---

# 53. Session Expiration Test

创建：

```text
expires_at = now - 1 second
```

验证：

```text
Invalid session
```

并且：

```text
IdentityContext
```

不得创建。

---

# 54. Token Storage Test

确认数据库：

```text
token_hash
```

存在。

确认：

```text
raw token
```

不存在。

---

# 55. Password Test

验证：

```text
password != password_hash
```

并：

```python
assert password_service.verify(
    password_hash,
    password,
)
```

必须 True。

错误密码：

```python
assert not password_service.verify(
    password_hash,
    "wrong",
)
```

必须 False。

---

# 56. Authentication Error Codes

增加：

```text
STRUCTAI-4001 Authentication Failed
STRUCTAI-4002 Session Invalid
STRUCTAI-4003 Session Expired
STRUCTAI-4004 Session Revoked
STRUCTAI-4200 Tenant Access Denied
```

---

# 57. Security Error Model

统一：

```python
class AuthenticationError(StructAIError):
    code = "STRUCTAI-4001"


class SessionInvalidError(StructAIError):
    code = "STRUCTAI-4002"


class SessionExpiredError(StructAIError):
    code = "STRUCTAI-4003"


class SessionRevokedError(StructAIError):
    code = "STRUCTAI-4004"


class TenantAccessDeniedError(StructAIError):
    code = "STRUCTAI-4200"
```

---

# 58. 安全日志

允许记录：

```text
login_success
login_failure
session_created
session_revoked
permission_denied
tenant_access_denied
confirmation_issued
confirmation_consumed
```

禁止记录：

```text
password
password_hash
raw_token
api_key
private_key
confirmation_token
```

对于 token，只允许记录：

```text
token fingerprint
```

例如：

```python
def fingerprint(value: str) -> str:
    import hashlib

    return hashlib.sha256(
        value.encode()
    ).hexdigest()[:12]
```

---

# 59. Security Audit

以下必须进入 Audit：

```text
LOGIN_SUCCESS
LOGIN_FAILURE
LOGOUT
SESSION_REVOKED
PERMISSION_DENIED
TENANT_ACCESS_DENIED
ACL_CHANGED
ROLE_CHANGED
PERMISSION_CHANGED
CONFIRMATION_ISSUED
CONFIRMATION_CONSUMED
```

---

# 60. Security 与 Execution Pipeline

下一阶段执行：

```text
MCP Request
 ↓
Authenticate
 ↓
IdentityContext
 ↓
Resolve Tool
 ↓
Resolve Operation
 ↓
Resolve Resource
 ↓
Schema Validation
 ↓
Engineering Validation
 ↓
Effective Permission
 ↓
Confirmation
 ↓
Idempotency
 ↓
Lock
 ↓
Capability
 ↓
Task
 ↓
Adapter
```

本批次完成：

```text
Authenticate
IdentityContext
Tenant
RBAC
Effective Permission
Confirmation
```

---

# 61. Security API 不允许被绕过

禁止：

```python
adapter.execute(...)
```

直接从 MCP Handler 调用。

正确：

```text
MCP
 ↓
ExecutionService
 ↓
SecurityGuard
 ↓
Execution Pipeline
 ↓
Adapter
```

即使未来：

```text
AI Agent
CLI
HTTP
MCP
UI
```

都必须走同一个安全入口。

---

# 62. 安全入口

最终定义：

```python
class ExecutionService:
    async def execute(
        self,
        request,
        context,
    ):
        ...
```

安全检查全部集中在这里。

这样：

```text
MCP
HTTP
CLI
AI
UI
```

不会分别实现一套权限逻辑。

---

# 63. Security Definition of Done

```text
[ ] Argon2id
[ ] Password Policy
[ ] Session ORM
[ ] Token Hash
[ ] AuthenticationService
[ ] SessionService
[ ] IdentityContext
[ ] Login Failure Tracking
[ ] Role Seed
[ ] Permission Seed
[ ] RBAC
[ ] Tenant Isolation
[ ] Project Access
[ ] Resource ACL
[ ] Explicit Deny
[ ] Effective Permission
[ ] AI Agent Permission Intersection
[ ] Confirmation Token
[ ] One-Time Confirmation
[ ] Confirmation Expiration
[ ] Security Audit
[ ] Secret Redaction
[ ] Authentication Tests
[ ] Tenant Isolation Tests
[ ] RBAC Tests
[ ] ACL Tests
[ ] Agent Permission Tests
[ ] Confirmation Tests
[ ] Session Expiration Tests
```

---

# 64. 下一份文档

第十一份进入：

```text
Core Alpha Execution Pipeline
```

核心实现：

```text
P18 ExecutionContext
P19 ResourceResolver
P20 SchemaEngine
P21 EngineeringValidator
P22 EffectivePermissionGuard
P23 ConfirmationGuard
P24 IdempotencyService
P25 ResourceLockManager
P26 CapabilityResolver
P27 OperationResolver
P28 ExecutionService
```

最终真正形成：

```text
MCP Request
 ↓
Authentication
 ↓
Identity
 ↓
ExecutionContext
 ↓
Tool Resolve
 ↓
Operation Resolve
 ↓
Resource Resolve
 ↓
Schema Validation
 ↓
Engineering Validation
 ↓
Permission
 ↓
Confirmation
 ↓
Idempotency
 ↓
Concurrency / Lock
 ↓
Capability
 ↓
Task / Transaction
 ↓
Adapter
```

这一批完成后，StructAI Core 才开始具备真正的“统一工程执行内核”。



# 完整收录：exec

# StructAI MCP Server V2.0
# 第十一份文档：Core Alpha Execution Pipeline 实际源码级实现
## P18-P28：ExecutionContext / ResourceResolver / SchemaEngine / EngineeringValidator / Permission / Confirmation / Idempotency / Lock / Capability / Operation / ExecutionService

> 本文档承接：
>
> - 第九份：Core Alpha Source Batch 01
> - 第十份：Core Alpha Security
>
> 本批次是 Core Alpha 的关键转折点。
>
> 前两批完成：
>
> ```text
> Database
> Domain
> Repository
> UnitOfWork
> Registry
> Authentication
> Session
> RBAC
> Tenant Isolation
> ACL
> Confirmation
> ```
>
> 本批次把这些组件正式串成一个统一执行内核：
>
> ```text
> Request
>  ↓
> Authentication
>  ↓
> IdentityContext
>  ↓
> ExecutionContext
>  ↓
> Tool Resolve
>  ↓
> Operation Resolve
>  ↓
> Resource Resolve
>  ↓
> Schema Validation
>  ↓
> Engineering Validation
>  ↓
> Permission
>  ↓
> Confirmation
>  ↓
> Idempotency
>  ↓
> Resource Lock
>  ↓
> Capability
>  ↓
> Task / Transaction
>  ↓
> Adapter
> ```
>
> 本批次仍然保持：
>
> ```text
> Core ≠ MIDAS
> Core ≠ CSI
> Core ≠ ANSYS
> Core ≠ MCP Transport
> ```
>
> Adapter 只是执行最后一跳。

---

# 1. 本批次目标

实现：

```text
P18 ExecutionContext
P19 ResourceResolver
P20 SchemaEngine
P21 EngineeringValidator
P22 EffectivePermissionGuard
P23 ConfirmationGuard
P24 IdempotencyService
P25 ResourceLockManager
P26 CapabilityResolver
P27 OperationResolver
P28 ExecutionService
```

完成后：

```text
Core Alpha
```

第一次具备真正的：

```text
统一请求执行能力
```

---

# 2. 核心原则

Execution Pipeline 必须是唯一安全执行入口。

所有调用方式：

```text
MCP
HTTP
CLI
AI Agent
UI
```

最终必须：

```text
        ↓
ExecutionService
```

禁止：

```text
MCP → Adapter
HTTP → Adapter
AI → Adapter
UI → Adapter
```

---

# 3. ExecutionContext

此前已经确定：

```python
from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class IdentityContext:
    user_id: UUID
    tenant_id: UUID
    session_id: UUID | None
    roles: tuple[str, ...] = ()
    authentication_method: str = "unknown"


@dataclass(frozen=True)
class SoftwareContext:
    instance_id: UUID | None = None
    product: str | None = None
    version: str | None = None


@dataclass(frozen=True)
class ProjectContext:
    project_id: UUID | None = None


@dataclass(frozen=True)
class ResourceContext:
    model_id: UUID | None = None
    document_id: UUID | None = None


@dataclass(frozen=True)
class ExecutionContext:
    request_id: str
    trace_id: str

    identity: IdentityContext

    software: SoftwareContext = field(
        default_factory=SoftwareContext
    )

    project: ProjectContext = field(
        default_factory=ProjectContext
    )

    resource: ResourceContext = field(
        default_factory=ResourceContext
    )
```

---

# 4. ExecutionContext 构造规则

客户端可以提供：

```json
{
  "software_instance_id": "uuid",
  "project_id": "uuid",
  "model_id": "uuid",
  "document_id": "uuid"
}
```

服务器负责：

```text
Authentication
 ↓
IdentityContext
```

因此：

```text
user_id
tenant_id
roles
permissions
```

绝不能从 Client Context 读取。

---

# 5. Context Factory

```python
from uuid import UUID, uuid4


class ExecutionContextFactory:

    def create(
        self,
        identity: IdentityContext,
        *,
        software_instance_id: str | None = None,
        project_id: str | None = None,
        model_id: str | None = None,
        document_id: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> ExecutionContext:

        return ExecutionContext(
            request_id=request_id or f"req_{uuid4().hex}",
            trace_id=trace_id or f"trace_{uuid4().hex}",
            identity=identity,
            software=SoftwareContext(
                instance_id=(
                    UUID(software_instance_id)
                    if software_instance_id
                    else None
                )
            ),
            project=ProjectContext(
                project_id=(
                    UUID(project_id)
                    if project_id
                    else None
                )
            ),
            resource=ResourceContext(
                model_id=(
                    UUID(model_id)
                    if model_id
                    else None
                ),
                document_id=(
                    UUID(document_id)
                    if document_id
                    else None
                ),
            ),
        )
```

---

# 6. Tool Request

统一请求：

```python
from pydantic import BaseModel, Field


class ToolRequest(BaseModel):
    operation: str

    parameters: dict = Field(
        default_factory=dict
    )

    context: dict = Field(
        default_factory=dict
    )

    idempotency_key: str | None = None

    confirmation_token: str | None = None

    dry_run: bool = False
```

注意：

```text
ToolRequest
```

不是：

```text
IdentityRequest
```

身份由 Authentication 层建立。

---

# 7. Execution Request

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    tool: str
    operation: str
    parameters: dict
    context: dict
    idempotency_key: str | None = None
    confirmation_token: str | None = None
    dry_run: bool = False
```

---

# 8. ResourceResolver

职责：

```text
Client Resource ID
       ↓
Database
       ↓
Resource
       ↓
Tenant Validation
       ↓
Project Validation
       ↓
Resource Context
```

Resolver 不负责：

```text
permission
adapter
task
MCP
```

---

# 9. ResourceResolver 接口

```python
class ResourceResolver:

    async def resolve_project(
        self,
        context: ExecutionContext,
    ):
        ...

    async def resolve_model(
        self,
        context: ExecutionContext,
    ):
        ...

    async def resolve_document(
        self,
        context: ExecutionContext,
    ):
        ...

    async def resolve_software_instance(
        self,
        context: ExecutionContext,
    ):
        ...
```

---

# 10. Tenant Boundary

例如：

```python
async def resolve_project(
    self,
    context: ExecutionContext,
):
    project = await self.project_repository.get(
        str(context.project.project_id)
    )

    if project is None:
        raise NotFoundError(
            "Project not found"
        )

    if project.tenant_id != str(
        context.identity.tenant_id
    ):
        raise TenantAccessDeniedError(
            "Tenant access denied"
        )

    return project
```

---

# 11. Model Boundary

Model：

```text
Model
 ↓
Project
 ↓
Tenant
```

所以不能只检查：

```text
model.id
```

必须：

```text
model
 ↓
project
 ↓
tenant
 ↓
identity
```

---

# 12. Software Instance Resolver

软件实例也属于 Tenant：

```text
SoftwareInstance
 ↓
Tenant
```

后续数据库应增加：

```text
software_instances.tenant_id
```

如果当前 Schema 还没有该字段，本批次必须通过所属 Project / Registry 关系补齐，不能允许跨租户实例被直接执行。

---

# 13. SchemaEngine

职责：

```text
operation
 ↓
input_schema
 ↓
JSON Schema
 ↓
validate parameters
```

标准：

```text
JSON Schema Draft 2020-12
```

---

# 14. Schema URI

统一：

```text
structai://schema/model/node/v1
structai://schema/model/node/query/v1
structai://schema/model/element/v1
structai://schema/analysis/static/v1
structai://schema/result/displacement/v1
structai://schema/design/steel/v1
```

---

# 15. SchemaRegistry

```python
class SchemaRegistry:

    def __init__(self):
        self._schemas: dict[str, dict] = {}

    def register(
        self,
        schema_id: str,
        schema: dict,
    ) -> None:
        self._schemas[schema_id] = schema

    def get(
        self,
        schema_id: str,
    ) -> dict:
        schema = self._schemas.get(schema_id)

        if schema is None:
            raise NotFoundError(
                f"Schema not found: {schema_id}"
            )

        return schema
```

---

# 16. SchemaEngine 实现

依赖：

```toml
jsonschema>=4.23,<5.0
```

实现：

```python
from jsonschema import Draft202012Validator


class SchemaEngine:

    def __init__(
        self,
        registry: SchemaRegistry,
    ):
        self.registry = registry

    def validate(
        self,
        schema_id: str,
        data: dict,
    ) -> None:
        schema = self.registry.get(
            schema_id
        )

        validator = Draft202012Validator(
            schema
        )

        errors = sorted(
            validator.iter_errors(data),
            key=lambda error: list(error.path),
        )

        if errors:
            raise ValidationError(
                "Schema validation failed",
                details={
                    "errors": [
                        {
                            "path": list(error.path),
                            "message": error.message,
                        }
                        for error in errors
                    ]
                },
            )
```

---

# 17. Schema Validation 原则

Schema 只解决：

```text
类型
字段
格式
结构
枚举
必填
范围
```

例如：

```text
x = number
y = number
z = number
```

但 Schema 不判断：

```text
结构是否合理
材料是否适合
荷载是否满足规范
节点是否重复
构件是否冲突
```

这些交给 EngineeringValidator。

---

# 18. EngineeringValidator

职责：

```text
Schema Validation
       ↓
Engineering Validation
```

例如：

```text
节点 ID 不重复
元素节点必须存在
材料必须存在
截面必须存在
荷载不能引用不存在节点
```

---

# 19. Validator 接口

```python
class EngineeringValidator:

    async def validate(
        self,
        operation: str,
        parameters: dict,
        context: ExecutionContext,
    ) -> None:
        ...
```

---

# 20. Validator Rules

第一阶段至少：

```text
MODEL.NODE.CREATE
MODEL.NODE.UPDATE
MODEL.ELEMENT.CREATE
MODEL.ELEMENT.UPDATE
MODEL.BOUNDARY.ASSIGN
MODEL.LOAD.ASSIGN
BUILD.COLUMN
BUILD.BEAM
ANALYSIS.STATIC
DESIGN.STEEL
```

---

# 21. Node Validation

```python
async def validate_node_create(
    self,
    parameters: dict,
):
    node_id = parameters["id"]

    existing = await self.node_repository.get(
        node_id
    )

    if existing is not None:
        raise EngineeringValidationError(
            "Node already exists"
        )
```

---

# 22. Element Validation

```python
async def validate_element_create(
    self,
    parameters: dict,
):
    node_ids = parameters["node_ids"]

    if len(node_ids) < 2:
        raise EngineeringValidationError(
            "Element requires at least two nodes"
        )

    for node_id in node_ids:
        node = await self.node_repository.get(
            node_id
        )

        if node is None:
            raise EngineeringValidationError(
                f"Node does not exist: {node_id}"
            )
```

---

# 23. Analysis Preconditions

静力分析前：

```text
Model exists
 ↓
Node count > 0
 ↓
Element count > 0
 ↓
Material assigned
 ↓
Section assigned
 ↓
Boundary exists
 ↓
Load exists
 ↓
Software supports ANALYSIS.STATIC
```

因此：

```text
ANALYSIS.STATIC
```

不能直接调用 Adapter。

---

# 24. OperationDefinition

继续使用：

```python
@dataclass(frozen=True, slots=True)
class OperationDefinition:
    name: str
    tool: str
    risk_level: RiskLevel
    execution_mode: ExecutionMode
    input_schema: str
    output_schema: str
    required_permissions: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    transactional: bool
    rollback_supported: bool
    dry_run_supported: bool
    recovery_policy: str
```

---

# 25. OperationResolver

```python
class OperationResolver:

    def __init__(
        self,
        registry: OperationRegistry,
    ):
        self.registry = registry

    async def resolve(
        self,
        tool: str,
        operation: str,
    ) -> OperationDefinition:

        definition = await self.registry.get(
            operation
        )

        if definition is None:
            raise NotFoundError(
                f"Operation not found: {operation}"
            )

        if definition.tool != tool:
            raise ValidationError(
                "Operation does not belong to tool"
            )

        return definition
```

---

# 26. Tool 与 Operation 双重验证

请求：

```json
{
  "tool": "engineering_model_query",
  "operation": "MODEL.NODE.CREATE"
}
```

必须失败。

因为：

```text
MODEL.NODE.CREATE
```

属于：

```text
engineering_model_assign
```

而不是：

```text
engineering_model_query
```

防止：

```text
Tool spoofing
```

---

# 27. EffectivePermissionGuard

```python
class EffectivePermissionGuard:

    def __init__(
        self,
        permission_service,
    ):
        self.permission_service = permission_service

    async def require(
        self,
        identity: IdentityContext,
        operation: OperationDefinition,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> None:

        for permission in (
            operation.required_permissions
        ):
            await self.permission_service.require(
                identity=identity,
                permission=permission,
                resource_type=resource_type,
                resource_id=resource_id,
            )
```

---

# 28. ConfirmationGuard

```python
class ConfirmationGuard:

    def __init__(
        self,
        confirmation_service,
    ):
        self.confirmation_service = (
            confirmation_service
        )

    def require(
        self,
        identity: IdentityContext,
        operation: OperationDefinition,
        token: str | None,
        resource_id: str | None = None,
    ) -> None:

        if operation.risk_level.value not in {
            "HIGH",
            "CRITICAL",
        }:
            return

        if not token:
            raise ConfirmationRequiredError(
                "Confirmation required"
            )

        self.confirmation_service.verify(
            token=token,
            user_id=str(identity.user_id),
            tenant_id=str(identity.tenant_id),
            operation=operation.name,
            resource_id=resource_id,
        )
```

---

# 29. Confirmation 策略

Core Alpha：

```text
LOW
    no confirmation

MEDIUM
    normally no confirmation

HIGH
    confirmation required

CRITICAL
    confirmation required
```

后续可以支持：

```text
per-operation
per-resource
per-tenant policy
per-user policy
```

---

# 30. Idempotency

目的：

防止：

```text
网络重试
客户端重复发送
MCP retry
AI retry
HTTP retry
```

导致：

```text
CREATE × 2
BUILD × 2
DELETE × 2
ANALYSIS × 2
```

---

# 31. Idempotency Key

客户端：

```json
{
  "idempotency_key": "column-build-001"
}
```

Key 必须与：

```text
tenant
```

绑定。

数据库唯一逻辑：

```text
(tenant_id, key)
```

---

# 32. Request Hash

不能只保存：

```text
idempotency_key
```

还必须保存：

```text
request_hash
```

因为：

```text
key = A
request = X
```

第一次成功后：

```text
key = A
request = Y
```

必须拒绝。

---

# 33. IdempotencyService

```python
import hashlib
import json


class IdempotencyService:

    def hash_request(
        self,
        request: ExecutionRequest,
    ) -> str:

        payload = {
            "tool": request.tool,
            "operation": request.operation,
            "parameters": request.parameters,
            "context": request.context,
            "dry_run": request.dry_run,
        }

        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )

        return hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()
```

---

# 34. Idempotency Check

```python
async def check(
    self,
    tenant_id: str,
    key: str,
    request_hash: str,
):
    record = await self.repository.get(
        tenant_id,
        key,
    )

    if record is None:
        return None

    if record.request_hash != request_hash:
        raise ValidationError(
            "Idempotency key reused with "
            "different request"
        )

    return record.response_json
```

---

# 35. Idempotency Atomicity

禁止：

```text
SELECT
 ↓
不存在
 ↓
INSERT
```

因为并发时：

```text
Request A → SELECT
Request B → SELECT
A → INSERT
B → INSERT
```

必须：

```text
UNIQUE(tenant_id, key)
```

然后捕获：

```text
IntegrityError
```

重新读取已有记录。

---

# 36. ResourceLockManager

资源：

```text
SoftwareInstance
Model
Document
```

锁：

```text
READ
WRITE
EXCLUSIVE
```

兼容矩阵：

```text
             READ     WRITE     EXCLUSIVE
READ          ✓        ✗          ✗
WRITE         ✗        ✗          ✗
EXCLUSIVE     ✗        ✗          ✗
```

---

# 37. Lock Resource Key

统一：

```python
@dataclass(frozen=True, slots=True)
class ResourceKey:
    resource_type: str
    resource_id: str
```

例如：

```text
MODEL:7f3...
SOFTWARE_INSTANCE:93c...
DOCUMENT:22a...
```

---

# 38. In-Memory Lock Manager

Core Alpha：

```python
import asyncio
from dataclasses import dataclass


@dataclass
class LockEntry:
    readers: int = 0
    writer: bool = False


class ResourceLockManager:

    def __init__(self):
        self._entries: dict[
            ResourceKey,
            LockEntry,
        ] = {}

        self._mutex = asyncio.Lock()
```

---

# 39. Lock Acquire

```python
async def acquire(
    self,
    resource: ResourceKey,
    mode: LockMode,
) -> None:

    async with self._mutex:

        entry = self._entries.setdefault(
            resource,
            LockEntry(),
        )

        if mode == LockMode.READ:
            if entry.writer:
                raise ResourceLockedError(
                    "Resource is write locked"
                )

            entry.readers += 1
            return

        if mode in {
            LockMode.WRITE,
            LockMode.EXCLUSIVE,
        }:
            if (
                entry.writer
                or entry.readers > 0
            ):
                raise ResourceLockedError(
                    "Resource is locked"
                )

            entry.writer = True
            return
```

---

# 40. Lock Release

```python
async def release(
    self,
    resource: ResourceKey,
    mode: LockMode,
) -> None:

    async with self._mutex:

        entry = self._entries.get(resource)

        if entry is None:
            return

        if mode == LockMode.READ:
            entry.readers -= 1

        else:
            entry.writer = False

        if (
            entry.readers <= 0
            and not entry.writer
        ):
            self._entries.pop(
                resource,
                None,
            )
```

---

# 41. Lock Scope

锁必须：

```text
Acquire
 ↓
Execute
 ↓
Release
```

使用：

```python
try:
    await lock_manager.acquire(
        resource,
        LockMode.WRITE,
    )

    result = await execute()

finally:
    await lock_manager.release(
        resource,
        LockMode.WRITE,
    )
```

禁止异常情况下不释放。

---

# 42. Optimistic Lock

Model 已有：

```text
version
```

更新：

```json
{
  "id": "model-001",
  "expected_version": 3
}
```

数据库：

```text
UPDATE models
SET version = version + 1
WHERE id = ?
AND version = 3
```

affected rows：

```text
1 → success
0 → STRUCTAI-1300
```

---

# 43. CapabilityResolver

Capability 不是：

```text
Operation
```

例如：

```text
Operation:
ANALYSIS.STATIC
```

需要：

```text
Capability:
ANALYSIS.STATIC
```

但：

```text
BUILD.COLUMN
```

可能需要：

```text
MODEL.NODE.WRITE
MODEL.ELEMENT.WRITE
MODEL.MATERIAL.WRITE
MODEL.SECTION.WRITE
```

因此 Capability Resolver 支持多个 capability。

---

# 44. CapabilityResolver 接口

```python
class CapabilityResolver:

    async def check(
        self,
        context: ExecutionContext,
        operation: OperationDefinition,
    ) -> None:
        ...
```

---

# 45. Runtime Capability

能力来源：

```text
Software
 ↓
Product
 ↓
Version
 ↓
Adapter
 ↓
Runtime Capability
```

例如：

```text
MIDAS CIVIL NX 2026
```

可能：

```text
ANALYSIS.STATIC = SUPPORTED
ANALYSIS.NONLINEAR = SUPPORTED
DESIGN.STEEL = SUPPORTED
```

而另一个软件：

```text
OpenSees
```

可能：

```text
ANALYSIS.STATIC = SUPPORTED
DESIGN.STEEL = UNSUPPORTED
```

---

# 46. Capability Resolver Algorithm

```text
Operation
 ↓
required_capabilities
 ↓
Software Instance
 ↓
Capability Cache
 ↓
Runtime Detection
 ↓
ALL required capabilities supported?
```

不是：

```text
ANY
```

而是：

```text
ALL
```

---

# 47. Unknown Capability

必须：

```text
UNKNOWN ≠ SUPPORTED
```

因此：

```python
if status != CapabilityStatus.SUPPORTED:
    raise CapabilityError(
        "Capability not supported"
    )
```

---

# 48. Capability Cache

字段：

```text
software_instance_id
product
version
capability
status
checked_at
expires_at
```

Cache：

```text
TTL
```

重新连接：

```text
invalidate
```

版本变化：

```text
invalidate
```

---

# 49. ExecutionService

最终：

```python
class ExecutionService:

    async def execute(
        self,
        request: ExecutionRequest,
        context: ExecutionContext,
    ):
        ...
```

---

# 50. ExecutionService 依赖

```python
class ExecutionService:

    def __init__(
        self,
        operation_resolver,
        resource_resolver,
        schema_engine,
        engineering_validator,
        permission_guard,
        confirmation_guard,
        idempotency_service,
        lock_manager,
        capability_resolver,
        task_engine,
        adapter_manager,
    ):
        ...
```

---

# 51. Pipeline Step 1：Operation Resolve

```python
operation = await (
    self.operation_resolver.resolve(
        request.tool,
        request.operation,
    )
)
```

如果：

```text
Tool ≠ Operation owner
```

立即失败。

---

# 52. Pipeline Step 2：Resource Resolve

根据 operation：

```text
需要 Model
需要 Document
需要 Project
需要 Software Instance
```

执行：

```python
resource = await (
    self.resource_resolver.resolve(
        operation,
        context,
    )
)
```

---

# 53. Pipeline Step 3：Schema Validation

```python
self.schema_engine.validate(
    operation.input_schema,
    request.parameters,
)
```

失败：

```text
STRUCTAI-1100
```

---

# 54. Pipeline Step 4：Engineering Validation

```python
await self.engineering_validator.validate(
    operation=operation.name,
    parameters=request.parameters,
    context=context,
)
```

失败：

```text
STRUCTAI-1200
```

---

# 55. Pipeline Step 5：Permission

```python
await self.permission_guard.require(
    identity=context.identity,
    operation=operation,
    resource_type=resource.type,
    resource_id=resource.id,
)
```

失败：

```text
STRUCTAI-4000
```

---

# 56. Pipeline Step 6：Confirmation

```python
self.confirmation_guard.require(
    identity=context.identity,
    operation=operation,
    token=request.confirmation_token,
    resource_id=resource.id,
)
```

失败：

```text
STRUCTAI-4100
```

---

# 57. Pipeline Step 7：Idempotency

如果：

```text
idempotency_key
```

存在：

```python
request_hash = (
    self.idempotency_service.hash_request(
        request
    )
)
```

查询历史结果。

如果存在：

```text
直接返回历史结果
```

如果不存在：

```text
继续执行
```

---

# 58. Pipeline Step 8：Lock

根据 operation：

```text
QUERY
 → READ

CREATE / UPDATE / ASSIGN
 → WRITE

DELETE / BUILD / DESIGN / ANALYSIS
 → WRITE / EXCLUSIVE
```

第一阶段建议：

```text
Analysis = EXCLUSIVE Model
Design = EXCLUSIVE Model
Build = WRITE Model
Delete = WRITE Model
Query = READ Model
```

---

# 59. Pipeline Step 9：Capability

```python
await self.capability_resolver.check(
    context=context,
    operation=operation,
)
```

失败：

```text
STRUCTAI-3000
```

---

# 60. Pipeline Step 10：Dry Run

如果：

```python
request.dry_run
```

且：

```python
operation.dry_run_supported
```

则：

```text
不调用 Adapter
```

返回：

```json
{
  "execution": {
    "mode": "DRY_RUN",
    "status": "PLANNED"
  }
}
```

---

# 61. Pipeline Step 11：Task

如果：

```text
operation.execution_mode = ASYNC
```

创建 Task：

```text
TaskEngine.create(...)
```

立即返回：

```json
{
  "success": true,
  "execution": {
    "mode": "ASYNC",
    "status": "QUEUED",
    "task_id": "task_001"
  }
}
```

如果：

```text
SYNC
```

则可以：

```text
直接执行 Task
```

但仍然建议统一经过 Task Engine。

---

# 62. Pipeline Step 12：Adapter

最终：

```python
adapter = await self.adapter_manager.resolve(
    context.software
)

result = await adapter.execute(
    operation=operation.name,
    parameters=request.parameters,
    context=context,
)
```

注意：

```text
ExecutionService
```

不理解：

```text
/anal/STATIC
```

不理解：

```text
MIDAS JSON
```

不理解：

```text
COM
```

这些属于 Adapter。

---

# 63. Pipeline Step 13：Result

Adapter 返回：

```text
Canonical Engineering Result
```

例如：

```json
{
  "node_id": 100,
  "ux": 0.001,
  "uy": 0.002,
  "uz": -0.015
}
```

Core 不需要知道：

```text
MIDAS response field
```

---

# 64. Pipeline Step 14：Idempotency Store

执行成功：

```text
response
 ↓
JSON
 ↓
IdempotencyRecord
```

以后重复请求：

```text
直接返回相同 response
```

---

# 65. Pipeline Step 15：Release Lock

无论：

```text
SUCCESS
FAIL
TIMEOUT
CANCEL
```

必须：

```python
finally:
    await lock_manager.release(...)
```

---

# 66. ExecutionService 伪代码

```python
async def execute(
    self,
    request,
    context,
):

    operation = await self.operation_resolver.resolve(
        request.tool,
        request.operation,
    )

    resource = await self.resource_resolver.resolve(
        operation,
        context,
    )

    self.schema_engine.validate(
        operation.input_schema,
        request.parameters,
    )

    await self.engineering_validator.validate(
        operation.name,
        request.parameters,
        context,
    )

    await self.permission_guard.require(
        context.identity,
        operation,
        resource.type,
        resource.id,
    )

    self.confirmation_guard.require(
        context.identity,
        operation,
        request.confirmation_token,
        resource.id,
    )

    cached = await self.check_idempotency(
        request,
        context,
    )

    if cached:
        return cached

    lock = self.lock_policy.resolve(
        operation,
        resource,
    )

    await self.lock_manager.acquire(
        lock.resource,
        lock.mode,
    )

    try:

        await self.capability_resolver.check(
            context,
            operation,
        )

        if request.dry_run:
            return self.plan(
                request,
                operation,
                resource,
            )

        task = await self.task_engine.execute(
            request=request,
            context=context,
            operation=operation,
        )

        return task

    finally:

        await self.lock_manager.release(
            lock.resource,
            lock.mode,
        )
```

---

# 67. Pipeline 顺序不可随意改变

正式顺序：

```text
1  Authenticate
2  Build IdentityContext
3  Build ExecutionContext
4  Resolve Tool
5  Resolve Operation
6  Resolve Resource
7  Schema Validation
8  Engineering Validation
9  Permission
10 Confirmation
11 Idempotency
12 Lock
13 Capability
14 Dry Run
15 Task
16 Adapter
17 Normalize Result
18 Persist Idempotency
19 Audit
20 Trace
21 Release Lock
22 Response
```

注意：

```text
Authentication
```

发生在：

```text
ExecutionService
```

之前的入口层。

---

# 68. 为什么 Permission 在 Capability 之前

因为：

```text
Capability
```

可能暴露：

```text
software
version
supported operations
```

但用户没有权限时：

```text
permission denied
```

应该尽早阻断。

同时避免无授权用户探测软件能力。

---

# 69. 为什么 Schema 在 Permission 前

Schema 验证可以在进入业务层之前拒绝恶意结构。

但是不要在未授权情况下返回过多内部信息。

因此：

```text
Schema error
```

应只返回必要错误。

---

# 70. 为什么 Engineering Validation 在 Permission 前

第一阶段：

```text
Schema
 ↓
Engineering
 ↓
Permission
```

这是确定的统一顺序。

但 Validator 不得泄露：

```text
其他租户资源存在性
```

因此 Validator 必须只操作：

```text
already-resolved-and-authorized resources
```

或者使用经过 Tenant Boundary 的 Repository。

---

# 71. Resource Resolver 与 Tenant Boundary

所有 Repository 查询都必须支持：

```text
tenant scoped
```

例如：

```python
await model_repository.get_for_tenant(
    model_id=model_id,
    tenant_id=identity.tenant_id,
)
```

禁止：

```python
await model_repository.get(model_id)
```

然后在业务层忘记检查 Tenant。

---

# 72. Scoped Repository

推荐：

```python
class ModelRepository:

    async def get_for_tenant(
        self,
        model_id: str,
        tenant_id: str,
    ):
        ...
```

SQL：

```text
WHERE
    id = ?
AND
    project.tenant_id = ?
```

---

# 73. Execution Resource

统一：

```python
@dataclass(frozen=True, slots=True)
class ResolvedResource:
    resource_type: str
    resource_id: str
    tenant_id: str
    project_id: str | None = None
```

---

# 74. Lock Policy

```python
class LockPolicy:

    def resolve(
        self,
        operation: OperationDefinition,
        resource: ResolvedResource,
    ):
        if operation.name.endswith(".QUERY"):
            return ResourceLock(
                resource=ResourceKey(
                    resource.resource_type,
                    resource.resource_id,
                ),
                mode=LockMode.READ,
            )

        if operation.risk_level.value in {
            "HIGH",
            "CRITICAL",
        }:
            return ResourceLock(
                resource=ResourceKey(
                    resource.resource_type,
                    resource.resource_id,
                ),
                mode=LockMode.EXCLUSIVE,
            )

        return ResourceLock(
            resource=ResourceKey(
                resource.resource_type,
                resource.resource_id,
            ),
            mode=LockMode.WRITE,
        )
```

后续可以精细化到 operation policy。

---

# 75. Lock 与 Software Instance

工程软件通常：

```text
one desktop instance
```

默认：

```text
SERIAL
```

因此：

```text
ANALYSIS.STATIC
```

不能与：

```text
MODEL.NODE.UPDATE
```

同时修改同一个软件实例。

锁层次：

```text
SoftwareInstance
 ↓
Model
 ↓
Document
```

后续支持：

```text
instance serial
model write
document write
```

---

# 76. Execution Result

统一返回：

```python
@dataclass(frozen=True, slots=True)
class ExecutionResult:
    success: bool
    request_id: str
    trace_id: str
    tool: str
    operation: str
    execution: dict
    data: dict | list | None = None
    warnings: list = None
    errors: list = None
    metadata: dict = None
```

实际实现建议使用 Pydantic DTO。

---

# 77. Sync Response

```json
{
  "success": true,
  "request_id": "req_001",
  "trace_id": "trace_001",
  "tool": "engineering_model_query",
  "operation": "MODEL.NODE.QUERY",
  "execution": {
    "mode": "SYNC",
    "status": "COMPLETED"
  },
  "data": {},
  "warnings": [],
  "errors": [],
  "metadata": {}
}
```

---

# 78. Async Response

```json
{
  "success": true,
  "request_id": "req_002",
  "trace_id": "trace_002",
  "tool": "engineering_analysis",
  "operation": "ANALYSIS.STATIC",
  "execution": {
    "mode": "ASYNC",
    "status": "QUEUED",
    "task_id": "task_001"
  },
  "data": null,
  "warnings": [],
  "errors": []
}
```

---

# 79. Error Mapping

```python
def error_response(
    exc: StructAIError,
    context: ExecutionContext,
):
    return {
        "success": False,
        "request_id": context.request_id,
        "trace_id": context.trace_id,
        "error": {
            "code": exc.code,
            "type": exc.__class__.__name__,
            "message": exc.message,
            "details": exc.details,
            "retryable": False,
        },
    }
```

不能直接：

```python
str(native_exception)
```

返回给 Client。

---

# 80. Retryable

Execution 层必须区分：

```text
validation = false
permission = false
confirmation = false
capability = false

network timeout = true
temporary adapter unavailable = true
rate limit = true
```

但真正 retry 由：

```text
Task Engine / Adapter Retry Policy
```

负责。

ExecutionService 不直接 while retry。

---

# 81. Execution Test Matrix

至少：

```text
Tool mismatch
Unknown operation
Missing schema
Schema invalid
Engineering invalid
Tenant denied
Permission denied
Confirmation missing
Confirmation expired
Confirmation mismatch
Idempotency replay
Idempotency key conflict
Resource locked
Capability unsupported
Dry run
Sync
Async
Adapter success
Adapter failure
Exception releases lock
```

---

# 82. Tool Mismatch Test

```text
tool:
engineering_model_query

operation:
MODEL.NODE.CREATE
```

结果：

```text
STRUCTAI-1100
```

---

# 83. Permission Test

用户：

```text
VIEWER
```

执行：

```text
MODEL.NODE.CREATE
```

结果：

```text
STRUCTAI-4000
```

---

# 84. Confirmation Test

用户：

```text
ENGINEER
```

执行：

```text
BUILD.COLUMN
```

没有 token：

```text
STRUCTAI-4100
```

---

# 85. Capability Test

软件：

```text
OpenSees
```

执行：

```text
DESIGN.STEEL
```

如果 capability：

```text
UNSUPPORTED
```

结果：

```text
STRUCTAI-3000
```

---

# 86. Idempotency Replay Test

第一次：

```text
key = column-001
```

成功。

第二次：

```text
key = column-001
same request
```

不执行 Adapter。

直接：

```text
return cached response
```

---

# 87. Idempotency Conflict Test

第一次：

```text
key = column-001
height = 6
```

第二次：

```text
key = column-001
height = 8
```

结果：

```text
STRUCTAI-1100
```

并且：

```text
Adapter 不得执行。
```

---

# 88. Lock Release Test

模拟：

```text
Adapter raises exception
```

然后：

```python
await lock_manager.acquire(...)
```

必须仍然能够成功。

否则说明：

```text
lock leak
```

---

# 89. Dry Run Test

请求：

```json
{
  "operation": "BUILD.COLUMN",
  "dry_run": true
}
```

必须：

```text
Schema = execute
Engineering Validation = execute
Permission = execute
Confirmation = execute
Capability = execute
Adapter = NOT EXECUTE
```

返回：

```text
PLANNED
```

---

# 90. Execution Pipeline 的最终职责划分

## ExecutionService

负责：

```text
Orchestration
```

## OperationResolver

负责：

```text
Operation lookup
```

## ResourceResolver

负责：

```text
Resource resolution
Tenant boundary
```

## SchemaEngine

负责：

```text
JSON Schema
```

## EngineeringValidator

负责：

```text
Engineering preconditions
```

## PermissionGuard

负责：

```text
Authorization
```

## ConfirmationGuard

负责：

```text
High-risk confirmation
```

## IdempotencyService

负责：

```text
Replay protection
```

## ResourceLockManager

负责：

```text
Concurrency
```

## CapabilityResolver

负责：

```text
Software capability
```

## TaskEngine

负责：

```text
Lifecycle
Queue
Retry
Timeout
Cancellation
Recovery
```

## Adapter

负责：

```text
Native software interaction
```

---

# 91. 严禁 ExecutionService 变成巨型类

ExecutionService 只能：

```text
coordinate
```

不能写：

```text
if MIDAS
if ETABS
if SAP2000
if OpenSees
```

也不能写：

```text
HTTP
COM
native SDK
```

如果 ExecutionService 开始出现：

```python
if product == ...
```

说明架构边界被破坏。

---

# 92. Core Alpha Execution Definition of Done

```text
[ ] ExecutionContext
[ ] ExecutionRequest
[ ] ResourceResolver
[ ] Tenant Scoped Repository
[ ] SchemaRegistry
[ ] SchemaEngine
[ ] EngineeringValidator
[ ] OperationResolver
[ ] PermissionGuard
[ ] ConfirmationGuard
[ ] IdempotencyService
[ ] Atomic Idempotency
[ ] ResourceLockManager
[ ] Optimistic Lock
[ ] CapabilityResolver
[ ] Capability Cache
[ ] Lock Policy
[ ] ExecutionService
[ ] Dry Run
[ ] Sync Execution
[ ] Async Delegation
[ ] Unified Result
[ ] Unified Error
[ ] Execution Tests
```

---

# 93. 本批次完成后的 Core 架构

```text
                 ┌───────────────────┐
                 │   MCP / HTTP / AI │
                 └─────────┬─────────┘
                           │
                           ▼
                 ┌───────────────────┐
                 │ ExecutionService  │
                 └─────────┬─────────┘
                           │
       ┌───────────────────┼───────────────────┐
       │                   │                   │
       ▼                   ▼                   ▼
 Operation             Resource             Schema
 Resolver              Resolver             Engine
       │                   │                   │
       └───────────────┬───┴───────────────────┘
                       ▼
               Engineering Validator
                       │
                       ▼
                Permission Guard
                       │
                       ▼
                Confirmation Guard
                       │
                       ▼
                Idempotency Service
                       │
                       ▼
                Resource Lock
                       │
                       ▼
              Capability Resolver
                       │
                       ▼
                  Task Engine
                       │
                       ▼
                Adapter Manager
                       │
                       ▼
             Engineering Software
```

---

# 94. 下一批：Task Engine

第十二份文档：

```text
Core Alpha Task Engine Source-Level Implementation
```

实现：

```text
P29 Task Domain
P30 Task Repository
P31 Task State Machine
P32 Task Queue
P33 Worker
P34 Task Engine
P35 DAG
P36 Dependency
P37 Retry
P38 Timeout
P39 Cancellation
P40 Progress
P41 Lease
P42 Heartbeat
P43 Recovery
P44 Task Result
P45 Task Artifact
```

目标：

把：

```text
ExecutionService
```

真正接到：

```text
Async Task
 ↓
Queue
 ↓
Worker
 ↓
Adapter
 ↓
Progress
 ↓
Result
 ↓
Recovery
```

之后才能真正执行：

```text
ANALYSIS.STATIC
DESIGN.STEEL
BUILD.COLUMN
BUILD.FRAME
```

等异步工程任务。

---

# 95. 最终阶段路线

当前已经完成设计/源码规范链：

```text
01 Database
02 Core Development
03 Core Implementation
04 Python Implementation
05 9 MCP Tools
06 Python File Blueprint
07 Core Alpha Source Spec
08 MIDAS Adapter Source Spec
09 Core Alpha Source Batch 01
10 Core Alpha Security
11 Core Alpha Execution Pipeline
```

下一阶段：

```text
12 Task Engine
13 Mock Adapter
14 Adapter Manager / Plugin Loader
15 Artifact / Document
16 Event / Audit / Trace / Metrics
17 9 MCP Tools Runtime
18 MCP Dispatcher
19 STDIO
20 Streamable HTTP
21 Core Alpha Integration
22 Core Alpha E2E
23 MIDAS API Registry
24 MIDAS Live Adapter
25 Generic AI Client E2E
```

---

# 96. 核心验收场景

完成第十一份后，可以构造：

```text
User
 ↓
Login
 ↓
IdentityContext
 ↓
engineering_model_build
 ↓
BUILD.COLUMN
 ↓
Schema
 ↓
Engineering Validation
 ↓
RBAC
 ↓
Confirmation
 ↓
Idempotency
 ↓
Lock
 ↓
Capability
 ↓
Task
 ↓
Mock Adapter
```

此时：

```text
MCP Tool
```

还没有接入，但：

```text
Core Execution Engine
```

已经可以独立测试。

这是非常重要的架构验收点。

---

# 97. 最终原则

StructAI 的真正核心不是：

```text
MCP
```

也不是：

```text
MIDAS
```

而是：

```text
Engineering Execution Kernel
```

即：

```text
Identity
+
Authorization
+
Validation
+
Resource
+
Concurrency
+
Capability
+
Task
+
Adapter
```

MCP 只是：

```text
AI ↔ StructAI
```

的标准协议入口。

MIDAS 只是：

```text
StructAI ↔ Engineering Software
```

的第一个 Adapter。

因此本批次完成后，整个架构仍然满足：

```text
9 MCP Tools = unchanged

MCP Protocol = transport layer

Core Execution Pipeline = software neutral

Task Engine = software neutral

Security = software neutral

Adapter = software specific
```

这才是 StructAI V2.0 可以持续扩展到：

```text
MIDAS
CSI ETABS
SAP2000
ANSYS
ABAQUS
OpenSees
```

而不需要重新设计 MCP Tool 层的根本基础。



# 完整收录：task

# StructAI MCP Server V2.0
# 第十二份文档：Core Alpha Task Engine 实际源码级实现
## P29-P45：Task Domain / State Machine / Queue / Worker / DAG / Retry / Timeout / Cancellation / Progress / Lease / Recovery / Result / Artifact

> 本文档承接第十一份《Core Alpha Execution Pipeline 实际源码级实现》。
>
> 第十一份已经完成：
>
> ```text
> Request
>  ↓
> Authentication
>  ↓
> ExecutionContext
>  ↓
> Operation
>  ↓
> Resource
>  ↓
> Schema
>  ↓
> Engineering Validation
>  ↓
> Permission
>  ↓
> Confirmation
>  ↓
> Idempotency
>  ↓
> Lock
>  ↓
> Capability
>  ↓
> Task
> ```
>
> 本批次正式把最后一个 `Task` 节点实现为真正可运行的 Core Alpha Task Engine。
>
> 目标不是简单做一个后台队列，而是建立 StructAI 的统一工程任务运行时：
>
> ```text
> Task
>  ↓
> State Machine
>  ↓
> Queue
>  ↓
> Worker
>  ↓
> DAG
>  ↓
> Dependency
>  ↓
> Retry
>  ↓
> Timeout
>  ↓
> Cancellation
>  ↓
> Progress
>  ↓
> Lease
>  ↓
> Heartbeat
>  ↓
> Recovery
>  ↓
> Result
>  ↓
> Artifact
> ```
>
> 本批次仍然：
>
> ```text
> Core ≠ MIDAS
> Core ≠ CSI
> Core ≠ ANSYS
> ```
>
> Task Engine 不知道任何 vendor API。

---

# 1. 本批次范围

```text
P29 Task Domain
P30 Task Repository
P31 Task State Machine
P32 Task Queue
P33 Worker
P34 Task Engine
P35 DAG
P36 Dependency
P37 Retry
P38 Timeout
P39 Cancellation
P40 Progress
P41 Lease
P42 Heartbeat
P43 Recovery
P44 Task Result
P45 Task Artifact
```

---

# 2. Task Engine 总体架构

```text
                    ExecutionService
                           │
                           ▼
                     TaskEngine
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
       TaskRepository   TaskQueue     TaskPolicy
            │              │
            │              ▼
            │           Worker
            │              │
            │       ┌──────┼──────┐
            │       ▼      ▼      ▼
            │     Retry  Timeout Cancel
            │       │      │      │
            │       └──────┼──────┘
            │              ▼
            │         AdapterManager
            │              │
            │              ▼
            │        Engineering Software
            │
            └──────── Result / Artifact
```

---

# 3. Task 生命周期

固定状态：

```text
CREATED
VALIDATING
QUEUED
RUNNING
PROCESSING
COMPLETED
FAILED
CANCEL_REQUESTED
CANCELLED
TIMEOUT
RETRYING
RECOVERING
```

---

# 4. 状态转换

正常：

```text
CREATED
  ↓
VALIDATING
  ↓
QUEUED
  ↓
RUNNING
  ↓
PROCESSING
  ↓
COMPLETED
```

失败：

```text
RUNNING
  ↓
FAILED
```

超时：

```text
RUNNING
  ↓
TIMEOUT
```

取消：

```text
RUNNING
  ↓
CANCEL_REQUESTED
  ↓
CANCELLED
```

重试：

```text
FAILED
  ↓
RETRYING
  ↓
QUEUED
```

恢复：

```text
RUNNING
  ↓
RECOVERING
  ↓
QUEUED
```

---

# 5. 状态机必须集中实现

禁止：

```python
task.status = "COMPLETED"
```

业务代码到处直接修改状态。

必须：

```python
task.transition(
    TaskStatus.COMPLETED
)
```

---

# 6. Task Entity

```python
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class Task:
    task_id: UUID
    tenant_id: UUID
    project_id: UUID | None

    request_id: str
    trace_id: str

    tool: str
    operation: str

    status: TaskStatus = TaskStatus.CREATED

    progress: int = 0

    retry_count: int = 0
    max_retries: int = 0

    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    error: dict | None = None
    result: dict | None = None

    cancel_requested: bool = False

    lease_owner: str | None = None
    lease_until: datetime | None = None

    metadata: dict = field(
        default_factory=dict
    )
```

---

# 7. Task State Machine

```python
ALLOWED_TRANSITIONS = {
    TaskStatus.CREATED: {
        TaskStatus.VALIDATING,
        TaskStatus.CANCELLED,
    },

    TaskStatus.VALIDATING: {
        TaskStatus.QUEUED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },

    TaskStatus.QUEUED: {
        TaskStatus.RUNNING,
        TaskStatus.CANCELLED,
        TaskStatus.RECOVERING,
    },

    TaskStatus.RUNNING: {
        TaskStatus.PROCESSING,
        TaskStatus.FAILED,
        TaskStatus.TIMEOUT,
        TaskStatus.CANCEL_REQUESTED,
        TaskStatus.RECOVERING,
    },

    TaskStatus.PROCESSING: {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.TIMEOUT,
        TaskStatus.CANCEL_REQUESTED,
        TaskStatus.RECOVERING,
    },

    TaskStatus.CANCEL_REQUESTED: {
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
        TaskStatus.RECOVERING,
    },

    TaskStatus.FAILED: {
        TaskStatus.RETRYING,
    },

    TaskStatus.RETRYING: {
        TaskStatus.QUEUED,
        TaskStatus.FAILED,
    },

    TaskStatus.TIMEOUT: {
        TaskStatus.RETRYING,
        TaskStatus.FAILED,
        TaskStatus.RECOVERING,
    },

    TaskStatus.RECOVERING: {
        TaskStatus.QUEUED,
        TaskStatus.RUNNING,
        TaskStatus.FAILED,
    },

    TaskStatus.COMPLETED: set(),
    TaskStatus.CANCELLED: set(),
}
```

---

# 8. Transition 方法

```python
def transition(
    self,
    new_status: TaskStatus,
) -> None:

    allowed = ALLOWED_TRANSITIONS[
        self.status
    ]

    if new_status not in allowed:
        raise TaskStateError(
            f"Invalid transition: "
            f"{self.status} -> {new_status}"
        )

    self.status = new_status
```

---

# 9. Task Repository

数据库字段扩展：

```text
task_id
tenant_id
project_id
request_id
trace_id
tool
operation
status
progress
retry_count
max_retries
started_at
completed_at
error_json
result_json
cancel_requested
lease_owner
lease_until
heartbeat_at
priority
created_at
updated_at
```

建议加入：

```text
version
```

用于 optimistic locking。

---

# 10. Task ORM

```python
from datetime import datetime
from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class TaskORM(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )

    tenant_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )

    project_id: Mapped[str | None] = mapped_column(
        String(36),
        index=True,
    )

    request_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    trace_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    tool: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    operation: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )

    progress: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    max_retries: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    cancel_requested: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    lease_owner: Mapped[str | None] = mapped_column(
        String(200),
    )

    lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    priority: Mapped[int] = mapped_column(
        Integer,
        default=100,
        nullable=False,
        index=True,
    )

    error_json: Mapped[str | None] = mapped_column(
        Text,
    )

    result_json: Mapped[str | None] = mapped_column(
        Text,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )
```

---

# 11. Task Queue

Core Alpha：

```text
asyncio.PriorityQueue
```

不引入：

```text
Redis
Celery
RabbitMQ
Kafka
```

原因：

```text
Core Alpha 先验证执行模型
```

而不是先引入基础设施复杂度。

---

# 12. Queue Item

```python
from dataclasses import dataclass


@dataclass(order=True, slots=True)
class QueueItem:
    priority: int
    sequence: int
    task_id: str
```

---

# 13. TaskQueue

```python
import asyncio
from itertools import count


class TaskQueue:

    def __init__(self):
        self._queue = asyncio.PriorityQueue()
        self._sequence = count()

    async def put(
        self,
        task_id: str,
        priority: int = 100,
    ) -> None:
        await self._queue.put(
            QueueItem(
                priority=priority,
                sequence=next(self._sequence),
                task_id=task_id,
            )
        )

    async def get(self) -> QueueItem:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    def qsize(self) -> int:
        return self._queue.qsize()
```

---

# 14. Priority

建议：

```text
0   CRITICAL
10  HIGH
50  NORMAL
100 LOW
```

数值越小：

```text
优先级越高
```

但必须防止：

```text
priority starvation
```

后续可加入 aging。

---

# 15. Worker

```python
class TaskWorker:

    def __init__(
        self,
        worker_id: str,
        queue: TaskQueue,
        task_engine,
    ):
        self.worker_id = worker_id
        self.queue = queue
        self.task_engine = task_engine
        self._running = False

    async def run(self):
        self._running = True

        while self._running:
            item = await self.queue.get()

            try:
                await self.task_engine.run_task(
                    item.task_id,
                    self.worker_id,
                )
            finally:
                self.queue.task_done()

    def stop(self):
        self._running = False
```

---

# 16. Worker 数量

Core Alpha 默认：

```text
1 Worker
```

以后：

```text
N Workers
```

但是工程软件实例可能要求：

```text
SERIAL
```

所以：

```text
Worker concurrency
≠
Software concurrency
```

最终限制由：

```text
ResourceLockManager
+
Software Instance Policy
```

决定。

---

# 17. Task Engine

```python
class TaskEngine:

    def __init__(
        self,
        repository,
        queue,
        worker_manager,
        adapter_manager,
        lock_manager,
    ):
        self.repository = repository
        self.queue = queue
        self.worker_manager = worker_manager
        self.adapter_manager = adapter_manager
        self.lock_manager = lock_manager
```

---

# 18. Create Task

```python
async def create(
    self,
    request,
    context,
    operation,
):
    task = Task(
        task_id=uuid4(),
        tenant_id=context.identity.tenant_id,
        project_id=context.project.project_id,
        request_id=context.request_id,
        trace_id=context.trace_id,
        tool=request.tool,
        operation=request.operation,
        max_retries=operation.max_retries
        if hasattr(operation, "max_retries")
        else 0,
    )

    await self.repository.create(task)

    return task
```

---

# 19. Queue Task

```python
async def enqueue(
    self,
    task: Task,
):
    task.transition(
        TaskStatus.QUEUED
    )

    await self.repository.update(
        task
    )

    await self.queue.put(
        task_id=str(task.task_id),
        priority=task.metadata.get(
            "priority",
            100,
        ),
    )
```

---

# 20. Worker Run

```python
async def run_task(
    self,
    task_id: str,
    worker_id: str,
):

    task = await self.repository.get(
        task_id
    )

    if task is None:
        return

    task.transition(
        TaskStatus.RUNNING
    )

    task.lease_owner = worker_id
    task.started_at = now()

    await self.repository.update(
        task
    )

    try:
        await self.execute_task(
            task,
            worker_id,
        )

    except TaskCancelled:
        await self.mark_cancelled(task)

    except TaskTimeout:
        await self.mark_timeout(task)

    except Exception as exc:
        await self.handle_failure(
            task,
            exc,
        )
```

---

# 21. Task Execution

```python
async def execute_task(
    self,
    task: Task,
    worker_id: str,
):

    adapter = await self.adapter_manager.resolve(
        task
    )

    task.transition(
        TaskStatus.PROCESSING
    )

    await self.repository.update(
        task
    )

    result = await self.execute_with_policy(
        task,
        adapter,
    )

    task.result = result
    task.progress = 100

    task.transition(
        TaskStatus.COMPLETED
    )

    task.completed_at = now()

    await self.repository.update(
        task
    )
```

---

# 22. Timeout

统一使用：

```python
asyncio.timeout
```

例如：

```python
import asyncio


async def execute_with_timeout(
    coroutine,
    timeout_seconds: float,
):
    try:
        async with asyncio.timeout(
            timeout_seconds
        ):
            return await coroutine

    except TimeoutError as exc:
        raise TaskTimeout() from exc
```

---

# 23. Timeout Policy

Operation 可以定义：

```text
timeout_seconds
```

例如：

```text
MODEL.NODE.QUERY
    30

BUILD.COLUMN
    120

ANALYSIS.STATIC
    1800

DESIGN.STEEL
    1800
```

实际值应由：

```text
Operation Policy
+
Tenant Policy
+
Software Policy
```

共同决定。

---

# 24. Retry Policy

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_retries: int = 0
    backoff_seconds: float = 1.0
    max_backoff_seconds: float = 60.0
```

---

# 25. Retry 判断

允许 retry：

```text
temporary network failure
adapter unavailable
timeout
rate limit
temporary software busy
```

禁止 retry：

```text
schema error
engineering validation
permission denied
tenant denied
unsupported capability
invalid credentials
invalid request
```

---

# 26. Retry Backoff

```python
import asyncio


async def backoff(
    retry_count: int,
    base: float,
    maximum: float,
):
    delay = min(
        base * (2 ** retry_count),
        maximum,
    )

    await asyncio.sleep(delay)
```

---

# 27. Retry Flow

```text
FAILED
 ↓
retryable?
 ├── NO → FAILED
 │
 └── YES
       ↓
   retry_count < max?
       ├── NO → FAILED
       │
       └── YES
             ↓
         RETRYING
             ↓
          backoff
             ↓
          QUEUED
```

---

# 28. Cancellation

请求：

```python
await task_engine.cancel(
    task_id
)
```

先：

```text
RUNNING
 ↓
CANCEL_REQUESTED
```

然后：

```text
Adapter.cancel()
```

成功：

```text
CANCELLED
```

---

# 29. Cancellation Service

```python
async def cancel(
    self,
    task_id: str,
):

    task = await self.repository.get(
        task_id
    )

    if task is None:
        raise NotFoundError(
            "Task not found"
        )

    if task.status in {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    }:
        return task

    task.cancel_requested = True

    if task.status in {
        TaskStatus.RUNNING,
        TaskStatus.PROCESSING,
    }:
        task.transition(
            TaskStatus.CANCEL_REQUESTED
        )

    await self.repository.update(
        task
    )

    return task
```

---

# 30. Cancellation 必须真实

如果软件支持：

```text
cancel
```

则：

```text
Adapter.cancel()
```

调用。

如果软件不支持：

```text
cannot cancel native operation
```

不要伪造：

```text
CANCELLED
```

必须保持：

```text
CANCEL_REQUESTED
```

或者：

```text
RECOVERING
```

最终真实状态必须可追踪。

---

# 31. Progress

统一：

```text
0 → 100
```

Task：

```python
async def update_progress(
    self,
    task_id: str,
    progress: int,
):
    progress = max(
        0,
        min(100, progress),
    )

    await self.repository.update_progress(
        task_id,
        progress,
    )
```

---

# 32. Progress Event

```python
@dataclass(frozen=True, slots=True)
class TaskProgress:
    task_id: str
    progress: int
    message: str | None = None
```

Event Bus：

```text
TaskProgress
```

后续 MCP：

```text
TaskProgress
 ↓
MCP progress notification
```

---

# 33. Progress 不可信

Adapter 返回：

```text
progress = 150
```

Core 必须归一化：

```text
100
```

Adapter 返回：

```text
-10
```

归一化：

```text
0
```

---

# 34. Lease

Worker 执行 Task 时：

```text
lease_owner
lease_until
heartbeat_at
```

例如：

```text
worker-001
lease_until = now + 30s
```

---

# 35. Lease Acquire

```python
async def acquire_lease(
    self,
    task_id: str,
    worker_id: str,
    lease_seconds: int = 30,
):
    now = datetime.now(timezone.utc)
    until = now + timedelta(
        seconds=lease_seconds
    )

    task = await self.repository.acquire_lease(
        task_id=task_id,
        worker_id=worker_id,
        now=now,
        lease_until=until,
    )

    if task is None:
        raise TaskLeaseError(
            "Task lease unavailable"
        )

    return task
```

---

# 36. Lease 原子更新

SQL 必须避免：

```text
SELECT
 ↓
UPDATE
```

导致两个 Worker 同时抢任务。

必须：

```text
UPDATE tasks
SET lease_owner = ?,
    lease_until = ?
WHERE id = ?
AND (
    lease_owner IS NULL
    OR lease_until < now
)
```

然后：

```text
affected rows = 1
```

才代表获得 Lease。

---

# 37. Heartbeat

Worker 定期：

```text
10s
```

发送 heartbeat。

如果：

```text
lease = 30s
```

建议：

```text
heartbeat < lease / 2
```

例如：

```text
10s heartbeat
30s lease
```

---

# 38. Heartbeat

```python
async def heartbeat(
    self,
    task_id: str,
    worker_id: str,
    lease_seconds: int = 30,
):

    now = datetime.now(timezone.utc)

    lease_until = (
        now
        + timedelta(
            seconds=lease_seconds
        )
    )

    await self.repository.heartbeat(
        task_id=task_id,
        worker_id=worker_id,
        heartbeat_at=now,
        lease_until=lease_until,
    )
```

---

# 39. Worker Heartbeat Loop

```python
async def heartbeat_loop(
    self,
    task_id: str,
    worker_id: str,
):
    while True:

        task = await self.repository.get(
            task_id
        )

        if task is None:
            return

        if task.status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.TIMEOUT,
        }:
            return

        await self.heartbeat(
            task_id,
            worker_id,
        )

        await asyncio.sleep(10)
```

生产实现应在：

```text
Task Worker
```

中统一管理，不要每个业务操作自己启动无限循环。

---

# 40. Recovery

服务器崩溃：

```text
Task = RUNNING
Worker = gone
Lease = expired
```

启动：

```text
RecoveryManager
```

扫描：

```text
RUNNING
PROCESSING
QUEUED
```

---

# 41. Recovery Algorithm

```text
find unfinished tasks
 ↓
check lease
 ↓
lease expired?
 ├── NO → leave running
 │
 └── YES
       ↓
   RECOVERING
       ↓
  determine policy
       ↓
REQUEUE / RESUME / FAIL
```

---

# 42. Recovery Policy

Operation：

```python
recovery_policy
```

例如：

```text
REQUEUE
RESUME
FAIL
MANUAL
```

第一阶段：

```text
REQUEUE
```

优先。

---

# 43. Recovery Service

```python
class TaskRecoveryService:

    async def recover_expired_tasks(
        self,
    ):

        tasks = await (
            self.repository
            .find_expired_leases()
        )

        for task in tasks:

            task.transition(
                TaskStatus.RECOVERING
            )

            await self.repository.update(
                task
            )

            if task.retry_count < task.max_retries:

                task.retry_count += 1

                task.transition(
                    TaskStatus.RETRYING
                )

                await self.repository.update(
                    task
                )

                await self.enqueue(task)

            else:

                task.transition(
                    TaskStatus.FAILED
                )

                task.error = {
                    "code":
                        "STRUCTAI-5300",
                    "message":
                        "Task recovery failed",
                }

                await self.repository.update(
                    task
                )
```

---

# 44. Recovery 不能重复执行危险操作

这是工程软件场景非常关键的问题。

例如：

```text
BUILD.COLUMN
```

Worker 崩溃：

```text
Native software 实际已经创建了柱
```

但 Core 不知道。

如果简单：

```text
REQUEUE
```

可能：

```text
柱子重复创建
```

因此 Recovery 必须依赖：

```text
Idempotency
+
Operation Recovery Policy
+
Adapter Native State Check
```

---

# 45. Recovery Policy 分类

```text
SAFE_RETRY
STATE_RECONCILE
MANUAL_REVIEW
FAIL
```

例如：

```text
MODEL.NODE.QUERY
    SAFE_RETRY

ANALYSIS.STATIC
    SAFE_RETRY / STATE_RECONCILE

BUILD.COLUMN
    STATE_RECONCILE

MODEL.DELETE
    STATE_RECONCILE

DESIGN.OPTIMIZE
    MANUAL_REVIEW
```

最终由 OperationDefinition 指定。

---

# 46. Task DAG

复杂工程任务不是单一步骤：

```text
BUILD.COLUMN
 ↓
ANALYSIS.STATIC
 ↓
RESULT.DISPLACEMENT
 ↓
DESIGN.STEEL
```

需要：

```text
DAG
```

---

# 47. DAG 数据结构

```python
@dataclass(slots=True)
class TaskStep:
    step_id: str
    operation: str
    parameters: dict
    depends_on: tuple[str, ...] = ()
```

Task：

```python
@dataclass(slots=True)
class TaskGraph:
    steps: dict[str, TaskStep]
```

---

# 48. DAG 校验

必须检测：

```text
missing dependency
cycle
duplicate step
unknown step
```

---

# 49. DAG Cycle Detection

```python
def validate_dag(
    graph: TaskGraph,
):
    visiting = set()
    visited = set()

    def visit(node: str):
        if node in visiting:
            raise ValidationError(
                "Task DAG contains cycle"
            )

        if node in visited:
            return

        visiting.add(node)

        for dependency in (
            graph.steps[node].depends_on
        ):
            if dependency not in graph.steps:
                raise ValidationError(
                    f"Unknown dependency: "
                    f"{dependency}"
                )

            visit(dependency)

        visiting.remove(node)
        visited.add(node)

    for node in graph.steps:
        visit(node)
```

---

# 50. DAG Scheduling

状态：

```text
PENDING
READY
RUNNING
COMPLETED
FAILED
SKIPPED
```

规则：

```text
all dependencies COMPLETED
        ↓
READY
```

如果 dependency：

```text
FAILED
```

默认：

```text
SKIPPED
```

除非明确配置：

```text
continue_on_failure = true
```

---

# 51. Parallel DAG

例如：

```text
          ┌─ RESULT.DISPLACEMENT
BUILD ────┤
          └─ RESULT.FORCE
                │
                ▼
          DESIGN.STEEL
```

两个 Result 可以并行。

但：

```text
DESIGN.STEEL
```

等待两者完成。

---

# 52. Task Step ORM

```python
class TaskStepORM(Base):
    __tablename__ = "task_steps"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )

    task_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )

    step_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    operation: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    parameters_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    depends_on_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    result_json: Mapped[str | None] = mapped_column(
        Text,
    )

    error_json: Mapped[str | None] = mapped_column(
        Text,
    )
```

---

# 53. Task Result

统一：

```python
@dataclass(frozen=True, slots=True)
class TaskResult:
    task_id: str
    success: bool
    data: dict | list | None
    warnings: list
    errors: list
    metadata: dict
```

---

# 54. Task Result Persist

Task 完成：

```text
Task
 ↓
result_json
```

但是大型结果：

```text
不要全部写 SQLite
```

例如：

```text
100000 nodes
1 million element results
```

应该：

```text
Artifact
```

---

# 55. Artifact

Artifact 类型：

```text
MODEL
ANALYSIS_RESULT
DESIGN_RESULT
CALCULATION_REPORT
SCREENSHOT
EXPORT
RAW_RESPONSE
```

---

# 56. Artifact ORM

```python
class ArtifactORM(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )

    task_id: Mapped[str | None] = mapped_column(
        String(36),
        index=True,
    )

    storage_backend: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    storage_key: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
    )

    mime_type: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    size: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    checksum: Mapped[str | None] = mapped_column(
        String(200),
    )
```

---

# 57. ArtifactStorage

```python
from typing import Protocol


class ArtifactStorage(Protocol):

    async def put(
        self,
        key: str,
        data: bytes,
        mime_type: str,
    ) -> str:
        ...

    async def get(
        self,
        key: str,
    ) -> bytes:
        ...

    async def delete(
        self,
        key: str,
    ) -> None:
        ...
```

---

# 58. Local Filesystem Storage

Core Alpha：

```text
data/artifacts/
```

实现：

```python
from pathlib import Path


class LocalFilesystemStorage:

    def __init__(
        self,
        root: Path,
    ):
        self.root = root
        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

    async def put(
        self,
        key: str,
        data: bytes,
        mime_type: str,
    ) -> str:

        path = self.root / key
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_bytes(data)

        return str(path)

    async def get(
        self,
        key: str,
    ) -> bytes:

        path = self.root / key

        return path.read_bytes()

    async def delete(
        self,
        key: str,
    ) -> None:

        path = self.root / key

        if path.exists():
            path.unlink()
```

---

# 59. Artifact Checksum

必须计算：

```text
SHA-256
```

```python
import hashlib


def checksum(data: bytes) -> str:
    return hashlib.sha256(
        data
    ).hexdigest()
```

用于：

```text
integrity
deduplication
audit
```

---

# 60. Artifact Key

推荐：

```text
tenant/
project/
task/
artifact/
```

例如：

```text
tenant-001/
project-001/
task-001/
analysis-result.json
```

禁止：

```text
../../etc/passwd
```

必须做 path traversal 防护。

---

# 61. Task Artifact Lifecycle

```text
Task Running
 ↓
Adapter
 ↓
Result
 ↓
ArtifactStorage
 ↓
Artifact Metadata
 ↓
Task Completed
```

---

# 62. Task Engine 与 Adapter

Task Engine 只调用：

```python
adapter.execute(...)
```

Adapter 不知道：

```text
Task Queue
Lease
DAG
RBAC
MCP
```

反过来：

```text
Task Engine
```

也不理解：

```text
MIDAS endpoint
COM method
ANSYS command
```

---

# 63. Adapter Cancellation

接口：

```python
async def cancel(
    self,
    task_id: str,
) -> None:
    ...
```

但是：

```text
task_id
```

是 Core Task ID。

Adapter 如果需要：

```text
native_job_id
```

必须由 Adapter 自己维护：

```text
Core Task ID
 ↕
Native Job ID
```

---

# 64. Native Job Mapping

未来可以增加：

```text
task_native_bindings
```

字段：

```text
task_id
software_instance_id
native_job_id
created_at
status
```

用于：

```text
cancel
recovery
reconciliation
```

---

# 65. Task Event

至少：

```text
TaskCreated
TaskQueued
TaskStarted
TaskProgress
TaskCompleted
TaskFailed
TaskCancelled
TaskTimeout
TaskRetrying
TaskRecovering
TaskLeaseAcquired
TaskLeaseLost
```

---

# 66. Task Event Bus

Core Alpha：

```python
class InProcessEventBus:

    def __init__(self):
        self._handlers = {}

    def subscribe(
        self,
        event_type,
        handler,
    ):
        self._handlers.setdefault(
            event_type,
            [],
        ).append(handler)

    async def publish(
        self,
        event,
    ):
        handlers = self._handlers.get(
            type(event),
            [],
        )

        for handler in handlers:
            await handler(event)
```

---

# 67. Event Bus 原则

Event Bus 用于：

```text
notification
observability
progress
audit trigger
```

不能作为：

```text
critical transaction
```

唯一持久化手段。

Task 状态必须：

```text
DB
```

持久化。

---

# 68. Task Engine Startup

启动：

```text
1. Load unfinished tasks
2. Recover expired leases
3. Requeue recoverable tasks
4. Start workers
5. Start heartbeat manager
6. Start recovery loop
```

---

# 69. Task Engine Shutdown

优雅关闭：

```text
STOP accepting new tasks
 ↓
wait current workers
 ↓
heartbeat
 ↓
persist state
 ↓
release leases
 ↓
shutdown
```

不能：

```text
process exit
```

后让 DB 中全部任务假装完成。

---

# 70. Recovery Loop

例如：

```python
async def recovery_loop(
    self,
):
    while self.running:

        await self.recovery_service.recover_expired_tasks()

        await asyncio.sleep(15)
```

第一阶段：

```text
15s
```

后续配置化。

---

# 71. Worker Shutdown

```python
async def stop(
    self,
):
    self._running = False
```

生产实现要避免：

```text
await queue.get()
```

永久阻塞。

可以：

```text
sentinel
```

或：

```text
asyncio.Event
```

---

# 72. Worker Supervisor

建议：

```text
WorkerSupervisor
```

负责：

```text
start
stop
restart
health
worker count
```

如果 Worker 异常退出：

```text
Supervisor
 ↓
restart worker
```

但不要无限快速重启。

---

# 73. Worker Crash Recovery

```text
Worker crash
 ↓
Lease expires
 ↓
Recovery Manager
 ↓
RECOVERING
 ↓
Recovery Policy
 ↓
Requeue / Fail / Manual
```

---

# 74. Task Engine Metrics

必须提供：

```text
structai_task_total
structai_task_running
structai_task_completed
structai_task_failed
structai_task_cancelled
structai_task_timeout
structai_task_retry
structai_task_recovery
structai_task_queue_size
structai_task_duration_seconds
```

---

# 75. Task Engine Test Matrix

至少：

```text
Task create
Task transition
Invalid transition
Queue FIFO within priority
Priority ordering
Worker execution
Worker exception
Retry
Retry exhaustion
Timeout
Cancellation
Progress
Lease acquisition
Lease conflict
Heartbeat
Expired lease
Recovery
DAG validation
DAG cycle
DAG dependency
DAG parallel
Task result
Artifact storage
Artifact checksum
Worker restart
```

---

# 76. State Machine Test

```python
task.transition(
    TaskStatus.VALIDATING
)

task.transition(
    TaskStatus.QUEUED
)

task.transition(
    TaskStatus.RUNNING
)

task.transition(
    TaskStatus.PROCESSING
)

task.transition(
    TaskStatus.COMPLETED
)
```

成功。

错误：

```python
task.transition(
    TaskStatus.RUNNING
)
```

在：

```text
COMPLETED
```

状态下必须：

```text
TaskStateError
```

---

# 77. Retry Test

模拟：

```text
attempt 1 → timeout
attempt 2 → timeout
attempt 3 → success
```

如果：

```text
max_retries = 2
```

那么：

```text
total attempts = 3
```

---

# 78. Timeout Test

设置：

```text
timeout = 0.1s
```

Adapter：

```text
sleep(1s)
```

结果：

```text
TIMEOUT
```

然后：

```text
retry policy
```

决定是否重试。

---

# 79. Cancellation Test

模拟：

```text
RUNNING
```

发送：

```text
cancel
```

期望：

```text
CANCEL_REQUESTED
```

Adapter 支持 cancel：

```text
CANCELLED
```

Adapter 不支持：

```text
CANCEL_REQUESTED
```

直到 native state 可确认。

---

# 80. Lease Conflict Test

Worker A：

```text
lease acquired
```

Worker B：

```text
same task
```

必须：

```text
TaskLeaseError
```

Worker B 不得执行。

---

# 81. Recovery Test

数据库：

```text
status = RUNNING
lease_until = expired
```

Recovery：

```text
RECOVERING
 →
RETRYING
 →
QUEUED
```

然后 Worker：

```text
RUNNING
```

---

# 82. DAG Test

```text
A
↓
B
↓
C
```

执行：

```text
A
B
C
```

不能：

```text
C
B
A
```

---

# 83. DAG Parallel Test

```text
      A
     / \
    B   C
     \ /
      D
```

执行约束：

```text
A before B/C
B and C before D
```

B/C 可以并行。

---

# 84. Artifact Test

写入：

```text
analysis.json
```

计算：

```text
sha256
```

读取后：

```text
checksum(original)
==
checksum(read)
```

必须成立。

---

# 85. Task Engine Definition of Done

```text
[ ] Task Entity
[ ] State Machine
[ ] Task Repository
[ ] Task Queue
[ ] Priority
[ ] Worker
[ ] Worker Supervisor
[ ] Task Engine
[ ] Retry
[ ] Backoff
[ ] Timeout
[ ] Cancellation
[ ] Progress
[ ] Lease
[ ] Heartbeat
[ ] Recovery
[ ] DAG
[ ] Dependency
[ ] Parallel Steps
[ ] Task Result
[ ] Artifact
[ ] Checksum
[ ] Task Events
[ ] Task Metrics
[ ] Startup Recovery
[ ] Graceful Shutdown
[ ] Crash Recovery Tests
```

---

# 86. ExecutionService 与 TaskEngine 接口

第十一份中的：

```python
task = await self.task_engine.execute(
    request=request,
    context=context,
    operation=operation,
)
```

现在正式定义为：

```python
async def execute(
    self,
    request,
    context,
    operation,
):
    task = await self.create(
        request,
        context,
        operation,
    )

    if operation.execution_mode == ExecutionMode.SYNC:
        return await self.run_sync(
            task
        )

    await self.enqueue(task)

    return task
```

---

# 87. Sync Task

即使：

```text
SYNC
```

也建议：

```text
Task Engine
```

统一执行。

区别只是：

```text
SYNC
```

等待完成：

```text
await task
```

而：

```text
ASYNC
```

立即返回：

```text
task_id
```

---

# 88. Sync Execution

```python
async def run_sync(
    self,
    task,
):
    await self.execute_task(
        task,
        worker_id="sync-worker",
    )

    return task
```

以后可以统一成：

```text
worker
```

实现。

---

# 89. Async Execution

```python
await self.enqueue(task)

return {
    "mode": "ASYNC",
    "status": "QUEUED",
    "task_id": str(task.task_id),
}
```

---

# 90. Task Engine 与 Idempotency

顺序：

```text
ExecutionService
 ↓
Idempotency
 ↓
Task Create
```

不能：

```text
Task Create
 ↓
Idempotency
```

否则重复请求可能先创建多个 Task。

---

# 91. Task Engine 与 Lock

对于长任务：

```text
Lock
```

必须覆盖实际执行期间。

因此：

```text
Task Created
 ↓
Queued
```

时不一定立即持有 Model Write Lock。

推荐：

```text
Worker 获得 Task
 ↓
Acquire Resource Lock
 ↓
Execute
 ↓
Release
```

这样队列不会长时间占用锁。

---

# 92. Task Engine 与 Confirmation

Confirmation 必须在：

```text
Task 创建之前
```

完成。

不能：

```text
Task queued
 ↓
等待用户 confirmation
```

否则会产生：

```text
untrusted pending task
```

---

# 93. Task Engine 与 Capability

Capability 应在：

```text
Task 创建之前
```

完成基本检查。

运行时如果软件版本发生变化：

```text
Adapter
 ↓
Runtime capability recheck
```

失败：

```text
TASK FAILED
STRUCTAI-3000
```

---

# 94. Task Engine 最终位置

最终：

```text
                 ExecutionService
                        │
       ┌────────────────┼────────────────┐
       │                │                │
       ▼                ▼                ▼
   Security        Validation       Capability
       │                │                │
       └────────────────┼────────────────┘
                        ▼
                    TaskEngine
                        │
                ┌───────┴───────┐
                ▼               ▼
              Queue           DAG
                │               │
                └───────┬───────┘
                        ▼
                      Worker
                        │
                  Resource Lock
                        │
                     Adapter
                        │
                Engineering Software
```

---

# 95. 下一批

第十三份：

```text
Core Alpha Mock Adapter + Adapter Manager + Plugin Loader
```

实现：

```text
P46 Adapter Base
P47 Adapter Manifest
P48 Adapter Manager
P49 Plugin Loader
P50 Mock Adapter
P51 Mock Model Store
P52 Capability Detection
P53 Adapter Lifecycle
P54 Adapter Health
P55 Adapter Error Normalization
P56 Adapter Cancellation
```

目标：

让当前 Core 在没有 MIDAS 的情况下，可以通过：

```text
Mock Adapter
```

真正跑通：

```text
BUILD.COLUMN
 ↓
MODEL.LOAD.ASSIGN
 ↓
ANALYSIS.STATIC
 ↓
RESULT.NODE.DISPLACEMENT
 ↓
DESIGN.STEEL
```

然后再进入真正的：

```text
MIDAS Adapter
```

---

# 96. 本批次最终结论

到第十二份完成后，StructAI Core Alpha 已经形成：

```text
Security
+
Execution Pipeline
+
Task Runtime
```

三大核心。

即：

```text
Who can execute?
    → Security

What can execute?
    → Execution Pipeline

How does it execute reliably?
    → Task Engine
```

最终工程软件只需要实现：

```text
Adapter
```

即可接入整个运行时。

这保证未来增加：

```text
MIDAS
ETABS
SAP2000
ANSYS
ABAQUS
OpenSees
```

时，不需要重新设计：

```text
Security
Task
Execution
MCP
AI
```

而只增加：

```text
Adapter
+
Capability Mapping
+
Operation Mapping
+
API Registry
```



# 完整收录：adapter

# StructAI MCP Server V2.0
# 第十三份文档：Core Alpha Mock Adapter + Adapter Manager + Plugin Loader
## P46-P56：Adapter Base / Manifest / Manager / Plugin Loader / Mock Adapter / Model Store / Capability / Lifecycle / Health / Error / Cancellation

> 本文档承接第十二份《Core Alpha Task Engine 实际源码级实现》。
>
> 第十二份已经完成：
>
> ```text
> Security
> ↓
> Execution Pipeline
> ↓
> Task Engine
> ```
>
> 本批次正式实现 Core 与工程软件之间的 Adapter 层。
>
> 第一原则：
>
> ```text
> Core 不认识 MIDAS
> Core 不认识 ETABS
> Core 不认识 SAP2000
> Core 不认识 ANSYS
> ```
>
> Core 只认识：
>
> ```text
> EngineeringSoftwareAdapter
> ```
>
> 为了在没有真实工程软件的情况下验证 Core，本批次先实现：
>
> ```text
> Mock Adapter
> ```
>
> 最终跑通：
>
> ```text
> BUILD.COLUMN
> ↓
> MODEL.LOAD.ASSIGN
> ↓
> ANALYSIS.STATIC
> ↓
> RESULT.NODE.DISPLACEMENT
> ↓
> DESIGN.STEEL
> ```
>
> 然后下一阶段才接入真正 MIDAS Adapter。

---

# 1. 本批次范围

```text
P46 Adapter Base
P47 Adapter Manifest
P48 Adapter Manager
P49 Plugin Loader
P50 Mock Adapter
P51 Mock Model Store
P52 Capability Detection
P53 Adapter Lifecycle
P54 Adapter Health
P55 Adapter Error Normalization
P56 Adapter Cancellation
```

---

# 2. Adapter 总体职责

Adapter 负责：

```text
Connection
Authentication
Version
Capability Detection
Operation Mapping
Parameter Transform
Native Execution
Response Transform
Error Normalization
Cancellation
Health
```

Adapter 不负责：

```text
MCP
RBAC
Authentication Context
Tenant Isolation
Task Lifecycle
Global Idempotency
Global Lock
AI
UI
```

---

# 3. Adapter Architecture

```text
                 Core
                  │
                  ▼
          AdapterManager
                  │
           ┌──────┴──────┐
           ▼             ▼
      Adapter Registry  Plugin Loader
           │
           ▼
 EngineeringSoftwareAdapter
           │
    ┌──────┼──────────────┐
    ▼      ▼              ▼
  Mock   MIDAS           CSI
 Adapter Adapter        Adapter
```

---

# 4. Adapter Interface

文件：

```text
app/infrastructure/adapters/base/adapter.py
```

```python
from abc import ABC, abstractmethod


class EngineeringSoftwareAdapter(ABC):

    name: str
    vendor: str
    product: str

    @abstractmethod
    async def connect(
        self,
        config: dict,
    ) -> None:
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    @abstractmethod
    async def health_check(self) -> dict:
        ...

    @abstractmethod
    async def get_version(self) -> str:
        ...

    @abstractmethod
    async def get_capabilities(
        self,
    ) -> list[str]:
        ...

    @abstractmethod
    async def execute(
        self,
        operation: str,
        parameters: dict,
        context,
    ) -> dict:
        ...

    @abstractmethod
    async def cancel(
        self,
        task_id: str,
    ) -> None:
        ...

    @abstractmethod
    async def normalize_error(
        self,
        error: Exception,
    ) -> dict:
        ...
```

---

# 5. Adapter Context

Adapter 不应该接收任意全局对象。

定义：

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AdapterContext:
    software_instance_id: str
    product: str
    version: str
    tenant_id: str
    project_id: str | None
    task_id: str | None
```

Adapter Context 不携带：

```text
password
session token
global permissions
raw client request
```

---

# 6. Adapter Manifest

每个 Adapter 必须声明：

```json
{
  "name": "structai.mock",
  "vendor": "StructAI",
  "product": "MockEngineering",
  "versions": ["1.0"],
  "protocols": ["IN_PROCESS"],
  "capabilities": [
    "MODEL.NODE.READ",
    "MODEL.NODE.WRITE",
    "MODEL.ELEMENT.READ",
    "MODEL.ELEMENT.WRITE",
    "MODEL.LOAD.WRITE",
    "ANALYSIS.STATIC",
    "RESULT.DISPLACEMENT",
    "DESIGN.STEEL"
  ]
}
```

---

# 7. Manifest Python Model

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AdapterManifest:
    name: str
    vendor: str
    product: str
    supported_versions: tuple[str, ...]
    protocols: tuple[str, ...]
    capabilities: tuple[str, ...]
```

---

# 8. Adapter Lifecycle

状态：

```text
CREATED
 ↓
CONNECTING
 ↓
CONNECTED
 ↓
READY
 ↓
DISCONNECTING
 ↓
DISCONNECTED
```

错误：

```text
ERROR
```

---

# 9. Lifecycle State

```python
from enum import StrEnum


class AdapterState(StrEnum):
    CREATED = "CREATED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    READY = "READY"
    DISCONNECTING = "DISCONNECTING"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"
```

---

# 10. Adapter Base State

```python
class BaseAdapter(EngineeringSoftwareAdapter):

    def __init__(self):
        self.state = AdapterState.CREATED

    async def connect(
        self,
        config: dict,
    ) -> None:
        self.state = AdapterState.CONNECTING

        try:
            await self._connect(config)

            self.state = AdapterState.CONNECTED

            await self._initialize()

            self.state = AdapterState.READY

        except Exception:
            self.state = AdapterState.ERROR
            raise

    async def disconnect(self) -> None:
        if self.state in {
            AdapterState.DISCONNECTED,
            AdapterState.CREATED,
        }:
            return

        self.state = AdapterState.DISCONNECTING

        try:
            await self._disconnect()

        finally:
            self.state = (
                AdapterState.DISCONNECTED
            )
```

---

# 11. Adapter Initialize

连接成功后：

```text
connect
 ↓
version detection
 ↓
capability detection
 ↓
health check
 ↓
READY
```

---

# 12. Adapter Manager

```python
class AdapterManager:

    def __init__(self):
        self._adapters = {}
```

注册：

```python
def register(
    self,
    adapter: EngineeringSoftwareAdapter,
):
    key = (
        adapter.vendor,
        adapter.product,
        adapter.name,
    )

    self._adapters[key] = adapter
```

---

# 13. Resolve Adapter

```python
def resolve(
    self,
    *,
    vendor: str,
    product: str,
    name: str,
):
    key = (
        vendor,
        product,
        name,
    )

    adapter = self._adapters.get(key)

    if adapter is None:
        raise AdapterNotFoundError(
            f"Adapter not found: {key}"
        )

    return adapter
```

实际项目中推荐进一步使用：

```text
SoftwareInstance
 ↓
adapter_id
```

而不是每次只根据字符串查找。

---

# 14. Adapter Instance Registry

需要区分：

```text
Adapter Package
Adapter Instance
Software Instance
```

例如：

```text
Package:
structai.midas

Instance:
midas-adapter-001

Software:
MIDAS CIVIL NX 2026
```

---

# 15. Adapter Instance ORM

建议增加：

```python
class AdapterInstanceORM(Base):
    __tablename__ = "adapter_instances"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )

    software_instance_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
    )

    adapter_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    state: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    last_health_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    error_json: Mapped[str | None] = mapped_column(
        Text,
    )
```

---

# 16. Plugin Loader

Python Entry Point：

```toml
[project.entry-points."structai.adapters"]
mock = "structai_mock.adapter:MockAdapter"
```

未来：

```toml
midas = "structai_midas.adapter:MidasAdapter"
csi = "structai_csi.adapter:CSIAdapter"
ansys = "structai_ansys.adapter:AnsysAdapter"
```

---

# 17. Plugin Loader 实现

使用：

```python
from importlib.metadata import entry_points


class AdapterPluginLoader:

    def load_all(self):
        entries = entry_points(
            group="structai.adapters"
        )

        adapters = []

        for entry in entries:
            adapter_cls = entry.load()

            adapter = adapter_cls()

            adapters.append(adapter)

        return adapters
```

---

# 18. Plugin Loader 安全

禁止从数据库直接执行：

```text
Python code
eval
exec
```

数据库只能保存：

```text
adapter name
package
version
configuration
```

代码必须来自：

```text
installed Python package
```

---

# 19. Plugin Manifest Validation

加载后：

```python
def validate_manifest(
    manifest: AdapterManifest,
):
    if not manifest.name:
        raise ConfigurationError(
            "Adapter name is required"
        )

    if not manifest.vendor:
        raise ConfigurationError(
            "Adapter vendor is required"
        )

    if not manifest.product:
        raise ConfigurationError(
            "Adapter product is required"
        )

    if not manifest.supported_versions:
        raise ConfigurationError(
            "Adapter versions are required"
        )
```

---

# 20. Version Matching

严格优先：

```text
Exact Version
```

例如：

```text
requested = 2026
supported = [2025, 2026]
```

选择：

```text
2026
```

如果：

```text
requested = 2027
```

而没有兼容声明：

```text
reject
```

不能偷偷使用：

```text
2026
```

---

# 21. Capability Detection

Capability 来源：

```text
Static Manifest
+
Version Mapping
+
Runtime Detection
```

最终：

```text
SUPPORTED
UNSUPPORTED
UNKNOWN
```

---

# 22. Capability Provider

```python
class AdapterCapabilityProvider:

    async def detect(
        self,
        adapter,
    ) -> dict[str, str]:

        capabilities = (
            await adapter.get_capabilities()
        )

        return {
            capability:
                "SUPPORTED"
            for capability in capabilities
        }
```

---

# 23. Runtime Capability

如果 Adapter 能动态检测：

```text
GET capabilities
```

必须优先使用 runtime。

否则：

```text
Manifest
+
Version Registry
```

---

# 24. Capability Cache

核心：

```text
software_instance_id
capability
status
checked_at
expires_at
```

Adapter reconnect：

```text
invalidate
```

Version change：

```text
invalidate
```

---

# 25. Health Check

统一返回：

```json
{
  "healthy": true,
  "state": "READY",
  "version": "1.0",
  "latency_ms": 3
}
```

---

# 26. Health 不等于 Capability

：

```text
healthy = true
```

不代表：

```text
ANALYSIS.NONLINEAR supported
```

必须分别：

```text
Health
Capability
```

---

# 27. Mock Model Store

文件：

```text
app/infrastructure/adapters/mock/model_store.py
```

使用：

```python
@dataclass
class MockNode:
    id: int
    x: float
    y: float
    z: float


@dataclass
class MockElement:
    id: int
    node_ids: tuple[int, ...]
    material: str | None = None
    section: str | None = None


@dataclass
class MockLoad:
    node_id: int
    fx: float
    fy: float
    fz: float
```

---

# 28. MockModelStore

```python
class MockModelStore:

    def __init__(self):
        self.nodes = {}
        self.elements = {}
        self.loads = {}
        self.materials = {}
        self.sections = {}
        self.boundaries = {}

    def clear(self):
        self.nodes.clear()
        self.elements.clear()
        self.loads.clear()
        self.materials.clear()
        self.sections.clear()
        self.boundaries.clear()
```

---

# 29. Mock Adapter

```python
class MockAdapter(BaseAdapter):

    name = "structai.mock"
    vendor = "StructAI"
    product = "MockEngineering"

    def __init__(self):
        super().__init__()
        self.store = MockModelStore()
        self.version = "1.0"
```

---

# 30. Mock Capabilities

至少：

```text
MODEL.NODE.READ
MODEL.NODE.WRITE
MODEL.NODE.DELETE

MODEL.ELEMENT.READ
MODEL.ELEMENT.WRITE
MODEL.ELEMENT.DELETE

MODEL.MATERIAL.READ
MODEL.MATERIAL.WRITE

MODEL.SECTION.READ
MODEL.SECTION.WRITE

MODEL.BOUNDARY.READ
MODEL.BOUNDARY.WRITE

MODEL.LOAD.READ
MODEL.LOAD.WRITE
MODEL.LOAD.DELETE

ANALYSIS.STATIC

RESULT.DISPLACEMENT
RESULT.REACTION
RESULT.ELEMENT_FORCE
RESULT.STRESS

DESIGN.STEEL
```

---

# 31. Mock Connect

```python
async def _connect(
    self,
    config: dict,
):
    self.config = config
```

Mock 不需要真实网络。

---

# 32. Mock Version

```python
async def get_version(self):
    return self.version
```

---

# 33. Mock Health

```python
async def health_check(self):
    return {
        "healthy": (
            self.state == AdapterState.READY
        ),
        "state": self.state.value,
        "version": self.version,
        "latency_ms": 0,
    }
```

---

# 34. Mock Node Create

```python
async def create_node(
    self,
    parameters: dict,
):
    node_id = int(
        parameters["id"]
    )

    if node_id in self.store.nodes:
        raise MockDuplicateError(
            "Node already exists"
        )

    node = MockNode(
        id=node_id,
        x=float(parameters["x"]),
        y=float(parameters["y"]),
        z=float(parameters["z"]),
    )

    self.store.nodes[node_id] = node

    return {
        "id": node_id,
        "x": node.x,
        "y": node.y,
        "z": node.z,
    }
```

---

# 35. Mock Node Query

```python
async def query_nodes(
    self,
    parameters: dict,
):
    nodes = list(
        self.store.nodes.values()
    )

    return {
        "items": [
            {
                "id": node.id,
                "x": node.x,
                "y": node.y,
                "z": node.z,
            }
            for node in nodes
        ],
        "pagination": {
            "has_more": False,
            "next_cursor": None,
        },
    }
```

---

# 36. Mock Element Create

```python
async def create_element(
    self,
    parameters: dict,
):
    element_id = int(
        parameters["id"]
    )

    node_ids = tuple(
        int(x)
        for x in parameters["node_ids"]
    )

    for node_id in node_ids:
        if node_id not in self.store.nodes:
            raise MockValidationError(
                f"Node not found: {node_id}"
            )

    element = MockElement(
        id=element_id,
        node_ids=node_ids,
        material=parameters.get(
            "material"
        ),
        section=parameters.get(
            "section"
        ),
    )

    self.store.elements[element_id] = element

    return {
        "id": element_id,
        "node_ids": list(node_ids),
    }
```

---

# 37. Mock Column Builder

这是 Core Alpha 最重要的演示操作。

输入：

```json
{
  "base_node_id": 1,
  "top_node_id": 2,
  "height": 6,
  "section": "H400x400x13x21",
  "material": "Q355B"
}
```

如果没有指定节点：

```text
自动创建：
base node
top node
```

然后：

```text
CREATE ELEMENT
ASSIGN MATERIAL
ASSIGN SECTION
```

---

# 38. BUILD.COLUMN

```python
async def build_column(
    self,
    parameters: dict,
):

    base_id = parameters.get(
        "base_node_id",
        1,
    )

    top_id = parameters.get(
        "top_node_id",
        2,
    )

    height = float(
        parameters["height"]
    )

    if base_id not in self.store.nodes:
        await self.create_node({
            "id": base_id,
            "x": 0,
            "y": 0,
            "z": 0,
        })

    if top_id not in self.store.nodes:
        await self.create_node({
            "id": top_id,
            "x": 0,
            "y": 0,
            "z": height,
        })

    element_id = int(
        parameters.get(
            "element_id",
            max(
                self.store.elements.keys(),
                default=0,
            ) + 1,
        )
    )

    return await self.create_element({
        "id": element_id,
        "node_ids": [
            base_id,
            top_id,
        ],
        "material": parameters.get(
            "material",
            "Q355B",
        ),
        "section": parameters.get(
            "section",
            "H400x400x13x21",
        ),
    })
```

---

# 39. Boundary Assignment

```python
async def assign_boundary(
    self,
    parameters: dict,
):

    node_id = int(
        parameters["node_id"]
    )

    if node_id not in self.store.nodes:
        raise MockValidationError(
            "Node does not exist"
        )

    self.store.boundaries[node_id] = {
        "ux": bool(parameters.get("ux", False)),
        "uy": bool(parameters.get("uy", False)),
        "uz": bool(parameters.get("uz", False)),
        "rx": bool(parameters.get("rx", False)),
        "ry": bool(parameters.get("ry", False)),
        "rz": bool(parameters.get("rz", False)),
    }

    return self.store.boundaries[node_id]
```

---

# 40. Load Assignment

```python
async def assign_load(
    self,
    parameters: dict,
):

    node_id = int(
        parameters["node_id"]
    )

    if node_id not in self.store.nodes:
        raise MockValidationError(
            "Node does not exist"
        )

    load = MockLoad(
        node_id=node_id,
        fx=float(
            parameters.get("fx", 0)
        ),
        fy=float(
            parameters.get("fy", 0)
        ),
        fz=float(
            parameters.get("fz", 0)
        ),
    )

    self.store.loads[node_id] = load

    return {
        "node_id": node_id,
        "fx": load.fx,
        "fy": load.fy,
        "fz": load.fz,
    }
```

---

# 41. Mock Static Analysis

Mock 不声称是工程真实求解器。

它只用于：

```text
Core integration test
```

因此必须明确：

```text
NOT ENGINEERING-GRADE
```

---

# 42. Mock Static Analysis Algorithm

对于单柱：

```text
F
L
E
A
```

用极简：

```text
δ = F L / (E A)
```

近似生成：

```text
top displacement
```

但是结果必须标记：

```json
{
  "engine": "MockEngineering",
  "engineering_grade": false
}
```

---

# 43. Mock Material

例如：

```text
Q355B
```

定义：

```python
MATERIALS = {
    "Q355B": {
        "E": 2.06e11,
        "fy": 355e6,
    },
    "Q235B": {
        "E": 2.06e11,
        "fy": 235e6,
    },
}
```

---

# 44. Mock Section

```python
SECTIONS = {
    "H400x400x13x21": {
        "area": 0.025,
        "iy": 0.20,
        "iz": 0.20,
    }
}
```

注意：

```text
这是测试数据
```

不是规范数据库。

---

# 45. Mock Static

```python
async def analysis_static(
    self,
    parameters: dict,
):

    if not self.store.nodes:
        raise MockValidationError(
            "No nodes"
        )

    if not self.store.elements:
        raise MockValidationError(
            "No elements"
        )

    return {
        "status": "COMPLETED",
        "analysis_type": "STATIC",
        "engine": "MockEngineering",
        "engineering_grade": False,
    }
```

---

# 46. Mock Displacement

```python
async def result_displacement(
    self,
    parameters: dict,
):

    node_id = int(
        parameters["node_id"]
    )

    if node_id not in self.store.nodes:
        raise MockValidationError(
            "Node not found"
        )

    load = self.store.loads.get(
        node_id
    )

    fz = (
        abs(load.fz)
        if load
        else 0
    )

    displacement = (
        fz * 1e-8
    )

    return {
        "node_id": node_id,
        "ux": 0.0,
        "uy": 0.0,
        "uz": displacement,
        "engine": "MockEngineering",
        "engineering_grade": False,
    }
```

---

# 47. Mock Steel Design

Mock 设计：

```text
仅用于验证 Design Pipeline
```

返回：

```json
{
  "status": "PASS",
  "utilization": 0.72,
  "engine": "MockEngineering",
  "engineering_grade": false
}
```

---

# 48. Mock Operation Dispatcher

```python
async def execute(
    self,
    operation: str,
    parameters: dict,
    context,
):

    handlers = {
        "MODEL.NODE.CREATE":
            self.create_node,

        "MODEL.NODE.QUERY":
            self.query_nodes,

        "MODEL.ELEMENT.CREATE":
            self.create_element,

        "BUILD.COLUMN":
            self.build_column,

        "MODEL.BOUNDARY.ASSIGN":
            self.assign_boundary,

        "MODEL.LOAD.ASSIGN":
            self.assign_load,

        "ANALYSIS.STATIC":
            self.analysis_static,

        "RESULT.NODE.DISPLACEMENT":
            self.result_displacement,

        "DESIGN.STEEL":
            self.design_steel,
    }

    handler = handlers.get(
        operation
    )

    if handler is None:
        raise AdapterCapabilityError(
            f"Unsupported operation: {operation}"
        )

    return await handler(
        parameters
    )
```

---

# 49. Mock Error Normalization

```python
async def normalize_error(
    self,
    error: Exception,
):

    if isinstance(
        error,
        MockValidationError,
    ):
        return {
            "code":
                "STRUCTAI-1200",
            "type":
                "ENGINEERING_VALIDATION_ERROR",
            "message":
                str(error),
            "retryable":
                False,
        }

    if isinstance(
        error,
        MockDuplicateError,
    ):
        return {
            "code":
                "STRUCTAI-1200",
            "type":
                "ENGINEERING_VALIDATION_ERROR",
            "message":
                str(error),
            "retryable":
                False,
        }

    return {
        "code":
            "STRUCTAI-6000",
        "type":
            "ADAPTER_ERROR",
        "message":
            "Mock adapter error",
        "retryable":
            False,
    }
```

---

# 50. Adapter Error 原则

Core 不允许直接暴露：

```text
native exception
```

Adapter 必须转换成：

```text
StructAI Error
```

统一：

```text
STRUCTAI-2000 Software Connection
STRUCTAI-2100 Software Authentication
STRUCTAI-2200 Software API
STRUCTAI-2300 Software Timeout
STRUCTAI-3000 Capability
STRUCTAI-6000 Adapter
```

---

# 51. Adapter Cancellation

Mock：

```python
async def cancel(
    self,
    task_id: str,
):
    return None
```

代表：

```text
Mock operation immediately cancellable
```

真实 MIDAS Adapter 必须根据实际 API 判断。

---

# 52. Adapter Health Manager

```python
class AdapterHealthManager:

    async def check(
        self,
        adapter,
    ):
        try:
            return await adapter.health_check()

        except Exception as exc:
            return {
                "healthy": False,
                "state": "ERROR",
                "error": {
                    "type": type(exc).__name__,
                },
            }
```

---

# 53. Health 隔离原则

一个：

```text
MIDAS instance
```

挂掉：

```text
Core = READY
```

只有：

```text
that instance = unhealthy
```

不能：

```text
Core readiness = false
```

---

# 54. Adapter Manager Lifecycle

启动：

```text
Plugin Loader
 ↓
Load Adapters
 ↓
Validate Manifest
 ↓
Register
 ↓
Create Instances
 ↓
Connect
 ↓
Health Check
 ↓
Capability Detection
 ↓
READY
```

---

# 55. Adapter Shutdown

```text
STOP
 ↓
Reject new execution
 ↓
Wait current tasks
 ↓
Disconnect adapters
 ↓
Release resources
 ↓
Shutdown
```

---

# 56. Adapter Manager Resolve by SoftwareInstance

推荐最终：

```python
async def resolve_for_instance(
    self,
    software_instance_id: str,
):
    instance = await (
        self.software_repository
        .get_instance(
            software_instance_id
        )
    )

    if instance is None:
        raise NotFoundError(
            "Software instance not found"
        )

    adapter = self._instances.get(
        software_instance_id
    )

    if adapter is None:
        raise AdapterNotFoundError(
            "Adapter instance not loaded"
        )

    return adapter
```

---

# 57. Adapter 与 Capability Resolver

Capability Resolver：

```text
Core
 ↓
AdapterManager
 ↓
Adapter.get_capabilities()
```

但最终缓存：

```text
CapabilityCache
```

避免每个请求都探测软件。

---

# 58. Adapter 与 API Registry

Adapter 只知道：

```text
Operation
```

API Registry：

```text
Operation
 ↓
Product
 ↓
Version
 ↓
Native API
```

例如未来：

```text
ANALYSIS.STATIC
```

可能映射：

```text
MIDAS CIVIL 2026
 → REST / xxx

ETABS 22
 → COM RunAnalysis

OpenSees
 → Script analyze
```

Core 不知道这些差异。

---

# 59. Mock API Registry

Mock：

```text
BUILD.COLUMN
 → build_column

MODEL.NODE.CREATE
 → create_node

MODEL.NODE.QUERY
 → query_nodes

ANALYSIS.STATIC
 → analysis_static

RESULT.NODE.DISPLACEMENT
 → result_displacement

DESIGN.STEEL
 → design_steel
```

---

# 60. Adapter Test

必须测试：

```text
connect
disconnect
health
version
capabilities
operation dispatch
unsupported operation
error normalization
cancel
```

---

# 61. Mock Integration Test

核心测试场景：

```text
1. connect Mock
2. BUILD.COLUMN
3. QUERY nodes
4. QUERY elements
5. ASSIGN boundary
6. ASSIGN load
7. ANALYSIS.STATIC
8. RESULT.NODE.DISPLACEMENT
9. DESIGN.STEEL
```

---

# 62. 完整 Mock E2E

输入：

```text
创建高度 6m 的 Q355B H400×400×13×21 钢柱
底部固定
顶部施加 500kN 轴压力
进行静力分析
返回顶部节点位移
返回钢柱设计利用率
```

流程：

```text
BUILD.COLUMN
      ↓
MODEL.BOUNDARY.ASSIGN
      ↓
MODEL.LOAD.ASSIGN
      ↓
ANALYSIS.STATIC
      ↓
RESULT.NODE.DISPLACEMENT
      ↓
DESIGN.STEEL
```

---

# 63. Mock E2E 预期

```text
BUILD.COLUMN
    success

BOUNDARY
    success

LOAD
    success

ANALYSIS.STATIC
    COMPLETED

DISPLACEMENT
    returned

DESIGN.STEEL
    returned
```

所有结果：

```text
engineering_grade = false
```

---

# 64. 为什么 Mock 必须先于 MIDAS

因为可以独立验证：

```text
Security
Execution
Task
Adapter
Capability
Result
```

如果直接接 MIDAS：

```text
Core Bug
+
MIDAS API Bug
+
Network Bug
+
MIDAS Version Bug
```

会导致问题无法隔离。

Mock Adapter 可以作为：

```text
Core Contract Test Reference
```

---

# 65. Mock Adapter 不允许成为生产计算器

必须明确：

```text
MockEngineering
```

只用于：

```text
unit test
integration test
e2e test
demo
development
```

不用于：

```text
正式设计
施工图
审查
工程计算报告
```

---

# 66. Adapter Contract Test

所有真实 Adapter 必须通过同一套：

```text
Adapter Contract Tests
```

例如：

```python
class AdapterContract:

    async def test_connect(...):
        ...

    async def test_health(...):
        ...

    async def test_version(...):
        ...

    async def test_capabilities(...):
        ...

    async def test_execute_node_create(...):
        ...

    async def test_execute_node_query(...):
        ...

    async def test_normalize_error(...):
        ...
```

Mock：

```text
PASS
```

MIDAS：

```text
必须 PASS
```

CSI：

```text
必须 PASS
```

---

# 67. Adapter Contract 的价值

以后新增：

```text
ANSYS
```

不需要重新设计 Core。

只需要：

```text
实现 Adapter
 ↓
通过 Contract Tests
 ↓
注册 Plugin
 ↓
注册 Capability
 ↓
注册 Operation Mapping
```

---

# 68. Adapter Manager Definition of Done

```text
[ ] Adapter Interface
[ ] Adapter Context
[ ] Manifest
[ ] Lifecycle
[ ] Adapter Manager
[ ] Adapter Instance Registry
[ ] Plugin Loader
[ ] Entry Point
[ ] Manifest Validation
[ ] Version Matching
[ ] Capability Detection
[ ] Capability Cache
[ ] Health Check
[ ] Error Normalization
[ ] Cancellation
[ ] Mock Adapter
[ ] Mock Model Store
[ ] Mock Static Analysis
[ ] Mock Result
[ ] Mock Design
[ ] Contract Tests
[ ] Mock E2E
```

---

# 69. 当前 Core Alpha 已形成的完整链

```text
MCP / HTTP / AI
       ↓
Authentication
       ↓
IdentityContext
       ↓
ExecutionContext
       ↓
OperationResolver
       ↓
ResourceResolver
       ↓
SchemaEngine
       ↓
EngineeringValidator
       ↓
PermissionGuard
       ↓
ConfirmationGuard
       ↓
Idempotency
       ↓
ResourceLock
       ↓
CapabilityResolver
       ↓
TaskEngine
       ↓
AdapterManager
       ↓
Mock / MIDAS / CSI / ANSYS
       ↓
Engineering Software
```

---

# 70. 下一份文档

第十四份：

```text
Core Alpha Artifact / Document / Event / Audit / Trace / Metrics
```

实现：

```text
P57 Artifact Storage
P58 Document Service
P59 Event Bus
P60 Audit Service
P61 Trace Service
P62 Metrics
P63 Health
P64 Backup
P65 Restore
P66 Retention
```

完成后 Core Alpha 才拥有完整的：

```text
执行
任务
适配器
结果
文件
事件
审计
追踪
监控
备份
恢复
```

然后进入：

```text
第十五份：9 MCP Tools Runtime
```

正式把之前确定的九个 software-neutral MCP Tool 接入 Core ExecutionService。

---

# 71. 本批次最终结论

第十三份完成后，StructAI 已经不再只是：

```text
MCP + API Adapter
```

而已经形成：

```text
Engineering Execution Runtime
```

核心结构：

```text
Security
+
Execution
+
Task
+
Adapter
```

其中：

```text
Security
    → 谁可以执行

Execution
    → 什么可以执行

Task
    → 怎么可靠执行

Adapter
    → 怎么与具体工程软件执行
```

这四层必须保持独立。

最终：

```text
MIDAS
```

只是：

```text
Adapter #1
```

而不是 StructAI Core 本身。



# 完整收录：artifact

# StructAI MCP Server V2.0
## Core Alpha Artifact / Document / Event / Audit / Trace / Metrics / Health / Backup / Restore
### Source-Level Implementation Specification · Revision V2

> 文档编号：⑭  
> 目标：在 Core Alpha 已完成 Adapter Manager、Mock Adapter、Plugin Loader、Task Engine、Security、Execution Pipeline 基础上，补齐工程运行时的产物、文档、事件、审计、追踪、指标、健康检查、备份恢复与数据保留能力。  
> 原则：核心层与具体工程软件解耦；本阶段不得写入 MIDAS 专用逻辑。

---

# 1. 本阶段目标

本阶段完成以下核心能力：

```text
Artifact Storage
Document Service
Event Bus
Audit Service
Trace Service
Metrics
Health
Backup
Restore
Retention
```

最终运行链：

```text
MCP Request
 ↓
Execution Pipeline
 ↓
Task Engine
 ↓
Adapter
 ↓
Result
 ↓
Artifact / Document
 ↓
Event
 ↓
Audit
 ↓
Trace
 ↓
Metrics
 ↓
Health
```

---

# 2. 本阶段实现边界

## 2.1 必须实现

```text
P57 Artifact Storage
P58 Document Service
P59 Event Bus
P60 Audit Service
P61 Trace Service
P62 Metrics
P63 Health
P64 Backup
P65 Restore
P66 Retention
```

## 2.2 本阶段不实现

```text
[ ] UI
[ ] AI Agent
[ ] MIDAS 专用逻辑
[ ] CSI 专用逻辑
[ ] 云对象存储
[ ] Redis
[ ] Kafka
[ ] NATS
[ ] Elasticsearch
[ ] 分布式 Trace Collector
```

这些能力通过 Protocol / Adapter 预留。

---

# 3. P57 Artifact Storage

## 3.1 设计目标

Artifact 用于保存任务和工程软件产生的文件型结果：

```text
模型文件
分析结果
计算书
PDF
CSV
JSON
截图
导出文件
中间结果
日志附件
```

数据库只保存元数据，不把大文件直接塞入 SQLite。

---

## 3.2 Artifact ORM

```python
class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(index=True)

    name: Mapped[str] = mapped_column(String(255))
    storage_backend: Mapped[str] = mapped_column(String(32))
    storage_key: Mapped[str] = mapped_column(String(1024), unique=True)

    mime_type: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(BigInteger)
    checksum: Mapped[str] = mapped_column(String(128))

    project_id: Mapped[UUID | None] = mapped_column(index=True)
    task_id: Mapped[UUID | None] = mapped_column(index=True)
    document_id: Mapped[UUID | None] = mapped_column(index=True)

    created_at: Mapped[datetime]
    created_by: Mapped[UUID]
```

---

## 3.3 Storage Protocol

```python
from typing import Protocol, BinaryIO

class ArtifactStorage(Protocol):

    async def put(
        self,
        storage_key: str,
        stream: BinaryIO,
    ) -> None:
        ...

    async def get(
        self,
        storage_key: str,
    ) -> BinaryIO:
        ...

    async def delete(
        self,
        storage_key: str,
    ) -> None:
        ...

    async def exists(
        self,
        storage_key: str,
    ) -> bool:
        ...
```

---

## 3.4 LocalFilesystemStorage

Core Alpha 第一实现：

```text
./data/artifacts/
```

目录：

```text
data/
└── artifacts/
    └── <tenant_id>/
        └── <project_id>/
            └── <artifact_id>/
                └── payload
```

禁止直接使用用户提供的文件名作为最终路径。

---

## 3.5 Storage Key

推荐：

```text
{tenant_id}/{project_id}/{artifact_id}/payload
```

例如：

```text
tenant-001/
project-001/
artifact-001/
payload
```

---

## 3.6 Checksum

上传时计算 SHA-256：

```python
import hashlib

def sha256_stream(stream) -> str:
    digest = hashlib.sha256()

    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)

    return digest.hexdigest()
```

完整性验证：

```python
async def verify_artifact(
    artifact: Artifact,
    storage: ArtifactStorage,
) -> bool:
    stream = await storage.get(artifact.storage_key)
    actual = sha256_stream(stream)
    return actual == artifact.checksum
```

---

# 4. P58 Document Service

Document 是工程模型文件/工程文档的逻辑实体。

Artifact 是文件存储对象。

二者必须分离：

```text
Document
  ↓
DocumentVersion
  ↓
Artifact
```

---

## 4.1 Document ORM

```python
class Document(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(index=True)
    project_id: Mapped[UUID | None] = mapped_column(index=True)

    name: Mapped[str] = mapped_column(String(255))
    document_type: Mapped[str] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(String(32))
    current_version: Mapped[int] = mapped_column(default=1)

    created_by: Mapped[UUID]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

---

## 4.2 DocumentVersion

```python
class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[UUID] = mapped_column(primary_key=True)

    document_id: Mapped[UUID] = mapped_column(index=True)
    version: Mapped[int]

    artifact_id: Mapped[UUID]
    checksum: Mapped[str]

    created_by: Mapped[UUID]
    created_at: Mapped[datetime]
```

唯一约束：

```text
(document_id, version)
```

---

## 4.3 Document Lifecycle

冻结生命周期：

```text
NEW
 ↓
OPEN
 ↓
SAVE
 ↓
SAVE_AS
 ↓
CLOSE
```

INFO 不改变生命周期。

---

## 4.4 DocumentService

```python
class DocumentService:

    async def new(
        self,
        ctx: ExecutionContext,
        name: str,
        document_type: str,
    ) -> Document:
        ...

    async def open(
        self,
        ctx: ExecutionContext,
        document_id: UUID,
    ) -> Document:
        ...

    async def save(
        self,
        ctx: ExecutionContext,
        document_id: UUID,
        content,
    ) -> DocumentVersion:
        ...

    async def save_as(
        self,
        ctx: ExecutionContext,
        document_id: UUID,
        new_name: str,
    ) -> Document:
        ...

    async def close(
        self,
        ctx: ExecutionContext,
        document_id: UUID,
    ) -> None:
        ...

    async def info(
        self,
        ctx: ExecutionContext,
        document_id: UUID,
    ) -> dict:
        ...
```

---

# 5. P59 Event Bus

## 5.1 Event

```python
@dataclass(frozen=True)
class DomainEvent:
    event_id: UUID
    event_type: str

    tenant_id: UUID | None
    project_id: UUID | None

    request_id: str | None
    trace_id: str | None
    task_id: UUID | None

    occurred_at: datetime

    payload: dict
```

---

## 5.2 Core Alpha Event Bus

第一阶段只使用进程内 Event Bus：

```python
class EventBus(Protocol):

    async def publish(
        self,
        event: DomainEvent,
    ) -> None:
        ...

    async def subscribe(
        self,
        event_type: str,
        handler,
    ) -> None:
        ...
```

实现：

```python
class InProcessEventBus:
    def __init__(self):
        self._handlers: dict[str, list] = {}

    async def subscribe(self, event_type, handler):
        self._handlers.setdefault(event_type, []).append(handler)

    async def publish(self, event):
        handlers = self._handlers.get(event.event_type, [])

        for handler in handlers:
            await handler(event)
```

---

## 5.3 标准事件

```text
TaskCreated
TaskStarted
TaskProgress
TaskCompleted
TaskFailed
TaskCancelled

AdapterConnected
AdapterDisconnected

ModelChanged

DocumentCreated
DocumentOpened
DocumentSaved
DocumentClosed

ArtifactCreated
ArtifactDeleted

AnalysisStarted
AnalysisCompleted

DesignStarted
DesignCompleted
```

---

## 5.4 Event 与事务

禁止：

```text
DB COMMIT
 ↓
publish
```

导致 DB 成功、Event 丢失。

Core Alpha 推荐：

```text
事务
 ↓
写业务数据
 ↓
写 Outbox/Event Record
 ↓
COMMIT
 ↓
Event Dispatcher
 ↓
publish
```

如果本阶段暂不实现完整 Outbox，则必须在代码层明确其为 Alpha 限制，并保留迁移接口。

---

# 6. Event Record / Outbox

建议直接建立事件持久化表。

```python
class EventRecord(Base):
    __tablename__ = "event_records"

    id: Mapped[UUID] = mapped_column(primary_key=True)

    event_type: Mapped[str] = mapped_column(index=True)

    tenant_id: Mapped[UUID | None] = mapped_column(index=True)
    project_id: Mapped[UUID | None] = mapped_column(index=True)

    request_id: Mapped[str | None]
    trace_id: Mapped[str | None]
    task_id: Mapped[UUID | None]

    payload_json: Mapped[str]

    status: Mapped[str] = mapped_column(default="PENDING")
    attempts: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime]
    published_at: Mapped[datetime | None]
```

状态：

```text
PENDING
PUBLISHED
FAILED
```

---

# 7. P60 Audit Service

Audit 与普通 Log 不同。

```text
Log
= 调试/运行信息

Trace
= 请求执行链

Audit
= 谁在什么时候对什么资源做了什么操作
```

---

## 7.1 AuditRecord

```python
class AuditRecord(Base):
    __tablename__ = "audit_records"

    id: Mapped[UUID] = mapped_column(primary_key=True)

    tenant_id: Mapped[UUID | None] = mapped_column(index=True)
    user_id: Mapped[UUID | None] = mapped_column(index=True)

    action: Mapped[str] = mapped_column(index=True)
    resource_type: Mapped[str]
    resource_id: Mapped[str | None]

    result: Mapped[str]

    request_id: Mapped[str | None]
    trace_id: Mapped[str | None]
    task_id: Mapped[UUID | None]

    metadata_json: Mapped[str]

    previous_hash: Mapped[str | None]
    entry_hash: Mapped[str]

    created_at: Mapped[datetime]
```

---

# 8. Audit Hash Chain

目标：

```text
Audit N
 ↓
Audit N+1
```

其中：

```text
entry_hash =
SHA256(
    previous_hash
    + canonical_payload
)
```

---

## 8.1 Canonical JSON

```python
import json

def canonical_json(value: dict) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
```

---

## 8.2 Hash

```python
import hashlib

def compute_entry_hash(
    previous_hash: str | None,
    payload: dict,
) -> str:

    raw = (
        (previous_hash or "")
        + canonical_json(payload)
    ).encode("utf-8")

    return hashlib.sha256(raw).hexdigest()
```

---

## 8.3 Audit Service

```python
class AuditService:

    async def record(
        self,
        ctx: ExecutionContext,
        action: str,
        resource_type: str,
        resource_id: str | None,
        result: str,
        metadata: dict | None = None,
    ) -> AuditRecord:
        ...
```

Audit 必须记录：

```text
LOGIN
LOGOUT

DOCUMENT.NEW
DOCUMENT.OPEN
DOCUMENT.SAVE
DOCUMENT.CLOSE

MODEL.CREATE
MODEL.UPDATE
MODEL.DELETE

ANALYSIS.RUN
DESIGN.RUN

TASK.CANCEL

ADAPTER.CONNECT
ADAPTER.DISCONNECT

PERMISSION.DENIED
CONFIRMATION.REQUIRED
```

---

# 9. Audit 安全规则

禁止写入：

```text
password
API key
access token
refresh token
private key
secret
credential
```

允许记录：

```text
secret_reference
credential_id
authentication_method
```

例如：

```json
{
  "authentication_method": "api_key",
  "credential_reference": "midas-prod-key"
}
```

而不是：

```json
{
  "api_key": "actual-secret"
}
```

---

# 10. P61 Trace Service

Trace 必须与具体 tracing vendor 解耦。

```python
class TraceService(Protocol):

    async def start_span(
        self,
        name: str,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
        attributes: dict | None = None,
    ):
        ...

    async def end_span(
        self,
        span,
        status: str = "OK",
    ) -> None:
        ...
```

---

# 11. Trace Span

```python
class TraceSpan(Base):
    __tablename__ = "trace_spans"

    id: Mapped[UUID] = mapped_column(primary_key=True)

    trace_id: Mapped[str] = mapped_column(index=True)
    parent_span_id: Mapped[str | None] = mapped_column(index=True)

    name: Mapped[str]
    kind: Mapped[str]

    start_time: Mapped[datetime]
    end_time: Mapped[datetime | None]

    status: Mapped[str]

    request_id: Mapped[str | None]
    task_id: Mapped[UUID | None]

    attributes_json: Mapped[str]
```

---

# 12. Standard Trace Tree

一个典型分析请求：

```text
MCP
└── Tool
    └── Operation
        ├── SchemaValidation
        ├── EngineeringValidation
        ├── Permission
        ├── Capability
        ├── Lock
        └── Task
            └── Adapter
                └── NativeAPI
        └── Result
        └── Audit
```

Trace 必须能够定位：

```text
哪个请求
哪个用户
哪个任务
哪个软件
哪个 Adapter
哪个 operation
哪个 native API
耗时多少
在哪一步失败
```

---

# 13. P62 Metrics

Core Alpha 采用 Prometheus 风格指标抽象。

```python
class MetricsService(Protocol):

    def counter(
        self,
        name: str,
        value: float = 1,
        labels: dict | None = None,
    ) -> None:
        ...

    def gauge(
        self,
        name: str,
        value: float,
        labels: dict | None = None,
    ) -> None:
        ...

    def observe(
        self,
        name: str,
        value: float,
        labels: dict | None = None,
    ) -> None:
        ...
```

---

# 14. 标准 Metrics

```text
structai_requests_total
structai_request_duration_seconds

structai_task_total
structai_task_duration_seconds
structai_task_failed_total
structai_active_tasks

structai_adapter_requests_total
structai_adapter_errors_total
structai_adapter_duration_seconds

structai_mcp_connections

structai_artifacts_total
structai_artifact_bytes_total

structai_events_total
structai_event_publish_failed_total

structai_audit_total
```

---

# 15. Metrics 标签规则

允许：

```text
tool
operation
software
product
adapter
status
```

谨慎使用：

```text
tenant_id
user_id
project_id
request_id
task_id
```

这些高基数 ID 不应直接作为 Prometheus label。

---

# 16. P63 Health

提供：

```text
/livez
/readyz
/health
```

---

## 16.1 /livez

只回答：

```text
进程是否存活
```

不检查：

```text
DB
Adapter
Task Engine
```

---

## 16.2 /readyz

检查：

```text
Database
Registry
Task Engine
Event Dispatcher
```

返回：

```json
{
  "status": "READY"
}
```

---

## 16.3 /health

返回完整状态：

```json
{
  "status": "DEGRADED",
  "database": {
    "status": "UP"
  },
  "task_engine": {
    "status": "UP",
    "active_tasks": 2
  },
  "adapters": {
    "midas_civil_01": {
      "status": "UP"
    },
    "etabs_01": {
      "status": "DOWN"
    }
  }
}
```

单个软件不可用：

```text
Adapter DOWN
≠
Core DOWN
```

---

# 17. Health Service

```python
class HealthService:

    async def liveness(self) -> dict:
        ...

    async def readiness(self) -> dict:
        ...

    async def health(self) -> dict:
        ...
```

检查器：

```python
class HealthChecker(Protocol):

    async def check(self) -> dict:
        ...
```

注册：

```python
health_registry.register(
    "database",
    database_health_checker,
)

health_registry.register(
    "task_engine",
    task_engine_health_checker,
)

health_registry.register(
    "adapter_manager",
    adapter_health_checker,
)
```

---

# 18. P64 Backup

Core Alpha 使用 SQLite 原生 backup 能力。

备份对象：

```text
SQLite DB
Artifact metadata
Registry
Configuration
```

Artifact payload 另行复制。

---

# 19. Backup Manifest

```json
{
  "backup_id": "backup-001",
  "created_at": "2026-10-05T00:00:00Z",
  "database": {
    "file": "structai.db",
    "checksum": "..."
  },
  "artifacts": {
    "count": 123,
    "bytes": 987654321
  },
  "version": "2.0",
  "schema_revision": "..."
}
```

---

# 20. Backup Service

```python
class BackupService:

    async def create_backup(
        self,
        destination,
    ) -> dict:
        ...

    async def verify_backup(
        self,
        backup_path,
    ) -> dict:
        ...
```

备份目录：

```text
backup/
└── 20261005T010000/
    ├── manifest.json
    ├── structai.db
    └── artifacts/
```

---

# 21. SQLite Backup

不得简单执行：

```text
cp structai.db backup.db
```

在数据库运行期间可能得到不一致快照。

应使用 SQLite backup API：

```python
import sqlite3

def backup_database(
    source_path: str,
    destination_path: str,
) -> None:

    source = sqlite3.connect(source_path)
    destination = sqlite3.connect(destination_path)

    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
```

---

# 22. Artifact Backup

每个 Artifact：

```text
读取
 ↓
SHA-256
 ↓
复制
 ↓
再次 SHA-256
 ↓
比较
```

失败：

```text
ARTIFACT_BACKUP_FAILED
```

整个备份不能被标记为完整成功。

---

# 23. P65 Restore

恢复不是简单覆盖。

流程：

```text
Validate Backup
 ↓
Verify Manifest
 ↓
Verify DB checksum
 ↓
Verify Artifact checksum
 ↓
Check Schema Version
 ↓
Maintenance Mode
 ↓
Restore Database
 ↓
Restore Artifacts
 ↓
Integrity Check
 ↓
Registry Validation
 ↓
Exit Maintenance Mode
```

---

# 24. Restore Safety

恢复前必须：

```text
创建当前状态紧急备份
```

例如：

```text
restore/
├── pre_restore_backup/
└── target_backup/
```

禁止：

```text
直接覆盖
无校验恢复
部分恢复后直接启动
```

---

# 25. Restore Service

```python
class RestoreService:

    async def validate(
        self,
        backup_path,
    ) -> dict:
        ...

    async def restore(
        self,
        backup_path,
    ) -> dict:
        ...

    async def integrity_check(self) -> dict:
        ...
```

---

# 26. Integrity Check

数据库：

```sql
PRAGMA integrity_check;
```

Artifact：

```text
checksum == actual_checksum
```

Registry：

```text
software
product
version
adapter
capability
API mapping
```

全部必须能够解析。

---

# 27. P66 Retention

Core Alpha 支持数据保留策略：

```python
@dataclass(frozen=True)
class RetentionPolicy:
    task_days: int
    trace_days: int
    audit_days: int
    artifact_days: int
    event_days: int
    session_days: int
```

---

# 28. 默认策略

示例：

```text
Task       30 days
Trace      14 days
Event      30 days
Artifact   90 days
Session    7 days
Audit      365 days
```

Audit 默认必须明显长于普通 Trace。

---

# 29. Retention Job

```python
class RetentionService:

    async def cleanup_tasks(self) -> int:
        ...

    async def cleanup_traces(self) -> int:
        ...

    async def cleanup_events(self) -> int:
        ...

    async def cleanup_artifacts(self) -> int:
        ...

    async def cleanup_sessions(self) -> int:
        ...
```

Audit 不允许普通 retention job 直接删除。

必须通过：

```text
Audit Retention Policy
+
Administrator Authorization
+
Audit of Deletion
```

---

# 30. Artifact 删除顺序

必须：

```text
DB Artifact
 ↓
Storage Payload
```

但为了避免孤儿文件，更推荐：

```text
Mark DELETE_PENDING
 ↓
Delete Storage
 ↓
Verify
 ↓
Delete DB
```

如果 Storage 删除失败：

```text
DELETE_FAILED
```

等待下一轮恢复。

---

# 31. Artifact Garbage Collection

处理：

```text
数据库不存在
但 storage 存在
```

的孤儿文件。

流程：

```text
scan storage
 ↓
extract artifact_id
 ↓
query DB
 ↓
not found
 ↓
quarantine
 ↓
retention period
 ↓
delete
```

禁止扫描后立即删除。

---

# 32. Document / Artifact / Task 关系

```text
Project
 ├── Document
 │    └── DocumentVersion
 │         └── Artifact
 │
 └── Task
      ├── Artifact
      └── Result
```

一个 Task 可以产生多个 Artifact。

一个 Document 可以有多个 Version。

---

# 33. Task Engine 集成

Task 完成：

```python
result = await adapter.execute(...)

artifact = await artifact_service.create_from_result(
    ctx,
    result,
)

await event_bus.publish(
    TaskCompleted(...)
)
```

如果产生文件：

```text
Task
 ↓
Artifact
 ↓
Event
 ↓
Audit
 ↓
Trace
```

---

# 34. Execution Pipeline 集成

成功：

```text
Operation
 ↓
Task
 ↓
Adapter
 ↓
ResultNormalizer
 ↓
ArtifactService
 ↓
AuditService
 ↓
EventBus
 ↓
Metrics
```

失败：

```text
Exception
 ↓
NormalizeError
 ↓
Task FAILED
 ↓
Audit
 ↓
Trace ERROR
 ↓
Metric failed++
 ↓
Event TaskFailed
```

---

# 35. Transaction Boundary

数据库修改必须明确事务边界：

```python
async with unit_of_work:
    await repository.save(...)
    await event_outbox.append(...)
    await audit_service.record(...)
    await unit_of_work.commit()
```

不能：

```text
业务成功
 ↓
DB commit
 ↓
Audit 失败
```

然后导致操作无法追溯。

---

# 36. Repository

至少实现：

```text
ArtifactRepository
DocumentRepository
DocumentVersionRepository
EventRepository
AuditRepository
TraceRepository
```

每个 Repository 只负责数据访问。

禁止：

```text
Repository → Adapter
Repository → MCP
Repository → TaskEngine
```

---

# 37. Service 依赖规则

```text
MCP
 ↓
Application Service
 ↓
Repository / Domain Service
 ↓
Infrastructure
```

禁止：

```text
ORM Model
 ↓
MCP Tool
```

禁止：

```text
Adapter
 ↓
MCP Server
```

---

# 38. 目录新增

在现有目录基础上：

```text
app/
├── application/
│   ├── artifact/
│   │   └── service.py
│   ├── document/
│   │   └── service.py
│   ├── audit/
│   │   └── service.py
│   ├── trace/
│   │   └── service.py
│   ├── health/
│   │   └── service.py
│   └── retention/
│       └── service.py
│
├── infrastructure/
│   ├── storage/
│   │   ├── base.py
│   │   └── local.py
│   ├── events/
│   │   ├── bus.py
│   │   └── outbox.py
│   ├── backup/
│   │   ├── backup.py
│   │   └── restore.py
│   └── metrics/
│       └── prometheus.py
│
└── observability/
    ├── audit.py
    ├── tracing.py
    ├── metrics.py
    └── health.py
```

---

# 39. 数据库新增表

```text
artifacts
documents
document_versions
event_records
audit_records
trace_spans
```

可选：

```text
retention_jobs
backup_records
```

Core Alpha 可以先不持久化 BackupRecord。

---

# 40. Artifact API 内部契约

```python
@dataclass(frozen=True)
class ArtifactCreateRequest:
    name: str
    mime_type: str
    project_id: UUID | None
    task_id: UUID | None
    document_id: UUID | None
```

返回：

```python
@dataclass(frozen=True)
class ArtifactInfo:
    artifact_id: UUID
    name: str
    mime_type: str
    size: int
    checksum: str
    storage_backend: str
```

---

# 41. Document API 内部契约

```python
@dataclass(frozen=True)
class DocumentInfo:
    document_id: UUID
    name: str
    document_type: str
    status: str
    current_version: int
```

---

# 42. Event Dispatcher

```python
class EventDispatcher:

    async def run(self):
        while True:
            events = await self.repository.pending(limit=100)

            for event in events:
                try:
                    await self.bus.publish(
                        self.to_domain_event(event)
                    )

                    await self.repository.mark_published(
                        event.id
                    )

                except Exception:
                    await self.repository.mark_failed(
                        event.id
                    )
```

必须支持：

```text
attempts++
retry
backoff
dead-letter
```

Core Alpha 可以先使用简单 exponential backoff。

---

# 43. Audit 查询

普通用户只能查询自己有权限访问的租户/项目数据。

管理员可以：

```text
按用户
按 action
按 resource
按时间
按 request_id
按 trace_id
按 task_id
```

---

# 44. Trace 查询

Trace 查询至少支持：

```text
trace_id
request_id
task_id
时间范围
status
```

Trace 数据不允许修改。

---

# 45. Metrics Endpoint

建议：

```text
GET /metrics
```

但 Metrics 暴露必须由 HTTP 管理层控制。

不要将：

```text
/metrics
```

暴露到不可信公网。

---

# 46. Health Security

```text
/livez
```

可以公开。

```text
/readyz
```

只返回有限状态。

```text
/health
```

可能包含：

```text
software
adapter
database
```

因此默认应需要管理权限或仅绑定本地管理接口。

---

# 47. Backup Security

备份包含：

```text
工程数据
模型
任务
配置
```

因此必须视为敏感数据。

备份目录权限：

```text
仅 StructAI 服务账户
```

备份日志不得输出：

```text
artifact payload
数据库内容
credential
token
```

---

# 48. Recovery Test

必须测试：

```text
Task RUNNING 时 Core 崩溃
Task QUEUED 时 Core 崩溃
Artifact 写入中断
Event 发布失败
Audit 写入失败
DB backup
DB restore
Artifact checksum mismatch
DB integrity failure
Adapter DOWN
```

---

# 49. Artifact Test Matrix

```text
[ ] create
[ ] get
[ ] delete
[ ] exists
[ ] checksum
[ ] duplicate
[ ] missing payload
[ ] corrupted payload
[ ] orphan payload
[ ] tenant isolation
```

---

# 50. Document Test Matrix

```text
[ ] NEW
[ ] OPEN
[ ] SAVE
[ ] SAVE_AS
[ ] CLOSE
[ ] INFO
[ ] version increment
[ ] concurrent save conflict
[ ] artifact association
```

---

# 51. Event Test Matrix

```text
[ ] publish
[ ] subscribe
[ ] multiple subscribers
[ ] handler failure
[ ] retry
[ ] event persistence
[ ] duplicate delivery
```

---

# 52. Audit Test Matrix

```text
[ ] hash chain
[ ] previous_hash
[ ] entry_hash
[ ] canonical JSON
[ ] secret redaction
[ ] permission denied audit
[ ] task audit
[ ] model audit
[ ] immutable behavior
```

---

# 53. Trace Test Matrix

```text
[ ] root span
[ ] child span
[ ] parent relation
[ ] error status
[ ] task relation
[ ] adapter relation
[ ] trace query
```

---

# 54. Health Test Matrix

```text
[ ] live
[ ] ready
[ ] DB down
[ ] TaskEngine down
[ ] Adapter down
[ ] multiple adapters
[ ] degraded state
```

---

# 55. Backup / Restore Test Matrix

```text
[ ] backup DB
[ ] backup artifact
[ ] checksum
[ ] manifest
[ ] restore
[ ] integrity_check
[ ] corrupt backup
[ ] corrupt artifact
[ ] schema mismatch
[ ] pre-restore backup
```

---

# 56. Security Acceptance

必须满足：

```text
[ ] tenant isolation
[ ] user authorization
[ ] no secret logging
[ ] audit integrity
[ ] backup protection
[ ] artifact path traversal protection
[ ] artifact filename sanitization
[ ] restore authorization
[ ] health information restriction
[ ] metrics exposure restriction
```

---

# 57. Source-Level Dependency Graph

```text
ArtifactService
 ├── ArtifactRepository
 └── ArtifactStorage

DocumentService
 ├── DocumentRepository
 ├── DocumentVersionRepository
 └── ArtifactService

EventBus
 ├── EventRepository
 └── EventDispatcher

AuditService
 └── AuditRepository

TraceService
 └── TraceRepository

MetricsService
 └── MetricsBackend

HealthService
 └── HealthChecker[]

BackupService
 ├── Database
 └── ArtifactStorage

RestoreService
 ├── BackupService
 ├── Database
 └── ArtifactStorage

RetentionService
 ├── TaskRepository
 ├── TraceRepository
 ├── EventRepository
 ├── ArtifactRepository
 └── ArtifactStorage
```

---

# 58. Core Alpha 集成顺序

```text
1. ArtifactStorage
2. ArtifactRepository
3. ArtifactService

4. DocumentRepository
5. DocumentVersionRepository
6. DocumentService

7. EventRepository
8. InProcessEventBus
9. EventDispatcher

10. AuditRepository
11. AuditService

12. TraceRepository
13. TraceService

14. MetricsService
15. HealthService

16. BackupService
17. RestoreService

18. RetentionService
```

---

# 59. 最终运行闭环

```text
Generic MCP Client
       ↓
MCP Tool
       ↓
ExecutionService
       ↓
Validation
       ↓
Permission
       ↓
Capability
       ↓
TaskEngine
       ↓
AdapterManager
       ↓
Engineering Software
       ↓
Result
       ↓
Artifact / Document
       ↓
Event
       ↓
Audit
       ↓
Trace
       ↓
Metrics
```

---

# 60. 第十四份完成标准

```text
[ ] Artifact Storage
[ ] Local Filesystem Storage
[ ] SHA-256 Integrity
[ ] Artifact Repository
[ ] Document Service
[ ] Document Version
[ ] Event Bus
[ ] Event Persistence
[ ] Event Dispatcher
[ ] Audit Service
[ ] Audit Hash Chain
[ ] Secret Redaction
[ ] Trace Service
[ ] Trace Span
[ ] Metrics
[ ] Health
[ ] Liveness
[ ] Readiness
[ ] Backup
[ ] Restore
[ ] Integrity Check
[ ] Retention
[ ] Artifact GC
[ ] Recovery Tests
[ ] Security Tests
```

---

# 61. 与前十三份文档的关系

```text
① Database Revision
        ↓
② Core Development
        ↓
③ Core Implementation
        ↓
④ Python Implementation
        ↓
⑤ 9 MCP Tools
        ↓
⑥ File-Level Blueprint
        ↓
⑦ Core Alpha Source
        ↓
⑧ MIDAS Adapter Source
        ↓
⑨ Source Batch 01
        ↓
⑩ Security
        ↓
⑪ Execution Pipeline
        ↓
⑫ Task Engine
        ↓
⑬ Adapter Manager / Mock / Plugin
        ↓
⑭ Artifact / Document / Event /
   Audit / Trace / Metrics /
   Health / Backup / Restore
```

---

# 62. 下一阶段

下一份应进入：

## ⑮ Core Alpha — 9 MCP Tools Runtime Source-Level Implementation

重点完成：

```text
engineering_doc
engineering_model_query
engineering_model_assign
engineering_model_delete
engineering_model_build
engineering_view
engineering_result
engineering_design
engineering_analysis
```

并实现：

```text
Tool Registry
Tool Definition
Tool Request
Tool Response
Operation Resolver
Schema Resolver
Permission Resolver
Capability Resolver
Execution Dispatcher
Sync Execution
Async Execution
Task Mapping
Progress Mapping
Cancellation Mapping
Idempotency
Dry Run
Batch
Confirmation
Error Mapping
```

最终目标：

```text
Generic MCP Client
        ↓
9 MCP Tools
        ↓
Core Execution Pipeline
        ↓
Mock Adapter
        ↓
Task Engine
        ↓
Artifact / Audit / Trace / Event
```

当第十五份完成后，Core Alpha 的完整 MCP Runtime 才真正闭环。



# 完整收录：tools15

# StructAI MCP Server V2.0
## Core Alpha — 9 MCP Tools Runtime Source-Level Implementation
### Revision V2 · 第十五份

> 目标：把前十四份 Core 能力正式接入 MCP Runtime，完成从 Generic MCP Client → 9 个软件无关 MCP Tool → Core Execution Pipeline → Task Engine → Adapter → Result/Artifact/Event/Audit/Trace 的完整闭环。
>
> 本文是源码级实现规格，不是 UI 设计文档，也不是某个工程软件的 API 手册。

---

# 1. 本阶段目标

本阶段正式实现冻结的 9 个 MCP Tool：

```text
engineering_doc
engineering_model_query
engineering_model_assign
engineering_model_delete
engineering_model_build
engineering_view
engineering_result
engineering_design
engineering_analysis
```

运行关系：

```text
Generic MCP Client
        ↓
MCP Protocol
        ↓
Tool Registry
        ↓
Tool Handler
        ↓
Tool Request
        ↓
Operation Resolver
        ↓
Schema Validation
        ↓
Engineering Validation
        ↓
Permission
        ↓
Confirmation
        ↓
Idempotency
        ↓
Resource Lock
        ↓
Capability
        ↓
ExecutionService
        ↓
TaskEngine
        ↓
AdapterManager
        ↓
Engineering Software
        ↓
Result Normalization
        ↓
Artifact / Event / Audit / Trace / Metrics
        ↓
MCP Response
```

---

# 2. 9 Tool 冻结定义

## 2.1 engineering_doc

```text
NEW
OPEN
SAVE
SAVE_AS
CLOSE
INFO
```

默认风险：

```text
MEDIUM
```

---

## 2.2 engineering_model_query

```text
MODEL.QUERY
MODEL.NODE.QUERY
MODEL.ELEMENT.QUERY
MODEL.MATERIAL.QUERY
MODEL.SECTION.QUERY
MODEL.BOUNDARY.QUERY
MODEL.LOAD.QUERY
MODEL.GROUP.QUERY
```

默认风险：

```text
LOW
```

---

## 2.3 engineering_model_assign

```text
MODEL.NODE.CREATE
MODEL.NODE.UPDATE
MODEL.ELEMENT.CREATE
MODEL.ELEMENT.UPDATE
MODEL.MATERIAL.ASSIGN
MODEL.SECTION.ASSIGN
MODEL.BOUNDARY.ASSIGN
MODEL.LOAD.ASSIGN
```

默认风险：

```text
MEDIUM
```

---

## 2.4 engineering_model_delete

```text
MODEL.NODE.DELETE
MODEL.ELEMENT.DELETE
MODEL.LOAD.DELETE
MODEL.BOUNDARY.DELETE
MODEL.GROUP.DELETE
MODEL.MATERIAL.DELETE
MODEL.SECTION.DELETE
```

默认风险：

```text
HIGH
```

---

## 2.5 engineering_model_build

```text
BUILD.NODE_GRID
BUILD.BEAM
BUILD.COLUMN
BUILD.FRAME
BUILD.TRUSS
BUILD.SLAB
BUILD.WALL
BUILD.FOUNDATION
BUILD.STEEL_FRAME

MODEL.COPY
MODEL.MOVE
MODEL.MIRROR
MODEL.PATTERN
MODEL.GENERATE_GRID
```

默认风险：

```text
HIGH
```

---

## 2.6 engineering_view

```text
VIEW.MODEL
VIEW.DEFORMED_MODEL
VIEW.REACTION
VIEW.DISPLACEMENT
VIEW.STRESS
VIEW.FORCE
VIEW.MODE_SHAPE
```

默认风险：

```text
LOW
```

---

## 2.7 engineering_result

```text
RESULT.NODE.DISPLACEMENT
RESULT.NODE.REACTION
RESULT.ELEMENT.FORCE
RESULT.ELEMENT.STRESS
RESULT.MODE.SHAPE
RESULT.ANALYSIS.SUMMARY
```

默认风险：

```text
LOW
```

---

## 2.8 engineering_design

```text
DESIGN.STEEL
DESIGN.CONCRETE
DESIGN.SRC
DESIGN.FOUNDATION
DESIGN.CODE_CHECK
DESIGN.OPTIMIZE
```

默认风险：

```text
HIGH
```

---

## 2.9 engineering_analysis

```text
ANALYSIS.STATIC
ANALYSIS.MODAL
ANALYSIS.SEISMIC
ANALYSIS.SPECTRUM
ANALYSIS.BUCKLING
ANALYSIS.TIME_HISTORY
ANALYSIS.NONLINEAR
```

默认风险：

```text
HIGH
```

---

# 3. Tool Runtime 核心原则

## 3.1 Tool 不直接访问 Adapter

错误：

```python
async def engineering_analysis(...):
    return await midas_adapter.run_static(...)
```

正确：

```text
MCP Tool
 ↓
ToolRuntime
 ↓
ExecutionService
 ↓
OperationDefinition
 ↓
AdapterManager
```

---

# 4. ToolDefinition

```python
from dataclasses import dataclass
from enum import Enum


class ExecutionMode(str, Enum):
    SYNC = "SYNC"
    ASYNC = "ASYNC"
    STREAM = "STREAM"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    operations: tuple[str, ...]
```

---

# 5. OperationDefinition

```python
@dataclass(frozen=True)
class OperationDefinition:
    name: str
    tool: str

    risk_level: RiskLevel
    execution_mode: ExecutionMode

    input_schema: str
    output_schema: str

    required_permissions: tuple[str, ...]
    required_capabilities: tuple[str, ...]

    transactional: bool
    rollback_supported: bool
    dry_run_supported: bool

    confirmation_required: bool
    recovery_policy: str

    preconditions: tuple[str, ...] = ()
    postconditions: tuple[str, ...] = ()
```

---

# 6. Tool Registry

```python
class ToolRegistry:

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        definition: ToolDefinition,
    ) -> None:
        if definition.name in self._tools:
            raise ValueError(
                f"Tool already registered: {definition.name}"
            )

        self._tools[definition.name] = definition

    def get(
        self,
        name: str,
    ) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(name)

    def list(self) -> list[ToolDefinition]:
        return list(self._tools.values())
```

---

# 7. Operation Registry

Tool Registry 与 Operation Registry 必须分离。

```python
class OperationRegistry:

    def __init__(self):
        self._operations: dict[str, OperationDefinition] = {}

    def register(
        self,
        operation: OperationDefinition,
    ) -> None:
        if operation.name in self._operations:
            raise ValueError(
                f"Operation already registered: {operation.name}"
            )

        self._operations[operation.name] = operation

    def get(
        self,
        name: str,
    ) -> OperationDefinition:
        try:
            return self._operations[name]
        except KeyError:
            raise OperationNotFoundError(name)
```

---

# 8. Tool Request

```python
from pydantic import BaseModel, Field


class ToolRequest(BaseModel):

    operation: str

    parameters: dict = Field(
        default_factory=dict
    )

    context: dict = Field(
        default_factory=dict
    )

    idempotency_key: str | None = None

    confirmation_token: str | None = None

    dry_run: bool = False

    batch: list[dict] | None = None
```

---

# 9. Tool Context

客户端只能提供资源上下文：

```json
{
  "software_instance_id": "uuid",
  "project_id": "uuid",
  "model_id": "uuid",
  "document_id": "uuid"
}
```

禁止客户端提供：

```text
user_id
tenant_id
roles
permissions
effective_permissions
```

这些必须由认证层产生。

---

# 10. ToolRuntime

```python
class ToolRuntime:

    def __init__(
        self,
        tool_registry,
        operation_registry,
        execution_service,
    ):
        self.tool_registry = tool_registry
        self.operation_registry = operation_registry
        self.execution_service = execution_service

    async def invoke(
        self,
        tool_name: str,
        request: ToolRequest,
        ctx: ExecutionContext,
    ):
        tool = self.tool_registry.get(tool_name)

        operation = self.operation_registry.get(
            request.operation
        )

        if operation.tool != tool.name:
            raise OperationToolMismatchError(
                operation.name,
                tool.name,
            )

        return await self.execution_service.execute(
            operation=operation,
            request=request,
            context=ctx,
        )
```

---

# 11. ExecutionService

这是 9 个 Tool 的真正统一入口。

```python
class ExecutionService:

    async def execute(
        self,
        operation: OperationDefinition,
        request: ToolRequest,
        context: ExecutionContext,
    ):
        ...
```

完整执行顺序：

```text
Resolve Operation
 ↓
Schema Validation
 ↓
Engineering Validation
 ↓
Resource Resolve
 ↓
Permission
 ↓
Quota
 ↓
Confirmation
 ↓
Idempotency
 ↓
Lock
 ↓
Capability
 ↓
Preconditions
 ↓
Dry Run / Task
 ↓
Adapter
 ↓
Postconditions
 ↓
Result Normalize
 ↓
Persist
 ↓
Audit
 ↓
Trace
 ↓
Event
 ↓
Metrics
 ↓
Response
```

---

# 12. ExecutionService 源码骨架

```python
class ExecutionService:

    async def execute(
        self,
        operation: OperationDefinition,
        request: ToolRequest,
        context: ExecutionContext,
    ):

        span = await self.trace.start_span(
            f"operation:{operation.name}",
            trace_id=context.trace_id,
            attributes={
                "operation": operation.name,
                "tool": operation.tool,
            },
        )

        try:

            await self.schema.validate(
                operation.input_schema,
                request.parameters,
            )

            await self.engineering_validator.validate(
                operation,
                request.parameters,
                context,
            )

            resource = await self.resource_resolver.resolve(
                operation,
                request.context,
                context,
            )

            await self.permission.check(
                operation.required_permissions,
                context,
                resource,
            )

            await self.quota.check(
                context,
                operation,
            )

            await self.confirmation.check(
                operation,
                request,
                context,
            )

            idem = await self.idempotency.check(
                context,
                request.idempotency_key,
            )

            if idem.is_completed:
                return idem.response

            lock = await self.lock_manager.acquire(
                resource,
                operation,
            )

            try:

                await self.capability.check(
                    operation.required_capabilities,
                    context,
                )

                await self.precondition.check(
                    operation,
                    resource,
                    context,
                )

                if request.dry_run:
                    return await self._dry_run(
                        operation,
                        request,
                        context,
                        resource,
                    )

                result = await self._dispatch(
                    operation,
                    request,
                    context,
                    resource,
                )

                await self.postcondition.check(
                    operation,
                    result,
                    resource,
                    context,
                )

                normalized = await self.result_normalizer.normalize(
                    operation,
                    result,
                )

                await self._persist_success(
                    operation,
                    normalized,
                    context,
                )

                return normalized

            finally:
                await self.lock_manager.release(lock)

        except Exception as exc:

            await self.audit.record_error(
                context,
                operation,
                exc,
            )

            raise

        finally:

            await self.trace.end_span(
                span,
            )
```

---

# 13. Dispatch 策略

```python
async def _dispatch(
    self,
    operation,
    request,
    context,
    resource,
):

    if operation.execution_mode == ExecutionMode.SYNC:
        return await self._execute_sync(
            operation,
            request,
            context,
            resource,
        )

    if operation.execution_mode == ExecutionMode.ASYNC:
        return await self._execute_async(
            operation,
            request,
            context,
            resource,
        )

    return await self._execute_stream(
        operation,
        request,
        context,
        resource,
    )
```

---

# 14. SYNC

适用于：

```text
MODEL.NODE.QUERY
MODEL.ELEMENT.QUERY
MODEL.MATERIAL.QUERY
MODEL.SECTION.QUERY
MODEL.BOUNDARY.QUERY
MODEL.LOAD.QUERY
MODEL.GROUP.QUERY

VIEW.*
RESULT.*
```

流程：

```text
MCP Request
 ↓
ExecutionService
 ↓
Adapter.execute
 ↓
Result
 ↓
Response
```

---

# 15. ASYNC

适用于：

```text
BUILD.*
MODEL.DELETE
ANALYSIS.*
DESIGN.*
```

流程：

```text
MCP Request
 ↓
ExecutionService
 ↓
TaskEngine.create
 ↓
QUEUED
 ↓
MCP Response
```

返回：

```json
{
  "success": true,
  "execution": {
    "mode": "ASYNC",
    "status": "QUEUED",
    "task_id": "task-001"
  }
}
```

---

# 16. STREAM

Core Alpha 可以保留接口：

```python
async def _execute_stream(...):
    ...
```

用于未来：

```text
实时进度
大型结果
流式日志
长时间分析
```

第一阶段可以映射为：

```text
STREAM → ASYNC + Progress
```

不能把 STREAM 当成普通同步响应。

---

# 17. 9 Tool 注册

```python
def register_core_tools(registry: ToolRegistry):

    registry.register(
        ToolDefinition(
            name="engineering_doc",
            description="Engineering document lifecycle operations",
            operations=(
                "NEW",
                "OPEN",
                "SAVE",
                "SAVE_AS",
                "CLOSE",
                "INFO",
            ),
        )
    )

    registry.register(
        ToolDefinition(
            name="engineering_model_query",
            description="Query canonical engineering model",
            operations=(
                "MODEL.QUERY",
                "MODEL.NODE.QUERY",
                "MODEL.ELEMENT.QUERY",
                "MODEL.MATERIAL.QUERY",
                "MODEL.SECTION.QUERY",
                "MODEL.BOUNDARY.QUERY",
                "MODEL.LOAD.QUERY",
                "MODEL.GROUP.QUERY",
            ),
        )
    )
```

其余 7 个按照同一机制注册。

---

# 18. 推荐完整注册表

```python
TOOL_OPERATION_MAP = {

    "engineering_doc": (
        "NEW",
        "OPEN",
        "SAVE",
        "SAVE_AS",
        "CLOSE",
        "INFO",
    ),

    "engineering_model_query": (
        "MODEL.QUERY",
        "MODEL.NODE.QUERY",
        "MODEL.ELEMENT.QUERY",
        "MODEL.MATERIAL.QUERY",
        "MODEL.SECTION.QUERY",
        "MODEL.BOUNDARY.QUERY",
        "MODEL.LOAD.QUERY",
        "MODEL.GROUP.QUERY",
    ),

    "engineering_model_assign": (
        "MODEL.NODE.CREATE",
        "MODEL.NODE.UPDATE",
        "MODEL.ELEMENT.CREATE",
        "MODEL.ELEMENT.UPDATE",
        "MODEL.MATERIAL.ASSIGN",
        "MODEL.SECTION.ASSIGN",
        "MODEL.BOUNDARY.ASSIGN",
        "MODEL.LOAD.ASSIGN",
    ),

    "engineering_model_delete": (
        "MODEL.NODE.DELETE",
        "MODEL.ELEMENT.DELETE",
        "MODEL.LOAD.DELETE",
        "MODEL.BOUNDARY.DELETE",
        "MODEL.GROUP.DELETE",
        "MODEL.MATERIAL.DELETE",
        "MODEL.SECTION.DELETE",
    ),

    "engineering_model_build": (
        "BUILD.NODE_GRID",
        "BUILD.BEAM",
        "BUILD.COLUMN",
        "BUILD.FRAME",
        "BUILD.TRUSS",
        "BUILD.SLAB",
        "BUILD.WALL",
        "BUILD.FOUNDATION",
        "BUILD.STEEL_FRAME",
        "MODEL.COPY",
        "MODEL.MOVE",
        "MODEL.MIRROR",
        "MODEL.PATTERN",
        "MODEL.GENERATE_GRID",
    ),

    "engineering_view": (
        "VIEW.MODEL",
        "VIEW.DEFORMED_MODEL",
        "VIEW.REACTION",
        "VIEW.DISPLACEMENT",
        "VIEW.STRESS",
        "VIEW.FORCE",
        "VIEW.MODE_SHAPE",
    ),

    "engineering_result": (
        "RESULT.NODE.DISPLACEMENT",
        "RESULT.NODE.REACTION",
        "RESULT.ELEMENT.FORCE",
        "RESULT.ELEMENT.STRESS",
        "RESULT.MODE.SHAPE",
        "RESULT.ANALYSIS.SUMMARY",
    ),

    "engineering_design": (
        "DESIGN.STEEL",
        "DESIGN.CONCRETE",
        "DESIGN.SRC",
        "DESIGN.FOUNDATION",
        "DESIGN.CODE_CHECK",
        "DESIGN.OPTIMIZE",
    ),

    "engineering_analysis": (
        "ANALYSIS.STATIC",
        "ANALYSIS.MODAL",
        "ANALYSIS.SEISMIC",
        "ANALYSIS.SPECTRUM",
        "ANALYSIS.BUCKLING",
        "ANALYSIS.TIME_HISTORY",
        "ANALYSIS.NONLINEAR",
    ),
}
```

---

# 19. Operation Definition Seed

Operation Registry 必须预置每个 operation 的：

```text
tool
risk
execution_mode
input_schema
output_schema
permissions
capabilities
transactional
rollback
dry_run
confirmation
recovery_policy
```

示例：

```python
OperationDefinition(
    name="MODEL.NODE.QUERY",
    tool="engineering_model_query",
    risk_level=RiskLevel.LOW,
    execution_mode=ExecutionMode.SYNC,
    input_schema="structai://schema/model/node/query/v1",
    output_schema="structai://schema/model/node/list/v1",
    required_permissions=("MODEL_READ",),
    required_capabilities=("MODEL.NODE.READ",),
    transactional=False,
    rollback_supported=False,
    dry_run_supported=False,
    confirmation_required=False,
    recovery_policy="NONE",
)
```

---

# 20. BUILD.COLUMN

```python
OperationDefinition(
    name="BUILD.COLUMN",
    tool="engineering_model_build",
    risk_level=RiskLevel.HIGH,
    execution_mode=ExecutionMode.ASYNC,
    input_schema="structai://schema/build/column/v1",
    output_schema="structai://schema/build/column/result/v1",
    required_permissions=("MODEL_WRITE",),
    required_capabilities=(
        "MODEL.NODE.WRITE",
        "MODEL.ELEMENT.WRITE",
        "MODEL.MATERIAL.WRITE",
        "MODEL.SECTION.WRITE",
    ),
    transactional=True,
    rollback_supported=False,
    dry_run_supported=True,
    confirmation_required=True,
    recovery_policy="STATE_RECONCILE",
)
```

注意：

```text
BUILD.COLUMN
```

不是某个软件的 API。

它是 StructAI 的工程语义操作。

---

# 21. ANALYSIS.STATIC

```python
OperationDefinition(
    name="ANALYSIS.STATIC",
    tool="engineering_analysis",
    risk_level=RiskLevel.HIGH,
    execution_mode=ExecutionMode.ASYNC,
    input_schema="structai://schema/analysis/static/v1",
    output_schema="structai://schema/analysis/static/result/v1",
    required_permissions=("ANALYSIS_EXECUTE",),
    required_capabilities=("ANALYSIS.STATIC",),
    transactional=False,
    rollback_supported=False,
    dry_run_supported=False,
    confirmation_required=True,
    recovery_policy="MANUAL_REVIEW",
)
```

---

# 22. DESIGN.STEEL

```python
OperationDefinition(
    name="DESIGN.STEEL",
    tool="engineering_design",
    risk_level=RiskLevel.HIGH,
    execution_mode=ExecutionMode.ASYNC,
    input_schema="structai://schema/design/steel/v1",
    output_schema="structai://schema/design/steel/result/v1",
    required_permissions=("DESIGN_EXECUTE",),
    required_capabilities=("DESIGN.STEEL",),
    transactional=False,
    rollback_supported=False,
    dry_run_supported=False,
    confirmation_required=True,
    recovery_policy="MANUAL_REVIEW",
)
```

---

# 23. Confirmation

高风险操作：

```text
MODEL.DELETE
BUILD.*
ANALYSIS.*
DESIGN.*
```

必须根据 OperationDefinition 判断。

Confirmation Token：

```text
server generated
short-lived
single-use
bound to:
    user
    tenant
    operation
    resource
    request
```

禁止：

```text
client 自己生成 token
```

---

# 24. Confirmation Service

```python
class ConfirmationService:

    async def create(
        self,
        context: ExecutionContext,
        operation: OperationDefinition,
        resource,
    ) -> str:
        ...

    async def verify(
        self,
        token: str,
        context: ExecutionContext,
        operation: OperationDefinition,
        resource,
    ) -> None:
        ...
```

如果没有确认：

```text
STRUCTAI-4100
```

---

# 25. Dry Run

例如：

```json
{
  "operation": "BUILD.COLUMN",
  "dry_run": true,
  "parameters": {
    "base": [0,0,0],
    "height": 6,
    "section": "H400x400x13x21",
    "material": "Q355B"
  }
}
```

返回：

```json
{
  "success": true,
  "execution": {
    "mode": "DRY_RUN",
    "status": "VALIDATED"
  },
  "data": {
    "planned_changes": [
      {
        "type": "CREATE_NODE",
        "id": 1
      },
      {
        "type": "CREATE_NODE",
        "id": 2
      },
      {
        "type": "CREATE_ELEMENT",
        "id": 1
      }
    ]
  }
}
```

绝不能修改实际模型。

---

# 26. Batch

支持：

```json
{
  "operation": "MODEL.NODE.CREATE",
  "batch": [
    {"id": 1, "x": 0, "y": 0, "z": 0},
    {"id": 2, "x": 0, "y": 0, "z": 6},
    {"id": 3, "x": 4, "y": 0, "z": 6}
  ]
}
```

必须明确：

```text
atomic
non_atomic
```

默认：

```text
MODEL.CREATE → atomic
QUERY → non_atomic
```

如果底层 Adapter 不支持事务：

```text
transactional=true
```

不能假装具有回滚能力。

---

# 27. Idempotency

Mutation Tool 必须支持：

```text
MODEL.NODE.CREATE
MODEL.ELEMENT.CREATE
BUILD.*
MODEL.MOVE
MODEL.COPY
MODEL.MIRROR
MODEL.PATTERN
MODEL.LOAD.ASSIGN
ANALYSIS.*
DESIGN.*
```

数据库唯一约束：

```text
tenant_id
+
idempotency_key
```

---

# 28. Idempotency Response

第一次：

```text
EXECUTE
```

第二次使用相同 key：

```text
RETURN PREVIOUS RESPONSE
```

禁止：

```text
再次创建节点
再次运行分析
再次执行设计
```

---

# 29. Pagination

查询 Tool 必须支持：

```json
{
  "limit": 100,
  "cursor": "..."
}
```

返回：

```json
{
  "data": [],
  "pagination": {
    "has_more": true,
    "next_cursor": "..."
  }
}
```

默认限制：

```text
limit <= 1000
```

具体上限由系统配置决定。

---

# 30. Query Filter

统一：

```json
{
  "filters": {
    "ids": [1,2,3],
    "group": "G1"
  },
  "limit": 100,
  "cursor": null
}
```

不要让每个软件 Adapter 自己发明分页协议。

---

# 31. Result Normalization

所有 Result 必须经过：

```python
class ResultNormalizer(Protocol):

    async def normalize(
        self,
        operation: OperationDefinition,
        result: dict,
    ) -> dict:
        ...
```

例如不同软件：

```text
MIDAS ux
ETABS U1
OpenSees DX
```

最终：

```json
{
  "node_id": 100,
  "ux": 0.001,
  "uy": 0.002,
  "uz": -0.015
}
```

---

# 32. Error Mapping

Tool Runtime 不直接暴露 Adapter 原始异常。

统一：

```python
class ErrorMapper:

    def map(self, exc: Exception) -> StructAIError:
        ...
```

例如：

```text
TimeoutError
 ↓
STRUCTAI-2300

CapabilityError
 ↓
STRUCTAI-3000

PermissionError
 ↓
STRUCTAI-4000

AdapterError
 ↓
STRUCTAI-6000
```

---

# 33. Unified MCP Response

```python
@dataclass
class MCPExecutionResponse:
    success: bool

    request_id: str
    trace_id: str

    tool: str
    operation: str

    execution: dict

    data: dict | list | None

    warnings: list[dict]
    errors: list[dict]

    metadata: dict
```

---

# 34. Sync Response

```json
{
  "success": true,
  "request_id": "req-001",
  "trace_id": "trace-001",
  "tool": "engineering_model_query",
  "operation": "MODEL.NODE.QUERY",
  "execution": {
    "mode": "SYNC",
    "status": "COMPLETED"
  },
  "data": [
    {
      "id": 1,
      "x": 0,
      "y": 0,
      "z": 0
    }
  ],
  "warnings": [],
  "errors": [],
  "metadata": {}
}
```

---

# 35. Async Response

```json
{
  "success": true,
  "request_id": "req-002",
  "trace_id": "trace-002",
  "tool": "engineering_analysis",
  "operation": "ANALYSIS.STATIC",
  "execution": {
    "mode": "ASYNC",
    "status": "QUEUED",
    "task_id": "task-002"
  },
  "data": null,
  "warnings": [],
  "errors": [],
  "metadata": {}
}
```

---

# 36. MCP Task Status

Core Runtime 必须提供任务查询机制。

任务状态：

```text
CREATED
VALIDATING
QUEUED
RUNNING
PROCESSING
COMPLETED
FAILED
CANCEL_REQUESTED
CANCELLED
TIMEOUT
RETRYING
RECOVERING
```

---

# 37. MCP Cancellation

```text
MCP Cancel
 ↓
ToolRuntime
 ↓
TaskEngine.cancel(task_id)
 ↓
Adapter.cancel(task_id)
```

如果 Adapter 不支持：

```text
cancel_requested = true
```

而不是伪造：

```text
CANCELLED
```

---

# 38. Progress

Task Engine：

```text
0
 ↓
20
 ↓
43
 ↓
75
 ↓
100
```

MCP Runtime 将进度映射为：

```text
task_id
progress
message
stage
```

例如：

```json
{
  "task_id": "task-001",
  "progress": 43,
  "stage": "ANALYSIS",
  "message": "Running static analysis"
}
```

---

# 39. MCP Tool Handler

Tool Handler 必须非常薄：

```python
async def handle_tool(
    tool_name: str,
    arguments: dict,
    session,
):

    identity = await authentication.resolve(session)

    context = await context_builder.build(
        identity=identity,
        arguments=arguments,
    )

    request = ToolRequest.model_validate(
        arguments
    )

    return await tool_runtime.invoke(
        tool_name,
        request,
        context,
    )
```

禁止在 Handler 中写：

```text
RBAC
Capability
Adapter
SQL
Task state
```

---

# 40. MCP Server

```python
class StructAIMCPServer:

    def __init__(
        self,
        tool_runtime,
    ):
        self.tool_runtime = tool_runtime

    async def invoke_tool(
        self,
        name: str,
        arguments: dict,
        session,
    ):
        return await handle_tool(
            name,
            arguments,
            session,
        )
```

---

# 41. Tool Discovery

MCP Client 应能够发现：

```text
engineering_doc
engineering_model_query
engineering_model_assign
engineering_model_delete
engineering_model_build
engineering_view
engineering_result
engineering_design
engineering_analysis
```

不要暴露：

```text
midas_api_post
midas_api_get
midas_raw_request
```

---

# 42. 为什么不暴露 Raw API Tool

如果把数百个软件 API 暴露给 LLM：

```text
Context Explosion
Tool Explosion
Prompt Pollution
API Version Coupling
Vendor Lock-in
```

StructAI 保持：

```text
9 Semantic Tools
+
Operation Registry
+
Capability Registry
+
API Registry
+
Adapter
```

---

# 43. AI 调用示例

用户：

> 创建一个高度 6m 的 Q355B H400×400×13×21 钢柱，底部固定，顶部施加 500kN 轴压力，进行静力分析并返回顶部节点位移和钢柱设计利用率。

AI 应形成：

```text
BUILD.COLUMN
 ↓
MODEL.BOUNDARY.ASSIGN
 ↓
MODEL.LOAD.ASSIGN
 ↓
ANALYSIS.STATIC
 ↓
RESULT.NODE.DISPLACEMENT
 ↓
DESIGN.STEEL
```

Tool Runtime 不要求 AI 了解 MIDAS API。

---

# 44. Mock E2E

Core Alpha 必须通过 Mock Adapter 完成：

```text
BUILD.COLUMN
 ↓
BOUNDARY
 ↓
LOAD
 ↓
ANALYSIS.STATIC
 ↓
RESULT.NODE.DISPLACEMENT
 ↓
DESIGN.STEEL
```

---

# 45. Mock E2E 示例

```python
result = await client.call_tool(
    "engineering_model_build",
    {
        "operation": "BUILD.COLUMN",
        "parameters": {
            "base": [0, 0, 0],
            "height": 6,
            "material": "Q355B",
            "section": "H400x400x13x21",
        },
        "confirmation_token": token,
        "idempotency_key": "column-demo-001",
    },
)
```

然后：

```python
await client.call_tool(
    "engineering_model_assign",
    {
        "operation": "MODEL.BOUNDARY.ASSIGN",
        ...
    },
)
```

然后：

```python
await client.call_tool(
    "engineering_analysis",
    {
        "operation": "ANALYSIS.STATIC",
        ...
    },
)
```

最终：

```python
await client.call_tool(
    "engineering_result",
    {
        "operation": "RESULT.NODE.DISPLACEMENT",
        ...
    },
)
```

---

# 46. Tool Contract Tests

每个 Tool 必须测试：

```text
[ ] discovery
[ ] valid operation
[ ] invalid operation
[ ] wrong tool-operation mapping
[ ] schema validation
[ ] permission
[ ] capability
[ ] confirmation
[ ] idempotency
[ ] dry-run
[ ] batch
[ ] sync
[ ] async
[ ] error mapping
```

---

# 47. 9 Tool 测试矩阵

| Tool | Query | Write | Delete | Async | Confirmation |
|---|---:|---:|---:|---:|---:|
| engineering_doc | ✓ | ✓ | - | ✓ | 部分 |
| engineering_model_query | ✓ | - | - | - | - |
| engineering_model_assign | - | ✓ | - | 部分 | 部分 |
| engineering_model_delete | - | - | ✓ | ✓ | ✓ |
| engineering_model_build | - | ✓ | - | ✓ | ✓ |
| engineering_view | ✓ | - | - | - | - |
| engineering_result | ✓ | - | - | - | - |
| engineering_design | - | ✓ | - | ✓ | ✓ |
| engineering_analysis | - | ✓ | - | ✓ | ✓ |

---

# 48. Tool Runtime 安全边界

Tool Runtime 必须确保：

```text
Client
 ≠
Identity

Client
 ≠
Permission

Client
 ≠
Capability

Client
 ≠
Confirmation Authority
```

---

# 49. Tenant Isolation

所有数据访问必须带：

```text
tenant_id
```

错误：

```python
await repository.get(document_id)
```

正确：

```python
await repository.get(
    tenant_id=context.identity.tenant_id,
    document_id=document_id,
)
```

禁止跨 Tenant 查询。

---

# 50. Resource Resolver

```python
class ResourceResolver:

    async def resolve(
        self,
        operation,
        request_context,
        identity_context,
    ):
        ...
```

解析：

```text
software_instance
project
model
document
```

同时验证：

```text
resource belongs to tenant
user can access resource
software instance is available
```

---

# 51. Capability Resolver

```python
class CapabilityResolver:

    async def check(
        self,
        required: tuple[str, ...],
        context: ExecutionContext,
    ) -> None:
        ...
```

必须同时考虑：

```text
Static Capability
Runtime Capability
Adapter Version
Software Instance
```

---

# 52. Tool Runtime 与 API Registry

Tool Runtime：

```text
operation
```

API Registry：

```text
operation
+
software
+
version
→
native API
```

例如：

```text
ANALYSIS.STATIC
        ↓
MIDAS 2026
        ↓
native endpoint

ANALYSIS.STATIC
        ↓
ETABS 22
        ↓
COM method

ANALYSIS.STATIC
        ↓
OpenSees
        ↓
script command
```

9 Tool 完全不变化。

---

# 53. Adapter Manager 集成

```python
adapter = await adapter_manager.get(
    context.software.instance_id
)

result = await adapter.execute(
    operation.name,
    request.parameters,
    context,
)
```

禁止：

```python
if software == "MIDAS":
    ...
elif software == "ETABS":
    ...
```

这种判断必须存在于 Adapter / Registry 层。

---

# 54. Result Persistence

Result 不一定全部写数据库。

策略：

```text
small result
 → DB

large result
 → Artifact

query result
 → paginated response

analysis report
 → Artifact
```

例如：

```text
RESULT.ANALYSIS.SUMMARY
 → DB / JSON

完整计算报告
 → PDF Artifact
```

---

# 55. Event Integration

成功：

```text
TaskCompleted
ModelChanged
ArtifactCreated
AnalysisCompleted
DesignCompleted
```

失败：

```text
TaskFailed
```

删除：

```text
ModelChanged
```

---

# 56. Audit Integration

每个 mutation：

```text
CREATE
UPDATE
DELETE
ASSIGN
BUILD
ANALYSIS
DESIGN
```

必须 Audit。

Query 默认可以只记录：

```text
high-value query
administrative query
```

避免产生巨量 Audit 数据。

---

# 57. Metrics Integration

Tool 调用：

```text
structai_requests_total++
```

失败：

```text
structai_task_failed_total++
```

Adapter：

```text
structai_adapter_requests_total++
structai_adapter_errors_total++
```

耗时：

```text
structai_request_duration_seconds
structai_task_duration_seconds
structai_adapter_duration_seconds
```

---

# 58. Trace Integration

至少：

```text
mcp.request
tool.invoke
operation.execute
schema.validate
permission.check
capability.check
task.execute
adapter.execute
result.normalize
artifact.create
audit.record
```

---

# 59. 完整调用链示例

```text
mcp.request
  |
  +-- tool.invoke
        |
        +-- operation.execute
              |
              +-- schema.validate
              |
              +-- engineering.validate
              |
              +-- permission.check
              |
              +-- confirmation.check
              |
              +-- capability.check
              |
              +-- task.execute
                    |
                    +-- adapter.execute
                          |
                          +-- native.api
              |
              +-- result.normalize
              |
              +-- artifact.create
              |
              +-- audit.record
              |
              +-- event.publish
```

---

# 60. MCP Transport

Core Runtime 必须与 Transport 解耦。

第一阶段：

```text
STDIO
```

第二阶段：

```text
Streamable HTTP
```

Tool Runtime 不允许判断：

```text
STDIO
HTTP
```

这些属于 Interface Layer。

---

# 61. STDIO

```python
async def run_stdio():
    server = build_server()
    await server.run_stdio()
```

STDIO 适用于：

```text
本地 AI Agent
本地 IDE
开发测试
```

---

# 62. Streamable HTTP

HTTP 层：

```text
Authentication
 ↓
Session
 ↓
MCP Protocol
 ↓
ToolRuntime
```

禁止：

```text
HTTP Route
 ↓
Adapter
```

---

# 63. Generic Client E2E

必须使用一个与 MIDAS 无关的 MCP Client。

测试：

```text
initialize
 ↓
tools/list
 ↓
engineering_model_build
 ↓
task status
 ↓
engineering_result
```

如果 Generic Client 能完成 Mock E2E：

```text
Core MCP Runtime = PASS
```

---

# 64. Core Alpha DoD

```text
[ ] 9 Tools registered
[ ] tools/list
[ ] Tool Registry
[ ] Operation Registry
[ ] ToolRequest
[ ] ToolRuntime
[ ] ExecutionService
[ ] Sync execution
[ ] Async execution
[ ] Progress
[ ] Cancellation
[ ] Schema validation
[ ] Engineering validation
[ ] RBAC
[ ] Capability
[ ] Confirmation
[ ] Idempotency
[ ] Resource Lock
[ ] Dry Run
[ ] Batch
[ ] Pagination
[ ] Result normalization
[ ] Error mapping
[ ] Task Engine integration
[ ] Adapter Manager integration
[ ] Artifact integration
[ ] Event integration
[ ] Audit integration
[ ] Trace integration
[ ] Metrics integration
[ ] STDIO
[ ] Streamable HTTP
[ ] Mock E2E
[ ] Contract tests
[ ] Security tests
```

---

# 65. 第十五份完成后的 Core Alpha 架构

```text
                         Generic AI Client
                                │
                                ▼
                         ┌──────────────┐
                         │ MCP Runtime  │
                         └──────┬───────┘
                                │
               ┌────────────────┼────────────────┐
               │                │                │
               ▼                ▼                ▼
       engineering_doc   model/query/write   analysis/design
               │                │                │
               └────────────────┼────────────────┘
                                ▼
                       Tool / Operation
                           Registry
                                │
                                ▼
                      Execution Pipeline
                                │
        ┌───────────────┬──────┼───────────────┐
        ▼               ▼      ▼               ▼
      Schema           RBAC  Capability       Lock
        │               │      │               │
        └───────────────┴──────┴───────────────┘
                                │
                                ▼
                           Task Engine
                                │
                                ▼
                         Adapter Manager
                                │
                  ┌─────────────┼─────────────┐
                  ▼             ▼             ▼
                MIDAS         ETABS        OpenSees
                  │             │             │
                  └─────────────┼─────────────┘
                                ▼
                           Result Layer
                                │
          ┌─────────────┬───────┼────────┬──────────┐
          ▼             ▼       ▼        ▼          ▼
       Artifact       Event   Audit    Trace      Metrics
          │             │       │        │          │
          └─────────────┴───────┴────────┴──────────┘
                                │
                                ▼
                           MCP Response
```

---

# 66. 下一阶段

第十五份完成后，下一份进入：

## ⑯ Core Alpha — MCP Transport / Session / STDIO / Streamable HTTP Source-Level Implementation

重点：

```text
MCP Server Bootstrap
MCP Session
Authentication Context
STDIO Transport
Streamable HTTP
tools/list
tools/call
Cancellation
Progress Notification
Session Lifecycle
HTTP Security
Connection Limits
Request Limits
MCP Error Mapping
Generic MCP Client E2E
```

再下一阶段才进入：

```text
⑰ MIDAS Adapter Runtime
```

届时才把真正的 MIDAS API Registry、请求转换、响应转换、版本映射、Capability Mapping 接入 Core Alpha。




# 完整收录：trans16

# StructAI MCP Server V2.0
## Core Alpha — MCP Transport / Session / STDIO / Streamable HTTP
### Source-Level Implementation Specification · Revision V2 · 第十六份

> 目标：在第十五份 9 MCP Tools Runtime 基础上，完成 MCP Protocol 接入层、Session、STDIO、Streamable HTTP、认证上下文、进度通知、取消、连接生命周期、HTTP 安全与 Generic MCP Client E2E。
>
> 核心原则：Transport 只负责通信；Session 只负责协议会话；Tool Runtime 负责业务执行。不得让 Transport 层侵入 Core Execution Pipeline，也不得在 Transport 层加入 MIDAS/ETABS 等软件逻辑。

---

# 1. 本阶段目标

完成：

```text
MCP Server Bootstrap
MCP Session
Authentication Context
STDIO Transport
Streamable HTTP Transport
tools/list
tools/call
Progress Notification
Cancellation
Session Lifecycle
Connection Limits
Request Limits
MCP Error Mapping
Generic MCP Client E2E
```

最终链路：

```text
MCP Client
    ↓
Transport
    ↓
MCP Protocol Server
    ↓
Session
    ↓
Authentication
    ↓
Tool Runtime
    ↓
ExecutionService
    ↓
TaskEngine
    ↓
AdapterManager
```

---

# 2. Transport 分层

必须保持：

```text
Transport
   ↓
MCP Protocol
   ↓
Session
   ↓
Tool Runtime
   ↓
Core
```

禁止：

```text
HTTP Route
   ↓
MIDAS Adapter
```

禁止：

```text
STDIO Handler
   ↓
SQLAlchemy
```

禁止：

```text
Transport
   ↓
Operation-specific logic
```

---

# 3. Transport 抽象

```python
from typing import Protocol, AsyncIterator


class MCPTransport(Protocol):

    async def start(self) -> None:
        ...

    async def receive(self) -> AsyncIterator[bytes]:
        ...

    async def send(self, message: bytes) -> None:
        ...

    async def close(self) -> None:
        ...
```

Transport 不知道：

```text
tool
operation
adapter
software
database
```

---

# 4. MCP Server Bootstrap

```python
class MCPServerRuntime:

    def __init__(
        self,
        transport,
        protocol_server,
    ):
        self.transport = transport
        self.protocol_server = protocol_server

    async def start(self):

        await self.transport.start()

        await self.protocol_server.run(
            self.transport
        )

    async def stop(self):

        await self.protocol_server.shutdown()

        await self.transport.close()
```

---

# 5. Application Bootstrap

完整启动：

```text
main.py
 ↓
Settings
 ↓
Database
 ↓
Repositories
 ↓
Registry
 ↓
Security
 ↓
TaskEngine
 ↓
AdapterManager
 ↓
ArtifactService
 ↓
EventBus
 ↓
Audit
 ↓
Trace
 ↓
Metrics
 ↓
ToolRuntime
 ↓
MCP Server
 ↓
Transport
```

---

# 6. Application Container

建议建立：

```python
@dataclass
class AppContainer:

    settings: Settings

    db: Database

    tool_registry: ToolRegistry
    operation_registry: OperationRegistry

    security: SecurityContainer

    task_engine: TaskEngine
    adapter_manager: AdapterManager

    artifact_service: ArtifactService
    document_service: DocumentService

    event_bus: EventBus
    audit_service: AuditService
    trace_service: TraceService
    metrics_service: MetricsService
    health_service: HealthService

    tool_runtime: ToolRuntime
```

Application Container 负责依赖注入。

---

# 7. MCP Protocol 层

Protocol 层负责：

```text
initialize
notifications/initialized
tools/list
tools/call
ping
session lifecycle
progress
cancellation
```

Protocol 层不负责：

```text
RBAC
Capability
Task business logic
Adapter mapping
```

---

# 8. Initialize

客户端建立连接后首先：

```text
initialize
```

服务端返回：

```text
protocolVersion
capabilities
serverInfo
instructions
```

示例：

```json
{
  "protocolVersion": "supported-version",
  "capabilities": {
    "tools": {
      "listChanged": false
    }
  },
  "serverInfo": {
    "name": "StructAI MCP Server",
    "version": "2.0.0"
  }
}
```

> `protocolVersion` 必须由实际采用的 MCP SDK/协议版本配置决定，不在 Core 中硬编码一个未经确认的版本号。

---

# 9. Initialize Context

初始化完成后生成：

```python
@dataclass(frozen=True)
class MCPSessionContext:

    session_id: str

    protocol_version: str

    client_name: str
    client_version: str

    connected_at: datetime

    identity: IdentityContext | None = None
```

---

# 10. IdentityContext

Transport 不直接相信客户端传入的：

```text
user_id
tenant_id
roles
permissions
```

必须：

```text
Transport
 ↓
Authentication
 ↓
IdentityContext
```

例如：

```python
@dataclass(frozen=True)
class IdentityContext:
    user_id: UUID
    tenant_id: UUID
    session_id: UUID | None

    roles: tuple[str, ...]

    authentication_method: str
```

---

# 11. STDIO Identity

本地 STDIO 可以配置：

```text
local trusted identity
```

例如：

```text
STRUCTAI_LOCAL_USER_ID
STRUCTAI_LOCAL_TENANT_ID
```

但仍必须构造标准：

```text
IdentityContext
```

不能因为 STDIO 是本地连接就绕过：

```text
RBAC
Tenant Isolation
Audit
```

---

# 12. HTTP Authentication

Streamable HTTP 必须经过：

```text
HTTP Request
 ↓
Authentication Middleware
 ↓
IdentityContext
 ↓
MCP Session
```

支持接口预留：

```python
class AuthenticationProvider(Protocol):

    async def authenticate(
        self,
        request,
    ) -> IdentityContext:
        ...
```

第一阶段可使用：

```text
Bearer Token
```

未来可以扩展：

```text
OIDC
OAuth
mTLS
API Key
```

---

# 13. Session Manager

```python
class MCPSessionManager:

    async def create(
        self,
        client_info,
    ) -> MCPSessionContext:
        ...

    async def get(
        self,
        session_id: str,
    ) -> MCPSessionContext:
        ...

    async def close(
        self,
        session_id: str,
    ) -> None:
        ...
```

---

# 14. Session 生命周期

```text
NEW
 ↓
INITIALIZING
 ↓
ACTIVE
 ↓
CLOSING
 ↓
CLOSED
```

异常：

```text
FAILED
```

---

# 15. Session 状态模型

```python
class SessionState(str, Enum):

    NEW = "NEW"
    INITIALIZING = "INITIALIZING"
    ACTIVE = "ACTIVE"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    FAILED = "FAILED"
```

---

# 16. Session 超时

配置：

```text
session_idle_timeout
session_max_lifetime
```

例如：

```text
idle timeout = 30 min
max lifetime = 24 h
```

具体默认值由 Settings 决定。

Session 关闭时：

```text
session
 ↓
revoke authentication binding
 ↓
release session resources
 ↓
audit
 ↓
CLOSED
```

---

# 17. Session 与 Task

Session 关闭：

```text
≠
自动取消全部 Task
```

必须根据 Task Policy：

```text
DETACH
CANCEL
CONTINUE
```

默认推荐：

```text
DETACH
```

原因：

```text
MCP Client 掉线
≠
工程分析必须停止
```

---

# 18. Request Context

每个 MCP Request 都建立：

```python
@dataclass(frozen=True)
class MCPRequestContext:

    session_id: str
    request_id: str

    trace_id: str

    identity: IdentityContext

    client_name: str
    client_version: str
```

再转换为 Core：

```python
ExecutionContext
```

---

# 19. Request ID

MCP 原始 Request ID 不一定适合内部全部系统。

建议：

```text
MCP request id
+
server-generated request_id
+
trace_id
```

例如：

```text
mcp_id = 17
request_id = req_8e...
trace_id = trace_91...
```

---

# 20. Request Limits

Settings：

```python
@dataclass(frozen=True)
class MCPRuntimeLimits:

    max_message_bytes: int
    max_request_bytes: int

    max_tool_arguments_bytes: int

    max_concurrent_sessions: int
    max_requests_per_session: int

    max_inflight_requests: int
```

---

# 21. Message Size

收到消息后：

```text
read
 ↓
size check
 ↓
parse
```

超过：

```text
STRUCTAI-1000
```

立即拒绝。

禁止：

```text
先完整解析
再判断大小
```

避免内存攻击。

---

# 22. Concurrent Sessions

Session Manager：

```python
if active_sessions >= limit:
    raise MCPConnectionLimitError()
```

返回协议层错误。

不能创建无限 Session。

---

# 23. Per-Session Request Limit

限制：

```text
active requests
```

例如：

```text
max 16
```

如果达到：

```text
request rejected / queued
```

策略由 Settings 决定。

---

# 24. Global Inflight Limit

全局：

```text
max_inflight_requests
```

防止一个客户端消耗整个 Runtime。

---

# 25. tools/list

MCP Client 请求：

```text
tools/list
```

服务端从：

```text
ToolRegistry
```

生成工具定义。

---

# 26. Tool Schema 映射

内部：

```python
ToolDefinition
```

转换为 MCP：

```json
{
  "name": "engineering_model_query",
  "description": "Query canonical engineering model",
  "inputSchema": {
    "type": "object"
  }
}
```

MCP 层不能自行修改 Operation Registry。

---

# 27. Tool Input Schema

建议 MCP Tool 的顶层 Schema 统一：

```json
{
  "type": "object",
  "properties": {
    "operation": {
      "type": "string"
    },
    "parameters": {
      "type": "object"
    },
    "context": {
      "type": "object"
    },
    "idempotency_key": {
      "type": ["string", "null"]
    },
    "confirmation_token": {
      "type": ["string", "null"]
    },
    "dry_run": {
      "type": "boolean"
    },
    "batch": {
      "type": ["array", "null"]
    }
  },
  "required": [
    "operation"
  ]
}
```

真正 operation 参数 Schema 仍由：

```text
Schema Engine
```

二次验证。

---

# 28. 为什么需要两级 Schema

第一层：

```text
MCP Tool Envelope
```

验证：

```text
operation
parameters
context
```

第二层：

```text
Operation Schema
```

验证：

```text
BUILD.COLUMN
MODEL.NODE.CREATE
ANALYSIS.STATIC
```

这样可以避免 9 个 Tool 产生大量独立 MCP Tool。

---

# 29. tools/call

处理流程：

```text
tools/call
 ↓
Session Validate
 ↓
Authentication
 ↓
Tool Lookup
 ↓
ToolRequest Parse
 ↓
ToolRuntime.invoke
```

---

# 30. tools/call Handler

```python
async def call_tool(
    session: MCPSessionContext,
    name: str,
    arguments: dict,
):

    request_context = await context_builder.build(
        session=session,
    )

    request = ToolRequest.model_validate(
        arguments
    )

    return await tool_runtime.invoke(
        name,
        request,
        request_context.execution_context,
    )
```

---

# 31. Tool Result → MCP Result

Core：

```python
MCPExecutionResponse
```

映射为 MCP：

```text
content[]
structuredContent
isError
```

建议：

```json
{
  "content": [
    {
      "type": "text",
      "text": "..."
    }
  ],
  "structuredContent": {
    "success": true,
    "data": {}
  },
  "isError": false
}
```

具体字段必须按照实际 MCP SDK 类型生成，不应手工构造与 SDK 不一致的 wire object。

---

# 32. Error Mapping

StructAI：

```text
STRUCTAI-4000
STRUCTAI-4100
STRUCTAI-3000
STRUCTAI-2300
STRUCTAI-5000
```

映射为 MCP：

```text
protocol error
```

或：

```text
tool execution error
```

区分：

```text
Protocol Failure
Tool Failure
```

---

# 33. Protocol Failure

例如：

```text
invalid JSON
invalid request
unknown method
invalid params
```

属于：

```text
MCP Protocol Layer
```

---

# 34. Tool Failure

例如：

```text
permission denied
capability unavailable
analysis failed
adapter timeout
```

属于：

```text
Tool Execution
```

客户端必须能够区分。

---

# 35. Progress Notification

异步任务：

```text
Tool Call
 ↓
Task Created
 ↓
Progress
 ↓
Progress
 ↓
Completed
```

Progress 数据：

```json
{
  "progress": 43,
  "total": 100,
  "message": "Running static analysis"
}
```

---

# 36. Progress Bridge

```python
class MCPProgressBridge:

    async def on_progress(
        self,
        task_id: UUID,
        progress: float,
        message: str | None,
        session_id: str,
        progress_token,
    ):
        ...
```

TaskEngine：

```text
TaskProgress Event
 ↓
Progress Bridge
 ↓
MCP Notification
```

---

# 37. Progress Token

客户端可提供：

```text
progressToken
```

服务端不得将：

```text
progressToken
```

当成：

```text
task_id
```

二者必须独立。

---

# 38. Cancellation

取消请求：

```text
MCP Cancellation
 ↓
Session
 ↓
TaskEngine.cancel()
 ↓
Adapter.cancel()
```

如果底层 Adapter 不支持：

```text
CANCEL_REQUESTED
```

然后：

```text
真实任务状态
```

决定最终：

```text
CANCELLED
```

或：

```text
RUNNING
```

---

# 39. Cancellation Policy

```python
class CancellationPolicy(str, Enum):

    IMMEDIATE = "IMMEDIATE"
    COOPERATIVE = "COOPERATIVE"
    UNSUPPORTED = "UNSUPPORTED"
```

Adapter 必须声明：

```python
cancel_policy
```

---

# 40. STDIO Transport

STDIO：

```text
stdin
 ↓
MCP message decoder
 ↓
Protocol
 ↓
ToolRuntime
 ↓
stdout
```

关键规则：

```text
stdout 只能输出 MCP protocol data
```

日志必须：

```text
stderr
```

否则：

```text
stdout contamination
```

会破坏 MCP 通信。

---

# 41. STDIO 实现骨架

```python
class StdioTransport:

    def __init__(
        self,
        reader,
        writer,
    ):
        self.reader = reader
        self.writer = writer

    async def start(self):
        ...

    async def receive(self):
        while True:
            message = await self.reader.readline()

            if not message:
                break

            yield message

    async def send(self, message: bytes):
        self.writer.write(message)
        await self.writer.drain()

    async def close(self):
        self.writer.close()
```

实际 wire framing 必须由采用的 MCP SDK/协议实现负责，不能假设简单 `readline()` 永远适用所有 MCP transport 实现。

---

# 42. STDIO 日志

正确：

```text
stdout → MCP
stderr → logs
```

例如：

```python
logger = logging.getLogger("structai")
handler = logging.StreamHandler(sys.stderr)
```

禁止：

```python
print("debug")
```

因为：

```text
print → stdout
```

---

# 43. STDIO 安全

本地 STDIO 默认：

```text
单客户端
```

建议：

```text
one process
one stdio session
```

如果需要多客户端：

```text
HTTP transport
```

更合适。

---

# 44. Streamable HTTP

HTTP 结构：

```text
HTTP Server
 ↓
Authentication Middleware
 ↓
MCP Session Middleware
 ↓
MCP Protocol
 ↓
ToolRuntime
```

---

# 45. HTTP Endpoint

建议配置：

```text
/mcp
```

例如：

```text
POST /mcp
```

具体 path 必须可配置。

---

# 46. HTTP Methods

Transport 层按实际采用的 MCP Streamable HTTP 规范处理：

```text
POST
GET
DELETE
```

具体是否启用以及各方法的语义由 MCP SDK/协议版本决定。

不要在 Core 中写死不存在的行为。

---

# 47. HTTP Session

服务端需要维护：

```text
MCP session ID
```

Session 信息：

```text
session_id
identity
client_info
protocol_version
created_at
last_activity
state
```

---

# 48. Session ID 安全

Session ID：

```text
cryptographically random
```

不能：

```text
UUID incremental
user_id
tenant_id
```

建议：

```python
secrets.token_urlsafe(32)
```

---

# 49. HTTP Session Binding

Session 必须绑定：

```text
authenticated identity
```

例如：

```text
session A
 ↓
user 001
tenant 001
```

如果后续请求：

```text
user 002
```

必须拒绝。

---

# 50. Origin / Host 安全

HTTP 服务必须考虑：

```text
Host
Origin
```

特别是本地部署场景。

允许列表：

```text
localhost
127.0.0.1
configured host
```

如果启用浏览器访问：

```text
explicit allowlist
```

禁止：

```text
allow all
```

作为默认安全配置。

---

# 51. CORS

如果 HTTP MCP 不需要浏览器直接调用：

```text
CORS disabled
```

如果需要：

```text
explicit origins
```

禁止：

```text
*
```

与凭证认证同时使用。

---

# 52. HTTP Body Limit

服务器必须在 body 进入业务解析前限制：

```text
Content-Length
streaming body size
```

超过：

```text
413
```

或者对应 MCP/HTTP 层错误。

---

# 53. Rate Limit

至少：

```text
per IP
per identity
per tenant
per session
```

但真正工程操作限流仍由：

```text
Core Quota
```

控制。

HTTP Rate Limit：

```text
Transport protection
```

Core Quota：

```text
Business protection
```

二者不能混淆。

---

# 54. HTTP Timeout

至少：

```text
header timeout
body timeout
request timeout
idle timeout
```

对于长时间工程分析：

```text
HTTP Request
```

不应该一直同步阻塞。

应：

```text
tools/call
 ↓
Task
 ↓
return task_id
```

然后：

```text
progress
result
```

---

# 55. Connection Limits

配置：

```python
@dataclass(frozen=True)
class ConnectionLimits:

    max_connections: int
    max_sessions: int
    max_connections_per_identity: int
    max_sessions_per_identity: int
```

---

# 56. Backpressure

当：

```text
Task Queue Full
```

不要：

```text
无限接受
```

应：

```text
reject
```

或：

```text
bounded queue
```

返回明确：

```text
STRUCTAI-5000
```

并说明：

```text
retryable = true
```

---

# 57. MCP Session Cleanup

后台任务：

```python
async def cleanup_sessions():
    while True:

        expired = await session_manager.find_expired()

        for session in expired:
            await session_manager.close(
                session.session_id
            )

        await asyncio.sleep(
            cleanup_interval
        )
```

---

# 58. Session Audit

记录：

```text
MCP.SESSION.CREATED
MCP.SESSION.CLOSED
MCP.SESSION.EXPIRED
MCP.AUTH.FAILED
```

不要记录：

```text
Bearer Token
API Key
Cookie
Secret
```

---

# 59. Session Metrics

增加：

```text
structai_mcp_sessions_created_total
structai_mcp_sessions_closed_total
structai_mcp_sessions_active
structai_mcp_auth_failures_total
structai_mcp_requests_total
structai_mcp_request_errors_total
```

---

# 60. MCP Request Trace

每次：

```text
tools/call
```

至少建立：

```text
mcp.request
mcp.tool
```

然后进入 Core：

```text
operation.execute
```

完整：

```text
mcp.request
  └── mcp.tool
       └── operation.execute
            └── task.execute
                 └── adapter.execute
```

---

# 61. Protocol Logging

日志：

```text
session_id
request_id
trace_id
method
tool
duration
status
```

不要记录：

```text
完整 arguments
完整 result
credential
token
```

特别是工程模型可能非常大。

---

# 62. Sensitive Data Redaction

建立：

```python
class Redactor:

    SENSITIVE_KEYS = {
        "password",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "secret",
        "private_key",
        "authorization",
    }

    def redact(self, value):
        ...
```

对：

```text
logs
audit metadata
trace attributes
errors
```

统一处理。

---

# 63. MCP Server Error Envelope

内部统一：

```python
@dataclass
class MCPError:

    code: str
    message: str
    retryable: bool
    request_id: str
    trace_id: str
```

对外：

```text
不要暴露 stack trace
```

Debug 模式才允许：

```text
internal diagnostic reference
```

---

# 64. Server Instructions

`initialize` 可以返回：

```text
StructAI MCP Server exposes software-neutral engineering tools.
Use operation names to select engineering actions.
Do not assume vendor-specific APIs.
Long-running operations return task_id.
```

这能帮助 Generic AI Client 正确使用 9 Tool。

---

# 65. tools/list 不暴露内部架构

Client 看到：

```text
engineering_model_build
```

而不是：

```text
TaskEngine
AdapterManager
API Registry
SQLAlchemy
```

内部实现完全隐藏。

---

# 66. Generic MCP Client 测试

测试客户端必须完成：

```text
connect
 ↓
initialize
 ↓
initialized
 ↓
tools/list
 ↓
engineering_model_query
 ↓
engineering_model_build
 ↓
task polling/progress
 ↓
engineering_result
```

---

# 67. Generic Client Query

```json
{
  "operation": "MODEL.NODE.QUERY",
  "parameters": {
    "limit": 100
  },
  "context": {
    "software_instance_id": "..."
  }
}
```

---

# 68. Generic Client Build

```json
{
  "operation": "BUILD.COLUMN",
  "parameters": {
    "base": [0, 0, 0],
    "height": 6,
    "material": "Q355B",
    "section": "H400x400x13x21"
  },
  "context": {
    "software_instance_id": "...",
    "project_id": "...",
    "model_id": "..."
  },
  "idempotency_key": "demo-column-001"
}
```

高风险时：

```text
STRUCTAI-4100
```

然后获取：

```text
confirmation token
```

再执行。

---

# 69. Generic Client Analysis

```json
{
  "operation": "ANALYSIS.STATIC",
  "parameters": {
    "load_case": "LC1"
  },
  "context": {
    "software_instance_id": "...",
    "model_id": "..."
  },
  "idempotency_key": "static-analysis-001"
}
```

返回：

```json
{
  "execution": {
    "mode": "ASYNC",
    "status": "QUEUED",
    "task_id": "..."
  }
}
```

---

# 70. Generic Client Result

分析完成后：

```json
{
  "operation": "RESULT.NODE.DISPLACEMENT",
  "parameters": {
    "node_ids": [2]
  }
}
```

返回：

```json
{
  "data": [
    {
      "node_id": 2,
      "ux": 0.0,
      "uy": 0.0,
      "uz": -0.015
    }
  ]
}
```

---

# 71. Transport Test Matrix

## STDIO

```text
[ ] initialize
[ ] tools/list
[ ] tools/call
[ ] malformed input
[ ] oversized message
[ ] stdout contamination
[ ] stderr logging
[ ] disconnect
```

## HTTP

```text
[ ] initialize
[ ] session creation
[ ] session reuse
[ ] authentication
[ ] wrong identity
[ ] tools/list
[ ] tools/call
[ ] progress
[ ] cancellation
[ ] oversized body
[ ] rate limit
[ ] timeout
[ ] session expiry
[ ] Origin validation
```

---

# 72. Security Test Matrix

```text
[ ] invalid token
[ ] expired token
[ ] revoked token
[ ] tenant mismatch
[ ] session identity mismatch
[ ] forged session ID
[ ] forged confirmation token
[ ] oversized message
[ ] oversized arguments
[ ] connection exhaustion
[ ] request exhaustion
[ ] tool enumeration
[ ] sensitive log leakage
```

---

# 73. Session Isolation Test

场景：

```text
User A
Tenant A
Session A
```

尝试访问：

```text
Session B
Tenant B
```

必须：

```text
DENIED
```

---

# 74. Confirmation Binding Test

Token：

```text
User A
Operation BUILD.COLUMN
Model A
Request A
```

尝试用于：

```text
User B
Operation BUILD.COLUMN
Model B
Request B
```

必须：

```text
STRUCTAI-4100
```

或对应的安全拒绝错误。

---

# 75. Cancellation Test

```text
start ANALYSIS.STATIC
 ↓
task RUNNING
 ↓
cancel
 ↓
adapter.cancel
```

验证：

```text
CANCEL_REQUESTED
```

以及最终真实状态。

不能直接断言：

```text
CANCELLED
```

除非 Adapter 确认已取消。

---

# 76. STDIO E2E

启动：

```bash
python -m app.main --transport stdio
```

然后 Generic MCP Client：

```text
initialize
tools/list
tools/call
```

要求：

```text
stdout = MCP only
stderr = logs
```

---

# 77. HTTP E2E

启动：

```bash
python -m app.main --transport http
```

检查：

```text
POST /mcp
```

完成：

```text
initialize
tools/list
tools/call
```

---

# 78. 配置

新增：

```python
@dataclass(frozen=True)
class MCPSettings:

    transport: str

    stdio_enabled: bool
    http_enabled: bool

    http_host: str
    http_port: int
    http_path: str

    session_idle_timeout: int
    session_max_lifetime: int

    max_message_bytes: int
    max_request_bytes: int

    max_sessions: int
    max_inflight_requests: int
```

---

# 79. 推荐环境变量

```text
STRUCTAI_MCP_TRANSPORT=stdio

STRUCTAI_MCP_HTTP_HOST=127.0.0.1
STRUCTAI_MCP_HTTP_PORT=8000
STRUCTAI_MCP_HTTP_PATH=/mcp

STRUCTAI_MCP_MAX_MESSAGE_BYTES=10485760
STRUCTAI_MCP_MAX_REQUEST_BYTES=10485760

STRUCTAI_MCP_MAX_SESSIONS=100
STRUCTAI_MCP_MAX_INFLIGHT_REQUESTS=100

STRUCTAI_MCP_SESSION_IDLE_TIMEOUT=1800
STRUCTAI_MCP_SESSION_MAX_LIFETIME=86400
```

生产环境不要直接复制这些默认值而不评估实际负载。

---

# 80. 目录结构

在前十五份基础上增加：

```text
app/
├── interfaces/
│   └── mcp/
│       ├── server.py
│       ├── context.py
│       ├── responses.py
│       ├── protocol.py
│       ├── session.py
│       ├── authentication.py
│       ├── progress.py
│       ├── cancellation.py
│       ├── tools/
│       └── transport/
│           ├── base.py
│           ├── stdio.py
│           └── http.py
│
└── application/
    └── mcp/
        ├── session_service.py
        └── runtime_service.py
```

---

# 81. 推荐 MCP Runtime 类关系

```text
MCPServerRuntime
        │
        ├── MCPProtocolServer
        │       │
        │       ├── SessionManager
        │       ├── AuthenticationProvider
        │       ├── ToolRuntime
        │       ├── ProgressBridge
        │       └── CancellationBridge
        │
        └── MCPTransport
                ├── StdioTransport
                └── StreamableHTTPTransport
```

---

# 82. 禁止循环依赖

必须：

```text
interfaces.mcp
 ↓
application
 ↓
domain
```

不能：

```text
domain
 ↓
interfaces.mcp
```

不能：

```text
adapter
 ↓
MCP transport
```

---

# 83. Core Alpha 完整入口

最终：

```python
async def create_app():

    settings = load_settings()

    db = create_database(settings)

    repositories = create_repositories(db)

    security = create_security(settings, repositories)

    registry = create_registry(repositories)

    adapter_manager = create_adapter_manager(
        registry,
        settings,
    )

    task_engine = create_task_engine(
        repositories,
        adapter_manager,
    )

    observability = create_observability(
        repositories,
        settings,
    )

    tool_runtime = create_tool_runtime(
        registry=registry,
        security=security,
        task_engine=task_engine,
        adapter_manager=adapter_manager,
        observability=observability,
    )

    mcp_server = create_mcp_server(
        tool_runtime=tool_runtime,
        security=security,
        settings=settings,
    )

    return mcp_server
```

---

# 84. 启动顺序

```text
1. Load Config
2. Initialize Logging
3. Initialize DB
4. Run Migrations
5. Load Registry
6. Load Plugins
7. Initialize Security
8. Initialize Event Bus
9. Initialize Task Engine
10. Initialize Artifact Service
11. Initialize Observability
12. Register 9 Tools
13. Start Adapter Manager
14. Start MCP Session Manager
15. Start Transport
```

---

# 85. 关闭顺序

```text
1. Stop accepting new MCP requests
2. Stop new Task submissions
3. Drain / detach active requests
4. Stop Event Dispatcher
5. Stop Task Scheduler
6. Disconnect Adapters
7. Close Sessions
8. Flush Audit
9. Flush Trace
10. Flush Metrics
11. Close DB
12. Close Transport
```

---

# 86. Core Alpha DoD

```text
[ ] MCP Server Bootstrap
[ ] MCP Transport abstraction
[ ] STDIO
[ ] Streamable HTTP
[ ] MCP Session
[ ] Session lifecycle
[ ] Authentication Context
[ ] tools/list
[ ] tools/call
[ ] Progress
[ ] Cancellation
[ ] Session limits
[ ] Request limits
[ ] Message limits
[ ] Rate limiting
[ ] Error mapping
[ ] Sensitive data redaction
[ ] Trace integration
[ ] Audit integration
[ ] Metrics integration
[ ] Generic MCP Client
[ ] STDIO E2E
[ ] HTTP E2E
[ ] Security tests
[ ] Recovery tests
```

---

# 87. 第十六份完成后的完整架构

```text
                    Generic AI / MCP Client
                              │
                              ▼
                    ┌──────────────────┐
                    │ MCP Transport    │
                    │ STDIO / HTTP     │
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │ MCP Protocol     │
                    │ Session          │
                    └────────┬─────────┘
                             ▼
                    Authentication
                             │
                             ▼
                    ┌──────────────────┐
                    │ 9 MCP Tools      │
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │ Tool Runtime     │
                    └────────┬─────────┘
                             ▼
                    Execution Pipeline
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
       Security          Capability          Lock
          │                  │                  │
          └──────────────────┼──────────────────┘
                             ▼
                        Task Engine
                             │
                             ▼
                      Adapter Manager
                             │
               ┌─────────────┼─────────────┐
               ▼             ▼             ▼
             MIDAS          ETABS        OpenSees
               │             │             │
               └─────────────┼─────────────┘
                             ▼
                     Result / Artifact
                             │
            ┌────────────────┼────────────────┐
            ▼                ▼                ▼
          Event            Audit            Trace
            │                │                │
            └────────────────┼────────────────┘
                             ▼
                          Metrics
```

---

# 88. 下一份

第十六份完成后，下一阶段进入：

## ⑰ MIDAS Adapter Runtime Source-Level Implementation

重点不再设计 Core，而是正式实现：

```text
MIDAS Adapter
MIDAS API Registry
MIDAS Version Resolver
MIDAS Capability Mapping
MIDAS Request Transformer
MIDAS Response Transformer
MIDAS Error Normalizer
MIDAS Connection Manager
MIDAS Health Check
MIDAS Authentication
MIDAS API Client
MIDAS Operation Mapping
MIDAS 2025 / 2026 Version Strategy
```

并且必须坚持：

```text
9 MCP Tools
        ↓
Operation
        ↓
Capability
        ↓
MIDAS Adapter
        ↓
MIDAS API Registry
        ↓
Native MIDAS API
```

而不是：

```text
MCP Tool
 ↓
MIDAS Endpoint
```

第十七份开始，才会把真正的 MIDAS API 手册中的接口映射接入 StructAI Core。



# 完整收录：midasall

# StructAI MCP Server V2.0
# MIDAS Adapter 完整源码级实现规范
## 合并文档：原 ⑰～㉛全部内容

> 文档版本：V2.0-MIDAS-ADAPTER-ALL  
> 文档性质：源码级实施规范 / Registry / Transformer / Runtime / Recovery / Test / Production Hardening  
> 适用产品：MIDAS CIVIL NX、MIDAS GEN NX  
> 上层系统：StructAI MCP Server V2.0  
> 文档目标：在**不丢失原 ⑰～㉛内容**的前提下，将 15 份 MIDAS 相关文档合并为一份可直接用于开发、代码审查、测试和后续版本维护的主文档。

---

# 0. 文档说明

本文件将原以下文档合并：

```text
⑰ MIDAS Adapter Runtime — CIVIL NX / GEN NX
⑱ MIDAS API Registry 完整种子与 JSON Schema 导入
⑲ MIDAS Node / Element Transformer
⑳ MIDAS Material / Section Transformer
㉑ MIDAS Boundary / Load Transformer
㉒ MIDAS Analysis Runtime
㉓ MIDAS Result Runtime
㉔ MIDAS View Runtime
㉕ MIDAS Design Runtime
㉖ MIDAS Recovery / Reconcile
㉗ MIDAS API Contract Test
㉘ MIDAS CIVIL NX 完整 E2E
㉙ MIDAS GEN NX Adapter
㉚ Multi-Version MIDAS Runtime
㉛ MIDAS Adapter Production Hardening
```

合并原则：

1. **只合并文档，不删除实现要求。**
2. 原来独立文档中的接口、数据模型、状态机、测试要求继续保留。
3. 重复的 Core 架构说明统一到本文件的基础章节。
4. MIDAS 原生 API 与 StructAI Canonical Model 严格分离。
5. 未经官方资料或真实 API 验证的 endpoint/schema 不得标记为 `VERIFIED`。
6. 不把推测的 MIDAS API 路径、字段或返回结构当成正式接口。
7. MIDAS Adapter 不负责 MCP、RBAC、Task 全局生命周期等 Core 职责。
8. 本文是 MIDAS Adapter 的**唯一主实现文档**；以后对 MIDAS 的增量开发优先修改本文件。

---

# 1. 官方资料与事实基线

## 1.1 官方 API 总体定位

MIDAS 官方 API Online Manual 明确说明，MIDAS NX 系列包括 **CIVIL NX 与 GEN NX**，API 基于 RESTful API，官方手册提供 endpoint、method、JSON structure 和 examples。

官方文档将 API 分为：

```text
DOC
DB
OPE
VIEW
POST
```

其中：

- DOC：文档/工程文件操作；
- DB：MIDAS NX 文件中的数据库数据；
- OPE：操作型 API；
- VIEW：视图/可视化；
- POST：结果/表格等输出型数据。

官方文档同时说明 DB Endpoint 通常使用：

```text
GET
POST
PUT
DELETE
```

而 DOC Endpoint 使用 POST。

官方来源：

- MIDAS API Online Manual
- MIDAS API Settings
- Base URL and API-KEY
- How to integrate CIVIL NX / GEN NX
- Get Object
- MIDAS GH Node / Object 相关官方页面

实现时必须以当前官方 API Manual 为第一来源，而不是以第三方 SDK 或旧代码为准。

---

# 2. MIDAS Adapter 在 StructAI 中的位置

完整架构：

```text
AI Client
   ↓
MCP
   ↓
StructAI MCP Server
   ↓
9 MCP Tools
   ↓
Operation
   ↓
ExecutionService
   ↓
Capability Resolver
   ↓
Software Registry
   ↓
Adapter Manager
   ↓
MIDAS Adapter
   ↓
API Registry
   ↓
Transformer
   ↓
MIDAS REST API
   ↓
MIDAS API Server
   ↓
CIVIL NX / GEN NX
```

必须遵守：

```text
MCP Tool
    不直接调用 MIDAS

Operation
    不直接拼 MIDAS endpoint

Capability
    不绑定具体 MIDAS URL

Adapter
    负责软件差异

API Registry
    负责 operation → native API 映射

Transformer
    负责 Canonical Model ↔ MIDAS JSON

MIDAS Client
    负责 HTTP / MAPI-Key / timeout / transport
```

---

# 3. Adapter 职责边界

## 3.1 Adapter 负责

```text
1. 建立 MIDAS API 连接
2. 保存/读取连接配置引用
3. 获取产品版本
4. Health Check
5. Capability Detection
6. API Registry Resolution
7. Canonical → MIDAS Request Transform
8. MIDAS Response → Canonical Transform
9. Native Error → StructAI Error
10. Analysis 状态检查
11. Recovery / Reconcile
12. MIDAS 特有并发策略
13. MIDAS 版本兼容
14. MIDAS Contract Test
```

## 3.2 Adapter 不负责

```text
MCP Protocol
MCP Session
Global Authentication
Global RBAC
Tenant
Project ACL
Global Task Lifecycle
Global Audit
Global Trace
Global Event Bus
UI
AI Prompt
AI Agent Permission Elevation
```

---

# 4. MIDAS Adapter 核心接口

```python
from abc import ABC, abstractmethod
from typing import Any

class EngineeringSoftwareAdapter(ABC):
    name: str
    vendor: str
    product: str

    @abstractmethod
    async def connect(self, config: dict) -> None:
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    @abstractmethod
    async def health_check(self) -> dict:
        ...

    @abstractmethod
    async def get_version(self) -> str:
        ...

    @abstractmethod
    async def get_capabilities(self) -> list[str]:
        ...

    @abstractmethod
    async def execute(
        self,
        operation: str,
        parameters: dict,
        context,
    ) -> dict:
        ...

    @abstractmethod
    async def cancel(self, task_id: str) -> None:
        ...

    @abstractmethod
    async def normalize_error(self, error: Exception) -> dict:
        ...
```

MIDAS Adapter 应实现：

```python
class MidasAdapter(EngineeringSoftwareAdapter):
    name = "midas"
    vendor = "MIDAS"

    async def connect(self, config): ...
    async def disconnect(self): ...
    async def health_check(self): ...
    async def get_version(self): ...
    async def get_capabilities(self): ...
    async def execute(self, operation, parameters, context): ...
    async def cancel(self, task_id): ...
    async def normalize_error(self, error): ...
```

---

# 5. MIDAS 连接模型

## 5.1 官方连接信息

MIDAS API Settings 提供：

```text
Base URL
MAPI-Key
Status
Connect
Disconnect
Refresh
Connect API on Startup
```

MAPI-Key 是访问 MIDAS API 的关键认证信息。

StructAI 必须：

```text
Base URL
    → 普通配置

MAPI-Key
    → Secret Reference
    → CredentialProvider
```

不得：

```text
数据库明文保存
日志打印
Trace 打印
Audit 打印
MCP Response 返回
Exception Message 返回
```

---

# 6. MIDAS HTTP Client

建议文件：

```text
app/infrastructure/adapters/midas/client.py
```

接口：

```python
class MidasHttpClient:
    def __init__(
        self,
        base_url: str,
        credential_provider,
        secret_ref: str,
        timeout: float = 30.0,
    ):
        ...

    async def get(self, path: str, **kwargs):
        ...

    async def post(self, path: str, **kwargs):
        ...

    async def put(self, path: str, **kwargs):
        ...

    async def delete(self, path: str, **kwargs):
        ...

    async def close(self):
        ...
```

请求头：

```text
MAPI-Key: <secret>
Content-Type: application/json
Accept: application/json
```

不要把 MAPI-Key 放在 URL Query。

---

# 7. MIDAS API Registry

## 7.1 Registry 目标

Registry 是：

```text
StructAI Operation
        ↓
MIDAS Product
        ↓
MIDAS Version
        ↓
HTTP Method
        ↓
Endpoint
        ↓
Request Schema
        ↓
Response Schema
        ↓
Transformer
        ↓
Verification Status
```

Registry 不允许存储任意 Python 代码。

错误设计：

```text
database:
    python_code = "exec(...)"
```

正确设计：

```text
database:
    transformer = "midas.node.v1"
```

真正 transformer 位于：

```text
app/infrastructure/adapters/midas/transformers/
```

---

# 8. Registry 状态

每个 endpoint 必须有：

```text
VERIFIED
PARTIAL
UNVERIFIED
DEPRECATED
```

定义：

### VERIFIED

以下全部满足：

```text
官方 endpoint 已确认
HTTP Method 已确认
Request Schema 已确认
Response Schema 已确认
产品范围已确认
版本范围已确认
至少一次真实 API Contract Test 通过
```

### PARTIAL

例如：

```text
Endpoint 已确认
Method 已确认
但 Request/Response Schema 尚未完全验证
```

### UNVERIFIED

仅存在于：

```text
草稿
未来版本
开发研究
待验证 API
```

生产执行禁止使用。

### DEPRECATED

旧 API：

```text
仍可能存在
但官方已经废弃
```

生产默认禁止，除非明确开启兼容策略。

---

# 9. Registry 数据模型

建议：

```text
midas_api_sources
midas_api_endpoints
midas_api_schemas
midas_api_versions
midas_api_mappings
midas_api_verifications
midas_capability_mappings
```

---

# 10. MidasApiSource

```python
class MidasApiSource(Base):
    __tablename__ = "midas_api_sources"

    id = mapped_column(UUID, primary_key=True)

    source_url = mapped_column(String(1000), nullable=False)
    source_title = mapped_column(String(500))

    product = mapped_column(String(100))
    category = mapped_column(String(50))

    manual_revision = mapped_column(String(100))
    source_hash = mapped_column(String(128))

    retrieved_at = mapped_column(DateTime(timezone=True))
    created_at = mapped_column(DateTime(timezone=True))
```

用途：

```text
记录 endpoint 从哪里来的
记录什么时候获取
记录哪个版本/手册
```

---

# 11. MidasApiEndpoint

```python
class MidasApiEndpoint(Base):
    __tablename__ = "midas_api_endpoints"

    id = mapped_column(UUID, primary_key=True)

    product = mapped_column(String(100), nullable=False)
    product_family = mapped_column(String(100))
    version_range = mapped_column(String(100))

    category = mapped_column(String(30), nullable=False)

    path = mapped_column(String(500), nullable=False)
    method = mapped_column(String(20), nullable=False)

    operation = mapped_column(String(200))

    request_schema_id = mapped_column(UUID)
    response_schema_id = mapped_column(UUID)

    verification_status = mapped_column(String(30), nullable=False)

    source_id = mapped_column(UUID)
    deprecated = mapped_column(Boolean, default=False)

    created_at = mapped_column(DateTime(timezone=True))
    updated_at = mapped_column(DateTime(timezone=True))
```

唯一性：

```text
(product, version_range, method, path)
```

---

# 12. MidasApiSchema

```python
class MidasApiSchema(Base):
    __tablename__ = "midas_api_schemas"

    id = mapped_column(UUID, primary_key=True)

    schema_uri = mapped_column(String(500), nullable=False, unique=True)

    direction = mapped_column(String(20))
    product = mapped_column(String(100))
    version_range = mapped_column(String(100))

    schema_json = mapped_column(JSON, nullable=False)

    verification_status = mapped_column(String(30))
    source_id = mapped_column(UUID)

    created_at = mapped_column(DateTime(timezone=True))
    updated_at = mapped_column(DateTime(timezone=True))
```

---

# 13. Schema URI

StructAI 与 MIDAS Schema 分开。

StructAI：

```text
structai://schema/model/node/v1
structai://schema/model/element/v1
structai://schema/model/material/v1
structai://schema/model/section/v1
```

MIDAS：

```text
midas://civil/node/request/v1
midas://civil/node/response/v1

midas://civil/elem/request/v1
midas://civil/elem/response/v1

midas://gen/node/request/v1
midas://gen/node/response/v1
```

禁止：

```text
StructAI Schema = MIDAS Schema
```

必须：

```text
Canonical
    ↓
StructAI Schema Validation
    ↓
Transformer
    ↓
MIDAS Schema Validation
    ↓
HTTP
```

---

# 14. 官方 API Registry 初始种子

以下 endpoint 来自官方 MIDAS API Manual 中明确列出的路径；具体 request/response 字段必须继续以对应 endpoint 页面验证，不能凭路径名称推断完整 JSON。

## DOC

```text
/doc/NEW
/doc/OPEN
/doc/CLOSE
/doc/SAVE
/doc/SAVEAS
/doc/STAGAS
/doc/IMPORT
/doc/IMPORTMXT
/doc/EXPORT
/doc/EXPORTMXT
/doc/ANAL
```

官方说明 DOC 只使用 POST，body 从 `Argument` 开始；空参数可使用空 body 结构。citeturn0search0

## DB

至少包括：

```text
/db/PJCF
/db/UNIT
/db/STYP
/db/GRUP
/db/BNGR
/db/LDGR
/db/TDGR

/db/NODE
/db/ELEM
/db/MATL
/db/SECT
/db/CONS
/db/NSPR
/db/GSTP
/db/GSPR
/db/SSPS
/db/ELNK
/db/RIGD
/db/NLLP
/db/NLNK
/db/STLD
/db/BODF
/db/CNLD
/db/BMLD
/db/SDSP
/db/NMAS
/db/LTOM
/db/NBOF
/db/PSLT
/db/PRES
/db/PNLD
/db/PNLA
/db/FBLD
/db/FBLA
/db/ACTL
/db/PDEL
/db/BUCK
/db/EIGV
/db/MVCT
/db/SMCT
/db/NLCT
/db/STCT
/db/BCCT
```

DB API 的基本机制是 GET/POST/PUT/DELETE；POST/PUT 的第一层关键字通常为 `Assign`，随后按照数据类型使用编号键。实际 endpoint 必须读取对应官方 schema。citeturn0search0

## OPE

```text
/ope/PROJECTSTATUS
/ope/DIVIDEELEM
/ope/SECTPROP
/ope/AUTOMESH
/ope/EDMP
```

## VIEW

```text
/view/SELECT
/view/CAPTURE
/view/PRECAPTURE
/view/ANGLE
/view/ACTIVE
/view/DISPLAY
/view/RESULTGRAPHIC
```

---

# 15. API Registry Seed 格式

建议 JSON：

```json
{
  "vendor": "MIDAS",
  "product": "CIVIL NX",
  "version_range": "2026.x",
  "category": "DOC",
  "path": "/doc/NEW",
  "method": "POST",
  "operation": "DOCUMENT.NEW",
  "request_schema": "midas://civil/doc/new/request/v1",
  "response_schema": "midas://civil/doc/new/response/v1",
  "verification_status": "VERIFIED"
}
```

注意：

`VERIFIED` 必须由真实验证流程赋值，不能因为文档存在就自动标记。

---

# 16. Registry Resolver

解析优先级：

```text
1. exact product
2. exact version
3. exact method/path
4. exact operation
5. compatible version range
6. fallback mapping
7. reject
```

禁止：

```text
版本不匹配
    ↓
盲目使用最新 API
```

正确：

```text
找不到匹配
    ↓
Capability = UNSUPPORTED
或
Adapter = DEGRADED
```

---

# 17. API Mapping

```python
@dataclass(frozen=True)
class MidasApiMapping:
    operation: str
    product: str
    version_range: str
    method: str
    path: str

    request_schema: str | None
    response_schema: str | None

    transformer: str | None

    verification_status: str
```

解析：

```python
mapping = registry.resolve(
    product="CIVIL NX",
    version="2026",
    operation="MODEL.NODE.CREATE",
)
```

返回：

```text
MidasApiMapping
```

---

# 18. API Contract Snapshot

每个 VERIFIED API 应保存：

```text
endpoint
method
request example
response example
status code
headers
schema hash
manual source
tested_at
software_version
```

例如：

```json
{
  "method": "GET",
  "path": "/db/NODE",
  "software": "CIVIL NX",
  "version": "2026",
  "schema_hash": "sha256:...",
  "verified_at": "2026-..."
}
```

---

# 19. Info API

MIDAS 官方资料还提供：

```text
baseURL/info/db/...
```

用于查看 DB resource 的 key/value 说明。

StructAI 可以把它用于：

```text
Registry Discovery
Schema Verification
开发期辅助
Contract Test
```

但：

```text
info API
    ≠
生产业务 API
```

不得将 info 内容直接当成稳定生产契约而跳过版本验证。citeturn0search11

---

# 20. Node Transformer

## 20.1 Canonical Node

```python
@dataclass
class CanonicalNode:
    id: int
    x: float
    y: float
    z: float
```

Schema：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "structai://schema/model/node/v1",
  "type": "object",
  "properties": {
    "id": {"type": "integer"},
    "x": {"type": "number"},
    "y": {"type": "number"},
    "z": {"type": "number"}
  },
  "required": ["id", "x", "y", "z"]
}
```

---

# 21. Node Request Transformer

```python
class MidasNodeTransformer:
    def to_native_create(self, node: CanonicalNode) -> dict:
        ...

    def to_native_update(self, node: CanonicalNode) -> dict:
        ...

    def from_native(self, data: dict) -> CanonicalNode:
        ...
```

重要：

不得在 Transformer 中硬编码所有 endpoint。

正确：

```text
Transformer
    ↓
Registry Schema
```

而不是：

```python
if operation == "MODEL.NODE.CREATE":
    ...
```

---

# 22. Node CRUD

StructAI：

```text
MODEL.NODE.QUERY
MODEL.NODE.CREATE
MODEL.NODE.UPDATE
MODEL.NODE.DELETE
```

MIDAS：

```text
/db/NODE
```

官方 Node 示例说明 Create Node 通过 POST，删除使用 DELETE。citeturn0search7

查询：

```text
GET /db/NODE
```

官方 Get Object 说明 DB 查询可以通过 `/db/...` 获取 JSON 数据。citeturn0search9

---

# 23. Node ID 策略

StructAI 不应默认假定：

```text
MIDAS 永远自动编号
```

必须支持：

```text
EXPLICIT
AUTO
```

Canonical 请求：

```json
{
  "id": 100,
  "x": 0,
  "y": 0,
  "z": 6
}
```

如果 MIDAS 返回自动 ID：

```text
native_id
    ↓
mapping
    ↓
canonical_id
```

必须保存映射关系。

---

# 24. Element Transformer

Canonical：

```python
@dataclass
class CanonicalElement:
    id: int
    type: str
    node_ids: list[int]
    material_id: int | None
    section_id: int | None
```

支持至少：

```text
BEAM
COLUMN
TRUSS
PLATE
SHELL
SOLID
```

不要在 Core 中定义 MIDAS 专用 element code。

---

# 25. Element 创建

典型：

```text
Canonical Element
    ↓
validate node_ids
    ↓
validate material
    ↓
validate section
    ↓
Transformer
    ↓
MIDAS /db/ELEM
```

前置条件：

```text
nodes exist
material exists
section exists
element id unique
```

---

# 26. Element 查询

```text
MODEL.ELEMENT.QUERY
```

支持：

```text
all
by id
by group
by type
by node
```

必须分页。

```json
{
  "items": [],
  "pagination": {
    "has_more": false,
    "next_cursor": null
  }
}
```

---

# 27. Material Transformer

Canonical：

```python
@dataclass
class CanonicalMaterial:
    id: int
    name: str
    type: str
    properties: dict
```

StructAI 不直接把：

```text
MIDAS MATL JSON
```

暴露给 AI。

AI 使用：

```json
{
  "id": 1,
  "name": "Q355B",
  "type": "STEEL",
  "properties": {
    "E": 206000000000,
    "fy": 355000000
  }
}
```

Transformer 再转 MIDAS schema。

---

# 28. Material Validation

必须检查：

```text
E > 0
density >= 0
fy > 0 for steel
fc > 0 for concrete
```

同时检查：

```text
unit system
material type
product capability
```

---

# 29. Section Transformer

Canonical：

```python
@dataclass
class CanonicalSection:
    id: int
    name: str
    section_type: str
    parameters: dict
```

例如：

```json
{
  "id": 1,
  "name": "H400x400x13x21",
  "section_type": "H",
  "parameters": {
    "height": 0.4,
    "width": 0.4,
    "tw": 0.013,
    "tf": 0.021
  }
}
```

注意：

这里是 StructAI canonical 参数示例，不是声明 MIDAS 官方字段名。

---

# 30. Section Property

MIDAS API/OPE 中存在截面属性相关能力；例如 `/ope/SECTPROP` 可作为 section-property operation 的 native mapping 候选。

但：

```text
DESIGN.STEEL
≠
SECTPROP
```

截面属性计算不能被误认为设计验算。

---

# 31. Boundary Transformer

Canonical：

```python
@dataclass
class CanonicalBoundary:
    node_id: int
    ux: bool
    uy: bool
    uz: bool
    rx: bool
    ry: bool
    rz: bool
```

例如：

```json
{
  "node_id": 1,
  "ux": true,
  "uy": true,
  "uz": true,
  "rx": true,
  "ry": true,
  "rz": true
}
```

转换到 MIDAS 对应 DB resource。

Boundary 的具体 MIDAS endpoint/schema 必须通过 Registry 绑定，不允许在 Core 中硬编码。

---

# 32. Load Transformer

Canonical Load：

```python
@dataclass
class CanonicalLoad:
    id: int
    load_case: str
    load_type: str
    target_type: str
    target_id: int
    values: dict
```

支持抽象：

```text
NODE_FORCE
NODE_MOMENT
BEAM_FORCE
BEAM_MOMENT
PRESSURE
TEMPERATURE
SELF_WEIGHT
```

---

# 33. Load Case

必须区分：

```text
Load Group
Load Case
Load Combination
Load Pattern
Load Type
```

不要在 StructAI 内把它们混为一个 `load_case` 字段。

Registry 应明确映射：

```text
LOAD.GROUP
LOAD.CASE
LOAD.COMBINATION
LOAD.ASSIGN
```

---

# 34. Load Assignment

执行：

```text
MODEL.LOAD.ASSIGN
```

流程：

```text
Input
 ↓
Schema
 ↓
Engineering Validation
 ↓
Target Exists
 ↓
Load Case Exists
 ↓
Capability
 ↓
Lock
 ↓
Transformer
 ↓
MIDAS
 ↓
Normalize
 ↓
Audit
```

---

# 35. Analysis Runtime

分析执行的关键事实：

官方 MIDAS API Manual 将：

```text
/doc/ANAL
```

列为：

```text
Perform Analysis
```

因此 StructAI：

```text
ANALYSIS.STATIC
```

不应直接硬编码成某个未经验证的 `/anal/STATIC` 路径。

正确架构：

```text
ANALYSIS.STATIC
    ↓
Capability
    ↓
Registry
    ↓
MIDAS /doc/ANAL
    ↓
Transformer / Argument
```

---

# 36. Analysis Operation

统一：

```text
ANALYSIS.STATIC
ANALYSIS.MODAL
ANALYSIS.SEISMIC
ANALYSIS.SPECTRUM
ANALYSIS.BUCKLING
ANALYSIS.TIME_HISTORY
ANALYSIS.NONLINEAR
```

但必须区分：

```text
StructAI conceptual operation
```

与：

```text
MIDAS actual native execution parameter
```

是否支持某种分析由：

```text
Capability Registry
```

决定。

---

# 37. Analysis Task

分析必须默认：

```text
ASYNC
```

原因：

```text
分析时间不可预测
软件可能阻塞
结果文件可能异步生成
```

Task：

```text
CREATED
VALIDATING
QUEUED
RUNNING
PROCESSING
COMPLETED
FAILED
TIMEOUT
RECOVERING
```

---

# 38. Analysis Resource Lock

默认：

```text
Software Instance = EXCLUSIVE
Model = READ
```

因为分析过程中软件状态可能改变。

禁止：

```text
同时两个分析
```

除非经过产品/版本验证确认软件支持并发。

---

# 39. Analysis Preconditions

至少：

```text
document open
model exists
nodes > 0
elements > 0
materials valid
sections valid
boundary valid
loads valid
no active write task
software healthy
API capability available
```

---

# 40. Analysis Postconditions

至少：

```text
analysis task completed
result availability checked
software status reconciled
result registry available
task artifact generated if configured
```

不能简单：

```text
HTTP 200
=
Analysis completed
```

必须检查业务状态。

---

# 41. Analysis Unknown Outcome

例如：

```text
POST /doc/ANAL
 ↓
timeout
```

不能直接：

```text
retry
```

必须：

```text
UNKNOWN
 ↓
RECONCILE
 ↓
PROJECTSTATUS / result availability / software state
 ↓
COMPLETED
或
FAILED
或
MANUAL_REVIEW
```

---

# 42. Result Runtime

Result 是：

```text
Native Result
    ↓
Parser
    ↓
Canonical Result
```

核心结果：

```text
RESULT.NODE.DISPLACEMENT
RESULT.NODE.REACTION
RESULT.ELEMENT.FORCE
RESULT.ELEMENT.STRESS
RESULT.MODE.SHAPE
RESULT.ANALYSIS.SUMMARY
```

---

# 43. Displacement Canonical

```json
{
  "node_id": 100,
  "ux": 0.001,
  "uy": 0.002,
  "uz": -0.015,
  "rx": 0.0,
  "ry": 0.0,
  "rz": 0.0
}
```

单位必须显式：

```json
{
  "units": {
    "length": "m",
    "rotation": "rad"
  }
}
```

不能假设所有 MIDAS 项目都使用 SI。

---

# 44. Reaction

Canonical：

```json
{
  "node_id": 1,
  "fx": 500000,
  "fy": 0,
  "fz": 1000000,
  "mx": 0,
  "my": 0,
  "mz": 0
}
```

必须包含：

```text
load_case
stage
step
units
```

如果原生结果没有某字段，使用 null，不要虚构 0。

---

# 45. Element Force

至少支持：

```text
axial
shear_y
shear_z
torsion
moment_y
moment_z
```

不同软件的局部坐标定义可能不同，因此必须保留：

```text
coordinate_system
local_axis_definition
```

---

# 46. Result Parser

禁止：

```python
return {
    "ux": native["DX"]
}
```

直接散落在业务代码。

正确：

```text
MIDAS Result Schema
    ↓
MidasResultParser
    ↓
CanonicalResult
```

---

# 47. Result Pagination

大型结构结果禁止一次返回全部数据。

支持：

```text
cursor
page_size
filter
node_ids
element_ids
load_cases
steps
```

---

# 48. View Runtime

VIEW API 主要用于：

```text
MODEL VIEW
RESULT VIEW
CAMERA
CAPTURE
DISPLAY
```

官方 Manual 中明确列出：

```text
/view/SELECT
/view/CAPTURE
/view/PRECAPTURE
/view/ANGLE
/view/ACTIVE
/view/DISPLAY
/view/RESULTGRAPHIC
```

这些接口应通过 View Registry 进行映射。

---

# 49. View 与 Model 数据分离

View 不应修改 Canonical Model。

错误：

```text
VIEW
 ↓
MODEL
```

正确：

```text
MODEL
 ↓
VIEW STATE
 ↓
MIDAS VIEW API
```

---

# 50. Capture Artifact

如果 `/view/CAPTURE` 返回图片：

```text
MIDAS
 ↓
image bytes
 ↓
ArtifactStorage
 ↓
artifact_id
```

MCP 返回：

```json
{
  "artifact_id": "..."
}
```

而不是把大图片直接塞进长期 task JSON。

---

# 51. Result Graphic

结果云图/图形：

```text
VIEW.RESULTGRAPHIC
```

属于：

```text
Visualization
```

不是：

```text
Canonical Result numerical data
```

二者必须分离。

---

# 52. Design Runtime

统一 StructAI：

```text
DESIGN.STEEL
DESIGN.CONCRETE
DESIGN.SRC
DESIGN.FOUNDATION
DESIGN.CODE_CHECK
DESIGN.OPTIMIZE
```

重要：

MIDAS 中存在大量与设计数据相关的 DB resources，但不能因为存在某个 `/db/...` endpoint 就推断其是设计执行 API。

例如：

```text
/db/DCON
/db/MATD
/db/RCHK
/db/LENG
/db/MEMB
/db/DCTL
/db/LTSR
/db/ULCT
/db/MBTP
/db/WMAK
/db/DSTL
```

这些可以进入 Registry，但其用途必须依据官方 endpoint 文档验证。

---

# 53. Steel Design Pipeline

```text
Model
 ↓
Load
 ↓
Analysis
 ↓
Result
 ↓
Design Configuration
 ↓
Steel Design
 ↓
Code Check
 ↓
Design Result
```

StructAI：

```text
DESIGN.STEEL
```

不能直接把：

```text
ANALYSIS.STATIC result
```

当成：

```text
DESIGN.STEEL result
```

---

# 54. Design Result Canonical

建议：

```json
{
  "member_id": 100,
  "code": "CODE-X",
  "utilization": 0.82,
  "status": "PASS",
  "checks": [
    {
      "name": "AXIAL",
      "ratio": 0.71
    },
    {
      "name": "BENDING",
      "ratio": 0.82
    }
  ]
}
```

其中 `CODE-X` 只是占位，不应伪装成某个官方设计规范。

---

# 55. Optimization

```text
DESIGN.OPTIMIZE
```

必须是：

```text
HIGH RISK
ASYNC
CONFIRMATION
```

因为优化可能修改：

```text
section
material
member
model
```

建议支持：

```text
DRY_RUN
```

返回：

```text
current
candidate
estimated_saving
constraint_violations
```

未经确认不得写回。

---

# 56. Recovery / Reconcile

Recovery 是 MIDAS Adapter 的关键部分。

## 56.1 状态

```text
KNOWN_SUCCESS
KNOWN_FAILURE
UNKNOWN
RECONCILING
RECOVERED
MANUAL_REVIEW
```

---

# 57. 网络超时

错误：

```text
POST sent
server processing
client timeout
```

此时不能认为：

```text
FAILED
```

应该：

```text
UNKNOWN
```

然后：

```text
query software state
query project status
query result availability
```

---

# 58. Build Recovery

例如：

```text
BUILD.COLUMN
```

可能执行：

```text
create node 1
create node 2
create element 3
assign material
assign section
```

如果在 element 创建后 Core 崩溃：

```text
blind retry
```

会产生：

```text
duplicate nodes
duplicate elements
```

因此 Recovery Policy：

```text
SAFE_RETRY
STATE_RECONCILE
MANUAL_REVIEW
FAIL
```

默认：

```text
BUILD
    → STATE_RECONCILE
```

---

# 59. Reconcile Algorithm

```text
Task UNKNOWN
 ↓
Adapter health
 ↓
Project status
 ↓
Query model
 ↓
Compare expected state
 ↓
Determine:
   COMPLETE
   PARTIAL
   NONE
   CONFLICT
 ↓
COMPLETE → success
PARTIAL → recovery
NONE → retry if safe
CONFLICT → manual review
```

---

# 60. Idempotency

MIDAS Adapter 必须支持：

```text
idempotency_key
```

但必须理解：

```text
StructAI idempotency
≠
MIDAS native idempotency
```

因此：

```text
StructAI
    保存 operation execution record

MIDAS
    通过状态 reconciliation 防止重复副作用
```

---

# 61. Version Runtime

支持：

```text
CIVIL NX 2025
CIVIL NX 2026
GEN NX 2025
GEN NX 2026
```

未来：

```text
2027+
```

版本选择：

```text
Exact
 ↓
Compatible Range
 ↓
Fallback
 ↓
Reject
```

---

# 62. Version Adapter Manifest

```json
{
  "name": "midas.civil",
  "vendor": "MIDAS",
  "product": "CIVIL NX",
  "supported_versions": [
    "2025",
    "2026"
  ],
  "protocols": [
    "REST"
  ]
}
```

GEN：

```json
{
  "name": "midas.gen",
  "vendor": "MIDAS",
  "product": "GEN NX",
  "supported_versions": [
    "2025",
    "2026"
  ],
  "protocols": [
    "REST"
  ]
}
```

---

# 63. CIVIL NX 与 GEN NX

两者共享：

```text
REST
MAPI-Key
DOC
DB
OPE
VIEW
```

因此共享：

```text
MidasHttpClient
Registry
Schema Engine
Error Normalizer
Recovery Framework
Capability Framework
```

但是：

```text
Product-specific endpoint
Schema
Capability
Analysis
Design
Result
```

必须允许差异。

---

# 64. Product Adapter

推荐：

```text
MidasAdapterBase
    ├── CivilNxAdapter
    └── GenNxAdapter
```

共享：

```python
class MidasAdapterBase:
    ...
```

CIVIL：

```python
class CivilNxAdapter(MidasAdapterBase):
    product = "CIVIL NX"
```

GEN：

```python
class GenNxAdapter(MidasAdapterBase):
    product = "GEN NX"
```

---

# 65. Product Capability

例如：

```text
CIVIL NX
    MODEL.NODE.READ
    MODEL.NODE.WRITE
    MODEL.ELEMENT.READ
    ...

GEN NX
    MODEL.NODE.READ
    MODEL.NODE.WRITE
    MODEL.ELEMENT.READ
    ...
```

但不能假定两者能力完全相同。

启动后：

```text
static capabilities
+
runtime detection
```

最终得到：

```text
effective capabilities
```

---

# 66. Capability Cache

字段：

```text
instance_id
product
version
capability
status
checked_at
expires_at
source
```

状态：

```text
SUPPORTED
UNSUPPORTED
UNKNOWN
```

---

# 67. Capability Refresh

触发：

```text
startup
connect
reconnect
version change
manual refresh
registry update
```

---

# 68. Unknown Version

如果：

```text
MIDAS version = 2027
```

但 Registry 只有：

```text
2025
2026
```

默认：

```text
READ_ONLY / DEGRADED
```

除非：

```text
compatible mapping
```

已经经过验证。

---

# 69. Contract Test

Contract Test 的目的：

```text
证明 Registry 描述
=
真实 MIDAS API
```

测试对象：

```text
HTTP Method
Path
Request
Response
Status
Schema
Business Effect
```

---

# 70. Contract Test Fixture

```json
{
  "product": "CIVIL NX",
  "version": "2026",
  "operation": "MODEL.NODE.QUERY",
  "method": "GET",
  "path": "/db/NODE"
}
```

执行：

```text
registry
 ↓
client
 ↓
real MIDAS
 ↓
response
 ↓
schema validator
```

---

# 71. Contract Test 分层

```text
L1 Static Registry Test
L2 Schema Test
L3 Mock Transport Test
L4 Live MIDAS Contract Test
L5 Business Effect Test
```

CI 默认：

```text
L1-L3
```

专用 MIDAS 环境：

```text
L4-L5
```

---

# 72. Contract Test 安全

Live Test 必须使用：

```text
dedicated MIDAS instance
dedicated API key
dedicated project
dedicated test model
```

不得：

```text
production model
```

---

# 73. CIVIL NX E2E

推荐第一条完整 E2E：

```text
1 Connect
2 Health
3 Version
4 Node Query
5 Node Create
6 Node Query
7 Node Delete
8 Document Save
```

第二阶段：

```text
Element
Material
Section
Boundary
Load
Analysis
Result
Design
```

---

# 74. CIVIL NX 完整工程 E2E

目标：

```text
创建一个高度 6m 的钢柱
Q355B
H400x400x13x21
底部固定
顶部 500kN 轴压力
执行静力分析
读取顶部位移
执行钢结构设计
返回利用率
```

Pipeline：

```text
BUILD.COLUMN
 ↓
MODEL.LOAD.ASSIGN
 ↓
ANALYSIS.STATIC
 ↓
RESULT.NODE.DISPLACEMENT
 ↓
DESIGN.STEEL
```

---

# 75. E2E 预期 MCP 行为

AI：

```text
创建一个高度 6m 的 Q355B H400×400×13×21 钢柱，
底部固定，顶部施加 500kN 轴压力。
完成静力分析，并返回顶部节点位移和钢柱设计利用率。
```

StructAI：

```text
BUILD.COLUMN
 ↓
MODEL.LOAD.ASSIGN
 ↓
ANALYSIS.STATIC
 ↓
RESULT.NODE.DISPLACEMENT
 ↓
DESIGN.STEEL
```

AI 不需要知道：

```text
/db/NODE
/db/ELEM
/doc/ANAL
...
```

---

# 76. GEN NX Adapter

GEN NX 使用相同 Core Contract：

```text
EngineeringSoftwareAdapter
```

实现：

```python
class GenNxAdapter(MidasAdapterBase):
    vendor = "MIDAS"
    product = "GEN NX"
```

共享：

```text
HTTP
Credential
Registry
Transformer Framework
Task
Recovery
Audit
Trace
```

不同：

```text
Registry mapping
Schema
Capability
Result
Design
```

---

# 77. GEN NX E2E

建议：

```text
Connect
 ↓
Health
 ↓
Version
 ↓
Query Node
 ↓
Create Node
 ↓
Query Element
 ↓
Material
 ↓
Section
 ↓
Boundary
 ↓
Load
 ↓
Analysis
 ↓
Result
```

然后：

```text
Design
View
Capture
```

---

# 78. API Version Migration

当 MIDAS 发布新版本：

```text
2026
 ↓
2027
```

流程：

```text
Import official manual
 ↓
Generate candidate registry
 ↓
Diff
 ↓
Schema diff
 ↓
Contract Test
 ↓
Mark VERIFIED
 ↓
Enable
```

不得：

```text
直接复制 2026 mapping
```

---

# 79. Registry Diff

比较：

```text
path
method
schema
required fields
optional fields
enum
response
status
```

输出：

```text
ADDED
REMOVED
CHANGED
UNCHANGED
```

---

# 80. Deprecated Mapping

```json
{
  "status": "DEPRECATED",
  "replacement": {
    "operation": "..."
  }
}
```

运行时：

```text
deprecated
 ↓
warning
 ↓
replacement if safe
```

高风险情况下不得自动替换。

---

# 81. Production Hardening

## 81.1 HTTP Timeout

分层：

```text
connect_timeout
read_timeout
write_timeout
pool_timeout
```

分析类：

```text
long-running
```

不能简单使用固定 30 秒作为整个 operation timeout。

---

# 82. Retry Policy

允许 retry：

```text
GET query
network connect
temporary 5xx
```

谨慎 retry：

```text
POST
PUT
DELETE
ANAL
BUILD
```

原则：

```text
No side effect
    → retry possible

Side effect
    → idempotency/reconcile first
```

---

# 83. Rate Limit

MIDAS Adapter 内部：

```text
per instance
per operation
```

避免：

```text
AI burst
```

导致桌面软件/API server 不稳定。

---

# 84. Connection Pool

默认：

```text
per software instance
```

但对于桌面软件 API：

```text
SERIAL
```

通常更安全。

HTTP connection pool：

```text
max_connections
max_keepalive
```

由实际测试确定。

---

# 85. Concurrency

默认：

```text
MODEL WRITE = EXCLUSIVE
ANALYSIS = EXCLUSIVE
DESIGN = EXCLUSIVE
VIEW = READ
QUERY = READ
```

未来如果验证软件支持并发：

```text
LIMITED
PARALLEL
```

---

# 86. Health Check

至少：

```text
API reachable
MAPI-Key valid
MIDAS connected
product
version
model state
```

返回：

```json
{
  "healthy": true,
  "connected": true,
  "product": "CIVIL NX",
  "version": "2026",
  "model_open": true
}
```

---

# 87. Health Isolation

一个 MIDAS 实例挂掉：

```text
MIDAS Instance A = DOWN
```

不应该导致：

```text
StructAI Core = DOWN
```

应返回：

```text
adapter unhealthy
```

而 Core：

```text
READY
```

---

# 88. Error Normalization

MIDAS native error：

```text
HTTP
JSON
native message
timeout
connection refused
```

统一：

```python
{
    "type": "SOFTWARE_API_ERROR",
    "provider": "MIDAS",
    "retryable": False,
    "details": {}
}
```

再映射 StructAI：

```text
STRUCTAI-2000
STRUCTAI-2100
STRUCTAI-2200
STRUCTAI-2300
STRUCTAI-3000
STRUCTAI-6000
```

---

# 89. Raw Native Error

默认：

```text
not exposed
```

Debug mode：

```json
{
  "cause": {
    "provider": "MIDAS",
    "native_code": "...",
    "native_message": "..."
  }
}
```

必须进行：

```text
secret redaction
PII redaction
```

---

# 90. Logging

结构化日志：

```text
timestamp
level
trace_id
request_id
task_id
tenant_id
user_id
software_instance
product
version
operation
path
duration
status
```

禁止：

```text
MAPI-Key
password
session token
private secret
```

---

# 91. Trace

建议：

```text
MCP
 ↓
Tool
 ↓
Operation
 ↓
Validation
 ↓
Permission
 ↓
Capability
 ↓
Task
 ↓
Lock
 ↓
Adapter
 ↓
Registry
 ↓
HTTP
 ↓
MIDAS
```

每一层：

```text
trace_id
span_id
```

---

# 92. Audit

必须记录：

```text
CREATE
UPDATE
DELETE
ANALYSIS
DESIGN
DOCUMENT SAVE
DOCUMENT OPEN
DOCUMENT CLOSE
```

Audit：

```text
audit_id
timestamp
tenant_id
user_id
project_id
software_instance
operation
resource
result
previous_hash
entry_hash
```

---

# 93. Artifact

MIDAS 可能产生：

```text
model file
result file
capture image
report
export
JSON
CSV
```

统一：

```text
ArtifactStorage
```

第一实现：

```text
LocalFilesystemStorage
```

数据库只保存：

```text
artifact_id
storage_backend
storage_key
mime_type
size
checksum
```

---

# 94. Document Runtime

StructAI：

```text
NEW
OPEN
SAVE
SAVE_AS
CLOSE
INFO
```

MIDAS：

```text
/doc/NEW
/doc/OPEN
/doc/SAVE
/doc/SAVEAS
/doc/CLOSE
```

Registry 负责映射。

---

# 95. Document State

建议：

```text
CLOSED
OPENING
OPEN
DIRTY
SAVING
SAVED
CLOSING
ERROR
```

---

# 96. Document Safety

如果：

```text
DIRTY
```

执行：

```text
CLOSE
```

必须根据用户/策略：

```text
SAVE
DISCARD
CONFIRM
```

不得静默丢失修改。

---

# 97. Batch

MIDAS Model Operations 支持 StructAI Batch：

```json
{
  "items": [
    {
      "id": 1,
      "x": 0,
      "y": 0,
      "z": 0
    },
    {
      "id": 2,
      "x": 0,
      "y": 0,
      "z": 6
    }
  ]
}
```

Batch 需要明确：

```text
ATOMIC
NON_ATOMIC
```

如果 MIDAS 本身没有事务：

```text
StructAI cannot falsely claim atomicity
```

---

# 98. Dry Run

支持：

```text
BUILD
ASSIGN
DELETE
DESIGN
OPTIMIZE
```

dry-run 返回：

```json
{
  "mode": "DRY_RUN",
  "changes": [
    {
      "resource": "NODE",
      "action": "CREATE",
      "id": 100
    }
  ]
}
```

不调用会产生副作用的 native API。

---

# 99. Preconditions

Operation 可以声明：

```python
@dataclass(frozen=True)
class MidasPrecondition:
    name: str
    description: str
```

例如：

```text
DOCUMENT_OPEN
MODEL_EXISTS
NODE_EXISTS
ELEMENT_EXISTS
ANALYSIS_IDLE
NO_WRITE_LOCK
```

---

# 100. Postconditions

例如：

```text
NODE.CREATE
    → node exists

NODE.DELETE
    → node absent

ANALYSIS.STATIC
    → analysis status complete

RESULT.NODE.DISPLACEMENT
    → result exists
```

---

# 101. Native Schema Validation

使用：

```text
JSON Schema Draft 2020-12
```

流程：

```text
Canonical Schema
 ↓
Engineering Validation
 ↓
Native Transformer
 ↓
MIDAS JSON Schema
 ↓
HTTP
```

---

# 102. Transformer 设计

推荐：

```text
transformers/
├── node.py
├── element.py
├── material.py
├── section.py
├── boundary.py
├── load.py
├── analysis.py
├── result.py
├── view.py
└── design.py
```

版本：

```text
node_v1.py
node_v2.py
```

---

# 103. Transformer Registry

```python
class TransformerRegistry:
    def register(
        self,
        name: str,
        transformer,
    ):
        ...

    def resolve(
        self,
        name: str,
    ):
        ...
```

数据库只保存：

```text
midas.node.v1
```

代码负责实现。

---

# 104. Adapter 文件结构

推荐：

```text
app/infrastructure/adapters/midas/
├── __init__.py
├── adapter.py
├── base.py
├── manifest.py
├── client.py
├── health.py
├── capabilities.py
├── registry.py
├── errors.py
├── recovery.py
├── reconcile.py
├── models.py
├── schemas/
│   ├── civil/
│   └── gen/
├── transformers/
│   ├── node.py
│   ├── element.py
│   ├── material.py
│   ├── section.py
│   ├── boundary.py
│   ├── load.py
│   ├── analysis.py
│   ├── result.py
│   ├── view.py
│   └── design.py
├── products/
│   ├── civil.py
│   └── gen.py
└── tests/
    ├── contract/
    ├── integration/
    ├── e2e/
    └── fixtures/
```

---

# 105. Registry Seed 文件结构

```text
schemas/
└── midas/
    ├── civil/
    │   ├── 2025/
    │   └── 2026/
    └── gen/
        ├── 2025/
        └── 2026/

registry/
└── midas/
    ├── civil_2025.json
    ├── civil_2026.json
    ├── gen_2025.json
    └── gen_2026.json
```

---

# 106. Seed Loader

```python
class MidasRegistrySeeder:
    async def seed(self):
        sources = self.load_sources()
        endpoints = self.load_endpoints()
        schemas = self.load_schemas()

        await self.insert_sources(sources)
        await self.insert_schemas(schemas)
        await self.insert_endpoints(endpoints)
```

必须：

```text
idempotent
```

---

# 107. Seed Integrity

每个 seed：

```text
schema hash
source hash
version
generated_at
generator_version
```

---

# 108. Registry Import

支持：

```text
manual JSON
official manual extraction
verified live capture
```

流程：

```text
Raw Source
 ↓
Parser
 ↓
Normalized Registry
 ↓
Human Review
 ↓
Contract Test
 ↓
VERIFIED
```

---

# 109. 自动导入原则

不要做：

```text
网页 HTML
 ↓
自动猜字段
 ↓
直接 production
```

应该：

```text
网页/JSON
 ↓
Extract
 ↓
Candidate
 ↓
Review
 ↓
Test
 ↓
Verified
```

---

# 110. API Source Provenance

每个 registry entry 至少：

```text
source_url
source_title
source_revision
retrieved_at
source_hash
```

这样未来可以回答：

> 这个 API 映射从哪里来的？

---

# 111. Registry Integrity Check

启动时：

```text
registry load
 ↓
schema hash check
 ↓
duplicate check
 ↓
version check
 ↓
operation mapping check
 ↓
transformer existence check
```

如果 production mapping：

```text
VERIFIED
```

但 transformer 不存在：

```text
FAIL FAST
```

---

# 112. Mock Adapter

虽然本文聚焦 MIDAS，但 MIDAS 开发必须继续支持：

```text
MockAdapter
```

用于：

```text
Core tests
Tool tests
Task tests
Recovery tests
MCP E2E
```

真实 MIDAS 只用于：

```text
Contract
Integration
E2E
```

---

# 113. Mock 与真实 MIDAS 的边界

Mock：

```text
测试逻辑
```

不代表：

```text
MIDAS engineering correctness
```

不得用 Mock 证明：

```text
MIDAS API schema 正确
MIDAS analysis 正确
MIDAS design 正确
```

---

# 114. Production Configuration

示例：

```yaml
midas:
  enabled: true

  request:
    connect_timeout: 5
    read_timeout: 30
    write_timeout: 30

  analysis:
    timeout: 3600
    poll_interval: 2

  retry:
    max_attempts: 2

  concurrency:
    mode: SERIAL
```

实际值必须通过压测确定。

---

# 115. Secret Configuration

```yaml
midas:
  base_url: "http://..."
  secret_ref: "secret://midas/instance/001/mapi-key"
```

而不是：

```yaml
mapi_key: "xxxx"
```

---

# 116. Instance Registry

```text
software_instances
```

字段：

```text
instance_id
tenant_id
vendor
product
version
base_url
credential_ref
status
concurrency_mode
last_health_check
```

---

# 117. Instance Lifecycle

```text
REGISTERED
CONNECTING
CONNECTED
DEGRADED
DISCONNECTED
ERROR
DISABLED
```

---

# 118. Adapter Lifecycle

```text
REGISTER
 ↓
LOAD
 ↓
VALIDATE
 ↓
CONNECT
 ↓
VERSION DETECT
 ↓
CAPABILITY DETECT
 ↓
READY
```

断线：

```text
READY
 ↓
DISCONNECTED
 ↓
RECONNECTING
 ↓
READY
```

---

# 119. Cancellation

Analysis：

```text
Task.cancel()
```

映射：

```text
Adapter.cancel()
```

如果 MIDAS native API 没有可靠取消能力：

```text
CANCEL_REQUESTED
```

不能假装：

```text
CANCELLED
```

最终状态必须通过 reconciliation 确认。

---

# 120. Task Recovery

Task Engine：

```text
TASK
 ↓
MIDAS operation
 ↓
unknown
```

Adapter：

```text
reconcile
```

最终：

```text
COMPLETED
FAILED
MANUAL_REVIEW
```

---

# 121. API Contract Failure

例如 Registry：

```text
POST /doc/ANAL
```

实际：

```text
400
```

则：

```text
do not retry blindly
```

记录：

```text
STRUCTAI-2200
```

同时：

```text
contract_status = FAILED
```

---

# 122. Registry Auto-Disable

如果连续发现：

```text
VERIFIED API
    ↓
production failure
```

建议：

```text
circuit breaker
```

状态：

```text
ACTIVE
DEGRADED
OPEN
```

但不得因为一次 transient failure 就永久禁用。

---

# 123. Circuit Breaker

适用：

```text
connection failure
5xx
timeout
```

不适用：

```text
business validation error
invalid model
bad user input
```

---

# 124. Performance

目标不是单纯追求 HTTP TPS，而是：

```text
MCP latency
+
Core latency
+
Adapter latency
+
MIDAS response
```

Metrics：

```text
midas_request_total
midas_request_duration_seconds
midas_request_error_total
midas_analysis_duration_seconds
midas_reconcile_total
midas_reconcile_duration_seconds
```

---

# 125. Metrics Labels

允许：

```text
product
version
operation
method
status
```

避免高基数：

```text
node_id
element_id
user-generated id
trace_id
```

不要直接作为 Prometheus label。

---

# 126. Security

MIDAS API Key：

```text
CredentialProvider
```

RBAC：

```text
Core
```

因此：

```text
AI
 ↓
RBAC
 ↓
MCP Tool
 ↓
MIDAS Adapter
```

不能：

```text
AI
 ↓
Adapter
```

绕过 Core。

---

# 127. Tenant Isolation

每个：

```text
MIDAS Instance
```

必须归属：

```text
tenant
```

Project：

```text
tenant
 ↓
project
 ↓
software instance/model
```

禁止跨 tenant 使用。

---

# 128. Audit Example

```json
{
  "action": "ANALYSIS.STATIC",
  "software": "MIDAS",
  "product": "CIVIL NX",
  "version": "2026",
  "result": "COMPLETED",
  "task_id": "task_001"
}
```

---

# 129. Full Execution Sequence

```text
MCP Request
 ↓
Authentication
 ↓
IdentityContext
 ↓
ExecutionContext
 ↓
Tool Resolution
 ↓
Operation Resolution
 ↓
Software Instance Resolution
 ↓
Schema Validation
 ↓
Engineering Validation
 ↓
Permission
 ↓
Quota
 ↓
Confirmation
 ↓
Idempotency
 ↓
Lock
 ↓
Capability
 ↓
Task
 ↓
MIDAS Adapter
 ↓
API Registry
 ↓
Transformer
 ↓
MIDAS HTTP
 ↓
MIDAS API Server
 ↓
CIVIL/GEN
 ↓
Native Response
 ↓
Transformer
 ↓
Canonical Result
 ↓
Postcondition
 ↓
Unlock
 ↓
Persist
 ↓
Audit
 ↓
Trace
 ↓
Event
 ↓
MCP Response
```

---

# 130. Source-Level Operation Resolver

```python
class MidasOperationExecutor:

    async def execute(
        self,
        operation: str,
        parameters: dict,
        context,
    ):
        mapping = await self.registry.resolve(
            product=context.software.product,
            version=context.software.version,
            operation=operation,
        )

        if mapping is None:
            raise CapabilityNotSupported(operation)

        if mapping.verification_status != "VERIFIED":
            raise RegistryMappingNotVerified(operation)

        transformer = self.transformers.resolve(
            mapping.transformer
        )

        request = transformer.to_native(
            parameters,
            mapping,
        )

        response = await self.client.request(
            method=mapping.method,
            path=mapping.path,
            json=request,
        )

        return transformer.from_native(
            response,
            mapping,
        )
```

---

# 131. 不允许巨大 if/elif

禁止：

```python
if operation == "MODEL.NODE.CREATE":
    ...
elif operation == "MODEL.ELEMENT.CREATE":
    ...
elif operation == "ANALYSIS.STATIC":
    ...
```

原因：

```text
版本增长
产品增长
endpoint 增长
代码会爆炸
```

应该：

```text
operation
 ↓
registry
 ↓
mapping
 ↓
transformer
```

---

# 132. Canonical Model 与 Native Model

必须保持：

```text
Canonical Model
```

稳定。

例如：

```text
Node
Element
Material
Section
Boundary
Load
Result
```

MIDAS schema 可以：

```text
2025
2026
2027
```

变化。

这样未来：

```text
ETABS
SAP2000
ANSYS
```

不会改变 Core。

---

# 133. MIDAS API Schema 不外泄

MCP Tool schema 应是：

```text
StructAI Canonical Schema
```

而不是：

```text
MIDAS raw JSON schema
```

AI 不应该需要知道：

```text
Assign
NODE ID
MIDAS-specific nested keys
```

除非进入：

```text
engineering raw/debug
```

专门的管理能力。

---

# 134. Raw API Debug

可提供内部 Admin API：

```text
/api/admin/midas/request-test
```

但：

```text
不是 MCP Tool
```

需要：

```text
SYSTEM_ADMIN
或
API_TEST
```

---

# 135. Real MIDAS Debug Workflow

```text
Get Object
 ↓
inspect JSON
 ↓
modify
 ↓
PUT/POST
 ↓
GET
 ↓
compare
 ↓
record fixture
 ↓
Schema
 ↓
Registry
 ↓
Contract Test
```

MIDAS 官方也建议通过 GET 获取 JSON，再根据需要调整并用 PUT/POST 写入，这是开发期验证 DB JSON 结构的有效方式。citeturn0search11

---

# 136. Node Contract Test Example

```python
async def test_node_get(live_midas):
    result = await live_midas.get("/db/NODE")

    assert result.status_code == 200
    assert isinstance(result.json(), dict)
```

不要仅测试 HTTP：

```text
必须验证 JSON schema
```

---

# 137. Node Create Contract Test

流程：

```text
GET existing nodes
 ↓
select unused ID
 ↓
POST
 ↓
GET
 ↓
assert exists
 ↓
DELETE
 ↓
GET
 ↓
assert absent
```

这样可以验证完整 CRUD。

---

# 138. Analysis Contract Test

必须：

```text
prepare test model
 ↓
run analysis
 ↓
wait/poll
 ↓
verify status
 ↓
query result
 ↓
verify schema
```

禁止：

```text
POST
 ↓
sleep(10)
 ↓
assume complete
```

---

# 139. Result Contract Test

必须验证：

```text
field exists
type correct
unit correct if exposed
node/element references valid
```

---

# 140. Design Contract Test

至少：

```text
design config
 ↓
execute
 ↓
result available
 ↓
utilization parsed
 ↓
status parsed
```

如果官方接口尚未确认执行路径：

```text
Registry = PARTIAL
```

不能写：

```text
VERIFIED
```

---

# 141. View Contract Test

```text
SELECT
DISPLAY
RESULTGRAPHIC
CAPTURE
```

验证：

```text
HTTP
image/json
artifact
```

---

# 142. CIVIL E2E 测试矩阵

| 功能 | Mock | Contract | Live E2E |
|---|---:|---:|---:|
| Connect | ✓ | ✓ | ✓ |
| Health | ✓ | ✓ | ✓ |
| Version | ✓ | ✓ | ✓ |
| Node Query | ✓ | ✓ | ✓ |
| Node Create | ✓ | ✓ | ✓ |
| Node Delete | ✓ | ✓ | ✓ |
| Element | ✓ | ✓ | ✓ |
| Material | ✓ | ✓ | ✓ |
| Section | ✓ | ✓ | ✓ |
| Boundary | ✓ | ✓ | ✓ |
| Load | ✓ | ✓ | ✓ |
| Analysis | ✓ | ✓ | ✓ |
| Result | ✓ | ✓ | ✓ |
| View | ✓ | ✓ | ✓ |
| Design | ✓ | ✓ | ✓ |
| Recovery | ✓ | ✓ | ✓ |

---

# 143. GEN E2E 测试矩阵

与 CIVIL 相同的 Core contract：

```text
Connect
Health
Version
Model
Analysis
Result
Design
```

但所有 native mapping 都从：

```text
product = GEN NX
```

解析。

---

# 144. Recovery Test Matrix

必须测试：

```text
connection lost before request
connection lost after request
timeout
5xx
MIDAS closed
MIDAS restarted
API key invalid
model closed
analysis running
analysis unknown
partial build
duplicate request
task worker crash
Core restart
```

---

# 145. Core Restart Recovery

```text
Core crash
 ↓
startup
 ↓
load unfinished tasks
 ↓
check lease
 ↓
RECOVERING
 ↓
MIDAS health
 ↓
reconcile
 ↓
resume/requeue/manual
```

---

# 146. MIDAS Closed Recovery

如果：

```text
MIDAS process closed
```

任务：

```text
RUNNING
```

应转：

```text
RECOVERING
```

然后：

```text
software unavailable
```

最终：

```text
FAILED
```

或：

```text
RESUME
```

取决于 operation。

---

# 147. API Key Refresh

MAPI-Key 可以被刷新。

因此：

```text
CredentialProvider
 ↓
new secret
 ↓
invalidate connection
 ↓
reconnect
 ↓
health
```

不能要求：

```text
重启 StructAI
```

---

# 148. API Key Failure

如果：

```text
401 / unauthorized
```

不要 retry 无限次。

应：

```text
AUTH_ERROR
 ↓
mark adapter degraded
 ↓
request credential refresh
```

---

# 149. Adapter Production Checklist

```text
[ ] HTTP Client
[ ] Credential Provider
[ ] Registry
[ ] Schema
[ ] Transformer
[ ] Capability
[ ] Version
[ ] Health
[ ] Error normalization
[ ] Recovery
[ ] Reconcile
[ ] Lock
[ ] Timeout
[ ] Retry
[ ] Circuit breaker
[ ] Metrics
[ ] Trace
[ ] Audit
[ ] Contract test
[ ] E2E
```

---

# 150. MIDAS Adapter Definition of Done

## Registry

```text
[ ] DOC Registry
[ ] DB Registry
[ ] OPE Registry
[ ] VIEW Registry
[ ] POST Registry
[ ] Version
[ ] Source
[ ] Schema
[ ] Verification
```

## Model

```text
[ ] Node
[ ] Element
[ ] Material
[ ] Section
[ ] Boundary
[ ] Load
```

## Analysis

```text
[ ] Static
[ ] Modal
[ ] Seismic
[ ] Spectrum
[ ] Buckling
[ ] Time History
[ ] Nonlinear
```

具体支持情况必须以版本 Capability 为准。

## Result

```text
[ ] Displacement
[ ] Reaction
[ ] Element Force
[ ] Stress
[ ] Mode Shape
[ ] Analysis Summary
```

## Design

```text
[ ] Steel
[ ] Concrete
[ ] Foundation
[ ] Code Check
[ ] Optimization
```

执行路径必须经过官方验证。

---

# 151. Production Hardening Definition of Done

```text
[ ] Connection pool
[ ] Timeout
[ ] Retry
[ ] Circuit breaker
[ ] Rate limit
[ ] Concurrency
[ ] Resource lock
[ ] Credential rotation
[ ] Secret redaction
[ ] Structured logging
[ ] Metrics
[ ] Trace
[ ] Audit
[ ] Recovery
[ ] Reconcile
[ ] Contract test
[ ] E2E
[ ] Backup
[ ] Version migration
```

---

# 152. 最终代码结构

```text
app/
└── infrastructure/
    └── adapters/
        └── midas/
            ├── __init__.py
            ├── adapter.py
            ├── base.py
            ├── client.py
            ├── manifest.py
            ├── registry.py
            ├── capabilities.py
            ├── health.py
            ├── errors.py
            ├── recovery.py
            ├── reconcile.py
            ├── lifecycle.py
            ├── products/
            │   ├── civil.py
            │   └── gen.py
            ├── transformers/
            │   ├── node.py
            │   ├── element.py
            │   ├── material.py
            │   ├── section.py
            │   ├── boundary.py
            │   ├── load.py
            │   ├── analysis.py
            │   ├── result.py
            │   ├── view.py
            │   └── design.py
            ├── schemas/
            │   ├── civil/
            │   └── gen/
            └── tests/
                ├── contract/
                ├── integration/
                ├── e2e/
                ├── recovery/
                └── fixtures/
```

---

# 153. 与 Core 的最终边界

```text
Core
├── MCP
├── Authentication
├── RBAC
├── Tenant
├── Project
├── Task
├── Lock
├── Idempotency
├── Audit
├── Trace
├── Metrics
├── Artifact
└── Adapter Manager

MIDAS Adapter
├── MIDAS connection
├── MIDAS version
├── MIDAS capability
├── MIDAS registry
├── MIDAS schema
├── MIDAS transformer
├── MIDAS execution
├── MIDAS result parsing
├── MIDAS recovery
└── MIDAS version compatibility
```

---

# 154. 第二个软件接入原则

接入 ETABS/SAP2000 时：

不应该修改：

```text
9 MCP Tools
Task Engine
RBAC
MCP Session
Core Execution Pipeline
```

只增加：

```text
Adapter
Registry
Schema
Transformer
Capability Mapping
Contract Test
```

如果第二个软件迫使修改：

```text
9 MCP Tool Contract
```

说明抽象层设计出现问题。

---

# 155. 最终 AI 调用示例

用户：

> 创建一个 6m 高的 Q355B H400×400×13×21 钢柱，底部固定，顶部施加 500kN 轴压力，进行静力分析并返回顶部位移和钢柱利用率。

AI 不应该生成：

```text
POST /db/NODE
POST /db/ELEM
...
```

AI 应调用：

```text
engineering_model_build
engineering_model_assign
engineering_analysis
engineering_result
engineering_design
```

---

# 156. 最终内部调用

```text
engineering_model_build
    operation = BUILD.COLUMN

engineering_model_assign
    operation = MODEL.LOAD.ASSIGN

engineering_analysis
    operation = ANALYSIS.STATIC

engineering_result
    operation = RESULT.NODE.DISPLACEMENT

engineering_design
    operation = DESIGN.STEEL
```

然后：

```text
Capability
 ↓
MIDAS Registry
 ↓
Transformer
 ↓
Native API
```

---

# 157. 最终验收场景

必须实现：

```text
AI Client
 ↓
MCP Connect
 ↓
tools/list
 ↓
capability discovery
 ↓
engineering_model_build
 ↓
Task
 ↓
MIDAS
 ↓
Analysis
 ↓
Result
 ↓
Design
 ↓
MCP Response
```

同时验证：

```text
Audit
Trace
Metrics
Task
Recovery
```

---

# 158. 最终工程原则

### 原则 1

```text
Core 不认识 MIDAS endpoint
```

### 原则 2

```text
Tool 不认识 MIDAS endpoint
```

### 原则 3

```text
Operation 不认识 MIDAS endpoint
```

### 原则 4

```text
Adapter Registry 认识 MIDAS endpoint
```

### 原则 5

```text
Transformer 认识 MIDAS JSON
```

### 原则 6

```text
只有 VERIFIED Mapping 才能进入生产执行
```

### 原则 7

```text
未知执行结果必须 Reconcile
```

### 原则 8

```text
AI 永远不能绕过 Core Security
```

### 原则 9

```text
MIDAS 版本差异必须由 Registry/Adapter 吸收
```

### 原则 10

```text
Canonical Model 必须保持软件无关
```

---

# 159. 官方资料基线

本实现规范应持续以以下官方资料为依据：

1. MIDAS API Online Manual  
   https://support.midasuser.com/hc/en-us/articles/33016922742937-MIDAS-API-Online-Manual

2. API Settings  
   https://support.midasuser.com/hc/en-us/articles/27745256204057-API-Settings

3. Base URL and API-KEY  
   https://support.midasuser.com/hc/en-us/articles/30508934444569-Base-URL-and-API-KEY

4. How to integrate CIVIL NX or GEN NX  
   https://support.midasuser.com/hc/en-us/articles/45625180842009-How-can-I-integrate-it-with-CIVIL-NX-or-GEN-NX

5. Get Object  
   https://support.midasuser.com/hc/en-us/articles/32836940545177-Get-Object

6. Node  
   https://support.midasuser.com/hc/en-us/articles/32838911436697-Node

7. Easyway to use the baseURL/DB  
   https://support.midasuser.com/hc/en-us/articles/30512265484569-Easyway-to-use-the-baseURL-DB

8. MIDAS CIVIL NX Open API  
   https://support.midasuser.com/hc/en-us/articles/30130748041369-How-to-use-MIDAS-CIVIL-NX-Open-API

官方 API Manual 当前页面说明其内容适用于 MIDAS NX 系列，包括 CIVIL NX 与 GEN NX，并明确给出 endpoint、method、JSON structure 和 examples。citeturn0search0

---

# 160. 当前明确可作为 Registry 基线的官方事实

```text
RESTful API
CIVIL NX + GEN NX
DOC / DB / OPE / VIEW / POST
MAPI-Key
Base URL
/doc/NEW
/doc/OPEN
/doc/CLOSE
/doc/SAVE
/doc/SAVEAS
/doc/STAGAS
/doc/IMPORT
/doc/IMPORTMXT
/doc/EXPORT
/doc/EXPORTMXT
/doc/ANAL
/db/NODE
/db/ELEM
/db/MATL
/db/SECT
/ope/PROJECTSTATUS
/view/CAPTURE
```

以上只是**官方文档中已确认的 Registry 基础事实**。

对于具体 JSON：

```text
不要猜
不要根据旧代码补
不要根据 endpoint 名称推断
```

必须进入：

```text
官方 endpoint 页面
 ↓
request schema
 ↓
response schema
 ↓
live contract test
```

---

# 161. 下一阶段实现顺序

MIDAS Adapter 的真正开发顺序：

```text
01 MIDAS HTTP Client
02 Credential Provider
03 Instance Registry
04 API Registry
05 Schema Registry
06 Registry Resolver
07 Node Transformer
08 Element Transformer
09 Material Transformer
10 Section Transformer
11 Boundary Transformer
12 Load Transformer
13 Document Runtime
14 Analysis Runtime
15 Result Runtime
16 View Runtime
17 Design Runtime
18 Recovery
19 Reconcile
20 Contract Tests
21 CIVIL E2E
22 GEN Adapter
23 Multi-Version
24 Production Hardening
```

---

# 162. 最终完成标准

当以下全部满足时，MIDAS Adapter 才能从 Alpha 进入 Beta：

```text
[ ] CIVIL NX Adapter
[ ] GEN NX Adapter
[ ] API Registry
[ ] Schema Registry
[ ] Source Provenance
[ ] Version Resolver
[ ] Capability Resolver
[ ] HTTP Client
[ ] Secret Management
[ ] Node CRUD
[ ] Element CRUD
[ ] Material
[ ] Section
[ ] Boundary
[ ] Load
[ ] Document
[ ] Analysis
[ ] Result
[ ] View
[ ] Design
[ ] Recovery
[ ] Reconcile
[ ] Contract Test
[ ] CIVIL E2E
[ ] GEN E2E
[ ] Multi-Version
[ ] Timeout
[ ] Retry
[ ] Circuit Breaker
[ ] Rate Limit
[ ] Concurrency
[ ] Audit
[ ] Trace
[ ] Metrics
[ ] Security
[ ] Secret Redaction
[ ] Production Configuration
```

---

# 163. 本文与原 ⑰～㉛的对应关系

| 原文档 | 本文章节 |
|---|---|
| ⑰ Adapter Runtime | 2～7、104～118 |
| ⑱ API Registry | 7～19、105～111 |
| ⑲ Node / Element | 20～26 |
| ⑳ Material / Section | 27～30 |
| ㉑ Boundary / Load | 31～34 |
| ㉒ Analysis | 35～41 |
| ㉓ Result | 42～47 |
| ㉔ View | 48～51 |
| ㉕ Design | 52～55、140 |
| ㉖ Recovery / Reconcile | 56～60、145～148 |
| ㉗ Contract Test | 69～72、136～140 |
| ㉘ CIVIL E2E | 73～75、137～142 |
| ㉙ GEN NX | 76～77、143 |
| ㉚ Multi-Version | 61～68、78～80 |
| ㉛ Production Hardening | 81～91、123～131、144～150 |

因此，本次合并不是删除原内容，而是把原 ⑰～㉛的实施内容集中到一份主规范中。

---

# 164. 最终结论

StructAI MCP V2.0 的 MIDAS 接入最终采用：

```text
                    StructAI Core
                         │
                 9 MCP Tools
                         │
                 Operation Layer
                         │
                Capability Resolver
                         │
                 Adapter Manager
                         │
              ┌──────────┴──────────┐
              │                     │
        MIDAS Adapter          Future Adapter
              │
       ┌──────┴──────┐
       │             │
   CIVIL NX       GEN NX
       │             │
       └──────┬──────┘
              │
        API Registry
              │
        Schema Registry
              │
        Transformer
              │
        Midas HTTP Client
              │
          MAPI-Key
              │
        MIDAS API Server
              │
       Engineering Software
```

最终抽象保持：

```text
MCP Tool
    ↓
Operation
    ↓
Capability
    ↓
Adapter
    ↓
Registry
    ↓
Transformer
    ↓
Native API
```

这套结构既可以支持当前：

```text
MIDAS CIVIL NX
MIDAS GEN NX
```

也为后续：

```text
ETABS
SAP2000
ANSYS
ABAQUS
OpenSees
```

保留统一 Adapter SDK。

**本文件即作为原 ⑰～㉛合并后的 MIDAS 主实现规范。**



# 来源映射

- `source9`：完整收录。
- `sec`：完整收录。
- `exec`：完整收录。
- `task`：完整收录。
- `adapter`：完整收录。
- `artifact`：完整收录。
- `tools15`：完整收录。
- `trans16`：完整收录。
- `midasall`：完整收录。
