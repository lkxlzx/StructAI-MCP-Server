# StructAI｜MIDAS GEN NX API 实测补充文档 V1.0

> ⚠️ **非规范性文档（NON-NORMATIVE）** —— 本文件已归档至 `archive/legacy_v1/`，
> 属 StructAI 早期（V1）规范草案 / 实测记录，**不作为开发依据，不作为准则**。
> 开发唯一依据：`docs/01`–`docs/06`（V2 规范）· `docs/07`（开发方案与任务续接）· `registry/`（机器可读端点注册表）。

> 本文是《StructAI 多结构工程软件一体化 MCP 完整开发文档 V1.0》的**第三份配套文档**。
>
> 前两份：① 主开发文档（产品/软件/连接/Adapter/Registry/工程/设计/图形/计算书主规范）；② 快速响应与实时反馈架构补充文档（执行与反馈层）。
>
> 本文只做一件事：**用 `G:\MIDAS-API-Online-Manual`（midas Gen API 使用手册）的真实数据，把主文档中"待录入"的 Endpoint Registry 知识层补实**，并给出对主文档的逐条回写建议。不修改前两份文档的核心原则。

---

## 1. 数据来源与可信度

| 项 | 内容 |
| --- | --- |
| 主来源 | `G:\MIDAS-API-Online-Manual\manual\midas Gen API 使用手册.md`（12.1 MB / 410,979 行） |
| 中文部分 | wolai 在线手册抓取，13 个分类 / 332 页面；含 `接口代码`、`Input URI`、`Active Methods`、`Input Data Form`、`Input Data Example`、必填字段表 |
| 英文部分 | MIDAS Support Help Center 抓取，33 个分区 / 691 页面；含 `Input URI`、`Active Methods`、**JSON Schema（draft-07）**、`Request/Response Examples`、`Specifications` |
| 官方索引 | `tools/cache/_en_index_rows.json`（430 行索引，274 个带 URI 的 Endpoint） |
| 中英对照 | `mapping.csv`（`category, zh_title, api_code, zh_path, en_title, en_path`） |
| 本文章节依据 | 英文数据手册（索引接口）区，行 54,970–325,858；该区每个 Endpoint 一页，共 **475 页** |

抽取方式：按 `### 分区` / `#### 页面` 切分，逐页解析 `Input URI`、`Active Methods`、JSON Schema（`Argument.properties.TABLE_TYPE.enum`）、Examples（`"TABLE_TYPE": "..."`）、Specifications 行数、官方原文 URL。抽取脚本与中间产物见第 12 节。

**实测总量**（可用于校核主文档的规模假设）：

| 指标 | 数值 |
| --- | --- |
| 官方索引 URI Endpoint | **274** |
| 手册正文 Endpoint 页面 | **475** |
| 唯一 URI（归一化后） | **268** |
| 可落地的 Registry 逻辑 key | **501**（见附件 CSV） |
| 带官方 JSON Schema 的页面 | 444 |
| 带 Specifications 字段表的页面 | 498 |
| 带产品/求解器约束的 key | 20（Hyper-S 专属） |
| `info/` Schema 自省出现次数 | 161（154 个不同 DB 代码） |

---

## 2. Registry 逻辑 key 总览

| namespace | 逻辑 key 数 | 唯一 URI 数 | Methods 组合 |
| --- | --- | --- | --- |
| DOC | 11 | 11 | POST ×11 |
| DB | 227 | 227 | POST+GET+PUT+DELETE ×206；GET+PUT+DELETE ×9；POST+GET+PUT ×4；GET+PUT ×7；手册未列 ×1 |
| OPE | 19 | 19 | POST ×15；GET ×2；GET+POST ×2 |
| VIEW | 7 | 7 | POST ×6；GET ×1 |
| POST | 237 | 4 | POST ×237 |
| **合计** | **501** | **268** | — |

主文档 §111「第一批 Registry」列出 **24** 个逻辑 Endpoint（DOC 4 + DB 11 + VIEW 4 + POST 5），占实测总量 501 的 **4.8%**。这确认了主文档 §123「最终以官方手册逐二级页面录入完整 Registry」是必要的长期工作量，也说明第一阶段必须严格限定范围。

---

## 3. 与主文档的差异与修正

### 3.1 已核对一致（主文档无需修改）

| 主文档 | 核对结果 |
| --- | --- |
| §5.1.1 DOC Endpoint 11 项 | **完全一致**：NEW / OPEN / CLOSE / SAVE / SAVEAS / STAGAS / IMPORT / IMPORTMXT / EXPORT / EXPORTMXT / ANAL，全部仅 POST |
| §52 OPE 列表 19 项 | **完全一致**：PROJECTSTATUS / DIVIDEELEM / SECTPROP / USLC / LINEBMLD / AUTOMESH / SSPS / EDMP / STOR / STORY_PARAM / STORY_IRR_PARAM / STORPROP / MEMB / GUSTFACTOR / LCOM-GEN / LCOM-CONC / LCOM-STEEL / LCOM-SRC / GSBG |
| §53 VIEW 列表 7 项 | **完全一致**：SELECT / CAPTURE / PRECAPTURE / ANGLE / ACTIVE / DISPLAY / RESULTGRAPHIC |
| §24 POST/TABLE 的 `fixed_arguments: TABLE_TYPE` 设计 | **正确**，实测 POST 层确实只有 4 个 URI，表类型由 `Argument.TABLE_TYPE` 选择 |
| §50 DB 写入用 `Assign` 包装 | **正确**，实测 DB 写入 Body 第一层为 `Assign` |
| §13 Solver 必须进 Runtime Context | **必要**，实测存在 20 个 Hyper-S 专属 Endpoint |
| §111 第一批 8 个建模 Endpoint（UNIT/STYP/PJCF/MATL/SECT/NODE/ELEM/CONS） | **URI 与 Methods 全部命中**，可直接落地 |

### 3.2 需要新增（主文档缺此机制）

| # | 发现 | 说明 | 影响 |
| --- | --- | --- | --- |
| N1 | **`info/{namespace}/{code}` Schema 自省** | 手册中每个 DB 页面的 `Input Data Form` 指向 `{base url} + info/db/{CODE}`，实测出现 161 次、覆盖 154 个 DB 代码。MIDAS 自身返回该 Endpoint 的 JSON 字段定义 | 主文档假设 `schema_ref` 指向本地 `schema/*.json`。应改为三源策略：**本地缓存（快）→ `info/` 回源（准）→ 手册 JSON Schema（兜底）**。MIDAS 升级时 Schema 自动对齐，不必手工重录 |
| N2 | **`include_schema` 的实现路径** | 主文档 §6 的 `midas_db_query.options.include_schema` 应直接调用 `info/db/{CODE}` 而非读本地文件 | 减少本地 schema 维护量，且保证与目标 MIDAS 版本一致 |
| N3 | **Registry `source.*` 可自动生成** | 手册每页都带官方原文 URL（`- 英文原文： [title](url)`）与标题 | 主文档 §122 要求的 `source.official/page/url/title/retrieved_at/source_hash` 可从手册自动产出，不必人工填写 |
| N4 | **Level 1 校验可自动生成** | 手册每页的 `Specifications` 表给出 `Key / Value Type / Default / Required`（498 页有此表） | 主文档 §47 Level 1 Schema Validation 可由手册直接生成，无需手写 |
| N5 | **公共参数组** | POST 表类页面统一含 `Argument.TABLE_NAME`、`Argument.TABLE_TYPE`、`Argument.EXPORT_PATH`、`Argument.UNIT{FORCE,DIST,...}`、`Argument.STYLES{FORMAT,PLACE}` | 应作为 POST 命名空间的公共 `wrapper` 定义，避免 237 个 key 重复描述 |

### 3.3 需要修正或补充说明

| # | 主文档现状 | 实测 | 建议 |
| --- | --- | --- | --- |
| C1 | §23 示例写 `uri: /db/NODE`（大写）；§5.1.1 写 `/doc/NEW`（大写） | 官方英文索引统一大写（`/doc/NEW`、`/db/NODE`、`/ope/USLC`、`/view/CAPTURE`、`/post/TABLE`）；中文手册部分页面写小写（`doc/new`、`db/PJCF`） | Registry 统一采用官方索引大写形式；**大小写敏感性需真机实测**后写入 Adapter 说明（当前不能断言 MIDAS 忽略大小写） |
| C2 | §22.4 只列 4 种 method，未说明逐条差异 | 227 个 DB Endpoint 中 206 个支持四方法，但有 9 个仅 GET/PUT/DELETE、4 个仅 POST/GET/PUT、7 个仅 GET/PUT、1 个手册未列 | `methods` **必须逐条录入**，不得统一假设；`midas_db_delete` 需按该方法集判断可用性并返回结构化错误 |
| C3 | §54 POST 层只列 8 类能力 | 实测 237 个表/文本类型：Analysis Result Table 97、Time History Result Table 52、Analysis Story Table 25、Time History Text 19、Pre-Process Table 17、Design 11、Pushover Text 10、Heat of Hydration 6 | 按 §7 分组录入；Registry key 命名统一为 `POST.TABLE.<TYPE>` / `POST.TEXT.<TYPE>` |
| C4 | §2 提到「部分 Endpoint 标注为 Hyper-S solver only」，未落清单 | 实测 21 个索引条目带标记：20 个 `-M1` 变体标 `ᴴˢ⁾`，1 个 `/db/GALD` 标 `ᴶ⁾`（网格模型分析） | 落为 §8 的清单，并在 Registry 增加 `solver` 字段值 `HYPER_S` / `GRID_MODEL` |
| C5 | §5.1 DOC 命令集（11 项） | 中文手册 DOC Control 另有 `UFIG`（模型视图截图 / 施工阶段截图），官方英文索引对应 `/view/CAPTURE` | 建议 `UFIG` **不进** DOC 命令集，截图统一走 `VIEW.CAPTURE`；若保留 UFIG，须标为旧版兼容并放入 Version Override |
| C6 | §111 第一批只给 key，未给 URI/Methods | 全部命中，见 §9 实测表 | 直接以 §9 表格作为第一批 Registry 的落地依据 |
| C7 | §108 目录有 `schema/` 但无生成来源 | 手册 444 页含官方 draft-07 JSON Schema | 增加 `tools/manual2registry/` 生成链：手册 → `schema/*.json` + `registry/common/*.yaml` + 测试用例 |
| C8 | §111 第一批的 `LCOM` / `REACTION` / `DISPLACEMENT` / `STORYDRIFT` | 实测**这四个 key 不存在**：无 `/db/LCOM`，只有 `LCOM-GEN/CONC/STEEL/SRC/STLCOMP/SEISMIC` 六个子类型；无 `REACTION`，只有 `REACTIONG`/`REACTIONL`；无 `DISPLACEMENT`，只有 `DISPLACEMENTG`/`DISPLACEMENTL`；无 `STORYDRIFT`，只有 `STORY_DRIFT_X`/`_Y`/`_COMB` | 第一批 Registry key 必须按 §9.2 修正，否则第一/第三阶段验收会直接失败 |

---

## 4. 官方分区 → MCP 命名空间映射（33 分区全覆盖）

主文档 §123 只列了 6 个大类（DOC / DB / OPE / VIEW / POST）。手册实测官方索引为 **33 个分区**，映射如下（括号内为该分区贡献的 Registry key 数）：

| 官方分区 | 命名空间 | key 数 | 官方分区 | 命名空间 | key 数 |
| --- | --- | --- | --- | --- | --- |
| DOC | DOC | 11 | Analysis | DB | 21 |
| Project | DB | 8 | Analysis Results | DB | 8 |
| View | DB | 5 | Bridge Specialization Results | DB | 4 |
| Structure | DB | 2 | Time History Analysis Results | DB | 4 |
| Node/Element | DB | 6 | Heat of Hydration Results | DB | 1 |
| Properties | DB | 31 | Pushover | DB | 6 |
| Boundary | DB | 24 | Design | DB + POST | 10 + 11 |
| Static Loads | DB | 21 | OPE | OPE | 19 |
| Temperature Loads | DB | 5 | VIEW | VIEW | 7 |
| Prestress Loads | DB | 7 | Pre-Process Table | POST | 17 |
| Moving Loads | DB | 28 | Analysis Result Table | POST | 97 |
| Dynamic Loads | DB | 12 | Analysis Story Table | POST | 25 |
| Construction Stage Loads | DB | 6 | Time History Result Table | POST | 52 |
| Heat of Hydration Loads | DB | 8 | Heat of Hydration Result Table | POST | 6 |
| Settlement Loads | DB | 2 | Time History Text | POST | 19 |
| Miscellaneous Loads | DB | 7 | Pushover Text | POST | 10 |
| Grid Model Analysis Loads | DB | 1 | | | |

合计：DOC 11 + DB 227 + OPE 19 + VIEW 7 + POST 237 = **501**。

要点：

- 官方索引把 `Project / View / Structure / Node-Element / Properties / Boundary / 各类 Load / Analysis / Design` 全部归入 **DB 命名空间**（URI 前缀 `/db/`），所以 DB 占 227/501 = 45%。
- `Design` 分区**横跨两个命名空间**：设计控制与材料数据走 DB（DCON / DCTL / DSTL / LENG / LTSR / MATD / MBTP / MEMB / RCHK / WMAK），设计结果查询走 POST（PM / STEELCODECHECK / 9 个 `*DESIGNFORCES` 表）。
- 6 个 "Table / Text" 分区（Pre-Process Table、Analysis Result Table、Analysis Story Table、Time History Result Table、Heat of Hydration Result Table、Time History Text、Pushover Text）**不引入新 URI**，全部落在 `/post/TABLE` 与 `/post/TEXT` 上。

---

## 5. URI / Methods / Wrapper 实测规范

### 5.1 URI 形式

```text
{base url} + /{namespace}/{CODE}

/doc/NEW  /doc/OPEN  /doc/CLOSE  /doc/SAVE  /doc/SAVEAS  /doc/STAGAS
/doc/IMPORT  /doc/IMPORTMXT  /doc/EXPORT  /doc/EXPORTMXT  /doc/ANAL

/db/NODE  /db/ELEM  /db/MATL  /db/SECT  /db/CONS  /db/STLD  /db/BMLD  /db/LCOM-GEN
/db/ACTL-M1  /db/THGC-M1  ...

/ope/PROJECTSTATUS  /ope/SECTPROP  /ope/DIVIDEELEM  /ope/USLC  /ope/AUTOMESH
/ope/SSPS  /ope/EDMP  /ope/STOR  /ope/STORY_PARAM  /ope/STORY_IRR_PARAM
/ope/STORPROP  /ope/MEMB  /ope/LINEBMLD  /ope/GSBG  /ope/GUSTFACTOR
/ope/LCOM-GEN  /ope/LCOM-CONC  /ope/LCOM-STEEL  /ope/LCOM-SRC

/view/SELECT  /view/CAPTURE  /view/PRECAPTURE  /view/ANGLE
/view/ACTIVE  /view/DISPLAY  /view/RESULTGRAPHIC

/post/TABLE  /post/TEXT  /post/PM  /post/STEELCODECHECK
```

### 5.2 Methods（逐条录入，不得统一假设）

| Methods 组合 | 数量 | 出现在 |
| --- | --- | --- |
| `POST, GET, PUT, DELETE` | 206 | DB（绝大多数） |
| `GET, PUT, DELETE` | 9 | DB（ACTL-M1、EIGV-M1、NLCT-M1、POGD-M1、STCT-M1、STYP-M1、THGC-M1、THOO-M1、HHCT-M1 等 Hyper-S 控制类） |
| `GET, PUT` | 7 | DB（CO_M / CO_S / CO_T / CO_F / MATD 等，与主文档 §2「Unit、Structure Type 只支持 GET/PUT」同类） |
| `POST, GET, PUT` | 4 | DB（BNGR / GRUP / CLDR 等分组类） |
| `POST` | 232 | DOC 11 + OPE 15 + VIEW 6 + POST 200 |
| `GET` | 3 | OPE.PROJECTSTATUS、OPE.SECTPROP、VIEW.SELECT |
| `GET, POST` | 2 | OPE.STORY_PARAM、OPE.STORY_IRR_PARAM |
| 手册未列 | 1 | `DB.SWIND`（Static Wind Load - KDS(41-12:2022)）→ **编码前必须真机确认** |

对 `midas_db_delete` 的影响：只有 215 个 DB key 支持 DELETE；其余 12 个（9 + 1 + 2… 按上表精确判断）必须在删除前返回结构化错误，不得发出请求。

### 5.3 Wrapper 规则（实测确认）

```yaml
# DB 命名空间：写入体第一层为 Assign
wrapper:
  write: Assign
  read_root: <CODE>        # 例如 NODE

# DOC / OPE / VIEW / POST：写入体第一层为 Argument
wrapper:
  write: Argument
```

实测样例（NODE，来自手册 Input Data Example）：

```json
{
  "Assign": {
    "901": { "X": -1, "Y": -1, "Z": -1 },
    "902": { "X": -2, "Y": -2, "Z": -2 }
  }
}
```

实测样例（`POST.TABLE.LOAD_SUMMARY_X`）：

```json
{
  "Argument": {
    "TABLE_NAME": "Example",
    "TABLE_TYPE": "LOAD_SUMMARY_X",
    "EXPORT_PATH": "C:\\MIDAS\\Result\\Load_Summary_X_Output.JSON"
  }
}
```

### 5.4 POST 命名空间公共参数（N5）

所有 `/post/TABLE`、`/post/TEXT` key 共享以下参数，应在 Registry 中提取为公共定义，237 个 key 只覆盖差异部分：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `Argument.TABLE_NAME` | string | 输出表名 |
| `Argument.TABLE_TYPE` | string | 表类型（决定 Registry key，必填） |
| `Argument.EXPORT_PATH` | string | 结果落盘路径 |
| `Argument.UNIT` | object | `FORCE / DIST / HEAT / TEMP` 等响应单位 |
| `Argument.STYLES` | object | `FORMAT`（Fixed / Scientific / General / Exponential）、`PLACE`（小数位） |
| `Argument.NODE_ELEMS` | object | 构件范围：`TO` / `KEYS[]` / `STRUCTURE_GROUP_NAME` 三选一（schema 用 `anyOf` 表达） |

---

## 6. Schema 来源与 `info/` 自省机制（新增能力 N1 / N2）

### 6.1 实测事实

中文手册每个 DB 页面的 `Input Data Form` 指向：

```text
{base url} + info/db/{CODE}
```

实测出现 161 次，覆盖 **154 个不同 DB 代码**（占 227 个 DB key 的 67.8%）。返回内容是该 Endpoint 的字段定义，形式为：

```json
{
  "NODE": {
    "X": { "__DESC__": "GLOBAL X-POSITION", "__TYPE__": "Real" },
    "Y": { "__DESC__": "GLOBAL Y-POSITION", "__TYPE__": "Real" },
    "Z": { "__DESC__": "GLOBAL Z-POSITION", "__TYPE__": "Real" }
  }
}
```

英文官方手册对同一 Endpoint 给出的是标准 draft-07 JSON Schema（`$schema` / `type` / `properties` / `required` / `enum` / `anyOf`），语义等价、形式不同。

### 6.2 三源 Schema 策略（回写主文档 §22.6 / §92）

```text
schema_ref 解析顺序
  1. 本地缓存  schema/gen_nx/{registry_version}/{CODE}.json   ← 命中即用（< 10 ms）
  2. info 回源  {base url} + info/db/{CODE}                   ← 未命中或版本不符时拉取
  3. 手册兜底  registry/manual/gen_nx/{CODE}.schema.json      ← 离线 / 回源失败时使用
```

缓存键：

```text
{software_id} + {midas_version} + {registry_version} + {CODE} + {source_hash}
```

缓存失效：`ConnectionProfile.last_checked_at` 变化、MIDAS 版本变化、Registry 版本升级时失效。

### 6.3 与 `include_schema` 的关系（回写主文档 §6）

`midas_db_query.options.include_schema = true` 时：

```text
1. 先返回已缓存的 schema（若存在）
2. 若无缓存 → 调用 info/db/{CODE}
3. 若 info 不可用 → 返回手册 JSON Schema，并在响应中标注 schema_source = "manual"
4. 永不因为 schema 缺失而阻断查询本身
```

响应中必须带 `schema_source`（`cache` / `info` / `manual`）与 `schema_hash`，便于审计与复现。

---

## 7. POST 结果层实测结构（回写主文档 §54）

### 7.1 只有 4 个 URI

```text
/post/TABLE             ← 所有“表格型”结果（含施工阶段、时程、推覆、水化热、预分析表）
/post/TEXT              ← 所有“文本型”时程 / 推覆结果
/post/PM                ← P-M 交互图（Design）
/post/STEELCODECHECK    ← 钢结构规范校核（Design）
```

表/文本类型由 `Argument.TABLE_TYPE` 决定。因此 Registry key 采用：

```text
POST.TABLE.<TABLE_TYPE>
POST.TEXT.<TABLE_TYPE>
POST.PM
POST.STEELCODECHECK
```

### 7.2 237 个 key 的分组

| 官方分区 | key 数 | Registry key 前缀 | 代表项 |
| --- | --- | --- | --- |
| Analysis Result Table | 97 | `POST.TABLE.*` | DISPLACEMENTG、DISPLACEMENTL、REACTIONG、REACTIONL、BEAMFORCE、BEAMSTRESS、PLATEFORCEG、TRUSSFORCE、SOLIDFG、EIGENVALUEMODE、BUCKLINGMODE、PARTICIPATIONVECTORMODE、CABLEFORCE、TNDN_*、GENERAL_LINK_FORCE、ELASTICLINK、RESULTANT_FORCES、COMPSECTBEAMFORCE、EQUILIBRIUM_ELEM_FORCE、INITIAL_ELEM_FORCE |
| Time History Result Table | 52 | `POST.TABLE.*` | THISDISPLACEMENT、THISVELOCITY、THISABSOLUTEACCEL、THISRELATIVEACCEL、THISBEAMFORCE、THISGLINKFORCE、IEHG_FORCE_*、IEHG_DEFORM_*、IEHG_DUCT_D1/D2_*、FIBR_* |
| Analysis Story Table | 25 | `POST.TABLE.*` | STORY_DISPLACEMENT_X/Y/COMB、STORY_DRIFT_X/Y/COMB、STORY_SHEAR_FOR_RS、STORY_STABILITY_COEFFICIENT_X/Y、TORSIONAL_IRREGULARITY_X/Y、STIFFNESS_IRREGULARITY_X/Y、WEIGHT_IRREGULARITY_X、OVERTURNING_MOMENT、STORY_MODE_SHAPE |
| Time History Text | 19 | `POST.TEXT.*` | TH_DISP、TH_VELOCITY、TH_ACCEL、TH_BEAMFORCE、TH_BEAMSTRESS、TH_TRUSSFORCE、TH_TRUSSSTRESS、TH_PLATEFORCE、TH_PLATESTRESS、TH_SOLIDFORCE、TH_SOLIDSTRESS、TH_WALLFORCE、TH_GLINKFORCE、TH_GLINKDEFORM、TH_PLANE_STRESS_FORCE、TH_PLANE_STRAIN_FORCE |
| Pre-Process Table | 17 | `POST.TABLE.*` | ELEMENTWEIGHT、LOAD_SUMMARY_X/Y/Z、MASS_SUMMARY_X/Y/Z、STORY_MASS、STORY_LOAD_SUMMARY_X/Y/Z、STORYWEIGHT、MATERIAL、SECTIONALL、SUPPORTS、NODALBODYFORCE |
| Design | 11 | `POST.TABLE.*` + 2 独立 URI | BEAMDESIGNFORCES、COLUMNDESIGNFORCES、BRACEDESIGNFORCES、WALLDESIGNFORCES、STEELMEMBERDESIGNFORCES、SRCBEAMDESIGNFORCES、SRCCOLUMNDESIGNFORCES、COLDFORMEDSTEELMEMBERDESIGNFORCES、`POST.PM`、`POST.STEELCODECHECK` |
| Pushover Text | 10 | `POST.TEXT.*` | PO_DISP、PO_BEAMFORCE、PO_BEAMSTRESS、PO_TRUSSFORCE、PO_TRUSSSTRESS、PO_WALLFORCE、PO_ELINKFORCE、PO_ELINKDEFORM、PO_GLINKFORCE、PO_GLINKDEFORM |
| Heat of Hydration Result Table | 6 | `POST.TABLE.*` | HEAT_HYDR_DISPLACEMENT、HEAT_HYDR_TEMPERATURE、HEAT_HYDR_STRESS_G、HEAT_HYDR_STRESS_L、HEAT_HYDR_TENS_STRESS、HEAT_HYDR_PIPE_NODE_TEMP |

### 7.3 对结果引擎的直接影响

1. **全局/局部必须显式**：`DISPLACEMENTG` / `DISPLACEMENTL`、`REACTIONG` / `REACTIONL`、`PLATEFORCEG` / `PLATEFORCEL` 是**不同表**。主文档 §59 的 `MAX_DISPLACEMENT` 类查询必须带上坐标系维度，否则结果不可比。
2. **层间位移角必须带方向**：`STORY_DRIFT_X` / `_Y` / `_COMB`。主文档 §90 的 `structai://project/results/summary` 里 `max_drift` 字段应拆为 `max_drift_x` / `max_drift_y` / `max_drift_comb`。
3. **时程/推覆结果体量最大**：`/post/TEXT` 类结果通常是逐时程步的文本序列，必须走 ASYNC/LONG 路径（补充文档 §2.2/§2.3），且强制落 ResultStore 后只回 Summary。
4. **`EXPORT_PATH` 是双通道**：MIDAS 既可通过 HTTP 响应返回结果，也可写文件到 `EXPORT_PATH`。Registry 需标注该 key 的 `output.mode`（`response` / `file` / `both`），文件模式下 Result Parser 需读取落盘文件。

---

## 8. 产品 / 求解器约束实测清单（回写主文档 §13 / §124）

官方索引用上标记号表达约束：`ᴴˢ⁾` = Hyper-S 专属，`ᴶ⁾` = 网格模型分析专属。共 21 条：

| Registry key | URI | Methods | 官方标题 | 约束 |
| --- | --- | --- | --- | --- |
| DB.STYP-M1 | `/db/STYP-M1` | GET/PUT/DELETE | Structure Type | `ᴴˢ⁾` |
| DB.MATL-M1 | `/db/MATL-M1` | POST/GET/PUT/DELETE | Material Properties | `ᴴˢ⁾` |
| DB.IMFM-M1 | `/db/IMFM-M1` | POST/GET/PUT/DELETE | Inelastic Material Link for Auto Generation | `ᴴˢ⁾` |
| DB.EPMT-M1 | `/db/EPMT-M1` | POST/GET/PUT/DELETE | Plastic Material | `ᴴˢ⁾` |
| DB.IEHG-BEAM-M1 | `/db/IEHG-BEAM-M1` | POST/GET/PUT/DELETE | Assign Inelastic Hinges - Beam | `ᴴˢ⁾` |
| DB.IEHG-TRUSS-M1 | `/db/IEHG-TRUSS-M1` | POST/GET/PUT/DELETE | Assign Inelastic Hinges - Truss | `ᴴˢ⁾` |
| DB.IEHG-GL-M1 | `/db/IEHG-GL-M1` | POST/GET/PUT/DELETE | Assign Inelastic Hinges - General Link | `ᴴˢ⁾` |
| DB.IEHG-PSS-M1 | `/db/IEHG-PSS-M1` | POST/GET/PUT/DELETE | Assign Inelastic Hinges - Point Spring Support | `ᴴˢ⁾` |
| DB.NLNK-M1 | `/db/NLNK-M1` | POST/GET/PUT/DELETE | General Link | `ᴴˢ⁾` |
| DB.THGC-M1 | `/db/THGC-M1` | GET/PUT/DELETE | Time History Global Control | `ᴴˢ⁾` |
| DB.THOO-M1 | `/db/THOO-M1` | GET/PUT/DELETE | Time History Output Option | `ᴴˢ⁾` |
| DB.THIS-M1 | `/db/THIS-M1` | POST/GET/PUT/DELETE | Time History Load Cases | `ᴴˢ⁾` |
| DB.ACTL-M1 | `/db/ACTL-M1` | GET/PUT/DELETE | Main Control Data | `ᴴˢ⁾` |
| DB.EIGV-M1 | `/db/EIGV-M1` | GET/PUT/DELETE | Eigenvalue Analysis Control | `ᴴˢ⁾` |
| DB.NLCT-M1 | `/db/NLCT-M1` | GET/PUT/DELETE | Nonlinear Analysis Control | `ᴴˢ⁾` |
| DB.STCT-M1 | `/db/STCT-M1` | GET/PUT/DELETE | Construction Stage Analysis Control Data | `ᴴˢ⁾` |
| DB.BCGD-M1 | `/db/BCGD-M1` | POST/GET/PUT/DELETE | Define Boundary Combination | `ᴴˢ⁾` |
| DB.BCGA-M1 | `/db/BCGA-M1` | POST/GET/PUT/DELETE | Assign Boundary Combination | `ᴴˢ⁾` |
| DB.POGD-M1 | `/db/POGD-M1` | GET/PUT/DELETE | Pushover Global Control | `ᴴˢ⁾` |
| DB.POLC-M1 | `/db/POLC-M1` | POST/GET/PUT/DELETE | Pushover Load Case | `ᴴˢ⁾` |
| DB.GALD | `/db/GALD` | DELETE/GET/POST/PUT | Grid Analysis Load | `ᴶ⁾` |

要点：

- `-M1` 后缀**不是版本号**，而是"同一功能的 Hyper-S 求解器变体"，其 URI 与标准版本并存（如 `/db/STYP` 与 `/db/STYP-M1`）。
- Hyper-S 变体的 methods **普遍比标准版少**（多为 GET/PUT/DELETE，缺 POST），与主文档 §62「不能在不知道 MIDAS 进程状态的情况下自动重复启动计算」的保守策略一致。
- 手册正文的 `Input URI` **丢弃了上标标记**（写作 `db/STYP-M1`），因此 **solver 约束只能从官方索引读取，不能从正文推断**——Registry 生成脚本必须同时读索引与正文。
- 不匹配时必须返回主文档 §104 的 `SOLVER_UNSUPPORTED`，且错误详情带 `required_solver` 与 `current_solver`。

---

## 9. 第一批 Registry 实测定义（回写主文档 §111）

### 9.1 实测表（可直接落地）

| Registry key | URI | Methods | Wrapper | Schema | 结论 |
| --- | --- | --- | --- | --- | --- |
| `DOC.NEW` | `/doc/NEW` | POST | Argument | 官方 | ✅ 命中 |
| `DOC.OPEN` | `/doc/OPEN` | POST | Argument | 官方 | ✅ 命中 |
| `DOC.SAVE` | `/doc/SAVE` | POST | Argument | 官方 | ✅ 命中 |
| `DOC.ANAL` | `/doc/ANAL` | POST | Argument | 官方 | ✅ 命中（risk=high，retryable=false） |
| `DB.UNIT` | `/db/UNIT` | POST/GET/PUT/DELETE | Assign | 官方 + `info/db/UNIT` | ✅ 命中 |
| `DB.STYP` | `/db/STYP` | POST/GET/PUT/DELETE | Assign | 官方 + `info/db/STYP` | ✅ 命中（另有 `DB.STYP-M1` 为 Hyper-S） |
| `DB.PJCF` | `/db/PJCF` | POST/GET/PUT/DELETE | Assign | 官方 + `info/db/PJCF` | ✅ 命中 |
| `DB.MATL` | `/db/MATL` | POST/GET/PUT/DELETE | Assign | 官方 + `info/db/MATL` | ✅ 命中（另有 `DB.MATL-M1` 为 Hyper-S） |
| `DB.SECT` | `/db/SECT` | POST/GET/PUT/DELETE | Assign | 官方 + `info/db/SECT` | ✅ 命中 |
| `DB.NODE` | `/db/NODE` | POST/GET/PUT/DELETE | Assign | 官方 + `info/db/NODE` | ✅ 命中（主文档 §23 示例正确） |
| `DB.ELEM` | `/db/ELEM` | POST/GET/PUT/DELETE | Assign | 官方 + `info/db/ELEM` | ✅ 命中 |
| `DB.CONS` | `/db/CONS` | POST/GET/PUT/DELETE | Assign | 官方 + `info/db/CONS` | ✅ 命中 |
| `DB.STLD` | `/db/STLD` | POST/GET/PUT/DELETE | Assign | 官方 | ✅ 命中 |
| `DB.BMLD` | `/db/BMLD` | POST/GET/PUT/DELETE | Assign | 官方 | ✅ 命中 |
| ~~`DB.LCOM`~~ | — | — | — | — | ❌ **不存在**，见 §9.2 |
| `VIEW.CAPTURE` | `/view/CAPTURE` | POST | Argument | 官方 | ✅ 命中 |
| `VIEW.ANGLE` | `/view/ANGLE` | POST | Argument | 官方 | ✅ 命中 |
| `VIEW.DISPLAY` | `/view/DISPLAY` | POST | Argument | 官方 | ✅ 命中 |
| `VIEW.RESULTGRAPHIC` | `/view/RESULTGRAPHIC` | POST | Argument | 官方 | ✅ 命中（231 个图形类型枚举，见 CSV） |
| ~~`POST.REACTION`~~ | — | — | — | — | ❌ **不存在**，见 §9.2 |
| ~~`POST.DISPLACEMENT`~~ | — | — | — | — | ❌ **不存在**，见 §9.2 |
| `POST.TABLE.BEAMFORCE` | `/post/TABLE` | POST | Argument | 官方 | ✅ 命中 |
| `POST.TABLE.BEAMSTRESS` | `/post/TABLE` | POST | Argument | 官方 | ✅ 命中 |
| ~~`POST.STORYDRIFT`~~ | — | — | — | — | ❌ **不存在**，见 §9.2 |

### 9.2 必须修正的 4 个 key（重要）

| 主文档 §111 原 key | 实测真实 key | 说明 |
| --- | --- | --- |
| `LCOM` | `LCOM-GEN`、`LCOM-CONC`、`LCOM-STEEL`、`LCOM-SRC`、`LCOM-STLCOMP`、`LCOM-SEISMIC` | `/db/LCOM` 不存在。荷载组合按**设计类型**分表：GEN（通用）/ CONC（混凝土）/ STEEL（钢结构）/ SRC（型钢混凝土）/ STLCOMP（钢-混组合）/ SEISMIC（抗震）。另有同名的 OPE 版本（`OPE.LCOM-*`，用于自动生成组合），两者语义不同、不可混用 |
| `REACTION` | `REACTIONG`、`REACTIONL` | 全局 / 局部坐标系反力是两张不同的表（`POST.TABLE.REACTIONG` / `POST.TABLE.REACTIONL`），另有 `REACTIONSURFACESPRING`、`REACTIONLSURFACESPRING` |
| `DISPLACEMENT` | `DISPLACEMENTG`、`DISPLACEMENTL` | 同上，全局 / 局部 |
| `STORYDRIFT` | `STORY_DRIFT_X`、`STORY_DRIFT_Y`、`STORY_DRIFT_COMB` | 层间位移角必须带方向；`_COMB` 为组合包络 |

### 9.3 第一批 Registry 落地样例（YAML）

```yaml
# registry/common/db/NODE.yaml
key: DB.NODE
namespace: DB
uri: /db/NODE
methods: [POST, GET, PUT, DELETE]

tool_map:
  query: midas_db_query
  assign: midas_db_assign
  delete: midas_db_delete

wrapper:
  write: Assign
  read_root: NODE

schema_ref:
  local: schema/gen_nx/2026/NODE.json
  introspect: info/db/NODE
  manual: registry/manual/gen_nx/NODE.schema.json

parser: db_generic

product: [GEN_NX, CIVIL_NX]
solver: [STANDARD, HYPER_S]

risk:
  level: low
  destructive: false

runtime:
  requires_project: true
  requires_analysis: false
  timeout_ms: 30000
  retryable: true

execution:
  mode: FAST
  idempotent: true

capability: [MODEL]

source:
  official: true
  title: Node
  url: https://support.midasuser.com/hc/en-us/articles/36007474963609-Node
  retrieved_at: 2026-07-14

dependencies:
  - endpoint: DB.ELEM
    relation: referenced_by
  - endpoint: DB.CONS
    relation: referenced_by
```

```yaml
# registry/common/post/TABLE/BEAMFORCE.yaml
key: POST.TABLE.BEAMFORCE
namespace: POST
uri: /post/TABLE
methods: [POST]

tool_map:
  query: midas_db_query

wrapper:
  write: Argument

fixed_arguments:
  TABLE_TYPE: BEAMFORCE

schema_ref:
  local: schema/gen_nx/2026/post/TABLE/BEAMFORCE.json
  manual: registry/manual/gen_nx/post/TABLE/BEAMFORCE.schema.json

parser: post_table

risk:
  level: low
  destructive: false

runtime:
  requires_project: true
  requires_analysis: true
  timeout_ms: 120000
  retryable: false

execution:
  mode: ASYNC
  idempotent: true

output:
  type: table
  mode: both          # response + EXPORT_PATH 文件

report:
  category: analysis_result
  figure_type: beam_force
```

### 9.4 第一 / 第三阶段验收的 Registry 覆盖建议

| 阶段 | 建议纳入的 key | 数量 |
| --- | --- | --- |
| 第一阶段（打通链路） | DOC.NEW/OPEN/SAVE/ANAL + DB.UNIT/STYP/PJCF/NODE/ELEM + OPE.PROJECTSTATUS | 10 |
| 第二阶段（完整钢框架） | DB.MATL/SECT/CONS/STLD/BMLD/GRUP/BNGR/LDGR + DB.LCOM-GEN | 9 |
| 第三阶段（分析闭环） | DB.ACTL/EIGV + POST.TABLE.DISPLACEMENTG/DISPLACEMENTL/REACTIONG/REACTIONL/BEAMFORCE/BEAMSTRESS/STORY_DRIFT_X/STORY_DRIFT_Y + VIEW.CAPTURE/ANGLE/DISPLAY/RESULTGRAPHIC | 16 |

三个阶段合计 35 个 key（占 501 的 7%），足以支撑主文档 §139–§141 的验收标准。

---

## 10. 对主文档的逐条回写建议

| 主文档章节 | 建议改动 | 优先级 |
| --- | --- | --- |
| §5.1 / §5.1.1 | 保留 11 个 DOC 命令（实测一致）；补一句：`UFIG` 属旧版 DOC Control，新版本用 `VIEW.CAPTURE` 承载截图，仅通过 Version Override 保留 | 低 |
| §6 `midas_db_query` | `options.include_schema` 改为调用 `info/db/{CODE}`；响应增加 `schema_source` / `schema_hash` | 高 |
| §22.4 methods | 补"必须逐条录入，不得统一假设"；附 §5.2 的组合分布表 | 高 |
| §22.6 schema_ref | 改为三源结构 `{local, introspect, manual}` | 高 |
| §22.9 solver | 补取值 `STANDARD` / `HYPER_S` / `GRID_MODEL`，并说明 `-M1` 变体的语义 | 高 |
| §23 NODE 示例 | 补 `schema_ref.introspect: info/db/NODE`、`source.url`、`methods` 实测值 | 中 |
| §24 POST/TABLE 示例 | 补公共参数 `TABLE_NAME` / `EXPORT_PATH` / `UNIT` / `STYLES` / `NODE_ELEMS`；补 `output.mode` | 中 |
| §52 OPE 列表 | 无需改动（实测 19 项完全一致） | — |
| §53 VIEW 列表 | 无需改动（实测 7 项完全一致） | — |
| §54 POST 层 | 替换为 §7 的 4 URI + 237 key 分组结构 | 高 |
| §59 Result Intelligence | `MAX_DISPLACEMENT` 类查询必须带坐标系（G/L）；层间位移带方向（X/Y/COMB） | 高 |
| §62 分析执行规则 | 补：Hyper-S 变体普遍不支持 POST，写入路径需按 methods 分流 | 中 |
| §90 结果 Summary Resource | `max_drift` 拆为 `max_drift_x` / `max_drift_y` / `max_drift_comb` | 中 |
| §104 失败处理 | `SOLVER_UNSUPPORTED` 详情补 `required_solver` / `current_solver` | 中 |
| §108 生产目录 | 增加 `registry/manual/`（手册生成的 schema 兜底）与 `tools/manual2registry/`（生成链） | 中 |
| §111 第一批 Registry | 按 §9.1 替换；**必须修正 4 个 key**（LCOM / REACTION / DISPLACEMENT / STORYDRIFT），见 §9.2 | **最高** |
| §113 测试矩阵 | Registry 组增加：手册 → Registry 生成回归测试、`info/` 自省一致性测试、Hyper-S 约束拒绝测试 | 中 |
| §123 官方覆盖原则 | 用 §4 的 33 分区 → 5 命名空间映射替换现有 6 大类描述 | 中 |
| §124 产品差异策略 | 补 `solver` 字段与 `ᴴˢ⁾` / `ᴶ⁾` 约束表达方式 | 中 |
| §139 第一阶段验收 | 建议按 §9.4 把第一阶段 Registry 覆盖锁定为 10 个 key | 高 |
| §145 核心原则 | 建议新增第 21 条：**Registry 必须能由官方手册机械生成，禁止手工誊抄** | 中 |

---

## 11. 数据质量说明与待确认问题

### 11.1 手册自身的数据质量问题（生成脚本必须处理）

| # | 现象 | 处理建议 |
| --- | --- | --- |
| D1 | `POST.TABLE.CABLEEFFICIENCY` 与 `POST.TABLE.CABLEEFFIENCY` **两种拼写同时存在** | 以官方索引为准保留一种；另一种作为 alias 记录，不建独立 key |
| D2 | 抽取出现 `POST.TABLE.string` 等伪影（来自 schema 的 `default` / 类型名） | 生成脚本需按 `Argument.properties.TABLE_TYPE.enum` 与 Examples 双源交叉校验，剔除伪影 |
| D3 | `DB.SWIND` 手册页面**未列 Active Methods** | 编码前真机确认；确认前该 key 标记 `methods: unknown`，Dispatcher 拒绝执行 |
| D4 | `POST.TABLE.PLATEFORCEUG` / `PLATEFORCEUL` / `PLATEFORCEUGVBM` 等命名不统一（有的带 G/L 后缀，有的不带） | 逐条以官方索引为准，不做批量改名 |
| D5 | `Design` 分区的 `POST.TABLE.string`（来自 `*DESIGNFORCES` 页） | 归入伪影，剔除 |

### 11.2 待确认问题（编码前必须裁决）

| # | 问题 | 影响 |
| --- | --- | --- |
| Q8 | `info/db/{CODE}` 覆盖 154/227（67.8%）。剩余 73 个 DB key 是否支持自省？是否需要权限？ | 决定 Schema 三源策略中"info 回源"的覆盖率，以及是否必须保留手册兜底 |
| Q9 | URI 大小写敏感性：官方索引大写 vs 中文手册小写 | 决定 Adapter 是否需要大小写归一化与重试 |
| Q10 | Hyper-S 变体（`-M1`）应作为独立 Registry key，还是同一 key 按 Runtime Solver 切换 URI？ | 影响 Registry 结构与 RuntimeContext 设计。**建议独立 key + `solver: HYPER_S` 约束**，理由：methods 集不同 |
| Q11 | 本文只覆盖 **GEN NX**。CIVIL NX 的 DB 覆盖面与 GEN 不同（如桥梁专用 Endpoint） | 第二份 Registry 需按同一流程对 CIVIL NX 手册另行录入，不能直接复用 |
| Q12 | 手册「英文数据手册（未编入索引）」区（行 325,859 起）含 `DESIGN/PSC/AASHTO-LRFD24`、`DESIGN/RC/DRC`、`DESIGN/RC/KDS-41-20-2022`、`DESIGN/SRC/AIK-SRC2K`、`DESIGN/STEEL/KDS-41-30-2022`、`RATING/PSC/AASHTO-LRFR19`、`其他` 共 7 个分区 | 属**规范设计专用 DB**，量级约 85,000 行。主文档 §65 Design Engine 需要它们，应在第四阶段前补充录入 |
| Q13 | `EXPORT_PATH` 文件模式下的结果解析责任划分（MIDAS 落盘 vs MCP 读文件） | 影响 Result Parser 与 ResultStore 设计 |

---

## 12. 附件与复现

### 12.1 附件

`StructAI_MIDAS_MCP_GEN_NX_Endpoint清单_v1.0.csv` —— 501 行，UTF-8 with BOM，可直接作为 Registry 生成器的输入。

| 字段 | 说明 |
| --- | --- |
| `registry_key` | 逻辑 key，如 `DB.NODE`、`POST.TABLE.BEAMFORCE`、`VIEW.CAPTURE` |
| `namespace` | `DOC` / `DB` / `OPE` / `VIEW` / `POST` |
| `uri` | 实测 URI，如 `/db/NODE` |
| `methods` | 实测方法集，`/` 分隔，如 `POST/GET/PUT/DELETE` |
| `table_type` | POST 命名空间的 `TABLE_TYPE` 值（其他命名空间为空） |
| `solver` | `HYPER_S` / `GRID_MODEL`（无约束为空） |
| `schema` | 是否有官方 JSON Schema（`yes`） |
| `spec_rows` | Specifications 字段表行数（用于生成 Level 1 校验） |
| `section` | 官方分区名，如 `Analysis Result Table` |
| `title` | 官方页面标题 |
| `source_url` | 官方原文 URL（可直接写入 Registry `source.url`） |

### 12.2 复现步骤

```text
1. 读取 G:\MIDAS-API-Online-Manual\tools\cache\_en_index_rows.json
   → 得到 33 分区 / 274 个带 URI 的官方 Endpoint（含 ᴴˢ⁾ / ᴶ⁾ 约束标记）

2. 读取 G:\MIDAS-API-Online-Manual\manual\midas Gen API 使用手册.md
   定位 "## 英文数据手册（索引接口）" 至 "## 英文数据手册（未编入索引）"（行 54,970–325,858）
   按 "### 分区" / "#### 页面" 切分 → 475 个 Endpoint 页面

3. 每页抽取：Input URI、Active Methods、JSON Schema、Examples、Specifications、官方 URL

4. 合并：以「官方索引」提供 URI 与 solver 约束，「正文」提供 methods 与 schema
   → 501 个 Registry 逻辑 key

5. 输出：gen_nx_endpoint_inventory.csv（即附件）
```

关键实现细节（避免踩坑）：

- 正文 `Input URI` 会丢弃 `ᴴˢ⁾` / `ᴶ⁾` 上标，**solver 约束只能从官方索引取**。
- JSON Schema 块前有 `Details` 文字与 ```` ```json ```` 围栏，解析前必须先剥离围栏。
- `TABLE_TYPE` 有两个来源：schema 的 `enum`（多数）与 Examples 的 `"TABLE_TYPE": "X"`（Pre-Process Table 类）。**两处都要扫**。
- 有 3 个页面的示例 JSON 不是围栏代码块（Story Mass Summary / Story Load Summary / Story Weight），且键值之间被换行拆开，需要跨行正则。

### 12.3 统计校核

| 项 | 值 |
| --- | --- |
| 官方索引 Endpoint | 274 |
| 正文页面 | 475 |
| 唯一 URI | 268 |
| Registry key | 501 |
| 分区数 | 33 |
| Hyper-S / 网格模型约束 key | 20 / 1 |
| 官方 JSON Schema 页面 | 444 |
| Specifications 表页面 | 498 |

---

## 13. 结论与边界

1. 主文档在 **DOC / OPE / VIEW 命名空间、URI 形式、`Assign` 包装、`POST.TABLE + TABLE_TYPE` 设计**上全部经实测验证正确，无需返工。
2. 主文档真正缺的是**知识层的量**与**四个机制**：`info/` 自省、三源 Schema、逐条 methods、solver 约束。本文已补齐，并给出 §10 的逐条回写建议。
3. 第一批 Registry 必须修正 4 个 key（§9.2），这是会直接影响第一/第三阶段验收的硬错误。
4. 本文边界：只覆盖 **GEN NX**，且未纳入「未编入索引」区的 7 个规范设计专用分区（约 85,000 行）。这两块需按同一流程另行录入。

> 本文为 MIDAS GEN NX 的 **API 知识层实测基线**。后续 MIDAS 手册更新时，按 §12.2 重跑生成链，产出新的 `registry_version` 并保留旧版本，符合主文档 §121 的版本与兼容性策略。
