# P160e-a 报告：剩余 17 个端点的**收益映射** + `POST.TABLE` 留缺（R151）

> 批次：**P160e-a**（P160e 的第一子批）｜ 状态：✅ **已验收**（**未**新增收口；产出**收益映射** + **R151** 留缺）
> 授权范围：**无** `app/**` 改动（只做只读诊断 + 真机有界实测）
> 前置：P160d（`VIEW.*` 参数通道 R148）· **铁律 ⓪**

---

## 0. 一句话结论

1. 📌 **收益映射算准**（并**更正** P160d 行的口径）：剩余端点挡住 **10** 个 Operation（**不**是 11）。
2. ⚠️ **`POST.TABLE` 留缺（R151）**：`RESULT.ANALYSIS.SUMMARY` **零请求** —— 被**核心自己的
   `spec_guard`**（P157 / R140 加的枚举预检）拦住：`value_not_in_spec_enum`（`endpoint=POST.TABLE`）。
3. 📌 **`DESIGN.RC.*` / `DESIGN.SRC.*` 需要"混凝土 / SRC 模型"** ⇒ 必须先建**对应类型**的模型，
   **不**能在钢结构模型上测 ⇒ 拆成 P160e-b / P160e-c。
4. ✅ **链本身再次全绿**（12 步全部 `200`，零残留）—— 本批的实测**没有**扰动既有能力。

---

## 1. 收益映射（**逐端点 → 挡住哪些 Operation**）

```text
被挡 Operation = 10 / 71

DESIGN.RC.KDS-41-20-2022.BD-ANAL   → DESIGN.CODE_CHECK · DESIGN.CONCRETE
DESIGN.RC.KDS-41-20-2022.BD-TABLE  → DESIGN.CODE_CHECK · DESIGN.CONCRETE
DESIGN.RC.KDS-41-20-2022.BR D-*    → DESIGN.CODE_CHECK          （BRD / CD / WD × ANAL/TABLE）
DESIGN.SRC.AIK-SRC2K.BC-ANAL       → DESIGN.CODE_CHECK · DESIGN.SRC
DESIGN.SRC.AIK-SRC2K.BC-TABLE      → DESIGN.CODE_CHECK · DESIGN.SRC
DESIGN.SRC.AIK-SRC2K.CC-*          → DESIGN.CODE_CHECK          （CC × ANAL/TABLE）
POST.STEELCODECHECK                → DESIGN.CODE_CHECK
POST.TABLE                         → RESULT.ANALYSIS.SUMMARY
VIEW.RESULTGRAPHIC                  → VIEW.DEFORMED_MODEL · DISPLACEMENT · FORCE · MODE_SHAPE · REACTION · STRESS
```

**分组收益**：

| 组 | 解锁 | 备注 |
| --- | --- | --- |
| `POST.TABLE` | **1**（`RESULT.ANALYSIS.SUMMARY`） | **出计算书**的通用取表入口 ⇒ 价值最高；本批被 `spec_guard` 挡住（R151） |
| `POST.STEELCODECHECK` | **0**（单独收口**不**解锁） | `DESIGN.CODE_CHECK` 还需要 12 个 RC/SRC 端点 |
| `DESIGN.RC.*`（8） | **2**（`DESIGN.CONCRETE` · `DESIGN.CODE_CHECK`） | 需**混凝土**模型 |
| `DESIGN.SRC.*`（4） | **2**（`DESIGN.SRC` · `DESIGN.CODE_CHECK`） | 需 **SRC** 模型 |
| `VIEW.RESULTGRAPHIC` | **6** | R150 留缺（需分析结果 / 正确取值） |

⚠️ **口径更正**：P160d 报告与 `docs/08` §4 里写的"被挡 11 个"应为 **10** —— 本批据实复算。

---

## 2. R151：`POST.TABLE` 被 `spec_guard` 拦住（**留缺**）

### 2.1 实测

```text
（先跑链到分析为止：单元 0–9 全部 200；再调 RESULT.ANALYSIS.SUMMARY）

--- native 键  {"TABLE_TYPE": "DISPLACEMENTG", "PRI_SORT": 1, "RESULT": 0} ---
   requests = []                       ← **零请求**
   error    = {"code": "STRUCTAI-1200", "native_reason": "value_not_in_spec_enum",
               "native_endpoint": "POST.TABLE"}
--- canonical 键 {"table_type": "DISPLACEMENTG", ...} ---  同上（**零请求**）
--- 空 {} ---                                              同上（**零请求**）
```

### 2.2 判定

* **拦在核心**（不是原生）：`native_stage = "midas_adapter"` ⇒ 是 **P157 / R140 加的 `spec_guard`**
  （说明书枚举预检）在**发请求之前**判的 ✓ —— 该守卫的初衷正是**防弹窗 / 防崩溃**（R140 的事故）✓
  ⇒ 它**按设计**工作 ✓；
* **成因**：`POST.TABLE` 的 Schema 里 **`TABLE_TYPE` 的枚举不含 `"DISPLACEMENTG"`**。
  该 Schema 来自 help center 的**通用** `post/TABLE`（**22** 个示例、多种 `Argument` 变体）
  ⇒ 枚举**可能不完整** ✗；
* ⚠️ **不**据此放宽 `spec_guard`（放宽会**丢掉** R140 的保护）⇒ **留缺**，登记**恢复条件**：
  **产品 / 数据侧裁决** —— ① 枚举不全 ⇒ 补枚举（数据侧）；② 取值确实非法 ⇒ 用合法 `TABLE_TYPE`。

### 2.3 影响

* `RESULT.ANALYSIS.SUMMARY` **仍不可用**（生产路径）⇒ `availability` **不**升级；
* 但 **`RESULT.*` 的具体表**（`RESULT.NODE.DISPLACEMENT` 等走 `POST.TABLE.DISPLACEMENTG`）**已 verified**
  ⇒ **"出计算书"不缺这一条**（通用入口缺，具体表在）✓。

---

## 3. 本批实测（真机，**带效果判据**）

```text
链（12 步）逐条状态码：
  [ 0] MODEL.UNIT.ASSIGN           [200]        [ 6] MODEL.BOUNDARY.ASSIGN    [200]
  [ 1] MODEL.MATERIAL.ASSIGN       [200]        [ 7] MODEL.LOAD.ASSIGN        [200, 200]
  [ 2] MODEL.SECTION.ASSIGN        [200]        [ 8] MODEL.LOAD_COMBINATION…  [200]
  [ 3] MODEL.NODE.CREATE           [200]        [ 9] ANALYSIS.STATIC          [200 ×4]
  [ 4] MODEL.NODE.CREATE           [200]        [10] RESULT.NODE.DISPLACEMENT [200]
  [ 5] MODEL.ELEMENT.CREATE        [200]        [11] DESIGN.STEEL             [200 ×6]
收尾：链的 `_cleanup` 逐条 gone=True（零残留）
```

⚠️ **我自己的脚本 bug（如实记录）**：`_substitute_steps()` **本来就含尾段** ⇒ 我又 `+ _tail_steps(...)`
⇒ 尾段**跑了两遍**（第二遍 `MODEL.LOAD.ASSIGN` / `MODEL.LOAD_COMBINATION.ASSIGN` 因重复而 `400`）。
**不影响**首次那遍的全绿结论，但**是我该避免的**。

---

## 4. 闸门

```text
pytest -q                    1252 passed / 11 skipped / 0 failed（本批**无**代码改动）
ruff check app tests         All checks passed!
ruff format --check app tests 247 files already formatted
mypy app                     Success: no issues found in 185 source files
实例状态                     零残留
```

---

## 5. 下一步（P160e 的其余子批）

| 子批 | 内容 | 前置 |
| --- | --- | --- |
| **P160e-b** | `DESIGN.RC.*`（8 端点 ⇒ `DESIGN.CONCRETE` + `DESIGN.CODE_CHECK`） | 先建**混凝土**模型（混凝土材质 + 混凝土截面 + 配筋） |
| **P160e-c** | `DESIGN.SRC.*`（4 端点 ⇒ `DESIGN.SRC` + `DESIGN.CODE_CHECK`） | 先建 **SRC** 模型 |
| **P160e-d** | `POST.STEELCODECHECK`（单独**不**解锁，但为 `DESIGN.CODE_CHECK` 的**组成部分**） | 现有钢模型 |
| **R151 裁决** | `POST.TABLE` 的 `TABLE_TYPE` 枚举是否不全 | **产品 / 数据侧裁决** |

---

## 6. 本批的教训

1. **先算"收益映射"再动手**：这一算就把"哪一组值得先做"看清了 ——
   `POST.TABLE` 只挡 **1** 个但那是**计算书入口**；`DESIGN.CODE_CHECK` 被 **13** 个端点挡 ⇒ 是**大目标**。
2. **`spec_guard` 会"正确地"挡住合法调用**：它的枚举来自 help center 的**通用** schema，
   对**多形态**端点（`POST.TABLE` 有 22 个示例 / 多种 `Argument` 变体）**可能不完整** ✗
   ⇒ 这类**留缺**必须登记"是枚举不全还是取值非法"，**不**自行放宽。
3. **我的脚本 bug 也要记**：`_substitute_steps()` 含尾段 ⇒ 我重复拼接导致尾段跑两遍。
   ⇒ **复用探针参数前先读它的语义**（这正是"不臆造"的一部分）。
