# P166 报告：**结果视图（post）的纯 API 路径** ⇒ 收口 `VIEW.RESULTGRAPHIC`（**R159**）

> 批次：**P166**（真机受控测量 + 数据侧收口）｜ 状态：✅ **已交付**
> 关联：**R157**（本批的出发点）· **R155**（变体取值表）· **R158**（主指标可执行化）·
> **R148**（`VIEW.*` 参数通道）· **R154**（原生崩溃护栏）· `docs/07` §16.1
> 纪律：**铁律 ⓪**（判据 = **效果**）· 只碰**自建项目** · **零残留** · **不**臆造取值

---

## 0. 一句话结论

**R157 的「静默 `200` / 画面没变」有答案了**：P164-f 的请求体**只有**
`CURRENT_MODE` + `LOAD_CASE_COMB`，**缺 `TYPE_OF_DISPLAY`** ——
而 **`TYPE_OF_DISPLAY.<子块>.OPT_CHECK = true` 才是真正把结果图形打开的那个开关**。

补上它之后，**纯 API 进结果视图（post）的路径**成立，`VIEW.RESULTGRAPHIC` 的
**效果判据 7 / 7 通过** ⇒ `availability` **`untested → verified`** ⇒
它挡住的 **6** 个 `VIEW.*` Operation **解锁** ⇒ **主指标 `61 / 71` → `67 / 71`**。

---

## 1. 纯 API 进结果视图（post）的路径（**手册自己的写法**）

| 机制 | 实测语义 |
| --- | --- |
| `POST /VIEW/CAPTURE` 的 `Argument.SET_MODE`（`"pre"` / `"post"`） | **切换视图模式**，且**粘性**（后续不带 `SET_MODE` 的 `CAPTURE` 仍在该模式下，直到再发 `"pre"`）；**前提** = 项目**确有分析结果**（无结果 ⇒ **`400`** `"Post Mode is not available"`，P160d 已实测） |
| `POST /VIEW/RESULTGRAPHIC` | 写**持久**结果图形：`CURRENT_MODE` + `LOAD_CASE_COMB` + **`TYPE_OF_DISPLAY`** |
| `POST /VIEW/CAPTURE` 的 `Argument.RESULT_GRAPHIC` | **一次性覆盖**（只作用于本次 `CAPTURE`）—— 手册 `Capture #1` 示例的形状 |
| 渲染条件 | 结果图形**只在 post 模式下渲染**；且**必须**有 `TYPE_OF_DISPLAY.<子块>.OPT_CHECK = true`，否则原生**照样回 `200`** 但**什么都不画** |

**依据（上游手册，可复算）**：`MIDAS_API_Online_Manual_数据_v1.0.json` 的 `view/CAPTURE`
条目第 3 项写着 `Select Analysis Mode • Pre-Mode: "pre" • Post-Mode: "post"`（`SET_MODE`）、
第 14 项写着 `Result Display • refer to "view/RESULTGRAPHIC" manual`（`RESULT_GRAPHIC`）；
`MIDAS_API_Online_Manual_Gen_NX_v1.0.json` 的 `Capture #1` 示例**同时**给出
`SET_MODE: "post"` 与 `RESULT_GRAPHIC`。

---

## 2. 效果判据（**铁律 ⓪**）= `PASSED`

真机：`gen-local`（`http://localhost:3030/gen`）· 项目 = P164-c 的自建混凝土简支梁
（21 节点 / 20 单元 / 1 材料 / 1 截面 / 工况 `DL` / 有位移结果）· 全部为 `VIEW.*`（**不**动模型）。

| 步 | 动作 | 截图字节 | sha256（前 16） | 结论 |
| --- | --- | ---: | --- | --- |
| ① | 图形**全关** → `CAPTURE(SET_MODE=post)` | **33438** | `2e0296e8258d7556` | 基线 |
| ① | 同上（**重复**） | **33438** | `2e0296e8258d7556` | **噪声地板 = 0 字节**（渲染确定） |
| ② | `RESULTGRAPHIC(DisplacementContour)` → `CAPTURE(post)` | **81236** | `88fd9b48f2eca5db` | **改前 ≠ 改后**（**2.4×**） |
| ③ | `RESULTGRAPHIC(DeformedShape)` → `CAPTURE(post)` | **84494** | `174e64557e9d8521` | **换取值 ⇒ 画面真的换** |
| ④ | `RESULTGRAPHIC(DisplacementContour)` → `CAPTURE(post)` | **81236** | `88fd9b48f2eca5db` | **同取值可复现**（与 ② 逐字节相同） |
| ⑤ | 图形**全关** → `CAPTURE(post)` | **33438** | `2e0296e8258d7556` | **回到基线** |
| ⑥ | `RESULTGRAPHIC(A)` → `CAPTURE(**pre**)` | **32457** | `b9bc3c72f639c1b0` | **pre 模式画不出结果** |
| ⑦ | **阳性对照**：`DISPLAY(ELEM_NUMBER)` 开 → `CAPTURE(post)` | **40211** | `a269dd6886bcbc39` | — |
| ⑦ | 同上 关 → `CAPTURE(post)` | **33438** | `2e0296e8258d7556` | **仪器有效**（且等于基线） |

**7 / 7 满足** ⇒ `PASSED`。

⚠️ **②③④ 的截图内容**（人工核对）：图例（`MIDAS GEN NX` / `X-方向` / 色阶 / 系数）、
沿梁的等值线、节点位移值、`ST: DL`、最大 / 最小、文件名 / 单位 / 日期、视图方向立方体 ——
即**结果视图**；`DeformedShape` 的图例是「**变形形态**」（含 `组合 = 1.25E-03`）。
**⑥ 的截图**只有模型线（无图例）⇒ pre 模式确实**画不出**结果。

⚠️ **①（基线重复）是本批新增的必需项**：它把「字节差异一定有语义」从**假设**变成**实测**
（本批实测的噪声地板 = **0** 字节）。P164-f 曾观察到一次 **29 字节**的编码抖动
（`recon1` 的第一次 post 切换后），故**不能**假设「有差异 = 有语义」。

### 2.1 与 R157 的对照（**为什么当时是 FAILED**）

| 项 | P164-f（R157） | P166（R159） |
| --- | --- | --- |
| 请求体 | `CURRENT_MODE` + `LOAD_CASE_COMB` | 上面 **+ `TYPE_OF_DISPLAY`**（`OPT_CHECK: true`） |
| `CURRENT_MODE` | 表内取值（合法） | 表内取值（合法） |
| 状态码 | `200` | `200` |
| 截图 | **32023** 三次全同 | **33438 → 81236 → 84494 → 81236** |
| 判定 | ❌ FAILED | ✅ PASSED |

⇒ **`200` 从来不是问题，缺的是「把结果图形打开」的那个开关。**

---

## 3. 顺带的两条**离线**结论（**零请求**）

1. **`VIEW.SELECT` 不是「激活 / 选择结果视图」的入口**。手册
   （`MIDAS_API_Online_Manual_数据_v1.0.json` 的 `view/SELECT` 条目）只有
   `Input URI` / `Active Methods` / **`Response Examples`** 三节：**无请求体**
   （`methods: [GET]`）、**无 `specifications`**，唯一响应示例是
   `{"SELECT": {"NODE_LIST": [67, …], "ELEM_LIST": [92, …]}}`
   ⇒ 它是**读**「当前被选中的节点 / 单元编号表」的查询。已写进
   `registry/common/view/SELECT.yaml` 头部。
2. **`VIEW.DISPLAY` 与 post / result 无关**：它是**模型显示**（节点 / 单元 / 属性 / 边界 /
   荷载 / 视图 …）；结果方向的字段**只**在 `VIEW.RESULTGRAPHIC` 与
   `VIEW.CAPTURE.RESULT_GRAPHIC` 里。已写进 `registry/common/view/CAPTURE.yaml` 头部。

### 3.1 与外部证据（`docs/nxsdk_review`）的关系

`docs/nxsdk_review` 的 **D-19**（`/ope/GSBG`）记：
「先跑 `/doc/ANAL`，再试 `set_result_graphic()`（`/view/RESULTGRAPHIC`）—— 它本身成功，
但**没有**为 `GSBG` 清掉 `post mode` 门控。只有用户手动点 Civil NX GUI 的 `Post` 标签才行。
**本次会话没找到纯 API 进入该模式的路径。**」

**本批的更正（只改现状声称、不动历史记录）**：那句话在「**只调 `set_result_graphic()`**」
这条路上是**对的**；但他们**没试** `VIEW.CAPTURE` 的 `SET_MODE`（手册 `Capture #1` 的写法）
⇒ 本批补上了这一步，**路径存在**。⚠️ 注意：**结果图形只在 post 模式下渲染**，
所以「先 `SET_MODE: "post"` 再配图形」才是完整形态。

---

## 4. 交付物

| 项 | 内容 |
| --- | --- |
| 工具 | `registry/tools/probe_view_result_post.py`（默认**预演** / `--probe` 真机 / `--check` 离线自洽；**复用** `probe_view_result_modes.py` 的取值闸门与崩溃族自检） |
| 证据 | `registry/live/view_result_post_probe.json`（**只记字节数与 sha256**，不记图片内容；含七条判据 + 哨兵 + 成因） |
| 数据侧收口 | `registry/common/view/RESULTGRAPHIC.yaml`（`availability: untested → verified` + `verified_on: [gen-local]` + R159 记录；**R155 / R157 的历史记录原样保留**） |
| 数据侧记录 | `registry/common/view/CAPTURE.yaml`（`SET_MODE` / `RESULT_GRAPHIC` 的实测语义）· `SELECT.yaml`（**不是**激活入口） |
| 主指标 | `registry/tools/check_operation_availability.py`（`EXPECTED_AVAILABLE 61 → 67`、被挡清单 **10 → 4**） |
| 判定 | `tests/test_midas_view_result_post_p166.py`（**14** 项） |
| 同步更新的既有判定 | `tests/test_midas_operation_availability_p165b.py`（67 / 71 · 14 个挡点）· `test_midas_view_result_modes_p164d.py` / `test_midas_view_result_effect_p164f.py`（**只改现状声称**：`availability` 由 `untested` 改 `verified`，历史记录断言保留）· `test_midas_availability_p149c/p149e` · `test_midas_result_tables_p149d` · `test_midas_nxsdk_products_p161`（`verified 509 → 510` · `untested 104 → 103` · `NO_GET 103 → 102`） |
| 文档 | `README.md` §1 / §1.1 / §5.1 / §5.2 / §5.3 · `registry/README.md` **§8.20**（§8.19.5 加指针）· `docs/07` §15.5（下一批）/ §16.1 **R159** / §6.0 / §7.2 / §17.3 · `docs/08` §3 / §4 |
| `app/**` | **一行未改**（纯数据侧 + 探针 + 文档） |
| 实例 | 只发 `VIEW.*`（**视图类**：不改模型）+ **一次** `DOC.OPEN`（打开自建项目；跑后哨兵 6 项**逐项一致**） |

---

## 5. 闸门

```text
check_operation_availability --check   ✅ 主指标自洽：67 / 71（被挡 4 · 挡点端点 14）
probe_view_result_post --check         ✅ 离线自洽（七条件 + 与数据侧一致）
sync_manifest                          ✅ 差异 0（幂等；availability / verified_on 各 1 处已写回）
ruff check app tests                   All checks passed!
ruff format --check app tests          258 files already formatted
mypy app                               Success: no issues found in 185 source files
pytest -q                              ✅ 1390 passed / 11 skipped / 0 failed
                                       （P165-b 基线 1375 ⇒ +14 = P166 的判定用例）
```

⚠️ `pytest -q` 必须先把 `TEMP` / `TMP` 指到**可写**目录（本会话 `%TEMP%` 不可写 ⇒ 见 §6）。

---

## 6. ⚠️ 顺带查清的一处**既有环境缺陷**（**与本批无关**，已给出可用口径）

本会话第一次跑 `pytest -q` 时出现 **1** 项失败：

```text
FAILED tests/test_mcp_p37_p39.py::test_idempotency_key_is_passed_through_and_replay_semantics_are_explicit
       sqlalchemy.exc.PendingRollbackError ... Original exception was:
       (sqlite3.OperationalError) unable to open database file
```

### 6.1 成因（**已定案，可复现**）

**`%TEMP%`（`C:\Users\<user>\AppData\Local\Temp`）在本会话**不可写**：
Python 在那里 `mkdir` ⇒ `PermissionError`；`tempfile.gettempdir()` 因此**回落到当前工作目录**
（pytest 的临时根变成仓库内的 `pytest-of-lkxlz/`）。
而 **SQLite 需要可写的临时目录**（WAL / 临时文件）⇒ 打开**已存在**的库时返回
`SQLITE_CANTOPEN`（`unable to open database file`）。

### 6.2 判据（**不是**猜测）

| 实验 | 结果 |
| --- | --- |
| 把本批**全部**改动（含未跟踪文件）`git stash -u` 后，在**未改动的树**上单跑该用例 | ❌ **同样失败、同一条报错** ⇒ **与本批无关** |
| 同一次运行里的 `tests/test_e2e_p42_p48.py::test_definition_of_source_complete_items_are_executable` | ✅ **通过** |
| 排除「路径长度」（pytest 的 `tmp_path` 目录名） | ❌ 用短 `--basetemp` 仍失败 |
| 排除「时序 / 连接未关」 | ❌ 在 `_seeded_runtime` 后 `await asyncio.sleep(1.0)` 仍失败 |
| **把 `TEMP` / `TMP` 指到一个可写目录后重跑** | ✅ **通过** |

### 6.3 可用口径（**本批采用的验收口径**）

```powershell
$env:TEMP = "E:\MCP\MMCP\.tmp_p164c\pytest_temp"; $env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
.\.venv\Scripts\python.exe -m pytest -q
```

⇒ 该口径下 **全绿**（见 §5 的闸门输出）。
⚠️ 本批**不**为了让数字好看而放宽或跳过任何判定 —— 这是**环境**问题，
**不是**判据问题；`TEMP` 不可写时**如实**报出失败，**不**声称全绿。

---

## 7. 仍未闭环（**不在我方手上**）

| 项 | 需要什么 | 风险 |
| --- | --- | --- |
| **数据侧**：补全 `VIEW.RESULTGRAPHIC` 的请求 Schema（**36** 个变体：`CURRENT_MODE` 枚举 + 各变体的兄弟键） | **产品裁决**（**R155**；规模不小） | 无（纯数据） |
| **主指标剩余 4 个 Operation** | 3 个要 **MIDAS 侧**修 `wg_db.dll`（**R154**）；1 个是 `POST.STEELCODECHECK`（**R152**：单独收口不解锁） | — |
| `POST.TABLE`（**R151**） | **数据侧裁决**：`TABLE_TYPE` 枚举的来源换成可复算的登记表（同时保住 **R140** 的保护）⇒ 解锁 `RESULT.ANALYSIS.SUMMARY`（**+1 ⇒ 68 / 71**） | 无（纯数据 + 一次真机取表） |
