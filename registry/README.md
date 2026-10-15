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
「上游手册（**两个来源**：`MIDAS_API_Online_Manual_数据_v1.0.json` + P149-B 起
`MIDAS_API_Online_Manual_Gen_NX_v1.0.json`）的 `endpoints[].examples[].json` 某个编号下的条目」
再施加本文件声明的 `adjustments`；此外 body 的字段名**不得**超出该端点的数据侧请求 Schema，
前置链的 key 必须已登记 / 已启用 / 含 `POST`；**编号声明**（P141 起）逐条可判 ——
`references[].path` / `self_references[]` 必须**存在**且当前取值**恰好**等于声明的编号，
`target_id_source` 必须指向本模板里的一个前置且**不**构成循环依赖。
`tests/test_midas_write_templates_p139.py` 另用 `jsonschema`（按各 Schema 声明的方言）逐条校验 body。

**覆盖面（P149-C 起）**：GEN NX 的 **72** 个可探候选 → **72 / 72 `PASSED`**（P149-C **+2**：
`DESIGN.RC.KDS-41-20-2022.WMAK` / `DESIGN.SRC.AIK-SRC2K.DSRC` —— 由**只读** L4 收口
`availability` 后解锁，见 §8.12（⑬）；P149-B2 两轮 **+12**：`DB.BNGR` / `DB.GRUP` / `DB.NPLN` /
`DB.PSLT` / `DB.VSEC` / `DB.WMAK` / `DESIGN.RC.DRC` / `DESIGN.RC.KDS-41-20-2022.DCO` /
`DESIGN.RC.KDS-41-20-2022.DCTL` / `DESIGN.SRC.AIK-SRC2K.DCO` / `DESIGN.STEEL.DSTL` /
`DESIGN.STEEL.KDS-41-30-2022.DCO`；P148 为 58 / 58、P147 为 46 / 46、P146 为 36 / 36、
P145 为 29 / 29、P144 为 18 / 18、P143 为 11 / 11、P139 为 10 / 10、P138c 为 1 / 10）；
CIVIL NX **62** 个候选（P149-A 为 49；P147 实测 39 / 39、P145 实测 25 / 25、P143 实测 11 / 11，
云端 `201`，**不**增加分子 —— 覆盖率按 **registry key** 去重）；
`live.write_path_coverage()` = **`72 / 633`**。
⚠️ **R106（P149-D）另立判据，不改本口径**：`POST.*` 的 **197** 个端点**没有** `GET` / `read_root`
⇒ 三步链**结构上不适用**；它们的结论由**取报表判据**给出（`registry/README.md` §8.13 / §8.12 ⑭）：
`PASSED` **15**（`availability: verified` + `response` 块）· `PARTIAL` **172** · `FAILED` **8** ·
留缺 **2**。⚠️ 这 **15** 个**不**计入 `write_path_coverage()` 的分子（**三步链的分子**仍只认
`contract_level = L5` ∧ `status = PASSED` 的 `midas_api_verifications` 行）；**两个口径同时报出**。
⚠️ **分母基线（P149-A 重算，`docs/07` §16.1 **R108**）**：`write_path_keys()` = **633**
（P148 为 **609**）—— 用**只读** `OPTIONS` 的 `Allow` 头实测端点方法集后，发现 registry 曾**系统性少声明**
**90** 个端点的方法集（+`DELETE` 88 · +`PUT` 80 · +`GET` 62 · +`POST` 6），其中 **24** 个因此才**进入**分母
（20 个 `DESIGN.*` 由「只有 `GET`」变为「`GET,PUT,DELETE`」、`DB.SWIND` 由「无方法」变为四方法齐全、
`OPE.SECTPROP` 由 `GET` 变为 `POST,GET`）；子桶随之 **`write_only` 368 → 306** ·
**`result_query` 199（不变）** · **`model_write` 410 → 434**。证据 = `registry/live/live_methods.json`；
复算工具 = `registry/tools/sync_endpoint_methods.py`（`--probe` / `--write` / `--check`）。
⚠️ **候选判据（P144 / `docs/07` §16.1 **R100**）**：`candidate_keys()` = 「有写方法 ∧ 有读路径 ∧
（**Transformer 已注册 ∨ 有数据侧模板**）∧ **有 `DELETE`** ∧ 非危险形态 ∧ 产品可得」——
分母里 **501** 个 GEN NX 写端点**既无** Transformer **又无**模板 ⇒ **不**入候选；
**有模板即可入候选**（模板是**数据**、不进 Core），包装键无 Transformer 时取数据侧 `wrapper.write`。
⚠️ 同一覆盖率**另报**一个**子桶**口径：`model_write_ratio` = **`72 / 434`** —— 分母里的
**199** 个「结果表 / 文本查询」端点（`POST.` 命名空间）在 L5 三步链下**结构上不适用**
（没有「自建 ID」可读回 / 可删），故单列；**原口径照旧报出、不过滤、不隐藏**（§8.6）。
（没有「自建 ID」可读回 / 可删），故单列；**原口径照旧报出、不过滤、不隐藏**（§8.6）。
⚠️ **R105（P148）**：`DB.IMFM` 的手册**两个**条目（`STEEL_NAME` / `CONC_NAME`+`REBAR_NAME`）都被本 build
**拒绝**（`POST` → `400 software_api_error`，与 R103 / R104 同形）⇒ 模板**不写**、**不**入候选；
成因**不是**数据缺陷（字段全在请求 Schema 里声明，且落盘前的只读自省 `unknown` = 0）。
⚠️ **目标编号可以取前置的编号（P145）**：按**构件号**取值的端点（`DB.LENG` / `DB.MBTP`）用
`target_id_source = "DB.ELEM#1"` 让目标自身的 `Assign` 键取**自建单元**的编号；而**键是名字**的端点
（`DB.HPCE`）**无法**用该机制表达 ⇒ **如实留缺**（`docs/07` §16.1 **R102**）。
⚠️ **R103（P146）**：手册示例被本 build **拒绝**（`DB.SKEW`：3 个变体全 `400 software_api_error`）
或**建了读不回**（`DB.HSPT` / `DB.MADO`：`POST 200` 但 `GET` 为空）的端点 ⇒ 模板**不写**、**不**入候选
（与 R101 的 `DB.EDMP` 同形）；成因**不是**数据缺陷（字段全在请求 Schema 里声明）。
**没有**模板的端点仍走 `derive_body()`，两者都取不到 → 如实记 `NO_PAYLOAD_TEMPLATE`
（**不**猜字段、**不**发请求）。

⚠️ **模板由工具拥有（P149-B2）**：模板不再逐批手工落盘，而由 `registry/tools/sync_write_templates.py`
机械生成 / 维护（`--write` / `--check`；`--check` 断言盘面 == 机械结果，**逐字节**）。池子判据 =
`enabled` ∧ 非 `destructive` ∧ 有写方法 ∧ 非 `delete_all_via_body` ∧ 本 build 路由存在 ∧
有 `GET` + `read_root` + `DELETE` ∧ **无 Transformer** ∧ **无模板** ∧ 不在留缺账本里；
示例按「**旧来源 → 新来源**」取**第一个**可用条目（包装键恰好 1 个 + 内层是对象 + 条目**非空**）。
**留缺账本** = `registry/live/write_template_left_out.json`：账本里的 key **必须**没有模板
（工具每次**主动剔除**），原因逐条可复算（R101–R105 / R109–R113）；
本批实测证据 = `registry/live/write_batch_p149b2.json`（第一轮 **179** 条 + 第二轮 **67** 条补测）。
⚠️ **本批两次触发实例崩溃**（`DB.NSPR` ⇒ **R113**，**永不再试**）：两轮**跑后**哨兵读数均**无效**
（**不**声称零残留）；第二轮**跑前**只读残留核对（**122** 个端点）**全空** ⇒ 第一轮无残留；
**收尾**（实例第二次恢复后）只读残留核对 **122** 个端点**全空、0 不可读** ⇒ **零残留**（见证据文件 `residue_final`）。
详见 §8.11 与 `docs/reports/P149-B2_写路径模板机械化与批量实测中断_v1.0.md`。

**模板**不能**改任何判定**：`verification_status` 仍只由 `availability` 机械映射
（`docs/07` §16 R78）；模板文件里**不得**出现 `availability` / `verification_status` / `products` / `verified_on`。
### 2.4 请求方向 Schema 的**覆盖不全**收口（R117 / P150）

`registry/schema/**` 的**请求方向** Schema 是**手册子集**的转录；端点定义里**已登记**一个**只读**的
机械来源 `schema_ref.introspect`（`GET /info/db/<CODE>`，§4）。P150 对**全部 244** 个有该来源的端点
做了一次**只读**扫描（**13** 块 × 20 + 块间只读健康检查 `GET /DB/NODE`；**只发 `GET`**），
逐端点做**递归**字段集差集：

| 结果 | 条数 |
| --- | --- |
| 可比（`200` ∧ 有条目节点 ∧ 有数据侧 Schema） | **199** |
| 本 build **无**该自省路由（`404`） | **45**（**23** `unverified`（R85）· **15** `unavailable_on` 含 `gen-local` · **7** CIVIL_DESIGNER 独有） |
| 自省独有字段（缺口）的端点 | **24** |
| **反向缺口**（数据侧有、自省没有）的端点 | **12**（**一律未动**，只如实记录） |

**裁决 R117 = 补 Schema（21 个端点 / 212 个字段）**，判据逐条可复算：端点 `products` 含探针实例的
产品 ∧ 待补节点**整棵子树**是合法 JSON Schema 片段 ∧ 父节点未声明 `additionalProperties: false`；
**只**补自省**实际声明**的字段、**只新增名字**（不删 / 不改名 / 不覆盖既有声明）。
**如实留缺 3 个**：`DB.KFAC`（`product_not_probed`）· `DB.SSEIS` / `DB.SWIND`
（`strict_schema_conflict` + `invalid_introspect_node`）。
⚠️ 判定口径**未变**：白名单**内容**按本 build 的声明据实扩大，同时 **3** 个原本「裸 `object` ⇒
**不判**」的父节点变成**可判**（判定在该处**变强**）；`check_write_templates` 仍
**71 / 71 非空判 · 0 未知字段 · 0 不可判 body**。
证据 = `registry/live/introspect_field_diff.json`（含自省**原文** ⇒ `--write` / `--check` 可**离线**复算）；
复算工具 = `registry/tools/sync_introspect_fields.py`（`--probe` **只发 `GET`** / `--write` / `--check`）。

⚠️ **R122 / R125（P151 只读实测）**：`DB.KFAC` 需 **CIVIL_DESIGNER** 自省来源，而 `designer-cloud`
**当前不可用** —— `GET /` · `/DB/NODE` · `/info/db/KFAC` · `/info/db/NODE` · `/KFAC` **全部**
`404 {"error":{"message":"client does not exist"}}`（**会话 / 客户端级**失败，**不是**端点级 `404`）
⇒ `--probe` **未**在该实例上跑（证据的 `instance` 是 `gen-local`，混跑会**污染**证据）；
`DB.KFAC` 的留缺条件**不变**（`DB.SSEIS` / `DB.SWIND` 仍需 **MIDAS 侧**澄清布局）。

### 2.5 写路径「编辑（PUT）」判据（R118 / P150；**P151 续跑前置链** + **R120 别名清理**）

L5 三步链只覆盖「创建 → 读回 → 按路径 key 删除」，**PUT（编辑）没有判据**。P150 补上：

    只读哨兵（全空）→ 创建（该端点的**写入方法**；**只**碰自建编号）→ 读回 →
    **PUT 一个改动过的值**（逐条记 `{path, from, to, why}`）→ 读回确认**改动生效** →
    按路径 key 删除 → 读回确认消失 → **无副作用观察**（删除后再发一次同一 PUT，看是否**重新出现**）

* 改动值**机械**选定：按 body 声明顺序深度优先，取**第一个** `boolean`（翻面）或**第一个**无
  `enum` / `const` 的 `number` / `integer`（`+1`）⇒ `--check` 可**离线**复算。
* 目标集 **71**（有数据侧模板 ∧ GEN NX 有 `PUT` / `DELETE` / `GET` / `read_root` ∧ 已启用 ∧ 非破坏性）；
  **P150** 实测**零前置链的 56** 个（**37** `PASSED` · **14** `LEFT_OUT` · **5** `FAILED`）；
  **P151 续跑**带前置链的 **15** 个（**5** `PASSED` · **9** `LEFT_OUT` · **1** `FAILED` = **R124**）
  ⇒ 子桶合计 **71** 行 = **42** `PASSED` + **23** `LEFT_OUT` + **6** `FAILED`，**留缺为空**。
* **前置链（P151）沿用 L5 的机制**：声明（`prerequisites` / `references` / `self_references` /
  `target_id_source` / `id_source`）由 `app/.../write_templates.py` **唯一**解析；编号**一律重新分配**
  （该端点既有编号的 `max + 1`；`id_source = "target"` 的前置取**目标**编号；目标可用
  `target_id_source` **反向**取某个前置的编号），**按声明顺序创建**、目标清理后**逆序**删除，
  **只**碰自建编号；`plan_chain()` 与 L5 的 `_plan()` 的**等价性**由测试逐条断言（空 + 非空快照）。
* **两个侦察答案**：PUT 的 body 形状 = **与创建同一形状**（`assign_keyed_item`）；
  **PUT 不要求记录已存在**（upsert，**42 / 42** 实测）⇒ 与 **R116** 互相印证。
* ⚠️ **残留如实披露（不声称零残留）**：本 build 的 `DELETE` 会**返回 `200` 并回显被删记录却不真正
  删除** ⇒ 判据以「**再读确认不在**」为准；哨兵 = **全部目标 ∪ 全部前置端点**（**72** 个，P151 起）；
  `/DESIGN/SRC/AIK-SRC2K/DSRC` **无** `DB.*` 别名、**无法清除**（`residue` + `allowed_residue` 披露）。
* **R120：别名路由的清理路径（P151 工具化）**：`DESIGN.*` 别名路由的 `DELETE` **不生效** ⇒ 清理走
  **同表 `DB.*` 路由**；映射**必须来自实测**（`--probe-aliases`：自建编号经别名路由创建 ⇒ 出现在同表
  `DB.*` 路由的读回块里 ⇒ `DB.*` 路由 `DELETE` 后**两个**路由再读均不在）。实测 **3** 对
  （`/DESIGN/RC/DRC` ↔ `/DB/DCON` · `/DESIGN/RC/KDS-41-20-2022/DCTL` ↔ `/DB/DCTL` ·
  `/DESIGN/STEEL/DSTL` ↔ `/DB/DSTL`）全部 `same_table_observed = true` ·
  `alias_delete_effective = false` · `db_delete_effective = true` · `delete_confirmed = true`。
  逐行 `delete_state` **区分**「删除已确认」（`delete_confirmed`）/「别名清理已确认」
  （`delete_confirmed_via_alias`）/「删除未确认」（`delete_unconfirmed` ⇒ **必须在 `residue` 里披露**）。
* **分桶**：与 R107 的取设置表判据**分开**，**不**并入 L5 三步链的覆盖率分子
  （`write_path_coverage()` **不变**）。证据 = `registry/live/put_edit_probe.json`；
  复算工具 = `registry/tools/probe_put_edits.py`（`--probe` 有界侦察（**分块 ≤ 10** + 块间只读健康检查）/
  `--probe-aliases` **R120 实测 + 收尾清理** / `--check` / `--summary`；`--allow-residue` **只**放行
  **已披露**的残留 key，其余跑前非空一律**中止**）。
* **接口层（P152 起，见 §8.12 ⑱）**：以上判据**全部**绕开 `app/`（模板 / 前置链 / 编号分配都在
  探针里实现）。**接口层**判据走**既有 9 个 MCP Tool 契约** ——
  `MCP Tool → OperationPlan（operations.py）→ Adapter（intent 分派）→ MidasHttpClient → 实例`，
  证据 = `registry/live/interface_path_probe.json`（**13** 条 = **4** `PASSED` + **9** `FAILED`，
  三条路径各有 `PASSED`，**零残留**）；复算工具 = `registry/tools/probe_interface_paths.py`。
  ⚠️ 该桶**独立**，**不**并入本节的 71 行子桶，也**不**并入任何覆盖率分子。
* **接口层读路径（P153，见 §8.12 ⑲）**：**同一链路**但**零写请求**（只发 `GET` 与取报表
  `POST /POST/TABLE`）—— **15** 条读类 Operation = **2** `PASSED` + **7** `PARTIAL` +
  **6** `FAILED`；证据 = `registry/live/interface_read_probe.json`（同工具 `--probe-read`）。
  ⚠️ **PUT 判据与读路径判据是两个桶**（读得回 ≠ 写得进）；两者都**不**并入覆盖率分子。
* **接口层写路径（P154，见 §8.12 ⑳；**P157 已到 `13 / 13`**）**：**R126 裁决 A′** 落地后 **13** 条 =
  **11** `PASSED` + **2** `FAILED`（`4 / 9` → `11 / 2`）；⚠️ **P157 / D2 = A 落地**（`BoundaryTransformer`
  加第 **7** 个自由度 `rw` ⇒ `CONSTRAINT` 输出 **7** 位）后重测 ⇒ **13** 条 = **13** `PASSED` + **0** `FAILED`
  （`DB.CONS` 的添加 / 删除**都** `PASSED`）。**R129**：`POST.TABLE` 在 GEN NX 上路由**存在**
  ⇒ P157 **已按实测更正数据**（`products` 补 `GEN_NX`，见 §8.12 ㉓）。


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

**⑦ P146 更新（第三批 10 个端点；新增 `docs/07` §16.1 R103）**：**7** 条模板跑通、**3** 条如实留缺。

- **7 个跑通**（全部**只有数据侧模板**、**零前置链**）：`DB.LDGR` / `DB.PJCF` / `DB.PNLD` /
  `DB.SMCT` / `DB.SPFC` / `DB.THFC` / `DB.THIK` ⇒ 模板 **28 → 35**、复算 body **64 → 71**
  （`references` 仍 **22** / `self_references` 仍 **4**）；真实 L5 **36 / 36 `PASSED`**
  （GEN NX 空项目）⇒ 覆盖率 **`29 / 609` → `36 / 609`**（`model_write_ratio` **`29 / 410` → `36 / 410`**）；
  候选集 GEN NX **29 → 36** · CIVIL NX **25 → 32** · Civil Designer 仍 **0**
  （blocked **524 → 517** / **457 → 450** / **31**）；跑前 / 跑后哨兵（**43** 个端点）**全空**。
- **`DB.SKEW` 如实留缺（R103）**：手册的 **3** 个变体（`Angle Type` / `3 Points Type` /
  `Vector Type`）逐个 `POST` → **全部** `400 software_api_error`；`GET /DB/SKEW` 始终空
  ⇒ 本 build **拒绝**手册的**每一个**取值形态，而 `adjustments` **只**能改**值**、**不能**改结构
  ⇒ 数据侧**无法**推出可接受形态；模板**不写**、不入候选。
- **`DB.HSPT` / `DB.MADO` 如实留缺（R103）**：`POST` → **`200`**（`HSPT` 回显
  `{"HSPT": {"1": {...}}}`、`MADO` 回**空表** `{"MADO": {}}`），但紧随的 `GET` **读不回**
  （`{"HSPT": {}}` / `{"MADO": {}}`）⇒ 三步链的「读回」**不成立**（与 R101 的 `DB.EDMP` 同形）
  ⇒ 模板**不写**、不入候选；**绝不**放宽「创建 → 读回 → 按路径 key 删除」。
  三个留缺端点的**字段**全在请求 Schema 里声明 ⇒ 成因**不是**数据缺陷（端点仍 `enabled` /
  `verified` / 写方法齐全，数据侧**未**动）。
- **`DB.SSEIS` 本批**不**纳入**：其请求 Schema 把条目字段声明在 `Assign` 的
  **`patternProperties`**（`^[0-9]+$`）下，而 `check_write_templates.py` 的 `request_schema()`
  **只**读 `properties` ⇒ 该形状下「字段不臆造」**不可判**（**不**改工具、**不**放宽判定）。
- 可执行判定 = `tests/test_midas_write_coverage_p146.py`（9 项）· `docs/reports/P146_…md`。

**⑧ P147 更新（第四批 13 个端点；新增 `docs/07` §16.1 R104）**：**10** 条模板跑通、**3** 条如实留缺。

- **落盘前的只读自省（本批新增的纪律）**：对 13 个候选**先**做**只读** `GET /info/db/<CODE>`，
  核对「手册示例字段 ⊆ 本 build 接受字段」（本批 13 个端点 `unknown` **0**）；`DB.ACTL` 的
  `CLATS`（R101 的对照物）正说明**数据侧 Schema 里有**该字段、而 build 不接受 ⇒「Schema 声明」
  **不足以**判定是否被接受（见 `tests/test_midas_write_coverage_p147.py` 的对照用例）。
- **10 个跑通**（全部**只有数据侧模板**、**零前置链**）：`DB.POGD` / `DB.POSP` / `DB.SDHY` /
  `DB.SDIS` / `DB.SDST` / `DB.SDVE` / `DB.SDVI` / `DB.TDGR` / `DB.TDME` / `DB.TDMT`
  ⇒ 模板 **35 → 45**、复算 body **71 → 81**（`references` 仍 **22** / `self_references` 仍 **4**）；
  真实 L5 **46 / 46 `PASSED`**（GEN NX 空项目）⇒ 覆盖率 **`36 / 609` → `46 / 609`**
  （`model_write_ratio` **`36 / 410` → `46 / 410`**）；候选集 GEN NX **36 → 46** · CIVIL NX **32 → 39** ·
  Civil Designer 仍 **0**（blocked **517 → 507** / **450 → 443** / **31**）；
  跑前 / 跑后哨兵（**49** 个端点）**全空、0 不可读**。
- **`DB.MVCT` / `DB.TDMF` / `DB.THGC` 如实留缺（R104）**：手册示例被本 build **拒绝**
  （`POST` → **`400 software_api_error`**，与 R103 的 `DB.SKEW` 同形）⇒ 模板**不写**、不入候选；
  三个端点的**字段**全在请求 Schema 里声明 ⇒ 成因**不是**数据缺陷（端点仍 `enabled` /
  `verified` / 写方法齐全，数据侧**未**动）。**未**做逐端点原生试探（P146 §7 的教训已落实）。
- **未试的救回路径（如实记录）**：`DB.TDMF` 另有 **2** 个手册示例条目（`Shrinkage Strain` /
  `Relaxation`）、`DB.MVCT` 另有 **1** 个（`Russia`）—— 若要救回，须按同一纪律做**一次**
  替代示例批量（**不**逐端点试探）。
- 可执行判定 = `tests/test_midas_write_coverage_p147.py`（9 项）· `docs/reports/P147_…md`。

**⑨ P148 更新（第五批 13 个端点 → 12 条模板跑通；新增 `docs/07` §16.1 R105）**：
池子 = 155 个「有写方法 ∧ 有读路径（`GET` + `read_root`）∧ 有 `DELETE` ∧ 非危险 ∧ 产品可得 ∧ **无**模板 ∧
无 Transformer」的端点（同一 `input_uri` 口径下 **132** 个有可用手册示例条目）；本批只取**定义类独立表**。

- **落盘前的只读自省（沿用 P147 的纪律）**：13 个候选**先**逐个做**只读** `GET /info/db/<CODE>`，
  核对「手册示例字段 ⊆ 本 build 接受字段」（13 个端点 `unknown` **0**），**再**落模板，
  然后**只跑一次**有界批量（`only=(本批 13 个 key)`）。**未**做任何逐端点原生试探。
- **12 条跑通**（body 全部**原样**照抄手册示例、零 `adjustments`）：
  **零前置链（10）** `DB.HHCT` / `DB.MVCTBS` / `DB.MVCTCH` / `DB.MVCTID` / `DB.MVCTTR` /
  `DB.POSL` / `DB.STOR` / `DB.EXLD` / `DB.LDSQ` / `DB.EFCT`；
  **用既有前置机制（2）** `DB.NMAS`（`target_id_source = "DB.NODE#1"`，`Assign` 键就是自建节点号）、
  `DB.TDNT`（`prerequisites[].references` 把自建材质号写回 body 的 `MATL`）。
  ⚠️ `DB.EXLD` / `DB.LDSQ` / `DB.EFCT` 的请求体**引用荷载工况名** ⇒ 第一次有界批量被拒（`400`），
  按**既有**机制补 `DB.STLD` 前置（工况名逐条对齐 `LCNAME_ITEM` / `LCNAME` / `COMB_LIST`）后通过 ——
  这**不是**「在数据侧硬凑」：前置链本来就是为「请求体引用的对象必须先存在」而设的（见 §2.3）。
  ⇒ 模板 **45 → 57**、复算 body **81 → 101**（`references` **22 → 23** / `self_references` 仍 **4**）；
  真实 L5 **58 / 58 `PASSED`**（GEN NX 空项目）⇒ 覆盖率 **`46 / 609` → `58 / 609`**
  （`model_write_ratio` **`46 / 410` → `58 / 410`**）；候选集 GEN NX **46 → 58** · CIVIL NX **39 → 49** ·
  Civil Designer 仍 **0**（blocked **507 → 495** / **443 → 433** / **31**）；
  跑前 / 跑后哨兵（**20** 个端点：4 个默认哨兵 + `DB.STLD` / `DB.FBLD` / `DB.BMLD` + 13 个候选）**全空、0 不可读**。
- **`DB.IMFM` 如实留缺（R105）**：其手册**两个**条目（条目 7 `STEEL_NAME`、条目 8 `CONC_NAME` +
  `CONFINED_CONC_NAME` + `REBAR_NAME`）**逐个**实测都被本 build **拒绝**
  （`POST` → **`400 software_api_error`**，与 R103 的 `DB.SKEW` / R104 的 `DB.MVCT` 同形）⇒ 模板**不写**、
  不入候选（**已撤模板**，不入 `limit`、不产生假 `FAILED`）；成因**不是**数据缺陷
  （字段全在请求 Schema 里声明，只读自省 `unknown` = 0；端点仍 `enabled` / `verified` / 写方法齐全）。
  恢复条件 = 上游手册 / 新 build 给出可接受示例。
- 可执行判定 = `tests/test_midas_write_coverage_p148.py`（9 项）· `docs/reports/P148_写路径覆盖推进第五批_v1.0.md`。

**⑩ P149-A 更新（端点方法集**实测修正**与分母重算；新增 `docs/07` §16.1 **R108**）**：

- **真值来源**：`HTTP OPTIONS` 的 `Allow` 头（**只读、零副作用**；无 `Allow` 时补一次 `HEAD`）。
  证据 = `registry/live/live_methods.json`（**636** 端点；其中 **72** 个 `live_methods` 为空 =
  该路由在本 build 上不存在）；复算工具 = `registry/tools/sync_endpoint_methods.py`
  （`--probe` 重测 / `--write` 写回 / `--check` 断言一致；**只增不减**、只改 `methods:` 一行）。
- **发现**：`registry == live` **513** · **少声明 90**（+`DELETE` 88 · +`PUT` 80 · +`GET` 62 · +`POST` 6；
  `DB` 9 · `DESIGN` 80 · `OPE` 1）· **多声明 0**。上游手册
  `E:\MCP\MIDAS-API-Online-Manual\manual\midas Gen API 使用手册.md` 的 `Active Methods` 与 live
  在 **541** 个可比端点里 **532** 个一致（差异 9 条，逐条见报告 §1）。
- **连带效果**：分母 **`609 → 633`**（**24** 个端点原来被整个漏出分母）· `write_only 368 → 306` ·
  `model_write 410 → 434` · `result_query 199`（不变）；候选集**不变**（58 / 49 / 0，新解锁端点仍缺模板）；
  blocked **495 → 515** / **443 → 451** / 31；`http_method_confirmed 635 → 636`；
  `request_schema_confirmed 629 → 628`（**收紧**：`OPE.SECTPROP` 实测有 `POST` ⇒ 需要请求体，而它没有 Schema）。
- **R5 裁决 B 的适用范围收窄**：`OPE.SECTPROP` 移出「无请求体」桶 ⇒ `R5_NO_REQUEST_BODY` 只剩
  `OPE.PROJECTSTATUS` / `VIEW.SELECT`（桶计数 `no_request_body 4 → 3`、`manual_has_no_json_schema 0 → 1`）。
- **72 个「本 build 路由不存在」**：**不**改 `methods`、**不**改 `products` / `availability`，只如实记录
  （它们是**有据可查**的定义，只是本 build 不可得；**不**算「欠账」）。
- 可执行判定 = `tests/test_midas_endpoint_methods_p149.py`（**7** 项）·
  `docs/reports/P149-A_端点方法集实测修正与分母重算_v1.0.md`。

**⑪ P149-B（第一子批）：模板来源扩为**两份**（新增上游 NX 手册抽取）**：

- **新增第二来源** `MIDAS_API_Online_Manual_Gen_NX_v1.0.json`（仓库根，2.98 MB）：上游 NX 手册
  `E:\MCP\MIDAS-API-Online-Manual\manual\midas Gen API 使用手册.md`（12 MB）的**机械抽取** ——
  **841** 条目 · **607** 有示例 · **1488** 个示例 · **629** 有 `Active Methods`；含来源指纹
  （`source.sha256` / `source.bytes`）。生成器 = `registry/tools/sync_manual_index.py`
  （`--write` / `--check`，只依赖标准库）。
- **形状与既有来源一致**（`endpoints[].input_uri` + `examples[].json` 原样文本），故
  `check_write_templates.py` 用**同一套** `manual_item()` 口径复算**两个来源**：
  URI 按 `normalize_uri()`（去前导斜杠 + 小写）查表、两来源**合并**（先到先得；
  同一路由在上游手册里多章节重复出现时**不**互相覆盖）。既有 57 条模板在新口径下仍 **0** 错。
- **`json_schema` 不抽取**：数据侧已有 **208/208** 个请求 Schema，模板复算只需示例
  （字段不臆造的判定仍走数据侧 Schema）。
- 与既有来源重叠 **264** 个 `input_uri`，新来源独有 **176** 个。
- 可执行判定 = `tests/test_midas_manual_index_p149b.py`（**4** 项）。
- **未完成**（下一子批）：**已由 §8.11（⑫，P149-B2）处置** —— 池子口径更正为 **205**
  （旧来源示例 **119** · 仅新来源 **70** = **189** 有可用示例；**13** 无可用示例），
  其中 **12** 条真实 `PASSED`、**180** 条留缺（**0** 条未取得结论）。原文保留以便追溯。

**⑫ P149-B2：模板由工具拥有 + 两轮实测（两次实例崩溃）**：

- **新工具** `registry/tools/sync_write_templates.py`（`--write` / `--check`，只依赖标准库 + `app/`）：
  按 §2.3 的池子判据**机械**生成模板（示例按「旧 → 新」取第一个可用条目，`manual_example`、
  零 `adjustments`、零前置链），并**主动剔除**留缺账本里的 key。
- **留缺账本** `registry/live/write_template_left_out.json`（**180** 条）：把「实测被拒 / 读不回 /
  数据侧 Schema 不匹配 / 读映射未验证 / **使实例崩溃**」的端点**机器可读**地记下来 ——
  R101–R105（**11** 条，原证据见 `docs/reports/P144…P148`）· R109（**2** 条）· R110（**117** 条）·
  R111（**49** 条）· R113（**1** 条）。
- **池子口径两处更正**（工具更严，逐条可复算）：① 已有 Transformer 的端点（`DB.NODE`）**不**属欠账；
  ② 3 个 `DESIGN.*.LCTB` **无写方法**（只有 `GET` + `DELETE`）⇒ 633 的分桶新增「无写方法 **3**」，
  「可判形态但缺模板」由 **208** 更正为 **205**（且本批已处置完毕）。
- **无可用示例 13**（严格口径）：`no_manual_entry` **11** · `example_item_empty` **1**（`DB.DRLS`）·
  `example_shape_unusable` **1**（`DB.NUCS`）；P149-A 的「**12**」是把旧来源的 `endpoint` 字段
  当定位串算的（`DB.ULCT` 那条的 `input_uri` 实为 `db/LTSR`）⇒ 更正为 **13**。
- **复算工具修一处真缺陷**：`check_write_templates.py::request_schema()` 新增 `_item_schema()`，
  支持 `Assign.patternProperties['^[0-9]+$']` 形状（剥到**条目** Schema）⇒ 假错 **71 → 0**，
  判定**变强**（R112 记录了**仍未**支持的「按端点代码键控」形状及其实测影响面 **53/60**）。
- **实测两轮（GEN NX 空项目）**：第一轮一次有界批量 **179** 条（**3** `PASSED` · **49**
  `400 software_api_error` · **10** 读不回 · **1** `solver_unsupported` · **49**
  `registry_mapping_not_verified` · **67** `request_timed_out`）；第二轮把 67 条**分块**（20/20/20/7，
  块间只读健康检查）补测 ⇒ **9** `PASSED` · **53** `400` · **4** 读不回 · **1** `DB.NSPR`
  `transport_error`。两轮合计 **12** `PASSED` ⇒ 覆盖率 **`58 / 633` → `70 / 633`**、
  候选 **70 / 60 / 0**、blocked **503 / 440 / 31**、模板 **69**、body **113**。
- ⚠️ **R113：`DB.NSPR` 使 NX 实例崩溃**（两轮各触发一次「发生了无法确定的问题需要终止程序」）
  ⇒ 模板**撤**、**永不再试**；两轮**跑后**哨兵读数均**无效**（**不**声称零残留），
  第二轮**跑前**只读残留核对（**122** 个端点）**全空** ⇒ 第一轮无残留；**收尾**（实例第二次恢复后）
  只读残留核对 **122** 个端点**全空、0 不可读** ⇒ **零残留**（证据文件 `residue_final`）。
- 可执行判定 = `tests/test_midas_write_templates_p149b2.py`（**8** 项）·
  `docs/reports/P149-B2_写路径模板机械化与批量实测中断_v1.0.md`。

**⑬ P149-C：只读 L4 收口 `availability`（R111 闭环）+ 解锁后的分块写路径实测**：

- **闸门的精确判据**：写路径第 1 步（只读 `LIST`）受 `client.guard_verified()` 约束 ——
  `verification_status == VERIFIED`，而该状态**只**由 `availability` 机械映射（`docs/07` §7.2 / R78）
  ⇒ `availability: untested` 的写端点**无法**进入写路径（`registry_mapping_not_verified`）。
- **`availability` 的语义**（§4）：`verified` = 「**至少一个实例 GET 成功**」⇒ 恢复条件 = **只读**实测
  再据实收口（P134 的 L4 口径：**响应顶层键 == `read_root`**）。
- **新工具** `registry/tools/sync_availability.py`（`--probe` **只发 GET** / `--write` **只升不降** /
  `--check`）：证据 = `registry/live/live_read_probe.json`（**49** 条，**不含凭据**）；
  收口 = 49 个 YAML 的 `availability: untested → verified` + `verified_on: ["gen-local"]`
  （一行替换 + 一行插入）⇒ `sync_manifest.py --write` 重派生（字段差异 **98** 处）⇒
  `sync_response_schemas.py --write` **只追加** `response` 块（49 个文件 / +784 行）。
- **只读 L4 实测**：**49 / 49** `HTTP 200` 且响应顶层键 == `read_root`（全部 `PARTIAL` = 空项目下
  块为空，与 P134 的 166 个 `PARTIAL` 同口径）；`availability == verified` **247 → 296**。
- **解锁后的分块写路径实测**（`registry/live/write_batch_p149c.json`）：**3** 块（20 / 20 / 9，块间只读
  健康检查 `GET /DB/NODE`）⇒ **2** `PASSED`（`DESIGN.RC.KDS-41-20-2022.WMAK` /
  `DESIGN.SRC.AIK-SRC2K.DSRC`）· **47** `FAILED`（**全部** `400 software_api_error` ⇒ **R110**）；
  跑前 / 跑后只读核对**均全空** ⇒ **零残留**、**未崩溃**（P149-B2 的两次崩溃教训已被分块流程吸收）。
- **计数**：覆盖率 **`70 / 633` → `72 / 633`**（`model_write` **`72 / 434`**）· 候选 **72 / 62 / 0** ·
  blocked **501 / 438 / 31** · 模板 **71** / body **115** · 响应 Schema 行 **241 → 290** ·
  留缺账本 **180 → 178**（R110 **164** · R101–R105 **11** · R109 **2** · R113 **1**）。
- **R111 闭环**（49 个全部取得结论），恢复路径**已工具化**（可复算）。
  ⚠️ **P149-E 更正**：旧记的「其余 **317** 个未验证的**只读**端点」**偏松** —— 据实复算
  `availability != verified` 共 **155** 个 = **35** 可探（`GET` + `read_root` + 已启用）+
  **119** **没有** `GET` + **1** 已禁用；其中 **35** 个已由 **P149-E** 只读补测（见 §8.12 ⑮），
  余 **23** 个 `unverified` 复测**仍 `404`**（**R85** 成立）。
- 可执行判定 = `tests/test_midas_availability_p149c.py`（**7** 项）·
  `docs/reports/P149-C_只读L4收口availability与写路径解锁_v1.0.md`。

**⑭ P149-D：**R106** 取报表判据（`POST.*` **197**）+ **R107** 取设置表判据（无 `DELETE` **14**）+ **R112** 修完**：

- **R106（`registry/README.md` §8.13）**：`POST.*` 的 **197** 个端点**只**有 `POST`、**没有**
  `GET` / `read_root` ⇒ L5 三步链（创建 → 读回 → 按路径 key 删除）**结构上不适用**。
  **判据** = 最小模型（**只**用自建编号，**8** 个对象）+ `POST /DOC/ANAL`（空体）⇒ 逐端点发
  **该端点自己那张表**的手册示例（**唯一**改动 = 剥掉 `Argument.EXPORT_PATH`）⇒ `HTTP 200` ∧
  **实测信封形状**（恰好 **1** 个顶层键 ∧ 其值是对象 ∧ 含 `HEAD` / `DATA` 两个数组）⇒ `PASSED`；
  `200` ∧ 空块（`{}` / `{"message": ""}`）⇒ `PARTIAL`；其余 ⇒ `FAILED`。
  **实测**（有界 **20** 块 × 10 条，块间只读健康检查）：`PASSED` **15** · `PARTIAL` **172** ·
  `FAILED` **8**（**全部** `400` 原生拒绝：`error creating utbl. (ex PostMode …)` ×6 ·
  `Please Check RC Design Code.` ×1 · `Unknown Error` ×1）· 留缺 **2** ⇒ **195** 条取得结论。
  **零残留**（跑前 == 跑后哨兵逐条相同；清理后全空）。
  ⚠️ **信封键逐端点不同**（`Example` **10** 个；另有 `ElementPropertiesatEachStage` /
  `TendonGroup` / `TendonProfile` / `TendonProperty` / **字面** `empty`）—— 判据**只**断言**形状**，
  实测键逐条记进证据（`envelope_key`）后落成 `response` 块。
  ⚠️ **R115（新）**：`POST.TABLE.FIBR_MAXCONTRACT` **使 NX 实例崩溃**（批量第 41 条 `ReadError`
  ⇒ 实例重启、项目关闭；**单独复现**确认 ⇒ **永不再试**）；成因需 **MIDAS 侧**排查。
- **R107（`registry/README.md` §8.14）**：GEN NX 上**无 `DELETE`** 的端点 **14** 个
  （`GET`+`PUT` **11** · `GET`+`POST` **3**）。**判据** = 「`GET` 读回**非空**原值 →
  `PUT` 改动过的值（手册示例）→ 读回确认**改动生效** → `PUT` **还原**原值 → 读回确认**逐字节**
  等于原值」。⚠️ **前置闸门**：`GET` 返回 `{}` ⇒ **绝不**发 `PUT`（**没有** `DELETE` ⇒ 会留下
  **不可删**的记录）。**实测**：`PASSED` **2**（`DB.STYP` / `DB.UNIT`，**逐字节**还原）·
  `FAILED` **7**（空原值闸门拒绝写）· 留缺 **5**。**结论单独成桶**（`no_delete_singleton`），
  **不**并入 L5 三步链的覆盖率分子；**原口径照旧报出、不过滤、不隐藏**。
  ⚠️ **残留如实披露**：侦察阶段对 `DB.PZEF` 发过一次 `PUT`（其 `GET` 原值是 `{}`、**无** `DELETE`）
  ⇒ **无法清除**（`PUT {"Assign": {}}` 返回 `200` 但读回仍在）⇒ 记入 `docs/reports/P149-D_*.md`。
- **R112 修完（`check_write_templates.request_schema()`）**：请求方向实测有**四种形状**
  （根 `properties` 包装 · **根级包装** · **按端点代码键控** · 单根键下**平铺**条目字段）。
  旧版**只**认第一种 ⇒ **63 / 71** 个模板的字段白名单检查是**空判**（恒真 = 没查）；
  修后 **71 / 71 全部非空判**（逐条复算 **0** 空判 · **0** 未知字段）—— 判定**变强**，**不**放宽。
  **裁决 R112-A = 补 Schema**：`DB.SECT.SECT_BEFORE.{DATATYPE, SECT_I}` 被暴露（手册示例 + 本 build
  自省 `GET /info/db/SECT` **双重**来源声明）⇒ 按**已登记的自省来源**补齐这两个字段（**不**引入
  自省里其余 55 个字段）；`tests/test_midas_write_templates_p149b2.py` 的「钉住旧现状」用例
  **反向**改成断言**更强**的行为。
- **计数（P149-C → P149-D）**：`availability == verified` **296 → 481**（`untested` **317 → 132**）·
  响应方向 Schema 行 **290 → 305**（`sync_response_schemas.py` 接入 R106 实测信封：新增
  `measured_envelope_keys()`，`is_measured()` / `envelope_chains()` 接受 R106 实测键 ——
  **同一**判定点，**不**另写规则）· `midas_api_schemas` 合计 **915 → 930** 行 ·
  **`live.write_path_coverage()` 仍是 `72 / 633`**（R106 / R107 的结论**不**改三步链口径）。
- 可执行判定 = `tests/test_midas_result_tables_p149d.py`（**10** 项）·
  `tests/test_midas_singleton_tables_p149d.py`（**7** 项）·
  `docs/reports/P149-D_写路径覆盖收尾_R106取报表判据与R107取设置表判据_v1.0.md`。

### 8.13 R106：`POST.*` 结果表 / 文本查询的**取报表判据**（P149-D）

`POST.*` 的 **197** 个端点（GEN NX：`POST.TABLE.*` **194** + `POST.PM` / `POST.TEXT` /
`POST.STEELCODECHECK`）**只**有 `POST`、**没有** `GET` / `read_root` ⇒ L5 三步链
（创建 → 读回 → 按路径 key 删除）**结构上不适用**（没有「自建 ID」可读回 / 可删）。

| 项 | 判据 |
| --- | --- |
| 前置链 | 最小模型（`MINIMAL_MODEL`，**只**用自建编号，**8** 个对象）+ `POST /DOC/ANAL`（`Argument` 空体）。**实测**：空项目下 `POST /POST/TABLE` → `400 "[empty] Cannot generate table data as there is no analysis result."` ⇒ **必须**有分析结果 |
| 请求体 | 上游手册（两个来源合并）里该端点**自己那张表**的示例；**唯一**改动 = **剥掉 `Argument.EXPORT_PATH`**（带它会让实例**落文件**）。定位：`table_type` 非空 ⇒ 按 `TABLE_TYPE` / `TEXT_TYPE` 精确匹配；否则按端点 `title` 与示例名（剥尾部 ` #<n>`）前缀匹配；仍多解 ⇒ 字典序第一个（记 `example_id`） |
| 判定 | `HTTP 200` ∧ **实测信封形状**（**恰好 1 个**顶层键 ∧ 其值是对象 ∧ 含 `HEAD` / `DATA` 两个数组）⇒ `PASSED`（实测键记 `envelope_key`）；`200` ∧ 空块（`{}` / `{"message": ""}`）⇒ `PARTIAL`；其余 ⇒ `FAILED`；传输失败 ⇒ `SKIPPED` |
| 零残留 | 跑前 / 跑后 **7** 个模型哨兵**逐条相同**；跑完**逆序**清理自建模型，清理后哨兵**全空** |

**证据** = `registry/live/result_table_probe.json` · **复算工具** =
`registry/tools/probe_result_tables.py`（`--probe` / `--write` / `--check`；
**续跑**：已取得结论的行逐字节保留，`instance_down` 的行重测；判据修订由 `CRITERION_VERSION` 触发重测）·
**可执行判定** = `tests/test_midas_result_tables_p149d.py`。

### 8.14 R107：无 `DELETE` 的单例 / 设置表的**取设置表判据**（P149-D）

GEN NX 上**无 `DELETE`** 的端点 **14** 个（`GET`+`PUT` **11** · `GET`+`POST` **3**）⇒ 三步链第 3 步
走不通。

| 项 | 判据 |
| --- | --- |
| 前置闸门 | `GET <uri>` 必须返回**非空**原值（`{<read_root>: {"1": {…}}}`）。**空 ⇒ 如实留缺**（`empty_singleton_put_creates_undeletable_record`，**绝不**发 `PUT`）：`PUT` 会**创建**记录而该端点**没有** `DELETE` ⇒ **无法还原** |
| 判定 | 读回原值 → `PUT` **改动过**的值（手册示例）→ 读回确认**改动生效** → `PUT` **还原**原值（逐字段照抄跑前读回）→ 读回确认**逐字节**等于原值 ⇒ `PASSED` |
| 子桶 | 结论**单独成桶**（`no_delete_singleton`），**不**并入 L5 三步链的覆盖率分子；**原口径照旧报出** |

**证据** = `registry/live/singleton_table_probe.json` · **复算工具** =
`registry/tools/probe_singleton_tables.py` · **可执行判定** =
`tests/test_midas_singleton_tables_p149d.py`。

**恢复条件（R119 / P150，**只**更新条件、**不**硬试）**：证据里的 `gaps` **逐条**配上 `recovery`
（由 `probe_singleton_tables.py --refresh-recovery` **离线**补齐：**不发任何请求、不改任何结论**）。

| 原因 | 条数 | 恢复条件 |
| --- | --- | --- |
| `empty_singleton_put_creates_undeletable_record` | **7** | **非空**专用项目（该表已有 `1` 号记录 ⇒ `PUT` 才是「改」而不是「建」）；**没有**就**如实**保持留缺（**R116**：空项目上 `PUT` 会留下**不可删**的记录） |
| `no_put_method` | **3** | **MIDAS 侧**提供 `PUT`（或另立判据） |
| `no_manual_entry` | **1** | 上游手册补条目 |

**⑮ P149-E：只读 L4 补测收口 + 「317」记法据实更正**：

- **记法更正（不美化）**：旧记「其余 **317** 个未验证的**只读**端点」**偏松** —— 据实复算
  `availability != verified` 共 **155** 个 = **35** 可探（`GET` + `read_root` + 已启用）+
  **119** **没有** `GET` + **1** 已禁用；**更正不改任何判定**。
- **工具加固**（P149-B2 的教训落到本工具，**只**改工具）：`sync_availability.py` 新增
  `--chunk-size`（默认 **20**）+ 块间**只读**健康检查 `GET /DB/NODE`（非 `200` ⇒ **立即中止**）+
  **累积**（既有证据的行**逐字节保留**，本批只补新目标）+ 传输失败 / `The project is not opened`
  归 `SKIPPED`（**不**计入收口）+ 非 `200` 记 `detail`。
- **只读补测**：**35** 个（**2** 块 20 / 15，健康检查均 `200`；**全部只发 `GET`**）⇒ 证据
  `registry/live/live_read_probe.json` **84** 行 = **61** `PARTIAL` + **23** `FAILED`。
- **收口 12 个**（`200` ∧ 块为空 ⇒ `PARTIAL`）：`DESIGN.RC.KDS-41-20-2022.{CMFT, DCREM, EQCT,
  MBTP, MCMB, MLLR, MRFT, REBB, SDGN, SUEQ, TRFT}` · `DESIGN.STEEL.KDS-41-30-2022.SLRS`
  ⇒ `availability: untested → verified` + `verified_on: ["gen-local"]`（**只升不降**）⇒
  `sync_manifest.py --write`（**24** 处字段）⇒ `sync_response_schemas.py --write`（**12** 个文件
  **只追加** `response` 块）。⚠️ 这 12 个正是 **R110** 留缺账本里的端点 —— **读路径**与**写路径**
  是**两个**判定（读得回 ≠ 写得进），留缺账本**一行未动**。
- **复测仍失败 23 个**（`-M1` 家族 + `DB.UFTR` / `DB.UTBL`）：本 build **`404`** ⇒ **R85 成立**；
  `availability: unverified` ⇒ **只升不降** ⇒ **一行未改**（逐条以 `git diff --quiet HEAD -- <file>` 断言）。
- **计数**：`availability == verified` **481 → 493**（`untested` **132 → 120**）· 响应 Schema 行
  **305 → 317** · `midas_api_schemas` **930 → 942** 行 · **`live.write_path_coverage()` 仍 `72 / 633`**。
- 可执行判定 = `tests/test_midas_availability_p149e.py`（**7** 项）·
  `docs/reports/P149-E_只读L4补测收口与317记法更正_v1.0.md`。

**⑯ P150：请求方向 Schema 的「覆盖不全」收口（R117）+ 写路径「编辑（PUT）」判据（R118）**：

- **R117（主）**：端点定义里**已登记**的**只读**来源 `schema_ref.introspect`（`GET /info/db/<CODE>`）
  对**全部 244** 个端点做**只读**扫描（**13** 块 × 20 + 块间只读健康检查 `GET /DB/NODE`，
  全部 `200`；**只发 `GET`**）⇒ **199** 可比 · **45** 本 build `404`
  （**23** `unverified`（R85）· **15** `unavailable_on` 含 `gen-local` · **7** CIVIL_DESIGNER 独有）。
  逐端点**递归**字段集差集：**24** 个端点自省独有字段、**12** 个端点**反向缺口**（**一律未动**）。
  **裁决 R117 = 补 Schema**（**21** 个端点 / **212** 个字段；**只**补自省实际声明的字段、**只新增名字**），
  **留缺 3 个**（`DB.KFAC` `product_not_probed` · `DB.SSEIS` / `DB.SWIND` `strict_schema_conflict` +
  `invalid_introspect_node`）。⚠️ 判定口径**未变**；**3** 个「裸 `object` ⇒ 不判」的父节点变成**可判**
  （判定在该处**变强**），`check_write_templates` 仍 **71 / 71 非空判 · 0 未知字段**。
  证据 = `registry/live/introspect_field_diff.json` · 工具 = `registry/tools/sync_introspect_fields.py`
  （`--probe` **只发 GET** / `--write` / `--check`）· 判定 = `tests/test_midas_introspect_fields_p150.py`（**10** 项）。
- **R118（次）**：写路径「**编辑（PUT）**」判据 = 只读哨兵 → 创建（该端点的**写入方法**；**只**碰自建编号）
  → 读回 → **PUT 改动过的值**（逐条记 `{path, from, to, why}`）→ 读回确认**改动生效** → 删除 →
  读回确认消失 → **无副作用观察**（删除后再发一次同一 PUT，看是否**重新出现**）。
  目标 **71**，本批实测**零前置链的 56** 个 ⇒ **37** `PASSED` · **14** `LEFT_OUT` · **5** `FAILED`；
  **15** 个带前置链如实留缺。**两个侦察答案**：PUT 的 body 形状 = **与创建同一形状**
  （`assign_keyed_item`）；**PUT 不要求记录已存在**（upsert，**37 / 37** 实测 ⇒ 与 **R116** 互相印证）。
  ⚠️ **残留如实披露**：本 build 的 `DELETE` 会**返回 `200` 并回显被删记录却不真正删除** ⇒ 判据以
  「**再读确认不在**」为准；`DESIGN.*` 别名路由（`DESIGN.RC.DRC` / `DESIGN.RC.KDS-41-20-2022.DCTL` /
  `DESIGN.STEEL.DSTL`）的 `DELETE` **不生效**（已按**同表 `DB.*` 路由**清理），
  `/DESIGN/SRC/AIK-SRC2K/DSRC` **无** `DB.*` 别名、**无法清除**（`residue` + `allowed_residue` 披露）。
  **分桶**：与 **R107** 分开、**不**并入 L5 覆盖率分子（`write_path_coverage()` **不变**）。
  证据 = `registry/live/put_edit_probe.json` · 工具 = `registry/tools/probe_put_edits.py` ·
  判定 = `tests/test_midas_put_edits_p150.py`（**9** 项）。
- **R119**：`registry/live/singleton_table_probe.json` 的留缺**逐条**配上 `recovery`（**离线**补齐：
  `probe_singleton_tables.py --refresh-recovery`，**不发任何请求、不改任何结论**）——
  空原值单例表（**7** 个）的恢复条件 = **非空**专用项目（**R116**）；**没有**就如实保持留缺。
- **计数**：端点 **636** · Schema 文件 **625** · 模板 **71** / body **115** ·
  `availability: verified` **493** · 响应 Schema 行 **317** · **`live.write_path_coverage()` 仍 `72 / 633`**
  （`model_write_ratio` **`72 / 434`**）—— 本批**没有**任何既有钉住计数变化。
- 可执行判定 = `tests/test_midas_introspect_fields_p150.py`（**10** 项）·
  `tests/test_midas_put_edits_p150.py`（**9** 项）·
  `tests/test_midas_singleton_tables_p149d.py::test_p150r119_every_gap_carries_a_recovery_condition`（**1** 项）·
  `docs/reports/P150_接口Schema覆盖收口与写路径编辑判据_v1.0.md`。

**⑰ P151：写路径「编辑（PUT）」判据续跑（15 个带前置链端点）+ R120 别名路由清理工具化（接 ⑯）**：

- **R118 续跑（主）**：⑯ 只实测**零前置链的 56** 个，带前置链的 **15** 个如实留缺；本批**同一判据、
  同一证据文件**续跑那 15 个 ⇒ **5** `PASSED`（`DB.ELEM` / `DB.LENG` / `DB.NMAS` / `DB.PDEL` /
  `DB.TDNT`）· **9** `LEFT_OUT`（`no_editable_scalar`）· **1** `FAILED`（`DB.EFCT`，**R124**：
  三种形状全 `400`）⇒ 子桶合计 **71** 行 = **42** `PASSED` + **23** `LEFT_OUT` + **6** `FAILED`，
  `left_out_prerequisite_chain` **空**（带链端点**全部**取得结论）。
- **前置链沿用 L5 的机制**（**不**重写判定点）：声明由 `app/.../write_templates.py` **唯一**解析；
  编号**一律重新分配**（该端点既有编号的 `max + 1`；`id_source = "target"` 的前置取**目标**编号；
  目标可用 `target_id_source` **反向**取前置编号）；**按声明顺序创建**、目标清理后**逆序**删除；
  **只**碰自建编号；删除一律以「**再读确认不在**」为准。工具 `plan_chain()` 与 L5 的 `_plan()` 的
  **等价性**由测试逐条断言（空项目 + **非空**快照，目标编号 + 每个前置编号 + 每个请求体**逐字节**）。
- **哨兵口径升级**：跑前 / 跑后只读哨兵 = **全部目标 ∪ 全部前置端点** = **72** 个（新增 `DB.NODE` ——
  它**只**作为前置出现、**不在**目标集里）；跑前用 `--allow-residue` 显式放行**已披露**的残留，
  跑后非空**仍然只有**它 ⇒ **零新增残留**、**未**中止、**未**崩溃（**3** 块 1 / 10 / 4 + 块间健康检查）。
- **R120 工具化（次）**：`DESIGN.*` 别名路由的清理路径 = **同表 `DB.*` 路由**，映射**必须来自实测**
  （`--probe-aliases`：自建编号经别名路由创建 ⇒ 出现在同表 `DB.*` 路由的读回块里 ⇒ `DB.*` 路由
  `DELETE` 后**两个**路由再读均不在）。实测 **3** 对全部 `same_table_observed = true` ·
  `alias_delete_effective = false` · `db_delete_effective = true` · `delete_confirmed = true`；
  证据的 `alias_cleanup` 块 + 逐行 `delete_state` **区分**「删除已确认」/「别名清理已确认」/
  「删除未确认」（**未**确认的**必须**在 `residue` 里如实披露）⇒ 收尾步骤**可离线复算**。
- **R122**：`designer-cloud` **当前不可用**（**全部**路径含根路径 `404 client does not exist` ⇒
  **会话 / 客户端级**失败）⇒ `DB.KFAC` 的 CIVIL_DESIGNER 自省来源仍缺，**如实保持留缺**（**R125**）；
  `--probe` **未**在该实例上跑（**不**污染 `gen-local` 的证据）。
- **计数**：**唯一**变化的钉住计数 = R118 子桶（56 → **71** 行；`37 / 14 / 5` → **`42 / 23 / 6`**）；
  其余**全部不变** —— 端点 **636** · Schema 文件 **625** · 模板 **71** / body **115** ·
  `availability: verified` **493** · 响应 Schema 行 **317** · **`live.write_path_coverage()` 仍 `72 / 633`**
  （`model_write_ratio` **`72 / 434`**）· 候选 **72 / 62 / 0** · blocked **501 / 438 / 31** · 留缺账本 **178**。
- 可执行判定 = `tests/test_midas_put_edits_p151.py`（**9** 项；含 L5 等价性与 R120 三态）·
  `tests/test_midas_put_edits_p150.py`（**9** 项，计数同步、**未**放宽）·
  `docs/reports/P151_写路径编辑判据前置链续跑与别名路由清理工具化_v1.0.md`。

**⑱ P152：接口层（`app/` 适配层）「添加 / 删除 / 编辑」端到端调试 + 映射缺口逐条登记（接 ⑯/⑰）**：

- **接口层判据（主）**：以上 ⑬–⑰ 的判据**全部**绕开 `app/`；本批起走**既有 9 个 MCP Tool 契约** ——
  `MCP Tool → OperationPlan（operations.py）→ Adapter（intent 分派）→ MidasHttpClient（护栏 + 包装键）
  → MIDAS 实例`。判据 = **只读侦察**（`OPTIONS` 核对 `Allow` + `GET` 核对 `read_root`）→
  跑前只读哨兵（**全部**被触碰的端点）必须为空 → **添加**（创建 `2xx` → 读回在）/
  **编辑**（创建 → `PUT` 改动过的值 → 读回**确认生效**）/ **删除**（创建 → `DELETE {uri}/{id}`
  **带路径 key** → 再读**确认不在**）→ **清理**（自建编号含前置**一律**删并以再读确认为准）。
- **实测**（GEN NX 专用空项目，**3** 块 5 / 2 / 6 + 块间只读健康检查 `GET /DB/NODE` 均 `200`）：
  **13** 条路径 = **4** `PASSED` + **9** `FAILED`；**添加 / 编辑 / 删除各取得端到端证据** ——
  `MODEL.NODE.CREATE`（`POST /DB/NODE` `200`）· `MODEL.NODE.UPDATE`
  （`PUT /DB/NODE`，`x` `1.0 → 2.0` **读回生效**）· `MODEL.NODE.DELETE`
  （`DELETE /DB/NODE/1` → 再读**不在**）· `MODEL.GROUP.DELETE`（`DELETE /DB/GRUP/1`，**原生**前置）。
  跑前 / 跑后哨兵（**6** 个端点）**全空** ⇒ **零残留**、**未**中止、**未**崩溃。
  ⚠️ **R119 在接口层同样成立**：删除返回体**回显被删记录**
  （`{"delete_node": {"NODE": {"1": {...}}}}`）⇒ 判据**必须**以「再读确认不在」为准。
  ⚠️ 写步骤的结果键是 **`intent`**（写 = `write_node` / 读 = `read`）⇒ `MODEL.*.QUERY` 的规范化
  结果是 `data["read"]`（**不是** Mock 的 `data["items"]`）。
- **R126（新，如实留缺）**：**接口层的 canonical → native 变换覆盖不到原生必填字段** ——
  `DB.ELEM` / `DB.MATL` / `DB.CONS` 的创建被原生 `400 Wrong Field`、`DB.SECT` 被
  `400 Unknown Error` 拒绝（逐条 `native_error` 前 200 字进证据）；而**同一端点**在**数据侧**
  用**手册示例**是**已实测可用**的（⑯/⑰ 的模板 + `put_edit_probe.json`）⇒ 缺口在**契约**
  （canonical 字段集，`docs/04` §20–§31），**不在**端点、**不在**护栏、**不在**数据侧模板。
  **不**硬凑、**不**放宽（补原生默认值会违反「不臆造字段」）；恢复条件 = **显式裁决** canonical
  字段集。连带面：`DB.ELEM` 的 `material_id` / `section_id` 在**空项目**上无编号可引用，而
  材质 / 截面**建不出来**（同一成因）。
- **映射缺口（次，逐条登记、离线可复算）**：`registry/live/interface_mapping_gap.json` ——
  数据侧写路径分母 **633** ⊇ 接口层可达（GEN NX ∧ 已启用 ∧ 非破坏性）**576** ⊇
  形态齐备（有 `GET` + `read_root`）**301**；69 个 Operation 共映射 **61** 个端点 ⇒
  **缺口 517** = **271** `not_in_operation_contract`（形态齐备但**契约外**）+
  **246** `no_readback_route`（没有 `GET` 或没有 `read_root`）。互补性可执行断言：
  `缺口 ∩ 已映射 = ∅`。⚠️ `DESIGN.SRC.AIK-SRC2K.DSRC` 与 `POST.TABLE.DISPLACEMENTG`
  **在契约内**（分别由 `DESIGN.SRC` / `RESULT.NODE.DISPLACEMENT` 映射）—— 据实澄清、**不**算缺口。
- **`app/**` 一行未改**（授权范围 = 空集；`pyproject.toml` 未改 ⇒ 无新依赖）：
  候选改动（扩 `transforms.py` 字段表 / 补原生默认值 / 新增 `MODEL.GROUP.CREATE`）分别属
  **改契约**、**放宽既有裁决**、**改 9 Tool Contract** ⇒ 均超出本批授权，理由逐条见报告 §3。
- **计数**：本批**没有**任何既有钉住计数变化 —— 端点 **636** · Schema 文件 **625** ·
  模板 **71** / body **115** · `availability: verified` **493** · 响应 Schema 行 **317** ·
  **`live.write_path_coverage()` 仍 `72 / 633`**（`model_write_ratio` **`72 / 434`**）·
  候选 **72 / 62 / 0** · blocked **501 / 438 / 31** · 留缺账本 **178** · R118 子桶 **42 / 23 / 6**。
  **新增的计数 = 接口层子桶**（路径 **13** 条 = 4 + 9；映射缺口 **517** = 271 + 246），
  与数据侧口径**分开**、**不**并入任何覆盖率分子。
- 可执行判定 = `tests/test_midas_interface_paths_p152.py`（**14** 项 + **1** 项环境门控）·
  `registry/tools/probe_interface_paths.py`（`--recon` / `--probe` / `--check` / `--summary`）·
  `docs/reports/P152_接口层添加删除编辑端到端调试与映射缺口登记_v1.0.md`。

**⑲ P153：接口层**读路径**端到端 + R126 的**裁决输入证据包** + 映射缺口分类收口（接 ⑱）**：

- **接口层读路径（主）**：与写路径**同一链路**（`MCP Tool → OperationPlan（`operations.py`）
  → Adapter（intent 分派）→ `MidasHttpClient`（护栏 + 包装键）→ MIDAS 实例`），但**零写请求**
  —— 只发 `GET` 与取报表 `POST /POST/TABLE`。**全部**读类 Operation（**8** 个 `MODEL.*.QUERY` +
  `INFO` + **6** 个取结果族 = **15** 条）在**专用空项目**上逐条取得结论：
  **2** `PASSED`（`OPE.PROJECTSTATUS` 的项目状态表**非空**：`MODEL.QUERY` / `INFO`）·
  **7** `PARTIAL`（`DB.*` 的**空块** —— L4 口径的第三态）· **6** `FAILED`
  （**5** 条 `POST.TABLE.*` 原生 `400` `[empty] Cannot generate table data as there is no
  analysis result.` + **1** 条 `RESULT.ANALYSIS.SUMMARY` 的通用入口 `POST.TABLE`
  ⇒ `STRUCTAI-3000`、**零** transport 调用）。
  ⚠️ **P157 / R129 同步（有实测依据）**：P153 / P154 时该行的成因是
  `endpoint_not_available_for_product`（`products` **不含** `GEN_NX`）；**R129 的数据更正落地**
  （`products` 补 `GEN_NX`）后**产品闸门已通过**，重测（零写）后的成因 = **`registry_mapping_not_verified`**
  （`availability: untested` ⇒ `verification_status != VERIFIED`，`docs/07` §6.11）。
  ⇒ **子桶计数不变**（**15** = **2** + **7** + **6**），**只**换成因。
  方法计数 = `{'GET': 12, 'POST': 5}` · `write_requests = 0` · 哨兵 **17** 个端点跑前 == 跑后 ·
  `residue` 空 · `aborted` 空。
  判定沿用 **L4 口径**（`docs/04` §71）：`2xx` ∧ 解包链命中（`read_root` 在响应顶层）⇒ 数据块
  非空 `PASSED` / **空块 `PARTIAL`**；`4xx` / 解包链不命中 ⇒ `FAILED`。
  ⚠️ **三个接口层事实**（已立 **R127**）：① 结果键是 **`intent`**（读 = `data["read"]`、
  取报表 = `data["result"]`），**多端点**读 Operation（`MODEL.LOAD.QUERY` 的 4 个端点）的聚合键
  会被**覆盖** ⇒ 逐端点读数**只**能取 `steps[]`；② **空块会退化成一条全 `None` 的条目**
  （`{"NODE": {}}` → `[(None, {})]` → `{"x": None, …}`，是**非空 dict**）⇒ 「空块」判据**只**看
  **原始块的形态**（`size == 0`），读回计数按**有取值**判；③ 哨兵的「编号」**只认数字键**
  （单例 / 状态表的 `DATA` / `HEAD` 会被误当编号 ⇒ 哨兵**假非空**并中止整批）。
  证据 = `registry/live/interface_read_probe.json` · 工具 = `registry/tools/probe_interface_paths.py`
  （新增 `--probe-read` / `--read-summary`）· 判定 = `tests/test_midas_interface_read_p153.py`。
- **R126 的裁决输入证据包（次）**：**71** 个数据侧模板端点逐条复算「接口层 canonical → native
  产出的 body」（判定点 = `transforms.py` 的 `TRANSFORMER_REGISTRY` + P152 证据的
  `requests[].body`）vs「手册示例 body」（判定点 = `write_templates.json` 的 `body`）的
  **字段差集**：**有**写侧 Transformer **10** / **无** **61**；**字段集缺口 4**
  （`DB.BMLD` · `DB.MATL` · `DB.PRES` · `DB.SECT` —— 手册示例用了、字段表**表达不了**）·
  **取值缺口 2**（`DB.CONS` · `DB.ELEM` —— 字段**已在** canonical 里，缺的是**值** / 形态）·
  **无 canonical 模型 61** · 已覆盖 **4**（`DB.BODF` / `DB.CNLD` / `DB.FBLD` / `DB.STLD`）。
  与 P152 §1.4 的人工结论**逐条机械对齐**（`DB.MATL` 11 个字段 / `DB.SECT` 6 个 /
  `DB.CONS` 的 `CONSTRAINT` 6 位 vs 手册 7 位 / `DB.ELEM` 的**取值**缺口）。
  **二选一方案**（**只**覆盖字段集缺口的 **4** 个端点）：**A** 扩 canonical 字段集
  （逐字段给 `canonical_hint` + `required`）· **B** 显式允许「按手册示例补原生默认值」
  （逐字段给**手册示例取值**，来源可回溯）。⚠️ 两处如实标注：**取值缺口不并入二选一**；
  **同一算法的新增发现**（`DB.BMLD` / `DB.PRES`）**只**登记字段差集，**不**声称会被拒。
  证据 = `registry/live/canonical_field_gap.json` · 工具 =
  `registry/tools/check_canonical_field_gap.py`（`--recon` / `--check` / `--summary`）。
- **映射缺口 517 的分类收口（次）**：缺口定义**未改**（**517** = **271** 契约外 + **246**
  无读回；`--check` 与 P152 的 `interface_mapping_gap.json` **逐条**一致）。**271** 个「契约外」
  按命名空间（`DB` **200** / `DESIGN` **68** / `OPE` **3**）· 能力码（`MODEL` **203** /
  `DELETE` **185** / `DESIGN` **68** / `OPERATION` **3**）· Tool 归属（`query` **271** /
  `assign` **270** / `delete` **185**）· 就绪度（`manual_example_ready` **51** /
  `schema_only` **219** / `no_request_schema` **1**）分桶 ⇒ **可纳入性**：
  **已有 canonical 模型 0** + **有手册示例 51** + **需产品裁决 220**。
  ⚠️ **`0` 是结论**：**不存在**「只声明一个 Operation 就能纳入」的端点（271 个契约外端点
  **全部**没有被任何 Operation 引用 ⇒ 也**没有** Transformer 绑定）⇒ 纳入契约一律要**新增
  canonical 模型**。证据 = `registry/live/interface_mapping_classification.json` · 工具 =
  `registry/tools/classify_mapping_gap.py`（`--recon` / `--check` / `--summary`）。
- **`app/**` 一行未改**（授权范围 = 空集；`pyproject.toml` / `migrations/` 未改 ⇒ 无新依赖、
  **未改表**）：候选改动（扩 `transforms.py` 字段表 / 补原生默认值 / 让多端点读结果不覆盖 /
  给 `POST.TABLE` 补 `GEN_NX`）分别属 **改契约**、**放宽既有裁决**、**改契约**、**需实测依据的
  数据侧改动** ⇒ 均超出本批授权，理由逐条见报告 §4。
- **计数**：本批**没有**任何既有钉住计数变化 —— 端点 **636** · Schema 文件 **625** ·
  模板 **71** / body **115** · `availability: verified` **493** / `untested` **120** /
  `unverified` **23** · 响应 Schema 行 **317** · 留缺账本 **178** ·
  **`live.write_path_coverage()` 仍 `72 / 633`**（`model_write_ratio` **`72 / 434`**）·
  候选 **72 / 62 / 0** · blocked **501 / 438 / 31** · R118 子桶 **42 / 23 / 6** ·
  **P152 的接口层写路径子桶仍 `13` = `4 + 9`** · **缺口仍 `517` = `271 + 246`**。
  **新增的计数 = 接口层**读**路径子桶**（**15** 条 = **2** + **7** + **6**）+ R126 证据包
  （**71** = **10** + **61**；字段集缺口 **4** / 取值缺口 **2**）+ 缺口分类
  （**271** = **0** + **51** + **220**），与数据侧口径**分开**、**不**并入任何覆盖率分子。
- 可执行判定 = `tests/test_midas_interface_read_p153.py`（**19** 项 + **1** 项环境门控）·
  `docs/reports/P153_接口层读路径端到端与R126裁决输入证据包_v1.0.md`。

**⑳ P154：R126 裁决 **A′** 落地（接口层写路径 `4/13` → **`11/13`**）+ **R128**（`DB.CONS` 请求体形状）
+ **R129**（`POST.TABLE` 路由存在）（接 ⑲）**：

- **R126 裁决 A′ 落地（主）**：按 `docs/reports/P0_裁决清单_v1.0.md` 的 **D1 = A′**，**只**把
  `DB.MATL` **11** + `DB.SECT` **6** = **17** 个原生字段纳入 canonical（canonical 名 = P153 证据包的
  `canonical_hint`）；`DB.BMLD`(4) / `DB.PRES`(1) **延后**。
  ⚠️ **`app/**` 的授权范围 = 仅 `app/infrastructure/adapters/midas/transforms.py` 的 2 张字段表**：
  17 个 native 叶子**全部**已在数据侧请求 Schema 里声明（`fields_for_path()` 逐条可查）⇒
  **不**需要改 `registry/**`；字段表**只**声明映射、**没有**任何默认值（**不**违反「不臆造字段」）；
  未新增 / 未改任何 Operation（**未**改 9 Tool Contract）。
  **实测**（GEN NX 专用空项目，**3** 块 5 / 5 / 3 + 块间只读健康检查均 `200`）：
  `registry/live/interface_path_probe.json` **13** 条 = **11** `PASSED` + **2** `FAILED`（P152 时 `4 / 9`）——
  `DB.MATL` / `DB.SECT` / `DB.ELEM` 的**添加 / 编辑 / 删除**全部 `PASSED`；**零残留**、`aborted` 空。
  顺带修掉**两处探针缺陷**（**不是**契约问题）：① 前置节点**几何**（两节点同坐标 ⇒ 原生
  `400`「单元 1 的几何形状不正确」）；② `DB.CONS` 缺 `group_name`（canonical 字段表里**一直有**）。
  证据 = `registry/live/canonical_field_gap.json`（重算：字段集缺口 **4 → 2** · 取值缺口 **2 → 3** ·
  已覆盖 **4 → 5**）· 判定 = `tests/test_midas_interface_contract_p154.py`（**16** 项 + **1** 项门控）。
- **R128（新，如实留缺）**：`DB.CONS` 的 `Assign` **外层键必须是「该支承所在的节点编号」**，且条目要
  套在**内层 `ITEMS`** 里 ⇒ 正确形状 = `{"Assign": {"<节点编号>": {"ITEMS": [<条目>]}}}`；
  接口层当前产出 `{"Assign": {"ITEMS": […]}}`（**缺外层编号键**）⇒ 原生 `400 Wrong Field`。
  ⚠️ **位数不是成因**（D2 已收口）：A/B 三变体（`"111000"` / `"1111000"` / 6 位且省略 `GROUP_NAME`）
  **全部 `400`** ⇒ **不必**扩 `RW`。
  ⚠️ **假成功陷阱**：外层键**不是**存在的节点编号时原生 **`200` 却什么都不建**（只看状态码会把
  「没建」当成「建好了」，与 **R119** 的「`DELETE` 假成功」同形）。
  **修复点**在 `MidasHttpClient` 的请求构造（`is_items_style()` 一族）——**属 `app/**` 改动，待新授权**；
  且**必须**同时复核其它 `ITEMS` 形态端点（`DB.CNLD` / `DB.PRES` …）。
  证据 = `registry/live/boundary_shape_probe.json`（形状 A/B **5** 变体 = **2** `PASSED` + **3** `FAILED`）·
  工具 = `registry/tools/probe_boundary_shape.py`（`--probe` / `--check` / `--summary`）。
- **R129（新，只读核实）**：`POST /POST/TABLE` 在 GEN NX 上**路由存在** ——
  `OPTIONS` → `200 Allow: POST`；`POST /POST/TABLE` → **业务级 `400`**（`[empty] Cannot generate
  table data as there is no analysis result.`），而对照 `POST /POST/NOSUCHTABLE` → **`404`**
  ⇒ `RESULT.ANALYSIS.SUMMARY` 的 `STRUCTAI-3000` 来自**数据侧 `products` 声明**（不含 `GEN_NX`），
  **不是**原生不可用。**恢复条件** = 按实测更正 `products`（数据侧改动，需实测依据 + 显式裁决）。
- **计数**：**本批变化的** = 接口层写路径子桶（`4 / 9` → **`11 / 2`**）· R126 证据包
  （字段集缺口 `4 → 2` · 取值缺口 `2 → 3` · 已覆盖 `4 → 5`）。
  **不变的**：端点 **636** · Schema 文件 **625** · 模板 **71** / body **115** ·
  `availability: verified` **493** · 响应 Schema 行 **317** · 留缺账本 **178** ·
  **`live.write_path_coverage()` 仍 `72 / 633`**（`model_write_ratio` **`72 / 434`**）·
  R118 子桶 **42 / 23 / 6** · 缺口 **517** = **271** + **246** · 缺口分类 **271** = **0** + **51** + **220** ·
  接口层读路径子桶 **15** = **2** + **7** + **6**（按新字段表刷新读数，计数不变）。
- 另：`tests/test_midas_write_templates_p139.py` 的「特征取值」清单**分类错误**已修正
  （`vSIZE` 是**键名**不是取值）+ **新增自检**（清单每项必须是模板取值、且不是键名）⇒ 判定**变强**。
- 可执行判定 = `tests/test_midas_interface_contract_p154.py`（**16** 项 + **1** 项环境门控）·
  `docs/reports/P154_R126裁决A落地与DB_CONS形状_v1.0.md`。

**㉑ P155：**R128 的修复**（`ITEMS` 形态的 `Assign` 带外层**编号键**）+ 探针加固（哨兵不可读 ⇒ **不盲写**）
（接 ⑳）**：

- **R128 的修复（主，已获授权）**：接口层 `ITEMS` 形态的 `Assign` 改为发
  `{"Assign": {"<编号>": {"ITEMS": […]}}}`（**外层编号键**）—— 与**数据侧一直在用、已实测可用**的形状
  **对齐**（`tests/test_midas_write_coverage_p142.py:471` 的 `{"Assign": {"1": {"ITEMS": [{"ID": 1}]}}}`）。
  ⚠️ **授权范围 = 2 个文件**：`app/infrastructure/adapters/midas/client.py`（`_wrap` 的 `ITEMS` 分支）+
  `adapter.py`（`_write` 的 `ITEMS` 分支改为**每条一个请求** + 新增 `_item_key`）。
  **键由代码导出**（**不**臆造）：取该 Transformer 字段表里**映射到原生 `ID`** 的 canonical 字段 ——
  `DB.CONS` → **`node_id`**（支承的编号就是它所在节点的编号），节点 / 梁 / 面荷载 → `id`；
  **取不到即明确失败**（`STRUCTAI-1200`，`reason = assign_item_key_missing`），**不**回落 `"1"`
  （外层键无效时原生会**静默 `200` 却什么都不建** = R128 的假成功陷阱）。
  **适用面**（`ITEMS` + `Assign`）**恰好 4 个**：`DB.CONS` · `DB.CNLD` · `DB.BMLD` · `DB.PRES`
  （逐条断言**都**有映射到原生 `ID` 的字段）。
  ⚠️ **端到端复验（13/13）受环境阻塞**：修复落地时 `gen-local` **不可达**（`WinError 10061`）
  ⇒ `registry/live/interface_path_probe.json` 仍是 **P154 的修复前快照**（**11** + **2**）；
  **恢复后必须重跑** `--probe`（预期 `{'PASSED': 13}`）并**只**同步数字。
- **探针加固（实测事故驱动；其中一处是**安全**缺陷）**：一次实例不可达的 `--probe` 暴露 ——
  ① ⚠️ **哨兵读不到时照常发写请求**（`sentinel()` 把传输失败记成 `ids: []` ⇒ 被当成「跑前为空」）⇒ **盲写**；
  ② 块间健康检查的**传输失败**让异常把整批打崩 ⇒ **证据文件没写成**；③ 中止时**覆盖**既有证据 ⇒
  把好证据冲成一份失败快照。**修法**：**任一**被触碰端点**读不到** ⇒ **中止、一个请求都不发**
  （依据 P138c「读不到就**不盲写**」；读路径为「全部不可读」）· 健康检查传输失败归 `aborted`（**不**抛）·
  `_write_evidence` 在 `aborted` 非空且**已有**文件时**保留**既有证据（两个探针工具都加）。
  **已实测验证**（实例当时正好不可达）：中止信息 + **零请求** + 证据**逐字节未变**（`git status` 干净）。
- **计数**：本批**没有**任何钉住计数变化 —— 端点 **636** · Schema 文件 **625** · 模板 **71** / body **115** ·
  `availability: verified` **493** · 响应 Schema 行 **317** · 留缺账本 **178** ·
  **`live.write_path_coverage()` 仍 `72 / 633`**（`model_write_ratio` **`72 / 434`**）·
  R118 子桶 **42 / 23 / 6** · 缺口 **517** = **271** + **246** · 缺口分类 **271** = **0** + **51** + **220** ·
  接口层写路径子桶 **13** = **11** + **2**（**修复前快照**，待复验）· 读路径子桶 **15** = **2** + **7** + **6**。
  ⇒ `registry/**` 数据文件**一行未改**、**未**重生成证据。
- **仍未闭环**：R128 的 **13/13 复验**（实例恢复后跑）· `DB.BMLD` / `DB.PRES` 的形状**未实测**
  （需构件前置，留到 P2）· **D4 的第二个专用项目预留槽位**（⇒ `§13.5` 旗舰五步链仍未跑通、**R127a** 未闭环）·
  **R129** 的数据更正待裁 · **D5** 未裁 · 冻结清单不变。
- 可执行判定 = `tests/test_midas_interface_shape_p155.py`（**10** 项 + **1** 项环境门控）·
  `docs/reports/P155_R128形状修复与探针加固_v1.0.md`。

**㉒ P156：R128 的**端到端复验**（形状修复 ✓）+ **D2 的更正**（`CONSTRAINT` **必须 7 位**）（接 ㉑）**：

- **R128 的端到端复验（形状修复已确认生效）**：实例重启后全量重跑 `--probe`
  （**3** 块 5 / 5 / 3 + 块间只读健康检查均 `200`；跑前哨兵全空、**零残留**）⇒ 接口层现在发
  `{"Assign": {"1": {"ITEMS": [{"GROUP_NAME": "", "ID": 1, "CONSTRAINT": "111000"}]}}}`（**外层编号键** ✓），
  原生文案从**形状级** `Wrong Field` 变成**取值级** **`[错误] 约束条件输入有错误。`**
  ⇒ **R128（形状）闭环**；写路径仍 **13** 条 = **11** `PASSED` + **2** `FAILED`（只剩 `DB.CONS`）。
- **D2 的更正（⚠️ 如实更正一处错判）**：P154 的「位数不是成因」是**混淆实验** —— 三变体全用了当时
  **未修的形状** `{"Assign": {"ITEMS": […]}}`（该形状**无论位数都 `400`**）⇒ 位数被**形状混淆**。
  **形状修好后**重测（`registry/live/constraint_value_probe.json`，**4** 变体，形状固定为编号键控）：

  | `CONSTRAINT` | 长度 | 原生 |
  | --- | --- | --- |
  | `"11100"` | 5 | `400 Unknown Error` |
  | `"111000"`（**接口层当前产出**） | 6 | `400 约束条件输入有错误` |
  | `"1110000"` | **7** | **`200` + 落库** |
  | `"1111000"`（手册示例） | **7** | **`200` + 落库** |

  ⇒ 原生要求**恰好 7 位**（`DX,DY,DZ,RX,RY,RZ,RW`）；`RX` 取值**无关**。
  ⚠️ 而 `BoundaryTransformer` **结构上**只能产出 **6** 位（`BOUNDARY_FLAGS` 恰好 6 个；`RW` **明确不臆造**）
  ⇒ 这是 **canonical 模型少一个自由度**（**不**在端点 / 护栏 / 形状 / 探针参数）⇒ **D2 重开**：
  **A** 加 canonical `rw`（**推荐**，与 A′ 同类）· **B** 固定补 `"0"`（**臆造**取值，需逐字段豁免）。
  **未**裁 ⇒ `DB.CONS` 的添加 / 编辑 / 删除三条**继续留缺**（写路径停在 **11 / 13**）。
- **计数**：本批**新增** = `CONSTRAINT` 取值子桶（**4** 变体 = **2** + **2**，被接受的长度 = **7**）；
  **不变** = 端点 **636** · Schema 文件 **625** · 模板 **71** / body **115** · `availability: verified` **493** ·
  响应 Schema 行 **317** · 留缺账本 **178** · **`write_path_coverage()` 仍 `72 / 633`** ·
  R118 子桶 **42 / 23 / 6** · 缺口 **517** = **271** + **246** · 分类 **271** = **0** + **51** + **220** ·
  写路径子桶 **13** = **11** + **2** · 读路径子桶 **15** = **2** + **7** + **6**。
  **同步** = P152 / P153 / P154 三个测试文件的**文案集与断言**（**只**改数字 / 注释与「钉住修复前状态」的
  那一处，新断言**更强**）+ `canonical_field_gap.json` 按修好后的证据重算（计数不变）。
- 可执行判定 = `tests/test_midas_constraint_value_p156.py`（**10** 项）·
  `docs/reports/P156_R128复验与D2更正_v1.0.md`。

**㉓ P157：D2 = A 落地（接口层写路径 `11/13` → **`13/13`**）+ 旗舰五步链的两处**结构成因** +
R129 的数据更正（接 ㉒）**：

- **D2 = A 落地（主；`app/**` 授权范围 = 恰好 **1** 个文件）**：按 `docs/reports/P0_裁决清单_v1.0.md` §7 的
  **D2 = A**，给 `BoundaryTransformer` 加第 **7** 个自由度：`BOUNDARY_FLAGS` **6 → 7**（追加 `rw`，
  顺序 = `DB.CONS` Schema 描述 `(DX,DY,DZ,RX,RY,RZ,RW)`）· `constraint_string` 文档化「位数 = 传入的
  自由度个数」· `constraint_flags` 增 `count`（默认 = `len(BOUNDARY_FLAGS)` = **7**）。
  ⚠️ **授权范围 = `app/infrastructure/adapters/midas/transforms.py` 一个文件**（**未**改 canonical 字段表 ·
  **未**改 9 Tool Contract · **未**改表 · **未**新增依赖）；**调用方显式给 `rw`**，**缺** ⇒
  `boundary_flags_incomplete`（**不**给默认值、**不**代填 `"0"` —— **方案 B 被否**）。
  **实测**（GEN NX 专用空项目，**3** 块 5 / 5 / 3 + 块间只读健康检查均 `200`）：
  写路径 **13** 条 = **13** `PASSED` + **0** `FAILED`；`DB.CONS` 现在发
  `{"Assign": {"1": {"ITEMS": [{"GROUP_NAME": "", "ID": 1, "CONSTRAINT": "1110000"}]}}}`（**7** 位）
  ⇒ 原生 **`200` 且落库**；**零残留**、`aborted` 空。
- **R126 证据包的**取值缺口**因 ① 而关闭（有实测依据）**：`DB.CONS` 由 `value_gap` 移入 `covered`
  ⇒ **取值缺口 3 → 2**（余 `DB.ELEM` / `DB.MATL`）· **已覆盖 5 → 6**；字段集缺口仍 **2**
  （`DB.BMLD` / `DB.PRES`）· 模板端点仍 **71 = 10 + 61**（`--recon` 复算）。
- **旗舰五步链（`docs/07` §13.5）：真机**仍未跑通** —— 成因已定位（**R131 材质面已闭环** / **R132** 待授权）**：
  新工具 `registry/tools/probe_flagship_chain.py`（**两个阶段**；判据**全部**取接口层响应；
  **数值不硬编码**；只碰自建编号 + 逆序清理 + 再读确认；**残留 = 0**、哨兵跑前 == 跑后**全空**）：

  | 阶段 | 步 | 结果 | 原生成因 |
  | --- | --- | --- | --- |
  | **A（§13.5 逐字）** | ① `BUILD.COLUMN` | `FAILED` | `POST /DB/MATL` → **`400 Wrong Field`**（**R131**） |
  | **B（替代前缀 ①′ + ②–⑤）** | ①′ 四个原子 Operation | **`PASSED` ×5** | —— |
  | | ② `MODEL.LOAD.ASSIGN` | `FAILED` | `POST /DB/CNLD` → **`400 Not Found Key`**（**R132**） |
  | | ③④⑤ | `NOT_RUN` | 链在 ② 停止（**有界**，**不**硬跑） |

  * **R131（⚠️ 结论经用户证据更正；材质面已闭环）**：`BUILD.COLUMN` 的材质载荷**混用两条互斥路线** ——
    声明 `TYPE="STEEL"`（**规范库**路线）却给"用户自定义"的属性、且**一个库判据都不给**
    （`p_type` / `standard` / `db` / `code`）⇒ `400 Wrong Field`。
    ⚠️ **不**是"canonical 少 11 个字段"（原记**作废**）、**不**是 API 问题。依据 = **上游手册 `db/MATL`
    的 3 个示例**（`Standard`（规范库）· `Isotropic - User Defined`（`TYPE=USER`+`P_TYPE=2`）·
    `Orthotropic - User Defined`（`TYPE=USER`+`P_TYPE=3`+`*_M`）⇒ **`TYPE`+`P_TYPE` 决定哪组属性有效**）
    + 用户在 GEN NX「材料数据」对话框上的实测（**钢材属性由规范库带出、不能自定义**）。
    **用户裁决 = B**（**不**改 `app/**`；建模走 `MODEL.MATERIAL.ASSIGN`；钢号 **`Q355`**）⇒ 修正后的
    **规范库** body（`STANDARD="GB50017-17(S)"` · `DB="Q355"`（= **钢号**）· `CODE=""` · `P_TYPE=1` ·
    `ELAST=206000000`（**kN/m²**））**实测 `200` 且落库** ⇒ ①′ 五步全 `PASSED`。
  * **R132（✅ 已闭环，用户裁决 = A）**：`MODEL.LOAD.ASSIGN` 的编排**声明**了 `DB.STLD` 的
    `write_load_case` 步，但 `select_steps` **只**选出该荷载类型那一步 ⇒ `DB.STLD` **永不**被执行；
    而 `MODEL.LOAD.DELETE` **能删**它（**不对称**）⇒ **接口层没有**任何 Operation 能**创建**工况。
    ✅ **修法（不动 9 Tool Contract）**：`select_steps` 在调用方**显式**给了 `load_case_definition` 时
    返回 `(DB.STLD 步, 荷载步)` ⇒ ② **`PASSED`**（`POST /DB/STLD` → `POST /DB/CNLD`）。
  * **R134（新，已闭环）**：§13.5 要求「柱底固定」，而 §6.5 给 `BUILD.COLUMN` 的组合**不含** `DB.CONS`
    （`BUILD.STEEL_FRAME` 却**含** ⇒ **§6.5 内部不一致**）⇒ 没有它 `POST /DOC/ANAL` → `400`
    **`[错误] 边界条件 没有定义。`**。①′ 补第 6 步 `MODEL.BOUNDARY.ASSIGN`（`CONSTRAINT = "1111110"`，
    **7** 位）后 ③ **`PASSED`** —— 这也是 **D2 = A 在真机上的第一次实际使用**。
  * **R135（新，已闭环）**：取结果**不能**带 `LOAD_CASE_NAMES` 过滤 —— 带过滤时原生回 **`200 {}`**
    （⇒ `parse_table` 报 `result_shape_invalid`；**有界重试 6 次全 `{}`**，**不**是没算完）；
    去掉过滤后同一端点返回真表 ⇒ ④ **`PASSED`** 并取到**真实数值**。
  * **R136（✅ 已闭环，用户裁决 = B）**：⑤ `DESIGN.STEEL` 的 `CODE-TABLE` → `400`，**根因 = 验算荷载组合不存在**（MIDAS 弹窗原文）。荷载组合端点（`DB.LCOM-*`）**都 `verified`** 但
    **零引用** ⇒ **新增一等 Operation `MODEL.LOAD_COMBINATION.ASSIGN`**（Operation **69 → 70**；
    6 条 steps 按 `combination_kind` 分派；**不**新增 Tool、**不**扩能力码），并把删除并入
    `MODEL.LOAD.DELETE`。⇒ 契约缺口**已闭**，但组合体被原生拒（见 **R137**）。
  * **R137（✅ 已闭环）**：`POST /DB/LCOM-STEEL` 照手册示例（`ANAL: "CS"`）→ **`400` `Unknown Error`**；
    **只读**读回官方验证模型 `Static-01.mgbx` 的 `GET /DB/LCOM-GEN` ⇒ 真值 **`ANAL = "ST"`**
    （手册的 `"CS"` 不被接受）⇒ 改后 **`200`** 且再读确认在。⚠️ 组合是**分析的输入** ⇒ 必须先于分析。
  * **R138（新，**未**闭环）**：⑤ 的 `CODE-TABLE` **复用**了 `CODE-ANAL` 的 Transformer ⇒ 请求体
    `{"Assign": {"1": {}}}`，而该端点要 **`Argument`** + **必填** `TABLE_TYPE`/`ELEMS` ⇒ **`400`**；
    修它要**新增 Transformer**（属 `app/**`，须授权）。
  * ⚠️ **铁律 ⓪（P160c 立，最高优先级）**：**判据必须是「效果」，不能是「状态码」** ——
    原生**静默 `200` 却什么都不做**已实测**四次**（R128 / R145 / R146 / P160c 事故 A）；
    **落盘 ⇒ 看文件**（存在 + 大小 / mtime）· **写模型 ⇒ 读回来** · **改配置 ⇒ 再读一次**。
  * **R139（✅ P158 已收口）**：`DOC.NEW` 也**未** `verified` ⇒ 接口层**无法**重置项目
    （Contract Test 口径下实测 `POST /gen/DOC/NEW` → `200`）。
  * **R140（❌ 结论已撤回）**：曾判「`DESIGN.*` 会驱动界面 ⇒ 不能无人值守跑」—— **无依据**。
    `CODE-ANAL` 照手册示例单独发 ⇒ **`200` `success`**；崩溃的**真实**成因是我们**请求写错**。
    ✅ 已加 `spec_guard`（发请求**前**拦非法枚举）防复发。
  * **R141（✅ 已闭环）**：`DESIGN.STEEL` 的**前四步是「配置」**（手册方法 `GET, PUT, DELETE`：
    `DSTL` 设规范 · `DCO` 设选项 · `DCTL` 设框架 · **`MEMB` 指派构件**）；原编排当 `GET` 读
    ⇒ 设计从未被配置 ⇒ 验算对话框报 `setting unit` + 崩溃。已改为 **PUT 配置 → 验算 → 取表**
    ⇒ 旗舰链 **11/11 `PASSED`**。
  * **R142（✅ 已闭环）**：设计结果表的**关键列名**是 MIDAS 规范校核表的原名 ——
    **利用率 = `RatPc`**、**结论 = `CHK`**、**组合号 = `LCB`**（原别名表没有它们 ⇒ `ratio`/`status`
    为 `None`、**出计算书要用的数就丢了**）。已按**实测**补齐别名 + 5 对「需求 vs 承载力」
    （`Pu`/`pPn`、`Muy`/`pMny`、`Muz`/`pMnz`、`Vuy`/`pVny`、`Vuz`/`pVnz`）⇒ 取回
    `ratio=1.814` · `status=NG` · `Pu=-500000`/`pPn=275668` …。
  * **R133（✅ P159 已闭环）**：`DB.MATL` 的**单位口径**在 canonical 侧**未**定义 —— 手册 / 对话框是
    `kN/m²` / `kN/m³`，而写路径探针发的是 Pa / kg·m⁻³（**1000× / 100×**）；原生**不**校验量级 ⇒
    两者都 `200`，但**工程含义不同** ⇒ 写路径 `DB.MATL` 的 `PASSED` 证明的是**形状 / 字段集**被接受，
    **不**证明取值工程正确。
  * ⚠️ **R132 属 `app/**`，本批**未**获授权 ⇒ 如实留缺**；**未**在空项目上跑分析
    （③ 未运行 ⇒ **没有**分析结果 ⇒ `analysis_result_persists = None`）。
- **R129 的数据更正（已获用户显式裁决）**：`registry/common/post/TABLE.yaml` 的 `products` →
  `[CIVIL_DESIGNER, CIVIL_NX, GEN_NX]`（**只**改 `products`）；`sync_manifest` 预演 **1** → `--write` → 再预演 **0**。
  **连锁**：`write_capable_endpoints` **576 → 577** ⇒ 缺口 / 分类证据重算（缺口仍 **517 = 271 + 246**）；
  **读路径重测（零写）**后 `RESULT.ANALYSIS.SUMMARY` 的成因由 `endpoint_not_available_for_product`
  变为 **`registry_mapping_not_verified`**（产品闸门**已通过**；下一个闸门 = `availability: untested`）
  ⇒ **读路径子桶计数不变**（**15** = **2** + **7** + **6**），**只**换成因；
  `MODEL.BOUNDARY.QUERY` 的读回键集**新增 `rw`**。
- **R130（新，`app/**`、**未**授权）**：`ITEMS` 形态端点的**读回**把外层 `ITEMS` 包装体当成条目交给
  Transformer ⇒ canonical 取值**全 `None`**（只有由**编号键**补的 `id` 有值）；**不**影响写路径判定
  （判定 = 「该编号**在**读回里」），但**限制**其证明力。
- **计数**：**变化的** = 写路径子桶（`11 / 2` → **`13 / 0`**）· R126 证据包（取值缺口 `3 → 2` ·
  已覆盖 `5 → 6`）· `write_capable_endpoints`（`576 → 577`）。
  **不变的** = 端点 **636** · Schema 文件 **625** · 模板 **71** / body **115** · `availability: verified` **493** ·
  响应 Schema 行 **317** · 留缺账本 **178** · **`write_path_coverage()` 仍 `72 / 633`**
  （`model_write_ratio` **`72 / 434`**）· R118 子桶 **42 / 23 / 6** · 缺口 **517** = **271** + **246** ·
  分类 **271** = **0** + **51** + **220** · 读路径子桶 **15** = **2** + **7** + **6** ·
  `CONSTRAINT` 取值子桶 **4** = **2** + **2**（被接受长度 **7**）。
- 可执行判定 = `tests/test_midas_constraint_rw_p157.py`（**16** 项）+
  `tests/test_midas_flagship_chain_p157.py`（**11** 项）·
  `docs/reports/P157_D2落地与旗舰五步链实测_v1.0.md`。

### 8.15 P161：外部证据（NXSDK）裁决 —— `products` 归属更正 33 条 + 3 处字段类型更正

**来源**：外部开源项目 [`Dennis5882/MIDAS-API-NX-SDK`](https://github.com/Dennis5882/MIDAS-API-NX-SDK)
（MIDAS IT 在职员工基于真机验证维护的双语言 SDK，**非**官方产品）。评估与逐条比对见
[`docs/nxsdk_review/00_评估与查漏补缺报告_v1.0.md`](../docs/nxsdk_review/00_评估与查漏补缺报告_v1.0.md)；
证据清单 [`docs/nxsdk_review/nxsdk_product_corrections.json`](../docs/nxsdk_review/nxsdk_product_corrections.json)
（**54** 条候选 = A **21** / B **21** / C **12**）。

> ⚠️ **口径**：外部证据是**待裁决输入**，**不是**判据。本批**只**落地证据最硬的两级
> （A + C），**B 级 21 条一律未动**（见下「未落地」）。全部改动**只**碰 `products` 与
> 3 处字段 `type`；`availability` / `verified_on` / `unavailable_on` / `enabled` **一行未改**。

**A 级（21 条）：Hyper-S `-M1` 族 `products` 由 `[GEN_NX]` 改为 `[CIVIL_NX]`**

四条独立证据同向：

| # | 证据 | 内容 |
| --- | --- | --- |
| 1 | **我方 `instances.yaml` 第 16 行** | gen-local「**缺 21 个 Hyper-S 变体**」—— 而这 21 条**全部**带 `unavailable_on: ["gen-local"]` |
| 2 | 对方 `docs/CLAUDE.md` | **"Hyper-S (`-M1`) endpoints are Civil NX only"**，`db/base.py` 设 `HYPER_S_ONLY` |
| 3 | 对方 `docs/live_verification_notes.md` | `HYPER_S_ONLY` = **13 implemented + 8 undocumented-stub** = **21**，live **两次**确认 "civil GET ok, gen GET fails" |
| 4 | 对方 `schema/hyper-s-info.json` | 以 `product: "civil"` 单独抓取；384 份契约中 18 个 `-M1` **全部** `products: [civil]` |

⚠️ **与 §8.2 的关系**：§8.2 对「声明的产品在其**唯一实例**上 404」的既定处置是
**不动**（先例 = `DB.UFTR` / `DB.UTBL`：摘除会让 `products` 变空）。本批**不主张**
这 21 条违反 §8.2；**主张的是**：Hyper-S 有 §8.2 先例所没有的**产品级归属证据**
（对方在 Gen NX 2026 v2.2 上复测仍为 Civil-only）。同形的 24 条里，另 3 条
（`DB.UFTR` / `DB.UTBL` / `OPE.STORPROP`）**保持不动**。

**C 级（12 条）：`products` 由 `[CIVIL_NX, GEN_NX]` 收为 `[GEN_NX]`**

`DB.REBB` · `DB.REBC` · `DB.REBR` · `DB.REBW` · `DESIGN.RC.KDS-41-20-2022.{REBB,REBC,REBR,REBW,TRFT,ULCT}` ·
`DESIGN.STEEL.KDS-41-30-2022.ULCT` · `OPE.STORYPROP`。

判据（**可复算**）：这 12 条的 `verified_on` **只有** `gen-local`、`unavailable_on` **为空**
⇒ `CIVIL_NX` **从未被实测**；而对方 `GEN_ONLY` 家族经**两次独立复现**
（其自身 `scripts/live_readonly_sweep.py --product civil` + 另一台机器/会话的独立扫描），
并被其 `tests/db/test_civil_v22_gen_only_products.py` 参数化钉住。
⇒ **摘除的是一个从未被验证过的声明**（保守方向）。

**3 处字段类型更正**（服务端 `/info` **与**对方**已复核契约**双证据同向才动）：

| 端点 | 字段 | 改动 | 依据 |
| --- | --- | --- | --- |
| `DB.SLANOP` | `OPT_STRADD` | `integer` → **`boolean`** | 服务端描述 **"BS Straddling Lane Boolean"**；对方契约 `provenance: info_schema` |
| `DB.REBC` | `ITEMS[].HOOP_TYPE` | `string`(+`oneOf` 字符串常量, `default: "Ties"`) → **`integer`** | 服务端描述 **"Hoop Type (1=Tied, 2=Spiral)"**；对方契约 `provenance: live_corrected`。⚠️ **不**声明 `enum` —— `/info` 未声明，含义是 description 里的散文，**从散文里读出枚举就是发明门控** |
| `DB.REBR` | `ITEMS[].HOOP_TYPE` | 同上 → **`integer`** + **`enum: [1, 2]`** | 同上，且该端点的 `/info` **声明了** `enum` |

⚠️ 三处都**删除**了手册的 `default: "Ties"` —— 字符串默认值在 `integer` 字段上不成立。

**未落地（B 级 21 条，需我方 CIVIL_NX 实例复测）**：服务端 `/info` 在 CIVIL_NX 上有 Schema
而我方只声明 `GEN_NX` 的 13 条 `/db/*`（`DB.DCTL` `DB.DSTL` `DB.EPSE` `DB.ESSF` `DB.LENG`
`DB.LLAN` `DB.LLANID` `DB.LTSR` `DB.MBTP` `DB.MEMB` `DB.POSL` `DB.POSP` `DB.WMAK`）
+ 8 条非 `/db/*`。**理由**：`/info` 是**产品族级**自述，我方 `products` 是**实例级**实测结论，
二者可同时为真（构建版本差异）⇒ 依 §8.2 需**我方实例实测 + 显式裁决**。
⚠️ 其中 `DB.POSP` 另需 `product_overrides.CIVIL_NX`：两产品记录**不同**
（Civil 多 `STR_HEIGHT` / `STR_WIDTH`），即 **MD-46** 形态。

**未采纳的 4 处类型分歧**（证据不足或与已复核契约相反）：`DB.EPSE` / `DB.EPST` 的
`LOADING_AREA_GROUP`（对方契约 `provenance: manual` 支持 `integer`，与服务端 `/info` 的
`string` **相反** ⇒ 契约站在我方）· `DB.RPSC` 的 `LBAR_INC_FC`（我方 `number` / 服务端
`boolean` / 契约 `integer` ⇒ **三方差歧**）· `DB.NLLP` 的 `SEIS_TYPE`（仅 `/info` 出现 ⇒ 单来源）。

**⚠️ 横切修复（独立动机，非本批判定）：`registry/tools/*.py` 的控制台编码守卫**

**21** 个工具原本在 Windows gbk 控制台下打印中文/符号时 `UnicodeEncodeError`，
使 **13** 个既有用例失败。守卫**必须放在 `if __name__ == "__main__":` 块内** ——
测试用 `exec_module()` 装载工具模块，**模块级** `sys.stdout.reconfigure()` 会改写
**pytest 的捕获流**，破坏其后所有用例的 capture（实测：75 个 ERROR）。

**计数（本批变化 / 不变）**

| 项 | 变化 |
| --- | --- |
| `products` 含 `CIVIL_NX` | **505 → 514**（+21 −12） |
| `products` 含 `GEN_NX` | **580 → 559**（−21） |
| 写路径候选集 `GEN_NX` / `CIVIL_NX` | **78 / 68 → 78 / 68**（**不变** —— 被移动的端点**无一**曾是候选） |
| 写路径 blocked `GEN_NX` / `CIVIL_NX` | **495 / 431 → 474 / 440** |
| 映射缺口（`product_key = GEN_NX`） | `gap_total` **510 → 489**；`write_capable_endpoints` **577 → 556** · `three_step_endpoints` **301 → 280** · `mapped_endpoints` **68（不变）** |
| 缺口分类 | `gap_total` **510 → 489** = 契约外 **264 → 243** + 无读回 **246（不变）**；三分类 **0** + **51** + **192**（需产品裁决 **213 → 192**）；`by_availability` 的 `unverified: 21` 桶**整体消失**（这 21 条离开了 GEN_NX 口径） |
| 缺口分桶（`by_namespace` / `by_capability` / `by_tool_map`） | `DB` **193 → 172** · `DELETE` **179 → 158** · `MODEL` **196 → 175** · `assign` **263 → 242** · `query` **264 → 243** · `schema_only` **212 → 191**（**全部 −21**） |
| **不变** | 端点 **636** · Schema 文件 **625** · 桶分布（`common` **370** / `products/gen_nx` **100** / `products/civil_nx` **17** / `products/civil_designer` **24** / `design` **125**）· `availability` 三档 **503 / 23 / 110** · 模板 **71** / body **115** |

**落地方式（可复现）**

```bash
python registry/tools/import_nxsdk_evidence.py --tier A --write   # 21 条 Hyper-S
python registry/tools/import_nxsdk_evidence.py --tier C --write   # 12 条 GEN_ONLY
python registry/tools/sync_manifest.py --write                    # 派生 manifest（33 处）
python registry/tools/probe_interface_paths.py --recon            # 缺口证据重算
python registry/tools/classify_mapping_gap.py --recon             # 分类证据重算
```

工具**默认预演**、**幂等**、`--tier` 分级、`--check` 断言；`sync_manifest` 落盘后再预演 **0**。

**可执行判定** = `tests/test_midas_nxsdk_products_p161.py`（**11** 项：Hyper-S 归属与全库不变量 ·
GEN_ONLY 收口 · B 级**故意未落地** · `availability` 三档未动 · 3 处类型更正 ·
4 处未采纳分歧）· 另**同步** `p142` / `p144`–`p148` / `p149` / `p149e` / `p150` / `p151` /
`p152` / `p153` / `p154` / `p155` / `p156` / `p157`（**只**改钉住数字与「整文件未改」→
「指定字段未改」的口径收窄；断言**未**放宽）· `p119_p123` 的求解器门控用例
（原取 `GEN_NX` **恰好编码了**被更正的那个错误归属 ⇒ 改为 `CIVIL_NX` 并断言 `GEN_NX` 被拒）。

### 8.16 P162：外部证据裁决（第二批）—— `/db/REB*` 家族形状重建 + `/db/PRES` 必填性

**承接 §8.15**。本批处理**字段结构类**勘误（MD-17 / MD-34 / MD-45），
判据统一为「服务端 `GET /info` **与**对方**已复核契约**同向 **且** 有**实测的形状级拒绝**」。

#### 8.16.1 🔴 `/db/REB*` 家族：手册的字段名**全部不对**（MD-34）

四个端点的 `ITEMS` 条目形状按**原生短键**重建。判据是三方一致：

| 端点 | 我方（改前） | `GET /info` | 对方契约 | 实测的形状级拒绝 |
| --- | ---: | ---: | ---: | --- |
| `/db/REBB` | 11 字段（长名） | **45** 路径 | **45** 路径（逐路径一致） | A-03：多种载荷**全部** `Wrong Field`；短键到达域检查 |
| `/db/REBC` | 9 字段 | **22** | **22** | A-02：手册单对象 → `Wrong Field`；数组形状 → 域错误（**形状被接受**），POST→GET→PUT→DELETE→GET 往返成功 |
| `/db/REBR` | 8 字段 | **17** | **17** | A-04：长键 → `Wrong Field`；短键 → 域检查 |
| `/db/REBW` | 12 字段（**一个都不对**） | **20** | **20** | A-01：`GET` 回显 + `/info` + **`PUT` 往返（改→验证→改回）** 三次确认 ⇒ 是**写契约** |

**关键更正**：

- **`MAIN_BAR`（单对象）+ 顶层 `DO`** → **`vMAIN_BAR`（数组）**，覆盖层在每条目内叫 **`D0`**
  （**数字零**，不是字母 O）。`/db/REBC`、`/db/REBR` 两处。
- **`CREATE_SUB_SECTION` / `ELEMS`** 在原生**根本不存在** —— 从三个端点移除。
- **`/db/REBW` 的 `STORY: {FROM, TO}`** → **`vSTORY_NAME`**（**字符串数组**，不是范围）；
  其余长名同理（`VERTICAL_REBAR`→`VER_BAR`、`HORIZONTAL_REBAR`→`HOR_BAR`、
  `END_REBAR`→`END_BAR`、`THICKNESS`→`THICK`、`USE_MODEL_THICKNESS`→`bUSE_MODEL_THICK` …）。
- **`/db/REBB` 的 `{LAYER1, LAYER2}` 对象** → **`{NAME, NUM}` 数组**（数组位置即层号，无 `LAYER` 字段）；
  三个 `BAR_SECTOR_{I,J,M}` 各含 `SHEAR_BAR` / `SKIN_BAR_NAME` / `SKIN_BAR_NUM` /
  `vMAIN_BAR_BOT[]` / `vMAIN_BAR_TOP[]`。

⚠️ **`/db/REBB` 的写路径不可用**（**从未观察到任何一次写入成功**）：
多种载荷（我方数组形状 · 官方文章的 `LAYER1`/`LAYER2` 形状 · 混合变体 · 字面空 item）
在 2026-08-27 / 09-03 / 09-27 / 10-04 四次尝试中**全部** `Wrong Field` 或 `Unknown Error`。
`ID` **必须**送（缺它得到 `Wrong Field`；`/info` 不声明 `required` 数组，故 requiredness 记为
`unstated`，该事实记在 `ID` 的 `description` 里）。同类：`/db/NLLP`、`/db/WVLD`。

#### 8.16.2 🔴 `/db/PRES` 的 `DIRECTION` 必须显式给出（MD-17）

**问题比"默认值错"更重**：手册把 `DIRECTION` 标 **Optional**、默认 `"NORMAL"`，
而**省略字段正是坏默认值被应用的途径** —— 在 `ELEM_TYPE="PLATE"` + `FACE_EDGE_TYPE="FACE"`
上，**省略**与**显式填 `"NORMAL"`** 得到**同一条**拒绝
（`[Error] Errors detected in Pressure Loads Data.(Item:Load Direction)`）。

**改动**（`registry/schema/common/db/PRES.json`）：

| 项 | 改前 | 改后 |
| --- | --- | --- |
| `required` | **无** | `["LCNAME", "FACE_EDGE_TYPE", "DIRECTION"]` |
| `DIRECTION` | 无 `enum`、无 `default` | `enum` = 服务端承认的**八个**值；**不**记 `default` |
| `ELEM_TYPE` / `FACE_EDGE_TYPE` | 无 `enum` | `["PLATE","SOLID","PLANE"]` / `["FACE","EDGE","PRES"]` |
| `VECTORS` | 无界 | `minItems: 3` · `maxItems: 3` |
| `EDGE_FACE` | 无界 | `minimum: 1` · `maximum: 6` |
| `ID` / `GROUP_NAME` / `CMD` / `ELEM_TYPE` / `OPT_PROJECTION` | 无默认值 | 记入 `0` / `""` / `"PRES"` / `"PLATE"` / `false` |

⚠️ **`"NORMAL"` 的可用性排除刻意不做成硬闸门**：手册的可用性矩阵是
`PLATE`+`FACE` **排除 `NORMAL`**、`PLANE`+`EDGE` 排除 `GX`/`GY`/`GZ`、
`PLATE`+`EDGE` 与 `SOLID`+`PRES` 接受全部八个。对方契约把该排除定为
`kind: warn` 而**不是** `reject_request`，理由是：该值对另外三种组合合法、原生错误本身是显式的、
而拒绝调用方**显式给出**的值等于替工程师做工程决策。**本批遵循该判断**，只写进 `description`。

**`EDGE_FACE` 未列入 `required`**：契约标 `required` 但 `safeToOmit: unverified`，
且手册自己的示例省略了它 ⇒ 不把它做成硬闸门（改前改后一致）。

#### 8.16.3 计数（本批变化）

| 项 | 变化 |
| --- | --- |
| 字段级比对「完全一致」对 | **316 → 337**（+21） |
| 「仅服务端有」字段 | **991 → 349**（**−642**，其中 `/db/REBW` 一个端点贡献 −400+） |
| 「仅我方有」字段 | **278 → 229** |
| 类型冲突 | **20 → 17** |
| 端点 **636** · Schema 文件 **625** · `availability` **503 / 23 / 110** · `products` 分布 | **不变** |

**可执行判定** = `tests/test_midas_nxsdk_schemas_p162.py`（**18** 项：
四个端点的 `ITEMS` 字段集逐条等于 `/info` · 手册长名**一个都不在** · `vMAIN_BAR` 是数组且覆盖层是 `D0` ·
`/db/REBW` 的 `vSTORY_NAME` 是字符串数组 · `/db/REBB` 的 `ID` 与「写路径不可用」口径 ·
`/db/PRES` 的 `DIRECTION` 必填 / `enum` / 无默认值 · `VECTORS` 恰好 3 · `EDGE_FACE` 有界 ·
`"NORMAL"` **未**被硬闸门排除）。

### 8.17 P163：CIVIL_NX 上线 —— **产品级只读路由探针**收口 B 级 21 条

**背景**：§8.15 的 B 级（**21** 条「我方只声明 `GEN_NX`、而服务端 `/info` 或对方契约含 `civil`」）
当时**故意未落地** —— 判据是「`/info` 是**产品族级**自述，我方 `products` 是**实例级**实测结论，
二者可同时为真（构建版本差异）」，故需**我方 CIVIL_NX 实例实测**。

**本批有了**：CIVIL_NX 云实例上线。证据 = `registry/live/civil_product_probe.json`
（**只发 `GET`**、零副作用；分块 + 块间只读健康检查 `GET /DB/NODE`；**带三组对照自检**）。
生成器 = `registry/tools/import_civil_probe.py`（默认预演 / 幂等 / `--check`）。

#### 8.17.1 判据（区分「路由存在」与「读回成功」）

| 探针结果 | 含义 | 动作 |
| --- | --- | --- |
| 非 `200` | **路由不在**该产品上 —— 唯一可用于产品归属的判据 | **不**并 `products`；`unavailable_on` 并上 `civil-cloud` |
| `200` ∧ 顶层键 == `read_root` | 路由在 + 读回成功 | 并 `products` · 并 `verified_on` · `availability → verified` |
| `200` ∧ 空表（`{"message": ""}`） | 路由在，本模型无数据 | 同上（P149-E 同一口径：`200` ∧ 空表 ⇒ `PARTIAL` ⇒ `verified`） |

⚠️ **`instances.yaml` 记载 civil-cloud 的语义**：未知 URI 返回 `404`（可靠）；
**空表返回 `200` + `{"message": ""}`**。故「路由存在」的判据是 **`200`**，**不是**「读回非空」。

**三组对照**（不符则证据不可用，工具拒绝执行）：
`DB.NODE` / `DB.MATL`（共有端点，必须 `200`）· `DB.SDHY` / `DB.SDIS`（§8.2 已摘除 `CIVIL_NX`，必须 `404`）·
`DB.STCT-M1` / `DB.MATL-M1` / `DB.STYP-M1`（Hyper-S 复核，见 §8.17.3）。

#### 8.17.2 B 级 21 条的收口结果

| 组 | 条数 | 端点 | 动作 |
| --- | ---: | --- | --- |
| **`200`（路由在 CIVIL_NX 上）** | **18** | `DB.{DCTL,DSTL,EPSE,ESSF,LENG,LLAN,LLANID,LTSR,MBTP,MEMB,POSL,WMAK}` · `OPE.{EDMP,GSBG,GUSTFACTOR,MEMB,SSPS}` · `VIEW.PRECAPTURE` | `products` 并 `CIVIL_NX` · `verified_on` 并 `civil-cloud` · `availability → verified` |
| **`404`（路由不在）** | **3** | `DB.POSP` · `DOC.STAGAS` · `POST.STEELCODECHECK` | **不**并 `CIVIL_NX`；`unavailable_on` 并上 `civil-cloud` |

⚠️ `DB.POSP` 的 `404` 与对方契约的 `verified_both`（含 `posp-civil-2026-10-11`）**冲突** ——
对方在 **Civil NX Build 10/10/2026** 上实测有它（其 CLAUDE.md 亦记「Civil NX 于 2026-10-11 获得
自己的 `/db/POSP`」），而我方云实例没有 ⇒ **构建差异**，如实记为实例级缺口。

#### 8.17.3 ⚠️ **一处我方实测与外部证据的冲突：Hyper-S `-M1`（21 条）**

| 来源 | GEN NX | CIVIL NX |
| --- | --- | --- |
| **我方 `gen-local`** | `404`（`unavailable_on` 已记） | —— |
| **我方 `civil-cloud`（本批，逐条实测）** | —— | **`404`（21/21 全部）** |
| **对方**（MIDAS IT 在职员工，两产品实测） | `404` | **`200`**（`HYPER_S_ONLY` = 13 + 8 = 21；live 两次确认；`hyper-s-info.json` 以 `product: civil` 抓取；18 份契约 `products: [civil]`） |

**处置（沿用 §8.2 的 `DB.UFTR`/`DB.UTBL` 先例）**：
`products` **保留** `[CIVIL_NX]`（**产品级能力声明**，依现有最强的产品级证据），
`unavailable_on` **两个实例都记**（`["civil-cloud", "gen-local"]`），
`availability` **仍为 `unverified`**（**从未在任何实例上验证成功过**）。

**为什么不回退到 `[GEN_NX]`**：`gen-local` 上它同样 `404`，且对方实测 Gen 也是 `404` ——
回退只会**放行必然 404 的 GEN_NX 调用**、同时**拦掉对方实测可用的 CIVIL_NX 调用**，两头都错。
**为什么不改成 `products: []`**：`products` 是能力声明，不是实例清单；空集会让端点彻底不可达。

**这条冲突本身是本批最值得注意的结论** —— 它说明「我方实例缺该能力」与
「该产品不支持该能力」是两件事，而 §8.2 的口径只覆盖前者。

#### 8.17.4 计数（本批变化）

| 项 | 变化 |
| --- | --- |
| `products` 含 `CIVIL_NX` | **514 → 532**（+18） |
| `availability` | `verified` **503 → 509**（+6）· `untested` **110 → 104**（−6）· `unverified` **23（不变）** |
| 写路径候选集 `CIVIL_NX` | **68 → 74**（+6） |
| 写路径 blocked `CIVIL_NX` | **440 → 452**（+18 − 6） |
| CIVIL_NX 覆盖率分子 | **`62 / 633` → `68 / 633`** |
| `civil-cloud` 出现在 `verified_on` | **226** 条 |
| `civil-cloud` 出现在 `unavailable_on` | **32** 条 |
| **不变** | 端点 **636** · Schema 文件 **625** · 映射缺口（`product_key = GEN_NX`）**489 = 243 + 246** |

**可执行判定** = `tests/test_midas_nxsdk_products_p161.py`（**13** 项，含本批新增的
「探针证据必须带三组对照且自检通过」与「21 条 `-M1` 在我方 CIVIL_NX 上全部 `404` 且如实入账」）·
`registry/tools/import_civil_probe.py --check` · 另**同步** `p141` / `p142` / `p143` / `p144`–`p148` /
`p149` / `p149c` / `p149d` / `p149e` / `p150` / `p150r118` / `p151`（**只**改钉住数字与
「整文件未改」→「指定字段未改」的口径收窄；断言**未**放宽）。

### 8.18 P164：手册勘误第四批 —— MD-60 / MD-03 / MD-16 / MD-29

判据同 §8.16：**服务端 `GET /info` 与对方已复核契约同向**，或**该节自己的示例/实测**定案。

| MD | 端点 | 手册怎么说 | 实际是什么 | 我方动作 |
| --- | --- | --- | --- | --- |
| **MD-60** | `/db/SPFC` | EURO2004 表把 `SPECTYPE`/`GROUTYPE`/`NATIONALANNEX` 放 **`OPT`** | 服务端 `/info` 把三者声明在 **`STR`**（字符串）；手册那个 body 在**两个产品**上都被拒（`Unknown Error`），去掉 `OPT` / 换 `VAL.AG` / 两者都改**同样被拒** —— **至今无可用 EURO2004 请求** | ✅ 我方**本来就是对的**（`STR` 有、`OPT` 无）；补 `STR` 说明 |
| **MD-60 附带** | `/db/SPFC` | 手册把同一字段拼成 **`LARGEBRIDEGE`**（描述也拼成 `LargeBridege`） | 服务端 `/info` 拼 **`LARGEBRIDGE`** | ✅ **保留手册拼写**（见下方「一处自我纠正」）并互相加注 |
| **MD-03** | `/db/MATL-M1` | 称它与 `/db/MATL` **同结构** | 两者**不共用 wire key**：`-M1` 用 `MATL_NAME`/`MATL_TYPE`/`PARAM`/`DAMP_RAT`，`/db/MATL` 用 `NAME`/`TYPE`/…+`HE_COND`/`HE_SPEC`/`PLMT`/`P_NAME`/`bMASS_DENS`；且 `PARAM[].P_TYPE` 在 `-M1` 是 **0-based**（`/db/MATL` 1-based） | ✅ 我方**本来就是对的**（4 个 `-M1` 专属名 + `enum: [0,1,2]`），**不改数据** |
| **MD-16** | `/db/MVHL` | 公共 Specifications 表把 `VEHICLE_TYPE_NAME`/`STANDARD_CODE` 标 **Required**、`USER_LOAD_TYPE` 标 Optional，**完全不提** `VEHICLE_LOAD_NUM` | `VEHICLE_LOAD_NUM` 是**分支判别子**（1 标准 / 2 用户定义）：`VEHICLE_TYPE_NAME` **只在分支 1 必填**（缺它得 `(Item:Length of Vehicular Load Type(0 ~ 40 characters))`，分支 2 下送它被**丢弃**）；`STANDARD_CODE` **两个分支都不需要**；`USER_LOAD_TYPE` 在 `MVLD_CODE = 2` 下**不是输入**（四种取值与省略**都**存成 `"Truck/Lane"`） | ✅ 补 `LOAD_ITEMS[].POINT_DIST2`（`/info` 有、我方缺）· `VEHICLE_LOAD_NUM` 加 `enum: [1,2]` + 分支说明 · **`if/then`** 表达条件必填 · 两处「手册说必填、实测不必填」**只加注不做闸门** |
| **MD-29** | `/DESIGN/RC/KDS-41-20-2022/REBB` | 该节的 **JSON Schema / Parameters 表**给 `MAIN_BAR_TOP`/`MAIN_BAR_BOT`（`{LAYER1, LAYER2}` 对象）+ `DT`/`DB` + `SKIN_BAR` 对象 | 该节**自己的** Request Body / Response Body / Python 示例**一律**用 `vMAIN_BAR_TOP`/`vMAIN_BAR_BOT` **数组** + `MAIN_BAR_DC_TOP`/`MAIN_BAR_DC_BOT` + 扁平 `SKIN_BAR_NAME`/`SKIN_BAR_NUM` + 三个 `bSAME_SIZE_*`；且该节有一处 callout **明说以示例为准** | ✅ 条目按**示例**重建（8 → **11** 成员；`DT`/`DB` 移除） |

**MD-16 为什么不做成硬闸门**：与 §8.16.2 的 `PRES.DIRECTION` 不同 —— 那里对方契约给的是
`reject_request`（`rejects: omission`），而这里契约只给 `appliesWhen` 元数据。
`STANDARD_CODE` 更是「手册标 Required、实测不必填」⇒ 做成闸门会**拒掉合法请求**。
`VEHICLE_TYPE_NAME` 的 `if/then` 是例外：缺它实测**被拒**，故表达为条件必填。

#### 8.18.1 ⚠️ 一处**自我纠正**：`OPT.LARGEBRIDEGE` 不能删

初版把 `OPT.LARGEBRIDEGE` 当成我方转写笔误**删掉**了（理由：描述也拼成 `LargeBridege`，
且 `OPT.LARGEBRIDGE` 就在旁边）。`sync_introspect_fields.py --check` 立刻报错：

> `DB.SPFC: 反向缺口（data_only）与证据不一致 —— 反向缺口**一律不动**`

核对后确认该拼写**确实出自官方手册**（`MIDAS_API_Online_Manual_数据_v1.0.json` /
`_Gen_NX_v1.0.json` / `_开发文档_v1.0.md` / `_完整API手册_v1.0.md` **四处**），
而 **R117** 明令「手册声明而本 build 自省**没有**的字段**不删**、**不改名** —— 删除会**削弱**既有判定」。
⇒ 已**恢复**，改为两个拼写**互相加注**。**这是本批最有价值的一条：既有规则挡住了我的一次越界。**

#### 8.18.2 计数（本批变化）

| 项 | 变化 |
| --- | --- |
| `/db/MVHL` Schema | +`LOAD_ITEMS[].POINT_DIST2` · +`allOf`（`if/then`）· `VEHICLE_LOAD_NUM` +`enum` |
| `/db/SPFC` Schema | `STR` 说明 + `OPT.LARGEBRIDGE`/`LARGEBRIDEGE` 互相加注（**字段数不变**） |
| `/DESIGN/RC/KDS-41-20-2022/REBB` | `ITEMS` 条目 **8 → 11** 成员（按示例重建） |
| **不变** | 端点 **636** · Schema 文件 **625** · `products` 分布 · `availability` 三档 **509 / 23 / 104** · 映射缺口 **489** |

**可执行判定** = `tests/test_midas_nxsdk_schemas_p164.py`（**18** 项：
MD-60 的 `STR`/`OPT` 归属与拼写保留 · MD-03 的 `-M1` 专属 wire key 与 0-based `P_TYPE` ·
MD-16 的缺字段 / `enum` / `if/then` / **两处不做闸门** · MD-29 的示例形状与表名消失）。

---

### 8.19 P164-c / P164-d：`DESIGN.{RC,SRC}` 的 `*-ANAL` 执行族 —— **实测打崩宿主程序 ⇒ 留缺 + 护栏**

> 事故驱动（**不是**手册勘误）。完整报告 = `docs/reports/P164-c_分块2_DESIGN_CONCRETE原生崩溃留缺_v1.0.md`
> · 裁决 = `docs/07` §16.1 **R154 / R155 / R156**。

#### 8.19.1 🛑 实测：`BD-ANAL` 让 **MIDAS Gen NX 直接终止**

```text
POST /DESIGN/RC/KDS-41-20-2022/BD-ANAL
Faulting application : GenNX.exe 26.9.1.1001
Faulting module      : wg_db.dll 1.0.0.1
Exception code       : 0xc0000005（访问违例）
Fault offset         : 0x2d97e5c        ← 四次实测**完全相同**
恢复文件             : .tmp_p164c/p164c-concrete_restore.mgbx
```

**四次**（2026-10-14 的 20:05:04 / 20:47:15 / 20:58:20 / **21:12:30**）用的请求体**各不相同**
（① 小写 canonical 键 · ② `PERFORM_TYPE="ALL"` + `ELEMS` 自相矛盾 · ③ **手册 `BD-ANAL` 文章的逐字示例**
· ④ ③ 的形状 + **关掉抗震**）⇒ **崩溃与请求体无关**，是**原生设计引擎的缺陷**，我方**无法规避**。

⚠️ **判据口径（本批最有价值的一条）**：链路层只回报 `STRUCTAI-2000 transport_error`
（`details.endpoint = /DESIGN/RC/KDS-41-20-2022/BD-ANAL`）—— **看不出**宿主机已经被打崩
⇒ 真机写路径的判据**必须**核对 **Windows 应用程序日志**（`Application Error 1000` / WER `1001`），
**不能**只看链路错误码。

#### 8.19.2 留缺口径与**覆盖范围**（同族全查）

`registry/manifest.json` 里**恰好 12** 个 `*-ANAL` 端点。**11** 个登记为「原生崩溃风险」留缺：

| 族 | 端点 | 依据 |
| --- | --- | --- |
| RC 设计执行 | `BD-ANAL` | 🛑 **实测**（四次，同一偏移） |
| RC 设计执行 | `CD-ANAL` · `BRD-ANAL` · `WD-ANAL` | 同族推定 |
| RC **校核**执行 | `BC-ANAL` · `CC-ANAL` · `BRC-ANAL` · `WC-ANAL` · `HCD-ANAL` | 同族推定（同原生模块 / 同调用形态） |
| SRC 执行 | `BC-ANAL` · `CC-ANAL` | 同族推定 |
| ~~钢铁~~ | ~~`DESIGN.STEEL.KDS-41-30-2022.CODE-ANAL`~~ | ✅ **排除**：旗舰链**真机 12/12 跑通** ⇒ 拦它 = 过度防护 |

⚠️ **第一版只拦了 6 个、漏了 5 个**：`DESIGN.RC.*` 的**校核**族**没进任何 Operation 的编排**
⇒ 只按「编排里出现的端点」查**查不出来**，**必须按 `manifest.json` 全量查**（R153 的教训）。
覆盖口径现由 `tests/test_midas_native_crash_guard_p164c.py` **对着 manifest 逐条复算**
（新增一个 RC/SRC 的 `*-ANAL` ⇒ 用例先红）。

⚠️ **`availability` 一行未改**（11 个**全部**保持 `untested`）：没有成功实测 ⇒ **不**升级。
这 11 个端点在生产路径**本来**就被 `registry_mapping_not_verified` 挡住
⇒ 护栏实际只收紧**探针**（`allow_unverified=True`）那条路 —— 那正是打崩 MIDAS 的那条路。
每个端点 YAML 头部写明失败形态 / 护栏 / 恢复条件（**恢复条件 = MIDAS 侧修 `wg_db.dll`**）。

#### 8.19.3 计数（本批变化）

| 项 | 变化 |
| --- | --- |
| 端点 / Schema 文件 | **不变**（636 / 625） |
| `availability` 三档 | **不变**（509 / 23 / 104） |
| 映射缺口 | **不变**（489） |
| `DESIGN.{RC,SRC}` 的 `*-ANAL` | **11** 个登记为「原生崩溃风险」留缺（**新口径**，不改变既有计数） |
| 新增证据 | `registry/live/view_result_modes.json`（`VIEW.RESULTGRAPHIC` 的 **36** 个 `CURRENT_MODE` 取值；生成器 `registry/tools/extract_result_modes.py`） |

#### 8.19.4 顺带：`VIEW.RESULTGRAPHIC` 的成因更正（**R155**）

`registry/live/view_result_modes.json` 证明：该端点是**多变体端点**，`Argument.CURRENT_MODE`
是**变体选择子**（手册 **34** 篇文章 / **56** 条示例 ⇒ **36** 个取值）；R150 实测被拒的
**`"displacement"` 不在表内** ⇒ 那一次 `400`（`second query is wrong`）= **取值非法**，
**不是**「缺分析结果」。⚠️ **数据侧缺口如实记录**：该端点的**请求 Schema** 的 `Argument`
**只**声明 `TYPE_OF_DISPLAY`（36 个变体里的 1 个；且实测覆盖只有 **53/56** —— **不是**必填）
⇒ **R140 的 `spec_guard` 抓不到非法 `CURRENT_MODE`**。补全 36 个变体的 Schema 是
**单独一次数据侧作业（须裁决）**；⚠️ **不建议**只按手册补枚举（**枚举可能不全**，R151 的教训
⇒ 会**误拦**原生其实接受的取值，而这里要防的只是 `400`、**不是崩溃** ⇒ 代价不对等）。

#### 8.19.5 🛑 P164-f（R157）：真机重测做完 —— `200` 了，但**画面没变** ⇒ **不**收口

**R155 成立**：用**表内**取值（`DisplacementContour` / `DeformedShape`）在 `gen-local` 的
混凝土简支梁上（21 节点 / 20 单元 / 工况 `DL` / **63** 行位移结果）**都**回 **`200`**
—— R150 的 `400 second query is wrong` **确实**只是**取值非法**。

**但效果判据 FAILED**：三次截图（A：Contour · B：Deformed · C：Contour 重放）
**字节完全相同**（**32023** 字节 · 同一 sha256）⇒ **`200` 是静默空转**
（与 **R119 / R128 / R145 / R146** 同族）⇒ **铁律 ⓪** 不成立 ⇒ **`availability` 保持 `untested`**。

⚠️ **方法学（缺一不可，本批最要紧的一条）**：**阳性对照**必须先通过 ——
`VIEW.DISPLAY` 的 `ELEMENT.ELEM_NUMBER` 开/关让截图**真的不同**
（**38869** vs **32023** 字节）⇒ 截图**确实**能看见显示变化 ⇒ 「无差异」**不是**仪器失灵；
且对照组 C == A（同取值可复现）⇒ 排除「截图本来就不稳定」。
**没有阳性对照的「无差异」不构成证据。**

⚠️ **另一条实测**：`VIEW.CAPTURE` 的 `SET_MODE: "post"` 也回 `200` 但截图与 `pre` **相同**
⇒ 与 `docs/nxsdk_review` 的实测摘要**一致**（**纯 API 进不了 post 模式**，需 GUI 手动点）
⇒ **成因未定**（原生空转？进不了结果视图？）⇒ **如实留缺**。

⚠️ **零残留**：跑后哨兵 6 项全一致（视图类操作**不**动模型）；
`VIEW.RESULTGRAPHIC` 挡住的 **6** 个 Operation **未**解锁（生产可用仍 **62/71**）。
证据 = `registry/live/view_result_effect_probe.json`（生成器 `registry/tools/probe_view_result_effect.py`）。

**可执行判定** = `tests/test_midas_native_crash_guard_p164c.py`（**30** 项）·
`tests/test_midas_view_result_modes_p164d.py`（**10** 项）·
`tests/test_midas_view_result_modes_probe_p164e.py`（**6** 项）。

⚠️ **P166 / R159 已收口（见 §8.20）** —— 本节 §8.19.5 的「不**收口**」是**当时的**结论，
**原样保留**（历史记录）；`VIEW.RESULTGRAPHIC` 的 `availability` 现为 **`verified`**。

---

### 8.20 P166：`VIEW.RESULTGRAPHIC` 的**纯 API 进结果视图（post）路径** —— **R157 的成因已定 ⇒ 收口**

> 事故 / 悬案驱动（**不是**手册勘误）。完整报告 =
> `docs/reports/P166_结果视图post纯API路径_R159_v1.0.md`；裁决 = `docs/07` §16.1 **R159**。

#### 8.20.1 一句话结论

**R157 的「静默 `200` / 画面没变」有答案了**：P164-f 的请求体**只有**
`CURRENT_MODE` + `LOAD_CASE_COMB`，**缺 `TYPE_OF_DISPLAY`** ——
而 **`TYPE_OF_DISPLAY.<子块>.OPT_CHECK = true` 才是真正把结果图形打开的那个开关**。
补上它之后 `VIEW.RESULTGRAPHIC` 的**效果判据 7 / 7 通过** ⇒ **`untested → verified`**。

#### 8.20.2 纯 API 进结果视图（post）的路径（**手册自己的写法**，实测成立）

| 机制 | 语义（实测） |
| --- | --- |
| `POST /VIEW/CAPTURE` 的 `Argument.SET_MODE`（`"pre"` / `"post"`） | **切换视图模式**，**粘性**（后续不带 `SET_MODE` 的 `CAPTURE` 仍在该模式下，直到再发 `"pre"`）；**前提** = 项目**确有分析结果**（无结果 ⇒ **`400`** `"Post Mode is not available"`，P160d 实测） |
| `POST /VIEW/RESULTGRAPHIC` | 写**持久**结果图形（`CURRENT_MODE` + `LOAD_CASE_COMB` + **`TYPE_OF_DISPLAY`**） |
| `POST /VIEW/CAPTURE` 的 `Argument.RESULT_GRAPHIC` | **一次性覆盖**（只作用于本次 `CAPTURE`）—— 手册 `Capture #1` 示例的形状 |
| 渲染条件 | 结果图形**只在 post 模式下渲染**；且**必须**有 `TYPE_OF_DISPLAY.<子块>.OPT_CHECK = true`，否则原生**照样回 `200`** 但**什么都不画** |

#### 8.20.3 效果判据（**铁律 ⓪**）= `PASSED`（2026-10-15，`gen-local`，自建混凝土简支梁，工况 `DL`）

| 步 | 动作 | 截图字节 | 结论 |
| --- | --- | ---: | --- |
| ① | 图形全关 → `CAPTURE(SET_MODE=post)` ×**2** | **33438** / **33438** | **噪声地板 = 0**（渲染确定） |
| ② | `RESULTGRAPHIC(DisplacementContour)` → `CAPTURE(post)` | **81236** | **改前 ≠ 改后**（**2.4×**） |
| ③ | `RESULTGRAPHIC(DeformedShape)` → `CAPTURE(post)` | **84494** | **换取值 ⇒ 画面真的换** |
| ④ | `RESULTGRAPHIC(DisplacementContour)` → `CAPTURE(post)` | **81236** | **同取值可复现**（与 ② 逐字节相同） |
| ⑤ | 图形全关 → `CAPTURE(post)` | **33438** | **回到基线** |
| ⑥ | `RESULTGRAPHIC(...)` → `CAPTURE(**pre**)` | **32457** | **pre 模式画不出结果** |
| ⑦ | **阳性对照**：`DISPLAY(ELEM_NUMBER)` 开 / 关 → `CAPTURE(post)` | **40211** / **33438** | **仪器有效** |

⇒ **7 / 7** 满足 ⇒ `availability` **收口为 `verified`**（**只升不降**，同 §4 口径）。

#### 8.20.4 计数（本批变化）

| 项 | 变化 |
| --- | --- |
| `availability` 三档 | `verified` **509 → 510** · `untested` **104 → 103** · `unverified` **23（不变）** |
| **生产路径可用 Operation**（`docs/07` §15.6.3 的主指标） | **`61 / 71` → `67 / 71`**（被挡 **10 → 4** · 挡点端点 **15 → 14**） |
| 端点 / Schema 文件 | **不变**（636 / 625） |
| 映射缺口（`product_key = GEN_NX`） | **不变**（489） |
| 数据侧缺口（**如实保留**） | 请求 Schema 的 `Argument` **只**声明 `TYPE_OF_DISPLAY` ⇒ `spec_guard` **没有** `CURRENT_MODE` 的枚举可查（**R155**，本批**不**修） |

#### 8.20.5 顺带的两条**离线**结论（**零请求**）

* **`VIEW.SELECT` 不是「激活 / 选择结果视图」的入口**：手册条目只有
  `Input URI` / `Active Methods` / **`Response Examples`** 三节（**无请求体**、**无 `specifications`**），
  唯一响应示例是 `{"SELECT": {"NODE_LIST": [...], "ELEM_LIST": [...]}}` ⇒ 它是**读**当前选中编号表的查询。
* **`VIEW.DISPLAY` 与 post / result 无关**：它是**模型显示**（节点 / 单元 / 属性 / 边界 / 荷载 …）；
  结果方向的字段**只**在 `VIEW.RESULTGRAPHIC` 与 `VIEW.CAPTURE.RESULT_GRAPHIC` 里。

**可执行判定** = `tests/test_midas_view_result_post_p166.py`（**14** 项）·
工具 `registry/tools/probe_view_result_post.py`（默认预演 / `--probe` 真机 / `--check` 离线自洽）·
证据 `registry/live/view_result_post_probe.json`（**只记字节数与 sha256**，不记图片内容）。

### 8.21 P167：`POST.TABLE` 的 `TABLE_TYPE` **枚举收口**（**R151 的恢复条件①**）⇒ **R160**

> 留缺驱动（**不是**手册勘误）。完整报告 = `docs/reports/P167_POST_TABLE枚举收口_R160_v1.0.md`；
> 裁决 = `docs/07` §16.1 **R160**；上游留缺 = **R151**（P160e-a）。

#### 8.21.1 一句话结论

拦住 `RESULT.ANALYSIS.SUMMARY` 的**不是**原生，而是核心自己的 `spec_guard`（**R140**）
手里那份**只有 2 个取值**的 `TABLE_TYPE` 枚举（`WEIGHT_IRREGULARITY_X` / `_Y`，
来自 help center **一篇文章**的 `json_schema`）。枚举来源换成**两个可复算来源的并集**
⇒ `POST.TABLE` 的 `availability: untested → verified` ⇒ 解锁 **1** 个 Operation。

#### 8.21.2 枚举口径（**可复算**；生成器 = `registry/tools/sync_table_type_enum.py`）

| 来源 | 判据（**机械扫描**，无人工取值） | 规模 |
| --- | --- | ---: |
| ① **登记表** | `registry/manifest.json` 里 key 以 `POST.TABLE.` 开头且 `table_type` **非空**的端点 ⇒ 取其 `table_type` | **194** |
| ② **手册声明** | `MIDAS_API_Online_Manual_数据_v1.0.json` 里**所有**条目 `json_schema` 的 `TABLE_TYPE.enum`（扫描口径与 `sync_request_schemas.table_type_tokens()` **逐字相同**） | **121** |
| **并集** | 落进 `registry/schema/common/post/TABLE.json` 的 `Argument.TABLE_TYPE.enum` | **225** |

* ⚠️ **只取①会丢掉 `WEIGHT_IRREGULARITY_Y`**（手册声明但**没有**登记成独立端点）⇒ 那是把闸门
  **收紧**，与 R151 的教训（枚举**可能不全**）**反向** ⇒ 故取**并集**。
* ⚠️ **枚举只增不减**：`--write` 时若机械结果丢掉了已落盘的任何取值，工具**拒绝写入**
  （确需收紧要显式 `--allow-shrink`）。
* ⚠️ **R140 的保护照旧**：伪 token（两个来源都不在）仍被 `spec_guard` 拦在**发请求之前**（**零请求**）；
  `app/**` **一行未改**（枚举是**数据**，不是 Core 常量）。

#### 8.21.3 效果判据（**铁律 ⓪**）= `PASSED`（2026-10-15，`gen-local`，自建混凝土简支梁）

| 相 | 实测 |
| --- | --- |
| **原生阳性** | `POST /POST/TABLE {TABLE_TYPE: "DISPLACEMENTG"}` ⇒ **`200`** · 信封 `"empty"` · `HEAD` **9** 列 · `DATA` **63** 行 |
| **核心阳性**（`engineering_result` / `RESULT.ANALYSIS.SUMMARY`） | `success=true` · 规范化结果 `data.result.rows` = **63** 行 · 原生请求 `POST /POST/TABLE` ⇒ `200` |
| **核心阴性** | 伪 token `NOT_A_REAL_TABLE_XYZ` ⇒ `STRUCTAI-1200 value_not_in_spec_enum`（`native_stage = midas_adapter`）∧ **零请求** |
| **原生阴性** | 伪 token ⇒ **`400`** |
| **零残留** | 跑前 / 跑后 **6** 个模型哨兵**逐项一致**（取报表**不**写模型） |

⚠️ **两个口径都测**：Contract-Test 口径（`allow_unverified=True`，收口**前**测效果）与
**生产口径**（`allow_unverified=False`，收口**后**再跑一次）**都** `PASSED`。

#### 8.21.4 顺带实测的两条事实（登记备查）

* **原生对 `TABLE_TYPE` 的取值大小写不敏感**（`displacementg` ⇒ 同样 `200` / **63** 行），
  而 `spec_guard` 按手册声明的**大写**取值判定 ⇒ 小写会在**核心**被拦（`STRUCTAI-1200`，**零请求**）。
* **手册声明但未登记**的 token 原生仍可能拒（`TH_DISP` ⇒ **`400`**）—— 那是**取值不适用**，
  **不是**崩溃风险（R140 的事故是**弹窗 / 访问违例**；这里回的是**干净的 `400`**）。

#### 8.21.5 计数（本批变化）

| 项 | 变化 |
| --- | --- |
| `availability` 三档 | `verified` **510 → 511** · `untested` **103 → 102** · `unverified` **23（不变）** |
| **生产路径可用 Operation**（`docs/07` §15.6.3 的主指标） | **`67 / 71` → `68 / 71`**（被挡 **4 → 3** · 挡点端点 **14 → 13**） |
| 端点 / Schema 文件 | **不变**（636 / 625） |
| 剩余 **3** 个被挡 Operation / **13** 个挡点端点 | **6** 个 `*-ANAL` = **实测崩溃族**（**R154** ⇒ **MIDAS 侧**）；**6** 个 `*-TABLE` = `untested`（要**先有设计结果** ⇒ 依赖那 6 个）+ **1** 个 `POST.STEELCODECHECK`（**R152**：我方**可**收口但**不**解锁） |

**可执行判定** = `tests/test_midas_post_table_enum_p167.py`（**19** 项）·
工具 `registry/tools/probe_post_table_enum.py`（默认预演 / `--probe` 真机 /
`--probe --production` 生产口径 / `--check` 离线自洽）·
枚举生成器 `registry/tools/sync_table_type_enum.py`（`--write` / `--check`）·
证据 `registry/live/post_table_enum_probe.json`（**不含**凭据 / 响应原文）。
