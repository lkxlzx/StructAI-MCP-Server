# P164-a 报告：composite 步骤编排的**同族复核**（R153 的收尾）

> 批次：**P164-a** ｜ 状态：✅ **已验收**（只读复核；修法由 **P164-b** 落地）
> 前置：P160e-b（R153：`DESIGN.CONCRETE` 前 4 步 `GET` → `PUT` + 4 个 RC 绑定转换器）
> 触发：P160e-b 报告 §2④ 明写「`DESIGN.SRC` 同形部分（`DCO`/`DCTL`/`MEMB` 仍是 `_read`）**一并**修」，
> 但该批的提交**只**动了 RC ⇒ **登记一项，收尾一项**。
> 方法：**只读**，机械审计 `operations.py` 的**全部 86 个 composite 步骤**。
> ➡️ **修法已由 P164-b 落地**（用户授权）：见 `P164-b_DESIGN_SRC配置步R153收尾_v1.0.md`。

---

## 0. 一句话结论

1. ✅ **同族已查完**（P160e-b 报告 §4 教训 2 要求的那件事）：**86 个步骤逐条审计**，
   与端点原生 `methods` 对照 ⇒ **真阳性 1 组（3 步）**，其余 22 处**全部**是可解释的误报。
2. ⚠️ **唯一的真阳性 = `DESIGN.SRC`**：第 1 步（`DSRC`）已修成 `PUT`，但
   **`DCO` / `DCTL` / `MEMB` 仍是 `_read`** ⇒ 与 **R141 / R153 逐条同形** ——
   设计选项 / 控制 / 构件**从未被配置** ⇒ `BC-ANAL` 必然失败。
3. ✅ **`DESIGN.FOUNDATION` / `DESIGN.OPTIMIZE` 不是同形**（P160e-b 报告把它们列为「待复核，可能同形」）：
   两者 **`steps` 为空**（MIDAS 无任何 API，自研引擎）⇒ **不适用**。
4. ⏳ **修 `DESIGN.SRC` 需动 `app/**`**（3 个新转换器 + 载荷入口 + 输入 Schema + 步骤改 `PUT`）
   ⇒ **按纪律须先取授权**（`docs/08` §4 第 4 条）。本批**不**动。

---

## 1. 判据（可复算）

对**每个** `composite=True` 的 `OperationPlan`，取 `steps=_steps(...)` 的每一步，
解析出 `(kind, endpoint, method)`，与 `registry/manifest.json` 里该端点的 `methods` 对照：

| 判据 | 含义 |
| --- | --- |
| **`READ-ON-CONFIG`** | 步骤是 `_read`（GET）而端点原生**支持 `PUT`/`POST`** ⇒ **可疑** |
| `METHOD-MISMATCH` | 步骤声明的 `method` 不在端点的原生 `methods` 里 ⇒ 可疑 |

脚本 = `docs/nxsdk_review/scripts/p92_composite_audit.py`（**只读**，产出
`.tmp_analysis/composite_step_audit.json`）。

**⚠️ 判据的已知边界**：`READ-ON-CONFIG` **只是可疑信号，不是缺陷判决** ——
「查询」与「前置检查」两类操作**本来就该** `_read`。故必须**逐条看语义**（见 §2）。

---

## 2. 结果：25 处命中 → 逐条甄别

### 2.1 ✅ 误报（22 处，语义正确，**不动**）

| 组 | 处数 | 形态 | 为什么正确 |
| --- | ---: | --- | --- |
| `MODEL.*.QUERY`（7 个 Operation） | 11 | `_read("DB.NODE")` 等 | **查询**操作就该 GET；端点的 `PUT` 是「另有一个写操作」，与查询无关 |
| `ANALYSIS.*`（7 个 Operation） | 11 | `_analyze(_read("DB.STLD"), _read("DB.BMLD"), …)` | 这些是**前置**（`note` 逐条写明，如 `ANALYSIS.STATIC` 的「`DOC.ANAL` + **前置** `DB.STLD`/`DB.BMLD`/`DB.CONS`」）—— 分析前确认模型齐备，**不是**配置 |

**「前置」与「配置」的区分是本判据的关键**：
`_analyze(...)` 包裹的 `_read` = 前置；直接作为 `DESIGN.*` 前几步的 `_read` = 配置（缺陷）。

### 2.2 ⚠️ 真阳性（1 组 / 3 步）：`DESIGN.SRC`

```
DESIGN.SRC（operations.py，composite=True）：
  _write("DESIGN.SRC.AIK-SRC2K.DSRC", "design", None, method="PUT")   ✅ 已修（P157/R141 同批）
  _read ("DESIGN.SRC.AIK-SRC2K.DCO")    ← ✗ 原生 methods = DELETE,GET,PUT
  _read ("DESIGN.SRC.AIK-SRC2K.DCTL")   ← ✗ 原生 methods = DELETE,GET,PUT
  _read ("DESIGN.SRC.AIK-SRC2K.MEMB")   ← ✗ 原生 methods = DELETE,GET,POST,PUT
  _write("DESIGN.SRC.AIK-SRC2K.BC-ANAL",  "design", None)
  _write("DESIGN.SRC.AIK-SRC2K.BC-TABLE", "design_result", None)
```

**与已修的 `DESIGN.CONCRETE` / `DESIGN.STEEL` 逐条对照**（结构完全相同，只差 `_read`/`_write`）：

```
DESIGN.CONCRETE（P160e-b 已修）：
  _write("DESIGN.RC.DRC",                  "write_design_code",   "midas.design.rc-code.v1",   method="PUT")
  _write("DESIGN.RC.KDS-41-20-2022.DCO",   "write_design_option", "midas.design.rc-option.v1", method="PUT")
  …
DESIGN.STEEL（R141 已修）：
  _write("DESIGN.STEEL.DSTL",                "write_design_code",   "midas.design.dstl.v1", method="PUT")
  _write("DESIGN.STEEL.KDS-41-30-2022.DCO",  "write_design_option", "midas.design.dco.v1",  method="PUT")
  …
```

⇒ **配置步从不写入 ⇒ 设计规范 / 选项 / 控制 / 构件全是空的 ⇒ `BC-ANAL` 必然失败。**
这与 R141 实测的事故（验算对话框报 `setting unit` + 崩溃）**逐条同形**。

---

## 3. 修法（**下一批照此落地**，需先取授权）

```text
① 新增 3 个 SRC 绑定的转换器（照 RC 的 4 个 / STEEL 的 4 个）
   ⇒ midas.design.src-{option,frame,member}.v1，endpoint 分别指向
      DESIGN.SRC.AIK-SRC2K.{DCO, DCTL, MEMB}
   ⚠️ 字段按**手册 / 规范表**取，**不**臆造（先确认取值出处；SRC 的体手册里可能没有）
   ⚠️ 现有 midas.design.{dco,dctl,memb}.v1 **绑定在 STEEL 端点**上 ⇒ 不能直接复用
② operations.py：DESIGN.SRC 的 3 步 _read → _write(..., method="PUT")
   intent = write_design_{option,frame,member}
③ adapter.py：_build_payloads 的 write_design_* 已存在（P160e-b 为 RC 加过）
   ⇒ 确认能按 intent 取到 SRC 的载荷
④ 输入 Schema：3 个新转换器需各自的 request Schema（照 RC 的做法）
⑤ 闸门：既有 20 码不扩 · 9 Tool Contract 不变 · 容器 7 字段不变 ·
   registry/** 不动（除非发现数据侧缺 Schema）
```

**授权范围（若获准）**：`app/infrastructure/adapters/midas/` 下的
`transforms.py`（+3 转换器）· `operations.py`（3 步改 `PUT`）· `adapter.py`（确认载荷入口）
—— **不**含 `registry/**`（除非发现数据侧确缺 Schema，那属于数据侧、另行登记）。

**复核的同形端点（本批已做）**：`DESIGN.STEEL` ✅ · `DESIGN.CONCRETE` ✅ ·
**`DESIGN.SRC` ⚠️（唯一剩余）** · `DESIGN.FOUNDATION` / `DESIGN.OPTIMIZE` ✅（无步骤，不适用）·
其余 `composite` 全 33 个 Operation 已逐条审计。

---

## 4. 本批**未**做的事（诚实边界）

1. **未改任何代码**：`app/**` 无授权 ⇒ 只做只读审计（符合 `docs/08` §4 第 4 条）。
2. **未在真机上验证 `DESIGN.SRC`**：修完之后需要在**真机**上建**钢-混凝土组合（SRC）**模型才能验效果
   （铁律 ⓪：判据 = `BC-TABLE` 的**结果行数**）。本批无实例。
3. **未动 `DESIGN.SRC` 的 `registry/**`**：数据侧 3 个端点 `availability: verified`、Schema 齐备，
   **不是**数据侧问题。

---

## 5. 闸门

```text
pytest -q                      1301 passed / 11 skipped / 0 failed（本批**无**代码改动）
ruff check app tests           All checks passed!
ruff format --check app tests  250 files already formatted
registry 全部 --check           全绿（本批未动 registry/**）
```
