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
registry/          Endpoint Registry（636 端点定义 + 625 JSON Schema + 索引 + 实例矩阵）
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
| 端点定义 | **636** |
| JSON Schema | **625**（98.3%） |
| 命名空间 | `DB`(244) / `POST`(199) / `DESIGN`(125) / `OPE`(34) / `DOC`(21) / `VIEW`(7) / `OPRT`(6) |
| 覆盖产品 | `GEN_NX` / `CIVIL_NX` / `CIVIL_DESIGNER` |
| 实测实例 | 3 个（本地 GEN NX、云 CIVIL NX、云 Civil Designer） |

字段与用法见 [`registry/README.md`](registry/README.md)。

**实测验证状态**（`availability`）：`verified` **509** · `unverified` **23** · `untested` **104**。

### 1.1 主指标：**接口层端到端**（`docs/07` §15.6.3）

> ⚠️ **`availability` 是端点级、**次**指标**。产品对外的单位是 **Operation**，
> 故主指标是**接口层端到端**与**生产路径可用 Operation**（`docs/07` §15.6.3）。

| 层级 | 指标 | 当前 |
| --- | --- | --- |
| 🔴 主指标 | 接口层写路径端到端 | **`13 / 13 PASSED`** |
| 🔴 主指标 | 接口层读路径端到端 | `2 PASSED + 7 PARTIAL + 6 FAILED`（15 条） |
| 🔴 主指标 | 旗舰五步链（`docs/07` §13.5）**生产口径** | **`12 / 12 PASSED`** |
| 🔴 主指标 | **生产路径可用 Operation** | **`62 / 71`**（缺口 = **6** 个端点 → 9 个 Operation） |
| 🟡 次指标 | 数据侧可达性上限（`write_path_coverage()`） | `72 / 633` |
| ⚪ 账本 | 映射缺口 / 留缺账本 | `489` / `178`（**只登记，不驱动优先级**） |

证据 = `registry/live/{interface_path_probe,interface_read_probe,flagship_chain_probe}.json`；
生成器 = `registry/tools/probe_interface_paths.py` / `probe_flagship_chain.py`（均可 `--check` 离线复算）。

---

## 2. 文档

### 2.1 规范性文档（唯一开发依据）

| 文件 | 说明 |
| --- | --- |
| **`docs/01`–`docs/06`** | **V2 原始规范（架构 / 实现 / 9 Tools / Adapter / SDK / 验收）** |
| **`docs/07_开发方案与任务续接_v1.0.md`** | **开发方案 + 任务续接（含 Operation → MIDAS API 映射）** |
| **`docs/08_会话交接与续接提示词_v1.0.md`** | **会话边界硬性原则 + 交接协议 + 批次状态表 + 续接提示词（每个新会话的第一个入口）** |
| **`registry/`** | **MIDAS API 唯一权威来源**（636 端点定义 + 625 JSON Schema） |
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

### 5.1 🔴 主指标上的剩余缺口：**6 个端点 → 9 个 Operation**（收口即 `71 / 71`）

| 端点 | 挡住 | 状态 |
| --- | ---: | --- |
| **`VIEW.RESULTGRAPHIC`** | **6** | 多变体端点（Civil NX 手册里 **20+** 篇各自带 Schema）；P160d 实测 `400 second query is wrong` ⇒ **留缺** |
| `DESIGN.RC.KDS-41-20-2022.BD-ANAL` + `BD-TABLE` | 1 | 需**混凝土**模型（`DESIGN.CONCRETE` 真机链） |
| `DESIGN.SRC.AIK-SRC2K.BC-ANAL` + `BC-TABLE` | 1 | 需 **SRC** 模型（`DESIGN.SRC` 真机链） |
| `POST.TABLE` | 1 | 需真机 `POST` + 读回结果表 |

⚠️ 这 6 个**全是纯写端点**（`methods = POST`）⇒ **不能只读收口**，必须**真机写 + 读回验效果**。

### 5.2 🟡 次指标：数据侧可达性上限与 Schema 覆盖

- **写路径模板**：`71` 个端点 / `115` 个 body（**全部**来源可复算：`check_write_templates.py --check` 全绿）。
- **11 个端点无 JSON Schema**：`DB.LCOM` · `DOC.CLOSEALL` · `DOC.EXIT` ·
  `OPE.{CPCREATE,CPEXPORT,CPUPDATEMODEL,CPUPDATERESULT,PROJECTSTATUS,SECTPROP,STORYPROP}` · `VIEW.SELECT`。
  ⚠️ 其中 `DB.LCOM` / `OPE.PROJECTSTATUS` / `OPE.SECTPROP` / `VIEW.SELECT` 属**无请求体**端点
  （`docs/07` §16 R5 的裁决），**不**建 Schema 文件是**如实留缺**，不是遗漏。
- **`availability` 分档**：`untested` 的 **104** 个里，绝大多数在现有实例上**结构性不可达**
  （`-M1` 家族 21 个 · `unavailable_on: gen-local` · CIVIL_DESIGNER 独有而 `designer-cloud` 宕机）
  ⇒ `docs/07` §15.6.2 的 **P4** 已明确**降级**，不再消耗批次预算。

### 5.3 环境与安全

- `DOC.CLOSEALL`、`DOC.EXIT` 等**不可回滚**操作**明确未测**。
- 云端中继存在**间歇性掉线**（`client does not exist`），客户端已用 `CLIENT_NOT_CONNECTED` 区分。
- 已实测的**静默失败**形态（**铁律 ⓪** 的由来）：原生**返回 `200` 却什么都不做**至少 **6** 次
  （`R128` `ITEMS` 外层键无效 · `R145` `DOC.NEW` 忽略路径 · `R146` `DOC.SAVE` 不写盘 ·
  P160c 事故 A `SAVEAS` 体被拆 · P164-c 的 `DELETE` 响应体**回显删除前状态**）。
  ⇒ **判据必须是「再读的效果」，不能是状态码。**

详见 `docs/07` §15.6（指标层级）· `docs/08` §3（批次状态）· `registry/README.md`（字段与口径）。
