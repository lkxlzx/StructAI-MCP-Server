"""Interface · HTTP · Health（`docs/07` §12 P34；`docs/02` §16 / §41 / §45 / §46 / §94 / §95）。

权威来源
--------
- `docs/02` §16 / §41 / §94（`exec` / `blue`）—— 三个入口 `GET /livez` /
  `GET /readyz` / `GET /health`。
- `docs/02` §45（`blue`）—— HTTP 管理面的路由前缀与标签口径（本模块给出
  `HEALTH_ROUTER_PREFIX` / `HEALTH_ROUTER_TAG` 两个常量，便于 `app/main.py` 装配）。
- `docs/02` §46（`exec`）—— `/health` 可能披露软件 / Adapter / 数据库信息，默认只应
  暴露在**管理面或本地绑定**的接口上。
- `docs/02` §95（`exec`）—— HTTP 管理面**不是** MCP Tool；目录形状是
  `interfaces/http/{api.py, health.py, management/}`。
- `docs/07` §3.1（`docs/07` §14.1 同口径）—— Interface 层**允许**依赖 FastAPI
  （Web 框架属接口层的正当依赖），但**禁止** `Interface → SQLAlchemy` /
  `Interface → Adapter` / `Interface → Filesystem`。
- `docs/07` §14.4 —— Registry 校验失败 → Server MUST NOT become READY；
  单实例失败不得让整个服务器不可用。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **`/livez` 与 `/readyz` 恒返回 HTTP 200，状态在**响应体**里**：`docs/02` §16.2
   给出的返回体是 `{"status": "READY"}` —— 就绪与否是**载荷**，不是 HTTP 状态码。
   负载均衡器读的是**体**（`readyz` 探针的通行做法），把 `NOT_READY` 映射成 5xx
   会让「尚未就绪」看起来像「服务器故障」，并让重试策略误判。故三个端点都用
   `status_code=200`，**不**用 `HTTPException` 表达未就绪。
2. **路由器前缀为**空**字符串**：`docs/02` §16 / §94 的路径是**绝对**路径
   （`/livez` 而不是 `/health/livez`）。`HEALTH_ROUTER_PREFIX = ""` 把这个事实写进
   常量，`app/main.py` 挂载时**不**再叠加前缀。
3. **薄处理器（`docs/02` §3.3「Tool Thin Handler」同理）**：端点**只**调用
   `HealthService`，不含业务逻辑、不访问数据库、不访问 Adapter
   （`docs/07` §14.1 的 Interface 禁止项）。服务实例经 `create_health_router`
   的闭包注入，故端点本身不依赖任何全局单例。
4. **可脱离 HTTP 服务器测试**：`livez` / `readyz` / `health_report` 是**普通协程**
   （不是 `Request` 依赖的端点），路由只做转发。`docs/02` §41 要求的
   「最小可运行形态」因此可以在**不启动 uvicorn** 的情况下验收。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库、`fastapi` 与 `app.observability.health`：**不**引用 SQLAlchemy、
**不**依赖 `app.infrastructure` / `app.infrastructure.adapters`，也**不**出现任何
厂商专属内容。响应体**只**含 `HealthService` 给出的状态 / 原因 / 计数 ——
**绝不**含连接串、凭据或 payload（`docs/02` §46；`docs/07` §14.3）。
"""

from __future__ import annotations

from typing import Any, Final

from fastapi import APIRouter

from app.observability.health import (
    HEALTH_PATH,
    LIVENESS_PATH,
    READINESS_PATH,
    HealthService,
)

__all__ = [
    "HEALTH_ROUTER_PREFIX",
    "HEALTH_ROUTER_TAG",
    "INTERFACE_STAGE",
    "create_health_router",
    "health_report",
    "livez",
    "readyz",
]

HEALTH_ROUTER_PREFIX: Final[str] = ""
"""健康路由的前缀（见模块裁决 2：路径是**绝对**路径，故前缀为空串）。"""

HEALTH_ROUTER_TAG: Final[str] = "health"
"""OpenAPI 标签（`docs/02` §95 的管理面分组）。"""

INTERFACE_STAGE: Final[str] = "health_api"
"""本模块的 `stage` 取值（`docs/07` §11；HTTP 层不抛领域异常，故目前只作文档口径）。"""


async def livez(health: HealthService) -> dict[str, Any]:
    """`GET /livez` 的处理器（`docs/02` §16.1 / §94 的 `Process Alive`）。

    Args:
        health: 健康服务（由 `create_health_router` 注入）。

    Returns:
        `{"status": HEALTHY}` —— **不**咨询任何依赖（见 `HealthService.liveness`）。
    """
    return await health.liveness()


async def readyz(health: HealthService) -> dict[str, Any]:
    """`GET /readyz` 的处理器（`docs/02` §16.2 / §94 的就绪定义）。

    Args:
        health: 健康服务。

    Returns:
        `{"status": "READY"}` 或 `{"status": "NOT_READY", "checks": {...}}`。

    ⚠️ **不**把 `NOT_READY` 映射成 HTTP 错误码（见模块裁决 1）：状态在响应体里。
    """
    return await health.readiness()


async def health_report(health: HealthService) -> dict[str, Any]:
    """`GET /health` 的处理器（`docs/02` §16.3 / §94）。

    Args:
        health: 健康服务。

    Returns:
        完整健康载荷（`status` / `database` / `registry` / `task_engine` / `adapters`）。

    ⚠️ `docs/02` §46：该端点可能披露软件 / Adapter / 数据库信息，默认只应暴露在
    管理面或本地绑定的接口上（装配职责在 `app/main.py`，不在本模块）。
    """
    return await health.health()


def create_health_router(health: HealthService) -> APIRouter:
    """构造健康路由（`docs/02` §16 / §41 / §94 / §95）。

    Args:
        health: 健康服务实例；三个端点共享它（闭包注入，见模块裁决 3）。

    Returns:
        `APIRouter`，含三个 `GET` 端点（路径见 `LIVENESS_PATH` / `READINESS_PATH` /
        `HEALTH_PATH`），全部 `status_code=200`（见模块裁决 1）。

    ⚠️ 前缀为空串（见模块裁决 2）：挂载时**不**再叠加前缀，否则路径会变成
    `/health/livez`，与 `docs/02` §16 的绝对路径不符。
    """
    router = APIRouter(prefix=HEALTH_ROUTER_PREFIX, tags=[HEALTH_ROUTER_TAG])

    async def _livez() -> dict[str, Any]:
        return await livez(health)

    async def _readyz() -> dict[str, Any]:
        return await readyz(health)

    async def _health() -> dict[str, Any]:
        return await health_report(health)

    router.add_api_route(
        LIVENESS_PATH,
        _livez,
        methods=["GET"],
        status_code=200,
        name="liveness",
        summary="进程是否存活（docs/02 §16.1）",
    )
    router.add_api_route(
        READINESS_PATH,
        _readyz,
        methods=["GET"],
        status_code=200,
        name="readiness",
        summary="Core DB + Registry + Task Engine 是否就绪（docs/02 §16.2）",
    )
    router.add_api_route(
        HEALTH_PATH,
        _health,
        methods=["GET"],
        status_code=200,
        name="health",
        summary="完整健康（docs/02 §16.3 / §94）",
    )
    return router
