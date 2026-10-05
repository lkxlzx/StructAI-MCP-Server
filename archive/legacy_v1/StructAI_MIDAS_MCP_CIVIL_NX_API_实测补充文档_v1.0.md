# StructAI｜MIDAS CIVIL NX API 实测补充文档 V1.0

> ⚠️ **非规范性文档（NON-NORMATIVE）** —— 本文件已归档至 `archive/legacy_v1/`，
> 属 StructAI 早期（V1）规范草案 / 实测记录，**不作为开发依据，不作为准则**。
> 开发唯一依据：`docs/01`–`docs/06`（V2 规范）· `docs/07`（开发方案与任务续接）· `registry/`（机器可读端点注册表）。

> 本文是《StructAI 多结构工程软件一体化 MCP 完整开发文档 V1.0》的**第四份配套文档**。
>
> 前三份：① 主开发文档（总规范）；② 快速响应与实时反馈架构补充文档（执行与反馈层）；③ MIDAS GEN NX API 实测补充文档（GEN NX 知识层 + 四个机制）。
>
> 本文只做一件事：**用 `G:\midas Civil NX - API`（midas Civil NX API 用户手册）的真实数据，建立 CIVIL NX 的知识层，并给出 GEN NX 与 CIVIL NX 的产品差异矩阵**。不修改前三份文档的核心原则。

---

## 1. 数据来源与规模

| 项 | 内容 |
| --- | --- |
| 主来源 | `G:\midas Civil NX - API\md\midas Civil NX - API 用户手册.md`（5,024,858 字节 / 162,153 行） |
| 在线来源 | wolai `https://www.wolai.com/midasit/pgwwxjjUbjMa7CkMJRtAhC` |
| 数据快照 | 源页面 `edited_time` = **2024-12-26**；文档自述「Latest Updated：2024.12」 |
| 文档自述规模 | 624 个页面 · 1638 个标题 · 565 张表格 · 1496 段代码示例 · 864 张截图 |
| 图片资源 | `md/assets/`（811 张 PNG + 1 SVG + 1 JPG） |
| 抓取链 | `_scrape/crawl.js → closure.js → render.js → validate.js`（块树 12,936 块，`errors.json` 为空） |
| 结构 | 前置区（入门学习 / 编程语言 / 提示技巧 / API 补充知识 / 案例 / 留言板）+ **JSON手册区（行 2339 起）** |

JSON手册区实测结构：**21 个 H3 · 60 个 H4 · 147 个 H5 · 1303 个 H6**。

与 GEN NX 手册的关键差异（影响抽取方法）：

| 维度 | GEN NX 手册 | CIVIL NX 手册 |
| --- | --- | --- |
| 单文件体量 | 12.1 MB / 410,979 行 | 5.0 MB / 162,153 行 |
| 官方英文索引 | 有（`_en_index_rows.json`，430 行 / 274 个带 URI 的 Endpoint） | **无**（只有中文 wolai 单源） |
| 求解器约束标记 | 有（`ᴴˢ⁾` / `ᴶ⁾`，21 条） | **无**（全文 0 处） |
| 代码标识 | 中文区 `接口代码：`，英文区无 | 内嵌于标题：`##### 中文[CODE]英文` |
| 页面标题层级 | 统一 `####` | **不统一**：`#####`（69 个带 [CODE] + 36 个 `[CODE]` 开头）与 `######` 混用 |
| 子块标记 | 统一 `##### **Input URI**` 等 | **两种混用**：`###### Input URI` 与 `**Input URI**` |
| `info/` 自省 | 161 次 | **181 次**（覆盖率更高） |
| 快照时间 | 2026-07（官方英文手册实时更新） | 2024-12 |

---

## 2. CIVIL NX 手册自身给出的 API 规范（可直接回写主文档）

以下均为手册**明文规定**，不是推断，可作为主文档 §2 / §22 / §50 / §100 的权威补充：

### 2.1 URL 结构

```text
base URL + Resource path
Resource path 分两步，第二步取决于第一步：
| 1st path | 2nd path                        | 说明                     |
| doc      | new, open, close, save, saveas… | 文档级动作               |
| db       | unit, node, elem, sect, matl…   | 构成文件的全部数据库      |
| post     | table                           | 文本后处理（表格）        |
| view     | capture, active, display…       | 图形后处理（模型视图窗口）|
| ope      | sectprop, uslc                  | 操作级能力               |
```

### 2.2 CRUD 规则（逐命名空间）

```text
doc   → 只允许 POST（它执行“动作”，读/改/删无意义）
db    → 允许全部 CRUD*
post  → 语义上是“读”，但实际由产品生成并发送数据，因此用 POST
view  → 同上，用 POST
ope   → 按 2nd path 选择 POST / GET

* /db/unit、/db/styp 等含唯一值的数据库只允许 PUT/GET，创建与删除不可能
```

这与本文实测的 methods 分布完全一致（见 §3.3）。

### 2.3 大小写：**区分大小写**

手册「JSON基本结构」明文第 4 条：

> 区分大小写字母。

**这直接回答了 GEN NX 补充文档遗留的 Q9**：URI、键名、值均区分大小写，Registry 必须使用官方索引的精确大小写形式，Adapter **不得**做大小写归一化后盲目重试。

### 2.4 首键与键名规则

```text
1. POST/PUT 时，第一层键为 "Argument"（doc / post / view / ope）或 "Assign"（db）
2. 除首键外，键名通常以大写字母开头；特定情况下可以小写开头（如 "b"、"i"、"n"、"v"）
3. 键名不含空格，用下划线分隔字母
4. 区分大小写
```

### 2.5 数据索引约定

```text
db 的第二层键是数字字符串：
  - 唯一标识符（节点号、单元号、材料号、截面号…）
  - 或有序数据的索引（如荷载组合）
  - 即使是 /db/unit、/db/styp 这类“唯一数据”，也使用索引值 "1"
```

### 2.6 Schema 自省（与 GEN 一致）

Civil 手册的 `Input Data Form` 同样指向：

```text
{base url} + info/db/{CODE}
```

实测出现 **181 次**（GEN 为 161 次）。返回形式为 `{ "__DESC__": ..., "__TYPE__": ... }` 字段定义。

**结论：GEN NX 补充文档 §6 的三源 Schema 策略对 CIVIL NX 同样适用，且覆盖率更高。**

---

## 3. CIVIL NX 实测总量

### 3.1 抽取结果

| 指标 | 数值 |
| --- | --- |
| 手册中 `Input URI` 记录 | **455** |
| 可落地的 Registry 逻辑 key | **379** |
| 唯一 URI | 228（其中 `/POST/TABLE` 一个 URI 承载 152 个 key） |
| 带 methods 的记录 | 451 / 455 |
| key 级带 Schema（JSON Schema 或 Input Data Form） | 217 / 379 |
| key 级带字段规格表 | 358 / 379 |

### 3.2 命名空间分布

| namespace | 逻辑 key 数 | 说明 |
| --- | --- | --- |
| DOC | 10 | 无 `STAGAS`（GEN 有） |
| DB | 190 | 含 4 个 Civil 独有（CPSETTINGS / NUCS / UFTR / UTBL） |
| OPE | 20 | 含 14 个 Civil 独有（影响线 9 + 协同 4 + BMLD 1） |
| VIEW | 6 | 无 `PRECAPTURE`（GEN 有） |
| POST | 153 | 全部走 `/post/TABLE`，**无 `/post/TEXT`** |
| **合计** | **379** | — |

### 3.3 Methods 分布（实测，与 §2.2 规定一致）

| Methods 组合 | key 数 |
| --- | --- |
| `POST` | 185 |
| `POST, GET, PUT, DELETE` | 171 |
| `POST, GET, PUT` | 12 |
| `GET, PUT` | 6 |
| `GET` | 3 |
| `GET, DELETE` | 1（`DB.NLLP`） |
| 手册未列 | 1（`POST.TABLE`，通用结果表入口，需 `TABLE_TYPE` 必填） |

### 3.4 Civil 的分区结构（与 GEN 不同）

```text
文件Documents · 项目Project · 视图View · 结构Structure · 节点/单元Node/Element
特性Properties · 边界Boundary · 荷载Load · 分析Analysis · 结果Results
Pushover · 设计Design · 协同Collaboration · 工具Apps
```

结果Results 下分 6 组：`荷载组合Combintaion`、`结果表格Result Tables`、`结果显示Result Display`、`详细结果Detail Result`、`移动荷载结果Moving Load`、`模态振型Mode Shapes`。

> 注意：GEN 手册的 33 分区按「官方英文索引」组织（含 Pre-Process Table / Analysis Result Table / Time History Text 等独立分区）；Civil 手册按「功能域」组织，**两套分区体系不能直接对齐**，Registry 的 `section` 字段应记录各自手册的分区名，不要强行归一。

---

## 4. GEN NX vs CIVIL NX 产品差异矩阵（核心）

### 4.1 总量对比

| namespace | CIVIL NX | GEN NX | 共享 | CIVIL 独有 | GEN 独有 |
| --- | --- | --- | --- | --- | --- |
| DOC | 10 | 11 | 10 | 0 | 1 |
| DB | 190 | 227 | 186 | 4 | 41 |
| OPE | 20 | 19 | 6 | 14 | 13 |
| VIEW | 6 | 7 | 6 | 0 | 1 |
| POST | 153 | 237 | 151 | 2 | 86 |
| **合计** | **379** | **501** | **359** | **20** | **142** |

共享率：

```text
从 CIVIL 视角：359 / 379 = 94.7%（Civil 的能力几乎被 GEN 覆盖）
从 GEN  视角：359 / 501 = 71.7%
并集视角    ：359 / 521 = 68.9%
```

> 说明：GEN 的 501 个 key 中含 1 个解析伪影 `POST.TABLE.string`（见 GEN 文档 §11.1 D5）。剔除后 GEN 有效 key 为 500，GEN 独有为 141。

### 4.2 三条结论

1. **GEN 是超集，Civil 是子集 + 专用域**。Civil 的 94.7% 能力在 GEN 中存在，但 Civil 额外提供 20 个 GEN 没有的 key（影响线 / 协同 / Smart Report）。
2. **OPE 层差异最大**（共享仅 6/20）。GEN 的 OPE 偏"自动生成建模数据"（LCOM-GEN/CONC/STEEL/SRC、GUSTFACTOR、STOR、MEMB、SSPS、EDMP、GSBG、STORY_PARAM），Civil 的 OPE 偏"桥梁结果查询"（影响线 9 个）+ 协同（4 个）。
3. **Civil 手册快照为 2024-12，GEN 手册为 2026-07**，相差约 19 个月。差异中有一部分可能是**版本滞后**而非产品差异（例如 Civil 无 `SWIND`、无 `THRE`），编码前应对可疑项做真机探测。

### 4.3 CIVIL NX 独有 key（20 个）

| Registry key | URI | Methods | 能力域 |
| --- | --- | --- | --- |
| `OPE.IRED` | `/ope/IRED` | POST | **影响线** — 反力 |
| `OPE.IDSD` | `/ope/IDSD` | POST | **影响线** — 位移 |
| `OPE.ITRD` | `/ope/ITRD` | POST | **影响线** — 桁架内力 |
| `OPE.IBFD` | `/ope/IBFD` | POST | **影响线** — 梁内力/弯矩 |
| `OPE.IELD` | `/ope/IELD` | POST | **影响线** — 弹性连接内力/弯矩 |
| `OPE.IGLD` | `/ope/IGLD` | POST | **影响线** — 一般连接内力/弯矩 |
| `OPE.IPLD` | `/ope/IPLD` | POST | **影响线** — 板内力/弯矩 |
| `OPE.IBSD` | `/ope/IBSD` | POST | **影响线** — 梁应力 |
| `OPE.ISSD` | `/ope/ISSD` | POST | **影响线** — 实体应力 |
| `OPE.CPCREATE` | `/ope/CPCREATE` | POST | **协同** — 创建模型 |
| `OPE.CPUPDATEMODEL` | `/ope/CPUPDATEMODEL` | POST | **协同** — 更新模型数据 |
| `OPE.CPUPDATERESULT` | `/ope/CPUPDATERESULT` | POST | **协同** — 更新分析结果 |
| `OPE.CPEXPORT` | `/ope/CPEXPORT` | POST | **协同** — 导出模型文件 |
| `DB.CPSETTINGS` | `/db/CPSETTINGS` | POST/GET/PUT | **协同** — 协同设置 |
| `DB.UTBL` | `/db/UTBL` | POST/GET/PUT/DELETE | **Smart Report** — 用户自定义表 |
| `DB.UFTR` | `/db/UFTR` | POST/GET/PUT/DELETE | **Smart Report** — 页眉页脚 |
| `POST.TABLE.TABLE` | `/post/TABLE` | POST | **Smart Report** — 从 Smart Report 取表 |
| `POST.TABLE` | `/post/TABLE` | 手册未列 | **通用结果表入口**（`TABLE_TYPE` 必填） |
| `DB.NUCS` | `/db/NUCS` | POST/GET/PUT/DELETE | 用户坐标系（Named UCS） |
| `OPE.BMLD` | `/OPE/BMLD` | POST | 梁详细分析（Beam Detail Analysis） |

### 4.4 GEN NX 独有 key（142 个，按能力域）

| 能力域 | 数量 | 代表 key | CIVIL 缺失的影响 |
| --- | --- | --- | --- |
| **层 / Story 结构控制** | 25 | `STORY_DRIFT_X/Y/COMB`、`STORY_DISPLACEMENT_X/Y/COMB`、`STIFFNESS_IRREGULARITY_X/Y`、`TORSIONAL_IRREGULARITY_X/Y`、`WEIGHT_IRREGULARITY_X`、`STORY_STABILITY_COEFFICIENT_X/Y`、`OVERTURNING_MOMENT`、`CAPACITY_IRREGULARITY`、`ULTIMATE_STORY_SHEAR_FORCE_CHECK` | **Civil 完全无此域**（`STORY_DRIFT` 全文 0 命中）。主文档 §68 抗震设计、§90 结果 Summary 的 `max_drift` 在 Civil 上无法实现 |
| **时程 / 推覆文本结果** | 29 | `POST.TEXT.TH_DISP`、`TH_VELOCITY`、`TH_ACCEL`、`TH_BEAMFORCE`、`PO_DISP`、`PO_BEAMFORCE` 等 | **Civil 无 `/post/TEXT`**（0 命中）。时程与推覆结果在 Civil 只能走 `/post/TABLE` |
| **设计结果** | 9 | `BEAMDESIGNFORCES`、`COLUMNDESIGNFORCES`、`STEELMEMBERDESIGNFORCES`、`SRCBEAMDESIGNFORCES`、`COLDFORMEDSTEELMEMBERDESIGNFORCES`、`POST.STEELCODECHECK` | Civil 手册只有 `POST.PM`（P-M 交互图）+ `DB.RCHK`（柱配筋），**无钢/SRC/冷弯设计结果表** |
| **Hyper-S 求解器变体** | 21 | `MATL-M1`、`STYP-M1`、`ACTL-M1`、`NLCT-M1`、`IEHG-*-M1`、`THGC-M1` 等 | Civil 手册**无求解器约束标记**，`-M1` 变体一个都没有 |
| **预分析表 / 层质量** | 9 | `STORY_MASS`、`STORY_MASS_X`、`STORY_LOAD_SUMMARY_X/Y/Z`、`STORYWEIGHT`、`MATERIAL`、`SECTIONALL`、`SUPPORTS` | Civil 只有 `LOAD_SUMMARY_X/Y/Z`、`MASS_SUMMARY_X/Y/Z`，无层质量统计 |
| **FIBR（纤维模型）结果** | 5 | `FIBR_ELASTREMAIN`、`FIBR_EVENTSTEP`、`FIBR_MAXCONTRACT`、`FIBR_MEANCOMPCONTRACT`、`FIBR_YILEDSTRENGTH` | Civil 无 |
| **其他 DB / OPE** | 44 | `DB.SWIND`、`DB.STOR`、`DB.STORPROP`、`DB.MEMB`、`DB.WMAK`、`DB.LENG`、`DB.DCTL/DSTL/DCON`、`DB.LTSR`、`DB.MBTP`、`DB.POSL/POSP`、`DB.SSEIS`、`DB.GALD`、`DB.EPSE/EPST`、`DB.ESSF`、`DB.THRE`、`DB.DRLS`、`DB.LLAN/LLANID`、`DB.UTBL` 之外的设计类；`OPE.STORY_PARAM`、`OPE.STORY_IRR_PARAM`、`OPE.GUSTFACTOR`、`OPE.LCOM-*`、`OPE.STOR`、`OPE.MEMB`、`OPE.SSPS`、`OPE.EDMP`、`OPE.GSBG`；`DOC.STAGAS`；`VIEW.PRECAPTURE` | 按需裁剪 |

### 4.5 同一能力、不同命名（Registry alias 的实例）

| 能力 | CIVIL NX | GEN NX | 处理 |
| --- | --- | --- | --- |
| 索效率 | `POST.TABLE.CABLEEFFIENCY` | `POST.TABLE.CABLEEFFICIENCY` **和** `CABLEEFFIENCY` 同时存在 | Common Registry 需建 alias 映射，不能假设同一 key 跨产品可用 |
| 荷载统计 | `LOAD_SUMMARY_X/Y/Z` | `LOAD_SUMMARY_X/Y/Z` | 一致 ✅ |
| 梁内力 | `BEAMFORCE`（页标题"内力Beam Force"） | `BEAMFORCE` | 一致 ✅ |
| 层间位移 | 无 | `STORY_DRIFT_X/Y/COMB` | 产品能力差异，非命名差异 |

---

## 5. 对 Registry 架构的影响（实测验证主文档 §26 / §27 / §124）

### 5.1 Common + Product Override 模型成立，但不能按"共享即 Common"简单划分

按 key 集合划分的结果：

```text
registry/common/                     359 个 key（两产品均验证存在）
registry/products/civil_nx/           20 个 key（Civil 独有）
registry/products/gen_nx/            141 个 key（GEN 独有，剔除 1 个解析伪影后）
```

但存在三类"看似共享、实则不同"的情况，必须用 Product Override 表达：

| 情况 | 实例 | 处理 |
| --- | --- | --- |
| 同名不同 methods | `DB.NLLP` Civil 仅 `GET/DELETE`；GEN 为 `POST/GET/PUT/DELETE` | Product Override 覆盖 `methods` |
| 同名不同参数 | `POST.TABLE.BEAMFORCE` 两产品 `COMPONENTS` 枚举不同 | Override 覆盖 schema 引用 |
| 求解器约束差异 | GEN 的 `-M1` 变体在 Civil 不存在 | 独立 key + `solver` 约束（GEN 文档 §8 结论） |

### 5.2 建议新增的 Registry 字段

```yaml
# 在 EndpointDefinition 上增加
products: [GEN_NX, CIVIL_NX]      # 已支持的产品
availability:                      # 逐产品的可用性（缺省 = products 全支持）
  GEN_NX: full
  CIVIL_NX: partial
alias_of: ""                       # 同一能力的别名指向（如 CABLEEFFIENCY -> CABLEEFFICIENCY）
capability_domain:                 # 能力域，用于 Adapter 能力裁剪
  - INFLUENCE_LINE                 # 仅 CIVIL
  - STORY_CONTROL                  # 仅 GEN
  - COLLABORATION                  # 仅 CIVIL
  - SMART_REPORT                   # 仅 CIVIL
```

### 5.3 对 Adapter 与 RuntimeContext 的影响

1. **Adapter 必须能声明能力域**。Civil 不支持 Story 域、不支持 `/post/TEXT`、不支持 Hyper-S 变体。当 Registry Resolve 失败或 `capability_domain` 不匹配时，必须返回主文档 §104 已有的 `PRODUCT_CAPABILITY_UNSUPPORTED`，并在 `details` 中带 `product` / `required_capability`。
2. **RuntimeContext 必须带 product + version**，否则无法区分同名 key 的差异（主文档 §13 已要求，此处实测证实必要性）。
3. **产品切换（主文档 §98 / §131）**：从 GEN 迁到 CIVIL 时，Story 域、Hyper-S 变体、`/post/TEXT` 相关能力**必然丢失**，兼容性检查必须显式报告这些能力域，而不是只报"字段缺失"。

### 5.4 对自动识别软件（主文档 §130）的影响

两产品共同的探测锚点：

```text
OPE.PROJECTSTATUS   （GET，返回项目状态）
DB.PJCF             （GET，返回项目信息）
```

但**这两个都无法区分 GEN NX 与 CIVIL NX**。建议：

```text
探测顺序：
1. ope/PROJECTSTATUS  → 确认 API 可用 + 取得项目状态
2. db/PJCF            → 取得工程信息
3. 产品判定：
   a. 调用一个 Civil 独有 key（如 db/NUCS 或 ope/IRED）→ 成功则为 CIVIL NX
   b. 调用一个 GEN 独有 key（如 db/STOR 或 db/GUSTFACTOR）→ 成功则为 GEN NX
   c. 两者都失败 → 无法判定，要求 WebUI 选择 Product（与主文档 §130 一致）
```

> 该判定策略需真机验证；若 MIDAS 对不存在的 Endpoint 返回统一错误而非 404，则改用 `db/UNIT` 的 `STYP` 取值域或版本号字段判定。

---

## 6. 第一批 Registry（CIVIL NX 版）

与 GEN 版（GEN 文档 §9.4）对照，第一 / 二 / 三阶段的 key 清单基本一致，差异如下：

| 阶段 | 与 GEN 的差异 | 处理 |
| --- | --- | --- |
| 第一阶段 | 无差异（DOC.NEW/OPEN/SAVE/ANAL + DB.UNIT/STYP/PJCF/NODE/ELEM + OPE.PROJECTSTATUS 共 10 个，两产品都存在） | 直接复用 |
| 第二阶段 | 无差异（DB.MATL/SECT/CONS/STLD/BMLD/GRUP/BNGR/LDGR + DB.LCOM-GEN 共 9 个） | 直接复用；注意 Civil 的 `LCOM-*` 与 GEN 同名同 URI |
| 第三阶段 | **Civil 无 `STORY_DRIFT_*`**，抗震/层控制类结果不可用 | 用 `POST.TABLE.DISPLACEMENTG/DISPLACEMENTL`、`REACTIONG/REACTIONL`、`BEAMFORCE`、`BEAMSTRESS`、`MODESHAPE` 类替代；桥梁项目可加 `OPE.IRED`（影响线反力） |

主文档 §141 第三阶段验收中的「层间位移」在 CIVIL NX 上应改为：

```text
层间位移  → POST.TABLE.DISPLACEMENTG / DISPLACEMENTL（全局/局部）
层间位移角 → CIVIL 无对应表；如需，必须由 StructAI 基于 DISPLACEMENTG + 楼层信息自行计算，
             并在 Report Source Map 中标注「由 StructAI 计算，非 MIDAS 原生结果」
```

这一条对主文档 §133「报告中的数字规则」是新增约束：**跨产品时，某些指标必须由 StructAI 派生，且必须标注派生来源。**

---

## 7. 对主文档与前三份文档的逐条回写建议

| 目标文档 / 章节 | 建议改动 | 优先级 |
| --- | --- | --- |
| 主文档 §2 设计约束 | 补：**MIDAS API 区分大小写**（Civil 手册明文）；补 CRUD 逐命名空间规则 | 高 |
| 主文档 §17 / §18 Adapter | 补：Adapter 必须声明**能力域**（INFLUENCE_LINE / STORY_CONTROL / COLLABORATION / SMART_REPORT），并在不支持时返回 `PRODUCT_CAPABILITY_UNSUPPORTED` | 高 |
| 主文档 §26 / §27 Registry 三层覆盖 | 用本文 §5.1 的实测划分（Common 359 / Civil 20 / GEN 141）替换估计值 | 高 |
| 主文档 §98 产品切换规则 | 补：GEN → CIVIL 迁移会丢失 Story 域、Hyper-S 变体、`/post/TEXT`；兼容性检查必须按**能力域**报告，不只报字段 | 高 |
| 主文档 §111 第一批 Registry | 补 CIVIL 版差异（§6）：Civil 无 `STAGAS`、无 `PRECAPTURE`、第三阶段无 `STORY_DRIFT` | 高 |
| 主文档 §123 官方 Endpoint 覆盖原则 | 补：Civil 手册按「功能域」组织（14 分区），与 GEN 的 33 分区体系不同，`section` 字段不要强行归一 | 中 |
| 主文档 §124 产品差异策略 | 用本文 §4.1 的完整差异矩阵替换现有示例；补 §4.5 的 alias 案例 | 高 |
| 主文档 §130 自动识别软件 | 用本文 §5.4 的探测策略替换现有描述 | 中 |
| 主文档 §133 报告数字规则 | 补：跨产品时部分指标由 StructAI 派生（如 CIVIL 的层间位移角），必须标注派生来源 | 中 |
| 主文档 §141 第三阶段验收 | 「层间位移」在 CIVIL NX 上改为 `DISPLACEMENTG/L`；`STORY_DRIFT_*` 仅适用于 GEN | 高 |
| 主文档 §145 核心原则 | 建议新增：**Registry 的 Common 层只收录"两产品均实测存在"的 key；产品差异一律进 Product Override** | 中 |
| GEN 补充文档 §11.2 Q9 | **已由本文 §2.3 回答**：区分大小写 | — |
| GEN 补充文档 §11.2 Q11 | **已由本文完成**：CIVIL NX Registry 已录入（379 个 key） | — |
| 项目框架图 §7 目录框架 | `registry/products/` 下应明确 `civil_nx/` 与 `gen_nx/` 的 key 数量与能力域清单 | 低 |

---

## 8. 数据质量说明与待确认问题

### 8.1 手册格式的特殊性（抽取脚本必须处理）

抽取过程中实际踩到的 4 个坑，已全部修正，此处记录以便后续重跑：

| # | 现象 | 影响 | 处理 |
| --- | --- | --- | --- |
| F1 | 页面标题层级不统一：`#####` 与 `######` 混用（69 个 `zh[CODE]en` + 36 个 `[CODE]en` + 42 个无代码） | 以标题层级判断"新页面"会误判 | 改为按"子块标记白名单"判断，凡不属于子块标记的标题即新页面 |
| F2 | 子块标记两种形式混用：`###### Input URI` 与 `**Input URI**` | 只认一种会漏掉约 2/3 页面 | 两种都识别 |
| F3 | 部分页面用**中文子块标记**：`###### 输入URI / 方法 / 示例 / 所需的请求数据` | 漏掉核心页面（如 `POST.TABLE.BEAMFORCE`） | 白名单补中文变体 |
| F4 | 部分页面的示例标题为 `###### Input JSON format example of table` | 被误判为新页面，导致该页 `TABLE_TYPE` 丢失（曾把 `LOAD_SUMMARY_X/Y/Z` 错并成 `LOAD_SUMMARY`） | 白名单补 `input json` / `output json` 等前缀 |

### 8.2 抽取结果的数据质量

| 项 | 状态 |
| --- | --- |
| 455 条记录中 451 条有 methods | 4 条缺（含通用入口 `POST.TABLE`） |
| 379 个 key 中 217 个带 Schema | 其余依赖 `info/db/{CODE}` 自省或字段规格表 |
| 379 个 key 中 358 个带字段规格表 | 可用于生成 Level 1 校验 |
| 1 个 key 命名为 `POST.TABLE`（无 `TABLE_TYPE`） | 为手册「结果表格Result Tables」通用入口，实际调用时必须带 `TABLE_TYPE`；建议在 Registry 中标记为 `requires_argument: TABLE_TYPE` |
| 1 个 Civil key 名带拼写错误 `CABLEEFFIENCY` | 手册原文如此；GEN 手册同时存在 `CABLEEFFICIENCY` 与 `CABLEEFFIENCY`，需按 §4.5 建 alias |

### 8.3 待确认问题（编码前必须裁决）

| # | 问题 | 影响 |
| --- | --- | --- |
| Q14 | **Civil 手册快照 2024-12，滞后约 19 个月**。GEN 独有域中哪些是"Civil 本来就没有"、哪些是"2024-12 之后新增"？ | 决定 Product Override 的边界。建议对 GEN 独有 key 做一次真机探测，把"Civil 实际支持但手册未录"的 key 从 GEN 独有移回 Common |
| Q15 | `POST.TABLE` 通用入口（`TABLE_TYPE` 必填）与逐类型的 `POST.TABLE.<TYPE>` 是否应并存？ | 建议：**并存**。通用入口用于手册未覆盖的表类型与 Smart Report，逐类型用于已录入的 151 个 |
| Q16 | Civil 的 9 个影响线 Endpoint 是否需要在 StructAI 侧建 Result 模型？ | 桥梁项目的核心能力，建议在 ResultStore 增加 `influence_line` 结果类型（当前主文档 §55 无此类型） |
| Q17 | 协同 Collaboration（4 个 OPE + 1 个 DB）是否纳入 StructAI 的 Project 生命周期？ | 涉及"MIDAS 模型与外部协同平台双向同步"，与主文档 §37 Project Binding 可能冲突，需明确是否由 StructAI 托管 |
| Q18 | Smart Report（`UTBL` / `UFTR` / `POST.TABLE.TABLE`）是否纳入 Report Engine？ | 若纳入，主文档 §74 Report Engine 需支持"读 MIDAS 侧 Smart Report 表"作为数据源 |
| Q19 | Civil 的 `POST.PM` 与 GEN 的 `POST.PM` URI 相同但页面不同（Civil 标注 DB Section） | 需确认两产品的 P-M 交互图参数是否一致 |

---

## 9. 附件与复现

### 9.1 附件

`StructAI_MIDAS_MCP_CIVIL_NX_Endpoint清单_v1.0.csv` —— 379 行，UTF-8 with BOM，字段与 GEN 版一致：

| 字段 | 说明 |
| --- | --- |
| `registry_key` | 逻辑 key，如 `DB.NODE`、`POST.TABLE.BEAMFORCE`、`OPE.IRED` |
| `namespace` | `DOC` / `DB` / `OPE` / `VIEW` / `POST` |
| `uri` | 实测 URI |
| `methods` | 实测方法集 |
| `table_type` | POST 命名空间的 `TABLE_TYPE` |
| `solver` | 恒为空（Civil 手册无求解器标记） |
| `schema` | 是否有 JSON Schema 或 Input Data Form |
| `spec_rows` | 字段规格表行数 |
| `section` | 手册 H3 分区（如 `结果Results`） |
| `group` | 手册 H4 分组（如 `移动荷载结果Moving Load`） |
| `page` | 手册页面标题（如 `内力Beam Force`） |

### 9.2 复现步骤

```text
1. 读取 G:\midas Civil NX - API\md\midas Civil NX - API 用户手册.md
2. 定位 "## JSON手册" 起始行（实测为第 2339 行）
3. 按 H3 / H4 / H5 / H6 切分，用"子块标记白名单"判定页面边界：
   Input URI / 输入URI / Active Methods / 方法 / JSON Schema / Input Data Form /
   Examples / 示例 / Input JSON format / Output JSON format /
   The required Input Data / 所需的请求数据 / Specifications
4. 每个 Input URI 块抽取：URI、Active Methods、JSON Schema、Examples、字段规格表
5. POST 命名空间额外抽取 `"TABLE_TYPE": "..."`（schema enum 与示例双源，含跨行形式）
6. 归一化 key：
   - 非 POST：`<NAMESPACE>.<URI 第 2 段>`
   - POST：`POST.<TABLE|TEXT>.<TABLE_TYPE>`；无 TABLE_TYPE 时用标题 `[CODE]`，仍无则记为 `POST.TABLE`
7. 输出 civil_endpoint_inventory.csv
8. 与 gen_nx_endpoint_inventory.csv 做集合比较，得到共享 / 独有划分
```

### 9.3 统计校核

| 项 | 值 |
| --- | --- |
| 手册总行数 | 162,153 |
| JSON手册区起始行 | 2,339 |
| H3 / H4 / H5 / H6 | 21 / 60 / 147 / 1303 |
| Input URI 记录 | 455 |
| Registry key | 379 |
| 唯一 URI | 228 |
| 命名空间分布 | DOC 10 · DB 190 · OPE 20 · VIEW 6 · POST 153 |
| `info/db/` 自省次数 | 181 |
| 与 GEN 共享 | 359 |
| Civil 独有 | 20 |
| GEN 独有 | 142（剔除 1 个伪影后 141） |

---

## 10. 结论与边界

1. **CIVIL NX 的知识层已建立**：379 个 Registry key，覆盖手册 JSON手册区的全部 455 条 `Input URI` 记录。
2. **产品差异矩阵已量化**：与 GEN NX 共享 359 个 key（占 Civil 能力的 94.7%），Civil 独有 20 个（影响线 / 协同 / Smart Report / NUCS / 梁详细分析），GEN 独有 142 个（层控制 / 时程推覆文本 / 设计结果 / Hyper-S 变体）。
3. **主文档的 Common + Product Override 模型经实测验证成立**，但不能按"共享即 Common"简单划分，需引入 `availability` / `alias_of` / `capability_domain` 三个字段（§5.2）。
4. **回答并关闭了 GEN 文档的两个遗留问题**：Q9（大小写敏感性 → 区分大小写）、Q11（CIVIL NX Registry → 已完成）。
5. **本文边界**：
   - 只覆盖 Civil 手册的 **JSON手册区**；前置区（入门/编程语言/技巧/案例）未纳入 Registry，但其中「提示与技巧 → 巧用URL中的"Info"」一节印证了 `info/` 自省机制是官方推荐用法。
   - Civil 手册快照为 2024-12，**版本滞后**；GEN 独有域中可能混有"已支持但手册未更新"的 key，需真机探测（Q14）。
   - 协同 Collaboration 与 Smart Report 的语义归属未裁决（Q17 / Q18）。

> 本文为 MIDAS CIVIL NX 的 **API 知识层实测基线**。后续 Civil 手册更新时，按 §9.2 重跑生成链，产出新的 `registry_version` 并保留旧版本。