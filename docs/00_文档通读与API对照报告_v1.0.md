# 00 · docs/ 通读与 API 对照报告 v1.0

> 目的：完整通读 `G:\MMCP\docs\` 全部文档，逐节不遗漏；并核对文档中的 MIDAS API 内容与我们的
> Endpoint Registry（`G:\MMCP\registry\`）的关系，为「**以我们整理的 API 为基础进行正式开发**」提供依据。
>
> 结论先行：**文档规定的正是「必须先有可验证的 API Registry」，而我们的 Registry 就是那一层；
> 文档自带的 API 清单反而不可直接用于生产。**
>
> 范围说明：本报告只通读 `docs/` 内的 V2 规范。根目录原 `StructAI_MIDAS_MCP_*` 系列文档
> （V1 完整开发文档 / 项目框架图 / 快速响应与实时反馈架构补充文档 / 实测补充文档 / Live 冒烟测试报告 /
> 统一修复计划 / 3 份 CSV 清单）**已归档至 `archive/legacy_v1/`，不作为开发依据，不作为准则**。

---

## 1. 通读范围与完整性证明

### 1.1 文件清单与规模

| 文件 | 行数 | 字符 | 约 token | 独立内容 |
| --- | --- | --- | --- | --- |
| `01_STRUCTAI_MCP_V2_ARCHITECTURE.md` | 3,420 | 38,511 | 1.3 万 | ✅ 全部 |
| `02_STRUCTAI_MCP_V2_CORE_IMPLEMENTATION.md` | 28,891 | 353,939 | 11.8 万 | 部分 |
| `03_STRUCTAI_MCP_V2_MCP_RUNTIME.md` | 9,543 | 118,891 | 4.0 万 | 部分 |
| `04_STRUCTAI_MCP_V2_MIDAS_ADAPTER.md` | 5,281 | 53,784 | 1.8 万 | 与 06 有差异 |
| `05_STRUCTAI_MCP_V2_ADAPTER_SDK.md` | 2,233 | 27,818 | 0.9 万 | 与 02/06 有差异 |
| `06_STRUCTAI_MCP_V2_DEPLOYMENT_TEST_ACCEPTANCE.md` | 25,676 | 311,660 | 10.4 万 | ⚠️ 全部重复 |
| **合计** | **75,044** | **904,603** | **30 万** | 去重后 **252,297** |

### 1.2 🔴 去重分析（重要）

`02` 与 `06` 是**多份子文档的拼合体**（以 `## 完整收录：<tag>` 分隔）。跨文件比对结果：

| 子文档 tag | 出现在 | 内容比对 |
| --- | --- | --- |
| `exec` | 02 · 06 | **逐字节相同** |
| `sec` | 02 · 06 | **逐字节相同** |
| `source9` | 02 · 06 | **逐字节相同** |
| `task` | 02 · 06 | **逐字节相同** |
| `tools15` | 03 · 06 | **逐字节相同** |
| `adapter` | 02 · 05 · 06 | 02 ≡ 06 ≠ 05（05 为 SDK 精简版） |
| `artifact` | 02 · 06 | 有差异 |
| `trans16` | 03 · 06 | 有差异 |
| `midasall` | 04 · 06 | 有差异 |

**真正独立的内容**（只出现一次）：

| tag | 所在文件 | 字符 | 内容 |
| --- | --- | --- | --- |
| `tools5` | 03 | 56,916 | **9 个 MCP Tool 完整实现规范**（第 1–152 节） |
| `source7` | 02 | 48,952 | Core Alpha 实际源码生成规范（第 1–136 节） |
| `blue` | 02 | 48,574 | MCP Server 逐文件实现蓝图（第 1–145 节） |
| `py` | 02 | 38,949 | Core Python 代码实现规范（第 1–87 节） |
| `db` | 01 | 22,432 | Core 数据模型与数据库设计规范（第 1–52 节） |
| `impl` | 02 | 20,703 | Core Implementation Specification（第 1–59 节） |
| `dev` | 01 | 15,771 | 总体架构与数据模型（第 1–36 节） |

> ⚠️ **`06` 无任何独立内容** —— 它 100% 由 `02`/`03`/`04` 已含的子文档组成。阅读时应以
> `01`/`02`/`03`/`04`/`05` 为主，`06` 仅作交叉校验。

### 1.3 通读方式

| 范围 | 方式 |
| --- | --- |
| `01`（dev + db）、`05`（adapter） | 子代理逐行精读 → 报告 `structai_docs_report.md` |
| `02`（impl + py） | 子代理逐行精读 → 报告 `report_impl_py.md`（1,320 行） |
| `02`（blue + source7） | 子代理逐行精读 → 报告 `blue_source7_report.md`（1,366 行） |
| `03`（tools5） | 子代理逐行精读 → 报告 `tools5_report.md` |
| `04`（midasall） | 子代理逐行精读 → 报告 `REPORT_MIDAS_ADAPTER_04.md`（2,937 行） |
| 跨文档 | 结构地图 + 去重哈希 + API 交叉核对（本文档） |

---

## 2. 文档体系概览

六份文档构成一套**完整且已冻结的 MCP Server V2 规范**：

| 文档 | 定位 |
| --- | --- |
| `01` | 总体架构 + Core 数据模型与数据库设计 |
| `02` | Core 源码级实现（impl / py / blue / source7 / …） |
| `03` | 9 个 MCP Tool 完整规范 + MCP Runtime + Transport |
| `04` | MIDAS Adapter 完整实现（含文档自带的 API Registry 种子） |
| `05` | 通用 Adapter SDK（面向第二个软件） |
| `06` | 部署 / 测试 / 验收（内容与 02–04 重复） |

---

## 3. V2 架构要点（开发必须遵守的骨架）

### 3.1 三层解耦（核心原则）

```
Tool  →  Operation  →  Capability  →  API Registry  →  Adapter  →  软件
```

- **Tool ≠ API**：Tool 是稳定的工程语义接口，**不得绑定任何软件或 API**
- **Operation** 是软件无关的工程动作（如 `BUILD.COLUMN`、`ANALYSIS.STATIC`）
- **Capability** 是软件能力声明，**禁止出现 MIDAS / CSI / ANSYS 等厂商名**
- **API Registry** 才承载「Operation → 具体软件 API」的映射

> 🔴 **架构红线（三份文档独立确认）**：**Core 中不允许出现任何 MIDAS endpoint 路径。**
> 三个子代理分别对 `02`/`03` 全文 grep，`/db/…`、`/doc/…`、`/ope/…`、`/view/…`、`/post/TABLE`、
> `/design/…` 命中数为 **0**；出现的 MIDAS 路径全部是「禁止这样做」的反例。

### 3.2 9 个 Core Tool（已冻结）

`engineering_doc` · `engineering_model_query` · `engineering_model_assign` ·
`engineering_model_delete` · `engineering_model_build` · `engineering_view` ·
`engineering_result` · `engineering_design` · `engineering_analysis`

共 **69 个 Operation**（V2 冻结契约 **68** + 2026-10-05 新增 `DESIGN.SRC`），风险等级与执行模式已定：

> 📌 **勘误（2026-10-05）** —— 本报告原写「69 个 Operation（`03` 的 Tool Operation Matrix 44 行 + 扩展）」，
> 该推导**不成立**：44 行含 3 个通配行（`BUILD.*` / `VIEW.*` / `RESULT.*`），正确展开恰为 **68**
> （与 `docs/02` §69 清单、`docs/03` §150 冻结树、`docs/03` §114–122 的 Tool Schema `enum` 四处一致；
> 后者已机器解析核对）。**「69」的真正来源是把 `docs/02` §69「Operation Seed」的章节号误读为数量。**
> 数字 69 现属**巧合性正确**：冻结 68 + 新增 `DESIGN.SRC`（补 `DESIGN.SRC.AIK-SRC2K.*` 共 27 个端点的归属）= **69**。
> 详见 `docs/07` §5.1 / §6.8 / §16 R11。
- Delete / Build / Design / Analysis → `HIGH` + `ASYNC`
- Doc / Query / Assign / View / Result → `LOW`/`MEDIUM` + `SYNC`

### 3.3 安全模型

- **身份必须由服务器生成**：客户端最多提供 `project_id` / `software_instance_id`，
  **不得**声明 `user_id` / `tenant_id` / `roles` / `permissions`
- Effective Permission 链：User → Global Roles → Tenant → Tenant Roles → Project → Project Roles
  → Resource ACL → Explicit Deny
- **AI Agent 权限 = 用户有效权限 ∩ Agent 权限**（不得提权）
- Confirmation Token（`STRUCTAI-4100`）用于删除 / 优化等高风险操作
- Resource Resolver 是**跨租户访问的唯一拦截点**

### 3.4 执行流水线（顺序冻结，26–31 步）

```
MCP Request → Authenticate → 服务器构造 IdentityContext → ExecutionContext
→ Resolve Tool → Resolve Operation → Resolve Resource → Schema Validation
→ Engineering Validation → Preconditions → Effective Permission → Quota
→ Confirmation → Idempotency → Lock → Capability Check → Task/Transaction
→ Adapter → Result Normalization → Postconditions → Release Lock
→ Persist Result → Audit → Trace → Event → MCP Response
```

不可变依据：身份须在 Auth 后构造；Schema 先于 Engineering；Resource Resolve 是唯一跨租户拦截点；
**Idempotency 先于 Lock**（重复请求直接返回，不抢锁）；Capability 先于 Task（避免无能力任务入队）；
Postconditions 先于 Release Lock（锁与 Task 生命周期绑定）。

### 3.5 技术栈（已冻结）

Python `>=3.12` + asyncio · FastAPI + uvicorn · Pydantic v2 + pydantic-settings ·
SQLAlchemy 2.x + Alembic · SQLite（Core Alpha）→ PostgreSQL · httpx · jsonschema ·
structlog · pytest + pytest-asyncio + ruff + mypy · 官方 MCP SDK（STDIO + Streamable HTTP）

### 3.6 错误契约（20 个码）

`STRUCTAI-1000` Protocol · `1100` Schema · `1200` Engineering · `1300` Concurrency ·
`2000` Software Connection · `2100` Software Auth · `2200` Software API · `2300` Software Timeout ·
`3000` Capability Not Supported · `4000` Permission Denied · `4100` Confirmation Required ·
`4200` Tenant Access Denied · `5000` Task · `5100` Task Timeout · `5200` Task Cancelled ·
`5300` Task Recovery · `6000` Adapter · `6100` Resource Locked · `6200` Artifact · `7000` Internal

---

## 4. 🔴 文档中的 API 内容 vs 我们的 Registry

### 4.1 文档自带的 API 清单（`04` 第 14 节「官方 API Registry 初始种子」）

| 分区 | 条数 | 内容 |
| --- | --- | --- |
| `DOC` | 11 | `/doc/NEW` `OPEN` `CLOSE` `SAVE` `SAVEAS` `STAGAS` `IMPORT` `IMPORTMXT` `EXPORT` `EXPORTMXT` `ANAL`（仅 POST） |
| `DB` | 43 | `/db/PJCF` `UNIT` `STYP` `GRUP` `BNGR` `LDGR` `TDGR` + `NODE` `ELEM` `MATL` `SECT` `CONS` `NSPR` `GSTP` `GSPR` `SSPS` `ELNK` `RIGD` `NLLP` `NLNK` `STLD` `BODF` `CNLD` `BMLD` `SDSP` `NMAS` `LTOM` `NBOF` `PSLT` `PRES` `PNLD` `PNLA` `FBLD` `FBLA` `ACTL` `PDEL` `BUCK` `EIGV` `MVCT` `SMCT` `NLCT` `STCT` `BCCT` |
| `OPE` | 5 | `/ope/PROJECTSTATUS` `DIVIDEELEM` `SECTPROP` `AUTOMESH` `EDMP` |
| `VIEW` | 7 | `/view/SELECT` `CAPTURE` `PRECAPTURE` `ANGLE` `ACTIVE` `DISPLAY` `RESULTGRAPHIC` |
| **合计** | **66** | 文档原文注明「**至少包括**」，即非穷举 |

`04` 第 160 节另列 **17 条**「当前明确可作为 Registry 基线的官方事实」：
11 个 DOC + `/db/NODE` `/db/ELEM` `/db/MATL` `/db/SECT` + `/ope/PROJECTSTATUS` + `/view/CAPTURE`。

### 4.2 🔴 关键：文档自带的种子**不能直接用于生产**

`04` 第 8 / 15 节明确规定 Registry 状态四态（`VERIFIED` / `PARTIAL` / `UNVERIFIED` / `DEPRECATED`），
且 **`VERIFIED` 必须由真实验证流程赋值，不能因为文档存在就自动标记**。

`04` 第 130 节（Source-Level Operation Resolver）的代码逐字写着：

```
mapping.verification_status != "VERIFIED"  →  raise RegistryMappingNotVerified
```

而第 14 节的 66 条种子**无一条被标 `VERIFIED`**（初始档位统一为 `PARTIAL`：endpoint + method 已确认、
schema 未验证）。**结论：按文档自己的规则，那 66 条种子在生产环境会直接被拒绝执行。**

`04` 第 14 节原文亦自我限定：

> 「以下 endpoint 来自官方 MIDAS API Manual 中明确列出的路径；**具体 request/response 字段必须继续以
> 对应 endpoint 页面验证，不能凭路径名称推断完整 JSON**。」
>
> 「对于具体 JSON：**不要猜 / 不要根据旧代码补 / 不要根据 endpoint 名称推断**。必须进入：
> 官方 endpoint 页面 → request schema → response schema → **live contract test**。」

### 4.3 交叉核对：文档 API 引用 ↔ 我们的 Registry

对 `docs/` 全文机械提取 MIDAS URI，与 Registry（636 端点 / 437 个唯一 URI）比对：

| 指标 | 结果 |
| --- | --- |
| 文档中出现的 MIDAS URI | **78** |
| 其中在 Registry 中存在 | **76（97.4%）** |
| 误命中（非 API） | 1（`POST/Login` —— 「HTTP POST 到登录路由」的流程描述） |
| **真实遗漏** | **1（`DB/ULCT`）→ 已补录** |

另对源手册 **359 篇**逐篇比对其「索引页 End Point」与「正文 Input URI」，定位错配：

| 错配类型 | 数量 | 影响 |
| --- | --- | --- |
| `-M1` 上标标题导致的解析假象 | 29 | 无（标准版与 M1 版均已收录） |
| `POST/<TABLE_TYPE>` 页（正文 URI 为 `/POST/TABLE`） | 8 | 无（对应 `POST.TABLE.*` key 全部存在） |
| **手册 Input URI 字段笔误** | **1** | 🔴 **`DB/ULCT` 整篇丢失** |

### 4.4 已修复的遗漏：`DB.ULCT`

**根因**：源手册第 147 篇「Underground Load Combination Type」的 **`Input URI` 字段误写为 `db/LTSR`**
（索引页 End Point 才是 `/db/ULCT`）。我们的采集以 `Input URI` 为准，于是该端点整篇丢失。

**实测确认**（3 实例）：

| 实例 | `/db/ULCT` | `/info/db/ULCT` |
| --- | --- | --- |
| GEN | ✅ 200 | ✅ 200（返回 schema） |
| CIVIL | ❌ 404 | ❌ 404 |
| Designer | 200（该实例恒 200，无鉴别力） | 200 |

→ 产品归属定为 **`[GEN_NX]`**。

**已补录**：`DB.ULCT`，methods `POST, GET, PUT, DELETE`，schema 取自 `/info/db/ULCT` 自省
（`Argument.bUNDERLOADTYPE: boolean`），`availability: verified`。

**补录后回归**：dry-run 636 端点 0 问题；GEN_NX live **256 调用 → 220 OK**（+1 即 ULCT，实测 OK）；
CIVIL_NX 215 / DESIGNER 14 均不变。

---

## 5. 关键结论：为什么「以我们的 Registry 为基础」是正确的

| 维度 | 文档自带种子（`04` §14） | 我们的 Registry |
| --- | --- | --- |
| 端点数 | 66（且注明「至少包括」） | **636** |
| JSON Schema | ❌ 无（原文要求「必须继续验证」） | ✅ **616** |
| 验证状态 | 全部 `PARTIAL`（无一条 `VERIFIED`） | `verified` **246** · `unverified` 23 · `untested` 367 |
| 真机实测 | ❌ 无 | ✅ **3 个真实实例逐端点实测**（含两轮复测） |
| 求解器约束 | ❌ 无 | ✅ 26 个 key 带 `solver`（Hyper-S / Grid Model） |
| 产品归属 | 粗略（未区分版本） | ✅ 逐端点 `products` + `product_overrides` |
| 请求体形态 | ❌ 无 | ✅ `body_kind`（数组/对象）+ 扁平/Assign 实测 |
| 破坏性风险标注 | ❌ 无 | ✅ `path_key_supported` / `delete_all_via_body` 等 |
| 与 `04` §130 的 `VERIFIED` 门槛 | ❌ 不满足 | ✅ **满足**（246 个端点已验证） |

> **文档要求的正是「可验证、带 schema、经 contract test 的 API Registry」，而这恰好是我们的 Registry
> 已经做成的部分。** 文档中的 66 条种子应视为「官方路径的最低参考集」，而非开发基础。

---

## 6. 开发就绪度评估

### 6.1 文档已冻结、可直接开发的部分

| 层 | 状态 | 依据 |
| --- | --- | --- |
| 总体架构 / 三层解耦 / 红线 | ✅ 冻结 | `01` §1–36、`02` §57 |
| Core 数据模型（24 张表） | ✅ 冻结 | `01` §6–52、`02` source9 |
| 9 Tool + 69 Operation 契约 | ✅ 冻结（**68 + 1 新增**，见 §3.2 勘误） | `03` §3、§86、§149–150 |
| 安全模型 / 权限链 / 确认机制 | ✅ 冻结 | `02` sec、`01` §11 |
| 执行流水线（顺序冻结） | ✅ 冻结 | `02` §55 |
| Task Engine / 状态机 / DAG / 恢复 | ✅ 冻结 | `02` task |
| Adapter SDK 接口 / Manifest / Plugin Loader | ✅ 冻结 | `05`、`02` adapter |
| 错误契约（20 码）/ 统一响应 | ✅ 冻结 | `02` §48、`03` §8 |
| 技术栈 / 目录结构 / 依赖清单 | ✅ 冻结 | `02` §4、§54 |
| 实现顺序（37 步）/ DoD（44–45 项） | ✅ 冻结 | `02` §55–56、§82–83 |

### 6.2 我们的资产（`registry/`）

| 资产 | 用途 |
| --- | --- |
| `manifest.json`（636 端点索引） | 直接作为 `API Registry` 的 seed 数据源 |
| 616 个 JSON Schema | 直接作为 `Schema Registry` 的 `native` 层 schema |
| `availability` / `verified_on` / `unavailable_on` | 直接映射文档的 `verification_status` 四态 |
| `products` / `product_overrides` | 直接驱动 `Product Adapter` 与版本匹配 |
| `solver` / `path_key_supported` / `body_kind` / `delete_*` | 直接驱动 Adapter 的请求构造与安全护栏 |
| `instances.yaml` | 直接作为 `Software Instance` 的实测基线 |
| `examples/midas_client.py` | 可作为 MIDAS Adapter 的 HTTP 客户端起点（含破坏性护栏） |
| `examples/smoke_test.py` | 可作为 Adapter Contract Test 的骨架 |

### 6.3 缺口（需要补的）

| 缺口 | 说明 |
| --- | --- |
| **文档 `04` 的 Transformer 规格未落地** | `04` §20–§55 给出了 Node/Element/Material/Section/Boundary/Load/Result 的 Canonical ↔ Native 映射规则，但 Registry 只有 schema，没有转换器实现 |
| **`Operation → API Mapping` 未建立** | 文档要求 `operations` × `api_endpoints` 的映射表；我们需要把 69 个 Operation 映射到 Registry 的 key |
| **`04` §14 的 66 条种子需升级为 `VERIFIED`** | 我们的 Registry 已覆盖其中绝大部分并实测通过，需要做一次「种子 ↔ Registry」的状态回填 |
| 写路径实测覆盖仅 11 / 369 | 若要按文档 DoD 声称 Adapter 生产就绪，需补写端点的 contract test |
| 20 个端点仍无 Schema | 详见 `archive/legacy_v1/StructAI_MIDAS_MCP_Live冒烟测试报告_v1.0.md` 附录 F.8（非规范性证据留痕） |

---

## 7. 建议的开发起点

按文档 `02` §55 的 37 步实现顺序，前 8 步（Bootstrap → Settings → Database → Alembic → Domain →
Repository/UoW → Seed → Registry）**不依赖 MIDAS**，可以立即开工；第 9 步 `Schema Engine` 与
第 17–19 步 `Adapter Framework / Plugin Loader / Mock Adapter` 之后才接入真实 MIDAS。

**Registry 的接入点在第 8 步与第 17 步之间**，具体建议：

1. **第 8 步 Registry**：把 `registry/manifest.json` 作为 `api_endpoints` 表的 seed，
   `availability` 映射为 `verification_status`（`verified` → `VERIFIED`，其余 → `PARTIAL`/`UNVERIFIED`）。
2. **第 9 步 Schema Engine**：把 `registry/schema/**/*.json` 作为 `schemas` 表的 seed，
   Schema URI 采用文档规定的 `midas://` 命名空间（`structai://` 留给 Canonical 层）。
3. **第 17–19 步 Adapter**：以 `examples/midas_client.py` 为 HTTP 客户端起点，
   按 `04` §20–§55 实现 Transformer，按 `path_key_supported` / `body_kind` / `wrapper` 构造请求。
4. **映射层**：建立 `operations × api_endpoints` 映射（文档 `04` §17），
   把 69 个 Operation 落到 Registry 的具体 key 上。

---

## 8. 附件

本次通读的详细报告（子代理产出，均在 session scratch 目录）：

| 文件 | 内容 |
| --- | --- |
| `structai_docs_report.md` | `01`（dev+db）+ `05`（adapter）逐节精读 |
| `report_impl_py.md` | `02` impl + py 逐节精读（1,320 行） |
| `blue_source7_report.md` | `02` blue + source7 逐节精读（1,366 行） |
| `tools5_report.md` | `03` tools5（9 Tool）逐节精读 |
| `REPORT_MIDAS_ADAPTER_04.md` | `04` midasall 逐节精读（2,937 行，含 §14/§160 逐字摘录） |

核对脚本：`docs_outline.py` · `docs_dedup.py` · `docs_api_xref.py` · `audit_uri_mismatch2.py` · `check_ulct.py`
