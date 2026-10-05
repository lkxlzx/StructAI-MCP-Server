# tools5 子文档精读报告

**源文件**: `G:\MMCP\docs\03_STRUCTAI_MCP_V2_MCP_RUNTIME.md`
**精读范围**: 第 1 行 – 第 4568 行（`# 完整收录：tools5` 起，至 `# 152. 最终原则` 结束；第 4569 行起为下一子文档 `tools15`）
**源规范文档**: `StructAI_MCP_Server_V2.0_9_MCP_Tools_Complete_Implementation_Specification.md`，Version 2.0，Status = Core Alpha Tool Contract Baseline（第 17–19 行）
**依赖**: Core_Database_Design_Revision_V2 / Core_Development_Document_Revision_V2 / Core_Implementation_Specification_Revision_V2 / Core_Python_Implementation_Specification_Revision_V2（第 20–24 行）
**边界**: 本文件只冻结 9 MCP Tool / Operation / JSON Schema / Parameters / Output / Risk / Execution Mode / Permission / Capability / Confirmation / Idempotency / Lock / Dry Run / Batch / Pre-Postconditions / Errors / Examples / Generic AI Client invocation（第 44–66 行）；**不得重新定义 Core Runtime**（第 68 行）。

---

## A. 章节地图

正文以 `# N. 标题` 为一级节（第 1–152 节），`## N.M 标题` 为二级节。

| 行 | 节 | 要点 |
|---|---|---|
| 28 | 1. 文档目的 | 冻结 Core Alpha 的 9 个 MCP Tool Contract，不重定义 Core Runtime |
| 72 | 2. 设计原则 | Tool ≠ API，必须经 Tool→Operation→Capability→API Registry→Adapter |
| 74 | 2.1 Tool ≠ API | 禁止 `engineering_analysis → /anal/STATIC`、`engineering_model_query → /db/NODE` 式直连 |
| 101 | 3. 9 个 Tool 总表 | 9 Tool 领域/默认风险/默认模式；风险 4 级、模式 3 种 |
| 134 | 4. 通用 Tool Request Contract | 统一请求外壳 6 字段 |
| 149 | 4.1 字段 | 字段类型/必填/说明 |
| 160 | 4.2 context | 客户端可提供 4 个资源 id；禁止 user_id/tenant_id/roles/permissions |
| 187 | 5. 通用 JSON Schema | `structai://schema/mcp/tool-request/v1` 全文 |
| 229 | 6. Context Input Schema | `structai://schema/mcp/execution-context-input/v1` 全文 |
| 260 | 7. 通用 Response Contract | Sync Success / Async Accepted / Error 三样例 |
| 262 | 7.1 Sync Success | SYNC + COMPLETED |
| 282 | 7.2 Async Accepted | ASYNC + QUEUED + task_id |
| 303 | 7.3 Error | success=false + errors[]（code/type/message/details/retryable） |
| 333 | 8. Error Contract | STRUCTAI-1000 ~ 7000 统一错误码；Native error 默认不暴露 |
| 382 | 9. 通用权限 | 10 个基础 Permission + Effective Permission 四要素 |
| 422 | 10. 通用执行规则 | 统一 Execution Pipeline（31 步）；Handler 不得绕过 |
| 484 | 11. Tool 1 — engineering_doc | 文档生命周期 6 Operation |
| 486 | 11.1 定位 | 工程文档生命周期管理 |
| 503 | 11.2 Tool Definition | Tool Definition JSON |
| 526 | 11.3 Permission | 6 Operation → 权限映射 |
| 539 | 11.4 Capability | DOCUMENT.* Capability |
| 554 | 11.5 Operation Parameters | NEW/OPEN/SAVE/SAVE_AS/CLOSE/INFO 参数与 Schema |
| 638 | 11.6 Preconditions | OPEN/SAVE/CLOSE 前置条件 |
| 656 | 11.7 Postconditions | 各 Operation 后置条件 |
| 677 | 11.8 Response | document_id/status/name/artifact/version |
| 693 | 12. Tool 2 — engineering_model_query | 只读查询 8 Operation |
| 695 | 12.1 定位 | LOW / SYNC / MODEL_READ |
| 722 | 12.2 Tool Definition | Tool Definition JSON |
| 736 | 12.3 通用 Query Parameters | ids/where/fields/limit/cursor + Schema |
| 785 | 12.4 MODEL.QUERY | 模型摘要与计数 |
| 805 | 12.5 MODEL.NODE.QUERY | Canonical Node |
| 820 | 12.6 MODEL.ELEMENT.QUERY | Canonical Element |
| 837 | 12.7 MODEL.MATERIAL.QUERY | 材料（Q355B 示例） |
| 853 | 12.8 MODEL.SECTION.QUERY | 截面（H 型钢示例） |
| 868 | 12.9 MODEL.BOUNDARY.QUERY | 边界 6 自由度布尔 |
| 884 | 12.10 MODEL.LOAD.QUERY | 荷载 case/target/values |
| 902 | 12.11 MODEL.GROUP.QUERY | 组 entity_type/members |
| 915 | 12.12 Pagination | has_more / next_cursor |
| 931 | 12.13 Preconditions | project/model/instance/capability 四条件 |
| 942 | 13. Tool 3 — engineering_model_assign | 创建/修改模型 8 Operation |
| 944 | 13.1 定位 | MEDIUM / SYNC-ASYNC / MODEL_WRITE |
| 971 | 14. MODEL.NODE.CREATE | 节点创建参数与 Schema（id 可空，服务端可分配） |
| 1007 | 15. MODEL.NODE.UPDATE | 更新 + expected_version；冲突 STRUCTAI-1300 |
| 1029 | 16. MODEL.ELEMENT.CREATE | type/node_i/node_j/material_id/section_id |
| 1044 | 17. MODEL.ELEMENT.UPDATE | section_id + expected_version |
| 1056 | 18. MODEL.MATERIAL.ASSIGN | target_type/target_ids/material_id |
| 1068 | 19. MODEL.SECTION.ASSIGN | target_type/target_ids/section_id |
| 1080 | 20. MODEL.BOUNDARY.ASSIGN | node_ids + boundary 6 分量 |
| 1098 | 21. MODEL.LOAD.ASSIGN | case/target_type/target_ids/load 6 分量 |
| 1118 | 22. Batch Assign | items[] + atomic；原子优先级 Native Tx→Snapshot→Compensating |
| 1158 | 23. Tool 4 — engineering_model_delete | 高风险删除 7 Operation；HIGH / ASYNC |
| 1160 | 23.1 定位 | 高风险模型删除 |
| 1185 | 24. Delete 权限与确认 | 需 MODEL_DELETE；高风险需 confirmation_token，缺失 → STRUCTAI-4100 |
| 1207 | 25. Delete 通用参数 | ids/expected_version/cascade + Schema（ids 必填） |
| 1246 | 26. Delete Preconditions | 6 条件；被引用节点须 reject 或 cascade=true |
| 1281 | 27. Delete Audit | 所有 DELETE 必须生成 Audit/Trace/Task |
| 1295 | 28. Tool 5 — engineering_model_build | 工程语义建模 14 Operation；HIGH / ASYNC / MODEL_WRITE |
| 1297 | 28.1 定位 | model_assign=低层变更，model_build=高层工程语义构建 |
| 1313 | 29. Operations | 9 个 BUILD.* + 5 个 MODEL.* |
| 1343 | 30. BUILD.NODE_GRID | origin/nx/ny/dx/dy |
| 1370 | 31. BUILD.BEAM | start/end/material/section |
| 1391 | 32. BUILD.COLUMN | height/material/section/boundary + Canonical 结果 |
| 1447 | 33. BUILD.FRAME | levels/bays/bay_width/story_height/材料/柱梁截面 |
| 1463 | 34. BUILD.TRUSS | span/height/panels/材料/弦腹杆截面 |
| 1478 | 35. BUILD.SLAB | boundary(x_min..z)/thickness/material |
| 1496 | 36. BUILD.WALL | start/end/height/thickness/material |
| 1510 | 37. BUILD.FOUNDATION | type/center/width/length/depth/material |
| 1525 | 38. BUILD.STEEL_FRAME | width/length/height/bay_spacing/材料/截面 |
| 1543 | 39. MODEL.COPY | source_ids + translation |
| 1558 | 40. MODEL.MOVE | ids + translation |
| 1573 | 41. MODEL.MIRROR | ids + plane(point/normal) |
| 1587 | 42. MODEL.PATTERN | ids/count/translation |
| 1603 | 43. MODEL.GENERATE_GRID | x/y/z 坐标数组 |
| 1615 | 44. Build Dry Run | 所有 Build 原则必须支持 Dry Run；返回 planned_changes；不得修改模型 |
| 1657 | 45. Build Preconditions | 8 条 |
| 1672 | 46. Build Postconditions | 5 条 |
| 1686 | 47. Tool 6 — engineering_view | 可视化 7 Operation；LOW / SYNC |
| 1688 | 47.1 定位 | 模型与结果可视化控制；MODEL_READ / RESULT_READ |
| 1714 | 48. VIEW.MODEL | entity_type/ids/camera → view_id+artifact_id |
| 1737 | 49. VIEW.DEFORMED_MODEL | load_case/scale |
| 1748 | 50. VIEW.REACTION | load_case/node_ids |
| 1759 | 51. VIEW.DISPLACEMENT | load_case/component/scale |
| 1771 | 52. VIEW.STRESS | load_case/component |
| 1782 | 53. VIEW.FORCE | load_case/component |
| 1793 | 54. VIEW.MODE_SHAPE | mode/scale |
| 1804 | 55. View Output | 返回 artifact/image/scene descriptor/native view state；不塞二进制 |
| 1829 | 56. Tool 7 — engineering_result | 结果读取 6 Operation；LOW / SYNC / RESULT_READ |
| 1831 | 56.1 定位 | 读取已完成的分析结果 |
| 1856 | 57. RESULT.NODE.DISPLACEMENT | node_ids/load_case → ux/uy/uz |
| 1882 | 58. RESULT.NODE.REACTION | node_ids/load_case → fx..mz |
| 1911 | 59. RESULT.ELEMENT.FORCE | element_ids/load_case → n/vy/vz/mx/my/mz |
| 1940 | 60. RESULT.ELEMENT.STRESS | element_ids/load_case |
| 1951 | 61. RESULT.MODE.SHAPE | mode → frequency/nodes |
| 1971 | 62. RESULT.ANALYSIS.SUMMARY | analysis_task_id → status/type/load_cases/result_sets |
| 1993 | 63. Result Preconditions | 分析完成/结果集存在/capability；未完成 → STRUCTAI-5000 或 RESULT_NOT_READY（须映射） |
| 2017 | 64. Result Pagination | data[] + pagination |
| 2033 | 65. Tool 8 — engineering_design | 设计验算优化 5 Operation；HIGH / ASYNC / DESIGN_EXECUTE |
| 2035 | 65.1 定位 | 工程设计、规范验算、优化 |
| 2067 | 66. DESIGN.STEEL | element_ids/code/combination/options；公式不写死在 Tool |
| 2103 | 67. DESIGN.CONCRETE | crack/strength/serviceability |
| 2120 | 68. DESIGN.FOUNDATION | foundation_ids/code/options(4 项) |
| 2137 | 69. DESIGN.CODE_CHECK | entity_type/entity_ids/code/checks[] |
| 2156 | 70. DESIGN.OPTIMIZE | objective/constraints/variables/apply；默认 apply=false |
| 2202 | 71. Design Dry Run | OPTIMIZE 必须支持 apply=false；apply=true 需高风险确认+audit+lock |
| 2228 | 72. Design Output | status/utilization_ratio/governing_check/warnings/recommendations |
| 2246 | 73. Tool 9 — engineering_analysis | 分析计算 7 Operation；HIGH / ASYNC / ANALYSIS_EXECUTE |
| 2248 | 73.1 定位 | 执行工程分析计算 |
| 2274 | 74. ANALYSIS.STATIC | load_cases/combinations → task_id+QUEUED |
| 2300 | 75. ANALYSIS.MODAL | modes/solver_options |
| 2311 | 76. ANALYSIS.SEISMIC | direction/cases/damping_ratio |
| 2323 | 77. ANALYSIS.SPECTRUM | spectrum_id/direction/damping_ratio |
| 2335 | 78. ANALYSIS.BUCKLING | modes/load_case |
| 2346 | 79. ANALYSIS.TIME_HISTORY | case/duration/time_step/record |
| 2359 | 80. ANALYSIS.NONLINEAR | load_case/solver(max_steps/tolerance) |
| 2373 | 81. Analysis Preconditions | 8 条 |
| 2396 | 82. Analysis Postconditions | 4 条；部分结果标 PARTIAL，不得标 COMPLETED |
| 2419 | 83. Analysis Task Response | 立即返回 ASYNC/QUEUED/task_id |
| 2436 | 84. MCP Progress | 0→VALIDATING→QUEUED→RUNNING→PROCESSING→100→COMPLETED；来源必须 Task Engine |
| 2462 | 85. MCP Cancellation | MCP cancel→TaskEngine.cancel()→CANCEL_REQUESTED→Adapter.cancel()→CANCELLED；不得伪造 |
| 2492 | 86. Tool Operation Matrix | 47 行 Operation×Tool×Risk×Mode×Permission×Capability |
| 2543 | 87. Capability Requirements for Build | BUILD.COLUMN / BUILD.FRAME / BUILD.STEEL_FRAME 所需 capability |
| 2576 | 88. Lock Requirements | Query=READ、Assign=WRITE、Delete=EXCLUSIVE、Build=WRITE(复杂 EXCLUSIVE)、Analysis/Design 规则 |
| 2637 | 89. Idempotency Requirements | 各 Tool 必须/推荐/可选 + 唯一键 tenant_id+idempotency_key |
| 2665 | 90. Confirmation Requirements | 3 类默认需确认 + Token 6 条约束 |
| 2698 | 91. Dry Run Matrix | 9 Tool 的 Dry Run 策略 |
| 2730 | 92. Batch Matrix | 9 Tool 的 Batch 策略 |
| 2746 | 93. Transaction Matrix | 11 类 Operation 的事务/回滚 + 回滚优先级 4 级 |
| 2778 | 94. Canonical Model | 7 个模型实体 + 3 个结果实体；Adapter 负责 Native→Canonical |
| 2804 | 95. Schema Versioning | v1 永不覆盖、v2 新版本；Operation 指向明确 Schema URI |
| 2824 | 96. Tool Discovery | initialize→tools/list；至少暴露 name/description/inputSchema |
| 2853 | 97. Tool Handler Implementation | Handler 只做 ToolRequest 校验 + execution_service.execute |
| 2879 | 98. Generic AI Client — 第一条 E2E | 钢柱 Prompt 与 5 步期望调用 |
| 2897 | 99. E2E 调用细节 | Step1 Build / Step2 Load / Step3 Analysis / Step4 Result / Step5 Design |
| 2978 | 100. Expected E2E Output | 期望聚合输出；数值必须来自真实/Mock Adapter |
| 3005 | 101. Error E2E | 不支持非线性 → STRUCTAI-3000 CAPABILITY_ERROR |
| 3030 | 102. Async Task E2E | Tool Call→CREATED→VALIDATING→QUEUED→RUNNING→PROCESSING→COMPLETED |
| 3070 | 103. Task Failure | 超时 → STRUCTAI-2300 retryable=true，状态 TIMEOUT 不得直接 FAILED |
| 3104 | 104. Task Recovery | lease inspection→RECOVERING→resume/requeue/fail；Tool Contract 不承担 |
| 3122 | 105. Capability Discovery | Client 只需 Capability，不需 MIDAS API/ETABS COM/OpenSees Script |
| 3149 | 106. Multi-Software Example | MIDAS→REST→/anal/STATIC；ETABS→COM→RunAnalysis；OpenSees→SCRIPT→analyze |
| 3191 | 107. Native API Mapping | BUILD.COLUMN → 6 个 native 调用链 |
| 3215 | 108. Operation Contract | Operation Registry 14 个必存字段 |
| 3238 | 109. Tool-Level JSON Schema | inputSchema 统一外壳 + operation enum（以 analysis 为例） |
| 3287 | 110. engineering_doc Tool Schema | `structai://schema/tool/engineering-doc/v2` |
| 3327 | 111. engineering_model_query Tool Schema | `.../engineering-model-query/v2` |
| 3360 | 112. engineering_model_assign Tool Schema | `.../engineering-model-assign/v2` |
| 3399 | 113. engineering_model_delete Tool Schema | `.../engineering-model-delete/v2`（三项 required） |
| 3444 | 114. engineering_model_build Tool Schema | `.../engineering-model-build/v2` |
| 3495 | 115. engineering_view Tool Schema | `.../engineering-view/v2` |
| 3527 | 116. engineering_result Tool Schema | `.../engineering-result/v2` |
| 3558 | 117. engineering_design Tool Schema | `.../engineering-design/v2` |
| 3600 | 118. engineering_analysis Tool Schema | `.../engineering-analysis/v2` |
| 3641 | 119. Operation Schema Resolution | Tool→Operation Registry→input_schema→Schema Registry |
| 3676 | 120. Operation Schema 不得混淆 | Tool Schema ≠ 所有软件 API Schema（5 层链路） |
| 3700 | 121. Response Schema Resolution | Native→Adapter Normalize→Canonical Result→output_schema→Tool Response |
| 3718 | 122. Warning Contract | STRUCTAI-W100/W110/W120/W130/W140 |
| 3746 | 123. Partial Result | metadata.partial=true + W130；不得把缺失填 0 |
| 3770 | 124. Retry Rules | 可重试 2000/2300/部分 6000；不可重试 1100/1200/1300/3000/4000/4100/4200 |
| 3796 | 125. Permission 与 Capability 的区别 | 用户是否有权 vs 软件是否能做；缺 capability → STRUCTAI-3000 |
| 3836 | 126. Resource Access 与 Permission 的区别 | 两者必须同时成立 |
| 3852 | 127. Confirmation 与 Permission 的区别 | permission ≠ confirmation |
| 3874 | 128. AI Client 最小知识模型 | 只需 Tool/Operation/Parameters/Context/Task/Result/Error |
| 3900 | 129. AI Tool Description 建议 | 不得写 "Call MIDAS /db/NODE and /db/ELEM" |
| 3917 | 130. Operation Description 建议 | 不得暴露 POST /db/NODE、POST /db/ELEM |
| 3935 | 131. Tool Security Boundary | 每次调用必须有 request_id/trace_id/identity/tenant/operation/resource |
| 3959 | 132. Tool Observability | 14 个日志字段；禁止记录 password/API key/token/private key |
| 3991 | 133. Tool Audit | 必须 Audit：MODEL.*.DELETE、BUILD.*、ANALYSIS.*、DESIGN.* |
| 4014 | 134. Tool Contract Versioning | Tool v2.0 / Schema v2 / Operation；不覆盖旧版本 |
| 4044 | 135. Backward Compatibility | Version Resolver；不兼容 → STRUCTAI-1100 + expected/received_schema |
| 4071 | 136. MCP Tool Registration | 伪代码；Tool Registry 是唯一 Tool Source of Truth |
| 4091 | 137. Tool Dispatcher | ToolDispatcher.dispatch 伪代码 |
| 4113 | 138. Operation Dispatcher | Operation 不属于当前 Tool → STRUCTAI-1000 |
| 4132 | 139. Operation Capability Resolution | 逐 capability require；缺失 → STRUCTAI-3000 |
| 4150 | 140. Generic AI Client 测试矩阵 | tools/list + 9 Tool；每 Tool 8 类用例 |
| 4182 | 141. 安全测试矩阵 | 14 项安全检查清单 |
| 4205 | 142. Concurrency Test | 并发 UPDATE → 一成功一 STRUCTAI-1300 |
| 4229 | 143. Lock Test | BUILD.FRAME 持锁期间 MODEL.NODE.UPDATE 阻塞 |
| 4254 | 144. Idempotency Race Test | 同 tenant/key/operation 并发 → 一次执行一次复用 |
| 4281 | 145. Recovery Test | ANALYSIS.STATIC worker 中断后 RECOVERING |
| 4303 | 146. Adapter Independence Test | Mock Adapter 支撑 5 个 Operation 后换 MIDAS Adapter |
| 4331 | 147. Second Software Acceptance | 第二真实 Adapter 接入后 9 Tool/Schema/Client/TaskEngine 不变 |
| 4350 | 148. Definition of Done — Tool Layer | 24 项验收清单 |
| 4381 | 149. Final Frozen Tool List | 9 Tool 冻结清单 |
| 4397 | 150. Final Frozen Operation List | 9 Tool × 各自 Operation 树（共 60 Operation） |
| 4489 | 151. 与四份 Core 文档的关系 | 不得改变 Auth/Identity/Tenant/Pipeline/Task/Lock/Idempotency/Adapter/Transport/Audit |
| 4523 | 152. 最终原则 | 9 Tool 是稳定工程语义接口；AI 永不需要知道 Native API |
---

## C. 通用契约（第 4–10 节）

### C.1 Tool Request Contract（第 134–183 行）

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

| 字段 | 类型 | 必须 | 说明 |
|---|---|---|---|
| `operation` | string | 是 | Operation Code |
| `parameters` | object | 否 | Operation 参数 |
| `context` | object | 否 | 资源选择上下文 |
| `idempotency_key` | string | 条件 | 写操作/异步任务推荐或必须 |
| `confirmation_token` | string | 条件 | 高风险操作 |
| `dry_run` | boolean | 否 | 是否只验证/生成计划 |

`context` 客户端**允许**提供：`software_instance_id` / `project_id` / `model_id` / `document_id`（均 uuid，可 null）。
`context` 客户端**不得**提供：`user_id` / `tenant_id` / `roles` / `permissions` / `effective_permissions` —— 这些由服务器 Authentication / Session / IdentityContext 生成。

### C.2 通用 JSON Schema（第 187–225 行，原样）

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "structai://schema/mcp/tool-request/v1",
  "title": "StructAI MCP Tool Request",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "operation": { "type": "string", "minLength": 1 },
    "parameters": { "type": "object", "default": {} },
    "context": { "$ref": "structai://schema/mcp/execution-context-input/v1" },
    "idempotency_key": { "type": ["string", "null"], "minLength": 1, "maxLength": 256 },
    "confirmation_token": { "type": ["string", "null"], "minLength": 1, "maxLength": 512 },
    "dry_run": { "type": "boolean", "default": false }
  },
  "required": ["operation"]
}
```

### C.3 Context Input Schema（第 229–256 行，原样）

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "structai://schema/mcp/execution-context-input/v1",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "software_instance_id": { "type": ["string", "null"], "format": "uuid" },
    "project_id":           { "type": ["string", "null"], "format": "uuid" },
    "model_id":             { "type": ["string", "null"], "format": "uuid" },
    "document_id":          { "type": ["string", "null"], "format": "uuid" }
  }
}
```

### C.4 通用 Response Contract（第 260–329 行）

Sync Success（7.1）：
```json
{ "success": true, "request_id": "req_001", "trace_id": "trace_001",
  "tool": "engineering_model_query", "operation": "MODEL.NODE.QUERY",
  "execution": { "mode": "SYNC", "status": "COMPLETED" },
  "data": {}, "warnings": [], "errors": [], "metadata": {} }
```
Async Accepted（7.2）：
```json
{ "success": true, "request_id": "req_002", "trace_id": "trace_002",
  "tool": "engineering_analysis", "operation": "ANALYSIS.STATIC",
  "execution": { "mode": "ASYNC", "status": "QUEUED", "task_id": "task_001" },
  "data": null, "warnings": [], "errors": [], "metadata": {} }
```
Error（7.3）：
```json
{ "success": false, "request_id": "req_003", "trace_id": "trace_003",
  "tool": "engineering_analysis", "operation": "ANALYSIS.STATIC",
  "execution": { "mode": "ASYNC", "status": "FAILED" },
  "data": null, "warnings": [], "errors": [
    { "code": "STRUCTAI-3000", "type": "CAPABILITY_ERROR",
      "message": "Current software does not support this operation",
      "details": {}, "retryable": false } ],
  "metadata": {} }
```

### C.5 Error Contract 错误码（第 333–378 行）

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
Native error 默认不暴露；诊断模式可加 `cause: { provider: "MIDAS", native_code, native_message }`（第 366–378 行）。

### C.6 通用权限（第 382–418 行）

基础 Permission：`DOCUMENT_READ`、`DOCUMENT_WRITE`、`MODEL_READ`、`MODEL_WRITE`、`MODEL_DELETE`、`ANALYSIS_EXECUTE`、`DESIGN_EXECUTE`、`DESIGN_MODIFY`、`RESULT_READ`、`SYSTEM_ADMIN`、`TOOL_TEST`、`API_TEST`。
Tool 权限不是唯一授权依据，最终必须经过：`Effective Permission + Resource Access + Operation Permission + Capability`。

### C.7 通用执行规则（第 422–480 行）

MCP Request → Authenticate → Server IdentityContext → ExecutionContext → Resolve Tool → Resolve Operation → Resolve Resource → Schema Validation → Engineering Validation → Preconditions → Effective Permission → Quota/Rate Limit → Confirmation → Idempotency → Concurrency/Resource Lock → Capability → Task/Transaction → Adapter → Result Normalization → Postconditions → Release Lock → Persist Result → Audit → Trace → Event → MCP Response。**Tool Handler 不允许绕过此流程。**
---

## B. 9 个 Tool 完整规格

### B.0 总表（第 101–130 行）

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

风险等级：LOW / MEDIUM / HIGH / CRITICAL；执行模式：SYNC / ASYNC / STREAM。

---

### B.1 Tool 1 — `engineering_doc`（第 484–689 行）

**定位**：工程文档生命周期管理。

**Tool Definition（第 505–522 行，原样）**
```json
{ "name": "engineering_doc", "version": "2.0", "category": "DOCUMENT",
  "description": "工程文档生命周期管理", "risk_level": "MEDIUM", "execution_mode": "SYNC",
  "operations": ["NEW", "OPEN", "SAVE", "SAVE_AS", "CLOSE", "INFO"] }
```

**Permission（第 528–535 行）**：NEW→DOCUMENT_WRITE；OPEN→DOCUMENT_READ；SAVE→DOCUMENT_WRITE；SAVE_AS→DOCUMENT_WRITE；CLOSE→DOCUMENT_WRITE；INFO→DOCUMENT_READ。
**Capability（第 541–550 行）**：`DOCUMENT.NEW` / `DOCUMENT.OPEN` / `DOCUMENT.SAVE` / `DOCUMENT.SAVE_AS` / `DOCUMENT.CLOSE` / `DOCUMENT.INFO`。

**Operation 清单与参数**

| Operation | 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| NEW | `name` | string | 是 | minLength 1 |
| NEW | `format` | string | 否 | 默认 `"native"` |
| NEW | `template` | string \| null | 否 | 模板引用 |
| OPEN | `artifact_id` | string(uuid) | 二者其一 | 或使用 `path`（local reference）；实际文件访问必须经 Artifact / Document Service |
| OPEN | `path` | string | 二者其一 | local reference |
| SAVE | — | — | — | 空对象 `{}` |
| SAVE_AS | `name` | string | 是（示例） | 如 `factory_model_v2` |
| SAVE_AS | `format` | string | 否 | 如 `native` |
| CLOSE | `save` | boolean | 否 | 是否保存后关闭 |
| INFO | — | — | — | 空对象 `{}` |

NEW 的 JSON Schema（第 569–587 行）：`type: object`、`additionalProperties: false`、`required: ["name"]`。

**Preconditions（第 640–652 行）**：OPEN → artifact exists / compatible software instance / adapter connected；SAVE → document opened / software connected；CLOSE → document exists。
**Postconditions（第 658–673 行）**：NEW→document created；OPEN→document active；SAVE→latest document persisted；SAVE_AS→new artifact/document created；CLOSE→document inactive。

**Response（第 679–688 行）**
```json
{ "document_id": "doc_001", "status": "OPEN", "name": "factory_model",
  "artifact": { "artifact_id": "artifact_001" }, "version": 1 }
```

---

### B.2 Tool 2 — `engineering_model_query`（第 693–940 行）

**定位**：只读查询工程模型。默认 Risk LOW / Execution SYNC / Permission `MODEL_READ`。
**Tool Definition（第 724–731 行，原样）**
```json
{ "name": "engineering_model_query", "version": "2.0",
  "category": "MODEL_QUERY", "risk_level": "LOW", "execution_mode": "SYNC" }
```

**通用 Query Parameters（第 738–781 行）**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `ids` | array[string \| integer] | 否 | 目标实体 id 列表 |
| `where` | object | 否 | 过滤条件 |
| `fields` | array[string] | 否 | 字段投影 |
| `limit` | integer | 否 | 1–10000，默认 100 |
| `cursor` | string \| null | 否 | 分页游标 |

**Operation 清单与参数/输出**

| Operation | 参数 | 输出 Canonical 结构 |
|---|---|---|
| MODEL.QUERY | 通用查询参数 | `{ model_id, name, counts:{nodes,elements,materials,sections,loads} }` |
| MODEL.NODE.QUERY | 通用查询参数 | `{ id, x, y, z }` |
| MODEL.ELEMENT.QUERY | 通用查询参数 | `{ id, type:"BEAM", node_i, node_j, material_id, section_id }` |
| MODEL.MATERIAL.QUERY | 通用查询参数 | `{ id, name:"Q355B", type:"STEEL", properties:{fy,fu} }` |
| MODEL.SECTION.QUERY | 通用查询参数 | `{ id, type:"H", height, width, web_thickness, flange_thickness }` |
| MODEL.BOUNDARY.QUERY | 通用查询参数 | `{ node_id, ux,uy,uz,rx,ry,rz }`（boolean） |
| MODEL.LOAD.QUERY | 通用查询参数 | `{ id, case:"N", target_type:"NODE", target_id, values:{fx,fy,fz} }` |
| MODEL.GROUP.QUERY | 通用查询参数 | `{ id, name:"Columns", entity_type:"ELEMENT", members:[...] }` |

**Pagination（第 915–927 行）**：所有大查询返回 `{ "data": [], "pagination": { "has_more": true, "next_cursor": "opaque-cursor" } }`。
**Preconditions（第 933–938 行）**：project accessible / model exists / software instance connected when native query required / capability supported。
**Capability（第 86 节矩阵）**：`MODEL.READ`、`MODEL.NODE.READ`、`MODEL.ELEMENT.READ`、`MODEL.MATERIAL.READ`、`MODEL.SECTION.READ`、`MODEL.BOUNDARY.READ`、`MODEL.LOAD.READ`、`MODEL.GROUP.READ`。
---

### B.3 Tool 3 — `engineering_model_assign`（第 942–1155 行）

**定位**：创建/修改工程模型。默认 Risk MEDIUM / Execution SYNC 或 ASYNC / Permission `MODEL_WRITE`。
> 注：本文档未给出 `engineering_model_assign` 的 Tool Definition JSON 块，仅有 §13.1 定位 + §112 的 Tool-Level Schema（见 F 节）。

**Operation 清单与参数**

| Operation | 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| MODEL.NODE.CREATE | `id` | integer \| null | 否 | minimum 1；服务端可以自动分配 ID |
| MODEL.NODE.CREATE | `x`,`y`,`z` | number | 是 | required: ["x","y","z"]；additionalProperties false |
| MODEL.NODE.UPDATE | `id` | integer | 是 | 目标节点 |
| MODEL.NODE.UPDATE | `x`,`y`,`z` | number | 是 | 新坐标 |
| MODEL.NODE.UPDATE | `expected_version` | integer | 条件 | 必须支持乐观并发；冲突 → STRUCTAI-1300 |
| MODEL.ELEMENT.CREATE | `id` | null | 否 | 示例为 null（服务端分配） |
| MODEL.ELEMENT.CREATE | `type` | string | 是 | 如 `BEAM` |
| MODEL.ELEMENT.CREATE | `node_i`,`node_j` | integer | 是 | 端节点 |
| MODEL.ELEMENT.CREATE | `material_id` | string | 否 | 如 `mat_001` |
| MODEL.ELEMENT.CREATE | `section_id` | string | 否 | 如 `sec_001` |
| MODEL.ELEMENT.UPDATE | `id` | integer | 是 | 目标单元 |
| MODEL.ELEMENT.UPDATE | `section_id` | string | 是 | 新截面 |
| MODEL.ELEMENT.UPDATE | `expected_version` | integer | 条件 | 乐观并发 |
| MODEL.MATERIAL.ASSIGN | `target_type` | string | 是 | 如 `ELEMENT` |
| MODEL.MATERIAL.ASSIGN | `target_ids` | array[integer] | 是 | 如 `[100,101]` |
| MODEL.MATERIAL.ASSIGN | `material_id` | string | 是 | 如 `mat_001` |
| MODEL.SECTION.ASSIGN | `target_type` | string | 是 | 如 `ELEMENT` |
| MODEL.SECTION.ASSIGN | `target_ids` | array[integer] | 是 | 如 `[100]` |
| MODEL.SECTION.ASSIGN | `section_id` | string | 是 | 如 `sec_001` |
| MODEL.BOUNDARY.ASSIGN | `node_ids` | array[integer] | 是 | 如 `[1]` |
| MODEL.BOUNDARY.ASSIGN | `boundary` | object | 是 | `ux/uy/uz/rx/ry/rz` 六布尔 |
| MODEL.LOAD.ASSIGN | `case` | string | 是 | 如 `N` |
| MODEL.LOAD.ASSIGN | `target_type` | string | 是 | 如 `NODE` |
| MODEL.LOAD.ASSIGN | `target_ids` | array[integer] | 是 | 如 `[2]` |
| MODEL.LOAD.ASSIGN | `load` | object | 是 | `fx,fy,fz,mx,my,mz`（力/弯矩） |

**Batch Assign（第 1118–1154 行）**
```json
{ "items": [ { "operation": "MODEL.NODE.CREATE", "parameters": { "x":0,"y":0,"z":0 } },
             { "operation": "MODEL.NODE.CREATE", "parameters": { "x":0,"y":0,"z":6 } } ],
  "atomic": true }
```
原子优先顺序：Native Transaction → Snapshot / Restore → Compensating Action；最终无法原子化时必须报告实际结果。
**Capability**：`MODEL.NODE.WRITE` / `MODEL.ELEMENT.WRITE` / `MODEL.MATERIAL.WRITE` / `MODEL.SECTION.WRITE` / `MODEL.BOUNDARY.WRITE` / `MODEL.LOAD.WRITE`。

---

### B.4 Tool 4 — `engineering_model_delete`（第 1158–1292 行）

**定位**：高风险模型删除。默认 Risk HIGH / Execution ASYNC。
**权限与确认（第 1185–1203 行）**：所有 DELETE 至少 `MODEL_DELETE`；高风险删除必须 `confirmation_token`，缺失 → `STRUCTAI-4100`。
**Capability**：`MODEL.NODE.DELETE` / `MODEL.ELEMENT.DELETE` / `MODEL.LOAD.DELETE` / `MODEL.BOUNDARY.DELETE` / `MODEL.GROUP.DELETE` / `MODEL.MATERIAL.DELETE` / `MODEL.SECTION.DELETE`。

**Operation 清单（7 个）**：`MODEL.NODE.DELETE`、`MODEL.ELEMENT.DELETE`、`MODEL.LOAD.DELETE`、`MODEL.BOUNDARY.DELETE`、`MODEL.GROUP.DELETE`、`MODEL.MATERIAL.DELETE`、`MODEL.SECTION.DELETE`。
（文档未逐个列出各 Delete Operation 的参数，7 个 Operation 共用 §25 通用参数。）

**Delete 通用参数（第 1209–1242 行）**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `ids` | array[integer \| string] | 是 | minItems 1 |
| `expected_version` | integer \| null | 否 | minimum 0 |
| `cascade` | boolean | 否 | 默认 false |

Schema：`additionalProperties: false`，`required: ["ids"]`。

**Preconditions（第 1250–1257 行）**：model exists / target nodes exist / user has MODEL_DELETE / required capability exists / confirmation valid / lock acquired。
若 Node 仍被 Element 引用，工程校验必须明确 `reject` 或要求 `cascade=true`；**Cascade 必须由 Operation Schema 明确允许**（第 1259–1277 行）。
**Audit（第 1283–1291 行）**：所有 DELETE 必须生成 Audit / Trace / Task。
---

### B.5 Tool 5 — `engineering_model_build`（第 1295–1684 行）

**定位**：工程语义建模。与 assign 的区别：`model_assign = low-level model mutation`，`model_build = high-level engineering semantic construction`。
默认 Risk HIGH / Execution ASYNC / Permission `MODEL_WRITE`。
> 注：未给出 Tool Definition JSON 块；Tool-Level Schema 见 §114。

**Operation 清单与参数（14 个）**

| Operation | 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| BUILD.NODE_GRID | `origin` | object{x,y,z} | 是 | 网格原点 |
| BUILD.NODE_GRID | `nx`,`ny` | integer | 是 | X/Y 方向节点数 |
| BUILD.NODE_GRID | `dx`,`dy` | number | 是 | 间距 |
| BUILD.NODE_GRID | 输出 | — | — | `{ created_nodes: 20, node_ids: [1,2,3] }` |
| BUILD.BEAM | `start` | object{x,y,z} | 是 | 起点 |
| BUILD.BEAM | `end` | object{x,y,z} | 是 | 终点 |
| BUILD.BEAM | `material` | string | 是 | 如 `Q355B` |
| BUILD.BEAM | `section` | string | 是 | 如 `H400x400x13x21` |
| BUILD.COLUMN | `height` | number | 是 | 如 6 |
| BUILD.COLUMN | `material` | string | 是 | 如 `Q355B` |
| BUILD.COLUMN | `section` | object{type,height,width,web_thickness,flange_thickness} | 是 | H 型钢参数 |
| BUILD.COLUMN | `boundary` | object{base} | 否 | 如 `{"base":"FIXED"}` |
| BUILD.COLUMN | 输出 | — | — | `{ nodes:[{id,x,y,z}...], elements:[{id,type:"COLUMN",node_i,node_j}], assignments:{material,section} }` |
| BUILD.FRAME | `levels`,`bays` | integer | 是 | 层数/跨数 |
| BUILD.FRAME | `bay_width`,`story_height` | number | 是 | 跨宽/层高 |
| BUILD.FRAME | `material` | string | 是 | `Q355B` |
| BUILD.FRAME | `column_section`,`beam_section` | string | 是 | 柱/梁截面 |
| BUILD.TRUSS | `span`,`height` | number | 是 | 跨度/高度 |
| BUILD.TRUSS | `panels` | integer | 是 | 节间数 |
| BUILD.TRUSS | `material` | string | 是 | `Q355B` |
| BUILD.TRUSS | `chord_section`,`web_section` | string | 是 | 弦杆/腹杆截面 |
| BUILD.SLAB | `boundary` | object{x_min,x_max,y_min,y_max,z} | 是 | 板范围 |
| BUILD.SLAB | `thickness` | number | 是 | 如 0.15 |
| BUILD.SLAB | `material` | string | 是 | 如 `C40` |
| BUILD.WALL | `start`,`end` | array[number] | 是 | 如 `[0,0,0]` / `[0,8,0]` |
| BUILD.WALL | `height`,`thickness` | number | 是 | 如 6 / 0.2 |
| BUILD.WALL | `material` | string | 是 | 如 `C40` |
| BUILD.FOUNDATION | `type` | string | 是 | 如 `PAD` |
| BUILD.FOUNDATION | `center` | array[number] | 是 | `[0,0,0]` |
| BUILD.FOUNDATION | `width`,`length`,`depth` | number | 是 | 2.5 / 2.5 / 0.6 |
| BUILD.FOUNDATION | `material` | string | 是 | 如 `C35` |
| BUILD.STEEL_FRAME | `width`,`length`,`height` | number | 是 | 24 / 60 / 8 |
| BUILD.STEEL_FRAME | `bay_spacing` | number | 是 | 6 |
| BUILD.STEEL_FRAME | `material` | string | 是 | `Q355B` |
| BUILD.STEEL_FRAME | `column_section`,`beam_section` | string | 是 | `H500x300x12x20` / `H450x250x10x16` |
| MODEL.COPY | `source_ids` | array[integer] | 是 | 如 `[100,101]` |
| MODEL.COPY | `translation` | object{x,y,z} | 是 | 平移向量 |
| MODEL.MOVE | `ids` | array[integer] | 是 | 如 `[100,101]` |
| MODEL.MOVE | `translation` | object{x,y,z} | 是 | 平移向量 |
| MODEL.MIRROR | `ids` | array[integer] | 是 | 如 `[100,101]` |
| MODEL.MIRROR | `plane` | object{point[3],normal[3]} | 是 | 镜像平面 |
| MODEL.PATTERN | `ids` | array[integer] | 是 | 如 `[100]` |
| MODEL.PATTERN | `count` | integer | 是 | 如 5 |
| MODEL.PATTERN | `translation` | object{x,y,z} | 是 | 阵列步距 |
| MODEL.GENERATE_GRID | `x`,`y`,`z` | array[number] | 是 | 如 `[0,6,12,18]` / `[0,6,12]` / `[0,4,8]` |

**Build Dry Run（第 1615–1653 行）**：所有 Build Operation 原则上必须支持 Dry Run。请求 `dry_run: true`；返回
```json
{ "dry_run": true, "planned_changes": { "nodes":2,"elements":1,"materials":1,"sections":1,"boundaries":1 }, "warnings": [] }
```
**不得修改模型。**

**Preconditions（第 1659–1668 行）**：project active / software instance selected / software connected / required capabilities available / geometry valid / material valid / section valid / model lock available。
**Postconditions（第 1674–1682 行）**：expected nodes exist / expected elements exist / material assignment exists / section assignment exists / boundary assignment exists。
**Capability（第 2543–2572 行）**：见 D 节「Capability Requirements for Build」。
---

### B.6 Tool 6 — `engineering_view`（第 1686–1826 行）

**定位**：工程模型和结果的可视化控制。默认 Risk LOW / Execution SYNC / Permission `MODEL_READ` 或 `RESULT_READ`。
> 未给出 Tool Definition JSON；Tool-Level Schema 见 §115。

| Operation | 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| VIEW.MODEL | `entity_type` | string | 否 | 如 `ALL` |
| VIEW.MODEL | `ids` | array | 否 | 默认 `[]` |
| VIEW.MODEL | `camera` | object | 否 | 如 `{"projection":"PERSPECTIVE"}` |
| VIEW.MODEL | 输出 | — | — | `{ view_id, artifact_id }` |
| VIEW.DEFORMED_MODEL | `load_case` | string | 是 | 如 `COMB1` |
| VIEW.DEFORMED_MODEL | `scale` | number | 否 | 如 20 |
| VIEW.REACTION | `load_case` | string | 是 | 如 `DEAD` |
| VIEW.REACTION | `node_ids` | array[integer] | 是 | 如 `[1,2,3]` |
| VIEW.DISPLACEMENT | `load_case` | string | 是 | 如 `COMB1` |
| VIEW.DISPLACEMENT | `component` | string | 是 | 如 `UZ` |
| VIEW.DISPLACEMENT | `scale` | number | 否 | 如 20 |
| VIEW.STRESS | `load_case` | string | 是 | 如 `COMB1` |
| VIEW.STRESS | `component` | string | 是 | 如 `VM` |
| VIEW.FORCE | `load_case` | string | 是 | 如 `COMB1` |
| VIEW.FORCE | `component` | string | 是 | 如 `MZ` |
| VIEW.MODE_SHAPE | `mode` | integer | 是 | 如 1 |
| VIEW.MODE_SHAPE | `scale` | number | 否 | 如 20 |

**View Output（第 1804–1825 行）**：结果可为 artifact / image / scene descriptor / native view state；MCP Response 不应把超大二进制内容塞进 JSON，优先返回
```json
{ "view_id": "view_001", "artifact_id": "artifact_001", "mime_type": "image/png" }
```
**Capability**：`VIEW.*`（第 86 节矩阵，即 `VIEW.MODEL`、`VIEW.DEFORMED_MODEL`、… 同名 Capability）。

---

### B.7 Tool 7 — `engineering_result`（第 1829–2031 行）

**定位**：读取已经完成的工程分析结果。默认 Risk LOW / Execution SYNC / Permission `RESULT_READ`。
> 未给出 Tool Definition JSON；Tool-Level Schema 见 §116。

| Operation | 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| RESULT.NODE.DISPLACEMENT | `node_ids` | array[integer] | 是 | 如 `[2]` |
| RESULT.NODE.DISPLACEMENT | `load_case` | string | 是 | 如 `COMB1` |
| RESULT.NODE.DISPLACEMENT | 输出 | — | — | `data:[{node_id,ux,uy,uz}]`（示例 uz=-0.015） |
| RESULT.NODE.REACTION | `node_ids` | array[integer] | 是 | 如 `[1]` |
| RESULT.NODE.REACTION | `load_case` | string | 是 | 如 `DEAD` |
| RESULT.NODE.REACTION | 输出 | — | — | `data:[{node_id,fx,fy,fz,mx,my,mz}]` |
| RESULT.ELEMENT.FORCE | `element_ids` | array[integer] | 是 | 如 `[100]` |
| RESULT.ELEMENT.FORCE | `load_case` | string | 是 | 如 `COMB1` |
| RESULT.ELEMENT.FORCE | 输出 | — | — | `data:[{element_id,n,vy,vz,mx,my,mz}]` |
| RESULT.ELEMENT.STRESS | `element_ids` | array[integer] | 是 | 如 `[100]` |
| RESULT.ELEMENT.STRESS | `load_case` | string | 是 | 如 `COMB1` |
| RESULT.MODE.SHAPE | `mode` | integer | 是 | 如 1；输出 `{mode,frequency,nodes:[]}` |
| RESULT.ANALYSIS.SUMMARY | `analysis_task_id` | string | 是 | 如 `task_001`；输出 `{status,analysis_type,load_cases,warnings,result_sets}` |

**Preconditions（第 1995–2013 行）**：analysis completed / requested result set exists / result capability supported。若分析尚未完成 → `STRUCTAI-5000` 或明确返回 `RESULT_NOT_READY`，但必须映射到统一 StructAI Error Contract。
**Pagination（第 2017–2029 行）**：`{ "data": [], "pagination": { "has_more": true, "next_cursor": "..." } }`。
**Capability**：`RESULT.*`。
---

### B.8 Tool 8 — `engineering_design`（第 2033–2243 行）

**定位**：工程设计、规范验算、优化。默认 Risk HIGH / Execution ASYNC / Permission `DESIGN_EXECUTE`；修改设计参数/优化结果可能需要 `DESIGN_MODIFY` + `MODEL_WRITE`。
> 未给出 Tool Definition JSON；Tool-Level Schema 见 §117。

| Operation | 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| DESIGN.STEEL | `element_ids` | array[integer] | 是 | 如 `[100]` |
| DESIGN.STEEL | `code` | string | 是 | 如 `GB50017` |
| DESIGN.STEEL | `combination` | string | 否 | 如 `DESIGN_COMB1` |
| DESIGN.STEEL | `options` | object | 否 | `check_stability` / `check_strength`（布尔） |
| DESIGN.STEEL | 输出 | — | — | `{element_id, utilization_ratio:0.82, status:"PASS", checks:{strength:0.71, stability:0.82}}` |
| DESIGN.CONCRETE | `element_ids` | array[integer] | 是 | 如 `[200]` |
| DESIGN.CONCRETE | `code` | string | 是 | 如 `GB50010` |
| DESIGN.CONCRETE | `combination` | string | 否 | 如 `DESIGN_COMB1` |
| DESIGN.CONCRETE | `options` | object | 否 | `crack` / `strength` / `serviceability`（布尔） |
| DESIGN.FOUNDATION | `foundation_ids` | array[string] | 是 | 如 `["F001"]` |
| DESIGN.FOUNDATION | `code` | string | 是 | 如 `GB50007` |
| DESIGN.FOUNDATION | `options` | object | 否 | `bearing_capacity` / `settlement` / `sliding` / `overturning`（布尔） |
| DESIGN.CODE_CHECK | `entity_type` | string | 是 | 如 `ELEMENT` |
| DESIGN.CODE_CHECK | `entity_ids` | array[integer] | 是 | 如 `[100,101]` |
| DESIGN.CODE_CHECK | `code` | string | 是 | 如 `GB50017` |
| DESIGN.CODE_CHECK | `checks` | array[string] | 是 | `STRENGTH` / `STABILITY` / `SERVICEABILITY` |
| DESIGN.OPTIMIZE | `entity_ids` | array[integer] | 是 | 如 `[100,101]` |
| DESIGN.OPTIMIZE | `objective` | string | 是 | 如 `MIN_STEEL_WEIGHT` |
| DESIGN.OPTIMIZE | `constraints` | object | 否 | `max_utilization` / `max_displacement` |
| DESIGN.OPTIMIZE | `variables` | array[object{name,allowed[]}] | 否 | 如 `section` 候选截面列表 |
| DESIGN.OPTIMIZE | `apply` | boolean | 否 | **默认 false**；true 需 DESIGN_MODIFY + MODEL_WRITE + confirmation |

规范计算公式**不写死在 MCP Tool**，由 Design Adapter / Design Engine / Registry 实现（第 2097–2099 行）。
**Design Dry Run（第 2202–2224 行）**：DESIGN.OPTIMIZE 必须支持 `apply=false`；`apply=true` 需 high-risk confirmation + audit + lock。
**Design Output（第 2232–2242 行）**：`{ "status":"PASS", "utilization_ratio":0.82, "governing_check":"STABILITY", "warnings":[], "recommendations":[] }`；不得要求 AI Client 理解 MIDAS/ETABS 原始设计结果格式。
**Capability**：`DESIGN.STEEL` / `DESIGN.CONCRETE` / `DESIGN.FOUNDATION` / `DESIGN.CODE_CHECK` / `DESIGN.OPTIMIZATION`（注意 OPTIMIZE 的 Capability 名为 `DESIGN.OPTIMIZATION`）。

---

### B.9 Tool 9 — `engineering_analysis`（第 2246–2490 行）

**定位**：执行工程分析计算。默认 Risk HIGH / Execution ASYNC / Permission `ANALYSIS_EXECUTE`。
> 未给出 Tool Definition JSON；Tool-Level Schema 见 §118。

| Operation | 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| ANALYSIS.STATIC | `load_cases` | array[string] | 是 | 如 `["DEAD","LIVE","WIND"]` |
| ANALYSIS.STATIC | `combinations` | array[string] | 否 | 如 `["COMB1"]` |
| ANALYSIS.STATIC | 输出 | — | — | `{ "task_id":"task_001", "status":"QUEUED" }` |
| ANALYSIS.MODAL | `modes` | integer | 是 | 如 12 |
| ANALYSIS.MODAL | `solver_options` | object | 否 | 求解器选项 |
| ANALYSIS.SEISMIC | `direction` | array[string] | 是 | 如 `["X","Y"]` |
| ANALYSIS.SEISMIC | `cases` | array[string] | 是 | 如 `["EQX","EQY"]` |
| ANALYSIS.SEISMIC | `damping_ratio` | number | 否 | 如 0.05 |
| ANALYSIS.SPECTRUM | `spectrum_id` | string | 是 | 如 `SPEC_X` |
| ANALYSIS.SPECTRUM | `direction` | string | 是 | 如 `X` |
| ANALYSIS.SPECTRUM | `damping_ratio` | number | 否 | 如 0.05 |
| ANALYSIS.BUCKLING | `modes` | integer | 是 | 如 10 |
| ANALYSIS.BUCKLING | `load_case` | string | 是 | 如 `COMB1` |
| ANALYSIS.TIME_HISTORY | `case` | string | 是 | 如 `TH_X` |
| ANALYSIS.TIME_HISTORY | `duration` | number | 是 | 如 20 |
| ANALYSIS.TIME_HISTORY | `time_step` | number | 是 | 如 0.01 |
| ANALYSIS.TIME_HISTORY | `record` | string | 是 | 如 `artifact_001` |
| ANALYSIS.NONLINEAR | `load_case` | string | 是 | 如 `NL1` |
| ANALYSIS.NONLINEAR | `solver` | object{max_steps,tolerance} | 否 | 如 `{max_steps:100, tolerance:1e-6}` |

**Preconditions（第 2377–2386 行）**：project active / model exists / software connected / model valid / required loads exist / analysis capability supported / no incompatible running task / software instance lock acquired。
**Postconditions（第 2398–2415 行）**：analysis completed / result set available / result metadata persisted / task completed；部分结果必须标 `PARTIAL`，不得错误标记 `COMPLETED`。
**Task Response（第 2421–2431 行）**：立即返回 `{ "success": true, "execution": { "mode":"ASYNC", "status":"QUEUED", "task_id":"task_001" } }`。
**Progress（第 2436–2458 行）**：0 → VALIDATING → QUEUED → RUNNING → PROCESSING → 100 → COMPLETED；progress 来源必须是 Task Engine，Tool Handler 不得自造进度。
**Cancellation（第 2462–2488 行）**：MCP cancel → TaskEngine.cancel() → CANCEL_REQUESTED → Adapter.cancel() → CANCELLED；若原生软件不支持真实取消，CANCEL_REQUESTED 可保持到软件真实结束，不得伪造 CANCELLED。
**Capability**：`ANALYSIS.STATIC` / `ANALYSIS.MODAL` / `ANALYSIS.SEISMIC` / `ANALYSIS.SPECTRUM` / `ANALYSIS.BUCKLING` / `ANALYSIS.TIME_HISTORY` / `ANALYSIS.NONLINEAR`。
---

## D. 各类矩阵（原样整理）

### D.1 Tool Operation Matrix（第 2492–2539 行）

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

### D.2 Capability Requirements for Build（第 2543–2572 行）

| Build Operation | 所需 Capability |
|---|---|
| `BUILD.COLUMN` | MODEL.NODE.WRITE, MODEL.ELEMENT.WRITE, MODEL.MATERIAL.WRITE, MODEL.SECTION.WRITE, MODEL.BOUNDARY.WRITE |
| `BUILD.FRAME` | MODEL.NODE.WRITE, MODEL.ELEMENT.WRITE, MODEL.MATERIAL.WRITE, MODEL.SECTION.WRITE |
| `BUILD.STEEL_FRAME` | MODEL.NODE.WRITE, MODEL.ELEMENT.WRITE, MODEL.MATERIAL.WRITE, MODEL.SECTION.WRITE, MODEL.BOUNDARY.WRITE |

（文档仅列此 3 个 Build Operation 的 capability 要求；其余 Build Operation 未单列。）

### D.3 Lock Requirements（第 2576–2633 行）

| 类别 | 锁策略 |
|---|---|
| Query | 通常 `READ` |
| Assign | `WRITE` |
| Delete | `EXCLUSIVE` |
| Build | `WRITE`；复杂 Build 如果涉及全模型重构 → `EXCLUSIVE` |
| Analysis | 默认 `Software Instance = WRITE / EXCLUSIVE`，`Model = READ`；具体 Adapter 可以提升锁级别 |
| Design | 读取 `Model = READ`；如果 `apply=true` → `Model = WRITE` |

### D.4 Idempotency Requirements（第 2637–2661 行）

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

唯一键：`tenant_id + idempotency_key`；重复请求必须避免重复创建模型、重复分析或重复删除。

### D.5 Confirmation Requirements（第 2665–2694 行）

默认需要 Confirmation：`MODEL.*.DELETE`、`DESIGN.OPTIMIZE + apply=true`、高风险模型重构。
Confirmation Token 必须：server generated / short-lived / bound to user / bound to tenant / bound to operation / bound to resource。不能使用固定 `CONFIRM`、`YES`、`true` 作为安全确认。

### D.6 Dry Run Matrix（第 2698–2726 行）

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

Dry Run 必须：validate / authorize / check capability / check preconditions / produce plan；但不得 modify model。

### D.7 Batch Matrix（第 2730–2742 行）

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

### D.8 Transaction Matrix（第 2746–2774 行）

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

Rollback 优先级：Native Transaction → Snapshot / Restore → Compensating Actions → Best Effort。不能声称不支持回滚的 Adapter「已回滚」。
---

## E. Canonical Model 与 Schema Versioning

### E.1 Canonical Model（第 2778–2800 行）
所有模型相关 Tool 必须尽可能使用 Canonical 实体：`Node`、`Element`、`Material`、`Section`、`Boundary`、`Load`、`Group`；结果侧为 `Analysis`、`Result`、`Design`。**Adapter 负责 Native → Canonical。**

### E.2 Schema Versioning（第 2804–2820 行）
示例 Schema URI：`structai://schema/model/node/v1`、`structai://schema/model/node/v2`。规则：`v1 never overwrite`、`v2 new version`。Operation 指向明确 Schema URI。

### E.3 相关版本/解析规则
- §119 Operation Schema Resolution（第 3641–3672 行）：Tool → Operation Registry → `input_schema` → Schema Registry → JSON Schema Validation。例：`engineering_analysis + ANALYSIS.STATIC → structai://schema/analysis/static/v1`。
- §120（第 3676–3696 行）：禁止 `Tool Schema = 所有软件 API Schema`；正确链路 Tool Schema → Operation Schema → Canonical Engineering Schema → Adapter Transform → Native API Schema。
- §121 Response Schema Resolution（第 3700–3714 行）：Native Response → Adapter Normalize → Canonical Result → Operation `output_schema` → Tool Response。
- §134 Tool Contract Versioning（第 4014–4040 行）：Tool `engineering_analysis v2.0` / Schema `structai://schema/tool/engineering-analysis/v2`；Schema 变化 `v1 → v2`，不覆盖旧版本。
- §135 Backward Compatibility（第 4044–4067 行）：Old Tool Contract → Version Resolver → Current Operation；不兼容返回 `STRUCTAI-1100` 并给出 `expected_schema` / `received_schema`。

---

## F. Tool-Level JSON Schema（第 3238–3637 行）

§109 总则：MCP `inputSchema` 可以使用统一外壳，但必须进一步限定 Operation。以下为 9 个 Tool 的 schema（原样摘录；`engineering_analysis` 为 §109 的示例，§118 又给出一次同构版本）。

### F.1 `structai://schema/tool/engineering-analysis/v2`（§109，第 3244–3281 行；§118 第 3602–3636 行同构）
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "structai://schema/tool/engineering-analysis/v2",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "operation": { "type": "string", "enum": ["ANALYSIS.STATIC","ANALYSIS.MODAL","ANALYSIS.SEISMIC","ANALYSIS.SPECTRUM","ANALYSIS.BUCKLING","ANALYSIS.TIME_HISTORY","ANALYSIS.NONLINEAR"] },
    "parameters": { "type": "object" },
    "context": { "$ref": "structai://schema/mcp/execution-context-input/v1" },
    "idempotency_key": { "type": ["string", "null"] },
    "confirmation_token": { "type": ["string", "null"] },
    "dry_run": { "type": "boolean" }
  },
  "required": ["operation"]
}
```
> §109 版本含 `additionalProperties:false` 与 `$schema`；§118 版本仅保留 `$id` + `required:["operation","idempotency_key"]`、`idempotency_key:{type:"string"}`。两者并存于文档。

### F.2 `engineering_doc`（§110，第 3289–3323 行）
```json
{ "$id": "structai://schema/tool/engineering-doc/v2", "type": "object",
  "properties": {
    "operation": { "type": "string", "enum": ["NEW","OPEN","SAVE","SAVE_AS","CLOSE","INFO"] },
    "parameters": { "type": "object" },
    "context": { "$ref": "structai://schema/mcp/execution-context-input/v1" },
    "idempotency_key": { "type": ["string", "null"] },
    "confirmation_token": { "type": ["string", "null"] },
    "dry_run": { "type": "boolean" } },
  "required": ["operation"] }
```

### F.3 `engineering_model_query`（§111，第 3329–3356 行）
```json
{ "$id": "structai://schema/tool/engineering-model-query/v2", "type": "object",
  "properties": {
    "operation": { "type": "string", "enum": ["MODEL.QUERY","MODEL.NODE.QUERY","MODEL.ELEMENT.QUERY","MODEL.MATERIAL.QUERY","MODEL.SECTION.QUERY","MODEL.BOUNDARY.QUERY","MODEL.LOAD.QUERY","MODEL.GROUP.QUERY"] },
    "parameters": { "type": "object" },
    "context": { "$ref": "structai://schema/mcp/execution-context-input/v1" } },
  "required": ["operation"] }
```
（该 Tool schema **不含** idempotency_key / confirmation_token / dry_run。）

### F.4 `engineering_model_assign`（§112，第 3362–3395 行）
```json
{ "$id": "structai://schema/tool/engineering-model-assign/v2", "type": "object",
  "properties": {
    "operation": { "type": "string", "enum": ["MODEL.NODE.CREATE","MODEL.NODE.UPDATE","MODEL.ELEMENT.CREATE","MODEL.ELEMENT.UPDATE","MODEL.MATERIAL.ASSIGN","MODEL.SECTION.ASSIGN","MODEL.BOUNDARY.ASSIGN","MODEL.LOAD.ASSIGN"] },
    "parameters": { "type": "object" },
    "context": { "$ref": "structai://schema/mcp/execution-context-input/v1" },
    "idempotency_key": { "type": ["string", "null"] },
    "dry_run": { "type": "boolean" } },
  "required": ["operation"] }
```

### F.5 `engineering_model_delete`（§113，第 3401–3440 行）
```json
{ "$id": "structai://schema/tool/engineering-model-delete/v2", "type": "object",
  "properties": {
    "operation": { "type": "string", "enum": ["MODEL.NODE.DELETE","MODEL.ELEMENT.DELETE","MODEL.LOAD.DELETE","MODEL.BOUNDARY.DELETE","MODEL.GROUP.DELETE","MODEL.MATERIAL.DELETE","MODEL.SECTION.DELETE"] },
    "parameters": { "type": "object" },
    "context": { "$ref": "structai://schema/mcp/execution-context-input/v1" },
    "idempotency_key": { "type": "string" },
    "confirmation_token": { "type": "string" },
    "dry_run": { "type": "boolean" } },
  "required": ["operation", "idempotency_key", "confirmation_token"] }
```

### F.6 `engineering_model_build`（§114，第 3446–3491 行）
```json
{ "$id": "structai://schema/tool/engineering-model-build/v2", "type": "object",
  "properties": {
    "operation": { "type": "string", "enum": ["BUILD.NODE_GRID","BUILD.BEAM","BUILD.COLUMN","BUILD.FRAME","BUILD.TRUSS","BUILD.SLAB","BUILD.WALL","BUILD.FOUNDATION","BUILD.STEEL_FRAME","MODEL.COPY","MODEL.MOVE","MODEL.MIRROR","MODEL.PATTERN","MODEL.GENERATE_GRID"] },
    "parameters": { "type": "object" },
    "context": { "$ref": "structai://schema/mcp/execution-context-input/v1" },
    "idempotency_key": { "type": "string" },
    "confirmation_token": { "type": ["string", "null"] },
    "dry_run": { "type": "boolean" } },
  "required": ["operation", "idempotency_key"] }
```

### F.7 `engineering_view`（§115，第 3497–3523 行）
```json
{ "$id": "structai://schema/tool/engineering-view/v2", "type": "object",
  "properties": {
    "operation": { "type": "string", "enum": ["VIEW.MODEL","VIEW.DEFORMED_MODEL","VIEW.REACTION","VIEW.DISPLACEMENT","VIEW.STRESS","VIEW.FORCE","VIEW.MODE_SHAPE"] },
    "parameters": { "type": "object" },
    "context": { "$ref": "structai://schema/mcp/execution-context-input/v1" } },
  "required": ["operation"] }
```

### F.8 `engineering_result`（§116，第 3529–3554 行）
```json
{ "$id": "structai://schema/tool/engineering-result/v2", "type": "object",
  "properties": {
    "operation": { "type": "string", "enum": ["RESULT.NODE.DISPLACEMENT","RESULT.NODE.REACTION","RESULT.ELEMENT.FORCE","RESULT.ELEMENT.STRESS","RESULT.MODE.SHAPE","RESULT.ANALYSIS.SUMMARY"] },
    "parameters": { "type": "object" },
    "context": { "$ref": "structai://schema/mcp/execution-context-input/v1" } },
  "required": ["operation"] }
```

### F.9 `engineering_design`（§117，第 3560–3596 行）
```json
{ "$id": "structai://schema/tool/engineering-design/v2", "type": "object",
  "properties": {
    "operation": { "type": "string", "enum": ["DESIGN.STEEL","DESIGN.CONCRETE","DESIGN.FOUNDATION","DESIGN.CODE_CHECK","DESIGN.OPTIMIZE"] },
    "parameters": { "type": "object" },
    "context": { "$ref": "structai://schema/mcp/execution-context-input/v1" },
    "idempotency_key": { "type": "string" },
    "confirmation_token": { "type": ["string", "null"] },
    "dry_run": { "type": "boolean" } },
  "required": ["operation", "idempotency_key"] }
```
---

## G. 所有出现的 MIDAS / Native API 引用（穷尽）

本节列出子文档 tools5（第 1–4568 行）中出现的**全部**软件原生接口引用。全部集中在少数几处，且大多为**反面示例**（禁止暴露）。

| # | 行号 | 出处小节 | 原文 | 性质 |
|---|---|---|---|---|
| 1 | 79 | §2.1 Tool ≠ API | `engineering_analysis → /anal/STATIC` | 禁止的反例（MIDAS 分析接口路径 `/anal/STATIC`） |
| 2 | 80 | §2.1 Tool ≠ API | `engineering_model_query → /db/NODE` | 禁止的反例（MIDAS DB 接口 `/db/NODE`） |
| 3 | 373 | §8 Error Contract | `"provider": "MIDAS"` | 诊断模式 `cause` 中的 provider 名 |
| 4 | 2242 | §72 Design Output | 「不得要求 AI Client 理解 MIDAS/ETABS 的原始设计结果格式」 | 约束 |
| 5 | 3018 | §101 Error E2E | `"software": "CIVIL NX"`，`"version": "2026"` | 错误 details 中的软件名（MIDAS Civil NX 2026） |
| 6 | 3127–3129 | §105 Capability Discovery | `MIDAS API` / `ETABS COM` / `OpenSees Script` | AI Client 不需要知道的东西 |
| 7 | 3157–3165 | §106 Multi-Software Example | `MIDAS：Adapter ↓ REST ↓ /anal/STATIC` | MIDAS 走 REST，端点 `/anal/STATIC` |
| 8 | 3167–3175 | §106 | `ETABS：Adapter ↓ COM ↓ RunAnalysis` | ETABS 走 COM，方法 `RunAnalysis` |
| 9 | 3177–3185 | §106 | `OpenSees：Adapter ↓ SCRIPT ↓ analyze` | OpenSees 走脚本，命令 `analyze` |
| 10 | 3815 | §125 Permission 与 Capability 的区别 | `MIDAS 2026 supports ANALYSIS.STATIC` | 能力判定示例 |
| 11 | 3891–3893 | §128 AI Client 最小知识模型 | `MIDAS Endpoint` / `ETABS COM` / `OpenSees Script` | 不需要理解的内容 |
| 12 | 3912 | §129 AI Tool Description 建议 | `"Call MIDAS /db/NODE and /db/ELEM"` | 禁止写入 description 的反例（含表/接口 `/db/NODE`、`/db/ELEM`） |
| 13 | 3929 | §130 Operation Description 建议 | `POST /db/NODE` | 不得暴露的 HTTP 方法与接口 |
| 14 | 3930 | §130 Operation Description 建议 | `POST /db/ELEM` | 不得暴露的 HTTP 方法与接口 |
| 15 | 4324 | §146 Adapter Independence Test | `MIDAS Adapter` | Mock Adapter 之后替换为 MIDAS Adapter |
| 16 | 4533 | §152 最终原则 | `AI Client 永远不需要知道 MIDAS、ETABS、SAP2000、ANSYS、OpenSees 的 Native API` | 原则 |

**穷尽性结论**
- 出现的**接口路径**仅 3 个：`/anal/STATIC`（行 79、3164）、`/db/NODE`（行 80、3912、3929）、`/db/ELEM`（行 3912、3930）。**没有**出现 `/doc/...`、`/ope/...`、`/view/...`、`/post/TABLE`、`/design/...` 形式的路径，也没有出现独立表代码（如 `NODE`、`ELEM`、`BEAM` 作为 MIDAS 表代码）。
- 出现的 **HTTP 方法**仅 `POST`（行 3929、3930），且均为「不得暴露」的反例。
- 其余软件引用：`ETABS`（行 2242、3128、3167、3892）、`ETABS COM` + `RunAnalysis`（行 3172–3174）、`OpenSees`（行 3129、3177、3893）+ 脚本命令 `analyze`（行 3184）、`SAP2000`/`ANSYS`（仅行 4533 列举）、`CIVIL NX`（行 3018）、`MIDAS 2026`（行 3815）。
- §107 Native API Mapping（第 3195–3209 行）用**中性**名称描述 BUILD.COLUMN 的展开链：`CREATE_NODE → CREATE_NODE → CREATE_ELEMENT → ASSIGN_MATERIAL → ASSIGN_SECTION → ASSIGN_BOUNDARY`（非 MIDAS 专有路径）。
- §105/§128/§129/§130 的一致要求：Native API 与 MIDAS/ETABS 端点**不得**进入 Tool Discovery、Tool description、Operation description 或 AI Client 的知识模型。

---

## H. E2E 场景：Generic AI Client 第一条 E2E（第 2879–3001 行）

**Prompt（第 2883 行）**
> 创建一个高度 6m 的 Q355B H400×400×13×21 钢柱，底部固定，顶部施加 500kN 轴压力。完成静力分析，并返回顶部节点位移和钢柱设计利用率。

**期望调用序列（第 2887–2893 行）**：`1 BUILD.COLUMN` → `2 MODEL.LOAD.ASSIGN` → `3 ANALYSIS.STATIC` → `4 RESULT.NODE.DISPLACEMENT` → `5 DESIGN.STEEL`

**Step 1 — Build（tool: engineering_model_build，第 2901–2920 行）**
```json
{ "operation": "BUILD.COLUMN",
  "parameters": { "height": 6, "material": "Q355B",
    "section": { "type":"H","height":400,"width":400,"web_thickness":13,"flange_thickness":21 },
    "boundary": { "base": "FIXED" } },
  "idempotency_key": "column-demo-001" }
```
**Step 2 — Load（tool: engineering_model_assign，第 2924–2937 行）**
```json
{ "operation": "MODEL.LOAD.ASSIGN",
  "parameters": { "case":"AXIAL","target_type":"NODE","target_ids":[2], "load": { "fz": -500000 } },
  "idempotency_key": "load-demo-001" }
```
**Step 3 — Analysis（tool: engineering_analysis，第 2941–2949 行）**
```json
{ "operation": "ANALYSIS.STATIC", "parameters": { "load_cases": ["AXIAL"] },
  "idempotency_key": "analysis-demo-001" }
```
**Step 4 — Result（tool: engineering_result，第 2953–2961 行）**
```json
{ "operation": "RESULT.NODE.DISPLACEMENT", "parameters": { "node_ids": [2], "load_case": "AXIAL" } }
```
**Step 5 — Design（tool: engineering_design，第 2965–2973 行）**
```json
{ "operation": "DESIGN.STEEL", "parameters": { "element_ids": [100], "code": "GB50017" },
  "idempotency_key": "design-demo-001" }
```
**Expected E2E Output（第 2982–2998 行）**
```json
{ "model": { "column_element_id": 100, "top_node_id": 2 },
  "analysis": { "status": "COMPLETED" },
  "displacement": { "uz": -0.015 },
  "design": { "utilization_ratio": 0.82, "status": "PASS" } }
```
**约束（第 3001 行）**：实际数值必须来自真实 Adapter / Mock Adapter，不能由 Tool Contract 写死。

**相关 E2E**
- §101 Error E2E（第 3009–3025 行）：软件不支持非线性 → `STRUCTAI-3000` / type `CAPABILITY_ERROR`，details = `{software:"CIVIL NX", version:"2026", capability:"ANALYSIS.NONLINEAR"}`，`retryable:false`。
- §102 Async Task E2E（第 3034–3066 行）：Tool Call → Task CREATED → VALIDATING → QUEUED → RUNNING → PROCESSING → COMPLETED；首次返回 `{execution:{mode:"ASYNC",status:"QUEUED",task_id:"task_001"}}`，随后 Client 通过 Task Query / MCP Progress 跟进。
- §103 Task Failure（第 3074–3100 行）：软件超时 → `STRUCTAI-2300` / type `SOFTWARE_TIMEOUT` / `retryable:true`，Task 状态 `TIMEOUT`，不得直接标 `FAILED`（除非 Task Engine 按 Retry Policy 最终归类）。
- §104 Task Recovery（第 3108–3118 行）：server restart → unfinished task → lease inspection → RECOVERING → resume / requeue / fail；Tool Contract 不承担恢复逻辑。
---

## I. 补充契约速查（子文档内其余强制条款）

| 主题 | 行 | 内容 |
|---|---|---|
| Tool Discovery | 2824–2849 | `initialize → tools/list`；每个 Tool 至少暴露 `name` / `description` / `inputSchema`；建议通过 description/registry 让 Client 获知 risk 与 operation domain；**底层 Native API 不进入 Tool Discovery** |
| Tool Handler | 2853–2875 | `async def handler(arguments)` → `ToolRequest.model_validate` → `execution_service.execute(tool_name=..., request=...)`；禁止 Handler 写 SQL / 选 Adapter / 算 RBAC / 做 Task worker / 直接调 Native API |
| Operation Contract | 3215–3234 | Operation Registry 必存 14 字段：name, tool, risk_level, execution_mode, input_schema, output_schema, required_permissions, required_capabilities, transactional, rollback_supported, dry_run_supported, recovery_policy, preconditions, postconditions |
| Warning Contract | 3718–3742 | Warning 不作为 Error；`STRUCTAI-W100` Deprecated API Mapping / `W110` Partial Capability / `W120` Engineering Warning / `W130` Result Partial / `W140` Optimization Did Not Improve |
| Partial Result | 3746–3766 | `success:true` + `warnings:[{code:"STRUCTAI-W130"}]` + `metadata.partial=true`；**不得把缺失数据静默填成 0** |
| Retry Rules | 3770–3792 | 可 Retry：`STRUCTAI-2000`、`STRUCTAI-2300`、部分 `STRUCTAI-6000`；不可 Retry：`1100`、`1200`、`1300`、`3000`、`4000`、`4100`、`4200`；具体策略由 Operation Registry / Adapter 决定 |
| Permission vs Capability | 3796–3832 | Permission = 用户是否有权；Capability = 当前软件是否能做；有权但软件不支持 → `STRUCTAI-3000` |
| Resource Access vs Permission | 3836–3848 | 两者必须同时成立 |
| Confirmation vs Permission | 3852–3870 | `permission = confirmation` 不可替代 |
| Security Boundary | 3935–3955 | 每次调用必须有 request_id / trace_id / authenticated identity / tenant / operation / resource；高风险另需 confirmation / audit / idempotency / lock |
| Observability | 3959–3987 | 记录 timestamp, trace_id, request_id, task_id, user_id, tenant_id, project_id, tool, operation, software, adapter, duration, status, error_code；禁止记录 password / API key / token / private key |
| Audit | 3991–4010 | 必须 Audit：`MODEL.*.DELETE`、`BUILD.*`、`ANALYSIS.*`、`DESIGN.*`；建议 Audit：`MODEL.*.ASSIGN`、`DOCUMENT.SAVE`、`DOCUMENT.SAVE_AS`；Query/View 不要求高风险 Audit 但仍可 Trace |
| Tool Registration | 4071–4087 | `tool_registry.list_tools()` → `mcp.register_tool(name, description, input_schema=schema_registry.resolve(...), handler=tool_dispatcher.dispatch)`；Tool Registry 是唯一 Tool Source of Truth |
| Tool Dispatcher | 4091–4109 | `registry.resolve_tool` → `ToolRequest.model_validate` → `execution_service.execute` |
| Operation Dispatcher | 4113–4128 | `operation_registry.resolve(tool.name, request.operation)`；Operation 不属于当前 Tool → `STRUCTAI-1000` |
| Capability Resolution | 4132–4146 | 逐个 `capability_resolver.require(software_instance_id, capability)`；缺失 → `STRUCTAI-3000` |
| 测试矩阵（客户端） | 4150–4178 | 必须测 `tools/list` + 9 Tool；每 Tool 至少 8 类：valid request / invalid schema / permission denied / capability denied / resource denied / duplicate request / timeout / adapter error |
| 安全测试矩阵 | 4182–4201 | 14 项：Forged user_id / tenant_id / role / permission、Cross-tenant model、Cross-project model、Expired session、Revoked session、Confirmation replay、Confirmation wrong operation、Confirmation wrong resource、Idempotency race、Lock bypass、Native error secret leakage |
| 并发/锁/幂等/恢复测试 | 4205–4299 | 并发 UPDATE 必须一成功一 `STRUCTAI-1300`；`BUILD.FRAME` 持锁期间 `MODEL.NODE.UPDATE` 阻塞至 COMPLETED/FAILED/CANCELLED 并释放 Lock；同 tenant+key+operation 并发 → one execution / one reused result；恢复后只能存在一个有效 Task execution identity |
| Adapter 独立性 | 4303–4327 | Mock Adapter 必须完整支持 `BUILD.COLUMN` / `MODEL.LOAD.ASSIGN` / `ANALYSIS.STATIC` / `RESULT.NODE.DISPLACEMENT` / `DESIGN.STEEL`；替换为 MIDAS Adapter 后 AI Client 不修改 |
| 第二软件验收 | 4331–4346 | 9 Tools / Tool Schema / AI Client / Task Engine 均不得变更，否则须做 Core abstraction review |
| Definition of Done | 4350–4377 | 24 项勾选清单（9 Tools registered、version、inputSchema、Operation schema/permission/capability、Risk、Execution mode、Pre/Postconditions、Dry-run、Transaction、Recovery、Idempotency、Lock、Confirmation policy、Unified response/errors、Pagination、Batch、Audit、Trace、Progress、Cancellation） |
| 冻结清单 | 4381–4485 | §149 Final Frozen Tool List = 9 Tool；§150 Final Frozen Operation List = 9 Tool 的 Operation 树（doc 6 + query 8 + assign 8 + delete 7 + build 14 + view 7 + result 6 + design 5 + analysis 7 = **68 个 Operation 条目**） |
| 与 Core 文档关系 | 4489–4519 | 不得改变 Authentication / IdentityContext / Tenant isolation / Resource Resolver / Execution Pipeline / Task Engine / Resource Lock / Idempotency / Adapter Architecture / MCP transport / Audit / Trace |
| 最终原则 | 4523–4565 | 9 Tool 是 AI Client 看到的稳定工程语义接口；Operation 是 Tool 内部工程动作；Capability 表示软件是否具备；Adapter 把 Operation 转成具体软件 API；AI Client 永不需要知道 MIDAS/ETABS/SAP2000/ANSYS/OpenSees 的 Native API |

### 读到的行范围
本次精读覆盖第 1–4568 行（含第 4568 行空行）；第 4569 行 `# 完整收录：tools15` 起为下一子文档，未在本报告范围内。全文件共 9543 行。
