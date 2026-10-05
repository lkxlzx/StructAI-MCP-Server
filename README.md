# StructAI MCP Server

> 仓库：`github.com/lkxlzx/StructAI-MCP-Server`

MIDAS Open API 的**机器可读端点注册表（Endpoint Registry）**与配套开发文档、参考实现。

本仓库是 StructAI 多 MIDAS 软件一体化 MCP（Model Context Protocol）Server 的**知识层**：
把 MIDAS 官方手册（Help Center JSON API、Civil NX 手册、Civil Designer 手册、GitHub 韩文整理版）
交叉合并为可直接被程序加载的 Registry，并用**真实 MIDAS 实例**逐端点实测验证。

---

## 目录

```
registry/          Endpoint Registry（635 端点定义 + 615 JSON Schema + 索引 + 实例矩阵）
examples/          参考客户端与冒烟测试（midas_client.py / smoke_test.py / cases.json）
*.md               开发文档、实测补充文档、Live 冒烟测试报告、统一修复计划
*.csv              Endpoint 清单、失败清单、DESIGN 中文名对照
```

---

## 1. Registry

| 指标 | 数值 |
| --- | --- |
| 端点定义 | **635** |
| JSON Schema | **615**（96.9%） |
| 命名空间 | `DB` / `POST` / `DESIGN` / `OPE` / `DOC` / `VIEW` / `OPRT` |
| 覆盖产品 | `GEN_NX` / `CIVIL_NX` / `CIVIL_DESIGNER` |
| 实测实例 | 3 个（本地 GEN NX、云 CIVIL NX、云 Civil Designer） |

字段与用法见 [`registry/README.md`](registry/README.md)。

**实测验证状态**（`availability`）：`verified` 245 · `unverified` 23 · `untested` 367。

---

## 2. 文档

| 文件 | 说明 |
| --- | --- |
| `StructAI_MIDAS_MCP_完整开发文档_v1.0.md` | 主开发文档（产品/连接/Adapter/Registry/工程/设计/图形/计算书主规范） |
| `StructAI_MIDAS_MCP_快速响应与实时反馈架构补充文档_v1.0.md` | 执行与反馈层 |
| `StructAI_MIDAS_MCP_GEN_NX_API_实测补充文档_v1.0.md` | GEN NX 知识层补实（501 个逻辑 key 实测） |
| `StructAI_MIDAS_MCP_CIVIL_NX_API_实测补充文档_v1.0.md` | CIVIL NX 补充 |
| `StructAI_MIDAS_MCP_项目框架图_v1.0.md` | 项目结构 |
| **`StructAI_MIDAS_MCP_Live冒烟测试报告_v1.0.md`** | **真实实例逐端点实测报告（含全部附录）** |
| **`StructAI_MIDAS_MCP_统一修复计划_v1.0.md`** | **问题汇总、修复项与实施记录** |
| `MIDAS_API_手册覆盖对照_CivilDesigner_v1.0.md` | 手册覆盖对照 |
| `MIDAS_API_DESIGN译名审查报告_v1.0.md` | DESIGN 命名空间中文译名审查 |
| `MIDAS_API_DESIGN中文名对照_v1.0.csv` | 125 条中文名对照（含术语依据） |

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

详见 `StructAI_MIDAS_MCP_Live冒烟测试报告_v1.0.md` 与 `StructAI_MIDAS_MCP_统一修复计划_v1.0.md`。
