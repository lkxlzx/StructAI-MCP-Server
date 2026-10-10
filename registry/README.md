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

`registry/schema/` 的 **625** 个文件是**请求体 Schema**（P141 起；P140 时 620、P138a 时 616），形态有两种：`{<请求体包装根键>: <JSON Schema>}`
（如 `ACTL` / `Argument` / `TABLE`；**378** 个）与直接就是 JSON Schema（**247** 个；判据 = `schema` 是否只有**一个**非 JSON-Schema 关键字 的键）。

| 项 | 实测值 | 说明 |
| --- | --- | --- |
| 文件数 | **625** | 与 `manifest.json` 中带 `schema` 的端点 **1:1**（无孤儿、无缺文件；P141 起） |
| 可装载 | **625** | 剥离包装根键后原样登记（**不改写任何取值**） |
| 无法装载 | **0** | P138a 前为 **1**（`products/gen_nx/db/MBTP.json` 的 `schema` 是**坏串**，见下） |
| `$schema` 声明 | **447** `draft-07` / **178** 未声明 | 按**生效 Schema**（剥离包装根键后）统计（P141 起） |
| 不是合法 JSON Schema | **0** | P138a 前为 **4**（`DESIGN.SRC.AIK-SRC2K.{MATD,MCRD,MRBD}` 的占位分支 + `OPE.EDMP` 的 `type: "Number"`） |

**方言裁决（`docs/07` §16 R18）**：**按各 Schema 自身声明的方言校验**（draft-07 → `Draft7Validator`；
未声明 / 未知 → 项目标准 **Draft 2020-12**，`docs/02` §12 / §13 / §22）。
依据：本目录是外部软件 API 的**唯一权威来源**，Schema 原样登记；用 2020-12 解释 draft-07 文档会**静默改变语义**
（`exclusiveMinimum` 布尔 vs 数值、`definitions` / `items` / `prefixItems`），实测 draft-07 的数组形式 `items`
喂给 2020-12 校验器时直接抛异常。Core 自有的 `schemas/`（`docs/02` §22）仍一律用 Draft 2020-12。

⚠️ **R19 已收口（P138a）**：本目录**不再有**数据缺陷 —— 修复固化在生成链工具
`registry/tools/fix_schema_defects.py`（见 §8.3），逐条差异可复算；`SchemaEngine.check_schema()`
的失败数 **4 → 0**，**625/625** 可装载（P141 起）。注意 `jsonschema` 在实例校验时**不**检查 Schema 自身，
非法关键字会被**静默忽略**（校验变宽松），故 Core 侧仍由 `check_schema()` 显式诊断。
另：**11** 个端点仍**没有** JSON Schema（`docs/07` §16 R5；P138b 分类 20 个、**P140 补齐 4 个**、
**P141 补齐 5 个**，见 §8.4），本目录不臆造。

### 2.2 response 方向 Schema（P136 裁决，2026-10-08 之后）

`registry/schema/**` 的**同一份文件**同时承载两个方向（**不**新增文件，故 P136 时文件数仍 **616**、
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
**864** 行 = 请求 **625** + 响应 **241**（P141 起；P140 时为 859 = 620 + 239）；未声明 `response`
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

## 2.3 写路径请求体模板（P139）

`registry/live/write_templates.json` 是**写路径 L5** 的请求体**唯一**来源（`docs/07` §16 R4 / R14 的分子）。
P138c 实测暴露：`write_probe.derive_body()` 从 Schema 机械派生的零值 / 空引用请求体被实例拒绝
（GEN NX 的 10 个可探候选里 9 个 `400 software_api_error`）→ P139 把**真实请求体**落成**数据**
（**不**硬编码进 Core：`app/**` 里 0 处模板取值）。

| 键 | 说明 |
| --- | --- |
| `templates.<key>.source` | `{kind, uri, example, example_id, url, retrieved_at}`：**来源可追溯**（上游手册的哪个示例、哪条包装编号、抓取日期） |
| `templates.<key>.body` | 请求体（**未**包装；包装键仍由数据侧 Transformer 的 `wrapper_key()` 决定） |
| `templates.<key>.adjustments` | 逐条 `{path, from, to, why}`：对示例的**每一处**改动都要写明理由；`kind = manual_example` 时**必须**为空 |
| `templates.<key>.prerequisites` | 前置对象 `{key, item_id, body, source, adjustments, [references], [id_source]}`：目标请求体引用的对象**必须**先存在 → 探针按顺序创建、**逆序**删除（**只**碰自建编号） |
| `templates.<key>.self_references` | **目标自身**编号在 `body` 里的路径（`[["ITEMS", 0, "ID"]]` 形态）：探针把编号改成**实分配**编号后写回 |
| `templates.<key>.target_id_source` | **目标自身**编号的来源：`""`（缺省）= 该端点既有编号的 `max + 1`；或本模板里某个前置的 `<key>#<item_id>` = 取**该前置**分配到的编号（`DB.CONS` / `DB.CNLD` 的 `Assign` 键就是它那个节点号） |
| `prerequisites[].references` | `[{in, path}]`：该前置编号出现在**哪个 body 的哪个路径**（`in` = `owner` 或同一模板里另一个前置的标签）—— P141 / R96 的**非空项目**判据 |

**可复算（`tools/check_write_templates.py`，只依赖标准库）**：每条 `body` 必须**等于**
「上游手册 `MIDAS_API_Online_Manual_数据_v1.0.json` 的 `endpoints[].examples[].json` 某个编号下的条目」
再施加本文件声明的 `adjustments`；此外 body 的字段名**不得**超出该端点的数据侧请求 Schema，
前置链的 key 必须已登记 / 已启用 / 含 `POST`；**编号声明**（P141 起）逐条可判 ——
`references[].path` / `self_references[]` 必须**存在**且当前取值**恰好**等于声明的编号，
`target_id_source` 必须指向本模板里的一个前置且**不**构成循环依赖。
`tests/test_midas_write_templates_p139.py` 另用 `jsonschema`（按各 Schema 声明的方言）逐条校验 body。

**覆盖面（2026-10-08 之后实测；**P145 更新**）**：GEN NX 的 **29** 个可探候选 → **29 / 29 `PASSED`**
（P144 为 18 / 18、P143 为 11 / 11、P139 为 10 / 10、P138c 为 1 / 10）；CIVIL NX **25 / 25 `PASSED`**
（云端 `201`，**不**增加分子 —— 覆盖率按 **registry key** 去重）；`live.write_path_coverage()` = **`29 / 609`**（分母**不挪**）。
⚠️ **候选判据（P144 / `docs/07` §16.1 **R100**）**：`candidate_keys()` = 「有写方法 ∧ 有读路径 ∧
（**Transformer 已注册 ∨ 有数据侧模板**）∧ **有 `DELETE`** ∧ 非危险形态 ∧ 产品可得」——
分母里 **524** 个 GEN NX 写端点**既无** Transformer **又无**模板 ⇒ **不**入候选；
**有模板即可入候选**（模板是**数据**、不进 Core），包装键无 Transformer 时取数据侧 `wrapper.write`。
⚠️ 同一覆盖率**另报**一个**子桶**口径：`model_write_ratio` = **`29 / 410`** —— 分母里的
**199** 个「结果表 / 文本查询」端点（`POST.` 命名空间）在 L5 三步链下**结构上不适用**
（没有「自建 ID」可读回 / 可删），故单列；**原口径照旧报出、不过滤、不隐藏**（§8.6）。
⚠️ **目标编号可以取前置的编号（P145）**：按**构件号**取值的端点（`DB.LENG` / `DB.MBTP`）用
`target_id_source = "DB.ELEM#1"` 让目标自身的 `Assign` 键取**自建单元**的编号；而**键是名字**的端点
（`DB.HPCE`）**无法**用该机制表达 ⇒ **如实留缺**（`docs/07` §16.1 **R102**）。
**没有**模板的端点仍走 `derive_body()`，两者都取不到 → 如实记 `NO_PAYLOAD_TEMPLATE`
（**不**猜字段、**不**发请求）。

**模板**不能**改任何判定**：`verification_status` 仍只由 `availability` 机械映射
（`docs/07` §16 R78）；模板文件里**不得**出现 `availability` / `verification_status` / `products` / `verified_on`。

## 3. 统计

- 端点定义（Registry key）：**636**
- JSON Schema 文件：**625**（P141 起；P140 时 620、P138a 时 616）

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
| `tools/check_write_templates.py` | **写路径请求体模板复算**（§2.3 / §8.5）：来源 = 手册示例 + 逐条 `adjustments`；字段不超出数据侧 Schema；前置链可执行；不合规退出码 1 |
| `tools/sync_request_schemas.py` | **R5 剩余补齐**（§8.4）：从上游手册 / 开发文档**机械生成**请求 Schema 文件（`manual_json_schema` / `manual_spec_table` / `dev_doc_json_schema`）；默认预演，`--write` 写回，`--check` 断言「已落盘 == 机械结果」 |

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

**写路径的实测覆盖（P138c 收口为一条可执行口径；P139 / P142 用「模板 + 契约内 Transformer」推上去）**：
写路径端点 = `methods` 含 `POST`/`PUT`/`DELETE`/`PATCH` 的端点 = **609**（`live.write_path_keys()`），
其中**连 `GET` 都没有**的 **368** 个（`live.write_only_keys()`）才是只读探针**完全**覆盖不到的。
覆盖率 `live.write_path_coverage()`（分子 = `midas_api_verifications` 的 L5 `PASSED` **去重** key）：
**P142 在专用 dev 项目（本地 GEN NX，空项目）上真实批量实测 = `11 / 609`** —— GEN NX 的 **11** 个
可探候选**逐条** `PASSED`（请求体由 §2.3 的数据侧模板给出，前置对象由探针自建并**逆序**清理；
P139 为 `10 / 609`、P138c 为 `1 / 609`）。第 11 个 = `DB.FBLD`（P142 补齐 `LOAD_TRANSFORMERS["FLOOR_LOAD"]`
后进入候选集，见 §8.7）。旧记录 `11 / 369`（R4）与 `379`（R14）与任何可执行判定都对不上，**作废**
（跟踪项见 `docs/07` §16 R4 / R14）。⚠️ **P141 裁决⑤**：分母**不挪**（仍 **609**），但**显式**划分成
「结果表 / 文本查询」**199** 与「模型写」**410** 两个子桶，并**同时**报 `ratio`（`11 / 609`）与
`model_write_ratio`（`11 / 410`）—— 原口径**不**过滤、**不**隐藏任何未覆盖项（详见 §8.6 ②）。

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

**效果**：**625/625** 可装载（P138a 时 616）、`SchemaEngine.check_schema()` 失败 **4 → 0**、
`draft-07` 声明 **440 → 441**；`sync_manifest.py` / `sync_response_schemas.py` 预演差异仍为 **0**。
可执行判定：`python registry/tools/fix_schema_defects.py --check` +
`tests/test_midas_registry_p138.py`。

### 8.4 R5：无 Schema 端点按**实测**分类（P138b；P140 补 4 条 + P141 补 5 条）

**不**臆造：P138b **未**新增文件（当时 Schema 文件仍 **616** 个）；**P140** 补 4 个、**P141** 补 5 个
（见本节末与 §8.6），故现为 **625** 个。判据全部来自数据文件本身：

| 类 | 条数 | 端点 | 判据（可执行） |
| --- | --- | --- | --- |
| `no_request_body` | **4** | `DB.LCOM` / `OPE.PROJECTSTATUS` / `OPE.SECTPROP` / `VIEW.SELECT` | `methods` 不含 `POST`/`PUT`/`PATCH` ⇒ **没有请求体**，不需要请求 Schema |
| `absent_from_nx_manual` | **7** | `DOC.CLOSEALL` / `DOC.EXIT` / `OPE.CP{CREATE,EXPORT,UPDATEMODEL,UPDATERESULT}` / `OPE.STORYPROP` | 手册**完全没有**该 URI，也没有同名 code |
| `manual_has_no_json_schema` | **0**（P138b 时 **5**） | — | P141 已补齐（见 §8.6 ①） |
| `uri_differs_in_manual` | **0**（P138b 时 **1**） | — | P140 已补齐（`OPE.BMLD` = **Beam Detail Analysis**） |
| `post_table_key_without_manual_table_type` | **0**（P138b 时 **3**） | — | P140 已补齐（手册 `json_schema` 的 `TABLE_TYPE.enum`） |
| **合计** | **11** | — | P138b 时 **20**；P140 补 **4**、P141 补 **5**（`registry/schema/**` = **625**） |

⚠️ 与旧提示词里的分组**不同**的两处（以**实测**为准）：① `OPE.MEMB` / `OPE.STOR` / `OPE.STORPROP` /
`OPE.STORY_*_PARAM` 的手册条目**就是同一个 URI**（不是「URI 不同」）；② `OPE.STORPROP` 在手册里**有**
同 URI 条目（旧提示词把它归入「手册完全没有」）。可执行判定 =
`tests/test_midas_registry_p138.py::test_p138b_the_eleven_missing_schemas_are_classified_by_measurement`。

**P140 的 R5 补齐（4 条，**不**臆造）**：`registry/tools/sync_request_schemas.py` 把**上游资料已有**的
请求 Schema **机械生成**落盘 —— 于是 20 个无 Schema 端点 → **16** 个（`registry/schema/**` = **620**）：

| 端点 | 来源（可复算） | 新文件 |
| --- | --- | --- |
| `POST.TABLE.WEIGHT_IRREGULARITY_X` | 手册条目「Weight Irregularity Check - Analysis Story Table」的 `json_schema`（`TABLE_TYPE.enum` 含该 token） | `schema/products/gen_nx/post/TABLE/WEIGHT_IRREGULARITY_X.json` |
| `POST.TABLE.CONCURRENT_JOINT_FORCE` | 手册条目「Concurrent Joint Force Table」的 `json_schema`（`TABLE_TYPE.enum = ["CONCURRENT_JOINT_FORCE"]`） | `…/CONCURRENT_JOINT_FORCE.json` |
| `POST.TABLE.STORY_SHEAR_FORCE_COEFFICIENT` | 手册**同族条目**的**规格表**（该条目无 `json_schema`；标题同时含本表名） | `…/STORY_SHEAR_FORCE_COEFFICIENT.json` |
| `OPE.BMLD` | `MIDAS_API_开发文档_v1.0.md` 的 `/OPE/BMLD` 章节里**已给出**的完整 JSON Schema | `schema/products/civil_nx/ope/BMLD.json` |

⚠️ **更正**：P138b 把前两条判为「手册 `table_types` 为空 ⇒ 无法机械确认」，那是**只看字段、漏看
`json_schema` 本体**；`OPE.BMLD` 也**不是**「无法确认同一操作」的悬案 —— 它是 **Beam Detail Analysis**
（与 `db/BMLD` 的「梁单元荷载」不同操作）。逐条证据见 `docs/reports/P140_R5剩余补齐_v1.0.md`。

### 8.5 R5 裁决 B（无请求体 ⇒ 不建 Schema 文件）+ R5 剩余（P139；**P140 已补齐 4 条、P141 再补 5 条**）

P138b 之后，`OPE.PROJECTSTATUS` / `OPE.SECTPROP` / `VIEW.SELECT` 的**唯一**缺口是
`docs/04` §8 的 7 项 AND 里的「Response Schema 已确认」——它们连 Schema 文件都没有
（`sync_response_schemas.py` 要求**有文件**才追加 `response` 块）。**P139 显式裁决：选项 B。**

| 项 | 值 |
| --- | --- |
| 裁决 | **B**：无请求体 ⇒ **不**建 Schema 文件（`registry/schema/**` 的**请求体** Schema 与 `manifest.json` 带 `schema` 的端点仍 **1:1**） |
| 依据 ① | 这 3 个端点**确实没有请求体**（`methods` 不含 `POST` / `PUT` / `PATCH`）→ 请求方向 Schema 是**类别错误**（P138b 已把该项判为「不适用」） |
| 依据 ② | `registry/schema/**` 的定义是**请求体 Schema**；允许「无请求体也建文件」会改变 §2.1 那条 **1:1 不变量**的**含义**（625 → 628、加载器 / 导入器 / P08 / P09 断言都要跟着改） |
| 依据 ③ | 收益有限：`verification_status` 由 `availability` 机械映射（`docs/07` §16 R78），与 7 项 AND **不是**同一件事 → 本裁决**不影响**任何 `verification_status` |
| 后果（如实） | 这 3 个端点如实保持 7 项 AND 的 `PARTIAL`（`missing = ["response_schema_confirmed"]`） |
| 恢复条件 | 若将来**显式**允许「无请求体端点的 response-only Schema 文件」：需同步 §2.1 / §3 与 P08 / P09 的「文件数 ↔ manifest 1:1」断言（**625 → 628**），届时同一判定点即由假转真 |
| 可执行判定 | `tests/test_midas_write_templates_p139.py::test_p139_r5_decision_b_no_response_only_schema_file` |

`DB.LCOM` **不**在这 3 个里：它同样没有请求体，但**连实测解包链都没有**（`read_root` 为空）
→ 连 `response` 块都无从生成。

**R5 剩余（**逐条**有数据侧依据，**不**臆造）**：

| 类 | 端点 | 缺口（可复算的判据） | 恢复条件 |
| --- | --- | --- | --- |
| `post_table_key_without_manual_table_type` | `POST.TABLE.{WEIGHT_IRREGULARITY_X, CONCURRENT_JOINT_FORCE}` | 手册近名条目**有** `json_schema` 但 `table_types` **为空** ⇒ 没有**机械**链接 | 手册侧补 `table_types` |
| 同上 | `POST.TABLE.STORY_SHEAR_FORCE_COEFFICIENT` | 手册近名条目声明的是**别的** token（`["STORY_SHEAR_FOR_RS"]`）且**没有** `json_schema` | 同上 |
| `uri_differs_in_manual` | `OPE.BMLD` | 手册**只有** `db/BMLD`；**本批只读实测**：`GET /OPE/BMLD` → **`405`**（只允许 `POST`）、`GET /DB/BMLD` → **`200`** ⇒ 两条路由**方法集不同**，不能视为同一操作 | 官方确认二者语义关系 |

> ⚠️ **上表是 P139 时期的记录**（证据不删）：其中 3 条已由 **P140** 机械补齐
> （`POST.TABLE.{WEIGHT_IRREGULARITY_X, CONCURRENT_JOINT_FORCE, STORY_SHEAR_FORCE_COEFFICIENT}` 取手册
> `json_schema` 的 `TABLE_TYPE.enum` / 同族规格表；`OPE.BMLD` 取自开发文档里**已给出**的完整 JSON Schema）。
> 另 5 条 `manual_has_no_json_schema` 由 **P141** 补齐。最新结论见 **§8.4 / §8.6**。

⚠️ 只读实测**不**在 CI 里复跑（需真实实例）；CI 侧固定的是**数据侧**事实
（`test_p139_r5_remaining_gaps_are_backed_by_data_side_facts`）。

### 8.6 P141：R5 剩余 5 条 + 写路径分母的**子桶裁决** + R96 前置链

**① R5：`manual_has_no_json_schema` 5 条机械补齐（20 → 11）**

这 5 条的手册条目与端点**同一 `input_uri`**，只是条目**没有** `json_schema`（只有规格表）——
`registry/tools/sync_request_schemas.py` 新增**定位串**（`uri:<input_uri>`，工具会**断言**
该 URI 就是端点的数据侧 URI；或 `title:<片段>`），按规格表机械生成请求 Schema：

| 端点 | 定位串 | 新文件 |
| --- | --- | --- |
| `OPE.MEMB` | `uri:ope/MEMB` | `schema/products/gen_nx/ope/MEMB.json` |
| `OPE.STOR` | `uri:ope/STOR` | `…/ope/STOR.json` |
| `OPE.STORPROP` | `uri:ope/STORPROP` | `…/ope/STORPROP.json` |
| `OPE.STORY_IRR_PARAM` | `uri:ope/STORY_IRR_PARAM` | `…/ope/STORY_IRR_PARAM.json` |
| `OPE.STORY_PARAM` | `uri:ope/STORY_PARAM` | `…/ope/STORY_PARAM.json` |

**规格表逐字段忠实**：生成 Schema 的字段名集合 == 规格表里带引号的字段行集合（**不**多、**不**少）。
**连带效果（同批、非人工）**：`OPE.STORY_IRR_PARAM` / `OPE.STORY_PARAM` 落盘请求 Schema 后
**立刻**满足 `sync_response_schemas.py` 的全部条件 → 同批追加 `response` 块（响应方向 **239 → 241**）。
为此 `sync_request_schemas.py` 新增 `with_preserved_response()`：两个工具写**同一批文件**，
装配时**原样透传** `response` 块（否则会互相抹掉）。
可执行判定 = `tests/test_midas_request_schemas_p141.py`。

**② 写路径分母（裁决⑤）：分母**不挪**，但显式划分两个子桶**

`write_path_keys()` 仍是 R4 / R14 的**正式**分母（**609**）；同一分母**另报**一个子桶口径：

| 子桶 | 条数 | 判据 | L5 三步链 |
| --- | --- | --- | --- |
| 结果表 / 文本查询 | **199** | `namespace == "POST"`（`/POST/TABLE` · `/POST/TEXT` · `/POST/PM` · `/POST/STEELCODECHECK`） | **结构上不适用**（请求体用 `TABLE_TYPE` **取表**，不创建 / 不修改 / 不删除任何模型对象 ⇒ 没有「自建 ID」可读回 / 可删） |
| 模型写 | **410** | 其余写路径端点 | 适用 |

`WriteCoverage` 同时给出 `ratio`（`<分子> / 609`）与 `model_write_ratio`（`<分子> / 410`）。
⚠️ **原口径不设限、不过滤、不隐藏**：若某个结果表端点真有 L5 `PASSED` 行，它**照样**计入原分子
（`test_p141_the_sub_bucket_never_hides_an_uncovered_endpoint`）。
**恢复条件**：若将来要改用子桶作为 R4 / R14 的**正式**分母，必须是一次**显式裁决**（写明判据与影响面）。

**③ `CONCURRENT_JOINT_FORCE` 的判别结论（更正 P140 的措辞）**

P141 在**有分析结果**的最小梁模型上逐条复算（只碰自建 ID）：

| token | 状态 | `error creating utbl` 标记 | 结论 |
| --- | --- | --- | --- |
| 伪 token（对照） | `400` | **有** | 未识别 |
| `WEIGHT_IRREGULARITY_X` · `STORY_SHEAR_FORCE_COEFFICIENT` | `200` | 无 | **接受** |
| `PLANESTRAINFL` · `PLANESTRESSFL` · `PLANESTRAINSG` | `200` | 无 | **接受**（本模型无该结果也照样出表）|
| `CONCURRENT_JOINT_FORCE`（**完整**必填体） | `400` | **有** | 与伪 token **同形** → 本 build **不接受** |

⚠️ P140 记的是「需移动荷载 / 后处理模式的模型」；同一模型上 `PLANESTRAINFL`（同样缺所需结果）
照样 `200` ⇒ 差异**不在**「模型缺某类结果」，而在**该表类型的建表规格本身**。残余假设（未排除）：
该表要求某个分析模式开关（`PostMode`）在模型里打开。无论哪一种，**它没有取得 `200`** ⇒
R5 账上仍记「未正向验证」（`verification_status` 保持 `PARTIAL`），**不**记为已判别为接受；
手册来源的 Schema **保留**（它记录的是**上游规格**，与「本 build 是否实现」是两件事）。

**④ R96：非空项目上的前置链（本批实现）**

原状：模板的前置编号从 `1` 起（`DB.NODE#1` …），而空项目闸门**按设计**只允许空项目。
现在编号**一律重新分配**：

| 机制 | 声明 | 语义 |
| --- | --- | --- |
| 前置编号 | （缺省） | 该端点既有编号的 `max + 1`（同一端点的多个前置依次 `+1`） |
| 编号写回 | `prerequisites[].references` | `[{in, path}]`：该前置编号出现在**哪个 body 的哪个路径**（`in` = `owner` 或另一个前置的标签） |
| 目标自身编号 | `self_references` | 目标编号在自身 body 里的路径 |
| **反向依赖** | `target_id_source` | **目标自身**编号取某个前置分配到的编号（`DB.CONS` / `DB.CNLD` 的 `Assign` 键就是它那个节点号） |

**闸门语义**：**默认**仍要求专用项目为空（`STRUCTAI-3000 dedicated_test_project_not_empty`，
零写请求）；`allow_non_empty=True` 时改为**更强**的判据 —— 写前记下被触碰端点的既有编号集合，
清理后逐端点核对**一字未变**，变了即如实 `FAILED`（`detail = existing_id_set_changed`）。
**真实实测（门控）**：在**预置**了 `MATL#1` / `SECT#1` / `NODE#1-2` 的专用项目上跑
`DB.ELEM` + `DB.CONS` → **2 / 2 `PASSED`**，前置分别取 `DB.MATL#2` / `DB.SECT#2` /
`DB.NODE#3` / `DB.NODE#4`，预置编号**一字未变**；空项目上的覆盖**未回退**（P141 为 **10 / 10**，
P142 为 **11 / 11**，见 §8.7）。
可执行判定 = `tests/test_midas_request_schemas_p141.py`（离线 4 项 + 门控 2 项）。

### 8.7 P142：候选集**上限**裁决 + 契约内缺口 `FLOOR_LOAD` / `DB.FBLD`

**① 分子**不可能**靠「加模板」增长（实测更正 `docs/07` §16.1 **R97**）**：
`candidate_keys()` = 「有写方法 ∧ 有读路径（`GET` + `read_root`）∧ Transformer **已注册** ∧
非危险形态 ∧ 产品可得」；`transformer_name_for()` 机械派生 `midas.<code>.v1`。
GEN NX 的候选集 = **11**，被「Transformer 未注册」挡住的写端点 = **542**
（CIVIL NX **471** / Civil Designer **32**）⇒ **加模板对它们零效果**；
契约内（`operations.py` 的 69 个 Operation）声明的写步骤里，凡三步链**适用**的端点
**全部**已在候选集内。

**② `FLOOR_LOAD` 缺口已收口（`docs/07` §16.1 **R98**）**：
`operations.LOAD_STEP_BY_TYPE["FLOOR_LOAD"] = "DB.FBLD"` **早已声明**
（`docs/07` §6.3 的 `MODEL.LOAD.ASSIGN` 端点表），但 `LOAD_TRANSFORMERS` 缺该键
⇒ 楼面荷载一律 `load_type_not_mapped`。P142 补 `FloorLoadTransformer`（`midas.fbld.v1`，
字段名逐条来自 `registry/schema/common/db/FBLD.json`）+ `TRANSFORMER_REGISTRY` 注册；
数据侧新增 `DB.FBLD` 模板（body **原样**照抄手册示例 `Define Floor Load Type`，零 `adjustments`；
前置 = 两条 `DB.STLD`：`DC` / `DW`，即示例 `ITEM[].LCNAME` 引用的工况名）。

**③ 效果**：模板 **9 → 10**、复算 body **31 → 34**（`references` 仍 **14** /
`self_references` 仍 **4**）；真实 L5 **11 / 11 `PASSED`**（含 `DB.FBLD` → `/DB/FBLD` **200**，
前置 `DB.STLD#1` / `#2`）；覆盖率 **`10 / 609` → `11 / 609`**
（`model_write_ratio` **`10 / 410` → `11 / 410`**）；跑后哨兵**全空**、**零残留**。
可执行判定 = `tests/test_midas_write_coverage_p142.py`（8 项）+
`python registry/tools/check_write_templates.py`（模板 10 / body 34 / 0 错）。

**④ P143 更正与补充（2026-10-08 之后）**：

- **`CIVIL_DESIGNER` 的候选集 = 0（更正 §8.7 ① 的「Civil Designer = 2」）**：数据侧对 CD 的
  `DB.NODE` / `DB.ELEM` 在 `product_overrides.CIVIL_DESIGNER.methods` 里**只声明 `GET`**
  （`registry/common/db/NODE.yaml` / `ELEM.yaml`）⇒ 它们在该产品上**没有写方法**，不可能是候选。
  P142 记的 **2** 是 `candidate_keys()` 只看**基础** `methods` 造成的**伪数**（见 `docs/07` §16.1 **R99**）。
  修复后三产品候选集 = **GEN NX 11 · CIVIL NX 11 · Civil Designer 0**。
- **`CIVIL_NX` 真实 L5 已在专用空白项目上跑通 = 11 / 11 `PASSED`**（状态码 **201**，GEN NX 为 `200`；
  跑前 / 跑后哨兵**全空**）。⚠️ **不**增加分子：覆盖率按 **registry key** 去重，CIVIL NX 与 GEN NX
  是**同一批 key** ⇒ 仍 **`11 / 609`**（跨产品证据是**另一条**判据，见 `docs/07` §16.1 的 P143 回填）。
- 可执行判定 = `tests/test_midas_write_coverage_p143.py`（5 项）· `docs/reports/P143_…md`。

**⑤ P144 更新（R100 / R101）**：候选判据放宽为「**Transformer 已注册 ∨ 有数据侧模板**」+ 新增
「**能建必须能删**」（没有 `DELETE` 的端点不入候选）；包装键无 Transformer 时取数据侧 `wrapper.write`。
本批新增 **7** 条模板（`DB.CCFC` / `DB.CUTL` / `DB.DCON` / `DB.DSTL`（1 处声明式调整）/
`DB.EIGV` / `DB.ETFC` / `DB.GSTP`）⇒ 模板 **10 → 17**、复算 body **34 → 41**；
真实 L5 **18 / 18 `PASSED`**（GEN NX 空项目）⇒ 覆盖率 **`11 / 609` → `18 / 609`**
（`model_write_ratio` **`11 / 410` → `18 / 410`**）。**3 个端点如实留缺（R101）**：
`DB.ACTL` / `DB.CLWP`（手册示例与本 build 自省字段集不一致 ⇒ `400 Wrong Field`）·
`DB.EDMP`（按构件号取值 ⇒ 非零前置）—— 均**不**入候选。可执行判定 =
`tests/test_midas_write_coverage_p144.py`（6 项）· `docs/reports/P144_…md`。

**⑥ P145 更新（第二批 12 个端点；新增 `docs/07` §16.1 R102）**：**11** 条模板跑通、**1** 条如实留缺。

- **11 个跑通**（全部**只有数据侧模板**、没有 Transformer）：`DB.DCTL` / `DB.EPMT` / `DB.FIMP` /
  `DB.HSFC` / `DB.IEHC` / `DB.LENG` / `DB.MBTP` / `DB.MLFC` / `DB.MVCD` / `DB.MVHLTR` / `DB.PDEL`
  ⇒ 模板 **17 → 28**、复算 body **41 → 64**（`references` **14 → 22** / `self_references` 仍 **4**）；
  真实 L5 **29 / 29 `PASSED`**（GEN NX 空项目）⇒ 覆盖率 **`18 / 609` → `29 / 609`**
  （`model_write_ratio` **`18 / 410` → `29 / 410`**）；候选集 GEN NX **18 → 29** · CIVIL NX **17 → 25** ·
  Civil Designer 仍 **0**（blocked **535 → 524** / **465 → 457** / **32 → 31**）；跑前 / 跑后哨兵**全空**。
- **按构件号取值的端点用 `target_id_source` 救回**：`DB.LENG` / `DB.MBTP` 的 `Assign` 键是**构件号**
  （空项目没有构件 ⇒ 手册形态 `400 Not Found Key`）⇒ 前置链 = `DB.MATL#1` + `DB.SECT#1` +
  `DB.NODE#1/#2` + `DB.ELEM#1`，并令**目标自身**的 `Assign` 键取该单元的编号
  （`target_id_source = "DB.ELEM#1"`，即 §2.3 的 R96 反向依赖）；目标 `body` **原样**照抄手册示例。
- **手册示例缺必填字段 ⇒ 换条目（仍是 `manual_example`）**：`DB.MVHLTR` 的**条目 1** 缺
  `ML` / `MW` / `LEFT_LANES`（规格表 `Required`）⇒ `400 Wrong Field`；**条目 2** 自带这三个字段 ⇒
  只把 `source.example_id` 由 `"1"` 改 `"2"`，**无** adjustments。
- **`DB.HPCE` 如实留缺（R102）**：`Assign` **数字键** → `400 Wrong Key`（键 `1` / `2`、带 / 不带
  `START_TIME` / `END_TIME`、空 `ITEMS` 六种形态均同）；`Assign` **名字键** → `200` 但**静默不落库**
  （`ITEMS` 指向**已建**节点也一样）；顶层 `HPCE` / `Argument` → `400 Wrong Field`
  ⇒ 其 `Assign` 键**不是**编号，而 `target_id_source` / `self_references` **只**写回**整数**编号、
  `adjustments` **只**能改值 ⇒ 数据侧**无法**表达；模板**不写**、不入候选，且**不**动数据侧
  （端点仍 `enabled` / `verified` / 写方法齐全）。`DB.HPCE` 是否该加**写侧产品覆盖**留待**显式裁决**。
- **跨产品**：CIVIL NX **25 / 25 `PASSED`**（云端 `201`）—— 分子按 **registry key** 去重 ⇒ **不**增加分子。
- 可执行判定 = `tests/test_midas_write_coverage_p145.py`（7 项）· `docs/reports/P145_…md`。
