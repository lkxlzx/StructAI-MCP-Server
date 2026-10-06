"""Interface · MCP · Tool Dispatcher（`docs/02` §58 / §72；`docs/07` §9 第 5 步之前）。

权威来源
--------
- `docs/02` §58（`Tool Dispatcher`）—— 原文：

  ```python
  class ToolDispatcher:
      async def dispatch(self, tool_name, request, context):
          tool = self.registry.get(tool_name)
          if tool is None:
              raise ProtocolError(f"Unknown tool: {tool_name}")
          return await tool.handle(request, context)
  ```

- `docs/02` §72（`Tool Dispatcher`）—— 文件 `interfaces/mcp/dispatcher.py`；流程
  `tool_name → Tool Registry → Operation Registry → Execution Service`，并明确
  「Dispatcher **不直接执行 Adapter**」。
- `docs/07` §12 P37–P39 —— 「未知工具 → 明确错误且**不新增**码」；
  「分发路径**不**做业务判断（权限 / Schema / Capability 仍归 26 步管线）」。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **注册表在进程内、按工具名精确匹配**：`docs/02` §72 的 `Tool Registry` 就是
   「名字 → Tool 实例」的映射。本模块**不**做模糊匹配、**不**做别名、**不**回落默认工具 ——
   未知名字一律 `STRUCTAI-1000`（见裁决 2）。`names()` 按字典序返回（确定性）。
2. **未知工具复用既有 `STRUCTAI-1000`**（`docs/07` §11 逐字含「未知 Tool / 请求格式非法」）：
   本批**不新增**任何 `STRUCTAI-xxxx` 码；错误 `details = {stage, reason, tool}`，
   工具名不是 secret，可回显（`app/interfaces/mcp/errors.py` 裁决 3）。
3. **装配期错误 → `STRUCTAI-7000`**（与 P08 / P19–P20 同一口径：「Registry 校验失败 →
   Server MUST NOT become READY」）：重复注册同一工具名 / 注册非 Tool 对象 / 工具没有名字，
   都在 `register()` 当场抛出，**不**静默覆盖（覆盖会让「注册了 9 个」变成谎话）。
4. **`dispatch` 只做三件事**：查表 → 未知即抛 → `await tool.handle(...)`。
   **不**做权限判断、**不**做 Schema 校验、**不**做能力检查、**不**碰 Adapter ——
   这些全部在第 5–26 步的管线里（`docs/07` §9；§12 P37–P39 的硬性要求）。
5. **未知工具的失败也翻成响应信封**：`dispatch` 按 `docs/02` §58 原文**抛出**，
   由调用方（`MCPServer`）在边界翻成 `success=false` 的统一响应（`docs/02` §71）。
   这样「异常契约」（管线内）与「响应契约」（对外）各自保持唯一形状。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 **Application** 层（错误契约）＋ 同包：**不**引用
SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖 `app.infrastructure`
（Adapter / 仓储一律不可见），也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from app.domain.errors import InternalError
from app.interfaces.mcp.context import MCPContext
from app.interfaces.mcp.errors import unknown_tool_error
from app.interfaces.mcp.responses import ToolResponse
from app.interfaces.mcp.tools.base import BaseEngineeringTool, ToolRequest

__all__ = [
    "DISPATCHER_STAGE",
    "DUPLICATE_TOOL_REASON",
    "INVALID_TOOL_REASON",
    "UNNAMED_TOOL_REASON",
    "ToolDispatcher",
]

DISPATCHER_STAGE: Final[str] = "mcp_dispatcher"
"""本模块错误 `details.stage` 的固定取值。"""

DUPLICATE_TOOL_REASON: Final[str] = "duplicate_tool"
"""同一工具名重复注册的原因取值（见落地裁决 3）。"""

INVALID_TOOL_REASON: Final[str] = "invalid_tool"
"""注册对象不是 `BaseEngineeringTool` 的原因取值（见落地裁决 3）。"""

UNNAMED_TOOL_REASON: Final[str] = "unnamed_tool"
"""注册对象没有 `name` 的原因取值（见落地裁决 3）。"""


class ToolDispatcher:
    """按工具名分发到已注册 Tool（`docs/02` §58 / §72；`docs/07` §9）。

    ⚠️ **不**直接执行 Adapter（`docs/02` §72 逐字），**不**做任何业务判断
    （权限 / Schema / Capability 全归 26 步管线，见落地裁决 4）。
    """

    def __init__(self, tools: Sequence[BaseEngineeringTool] = ()) -> None:
        """建立空注册表并注册传入的 Tool（按传入顺序；重复名字即装配错误）。

        Args:
            tools: 要注册的 Tool 序列（可为空 —— 由 `MCPServer` 装配 9 个）。
        """
        self._tools: dict[str, BaseEngineeringTool] = {}
        for tool in tools:
            self.register(tool)

    # ===== 注册表 =====

    def register(self, tool: BaseEngineeringTool) -> None:
        """注册一个 Tool（`docs/02` §72 的 `Tool Registry`；见落地裁决 3）。

        Args:
            tool: 待注册的 Tool 实例。

        Raises:
            InternalError: `STRUCTAI-7000` —— 不是 `BaseEngineeringTool` /
                没有 `name` / 同名工具已注册（**不**静默覆盖）。
        """
        if not isinstance(tool, BaseEngineeringTool):
            raise InternalError(
                "Tool is not a BaseEngineeringTool",
                details={"stage": DISPATCHER_STAGE, "reason": INVALID_TOOL_REASON},
            )
        name = str(getattr(tool, "name", "") or "")
        if not name:
            raise InternalError(
                "Tool has no name",
                details={"stage": DISPATCHER_STAGE, "reason": UNNAMED_TOOL_REASON},
            )
        if name in self._tools:
            raise InternalError(
                "Tool is already registered",
                details={
                    "stage": DISPATCHER_STAGE,
                    "reason": DUPLICATE_TOOL_REASON,
                    "tool": name,
                },
            )
        self._tools[name] = tool

    def get(self, tool_name: str) -> BaseEngineeringTool | None:
        """按名字取 Tool（`docs/02` §58 的 `registry.get`）；未知返回 `None`。"""
        return self._tools.get(str(tool_name))

    def names(self) -> tuple[str, ...]:
        """已注册的工具名（**字典序**，见落地裁决 1）。"""
        return tuple(sorted(self._tools))

    def tools(self) -> tuple[BaseEngineeringTool, ...]:
        """已注册的 Tool（按名字字典序；只读用途）。"""
        return tuple(self._tools[name] for name in self.names())

    def __len__(self) -> int:
        """已注册的工具数量（验收断言「恰好 9 个」）。"""
        return len(self._tools)

    def __contains__(self, tool_name: object) -> bool:
        """是否已注册该工具名。"""
        return str(tool_name) in self._tools

    # ===== 分发 =====

    async def dispatch(
        self,
        tool_name: str,
        request: ToolRequest,
        context: MCPContext,
    ) -> ToolResponse:
        """分发一次调用（`docs/02` §58 / §72；见落地裁决 1 / 4）。

        Args:
            tool_name: 客户端请求的工具名。
            request: 统一请求信封（`docs/02` §54）。
            context: **服务端** MCP 上下文（`docs/02` §57）。

        Returns:
            统一响应信封（`docs/02` §71）。

        Raises:
            ProtocolError: `STRUCTAI-1000` —— 未知工具（`details.reason = "unknown_tool"`）。
                **不**静默回落、**不**新增码（见落地裁决 2）。
        """
        tool = self.get(tool_name)
        if tool is None:
            raise unknown_tool_error(tool_name)
        return await tool.handle(request, context)
