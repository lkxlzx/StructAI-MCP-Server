# 精读报告：`G:\MMCP\docs\04_STRUCTAI_MCP_V2_MIDAS_ADAPTER.md`

- 文件规模：**5281 行**（Read 工具 totalLines=5281），63,090 bytes，UTF-8。
- 单一子文档：`midasall`，合并原第 ⑰～㉛ 共 15 份 MIDAS 文档，第 **0–164 节**（+「来源映射」尾节）。
- 标题体系：**`#` 为节号（0–164）**，`##` 为少数子节，`###` 为 VERIFIED/PARTIAL/UNVERIFIED/DEPRECATED 与「原则 1–10」。
- 本次读取覆盖：offset 0/450/900/1350/1800/2250/2700/3150/3600/4050/4500/4950 → 5281，**无跳读，已读到 EOF（line 5281 = `- \`midasall\`：完整收录。`）**。
- 未修改任何文件（只读）。

---

# A. 章节地图

## A.1 全部二级标题（`##`）——共 18 条，逐条列出

| 行号 | 二级标题 | 一句话要点 |
|---|---|---|
| 16 | `## 合并文档：原 ⑰～㉛全部内容` | 标题页副题：声明本文是 15 份 MIDAS 文档的合并本（V2.0-MIDAS-ADAPTER-ALL）。 |
| 63 | `## 1.1 官方 API 总体定位` | MIDAS NX 官方 RESTful API 分 DOC/DB/OPE/VIEW/POST 五类，DB 用 GET/POST/PUT/DELETE，DOC 只用 POST。 |
| 174 | `## 3.1 Adapter 负责` | Adapter 负责 14 项：连接、版本、健康检查、Capability、Registry 解析、双向 Transformer、错误归一、分析状态、Recovery/Reconcile、并发、版本兼容、Contract Test。 |
| 193 | `## 3.2 Adapter 不负责` | 明确排除 MCP 协议/会话、全局认证、RBAC、Tenant、Project ACL、全局 Task 生命周期、全局 Audit/Trace/EventBus、UI、AI Prompt 等。 |
| 283 | `## 5.1 官方连接信息` | MIDAS API Settings 提供 Base URL / MAPI-Key / Status / Connect / Disconnect / Refresh / Connect API on Startup。 |
| 374 | `## 7.1 Registry 目标` | Registry 的目标链路：Operation→Product→Version→Method→Endpoint→Req/Resp Schema→Transformer→Verification Status；禁止在 DB 存 Python 代码。 |
| 648 | `## DOC` | Registry 种子·DOC 分区：11 个 `/doc/*` 端点，仅 POST，body 从 `Argument` 开始。 |
| 666 | `## DB` | Registry 种子·DB 分区：45 个 `/db/*` 端点，机制为 GET/POST/PUT/DELETE，POST/PUT 首层键通常为 `Assign`。 |
| 719 | `## OPE` | Registry 种子·OPE 分区：5 个 `/ope/*` 操作型端点。 |
| 729 | `## VIEW` | Registry 种子·VIEW 分区：7 个 `/view/*` 视图端点。 |
| 904 | `## 20.1 Canonical Node` | Canonical Node 的 dataclass 与 JSON Schema（`structai://schema/model/node/v1`）。 |
| 1968 | `## 56.1 状态` | Recovery 六态：KNOWN_SUCCESS / KNOWN_FAILURE / UNKNOWN / RECONCILING / RECOVERED / MANUAL_REVIEW。 |
| 2725 | `## 81.1 HTTP Timeout` | 超时四层拆分：connect/read/write/pool_timeout；分析类必须 long-running，不能固定 30s。 |
| 4645 | `## Registry` | Definition of Done·Registry 9 项（DOC/DB/OPE/VIEW/POST Registry + Version/Source/Schema/Verification）。 |
| 4659 | `## Model` | DoD·Model 6 项（Node/Element/Material/Section/Boundary/Load）。 |
| 4670 | `## Analysis` | DoD·Analysis 7 项（Static/Modal/Seismic/Spectrum/Buckling/Time History/Nonlinear），支持情况以版本 Capability 为准。 |
| 4684 | `## Result` | DoD·Result 6 项（Displacement/Reaction/Element Force/Stress/Mode Shape/Analysis Summary）。 |
| 4695 | `## Design` | DoD·Design 5 项（Steel/Concrete/Foundation/Code Check/Optimization），执行路径必须经官方验证。 |

> 注：`###` 级标题共 14 个：`### VERIFIED`(435)、`### PARTIAL`(449)、`### UNVERIFIED`(459)、`### DEPRECATED`(472)、`### 原则 1`(4950)～`### 原则 10`(5004)。

## A.2 顶级节（`#`）全图（0–164）

**基线/定位（0–6）**：`0 文档说明`(26，列出被合并的 ⑰～㉛ 与 8 条合并原则)；`1 官方资料与事实基线`(61)；`2 MIDAS Adapter 在 StructAI 中的位置`(109，AI Client→MCP→Core→9 Tools→Operation→ExecutionService→Capability Resolver→Software Registry→Adapter Manager→MIDAS Adapter→API Registry→Transformer→MIDAS REST API→CIVIL/GEN NX)；`3 Adapter 职责边界`(172)；`4 MIDAS Adapter 核心接口`(213，`EngineeringSoftwareAdapter` ABC 8 个抽象方法)；`5 MIDAS 连接模型`(281)；`6 MIDAS HTTP Client`(323，`MidasHttpClient`，文件 `app/infrastructure/adapters/midas/client.py`)。

**Registry（7–19）**：`7 MIDAS API Registry`(372)；`8 Registry 状态`(422)；`9 Registry 数据模型`(485)；`10 MidasApiSource`(501)；`11 MidasApiEndpoint`(532)；`12 MidasApiSchema`(571)；`13 Schema URI`(596)；`14 官方 API Registry 初始种子`(644)；`15 API Registry Seed 格式`(743)；`16 Registry Resolver`(768)；`17 API Mapping`(802)；`18 API Contract Snapshot`(839)；`19 Info API`(871)。

**Transformer（20–34）**：`20 Node Transformer`(902)；`21 Node Request Transformer`(934)；`22 Node CRUD`(969)；`23 Node ID 策略`(998)；`24 Element Transformer`(1038)；`25 Element 创建`(1067)；`26 Element 查询`(1096)；`27 Material Transformer`(1126)；`28 Material Validation`(1165)；`29 Section Transformer`(1186)；`30 Section Property`(1221)；`31 Boundary Transformer`(1237)；`32 Load Transformer`(1273)；`33 Load Case`(1302)；`34 Load Assignment`(1327)。

**Runtime（35–55）**：`35 Analysis Runtime`(1363)；`36 Analysis Operation`(1403)；`37 Analysis Task`(1439)；`38 Analysis Resource Lock`(1471)；`39 Analysis Preconditions`(1492)；`40 Analysis Postconditions`(1512)；`41 Analysis Unknown Outcome`(1536)；`42 Result Runtime`(1570)；`43 Displacement Canonical`(1595)；`44 Reaction`(1624)；`45 Element Force`(1653)；`46 Result Parser`(1675)；`47 Result Pagination`(1699)；`48 View Runtime`(1717)；`49 View 与 Model 数据分离`(1745)；`50 Capture Artifact`(1769)；`51 Result Graphic`(1795)；`52 Design Runtime`(1819)；`53 Steel Design Pipeline`(1855)；`54 Design Result Canonical`(1895)；`55 Optimization`(1922)。

**恢复/版本/测试（56–80）**：`56 Recovery / Reconcile`(1964)；`57 网络超时`(1981)；`58 Build Recovery`(2013)；`59 Reconcile Algorithm`(2062)；`60 Idempotency`(2089)；`61 Version Runtime`(2117)；`62 Version Adapter Manifest`(2148)；`63 CIVIL NX 与 GEN NX`(2184)；`64 Product Adapter`(2223)；`65 Product Capability`(2256)；`66 Capability Cache`(2292)；`67 Capability Refresh`(2317)；`68 Unknown Version`(2332)；`69 Contract Test`(2363)；`70 Contract Test Fixture`(2387)；`71 Contract Test 分层`(2415)；`72 Contract Test 安全`(2439)；`73 CIVIL NX E2E`(2458)；`74 CIVIL NX 完整工程 E2E`(2488)；`75 E2E 预期 MCP 行为`(2520)；`76 GEN NX Adapter`(2555)；`77 GEN NX E2E`(2596)；`78 API Version Migration`(2636)；`79 Registry Diff`(2672)；`80 Deprecated Mapping`(2698)。

**生产加固（81–93）**：`81 Production Hardening`(2723)；`82 Retry Policy`(2746)；`83 Rate Limit`(2778)；`84 Connection Pool`(2797)；`85 Concurrency`(2824)；`86 Health Check`(2845)；`87 Health Isolation`(2872)；`88 Error Normalization`(2900)；`89 Raw Native Error`(2936)；`90 Logging`(2965)；`91 Trace`(2997)；`92 Audit`(3036)；`93 Artifact`(3069)。

**文档/批处理/校验（94–103）**：`94 Document Runtime`(3108)；`95 Document State`(3135)；`96 Document Safety`(3152)；`97 Batch`(3178)；`98 Dry Run`(3216)；`99 Preconditions`(3247)；`100 Postconditions`(3271)；`101 Native Schema Validation`(3291)；`102 Transformer 设计`(3315)；`103 Transformer Registry`(3342)。

**工程结构/导入（104–113）**：`104 Adapter 文件结构`(3370)；`105 Registry Seed 文件结构`(3414)；`106 Seed Loader`(3436)；`107 Seed Integrity`(3458)；`108 Registry Import`(3472)；`109 自动导入原则`(3500)；`110 API Source Provenance`(3530)；`111 Registry Integrity Check`(3548)；`112 Mock Adapter`(3580)；`113 Mock 与真实 MIDAS 的边界`(3608)。

**配置/生命周期（114–123）**：`114 Production Configuration`(3632)；`115 Secret Configuration`(3660)；`116 Instance Registry`(3676)；`117 Instance Lifecycle`(3699)；`118 Adapter Lifecycle`(3713)；`119 Cancellation`(3745)；`120 Task Recovery`(3775)；`121 API Contract Failure`(3803)；`122 Registry Auto-Disable`(3837)；`123 Circuit Breaker`(3865)。

**性能/安全（124–128）**：`124 Performance`(3885)；`125 Metrics Labels`(3912)；`126 Security`(3937)；`127 Tenant Isolation`(3975)；`128 Audit Example`(4003)。

**执行序列与反模式（129–135）**：`129 Full Execution Sequence`(4018)；`130 Source-Level Operation Resolver`(4088)；`131 不允许巨大 if/elif`(4134)；`132 Canonical Model 与 Native Model`(4170)；`133 MIDAS API Schema 不外泄`(4214)；`134 Raw API Debug`(4246)；`135 Real MIDAS Debug Workflow`(4270)。

**测试矩阵（136–148）**：`136 Node Contract Test Example`(4298)；`137 Node Create Contract Test`(4316)；`138 Analysis Contract Test`(4342)；`139 Result Contract Test`(4372)；`140 Design Contract Test`(4385)；`141 View Contract Test`(4415)；`142 CIVIL E2E 测试矩阵`(4434)；`143 GEN E2E 测试矩阵`(4457)；`144 Recovery Test Matrix`(4481)；`145 Core Restart Recovery`(4504)；`146 MIDAS Closed Recovery`(4526)；`147 API Key Refresh`(4568)；`148 API Key Failure`(4594)。

**收尾（149–164）**：`149 Adapter Production Checklist`(4616)；`150 MIDAS Adapter Definition of Done`(4643)；`151 Production Hardening Definition of Done`(4709)；`152 最终代码结构`(4735)；`153 与 Core 的最终边界`(4781)；`154 第二个软件接入原则`(4814)；`155 最终 AI 调用示例`(4849)；`156 最终内部调用`(4875)；`157 最终验收场景`(4908)；`158 最终工程原则`(4948，10 条)；`159 官方资料基线`(5012)；`160 当前明确可作为 Registry 基线的官方事实`(5044)；`161 下一阶段实现顺序`(5095，24 步)；`162 最终完成标准`(5128)；`163 本文与原 ⑰～㉛的对应关系`(5174)；`164 最终结论`(5198)；`来源映射`(5279)。

---

# B. 🔴 第 14 节「官方 API Registry 初始种子」——逐字完整摘录

**位置**：`docs/04_STRUCTAI_MCP_V2_MIDAS_ADAPTER.md:644-741`

## B.0 节首引言（line 644-646，逐字）

```
# 14. 官方 API Registry 初始种子

以下 endpoint 来自官方 MIDAS API Manual 中明确列出的路径；具体 request/response 字段必须继续以对应 endpoint 页面验证，不能凭路径名称推断完整 JSON。
```

## B.1 `## DOC`（line 648-664）—— 共 **11** 条

逐字原文（line 650-662）：

```
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

节内说明（line 664，逐字）：

```
官方说明 DOC 只使用 POST，body 从 `Argument` 开始；空参数可使用空 body 结构。cite turn0search0
```

（原文该句末尾带一个形如 `cite...turn0search0` 的引用标记。）

### DOC 分区清单（接口路径 + 名称/说明 + 状态标记）

| # | 路径 | 名称/说明（文档给的语义） | 文档标注的状态标记 |
|---|---|---|---|
| 1 | `/doc/NEW` | 新建文档（Document Runtime: NEW，line 3113/3124；Seed 示例 operation `DOCUMENT.NEW`，line 755） | 无显式标记；Seed 示例中写作 `"verification_status": "VERIFIED"`（line 758，但 line 764 明确：`VERIFIED` 必须由真实验证流程赋值，不能因为文档存在就自动标记） |
| 2 | `/doc/OPEN` | 打开文档（OPEN） | 无显式标记 |
| 3 | `/doc/CLOSE` | 关闭文档（CLOSE） | 无显式标记 |
| 4 | `/doc/SAVE` | 保存文档（SAVE） | 无显式标记 |
| 5 | `/doc/SAVEAS` | 另存为（SAVE_AS） | 无显式标记 |
| 6 | `/doc/STAGAS` | 阶段另存（Stage As，文档未展开说明） | 无显式标记 |
| 7 | `/doc/IMPORT` | 导入（文档未展开说明） | 无显式标记 |
| 8 | `/doc/IMPORTMXT` | 导入 MXT（文档未展开说明） | 无显式标记 |
| 9 | `/doc/EXPORT` | 导出（文档未展开说明） | 无显式标记 |
| 10 | `/doc/EXPORTMXT` | 导出 MXT（文档未展开说明） | 无显式标记 |
| 11 | `/doc/ANAL` | **Perform Analysis**（line 1370-1377 明确列为「Perform Analysis」） | 无显式标记；line 121/3808 把它当作可能 contract 失败的端点 |

> ⚠️ **重要事实**：第 14 节**本身不给任何单条 endpoint 赋 VERIFIED/PARTIAL/UNVERIFIED/DEPRECATED 标记**。整节只有 4 个分区清单 + 分区级机制说明。唯一出现 `VERIFIED` 的地方是第 15 节（line 743-764）的 seed JSON 示例，且紧接一句否证：不能因为文档存在就自动标记 VERIFIED。因此**这 68 条端点的状态在文档中统一处于「官方路径已确认、schema 未验证」即 PARTIAL 语义档位**（对应第 8 节 PARTIAL 定义：Endpoint 已确认 + Method 已确认，但 Request/Response Schema 尚未完全验证）。

## B.2 `## DB`（line 666-717）—— 共 **43** 条（原文分两组：7 + 36）

逐字原文（line 668-715）：

```
至少包括：

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

节内说明（line 717，逐字）：

```
DB API 的基本机制是 GET/POST/PUT/DELETE；POST/PUT 的第一层关键字通常为 `Assign`，随后按照数据类型使用编号键。实际 endpoint 必须读取对应官方 schema。cite turn0search0
```

### DB 分区清单（接口路径 + 名称/说明 + 状态标记）

| # | 路径 | 名称/说明（文档给的语义 / 出处） | 状态标记 |
|---|---|---|---|
| 1 | `/db/PJCF` | 项目配置（Project Configuration，文档未展开） | 无显式标记 |
| 2 | `/db/UNIT` | 单位系统（Material Validation 要求检查 unit system，line 1179） | 无显式标记 |
| 3 | `/db/STYP` | 截面/结构类型（文档未展开） | 无显式标记 |
| 4 | `/db/GRUP` | 组（Element 查询支持 by group，line 1107） | 无显式标记 |
| 5 | `/db/BNGR` | 边界组（文档未展开） | 无显式标记 |
| 6 | `/db/LDGR` | 荷载组（Load Group，line 1307） | 无显式标记 |
| 7 | `/db/TDGR` | 温度/热荷载组（文档未展开） | 无显式标记 |
| 8 | `/db/NODE` | 节点（Node CRUD 的 native endpoint；line 983/991/1082/2395/4302） | 无显式标记 |
| 9 | `/db/ELEM` | 单元（Element 创建目标；line 1082/2548） | 无显式标记 |
| 10 | `/db/MATL` | 材料（Material Transformer；line 1142 提到 MIDAS MATL JSON） | 无显式标记 |
| 11 | `/db/SECT` | 截面（Section Transformer） | 无显式标记 |
| 12 | `/db/CONS` | 约束（Constraints，文档未展开） | 无显式标记 |
| 13 | `/db/NSPR` | 节点弹性支承（Node Spring） | 无显式标记 |
| 14 | `/db/GSTP` | 地基/面弹簧属性（文档未展开） | 无显式标记 |
| 15 | `/db/GSPR` | 通用弹簧（General Spring） | 无显式标记 |
| 16 | `/db/SSPS` | 索/桁架特殊属性（文档未展开） | 无显式标记 |
| 17 | `/db/ELNK` | 弹性连接（Elastic Link） | 无显式标记 |
| 18 | `/db/RIGD` | 刚体连接（Rigid Link） | 无显式标记 |
| 19 | `/db/NLLP` | 非线性连接属性（文档未展开） | 无显式标记 |
| 20 | `/db/NLNK` | 非线性连接（Nonlinear Link） | 无显式标记 |
| 21 | `/db/STLD` | 静力荷载（Static Load） | 无显式标记 |
| 22 | `/db/BODF` | 体力/节点荷载（Body Force） | 无显式标记 |
| 23 | `/db/CNLD` | 节点集中荷载（Concentrated Node Load） | 无显式标记 |
| 24 | `/db/BMLD` | 梁单元荷载（Beam Load） | 无显式标记 |
| 25 | `/db/SDSP` | 支座位移（Support Displacement） | 无显式标记 |
| 26 | `/db/NMAS` | 节点质量（Node Mass） | 无显式标记 |
| 27 | `/db/LTOM` | 荷载→质量转换（Load to Mass） | 无显式标记 |
| 28 | `/db/NBOF` | 节点体荷载（文档未展开） | 无显式标记 |
| 29 | `/db/PSLT` | 板/压力荷载（文档未展开） | 无显式标记 |
| 30 | `/db/PRES` | 压力荷载（Pressure，Load Transformer 抽象 `PRESSURE`，line 1295） | 无显式标记 |
| 31 | `/db/PNLD` | 预应力/预紧荷载（文档未展开） | 无显式标记 |
| 32 | `/db/PNLA` | 预应力分析（文档未展开） | 无显式标记 |
| 33 | `/db/FBLD` | 楼面荷载（Floor Load） | 无显式标记 |
| 34 | `/db/FBLA` | 楼面荷载分配（Floor Load Assignment） | 无显式标记 |
| 35 | `/db/ACTL` | 施工阶段/激活控制（文档未展开） | 无显式标记 |
| 36 | `/db/PDEL` | 阶段删除（文档未展开） | 无显式标记 |
| 37 | `/db/BUCK` | 屈曲分析数据（对应 `ANALYSIS.BUCKLING`，line 1412） | 无显式标记 |
| 38 | `/db/EIGV` | 特征值/振型（对应 `ANALYSIS.MODAL`） | 无显式标记 |
| 39 | `/db/MVCT` | 移动荷载（Moving Load Case/Table） | 无显式标记 |
| 40 | `/db/SMCT` | 反应谱/地震（对应 `ANALYSIS.SPECTRUM`/`SEISMIC`） | 无显式标记 |
| 41 | `/db/NLCT` | 非线性控制（对应 `ANALYSIS.NONLINEAR`） | 无显式标记 |
| 42 | `/db/STCT` | 静力分析控制（对应 `ANALYSIS.STATIC`） | 无显式标记 |
| 43 | `/db/BCCT` | 边界条件控制（文档未展开） | 无显式标记 |
| 44 | *(空行分隔，非端点)* | — | — |
| 45 | *(空行分隔，非端点)* | — | — |

> 精确计数：line 671-677 为 7 条（PJCF/UNIT/STYP/GRUP/BNGR/LDGR/TDGR），line 679-715 为 36 条（NODE…BCCT），**合计 43 条端点**（原文写「至少包括」，即非穷举）。

## B.3 `## OPE`（line 719-727）—— 共 **5** 条

逐字原文（line 721-726）：

```
/ope/PROJECTSTATUS
/ope/DIVIDEELEM
/ope/SECTPROP
/ope/AUTOMESH
/ope/EDMP
```

### OPE 分区清单

| # | 路径 | 名称/说明（文档给的语义 / 出处） | 状态标记 |
|---|---|---|---|
| 1 | `/ope/PROJECTSTATUS` | 工程/分析状态查询；用于 Analysis Unknown Outcome 的 reconcile 依据（line 1559），第 160 节列入官方基线（line 5067） | 无显式标记 |
| 2 | `/ope/DIVIDEELEM` | 单元细分（Divide Element），文档未展开 | 无显式标记 |
| 3 | `/ope/SECTPROP` | 截面属性计算；line 1223 明确「可作为 section-property operation 的 native mapping 候选」，但 line 1227-1233 强调 `DESIGN.STEEL ≠ SECTPROP`，截面属性≠设计验算 | 无显式标记 |
| 4 | `/ope/AUTOMESH` | 自动网格划分（Auto Mesh） | 无显式标记 |
| 5 | `/ope/EDMP` | 文档未展开（名称/语义未在文中说明） | 无显式标记 |

## B.4 `## VIEW`（line 729-739）—— 共 **7** 条

逐字原文（line 731-738）：

```
/view/SELECT
/view/CAPTURE
/view/PRECAPTURE
/view/ANGLE
/view/ACTIVE
/view/DISPLAY
/view/RESULTGRAPHIC
```

（同一清单在第 48 节 `View Runtime` line 1732-1738 被**原样重复一次**，并称「官方 Manual 中明确列出」。）

### VIEW 分区清单

| # | 路径 | 名称/说明（文档给的语义 / 出处） | 状态标记 |
|---|---|---|---|
| 1 | `/view/SELECT` | 视图选择（View Contract Test 验证项 SELECT，line 4418） | 无显式标记 |
| 2 | `/view/CAPTURE` | 截图；返回图片 bytes→ArtifactStorage→artifact_id（line 1771-1791）；第 160 节列入官方基线（line 5068） | 无显式标记 |
| 3 | `/view/PRECAPTURE` | 预截图/截图前处理（文档未展开） | 无显式标记 |
| 4 | `/view/ANGLE` | 相机角度（对应 `CAMERA`，line 1724） | 无显式标记 |
| 5 | `/view/ACTIVE` | 激活视图（文档未展开） | 无显式标记 |
| 6 | `/view/DISPLAY` | 显示控制（line 1726；View Contract Test 验证项，line 4419） | 无显式标记 |
| 7 | `/view/RESULTGRAPHIC` | 结果云图；`VIEW.RESULTGRAPHIC` 属 Visualization，不是 Canonical Result 数值数据（line 1799-1815；Contract Test line 4420） | 无显式标记 |

## B.5 第 14 节种子合计

- DOC **11** + DB **43** + OPE **5** + VIEW **7** = **66** 条 endpoint 路径。
- **状态标记结论（逐字依据）**：
  - 第 14 节**无任何单条状态标记**。
  - 第 8 节定义（line 422-481）四态：`VERIFIED` / `PARTIAL` / `UNVERIFIED` / `DEPRECATED`。
  - 第 15 节 line 764（逐字）：``VERIFIED` 必须由真实验证流程赋值，不能因为文档存在就自动标记。`
  - 因此第 14 节种子的正确初始状态 = **PARTIAL**（endpoint+method 已由官方 Manual 确认，request/response schema 未验证），`UNVERIFIED` 仅适用于草稿/未来版本/研究性 API，`DEPRECATED` 仅适用于官方已废弃路径（第 14 节清单中**无**一条被标 DEPRECATED）。
  - 第 160 节（line 5044-5071）进一步把其中 **17 条**提升为「官方文档中已确认的 Registry 基础事实」。


---


---

# C. 🔴 第 1 节「官方资料与事实基线」与第 160 节「当前明确可作为 Registry 基线的官方事实」——逐字完整摘录

> 说明：以下所有「逐字全文」区块外层统一使用 **4 个反引号** 围栏，以便内部原样保留文档自带的 ``` 代码块。

## C.1 第 1 节「官方资料与事实基线」（`docs/04_STRUCTAI_MCP_V2_MIDAS_ADAPTER.md:61-107`）

逐字全文（含 `## 1.1` 子节）：

````
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
````

**该节无表格。** 事实要点归纳：

| 事实 | 内容 | 出处行 |
|---|---|---|
| 产品范围 | MIDAS NX 系列 = CIVIL NX + GEN NX | 65 |
| 协议 | RESTful API | 65 |
| 官方手册提供 | endpoint / method / JSON structure / examples | 65 |
| API 五大分类 | DOC / DB / OPE / VIEW / POST | 69-83 |
| DOC 语义 | 文档/工程文件操作 | 79 |
| DB 语义 | MIDAS NX 文件中的数据库数据 | 80 |
| OPE 语义 | 操作型 API | 81 |
| VIEW 语义 | 视图/可视化 | 82 |
| POST 语义 | 结果/表格等输出型数据 | 83 |
| DB HTTP 方法 | GET / POST / PUT / DELETE | 87-92 |
| DOC HTTP 方法 | 仅 POST | 94 |
| 权威优先级 | 以当前官方 API Manual 为第一来源，**不得以第三方 SDK 或旧代码为准** | 105 |

## C.2 第 160 节「当前明确可作为 Registry 基线的官方事实」（`...:5044-5093`）

逐字全文：

````
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
````

**该节无表格。** 逐条展开（**5 条非端点事实 + 17 条端点事实 = 22 条**）：

| # | 条目 | 类别 | 出处行 |
|---|---|---|---|
| 1 | `RESTful API` | 协议事实 | 5047 |
| 2 | `CIVIL NX + GEN NX` | 产品范围事实 | 5048 |
| 3 | `DOC / DB / OPE / VIEW / POST` | API 分类事实 | 5049 |
| 4 | `MAPI-Key` | 认证事实 | 5050 |
| 5 | `Base URL` | 连接事实 | 5051 |
| 6 | `/doc/NEW` | 端点 | 5052 |
| 7 | `/doc/OPEN` | 端点 | 5053 |
| 8 | `/doc/CLOSE` | 端点 | 5054 |
| 9 | `/doc/SAVE` | 端点 | 5055 |
| 10 | `/doc/SAVEAS` | 端点 | 5056 |
| 11 | `/doc/STAGAS` | 端点 | 5057 |
| 12 | `/doc/IMPORT` | 端点 | 5058 |
| 13 | `/doc/IMPORTMXT` | 端点 | 5059 |
| 14 | `/doc/EXPORT` | 端点 | 5060 |
| 15 | `/doc/EXPORTMXT` | 端点 | 5061 |
| 16 | `/doc/ANAL` | 端点 | 5062 |
| 17 | `/db/NODE` | 端点 | 5063 |
| 18 | `/db/ELEM` | 端点 | 5064 |
| 19 | `/db/MATL` | 端点 | 5065 |
| 20 | `/db/SECT` | 端点 | 5066 |
| 21 | `/ope/PROJECTSTATUS` | 端点 | 5067 |
| 22 | `/view/CAPTURE` | 端点 | 5068 |

**基线禁令（逐字，line 5071-5091）**：以上只是「官方文档中已确认的 Registry 基础事实」；对具体 JSON 「不要猜 / 不要根据旧代码补 / 不要根据 endpoint 名称推断」，必须走「官方 endpoint 页面 → request schema → response schema → live contract test」。

## C.3 关联第 159 节「官方资料基线」（line 5012-5040）—— 8 条官方 URL（逐字）

````
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

官方 API Manual 当前页面说明其内容适用于 MIDAS NX 系列，包括 CIVIL NX 与 GEN NX，并明确给出 endpoint、method、JSON structure 和 examples。cite turn0search0
````

---

# D. Registry 数据模型与状态判定标准

## D.1 表结构总览（第 9 节，line 485-497，逐字）

````
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
````

> 共 7 张建议表；文档仅为前 3 张给出字段定义（第 10/11/12 节）。

## D.2 `MidasApiSource`（第 10 节，line 501-528，逐字代码）

````python
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
````

用途（line 522-528，逐字）：

````
记录 endpoint 从哪里来的
记录什么时候获取
记录哪个版本/手册
````

**字段表**：

| 字段 | 类型 | 约束 | 语义 |
|---|---|---|---|
| `id` | UUID | primary_key | 主键 |
| `source_url` | String(1000) | nullable=False | 官方资料 URL |
| `source_title` | String(500) | — | 官方资料标题 |
| `product` | String(100) | — | 产品（CIVIL NX / GEN NX） |
| `category` | String(50) | — | 分类（DOC/DB/OPE/VIEW/POST） |
| `manual_revision` | String(100) | — | 手册修订版本 |
| `source_hash` | String(128) | — | 来源内容哈希（可追溯性） |
| `retrieved_at` | DateTime(tz) | — | 抓取时间 |
| `created_at` | DateTime(tz) | — | 入库时间 |

## D.3 `MidasApiEndpoint`（第 11 节，line 532-567，逐字代码）

````python
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
````

唯一性约束（line 563-567，逐字）：

````
(product, version_range, method, path)
````

**字段表**：

| 字段 | 类型 | 约束 | 语义 |
|---|---|---|---|
| `id` | UUID | primary_key | 主键 |
| `product` | String(100) | nullable=False | 产品 |
| `product_family` | String(100) | — | 产品族（NX 系列） |
| `version_range` | String(100) | — | 版本范围（如 `2026.x`） |
| `category` | String(30) | nullable=False | 分类 DOC/DB/OPE/VIEW/POST |
| `path` | String(500) | nullable=False | 端点路径 |
| `method` | String(20) | nullable=False | HTTP 方法 |
| `operation` | String(200) | — | StructAI operation（如 `DOCUMENT.NEW`） |
| `request_schema_id` | UUID | — | → `midas_api_schemas.id` |
| `response_schema_id` | UUID | — | → `midas_api_schemas.id` |
| `verification_status` | String(30) | nullable=False | VERIFIED/PARTIAL/UNVERIFIED/DEPRECATED |
| `source_id` | UUID | — | → `midas_api_sources.id` |
| `deprecated` | Boolean | default=False | 废弃标记（与 `verification_status=DEPRECATED` 并行） |
| `created_at` / `updated_at` | DateTime(tz) | — | 时间戳 |

**唯一键**：`(product, version_range, method, path)`。

## D.4 `MidasApiSchema`（第 12 节，line 571-592，逐字代码）

````python
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
````

**字段表**：

| 字段 | 类型 | 约束 | 语义 |
|---|---|---|---|
| `id` | UUID | primary_key | 主键 |
| `schema_uri` | String(500) | nullable=False, **unique** | 如 `midas://civil/node/request/v1` |
| `direction` | String(20) | — | request / response |
| `product` | String(100) | — | 产品 |
| `version_range` | String(100) | — | 版本范围 |
| `schema_json` | JSON | nullable=False | JSON Schema Draft 2020-12 本体 |
| `verification_status` | String(30) | — | 同四态 |
| `source_id` | UUID | — | → `midas_api_sources.id` |
| `created_at` / `updated_at` | DateTime(tz) | — | 时间戳 |

## D.5 Schema URI 命名空间（第 13 节，line 596-640，逐字）

StructAI 侧：

````
structai://schema/model/node/v1
structai://schema/model/element/v1
structai://schema/model/material/v1
structai://schema/model/section/v1
````

MIDAS 侧：

````
midas://civil/node/request/v1
midas://civil/node/response/v1

midas://civil/elem/request/v1
midas://civil/elem/response/v1

midas://gen/node/request/v1
midas://gen/node/response/v1
````

禁止 / 必须（line 622-640，逐字）：

````
禁止：

StructAI Schema = MIDAS Schema

必须：

Canonical
    ↓
StructAI Schema Validation
    ↓
Transformer
    ↓
MIDAS Schema Validation
    ↓
HTTP
````

## D.6 Registry 状态枚举与判定标准（第 8 节，line 422-481，逐字全文）

````
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
````

### 判定标准表（7 项 AND 条件）

| 状态 | 判定条件 | 生产可用性 |
|---|---|---|
| **VERIFIED** | ①官方 endpoint 已确认 ②HTTP Method 已确认 ③Request Schema 已确认 ④Response Schema 已确认 ⑤产品范围已确认 ⑥版本范围已确认 ⑦**至少一次真实 API Contract Test 通过**（7 项全部满足，AND） | 唯一允许进入生产执行的档位（见第 158 节原则 6：`只有 VERIFIED Mapping 才能进入生产执行`，line 4983） |
| **PARTIAL** | Endpoint 已确认 + Method 已确认，但 Request/Response Schema 尚未完全验证 | 不可进入生产执行（第 130 节 line 4108 显式抛 `RegistryMappingNotVerified`）；Design 未确认执行路径时也标 PARTIAL（line 4404） |
| **UNVERIFIED** | 仅存在于草稿 / 未来版本 / 开发研究 / 待验证 API | **生产执行禁止使用**（line 470） |
| **DEPRECATED** | 旧 API，仍可能存在但官方已废弃 | **生产默认禁止**，除非明确开启兼容策略（line 481） |

### 与状态相关的补充硬约束

- 第 0 节合并原则 5（line 54）：`未经官方资料或真实 API 验证的 endpoint/schema 不得标记为 VERIFIED。`
- 第 15 节（line 764）：``VERIFIED` 必须由真实验证流程赋值，不能因为文档存在就自动标记。`
- 第 17 节 `MidasApiMapping`（line 804-819）带 `verification_status: str` 字段，`registry.resolve(...)` 返回该映射。
- 第 111 节（line 3548-3576）：启动期 Integrity Check 若发现 `VERIFIED` 但 transformer 不存在 → `FAIL FAST`。
- 第 121 节（line 3803-3833）：contract 失败记录 `STRUCTAI-2200` 且 `contract_status = FAILED`。
- 第 80 节（line 2698-2719）：DEPRECATED mapping 结构 `{"status": "DEPRECATED", "replacement": {"operation": "..."}}`，运行时 `deprecated → warning → replacement if safe`，**高风险情况下不得自动替换**。

## D.7 `MidasApiMapping`（第 17 节，line 802-836，逐字代码）

````python
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
````

解析调用（line 821-829，逐字）：

````python
mapping = registry.resolve(
    product="CIVIL NX",
    version="2026",
    operation="MODEL.NODE.CREATE",
)
````

## D.8 Registry Resolver 解析优先级（第 16 节，line 768-798，逐字）

````
1. exact product
2. exact version
3. exact method/path
4. exact operation
5. compatible version range
6. fallback mapping
7. reject
````

禁止 / 正确：

````
禁止：

版本不匹配
    ↓
盲目使用最新 API

正确：

找不到匹配
    ↓
Capability = UNSUPPORTED
或
Adapter = DEGRADED
````

---

# E. Transformer 规格（Canonical ↔ Native 双向）

## E.1 Node（第 20–23 节）

### E.1.1 Canonical Node（第 20.1 节，line 904-930，逐字）

````python
@dataclass
class CanonicalNode:
    id: int
    x: float
    y: float
    z: float
````

JSON Schema（逐字）：

````json
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
````

### E.1.2 Node Request Transformer（第 21 节，line 934-966，逐字）

````python
class MidasNodeTransformer:
    def to_native_create(self, node: CanonicalNode) -> dict:
        ...

    def to_native_update(self, node: CanonicalNode) -> dict:
        ...

    def from_native(self, data: dict) -> CanonicalNode:
        ...
````

关键约束（line 948-966，逐字）：

````
重要：

不得在 Transformer 中硬编码所有 endpoint。

正确：

Transformer
    ↓
Registry Schema

而不是：

if operation == "MODEL.NODE.CREATE":
    ...
````

### E.1.3 Node CRUD 映射（第 22 节，line 969-994，逐字）

````
StructAI：

MODEL.NODE.QUERY
MODEL.NODE.CREATE
MODEL.NODE.UPDATE
MODEL.NODE.DELETE

MIDAS：

/db/NODE
````

- 官方 Node 示例说明 **Create Node 通过 POST，删除使用 DELETE**（line 986）。
- 查询：`GET /db/NODE`（line 991）。
- 官方 Get Object 说明 DB 查询可通过 `/db/...` 获取 JSON 数据（line 994）。

### E.1.4 Node ID 策略（第 23 节，line 998-1034，逐字）

不得假定 MIDAS 永远自动编号；必须支持 `EXPLICIT` / `AUTO`。Canonical 请求示例：

````json
{
  "id": 100,
  "x": 0,
  "y": 0,
  "z": 6
}
````

自动 ID 时的映射链：

````
native_id
    ↓
mapping
    ↓
canonical_id
````

**必须保存映射关系**（line 1034）。

## E.2 Element（第 24–26 节）

### E.2.1 CanonicalElement（第 24 节，line 1038-1063，逐字）

````python
@dataclass
class CanonicalElement:
    id: int
    type: str
    node_ids: list[int]
    material_id: int | None
    section_id: int | None
````

支持至少：`BEAM` / `COLUMN` / `TRUSS` / `PLATE` / `SHELL` / `SOLID`。
**不要在 Core 中定义 MIDAS 专用 element code**（line 1063）。

### E.2.2 Element 创建链（第 25 节，line 1067-1092，逐字）

````
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
````

前置条件：`nodes exist` / `material exists` / `section exists` / `element id unique`。

### E.2.3 Element 查询（第 26 节，line 1096-1122）

`MODEL.ELEMENT.QUERY` 支持 `all` / `by id` / `by group` / `by type` / `by node`，**必须分页**：

````json
{
  "items": [],
  "pagination": {
    "has_more": false,
    "next_cursor": null
  }
}
````

## E.3 Material（第 27–28 节）

### E.3.1 CanonicalMaterial（line 1126-1161，逐字）

````python
@dataclass
class CanonicalMaterial:
    id: int
    name: str
    type: str
    properties: dict
````

StructAI **不直接把 MIDAS MATL JSON 暴露给 AI**。AI 使用形态：

````json
{
  "id": 1,
  "name": "Q355B",
  "type": "STEEL",
  "properties": {
    "E": 206000000000,
    "fy": 355000000
  }
}
````

Transformer 再转 MIDAS schema。

### E.3.2 Material Validation（第 28 节，line 1165-1182，逐字）

必须检查：

````
E > 0
density >= 0
fy > 0 for steel
fc > 0 for concrete
````

同时检查：`unit system` / `material type` / `product capability`。

## E.4 Section（第 29–30 节）

### E.4.1 CanonicalSection（line 1186-1217，逐字）

````python
@dataclass
class CanonicalSection:
    id: int
    name: str
    section_type: str
    parameters: dict
````

示例（逐字）：

````json
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
````

⚠️ 文档明确警告（line 1215-1217，逐字）：`这里是 StructAI canonical 参数示例，不是声明 MIDAS 官方字段名。`

### E.4.2 Section Property（第 30 节，line 1221-1233，逐字）

````
MIDAS API/OPE 中存在截面属性相关能力；例如 `/ope/SECTPROP` 可作为 section-property operation 的 native mapping 候选。

但：

DESIGN.STEEL
≠
SECTPROP

截面属性计算不能被误认为设计验算。
````

## E.5 Boundary（第 31 节，line 1237-1269，逐字）

````python
@dataclass
class CanonicalBoundary:
    node_id: int
    ux: bool
    uy: bool
    uz: bool
    rx: bool
    ry: bool
    rz: bool
````

示例（逐字）：

````json
{
  "node_id": 1,
  "ux": true,
  "uy": true,
  "uz": true,
  "rx": true,
  "ry": true,
  "rz": true
}
````

硬约束（line 1267-1269，逐字）：转换到 MIDAS 对应 DB resource；**Boundary 的具体 MIDAS endpoint/schema 必须通过 Registry 绑定，不允许在 Core 中硬编码**。

## E.6 Load（第 32–34 节）

### E.6.1 CanonicalLoad（line 1273-1298，逐字）

````python
@dataclass
class CanonicalLoad:
    id: int
    load_case: str
    load_type: str
    target_type: str
    target_id: int
    values: dict
````

支持抽象（逐字）：

````
NODE_FORCE
NODE_MOMENT
BEAM_FORCE
BEAM_MOMENT
PRESSURE
TEMPERATURE
SELF_WEIGHT
````

### E.6.2 Load Case 语义分离（第 33 节，line 1302-1323，逐字）

必须区分：

````
Load Group
Load Case
Load Combination
Load Pattern
Load Type
````

**不要在 StructAI 内把它们混为一个 `load_case` 字段。** Registry 应明确映射：`LOAD.GROUP` / `LOAD.CASE` / `LOAD.COMBINATION` / `LOAD.ASSIGN`。

### E.6.3 Load Assignment 流程（第 34 节，line 1327-1359，逐字）

````
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
````

## E.7 Displacement（第 43 节，line 1595-1620，逐字）

````json
{
  "node_id": 100,
  "ux": 0.001,
  "uy": 0.002,
  "uz": -0.015,
  "rx": 0.0,
  "ry": 0.0,
  "rz": 0.0
}
````

单位必须显式（逐字）：

````json
{
  "units": {
    "length": "m",
    "rotation": "rad"
  }
}
````

⚠️ **不能假设所有 MIDAS 项目都使用 SI**（line 1620）。

## E.8 Reaction（第 44 节，line 1624-1649，逐字）

````json
{
  "node_id": 1,
  "fx": 500000,
  "fy": 0,
  "fz": 1000000,
  "mx": 0,
  "my": 0,
  "mz": 0
}
````

必须包含：`load_case` / `stage` / `step` / `units`。
**如果原生结果没有某字段，使用 null，不要虚构 0**（line 1649）。

## E.9 ElementForce（第 45 节，line 1653-1671，逐字）

至少支持：

````
axial
shear_y
shear_z
torsion
moment_y
moment_z
````

必须保留：`coordinate_system` / `local_axis_definition`（不同软件局部坐标定义可能不同）。

## E.10 Result Parser（第 46 节，line 1675-1695，逐字）

禁止把 `return {"ux": native["DX"]}` 直接散落在业务代码；正确链路：

````
MIDAS Result Schema
    ↓
MidasResultParser
    ↓
CanonicalResult
````

## E.11 DesignResult（第 54 节，line 1895-1918，逐字）

````json
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
````

⚠️ `CODE-X` **只是占位，不应伪装成某个官方设计规范**（line 1918）。

## E.12 Result Pagination（第 47 节，line 1699-1713）

大型结构结果**禁止一次返回全部数据**。支持：`cursor` / `page_size` / `filter` / `node_ids` / `element_ids` / `load_cases` / `steps`。

## E.13 Transformer 设计 / 注册（第 102–103 节）

文件组织（line 3315-3338，逐字）：

````
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
````

版本化：`node_v1.py` / `node_v2.py`。

````python
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
````

数据库只保存 `midas.node.v1` 这类名字，**代码负责实现**（line 3360-3366）。

## E.14 Native Schema Validation 管线（第 101 节，line 3291-3311，逐字）

使用 `JSON Schema Draft 2020-12`：

````
Canonical Schema
 ↓
Engineering Validation
 ↓
Native Transformer
 ↓
MIDAS JSON Schema
 ↓
HTTP
````

## E.15 Canonical ↔ Native 分离总原则（第 132 节，line 4170-4210，逐字要点）

- Canonical Model 必须**稳定**：`Node / Element / Material / Section / Boundary / Load / Result`。
- MIDAS schema 可以随 `2025 / 2026 / 2027` **变化**。
- 这样未来接入 `ETABS / SAP2000 / ANSYS` 不会改变 Core。
- 第 133 节（line 4214-4242）：MCP Tool schema 必须是 StructAI Canonical Schema，AI **不应需要知道** `Assign` / `NODE ID` / MIDAS-specific nested keys，除非进入 engineering raw/debug 管理能力。

---

# F. 各 Runtime 的规格

## F.1 Model CRUD Runtime（第 20–34、94–98 节）

**接口面（StructAI operation）**：

| 领域 | operations | Native 映射 |
|---|---|---|
| Node | `MODEL.NODE.QUERY` / `MODEL.NODE.CREATE` / `MODEL.NODE.UPDATE` / `MODEL.NODE.DELETE` | `GET/POST/PUT/DELETE /db/NODE`（line 974-983） |
| Element | `MODEL.ELEMENT.QUERY` /（创建见第 25 节） | `/db/ELEM`（line 1082） |
| Material | Material Transformer | `/db/MATL`（隐含） |
| Section | Section Transformer | `/db/SECT`（隐含） |
| Boundary | Boundary Transformer | Registry 绑定，**不允许 Core 硬编码**（line 1269） |
| Load | `MODEL.LOAD.ASSIGN`、`LOAD.GROUP/CASE/COMBINATION/ASSIGN` | Registry 绑定（line 1316-1323） |
| Build 组合 | `BUILD.COLUMN`（line 2018、2507） | 由多个 native 调用组合 |

**前置条件（Element 创建示例，line 1085-1092）**：`nodes exist` / `material exists` / `section exists` / `element id unique`。

**幂等要求**：第 60 节（line 2089-2113，逐字）——

````
MIDAS Adapter 必须支持：

idempotency_key

但必须理解：

StructAI idempotency
≠
MIDAS native idempotency

因此：

StructAI
    保存 operation execution record

MIDAS
    通过状态 reconciliation 防止重复副作用
````

**Document Runtime（第 94–96 节）**：

StructAI operations（line 3110-3119）：`NEW / OPEN / SAVE / SAVE_AS / CLOSE / INFO`。
Native（line 3121-3129）：`/doc/NEW`、`/doc/OPEN`、`/doc/SAVE`、`/doc/SAVEAS`、`/doc/CLOSE`。
Document State（line 3135-3148）：`CLOSED / OPENING / OPEN / DIRTY / SAVING / SAVED / CLOSING / ERROR`。
Document Safety（line 3152-3174）：若 `DIRTY` 时执行 `CLOSE`，必须按用户/策略 `SAVE / DISCARD / CONFIRM`，**不得静默丢失修改**。

**Batch（第 97 节，line 3178-3212）**：必须明确 `ATOMIC` / `NON_ATOMIC`；**如果 MIDAS 本身没有事务，`StructAI cannot falsely claim atomicity`**。

**Dry Run（第 98 节，line 3216-3243）**：支持 `BUILD / ASSIGN / DELETE / DESIGN / OPTIMIZE`；返回

````json
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
````

**不调用会产生副作用的 native API。**

**Preconditions 声明（第 99 节，line 3247-3267）**：

````python
@dataclass(frozen=True)
class MidasPrecondition:
    name: str
    description: str
````

内置：`DOCUMENT_OPEN / MODEL_EXISTS / NODE_EXISTS / ELEMENT_EXISTS / ANALYSIS_IDLE / NO_WRITE_LOCK`。

**Postconditions（第 100 节，line 3271-3287）**：

````
NODE.CREATE
    → node exists

NODE.DELETE
    → node absent

ANALYSIS.STATIC
    → analysis status complete

RESULT.NODE.DISPLACEMENT
    → result exists
````

## F.2 Analysis Runtime（第 35–41、138 节）

**Native 事实（第 35 节，line 1363-1399，逐字）**：官方 MIDAS API Manual 把 `/doc/ANAL` 列为 **Perform Analysis**；因此 `ANALYSIS.STATIC` **不应直接硬编码成某个未经验证的 `/anal/STATIC` 路径**。正确链路：

````
ANALYSIS.STATIC
    ↓
Capability
    ↓
Registry
    ↓
MIDAS /doc/ANAL
    ↓
Transformer / Argument
````

**统一 operations（第 36 节，line 1403-1435）**：`ANALYSIS.STATIC / ANALYSIS.MODAL / ANALYSIS.SEISMIC / ANALYSIS.SPECTRUM / ANALYSIS.BUCKLING / ANALYSIS.TIME_HISTORY / ANALYSIS.NONLINEAR`；必须区分「StructAI conceptual operation」与「MIDAS actual native execution parameter」；是否支持由 **Capability Registry** 决定。

**Task 与异步（第 37 节，line 1439-1467）**：分析必须**默认 ASYNC**（原因：分析时间不可预测 / 软件可能阻塞 / 结果文件可能异步生成）。Task 状态机：

````
CREATED
VALIDATING
QUEUED
RUNNING
PROCESSING
COMPLETED
FAILED
TIMEOUT
RECOVERING
````

**锁策略（第 38 节，line 1471-1488，逐字）**：

````
默认：

Software Instance = EXCLUSIVE
Model = READ

因为分析过程中软件状态可能改变。

禁止：

同时两个分析

除非经过产品/版本验证确认软件支持并发。
````

**前置条件（第 39 节，line 1492-1508，逐字）**：

````
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
````

**后置条件（第 40 节，line 1512-1532，逐字）**：

````
analysis task completed
result availability checked
software status reconciled
result registry available
task artifact generated if configured
````

⚠️ **不能简单 `HTTP 200 = Analysis completed`，必须检查业务状态。**

**Unknown Outcome（第 41 节，line 1536-1566，逐字）**：

````
例如：

POST /doc/ANAL
 ↓
timeout

不能直接：

retry

必须：

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
````

**Analysis Contract Test（第 138 节，line 4342-4368）**：必须 `prepare test model → run analysis → wait/poll → verify status → query result → verify schema`；**禁止** `POST → sleep(10) → assume complete`。

## F.3 Result Runtime（第 42–47、139 节）

**链路（第 42 节，line 1570-1591，逐字）**：

````
Native Result
    ↓
Parser
    ↓
Canonical Result
````

核心 operations：`RESULT.NODE.DISPLACEMENT / RESULT.NODE.REACTION / RESULT.ELEMENT.FORCE / RESULT.ELEMENT.STRESS / RESULT.MODE.SHAPE / RESULT.ANALYSIS.SUMMARY`。

**幂等/无副作用**：Result 为只读查询，属「No side effect → retry possible」（第 82 节，line 2768-2773）。

**Result Contract Test（第 139 节，line 4372-4381）**：必须验证 `field exists` / `type correct` / `unit correct if exposed` / `node/element references valid`。

**分页**：见 E.12。

## F.4 View Runtime（第 48–51、141 节）

**职责（第 48 节，line 1717-1741）**：VIEW API 用于 `MODEL VIEW / RESULT VIEW / CAMERA / CAPTURE / DISPLAY`；官方 Manual 明确列出 7 个 `/view/*` 端点（line 1732-1738），**应通过 View Registry 进行映射**。

**数据分离（第 49 节，line 1745-1765，逐字）**：

````
View 不应修改 Canonical Model。

错误：

VIEW
 ↓
MODEL

正确：

MODEL
 ↓
VIEW STATE
 ↓
MIDAS VIEW API
````

**Capture Artifact（第 50 节，line 1769-1791，逐字）**：

````
MIDAS
 ↓
image bytes
 ↓
ArtifactStorage
 ↓
artifact_id
````

MCP 只返回 `{"artifact_id": "..."}`，**而不是把大图片直接塞进长期 task JSON**。

**Result Graphic（第 51 节，line 1795-1815）**：`VIEW.RESULTGRAPHIC` 属 `Visualization`，**不是 Canonical Result numerical data**，二者必须分离。

**View Contract Test（第 141 节，line 4415-4430）**：验证 `SELECT / DISPLAY / RESULTGRAPHIC / CAPTURE` 的 `HTTP` / `image/json` / `artifact`。

## F.5 Design Runtime（第 52–55、140 节）

**统一 operations（第 52 节，line 1819-1851）**：`DESIGN.STEEL / DESIGN.CONCRETE / DESIGN.FOUNDATION / DESIGN.CODE_CHECK / DESIGN.OPTIMIZE`。

⚠️ **重要警告（line 1831-1851，逐字）**：MIDAS 中存在大量与设计数据相关的 DB resources，但**不能因为存在某个 `/db/...` endpoint 就推断其是设计执行 API**。文档列举了 11 个此类候选（`/db/DCON`、`/db/MATD`、`/db/RCHK`、`/db/LENG`、`/db/MEMB`、`/db/DCTL`、`/db/LTSR`、`/db/ULCT`、`/db/MBTP`、`/db/WMAK`、`/db/DSTL`）——**「这些可以进入 Registry，但其用途必须依据官方 endpoint 文档验证」**。

**Steel Design Pipeline（第 53 节，line 1855-1891，逐字）**：

````
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
````

**不能直接把 `ANALYSIS.STATIC result` 当成 `DESIGN.STEEL result`。**

**Optimization（第 55 节，line 1922-1960，逐字）**：`DESIGN.OPTIMIZE` 必须是 `HIGH RISK` + `ASYNC` + `CONFIRMATION`（可能修改 `section / material / member / model`）；建议支持 `DRY_RUN`，返回 `current / candidate / estimated_saving / constraint_violations`；**未经确认不得写回**。

**Design Contract Test（第 140 节，line 4385-4411）**：`design config → execute → result available → utilization parsed → status parsed`；**如果官方接口尚未确认执行路径，Registry = PARTIAL，不能写 VERIFIED**。

## F.6 锁策略汇总

| 场景 | 锁 | 出处 |
|---|---|---|
| Software Instance（分析期间） | `EXCLUSIVE` | line 1476 |
| Model（分析期间） | `READ` | line 1477 |
| `MODEL WRITE` | `EXCLUSIVE` | line 2829 |
| `ANALYSIS` | `EXCLUSIVE` | line 2830 |
| `DESIGN` | `EXCLUSIVE` | line 2831 |
| `VIEW` | `READ` | line 2832 |
| `QUERY` | `READ` | line 2833 |
| 未来若验证支持并发 | `LIMITED` / `PARALLEL` | line 2839-2840 |

## F.7 Idempotency / Cancellation / Task Recovery

**Idempotency（第 60 节）**：见 F.1 逐字。第 129 节把 `Idempotency` 置于 `Confirmation` 之后、`Lock` 之前（line 4045-4047）。

**Cancellation（第 119 节，line 3745-3771，逐字）**：

````
Analysis：

Task.cancel()

映射：

Adapter.cancel()

如果 MIDAS native API 没有可靠取消能力：

CANCEL_REQUESTED

不能假装：

CANCELLED

最终状态必须通过 reconciliation 确认。
````

**Task Recovery（第 120 节，line 3775-3799，逐字）**：

````
Task Engine：

TASK
 ↓
MIDAS operation
 ↓
unknown

Adapter：

reconcile

最终：

COMPLETED
FAILED
MANUAL_REVIEW
````

## F.8 Recovery / Reconcile 算法（第 56–59、144–148 节）

**Recovery 状态机（第 56.1 节，line 1968-1977，逐字）**：

````
KNOWN_SUCCESS
KNOWN_FAILURE
UNKNOWN
RECONCILING
RECOVERED
MANUAL_REVIEW
````

**网络超时（第 57 节，line 1981-2009，逐字）**：`POST sent → server processing → client timeout` 时**不能认为 FAILED**，应为 `UNKNOWN`，然后 `query software state` / `query project status` / `query result availability`。

**Build Recovery（第 58 节，line 2013-2058，逐字）**：`BUILD.COLUMN` 可能执行 `create node 1 / create node 2 / create element 3 / assign material / assign section`；若在 element 创建后 Core 崩溃，`blind retry` 会产生 `duplicate nodes` / `duplicate elements`。因此 Recovery Policy：

````
SAFE_RETRY
STATE_RECONCILE
MANUAL_REVIEW
FAIL
````

默认：`BUILD → STATE_RECONCILE`。

**Reconcile Algorithm（第 59 节，line 2062-2085，逐字）**：

````
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
````

**Core Restart Recovery（第 145 节，line 4504-4522，逐字）**：

````
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
````

**MIDAS Closed Recovery（第 146 节，line 4526-4564）**：`MIDAS process closed` 时 `RUNNING` → `RECOVERING` → `software unavailable` → 最终 `FAILED` 或 `RESUME`（取决于 operation）。

**API Key Refresh（第 147 节，line 4568-4590，逐字）**：

````
CredentialProvider
 ↓
new secret
 ↓
invalidate connection
 ↓
reconnect
 ↓
health
````

**不能要求重启 StructAI。**

**API Key Failure（第 148 节，line 4594-4612，逐字）**：

````
401 / unauthorized

不要 retry 无限次。

应：

AUTH_ERROR
 ↓
mark adapter degraded
 ↓
request credential refresh
````

**Recovery Test Matrix（第 144 节，line 4481-4500，逐字 14 项）**：

````
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
````

---

# G. 生产加固（第 81–93、114–128、149、151 节）

## G.1 HTTP Timeout（第 81.1 节，line 2725-2742，逐字）

````
分层：

connect_timeout
read_timeout
write_timeout
pool_timeout

分析类：

long-running

不能简单使用固定 30 秒作为整个 operation timeout。
````

## G.2 Retry Policy（第 82 节，line 2746-2774，逐字）

````
允许 retry：

GET query
network connect
temporary 5xx

谨慎 retry：

POST
PUT
DELETE
ANAL
BUILD

原则：

No side effect
    → retry possible

Side effect
    → idempotency/reconcile first
````

## G.3 Rate Limit（第 83 节，line 2778-2793，逐字）

````
MIDAS Adapter 内部：

per instance
per operation

避免：

AI burst

导致桌面软件/API server 不稳定。
````

## G.4 Connection Pool（第 84 节，line 2797-2820，逐字）

````
默认：

per software instance

但对于桌面软件 API：

SERIAL

通常更安全。

HTTP connection pool：

max_connections
max_keepalive

由实际测试确定。
````

## G.5 Concurrency（第 85 节）—— 见 F.6 锁表。

## G.6 Health Check（第 86 节，line 2845-2868，逐字）

至少检查：`API reachable` / `MAPI-Key valid` / `MIDAS connected` / `product` / `version` / `model state`。返回：

````json
{
  "healthy": true,
  "connected": true,
  "product": "CIVIL NX",
  "version": "2026",
  "model_open": true
}
````

## G.7 Health Isolation（第 87 节，line 2872-2896，逐字）

````
一个 MIDAS 实例挂掉：

MIDAS Instance A = DOWN

不应该导致：

StructAI Core = DOWN

应返回：

adapter unhealthy

而 Core：

READY
````

## G.8 Error Normalization（第 88 节，line 2900-2932，逐字）

MIDAS native error 来源：`HTTP` / `JSON` / `native message` / `timeout` / `connection refused`。统一为：

````python
{
    "type": "SOFTWARE_API_ERROR",
    "provider": "MIDAS",
    "retryable": False,
    "details": {}
}
````

再映射 StructAI 错误码：`STRUCTAI-2000` / `STRUCTAI-2100` / `STRUCTAI-2200` / `STRUCTAI-2300` / `STRUCTAI-3000` / `STRUCTAI-6000`。

## G.9 Raw Native Error（第 89 节，line 2936-2961，逐字）

默认 `not exposed`；Debug mode 下：

````json
{
  "cause": {
    "provider": "MIDAS",
    "native_code": "...",
    "native_message": "..."
  }
}
````

必须进行 `secret redaction` + `PII redaction`。

## G.10 Logging（第 90 节，line 2965-2993，逐字）

结构化日志字段：`timestamp / level / trace_id / request_id / task_id / tenant_id / user_id / software_instance / product / version / operation / path / duration / status`。
**禁止**打印：`MAPI-Key` / `password` / `session token` / `private secret`。

## G.11 Trace（第 91 节，line 2997-3032，逐字）

````
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
````

每层携带 `trace_id` / `span_id`。

## G.12 Audit（第 92 节，line 3036-3065）

必须记录：`CREATE / UPDATE / DELETE / ANALYSIS / DESIGN / DOCUMENT SAVE / DOCUMENT OPEN / DOCUMENT CLOSE`。
Audit 字段：`audit_id / timestamp / tenant_id / user_id / project_id / software_instance / operation / resource / result / previous_hash / entry_hash`（哈希链）。

Audit 示例（第 128 节，line 4003-4013，逐字）：

````json
{
  "action": "ANALYSIS.STATIC",
  "software": "MIDAS",
  "product": "CIVIL NX",
  "version": "2026",
  "result": "COMPLETED",
  "task_id": "task_001"
}
````

## G.13 Artifact（第 93 节，line 3069-3104）

MIDAS 可能产生：`model file / result file / capture image / report / export / JSON / CSV`；统一到 `ArtifactStorage`；第一实现 `LocalFilesystemStorage`；数据库只保存 `artifact_id / storage_backend / storage_key / mime_type / size / checksum`。

## G.14 熔断与 Registry 自动禁用（第 122–123 节）

**Registry Auto-Disable（第 122 节，line 3837-3861，逐字）**：

````
如果连续发现：

VERIFIED API
    ↓
production failure

建议：

circuit breaker

状态：

ACTIVE
DEGRADED
OPEN

但不得因为一次 transient failure 就永久禁用。
````

**Circuit Breaker（第 123 节，line 3865-3881，逐字）**：

````
适用：

connection failure
5xx
timeout

不适用：

business validation error
invalid model
bad user input
````

**API Contract Failure（第 121 节，line 3803-3833，逐字）**：Registry 写 `POST /doc/ANAL` 而实际返回 `400` → `do not retry blindly`，记录 `STRUCTAI-2200`，同时 `contract_status = FAILED`。

## G.15 Production Configuration（第 114 节，line 3632-3656，逐字 YAML）

````yaml
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
````

**实际值必须通过压测确定。**

## G.16 Secret Configuration（第 115 节，line 3660-3672，逐字）

````yaml
midas:
  base_url: "http://..."
  secret_ref: "secret://midas/instance/001/mapi-key"
````

而不是 `mapi_key: "xxxx"`。

## G.17 Instance Registry（第 116 节，line 3676-3695）

表 `software_instances`，字段：`instance_id / tenant_id / vendor / product / version / base_url / credential_ref / status / concurrency_mode / last_health_check`。

## G.18 Instance Lifecycle（第 117 节，line 3699-3709，逐字）

````
REGISTERED
CONNECTING
CONNECTED
DEGRADED
DISCONNECTED
ERROR
DISABLED
````

## G.19 Adapter Lifecycle（第 118 节，line 3713-3741，逐字）

````
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
````

断线：

````
READY
 ↓
DISCONNECTED
 ↓
RECONNECTING
 ↓
READY
````

## G.20 Performance / Metrics（第 124–125 节）

目标不是单纯 HTTP TPS，而是 `MCP latency + Core latency + Adapter latency + MIDAS response`。
Metrics：`midas_request_total` / `midas_request_duration_seconds` / `midas_request_error_total` / `midas_analysis_duration_seconds` / `midas_reconcile_total` / `midas_reconcile_duration_seconds`。
允许 label：`product / version / operation / method / status`；**避免高基数**：`node_id / element_id / user-generated id / trace_id` 不要直接作为 Prometheus label。

## G.21 Security / Tenant Isolation（第 126–127 节）

MAPI-Key 归 `CredentialProvider`；RBAC 归 `Core`。链路必须 `AI → RBAC → MCP Tool → MIDAS Adapter`，**不能 `AI → Adapter` 绕过 Core**。
每个 MIDAS Instance 必须归属 tenant；`tenant → project → software instance/model`；**禁止跨 tenant 使用**。

## G.22 其他治理（第 104–113 节）

- **Adapter 文件结构**（第 104 节，line 3370-3410）：`app/infrastructure/adapters/midas/` 下含 `adapter.py / base.py / manifest.py / client.py / health.py / capabilities.py / registry.py / errors.py / recovery.py / reconcile.py / models.py / schemas/{civil,gen} / transformers/* / products/{civil,gen}.py / tests/{contract,integration,e2e,fixtures}`。
- **Registry Seed 文件结构**（第 105 节，line 3414-3432）：`schemas/midas/{civil,gen}/{2025,2026}/` + `registry/midas/{civil_2025,civil_2026,gen_2025,gen_2026}.json`。
- **Seed Loader**（第 106 节，line 3436-3454）：`MidasRegistrySeeder.seed()` 依序 insert_sources → insert_schemas → insert_endpoints，**必须 idempotent**。
- **Seed Integrity**（第 107 节）：`schema hash / source hash / version / generated_at / generator_version`。
- **Registry Import**（第 108 节）：`manual JSON / official manual extraction / verified live capture` → `Raw Source → Parser → Normalized Registry → Human Review → Contract Test → VERIFIED`。
- **自动导入原则**（第 109 节）：**不要**「网页 HTML → 自动猜字段 → 直接 production」，应走 `网页/JSON → Extract → Candidate → Review → Test → Verified`。
- **API Source Provenance**（第 110 节）：每条 registry entry 至少带 `source_url / source_title / source_revision / retrieved_at / source_hash`。
- **Registry Integrity Check**（第 111 节）：启动期 `registry load → schema hash check → duplicate check → version check → operation mapping check → transformer existence check`；若 production mapping 标 `VERIFIED` 但 transformer 不存在 → **FAIL FAST**。
- **Mock Adapter / Mock 边界**（第 112–113 节）：Mock 只证明「测试逻辑」，**不代表 MIDAS engineering correctness**，不得用 Mock 证明 MIDAS API schema 正确 / MIDAS analysis 正确 / MIDAS design 正确。
- **Deprecated Mapping**（第 80 节）：见 D.6 末段。
- **Version Migration（第 78 节）/ Registry Diff（第 79 节）/ Unknown Version（第 68 节）**：见 I.4。

## G.23 Adapter Production Checklist（第 149 节，line 4616-4639，逐字 20 项）

````
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
````

## G.24 Production Hardening Definition of Done（第 151 节，line 4709-4731，逐字 19 项）

````
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
````

---

# H. 完整执行序列（第 129 节）与 Source-Level Operation Resolver（第 130 节）

## H.1 第 129 节 Full Execution Sequence（line 4018-4084，逐字全文，共 40 步）

````
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
````

**步骤编号展开**（自上而下 33 个节点）：

| # | 步骤 | # | 步骤 |
|---|---|---|---|
| 1 | MCP Request | 18 | API Registry |
| 2 | Authentication | 19 | Transformer（出向） |
| 3 | IdentityContext | 20 | MIDAS HTTP |
| 4 | ExecutionContext | 21 | MIDAS API Server |
| 5 | Tool Resolution | 22 | CIVIL/GEN |
| 6 | Operation Resolution | 23 | Native Response |
| 7 | Software Instance Resolution | 24 | Transformer（入向） |
| 8 | Schema Validation | 25 | Canonical Result |
| 9 | Engineering Validation | 26 | Postcondition |
| 10 | Permission | 27 | Unlock |
| 11 | Quota | 28 | Persist |
| 12 | Confirmation | 29 | Audit |
| 13 | Idempotency | 30 | Trace |
| 14 | Lock | 31 | Event |
| 15 | Capability | 32 | MCP Response |
| 16 | Task | | |
| 17 | MIDAS Adapter | | |

## H.2 第 130 节 Source-Level Operation Resolver（line 4088-4130，逐字全文）

````python
# 130. Source-Level Operation Resolver

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
````

**该 Resolver 的四条硬性语义**：

1. `registry.resolve(product, version, operation)` —— 解析键是 **product + version + operation**（不含 path/method）。
2. `mapping is None` → 抛 `CapabilityNotSupported(operation)`。
3. `mapping.verification_status != "VERIFIED"` → 抛 `RegistryMappingNotVerified(operation)`（**这就是第 14 节 66 条种子在未验证前不可用于生产的执行点**）。
4. `transformer = self.transformers.resolve(mapping.transformer)` —— transformer 由 Registry 的**名字**解析，再由 `client.request(method=mapping.method, path=mapping.path)` 发请求，最后 `transformer.from_native(response, mapping)`。

## H.3 配套反模式禁令（第 131 节，line 4134-4166，逐字）

````
禁止：

if operation == "MODEL.NODE.CREATE":
    ...
elif operation == "MODEL.ELEMENT.CREATE":
    ...
elif operation == "ANALYSIS.STATIC":
    ...

原因：

版本增长
产品增长
endpoint 增长
代码会爆炸

应该：

operation
 ↓
registry
 ↓
mapping
 ↓
transformer
````

## H.4 最终内部调用映射（第 156 节，line 4875-4904，逐字）

````
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
````

然后：`Capability → MIDAS Registry → Transformer → Native API`。

---

# I. Definition of Done / 验收场景 / 生产检查清单

## I.1 第 150 节 MIDAS Adapter Definition of Done（line 4643-4705，逐字全文）

````
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
````

**计数**：Registry 9 + Model 6 + Analysis 7 + Result 6 + Design 5 = **33 项**。

## I.2 第 151 节 Production Hardening DoD —— 见 G.24（19 项）。

## I.3 第 162 节 最终完成标准（line 5128-5170，逐字，共 37 项）

> 「当以下全部满足时，MIDAS Adapter 才能从 Alpha 进入 Beta」

````
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
````

## I.4 第 157 节 最终验收场景（line 4908-4944，逐字）

````
必须实现：

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
````

同时验证：`Audit` / `Trace` / `Metrics` / `Task` / `Recovery`。

## I.5 第 74–75 节 CIVIL NX 完整工程 E2E 验收场景（line 2488-2551，逐字）

目标：

````
创建一个高度 6m 的钢柱
Q355B
H400x400x13x21
底部固定
顶部 500kN 轴压力
执行静力分析
读取顶部位移
执行钢结构设计
返回利用率
````

Pipeline：

````
BUILD.COLUMN
 ↓
MODEL.LOAD.ASSIGN
 ↓
ANALYSIS.STATIC
 ↓
RESULT.NODE.DISPLACEMENT
 ↓
DESIGN.STEEL
````

AI 自然语言（line 2525-2527）：`创建一个高度 6m 的 Q355B H400×400×13×21 钢柱，底部固定，顶部施加 500kN 轴压力。完成静力分析，并返回顶部节点位移和钢柱设计利用率。`

**AI 不需要知道**：`/db/NODE` / `/db/ELEM` / `/doc/ANAL` / ...

AI 应调用（第 155 节，line 4866-4870）：`engineering_model_build` / `engineering_model_assign` / `engineering_analysis` / `engineering_result` / `engineering_design`；**AI 不应该生成** `POST /db/NODE` / `POST /db/ELEM` / ...（line 4857-4861）。

## I.6 测试矩阵

**第 142 节 CIVIL E2E 测试矩阵（line 4434-4453，逐字表格）**：

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

（16 行 × 3 列，全 ✓。）

**第 143 节 GEN E2E 测试矩阵（line 4457-4477）**：与 CIVIL 相同 Core contract —— `Connect / Health / Version / Model / Analysis / Result / Design`；但**所有 native mapping 都从 `product = GEN NX` 解析**。

**第 71 节 Contract Test 分层（line 2415-2435）**：

````
L1 Static Registry Test
L2 Schema Test
L3 Mock Transport Test
L4 Live MIDAS Contract Test
L5 Business Effect Test
````

CI 默认跑 `L1-L3`；专用 MIDAS 环境跑 `L4-L5`。

**第 72 节 Contract Test 安全（line 2439-2454）**：Live Test 必须使用 `dedicated MIDAS instance` / `dedicated API key` / `dedicated project` / `dedicated test model`，**不得用 production model**。

**第 73 节 CIVIL NX E2E 第一条（line 2458-2484，逐字）**：

````
1 Connect
2 Health
3 Version
4 Node Query
5 Node Create
6 Node Query
7 Node Delete
8 Document Save
````

第二阶段：`Element / Material / Section / Boundary / Load / Analysis / Result / Design`。

**第 77 节 GEN NX E2E（line 2596-2632）**：`Connect → Health → Version → Query Node → Create Node → Query Element → Material → Section → Boundary → Load → Analysis → Result`，然后 `Design / View / Capture`。

**第 136 节 Node Contract Test Example（line 4298-4312，逐字）**：

````python
async def test_node_get(live_midas):
    result = await live_midas.get("/db/NODE")

    assert result.status_code == 200
    assert isinstance(result.json(), dict)
````

**不要仅测试 HTTP，必须验证 JSON schema。**

**第 137 节 Node Create Contract Test（line 4316-4338，逐字）**：

````
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
````

## I.7 第 161 节 下一阶段实现顺序（line 5095-5124，逐字 24 步）

````
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
````

## I.8 第 158 节 最终工程原则（line 4948-5008，逐字 10 条）

````
### 原则 1   Core 不认识 MIDAS endpoint
### 原则 2   Tool 不认识 MIDAS endpoint
### 原则 3   Operation 不认识 MIDAS endpoint
### 原则 4   Adapter Registry 认识 MIDAS endpoint
### 原则 5   Transformer 认识 MIDAS JSON
### 原则 6   只有 VERIFIED Mapping 才能进入生产执行
### 原则 7   未知执行结果必须 Reconcile
### 原则 8   AI 永远不能绕过 Core Security
### 原则 9   MIDAS 版本差异必须由 Registry/Adapter 吸收
### 原则 10  Canonical Model 必须保持软件无关
````

## I.9 多版本 / 迁移 DoD（第 61–68、78–80 节）

- **版本选择（第 61 节，line 2134-2144）**：`Exact → Compatible Range → Fallback → Reject`。支持 `CIVIL NX 2025 / 2026`、`GEN NX 2025 / 2026`，未来 `2027+`。
- **Version Adapter Manifest（第 62 节）**：`midas.civil` / `midas.gen`，`supported_versions: ["2025","2026"]`，`protocols: ["REST"]`。
- **Unknown Version（第 68 节）**：MIDAS 版本 2027 而 Registry 只有 2025/2026 → 默认 `READ_ONLY / DEGRADED`，除非 compatible mapping 已验证。
- **Capability Cache（第 66 节）** 字段：`instance_id / product / version / capability / status / checked_at / expires_at / source`；状态 `SUPPORTED / UNSUPPORTED / UNKNOWN`。
- **Capability Refresh 触发（第 67 节）**：`startup / connect / reconnect / version change / manual refresh / registry update`。
- **API Version Migration 流程（第 78 节）**：`Import official manual → Generate candidate registry → Diff → Schema diff → Contract Test → Mark VERIFIED → Enable`；**不得直接复制 2026 mapping**。
- **Registry Diff 比较项（第 79 节）**：`path / method / schema / required fields / optional fields / enum / response / status`；输出 `ADDED / REMOVED / CHANGED / UNCHANGED`。
- **第 163 节 原文档↔章节映射表（line 5174-5192，逐字）**：

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

## I.10 第 164 节 最终结论结构（line 5198-5275，逐字要点）

最终抽象保持：`MCP Tool → Operation → Capability → Adapter → Registry → Transformer → Native API`。
当前支持 `MIDAS CIVIL NX / MIDAS GEN NX`，为后续 `ETABS / SAP2000 / ANSYS / ABAQUS / OpenSees` 保留统一 Adapter SDK。
**本文件即作为原 ⑰～㉛合并后的 MIDAS 主实现规范。**

---

# J. 全文所有 MIDAS API 引用（第 14 节清单之外）

> 检索方法：对全文做 `/(db|doc|ope|view|info|api)/[A-Za-z]` 与 `(baseURL|base_url|GET |POST |PUT |DELETE |MAPI)` 两类正则全量扫描，命中 128 + 30 条，逐条归并如下。**第 14 节的 66 条种子已单列于 B 项，本节只列「其他位置」的引用。**

## J.1 端点路径引用（按小节归类，逐条）

| # | 引用 | 方法 | 出处小节 | 行号 | 上下文语义 |
|---|---|---|---|---|---|
| 1 | `/doc/NEW` | POST | 15 API Registry Seed 格式 | 753 | Seed JSON 示例 `"path": "/doc/NEW"`，`operation = DOCUMENT.NEW`，`verification_status = VERIFIED`（示例用，line 764 否证其自动性） |
| 2 | `/db/NODE` | GET | 18 API Contract Snapshot | 861 | 契约快照示例 `"method": "GET", "path": "/db/NODE"` |
| 3 | `baseURL/info/db/...` | — | 19 Info API | 876 | Info API：查看 DB resource 的 key/value 说明，用于 Registry Discovery / Schema Verification / 开发期辅助 / Contract Test；**info API ≠ 生产业务 API** |
| 4 | `/db/NODE` | — | 22 Node CRUD | 983 | 「MIDAS：/db/NODE」 |
| 5 | `/db/NODE` | GET | 22 Node CRUD | 991 | 「查询：GET /db/NODE」 |
| 6 | `/db/...` | GET | 22 Node CRUD | 994 | 官方 Get Object 说明 DB 查询可通过 `/db/...` 获取 JSON 数据 |
| 7 | `/db/ELEM` | — | 25 Element 创建 | 1082 | 「MIDAS /db/ELEM」 |
| 8 | `/ope/SECTPROP` | — | 30 Section Property | 1223 | 「可作为 section-property operation 的 native mapping 候选」 |
| 9 | `/doc/ANAL` | — | 35 Analysis Runtime | 1370 | 「官方 MIDAS API Manual 将 /doc/ANAL 列为 Perform Analysis」 |
| 10 | `/anal/STATIC` | — | 35 Analysis Runtime | 1385 | **反例**：`ANALYSIS.STATIC` 不应直接硬编码成某个未经验证的 `/anal/STATIC` 路径 |
| 11 | `/doc/ANAL` | — | 35 Analysis Runtime | 1396 | 正确架构终点「MIDAS /doc/ANAL」 |
| 12 | `/doc/ANAL` | POST | 41 Analysis Unknown Outcome | 1541 | 「POST /doc/ANAL ↓ timeout」 |
| 13-19 | `/view/SELECT`、`/view/CAPTURE`、`/view/PRECAPTURE`、`/view/ANGLE`、`/view/ACTIVE`、`/view/DISPLAY`、`/view/RESULTGRAPHIC` | — | 48 View Runtime | 1732-1738 | 「官方 Manual 中明确列出」7 条，应通过 View Registry 映射（与第 14 节 VIEW 分区完全一致） |
| 20 | `/view/CAPTURE` | — | 50 Capture Artifact | 1771 | 「如果 /view/CAPTURE 返回图片」→ image bytes → ArtifactStorage → artifact_id |
| 21 | `/db/DCON` | — | 52 Design Runtime | 1838 | 设计相关 DB resource 候选（用途须依官方 endpoint 文档验证） |
| 22 | `/db/MATD` | — | 52 Design Runtime | 1839 | 同上 |
| 23 | `/db/RCHK` | — | 52 Design Runtime | 1840 | 同上 |
| 24 | `/db/LENG` | — | 52 Design Runtime | 1841 | 同上 |
| 25 | `/db/MEMB` | — | 52 Design Runtime | 1842 | 同上 |
| 26 | `/db/DCTL` | — | 52 Design Runtime | 1843 | 同上 |
| 27 | `/db/LTSR` | — | 52 Design Runtime | 1844 | 同上 |
| 28 | `/db/ULCT` | — | 52 Design Runtime | 1845 | 同上 |
| 29 | `/db/MBTP` | — | 52 Design Runtime | 1846 | 同上 |
| 30 | `/db/WMAK` | — | 52 Design Runtime | 1847 | 同上 |
| 31 | `/db/DSTL` | — | 52 Design Runtime | 1848 | 同上 |
| 32 | `/db/NODE` | GET | 70 Contract Test Fixture | 2395 | fixture `"method": "GET", "path": "/db/NODE"`，operation `MODEL.NODE.QUERY` |
| 33 | `/db/NODE` | — | 75 E2E 预期 MCP 行为 | 2547 | 「AI 不需要知道」清单 |
| 34 | `/db/ELEM` | — | 75 E2E 预期 MCP 行为 | 2548 | 同上 |
| 35 | `/doc/ANAL` | — | 75 E2E 预期 MCP 行为 | 2549 | 同上 |
| 36 | `/doc/NEW` | — | 94 Document Runtime | 3124 | StructAI `NEW` ↔ MIDAS `/doc/NEW` |
| 37 | `/doc/OPEN` | — | 94 Document Runtime | 3125 | ↔ `OPEN` |
| 38 | `/doc/SAVE` | — | 94 Document Runtime | 3126 | ↔ `SAVE` |
| 39 | `/doc/SAVEAS` | — | 94 Document Runtime | 3127 | ↔ `SAVE_AS` |
| 40 | `/doc/CLOSE` | — | 94 Document Runtime | 3128 | ↔ `CLOSE` |
| 41 | `/doc/ANAL` | POST | 121 API Contract Failure | 3808 | 「Registry: POST /doc/ANAL，实际: 400」→ 不得盲目重试 |
| 42 | `/api/admin/midas/request-test` | — | 134 Raw API Debug | 4251 | **内部 Admin API，不是 MCP Tool**；需 `SYSTEM_ADMIN` 或 `API_TEST` 权限 |
| 43 | `/db/NODE` | GET | 136 Node Contract Test Example | 4302 | `result = await live_midas.get("/db/NODE")` |
| 44 | `/db/NODE` | POST | 155 最终 AI 调用示例 | 4858 | 「AI 不应该生成」的反例 |
| 45 | `/db/ELEM` | POST | 155 最终 AI 调用示例 | 4859 | 同上 |
| 46 | `/db/MATL` | — | 27 Material Transformer | 1142 | 「StructAI 不直接把 MIDAS MATL JSON 暴露给 AI」 |
| 47-63 | 17 条官方基线端点 | — | 160 官方事实 | 5052-5068 | 见 C.2 表（与第 14 节重叠） |

**「只出现一次、且不在第 14 节清单内」的路径**：`/anal/STATIC`（反例，line 1385）、`baseURL/info/db/...`（line 876）、`/api/admin/midas/request-test`（line 4251）。

## J.2 HTTP 方法引用（全文）

| 方法 | 出处 | 行号 | 语义 |
|---|---|---|---|
| `GET` | 1.1 官方 API 总体定位 | 88 | DB Endpoint 通常使用 GET |
| `POST` | 1.1 | 89 | DB Endpoint 通常使用 POST |
| `PUT` | 1.1 | 90 | DB Endpoint 通常使用 PUT |
| `DELETE` | 1.1 | 91 | DB Endpoint 通常使用 DELETE |
| `POST` | 1.1 | 94 | **DOC Endpoint 使用 POST** |
| `POST` | 6 MIDAS HTTP Client | 347 | `MidasHttpClient.post` |
| `GET` / `POST` / `PUT` / `DELETE` | 6 MIDAS HTTP Client | 344/347/350/353 | 客户端四方法 |
| `POST` | 14 DOC 分区 | 664 | DOC 只用 POST，body 从 `Argument` 开始 |
| `GET/POST/PUT/DELETE` | 14 DB 分区 | 717 | DB 基本机制；POST/PUT 第一层关键字通常为 `Assign` |
| `GET` | 15 Seed 格式 | 754 | `"method": "POST"`（DOCUMENT.NEW） |
| `GET` | 18 Contract Snapshot | 860 | 快照示例 method=GET |
| `POST` | 22 Node CRUD | 986 | Create Node 通过 POST |
| `DELETE` | 22 Node CRUD | 986 | 删除使用 DELETE |
| `GET` | 22 Node CRUD | 991 | 查询 GET /db/NODE |
| `POST` | 41 Unknown Outcome | 1541 | POST /doc/ANAL |
| `POST` | 69/70 Contract Test | 2394 | fixture method=GET（`MODEL.NODE.QUERY`） |
| `GET` | 82 Retry Policy | 2751 | 「允许 retry：GET query」 |
| `POST` | 82 Retry Policy | 2759 | 「谨慎 retry：POST」 |
| `PUT` | 82 Retry Policy | 2760 | 「谨慎 retry：PUT」 |
| `DELETE` | 82 Retry Policy | 2761 | 「谨慎 retry：DELETE」 |
| `POST` | 121 API Contract Failure | 3808 | POST /doc/ANAL → 400 |
| `GET` | 135 Real MIDAS Debug Workflow | 4273/4281 | Get Object → … → PUT/POST → GET |
| `PUT`/`POST` | 135 | 4279 | 写入 |
| `GET` | 136 Node Contract Test | 4302 | `live_midas.get` |
| `GET` | 137 Node Create Contract Test | 4321/4327/4333 | GET → POST → GET → DELETE → GET |
| `POST` | 137 | 4325 | POST |
| `DELETE` | 137 | 4331 | DELETE |
| `POST` | 155 | 4858/4859 | POST /db/NODE、POST /db/ELEM |
| `POST` | 160 | — | （无显式方法） |

## J.3 表代码 / DB resource 代码（非端点路径形式的引用）

**第 14 节 DB 分区 43 条**（见 B.2）+ **第 52 节设计类 11 条**（见 J.1 #21-31）+ **第 27 节 `MATL`**（line 1142）。

**第 30 节** 另有 `DESIGN.STEEL` vs `SECTPROP` 的语义区分（line 1228-1230）。

## J.4 MIDAS Schema URI 引用（第 13 节，line 596-620）

| URI | 用途 | 行号 |
|---|---|---|
| `midas://civil/node/request/v1` | CIVIL 节点请求 schema | 612 |
| `midas://civil/node/response/v1` | CIVIL 节点响应 schema | 613 |
| `midas://civil/elem/request/v1` | CIVIL 单元请求 schema | 615 |
| `midas://civil/elem/response/v1` | CIVIL 单元响应 schema | 616 |
| `midas://gen/node/request/v1` | GEN 节点请求 schema | 618 |
| `midas://gen/node/response/v1` | GEN 节点响应 schema | 619 |
| `midas://civil/doc/new/request/v1` | 第 15 节 Seed 示例 | 756 |
| `midas://civil/doc/new/response/v1` | 第 15 节 Seed 示例 | 757 |

StructAI 侧对照（line 603-606）：`structai://schema/model/node/v1`、`.../element/v1`、`.../material/v1`、`.../section/v1`。

## J.5 认证 / 连接头引用

| 引用 | 出处 | 行号 |
|---|---|---|
| `MAPI-Key`（关键认证信息） | 5.1 官方连接信息 | 289/297 |
| `MAPI-Key → Secret Reference → CredentialProvider` | 5 MIDAS 连接模型 | 305-307 |
| 请求头 `MAPI-Key: <secret>` / `Content-Type: application/json` / `Accept: application/json` | 6 HTTP Client | 363-365 |
| 「不要把 MAPI-Key 放在 URL Query」 | 6 HTTP Client | 368 |
| `MAPI-Key` 在共享能力清单 | 63 CIVIL NX 与 GEN NX | 2190 |
| 「MAPI-Key valid」健康检查项 | 86 Health Check | 2851 |
| 日志禁止打印 `MAPI-Key` | 90 Logging | 2989 |
| 「MAPI-Key 可以被刷新」 | 147 API Key Refresh | 4570 |
| `MAPI-Key` 在最终架构图中 | 164 最终结论 | 5231 |
| `base_url: "http://..."` / `secret_ref: "secret://midas/instance/001/mapi-key"` | 115 Secret Configuration | 3664-3665 |
| `base_url` 为 `software_instances` 字段 | 116 Instance Registry | 3690 |
| `Base URL and API-KEY` 官方页面 | 159 官方资料基线 | 5022-5023 |
| `Easyway to use the baseURL/DB` 官方页面 | 159 官方资料基线 | 5034-5035 |

## J.6 API 分类与产品名引用

| 引用 | 出处 | 行号 |
|---|---|---|
| `DOC / DB / OPE / VIEW / POST` 五分类 | 1.1 | 69-75 |
| `POST` 分类（结果/表格输出型） | 1.1 | 83 |
| `DOC / DB / OPE / VIEW / POST` 在 DoD 中 | 150 Registry DoD | 4648-4652 |
| `CIVIL NX + GEN NX` 共享 REST / MAPI-Key / DOC / DB / OPE / VIEW | 63 | 2188-2195 |
| `POST Registry` 待办 | 150 DoD | 4652 |

## J.7 明确「非 MIDAS 官方 API」的路径（避免误用）

| 路径 | 出处 | 行号 | 说明 |
|---|---|---|---|
| `/anal/STATIC` | 35 Analysis Runtime | 1385 | 明确点名**未经验证**，不得硬编码 |
| `/api/admin/midas/request-test` | 134 Raw API Debug | 4251 | StructAI **内部** Admin API，非 MCP Tool、非 MIDAS 官方端点 |
| `baseURL/info/db/...` | 19 Info API | 876 | 官方 info API，但「info API ≠ 生产业务 API」，不得跳过版本验证当作稳定契约 |

---

# K. 未能完成 / 需提请注意的事项

1. **第 14 节无任何单条状态标记**。任务描述中「状态标记（如 VERIFIED/PARTIAL/UNVERIFIED/DEPRECATED）」在第 14 节原文中**不存在**；只有第 8 节的四态定义与第 15 节的一句否证。本报告已在 B.5 给出推定结论（统一为 PARTIAL 语义档位）并逐字标注依据行号，未虚构任何单条标记。
2. **文档计数为 66 条**（DOC 11 + DB 43 + OPE 5 + VIEW 7），而非 68。第 160 节仅将其中的 17 条端点列入「官方基线」。
3. **第 9 节列出 7 张表，但仅 3 张有字段定义**：`midas_api_versions`、`midas_api_mappings`、`midas_api_verifications`、`midas_capability_mappings` 在全文（含第 11/12 节）**未给出字段定义**——这是文档的空缺，不是本次漏读。
4. 原文第 664、717、898、994、4294、5040 行末尾带有形如 `cite...turn0search0/turn0search7/turn0search9/turn0search11` 的引用残留标记，系合并时未清理的检索引用，本报告按「cite …」保留。
5. 全文 grep 命中的 `POST /db/NODE`（line 4858）等属「AI 不应该生成」的**反例**，非推荐用法。
