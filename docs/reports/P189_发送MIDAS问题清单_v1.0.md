# P189 —— 发送 MIDAS 问题清单（正式交付件 · 干净版）

> 批次：**P189**（项 A · **零请求** · 不改 registry / 不动真机 / 不改主指标）
> 基础：`docs/reports/P186_向MIDAS的4个问题_v1.0.md`（P186-A + P186-B + P187 + P188 收敛结果）
> 用途：把已收敛的「向 MIDAS 的 **5 条问题**」做成一份**可直接对外发送**的正式交付件 ——
> 含 **① 5 条问题一览表**、**② 一封信正文（可直接粘贴）**、**③ 复现证据索引**、**④ 我方已排除项**。
> 本文件**只做排版与索引**：**不新增**任何裁决、**不改**任何裁定、**不发**任何请求。
>
> 权威来源（判定口径，均已在各批落定）：
> - `R171`（P178）—— `DB.REBR::HOOP_TYPE` 类型冲突
> - `R172`（P179）—— `DESIGN.RC.KDS-41-20-2022.DCRE::SPLICED_BARS` 类型冲突
> - `R164`（P171）—— `OPE.GSBG::BRDG_GROUP` 自由引用名（已裁决）· `OPE.LCOM-GEN::DGNCODE` 收窄为键名是非问答
> - `P186-B` / `P188` —— `DESIGN.RC.REBC` 与 `REBR` 真机证伪「前置对象缺失」，归因 = 键名 / 形状层（同族合并一问）

---

## 0. 一句话结论

本 build 里，**真正需要 MIDAS 产品侧回话的只有 4 个问题**（①②④⑤），第 5 项（③）我方已自查清楚、无需回复；
其中 **④⑤ 同属「`Wrong Field` / 键名层」**（已用真机证伪「前置对象缺失」），**①② 同属「类型冲突」**；
共同根因是「**来源冲突 / 不可判别**」⇒ 我方策略是**宁可拦、不猜**（`R151`），恢复条件统一为
「**产品侧给权威结论** **或** **一次授权真机测量**」。

---

## 1. 五条问题一览表

| # | 端点 / 字段 | 类别 | `Wrong Field`? | 需产品侧回话 | 恢复条件 | 我方当前处置（留缺期间） |
|---|---|---|---|---|---|---|
| ① | `DB.REBR :: ITEMS[].HOOP_TYPE` | **类型冲突**（integer vs string） | 否（非本问题） | **要** | 产品侧结论 **或** 一次授权 `PUT` 两写法 | 整数 `1`/`2` **放行**（与 `/info` 一致）；字符串被拦 |
| ② | `DESIGN.RC.KDS-41-20-2022.DCRE :: Assign.1.{BEAM,COLUMN,BRACE}.SPLICED_BARS` | **类型冲突**（string enum vs integer 示例） | 否（非本问题） | **要** | 产品侧结论 **或** 一次授权 `PUT` 两写法 | 字符串 `"None"/"50%"/"100%"` **放行**（与落盘一致）；整数被拦 |
| ③ | `OPE.GSBG :: Argument.BRDG_GROUP` | **自由引用名**（非受控词表） | —（已裁决，**无需问**） | **不要** | 无需恢复；上游若改声明再重跑普查 | 不加 `enum`（硬凑会拦合法 `Girder_All`/`SG1`） |
| ④ | `OPE.LCOM-GEN`（键名 `OPTION` 是否存在） | **键名疑点**（收窄为一次是非问答） | **是**（任何取值） | **要** | 产品侧答 **是 / 否** 任一 | Schema 保持现状；不按示例硬凑 |
| ⑤ | `DESIGN.RC.KDS-41-20-2022.REBC` **与** `REBR`（同族合并一问） | **键名 / 形状疑点**（真机：前置无关 + `Wrong Field`） | **是**（任何写法，前置单元已就绪亦然） | **要** | 产品侧给正确键名/包装 **或** 确认形体无误（登记产品不支持） | 不硬凑（`R151`）；不碰 `*-ANAL`（`R154`） |

> **需回话 = 4 个**（①②④⑤）；其中 **⑤ 已把 REBC / REBR 合并为同一问**（P188 证同族同因）。
> 表内「`Wrong Field`?」列仅标示是否为该问题的机械特征；①② 是**类型冲突**，不是 `Wrong Field`。

---

## 2. 一封信（可直接粘贴发送）

> **主题：MIDAS Open API 对接 —— 4 个需要贵方确认的请求/字段契约问题**
>
> 您好，
>
> 我们在对接 **MIDAS Open API（GEN NX）** 时，遇到 **4 个需要贵方确认的点**（另有 1 个我们已自查清楚、无需回复）：
>
> **1. `PUT /db/REBR` 的 `HOOP_TYPE` 字段类型**
> 本 build 的 `/info/db/REBR` 自省声明其为 **integer**（`1=Tied, 2=Spiral`）；
> 但手册示例体（`MIDAS_API_Online_Manual_Gen_NX_v1.0.json` article #835）给的是 **字符串 `"Spirals"`** —— 两者冲突。
> 请问：`HOOP_TYPE` 接受**整数 `1`/`2`**、**字符串 `"Ties"`/`"Spirals"`**，还是**两者都接受**？
> （注：这与 `DESIGN.RC...REBR` 的 `HOOP_TYPE` 是两条不同路由，后者本就是 string，非同一字段。）
>
> **2. `PUT /DESIGN/RC/KDS-41-20-2022/DCRE` 的 `SPLICED_BARS` 字段类型**
> 我们落盘的枚举是**字符串** `["None","50%","100%"]`；
> 但手册示例体给的是 **整数 `1`**（`Assign.1.{BEAM,COLUMN,BRACE}.SPLICED_BARS = 1`）。
> 请问：`SPLICED_BARS` 接受**字符串 `"None"`/`"50%"`/`"100%"`**、**整数 `0`/`1`/`2`**，还是**两者**？
>
> **3. `POST /OPE/LCOM-GEN` 请求体 —— 选择操作的键名是否为 `OPTION`？**
> 我们对 `POST /OPE/LCOM-GEN` 的**任何**取值都收到 `400 Wrong Field`（连手册声明的合法值也一样）。
> 请问：选择操作的那个键，键名是 **`OPTION`** 吗？（这是**一次是非问答**，无需样例。）
>
> **4. `PUT /DESIGN/RC/KDS-41-20-2022/REBC` 与 `/REBR`（同族）—— 请求体的正确顶层键名 / 包装是什么？**
> 对这两个端点，请求体 `Assign → 截面号 → ITEMS[]`（含 `MAIN_BAR`/`SHEAR_BAR_END`/`SHEAR_BAR_CEN`/`DO`/`ELEMS`）
> 的**任何**写法都回 `400 {"error":{"message":"Wrong Field"}}` —— **即使前置单元 / 截面已真实存在并读回亦然**（REBC、REBR 同形）。
> 请问：该端点请求体的**正确顶层键名 / 包装**是什么？是否另有必填键
> （如 `Assign` 之上的包装、或 `ITEMS[]` 内的必需子键）？
>
> （**第 5 项 `OPE.GSBG :: BRDG_GROUP`** 我们已确认它是**模型内 StructureGroup 的引用名、非受控词表**，
> 传递模型已有组名（如 `SG1`）与我们自建组名均被接受 ⇒ **无需贵方回复**。）
>
> 如方便，也请告知是否有对应的**权威请求示例**可提供（尤其第 4 项）。
> 谢谢！

---

## 3. 复现证据索引（本仓可读，均零成本复算或已落盘证据）

| 问题 | 可复算命令（`--check` 零请求） | 落盘证据 / 来源 |
|---|---|---|
| ① `DB.REBR::HOOP_TYPE` | `python registry/tools/check_spec_enums.py --check` | `/info/db/REBR`（`{"type":"integer","description":"Hoop Type (1=Tied, 2=Spiral)"}`）· 手册 `MIDAS_API_Online_Manual_Gen_NX_v1.0.json` article #835（示例 `"HOOP_TYPE":"Spirals"`）· `R171`（P178） |
| ② `DCRE::SPLICED_BARS` | `python registry/tools/check_spec_enums.py --check`（此条为 4 条 `left_open` 之一） | `registry/schema/products/gen_nx/design/.../DCRE` 落盘枚举 `["None","50%","100%"]` · 手册 `MIDAS_API_Online_Manual_数据_v1.0.json`（`SPLICED_BARS` 出现 0 次，仅示例给 `1`）· `/info/design/RC/KDS-41-20-2022/DCRE` 只声明 `type` · `R172`（P179） |
| ③ `OPE.GSBG::BRDG_GROUP` | —（已裁决，无需复算） | `registry/schema/products/gen_nx/ope/GSBG.json`（`Argument.BRDG_GROUP` 仅 `{"type":"string"}` + `additionalProperties:false` + `if/then/not`）· `docs/nxsdk_review/evidence/02_实测发现_中文摘要.md` §D-19 · `nxsdk_availability_upgrade.csv`（`/OPE/GSBG` 行）· `R164`（P171） |
| ④ `OPE.LCOM-GEN::DGNCODE` | `python registry/tools/check_spec_enums.py --check`（4 条 `left_open` 之一） | `registry/live/lcom_dgncode_probe.json`（P169 真机：任何取值 400 `Wrong Field`）· 手册 `json_schema`（#253）与落盘 Schema 逐字节同形 · `E-02`（`POST.TEXT` `TABLE_TYPE`→`TEXT_TYPE` 键名错先例）· `R164`（P171） |
| ⑤ `REBC` / `REBR` | —（真机证据已落盘） | `registry/live/rebc_prereq_probe_p186.json`（P186-B）· `registry/live/rebr_prereq_probe_p188.json`（P188）· `registry/tools/probe_rebc_prereq_p186.py` · `registry/tools/probe_rebr_prereq_p188.py` · `docs/reports/P186B_REBC400归因排查_v1.0.md` · `docs/reports/P188_REBR400归因排查_v1.0.md` |

> **主指标（可执行复算，零请求）**：`python registry/tools/check_operation_availability.py --check`
> ⇒ 生产路径可用 Operation **71 / 73**（被挡 2 · 挡点端点 4，**全部 MIDAS 侧**，`ours` 空集）。
> **窄枚举台账（可执行复算，零请求）**：`python registry/tools/check_spec_enums.py --check`
> ⇒ `closed 22` / `left_open 4`，**与 audit 一致（无差异）**。

---

## 4. 我方已排除项（每条问题「不是这些」）

### ① `DB.REBR::HOOP_TYPE`
- ✗ **不是我方台账串了路由族** —— `DB.REBR` 与 `DESIGN.RC...REBR` 是**两条不同路由**，后者 `HOOP_TYPE` 本就是 string（`["Ties","Spirals"]`，与 `/info/design/.../REBC` 及手册示例同口径）；两者**类型本就不同**（P179 已核实）。
- ✗ **不是有可复算的第三来源可定夺** —— 手册全文中 `Ties`/`Spirals` 出现 **0** 次（只在示例 JSON 里）⇒ 推不出。

### ② `DCRE::SPLICED_BARS`
- ✗ **不是有第三来源可复算** —— `SPLICED_BARS` 在 `MIDAS_API_Online_Manual_数据_v1.0.json` 出现 **0** 次（只存在于 `repo_midas_api` 来源的 Schema 与 Gen NX 手册示例）；`/info/design/RC/KDS-41-20-2022/DCRE` 也**不声明**枚举（只声明 `type`）⇒ 无法判定「示例是旧写法」还是「枚举是错的」。

### ③ `OPE.GSBG::BRDG_GROUP`
- ✓ **已裁决**：它是**单个引用名**（模型内 StructureGroup 名），**结构性不可能**有 `enum`。
- ✗ **不是取值域** —— 若硬凑示例体 `[BG_LEFT, BG_RIGHT]` 两个值，会把合法的 `Girder_All`/`SG1` 这类**真实**取值在**发请求之前**拦掉（`R151` 形态、方向相反）。

### ④ `OPE.LCOM-GEN::DGNCODE`
- ✗ **不是「手册扁平 vs 我方 `oneOf` 的形状分歧」** —— 手册**自己的** `json_schema`（`MIDAS_API_Online_Manual_数据_v1.0.json` #253）与我们**已落盘**的 Schema（`registry/schema/products/gen_nx/ope/LCOM-GEN.json`）**逐字节同形**（同一份 `oneOf` 三分支、同一句 `Body structure is selected by CODE_SELECTION.`）⇒ 形状**无分歧**。
- ✓ **`Wrong Field` 在同族端点的唯一已知成因是键名错**（`E-02`：`POST.TEXT` 的 `TABLE_TYPE` 任何取值都回 `Wrong Field`，实测契约键是 `TEXT_TYPE`）⇒ 疑点**收窄为一处**：`OPTION` 这个键名对不对。

### ⑤ `REBC` / `REBR`
- ✗ **不是「前置对象缺失（单元/截面）」** —— 在 `gen-local` 空项目先建**真实节点 + 单元**（阳性对照 `201`/`200` + 读回真值）后再 `PUT REBC`，**仍 `400 Wrong Field`**（与空项目同形）；`CREATE_SUB_SECTION=true` 变体同形；`REBR` 在前置单元已存在时同样 `400 Wrong Field`、`GET` 读回 `{}` ⇒ **与前置对象无关**。
- ✓ **归因收窄 = 请求体形状 / 键名层**（`Wrong Field` 在同族上的唯一已知成因是键名错；对照 `POST /db/SECT` 缺尺寸回**中文**「截面尺寸输入有错误」（取值级），与 `Wrong Field`（键名级）不同类）。
- ⚠️ **无权威示例**：`REBC` 的 `source = repo_midas_api`（GitHub 韩文整理版），Gen NX 手册 `MIDAS_API_Online_Manual_数据_v1.0.json` 里 `REBC` 出现 **0** 次 ⇒ 无「正确键名 / 包装」的可复算来源。

---

## 5. 本批「不做」的（如实记录）

- **不发任何请求**（零请求）；**不改** `registry/` 任何数据；**不改**主指标 / 收益映射 / 归因。
- **不改**任何裁定 —— 本页只**汇总** `R164`/`R171`/`R172` 与 P186-B/P188 的既有结论并重排为**发送件**。
- **不碰** `DESIGN.{RC,SRC}` 的 `*-ANAL`（`R154` 崩溃族）。
- **一次都不发** `DOC.NEW`（`R144`）。

---

## 6. 复算命令（零请求，可验证本页与台账一致）

```bash
python registry/tools/check_operation_availability.py --check   # 应：生产路径可用 Operation 71 / 73
python registry/tools/check_spec_enums.py --check               # 应：closed 22 / left_open 4，与 audit 一致（无差异）
```
