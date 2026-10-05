# 04_STRUCTAI_MCP_V2_MIDAS_ADAPTER.md — MIDAS Adapter 完整实现

V2.0 Consolidated MIDAS ⑰～㉛。完整覆盖 CIVIL NX / GEN NX、官方 API 基线、MAPI-Key、HTTP Client、API Registry、Schema、Transformer、Document、Model、Load、Analysis、Result、View、Design、Recovery、Contract Test、E2E、Multi-Version、Production Hardening。

---

# 内容保全说明

本主文档按六文档体系重新组织。**原有内容不删除**；各来源规范以完整原文收录在对应章节，确保代码、字段、状态、测试要求和实现约束均可追溯。


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

- `midasall`：完整收录。
