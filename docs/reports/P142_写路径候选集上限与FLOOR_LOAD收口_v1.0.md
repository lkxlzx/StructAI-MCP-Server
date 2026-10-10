# P142 · 写路径候选集上限裁决 + 契约内缺口 `FLOOR_LOAD` / `DB.FBLD` 收口 v1.0

> 批次：**P142**（`docs/08` §4 的续接提示词）· 任务：**写路径覆盖继续扩大（R4 / R14 / R97）**
> 提交：见 `docs/08` §3 · 裁决：`docs/07` §16.1 **R97 更正** + **R98 新增**

---

## 0. 一句话结论

续接提示词给的「扩大机制**只有一条**：加模板 + 前置链」在**实测上不成立** ——
`candidate_keys()` 的上限是「Transformer **已注册**」，GEN NX 的 10 个候选**已全部 `PASSED`**，
加模板**不可能**增加候选。真正能扩大分子的**契约内**缺口只有一处：
`operations.LOAD_STEP_BY_TYPE` **早已声明** `"FLOOR_LOAD": "DB.FBLD"`，但
`LOAD_TRANSFORMERS` 里**没有** `FLOOR_LOAD`、`TRANSFORMER_REGISTRY` 里**没有** `midas.fbld.v1`
（缺的是**实现**，不是 canonical 概念）。本批把它补齐并实测：

| 项 | P141 | **P142** |
| --- | --- | --- |
| `candidate_keys()`（GEN NX / CIVIL NX / Civil Designer） | 10 / 10 / 2 | **11 / 11 / 2** |
| 被「Transformer 未注册」挡住的写端点 | 543 / 472 / 32 | **542 / 471 / 32** |
| 写路径模板 | 9 | **10** |
| 复算的 body 总数 | 31 | **34** |
| `TRANSFORMER_REGISTRY` | 19 | **20** |
| **真实 L5 覆盖率** `write_path_coverage().ratio` | **`10 / 609`** | **`11 / 609`** |
| 子桶 `model_write_ratio` | `10 / 410` | **`11 / 410`** |
| 分母 `write_path_keys()` / `write_only` / `result_query` / `model_write` | 609 / 368 / 199 / 410 | **609 / 368 / 199 / 410（不挪）** |

---

## 1. 候选集上限：实测与归因（判定 1）

`MidasLiveWriteProbe.candidate_keys()` 的判据（`write_probe.py` 裁决 1 / 5）：
**有写方法（`POST`/`PUT`）∧ 有读路径（`GET` + `read_root`）∧ `TRANSFORMER_REGISTRY` 已注册 ∧
非 `destructive` / 非 `delete_all_via_body` ∧ 端点 `enabled` ∧ 产品可得**。

| 产品 | 候选数 | 候选 | 被未注册 Transformer 挡住 |
| --- | --- | --- | --- |
| `GEN_NX` | **11** | `DB.BMLD` · `DB.BODF` · `DB.CNLD` · `DB.CONS` · `DB.ELEM` · **`DB.FBLD`** · `DB.MATL` · `DB.NODE` · `DB.PRES` · `DB.SECT` · `DB.STLD` | **542** |
| `CIVIL_NX` | **11** | 同上 | **471** |
| `CIVIL_DESIGNER` | **2** | `DB.ELEM` · `DB.NODE` | **32** |

**关键事实（P141 提示词的错误前提）**：

1. `candidate_keys()` 要求 `TRANSFORMER_REGISTRY.get(transformer_name_for(key))` **非空**；
   `transformer_name_for()` 是**机械派生** `midas.<code 小写>.v1`。
2. 分母 **609** 里，**542**（GEN NX）根本进不了候选 —— 它们**没有** Transformer；
   模板只影响**已候选**端点的请求体，故「加模板」对它们**零效果**。
3. 10 个候选在 P139 已 **10 / 10 `PASSED`**，且候选里 `NO_PAYLOAD_TEMPLATE` = **0** ⇒
   **`10 / 609` 是「只加模板」这一机制的上限**。
4. 契约内（`operations.py` 的 69 个 Operation 编排）声明的**写步骤**里，
   凡三步链**适用**的端点**全部**已在候选集内（P142 前 = 10 个，本批 = 11 个）⇒
   加模板**不可能**再增加分子（可执行判定 =
   `tests/test_midas_write_coverage_p142.py::test_p142_no_contract_write_endpoint_is_blocked_by_a_missing_transformer`）。
5. 契约内**其余**写步骤（`DOC.*` / `VIEW.DISPLAY` / `VIEW.RESULTGRAPHIC` / `DESIGN.*` /
   `POST.STEELCODECHECK`）**没有 `GET` / 没有 `read_root`** ⇒ 三步链（创建 → 读回 → 按路径 key 删除）
   **结构上不适用**，与模板无关。

> 结论：**分子不可能靠「加模板」增长**；唯一契约内的增长点是「补齐一个**已被声明**的 Transformer」，
> 即 `FLOOR_LOAD`。

---

## 2. 契约内缺口：`FLOOR_LOAD` → `DB.FBLD`（判定 3）

### 2.1 为什么这是缺口、而不是臆造

| 证据 | 内容 |
| --- | --- |
| `docs/07` §6.3（`MODEL.LOAD.ASSIGN` 行） | 端点表**明确列出** `DB.STLD · DB.BMLD · DB.BODF · DB.PRES · DB.CNLD · **DB.FBLD**`，「按荷载类型分派」 |
| `app/infrastructure/adapters/midas/operations.py` | `LOAD_STEP_BY_TYPE = {… "SELF_WEIGHT": "DB.BODF", **"FLOOR_LOAD": "DB.FBLD"**}` —— **早已声明**（冻结编排） |
| `app/infrastructure/adapters/midas/transforms.py`（P142 前） | `LOAD_TRANSFORMERS` **没有** `FLOOR_LOAD` 键 ⇒ 执行楼面荷载一律 `load_type_not_mapped`（`STRUCTAI-1200`） |
| `registry/common/db/FBLD.yaml` | `methods: [POST, GET, PUT, DELETE]` · `wrapper.write: Assign` · `wrapper.read_root: FBLD` · `path_key_supported: true` · `risk.destructive: false` · `products: [CIVIL_NX, GEN_NX]` · `title: Define Floor Load Type` |
| `registry/schema/common/db/FBLD.json` | 原生字段 `NAME` / `DESC` / `ITEM[]{LCNAME, FLOOR_LOAD, OPT_SUB_BEAM_WEIGHT}`（`help_center` 来源） |
| 上游手册 `db/FBLD` 示例 | `{"Assign": {"1": {"NAME": "Floor_example", "DESC": "", "ITEM": [{"LCNAME": "DC", "FLOOR_LOAD": 10, "OPT_SUB_BEAM_WEIGHT": true}, {"LCNAME": "DW", "FLOOR_LOAD": 20, …}]}}}` |

**故本批**：canonical 概念（`FLOOR_LOAD`）**已在契约里**，缺的是实现 —— 补实现**不是**改规范、
**不是**臆造字段（字段名逐条来自数据侧 Schema），**不**触碰 9 Tool Contract。

### 2.2 `TEMPERATURE` 的对照（本批**未**放宽）

`docs/04` §32 的 canonical 荷载抽象 = `NODE_FORCE` / `NODE_MOMENT` / `BEAM_FORCE` /
`BEAM_MOMENT` / `PRESSURE` / `TEMPERATURE` / `SELF_WEIGHT`。`TEMPERATURE` **在 `registry/` 的
DB Schema 里没有对应条目**（`transforms.py` 裁决 7），故**故意缺席**：本批**保持**它
`load_type_not_mapped`（可执行判定见同文件 `test_p142_floor_load_dispatch_uses_only_schema_declared_fields`）。

---

## 3. Core 改动（`app/infrastructure/adapters/midas/transforms.py`）

1. 新增 `FloorLoadTransformer(SchemaBoundTransformer)`：`name = "midas.fbld.v1"` ·
   `endpoint = "DB.FBLD"` · `fields` = `name→NAME`（required）/ `desc→DESC` /
   `load_case→ITEM[].LCNAME`（required）/ `floor_load→ITEM[].FLOOR_LOAD`（required）/
   `sub_beam_weight→ITEM[].OPT_SUB_BEAM_WEIGHT`。
   ⚠️ `ITEM[]` 与 `MaterialTransformer` 的 `PARAM[]` 是**同一**约定：canonical 只覆盖**首行**。
2. `LOAD_TRANSFORMERS` 增 `"FLOOR_LOAD": FloorLoadTransformer`（`MODEL.LOAD.ASSIGN` 的楼面荷载
   不再 `load_type_not_mapped`）。
3. `TRANSFORMER_REGISTRY` 增 `"midas.fbld.v1"`（⇒ `DB.FBLD` 进入候选集）。
4. `__all__` 增 `"FloorLoadTransformer"`。

**分层红线**：改动**只**落在 `adapters/midas/` 子包内；`grep -ri "midas\|etabs\|csi" app/`
在各自子包**之外** = **0**；`STRUCTAI-xxxx` 仍**恰好 20** 码；无新依赖。

---

## 4. 数据侧改动（`registry/live/write_templates.json`）

新增 `DB.FBLD` 模板（**唯一**扩大机制的数据侧落点）：

| 项 | 值 |
| --- | --- |
| `source` | `kind = manual_example` · `uri = db/FBLD` · `example = Define Floor Load Type` · `example_id = 1` · `url = …/articles/35953604106137` |
| `adjustments` | **`[]`**（body **原样**照抄手册示例） |
| `body` | `{NAME: "Floor_example", DESC: "", ITEM: [{LCNAME: "DC", FLOOR_LOAD: 10, OPT_SUB_BEAM_WEIGHT: true}, {LCNAME: "DW", FLOOR_LOAD: 20, OPT_SUB_BEAM_WEIGHT: true}]}` |
| `prerequisites` | **2** 条 `DB.STLD`（`item_id` `1` / `2`）：`manual_example_adjusted`，`NAME: DL → DC` / `NAME: DL → DW`（`TYPE: D` 不变），body = `{NAME: DC\|DW, TYPE: D, DESC: DeadLoads}` |
| `self_references` / `target_id_source` | 均为空（`Assign` 键承载编号，body 内**没有**自身编号字段） |
| `references` | 无（FBLD 按 **`LCNAME` 名字**引用荷载工况，不是按编号） |

### 4.1 数据侧复算（改动前 → 改动后，逐条）

```powershell
python registry/tools/check_write_templates.py        # 模板 + 编号声明
python registry/tools/fix_schema_defects.py --check   # R19 不变量
python registry/tools/sync_manifest.py                # 派生 manifest（预演）
python registry/tools/sync_response_schemas.py        # response 块（预演）
python registry/tools/sync_request_schemas.py --check # 已落盘 == 机械结果
```

| 工具 | 输出（改动后） |
| --- | --- |
| `check_write_templates.py` | 端点模板 **9 → 10**；校验的 body **31 → 34**；来源可复算 body **34**；不可判 **0**；`references` **14（不变）**；`self_references` **4（不变）**；`✅ 全部模板的来源可复算；body 无 Schema 未声明的字段；前置链可执行。` |
| `fix_schema_defects.py --check` | `✅ registry/schema/** 文件数 = 625；schema 全为对象；无残留占位串；无大小写不符的 type。` |
| `sync_manifest.py` | 字段差异总数 **0** |
| `sync_response_schemas.py` | 差异 **0**（未声明解包链 = 0） |
| `sync_request_schemas.py --check` | `✅ --check：9 个文件与机械结果一致` |

`git status` 在跑完 5 个工具后**只剩本批的 2 个改动文件**（`transforms.py` +
`write_templates.json`）⇒ 生成链**幂等**、无意外写回。

---

## 5. 真实 L5 批量实测（判定 6 / 7）

**命令**（专用 dev 实例 = 本地 GEN NX，项目为空；凭据**只**经环境变量）：

```powershell
. .\scripts\load-midas-env.ps1 -Instance gen
$env:MIDAS_LIVE_L4 = '1'; $env:MIDAS_LIVE_PROJECT = 'p142-dedicated-dev-project'
python -m pytest "tests/test_midas_registry_p138.py::test_p138c_live_batch_records_l5_rows_and_the_recounted_coverage" -q -s
# → 1 passed in 5.94s
```

### 5.1 跑前哨兵（只读，`GET`）

`db/NODE` · `db/ELEM` · `db/MATL` · `db/SECT` · `db/STLD` · `db/FBLD` → **全部 200 + `{"message":""}`（空）**
⇒ 空项目闸门放行，**零**写请求前先完成核对。

### 5.2 逐条四态（**11 / 11 `PASSED`**，脱敏：只有 key / 方法 / URI / 自建编号 / 状态码 / 载荷来源 / 前置链）

| key | 方法 | 路径 | 结论 | 自建编号 | 读回 | 已删 | 状态码 | 载荷来源 | 前置链 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `DB.BMLD` | POST | `/DB/BMLD` | **PASSED** | 1 | ✔ | ✔ | 200 | `manual_example` | `DB.STLD#1` `DB.MATL#1` `DB.SECT#1` `DB.NODE#1` `DB.NODE#2` `DB.ELEM#1` |
| `DB.BODF` | POST | `/DB/BODF` | **PASSED** | 1 | ✔ | ✔ | 200 | `manual_example` | `DB.STLD#1` |
| `DB.CNLD` | POST | `/DB/CNLD` | **PASSED** | 1 | ✔ | ✔ | 200 | `manual_example` | `DB.STLD#1` `DB.NODE#1` |
| `DB.CONS` | POST | `/DB/CONS` | **PASSED** | 1 | ✔ | ✔ | 200 | `manual_example_adjusted` | `DB.NODE#1` |
| `DB.ELEM` | POST | `/DB/ELEM` | **PASSED** | 1 | ✔ | ✔ | 200 | `manual_example_adjusted` | `DB.MATL#1` `DB.SECT#1` `DB.NODE#1` `DB.NODE#2` |
| **`DB.FBLD`** | **POST** | **`/DB/FBLD`** | **PASSED** | **1** | **✔** | **✔** | **200** | **`manual_example`** | **`DB.STLD#1` `DB.STLD#2`** |
| `DB.MATL` | POST | `/DB/MATL` | **PASSED** | 1 | ✔ | ✔ | 200 | `manual_example` | — |
| `DB.NODE` | POST | `/DB/NODE` | **PASSED** | 1 | ✔ | ✔ | 200 | `schema_derived` | — |
| `DB.PRES` | POST | `/DB/PRES` | **PASSED** | 1 | ✔ | ✔ | 200 | `manual_example_adjusted` | `DB.STLD#1` `DB.MATL#1` `DB.SECT#1` `DB.NODE#1..#4` `DB.ELEM#1` |
| `DB.SECT` | POST | `/DB/SECT` | **PASSED** | 1 | ✔ | ✔ | 200 | `manual_example` | — |
| `DB.STLD` | POST | `/DB/STLD` | **PASSED** | 1 | ✔ | ✔ | 200 | `manual_example` | — |

计数：`{PASSED: 11, FAILED: 0, NO_PAYLOAD_TEMPLATE: 0, NO_READBACK: 0}`。

### 5.3 覆盖率重算（分母**不挪**）

```text
write_path_keys = 609 | write_only = 368 | result_query = 199 | model_write = 410
covered = 11 | ratio = 11 / 609 | model_write_covered = 11 | model_write_ratio = 11 / 410
covered_keys = (DB.BMLD, DB.BODF, DB.CNLD, DB.CONS, DB.ELEM, DB.FBLD, DB.MATL, DB.NODE, DB.PRES, DB.SECT, DB.STLD)
```

### 5.4 清理核对（纪律：跑完必须恢复空白）

跑后对 **11** 个被触碰端点逐一只读核对（`db/NODE` `db/ELEM` `db/MATL` `db/SECT` `db/STLD`
`db/FBLD` `db/BMLD` `db/BODF` `db/CNLD` `db/CONS` `db/PRES`）→ **全部 200 + 空**
⇒ **零残留**，项目恢复空白；`DELETE` 全程带路径 key（`/DB/FBLD/1`、`/DB/STLD/2`、`/DB/STLD/1`）。

---

## 6. 测试（判定 1–8）

新增 `tests/test_midas_write_coverage_p142.py`（**8** 项）：

| 判定 | 用例 |
| --- | --- |
| 1 候选集上限 | `test_p142_the_candidate_set_is_the_registered_transformer_intersection`（独立复算 11/11/2 + 542/471/32 + `TRANSFORMER_REGISTRY` = 20） |
| 8 契约内无残留缺口 | `test_p142_no_contract_write_endpoint_is_blocked_by_a_missing_transformer`（声明的写步骤里三步链适用者 == 候选集；不适用者只能是 `DOC.` / `VIEW.` / `DESIGN.` / `POST.`） |
| 2 加模板不能新增候选 | `test_p142_a_template_alone_cannot_add_a_candidate`（`DB.ELNK` 注入模板 → 候选集不变、`NO_PAYLOAD_TEMPLATE`、**零**写请求） |
| 3 缺口收口 | `test_p142_fbld_closes_the_declared_floor_load_gap` |
| 4 字段只来自 Schema | `test_p142_floor_load_dispatch_uses_only_schema_declared_fields`（含 `TEMPERATURE` 仍拒绝） |
| 5 数据侧模板 | `test_p142_the_data_side_declares_the_fbld_template_with_the_stld_chain`（body == 手册示例；10 模板 / 34 body / 0 错） |
| 6 离线三步链 | `test_p142_the_fbld_chain_creates_reads_back_and_deletes_only_its_own_ids`（路径顺序逐条 + 三处 POST 载荷逐字节 + 零残留） |
| 7 口径不变 | `test_p142_the_denominator_and_sub_buckets_are_unchanged`（609/368/199/410 + `11 / 609` + `11 / 410` + 分子**数据驱动**） |

既有断言**逐条更新、不放宽**：
- `tests/test_midas_write_templates_p139.py`：`TEMPLATE_KEYS` **9 → 10**（+`DB.FBLD`）、
  `PROBED_KEYS` **10 → 11**、`EXPECTED_BODIES` **31 → 34**、
  `CORE_FORBIDDEN_LITERALS` **新增 `"Floor_example"`**（模板取值**不得**进 Core）、
  用例名与 docstring 同步。
- `tests/test_midas_registry_p138.py` 的 gated 真实批量用例（断言「**全部**候选 `PASSED`」）
  自动覆盖新增的 `DB.FBLD`（本批已实测通过）。

---

## 7. 全量闸门（P142 收尾实测）

| 闸门 | 结果 |
| --- | --- |
| `ruff check app tests` | **All checks passed!** |
| `ruff format --check app tests` | **218 files already formatted**（P141 为 217） |
| `python -m mypy app` | **Success: no issues found in 184 source files** |
| `python -m pytest -q` | **987 passed + 7 skipped**（P141 为 980 + 7；本批 **+8** 用例） |
| `python -m app.main` | 退出码 **0**，**stdout 0 字节** |
| `Base.metadata.create_all` + `inspect` | **24** 张表（缺失 0 / 多余 0）+ `SELECT 1` → **1** |
| 数据侧 5 工具 | 见 §4.1（差异 0 / 幂等） |
| 红线 | 厂商名（各自子包之外）**0**；`app/domain` 无 SQLAlchemy/FastAPI/MCP SDK；`STRUCTAI-xxxx` **恰好 20**；`commit()`/`rollback()` **仅** `unit_of_work.py`；`app/**` 里 **0** 处模板取值（`Floor_example`） |
| `container.BATCH_ID` | 仍 `"P42"`（`docs/07` §16 **R82** 的裁决：P119 起不推进批次标记） |

> 运行环境注意（本机）：`.venv` 的 `pyvenv.cfg` 指向本机 Python 3.14.2（原为另一台机器的
> `C:\Python314`）；子进程会打印 `✅`，故闸门需 `$env:PYTHONUTF8='1'`（否则 2 个用例因
> 子进程 GBK 编码报假失败）。

---

## 8. 裁决回填（`docs/07` §16.1）

### 8.1 **R97 更正**（模板覆盖面）

| 项 | 原（P139 / P141 记） | **P142 实测更正** |
| --- | --- | --- |
| 模板覆盖面 | 「仅 **9** 个端点有模板」 | **10** 个（`DB.FBLD` 补齐）；`DB.NODE` **不**带模板（机械派生 body 已被接受） |
| 未覆盖的含义 | 「`609` 里仍有 **599** 个未覆盖」 | **不成立为「欠账」**：`609` 里 **542**（GEN NX）**没有** Transformer ⇒ **不**入候选，加模板**零效果**；分子上限 = 候选集（本批 **11**） |
| 扩大机制 | 「按同一机制逐个补（一条模板 + 前置链 = 一个端点）」 | **模板不能增加候选**；增长只能靠**补齐已声明的 Transformer**（本批 `FLOOR_LOAD`）。下一步的真实杠杆见 §9 |

### 8.2 **R98 新增**（`FLOOR_LOAD` 实现缺口）

| # | 事项 | 影响 | 处置 |
| --- | --- | --- | --- |
| **R98** | **`FLOOR_LOAD` 已声明但无实现** | `LOAD_STEP_BY_TYPE["FLOOR_LOAD"] = "DB.FBLD"` 在冻结编排里**早已存在**，但 `LOAD_TRANSFORMERS` 缺该键、`TRANSFORMER_REGISTRY` 缺 `midas.fbld.v1` ⇒ ① `MODEL.LOAD.ASSIGN` 的楼面荷载一律 `load_type_not_mapped`（`STRUCTAI-1200`）；② `DB.FBLD` 因「Transformer 未注册」被 `candidate_keys()` 排除，写路径覆盖**少一个** | **已收口（P142）**：新增 `FloorLoadTransformer`（`midas.fbld.v1`）+ `LOAD_TRANSFORMERS["FLOOR_LOAD"]` + 数据侧模板（body 原样照抄手册示例 + 2 条 `DB.STLD` 前置）⇒ 真实 L5 **11 / 11 `PASSED`**、覆盖率 **`11 / 609`**（`model_write_ratio` `11 / 410`）。**不**改规范、**不**臆造字段、**不**动 9 Tool Contract。可执行判定 = `tests/test_midas_write_coverage_p142.py` |

---

## 9. 未闭环（如实留缺，**不**假装完成）

1. **写路径覆盖仍 `11 / 609`** —— 分母里 **598** 个未覆盖，其中 **368** 个是**只写**端点
   （连 `GET` 都没有，只读探针**完全**覆盖不到）。
2. **契约内不再有「仅缺 Transformer」的写端点**（§1 判定 4）⇒ 想继续推分子，只有三条路
   （**均需一次显式裁决**，本批**不**自行选择）：
   - **(a) 换产品实测**：`CIVIL_NX` **11** 个候选 / `Civil Designer` **2** 个候选**从未跑过**，
     但两者当前实例的项目**非空**（CIVIL NX：节点 162 / 单元 273 / 材料 5）⇒ 需要
     `docs/04` §72 的**专用空项目**（用户侧动作），或显式 `allow_non_empty=True`
     （P141 / R96 的更强判据：清理后既有编号集合**一字未变**）。
   - **(b) 扩契约**：为 `542`（GEN NX）个**未声明**的写端点注册 Transformer —— 它们**不在**
     9 Tool / 69 Operation 契约内（`docs/07` §14.5 禁止改 Tool Contract）⇒ **本批不做**。
   - **(c) 改规范**：`DB.FBLD` 之外的「`docs/04` §32 canonical 荷载抽象」扩展（如把 `TEMPERATURE`
     映射到某个端点）—— 需先改 `docs/04`（规范），**本批不做**。
3. **`R95`（模板新鲜度）** 仍未常规化：模板是「手册示例 + 实测」的快照，MIDAS 构建升级后
   可能失效；失效**不会**被掩盖（L5 逐条跑，失效即 `FAILED`）。
4. **`R90`（ETABS 的 L4 / L5）** 仍缺专用环境（用户确认 ETABS 未安装）。
5. **`CONCURRENT_JOINT_FORCE` 的残余假设**（分析模式开关 `PostMode`）未证伪（P141 结论不变）。

---

## 10. 证据索引

| 项 | 位置 |
| --- | --- |
| Core 改动 | `app/infrastructure/adapters/midas/transforms.py`（`FloorLoadTransformer` + 2 处注册 + `__all__`） |
| 数据侧改动 | `registry/live/write_templates.json`（`DB.FBLD` 模板 + note） |
| 验收测试 | `tests/test_midas_write_coverage_p142.py`（8 项） |
| 既有断言更新 | `tests/test_midas_write_templates_p139.py`（集合/计数/禁字） |
| 权威数据源 | `registry/README.md` §2.3 / §8.1 / §8.6 · `registry/common/db/FBLD.yaml` · `registry/schema/common/db/FBLD.json` |
| 上游手册 | `MIDAS_API_Online_Manual_数据_v1.0.json` 的 `db/FBLD` 条目（示例 `Define Floor Load Type`） |
| 风险裁决 | `docs/07` §16.1 **R97 更正** + **R98 新增** |
| 交接 | `docs/08` §3（批次状态表）/ §4（下一批提示词） |
