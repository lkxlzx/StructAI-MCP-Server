"""Interface · MCP · Server（`docs/02` §57 / §58 / §68 / §72；`docs/07` §9 第 1–4 步）。

权威来源
--------
- `docs/02` §68（Server 启动顺序）—— 原文：

  ```text
  注册 9 Tool
  初始化 Application Container
  绑定 Tool Dispatcher
  启动 Transport
  ```

  并明确「**不得**在 `server.py` 写业务逻辑」。
- `docs/02` §72 —— 文件 `interfaces/mcp/server.py` 属冻结结构（`docs/07` §3.3）。
- `docs/07` §9 —— 第 1–4 步（`MCP Request` / `Authenticate` /
  `Build Server IdentityContext` / `Build ExecutionContext`）属 **P37–P39**；
  第 26 步（`MCP Response`）由本层组装（`app/interfaces/mcp/responses.py`）。
- `docs/07` §8.1 —— 身份**必须**由服务器生成；STDIO 可用本地可信身份，
  HTTP 必须鉴权（传输层属 P40 / P41）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **`MCPServer` 是「装配 + 转发」，不是业务层**：它按 §68 的顺序注册 9 个 Tool、
   绑定 Dispatcher、并暴露两个入口 —— `handle()`（**传输层入口**：客户端参数 →
   第 1–4 步 → 分发）与 `call_tool()`（**已构造上下文入口**：只做分发）。
   **不**碰仓储 / 事务 / Adapter，**不**判断权限 / Schema / Capability（`docs/02` §68）。
2. **`handle()` 是「一个请求 → 一个响应」的**唯一**边界**：`ToolRequest` 解析失败
   （`STRUCTAI-1000`）与上下文构造失败（同样是 `STRUCTAI-1000`）都在这里翻成
   `success=false` 的统一响应，**不**把异常抛给传输层；`request_id` / `trace_id`
   在任何分支都已由 Core 生成（见 `context.py` 裁决 2），因此**失败响应也可被定位**。
3. **认证不在此实现**：`handle()` 的 `identity` 必须由调用方（传输层 / 会话链，
   P40 / P41）传入**已认证**的服务端身份；本层**绝不**从客户端输入推导身份，
   `ToolRequest.context` 里的 `identity` / `user_id` / `tenant_id` / … 一律忽略
   （`docs/07` §8.1 / §14.3），忽略证据随响应 `metadata` 返回。
4. **传输（STDIO / Streamable HTTP）不在本批**（`docs/07` §12 P40 / P41；
   `docs/08` §4：不要提前做）：本模块只提供「无传输也可验收」的调用面
   （`build_mcp_server` + `handle` / `call_tool`），P40 / P41 只需在其上挂传输，
   **不**复制任何业务逻辑（`docs/02` §124）。
5. **`list_tools()` 返回工具名元组**：`docs/02` §123 的 `list_tools` 是 P40 的门槛，
   本批只提供**只读**的名字清单（9 个），**不**构造 MCP SDK 的 Tool 描述对象 ——
   SDK 类型属传输层（P40 / P41）。

6. **显式 `request_id` / `trace_id` 必须符合本层形态**：二者由 Core 生成（`docs/02` §5；
   `docs/07` §9 第 1–4 步），`handle()` 仍允许调用方显式传入（便于把同一逻辑请求串成一条
   链路），但**只接受** `req_<32 hex>` / `trace_<32 hex>`；其余一律 `STRUCTAI-1000`
   （`details.reason = invalid_request_id` / `invalid_trace_id`）。这样 P40 / P41 的传输层
   **不能**把客户端给的关联 id（如 JSON-RPC `id`）原样塞进审计 / Trace 的关联字段。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 **Application** 层（`ExecutionService`）＋ 同包：
**不**引用 SQLAlchemy / FastAPI / **MCP SDK** / httpx（SDK 属 P40 / P41 的传输层），
**不**依赖 `app.infrastructure`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, Final

from app.application.execution.service import ExecutionService
from app.application.security.context import IdentityContext
from app.domain.errors import StructAIError
from app.interfaces.mcp.context import (
    MCPContext,
    MCPContextFactory,
    new_request_id,
    new_trace_id,
)
from app.interfaces.mcp.dispatcher import ToolDispatcher
from app.interfaces.mcp.errors import (
    INVALID_REQUEST_ID_REASON,
    INVALID_TRACE_ID_REASON,
    invalid_arguments_error,
)
from app.interfaces.mcp.responses import UNKNOWN_OPERATION, ToolResponse, failure_response
from app.interfaces.mcp.tools import build_tools
from app.interfaces.mcp.tools.base import ToolRequest

__all__ = [
    "MCP_SERVER_STAGE",
    "REQUEST_ID_PATTERN",
    "TRACE_ID_PATTERN",
    "MCPServer",
    "build_mcp_server",
]

MCP_SERVER_STAGE: Final[str] = "mcp_server"
"""本模块错误 `details.stage` 的固定取值（`docs/07` §11 的诊断口径）。"""

REQUEST_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^req_[0-9a-f]{32}$")
"""`request_id` 的形态（`docs/02` §5 的 `req_<hex>`；见落地裁决 6）。"""

TRACE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^trace_[0-9a-f]{32}$")
"""`trace_id` 的形态（`docs/02` §5 的 `trace_<hex>`；见落地裁决 6）。"""


class MCPServer:
    """MCP Server 的**装配 + 转发**层（`docs/02` §68 / §72；见落地裁决 1）。

    ⚠️ 本类**不**含业务逻辑（`docs/02` §68 逐字）：注册 9 个 Tool、绑定 Dispatcher、
    把客户端参数翻译成「第 1–4 步 ＋ 分发」，仅此而已。

    Attributes:
        execution: 会话级执行服务（9 个 Tool 共享**同一个**实例）。
        contexts: MCP 上下文工厂（第 3–4 步）。
        dispatcher: 工具分发器（第 5 步之前的**唯一**入口）。
    """

    def __init__(
        self,
        *,
        execution: ExecutionService,
        contexts: MCPContextFactory | None = None,
        dispatcher: ToolDispatcher | None = None,
    ) -> None:
        """装配服务器（`docs/02` §68 的顺序：注册 9 Tool → 绑定 Dispatcher）。

        Args:
            execution: 会话级 `ExecutionService`（`ExecutionServiceFactory.create()`）。
            contexts: 上下文工厂；缺省新建一个（`docs/02` §57 / §69）。
            dispatcher: 分发器；缺省用 `build_tools(execution)` 注册**恰好 9** 个 Tool。
        """
        self._execution = execution
        self._contexts = contexts or MCPContextFactory()
        self._dispatcher = dispatcher or ToolDispatcher(build_tools(execution))

    # ===== 只读视图（供装配 / 验收断言）=====

    @property
    def execution(self) -> ExecutionService:
        """被绑定的执行服务（只读用途）。"""
        return self._execution

    @property
    def contexts(self) -> MCPContextFactory:
        """被绑定的上下文工厂（只读用途）。"""
        return self._contexts

    @property
    def dispatcher(self) -> ToolDispatcher:
        """被绑定的分发器（只读用途）。"""
        return self._dispatcher

    def tool_names(self) -> tuple[str, ...]:
        """已注册的工具名（**字典序**）。"""
        return self._dispatcher.names()

    def list_tools(self) -> tuple[str, ...]:
        """`list_tools` 的只读结果（`docs/02` §123；见落地裁决 5）。

        ⚠️ 返回的是**名字清单**（恰好 9 个，字典序），不是 MCP SDK 的 Tool 描述对象 ——
        SDK 类型属传输层（P40 / P41），本批**不**引入。
        """
        return self._dispatcher.names()

    # ===== 入口一：已构造上下文（只分发）=====

    async def call_tool(
        self,
        tool_name: str,
        request: ToolRequest,
        context: MCPContext,
    ) -> ToolResponse:
        """分发一次已构造好的调用（`docs/02` §58 / §72）。

        Args:
            tool_name: 客户端请求的工具名。
            request: 统一请求信封（`docs/02` §54）。
            context: **服务端** MCP 上下文（`docs/02` §57）。

        Returns:
            统一响应信封；未知工具翻成 `success=false` ＋ `STRUCTAI-1000`（见落地裁决 2）。

        Raises:
            Exception: **非** `StructAIError` 的异常（编程错误）原样上抛。
        """
        try:
            return await self._dispatcher.dispatch(tool_name, request, context)
        except StructAIError as error:
            return failure_response(
                tool=str(tool_name),
                operation=request.operation,
                error=error,
                context=context,
            )

    # ===== 入口二：传输层入口（第 1–4 步 ＋ 分发）=====

    async def handle(
        self,
        tool_name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        identity: IdentityContext,
        permissions: Iterable[str] = (),
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> ToolResponse:
        """处理一次 MCP 调用（`docs/02` §57 / §58；`docs/07` §9 第 1–4 步）。

        Args:
            tool_name: 客户端请求的工具名（`docs/07` §5.1 的 9 个之一）。
            arguments: MCP 调用的 `arguments`（`docs/02` §54 的请求信封）。
            identity: **已认证**的服务端身份（见落地裁决 3；本层不做认证）。
            permissions: 服务端计算的有效权限快照（`docs/02` §42）；缺省空集。
            request_id: 服务端请求标识；缺省生成（`docs/02` §5）。显式传入时**必须**是本层
                的 `req_<32 hex>` 形态，否则 `STRUCTAI-1000`（见落地裁决 6 —— 防传输层伪造）。
            trace_id: 服务端链路标识；同上（`trace_<32 hex>`）。

        Returns:
            统一响应信封（`docs/02` §71）—— 成功与失败都是「一个响应」。

        Raises:
            Exception: **非** `StructAIError` 的异常（编程错误）原样上抛。
        """
        try:
            resolved_request_id = _validated_request_id(request_id)
            resolved_trace_id = _validated_trace_id(trace_id)
            request = ToolRequest.from_mapping(arguments)
            context = self._contexts.create(
                identity,
                client_context=request.context,
                permissions=permissions,
                request_id=resolved_request_id,
                trace_id=resolved_trace_id,
            )
        except StructAIError as error:
            return failure_response(
                tool=str(tool_name),
                operation=UNKNOWN_OPERATION,
                error=error,
                request_id=new_request_id(),
                trace_id=new_trace_id(),
            )
        return await self.call_tool(tool_name, request, context)


def build_mcp_server(
    execution: ExecutionService,
    *,
    contexts: MCPContextFactory | None = None,
) -> MCPServer:
    """装配一个 MCP Server（`docs/02` §68 的启动顺序；见落地裁决 4）。

    Args:
        execution: 会话级 `ExecutionService`（`ExecutionServiceFactory.create()`）。
        contexts: 可选的上下文工厂（测试可注入固定时钟 / 工厂）。

    Returns:
        已注册**恰好 9** 个 Tool 的 `MCPServer`。

    ⚠️ 本函数**不**启动任何传输（STDIO / HTTP 属 P40 / P41）：它只做 §68 的
    「注册 9 Tool → 绑定 Dispatcher」两步，因此可以在**不启动 uvicorn / 不接 STDIO**
    的情况下验收（`docs/02` §41 的最小可运行形态）。
    """
    return MCPServer(
        execution=execution,
        contexts=contexts,
        dispatcher=ToolDispatcher(build_tools(execution)),
    )


def _validated_request_id(value: str | None) -> str:
    """校验显式传入的 `request_id`（见模块裁决 6）；`None` → 生成一个。

    Raises:
        ProtocolError: `STRUCTAI-1000` —— 形态不是 `req_<32 hex>`。
    """
    if value is None:
        return new_request_id()
    if not REQUEST_ID_PATTERN.match(str(value)):
        raise invalid_arguments_error(INVALID_REQUEST_ID_REASON)
    return str(value)


def _validated_trace_id(value: str | None) -> str:
    """校验显式传入的 `trace_id`（见模块裁决 6）；`None` → 生成一个。

    Raises:
        ProtocolError: `STRUCTAI-1000` —— 形态不是 `trace_<32 hex>`。
    """
    if value is None:
        return new_trace_id()
    if not TRACE_ID_PATTERN.match(str(value)):
        raise invalid_arguments_error(INVALID_TRACE_ID_REASON)
    return str(value)
