"""Interface · HTTP · 管理面 · 设置 / 用户 / 角色 / 模型路由（P185）。

⚠️ 全部是**薄转发**：写操作要求 `SYSTEM_ADMIN`（见 `management_shared.admin`）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.application.management import ManagementPort
from app.domain.errors import StructAIError
from app.interfaces.http.management_shared import (
    AdminDependency,
    IdentityDependency,
    error_response,
    json_payload,
)


def register_settings_routes(
    router: APIRouter,
    port: ManagementPort,
    *,
    identity: IdentityDependency,
    admin: AdminDependency,
) -> None:
    """把设置 / 用户 / 角色 / 模型路由挂到 `router` 上。"""

    # ===== 系统设置 =====

    @router.get("/settings")
    async def settings(request: Request) -> Any:
        """全部设置分区（默认值 ⊕ 落库值）＋ 运行时信息。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload(await port.settings())

    @router.put("/settings/{section}")
    async def settings_update(request: Request, section: str) -> Any:
        """深合并一个设置分区（未知分区 → `STRUCTAI-1000`）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        body = await request.json()
        try:
            return json_payload(await port.update_settings(section, dict(body or {})))
        except StructAIError as error:
            return error_response(error)

    @router.post("/settings/reset")
    async def settings_reset(request: Request) -> Any:
        """恢复默认值（`{"section": "..."}` 或空 = 全部）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        body = await request.json()
        try:
            return json_payload(await port.reset_settings(str((body or {}).get("section") or "")))
        except StructAIError as error:
            return error_response(error)

    @router.post("/notify/test")
    async def notify_test(request: Request) -> Any:
        """校验通知邮箱并如实报告投递状态（配置了 SMTP 时真实发送）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        body = await request.json()
        return json_payload(await port.test_notification(str((body or {}).get("email") or "")))

    @router.get("/updates/check")
    async def updates_check(request: Request) -> Any:
        """检查更新（无更新源时如实报告）。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload(await port.check_update())

    @router.post("/service/control")
    async def service_control(request: Request) -> Any:
        """服务控制（stop / restart；未注入钩子时如实报告）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        body = await request.json()
        try:
            return json_payload(await port.service_control(str((body or {}).get("action") or "")))
        except StructAIError as error:
            return error_response(error)

    # ===== 用户 =====

    @router.get("/users")
    async def users(request: Request, q: str = "") -> Any:
        """用户列表（**不含** `password_hash`）。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload(await port.users(query=q))

    @router.post("/users")
    async def user_create(request: Request) -> Any:
        """新建用户。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        body = await request.json()
        try:
            return json_payload(await port.create_user(dict(body or {})))
        except StructAIError as error:
            return error_response(error)

    @router.put("/users/{user_id}")
    async def user_update(request: Request, user_id: str) -> Any:
        """更新用户。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        body = await request.json()
        try:
            return json_payload(await port.update_user(user_id, dict(body or {})))
        except StructAIError as error:
            return error_response(error)

    @router.delete("/users/{user_id}")
    async def user_delete(request: Request, user_id: str) -> Any:
        """删除用户（最后一个管理员拒绝）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        try:
            return json_payload(await port.delete_user(user_id))
        except StructAIError as error:
            return error_response(error)

    @router.post("/users/password/check")
    async def password_check(request: Request) -> Any:
        """按当前密码策略校验口令（**不回显**口令）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        body = await request.json()
        return json_payload(
            await port.verify_password_policy(str((body or {}).get("password") or ""))
        )

    # ===== 角色 =====

    @router.get("/roles")
    async def roles(request: Request) -> Any:
        """角色列表 ＋ 全部权限码。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload(await port.roles())

    @router.post("/roles")
    async def role_create(request: Request) -> Any:
        """新建角色。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        body = await request.json()
        try:
            return json_payload(await port.create_role(dict(body or {})))
        except StructAIError as error:
            return error_response(error)

    @router.put("/roles/{role_id}")
    async def role_update(request: Request, role_id: str) -> Any:
        """更新角色权限。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        body = await request.json()
        try:
            return json_payload(await port.update_role(role_id, dict(body or {})))
        except StructAIError as error:
            return error_response(error)

    @router.delete("/roles/{role_id}")
    async def role_delete(request: Request, role_id: str) -> Any:
        """删除角色（系统管理员 / 仍被用户引用时拒绝）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        try:
            return json_payload(await port.delete_role(role_id))
        except StructAIError as error:
            return error_response(error)

    # ===== 模型 =====

    @router.get("/models")
    async def models(request: Request) -> Any:
        """模型列表 ＋ 参数 / 连接配置（**不含**明文 API Key）。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload(await port.models())

    @router.put("/models")
    async def models_update(request: Request) -> Any:
        """整体替换模型列表 / 默认模型 / 参数。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        body = await request.json()
        try:
            return json_payload(await port.update_models(dict(body or {})))
        except StructAIError as error:
            return error_response(error)

    @router.post("/models/{model_id}/test")
    async def model_test(request: Request, model_id: str) -> Any:
        """测试模型配置完整性（**不**发起外部请求）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        try:
            return json_payload(await port.test_model(model_id))
        except StructAIError as error:
            return error_response(error)
