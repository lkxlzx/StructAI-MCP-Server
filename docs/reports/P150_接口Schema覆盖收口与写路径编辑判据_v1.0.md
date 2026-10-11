# P150 —— 接口 / Schema 定义收口（R117）+ 写路径「编辑（PUT）」判据（R118）v1.0

- 批次：**P150**（主体 `R117` / `R118` / `R119`；`app/**` **一行未改**）
- 实例：`gen-local`（GEN NX，`http://localhost:3030/gen`）· 实测日期 `2026-10-11`
- 证据：`registry/live/introspect_field_diff.json`（**244** 行）· `registry/live/put_edit_probe.json`（**56** 行）
- 工具：`registry/tools/sync_introspect_fields.py` · `registry/tools/probe_put_edits.py`
- 判定：`tests/test_midas_introspect_fields_p150.py`（**10** 项）· `tests/test_midas_put_edits_p150.py`（**9** 项）·
  `tests/test_midas_singleton_tables_p149d.py::test_p150r119_every_gap_carries_a_recovery_condition`（**1** 项）

## 0. 一句话结论

**R117**：把端点定义里**已登记**的**只读**自省来源（`GET /info/db/<CODE>`）对**全部 244** 个端点扫了一遍，
逐端点做**递归**字段集差集 ⇒ 数据侧请求 Schema 确实只转录了手册子集（**24** 个端点有缺口）；
按**先写清楚的裁决**，**21** 个端点**补 Schema**（逐条 **212** 个字段，来源逐条记在证据里），
**3** 个**如实留缺**（不可比 / 自省节点非法 / 父节点手工收紧）；**反向缺口 12 个端点一律未动**。
**R118**：给「编辑（PUT）」补上判据（创建 → 读回 → **PUT 改动过的值** → 读回确认 → 删除 → 读回消失），
在**零前置链的 56** 个端点上实测 ⇒ **37 `PASSED`** · **14 `LEFT_OUT`** · **5 `FAILED`**；
两个侦察问题都有答案：**PUT 的 body 形状与创建同一形状**（`assign_keyed_item`），
**PUT 不要求记录已存在**（upsert）。⚠️ 本批**发现并如实披露**一处**删不掉**的残留（`DESIGN.SRC.AIK-SRC2K.DSRC`）。

## 1. R117：请求方向 Schema 的「覆盖不全」收口

### 1.1 只读侦察（零副作用）

* 来源 = 端点定义里的 `schema_ref.introspect`（`info/db/<CODE>`，`registry/README.md` §4）；
  本 build 的返回形态**199 / 199 一致**：`{"$schema": …, "Argument": {"type": "object", "properties": {…}}}`。
* 扫描**全部 244** 个有 `introspect` 的端点（**13** 块 × 20 + 块间**只读**健康检查 `GET /DB/NODE`，
  全部 `200`；**未**中止）。**只发 `GET`**（源码里没有 `.post(` / `.put(` / `.delete(`）。
* 差集口径：**递归**比对自省的条目字段表与数据侧 `request_schema()` 的条目 Schema；
  一侧声明 `properties`、另一侧是**裸 `object`** 时，逐个子字段路径记入（这正是「白名单可判面」所在）。

| 结果 | 条数 | 说明 |
| --- | --- | --- |
| 可比（`200` ∧ 有条目节点 ∧ 有数据侧 Schema） | **199** | — |
| 本 build **无**该自省路由（`404`） | **45** | **23** `unverified`（R85）· **15** `unavailable_on` 含 `gen-local` · **7** **CIVIL_DESIGNER 独有** |
| 自省独有字段的端点 | **24** | 逐条见证据的 `introspect_only` |
| **反向缺口**（数据侧有、自省没有）的端点 | **12** | 逐条见证据的 `data_only` |

⚠️ **本证据只断言「自省路由在本 build 上 404」，不断言端点不可用**（那是**另一条**路由 `/DB/<CODE>`，
需**另一次**实测）⇒ **不**写任何 `availability` / `unavailable_on`（逐条 `git diff --quiet` 断言 YAML 一行未改）。

### 1.2 裁决 R117（**先写清楚再动手**）

| 取值 | 判据（工具逐条复算） | 条数 |
| --- | --- | --- |
| `add_fields`（**补 Schema**） | 端点 `products` 含探针实例的产品 ∧ 待补节点**整棵子树**是合法 JSON Schema ∧ 父节点未声明 `additionalProperties: false` | **21** |
| `record_left_out`（**如实留缺**） | `product_not_probed` / `invalid_introspect_node` / `strict_schema_conflict` | **3** |
| `no_gap` | 自省与数据侧字段集一致 | **175** |
| `not_comparable` | 非 `200` / 无条目节点 / 无数据侧 Schema | **45** |

**逐条依据（留缺的 3 个）**

| 端点 | 原因 | 依据 |
| --- | --- | --- |
| `DB.KFAC` | `product_not_probed` | 端点 `products = ["CIVIL_DESIGNER"]`，而探针实例是 **GEN NX** ⇒ 自省与端点**不可比** |
| `DB.SSEIS` · `DB.SWIND` | `strict_schema_conflict` + `invalid_introspect_node` | 数据侧条目 Schema **手工收紧**（`additionalProperties: false` + `required`）⇒ 补字段会**放宽**它；且自省把 `INPUTS` 声明成 `type: "multi object"`（**非法** JSON Schema 片段） |

**影响面（逐条，不静默放宽）**

* **21** 个端点共补入 **212** 个字段名（**只**补自省**实际声明**的字段；**不**引入自省没声明的任何字段）。
  来源逐条记在证据里（`introspect: /info/db/<CODE>`）。**只新增名字**：不删、不改名、不覆盖既有声明。
* **白名单内容按本 build 的声明据实扩大**：`check_write_templates` 的判定口径**未变**
  （仍是「body 字段 ⊆ Schema 声明的字段」），但被声明为「合法」的名字多了 **212** 个 —— 这是
  **据实登记**，不是放宽规则；逐条名字见证据，可复算。
* **判定在该处变强**：**3** 个原本是**裸 `object`（⇒ 不可判）**的父节点现在**有 `properties`**
  （`DB.GALD.SUBTYPE` / `DB.GALD.LOAD` / `DB.SECT.SECT_BEFORE.SECT_I.CF_STIFF_ULS`）⇒ 这些位置的
  字段白名单检查由**不判**变成**可判**。
* ⚠️ 本批**没有**因此暴露新的既有缺口：`check_write_templates` 仍 **71 / 71 非空判 · 0 未知字段 ·
  0 不可判 body**（见 §4 闸门原始输出）。若将来暴露，**逐条裁决**、**不**放宽。
* **反向缺口（12 个端点）一律未动**：删除会**削弱**既有判定；`DB.ACTL` 的 `CLATS` vs `ACWC` 是
  **R101** 已在案的手册 / build 命名差异。逐条记在证据里（如 `DB.SPFC` 的 `OPT.LARGEBRIDEGE` vs
  自省 `OPT.LARGEBRIDGE`，疑似手册笔误 ⇒ 只记录、不改）。

### 1.3 落盘（可复算）

* `sync_introspect_fields.py --write`：**21** 个端点 / **212** 个字段；改后 `--check` 退出码 **0**（幂等）。
* **实现修正（如实记录）**：`check_write_templates.request_schema()` 抽出**纯函数**
  `item_schema_of(schema)`（`request_schema()` = 读盘 + 该纯函数）—— 探针必须在**同一次读盘的文档**里
  定位条目节点，否则改动落在另一份副本上、写回时被丢掉（本批实测踩过）。抽出后「条目形状判定点」
  仍**唯一**，两个调用方**不可能**各自演化；R112 的既有判定**未**变（既有用例全绿）。

## 2. R118：写路径「编辑（PUT）」的判据

### 2.1 判据

    只读哨兵（全部目标端点必须空）→
    自建一条记录（**该端点的写入方法** = POST，没有 POST 时用 PUT；**只**用自建编号）→ 读回 →
    **PUT 一个改动过的值**（逐条记 `{path, from, to, why}`）→ 读回确认**改动生效** →
    按路径 key **删除** → 读回确认消失 → **无副作用观察**（对**已删除**的编号再发一次同一 PUT，
    看记录是否**重新出现**）→ 把该观察留下的编号删净 → 只读哨兵（必须空）。

* 改动值的选择是**机械**的：按 body 声明顺序深度优先，取**第一个** `boolean`（翻面）或**第一个**
  无 `enum` / `const` 的 `number` / `integer`（`+1`）⇒ `--check` 可**离线**复算。
* 目标集 = 有数据侧模板 ∧ GEN NX 有 `PUT` ∧ `DELETE` / `GET` / `read_root` ∧ 已启用 ∧ 非破坏性
  = **71**；本批只处理**零前置链**的 **56** 个（前置链与 L5 同一机制，本批不重复实现），
  带前置链的 **15** 个如实记 `prerequisite_chain_out_of_scope`。

### 2.2 实测（分块 ≤ 10 + 块间只读健康检查；**未**中止、**未**崩溃）

| 结论 | 条数 | 说明 |
| --- | --- | --- |
| `PASSED` | **37** | 六步全成立（创建 → 读回 → 编辑 → 读回确认 → 删除 → 读回消失） |
| `LEFT_OUT` | **14** | 请求体里**没有**可机械改动的标量（`no_editable_scalar`）；仍走创建 → 读回 → 删除 |
| `FAILED` | **5** | **4** 个 `put_rejected:400`（`DB.IEHC` / `DB.MLFC` / `DB.SDVI` / `DB.THIK`：**三种形状全被拒**）+ **1** 个 `delete_failed`（`DESIGN.RC.KDS-41-20-2022.DCTL`） |

**侦察问题①（PUT 的 body 形状）**：**37 / 37** `PASSED` 都用 `assign_keyed_item`
（`{"Assign": {"<自建编号>": <条目>}}`）—— **与创建同一形状**。

**侦察问题②（是否要求记录已存在）**：**37 / 37** 的 `requires_existing_record` 都是 **`False`**
—— 记录删除后对同一编号再发同一 `PUT`，记录**重新出现** ⇒ **PUT 是 upsert**。
⚠️ 这与 **R116**（无 `DELETE` 的端点上 `PUT` 会留下**不可删**的记录）**互相印证**。

### 2.3 残留（**如实披露，不声称零残留**）

* **`DELETE` 会「假成功」**：本 build 上 `DELETE` 可以**返回 `200` 并回显被删记录**却**不真正删除**
  ⇒ 判据以「**再读一次、该编号确实不在**」为准（只信状态码会把残留当成零残留 —— 本批实测踩过，
  已把该教训固化进工具 `_gone()`）。
* **`DESIGN.*` 别名路由的 `DELETE` 不生效**（实测 3 个）：`/DESIGN/RC/DRC`、`/DESIGN/RC/KDS-41-20-2022/DCTL`、
  `/DESIGN/STEEL/DSTL` 与 `/DB/DCON`、`/DB/DCTL`、`/DB/DSTL` **同表**，别名路由的 `DELETE` 删不掉
  ⇒ 这 3 处残留**已按同表 `DB.*` 路由**（`DELETE /DB/<CODE>/<自建编号>`）**清理干净**（逐条核对 `GET` 为空）。
* ⚠️ **`/DESIGN/SRC/AIK-SRC2K/DSRC` 的 `1` 号记录无法清除**（本批跑前哨兵为**空** ⇒ 该记录由本批产生）：
  路径 key / 无 key / 带 body 三种 `DELETE` 形式**都返回 `200`** 而记录**仍在**；它**没有** `DB.*` 别名
  ⇒ **只能如实披露**（证据 `residue` + `allowed_residue`；成因需 **MIDAS 侧**排查）。
  `--allow-residue` **只**放行**已披露**的残留 key，其余跑前非空一律**中止**（零写请求）。
* 说明：残留**不**影响本批任何判定 —— `PASSED` 的 37 个端点逐条**删除后读回确认为空**。

### 2.4 分桶（**不**并入三步链）

本桶与 **R107** 的取设置表判据（无 `DELETE` 的单例表）**分开**，也**不**并入 L5 三步链的覆盖率分子
——`live.write_path_coverage()` **仍是 `72 / 633`**（`model_write_ratio` **`72 / 434`**）。
「读得回 / 写得进 / 编辑生效 / 删得掉」是**四个**判定，本批只补「编辑生效」这一个。

## 3. R119：留缺的**恢复条件**（只更新条件，**不**硬试）

`registry/live/singleton_table_probe.json` 的 `gaps` **逐条**配上 `recovery`（**离线**补齐，
`probe_singleton_tables.py --refresh-recovery`：**不发任何请求**、**不改任何结论**）：

| 原因 | 条数 | 恢复条件 |
| --- | --- | --- |
| `empty_singleton_put_creates_undeletable_record` | **7** | **非空**专用项目（`PUT` 才是「改」而不是「建」；空项目上 `PUT` 会留下**不可删**的记录 ⇒ **R116**）；**没有**就如实保持留缺 |
| `no_put_method` | **3** | **MIDAS 侧**提供 `PUT`（或另立判据） |
| `no_manual_entry` | **1** | 上游手册补条目 |

⚠️ **未**在空项目上做任何 `PUT` 尝试（`put_sent` 逐条为 `false`，见 §4 闸门原始输出）。

## 4. 闸门（原始输出）

```text
pytest -q
  1113 passed, 7 skipped in 227.07s        （基线 1093 / 7 / 0 ⇒ 本批 +20，既有 1093 全部保留）

ruff check app tests            → All checks passed!
ruff format --check app tests   → 233 files already formatted
mypy app                        → Success: no issues found in 184 source files

python -m app.main              → 退出码 0；stdout 0 字节；stderr 0 字节
Base.metadata.create_all        → 24 张表；SELECT 1 → 1

数据侧工具（全绿；改动前后逐条差异见 §1.3 / §3）
  sync_introspect_fields --check        → ✅ 与证据一致（199 个端点可比；补 Schema 21 · 留缺 3 · 无缺口 175）
  check_write_templates                 → ✅ 71 个模板 / 115 个 body；来源可复算；0 未知字段；不可判 body = 0
  sync_write_templates --check          → ✅ 模板文件与机械结果一致（71）
  sync_availability --check             → ✅ 与只读证据一致（61 个可用端点已收口）
  sync_endpoint_methods --check         → ✅ 端点 methods 与证据文件一致（无待写回项）
  sync_manual_index --check             → ✅ 产物与机械结果一致
  sync_request_schemas --check          → ✅ 9 个文件与机械结果一致
  fix_schema_defects --check            → ✅ registry/schema/** 文件数 = 625；无残留占位串；无大小写不符的 type
  sync_manifest（预演）                  → manifest 条目数 = 636；字段差异总数 = 0
  sync_response_schemas（预演）          → 补 response Schema 的端点 = 0
  probe_result_tables --check           → ✅ 与取报表证据一致（实测 195 条：可收口 187 · 留缺 2）
  probe_singleton_tables --check        → ✅ 与取设置表证据一致（PASSED 2 · FAILED 7 · 留缺 5）

红线（全 0）
  厂商名（midas/csi/etabs）在两豁免子包之外 = 0
  app/** 里 .commit() / .rollback() 仅 unit_of_work.py（其余 0 处）
  app/** 里模板取值字面量 = 0
  app/** 本批一行未改（git status --porcelain app 为空）
  依赖清单（pyproject.toml）一行未改（无新依赖）
  未改表（无 Alembic 迁移）· 未改 9 Tool Contract
```

**钉住计数**：本批**没有**任何既有钉住计数发生变化 —— 端点 **636** · Schema 文件 **625** ·
模板 **71** / body **115** · `availability: verified` **493** · 响应 Schema 行 **317** ·
`write_path_coverage()` **`72 / 633`**（`model_write_ratio` **`72 / 434`**）·
候选 **72 / 62 / 0** · blocked **501 / 438 / 31** · 留缺账本 **178**。
⇒ `tests/test_midas_*_p142..p149*`（含 `p149b2` / `p149c` / `p149d` / `p149e`）**一行未改**、断言**未**放宽
（`test_midas_singleton_tables_p149d.py` 只**新增**一项 R119 用例，**未**改任何既有断言）。

## 5. 仍未闭环（如实）

1. **R117 的 3 个留缺**：`DB.KFAC` 需 **CIVIL_DESIGNER** 自省来源；`DB.SSEIS` / `DB.SWIND` 需
   **MIDAS 侧**澄清 `INPUTS` / `PROFILE` 布局（数据侧现用 `PARAMETERS` / `ADDITIONAL_LOAD`，两者不一致）
   与 `type: "multi object"` 的合法写法。
2. **R118 的 15 个带前置链端点**：恢复条件 = 沿用 L5 的前置链机制续跑（`--probe --only …`）。
3. **R118 的 4 个 `put_rejected:400`**：三种形状全被拒（原生报错文本已逐条记进证据），成因需 **MIDAS 侧**排查。
4. **`/DESIGN/SRC/AIK-SRC2K/DSRC` 的残留**：`DELETE` 返回 `200` 却不删，**无法清除**（已披露）。
5. **`DESIGN.*` 别名路由的 `DELETE` 不生效**（3 个实测）：影响面 = 别名路由上的删除；**成因需 MIDAS 侧**。
6. **R113 / R114 / R115 / R116 / `DB.PZEF` 残留**：本批只维护留缺记录（成因需 MIDAS 侧）。
