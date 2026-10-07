"""Interface · MCP · Transport · STDIO（`docs/03` §40–§43；`docs/02` §97 / §123）。

权威来源
--------
- `docs/03` §40（STDIO Transport）—— 链路
  `stdin → MCP message decoder → Protocol → ToolRuntime → stdout`；关键规则
  「**stdout 只能输出 MCP protocol data**」，日志必须走 `stderr`，否则
  *stdout contamination* 会破坏 MCP 通信。
- `docs/03` §41（STDIO 实现骨架）—— `StdioTransport(reader, writer)` 的
  `start` / `receive` / `send` / `close`；并明确「实际 wire framing **必须**由
  采用的 MCP SDK/协议实现负责，不能假设简单 `readline()` 永远适用」。
- `docs/03` §42（STDIO 日志）—— `stdout → MCP` / `stderr → logs`；**禁止**
  `print()`（它会落到 stdout）。
- `docs/03` §43（STDIO 安全）—— 本地 STDIO 默认**单客户端**：
  `one process / one stdio session`；多客户端应用 HTTP。
- `docs/02` §97 —— `python -m app.main` 启动、`MCP_TRANSPORT=stdio`，
  且「STDIO 不应该输出普通日志到 stdout」。
- `docs/07` §8.1 / `docs/03` §11 —— STDIO 可用 *local trusted identity*，
  但**仍**必须构造标准 `IdentityContext`，不得绕过 RBAC / 租户隔离 / 审计。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **STDIO 单会话**：`docs/03` §43 的「one process / one stdio session」直接落成
   「一个 `StdioTransport` 服务一个本地客户端，连接结束即进程收尾」。
   本模块因此**不**实现会话表 / 空闲回收 —— 那是 HTTP 传输的职责（§57）。
2. **协议帧与 stdout 纪律由 SDK 承担**：`docs/03` §41 要求 framing 交给 SDK；
   SDK 的 `stdio_server()` 在服务期间把 fd 0 指向 null、fd 1 指向 **stderr**
   （其源码注释逐字如此），这正是 `docs/03` §42 想要的「stdout 只走协议」。
   本模块因此**不**自己写 `readline()` 循环，也**不**碰 `sys.stdout`。
3. **`receive` / `send` 显式拒绝而不是假装工作**：SDK 已自带 IO 循环
   （见裁决 2），本模块**不**伪造一对「永远读不到东西」的假流；
   两个方法如实抛出 `RuntimeError` 并说明落点。
4. **本地身份由装配方确认**：`docs/03` §11 的 `STRUCTAI_LOCAL_USER_ID` /
   `STRUCTAI_LOCAL_TENANT_ID` 在本项目里**不**新增 `Settings` 字段
   （`docs/02` §5 的 17 字段是冻结形状），而是由装配方（`app/main.py`）
   从**已配备的种子数据**里解析出管理员身份并显式传入；
   `authentication_method` 必须如实标注 `LOCAL`。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库、`mcp`（SDK）与同包：**不**引用 SQLAlchemy /
`app.infrastructure` / `app.observability`；**不**出现任何 Operation 名、
**不**判断权限 / Schema / Capability，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import logging
from typing import Any, Final

from mcp.server.stdio import stdio_server

from app.application.execution.identity import MCPIdentity
from app.interfaces.mcp.server import MCPServer
from app.interfaces.mcp.tools import TOOL_NAMES
from app.interfaces.mcp.transport.base import (
    MCP_TRANSPORT_STAGE,
    ServerFactory,
    build_protocol_server,
)

__all__ = [
    "SDK_OWNED_IO_REASON",
    "STDIO_STAGE",
    "StdioTransport",
    "run_stdio",
]

STDIO_STAGE: Final[str] = "mcp_stdio"
"""本模块的诊断 `stage` 取值（`docs/07` §11）。"""

SDK_OWNED_IO_REASON: Final[str] = (
    "stdio wire framing is owned by the MCP SDK's IO loop "
    f"(docs/03 §41; stage={MCP_TRANSPORT_STAGE})"
)
"""`receive` / `send` 显式拒绝的说明（见落地裁决 3）。"""

logger = logging.getLogger("structai")


class StdioTransport:
    """STDIO 传输（`docs/03` §40–§43；`docs/02` §97）。

    ⚠️ 本类**只**负责通信（`docs/03` §2 / §60）：它不知道 `tool` / `operation` /
    `adapter` / `software` / `database`（`docs/03` §3 逐字）。

    Attributes:
        server: **P37–P39 已落地**的 `MCPServer`（9 Tool / Dispatcher 原样复用）。
        identity: 本地可信身份（`docs/03` §11；`authentication_method = LOCAL`）。
    """

    def __init__(self, server: MCPServer | ServerFactory, *, identity: MCPIdentity) -> None:
        """绑定 MCP Server 与本地可信身份。

        Args:
            server: 既有 `MCPServer`（`docs/02` §68 的装配产物）。
            identity: 服务端确认的本地身份；**绝不**从客户端输入推导（`docs/07` §8.1）。
        """
        self._server: MCPServer | ServerFactory = server
        self._identity = identity
        self._protocol = build_protocol_server(server, identity=identity)

    @property
    def server(self) -> MCPServer | ServerFactory:
        """被绑定的 MCP Server 或按需装配工厂（只读用途）。"""
        return self._server

    @property
    def identity(self) -> MCPIdentity:
        """被绑定的本地可信身份（只读用途；`repr` 里**不含**任何 secret）。"""
        return self._identity

    @property
    def tool_names(self) -> tuple[str, ...]:
        """`tools/list` 会下发的工具名（`docs/03` §25；**恰好 9** 个）。

        ⚠️ 名字清单来自既有接口层：固定实例直接问它（`MCPServer.list_tools()`），
        按需装配的工厂则用 `docs/02` §123 冻结的**同一份** `TOOL_NAMES`
        （P37–P39 已逐条断言 `TOOL_NAMES` == 注册表 == 装配结果，故不会漂移）。
        """
        if callable(self._server):
            return TOOL_NAMES
        return self._server.list_tools()

    async def start(self) -> None:
        """`docs/03` §3 的抽象方法（见落地裁决 2 / 3）。

        ⚠️ STDIO 的 IO 由 SDK 的 `stdio_server()` 在 `serve()` 里建立，
        故这里**没有**需要单独启动的资源；保留该方法是为了满足
        `docs/03` §3 的四方法抽象，**不**做任何隐藏的 I/O。
        """

    async def receive(self) -> Any:
        """显式拒绝（见落地裁决 3）。

        Raises:
            RuntimeError: 协议帧由 SDK 的 IO 循环接收（`docs/03` §41）。
        """
        raise RuntimeError(SDK_OWNED_IO_REASON)

    async def send(self, message: bytes) -> None:
        """显式拒绝（见落地裁决 3）。

        Raises:
            RuntimeError: 协议帧由 SDK 的 IO 循环发送（`docs/03` §41）。
        """
        raise RuntimeError(SDK_OWNED_IO_REASON)

    async def close(self) -> None:
        """`docs/03` §3 的抽象方法。

        ⚠️ 连接由 SDK 的上下文管理器持有：`serve()` 返回即已关闭
        （`docs/03` §85 的关闭顺序由装配方负责），故此处无需额外动作。
        """

    async def serve(
        self,
        *,
        stdin: Any = None,
        stdout: Any = None,
    ) -> None:
        """在当前进程的 stdin / stdout 上服务一个本地客户端（`docs/03` §40–§43）。

        Args:
            stdin: 可选的输入流（`anyio.AsyncFile`）；缺省用进程 stdin。
                测试可注入一对显式流，避免碰真实的标准句柄（`docs/03` §41）。
            stdout: 可选的输出流；缺省用进程 stdout。

        ⚠️ 日志**只**走 stderr（`docs/03` §42）：本模块不 `print()`，
        且 SDK 在服务期间把 fd 1 重定向到 stderr（见落地裁决 2），
        因此 `python -m app.main` 在**未接客户端**时 stdout 仍为 0 字节。
        """
        logger.info("stdio transport starting (stage=%s)", STDIO_STAGE)
        async with stdio_server(stdin, stdout) as (read_stream, write_stream):
            await self._protocol.run(
                read_stream,
                write_stream,
                self._protocol.create_initialization_options(),
            )
        logger.info("stdio transport stopped (stage=%s)", STDIO_STAGE)


async def run_stdio(
    server: MCPServer | ServerFactory,
    *,
    identity: MCPIdentity,
    stdin: Any = None,
    stdout: Any = None,
) -> None:
    """在 STDIO 上服务一个客户端（`docs/03` §61 的 `run_stdio()`；`docs/02` §123）。

    Args:
        server: 既有 `MCPServer`（**不**重写、**不**回退，`docs/02` §124）。
        identity: 本地可信身份（`docs/03` §11）。
        stdin: 可选输入流（测试注入用）。
        stdout: 可选输出流（测试注入用）。

    ⚠️ 本函数**不**引入任何新的 `Settings` 字段：限制与身份由装配方显式给出
    （`transport/stdio.py` 裁决 4）。
    """
    transport = StdioTransport(server, identity=identity)
    await transport.serve(stdin=stdin, stdout=stdout)
