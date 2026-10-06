"""Interface · MCP Tool · `engineering_model_delete`（`docs/02` §53；`docs/07` §5.1）。

⚠️ **thin wrapper**（`docs/02` §53）：本模块只做「参数 → `ExecutionService`」——
**不**承载工程语义、**不**重复 26 步管线中的任何一步、**不**判断权限 / Schema /
Capability。Operation 由请求给出（`docs/02` §54），本模块**不**持有任何 Operation 名，
因此新增 / 调整 Operation 不会触碰接口层（`docs/07` §14.5：不得修改 9 Tool Contract）。

分层红线（`docs/07` §14.1）：本模块只依赖 **Application** 层与同包；
**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖 `app.infrastructure`
（仓储 / 事务 / Adapter 一律不可见），也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from app.interfaces.mcp.context import MCPContext
from app.interfaces.mcp.responses import ToolResponse
from app.interfaces.mcp.tools.base import BaseEngineeringTool, ToolRequest

__all__ = ["EngineeringModelDeleteTool"]


class EngineeringModelDeleteTool(BaseEngineeringTool):
    """`engineering_model_delete`（`docs/07` §5.1）。

    HIGH / ASYNC / `MODEL_DELETE` / 7 个 Operation。
    """

    name = "engineering_model_delete"

    async def handle(self, request: ToolRequest, context: MCPContext) -> ToolResponse:
        """转发一次请求（`docs/02` §59 的 `handle` → `ExecutionService` 模式）。"""
        return await self.invoke(request, context)
