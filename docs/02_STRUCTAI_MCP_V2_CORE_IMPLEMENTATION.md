# 02_STRUCTAI_MCP_V2_CORE_IMPLEMENTATION.md — Core 源码级完整实现

V2.0 Consolidated Core Alpha Source Specification。覆盖项目 Bootstrap、Domain、Database、Repository、UnitOfWork、Registry、Security、Execution Pipeline、Task Engine、Adapter Manager、Artifact、Document、Event、Audit、Trace、Metrics、Health、Backup/Restore、Recovery、测试与文件级实现。

---

# 内容保全说明

本主文档按六文档体系重新组织。**原有内容不删除**；各来源规范以完整原文收录在对应章节，确保代码、字段、状态、测试要求和实现约束均可追溯。


# 完整收录：impl

# StructAI MCP Server V2.0
## Core Implementation Specification — Revision V2

**Document:** `StructAI_MCP_Server_V2.0_Core_Implementation_Specification_Revision_V2.md`  
**Version:** 2.0 Revision V2  
**Status:** Core Alpha Implementation Baseline  
**Target:** Python 3.12+

---

# 1. 修订说明

本文件是原《Core Implementation Specification》的正式 Revision V2。

目标不是重新定义产品，而是把前三份设计与最终冻结的 Core Python Revision V2 统一到一个可实施的代码级规范。

本版本必须实现：

```text
Authentication / Session
IdentityContext
Multi-Tenant
RBAC / Effective Permission
Resource Resolver
Schema Engine
Engineering Validation
Capability Resolver
Resource Lock
Optimistic Concurrency
Atomic Idempotency
Task Engine
Task DAG
Task Lease / Recovery
Adapter Plugin Loader
API Registry / Version Resolver
Artifact / Document
Pagination
Batch
Dry Run
Preconditions / Postconditions
Event Bus
Quota
Health / Metrics
Audit / Trace
Backup / Recovery
MCP SDK
STDIO
Streamable HTTP
9 MCP Tools
Generic MCP Client E2E
```

---

# 2. 技术基线

```text
Python >= 3.12
FastAPI
Pydantic v2
SQLAlchemy 2.x
aiosqlite
Alembic
httpx
jsonschema
structlog
pytest
pytest-asyncio
```

MCP 使用官方/成熟 Python SDK。

不得自行重新实现 MCP protocol。

---

# 3. 最终项目结构

```text
structai-mcp/
├── pyproject.toml
├── README.md
├── LICENSE
├── .env.example
├── .gitignore
├── app/
│   ├── main.py
│   ├── config/
│   │   ├── settings.py
│   │   ├── runtime_config.py
│   │   └── logging.py
│   ├── domain/
│   │   ├── enums.py
│   │   ├── entities.py
│   │   ├── value_objects.py
│   │   ├── errors.py
│   │   ├── events.py
│   │   └── protocols.py
│   ├── application/
│   │   ├── commands/
│   │   ├── queries/
│   │   ├── services/
│   │   ├── execution/
│   │   ├── task/
│   │   ├── security/
│   │   ├── resource/
│   │   └── dto/
│   ├── infrastructure/
│   │   ├── database/
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   ├── models/
│   │   │   ├── repositories/
│   │   │   └── migrations/
│   │   ├── registry/
│   │   ├── adapters/
│   │   │   ├── base/
│   │   │   ├── mock/
│   │   │   └── plugins/
│   │   ├── storage/
│   │   ├── secrets/
│   │   ├── events/
│   │   ├── notifications/
│   │   └── locks/
│   ├── interfaces/
│   │   ├── mcp/
│   │   │   ├── server.py
│   │   │   ├── context.py
│   │   │   ├── responses.py
│   │   │   └── tools/
│   │   ├── http/
│   │   │   ├── api.py
│   │   │   ├── health.py
│   │   │   └── management/
│   │   └── cli/
│   └── observability/
│       ├── tracing.py
│       ├── metrics.py
│       └── audit.py
├── schemas/
├── migrations/
├── scripts/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── recovery/
│   ├── security/
│   └── e2e/
└── docs/
```

依赖方向：

```text
Interface → Application → Domain
Infrastructure → Domain/Application Interfaces
```

禁止反向依赖。

---

# 4. Domain Enum

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

class LockMode(StrEnum):
    READ = "READ"
    WRITE = "WRITE"
    EXCLUSIVE = "EXCLUSIVE"
```

---

# 5. IdentityContext / ExecutionContext

身份必须由服务器生成：

```python
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
class ExecutionContext:
    request_id: str
    trace_id: str
    identity: IdentityContext
    software: SoftwareContext = field(default_factory=SoftwareContext)
    project: ProjectContext = field(default_factory=ProjectContext)
```

来源：

```text
Authentication
 ↓
AuthenticatedPrincipal
 ↓
IdentityContext
 ↓
ExecutionContext
```

客户端不得声明：

```text
user_id
tenant_id
roles
permissions
```

---

# 6. Authentication / Session

服务：

```text
AuthenticationService
PasswordService
SessionService
TokenService
```

密码：

```text
Argon2id
```

必须支持：

```text
login
logout
session expiry
session revoke
failed-login tracking
account lock
```

STDIO 可以使用：

```text
local trusted identity
```

但仍生成标准 IdentityContext。

---

# 7. Effective Permission

权限计算：

```text
User
 ↓
Global Roles
 ↓
Tenant Membership / Roles
 ↓
Project Membership / Roles
 ↓
Resource ACL
 ↓
Explicit Deny
 ↓
Effective Permissions
```

接口：

```python
class EffectivePermissionService:
    async def resolve(context, resource) -> set[str]: ...
    async def authorize(context, permission, resource) -> None: ...
```

AI Agent：

```text
Effective User Permissions
        ∩
Agent Permissions
        =
Effective Agent Permissions
```

---

# 8. Resource Resolver

```python
@dataclass(frozen=True)
class ResourceRef:
    resource_type: str
    resource_id: str
```

解析：

```text
Project
Model
Document
Software Instance
Task
Artifact
```

所有跨租户访问必须在 Resource Resolver 拦截。

---

# 9. Database / UnitOfWork

```python
AsyncEngine
AsyncSession
async_sessionmaker
```

Application：

```text
Application Service
 ↓
UnitOfWork
 ↓
Repository
 ↓
Commit
```

异常：

```text
Exception
 ↓
Rollback
```

Repository 不自行 commit。

---

# 10. Tool / Operation / Capability

## Tool

```python
@dataclass(frozen=True)
class ToolDefinition:
    name: str
    version: str
    category: str
    description: str
    risk_level: RiskLevel
    execution_mode: ExecutionMode
```

## Operation

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
    recovery_policy: str
```

## Capability

```python
@dataclass(frozen=True)
class CapabilityDefinition:
    code: str
    category: str
    name: str
    version: str = "1.0"
    description: str = ""
```

Capability 不允许出现：

```text
MIDAS
CSI
ANSYS
```

---

# 11. Registry

必须存在：

```text
ToolRegistry
OperationRegistry
CapabilityRegistry
SchemaRegistry
SoftwareRegistry
AdapterRegistry
APIRegistry
```

Tool 不自行寻找 Adapter。

---

# 12. Schema Engine

使用：

```text
JSON Schema Draft 2020-12
```

Schema URI：

```text
structai://schema/model/node/v1
structai://schema/model/node/v2
```

旧版本不可覆盖。

---

# 13. Validation Engine

严格顺序：

```text
Input
 ↓
Schema Validation
 ↓
Engineering Validation
 ↓
Permission
 ↓
Confirmation
 ↓
Capability
 ↓
Execution
```

完整 Pipeline：

```text
MCP Request
 ↓
Authenticate
 ↓
IdentityContext
 ↓
ExecutionContext
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
Preconditions
 ↓
Effective Permission
 ↓
Quota
 ↓
Confirmation
 ↓
Idempotency
 ↓
Concurrency / Resource Lock
 ↓
Capability
 ↓
Task / Transaction
 ↓
Adapter
 ↓
Result Normalization
 ↓
Postconditions
 ↓
Release Lock
 ↓
Persist Result
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

# 14. Preconditions / Postconditions

OperationDefinition 必须支持：

```text
preconditions
postconditions
```

示例：

```text
ANALYSIS.STATIC
preconditions:
  - model_open
  - valid_load_cases
  - required_capability

postconditions:
  - task_completed
  - result_available
```

---

# 15. Resource Lock

```python
class ResourceLockManager:
    async def acquire(...): ...
    async def release(...): ...
    async def refresh(...): ...
```

兼容矩阵：

```text
READ + READ = allowed
READ + WRITE = blocked
WRITE + WRITE = blocked
EXCLUSIVE = blocks all
```

锁必须与 Task 生命周期关联。

---

# 16. Optimistic Concurrency

资源拥有：

```text
version
```

更新携带：

```text
expected_version
```

数据库：

```sql
UPDATE resource
SET version = version + 1
WHERE id = :id
  AND version = :expected_version
```

0 rows affected：

```text
STRUCTAI-1300
```

---

# 17. Task Engine

状态：

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

Task 支持：

```text
sequential
parallel
dependency
retry
timeout
cancel
resume
recovery
priority
lease
heartbeat
```

---

# 18. Task Lease / Recovery

Task Lease：

```python
lease_owner
lease_until
last_heartbeat
```

重启：

```text
unfinished tasks
 ↓
inspect lease
 ↓
RECOVERING
 ↓
REQUEUE / RESUME / FAIL
```

不能把恢复中的 Task 直接标记为 COMPLETED。

---

# 19. Task DAG

```text
Task
 ├── Step A
 ├── Step B
 ├── Step C → A
 └── Step D → B,C
```

循环依赖必须在提交前拒绝。

---

# 20. Task Priority / Concurrency

优先级：

```text
CRITICAL
HIGH
NORMAL
LOW
```

软件实例：

```text
SERIAL
LIMITED
PARALLEL
```

桌面工程软件默认：

```text
SERIAL
```

---

# 21. Adapter Interface

```python
class EngineeringSoftwareAdapter(ABC):
    name: str
    vendor: str
    product: str

    async def connect(self, config: dict) -> None: ...
    async def disconnect(self) -> None: ...
    async def health_check(self) -> dict: ...
    async def get_version(self) -> str: ...
    async def get_capabilities(self) -> list[str]: ...
    async def execute(
        self,
        operation: str,
        parameters: dict,
        context: ExecutionContext,
    ) -> dict: ...
    async def cancel(self, task_id: str) -> None: ...
    async def normalize_error(self, error: Exception) -> dict: ...
```

---

# 22. Adapter Plugin Loader

使用 Python Entry Points：

```toml
[project.entry-points."structai.adapters"]
midas.civil = "structai_midas.adapter:CivilAdapter"
```

Adapter Manifest：

```json
{
  "name": "midas.civil",
  "vendor": "MIDAS",
  "product": "CIVIL NX",
  "supported_versions": ["2025", "2026"],
  "capabilities": [],
  "protocols": ["REST"]
}
```

禁止从数据库执行任意 Python。

---

# 23. Software Instance Lifecycle

```text
DISCONNECTED
CONNECTING
CONNECTED
DEGRADED
RECONNECTING
UNAVAILABLE
```

健康检查：

```python
async def health_check() -> dict:
    ...
```

一个实例失败不能让整个 Server Not Ready。

---

# 24. API Registry / Version Resolver

Resolver 输入：

```text
software instance
operation
```

输出：

```text
adapter
API mapping
protocol
native operation
transform
timeout
retry policy
```

支持：

```text
exact version
version range
fallback
deprecated mapping
```

复杂 request/response transformer 必须位于 Adapter package。

---

# 25. Capability Cache

缓存：

```text
instance
version
capability
support_level
checked_at
expires_at
```

刷新：

```text
reconnect
version change
adapter change
manual refresh
expiry
```

---

# 26. Secret / Credential Provider

```python
class CredentialProvider(Protocol):
    async def get_secret(reference: str) -> str: ...
    async def set_secret(reference: str, value: str) -> None: ...
    async def delete_secret(reference: str) -> None: ...
```

第一阶段：

```text
EnvironmentCredentialProvider
```

未来：

```text
OS Credential Store
Vault
KMS
```

绝不记录 secret。

---

# 27. Batch / Dry Run

Tool Request：

```python
class ToolRequest(BaseModel):
    operation: str
    parameters: dict = {}
    context: dict = {}
    idempotency_key: str | None = None
    confirmation_token: str | None = None
    dry_run: bool = False
```

Context 中的身份不能覆盖服务器 IdentityContext。

Batch：

```json
{
  "items": [{}, {}, {}],
  "atomic": true
}
```

---

# 28. Atomic Idempotency

唯一键：

```text
tenant_id + idempotency_key
```

必须：

```text
atomic INSERT
```

而不是：

```text
SELECT
INSERT
```

重复请求必须返回已有 Task/Response。

---

# 29. Artifact Storage

```python
class ArtifactStorage(Protocol):
    async def put(...): ...
    async def get(...): ...
    async def delete(...): ...
```

第一阶段：

```text
LocalFilesystemStorage
```

数据库保存 metadata。

---

# 30. Document Service

生命周期：

```text
NEW
OPEN
SAVE
SAVE_AS
CLOSE
INFO
```

Document Service 调用：

```text
ArtifactService
Adapter
```

而不是直接操作 MCP transport。

---

# 31. Pagination

所有可能产生大量数据的 Query/Result 必须分页。

```json
{
  "data": [],
  "pagination": {
    "has_more": true,
    "next_cursor": "opaque-cursor"
  }
}
```

禁止无限 payload。

---

# 32. Canonical Engineering Model

Core Canonical entities：

```text
Node
Element
Material
Section
Boundary
Load
Group
Analysis
Result
Design
```

Adapter 可以将软件原生结构转换成 Canonical Model。

---

# 33. Result Normalization

例如：

```json
{
  "node_id": 100,
  "ux": 0.001,
  "uy": 0.002,
  "uz": -0.015
}
```

AI Client 不应该依赖 MIDAS 原始字段。

---

# 34. Event Bus

```python
class EventBus(Protocol):
    async def publish(self, event): ...
    async def subscribe(self, event_type, handler): ...
```

Core Alpha：

```text
InProcessEventBus
```

事件：

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
```

---

# 35. Notification Extension

支持未来：

```text
MCP Notification
Webhook
WebSocket
UI
Email
```

Notification 不成为 Core Tool。

---

# 36. Quota / Rate Limit

至少：

```text
max_tasks
max_concurrent_tasks
max_api_requests
max_storage
max_projects
```

维度：

```text
user
tenant
AI agent
software instance
```

Core Alpha 可使用内存 limiter + DB quota definition。

---

# 37. Health / Metrics

```text
/livez
/readyz
/health
```

Metrics：

```text
structai_requests_total
structai_request_duration_seconds
structai_task_total
structai_task_duration_seconds
structai_task_failed_total
structai_adapter_requests_total
structai_adapter_errors_total
structai_active_tasks
structai_mcp_connections
```

---

# 38. Runtime Configuration

配置至少：

```text
environment
host
port
database_url
log_level
task_workers
task_timeout
mcp_transport
artifact_root
retention
quota
```

Secret 不进入普通 settings。

---

# 39. Audit Integrity

Audit 字段：

```text
audit_id
timestamp
tenant_id
user_id
action
resource
result
previous_hash
entry_hash
```

计算：

```text
entry_hash =
H(previous_hash + canonical_entry)
```

高风险操作必须 Audit。

---

# 40. Data Retention

配置：

```text
task_retention_days
trace_retention_days
audit_retention_days
artifact_retention_days
session_retention_days
event_retention_days
```

删除必须服从审计与法规策略。

---

# 41. Backup / Restore

Core Alpha：

```text
SQLite backup
+
Artifact metadata
+
Registry data
```

恢复后：

```text
integrity-check
 ↓
migration validation
 ↓
registry validation
 ↓
runtime health
```

---

# 42. Migration Safety

所有结构变更：

```text
Alembic migration
```

禁止：

```text
启动时静默 ALTER TABLE
```

Migration 必须：

```text
versioned
checksum
tested
rollback strategy documented
```

---

# 43. Unified Error Contract

```text
STRUCTAI-1000 Protocol Error
STRUCTAI-1100 Schema Validation Error
STRUCTAI-1200 Engineering Validation Error
STRUCTAI-1300 Concurrency Conflict
STRUCTAI-2000 Software Connection Error
STRUCTAI-2100 Software Authentication Error
STRUCTAI-2200 Software API Error
STRUCTAI-2300 Software Timeout
STRUCTAI-3000 Capability Not Supported
STRUCTAI-4000 Permission Denied
STRUCTAI-4100 Confirmation Required
STRUCTAI-4200 Tenant Access Denied
STRUCTAI-5000 Task Error
STRUCTAI-5100 Task Timeout
STRUCTAI-5200 Task Cancelled
STRUCTAI-5300 Task Recovery Error
STRUCTAI-6000 Adapter Error
STRUCTAI-6100 Resource Locked
STRUCTAI-6200 Artifact Error
STRUCTAI-7000 Internal Error
```

---

# 44. MCP SDK Integration

SDK 负责：

```text
MCP Protocol
Session
Tool Discovery
Tool Registration
Tool Invocation
Cancellation
Progress
```

StructAI 负责：

```text
Tool Registry
Execution Pipeline
Task
Security
Adapter
Result
Audit
Trace
```

---

# 45. MCP Progress / Cancellation

Progress：

```text
TaskEngine
 ↓
MCP progress notification
```

Cancellation：

```text
MCP cancel
 ↓
TaskEngine.cancel()
 ↓
Adapter.cancel()
```

无法真实取消时必须返回：

```text
cancellation_requested
```

而不是伪造 CANCELLED。

---

# 46. 9 Tool Layer

Interface 层：

```text
app/interfaces/mcp/tools/
```

实现：

```text
document.py
model_query.py
model_assign.py
model_delete.py
model_build.py
view.py
result.py
design.py
analysis.py
```

Handler 必须很薄：

```text
parse request
 ↓
build context
 ↓
call Application Service
 ↓
map response
```

禁止在 Handler：

```text
SQL
RBAC calculation
Adapter lookup
Task implementation
```

---

# 47. 9 Tool 注册

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

完整 JSON Schema、Operation 参数和每个 Tool 的 Contract 不在本文件重复定义。

它们由下一份：

> 《9 个 MCP Tool 完整实现规范》

冻结。

---

# 48. Mock Adapter

Mock Adapter 必须支持：

```text
MODEL.NODE.*
MODEL.ELEMENT.*
MODEL.MATERIAL.*
MODEL.SECTION.*
MODEL.BOUNDARY.*
MODEL.LOAD.*
BUILD.COLUMN
ANALYSIS.STATIC
RESULT.NODE.DISPLACEMENT
DESIGN.STEEL
```

用于完整闭环。

---

# 49. E2E

Generic AI Client：

```text
connect
 ↓
discover tools
 ↓
discover capabilities
 ↓
BUILD.COLUMN
 ↓
query nodes
 ↓
query elements
 ↓
assign load
 ↓
ANALYSIS.STATIC
 ↓
poll task
 ↓
RESULT.NODE.DISPLACEMENT
 ↓
RESULT.ELEMENT.FORCE
 ↓
DESIGN.STEEL
 ↓
verify trace
 ↓
verify audit
```

---

# 50. Failure / Recovery

必须测试：

```text
adapter timeout
adapter disconnect
task worker crash
lease expiry
duplicate request
lock conflict
version conflict
permission denied
capability unavailable
schema failure
engineering validation failure
artifact failure
database restart
```

---

# 51. Test Layers

```text
Unit
Contract
Integration
Recovery
Security
Concurrency
Failure
Performance
E2E
```

---

# 52. Security Tests

至少：

```text
cross-tenant access
forged identity context
role escalation
agent privilege escalation
expired session
revoked session
secret leakage
audit tampering
confirmation bypass
idempotency race
lock bypass
```

---

# 53. Performance Tests

至少测试：

```text
tool discovery
operation discovery
schema validation
capability resolution
task queue
concurrent read
serialized write
large result pagination
adapter latency
```

目标不是提前规定绝对 TPS，而是建立 Core Alpha 基准。

---

# 54. Graceful Shutdown

Shutdown 顺序：

```text
stop accepting new work
 ↓
mark server draining
 ↓
stop task scheduling
 ↓
wait bounded time
 ↓
persist task state
 ↓
release owned locks
 ↓
close adapters
 ↓
close DB
 ↓
close MCP transport
```

未完成 Task 必须能够在下次启动进入 Recovery。

---

# 55. Core Alpha Implementation Order

```text
01 Project Bootstrap
02 Settings
03 Database / AsyncSession
04 Alembic
05 Domain Model
06 Repository / UnitOfWork
07 Seed
08 Registry
09 Schema Engine
10 Authentication / Session
11 RBAC / Effective Permission
12 Resource Resolver
13 Resource Lock
14 Execution Context
15 Validation
16 Capability Resolver
17 Adapter Framework
18 Plugin Loader
19 Mock Adapter
20 Task Engine
21 Task DAG
22 Task Recovery
23 Idempotency
24 Artifact Storage
25 Document Service
26 Event Bus
27 Audit / Trace
28 Metrics / Health
29 9 MCP Tools
30 MCP SDK Integration
31 STDIO
32 Streamable HTTP
33 Contract Tests
34 Integration Tests
35 Recovery Tests
36 Security Tests
37 Generic AI Client E2E
```

---

# 56. Definition of Done

```text
[ ] Python 3.12+
[ ] Async SQLite
[ ] SQLAlchemy 2.x
[ ] Alembic
[ ] UnitOfWork
[ ] Multi-Tenant
[ ] Authentication
[ ] Session
[ ] RBAC
[ ] Effective Permission
[ ] Resource Resolver
[ ] Resource Lock
[ ] Optimistic Lock
[ ] Registry
[ ] Schema Engine
[ ] Validation
[ ] Capability Resolver
[ ] Adapter Framework
[ ] Plugin Loader
[ ] Mock Adapter
[ ] Task Engine
[ ] Task DAG
[ ] Task Lease
[ ] Task Recovery
[ ] Idempotency
[ ] Artifact Storage
[ ] Document Service
[ ] Batch
[ ] Dry Run
[ ] Preconditions
[ ] Postconditions
[ ] Event Bus
[ ] Quota
[ ] Health
[ ] Metrics
[ ] Audit
[ ] Trace
[ ] Backup
[ ] Recovery Tests
[ ] Security Tests
[ ] 9 MCP Tools
[ ] STDIO
[ ] Streamable HTTP
[ ] Generic MCP Client E2E
```

---

# 57. Architecture Red Lines

禁止：

```text
MCP Tool → Native API
MCP Tool → SQLAlchemy
UI → SQLAlchemy
AI → Native API
Adapter → FastAPI
Client → forged IdentityContext
Database → executable Python
```

必须：

```text
Interface
 ↓
Application
 ↓
Domain
 ↓
Infrastructure
```

以及：

```text
MCP Tool
 ↓
Operation
 ↓
Capability
 ↓
Policy / Validation
 ↓
Task
 ↓
Adapter
 ↓
Engineering Software
```

---

# 58. 与下一份文档的关系

本文件冻结：

```text
Core Runtime
Execution Pipeline
Security
Task
Adapter
Database interaction
Observability
MCP integration
```

下一份文档冻结：

```text
9 MCP Tool
JSON Schema
Operation enum
Parameters
Output
Risk
Permission
Capability
Confirmation
Errors
Examples
```

下一份不得重新定义 Core Runtime。

---

# 59. 最终结论

> Core Python Revision V2 是 StructAI MCP Server 的底层执行基线；9 Tool Contract 是上层稳定接口；真实工程软件通过 Adapter 接入。

MIDAS 只能是第一个 Adapter，而不是 Core 的架构边界。



# 完整收录：py

# StructAI MCP Server V2.0

## Core Python 代码实现规范 --- Revision V2

**Document:**
`StructAI_MCP_Server_V2.0_Core_Python_Implementation_Specification_Revision_V2.md`\
**Version:** 2.0 Revision V2\
**Status:** Development Baseline\
**Target:** Core Alpha\
**Language:** Python 3.12+

------------------------------------------------------------------------

# 1. 修订说明

本文件是在第四份：

> 《StructAI MCP Server V2.0 --- Core Python 代码实现规范》

基础上的正式修订版。

本次不是推倒重来，而是补齐 Core Alpha 在进入第 5 份「9 个 MCP Tool
完整实现规范」之前必须冻结的底层能力。

本修订新增：

``` text
01 MCP SDK / Protocol Integration
02 Task Recovery
03 Task DAG
04 Task Lease / Heartbeat
05 Resource Lock
06 Optimistic Concurrency
07 Atomic Idempotency
08 Authentication / Session
09 Server-generated Identity Context
10 Secret / Credential Provider
11 Adapter Plugin Loader
12 Software Instance Lifecycle
13 Artifact / Document Storage
14 Pagination
15 Batch Execution
16 Dry Run
17 Operation Preconditions / Postconditions
18 Capability Cache / Refresh
19 Health / Readiness / Liveness
20 Metrics
21 Runtime Configuration
22 Event Bus
23 Notification Extension
24 Quota / Rate Limit
25 Audit Integrity
26 Data Retention
27 Backup / Restore
28 Migration Safety
29 Failure Recovery Tests
30 Security Tests
31 Resource Resolver
32 Application / Infrastructure / Interface Layering
```

本版本是后续第五份 Tool Contract 的实现基础。

------------------------------------------------------------------------

# 2. 最终分层架构

StructAI MCP Core 最终采用：

``` text
Domain
    ↓
Application
    ↓
Infrastructure
    ↓
Interface
```

完整结构：

``` text
                    ┌──────────────────────┐
                    │      MCP Client      │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │    Interface Layer   │
                    │ MCP / HTTP / CLI     │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │   Application Layer  │
                    │ Commands / Queries   │
                    │ Execution Services   │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │      Domain Layer    │
                    │ Engineering Semantics│
                    │ Rules / Contracts    │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Infrastructure Layer │
                    │ DB / Adapter / Files │
                    │ Secrets / Events     │
                    └──────────────────────┘
```

核心原则：

> Interface 不定义业务规则；Application 编排；Domain
> 定义工程语义；Infrastructure 提供具体实现。

------------------------------------------------------------------------

# 3. 最终项目结构

``` text
structai-mcp/
│
├── pyproject.toml
├── README.md
├── LICENSE
├── .env.example
├── .gitignore
│
├── app/
│   ├── main.py
│   │
│   ├── config/
│   │   ├── settings.py
│   │   ├── runtime_config.py
│   │   └── logging.py
│   │
│   ├── domain/
│   │   ├── enums.py
│   │   ├── entities.py
│   │   ├── value_objects.py
│   │   ├── errors.py
│   │   ├── events.py
│   │   └── protocols.py
│   │
│   ├── application/
│   │   ├── commands/
│   │   ├── queries/
│   │   ├── services/
│   │   ├── execution/
│   │   ├── task/
│   │   ├── security/
│   │   ├── resource/
│   │   └── dto/
│   │
│   ├── infrastructure/
│   │   ├── database/
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   ├── models/
│   │   │   ├── repositories/
│   │   │   └── migrations/
│   │   │
│   │   ├── registry/
│   │   ├── adapters/
│   │   │   ├── base/
│   │   │   ├── mock/
│   │   │   └── plugins/
│   │   ├── storage/
│   │   ├── secrets/
│   │   ├── events/
│   │   ├── notifications/
│   │   └── locks/
│   │
│   ├── interfaces/
│   │   ├── mcp/
│   │   │   ├── server.py
│   │   │   ├── context.py
│   │   │   ├── responses.py
│   │   │   └── tools/
│   │   ├── http/
│   │   │   ├── api.py
│   │   │   ├── health.py
│   │   │   └── management/
│   │   └── cli/
│   │
│   └── observability/
│       ├── tracing.py
│       ├── metrics.py
│       └── audit.py
│
├── schemas/
├── migrations/
├── scripts/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── recovery/
│   ├── security/
│   └── e2e/
└── docs/
```

------------------------------------------------------------------------

# 4. Python 与依赖

``` text
Python >= 3.12
```

基础：

``` toml
[project]
name = "structai-mcp"
version = "2.0.0"
requires-python = ">=3.12"

dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "pydantic>=2.10",
    "pydantic-settings>=2.7",
    "sqlalchemy>=2.0",
    "alembic>=1.14",
    "aiosqlite>=0.20",
    "httpx>=0.28",
    "jsonschema>=4.23",
    "structlog>=25.1"
]
```

测试：

``` toml
[project.optional-dependencies]
test = [
    "pytest>=8.3",
    "pytest-asyncio>=0.25",
    "pytest-cov>=6.0"
]

dev = [
    "ruff>=0.9",
    "mypy>=1.14",
    "pre-commit>=4.0"
]
```

MCP：

> 使用实现时的官方稳定 MCP Python
> SDK，并锁定实际验证通过的版本。不得自行重新实现 MCP 协议。

------------------------------------------------------------------------

# 5. Domain Enum

``` python
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


class LockMode(StrEnum):
    READ = "READ"
    WRITE = "WRITE"
    EXCLUSIVE = "EXCLUSIVE"


class HealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class SoftwareConnectionState(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    RECONNECTING = "RECONNECTING"
    UNAVAILABLE = "UNAVAILABLE"


class PermissionEffect(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
```

------------------------------------------------------------------------

# 6. ExecutionContext：身份必须由服务器生成

这是本版本的重要安全修正。

客户端不得直接决定：

``` text
user_id
tenant_id
roles
permissions
```

定义：

``` python
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
```

身份来源：

``` text
Authentication
       ↓
AuthenticatedPrincipal
       ↓
IdentityContext
       ↓
ExecutionContext
```

客户端最多提供：

``` text
project_id
software_instance_id
```

服务器必须验证其归属。

------------------------------------------------------------------------

# 7. Authentication / Session

Core 必须包含：

``` text
AuthenticationService
PasswordService
SessionService
TokenService
```

最小接口：

``` python
class AuthenticationService:

    async def authenticate(
        self,
        username: str,
        password: str,
    ) -> AuthenticatedPrincipal:
        ...


class SessionService:

    async def create(
        self,
        principal: AuthenticatedPrincipal,
    ) -> Session:
        ...

    async def revoke(
        self,
        session_id,
    ) -> None:
        ...

    async def validate(
        self,
        session_id,
    ) -> AuthenticatedPrincipal:
        ...
```

密码哈希：

``` text
Argon2id
```

必须支持：

``` text
login
logout
session expiry
session revoke
failed-login tracking
account lock
```

MCP STDIO 单机模式可以使用：

``` text
local trusted identity
```

但仍必须构造标准 `IdentityContext`。

------------------------------------------------------------------------

# 8. Effective Permission Resolver

最终权限不能简单读取一个角色。

必须计算：

``` text
User
 ↓
Global Roles
 ↓
Tenant Membership
 ↓
Tenant Roles
 ↓
Project Membership
 ↓
Project Roles
 ↓
Resource ACL
 ↓
Explicit Deny
 ↓
Effective Permissions
```

接口：

``` python
class EffectivePermissionService:

    async def resolve(
        self,
        context: ExecutionContext,
        resource: "ResourceRef | None",
    ) -> set[str]:
        ...

    async def authorize(
        self,
        context: ExecutionContext,
        permission: str,
        resource: "ResourceRef | None",
    ) -> None:
        ...
```

AI Agent 权限：

``` text
Effective User Permissions
            ∩
Agent Permissions
            =
Effective Agent Permissions
```

AI Agent 不允许提升权限。

------------------------------------------------------------------------

# 9. Resource Resolver

统一解决：

``` text
Project
Model
Document
Software Instance
Task
Artifact
```

接口：

``` python
@dataclass(frozen=True)
class ResourceRef:
    resource_type: str
    resource_id: str


class ResourceResolver:

    async def resolve(
        self,
        resource: ResourceRef,
        context: ExecutionContext,
    ) -> object:
        ...

    async def verify_access(
        self,
        resource: ResourceRef,
        context: ExecutionContext,
    ) -> None:
        ...
```

所有跨租户访问必须在 Resource Resolver 层被拦截。

------------------------------------------------------------------------

# 10. Database Session / Unit of Work

使用：

``` python
AsyncEngine
AsyncSession
async_sessionmaker
```

建立：

``` python
class UnitOfWork:

    session: AsyncSession

    async def __aenter__(self):
        ...

    async def __aexit__(self, exc_type, exc, tb):
        ...
```

事务：

``` text
Application Service
       ↓
Unit of Work
       ↓
Repository
       ↓
Commit
```

异常：

``` text
Exception
 ↓
Rollback
```

Repository 不自行随意 commit。

------------------------------------------------------------------------

# 11. Tenant Isolation

所有 Tenant-scoped Repository 必须要求：

``` python
tenant_id
```

例如：

``` python
async def get_task(
    self,
    task_id: UUID,
    tenant_id: UUID,
) -> Task | None:
    ...
```

数据库查询必须同时限制：

``` text
tenant_id
+
resource_id
```

禁止依赖 UI 过滤。

------------------------------------------------------------------------

# 12. Optimistic Concurrency

模型、文档等可变资源必须有：

``` text
version
```

更新：

``` text
expected_version
```

流程：

``` text
Read version=12
      ↓
Modify
      ↓
UPDATE ... WHERE version=12
      ↓
version=13
```

如果影响行数为 0：

``` text
STRUCTAI-1300
CONCURRENCY_CONFLICT
```

不得覆盖其他用户修改。

------------------------------------------------------------------------

# 13. Resource Lock Manager

用于：

``` text
Software Instance
Model
Document
```

接口：

``` python
class ResourceLockManager:

    async def acquire(
        self,
        resource: ResourceRef,
        mode: LockMode,
        owner_id: str,
        timeout: float,
    ) -> None:
        ...

    async def release(
        self,
        resource: ResourceRef,
        owner_id: str,
    ) -> None:
        ...
```

规则：

``` text
READ + READ = allowed
READ + WRITE = blocked
WRITE + WRITE = blocked
EXCLUSIVE = blocks all
```

对于工程模型修改：

``` text
WRITE / EXCLUSIVE
```

默认建议：

``` text
SERIAL
```

------------------------------------------------------------------------

# 14. Task Lease / Heartbeat

每个运行中 Task：

``` text
lease_owner
lease_until
last_heartbeat
```

Worker 必须定期 heartbeat。

如果：

``` text
now > lease_until
```

任务视为 Worker 丢失。

------------------------------------------------------------------------

# 15. Task Recovery

服务器启动：

``` text
Load unfinished tasks
       ↓
Inspect lease
       ↓
Lease valid?
 ├── Yes → wait / reconcile
 └── No → RECOVERING
              ↓
          retry / requeue
```

Task Recovery Policy：

``` text
REQUEUE
FAIL
RESUME
```

具体由 OperationDefinition 指定。

默认：

``` text
不可恢复 → FAILED
可重入 → REQUEUE
支持 checkpoint → RESUME
```

------------------------------------------------------------------------

# 16. Task DAG

Task 不仅是单个函数。

结构：

``` text
Task
 ├── Step A
 ├── Step B
 ├── Step C
 │    └── depends_on A
 └── Step D
      └── depends_on B,C
```

定义：

``` python
@dataclass
class TaskStep:
    step_id: str
    operation: str
    parameters: dict
    depends_on: tuple[str, ...] = ()
```

调度规则：

``` text
dependency all COMPLETED
        ↓
step becomes runnable
```

支持：

``` text
sequential
parallel
dependency
retry
timeout
cancel
resume
```

------------------------------------------------------------------------

# 17. Task Priority

至少：

``` text
LOW
NORMAL
HIGH
CRITICAL
```

Queue 必须按：

``` text
priority
+
created_at
```

排序。

------------------------------------------------------------------------

# 18. Task 并发策略

Task Engine 必须支持：

``` text
global concurrency
tenant concurrency
user concurrency
software-instance concurrency
```

例如：

``` text
Tenant A = 10
User A = 4
CIVIL-01 = 1
```

最终取最严格限制。

------------------------------------------------------------------------

# 19. Software Instance Lifecycle

软件实例状态：

``` text
DISCONNECTED
CONNECTING
CONNECTED
DEGRADED
RECONNECTING
UNAVAILABLE
```

Adapter Manager：

``` python
class AdapterManager:

    async def connect(self, instance_id):
        ...

    async def disconnect(self, instance_id):
        ...

    async def health_check(self, instance_id):
        ...

    async def get_adapter(self, instance_id):
        ...
```

------------------------------------------------------------------------

# 20. Software Instance Concurrency Policy

每个软件实例定义：

``` text
SERIAL
LIMITED
PARALLEL
```

默认：

``` text
SERIAL
```

特别是桌面型有限元软件。

------------------------------------------------------------------------

# 21. Secret / Credential Provider

数据库不得保存明文：

``` text
API Key
Password
Token
Certificate Private Key
```

定义：

``` python
class CredentialProvider(Protocol):

    async def get_secret(
        self,
        reference: str,
    ) -> str:
        ...

    async def set_secret(
        self,
        reference: str,
        value: str,
    ) -> None:
        ...

    async def delete_secret(
        self,
        reference: str,
    ) -> None:
        ...
```

第一阶段：

``` text
EnvironmentCredentialProvider
```

后续：

``` text
OS Credential Store
Vault
KMS
```

日志绝对禁止输出 secret。

------------------------------------------------------------------------

# 22. Adapter Plugin Loader

Adapter 必须可插件化。

推荐：

``` text
Python Entry Points
```

例如：

``` toml
[project.entry-points."structai.adapters"]
midas.civil = "structai_midas.adapter:CivilAdapter"
```

启动：

``` text
Plugin Loader
 ↓
Discover Adapter Plugins
 ↓
Validate Manifest
 ↓
Register Adapter
```

新软件原则：

``` text
New Adapter
+
Capability Mapping
+
Operation Mapping
+
API Registry
```

不修改 9 个 Tool Contract。

------------------------------------------------------------------------

# 23. Adapter Manifest

每个 Adapter 应声明：

``` json
{
  "name": "midas.civil",
  "vendor": "MIDAS",
  "product": "CIVIL NX",
  "supported_versions": ["2025", "2026"],
  "capabilities": [],
  "protocols": ["REST"]
}
```

------------------------------------------------------------------------

# 24. API Registry / Version Resolver

同一个 Operation 可以：

``` text
Operation
 ↓
Software
 ↓
Version
 ↓
API Mapping
```

必须支持：

``` text
version exact match
version range
fallback mapping
deprecated mapping
```

例如：

``` text
CIVIL 2025 → API A
CIVIL 2026 → API B
CIVIL 2027 → API C
```

------------------------------------------------------------------------

# 25. API Transform Engine

API Mapping 必须支持：

``` text
STATIC_MAPPING
TEMPLATE_MAPPING
JSON_MAPPING
CUSTOM_TRANSFORM
```

统一：

``` text
Operation Parameters
        ↓
Request Transformer
        ↓
Native API
        ↓
Response Transformer
        ↓
Canonical Result
```

Custom Transformer 必须经过：

``` text
Adapter package
```

禁止数据库直接执行任意 Python。

------------------------------------------------------------------------

# 26. Capability Cache

Capability 分为：

``` text
Static Capability
Runtime Capability
```

缓存：

``` text
instance_id
software_version
capability
checked_at
expires_at
```

支持：

``` text
get
refresh
invalidate
```

软件重连 / 版本变化后必须重新验证。

------------------------------------------------------------------------

# 27. Schema Registry

Schema：

``` text
structai://schema/model/node/v1
structai://schema/model/node/v2
```

旧版本不可覆盖。

必须记录：

``` text
schema_uri
version
content
status
created_at
deprecated_at
```

支持：

``` text
resolve
validate
compatibility check
```

------------------------------------------------------------------------

# 28. Operation Definition

OperationDefinition 至少包含：

``` python
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
    recovery_policy: str
```

------------------------------------------------------------------------

# 29. Preconditions / Postconditions

每个重要 Operation 支持：

``` text
Preconditions
Postconditions
```

例如：

``` text
BUILD.COLUMN

Preconditions:
- project active
- software connected
- material valid
- section valid

Postconditions:
- nodes created
- element created
- assignments created
```

------------------------------------------------------------------------

# 30. Dry Run

高风险操作支持：

``` text
mode = DRY_RUN
```

例如：

``` text
BUILD.COLUMN
```

返回：

``` json
{
  "dry_run": true,
  "planned_changes": {
    "nodes": 2,
    "elements": 1,
    "materials": 1,
    "sections": 1
  }
}
```

不得修改模型。

------------------------------------------------------------------------

# 31. Batch Execution

模型操作必须支持批量：

``` json
{
  "items": [
    {},
    {},
    {}
  ]
}
```

适用于：

``` text
NODE.CREATE
ELEMENT.CREATE
LOAD.ASSIGN
```

Batch 必须明确：

``` text
atomic
non_atomic
```

------------------------------------------------------------------------

# 32. Idempotency：必须原子化

Idempotency Key 必须有数据库唯一约束：

``` text
tenant_id
+
idempotency_key
```

流程：

``` text
Atomic Insert
      ↓
Conflict?
 ├── Yes → Return existing result
 └── No → Execute
```

不能采用：

``` text
SELECT
then INSERT
```

的非原子方式。

------------------------------------------------------------------------

# 33. Artifact Service

工程任务可能产生：

``` text
工程文件
模型文件
分析结果
计算书
报告
截图
导出文件
```

定义：

``` python
class ArtifactStorage(Protocol):

    async def put(...):
        ...

    async def get(...):
        ...

    async def delete(...):
        ...
```

数据库只保存：

``` text
artifact_id
storage_backend
storage_key
mime_type
size
checksum
```

第一阶段：

``` text
LocalFilesystemStorage
```

后续：

``` text
S3
MinIO
NAS
```

------------------------------------------------------------------------

# 34. Document Service

`engineering_doc` 不直接操作文件系统。

使用：

``` text
DocumentService
 ↓
ArtifactService
 ↓
Adapter
```

生命周期：

``` text
NEW
OPEN
SAVE
SAVE_AS
CLOSE
INFO
```

------------------------------------------------------------------------

# 35. 大结果集分页

所有可能产生大量数据的 Query 必须支持：

``` text
limit
cursor
has_more
next_cursor
```

统一：

``` json
{
  "data": [],
  "pagination": {
    "has_more": true,
    "next_cursor": "..."
  }
}
```

禁止一次返回无限数据。

------------------------------------------------------------------------

# 36. Canonical Engineering Model

至少：

``` text
Node
Element
Material
Section
Boundary
Load
Group
Analysis
Result
Design
```

必须定义稳定 Schema。

------------------------------------------------------------------------

# 37. Result Normalization

不同软件：

``` text
MIDAS
ETABS
SAP2000
ANSYS
OpenSees
```

统一为 StructAI Canonical Model。

例如：

``` json
{
  "node_id": 100,
  "ux": 0.001,
  "uy": 0.002,
  "uz": -0.015
}
```

------------------------------------------------------------------------

# 38. Event Bus

Core Alpha 实现：

``` text
InProcessEventBus
```

事件：

``` text
TaskCreated
TaskStarted
TaskProgress
TaskCompleted
TaskFailed
TaskCancelled
AdapterConnected
AdapterDisconnected
ModelChanged
```

未来可以替换：

``` text
Redis
NATS
Kafka
```

而不修改 Domain Event。

------------------------------------------------------------------------

# 39. Notification Extension

定义：

``` python
class NotificationService(Protocol):

    async def notify(
        self,
        event,
    ) -> None:
        ...
```

未来支持：

``` text
MCP notification
Webhook
WebSocket
UI
Email
```

Core Alpha 可以只实现 InProcess。

------------------------------------------------------------------------

# 40. Quota / Rate Limit

必须区分：

``` text
User
Tenant
AI Agent
Software Instance
```

至少预留：

``` text
max_tasks
max_concurrent_tasks
max_api_requests
max_storage
max_projects
```

Rate Limiter 第一阶段可以是：

``` text
InMemory
```

未来替换：

``` text
Redis
```

------------------------------------------------------------------------

# 41. Health / Readiness / Liveness

HTTP：

``` text
GET /livez
GET /readyz
GET /health
```

Liveness：

``` text
process alive
```

Readiness：

``` text
database
registry
task engine
```

Health：

``` text
database
task engine
adapter manager
software instances
```

某一个 MIDAS 不在线：

``` text
Core = READY
MIDAS = UNAVAILABLE
```

不得让整个服务器不可用。

------------------------------------------------------------------------

# 42. Metrics

至少：

``` text
structai_requests_total
structai_request_duration_seconds
structai_task_total
structai_task_duration_seconds
structai_task_failed_total
structai_adapter_requests_total
structai_adapter_errors_total
structai_active_tasks
structai_mcp_connections
```

推荐 Prometheus-compatible exposition。

------------------------------------------------------------------------

# 43. Runtime Configuration

配置分为：

``` text
Startup Config
Runtime Config
Persistent Config
Secret Config
```

例如：

``` text
Startup:
database URL

Runtime:
log level
task concurrency

Persistent:
software instance configuration

Secret:
API key
password
token
```

UI 后续修改 Runtime Config 时：

``` text
Config Service
 ↓
Validation
 ↓
Persist if required
 ↓
Apply
```

------------------------------------------------------------------------

# 44. Audit Integrity

Audit 至少：

``` text
audit_id
timestamp
tenant_id
user_id
action
resource
result
previous_hash
entry_hash
```

用于检测篡改。

------------------------------------------------------------------------

# 45. Data Retention

必须定义 Retention Policy：

``` text
Task
Trace
Audit
Artifact
Session
```

每类数据允许：

``` text
retention_days
```

Audit 默认不允许普通用户删除。

------------------------------------------------------------------------

# 46. Backup / Restore

Core Alpha 必须提供：

``` text
backup
restore
integrity-check
```

SQLite：

``` text
backup DB
backup artifact metadata
backup registry data
```

恢复后：

``` text
database integrity check
registry validation
```

------------------------------------------------------------------------

# 47. Migration Safety

Alembic：

``` text
upgrade
downgrade
```

生产升级前：

``` text
backup
 ↓
migration
 ↓
integrity check
 ↓
registry validation
```

Migration 失败：

``` text
rollback / restore
```

------------------------------------------------------------------------

# 48. Error Contract

统一：

``` text
STRUCTAI-1000 Protocol Error
STRUCTAI-1100 Schema Validation Error
STRUCTAI-1200 Engineering Validation Error
STRUCTAI-1300 Concurrency Conflict

STRUCTAI-2000 Software Connection Error
STRUCTAI-2100 Software Authentication Error
STRUCTAI-2200 Software API Error
STRUCTAI-2300 Software Timeout

STRUCTAI-3000 Capability Not Supported

STRUCTAI-4000 Permission Denied
STRUCTAI-4100 Confirmation Required
STRUCTAI-4200 Tenant Access Denied

STRUCTAI-5000 Task Error
STRUCTAI-5100 Task Timeout
STRUCTAI-5200 Task Cancelled
STRUCTAI-5300 Task Recovery Error

STRUCTAI-6000 Adapter Error
STRUCTAI-6100 Resource Locked
STRUCTAI-6200 Artifact Error

STRUCTAI-7000 Internal Error
```

------------------------------------------------------------------------

# 49. MCP Error Mapping

Native Error：

``` text
Adapter
 ↓
StructAI Error
 ↓
Application Response
 ↓
MCP Response
```

AI 默认看到：

``` text
StructAI normalized error
```

需要诊断时才返回：

``` json
{
  "cause": {
    "provider": "MIDAS",
    "native_code": "...",
    "native_message": "..."
  }
}
```

------------------------------------------------------------------------

# 50. MCP SDK 集成

MCP Server 负责：

``` text
Protocol
Session
Tool Discovery
Tool Registration
Tool Invocation
Cancellation
Progress
```

Tool Handler 不实现工程业务。

：

``` text
MCP Tool
 ↓
ToolRequest
 ↓
ExecutionService
```

------------------------------------------------------------------------

# 51. MCP Progress

异步 Task：

``` text
Task Engine
 ↓
progress event
 ↓
MCP progress notification
```

例如：

``` text
0
25
43
80
100
```

Task Engine 是唯一进度来源。

------------------------------------------------------------------------

# 52. MCP Cancellation

MCP cancellation：

``` text
MCP Cancel
 ↓
TaskEngine.cancel()
 ↓
CANCEL_REQUESTED
 ↓
Adapter.cancel()
 ↓
CANCELLED
```

不能直接终止 Python process。

------------------------------------------------------------------------

# 53. Tool Layer

9 个 Tool：

``` text
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

每个 Tool：

``` text
thin wrapper
```

最终：

``` python
return await execution_service.execute(...)
```

------------------------------------------------------------------------

# 54. Tool 参数

统一：

``` python
class ToolRequest(BaseModel):
    operation: str
    parameters: dict = {}
    context: dict = {}
    idempotency_key: str | None = None
    confirmation_token: str | None = None
    dry_run: bool = False
```

注意：

``` text
context.identity
```

不得由客户端覆盖。

------------------------------------------------------------------------

# 55. Execution Pipeline

最终执行顺序冻结为：

``` text
MCP Request
 ↓
Authenticate
 ↓
Build Server IdentityContext
 ↓
Build ExecutionContext
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
Preconditions
 ↓
Effective Permission
 ↓
Quota / Rate Limit
 ↓
Confirmation
 ↓
Idempotency
 ↓
Concurrency / Resource Lock
 ↓
Capability Check
 ↓
Task / Transaction
 ↓
Adapter
 ↓
Result Normalization
 ↓
Postconditions
 ↓
Release Lock
 ↓
Persist Result
 ↓
Audit
 ↓
Trace
 ↓
Event
 ↓
MCP Response
```

这是 Core Alpha 的最终标准执行链。

------------------------------------------------------------------------

# 56. Transaction / Rollback

复杂 Operation：

``` text
BUILD.COLUMN
BUILD.FRAME
BUILD.STEEL_FRAME
```

优先：

``` text
Native Transaction
 ↓
Snapshot / Restore
 ↓
Compensating Actions
 ↓
Best Effort
```

OperationDefinition 必须声明：

``` text
transactional
rollback_supported
```

------------------------------------------------------------------------

# 57. Mock Adapter

Mock Adapter 必须模拟：

``` text
Node
Element
Material
Section
Boundary
Load
Analysis
Result
Design
```

并支持：

``` text
snapshot
restore
lock compatibility
deterministic analysis
```

------------------------------------------------------------------------

# 58. Mock E2E

固定场景：

> 创建一个高度 6m 的 Q355B H400×400×13×21 钢柱，底部固定，顶部施加 500kN
> 轴压力。完成静力分析，并返回顶部节点位移和钢柱设计利用率。

链：

``` text
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

------------------------------------------------------------------------

# 59. Result / Artifact

Analysis 完成后：

``` text
Analysis Result
 ↓
Canonical Result
 ↓
Artifact
```

例如：

``` text
analysis.json
result.csv
report.pdf
```

数据库只保存 Artifact metadata。

------------------------------------------------------------------------

# 60. Application Service

Application Service 负责：

``` text
Command
Query
Execution
Task
Security
Resource
```

例如：

``` python
class EngineeringExecutionService:

    async def execute(
        self,
        command: ExecutionCommand,
    ) -> ExecutionResult:
        ...
```

Application Service 可以编排多个 Domain Service。

------------------------------------------------------------------------

# 61. Domain Service

Domain Service 负责纯工程规则：

``` text
Model validation
Engineering rules
Operation preconditions
Canonical model rules
```

不得访问：

``` text
HTTP
SQLAlchemy
FastAPI
MCP SDK
```

------------------------------------------------------------------------

# 62. Infrastructure Service

负责：

``` text
Database
Adapter
Filesystem
Secret
Lock
Event
Notification
```

------------------------------------------------------------------------

# 63. Interface Layer

只允许：

``` text
MCP
HTTP
CLI
```

Interface 层不得直接访问：

``` text
SQLAlchemy
Adapter
Filesystem
```

必须经过 Application Service。

------------------------------------------------------------------------

# 64. Configuration Bootstrap

启动：

``` text
1 Settings
2 Logging
3 Database
4 Migration
5 Seed
6 Registry
7 Plugin Loader
8 Schema Registry
9 Capability Registry
10 Adapter Manager
11 Resource Lock Manager
12 Task Engine
13 Event Bus
14 Security
15 Health
16 MCP Server
17 Transport
```

Registry validation 失败：

``` text
Server MUST NOT become READY
```

------------------------------------------------------------------------

# 65. Graceful Shutdown

``` text
Stop new requests
 ↓
Stop scheduler
 ↓
Stop accepting tasks
 ↓
Wait / recover active tasks
 ↓
Disconnect adapters
 ↓
Flush audit/events
 ↓
Close DB
 ↓
Exit
```

------------------------------------------------------------------------

# 66. Health / Recovery Policy

服务器启动发现：

``` text
RUNNING task
```

必须根据 Operation Recovery Policy：

``` text
REQUEUE
RESUME
FAIL
```

不得简单删除。

------------------------------------------------------------------------

# 67. Tests

测试目录：

``` text
tests/
├── unit/
├── contract/
├── integration/
├── recovery/
├── security/
└── e2e/
```

------------------------------------------------------------------------

# 68. Unit Tests

至少：

``` text
ToolRegistry
OperationRegistry
CapabilityResolver
SchemaValidator
EngineeringValidator
PermissionResolver
ResourceResolver
TaskStateMachine
TaskDAG
Idempotency
ResourceLock
ErrorMapper
```

------------------------------------------------------------------------

# 69. Contract Tests

必须：

``` text
9 Tool Schemas
Operation Schema
Response Schema
Error Schema
Context Schema
Canonical Model Schema
```

------------------------------------------------------------------------

# 70. Integration Tests

必须：

``` text
Tool
 ↓
Application Service
 ↓
Task Engine
 ↓
Mock Adapter
```

------------------------------------------------------------------------

# 71. Recovery Tests

必须：

``` text
test_server_restart_recovery
test_expired_task_lease
test_task_requeue
test_task_resume
test_task_failure_after_recovery
test_adapter_disconnect_recovery
```

------------------------------------------------------------------------

# 72. Concurrency Tests

必须：

``` text
test_optimistic_lock
test_idempotency_race
test_resource_lock
test_parallel_read
test_serial_write
test_software_instance_serialization
```

------------------------------------------------------------------------

# 73. Security Tests

必须：

``` text
test_cross_tenant_access_denied
test_cross_project_access_denied
test_ai_agent_no_privilege_escalation
test_expired_session
test_revoked_session
test_invalid_confirmation
test_confirmation_replay
test_secret_not_logged
test_client_cannot_forge_identity
```

------------------------------------------------------------------------

# 74. Failure Tests

必须：

``` text
test_adapter_timeout
test_adapter_connection_failure
test_database_failure
test_task_worker_failure
test_registry_failure
test_schema_version_mismatch
test_artifact_failure
```

------------------------------------------------------------------------

# 75. Performance Tests

Core Alpha 至少测试：

``` text
Tool discovery latency
Schema validation latency
Query latency
Task submission latency
Concurrent task limit
Memory growth
```

不得用性能优化破坏抽象层。

------------------------------------------------------------------------

# 76. Code Quality

必须：

``` text
ruff
mypy
pytest
pytest-cov
pre-commit
```

CI：

``` text
lint
 ↓
type check
 ↓
unit
 ↓
contract
 ↓
integration
 ↓
recovery
 ↓
security
 ↓
e2e
```

------------------------------------------------------------------------

# 77. Observability

每个请求：

``` text
request_id
trace_id
```

每个异步任务：

``` text
task_id
```

日志：

``` text
timestamp
level
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
message
```

不得记录：

``` text
password
API key
token
private key
```

------------------------------------------------------------------------

# 78. Trace Span

至少：

``` text
MCP
Tool
Operation
Schema
Validation
Permission
Capability
Task
Lock
Adapter
Native API
Result
Audit
```

------------------------------------------------------------------------

# 79. Audit

HIGH / CRITICAL：

``` text
必审计
```

审计字段：

``` text
user
tenant
project
tool
operation
resource
software
result
timestamp
hash
```

------------------------------------------------------------------------

# 80. Data Retention

必须配置：

``` text
task_retention_days
trace_retention_days
audit_retention_days
artifact_retention_days
session_retention_days
```

------------------------------------------------------------------------

# 81. Backup

至少：

``` text
database backup
artifact metadata backup
registry backup
```

执行：

``` text
backup
 ↓
integrity check
```

恢复：

``` text
restore
 ↓
migration check
 ↓
registry validation
 ↓
health check
```

------------------------------------------------------------------------

# 82. Core Alpha 实现顺序

正式顺序：

``` text
01 Project Bootstrap
02 Settings
03 Database / AsyncSession
04 Alembic
05 Domain Model
06 Repository / UnitOfWork
07 Seed
08 Registry
09 Schema Engine
10 Authentication / Session
11 RBAC / Effective Permission
12 Resource Resolver
13 Resource Lock
14 Execution Context
15 Validation
16 Capability Resolver
17 Adapter Framework
18 Plugin Loader
19 Mock Adapter
20 Task Engine
21 Task DAG
22 Task Recovery
23 Idempotency
24 Artifact Storage
25 Document Service
26 Event Bus
27 Audit / Trace
28 Metrics / Health
29 9 MCP Tools
30 MCP SDK Integration
31 STDIO
32 Streamable HTTP
33 Contract Tests
34 Integration Tests
35 Recovery Tests
36 Security Tests
37 Generic AI Client E2E
```

------------------------------------------------------------------------

# 83. Core Alpha Definition of Done

``` text
[ ] Python 3.12+
[ ] Async SQLite
[ ] Alembic
[ ] UnitOfWork
[ ] Multi-Tenant
[ ] Authentication
[ ] Session
[ ] RBAC
[ ] Effective Permission
[ ] Resource Resolver
[ ] Resource Lock
[ ] Optimistic Lock
[ ] Registry
[ ] Schema Engine
[ ] Validation
[ ] Capability Resolver
[ ] Adapter Framework
[ ] Plugin Loader
[ ] Mock Adapter
[ ] Task Engine
[ ] Task DAG
[ ] Task Lease
[ ] Task Recovery
[ ] Idempotency
[ ] Artifact Storage
[ ] Document Service
[ ] Batch
[ ] Dry Run
[ ] Preconditions
[ ] Postconditions
[ ] Event Bus
[ ] Quota
[ ] Health
[ ] Metrics
[ ] Audit
[ ] Trace
[ ] Backup
[ ] Recovery Tests
[ ] Security Tests
[ ] 9 MCP Tools
[ ] STDIO
[ ] Streamable HTTP
[ ] Generic MCP Client E2E
```

------------------------------------------------------------------------

# 84. Final Architecture

``` text
                         MCP Client
                              │
                              ▼
                     ┌─────────────────┐
                     │ Interface Layer │
                     │ MCP / HTTP /CLI │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │ Application     │
                     │ Execution       │
                     │ Task            │
                     │ Security       │
                     │ Resource       │
                     └────────┬────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
       Domain             Registry            Validation
          │                   │                   │
          └───────────────────┼───────────────────┘
                              ▼
                     Capability Resolver
                              │
                              ▼
                      Resource Lock
                              │
                              ▼
                         Task Engine
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
                 Adapter             Artifact
                 Manager              Storage
                    │
        ┌───────────┼────────────┐
        ▼           ▼            ▼
      MIDAS        ETABS      OpenSees
        │           │            │
        └───────────┼────────────┘
                    ▼
             Canonical Result
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
       Response   Trace      Audit
```

------------------------------------------------------------------------

# 85. 最终冻结原则

StructAI MCP Server Core 必须遵守：

> **先定义工程语义，再适配软件实现。**

> **Tool 不等于 API。**

> **Operation 不等于厂商 API。**

> **Capability 不绑定 MIDAS。**

> **Adapter 吸收软件差异。**

> **Identity 必须由服务器生成。**

> **Tenant 隔离必须在 Core / Repository 层完成。**

> **工程模型修改必须经过 Resource Lock + Concurrency Control。**

> **异步任务必须支持 Lease + Recovery。**

> **大型结果必须分页。**

> **复杂模型操作必须支持事务 / 回滚 / Dry Run。**

> **软件 Adapter 必须插件化。**

> **文件和工程产物必须进入 Artifact 层。**

> **UI 只能消费 Application / Management API，不能反向定义 Core。**

------------------------------------------------------------------------

# 86. 与第五份文档的关系

第四份 Revision V2 完成后，Core 的底层规则已经冻结。

下一份：

> **《StructAI MCP Server V2.0 --- 9 个 MCP Tool 完整实现规范》**

将只负责定义：

``` text
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

每个 Tool 都必须引用本文件已经冻结的：

``` text
Authentication
IdentityContext
Permission
Resource Resolver
Schema
Capability
Quota
Idempotency
Resource Lock
Task
Dry Run
Transaction
Artifact
Trace
Audit
```

因此从第五份开始，不再反复修改 Core 架构。

------------------------------------------------------------------------

# 87. 最终一句话

> **StructAI MCP Server V2.0 Core Alpha 的目标不是"能调用
> MIDAS"，而是建立一个具备身份、权限、租户、资源锁、任务编排、故障恢复、插件适配、工程语义、结果标准化和
> MCP 协议能力的通用工程软件执行运行时。**



# 完整收录：blue

# StructAI MCP Server V2.0
# 第六份：MCP Server 实际 Python 代码实现蓝图
## File-Level Implementation Blueprint

> 文档定位：将 StructAI MCP Server V2.0 已冻结的 Core Baseline、9 MCP Tool、Task Engine、Adapter、Security、Registry、Artifact、Observability 等设计，转换为**可直接进入编码阶段的文件级实现任务书**。
>
> 本文不重新设计架构，不把 MIDAS API 写入 Core，不增加第 10 个 MCP Tool。MIDAS、CSI、ANSYS、OpenSees 等均通过 Adapter + Capability + API Registry 接入。

---

# 1. Implementation Baseline

## 1.1 冻结目标

StructAI MCP Server V2.0 第一阶段必须形成一个可以独立运行的、软件无关的 MCP Server Core。

第一阶段优先完成：

```text
MCP Client
  ↓
MCP Transport
  ↓
9 MCP Tools
  ↓
Tool Dispatcher
  ↓
Execution Pipeline
  ↓
Authentication / RBAC
  ↓
Schema Validation
  ↓
Capability Resolver
  ↓
Resource Lock
  ↓
Task Engine
  ↓
Adapter
  ↓
Canonical Engineering Model
  ↓
Result / Artifact
  ↓
Audit / Trace / Event
  ↓
MCP Response
```

第一阶段 Adapter 使用 Mock Adapter。

完成 Core Alpha 后，再增加 MIDAS Adapter。

## 1.2 不允许的架构漂移

以下内容禁止直接进入 Core：

```text
midas_xxx()
midas_api()
midas_endpoint()
midas_node_create()
midas_analysis_static()
```

Tool 层禁止：

```text
Tool → MIDAS API
Tool → SQLAlchemy
Tool → requests/httpx
Tool → native vendor SDK
```

正确方向：

```text
Tool
 ↓
Application Service
 ↓
Operation
 ↓
Capability
 ↓
Adapter
 ↓
Native API
```

---

# 2. Python Runtime

## 2.1 Python

要求：

```text
Python >= 3.12
```

推荐：

```text
Python 3.12.x
```

## 2.2 异步模型

Core 使用：

```text
asyncio
```

数据库：

```text
SQLAlchemy AsyncIO
SQLite
aiosqlite
```

MCP：

```text
官方 MCP Python SDK
```

HTTP：

```text
FastAPI
Uvicorn
```

数据模型：

```text
Pydantic v2
```

迁移：

```text
Alembic
```

密码：

```text
argon2-cffi
```

测试：

```text
pytest
pytest-asyncio
httpx
```

## 2.3 依赖原则

Core Alpha 不强制：

```text
Redis
Celery
RabbitMQ
Kafka
NATS
PostgreSQL
```

这些作为未来扩展。

---

# 3. Project Directory

最终目录：

```text
structai-mcp/
├── pyproject.toml
├── README.md
├── LICENSE
├── .env.example
├── .gitignore
│
├── app/
│   ├── __init__.py
│   ├── main.py
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
│   │   ├── entities.py
│   │   ├── value_objects.py
│   │   ├── errors.py
│   │   ├── events.py
│   │   └── protocols.py
│   │
│   ├── application/
│   │   ├── __init__.py
│   │   ├── commands/
│   │   ├── queries/
│   │   ├── services/
│   │   ├── execution/
│   │   ├── task/
│   │   ├── security/
│   │   ├── resource/
│   │   └── dto/
│   │
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── database/
│   │   ├── registry/
│   │   ├── adapters/
│   │   ├── storage/
│   │   ├── secrets/
│   │   ├── events/
│   │   ├── notifications/
│   │   └── locks/
│   │
│   ├── interfaces/
│   │   ├── __init__.py
│   │   ├── mcp/
│   │   ├── http/
│   │   └── cli/
│   │
│   └── observability/
│       ├── __init__.py
│       ├── tracing.py
│       ├── metrics.py
│       └── audit.py
│
├── schemas/
├── migrations/
├── scripts/
├── tests/
└── docs/
```

---

# 4. pyproject.toml

基础依赖应包括：

```toml
[project]
name = "structai-mcp"
version = "2.0.0"
requires-python = ">=3.12"

dependencies = [
    "pydantic>=2",
    "pydantic-settings>=2",
    "sqlalchemy>=2",
    "aiosqlite",
    "alembic",
    "fastapi",
    "uvicorn",
    "argon2-cffi",
    "httpx",
    "mcp",
]

[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-asyncio",
    "pytest-cov",
    "ruff",
    "mypy",
]
```

实际项目开始编码时，应锁定经过测试的版本，而不是长期使用无上限版本。

---

# 5. Configuration Layer

## 5.1 `app/config/settings.py`

职责：

```text
读取环境变量
配置数据库
配置 MCP
配置 HTTP
配置日志
配置任务
配置安全
配置 Artifact
```

核心：

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "StructAI MCP Server"
    app_version: str = "2.0.0"

    database_url: str = "sqlite+aiosqlite:///./structai.db"

    mcp_transport: str = "stdio"

    host: str = "127.0.0.1"
    port: int = 7860

    task_worker_count: int = 4

    artifact_root: str = "./data/artifacts"

    session_expire_seconds: int = 86400

    class Config:
        env_file = ".env"
```

不得在代码中保存：

```text
密码
API Key
Token
私钥
MIDAS Key
```

---

# 6. Domain Layer

Domain 不依赖：

```text
FastAPI
MCP SDK
SQLAlchemy
HTTPX
MIDAS
```

---

# 7. `app/domain/enums.py`

定义：

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


class LockMode(StrEnum):
    READ = "READ"
    WRITE = "WRITE"
    EXCLUSIVE = "EXCLUSIVE"
```

还需要：

```text
Permission
Capability
TaskPriority
ResourceType
ArtifactType
AuditResult
AuthenticationMethod
```

---

# 8. `app/domain/value_objects.py`

定义：

```python
@dataclass(frozen=True)
class RequestIdentity:
    request_id: str
    trace_id: str
```

以及：

```text
ResourceRef
VersionRef
Pagination
IdempotencyKey
SoftwareRef
ProjectRef
ModelRef
DocumentRef
```

Value Object 必须不可变。

---

# 9. `app/domain/entities.py`

核心实体：

```text
Tenant
User
Role
Permission
Session
Project
Software
SoftwareProduct
SoftwareVersion
SoftwareInstance
ProjectMember
Model
Document
Task
TaskStep
Artifact
Capability
Operation
OperationCapability
IdempotencyRecord
ResourceLock
AuditRecord
```

模型对象：

```text
EngineeringNode
EngineeringElement
EngineeringMaterial
EngineeringSection
EngineeringBoundary
EngineeringLoad
EngineeringGroup
EngineeringAnalysis
EngineeringResult
EngineeringDesign
```

Canonical Model 不绑定任何供应商。

---

# 10. `app/domain/errors.py`

定义 StructAI 统一异常。

```python
class StructAIError(Exception):
    code = "STRUCTAI-7000"
    error_type = "INTERNAL_ERROR"
    retryable = False


class SchemaValidationError(StructAIError):
    code = "STRUCTAI-1100"
    error_type = "SCHEMA_VALIDATION_ERROR"


class EngineeringValidationError(StructAIError):
    code = "STRUCTAI-1200"
    error_type = "ENGINEERING_VALIDATION_ERROR"


class CapabilityError(StructAIError):
    code = "STRUCTAI-3000"
    error_type = "CAPABILITY_ERROR"


class PermissionDeniedError(StructAIError):
    code = "STRUCTAI-4000"
    error_type = "PERMISSION_DENIED"


class ConfirmationRequiredError(StructAIError):
    code = "STRUCTAI-4100"
    error_type = "CONFIRMATION_REQUIRED"


class ResourceLockedError(StructAIError):
    code = "STRUCTAI-6100"
    error_type = "RESOURCE_LOCKED"
```

完整错误代码：

```text
STRUCTAI-1000 Protocol Error
STRUCTAI-1100 Schema Validation Error
STRUCTAI-1200 Engineering Validation Error
STRUCTAI-1300 Concurrency Conflict
STRUCTAI-2000 Software Connection Error
STRUCTAI-2100 Software Authentication Error
STRUCTAI-2200 Software API Error
STRUCTAI-2300 Software Timeout
STRUCTAI-3000 Capability Not Supported
STRUCTAI-4000 Permission Denied
STRUCTAI-4100 Confirmation Required
STRUCTAI-4200 Tenant Access Denied
STRUCTAI-5000 Task Error
STRUCTAI-5100 Task Timeout
STRUCTAI-5200 Task Cancelled
STRUCTAI-5300 Task Recovery Error
STRUCTAI-6000 Adapter Error
STRUCTAI-6100 Resource Locked
STRUCTAI-6200 Artifact Error
STRUCTAI-7000 Internal Error
```

---

# 11. `app/domain/protocols.py`

定义应用层需要的接口。

例如：

```python
class Repository(Protocol):
    async def get(self, entity_id):
        ...


class UnitOfWork(Protocol):
    async def commit(self):
        ...

    async def rollback(self):
        ...


class ArtifactStorage(Protocol):
    async def put(self, data, metadata):
        ...

    async def get(self, artifact_id):
        ...

    async def delete(self, artifact_id):
        ...
```

这样 Domain/Application 不依赖具体数据库和文件系统。

---

# 12. Database Layer

目录：

```text
app/infrastructure/database/
├── base.py
├── session.py
├── models/
├── repositories/
└── migrations/
```

---

# 13. `database/base.py`

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

所有 ORM Model 从 `Base` 继承。

---

# 14. `database/session.py`

负责：

```text
AsyncEngine
async_sessionmaker
AsyncSession
```

示例：

```python
engine = create_async_engine(
    settings.database_url,
    future=True,
)

SessionFactory = async_sessionmaker(
    engine,
    expire_on_commit=False,
)
```

---

# 15. ORM Models

建议拆分：

```text
models/
├── tenant.py
├── user.py
├── role.py
├── permission.py
├── session.py
├── project.py
├── software.py
├── model.py
├── document.py
├── capability.py
├── operation.py
├── task.py
├── artifact.py
├── lock.py
├── idempotency.py
├── audit.py
└── __init__.py
```

禁止把所有模型写进一个 3000 行文件。

---

# 16. Repository Layer

例如：

```text
repositories/
├── user.py
├── tenant.py
├── project.py
├── software.py
├── model.py
├── document.py
├── capability.py
├── operation.py
├── task.py
├── artifact.py
├── lock.py
├── idempotency.py
└── audit.py
```

Repository 只负责持久化。

不允许 Repository 执行：

```text
RBAC
Adapter
MCP
Task business logic
```

---

# 17. UnitOfWork

文件：

```text
app/infrastructure/database/unit_of_work.py
```

接口：

```python
class SQLAlchemyUnitOfWork:
    session: AsyncSession

    async def __aenter__(self):
        ...

    async def __aexit__(self, exc_type, exc, tb):
        ...

    async def commit(self):
        ...

    async def rollback(self):
        ...
```

要求：

```text
一个业务事务
=
一个明确 UnitOfWork
```

---

# 18. Registry

目录：

```text
app/infrastructure/registry/
├── software_registry.py
├── capability_registry.py
├── operation_registry.py
├── schema_registry.py
└── api_registry.py
```

---

# 19. SoftwareRegistry

职责：

```text
Vendor
Product
Version
Instance
```

查询：

```python
get_instance(instance_id)
get_product(product_id)
get_version(version_id)
list_instances()
```

---

# 20. CapabilityRegistry

Capability 例如：

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

# 21. OperationRegistry

定义：

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
    recovery_policy: str
```

并注册全部冻结 Operation。

---

# 22. SchemaRegistry

目录：

```text
schemas/
├── model/
│   ├── node/
│   │   └── v1.json
│   ├── element/
│   └── material/
├── task/
├── result/
├── tool/
└── common/
```

Schema ID：

```text
structai://schema/model/node/v1
structai://schema/model/node/v2
```

JSON Schema Draft 2020-12。

---

# 23. API Registry

文件：

```text
app/infrastructure/registry/api_registry.py
```

API Registry 只保存：

```text
software
product
version
operation
protocol
method
path
request_schema
response_schema
```

例如：

```json
{
  "software": "MIDAS",
  "product": "CIVIL NX",
  "version": "2026",
  "operation": "ANALYSIS.STATIC",
  "protocol": "REST",
  "method": "POST",
  "path": "/anal/STATIC"
}
```

注意：

API Registry 是映射数据。

复杂转换逻辑放 Adapter，不放数据库中执行任意 Python。

---

# 24. Authentication

目录：

```text
application/security/
├── authentication.py
├── password.py
├── session.py
├── token.py
├── rbac.py
├── permission.py
└── effective_permission.py
```

---

# 25. AuthenticationService

接口：

```python
class AuthenticationService:
    async def authenticate(
        self,
        username: str,
        password: str,
    ) -> IdentityContext:
        ...
```

必须处理：

```text
用户不存在
密码错误
账号锁定
Session
登录失败计数
登录审计
```

密码使用：

```text
Argon2id
```

---

# 26. IdentityContext

文件：

```text
app/application/security/context.py
```

定义：

```python
@dataclass(frozen=True)
class IdentityContext:
    user_id: UUID
    tenant_id: UUID
    session_id: UUID | None
    roles: tuple[str, ...] = ()
    authentication_method: str = "unknown"
```

重要规则：

```text
user_id
tenant_id
roles
permissions
```

不得由 AI Client 直接提交后被信任。

必须由 Server Authentication 生成。

---

# 27. Effective Permission

计算：

```text
User
 ↓
Global Roles
 ↓
Tenant Roles
 ↓
Project Roles
 ↓
Resource ACL
 ↓
Explicit Deny
 ↓
Effective Permissions
```

AI Agent：

```text
Effective User Permission
        ∩
Agent Permission
```

不得扩大权限。

---

# 28. Resource Resolver

文件：

```text
application/resource/resolver.py
```

负责：

```text
software_instance_id
project_id
model_id
document_id
```

解析成：

```text
SoftwareContext
ProjectContext
ResourceContext
```

---

# 29. ExecutionContext

文件：

```text
application/execution/context.py
```

```python
@dataclass(frozen=True)
class SoftwareContext:
    instance_id: UUID | None = None
    product: str | None = None
    version: str | None = None


@dataclass(frozen=True)
class ProjectContext:
    project_id: UUID | None = None


@dataclass(frozen=True)
class ExecutionContext:
    request_id: str
    trace_id: str
    identity: IdentityContext
    software: SoftwareContext
    project: ProjectContext
```

扩展时可以加入：

```text
model_id
document_id
session_id
task_id
```

但必须保持上下文职责单一。

---

# 30. Validation Pipeline

文件：

```text
application/execution/pipeline.py
```

顺序冻结：

```text
Input
 ↓
Schema Validation
 ↓
Engineering Validation
 ↓
Permission
 ↓
Confirmation
 ↓
Capability
 ↓
Execution
```

完整运行时实际链：

```text
Authenticate
 ↓
IdentityContext
 ↓
ExecutionContext
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
Preconditions
 ↓
Effective Permission
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
Task / Transaction
 ↓
Adapter
 ↓
Result Normalize
 ↓
Postconditions
 ↓
Release Lock
 ↓
Persist Result
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

# 31. Engineering Validation

文件：

```text
application/execution/engineering_validator.py
```

检查：

```text
几何合法性
节点 ID
坐标
元素连接
材料
截面
荷载
边界
工程参数
```

例如：

```text
节点 ID 不得重复
元素引用节点必须存在
长度不得为 0
材料必须存在
截面必须存在
```

Schema Validation 不等于 Engineering Validation。

---

# 32. Preconditions / Postconditions

文件：

```text
application/execution/preconditions.py
application/execution/postconditions.py
```

例如：

```text
MODEL.NODE.CREATE
Precondition:
    model 可写

Postcondition:
    node 存在
```

```text
ANALYSIS.STATIC
Precondition:
    model 完整
    software 已连接
    capability 存在

Postcondition:
    analysis task 已完成
    result 可查询
```

---

# 33. Confirmation

文件：

```text
application/execution/confirmation.py
```

规则：

```text
LOW
无需确认

MEDIUM
根据策略

HIGH
默认需要确认

CRITICAL
必须确认
```

确认 Token 不得永久有效。

---

# 34. Capability Resolver

文件：

```text
application/services/capability_resolver.py
```

方法：

```python
async def supports(
    instance_id,
    capability,
) -> bool:
    ...
```

能力来源：

```text
Static Manifest
+
Runtime Detection
```

缓存：

```text
instance
version
capability
checked_at
expires_at
```

软件重连或版本改变时必须重新验证。

---

# 35. Resource Lock

目录：

```text
application/resource/
├── lock_manager.py
└── lock_policy.py
```

规则：

```text
READ + READ = allowed
READ + WRITE = blocked
WRITE + WRITE = blocked
EXCLUSIVE = blocks all
```

资源：

```text
Software Instance
Model
Document
```

桌面工程软件默认：

```text
SERIAL
```

---

# 36. Optimistic Concurrency

所有重要可变资源具有：

```text
version
```

更新：

```json
{
  "expected_version": 12
}
```

数据库当前：

```text
version = 13
```

则：

```text
STRUCTAI-1300
```

不得覆盖新版本。

---

# 37. Idempotency

文件：

```text
application/execution/idempotency.py
```

唯一键：

```text
tenant_id + idempotency_key
```

必须使用数据库唯一约束解决并发。

禁止：

```text
SELECT
 ↓
if not exists
 ↓
INSERT
```

这种方式存在 race condition。

必须：

```text
Atomic Insert
 ↓
Unique Conflict
 ↓
Return Existing Result
```

适用于：

```text
CREATE
ASSIGN
DELETE
BUILD
ANALYSIS
DESIGN
```

---

# 38. Adapter Framework

目录：

```text
infrastructure/adapters/
├── base/
│   ├── adapter.py
│   ├── manifest.py
│   ├── errors.py
│   └── registry.py
├── mock/
│   └── adapter.py
└── plugins/
```

---

# 39. EngineeringSoftwareAdapter

```python
from abc import ABC, abstractmethod


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
        context: ExecutionContext,
    ) -> dict:
        ...

    async def cancel(self, task_id: str) -> None:
        raise NotImplementedError

    async def normalize_error(
        self,
        error: Exception,
    ) -> dict:
        ...
```

---

# 40. Adapter Responsibilities

Adapter 负责：

```text
1. Connection
2. Authentication
3. Version Detection
4. Capability Detection
5. Operation Mapping
6. Parameter Transformation
7. Native Execution
8. Response Transformation
9. Error Normalization
10. Health Check
```

Adapter 不负责：

```text
MCP
RBAC
Global Task Lifecycle
Global Audit
AI
UI
```

---

# 41. Adapter Manifest

```json
{
  "name": "midas.civil",
  "vendor": "MIDAS",
  "product": "CIVIL NX",
  "supported_versions": [
    "2025",
    "2026"
  ],
  "capabilities": [],
  "protocols": [
    "REST"
  ]
}
```

---

# 42. Plugin Loading

`pyproject.toml`：

```toml
[project.entry-points."structai.adapters"]
midas.civil = "structai_midas.adapter:CivilAdapter"
```

Core 只发现 Plugin。

Core 不 import：

```python
from midas import ...
```

---

# 43. Mock Adapter

这是 Core Alpha 的第一真实 Adapter。

文件：

```text
infrastructure/adapters/mock/adapter.py
```

Mock Adapter 必须实现：

```text
MODEL.NODE.QUERY
MODEL.NODE.CREATE
MODEL.NODE.UPDATE
MODEL.NODE.DELETE

MODEL.ELEMENT.QUERY
MODEL.ELEMENT.CREATE
MODEL.ELEMENT.UPDATE
MODEL.ELEMENT.DELETE

MODEL.MATERIAL.ASSIGN
MODEL.SECTION.ASSIGN
MODEL.BOUNDARY.ASSIGN
MODEL.LOAD.ASSIGN

BUILD.COLUMN
BUILD.BEAM

ANALYSIS.STATIC

RESULT.NODE.DISPLACEMENT
RESULT.ELEMENT.FORCE

DESIGN.STEEL
```

Mock Adapter 内部维护 Canonical Model。

---

# 44. Canonical Model

最小结构：

```python
@dataclass
class EngineeringNode:
    id: int
    x: float
    y: float
    z: float
```

```python
@dataclass
class EngineeringElement:
    id: int
    type: str
    node_ids: list[int]
    material_id: int | None
    section_id: int | None
```

进一步：

```text
Material
Section
Boundary
Load
Group
Analysis
Result
Design
```

---

# 45. Mock Adapter BUILD.COLUMN

输入：

```json
{
  "base_node": {
    "x": 0,
    "y": 0,
    "z": 0
  },
  "height": 6,
  "material": "Q355B",
  "section": "H400x400x13x21"
}
```

内部：

```text
Create bottom node
Create top node
Create column element
Assign material
Assign section
```

返回：

```json
{
  "node_ids": [1, 2],
  "element_ids": [1]
}
```

---

# 46. Task Engine

目录：

```text
application/task/
├── engine.py
├── queue.py
├── worker.py
├── state_machine.py
├── scheduler.py
├── dag.py
├── lease.py
├── recovery.py
├── cancellation.py
└── progress.py
```

---

# 47. Task State Machine

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

异常：

```text
FAILED
TIMEOUT
CANCELLED
RETRYING
RECOVERING
```

禁止非法状态跳转。

---

# 48. TaskEngine

核心：

```python
class TaskEngine:

    async def submit(self, request) -> Task:
        ...

    async def get(self, task_id) -> Task:
        ...

    async def cancel(self, task_id) -> None:
        ...

    async def retry(self, task_id) -> None:
        ...

    async def recover(self) -> None:
        ...
```

---

# 49. Scheduler

Core Alpha：

```python
asyncio.Queue
```

支持：

```text
priority
concurrency
software instance serialization
```

未来可以替换为：

```text
Redis
RabbitMQ
NATS
Kafka
```

但 Application Interface 不改变。

---

# 50. Worker

Worker：

```text
取 Task
 ↓
获取 Lease
 ↓
RUNNING
 ↓
获取 Lock
 ↓
执行 Pipeline
 ↓
Adapter
 ↓
更新 Progress
 ↓
保存 Result
 ↓
COMPLETED
 ↓
释放 Lock
```

---

# 51. Task Lease

字段：

```text
lease_owner
lease_until
last_heartbeat
```

Worker 必须周期性 heartbeat。

---

# 52. Recovery

服务重启：

```text
查询未完成 Task
 ↓
检查 lease
 ↓
lease 已失效
 ↓
RECOVERING
 ↓
REQUEUE / RESUME / FAIL
```

绝不能把：

```text
RUNNING
```

永久留在数据库。

---

# 53. Cancellation

```python
async def cancel(task_id):
    task.status = CANCEL_REQUESTED
    await adapter.cancel(task_id)
```

如果软件不支持真正取消：

```text
记录实际状态
```

不得伪造：

```text
CANCELLED
```

---

# 54. Task DAG

```text
Task
 ├── Step A
 ├── Step B
 ├── Step C → A
 └── Step D → B,C
```

依赖满足后才能执行。

---

# 55. Artifact Storage

目录：

```text
infrastructure/storage/
├── base.py
├── local.py
└── manager.py
```

接口：

```python
class ArtifactStorage(Protocol):

    async def put(
        self,
        data,
        metadata,
    ):
        ...

    async def get(
        self,
        artifact_id,
    ):
        ...

    async def delete(
        self,
        artifact_id,
    ):
        ...
```

---

# 56. LocalFilesystemStorage

第一实现：

```text
./data/artifacts/
```

数据库保存：

```text
artifact_id
storage_backend
storage_key
mime_type
size
checksum
```

支持：

```text
JSON
CSV
PDF
模型文件
分析结果
截图
```

---

# 57. Document Service

文件：

```text
application/services/document.py
```

生命周期：

```text
NEW
OPEN
SAVE
SAVE_AS
CLOSE
INFO
```

核心方法：

```python
new()
open()
save()
save_as()
close()
info()
```

Document Service 不知道：

```text
MIDAS
ETABS
SAP2000
```

---

# 58. Event Bus

目录：

```text
infrastructure/events/
├── bus.py
└── in_process.py
```

Core Alpha：

```python
class InProcessEventBus:
    async def publish(self, event):
        ...
```

事件：

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
```

---

# 59. Notification Service

预留：

```text
MCP Notification
Webhook
WebSocket
UI
Email
```

第一阶段可以只实现：

```text
InProcess
```

---

# 60. Quota / Rate Limit

文件：

```text
application/services/quota.py
```

维度：

```text
User
Tenant
AI Agent
Software Instance
```

指标：

```text
max_tasks
max_concurrent_tasks
max_api_requests
max_storage
max_projects
```

Core Alpha：

```text
In-memory limiter
```

未来：

```text
Redis
```

---

# 61. Observability

目录：

```text
observability/
├── tracing.py
├── metrics.py
└── audit.py
```

---

# 62. Structured Logging

字段：

```text
timestamp
level
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
message
```

绝不输出：

```text
password
API key
token
private key
secret
```

---

# 63. Trace

Span：

```text
MCP
Tool
Operation
Schema
Validation
Permission
Capability
Task
Lock
Adapter
Native API
Result
Audit
```

Core Alpha 可以首先实现：

```text
request_id
trace_id
structured logs
```

再扩展 OpenTelemetry。

---

# 64. Metrics

至少：

```text
structai_requests_total
structai_request_duration_seconds
structai_task_total
structai_task_duration_seconds
structai_task_failed_total
structai_adapter_requests_total
structai_adapter_errors_total
structai_active_tasks
structai_mcp_connections
```

---

# 65. Audit

文件：

```text
observability/audit.py
```

字段：

```text
audit_id
timestamp
tenant_id
user_id
action
resource
result
previous_hash
entry_hash
```

Hash Chain：

```text
Entry N
 ↓
previous_hash
 ↓
current entry
 ↓
entry_hash
```

普通用户不得删除。

---

# 66. Backup / Restore

目录：

```text
application/services/backup.py
```

操作：

```text
backup
restore
integrity-check
```

SQLite：

```text
SQLite backup
+
Registry data
+
Artifact metadata
```

恢复后：

```text
Integrity Check
 ↓
Registry Validation
 ↓
Task Recovery
```

---

# 67. MCP Layer

目录：

```text
interfaces/mcp/
├── server.py
├── context.py
├── dispatcher.py
├── responses.py
├── errors.py
└── tools/
```

---

# 68. MCP Server

`server.py` 负责：

```text
初始化 MCP Server
注册 9 Tool
初始化 Application Container
绑定 Tool Dispatcher
启动 Transport
```

不得在 `server.py` 写业务逻辑。

---

# 69. MCP Context

负责：

```text
MCP Session
Request ID
Trace ID
Authentication Context
Execution Context
```

客户端可以提供：

```json
{
  "software_instance_id": "uuid",
  "project_id": "uuid",
  "model_id": "uuid",
  "document_id": "uuid"
}
```

不能提供并覆盖：

```text
user_id
tenant_id
roles
effective_permissions
```

---

# 70. Unified ToolRequest

```python
class ToolRequest(BaseModel):
    operation: str
    parameters: dict = {}
    context: dict = {}
    idempotency_key: str | None = None
    confirmation_token: str | None = None
    dry_run: bool = False
```

---

# 71. Unified Response

同步：

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

异步：

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

# 72. Tool Dispatcher

文件：

```text
interfaces/mcp/dispatcher.py
```

核心：

```python
class ToolDispatcher:

    async def dispatch(
        self,
        tool_name: str,
        request: ToolRequest,
        context: MCPContext,
    ):
        ...
```

流程：

```text
tool_name
 ↓
Tool Registry
 ↓
Operation Registry
 ↓
Execution Service
```

Dispatcher 不直接执行 Adapter。

---

# 73. Tool Base Class

```python
class BaseEngineeringTool(ABC):

    name: str

    @abstractmethod
    async def handle(
        self,
        request: ToolRequest,
        context: MCPContext,
    ):
        ...
```

Tool 只负责：

```text
接收请求
解析请求
调用 Application Service
返回统一结果
```

---

# 74. 9 MCP Tools

目录：

```text
interfaces/mcp/tools/
├── engineering_doc.py
├── engineering_model_query.py
├── engineering_model_assign.py
├── engineering_model_delete.py
├── engineering_model_build.py
├── engineering_view.py
├── engineering_result.py
├── engineering_design.py
└── engineering_analysis.py
```

---

# 75. `engineering_doc`

操作：

```text
NEW
OPEN
SAVE
SAVE_AS
CLOSE
INFO
```

权限：

```text
DOCUMENT_READ
DOCUMENT_WRITE
```

风险：

```text
MEDIUM
```

---

# 76. `engineering_model_query`

操作：

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

默认：

```text
SYNC
LOW
READ
```

支持：

```text
pagination
cursor
filters
```

---

# 77. `engineering_model_assign`

操作：

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

需要：

```text
MODEL_WRITE
```

重要修改支持：

```text
idempotency
version
dry_run
transaction
```

---

# 78. `engineering_model_delete`

操作：

```text
MODEL.NODE.DELETE
MODEL.ELEMENT.DELETE
MODEL.LOAD.DELETE
MODEL.BOUNDARY.DELETE
MODEL.GROUP.DELETE
MODEL.MATERIAL.DELETE
MODEL.SECTION.DELETE
```

默认：

```text
HIGH
ASYNC
```

需要：

```text
MODEL_DELETE
```

通常需要确认。

---

# 79. `engineering_model_build`

操作：

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

默认：

```text
HIGH
ASYNC
```

---

# 80. `engineering_view`

操作：

```text
VIEW.MODEL
VIEW.DEFORMED_MODEL
VIEW.REACTION
VIEW.DISPLACEMENT
VIEW.STRESS
VIEW.FORCE
VIEW.MODE_SHAPE
```

默认：

```text
LOW
SYNC
```

---

# 81. `engineering_result`

操作：

```text
RESULT.NODE.DISPLACEMENT
RESULT.NODE.REACTION
RESULT.ELEMENT.FORCE
RESULT.ELEMENT.STRESS
RESULT.MODE.SHAPE
RESULT.ANALYSIS.SUMMARY
```

默认：

```text
LOW
SYNC
```

大结果必须分页。

---

# 82. `engineering_design`

操作：

```text
DESIGN.STEEL
DESIGN.CONCRETE
DESIGN.SRC
DESIGN.FOUNDATION
DESIGN.CODE_CHECK
DESIGN.OPTIMIZE
```

默认：

```text
HIGH
ASYNC
```

需要：

```text
DESIGN_EXECUTE
```

优化还需要：

```text
DESIGN_MODIFY
```

---

# 83. `engineering_analysis`

操作：

```text
ANALYSIS.STATIC
ANALYSIS.MODAL
ANALYSIS.SEISMIC
ANALYSIS.SPECTRUM
ANALYSIS.BUCKLING
ANALYSIS.TIME_HISTORY
ANALYSIS.NONLINEAR
```

默认：

```text
HIGH
ASYNC
```

需要：

```text
ANALYSIS_EXECUTE
```

---

# 84. Tool Schema

所有 Tool 使用 JSON Schema Draft 2020-12。

统一：

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
    }
  },
  "required": [
    "operation"
  ]
}
```

---

# 85. Operation Dispatch

示例：

```python
operation = registry.get(request.operation)

if operation.tool != tool.name:
    raise ProtocolError(...)

return await execution_service.execute(
    operation=operation,
    parameters=request.parameters,
    context=context,
)
```

---

# 86. Application Execution Service

文件：

```text
application/execution/service.py
```

核心：

```python
class ExecutionService:

    async def execute(
        self,
        operation,
        parameters,
        context,
        request,
    ):
        ...
```

必须串联：

```text
Validation
Permission
Confirmation
Quota
Idempotency
Lock
Capability
Task
Adapter
Result
Audit
Event
```

---

# 87. Adapter Resolution

文件：

```text
application/services/adapter_resolver.py
```

输入：

```text
software_instance_id
operation
```

输出：

```text
Adapter
```

解析：

```text
Software Instance
 ↓
Vendor/Product/Version
 ↓
Adapter Manifest
 ↓
Capability
 ↓
API Registry
 ↓
Adapter
```

---

# 88. API Mapping

例如：

```text
ANALYSIS.STATIC
```

MIDAS：

```text
REST POST /anal/STATIC
```

ETABS：

```text
COM RunAnalysis
```

OpenSees：

```text
SCRIPT analyze
```

Core 只看到：

```text
ANALYSIS.STATIC
```

---

# 89. Native Response Normalization

Native：

```text
MIDAS response
```

Adapter 转换：

```text
Canonical Result
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

AI Client 不需要知道：

```text
MIDAS JSON
ETABS COM
OpenSees Tcl
```

---

# 90. Pagination

Query：

```json
{
  "data": [],
  "pagination": {
    "has_more": true,
    "next_cursor": "..."
  }
}
```

禁止：

```text
一次返回整个百万节点模型
```

---

# 91. Batch

Model 操作支持：

```json
{
  "items": [
    {},
    {},
    {}
  ]
}
```

必须明确：

```text
atomic
non_atomic
```

Atomic：

```text
全部成功
OR
全部 rollback
```

Non-Atomic：

```text
逐项执行
逐项记录结果
```

---

# 92. Dry Run

支持的 Operation：

```text
CREATE
UPDATE
ASSIGN
BUILD
DELETE
DESIGN
```

返回：

```json
{
  "mode": "DRY_RUN",
  "changes": [],
  "warnings": []
}
```

不得修改真实模型。

---

# 93. Transaction / Rollback

支持事务的操作：

```text
MODEL.NODE.CREATE
MODEL.ELEMENT.CREATE
MODEL.NODE.UPDATE
MODEL.ELEMENT.UPDATE
MODEL.MATERIAL.ASSIGN
MODEL.SECTION.ASSIGN
MODEL.BOUNDARY.ASSIGN
MODEL.LOAD.ASSIGN
```

对于 native software 不支持真正 transaction 的情况：

```text
记录已执行步骤
 ↓
执行 compensating actions
 ↓
rollback
```

如果 rollback 失败：

```text
STRUCTAI-5300
```

并进入人工处理/恢复流程。

---

# 94. Health

HTTP：

```text
GET /livez
GET /readyz
GET /health
```

定义：

```text
livez
=
Process Alive
```

```text
readyz
=
Core DB
+
Registry
+
Task Engine
```

```text
health
=
DB
+
Registry
+
Task Engine
+
Adapter Manager
+
Software Instances
```

单个 MIDAS 不可用不得导致：

```text
Core ready = false
```

---

# 95. HTTP Management API

不是 MCP Tool。

用于：

```text
健康
系统管理
Adapter
软件实例
Task
Logs
Metrics
```

目录：

```text
interfaces/http/
├── api.py
├── health.py
└── management/
    ├── software.py
    ├── tasks.py
    └── system.py
```

---

# 96. MCP Transport

第一阶段：

```text
STDIO
```

第二阶段：

```text
Streamable HTTP
```

Core 不绑定 Transport。

---

# 97. STDIO

启动：

```bash
python -m app.main
```

配置：

```env
MCP_TRANSPORT=stdio
```

STDIO 不应该输出普通日志到 stdout。

日志必须：

```text
stderr
```

否则可能污染 MCP Protocol。

---

# 98. Streamable HTTP

使用 MCP SDK 提供的 Streamable HTTP 能力。

HTTP 层负责：

```text
session
authentication
transport
request
notification
```

业务继续走：

```text
ToolDispatcher
```

---

# 99. MCP Progress

Task Engine：

```text
progress = 43
```

映射为：

```text
MCP Progress Notification
```

Cancellation：

```text
MCP cancel
 ↓
TaskEngine.cancel()
 ↓
Adapter.cancel()
```

---

# 100. Seed Data

目录：

```text
scripts/
├── seed.py
├── seed_permissions.py
├── seed_operations.py
├── seed_capabilities.py
└── seed_mock.py
```

Seed：

```text
default tenant
admin user
roles
permissions
9 tools
operations
capabilities
mock software
mock instance
```

---

# 101. Mock Software

注册：

```text
Vendor:
StructAI

Product:
Mock Engineering Software

Version:
1.0
```

能力：

```text
MODEL.NODE.READ
MODEL.NODE.WRITE
MODEL.NODE.DELETE
MODEL.ELEMENT.READ
MODEL.ELEMENT.WRITE
MODEL.ELEMENT.DELETE
ANALYSIS.STATIC
RESULT.DISPLACEMENT
RESULT.ELEMENT_FORCE
DESIGN.STEEL
```

---

# 102. Alembic

目录：

```text
migrations/
├── env.py
├── script.py.mako
└── versions/
```

命令：

```bash
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

禁止运行时自动：

```text
create_all()
```

生产数据库必须使用 Migration。

---

# 103. Test Architecture

```text
tests/
├── unit/
├── contract/
├── integration/
├── recovery/
├── security/
├── concurrency/
└── e2e/
```

---

# 104. Unit Tests

测试：

```text
Domain
Value Objects
State Machine
RBAC
Capability
Schema
Validation
Lock
Idempotency
Operation Registry
```

例如：

```text
test_task_state_machine.py
test_permission.py
test_capability.py
test_lock_manager.py
test_idempotency.py
```

---

# 105. Contract Tests

Adapter 必须满足统一 Contract。

例如：

```python
async def test_adapter_health(adapter):
    result = await adapter.health_check()
    assert result["healthy"] is True
```

所有 Adapter：

```text
Mock
MIDAS
ETABS
ANSYS
```

必须通过同一 Contract。

---

# 106. Integration Tests

验证：

```text
SQLite
Repository
UnitOfWork
Task Engine
Adapter
Artifact
Event
Audit
```

---

# 107. Security Tests

必须测试：

```text
未认证
无权限
跨 Tenant
跨 Project
AI 权限提升
过期 Session
错误密码
账号锁定
Confirmation bypass
```

重点：

```text
AI Client 提交 user_id
```

服务器必须忽略/拒绝覆盖。

---

# 108. Concurrency Tests

测试：

```text
READ + READ
READ + WRITE
WRITE + WRITE
```

以及：

```text
两个 CREATE
同一个 idempotency_key
两个 UPDATE
expected_version 冲突
```

必须证明不会：

```text
重复创建
数据覆盖
死锁
```

---

# 109. Recovery Tests

模拟：

```text
Worker crash
Server restart
Adapter timeout
Task timeout
Lock orphan
Lease expiration
```

确认：

```text
RECOVERING
 ↓
REQUEUE / RESUME / FAIL
```

---

# 110. E2E Test

第一条完整 E2E：

```text
Connect MCP
 ↓
List Tools
 ↓
List Capabilities
 ↓
BUILD.COLUMN
 ↓
MODEL.NODE.QUERY
 ↓
MODEL.ELEMENT.QUERY
 ↓
MODEL.LOAD.ASSIGN
 ↓
ANALYSIS.STATIC
 ↓
Poll Task
 ↓
RESULT.NODE.DISPLACEMENT
 ↓
RESULT.ELEMENT.FORCE
 ↓
DESIGN.STEEL
```

---

# 111. Generic AI Client E2E

输入：

> 创建一个高度 6m 的 Q355B H400×400×13×21 钢柱，底部固定，顶部施加 500kN 轴压力。完成静力分析，并返回顶部节点位移和钢柱设计利用率。

预期 Tool Chain：

```text
engineering_model_build
    BUILD.COLUMN

engineering_model_assign
    MODEL.BOUNDARY.ASSIGN
    MODEL.LOAD.ASSIGN

engineering_analysis
    ANALYSIS.STATIC

engineering_result
    RESULT.NODE.DISPLACEMENT

engineering_design
    DESIGN.STEEL
```

---

# 112. E2E Acceptance

必须验证：

```text
1. MCP Connect
2. Tool Discovery
3. Capability Discovery
4. Build Column
5. Query Nodes
6. Query Elements
7. Assign Boundary
8. Assign Load
9. Static Analysis
10. Task Poll
11. Displacement Result
12. Element Force Result
13. Steel Design
14. Audit
15. Trace
```

---

# 113. Implementation Sequence

## P0 — Bootstrap

```text
pyproject.toml
settings
logging
main
database
Alembic
```

## P1 — Domain

```text
enums
entities
value objects
errors
protocols
```

## P2 — Persistence

```text
ORM
repositories
UnitOfWork
seed
```

## P3 — Registry

```text
SoftwareRegistry
CapabilityRegistry
OperationRegistry
SchemaRegistry
APIRegistry
```

## P4 — Security

```text
Authentication
Password
Session
RBAC
Effective Permission
```

## P5 — Execution Core

```text
ExecutionContext
Resource Resolver
Validation
Capability
Confirmation
Quota
Idempotency
Lock
```

## P6 — Adapter

```text
Adapter Base
Manifest
Plugin Loader
Mock Adapter
```

## P7 — Task

```text
Task State
Queue
Worker
Scheduler
DAG
Lease
Recovery
Cancellation
```

## P8 — Artifact

```text
Artifact
Local Storage
Document Service
```

## P9 — Observability

```text
Event Bus
Audit
Trace
Metrics
Health
```

## P10 — MCP

```text
MCP Server
Dispatcher
Context
Responses
9 Tools
```

## P11 — Transport

```text
STDIO
Streamable HTTP
```

## P12 — Tests

```text
Unit
Contract
Integration
Security
Concurrency
Recovery
E2E
```

---

# 114. First Runnable Milestone

完成：

```text
Settings
+
SQLite
+
Registry
+
Mock Adapter
+
ExecutionContext
+
Permission
+
Capability
+
Task Engine
+
engineering_model_build
```

即可执行：

```text
BUILD.COLUMN
```

并得到：

```json
{
  "success": true,
  "data": {
    "node_ids": [1, 2],
    "element_ids": [1]
  }
}
```

---

# 115. Second Runnable Milestone

增加：

```text
MODEL.NODE.QUERY
MODEL.ELEMENT.QUERY
MODEL.LOAD.ASSIGN
```

得到：

```text
BUILD
 ↓
QUERY
 ↓
ASSIGN LOAD
```

---

# 116. Third Runnable Milestone

增加：

```text
ANALYSIS.STATIC
```

Task：

```text
QUEUED
 ↓
RUNNING
 ↓
PROCESSING
 ↓
COMPLETED
```

---

# 117. Fourth Runnable Milestone

增加：

```text
RESULT.NODE.DISPLACEMENT
RESULT.ELEMENT.FORCE
```

形成：

```text
Model
 ↓
Analysis
 ↓
Result
```

---

# 118. Fifth Runnable Milestone

增加：

```text
DESIGN.STEEL
```

形成：

```text
Build
 ↓
Load
 ↓
Analysis
 ↓
Result
 ↓
Design
```

---

# 119. MIDAS Adapter 接入

Core Alpha 完成后：

```text
infrastructure/adapters/plugins/
```

新增：

```text
structai_midas/
├── __init__.py
├── adapter.py
├── manifest.py
├── client.py
├── capabilities.py
├── operations.py
├── transforms.py
├── errors.py
└── health.py
```

Core 不修改：

```text
9 MCP Tools
Task Engine
RBAC
MCP Protocol
Canonical Model
Execution Pipeline
```

---

# 120. MIDAS Adapter 内部结构

```text
StructAI Operation
 ↓
MIDAS Adapter
 ↓
API Registry
 ↓
Native Endpoint
 ↓
MIDAS Response
 ↓
Transform
 ↓
Canonical Result
```

例如：

```text
ANALYSIS.STATIC
```

映射：

```text
MIDAS CIVIL NX 2026
POST /anal/STATIC
```

实际接口路径和参数必须依据对应 MIDAS API Registry / API 文档注册，不能硬编码到 Core。

---

# 121. Second Software Acceptance

增加第二个真实软件后：

必须确认：

```text
MCP Protocol 无修改
9 Tool Contract 无修改
AI Client 无修改
Task Engine 无修改
Security 无修改
```

正常只增加：

```text
Adapter
Capability Mapping
Operation Mapping
API Registry
```

如果增加第二软件必须修改 9 Tool，则说明抽象层出现泄漏，需要重新审查。

---

# 122. Dependency Direction

冻结：

```text
Interface
    ↓
Application
    ↓
Domain
```

Infrastructure：

```text
Infrastructure
    ↓
Domain / Application Interfaces
```

禁止：

```text
Domain → SQLAlchemy
Domain → FastAPI
Domain → MCP
Domain → MIDAS
```

---

# 123. Application Container

文件：

```text
app/container.py
```

负责组装：

```text
Settings
Database
Repositories
Registry
Security
TaskEngine
AdapterManager
ArtifactStorage
EventBus
ExecutionService
ToolDispatcher
```

依赖注入集中管理。

禁止：

```python
global TaskEngine()
```

在业务文件中随意创建。

---

# 124. Application Bootstrap

`app/main.py`：

```text
load settings
 ↓
init logging
 ↓
init DB
 ↓
init repositories
 ↓
init registry
 ↓
init security
 ↓
init adapter manager
 ↓
init task engine
 ↓
init execution service
 ↓
register tools
 ↓
start MCP
```

---

# 125. Shutdown

必须支持：

```text
SIGINT
SIGTERM
```

关闭顺序：

```text
Stop accepting requests
 ↓
Stop scheduling new tasks
 ↓
Graceful task shutdown
 ↓
Release locks
 ↓
Close adapters
 ↓
Close DB
 ↓
Flush logs
 ↓
Exit
```

---

# 126. Database Transaction Rules

一个数据库事务不得无限包含：

```text
长时间 Native API 调用
```

正确：

```text
DB transaction
 ↓
prepare
 ↓
commit necessary state
 ↓
native execution
 ↓
persist result
```

长时间分析不能长期占用 SQLite transaction。

---

# 127. Native API Timeout

Adapter 必须支持：

```text
connect timeout
request timeout
analysis timeout
```

统一转换：

```text
STRUCTAI-2300
```

Task 层转换：

```text
STRUCTAI-5100
```

---

# 128. Error Boundary

每层负责转换：

```text
Native Exception
 ↓
Adapter Error
 ↓
Application Error
 ↓
MCP Error
```

不能把：

```text
Python traceback
MIDAS API Key
HTTP Authorization
```

直接返回 AI Client。

---

# 129. Security Boundary

安全边界：

```text
MCP Client
     X
      ↓
Authentication
      ↓
Identity
      ↓
RBAC
      ↓
Resource ACL
      ↓
Execution
```

任何 Tool 都不能绕过。

---

# 130. AI Engineering Agent

AI Agent 不属于 Core Tool。

它属于上层 Client / Application。

AI：

```text
理解工程意图
 ↓
选择 Tool
 ↓
构造参数
 ↓
调用 MCP
 ↓
解释结果
```

Core：

```text
验证
授权
执行
记录
```

Core 不依赖具体 LLM。

---

# 131. AI 权限模型

如果 AI Agent 被限制：

```text
MODEL_READ
ANALYSIS_EXECUTE
RESULT_READ
```

即使用户有：

```text
MODEL_DELETE
DESIGN_MODIFY
```

Agent 也不能执行。

有效权限：

```text
UserPermission ∩ AgentPermission
```

---

# 132. Logging Rule

日志中允许：

```text
operation
tool
software
version
request_id
trace_id
duration
status
```

禁止：

```text
password
token
API Key
private key
secret
完整 Authorization header
```

---

# 133. File-Level Definition

每一个实现文件在进入编码阶段都必须回答：

```text
1. 为什么存在？
2. 谁调用？
3. 调用谁？
4. 输入是什么？
5. 输出是什么？
6. 异常是什么？
7. 是否访问数据库？
8. 是否访问 Adapter？
9. 是否需要事务？
10. 是否需要 Lock？
11. 是否需要 Audit？
12. 是否需要 Event？
13. 如何测试？
```

---

# 134. Implementation Rules

## Rule 1

Domain 不依赖 Infrastructure。

## Rule 2

Tool 不直接操作数据库。

## Rule 3

Tool 不直接调用 Adapter。

## Rule 4

Adapter 不实现 RBAC。

## Rule 5

AI 不拥有独立于用户的越权能力。

## Rule 6

所有写操作必须经过版本/锁/idempotency 策略。

## Rule 7

所有高风险操作必须经过 Confirmation 策略。

## Rule 8

所有异步任务必须有 Task ID。

## Rule 9

所有任务必须可以查询状态。

## Rule 10

所有异常必须转换为 StructAI Error。

---

# 135. Minimum Production Requirements

在进入实际 MIDAS 接入之前：

```text
[ ] SQLite
[ ] Alembic
[ ] Repository
[ ] UnitOfWork
[ ] Multi-Tenant
[ ] Authentication
[ ] Session
[ ] RBAC
[ ] Effective Permission
[ ] Resource Resolver
[ ] Lock
[ ] Optimistic Concurrency
[ ] Idempotency
[ ] Registry
[ ] Schema Engine
[ ] Validation
[ ] Capability Resolver
[ ] Adapter Framework
[ ] Plugin Loader
[ ] Mock Adapter
[ ] Task Engine
[ ] DAG
[ ] Lease
[ ] Recovery
[ ] Cancellation
[ ] Artifact
[ ] Document
[ ] Batch
[ ] Dry Run
[ ] Preconditions
[ ] Postconditions
[ ] Event Bus
[ ] Quota
[ ] Audit
[ ] Trace
[ ] Metrics
[ ] Health
[ ] Backup
[ ] 9 MCP Tools
[ ] STDIO
[ ] Streamable HTTP
[ ] Unit Tests
[ ] Contract Tests
[ ] Integration Tests
[ ] Security Tests
[ ] Concurrency Tests
[ ] Recovery Tests
[ ] E2E
```

---

# 136. Acceptance Commands

创建环境：

```bash
python -m venv .venv
```

Windows：

```powershell
.venv\Scripts\Activate.ps1
```

Linux：

```bash
source .venv/bin/activate
```

安装：

```bash
pip install -e ".[dev]"
```

迁移：

```bash
alembic upgrade head
```

Seed：

```bash
python scripts/seed.py
```

启动：

```bash
python -m app.main
```

测试：

```bash
pytest
```

覆盖率：

```bash
pytest --cov=app
```

---

# 137. Core Alpha Acceptance

必须做到：

```text
启动成功
 ↓
SQLite 正常
 ↓
Migration 正常
 ↓
Seed 正常
 ↓
MCP Server 正常
 ↓
Discover 9 Tools
 ↓
Discover Operations
 ↓
Discover Capabilities
```

---

# 138. Functional Acceptance

至少：

```text
BUILD.COLUMN
MODEL.NODE.QUERY
MODEL.ELEMENT.QUERY
MODEL.BOUNDARY.ASSIGN
MODEL.LOAD.ASSIGN
ANALYSIS.STATIC
RESULT.NODE.DISPLACEMENT
RESULT.ELEMENT.FORCE
DESIGN.STEEL
```

完整通过。

---

# 139. Security Acceptance

验证：

```text
未登录 → 拒绝

无 MODEL_WRITE → MODEL.NODE.CREATE 拒绝

无 ANALYSIS_EXECUTE → ANALYSIS.STATIC 拒绝

跨 Tenant → 拒绝

跨 Project → 拒绝

无 Confirmation → HIGH 操作拒绝

AI Agent 权限不足 → 拒绝
```

---

# 140. Reliability Acceptance

验证：

```text
重复请求
 ↓
Idempotency

并发修改
 ↓
Optimistic Lock

资源冲突
 ↓
Resource Lock

Worker 崩溃
 ↓
Recovery

Task 超时
 ↓
Timeout

Adapter 断开
 ↓
Adapter Error / Recovery
```

---

# 141. Generic AI Client Acceptance

AI Client 不需要知道：

```text
MIDAS
ETABS
SAP2000
OpenSees
```

只需要知道：

```text
engineering_model_build
engineering_model_assign
engineering_analysis
engineering_result
engineering_design
```

这是 StructAI MCP Core 的核心抽象目标。

---

# 142. Final Architecture

最终：

```text
                    AI / Human Client
                           │
                           ▼
                    ┌──────────────┐
                    │ MCP Protocol │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ 9 MCP Tools  │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ ToolDispatch │
                    └──────┬───────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │ ExecutionService │
                  └────────┬─────────┘
                           │
       ┌───────────────────┼──────────────────┐
       │                   │                  │
       ▼                   ▼                  ▼
   Security            Validation          Registry
       │                   │                  │
       └───────────────────┼──────────────────┘
                           │
                           ▼
                    Capability Resolver
                           │
                           ▼
                       Task Engine
                           │
                           ▼
                     Resource Lock
                           │
                           ▼
                     Adapter Manager
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
       MIDAS              CSI             ANSYS
       Adapter           Adapter          Adapter
          │                │                │
          ▼                ▼                ▼
      Native API       Native API       Native API
          │                │                │
          └────────────────┼────────────────┘
                           ▼
                  Canonical Engineering
                        Model/Result
                           │
              ┌────────────┼─────────────┐
              ▼            ▼             ▼
           Artifact       Audit        Event
              │            │             │
              └────────────┼─────────────┘
                           ▼
                      MCP Response
```

---

# 143. Final Definition of Done

StructAI MCP Server V2.0 Core Alpha 只有同时满足以下条件才算完成：

```text
[✓] Python 3.12+
[✓] Async Architecture
[✓] SQLite
[✓] Alembic
[✓] Repository
[✓] UnitOfWork
[✓] Multi-Tenant
[✓] Authentication
[✓] Session
[✓] RBAC
[✓] Effective Permission
[✓] Resource Resolver
[✓] Resource Lock
[✓] Optimistic Lock
[✓] Idempotency
[✓] Software Registry
[✓] Capability Registry
[✓] Operation Registry
[✓] Schema Registry
[✓] API Registry
[✓] JSON Schema
[✓] Validation
[✓] Preconditions
[✓] Postconditions
[✓] Confirmation
[✓] Adapter Framework
[✓] Plugin Loader
[✓] Mock Adapter
[✓] Task Engine
[✓] Task DAG
[✓] Task Lease
[✓] Task Recovery
[✓] Cancellation
[✓] Artifact Storage
[✓] Document Service
[✓] Batch
[✓] Dry Run
[✓] Event Bus
[✓] Quota
[✓] Audit
[✓] Trace
[✓] Metrics
[✓] Health
[✓] Backup / Restore
[✓] 9 MCP Tools
[✓] MCP Dispatcher
[✓] STDIO
[✓] Streamable HTTP
[✓] Unit Tests
[✓] Contract Tests
[✓] Integration Tests
[✓] Security Tests
[✓] Concurrency Tests
[✓] Recovery Tests
[✓] Generic AI E2E
```

---

# 144. 第六份文档与前五份的关系

```text
① Core Database Design
          ↓
② Core Development Document
          ↓
③ Core Implementation Specification
          ↓
④ Core Python Implementation Specification
          ↓
⑤ 9 MCP Tools Complete Implementation Specification
          ↓
⑥ Python File-Level Implementation Blueprint
          ↓
实际编码
```

第六份不是新的架构设计，而是：

```text
Architecture
     ↓
Specification
     ↓
File
     ↓
Class
     ↓
Method
     ↓
Test
     ↓
Executable Core
```

---

# 145. 下一阶段

完成第六份之后，实际开发应进入：

```text
第七份：
StructAI MCP Server V2.0
Core Alpha 实际源码生成规范
```

第七份将进一步把本文件继续拆成：

```text
每个 Python 文件
 ↓
完整 import
 ↓
完整 class
 ↓
完整 method
 ↓
Pydantic Model
 ↓
SQLAlchemy Model
 ↓
Repository
 ↓
Service
 ↓
Test
```

并按照：

```text
P0 → P1 → P2 → P3 → ...
```

的顺序逐批生成源码。

**第六份的完成标准不是“文档看起来完整”，而是任何开发人员拿到本文件后，不需要重新做架构设计，就可以开始创建 `structai-mcp/` 并逐文件实现。**



# 完整收录：source7

# StructAI MCP Server V2.0
# 第七份：Core Alpha 实际源码生成规范
## Source-Level Implementation Specification

> 目标：在第六份《Python File-Level Implementation Blueprint》的基础上，将 StructAI MCP Server V2.0 进一步落实到“可以直接创建源码文件并编码”的粒度。
>
> 本文是 Core Alpha 的**源码级合同**。它不重新设计前六份架构，不增加新的 MCP Tool，不把 MIDAS 特有逻辑放入 Core。
>
> 本文的输出目标是：
>
> ```text
> 第六份：文件应该有什么
>         ↓
> 第七份：文件里面具体应该实现什么
>         ↓
> 第八阶段：实际源码
> ```

---

# 1. 文档定位

## 1.1 已冻结的上层设计

StructAI MCP Server V2.0 已冻结：

```text
9 MCP Tools
Software-neutral Core
Capability abstraction
Operation abstraction
Adapter architecture
Canonical Engineering Model
Task Engine
RBAC
Multi-Tenant
Resource Lock
Optimistic Concurrency
Idempotency
Artifact
Document
Event Bus
Audit
Trace
Metrics
Health
STDIO
Streamable HTTP
```

## 1.2 本文解决的问题

本文明确：

```text
Python Module
    ↓
Class
    ↓
Method
    ↓
Parameter
    ↓
Return
    ↓
Exception
    ↓
Database Interaction
    ↓
Service Interaction
    ↓
Test
```

## 1.3 本文不解决的问题

本文不具体实现：

```text
MIDAS API
CSI API
ANSYS API
OpenSees API
```

这些属于 Adapter 阶段。

---

# 2. Core Alpha 源码目标

Core Alpha 必须能够：

```text
启动 StructAI MCP Server
        ↓
初始化 SQLite
        ↓
执行 Alembic Migration
        ↓
Seed 基础数据
        ↓
加载 Registry
        ↓
加载 Mock Adapter
        ↓
启动 Task Engine
        ↓
注册 9 MCP Tools
        ↓
接受 MCP Client
        ↓
执行工程操作
```

最小完整 E2E：

```text
BUILD.COLUMN
    ↓
MODEL.NODE.QUERY
    ↓
MODEL.ELEMENT.QUERY
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

# 3. 源码实现原则

## 3.1 Domain First

依赖方向：

```text
interfaces
    ↓
application
    ↓
domain
```

Infrastructure 实现 Domain/Application 定义的接口。

## 3.2 禁止反向依赖

禁止：

```text
domain → SQLAlchemy
domain → FastAPI
domain → MCP SDK
domain → MIDAS
domain → HTTPX
```

## 3.3 Tool Thin Handler

Tool：

```text
Parse
 ↓
Context
 ↓
Application Service
 ↓
Response
```

Tool 不包含业务算法。

## 3.4 Adapter Isolation

Adapter 只处理：

```text
Native Connection
Native Authentication
Native Operation
Native Response
Native Error
```

## 3.5 Server Trust Boundary

客户端不能决定：

```text
user_id
tenant_id
roles
permissions
effective_permissions
```

---

# 4. 最终源码目录

```text
structai-mcp/
├── pyproject.toml
├── README.md
├── LICENSE
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
│   │   ├── entities.py
│   │   ├── value_objects.py
│   │   ├── errors.py
│   │   ├── events.py
│   │   └── protocols.py
│   │
│   ├── application/
│   │   ├── __init__.py
│   │   ├── dto/
│   │   │   ├── common.py
│   │   │   ├── tool.py
│   │   │   ├── task.py
│   │   │   ├── model.py
│   │   │   └── result.py
│   │   ├── execution/
│   │   │   ├── context.py
│   │   │   ├── service.py
│   │   │   ├── pipeline.py
│   │   │   ├── validation.py
│   │   │   ├── engineering_validator.py
│   │   │   ├── preconditions.py
│   │   │   ├── postconditions.py
│   │   │   └── confirmation.py
│   │   ├── services/
│   │   │   ├── adapter_resolver.py
│   │   │   ├── capability_resolver.py
│   │   │   ├── document.py
│   │   │   ├── model.py
│   │   │   ├── result.py
│   │   │   ├── quota.py
│   │   │   └── backup.py
│   │   ├── security/
│   │   │   ├── authentication.py
│   │   │   ├── password.py
│   │   │   ├── session.py
│   │   │   ├── rbac.py
│   │   │   ├── permission.py
│   │   │   └── context.py
│   │   ├── resource/
│   │   │   ├── resolver.py
│   │   │   ├── lock_manager.py
│   │   │   └── lock_policy.py
│   │   └── task/
│   │       ├── engine.py
│   │       ├── queue.py
│   │       ├── worker.py
│   │       ├── scheduler.py
│   │       ├── state_machine.py
│   │       ├── dag.py
│   │       ├── lease.py
│   │       ├── recovery.py
│   │       ├── cancellation.py
│   │       └── progress.py
│   │
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── database/
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   ├── unit_of_work.py
│   │   │   ├── models/
│   │   │   └── repositories/
│   │   ├── registry/
│   │   │   ├── software_registry.py
│   │   │   ├── capability_registry.py
│   │   │   ├── operation_registry.py
│   │   │   ├── schema_registry.py
│   │   │   └── api_registry.py
│   │   ├── adapters/
│   │   │   ├── base/
│   │   │   │   ├── adapter.py
│   │   │   │   ├── manifest.py
│   │   │   │   ├── errors.py
│   │   │   │   └── manager.py
│   │   │   └── mock/
│   │   │       ├── adapter.py
│   │   │       ├── model_store.py
│   │   │       └── analysis.py
│   │   ├── storage/
│   │   │   ├── base.py
│   │   │   ├── local.py
│   │   │   └── manager.py
│   │   ├── secrets/
│   │   │   ├── base.py
│   │   │   └── environment.py
│   │   ├── events/
│   │   │   ├── bus.py
│   │   │   └── in_process.py
│   │   ├── notifications/
│   │   │   └── service.py
│   │   └── locks/
│   │       └── in_memory.py
│   │
│   ├── interfaces/
│   │   ├── __init__.py
│   │   ├── mcp/
│   │   │   ├── server.py
│   │   │   ├── context.py
│   │   │   ├── dispatcher.py
│   │   │   ├── responses.py
│   │   │   ├── errors.py
│   │   │   └── tools/
│   │   │       ├── base.py
│   │   │       ├── engineering_doc.py
│   │   │       ├── engineering_model_query.py
│   │   │       ├── engineering_model_assign.py
│   │   │       ├── engineering_model_delete.py
│   │   │       ├── engineering_model_build.py
│   │   │       ├── engineering_view.py
│   │   │       ├── engineering_result.py
│   │   │       ├── engineering_design.py
│   │   │       └── engineering_analysis.py
│   │   ├── http/
│   │   │   ├── api.py
│   │   │   ├── health.py
│   │   │   └── management/
│   │   └── cli/
│   │
│   └── observability/
│       ├── tracing.py
│       ├── metrics.py
│       └── audit.py
│
├── schemas/
├── migrations/
├── scripts/
└── tests/
```

---

# 5. Configuration Source

## 5.1 `app/config/settings.py`

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "StructAI MCP Server"
    app_version: str = "2.0.0"

    database_url: str = (
        "sqlite+aiosqlite:///./structai.db"
    )

    mcp_transport: str = "stdio"

    host: str = "127.0.0.1"
    port: int = 7860

    task_worker_count: int = 4

    artifact_root: str = "./data/artifacts"

    session_expire_seconds: int = 86400

    task_default_timeout_seconds: int = 3600

    lock_default_timeout_seconds: int = 300

    capability_cache_seconds: int = 300
```

---

# 6. Runtime Config

`app/config/runtime_config.py`

```python
from dataclasses import dataclass


@dataclass
class RuntimeConfig:
    shutdown_timeout_seconds: int = 30
    task_poll_interval_seconds: float = 0.5
    lease_seconds: int = 30
    heartbeat_seconds: int = 10
```

---

# 7. Logging

`app/config/logging.py`

必须支持：

```text
structured log
stderr
trace_id
request_id
task_id
```

不要把 MCP Protocol 数据写入 stdout。

---

# 8. Domain Enum Source

`app/domain/enums.py`

至少：

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


class LockMode(StrEnum):
    READ = "READ"
    WRITE = "WRITE"
    EXCLUSIVE = "EXCLUSIVE"


class ResourceType(StrEnum):
    SOFTWARE_INSTANCE = "SOFTWARE_INSTANCE"
    MODEL = "MODEL"
    DOCUMENT = "DOCUMENT"


class AuthenticationMethod(StrEnum):
    PASSWORD = "PASSWORD"
    LOCAL = "LOCAL"
    TOKEN = "TOKEN"
```

---

# 9. Domain Errors

`app/domain/errors.py`

基础：

```python
class StructAIError(Exception):
    code = "STRUCTAI-7000"
    error_type = "INTERNAL_ERROR"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        details: dict | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.cause = cause
```

派生异常：

```text
ProtocolError
SchemaValidationError
EngineeringValidationError
ConcurrencyConflictError
SoftwareConnectionError
SoftwareAuthenticationError
SoftwareAPIError
SoftwareTimeoutError
CapabilityError
PermissionDeniedError
ConfirmationRequiredError
TenantAccessDeniedError
TaskError
TaskTimeoutError
TaskCancelledError
TaskRecoveryError
AdapterError
ResourceLockedError
ArtifactError
```

每一个异常必须对应统一错误码。

---

# 10. Execution Context

`app/application/execution/context.py`

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

# 11. Tool DTO

`app/application/dto/tool.py`

```python
from pydantic import BaseModel, Field


class ToolRequest(BaseModel):
    operation: str
    parameters: dict = Field(default_factory=dict)
    context: dict = Field(default_factory=dict)
    idempotency_key: str | None = None
    confirmation_token: str | None = None
    dry_run: bool = False
```

统一 Response：

```python
class ToolResponse(BaseModel):
    success: bool
    request_id: str
    trace_id: str
    tool: str
    operation: str
    execution: dict
    data: object | None = None
    warnings: list[dict] = []
    errors: list[dict] = []
    metadata: dict = {}
```

实际实现中使用 `Field(default_factory=list)` 和 `Field(default_factory=dict)`，避免可变默认值。

---

# 12. Task DTO

`app/application/dto/task.py`

```python
class TaskResponse(BaseModel):
    task_id: str
    request_id: str
    trace_id: str
    status: str
    progress: int = 0
    tool: str
    operation: str
    result: object | None = None
    artifacts: list[dict] = Field(
        default_factory=list
    )
    error: dict | None = None
```

---

# 13. Operation Definition

建议放在：

```text
app/domain/value_objects.py
```

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
    recovery_policy: str
```

---

# 14. Database Base

`app/infrastructure/database/base.py`

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

---

# 15. Database Session

`app/infrastructure/database/session.py`

```python
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_database(database_url: str):
    engine = create_async_engine(
        database_url,
        future=True,
    )

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    return engine, session_factory
```

---

# 16. UnitOfWork

`app/infrastructure/database/unit_of_work.py`

```python
class SQLAlchemyUnitOfWork:

    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.session = None

    async def __aenter__(self):
        self.session = self.session_factory()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc:
            await self.rollback()
        await self.session.close()

    async def commit(self):
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()
```

---

# 17. ORM Entity Rules

所有 ORM 模型必须：

```text
UUID primary key
created_at
updated_at
```

重要可变资源：

```text
version
```

Tenant-owned 数据：

```text
tenant_id
```

---

# 18. ORM Model Minimum Set

必须实现：

```text
TenantModel
UserModel
RoleModel
PermissionModel
UserRoleModel
RolePermissionModel
SessionModel
ProjectModel
ProjectMemberModel
SoftwareModel
SoftwareProductModel
SoftwareVersionModel
SoftwareInstanceModel
ModelModel
DocumentModel
CapabilityModel
OperationModel
OperationCapabilityModel
TaskModel
TaskStepModel
ArtifactModel
ResourceLockModel
IdempotencyRecordModel
AuditRecordModel
```

---

# 19. Repository Contract

Repository：

```python
class UserRepository(Protocol):

    async def get_by_id(self, user_id):
        ...

    async def get_by_username(self, username):
        ...

    async def add(self, user):
        ...
```

每个 Repository：

```text
CRUD
Query
Persistence
```

不得负责：

```text
Authorization
Task scheduling
Native API
```

---

# 20. Authentication Service

`application/security/authentication.py`

```python
class AuthenticationService:

    async def authenticate(
        self,
        username: str,
        password: str,
    ) -> IdentityContext:
        ...
```

流程：

```text
Find User
 ↓
Check Locked
 ↓
Verify Password
 ↓
Update Login State
 ↓
Create Session
 ↓
Build IdentityContext
 ↓
Audit Login
```

---

# 21. Password Service

`application/security/password.py`

```python
class PasswordService:

    def hash(self, password: str) -> str:
        ...

    def verify(
        self,
        password: str,
        password_hash: str,
    ) -> bool:
        ...
```

使用 Argon2id。

---

# 22. Session Service

负责：

```text
create
validate
refresh
revoke
expire
```

Session 必须：

```text
有过期时间
可撤销
绑定 User
绑定 Tenant
```

---

# 23. RBAC Service

`application/security/rbac.py`

```python
class RBACService:

    async def has_permission(
        self,
        identity: IdentityContext,
        permission: str,
        resource=None,
    ) -> bool:
        ...
```

---

# 24. Effective Permission Service

计算：

```text
Global Role
+
Tenant Role
+
Project Role
+
Resource ACL
-
Explicit Deny
```

最终返回：

```python
set[str]
```

---

# 25. Resource Resolver

`application/resource/resolver.py`

```python
class ResourceResolver:

    async def resolve(
        self,
        context: ExecutionContext,
    ):
        ...
```

验证：

```text
Tenant ownership
Project membership
Model ownership
Document ownership
Software access
```

---

# 26. Lock Manager

接口：

```python
class ResourceLockManager(Protocol):

    async def acquire(
        self,
        resource_type,
        resource_id,
        mode,
        owner_id,
        timeout,
    ):
        ...

    async def release(
        self,
        lock_id,
    ):
        ...
```

---

# 27. Lock Compatibility

```text
READ + READ       ALLOW
READ + WRITE      DENY
WRITE + WRITE     DENY
EXCLUSIVE + ANY   DENY
```

---

# 28. Idempotency Service

```python
class IdempotencyService:

    async def get_existing(
        self,
        tenant_id,
        key,
    ):
        ...

    async def reserve(
        self,
        tenant_id,
        key,
        request_hash,
    ):
        ...

    async def complete(
        self,
        record_id,
        response,
    ):
        ...
```

必须有数据库唯一约束。

---

# 29. Schema Validator

```text
application/execution/validation.py
```

接口：

```python
class SchemaValidator:

    async def validate(
        self,
        schema_id: str,
        data: dict,
    ):
        ...
```

错误：

```text
STRUCTAI-1100
```

---

# 30. Engineering Validator

检查：

```text
Node
Element
Material
Section
Boundary
Load
```

例：

```python
if node["x"] is None:
    raise EngineeringValidationError(...)
```

工程规则和 JSON Schema 分离。

---

# 31. Capability Resolver

```python
class CapabilityResolver:

    async def require(
        self,
        software_instance_id,
        capability,
    ):
        ...
```

不存在：

```text
STRUCTAI-3000
```

---

# 32. Adapter Base

`infrastructure/adapters/base/adapter.py`

```python
class EngineeringSoftwareAdapter(ABC):

    name: str
    vendor: str
    product: str

    async def connect(self, config: dict) -> None:
        raise NotImplementedError

    async def disconnect(self) -> None:
        raise NotImplementedError

    async def health_check(self) -> dict:
        raise NotImplementedError

    async def get_version(self) -> str:
        raise NotImplementedError

    async def get_capabilities(self) -> list[str]:
        raise NotImplementedError

    async def execute(
        self,
        operation: str,
        parameters: dict,
        context: ExecutionContext,
    ) -> dict:
        raise NotImplementedError

    async def cancel(self, task_id: str) -> None:
        raise NotImplementedError

    async def normalize_error(
        self,
        error: Exception,
    ) -> dict:
        raise NotImplementedError
```

---

# 33. Adapter Manager

负责：

```text
注册 Adapter
查找 Adapter
连接实例
断开实例
健康检查
```

接口：

```python
class AdapterManager:

    async def register(self, adapter):
        ...

    async def get_for_instance(
        self,
        instance_id,
    ):
        ...

    async def health_check_all(self):
        ...
```

---

# 34. Mock Adapter

Mock Adapter 必须首先实现：

```text
MODEL.NODE.CREATE
MODEL.NODE.UPDATE
MODEL.NODE.DELETE
MODEL.NODE.QUERY

MODEL.ELEMENT.CREATE
MODEL.ELEMENT.UPDATE
MODEL.ELEMENT.DELETE
MODEL.ELEMENT.QUERY

MODEL.BOUNDARY.ASSIGN
MODEL.LOAD.ASSIGN

BUILD.COLUMN

ANALYSIS.STATIC

RESULT.NODE.DISPLACEMENT
RESULT.ELEMENT.FORCE

DESIGN.STEEL
```

---

# 35. Mock Model Store

`infrastructure/adapters/mock/model_store.py`

内存结构：

```python
class MockModelStore:

    nodes: dict[int, dict]
    elements: dict[int, dict]
    materials: dict[int, dict]
    sections: dict[int, dict]
    boundaries: list[dict]
    loads: list[dict]
```

要求：

```text
线程/协程安全
ID 自动分配
版本控制
查询
更新
删除
```

---

# 36. Mock Analysis

`infrastructure/adapters/mock/analysis.py`

静力分析不需要模拟真实有限元求解器。

Core Alpha 只要求：

```text
接受合法模型
产生确定性的测试结果
```

例如：

```json
{
  "node_id": 2,
  "ux": 0.001,
  "uy": 0.002,
  "uz": -0.015
}
```

重要：

```text
Mock Result ≠ 工程计算结果
```

必须在测试文档中明确标识。

---

# 37. Task State Machine

`application/task/state_machine.py`

定义：

```python
ALLOWED_TRANSITIONS = {
    CREATED: {VALIDATING, CANCELLED},
    VALIDATING: {QUEUED, FAILED, CANCELLED},
    QUEUED: {RUNNING, CANCELLED},
    RUNNING: {
        PROCESSING,
        COMPLETED,
        FAILED,
        CANCEL_REQUESTED,
        TIMEOUT,
    },
    PROCESSING: {
        COMPLETED,
        FAILED,
        CANCEL_REQUESTED,
        TIMEOUT,
    },
    CANCEL_REQUESTED: {
        CANCELLED,
        FAILED,
    },
    RETRYING: {
        QUEUED,
        FAILED,
    },
    RECOVERING: {
        QUEUED,
        RUNNING,
        FAILED,
    },
}
```

所有状态更新必须经过 State Machine。

---

# 38. Task Queue

```python
class TaskQueue:

    async def put(self, task_id: str, priority: int = 0):
        ...

    async def get(self) -> str:
        ...

    async def shutdown(self):
        ...
```

Core Alpha 使用：

```text
asyncio.Queue
```

---

# 39. Task Engine

```python
class TaskEngine:

    async def submit(
        self,
        request,
        context,
    ):
        ...

    async def get(
        self,
        task_id,
    ):
        ...

    async def cancel(
        self,
        task_id,
    ):
        ...

    async def retry(
        self,
        task_id,
    ):
        ...

    async def recover(
        self,
    ):
        ...
```

---

# 40. Task Worker

Worker：

```text
Queue.get
 ↓
Lease
 ↓
RUNNING
 ↓
ExecutionService
 ↓
Progress
 ↓
COMPLETED / FAILED
 ↓
Release
```

---

# 41. Lease Service

字段：

```text
lease_owner
lease_until
last_heartbeat
```

接口：

```python
acquire()
heartbeat()
release()
is_expired()
```

---

# 42. Recovery Service

启动时：

```python
await recovery.recover_unfinished_tasks()
```

查找：

```text
QUEUED
RUNNING
PROCESSING
RECOVERING
```

检查 lease。

---

# 43. Task Cancellation

```text
CANCEL_REQUESTED
```

之后：

```text
Adapter.cancel()
```

成功：

```text
CANCELLED
```

不支持：

```text
保持真实 native state
```

---

# 44. Progress Service

```python
class ProgressReporter:

    async def report(
        self,
        task_id,
        progress: int,
        message: str | None = None,
    ):
        ...
```

范围：

```text
0–100
```

---

# 45. ExecutionService

这是 Core 最重要的 Application Service。

```python
class ExecutionService:

    async def execute(
        self,
        tool_name: str,
        operation: OperationDefinition,
        parameters: dict,
        request: ToolRequest,
        context: ExecutionContext,
    ):
        ...
```

执行顺序：

```text
Schema
 ↓
Engineering
 ↓
Precondition
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
Adapter
 ↓
Normalize
 ↓
Postcondition
 ↓
Audit
 ↓
Event
```

---

# 46. Sync / Async Decision

Operation Definition 决定：

```text
SYNC
ASYNC
STREAM
```

例如：

```text
MODEL.NODE.QUERY
→ SYNC

BUILD.COLUMN
→ ASYNC

ANALYSIS.STATIC
→ ASYNC

RESULT.NODE.DISPLACEMENT
→ SYNC

DESIGN.STEEL
→ ASYNC
```

---

# 47. Document Service

```python
class DocumentService:

    async def new(self, ...):
        ...

    async def open(self, ...):
        ...

    async def save(self, ...):
        ...

    async def save_as(self, ...):
        ...

    async def close(self, ...):
        ...

    async def info(self, ...):
        ...
```

---

# 48. Model Service

`application/services/model.py`

提供：

```text
query_node
query_element
query_material
query_section
query_boundary
query_load
assign_material
assign_section
assign_boundary
assign_load
```

Tool 不直接调用 Repository。

---

# 49. Result Service

`application/services/result.py`

负责：

```text
Result query
pagination
canonical normalization
artifact linking
```

---

# 50. Artifact Service

```python
class ArtifactService:

    async def create(
        self,
        data,
        metadata,
    ):
        ...

    async def get(
        self,
        artifact_id,
    ):
        ...
```

---

# 51. Local Storage

路径：

```text
data/
└── artifacts/
    └── <artifact_id>/
        └── <storage_key>
```

数据库只存：

```text
metadata
```

---

# 52. Event Bus

```python
class EventBus(Protocol):

    async def publish(self, event):
        ...

    async def subscribe(self, event_type, handler):
        ...
```

Core Alpha：

```text
InProcessEventBus
```

---

# 53. Audit Service

```python
class AuditService:

    async def record(
        self,
        *,
        context,
        action,
        resource,
        result,
    ):
        ...
```

所有重要写操作记录 Audit。

---

# 54. Trace Service

Core Alpha：

```text
request_id
trace_id
```

生成：

```python
uuid4()
```

所有子 Task 继承：

```text
trace_id
```

---

# 55. Metrics

最少实现计数器：

```text
requests_total
tasks_total
tasks_failed_total
adapter_requests_total
adapter_errors_total
active_tasks
```

---

# 56. MCP Base Tool

`interfaces/mcp/tools/base.py`

```python
class BaseEngineeringTool(ABC):

    name: str

    @abstractmethod
    async def handle(
        self,
        request: ToolRequest,
        context: MCPContext,
    ) -> ToolResponse:
        ...
```

---

# 57. MCP Context

```python
@dataclass
class MCPContext:
    request_id: str
    trace_id: str
    identity: IdentityContext
```

客户端上下文解析后只能补充：

```text
software_instance_id
project_id
model_id
document_id
```

不能覆盖 Identity。

---

# 58. Tool Dispatcher

```python
class ToolDispatcher:

    async def dispatch(
        self,
        tool_name,
        request,
        context,
    ):
        tool = self.registry.get(tool_name)

        if tool is None:
            raise ProtocolError(
                f"Unknown tool: {tool_name}"
            )

        return await tool.handle(
            request,
            context,
        )
```

---

# 59. Tool Implementation Pattern

所有 9 Tool 遵循：

```text
handle()
 ↓
resolve operation
 ↓
build ExecutionContext
 ↓
ExecutionService.execute()
 ↓
Unified Response
```

---

# 60. Engineering Doc Tool

```python
class EngineeringDocTool(BaseEngineeringTool):

    name = "engineering_doc"

    async def handle(...):
        ...
```

允许：

```text
NEW
OPEN
SAVE
SAVE_AS
CLOSE
INFO
```

---

# 61. Engineering Model Query Tool

```python
class EngineeringModelQueryTool(BaseEngineeringTool):

    name = "engineering_model_query"
```

操作：

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

---

# 62. Engineering Model Assign Tool

```python
class EngineeringModelAssignTool(BaseEngineeringTool):

    name = "engineering_model_assign"
```

操作：

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

---

# 63. Engineering Model Delete Tool

```python
class EngineeringModelDeleteTool(BaseEngineeringTool):

    name = "engineering_model_delete"
```

操作：

```text
MODEL.NODE.DELETE
MODEL.ELEMENT.DELETE
MODEL.LOAD.DELETE
MODEL.BOUNDARY.DELETE
MODEL.GROUP.DELETE
MODEL.MATERIAL.DELETE
MODEL.SECTION.DELETE
```

默认：

```text
HIGH
ASYNC
```

---

# 64. Engineering Model Build Tool

```python
class EngineeringModelBuildTool(BaseEngineeringTool):

    name = "engineering_model_build"
```

操作：

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

---

# 65. Engineering View Tool

```python
class EngineeringViewTool(BaseEngineeringTool):

    name = "engineering_view"
```

操作：

```text
VIEW.MODEL
VIEW.DEFORMED_MODEL
VIEW.REACTION
VIEW.DISPLACEMENT
VIEW.STRESS
VIEW.FORCE
VIEW.MODE_SHAPE
```

---

# 66. Engineering Result Tool

```python
class EngineeringResultTool(BaseEngineeringTool):

    name = "engineering_result"
```

操作：

```text
RESULT.NODE.DISPLACEMENT
RESULT.NODE.REACTION
RESULT.ELEMENT.FORCE
RESULT.ELEMENT.STRESS
RESULT.MODE.SHAPE
RESULT.ANALYSIS.SUMMARY
```

---

# 67. Engineering Design Tool

```python
class EngineeringDesignTool(BaseEngineeringTool):

    name = "engineering_design"
```

操作：

```text
DESIGN.STEEL
DESIGN.CONCRETE
DESIGN.SRC
DESIGN.FOUNDATION
DESIGN.CODE_CHECK
DESIGN.OPTIMIZE
```

---

# 68. Engineering Analysis Tool

```python
class EngineeringAnalysisTool(BaseEngineeringTool):

    name = "engineering_analysis"
```

操作：

```text
ANALYSIS.STATIC
ANALYSIS.MODAL
ANALYSIS.SEISMIC
ANALYSIS.SPECTRUM
ANALYSIS.BUCKLING
ANALYSIS.TIME_HISTORY
ANALYSIS.NONLINEAR
```

---

# 69. Operation Seed

必须把全部 Operation 注册进去。

完整列表：

```text
engineering_doc
    NEW
    OPEN
    SAVE
    SAVE_AS
    CLOSE
    INFO

engineering_model_query
    MODEL.QUERY
    MODEL.NODE.QUERY
    MODEL.ELEMENT.QUERY
    MODEL.MATERIAL.QUERY
    MODEL.SECTION.QUERY
    MODEL.BOUNDARY.QUERY
    MODEL.LOAD.QUERY
    MODEL.GROUP.QUERY

engineering_model_assign
    MODEL.NODE.CREATE
    MODEL.NODE.UPDATE
    MODEL.ELEMENT.CREATE
    MODEL.ELEMENT.UPDATE
    MODEL.MATERIAL.ASSIGN
    MODEL.SECTION.ASSIGN
    MODEL.BOUNDARY.ASSIGN
    MODEL.LOAD.ASSIGN

engineering_model_delete
    MODEL.NODE.DELETE
    MODEL.ELEMENT.DELETE
    MODEL.LOAD.DELETE
    MODEL.BOUNDARY.DELETE
    MODEL.GROUP.DELETE
    MODEL.MATERIAL.DELETE
    MODEL.SECTION.DELETE

engineering_model_build
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

engineering_view
    VIEW.MODEL
    VIEW.DEFORMED_MODEL
    VIEW.REACTION
    VIEW.DISPLACEMENT
    VIEW.STRESS
    VIEW.FORCE
    VIEW.MODE_SHAPE

engineering_result
    RESULT.NODE.DISPLACEMENT
    RESULT.NODE.REACTION
    RESULT.ELEMENT.FORCE
    RESULT.ELEMENT.STRESS
    RESULT.MODE.SHAPE
    RESULT.ANALYSIS.SUMMARY

engineering_design
    DESIGN.STEEL
    DESIGN.CONCRETE
    DESIGN.SRC
    DESIGN.FOUNDATION
    DESIGN.CODE_CHECK
    DESIGN.OPTIMIZE

engineering_analysis
    ANALYSIS.STATIC
    ANALYSIS.MODAL
    ANALYSIS.SEISMIC
    ANALYSIS.SPECTRUM
    ANALYSIS.BUCKLING
    ANALYSIS.TIME_HISTORY
    ANALYSIS.NONLINEAR
```
>
> ⭐ **2026-10-05 契约修订**：`engineering_design` 新增 `DESIGN.SRC`（5 → **6**），
> 补 `DESIGN.SRC.AIK-SRC2K.*` 共 27 个端点的归属（原先无对应 Operation）。
> Operation 总数 68 → **69**。详见 `docs/07` §5.1 / §6.8 / §16 R11。

---

# 70. Capability Seed

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

# 71. Permission Seed

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

---

# 72. Default Roles

至少：

```text
system_admin
engineer
viewer
ai_agent
```

建议：

```text
system_admin
    ALL

engineer
    MODEL_READ
    MODEL_WRITE
    MODEL_DELETE
    ANALYSIS_EXECUTE
    DESIGN_EXECUTE
    DESIGN_MODIFY
    RESULT_READ
    DOCUMENT_READ
    DOCUMENT_WRITE

viewer
    MODEL_READ
    RESULT_READ
    DOCUMENT_READ

ai_agent
    根据 Agent Scope 动态限制
```

---

# 73. MCP Server

`interfaces/mcp/server.py`

初始化：

```text
MCP Server
 ↓
Tool registration
 ↓
Dispatcher
 ↓
Transport
```

不要把：

```text
Task Engine
RBAC
Repository
```

直接写入 Tool registration。

---

# 74. Tool Registration

服务器启动时注册：

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

Tool 数量必须严格：

```text
9
```

---

# 75. Unified Error Response

```python
def error_response(
    error: StructAIError,
    *,
    request_id: str,
    trace_id: str,
    tool: str,
    operation: str,
):
    return {
        "success": False,
        "request_id": request_id,
        "trace_id": trace_id,
        "tool": tool,
        "operation": operation,
        "execution": {},
        "data": None,
        "warnings": [],
        "errors": [
            {
                "code": error.code,
                "type": error.error_type,
                "message": error.message,
                "details": error.details,
                "retryable": error.retryable,
            }
        ],
    }
```

---

# 76. MCP Error Boundary

所有异常必须最终进入：

```text
MCP Error Boundary
```

不得直接向 Client 泄漏：

```text
Python traceback
SQL query
password hash
API key
HTTP Authorization
native secret
```

---

# 77. HTTP Health

`interfaces/http/health.py`

实现：

```text
/livez
/readyz
/health
```

---

# 78. Application Container

`app/container.py`

```python
@dataclass
class ApplicationContainer:
    settings: Settings
    database: object
    repositories: object
    software_registry: object
    capability_registry: object
    operation_registry: object
    adapter_manager: object
    lock_manager: object
    task_engine: object
    execution_service: object
    event_bus: object
    audit_service: object
    artifact_service: object
    tool_dispatcher: object
```

Container 负责组装依赖。

---

# 79. Startup

`app/main.py`

启动顺序：

```text
Settings
 ↓
Logging
 ↓
Database
 ↓
Migration Check
 ↓
Repositories
 ↓
Registry
 ↓
Security
 ↓
Adapter Manager
 ↓
Mock Adapter
 ↓
Task Engine
 ↓
Execution Service
 ↓
Tool Dispatcher
 ↓
MCP Server
```

---

# 80. Shutdown

```text
Stop Transport
 ↓
Stop New Tasks
 ↓
Drain Workers
 ↓
Release Locks
 ↓
Disconnect Adapters
 ↓
Close Database
 ↓
Flush Logs
```

---

# 81. Schema Files

最少：

```text
schemas/
├── common/
│   ├── pagination.json
│   ├── error.json
│   └── response.json
├── model/
│   ├── node/
│   │   └── v1.json
│   ├── element/
│   │   └── v1.json
│   ├── material/
│   │   └── v1.json
│   ├── section/
│   │   └── v1.json
│   ├── boundary/
│   │   └── v1.json
│   └── load/
│       └── v1.json
├── analysis/
│   └── static/
│       └── v1.json
└── result/
    ├── displacement/
    │   └── v1.json
    └── element_force/
        └── v1.json
```

---

# 82. Node Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "structai://schema/model/node/v1",
  "type": "object",
  "properties": {
    "id": {
      "type": "integer"
    },
    "x": {
      "type": "number"
    },
    "y": {
      "type": "number"
    },
    "z": {
      "type": "number"
    }
  },
  "required": [
    "id",
    "x",
    "y",
    "z"
  ],
  "additionalProperties": false
}
```

---

# 83. Column Build Schema

建议：

```json
{
  "type": "object",
  "properties": {
    "base_node": {
      "type": "object",
      "properties": {
        "x": {"type": "number"},
        "y": {"type": "number"},
        "z": {"type": "number"}
      },
      "required": ["x", "y", "z"]
    },
    "height": {
      "type": "number",
      "exclusiveMinimum": 0
    },
    "material": {
      "type": "string"
    },
    "section": {
      "type": "string"
    }
  },
  "required": [
    "base_node",
    "height",
    "material",
    "section"
  ]
}
```

---

# 84. Load Schema

最小：

```json
{
  "type": "object",
  "properties": {
    "node_id": {
      "type": "integer"
    },
    "fx": {
      "type": "number"
    },
    "fy": {
      "type": "number"
    },
    "fz": {
      "type": "number"
    }
  },
  "required": ["node_id"]
}
```

工程单位体系必须在 Project / Model 层明确，不允许 Core 默认为任意单位而产生歧义。

---

# 85. Result Schema

位移：

```json
{
  "type": "object",
  "properties": {
    "node_id": {"type": "integer"},
    "ux": {"type": "number"},
    "uy": {"type": "number"},
    "uz": {"type": "number"}
  },
  "required": [
    "node_id",
    "ux",
    "uy",
    "uz"
  ]
}
```

---

# 86. Operation Registration Matrix

实现时每个 Operation 至少需要：

```text
name
tool
risk_level
execution_mode
input_schema
output_schema
permissions
capabilities
transactional
rollback_supported
dry_run_supported
recovery_policy
```

示例：

```python
OperationDefinition(
    name="BUILD.COLUMN",
    tool="engineering_model_build",
    risk_level=RiskLevel.HIGH,
    execution_mode=ExecutionMode.ASYNC,
    input_schema="structai://schema/build/column/v1",
    output_schema="structai://schema/build/column/result/v1",
    required_permissions=("MODEL_WRITE",),
    required_capabilities=("MODEL.NODE.WRITE", "MODEL.ELEMENT.WRITE"),
    transactional=True,
    rollback_supported=True,
    dry_run_supported=True,
    recovery_policy="RETRY_SAFE",
)
```

---

# 87. Operation Semantics

## MODEL.NODE.CREATE

```text
Permission:
MODEL_WRITE

Capability:
MODEL.NODE.WRITE

Lock:
MODEL WRITE

Idempotency:
REQUIRED

Version:
REQUIRED where update semantics apply

Dry Run:
YES
```

## MODEL.NODE.DELETE

```text
Permission:
MODEL_DELETE

Capability:
MODEL.NODE.DELETE

Risk:
HIGH

Lock:
MODEL WRITE

Confirmation:
YES by default
```

## ANALYSIS.STATIC

```text
Permission:
ANALYSIS_EXECUTE

Capability:
ANALYSIS.STATIC

Risk:
HIGH

Execution:
ASYNC

Lock:
MODEL READ / SOFTWARE SERIAL

Task:
REQUIRED
```

---

# 88. Operation Handler Rule

不为每个 Operation 创建独立 MCP Tool。

正确：

```text
Tool
 ↓
Operation
 ↓
OperationDefinition
 ↓
ExecutionService
 ↓
Adapter
```

错误：

```text
MCP Tool 1
MCP Tool 2
MCP Tool 3
...
```

---

# 89. Adapter Operation Mapping

Adapter 内：

```python
operation_handlers = {
    "BUILD.COLUMN": self.build_column,
    "MODEL.NODE.CREATE": self.create_node,
    "ANALYSIS.STATIC": self.static_analysis,
}
```

Core 不知道这些函数。

---

# 90. Mock Adapter Build Column

伪代码：

```python
async def build_column(
    self,
    parameters,
):
    base = parameters["base_node"]
    height = parameters["height"]

    bottom = self.store.create_node(
        base["x"],
        base["y"],
        base["z"],
    )

    top = self.store.create_node(
        base["x"],
        base["y"],
        base["z"] + height,
    )

    element = self.store.create_element(
        type="COLUMN",
        node_ids=[bottom["id"], top["id"]],
    )

    return {
        "node_ids": [
            bottom["id"],
            top["id"],
        ],
        "element_ids": [
            element["id"],
        ],
    }
```

---

# 91. Mock Static Analysis

```text
Validate model
 ↓
Find loads
 ↓
Generate deterministic test result
 ↓
Persist result
 ↓
Return Result Reference
```

不宣称真实工程计算。

---

# 92. Mock Steel Design

返回：

```json
{
  "element_id": 1,
  "utilization": 0.72,
  "status": "PASS"
}
```

仅用于：

```text
Core workflow testing
```

不能作为实际工程设计依据。

---

# 93. Test Fixture

`tests/conftest.py`

提供：

```text
test database
test container
test user
test tenant
test project
mock software
mock instance
authenticated identity
```

---

# 94. Unit Test Matrix

```text
test_enums
test_value_objects
test_errors
test_state_machine
test_lock_manager
test_rbac
test_effective_permission
test_schema_validator
test_engineering_validator
test_operation_registry
test_capability_registry
test_idempotency
```

---

# 95. Adapter Contract Test

所有 Adapter 必须通过：

```text
connect
health_check
get_version
get_capabilities
execute
normalize_error
disconnect
```

---

# 96. Task Tests

必须测试：

```text
submit
queue
run
complete
fail
timeout
cancel
retry
lease
heartbeat
recovery
```

---

# 97. Security Tests

至少：

```text
test_unauthenticated
test_wrong_password
test_expired_session
test_revoked_session
test_permission_denied
test_cross_tenant
test_cross_project
test_ai_scope
test_confirmation
```

---

# 98. Idempotency Tests

场景：

```text
same key
same request
```

结果：

```text
只执行一次
```

场景：

```text
same key
different request
```

结果：

```text
拒绝
```

---

# 99. Concurrency Tests

两个协程：

```text
CREATE same key
```

只能产生：

```text
one execution
```

两个 UPDATE：

```text
expected_version=10
```

只能一个成功。

---

# 100. Lock Tests

验证：

```text
READ + READ = success

READ + WRITE = second blocked

WRITE + WRITE = second blocked

EXCLUSIVE + READ = blocked
```

---

# 101. Recovery Test

流程：

```text
Task RUNNING
 ↓
Worker Crash
 ↓
Lease Expired
 ↓
Server Restart
 ↓
RECOVERING
 ↓
REQUEUE
 ↓
RUNNING
 ↓
COMPLETED
```

---

# 102. E2E Test Code Flow

```python
async def test_full_engineering_flow(
    mcp_client,
):

    build = await mcp_client.call_tool(
        "engineering_model_build",
        {
            "operation": "BUILD.COLUMN",
            "parameters": {
                "base_node": {
                    "x": 0,
                    "y": 0,
                    "z": 0,
                },
                "height": 6,
                "material": "Q355B",
                "section": "H400x400x13x21",
            },
        },
    )

    assert build["success"] is True
```

然后：

```text
Query
Boundary
Load
Analysis
Result
Design
```

---

# 103. Generic AI E2E

AI 输入：

> 创建一个高度 6m 的 Q355B H400×400×13×21 钢柱，底部固定，顶部施加 500kN 轴压力。完成静力分析，并返回顶部节点位移和钢柱设计利用率。

Core 不理解自然语言。

AI 将其转换成：

```text
BUILD.COLUMN
MODEL.BOUNDARY.ASSIGN
MODEL.LOAD.ASSIGN
ANALYSIS.STATIC
RESULT.NODE.DISPLACEMENT
DESIGN.STEEL
```

---

# 104. E2E Expected Result

最终：

```json
{
  "success": true,
  "data": {
    "displacement": {},
    "design": {}
  }
}
```

并存在：

```text
Audit
Trace
Task
Result
```

---

# 105. Development Order

必须严格：

```text
P01 Project Bootstrap
P02 Config
P03 Domain
P04 Database
P05 Repository
P06 UnitOfWork
P07 Seed
P08 Registry
P09 Schema
P10 Authentication
P11 Session
P12 RBAC
P13 Effective Permission
P14 Resource Resolver
P15 Lock
P16 Execution Context
P17 Validation
P18 Capability
P19 Adapter Base
P20 Mock Adapter
P21 Idempotency
P22 Task State
P23 Queue
P24 Worker
P25 Scheduler
P26 Lease
P27 Recovery
P28 Cancellation
P29 Artifact
P30 Document
P31 Event
P32 Audit
P33 Trace
P34 Metrics
P35 Health
P36 Execution Service
P37 MCP Context
P38 Dispatcher
P39 9 Tools
P40 STDIO
P41 HTTP
P42 Unit Tests
P43 Contract Tests
P44 Integration Tests
P45 Security Tests
P46 Concurrency Tests
P47 Recovery Tests
P48 E2E
```

---

# 106. P01 Bootstrap

先创建：

```text
pyproject.toml
README.md
.env.example
.gitignore
app/__init__.py
app/main.py
app/container.py
```

目标：

```bash
python -m app.main
```

能够启动并正常退出。

---

# 107. P02 Config

实现：

```text
Settings
RuntimeConfig
Logging
```

测试：

```text
环境变量覆盖默认值
```

---

# 108. P03 Domain

完成：

```text
Enums
Errors
Value Objects
Protocols
Events
```

不得引用：

```text
SQLAlchemy
FastAPI
MCP
```

---

# 109. P04 Database

完成：

```text
Base
Engine
Session
ORM
```

验证：

```text
SQLite connection
```

---

# 110. P05 Repository

实现最小：

```text
UserRepository
TenantRepository
ProjectRepository
SoftwareRepository
ModelRepository
TaskRepository
```

---

# 111. P06 UnitOfWork

验证：

```text
commit
rollback
close
```

---

# 112. P07 Seed

Seed：

```text
Tenant
Admin
Roles
Permissions
Operations
Capabilities
Mock Software
Mock Instance
```

---

# 113. P08 Registry

启动后：

```python
operation_registry.get(
    "BUILD.COLUMN"
)
```

必须返回定义。

---

# 114. P09 Schema

必须能够：

```text
load schema
validate valid data
reject invalid data
```

---

# 115. P10–P13 Security

必须先完成：

```text
Authentication
Session
RBAC
Effective Permission
```

再允许写操作。

---

# 116. P14–P18 Execution Foundation

实现：

```text
Resource
Lock
Context
Validation
Capability
```

完成后才能执行 Adapter。

---

# 117. P19–P20 Adapter

先：

```text
Adapter Base
```

再：

```text
Mock Adapter
```

不要先开发 MIDAS。

---

# 118. P21 Idempotency

所有 CREATE/BUILD/ASSIGN 流程接入。

---

# 119. P22–P28 Task

完成：

```text
State
Queue
Worker
Scheduler
Lease
Recovery
Cancellation
```

之后才接 ASYNC Tool。

---

# 120. P29–P35 Infrastructure

完成：

```text
Artifact
Document
Event
Audit
Trace
Metrics
Health
```

---

# 121. P36 ExecutionService

这是第一个真正的 Core 主干。

必须实现：

```text
validate
authorize
confirm
idempotency
lock
capability
task
adapter
normalize
persist
audit
event
```

---

# 122. P37–P39 MCP

顺序：

```text
MCP Context
 ↓
Dispatcher
 ↓
Base Tool
 ↓
9 Tools
```

---

# 123. P40 STDIO

首先让：

```text
Generic MCP Client
```

能够：

```text
connect
list_tools
call_tool
```

---

# 124. P41 HTTP

加入：

```text
Streamable HTTP
```

但不要复制业务逻辑。

---

# 125. P42–P48 Testing

测试顺序：

```text
Unit
 ↓
Contract
 ↓
Integration
 ↓
Security
 ↓
Concurrency
 ↓
Recovery
 ↓
E2E
```

---

# 126. Definition of Source Complete

源码阶段必须满足：

```text
[ ] 所有 import 可解析
[ ] 类型检查通过
[ ] Ruff 通过
[ ] Unit Test 通过
[ ] Integration Test 通过
[ ] Security Test 通过
[ ] Concurrency Test 通过
[ ] Recovery Test 通过
[ ] MCP Client 可连接
[ ] 9 Tool 可发现
[ ] Mock Adapter 可执行
```

---

# 127. Definition of Core Alpha

最终：

```text
MCP Client
 ↓
9 Tools
 ↓
Execution Pipeline
 ↓
RBAC
 ↓
Capability
 ↓
Lock
 ↓
Task Engine
 ↓
Mock Adapter
 ↓
Canonical Model
 ↓
Result
```

全部运行。

---

# 128. MIDAS 接入前置条件

只有 Core Alpha 通过：

```text
Unit
Contract
Integration
Security
Concurrency
Recovery
E2E
```

以后，才进入 MIDAS Adapter。

---

# 129. MIDAS 接入边界

MIDAS Adapter 可以新增：

```text
client.py
adapter.py
manifest.py
capabilities.py
operations.py
transforms.py
errors.py
health.py
```

Core 不允许新增：

```text
midas tool
midas service
midas domain entity
```

---

# 130. 第二软件验证

增加：

```text
CSI ETABS
```

后：

```text
9 Tool 不变
Operation 不变
AI Client 不变
Task Engine 不变
RBAC 不变
```

只增加：

```text
ETABS Adapter
Capability Mapping
API Mapping
```

---

# 131. Source-Level Acceptance Matrix

| 模块 | 必须存在 | 必须测试 |
|---|---|---|
| Config | Settings | 配置覆盖 |
| Domain | Entity/Enum/Error | Unit |
| Database | Async SQLite | Integration |
| Repository | CRUD | Integration |
| Registry | Operation/Capability | Unit |
| Schema | JSON Schema | Contract |
| Auth | Login/Session | Security |
| RBAC | Permission | Security |
| Lock | Read/Write | Concurrency |
| Idempotency | Atomic reserve | Concurrency |
| Adapter | Base/Mock | Contract |
| Task | Queue/Worker | Integration |
| Recovery | Lease | Recovery |
| Artifact | Local storage | Integration |
| Audit | Hash chain | Security |
| MCP | 9 Tools | E2E |
| Transport | STDIO/HTTP | E2E |

---

# 132. 最终代码调用链

同步：

```text
MCP
 ↓
Tool
 ↓
Dispatcher
 ↓
ExecutionService
 ↓
Validation
 ↓
Permission
 ↓
Capability
 ↓
Lock
 ↓
Adapter
 ↓
Normalize
 ↓
Audit
 ↓
Response
```

异步：

```text
MCP
 ↓
Tool
 ↓
ExecutionService
 ↓
TaskEngine.submit
 ↓
QUEUED
 ↓
Worker
 ↓
Lock
 ↓
Adapter
 ↓
Result
 ↓
Audit
 ↓
Event
 ↓
COMPLETED
```

---

# 133. 最终软件无关性检查

在 Core Alpha 完成后执行：

```text
grep -R "midas" app/
```

预期：

```text
Core application code
=
0 MIDAS-specific business dependency
```

允许出现：

```text
tests
docs
adapter plugin registration
```

但 Core Domain/Application 不允许出现：

```text
MIDAS endpoint
MIDAS parameter
MIDAS response
MIDAS SDK
```

---

# 134. 最终架构冻结

```text
                  ┌────────────────────┐
                  │ AI / Human Client  │
                  └─────────┬──────────┘
                            │
                            ▼
                     ┌─────────────┐
                     │ MCP Server  │
                     └──────┬──────┘
                            │
                            ▼
                     ┌─────────────┐
                     │ 9 MCP Tool  │
                     └──────┬──────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │ Tool Dispatcher  │
                  └────────┬─────────┘
                           │
                           ▼
                 ┌────────────────────┐
                 │ Execution Service │
                 └─────────┬──────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
    Security          Validation          Registry
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │ Capability      │
                  └────────┬────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │ Resource Lock   │
                  └────────┬────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │ Task Engine     │
                  └────────┬────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │ Adapter Manager │
                  └────────┬────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
           Mock          MIDAS         CSI
          Adapter       Adapter       Adapter
              │            │            │
              ▼            ▼            ▼
          Canonical Engineering Model
                           │
             ┌─────────────┼────────────┐
             ▼             ▼            ▼
          Result        Artifact       Audit
```

---

# 135. 第七份之后的实施路线

第七份完成后，不再继续无限增加架构文档。

进入实际源码阶段：

```text
第七份
   ↓
Core Alpha 源码生成
   ↓
编译
   ↓
单元测试
   ↓
Integration
   ↓
MCP E2E
   ↓
Core Alpha Freeze
   ↓
MIDAS Adapter
```

下一份文档如果继续编号，应该进入：

```text
第八份：
StructAI MCP Server V2.0
MIDAS Adapter 实际源码实现规范
```

但**只有 Core Alpha 源码接口稳定后再正式实现 MIDAS Adapter**。

---

# 136. 第七份最终结论

StructAI MCP Server V2.0 当前已经从：

```text
“设计一个 MCP Server”
```

进入：

```text
“按照固定源码合同实现一个 MCP Server”
```

源码阶段的核心原则只有三个：

```text
1. Core 不认识 MIDAS
2. Tool 不直接碰 Native API
3. 新软件通过 Adapter 扩展，而不是修改 Core
```

最终目标：

```text
一个 Core
+
9 个软件无关 MCP Tool
+
N 个工程软件 Adapter
```

形成：

```text
StructAI MCP Core
        +
MIDAS Adapter
        +
CSI Adapter
        +
ANSYS Adapter
        +
OpenSees Adapter
        +
未来更多 Adapter
```

而 AI Client 始终面对同一套：

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

这就是 StructAI MCP Server V2.0 Core Alpha 的源码级冻结标准。



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



# 来源映射

- `impl`：完整收录。
- `py`：完整收录。
- `blue`：完整收录。
- `source7`：完整收录。
- `source9`：完整收录。
- `sec`：完整收录。
- `exec`：完整收录。
- `task`：完整收录。
- `adapter`：完整收录。
- `artifact`：完整收录。
