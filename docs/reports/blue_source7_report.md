# StructAI MCP Server V2.0 — 精读报告：子文档 blue（第六份） + source7（第七份）

源文件：`G:\MMCP\docs\02_STRUCTAI_MCP_V2_CORE_IMPLEMENTATION.md`
- 子文档 **blue**：第 4674–9487 行（第 4674 行 `# 完整收录：blue`；正文标题在第 4676–4678 行）
- 子文档 **source7**：第 9488–13462 行（第 9488 行 `# 完整收录：source7`）
- 下一份 source9 从第 13463 行开始（边界已确认）。

---

## A. 章节地图

### A-1. blue（第六份，File-Level Implementation Blueprint，第 1–145 节）

| 节 | 标题 | 一句话要点 |
|---|---|---|
| 1 | Implementation Baseline | 冻结目标：可独立运行、软件无关的 Core；第一阶段 Adapter 用 Mock；禁止 `midas_*()` 进入 Core。 |
| 2 | Python Runtime | Python>=3.12、asyncio、SQLAlchemy AsyncIO+SQLite+aiosqlite、官方 MCP SDK、FastAPI/Uvicorn、Pydantic v2、Alembic、argon2-cffi、pytest；不强制 Redis/Celery/MQ/PG。 |
| 3 | Project Directory | `structai-mcp/` 最终目录树。 |
| 4 | pyproject.toml | 基础依赖与 dev 依赖清单。 |
| 5 | Configuration Layer | settings.py 读环境变量；不得在代码保存密码/API Key/Token/私钥/MIDAS Key。 |
| 6 | Domain Layer | Domain 不依赖 FastAPI/MCP SDK/SQLAlchemy/HTTPX/MIDAS。 |
| 7 | app/domain/enums.py | RiskLevel/ExecutionMode/TaskStatus/LockMode；还需 Permission/Capability/TaskPriority/ResourceType/ArtifactType/AuditResult/AuthenticationMethod。 |
| 8 | app/domain/value_objects.py | RequestIdentity + ResourceRef/VersionRef/Pagination/IdempotencyKey/SoftwareRef/ProjectRef/ModelRef/DocumentRef；必须不可变。 |
| 9 | app/domain/entities.py | 核心实体清单 + 模型对象（EngineeringNode/Element/…/Design）；Canonical Model 不绑定供应商。 |
| 10 | app/domain/errors.py | StructAIError 及派生异常 + 完整错误码 STRUCTAI-1000…7000。 |
| 11 | app/domain/protocols.py | Repository/UnitOfWork/ArtifactStorage Protocol。 |
| 12 | Database Layer | infrastructure/database 目录。 |
| 13 | database/base.py | `class Base(DeclarativeBase)`。 |
| 14 | database/session.py | AsyncEngine/async_sessionmaker/AsyncSession。 |
| 15 | ORM Models | 按文件拆分；禁止 3000 行单文件。 |
| 16 | Repository Layer | 只负责持久化，不做 RBAC/Adapter/MCP/Task 业务。 |
| 17 | UnitOfWork | SQLAlchemyUnitOfWork；一业务事务=一 UoW。 |
| 18 | Registry | software/capability/operation/schema/api 五 registry。 |
| 19 | SoftwareRegistry | Vendor/Product/Version/Instance 查询。 |
| 20 | CapabilityRegistry | MODEL.*/ANALYSIS.*/RESULT.*/DESIGN.* 能力清单。 |
| 21 | OperationRegistry | OperationDefinition（12 字段）+ 注册全部冻结 Operation。 |
| 22 | SchemaRegistry | schemas/ 目录 + `structai://schema/...` ID；Draft 2020-12。 |
| 23 | API Registry | 映射字段（software/product/version/operation/protocol/method/path/…）；MIDAS CIVIL NX 2026 `POST /anal/STATIC` 示例。 |
| 24 | Authentication | application/security 目录。 |
| 25 | AuthenticationService | authenticate()->IdentityContext；Argon2id；失败计数/锁定/审计。 |
| 26 | IdentityContext | frozen dataclass；user_id/tenant_id/roles 不得由 AI Client 提交后信任。 |
| 27 | Effective Permission | User→Global→Tenant→Project Role→Resource ACL→Explicit Deny；AI 取 User∩Agent，不得扩大。 |
| 28 | Resource Resolver | resolver.py 解析 instance/project/model/document→各 Context。 |
| 29 | ExecutionContext | SoftwareContext/ProjectContext/ExecutionContext；可扩 model_id 等。 |
| 30 | Validation Pipeline | 冻结顺序 Input→Schema→Engineering→Permission→Confirmation→Capability→Execution + 完整运行时链。 |
| 31 | Engineering Validation | engineering_validator.py：几何/节点/坐标/连接/材料/截面/荷载/边界；≠Schema Validation。 |
| 32 | Preconditions / Postconditions | NODE.CREATE、ANALYSIS.STATIC 前后置条件示例。 |
| 33 | Confirmation | LOW 免 / MEDIUM 策略 / HIGH 默认 / CRITICAL 必须；Token 不得永久有效。 |
| 34 | Capability Resolver | supports()；Manifest+Runtime；带缓存，重连/改版本重验。 |
| 35 | Resource Lock | READ+READ ok；READ+WRITE、WRITE+WRITE blocked；EXCLUSIVE blocks all；桌面默认 SERIAL。 |
| 36 | Optimistic Concurrency | version + expected_version；冲突 STRUCTAI-1300。 |
| 37 | Idempotency | tenant_id+key；原子插入+唯一约束；禁止 SELECT→if not exists→INSERT。 |
| 38 | Adapter Framework | adapters/ base+mock+plugins。 |
| 39 | EngineeringSoftwareAdapter | ABC：connect/disconnect/health_check/get_version/get_capabilities/execute/cancel/normalize_error。 |
| 40 | Adapter Responsibilities | 负责 10 项；不负责 MCP/RBAC/Global Task/Audit/AI/UI。 |
| 41 | Adapter Manifest | name/vendor/product/supported_versions/capabilities/protocols。 |
| 42 | Plugin Loading | entry-points structai.adapters；Core 不 import midas。 |
| 43 | Mock Adapter | 必须实现的 Operation 清单（NODE/ELEMENT CRUD、ASSIGN、BUILD.COLUMN/BEAM、ANALYSIS.STATIC、RESULT、DESIGN.STEEL）。 |
| 44 | Canonical Model | EngineeringNode/Element 最小结构 + 扩展。 |
| 45 | Mock Adapter BUILD.COLUMN | 输入/内部步骤/返回 node_ids,element_ids。 |
| 46 | Task Engine | application/task 目录（10 文件）。 |
| 47 | Task State Machine | CREATED→…→COMPLETED；异常 FAILED/TIMEOUT/CANCELLED/RETRYING/RECOVERING。 |
| 48 | TaskEngine | submit/get/cancel/retry/recover。 |
| 49 | Scheduler | asyncio.Queue；priority/concurrency/serialization。 |
| 50 | Worker | 取任务→Lease→RUNNING→Lock→Pipeline→Adapter→Progress→Result→COMPLETED→释放。 |
| 51 | Task Lease | lease_owner/lease_until/last_heartbeat。 |
| 52 | Recovery | 重启查未完成→查 lease→RECOVERING→REQUEUE/RESUME/FAIL；不得留 RUNNING。 |
| 53 | Cancellation | CANCEL_REQUESTED→adapter.cancel()；不支持则记录真实状态，不得伪造 CANCELLED。 |
| 54 | Task DAG | Step 依赖满足后才执行。 |
| 55 | Artifact Storage | storage/ base+local+manager；put/get/delete。 |
| 56 | LocalFilesystemStorage | ./data/artifacts/；DB 存 id/backend/key/mime/size/checksum。 |
| 57 | Document Service | NEW/OPEN/SAVE/SAVE_AS/CLOSE/INFO；不知道 MIDAS/ETABS/SAP2000。 |
| 58 | Event Bus | events/ bus+in_process；事件清单。 |
| 59 | Notification Service | 预留 MCP Notification/Webhook/WS/UI/Email；一期只 InProcess。 |
| 60 | Quota / Rate Limit | quota.py；维度/指标；一期内存限流。 |
| 61 | Observability | tracing/metrics/audit。 |
| 62 | Structured Logging | 结构化字段；绝不输出 password/API key/token/private key/secret。 |
| 63 | Trace | Span 清单；先 request_id/trace_id/日志再扩 OTel。 |
| 64 | Metrics | structai_* 指标清单。 |
| 65 | Audit | 字段 + Hash Chain；普通用户不得删除。 |
| 66 | Backup / Restore | backup/restore/integrity-check；恢复后 Integrity→Registry→Task Recovery。 |
| 67 | MCP Layer | interfaces/mcp 目录。 |
| 68 | MCP Server | server.py 初始化/注册 9 Tool/绑定 Dispatcher/Transport；不写业务逻辑。 |
| 69 | MCP Context | 客户端只能提供 instance/project/model/document id，不能覆盖身份。 |
| 70 | Unified ToolRequest | operation/parameters/context/idempotency_key/confirmation_token/dry_run。 |
| 71 | Unified Response | 同步/异步统一响应示例。 |
| 72 | Tool Dispatcher | dispatch()；tool→Tool Registry→Operation Registry→Execution Service。 |
| 73 | Tool Base Class | BaseEngineeringTool(ABC)。 |
| 74 | 9 MCP Tools | tools/ 下 9 文件清单。 |
| 75 | engineering_doc | NEW/OPEN/SAVE/SAVE_AS/CLOSE/INFO；DOCUMENT_READ/WRITE；MEDIUM。 |
| 76 | engineering_model_query | MODEL(.NODE/ELEMENT/MATERIAL/SECTION/BOUNDARY/LOAD/GROUP).QUERY；SYNC/LOW/READ；分页。 |
| 77 | engineering_model_assign | NODE/ELEMENT CREATE/UPDATE + ASSIGN；需 MODEL_WRITE；idempotency/version/dry_run/transaction。 |
| 78 | engineering_model_delete | *.DELETE；HIGH/ASYNC；需 MODEL_DELETE；通常需确认。 |
| 79 | engineering_model_build | BUILD.* + MODEL.COPY/MOVE/MIRROR/PATTERN/GENERATE_GRID；HIGH/ASYNC。 |
| 80 | engineering_view | VIEW.*；LOW/SYNC。 |
| 81 | engineering_result | RESULT.*；LOW/SYNC；大结果分页。 |
| 82 | engineering_design | DESIGN.STEEL/CONCRETE/FOUNDATION/CODE_CHECK/OPTIMIZE；HIGH/ASYNC；DESIGN_EXECUTE(+DESIGN_MODIFY)。 |
| 83 | engineering_analysis | ANALYSIS.STATIC/MODAL/SEISMIC/SPECTRUM/BUCKLING/TIME_HISTORY/NONLINEAR；HIGH/ASYNC；ANALYSIS_EXECUTE。 |
| 84 | Tool Schema | 统一 JSON Schema Draft 2020-12。 |
| 85 | Operation Dispatch | registry.get + operation.tool 校验 + execution_service.execute。 |
| 86 | Application Execution Service | ExecutionService.execute 串联 12 环节。 |
| 87 | Adapter Resolution | adapter_resolver.py 解析链。 |
| 88 | API Mapping | ANALYSIS.STATIC→MIDAS REST POST /anal/STATIC / ETABS COM / OpenSees SCRIPT。 |
| 89 | Native Response Normalization | Adapter 转 Canonical Result。 |
| 90 | Pagination | {data,pagination{has_more,next_cursor}}；禁止一次返回百万节点。 |
| 91 | Batch | items[]；atomic / non_atomic。 |
| 92 | Dry Run | CREATE/UPDATE/ASSIGN/BUILD/DELETE/DESIGN；返回 DRY_RUN/changes/warnings。 |
| 93 | Transaction / Rollback | 支持事务操作清单；native 无真事务用 compensating actions；失败 STRUCTAI-5300。 |
| 94 | Health | /livez /readyz /health；单个 MIDAS 不可用不得令 Core ready=false。 |
| 95 | HTTP Management API | 非 MCP Tool；interfaces/http。 |
| 96 | MCP Transport | 一期 STDIO，二期 Streamable HTTP。 |
| 97 | STDIO | python -m app.main；日志必须 stderr。 |
| 98 | Streamable HTTP | MCP SDK 能力；业务仍走 ToolDispatcher。 |
| 99 | MCP Progress | progress→MCP Notification；cancel→TaskEngine→Adapter。 |
| 100 | Seed Data | scripts/ 5 文件；seed tenant/admin/roles/permissions/9 tools/ops/caps/mock。 |
| 101 | Mock Software | Vendor=StructAI / Product=Mock Engineering Software / Version=1.0；能力清单。 |
| 102 | Alembic | 禁止运行时 create_all()。 |
| 103 | Test Architecture | unit/contract/integration/recovery/security/concurrency/e2e。 |
| 104 | Unit Tests | Domain/Value Objects/State Machine/RBAC/Capability/Schema/Validation/Lock/Idempotency/Operation Registry。 |
| 105 | Contract Tests | 所有 Adapter 同一 Contract。 |
| 106 | Integration Tests | SQLite/Repository/UoW/Task/Adapter/Artifact/Event/Audit。 |
| 107 | Security Tests | 未认证/无权限/跨 Tenant/跨 Project/AI 提权/过期 Session/错误密码/锁定/Confirmation bypass。 |
| 108 | Concurrency Tests | READ/READ、READ/WRITE、WRITE/WRITE、同 key CREATE、version 冲突；证明不重复创建/覆盖/死锁。 |
| 109 | Recovery Tests | Worker crash/restart/timeout/Lock orphan/Lease expiry。 |
| 110 | E2E Test | 第一条完整 E2E 流程（Connect…DESIGN.STEEL）。 |
| 111 | Generic AI Client E2E | 自然语言→Tool Chain。 |
| 112 | E2E Acceptance | 15 项验收。 |
| 113 | Implementation Sequence | P0 Bootstrap…P12 Tests。 |
| 114 | First Runnable Milestone | 可执行 BUILD.COLUMN。 |
| 115 | Second Runnable Milestone | +QUERY/ASSIGN LOAD。 |
| 116 | Third Runnable Milestone | +ANALYSIS.STATIC。 |
| 117 | Fourth Runnable Milestone | +RESULT。 |
| 118 | Fifth Runnable Milestone | +DESIGN.STEEL。 |
| 119 | MIDAS Adapter 接入 | Core Alpha 后加 structai_midas/ 插件；Core 不修改。 |
| 120 | MIDAS Adapter 内部结构 | Operation→Adapter→API Registry→Native→Transform→Canonical；POST /anal/STATIC。 |
| 121 | Second Software Acceptance | 加第二软件不改 9 Tool/协议/Client/Task/Security。 |
| 122 | Dependency Direction | Interface→Application→Domain；禁止 Domain→SQLAlchemy/FastAPI/MCP/MIDAS。 |
| 123 | Application Container | app/container.py 组装依赖；禁止 global TaskEngine()。 |
| 124 | Application Bootstrap | main.py 启动顺序。 |
| 125 | Shutdown | SIGINT/SIGTERM；关闭顺序。 |
| 126 | Database Transaction Rules | DB 事务不得无限包含长 Native 调用。 |
| 127 | Native API Timeout | connect/request/analysis timeout→STRUCTAI-2300；Task 层 STRUCTAI-5100。 |
| 128 | Error Boundary | Native→Adapter→Application→MCP；不泄漏 traceback/Key/Authorization。 |
| 129 | Security Boundary | 任何 Tool 都不能绕过认证/RBAC/ACL。 |
| 130 | AI Engineering Agent | AI 属上层 Client；Core 不依赖具体 LLM。 |
| 131 | AI 权限模型 | UserPermission ∩ AgentPermission。 |
| 132 | Logging Rule | 允许/禁止字段。 |
| 133 | File-Level Definition | 每文件须答 13 问。 |
| 134 | Implementation Rules | Rule 1–10。 |
| 135 | Minimum Production Requirements | 进入 MIDAS 前的 47 项勾选清单。 |
| 136 | Acceptance Commands | venv/pip/alembic/seed/start/pytest/coverage。 |
| 137 | Core Alpha Acceptance | 启动→SQLite→Migration→Seed→MCP→Discover 9 Tools/Ops/Caps。 |
| 138 | Functional Acceptance | 9 个 Operation 完整通过。 |
| 139 | Security Acceptance | 7 条拒绝场景。 |
| 140 | Reliability Acceptance | 幂等/乐观锁/资源锁/恢复/超时/Adapter 断。 |
| 141 | Generic AI Client Acceptance | AI 不需知道 MIDAS/ETABS/SAP2000/OpenSees。 |
| 142 | Final Architecture | 架构总图。 |
| 143 | Final Definition of Done | 53 项 [✓] 完成判据。 |
| 144 | 第六份文档与前五份的关系 | 六份文档层层落地。 |
| 145 | 下一阶段 | 进入第七份（源码生成规范）。 |

### A-2. source7（第七份，Source-Level Implementation Specification，第 1–136 节）

| 节 | 标题 | 一句话要点 |
|---|---|---|
| 1 | 文档定位 | 已冻结上层设计清单；解决 Module→Class→Method→Parameter→Return→Exception→DB/Service→Test；不实现 MIDAS/CSI/ANSYS/OpenSees API。 |
| 2 | Core Alpha 源码目标 | 启动→SQLite→Migration→Seed→Registry→Mock Adapter→Task Engine→9 Tools；最小 E2E 8 步。 |
| 3 | 源码实现原则 | Domain First / 禁止反向依赖 / Tool Thin Handler / Adapter Isolation / Server Trust Boundary。 |
| 4 | 最终源码目录 | 完整目录树（含 container.py、dto/、services/model.py、result.py、mock/model_store.py、analysis.py、secrets/、locks/、notifications/ 等）。 |
| 5 | Configuration Source | settings.py 源码（含 task_default_timeout_seconds/lock_default_timeout_seconds/capability_cache_seconds）。 |
| 6 | Runtime Config | runtime_config.py（shutdown/task_poll/lease/heartbeat）。 |
| 7 | Logging | 结构化日志到 stderr，带 trace/request/task id。 |
| 8 | Domain Enum Source | 枚举源码（RiskLevel/ExecutionMode/TaskStatus/LockMode/ResourceType/AuthenticationMethod）。 |
| 9 | Domain Errors | StructAIError 源码 + 19 个派生异常清单。 |
| 10 | Execution Context | context.py 五个 frozen dataclass 源码。 |
| 11 | Tool DTO | ToolRequest/ToolResponse 源码。 |
| 12 | Task DTO | TaskResponse 源码。 |
| 13 | Operation Definition | OperationDefinition frozen dataclass（放 value_objects.py）。 |
| 14 | Database Base | Base(DeclarativeBase)。 |
| 15 | Database Session | create_database() 源码。 |
| 16 | UnitOfWork | SQLAlchemyUnitOfWork 源码。 |
| 17 | ORM Entity Rules | UUID PK + created_at/updated_at；可变资源 version；tenant 数据 tenant_id。 |
| 18 | ORM Model Minimum Set | 24 个 Model 类清单。 |
| 19 | Repository Contract | UserRepository 等 Protocol 源码。 |
| 20 | Authentication Service | authenticate() 7 步流程。 |
| 21 | Password Service | hash/verify；Argon2id。 |
| 22 | Session Service | create/validate/refresh/revoke/expire；有过期/可撤销/绑 User/Tenant。 |
| 23 | RBAC Service | has_permission(identity,permission,resource)。 |
| 24 | Effective Permission Service | Global+Tenant+Project Role+ACL-Deny→set[str]。 |
| 25 | Resource Resolver | resolve(context)；验证 Tenant/Project/Model/Document/Software。 |
| 26 | Lock Manager | ResourceLockManager.acquire/release。 |
| 27 | Lock Compatibility | READ+READ ALLOW；READ+WRITE/WRITE+WRITE DENY；EXCLUSIVE+ANY DENY。 |
| 28 | Idempotency Service | get_existing/reserve/complete；必须有唯一约束。 |
| 29 | Schema Validator | validate(schema_id,data)；错误 STRUCTAI-1100。 |
| 30 | Engineering Validator | 检查 Node/Element/Material/Section/Boundary/Load；工程规则与 JSON Schema 分离。 |
| 31 | Capability Resolver | require(instance_id,capability)；不存在 STRUCTAI-3000。 |
| 32 | Adapter Base | EngineeringSoftwareAdapter 源码。 |
| 33 | Adapter Manager | register/get_for_instance/health_check_all。 |
| 34 | Mock Adapter | 必须实现的操作清单（同 blue §43 略简）。 |
| 35 | Mock Model Store | MockModelStore 内存结构 + 线程/协程安全/自动 ID/版本控制。 |
| 36 | Mock Analysis | 接受合法模型→产生确定性测试结果；Mock Result ≠ 工程计算结果。 |
| 37 | Task State Machine | ALLOWED_TRANSITIONS 字典源码。 |
| 38 | Task Queue | TaskQueue put/get/shutdown；asyncio.Queue。 |
| 39 | Task Engine | submit/get/cancel/retry/recover。 |
| 40 | Task Worker | Queue.get→Lease→RUNNING→ExecutionService→Progress→COMPLETED/FAILED→Release。 |
| 41 | Lease Service | acquire/heartbeat/release/is_expired。 |
| 42 | Recovery Service | recover_unfinished_tasks() 查 QUEUED/RUNNING/PROCESSING/RECOVERING。 |
| 43 | Task Cancellation | CANCEL_REQUESTED→Adapter.cancel()。 |
| 44 | Progress Service | ProgressReporter.report()；范围 0–100。 |
| 45 | ExecutionService | execute(tool_name,operation,parameters,request,context)；执行顺序 14 步。 |
| 46 | Sync / Async Decision | Operation 决定 SYNC/ASYNC/STREAM（NODE.QUERY SYNC…DESIGN.STEEL ASYNC）。 |
| 47 | Document Service | new/open/save/save_as/close/info。 |
| 48 | Model Service | query_*/assign_*；Tool 不直接调 Repository。 |
| 49 | Result Service | Result query/pagination/normalization/artifact linking。 |
| 50 | Artifact Service | create/get。 |
| 51 | Local Storage | data/artifacts/<artifact_id>/<storage_key>；DB 只存 metadata。 |
| 52 | Event Bus | EventBus Protocol publish/subscribe；InProcessEventBus。 |
| 53 | Audit Service | record(context,action,resource,result)。 |
| 54 | Trace Service | request_id/trace_id 由 uuid4() 生成；子 Task 继承 trace_id。 |
| 55 | Metrics | 7 个计数器。 |
| 56 | MCP Base Tool | BaseEngineeringTool.handle() 返回 ToolResponse。 |
| 57 | MCP Context | MCPContext(request_id/trace_id/identity)；客户端只补 instance/project/model/document id。 |
| 58 | Tool Dispatcher | dispatch() 源码（registry.get + tool.handle）。 |
| 59 | Tool Implementation Pattern | handle→resolve operation→build ExecutionContext→ExecutionService→Unified Response。 |
| 60 | Engineering Doc Tool | class EngineeringDocTool，name=engineering_doc。 |
| 61 | Engineering Model Query Tool | class + 8 操作。 |
| 62 | Engineering Model Assign Tool | class + 8 操作。 |
| 63 | Engineering Model Delete Tool | class + 7 操作；HIGH/ASYNC。 |
| 64 | Engineering Model Build Tool | class + 14 操作。 |
| 65 | Engineering View Tool | class + 7 操作。 |
| 66 | Engineering Result Tool | class + 6 操作。 |
| 67 | Engineering Design Tool | class + 5 操作。 |
| 68 | Engineering Analysis Tool | class + 7 操作。 |
| 69 | Operation Seed | 全部 Operation 注册清单（按 9 Tool 分组）。 |
| 70 | Capability Seed | 全部 Capability 清单。 |
| 71 | Permission Seed | 12 个权限。 |
| 72 | Default Roles | system_admin/engineer/viewer/ai_agent 及权限映射。 |
| 73 | MCP Server | server.py 初始化顺序；不把 TaskEngine/RBAC/Repository 写入 Tool registration。 |
| 74 | Tool Registration | 注册 9 Tool，数量必须严格=9。 |
| 75 | Unified Error Response | error_response() 源码。 |
| 76 | MCP Error Boundary | 不泄漏 traceback/SQL/password hash/API key/Authorization/native secret。 |
| 77 | HTTP Health | /livez /readyz /health。 |
| 78 | Application Container | ApplicationContainer dataclass 字段清单。 |
| 79 | Startup | main.py 启动顺序 13 步。 |
| 80 | Shutdown | 7 步关闭顺序。 |
| 81 | Schema Files | schemas/ 目录树（common/model/analysis/result）。 |
| 82 | Node Schema | node v1 JSON Schema 源码。 |
| 83 | Column Build Schema | build/column JSON Schema 源码。 |
| 84 | Load Schema | load JSON Schema 源码；单位须在 Project/Model 明确。 |
| 85 | Result Schema | 位移 JSON Schema 源码。 |
| 86 | Operation Registration Matrix | 每 Operation 至少 12 字段；BUILD.COLUMN 示例。 |
| 87 | Operation Semantics | MODEL.NODE.CREATE / MODEL.NODE.DELETE / ANALYSIS.STATIC 语义。 |
| 88 | Operation Handler Rule | 不为每个 Operation 建独立 MCP Tool。 |
| 89 | Adapter Operation Mapping | operation_handlers 字典。 |
| 90 | Mock Adapter Build Column | build_column 伪代码。 |
| 91 | Mock Static Analysis | 流程；不宣称真实工程计算。 |
| 92 | Mock Steel Design | 返回 element_id/utilization/status。 |
| 93 | Test Fixture | conftest.py 提供项。 |
| 94 | Unit Test Matrix | 12 个测试文件。 |
| 95 | Adapter Contract Test | 7 个方法。 |
| 96 | Task Tests | submit…recovery 12 项。 |
| 97 | Security Tests | 9 个测试。 |
| 98 | Idempotency Tests | same key 同/异请求。 |
| 99 | Concurrency Tests | CREATE same key / UPDATE version。 |
| 100 | Lock Tests | 4 组合。 |
| 101 | Recovery Test | RUNNING→Crash→Lease Expired→Restart→RECOVERING→REQUEUE→RUNNING→COMPLETED。 |
| 102 | E2E Test Code Flow | test_full_engineering_flow 源码。 |
| 103 | Generic AI E2E | 自然语言→6 Operation。 |
| 104 | E2E Expected Result | 最终响应 + Audit/Trace/Task/Result 存在。 |
| 105 | Development Order | P01–P48 严格顺序清单。 |
| 106 | P01 Bootstrap | 先建文件；python -m app.main 可启停。 |
| 107 | P02 Config | Settings/RuntimeConfig/Logging；测试环境变量覆盖。 |
| 108 | P03 Domain | Enums/Errors/VO/Protocols/Events；不得引用 SQLAlchemy/FastAPI/MCP。 |
| 109 | P04 Database | Base/Engine/Session/ORM；验证 SQLite 连接。 |
| 110 | P05 Repository | 最小 6 个 Repository。 |
| 111 | P06 UnitOfWork | commit/rollback/close。 |
| 112 | P07 Seed | Tenant/Admin/Roles/Permissions/Operations/Capabilities/Mock Software/Instance。 |
| 113 | P08 Registry | operation_registry.get("BUILD.COLUMN") 返回定义。 |
| 114 | P09 Schema | load/validate/reject。 |
| 115 | P10–P13 Security | Authentication/Session/RBAC/Effective Permission 先于写操作。 |
| 116 | P14–P18 Execution Foundation | Resource/Lock/Context/Validation/Capability 完成后才能执行 Adapter。 |
| 117 | P19–P20 Adapter | 先 Adapter Base 再 Mock Adapter；不要先开发 MIDAS。 |
| 118 | P21 Idempotency | 所有 CREATE/BUILD/ASSIGN 接入。 |
| 119 | P22–P28 Task | State/Queue/Worker/Scheduler/Lease/Recovery/Cancellation。 |
| 120 | P29–P35 Infrastructure | Artifact/Document/Event/Audit/Trace/Metrics/Health。 |
| 121 | P36 ExecutionService | 第一个真正的 Core 主干，实现 12 环节。 |
| 122 | P37–P39 MCP | Context→Dispatcher→Base Tool→9 Tools。 |
| 123 | P40 STDIO | MCP Client connect/list_tools/call_tool。 |
| 124 | P41 HTTP | Streamable HTTP；不复制业务逻辑。 |
| 125 | P42–P48 Testing | Unit→Contract→Integration→Security→Concurrency→Recovery→E2E。 |
| 126 | Definition of Source Complete | 11 项判据。 |
| 127 | Definition of Core Alpha | 端到端链路全部运行。 |
| 128 | MIDAS 接入前置条件 | 七类测试全通过后才进 MIDAS。 |
| 129 | MIDAS 接入边界 | Adapter 可新增 8 文件；Core 不允许新增 midas tool/service/domain entity。 |
| 130 | 第二软件验证 | 加 CSI ETABS 后 9 Tool/Operation/Client/Task/RBAC 不变。 |
| 131 | Source-Level Acceptance Matrix | 17 行模块×必须存在×必须测试。 |
| 132 | 最终代码调用链 | 同步/异步调用链。 |
| 133 | 最终软件无关性检查 | grep -R "midas" app/ 预期 0。 |
| 134 | 最终架构冻结 | 架构总图。 |
| 135 | 第七份之后的实施路线 | 进源码→编译→测试→E2E→Freeze→MIDAS Adapter。 |
| 136 | 第七份最终结论 | 三原则：Core 不认识 MIDAS；Tool 不直接碰 Native API；新软件通过 Adapter 扩展。 |

---

## B. 逐文件实现蓝图（blue 给出的文件规格）

> 说明：blue 主要按“目录/文件 + 职责”给出规格，source7 再给出更细的类/方法。下表合并两份文档，列出所有出现的源文件（含 app 各层、database、registry、adapters、storage、events、notifications、locks、secrets、observability、interfaces、schemas、migrations、scripts、tests、根配置）。

| 文件路径 | 职责 | 关键类 / 函数 |
|---|---|---|
| pyproject.toml | 依赖与打包（blue §4；source7 §4） | project.dependencies / optional dev / entry-points `structai.adapters`（blue §42） |
| README.md / LICENSE / .env.example / .gitignore | 项目根文件 | — |
| app/__init__.py | 包初始化 | — |
| app/main.py | 启动/关闭编排（blue §124/§125；source7 §79/§80） | 启动链、SIGINT/SIGTERM |
| app/container.py | 依赖组装（blue §123；source7 §78） | `ApplicationContainer` |
| app/config/settings.py | 环境变量/DB/MCP/HTTP/日志/任务/安全/Artifact 配置 | `Settings(BaseSettings)` |
| app/config/runtime_config.py | 运行时参数 | `RuntimeConfig`（shutdown/task_poll/lease/heartbeat） |
| app/config/logging.py | 结构化日志到 stderr | 日志初始化 |
| app/domain/__init__.py | 包初始化 | — |
| app/domain/enums.py | 枚举 | RiskLevel/ExecutionMode/TaskStatus/LockMode + ResourceType/AuthenticationMethod 等（blue §7；source7 §8） |
| app/domain/entities.py | 领域实体 | Tenant/User/Role/Permission/Session/Project/Software*/Model/Document/Task/TaskStep/Artifact/Capability/Operation/OperationCapability/IdempotencyRecord/ResourceLock/AuditRecord + Engineering*（blue §9） |
| app/domain/value_objects.py | 不可变值对象 | RequestIdentity、ResourceRef、VersionRef、Pagination、IdempotencyKey、SoftwareRef、ProjectRef、ModelRef、DocumentRef；`OperationDefinition`（blue §8/§21；source7 §13） |
| app/domain/errors.py | 统一异常与错误码 | `StructAIError` 及 19 个派生异常（blue §10；source7 §9） |
| app/domain/events.py | 领域事件定义 | Task*/Adapter*/ModelChanged（blue §9/§58） |
| app/domain/protocols.py | 应用层接口 | `Repository`、`UnitOfWork`、`ArtifactStorage`（blue §11；source7 §3.1） |
| app/application/__init__.py | 包初始化 | — |
| app/application/commands/ | 命令（blue §3 目录，未展开） | — |
| app/application/queries/ | 查询（blue §3 目录，未展开） | — |
| app/application/dto/common.py | 通用 DTO（source7 §4） | — |
| app/application/dto/tool.py | Tool 请求/响应 DTO | `ToolRequest`、`ToolResponse`（source7 §11） |
| app/application/dto/task.py | 任务 DTO | `TaskResponse`（source7 §12） |
| app/application/dto/model.py | 模型 DTO（source7 §4） | — |
| app/application/dto/result.py | 结果 DTO（source7 §4） | — |
| app/application/execution/context.py | 执行上下文 | IdentityContext/SoftwareContext/ProjectContext/ResourceContext/ExecutionContext（blue §29；source7 §10） |
| app/application/execution/service.py | 核心执行服务 | `ExecutionService.execute()`（blue §86；source7 §45） |
| app/application/execution/pipeline.py | 校验流水线 | 冻结顺序（blue §30） |
| app/application/execution/validation.py | Schema 校验 | `SchemaValidator.validate()`（source7 §29） |
| app/application/execution/engineering_validator.py | 工程校验 | `EngineeringValidationError` 抛出（blue §31；source7 §30） |
| app/application/execution/preconditions.py | 前置条件 | MODEL.NODE.CREATE/ANALYSIS.STATIC 等（blue §32） |
| app/application/execution/postconditions.py | 后置条件 | 同上（blue §32） |
| app/application/execution/confirmation.py | 确认策略 | 风险等级→确认（blue §33） |
| app/application/execution/idempotency.py | 幂等 | `IdempotencyService.get_existing/reserve/complete`（blue §37；source7 §28） |
| app/application/services/adapter_resolver.py | Adapter 解析 | `AdapterResolver`（blue §87） |
| app/application/services/capability_resolver.py | 能力解析 | `CapabilityResolver.supports()/require()`（blue §34；source7 §31） |
| app/application/services/document.py | 文档服务 | `DocumentService.new/open/save/save_as/close/info`（blue §57；source7 §47） |
| app/application/services/model.py | 模型服务 | query_node/element/material/section/boundary/load、assign_material/section/boundary/load（source7 §48） |
| app/application/services/result.py | 结果服务 | Result query/pagination/normalization/artifact linking（source7 §49） |
| app/application/services/quota.py | 配额/限流 | 维度/指标（blue §60） |
| app/application/services/backup.py | 备份恢复 | backup/restore/integrity-check（blue §66） |
| app/application/security/authentication.py | 认证 | `AuthenticationService.authenticate()`（blue §25；source7 §20） |
| app/application/security/password.py | 密码 | `PasswordService.hash/verify`（Argon2id）（blue §25；source7 §21） |
| app/application/security/session.py | 会话 | create/validate/refresh/revoke/expire（blue §24；source7 §22） |
| app/application/security/rbac.py | RBAC | `RBACService.has_permission()`（blue §24；source7 §23） |
| app/application/security/permission.py | 权限（blue §24） | — |
| app/application/security/context.py | 身份上下文 | `IdentityContext`（blue §26；source7 §10） |
| app/application/security/token.py | Token（blue §24 目录） | — |
| app/application/security/effective_permission.py | 有效权限 | 计算链→set[str]（blue §27；source7 §24） |
| app/application/resource/resolver.py | 资源解析 | `ResourceResolver.resolve()`（blue §28；source7 §25） |
| app/application/resource/lock_manager.py | 资源锁 | `ResourceLockManager.acquire/release`（blue §35；source7 §26） |
| app/application/resource/lock_policy.py | 锁策略 | 兼容性规则（blue §35；source7 §27） |
| app/application/task/engine.py | 任务引擎 | `TaskEngine.submit/get/cancel/retry/recover`（blue §48；source7 §39） |
| app/application/task/queue.py | 队列 | `TaskQueue.put/get/shutdown`（blue §49；source7 §38） |
| app/application/task/worker.py | Worker | 取任务→执行链（blue §50；source7 §40） |
| app/application/task/state_machine.py | 状态机 | `ALLOWED_TRANSITIONS`（blue §47；source7 §37） |
| app/application/task/scheduler.py | 调度 | 优先级/并发/序列化（blue §49） |
| app/application/task/dag.py | DAG | Step 依赖（blue §54） |
| app/application/task/lease.py | 租约 | acquire/heartbeat/release/is_expired（blue §51；source7 §41） |
| app/application/task/recovery.py | 恢复 | `recover_unfinished_tasks()`（blue §52；source7 §42） |
| app/application/task/cancellation.py | 取消 | CANCEL_REQUESTED→Adapter.cancel（blue §53；source7 §43） |
| app/application/task/progress.py | 进度 | `ProgressReporter.report()`（source7 §44） |
| app/infrastructure/__init__.py | 包初始化 | — |
| app/infrastructure/database/base.py | ORM 基类 | `Base(DeclarativeBase)`（blue §13；source7 §14） |
| app/infrastructure/database/session.py | 会话工厂 | `create_database()`（blue §14；source7 §15） |
| app/infrastructure/database/unit_of_work.py | 工作单元 | `SQLAlchemyUnitOfWork`（blue §17；source7 §16） |
| app/infrastructure/database/models/* | ORM 模型（按实体拆文件） | TenantModel…AuditRecordModel（blue §15；source7 §18） |
| app/infrastructure/database/repositories/* | 仓储实现 | UserRepository…AuditRepository（blue §16；source7 §19） |
| app/infrastructure/registry/software_registry.py | 软件注册 | `SoftwareRegistry`（blue §19） |
| app/infrastructure/registry/capability_registry.py | 能力注册 | `CapabilityRegistry`（blue §20） |
| app/infrastructure/registry/operation_registry.py | 操作注册 | `OperationRegistry`（blue §21） |
| app/infrastructure/registry/schema_registry.py | Schema 注册 | `SchemaRegistry`（blue §22） |
| app/infrastructure/registry/api_registry.py | API 映射注册 | `APIRegistry`（blue §23） |
| app/infrastructure/adapters/base/adapter.py | Adapter 基类 | `EngineeringSoftwareAdapter(ABC)`（blue §39；source7 §32） |
| app/infrastructure/adapters/base/manifest.py | Adapter 清单 | Manifest 模型（blue §41） |
| app/infrastructure/adapters/base/errors.py | Adapter 错误 | AdapterError（blue §38） |
| app/infrastructure/adapters/base/manager.py | Adapter 管理 | `AdapterManager.register/get_for_instance/health_check_all`（blue §87；source7 §33） |
| app/infrastructure/adapters/mock/adapter.py | Mock Adapter | 实现全部 Mock Operation（blue §43；source7 §34） |
| app/infrastructure/adapters/mock/model_store.py | 内存模型存储 | `MockModelStore`（source7 §35） |
| app/infrastructure/adapters/mock/analysis.py | Mock 分析 | 确定性测试结果（source7 §36） |
| app/infrastructure/adapters/plugins/ | 插件（MIDAS 等） | structai_midas 等（blue §119） |
| app/infrastructure/storage/base.py | 存储接口 | `ArtifactStorage` Protocol（blue §55） |
| app/infrastructure/storage/local.py | 本地存储 | `LocalFilesystemStorage`（blue §56；source7 §51） |
| app/infrastructure/storage/manager.py | 存储管理 | Artifact 管理（blue §55） |
| app/infrastructure/secrets/base.py | 密钥接口 | —（source7 §4） |
| app/infrastructure/secrets/environment.py | 环境变量密钥 | —（source7 §4） |
| app/infrastructure/events/bus.py | 事件总线接口 | `EventBus` Protocol（blue §58；source7 §52） |
| app/infrastructure/events/in_process.py | 进程内事件总线 | `InProcessEventBus.publish/subscribe`（blue §58；source7 §52） |
| app/infrastructure/notifications/service.py | 通知服务 | 预留（blue §59） |
| app/infrastructure/locks/in_memory.py | 内存锁 | 锁实现（source7 §4） |
| app/interfaces/__init__.py | 包初始化 | — |
| app/interfaces/mcp/server.py | MCP 服务器 | 初始化/注册/绑定（blue §68；source7 §73） |
| app/interfaces/mcp/context.py | MCP 上下文 | `MCPContext`（blue §69；source7 §57） |
| app/interfaces/mcp/dispatcher.py | Tool 分发 | `ToolDispatcher.dispatch()`（blue §72；source7 §58） |
| app/interfaces/mcp/responses.py | 统一响应 | 同步/异步响应（blue §71） |
| app/interfaces/mcp/errors.py | MCP 错误边界 | `error_response()`（source7 §75） |
| app/interfaces/mcp/tools/base.py | Tool 基类 | `BaseEngineeringTool(ABC)`（blue §73；source7 §56） |
| app/interfaces/mcp/tools/engineering_doc.py | Doc Tool | `EngineeringDocTool`（blue §75；source7 §60） |
| app/interfaces/mcp/tools/engineering_model_query.py | 查询 Tool | `EngineeringModelQueryTool`（blue §76；source7 §61） |
| app/interfaces/mcp/tools/engineering_model_assign.py | 赋值 Tool | `EngineeringModelAssignTool`（blue §77；source7 §62） |
| app/interfaces/mcp/tools/engineering_model_delete.py | 删除 Tool | `EngineeringModelDeleteTool`（blue §78；source7 §63） |
| app/interfaces/mcp/tools/engineering_model_build.py | 建模 Tool | `EngineeringModelBuildTool`（blue §79；source7 §64） |
| app/interfaces/mcp/tools/engineering_view.py | 视图 Tool | `EngineeringViewTool`（blue §80；source7 §65） |
| app/interfaces/mcp/tools/engineering_result.py | 结果 Tool | `EngineeringResultTool`（blue §81；source7 §66） |
| app/interfaces/mcp/tools/engineering_design.py | 设计 Tool | `EngineeringDesignTool`（blue §82；source7 §67） |
| app/interfaces/mcp/tools/engineering_analysis.py | 分析 Tool | `EngineeringAnalysisTool`（blue §83；source7 §68） |
| app/interfaces/http/api.py | HTTP 入口（blue §95） | FastAPI app |
| app/interfaces/http/health.py | 健康检查 | /livez /readyz /health（blue §94；source7 §77） |
| app/interfaces/http/management/software.py | 管理 API | 软件实例（blue §95） |
| app/interfaces/http/management/tasks.py | 管理 API | Task（blue §95） |
| app/interfaces/http/management/system.py | 管理 API | 系统（blue §95） |
| app/interfaces/cli/ | CLI（blue §3 目录） | — |
| app/observability/tracing.py | 追踪 | Trace Span（blue §63） |
| app/observability/metrics.py | 指标 | structai_* 计数（blue §64；source7 §55） |
| app/observability/audit.py | 审计 | `AuditService.record()` + Hash Chain（blue §65；source7 §53） |
| schemas/ | JSON Schema 文件（见 C 节） | Draft 2020-12 |
| migrations/env.py / script.py.mako / versions/ | Alembic（blue §102；source7 §4） | — |
| scripts/seed.py / seed_permissions.py / seed_operations.py / seed_capabilities.py / seed_mock.py | Seed 数据（blue §100） | — |
| tests/conftest.py | 测试 fixture（source7 §93） | test db/container/user/tenant/project/mock/identity |
| tests/unit/ | 单元测试（blue §104；source7 §94） | test_domain/test_registry/test_enums/… |
| tests/contract/ | Adapter 契约测试（blue §105；source7 §95） | adapter contract |
| tests/integration/ | 集成测试（blue §106） | test_database 等 |
| tests/recovery/ | 恢复测试（blue §109；source7 §101） | — |
| tests/security/ | 安全测试（blue §107；source7 §97） | — |
| tests/concurrency/ | 并发测试（blue §108；source7 §99） | — |
| tests/e2e/ | 端到端（blue §110；source7 §102） | test_full_engineering_flow |

注：blue §3 目录里 `application/commands/`、`application/queries/`、`interfaces/cli/`、`application/security/token.py`、`database/migrations/` 被列出但未展开规格；source7 §4 增加了 `container.py`、`dto/*`、`services/model.py|result.py`、`mock/model_store.py|analysis.py`、`secrets/*`、`locks/in_memory.py`、`notifications/service.py`、`adapters/base/manager.py`，并去掉了 blue 的 `commands/queries`。

---

## C. 源码级规格（来自 source7，尽量原样摘录）

### C-1. 最终源码目录树（source7 §4，第 9699–9848 行）

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

### C-2. Domain Enum（source7 §8，第 9936–9984 行）

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

（blue §7 另列还需 Permission、Capability、TaskPriority、ResourceType、ArtifactType、AuditResult、AuthenticationMethod。）

### C-3. Domain Errors（source7 §9，第 9995–10035 行）

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

派生异常（19 个）：ProtocolError、SchemaValidationError、EngineeringValidationError、ConcurrencyConflictError、SoftwareConnectionError、SoftwareAuthenticationError、SoftwareAPIError、SoftwareTimeoutError、CapabilityError、PermissionDeniedError、ConfirmationRequiredError、TenantAccessDeniedError、TaskError、TaskTimeoutError、TaskCancelledError、TaskRecoveryError、AdapterError、ResourceLockedError、ArtifactError。

blue §10 错误码表（完整）：
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

### C-4. Value Objects / Operation Definition

blue §8：`RequestIdentity(request_id, trace_id)`（frozen dataclass）+ ResourceRef、VersionRef、Pagination、IdempotencyKey、SoftwareRef、ProjectRef、ModelRef、DocumentRef；必须不可变。

Operation Definition（blue §21 / source7 §13，第 10163–10177 行）：
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

### C-5. Domain Events（blue §58，第 6732–6742 行）

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

### C-6. Protocols（blue §11，第 5244–5267 行；source7 §52）

```python
class Repository(Protocol):
    async def get(self, entity_id): ...

class UnitOfWork(Protocol):
    async def commit(self): ...
    async def rollback(self): ...

class ArtifactStorage(Protocol):
    async def put(self, data, metadata): ...
    async def get(self, artifact_id): ...
    async def delete(self, artifact_id): ...

class EventBus(Protocol):
    async def publish(self, event): ...
    async def subscribe(self, event_type, handler): ...
```

### C-7. ORM 模型最小集合（source7 §18，第 10281–10306 行；逐表）

ORM 规则（source7 §17）：所有 ORM 模型必须 UUID 主键 + created_at + updated_at；重要可变资源带 version；Tenant-owned 数据带 tenant_id。

必须实现的 24 个 Model 类：
| 序 | Model 类 | 语义/表（文档未逐表列字段，以下为可推导的字段与关系） |
|---|---|---|
| 1 | TenantModel | 租户根；PK UUID；created_at/updated_at；被 User/Project/… 以 tenant_id 引用 |
| 2 | UserModel | 用户；PK UUID；username（唯一）；password_hash；locked；login 失败计数；tenant_id |
| 3 | RoleModel | 角色；PK UUID；name（system_admin/engineer/viewer/ai_agent）；tenant_id |
| 4 | PermissionModel | 权限；PK UUID；code（MODEL_READ…API_TEST） |
| 5 | UserRoleModel | User↔Role 关联表 |
| 6 | RolePermissionModel | Role↔Permission 关联表 |
| 7 | SessionModel | 会话；PK UUID；user_id、tenant_id；过期时间；revoked 状态 |
| 8 | ProjectModel | 项目；PK UUID；tenant_id；version |
| 9 | ProjectMemberModel | 项目成员；project_id↔user_id/role |
| 10 | SoftwareModel | 软件厂商（Vendor，如 MIDAS/StructAI） |
| 11 | SoftwareProductModel | 产品（如 CIVIL NX / Mock Engineering Software） |
| 12 | SoftwareVersionModel | 版本（2025/2026/1.0） |
| 13 | SoftwareInstanceModel | 实例；instance_id；连接配置；credential_reference；version |
| 14 | ModelModel | 工程模型；PK UUID；project_id；version |
| 15 | DocumentModel | 文档；PK UUID；model_id；生命周期状态 |
| 16 | CapabilityModel | 能力；code（MODEL.NODE.READ…DESIGN.OPTIMIZATION） |
| 17 | OperationModel | 操作定义持久化（name/tool/risk/mode/schemas/…） |
| 18 | OperationCapabilityModel | Operation↔Capability 关联 |
| 19 | TaskModel | 任务；task_id；status；progress；lease_owner/lease_until/last_heartbeat；trace_id；version |
| 20 | TaskStepModel | 任务步骤；task_id；依赖（DAG） |
| 21 | ArtifactModel | 产物；artifact_id；storage_backend；storage_key；mime_type；size；checksum |
| 22 | ResourceLockModel | 资源锁；resource_type；resource_id；mode；owner_id；timeout |
| 23 | IdempotencyRecordModel | 幂等记录；(tenant_id, idempotency_key) 唯一；request_hash；response |
| 24 | AuditRecordModel | 审计；audit_id；tenant_id/user_id/action/resource/result；previous_hash；entry_hash |

（blue §9 另列领域实体 Engineering*：EngineeringNode/Element/Material/Section/Boundary/Load/Group/Analysis/Result/Design，属 Canonical Model，不绑定供应商。）

### C-8. Repository 契约（source7 §19，第 10315–10341 行）

```python
class UserRepository(Protocol):
    async def get_by_id(self, user_id): ...
    async def get_by_username(self, username): ...
    async def add(self, user): ...
```

每个 Repository：CRUD + Query + Persistence；不得负责 Authorization / Task scheduling / Native API。blue §16 要求 repositories 目录含 user/tenant/project/software/model/document/capability/operation/task/artifact/lock/idempotency/audit。

### C-9. 各 Service 接口签名（source7）

| Service | 文件 | 接口签名（原文） |
|---|---|---|
| AuthenticationService | security/authentication.py | `async def authenticate(self, username: str, password: str) -> IdentityContext`；流程 Find User→Check Locked→Verify Password→Update Login State→Create Session→Build IdentityContext→Audit Login |
| PasswordService | security/password.py | `def hash(self, password: str) -> str`；`def verify(self, password: str, password_hash: str) -> bool`；使用 Argon2id |
| SessionService | security/session.py | create / validate / refresh / revoke / expire；Session 必须有过期时间、可撤销、绑定 User、绑定 Tenant |
| RBACService | security/rbac.py | `async def has_permission(self, identity: IdentityContext, permission: str, resource=None) -> bool` |
| EffectivePermissionService | security/effective_permission.py | 计算 Global Role + Tenant Role + Project Role + Resource ACL - Explicit Deny；返回 `set[str]` |
| ResourceResolver | resource/resolver.py | `async def resolve(self, context: ExecutionContext)`；验证 Tenant ownership / Project membership / Model ownership / Document ownership / Software access |
| ResourceLockManager | resource/lock_manager.py | `async def acquire(self, resource_type, resource_id, mode, owner_id, timeout)`；`async def release(self, lock_id)` |
| IdempotencyService | execution/idempotency.py | `async def get_existing(self, tenant_id, key)`；`async def reserve(self, tenant_id, key, request_hash)`；`async def complete(self, record_id, response)`；必须有数据库唯一约束 |
| SchemaValidator | execution/validation.py | `async def validate(self, schema_id: str, data: dict)`；错误 STRUCTAI-1100 |
| EngineeringValidator | execution/engineering_validator.py | 检查 Node/Element/Material/Section/Boundary/Load；例 `if node["x"] is None: raise EngineeringValidationError(...)`；工程规则与 JSON Schema 分离 |
| CapabilityResolver | services/capability_resolver.py | `async def require(self, software_instance_id, capability)`；不存在 STRUCTAI-3000（blue §34 另有 `supports()`） |
| AdapterManager | adapters/base/manager.py | `async def register(self, adapter)`；`async def get_for_instance(self, instance_id)`；`async def health_check_all(self)` |
| TaskEngine | task/engine.py | `async def submit(self, request, context)`；`async def get(self, task_id)`；`async def cancel(self, task_id)`；`async def retry(self, task_id)`；`async def recover(self)` |
| TaskQueue | task/queue.py | `async def put(self, task_id: str, priority: int = 0)`；`async def get(self) -> str`；`async def shutdown(self)` |
| LeaseService | task/lease.py | `acquire()` / `heartbeat()` / `release()` / `is_expired()`；字段 lease_owner/lease_until/last_heartbeat |
| RecoveryService | task/recovery.py | `await recovery.recover_unfinished_tasks()`；查 QUEUED/RUNNING/PROCESSING/RECOVERING 并检查 lease |
| ProgressReporter | task/progress.py | `async def report(self, task_id, progress: int, message: str | None = None)`；范围 0–100 |
| ExecutionService | execution/service.py | `async def execute(self, tool_name: str, operation: OperationDefinition, parameters: dict, request: ToolRequest, context: ExecutionContext)`；顺序 Schema→Engineering→Precondition→Permission→Quota→Confirmation→Idempotency→Lock→Capability→Task→Adapter→Normalize→Postcondition→Audit→Event |
| DocumentService | services/document.py | `async def new/open/save/save_as/close/info(self, ...)` |
| ModelService | services/model.py | query_node / query_element / query_material / query_section / query_boundary / query_load / assign_material / assign_section / assign_boundary / assign_load；Tool 不直接调 Repository |
| ResultService | services/result.py | Result query / pagination / canonical normalization / artifact linking |
| ArtifactService | services/artifact.py（blue §50） | `async def create(self, data, metadata)`；`async def get(self, artifact_id)` |
| EventBus | events/bus.py | `async def publish(self, event)`；`async def subscribe(self, event_type, handler)`；Core Alpha = InProcessEventBus |
| AuditService | observability/audit.py | `async def record(self, *, context, action, resource, result)` |
| TraceService | observability/tracing.py | 生成 request_id/trace_id 用 `uuid4()`；所有子 Task 继承 trace_id |
| Metrics | observability/metrics.py | 计数器 requests_total/tasks_total/tasks_failed_total/adapter_requests_total/adapter_errors_total/active_tasks |
| ToolDispatcher | mcp/dispatcher.py | `async def dispatch(self, tool_name, request, context)`；`tool = self.registry.get(tool_name)`；None 抛 `ProtocolError(f"Unknown tool: {tool_name}")`；`return await tool.handle(request, context)` |
| BaseEngineeringTool | mcp/tools/base.py | `name: str`；`@abstractmethod async def handle(self, request: ToolRequest, context: MCPContext) -> ToolResponse` |

blue §86 ExecutionService 串联环节（12 项）：Validation / Permission / Confirmation / Quota / Idempotency / Lock / Capability / Task / Adapter / Result / Audit / Event。

blue §30 完整运行时链（Authenticate→IdentityContext→ExecutionContext→Resolve Tool→Resolve Operation→Resolve Resource→Schema Validation→Engineering Validation→Preconditions→Effective Permission→Quota→Confirmation→Idempotency→Lock→Capability→Task/Transaction→Adapter→Result Normalize→Postconditions→Release Lock→Persist Result→Audit→Trace→Event→MCP Response）。

### C-10. Mock Adapter 的行为（source7 §34–§36、§90–§92；blue §43–§45）

**必须实现的操作（source7 §34 / blue §43）**
```text
MODEL.NODE.CREATE / UPDATE / DELETE / QUERY
MODEL.ELEMENT.CREATE / UPDATE / DELETE / QUERY
MODEL.BOUNDARY.ASSIGN
MODEL.LOAD.ASSIGN
BUILD.COLUMN
ANALYSIS.STATIC
RESULT.NODE.DISPLACEMENT
RESULT.ELEMENT.FORCE
DESIGN.STEEL
```
（blue §43 版本更全，另含 MODEL.MATERIAL.ASSIGN、MODEL.SECTION.ASSIGN、BUILD.BEAM。）

**MockModelStore（source7 §35，第 10749–10757 行）**
```python
class MockModelStore:
    nodes: dict[int, dict]
    elements: dict[int, dict]
    materials: dict[int, dict]
    sections: dict[int, dict]
    boundaries: list[dict]
    loads: list[dict]
```
要求：线程/协程安全、ID 自动分配、版本控制、查询、更新、删除。

**BUILD.COLUMN（source7 §90 伪代码，第 12313–12346 行）**
```python
async def build_column(self, parameters):
    base = parameters["base_node"]
    height = parameters["height"]

    bottom = self.store.create_node(base["x"], base["y"], base["z"])
    top = self.store.create_node(base["x"], base["y"], base["z"] + height)

    element = self.store.create_element(
        type="COLUMN",
        node_ids=[bottom["id"], top["id"]],
    )

    return {
        "node_ids": [bottom["id"], top["id"]],
        "element_ids": [element["id"]],
    }
```
输入示例（blue §45）：`{"base_node":{"x":0,"y":0,"z":0},"height":6,"material":"Q355B","section":"H400x400x13x21"}`；返回 `{"node_ids":[1,2],"element_ids":[1]}`。

**ANALYSIS.STATIC（source7 §91 / §36）**：流程 Validate model→Find loads→Generate deterministic test result→Persist result→Return Result Reference；不宣称真实工程计算。示例结果 `{"node_id":2,"ux":0.001,"uy":0.002,"uz":-0.015}`；**Mock Result ≠ 工程计算结果**，必须在测试文档中明确标识。

**DESIGN.STEEL（source7 §92）**：返回 `{"element_id":1,"utilization":0.72,"status":"PASS"}`；仅用于 Core workflow testing，不能作为实际工程设计依据。

### C-11. Operation Seed 全清单（source7 §69，第 11596–11682 行；按 Tool 分组）

**engineering_doc**
```text
NEW / OPEN / SAVE / SAVE_AS / CLOSE / INFO
```
**engineering_model_query**
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
**engineering_model_assign**
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
**engineering_model_delete**
```text
MODEL.NODE.DELETE
MODEL.ELEMENT.DELETE
MODEL.LOAD.DELETE
MODEL.BOUNDARY.DELETE
MODEL.GROUP.DELETE
MODEL.MATERIAL.DELETE
MODEL.SECTION.DELETE
```
**engineering_model_build**
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
**engineering_view**
```text
VIEW.MODEL / VIEW.DEFORMED_MODEL / VIEW.REACTION / VIEW.DISPLACEMENT / VIEW.STRESS / VIEW.FORCE / VIEW.MODE_SHAPE
```
**engineering_result**
```text
RESULT.NODE.DISPLACEMENT / RESULT.NODE.REACTION / RESULT.ELEMENT.FORCE / RESULT.ELEMENT.STRESS / RESULT.MODE.SHAPE / RESULT.ANALYSIS.SUMMARY
```
**engineering_design**
```text
DESIGN.STEEL / DESIGN.CONCRETE / DESIGN.FOUNDATION / DESIGN.CODE_CHECK / DESIGN.OPTIMIZE
```
**engineering_analysis**
```text
ANALYSIS.STATIC / ANALYSIS.MODAL / ANALYSIS.SEISMIC / ANALYSIS.SPECTRUM / ANALYSIS.BUCKLING / ANALYSIS.TIME_HISTORY / ANALYSIS.NONLINEAR
```

**Operation 语义（source7 §87，第 12198–12259 行）**
- `MODEL.NODE.CREATE`：Permission=MODEL_WRITE；Capability=MODEL.NODE.WRITE；Lock=MODEL WRITE；Idempotency=REQUIRED；Version=REQUIRED where update semantics apply；Dry Run=YES。
- `MODEL.NODE.DELETE`：Permission=MODEL_DELETE；Capability=MODEL.NODE.DELETE；Risk=HIGH；Lock=MODEL WRITE；Confirmation=YES by default。
- `ANALYSIS.STATIC`：Permission=ANALYSIS_EXECUTE；Capability=ANALYSIS.STATIC；Risk=HIGH；Execution=ASYNC；Lock=MODEL READ / SOFTWARE SERIAL；Task=REQUIRED。

**Operation 风险/模式总表（blue §75–§83）**
| Tool | 默认 Risk | 默认 Mode | 权限 |
|---|---|---|---|
| engineering_doc | MEDIUM | — | DOCUMENT_READ / DOCUMENT_WRITE |
| engineering_model_query | LOW | SYNC | MODEL_READ |
| engineering_model_assign | — | — | MODEL_WRITE |
| engineering_model_delete | HIGH | ASYNC | MODEL_DELETE |
| engineering_model_build | HIGH | ASYNC | （需 MODEL_WRITE） |
| engineering_view | LOW | SYNC | — |
| engineering_result | LOW | SYNC | RESULT_READ |
| engineering_design | HIGH | ASYNC | DESIGN_EXECUTE（优化另需 DESIGN_MODIFY） |
| engineering_analysis | HIGH | ASYNC | ANALYSIS_EXECUTE |

### C-12. Capability Seed 全清单（source7 §70，第 11690–11730 行）

```text
MODEL.NODE.READ / MODEL.NODE.WRITE / MODEL.NODE.DELETE
MODEL.ELEMENT.READ / MODEL.ELEMENT.WRITE / MODEL.ELEMENT.DELETE
MODEL.MATERIAL.READ / MODEL.MATERIAL.WRITE
MODEL.SECTION.READ / MODEL.SECTION.WRITE
MODEL.BOUNDARY.READ / MODEL.BOUNDARY.WRITE
MODEL.LOAD.READ / MODEL.LOAD.WRITE / MODEL.LOAD.DELETE
ANALYSIS.STATIC / ANALYSIS.MODAL / ANALYSIS.SEISMIC / ANALYSIS.SPECTRUM / ANALYSIS.BUCKLING / ANALYSIS.TIME_HISTORY / ANALYSIS.NONLINEAR
RESULT.DISPLACEMENT / RESULT.REACTION / RESULT.ELEMENT_FORCE / RESULT.STRESS / RESULT.MODE_SHAPE
DESIGN.STEEL / DESIGN.CONCRETE / DESIGN.FOUNDATION / DESIGN.OPTIMIZATION
```
（blue §101 中 Mock Software 实际注册的能力子集：MODEL.NODE.READ/WRITE/DELETE、MODEL.ELEMENT.READ/WRITE/DELETE、ANALYSIS.STATIC、RESULT.DISPLACEMENT、RESULT.ELEMENT_FORCE、DESIGN.STEEL。）

### C-13. Permission Seed / 默认 Role 全清单（source7 §71–§72，第 11736–11788 行）

**Permission Seed（12 个）**
```text
MODEL_READ / MODEL_WRITE / MODEL_DELETE
ANALYSIS_EXECUTE
DESIGN_EXECUTE / DESIGN_MODIFY
RESULT_READ
DOCUMENT_READ / DOCUMENT_WRITE
SYSTEM_ADMIN / TOOL_TEST / API_TEST
```

**Default Roles（4 个）**
```text
system_admin  → ALL
engineer      → MODEL_READ, MODEL_WRITE, MODEL_DELETE, ANALYSIS_EXECUTE,
                DESIGN_EXECUTE, DESIGN_MODIFY, RESULT_READ,
                DOCUMENT_READ, DOCUMENT_WRITE
viewer        → MODEL_READ, RESULT_READ, DOCUMENT_READ
ai_agent      → 根据 Agent Scope 动态限制
```
（blue §131：有效权限 = UserPermission ∩ AgentPermission，AI 不得扩大权限。）

### C-14. 9 个 MCP Tool 的源码级规格（source7 §56–§68、§74；blue §72–§84）

**统一模式（source7 §59）**：`handle() → resolve operation → build ExecutionContext → ExecutionService.execute() → Unified Response`。Tool 只 Parse→Context→Application Service→Response，不含业务算法。统一入参 schema（blue §84）：`operation`(required)、`parameters`、`context`、`idempotency_key`、`confirmation_token`、`dry_run`。Tool 注册数量必须严格 = 9（source7 §74）。

| # | Tool name | 类 | 允许的 operation | 默认 risk/mode | 权限 |
|---|---|---|---|---|---|
| 1 | engineering_doc | EngineeringDocTool | NEW / OPEN / SAVE / SAVE_AS / CLOSE / INFO | MEDIUM | DOCUMENT_READ / DOCUMENT_WRITE |
| 2 | engineering_model_query | EngineeringModelQueryTool | MODEL.QUERY / MODEL.NODE.QUERY / MODEL.ELEMENT.QUERY / MODEL.MATERIAL.QUERY / MODEL.SECTION.QUERY / MODEL.BOUNDARY.QUERY / MODEL.LOAD.QUERY / MODEL.GROUP.QUERY | LOW / SYNC | MODEL_READ |
| 3 | engineering_model_assign | EngineeringModelAssignTool | MODEL.NODE.CREATE / MODEL.NODE.UPDATE / MODEL.ELEMENT.CREATE / MODEL.ELEMENT.UPDATE / MODEL.MATERIAL.ASSIGN / MODEL.SECTION.ASSIGN / MODEL.BOUNDARY.ASSIGN / MODEL.LOAD.ASSIGN | 支持 idempotency/version/dry_run/transaction | MODEL_WRITE |
| 4 | engineering_model_delete | EngineeringModelDeleteTool | MODEL.NODE.DELETE / MODEL.ELEMENT.DELETE / MODEL.LOAD.DELETE / MODEL.BOUNDARY.DELETE / MODEL.GROUP.DELETE / MODEL.MATERIAL.DELETE / MODEL.SECTION.DELETE | HIGH / ASYNC | MODEL_DELETE |
| 5 | engineering_model_build | EngineeringModelBuildTool | BUILD.NODE_GRID / BUILD.BEAM / BUILD.COLUMN / BUILD.FRAME / BUILD.TRUSS / BUILD.SLAB / BUILD.WALL / BUILD.FOUNDATION / BUILD.STEEL_FRAME / MODEL.COPY / MODEL.MOVE / MODEL.MIRROR / MODEL.PATTERN / MODEL.GENERATE_GRID | HIGH / ASYNC | （MODEL_WRITE） |
| 6 | engineering_view | EngineeringViewTool | VIEW.MODEL / VIEW.DEFORMED_MODEL / VIEW.REACTION / VIEW.DISPLACEMENT / VIEW.STRESS / VIEW.FORCE / VIEW.MODE_SHAPE | LOW / SYNC | — |
| 7 | engineering_result | EngineeringResultTool | RESULT.NODE.DISPLACEMENT / RESULT.NODE.REACTION / RESULT.ELEMENT.FORCE / RESULT.ELEMENT.STRESS / RESULT.MODE.SHAPE / RESULT.ANALYSIS.SUMMARY | LOW / SYNC；大结果分页 | RESULT_READ |
| 8 | engineering_design | EngineeringDesignTool | DESIGN.STEEL / DESIGN.CONCRETE / DESIGN.FOUNDATION / DESIGN.CODE_CHECK / DESIGN.OPTIMIZE | HIGH / ASYNC | DESIGN_EXECUTE（优化另需 DESIGN_MODIFY） |
| 9 | engineering_analysis | EngineeringAnalysisTool | ANALYSIS.STATIC / ANALYSIS.MODAL / ANALYSIS.SEISMIC / ANALYSIS.SPECTRUM / ANALYSIS.BUCKLING / ANALYSIS.TIME_HISTORY / ANALYSIS.NONLINEAR | HIGH / ASYNC | ANALYSIS_EXECUTE |

**ToolDispatcher 源码（source7 §58，第 11336–11355 行）**
```python
class ToolDispatcher:
    async def dispatch(self, tool_name, request, context):
        tool = self.registry.get(tool_name)
        if tool is None:
            raise ProtocolError(f"Unknown tool: {tool_name}")
        return await tool.handle(request, context)
```

**统一 Error Response（source7 §75，第 11847–11873 行）**
```python
def error_response(error: StructAIError, *, request_id, trace_id, tool, operation):
    return {
        "success": False,
        "request_id": request_id,
        "trace_id": trace_id,
        "tool": tool,
        "operation": operation,
        "execution": {},
        "data": None,
        "warnings": [],
        "errors": [{
            "code": error.code,
            "type": error.error_type,
            "message": error.message,
            "details": error.details,
            "retryable": error.retryable,
        }],
    }
```

### C-15. Schema 文件（source7 §81–§85；blue §22/§82–§85）

**目录（source7 §81，第 12000–12027 行）**
```text
schemas/
├── common/
│   ├── pagination.json
│   ├── error.json
│   └── response.json
├── model/
│   ├── node/v1.json
│   ├── element/v1.json
│   ├── material/v1.json
│   ├── section/v1.json
│   ├── boundary/v1.json
│   └── load/v1.json
├── analysis/
│   └── static/v1.json
└── result/
    ├── displacement/v1.json
    └── element_force/v1.json
```
Schema ID 形如 `structai://schema/model/node/v1`（blue §22）。JSON Schema Draft 2020-12。

**Node Schema（source7 §82，第 12034–12059 行）**
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "structai://schema/model/node/v1",
  "type": "object",
  "properties": {
    "id": { "type": "integer" },
    "x": { "type": "number" },
    "y": { "type": "number" },
    "z": { "type": "number" }
  },
  "required": ["id", "x", "y", "z"],
  "additionalProperties": false
}
```

**Column Build Schema（source7 §83，第 12068–12099 行）**
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
    "height": { "type": "number", "exclusiveMinimum": 0 },
    "material": { "type": "string" },
    "section": { "type": "string" }
  },
  "required": ["base_node", "height", "material", "section"]
}
```

**Load Schema（source7 §84，第 12107–12126 行）**
```json
{
  "type": "object",
  "properties": {
    "node_id": { "type": "integer" },
    "fx": { "type": "number" },
    "fy": { "type": "number" },
    "fz": { "type": "number" }
  },
  "required": ["node_id"]
}
```
（工程单位体系必须在 Project / Model 层明确，不允许 Core 默认任意单位。）

**Result Schema（位移，source7 §85，第 12136–12152 行）**
```json
{
  "type": "object",
  "properties": {
    "node_id": {"type": "integer"},
    "ux": {"type": "number"},
    "uy": {"type": "number"},
    "uz": {"type": "number"}
  },
  "required": ["node_id", "ux", "uy", "uz"]
}
```

**Operation Registration Matrix（source7 §86）**：每个 Operation 至少需要 name/tool/risk_level/execution_mode/input_schema/output_schema/permissions/capabilities/transactional/rollback_supported/dry_run_supported/recovery_policy。BUILD.COLUMN 示例：
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

### C-16. 开发顺序 P01–P48 逐批内容（source7 §105–§125）

严格顺序（source7 §105，第 12667–12714 行）：P01 Project Bootstrap → P02 Config → P03 Domain → P04 Database → P05 Repository → P06 UnitOfWork → P07 Seed → P08 Registry → P09 Schema → P10 Authentication → P11 Session → P12 RBAC → P13 Effective Permission → P14 Resource Resolver → P15 Lock → P16 Execution Context → P17 Validation → P18 Capability → P19 Adapter Base → P20 Mock Adapter → P21 Idempotency → P22 Task State → P23 Queue → P24 Worker → P25 Scheduler → P26 Lease → P27 Recovery → P28 Cancellation → P29 Artifact → P30 Document → P31 Event → P32 Audit → P33 Trace → P34 Metrics → P35 Health → P36 Execution Service → P37 MCP Context → P38 Dispatcher → P39 9 Tools → P40 STDIO → P41 HTTP → P42 Unit Tests → P43 Contract Tests → P44 Integration Tests → P45 Security Tests → P46 Concurrency Tests → P47 Recovery Tests → P48 E2E。

| 批 | 名称 | 内容 / 验收 |
|---|---|---|
| P01 | Bootstrap（§106） | 建 pyproject.toml、README.md、.env.example、.gitignore、app/__init__.py、app/main.py、app/container.py；`python -m app.main` 能启动并正常退出 |
| P02 | Config（§107） | Settings / RuntimeConfig / Logging；测环境变量覆盖默认值 |
| P03 | Domain（§108） | Enums / Errors / Value Objects / Protocols / Events；不得引用 SQLAlchemy/FastAPI/MCP |
| P04 | Database（§109） | Base / Engine / Session / ORM；验证 SQLite 连接 |
| P05 | Repository（§110） | 最小 UserRepository / TenantRepository / ProjectRepository / SoftwareRepository / ModelRepository / TaskRepository |
| P06 | UnitOfWork（§111） | 验证 commit / rollback / close |
| P07 | Seed（§112） | Tenant / Admin / Roles / Permissions / Operations / Capabilities / Mock Software / Mock Instance |
| P08 | Registry（§113） | `operation_registry.get("BUILD.COLUMN")` 必须返回定义 |
| P09 | Schema（§114） | load schema / validate valid data / reject invalid data |
| P10–P13 | Security（§115） | Authentication / Session / RBAC / Effective Permission，先于写操作 |
| P14–P18 | Execution Foundation（§116） | Resource / Lock / Context / Validation / Capability，完成后才能执行 Adapter |
| P19–P20 | Adapter（§117） | 先 Adapter Base 再 Mock Adapter；不要先开发 MIDAS |
| P21 | Idempotency（§118） | 所有 CREATE/BUILD/ASSIGN 流程接入 |
| P22–P28 | Task（§119） | State / Queue / Worker / Scheduler / Lease / Recovery / Cancellation，之后才接 ASYNC Tool |
| P29–P35 | Infrastructure（§120） | Artifact / Document / Event / Audit / Trace / Metrics / Health |
| P36 | ExecutionService（§121） | 第一个真正的 Core 主干，实现 validate/authorize/confirm/idempotency/lock/capability/task/adapter/normalize/persist/audit/event |
| P37–P39 | MCP（§122） | 顺序：MCP Context → Dispatcher → Base Tool → 9 Tools |
| P40 | STDIO（§123） | Generic MCP Client 能 connect / list_tools / call_tool |
| P41 | HTTP（§124） | 加入 Streamable HTTP，但不复制业务逻辑 |
| P42–P48 | Testing（§125） | Unit → Contract → Integration → Security → Concurrency → Recovery → E2E |

blue §113 的 P0–P12 里程碑与 source7 的 P01–P48 对应：P0 Bootstrap / P1 Domain / P2 Persistence / P3 Registry / P4 Security / P5 Execution Core / P6 Adapter / P7 Task / P8 Artifact / P9 Observability / P10 MCP / P11 Transport / P12 Tests。blue §114–§118 五个可运行里程碑：①BUILD.COLUMN ②+QUERY/ASSIGN LOAD ③+ANALYSIS.STATIC ④+RESULT ⑤+DESIGN.STEEL。

---

## D. 所有出现的 MIDAS API 引用（blue + source7 范围内，逐条）

> 结论先行：在 blue（4674–9487）与 source7（9488–13462）两个子文档中，**唯一被具体写出的 MIDAS 接口路径是 `POST /anal/STATIC`（REST）**。文档刻意不把 MIDAS 路径/表代码写入 Core，反复强调“实际接口路径和参数必须依据对应 MIDAS API Registry / API 文档注册，不能硬编码到 Core”（第 8622 行）。`/db/...`、`/doc/...`、`/ope/...`、`/view/...`、`/post/TABLE`、`/design/...` 这类路径在本范围内**完全没有出现**（经全文 grep 确认：这些模式仅出现在后续文档，如第 15370、19899 行等 source9 及以后）。

### D-1. 具体接口路径 / HTTP 方法

| # | 引用 | HTTP 方法 | 出处（行号 / 小节） |
|---|---|---|---|
| 1 | `/anal/STATIC` | POST | 第 5596–5598 行，blue §23 API Registry 示例（`"protocol":"REST","method":"POST","path":"/anal/STATIC"`） |
| 2 | `REST POST /anal/STATIC` | POST | 第 7597 行，blue §88 API Mapping（ANALYSIS.STATIC → MIDAS） |
| 3 | `POST /anal/STATIC` | POST | 第 8619 行，blue §120 MIDAS Adapter 内部结构（MIDAS CIVIL NX 2026） |

### D-2. 软件 / 产品 / 版本 / 协议标识

| # | 引用 | 出处 |
|---|---|---|
| 4 | software=`MIDAS`，product=`CIVIL NX`，version=`2026`，operation=`ANALYSIS.STATIC`，protocol=`REST` | 第 5592–5598 行，blue §23 |
| 5 | Adapter manifest：name=`midas.civil`，vendor=`MIDAS`，product=`CIVIL NX`，supported_versions=[`2025`,`2026`]，protocols=[`REST`] | 第 6240–6251 行，blue §41 |
| 6 | plugin entry-point：`midas.civil = "structai_midas.adapter:CivilAdapter"` | 第 6262 行，blue §42 |
| 7 | MIDAS Adapter 模块 `structai_midas/`：adapter.py / manifest.py / client.py / capabilities.py / operations.py / transforms.py / errors.py / health.py | 第 8566–8575 行，blue §119 |
| 8 | `MIDAS CIVIL NX 2026` + `POST /anal/STATIC` | 第 8618–8619 行，blue §120 |

### D-3. 其他厂商 / 非 REST 映射（对照，非 MIDAS 路径）

| # | 引用 | 出处 |
|---|---|---|
| 9 | ETABS → `COM RunAnalysis` | 第 7603 行，blue §88 |
| 10 | OpenSees → `SCRIPT analyze` | 第 7609 行，blue §88 |
| 11 | MIDAS response→Canonical；AI 不需知道 `MIDAS JSON` / `ETABS COM` / `OpenSees Tcl` | 第 7625、7648–7650 行，blue §89 |
| 12 | MIDAS CIVIL 2026 / ETABS 22 / OpenSees（后续文档举例，供参考） | 第 26164–26170 行（超出本范围，source 后续） |

### D-4. 表代码 / 数据库表

本范围内**没有任何 MIDAS 表代码（如 `/db/NODE`、`/post/TABLE`）被列出**。文档只在多处出现“禁止把 MIDAS endpoint/parameter/response/SDK 放进 Core”的约束（第 13284–13288 行），以及 `grep -R "midas" app/` 应得 0 的检查（第 13262 行）。

### D-5. 与 MIDAS 相关的禁令/边界（逐条，含出处）

- 第 4735–4739 行（blue §1.2）：禁止 `midas_xxx()`、`midas_api()`、`midas_endpoint()`、`midas_node_create()`、`midas_analysis_static()`。
- 第 4745 行（blue §1.2）：禁止 `Tool → MIDAS API`（同理 SQLAlchemy / requests/httpx / native vendor SDK）。
- 第 5019 行（blue §5）：不得保存 `MIDAS Key`。
- 第 5033 行（blue §6）：Domain 不依赖 MIDAS。
- 第 6270 行（blue §42）：Core 不 import `from midas import ...`。
- 第 6705–6707 行（blue §57）：Document Service 不知道 MIDAS/ETABS/SAP2000。
- 第 8679 行（blue §122）：禁止 `Domain → MIDAS`。
- 第 8849 行（blue §128）：不返回 `MIDAS API Key`。
- 第 9569–9572 行（source7 §1.3）：本文不实现 MIDAS API / CSI API / ANSYS API / OpenSees API。
- 第 9651 行（source7 §3.2）：禁止 `domain → MIDAS`。
- 第 12917 行（source7 §117）：不要先开发 MIDAS。
- 第 13102–13116 行（source7 §128）：MIDAS 接入前置条件（七类测试全过）。
- 第 13120–13141 行（source7 §129）：MIDAS Adapter 可新增 8 文件；Core 不允许新增 `midas tool` / `midas service` / `midas domain entity`。
- 第 13262–13288 行（source7 §133）：`grep -R "midas" app/` 预期 0 MIDAS-specific business dependency；Core Domain/Application 不允许 MIDAS endpoint/parameter/response/SDK。
- 第 13414 行（source7 §136）：原则 1「Core 不认识 MIDAS」。

---

## E. Definition of Source Complete / Definition of Core Alpha（判据）

### E-1. Definition of Source Complete（source7 §126，第 13057–13068 行）
源码阶段必须同时满足（原文勾选项）：
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

### E-2. Definition of Core Alpha（source7 §127，第 13077–13096 行）
端到端链路全部运行：
```text
MCP Client → 9 Tools → Execution Pipeline → RBAC → Capability → Lock
→ Task Engine → Mock Adapter → Canonical Model → Result
```

### E-3. blue §143 Final Definition of Done（第 9346–9402 行，53 项 [✓]）
Python 3.12+ / Async Architecture / SQLite / Alembic / Repository / UnitOfWork / Multi-Tenant / Authentication / Session / RBAC / Effective Permission / Resource Resolver / Resource Lock / Optimistic Lock / Idempotency / Software Registry / Capability Registry / Operation Registry / Schema Registry / API Registry / JSON Schema / Validation / Preconditions / Postconditions / Confirmation / Adapter Framework / Plugin Loader / Mock Adapter / Task Engine / Task DAG / Task Lease / Task Recovery / Cancellation / Artifact Storage / Document Service / Batch / Dry Run / Event Bus / Quota / Audit / Trace / Metrics / Health / Backup / Restore / 9 MCP Tools / MCP Dispatcher / STDIO / Streamable HTTP / Unit Tests / Contract Tests / Integration Tests / Security Tests / Concurrency Tests / Recovery Tests / Generic AI E2E。

### E-4. blue §137 Core Alpha Acceptance（第 9154–9169 行）
启动成功 → SQLite 正常 → Migration 正常 → Seed 正常 → MCP Server 正常 → Discover 9 Tools → Discover Operations → Discover Capabilities。

### E-5. blue §138 Functional Acceptance（第 9178–9187 行）
BUILD.COLUMN / MODEL.NODE.QUERY / MODEL.ELEMENT.QUERY / MODEL.BOUNDARY.ASSIGN / MODEL.LOAD.ASSIGN / ANALYSIS.STATIC / RESULT.NODE.DISPLACEMENT / RESULT.ELEMENT.FORCE / DESIGN.STEEL 完整通过。

### E-6. blue §139 Security Acceptance（第 9198–9210 行）
未登录→拒绝；无 MODEL_WRITE→MODEL.NODE.CREATE 拒绝；无 ANALYSIS_EXECUTE→ANALYSIS.STATIC 拒绝；跨 Tenant→拒绝；跨 Project→拒绝；无 Confirmation→HIGH 操作拒绝；AI Agent 权限不足→拒绝。

### E-7. blue §135 Minimum Production Requirements（第 9039–9087 行，47 项）
SQLite / Alembic / Repository / UnitOfWork / Multi-Tenant / Authentication / Session / RBAC / Effective Permission / Resource Resolver / Lock / Optimistic Concurrency / Idempotency / Registry / Schema Engine / Validation / Capability Resolver / Adapter Framework / Plugin Loader / Mock Adapter / Task Engine / DAG / Lease / Recovery / Cancellation / Artifact / Document / Batch / Dry Run / Preconditions / Postconditions / Event Bus / Quota / Audit / Trace / Metrics / Health / Backup / 9 MCP Tools / STDIO / Streamable HTTP / Unit / Contract / Integration / Security / Concurrency / Recovery / E2E。

### E-8. Source-Level Acceptance Matrix（source7 §131，第 13175–13193 行）
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

## F. 架构冻结原则与禁止项

### F-1. 依赖方向（冻结）
- blue §122 / source7 §3.1–§3.2：`Interface → Application → Domain`；Infrastructure 实现 Domain/Application 接口（`Infrastructure → Domain/Application Interfaces`）。
- 禁止：`Domain → SQLAlchemy`、`Domain → FastAPI`、`Domain → MCP`、`Domain → MIDAS`、`Domain → HTTPX`。
- source7 §133：Core Alpha 完成后 `grep -R "midas" app/` 预期 = 0 MIDAS-specific business dependency；允许出现在 tests/docs/adapter plugin registration，但 Core Domain/Application 不允许 MIDAS endpoint/parameter/response/SDK。

### F-2. 架构漂移禁止项（blue §1.2）
- 禁止直接进入 Core：`midas_xxx()`、`midas_api()`、`midas_endpoint()`、`midas_node_create()`、`midas_analysis_static()`。
- Tool 层禁止：`Tool → MIDAS API`、`Tool → SQLAlchemy`、`Tool → requests/httpx`、`Tool → native vendor SDK`。
- 正确方向：`Tool → Application Service → Operation → Capability → Adapter → Native API`。
- 不增加第 10 个 MCP Tool（blue 开头声明；source7 §74 明确 Tool 数量必须严格 = 9）。

### F-3. Implementation Rules（blue §134，Rule 1–10）
1. Domain 不依赖 Infrastructure。
2. Tool 不直接操作数据库。
3. Tool 不直接调用 Adapter。
4. Adapter 不实现 RBAC。
5. AI 不拥有独立于用户的越权能力。
6. 所有写操作必须经过版本/锁/idempotency 策略。
7. 所有高风险操作必须经过 Confirmation 策略。
8. 所有异步任务必须有 Task ID。
9. 所有任务必须可以查询状态。
10. 所有异常必须转换为 StructAI Error。

### F-4. 其他冻结约束
- **Server Trust Boundary（source7 §3.5 / blue §26/§69/§107）**：客户端不能决定 user_id / tenant_id / roles / permissions / effective_permissions；必须由 Server Authentication 生成，AI Client 提交的对应字段必须被忽略/拒绝覆盖。
- **Security Boundary（blue §129）**：任何 Tool 都不能绕过 Authentication→Identity→RBAC→Resource ACL→Execution。
- **Error Boundary（blue §128 / source7 §76）**：Native Exception → Adapter Error → Application Error → MCP Error；不得返回 Python traceback / SQL query / password hash / API Key / HTTP Authorization / native secret。
- **Adapter 边界（blue §40 / source7 §129）**：Adapter 负责连接/认证/版本/能力/映射/转换/执行/归一化/健康检查 10 项；不负责 MCP/RBAC/Global Task Lifecycle/Global Audit/AI/UI；Core 不允许新增 midas tool/service/domain entity。
- **事务边界（blue §126）**：一个数据库事务不得无限包含长时间 Native API 调用（prepare→commit necessary state→native execution→persist result）。
- **幂等并发（blue §37）**：必须原子插入 + 唯一约束，禁止 `SELECT→if not exists→INSERT`。
- **乐观并发（blue §36）**：expected_version 冲突返回 STRUCTAI-1300，不得覆盖新版本。
- **日志边界（blue §132 / §62）**：禁止输出 password/token/API Key/private key/secret/完整 Authorization header；STDIO 模式下日志必须到 stderr（blue §97）。
- **端口/协议（source7 §3.3）**：Tool Thin Handler——Tool 只 Parse→Context→Application Service→Response，不含业务算法。
- **无无限文档（source7 §135）**：第七份之后不再增加架构文档，直接进入源码→编译→测试→E2E→Core Alpha Freeze→MIDAS Adapter。
- **source7 §136 三原则**：1. Core 不认识 MIDAS；2. Tool 不直接碰 Native API；3. 新软件通过 Adapter 扩展，而不是修改 Core。

### F-5. 未在本文档中展开的事项（如实说明）
- blue §3 列出的 `application/commands/`、`application/queries/`、`interfaces/cli/`、`application/security/token.py`、`database/migrations/` 只出现在目录树，未给出类/方法级规格；source7 最终目录中已移除 `commands/queries`（改为 `dto/`）。
- ORM 24 个 Model 的**逐字段/逐关系**定义在两份子文档中均未逐表给出（仅给出命名规则：UUID PK + created_at + updated_at + version + tenant_id）；完整字段定义在后续文档（source9 起）。
- MIDAS 具体接口路径除 `/anal/STATIC` 外均未在本范围内给出（文档要求以 MIDAS API Registry 为准）。
- Artifact Service 的文件路径在两份文档中不一致：blue §50 未点名文件，source7 §4 目录中无 `services/artifact.py`（结果/产物逻辑归入 `services/result.py` 与 `storage/manager.py`）。

---

## 附：本次精读覆盖范围确认
- blue：第 4674–9487 行全部读取（§1–§145）。
- source7：第 9488–13462 行全部读取（§1–§136）。
- 已用 grep 全文核验 MIDAS/接口路径模式，确认 D 节结论。
- 未修改任何文件（仅读取 + 写入本报告到 session scratch 目录）。
