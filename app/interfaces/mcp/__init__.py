"""Interface · MCP（`docs/07` §3.3 冻结结构；`docs/02` §53 / §57 / §58 / §68 / §72）。

`docs/07` §3.3 冻结的目录形状：

```text
interfaces/mcp/  server.py · context.py · dispatcher.py · responses.py · errors.py
                 tools/{base,engineering_doc,engineering_model_query,
                        engineering_model_assign,engineering_model_delete,
                        engineering_model_build,engineering_view,
                        engineering_result,engineering_design,engineering_analysis}.py
```

本包是 **P37–P39** 的落点（`docs/07` §12 P37–P39；`docs/02` §122）：

| 顺序（`docs/02` §122） | 落点 |
| --- | --- |
| MCP Context | `context.py`（第 1–4 步：`docs/07` §9） |
| Dispatcher | `dispatcher.py`（`docs/02` §58 / §72） |
| Base Tool | `tools/base.py`（`docs/02` §53 / §54 / §73） |
| 9 Tools | `tools/engineering_*.py`（`docs/02` §53 / §74；**恰好 9 个**） |

⚠️ **不**做 P40 / P41（STDIO / Streamable HTTP 传输）与 P42–P48（Testing）：
本包只提供「无传输也可验收」的调用面（`MCPServer.handle` / `call_tool`），
传输层在其上挂载而**不**复制业务逻辑（`docs/02` §124）。

分层红线（`docs/07` §14.1 / §14.2）：Interface 层**允许**依赖 Application 层，
但**禁止** `Interface → SQLAlchemy` / `Interface → Adapter` / `Interface → Filesystem`；
本包因此只做「协议 → Application 服务」的转换，**不含**业务逻辑
（`docs/02` §53「Tool Thin Handler」/ §68「不得在 `server.py` 写业务逻辑」）。
MCP SDK 属传输层（P40 / P41），本包**不**引入。
"""

from __future__ import annotations

from app.interfaces.mcp.context import (
    MCP_AUTHENTICATE_STEP,
    MCP_EXECUTION_STEP,
    MCP_IDENTITY_STEP,
    MCP_REQUEST_STEP,
    MCP_STEPS,
    MCPContext,
    MCPContextFactory,
    new_request_id,
    new_trace_id,
)
from app.interfaces.mcp.dispatcher import ToolDispatcher
from app.interfaces.mcp.errors import error_envelope, sanitize_details, unknown_tool_error
from app.interfaces.mcp.responses import (
    RESPONSE_KEYS,
    ToolResponse,
    execution_envelope,
    failure_response,
    success_response,
)
from app.interfaces.mcp.server import MCPServer, build_mcp_server
from app.interfaces.mcp.tools import TOOL_CLASSES, TOOL_NAMES, build_tools
from app.interfaces.mcp.tools.base import TOOL_REQUEST_FIELDS, BaseEngineeringTool, ToolRequest

__all__ = [
    "MCP_AUTHENTICATE_STEP",
    "MCP_EXECUTION_STEP",
    "MCP_IDENTITY_STEP",
    "MCP_REQUEST_STEP",
    "MCP_STEPS",
    "RESPONSE_KEYS",
    "TOOL_CLASSES",
    "TOOL_NAMES",
    "TOOL_REQUEST_FIELDS",
    "BaseEngineeringTool",
    "MCPContext",
    "MCPContextFactory",
    "MCPServer",
    "ToolDispatcher",
    "ToolRequest",
    "ToolResponse",
    "build_mcp_server",
    "build_tools",
    "error_envelope",
    "execution_envelope",
    "failure_response",
    "new_request_id",
    "new_trace_id",
    "sanitize_details",
    "success_response",
    "unknown_tool_error",
]
