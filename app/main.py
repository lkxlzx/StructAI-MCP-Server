"""StructAI MCP Server —— 进程入口（P01 Bootstrap / P02 Config / P03 Domain / P04 Database /
P40 STDIO / P41 Streamable HTTP）。

验收门槛（`docs/07` §12 P01 / P40 / P41；`docs/08` §3）：

    python -m app.main                    → 能启动并正常退出（退出码 0，**stdout 0 字节**）
    python -m app.main --transport stdio  → 在 STDIO 上服务一个 MCP 客户端
    python -m app.main --transport http   → 在 Streamable HTTP 上服务 MCP 客户端

装配顺序（`docs/02` §34 / `docs/03` §84）：

    configure_logging(settings.log_level)   → 日志先就绪（structlog → stderr）
    build_container(settings)               → 装配 settings / runtime_config / engine
    await container.startup()               → 连接校验 + Registry + 执行运行时
    <transport>                             → 按 `--transport` 选择 STDIO / HTTP / 不启动

⚠️ **stdout 纪律**（`docs/03` §42 / §97）：stdout 只允许放 MCP 协议帧。
本模块因此**不** `print()`，所有日志走 stderr（`app/config/logging.py`）；
未指定 `--transport` 时**不**启动任何传输，进程立即以退出码 0 结束 ——
这是 P02 门槛「stdout 0 字节」在传输层上线后的延伸。

⚠️ **按请求装配**（`docs/02` §16 / §33 / §124）：`MCPServer` 的 9 个 Tool 持有
**会话级** `ExecutionService`（它绑定会话级的 `*Store`），而每个 MCP 请求必须有
自己的数据库会话。故本模块把「装配一个 `MCPServer`」包成一个**按需**可调用对象
交给传输层（`build_protocol_server` 支持 `MCPServer | Callable[[], MCPServer]`），
从而「同一个 Tool Runtime 经 STDIO / HTTP 可达」而**不**复制任何业务逻辑。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager

from app import __app_name__, __version__
from app.config.logging import configure_logging
from app.config.settings import settings
from app.container import BATCH_ID, AppContainer, build_container, resolve_local_identity
from app.interfaces.mcp.server import MCPServer, build_mcp_server

__all__ = ["TRANSPORT_CHOICES", "async_main", "main"]

logger = logging.getLogger("structai")

type ServerBuilder = Callable[[], AbstractAsyncContextManager[MCPServer]]
"""按需装配 MCPServer 的工厂（docs/02 §16 / §33 / §124；见模块头部说明）。"""

TRANSPORT_CHOICES: tuple[str, ...] = ("none", "stdio", "http")
"""`--transport` 的取值（`docs/02` §97 / §98；`none` = 不启动传输）。"""


def _server_builder(
    container: AppContainer,
    stack: AsyncExitStack,
) -> ServerBuilder:
    """返回「按需装配 `MCPServer`」的可调用对象（见模块头部的说明）。

    ⚠️ 每个请求开一个**自己的**数据库会话，由 `AsyncExitStack` 在传输结束时
    统一关闭；会话**不**跨请求复用（`docs/02` §16 / §33）。
    """

    @asynccontextmanager
    async def _build() -> AsyncIterator[MCPServer]:
        """装配一个 `MCPServer` 并**持有**它的会话直到调用方退出。

        ⚠️ 会话必须活到本次 `tools/call` 结束（9 个 Tool 与管线都持有会话级
        `*Store`，`docs/02` §16 / §33），故这里用 `AsyncExitStack` 把「开会话」
        的退出动作**延后**到 `async with` 退出时执行。
        """
        factory = container.execution_service
        if factory is None:  # pragma: no cover - 调用方已判空
            raise RuntimeError("execution runtime is not ready")
        async with container.session_factory() as session:
            yield build_mcp_server(factory.create_service(session))

    return _build


async def async_main(transport: str = "none") -> int:
    """异步主流程：初始化日志 → 装配容器 → startup → （可选）服务传输 → shutdown。

    Args:
        transport: 传输选择（`TRANSPORT_CHOICES`）。`"none"` 只做启动 / 关闭，
            因此 P01–P39 的门槛（退出码 0 + stdout 0 字节）**不**受本批影响。

    Returns:
        进程退出码（正常为 0）。
    """
    configure_logging(settings.log_level)

    container: AppContainer = build_container(settings)

    logger.info("%s %s starting (batch=%s)", __app_name__, __version__, BATCH_ID)

    await container.startup()
    try:
        logger.info(
            "%s initialized: version=%s environment=%s transport=%s",
            __app_name__,
            settings.app_version,
            settings.environment,
            transport,
        )
        await _serve(container, transport)
    finally:
        await container.shutdown()

    logger.info("%s stopped cleanly", __app_name__)
    return 0


async def _serve(container: AppContainer, transport: str) -> None:
    """按 `--transport` 启动传输（`docs/03` §83 / §84 的启动顺序）。

    ⚠️ 传输层**只**做通信（`docs/03` §2 / §60）：它复用既有 `MCPServer`
    （9 Tool / Dispatcher / Context 工厂），**不**复制业务逻辑（`docs/02` §124）。
    """
    if transport == "none":
        return
    if container.execution_service is None:
        logger.warning("%s transport not started: execution runtime is not ready", transport)
        return
    async with AsyncExitStack() as stack:
        builder = _server_builder(container, stack)
        if transport == "stdio":
            await _serve_stdio(container, builder)
            return
        await _serve_http(container, builder)


async def _serve_stdio(container: AppContainer, builder: ServerBuilder) -> None:
    """在 STDIO 上服务（`docs/02` §97；`docs/03` §40–§43）。

    ⚠️ 身份是**本地可信身份**（`docs/03` §11）：从已配备的种子管理员解析，
    并如实标注 `LOCAL` —— **不**绕过 RBAC / 租户隔离 / 审计。
    """
    from app.interfaces.mcp.transport.stdio import run_stdio

    identity = await resolve_local_identity(container.session_factory)
    await run_stdio(builder, identity=identity)


async def _serve_http(container: AppContainer, builder: ServerBuilder) -> None:
    """在 Streamable HTTP 上服务（`docs/02` §98；`docs/03` §44–§59）。

    ⚠️ HTTP **必须鉴权**（`docs/07` §8.1）：认证端口由容器提供
    （`ExecutionServiceFactory.authenticator`），身份仍由**服务端**构造。
    """
    import uvicorn

    from app.interfaces.mcp.transport.http import DEFAULT_HTTP_PATH, build_http_app

    factory = container.execution_service
    assert factory is not None  # noqa: S101 - `_serve` 已判空
    app = build_http_app(
        builder,
        authenticator=factory.authenticator(),
        path=DEFAULT_HTTP_PATH,
        host=settings.host,
    )
    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config)
    await server.serve()


def main(argv: Sequence[str] | None = None) -> int:
    """同步入口，返回进程退出码（正常为 0）。"""
    parser = argparse.ArgumentParser(
        prog="structai-mcp",
        description=f"{__app_name__} {__version__} — Core bootstrap (P40 / P41)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{__app_name__} {__version__}",
    )
    parser.add_argument(
        "--transport",
        choices=TRANSPORT_CHOICES,
        default="none",
        help="启动的 MCP 传输（缺省 none：只做启动 / 关闭，不接客户端）",
    )
    args = parser.parse_args(argv)

    try:
        return asyncio.run(async_main(args.transport))
    except KeyboardInterrupt:  # pragma: no cover - 交互式中断
        logger.warning("interrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())
