"""Interface · HTTP · 管理面的共享鉴权 / 错误形状（P185）。

`api.py` 已按领域拆成多个路由模块（认证 / 客户端 / 设置 / 数据 …）。本模块只放
**所有路由模块共用**的薄工具：

- Bearer 解析与身份 / 管理员校验（`identity` / `admin` 依赖）；
- `StructAIError` → 统一 JSON（`{code, message, details}`）；
- `_json`（Application 端口的 Mapping / Sequence → 可序列化形状）。

⚠️ 本模块**不**包含任何业务判定：权限 / 租户 / 任务状态一律在 Application / Core。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

from fastapi import Request
from fastapi.responses import JSONResponse

from app.application.management import ManagementPort
from app.domain.errors import StructAIError

__all__ = [
    "UNAUTHORIZED_HEADERS",
    "access_decision",
    "admin_dependency",
    "bearer",
    "client_ip",
    "error_response",
    "forbidden",
    "identity_dependency",
    "is_admin",
    "json_payload",
    "unauthorized",
]

UNAUTHORIZED_HEADERS: Final[Mapping[str, str]] = {"WWW-Authenticate": 'Bearer realm="structai-ui"'}
"""`401` 的 `WWW-Authenticate`（`docs/02` §17）。"""

IdentityDependency = Callable[[Request], Any]
AdminDependency = Callable[[Request], Any]


def bearer(request: Request) -> str:
    """从请求头取 Bearer Token（缺失 ⇒ 空串）。"""
    header = request.headers.get("authorization", "")
    prefix = "bearer "
    return header[len(prefix) :].strip() if header.lower().startswith(prefix) else ""


def error_response(error: StructAIError) -> JSONResponse:
    """`StructAIError` → 统一 JSON（**不含**凭据 / SQL / 栈）。

    ⚠️ `STRUCTAI-1000`（请求形状非法）映射 **400**：前端据此显示「参数不合法」，
    422 会与 FastAPI 自身的校验错误混淆。
    """
    status = 401 if error.code.endswith("4000") else 400
    if error.code.endswith("4200"):
        status = 403
    return JSONResponse(
        status_code=status,
        content={
            "code": error.code,
            "message": error.message,
            "details": dict(error.details),
        },
    )


def unauthorized() -> JSONResponse:
    """`401`（不区分「无 token」与「token 无效」，`docs/02` §17）。"""
    return JSONResponse(
        status_code=401,
        content={"code": "STRUCTAI-4000", "message": "Unauthorized", "details": {}},
        headers=dict(UNAUTHORIZED_HEADERS),
    )


def forbidden(reason: str = "admin_required") -> JSONResponse:
    """`403`：已认证但有效权限不含 `SYSTEM_ADMIN`（或访问控制拒绝）。"""
    message = (
        "System administrator permission is required"
        if reason == "admin_required"
        else "Access denied by the access control policy"
    )
    return JSONResponse(
        status_code=403,
        content={
            "code": "STRUCTAI-4000",
            "message": message,
            "details": {"stage": "management", "reason": reason},
        },
    )


def is_admin(identity: Mapping[str, Any]) -> bool:
    """身份摘要是否含 `SYSTEM_ADMIN`（`identity()` 的 `permissions` 已求交）。"""
    return "SYSTEM_ADMIN" in {str(code) for code in identity.get("permissions") or ()}


def client_ip(request: Request) -> str:
    """请求来源 IP（优先 `X-Forwarded-For` 第一段；缺失 ⇒ `unknown`）。"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def access_decision(port: ManagementPort, request: Request) -> Mapping[str, Any]:
    """访问控制判定（端口未实现该方法 ⇒ 放行，保持既有装配兼容）。"""
    decide = getattr(port, "access_decision", None)
    if decide is None:
        return {"allowed": True, "reason": None}
    decision = await decide(client_ip(request))
    return decision or {"allowed": True, "reason": None}


def json_payload(payload: Any) -> Any:
    """把 Application 端口返回的映射 / 序列转成可序列化形状（**不**改语义）。"""
    if isinstance(payload, Mapping):
        return {str(key): json_payload(value) for key, value in payload.items()}
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        return [json_payload(item) for item in payload]
    return payload


def identity_dependency(port: ManagementPort) -> IdentityDependency:
    """构造「校验 Bearer Token」依赖（失败返回 `401` 响应）。"""

    async def _identity(request: Request) -> Mapping[str, Any] | JSONResponse:
        token = bearer(request)
        if not token:
            return unauthorized()
        try:
            return await port.identity(token)
        except StructAIError:
            return unauthorized()

    return _identity


def admin_dependency(port: ManagementPort, identity: IdentityDependency) -> AdminDependency:
    """构造「要求 `SYSTEM_ADMIN` + 访问控制」依赖。"""

    async def _admin(request: Request) -> Mapping[str, Any] | JSONResponse:
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        if not is_admin(current):
            return forbidden()
        decision = await access_decision(port, request)
        if not decision.get("allowed"):
            return forbidden(str(decision.get("reason") or "access_denied"))
        return current

    return _admin
