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
registry/          Endpoint Registry（636 端点定义 + 616 JSON Schema + 索引 + 实例矩阵）
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
| JSON Schema | **616**（96.9%） |
| 命名空间 | `DB` / `POST` / `DESIGN` / `OPE` / `DOC` / `VIEW` / `OPRT` |
| 覆盖产品 | `GEN_NX` / `CIVIL_NX` / `CIVIL_DESIGNER` |
| 实测实例 | 3 个（本地 GEN NX、云 CIVIL NX、云 Civil Designer） |

字段与用法见 [`registry/README.md`](registry/README.md)。

**实测验证状态**（`availability`）：`verified` 246 · `unverified` 23 · `untested` 367。

---

## 2. 文档

### 2.1 规范性文档（唯一开发依据）

| 文件 | 说明 |
| --- | --- |
| **`docs/01`–`docs/06`** | **V2 原始规范（架构 / 实现 / 9 Tools / Adapter / SDK / 验收）** |
| **`docs/07_开发方案与任务续接_v1.0.md`** | **开发方案 + 任务续接（含 Operation → MIDAS API 映射）** |
| **`docs/08_会话交接与续接提示词_v1.0.md`** | **会话边界硬性原则 + 交接协议 + 批次状态表 + 续接提示词（每个新会话的第一个入口）** |
| **`registry/`** | **MIDAS API 唯一权威来源**（636 端点定义 + 616 JSON Schema） |
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

- 写路径实测覆盖 11 / 369 个纯写端点（读路径 266 个含 GET 端点已全部实测）。
- 20 个端点尚无 JSON Schema（OPE 13 / VIEW 1 / DB.LCOM / DOC.CLOSEALL·EXIT / 3 个 POST 表）。
- `DOC.CLOSEALL`、`DOC.EXIT` 等不可回滚操作**明确未测**。
- 云端中继存在**间歇性掉线**（`client does not exist`），客户端已用 `CLIENT_NOT_CONNECTED` 区分。

详见 `archive/legacy_v1/StructAI_MIDAS_MCP_Live冒烟测试报告_v1.0.md` 与 `archive/legacy_v1/StructAI_MIDAS_MCP_统一修复计划_v1.0.md`（**非规范性**证据留痕）。
