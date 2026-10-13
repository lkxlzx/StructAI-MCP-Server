# P160d 报告：`VIEW.*` 参数通道修复（R148）+ `VIEW.CAPTURE` / `VIEW.DISPLAY` 收口

> 批次：**P160d** ｜ 状态：✅ **已验收**（含 **R148** 编排修复、两条**手册示例不适用**的实测取值、1 个端点**留缺**）
> 授权范围：`app/**` = **3** 个文件（`operations.py` / `adapter.py` / `transforms.py`）+ **数据侧** 3 个 YAML
> 前置：P160c（DOC 生命周期 4 个端点收口）· **铁律 ⓪**（判据必须是效果，不是状态码）

---

## 0. 一句话结论

1. ⚠️ **发现并修复 R148**：`VIEW.*` 的 7 个 Operation 原先**全部不可用** —— 两三个步骤**形状不同**
   却共用一份 `parameters["arguments"]` ⇒ 传并集被转换器白名单**拒**、传子集 `VIEW.DISPLAY` **`400`**。
   按 **R141 的先例**拆成**各自的参数通道**（`display` / `result_graphic` / `capture`）。
2. ✅ **收口 2 个端点**（**带效果判据**）：`VIEW.CAPTURE`（**jpg 真的落盘**）· `VIEW.DISPLAY`
   （改前/改后**两张截图字节不同** ⇒ 设置**真的生效**）。
3. ⚠️ **1 个端点留缺**：`VIEW.RESULTGRAPHIC` → `400`「second query is wrong」（**不**升级 `availability`）。
4. 📌 **两条实测取值（手册示例不适用）**：`SET_MODE` 的 `"post"` **不可用**；`FIGURE_NAME` **只能**引用已存在的图形名。

---

## 1. R148：`VIEW.*` 的参数通道（用户授权）

### 1.1 缺陷（两次实测都证实）

| 步 | 体 | 转换器 |
| --- | --- | --- |
| `VIEW.DISPLAY` | **原生键**（`{"ELEMENT": {"ELEM_NUMBER": true}}`） | **无** |
| `VIEW.RESULTGRAPHIC` | **原生键**（`CURRENT_MODE` / `LOAD_CASE_COMB` …） | **无** |
| `VIEW.CAPTURE` | **canonical 键**（`export_path` …） | **有**（白名单） |

```text
传并集 ⇒ VIEW.CAPTURE 的转换器白名单**拒**：transformer_field_not_in_schema
传子集 ⇒ VIEW.DISPLAY **400**（缺合法显示体）⇒ 编排停在第一步
⇒ **无解** ⇒ 7 个 VIEW.* Operation **全部不可用**
```

### 1.2 修复（按 R141 的先例）

```text
operations.py   VIEW.DISPLAY → intent="view_display"
                VIEW.RESULTGRAPHIC → intent="view_result"
                VIEW.CAPTURE → intent="view_capture"（**该步有**白名单转换器）
adapter.py      VIEW_ARGUMENT_CHANNELS = {view_display: "display",
                                          view_result:  "result_graphic",
                                          view_capture: "capture"}
```

⇒ 每一步走**自己的**参数通道 ⇒ 形状不再冲突 ✓（实测：两步各发各的体 ✓）。

### 1.3 顺带补齐的转换器字段

`ViewTransformer` 原先只有 6 个字段 ⇒ 按手册示例补 `SET_MODE` / `SET_HIDDEN` / `STAGE_NAME` /
`DISPLAY` / `RESULT_GRAPHIC`（手册示例的 `VIEW.CAPTURE` 体**自带显示设置**）。

---

## 2. 两条**手册示例不适用**的实测取值

### 2.1 `SET_MODE`：手册示例的 `"post"` **不可用**

```text
SET_MODE="post"   → 400 {"error":{"message":"MIDAS GEN NX It's failed, Post Mode is not available"}}
SET_MODE="pre"    → 200 ✓ 文件 12 400 字节
SET_MODE="PRE"    → 200 ✓ 文件 12 400 字节
SET_MODE 省略      → 200 ✓ 文件 12 400 字节
SET_MODE="model"  → 400 {"error":{"message":"MIDAS GEN NX second query is wrong"}}
```

⇒ **"Post Mode" 需要分析结果** ⇒ 手册示例的取值在**无结果**的项目上**必然失败**（R140/R141 同族）。

### 2.2 `FIGURE_NAME`：**只能**引用**已存在**的图形名

```text
FIGURE_NAME="P160D"（任意标签） → 400 {"error":{"message":"MIDAS GEN NX It's not found Figure Name"}}
FIGURE_NAME 省略                → 200 ✓
```

---

## 3. 实测（真机，**全部带效果判据** —— 铁律 ⓪）

```text
建最小模型：材质 → 截面 → 节点 1 → 节点 2 → 单元 1（复用链的**已实测**参数）

① VIEW.MODEL（ELEM_NUMBER=true） : VIEW.DISPLAY 200 + VIEW.CAPTURE 200 → **12 400 字节**
② VIEW.MODEL（ELEM_NUMBER=false）: VIEW.DISPLAY 200 + VIEW.CAPTURE 200 → **12 142 字节**
   ⇒ ✅ 两张图**字节不同** ⇒ `VIEW.DISPLAY` **真的生效**（不只看状态码）
   ⇒ ✅ 两张图**都落盘** ⇒ `VIEW.CAPTURE` **真的生效**
③ VIEW.DISPLACEMENT（RESULTGRAPHIC + CAPTURE）→ VIEW.RESULTGRAPHIC **400**（留缺）
收尾：链的 `_cleanup` 逐条确认 gone=True（零残留）
```

---

## 4. 收口与留缺

| 端点 | 处置 | 依据 |
| --- | --- | --- |
| `VIEW.CAPTURE` | ✅ `verified`（`gen-local`） | jpg **真的落盘**（12 400 / 12 142 字节） |
| `VIEW.DISPLAY` | ✅ `verified`（`gen-local`） | 改设置后**两张截图字节不同** ⇒ 设置**真的生效** |
| `VIEW.RESULTGRAPHIC` | ⚠️ **留缺**（`untested` 不动） | `400`「second query is wrong」；**成因未定**（缺分析结果？取值不符？）⇒ YAML 内写明恢复条件 |

---

## 5. 连锁同步（**事实变更**，**不**是放宽断言）

| 指标 | 前 → 后 |
| --- | --- |
| `availability: verified` | **501 → 503** |
| `availability: untested` | **112 → 110** |
| 「`untested` 且**无** `GET`」 | **111 → 109**（合计 147 → **145**） |
| 派生证据 | `probe_interface_paths --recon` / `classify_mapping_gap --recon` / `check_canonical_field_gap --recon` 全部重算（`VIEW.DISPLAY` 进契约映射 + 意图改名） |

⚠️ 过程中我**误把 `ruff format` 跑到了 `registry/`**（那里不在闸门内）⇒ **20 个文件被误格式化** ⇒
**已全部还原**（`git checkout --`），只保留本次该改的 3 个文件。

---

## 6. 闸门（原始输出）

```text
pytest -q                    1252 passed / 11 skipped / 0 failed（P160c 基线 1249 ⇒ +3）
ruff check app tests         All checks passed!
ruff format --check app tests 247 files already formatted
mypy app                     Success: no issues found in 185 source files
实例状态                     零残留（链的 cleanup 逐条 gone=True）
```

---

## 7. 新增测试

`tests/test_midas_view_channels_p160d.py`（**3** 项）：
① 三步各有通道且**不**共用 `arguments`；② 7 个 `VIEW.*` 的步**只用**这三个意图（转换器归属正确）；
③ `ViewTransformer` 覆盖手册示例的**全部**字段。

---

## 8. 仍未闭环（交给下一批）

| 项 | 内容 | 需要什么 |
| --- | --- | --- |
| **`VIEW.RESULTGRAPHIC`** | `400`「second query is wrong」⇒ 成因未定 | 在**有分析结果**的项目上重测（先跑链的分析）+ 确认 `CURRENT_MODE` 取值 |
| **`DESIGN.RC.*` / `DESIGN.SRC.*`（12）+ `POST.STEELCODECHECK` + `POST.TABLE`** | 未实测 | P160e |
| **D5 / R126 剩余** | 扩面决策 | 产品裁决 |

---

## 9. 本批的教训

1. **"编排接上了" ≠ "能跑"**：7 个 `VIEW.*` Operation 在编排表里**一直都在**，但**形状接不上**
   ⇒ 一跑就 400 / 一传就白名单拒。**编排的"形状"必须与每步的体形状逐一对齐**（R132 / R148 同族）。
2. **手册示例是"起点"不是"真值"**：`SET_MODE: "post"` 与 `FIGURE_NAME` 两条都是**照抄必败**
   （R140 / R141 / R146 同族）⇒ 实测取值必须**记录在端点 YAML 里**，供后续复用。
3. **铁律 ⓪ 再次救场**：`VIEW.CAPTURE` 若只看状态码，前三次 `400` 会被我当成"编排问题"；
   而**"文件到底落没落盘"**一眼就把范围锁死（12 400 字节 vs 不存在）。
4. **我自己的操作也要守纪律**：`ruff format` 跑错目录（`registry/`）⇒ 20 个文件被误改 ⇒ 已还原。
   **闸门是 `ruff check app tests`，`registry/` 不在其中。**
