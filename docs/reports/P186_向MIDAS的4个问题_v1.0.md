# P186/P187 向 MIDAS 的 5 个问题（`left_open` 4 条 + REBC 真机归因 1 条）

> ⚠️ 文件名沿用 P186-A 的旧名（`P186_向MIDAS的4个问题`）以保留 git 引用与交接链；
> 内容已随 **P186-B** 扩展为 **5 条**（新增问题⑤ REBC）。

> 批次：**P186-A（`left_open` 4 条，零请求）** + **P186-B（REBC，真机归因，问题⑤）**
> 用途：把 `check_spec_enums.py --check` 的 **4 条 `left_open`** + P186-B 新增的 **1 条（REBC 键名）**
> 汇总成**一页可直接发给 MIDAS 产品侧**的问题清单 —— 每条含**端点/字段**、**冲突或结构事实**、
> **已排除的可能**、**判据**、**一句可直接问**、**恢复条件**。
> 依据来自**本仓可读证据**（Schema / `/info` 声明 / 手册 `json_schema` / 历史实测 JSON）与 **P186-B 真机证据**；
> **不改任何裁定**、**主指标仍 `71 / 73`**。
>
> 权威来源：`R164`（P171：澄清 2 + 收窄 1）· `R171`（P178：`HOOP_TYPE`）·
> `R172`（P179：`SPLICED_BARS`）· `P186-B`（REBC 真机证伪「前置对象缺失」）。

---

## 分组总览

| # | 端点 / 字段 | 类别 | 需不需要问产品侧 | 谁答复 |
|---|---|---|---|---|
| ① | `DB.REBR :: HOOP_TYPE` | **类型冲突**（integer vs string） | **要**（唯一一次问答） | MIDAS |
| ② | `DESIGN.RC.KDS-41-20-2022.DCRE :: SPLICED_BARS` | **类型冲突**（string enum vs integer 示例） | **要**（唯一一次问答） | MIDAS |
| ③ | `OPE.GSBG :: BRDG_GROUP` | **自由引用名**（非受控词表） | **不要**（已裁决；仅如实登记「此处无 `enum` 是对的」） | —（仅台账口径） |
| ④ | `OPE.LCOM-GEN :: DGNCODE` | **键名疑点**（`Wrong Field` 收窄为键名错） | **要**（一次是非问答） | MIDAS |
| ⑤ | `DESIGN.RC.KDS-41-20-2022.REBC` | **键名/形状疑点**（真机：前置无关 + `Wrong Field`） | **要**（问请求体契约） | MIDAS |

> ⚠️ ①②④⑤ 是**真正需要发出去的问题**（共 **4 个**）；③ 只是「如实留缺」的登记，**不需要**产品侧回话。
> ④⑤ **同族**（`Wrong Field` / 键名层）；①② 是**类型冲突**；共同根因都是「**来源冲突 / 不可判别**」
> ⇒ 我们**宁可拦、不猜**（`R151`）。恢复条件统一是「产品侧给权威结论 **或** 一次授权真机测量」。

---

## 问题 ① —— `DB.REBR :: HOOP_TYPE`（类型冲突，`R171`）

- **端点 / 字段**：`DB.REBR`（`PUT /db/REBR`）的 `Argument` 下 `ITEMS[].HOOP_TYPE`。
- **冲突事实**：
  - **`/info/db/REBR` 权威声明**：`{"type": "integer", "description": "Hoop Type (1=Tied, 2=Spiral)"}`
    ⇒ 官方**结构化自省**站在 **integer `1` / `2`** 一侧。
  - **但手册自己的示例体**（`MIDAS_API_Online_Manual_Gen_NX_v1.0.json`，article #835）
    写的是 **`"HOOP_TYPE": "Spirals"`** —— **string**，与 `/info` **冲突**。
  - ⚠️ **不是**「我方台账串了路由族」：`DB.REBR` 与 `DESIGN.RC.KDS-41-20-2022.REBR` 是
    **两条不同路由**，后者的 `HOOP_TYPE` **本就**是 string（`["Ties","Spirals"]`，`/info/design/.../REBC`
    与手册示例同口径）。两者**类型本就不同**。
  - **无第三来源**：手册全文中 `Ties` / `Spirals` 出现 **0** 次（只在示例 JSON 里）。
- **已排除**：
  - ✗ 「我方台账串族」—— 两条路由类型本不同，已核实（P179）。
  - ✗ 「有可复算的第三来源可定夺」—— 手册全文 0 次，推不出。
- **判据**：本 build 的 `/db/REBR` 的 `HOOP_TYPE` 到底接受**哪种类型**。
- **可直接问（一句）**：
  > 本 build 的 `/db/REBR` 的 `HOOP_TYPE` 接受**整数** `1` / `2`、**字符串** `"Ties"` / `"Spirals"`，
  > 还是**两者都接受**？
- **答复分支与恢复条件**：
  - 只接受整数 ⇒ 手册示例（#835）需**勘误**；我方 integer 枚举**正确** ⇒ 台账 `closed`。
  - 只接受字符串 ⇒ 我方 Schema **类型错**，须改 `string` + 该枚举。
  - 两者都接受 ⇒ 枚举须改 `oneOf[{integer},{string}]`（**另一件事**，须单独裁决）。
  - 或：一次**授权真机测量**（`PUT` 两种写法各一次）。
- **留缺期间的处置（有意）**：整数 `1` / `2` **仍放行**（与 `/info` 一致）；字符串被拦
  —— 宁可我方拦，也不把与 `/info` 冲突的取值放行到原生。

---

## 问题 ② —— `DESIGN.RC.KDS-41-20-2022.DCRE :: SPLICED_BARS`（类型冲突，`R172`）

- **端点 / 字段**：`DESIGN.RC.KDS-41-20-2022.DCRE` 的
  `Assign.1.{BEAM,COLUMN,BRACE}.SPLICED_BARS`。
- **冲突事实**：
  - **落盘枚举是 string** `["None", "50%", "100%"]`（`description` = 「이음 옵션」= 拼接选项）。
  - **手册自己的示例体**给的是 **integer `1`**（`Assign.1.{BEAM,COLUMN,BRACE}.SPLICED_BARS = 1`）。
- **已排除**：
  - ✗ 「有第三来源可复算」—— `SPLICED_BARS` 在 `MIDAS_API_Online_Manual_数据_v1.0.json`
    出现 **0** 次（只存在于 `repo_midas_api` 来源的 Schema 与 Gen NX 手册示例）；
    `/info/design/RC/KDS-41-20-2022/DCRE` 也**不声明**枚举（只声明 `type`）。
  - ⇒ 无法判定「示例是**旧写法**」还是「枚举**是错的**」。
- **判据**：无法靠现有来源判定 ⇒ **不混型**（混型会**放松**闸门，是 `R151` 的镜像错误）。
- **可直接问（一句）**：
  > `DESIGN.RC.KDS-41-20-2022.DCRE` 的 `SPLICED_BARS` 接受**字符串** `"None"` / `"50%"` / `"100%"`、
  > **整数** `0` / `1` / `2`，还是**两者**？（手册示例给 `1`，落盘枚举给字符串。）
- **答复分支与恢复条件**：
  - 只接受字符串 ⇒ 示例体需**勘误**；落盘枚举**正确** ⇒ `closed`。
  - 只接受整数 ⇒ 我方 Schema **类型错**，须改 integer + 该枚举。
  - 两者都接受 ⇒ 枚举改 `oneOf[{string},{integer}]`（单独裁决）。
  - 或：一次**授权真机测量**（`PUT` 两种写法各一次）。
- **留缺期间的处置（有意）**：字符串三值**仍放行**（与落盘一致）；整数被拦。

---

## 问题 ③ —— `OPE.GSBG :: BRDG_GROUP`（自由引用名，**无需问**，`R164`）

> ⚠️ 这条**不是**「待澄清」——**已裁决**：它是**单个引用名**，**结构性不可能**有 `enum`。
> 本页收录它只为**如实登记**「此处没有 `enum` 是**正确**的」，**不需**产品侧答复。

- **端点 / 字段**：`OPE.GSBG`（`POST /OPE/GSBG`）的 `Argument.BRDG_GROUP`。
- **结构事实（本仓可读，零请求）**：
  - `registry/schema/products/gen_nx/ope/GSBG.json` 的 `Argument.BRDG_GROUP` **只**声明
    `{"type": "string"}`，且该体是 `additionalProperties: false` + `if/then/not` 的**结构约束**
    （`BATCH=true` 时**禁止** `BRDG_GROUP`；`BATCH=false` 时**要求**它）⇒ 它是**单个引用名**，
    **不是**取值域。
  - **既有实测证据**（`docs/nxsdk_review/evidence/02_实测发现_中文摘要.md` §D-19 +
    `nxsdk_availability_upgrade.csv` 的 `/OPE/GSBG` 行）：在**真实 Civil NX 会话**上，
    `BRDG_GROUP` 传**自建** `StructureGroup` 名（如 `Girder_All`）越过「组不存在」错误、
    传模型**既有**的 `SG1` 分组名也被接受 ⇒ **取值随模型而定**（= `/db/GRUP` 组名）。
- **为什么要「留缺」而不是补 `enum`**：若硬凑示例体的 `[BG_LEFT, BG_RIGHT]` 两个取值，
  会把**合法**的 `Girder_All` / `SG1` 这类**真实**取值在**发请求之前**拦掉（`R151` 形态，方向相反）。
- **恢复条件**：**无需恢复**；若上游手册日后改声明为受控词表 ⇒ 重跑
  `python registry/tools/check_spec_enums.py`（届时闸门会如实纳入检查）。

---

## 问题 ④ —— `OPE.LCOM-GEN :: DGNCODE`（键名疑点，`R164`，已收窄为一次是非问答）

- **端点 / 字段**：`OPE.LCOM-GEN`（`POST /OPE/LCOM-GEN`）请求体（`CODE_SELECTION.OPTION` 相关）。
- **机械事实**：本 build 对 `POST /OPE/LCOM-GEN` 的**任何**取值都回
  **`400 Wrong Field`**（`registry/live/lcom_dgncode_probe.json`，P169 真机）——
  **连手册声明的合法值**也一样。
- **已排除**：
  - ✗ 「手册扁平 vs 我方 `oneOf` 的形状分歧」—— 手册**自己的** `json_schema`
    （`MIDAS_API_Online_Manual_数据_v1.0.json#253`）与我们**已落盘**的 Schema
    （`registry/schema/products/gen_nx/ope/LCOM-GEN.json`）**逐字节同形**
    （同一份 `oneOf` 三分支、同一句 `Body structure is selected by CODE_SELECTION.`）
    ⇒ 那份 `oneOf` 就是**上游**的声明，形状**无分歧**。
  - ✓ `Wrong Field` 在**同族**端点上的**唯一**已知成因是**键名错**
    （`E-02`：`POST.TEXT` 的 `TABLE_TYPE` 任何取值都回 `Wrong Field`，实测契约键是 `TEXT_TYPE`）。
- **判据**：疑点**收窄为一处** —— `OPTION` 这个键名对不对
  （手册**另一族** `OPE.LCOM-{CONC,STEEL,SRC}` 也用 `OPTION`，**不构成**独立佐证）。
- **可直接问（一句是非问答，无需给样例）**：
  > 本 build 的 `POST /OPE/LCOM-GEN` 的请求体里，选择操作的那个键是叫 **`OPTION`** 吗？
- **答复分支与恢复条件**：
  - **是** ⇒ 形状分歧排除，剩下唯一可能是本 build **未实现**该端点 ⇒ 登记为
    **产品缺陷 / 不支持**（与 `R154` 的 `BD-ANAL` 同档），**不再当「待澄清」**。
  - **否** ⇒ 给出正确键名 ⇒ 我方 Schema 登记**勘误**。
  - 恢复条件：产品侧答「是」或「否」**任一**（本问已收窄到一次是非问答）。

---

## 问题 ⑤ —— `DESIGN.RC.REBC` / `REBR`（键名/形状疑点，`P186-B` + `P188` 真机归因，**合并一问**）

> ⚠️ 本条由 **P186-B 真机排查**新增（`docs/reports/P186B_REBC400归因排查_v1.0.md`）。
> **P188** 已证实 `REBR` 与 `REBC` **同族同因**（同 `Assign → 截面号 → ITEMS[]`；`PUT REBR` 在前置单元已存在时同样回 `400 Wrong Field`、读回 `{}`）
> ⇒ **REBC 与 REBR 合并为同一问**，不再单独提第 6 问。证据 = `registry/live/{rebc_prereq_probe_p186,rebr_prereq_probe_p188}.json`。

- **端点 / 字段**：`PUT /DESIGN/RC/KDS-41-20-2022/REBC`（列配筋数据），请求体 `Assign → 截面号 → ITEMS[]`。
- **机械事实**：本 build 对「`Assign` → 截面键 → `ITEMS[]`（含 `MAIN_BAR`/`SHEAR_BAR_END`/`SHEAR_BAR_CEN`/`DO`/`ELEMS`）」的**任何**写法都回
  **`400 {"error":{"message":"Wrong Field"}}`**。
- **已排除（真机）**：
  - ✗ 「**前置对象缺失**（单元/截面）」—— 在 `gen-local` 空项目先建**真实节点 + 单元**（阳性对照 `201` + 读回真值）后再 `PUT REBC`，**仍 `Wrong Field`**；`CREATE_SUB_SECTION=true` 变体同形 ⇒ **与前置对象无关**。
  - ✓ **归因收窄** = 请求体**形状/键名层**（`Wrong Field` 在**同族**上的唯一已知成因是键名错，见 `E-02`：`POST.TEXT` 的 `TABLE_TYPE`→实测契约键 `TEXT_TYPE`）。对照：`POST /db/SECT` 缺尺寸回**中文**「截面尺寸输入有错误」（**取值级**），与 `Wrong Field`（**键名级**）不同类。
  - ⚠️ **无权威示例**：`REBC` 的 `source = repo_midas_api`（GitHub 韩文整理版），Gen NX 手册 `MIDAS_API_Online_Manual_数据_v1.0.json` 里 **`REBC` 出现 0 次** ⇒ 无「正确键名/包装」的可复算来源。
- **判据**：`Wrong Field` + 前置无关 + 无权威示例 ⇒ 只能向产品侧确认请求体契约，**不硬凑**（`R151`）。
- **可直接问（一句）**：
  > 本 build 的 `PUT /DESIGN/RC/KDS-41-20-2022/REBC` 请求体（`Assign` → 截面号 → `ITEMS[]`）**任何**写法都回
  > `400 Wrong Field`（前置单元已就绪亦然）。请问该端点请求体的**正确顶层键名 / 包装**是什么？是否另有必填键
  > （如 `Assign` 之上的包装、或 `ITEMS[]` 内的必需子键）？
- **恢复条件**：
  - 产品侧给出**正确键名/包装** ⇒ 我方 Schema 登记勘误（形如 `TABLE_TYPE`→`TEXT_TYPE` 的键名修正）⇒ 可重测。
  - 若产品侧确认形体无误 ⇒ 本 build **未实现**该端点 ⇒ 登记**产品缺陷/不支持**（与 `R154` 的 `BD-ANAL` 同档）。
  - ✅ **`REBR` 同族同因（P188 已确认）**：`PUT /DESIGN/RC/KDS-41-20-2022/REBR` 在**前置单元已存在**时同样回 `400 Wrong Field`、`GET` 读回 `{}` ⇒ **REBC/REBR 合并为同一问**（问法里的端点写「`REBC` 或 `REBR`」即可）。

---

## 汇总给产品侧「一封信」（可直接粘贴）

> 您好，我们对接 MIDAS Open API 时遇到 **4 个需要贵方确认的点**（另有 1 个已自查清楚、无需回复）：
> 1. **`/db/REBR` 的 `HOOP_TYPE`**：接受整数 `1`/`2`、字符串 `"Ties"`/`"Spirals"`，还是两者都接受？
>    （`/info` 声明 integer，但示例 #835 给 `"Spirals"`。）
> 2. **`DESIGN.RC.KDS-41-20-2022.DCRE` 的 `SPLICED_BARS`**：接受字符串 `"None"`/`"50%"`/`"100%"`、
>    整数 `0`/`1`/`2`，还是两者？（落盘枚举是字符串，示例给 `1`。）
> 3. **`POST /OPE/LCOM-GEN` 的请求体**：选择操作的那个键，键名是 **`OPTION`** 吗？
>    （我们对任何取值都收到 `400 Wrong Field`，怀疑键名。）
> 4. **`PUT /DESIGN/RC/KDS-41-20-2022/REBC` 与 `/REBR` 的请求体**（同族）：`Assign → 截面号 → ITEMS[]` 的任何写法都回
>    `400 Wrong Field`（**前置单元已就绪亦然**，REBR 同）。请问正确的**顶层键名/包装**是什么？是否另有必填键？
>
> （第 5 项 `OPE.GSBG::BRDG_GROUP` 我们已确认是模型内 StructureGroup 的引用名、非受控词表，无需回复。）
> 谢谢！

---

## 本批「不做」的（如实记录）

- **不发任何请求**（零请求）；**不改** `registry/` 任何数据；**不改**主指标 / 收益映射 / 归因。
- **不碰** `DESIGN.{RC,SRC}` 的 `*-ANAL`（`R154` 崩溃族）。
- 本页**只汇总**既有 `R164` / `R171` / `R172` 的结论，**不新增**任何裁决。

## 复算命令（零请求，可验证本页与台账一致）

```bash
python registry/tools/check_spec_enums.py --check   # 应显示 4 条「⏳ 留缺」，且与 live/spec_enum_audit.json 一致
```
