"""P183：系统设置的持久化与管理端点（**零真机**）。

为什么需要它
------------
P181 只覆盖了「只读管理面」。系统设置页要能**真正操作**，本批补齐：

| # | 事实 | 为什么必须机器可读 |
| --- | --- | --- |
| 1 | 设置分区可读写、深合并、未知分区拒绝 | 前端每个开关 / 下拉都落在分区上 |
| 2 | `system` 分区只读 | 版本 / 运行环境由进程给出，不能被前端覆盖 |
| 3 | 设置文件**独立于 Core 库** | `docs/07` §4.3 的 24 张表是冻结口径 |
| 4 | 用户 CRUD（口令只落 Argon2id 哈希） | 「用户与权限」页的新建 / 编辑 / 禁用 |
| 5 | 角色权限可改，未知权限码拒绝 | 权限码是 12 码封闭集合 |
| 6 | 模型列表整体替换（列表不做深合并） | 设为默认 / 删除模型 |
| 7 | 备份用 SQLite backup API，可列出 / 删除 | 数据管理页 |
| 8 | 清理**不删审计记录** | `docs/02` §29 / §45 |

⚠️ 本文件不启动 uvicorn、不连 MIDAS：用 ASGI transport 直接打应用。
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
ADMIN_PASSWORD: Final[str] = "P183-Smoke!2345"
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
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'p183.db').as_posix()}",
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
    """ASGI 客户端（不启动 uvicorn）。"""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _auth(client: httpx.AsyncClient) -> dict[str, str]:
    """登录并返回 Bearer 头。"""
    response = await client.post(
        "/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


# ===== 1. 设置读写 =====


@pytest.mark.asyncio
async def test_settings_requires_authentication(app: Any) -> None:
    """门槛 ①：设置端点与其它管理端点同口径（无 token ⇒ 401）。"""
    async with _client(app) as client:
        for path in ("/api/settings", "/api/users", "/api/roles", "/api/models"):
            response = await client.get(path)
            assert response.status_code == 401, path


@pytest.mark.asyncio
async def test_settings_read_merges_defaults_with_stored_values(app: Any) -> None:
    """门槛 ①：读取返回全部默认分区；写入后**只**覆盖给出的键。"""
    async with _client(app) as client:
        headers = await _auth(client)
        initial = await client.get("/api/settings", headers=headers)
        assert initial.status_code == 200
        payload = initial.json()
        for section in (
            "behavior",
            "interface",
            "paths",
            "notify",
            "service",
            "security",
            "models",
            "data",
            "system",
        ):
            assert section in payload, section
        assert payload["interface"]["theme"] == "light"

        saved = await client.put("/api/settings/interface", headers=headers, json={"theme": "dark"})
        assert saved.status_code == 200
        assert saved.json()["values"]["theme"] == "dark"
        # 深合并：未给出的键保持默认值
        assert saved.json()["values"]["page_size"] == 10

        reread = await client.get("/api/settings", headers=headers)
        assert reread.json()["interface"]["theme"] == "dark"


@pytest.mark.asyncio
async def test_settings_system_section_is_read_only(app: Any) -> None:
    """门槛 ②：`system` 由进程给出，写入被忽略。"""
    async with _client(app) as client:
        headers = await _auth(client)
        before = (await client.get("/api/settings", headers=headers)).json()["system"]
        response = await client.put(
            "/api/settings/system", headers=headers, json={"version": "forged"}
        )
        assert response.status_code == 200
        after = (await client.get("/api/settings", headers=headers)).json()["system"]
        assert after["version"] == before["version"] != "forged"
        assert after["python"] and after["platform"]


@pytest.mark.asyncio
async def test_unknown_settings_section_is_rejected(app: Any) -> None:
    """门槛 ①：未知分区 ⇒ `STRUCTAI-1000`（不静默落库）。"""
    async with _client(app) as client:
        headers = await _auth(client)
        response = await client.put("/api/settings/nope", headers=headers, json={"x": 1})
        assert response.status_code == 400
        assert response.json()["code"] == "STRUCTAI-1000"


@pytest.mark.asyncio
async def test_settings_reset_restores_defaults(app: Any) -> None:
    """门槛 ①：`/api/settings/reset` 把分区恢复为默认值。"""
    async with _client(app) as client:
        headers = await _auth(client)
        await client.put("/api/settings/behavior", headers=headers, json={"log_retention_days": 99})
        reset = await client.post(
            "/api/settings/reset", headers=headers, json={"section": "behavior"}
        )
        assert reset.status_code == 200
        assert reset.json()["behavior"]["log_retention_days"] == 30


# ===== 2. 用户与角色 =====


@pytest.mark.asyncio
async def test_user_crud_never_exposes_password_hash(app: Any) -> None:
    """门槛 ④：新建 / 更新 / 删除用户；响应**不含** `password_hash`。"""
    async with _client(app) as client:
        headers = await _auth(client)
        created = await client.post(
            "/api/users",
            headers=headers,
            json={
                "username": "p183-user",
                "password": "Abc!23456",
                "roles": ["engineer"],
                "display_name": "测试用户",
                "email": "p183@example.com",
            },
        )
        assert created.status_code == 200, created.text
        body = created.json()
        assert "password_hash" not in body
        assert body["role_label"] == "工程师"
        user_id = body["id"]

        listed = await client.get("/api/users", headers=headers)
        assert listed.status_code == 200
        assert any(item["username"] == "p183-user" for item in listed.json()["items"])

        updated = await client.put(
            f"/api/users/{user_id}",
            headers=headers,
            json={"is_active": False, "roles": ["viewer"], "display_name": "改名"},
        )
        assert updated.status_code == 200
        assert updated.json()["is_active"] is False
        assert updated.json()["role_label"] == "访客"

        removed = await client.delete(f"/api/users/{user_id}", headers=headers)
        assert removed.status_code == 200
        remaining = await client.get("/api/users", headers=headers)
        assert all(item["id"] != user_id for item in remaining.json()["items"])


@pytest.mark.asyncio
async def test_duplicate_username_and_last_admin_are_rejected(app: Any) -> None:
    """门槛 ④：用户名唯一；**不允许**删除最后一个管理员。"""
    async with _client(app) as client:
        headers = await _auth(client)
        duplicate = await client.post(
            "/api/users", headers=headers, json={"username": "admin", "password": "Abc!23456"}
        )
        assert duplicate.status_code == 400
        assert duplicate.json()["details"]["reason"] == "username_taken"

        users = (await client.get("/api/users", headers=headers)).json()["items"]
        admin = next(item for item in users if item["username"] == "admin")
        refused = await client.delete(f"/api/users/{admin['id']}", headers=headers)
        assert refused.status_code == 400
        assert refused.json()["details"]["reason"] == "last_admin"


@pytest.mark.asyncio
async def test_role_permissions_are_validated(app: Any) -> None:
    """门槛 ⑤：角色权限可改；未知权限码 ⇒ `STRUCTAI-1000`。"""
    async with _client(app) as client:
        headers = await _auth(client)
        roles = (await client.get("/api/roles", headers=headers)).json()
        assert len(roles["items"]) == 4
        engineer = next(item for item in roles["items"] if item["name"] == "engineer")

        ok = await client.put(
            f"/api/roles/{engineer['id']}",
            headers=headers,
            json={"permissions": ["MODEL_READ", "RESULT_READ"]},
        )
        assert ok.status_code == 200
        assert ok.json()["permissions"] == ["MODEL_READ", "RESULT_READ"]

        bad = await client.put(
            f"/api/roles/{engineer['id']}",
            headers=headers,
            json={"permissions": ["NOT_A_PERMISSION"]},
        )
        assert bad.status_code == 400
        assert bad.json()["details"]["reason"] == "unknown_permission"


# ===== 3. 模型 =====


@pytest.mark.asyncio
async def test_models_can_be_replaced_and_defaulted(app: Any) -> None:
    """门槛 ⑥：模型列表整体替换（列表语义），并保持「唯一默认」。"""
    async with _client(app) as client:
        headers = await _auth(client)
        initial = (await client.get("/api/models", headers=headers)).json()
        assert len(initial["items"]) == 6

        items = [
            {"id": "a", "name": "model-a", "provider": "X", "available": True, "is_default": False},
            {"id": "b", "name": "model-b", "provider": "Y", "available": True, "is_default": True},
        ]
        saved = await client.put(
            "/api/models", headers=headers, json={"items": items, "default": "b"}
        )
        assert saved.status_code == 200
        assert [item["id"] for item in saved.json()["items"]] == ["a", "b"]
        assert saved.json()["default"] == "b"

        tested = await client.post("/api/models/b/test", headers=headers)
        assert tested.status_code == 200
        assert tested.json()["reason"] == "api_key_not_configured"


# ===== 4. 数据管理 =====


@pytest.mark.asyncio
async def test_backup_uses_sqlite_api_and_is_listed(app: Any) -> None:
    """门槛 ⑦：立即备份 → 目录 + 清单 → 可列出 / 删除。"""
    async with _client(app) as client:
        headers = await _auth(client)
        created = await client.post("/api/data/backup", headers=headers)
        assert created.status_code == 200, created.text
        backup_id = created.json()["backup_id"]
        backup_dir = Path(created.json()["path"])
        assert await asyncio.to_thread(backup_dir.is_dir)

        listed = await client.get("/api/data/backups", headers=headers)
        assert listed.status_code == 200
        assert any(item["id"] == backup_id and item["complete"] for item in listed.json()["items"])

        stats = await client.get("/api/data/stats", headers=headers)
        assert stats.status_code == 200
        assert stats.json()["tables"]["users"] >= 1

        removed = await client.delete(f"/api/data/backups/{backup_id}", headers=headers)
        assert removed.status_code == 200
        assert not await asyncio.to_thread(backup_dir.exists)


@pytest.mark.asyncio
async def test_backup_id_path_traversal_is_rejected(app: Any) -> None:
    """门槛 ⑦：备份标识不能穿越目录。"""
    async with _client(app) as client:
        headers = await _auth(client)
        response = await client.delete("/api/data/backups/..%2F..%2Fetc", headers=headers)
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_cleanup_never_deletes_audit_records(app: Any) -> None:
    """门槛 ⑧：清理返回各类计数，审计固定为 0（`docs/02` §29 / §45）。"""
    async with _client(app) as client:
        headers = await _auth(client)
        response = await client.post(
            "/api/data/cleanup",
            headers=headers,
            json={"tasks": {"enabled": True, "days": 30}, "logs": {"enabled": True, "days": 1}},
        )
        assert response.status_code == 200
        removed = response.json()["removed"]
        assert removed["audit"] == 0
        assert "tasks" in removed and "sessions" in removed


@pytest.mark.asyncio
async def test_security_overview_reports_real_counts(app: Any) -> None:
    """安全设置页统计来自数据库（锁定账号 / 活跃会话 / 24h 审计）。"""
    async with _client(app) as client:
        headers = await _auth(client)
        response = await client.get("/api/security/overview", headers=headers)
        assert response.status_code == 200
        payload = response.json()
        for key in ("locked_accounts", "failed_login_total", "active_sessions", "audit_24h"):
            assert isinstance(payload[key], int), key
        assert payload["active_sessions"] >= 1  # 本次登录的会话
        assert isinstance(payload["events"], list)


# ===== 5. 设置文件独立于 Core 库 =====


@pytest.mark.asyncio
async def test_settings_file_is_independent_of_core_schema(app: Any, tmp_path: Path) -> None:
    """门槛 ③：设置落在独立文件；Core 的 24 张表**没有**新增。"""
    async with _client(app) as client:
        headers = await _auth(client)
        await client.put("/api/settings/notify", headers=headers, json={"email": "a@b.c"})
    settings_file = tmp_path / "management" / "settings.db"
    assert settings_file.is_file()
    assert "settings" not in Base.metadata.tables
    assert len(Base.metadata.tables) == 24
