# 精读报告：02_STRUCTAI_MCP_V2_CORE_IMPLEMENTATION.md 前两个子文档

文件：G:\MMCP\docs\02_STRUCTAI_MCP_V2_CORE_IMPLEMENTATION.md（全文 28891 行，394907 bytes）
本次范围：第 1-4673 行
- 子文档 impl = Core Implementation Specification — Revision V2：L12-L1779（第 1-59 节）
- 子文档 py = Core Python 代码实现规范 — Revision V2：L1781-L4673（第 1-87 节）
- 下一子文档 blue（File-Level Implementation Blueprint）从 L4674 开始，不在本次范围。

标题层级说明：两个子文档的正文小节实际用 H1（`# N.`）书写；H2（`##`）只出现在子文档标题处 —— impl L15 `## Core Implementation Specification — Revision V2`，py L1785 `## Core Python 代码实现规范 --- Revision V2`。下表按"节"列出。

---

## A. 章节地图

### A1. impl（L12-L1779，第 1-59 节）

| 节 | 行 | 一句话要点 |
|---|---|---|
| 1 修订说明 | L24 | 把前三份设计与冻结的 Core Python Revision V2 统一为可实施代码级规范；列 30 项必须实现能力（Auth/Session/IdentityContext/Multi-Tenant/RBAC/Resource Resolver/Schema/Engineering Validation/Capability Resolver/Resource Lock/Optimistic Concurrency/Atomic Idempotency/Task Engine/Task DAG/Task Lease+Recovery/Adapter Plugin Loader/API Registry/Artifact/Document/Pagination/Batch/Dry Run/Pre-Postconditions/Event Bus/Quota/Health+Metrics/Audit+Trace/Backup+Recovery/MCP SDK/STDIO/Streamable HTTP/9 MCP Tools/E2E）。 |
| 2 技术基线 | L68 | Python>=3.12、FastAPI、Pydantic v2、SQLAlchemy 2.x、aiosqlite、Alembic、httpx、jsonschema、structlog、pytest、pytest-asyncio；MCP 用官方/成熟 Python SDK，不得自行重新实现 MCP protocol。 |
| 3 最终项目结构 | L90 | structai-mcp 目录树；依赖方向 Interface→Application→Domain、Infrastructure→Domain/Application Interfaces；禁止反向依赖。 |
| 4 Domain Enum | L177 | RiskLevel / ExecutionMode / TaskStatus / LockMode。 |
| 5 IdentityContext / ExecutionContext | L215 | 身份必须由服务器生成；IdentityContext + SoftwareContext + ProjectContext + ExecutionContext；客户端不得声明 user_id/tenant_id/roles/permissions。 |
| 6 Authentication / Session | L270 | AuthenticationService/PasswordService/SessionService/TokenService；Argon2id；login/logout/expiry/revoke/failed-login tracking/account lock；STDIO 可用 local trusted identity 但仍生成标准 IdentityContext。 |
| 7 Effective Permission | L308 | 权限链 User→Global Roles→Tenant Membership/Roles→Project Membership/Roles→Resource ACL→Explicit Deny；EffectivePermissionService.resolve/authorize；Agent 权限 = 用户有效权限 ∩ Agent 权限。 |
| 8 Resource Resolver | L348 | ResourceRef(resource_type, resource_id)；解析 Project/Model/Document/Software Instance/Task/Artifact；所有跨租户访问必须在此拦截。 |
| 9 Database / UnitOfWork | L372 | AsyncEngine/AsyncSession/async_sessionmaker；Application Service→UnitOfWork→Repository→Commit；异常→Rollback；Repository 不自行 commit。 |
| 10 Tool / Operation / Capability | L404 | ToolDefinition / OperationDefinition / CapabilityDefinition；Capability 不允许出现 MIDAS/CSI/ANSYS。 |
| 11 Registry | L460 | 必须存在 ToolRegistry/OperationRegistry/CapabilityRegistry/SchemaRegistry/SoftwareRegistry/AdapterRegistry/APIRegistry；Tool 不自行寻找 Adapter。 |
| 12 Schema Engine | L478 | JSON Schema Draft 2020-12；schema URI structai://schema/model/node/v1|v2；旧版本不可覆盖。 |
| 13 Validation Engine | L497 | 严格顺序 Input→Schema→Engineering→Permission→Confirmation→Capability→Execution；并给出完整 26 步 Pipeline。 |
| 14 Preconditions / Postconditions | L575 | OperationDefinition 必须支持 preconditions/postconditions；示例 ANALYSIS.STATIC。 |
| 15 Resource Lock | L600 | ResourceLockManager acquire/release/refresh；兼容矩阵；锁必须与 Task 生命周期关联。 |
| 16 Optimistic Concurrency | L622 | version / expected_version；UPDATE ... WHERE version=:expected_version；0 rows → STRUCTAI-1300。 |
| 17 Task Engine | L653 | 12 个 Task 状态；支持 sequential/parallel/dependency/retry/timeout/cancel/resume/recovery/priority/lease/heartbeat。 |
| 18 Task Lease / Recovery | L690 | lease_owner/lease_until/last_heartbeat；重启恢复流程；不能把恢复中的 Task 直接标记为 COMPLETED。 |
| 19 Task DAG | L716 | 依赖图示例；循环依赖必须在提交前拒绝。 |
| 20 Task Priority / Concurrency | L730 | CRITICAL/HIGH/NORMAL/LOW；软件实例 SERIAL/LIMITED/PARALLEL；桌面工程软件默认 SERIAL。 |
| 21 Adapter Interface | L757 | EngineeringSoftwareAdapter(ABC) 全签名。 |
| 22 Adapter Plugin Loader | L782 | Python Entry Points（[project.entry-points."structai.adapters"]）；Adapter Manifest JSON；禁止从数据库执行任意 Python。 |
| 23 Software Instance Lifecycle | L808 | 6 个实例状态；health_check；一个实例失败不能让整个 Server Not Ready。 |
| 24 API Registry / Version Resolver | L830 | 输入 software instance+operation，输出 adapter/API mapping/protocol/native operation/transform/timeout/retry policy；exact/range/fallback/deprecated；复杂 transformer 必须在 Adapter package。 |
| 25 Capability Cache | L864 | instance/version/capability/support_level/checked_at/expires_at；刷新触发条件（reconnect/version change/adapter change/manual refresh/expiry）。 |
| 26 Secret / Credential Provider | L889 | CredentialProvider Protocol；第一阶段 EnvironmentCredentialProvider；绝不记录 secret。 |
| 27 Batch / Dry Run | L916 | ToolRequest(BaseModel) 定义；Context 中的身份不能覆盖服务器 IdentityContext；Batch items+atomic。 |
| 28 Atomic Idempotency | L943 | 唯一键 tenant_id+idempotency_key；必须 atomic INSERT，而非 SELECT→INSERT；重复请求返回已有 Task/Response。 |
| 29 Artifact Storage | L968 | ArtifactStorage Protocol；第一阶段 LocalFilesystemStorage；DB 只存 metadata。 |
| 30 Document Service | L987 | 生命周期 NEW/OPEN/SAVE/SAVE_AS/CLOSE/INFO；调用 ArtifactService+Adapter，不直接操作 MCP transport。 |
| 31 Pagination | L1011 | data+pagination{has_more,next_cursor}；禁止无限 payload。 |
| 32 Canonical Engineering Model | L1029 | Node/Element/Material/Section/Boundary/Load/Group/Analysis/Result/Design。 |
| 33 Result Normalization | L1050 | 归一化示例 {node_id,ux,uy,uz}；AI Client 不应依赖 MIDAS 原始字段。 |
| 34 Event Bus | L1067 | EventBus Protocol；InProcessEventBus；9 个事件。 |
| 35 Notification Extension | L1097 | MCP Notification/Webhook/WebSocket/UI/Email；Notification 不成为 Core Tool。 |
| 36 Quota / Rate Limit | L1113 | max_tasks/max_concurrent_tasks/max_api_requests/max_storage/max_projects；维度 user/tenant/AI agent/software instance；内存 limiter + DB quota definition。 |
| 37 Health / Metrics | L1138 | /livez /readyz /health；9 个指标名。 |
| 38 Runtime Configuration | L1162 | environment/host/port/database_url/log_level/task_workers/task_timeout/mcp_transport/artifact_root/retention/quota；Secret 不进入普通 settings。 |
| 39 Audit Integrity | L1184 | audit_id/timestamp/tenant_id/user_id/action/resource/result/previous_hash/entry_hash；entry_hash = H(previous_hash + canonical_entry)；高风险必须 Audit。 |
| 40 Data Retention | L1211 | 6 个 *_retention_days；删除必须服从审计与法规策略。 |
| 41 Backup / Restore | L1228 | SQLite backup + Artifact metadata + Registry data；恢复后 integrity-check→migration validation→registry validation→runtime health。 |
| 42 Migration Safety | L1254 | 必须 Alembic migration；禁止启动时静默 ALTER TABLE；versioned/checksum/tested/rollback strategy documented。 |
| 43 Unified Error Contract | L1279 | 20 个 STRUCTAI 错误码（见 B.16）。 |
| 44 MCP SDK Integration | L1306 | SDK 负责 Protocol/Session/Discovery/Registration/Invocation/Cancellation/Progress；StructAI 负责 Registry/Pipeline/Task/Security/Adapter/Result/Audit/Trace。 |
| 45 MCP Progress / Cancellation | L1335 | 进度链 TaskEngine→MCP progress notification；取消链 MCP cancel→TaskEngine.cancel()→Adapter.cancel()；无法真实取消时返回 cancellation_requested 而非伪造 CANCELLED。 |
| 46 9 Tool Layer | L1365 | app/interfaces/mcp/tools/ 下 9 个文件；Handler 必须很薄（parse→build context→call Application Service→map response）；禁止 SQL/RBAC calculation/Adapter lookup/Task implementation。 |
| 47 9 Tool 注册 | L1410 | engineering_doc / engineering_model_query / engineering_model_assign / engineering_model_delete / engineering_model_build / engineering_view / engineering_result / engineering_design / engineering_analysis。 |
| 48 Mock Adapter | L1434 | 必须支持 MODEL.NODE.* / MODEL.ELEMENT.* / MODEL.MATERIAL.* / MODEL.SECTION.* / MODEL.BOUNDARY.* / MODEL.LOAD.* / BUILD.COLUMN / ANALYSIS.STATIC / RESULT.NODE.DISPLACEMENT / DESIGN.STEEL。 |
| 49 E2E | L1455 | Generic AI Client 16 步闭环（connect→discover→BUILD.COLUMN→query→assign load→ANALYSIS.STATIC→poll→RESULT→DESIGN.STEEL→verify trace/audit）。 |
| 50 Failure / Recovery | L1491 | 13 项必测故障。 |
| 51 Test Layers | L1513 | Unit/Contract/Integration/Recovery/Security/Concurrency/Failure/Performance/E2E。 |
| 52 Security Tests | L1529 | 11 项（cross-tenant/forged identity/role escalation/agent privilege escalation/expired session/revoked session/secret leakage/audit tampering/confirmation bypass/idempotency race/lock bypass）。 |
| 53 Performance Tests | L1549 | 9 项；目标不是提前规定绝对 TPS，而是建立 Core Alpha 基准。 |
| 54 Graceful Shutdown | L1569 | 9 步顺序；未完成 Task 必须能在下次启动进入 Recovery。 |
| 55 Core Alpha Implementation Order | L1597 | 37 步实现顺序（见 F）。 |
| 56 Definition of Done | L1641 | 45 项 checklist。 |
| 57 Architecture Red Lines | L1692 | 禁止 7 项 + 必须的依赖链与调用链（见 G）。 |
| 58 与下一份文档的关系 | L1738 | 本文件冻结 Core Runtime/Execution Pipeline/Security/Task/Adapter/DB interaction/Observability/MCP integration；下一份冻结 9 Tool/JSON Schema/Operation enum/Parameters/Output/Risk/Permission/Capability/Confirmation/Errors/Examples；下一份不得重新定义 Core Runtime。 |
| 59 最终结论 | L1773 | Core Python Revision V2 是底层执行基线；9 Tool Contract 是上层稳定接口；MIDAS 只能是第一个 Adapter，而不是 Core 的架构边界。 |

### A2. py（L1781-L4673，第 1-87 节）

| 节 | 行 | 一句话要点 |
|---|---|---|
| 1 修订说明 | L1796 | 相对第四份新增 32 项底层能力（MCP SDK/Protocol、Task Recovery、Task DAG、Task Lease/Heartbeat、Resource Lock、Optimistic Concurrency、Atomic Idempotency、Auth/Session、Server-generated Identity、Secret Provider、Plugin Loader、Instance Lifecycle、Artifact/Document、Pagination、Batch、Dry Run、Pre/Postconditions、Capability Cache、Health/Readiness/Liveness、Metrics、Runtime Config、Event Bus、Notification、Quota、Audit Integrity、Retention、Backup/Restore、Migration Safety、Failure/Security Tests、Resource Resolver、分层）。 |
| 2 最终分层架构 | L1848 | Domain→Application→Infrastructure→Interface；ASCII 图；原则：Interface 不定义业务规则，Application 编排，Domain 定义工程语义，Infrastructure 提供实现。 |
| 3 最终项目结构 | L1904 | 与 impl §3 相同的目录树。 |
| 4 Python 与依赖 | L1992 | Python>=3.12；pyproject.toml 完整依赖与 test/dev extras；MCP 用官方稳定 SDK 并锁定验证版本。 |
| 5 Domain Enum | L2044 | 7 个枚举（比 impl 多 HealthStatus/SoftwareConnectionState/PermissionEffect）。 |
| 6 ExecutionContext：身份必须由服务器生成 | L2106 | 同 impl §5；客户端最多提供 project_id / software_instance_id，服务器必须验证其归属。 |
| 7 Authentication / Session | L2183 | 最小接口 authenticate / SessionService.create / revoke / validate。 |
| 8 Effective Permission Resolver | L2255 | 权限链 + EffectivePermissionService 完整签名；AI Agent 不允许提升权限。 |
| 9 Resource Resolver | L2316 | ResourceRef + ResourceResolver.resolve/verify_access 完整签名；跨租户访问必须在此层被拦截。 |
| 10 Database Session / Unit of Work | L2359 | UnitOfWork 类定义（session / __aenter__ / __aexit__）。 |
| 11 Tenant Isolation | L2407 | 所有 tenant-scoped Repository 必须要求 tenant_id；查询必须同时限制 tenant_id + resource_id；禁止依赖 UI 过滤。 |
| 12 Optimistic Concurrency | L2438 | Read version=12→Modify→UPDATE WHERE version=12→version=13；0 行 → STRUCTAI-1300 CONCURRENCY_CONFLICT；不得覆盖其他用户修改。 |
| 13 Resource Lock Manager | L2475 | acquire(resource, mode, owner_id, timeout)/release 完整签名；规则矩阵；工程模型修改用 WRITE/EXCLUSIVE；默认建议 SERIAL。 |
| 14 Task Lease / Heartbeat | L2530 | lease_owner/lease_until/last_heartbeat；now > lease_until 视为 Worker 丢失。 |
| 15 Task Recovery | L2552 | 启动恢复流程（Load unfinished→Inspect lease→valid? wait/reconcile : RECOVERING→retry/requeue）；策略 REQUEUE/FAIL/RESUME；默认：不可恢复→FAILED、可重入→REQUEUE、支持 checkpoint→RESUME。 |
| 16 Task DAG | L2588 | TaskStep dataclass（step_id/operation/parameters/depends_on）；dependency all COMPLETED→step runnable；支持 sequential/parallel/dependency/retry/timeout/cancel/resume。 |
| 17 Task Priority | L2637 | LOW/NORMAL/HIGH/CRITICAL；队列按 priority + created_at 排序。 |
| 18 Task 并发策略 | L2660 | global/tenant/user/software-instance 四级并发；示例 Tenant A=10、User A=4、CIVIL-01=1；最终取最严格限制。 |
| 19 Software Instance Lifecycle | L2683 | 6 状态 + AdapterManager（connect/disconnect/health_check/get_adapter）。 |
| 20 Software Instance Concurrency Policy | L2716 | SERIAL/LIMITED/PARALLEL；默认 SERIAL（尤其桌面型有限元软件）。 |
| 21 Secret / Credential Provider | L2736 | 数据库不得保存明文 API Key/Password/Token/Certificate Private Key；CredentialProvider Protocol 完整；第一阶段 EnvironmentCredentialProvider；日志绝对禁止输出 secret。 |
| 22 Adapter Plugin Loader | L2790 | Python Entry Points；启动 4 步（Plugin Loader→Discover→Validate Manifest→Register）；新软件原则 = New Adapter + Capability Mapping + Operation Mapping + API Registry；不修改 9 个 Tool Contract。 |
| 23 Adapter Manifest | L2835 | JSON（name/vendor/product/supported_versions/capabilities/protocols）。 |
| 24 API Registry / Version Resolver | L2852 | Operation→Software→Version→API Mapping；必须支持 exact match / version range / fallback / deprecated；示例 CIVIL 2025→API A、2026→API B、2027→API C。 |
| 25 API Transform Engine | L2885 | STATIC_MAPPING/TEMPLATE_MAPPING/JSON_MAPPING/CUSTOM_TRANSFORM；统一 Operation Parameters→Request Transformer→Native API→Response Transformer→Canonical Result；Custom Transformer 必须在 Adapter package；禁止数据库直接执行任意 Python。 |
| 26 Capability Cache | L2920 | Static Capability / Runtime Capability；缓存 instance_id/software_version/capability/checked_at/expires_at；支持 get/refresh/invalidate；重连或版本变化后必须重新验证。 |
| 27 Schema Registry | L2951 | schema URI；必须记录 schema_uri/version/content/status/created_at/deprecated_at；支持 resolve/validate/compatibility check；旧版本不可覆盖。 |
| 28 Operation Definition | L2983 | OperationDefinition 完整 dataclass（同 impl §10）。 |
| 29 Preconditions / Postconditions | L3006 | BUILD.COLUMN 示例：preconditions=project active/software connected/material valid/section valid；postconditions=nodes created/element created/assignments created。 |
| 30 Dry Run | L3034 | 高风险操作支持 mode=DRY_RUN；BUILD.COLUMN 返回 {dry_run:true, planned_changes:{nodes:2,elements:1,materials:1,sections:1}}；不得修改模型。 |
| 31 Batch Execution | L3066 | items 数组；适用于 NODE.CREATE/ELEMENT.CREATE/LOAD.ASSIGN；必须明确 atomic / non_atomic。 |
| 32 Idempotency：必须原子化 | L3097 | 唯一约束 tenant_id+idempotency_key；Atomic Insert→Conflict? Yes→Return existing result / No→Execute；不能 SELECT then INSERT。 |
| 33 Artifact Service | L3128 | 产物类型（工程文件/模型文件/分析结果/计算书/报告/截图/导出文件）；ArtifactStorage Protocol；DB 只存 artifact_id/storage_backend/storage_key/mime_type/size/checksum；第一阶段 LocalFilesystemStorage，未来 S3/MinIO/NAS。 |
| 34 Document Service | L3184 | engineering_doc 不直接操作文件系统；DocumentService→ArtifactService→Adapter；生命周期 NEW/OPEN/SAVE/SAVE_AS/CLOSE/INFO。 |
| 35 大结果集分页 | L3211 | limit/cursor/has_more/next_cursor；统一 data+pagination 结构；禁止一次返回无限数据。 |
| 36 Canonical Engineering Model | L3238 | Node/Element/Material/Section/Boundary/Load/Group/Analysis/Result/Design；必须定义稳定 Schema。 |
| 37 Result Normalization | L3259 | MIDAS/ETABS/SAP2000/ANSYS/OpenSees 统一为 StructAI Canonical Model。 |
| 38 Event Bus | L3286 | InProcessEventBus；9 事件；未来可替换 Redis/NATS/Kafka 而不修改 Domain Event。 |
| 39 Notification Extension | L3320 | NotificationService Protocol（notify）；未来 MCP notification/Webhook/WebSocket/UI/Email；Core Alpha 可只实现 InProcess。 |
| 40 Quota / Rate Limit | L3348 | 维度 User/Tenant/AI Agent/Software Instance；预留 max_tasks/max_concurrent_tasks/max_api_requests/max_storage/max_projects；Rate Limiter 第一阶段 InMemory→未来 Redis。 |
| 41 Health / Readiness / Liveness | L3383 | GET /livez /readyz /health；Liveness=process alive；Readiness=database/registry/task engine；Health=database/task engine/adapter manager/software instances；某一个 MIDAS 不在线时 Core=READY、MIDAS=UNAVAILABLE，不得让整个服务器不可用。 |
| 42 Metrics | L3427 | 9 个指标；推荐 Prometheus-compatible exposition。 |
| 43 Runtime Configuration | L3447 | Startup/Runtime/Persistent/Secret 四类；UI 修改 Runtime Config 流程 Config Service→Validation→Persist if required→Apply。 |
| 44 Audit Integrity | L3491 | 9 字段；用于检测篡改。 |
| 45 Data Retention | L3511 | Task/Trace/Audit/Artifact/Session 五类，每类 retention_days；Audit 默认不允许普通用户删除。 |
| 46 Backup / Restore | L3533 | backup/restore/integrity-check；SQLite 备份 DB+artifact metadata+registry data；恢复后 database integrity check + registry validation。 |
| 47 Migration Safety | L3560 | Alembic upgrade/downgrade；生产升级前 backup→migration→integrity check→registry validation；失败 rollback/restore。 |
| 48 Error Contract | L3589 | 同一套 20 个错误码。 |
| 49 MCP Error Mapping | L3624 | Adapter→StructAI Error→Application Response→MCP Response；AI 默认只看到 normalized error；诊断时才返回 cause{provider,native_code,native_message}。 |
| 50 MCP SDK 集成 | L3658 | MCP Server 负责 Protocol/Session/Discovery/Registration/Invocation/Cancellation/Progress；Tool Handler 不实现工程业务；MCP Tool→ToolRequest→ExecutionService。 |
| 51 MCP Progress | L3686 | Task Engine→progress event→MCP progress notification（0/25/43/80/100）；Task Engine 是唯一进度来源。 |
| 52 MCP Cancellation | L3712 | MCP Cancel→TaskEngine.cancel()→CANCEL_REQUESTED→Adapter.cancel()→CANCELLED；不能直接终止 Python process。 |
| 53 Tool Layer | L3732 | 9 个 Tool；每个都是 thin wrapper；最终 return await execution_service.execute(...)。 |
| 54 Tool 参数 | L3762 | ToolRequest(BaseModel)；context.identity 不得由客户端覆盖。 |
| 55 Execution Pipeline | L3786 | 冻结的 26 步执行链（见 C）。 |
| 56 Transaction / Rollback | L3848 | BUILD.COLUMN/BUILD.FRAME/BUILD.STEEL_FRAME；优先级 Native Transaction→Snapshot/Restore→Compensating Actions→Best Effort；OperationDefinition 必须声明 transactional / rollback_supported。 |
| 57 Mock Adapter | L3879 | 必须模拟 Node/Element/Material/Section/Boundary/Load/Analysis/Result/Design；支持 snapshot/restore/lock compatibility/deterministic analysis。 |
| 58 Mock E2E | L3906 | 固定场景：6m Q355B H400x400x13x21 钢柱，底部固定，顶部 500kN 轴压，静力分析，返回顶部节点位移与钢柱设计利用率；链 BUILD.COLUMN→MODEL.LOAD.ASSIGN→ANALYSIS.STATIC→RESULT.NODE.DISPLACEMENT→DESIGN.STEEL。 |
| 59 Result / Artifact | L3929 | Analysis Result→Canonical Result→Artifact（analysis.json/result.csv/report.pdf）；DB 只保存 Artifact metadata。 |
| 60 Application Service | L3953 | 负责 Command/Query/Execution/Task/Security/Resource；EngineeringExecutionService.execute(command)->ExecutionResult；可编排多个 Domain Service。 |
| 61 Domain Service | L3982 | 纯工程规则（Model validation/Engineering rules/Operation preconditions/Canonical model rules）；不得访问 HTTP/SQLAlchemy/FastAPI/MCP SDK。 |
| 62 Infrastructure Service | L4004 | 负责 Database/Adapter/Filesystem/Secret/Lock/Event/Notification。 |
| 63 Interface Layer | L4020 | 只允许 MCP/HTTP/CLI；不得直接访问 SQLAlchemy/Adapter/Filesystem；必须经过 Application Service。 |
| 64 Configuration Bootstrap | L4042 | 17 步启动顺序（Settings→Logging→Database→Migration→Seed→Registry→Plugin Loader→Schema Registry→Capability Registry→Adapter Manager→Resource Lock Manager→Task Engine→Event Bus→Security→Health→MCP Server→Transport）；Registry validation 失败 → Server MUST NOT become READY。 |
| 65 Graceful Shutdown | L4074 | 8 步（Stop new requests→Stop scheduler→Stop accepting tasks→Wait/recover active tasks→Disconnect adapters→Flush audit/events→Close DB→Exit）。 |
| 66 Health / Recovery Policy | L4096 | 启动发现 RUNNING task 必须按 Operation Recovery Policy 处理 REQUEUE/RESUME/FAIL；不得简单删除。 |
| 67 Tests | L4116 | tests/ 六个子目录。 |
| 68 Unit Tests | L4132 | 12 项（ToolRegistry/OperationRegistry/CapabilityResolver/SchemaValidator/EngineeringValidator/PermissionResolver/ResourceResolver/TaskStateMachine/TaskDAG/Idempotency/ResourceLock/ErrorMapper）。 |
| 69 Contract Tests | L4153 | 6 项 Schema（9 Tool Schemas/Operation/Response/Error/Context/Canonical Model）。 |
| 70 Integration Tests | L4168 | Tool→Application Service→Task Engine→Mock Adapter。 |
| 71 Recovery Tests | L4184 | 6 个 test_*（server_restart_recovery / expired_task_lease / task_requeue / task_resume / task_failure_after_recovery / adapter_disconnect_recovery）。 |
| 72 Concurrency Tests | L4199 | 6 个 test_*（optimistic_lock / idempotency_race / resource_lock / parallel_read / serial_write / software_instance_serialization）。 |
| 73 Security Tests | L4214 | 9 个 test_*（cross_tenant_access_denied / cross_project_access_denied / ai_agent_no_privilege_escalation / expired_session / revoked_session / invalid_confirmation / confirmation_replay / secret_not_logged / client_cannot_forge_identity）。 |
| 74 Failure Tests | L4232 | 7 个 test_*（adapter_timeout / adapter_connection_failure / database_failure / task_worker_failure / registry_failure / schema_version_mismatch / artifact_failure）。 |
| 75 Performance Tests | L4248 | 6 项；不得用性能优化破坏抽象层。 |
| 76 Code Quality | L4265 | ruff/mypy/pytest/pytest-cov/pre-commit；CI 8 步 lint→type check→unit→contract→integration→recovery→security→e2e。 |
| 77 Observability | L4299 | 每请求 request_id+trace_id，每异步任务 task_id；日志 14 个字段；不得记录 password/API key/token/private key。 |
| 78 Trace Span | L4343 | 13 个 span（MCP/Tool/Operation/Schema/Validation/Permission/Capability/Task/Lock/Adapter/Native API/Result/Audit）。 |
| 79 Audit | L4365 | HIGH/CRITICAL 必审计；审计字段 10 项（user/tenant/project/tool/operation/resource/software/result/timestamp/hash）。 |
| 80 Data Retention | L4390 | 5 个 *_retention_days（task/trace/audit/artifact/session）。 |
| 81 Backup | L4404 | database backup + artifact metadata backup + registry backup；执行 backup→integrity check；恢复 restore→migration check→registry validation→health check。 |
| 82 Core Alpha 实现顺序 | L4436 | 37 步（与 impl §55 完全一致）。 |
| 83 Core Alpha Definition of Done | L4482 | 44 项（比 impl §56 少一项 SQLAlchemy 2.x）。 |
| 84 Final Architecture | L4532 | 大 ASCII 架构图：Interface→Application→(Domain/Registry/Validation)→Capability Resolver→Resource Lock→Task Engine→(Adapter Manager/Artifact Storage)→MIDAS/ETABS/OpenSees→Canonical Result→Response/Trace/Audit。 |
| 85 最终冻结原则 | L4586 | 15 条原则（先定义工程语义再适配软件；Tool≠API；Operation≠厂商 API；Capability 不绑定 MIDAS；Adapter 吸收差异；Identity 由服务器生成；Tenant 隔离在 Core/Repository；模型修改必须 Resource Lock+Concurrency；异步任务必须 Lease+Recovery；大结果必须分页；复杂模型操作必须事务/回滚/Dry Run；Adapter 必须插件化；文件产物必须进 Artifact 层；UI 只能消费 Application/Management API）。 |
| 86 与第五份文档的关系 | L4620 | 下一份《9 个 MCP Tool 完整实现规范》只定义 9 个 tool，且每个 Tool 必须引用本文件冻结的 16 项（Authentication/IdentityContext/Permission/Resource Resolver/Schema/Capability/Quota/Idempotency/Resource Lock/Task/Dry Run/Transaction/Artifact/Trace/Audit）。 |
| 87 最终一句话 | L4666 | 目标不是"能调用 MIDAS"，而是建立具备身份、权限、租户、资源锁、任务编排、故障恢复、插件适配、工程语义、结果标准化和 MCP 协议能力的通用工程软件执行运行时。 |

---

## B. 源码级规格（原样摘录）

### B.1 Domain Enum

**impl §4（L179-L211）** 与 **py §5（L2046-L2102）** 的定义一致，py 多出 3 个枚举。

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

py 额外（L2084-L2102）：

```python
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

枚举取值汇总：RiskLevel{4} / ExecutionMode{3} / TaskStatus{12} / LockMode{3} / HealthStatus{3} / SoftwareConnectionState{6} / PermissionEffect{2}。

### B.2 IdentityContext / ExecutionContext

impl §5（L219-L245）与 py §6（L2121-L2158）完全相同：

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

身份来源链：`Authentication → AuthenticatedPrincipal → IdentityContext → ExecutionContext`。
客户端不得声明：`user_id / tenant_id / roles / permissions`；客户端最多提供 `project_id / software_instance_id`（py L2172-2179），服务器必须验证其归属。

### B.3 Authentication / Session

服务（impl §6 L274-279 / py §7 L2187-2192）：`AuthenticationService / PasswordService / SessionService / TokenService`。
密码哈希：`Argon2id`。必须支持：`login / logout / session expiry / session revoke / failed-login tracking / account lock`。
STDIO 单机模式可用 `local trusted identity`，但仍必须构造标准 IdentityContext。

py §7 最小接口（L2196-L2226）：

```python
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

### B.4 Effective Permission 解析算法

解析链（impl §7 L312-326 / py §8 L2261-2279）：

```text
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

接口（py §8 L2283-L2300，impl §7 为简化版 `resolve(context, resource) -> set[str]` / `authorize(context, permission, resource) -> None`）：

```python
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

AI Agent 权限 = `Effective User Permissions ∩ Agent Permissions`；AI Agent 不允许提升权限。

### B.5 Resource Resolver

impl §8（L350-368）/ py §9（L2331-L2355）：

```python
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

解析对象：`Project / Model / Document / Software Instance / Task / Artifact`。
所有跨租户访问必须在 Resource Resolver 层被拦截。

### B.6 Database / UnitOfWork / Repository / Tenant Isolation

使用（impl §9 L374-378 / py §10 L2363-2367）：`AsyncEngine / AsyncSession / async_sessionmaker`。

```python
class UnitOfWork:

    session: AsyncSession

    async def __aenter__(self):
        ...

    async def __aexit__(self, exc_type, exc, tb):
        ...
```

事务链：`Application Service → Unit of Work → Repository → Commit`；异常：`Exception → Rollback`。
Repository 不自行随意 commit。

Tenant Isolation（py §11 L2417-L2432）：

```python
async def get_task(
    self,
    task_id: UUID,
    tenant_id: UUID,
) -> Task | None:
    ...
```

数据库查询必须同时限制 `tenant_id + resource_id`；禁止依赖 UI 过滤。

### B.7 Registry 的加载与版本解析

impl §11（L462-474）必须存在：`ToolRegistry / OperationRegistry / CapabilityRegistry / SchemaRegistry / SoftwareRegistry / AdapterRegistry / APIRegistry`；**Tool 不自行寻找 Adapter**。

Schema Registry（py §27 L2951-2979）：schema URI `structai://schema/model/node/v1`、`structai://schema/model/node/v2`；旧版本不可覆盖；必须记录 `schema_uri / version / content / status / created_at / deprecated_at`；支持 `resolve / validate / compatibility check`。

API Registry / Version Resolver（impl §24 L830-860 / py §24 L2852-2881）：
- 输入：`software instance`、`operation`
- 输出：`adapter / API mapping / protocol / native operation / transform / timeout / retry policy`
- 必须支持：`version exact match / version range / fallback mapping / deprecated mapping`
- 示例：`CIVIL 2025 → API A`、`CIVIL 2026 → API B`、`CIVIL 2027 → API C`
- 复杂 request/response transformer 必须位于 Adapter package。

API Transform Engine（py §25 L2885-2916）：`STATIC_MAPPING / TEMPLATE_MAPPING / JSON_MAPPING / CUSTOM_TRANSFORM`；统一链 `Operation Parameters → Request Transformer → Native API → Response Transformer → Canonical Result`；Custom Transformer 必须在 Adapter package；禁止数据库直接执行任意 Python。

Configuration Bootstrap（py §64 L4046-4070）启动顺序：`1 Settings → 2 Logging → 3 Database → 4 Migration → 5 Seed → 6 Registry → 7 Plugin Loader → 8 Schema Registry → 9 Capability Registry → 10 Adapter Manager → 11 Resource Lock Manager → 12 Task Engine → 13 Event Bus → 14 Security → 15 Health → 16 MCP Server → 17 Transport`；Registry validation 失败 → `Server MUST NOT become READY`。

### B.8 Schema Engine / Validation Engine / Preconditions / Postconditions

Schema Engine（impl §12 L478-493）：使用 `JSON Schema Draft 2020-12`；URI `structai://schema/model/node/v1`、`structai://schema/model/node/v2`；旧版本不可覆盖。

Validation Engine 严格顺序（impl §13 L499-515）：

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

Preconditions / Postconditions（impl §14 L575-596，py §29 L3006-3030）：

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

```text
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

### B.9 Resource Lock / Optimistic Concurrency / Idempotency（含原子性要求）

Resource Lock Manager（py §13 L2487-L2526，impl §15 L602-618）：

```python
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

（impl §15 另有 `refresh(...)`。）兼容矩阵：

```text
READ + READ = allowed
READ + WRITE = blocked
WRITE + WRITE = blocked
EXCLUSIVE = blocks all
```

锁必须与 Task 生命周期关联；工程模型修改使用 `WRITE / EXCLUSIVE`；默认建议 `SERIAL`。

Optimistic Concurrency（impl §16 L622-649 / py §12 L2438-2471）：资源拥有 `version`；更新携带 `expected_version`；

```sql
UPDATE resource
SET version = version + 1
WHERE id = :id
  AND version = :expected_version
```

0 rows affected → `STRUCTAI-1300`（py 写作 `STRUCTAI-1300 CONCURRENCY_CONFLICT`）；不得覆盖其他用户修改。

Atomic Idempotency（impl §28 L943-964 / py §32 L3097-3124）：唯一键 `tenant_id + idempotency_key`；必须 `atomic INSERT`，而不是 `SELECT → INSERT`：

```text
Atomic Insert
      ↓
Conflict?
 ├── Yes → Return existing result
 └── No → Execute
```

重复请求必须返回已有 Task/Response。

### B.10 Task Engine / Lease / DAG / 恢复

Task Engine（impl §17 L653-686）：状态 12 个（同 TaskStatus 枚举）；支持 `sequential / parallel / dependency / retry / timeout / cancel / resume / recovery / priority / lease / heartbeat`。

Task Lease / Heartbeat（impl §18 L690-712 / py §14 L2530-2548）：`lease_owner / lease_until / last_heartbeat`；`now > lease_until` 视为 Worker 丢失。启动恢复：

```text
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

Recovery Policy：`REQUEUE / FAIL / RESUME`（由 OperationDefinition 指定）。默认：不可恢复 → FAILED；可重入 → REQUEUE；支持 checkpoint → RESUME。**不能把恢复中的 Task 直接标记为 COMPLETED**；不得简单删除 RUNNING task。

Task DAG（py §16 L2606-L2633）：

```python
@dataclass
class TaskStep:
    step_id: str
    operation: str
    parameters: dict
    depends_on: tuple[str, ...] = ()
```

调度规则 `dependency all COMPLETED → step becomes runnable`；支持 sequential/parallel/dependency/retry/timeout/cancel/resume；**循环依赖必须在提交前拒绝**（impl §19 L726）。

Task Priority（impl §20 L734-753 / py §17 L2641-2656）：`CRITICAL / HIGH / NORMAL / LOW`；队列按 `priority + created_at` 排序。
Task 并发策略（py §18 L2664-2679）：`global / tenant / user / software-instance` 四级，最终取最严格限制（示例 Tenant A=10、User A=4、CIVIL-01=1）。
软件实例并发：`SERIAL / LIMITED / PARALLEL`，桌面工程软件默认 `SERIAL`。

### B.11 Adapter 接口与 Plugin Loader

impl §21（L760-L778）：

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

AdapterManager（py §19 L2699-L2711）：`connect(instance_id) / disconnect(instance_id) / health_check(instance_id) / get_adapter(instance_id)`。

Plugin Loader（impl §22 L786-801 / py §22 L2802-2831）：Python Entry Points

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

启动：`Plugin Loader → Discover Adapter Plugins → Validate Manifest → Register Adapter`；新软件原则 = `New Adapter + Capability Mapping + Operation Mapping + API Registry`，**不修改 9 个 Tool Contract**；禁止从数据库执行任意 Python。

Software Instance Lifecycle（impl §23 L810-826 / py §19 L2687-2694）：`DISCONNECTED / CONNECTING / CONNECTED / DEGRADED / RECONNECTING / UNAVAILABLE`；一个实例失败不能让整个 Server Not Ready。

### B.12 Capability Cache / Secret Provider

Capability Cache（impl §25 L868-885 / py §26 L2922-2947）：分为 `Static Capability` 与 `Runtime Capability`；缓存字段 `instance_id / software_version / capability / checked_at / expires_at`（impl 用 `instance / version / capability / support_level / checked_at / expires_at`）；支持 `get / refresh / invalidate`；刷新触发：`reconnect / version change / adapter change / manual refresh / expiry`；重连或版本变化后必须重新验证。

Secret / Credential Provider（impl §26 L891-912 / py §21 L2749-2786）：

```python
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

第一阶段：`EnvironmentCredentialProvider`；未来：`OS Credential Store / Vault / KMS`。数据库不得保存明文 `API Key / Password / Token / Certificate Private Key`；**绝不记录 secret**。

### B.13 Batch / Dry Run / Artifact / Document / Pagination

ToolRequest（impl §27 L920-928 / py §54 L3766-3774）：

```python
class ToolRequest(BaseModel):
    operation: str
    parameters: dict = {}
    context: dict = {}
    idempotency_key: str | None = None
    confirmation_token: str | None = None
    dry_run: bool = False
```

`context.identity` 不得由客户端覆盖。

Batch（impl §27 L932-939 / py §31 L3066-3093）：`{"items": [{}, {}, {}], "atomic": true}`；适用于 `NODE.CREATE / ELEMENT.CREATE / LOAD.ASSIGN`；必须明确 `atomic / non_atomic`。

Dry Run（py §30 L3034-3062）：`mode = DRY_RUN`；返回

```json
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

**不得修改模型**。

Artifact Storage（impl §29 L970-983 / py §33 L3144-3180）：

```python
class ArtifactStorage(Protocol):
    async def put(...): ...
    async def get(...): ...
    async def delete(...): ...
```

DB 只保存 `artifact_id / storage_backend / storage_key / mime_type / size / checksum`；第一阶段 `LocalFilesystemStorage`，未来 `S3 / MinIO / NAS`。产物类型：工程文件、模型文件、分析结果、计算书、报告、截图、导出文件。

Document Service（impl §30 L989-1007 / py §34 L3184-3207）：`engineering_doc` 不直接操作文件系统；链 `DocumentService → ArtifactService → Adapter`；生命周期 `NEW / OPEN / SAVE / SAVE_AS / CLOSE / INFO`。

Pagination（impl §31 L1011-1025 / py §35 L3211-3234）：

```json
{
  "data": [],
  "pagination": {
    "has_more": true,
    "next_cursor": "opaque-cursor"
  }
}
```

所有可能产生大量数据的 Query/Result 必须分页（limit / cursor / has_more / next_cursor）；禁止无限 payload。

### B.14 Canonical Engineering Model 与 Result Normalization

Canonical entities（impl §32 L1029-1046 / py §36 L3238-3255）：`Node / Element / Material / Section / Boundary / Load / Group / Analysis / Result / Design`；Adapter 可将软件原生结构转成 Canonical Model；必须定义稳定 Schema。

Result Normalization（impl §33 L1050-1063 / py §37 L3259-3282）：MIDAS / ETABS / SAP2000 / ANSYS / OpenSees 统一为 StructAI Canonical Model：

```json
{
  "node_id": 100,
  "ux": 0.001,
  "uy": 0.002,
  "uz": -0.015
}
```

AI Client 不应该依赖 MIDAS 原始字段。

### B.15 Event Bus / Health / Metrics / Audit / Retention / Backup

Event Bus（impl §34 L1069-1093 / py §38 L3286-3316）：

```python
class EventBus(Protocol):
    async def publish(self, event): ...
    async def subscribe(self, event_type, handler): ...
```

Core Alpha：`InProcessEventBus`；事件 9 个：`TaskCreated / TaskStarted / TaskProgress / TaskCompleted / TaskFailed / TaskCancelled / AdapterConnected / AdapterDisconnected / ModelChanged`；未来可替换 Redis/NATS/Kafka 而不修改 Domain Event。

Notification（impl §35 / py §39）：

```python
class NotificationService(Protocol):
    async def notify(self, event) -> None: ...
```

未来通道 MCP notification / Webhook / WebSocket / UI / Email；Notification 不成为 Core Tool。

Quota / Rate Limit（impl §36 L1117-1134 / py §40 L3352-3379）：维度 `user / tenant / AI agent / software instance`；`max_tasks / max_concurrent_tasks / max_api_requests / max_storage / max_projects`；Core Alpha 可用内存 limiter + DB quota definition（第一阶段 InMemory，未来 Redis）。

Health / Readiness / Liveness（impl §37 L1140-1144 / py §41 L3387-3423）：`GET /livez`、`GET /readyz`、`GET /health`；Liveness = process alive；Readiness = database / registry / task engine；Health = database / task engine / adapter manager / software instances；某一个 MIDAS 不在线时 `Core = READY`、`MIDAS = UNAVAILABLE`，不得让整个服务器不可用。

Metrics 9 个（impl §37 L1148-1158 / py §42 L3431-3443）：`structai_requests_total / structai_request_duration_seconds / structai_task_total / structai_task_duration_seconds / structai_task_failed_total / structai_adapter_requests_total / structai_adapter_errors_total / structai_active_tasks / structai_mcp_connections`；推荐 Prometheus-compatible exposition。

Runtime Configuration（impl §38 L1166-1180 / py §43 L3449-3487）：`environment / host / port / database_url / log_level / task_workers / task_timeout / mcp_transport / artifact_root / retention / quota`；四类 Startup/Runtime/Persistent/Secret；Secret 不进入普通 settings；UI 修改流程 `Config Service → Validation → Persist if required → Apply`。

Audit Integrity（impl §39 L1188-1207 / py §44 L3495-3507）：字段 `audit_id / timestamp / tenant_id / user_id / action / resource / result / previous_hash / entry_hash`；

```text
entry_hash =
H(previous_hash + canonical_entry)
```

HIGH/CRITICAL 高风险操作必须 Audit；用于检测篡改。

Data Retention（impl §40 L1215-1224 / py §45 L3515-3529）：`task_retention_days / trace_retention_days / audit_retention_days / artifact_retention_days / session_retention_days / event_retention_days`（impl 多 event_retention_days）；Audit 默认不允许普通用户删除；删除必须服从审计与法规策略。

Backup / Restore（impl §41 L1230-1250 / py §46、§81）：Core Alpha = `SQLite backup + Artifact metadata + Registry data`；执行 `backup → integrity check`；恢复 `restore → migration check → registry validation → health check`。

Migration Safety（impl §42 L1256-1275 / py §47 L3560-3585）：所有结构变更必须 Alembic migration；禁止启动时静默 `ALTER TABLE`；Migration 必须 `versioned / checksum / tested / rollback strategy documented`；生产升级前 `backup → migration → integrity check → registry validation`；失败 `rollback / restore`。

Graceful Shutdown（impl §54 L1571-1593 / py §65 L4076-4092）：
impl：`stop accepting new work → mark server draining → stop task scheduling → wait bounded time → persist task state → release owned locks → close adapters → close DB → close MCP transport`；未完成 Task 必须能够在下次启动进入 Recovery。
py：`Stop new requests → Stop scheduler → Stop accepting tasks → Wait / recover active tasks → Disconnect adapters → Flush audit/events → Close DB → Exit`。

### B.16 统一错误契约（错误码清单，共 20 个）

impl §43（L1282-L1301）与 py §48（L3594-L3619）完全一致：

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

MCP Error Mapping（py §49 L3624-3654）：`Adapter → StructAI Error → Application Response → MCP Response`；AI 默认只看到 `StructAI normalized error`；需要诊断时才返回：

```json
{
  "cause": {
    "provider": "MIDAS",
    "native_code": "...",
    "native_message": "..."
  }
}
```

### B.17 MCP SDK 集成方式（stdio / streamable http）

impl §44（L1308-L1331）/ py §50（L3660-L3682）：

```text
SDK 负责：MCP Protocol / Session / Tool Discovery / Tool Registration / Tool Invocation / Cancellation / Progress
StructAI 负责：Tool Registry / Execution Pipeline / Task / Security / Adapter / Result / Audit / Trace
```

py §50 明确：Tool Handler 不实现工程业务；调用链 `MCP Tool → ToolRequest → ExecutionService`。

MCP Progress（impl §45 L1337-1343 / py §51 L3688-3708）：`Task Engine → progress event → MCP progress notification`（示例 0 / 25 / 43 / 80 / 100）；**Task Engine 是唯一进度来源**。

MCP Cancellation（impl §45 L1345-1361 / py §52 L3714-3728）：

```text
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

不能直接终止 Python process；无法真实取消时必须返回 `cancellation_requested`，而不是伪造 CANCELLED。

传输：项目结构含 `app/interfaces/mcp/server.py`、`app/interfaces/http/`；实现顺序第 31 步 STDIO、第 32 步 Streamable HTTP；DoD 含 `[ ] STDIO`、`[ ] Streamable HTTP`。MCP 依赖为"实现时的官方稳定 MCP Python SDK，并锁定实际验证通过的版本；不得自行重新实现 MCP 协议"（py L2039-2040）。

### B.18 9 Tool Layer 与 Tool 注册

9 个 Tool（impl §47 L1413-L1421 / py §53 L3737-3745）：
`engineering_doc / engineering_model_query / engineering_model_assign / engineering_model_delete / engineering_model_build / engineering_view / engineering_result / engineering_design / engineering_analysis`

Handler 必须很薄（impl §46 L1390-1397）：`parse request → build context → call Application Service → map response`；禁止在 Handler 出现 `SQL / RBAC calculation / Adapter lookup / Task implementation`。
py §53：每个 Tool 是 `thin wrapper`，最终 `return await execution_service.execute(...)`。

ToolDefinition / OperationDefinition / CapabilityDefinition（impl §10 L410-448 / py §28 L2989-3002）：

```python
@dataclass(frozen=True)
class ToolDefinition:
    name: str
    version: str
    category: str
    description: str
    risk_level: RiskLevel
    execution_mode: ExecutionMode

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

@dataclass(frozen=True)
class CapabilityDefinition:
    code: str
    category: str
    name: str
    version: str = "1.0"
    description: str = ""
```

Capability 不允许出现 `MIDAS / CSI / ANSYS`。

---

## C. Execution Pipeline 的步骤顺序（不可变）

py §55（L3786-L3844）"最终执行顺序冻结为"，与 impl §13（L520-L571）一致，共 **26 步**：

| # | 步骤 | 不可变理由（文档依据 / 标注"推断"者为据文档约束推导） |
|---|---|---|
| 1 | MCP Request | 入口；SDK 负责 Protocol/Session（L1308-1318） |
| 2 | Authenticate | 身份必须由服务器生成（L217）；客户端不得声明 user_id/tenant_id/roles/permissions（L259-266） |
| 3 | Build Server IdentityContext | 必须在 Auth 之后才能由服务器构造（L2163-2169） |
| 4 | Build ExecutionContext | IdentityContext 是其字段（L2148-2157） |
| 5 | Resolve Tool | Tool 必须先存在才能解析 Operation（Tool→Operation 层级，L1721-1725） |
| 6 | Resolve Operation | Operation 引用 tool 字段（L424-425） |
| 7 | Resolve Resource | Resource Resolver 是所有跨租户访问的拦截点，必须在权限/锁之前（L2355、L368） |
| 8 | Schema Validation | 严格顺序 Input→Schema→Engineering（L502-506）；错误 STRUCTAI-1100 |
| 9 | Engineering Validation | 在 Schema 之后（L504-506）；错误 STRUCTAI-1200 |
| 10 | Preconditions | OperationDefinition 的 preconditions 必须在执行前评估（L578-596） |
| 11 | Effective Permission | 权限在 Preconditions 之后、Quota 之前（L538-542）；错误 STRUCTAI-4000/4200 |
| 12 | Quota / Rate Limit | 在 Confirmation 之前，避免超配额请求进入确认流程（L542-544） |
| 13 | Confirmation | 高风险操作需要 confirmation_token（L926、STRUCTAI-4100）；在 Idempotency 之前，避免无效确认占用幂等键（推断） |
| 14 | Idempotency | 必须在 Concurrency/Lock 之前：重复请求应直接返回已有结果，不得先抢锁（推断，依据 L951-964） |
| 15 | Concurrency / Resource Lock | 在 Capability 与 Task 之前，避免拿不到锁却已启动任务（推断，L618 锁与 Task 生命周期关联） |
| 16 | Capability Check | 在 Task/Transaction 之前，避免无能力任务入队（推断，L512-514、STRUCTAI-3000） |
| 17 | Task / Transaction | 事务语义由 OperationDefinition 声明（L3870-3875） |
| 18 | Adapter | Adapter 是唯一的软件访问通道（L1721-1734） |
| 19 | Result Normalization | 必须在 Postconditions 之前，使 Postconditions 判定基于 Canonical Result（推断，L3827-3829） |
| 20 | Postconditions | 必须在 Release Lock 之前，锁与 Task 生命周期绑定（L618、L3830-3831） |
| 21 | Release Lock | 在 Persist Result 之前（L3831-3833） |
| 22 | Persist Result | 在 Audit/Trace/Event 之前，保证审计对象已持久化（推断） |
| 23 | Audit | 高风险必须 Audit（L1207）；在响应前（L3835-3841） |
| 24 | Trace | 与 Audit 同层，在响应前（L3837） |
| 25 | Event | 领域事件在响应前发布（L3839） |
| 26 | MCP Response | 终点；`这是 Core Alpha 的最终标准执行链`（L3844） |

文档原文："**严格顺序**"（L499）、"**最终执行顺序冻结为**"（L3788）、"这是 Core Alpha 的最终标准执行链"（L3844）、"因此从第五份开始，不再反复修改 Core 架构"（L4662）。

另有 impl §13 的 7 步抽象顺序（L502-514）：`Input → Schema Validation → Engineering Validation → Permission → Confirmation → Capability → Execution`。

事务/回滚优先级（py §56 L3852-3868）：`Native Transaction → Snapshot / Restore → Compensating Actions → Best Effort`，适用于 `BUILD.COLUMN / BUILD.FRAME / BUILD.STEEL_FRAME`。

---

## D. 项目结构与依赖

### D.1 目录树（impl §3 L93-L164 = py §3 L1907-L1987，原样）

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

依赖方向（impl L168-173）：`Interface → Application → Domain`、`Infrastructure → Domain/Application Interfaces`；禁止反向依赖。
9 Tool 文件（impl §46 L1376-1385）：`document.py / model_query.py / model_assign.py / model_delete.py / model_build.py / view.py / result.py / design.py / analysis.py`（位于 `app/interfaces/mcp/tools/`）。

### D.2 Python 版本

`Python >= 3.12`（impl L71、py L1995）；`requires-python = ">=3.12"`（py L2004）。

### D.3 依赖清单（py §4 L2001-L2035，原样摘录）

```toml
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

```toml
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

MCP 依赖（py L2039-2040）："使用实现时的官方稳定 MCP Python SDK，并锁定实际验证通过的版本。不得自行重新实现 MCP 协议。"
impl §2 技术基线（L71-82）：`Python >= 3.12 / FastAPI / Pydantic v2 / SQLAlchemy 2.x / aiosqlite / Alembic / httpx / jsonschema / structlog / pytest / pytest-asyncio`。

---

## E. 所有 MIDAS API 引用（穷尽性核查）

### E.1 结论（重要）

**在本次范围（第 1-4673 行，即 impl + py 两个子文档）内，不存在任何 MIDAS API 接口路径、MIDAS 表代码、MIDAS HTTP 方法。** 两份子文档刻意把 MIDAS 排除在 Core 之外（impl §10 L450-456 "Capability 不允许出现 MIDAS/CSI/ANSYS"；impl §57 L1696-1704 红线；py §85 L4596 "Capability 不绑定 MIDAS"）。

全文（28891 行）grep 结果：
- 正则 `/db/|/doc/|/ope/|/view/|/post/|/design/|/midas/` → 仅 1 处命中：**L18502 `structai://schema/design/steel/v1`**（是 StructAI 的 Schema URI，不是 MIDAS API）。
- 正则 `(?i)/anal/` → 命中 **L5598 `"path": "/anal/STATIC"`、L7597 `REST POST /anal/STATIC`、L8619 `POST /anal/STATIC`、L15370 `"/anal/STATIC"`、L19899 `/anal/STATIC`** —— 全部位于 **L4674 之后的子文档**（blue 等），不属于本次两个子文档。
- 正则 `(GET|POST|PUT|DELETE|PATCH)\s+/` 在本范围内仅命中 **L3388-3390 `GET /livez`、`GET /readyz`、`GET /health`**（这是 StructAI 自身的 HTTP 健康检查端点，非 MIDAS API）。
- 未发现任何 `api.midas*`、`/TABLES`、表代码（如 `*TABLE*` 形式的 MIDAS 表名）等。

### E.2 本范围内所有 MIDAS 出现点（逐条，含小节出处）

| 行 | 小节 | 原文 | 性质 |
|---|---|---|---|
| L453 | impl §10 Capability | `MIDAS` | 禁止出现在 Capability 中的厂商名 |
| L788 | impl §22 Plugin Loader | `midas.civil = "structai_midas.adapter:CivilAdapter"` | Entry Point 示例（包名/适配器类） |
| L795 | impl §22 | `"name": "midas.civil"` | Adapter Manifest 示例 |
| L796 | impl §22 | `"vendor": "MIDAS"` | Adapter Manifest 示例 |
| L1063 | impl §33 Result Normalization | `AI Client 不应该依赖 MIDAS 原始字段。` | 归一化原则 |
| L1777 | impl §59 最终结论 | `MIDAS 只能是第一个 Adapter，而不是 Core 的架构边界。` | 架构原则 |
| L2804 | py §22 Plugin Loader | `midas.civil = "structai_midas.adapter:CivilAdapter"` | Entry Point 示例 |
| L2841 | py §23 Adapter Manifest | `"name": "midas.civil"` | Manifest 示例 |
| L2842 | py §23 | `"vendor": "MIDAS"` | Manifest 示例（product = "CIVIL NX"，supported_versions ["2025","2026"]，protocols ["REST"]） |
| L3264 | py §37 Result Normalization | `MIDAS`（与 ETABS/SAP2000/ANSYS/OpenSees 并列） | 需归一化的软件清单 |
| L3416 | py §41 Health | `某一个 MIDAS 不在线：` | 健康检查原则 |
| L3420 | py §41 | `MIDAS = UNAVAILABLE` | 实例级不可用，Core 仍 READY |
| L3649 | py §49 MCP Error Mapping | `"provider": "MIDAS"` | 错误 cause 示例 |
| L4573 | py §84 Final Architecture | `MIDAS        ETABS      OpenSees` | 架构图叶子节点 |
| L4596 | py §85 冻结原则 | `> **Capability 不绑定 MIDAS。**` | 架构原则 |
| L4669 | py §87 最终一句话 | `> MIDAS"，而是建立一个...` | 目标陈述 |

（注：L788/L795-796/L2804/L2841-2842 中的 `structai_midas` 是 Python 包名，`midas.civil` 是 entry-point 名，均非 HTTP 接口路径。）

### E.3 全文范围内真实 MIDAS API 路径（供主 Agent 参考，超出本次范围）

- **`POST /anal/STATIC`**（MIDAS 的 `ANALYSIS.STATIC` 映射）：
  - L5598 — 子文档 blue 某节：`"path": "/anal/STATIC"`
  - L7597 — 子文档 blue §88 API Mapping：`REST POST /anal/STATIC`
  - L8619 — 子文档 blue §120 MIDAS Adapter 内部结构：`POST /anal/STATIC`（同处 L8618 写 `MIDAS CIVIL NX 2026`，L8622 明确"实际接口路径和参数必须依据对应 MIDAS API Registry / API 文档注册，不能硬编码到 Core"）
  - L15370 — 更后子文档中 `"/anal/STATIC"`
  - L19899 — 更后子文档中 `/anal/STATIC`
- 全文再无其他 MIDAS 风格 REST 路径（`/db/…`、`/doc/…`、`/ope/…`、`/view/…`、`/post/TABLE`、`/design/…` 均 0 命中）。

**精确死胡同说明**：若期望在 impl/py 两个子文档中穷举 MIDAS 表代码与接口路径，答案是**不存在**——这是文档刻意的架构约束（Core 不得写入 MIDAS endpoint，见 L13569 "不允许在 Core 中出现 MIDAS endpoint"、L13284-13287 禁止项）。MIDAS 的具体 API 只从 `blue` 子文档（L4674 起）开始出现，且仅 `POST /anal/STATIC` 一处。

---

## F. 实现顺序（P0-P...）与 Definition of Done

### F.1 Core Alpha Implementation Order（impl §55 L1600-1637 = py §82 L4441-4477，37 步，完全一致）

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

（文档未使用 "P0/P1" 编号，而是 01-37 顺序号。py §64 另有 17 步启动（bootstrap）顺序，见 B.7。）

### F.2 Definition of Done

**impl §56（L1644-1688）45 项**：

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

**py §83（L4485-4527）44 项**：与 impl 完全一致，**唯一差异是没有 `[ ] SQLAlchemy 2.x` 一项**。

### F.3 其他验收/测试清单（要点）

- 测试分层（impl §51 / py §67）：unit / contract / integration / recovery / security /（+concurrency / failure / performance）/ e2e。
- Unit Tests 12 项、Contract Tests 6 项、Integration 链、Recovery 6 个 test_*、Concurrency 6 个 test_*、Security 9 个 test_*、Failure 7 个 test_*、Performance 6 项（见 A2 表 py §68-§75）。
- Failure / Recovery 必测（impl §50 L1496-1508）：adapter timeout / adapter disconnect / task worker crash / lease expiry / duplicate request / lock conflict / version conflict / permission denied / capability unavailable / schema failure / engineering validation failure / artifact failure / database restart。
- Security Tests（impl §52 L1534-1544）：cross-tenant access / forged identity context / role escalation / agent privilege escalation / expired session / revoked session / secret leakage / audit tampering / confirmation bypass / idempotency race / lock bypass。
- Code Quality（py §76）：ruff / mypy / pytest / pytest-cov / pre-commit；CI 顺序 lint → type check → unit → contract → integration → recovery → security → e2e。

---

## G. 架构红线 / 禁止项清单

### G.1 impl §57 Architecture Red Lines（L1694-1734，原样）

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

必须的依赖方向：

```text
Interface
 ↓
Application
 ↓
Domain
 ↓
Infrastructure
```

以及调用链：

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

### G.2 py 补充的禁止/必须项（逐条，含出处）

- 客户端不得直接决定 `user_id / tenant_id / roles / permissions`（L2112-2117）；`context.identity` 不得由客户端覆盖（L3779-3782）。
- Capability 不允许出现 `MIDAS / CSI / ANSYS`（impl L450-456）。
- Tool 不自行寻找 Adapter（impl L474）。
- Repository 不自行随意 commit（L2403）。
- 禁止依赖 UI 过滤做租户隔离（L2434）。
- 不得覆盖其他用户修改（L2471）。
- 不能把恢复中的 Task 直接标记为 COMPLETED（L712）；不得简单删除 RUNNING task（L4112）。
- 循环依赖必须在提交前拒绝（L726）。
- 禁止从数据库执行任意 Python（L804、L2916）；Custom Transformer 必须位于 Adapter package（L860、L2910-2914）。
- 绝不记录 secret（L912）；日志绝对禁止输出 secret（L2786）；不得记录 password / API key / token / private key（L4332-4339）。
- 禁止无限 payload / 一次返回无限数据（L1025、L3234）。
- 禁止启动时静默 ALTER TABLE（L1262-1266）。
- Registry validation 失败 → Server MUST NOT become READY（L4066-4070）。
- 一个实例（如 MIDAS）失败不能让整个 Server Not Ready / 不可用（L826、L3416-3423）。
- 不能直接终止 Python process 来取消任务（L3728）；无法真实取消时返回 `cancellation_requested`（L1355-1361）。
- Domain Service 不得访问 HTTP / SQLAlchemy / FastAPI / MCP SDK（L3993-4000）。
- Interface 层不得直接访问 SQLAlchemy / Adapter / Filesystem（L4030-4036），必须经过 Application Service。
- Tool Handler 禁止 SQL / RBAC calculation / Adapter lookup / Task implementation（L1399-1406）。
- 不得用性能优化破坏抽象层（L4261）。
- 禁止反向依赖（L173）；Audit 默认不允许普通用户删除（L3529）。
- 新增软件只加 Adapter + Capability Mapping + Operation Mapping + API Registry，不修改 9 个 Tool Contract（L2819-2831）。
- UI 只能消费 Application / Management API，不能反向定义 Core（L4616）。
- 下一份文档不得重新定义 Core Runtime（L1769）；第五份每个 Tool 必须引用本文件冻结的 16 项能力（L4642-4660）。

---

## 附：范围与校验

- 已逐行读取 L1-L4700（覆盖 L1-L4673 全部内容，无跳读）。
- 关键边界核对：impl 结束于 L1779，L1781 `# 完整收录：py` 起为第二子文档，L4673 为 py 末尾空行，L4674 `# 完整收录：blue` 起为第三子文档。
- 未修改工作区任何文件；本报告写在会话 scratch 目录。
