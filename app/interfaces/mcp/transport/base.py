"""Interface · MCP · Transport · 抽象与协议适配（`docs/03` §2 / §3 / §7 / §25–§34 / §63）。

权威来源
--------
- `docs/03` §2（Transport 分层）—— 必须保持
  `Transport → MCP Protocol → Session → Tool Runtime → Core`；
  **禁止** `HTTP Route → Adapter`、`STDIO Handler → SQLAlchemy`、
  `Transport → Operation-specific logic`。
- `docs/03` §3（Transport 抽象）—— `MCPTransport` 只声明
  `start` / `receive` / `send` / `close`；Transport **不知道**
  `tool` / `operation` / `adapter` / `software` / `database`。
- `docs/03` §7（MCP Protocol 层）—— 负责 `initialize` /
  `notifications/initialized` / `tools/list` / `tools/call` / `ping` /
  session lifecycle / progress / cancellation；**不**负责 RBAC / Capability /
  Task business logic / Adapter mapping。
- `docs/03` §25–§34（tools/list · Tool Schema 映射 · tools/call · Tool Result ·
  Error Mapping）—— 工具定义来自 Tool Registry（本项目的 `MCPServer.list_tools()`）；
  两级 Schema（MCP 信封 + Operation Schema）中**第二级仍归 Schema Engine**。
- `docs/03` §63（MCP Server Error Envelope）—— 对外**不**暴露 stack trace。
- `docs/07` §12 P40 / P41 —— 「**不**新增业务逻辑」：传输层只做
  「协议 ↔ `MCPServer.handle()` / `call_tool()`」的转换（`docs/02` §124）。
- `docs/07` §14.1 / §14.2 —— Interface 层**允许** FastAPI 与 MCP SDK
  （两者都在 `docs/07` §3.1 冻结清单内），**禁止** SQLAlchemy / Adapter / 仓储。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **协议帧由官方 MCP SDK 负责，本层只做「信封 ↔ 统一响应」的转换**：
   `docs/02` §124 要求「加入 HTTP 传输，**不**复制业务逻辑」；`docs/03` §41 / §46
   也明确「wire framing 必须由采用的 MCP SDK/协议实现负责，不能假设简单
   `readline()` 永远适用」「具体是否启用以及各方法的语义由 MCP SDK/协议版本决定」。
   故本层用 SDK 的 low-level `Server` 承载 `initialize` / `ping` / 会话与 JSON-RPC
   编解码，只把 `tools/list` / `tools/call` 接到 **P37–P39 已有的** `MCPServer` 上。
2. **`MCPTransport` 是 `docs/03` §3 的逐字抽象**：`start` / `receive` / `send` /
   `close` 四个方法一个不少。SDK 已经自带各自的 IO 循环，故 `receive` / `send`
   在具体传输里如实声明为「由 SDK 的 IO 循环承担」（返回空迭代器 / 显式拒绝），
   **不**伪造一对假流。
3. **工具清单与入参 Schema 一律取自既有接口层**：`tools/list` 的**名字**来自
   `MCPServer.list_tools()`（`docs/02` §123），入参 Schema 是 `docs/02` §84 /
   `docs/03` §27 的**逐字**信封（`TOOL_INPUT_SCHEMA`）。本层**不**自行发明工具、
   **不**改 Operation Registry（`docs/03` §26 逐字：MCP 层不能自行修改）。
4. **`tools/call` 的返回值 = 统一响应信封**：`docs/02` §71 的信封（13 键）放进
   `structuredContent`，同时在 `content` 里放一段**只含定位信息**的文本
   （`tool` / `operation` / `success` / `request_id` / `trace_id`），便于只读
   `content` 的客户端定位问题。`isError` 与信封的 `success` 严格互为取反 ——
   `docs/03` §32–§34 要求客户端能区分 *Protocol Failure* 与 *Tool Failure*。
5. **协议级失败与工具级失败严格分开**（`docs/03` §33 / §34）：JSON-RPC 层的
   失败（非法 JSON / 未知方法 / 非法参数）由 SDK 的协议层负责；**工具级**失败
   （权限 / 能力 / 适配器 / 未知工具 / 信封非法）一律由 MCP 层翻成
   `success=false` 的统一信封，本层**只搬运**、**不**新增 `STRUCTAI-xxxx` 码。
6. **身份只能来自服务端**（`docs/07` §8.1）：本层的 `_identity_for()` **只**从
   「服务端上下文」取身份 —— HTTP 取 ASGI `scope["state"]`（由鉴权中间件写入），
   STDIO 取进程内的本地可信身份。客户端 header / body 里的
   `user_id` / `tenant_id` / `roles` / `permissions` / `session_id`
   **连读都不读**。
7. **限制（`docs/03` §20–§24）不新增 Settings 字段**：`docs/02` §5 的 17 个
   字段是 P02 冻结形状（`tests/test_infrastructure_p29_p35.py` 逐字段断言），
   故本批把限制声明为**传输层的运行期参数**（`MCPRuntimeLimits`，带规范默认值），
   由装配方（`app/main.py`）显式传入，并登记在 `docs/07` §16。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库、`mcp`（SDK，属 `docs/07` §3.1 冻结清单）、Application 层与同包：
**不**引用 SQLAlchemy / `app.infrastructure` / `app.observability`；
**不**出现任何 Operation 名、**不**判断权限 / Schema / Capability、
**不**import 仓储 / UnitOfWork，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import contextvars
import logging
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any, Final, Protocol, runtime_checkable

from mcp.server.lowlevel import Server
from mcp.server.lowlevel.server import ServerRequestContext
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from app import __app_name__, __version__
from app.application.execution.identity import MCPIdentity
from app.domain.errors import StructAIError
from app.interfaces.mcp.responses import ToolResponse
from app.interfaces.mcp.server import MCPServer

__all__ = [
    "HTTP_IDENTITY_STATE_KEY",
    "MCP_TRANSPORT_STAGE",
    "MCPRuntimeLimits",
    "MCPTransport",
    "SERVER_INSTRUCTIONS",
    "TOOL_INPUT_SCHEMA",
    "build_protocol_server",
    "tool_definition",
]

logger = logging.getLogger("structai")

MCP_TRANSPORT_STAGE: Final[str] = "mcp_transport"
"""本层错误 `details.stage` 的固定取值（`docs/07` §11 的诊断口径）。"""

HTTP_IDENTITY_STATE_KEY: Final[str] = "structai.mcp.identity"
"""ASGI `scope["state"]` 里承载 `MCPIdentity` 的键（`docs/03` §12；见落地裁决 6）。

由鉴权中间件（`transport/http.py`）写入，由本模块的 `tools/call` 处理器读取 ——
这是**服务端**身份的传递通道，客户端无法写入。
"""

TOOL_INPUT_SCHEMA: Final[Mapping[str, Any]] = {
    "type": "object",
    "properties": {
        "operation": {"type": "string"},
        "parameters": {"type": "object"},
        "context": {"type": "object"},
        "idempotency_key": {"type": ["string", "null"]},
        "confirmation_token": {"type": ["string", "null"]},
        "dry_run": {"type": "boolean"},
        "batch": {"type": ["array", "null"]},
    },
    "required": ["operation"],
}
"""MCP Tool 的**顶层**信封 Schema（`docs/02` §84 ∪ `docs/03` §27，逐条照抄）。

⚠️ 这是**两级 Schema 的第一级**（`docs/03` §28）：它只校验「信封」；
真正的 Operation 参数 Schema 仍由 **Schema Engine** 在管线第 8 步二次校验
（`docs/02` §13；`docs/07` §9），本层**不**复制那一步。
"""

SERVER_INSTRUCTIONS: Final[str] = (
    "StructAI MCP Server exposes software-neutral engineering tools. "
    "Use operation names to select engineering actions. "
    "Do not assume vendor-specific APIs. "
    "Long-running operations return task_id."
)
"""`initialize` 返回的 `instructions`（`docs/03` §64 逐字照抄）。"""


@runtime_checkable
class MCPTransport(Protocol):
    """传输抽象（`docs/03` §3 的逐字形状；见落地裁决 2）。

    ⚠️ Transport **不知道** `tool` / `operation` / `adapter` / `software` /
    `database`（`docs/03` §3 逐字）：本协议因此**只有**四个通信方法，
    没有任何业务入口。
    """

    async def start(self) -> None:
        """开始接收（`docs/03` §3）。"""
        ...

    async def receive(self) -> AsyncIterator[bytes]:
        """接收一个协议帧（`docs/03` §3）。

        ⚠️ 实际 wire framing 由 MCP SDK 承担（`docs/03` §41 / §46；见落地裁决 1），
        故具体实现如实声明「由 SDK 的 IO 循环承担」而**不**伪造假流。
        """
        ...

    async def send(self, message: bytes) -> None:
        """发送一个协议帧（`docs/03` §3）。"""
        ...

    async def close(self) -> None:
        """关闭传输（`docs/03` §3）。"""
        ...


@dataclass(frozen=True, slots=True)
class MCPRuntimeLimits:
    """MCP 运行期限制（`docs/03` §20 的 `MCPRuntimeLimits` ＋ §16 / §22–§24 / §52–§56）。

    ⚠️ 见落地裁决 7：这些**不**是 `Settings` 字段（`docs/02` §5 的 17 字段是
    P02 冻结形状），而是传输层的运行期参数，默认值逐条取自 `docs/03` §79。

    Attributes:
        max_message_bytes: 单条消息上限（`docs/03` §21：**先**判大小再解析）。
        max_request_bytes: 单个 HTTP 请求体上限（`docs/03` §52）。
        max_tool_arguments_bytes: `tools/call` 的 `arguments` 上限（`docs/03` §20）。
        max_concurrent_sessions: 并发会话上限（`docs/03` §22）。
        max_requests_per_session: 单会话在途请求上限（`docs/03` §23）。
        max_inflight_requests: 全局在途请求上限（`docs/03` §24）。
        session_idle_timeout_seconds: 会话空闲超时（`docs/03` §16）。
        session_max_lifetime_seconds: 会话最长存活（`docs/03` §16）。
        request_timeout_seconds: 请求超时（`docs/03` §54）。
        max_connections_per_identity: 单身份连接上限（`docs/03` §55）。
        rate_limit_per_minute: 传输层限流（`docs/03` §53：**传输保护**，
            与 Core Quota 的**业务保护**严格分开）。
    """

    max_message_bytes: int = 10_485_760
    max_request_bytes: int = 10_485_760
    max_tool_arguments_bytes: int = 1_048_576
    max_concurrent_sessions: int = 100
    max_requests_per_session: int = 16
    max_inflight_requests: int = 100
    session_idle_timeout_seconds: int = 1800
    session_max_lifetime_seconds: int = 86_400
    request_timeout_seconds: int = 300
    max_connections_per_identity: int = 8
    rate_limit_per_minute: int = 600


_HTTP_IDENTITY: contextvars.ContextVar[MCPIdentity | None] = contextvars.ContextVar(
    "structai_mcp_http_identity",
    default=None,
)
"""HTTP 请求级身份（由 `tools/call` 处理器从 ASGI scope 读出后写入）。

用 contextvar 而不是把身份塞进 `ToolRequest`：SDK 的 `tools/call` 处理器签名由
SDK 固定（`(ctx, params)`），而 `ctx.request` 只在 Streamable HTTP 上存在；
contextvar 让**同一个**处理器同时服务 STDIO（本地可信身份）与 HTTP（请求级身份）。
"""


def tool_definition(name: str) -> Tool:
    """由工具名构造 MCP 工具定义（`docs/03` §26 / §27；见落地裁决 3）。

    ⚠️ 工具名**只**来自既有 `MCPServer.list_tools()`（`docs/02` §123）；
    Operation 清单仍归 Operation Registry，本层**不**读也不改（`docs/03` §26）。
    `docs/03` §65 要求 `tools/list` **不**暴露 `TaskEngine` / `AdapterManager` /
    `API Registry` / `SQLAlchemy` 等内部架构，故描述只写「软件中立的工程工具」。
    """
    return Tool(
        name=name,
        description=(
            f"{name}: software-neutral engineering tool. "
            "Provide an operation name in `operation` and its parameters in `parameters`."
        ),
        input_schema=dict(TOOL_INPUT_SCHEMA),
    )


type ServerFactory = Callable[[], AbstractAsyncContextManager[MCPServer]]
"""按请求装配 `MCPServer` 的工厂（HTTP 用；见 `build_protocol_server` 的说明）。"""


def build_protocol_server(
    server: MCPServer | ServerFactory,
    *,
    identity: MCPIdentity | None = None,
) -> Server[Any]:
    """把既有 `MCPServer` 接到 MCP SDK 的协议层（见落地裁决 1 / 3 / 4）。

    Args:
        server: **P37–P39 已落地**的 `MCPServer`（9 Tool / Dispatcher / Context
            工厂原样复用，`docs/02` §124），或一个「按请求装配 `MCPServer`」的
            可调用对象。后者用于 HTTP：`MCPServer` 的 9 个 Tool 持有**会话级**
            `ExecutionService`（`docs/02` §16 / §33），而 HTTP 的每个请求有自己
            的数据库会话，故必须按请求装配 —— 这正是「同一个 Tool Runtime
            经 HTTP 可达」而**不**复制任何业务逻辑的做法（`docs/02` §124）。
        identity: STDIO 的**本地可信身份**（`docs/03` §11）；HTTP 下应为 `None`
            —— 身份由请求级鉴权中间件给出（见落地裁决 6）。

    Returns:
        已注册 `tools/list` 与 `tools/call` 的 low-level `Server`；
        `initialize` / `ping` / 会话 / JSON-RPC 编解码全部由 SDK 承担。
    """

    @asynccontextmanager
    async def _resolve_server() -> AsyncIterator[MCPServer]:
        """按需取 MCP Server，并**持有**它的会话直到本次调用结束。

        ⚠️ 为什么必须持有：`MCPServer` 的 9 个 Tool 持有**会话级**
        `ExecutionService`（`docs/02` §16 / §33）。HTTP 的每个请求有自己的
        数据库会话，因此按请求装配的工厂会在 `tools/call` 结束后释放会话；
        固定实例（STDIO）则不需要释放。
        """
        if not callable(server):
            yield server
            return
        async with server() as instance:
            yield instance

    async def _list_tools(
        _ctx: ServerRequestContext[Any, Any],
        _params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        """`tools/list`（`docs/03` §25）：工具清单来自既有 `MCPServer`。"""
        async with _resolve_server() as resolved:
            names = resolved.list_tools()
        return ListToolsResult(tools=[tool_definition(name) for name in names])

    async def _call_tool(
        ctx: ServerRequestContext[Any, Any],
        params: CallToolRequestParams,
    ) -> CallToolResult:
        """`tools/call`（`docs/03` §29–§34）：只做「协议 ↔ `MCPServer.handle`」转换。"""
        resolved_identity = _identity_for(ctx, identity)
        token = _HTTP_IDENTITY.set(resolved_identity)
        try:
            async with _resolve_server() as mcp_server:
                response = await mcp_server.handle(
                    str(params.name),
                    _arguments(params.arguments),
                    identity=resolved_identity.identity,
                    permissions=resolved_identity.permissions,
                )
        finally:
            _HTTP_IDENTITY.reset(token)
        return _tool_result(response)

    return Server(
        __app_name__,
        version=__version__,
        instructions=SERVER_INSTRUCTIONS,
        on_list_tools=_list_tools,
        on_call_tool=_call_tool,
    )


def _identity_for(ctx: ServerRequestContext[Any, Any], fallback: MCPIdentity | None) -> MCPIdentity:
    """取出**服务端**身份（见落地裁决 6）。

    HTTP：`ctx.request.scope["state"][HTTP_IDENTITY_STATE_KEY]`（鉴权中间件写入）。
    STDIO：`fallback`（`docs/03` §11 的本地可信身份）。

    Raises:
        RuntimeError: 两条通道都没有身份 —— 说明装配错误（**绝不**回落成匿名身份）。
    """
    request = getattr(ctx, "request", None)
    scope = getattr(request, "scope", None)
    if isinstance(scope, Mapping):
        state = scope.get("state")
        if isinstance(state, Mapping):
            candidate = state.get(HTTP_IDENTITY_STATE_KEY)
            if isinstance(candidate, MCPIdentity):
                return candidate
    if fallback is not None:
        return fallback
    raise RuntimeError(
        "MCP transport received a tools/call without a server-side identity "
        f"(stage={MCP_TRANSPORT_STAGE})"
    )


def _arguments(arguments: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """`tools/call` 的 `arguments`（`docs/02` §54）—— 非对象一律按空对象处理。

    ⚠️ 这里**不**做信封校验：非法信封由既有 MCP 层翻成 `STRUCTAI-1000`
    （`app/interfaces/mcp/tools/base.py` 裁决 4），本层**不**另立一套判定。
    """
    if isinstance(arguments, Mapping):
        return {str(key): value for key, value in arguments.items()}
    return {}


def _tool_result(response: ToolResponse) -> CallToolResult:
    """统一响应信封 → MCP `CallToolResult`（`docs/03` §31 / §32；见落地裁决 4）。

    ⚠️ `isError` 与信封的 `success` 严格互为取反；`structuredContent` 放**完整**的
    13 键信封，故「端到端返回 `docs/02` §71 的统一信封」是可断言的事实。
    """
    envelope = response.to_dict()
    return CallToolResult(
        content=[TextContent(type="text", text=_summary_text(response))],
        structured_content=envelope,
        is_error=not response.success,
    )


def _summary_text(response: ToolResponse) -> str:
    """`content` 里的定位文本（只含定位信息，**不**回显参数 / 结果 / secret）。"""
    if response.success:
        return f"{response.tool} {response.operation} succeeded (request_id={response.request_id})"
    code = ""
    first = response.error
    if isinstance(first, Mapping):
        code = str(first.get("code", ""))
    return (
        f"{response.tool} {response.operation} failed with {code} "
        f"(request_id={response.request_id}, trace_id={response.trace_id})"
    )


def error_result(error: StructAIError) -> CallToolResult:
    """把领域异常直接翻成 MCP 结果（**仅**用于本层的装配期 / 协议期兜底）。

    ⚠️ 正常路径**不**走这里：工具级失败一律由 MCP 层翻成统一信封（见落地裁决 5），
    本函数只为「传输层自己发现的失败」保留一个**不暴露 stack trace**的出口
    （`docs/03` §63）。
    """
    return CallToolResult(
        content=[TextContent(type="text", text=f"transport failure ({error.error_type})")],
        structured_content={"code": error.code, "type": error.error_type, "message": error.message},
        is_error=True,
    )
