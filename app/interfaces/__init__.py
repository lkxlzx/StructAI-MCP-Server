"""Interface 层（`docs/07` §3.3 冻结结构；`docs/02` §63 / §95）。

本包是 Core 的**对外接口层**，冻结形状（`docs/07` §3.3）：

| 子包 | 内容 | 批次 |
| --- | --- | --- |
| `interfaces/http/` | HTTP 管理面（`docs/02` §95） | **P29–P35 ✅** |
| `interfaces/mcp/` | MCP Server 与 9 Tool 契约（`docs/02` §96 / §44 / §47） | P36+（**未来**） |
| `interfaces/cli/` | 命令行入口 | P36+（**未来**） |

⚠️ `docs/02` §95 明确：HTTP 管理面「**不是** MCP Tool」—— 它服务于健康 / 系统管理 /
Adapter / 软件实例 / Task / Logs / Metrics，与 9 Tool 契约（`docs/07` §14.5
「不得修改 9 Tool Contract」）是**两条**独立的对外面。

本批只落地 `interfaces/http/health.py`（`docs/02` §16 / §41 的三个健康入口）。
`interfaces/mcp/` 与 `interfaces/cli/` 属**后续批次**，本包**不**为它们导出任何
占位名（导出不存在的东西会让 `from app.interfaces import …` 在运行期才失败）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
Interface 层**允许**依赖 FastAPI（Web 框架属接口层的正当依赖），但**禁止**
`Interface → SQLAlchemy`、`Interface → Adapter`、`Interface → Filesystem`
（`docs/07` §14.1）。本包因此只做「协议 → Application 服务」的转换，不含业务逻辑、
不直接访问数据库、不直接访问 Adapter（`docs/02` §3.3「Tool Thin Handler」同理）。
"""

from __future__ import annotations

__all__: list[str] = []
"""本包**不**导出任何名字（见模块 docstring：MCP / CLI 属后续批次）。

`app/interfaces/http/` 的公开名从 `app.interfaces.http` 取。
"""
