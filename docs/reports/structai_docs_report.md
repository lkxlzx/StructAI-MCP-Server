# StructAI MCP Server — 文档精读报告（01 架构 / 05 Adapter SDK）

范围：`docs/01_STRUCTAI_MCP_V2_ARCHITECTURE.md`（3420 行，内嵌 dev + db 两份子文档，逐行读完）与
`docs/05_STRUCTAI_MCP_V2_ADAPTER_SDK.md`（2233 行，逐行读完）。报告用中文。

---

## A. 章节地图

### A.1 `01_..._ARCHITECTURE.md`（3420 行）

顶层骨架：
- L1 `# 01_STRUCTAI_MCP_V2_ARCHITECTURE.md — 总体架构与数据模型` — V2.0 Consolidated Architecture Baseline；Core First / Software Agnostic / UI Later；统一 9 Tool / Multi-Tenant / Registry / Canonical Model / 数据库 / 权限 / 任务 / Adapter 边界。
- L7 `# 内容保全说明` — 六文档体系重组，原文不删除。
- L12 `# 完整收录：dev` — 内嵌「总体架构与数据模型（dev）」子文档起点。
- L1401 `# 完整收录：db` — 内嵌「Core 数据模型与数据库设计规范（db）」子文档起点。
- L3417 `# 来源映射` — dev/db 均「完整收录」。

**实际二级标题（`##`）**：
- L15 `## 核心开发文档 — Revision V2`
- L70 `## 2.1 工程语义优先`；L93 `## 2.2 Tool 不绑定 API`；L118 `## 2.3 软件差异由 Adapter 消化`；L140 `## 2.4 9 Tool 固定为第一阶段核心接口`
- L227/238/251/264/290/309/321/332/342 `## engineering_doc / engineering_model_query / engineering_model_assign / engineering_model_delete / engineering_model_build / engineering_view / engineering_result / engineering_design / engineering_analysis`（9 个 Tool 各自的 Operation 清单）
- L1405 `## Core 数据模型与数据库设计规范`

**dev 子文档章节（`#`，L24–L1398）**：1 目标(24)｜2 核心原则(68)｜3 总体架构(156)｜4 9 个 Core Tool(192)｜5 Tool Operation(225)｜6 Operation Registry(356)｜7 Capability Registry(385)｜8 Software Registry(442)｜9 Adapter(481)｜10 ExecutionContext(523)｜11 Security Model(556)｜12 Resource Resolver(590)｜13 Validation(607)｜14 Task Engine(685)｜15 Lock/Concurrency(732)｜16 Idempotency(775)｜17 Dry Run/Batch(798)｜18 Artifact/Document(834)｜19 Result Normalization(868)｜20 API Registry(887)｜21 Error Contract(933)｜22 Unified Response(974)｜23 MCP Discovery(1018)｜24 MCP Progress/Cancellation(1038)｜25 Health/Metrics(1062)｜26 Event Bus(1090)｜27 Audit/Trace(1122)｜28 UI 与 AI 工程助手边界(1155)｜29 Mock Adapter(1192)｜30 第一条完整 E2E(1219)｜31 第二软件验证(1241)｜32 Core Alpha 验收(1270)｜33 UI 后续阶段(1303)｜34 开发顺序(1322)｜35 最终架构红线(1356)｜36 最终原则(1391)。

**db 子文档章节（`#`，L1414–L3420）**：1 设计目标(1414)｜2 数据库技术选型(1438)｜3 数据库逻辑分层(1472)｜4 核心实体关系(1518)｜5 主键设计(1559)｜6 Tool Registry(1579)｜7 Operation Registry(1624)｜8 Capability Registry(1674)｜9 Operation→Capability(1743)｜10 Software Vendor(1787)｜11 Software Product(1820)｜12 Software Version(1871)｜13 Software Instance(1914)｜14 Adapter Registry(1974)｜15 Adapter→Software Version(2014)｜16 Adapter Capability(2047)｜17 Operation API Mapping(2089)｜18 一个 Operation 对多个 API(2158)｜19 API Registry(2214)｜20 Schema Registry(2257)｜21 Schema Version(2292)｜22 Schema URI(2324)｜23 Task(2344)｜24 Task Steps(2393)｜25 Idempotency(2437)｜26 Trace(2484)｜27 Trace Span(2509)｜28 Audit Log(2553)｜29 Permission(2593)｜30 Role(2626)｜31 Role Permission(2659)｜32 Confirmation Token(2679)｜33 System Settings(2709)｜34 数据库索引(2742)｜35 删除策略(2786)｜36 Registry 生命周期(2813)｜37 数据一致性(2840)｜38 Registry 加载流程(2875)｜39 Registry Cache(2917)｜40 Registry Reload(2945)｜41 Initial Seed(2971)｜42 Seed 原则(3003)｜43 Migration(3029)｜44 数据库初始化(3063)｜45 Core Alpha 最小数据库(3087)｜46 Mock Adapter 数据边界(3133)｜47 工程模型数据是否进入 Core DB(3165)｜48 核心边界(3211)｜49 完整数据流(3241)｜50 第三份完成标准(3301)｜51 与第二份文档的关系(3342)｜52 架构总原则(3386)｜Appendix A V2.0 数据库多用户修订说明(3400)。

### A.2 `05_..._ADAPTER_SDK.md`（2233 行）

- L1 标题 — 通用 Adapter SDK；定义 EngineeringSoftwareAdapter / Manifest / Plugin Loader / Adapter Manager / Capability / Version / Registry / Transformer / Health / Error / Cancellation / Mock 与 Contract Test。
- L7 内容保全说明｜L12 完整收录：adapter｜L14 StructAI MCP Server V2.0｜L15 第十三份文档：Core Alpha Mock Adapter + Adapter Manager + Plugin Loader。
- **唯一 `##`**：L16 `## P46-P56：Adapter Base / Manifest / Manager / Plugin Loader / Mock Adapter / Model Store / Capability / Lifecycle / Health / Error / Cancellation`。
- 章节（`#`）：1 本批次范围(71)｜2 Adapter 总体职责(89)｜3 Adapter Architecture(123)｜4 Adapter Interface(146)｜5 Adapter Context(215)｜6 Adapter Manifest(246)｜7 Manifest Python Model(272)｜8 Adapter Lifecycle(290)｜9 Lifecycle State(316)｜10 Adapter Base State(334)｜11 Adapter Initialize(381)｜12 Adapter Manager(399)｜13 Resolve Adapter(426)｜14 Adapter Instance Registry(464)｜15 Adapter Instance ORM(489)｜16 Plugin Loader(529)｜17 Plugin Loader 实现(548)｜18 Plugin Loader 安全(577)｜19 Plugin Manifest Validation(604)｜20 Version Matching(635)｜21 Capability Detection(676)｜22 Capability Provider(698)｜23 Runtime Capability(721)｜24 Capability Cache(741)｜25 Health Check(767)｜26 Health 不等于 Capability(782)｜27 Mock Model Store(805)｜28 MockModelStore(842)｜29 Mock Adapter(866)｜30 Mock Capabilities(883)｜31 Mock Connect(921)｜32 Mock Version(935)｜33 Mock Health(944)｜34 Mock Node Create(960)｜35 Mock Node Query(995)｜36 Mock Element Create(1025)｜37 Mock Column Builder(1068)｜38 BUILD.COLUMN(1102)｜39 Boundary Assignment(1169)｜40 Load Assignment(1200)｜41 Mock Static Analysis(1242)｜42 Mock Static Analysis Algorithm(1260)｜43 Mock Material(1294)｜44 Mock Section(1319)｜45 Mock Static(1341)｜46 Mock Displacement(1369)｜47 Mock Steel Design(1412)｜48 Mock Operation Dispatcher(1433)｜49 Mock Error Normalization(1488)｜50 Adapter Error 原则(1540)｜51 Adapter Cancellation(1567)｜52 Adapter Health Manager(1589)｜53 Health 隔离原则(1613)｜54 Adapter Manager Lifecycle(1641)｜55 Adapter Shutdown(1667)｜56 Adapter Manager Resolve by SoftwareInstance(1685)｜57 Adapter 与 Capability Resolver(1720)｜58 Adapter 与 API Registry(1742)｜59 Mock API Registry(1785)｜60 Adapter Test(1811)｜61 Mock Integration Test(1829)｜62 完整 Mock E2E(1847)｜63 Mock E2E 预期(1878)｜64 为什么 Mock 必须先于 MIDAS(1908)｜65 Mock Adapter 不允许成为生产计算器(1943)｜66 Adapter Contract Test(1972)｜67 Adapter Contract 的价值(2027)｜68 Adapter Manager Definition of Done(2053)｜69 当前 Core Alpha 已形成的完整链(2082)｜70 下一份文档(2122)｜71 本批次最终结论(2171)｜来源映射(2231)。

---

## B. 架构与数据模型关键决策（来自 01）

### B.1 9 个 Core Tool（dev §4，L192-204）
| Tool | 领域 | 默认风险 | 默认执行 |
|---|---|---|---|
| engineering_doc | 文档 | MEDIUM | SYNC/ASYNC |
| engineering_model_query | 模型查询 | LOW | SYNC |
| engineering_model_assign | 模型修改 | MEDIUM | SYNC/ASYNC |
| engineering_model_delete | 模型删除 | HIGH | ASYNC |
| engineering_model_build | 工程建模 | HIGH | ASYNC |
| engineering_view | 可视化 | LOW | SYNC |
| engineering_result | 结果 | LOW | SYNC |
| engineering_design | 设计验算 | HIGH | ASYNC |
| engineering_analysis | 分析计算 | HIGH | ASYNC |

Risk 取值 LOW/MEDIUM/HIGH/CRITICAL；Execution 取值 SYNC/ASYNC/STREAM。
各 Tool 的 Operation（dev §5，L225-352）：doc=NEW/OPEN/SAVE/SAVE_AS/CLOSE/INFO；query=MODEL.QUERY、MODEL.{NODE,ELEMENT,MATERIAL,SECTION,BOUNDARY,LOAD,GROUP}.QUERY；assign=MODEL.NODE.CREATE/UPDATE、MODEL.ELEMENT.CREATE/UPDATE、MODEL.{MATERIAL,SECTION,BOUNDARY,LOAD}.ASSIGN；delete=MODEL.{NODE,ELEMENT,LOAD,BOUNDARY,GROUP,MATERIAL,SECTION}.DELETE（删除须经 Permission→Risk→Confirmation→Audit→Execution）；build=BUILD.{NODE_GRID,BEAM,COLUMN,FRAME,TRUSS,SLAB,WALL,FOUNDATION,STEEL_FRAME}、MODEL.{COPY,MOVE,MIRROR,PATTERN,GENERATE_GRID}；view=VIEW.{MODEL,DEFORMED_MODEL,REACTION,DISPLACEMENT,STRESS,FORCE,MODE_SHAPE}；result=RESULT.NODE.{DISPLACEMENT,REACTION}、RESULT.ELEMENT.{FORCE,STRESS}、RESULT.MODE.SHAPE、RESULT.ANALYSIS.SUMMARY；design=DESIGN.{STEEL,CONCRETE,FOUNDATION,CODE_CHECK,OPTIMIZE}；analysis=ANALYSIS.{STATIC,MODAL,SEISMIC,SPECTRUM,BUCKLING,TIME_HISTORY,NONLINEAR}。

### B.2 Tool / Operation / Capability 三层关系与区别
- 层次链（dev §2.2，L93-116）：`Tool → Operation → Capability → API Registry → Adapter → Software`；禁止 `Tool → /db/NODE`、`Tool → /anal/STATIC`。
- Tool：面向工程的稳定接口（9 个），表达 document/model/build/view/result/design/analysis，不绑定 MIDAS/CSI/ANSYS/OpenSees（§2.1，L70-91）。
- Operation：Core 的稳定工程语义（§6，L356-381），字段含 code/tool/execution_mode/risk_level/input_schema/output_schema；**不含** MIDAS URL、ETABS COM method、OpenSees command。
- Capability：必须软件无关（§7，L385-438），分模型(READ/WRITE/DELETE)、分析、结果、设计四类。
- 关系图（db §4，L1518-1532）：`Tool └ Operation └ Capability ├ Software Version └ Adapter └ API Registry`。
- Operation→Capability（db §9，L1743-1783）：一个 Operation 依赖多个 Capability（BUILD.COLUMN 依赖 MODEL.NODE.WRITE / ELEMENT.WRITE / MATERIAL.WRITE / SECTION.WRITE / BOUNDARY.WRITE）；表 operation_capabilities，UNIQUE(operation_id, capability_id)。

### B.3 ExecutionContext（dev §10，L523-552）
结构：`IdentityContext / SoftwareContext / ProjectContext / ExecutionContext`。
- 身份必须由服务器 Authentication 生成；客户端**不能**声明 user_id / tenant_id / roles / permissions；最多请求 project_id、software_instance_id；服务器必须经 Resource Resolver 验证归属。
- 完整 Runtime Pipeline（dev §13，L627-681）：MCP Request→Authenticate→IdentityContext→ExecutionContext→Resolve Tool→Resolve Operation→Resolve Resource→Schema Validation→Engineering Validation→Preconditions→Effective Permission→Quota→Confirmation→Idempotency→Concurrency/Lock→Capability→Task/Transaction→Adapter→Result Normalization→Postconditions→Release Lock→Persist Result→Audit→Trace→Event→MCP Response。

### B.4 安全模型
- 认证/会话：Authentication 生成 IdentityContext；Session/Refresh Token 采用 Hash 保存，禁止明文持久化（Appendix A，L3406）。
- RBAC / Effective Permission（§11，L556-587）：User→Global Roles→Tenant Membership/Roles→Project Membership/Roles→Resource ACL→Explicit Deny→Effective Permissions。AI Agent：`Effective User Permissions ∩ Agent Permissions = Effective Agent Permissions`；**Agent 不得提升权限**。
- Tenant 隔离：Resource Resolver（§12，L590-603）统一解析 Project/Model/Document/Software Instance/Task/Artifact；**所有跨租户资源访问必须在此阻断**；Task/Trace/Audit 必须绑定 tenant_id/user_id/project_id（Appendix A，L3407）。
- Confirmation（db §32，L2679-2705）：高风险操作（MODEL.DELETE、DESIGN.MODIFY 等）返回 STRUCTAI-4100 CONFIRMATION_REQUIRED；确认后携带 confirmation_token，服务器验证 Token 后才执行。
- Permission 预置（db §29，L2593-2622）：MODEL_READ/MODEL_WRITE/MODEL_DELETE、ANALYSIS_EXECUTE、DESIGN_EXECUTE/DESIGN_MODIFY、RESULT_READ、DOCUMENT_READ/DOCUMENT_WRITE、SYSTEM_ADMIN、TOOL_TEST、API_TEST。
- Role（db §30，L2626-2655）：ADMIN/ENGINEER/OPERATOR/VIEWER/AI_AGENT；AI_AGENT 默认 MODEL_READ/MODEL_WRITE/ANALYSIS_EXECUTE/RESULT_READ，不是超级管理员。
- 多用户修订（Appendix A，L3404-3411）：升级为 User+Tenant+Project+Role+Permission+Resource ACL；user_identities 支持 OAuth/OIDC/SSO；AI Agent 独立身份；Registry 支持 Global/Tenant 两级；即使只有一管理员也必须建默认 Tenant。

### B.5 任务引擎 / 锁 / 幂等 / Dry Run / Batch
- Task Engine（§14，L685-728）：支持 sequential/parallel/dependency/retry/timeout/cancel/resume/recovery/priority/lease/heartbeat；状态 CREATED/VALIDATING/QUEUED/RUNNING/PROCESSING/COMPLETED/FAILED/CANCEL_REQUESTED/CANCELLED/TIMEOUT/RETRYING/RECOVERING；支持 Task DAG（Step 依赖）。
- Lock/Concurrency（§15，L732-771）：资源=Software Instance/Model/Document；READ+READ 允许、READ+WRITE 阻断、WRITE+WRITE 阻断、EXCLUSIVE 阻断全部；桌面工程软件默认 SERIAL，可配 SERIAL/LIMITED/PARALLEL；可变资源支持 version+expected_version；冲突返回 STRUCTAI-1300。
- Idempotency（§16，L775-794）：用于 CREATE/BUILD/ASSIGN/DELETE/ANALYSIS/DESIGN；DB 唯一约束 (tenant_id, idempotency_key)；必须原子处理。
- Dry Run/Batch（§17，L798-830）：`dry_run: true` 不修改模型；Batch 用 items 数组 + atomic 标志，必须明确 atomic / non-atomic。
- 取消（§24，L1038-1058）：MCP cancellation→TaskEngine.cancel()→Adapter.cancel()；底层软件若不能真正取消必须返回真实状态，不能伪装已取消。

### B.6 错误契约与统一响应
- 错误码（§21，L933-958）：STRUCTAI-1000 Protocol｜1100 Schema Validation｜1200 Engineering Validation｜1300 Concurrency Conflict｜2000 Software Connection｜2100 Software Authentication｜2200 Software API｜2300 Software Timeout｜3000 Capability Not Supported｜4000 Permission Denied｜4100 Confirmation Required｜4200 Tenant Access Denied｜5000 Task Error｜5100 Task Timeout｜5200 Task Cancelled｜5300 Task Recovery Error｜6000 Adapter Error｜6100 Resource Locked｜6200 Artifact Error｜7000 Internal Error。
- Raw native cause 默认隐藏，形如 `{cause:{provider:"MIDAS", native_code, native_message}}`（L960-970）。
- Unified Response（§22，L974-1014）同步字段：success / request_id / trace_id / tool / operation / execution{mode,status} / data / warnings / errors / metadata；异步在 execution 中加 task_id，data=null。

### B.7 数据库设计（db 子文档）
技术：Core Alpha = SQLite + SQLAlchemy 2.x + Alembic；生产可迁移 PostgreSQL；主键统一 UUID（CHAR(36)，uuid.uuid4()，§5 L1559-1575）。数据库描述「能力和运行状态」，不复制某软件 API 结构（§1）。

逻辑分层（§3，L1472-1514）：Registry{tools,operations,capabilities,mappings}；Software{software_vendors,software_products,software_versions,software_instances}；Adapter{adapters,adapter_versions,adapter_capabilities}；Schema{schemas,schema_versions}；Execution{tasks,task_steps,idempotency_records}；Security{users,roles,permissions,role_permissions,audit_logs}；Observability{traces,trace_spans}；System{system_settings}。

**全部表名 + 用途 + 关键字段**（括号为章节/行）：
- `tools`（Tool Registry，§6 L1579）：id, name, display_name, description, risk_level, default_execution_mode, enabled, version, created_at, updated_at；UNIQUE(name)。固定注册 9 Tool。
- `operations`（Operation Registry，§7 L1624）：id, tool_id, name, display_name, description, category, risk_level, execution_mode, input_schema_id, output_schema_id, enabled, version, created_at, updated_at；UNIQUE(tool_id, name)。
- `capabilities`（Capability Registry，§8 L1674）：id, code, name, description, category, direction, risk_level, enabled, created_at, updated_at。
- `operation_capabilities`（Operation→Capability，§9 L1743）：id, operation_id, capability_id, required, created_at；UNIQUE(operation_id, capability_id)。
- `software_vendors`（§10 L1787）：id, name, display_name, description, website, enabled, created_at, updated_at（MIDAS/CSI/ANSYS/Dassault Systemes/OpenSees）。
- `software_products`（§11 L1820）：id, vendor_id, name, display_name, product_type, description, enabled, created_at, updated_at；UNIQUE(vendor_id, name)。
- `software_versions`（§12 L1871）：id, product_id, version, release_date, api_version, capability_snapshot, enabled, created_at, updated_at（软件版本 ≠ API 版本，必须保留 api_version）。
- `software_instances`（§13 L1914）：id, name, software_version_id, host, port, protocol, endpoint, credential_ref, status, last_health_check, metadata, enabled, created_at, updated_at；**禁止保存明文 API Key**，只存 credential_ref（如 secret://software/civil_01/api_key）。
- `adapters`（Adapter Registry，§14 L1974）：id, name, vendor, product, module, class_name, version, status, priority, enabled, config_schema_id, created_at, updated_at（midas.civil/midas.gen/csi.etabs/csi.sap2000/opensees.default）。
- `adapter_versions`（Adapter→Software Version，§15 L2014）：id, adapter_id, software_version_id, compatibility, priority, enabled。
- `adapter_capabilities`（Adapter Capability，§16 L2047）：id, adapter_id, software_version_id, capability_id, support_level, enabled, metadata；support_level=FULL/PARTIAL/READ_ONLY/EXPERIMENTAL/UNSUPPORTED。
- `operation_api_mappings`（Operation API Mapping，§17 L2089）：id, operation_id, software_version_id, adapter_id, protocol, method, path, native_operation, request_transform, response_transform, timeout, retry_policy, enabled, created_at, updated_at；一个 Operation 可映射多 API，用 sequence 定序（§18）。
- `api_endpoints`（API Registry，§19 L2214）：id, software_version_id, name, protocol, method, path, operation_name, description, request_schema_id, response_schema_id, authentication_type, timeout, enabled, metadata, created_at, updated_at。
- `schemas`（Schema Registry，§20 L2257）：id, name, namespace, schema_type, description, current_version, created_at, updated_at（EngineeringNode/Element/Material/Section/Load、AnalysisRequest/Result）。
- `schema_versions`（Schema Version，§21 L2292）：id, schema_id, version, schema_json, status, created_at；禁止覆盖历史版本。Schema URI 规范 `structai://schema/{domain}/{name}/v{version}`（§22）。
- `tasks`（Task，§23 L2344）：id, task_id, request_id, trace_id, parent_task_id, tool, operation, software_instance_id, status, progress, priority, idempotency_key, input_data, result_data, error_data, created_at, started_at, completed_at, updated_at。
- `task_steps`（Task Steps/DAG，§24 L2393）：id, task_id, step_id, parent_step_id, sequence, name, operation, status, progress, input_data, output_data, error_data, started_at, completed_at。
- `idempotency_records`（§25 L2437）：id, idempotency_key, request_hash, request_id, task_id, status, response_data, expires_at, created_at；UNIQUE(idempotency_key)。
- `traces`（Trace，§26 L2484）：id, trace_id, request_id, session_id, task_id, root_span_id, status, started_at, completed_at, metadata。
- `trace_spans`（Trace Span，§27 L2509）：id, trace_id, span_id, parent_span_id, name, component, status, start_time, end_time, duration_ms, attributes, error_data。
- `audit_logs`（Audit Log，§28 L2553）：id, user_id, request_id, trace_id, task_id, action, resource_type, resource_id, result, ip_address, user_agent, details, created_at；至少记录 DELETE/BUILD/ANALYSIS/DESIGN/权限修改/API Test/软件配置修改；Audit 用 previous_hash + entry_hash 形成完整性链（§27 dev）。
- `permissions`（§29 L2593）、`roles`（§30 L2626）、`role_permissions`（§31 L2659）。
- `system_settings`（§33 L2709）：id, key, value, value_type, scope, description, updated_at（server.host/port、task.max_workers、task.default_timeout、logging.level、security.require_confirmation）。
- （Appendix A 新增，未给字段）`user_identities`、Session/Refresh Token 表、Tenant/Project/Resource ACL 相关表、Global/Tenant 两级 Registry。
- 索引（§34 L2742）：tools.name；operations.tool_id/name；capabilities.code；software_products.vendor_id；software_versions.product_id；software_instances.software_version_id；operation_api_mappings.operation_id/software_version_id；tasks.task_id/request_id/trace_id/status；trace_spans.trace_id；audit_logs.trace_id/request_id。
- 最小库（§45 L3087）：上表除 user_identities 外全列；Security 最小 = users/roles/permissions/role_permissions。
- Registry 生命周期（§36 L2813）：DRAFT/ACTIVE/DISABLED/DEPRECATED；删除策略（§35）用 enabled/deleted_at 软删除，不物理删除。
- Registry 加载/缓存/重载（§38-40）：启动加载 DB→内存 Registry；Reload 走 Validate→Build Temporary Registry→Atomic Swap，不得半加载替换。

---

## C. Adapter SDK 关键接口（来自 05）

### C.1 Adapter 接口方法签名（§4，L146-211；文件 `app/infrastructure/adapters/base/adapter.py`）
```python
from abc import ABC, abstractmethod

class EngineeringSoftwareAdapter(ABC):

    name: str
    vendor: str
    product: str

    @abstractmethod
    async def connect(self, config: dict) -> None: ...
    @abstractmethod
    async def disconnect(self) -> None: ...
    @abstractmethod
    async def health_check(self) -> dict: ...
    @abstractmethod
    async def get_version(self) -> str: ...
    @abstractmethod
    async def get_capabilities(self) -> list[str]: ...
    @abstractmethod
    async def execute(self, operation: str, parameters: dict, context) -> dict: ...
    @abstractmethod
    async def cancel(self, task_id: str) -> None: ...
    @abstractmethod
    async def normalize_error(self, error: Exception) -> dict: ...
```
Adapter 负责（§2，L89-105）：Connection/Authentication/Version/Capability Detection/Operation Mapping/Parameter Transform/Native Execution/Response Transform/Error Normalization/Cancellation/Health。Adapter 不负责：MCP/RBAC/Authentication Context/Tenant Isolation/Task Lifecycle/Global Idempotency/Global Lock/AI/UI。

AdapterContext（§5，L215-242，frozen/slots dataclass）：software_instance_id, product, version, tenant_id, project_id | None, task_id | None；**不携带** password/session token/global permissions/raw client request。

BaseAdapter（§10，L334-377）状态流转：connect() → state=CONNECTING → _connect() → CONNECTED → _initialize() → READY；异常置 ERROR。disconnect() 在 DISCONNECTED/CREATED 时直接返回，否则 DISCONNECTING→_disconnect()→DISCONNECTED。Adapter Initialize（§11，L381-395）：connect→version detection→capability detection→health check→READY。

### C.2 AdapterManifest 字段（§6/§7，L246-286）
JSON 示例字段：name, vendor, product, versions[], protocols[], capabilities[]。
Python 模型：
```python
@dataclass(frozen=True, slots=True)
class AdapterManifest:
    name: str
    vendor: str
    product: str
    supported_versions: tuple[str, ...]
    protocols: tuple[str, ...]
    capabilities: tuple[str, ...]
```
Mock manifest 例：name=structai.mock, vendor=StructAI, product=MockEngineering, versions=[1.0], protocols=[IN_PROCESS]。

### C.3 生命周期状态机（§8/§9，L290-330）
CREATED → CONNECTING → CONNECTED → READY → DISCONNECTING → DISCONNECTED，另有错误态 ERROR。
```python
class AdapterState(StrEnum):
    CREATED = "CREATED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    READY = "READY"
    DISCONNECTING = "DISCONNECTING"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"
```
Manager 生命周期（§54，L1641-1663）：Plugin Loader→Load Adapters→Validate Manifest→Register→Create Instances→Connect→Health Check→Capability Detection→READY。
Shutdown（§55，L1667-1681）：STOP→Reject new execution→Wait current tasks→Disconnect adapters→Release resources→Shutdown。

### C.4 Plugin Loader 加载与校验规则（§16-§20，L529-674）
- Python Entry Point 组 `structai.adapters`：
```toml
[project.entry-points."structai.adapters"]
mock = "structai_mock.adapter:MockAdapter"
# 未来: midas = "structai_midas.adapter:MidasAdapter"; csi = "...CSIAdapter"; ansys = "...AnsysAdapter"
```
- 实现（§17，L548-573）用 `from importlib.metadata import entry_points`，`entry_points(group="structai.adapters")` 遍历，`adapter_cls = entry.load(); adapter = adapter_cls()`。
- 安全（§18，L577-600）：禁止从数据库直接执行 Python code/eval/exec；DB 只存 adapter name/package/version/configuration；代码必须来自 installed Python package。
- Manifest 校验（§19，L604-631）：validate_manifest 校验 name/vendor/product/supported_versions 非空，否则 ConfigurationError。
- 版本匹配（§20，L635-672）：严格优先 Exact Version；requested=2026 且 supported=[2025,2026] 选 2026；requested=2027 无兼容声明则 reject，不能偷偷用 2026。
- Adapter Manager（§12/§13，L399-460）：register 以 (vendor, product, name) 为 key；resolve 找不到抛 AdapterNotFoundError；推荐用 SoftwareInstance→adapter_id 查找。Adapter Instance Registry（§14，L464-485）区分 Adapter Package / Adapter Instance / Software Instance；AdapterInstanceORM（§15，L489-525）表 adapter_instances（id, software_instance_id unique, adapter_name, state, last_health_at, error_json）。resolve_for_instance（§56，L1685-1716）经 software_repository.get_instance 查实例，找不到抛 NotFoundError/AdapterNotFoundError。

### C.5 Capability 探测与缓存规则（§21-§26，L676-801）
- 来源：Static Manifest + Version Mapping + Runtime Detection；最终状态 SUPPORTED/UNSUPPORTED/UNKNOWN。
- AdapterCapabilityProvider.detect（§22，L698-717）调用 adapter.get_capabilities() 并全部标 SUPPORTED。
- Runtime Capability（§23，L721-738）：若 Adapter 能动态检测（GET capabilities）必须优先用 runtime；否则用 Manifest + Version Registry。
- Capability Cache（§24，L741-763）键：software_instance_id, capability, status, checked_at, expires_at；Adapter reconnect 或 Version change 时 invalidate。
- Health（§25，L767-777）返回 {healthy, state, version, latency_ms}；§26（L782-801）强调 healthy=true **不代表**某 Capability 支持，Health 与 Capability 必须分别处理。
- Capability Resolver 链（§57，L1720-1738）：Core→AdapterManager→Adapter.get_capabilities()，最终缓存 CapabilityCache，避免每请求探测。
- Adapter 与 API Registry（§58，L1742-1781）：Adapter 只知道 Operation；API Registry 负责 Operation→Product→Version→Native API 映射。

### C.6 Mock 与 Contract Test 要点
- MockModelStore（§27/§28，L805-862）：MockNode{id,x,y,z}、MockElement{id,node_ids,material,section}、MockLoad{node_id,fx,fy,fz}；store 含 nodes/elements/loads/materials/sections/boundaries。
- Mock Capabilities（§30，L883-917）：MODEL.NODE/ELEMENT/MATERIAL/SECTION/BOUNDARY/LOAD 的 READ/WRITE/DELETE + ANALYSIS.STATIC + RESULT.DISPLACEMENT/REACTION/ELEMENT_FORCE/STRESS + DESIGN.STEEL。
- Mock 静态分析（§41/§42/§45）：非工程级（NOT ENGINEERING-GRADE）；算法 δ = F L / (E A) 近似；结果标记 engine=MockEngineering、engineering_grade=false。
- 材料/截面测试数据（§43/§44）：MATERIALS{Q355B:{E:2.06e11,fy:355e6},Q235B:{E:2.06e11,fy:235e6}}；SECTIONS{H400x400x13x21:{area:0.025,iy:0.20,iz:0.20}}。
- 操作派发（§48，L1433-1484）：handlers 字典映射 MODEL.NODE.CREATE/QUERY、MODEL.ELEMENT.CREATE、BUILD.COLUMN、MODEL.BOUNDARY.ASSIGN、MODEL.LOAD.ASSIGN、ANALYSIS.STATIC、RESULT.NODE.DISPLACEMENT、DESIGN.STEEL；未命中抛 AdapterCapabilityError。
- 错误归一（§49，L1488-1536）：MockValidationError/MockDuplicateError→STRUCTAI-1200 ENGINEERING_VALIDATION_ERROR；其他→STRUCTAI-6000 ADAPTER_ERROR。
- 取消（§51）：Mock cancel() 直接 return None（立即可取消）；真实 MIDAS Adapter 须按实际 API 判断。
- Contract Test（§66，L1972-2005）：AdapterContract 测试 connect/health/version/capabilities/execute_node_create/execute_node_query/normalize_error；Mock、MIDAS、CSI 必须 PASS。
- E2E（§62，L1847-1874）：BUILD.COLUMN→MODEL.BOUNDARY.ASSIGN→MODEL.LOAD.ASSIGN→ANALYSIS.STATIC→RESULT.NODE.DISPLACEMENT→DESIGN.STEEL，全部 engineering_grade=false。

---

## D. 所有出现的 MIDAS API 引用（穷尽）

### D.0 重要结论（先看这条）
本次要求精读的 **01 与 05 两份文档几乎没有具体 MIDAS 原生接口路径**：01 仅出现 `Tool → /db/NODE`、`Tool → /anal/STATIC` 这类**禁止示例**与一个 API Registry 示例 `/anal/STATIC`；05 只有占位符 `REST / xxx`。任务给出的形式（`/db/XXX`、`/doc/XXX`、`/ope/XXX`、`/view/XXX`、`/post/TABLE`、`/design/...`、表代码 `NODE`/`MATL`）实际全部位于 **doc 04（MIDAS Adapter）与 doc 06（Deployment/Test）**，01/05 未收录。为满足「必须穷尽」，下面 D.2 给出 doc 04/06 中的完整 MIDAS 原生 API 目录（01/05 的完整清单见 D.1）。

### D.1 01 与 05 中出现的 MIDAS 引用
01（`docs/01_STRUCTAI_MCP_V2_ARCHITECTURE.md`）：
- L98 `Tool → /db/NODE` — dev §2.2「Tool 不绑定 API」禁止示例。
- L99 `Tool → /anal/STATIC` — dev §2.2 禁止示例。
- L376 `MIDAS URL` — dev §6 Operation Registry：Operation 不含 MIDAS URL。
- L899 `"protocol": "REST"` + L901 `"path": "/anal/STATIC"` — dev §20 API Registry 示例（software=MIDAS, product=CIVIL NX, version=2026, operation=ANALYSIS.STATIC, method=POST）。
- L913 `"protocol": "COM"` / L914 `"method": "RunAnalysis"` — dev §20 ETABS 示例（非 MIDAS）。
- L924 `"protocol": "SCRIPT"` / L925 `"method": "analyze"` — dev §20 OpenSees 示例。
- L2131 `POST /anal/STATIC`、L2137-2146 `ANALYSIS.STATIC → MIDAS CIVIL NX / POST /anal/STATIC` 及 `ETABS COM RunAnalysis` — db §18「一个 Operation 对多个 API」。
- L2250 `/anal/STATIC`（上下文 `MIDAS / CIVIL NX / 2026 / POST /anal/STATIC`）— db §19 API Registry 示例。
- L187 架构图 `REST / COM / CLI/API`（MIDAS/CSI/OpenSees 接入协议）。
05（`docs/05_STRUCTAI_MCP_V2_ADAPTER_SDK.md`）：
- L1772 `→ REST / xxx` — §58 Adapter 与 API Registry：`ANALYSIS.STATIC` 未来可能映射 `MIDAS CIVIL 2026 → REST / xxx`（占位符，无具体路径）。
- 其余均为文字提及（MIDAS 是 Adapter #1、Mock 先于 MIDAS 等），无具体接口路径。

### D.2 完整 MIDAS 原生 API 目录（doc 04 §14「官方 API Registry 初始种子」，doc 06 亦镜像；01/05 未收录）
来源：`docs/04_STRUCTAI_MCP_V2_MIDAS_ADAPTER.md` L644-739（§14），并见 L1819-1852（§52 Design Runtime）、L991/L4858/L4859/L1541 等方法示例；doc 06 对应块在 L21038-21125、L25439-25455 等。

**DOC（官方仅 POST；body 从 `Argument` 开始）**：
- POST /doc/NEW｜/doc/OPEN｜/doc/CLOSE｜/doc/SAVE｜/doc/SAVEAS｜/doc/STAGAS｜/doc/IMPORT｜/doc/IMPORTMXT｜/doc/EXPORT｜/doc/EXPORTMXT｜/doc/ANAL
- `/doc/ANAL` 被官方列为 Perform Analysis（doc 04 §35，L1363-1385）；`ANALYSIS.STATIC` 不应硬编码成未经验证的 `/anal/STATIC`。

**DB（GET/POST/PUT/DELETE；POST/PUT 首层关键字通常为 `Assign`，随后按数据类型使用编号键）**：
- /db/PJCF｜/db/UNIT｜/db/STYP｜/db/GRUP｜/db/BNGR｜/db/LDGR｜/db/TDGR
- /db/NODE｜/db/ELEM｜/db/MATL｜/db/SECT｜/db/CONS｜/db/NSPR｜/db/GSTP｜/db/GSPR｜/db/SSPS｜/db/ELNK｜/db/RIGD｜/db/NLLP｜/db/NLNK｜/db/STLD｜/db/BODF｜/db/CNLD｜/db/BMLD｜/db/SDSP｜/db/NMAS｜/db/LTOM｜/db/NBOF｜/db/PSLT｜/db/PRES｜/db/PNLD｜/db/PNLA｜/db/FBLD｜/db/FBLA｜/db/ACTL｜/db/PDEL｜/db/BUCK｜/db/EIGV｜/db/MVCT｜/db/SMCT｜/db/NLCT｜/db/STCT｜/db/BCCT

**DB（设计数据相关，doc 04 §52 Design Runtime L1838-1848；不能因存在 `/db/...` 就推断为设计执行 API）**：
- /db/DCON｜/db/MATD｜/db/RCHK｜/db/LENG｜/db/MEMB｜/db/DCTL｜/db/LTSR｜/db/ULCT｜/db/MBTP｜/db/WMAK｜/db/DSTL

**OPE（操作类）**：
- /ope/PROJECTSTATUS｜/ope/DIVIDEELEM｜/ope/SECTPROP｜/ope/AUTOMESH｜/ope/EDMP
- `/ope/SECTPROP` 可作为 section-property operation 的 native mapping 候选（doc 04 L1223）。

**VIEW（视图类）**：
- /view/SELECT｜/view/CAPTURE｜/view/PRECAPTURE｜/view/ANGLE｜/view/ACTIVE｜/view/DISPLAY｜/view/RESULTGRAPHIC
- `/view/CAPTURE` 可能返回图片（doc 04 L1771）。

**方法示例（doc 04）**：`GET /db/NODE`（L991）、`POST /db/NODE`（L4858）、`POST /db/ELEM`（L4859）、`POST /doc/ANAL`（L1541）、`live_midas.get("/db/NODE")`（L4302）。
**路径/表代码**：`/db/NODE`、`/db/ELEM`、`/db/MATL`、`/db/SECT`、`/db/CONS` 等（见上）。
**未出现的形式**：文档中**没有** `/post/TABLE` 形式，也**没有** `/design/...` 路径；设计能力由 `DESIGN.*` operation + `/db/*` 设计数据资源表达（doc 04 §52）。

---

## E. 技术栈与项目结构

### E.1 明确选型
- 语言/运行时：**Python**（05 全部接口为 `async def`，dataclasses / `StrEnum` / `abc.ABC`；用 importlib.metadata entry points 做插件）。
- 协议/传输：**MCP**（MCP Runtime/Transport）；04/01 提及 **STDIO / Streamable HTTP**（01 §51，L3381）。
- Web 框架：**FastAPI** 出现，但被明确禁止在 Adapter 层使用（红线 `Adapter → FastAPI`，01 §35）。
- ORM/迁移：**SQLAlchemy 2.x** + **Alembic**（01 db §2，L1438-1448；§43 Migration）。
- 数据库：Core Alpha = **SQLite**；生产可迁移 **PostgreSQL**；访问统一经 SQLAlchemy，禁止 `sqlite3.connect(...)` 直连与业务层按 DB 类型分支。主键 UUID（CHAR(36)，后续可原生 UUID）。
- 事件：Core Alpha = **InProcessEventBus**；未来可 **Redis/NATS/Kafka**（01 §26，L1090-1118）。
- 存储：Artifact 第一阶段 = **LocalFilesystemStorage**（01 §18，L860-864）。
- 密钥：禁止明文 API Key，只存 `credential_ref`（如 secret://software/civil_01/api_key）；Secret 由 **OS Credential Store / Vault / 环境变量 / Secret Manager** 负责（01 db §13，L1949-1970）。
- 可观测：健康端点 `/livez`、`/readyz`、`/health`；Prometheus 风格指标 structai_requests_total 等（01 §25，L1062-1084）。
- Adapter 目标软件：MIDAS（CIVIL NX/GEN NX/FEA NX）、CSI（ETABS/SAP2000）、ANSYS、ABAQUS、OpenSees（01 db §1，L1424-1432；05 目标 ETABS/SAP2000/ANSYS/ABAQUS/OpenSees）。

### E.2 目录结构（原样摘录）
- 05 §4（L151）：`app/infrastructure/adapters/base/adapter.py`
- 05 §27（L810）：`app/infrastructure/adapters/mock/model_store.py`
- 01 db §43 Migration（L3039-3047）：
```text
migrations/
├── env.py
└── versions/
    ├── 0001_initial.py
    ├── 0002_registry.py
    ├── 0003_task_engine.py
    └── ...
```
- 01 §34 开发顺序（L1324-1351）：01 Database → 02 Domain → 03 Repository/UnitOfWork → 04 Registry → 05 Schema Engine → 06 Authentication → 07 RBAC → 08 Resource Resolver → 09 Lock → 10 Execution Context → 11 Validation → 12 Capability → 13 Adapter → 14 Mock Adapter → 15 Task Engine → 16 Recovery → 17 Artifact → 18 Event → 19 Audit/Trace → 20 Metrics/Health → 21 MCP → 22 9 Tools → 23 Contract Tests → 24 E2E → 25 Real MIDAS Adapter → 26 Second Software Adapter → 27 UI。
- 05 §69（L2082-2118）运行链：MCP/HTTP/AI→Authentication→IdentityContext→ExecutionContext→OperationResolver→ResourceResolver→SchemaEngine→EngineeringValidator→PermissionGuard→ConfirmationGuard→Idempotency→ResourceLock→CapabilityResolver→TaskEngine→AdapterManager→Mock/MIDAS/CSI/ANSYS→Engineering Software。
- （说明：文档未给出完整仓库树，只给出上述零散路径与包名 structai_mock/structai_midas/structai_csi/structai_ansys。）

---

## F. 明确的「不做什么」清单（禁止项 / 边界）

**01（dev + db）**：
1. Tool 不绑定具体软件（MIDAS/CSI/ANSYS/OpenSees），只表达工程语义（§2.1）。
2. 禁止 `Tool → /db/NODE`、`Tool → /anal/STATIC`（§2.2）。
3. 新增软件不应修改 MCP Protocol / 9 Core Tools / Task Engine / Schema Engine / Permission Engine（§2.3）。
4. Adapter 不负责 MCP / RBAC / 全局 Task 生命周期 / AI / UI / Knowledge Base（§9，L510-519）。
5. 客户端不能声明 user_id / tenant_id / roles / permissions（§10）；服务器必须经 Resource Resolver 验证归属。
6. Agent 不得提升权限（§11）。
7. 底层软件不能真正取消时，不得伪装为已取消（§24）。
8. 一个 MIDAS Instance 不可用不能让整个 Core 变为 unavailable（§25）。
9. 第二软件接入不得修改 9 Tool Contract / MCP Protocol / Task Engine / AI Client Integration（§31）。
10. UI 不得反向改变 Core Contract（§33）。
11. 最终架构红线（§35）禁止：`Tool → MIDAS API`、`Tool → SQLAlchemy`、`UI → Database`、`AI → Native API`、`Adapter → FastAPI`、`Client → 自行声明 user_id/role`。
12. AI 不直接调用 MIDAS Native API（§28）。
13. 数据库：禁止 `sqlite3.connect(...)` 直连、禁止业务层按数据库类型大量分支（db §2）。
14. 禁止保存明文 API Key，只存 credential_ref（db §13）。
15. 不能设计为 `Operation → One API`，必须支持一 Operation 对多 API + sequence（db §18）。
16. 禁止覆盖 Schema 历史版本（db §21）。
17. 运行时不要每次请求都扫描数据库（db §38）。
18. 不要因 UI 操作直接物理删除 Registry（Tool/Operation/Capability/Software/Adapter/Schema/API），用 enabled/deleted_at（db §35）。
19. 禁止数据不一致（Operation 无 Tool、API Mapping 无 Software Version、Adapter Capability 引用不存在 Capability）（db §37）。
20. 不能在半加载状态直接替换运行中的 Registry（db §40）。
21. Seed 必须幂等，禁止产生重复 Tool/Operation/Capability/Schema（db §42）。
22. 不能把 Mock Node 当成 software_instances（db §46）。
23. 真实工程数据（Node/Element/Material/Section/Load/Result）不进入 MCP Core Registry 数据库（db §47）。
24. 架构不是 `StructAI MCP → MIDAS Database → ETABS` 的复制品（db §48）。
25. 新增 MIDAS 版本/ETABS/OpenSees 不应修改 Core 表结构 / MCP Tool / Task Engine（db §50）。
26. 定位：StructAI MCP Server 是通用执行运行时，**不是 MIDAS 的 API 包装器**（§36）。

**05（Adapter SDK）**：
1. Adapter 不负责 MCP / RBAC / Authentication Context / Tenant Isolation / Task Lifecycle / Global Idempotency / Global Lock / AI / UI（§2）。
2. AdapterContext 不携带 password / session token / global permissions / raw client request（§5）。
3. 禁止从数据库直接执行 Python code / eval / exec；代码必须来自 installed Python package（§18）。
4. 版本匹配不能偷偷使用不兼容版本（requested=2027 无声明即 reject，不得回退 2026）（§20）。
5. Health ≠ Capability，必须分别处理（§26）。
6. Mock 不声称是工程真实求解器；明确 NOT ENGINEERING-GRADE（§41）。
7. Mock 结果必须标记 `engineering_grade=false`（§42/§63）。
8. Core 不允许直接暴露 native exception，Adapter 必须转成 StructAI Error（§50）。
9. 一个 MIDAS instance 挂掉，Core 仍应为 READY；不能让 Core readiness=false（§53）。
10. Shutdown 时拒绝新执行、等待当前任务、断开 Adapter、释放资源（§55）。
11. Mock Adapter 不允许成为生产计算器；只用于 unit/integration/e2e test/demo/development，**不用于**正式设计/施工图/审查/工程计算报告（§65）。
12. Security / Execution / Task / Adapter 四层必须保持独立（§71）。
13. MIDAS 只是 Adapter #1，不是 StructAI Core 本身（§71）。

---

## 附：本次精读未覆盖但相关的文档（供交叉参考，未精读）
- `docs/04_STRUCTAI_MCP_V2_MIDAS_ADAPTER.md`（5281 行）— MIDAS 原生 API 目录（D.2 来源）。
- `docs/06_STRUCTAI_MCP_V2_DEPLOYMENT_TEST_ACCEPTANCE.md` — 镜像 MIDAS API 目录与验收测试。
（01/05 未包含具体 MIDAS 原生接口路径，故 D 项的完整清单取自 04/06。）
