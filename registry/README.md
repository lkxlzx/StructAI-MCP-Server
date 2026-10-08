# StructAI Endpoint Registry

MIDAS Open API 的**机器可读端点注册表**。由四份官方/权威来源交叉合并生成，可直接被 StructAI MCP Server 加载。

## 1. 数据来源

| 来源 | 语言 | 覆盖 |
| --- | --- | --- |
| MIDAS API Online Manual（Help Center 官方 JSON API） | 英文 | NX 系列（CIVIL NX / GEN NX）主手册 |
| midas Civil NX - API（wolai 快照 2024-12） | 中文 | CIVIL NX 补充端点 + 中文名 + `info/db/{CODE}` 字段表 |
| Dennis5882/MIDAS-API（GitHub，官方手册韩文版整理） | 韩文 | DESIGN 设计代码命名空间 + 实测勘误 |
| midas Civil Designer - API（wolai 快照） | 中文 | Civil Designer（REST + WebSocket） |

## 2. 目录结构

```text
registry/
├── manifest.json          全量索引（key / uri / methods / products / 文件路径 / 统计）
├── instances.yaml         实测实例矩阵（availability / verified_on / unavailable_on 的溯源）
├── designer_params.json   Civil Designer 手册的请求参数表原文（无 JSON Schema 时的证据来源）
├── design_codes.yaml      设计规范（Design Code）候选枚举：155 条 / 三套体系（见 §7）
├── README.md              本文件
├── common/                多产品共有端点（GEN_NX ∩ CIVIL_NX）
│   ├── doc/  db/  ope/  view/
│   └── post/TABLE/        结果表（按 TABLE_TYPE 拆分为独立 key）
├── products/
│   ├── gen_nx/            仅 GEN NX
│   ├── civil_nx/          仅 CIVIL NX
│   └── civil_designer/    仅 Civil Designer
├── design/                DESIGN 命名空间（设计代码接口，STEEL / RC / SRC）
├── schema/                各端点的 JSON Schema（draft-07 声明 440 / 未声明 175 —— 见 §2.1）
└── tools/                 生成与校验工具（见 §8）
```

### 2.1 JSON Schema 方言与装载现状（P09 裁决，2026-10-05）

`registry/schema/` 的 **616** 个文件是**请求体 Schema**，形态有两种：`{<请求体包装根键>: <JSON Schema>}`
（如 `ACTL` / `Argument` / `TABLE`；**378** 个）与直接就是 JSON Schema（**238** 个）。

| 项 | 实测值 | 说明 |
| --- | --- | --- |
| 文件数 | **616** | 与 `manifest.json` 中带 `schema` 的端点 **1:1**（无孤儿、无缺文件） |
| 可装载 | **616** | 剥离包装根键后原样登记（**不改写任何取值**） |
| 无法装载 | **0** | P138a 前为 **1**（`products/gen_nx/db/MBTP.json` 的 `schema` 是**坏串**，见下） |
| `$schema` 声明 | **441** `draft-07` / **175** 未声明 | 按**生效 Schema**（剥离包装根键后）统计 |
| 不是合法 JSON Schema | **0** | P138a 前为 **4**（`DESIGN.SRC.AIK-SRC2K.{MATD,MCRD,MRBD}` 的占位分支 + `OPE.EDMP` 的 `type: "Number"`） |

**方言裁决（`docs/07` §16 R18）**：**按各 Schema 自身声明的方言校验**（draft-07 → `Draft7Validator`；
未声明 / 未知 → 项目标准 **Draft 2020-12**，`docs/02` §12 / §13 / §22）。
依据：本目录是外部软件 API 的**唯一权威来源**，Schema 原样登记；用 2020-12 解释 draft-07 文档会**静默改变语义**
（`exclusiveMinimum` 布尔 vs 数值、`definitions` / `items` / `prefixItems`），实测 draft-07 的数组形式 `items`
喂给 2020-12 校验器时直接抛异常。Core 自有的 `schemas/`（`docs/02` §22）仍一律用 Draft 2020-12。

⚠️ **R19 已收口（P138a）**：本目录**不再有**数据缺陷 —— 修复固化在生成链工具
`registry/tools/fix_schema_defects.py`（见 §8.3），逐条差异可复算；`SchemaEngine.check_schema()`
的失败数 **4 → 0**，**616/616** 可装载。注意 `jsonschema` 在实例校验时**不**检查 Schema 自身，
非法关键字会被**静默忽略**（校验变宽松），故 Core 侧仍由 `check_schema()` 显式诊断。
另：**20** 个端点仍**没有** JSON Schema（`docs/07` §16 R5，P138b 已按**实测**分类，见 §8.4），本目录不臆造。

### 2.2 response 方向 Schema（P136 裁决，2026-10-08 之后）

`registry/schema/**` 的**同一份文件**同时承载两个方向（**不**新增文件，故文件数仍 **616**、
与 `manifest.json` 带 `schema` 的端点仍 **1:1**）：

| 键 | 方向 | 来源 |
| --- | --- | --- |
| `schema` | 请求体 | 外部手册 / 权威来源**原样登记**（P136 **一行未改**） |
| `response` | **响应信封** | `{direction: "response", source, schema}` —— 由 `tools/sync_response_schemas.py` 按**实测信封**生成 |

**覆盖口径（「已实测」，**不**臆造）**：`availability == verified`（§4：至少一个实例 GET 成功）
**且** `methods` 含 `GET` **且**该端点有可读的 Schema 文件 **且**声明了解包链 —— 共 **239** 个端点
（`verified` + `GET` 的 245 个里，6 个尚无 Schema 文件：`DB.LCOM` / `OPE.PROJECTSTATUS` /
`OPE.SECTPROP` / `OPE.STORY_IRR_PARAM` / `OPE.STORY_PARAM` / `VIEW.SELECT`）。

**`response.schema` 只断言实测到的信封层级**（载荷字段一个都不写）：

| 情形 | 分支 |
| --- | --- |
| NX 系（§4 的 `{<read_root>: {...}}` 实测口径） | `{"required": [<read_root>], "properties": {<read_root>: {"type": "object"}}}` |
| 声明了解包链（`CIVIL_DESIGNER` 的 `result.return_value`，§8.1 / R83） | 按链逐层 `required` / `properties`，**叶子类型留空**（未实测 → 不猜） |
| 一个端点的多个产品信封不同（如 `DB.NODE`） | `oneOf` 列出各分支 |

**效果（`docs/07` §16 R87）**：`docs/04` §8 的 7 项 AND 里「Response Schema 已确认」
不再恒为假 —— 判定点仍是**同一处**（`app/infrastructure/adapters/midas/live.py` 的
`seven_and_verdict` / `registry_evidence`，经 `MidasRegistry.response_schema_document()` 读数据）。
**P138a 收口后**：**239 / 239** 个已实测端点 7 项全满足 —— 原唯一例外 `DB.MBTP`
（缺「Request Schema 已确认」，因它的 `schema` 是非法 JSON 字符串）已按上游手册重建为合法对象。

**`request_schema_confirmed` 对无请求体端点「不适用」（P138b 裁决）**：`methods` 不含
`POST` / `PUT` / `PATCH` 的端点（`DB.LCOM` / `OPE.PROJECTSTATUS` / `OPE.SECTPROP` /
`VIEW.SELECT`）**没有请求体**，把「没有请求 Schema」判成缺口是**类别错误**（会让这类端点**永远**
`PARTIAL`）→ 该项视为满足，并由 `live.not_applicable_items()` **如实**报出。判定口径**未改**：
`verification_status` 仍只由 `availability` 机械映射（`docs/07` §7.2 / §16 R78）。

**落库（P137a，2026-10-08 之后）**：`MidasRegistryImporter` 把**两个方向**都导进
`midas_api_schemas`（`direction = "response"`，URI = `midas://<product>/<code>/response/v1`），
并**回填** `midas_api_endpoints.response_schema_id` 与 `midas_api_mappings.response_schema`
（存的是 Schema 行的 id，与 `request_schema*` 同口径）—— 该表自 **P138a** 起为
**855** 行 = 请求 **616** + 响应 **239**（P137a 时为 854 = 615 + 239）；未声明 `response`
块的端点仍为 `None`（**不**臆造）。
数据侧仍**可复算**：`sync_manifest.py` / `sync_response_schemas.py` / `fix_schema_defects.py`
预演差异均为 **0**。

```powershell
python registry/tools/fix_schema_defects.py --check   # R19 不变量自检（CI）
python registry/tools/fix_schema_defects.py --write   # 生成链归一（幂等）
python registry/tools/sync_manifest.py --write         # 派生 manifest（products 等）
python registry/tools/sync_response_schemas.py         # 预演（只打印差异）
python registry/tools/sync_response_schemas.py --write # 写回（只追加 response 块）
```

## 3. 统计

- 端点定义（Registry key）：**636**
- JSON Schema 文件：**616**

| 桶 | 数量 | 说明 |
| --- | --- | --- |
| common | 370 | GEN NX 与 CIVIL NX 共有 |
| products/gen_nx | 100 | GEN NX 独有 |
| products/civil_nx | 17 | CIVIL NX 独有 |
| products/civil_designer | 24 | Civil Designer 独有 |
| design | 125 | DESIGN 命名空间（设计代码） |

命名空间分布：

| 命名空间 | 数量 |
| --- | --- |
| DB | 244 |
| POST | 199 |
| DESIGN | 125 |
| OPE | 34 |
| DOC | 21 |
| VIEW | 7 |
| OPRT | 6 |

## 4. EndpointDefinition 字段

| 字段 | 说明 |
| --- | --- |
| `key` | 逻辑 key，`<命名空间>.<代码>`；POST 表为 `POST.TABLE.<TABLE_TYPE>`；设计代码为 `DESIGN.<分组>.<代码>` |
| `namespace` | `DOC` / `DB` / `OPE` / `VIEW` / `POST` / `DESIGN` / `OPRT` |
| `uri` | 实际 URI（含前导斜杠），调用时为 `{base url}` + 此值 |
| `methods` | 实测可用方法集（**逐端点不同，不得统一假设**） |
| `tool_map` | 该端点由哪个 MCP Tool 路由 |
| `wrapper` | 请求体包装。**按实例产品不同**：NX 系为 `Assign`（DB / DESIGN）或 `Argument`（DOC / OPE / VIEW / POST）；**CIVIL_DESIGNER 为扁平结构**（`write: none`，实测确认，见测试报告附录 C），共有端点通过 `product_overrides.<产品>.wrapper` 覆盖 |
| `wrapper.read_root` | **读响应**的业务载荷根键（`{<read_root>: {...}}`，NX 系实测口径）。**只允许来自手册 Response 示例或实测**，不得从 URI 猜（见 §8.1） |
| `wrapper.read_root_path` | **读响应解包链**（可选，字符串数组）。用于「响应信封与 `read_root` 不一致」的产品：`CIVIL_DESIGNER` 实测业务载荷在 `result.return_value`，故其值为 `[result, return_value]`；NX 系不需要声明。优先级：`product_overrides.<产品>.wrapper.read_root_path` → 端点定义 `wrapper.read_root_path` → `read_root` → 未声明（客户端**必须**明确报错，禁止静默降级） |
| `schema_ref` | 本地 Schema 路径 / `info/db/{CODE}` 自省路径 / Schema 来源 |
| `products` | 支持该端点的产品 |
| `product_overrides` | 同名不同语义时的逐产品覆盖（如 Civil Designer 的 `/DOC/OPEN`） |
| `solver` | 求解器约束：`HYPER_S`（Hyper-S 专属）/ `GRID_MODEL`（网格模型分析专属）；**缺失表示标准求解器** |
| `availability` | 实测可用性：`verified`（至少一个实例成功）/ `unverified`（实测全部失败）/ `untested`（未测，因端点不含 GET） |
| `verified_on` / `unavailable_on` | 实测成功的实例别名 / 实测失败的实例别名（别名定义见 `instances.yaml`） |
| `enabled` / `disable_reason` | 为 `false` 时客户端直接拒绝调用（错误码 `ENDPOINT_DISABLED`） |
| `path_key_supported` | NX 系支持把 key 写在 URL 路径中（`{uri}/{key}`）。**实测 + 官方手册：`DELETE {uri}` 不带路径 key 会删除全表**，单条删除必须写 `DELETE {uri}/{key}` |
| `schema_ref.params_ref` | 当源手册只有请求参数表、没有 JSON Schema 时，指向 `designer_params.json#<URI>` 的原始参数证据 |
| `schema_ref.shape` | 请求体形态：`flat_object` / `flat_array` 表示根级扁平（CIVIL_DESIGNER，实测确认）；缺失表示按 NX 系的 `Assign` / `Argument` 包装 |
| `table_type` | POST 命名空间的 `Argument.TABLE_TYPE` 取值 |
| `title` | 官方原名（英文 / 韩文 / 中文，视来源而定） |
| `title_zh` / `title_zh_official` | 中文名。`title_zh_official: true` 为官方中文名；`false` 为**非官方译名**（当前仅 DESIGN 命名空间 125 个端点，按英文原名翻译，对照表见 `MIDAS_API_DESIGN中文名对照_v1.0.csv`） |
| `risk` | `level`（`DOC.ANAL` 为 `high`）/ `destructive`（端点本身是否破坏性）/ `retry`（逐方法重试策略：GET 可重试、POST/PUT 条件重试、DELETE 与 ANAL 不重试，对齐主开发文档 §102）/ `delete_without_body_is_global`（**实测：NX 系不带主体的 DELETE 会删除全表且返回 200 不报错**，客户端必须硬性拒绝无主体 DELETE） |
| `runtime` | `requires_project` / `requires_analysis` |
| `execution` | `mode`：`FAST` / `ASYNC` / `LONG` |
| `capability` | 能力域（MODEL / RESULT / DESIGN / GRAPHICS / PROJECT / OPERATION） |
| `source` | 官方原文 URL、抓取日期、来源清单 |
| `stats` | 参数字段行数 / 示例数 / 是否有 Response HEAD |
| `notes` | 实测注意项与源数据勘误（来自韩文版仓库的逐条核对） |

## 5. 使用方式

```text
1. 启动时加载 registry/manifest.json 建立 key -> 定义文件索引
2. Resolve：按 (product, version, solver, key) 定位定义；
   产品差异先查 product_overrides，再回落主定义
3. 调用前：校验 methods 是否包含目标方法；
   若不含，直接返回结构化错误，不发出请求
4. 组装请求：按 wrapper.write 包装（Assign / Argument）
5. 校验请求体：用 schema_ref.local 指向的 JSON Schema 做 Level 1 校验
6. 执行：按 execution.mode 选择同步或 Job 路径
```

## 6. 治理规则

1. **Common 层只收录多产品共有的端点**；产品差异一律进 `products/` 或 `product_overrides`。
2. **Registry 必须能由官方手册机械生成**，禁止手工誊抄。
3. MIDAS 手册更新时，重跑生成链产出新的 `registry_version`，保留旧版本。
4. `notes` 中的勘误优先于源手册原文；如与官方最新原文冲突，以实测为准并更新本文件。


## 7. 设计规范（Design Code）

`design_codes.yaml` 收录 MIDAS 的**三套独立规范体系**（共 155 条候选），
全部由官方手册枚举表逐行抽取（工具见 §8）：

| 体系 | 端点 | 字段 | 条数 | 说明 |
| --- | --- | --- | --- | --- |
| `nx_rc` | `DB.DCON` | `DGNCODE`（string） | **64** | NX 系混凝土设计规范 |
| `nx_steel` | `DB.DSTL` | `DGNCODE`（string） | **66** | NX 系钢设计规范 |
| `designer_module` | `DB.MODULE` | `DgnCode`（**integer**） | **22** | Civil Designer 中国公路/铁路桥涵规范，按 设计/评定/试验/加固 4 模块分组 |
| `designer_design` | `/DESIGN/{material}/{code}/…` | 路径段 | 3 | Civil Designer 设计代码命名空间（RC / STEEL / SRC） |

**含中国规范**：`GB/T50010-10`、`GB50010-02`（混凝土）；`GB50017-03`、`GBJ17-88`、`JTJ025-86`（钢）。

### 7.1 支持集如何确定（两段式）

1. **静态候选集** —— `design_codes.yaml`（来源：官方手册枚举表）。
   API **不提供**支持集枚举：
   - `/info/db/DCON` 返回的 schema 里 `DGNCODE` 是 `type: string`，**无 enum**；
   - 裸路径 `/DESIGN`、`/DESIGN/RC` 等一律 404，无法列子节点。
2. **运行时探测** —— Adapter 连接时用候选集做 `GET` 探测，得到该实例的**可用子集**：
   - `GET /DESIGN/{material}/{code}/DCO` → `200` 支持 / `404` 不支持；
   - 零副作用；结果只存连接会话，**不落盘**。
   - 实测（gen-local + civil-cloud）：`KDS-41-20-2022` → 200；
     `GB50010-2010` / `ACI318-19` / `AISC360-16` / `EN1992-1-1` / `AIJ` → 404。
3. **读当前生效值** —— `GET /db/DCON`、`GET /db/DSTL`、`GET /db/MODULE`
   （空项目返回 `{}` 或 `{"message":""}`，属正常空表，不是错误）。

Core 侧 `code` 保持**自由字符串**（规范中立，Core 内不出现任何厂商规范名）；
可用性校验由 Adapter 在调用前完成。

## 8. 生成与校验工具

| 工具 | 用途 |
| --- | --- |
| `tools/extract_design_codes.py` | 从官方手册抽取规范枚举 → `design_codes.yaml`（带条数断言，锚点漂移即报错） |
| `tools/sync_manifest.py` | 以端点 YAML 为真源，重建 `manifest.json` 的派生字段；默认预演，`--write` 写回 |
| `tools/sync_response_schemas.py` | 为**已实测**的端点补 `direction: response` 的 `response` 块（§2.2）；默认预演，`--write` 写回 |
| `tools/fix_schema_defects.py` | **R19 生成链归一**（§8.3）：坏串重建 / 占位分支合法化 / `type` 大小写；`--check` 自检不变量 |

```powershell
python registry/tools/extract_design_codes.py
python registry/tools/sync_manifest.py           # 预演（只打印差异）
python registry/tools/sync_manifest.py --write   # 写回
python registry/tools/sync_response_schemas.py   # 预演（只打印差异）
python registry/tools/sync_response_schemas.py --write   # 写回（只追加 response 块）
python registry/tools/fix_schema_defects.py --check     # R19 不变量自检（CI；不合规退出码 1）
python registry/tools/fix_schema_defects.py --write     # 生成链归一（幂等）
```

### 8.1 ⚠️ 已知缺陷：`read_root` 曾是「从 URI 猜的」

原生成器把 `wrapper.read_root` 取为 **URI 末段的大写**（`uri.split("/")[-1].upper()`），
既非手册 Response 示例、也非实测值。**实测已证实 8 处错误**（2026-10-05，gen-local，GET 零副作用）：

| Registry key | 原值（猜） | 实测根键 |
| --- | --- | --- |
| `DESIGN.RC.DRC` | `DRC` | **`DCON`** |
| `DESIGN.RC.KDS-41-20-2022.DCO` | `DCO` | **`DCORC`** |
| `DESIGN.RC.KDS-41-20-2022.DCRM-BEAM` | `DCRM-BEAM` | **`DCRMB`** |
| `DESIGN.RC.KDS-41-20-2022.DCRM-BRACE` | `DCRM-BRACE` | **`DCRMR`** |
| `DESIGN.RC.KDS-41-20-2022.DCRM-COLUMN` | `DCRM-COLUMN` | **`DCRMC`** |
| `DESIGN.RC.KDS-41-20-2022.DCRM-WALL` | `DCRM-WALL` | **`DCRMW`** |
| `DESIGN.RC.KDS-41-20-2022.SRDF` | `SRDF` | **`SRDFRC`** |
| `DESIGN.SRC.AIK-SRC2K.DCO` | `DCO` | **`SRCDCO`** |

**自 2026-10-05 起：端点 YAML 是唯一真源**；`read_root` 只允许来自手册 Response 示例或实测，
`manifest.json` 一律由 `tools/sync_manifest.py` 派生。

**2026-10-08（P134）全量只读实测**：对三个实例的**全部只读端点**（GEN NX 257 · CIVIL NX 216 ·
Civil Designer 14，合计 **487**）做零副作用 `GET` 探测并落库 `midas_api_verifications`
（`contract_level = L4`）。结果：**278** 条 `PASSED`（响应顶层键 == `read_root`，逐条证实）、
166 条 `PARTIAL`（数据块为空）、43 条 `FAILED`（404 = 产品 / 求解器可得性差异）。
证据见 `docs/reports/P134_L4_L5_实测报告_v1.0.md`。

本次实测又发现 **5 处 `read_root` 缺失**（原为空串，已按实测补齐）：

| Registry key | 原值 | 实测根键 | 证据实例 |
| --- | --- | --- | --- |
| `OPE.PROJECTSTATUS` | （空） | **`PROJECTSTATUS`** | gen-local + civil-cloud |
| `OPE.SECTPROP` | （空） | **`SECTPROP`** | civil-cloud |
| `OPE.STORY_IRR_PARAM` | （空） | **`STORY_IRR_PARAM`** | gen-local |
| `OPE.STORY_PARAM` | （空） | **`STORY_PARAM`** | gen-local |
| `VIEW.SELECT` | （空） | **`SELECT`** | gen-local |

**仍未实测**：**379** 个端点只有 `POST` / `PUT` / `DELETE`（写路径），只读探针覆盖不到，
需**专用测试项目**才能安全覆盖（跟踪项见 `docs/07` R4 / R14）。

> 附带修正：`DESIGN.SRC.AIK-SRC2K.DCO` 原 `methods: [PUT]` 漏标 GET（实测 200），
> 已改为 `[GET, PUT]` 并标 `verified`；`DESIGN.SRC.AIK-SRC2K.OCHECK` 实测 404，已标 `unavailable_on: [gen-local]`。

### 8.2 产品可得性差异：按实测收口 `products`（P136a）

`docs/07` §16 **R85** 的 L4 实测（`docs/reports/P134_L4_L5_实测报告_v1.0.md` §4）
记录了 **21** 条「数据侧声明了某产品、但该产品的实例上路由 `404`」的端点。
P136 把该结论**落进数据**（**只**改 `products`；`availability` / `verified_on` /
`unavailable_on` / `enabled` 一行未改 —— 故 `verification_status` 不变，`docs/07` §7.2）：

| 组 | 条数 | 端点 | 改动 |
| --- | --- | --- | --- |
| GEN NX 上 `404` | **14** | `DB.CAMB` / `DB.CJFG` / `DB.CMCS` / `DB.CRGR` / `DB.DYFG` / `DB.DYLA` / `DB.DYNF` / `DB.EWSF` / `DB.GCMB` / `DB.GSBG` / `DB.PLCB` / `DB.RCHK` / `DB.STRPSSM` / `DB.WVLD` | `[CIVIL_NX, GEN_NX]` → `[CIVIL_NX]` |
| CIVIL NX 上 `404` | **5** | `DB.SDHY` / `DB.SDIS` / `DB.THRS` / `DESIGN.RC.KDS-41-20-2022.MATD` / `DESIGN.SRC.AIK-SRC2K.MATD` | `[CIVIL_NX, GEN_NX]` → `[GEN_NX]` |
| CIVIL NX 上 `404`，**本来**已如实记录 | **2** | `DB.UFTR` / `DB.UTBL` | **不动**（`unavailable_on: [civil-cloud]` + `availability: unverified` 已在） |

**效果**：解析期即**如实失败**（`STRUCTAI-3000 endpoint_not_available_for_product`），
不再发出必然 `404` 的请求（与 §4 的 `resolve` 口径一致）。实例级证据仍保留在
`unavailable_on`（`instances.yaml` 口径）。

**`DB.SPAN` 的 `GEN_NX` 已按同一口径摘除（P138d 裁决 A）**：它与上表 **14** 条**同形**
（`verified_on` 有非 GEN 实例、`unavailable_on` 有 `gen-local`、在 `gen-local` 上 `404`）——
只对那 14 条摘除、却对同形的 `DB.SPAN` 例外，是**口径不一致**。故其 `products` 由
`[CIVIL_DESIGNER, CIVIL_NX, GEN_NX]` 改为 `[CIVIL_DESIGNER, CIVIL_NX]`（**只**改 `products`）。
**恢复条件**：**更新**的 GEN NX 构建上 `/DB/SPAN` 路由成功（新的 L4 `PASSED`）→ 恢复 `GEN_NX`。
依据：`docs/07` §16 **R85**；可执行判定 =
`tests/test_midas_registry_p136.py::test_p138_span_gen_nx_is_removed_consistently_with_the_fourteen`。

**证据**：`docs/reports/P136_数据侧收口与L4复核_v1.0.md` §2 / §4；
可执行判定 = `tests/test_midas_registry_p136.py` + `tests/test_midas_write_probe_p135.py` 的 R85 用例。

### 8.3 R19 收口：生成链归一（P138a）

`tools/fix_schema_defects.py`（只依赖标准库、默认**预演**、`--write` 写回、**幂等**）
把 `registry/schema/**` 的 **3** 类缺陷一次修完，**不**手改单个产物文件：

| 缺陷 | 修法 | 依据 |
| --- | --- | --- |
| `DB.MBTP` 的 `schema` 是**坏串**（缺 1 个 `}`） | **从上游手册重新生成**：`MIDAS_API_Online_Manual_数据_v1.0.json` 的 `endpoints[].json_schema` 是**同一条坏串** → 补齐尾部闭合符后落成**对象** | 逐字节比对：374 个 `help_center` Schema 里 **373** 个与上游解析结果**完全相等**，唯一例外就是它 |
| **22** 处占位分支 `"...(전체 N개)"`（**7** 个文件） | 换成**合法**兜底分支：`type` 由**已转录成员**推断、`description` 注明「手册该表共 N 项，仅转录前 K 项（未逐项转录）」；`oneOf` → **`anyOf`** | 占位串**出自手册原文** `MIDAS_API_开发文档_v1.0.md`（该文件里同样出现 **22** 次）；`oneOf` 必须换关键字，否则兜底分支会让已转录取值**恰好匹配两次**、把合法取值全判为非法 |
| `OPE.EDMP` 的 `type: "Number"`（2 处） | `type` 大小写归一（`Number` / `String` / `Boolean` / `Object` / `Array` / `Integer` / `Null` → 小写） | 上游手册 `specifications` 参数表里另有 **1344** 处 `"Number"`，属**参数表**口径、**不**在 Schema 生成链内 |

**效果**：**616/616** 可装载（原 615）、`SchemaEngine.check_schema()` 失败 **4 → 0**、
`draft-07` 声明 **440 → 441**；`sync_manifest.py` / `sync_response_schemas.py` 预演差异仍为 **0**。
可执行判定：`python registry/tools/fix_schema_defects.py --check` +
`tests/test_midas_registry_p138.py`。

### 8.4 R5：20 个无 Schema 端点按**实测**分类（P138b）

**不**臆造、**不**新增文件（Schema 文件仍 **616** 个）。判据全部来自数据文件本身：

| 类 | 条数 | 端点 | 判据（可执行） |
| --- | --- | --- | --- |
| `no_request_body` | **4** | `DB.LCOM` / `OPE.PROJECTSTATUS` / `OPE.SECTPROP` / `VIEW.SELECT` | `methods` 不含 `POST`/`PUT`/`PATCH` ⇒ **没有请求体**，不需要请求 Schema |
| `manual_has_no_json_schema` | **5** | `OPE.MEMB` / `OPE.STOR` / `OPE.STORPROP` / `OPE.STORY_IRR_PARAM` / `OPE.STORY_PARAM` | 手册**有同一个 URI** 的条目，但 `json_schema` 为空（只有参数表） |
| `uri_differs_in_manual` | **1** | `OPE.BMLD` | 手册**没有**该 URI，只有同名 code 的 `db/BMLD` ⇒ **无法确认同一操作**，如实留缺 |
| `post_table_key_without_manual_table_type` | **3** | `POST.TABLE.{CONCURRENT_JOINT_FORCE, STORY_SHEAR_FORCE_COEFFICIENT, WEIGHT_IRREGULARITY_X}` | 手册条目的 `table_types` 为空 ⇒ 无法机械确认同一操作，如实留缺 |
| `absent_from_nx_manual` | **7** | `DOC.CLOSEALL` / `DOC.EXIT` / `OPE.CP{CREATE,EXPORT,UPDATEMODEL,UPDATERESULT}` / `OPE.STORYPROP` | 手册**完全没有**该 URI，也没有同名 code |

⚠️ 与旧提示词里的分组**不同**的两处（以**实测**为准）：① `OPE.MEMB` / `OPE.STOR` / `OPE.STORPROP` /
`OPE.STORY_*_PARAM` 的手册条目**就是同一个 URI**（不是「URI 不同」）；② `OPE.STORPROP` 在手册里**有**
同 URI 条目（旧提示词把它归入「手册完全没有」）。可执行判定 =
`tests/test_midas_registry_p138.py::test_p138b_the_twenty_missing_schemas_are_classified_by_measurement`。
