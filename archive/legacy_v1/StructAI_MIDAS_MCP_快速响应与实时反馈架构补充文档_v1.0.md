# StructAI｜MIDAS MCP 快速响应与实时反馈架构补充文档 V1.0

> ⚠️ **非规范性文档（NON-NORMATIVE）** —— 本文件已归档至 `archive/legacy_v1/`，
> 属 StructAI 早期（V1）规范草案 / 实测记录，**不作为开发依据，不作为准则**。
> 开发唯一依据：`docs/01`–`docs/06`（V2 规范）· `docs/07`（开发方案与任务续接）· `registry/`（机器可读端点注册表）。

> 本文为《StructAI 多结构工程软件一体化 MCP 完整开发文档 V1.0》的独立补充文档。
>
> 本文只补充“快速响应 + 命令执行状态 + 结果持续反馈给 StructAI”这一执行层能力。主架构文档继续作为产品、软件、连接、Adapter、Registry、工程模型、设计、图形和计算书的主规范；后续调整继续通过独立补充文档维护。

---

# 1. 核心目标

StructAI MCP 必须满足：

```text
StructAI
   │
   │ MCP 命令
   ▼
MCP Server
   │
   ├─ 快速校验
   ├─ 生成 Request ID
   ├─ 下发命令
   └─ 快速 ACK
          │
          ▼
       Job/Worker
          │
          ▼
      MIDAS Adapter
          │
          ▼
       MIDAS 软件
          │
          ▼
     Result / Error
          │
          ▼
    Feedback Manager
          │
          ▼
       StructAI
```

必须保证：

- 短命令快速返回真实结果。
- 长任务不长期阻塞 MCP 请求。
- 命令执行后，状态持续反馈。
- 最终结果必须反馈给 StructAI。
- 错误必须反馈给 StructAI。
- 即使 Push 通知丢失，也可以通过 Job ID 恢复状态。
- 不允许伪造 MIDAS 内部不存在的进度。

---

# 2. 执行模式

所有请求统一分三种：

## 2.1 FAST

适用于：

```text
NODE 查询
ELEM 查询
MATL 查询
SECT 查询
CONS 查询
项目状态
小规模 DB 读写
普通配置
```

流程：

```text
Request
→ Validate
→ MIDAS
→ Parse
→ Response
```

默认同步完成。

---

## 2.2 ASYNC

适用于：

```text
大量节点
大量单元
大量荷载
大规模结果提取
VIEW 截图
复杂 OPE
```

流程：

```text
Request
→ ACK
→ Job
→ Worker
→ MIDAS
→ Result
→ Feedback
```

---

## 2.3 LONG

适用于：

```text
DOC.ANAL
模态
屈曲
地震
时程
非线性
施工阶段
设计
优化
计算书
```

统一使用：

```text
Job + Event + Result
```

---

# 3. 三个核心 ID

每一次命令执行至少生成三个 ID。

## Request ID

代表 StructAI 发起的一次请求：

```text
REQ-20260922-000001
```

## Job ID

代表一个异步执行任务：

```text
JOB-20260922-000001
```

## Operation ID

代表一次实际 MIDAS 操作：

```text
OP-20260922-000001
```

完整关系：

```text
Request
  │
  └── request_id
        │
        └── job_id
              │
              └── operation_id
                    │
                    └── MIDAS API
```

---

# 4. ACK 与最终结果必须分离

异步命令收到后立即返回：

```json
{
  "success": true,
  "accepted": true,
  "request_id": "REQ-001",
  "job_id": "JOB-001",
  "status": "QUEUED"
}
```

这只表示：

> StructAI 的命令已经被 MCP 接受并进入执行链。

不能表示：

> MIDAS 已经计算完成。

最终结果单独反馈：

```json
{
  "type": "final",
  "job_id": "JOB-001",
  "status": "SUCCEEDED",
  "result_id": "RSET-00001"
}
```

---

# 5. Job 生命周期

标准生命周期：

```text
CREATED
 ↓
QUEUED
 ↓
DISPATCHING
 ↓
RUNNING
 ↓
WAITING / PROGRESS
 ↓
PARSING
 ↓
RESULT_READY
 ↓
SUCCEEDED
```

异常：

```text
RUNNING → FAILED
RUNNING → CANCEL_REQUESTED → CANCELLED
RUNNING → TIMEOUT_DETECTED → RECOVERY
```

未知状态：

```text
UNKNOWN
```

不得因为 MCP 自身超时就直接认定 MIDAS 计算失败。

---

# 6. Execution Event

所有执行过程产生 Event：

```text
RECEIVED
VALIDATING
QUEUED
DISPATCHING
SENDING
SENT
RUNNING
PROGRESS
WAITING
PARSING
RESULT_READY
SUCCEEDED
FAILED
CANCELLED
TIMEOUT
```

事件格式：

```json
{
  "event_id": "EVT-00001",
  "request_id": "REQ-001",
  "job_id": "JOB-001",
  "operation_id": "OP-001",
  "event_type": "RUNNING",
  "status": "RUNNING",
  "progress": null,
  "stage": "ANALYSIS",
  "message": "MIDAS analysis is running",
  "timestamp": "2026-09-22T10:00:00+08:00"
}
```

---

# 7. Feedback 分层

反馈统一分成：

```text
ACK
STATE
PROGRESS
RESULT
ERROR
FINAL
```

## ACK

```json
{
  "type": "ack",
  "request_id": "REQ-001",
  "job_id": "JOB-001",
  "accepted": true
}
```

## STATE

```json
{
  "type": "state",
  "job_id": "JOB-001",
  "status": "RUNNING"
}
```

## PROGRESS

```json
{
  "type": "progress",
  "job_id": "JOB-001",
  "stage": "ANALYSIS",
  "progress": null,
  "message": "Solving structural model"
}
```

如果 MIDAS 没有可靠百分比，不允许伪造 35%、62% 等数值。

## RESULT

```json
{
  "type": "result",
  "job_id": "JOB-001",
  "result_id": "RSET-00001",
  "status": "RESULT_READY"
}
```

## ERROR

```json
{
  "type": "error",
  "job_id": "JOB-001",
  "code": "CONNECTION_LOST",
  "message": "MIDAS connection lost",
  "recoverable": true,
  "retryable": false
}
```

## FINAL

```json
{
  "type": "final",
  "job_id": "JOB-001",
  "status": "SUCCEEDED",
  "result_id": "RSET-00001"
}
```

---

# 8. 双通道反馈

生产版必须支持两条反馈路径：

```text
             MCP
              │
       ┌──────┴──────┐
       ▼             ▼
   Push/Event     Job Query
       │             │
       └──────┬──────┘
              ▼
           StructAI
```

### Push

实时发送事件。

### Query

StructAI 根据：

```text
job_id
request_id
```

查询当前状态和历史 Event。

Push 是实时通道。

Query 是可靠兜底。

---

# 9. 为什么必须保存 Event

不能出现：

```text
MCP 重启
→ Event 丢失
→ StructAI 不知道 MIDAS 做了什么
```

因此所有 Job Event 必须持久化。

建议：

```sql
CREATE TABLE job_events (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    request_id TEXT,
    operation_id TEXT,
    event_type TEXT NOT NULL,
    status TEXT,
    progress REAL,
    stage TEXT,
    message TEXT,
    payload_json TEXT,
    created_at TEXT NOT NULL
);
```

---

# 10. Job 当前状态表

历史 Event 和当前状态分开。

```sql
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    request_id TEXT,
    project_id TEXT,
    software_id TEXT,
    connection_id TEXT,
    type TEXT,
    status TEXT,
    progress REAL,
    stage TEXT,
    result_id TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT,
    updated_at TEXT,
    started_at TEXT,
    finished_at TEXT
);
```

`jobs` 用于快速查询当前状态。

`job_events` 用于恢复完整历史。

---

# 11. Worker 架构

```text
MCP Request
     │
     ▼
Command Router
     │
 ┌───┴──────────────┐
 │                  │
 ▼                  ▼
FAST             ASYNC/LONG
 │                  │
 ▼                  ▼
Sync Executor    Job Queue
                    │
                    ▼
                  Worker
                    │
                    ▼
               MIDAS Adapter
                    │
                    ▼
                  MIDAS
```

---

# 12. Fast Path

FAST 请求不应该经过 Job Queue。

标准路径：

```text
MCP Tool
→ Session Context
→ Registry Resolve
→ Validation
→ HTTP
→ Parse
→ Response
```

避免不必要的数据库、队列和后台调度开销。

---

# 13. Long Path

LONG 请求：

```text
MCP Tool
→ Create Job
→ ACK
→ Queue
→ Worker
→ MIDAS
→ Result Parser
→ Result Store
→ Event
→ FINAL
```

MCP 主请求不长期等待 MIDAS。

---

# 14. Analysis 必须异步

`DOC.ANAL` 属于 LONG。

标准流程：

```text
midas_doc(ANAL)
      │
      ▼
Create Analysis Job
      │
      ▼
快速返回 ACK
      │
      ▼
Worker 获取 Connection Lock
      │
      ▼
执行 MIDAS ANAL
      │
      ▼
等待 MIDAS
      │
      ▼
检查结果
      │
      ▼
ResultSet
      │
      ▼
反馈 StructAI
```

分析过程中不得自动重复执行。

---

# 15. Connection Lock

同一个 MIDAS Connection 默认：

```text
写入 / 修改 / 删除 / 分析
```

串行执行。

例如：

```text
CIVIL-01
Worker = 1
```

不同连接可以并行：

```text
CIVIL-01 → Job A
GEN-01   → Job B
```

这样实现：

```text
同一模型安全
+
不同软件并行
```

---

# 16. Read / Write / Analysis 并发等级

以后可优化为：

```text
READ
  → 可以有限并发

WRITE
  → 默认排他

ANALYSIS
  → 默认排他
```

第一版直接：

```text
同一 Connection 单 Worker
```

先保证稳定，再增加读并发。

---

# 17. 自动从同步升级为异步

MCP 内部根据 Registry 与运行时情况自动判断：

```text
execution.mode = FAST
```

但出现：

```text
数据规模过大
预估执行时间过长
结果集过大
```

可以：

```text
FAST
 ↓
AUTO ASYNC
```

立即返回 Job。

LLM 不负责判断这种底层性能问题。

---

# 18. Registry 增加执行配置

Endpoint Definition 增加：

```yaml
execution:
  mode: FAST
  timeout_ms: 30000
  retryable: true
  idempotent: true
```

分析：

```yaml
execution:
  mode: LONG
  timeout_ms: 3600000
  retryable: false
  idempotent: false
```

---

# 19. ResultStore

无论同步还是异步，重要计算结果必须进入统一 ResultStore。

例如：

```text
POST/TABLE
POST/TEXT
DB Result
Analysis Result
Design Result
```

最后都统一：

```text
ResultSet
ResultItem
Evidence
```

---

# 20. ResultSet 必须绑定完整上下文

```json
{
  "result_id": "RSET-001",
  "project_id": "P001",
  "model_version": 23,
  "software_id": "civil-main",
  "connection_id": "conn-civil",
  "job_id": "JOB-001",
  "source_endpoint": "POST.TABLE.BEAMFORCE"
}
```

因此不会把不同 MIDAS、不同工程、不同模型版本的结果混起来。

---

# 21. 结果不能一次性全部塞回 StructAI

例如几十万条 BeamForce：

错误：

```text
MIDAS
→ MCP
→ StructAI Context
```

正确：

```text
MIDAS
→ Result Parser
→ ResultStore
→ Summary
→ StructAI
```

StructAI 默认获得：

```text
最大值
最小值
控制组合
控制构件
结果数量
单位
异常数量
```

需要详细数据时再分页查询。

---

# 22. Result Summary

例如：

```json
{
  "result_id": "RSET-001",
  "summary": {
    "count": 128934,
    "max": 425.3,
    "min": -387.2,
    "critical_count": 12,
    "unit": "kN.m",
    "critical_member": "102",
    "critical_combination": "LC23"
  }
}
```

StructAI 首先拿到 Summary。

---

# 23. 快速响应不是牺牲可靠性

不能为了快而：

```text
跳过 Validation
跳过 Audit
跳过 ResultStore
跳过 Model Version
```

正确模式：

```text
快速 ACK
+
可靠后台执行
+
实时 Event
+
结果落库
+
最终反馈
```

---

# 24. 错误统一反馈

错误必须带：

```text
code
message
stage
recoverable
retryable
request_id
job_id
```

例如：

```json
{
  "code": "ANALYSIS_FAILED",
  "message": "MIDAS analysis failed",
  "stage": "ANALYSIS",
  "recoverable": false,
  "retryable": false,
  "request_id": "REQ-001",
  "job_id": "JOB-001"
}
```

---

# 25. 错误分类

统一：

```text
VALIDATION_ERROR
REGISTRY_ERROR
PRODUCT_UNSUPPORTED
CONNECTION_ERROR
AUTH_ERROR
HTTP_ERROR
MIDAS_ERROR
JOB_ERROR
ANALYSIS_FAILED
PARSER_ERROR
RESULT_ERROR
DESIGN_ERROR
REPORT_ERROR
TIMEOUT
CANCELLED
UNKNOWN
```

---

# 26. Retry 规则

普通查询：

```text
允许有限 Retry
```

幂等写入：

```text
依据 Registry 的 idempotent 标记
```

分析：

```text
禁止自动重复分析
```

分析失败必须先：

```text
Diagnosis
→ Determine State
→ Confirm Retry Safe
```

---

# 27. Connection Lost

如果运行过程中连接断开：

```text
RUNNING
 ↓
CONNECTION_LOST
```

不要直接：

```text
FAILED
```

必须检查：

```text
MIDAS Process
API 状态
Job 状态
是否已经完成分析
```

再决定：

```text
SUCCEEDED
FAILED
UNKNOWN
```

---

# 28. Timeout

MCP 超时不等于 MIDAS 已停止。

正确流程：

```text
TIMEOUT_DETECTED
 ↓
检查 MIDAS 状态
 ↓
检查 Job
 ↓
判断：
  SUCCESS
  RUNNING
  FAILED
  UNKNOWN
```

---

# 29. Cancel

长任务必须支持：

```text
Cancel Job
```

状态：

```text
RUNNING
 ↓
CANCEL_REQUESTED
 ↓
STOPPING
 ↓
CANCELLED
```

如果 MIDAS 无法即时停止，则不能伪造已经停止，继续监控直到可以确定最终状态。

---

# 30. MCP / StructAI 重启恢复

如果 StructAI 重启：

```text
重新连接 MCP
→ 获取 Active Jobs
→ 读取 Job 状态
→ 读取 Events
→ 恢复 Result 引用
```

如果 MCP 重启：

```text
加载 Jobs
→ 检查 RUNNING / QUEUED
→ 检查 MIDAS
→ 恢复或标记 UNKNOWN
```

绝不能简单把所有任务标记 FAILED。

---

# 31. Multi-MIDAS 与 Job 绑定

每个 Job 必须保存：

```text
software_id
connection_id
project_id
model_version
```

例如：

```text
JOB-001
  → CIVIL NX
  → conn-civil-main
  → Project P001
  → Model v23
```

因此用户后来切换到 GEN NX，不会改变已经运行 Job 的目标。

---

# 32. Feedback Manager

核心接口：

```go
type FeedbackManager interface {
    Publish(event JobEvent) error
    PublishResult(result ResultEnvelope) error
    PublishError(err ErrorEnvelope) error
}
```

职责：

```text
更新 Job
保存 Event
推送 StructAI
保存 Result
保存 Error
```

---

# 33. Execution 模块

正式目录增加：

```text
internal/execution/
├── classifier.go
├── queue.go
├── worker.go
├── scheduler.go
├── lock.go
├── event.go
├── feedback.go
├── executor.go
├── recovery.go
└── cancel.go
```

---

# 34. Dispatcher 调整

```go
func Dispatch(ctx context.Context, req Request) Response {

    normalized := Normalize(req)

    endpoint := registry.Resolve(normalized.Endpoint)

    Validate(normalized, endpoint)

    mode := classifier.Classify(endpoint, normalized)

    switch mode {

    case ModeFast:
        return executeSync(normalized, endpoint)

    case ModeAsync, ModeLong:
        job := jobs.Create(normalized, endpoint)
        queue.Submit(job)

        return Ack(job)
    }

    return Error(...)
}
```

---

# 35. 完整建模反馈示例

StructAI：

```text
创建 10000 个节点。
```

MCP 立即：

```text
ACK
REQ-001
JOB-001
```

然后 Event：

```text
VALIDATING
QUEUED
RUNNING
```

如果有可靠阶段信息：

```text
WRITING_NODES
```

完成：

```text
RESULT_READY
```

最终：

```json
{
  "status": "SUCCEEDED",
  "created": 10000,
  "failed": 0,
  "result_id": "RSET-001"
}
```

整个过程 StructAI 都可以知道状态。

---

# 36. 完整分析反馈示例

StructAI：

```text
执行结构分析。
```

MCP：

```text
ACK
JOB-2026
```

Event：

```text
MODEL_CHECK
ANALYSIS RUNNING
RESULT_EXTRACTION
RESULT_READY
SUCCEEDED
```

最终：

```json
{
  "status": "SUCCEEDED",
  "result_id": "RSET-2026",
  "summary": {
    "max_displacement": 32.8,
    "max_story_drift": 0.00182,
    "critical_findings": 3
  }
}
```

---

# 37. 完整计算书反馈示例

```text
Report Request
 ↓
ACK
 ↓
JOB
 ↓
COLLECT_RESULTS
 ↓
BUILD_FIGURES
 ↓
BUILD_DOCX
 ↓
BUILD_PDF
 ↓
SUCCEEDED
```

最终：

```json
{
  "status": "SUCCEEDED",
  "artifacts": [
    {
      "type": "DOCX",
      "path": "reports/StructAI_Report.docx"
    },
    {
      "type": "PDF",
      "path": "reports/StructAI_Report.pdf"
    }
  ]
}
```

---

# 38. 快速响应性能目标

第一阶段工程目标：

```text
Registry Resolve：毫秒级
Local Validation：毫秒级
ACK：尽可能 < 200ms
普通小查询：通常 < 1s
```

受 MIDAS、网络、模型规模影响的任务：

```text
大批量建模
分析
结果提取
设计
优化
计算书
```

全部走 Job，不占用 MCP 长连接等待。

以上是工程目标，不承诺所有环境的固定 SLA。

---

# 39. 最终架构

```text
                         StructAI
                            │
                            │ MCP
                            ▼
                   ┌─────────────────┐
                   │    MCP Server   │
                   │                 │
                   │  4 MCP Tools    │
                   └────────┬────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │  Dispatcher  │
                     └──────┬───────┘
                            │
                 ┌──────────┴──────────┐
                 │                     │
                 ▼                     ▼
             FAST PATH            ASYNC / LONG
                 │                     │
                 ▼                     ▼
          Sync Executor            Job Manager
                                       │
                                     Queue
                                       │
                                     Worker
                                       │
                          ┌────────────┴────────────┐
                          ▼                         ▼
                    MIDAS Adapter              Event Store
                          │                         │
                          ▼                         │
                       MIDAS                      Job State
                          │                         │
                          ▼                         │
                    Result Parser                   │
                          │                         │
                          ▼                         │
                     ResultStore                    │
                          └────────────┬────────────┘
                                       ▼
                                Feedback Manager
                                       │
                         ┌─────────────┴────────────┐
                         ▼                          ▼
                       Push                     Query
                         │                          │
                         └─────────────┬────────────┘
                                       ▼
                                   StructAI
```

---

# 40. 与主开发文档的边界

主文档继续负责：

```text
多结构工程软件
SoftwareProfile
ConnectionProfile
Adapter
Solver
Endpoint Registry
MCP 四工具
Project
Model
Analysis
Design
Graphics
Report
```

本补充文档负责：

```text
Request ID
Job ID
Operation ID
Execution Mode
Fast Path
Async Path
Long Path
Job Queue
Worker
Connection Lock
Event
ACK
Push
Query
Result Feedback
Error Feedback
Retry
Timeout
Cancel
Recovery
快速响应
```

后续如果要增加：

```text
WebSocket
SSE
分布式 Worker
Redis Queue
多机调度
GPU/CPU Worker
高并发读
任务优先级
```

继续新建补充文档，不修改本文件的核心原则。

---

# 41. 最终验收标准

## 快速响应

```text
□ MCP 命令快速被接受
□ FAST 不进入后台队列
□ LONG 不阻塞主 MCP 请求
□ ACK 包含 Request ID / Job ID
```

## 执行反馈

```text
□ RECEIVED
□ VALIDATING
□ QUEUED
□ RUNNING
□ 阶段状态
□ RESULT_READY
□ FINAL
```

## 结果

```text
□ result_id
□ summary
□ findings
□ artifact
□ error
```

## 可靠性

```text
□ Event 持久化
□ Job 持久化
□ Push 丢失可 Query
□ MCP 重启可恢复
□ StructAI 重启可恢复
```

## 多软件

```text
□ Job 绑定 software_id
□ Job 绑定 connection_id
□ 不同 MIDAS 实例可并行
□ 同一实例有执行锁
```

## 长任务

```text
□ ANAL 异步
□ 设计异步
□ 优化异步
□ 计算书异步
□ 不盲目自动 Retry
```

---

# 42. 最终原则

StructAI MCP 的执行层最终固定为：

> **快速接受、立即确认、后台执行、持续反馈、结果持久化、最终回传、异常可恢复。**

不是：

```text
发送命令
→ 等待
→ 最后一次性告诉 AI
```

而是：

```text
StructAI
  │
  │ Command
  ▼
MCP
  │
  ├── ACK ───────────────→ StructAI
  │
  ├── Event ─────────────→ StructAI
  │
  ├── Progress/Stage ────→ StructAI
  │
  ├── Result ────────────→ StructAI
  │
  └── Error ─────────────→ StructAI
```

最终形成：

# “命令下发快、执行过程透明、结果反馈完整、失败可追踪、任务可恢复。”

本补充文档作为 StructAI MCP 的**执行与反馈层规范**。
