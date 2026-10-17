"""Interface · HTTP · 管理面（`docs/02` §95；P181）。

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
3. **`/api/auth/login` 是唯一匿名端点**；其余全部要求 Bearer。
4. **CORS 由装配方显式给出**（`docs/03` §51）：本模块只接受一个来源列表，
   出现 `*` 直接拒绝（与 MCP 传输同口径）。
5. **静态 UI 由装配方挂载**（`app/interfaces/http/app.py`）：本模块不碰文件系统。
6. **错误形状**：`StructAIError` → 统一 `{code, message, details}`；其余异常
   由 FastAPI 的默认 500 处理（**不**把栈或 SQL 回显给浏览器）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.application.management import ManagementPort
from app.domain.errors import NotFoundError, StructAIError

__all__ = [
    "API_PREFIX",
    "ApiAuthError",
    "create_api_router",
    "install_cors",
]

API_PREFIX: Final[str] = "/api"
"""管理面前缀（`docs/02` §95；与 MCP 的 `/mcp` 并列）。"""

_UNAUTHORIZED_HEADERS: Final[Mapping[str, str]] = {"WWW-Authenticate": 'Bearer realm="structai-ui"'}


class ApiAuthError(Exception):
    """管理面鉴权失败（路由层内部用；**不**外泄细节）。"""


def _bearer(request: Request) -> str:
    """从请求头取 Bearer Token（缺失 ⇒ 空串）。"""
    header = request.headers.get("authorization", "")
    prefix = "bearer "
    return header[len(prefix) :].strip() if header.lower().startswith(prefix) else ""


def _error_response(error: StructAIError) -> JSONResponse:
    """`StructAIError` → 统一 JSON（**不含**凭据 / SQL / 栈）。"""
    status = 401 if error.code.endswith("4000") else 400
    if error.code.endswith("4200"):
        status = 403
    if error.code.endswith("1000"):
        status = 422
    return JSONResponse(
        status_code=status,
        content={
            "code": error.code,
            "message": error.message,
            "details": dict(error.details),
        },
    )


def _unauthorized() -> JSONResponse:
    """`401`（不区分「无 token」与「token 无效」，`docs/02` §17）。"""
    return JSONResponse(
        status_code=401,
        content={"code": "STRUCTAI-4000", "message": "Unauthorized", "details": {}},
        headers=dict(_UNAUTHORIZED_HEADERS),
    )


def _json(payload: Any) -> Any:
    """把 Application 端口返回的映射 / 序列转成可序列化形状（**不**改语义）。"""
    if isinstance(payload, Mapping):
        return {str(key): _json(value) for key, value in payload.items()}
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        return [_json(item) for item in payload]
    return payload


def create_api_router(port: ManagementPort) -> APIRouter:
    """构造管理面路由（`docs/02` §95；所有端点都是薄转发）。"""
    router = APIRouter(prefix=API_PREFIX, tags=["management"])

    async def _identity(request: Request) -> Mapping[str, Any] | JSONResponse:
        """校验 Bearer Token；失败返回 `401` 响应（调用方直接 return）。"""
        token = _bearer(request)
        if not token:
            return _unauthorized()
        try:
            return await port.identity(token)
        except StructAIError:
            return _unauthorized()

    # ===== 认证 =====

    @router.post("/auth/login")
    async def login(request: Request) -> Any:
        """口令登录 → 会话 token（唯一匿名端点）。"""
        body = await request.json()
        try:
            return _json(
                await port.login(str(body.get("username") or ""), str(body.get("password") or ""))
            )
        except StructAIError as error:
            return _error_response(error)

    @router.post("/auth/logout")
    async def logout(request: Request) -> Any:
        """注销当前会话（幂等）。"""
        token = _bearer(request)
        if not token:
            return _unauthorized()
        return {"ok": await port.logout(token)}

    @router.get("/auth/me")
    async def me(request: Request) -> Any:
        """当前身份摘要。"""
        identity = await _identity(request)
        return identity if isinstance(identity, JSONResponse) else _json(identity)

    # ===== 总览 =====

    @router.get("/status")
    async def status(request: Request) -> Any:
        """首页 / 侧栏状态（服务、任务、客户端、注册表、模板摘要）。"""
        identity = await _identity(request)
        if isinstance(identity, JSONResponse):
            return identity
        return _json(await port.overview())

    @router.get("/stats")
    async def stats(request: Request) -> Any:
        """首页 5 张指标卡（由 `overview` 派生，**不**另算一套）。"""
        identity = await _identity(request)
        if isinstance(identity, JSONResponse):
            return identity
        overview = await port.overview()
        return _json(_stat_cards(overview))

    # ===== 客户端 / 任务 / 日志 =====

    @router.get("/clients")
    async def clients(request: Request) -> Any:
        """软件实例列表（**不含**凭据）。"""
        identity = await _identity(request)
        if isinstance(identity, JSONResponse):
            return identity
        return _json({"items": list(await port.clients())})

    @router.get("/tasks")
    async def tasks(request: Request, limit: int = 20, offset: int = 0) -> Any:
        """任务列表（租户作用域）。"""
        identity = await _identity(request)
        if isinstance(identity, JSONResponse):
            return identity
        return _json(await port.tasks(limit=_bounded(limit), offset=max(offset, 0)))

    @router.get("/tasks/{task_id}")
    async def task_detail(request: Request, task_id: str) -> Any:
        """任务详情（含步骤）。"""
        identity = await _identity(request)
        if isinstance(identity, JSONResponse):
            return identity
        try:
            return _json(await port.task(task_id))
        except StructAIError as error:
            return _error_response(error)

    @router.post("/tasks/{task_id}/cancel")
    async def task_cancel(request: Request, task_id: str) -> Any:
        """请求取消（返回真实取消结果）。"""
        identity = await _identity(request)
        if isinstance(identity, JSONResponse):
            return identity
        try:
            return _json(await port.cancel(task_id))
        except StructAIError as error:
            return _error_response(error)

    @router.get("/events")
    async def events(request: Request, limit: int = 20) -> Any:
        """审计链最近 N 条。"""
        identity = await _identity(request)
        if isinstance(identity, JSONResponse):
            return identity
        return _json({"items": list(await port.events(limit=_bounded(limit)))})

    # ===== 执行（与 MCP 同一条链）=====

    @router.post("/call")
    async def call(request: Request) -> Any:
        """把 UI 请求转成一次 MCP Tool 调用（**同一** 9 Tool 契约）。"""
        identity = await _identity(request)
        if isinstance(identity, JSONResponse):
            return identity
        body = await request.json()
        token = _bearer(request)
        return _json(
            await port.call(
                tool=str(body.get("tool") or ""),
                operation=str(body.get("operation") or ""),
                parameters=dict(body.get("parameters") or {}),
                context=dict(body.get("context") or {}),
                token=token,
            )
        )

    # ===== 端点目录 / Operation =====

    @router.get("/registry")
    async def registry(request: Request) -> Any:
        """端点目录摘要（命名空间计数 / 总数）。"""
        identity = await _identity(request)
        if isinstance(identity, JSONResponse):
            return identity
        return _json(await port.registry())

    @router.get("/endpoints")
    async def endpoints(
        request: Request,
        namespace: str = "",
        q: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> Any:
        """端点列表（按命名空间 / 关键词过滤）。"""
        identity = await _identity(request)
        if isinstance(identity, JSONResponse):
            return identity
        return _json(
            await port.endpoints(
                namespace=namespace,
                query=q,
                limit=_bounded(limit, default=50, maximum=500),
                offset=max(offset, 0),
            )
        )

    @router.get("/endpoints/{key:path}")
    async def endpoint_detail(request: Request, key: str) -> Any:
        """端点详情（含请求 Schema 原文）。"""
        identity = await _identity(request)
        if isinstance(identity, JSONResponse):
            return identity
        try:
            return _json(await port.endpoint(key))
        except StructAIError as error:
            return _error_response(error)
        except NotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"code": "NOT_FOUND", "message": str(error), "details": {}},
            )

    @router.get("/operations")
    async def operations(request: Request) -> Any:
        """运行时 Operation 清单（名字 + 归属 Tool）。"""
        identity = await _identity(request)
        if isinstance(identity, JSONResponse):
            return identity
        return _json({"items": list(await port.operations())})

    # ===== 模板 =====

    @router.get("/templates")
    async def templates(request: Request) -> Any:
        """模板库摘要 + 列表。"""
        identity = await _identity(request)
        if isinstance(identity, JSONResponse):
            return identity
        return _json(await port.templates())

    @router.get("/templates/{name}")
    async def template_detail(request: Request, name: str) -> Any:
        """单个模板的参数表。"""
        identity = await _identity(request)
        if isinstance(identity, JSONResponse):
            return identity
        try:
            return _json(await port.template(name))
        except (StructAIError, NotFoundError) as error:
            return JSONResponse(
                status_code=404,
                content={"code": "NOT_FOUND", "message": str(error), "details": {}},
            )

    # ===== 模板导入 =====

    @router.post("/templates/{name}/import")
    async def template_import(request: Request, name: str) -> Any:
        """模板 + 参数 → 服务器侧 JSON → `MODEL.IMPORT`（经 MCP 契约）。"""
        identity = await _identity(request)
        if isinstance(identity, JSONResponse):
            return identity
        body = await request.json()
        return _json(
            await port.import_template(
                name=name,
                overrides=dict(body.get("parameters") or {}),
                project_path=str(body.get("project_path") or ""),
                token=_bearer(request),
            )
        )

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


def _bounded(value: int, *, default: int = 20, maximum: int = 200) -> int:
    """列表条数上限（**禁止**无限 payload，`docs/07` §14.4）。"""
    if value <= 0:
        return default
    return min(int(value), maximum)


def _stat_cards(overview: Mapping[str, Any]) -> list[dict[str, Any]]:
    """首页 5 张指标卡（数值**只**来自 `overview`）。"""
    service = overview.get("service") or {}
    tasks = overview.get("tasks") or {}
    clients = overview.get("clients") or {}
    return [
        {
            "key": "service",
            "label": "MCP 服务状态",
            "value": "运行中" if service.get("running") else "已停止",
            "tone": "green" if service.get("running") else "gray",
            "foot": str(service.get("version") or ""),
        },
        {
            "key": "clients",
            "label": "已连接客户端",
            "value": str(clients.get("connected") or 0),
            "foot": f"总计 {clients.get('total') or 0}",
        },
        {
            "key": "tasks",
            "label": "活跃任务",
            "value": str(tasks.get("active") or 0),
            "foot": f"排队 {tasks.get('queued') or 0} | 失败 {tasks.get('failed') or 0}",
        },
        {
            "key": "requests",
            "label": "端点总数",
            "value": str((overview.get("registry") or {}).get("endpoints") or 0),
            "foot": f"Schema {(overview.get('registry') or {}).get('schemas') or 0}",
        },
        {
            "key": "latency",
            "label": "模板总数",
            "value": str((overview.get("templates") or {}).get("count") or 0),
            "foot": f"族 {(overview.get('templates') or {}).get('families') or 0}",
        },
    ]
