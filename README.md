# StructAI MCP Server

> 仓库：`github.com/lkxlzx/StructAI-MCP-Server`

MIDAS Open API 的**机器可读端点注册表（Endpoint Registry）**与配套开发文档、参考实现。

本仓库是 StructAI **多结构工程软件一体化 MCP（Model Context Protocol）Server** 的**知识层**：
把 MIDAS 官方手册（Help Center JSON API、Civil NX 手册、Civil Designer 手册、GitHub 韩文整理版）
交叉合并为可直接被程序加载的 Registry，并用**真实 MIDAS 实例**逐端点实测验证。

---

## 0. 🔴 会话边界（硬性原则）

**一个批次 = 一个会话。**

每完成 `docs/07` §12 的一个批次（P01 / P02 / …），**必须新建对话**，
不得在同一窗口继续下一批 —— 否则上下文超长会稀释架构红线等早期约束。

- 完整规则 / 交接协议 / 批次状态表 / **可复制的续接提示词**
  → **`docs/08_会话交接与续接提示词_v1.0.md`**
- **每个新会话的第一个入口就是 `docs/08`**；不要重读 `docs/01`–`06` 全文（90.5 万字符）

---

## 目录

```
registry/          Endpoint Registry（663 端点定义 + 652 JSON Schema + 索引 + 实例矩阵）
examples/          参考客户端与冒烟测试（midas_client.py / smoke_test.py / cases.json）
app/               Core 实现（P01 起逐步落地；进度见 docs/08 §3）
pyproject.toml     依赖与工具链配置（冻结于 docs/07 §3.1–§3.2）· .env.example 环境变量样例
docs/              V2 规范 01–06 + 通读报告 00 + 开发方案 07   ← 唯一开发依据
archive/legacy_v1/ 非规范性历史资料（V1 文档与实测留痕，不作依据）
MIDAS_API_*.md     MIDAS 官方手册整理（外部厂商资料）
```

---

## 1. Registry

| 指标 | 数值 |
| --- | --- |
| 端点定义 | **663** |
| JSON Schema | **652**（98.3%） |
| 命名空间 | `DB`(**271**) / `POST`(199) / `DESIGN`(125) / `OPE`(34) / `DOC`(21) / `VIEW`(7) / `OPRT`(6) |
| 覆盖产品 | `GEN_NX` / `CIVIL_NX` / `CIVIL_DESIGNER` |
| 实测实例 | 3 个（本地 GEN NX、云 CIVIL NX、云 Civil Designer） |

字段与用法见 [`registry/README.md`](registry/README.md)。

**实测验证状态**（`availability`）：`verified` **514** · `unverified` **23** · `untested` **126**。

> ⚠️ **P176 / R168**：`verified` **+2**（`DOC.EXPORT` / `DOC.IMPORT` 真机收口）· `untested` **+27**（「导出可见但未登记」的表补登，**方法集未逐表实测** ⇒ 如实留在 `untested`）。

### 1.1 主指标：**接口层端到端**（`docs/07` §15.6.3）

> ⚠️ **`availability` 是端点级、**次**指标**。产品对外的单位是 **Operation**，
> 故主指标是**接口层端到端**与**生产路径可用 Operation**（`docs/07` §15.6.3）。

| 层级 | 指标 | 当前 |
| --- | --- | --- |
| 🔴 主指标 | 接口层写路径端到端 | **`13 / 13 PASSED`** |
| 🔴 主指标 | 接口层读路径端到端 | `2 PASSED + 7 PARTIAL + 6 FAILED`（15 条） |
| 🔴 主指标 | 旗舰五步链（`docs/07` §13.5）**生产口径** | **`12 / 12 PASSED`**（⚠️ **阶段 B**：`BUILD.COLUMN` 仍 `FAILED`，①′ 用 §6.5 的原子 Operation 替代；见 `flagship_chain_probe.json` 的 `substituted_*`） |
| 🔴 主指标 | **生产路径可用 Operation** | **`71 / 73`**（缺口 = **4** 个端点 → **2** 个 Operation） |
| 🟡 次指标 | 数据侧可达性上限（`write_path_coverage()`） | `72 / **660**` |
| ⚪ 账本 | 映射缺口 / 留缺账本 | `514` / `178`（**只登记，不驱动优先级**；缺口 `487 → 514` 见 **R168**） |

证据 = `registry/live/{interface_path_probe,interface_read_probe,flagship_chain_probe}.json`；
生成器 = `registry/tools/probe_interface_paths.py` / `probe_flagship_chain.py`（均可 `--check` 离线复算）。

> ⚠️ **R158（P165-b 更正）**：主指标**不再手写** —— 它由
> `python registry/tools/check_operation_availability.py --check` **可执行复算**。
> 旧值 `62 / 71`（「6 个端点 → 9 个 Operation」）**是错的**：它把 `DESIGN.CODE_CHECK`
> 算成可用，而该 Operation 的 **7 条路由全部被挡**（`steel` 的末步
> `POST.STEELCODECHECK` 仍是 `PARTIAL`；`concrete:*` / `src:*` 需**原生崩溃护栏**拦住的
> `*-ANAL`）。⇒ R158 的真实值 = `61 / 71`、挡点端点 **15** 个。**手写的指标必然漂。**

> ⚠️ 上表「接口层读路径端到端」是 **P153 的基线**（在**空**专用项目上测得 ⇒ 取报表族
> **必然** `FAILED`：原生回 `400 "[empty] Cannot generate table data…"`）。
> ✅ **P167 / R160** 在**有分析结果**的自建项目上**另测**了一次生产路径（见 §5.1）——
> 两处**判据不同、项目不同**，**不**互相覆盖。

> ✅ **R159（P166 收口）**：**单点最大杠杆** `VIEW.RESULTGRAPHIC` 已收口 ——
> 找到**纯 API 进结果视图（post）**的路径（成因 = 原请求体**缺 `TYPE_OF_DISPLAY`**；
> `TYPE_OF_DISPLAY.<子块>.OPT_CHECK = true` 才是把结果图形打开的开关），
> 效果判据 **7 / 7 PASSED**（`33438` → **`81236`** 字节；换 `CURRENT_MODE` → `84494`；
> 阳性对照 `40211` vs `33438`）⇒ `untested → verified` ⇒ 它挡住的 **6** 个 `VIEW.*`
> Operation **解锁** ⇒ 主指标 `61 / 71` → `67 / 71`（被挡 **10 → 4** · 挡点端点 **15 → 14**）。
> 证据 = [`registry/live/view_result_post_probe.json`](registry/live/view_result_post_probe.json)；
> 生成器 = [`registry/tools/probe_view_result_post.py`](registry/tools/probe_view_result_post.py)（可 `--check` 离线复算）。

> ✅ **R160（P167 收口）**：`POST.TABLE` 的 `TABLE_TYPE` 枚举**来源**从「help center 一篇文章的
> `json_schema`（**2** 个取值）」换成**两个可复算来源的并集** —— ① `registry/manifest.json` 里
> 已登记的 `POST.TABLE.*` 端点取值（**194**）∪ ② 上游手册全部 `json_schema` 声明的
> `TABLE_TYPE.enum`（**121**）= **225**（**严格包含**旧枚举 ⇒ **只增不减**）。
> 效果判据 **PASSED**（原生 `POST /POST/TABLE {TABLE_TYPE: "DISPLACEMENTG"}` ⇒ **`200`** ·
> `HEAD` **9** 列 · `DATA` **63** 行；经 MCP Tool 契约的规范化结果 `rows` = **63**；
> 伪 token **零请求**仍被 `spec_guard` 拦）⇒ `untested → verified` ⇒ 它挡住的 **1** 个
> `RESULT.ANALYSIS.SUMMARY`（**通用取表入口**）**解锁** ⇒ 主指标 `67 / 71` → **`68 / 71`**
> （被挡 **4 → 3** · 挡点端点 **14 → 13**）。
> 证据 = [`registry/live/post_table_enum_probe.json`](registry/live/post_table_enum_probe.json)；
> 生成器 = [`registry/tools/probe_post_table_enum.py`](registry/tools/probe_post_table_enum.py)（可 `--check` 离线复算）；
> 枚举生成器 = [`registry/tools/sync_table_type_enum.py`](registry/tools/sync_table_type_enum.py)（`--check` 断言「已落盘 == 机械结果」）。

> ✅ **R161（P168 收口）**：**枚举**来源普查**抓到一件比「某个枚举太窄」严重得多的事** ——
> `spec_guard`（**R140**）对 **104 / 225** 个「带枚举约束」的 Schema 文件**一个字段都不检查**
> （`registry/schema/**` 有 **393 / 625** 个文件的**根键就是包装键**，而闸门的下钻约定是
> `schema["properties"][包装键]`）⇒ **盲区**。
> 修法 = **核心 1 行**（**用户已授权**）：`adapter._build` 的 `spec_guard` 由
> `registry.schema_json(key)` 改用 **`registry.effective_schema(key)`**（P09 的 `unwrap_schema()`）
> ⇒ 可下钻 **121 → 225**（**盲区 `104 → 0`**，已可见的 **121** 个**零回归**）。
> ⚠️ **可见性是放大器**：恢复后**窄枚举立刻变成「拦住合法调用」的事故** ⇒ 同批**先补枚举**：
> **①** `VIEW.RESULTGRAPHIC` 的 `CURRENT_MODE`（**R155** 留缺的**缺枚举**）补 **36** 个取值；
> **②** **6** 个变体端点的 `TABLE_TYPE`（**来源太窄**）追加**登记表的 token**。
> 效果判据 **PASSED**（**6 / 6** 个登记 token 原生 **`200`**；`RESULT.NODE.DISPLACEMENT` 经生产路径
> 取到 **63** 行 ⇒ **真的**走了变体文件的枚举；合法 `CURRENT_MODE` 真的发出去且三张截图
> **32023 → 79969 → 83282** 字节**两两不同**；**非法** `CURRENT_MODE` **零请求**被拦）。
> ⚠️ **主指标 `68 / 71` 不变** —— 本批的价值在**防事故**（R140 的目的），**不**在抬主指标。
> 证据 = [`registry/live/spec_enum_audit.json`](registry/live/spec_enum_audit.json)（普查）·
> [`registry/live/spec_enum_probe.json`](registry/live/spec_enum_probe.json)（真机）；
> 工具 = [`registry/tools/check_spec_enums.py`](registry/tools/check_spec_enums.py)（四分类 + 三标志 + 台账，`--check` 零请求）·
> 生成器 = [`registry/tools/sync_result_graphic_modes.py`](registry/tools/sync_result_graphic_modes.py) ·
> [`registry/tools/sync_table_type_variant_enum.py`](registry/tools/sync_table_type_variant_enum.py)。

> ✅ **R169（P176 收口）—— 设计规范是**运行时数据**，不是接口层的常量**：
> 接口层原先写死了「生效规范 / 配置端点的字段集 / 材料库名」。根因是**设计规范三处必须同族** ——
> `DRC.DGNCODE`（规范码）· `MATL.STANDARD`（**材料库名**，如 `GB/T10(RC)`，**不是**规范码）·
> `MDGN.CONC_CODE`（配筋材料码）；**只切一处** ⇒ 引擎跳过**所有**单元
> （⚠️ **不崩**，只是 `400 failed:LoadCombination` + `*-TABLE` **0 行**）。
> 三条实测事实：**①** 路径段是**固定路由名**（`/design/RC/GB-T50010-10/DCO` → **`404`**）
> ⇒ 规范码**不能**进 URI，切换只能靠 `DRC.DGNCODE`；**②** 配置端点字段集**随规范变化**
> （KDS **12/13**、`GB/T50010-10` **0**），而 `GET /info/...` 在两种规范下**返回同一份 13 字段**
> ⇒ **自省不能作来源**，只能实测（`registry/live/design_code_field_sets.json`）；
> **③** `DCO` 可选（为空时设计链照常跑通）。
> ⇒ 主指标 **`71 / 73` 不变**（本批**不**改任何裁定）—— 价值在**去硬编码**与**归因更正**
> （推翻 P164-c 的「`BD-ANAL` 必崩」：同 build 实测**不崩**且设计**真的产出**）。
> ⚠️ 新登记 **R170**：`spec_guard` 对 `patternProperties` 下的枚举**一个都不检查**
> （**21** 个文件 / **90** 个枚举节点 **100% 盲区**；两相对照：`DESIGN.RC.DRC` 的
> `DGNCODE="TOTALLY-BOGUS"` **不拦**，同一取值在 `OPE.LCOM-CONC` **拦**）。
> ✅ **P178 已收口**（**R171**）：盲区 **21 文件 / 90 节点 → 0**；修完后闸门**第一次**
> 看见 **6** 条既有窄枚举 ⇒ **2** 条已补（`DB.SWIND` / `DB.SSEIS` 的 `USER TYPE`）、
> **4** 条**如实留缺**（钢筋规格「D4~D57」手册无完整表；`HOOP_TYPE` 整数/字符串冲突）。
> 细节 = [`registry/README.md`](registry/README.md) §8.31 / §8.32 · `docs/07` §16.1
> **R169** / **R170** / **R171**。

> ✅ **R166（P174 收口）**：`POST.STEELCODECHECK` **真机实测收口** ⇒ 它挡住的
> **`DESIGN.CODE_CHECK`**（钢铁路由）**解锁** ⇒ 主指标 `68 / 71` → **`69 / 71`**
> （被挡 **3 → 2** · 挡点端点 **13 → 4**）。
> **判据 = 效果**（铁律 ⓪，**不**是状态码）：**同一个**请求体（空体 `{}`）——
> **无设计结果**时 **0 行** · `CODE-ANAL` 跑完后 **2 行**（根键 `vSECT` / `vELEM`）
> ⇒ 输出**真的**跟着设计状态走；**防回显**（**R157** 的仪器有效性）：取值
> `ELEM 1 / RAT 8.0846`，而手册 `json_schema` 示例是 `ELEM 10 / RAT 0.6119`、本模型**没有**
> 单元 `10` ⇒ **不**是 schema 回显。
> ⚠️ **本端点对 `Argument` 完全不敏感**：空体 / 自名 `TABLE_TYPE` / **逐字照** `CODE-TABLE` /
> **伪**取值，四者答复**逐字节同形** ⇒ 「坏取值被拦」这一形态的阴性对照**结构上不可用**
> ⇒ 改用**状态对照**（如实记录，**不**硬凑假对照）。
> 证据 = [`registry/live/steelcodecheck_probe.json`](registry/live/steelcodecheck_probe.json)；
> 生成器 = [`registry/tools/probe_steelcodecheck_p174.py`](registry/tools/probe_steelcodecheck_p174.py)（可 `--check` 离线复算）。

> ⚠️ **R169 / R170 / R171（P176 / P177 / P178）—— 设计规范是运行时数据；闸门盲区已收口**：
> 上表「谁**能**修」是**端点可用性**的归因，**不**覆盖「**为什么**某个设计链跑不出结果」。
> P176 实测的根因是**配置不同族**（`DRC.DGNCODE` / `MATL.STANDARD` / `MDGN.CONC_CODE` 三处
> **必须同族**；⚠️ `MATL.STANDARD` 的合法值是**材料库名**，**不是**规范码）⇒ 只切一处时
> 引擎**跳过所有单元**（⚠️ **不崩**，只是 `400 failed:LoadCombination` + `*-TABLE` **0 行**）
> ⇒ **不要**据此判定「产品不支持」。三条实测事实（路径段是**固定路由名** / 字段集**随规范变化**
> 且**自省不反映** / `DCO` 可选）见 [`registry/README.md`](registry/README.md) §8.31。
> ✅ **R170 → R171（P178 已收口）**：`spec_guard` 现在**认识** `patternProperties` ——
> 盲区 **21 个文件 / 90 个枚举节点 → 0**；`DESIGN.RC.DRC` 的 `DGNCODE="TOTALLY-BOGUS"`
> **现在会拦**（修前不拦），而**合法值**（`KDS 41 20 : 2022` / `GB/T50010-10`）**仍放行**。
> ⚠️ **修完的直接后果**：闸门**第一次**看见 **6** 条既有窄枚举（**不是**新增闸门）⇒
> **2** 条已补（`DB.SWIND` / `DB.SSEIS` 的 `USER TYPE`，来源 = 本端点自己的手册示例）、
> **4** 条**如实留缺**：钢筋规格「D4~D57」手册**无完整表**（`D57` 出现 **0** 次）⇒ 不发明；
> `DB.REBR.HOOP_TYPE` 整数/字符串**类型冲突**（`/info` 权威站在 integer 一侧）。
> ⚠️ **代价如实记录**：钢筋规格那 **5** 个端点的合法调用（如 `D22`）**会被我方拦** ——
> 有意的取舍（宁可我方拦，也不把不确定的取值放行到原生）。
> 主指标**不受影响**（仍 **`71 / 73`**）。

> ⚠️ **R166（P173，归因）**：主指标的**缺口归因**也**不**手写 ——
> `python registry/tools/check_operation_availability.py --attribution`（**零请求**）给出
> 每个挡点端点**卡在谁**（**我方** / **MIDAS 侧**）。⚠️ 收口 `POST.STEELCODECHECK` 后，
> **我方**的可拿下项**已全部收口** ⇒ 剩余 **4** 个挡点端点**全部**是 **MIDAS 侧**（崩溃族）。
> ⇒ 「下一步该做什么」见 §5.1。

---

## 2. 文档

### 2.1 规范性文档（唯一开发依据）

| 文件 | 说明 |
| --- | --- |
| **`docs/01`–`docs/06`** | **V2 原始规范（架构 / 实现 / 9 Tools / Adapter / SDK / 验收）** |
| **`docs/07_开发方案与任务续接_v1.0.md`** | **开发方案 + 任务续接（含 Operation → MIDAS API 映射）** |
| **`docs/08_会话交接与续接提示词_v1.0.md`** | **会话边界硬性原则 + 交接协议 + 批次状态表 + 续接提示词（每个新会话的第一个入口）** |
| **`registry/`** | **MIDAS API 唯一权威来源**（663 端点定义 + 652 JSON Schema） |
| `docs/00_文档通读与API对照报告_v1.0.md` | V2 六份文档的通读与 API 对照结论 |
| `docs/reports/` | 5 份逐节精读报告 |
| `MIDAS_API_手册覆盖对照_CivilDesigner_v1.0.md` | 手册覆盖对照 |
| `MIDAS_API_DESIGN译名审查报告_v1.0.md` | DESIGN 命名空间中文译名审查 |
| `MIDAS_API_DESIGN中文名对照_v1.0.csv` | 125 条中文名对照（含术语依据） |

> `docs/04` §14 的 66 条种子全部为 `PARTIAL`，生产路径会被 `RegistryMappingNotVerified` 拒绝；
> **涉及 MIDAS API 一律以 `registry/` 为准**。

### 2.2 非规范性历史资料（不作开发依据）

| 文件 | 说明 |
| --- | --- |
| `archive/legacy_v1/` | 根目录 `StructAI_MIDAS_MCP_*` 全家族（7 `.md` + 3 `.csv`）已归档 |

> ⚠️ `archive/legacy_v1/` 下全部文件**不作为开发依据，不作为准则**，仅用于来源追溯与审计核对。
> 索引与约束见 [`archive/legacy_v1/README.md`](archive/legacy_v1/README.md)。

### 2.3 外部证据输入（第三方 SDK 对照，**不作开发依据**）

| 文件 | 说明 |
| --- | --- |
| [`docs/nxsdk_review/00_评估与查漏补缺报告_v1.0.md`](docs/nxsdk_review/00_评估与查漏补缺报告_v1.0.md) | 对 [`Dennis5882/MIDAS-API-NX-SDK`](https://github.com/Dennis5882/MIDAS-API-NX-SDK) 的评估与逐端点/逐字段/逐产品比对 |
| [`MIDAS_API_Online_Manual_勘误与补全_v1.0.md`](MIDAS_API_Online_Manual_勘误与补全_v1.0.md) | **官方手册勘误 62 条（MD-01～MD-62）** + 我方手册补全清单 |
| [`docs/nxsdk_review/nxsdk_product_corrections.json`](docs/nxsdk_review/nxsdk_product_corrections.json) | 54 条产品归属更正（A/B/C 三级 + 逐条证据），供导入工具消费 |
| [`docs/nxsdk_review/nxsdk_gap_summary.json`](docs/nxsdk_review/nxsdk_gap_summary.json) | 全部计数的机器可读汇总 |
| [`registry/tools/import_nxsdk_evidence.py`](registry/tools/import_nxsdk_evidence.py) | 外部证据导入工具（默认预演、幂等、`--tier` 分级、`--check` 断言） |

> ⚠️ 上列内容**全部是外部证据**，**不是本仓库的实测结论**。
> 依 §8.2 的既定口径，凡涉及 `products` / 必填性 / 类型的变更，均需**我方实例实测 + 显式裁决**。
> 导入工具**默认只预演**；本批次**未改动 `registry/` 任何数据**。

---

## 3. 参考实现与冒烟测试

```powershell
cd examples
$env:MIDAS_BASE_URL = "http://localhost:3030/gen"
$env:MIDAS_MAPI_KEY = "<从密钥管理获取，勿落盘>"

python smoke_test.py                                    # dry-run（离线结构校验）
python smoke_test.py --live --expect-product GEN_NX     # 真实调用（默认只调 GET）
```

`smoke_test.py` 会输出结构化报告（`smoke_report_*.json`），区分
`OK` / `OK_EMPTY` / `INDETERMINATE` / `ENDPOINT_NOT_FOUND` / `CLIENT_NOT_CONNECTED` 等状态。

---

## 4. 安全约定

- **`MAPI-Key` 只经环境变量传入**，本仓库**不包含任何真实密钥**。
- 客户端内置破坏性调用护栏：
  - NX 系 `DELETE` 必须给路径 key（`DELETE {uri}/{key}`）——不带路径 key 会**删除全表**（官方手册 + 实测确认）；
  - Civil Designer 的 `DELETE` 空主体 / `Type=0` 表示**删除全部**，需显式开关放行。

---

## 5. 已知边界

> ⚠️ 本节按 **`docs/07` §15.6.3 的指标层级**写：**主指标 = 接口层端到端 / 生产路径可用 Operation**；
> `availability` 计数与缺口账本属**次指标 / 账本**，**不**驱动优先级。

### 5.1 🔴 主指标上的剩余缺口：**4 个端点 → 2 个 Operation**（收口即 `71 / 71`）

> ⚠️ **R158 更正**：本节旧值写「**6** 个端点 → **9** 个 Operation」（`62 / 71`），
> **漏了** `DESIGN.CODE_CHECK` 与 `POST.STEELCODECHECK`，且只列了 BD/BC 两个变体、
> 没算 CD/BRD/WD/CC。⇒ R158 的真实值 = `61 / 71`。
> ✅ **R159 收口**：**单点最大杠杆 `VIEW.RESULTGRAPHIC` 已解锁 6 个 Operation**
> ⇒ 值 = `67 / 71`。
> ✅ **R160 收口**：**通用取表入口 `POST.TABLE` 已解锁 `RESULT.ANALYSIS.SUMMARY`**
> ⇒ 值 = `68 / 71`。
> ✅ **R166 收口**：**`POST.STEELCODECHECK` 已解锁 `DESIGN.CODE_CHECK`**（钢铁路由，
> **真机实测**；判据 = 效果）⇒ 当时现值 = **`69 / 71`**（后由 **R168** 抬到 `71 / 73`，见下），
> **逐条**由 `python registry/tools/check_operation_availability.py` 复算。

> ✅ **R168（P176 新增并收口）**：新增 `MODEL.EXPORT` / `MODEL.IMPORT` 两条 Operation
> —— 模型 ↔ JSON 的**官方**通道。端点 `DOC.EXPORT` / `DOC.IMPORT` 由 `untested`
> **真机实测**收口为 `verified`，**判据 = 效果**（铁律 ⓪）：导出**真的落盘**
> （4 708 字节 ∧ `DBG` **218** 张表 ∧ 10 项哨兵**逐表与读回同形**）；
> 导入后**新编号按写入值读回**（节点 `9001` → `X = 100`）。
> ⇒ 主指标 **`69 / 71` → `71 / 73`**（分子分母**各 +2**；被挡仍 **2** · 挡点端点仍 **4**）。
> 探针 = `registry/tools/probe_model_doc_p175.py` · 证据 = `registry/live/model_doc_probe.json`。

| 端点 | 挡住 | 谁**能**修 | 状态 |
| --- | ---: | --- | --- |
| `DESIGN.RC.KDS-41-20-2022.BD-ANAL` + `BD-TABLE`（**2**） | 1 | **MIDAS 侧** | `BD-ANAL` **实测四次**打崩 `GenNX.exe`（`wg_db.dll` `0xc0000005` @ `0x2d97e5c`）⇒ **原生崩溃护栏**（**R154**）；`BD-TABLE` 要读的**设计结果**只能由该 `*-ANAL` 产出（**R166**） |
| `DESIGN.SRC.AIK-SRC2K.BC-ANAL` + `BC-TABLE`（**2**） | 1 | **MIDAS 侧** | 同族推定 ⇒ **原生崩溃护栏**（**R154**）；`BC-TABLE` 同上 |
| ~~`POST.STEELCODECHECK`~~ | — | — | ✅ **R166 已收口**（→ `verified`）⇒ 挡点端点 **13 → 4** |

> ⚠️ **R166 的关键**：**我方**不依赖崩溃族 `*-ANAL` 的可拿下项**已全部收口**
> （`--attribution` 的 `ours` 现为**空**）⇒ 剩余 **4** 个挡点端点**全部**卡在 **MIDAS 侧**。
> 即：`python registry/tools/check_operation_availability.py --attribution` 现在会打印
> 「**我方**不依赖 `*-ANAL` 的可自己拿下的一格：**（已全部收口）**」。

> ⚠️ **R165（P172，2026-10-15）—— 收益映射本身也曾是**手写**的，于是漂了**：
> 上表第三行原先照抄 `docs/reports/P160e-a` §1 的「**0**（单独收口**不**解锁）」，
> 理由是「`DESIGN.CODE_CHECK` 还需 **12** 个 RC/SRC 端点」。**实测（离线可复算）**：
> `DESIGN.CODE_CHECK` 的 `steel` 路由 = `CODE-ANAL` → `CODE-TABLE` → `POST.STEELCODECHECK`，
> 前 **2** 步**已** `VERIFIED` ⇒ **只有**末步挡着 ⇒ 收口它 ⇒ **解锁 `DESIGN.CODE_CHECK`**
> （主指标 **68 → 69** · 被挡 **3 → 2** · 挡点端点 **13 → 4**）。
> ⇒ 与 **R158** 同一类教训（那次漂的是**主指标**，这次漂的是**收益映射**）⇒
> **把它变成可执行判定**：`python registry/tools/check_operation_availability.py --benefit`。
>
> ⚠️ **顺带澄清一个**口径**：**挡点**个数**（**13**）**不是**解锁**代价** ——
> `routes` 是**替代**路线 ⇒ 解锁 `DESIGN.CODE_CHECK` 只要 **1** 个端点、
> `DESIGN.CONCRETE` / `DESIGN.SRC` 各 **2** 个、**全部 3 个**只要 **4** 个
> （`BD-ANAL` + `BD-TABLE` + `BC-ANAL` + `BC-TABLE`）。
> ⚠️ **但**可实施性**卡在产品侧**：那 **4** 个里有 **2** 个 `*-ANAL` 是**崩溃族**
> （`BD-ANAL` **实测**打崩 `GenNX.exe`，**R154**）⇒ 「多花几个端点就能绕开」**不成立**。
> ⚠️ 另：**零边际收益 ≠ 没用** —— 6 个 `*-TABLE` 单独收口收益为 **0**，
> 但**成组**收口（`BD-ANAL` + `BD-TABLE`）**真的**解锁 `DESIGN.CONCRETE` + `DESIGN.CODE_CHECK`。
>
> ⚠️ **收益 `+1` ≠ 马上能做**（**代价**那一半，**零请求**可复算）：`POST.STEELCODECHECK` 的
> **请求体来源**在本仓**不成立** —— ① 手册条目**没有** `Request Examples` / `Response Examples`
> 两节（它是 **13** 个挡点端点里**唯一**缺的；对照 `POST.TABLE` / `POST.TEXT` **都**有）；
> ② 手册的 `json_schema` 根键 = `vSECT` / `vELEM`（规格表写的是 Combined Strength Ratio /
> Slenderness Ratio / Deflection ⇒ **结果量**）⇒ 那是**响应**形状，**不**是请求形状；
> ③ 我们落盘的 Schema 与它**逐字节同形**且**没有** `properties` ⇒ `spec_guard` 对它
> **一个字段都不检查**。⇒ 收口**须**一次**有副作用**的授权测量（**R151** 的教训：
> **不**按示例体硬凑 —— 这里连示例体都**没有**）。

> ⚠️ **R166（P173，2026-10-16）—— 收益 ≠ **可实施性**：上表「谁**能**修」那一列现在**算**出来**：
> `python registry/tools/check_operation_availability.py --attribution`（**零请求**）。
> 机械结果：**13** 个挡点端点里 **12** 个卡在 **MIDAS 侧**、**1** 个（`POST.STEELCODECHECK`）是**我方**的。
> ⚠️ **两个反直觉的机械**事实**：
> ① **修好整个崩溃族，主指标**一格都不动**（仍 `68 / 71`）—— 因为剩下的挡点是 **6** 个 `*-TABLE`
> + `POST.STEELCODECHECK`，而 `*-TABLE` 要读的**设计结果**只能由崩溃族的 `*-ANAL` **产出**
> （`-ANAL` = **执行**分析并写结果，`-TABLE` = **读**那份结果；两个端点 YAML 的标题逐字如此）
> ⇒ 「卡在 MIDAS 侧」是**结构**性的，**不**是「多收口几个端点就能绕开」；
> ② `--benefit` 的**每一条**路线都**至少含一个** `*-ANAL`（**含** `DESIGN.SRC` 的最短选项
> `BC-ANAL` + `BC-TABLE`）⇒ **不**碰 `*-ANAL` 就拿不下任何一格 —— **唯一例外**是 `steel` 路由
> （这正是 `DESIGN.CODE_CHECK` 最小代价 = **1** 的成因）。
> ⇒ ~~**下一个可执行动作**仍是 `POST.STEELCODECHECK`~~ ✅ **R166（P174）已兑付** ——
> 那次授权测量**做完了**（判据 = 效果：**0 行 → 2 行** ∧ 取值**不**等于手册示例）
> ⇒ 主指标 **`71 / 73`**，且**我方**可拿下项**已全部收口**（`--attribution` 的 `ours` 为**空**）。
> 细节 = [`registry/README.md`](registry/README.md) §8.28 / §8.29 · `docs/07` §16.1 **R166**。

> ✅ **已收口（R159，2026-10-15）**：~~`VIEW.RESULTGRAPHIC`（挡 6）~~ ——
> 纯 API 进结果视图（post）的路径 = `POST /VIEW/CAPTURE` 的 `Argument.SET_MODE: "post"`
> （**粘性**切换视图模式）+ `TYPE_OF_DISPLAY.<子块>.OPT_CHECK = true`（**结果图形的开关**）；
> 结果图形也可由独立的 `POST /VIEW/RESULTGRAPHIC`（**持久**）配置。
> ⚠️ **R157 的「静默 `200`」成因** = 请求体**缺 `TYPE_OF_DISPLAY`** —— 不是原生空转。

> ✅ **已收口（R160，2026-10-15）**：~~`POST.TABLE`（挡 1）~~ —— 拦住 `RESULT.ANALYSIS.SUMMARY`
> 的**不是**原生，而是核心 `spec_guard`（**R140**）手里那份**只有 2 个取值**的
> `TABLE_TYPE` 枚举（来自 help center **一篇文章**）。枚举来源换成
> **登记表（194）∪ 手册声明（121）= 225**（生成器 `sync_table_type_enum.py`）后，
> 真机实测：原生 `POST /POST/TABLE {TABLE_TYPE: "DISPLACEMENTG"}` ⇒ **`200`** ·
> `HEAD` **9** 列 · `DATA` **63** 行；经 MCP Tool 契约（**生产口径，无旁路**）规范化结果
> `rows` = **63**；伪 token 仍**零请求**被拦（**R140 的保护未丢**）。
> 证据 = [`registry/live/post_table_enum_probe.json`](registry/live/post_table_enum_probe.json)。

> ⚠️ **R161（P168，2026-10-15）—— 主指标不变，但**闸门的覆盖面**变了**：
> 普查发现 `spec_guard` 对 **104 / 225** 个带枚举的 Schema 文件**一个字段都不检查**
> （**盲区**：文件根键就是包装键 ⇒ 下钻约定取不到）；核心 1 行改用 `effective_schema()`
> 后 **盲区归零**（`104 → 0`，零回归）。⚠️ **可见性恢复 ⇒ 窄枚举立刻会拦住合法调用**
> ⇒ 同批先补枚举（`CURRENT_MODE` **36** 个取值 + **6** 个变体 token），
> 效果判据 `PASSED`。**本节的主指标数字不受影响**（当时为 `68 / 71`；**现值见 §1.1**）—— 本批的价值在**防事故**。
> 细节 = [`registry/README.md`](registry/README.md) §8.22 · `docs/07` §16.1 **R161**；
> 证据 = [`registry/live/spec_enum_audit.json`](registry/live/spec_enum_audit.json)。

⚠️ 上表端点**全是纯写端点**（`methods = POST`）⇒ **不能只读收口**，必须**真机写 + 读回验效果**。
⚠️ **剩余 2 个被挡 Operation 的 4 个挡点端点分两组**（**逐条**由
`tests/test_midas_operation_availability_p165b.py::test_p165b_the_remaining_blockers_are_split_by_recovery_condition` 钉住）：
**2** 个 `*-ANAL`（`BD-ANAL` / `BC-ANAL`）= **实测 / 同族推定的崩溃族**
（`NATIVE_CRASH_ENDPOINTS`，**R154** ⇒ **MIDAS 侧**修 `wg_db.dll`）；
**2** 个 `*-TABLE`（`BD-TABLE` / `BC-TABLE`）= `availability: untested`
（要读的**设计结果**只能由同选项里的崩溃族 `*-ANAL` 产出 ⇒ 卡在**同一条**崩溃边，**R166**）。
> ✅ **R166（P174）已收口** `POST.STEELCODECHECK`（→ `verified`）⇒ 挡点端点 **13 → 4**、
> 被挡 Operation **3 → 2**；`--attribution` 的 `ours` 现为**空**。

> ⚠️ **上表「挡住」列是**挡点个数**，不是**解锁代价**（**R165** 澄清）：因为 `routes` 是
> **替代**路线，解锁 `DESIGN.CODE_CHECK` 只要 **1** 个端点、`DESIGN.CONCRETE` / `DESIGN.SRC`
> 各 **2** 个、**全部 3 个**只要 **4** 个。逐端点收益与最小代价由
> `python registry/tools/check_operation_availability.py --benefit` **可执行复算**
> （⚠️ 该脚本 `--check` 会**逐条断言**收益映射与最小代价 —— **手写的映射必然漂**）。

### 5.2 🟡 次指标：数据侧可达性上限与 Schema 覆盖

- **写路径模板**：`71` 个端点 / `115` 个 body（**全部**来源可复算：`check_write_templates.py --summary` 全绿）。
- **11 个端点无 JSON Schema**：`DB.LCOM` · `DOC.CLOSEALL` · `DOC.EXIT` ·
  `OPE.{CPCREATE,CPEXPORT,CPUPDATEMODEL,CPUPDATERESULT,PROJECTSTATUS,SECTPROP,STORYPROP}` · `VIEW.SELECT`。
  ⚠️ 其中 `DB.LCOM` / `OPE.PROJECTSTATUS` / `OPE.SECTPROP` / `VIEW.SELECT` 属**无请求体**端点
  （`docs/07` §16 R5 的裁决），**不**建 Schema 文件是**如实留缺**，不是遗漏。
- **`availability` 分档**：`untested` **126** 个里，**15** 个是 CIVIL_DESIGNER 独有（`designer-cloud` 宕机）、
  **3** 个已声明 `unavailable_on`；其余为**无 GET** 的纯写端点（只读探针覆盖不到）。
  ⚠️ `-M1` 家族 **21** 个属 **`unverified`**（不是 `untested`）—— 两个实例实测均 `404`，见 §1 / `registry/README.md` §8.17.3。
  ⇒ `docs/07` §15.6.2 的 **P4** 已明确**降级**，不再消耗批次预算。
- **窄枚举台账**（P179 收尾）：`closed` **22** · `left_open` **4**。
  ⚠️ 剩余 4 条**全部**是**类型冲突**或**自由引用名** —— 即「不是不知道取值，而是不知道**类型**」：
  `DB.REBR::HOOP_TYPE` · `DCRE::SPLICED_BARS` · `OPE.GSBG::BRDG_GROUP` · `OPE.LCOM-GEN::DGNCODE`。
  P179 的真机测量已证明**这类问题无法靠测量判别**（所有合法载荷统一 `400` 且响应体为空）
  ⇒ 只能等产品侧答复。见 `registry/README.md` §8.33。

### 5.3 环境与安全

- `DOC.CLOSEALL`、`DOC.EXIT` 等**不可回滚**操作**明确未测**。
- 云端中继存在**间歇性掉线**（`client does not exist`），客户端已用 `CLIENT_NOT_CONNECTED` 区分。
- 已实测的**静默失败**形态（**铁律 ⓪** 的由来）：原生**返回 `200` 却什么都不做**至少 **7** 次
  （`R128` `ITEMS` 外层键无效 · `R145` `DOC.NEW` 忽略路径 · `R146` `DOC.SAVE` 不写盘 ·
  P160c 事故 A `SAVEAS` 体被拆 · P164-c 的 `DELETE` 响应体**回显删除前状态** ·
  **R159** `VIEW.RESULTGRAPHIC` 缺 `TYPE_OF_DISPLAY` 时静默不画结果）。
  ⇒ **判据必须是「再读的效果」，不能是状态码。**

详见 `docs/07` §15.6（指标层级）· `docs/08` §3（批次状态）· `registry/README.md`（字段与口径）。
