# MIDAS API DESIGN 命名空间 中文名审查报告 v1.0

> 审查对象：`MIDAS_API_DESIGN中文名对照_v1.0.csv` 中的 125 条中文名（DESIGN/STEEL 28 · DESIGN/RC 70 · DESIGN/SRC 27）
> 审查日期：2026-10-04 ｜ 性质：**非官方译名**（源手册为韩文，仅有英文原名）

---

## 1. 审查方法

| 步骤 | 内容 | 结论 |
| --- | --- | --- |
| ① 查官方中文源 | 在 StructAI 语料（主开发文档 / 补充文档 / GEN、CIVIL 实测补充）与《midas Civil NX - API 用户手册》中检索这些设计术语 | **均无中文**。DESIGN 端点只存在于 GEN/设计规范侧，Civil 手册中连端点都不存在（仅 `MATD` 有英文页），因此**只能自译** |
| ② 对照中国现行规范 | GB 50017（钢结构）· GB 50010（混凝土）· GB 50011（抗震）· GB 50009（荷载）· JGJ 138（型钢混凝土） | 125 条中 **96 条**直接对应规范术语，另 2 条为规范体系写法（RC / P-M） |
| ③ 内部一致性 | 同一英文名是否对应唯一中文名；同一中文名是否被多个英文名复用 | **通过**（无冲突） |
| ④ 格式一致性 | 全角括号、`RC ` / `SRC ` 后空格、`（执行）/ 表 / 报告` 三段式 | **通过** |

---

## 2. 发现并修正的问题（5 处 / 2 个术语）

| # | 英文原名 | 原译 | 修正为 | 依据 |
| --- | --- | --- | --- | --- |
| 1 | Equivalent Moment Correction Factor | 等效弯矩修正系数（Cm） | **等效弯矩系数（Cm）** | GB 50017 压弯构件术语即为「等效弯矩系数 βmx/βmy」，AISC 的 Cm 亦对应此名。原译「修正系数」属字面直译，中国工程师不熟悉 |
| 2 | Underground Load Combination Type | 地下荷载组合类型 | **地下结构荷载组合类型** | GB 50011 的表述是「地下结构」，补全后语义完整 |

影响范围：`DESIGN/STEEL/.../CMFT`、`DESIGN/RC/.../CMFT`、`DESIGN/SRC/.../CMFT`、`DESIGN/STEEL/.../ULCT`、`DESIGN/RC/.../ULCT`，共 **5 个端点**。已同步到 Registry 与开发文档（旧译名残留 **0** 处）。

---

## 3. 术语依据分布

| 依据 | 条数 |
| --- | --- |
| GB 50010（混凝土）术语 | 42 |
| GB 50017（钢结构）术语 | 27 |
| JGJ 138（型钢混凝土）术语 | 12 |
| GB 50011（抗震）术语 | 9 |
| GB 50009（荷载）术语 | 6 |
| 其他规范/标准写法（AISC Cb / ACI 环境类别 / P-M / RC 体系） | 6 |
| MIDAS 功能名直译（无对应规范术语） | 23 |

> 全部 125 条均在 CSV 的 `terminology_basis(术语依据)` 列给出逐条依据，**无「未标注依据」条目**。

---

## 4. 需你确认的 5 处判断性译法

这些词在规范中有多种说法，我选了工程界最常用的一种，但都可以改：

| # | 英文原名 | 我的译名 | 备选 | 说明 |
| --- | --- | --- | --- | --- |
| 1 | Bending Coefficient (Cb) | 弯曲系数（Cb） | 弯矩系数（Cb） | GB 50017 中 Cb 未单列中文名；若用「弯矩系数」会与 Cm 的「等效弯矩系数」过于接近，故选「弯曲系数」以区分 |
| 2 | Serviceability Parameters | 适用性参数 | 正常使用极限状态参数 | 前者贴近英文，后者贴近 GB 50010 表述；当前偏直译 |
| 3 | Member Assignment | 设计构件指定 | 构件指定 / 设计构件分配 | MIDAS 中该功能是「把哪些构件纳入设计」，「指定」比「分配」更贴切 |
| 4 | Rebar Exposure Condition | 钢筋暴露条件 | 钢筋环境类别 | GB 50010 用「环境类别」，但英文强调的是 exposure condition（暴露条件），当前偏直译 |
| 5 | Design Criteria for Rebars | 钢筋设计准则 | 钢筋构造规定 | GB 50010 把这类条文叫「构造规定」；英文 Criteria=准则，当前偏直译 |

**如果你要改**：告诉我编号与目标译名，我改词典后一键重跑（Registry + 文档 + CSV 三处同步更新）。

---

## 5. 已核对无误的关键译法（易错点）

| 英文原名 | 译名 | 为什么容易译错 |
| --- | --- | --- |
| Boundary Element Method by Wall ID | 按墙体 ID 的**边缘构件**法 | 「Boundary Element」在剪力墙设计中指**边缘构件**，**不是**数值方法的「边界元法」 |
| Effective Length Factor (K) | **计算长度系数**（K） | 不是「有效长度系数」；GB 50017 用「计算长度系数」 |
| Moment Magnifier | **弯矩放大系数** | 不是「弯矩增大系数」；二阶效应术语 |
| Haunched Beam | **加腋梁** | 不是「牛腿梁」「变高梁」 |
| Limiting Slenderness Ratio | **长细比限值** | GB 用「容许长细比」，此处按 Limiting 译为限值 |
| Live Load Reduction Factor | **活荷载**折减系数 | 用「活荷载」而非「活载」（与语料一致） |
| Checking / Check | **校核** | 与 StructAI 语料的「校核」「超限」「利用率」体系一致 |
| Perform / Table / Report | **（执行）/ 表 / 报告** | 三段式统一，与 RC/SRC 各 12 组命名保持一致 |

---

## 6. 一致性检查结果

```text
一个英文名 -> 多个中文名：无 ✅
一个中文名 -> 多个英文名：无 ✅
（其中 3 组「同概念不同符号」按源手册区分：
   Unbraced Length / Unbraced Length (L, Lb)
   Effective Length Factor / Effective Length Factor (K)
   Moment Magnifier / Moment Magnifier(B1/Δb, B2/Δs)）
```

---

## 7. 产物同步情况

| 产物 | 状态 |
| --- | --- |
| `MIDAS_API_DESIGN中文名对照_v1.0.csv` | 125 行，新增 `terminology_basis(术语依据)` 列 |
| `registry/design/**/*.yaml` | 125 个定义带 `title_zh` + `title_zh_official: false` |
| `registry/manifest.json` | 每条含 `title_zh` / `title_zh_official` |
| `registry/README.md` | 字段字典已说明非官方译名与对照表位置 |
| `MIDAS_API_开发文档_v1.0.md` 第 8 章 | 总表与明细均为中文名，逐条标注「（非官方译名）」 |
| Registry 全量校验 | ✅ 全部通过（634 定义 / 570 schema / manifest 一致） |

---

## 8. 结论

1. DESIGN 命名空间的术语**在现有全部语料中没有官方中文**，自译是唯一可行路径——本报告已把这一事实与逐条依据固化，避免后续被误认为官方名称。
2. 125 条译名中 **96 条直接对齐中国现行规范术语**（GB 50010 42 · GB 50017 27 · JGJ 138 12 · GB 50011 9 · GB 50009 6），另 6 条采用其他规范/标准写法，**23 条为 MIDAS 功能名直译**（无对应规范术语）。
3. 审查修正了 2 个术语（5 个端点），并消除了 1 处潜在的 Cm/Cb 混淆。
4. 仍有 5 处属**判断性译法**（第 4 节），需你确认或改词。
