# P164-c 报告（分块 2）：`DESIGN.CONCRETE` —— **原生崩溃，判定为产品缺陷（留缺）**

> 批次：**P164-c**（真机验证批）｜ 状态：🛑 **分块 2 中止（留缺）—— 已加硬性护栏**
> 实例：`gen-local`（GEN NX，`http://localhost:3030/gen`）· **MIDAS Gen NX 26.9.1.1001**
> 授权：用户授权用 API 新建项目（`DOC.NEW` + `DOC.SAVE_AS`）
> 纪律：**铁律 ⓪**（判据 = 效果）· 哨兵跑前/跑后 · 只碰自建项目
> ⚠️ **2026-10-14 21:12:30 第 4 次崩溃后补记**（含**肇事命令**与**已落地的护栏**，见 §2.1 / §2.2）

---

## 0. 一句话结论

1. ✅ **前置全部成功**：新建空项目（**文件真的落盘**）· 混凝土简支梁 **10/10 步效果确认** ·
   静力分析跑通（`DISPLACEMENTG` 取到 **63 行**）。
2. 🛑 **`DESIGN.CONCRETE` 无法完成**：`BD-ANAL` 让 **MIDAS Gen NX 崩溃**
   （**四次**，**字节级完全相同**：`wg_db.dll` / `0xc0000005` / `@0x2d97e5c`）。
3. 🔴 **判定 = 产品缺陷，不是我方的请求问题** —— 四次的请求体**各不相同**
   （含**手册 `BD-ANAL` 文章的逐字示例**），崩溃**位置一模一样**。
   ⇒ **我方无法规避、无法修复** ⇒ 记为 **留缺**。
4. ✅ **但「不再打崩用户软件」是我方能做的、且已经做了**：新增**原生崩溃护栏**
   （`guard_native_crash`）—— 该端点族现在**在发请求之前**被拦死（**零请求**），
   除非显式 `allow_native_crash_risk=True`。见 §2.2。
5. ⚠️ **`availability` 一行未改**（`BD-ANAL` / `BD-TABLE` 仍 `untested`）—— 没有成功实测，
   **不**升级。
6. ✅ **顺带修掉一个**真实**的接口层缺陷**（R154：`*-ANAL` 步缺转换器）—— 但它**不足以**让
   `BD-ANAL` 跑通（见 §4）。

---

## 1. 做了什么（分块 2 的完整过程）

| 步 | 内容 | 判据（**铁律 ⓪**） | 结果 |
| --- | --- | --- | --- |
| 1 | `DOC.NEW`（**不带**路径，P160c/R144） | **不弹窗** ⇒ 后续请求仍可发 | ✅ `GET /DB/NODE` → `200` |
| 2 | `DOC.SAVE_AS`（带路径 `.tmp_p164c/p164c-concrete.mgbx`） | **文件真的落盘** | ✅ **24 762 字节** |
| 3 | 哨兵 | 模型**全空** | ✅ 全 0 |
| 4 | 建**混凝土简支梁**（10 步，**照官方手册附件**） | 每步**读回**条目数 | ✅ **10/10** |
| 5 | 静力分析 `DOC.ANAL` + **有界等待**（R135） | 结果表**行数 ≥ 1** | ✅ **63 行** |
| 6 | `DESIGN.CONCRETE`（**接口层**） | `BD-TABLE` **结果行数** | 🛑 **原生崩溃** |

**建模型用的取值**（**逐字照**官方手册附件
`E:\MCP\MAPI\docs\assets\du5V1xsR59aMYTmMdgdmbe_Gen_Simple_Beam.py`，**不**臆造）：

```text
单位 M / KN · 梁长 10.0 m · 高 1.0 m · 宽 0.8 m · 均布 -30 kN/m
材料 TYPE=CONC · STANDARD="AS17(RC)" · DB="C32"
截面 SECTTYPE=DBUSER · SHAPE="SB" · DATATYPE=2 · vSIZE=[1.0, 0.8]
21 节点 / 20 单元 · 边界 node1="1111000" · node21="0111000"
工况 DL / SIDL · 自重 FV=[0,0,-1] · 组合 Comb1 = 1.2 DL + 1.5 SIDL
```

⚠️ **附带发现（安全）**：那份手册附件**第 7 行硬编码了一把 MAPI key**
（`api-beta.midasit.cn`，用户 `libin200`），与 `~/.structai/midas-test.env` 里的三把**都不同**。
**未**复制进仓库；建议轮换。

---

## 2. 🔴 崩溃证据（**四次，字节级相同**）

```text
Windows 应用程序日志（Application Error 1000 / WER 1001）：

21:12:30  GenNX.exe 26.9.1.1001  wg_db.dll 1.0.0.1  c0000005  offset=0x2d97e5c   ← 第 4 次
20:58:20  GenNX.exe 26.9.1.1001  wg_db.dll 1.0.0.1  c0000005  offset=0x2d97e5c
20:47:15  GenNX.exe 26.9.1.1001  wg_db.dll 1.0.0.1  c0000005  offset=0x2d97e5c
20:05:04  GenNX.exe 26.9.1.1001  wg_db.dll 1.0.0.1  c0000005  offset=0x2d97e5c
```

**四次的请求体各不相同**：

| # | 请求体 | 性质 |
| --- | --- | --- |
| ① | `{"Argument": {"perform_type": "ALL", "elements": [...], "sections": null}}` | **小写 canonical 键**（转换器缺失导致，见 §4） |
| ② | `{"Argument": {"PERFORM_TYPE": "ALL", "ELEMS": {"KEYS": [...]}}}` | 键已修对，但 `ALL` 与 `ELEMS` **自相矛盾** |
| ③ | `{"Argument": {"PERFORM_TYPE": "ELEMS", "ELEMS": {"KEYS": [1..20]}}}` | **手册 `BD-ANAL` 文章的逐字示例形状** |
| ④ | `{"Argument": {"PERFORM_TYPE": "ELEMS", "ELEMS": {"KEYS": [1..20]}}}` + **抗震关闭** | ③ 的形状 + **关掉 `seismic_prov`**（当时假设 = 抗震配置缺失）⇒ **照样崩** |

⇒ **第 ④ 次把最后一个「我方参数」假设也排除了**：崩溃**与请求体无关**。

**⇒ 四种体、同一个崩溃偏移 ⇒ 崩溃与请求体无关。**

**故障模块 `wg_db.dll` 是 98.6 MB 的模型数据库模块** ⇒ 崩溃发生在设计引擎**读模型数据**时。
`GenNX.exe` 26.9.1.1001 在 `wg_db.dll` 里**有崩溃前科**（2026-10-10 三次，偏移 `0x1254da`）。

### 2.1 🎯 肇事命令（第 4 次崩溃，2026-10-14 21:12:30）

**我在上一会话里发出的、把 MIDAS 打崩的那一条 `pwsh`**（逐字）：

```powershell
cd E:\MCP\MMCP
$py="E:\MCP\MMCP\.venv\Scripts\python.exe"
$env:PYTHONUTF8='1'
. .\scripts\load-midas-env.ps1 -Instance gen | Out-Null
$ErrorActionPreference='Continue'
& $py ".tmp_analysis\p117_reopen.py" --write 2>&1 | Select-Object -Last 2
& $py ".tmp_analysis\p115_design_concrete.py" --write 2>&1 | Select-String "design_option|success=|task=|结果 data|error" | Select-Object -First 8
```

* `p117_reopen.py --write` = `POST /DOC/OPEN`（**无害**：模型指纹读回 **一致 ✅**）。
* **`p115_design_concrete.py --write` = 肇事者** —— 它经**接口层**跑 `DESIGN.CONCRETE`，
  最后一步落到 **`POST /DESIGN/RC/KDS-41-20-2022/BD-ANAL`**。
* 实际发出的请求体（`_design_arguments()` → `midas.design.rc-anal.v1`）：
  `{"Argument": {"PERFORM_TYPE": "ELEMS", "ELEMS": {"KEYS": [1..20]}}}`。
* 接口层**如实**回报：`task.status = FAILED` · `STRUCTAI-2000 transport_error` ·
  `details.endpoint = /DESIGN/RC/KDS-41-20-2022/BD-ANAL` · `stage = midas_adapter`
  （证据：`.tmp_p164c/design_concrete_result.json`）—— 但**那时用户的 MIDAS 已经没了**。

⚠️ **这就是「命令 vs 后果」的关键**：链路层看到的是「连接断了」（`transport_error`），
**看不出**「宿主进程被我们发的请求打崩了」。⇒ 判据**不能**只看链路错误码，必须**核对
Windows 事件日志**。

### 2.2 ✅ 已落地的护栏（**本报告之后新增；事故驱动**）

`app/infrastructure/adapters/midas/`（`client.py` · `errors.py` · `adapter.py`）：

| 项 | 内容 |
| --- | --- |
| `NATIVE_CRASH_MEASURED` | **恰好 1 个**：`DESIGN.RC.KDS-41-20-2022.BD-ANAL`（**实测**） |
| `NATIVE_CRASH_ENDPOINTS` | 上面那个 **+ 10 个同族推定** = **11** 个（`DESIGN.RC.*` 的 **8** 个 `*-ANAL` + `DESIGN.SRC.AIK-SRC2K.{BC,CC}-ANAL`） |
| `guard_native_crash()` | 在 `build_request()` 里、**发请求之前**拒绝 ⇒ **零请求** |
| `guard_native_crash_path()` | 挂在**唯一的发送汇合点** `_raw()` 上（见 §2.3） |
| 异常 | `MidasNativeCrashRisk`（`STRUCTAI-1200`，`details.reason = native_crash_risk`，带 `measured`） |
| 开关 | `allow_native_crash_risk`（`MidasAdapter` / `build_request` / 裸请求方法），**默认 `False`** |

**覆盖口径（可复算，**同族全查**）**：`registry/manifest.json` 里**恰好 12** 个 `*-ANAL` 端点 ——
本名单收 **11** 个，**唯一**排除的是 `DESIGN.STEEL.KDS-41-30-2022.CODE-ANAL`
（它在旗舰链里**真机实测 12/12 跑通** ⇒ 拦它 = **过度**防护、会把能用的功能关掉）。

⚠️ **第一版只拦了 6 个（漏了 5 个）**：`DESIGN.RC.*` 的 **校核**族
（`BC` / `CC` / `BRC` / `WC` / `HCD-ANAL`）**同原生模块、同调用形态**却被漏在外面 ——
那 5 个**没进任何 Operation 的编排**，所以「按编排查」查不出来，**只有按 manifest 全量查**
才发现。⇒ 现在覆盖口径由**用例**对着 manifest **逐条复算**
（新增一个 RC/SRC 的 `*-ANAL` ⇒ **用例先红**，不允许静默漏拦）。

⚠️ **为什么把「推定」也拦上**：`allow_unverified=True`（Contract Test 口径）**放不开**这道护栏
—— 两者是**不同**的事（「没验过」≠「验出会崩」）。**代价不对称**：误拦的代价是少一次真机验证，
漏拦的代价是**把用户正在用的软件打崩**。同族推定的 `measured=False` **如实标在 `details` 里**。
⚠️ 这 11 个端点**全部**是 `untested` ⇒ 生产路径**本来**就被 `registry_mapping_not_verified` 挡住
⇒ 本护栏实际只收紧**探针**那条路 —— 那正是打崩 MIDAS 的那条路。

判定：`tests/test_midas_native_crash_guard_p164c.py`（**30** 项，含「第 ④ 次事故现场复现」）。

### 2.3 ⚠️ 修复过程中**又发现一个缺口**：护栏**可被绕过**（**已闭合**）

**发现**：`guard_native_crash()` 只挂在 `build_request()` 上，而 `MidasHttpClient` 还有**裸**的
`post` / `put` / `delete` / `get` / `probe` / `probe_payload` —— 它们**直接走 `_raw`**、
**不**经过 `build_request`。⇒ 修复前，一句

```python
await client.post("/DESIGN/RC/KDS-41-20-2022/BD-ANAL", json_body={"PERFORM_TYPE": "ELEMS"})
```

**照样能把 MIDAS 打崩**，第一版护栏**形同虚设**。

**闭合方式**（不是「再挂一处」，而是挂到**结构上的唯一汇合点**）：

| 点 | 内容 |
| --- | --- |
| 位置 | `MidasHttpClient._raw()` —— `build_request → send → _request → _raw` **与** 裸方法 `→ _request / _raw` **都**经过它 |
| 判定 | `guard_native_crash_path(path)`：按**路径**匹配（裸方法拿不到端点键） |
| 路径来源 | `native_crash_paths()` 由端点键**机械推导**（`.` → `/`）—— **不**再抄一份字面量（两处字面量必然漂移）；并有**逐条对齐 `registry` 实际 `uri`** 的用例防漂移 |
| 归一化 | 去空白 / 去尾部斜杠 / **忽略大小写**（探针常手写路径） |
| 为什么不分方法 | 这 6 个端点的 `methods` **只有 `POST`**（无读语义）⇒ 对该路径的任何流量要么是会打崩的那个 `POST`、要么本身无意义 |
| 判据 | **零请求**：护栏拦在**取凭据之前**（用例用「计数凭据」证明 `get_secret` **一次都没被调用**） |

⚠️ **仍然存在的边界（如实说明）**：`.tmp_analysis/` 与 `registry/tools/probe_*.py` 里的一次性脚本
**自带 `httpx.Client`**（不走 `MidasHttpClient`）⇒ 护栏**管不到**它们。这类脚本只能靠
**纪律**（如 `p115` 已加 `--i-know-this-crashes-midas` 硬性开关）与**代码评审**把关。

---

## 3. 判定：**产品缺陷 ⇒ 留缺**

**依据**（`docs/07` §16 的留缺口径：实测不通且**我方无法规避** ⇒ 如实留缺、**不**硬凑）：

1. **请求体不是变量** —— **四次**不同的体（含手册逐字示例、含关掉抗震的变体）崩溃位置完全相同。
2. **不是我方代码路径的问题** —— 崩溃在**原生 DLL** 的**访问违例**，不是 `4xx` 业务拒绝。
3. **不是模型数据的问题（至少不是显然的）** —— 模型按官方手册附件逐字建成，
   10/10 步读回确认；分析结果可读（63 行）。
4. **我方无规避手段** —— 不能改 `wg_db.dll`；也不该为了"绕过"而臆造别的请求形状
   （那正是 R101–R110 的留缺口径要防的）。
5. ⚠️ **但我方能做的是「不再打崩用户软件」** —— 已落地 `guard_native_crash`（§2.2）。
   **这不等于**该端点可用：**留缺**的判定**不**因护栏而改变。

**⇒ 记录为留缺**：`DESIGN.RC.KDS-41-20-2022.BD-ANAL` 及其**同族**（`CD/BRD/WD-ANAL`、
`DESIGN.SRC.AIK-SRC2K.{BC,CC}-ANAL`）**无法在我方实例上验证**。
`availability` **保持 `untested`**（**不**升级、**不**降级）。

⚠️ **对主指标的影响**：`DESIGN.CONCRETE` 与 `DESIGN.SRC` 两个 Operation
**仍**在"生产路径会被挡"的 **9** 个里（生产可用 Operation 仍是 **62/71**）。
⇒ 若要把它们变成可用，**必须**先由 **MIDAS 侧**修掉 `wg_db.dll` 的崩溃。

---

## 4. ⚠️ 顺带修掉的**真实**接口层缺陷（R154）—— 但它**不足以**解决问题

**在排查崩溃的过程中**发现并修了一个**客观存在**的缺陷（**与崩溃本身无关**）：

**缺陷**：`DESIGN.CONCRETE` / `DESIGN.SRC` / `DESIGN.CODE_CHECK` 的 `*-ANAL` 步
**没有转换器**（`transformer=None`），而 `DESIGN.STEEL` 的同形步**有**
（`midas.design.steel.v1`）。`transformer=None` 时 `_arguments_step` 会把
`_design_arguments()` 产出的**小写 canonical 体原样**发出去，而原生要 `PERFORM_TYPE` / `ELEMS.KEYS`。

**修复（7 处）**：

| # | 位置 | 修复 |
| --- | --- | --- |
| 1 | `DESIGN.RC.KDS-41-20-2022.BD-ANAL` | + `midas.design.rc-anal.v1` |
| 2 | `DESIGN.RC.KDS-41-20-2022.CD-ANAL` | + `midas.design.rc-cd-anal.v1` |
| 3 | `DESIGN.RC.KDS-41-20-2022.BRD-ANAL` | + `midas.design.rc-brd-anal.v1` |
| 4 | `DESIGN.RC.KDS-41-20-2022.WD-ANAL` | + `midas.design.rc-wd-anal.v1`（**字段不同**：只有 `SELECTIONS`） |
| 5 | `DESIGN.SRC.AIK-SRC2K.BC-ANAL` | + `midas.design.src-anal.v1` |
| 6 | `DESIGN.SRC.AIK-SRC2K.CC-ANAL` | + `midas.design.src-cc-anal.v1` |
| 7 | `DESIGN.SRC.AIK-SRC2K.DSRC` | `intent="design"`/`None` → **`write_design_code`** + `midas.design.src-code.v1`（与 `DESIGN.RC.DRC` 对齐） |

**另加两道结构性防护**（**事故驱动**）：

* `intent=design` 而**无转换器** ⇒ **发请求前**明确失败（`design_transformer_missing`）。
* `PERFORM_TYPE` 与目标选择**不一致**（如 `ALL` + `elements`）⇒ **发请求前**明确失败
  （`design_target_conflict`）—— 手册把 `ALL`/`ELEMS`/`SECTIONS` 定义得很清楚，
  自相矛盾的请求**不该**发给原生设计引擎。

⚠️ **诚实边界**：**这两道防护与 7 个转换器都救不了 `BD-ANAL`** ——
第三次实测用的就是**修好之后**的、**手册逐字形状**的体，**照样崩溃**。

**回归**：`pytest -q` **1315 passed / 11 skipped / 0 failed**；
`ruff check` / `ruff format --check` / `mypy app` 全绿；
`sync_manifest` 幂等（差异 0）。

---

## 5. 残留与清理

| 项 | 状态 |
| --- | --- |
| 项目文件 | `.tmp_p164c/p164c-concrete.mgbx`（68 KB）+ 崩溃恢复文件（**都在 `.gitignore` 内**） |
| 模型 | **21 节点 / 20 单元 / CONC C32 / 矩形 / DL+SIDL / Comb1**（**未**清理 —— 留作后续复现用） |
| 分析结果 | 存在（63 行位移） |
| `DESIGN/RC/DRC` 等设计配置 | 由 `DESIGN.CONCRETE` 的配置步写入（`PUT` 全部 `200`） |
| 用户 MIDAS 进程 | ⚠️ **崩溃 4 次**（20:05 / 20:47 / 20:58 / **21:12:30**），每次需用户手动关掉弹窗 |

⚠️ **我不再重试 `BD-ANAL`。** 现在**代码层面**也拦住了：`guard_native_crash` 会在
**发请求之前**抛 `MidasNativeCrashRisk`（**零请求**）。要重跑**必须**显式
`allow_native_crash_risk=True`，**且**先取得用户对「会打崩他的 MIDAS」的明确同意。

---

## 6. 下一步建议

1. **向 MIDAS 报缺陷**：`GenNX.exe 26.9.1.1001` · `wg_db.dll` · `0xc0000005` @ `0x2d97e5c`，
   触发 = `POST /DESIGN/RC/KDS-41-20-2022/BD-ANAL`（含**手册逐字示例体**）。
   **最小复现**：手册附件的 10 步建一个混凝土简支梁 → 分析 → `BD-ANAL`。
2. **把 `BD-ANAL` 家族登记为留缺**（`registry/README.md` 的留缺账本），
   `availability` 保持 `untested`。
3. **主指标不变**（生产可用 Operation **62/71**）—— 这两个 Operation 的解锁**依赖 MIDAS 侧**。
4. **转去啃 `VIEW.RESULTGRAPHIC`**（+6 Operation，**纯我方工作**、不需要 MIDAS 改代码）。
