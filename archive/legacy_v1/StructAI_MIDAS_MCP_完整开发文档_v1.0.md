# StructAI｜多结构工程软件一体化 MCP 完整开发文档

> ⚠️ **非规范性文档（NON-NORMATIVE）** —— 本文件已归档至 `archive/legacy_v1/`，
> 属 StructAI 早期（V1）规范草案 / 实测记录，**不作为开发依据，不作为准则**。
> 开发唯一依据：`docs/01`–`docs/06`（V2 规范）· `docs/07`（开发方案与任务续接）· `registry/`（机器可读端点注册表）。

**版本：v1.0**  
**定位：生产级架构 + 开发规范 + 接口规范 + 工程工作流规范**  
**目标产品：StructAI Structural Intelligence Platform**  
**核心对象：多结构工程软件 API/MCP 集成（MIDAS 系列为首批接入）**

---

## 0. 文档说明

本文档是 StructAI 的 MCP 核心开发总规范，整合此前确定的全部架构要求，并将其落实为开发人员可以直接执行的工程设计。

本文档覆盖：

- 多结构工程软件管理
- 多软件、多实例、多版本、多 Solver
- Base URL / MAPI-Key / Secret 管理
- 软件连接 Profile
- CIVIL NX / GEN NX Adapter
- 四个统一 MCP Tool
- Endpoint Registry
- DOC / DB / OPE / VIEW / POST 统一路由
- Semantic Engineering Layer
- Project / Model / Version 管理
- Operation DAG
- Validation / Dependency Check
- Analysis Job
- Result Store
- Evidence Chain
- Design Engine
- Verification Engine
- Graphics Engine
- Calculation Report Engine
- Workflow Engine
- Audit
- Security
- Context Compression
- MCP Resources / Prompts
- 测试策略
- 部署方式
- 开发阶段与验收标准

本文档的核心设计原则：

> **MCP 是统一控制入口，Endpoint Registry 是 MIDAS API 知识层，Engineering Layer 是结构工程语义层，Result Store 是数字事实源，Workflow Engine 是一条龙流程控制器。**

---

# 1. 总体目标

StructAI 不是简单的“MIDAS API MCP”。

最终系统必须完成：

```text
图纸 / PDF / CAD / 用户描述
        ↓
工程意图识别
        ↓
结构工程模型
        ↓
MIDAS 建模
        ↓
模型检查
        ↓
荷载与组合
        ↓
分析计算
        ↓
结果提取
        ↓
规范设计
        ↓
独立校核
        ↓
问题识别
        ↓
自动优化
        ↓
重新分析
        ↓
最终设计
        ↓
图形生成
        ↓
计算书
        ↓
审计与证据链
```

最终实现：

> **建模 → 设计 → 计算 → 演算 → 验算 → 优化 → 出图 → 计算书**

的一条龙结构设计闭环。

---

# 2. 官方 API 基础与设计约束

StructAI 的 MIDAS API 适配层以官方 MIDAS API Online Manual 为基础。官方当前手册明确说明：MIDAS NX 系列（包括 CIVIL NX、GEN NX）使用 RESTful API，手册按 Endpoint、Method、JSON Structure 和 Example 描述各功能；DOC、DB、OPE、VIEW、POST 是主要接口体系。

官方当前文档还明确规定：

- DOC 使用 POST，Body 以 `Argument` 为入口；
- DB 主要使用 GET / POST / PUT / DELETE；
- DB 写入 Body 的第一层 Key 通常为 `Assign`；
- DB 数据对象通常使用数字字符串 Key；
- 某些新建文件所需数据，例如 Unit、Structure Type，只支持 GET / PUT；
- 部分 Endpoint 标注为 Hyper-S solver only；
- 部分能力具备产品/区域/版本约束。

因此 StructAI **严禁把 MIDAS API URL、产品差异、版本差异硬编码在 LLM Prompt 或 MCP Tool Schema 中**。

官方参考资料：`MIDAS API Online Manual`。

---

# 3. 核心架构

## 3.1 顶层架构

```text
                           User / LLM / Agent
                                   │
                                   ▼
                         ┌──────────────────┐
                         │ StructAI Workflow│
                         └────────┬─────────┘
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │ Engineering Semantic    │
                    │ Layer                   │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │       MCP Core          │
                    │                         │
                    │  midas_doc              │
                    │  midas_db_query         │
                    │  midas_db_assign        │
                    │  midas_db_delete        │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ Software Manager        │
                    │ Product / Version       │
                    │ Solver / Connection     │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ Product Adapter         │
                    │ CIVIL NX / GEN NX / ... │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ Endpoint Registry       │
                    │ DOC / DB / OPE / VIEW   │
                    │ POST                    │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ Dispatcher              │
                    │ Validate / Execute      │
                    │ Dependency / Audit      │
                    └────────────┬────────────┘
                                 │
                                 ▼
                          MIDAS REST API
                                 │
                                 ▼
                           MIDAS NX Host
```

---

# 4. 为什么只暴露四个 MCP Tool

如果把所有 Endpoint 都注册成 MCP Tool，会产生：

- Tool 数量巨大
- 路由选择困难
- Schema 占用大量 Context
- 模型更容易选错 Tool
- 产品/版本差异导致 Tool 数量爆炸
- API 更新导致 MCP 接口频繁变化

因此只保留：

```text
midas_doc
midas_db_query
midas_db_assign
midas_db_delete
```

这四个 Tool 不是功能少，而是采用“逻辑 Endpoint + Registry Dispatch”。

---

# 5. 四个 MCP Tool 正式定义

## 5.1 midas_doc

用途：项目生命周期、文件、阶段另存和分析控制。

```json
{
  "name": "midas_doc",
  "description": "执行 MIDAS 项目生命周期、文件及分析控制操作",
  "inputSchema": {
    "type": "object",
    "properties": {
      "software_id": {
        "type": ["string", "null"],
        "description": "MIDAS 软件 Profile ID，可为空；为空时使用 Session/Project 默认连接"
      },
      "command": {
        "type": "string",
        "enum": [
          "NEW",
          "OPEN",
          "CLOSE",
          "SAVE",
          "SAVEAS",
          "STAGAS",
          "IMPORT",
          "IMPORTMXT",
          "EXPORT",
          "EXPORTMXT",
          "ANAL"
        ]
      },
      "argument": {
        "type": "object",
        "default": {}
      },
      "options": {
        "type": "object"
      }
    },
    "required": ["command"]
  }
}
```

### 5.1.1 DOC Endpoint

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

### 5.1.2 安全策略

`ANAL` 默认：

```text
retryable = false
risk = high
```

`CLOSE`、`SAVEAS` 等由项目上下文管理。

---

# 6. midas_db_query

用途：查询 DB、OPE、VIEW、POST 等所有“查询型逻辑 Endpoint”。

```json
{
  "name": "midas_db_query",
  "inputSchema": {
    "type": "object",
    "properties": {
      "software_id": {
        "type": ["string", "null"]
      },
      "endpoint": {
        "type": "string"
      },
      "item_id": {
        "type": ["string", "null"]
      },
      "selector": {
        "type": "object"
      },
      "options": {
        "type": "object",
        "properties": {
          "raw": {
            "type": "boolean",
            "default": false
          },
          "include_schema": {
            "type": "boolean",
            "default": false
          },
          "include_source": {
            "type": "boolean",
            "default": false
          },
          "page": {
            "type": "integer",
            "minimum": 1,
            "default": 1
          },
          "page_size": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1000,
            "default": 100
          }
        }
      }
    },
    "required": ["endpoint"]
  }
}
```

默认不返回超大量原始数据，优先返回摘要、最大值、最小值、关键对象和分页结果。

---

# 7. midas_db_assign

用途：创建和修改。

```json
{
  "name": "midas_db_assign",
  "inputSchema": {
    "type": "object",
    "properties": {
      "software_id": {
        "type": ["string", "null"]
      },
      "endpoint": {
        "type": "string"
      },
      "mode": {
        "type": "string",
        "enum": ["create", "update", "upsert"]
      },
      "data": {
        "type": "object"
      },
      "options": {
        "type": "object",
        "properties": {
          "validate_only": {
            "type": "boolean",
            "default": false
          },
          "atomic": {
            "type": "boolean",
            "default": true
          },
          "save_version": {
            "type": "boolean",
            "default": true
          }
        }
      }
    },
    "required": ["endpoint", "mode", "data"]
  }
}
```

---

# 8. midas_db_delete

用途：删除数据，必须进行依赖检查。

```json
{
  "name": "midas_db_delete",
  "inputSchema": {
    "type": "object",
    "properties": {
      "software_id": {
        "type": ["string", "null"]
      },
      "endpoint": {
        "type": "string"
      },
      "target_ids": {
        "type": "array",
        "items": {"type": "string"},
        "minItems": 1
      },
      "confirm": {
        "type": "boolean",
        "default": false
      },
      "options": {
        "type": "object",
        "properties": {
          "check_dependencies": {
            "type": "boolean",
            "default": true
          },
          "save_version": {
            "type": "boolean",
            "default": true
          }
        }
      }
    },
    "required": ["endpoint", "target_ids"]
  }
}
```

禁止隐式“删除全部”。

---

# 9. 多结构工程软件支持

MIDAS 是产品系列，因此 StructAI 不能设计成单一软件连接器。

核心对象分为：

```text
SoftwareProfile
ConnectionProfile
ProductDefinition
SolverDefinition
CapabilityDefinition
```

---

# 10. SoftwareProfile

SoftwareProfile 描述“是什么软件”。

```go
type SoftwareProfile struct {
    ID              string
    Name            string
    Vendor          string
    ProductFamily   string
    Product         string
    Version         string
    Build           string
    Adapter         string
    Enabled         bool
    CreatedAt       time.Time
    UpdatedAt       time.Time
}
```

示例：

```json
{
  "id": "civil-main",
  "name": "汕尾 Civil 主机",
  "vendor": "MIDAS",
  "product_family": "STRUCTURE",
  "product": "CIVIL NX",
  "version": "2026",
  "adapter": "midas.civil_nx",
  "enabled": true
}
```

---

# 11. ConnectionProfile

ConnectionProfile 描述“怎么连接”。

```go
type ConnectionProfile struct {
    ID              string
    SoftwareID      string
    Name            string
    BaseURL         string
    APIKeyRef       string
    Environment     string
    TLSVerify       bool
    TimeoutMS       int
    RetryCount      int
    Enabled         bool
    LastStatus      string
    LastLatencyMS   int
    LastCheckedAt   time.Time
    CreatedAt       time.Time
    UpdatedAt       time.Time
}
```

原则：

> 数据库保存 `APIKeyRef`，不保存 MAPI-Key 明文。

---

# 12. 为什么 Software 与 Connection 必须分开

一个软件可以存在多个连接：

```text
CIVIL NX
├── 本机 Civil
├── 公司服务器 Civil
├── 测试 Civil
└── 临时 Civil
```

软件 Profile 描述产品身份；Connection Profile 描述网络连接。

这样可以：

- 切换主机
- 切换测试/生产
- 同一个产品多个实例
- 不重复定义产品信息
- 软件升级时保留连接

---

# 13. 产品与 Solver

Runtime Context 必须至少包含：

```text
Vendor
Product
Version
Solver
Connection
Endpoint
```

因为部分 API 仅适用于 Hyper-S 等特定求解器。

示例：

```text
MIDAS
CIVIL NX
2026
Hyper-S
civil-main
```

---

# 14. 软件状态

正式状态：

```text
REGISTERED
CONNECTING
CONNECTED
DEGRADED
AUTH_FAILED
API_UNAVAILABLE
WRONG_PRODUCT
VERSION_UNSUPPORTED
DISABLED
CONNECTION_LOST
UNKNOWN
```

---

# 15. 软件能力矩阵

```go
type Capabilities struct {
    DOC              bool
    DB               bool
    OPE              bool
    VIEW             bool
    POST             bool

    StaticAnalysis   bool
    Modal            bool
    Buckling         bool
    Seismic          bool
    TimeHistory      bool
    Nonlinear        bool
    MovingLoad       bool
    ConstructionStage bool

    SteelDesign      bool
    ConcreteDesign   bool
    SRCDesign        bool
}
```

Registry 也可以通过 capability 标签描述具体 Endpoint 是否可用。

---

# 16. Adapter 架构

```go
type SoftwareAdapter interface {
    Product() string
    Version() string
    Capabilities() Capabilities

    Connect(ctx context.Context) error
    Disconnect(ctx context.Context) error
    Health(ctx context.Context) error

    Request(ctx context.Context, req *DispatchRequest) (*DispatchResponse, error)
}
```

Adapter 负责：

- 产品差异
- 版本差异
- URI 差异
- Request Builder
- Response Parser
- Capability
- View/Analysis 差异

MCP Tool 不关心具体 Adapter。

---

# 17. CIVIL NX Adapter

```text
adapter: midas.civil_nx
```

建议目录：

```text
adapters/
└── civil_nx/
    ├── adapter.go
    ├── capabilities.go
    ├── registry.go
    ├── request.go
    └── response.go
```

---

# 18. GEN NX Adapter

```text
adapter: midas.gen_nx
```

目录：

```text
adapters/
└── gen_nx/
    ├── adapter.go
    ├── capabilities.go
    ├── registry.go
    ├── request.go
    └── response.go
```

禁止直接复制 CIVIL NX 的 Schema 作为 GEN NX 最终规范；两者可以共享 Common Registry，但产品差异必须通过 Adapter/Override 表达。

---

# 19. Neutral Engineering Model

为了未来支持更多软件，StructAI 不应让 Engineering Layer 直接绑定 MIDAS JSON。

采用中立模型：

```text
Neutral Engineering Model
│
├── Project
├── Geometry
├── Nodes
├── Elements
├── Materials
├── Sections
├── Boundaries
├── Loads
├── Load Cases
├── Load Combinations
├── Analysis Settings
├── Design Settings
└── Results
```

然后：

```text
Neutral Model
   ├──→ CIVIL NX Adapter
   ├──→ GEN NX Adapter
   └──→ Future Adapter
```

这是 StructAI 长期支持多个结构软件的关键。

---

# 20. Endpoint Registry

Endpoint Registry 是整个系统最重要的数据层。

LLM 不直接生成 URL。

LLM 只使用：

```text
NODE
ELEM
MATL
SECT
CONS
STLD
BEAM_FORCE_RESULT
MODEL_CAPTURE
...
```

Registry 决定：

```text
URI
Method
Wrapper
Schema
Parser
Product
Version
Solver
Capability
Risk
Dependency
Report Mapping
```

---

# 21. EndpointDefinition

```go
type EndpointDefinition struct {
    Key          string
    Namespace    string
    URI          string
    Methods      []string
    ToolMap      map[string]string

    Wrapper      *WrapperDef
    Selector     *SelectorDef
    Response     *ResponseDef

    SchemaRef    string
    Parser       string

    Product      []string
    Version      *VersionDef
    Solver       []string

    Risk         RiskDef
    Runtime      RuntimeDef

    Source       SourceDef
    Dependencies []DependencyDef

    Capability   []string
    Report       *ReportMapping
}
```

---

# 22. Registry 字段说明

## 22.1 key

逻辑名称，不允许使用完整 URL 作为 LLM 层 API。

## 22.2 namespace

```text
DOC
DB
OPE
VIEW
POST
```

## 22.3 uri

实际 MIDAS URI。

## 22.4 methods

```text
GET
POST
PUT
DELETE
```

## 22.5 tool_map

指定由哪个 MCP Tool 路由。

## 22.6 schema_ref

关联 JSON Schema。

## 22.7 parser

指定响应解析器。

## 22.8 product

限定产品。

## 22.9 solver

限定 Solver。

## 22.10 capability

限定能力。

## 22.11 risk

操作风险级别。

## 22.12 dependencies

工程依赖关系。

---

# 23. Registry YAML 示例：NODE

```yaml
key: NODE
namespace: DB
uri: /db/NODE
methods:
  - GET
  - POST
  - PUT
  - DELETE

tool_map:
  query: midas_db_query
  assign: midas_db_assign
  delete: midas_db_delete

wrapper:
  write: Assign

selector:
  mode: item_id

response:
  root: NODE

schema_ref: db/NODE.json
parser: db_generic

product:
  - CIVIL_NX
  - GEN_NX

risk:
  level: low
  destructive: false

runtime:
  requires_project: true
  requires_analysis: false
  timeout_ms: 30000
  retryable: true

capability:
  - MODEL

source:
  official: true
  page: NODE

dependencies:
  - endpoint: ELEM
    relation: referenced_by
```

---

# 24. Registry YAML 示例：POST/TABLE

```yaml
key: POST.TABLE.BEAMFORCE
namespace: POST
uri: /post/TABLE
methods:
  - POST

tool_map:
  query: midas_db_query

wrapper:
  write: Argument

fixed_arguments:
  TABLE_TYPE: BEAMFORCE

schema_ref: post/table/BEAMFORCE.json
parser: post_table

runtime:
  requires_project: true
  requires_analysis: true
  timeout_ms: 120000
  retryable: false

risk:
  level: low
  destructive: false

report:
  category: analysis_result
  figure_type: beam_force
```

---

# 25. Registry YAML 示例：VIEW/CAPTURE

```yaml
key: VIEW.CAPTURE
namespace: VIEW
uri: /view/CAPTURE
methods:
  - POST

tool_map:
  assign: midas_db_assign

wrapper:
  write: Argument

schema_ref: view/CAPTURE.json
parser: view_capture

runtime:
  requires_project: true
  requires_analysis: false
  timeout_ms: 60000
  retryable: false

output:
  type: image
```

---

# 26. Registry 三层覆盖

建议：

```text
Common
   ↓
Product
   ↓
Version / Solver
```

目录：

```text
registry/
├── common/
├── products/
│   ├── civil_nx/
│   └── gen_nx/
└── versions/
    ├── civil_nx/
    └── gen_nx/
```

Runtime Registry = Common + Product Override + Version/Solver Override。

---

# 27. Registry Resolver

```go
func Resolve(
    product string,
    version string,
    solver string,
    endpoint string,
) (*EndpointDefinition, error)
```

解析顺序：

```text
1. Common
2. Product
3. Version
4. Solver
5. Capability
```

最终得到唯一可执行 Endpoint。

---

# 28. Dispatcher

Dispatcher 是 MCP 到 MIDAS 的核心执行引擎。

```text
MCP Tool
  ↓
Normalize
  ↓
Resolve
  ↓
Validate
  ↓
Dependency Check
  ↓
Build Request
  ↓
Execute HTTP
  ↓
Parse Response
  ↓
Persist
  ↓
Audit
  ↓
Return
```

---

# 29. DispatchRequest

```go
type DispatchRequest struct {
    RequestID       string
    ProjectID       string
    SoftwareID      string
    ConnectionID    string

    Endpoint        string
    Method          string
    Payload         any

    AgentID         string
    SessionID       string

    ValidateOnly    bool
    Atomic          bool
    SaveVersion     bool
}
```

---

# 30. RuntimeContext

```go
type RuntimeContext struct {
    ProjectID        string
    SoftwareID       string
    ConnectionID     string

    Vendor           string
    Product          string
    Version          string
    Solver           string

    Endpoint         string
    RegistryVersion  string

    RequestID        string
    JobID            string
}
```

---

# 31. HTTP Client

HTTP Client 统一处理：

```text
Base URL
MAPI-Key
Timeout
TLS
Headers
Retry
Trace ID
```

标准 Header：

```http
Content-Type: application/json
MAPI-Key: <secret>
```

MAPI-Key 只能从 Secret Store 读取。

LLM、MCP Schema、Prompt、普通日志均不得出现完整 Key。

---

# 32. Secret Store

## Windows

优先：

```text
Windows Credential Manager / DPAPI
```

## Linux

优先：

```text
Secret Service
```

## Fallback

```text
AES-256-GCM
```

Master Key 不得和加密数据一起明文保存。

---

# 33. API Key 生命周期

软件管理页面支持：

```text
新增 Key
更新 Key
测试 Key
失效 Key
更换连接
```

只显示掩码：

```text
••••••••••9A7F
```

不提供“显示完整 Key”功能。

---

# 34. 多软件 WebUI

左侧：

```text
MIDAS
├── 软件管理
├── API 连接
├── 软件能力
├── Endpoint Registry
└── API 日志
```

软件管理表：

```text
名称 | 产品 | 版本 | Solver | API | 状态 | 默认
```

---

# 35. 添加软件页面

字段：

```text
软件名称
产品
版本
Build
Solver
环境
Base URL
MAPI-Key
描述
启用
```

按钮：

```text
自动识别
测试连接
保存
```

---

# 36. Connection Test

流程：

```text
Base URL
  ↓
API Request
  ↓
MAPI-Key
  ↓
Health Check
  ↓
Product Detection
  ↓
Version Detection
  ↓
Capability Detection
```

返回：

```json
{
  "success": true,
  "software_id": "civil-main",
  "product": "CIVIL NX",
  "version": "2026",
  "latency_ms": 23,
  "status": "CONNECTED"
}
```

---

# 37. Project Binding

每个工程必须绑定：

```text
software_id
connection_id
product
version
solver
```

工程运行时不能凭空选择另一个软件。

---

# 38. ProjectContext

```go
type ProjectContext struct {
    ProjectID          string
    SoftwareID         string
    ConnectionID       string
    MidasProduct       string
    MidasVersion       string
    Solver             string
    ActiveModel        string
    ModelVersion       string
    State              ProjectState
    UnitSystem         string
    DesignProfile      string
    CodeProfile        string
}
```

---

# 39. SessionContext

```go
type SessionContext struct {
    SessionID            string
    DefaultProjectID     string
    DefaultSoftwareID    string
    DefaultConnectionID  string
    UserID               string
}
```

工具中 `software_id` 可以为空。

解析规则：

```text
显式 software_id
    ↓
Project Binding
    ↓
Session Default
```

---

# 40. Project State Machine

```text
EMPTY
 ↓
PROJECT_CREATED
 ↓
MODEL_DRAFT
 ↓
MODEL_VALIDATED
 ↓
LOAD_READY
 ↓
ANALYSIS_READY
 ↓
ANALYZING
 ↓
ANALYSIS_COMPLETE
 ↓
DESIGNING
 ↓
DESIGN_COMPLETE
 ↓
VERIFICATION_COMPLETE
 ↓
REPORT_BUILDING
 ↓
FINAL
```

发现问题可以回退到：

```text
MODEL_DRAFT
LOAD_READY
ANALYSIS_READY
DESIGNING
```

但不能直接覆盖历史版本。

---

# 41. Model Version

```go
type ModelVersion struct {
    ID             string
    ProjectID      string
    Version        int
    ParentVersion  int
    ModelHash      string
    InputHash      string
    ChangeSummary  string
    CreatedBy      string
    CreatedAt      time.Time
}
```

示例：

```text
v23
Parent: v22
Change: Column C102 changed from H500x300 to H550x350
```

---

# 42. 为什么必须版本化

计算书必须能回答：

> 这本计算书使用的是哪一个模型？

因此：

```text
Report
  ↓
Model Version
  ↓
Analysis Job
  ↓
Result Set
  ↓
Design Result
```

形成可复现证据链。

---

# 43. Operation DAG

模型编译之后不是立即顺序调用 API，而是先形成 Operation DAG。

例如：

```text
UNIT
│
├── MATL
│    └── SECT
│         └── ELEM
│
├── NODE
│    └── ELEM
│
├── STLD
│    └── BMLD
│
└── STLD
     └── LCOM
```

这样可以自动解决依赖顺序。

---

# 44. Operation

```go
type Operation struct {
    ID            string
    Endpoint      string
    Action        string
    Data          any
    Dependencies  []string
    Rollback      *RollbackOperation
    Description   string
}
```

---

# 45. Engineering Model

内部模型至少包括：

```text
Project
Geometry
Grid
Story
Node
Element
Material
Section
Boundary
Load Case
Load
Load Combination
Analysis
Design
Results
```

---

# 46. Model Compiler

```go
type ModelCompiler interface {
    Compile(project *EngineeringProject) ([]Operation, error)
}
```

例如用户说：

```text
创建五层钢框架
```

Compiler 产生：

```text
UNIT
STYP
MATL
SECT
NODE
ELEM
CONS
STLD
BMLD
LCOM
ANALYSIS CONTROL
```

---

# 47. Validation

分三级：

## Level 1：Schema Validation

检查 JSON 字段类型和必填字段。

## Level 2：Engineering Validation

检查工程语义：

- 节点重复
- 单元重复
- 断链
- 零长度
- 材料缺失
- 截面缺失
- 支座缺失
- 楼层异常
- 单位异常

## Level 3：Dependency Validation

检查 MIDAS 数据引用关系。

---

# 48. Delete Dependency Check

例如删除：

```text
NODE 1001
```

先检查：

```text
ELEM
CONS
CNLD
BMLD
OTHER
```

如果存在：

```json
{
  "success": false,
  "error": {
    "code": "DEPENDENCY_EXISTS",
    "dependencies": {
      "ELEM": [12, 15],
      "CONS": [8]
    }
  }
}
```

---

# 49. Batch 与 Atomic

大批量数据必须支持：

```text
Validate
 ↓
Execute
 ↓
Verify
```

`atomic=true` 时：

- 能回滚则回滚
- 无法回滚则建立失败版本
- 不允许隐藏部分成功

返回：

```json
{
  "created": 1000,
  "updated": 0,
  "failed": 0,
  "model_version": 24
}
```

---

# 50. DB 数据通用模式

官方 DB 写入常采用：

```json
{
  "Assign": {
    "1": {
      "...": "..."
    },
    "2": {
      "...": "..."
    }
  }
}
```

例如节点：

```json
{
  "Assign": {
    "1001": {
      "X": 0,
      "Y": 0,
      "Z": 0
    },
    "1002": {
      "X": 8,
      "Y": 0,
      "Z": 0
    }
  }
}
```

MCP 层不要求 LLM 自己生成 `Assign` 包装，Dispatcher 根据 Registry 自动生成。

---

# 51. DOC 通用模式

例如：

```json
{
  "Argument": {}
}
```

OPEN / SAVEAS 可以是路径参数。

阶段另存：

```json
{
  "Argument": {
    "EXPORT_PATH": "C:\\MIDAS\\Stage1.mcb",
    "STAGE_STEP": "Stage1"
  }
}
```

MCP Tool 只提供 `command + argument`，不让 LLM 直接写 URI。

---

# 52. OPE 层

OPE 是操作级能力，不应该独立变成 MCP Tool。

逻辑上仍统一进入四工具。

当前 OPE 体系包括例如：

```text
PROJECTSTATUS
DIVIDEELEM
SECTPROP
USLC
LINEBMLD
AUTOMESH
SSPS
EDMP
STOR
STORY_PARAM
STORY_IRR_PARAM
STORPROP
MEMB
GUSTFACTOR
LCOM-GEN
LCOM-CONC
LCOM-STEEL
LCOM-SRC
GSBG
```

具体能力必须按产品/版本 Registry 管理。

---

# 53. VIEW 层

VIEW 是图形/界面控制能力。

逻辑 Endpoint 包括：

```text
SELECT
CAPTURE
PRECAPTURE
ANGLE
ACTIVE
DISPLAY
RESULTGRAPHIC
```

最终用于：

- 三维模型图
- 平面图
- 立面图
- 变形图
- 荷载图
- 反力图
- 梁内力图
- 应力图
- 模态图
- 屈曲图

---

# 54. POST 层

POST 是结果数据核心。

内部 Registry 需要支持：

```text
Preprocess Table
Analysis Result Table
Analysis Story Table
Time History Result Table
Heat of Hydration Result Table
Time History Text
Pushover Text
Design POST
```

结果查询优先级：

```text
Summary
 ↓
Maximum / Minimum
 ↓
Critical
 ↓
Specific entity
 ↓
Full dataset
```

---

# 55. Result Store

ResultStore 是 StructAI 的数字事实源。

```sql
CREATE TABLE result_sets (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    model_version INTEGER NOT NULL,
    analysis_job_id TEXT,
    result_type TEXT NOT NULL,
    source_endpoint TEXT,
    load_case TEXT,
    combination TEXT,
    unit_json TEXT,
    source_hash TEXT,
    created_at TEXT NOT NULL
);
```

---

# 56. Result Items

```sql
CREATE TABLE result_items (
    id TEXT PRIMARY KEY,
    result_set_id TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    position REAL,
    component TEXT,
    value REAL,
    unit TEXT,
    raw_json TEXT
);
```

---

# 57. Result Normalization

MIDAS 原始：

```text
HEAD
DATA
```

先解析成统一结构：

```json
{
  "entity_type": "BEAM",
  "entity_id": "102",
  "result_type": "MOMENT",
  "component": "MZ",
  "value": 425.3,
  "unit": "kN.m"
}
```

这样 Result Engine 与产品无关。

---

# 58. Evidence Chain

每个正式结果必须有 `Evidence ID`。

```json
{
  "evidence_id": "EVID-00001382",
  "source": "POST/TABLE",
  "result_set": "RSET-00023",
  "entity": "BEAM:102",
  "combination": "LC23",
  "value": 425.3,
  "unit": "kN.m"
}
```

正式计算书中的所有关键数字必须可追溯到 Evidence。

---

# 59. Result Intelligence

Result Engine 提供：

```text
MAX
MIN
ENVELOPE
CRITICAL
AVERAGE
STORY_MAX
MEMBER_MAX
COMBINATION_MAX
TREND
RANK
```

例如：

```json
{
  "query": "MAX_BEAM_MOMENT",
  "result": {
    "element": 102,
    "combination": "LC23",
    "value": 425.3,
    "unit": "kN.m"
  }
}
```

---

# 60. Finding

统一问题对象：

```go
type Finding struct {
    ID                  string
    ProjectID           string
    Severity            string
    Category            string
    EntityType          string
    EntityID            string
    Title               string
    Description         string
    SourceIDs           []string
    Status              string
    RecommendedAction   string
}
```

Severity：

```text
INFO
WARNING
REVIEW
ERROR
CRITICAL
```

---

# 61. Analysis Job

分析不是普通 API 调用。

建立 Job：

```go
type Job struct {
    ID            string
    ProjectID     string
    Type          string
    Status        string
    Progress      float64
    ModelVersion  int
    StartedAt     *time.Time
    FinishedAt    *time.Time
    ErrorCode     string
    ErrorMessage  string
}
```

状态：

```text
QUEUED
RUNNING
WAITING
SUCCESS
FAILED
TIMEOUT
CANCELLED
CONNECTION_LOST
UNKNOWN
```

---

# 62. 分析执行规则

普通 GET：

```text
retryable = true
```

普通 DB 写：

```text
有条件 retry
```

分析：

```text
retryable = false
```

原因：不能在不知道 MIDAS 当前进程状态的情况下自动重复启动计算。

---

# 63. Analysis Planner

根据工程意图和 Code Profile 自动产生 Analysis Plan。

例如：

```json
{
  "analysis_plan_id": "PLAN-001",
  "steps": [
    {"id": "A01", "type": "STATIC"},
    {"id": "A02", "type": "MODAL", "depends_on": ["A01"]},
    {"id": "A03", "type": "SEISMIC", "depends_on": ["A02"]},
    {"id": "A04", "type": "BUCKLING", "depends_on": ["A01"]}
  ]
}
```

根据项目还可进入：

```text
P-Delta
Time History
Nonlinear
Moving Load
Construction Stage
Heat Hydration
Settlement
Pushover
```

---

# 64. Analysis Failure Analyzer

分析失败时不能只返回：

```text
Analysis Failed
```

必须检查：

```text
刚体运动
模型奇异
孤立节点
零长度
材料缺失
截面缺失
支座错误
荷载引用错误
组合错误
模态异常
非线性不收敛
```

结果：

```text
Diagnosis
→ Recommended Fix
→ Patch
→ Validation
→ Re-run
```

---

# 65. Design Engine

统一接口：

```go
type DesignEngine interface {
    Name() string
    Prepare(
        project *EngineeringProject,
        results *ResultStore,
    ) error
    Run(
        ctx context.Context,
        project *EngineeringProject,
        results *ResultStore,
    ) (*DesignResult, error)
}
```

实现：

```text
SteelDesignEngine
ConcreteDesignEngine
SRCDesignEngine
SeismicDesignEngine
StabilityEngine
BridgeDesignEngine
```

---

# 66. 钢结构设计流程

```text
构件识别
 ↓
设计长度
 ↓
计算长度
 ↓
长细比
 ↓
截面分类
 ↓
轴压
 ↓
受弯
 ↓
剪切
 ↓
压弯
 ↓
整体稳定
 ↓
局部稳定
 ↓
节点/构造要求
 ↓
最终验算
```

---

# 67. 混凝土设计

覆盖：

```text
梁
柱
板
墙
基础
```

每个构件：

```text
内力
设计组合
截面
材料
承载力
裂缝
变形
构造
配筋
```

---

# 68. 抗震设计

Seismic Engine 处理：

```text
周期
振型
质量参与系数
层间位移角
楼层剪力
刚度比
承载力比
扭转
偶然偏心
薄弱层
强弱柱
强剪弱弯
```

结果必须关联 Evidence。

---

# 69. Optimization Engine

优化不是让 LLM 随机换截面。

正式定义：

```text
Objective
Constraints
Variables
Candidate
Analysis
Design
Verification
```

示例：

```json
{
  "objective": "MIN_STEEL_WEIGHT",
  "constraints": [
    "UTILIZATION <= 1.0",
    "DRIFT <= LIMIT",
    "SLENDERNESS <= LIMIT"
  ],
  "variables": [
    "BEAM_SECTION",
    "COLUMN_SECTION",
    "BRACE_SECTION"
  ]
}
```

---

# 70. Optimization Loop

```text
Candidate 1
 ↓
Analysis
 ↓
Design
 ↓
Check Constraints
 ↓
Candidate 2
 ↓
...
 ↓
Feasible Candidate Set
 ↓
Select by objective
```

每个 Candidate 都必须有 Model Version。

---

# 71. Graphics Engine

图形分两类。

## A. MIDAS 原生图形

通过 VIEW/CAPTURE 等能力获取。

## B. StructAI 原生图形

使用 Result Store 生成：

```text
利用率柱状图
层间位移图
楼层剪力图
构件统计图
趋势图
优化前后对比图
```

---

# 72. Figure 数据结构

```go
type Figure struct {
    ID            string
    Type          string
    Source        string
    ProjectID     string
    ModelVersion  int
    ResultSetID   string
    EvidenceIDs   []string
    Path          string
    Width         int
    Height        int
    Format        string
    Metadata      map[string]any
}
```

---

# 73. 图形类型

```text
MODEL_3D
MODEL_PLAN
MODEL_ELEVATION
MODEL_SECTION
LOAD_DISTRIBUTION
BOUNDARY
MESH
DEFORMED_SHAPE
DISPLACEMENT_CONTOUR
STRESS_CONTOUR
BEAM_MOMENT
BEAM_SHEAR
BEAM_AXIAL
PLATE_FORCE
PLATE_STRESS
MODE_SHAPE
BUCKLING_MODE
STORY_DRIFT
STORY_SHEAR
UTILIZATION
MEMBER_STATISTICS
OPTIMIZATION_COMPARISON
```

---

# 74. Report Engine

Report Engine 不从 LLM 直接生成最终数字。

流程：

```text
Result Store
 ↓
Design Result
 ↓
Verification
 ↓
Figure
 ↓
Report Data Model
 ↓
Template Engine
 ↓
DOCX
 ↓
PDF
 ↓
HTML
```

---

# 75. ReportModel

```go
type ReportModel struct {
    Cover             CoverSection
    Project           ProjectSection
    DesignBasis       DesignBasisSection
    StructuralSystem  StructuralSystemSection
    Materials         []MaterialSection
    Loads             []LoadSection
    Analysis          AnalysisSection
    Results           ResultSection
    Design            DesignSection
    Verification      VerificationSection
    Findings          []Finding
    Figures           []Figure
    Conclusions       ConclusionSection
    Appendix          AppendixSection
}
```

---

# 76. 计算书结构

```text
1. 封面
2. 工程概况
3. 设计依据
4. 设计参数
5. 材料
6. 截面
7. 结构体系
8. 计算模型
9. 模型检查
10. 荷载
11. 荷载组合
12. 分析方法
13. 模态分析
14. 静力分析
15. P-Delta
16. 风荷载
17. 地震
18. 层间位移
19. 构件内力
20. 应力
21. 构件设计
22. 稳定
23. 抗震
24. 控制构件
25. 优化过程
26. 最终设计
27. 问题与修复记录
28. 结论
29. 附录
30. API/模型审计
```

---

# 77. 计算书图形

至少自动生成：

```text
1. 三维模型图
2. 平面模型图
3. 立面模型图
4. 荷载布置图
5. 边界图
6. 变形图
7. 位移云图
8. 梁弯矩图
9. 梁剪力图
10. 应力图
11. 模态振型图
12. 层间位移图
13. 楼层剪力图
14. 构件利用率图
15. 优化前后对比图
```

具体项目可继续扩展。

---

# 78. Report Source Map

每章必须保存来源：

```json
{
  "section": "层间位移验算",
  "sources": [
    "RSET-00021",
    "EVID-00128",
    "FIG-00031"
  ]
}
```

这使计算书可审计。

---

# 79. Workflow Engine

不要让 Master Agent 自己记住所有步骤。

Workflow Engine 负责：

- 顺序
- 依赖
- 状态
- 重试
- 锁
- 版本
- 审计

Agent 负责：

- 理解任务
- 选择策略
- 解释结果
- 处理异常
- 选择优化方向

---

# 80. Structural Design Workflow

```yaml
workflow: structural_design
steps:
  - id: create_project
    action: project.create

  - id: build_model
    action: model.compile
    depends_on:
      - create_project

  - id: validate_model
    action: model.validate
    depends_on:
      - build_model

  - id: build_loads
    action: load.compile
    depends_on:
      - validate_model

  - id: build_combinations
    action: combination.compile
    depends_on:
      - build_loads

  - id: run_analysis
    action: analysis.run
    depends_on:
      - build_combinations

  - id: extract_results
    action: result.extract
    depends_on:
      - run_analysis

  - id: run_design
    action: design.run
    depends_on:
      - extract_results

  - id: verify
    action: verification.run
    depends_on:
      - run_design

  - id: build_figures
    action: graphics.build
    depends_on:
      - verify

  - id: build_report
    action: report.build
    depends_on:
      - build_figures
```

---

# 81. Model Validator

实现：

```text
NodeValidator
ElementValidator
MaterialValidator
SectionValidator
BoundaryValidator
LoadValidator
CombinationValidator
ConnectivityValidator
UnitValidator
StoryValidator
```

统一接口：

```go
type Validator interface {
    Name() string
    Validate(project *Project) []Finding
}
```

---

# 82. API Audit

每个 MCP 调用都必须审计：

```sql
CREATE TABLE api_audit (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    model_version INTEGER,
    tool TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    method TEXT,
    request_hash TEXT,
    response_hash TEXT,
    request_json TEXT,
    response_json TEXT,
    success INTEGER NOT NULL,
    error_code TEXT,
    error_message TEXT,
    agent_id TEXT,
    software_id TEXT,
    connection_id TEXT,
    created_at TEXT NOT NULL
);
```

注意：`request_json`、`response_json` 做敏感信息清洗，禁止保存 MAPI-Key。

---

# 83. Job Events

```sql
CREATE TABLE job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    level TEXT,
    event_type TEXT,
    message TEXT,
    progress REAL,
    payload_json TEXT,
    created_at TEXT NOT NULL
);
```

典型过程：

```text
MODEL_CHECK_START
MODEL_CHECK_OK
ANALYSIS_START
ANALYSIS_RUNNING
ANALYSIS_COMPLETE
RESULT_EXTRACT_START
RESULT_EXTRACT_COMPLETE
DESIGN_START
DESIGN_COMPLETE
REPORT_START
REPORT_COMPLETE
```

---

# 84. SQLite Schema 总览

核心表：

```text
software_profiles
connection_profiles
projects
project_versions
jobs
job_events
api_audit
result_sets
result_items
findings
figures
reports
report_sources
```

---

# 85. software_profiles

```sql
CREATE TABLE software_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    vendor TEXT NOT NULL,
    product_family TEXT,
    product TEXT NOT NULL,
    version TEXT,
    build TEXT,
    adapter TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

---

# 86. connection_profiles

```sql
CREATE TABLE connection_profiles (
    id TEXT PRIMARY KEY,
    software_id TEXT NOT NULL,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    api_key_ref TEXT NOT NULL,
    environment TEXT NOT NULL DEFAULT 'production',
    tls_verify INTEGER NOT NULL DEFAULT 1,
    timeout_ms INTEGER NOT NULL DEFAULT 30000,
    retry_count INTEGER NOT NULL DEFAULT 2,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_status TEXT,
    last_latency_ms INTEGER,
    last_checked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (software_id) REFERENCES software_profiles(id)
);
```

---

# 87. projects

```sql
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    software_id TEXT,
    connection_id TEXT,
    product TEXT,
    version TEXT,
    solver TEXT,
    state TEXT NOT NULL,
    unit_system TEXT,
    code_profile TEXT,
    model_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

---

# 88. MCP Resources

建议：

```text
structai://software
structai://software/{id}
structai://project
structai://project/model
structai://project/state
structai://project/issues
structai://project/results/summary
structai://project/design/summary
structai://project/report/status
```

这些 Resource 的作用是减少 Tool 调用和 Context 压力。

---

# 89. 软件 Resource

`structai://software` 返回软件列表，但绝不返回完整 Key。

```json
{
  "items": [
    {
      "id": "civil-main",
      "name": "汕尾 Civil 主机",
      "product": "CIVIL NX",
      "version": "2026",
      "status": "CONNECTED"
    },
    {
      "id": "gen-main",
      "name": "设计院 GEN 主机",
      "product": "GEN NX",
      "version": "2026",
      "status": "CONNECTED"
    }
  ]
}
```

---

# 90. Project Result Summary Resource

不要把 5 万条结果全部塞给 LLM。

推荐 Resource：

```text
structai://project/results/summary
```

返回：

```json
{
  "max_displacement": 32.8,
  "max_drift": 0.00182,
  "max_beam_utilization": 0.91,
  "max_column_utilization": 0.97,
  "critical_findings": 3
}
```

---

# 91. MCP Prompts

建议提供少量固定 Prompt：

```text
structural_model_check
run_analysis
analyze_results
run_design
verify_structure
generate_calculation_book
```

Prompt 不包含具体 MAPI-Key 和完整 Endpoint。

---

# 92. Context Compression

LLM 不加载全部 API Schema。

只按需加载：

```text
当前工程
+
当前产品
+
当前版本
+
当前 Endpoint Schema
```

例如用户要创建节点：

```text
NODE
 ↓
加载 NODE Schema
 ↓
Validation
 ↓
Execute
```

这样大幅降低 Context 消耗。

---

# 93. Result Compression

结果查询顺序：

```text
SUMMARY
 ↓
MAX/MIN
 ↓
CRITICAL
 ↓
Specific Entity
 ↓
Full Dataset
```

默认分页：

```text
page = 1
page_size = 100
```

最大 page_size 建议 1000。

---

# 94. 大批量建模策略

不要：

```text
1 Tool Call = 1 Node
```

而应该：

```text
1 Batch = N Objects
```

例如：

```text
10000 Nodes
30000 Elements
```

拆成适合 API 的 Batch，并记录 Batch ID。

---

# 95. 执行锁

同一个 Project 同一时间默认：

```text
1 个写入任务
1 个分析任务
1 个发布任务
```

防止：

```text
分析运行中
        ↓
另一个 Agent 修改模型
```

如果必须并行，建立模型 Clone。

---

# 96. Project Lock

```go
type ProjectLock struct {
    ProjectID string
    Holder    string
    Type      string
    Acquired  time.Time
    ExpiresAt time.Time
}
```

Lock 类型：

```text
WRITE
ANALYSIS
DESIGN
REPORT
PUBLISH
```

---

# 97. 安全策略

## 97.1 Key

不得进入：

```text
Prompt
Tool Description
MCP Result
普通日志
Audit Raw JSON
```

## 97.2 删除

需要依赖检查。

## 97.3 分析

不可盲目 Retry。

## 97.4 发布

必须绑定最终模型版本。

---

# 98. 产品切换规则

Project 绑定软件以后不能无条件切换：

```text
CIVIL NX
 ↓
GEN NX
```

应执行：

```text
Neutral Model Export
 ↓
Compatibility Check
 ↓
Conversion
 ↓
New Project / New Model Version
```

不能覆盖原始工程。

---

# 99. 多软件同时运行

StructAI 允许：

```text
CIVIL NX → Project A
GEN NX   → Project B
```

甚至：

```text
CIVIL NX Local
CIVIL NX Office
GEN NX Office
GEN NX Test
```

同时存在。

---

# 100. API 地址管理

Base URL 必须为 ConnectionProfile 字段。

不能写死：

```text
https://...
```

也不能写死：

```text
/civil
/gen
```

最终由 Adapter + Connection + Registry 共同确定。

---

# 101. API 访问统一流程

```text
Tool
 ↓
Runtime Context
 ↓
Connection Profile
 ↓
Secret Store
 ↓
Adapter
 ↓
Registry Resolve
 ↓
HTTP Client
 ↓
MIDAS
```

---

# 102. HTTP Retry

## GET

默认：

```text
2 retries
Exponential Backoff
```

## POST/PUT DB

仅在明确幂等或者请求 Hash 未改变时重试。

## ANAL

不自动重试。

---

# 103. Connection Lost

如果分析中断网：

```text
CONNECTION_LOST
```

先检测：

```text
MIDAS Process
API Status
Project Status
Job Status
```

确定后才能分类：

```text
SUCCESS
FAILED
UNKNOWN
```

---

# 104. 失败处理统一模型

```json
{
  "success": false,
  "error": {
    "code": "PRODUCT_CAPABILITY_UNSUPPORTED",
    "message": "...",
    "details": {},
    "request_id": "REQ-001",
    "software_id": "gen-main",
    "endpoint": "MOVING_LOAD"
  }
}
```

错误码建议：

```text
CONFIG_NOT_FOUND
SOFTWARE_NOT_FOUND
CONNECTION_NOT_FOUND
AUTH_FAILED
API_UNAVAILABLE
PRODUCT_MISMATCH
VERSION_UNSUPPORTED
SOLVER_UNSUPPORTED
ENDPOINT_NOT_FOUND
SCHEMA_INVALID
DEPENDENCY_EXISTS
PROJECT_STATE_INVALID
PROJECT_LOCKED
MIDAS_REQUEST_FAILED
MIDAS_ANALYSIS_FAILED
RESULT_PARSE_FAILED
REPORT_BUILD_FAILED
```

---

# 105. MCP 返回规范

成功：

```json
{
  "success": true,
  "operation": {
    "id": "OP-00128",
    "endpoint": "NODE",
    "action": "create"
  },
  "project": {
    "id": "P001",
    "model_version": 23
  },
  "result": {
    "created": 200,
    "updated": 0,
    "failed": 0
  },
  "evidence": [
    "EVID-00123"
  ]
}
```

---

# 106. Query 返回规范

```json
{
  "success": true,
  "endpoint": "NODE",
  "count": 2,
  "items": [
    {"id": "1", "X": 0, "Y": 0, "Z": 0},
    {"id": "2", "X": 8, "Y": 0, "Z": 0}
  ],
  "source": {
    "uri": "/db/NODE"
  }
}
```

`raw=true` 时才允许返回接近 MIDAS 原始结构。

---

# 107. Logging

日志分：

```text
application.log
api.log
job.log
security.log
```

推荐统一 JSONL：

```json
{
  "timestamp": "...",
  "level": "INFO",
  "request_id": "REQ-001",
  "project_id": "P001",
  "software_id": "civil-main",
  "endpoint": "NODE",
  "message": "create node batch"
}
```

绝对禁止记录完整 Key。

---

# 108. 生产目录结构

```text
structai-mcp/
├── cmd/
│   └── structai-mcp/
│       └── main.go
├── internal/
│   ├── mcp/
│   ├── config/
│   ├── software/
│   ├── connection/
│   ├── secrets/
│   ├── adapter/
│   ├── registry/
│   ├── dispatcher/
│   ├── project/
│   ├── engineering/
│   ├── analysis/
│   ├── result/
│   ├── design/
│   ├── verification/
│   ├── graphics/
│   ├── report/
│   ├── workflow/
│   ├── audit/
│   └── storage/
├── registry/
│   ├── common/
│   ├── products/
│   │   ├── civil_nx/
│   │   └── gen_nx/
│   └── versions/
├── schema/
├── templates/
├── migrations/
├── tests/
└── docs/
```

---

# 109. Go 模块边界

推荐：

```text
internal/mcp
    ↓
internal/workflow
    ↓
internal/engineering
    ↓
internal/dispatcher
    ↓
internal/adapter
    ↓
internal/registry
    ↓
internal/connection
    ↓
internal/http client
```

MCP 层不得反向依赖具体 CIVIL JSON。

---

# 110. MVP 实现范围

第一版必须完整跑通：

```text
CIVIL NX
或
GEN NX
```

任选一个首先作为完整链路验证，但架构同时支持二者。

MVP 工程流程：

```text
NEW
 ↓
UNIT
 ↓
STYP
 ↓
MATL
 ↓
SECT
 ↓
NODE
 ↓
ELEM
 ↓
CONS
 ↓
STLD
 ↓
BMLD
 ↓
LCOM
 ↓
MODEL VALIDATE
 ↓
ANAL
 ↓
POST RESULT
 ↓
VIEW CAPTURE
 ↓
REPORT
```

---

# 111. 第一批 Registry

```text
DOC
  NEW
  OPEN
  SAVE
  ANAL

DB
  UNIT
  STYP
  PJCF
  MATL
  SECT
  NODE
  ELEM
  CONS
  STLD
  BMLD
  LCOM

VIEW
  CAPTURE
  ANGLE
  DISPLAY
  RESULTGRAPHIC

POST
  REACTION
  DISPLACEMENT
  BEAMFORCE
  BEAMSTRESS
  STORYDRIFT
```

然后扩展到全量官方 Endpoint。

---

# 112. 结果闭环验收

第一个端到端测试必须做到：

```text
AI
 ↓
4 MCP Tools
 ↓
真实 MIDAS
 ↓
建立三维钢框架
 ↓
真实分析
 ↓
真实结果
 ↓
真实图形
 ↓
真实设计
 ↓
计算书
```

不能用 Mock 结果冒充完整链路。

Mock 可以用于单元测试，但最终集成测试必须连接真实 MIDAS 实例。

---

# 113. 测试矩阵

## MCP

```text
Tool Discovery
Schema Validation
Invalid Arguments
Unknown Tool
```

## Software

```text
Create Profile
Update Profile
Delete Profile
Connection Test
Auth Failure
Product Mismatch
Version Mismatch
```

## Registry

```text
Resolve NODE
Resolve ELEM
Resolve Product Override
Resolve Version Override
Resolve Unsupported Capability
```

## Dispatcher

```text
GET
POST
PUT
DELETE
Retry
Timeout
Dependency
Audit
```

## Project

```text
State Transition
Version Creation
Lock
Rollback
```

## Analysis

```text
Start
Running
Success
Failure
Timeout
Connection Lost
Unknown State
```

## Result

```text
Parse
Normalize
Evidence
Max
Min
Envelope
```

## Report

```text
Figure
Table
Source Map
DOCX
PDF
HTML
```

---

# 114. 安全验收

必须验证：

```text
MAPI-Key 不出现在 MCP Tool Schema
MAPI-Key 不出现在 Prompt
MAPI-Key 不出现在普通日志
MAPI-Key 不出现在 Audit Raw JSON
删除动作有依赖检查
Project Lock 有效
Report 绑定 Model Version
跨软件切换有兼容性检查
```

---

# 115. 性能目标

第一阶段建议：

```text
普通查询 P95 < 1 s（不含 MIDAS 计算）
小批量写入 P95 < 2 s
Registry Lookup < 10 ms
SQLite 元数据查询 < 50 ms
MCP Tool 构造 < 20 ms
```

分析性能由 MIDAS Solver 决定，不在 MCP 层虚构 SLA。

---

# 116. 并发策略

同一 Project：

```text
写入互斥
分析互斥
发布互斥
```

不同 Project：

```text
可以并行
```

不同 MIDAS Connection：

```text
可以并行
```

---

# 117. 多软件同时运行示例

```text
Project A
CIVIL NX
civil-office

Project B
GEN NX
gen-office

Project C
CIVIL NX
civil-test
```

MCP Tool 仍然只有四个。

---

# 118. 一个完整 Agent 任务

用户：

```text
创建一栋五层钢框架，柱距8m，跨度24m，层高4.2m，
Q355，考虑恒载、活载、风、地震，完成计算并出计算书。
```

内部：

```text
1. 选择 Project
2. 选择 CIVIL NX / GEN NX Profile
3. 创建项目
4. 生成 Engineering Intent
5. Model Compiler
6. Operation DAG
7. 写入 MIDAS
8. Validation
9. 荷载生成
10. 荷载组合
11. Analysis Plan
12. ANAL
13. Result Store
14. Design Engine
15. Verification
16. Findings
17. Optimization
18. Re-analysis
19. Graphics
20. Report
21. Final Audit
```

---

# 119. 最终输出 Project Package

```text
Project-001/
├── model/
│   ├── final.mcb
│   ├── final.json
│   └── final.mct
├── input/
│   ├── project.json
│   ├── loads.json
│   └── combinations.json
├── analysis/
│   ├── analysis.json
│   ├── modal.json
│   ├── seismic.json
│   └── result/
├── design/
│   ├── steel.json
│   ├── concrete.json
│   └── verification.json
├── figures/
│   ├── model_3d.png
│   ├── model_plan.png
│   ├── load.png
│   ├── displacement.png
│   ├── stress.png
│   ├── moment.png
│   ├── mode1.png
│   └── drift.png
├── report/
│   ├── StructAI_Calculation_Report.docx
│   ├── StructAI_Calculation_Report.pdf
│   └── StructAI_Calculation_Report.html
└── audit/
    ├── operation_log.jsonl
    ├── model_versions.json
    ├── api_trace.jsonl
    └── evidence.json
```

---

# 120. 最终逻辑分层

```text
MCP
= 控制入口

Software Manager
= 管理 MIDAS 系列软件

Connection Manager
= 管理 Base URL / Key / 环境

Adapter
= 产品差异

Registry
= MIDAS API 知识

Dispatcher
= 执行 API

Engineering Layer
= 结构语义

Workflow Engine
= 一条龙流程

Analysis Engine
= 分析调度

Result Store
= 数字事实

Design Engine
= 规范设计

Verification Engine
= 独立校核

Graphics Engine
= 图形

Report Engine
= 计算书

Audit Engine
= 全链路审计
```

---

# 121. 版本与兼容性策略

推荐版本组合：

```text
StructAI MCP Version
    ↓
Adapter Version
    ↓
MIDAS Product Version
    ↓
Registry Version
```

例如：

```text
StructAI 1.0
CIVIL NX Adapter 1.0
CIVIL NX 2026
Registry 2026.07
```

如果 MIDAS API 改动：

```text
新增 Registry Override
```

而不是直接破坏 Common Registry。

---

# 122. Registry Source Governance

Registry 每条 Endpoint 必须记录：

```text
source.official
source.page
source.url
source.title
source.retrieved_at
source_hash
```

正式发布前：

```text
官方来源
→ Schema
→ Sample
→ Parser
→ Test
```

必须全部有对应记录。

---

# 123. 官方 Endpoint 覆盖原则

当前官方手册的 Endpoint 大类包括：

```text
DOC
DB
OPE
VIEW
POST
```

DB 继续分：

```text
Project
View
Structure
Node/Element
Properties
Boundary
Static Loads
Temperature
Prestress
Moving Loads
Dynamic Loads
Construction Stage
Heat Hydration
Settlement
Misc
Analysis
Analysis Results
Bridge/Time History/Pushover Results
Design
```

StructAI 最终目标是以官方手册逐二级页面录入完整 Registry，不以历史镜像作为最终权威。

---

# 124. 产品差异策略

Endpoint 支持：

```yaml
products:
  - CIVIL_NX

solvers:
  - STANDARD
  - HYPER_S

versions:
  min: 2026
  max: 2026
```

不匹配时返回结构化错误。

---

# 125. 跨软件设计

如果未来支持：

```text
CIVIL NX
GEN NX
```

同一个工程模型由 Neutral Engineering Model 表达。

以后添加其他软件时只需要：

```text
ProductDefinition
Adapter
Registry
Capability
Converter
```

MCP 四个工具不改变。

---

# 126. 最终生产运行方式

Windows：

```text
structai-mcp.exe --stdio
```

可选：

```text
structai-mcp.exe --http :8765
```

生产建议：

```text
MCP stdout
= 只输出协议数据

日志
= stderr / log file
```

不能把普通日志写进 stdout 污染 stdio MCP 通道。

---

# 127. 配置文件

```yaml
config:
  database:
    path: ./data/structai.db

  secrets:
    provider: auto

  mcp:
    transport: stdio

  registry:
    path: ./registry

  logging:
    level: info

  defaults:
    software_id: ""
    connection_id: ""
```

MAPI-Key 不进入 config.yaml。

---

# 128. 启动流程

```text
Start
 ↓
Load config
 ↓
Open SQLite
 ↓
Load Secret Provider
 ↓
Load Software Profiles
 ↓
Load Connection Profiles
 ↓
Load Product Adapters
 ↓
Load Registry
 ↓
Validate Registry
 ↓
Start MCP
```

不要求启动时连接所有软件，连接采用 Lazy Connect。

---

# 129. Lazy Connect

启动：

```text
读取配置
```

实际调用：

```text
Project
 ↓
Connection
 ↓
Adapter.Connect
```

这样某个 GEN NX 没启动，不会影响 CIVIL NX 项目。

---

# 130. 自动识别软件

仅提供 Base URL + MAPI-Key 时，可以尝试：

```text
Health
Project Status
Product Info
```

识别：

```text
CIVIL NX
GEN NX
Unknown
```

无法确认时要求 WebUI 选择 Product。

---

# 131. 软件迁移

以后支持：

```text
CIVIL NX
 ↓
Neutral Engineering Model
 ↓
GEN NX
```

迁移后必须：

```text
Compatibility Check
Warning Review
New Project Version
```

原始项目不覆盖。

---

# 132. 计算书发布规则

只有满足：

```text
MODEL_VALIDATED
ANALYSIS_COMPLETE
DESIGN_COMPLETE
VERIFICATION_COMPLETE
```

才能进入：

```text
REPORT_BUILDING
```

最终报告绑定：

```text
Project ID
Model Version
Analysis Result Set
Design Result
Figure Set
```

---

# 133. 报告中的数字规则

正式报告中的所有关键数字必须来自：

```text
ResultStore
DesignResult
VerificationResult
```

LLM 只负责：

```text
解释
归纳
组织文本
```

LLM 不允许凭记忆生成正式工程数字。

---

# 134. 图形与数据绑定

每张图必须保存：

```text
figure_id
model_version
result_set_id
evidence_ids
load_case
combination
```

不允许创建“看起来正确但与真实结果没有关联”的工程图。

---

# 135. Master Agent / Specialist Agent

推荐 Agent 架构：

```text
Master Agent
│
├── Model Agent
├── Load Agent
├── Analysis Agent
├── Result Agent
├── Design Agent
├── Verification Agent
└── Report Agent
```

Master Agent 负责任务规划；Workflow Engine 保证执行顺序。

---

# 136. Master Agent 不直接生成原始 API

错误方式：

```text
LLM → /db/NODE → JSON
```

正确方式：

```text
LLM
 ↓
Engineering Intent
 ↓
Semantic Operation
 ↓
Model Compiler
 ↓
Endpoint Registry
 ↓
MCP Tool
```

这样可以控制 Context、减少幻觉和降低维护成本。

---

# 137. 标准工程数据流

```text
User Input
 ↓
Intent Model
 ↓
Engineering Model
 ↓
Operation DAG
 ↓
MCP
 ↓
MIDAS
 ↓
Raw Result
 ↓
Normalized Result
 ↓
Evidence
 ↓
Design
 ↓
Verification
 ↓
Figure
 ↓
Report
```

---

# 138. 第一阶段开发计划

## Part 1

Config Core

## Part 2

Software Manager

## Part 3

Connection Manager

## Part 4

Secret Store

## Part 5

Product Adapter Interface

## Part 6

CIVIL NX Adapter

## Part 7

GEN NX Adapter

## Part 8

Endpoint Registry

## Part 9

MCP Server

## Part 10

Dispatcher

## Part 11

Project / Version

## Part 12

Job Manager

## Part 13

Result Store

## Part 14

Model Validator

## Part 15

Analysis Planner

## Part 16

Design Engine Interface

## Part 17

Graphics Engine

## Part 18

Report Engine

---

# 139. 第一阶段验收

必须做到：

```text
安装 structai-mcp
 ↓
新增 CIVIL NX Profile
 ↓
输入 Base URL
 ↓
保存 Key 到 Secret Store
 ↓
测试连接
 ↓
创建 Project
 ↓
绑定 Connection
 ↓
MCP Discovery
 ↓
调用 midas_db_assign
 ↓
真实写入 NODE
 ↓
调用 midas_db_query
 ↓
读取 NODE
 ↓
Audit 生成
```

---

# 140. 第二阶段验收

```text
NODE
ELEM
MATL
SECT
CONS
STLD
BMLD
LCOM
```

能够建立完整三维钢框架。

---

# 141. 第三阶段验收

```text
ANAL
 ↓
POST
 ↓
VIEW
```

真实：

```text
静力
模态
P-Delta
```

并得到：

```text
位移
反力
梁力
应力
层间位移
```

---

# 142. 第四阶段验收

```text
Steel Design
Verification
Optimization
```

至少形成：

```text
控制构件
利用率
超限构件
优化结果
```

---

# 143. 第五阶段验收

计算书必须包含：

```text
模型图
荷载图
变形图
内力图
应力图
模态图
层间位移图
利用率图
```

以及：

```text
DOCX
PDF
HTML
```

---

# 144. 最终产品边界

最终 StructAI：

```text
                    StructAI
                       │
        ┌──────────────┴──────────────┐
        │                             │
 Engineering AI                  MCP Core
        │                             │
        │                   4 个统一 MCP Tool
        │                             │
        ▼                             ▼
 Neutral Engineering Model     Software Manager
                                      │
                  ┌───────────────────┼────────────────┐
                  │                   │                │
               CIVIL NX           GEN NX        Future Products
                  │                   │                │
                  ▼                   ▼                ▼
               Adapter            Adapter          Adapter
                  │                   │                │
                  └───────────────────┼────────────────┘
                                      ▼
                              Endpoint Registry
                                      │
                                      ▼
                                 Dispatcher
                                      │
                                      ▼
                                 MIDAS API
                                      │
                                      ▼
                                  ResultStore
                                      │
                     ┌────────────────┼───────────────┐
                     ▼                ▼               ▼
                  Design         Verification      Graphics
                     │                │               │
                     └────────────────┼───────────────┘
                                      ▼
                                   Report
```

---

# 145. 核心原则最终版

1. MCP 工具少而稳定。
2. MIDAS Endpoint 全部由 Registry 管理。
3. 软件产品通过 Profile 管理。
4. Base URL 属于 ConnectionProfile。
5. MAPI-Key 只能进入 Secret Store。
6. Product / Version / Solver 必须进入 Runtime Context。
7. Project 必须绑定软件连接。
8. LLM 不直接生成 URL。
9. LLM 不直接管理 MAPI-Key。
10. 所有工程数字必须有 Result/Evidence 来源。
11. 所有重要模型修改必须版本化。
12. 所有长计算必须 Job 化。
13. 删除必须做依赖检查。
14. 分析失败必须进入诊断流程。
15. 计算书必须绑定模型版本和结果版本。
16. 图形必须绑定真实结果。
17. Product Adapter 负责软件差异。
18. Neutral Engineering Model 负责软件无关工程语义。
19. Workflow Engine 负责一条龙执行。
20. MCP Core 不因新增 MIDAS 产品而增加 Tool 数量。

---

# 146. 建议的下一份配套开发文档

本总文档完成后，实际编码建议继续拆成以下独立文档：

```text
01_MCP_PROTOCOL.md
02_SOFTWARE_MANAGER.md
03_CONNECTION_MANAGER.md
04_SECRET_STORE.md
05_ADAPTER_INTERFACE.md
06_ENDPOINT_REGISTRY.md
07_DISPATCHER.md
08_PROJECT_STATE.md
09_OPERATION_DAG.md
10_ANALYSIS_ENGINE.md
11_RESULT_STORE.md
12_DESIGN_ENGINE.md
13_VERIFICATION_ENGINE.md
14_GRAPHICS_ENGINE.md
15_REPORT_ENGINE.md
16_WORKFLOW_ENGINE.md
17_AUDIT_SECURITY.md
18_TEST_MATRIX.md
19_CIVIL_NX_REGISTRY.md
20_GEN_NX_REGISTRY.md
21_DEPLOYMENT.md
22_END_TO_END_EXAMPLES.md
```

---

# 147. 开发结论

StructAI 的 MCP 最终不是一个“把 MIDAS API 包起来的服务器”。

正确定位是：

> **一个面向结构工程 AI 的多结构工程软件执行平台。**

四个 MCP Tool 是稳定入口：

```text
midas_doc
midas_db_query
midas_db_assign
midas_db_delete
```

多软件通过：

```text
SoftwareProfile
ConnectionProfile
ProductAdapter
Version/Solver Registry
Capability Matrix
```

实现。

工程通过：

```text
Neutral Engineering Model
Operation DAG
Workflow Engine
```

实现。

计算通过：

```text
Analysis Job
Result Store
Evidence Chain
```

实现。

设计通过：

```text
Design Engine
Verification Engine
Optimization Engine
```

实现。

最终通过：

```text
Graphics Engine
Report Engine
```

输出真正可追溯的结构计算成果。

---

# 148. 官方依据

本方案涉及的 MIDAS API 原始协议、Endpoint 分类和产品范围，应持续以官方 `MIDAS API Online Manual` 为最终依据。官方当前版本页面明确以 NX series（包括 CIVIL NX、GEN NX）为对象，并采用 RESTful API；文档页面当前记录的最近编辑日期为 2026-07-14。

开发过程中如本文档与某一 MIDAS 软件实际版本的官方二级页面存在差异，以该软件对应版本的官方二级页面为准，并通过 Registry Version Override 修正，不直接破坏 Common Registry。

---

# 149. 最终验收标准

只有满足以下条件，StructAI MCP Core 才算 V1.0 完成：

```text
[✓] 支持多个 MIDAS Software Profile
[✓] 支持多个 Connection Profile
[✓] 支持 Base URL 配置
[✓] 支持 MAPI-Key 安全保存
[✓] 支持 CIVIL NX Adapter
[✓] 支持 GEN NX Adapter
[✓] 支持 Version / Solver
[✓] 支持 Capability Matrix
[✓] 只有 4 个 MCP Tool
[✓] Endpoint Registry 可动态加载
[✓] Registry 支持 Product/Version/Solver Override
[✓] Dispatcher 完成统一调用
[✓] Project Binding 完成
[✓] Project State 完成
[✓] Model Version 完成
[✓] Validation 完成
[✓] Dependency Check 完成
[✓] Audit 完成
[✓] Job Manager 完成
[✓] Result Store 完成
[✓] Evidence Chain 完成
[✓] Analysis Pipeline 完成
[✓] Design Engine 接口完成
[✓] Verification Engine 接口完成
[✓] Graphics Engine 接口完成
[✓] Report Engine 接口完成
[✓] End-to-End 真实 MIDAS 测试完成
```

这份文档是 StructAI MCP 的总设计基线；后续源码开发应以本架构为准，新增能力优先增加 Registry / Adapter / Semantic Layer，而不是随意增加 MCP Tool。
