# 03_STRUCTAI_MCP_V2_MCP_RUNTIME.md — 9 Tools + MCP Runtime

V2.0 Consolidated MCP Runtime。冻结 9 Tool、Operation、Schema、Risk、Execution Mode、Permission、Capability、Confirmation、Idempotency、Lock、Dry Run、Batch、Pre/Post Conditions、Error，并完整覆盖 Session、STDIO、Streamable HTTP、Progress、Cancellation、Generic MCP Client E2E。

---

# 内容保全说明

本主文档按六文档体系重新组织。**原有内容不删除**；各来源规范以完整原文收录在对应章节，确保代码、字段、状态、测试要求和实现约束均可追溯。


# 完整收录：tools5

# StructAI MCP Server V2.0
## 9 个 MCP Tool 完整实现规范

**Document:** `StructAI_MCP_Server_V2.0_9_MCP_Tools_Complete_Implementation_Specification.md`  
**Version:** 2.0  
**Status:** Core Alpha Tool Contract Baseline  
**Depends on:**  
- `StructAI_MCP_Server_V2.0_Core_Database_Design_Revision_V2.md`
- `StructAI_MCP_Server_V2.0_Core_Development_Document_Revision_V2.md`
- `StructAI_MCP_Server_V2.0_Core_Implementation_Specification_Revision_V2.md`
- `StructAI_MCP_Server_V2.0_Core_Python_Implementation_Specification_Revision_V2.md`

---

# 1. 文档目的

本文件冻结 StructAI MCP Server Core Alpha 的 **9 个 MCP Tool Contract**。

前三份/第四份文档已经冻结：

```text
Core Runtime
Database
Execution Pipeline
Security
Task Engine
Adapter
MCP Transport
```

本文件只负责冻结：

```text
9 MCP Tools
Operation
JSON Schema
Parameters
Output
Risk
Execution Mode
Permission
Capability
Confirmation
Idempotency
Lock
Dry Run
Batch
Preconditions
Postconditions
Errors
Examples
Generic AI Client invocation
```

本文件不得重新定义 Core Runtime。

---

# 2. 设计原则

## 2.1 Tool ≠ API

禁止：

```text
engineering_analysis → /anal/STATIC
engineering_model_query → /db/NODE
```

必须：

```text
MCP Tool
 ↓
Operation
 ↓
Capability
 ↓
API Registry
 ↓
Adapter
 ↓
Engineering Software
```

---

# 3. 9 个 Tool 总表

| # | Tool | 领域 | 默认风险 | 默认模式 |
|---|---|---|---|---|
| 1 | `engineering_doc` | 工程文档 | MEDIUM | SYNC / ASYNC |
| 2 | `engineering_model_query` | 模型查询 | LOW | SYNC |
| 3 | `engineering_model_assign` | 模型修改 | MEDIUM | SYNC / ASYNC |
| 4 | `engineering_model_delete` | 模型删除 | HIGH | ASYNC |
| 5 | `engineering_model_build` | 工程语义建模 | HIGH | ASYNC |
| 6 | `engineering_view` | 可视化 | LOW | SYNC |
| 7 | `engineering_result` | 计算结果 | LOW | SYNC |
| 8 | `engineering_design` | 设计验算 | HIGH | ASYNC |
| 9 | `engineering_analysis` | 分析计算 | HIGH | ASYNC |

风险等级：

```text
LOW
MEDIUM
HIGH
CRITICAL
```

执行模式：

```text
SYNC
ASYNC
STREAM
```

---

# 4. 通用 Tool Request Contract

所有 Tool 使用统一请求外壳。

```json
{
  "operation": "MODEL.NODE.QUERY",
  "parameters": {},
  "context": {},
  "idempotency_key": null,
  "confirmation_token": null,
  "dry_run": false
}
```

## 4.1 字段

| 字段 | 类型 | 必须 | 说明 |
|---|---|---:|---|
| `operation` | string | 是 | Operation Code |
| `parameters` | object | 否 | Operation 参数 |
| `context` | object | 否 | 资源选择上下文 |
| `idempotency_key` | string | 条件 | 写操作/异步任务推荐或必须 |
| `confirmation_token` | string | 条件 | 高风险操作 |
| `dry_run` | boolean | 否 | 是否只验证/生成计划 |

## 4.2 context

客户端允许提供：

```json
{
  "software_instance_id": "uuid",
  "project_id": "uuid",
  "model_id": "uuid",
  "document_id": "uuid"
}
```

客户端不得提供：

```text
user_id
tenant_id
roles
permissions
effective_permissions
```

这些由服务器 Authentication / Session / IdentityContext 生成。

---

# 5. 通用 JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "structai://schema/mcp/tool-request/v1",
  "title": "StructAI MCP Tool Request",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "operation": {
      "type": "string",
      "minLength": 1
    },
    "parameters": {
      "type": "object",
      "default": {}
    },
    "context": {
      "$ref": "structai://schema/mcp/execution-context-input/v1"
    },
    "idempotency_key": {
      "type": ["string", "null"],
      "minLength": 1,
      "maxLength": 256
    },
    "confirmation_token": {
      "type": ["string", "null"],
      "minLength": 1,
      "maxLength": 512
    },
    "dry_run": {
      "type": "boolean",
      "default": false
    }
  },
  "required": ["operation"]
}
```

---

# 6. Context Input Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "structai://schema/mcp/execution-context-input/v1",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "software_instance_id": {
      "type": ["string", "null"],
      "format": "uuid"
    },
    "project_id": {
      "type": ["string", "null"],
      "format": "uuid"
    },
    "model_id": {
      "type": ["string", "null"],
      "format": "uuid"
    },
    "document_id": {
      "type": ["string", "null"],
      "format": "uuid"
    }
  }
}
```

---

# 7. 通用 Response Contract

## 7.1 Sync Success

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

## 7.2 Async Accepted

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
  "errors": [],
  "metadata": {}
}
```

## 7.3 Error

```json
{
  "success": false,
  "request_id": "req_003",
  "trace_id": "trace_003",
  "tool": "engineering_analysis",
  "operation": "ANALYSIS.STATIC",
  "execution": {
    "mode": "ASYNC",
    "status": "FAILED"
  },
  "data": null,
  "warnings": [],
  "errors": [
    {
      "code": "STRUCTAI-3000",
      "type": "CAPABILITY_ERROR",
      "message": "Current software does not support this operation",
      "details": {},
      "retryable": false
    }
  ],
  "metadata": {}
}
```

---

# 8. Error Contract

所有 9 Tool 使用统一错误代码。

```text
STRUCTAI-1000  Protocol Error
STRUCTAI-1100  Schema Validation Error
STRUCTAI-1200  Engineering Validation Error
STRUCTAI-1300  Concurrency Conflict

STRUCTAI-2000  Software Connection Error
STRUCTAI-2100  Software Authentication Error
STRUCTAI-2200  Software API Error
STRUCTAI-2300  Software Timeout

STRUCTAI-3000  Capability Not Supported

STRUCTAI-4000  Permission Denied
STRUCTAI-4100  Confirmation Required
STRUCTAI-4200  Tenant Access Denied

STRUCTAI-5000  Task Error
STRUCTAI-5100  Task Timeout
STRUCTAI-5200  Task Cancelled
STRUCTAI-5300  Task Recovery Error

STRUCTAI-6000  Adapter Error
STRUCTAI-6100  Resource Locked
STRUCTAI-6200  Artifact Error

STRUCTAI-7000  Internal Error
```

Native error 默认不暴露。

诊断模式可增加：

```json
{
  "cause": {
    "provider": "MIDAS",
    "native_code": "xxx",
    "native_message": "xxx"
  }
}
```

---

# 9. 通用权限

基础 Permission：

```text
DOCUMENT_READ
DOCUMENT_WRITE

MODEL_READ
MODEL_WRITE
MODEL_DELETE

ANALYSIS_EXECUTE

DESIGN_EXECUTE
DESIGN_MODIFY

RESULT_READ

SYSTEM_ADMIN
TOOL_TEST
API_TEST
```

Tool 权限不是唯一授权依据。

最终必须经过：

```text
Effective Permission
+
Resource Access
+
Operation Permission
+
Capability
```

---

# 10. 通用执行规则

每个 Tool 必须进入统一 Execution Pipeline：

```text
MCP Request
 ↓
Authenticate
 ↓
Server IdentityContext
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
Quota / Rate Limit
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

Tool Handler 不允许绕过此流程。

---

# 11. Tool 1 — engineering_doc

## 11.1 定位

工程文档生命周期管理。

Operations：

```text
NEW
OPEN
SAVE
SAVE_AS
CLOSE
INFO
```

---

## 11.2 Tool Definition

```json
{
  "name": "engineering_doc",
  "version": "2.0",
  "category": "DOCUMENT",
  "description": "工程文档生命周期管理",
  "risk_level": "MEDIUM",
  "execution_mode": "SYNC",
  "operations": [
    "NEW",
    "OPEN",
    "SAVE",
    "SAVE_AS",
    "CLOSE",
    "INFO"
  ]
}
```

---

## 11.3 Permission

```text
NEW       → DOCUMENT_WRITE
OPEN      → DOCUMENT_READ
SAVE      → DOCUMENT_WRITE
SAVE_AS   → DOCUMENT_WRITE
CLOSE     → DOCUMENT_WRITE
INFO      → DOCUMENT_READ
```

---

## 11.4 Capability

Document Capability 可以由 Adapter 映射为：

```text
DOCUMENT.NEW
DOCUMENT.OPEN
DOCUMENT.SAVE
DOCUMENT.SAVE_AS
DOCUMENT.CLOSE
DOCUMENT.INFO
```

---

## 11.5 Operation Parameters

### NEW

```json
{
  "name": "factory_model",
  "format": "native",
  "template": null
}
```

Schema：

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "name": {
      "type": "string",
      "minLength": 1
    },
    "format": {
      "type": "string",
      "default": "native"
    },
    "template": {
      "type": ["string", "null"]
    }
  },
  "required": ["name"]
}
```

### OPEN

```json
{
  "artifact_id": "uuid"
}
```

或：

```json
{
  "path": "local reference"
}
```

实际文件访问必须经过 Artifact / Document Service。

### SAVE

```json
{}
```

### SAVE_AS

```json
{
  "name": "factory_model_v2",
  "format": "native"
}
```

### CLOSE

```json
{
  "save": true
}
```

### INFO

```json
{}
```

---

## 11.6 Preconditions

```text
OPEN:
- artifact exists
- compatible software instance
- adapter connected

SAVE:
- document opened
- software connected

CLOSE:
- document exists
```

---

## 11.7 Postconditions

```text
NEW:
- document created

OPEN:
- document active

SAVE:
- latest document persisted

SAVE_AS:
- new artifact/document created

CLOSE:
- document inactive
```

---

## 11.8 Response

```json
{
  "document_id": "doc_001",
  "status": "OPEN",
  "name": "factory_model",
  "artifact": {
    "artifact_id": "artifact_001"
  },
  "version": 1
}
```

---

# 12. Tool 2 — engineering_model_query

## 12.1 定位

只读查询工程模型。

Operations：

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
Risk: LOW
Execution: SYNC
Permission: MODEL_READ
```

---

## 12.2 Tool Definition

```json
{
  "name": "engineering_model_query",
  "version": "2.0",
  "category": "MODEL_QUERY",
  "risk_level": "LOW",
  "execution_mode": "SYNC"
}
```

---

## 12.3 通用 Query Parameters

```json
{
  "ids": [],
  "where": {},
  "fields": [],
  "limit": 100,
  "cursor": null
}
```

Schema：

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "ids": {
      "type": "array",
      "items": {
        "type": ["string", "integer"]
      }
    },
    "where": {
      "type": "object"
    },
    "fields": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 10000,
      "default": 100
    },
    "cursor": {
      "type": ["string", "null"]
    }
  }
}
```

---

## 12.4 MODEL.QUERY

返回模型摘要：

```json
{
  "model_id": "model_001",
  "name": "Steel Frame",
  "counts": {
    "nodes": 120,
    "elements": 145,
    "materials": 4,
    "sections": 12,
    "loads": 8
  }
}
```

---

## 12.5 MODEL.NODE.QUERY

Canonical Node：

```json
{
  "id": 1,
  "x": 0,
  "y": 0,
  "z": 0
}
```

---

## 12.6 MODEL.ELEMENT.QUERY

Canonical Element：

```json
{
  "id": 100,
  "type": "BEAM",
  "node_i": 1,
  "node_j": 2,
  "material_id": "mat_001",
  "section_id": "sec_001"
}
```

---

## 12.7 MODEL.MATERIAL.QUERY

```json
{
  "id": "mat_001",
  "name": "Q355B",
  "type": "STEEL",
  "properties": {
    "fy": 355000000,
    "fu": 510000000
  }
}
```

---

## 12.8 MODEL.SECTION.QUERY

```json
{
  "id": "sec_001",
  "type": "H",
  "height": 400,
  "width": 400,
  "web_thickness": 13,
  "flange_thickness": 21
}
```

---

## 12.9 MODEL.BOUNDARY.QUERY

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

---

## 12.10 MODEL.LOAD.QUERY

```json
{
  "id": "load_001",
  "case": "N",
  "target_type": "NODE",
  "target_id": 2,
  "values": {
    "fx": 0,
    "fy": 0,
    "fz": -500000
  }
}
```

---

## 12.11 MODEL.GROUP.QUERY

```json
{
  "id": "group_001",
  "name": "Columns",
  "entity_type": "ELEMENT",
  "members": [1, 2, 3]
}
```

---

## 12.12 Pagination

所有大查询：

```json
{
  "data": [],
  "pagination": {
    "has_more": true,
    "next_cursor": "opaque-cursor"
  }
}
```

---

## 12.13 Preconditions

```text
- project accessible
- model exists
- software instance connected when native query required
- capability supported
```

---

# 13. Tool 3 — engineering_model_assign

## 13.1 定位

创建/修改工程模型。

Operations：

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

默认：

```text
Risk: MEDIUM
Execution: SYNC / ASYNC
Permission: MODEL_WRITE
```

---

# 14. MODEL.NODE.CREATE

输入：

```json
{
  "id": 1,
  "x": 0,
  "y": 0,
  "z": 0
}
```

Schema：

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "id": {
      "type": ["integer", "null"],
      "minimum": 1
    },
    "x": {"type": "number"},
    "y": {"type": "number"},
    "z": {"type": "number"}
  },
  "required": ["x", "y", "z"]
}
```

服务端可以自动分配 ID。

---

# 15. MODEL.NODE.UPDATE

```json
{
  "id": 1,
  "x": 0,
  "y": 0,
  "z": 6,
  "expected_version": 3
}
```

必须支持 optimistic concurrency。

冲突：

```text
STRUCTAI-1300
```

---

# 16. MODEL.ELEMENT.CREATE

```json
{
  "id": null,
  "type": "BEAM",
  "node_i": 1,
  "node_j": 2,
  "material_id": "mat_001",
  "section_id": "sec_001"
}
```

---

# 17. MODEL.ELEMENT.UPDATE

```json
{
  "id": 100,
  "section_id": "sec_002",
  "expected_version": 4
}
```

---

# 18. MODEL.MATERIAL.ASSIGN

```json
{
  "target_type": "ELEMENT",
  "target_ids": [100, 101],
  "material_id": "mat_001"
}
```

---

# 19. MODEL.SECTION.ASSIGN

```json
{
  "target_type": "ELEMENT",
  "target_ids": [100],
  "section_id": "sec_001"
}
```

---

# 20. MODEL.BOUNDARY.ASSIGN

```json
{
  "node_ids": [1],
  "boundary": {
    "ux": true,
    "uy": true,
    "uz": true,
    "rx": true,
    "ry": true,
    "rz": true
  }
}
```

---

# 21. MODEL.LOAD.ASSIGN

```json
{
  "case": "N",
  "target_type": "NODE",
  "target_ids": [2],
  "load": {
    "fx": 0,
    "fy": 0,
    "fz": -500000,
    "mx": 0,
    "my": 0,
    "mz": 0
  }
}
```

---

# 22. Batch Assign

支持：

```json
{
  "items": [
    {
      "operation": "MODEL.NODE.CREATE",
      "parameters": {
        "x": 0,
        "y": 0,
        "z": 0
      }
    },
    {
      "operation": "MODEL.NODE.CREATE",
      "parameters": {
        "x": 0,
        "y": 0,
        "z": 6
      }
    }
  ],
  "atomic": true
}
```

Atomic 优先：

```text
Native Transaction
Snapshot / Restore
Compensating Action
```

最终无法原子化时必须报告实际结果。

---

# 23. Tool 4 — engineering_model_delete

## 23.1 定位

高风险模型删除。

Operations：

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
Risk: HIGH
Execution: ASYNC
```

---

# 24. Delete 权限与确认

所有 DELETE 至少：

```text
MODEL_DELETE
```

高风险删除必须：

```text
confirmation_token
```

缺失：

```text
STRUCTAI-4100
```

---

# 25. Delete 通用参数

```json
{
  "ids": [10, 11],
  "expected_version": null,
  "cascade": false
}
```

Schema：

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "ids": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": ["integer", "string"]
      }
    },
    "expected_version": {
      "type": ["integer", "null"],
      "minimum": 0
    },
    "cascade": {
      "type": "boolean",
      "default": false
    }
  },
  "required": ["ids"]
}
```

---

# 26. Delete Preconditions

例如删除 Node：

```text
- model exists
- target nodes exist
- user has MODEL_DELETE
- required capability exists
- confirmation valid
- lock acquired
```

如果 Node 仍被 Element 引用：

```text
engineering validation
```

必须明确：

```text
reject
```

或者：

```text
cascade=true
```

但 Cascade 必须由 Operation Schema 明确允许。

---

# 27. Delete Audit

所有 DELETE：

```text
Audit
Trace
Task
```

必须生成。

---

# 28. Tool 5 — engineering_model_build

## 28.1 定位

工程语义建模。

它与 `engineering_model_assign` 的区别：

```text
model_assign
    = low-level model mutation

model_build
    = high-level engineering semantic construction
```

---

# 29. Operations

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
Risk: HIGH
Execution: ASYNC
Permission: MODEL_WRITE
```

---

# 30. BUILD.NODE_GRID

```json
{
  "origin": {
    "x": 0,
    "y": 0,
    "z": 0
  },
  "nx": 5,
  "ny": 4,
  "dx": 6,
  "dy": 6
}
```

结果：

```json
{
  "created_nodes": 20,
  "node_ids": [1, 2, 3]
}
```

---

# 31. BUILD.BEAM

```json
{
  "start": {
    "x": 0,
    "y": 0,
    "z": 6
  },
  "end": {
    "x": 6,
    "y": 0,
    "z": 6
  },
  "material": "Q355B",
  "section": "H400x400x13x21"
}
```

---

# 32. BUILD.COLUMN

完整示例：

```json
{
  "height": 6,
  "material": "Q355B",
  "section": {
    "type": "H",
    "height": 400,
    "width": 400,
    "web_thickness": 13,
    "flange_thickness": 21
  },
  "boundary": {
    "base": "FIXED"
  }
}
```

Canonical 结果：

```json
{
  "nodes": [
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
  ],
  "elements": [
    {
      "id": 100,
      "type": "COLUMN",
      "node_i": 1,
      "node_j": 2
    }
  ],
  "assignments": {
    "material": "Q355B",
    "section": "H400x400x13x21"
  }
}
```

---

# 33. BUILD.FRAME

```json
{
  "levels": 3,
  "bays": 4,
  "bay_width": 6,
  "story_height": 4,
  "material": "Q355B",
  "column_section": "H400x400x13x21",
  "beam_section": "H300x200x8x12"
}
```

---

# 34. BUILD.TRUSS

```json
{
  "span": 30,
  "height": 4,
  "panels": 10,
  "material": "Q355B",
  "chord_section": "H200x200x8x12",
  "web_section": "H150x150x6x9"
}
```

---

# 35. BUILD.SLAB

```json
{
  "boundary": {
    "x_min": 0,
    "x_max": 12,
    "y_min": 0,
    "y_max": 8,
    "z": 6
  },
  "thickness": 0.15,
  "material": "C40"
}
```

---

# 36. BUILD.WALL

```json
{
  "start": [0, 0, 0],
  "end": [0, 8, 0],
  "height": 6,
  "thickness": 0.2,
  "material": "C40"
}
```

---

# 37. BUILD.FOUNDATION

```json
{
  "type": "PAD",
  "center": [0, 0, 0],
  "width": 2.5,
  "length": 2.5,
  "depth": 0.6,
  "material": "C35"
}
```

---

# 38. BUILD.STEEL_FRAME

```json
{
  "width": 24,
  "length": 60,
  "height": 8,
  "bay_spacing": 6,
  "material": "Q355B",
  "column_section": "H500x300x12x20",
  "beam_section": "H450x250x10x16"
}
```

这是高层语义 Operation，可以展开为多个底层操作。

---

# 39. MODEL.COPY

```json
{
  "source_ids": [100, 101],
  "translation": {
    "x": 6,
    "y": 0,
    "z": 0
  }
}
```

---

# 40. MODEL.MOVE

```json
{
  "ids": [100, 101],
  "translation": {
    "x": 0,
    "y": 6,
    "z": 0
  }
}
```

---

# 41. MODEL.MIRROR

```json
{
  "ids": [100, 101],
  "plane": {
    "point": [0, 0, 0],
    "normal": [1, 0, 0]
  }
}
```

---

# 42. MODEL.PATTERN

```json
{
  "ids": [100],
  "count": 5,
  "translation": {
    "x": 6,
    "y": 0,
    "z": 0
  }
}
```

---

# 43. MODEL.GENERATE_GRID

```json
{
  "x": [0, 6, 12, 18],
  "y": [0, 6, 12],
  "z": [0, 4, 8]
}
```

---

# 44. Build Dry Run

所有 Build Operation 原则上必须支持 Dry Run。

```json
{
  "operation": "BUILD.COLUMN",
  "dry_run": true,
  "parameters": {
    "height": 6,
    "material": "Q355B",
    "section": {
      "type": "H",
      "height": 400,
      "width": 400,
      "web_thickness": 13,
      "flange_thickness": 21
    }
  }
}
```

返回：

```json
{
  "dry_run": true,
  "planned_changes": {
    "nodes": 2,
    "elements": 1,
    "materials": 1,
    "sections": 1,
    "boundaries": 1
  },
  "warnings": []
}
```

不得修改模型。

---

# 45. Build Preconditions

```text
- project active
- software instance selected
- software connected
- required capabilities available
- geometry valid
- material valid
- section valid
- model lock available
```

---

# 46. Build Postconditions

必须检查：

```text
- expected nodes exist
- expected elements exist
- material assignment exists
- section assignment exists
- boundary assignment exists
```

---

# 47. Tool 6 — engineering_view

## 47.1 定位

工程模型和结果的可视化控制。

Operations：

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
Risk: LOW
Execution: SYNC
Permission: MODEL_READ / RESULT_READ
```

---

# 48. VIEW.MODEL

```json
{
  "entity_type": "ALL",
  "ids": [],
  "camera": {
    "projection": "PERSPECTIVE"
  }
}
```

返回：

```json
{
  "view_id": "view_001",
  "artifact_id": "artifact_001"
}
```

---

# 49. VIEW.DEFORMED_MODEL

```json
{
  "load_case": "COMB1",
  "scale": 20
}
```

---

# 50. VIEW.REACTION

```json
{
  "load_case": "DEAD",
  "node_ids": [1, 2, 3]
}
```

---

# 51. VIEW.DISPLACEMENT

```json
{
  "load_case": "COMB1",
  "component": "UZ",
  "scale": 20
}
```

---

# 52. VIEW.STRESS

```json
{
  "load_case": "COMB1",
  "component": "VM"
}
```

---

# 53. VIEW.FORCE

```json
{
  "load_case": "COMB1",
  "component": "MZ"
}
```

---

# 54. VIEW.MODE_SHAPE

```json
{
  "mode": 1,
  "scale": 20
}
```

---

# 55. View Output

视图结果可以是：

```text
artifact
image
scene descriptor
native view state
```

MCP Response 不应把超大二进制内容直接塞进 JSON。

优先返回：

```json
{
  "view_id": "view_001",
  "artifact_id": "artifact_001",
  "mime_type": "image/png"
}
```

---

# 56. Tool 7 — engineering_result

## 56.1 定位

读取已经完成的工程分析结果。

Operations：

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
Risk: LOW
Execution: SYNC
Permission: RESULT_READ
```

---

# 57. RESULT.NODE.DISPLACEMENT

```json
{
  "node_ids": [2],
  "load_case": "COMB1"
}
```

返回：

```json
{
  "data": [
    {
      "node_id": 2,
      "ux": 0.001,
      "uy": 0.002,
      "uz": -0.015
    }
  ]
}
```

---

# 58. RESULT.NODE.REACTION

```json
{
  "node_ids": [1],
  "load_case": "DEAD"
}
```

返回：

```json
{
  "data": [
    {
      "node_id": 1,
      "fx": 0,
      "fy": 0,
      "fz": 500000,
      "mx": 0,
      "my": 0,
      "mz": 0
    }
  ]
}
```

---

# 59. RESULT.ELEMENT.FORCE

```json
{
  "element_ids": [100],
  "load_case": "COMB1"
}
```

返回：

```json
{
  "data": [
    {
      "element_id": 100,
      "n": -500000,
      "vy": 0,
      "vz": 0,
      "mx": 0,
      "my": 0,
      "mz": 0
    }
  ]
}
```

---

# 60. RESULT.ELEMENT.STRESS

```json
{
  "element_ids": [100],
  "load_case": "COMB1"
}
```

---

# 61. RESULT.MODE.SHAPE

```json
{
  "mode": 1
}
```

返回：

```json
{
  "mode": 1,
  "frequency": 2.31,
  "nodes": []
}
```

---

# 62. RESULT.ANALYSIS.SUMMARY

```json
{
  "analysis_task_id": "task_001"
}
```

返回：

```json
{
  "status": "COMPLETED",
  "analysis_type": "STATIC",
  "load_cases": ["DEAD", "LIVE"],
  "warnings": [],
  "result_sets": 12
}
```

---

# 63. Result Preconditions

```text
- analysis completed
- requested result set exists
- result capability supported
```

如果分析尚未完成：

```text
STRUCTAI-5000
```

或返回明确：

```text
RESULT_NOT_READY
```

但必须映射到统一 StructAI Error Contract。

---

# 64. Result Pagination

元素/节点结果大量返回时：

```json
{
  "data": [],
  "pagination": {
    "has_more": true,
    "next_cursor": "..."
  }
}
```

---

# 65. Tool 8 — engineering_design

## 65.1 定位

工程设计、规范验算、优化。

Operations：

```text
DESIGN.STEEL
DESIGN.CONCRETE
DESIGN.SRC
DESIGN.FOUNDATION
DESIGN.CODE_CHECK
DESIGN.OPTIMIZE
```
>
> ⭐ **2026-10-05 契约修订**：新增 `DESIGN.SRC`（本 Tool 5 → **6**），
> 补 `DESIGN.SRC.AIK-SRC2K.*` 共 27 个端点的归属（原先无对应 Operation）。
> Operation 总数 68 → **69**。详见 `docs/07` §5.1 / §6.8 / §16 R11。

默认：

```text
Risk: HIGH
Execution: ASYNC
Permission:
DESIGN_EXECUTE
```

修改设计参数/优化结果可能需要：

```text
DESIGN_MODIFY
MODEL_WRITE
```

---

# 66. DESIGN.STEEL

示例：

```json
{
  "element_ids": [100],
  "code": "GB50017",
  "combination": "DESIGN_COMB1",
  "options": {
    "check_stability": true,
    "check_strength": true
  }
}
```

返回：

```json
{
  "element_id": 100,
  "utilization_ratio": 0.82,
  "status": "PASS",
  "checks": {
    "strength": 0.71,
    "stability": 0.82
  }
}
```

注意：

> 规范计算公式不写死在 MCP Tool；由 Design Adapter / Design Engine / Registry 实现。

---

# 67. DESIGN.CONCRETE

```json
{
  "element_ids": [200],
  "code": "GB50010",
  "combination": "DESIGN_COMB1",
  "options": {
    "crack": true,
    "strength": true,
    "serviceability": true
  }
}
```

---

# 68. DESIGN.FOUNDATION

```json
{
  "foundation_ids": ["F001"],
  "code": "GB50007",
  "options": {
    "bearing_capacity": true,
    "settlement": true,
    "sliding": true,
    "overturning": true
  }
}
```

---

# 69. DESIGN.CODE_CHECK

通用规范检查：

```json
{
  "entity_type": "ELEMENT",
  "entity_ids": [100, 101],
  "code": "GB50017",
  "checks": [
    "STRENGTH",
    "STABILITY",
    "SERVICEABILITY"
  ]
}
```

---

# 70. DESIGN.OPTIMIZE

优化是高风险操作。

```json
{
  "entity_ids": [100, 101],
  "objective": "MIN_STEEL_WEIGHT",
  "constraints": {
    "max_utilization": 1.0,
    "max_displacement": 0.05
  },
  "variables": [
    {
      "name": "section",
      "allowed": [
        "H400x400x13x21",
        "H450x450x14x22",
        "H500x500x16x25"
      ]
    }
  ],
  "apply": false
}
```

默认：

```text
apply = false
```

先返回优化建议。

真正修改模型必须：

```text
DESIGN_MODIFY
+
MODEL_WRITE
+
confirmation
```

---

# 71. Design Dry Run

Design 本身不一定修改模型。

对于：

```text
DESIGN.OPTIMIZE
```

必须支持：

```text
apply=false
```

如果 `apply=true`：

```text
high-risk confirmation
audit
lock
```

---

# 72. Design Output

统一：

```json
{
  "status": "PASS",
  "utilization_ratio": 0.82,
  "governing_check": "STABILITY",
  "warnings": [],
  "recommendations": []
}
```

不得要求 AI Client 理解 MIDAS/ETABS 的原始设计结果格式。

---

# 73. Tool 9 — engineering_analysis

## 73.1 定位

执行工程分析计算。

Operations：

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
Risk: HIGH
Execution: ASYNC
Permission: ANALYSIS_EXECUTE
```

---

# 74. ANALYSIS.STATIC

```json
{
  "load_cases": [
    "DEAD",
    "LIVE",
    "WIND"
  ],
  "combinations": [
    "COMB1"
  ]
}
```

返回：

```json
{
  "task_id": "task_001",
  "status": "QUEUED"
}
```

---

# 75. ANALYSIS.MODAL

```json
{
  "modes": 12,
  "solver_options": {}
}
```

---

# 76. ANALYSIS.SEISMIC

```json
{
  "direction": ["X", "Y"],
  "cases": ["EQX", "EQY"],
  "damping_ratio": 0.05
}
```

---

# 77. ANALYSIS.SPECTRUM

```json
{
  "spectrum_id": "SPEC_X",
  "direction": "X",
  "damping_ratio": 0.05
}
```

---

# 78. ANALYSIS.BUCKLING

```json
{
  "modes": 10,
  "load_case": "COMB1"
}
```

---

# 79. ANALYSIS.TIME_HISTORY

```json
{
  "case": "TH_X",
  "duration": 20,
  "time_step": 0.01,
  "record": "artifact_001"
}
```

---

# 80. ANALYSIS.NONLINEAR

```json
{
  "load_case": "NL1",
  "solver": {
    "max_steps": 100,
    "tolerance": 1e-6
  }
}
```

---

# 81. Analysis Preconditions

至少：

```text
- project active
- model exists
- software connected
- model valid
- required loads exist
- analysis capability supported
- no incompatible running task
- software instance lock acquired
```

具体 Operation 可增加：

```text
Preconditions
```

---

# 82. Analysis Postconditions

```text
- analysis completed
- result set available
- result metadata persisted
- task completed
```

如果软件只完成部分结果：

```text
PARTIAL
```

不得错误标记：

```text
COMPLETED
```

---

# 83. Analysis Task Response

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

---

# 84. MCP Progress

Analysis Task：

```text
0
 ↓
VALIDATING
 ↓
QUEUED
 ↓
RUNNING
 ↓
PROCESSING
 ↓
100
 ↓
COMPLETED
```

MCP progress 来源必须是 Task Engine。

不能由 Tool Handler 自己制造进度。

---

# 85. MCP Cancellation

```text
MCP cancel
 ↓
TaskEngine.cancel()
 ↓
CANCEL_REQUESTED
 ↓
Adapter.cancel()
 ↓
CANCELLED
```

如果原生软件不支持真实取消：

```text
CANCEL_REQUESTED
```

可以保持到软件真实结束。

不得伪造：

```text
CANCELLED
```

---

# 86. Tool Operation Matrix

| Operation | Tool | Risk | Mode | Permission | Capability |
|---|---|---|---|---|---|
| NEW | doc | MEDIUM | SYNC | DOCUMENT_WRITE | DOCUMENT.NEW |
| OPEN | doc | MEDIUM | SYNC | DOCUMENT_READ | DOCUMENT.OPEN |
| SAVE | doc | MEDIUM | SYNC | DOCUMENT_WRITE | DOCUMENT.SAVE |
| SAVE_AS | doc | MEDIUM | SYNC | DOCUMENT_WRITE | DOCUMENT.SAVE_AS |
| CLOSE | doc | MEDIUM | SYNC | DOCUMENT_WRITE | DOCUMENT.CLOSE |
| INFO | doc | LOW | SYNC | DOCUMENT_READ | DOCUMENT.INFO |
| MODEL.QUERY | query | LOW | SYNC | MODEL_READ | MODEL.READ |
| MODEL.NODE.QUERY | query | LOW | SYNC | MODEL_READ | MODEL.NODE.READ |
| MODEL.ELEMENT.QUERY | query | LOW | SYNC | MODEL_READ | MODEL.ELEMENT.READ |
| MODEL.MATERIAL.QUERY | query | LOW | SYNC | MODEL_READ | MODEL.MATERIAL.READ |
| MODEL.SECTION.QUERY | query | LOW | SYNC | MODEL_READ | MODEL.SECTION.READ |
| MODEL.BOUNDARY.QUERY | query | LOW | SYNC | MODEL_READ | MODEL.BOUNDARY.READ |
| MODEL.LOAD.QUERY | query | LOW | SYNC | MODEL_READ | MODEL.LOAD.READ |
| MODEL.GROUP.QUERY | query | LOW | SYNC | MODEL_READ | MODEL.GROUP.READ |
| MODEL.NODE.CREATE | assign | MEDIUM | SYNC/ASYNC | MODEL_WRITE | MODEL.NODE.WRITE |
| MODEL.NODE.UPDATE | assign | MEDIUM | SYNC/ASYNC | MODEL_WRITE | MODEL.NODE.WRITE |
| MODEL.ELEMENT.CREATE | assign | MEDIUM | SYNC/ASYNC | MODEL_WRITE | MODEL.ELEMENT.WRITE |
| MODEL.ELEMENT.UPDATE | assign | MEDIUM | SYNC/ASYNC | MODEL_WRITE | MODEL.ELEMENT.WRITE |
| MODEL.MATERIAL.ASSIGN | assign | MEDIUM | SYNC/ASYNC | MODEL_WRITE | MODEL.MATERIAL.WRITE |
| MODEL.SECTION.ASSIGN | assign | MEDIUM | SYNC/ASYNC | MODEL_WRITE | MODEL.SECTION.WRITE |
| MODEL.BOUNDARY.ASSIGN | assign | MEDIUM | SYNC/ASYNC | MODEL_WRITE | MODEL.BOUNDARY.WRITE |
| MODEL.LOAD.ASSIGN | assign | MEDIUM | SYNC/ASYNC | MODEL_WRITE | MODEL.LOAD.WRITE |
| MODEL.NODE.DELETE | delete | HIGH | ASYNC | MODEL_DELETE | MODEL.NODE.DELETE |
| MODEL.ELEMENT.DELETE | delete | HIGH | ASYNC | MODEL_DELETE | MODEL.ELEMENT.DELETE |
| MODEL.LOAD.DELETE | delete | HIGH | ASYNC | MODEL_DELETE | MODEL.LOAD.DELETE |
| MODEL.BOUNDARY.DELETE | delete | HIGH | ASYNC | MODEL_DELETE | MODEL.BOUNDARY.DELETE |
| MODEL.GROUP.DELETE | delete | HIGH | ASYNC | MODEL_DELETE | MODEL.GROUP.DELETE |
| MODEL.MATERIAL.DELETE | delete | HIGH | ASYNC | MODEL_DELETE | MODEL.MATERIAL.DELETE |
| MODEL.SECTION.DELETE | delete | HIGH | ASYNC | MODEL_DELETE | MODEL.SECTION.DELETE |
| BUILD.* | build | HIGH | ASYNC | MODEL_WRITE | corresponding write capabilities |
| VIEW.* | view | LOW | SYNC | MODEL_READ/RESULT_READ | VIEW.* |
| RESULT.* | result | LOW | SYNC | RESULT_READ | RESULT.* |
| DESIGN.STEEL | design | HIGH | ASYNC | DESIGN_EXECUTE | DESIGN.STEEL |
| DESIGN.CONCRETE | design | HIGH | ASYNC | DESIGN_EXECUTE | DESIGN.CONCRETE |
| DESIGN.SRC | design | HIGH | ASYNC | DESIGN_EXECUTE | DESIGN.SRC |
| DESIGN.FOUNDATION | design | HIGH | ASYNC | DESIGN_EXECUTE | DESIGN.FOUNDATION |
| DESIGN.CODE_CHECK | design | HIGH | ASYNC | DESIGN_EXECUTE | DESIGN.CODE_CHECK |
| DESIGN.OPTIMIZE | design | HIGH | ASYNC | DESIGN_EXECUTE | DESIGN.OPTIMIZATION |
| ANALYSIS.STATIC | analysis | HIGH | ASYNC | ANALYSIS_EXECUTE | ANALYSIS.STATIC |
| ANALYSIS.MODAL | analysis | HIGH | ASYNC | ANALYSIS_EXECUTE | ANALYSIS.MODAL |
| ANALYSIS.SEISMIC | analysis | HIGH | ASYNC | ANALYSIS_EXECUTE | ANALYSIS.SEISMIC |
| ANALYSIS.SPECTRUM | analysis | HIGH | ASYNC | ANALYSIS_EXECUTE | ANALYSIS.SPECTRUM |
| ANALYSIS.BUCKLING | analysis | HIGH | ASYNC | ANALYSIS_EXECUTE | ANALYSIS.BUCKLING |
| ANALYSIS.TIME_HISTORY | analysis | HIGH | ASYNC | ANALYSIS_EXECUTE | ANALYSIS.TIME_HISTORY |
| ANALYSIS.NONLINEAR | analysis | HIGH | ASYNC | ANALYSIS_EXECUTE | ANALYSIS.NONLINEAR |

---

# 87. Capability Requirements for Build

`BUILD.COLUMN`：

```text
MODEL.NODE.WRITE
MODEL.ELEMENT.WRITE
MODEL.MATERIAL.WRITE
MODEL.SECTION.WRITE
MODEL.BOUNDARY.WRITE
```

`BUILD.FRAME`：

```text
MODEL.NODE.WRITE
MODEL.ELEMENT.WRITE
MODEL.MATERIAL.WRITE
MODEL.SECTION.WRITE
```

`BUILD.STEEL_FRAME`：

```text
MODEL.NODE.WRITE
MODEL.ELEMENT.WRITE
MODEL.MATERIAL.WRITE
MODEL.SECTION.WRITE
MODEL.BOUNDARY.WRITE
```

---

# 88. Lock Requirements

## Query

通常：

```text
READ
```

## Assign

```text
WRITE
```

## Delete

```text
EXCLUSIVE
```

## Build

```text
WRITE
```

复杂 Build 如果涉及全模型重构：

```text
EXCLUSIVE
```

## Analysis

默认：

```text
Software Instance = WRITE / EXCLUSIVE
Model = READ
```

具体 Adapter 可以提升锁级别。

## Design

读取：

```text
Model = READ
```

如果 `apply=true`：

```text
Model = WRITE
```

---

# 89. Idempotency Requirements

必须支持/建议：

| Tool | Idempotency |
|---|---|
| doc NEW | 必须 |
| doc OPEN | 可选 |
| doc SAVE | 推荐 |
| model query | 可选 |
| model assign | 必须 |
| model delete | 必须 |
| model build | 必须 |
| view | 可选 |
| result | 可选 |
| design | 必须 |
| analysis | 必须 |

唯一键：

```text
tenant_id + idempotency_key
```

重复请求必须避免重复创建模型、重复分析或重复删除。

---

# 90. Confirmation Requirements

默认需要 Confirmation：

```text
MODEL.*.DELETE
DESIGN.OPTIMIZE + apply=true
高风险模型重构
```

Confirmation Token 必须：

```text
server generated
short-lived
bound to user
bound to tenant
bound to operation
bound to resource
```

不能使用固定：

```text
CONFIRM
YES
true
```

作为安全确认。

---

# 91. Dry Run Matrix

| Tool | Dry Run |
|---|---|
| engineering_doc | 受 Operation 支持 |
| model_query | 无意义 |
| model_assign | 推荐 |
| model_delete | 推荐 |
| model_build | 必须 |
| engineering_view | 无意义 |
| engineering_result | 无意义 |
| engineering_design | 推荐 |
| engineering_analysis | 推荐 |

Dry Run 必须：

```text
validate
authorize
check capability
check preconditions
produce plan
```

但不得：

```text
modify model
```

---

# 92. Batch Matrix

| Tool | Batch |
|---|---|
| model_query | 必须支持 |
| model_assign | 必须支持 |
| model_delete | 支持 |
| model_build | 支持高层批量 |
| result | 必须支持 |
| design | 支持 |
| analysis | 支持多 Case |
| view | 可选 |
| doc | 不要求 |

---

# 93. Transaction Matrix

| Operation | Transaction | Rollback |
|---|---|---|
| NODE.CREATE | Yes | Yes |
| ELEMENT.CREATE | Yes | Yes |
| ASSIGN | Yes | Yes |
| DELETE | Yes | Yes |
| BUILD.COLUMN | Yes | Yes |
| BUILD.FRAME | Yes | Yes |
| BUILD.STEEL_FRAME | Yes | preferred |
| ANALYSIS | native task | software dependent |
| DESIGN | task | software dependent |
| VIEW | No | No |
| QUERY | No | No |

Rollback 优先级：

```text
Native Transaction
 ↓
Snapshot / Restore
 ↓
Compensating Actions
 ↓
Best Effort
```

不能声称不支持回滚的 Adapter “已回滚”。

---

# 94. Canonical Model

所有模型相关 Tool 必须尽可能使用：

```text
Node
Element
Material
Section
Boundary
Load
Group
```

结果：

```text
Analysis
Result
Design
```

Adapter 负责 Native → Canonical。

---

# 95. Schema Versioning

Schema：

```text
structai://schema/model/node/v1
structai://schema/model/node/v2
```

规则：

```text
v1 never overwrite
v2 new version
```

Operation 指向明确 Schema URI。

---

# 96. Tool Discovery

Generic MCP Client：

```text
initialize
 ↓
tools/list
```

每个 Tool 至少暴露：

```text
name
description
inputSchema
```

建议通过 description / registry 信息让 Client 获知：

```text
risk
operation domain
```

底层 Native API 不进入 Tool Discovery。

---

# 97. Tool Handler Implementation

所有 Handler：

```python
async def handler(arguments: dict):
    request = ToolRequest.model_validate(arguments)

    return await execution_service.execute(
        tool_name="engineering_model_build",
        request=request,
    )
```

禁止 Handler：

```text
SQL
Adapter selection
RBAC calculation
Task worker
Native API call
```

---

# 98. Generic AI Client — 第一条 E2E

Prompt：

> 创建一个高度 6m 的 Q355B H400×400×13×21 钢柱，底部固定，顶部施加 500kN 轴压力。完成静力分析，并返回顶部节点位移和钢柱设计利用率。

期望调用：

```text
1 BUILD.COLUMN
2 MODEL.LOAD.ASSIGN
3 ANALYSIS.STATIC
4 RESULT.NODE.DISPLACEMENT
5 DESIGN.STEEL
```

---

# 99. E2E 调用细节

## Step 1 — Build

```json
{
  "operation": "BUILD.COLUMN",
  "parameters": {
    "height": 6,
    "material": "Q355B",
    "section": {
      "type": "H",
      "height": 400,
      "width": 400,
      "web_thickness": 13,
      "flange_thickness": 21
    },
    "boundary": {
      "base": "FIXED"
    }
  },
  "idempotency_key": "column-demo-001"
}
```

## Step 2 — Load

```json
{
  "operation": "MODEL.LOAD.ASSIGN",
  "parameters": {
    "case": "AXIAL",
    "target_type": "NODE",
    "target_ids": [2],
    "load": {
      "fz": -500000
    }
  },
  "idempotency_key": "load-demo-001"
}
```

## Step 3 — Analysis

```json
{
  "operation": "ANALYSIS.STATIC",
  "parameters": {
    "load_cases": ["AXIAL"]
  },
  "idempotency_key": "analysis-demo-001"
}
```

## Step 4 — Result

```json
{
  "operation": "RESULT.NODE.DISPLACEMENT",
  "parameters": {
    "node_ids": [2],
    "load_case": "AXIAL"
  }
}
```

## Step 5 — Design

```json
{
  "operation": "DESIGN.STEEL",
  "parameters": {
    "element_ids": [100],
    "code": "GB50017"
  },
  "idempotency_key": "design-demo-001"
}
```

---

# 100. Expected E2E Output

最终 AI 应能得到类似：

```json
{
  "model": {
    "column_element_id": 100,
    "top_node_id": 2
  },
  "analysis": {
    "status": "COMPLETED"
  },
  "displacement": {
    "uz": -0.015
  },
  "design": {
    "utilization_ratio": 0.82,
    "status": "PASS"
  }
}
```

实际数值必须来自真实 Adapter / Mock Adapter，不能由 Tool Contract 写死。

---

# 101. Error E2E

例如软件不支持非线性：

```json
{
  "success": false,
  "errors": [
    {
      "code": "STRUCTAI-3000",
      "type": "CAPABILITY_ERROR",
      "message": "Current software does not support ANALYSIS.NONLINEAR",
      "details": {
        "software": "CIVIL NX",
        "version": "2026",
        "capability": "ANALYSIS.NONLINEAR"
      },
      "retryable": false
    }
  ]
}
```

---

# 102. Async Task E2E

分析：

```text
Tool Call
 ↓
Task CREATED
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

MCP 首次返回：

```json
{
  "execution": {
    "mode": "ASYNC",
    "status": "QUEUED",
    "task_id": "task_001"
  }
}
```

Client 随后：

```text
Task Query / MCP Progress
```

---

# 103. Task Failure

例如软件超时：

```json
{
  "success": false,
  "errors": [
    {
      "code": "STRUCTAI-2300",
      "type": "SOFTWARE_TIMEOUT",
      "message": "Engineering software execution timed out",
      "retryable": true
    }
  ]
}
```

Task 状态：

```text
TIMEOUT
```

不得直接标记：

```text
FAILED
```

除非 Task Engine 根据 Retry Policy 完成最终归类。

---

# 104. Task Recovery

Server restart：

```text
unfinished task
 ↓
lease inspection
 ↓
RECOVERING
 ↓
resume / requeue / fail
```

Tool Contract 不承担恢复逻辑。

---

# 105. Capability Discovery

AI Client 不需要知道：

```text
MIDAS API
ETABS COM
OpenSees Script
```

只需要：

```text
Capability
```

例如：

```json
{
  "capability": "ANALYSIS.STATIC",
  "supported": true
}
```

---

# 106. Multi-Software Example

同一个请求：

```text
ANALYSIS.STATIC
```

MIDAS：

```text
Adapter
 ↓
REST
 ↓
/anal/STATIC
```

ETABS：

```text
Adapter
 ↓
COM
 ↓
RunAnalysis
```

OpenSees：

```text
Adapter
 ↓
SCRIPT
 ↓
analyze
```

AI Client 不变化。

---

# 107. Native API Mapping

一个 Operation 可以展开多个 Native API：

```text
BUILD.COLUMN
 ↓
CREATE_NODE
 ↓
CREATE_NODE
 ↓
CREATE_ELEMENT
 ↓
ASSIGN_MATERIAL
 ↓
ASSIGN_SECTION
 ↓
ASSIGN_BOUNDARY
```

这不是 MCP Client 的责任。

---

# 108. Operation Contract

每个 Operation Registry 必须至少保存：

```text
name
tool
risk_level
execution_mode
input_schema
output_schema
required_permissions
required_capabilities
transactional
rollback_supported
dry_run_supported
recovery_policy
preconditions
postconditions
```

---

# 109. Tool-Level JSON Schema

MCP `inputSchema` 可以使用统一外壳，但必须进一步限定 Operation。

例如 `engineering_analysis`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "structai://schema/tool/engineering-analysis/v2",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "operation": {
      "type": "string",
      "enum": [
        "ANALYSIS.STATIC",
        "ANALYSIS.MODAL",
        "ANALYSIS.SEISMIC",
        "ANALYSIS.SPECTRUM",
        "ANALYSIS.BUCKLING",
        "ANALYSIS.TIME_HISTORY",
        "ANALYSIS.NONLINEAR"
      ]
    },
    "parameters": {
      "type": "object"
    },
    "context": {
      "$ref": "structai://schema/mcp/execution-context-input/v1"
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
  "required": ["operation"]
}
```

其它 8 个 Tool 采用相同模式，并将 `operation.enum` 替换为各自 Operation 集合。

---

# 110. engineering_doc Tool Schema

```json
{
  "$id": "structai://schema/tool/engineering-doc/v2",
  "type": "object",
  "properties": {
    "operation": {
      "type": "string",
      "enum": [
        "NEW",
        "OPEN",
        "SAVE",
        "SAVE_AS",
        "CLOSE",
        "INFO"
      ]
    },
    "parameters": {
      "type": "object"
    },
    "context": {
      "$ref": "structai://schema/mcp/execution-context-input/v1"
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
  "required": ["operation"]
}
```

---

# 111. engineering_model_query Tool Schema

```json
{
  "$id": "structai://schema/tool/engineering-model-query/v2",
  "type": "object",
  "properties": {
    "operation": {
      "type": "string",
      "enum": [
        "MODEL.QUERY",
        "MODEL.NODE.QUERY",
        "MODEL.ELEMENT.QUERY",
        "MODEL.MATERIAL.QUERY",
        "MODEL.SECTION.QUERY",
        "MODEL.BOUNDARY.QUERY",
        "MODEL.LOAD.QUERY",
        "MODEL.GROUP.QUERY"
      ]
    },
    "parameters": {
      "type": "object"
    },
    "context": {
      "$ref": "structai://schema/mcp/execution-context-input/v1"
    }
  },
  "required": ["operation"]
}
```

---

# 112. engineering_model_assign Tool Schema

```json
{
  "$id": "structai://schema/tool/engineering-model-assign/v2",
  "type": "object",
  "properties": {
    "operation": {
      "type": "string",
      "enum": [
        "MODEL.NODE.CREATE",
        "MODEL.NODE.UPDATE",
        "MODEL.ELEMENT.CREATE",
        "MODEL.ELEMENT.UPDATE",
        "MODEL.MATERIAL.ASSIGN",
        "MODEL.SECTION.ASSIGN",
        "MODEL.BOUNDARY.ASSIGN",
        "MODEL.LOAD.ASSIGN"
      ]
    },
    "parameters": {
      "type": "object"
    },
    "context": {
      "$ref": "structai://schema/mcp/execution-context-input/v1"
    },
    "idempotency_key": {
      "type": ["string", "null"]
    },
    "dry_run": {
      "type": "boolean"
    }
  },
  "required": ["operation"]
}
```

---

# 113. engineering_model_delete Tool Schema

```json
{
  "$id": "structai://schema/tool/engineering-model-delete/v2",
  "type": "object",
  "properties": {
    "operation": {
      "type": "string",
      "enum": [
        "MODEL.NODE.DELETE",
        "MODEL.ELEMENT.DELETE",
        "MODEL.LOAD.DELETE",
        "MODEL.BOUNDARY.DELETE",
        "MODEL.GROUP.DELETE",
        "MODEL.MATERIAL.DELETE",
        "MODEL.SECTION.DELETE"
      ]
    },
    "parameters": {
      "type": "object"
    },
    "context": {
      "$ref": "structai://schema/mcp/execution-context-input/v1"
    },
    "idempotency_key": {
      "type": "string"
    },
    "confirmation_token": {
      "type": "string"
    },
    "dry_run": {
      "type": "boolean"
    }
  },
  "required": [
    "operation",
    "idempotency_key",
    "confirmation_token"
  ]
}
```

---

# 114. engineering_model_build Tool Schema

```json
{
  "$id": "structai://schema/tool/engineering-model-build/v2",
  "type": "object",
  "properties": {
    "operation": {
      "type": "string",
      "enum": [
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
        "MODEL.GENERATE_GRID"
      ]
    },
    "parameters": {
      "type": "object"
    },
    "context": {
      "$ref": "structai://schema/mcp/execution-context-input/v1"
    },
    "idempotency_key": {
      "type": "string"
    },
    "confirmation_token": {
      "type": ["string", "null"]
    },
    "dry_run": {
      "type": "boolean"
    }
  },
  "required": [
    "operation",
    "idempotency_key"
  ]
}
```

---

# 115. engineering_view Tool Schema

```json
{
  "$id": "structai://schema/tool/engineering-view/v2",
  "type": "object",
  "properties": {
    "operation": {
      "type": "string",
      "enum": [
        "VIEW.MODEL",
        "VIEW.DEFORMED_MODEL",
        "VIEW.REACTION",
        "VIEW.DISPLACEMENT",
        "VIEW.STRESS",
        "VIEW.FORCE",
        "VIEW.MODE_SHAPE"
      ]
    },
    "parameters": {
      "type": "object"
    },
    "context": {
      "$ref": "structai://schema/mcp/execution-context-input/v1"
    }
  },
  "required": ["operation"]
}
```

---

# 116. engineering_result Tool Schema

```json
{
  "$id": "structai://schema/tool/engineering-result/v2",
  "type": "object",
  "properties": {
    "operation": {
      "type": "string",
      "enum": [
        "RESULT.NODE.DISPLACEMENT",
        "RESULT.NODE.REACTION",
        "RESULT.ELEMENT.FORCE",
        "RESULT.ELEMENT.STRESS",
        "RESULT.MODE.SHAPE",
        "RESULT.ANALYSIS.SUMMARY"
      ]
    },
    "parameters": {
      "type": "object"
    },
    "context": {
      "$ref": "structai://schema/mcp/execution-context-input/v1"
    }
  },
  "required": ["operation"]
}
```

---

# 117. engineering_design Tool Schema

```json
{
  "$id": "structai://schema/tool/engineering-design/v2",
  "type": "object",
  "properties": {
    "operation": {
      "type": "string",
      "enum": [
        "DESIGN.STEEL",
        "DESIGN.CONCRETE",
        "DESIGN.SRC",
        "DESIGN.FOUNDATION",
        "DESIGN.CODE_CHECK",
        "DESIGN.OPTIMIZE"
      ]
    },
    "parameters": {
      "type": "object"
    },
    "context": {
      "$ref": "structai://schema/mcp/execution-context-input/v1"
    },
    "idempotency_key": {
      "type": "string"
    },
    "confirmation_token": {
      "type": ["string", "null"]
    },
    "dry_run": {
      "type": "boolean"
    }
  },
  "required": [
    "operation",
    "idempotency_key"
  ]
}
```

---

# 118. engineering_analysis Tool Schema

```json
{
  "$id": "structai://schema/tool/engineering-analysis/v2",
  "type": "object",
  "properties": {
    "operation": {
      "type": "string",
      "enum": [
        "ANALYSIS.STATIC",
        "ANALYSIS.MODAL",
        "ANALYSIS.SEISMIC",
        "ANALYSIS.SPECTRUM",
        "ANALYSIS.BUCKLING",
        "ANALYSIS.TIME_HISTORY",
        "ANALYSIS.NONLINEAR"
      ]
    },
    "parameters": {
      "type": "object"
    },
    "context": {
      "$ref": "structai://schema/mcp/execution-context-input/v1"
    },
    "idempotency_key": {
      "type": "string"
    },
    "dry_run": {
      "type": "boolean"
    }
  },
  "required": [
    "operation",
    "idempotency_key"
  ]
}
```

---

# 119. Operation Schema Resolution

Tool-level Schema 只负责：

```text
operation enum
common envelope
```

真正的 parameters Schema 必须进一步：

```text
Tool
 ↓
Operation Registry
 ↓
input_schema
 ↓
Schema Registry
 ↓
JSON Schema Validation
```

例如：

```text
engineering_analysis
      +
ANALYSIS.STATIC
      ↓
structai://schema/analysis/static/v1
```

---

# 120. Operation Schema 不得混淆

禁止：

```text
Tool Schema = 所有软件 API Schema
```

正确：

```text
Tool Schema
    ↓
Operation Schema
    ↓
Canonical Engineering Schema
    ↓
Adapter Transform
    ↓
Native API Schema
```

---

# 121. Response Schema Resolution

同样：

```text
Native Response
 ↓
Adapter Normalize
 ↓
Canonical Result
 ↓
Operation output_schema
 ↓
Tool Response
```

---

# 122. Warning Contract

Warning 不应作为 Error。

```json
{
  "warnings": [
    {
      "code": "STRUCTAI-W100",
      "message": "Section is close to design limit",
      "severity": "WARNING"
    }
  ]
}
```

常见：

```text
STRUCTAI-W100 Deprecated API Mapping
STRUCTAI-W110 Partial Capability
STRUCTAI-W120 Engineering Warning
STRUCTAI-W130 Result Partial
STRUCTAI-W140 Optimization Did Not Improve
```

---

# 123. Partial Result

如果底层软件返回部分结果：

```json
{
  "success": true,
  "data": {},
  "warnings": [
    {
      "code": "STRUCTAI-W130",
      "message": "Only partial result set is available"
    }
  ],
  "metadata": {
    "partial": true
  }
}
```

不得把缺失数据静默填成 0。

---

# 124. Retry Rules

可 Retry：

```text
STRUCTAI-2000
STRUCTAI-2300
部分 STRUCTAI-6000
```

通常不可 Retry：

```text
STRUCTAI-1100
STRUCTAI-1200
STRUCTAI-1300
STRUCTAI-3000
STRUCTAI-4000
STRUCTAI-4100
STRUCTAI-4200
```

具体 Retry Policy 由 Operation Registry / Adapter 决定。

---

# 125. Permission 与 Capability 的区别

Permission：

```text
用户是否有权做
```

Capability：

```text
当前软件是否能做
```

例如：

```text
User has ANALYSIS_EXECUTE
+
MIDAS 2026 supports ANALYSIS.STATIC
=
can execute
```

如果：

```text
User has permission
+
software lacks capability
```

返回：

```text
STRUCTAI-3000
```

---

# 126. Resource Access 与 Permission 的区别

```text
Permission
=
用户拥有某类操作权限

Resource Access
=
用户是否能访问这个 Project / Model / Software Instance
```

两者必须同时成立。

---

# 127. Confirmation 与 Permission 的区别

```text
Permission
=
允许做

Confirmation
=
用户明确确认当前高风险动作
```

不能用：

```text
permission = confirmation
```

替代。

---

# 128. AI Client 最小知识模型

Generic AI Client 只需要理解：

```text
Tool
Operation
Parameters
Context
Task
Result
Error
```

不需要理解：

```text
MIDAS Endpoint
ETABS COM
OpenSees Script
API Key
Adapter internals
```

---

# 129. AI Tool Description 建议

Tool description 应明确：

```text
engineering_model_build:
"Create or transform engineering model entities using high-level engineering semantics."
```

不要写：

```text
"Call MIDAS /db/NODE and /db/ELEM"
```

---

# 130. Operation Description 建议

例如：

```text
BUILD.COLUMN
"Build a structural column from geometric, material, section and boundary parameters."
```

不要暴露：

```text
POST /db/NODE
POST /db/ELEM
```

---

# 131. Tool Security Boundary

每次调用必须拥有：

```text
request_id
trace_id
authenticated identity
tenant
operation
resource
```

高风险：

```text
confirmation
audit
idempotency
lock
```

---

# 132. Tool Observability

至少记录：

```text
timestamp
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
duration
status
error_code
```

禁止：

```text
password
API key
token
private key
```

---

# 133. Tool Audit

必须 Audit：

```text
MODEL.*.DELETE
BUILD.*
ANALYSIS.*
DESIGN.*
```

建议 Audit：

```text
MODEL.*.ASSIGN
DOCUMENT.SAVE
DOCUMENT.SAVE_AS
```

Query / View 通常不要求高风险 Audit，但仍可通过 Trace 记录。

---

# 134. Tool Contract Versioning

Tool：

```text
engineering_analysis v2.0
```

Schema：

```text
structai://schema/tool/engineering-analysis/v2
```

Operation：

```text
ANALYSIS.STATIC
```

Schema 变化：

```text
v1 → v2
```

不覆盖旧版本。

---

# 135. Backward Compatibility

兼容策略：

```text
Old Tool Contract
 ↓
Version Resolver
 ↓
Current Operation
```

如果不兼容：

```text
STRUCTAI-1100
```

并给出：

```text
expected_schema
received_schema
```

---

# 136. MCP Tool Registration

伪代码：

```python
for definition in tool_registry.list_tools():
    mcp.register_tool(
        name=definition.name,
        description=definition.description,
        input_schema=schema_registry.resolve(
            definition.input_schema
        ),
        handler=tool_dispatcher.dispatch,
    )
```

Tool Registry 是唯一 Tool Source of Truth。

---

# 137. Tool Dispatcher

```python
class ToolDispatcher:

    async def dispatch(
        self,
        tool_name: str,
        arguments: dict,
    ):
        tool = registry.resolve_tool(tool_name)

        request = ToolRequest.model_validate(arguments)

        return await execution_service.execute(
            tool=tool,
            request=request,
        )
```

---

# 138. Operation Dispatcher

```python
operation = operation_registry.resolve(
    tool.name,
    request.operation,
)
```

如果 Operation 不属于当前 Tool：

```text
STRUCTAI-1000
```

不能执行。

---

# 139. Operation Capability Resolution

```python
for capability in operation.required_capabilities:
    await capability_resolver.require(
        software_instance_id,
        capability,
    )
```

缺失：

```text
STRUCTAI-3000
```

---

# 140. Generic AI Client 测试矩阵

必须测试：

```text
tools/list
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

每个 Tool 至少：

```text
valid request
invalid schema
permission denied
capability denied
resource denied
duplicate request
timeout
adapter error
```

---

# 141. 安全测试矩阵

必须：

```text
[ ] Forged user_id
[ ] Forged tenant_id
[ ] Forged role
[ ] Forged permission
[ ] Cross-tenant model
[ ] Cross-project model
[ ] Expired session
[ ] Revoked session
[ ] Confirmation replay
[ ] Confirmation wrong operation
[ ] Confirmation wrong resource
[ ] Idempotency race
[ ] Lock bypass
[ ] Native error secret leakage
```

---

# 142. Concurrency Test

同时：

```text
Client A → MODEL.NODE.UPDATE
Client B → MODEL.NODE.UPDATE
```

必须出现：

```text
one success
one STRUCTAI-1300
```

如果两个都成功覆盖：

```text
FAIL
```

---

# 143. Lock Test

同时：

```text
Task A → BUILD.FRAME
Task B → MODEL.NODE.UPDATE
```

同一 Model：

```text
Task B blocked
```

直到 Task A：

```text
COMPLETED / FAILED / CANCELLED
```

并释放 Lock。

---

# 144. Idempotency Race Test

两个请求：

```text
same tenant
same idempotency_key
same operation
```

并发提交。

必须：

```text
one execution
one reused result
```

不能：

```text
two executions
```

---

# 145. Recovery Test

执行：

```text
ANALYSIS.STATIC
```

Worker 中断。

重启：

```text
RECOVERING
 ↓
REQUEUE / RESUME / FAIL
```

最终只能存在一个有效 Task execution identity。

---

# 146. Adapter Independence Test

Mock：

```text
Mock Adapter
```

必须完整支持：

```text
BUILD.COLUMN
MODEL.LOAD.ASSIGN
ANALYSIS.STATIC
RESULT.NODE.DISPLACEMENT
DESIGN.STEEL
```

然后替换：

```text
MIDAS Adapter
```

AI Client 不修改。

---

# 147. Second Software Acceptance

第二个真实 Adapter 接入后：

```text
9 Tools unchanged
Tool Schema unchanged
AI Client unchanged
Task Engine unchanged
```

如果必须修改：

```text
Core abstraction review
```

---

# 148. Definition of Done — Tool Layer

```text
[ ] 9 Tools registered
[ ] Every Tool has version
[ ] Every Tool has inputSchema
[ ] Every Operation has schema
[ ] Every Operation has permission
[ ] Every Operation has capability
[ ] Risk level registered
[ ] Execution mode registered
[ ] Preconditions registered
[ ] Postconditions registered
[ ] Dry-run policy registered
[ ] Transaction policy registered
[ ] Recovery policy registered
[ ] Idempotency policy registered
[ ] Lock policy registered
[ ] Confirmation policy registered
[ ] Unified response
[ ] Unified errors
[ ] Pagination
[ ] Batch where applicable
[ ] Audit
[ ] Trace
[ ] Progress
[ ] Cancellation
```

---

# 149. Final Frozen Tool List

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

# 150. Final Frozen Operation List

```text
engineering_doc
 ├── NEW
 ├── OPEN
 ├── SAVE
 ├── SAVE_AS
 ├── CLOSE
 └── INFO

engineering_model_query
 ├── MODEL.QUERY
 ├── MODEL.NODE.QUERY
 ├── MODEL.ELEMENT.QUERY
 ├── MODEL.MATERIAL.QUERY
 ├── MODEL.SECTION.QUERY
 ├── MODEL.BOUNDARY.QUERY
 ├── MODEL.LOAD.QUERY
 └── MODEL.GROUP.QUERY

engineering_model_assign
 ├── MODEL.NODE.CREATE
 ├── MODEL.NODE.UPDATE
 ├── MODEL.ELEMENT.CREATE
 ├── MODEL.ELEMENT.UPDATE
 ├── MODEL.MATERIAL.ASSIGN
 ├── MODEL.SECTION.ASSIGN
 ├── MODEL.BOUNDARY.ASSIGN
 └── MODEL.LOAD.ASSIGN

engineering_model_delete
 ├── MODEL.NODE.DELETE
 ├── MODEL.ELEMENT.DELETE
 ├── MODEL.LOAD.DELETE
 ├── MODEL.BOUNDARY.DELETE
 ├── MODEL.GROUP.DELETE
 ├── MODEL.MATERIAL.DELETE
 └── MODEL.SECTION.DELETE

engineering_model_build
 ├── BUILD.NODE_GRID
 ├── BUILD.BEAM
 ├── BUILD.COLUMN
 ├── BUILD.FRAME
 ├── BUILD.TRUSS
 ├── BUILD.SLAB
 ├── BUILD.WALL
 ├── BUILD.FOUNDATION
 ├── BUILD.STEEL_FRAME
 ├── MODEL.COPY
 ├── MODEL.MOVE
 ├── MODEL.MIRROR
 ├── MODEL.PATTERN
 └── MODEL.GENERATE_GRID

engineering_view
 ├── VIEW.MODEL
 ├── VIEW.DEFORMED_MODEL
 ├── VIEW.REACTION
 ├── VIEW.DISPLACEMENT
 ├── VIEW.STRESS
 ├── VIEW.FORCE
 └── VIEW.MODE_SHAPE

engineering_result
 ├── RESULT.NODE.DISPLACEMENT
 ├── RESULT.NODE.REACTION
 ├── RESULT.ELEMENT.FORCE
 ├── RESULT.ELEMENT.STRESS
 ├── RESULT.MODE.SHAPE
 └── RESULT.ANALYSIS.SUMMARY

engineering_design
 ├── DESIGN.STEEL
 ├── DESIGN.CONCRETE
 ├── DESIGN.SRC
 ├── DESIGN.FOUNDATION
 ├── DESIGN.CODE_CHECK
 └── DESIGN.OPTIMIZE

engineering_analysis
 ├── ANALYSIS.STATIC
 ├── ANALYSIS.MODAL
 ├── ANALYSIS.SEISMIC
 ├── ANALYSIS.SPECTRUM
 ├── ANALYSIS.BUCKLING
 ├── ANALYSIS.TIME_HISTORY
 └── ANALYSIS.NONLINEAR
```

---

# 151. 与四份 Core 文档的关系

本文件依赖并遵守：

```text
Core Database Revision V2
        ↓
Core Development Revision V2
        ↓
Core Implementation Revision V2
        ↓
Core Python Implementation Revision V2
        ↓
THIS DOCUMENT
```

本文件不得改变：

```text
Authentication
IdentityContext
Tenant isolation
Resource Resolver
Execution Pipeline
Task Engine
Resource Lock
Idempotency
Adapter Architecture
MCP transport
Audit / Trace
```

---

# 152. 最终原则

> **9 个 MCP Tool 是 AI Client 看到的稳定工程语义接口。**

> **Operation 是 Tool 内部的工程动作。**

> **Capability 表示当前工程软件是否具备该能力。**

> **Adapter 将稳定的工程 Operation 转换成具体软件 API。**

> **AI Client 永远不需要知道 MIDAS、ETABS、SAP2000、ANSYS、OpenSees 的 Native API。**

最终链路：

```text
Generic AI Client
       ↓
MCP
       ↓
9 MCP Tools
       ↓
Operation
       ↓
Schema / Validation
       ↓
Permission / Confirmation
       ↓
Capability
       ↓
Task / Lock / Idempotency
       ↓
Adapter
       ↓
Native API
       ↓
Engineering Software
       ↓
Canonical Result
       ↓
MCP Response
```

**第五份至此冻结 Tool Contract 边界。**



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



# 来源映射

- `tools5`：完整收录。
- `tools15`：完整收录。
- `trans16`：完整收录。
