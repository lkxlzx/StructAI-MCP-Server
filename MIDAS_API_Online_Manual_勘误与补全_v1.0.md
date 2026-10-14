# MIDAS API Online Manual — 勘误与补全 v1.0

> **性质**：本文件是 [`MIDAS_API_Online_Manual_完整API手册_v1.0.md`](MIDAS_API_Online_Manual_完整API手册_v1.0.md)、
> [`MIDAS_API_开发文档_v1.0.md`](MIDAS_API_开发文档_v1.0.md)、
> [`MIDAS_API_Online_Manual_索引_v1.0.csv`](MIDAS_API_Online_Manual_索引_v1.0.csv)
> 及配套 `MIDAS_API_Online_Manual_*.json` 的**勘误与补全附录**。
>
> **证据来源**：外部项目 [`Dennis5882/MIDAS-API-NX-SDK`](https://github.com/Dennis5882/MIDAS-API-NX-SDK)
> 的 `docs/manual_defects_register.md`（1917 行 / 136 KB，登记 **62 条**针对 **MIDAS 官方手册**的缺陷），
> 经与本仓库 `registry/manifest.json`（636 端点）逐条交叉映射后产出。
>
> **⚠️ 证据等级声明**：本附录内容**不是**本仓库的实测结论，而是**外部证据输入**。
> 依 `registry/README.md` §8.2 的既定口径，凡涉及 `products` / 必填性 / 类型的数据变更，
> 均需**我方实例实测 + 显式裁决**方可落地。本文件**未改动 `registry/` 任何数据**。
>
> **配套报告**：[`docs/nxsdk_review/00_评估与查漏补缺报告_v1.0.md`](docs/nxsdk_review/00_评估与查漏补缺报告_v1.0.md)
> **机器可读版**：[`docs/nxsdk_review/nxsdk_manual_errata.csv`](docs/nxsdk_review/nxsdk_manual_errata.csv)

---

## 0. 落地状态（**先看这一节**）

本附录的 62 条**不是**一次性全部落地 —— 落地需要**我方实测 + 显式裁决**（见文首「证据等级声明」）。
截至本版，落地情况如下：

| 状态 | 条数 | 说明 |
| --- | --- | --- |
| ✅ **已落地（数据侧）** | 12 | 见 §0.1 —— 服务端 `/info` **与**对方**已复核契约**双证据同向，**且**有实测的形状级拒绝，才动数据 |
| ✅ **已核对，我方本来就对** | 2 | **MD-03**（`/db/MATL-M1`）与 **MD-60**（`/db/SPFC`）—— 我方数据已是正确的一侧，**不改** |
| 📌 **已登记，待我方复测** | 约 15 | 需在我方实例上实测后裁决（其余必填性、层级、产品差异类） |
| 📝 **已登记，仅改手册文字** | 约 20 | 不影响 `registry/` 数据；本附录即为手册侧的勘误标注 |
| ⚪ **不改（对方工具缺陷）** | 7 | 手册内容**是对的**，是对方解析器的问题 —— **不得**转嫁到手册 |
| 🚫 **禁止采纳（已撤回）** | 5 | 见 §2，对方 2026-07-27 用官方文章复核后撤回 |

### 0.1 已改（`registry/` 数据侧）

**（a）字段类型（第一批）**

| 端点 | 字段 | 改动 | 双重依据 |
| --- | --- | --- | --- |
| `DB.SLANOP` | `OPT_STRADD` | `integer` → **`boolean`** | 服务端 `/info` 描述 **"BS Straddling Lane Boolean"**；对方契约 `provenance: info_schema` |
| `DB.REBC` | `ITEMS[].HOOP_TYPE` | `string`（+字符串 `oneOf`、`default: "Ties"`）→ **`integer`** | 服务端描述 **"Hoop Type (1=Tied, 2=Spiral)"**；对方契约 `provenance: live_corrected`。**不**声明 `enum` |
| `DB.REBR` | `ITEMS[].HOOP_TYPE` | 同上 → **`integer`** + **`enum: [1, 2]`** | 同上；且该端点 `/info` **声明了** `enum` |

**（b）字段结构 —— `/db/REB*` 家族整体重建（第二批；MD-34 全量落地）**

手册（含官方 en-us 文章）在这四个端点上的字段名**全部不对**。
`GET /info` 与对方**已复核契约**在四个端点上**逐路径一致**（45/45 · 22/22 · 17/17 · 20/20），
且每个都有**实测的形状级拒绝**：

| 端点 | 关键改动 | 实测证据 |
| --- | --- | --- |
| `/db/REBB` | `{LAYER1, LAYER2}` 对象 → **`{NAME, NUM}` 数组**；移除 `CREATE_SUB_SECTION`/`ELEMS` | A-03：多种载荷**全部** `Wrong Field`；短键到达域检查 |
| `/db/REBC` | `MAIN_BAR` 单对象 + 顶层 `DO` → **`vMAIN_BAR` 数组**（每项含 **`D0`**）；移除 `CREATE_SUB_SECTION`/`ELEMS` | A-02：手册形状 → `Wrong Field`；数组 → 域错误（**形状被接受**），完整 CRUD 往返成功 |
| `/db/REBR` | 同上 | A-04：长键 → `Wrong Field`；短键 → 域检查 |
| `/db/REBW` | **一个字段名都不对**：`VERTICAL_REBAR`→`VER_BAR`、`HORIZONTAL_REBAR`→`HOR_BAR`、`STORY:{FROM,TO}`→**`vSTORY_NAME`（字符串数组）**、`THICKNESS`→`THICK` … | A-01：`GET` 回显 + `/info` + **`PUT` 往返** 三次确认 ⇒ **写契约** |

⚠️ **`/db/REBB` 的写路径不可用**（四次尝试**从未成功**，与 `/db/NLLP`、`/db/WVLD` 同类）；
`ID` **必须**送（缺它得到 `Wrong Field`）。

**（c）必填性 —— `/db/PRES` 的 `DIRECTION`（第二批；MD-17 全量落地）**

手册标 `DIRECTION` **Optional**、默认 `"NORMAL"`；实测**省略字段正是坏默认值被应用的途径** ——
在 `PLATE`+`FACE` 上**省略**与**显式填 `"NORMAL"`** 得到**同一条**拒绝。
已把 `DIRECTION` 加入 `required`，并补 `enum`（八个值）、`VECTORS` 的 3 分量界、
`EDGE_FACE` 的 1..6 界、以及若干默认值。⚠️ `"NORMAL"` 的可用性排除**刻意不做硬闸门**
（对方契约定为 `warn` 而非 `reject`：该值对另外三种组合合法，拒绝调用方显式给的值等于替工程师做工程决策）。

### 0.2 另已落地（产品归属，**不在**本表 62 条内）

**第一批（外部证据）**：`registry/` 的 `products` 更正 **33** 条 —— **21** 个 Hyper-S `-M1`
由 `[GEN_NX]` 改为 `[CIVIL_NX]`；**12** 个由 `[CIVIL_NX, GEN_NX]` 收为 `[GEN_NX]`。

**第三批（我方 CIVIL_NX 实例实测，2026-10-14）**：B 级 21 条「我方少声明 `CIVIL_NX`」**收口** ——
CIVIL_NX 产品级只读探针（`registry/live/civil_product_probe.json`，**只发 GET**、含三组对照）实测：

| 结果 | 条数 | 动作 |
| --- | ---: | --- |
| 路由**存在**（`200`） | **18** | 并上 `CIVIL_NX` + `verified_on: civil-cloud` + `availability: verified` |
| 路由**不存在**（`404`） | **3** | **不**并 `CIVIL_NX`，只记 `unavailable_on: civil-cloud` |

⚠️ **一处冲突（值得注意）**：**21 条 Hyper-S `-M1` 在我方 CIVIL_NX 上全部 `404`**，
而外部证据（MIDAS IT 在职员工两产品实测）称它们是 Civil NX 专属且 `civil GET ok`。
处置：`products` **保留** `[CIVIL_NX]`（产品级能力声明），两个实例的缺口**都**记入
`unavailable_on`，`availability` 仍为 `unverified`。详见
[`registry/README.md` §8.17.3](registry/README.md)。

逐条证据与计数见 [`registry/README.md` §8.15](registry/README.md) / [§8.17](registry/README.md) 与
[`docs/nxsdk_review/00_评估与查漏补缺报告_v1.0.md`](docs/nxsdk_review/00_评估与查漏补缺报告_v1.0.md) §3.1 / §3.3 / §3.4。

### 0.3 第四批（P164）已落地 / 已核对

| MD | 端点 | 结论 | 动作 |
| --- | --- | --- | --- |
| **MD-60** | `/db/SPFC` | 手册的 EURO2004 表把 `SPECTYPE`/`GROUTYPE`/`NATIONALANNEX` 放 **`OPT`**，`/info` 声明在 **`STR`**；手册那个 body 双产品都答 `Unknown Error`，**至今无可用 EURO2004 请求** | ✅ 我方**本来就对**（`STR` 有、`OPT` 无）；补 `STR` 说明。**附带**：手册把同一字段拼成 `LARGEBRIDEGE` —— 按 **R117 保留**并互相加注 |
| **MD-03** | `/db/MATL-M1` | 与 `/db/MATL` **不共用 wire key**；`PARAM[].P_TYPE` 在 `-M1` 是 **0-based** | ✅ 我方**本来就对**（`MATL_NAME`/`MATL_TYPE`/`PARAM`/`DAMP_RAT` + `enum: [0,1,2]`），**不改数据** |
| **MD-16** | `/db/MVHL` | `VEHICLE_LOAD_NUM` 是**分支判别子**；`VEHICLE_TYPE_NAME` 只在分支 1 必填；手册标 Required 的 `STANDARD_CODE` 实测**不必填**；`USER_LOAD_TYPE` 在 `MVLD_CODE=2` 下不是输入 | ✅ 补 `LOAD_ITEMS[].POINT_DIST2` · `enum: [1,2]` · **`if/then`** 条件必填 · 两处**只加注不做闸门** |
| **MD-29** | `/DESIGN/RC/…/REBB` | 该节的 **schema/表** 与**它自己的三个示例**描述不同 payload，且该节 callout **明说以示例为准** | ✅ 条目按**示例**重建（8 → **11** 成员；`DT`/`DB` 移除） |

> ✅ **已不在本清单**：**MD-17**（`/db/PRES` `DIRECTION`）与 **MD-34**（`/db/REBR` item 形状）
> 已于第二批**全量落地**（含同族的 `/db/REBB`、`/db/REBC`、`/db/REBW`）—— 见 §0.1(b)(c)。

---

## 0.4 使用方式

本附录按**动作类型**组织，而非按 MD 编号 —— 因为 62 条中只有一部分需要改我方数据，
另一部分只需改我方手册文字，还有一部分是**对方自己的工具缺陷**（不应转嫁到手册）。

| 分组 | 条数 | 我方动作 | 是否需实测 |
| --- | --- | --- | --- |
| **A. 需改我方 registry 数据** | 约 24 | 复核字段类型 / 必填性 / 层级 / `products` | 部分需 |
| **B. 需改我方手册文字** | 约 20 | 在对应端点章节加勘误标注 | 否 |
| **C. 对方工具缺陷，勿转嫁手册** | 7 | **不改**（仅记录） | 否 |
| **D. 产品缺陷而非文档缺陷** | 约 6 | 记入我方 `risk` / 前置链 | 否 |
| **E. 已撤回的主张** | 5 | **禁止采纳** | — |

---

## 1. 全量勘误表（MD-01 ～ MD-62）

> 「我方现状」列取自 `registry/manifest.json` 的实际值（生成于本轮比对）。
> 「建议」列中 🔴 = 高优先、🟡 = 中、⚪ = 仅记录。

### 1.1 方法 / 动词类

| MD | 端点 | 手册主张 | 实测结论 | 我方键 / 现状 | 建议 |
| --- | --- | --- | --- | --- | --- |
| **MD-01** | `/db/STYP-M1` | 三处声明支持 `DELETE` | **三种 DELETE 形式在两个产品上全部被拒** | `DB.STYP-M1` · `[CIVIL_NX]` · `unverified` · `methods` 含 DELETE | 🔴 从 `methods` 移除 DELETE；同时按报告 §3.1 改 `products` |
| **MD-02** | `/db/POLC-M1` | callout 称不提供 `POST` | `POST` **成功建记录且 GET 能取回**（手册过严） | `DB.POLC-M1` · `[CIVIL_NX]` · `unverified` | 🟡 确认我方 `methods` 含 POST；按 §3.1 改 `products` |

### 1.2 字段结构 / 层级 / 命名类

| MD | 端点 | 手册主张 | 实测结论 | 我方键 / 现状 | 建议 |
| --- | --- | --- | --- | --- | --- |
| **MD-03** | `/db/MATL-M1` | 称与 `/db/MATL` **同结构** | 顶层名不同、字段数 **4 vs 9**、`HE_*` 在父端点 | `DB.MATL-M1` 已**独立建键**（方向正确） | ⚪ 方向已对；核对字段数 |
| **MD-07** | `/db/FIMP` | Kent & Park 表把**三层对象写成十个扁平顶层字段**，漏 `CONC`/`STEEL` | 同节 Request Example + JSON Schema 证明是三层 | `DB.FIMP` · `verified` | 🔴 核对我方 FIMP Schema 层级 |
| **MD-08** | `/db/CO_S`、`/db/CO_T` | 一行压缩**九个颜色键**为 `"W_R" ~ "HE_B"`，会被读作两个字面键 | 同节 schema + 示例 + `/db/CO_M` 三处对照 | `DB.CO_S` / `DB.CO_T` · `verified` | 🟡 核对我方是否把 `"W_R" ~ "HE_B"` 误当字面键 |
| **MD-10** | `/db/EPMT`、`/db/ELEM`、`/db/RCHK`、`/db/FIMP` | Specifications 表漏掉同节 JSON Schema 声明的根属性 | 逐节对照：**2 reconciled / 2 open**；另 5 条实为对方解析器缺陷 | 四端点我方均 `verified` | 🟡 核对根属性完整性 |
| **MD-20** | `/db/THGC-M1` | 「ITER_PARAM 서브 파라미터」Key 列**写路径而非属性名** | 照印会得到 `{OPT_USE, VALUE}` 这种字段 | `DB.THGC-M1` · `[CIVIL_NX]` · `unverified` | 🔴 核对我方 THGC-M1 |
| **MD-21** | `/db/STCT-M1` | 五处 Key 单元格不命名单一 wire 属性；"나머지 객체" 表用 `Object` 列表达父级 | `/info` 确认真名为 `bSDLE` / `vSDLE` | `DB.STCT-M1` · `[CIVIL_NX]` · `unverified` | 🔴 核对我方 STCT-M1 |
| **MD-22** | `/db/STCT-M1` | 顶层表十四行**无一行命名 `FINAL_STAGE`** | `/info` 声明十六个根属性，**含 `FINAL_STAGE`** | 同上 | 🔴 补 `FINAL_STAGE` |
| **MD-23** | `/db/THIS-M1` | `FREQ1`/`PERIOD1`、`FREQ2`/`PERIOD2` 两行各键两个**互斥**属性 | 由正上方行 `COEF_CALC` 选择 | `DB.THIS-M1` · `unverified` | 🟡 建模为条件分支 |
| **MD-25** | `/db/MVLDeu` | `OPT_COMB` 标 String 实为整数；两个数组无成员行 | 同节两个 Request Body 示例 | `DB.MVLDEU` · `verified` | 🟡 核对类型与成员 |
| **MD-26** | `/db/REBR` | 表编号 `(1)`–`(6)` 但 `ID`/`ELEMS` **无行**；第三表四行分属两层未说明 | 同节 JSON Schema + chapter 26 对照 | `DB.REBR` · `verified` | 🔴 见 MD-34 |
| **MD-29** | `/DESIGN/RC/KDS-41-20-2022/REBB` | schema/表 与**三个示例描述不同 payload**，该节自述"以示例为准" | 同节三处示例 + callout | `DESIGN.RC.KDS-41-20-2022.REBB` · `verified` | 🔴 以示例为准复核我方 Schema |
| **MD-30** | `/DESIGN/RC/KDS-41-20-2022/REBR` | 在 `MAIN_BAR.NUM`（`integer`）上写了**只对数组有效**的 `minItems: 4` | 同节 Parameters 行 + chapter 24 对照 | `DESIGN.RC.KDS-41-20-2022.REBR` · `verified` | 🟡 移除误用关键字 |
| **MD-31** | `/DESIGN/RC/KDS-41-20-2022/TABLE` | `NODE_ELEMS` 类型单元格写 `Object (oneOf)` 且**不列任何成员** | 同节 JSON Schema + Request Body | `DESIGN.…TABLE` + `.BEAM`/`.BRACE` · `untested` | 🟡 补成员 |
| **MD-34** | `/db/REBR` | 整个 item 形状错 | `/info` 逐字段不符：**`vMAIN_BAR` 数组、`D0` 非 `DO`、`HOOP_TYPE` 为整数** | `DB.REBR` · `verified`；我方 `HOOP_TYPE: string` | 🔴 **与本报告 §3.2 类型冲突同向**，证据最硬 |
| **MD-35** | 六个 `/db/LCOM-*` | 章末比较表说五个"无额外字段" | **六个都有同样四个** | `DB.LCOM-GEN`/`-STEEL`/`-SRC`/`-CONC` 均 `verified` | 🟡 补四个字段 |
| **MD-37** | `/db/POGD-M1` | `ANALYSIS_STOP` 四项主张 | 两处字段名与 `/info` 不同（手册自相矛盾），两处 `/info` 完全不声明 | `DB.POGD-M1` · `[CIVIL_NX]` · `unverified` | 🔴 按 §3.1 改 `products` + 核字段名 |
| **MD-38** | `/db/STRPSSM` | `POINT1`/`POINT2` 条目**把 description 文字当成了键**（`PY`/`PZ` vs 实际 `Y`/`Z`） | `/info/db/STRPSSM` | `DB.STRPSSM` · `[CIVIL_NX]` · `verified` | 🔴 **与本报告 §3.6 的 `STRPSSM` 4 缺 4 多直接吻合** |
| **MD-39** | `/db/STOR` | 三处都只给**十五个**属性 | 实际有**第十六个** | `DB.STOR` · `[GEN_NX]` · `verified` | 🟡 补字段 |
| **MD-40** | `/db/RPSC` | 行 5 把 `MBAR_ITEMS` 放在根 | 实际**低一层**，在 `MBARS` 数组内 | `DB.RPSC` · `verified` | 🟡 修层级；另见 §3.2 `LBAR_INC_FC` 类型 |
| **MD-41** | 九个 `/db/*` 节 / 十五个字段 | 各节表自称完整 | `/info` 每节**多声明一至六个** | 跨多节 | 🟡 逐节核对 |
| **MD-43** | `/db/SLANch` | 唯一 Parameters 表其实是 `LANE_ITEMS` 的**数组成员表**，记录自身八字段无表 | 同节示例 + `/info` + `/db/SLAN` 对照 | `DB.SLANCH` · `verified` | 🟡 修层级 |
| **MD-45** | `/db/LLANtr`、`/db/SLANop` | **完全未记录** `SPECIAL_LANE_ITEMS`、`OPT_STRADD`、`CHINA_ITEMS` | `/info` 双端点声明 | `DB.LLANTR` / `DB.SLANOP` · `verified` | 🔴 `OPT_STRADD` 见 §3.2（我方 `integer`，服务端 `boolean`） |
| **MD-47** | `/db/TDMT` | `CODE="EUROPEAN"` 是**第三个分支**，带两个表从未命名的字段 | 2026-07-30 真实 PSC 模型 + `/info` 双产品 | `DB.TDMT` · `verified` | 🟡 补分支字段 |
| **MD-48** | `/db/MVHL` | 表只记录 `VEH_DEFAULT` | `/info` 多声明**十一个 country 对象**（共 48 字段） | `DB.MVHL` · `verified` | 🟡 补 country 对象 |
| **MD-50** | `/db/MVCTch` | 双 Key 列的表只被读了一半；`BTYPE` 写在**粗体引导句**里 | `/info` sweep + 全 27 章扫描 | `DB.MVCTCH` · `verified` | 🟡 核对 |
| **MD-60** | `/db/SPFC` EURO2004 | 表把三个字段放在 `OPT` | 该 body 双产品答 `Unknown Error`；`/info` 说在 **`STR`** | `DB.SPFC` · `verified` | 🔴 修层级 |
| **MD-61** | `/db/MVHL` country 表 | 标题说 `STANDARD_CODE` 选择对象 | 实际是 **`MVLD_CODE`** | `DB.MVHL` · `verified` | 🔴 改选择器名 |

### 1.3 类型 / 枚举 / 取值类

| MD | 端点 | 手册主张 | 实测结论 | 我方键 / 现状 | 建议 |
| --- | --- | --- | --- | --- | --- |
| **MD-04** | `/db/IEHC` `WAreaSize` | 表标 `Integer` | Gen `/info` 是 **`string`**；章节自己的示例发 `"AUTO"` | `DB.IEHC` · `verified`；我方**多出 9 个字段含 `WAreaSize`** | 🔴 见 §3.6(c) |
| **MD-09** | `/DESIGN/RC/.../DCRM-*`、`/DESIGN/SRC/AIK-SRC2K/LLRF` | `enum` 只列 5 个钢筋规格 / 6 个系数 | 同行 description 说 **19 种 / 11 个** —— **采样 enum 冒充完整值集** | 两键均 `verified` | 🔴 若我方照抄手册 `enum` 则同错；**建议加 `description` 标注"非完整值集"** |
| **MD-11** | `/db/SBDO`、`/db/MATL`、`/ope/AUTOMESH`、`/db/RCHK` | 表与同节 JSON Schema **类型互相矛盾**；两个改变值形状 | `/db/SBDO` `AXIS_VECTOR` 标 Number 实为**数字数组**；`/db/MATL` `PARAM` 标 Object 实为 **array** | 四键中 `DB.SBDO`/`DB.MATL`/`DB.RCHK` `verified`，`OPE.AUTOMESH` `untested` | 🔴 **§3.6(b) 显示我方 `SBDO` 多出 `AXIS_VECTOR`** —— 交叉印证 |
| **MD-13** | `/db/TDME` `"SCALE"` | 一个键给两行（`Number` 与 `Array[Object]`） | 2026-09-02 `/info` 定案：真名 **`aDATA`** | `DB.TDME` · `verified` | 🟡 改键名 |
| **MD-18** | `/db/THGC-M1` `INIT_LOAD_TYPE` | enum 两个选项**都印成字面 `0`** | 实际是 `0` 与 `1` | `DB.THGC-M1` · `unverified` | 🟡 修 enum |
| **MD-27** | `/db/RCHK` 五个计数字段 | 表与同节 schema 在 `integer`/`number` 上**五个字段全部相反** | 示例发整数**无法定案** | `DB.RCHK` · `[CIVIL_NX]` · `verified` | 🟡 需实测定案 |
| **MD-51** | `/ope/MEMB` `SELECTION_TYPE` | 官方表把键拼成 **`"SELETION_TYPE"`**（少一个 C） | 原始文章全文读取 + live 确认 | `OPE.MEMB` · `untested` | 🔴 核对我方拼写 |
| **MD-49** | `/post/TABLE` 面弹簧反力 `TABLE_TYPE` | 表与 schema 给 `REACTIONSURFACESPRING` | **只有示例给对的 `REACTIONLSURFACESPRING`**（多一个 L） | `POST.TABLE.*` 199 键 | 🔴 **查我方 `TABLE_TYPE` 枚举是否含错拼**；注意"多数决不可信" |
| **MD-62** | `/ope/DIVIDEELEM` Unequal / ParametricUnequal | 六个字段标 Required 且无条件 | 实际按 **Equal 行的坐标轴规则** | `OPE.DIVIDEELEM` · `untested` | 🟡 建模条件 |

### 1.4 必填性 / 条件类

| MD | 端点 | 手册主张 | 实测结论 | 我方键 / 现状 | 建议 |
| --- | --- | --- | --- | --- | --- |
| **MD-15** | `/db/SECT`、`/db/SPFC` | 同一个 `Create Only` 值用于两份**不同**契约；`/db/SPFC` 示例按原文**被拒** | Gen NX 2026-09-03 live | 两键均 `verified` | 🟡 区分语义 |
| **MD-16** | `/db/MVHL` 公共 Specifications 表 | 分支必填性写成**无条件**必填，未提 `VEHICLE_LOAD_NUM` 是**分支判别子** | Civil NX 2026-09-03 live | `DB.MVHL` · `verified` | 🔴 按分支拆 `required` |
| **MD-17** | `/db/PRES` `DIRECTION` + 该节自己的示例 | 行标 **Optional 默认 `"NORMAL"`** | **省略与填 `"NORMAL"` 都被拒** —— **省略即触发坏默认值** | `DB.PRES` · `verified` | 🔴 **最高优先**：`DIRECTION` 必须显式要求，不得给默认值 |
| **MD-19** | `/db/THGC-M1` `ITER_PARAM.LINE_SEARCH` 子项 | 五个子项**全标 Required** | 同节 Python 示例**只发一个** | `DB.THGC-M1` · `unverified` | 🟡 **未实测**（需 PUT 写操作） |
| **MD-24** | `/DESIGN/RC/…/BRD-TABLE`、`CD-TABLE`，`ELEMS`/`SECTIONS` | 两行标 조건부，**全节无一处给出条件** | 同章 15 处对照（但两节本身无示例） | 两键均 `untested` | 🟡 补条件 |
| **MD-28** | `/ope/AUTOMESH` `MESH_SIZE`、`INCLUDE_INTERIOR_LINES` | **互斥二选一的两字段都标 Required**；`INCLUDE_INTERIOR_LINES` 不列成员 | 同节两个 Request Body + schema | `OPE.AUTOMESH` · `untested` | 🟡 改为互斥二选一 |
| **MD-33** | `/DESIGN/RC/…/CD-TABLE`、`BRD-TABLE`，`ELEMS`/`SECTIONS` | 二者是"**恰好其一**"，同章另七节都这么说，**只这两节不说** | chapter 26 七节对照（行 + schema `oneOf`） | 两键均 `untested` | 🟡 补 `oneOf` |
| **MD-57** | `/db/SPLC` 行 25-29 与 `NDP` | 六个字段标 **Required** | **实际全部可省略** | `DB.SPLC` · `verified` | 🟡 核对我方 `required` |
| **MD-58** | `/db/STCT` `vSDLE` | 行 9 标 Required 且**无条件** | 实际 `bSDLE` **关闭时非必需** | `DB.STCT` · `verified` | 🟡 改为条件必填 |
| **MD-59** | `/db/ELEM` 按类型表 | 四个 Required 行 | **实际都可选**；且 Civil **拒绝所有 `WALL`** | `DB.ELEM` · `verified` | 🔴 与 MD-06 合并处理 |

### 1.5 产品差异未标注类

| MD | 端点 | 手册主张 | 实测结论 | 我方键 / 现状 | 建议 |
| --- | --- | --- | --- | --- | --- |
| **MD-06** | `/db/ELEM` `TYPE:"WALL"` on Civil | 未标注产品差异 | Gen **接受**手册形状的 WALL；**Civil NX v2.2 报不支持单元类型** | `DB.ELEM` · `[CIVIL_DESIGNER, CIVIL_NX, GEN_NX]` | 🔴 需 `product_overrides` 或 `description` 标注 |
| **MD-14** | `/db/TDME` `CODENAME` `Japan(hydration)`/`Japan(elastic)` | 码表**混入另一产品（iGen）的值**且未标注 | 两值均 `Wrong Field` 且**这是正确的** | `DB.TDME` · `verified` | 🟡 标注产品范围 |
| **MD-46** | 十个 `/db/*` 节 / **73 个字段** | 手册每节只有**一张无产品限定的表** | **两个产品声明的记录不同**（`--divergence`：177 对中 10 对不同） | 我方 `product_overrides` 机制正为此 | 🟡 **核对 `product_overrides` 覆盖度** |
| **MD-56** | `/db/EPMT` on Civil NX | 未标注产品差异 | 同一 payload **Gen 通过、Civil 答 `Wrong Field`**，而 `/info` 两产品形状相同 | `DB.EPMT` · `verified` | 🟡 见 §3.6(b)：我方 EPMT 多出 `MASONRY` 13 字段 |

### 1.6 全局事实类

| MD | 端点 | 手册主张 | 实测结论 | 我方现状 | 建议 |
| --- | --- | --- | --- | --- | --- |
| **MD-05** | 模型文件扩展名（全局） | 示例仍用 pre-NX 拼写 | **四扩展两对**：pre-NX Gen `.mgb` / Civil `.mcb`；**NX Gen `.mgbx` / Civil `.mcbz`**。`/doc/SAVEAS` 要 **NX 对**，`/doc/STAGAS` 要 **legacy `.mcb`** 且拒绝其他拼写；Civil 还**容忍** `.mcbx` 但非其自身扩展名 | `DOC.SAVEAS` `verified` / `DOC.STAGAS` `untested` | 🔴 手册与 `description` 全面核对扩展名 |
| **MD-32** | `/DESIGN/SRC/AIK-SRC2K/OCHECK` 路由本身 | 文档 URL | **干净 404**；实际路由移入 **`/TEMP/`** 前缀，且**该路由会终止 NX 会话并占住 license**（4 次复现：07-31 / 08-07 / 08-13 / 08-24） | 我方为 `DESIGN.SRC.AIK-SRC2K.OCHECK`（**无 `/TEMP/` 前缀**）· `untested` | 🔴 见下"命名分歧" |
| **MD-52** | `/ope/MEMB` 请求示例 | 同一文章 id、同一 `updated_at` | **两个 locale 给不同请求示例，`ko` 那个是错的** | `OPE.MEMB` · `untested` | 🟡 以 `en-us` 为准 |
| **MD-55** | `/db/TDMF` Creep 示例 | 示例 | 示例**在两个产品上都被拒**；`/info` 另有**未文档化**的 `ELAST` | `DB.TDMF` · `verified` | 🟡 补 `ELAST` + 修示例 |

### 1.7 示例不可运行类

| MD | 端点 | 手册主张 | 实测结论 | 我方键 / 现状 | 建议 |
| --- | --- | --- | --- | --- | --- |
| **MD-53** | `/db/MATD` 钢筋等级示例 | 示例让强度看起来**由等级推导** | **实际强度是必需输入** | `DB.MATD` · `verified` | 🟡 手册示例标注 |
| **MD-54** | `/db/FIMP` Kent & Park 示例 | 章节示例的三个数值 | **不满足产品自述关系**；且**文章并未印这些值**（转写引入） | `DB.FIMP` · `verified` | 🟡 标注"示例为转写引入，非官方原文" |

### 1.8 我方工具缺陷，**不得转嫁手册**（分组 C）

> 对方原文结论：**"先查工具再指认手册"**。以下 7 条是其**自身提取器**的缺陷，
> 手册内容**是对的**。我方**不应**据此改动任何手册文字或 registry 数据。

| MD | 端点 | 对方结论 | 我方动作 |
| --- | --- | --- | --- |
| **MD-36** | `/db/LCOM-*`、`/db/POGD` 成员行 | 手册用最显式的 `(vCOMB)` 命名父级形式，对方解析器**唯独不读这一种** | ⚪ 不改 |
| **MD-42** | `/db/GRDP` `GROUP_DAMPING_ITEMS[]` 十五成员 | 手册用**散文**列出十五个成员且**全对**，是解析器只读表格行 | ⚪ 不改 |
| **MD-44** | 五数组 + 一对象，跨 `/db/SLAN`、`/db/POLC`、`/db/ACTL-M1`、`/db/NLNK`、`/db/NLNK-M1` | 成员都在**编号表格行之外**陈述，手册**全对**，解析器全没读到 | ⚪ 不改 |
| **MD-48**（部分） | `/db/MVHL` | 同上性质（但含真实缺失字段，已在 1.2 计入） | ⚪ 部分不改 |
| **MD-50** | `/db/MVCTch` | 双 Key 列的表只被读了一半；`BTYPE` 写在**粗体引导句**里 | ⚪ 不改 |
| **MD-10**（部分 5 条） | `/db/EPMT`、`/db/ELEM`、`/db/RCHK`、`/db/FIMP` | 5 条实为对方解析器缺陷 | ⚪ 部分不改 |
| **MD-43**（部分） | `/db/SLANch` | 层级误读，部分归因解析器 | ⚪ 部分不改 |

---

## 2. 已撤回的主张 —— **禁止采纳**

对方于 **2026-07-27** 用 **Zendesk 官方文章**（而非其 vendored 转写本）复核后**撤回了 7 个 B 项中的 4 项**。
这些主张**不得**传入我方任何产物（手册、registry、报告）：

| 原主张 | 撤回原因 |
| --- | --- |
| `/db/TDMT` 的"精确 28 值枚举" | 实为把 `NAME` 列读成了 `CODE` 列 |
| `/db/TDME` 的 `"KDS2016"` | **官方文章里根本没有这个值**，是转写错误 |
| `/db/SECF` 的"keyed by element id" | **是该 SDK 自己的 docstring**，不是 MIDASIT 的说法 |
| `/db/PRES` 的 `FORCES` 长度 | 复核后不成立 |
| `/db/MVHL` 的 `VEHICLE_LOAD_NUM` "未按文档工作" | **已撤回** —— 它是**分支判别子**（1 标准 / 2 用户定义），行为与文档一致。真正的问题是通用表把**分支必填性写成无条件必填**，即 **MD-16** |

**对方给出的铁律（建议照抄进我方文档规范）**：

> **Never cite the vendored manual as "the documentation" in anything sent outside —
> fetch the article and quote it.**
>
> 绝不要把转写本手册当作"文档"引用到任何对外材料；要主张 MIDASIT 发布了什么，
> 必须取官方文章并引用原文。

**对我方的直接含义**：我方 `MIDAS_API_Online_Manual_*` 同样是**转写本**。
任何对外材料（含提交给 MIDASIT 的缺陷报告）**必须**回到
`https://support.midasuser.com/hc/en-us/articles/{id}` 引用原文，
不能引用我方整理稿。建议在 `registry/README.md` 的治理规则中显式写入此条。

---

## 3. 两项需要特别处理的命名分歧

### 3.1 `DESIGN.SRC.AIK-SRC2K.OCHECK` 的 `/TEMP/` 前缀（MD-32）

| | 值 |
| --- | --- |
| 我方键 / URI | `DESIGN.SRC.AIK-SRC2K.OCHECK` / `DESIGN/SRC/AIK-SRC2K/OCHECK` |
| 对方 coverage / 契约 | `/TEMP/DESIGN/SRC/AIK-SRC2K/OCHECK`（**带 `/TEMP/` 前缀**） |
| 对方 `/info` | **404** |
| 对方契约 | `products: [civil, gen]`，来源含 `liveNotes` |
| 我方 `availability` | `untested`；`unavailable_on: [gen-local]`（`registry/README.md` §8.1 记载实测 404） |

**对方登记的关键事实**：该路由**会终止 NX 会话并占住 license**（4 次复现）。
对方 `docs/vendor_report_triage.md` 将该条列为 **"the author's call, not a drafting one"**（保留，未上报）。

**建议**：
1. 🔴 **将 `DB`/`DESIGN` 的 `risk` 建模扩展**，为此类"调用即杀会话"的端点引入显式标记
   （我方现有 `risk.level` 只有 `low`，不足以表达）。对方 `safety.md` 的 0–4 级风险模型可直接借用：
   `4 = High risk`（`.delete()` / `doc.new_project()` / `doc.analyze()` …）。
2. 🟡 核实 `/TEMP/` 前缀是否为我方 URI 的漏写 —— 若路由确在 `/TEMP/` 下，
   我方 `uri` 需更正，否则必然 404。

### 3.2 `/db/PRES` 的 `DIRECTION`（MD-17）—— 我方需优先处理

对方 2026-09-03 完整实测的结论比"默认值错"更严重：

> **省略 `DIRECTION` 正是坏默认值被应用的途径** —— 行的两半（"Optional" 与 "default `NORMAL`"）**一起失败**。
> 两个 SDK 现在都**要求 `DIRECTION` 显式给出**，不替调用方选任何值 ——
> 因为压力作用方向是**工程决策**，不是 SDK 能选的（契约规则 `db-pres-direction-must-be-explicit`）。

**建议**：🔴 我方 `DB.PRES` 若给了 `DIRECTION` 默认值，应移除；并在
`required` 或等价机制中要求显式给出。这是"宁可拒绝、不替工程师做工程决策"的范例，
与我方 `docs/07` 的架构红线方向一致。

---

## 4. 对方给出的方法论规则（建议纳入我方文档规范）

对方在其摘要附录中列出的 10 条贯穿性规则，对我方同样适用：

1. **`/info` 既不是服务端可接受集合的超集，也不是子集** —— 缺失只支持"加注"，
   **绝不支持删除**已转录字段。删除需要一次 live 对比（文档形状被拒、另一形状被接受）。
2. **`/info` 与 live round trip 冲突时，round trip 胜。**
3. **`/info` 只对 `/db/*` 提供**；`/DESIGN/*` 全部 404 是 **API 事实，不是 URL bug**。
   三个例外：`/db/IEHG-GL-M1`、`/db/IEHG-PSS-M1`、`/db/IEHG-TRUSS-M1`。
4. **`documentedOptional`（关于文档）与 `safeToOmit`（关于产品）是两个独立布尔量**，不可合并。
   `safeToOmit` 取 `true` / `false` / **`"unverified"`** —— `"unverified"` 不是较差状态。
   范例：`/db/NMAS` 的 `rmX` 是 `documentedOptional: true` + `safeToOmit: false`。
5. **`risk`（端点是什么）与 `mitigation`（SDK 做了什么）是两条独立轴** ——
   已缓解的崩溃风险**仍然是崩溃风险**。
6. **写路径实测覆盖远低于读路径**：对方 337 个 CRUD 用例中 297 个 `confirmed`；
   且**每个字段名 / 枚举 / 默认值缺陷对 GET 都是不可见的** —— 只有 round trip 能证明请求形状被接受。
7. **`"Wrong Field"` 通常意味着值错，不是字段名错** —— 先变枚举值。
8. **一个文档缺陷在被官方文章核实前不算已证实。**
9. **一次"多数决"不可信**（MD-49：表和 schema 都错，只有示例对）。
10. **`/post/TABLE` 的顶层响应键不稳定**（`"Result Table"` / `"empty"` / 传入的 `TABLE_NAME`），
    必须**按形状匹配**（找含 `HEAD`/`DATA` 的对象）；**`"empty"` 不是"无数据"标记**。

---

## 5. 与我方现有数据的交叉印证（已确认同向的强证据）

以下 6 条**同时**被对方的 `/info` 实测与本勘误册指认，且与我方数据冲突 —— **建议优先处理**：

| # | 端点 | 我方现值 | 应有值 | 双重证据 |
| --- | --- | --- | --- | --- |
| 1 | `/db/REBC` `ITEMS[].HOOP_TYPE` | `string` | `integer`（1=Tied, 2=Spiral） | `/info` description + MD-34 |
| 2 | `/db/REBR` `ITEMS[].HOOP_TYPE` | `string` | `integer` | `/info` description + MD-34 |
| 3 | `/db/SLANop` `OPT_STRADD` | `integer` | `boolean` | `/info` description "…Boolean" + MD-45 |
| 4 | `/db/SBDO` `AXIS_VECTOR` | （我方多出该字段） | 数字数组，非 `Number` | `/info` + MD-11 |
| 5 | `/db/STRPSSM` `POINT1`/`POINT2` | 4 缺 4 多 | `Y`/`Z` 而非 `PY`/`PZ` | `/info` + MD-38 |
| 6 | `/db/IEHC` `WAreaSize` | （我方多出该字段） | `string`（如 `"AUTO"`） | `/info` + MD-04 |

---

## 6. 落地清单

| 优先级 | 动作 | 涉及 | 需实测 |
| --- | --- | --- | --- |
| 🔴 P0 | `DB.PRES` 移除 `DIRECTION` 默认值，改为显式要求 | 1 键 | 否（对方已实测，建议复测） |
| 🔴 P0 | 6 条交叉印证的类型/字段修正（§5） | 6 键 | 否（双证据） |
| 🔴 P1 | `DB.REBR` 整个 item 形状按 `/info` 重建 | 1 键 | 建议（对方未对 REBR 做 POST 对比） |
| 🔴 P1 | `/db/SWIND`、`/db/SSEIS` 形状实测（见主报告 §3.6a） | 2 键 | **是** |
| 🔴 P1 | 21 条 Hyper-S `products` 改正（见主报告 §3.1） | 21 键 | 否（三证据同向） |
| 🟡 P2 | 扩展名（MD-05）、`TABLE_TYPE` 拼写（MD-49）、`SELECTION_TYPE`（MD-51）核对 | 全局 | 否 |
| 🟡 P2 | 必填性类 MD-16/24/28/33/57/58/59/62 复核 `required` | 约 12 键 | 部分 |
| 🟡 P2 | `product_overrides` 覆盖度核对（MD-46，73 字段） | 10 节 | 否 |
| 🟡 P2 | 引入 0–4 级风险模型（§3.1 建议） | 全局 `risk` | 否 |
| ⚪ P3 | 分组 C（7 条工具缺陷）仅记录，不改动 | — | — |
| ⚪ P3 | §2 的 5 条已撤回主张列入"禁止引用"清单 | 文档规范 | 否 |

---

## 附录：本附录的可复现性

- 源登记册：`.tmp_nxsdk/docs/manual_defects_register.md`（1917 行）—— 浅克隆
  `git clone --depth 1 https://github.com/Dennis5882/MIDAS-API-NX-SDK.git`
- 中文逐条摘要：`.tmp_analysis/sdk_manual_defects_digest.md`（484 行，62/62 覆盖）
- 我方映射：`.tmp_analysis/md_registry_map.json`（由 `p22_md_map.py` 生成）
- 机器可读勘误表：[`docs/nxsdk_review/nxsdk_manual_errata.csv`](docs/nxsdk_review/nxsdk_manual_errata.csv)

**⚠️ 再次声明**：本附录全部 62 条均为**外部证据**。对方登记册自我定位为
**"This file collects; it does not act."** —— 它只收集，不执行任何动作，
没有任何一条被应用到手册仓库、发送给 MIDASIT 或记入 Jira。
我方采纳时须逐条走**实测 + 裁决**流程。
