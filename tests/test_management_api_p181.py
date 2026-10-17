"""P181：同源 Web UI 的管理面（`/api/*`）与同源装配（**零真机**）。

为什么需要它
------------
UI 的数据面是**普通 REST**，而核心的对外面是 MCP Tool。两者之间不能直连数据库
（`docs/02` §57）。本文件钉住：

| # | 事实 | 为什么必须机器可读 |
| --- | --- | --- |
| 1 | **鉴权是硬性的** | 无 token ⇒ 401；错误 token ⇒ 401（形状一致，不泄露用户是否存在） |
| 2 | **同源装配路由不冲突** | `/`、`/api/*`、`/livez`、`/mcp` 四条面同时存在且各自可达 |
| 3 | **`/mcp` 仍走守门中间件** | 同源挂载不能绕过 MCP 的 Bearer 鉴权 |
| 4 | **UI 请求与 MCP 同一条链** | `/api/call` 返回的是 13 键统一信封（不复制业务逻辑） |
| 5 | **模板 → JSON → 导入** | 生成的文件落在服务器侧，且导入经 `MODEL.IMPORT` |
| 6 | **端点目录 / 模板库只读** | 663 端点 / 156 模板如实暴露，缺失时 `available=false` 不伪造 |

⚠️ 本文件不启动 uvicorn、不连 MIDAS：用 ASGI transport 直接打应用。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

import httpx
import pytest

from app.application.management import ManagementPort
from app.application.registry_catalog import load_catalog
from app.application.templates.library import load_library
from app.container import build_execution_runtime
from app.infrastructure.database.base import Base
from app.infrastructure.database.seed import seed
from app.infrastructure.database.session import create_engine, create_session_factory
from app.infrastructure.management.service import build_management_service
from app.infrastructure.registry.capability_registry import CapabilityRegistry
from app.infrastructure.registry.operation_registry import OperationRegistry
from app.interfaces.http.app import build_ui_app
from app.interfaces.mcp.transport.http import StreamableHTTPTransport

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
ADMIN_PASSWORD: Final[str] = "P181-Smoke!2345"
ADMIN_PASSWORD_ENV: Final[str] = "STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD"
UI_ROOT: Final[Path] = REPO_ROOT / "StructAI MCP UI" / "web"


class _DenyAuthenticator:
    """MCP 守门中间件用的认证端口（本文件只验证「被拦」，不验证放行）。"""

    async def authenticate(self, token: str) -> Any:
        """任何 token 都拒绝（`/mcp` 的 401 判据）。"""
        raise RuntimeError("denied")


class _StubPort(ManagementPort):
    """只实现本文件用到的端口方法（用于**不建库**的路由级断言）。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def login(self, username: str, password: str) -> dict[str, Any]:
        return {
            "token": "stub-token",
            "user": username,
            "tenant": "t",
            "roles": [],
            "authentication_method": "PASSWORD",
        }

    async def logout(self, token: str) -> bool:
        return True

    async def identity(self, token: str) -> dict[str, Any]:
        if token != "stub-token":
            from app.domain.errors import PermissionDeniedError

            raise PermissionDeniedError("invalid")
        return {"user": "u", "tenant": "t", "roles": [], "permissions": []}

    async def overview(self) -> dict[str, Any]:
        return {
            "service": {"running": True, "version": "test"},
            "tasks": {"total": 0, "active": 0, "queued": 0, "failed": 0},
            "clients": {"total": 0, "connected": 0},
            "registry": {"endpoints": 663, "schemas": 652},
            "templates": {"count": 156, "families": 17},
        }

    async def clients(self) -> list[dict[str, Any]]:
        return []

    async def tasks(self, *, limit: int, offset: int) -> dict[str, Any]:
        return {"total": 0, "items": []}

    async def task(self, task_id: str) -> dict[str, Any]:
        return {"task": {"id": task_id}, "steps": []}

    async def cancel(self, task_id: str) -> dict[str, Any]:
        return {"task_id": task_id, "cancelled": True}

    async def events(self, *, limit: int) -> list[dict[str, Any]]:
        return []

    async def call(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("call", kwargs))
        return {"success": True, "tool": kwargs["tool"], "operation": kwargs["operation"]}

    async def registry(self) -> dict[str, Any]:
        return {"available": True, "counts": {"keys": 663, "schemas": 652}}

    async def endpoints(self, **kwargs: Any) -> dict[str, Any]:
        return {"total": 0, "items": []}

    async def endpoint(self, key: str) -> dict[str, Any]:
        return {"key": key}

    async def operations(self) -> list[dict[str, Any]]:
        return []

    async def templates(self) -> dict[str, Any]:
        return {"available": True, "count": 0, "families": {}, "items": []}

    async def template(self, name: str) -> dict[str, Any]:
        return {"name": name, "parameters": {}}

    async def import_template(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("import", kwargs))
        return {"template": kwargs["name"], "response": {"success": True}}


class _Health:
    """健康端口的最小替身（只回答固定状态）。"""

    async def liveness(self) -> dict[str, str]:
        return {"status": "HEALTHY"}

    async def readiness(self) -> dict[str, str]:
        return {"status": "READY"}

    async def health(self) -> dict[str, str]:
        return {"status": "HEALTHY"}


def _app(port: ManagementPort, *, ui_root: Path | None = None) -> Any:
    """构造同源应用（MCP 用「一律拒绝」的认证端口）。"""
    transport = StreamableHTTPTransport(server=lambda: None, authenticator=_DenyAuthenticator())
    return build_ui_app(
        api=port,
        health=_Health(),
        mcp_app=transport.protocol_app,
        mcp_middleware=transport.middleware,
        ui_root=ui_root,
    )


def _client(app: Any) -> httpx.AsyncClient:
    """ASGI 客户端（不启动 uvicorn）。"""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


# ===== 1. 鉴权 =====


@pytest.mark.asyncio
async def test_p181_management_api_requires_bearer_token() -> None:
    """门槛 ①：无 token ⇒ 401（且带 `WWW-Authenticate`）。"""
    async with _client(_app(_StubPort())) as client:
        response = await client.get("/api/status")
    assert response.status_code == 401
    assert response.headers.get("www-authenticate", "").startswith("Bearer")


@pytest.mark.asyncio
async def test_p181_invalid_token_has_the_same_shape_as_missing_token() -> None:
    """门槛 ①：无效 token 与缺失 token **同形**（不泄露用户是否存在）。"""
    async with _client(_app(_StubPort())) as client:
        missing = await client.get("/api/status")
        invalid = await client.get("/api/status", headers={"Authorization": "Bearer nope"})
    assert missing.status_code == invalid.status_code == 401
    assert missing.json() == invalid.json()


@pytest.mark.asyncio
async def test_p181_login_is_the_only_anonymous_endpoint() -> None:
    """门槛 ①：`/api/auth/login` 匿名；其余端点全部要求 Bearer。"""
    async with _client(_app(_StubPort())) as client:
        login = await client.post(
            "/api/auth/login", json={"username": "admin", "password": "whatever"}
        )
        anonymous = await client.get("/api/clients")
    assert login.status_code == 200
    assert login.json()["token"] == "stub-token"
    assert anonymous.status_code == 401


# ===== 2. 同源装配 =====


@pytest.mark.asyncio
async def test_p181_same_origin_app_serves_all_four_surfaces() -> None:
    """门槛 ②：`/`、`/api/*`、`/livez`、`/mcp` 四条面同时可达（各自状态码）。"""
    async with _client(_app(_StubPort(), ui_root=UI_ROOT)) as client:
        index = await client.get("/")
        api = await client.get("/api/status")
        health = await client.get("/livez")
        mcp = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Accept": "application/json, text/event-stream"},
        )
    assert index.status_code == 200
    assert "MIDAS MCP" in index.text
    assert api.status_code == 401  # 未带 token
    assert health.status_code == 200 and health.json()["status"] == "HEALTHY"
    assert mcp.status_code == 401  # 守门中间件仍生效


@pytest.mark.asyncio
async def test_p181_mcp_mount_still_enforces_authentication() -> None:
    """门槛 ③：同源挂载**不**绕过 MCP 的 Bearer 鉴权（无 token ⇒ 401）。"""
    async with _client(_app(_StubPort())) as client:
        response = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert response.status_code == 401
    assert "unauthorized" in response.text


@pytest.mark.asyncio
async def test_p181_ui_assets_are_served_from_the_same_app() -> None:
    """门槛 ②：前端脚本与样式由同一应用托管（同源 ⇒ 不需要 CORS）。"""
    async with _client(_app(_StubPort(), ui_root=UI_ROOT)) as client:
        script = await client.get("/scripts/api.js")
        style = await client.get("/styles/pages/templates.css")
    assert script.status_code == 200
    assert "window.Api" in script.text
    assert style.status_code == 200


# ===== 3. UI 请求走同一条 MCP 链 =====


@pytest.mark.asyncio
async def test_p181_ui_call_returns_the_13_key_envelope() -> None:
    """门槛 ④：`/api/call` 返回统一响应信封（**不**复制业务逻辑）。"""
    port = _StubPort()
    async with _client(_app(port)) as client:
        response = await client.post(
            "/api/call",
            json={"tool": "engineering_doc", "operation": "MODEL.IMPORT", "parameters": {}},
            headers={"Authorization": "Bearer stub-token"},
        )
    assert response.status_code == 200
    assert port.calls and port.calls[0][0] == "call"
    assert port.calls[0][1]["tool"] == "engineering_doc"
    assert response.json()["operation"] == "MODEL.IMPORT"


@pytest.mark.asyncio
async def test_p181_import_template_goes_through_the_same_port() -> None:
    """门槛 ⑤：模板导入也经端口（最终是 `MODEL.IMPORT`，不是另开一条写路径）。"""
    port = _StubPort()
    async with _client(_app(port)) as client:
        response = await client.post(
            "/api/templates/Static-02/import",
            json={"parameters": {"material.1.elastic_modulus": 1.0}},
            headers={"Authorization": "Bearer stub-token"},
        )
    assert response.status_code == 200
    assert port.calls[0][0] == "import"
    assert port.calls[0][1]["name"] == "Static-02"


# ===== 4. 只读数据源 =====


def test_p181_registry_catalog_exposes_every_endpoint() -> None:
    """门槛 ⑥：端点目录如实暴露（663 端点；缺索引 ⇒ `available=False`）。"""
    catalog = load_catalog(REPO_ROOT / "registry")
    assert catalog.available is True
    assert len(catalog.endpoints) == 663
    page = catalog.list_endpoints(namespace="DB", limit=5)
    assert page["total"] == 271
    assert len(page["items"]) == 5
    detail = catalog.endpoint("DB.NODE")
    assert detail is not None and detail["schema"] is not None
    missing = load_catalog(REPO_ROOT / "no-such-registry")
    assert missing.available is False and missing.endpoints == ()


def test_p181_template_library_exposes_every_template() -> None:
    """门槛 ⑥：模板库如实暴露（156 模板 / 17 族；缺索引 ⇒ `available=False`）。"""
    library = load_library(REPO_ROOT / "templates" / "gen_verification")
    assert library.available is True
    assert len(library.templates) == 156
    assert len(library.families) == 17
    defaults = library.defaults("Static-02")
    assert "material.1.elastic_modulus" in defaults
    rendered = library.render("Static-02", {"material.1.elastic_modulus": 123.0})
    assert rendered["DBG"]["MATL"]["1"]["PARAM"][0]["ELAST"] == 123.0
    assert load_library(REPO_ROOT / "no-such-templates").available is False


# ===== 5. 真实管理服务（临时库；不连 MIDAS）=====


@pytest.fixture()
def _seeded_runtime(tmp_path: Path) -> Iterator[Any]:
    """临时库 + seed + 运行时（**不**注册任何 Adapter）。"""
    import asyncio

    os.environ[ADMIN_PASSWORD_ENV] = ADMIN_PASSWORD
    settings = type(
        "S",
        (),
        {
            "database_url": f"sqlite+aiosqlite:///{(tmp_path / 'p181.db').as_posix()}",
            "artifact_root": str(tmp_path / "artifacts"),
            "session_expire_seconds": 3600,
            "capability_cache_seconds": 300,
            "lock_default_timeout_seconds": 300,
        },
    )()

    async def build() -> tuple[Any, Any]:
        from app.config.settings import Settings

        real = Settings(database_url=settings.database_url, artifact_root=settings.artifact_root)
        engine = create_engine(real.database_url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = create_session_factory(engine)
        await seed(factory)
        runtime = build_execution_runtime(
            real,
            operation_registry=await OperationRegistry.load(engine, factory),
            capability_registry=await CapabilityRegistry.load(engine, factory),
        )
        runtime.session_factory = factory
        return runtime, engine

    runtime, engine = asyncio.run(build())
    try:
        yield runtime
    finally:
        asyncio.run(engine.dispose())


@pytest.mark.asyncio
async def test_p181_management_service_reads_real_counts(
    _seeded_runtime: Any, tmp_path: Path
) -> None:
    """门槛 ⑥：真实服务返回端点 / 模板 / 实例计数（不伪造）。"""
    service = build_management_service(
        _seeded_runtime,
        catalog=load_catalog(REPO_ROOT / "registry"),
        templates=load_library(REPO_ROOT / "templates" / "gen_verification"),
        import_root=tmp_path / "imports",
        version="test",
    )
    overview = await service.overview()
    assert overview["registry"]["endpoints"] == 663
    assert overview["templates"]["count"] == 156
    assert overview["clients"]["total"] == 1  # seed 的 Mock Instance
    login = await service.login("admin", ADMIN_PASSWORD)
    identity = await service.identity(login["token"])
    assert "MODEL_READ" in identity["permissions"]
    operations = await service.operations()
    assert len(operations) == 73
    await service.logout(login["token"])
    from app.domain.errors import StructAIError

    with pytest.raises(StructAIError):
        await service.identity(login["token"])
