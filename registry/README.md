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
