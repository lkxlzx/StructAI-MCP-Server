# 05_STRUCTAI_MCP_V2_ADAPTER_SDK.md — 通用 Adapter SDK

V2.0 Adapter SDK。定义 EngineeringSoftwareAdapter、Manifest、Plugin Loader、Adapter Manager、Capability、Version、Registry、Transformer、Health、Error、Cancellation、Mock 与 Contract Test，使 ETABS/SAP2000/ANSYS/ABAQUS/OpenSees 可按同一接口扩展。

---

# 内容保全说明

本主文档按六文档体系重新组织。**原有内容不删除**；各来源规范以完整原文收录在对应章节，确保代码、字段、状态、测试要求和实现约束均可追溯。


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



# 来源映射

- `adapter`：完整收录。
