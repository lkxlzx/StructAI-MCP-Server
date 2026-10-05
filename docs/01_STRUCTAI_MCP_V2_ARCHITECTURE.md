# 01_STRUCTAI_MCP_V2_ARCHITECTURE.md — 总体架构与数据模型

V2.0 Consolidated Architecture Baseline。Core First / Software Agnostic / UI Later。统一总体架构、核心原则、9 Tool、Multi-Tenant、Registry、Canonical Model、数据库、权限、任务、Adapter 边界与跨软件扩展规则。

---

# 内容保全说明

本主文档按六文档体系重新组织。**原有内容不删除**；各来源规范以完整原文收录在对应章节，确保代码、字段、状态、测试要求和实现约束均可追溯。


# 完整收录：dev

# StructAI MCP Server V2.0
## 核心开发文档 — Revision V2

**Document:** `StructAI_MCP_Server_V2.0_Core_Development_Document_Revision_V2.md`  
**Version:** 2.0 Revision V2  
**Status:** Core Alpha Baseline  
**Phase:** Core First, UI Later

---

# 1. 目标

StructAI MCP Server 是面向工程软件的通用、软件无关 MCP 智能操作与适配运行时。

第一阶段必须跑通：

```text
Generic AI Client
      ↓ MCP
StructAI MCP Server
      ↓
Authentication
      ↓
ExecutionContext
      ↓
Tool Registry
      ↓
Operation Registry
      ↓
Resource Resolver
      ↓
Schema Validation
      ↓
Engineering Validation
      ↓
Permission / Risk / Confirmation
      ↓
Idempotency / Lock / Quota
      ↓
Capability Resolver
      ↓
Task Engine
      ↓
Software Adapter
      ↓
Engineering Software
```

UI 不定义 Core。

AI Engineering Assistant 也不绕过 Core。

---

# 2. 核心原则

## 2.1 工程语义优先

Tool 不绑定：

```text
MIDAS
CSI
ANSYS
OpenSees
```

Tool 表达：

```text
document
model
build
view
result
design
analysis
```

## 2.2 Tool 不绑定 API

禁止：

```text
Tool → /db/NODE
Tool → /anal/STATIC
```

必须：

```text
Tool
 ↓
Operation
 ↓
Capability
 ↓
API Registry
 ↓
Adapter
 ↓
Software
```

## 2.3 软件差异由 Adapter 消化

新增软件通常只增加：

```text
Adapter
Capability Mapping
Operation Mapping
API Registry
Software Registry
```

不应修改：

```text
MCP Protocol
9 Core Tools
Task Engine
Schema Engine
Permission Engine
```

## 2.4 9 Tool 固定为第一阶段核心接口

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

---

# 3. 总体架构

```text
                    Generic AI Client
                           │
                          MCP
                           ▼
┌─────────────────────────────────────────────────┐
│             StructAI MCP Server Core             │
│                                                 │
│ Authentication / Session                        │
│ MCP Runtime / Transport                         │
│ Tool Registry                                    │
│ Operation Registry                               │
│ Capability Registry                              │
│ Schema / Validation                              │
│ Resource Resolver                                │
│ Permission / Risk / Confirmation                 │
│ Idempotency / Lock / Quota                       │
│ Task Engine / Recovery                           │
│ Trace / Audit / Metrics                          │
│ Adapter Manager                                  │
│ API Registry                                     │
└──────────────────────┬──────────────────────────┘
                       │
             ┌─────────┼─────────┐
             ▼         ▼         ▼
           MIDAS      CSI      OpenSees
           Adapter   Adapter    Adapter
             │         │         │
             ▼         ▼         ▼
           REST       COM       CLI/API
```

---

# 4. 9 个 Core Tool

| Tool | 领域 | 默认风险 | 默认执行 |
|---|---|---:|---|
| `engineering_doc` | 文档 | MEDIUM | SYNC/ASYNC |
| `engineering_model_query` | 模型查询 | LOW | SYNC |
| `engineering_model_assign` | 模型修改 | MEDIUM | SYNC/ASYNC |
| `engineering_model_delete` | 模型删除 | HIGH | ASYNC |
| `engineering_model_build` | 工程建模 | HIGH | ASYNC |
| `engineering_view` | 可视化 | LOW | SYNC |
| `engineering_result` | 结果 | LOW | SYNC |
| `engineering_design` | 设计验算 | HIGH | ASYNC |
| `engineering_analysis` | 分析计算 | HIGH | ASYNC |

Risk：

```text
LOW
MEDIUM
HIGH
CRITICAL
```

Execution：

```text
SYNC
ASYNC
STREAM
```

---

# 5. Tool Operation

## engineering_doc

```text
NEW
OPEN
SAVE
SAVE_AS
CLOSE
INFO
```

## engineering_model_query

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

## engineering_model_assign

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

## engineering_model_delete

```text
MODEL.NODE.DELETE
MODEL.ELEMENT.DELETE
MODEL.LOAD.DELETE
MODEL.BOUNDARY.DELETE
MODEL.GROUP.DELETE
MODEL.MATERIAL.DELETE
MODEL.SECTION.DELETE
```

删除必须经过：

```text
Permission
 ↓
Risk
 ↓
Confirmation
 ↓
Audit
 ↓
Execution
```

## engineering_model_build

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

## engineering_view

```text
VIEW.MODEL
VIEW.DEFORMED_MODEL
VIEW.REACTION
VIEW.DISPLACEMENT
VIEW.STRESS
VIEW.FORCE
VIEW.MODE_SHAPE
```

## engineering_result

```text
RESULT.NODE.DISPLACEMENT
RESULT.NODE.REACTION
RESULT.ELEMENT.FORCE
RESULT.ELEMENT.STRESS
RESULT.MODE.SHAPE
RESULT.ANALYSIS.SUMMARY
```

## engineering_design

```text
DESIGN.STEEL
DESIGN.CONCRETE
DESIGN.FOUNDATION
DESIGN.CODE_CHECK
DESIGN.OPTIMIZE
```

## engineering_analysis

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

# 6. Operation Registry

Operation 是 Core 的稳定工程语义。

例如：

```json
{
  "code": "ANALYSIS.STATIC",
  "tool": "engineering_analysis",
  "execution_mode": "ASYNC",
  "risk_level": "HIGH",
  "input_schema": "structai://schema/analysis/static/v1",
  "output_schema": "structai://schema/task/result/v1"
}
```

Operation 不包含：

```text
MIDAS URL
ETABS COM method
OpenSees command
```

这些由 API Registry + Adapter 提供。

---

# 7. Capability Registry

Capability 必须软件无关。

模型：

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
```

分析：

```text
ANALYSIS.STATIC
ANALYSIS.MODAL
ANALYSIS.SEISMIC
ANALYSIS.SPECTRUM
ANALYSIS.BUCKLING
ANALYSIS.TIME_HISTORY
ANALYSIS.NONLINEAR
```

结果：

```text
RESULT.DISPLACEMENT
RESULT.REACTION
RESULT.ELEMENT_FORCE
RESULT.STRESS
RESULT.MODE_SHAPE
```

设计：

```text
DESIGN.STEEL
DESIGN.CONCRETE
DESIGN.FOUNDATION
DESIGN.OPTIMIZATION
```

---

# 8. Software Registry

最终层级：

```text
Vendor
 ↓
Product
 ↓
Version
 ↓
Instance
```

例如：

```text
MIDAS
 ├── CIVIL NX
 │    ├── 2025
 │    ├── 2026
 │    └── 2027
 ├── GEN NX
 └── FEA NX

CSI
 ├── ETABS
 └── SAP2000

ANSYS
 └── Mechanical

OpenSees
```

Runtime 面向 `Software Instance` 执行，而不是只面向 Product。

---

# 9. Adapter

统一接口：

```python
class EngineeringSoftwareAdapter:
    async def connect(self, config): ...
    async def disconnect(self): ...
    async def health_check(self): ...
    async def get_version(self): ...
    async def get_capabilities(self): ...
    async def execute(self, operation, parameters, context): ...
    async def cancel(self, task_id): ...
    async def normalize_error(self, error): ...
```

Adapter 负责：

1. 连接
2. 认证
3. 版本检测
4. Capability 检测
5. Operation 映射
6. 参数转换
7. 执行
8. 响应转换
9. 错误标准化
10. 健康检查

Adapter 不负责：

```text
MCP
RBAC
全局 Task 生命周期
AI
UI
Knowledge Base
```

---

# 10. ExecutionContext

最终结构：

```text
IdentityContext
SoftwareContext
ProjectContext
ExecutionContext
```

身份必须由服务器 Authentication 生成。

客户端不能声明：

```text
user_id
tenant_id
roles
permissions
```

客户端最多请求：

```text
project_id
software_instance_id
```

服务器必须通过 Resource Resolver 验证归属。

---

# 11. Security Model

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

AI Agent：

```text
Effective User Permissions
        ∩
Agent Permissions
        =
Effective Agent Permissions
```

Agent 不得提升权限。

---

# 12. Resource Resolver

统一解析：

```text
Project
Model
Document
Software Instance
Task
Artifact
```

所有跨租户资源访问必须在这里阻断。

---

# 13. Validation

顺序固定：

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

完整 Runtime Pipeline：

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
Concurrency / Lock
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

# 14. Task Engine

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

Task DAG：

```text
Task
 ├── Step A
 ├── Step B
 ├── Step C → depends A
 └── Step D → depends B,C
```

---

# 15. Lock / Concurrency

Resource：

```text
Software Instance
Model
Document
```

规则：

```text
READ + READ = allowed
READ + WRITE = blocked
WRITE + WRITE = blocked
EXCLUSIVE = blocks all
```

桌面工程软件默认：

```text
SERIAL
```

可配置：

```text
SERIAL
LIMITED
PARALLEL
```

可变资源支持 `version + expected_version`。

冲突返回：

```text
STRUCTAI-1300
```

---

# 16. Idempotency

用于：

```text
CREATE
BUILD
ASSIGN
DELETE
ANALYSIS
DESIGN
```

数据库唯一约束：

```text
(tenant_id, idempotency_key)
```

必须原子处理。

---

# 17. Dry Run / Batch

支持：

```json
{
  "operation": "BUILD.COLUMN",
  "parameters": {},
  "dry_run": true
}
```

Dry Run 不修改模型。

Batch：

```json
{
  "items": [
    {},
    {},
    {}
  ],
  "atomic": true
}
```

必须明确：

```text
atomic
non-atomic
```

---

# 18. Artifact / Document

Artifact：

```text
model file
analysis result
calculation report
screenshot
export
JSON
CSV
PDF
```

Core DB 保存：

```text
artifact_id
storage_backend
storage_key
mime_type
size
checksum
```

第一阶段：

```text
LocalFilesystemStorage
```

---

# 19. Result Normalization

不同软件结果统一成 Canonical Engineering Model。

例如：

```json
{
  "node_id": 100,
  "ux": 0.001,
  "uy": 0.002,
  "uz": -0.015
}
```

AI Client 不应该理解每个软件的原始结果格式。

---

# 20. API Registry

示例：

MIDAS：

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

ETABS：

```json
{
  "software": "CSI",
  "product": "ETABS",
  "version": "22",
  "operation": "ANALYSIS.STATIC",
  "protocol": "COM",
  "method": "RunAnalysis"
}
```

OpenSees：

```json
{
  "software": "OpenSees",
  "operation": "ANALYSIS.STATIC",
  "protocol": "SCRIPT",
  "method": "analyze"
}
```

复杂转换逻辑不写进 DB，应由 Adapter 实现。

---

# 21. Error Contract

统一错误：

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

Raw native cause 默认隐藏：

```json
{
  "cause": {
    "provider": "MIDAS",
    "native_code": "...",
    "native_message": "..."
  }
}
```

---

# 22. Unified Response

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

# 23. MCP Discovery

Generic AI Client 首先：

```text
connect
 ↓
initialize
 ↓
tools/list
 ↓
capability discovery
 ↓
tool call
```

Discovery 不要求 Client 知道 MIDAS Endpoint。

---

# 24. MCP Progress / Cancellation

MCP Progress：

```text
MCP progress
 ↓
TaskEngine progress
```

MCP cancellation：

```text
MCP cancellation
 ↓
TaskEngine.cancel()
 ↓
Adapter.cancel()
```

如果底层工程软件不能真正取消，必须返回真实状态，不能伪装为已取消。

---

# 25. Health / Metrics

健康：

```text
/livez
/readyz
/health
```

指标至少：

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

一个 MIDAS Instance 不可用不能让整个 Core 变为 unavailable。

---

# 26. Event Bus

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

未来可以：

```text
Redis
NATS
Kafka
```

---

# 27. Audit / Trace

Trace：

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

高风险操作必须审计。

Audit 采用：

```text
previous_hash
entry_hash
```

形成完整性链。

---

# 28. UI 与 AI 工程助手边界

UI：

```text
Management Plane
```

AI Engineering Assistant：

```text
AI Client / AI Service
```

MCP Server：

```text
Execution Plane
```

关系：

```text
AI Engineering Assistant
          │
          │ MCP
          ▼
StructAI MCP Server
          │
          ▼
Engineering Software
```

AI 不直接调用 MIDAS Native API。

---

# 29. Mock Adapter

第一阶段必须先实现 Mock Adapter。

它必须能够模拟：

```text
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

目的：

```text
不依赖真实 MIDAS
验证整个 Core
```

---

# 30. 第一条完整 E2E

Generic AI Client：

> 创建一个高度 6m 的 Q355B H400×400×13×21 钢柱，底部固定，顶部施加 500kN 轴压力。完成静力分析，并返回顶部节点位移和钢柱设计利用率。

预期：

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

# 31. 第二软件验证

在 MIDAS Adapter 验证后增加第二软件。

新增软件原则：

```text
New Adapter
+
Capability Mapping
+
Operation Mapping
+
API Registry
```

不得修改：

```text
9 Tool Contract
MCP Protocol
Task Engine
AI Client Integration
```

如果必须修改上述组件，应重新审查抽象边界。

---

# 32. Core Alpha 验收

```text
[ ] Generic AI Client can connect
[ ] MCP initialize
[ ] tools/list
[ ] 9 Tools discoverable
[ ] Operations discoverable
[ ] Capability discovery
[ ] Authentication
[ ] Session
[ ] RBAC
[ ] Resource Resolver
[ ] Schema Validation
[ ] Engineering Validation
[ ] Confirmation
[ ] Idempotency
[ ] Resource Lock
[ ] Task Engine
[ ] Task DAG
[ ] Task Recovery
[ ] Artifact
[ ] Event
[ ] Audit
[ ] Trace
[ ] Metrics
[ ] Health
[ ] Mock Adapter
[ ] Complete E2E
```

---

# 33. UI 后续阶段

Core Alpha 完成后才进入：

```text
首页
AI 工程助手
工程软件
MCP 服务器
工具与接口
任务监控
日志中心
系统设置
```

UI 不得反向改变 Core Contract。

---

# 34. 开发顺序

```text
01 Database
02 Domain
03 Repository / UnitOfWork
04 Registry
05 Schema Engine
06 Authentication
07 RBAC
08 Resource Resolver
09 Lock
10 Execution Context
11 Validation
12 Capability
13 Adapter
14 Mock Adapter
15 Task Engine
16 Recovery
17 Artifact
18 Event
19 Audit / Trace
20 Metrics / Health
21 MCP
22 9 Tools
23 Contract Tests
24 E2E
25 Real MIDAS Adapter
26 Second Software Adapter
27 UI
```

---

# 35. 最终架构红线

禁止：

```text
Tool → MIDAS API
Tool → SQLAlchemy
UI → Database
AI → Native API
Adapter → FastAPI
Client → 自行声明 user_id / role
```

必须：

```text
MCP
 ↓
Tool
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
Software
```

---

# 36. 最终原则

> **StructAI MCP Server 是工程软件的通用执行运行时，而不是 MIDAS 的 API 包装器。**

MIDAS 是第一个 Adapter。

9 个 Tool、Operation、Capability、Task、Schema、Security 和 Core Runtime 是稳定边界。



# 完整收录：db

# StructAI MCP Server V2.0

## Core 数据模型与数据库设计规范

**Document:** `StructAI_MCP_Server_V2.0_Core_Database_Design.md`\
**Version:** 2.0\
**Status:** Development Specification\
**Architecture:** Software-Agnostic Engineering MCP Runtime

------------------------------------------------------------------------

# 1. 设计目标

StructAI MCP Server 的数据库不是单纯保存业务工程数据，而是保存 **MCP
Runtime 的控制数据、Registry 数据、任务数据、审计数据和运行状态**。

核心原则：

> 数据库描述"能力和运行状态"，而不是把某一个工程软件的 API
> 结构直接变成数据库结构。

数据库必须同时支持：

-   MIDAS
-   CSI ETABS
-   SAP2000
-   ANSYS
-   ABAQUS
-   OpenSees
-   未来新增的其他工程软件

新增软件不应改变 MCP Core 的数据库基本结构。

------------------------------------------------------------------------

# 2. 数据库技术选型

Core Alpha：

``` text
SQLite
+
SQLAlchemy 2.x
+
Alembic
```

生产环境：

``` text
SQLite
        ↓
可选
        ↓
PostgreSQL
```

数据库访问统一通过 SQLAlchemy。

业务代码禁止直接依赖：

``` python
sqlite3.connect(...)
```

也禁止在业务层根据数据库类型大量分支。

------------------------------------------------------------------------

# 3. 数据库逻辑分层

``` text
Registry
├── tools
├── operations
├── capabilities
└── mappings

Software
├── software_vendors
├── software_products
├── software_versions
└── software_instances

Adapter
├── adapters
├── adapter_versions
└── adapter_capabilities

Schema
├── schemas
└── schema_versions

Execution
├── tasks
├── task_steps
└── idempotency_records

Security
├── users
├── roles
├── permissions
├── role_permissions
└── audit_logs

Observability
├── traces
└── trace_spans

System
└── system_settings
```

------------------------------------------------------------------------

# 4. 核心实体关系

``` text
Tool
 │
 └── Operation
        │
        └── Capability
                │
                ├── Software Version
                │
                └── Adapter
                       │
                       └── API Registry
```

执行链：

``` text
Request
   │
   ▼
Task
   │
   ├── Task Steps
   ├── Trace
   └── Audit
```

Schema：

``` text
Operation
    │
    └── Schema
           │
           └── Schema Version
```

------------------------------------------------------------------------

# 5. 主键设计

所有核心表统一使用 UUID。

推荐：

``` python
uuid.uuid4()
```

Core Alpha 可以使用：

``` text
CHAR(36)
```

PostgreSQL 后续可以优化为原生 UUID，但应用层保持 UUID 抽象。

------------------------------------------------------------------------

# 6. Tool Registry

表：

``` text
tools
```

字段：

  字段                     类型       说明
  ------------------------ ---------- --------------------------
  id                       UUID       主键
  name                     VARCHAR    Tool 名称
  display_name             VARCHAR    显示名称
  description              TEXT       描述
  risk_level               VARCHAR    LOW/MEDIUM/HIGH/CRITICAL
  default_execution_mode   VARCHAR    SYNC/ASYNC/STREAM
  enabled                  BOOLEAN    是否启用
  version                  VARCHAR    Tool Contract 版本
  created_at               DATETIME   创建时间
  updated_at               DATETIME   更新时间

Core Alpha 固定注册：

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

约束：

``` text
UNIQUE(name)
```

------------------------------------------------------------------------

# 7. Operation Registry

表：

``` text
operations
```

字段：

  字段               类型
  ------------------ ----------
  id                 UUID
  tool_id            UUID
  name               VARCHAR
  display_name       VARCHAR
  description        TEXT
  category           VARCHAR
  risk_level         VARCHAR
  execution_mode     VARCHAR
  input_schema_id    UUID
  output_schema_id   UUID
  enabled            BOOLEAN
  version            VARCHAR
  created_at         DATETIME
  updated_at         DATETIME

例如：

``` text
engineering_model_query
        │
        ├── MODEL.QUERY
        ├── MODEL.NODE.QUERY
        ├── MODEL.ELEMENT.QUERY
        ├── MODEL.MATERIAL.QUERY
        ├── MODEL.SECTION.QUERY
        ├── MODEL.BOUNDARY.QUERY
        ├── MODEL.LOAD.QUERY
        └── MODEL.GROUP.QUERY
```

约束：

``` text
UNIQUE(tool_id, name)
```

------------------------------------------------------------------------

# 8. Capability Registry

表：

``` text
capabilities
```

字段：

  字段          类型
  ------------- ----------
  id            UUID
  code          VARCHAR
  name          VARCHAR
  description   TEXT
  category      VARCHAR
  direction     VARCHAR
  risk_level    VARCHAR
  enabled       BOOLEAN
  created_at    DATETIME
  updated_at    DATETIME

典型 Capability：

``` text
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
DESIGN.FOUNDATION
DESIGN.OPTIMIZATION
```

------------------------------------------------------------------------

# 9. Operation → Capability

表：

``` text
operation_capabilities
```

一个 Operation 可以依赖多个 Capability。

例如：

``` text
BUILD.COLUMN
```

可能需要：

``` text
MODEL.NODE.WRITE
MODEL.ELEMENT.WRITE
MODEL.MATERIAL.WRITE
MODEL.SECTION.WRITE
MODEL.BOUNDARY.WRITE
```

字段：

``` text
id
operation_id
capability_id
required
created_at
```

约束：

``` text
UNIQUE(operation_id, capability_id)
```

------------------------------------------------------------------------

# 10. Software Vendor

表：

``` text
software_vendors
```

例如：

``` text
MIDAS
CSI
ANSYS
Dassault Systemes
OpenSees
```

字段：

``` text
id
name
display_name
description
website
enabled
created_at
updated_at
```

------------------------------------------------------------------------

# 11. Software Product

表：

``` text
software_products
```

结构：

``` text
Vendor
  │
  └── Product
```

例如：

``` text
MIDAS
 ├── CIVIL NX
 ├── GEN NX
 └── FEA NX

CSI
 ├── ETABS
 └── SAP2000
```

字段：

``` text
id
vendor_id
name
display_name
product_type
description
enabled
created_at
updated_at
```

约束：

``` text
UNIQUE(vendor_id, name)
```

------------------------------------------------------------------------

# 12. Software Version

表：

``` text
software_versions
```

字段：

``` text
id
product_id
version
release_date
api_version
capability_snapshot
enabled
created_at
updated_at
```

例如：

``` text
CIVIL NX
 ├── 2025
 ├── 2026
 └── 2027
```

必须保留：

``` text
api_version
```

因为：

> 软件版本 ≠ API 版本。

------------------------------------------------------------------------

# 13. Software Instance

实际运行的软件连接对象：

``` text
software_instances
```

例如：

``` text
civil_01
civil_02
etabs_01
```

字段：

``` text
id
name
software_version_id
host
port
protocol
endpoint
credential_ref
status
last_health_check
metadata
enabled
created_at
updated_at
```

**禁止保存明文 API Key。**

只允许保存：

``` text
credential_ref
```

例如：

``` text
secret://software/civil_01/api_key
```

Secret 应由：

-   OS Credential Store
-   Vault
-   环境变量
-   Secret Manager

负责。

------------------------------------------------------------------------

# 14. Adapter Registry

表：

``` text
adapters
```

字段：

``` text
id
name
vendor
product
module
class_name
version
status
priority
enabled
config_schema_id
created_at
updated_at
```

例如：

``` text
midas.civil
midas.gen
csi.etabs
csi.sap2000
opensees.default
```

Adapter 是执行插件，不属于 MCP Tool。

------------------------------------------------------------------------

# 15. Adapter → Software Version

表：

``` text
adapter_versions
```

一个 Adapter 可以支持多个软件版本。

字段：

``` text
id
adapter_id
software_version_id
compatibility
priority
enabled
```

例如：

``` text
midas.civil
    │
    ├── CIVIL NX 2025
    ├── CIVIL NX 2026
    └── CIVIL NX 2027
```

------------------------------------------------------------------------

# 16. Adapter Capability

表：

``` text
adapter_capabilities
```

用于表示某 Adapter 对某 Software Version 实际支持哪些 Capability。

字段：

``` text
id
adapter_id
software_version_id
capability_id
support_level
enabled
metadata
```

support_level：

``` text
FULL
PARTIAL
READ_ONLY
EXPERIMENTAL
UNSUPPORTED
```

这样 Runtime 可以准确回答：

``` text
ETABS 22 是否支持 ANALYSIS.SEISMIC？
```

而不是让 AI 猜测。

------------------------------------------------------------------------

# 17. Operation API Mapping

这是数据库最关键的表之一：

``` text
operation_api_mappings
```

解决：

> 一个工程 Operation 如何映射到不同软件的具体 API。

字段：

``` text
id
operation_id
software_version_id
adapter_id
protocol
method
path
native_operation
request_transform
response_transform
timeout
retry_policy
enabled
created_at
updated_at
```

例如：

``` text
ANALYSIS.STATIC
```

可以映射到：

``` text
MIDAS CIVIL NX
POST /anal/STATIC
```

同时：

``` text
ANALYSIS.STATIC
```

也可以映射到：

``` text
ETABS
COM
RunAnalysis
```

或者：

``` text
OpenSees
SCRIPT
analyze
```

------------------------------------------------------------------------

# 18. 一个 Operation 对多个 API

必须支持：

``` text
BUILD.COLUMN
```

映射：

``` text
CREATE_NODE
CREATE_NODE
CREATE_ELEMENT
ASSIGN_MATERIAL
ASSIGN_SECTION
ASSIGN_BOUNDARY
```

因此不能设计为：

``` text
Operation → One API
```

必须：

``` text
Operation
   │
   ├── API 001
   ├── API 002
   ├── API 003
   ├── API 004
   └── API 005
```

增加：

``` text
sequence
```

执行顺序：

``` text
1 CREATE_NODE
2 CREATE_NODE
3 CREATE_ELEMENT
4 ASSIGN_MATERIAL
5 ASSIGN_SECTION
6 ASSIGN_BOUNDARY
```

------------------------------------------------------------------------

# 19. API Registry

原始软件 API 单独保存：

``` text
api_endpoints
```

字段：

``` text
id
software_version_id
name
protocol
method
path
operation_name
description
request_schema_id
response_schema_id
authentication_type
timeout
enabled
metadata
created_at
updated_at
```

例如：

``` text
MIDAS
CIVIL NX
2026
POST
/anal/STATIC
```

API Registry 不属于 MCP Tool 层。

------------------------------------------------------------------------

# 20. Schema Registry

表：

``` text
schemas
```

字段：

``` text
id
name
namespace
schema_type
description
current_version
created_at
updated_at
```

例如：

``` text
EngineeringNode
EngineeringElement
EngineeringMaterial
EngineeringSection
EngineeringLoad
AnalysisRequest
AnalysisResult
```

------------------------------------------------------------------------

# 21. Schema Version

表：

``` text
schema_versions
```

字段：

``` text
id
schema_id
version
schema_json
status
created_at
```

例如：

``` text
EngineeringNode
 ├── v1
 ├── v2
 └── v3
```

禁止覆盖历史版本。

------------------------------------------------------------------------

# 22. Schema URI

统一使用：

``` text
structai://schema/{domain}/{name}/v{version}
```

例如：

``` text
structai://schema/model/node/v1
structai://schema/model/element/v1
structai://schema/model/material/v1
structai://schema/analysis/static/v1
structai://schema/result/displacement/v1
```

------------------------------------------------------------------------

# 23. Task

表：

``` text
tasks
```

字段：

``` text
id
task_id
request_id
trace_id
parent_task_id
tool
operation
software_instance_id
status
progress
priority
idempotency_key
input_data
result_data
error_data
created_at
started_at
completed_at
updated_at
```

状态：

``` text
CREATED
VALIDATING
QUEUED
RUNNING
PROCESSING
COMPLETED
FAILED
CANCELLED
TIMEOUT
RETRYING
```

------------------------------------------------------------------------

# 24. Task Steps

表：

``` text
task_steps
```

用于支持 DAG。

字段：

``` text
id
task_id
step_id
parent_step_id
sequence
name
operation
status
progress
input_data
output_data
error_data
started_at
completed_at
```

例如：

``` text
BUILD.COLUMN
 │
 ├── Step 1 Material
 ├── Step 2 Section
 ├── Step 3 Nodes
 ├── Step 4 Element
 ├── Step 5 Boundary
 └── Step 6 Load
```

------------------------------------------------------------------------

# 25. Idempotency

表：

``` text
idempotency_records
```

字段：

``` text
id
idempotency_key
request_hash
request_id
task_id
status
response_data
expires_at
created_at
```

约束：

``` text
UNIQUE(idempotency_key)
```

用于防止：

``` text
AI retry
网络超时
客户端重复提交
```

导致：

``` text
BUILD.COLUMN
BUILD.COLUMN
```

被执行两次。

------------------------------------------------------------------------

# 26. Trace

表：

``` text
traces
```

字段：

``` text
id
trace_id
request_id
session_id
task_id
root_span_id
status
started_at
completed_at
metadata
```

------------------------------------------------------------------------

# 27. Trace Span

表：

``` text
trace_spans
```

执行链：

``` text
AI Client
MCP Request
Tool
Operation
Schema
Validation
Permission
Capability
Task
Adapter
Software API
Result
```

字段：

``` text
id
trace_id
span_id
parent_span_id
name
component
status
start_time
end_time
duration_ms
attributes
error_data
```

------------------------------------------------------------------------

# 28. Audit Log

所有高风险操作进入：

``` text
audit_logs
```

字段：

``` text
id
user_id
request_id
trace_id
task_id
action
resource_type
resource_id
result
ip_address
user_agent
details
created_at
```

至少记录：

``` text
DELETE
BUILD
ANALYSIS
DESIGN
权限修改
API Test
软件配置修改
```

------------------------------------------------------------------------

# 29. Permission

表：

``` text
permissions
```

预置：

``` text
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

------------------------------------------------------------------------

# 30. Role

表：

``` text
roles
```

建议：

``` text
ADMIN
ENGINEER
OPERATOR
VIEWER
AI_AGENT
```

AI_AGENT 不是超级管理员。

默认可以拥有：

``` text
MODEL_READ
MODEL_WRITE
ANALYSIS_EXECUTE
RESULT_READ
```

危险操作需要额外授权。

------------------------------------------------------------------------

# 31. Role Permission

表：

``` text
role_permissions
```

关系：

``` text
Role
  │
  ├── Permission
  ├── Permission
  └── Permission
```

------------------------------------------------------------------------

# 32. Confirmation Token

高风险操作不能只依赖权限。

例如：

``` text
MODEL.DELETE
DESIGN.MODIFY
```

可以返回：

``` text
STRUCTAI-4100
CONFIRMATION_REQUIRED
```

确认后：

``` json
{
  "confirmation_token": "confirm_xxx"
}
```

服务器验证 Token 后才执行。

------------------------------------------------------------------------

# 33. System Settings

表：

``` text
system_settings
```

字段：

``` text
id
key
value
value_type
scope
description
updated_at
```

例如：

``` text
server.host
server.port
task.max_workers
task.default_timeout
logging.level
security.require_confirmation
```

------------------------------------------------------------------------

# 34. 数据库索引

必须建立：

``` text
tools.name

operations.tool_id
operations.name

capabilities.code

software_products.vendor_id

software_versions.product_id

software_instances.software_version_id

operation_api_mappings.operation_id
operation_api_mappings.software_version_id

tasks.task_id
tasks.request_id
tasks.trace_id
tasks.status

trace_spans.trace_id

audit_logs.trace_id
audit_logs.request_id
```

重点：

``` text
trace_id
request_id
task_id
```

必须高效查询。

------------------------------------------------------------------------

# 35. 删除策略

Registry 数据原则上采用软删除或禁用。

不要因为 UI 操作直接物理删除：

``` text
Tool
Operation
Capability
Software
Adapter
Schema
API
```

建议：

``` text
enabled
deleted_at
```

这样不会破坏历史 Task、Trace 和 Audit。

------------------------------------------------------------------------

# 36. Registry 生命周期

Registry 对象统一支持：

``` text
DRAFT
ACTIVE
DISABLED
DEPRECATED
```

例如：

``` text
旧 API
  ↓
DEPRECATED

新 API
  ↓
ACTIVE
```

旧任务仍然可以追溯历史 Registry 信息。

------------------------------------------------------------------------

# 37. 数据一致性

禁止：

``` text
Operation 存在
但 Tool 不存在
```

禁止：

``` text
API Mapping 存在
但 Software Version 不存在
```

禁止：

``` text
Adapter Capability
引用不存在 Capability
```

必须同时使用：

``` text
Foreign Key
+
Application Validation
```

保证一致性。

------------------------------------------------------------------------

# 38. Registry 加载流程

服务器启动：

``` text
启动
 ↓
加载数据库
 ↓
加载 Tools
 ↓
加载 Operations
 ↓
加载 Capabilities
 ↓
加载 Schemas
 ↓
加载 Software
 ↓
加载 Adapters
 ↓
加载 API Mapping
 ↓
建立内存 Registry
 ↓
Runtime Ready
```

运行时：

``` text
MCP Request
 ↓
Registry
 ↓
Resolve
```

不要每次请求都扫描数据库。

------------------------------------------------------------------------

# 39. Registry Cache

推荐：

``` text
Database
   ↓
Registry Loader
   ↓
In-Memory Registry
```

内存中维护：

``` python
tool_registry
operation_registry
capability_registry
schema_registry
software_registry
adapter_registry
api_registry
```

数据库负责持久化，内存负责 Runtime Lookup。

------------------------------------------------------------------------

# 40. Registry Reload

管理接口支持：

``` text
Registry Reload
```

流程：

``` text
Database
 ↓
Validate
 ↓
Build Temporary Registry
 ↓
Validation Pass
 ↓
Atomic Swap
```

不能在半加载状态直接替换运行中的 Registry。

------------------------------------------------------------------------

# 41. Initial Seed

Core Alpha 必须自带 Seed：

``` text
9 Tools
+
Operations
+
Capabilities
+
Schemas
+
Mock Adapter
```

执行 Seed 后数据库应自动拥有：

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

------------------------------------------------------------------------

# 42. Seed 原则

Seed 必须幂等。

连续执行：

``` text
seed
seed
seed
seed
```

最终数据库状态必须一致。

禁止产生重复：

``` text
Tool
Operation
Capability
Schema
```

------------------------------------------------------------------------

# 43. Migration

使用：

``` text
Alembic
```

目录：

``` text
migrations/
├── env.py
└── versions/
    ├── 0001_initial.py
    ├── 0002_registry.py
    ├── 0003_task_engine.py
    └── ...
```

开发流程：

``` text
修改 SQLAlchemy Model
        ↓
alembic revision
        ↓
检查 migration
        ↓
alembic upgrade head
```

------------------------------------------------------------------------

# 44. 数据库初始化

首次运行：

``` text
structai-mcp
    ↓
检查 DB
    ↓
不存在
    ↓
创建
    ↓
Alembic Upgrade
    ↓
Seed
    ↓
Registry Load
    ↓
Ready
```

------------------------------------------------------------------------

# 45. Core Alpha 最小数据库

第一阶段必须优先实现：

``` text
tools
operations
capabilities
operation_capabilities

software_vendors
software_products
software_versions
software_instances

adapters
adapter_versions
adapter_capabilities

api_endpoints
operation_api_mappings

schemas
schema_versions

tasks
task_steps
idempotency_records

traces
trace_spans

audit_logs
```

Security 最小实现：

``` text
users
roles
permissions
role_permissions
```

------------------------------------------------------------------------

# 46. Mock Adapter 数据边界

Mock Adapter 可以模拟：

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

但是这些不是 MCP Registry。

Mock Engineering Model State 属于：

``` text
Mock Runtime State
```

不能把 Mock Node 当成：

``` text
software_instances
```

------------------------------------------------------------------------

# 47. 工程模型数据是否进入 Core DB

原则：

> 不进入 MCP Core Registry 数据库。

MCP Core 数据库保存：

``` text
Registry
Task
Trace
Audit
Configuration
Security
```

真实工程数据：

``` text
Node
Element
Material
Section
Load
Result
```

属于：

``` text
Engineering Software
```

或者未来独立的：

``` text
Engineering Project Data Layer
```

Adapter 负责访问。

这样可以避免 StructAI MCP 最终变成某个软件的数据库复制品。

------------------------------------------------------------------------

# 48. 核心边界

``` text
                 StructAI MCP Core
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
       Registry       Task          Security
          │             │             │
          └─────────────┼─────────────┘
                        ▼
                    Adapter
                        │
              ┌─────────┼─────────┐
              ▼         ▼         ▼
            MIDAS      ETABS    OpenSees
```

不是：

``` text
StructAI MCP
     │
     └── MIDAS Database
            │
            └── ETABS
```

------------------------------------------------------------------------

# 49. 完整数据流

``` text
MCP Client
    │
    ▼
Tool
    │
    ▼
Operation
    │
    ▼
Schema
    │
    ▼
Validation
    │
    ▼
Permission
    │
    ▼
Capability
    │
    ▼
Software Instance
    │
    ▼
Adapter
    │
    ▼
Operation API Mapping
    │
    ▼
API Registry
    │
    ▼
Engineering Software
```

返回：

``` text
Engineering Software
        │
        ▼
Adapter
        │
        ▼
Normalize
        │
        ├── Task
        ├── Trace
        └── Audit
        │
        ▼
MCP Response
```

------------------------------------------------------------------------

# 50. 第三份完成标准

完成本规范后，开发人员必须能够明确回答：

``` text
Tool 存哪里？
Operation 存哪里？
Capability 存哪里？
Software 存哪里？
Version 存哪里？
Adapter 存哪里？
API 存哪里？
Schema 存哪里？
Task 存哪里？
Trace 存哪里？
Audit 存哪里？
Permission 存哪里？
```

并且：

``` text
新增 MIDAS 版本
```

不需要修改 Core 表结构。

``` text
新增 ETABS
```

不需要修改 MCP Tool。

``` text
新增 OpenSees
```

不需要修改 Task Engine。

------------------------------------------------------------------------

# 51. 与第二份文档的关系

第二份解决：

> **StructAI MCP Core 应该如何工作？**

第三份解决：

> **StructAI MCP Core 工作所需要的数据如何组织和持久化？**

因此第四份进入：

> **Core Python 代码实现规范**

实现：

``` text
SQLAlchemy Models
        ↓
Repository
        ↓
Registry Service
        ↓
Operation Resolver
        ↓
Capability Resolver
        ↓
Schema Engine
        ↓
Validation Engine
        ↓
Task Engine
        ↓
Adapter Manager
        ↓
Mock Adapter
        ↓
9 MCP Tools
        ↓
STDIO / Streamable HTTP
```

------------------------------------------------------------------------

# 52. 架构总原则

StructAI MCP Server 必须始终遵循：

> **先定义工程语义，再适配软件实现；先完成 MCP
> Core，再对接具体软件；数据库保存 Runtime
> 元数据和控制状态，不复制任何具体工程软件的数据模型；UI 只消费 Core
> Registry 和 Service，不反向定义 Core。**

MIDAS 是第一个真实 Adapter，不是 StructAI MCP 的架构边界。


---

# Appendix A. V2.0 数据库多用户修订说明

本版本对初始第三份数据库设计做了关键增强：

1. 从单用户权限模型升级为 **User + Tenant + Project + Role + Permission + Resource ACL**。
2. User 与登录方式解耦，通过 `user_identities` 支持未来 OAuth/OIDC/SSO。
3. Session / Refresh Token 采用 Hash 保存，禁止明文持久化。
4. Task、Trace、Audit 必须绑定 `tenant_id`、`user_id`、`project_id`，保证可追溯和数据隔离。
5. AI Agent 采用独立身份，不允许通过 AI 身份获得超过当前用户的权限。
6. Registry 支持 Global 与 Tenant 两级，企业可扩展自己的 Operation / Schema / Adapter，而不会污染 Global Core。
7. 软件实例权限独立于用户全局权限，可进一步实施项目级或资源级访问控制。
8. 即使 Core Alpha 只有一个管理员，也必须按照该数据边界创建默认 Tenant，避免后续迁移时重构数据库。

**因此，本文件是第三份数据库设计的修订版，应以本版本作为后续第四份代码实现规范的数据库依据。**



# 来源映射

- `dev`：完整收录。
- `db`：完整收录。
