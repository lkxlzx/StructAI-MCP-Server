# P167 报告：`POST.TABLE` 的 `TABLE_TYPE` **枚举收口** ⇒ 解锁 `RESULT.ANALYSIS.SUMMARY`（**R160**）

> 批次：**P167**（数据侧裁决 + 真机受控测量）｜ 状态：✅ **已交付**
> 关联：**R151**（本批的出发点，P160e-a 留缺）· **R140**（`spec_guard` 的由来）·
> **R129**（`POST.TABLE` 的产品闸门已通过）· **R152**（收益映射）· **R158 / R159**（主指标可执行化）
> 纪律：**铁律 ⓪**（判据 = **效果**）· 只碰**自建项目** · **零残留** · **不**放松 R140 · **不**按手册示例硬凑

---

## 0. 一句话结论

拦住 `RESULT.ANALYSIS.SUMMARY` 的**不是**原生，而是**核心自己的 `spec_guard`**（**R140**）
手里那份**只有 2 个取值**的 `TABLE_TYPE` 枚举（来自 help center **一篇文章**的 `json_schema`）。

枚举来源换成**两个可复算来源的并集**（登记表 **194** ∪ 手册声明 **121** = **225**，
**严格包含**旧枚举）⇒ `POST.TABLE` 的 `availability` **`untested → verified`**
⇒ 它挡住的 **1** 个 Operation（`RESULT.ANALYSIS.SUMMARY`，**通用取表入口**）**解锁**
⇒ **主指标 `67 / 71` → `68 / 71`**（被挡 **4 → 3** · 挡点端点 **14 → 13**）。

⚠️ **`app/**` 一行未改** —— 枚举是**数据**，`spec_guard` **只**按 Schema 里写下的 `enum` 判定。

---

## 1. R151 的答案（**真机实测**）

| 相 | 实测（2026-10-15，`gen-local`，自建混凝土简支梁：21 节点 / 20 单元 / 工况 `DL`） |
| --- | --- |
| **原生** | `POST /POST/TABLE {"Argument": {"TABLE_TYPE": "DISPLACEMENTG"}}` ⇒ **`200`** · 信封 `"empty"` · `HEAD` **9** 列 · `DATA` **63** 行 |
| **核心（收口前）** | `STRUCTAI-1200 value_not_in_spec_enum`（`native_stage = midas_adapter`）∧ **零请求** |
| **核心（收口后，Contract-Test 口径）** | `PASSED` · 规范化结果 `data.result.rows` = **63** 行 · 原生请求 `POST /POST/TABLE` ⇒ `200` |
| **核心（收口后，生产口径）** | 同上（`allow_unverified=False`，**无**任何旁路） |
| **阴性（核心）** | 伪 token `NOT_A_REAL_TABLE_XYZ` ⇒ `STRUCTAI-1200 value_not_in_spec_enum` ∧ **零请求** |
| **阴性（原生）** | 伪 token ⇒ **`400`** |
| **零残留** | 跑前 / 跑后 **6** 项模型哨兵**逐项一致**（`/DB/{NODE,ELEM,MATL,SECT,STLD,CNLD}`） |

⇒ **拦住它的是枚举，不是原生**（R151 的判定得到直接证实）。

---

## 2. 数据侧裁决：枚举的来源（**可复算**）

生成器 = `registry/tools/sync_table_type_enum.py`（**只**拥有
`registry/schema/common/post/TABLE.json` 的 `Argument.TABLE_TYPE` 的 `enum` / `description`；
其余内容**逐字节**透传）。

| 来源 | 判据（**机械扫描**，无人工取值） | 规模 |
| --- | --- | ---: |
| ① **登记表** | `registry/manifest.json` 里 key 以 `POST.TABLE.` 开头且 `table_type` **非空**的端点 ⇒ 取其 `table_type` | **194** |
| ② **手册声明** | `MIDAS_API_Online_Manual_数据_v1.0.json` 里**所有**条目 `json_schema` 的 `TABLE_TYPE.enum`（扫描口径与 `sync_request_schemas.table_type_tokens()` **逐字相同**） | **121** |
| **并集** | 落进 `TABLE_TYPE.enum` | **225** |

### 2.1 为什么取**并集**（**不**只取登记表）

`WEIGHT_IRREGULARITY_Y` 是**手册声明**但**没有**登记成独立端点的取值
（`POST.TABLE.WEIGHT_IRREGULARITY_Y` 不存在）—— 而它**就在旧枚举里**。
只取①会把它**删掉** ⇒ 那是把闸门**收紧**，与 R151 的教训（枚举**可能不全**）**反向**。

| 判据 | 结果 |
| --- | --- |
| 新枚举 ⊇ 旧枚举（`WEIGHT_IRREGULARITY_X` / `_Y`） | ✅ **是**（`superset_of_historical = true`） |
| 登记表独有 / 手册独有 | **104** / **31** |
| 伪 token 在枚举里？ | ❌ **不在**（⇒ R140 的保护成立） |
| 原生的 `WEIGHT_IRREGULARITY_Y` 实测 | `200` · **空块** `{}`（⇒ 它**确实是**合法 token，只是本模型无数据） |
| 原生的 `TH_DISP`（手册声明但未登记）实测 | **`400`** —— **取值不适用**，**不是**崩溃（干净的 `400`） |

### 2.2 「枚举只增不减」是**可执行**的护栏

`sync_table_type_enum.py --write` 时，若机械结果**丢掉**了已落盘的任何取值 ⇒ **拒绝写入**
（退出码 1，文件一字未改）；确需收紧才加 `--allow-shrink`（= 一次**显式裁决**）。
判定 = `tests/test_midas_post_table_enum_p167.py::test_p167_the_generator_refuses_to_shrink_the_enum`
（在临时仓库上跑，**不**碰真实数据）。

---

## 3. 顺带实测的两条事实（登记备查）

1. **原生对 `TABLE_TYPE` 的取值大小写不敏感**：`displacementg` ⇒ 同样 **`200`** / **63** 行。
   而 `spec_guard` 按手册声明的**大写**取值判定 ⇒ 小写会在**核心**被拦
   （`STRUCTAI-1200`，**零请求**）。⚠️ 这**不是**本批引入的收紧（小写**从来**不在枚举里）；
   规范调用方一律传登记表里的 token（大写）。
2. **手册声明但未登记**的 token 原生仍可能拒（`TH_DISP` ⇒ **`400`**）—— 那是**取值不适用**，
   **不是**崩溃风险（R140 的事故形态是**弹窗 / 访问违例**；这里回的是**干净的 `400`**）
   ⇒ 把手册声明的取值纳入枚举**不会**重新引入 R140 的事故面。

---

## 4. 交付物

| 项 | 内容 |
| --- | --- |
| 枚举生成器 | `registry/tools/sync_table_type_enum.py`（默认预演 / `--write` / `--check`；**只增不减**护栏；只依赖标准库） |
| 数据侧改动 | `registry/schema/common/post/TABLE.json`（`TABLE_TYPE.enum` **2 → 225** + `description` 指向来源） |
| 数据侧收口 | `registry/common/post/TABLE.yaml`（`availability: untested → verified` + `verified_on: ["gen-local"]` + R160 记录；**R151 的历史记录原样保留**） |
| 派生物 | `registry/manifest.json`（`sync_manifest.py --write`：**2** 处字段；再预演差异 **0**） |
| 探针 | `registry/tools/probe_post_table_enum.py`（默认预演 / `--probe` Contract-Test 口径 / `--probe --production` 生产口径 / `--check` 离线自洽；**复用** `probe_interface_paths._Stack` 与 `_read_exercise`） |
| 证据 | `registry/live/post_table_enum_probe.json`（原生 + 核心 + 阴性 + **两个口径** + 哨兵；**不含**凭据 / 响应原文） |
| 主指标 | `registry/tools/check_operation_availability.py`（`EXPECTED_AVAILABLE 67 → 68`、被挡清单 **4 → 3**） |
| 判定 | `tests/test_midas_post_table_enum_p167.py`（**19** 项） |
| 同步更新的既有判定 | `test_midas_operation_availability_p165b.py`（68 / 3 / 13 + 新增「剩余挡点**分组**」用例）· `test_midas_view_result_post_p166.py`（主指标现值）· `test_midas_availability_p149c/p149e` · `test_midas_nxsdk_products_p161.py` · `test_midas_result_tables_p149d.py`（`verified 510 → 511` · `untested 103 → 102` · `NO_GET 102 → 101`）· `test_midas_interface_read_p153.py`（`POST.TABLE` 的现状由 `untested` 改 `verified`，**P153 的时点证据原样保留**） |
| 文档 | `README.md` §1 / §1.1 / §5.1 / §5.2 · `registry/README.md` **§8.21** · `docs/07` §6.0 / §7.2 / §15.5 / §16.1 **R160** / §17.3 · `docs/08` §3 / §4 |
| `app/**` | **一行未改**（纯数据侧 + 探针 + 文档） |
| 实例 | **只**发 `POST /POST/TABLE`（取报表：**不**落文件、**不**写模型）+ 只读 `GET`（健康检查 / 哨兵）；**绝不**碰 `DESIGN.{RC,SRC}` 的 `*-ANAL`（R154 崩溃族；探针内有**显式**闸门自检） |

---

## 5. 闸门

```text
pytest -q                              ✅ 1410 passed / 11 skipped / 0 failed
                                       （P166 基线 1390 ⇒ +19 = P167 判定用例 + 1 = P165-b 的新增用例）
ruff check app tests                   All checks passed!
ruff format --check app tests          259 files already formatted
mypy app                               Success: no issues found in 185 source files
sync_table_type_enum --check           ✅ 与机械结果一致（225）
sync_table_type_enum（预演）            差异 0（幂等）
probe_post_table_enum --check          ✅ 离线自洽（两个口径 + 阴性 + 哨兵）
check_operation_availability --check   ✅ 68 / 71（被挡 3 · 挡点端点 13）
sync_manifest（预演）                    字段差异 0
fix_schema_defects --check             ✅ 625 文件 / 0 违规
sync_request_schemas --check           ✅ 9 个文件与机械结果一致
sync_response_schemas（预演）            补 response Schema 的端点 = 0
check_write_templates --summary        ✅ 全部来源可复算
sync_availability --check              ✅ 与只读证据一致
probe_view_result_post --check         ✅ 离线自洽（R159 未回退）
```

⚠️ `pytest -q` 必须先把 `TEMP` / `TMP` 指到**可写**目录（本机 `%TEMP%` 不可写 ⇒ 见 P166 报告 §6）。
⚠️ 那 **1** 条 warning 是 **P137 已记录**的 aiosqlite 线程清理 warning（**不**来自本批文件）。

---

## 6. 仍未闭环（**不在我方手上**）

| 项 | 需要什么 | 风险 |
| --- | --- | --- |
| **主指标剩余 3 个 Operation** | 挡点 **13** 个端点分两组：**6** 个 `*-ANAL` = **实测崩溃族**（**R154**）⇒ **MIDAS 侧**修 `wg_db.dll`；**6** 个 `*-TABLE` = `untested`（要**先有设计结果** ⇒ 依赖那 6 个）+ **1** 个 `POST.STEELCODECHECK`（**R152**：我方**可**收口但**不**解锁） | — |
| `VIEW.RESULTGRAPHIC` 的请求 Schema（**36** 个变体） | **产品 / 数据侧裁决**（**R155**）：`spec_guard` **没有** `CURRENT_MODE` 的枚举可查 ⇒ 非法取值抓不到 | 无（纯数据） |
| **枚举来源普查**（R160 的同类复核） | 见 `docs/07` §15.5 的 **P168** 建议：把 `registry/schema/**` 的**每一个** `enum` 逐条分类来源，找出其余「来源太窄」的 | 无（纯数据 + 离线工具） |

---

## 7. 本批的教训

1. **「拦住调用」的可能是我们自己的护栏** —— R151 整整留缺了两个批次（P160e-a → P166），
   而原生一直是好的。⇒ 遇到「零请求 + `STRUCTAI-xxxx`」时，**先**确认闸门是**谁**（`native_stage`
   就是为此留的），再判「产品缺陷」还是「我方数据太窄」。
2. **枚举的来源必须是「可复算的登记表」，而且**只增不减**** —— 这是 R151 的直接教训：
   从**一篇文章**的 `json_schema` 落下来的枚举，天然**太窄**；而「补枚举」若顺手删掉旧取值，
   就变成**收紧**闸门（同一类事故的镜像）。⇒ 本批把「只增不减」做成**可执行护栏**。
3. **两个口径都要测** —— Contract-Test 口径（旁路）用来**测效果**（否则可用性闸门先拦），
   生产口径用来证**生产路径本身已通**。只测前者会把「旁路能跑」当成「产品能跑」（P160a 的教训）。
4. **顺手核对自己的断言** —— 起草时写的「剩余挡点**全部**在崩溃族里」是**错的**
   （13 个里只有 6 个）；已改成**分组**断言并逐条钉住。**不**让一句顺口的总结留在文档里。
