"""Interface · HTTP · 同源应用装配（P181）。

把一个进程里的三条对外面装进**同一个** FastAPI 应用：

    /                        → Web UI 静态资源（同源部署，无需 CORS）
    /api/*                   → 管理面（`api.py`；UI 的数据来源）
    /livez /readyz /health   → 健康探针（`health.py`）
    /mcp                     → 既有 MCP Streamable HTTP（**原样转发**，不改协议）

三个落地细节
------------
1. **`/mcp` 用 `Mount` + 路径还原**：SDK 应用自带 `Route("/mcp")`，而 Starlette 的
   `Mount("/mcp", …)` 会把前缀剥掉（内层看到 `/`）。故挂载一个极薄的
   `_RestorePath` 把 `scope["path"]` 还原成 `/mcp` 再交给守门中间件 ——
   这样守门中间件的路径判定与独立部署时**逐字一致**。
2. **lifespan 合并**：SDK 的会话管理器在自己的 lifespan 里启动；`Mount` **不会**
   自动跑子应用的 lifespan，故 FastAPI 的 lifespan 显式进入
   `sdk_app.router.lifespan_context(...)`。
3. **静态 UI 最后挂**：Starlette 按注册顺序匹配，`/` 的兜底必须排在
   `/api` / `/livez` / `/mcp` 之后。

分层红线（`docs/07` §14.1）
--------------------------
本模块只依赖 FastAPI / Starlette 与同包：**不**引用 SQLAlchemy、**不**依赖
`app.infrastructure`、**不**出现任何厂商名。静态目录由调用方注入。
"""

from __future__ import annotations

import pathlib
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any, Final

from fastapi import FastAPI
from starlette.routing import Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.interfaces.http.api import create_api_router, install_cors
from app.interfaces.http.health import create_health_router
from app.interfaces.mcp.transport.http import MCPHTTPMiddleware

__all__ = ["UI_MOUNT_NAME", "build_ui_app"]

UI_MOUNT_NAME: Final[str] = "ui"
"""静态 UI 在 Starlette 里的挂载名（只用于路由命名）。"""

MCP_MOUNT_PATH: Final[str] = "/mcp"
"""MCP 的对外路径（`docs/03` §45；与 `transport/http.py` 的 `DEFAULT_HTTP_PATH` 一致）。"""


class _RestorePath:
    """把 `Mount` 剥掉的前缀还原回 `scope["path"]`（见模块说明 ①）。"""

    def __init__(self, app: ASGIApp, prefix: str) -> None:
        """绑定下游应用与要还原的前缀。"""
        self._app = app
        self._prefix = prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """还原路径后转发（不改其余 scope 字段）。"""
        if scope.get("type") in {"http", "websocket"}:
            scope = dict(scope)
            inner = str(scope.get("path") or "/")
            # ⚠️ **两处都要还原**：Starlette 的 `get_route_path()` 会把 `root_path`
            # 从 `path` 里剥掉；只还原 `path` 时内层 Route 看到的是空串 ⇒ 405。
            scope["path"] = self._prefix + ("" if inner == "/" else inner)
            scope["root_path"] = ""
        await self._app(scope, receive, send)


def build_ui_app(
    *,
    api: Any,
    health: Any,
    mcp_app: ASGIApp,
    mcp_middleware: MCPHTTPMiddleware,
    ui_root: str | pathlib.Path | None,
    cors_allow_origins: Sequence[str] = (),
    title: str = "StructAI MCP Server",
) -> FastAPI:
    """构造同源应用（管理面 + 健康 + MCP + 静态 UI）。

    Args:
        api: `ManagementPort` 实现（Application / Infrastructure 提供的服务）。
        health: `HealthService`。
        mcp_app: **未守门**的 MCP ASGI 应用（`StreamableHTTPTransport.protocol_app`）。
        mcp_middleware: 已装配的守门中间件（鉴权 / 会话 / 限额）。
        ui_root: 静态 UI 根目录；`None` 或不存在的目录 ⇒ 不挂载（纯 API 模式）。
        cors_allow_origins: 显式允许的浏览器来源（同源部署时留空）。
        title: OpenAPI 标题。

    Returns:
        可直接交给 uvicorn 的 FastAPI 应用。
    """

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """同时启动 SDK 会话管理器（见模块说明 ②）。"""
        lifespan_context = getattr(getattr(mcp_app, "router", None), "lifespan_context", None)
        if lifespan_context is None:  # pragma: no cover - SDK 形状变化
            yield
            return
        async with lifespan_context(mcp_app):
            yield

    app = FastAPI(
        title=title,
        version="2.0.0-alpha",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
        redirect_slashes=False,
    )

    app.include_router(create_health_router(health))
    app.include_router(create_api_router(api))
    # ⚠️ **精确路径要单列一条 `Route`**：Starlette 的 `Mount("/mcp", …)` 只匹配
    # `/mcp/…`；对**恰好** `/mcp` 会走 `redirect_slashes`（307）。而 MCP 客户端
    # 用的就是 `/mcp` ⇒ 关掉重定向后必须显式注册这条精确路由（见模块说明 ①）。
    app.router.routes.append(
        Route(
            MCP_MOUNT_PATH,
            # 精确匹配时**不**还原路径（`Route` 不会剥前缀，再拼一次会变成 `/mcp/mcp`）。
            endpoint=mcp_middleware,
            methods=["GET", "POST", "DELETE"],
            name="mcp-exact",
        )
    )
    app.mount(
        MCP_MOUNT_PATH,
        _RestorePath(mcp_middleware, MCP_MOUNT_PATH),
        name="mcp",
    )

    if ui_root is not None:
        root = pathlib.Path(ui_root)
        if root.is_dir():
            # 必须最后挂：`/` 是兜底路由（见模块说明 ③）。
            app.mount("/", StaticFiles(directory=str(root), html=True), name=UI_MOUNT_NAME)

    install_cors(app, cors_allow_origins)
    return app


# 显式保留 `Message` 的类型导入（ASGI 契约的一部分，供后续扩展使用）。
_ = Message
