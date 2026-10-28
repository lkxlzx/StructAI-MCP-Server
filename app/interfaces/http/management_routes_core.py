"""Interface · HTTP · 管理面 · 核心路由（P185）。

覆盖：认证、总览、客户端、任务、审计、执行（`/api/call`）、端点目录、模板。

⚠️ 全部是**薄转发**：HTTP → `ManagementPort` → JSON；业务判定在 Application / Core
（`docs/02` §61 / §62）。鉴权 / 错误形状见 `management_shared.py`。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.application.management import ManagementPort
from app.domain.errors import NotFoundError, StructAIError
from app.interfaces.http.management_shared import (
    AdminDependency,
    IdentityDependency,
    access_decision,
    bearer,
    error_response,
    forbidden,
    json_payload,
    unauthorized,
)


def register_core_routes(
    router: APIRouter,
    port: ManagementPort,
    *,
    identity: IdentityDependency,
    admin: AdminDependency,
) -> None:
    """把核心路由挂到 `router` 上（前缀由调用方给出）。"""

    # ===== 认证 =====

    @router.post("/auth/login")
    async def login(request: Request) -> Any:
        """口令登录 → 会话 token（唯一匿名端点；受访问控制约束）。"""
        decision = await access_decision(port, request)
        if not decision.get("allowed"):
            return forbidden(str(decision.get("reason") or "access_denied"))
        body = await request.json()
        try:
            return json_payload(
                await port.login(str(body.get("username") or ""), str(body.get("password") or ""))
            )
        except StructAIError as error:
            return error_response(error)

    @router.post("/auth/logout")
    async def logout(request: Request) -> Any:
        """注销当前会话（幂等）。"""
        token = bearer(request)
        if not token:
            return unauthorized()
        return {"ok": await port.logout(token)}

    @router.post("/auth/password")
    async def change_password(request: Request) -> Any:
        """当前用户修改自己的口令（旧口令 + 密码策略校验）。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        body = await request.json()
        try:
            return json_payload(
                await port.change_password(
                    bearer(request),
                    str((body or {}).get("current") or ""),
                    str((body or {}).get("new") or ""),
                )
            )
        except StructAIError as error:
            return error_response(error)

    @router.get("/auth/me")
    async def me(request: Request) -> Any:
        """当前身份摘要。"""
        current = await identity(request)
        return current if isinstance(current, JSONResponse) else json_payload(current)

    # ===== 总览 =====

    @router.get("/status")
    async def status(request: Request) -> Any:
        """首页 / 侧栏状态（服务、任务、客户端、注册表、模板摘要）。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload(await port.overview())

    @router.get("/stats")
    async def stats(request: Request) -> Any:
        """首页 5 张指标卡（由 `overview` 派生，**不**另算一套）。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload(_stat_cards(await port.overview()))

    # ===== 客户端 =====

    @router.get("/clients")
    async def clients(request: Request) -> Any:
        """软件实例列表（**不含**凭据）。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload({"items": list(await port.clients())})

    @router.get("/clients/options")
    async def clients_options(request: Request) -> Any:
        """新增 / 编辑客户端的候选值（软件 / 产品 / 版本 / 状态 / 凭据引用）。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload(await port.client_options())

    @router.post("/clients")
    async def client_create(request: Request) -> Any:
        """登记软件实例。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        body = await request.json()
        try:
            return json_payload(await port.create_client(dict(body or {})))
        except StructAIError as error:
            return error_response(error)

    @router.put("/clients/{client_id}")
    async def client_update(request: Request, client_id: str) -> Any:
        """更新软件实例。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        body = await request.json()
        try:
            return json_payload(await port.update_client(client_id, dict(body or {})))
        except StructAIError as error:
            return error_response(error)

    @router.delete("/clients/{client_id}")
    async def client_delete(request: Request, client_id: str) -> Any:
        """删除软件实例（连带清理孤儿版本链）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        try:
            return json_payload(await port.delete_client(client_id))
        except StructAIError as error:
            return error_response(error)

    @router.post("/clients/{client_id}/test")
    async def client_test(request: Request, client_id: str) -> Any:
        """测试实例连通性（真实探测，不伪造）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        try:
            return json_payload(await port.test_client(client_id))
        except StructAIError as error:
            return error_response(error)

    @router.post("/clients/{client_id}/connect")
    async def client_connect(request: Request, client_id: str) -> Any:
        """连接实例（按需注册 Adapter → 绑定 → 连接 → 健康检查）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        try:
            return json_payload(await port.connect_client(client_id))
        except StructAIError as error:
            return error_response(error)

    @router.post("/clients/{client_id}/disconnect")
    async def client_disconnect(request: Request, client_id: str) -> Any:
        """断开实例（幂等）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        try:
            return json_payload(await port.disconnect_client(client_id))
        except StructAIError as error:
            return error_response(error)

    @router.get("/clients/{client_id}/events")
    async def client_events(request: Request, client_id: str, limit: int = 50) -> Any:
        """实例的连接测试 / 生命周期事件。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        events = await port.client_events(client_id, limit=_bounded(limit, default=50))
        return json_payload({"items": list(events)})

    # ===== 任务 / 审计 =====

    @router.get("/tasks")
    async def tasks(request: Request, limit: int = 20, offset: int = 0) -> Any:
        """任务列表（租户作用域）。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload(await port.tasks(limit=_bounded(limit), offset=max(offset, 0)))

    @router.get("/tasks/{task_id}")
    async def task_detail(request: Request, task_id: str) -> Any:
        """任务详情（含步骤）。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        try:
            return json_payload(await port.task(task_id))
        except StructAIError as error:
            return error_response(error)

    @router.post("/tasks/{task_id}/cancel")
    async def task_cancel(request: Request, task_id: str) -> Any:
        """请求取消（返回真实取消结果）。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        try:
            return json_payload(await port.cancel(task_id))
        except StructAIError as error:
            return error_response(error)

    @router.get("/events")
    async def events(request: Request, limit: int = 20) -> Any:
        """审计链最近 N 条。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload({"items": list(await port.events(limit=_bounded(limit)))})

    # ===== 执行（与 MCP 同一条链）=====

    @router.post("/call")
    async def call(request: Request) -> Any:
        """把 UI 请求转成一次 MCP Tool 调用（**同一** 9 Tool 契约）。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        body = await request.json()
        return json_payload(
            await port.call(
                tool=str(body.get("tool") or ""),
                operation=str(body.get("operation") or ""),
                parameters=dict(body.get("parameters") or {}),
                context=dict(body.get("context") or {}),
                token=bearer(request),
            )
        )

    # ===== 端点目录 / Operation =====

    @router.get("/registry")
    async def registry(request: Request) -> Any:
        """端点目录摘要（命名空间计数 / 总数）。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload(await port.registry())

    @router.get("/endpoints")
    async def endpoints(
        request: Request,
        namespace: str = "",
        q: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> Any:
        """端点列表（按命名空间 / 关键词过滤）。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload(
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
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        try:
            return json_payload(await port.endpoint(key))
        except StructAIError as error:
            return error_response(error)
        except NotFoundError as error:
            return _not_found(str(error))

    @router.get("/operations")
    async def operations(request: Request) -> Any:
        """运行时 Operation 清单（名字 + 归属 Tool）。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload({"items": list(await port.operations())})

    # ===== 模板 =====

    @router.get("/templates")
    async def templates(request: Request) -> Any:
        """模板库摘要 + 列表。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload(await port.templates())

    @router.get("/templates/{name}")
    async def template_detail(request: Request, name: str) -> Any:
        """单个模板的参数表。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        try:
            return json_payload(await port.template(name))
        except (StructAIError, NotFoundError) as error:
            return _not_found(str(error))

    @router.post("/templates/{name}/import")
    async def template_import(request: Request, name: str) -> Any:
        """模板 + 参数 → 服务器侧 JSON → `MODEL.IMPORT`（经 MCP 契约）。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        body = await request.json()
        return json_payload(
            await port.import_template(
                name=name,
                overrides=dict(body.get("parameters") or {}),
                project_path=str(body.get("project_path") or ""),
                token=bearer(request),
            )
        )


def _not_found(message: str) -> JSONResponse:
    """`404`（查找失败；**不**带 `STRUCTAI-xxxx`，见 `docs/07` §11 裁决）。"""
    return JSONResponse(
        status_code=404,
        content={"code": "NOT_FOUND", "message": message, "details": {}},
    )


def _bounded(value: int, *, default: int = 20, maximum: int = 200) -> int:
    """列表条数上限（**禁止**无限 payload，`docs/07` §14.4）。"""
    if value <= 0:
        return default
    return min(int(value), maximum)


def _stat_cards(overview: Any) -> list[dict[str, Any]]:
    """首页 5 张指标卡（**按设计原稿**：服务 / 客户端 / 任务 / 今日请求 / 平均响应）。

    数值**只**来自 `overview`；昨日基线或环比算不出时字段为 `None`
    （前端据此隐藏，**不**显示编造的 0%）。
    """
    service = overview.get("service") or {}
    tasks = overview.get("tasks") or {}
    clients = overview.get("clients") or {}
    usage = overview.get("usage") or {}
    requests = usage.get("requests") or {}
    latency = usage.get("latency_ms") or {}
    return [
        {
            "key": "service",
            "label": "MCP 服务状态",
            "value": "运行中" if service.get("running") else "已停止",
            "unit": None,
            "tone": "green" if service.get("running") else "gray",
            "delta": None,
            "foot": str(service.get("version") or ""),
        },
        {
            "key": "clients",
            "label": "已连接客户端",
            "value": str(clients.get("connected") or 0),
            "unit": None,
            "tone": "plain",
            "delta": None,
            "foot": f"总计 {clients.get('total') or 0}",
        },
        {
            "key": "tasks",
            "label": "活跃任务",
            "value": str(tasks.get("active") or 0),
            "unit": None,
            "tone": "plain",
            "delta": None,
            "foot": f"排队 {tasks.get('queued') or 0} | 失败 {tasks.get('failed') or 0}",
        },
        {
            "key": "requests",
            "label": "今日请求数",
            "value": str(requests.get("today") or 0),
            "unit": None,
            "tone": "plain",
            "delta": requests.get("delta_percent"),
            "foot": f"昨日 {requests.get('yesterday') or 0}",
        },
        {
            "key": "latency",
            "label": "平均响应时间",
            "value": None if latency.get("today") is None else str(latency.get("today")),
            "unit": "ms",
            "tone": "plain",
            "delta": latency.get("delta_percent"),
            "foot": "昨日 —"
            if latency.get("yesterday") is None
            else f"昨日 {latency.get('yesterday')} ms",
        },
    ]
