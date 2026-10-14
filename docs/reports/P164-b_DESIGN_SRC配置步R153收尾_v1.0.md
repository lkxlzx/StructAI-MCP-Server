# P164-b 报告：`DESIGN.SRC` 的配置步收尾（R153 收口）

> 批次：**P164-b** ｜ 状态：✅ **已验收（代码已落地；真机效果待验）**
> 授权：**用户已授权** —— 范围 = `app/infrastructure/adapters/midas/`
> （`transforms.py` + `operations.py`；`adapter.py` **未改**，见 §3）
> 前置：**P164-a**（同族复核：86 个 composite 步骤逐条审计 ⇒ 真阳性只有这一组）
> 纪律：**铁律 ⓪**（判据 = 效果，不是状态码）· `docs/08` §4 第 4 条（动 `app/**` 先取授权）

---

## 0. 一句话结论

1. ✅ **R153 收口**：`DESIGN.SRC` 的 3 个**配置**步 `_read` → `_write(..., method="PUT")`
   —— 与 **R141**（`DESIGN.STEEL`）/ **R153**（`DESIGN.CONCRETE`）**逐条同形**的那个缺陷，
   设计族**已全部清零**（`DESIGN.{STEEL,CONCRETE,SRC}` 的配置步 **0** 处 `_read`）。
2. ✅ **新增 3 个 SRC 绑定的转换器**（`midas.design.src-{option,frame,member}.v1`）
   —— 字段**逐个**照端点 Schema 取（**不**臆造、**不**复用 STEEL / RC 的表：
   SRC 的 `DCO` 只有 **2** 个字段且 `SEISMIC` 是 **boolean**，与 RC 的 **13** 个字段 / object 完全不同）。
3. ⏳ **真机效果**（铁律 ⓪ 的判据 = `BC-TABLE` 的**结果行数**）**本批未验** ——
   需建**钢-混凝土组合（SRC）**模型才能测；本批无实例。

---

## 1. 改了什么（逐处）

| 文件 | 改动 |
| --- | --- |
| `app/infrastructure/adapters/midas/transforms.py` | +3 个转换器类 · `__all__` +3 · `TRANSFORMER_REGISTRY` +3（**35 → 38**） |
| `app/infrastructure/adapters/midas/operations.py` | `DESIGN.SRC` 的 `DCO`/`DCTL`/`MEMB` 三步：`_read` → `_write(..., method="PUT")` + 各自的 `intent` / 转换器名 |
| `app/infrastructure/adapters/midas/adapter.py` | **未改** —— `_build_payloads` 的 `write_design_{option,frame,member}` 三个载荷入口**已存在**（P160e-b 为 RC 加的），确认可复用 |

**字段表（逐个照端点 Schema，`不`臆造）**：

```text
midas.design.src-option.v1  → DESIGN.SRC.AIK-SRC2K.DCO   (required: DGNCODE, SEISMIC)
    dgn_code   ← DGNCODE   (必填)
    seismic    ← SEISMIC   (必填；SRC 是 **boolean**，RC 是 object)

midas.design.src-frame.v1   → DESIGN.SRC.AIK-SRC2K.DCTL  (required: 无)
    frame_x / frame_y / auto_kf / design_type ← FRAMEX / FRAMEY / bAUTOKF / DT

midas.design.src-member.v1  → DESIGN.SRC.AIK-SRC2K.MEMB  (required: AELEM)
    elements ← AELEM (必填) · reverse ← bREVERSE
```

**`DESIGN.SRC` 的编排（改后）**：

```text
DESIGN.SRC.AIK-SRC2K.DSRC      _write("design",              method="PUT")   ← 原已修
DESIGN.SRC.AIK-SRC2K.DCO       _write("write_design_option", midas.design.src-option.v1, method="PUT")  ← 本批
DESIGN.SRC.AIK-SRC2K.DCTL      _write("write_design_frame",  midas.design.src-frame.v1,  method="PUT")  ← 本批
DESIGN.SRC.AIK-SRC2K.MEMB      _write("write_design_member", midas.design.src-member.v1, method="PUT")  ← 本批
DESIGN.SRC.AIK-SRC2K.BC-ANAL   _write("design")            ← 不变
DESIGN.SRC.AIK-SRC2K.BC-TABLE  _write("design_result")     ← 不变
```

---

## 2. 复算证据（改动前后）

| 项 | 改前 | 改后 |
| --- | ---: | ---: |
| `TRANSFORMER_REGISTRY` 条数 | 35 | **38** |
| **同族复核：设计族配置步的 `_read` 处数** | **3**（`DESIGN.SRC`） | **0** |
| 同族复核：全部 86 个 composite 步骤的可疑数 | 25 | **22**（余下 22 全部是可解释的误报，见 P164-a §2.1） |
| R126 证据包 `with_transformer` | 15 | **16** |
| R126 证据包 `without_transformer` | 56 | **55** |
| R126 证据包 `no_canonical_model` | 56 | **55** |
| R126 证据包 `covered` | 10 | **11** |
| R126 证据包 `field_set_gap` | 3 | **3（不变）** |
| 映射缺口（`GEN_NX`） | 489 = 243 + 246 | **489（不变）** |

**⚠️ 判据边界（P164-a §2.1 已记录）**：同族复核的 `READ-ON-CONFIG` **只是可疑信号** ——
`MODEL.*.QUERY` 的 11 处是**查询**（本就该 GET）、`ANALYSIS.*` 的 11 处是**前置检查**
（`_analyze(_read(...))`，`note` 逐条写明「前置」）。**只有** `DESIGN.*` 的前几步是真配置。

---

## 3. 本批**未**做的事（诚实边界）

1. **未在真机上验证效果**（**铁律 ⓪**）：判据是 `BC-TABLE` 的**结果行数**，需建 **SRC** 模型；
   本批无实例 ⇒ **不**声称 `DESIGN.SRC` 已可用，只声称**编排已不再是"配置从不写入"**。
2. **未改 `adapter.py`**：`_build_payloads` 的三个入口已存在且**按 intent 取值**（与端点无关）
   ⇒ 确认无需改动（**不**做无谓改动）。
3. **未改 `registry/**`**：3 个 SRC 端点 `availability: verified`、Schema 齐备 ⇒ **不是**数据侧问题。
4. **未扩大授权范围**：只在 `midas/` 适配层内改，**未**触碰 9 Tool Contract / 领域层 / 表结构。

---

## 4. 闸门

```text
pytest -q                      1308 passed / 11 skipped / 0 failed
ruff check app tests           All checks passed!
ruff format --check app tests  251 files already formatted
mypy app                       Success: no issues found in 185 source files
python -m app.main             退出码 0 · stdout **0** 字节
红线：厂商名（豁免子包之外）     0 处
registry 全部 --check           全绿（probe_interface_paths / check_canonical_field_gap /
                               classify_mapping_gap / sync_manifest 差异 0 / …）
```

**新增可执行判定** = `tests/test_midas_design_src_p164b.py`（**7** 项）：
3 步是 PUT 写 · 端点集不变 · 3 个转换器注册且绑定 · **字段表逐个等于端点 Schema** ·
`required` 标志照 Schema · **设计族配置步 0 处 `_read`（族不变量）** · 两个无 API 的 Operation 无步骤。

**同步的钉住计数**（只改数字，断言**未**放宽）：
`test_midas_write_coverage_p142.py`（35 → 38）·
`test_midas_interface_read_p153.py` / `test_midas_constraint_rw_p157.py` /
`test_midas_interface_contract_p154.py`（`with_transformer` 15 → 16 等 4 项）。
