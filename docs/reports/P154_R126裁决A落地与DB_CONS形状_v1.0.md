# P154 —— **R126 裁决 A′ 落地**（接口层写路径 4/13 → **11/13**）+ **R128**（`DB.CONS` 请求体形状）+ **R129**（`POST.TABLE` 路由存在）v1.0

- 批次：**P154**（＝ `docs/07` §15.6 的 **P0 裁决闸门 + P1 的前半**；**P154-B** 见 §8）
- 裁决：**D1 = A′**（只扩 `DB.MATL` **11** + `DB.SECT` **6** = **17** 个 canonical 字段）·
  **D4 = 两个专用项目**（`gen-empty` + 建模/分析用项目，后者**待提供**）
- 实例：`gen-local`（GEN NX，`http://localhost:3030/gen`）· 实测日期 `2026-10-11`
- 证据：
  - `registry/live/interface_path_probe.json`（写路径 **13** 条 = **11** `PASSED` + **2** `FAILED`；**零残留**）
  - `registry/live/boundary_shape_probe.json`（**R128**：形状 A/B **5** 变体 = **2** `PASSED` + **3** `FAILED`）
  - `registry/live/canonical_field_gap.json`（A′ 后重算：字段集缺口 **4 → 2**）
  - `registry/live/interface_read_probe.json`（读路径 **15** 条 = **2** + **7** + **6**，按新字段表刷新）
- 工具：`registry/tools/probe_interface_paths.py`（扩参 / 前置链 / 形状判定）·
  `registry/tools/probe_boundary_shape.py`（**新**）
- 判定：`tests/test_midas_interface_contract_p154.py`（**16** 项 + **1** 项环境门控）·
  `tests/test_midas_interface_paths_p152.py` / `tests/test_midas_interface_read_p153.py`（**只**同步数字）·
  `tests/test_midas_write_templates_p139.py`（清单自检，**判定变强**）

## 0. 一句话结论

**R126 的 A′ 落地后，接口层写路径从 `4 / 13` 变成 `11 / 13`。** `DB.MATL` / `DB.SECT` 的
**17** 个原生字段按裁决纳入 canonical（**只**改 `transforms.py` 的两张字段表 —— 17 个 native 叶子
**全部**已在数据侧请求 Schema 里声明 ⇒ **不**需要改 `registry/**`、**不**注入任何默认值）；
`DB.ELEM` 的添加 / 编辑 / 删除随之全部 `PASSED`（原先连创建都过不去）。

**剩下的 `2 / 13` 不是字段集问题，而是形状问题（新裁决 R128）**：`DB.CONS` 的 `Assign`
**外层键必须是该支承所在的节点编号**，接口层当前产出的是 `{"Assign": {"ITEMS": […]}}`（缺外层编号键）
⇒ 原生 `400 Wrong Field`。**位数（6 vs 7）已被 A/B 排除**（D2 收口）。

**另立 R129**：`POST /POST/TABLE` 在 GEN NX 上**路由存在**（业务级 `400`，而对照 `POST/NOSUCHTABLE`
是 `404`）⇒ `RESULT.ANALYSIS.SUMMARY` 的 `STRUCTAI-3000` 是**数据侧 `products` 声明**造成的，
**不是**原生不可用。

## 1. `app/**` 的授权范围与理由（⚠️ 本批要求的**前置声明**）

**授权范围 = `app/infrastructure/adapters/midas/transforms.py` 的 2 张字段表**（`MaterialTransformer` /
`SectionTransformer`），**仅此一个文件**（`git status` 可核）。

| 项 | 内容 |
| --- | --- |
| **授权依据** | `docs/reports/P0_裁决清单_v1.0.md` 的 **D1 = A′**（用户裁决，2026-10-11） |
| **为什么必须动 `app/**`** | canonical 字段集**只**由 `transforms.py` 的 `FieldMap` 表达（判定点唯一）；P09 起 65 个 Operation 的 `input_schema` **未登记** ⇒ `SchemaEngine` 不拦，**唯一**的契约执行点就是字段表 |
| **为什么**不**动 `registry/**`** | 17 个 native 叶子**全部**已在数据侧请求 Schema 里声明（`fields_for_path()` 逐条可查，见 `tests/...p154` 的 `test_p154_aprime_native_fields_are_all_schema_declared`） |
| **为什么**不**动 9 Tool Contract** | 未新增 / 未删除 Operation；未改任何 Tool 名 / 数量 / 请求信封 |
| **为什么不违反「不臆造字段」** | 字段表**只**声明 `(canonical, native)` 映射，**没有**任何默认值 —— 不给值就**不**出现在 body（`test_p154_the_manual_example_values_are_not_injected_as_defaults` 逐条断言）；探针里的取值来自**手册示例**（可回溯 `write_templates.json`） |
| **判定有无放宽** | **没有**：P152 的断言逐条保留，只把「当时的数字」换成「实测的数字」；P139 的清单还**变强**（新增自检，见 §6） |

## 2. R126 裁决 A′ 落地（主）

### 2.1 改了什么（**17** 个字段，逐条）

| 端点 | 字段数 | `canonical` ← `native`（canonical 名 = P153 证据包的 `canonical_hint`） |
| --- | --- | --- |
| `DB.MATL` | **11** | `he_spec`←`HE_SPEC` · `he_cond`←`HE_COND` · `plmt`←`PLMT` · `p_name`←`P_NAME` · `bmass_dens`←`bMASS_DENS` · `damp_rat`←`DAMP_RAT` · `p_type`←`PARAM[].P_TYPE` · `standard`←`PARAM[].STANDARD` · `code`←`PARAM[].CODE` · `db`←`PARAM[].DB` · `belast`←`PARAM[].bELAST` |
| `DB.SECT` | **6** | `datatype`←`SECT_BEFORE.DATATYPE` · `horz_offset_opt`←`SECT_BEFORE.HORZ_OFFSET_OPT` · `vert_offset_opt`←`SECT_BEFORE.VERT_OFFSET_OPT` · `use_shear_deform`←`SECT_BEFORE.USE_SHEAR_DEFORM` · `use_warping_effect`←`SECT_BEFORE.USE_WARPING_EFFECT` · `vsize`←`SECT_BEFORE.SECT_I.vSIZE` |

**全部 `required = false`**（可选）—— 既有必填字段（`name` / `type` / `section_type`）**一行未改**。

### 2.2 接口层产出的 body == 手册示例 body（**字段级**关闭）

离线逐条复算（`tests/...p154` 的 `test_p154_the_interface_body_matches_the_manual_example_field_for_field`）：

```text
DB.MATL  手册示例用到的叶子路径 ⊆ 接口层 body 的叶子路径   （差集 = ∅）
DB.SECT  同上                                            （差集 = ∅）
A′ 的 17 个 native 路径 ⊆ 接口层 body 的叶子路径            （逐条）
```

⚠️ 反向**不**要求相等：接口层另有**既有**可选字段（`density` / `poisson_ratio`）会一并出现 ——
那是 P152 起就有的 canonical 字段，**不**属 R126 缺口。

### 2.3 接口层写路径实测：**13** 条 = **11** `PASSED` + **2** `FAILED`

| 路径 | 端点 | P152（A′ 前） | **P154（A′ 后）** |
| --- | --- | --- | --- |
| 添加 | `DB.NODE` | `PASSED` | `PASSED` |
| 添加 | `DB.ELEM` | `FAILED`（`400 Wrong Field`） | **`PASSED`** |
| 添加 | `DB.MATL` | `FAILED`（`400 Wrong Field`） | **`PASSED`** |
| 添加 | `DB.SECT` | `FAILED`（`400 Unknown Error`） | **`PASSED`** |
| 添加 | `DB.CONS` | `FAILED` | `FAILED`（⇒ **R128**） |
| 编辑 | `DB.NODE` | `PASSED` | `PASSED` |
| 编辑 | `DB.ELEM` | `FAILED` | **`PASSED`** |
| 删除 | `DB.NODE` | `PASSED` | `PASSED` |
| 删除 | `DB.ELEM` | `FAILED`（前置创建被拒） | **`PASSED`** |
| 删除 | `DB.MATL` | `FAILED`（前置创建被拒） | **`PASSED`** |
| 删除 | `DB.SECT` | `FAILED`（前置创建被拒） | **`PASSED`** |
| 删除 | `DB.CONS` | `FAILED`（前置创建被拒） | `FAILED`（⇒ **R128**） |
| 删除 | `DB.GRUP` | `PASSED`（**原生**前置） | `PASSED` |

**计数** `{'PASSED': 11, 'FAILED': 2}`；按路径 = `add {4,1}` · `edit {2}` · `delete {5,1}`；
**跑前 / 跑后哨兵（6 个端点）逐条相同**、`residue = {}`、`aborted = ''`（3 块 5 / 5 / 3 + 块间只读健康检查均 `200`）。

### 2.4 顺带修掉的**两处探针缺陷**（**不是**契约问题）

| # | 缺陷 | 症状 | 修法 |
| --- | --- | --- | --- |
| 1 | **前置节点几何**：两个节点用了**同一坐标** | `DB.ELEM` 原生 `400`「**不能添加/编辑单元。单元 1 的几何形状不正确。**」 | 第 `index` 个节点沿 `-Z` 逐级下移（`0` / `-6`）= `docs/07` §13.5 的竖向构件 |
| 2 | **`DB.CONS` 缺 `group_name`** | canonical 字段表里**一直有** `group_name`，P152 的探针**没传** | 补 `group_name=""`（手册示例的空串 = 不分组） |

⚠️ 缺陷 1 是 P152 那 5 条 `400 Wrong Field` 里 `DB.ELEM` 的**第二层**成因 —— A′ 补齐字段后**才**暴露出来；
这说明「字段集补齐」与「探针参数正确」是**两个**独立的必要条件。

## 3. R128（新裁决）：`DB.CONS` 的请求体**形状**

### 3.1 先排除**位数**（D2 的前半）

补上 `group_name` 后仍 `400` ⇒ 按 D2 的「先测后裁」做了**位数 A/B**（数据侧 raw，3 变体）：
`"111000"`（6 位）/ `"1111000"`（7 位，手册示例）/ 6 位且省略 `GROUP_NAME` ⇒ **三者全部 `400`**
⇒ **位数不是成因**（D2 的「扩 `RW`」**不必**做）。

### 3.2 形状 A/B（**5** 变体，`registry/live/boundary_shape_probe.json`）

⚠️ 首轮 A/B 被**混淆**：变体各自用了编号 `1..5` 当外层键，而**只有节点 1 存在** ⇒ 结果不可用。
修正后的设计：**每个变体都用同一个「存在的」节点编号当外层键**，且**变体间先清理再下一个**。

| 变体 | 请求体（要点） | 原生 | 落库 | 读回键 |
| --- | --- | --- | --- | --- |
| `assign_items` | `{"Assign": {"ITEMS": [<条目>]}}` ← **接口层当前产出** | **`400`** | ✗ | — |
| `assign_node_keyed_items` | `{"Assign": {"<节点编号>": {"ITEMS": [<条目含 ID>]}}}` ← **数据侧形态** | **`200`** | **✓** | `CONSTRAINT` · `GROUP_NAME` · `ID` |
| `assign_node_keyed_items_no_id` | 同上，内层条目**省略** `ID` | **`200`** | **✓** | 同上（原生补 `ID`） |
| `assign_node_keyed_item` | `{"Assign": {"<节点编号>": <条目平铺>}}` | **`400`** | ✗ | — |
| `assign_nonexistent_node_key` | 外层键 = **不存在**的节点编号（`999999`） | **`200`** | **✗** | — |

**结论（R128）**：`DB.CONS` 的正确形状 = **外层键为「该支承所在的节点编号」+ 内层 `ITEMS` 数组**；
内层条目的 `ID` **可选**（原生自行补全）。

⚠️ **假成功陷阱**：外层键**不是**存在的节点编号时，原生返回 **`200` 却什么都不建** ——
只看状态码会把「没建」当成「建好了」（与 **R119** 的「`DELETE` 假成功」同形，**必须**以**再读**为准）。

### 3.3 为什么这**不**是 R126 的字段集问题

接口层 `DB.CONS` 的 body 字段集已与手册示例**逐条一致**（`ID` / `GROUP_NAME` / `CONSTRAINT` 都在），
差异**只**在**包装形状**（缺外层编号键）。⇒ 修复点在 `MidasHttpClient` 的**请求构造**
（`is_items_style()` 对 `DB.CONS` 的包装），**不**在字段表。

## 4. D3 的裁决输入：`POST.TABLE` 在 GEN NX 上**路由存在**（R129）

**零写请求**的只读核实（3 次请求 + 2 次对照哨兵）：

```text
OPTIONS /POST/TABLE                                  → 200   Allow: POST
POST    /POST/TABLE {TABLE_TYPE: DISPLACEMENTG}      → 400   {"error":{"message":"[empty] Cannot generate
                                                              table data as there is no analysis result."}}
POST    /POST/NOSUCHTABLE（**对照**）                 → 404   Not Found
GET     /DB/NODE · /DB/CONS                          → 200   {"NODE":{}} · {"CONS":{}}   （项目仍为空）
```

**判读**：`400` 是**业务级**错误（「没有分析结果」），而**不存在**的路由是 `404`（对照已证）
⇒ `POST /POST/TABLE` 在本 build 上**路由存在**。因此接口层 `RESULT.ANALYSIS.SUMMARY` 的
`STRUCTAI-3000 endpoint_not_available_for_product` 来自**数据侧 `products` 声明**
（`["CIVIL_DESIGNER", "CIVIL_NX"]`，**不含** `GEN_NX`），**不是**原生不可用。

⇒ **R129**：`POST.TABLE` 的 `products` 声明与实测不符。**恢复条件** = 按实测更正 `products`
（属**数据侧**改动，需**实测依据 + 显式裁决** —— 本批**只**交付依据，**不**改数据）。

## 5. 不变量与**同步的钉住计数**

| 项 | 值 | 说明 |
| --- | --- | --- |
| `live.write_path_coverage()` | **`72 / 633`** | **不变**（`model_write_ratio` **`72 / 434`**） |
| R118 子桶（编辑 PUT） | **`42 / 23 / 6`**（71 行） | **不变** |
| 映射缺口 | **`517` = `271` + `246`** | **不变** |
| 缺口分类 | **`271` = `0` + `51` + `220`** | **不变** |
| 端点 / Schema 文件 / 模板 / body / 响应 Schema 行 / 留缺账本 | **636 / 625 / 71 / 115 / 317 / 178** | **不变** |
| **接口层写路径子桶** | `4 / 9` → **`11 / 2`** | ⚠️ **变了**（A′ 的实测依据） |
| **R126 证据包** | 字段集缺口 `4 → **2**` · 取值缺口 `2 → **3**` · 已覆盖 `4 → **5**` | ⚠️ **变了**（同上） |
| 接口层读路径子桶 | **`15` = `2` + `7` + `6`** | 计数不变（按新字段表**刷新**了读数） |

⇒ 同步的文件：`tests/test_midas_interface_paths_p152.py` · `tests/test_midas_interface_read_p153.py`
（**只**改数字与注释，断言**未**放宽）；其余 `tests/test_midas_*_p142..p151*` **一行未改**。

## 6. 顺带修正：P139 的「特征取值」清单**分类错误**（判定**变强**）

`tests/test_midas_write_templates_p139.py` 的 `CORE_FORBIDDEN_LITERALS` 把 **`vSIZE`** 列为
「模板**取值**」—— 但它其实是 `{"SECT_I": {"vSIZE": [1, 1]}}` 的**键名**（= 原生**字段名**，
且已在数据侧请求 Schema 里声明）。A′ 把 `SECT_BEFORE.SECT_I.vSIZE` 写进字段表时**必然**命中。

**修法（不是放宽）**：从清单移除 `vSIZE`，并**新增**
`test_p139_the_forbidden_literals_are_template_values_not_field_names` —— **机械**断言
「清单里每一项都是模板的**取值**、且都不是**键名**」⇒ 清单自此**自检**（判定**变强**）。

## 7. 闸门（原始输出）

```text
pytest -q
  1171 passed, 10 skipped in 246.92s     （收尾；0 failed）
  （基线 1155 / 9 / 0 ⇒ 本批 +16 passed、+1 skipped；既有 1155 全部保留）

ruff check app tests            → All checks passed!
ruff format --check app tests   → 237 files already formatted
mypy app                        → Success: no issues found in 184 source files

python -m app.main              → 退出码 0；stdout 0 字节
Base.metadata.create_all        → 24 张表；SELECT 1 → 1

数据侧工具（**17** 个全绿；本批**未**改任何 `registry/**` 数据文件）
  check_write_templates         → ✅ 71 个模板 / 115 个 body；0 未知字段；不可判 body = 0
  sync_write_templates --check  → ✅ 模板 = 71（盘面 71）；新增 0；剔除 0
  sync_availability --check     → ✅ 与只读证据一致（61 个可用端点已收口）
  sync_endpoint_methods --check → ✅ 端点 methods 与证据文件一致（无待写回项）
  sync_manual_index --check     → ✅ 产物与机械结果一致（841 端点 / 607 有示例）
  sync_request_schemas --check  → ✅ 9 个文件与机械结果一致
  fix_schema_defects --check    → ✅ registry/schema/** 文件数 = 625；无残留占位串
  sync_manifest（预演）          → manifest 条目数 = 636；字段差异总数 = 0
  sync_response_schemas（预演）  → 补 response 的端点 = 0；跳过（无 Schema 文件）= 4
  probe_result_tables --check   → ✅ 与取报表证据一致（实测 195 条：可收口 187 · 留缺 2）
  probe_singleton_tables --check→ ✅ 与取设置表证据一致（PASSED 2 · FAILED 7 · 留缺 5）
  sync_introspect_fields --check→ ✅ 与证据一致（199 可比；补 Schema 21 · 留缺 3 · 无缺口 175）
  probe_put_edits --check       → ✅ 与数据侧一致（可探 71 行：42 / 23 / 6；已披露残留 = DSRC）
  probe_interface_paths --check → ✅ 写路径 13 条（**11 + 2**）· 读路径 15 条零写请求（2 / 7 / 6）
                                   · 缺口 271 + 246
  check_canonical_field_gap     → ✅ 模板端点 71（有 Transformer 10 / 无 61）· 字段集缺口 **2**
                                   · 取值缺口 **3** · 无 canonical 模型 61 · 已覆盖 **5**
  classify_mapping_gap --check  → ✅ 契约外 271 = 已有模型 0 + 有手册示例 51 + 需产品裁决 220
  probe_boundary_shape --check  → ✅ `DB.CONS` 形状证据自洽（5 变体 = 2 + 3）· 清理逐条确认

红线（全 0）
  厂商名（midas/csi/etabs，两豁免子包之外）= 0
  app/domain 无 SQLAlchemy / FastAPI / MCP SDK = 0 处
  app/** 里 .commit() / .rollback() 仅 unit_of_work.py（5 处，含 1 处 docstring）
  Core（MIDAS 子包之外）里模板取值 = 0 处
  STRUCTAI-xxxx 恰好 20 码 · 未改表 · **未**改 9 Tool Contract · 无新依赖
  app/** 改动 = **仅** `app/infrastructure/adapters/midas/transforms.py`（见 §1 的授权范围）
```

## 8. 仍未闭环 / **P154-B** 的前置条件

1. **R128 的修复（P154-B 的主项）**：把 `DB.CONS` 的请求构造从
   `{"Assign": {"ITEMS": […]}}` 改成 `{"Assign": {"<节点编号>": {"ITEMS": […]}}}`
   —— 落点在 `MidasHttpClient` 的包装逻辑（`is_items_style()` 一族），**属 `app/**` 改动**，
   需**新的授权范围**；且**必须**同时复核其它 `ITEMS` 形态端点（`DB.CNLD` / `DB.PRES` …）
   是否受同一包装规则影响（**不**能只改 `DB.CONS` 一处）。
2. **旗舰五步链（P1 的后半）需要第二个专用项目**：**D4 = 两个项目**已裁决，但第二个项目
   **尚未提供**。请给出它的 MAPI 路径（形如 `http://localhost:3030/<项目名>`）——
   拿到后即可跑 `§13.5` 五步链（`BUILD.COLUMN → MODEL.LOAD.ASSIGN → ANALYSIS.STATIC →
   RESULT.NODE.DISPLACEMENT → DESIGN.STEEL`）并闭环 **R127a**（取结果族）。
   ⚠️ **不要**在 `gen-empty`（当前空项目）上跑分析：分析结果**可能清不掉**，会把唯一项目永久弄脏。
3. **D2 已收口**：位数（6 vs 7）**不是**成因（A/B 三变体全 `400`）⇒ **不必**扩 `RW`；
   `DB.CONS` 的问题归 **R128**（形状）。
4. **D3 已给出输入**：`POST.TABLE` 路由**存在**（**R129**）；是否按实测更正数据侧 `products`
   仍待裁决（改数据需实测依据 + 显式裁决 —— 依据已备齐）。
5. **D5（51 个「有手册示例」端点是否纳入契约）**：**未裁**，按 P0 清单**可延后**。
6. **R118 / R119–R125 / R113–R116 / `DB.PZEF` 残留**：一律**只维护留缺记录**（**冻结**）。
