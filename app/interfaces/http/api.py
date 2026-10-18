"""Interface · HTTP · 管理面（`docs/02` §95；P181 / P185）。

权威来源
--------
- `docs/02` §95 —— HTTP 管理面**不是** MCP Tool；目录形状
  `interfaces/http/{api.py, health.py, management/}`。
- `docs/02` §57 —— `UI → SQLAlchemy` 禁止：管理面**只**调用 Application 端口。
- `docs/07` §14.1 —— Interface **允许** FastAPI；**禁止** `Interface → SQLAlchemy`
  / `Interface → Adapter` / `Interface → Filesystem`。
- `docs/07` §8.1 —— HTTP **必须鉴权**；身份由服务端从 Token 还原。

落地裁决（只补实现手段）
------------------------
1. **薄转发**：每个处理器只做「HTTP → `ManagementPort` → JSON」。业务判定
   （权限 / 租户 / 任务状态）一律在 Application / Core（`docs/02` §61 / §62）。
2. **鉴权在路由层**：`Authorization: Bearer <token>` → `port.identity(token)`；
   失败一律 `401` + `WWW-Authenticate`，**不**泄露用户是否存在（`docs/02` §17）。
   写操作与敏感读取额外要求 `SYSTEM_ADMIN`（`admin` 依赖）。
3. **`/api/auth/login` 是唯一匿名端点**；其余全部要求 Bearer。
4. **CORS 由装配方显式给出**（`docs/03` §51）：本模块只接受一个来源列表，
   出现 `*` 直接拒绝（与 MCP 传输同口径）。
5. **静态 UI 由装配方挂载**（`app/interfaces/http/app.py`）：本模块不碰文件系统。
6. **错误形状**：`StructAIError` → 统一 `{code, message, details}`；其余异常
   由 FastAPI 的默认 500 处理（**不**把栈或 SQL 回显给浏览器）。
7. **按领域拆分**（P185，单文件 < 800 行）：
   - `management_routes_core.py` —— 认证 / 总览 / 客户端 / 任务 / 目录 / 模板；
   - `management_routes_settings.py` —— 设置 / 用户 / 角色 / 模型 / 通知 / 服务；
   - `management_routes_data.py` —— 数据统计 / 备份 / 清理 / 日志 / 安全概览。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

from fastapi import APIRouter
from starlette.middleware.cors import CORSMiddleware

from app.application.management import ManagementPort
from app.interfaces.http.management_routes_core import register_core_routes
from app.interfaces.http.management_routes_data import register_data_routes
from app.interfaces.http.management_routes_settings import register_settings_routes
from app.interfaces.http.management_shared import admin_dependency, identity_dependency

__all__ = [
    "API_PREFIX",
    "ApiAuthError",
    "create_api_router",
    "install_cors",
]

API_PREFIX: Final[str] = "/api"
"""管理面前缀（`docs/02` §95；与 MCP 的 `/mcp` 并列）。"""


class ApiAuthError(Exception):
    """管理面鉴权失败（路由层内部用；**不**外泄细节）。"""


def create_api_router(port: ManagementPort) -> APIRouter:
    """构造管理面路由（`docs/02` §95；所有端点都是薄转发）。"""
    router = APIRouter(prefix=API_PREFIX, tags=["management"])
    identity = identity_dependency(port)
    admin = admin_dependency(port, identity)
    register_core_routes(router, port, identity=identity, admin=admin)
    register_settings_routes(router, port, identity=identity, admin=admin)
    register_data_routes(router, port, identity=identity, admin=admin)
    return router


def install_cors(app: Any, allow_origins: Sequence[str]) -> None:
    """按显式来源挂 CORS（`docs/03` §51：`*` 与凭证认证不得同用）。"""
    if any(origin.strip() == "*" for origin in allow_origins):
        raise ValueError("CORS wildcard origin is forbidden with credential auth (docs/03 §51)")
    if not allow_origins:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin for origin in allow_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["authorization", "content-type"],
    )
