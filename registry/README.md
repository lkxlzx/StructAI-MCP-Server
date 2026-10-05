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
（如 `ACTL` / `Argument` / `TABLE`；**377** 个）与直接就是 JSON Schema（**237** 个）；另有 **1** 个
（`DB.MBTP`）把 JSON 存成了**非法字符串**（见下）。

| 项 | 实测值 | 说明 |
| --- | --- | --- |
| 文件数 | **616** | 与 `manifest.json` 中带 `schema` 的端点 **1:1**（无孤儿、无缺文件） |
| 可装载 | **615** | 剥离包装根键后原样登记（**不改写任何取值**） |
| 无法装载 | **1** | `products/gen_nx/db/MBTP.json`：`schema` 是字符串且**不是合法 JSON**（缺 1 个 `}`） |
| `$schema` 声明 | **440** `draft-07` / **175** 未声明 | 按**生效 Schema**（剥离包装根键后）统计 |
| 不是合法 JSON Schema | **4** | `DESIGN.SRC.AIK-SRC2K.MATD` / `.MCRD` / `.MRBD`、`OPE.EDMP`（占位字符串 / 非法子 schema） |

**方言裁决（`docs/07` §16 R18）**：**按各 Schema 自身声明的方言校验**（draft-07 → `Draft7Validator`；
未声明 / 未知 → 项目标准 **Draft 2020-12**，`docs/02` §12 / §13 / §22）。
依据：本目录是外部软件 API 的**唯一权威来源**，Schema 原样登记；用 2020-12 解释 draft-07 文档会**静默改变语义**
（`exclusiveMinimum` 布尔 vs 数值、`definitions` / `items` / `prefixItems`），实测 draft-07 的数组形式 `items`
喂给 2020-12 校验器时直接抛异常。Core 自有的 `schemas/`（`docs/02` §22）仍一律用 Draft 2020-12。

⚠️ **本目录的 5 个数据缺陷**（`docs/07` §16 R19，待数据侧生成链修复）：上表「无法装载 1 个」+「不是合法
JSON Schema 4 个」。注意 `jsonschema` 在实例校验时**不**检查 Schema 自身，非法关键字会被**静默忽略**
（校验变宽松），故 Core 侧由 `SchemaEngine.check_schema()` 显式诊断。
另：**20** 个端点仍**没有** JSON Schema（`docs/07` §16 R5），本目录不臆造。

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

```powershell
python registry/tools/extract_design_codes.py
python registry/tools/sync_manifest.py           # 预演（只打印差异）
python registry/tools/sync_manifest.py --write   # 写回
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
**其余 628 个端点的 `read_root` 尚未实测校验**（跟踪项见 `docs/07` R14）。

> 附带修正：`DESIGN.SRC.AIK-SRC2K.DCO` 原 `methods: [PUT]` 漏标 GET（实测 200），
> 已改为 `[GET, PUT]` 并标 `verified`；`DESIGN.SRC.AIK-SRC2K.OCHECK` 实测 404，已标 `unavailable_on: [gen-local]`。
