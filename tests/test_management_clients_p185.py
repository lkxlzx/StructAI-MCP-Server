"""P185：MIDAS 客户端 CRUD 与系统设置的完整能力（**零真机**）。

覆盖：

| # | 事实 |
| --- | --- |
| 1 | 客户端可新增 / 编辑 / 删除，软件注册链按需创建并清理孤儿 |
| 2 | 连接测试如实报告（未配置地址 / 不可达地址） |
| 3 | 客户端事件写入本机运维库 |
| 4 | 角色可新增 / 删除（系统管理员与仍被引用的角色拒绝） |
| 5 | 口令按「安全设置 · 密码策略」校验，历史口令拒绝复用 |
| 6 | 备份包含设置库；恢复会先生成 pre-restore 备份 |
| 7 | 导出 / 导入设置；清空数据保留审计与管理员 |
| 8 | 日志与目录浏览端点可用 |
| 9 | 写操作要求 `SYSTEM_ADMIN`（viewer ⇒ 403） |

⚠️ 不启动 uvicorn、不连 MIDAS：用 ASGI transport 直接打应用。
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

import httpx
import pytest

from app.application.registry_catalog import load_catalog
from app.application.templates.library import load_library
from app.config.settings import Settings
from app.container import build_execution_runtime
from app.infrastructure.database.base import Base
from app.infrastructure.database.seed import seed
from app.infrastructure.database.session import create_engine, create_session_factory
from app.infrastructure.management.service import build_management_service
from app.infrastructure.management.settings import build_settings_store
from app.infrastructure.registry.capability_registry import CapabilityRegistry
from app.infrastructure.registry.operation_registry import OperationRegistry
from app.interfaces.http.app import build_ui_app
from app.interfaces.mcp.transport.http import StreamableHTTPTransport

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
ADMIN_PASSWORD: Final[str] = "P185-Smoke!2345"
ADMIN_PASSWORD_ENV: Final[str] = "STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD"


class _Health:
    """健康端口的最小替身。"""

    async def liveness(self) -> dict[str, str]:
        return {"status": "HEALTHY"}

    async def readiness(self) -> dict[str, str]:
        return {"status": "READY"}

    async def health(self) -> dict[str, str]:
        return {"status": "HEALTHY"}


class _DenyAuthenticator:
    """MCP 守门中间件用的认证端口（本文件只验证管理面）。"""

    async def authenticate(self, token: str) -> Any:
        raise RuntimeError("denied")


@pytest.fixture()
def app(tmp_path: Path) -> Iterator[Any]:
    """临时库 + seed + 同源应用（设置文件落在临时目录）。"""
    os.environ[ADMIN_PASSWORD_ENV] = ADMIN_PASSWORD
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'p185.db').as_posix()}",
        artifact_root=str(tmp_path / "artifacts"),
        management_import_root=str(tmp_path / "management"),
    )

    async def build() -> tuple[Any, Any]:
        engine = create_engine(settings.database_url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = create_session_factory(engine)
        await seed(factory)
        runtime = build_execution_runtime(
            settings,
            operation_registry=await OperationRegistry.load(engine, factory),
            capability_registry=await CapabilityRegistry.load(engine, factory),
        )
        runtime.session_factory = factory
        return runtime, engine

    runtime, engine = asyncio.run(build())
    service = build_management_service(
        runtime,
        catalog=load_catalog(REPO_ROOT / "registry"),
        templates=load_library(REPO_ROOT / "templates" / "gen_verification"),
        import_root=tmp_path / "imports",
        version="test",
        settings=build_settings_store(tmp_path / "management" / "settings.db"),
    )
    transport = StreamableHTTPTransport(server=lambda: None, authenticator=_DenyAuthenticator())
    yield build_ui_app(
        api=service,
        health=_Health(),
        mcp_app=transport.protocol_app,
        mcp_middleware=transport.middleware,
        ui_root=None,
    )
    asyncio.run(engine.dispose())


def _client(app: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _auth(client: httpx.AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


# ===== 1. 客户端 CRUD =====


@pytest.mark.asyncio
async def test_client_create_update_delete_roundtrip(app: Any) -> None:
    """新增 → 列表 → 编辑 → 删除；软件注册链按需创建。"""
    async with _client(app) as client:
        headers = await _auth(client)
        created = await client.post(
            "/api/clients",
            headers=headers,
            json={
                "name": "CIVIL NX (本机)",
                "vendor": "MIDAS",
                "product": "CIVIL NX",
                "version": "2024",
                "endpoint": "http://127.0.0.1:4010",
                "description": "本机实例",
            },
        )
        assert created.status_code == 200, created.text
        body = created.json()
        assert body["name"] == "CIVIL NX (本机)"
        assert body["description"] == "本机实例"
        client_id = body["id"]

        listed = await client.get("/api/clients", headers=headers)
        names = [item["name"] for item in listed.json()["items"]]
        assert "CIVIL NX (本机)" in names

        updated = await client.put(
            f"/api/clients/{client_id}",
            headers=headers,
            json={"name": "CIVIL NX (改名)", "version": "2025", "description": "改名后"},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "CIVIL NX (改名)"
        assert updated.json()["version"] == "2025"
        assert updated.json()["description"] == "改名后"

        removed = await client.delete(f"/api/clients/{client_id}", headers=headers)
        assert removed.status_code == 200
        remaining = await client.get("/api/clients", headers=headers)
        assert all(item["id"] != client_id for item in remaining.json()["items"])

        # 种子实例仍在（删除只清理自己创建的那条链）
        assert any(item["name"] == "Mock Instance" for item in remaining.json()["items"])


@pytest.mark.asyncio
async def test_client_create_requires_core_fields(app: Any) -> None:
    """缺名称 / 厂商 / 产品 / 版本 ⇒ `STRUCTAI-1000`。"""
    async with _client(app) as client:
        headers = await _auth(client)
        response = await client.post("/api/clients", headers=headers, json={"name": "x"})
        assert response.status_code == 400
        assert response.json()["details"]["reason"] == "client_fields_missing"


@pytest.mark.asyncio
async def test_client_options_lists_registered_chain(app: Any) -> None:
    """候选值来自已登记的软件链（种子实例可见）。"""
    async with _client(app) as client:
        headers = await _auth(client)
        response = await client.get("/api/clients/options", headers=headers)
        assert response.status_code == 200
        payload = response.json()
        assert any(item["vendor"] == "StructAI" for item in payload["software"])
        assert any(item["product"] == "Mock Engineering Software" for item in payload["products"])
        assert any(item["version"] == "1.0" for item in payload["versions"])
        assert "CONNECTED" in payload["statuses"]


# ===== 2. 连接测试 / 事件 =====


@pytest.mark.asyncio
async def test_client_test_reports_unconfigured_endpoint(app: Any) -> None:
    """无地址 ⇒ `endpoint_not_configured`（不伪造可达）。"""
    async with _client(app) as client:
        headers = await _auth(client)
        clients = (await client.get("/api/clients", headers=headers)).json()["items"]
        seed_client = next(item for item in clients if item["name"] == "Mock Instance")
        result = await client.post(f"/api/clients/{seed_client['id']}/test", headers=headers)
        assert result.status_code == 200
        assert result.json()["reachable"] is False
        assert result.json()["reason"] == "endpoint_not_configured"

        events = await client.get(f"/api/clients/{seed_client['id']}/events", headers=headers)
        assert events.status_code == 200
        assert any(item["action"] == "test_connection" for item in events.json()["items"])


@pytest.mark.asyncio
async def test_client_test_reports_unreachable_endpoint(app: Any) -> None:
    """不可达地址 ⇒ `reachable=False`（真实探测，不抛 500）。"""
    async with _client(app) as client:
        headers = await _auth(client)
        created = await client.post(
            "/api/clients",
            headers=headers,
            json={
                "name": "Unreachable",
                "vendor": "MIDAS",
                "product": "CIVIL NX",
                "version": "2024",
                "endpoint": "http://127.0.0.1:1",
            },
        )
        client_id = created.json()["id"]
        result = await client.post(f"/api/clients/{client_id}/test", headers=headers)
        assert result.status_code == 200
        assert result.json()["reachable"] is False
        assert result.json()["reason"]


# ===== 3. 角色增删 =====


@pytest.mark.asyncio
async def test_role_create_and_delete(app: Any) -> None:
    """新建角色 → 出现在列表；删除后消失；系统管理员角色拒绝删除。"""
    async with _client(app) as client:
        headers = await _auth(client)
        created = await client.post(
            "/api/roles",
            headers=headers,
            json={"name": "analyst", "permissions": ["MODEL_READ", "RESULT_READ"]},
        )
        assert created.status_code == 200, created.text
        role_id = created.json()["id"]
        assert created.json()["permissions"] == ["MODEL_READ", "RESULT_READ"]

        roles = (await client.get("/api/roles", headers=headers)).json()
        assert any(item["id"] == role_id for item in roles["items"])

        removed = await client.delete(f"/api/roles/{role_id}", headers=headers)
        assert removed.status_code == 200
        roles = (await client.get("/api/roles", headers=headers)).json()
        assert all(item["id"] != role_id for item in roles["items"])

        admin_role = next(item for item in roles["items"] if item["name"] == "system_admin")
        refused = await client.delete(f"/api/roles/{admin_role['id']}", headers=headers)
        assert refused.status_code == 400
        assert refused.json()["details"]["reason"] == "system_role"


@pytest.mark.asyncio
async def test_role_delete_refuses_when_users_are_assigned(app: Any) -> None:
    """仍被用户引用的角色拒绝删除。"""
    async with _client(app) as client:
        headers = await _auth(client)
        created = await client.post(
            "/api/roles",
            headers=headers,
            json={"name": "in-use", "permissions": ["MODEL_READ"]},
        )
        role_id = created.json()["id"]
        user = await client.post(
            "/api/users",
            headers=headers,
            json={"username": "inuse", "password": "InUse!2345", "roles": ["in-use"]},
        )
        assert user.status_code == 200, user.text
        response = await client.delete(f"/api/roles/{role_id}", headers=headers)
        assert response.status_code == 400
        assert response.json()["details"]["reason"] == "role_in_use"


# ===== 4. 口令策略 / 历史 =====


@pytest.mark.asyncio
async def test_password_policy_is_enforced_on_create_and_update(app: Any) -> None:
    """弱口令拒绝；策略放宽后可创建。"""
    async with _client(app) as client:
        headers = await _auth(client)
        weak = await client.post(
            "/api/users", headers=headers, json={"username": "weak", "password": "abc"}
        )
        assert weak.status_code == 400
        assert weak.json()["details"]["reason"] == "password_policy"
        assert weak.json()["details"]["problems"]

        check = await client.post(
            "/api/users/password/check", headers=headers, json={"password": "Abc!23456"}
        )
        assert check.status_code == 200
        assert check.json()["valid"] is True

        relaxed = await client.put(
            "/api/settings/security",
            headers=headers,
            json={
                "password": {
                    "require_special": False,
                    "require_upper": False,
                    "require_digit": False,
                    "min_length": 6,
                }
            },
        )
        assert relaxed.status_code == 200
        created = await client.post(
            "/api/users", headers=headers, json={"username": "weak2", "password": "abcdef"}
        )
        assert created.status_code == 200, created.text


@pytest.mark.asyncio
async def test_password_history_rejects_reuse(app: Any) -> None:
    """修改口令时拒绝复用最近用过的口令。"""
    async with _client(app) as client:
        headers = await _auth(client)
        created = await client.post(
            "/api/users",
            headers=headers,
            json={"username": "history", "password": "First!2345"},
        )
        user_id = created.json()["id"]
        first = await client.put(
            f"/api/users/{user_id}", headers=headers, json={"password": "Second!2345"}
        )
        assert first.status_code == 200
        reused = await client.put(
            f"/api/users/{user_id}", headers=headers, json={"password": "First!2345"}
        )
        assert reused.status_code == 400
        assert reused.json()["details"]["reason"] == "password_reused"


# ===== 5. 备份 / 恢复 / 导入 / 清空 =====


@pytest.mark.asyncio
async def test_backup_includes_settings_and_can_restore(app: Any) -> None:
    """备份包含设置库；恢复先生成 pre-restore 备份。"""
    async with _client(app) as client:
        headers = await _auth(client)
        await client.put("/api/settings/interface", headers=headers, json={"theme": "dark"})
        created = await client.post("/api/data/backup", headers=headers)
        assert created.status_code == 200, created.text
        backup_id = created.json()["backup_id"]
        assert created.json()["settings"]["size"] > 0

        # 改回浅色后再恢复 → 主题回到 dark
        await client.put("/api/settings/interface", headers=headers, json={"theme": "light"})
        restored = await client.post(f"/api/data/backups/{backup_id}/restore", headers=headers)
        assert restored.status_code == 200, restored.text
        assert restored.json()["restored"] is True
        assert restored.json()["settings_restored"] is True
        assert restored.json()["pre_restore_backup"]
        settings = (await client.get("/api/settings", headers=headers)).json()
        assert settings["interface"]["theme"] == "dark"


@pytest.mark.asyncio
async def test_import_data_replaces_settings_sections(app: Any) -> None:
    """导入只接受 settings 对象；未知分区忽略。"""
    async with _client(app) as client:
        headers = await _auth(client)
        bad = await client.post("/api/data/import", headers=headers, json={"x": 1})
        assert bad.status_code == 400

        imported = await client.post(
            "/api/data/import",
            headers=headers,
            json={"settings": {"interface": {"theme": "dark"}, "nope": {"x": 1}}},
        )
        assert imported.status_code == 200
        assert imported.json()["imported"] == ["interface"]
        settings = (await client.get("/api/settings", headers=headers)).json()
        assert settings["interface"]["theme"] == "dark"


@pytest.mark.asyncio
async def test_purge_keeps_admins_roles_and_audit(app: Any) -> None:
    """清空业务数据后管理员仍在，审计计数固定为 0（不删除）。"""
    async with _client(app) as client:
        headers = await _auth(client)
        response = await client.post("/api/data/purge", headers=headers)
        assert response.status_code == 200
        assert response.json()["removed"]["audit"] == 0
        # 清空会删除会话；用口令重新登录（用户 / 角色未被清空）
        headers = await _auth(client)
        users = (await client.get("/api/users", headers=headers)).json()["items"]
        assert any(item["username"] == "admin" for item in users)
        roles = (await client.get("/api/roles", headers=headers)).json()["items"]
        assert len(roles) == 4


# ===== 6. 日志 / 目录浏览 =====


@pytest.mark.asyncio
async def test_logs_endpoint_reports_availability(app: Any) -> None:
    """日志端点如实报告（未启用文件日志 ⇒ available=False 或返回行）。"""
    async with _client(app) as client:
        headers = await _auth(client)
        response = await client.get("/api/logs", headers=headers)
        assert response.status_code == 200
        payload = response.json()
        assert "available" in payload and isinstance(payload["items"], list)


@pytest.mark.asyncio
async def test_browse_lists_directories(app: Any, tmp_path: Path) -> None:
    """目录浏览只列子目录；不存在的目录 ⇒ 404。"""
    async with _client(app) as client:
        headers = await _auth(client)
        (tmp_path / "subdir").mkdir()
        response = await client.get(
            "/api/fs/browse", headers=headers, params={"path": str(tmp_path)}
        )
        assert response.status_code == 200
        names = [item["name"] for item in response.json()["items"]]
        assert "subdir" in names

        missing = await client.get(
            "/api/fs/browse", headers=headers, params={"path": str(tmp_path / "nope")}
        )
        assert missing.status_code == 404


# ===== 7. 管理员权限门 =====


@pytest.mark.asyncio
async def test_write_operations_require_system_admin(app: Any) -> None:
    """viewer 登录后写操作 ⇒ 403；只读端点仍可用。"""
    async with _client(app) as client:
        admin_headers = await _auth(client)
        created = await client.post(
            "/api/users",
            headers=admin_headers,
            json={"username": "viewer1", "password": "Viewer!2345", "roles": ["viewer"]},
        )
        assert created.status_code == 200, created.text

        login = await client.post(
            "/api/auth/login", json={"username": "viewer1", "password": "Viewer!2345"}
        )
        assert login.status_code == 200
        viewer_headers = {"Authorization": "Bearer " + login.json()["token"]}

        allowed = await client.get("/api/settings", headers=viewer_headers)
        assert allowed.status_code == 200

        forbidden = await client.put(
            "/api/settings/interface", headers=viewer_headers, json={"theme": "dark"}
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["details"]["reason"] == "admin_required"

        forbidden_client = await client.post(
            "/api/clients",
            headers=viewer_headers,
            json={"name": "x", "vendor": "MIDAS", "product": "CIVIL NX", "version": "2024"},
        )
        assert forbidden_client.status_code == 403


@pytest.mark.asyncio
async def test_access_control_blacklist_blocks_login(app: Any) -> None:
    """黑名单命中 ⇒ 登录 403（配置写入后立即生效）。"""
    async with _client(app) as client:
        headers = await _auth(client)
        await client.put(
            "/api/settings/security",
            headers=headers,
            json={"access": {"blacklist_enabled": True, "blacklist": "127.0.0.1"}},
        )
        blocked = await client.post(
            "/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}
        )
        assert blocked.status_code == 403
        assert blocked.json()["details"]["reason"] == "blacklisted"


# ===== 8. 连接 / 断开（P185）=====


@pytest.mark.asyncio
async def test_connect_reports_missing_endpoint(app: Any) -> None:
    """未配置地址 ⇒ `base_url_not_configured`（不伪造连接成功）。"""
    async with _client(app) as client:
        headers = await _auth(client)
        created = await client.post(
            "/api/clients",
            headers=headers,
            json={"name": "NoAddr", "vendor": "MIDAS", "product": "CIVIL NX", "version": "2025"},
        )
        client_id = created.json()["id"]
        result = await client.post(f"/api/clients/{client_id}/connect", headers=headers)
        assert result.status_code == 200
        assert result.json()["connected"] is False
        assert result.json()["reason"] == "base_url_not_configured"
        listed = (await client.get("/api/clients", headers=headers)).json()["items"]
        assert next(item for item in listed if item["id"] == client_id)["status"] == "DEGRADED"


@pytest.mark.asyncio
async def test_connect_unknown_vendor_is_rejected(app: Any) -> None:
    """没有可用 Adapter ⇒ `STRUCTAI-1000` + `adapter_not_found`。"""
    async with _client(app) as client:
        headers = await _auth(client)
        created = await client.post(
            "/api/clients",
            headers=headers,
            json={"name": "Unknown", "vendor": "Nope", "product": "X", "version": "1"},
        )
        result = await client.post(f"/api/clients/{created.json()['id']}/connect", headers=headers)
        assert result.status_code == 400
        assert result.json()["details"]["reason"] == "adapter_not_found"


@pytest.mark.asyncio
async def test_disconnect_is_idempotent_and_updates_status(app: Any) -> None:
    """断开未连接的实例也成功，并把状态写回 `DISCONNECTED`。"""
    async with _client(app) as client:
        headers = await _auth(client)
        created = await client.post(
            "/api/clients",
            headers=headers,
            json={
                "name": "Idle",
                "vendor": "MIDAS",
                "product": "CIVIL NX",
                "version": "2025",
                "status": "CONNECTED",
            },
        )
        client_id = created.json()["id"]
        result = await client.post(f"/api/clients/{client_id}/disconnect", headers=headers)
        assert result.status_code == 200
        assert result.json()["connected"] is False
        listed = (await client.get("/api/clients", headers=headers)).json()["items"]
        assert next(item for item in listed if item["id"] == client_id)["status"] == "DISCONNECTED"


def test_adapter_plugins_are_discovered_without_vendor_names() -> None:
    """适配器发现按子包扫描（Core 内不写厂商名），能解析出注册键。"""
    from app.infrastructure.adapters.plugins import adapter_class_for, discover_adapters

    found = discover_adapters()
    assert ("MIDAS", "CIVIL NX") in found
    assert ("CSI", "ETABS") in found
    # 同厂商的其它产品复用同一实现（产品由连接配置选择）
    assert adapter_class_for("MIDAS", "GEN NX") is found[("MIDAS", "CIVIL NX")]
    assert adapter_class_for("Nope", "X") is None
