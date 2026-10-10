# P143 · 候选集的**产品级方法覆盖**保真度修复 + CIVIL NX 跨产品真实 L5 实测 v1.0

> 批次：**P143**（用户续接：「MIDAS CIVIL NX 我新建了空白项目；Civil Designer 是 CIVIL NX 的后处理，没办法新建空白模型」）
> 提交：见 `docs/08` §3 · 裁决：`docs/07` §16.1 **R99 新增** + P143 回填

---

## 0. 一句话结论

用户给的约束（CD 无法建空白模型）**不构成阻塞** —— 实测发现 **`CIVIL_DESIGNER` 根本没有可写的候选端点**：
数据侧对它的 `DB.NODE` / `DB.ELEM` 只声明 `GET`（`product_overrides`），而 `candidate_keys()` 只看**基础**
`methods`，把这两个**只读**端点误判成候选。**P142 公布的 `Civil Designer = 2` 是伪的，真值是 `0`**。

同时：**CIVIL NX 的真实 L5 已在用户新建的空白项目上跑通 = 11 / 11 `PASSED`**（可复现命令见 §3.1）。

| 项 | P142 记 | **P143 实测** |
| --- | --- | --- |
| `candidate_keys()` — GEN NX | 11 | **11（不变）** |
| `candidate_keys()` — CIVIL NX | 11 | **11（不变）** |
| `candidate_keys()` — **Civil Designer** | **2** | **0（更正）** |
| CIVIL NX 真实 L5 | 未跑 | **11 / 11 `PASSED`**（状态码 **201**） |
| 覆盖率 `write_path_coverage().ratio` | `11 / 609` | **`11 / 609`（口径不变 —— 分子是 key 去重，见 §4）** |

---

## 1. 为什么 CD 的「2 个候选」是伪的（实测）

### 1.1 数据侧怎么说（`registry/common/db/NODE.yaml` / `ELEM.yaml`）

```yaml
products: [CIVIL_DESIGNER, CIVIL_NX, GEN_NX]
product_overrides:
  CIVIL_DESIGNER:
    uri: DB/NODE
    methods: GET          # ← CD 上**只有** GET
    wrapper: {write: none, shape: flat, body_kind: object, read_root_path: [result, return_value]}
```

`DB.ELEM` 同形（`methods: GET`）。全表扫描：**37** 个端点带 `CIVIL_DESIGNER.methods` 覆盖，其中**只有**
`DB.NODE` / `DB.ELEM` 把读写**降级为只读**（其余是 `POST` 或 `GET, PUT`，不影响候选判定）。

### 1.2 解析层**早已**正确

```text
registry.resolve(key="DB.NODE", product="CIVIL_DESIGNER", method="POST")
  → MidasCapabilityError("method_not_available_for_product")
registry.methods_for(key="DB.NODE", product="CIVIL_DESIGNER") == ("GET",)
```

`resolve()` 的 `methods = _methods(override.get("methods")) or definition.methods`（`docs/07` §7.6 / `registry/README.md` §5 第 2 步）**一直**是对的。

### 1.3 缺陷在候选集那一层（已修）

`MidasLiveWriteProbe.candidate_keys()` / `_write_method()` 原先读的是 **`definition.methods`（基础定义）**
⇒ CD 的 `DB.NODE` / `DB.ELEM` 进了候选集。若真去探，`resolve(POST)` 会拒绝 → 记 `FAILED`
（而 `tests/test_midas_registry_p138.py` 的门控用例断言「**全部**候选 `PASSED`」→ 在 CD 上**必然失败**）。

---

## 2. 修复（P143）

| 文件 | 改动 |
| --- | --- |
| `app/infrastructure/adapters/midas/registry.py` | 新增 **`MidasRegistry.methods_for(*, key, product)`**：先 `product_overrides.<产品>.methods`，再回落主定义；`resolve()` 改为**调用它**（单一真源，行为不变） |
| `app/infrastructure/adapters/midas/write_probe.py` | ① `candidate_keys()` 用 `methods_for` 判定「有写方法 / 有 `GET`+`read_root`」；② `_write_method()` 同源；③ `probe_key()` 把「**该产品没有写方法**」与「Transformer 未注册」**分开记因**：新增 `detail = no_write_method_for_product`（仍 `NO_PAYLOAD_TEMPLATE`、**零**写请求） |

**修复后实测**：

```text
GEN_NX          candidates = 11  (DB.BMLD … DB.STLD)
CIVIL_NX        candidates = 11  (同一批 key)
CIVIL_DESIGNER  candidates =  0  ()          ← P142 记 2，更正为 0
```

**红线**：改动**只**落在 `adapters/midas/` 子包内；无新依赖；`STRUCTAI-xxxx` 仍 **20** 码；未改表。

---

## 3. CIVIL NX 真实 L5 实测（用户新建的空白项目）

### 3.1 可复现命令

```powershell
. .\scripts\load-midas-env.ps1 -Instance civil
$env:MIDAS_LIVE_L4 = '1'
$env:MIDAS_LIVE_PROJECT = 'civil-nx-blank-dedicated-project'
$env:MIDAS_LIVE_PRODUCT = 'CIVIL_NX'      # P143 新增：门控用例按产品跑（缺省 GEN_NX）
python -m pytest "tests/test_midas_registry_p138.py::test_p138c_live_batch_records_l5_rows_and_the_recounted_coverage" -q
# → 1 passed in 17.42s
```

### 3.2 逐条四态（**11 / 11 `PASSED`**，脱敏）

| key | 方法 | 路径 | 结论 | 自建编号 | 读回 | 已删 | 状态码 | 载荷来源 | 前置链 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `DB.BMLD` | POST | `/DB/BMLD` | **PASSED** | 1 | ✔ | ✔ | **201** | `manual_example` | `DB.STLD#1` `DB.MATL#1` `DB.SECT#1` `DB.NODE#1` `DB.NODE#2` `DB.ELEM#1` |
| `DB.BODF` | POST | `/DB/BODF` | **PASSED** | 1 | ✔ | ✔ | **201** | `manual_example` | `DB.STLD#1` |
| `DB.CNLD` | POST | `/DB/CNLD` | **PASSED** | 1 | ✔ | ✔ | **201** | `manual_example` | `DB.STLD#1` `DB.NODE#1` |
| `DB.CONS` | POST | `/DB/CONS` | **PASSED** | 1 | ✔ | ✔ | **201** | `manual_example_adjusted` | `DB.NODE#1` |
| `DB.ELEM` | POST | `/DB/ELEM` | **PASSED** | 1 | ✔ | ✔ | **201** | `manual_example_adjusted` | `DB.MATL#1` `DB.SECT#1` `DB.NODE#1` `DB.NODE#2` |
| `DB.FBLD` | POST | `/DB/FBLD` | **PASSED** | 1 | ✔ | ✔ | **201** | `manual_example` | `DB.STLD#1` `DB.STLD#2` |
| `DB.MATL` | POST | `/DB/MATL` | **PASSED** | 1 | ✔ | ✔ | **201** | `manual_example` | — |
| `DB.NODE` | POST | `/DB/NODE` | **PASSED** | 1 | ✔ | ✔ | **201** | `schema_derived` | — |
| `DB.PRES` | POST | `/DB/PRES` | **PASSED** | 1 | ✔ | ✔ | **201** | `manual_example_adjusted` | `DB.STLD#1` `DB.MATL#1` `DB.SECT#1` `DB.NODE#1..#4` `DB.ELEM#1` |
| `DB.SECT` | POST | `/DB/SECT` | **PASSED** | 1 | ✔ | ✔ | **201** | `manual_example` | — |
| `DB.STLD` | POST | `/DB/STLD` | **PASSED** | 1 | ✔ | ✔ | **201** | `manual_example` | — |

`{PASSED: 11, FAILED: 0, NO_PAYLOAD_TEMPLATE: 0, NO_READBACK: 0}`。

⚠️ **真实差异（已记录）**：CIVIL NX 的创建返回 **`201 Created`**（GEN NX 为 `200`）—— `status_code`
保真（P139）如实回传原生码，**没有**把 201 伪装成 200。

### 3.3 纪律核对

- 跑前哨兵（`db/NODE` `db/ELEM` `db/MATL` `db/SECT` `db/STLD` `db/FBLD`）→ **全空** ⇒ 空项目闸门放行；
- 跑后**同一批哨兵再次全空** ⇒ **零残留**；`DELETE` 全程带路径 key（`/DB/STLD/2`、`/DB/STLD/1` …）；
- 只碰自建编号（`max + 1`）；**未**触碰用户既有模型（新项目本身为空）。
- ⚠️ 实测还发现：切换项目瞬间云端中继会**短暂全 404**（含根路径），重试即恢复 —— 与 `docs/07` §15.4
  的「云端中继间歇性掉线」同源；排查时**先重试**再判故障。

---

## 4. 覆盖口径（**未**变）：换产品**不**增加分子

`live.write_path_coverage()` 的分子 = `midas_api_verifications` 的 **L5 `PASSED` 行的去重 `endpoint_key`**
∩ 写路径端点 —— **按 registry key**，**不**按「端点 × 产品」。故：

- CIVIL NX 的 11 条 `PASSED` 行与 GEN NX 的**是同一批 key** ⇒ `covered` 仍 **11**、`ratio` 仍 **`11 / 609`**；
- 它们证明的是「**同一批端点在第二个产品上也通**」（跨产品证据），**不是**新的覆盖数；
- 要按「端点 × 产品」统计，属于**口径变更**（需一次显式裁决，本批**不**自行改）。
- 可执行判定 = `tests/test_midas_write_coverage_p143.py::test_p143_the_coverage_numerator_is_key_based_not_product_based`。

---

## 5. 测试

新增 `tests/test_midas_write_coverage_p143.py`（**5** 项）：

| 判定 | 用例 |
| --- | --- |
| 候选集按产品解析 | `test_p143_candidates_respect_product_level_method_overrides`（11 / 11 / **0**；CD 的只读端点不入候选，但 GEN NX / CIVIL NX 仍入） |
| 解析层早已正确 | `test_p143_resolve_rejects_write_methods_the_product_does_not_declare` |
| `methods_for` 语义 | `test_p143_methods_for_prefers_the_override_and_falls_back_to_the_definition` |
| 如实记因 + 零写请求 | `test_p143_probe_key_reports_the_missing_write_method_without_writing`（`no_write_method_for_product`） |
| 口径（key 去重） | `test_p143_the_coverage_numerator_is_key_based_not_product_based` |

既有断言**逐条更新、不放宽**：

- `tests/test_midas_write_coverage_p142.py`：`CANDIDATES_BY_PRODUCT["CIVIL_DESIGNER"]` **2 → 0**；
  `_derived_candidates()` 改用 `registry.methods_for`（独立复算与实现同源但**不**调用 `candidate_keys`）。
- `tests/test_midas_registry_p138.py`：门控真实批量用例新增 **`MIDAS_LIVE_PRODUCT`**（缺省 `GEN_NX`），
  探针与 L5 行的 `product` 都按它取 —— 于是 CIVIL NX 可用**同一条**可执行判据复现（§3.1）。

---

## 6. 全量闸门（P143 收尾实测）

| 闸门 | 结果 |
| --- | --- |
| `ruff check app tests` | **All checks passed!** |
| `ruff format --check app tests` | **219 files already formatted**（P142 为 218） |
| `python -m mypy app` | **Success: no issues found in 184 source files** |
| `python -m pytest -q` | **993 passed + 7 skipped**（P142 为 988 + 7；本批 **+5**） |
| `python -m app.main` | 退出码 **0**，**stdout 0 字节** |
| 建表 / `SELECT 1` | **24** 张表 + `SELECT 1` → **1** |
| 红线 | 厂商名（各自子包之外）**0**；`STRUCTAI-xxxx` **恰好 20**；`commit()` / `rollback()` **仅** `unit_of_work.py` |
| 真实 L5（CIVIL NX） | **11 / 11 `PASSED`**；跑前 / 跑后哨兵**全空** |

> 1 条 `aiosqlite` 线程清理 warning 为**既有**（`docs/08` §3 的 P137 行已登记「不来自本批文件」）。

---

## 7. 裁决（`docs/07` §16.1）

### **R99 新增**（候选集曾忽略**产品级方法覆盖**）

| 项 | 内容 |
| --- | --- |
| 现象 | `candidate_keys()` / `_write_method()` 读**基础** `definition.methods`，忽略 `product_overrides.<产品>.methods` ⇒ `CIVIL_DESIGNER` 的 `DB.NODE` / `DB.ELEM`（数据侧只有 `GET`）被误判成候选（**2** 个），而 `resolve(POST)` 会正确拒绝 |
| 影响 | ① P142 公布的「CD 候选 = 2」是**伪数**（真值 **0**）；② 若真按 CD 跑批量，两个端点都会记 `FAILED`，而门控用例断言「全部候选 `PASSED`」→ **必然失败**；③ 掩盖了「CD 没有可写端点」这一事实 |
| 处置 | **已修**：`registry.methods_for()` 单一真源 + `resolve()` 复用它；`candidate_keys()` / `_write_method()` 改用产品级方法；`probe_key()` 把原因分成 `no_transformer_for_endpoint` / **`no_write_method_for_product`**（都零写请求）。可执行判定 = `tests/test_midas_write_coverage_p143.py` |
| 关联 | `docs/07` §7.6（产品差异先查 `product_overrides`）· `registry/README.md` §4 / §5 第 2 步 · **R97 / R98** |

---

## 8. 未闭环（如实留缺）

1. **覆盖率仍 `11 / 609`**（口径不变）：CD 的候选集为 **0** ⇒ **没有**「CD 专用空项目」这一需求；想继续推分子仍只有
   P142 报告 §9 列的三条路（补 Transformer（206 个可读回）/ 另立判据（336 个读不回）/ 改规范）。
2. **`CIVIL_NX` 的 11 / 11 是跨产品证据，不进分子**；要让它进分子必须先裁决「是否按端点 × 产品统计」。
3. `R95`（模板新鲜度）、`R90`（ETABS L4 / L5）状态**未变**。
4. 云端中继的**短暂全 404** 已在 §3.3 记录（排查时先重试）；未做自动化重试（属下一批可选项）。

---

## 9. 证据索引

| 项 | 位置 |
| --- | --- |
| Core 修复 | `app/infrastructure/adapters/midas/registry.py`（`methods_for`）· `write_probe.py`（候选集 / 写方法 / 新原因） |
| 测试 | `tests/test_midas_write_coverage_p143.py`（5 项）· `tests/test_midas_write_coverage_p142.py`（CD 更正）· `tests/test_midas_registry_p138.py`（`MIDAS_LIVE_PRODUCT`） |
| 数据侧（未改） | `registry/common/db/NODE.yaml` / `ELEM.yaml` 的 `product_overrides.CIVIL_DESIGNER.methods = GET` |
| 风险裁决 | `docs/07` §16.1 **R99 新增** + P143 回填 |
| 交接 | `docs/08` §3 / §4 |
