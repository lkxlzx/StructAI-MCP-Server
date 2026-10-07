"""P42–P48 验收 · 第 4 类：**Security**（认证 / 授权 / 租户隔离 / 凭据 / 确认 / 敏感信息）。

门槛（`docs/08` §4 的本批提示词；`docs/07` §12 P42–P48 / §13.1 / §13.4 / §8.1；
`docs/02` §52 / §67）
------------------------------------------------------------------------------
① 认证链：`Authentication → Session → RBAC → Effective Permission` 四步全通，且认证 /
   授权路径**零写入**（SQL 级钩子），失败形状**不可区分**。
② 租户隔离与授权：跨租户一律 `STRUCTAI-4200`；缺权限 `STRUCTAI-4000`；
   AI Agent **不得提权**。
③ 凭据与确认：凭据**只**来自运行环境；confirmation token 一次性、绑定
   user + tenant + operation + resource，固定串一律拒绝。
④ 敏感信息：口令 / token / 确认令牌**绝不**落库、绝不进响应（全库文本列扫描）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

import p42_p48_support as support
from app.application.execution.pipeline import PipelineRequest
from app.application.security import (
    MAX_FAILED_LOGIN_ATTEMPTS,
    AuthenticationResult,
    IdentityContext,
    build_security_services,
)
from app.application.security.context import AUTHENTICATION_METHOD_TOKEN
from app.application.security.password import PasswordService
from app.application.security.session import (
    INVALID_SESSION_MESSAGE,
    SESSION_FAILURE_REASONS,
)
from app.infrastructure.database.repositories import build_security_stores
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.interfaces.mcp import build_mcp_server

# ===== ① 认证链与失败形状（`docs/02` §16–§21 / §41；`docs/07` §8.1）=====


async def test_login_chain_issues_a_token_and_rebuilds_the_identity(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/02` §41）：四步链全通；Token 可还原身份与权限。"""
    from app.domain.errors import PermissionDeniedError

    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_security_login.db"
    )
    async with UnitOfWork.from_session_factory(factory) as uow:
        security = runtime.execution.security_for(uow.session)
        assert security.guard.chain_order == support.SECURITY_CHAIN_SPEC
        assert security.authentication.max_failed_attempts == MAX_FAILED_LOGIN_ATTEMPTS
        result = await security.guard.login(support.ADMIN_USERNAME, support.TEST_PASSWORD)
        assert isinstance(result, AuthenticationResult)
        assert result.access_token
        assert result.session_id
        assert result.identity.tenant_id == UUID(ids["tenant_id"])
        assert result.identity.authentication_method == "PASSWORD"

        identity = await security.guard.authenticate(result.access_token)
        assert identity.user_id == result.identity.user_id
        assert identity.authentication_method == AUTHENTICATION_METHOD_TOKEN
        context = await security.guard.build_context(result.access_token)
        assert context.authenticated is True
        assert context.permissions
        assert "MODEL_READ" in context.permissions
        assert await security.guard.logout(result.session_id) is True
        with pytest.raises(PermissionDeniedError):
            await security.guard.authenticate(result.access_token)


async def test_login_failure_shape_is_identical_and_hides_existence(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/02` §17 / §48）：未知用户与口令错误**同一形状**（不泄露存在性）。"""
    from app.domain.errors import PermissionDeniedError

    runtime, factory, _ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_security_failure.db"
    )
    async with UnitOfWork.from_session_factory(factory) as uow:
        security = runtime.execution.security_for(uow.session)
        with pytest.raises(PermissionDeniedError) as unknown:
            await security.guard.login("no-such-user", "whatever")
        with pytest.raises(PermissionDeniedError) as wrong:
            await security.guard.login(support.ADMIN_USERNAME, "wrong-password")
    assert unknown.value.code == "STRUCTAI-4000"
    assert wrong.value.code == "STRUCTAI-4000"
    assert unknown.value.message == wrong.value.message
    assert unknown.value.details == wrong.value.details
    assert unknown.value.details == {
        "stage": "authentication",
        "reason": support.INVALID_CREDENTIALS_REASON,
    }


async def test_repeated_failures_lock_the_account(tmp_path: Path, monkeypatch: Any) -> None:
    """门槛 ①（`docs/02` §18）：连续失败达到阈值后锁定，正确口令同样被拒（同形状）。"""
    from app.domain.errors import PermissionDeniedError

    runtime, factory, _ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_security_lock.db"
    )
    async with UnitOfWork.from_session_factory(factory) as uow:
        security = runtime.execution.security_for(uow.session)
        for _ in range(MAX_FAILED_LOGIN_ATTEMPTS):
            with pytest.raises(PermissionDeniedError):
                await security.guard.login(support.ADMIN_USERNAME, "wrong-password")
        with pytest.raises(PermissionDeniedError) as locked:
            await security.guard.login(support.ADMIN_USERNAME, support.TEST_PASSWORD)
    assert locked.value.code == "STRUCTAI-4000"
    assert locked.value.details == {
        "stage": "authentication",
        "reason": support.INVALID_CREDENTIALS_REASON,
    }


async def test_authorization_path_performs_no_writes(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/07` §9 第 2–4 / 11 步）：会话校验 + RBAC + 有效权限**零写入**。"""
    runtime, factory, _ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_security_nowrite.db"
    )
    settings = support.seeded_settings(tmp_path, name="p42_security_nowrite.db")
    async with UnitOfWork.from_session_factory(factory) as uow:
        security = runtime.execution.security_for(uow.session)
        result = await security.guard.login(support.ADMIN_USERNAME, support.TEST_PASSWORD)
    engine = support.engine_for(settings)
    try:
        statements = support.record_statements(engine)
        async with UnitOfWork.from_session_factory(factory) as uow:
            security = runtime.execution.security_for(uow.session)
            identity = await security.guard.authenticate(result.access_token)
            await security.guard.authorize(identity, "MODEL_READ")
            granted = await security.permissions.get_permissions(identity)
            assert "MODEL_READ" in granted
        writes = [
            statement
            for statement in statements
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        ]
        assert writes == [], writes
    finally:
        await engine.dispose()


async def test_only_the_token_hash_is_stored(tmp_path: Path, monkeypatch: Any) -> None:
    """门槛 ①（`docs/02` §13 / §54）：库里只有 `token_hash`，明文 token 与口令零命中。"""
    import hashlib

    runtime, factory, _ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_security_token_storage.db"
    )
    settings = support.seeded_settings(tmp_path, name="p42_security_token_storage.db")
    async with UnitOfWork.from_session_factory(factory) as uow:
        security = runtime.execution.security_for(uow.session)
        result = await security.guard.login(support.ADMIN_USERNAME, support.TEST_PASSWORD)
    engine = support.engine_for(settings)
    try:
        values = await support.all_text_values(engine)
        assert await support.row_count(engine, "sessions") >= 1
        assert result.access_token not in values, "明文 token 绝不落库"
        assert support.TEST_PASSWORD not in values, "明文口令绝不落库"
        digest = hashlib.sha256(result.access_token.encode("utf-8")).hexdigest()
        assert digest in values, "只存 token_hash（sha256）"
    finally:
        await engine.dispose()


async def test_expired_and_revoked_sessions_are_rejected(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/02` §20 / §21 / §53）：过期与注销立即失效，原因取自冻结词表。"""
    from app.domain.errors import PermissionDeniedError

    runtime, factory, _ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_security_session.db"
    )
    assert set(SESSION_FAILURE_REASONS) == {
        "unknown_session",
        "session_revoked",
        "session_expired",
        "user_inactive",
    }
    async with UnitOfWork.from_session_factory(factory) as uow:
        expiring = build_security_services(
            build_security_stores(uow.session),
            password_service=PasswordService(),
            session_lifetime_seconds=0,
        )
        issued = await expiring.guard.login(support.ADMIN_USERNAME, support.TEST_PASSWORD)
        with pytest.raises(PermissionDeniedError) as expired:
            await expiring.guard.authenticate(issued.access_token)
    assert expired.value.code == "STRUCTAI-4000"
    assert expired.value.message == INVALID_SESSION_MESSAGE
    assert expired.value.details == {"stage": "session", "reason": "session_expired"}

    async with UnitOfWork.from_session_factory(factory) as uow:
        security = build_security_services(
            build_security_stores(uow.session),
            password_service=PasswordService(),
        )
        issued = await security.guard.login(support.ADMIN_USERNAME, support.TEST_PASSWORD)
        assert await security.guard.logout(issued.session_id) is True
        with pytest.raises(PermissionDeniedError) as revoked:
            await security.guard.authenticate(issued.access_token)
    assert revoked.value.details == {"stage": "session", "reason": "session_revoked"}


# ===== ② 授权 / 租户隔离 / AI Agent（`docs/02` §22 / §29–§32；`docs/07` §8.2）=====


async def test_missing_permission_is_denied_and_agents_cannot_escalate(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ②（`docs/07` §13.4）：缺权限 → `STRUCTAI-4000`；Agent 权限只减不增。"""
    from app.domain.errors import PermissionDeniedError

    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_security_authorization.db"
    )
    async with UnitOfWork.from_session_factory(factory) as uow:
        security = runtime.execution.security_for(uow.session)
        admin = IdentityContext(
            user_id=UUID(ids["user_id"]),
            tenant_id=UUID(ids["tenant_id"]),
            roles=("system_admin",),
        )
        granted = await security.permissions.get_permissions(admin)
        assert "MODEL_WRITE" in granted
        assert "NOPE_PERMISSION" not in granted
        await security.guard.authorize(admin, "MODEL_WRITE")
        with pytest.raises(PermissionDeniedError) as denied:
            await security.guard.authorize(admin, "NOPE_PERMISSION")
        assert denied.value.code == "STRUCTAI-4000"
        assert denied.value.details == {
            "permission": "NOPE_PERMISSION",
            "stage": "authorization",
        }

        scoped = await security.permissions.get_permissions(admin, agent_permissions={"MODEL_READ"})
        assert scoped == {"MODEL_READ"}, scoped
        narrowed = await security.agents.intersect({"MODEL_READ", "MODEL_WRITE"}, {"MODEL_READ"})
        assert narrowed == {"MODEL_READ"}, narrowed
        assert await security.agents.intersect({"MODEL_READ", "MODEL_WRITE"}, set()) == set()


async def test_cross_tenant_access_is_denied_with_structai_4200(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ②（`docs/02` §22 / §48）：跨租户 / 跨项目一律 `STRUCTAI-4200`。"""
    from app.domain.errors import TenantAccessDeniedError

    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_security_tenant.db"
    )
    foreign_tenant = str(UUID(int=9999))
    async with UnitOfWork.from_session_factory(factory) as uow:
        security = runtime.execution.security_for(uow.session)
        identity = support.identity_context(ids)
        with pytest.raises(TenantAccessDeniedError) as foreign:
            security.tenant_access.ensure_access(identity, foreign_tenant)
        assert foreign.value.code == support.TENANT_DENIED_CODE
        with pytest.raises(TenantAccessDeniedError):
            security.tenant_access.ensure_resource_access(identity, None)
        security.tenant_access.ensure_access(identity, ids["tenant_id"])
        with pytest.raises(TenantAccessDeniedError):
            await security.project_access.ensure_access(identity, foreign_tenant)
        await security.project_access.ensure_access(identity, ids["project_id"])


async def test_explicit_deny_beats_role_grants(tmp_path: Path, monkeypatch: Any) -> None:
    """门槛 ②（`docs/02` §28 / §30）：显式 `DENY` 压过角色授予（Deny wins）。"""
    from app.application.security.permission import InMemoryResourceACLLookup
    from app.domain.enums import ACLPrincipalType, PermissionEffect
    from app.domain.protocols import ResourceACLEntry

    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_security_acl.db"
    )
    identity = support.identity_context(ids)
    entry = ResourceACLEntry(
        principal_type=ACLPrincipalType.USER,
        principal_id=str(identity.user_id),
        permission="MODEL_WRITE",
        effect=PermissionEffect.DENY,
    )
    async with UnitOfWork.from_session_factory(factory) as uow:
        stores = build_security_stores(uow.session)
        baseline = build_security_services(stores, password_service=PasswordService())
        assert "MODEL_WRITE" in await baseline.permissions.get_permissions(identity)
        denied = build_security_services(
            stores,
            password_service=PasswordService(),
            resource_acl=InMemoryResourceACLLookup(str(identity.tenant_id), [entry]),
        )
        granted = await denied.permissions.get_permissions(identity)
        assert "MODEL_WRITE" not in granted, "显式 DENY 必须生效（docs/02 §28）"
        assert "MODEL_READ" in granted


# ===== ③ 确认令牌（`docs/07` §8.4；`docs/02` §34–§39）=====


async def test_confirmation_is_required_consumed_once_and_bound(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ③（`docs/07` §8.4）：缺 / 假 token → `STRUCTAI-4100`；有效 token 一次性且绑定。"""
    from app.application.execution.confirmation import ConfirmationService
    from app.domain.errors import ConfirmationRequiredError

    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_security_confirmation.db"
    )
    with pytest.raises(RuntimeError):
        ConfirmationService(token_factory=lambda: "CONFIRM").issue(
            user_id="u", tenant_id="t", operation="BUILD.COLUMN"
        )
    identity = support.identity_context(ids)
    context = support.client_context(ids)
    async with UnitOfWork.from_session_factory(factory) as uow:
        bundle = runtime.execution.create(uow.session)
        server = build_mcp_server(bundle.service)
        resolved = await bundle.resolver.resolve(
            server.contexts.create(identity, client_context=context).execution
        )
        assert resolved is not None
        resource_id = resolved.resource_id

        missing = await server.handle(
            "engineering_model_build",
            support.arguments(
                "BUILD.COLUMN", parameters=support.BUILD_COLUMN_PARAMETERS, context=context
            ),
            identity=identity,
        )
        assert missing.success is False
        assert missing.errors[0]["code"] == support.CONFIRMATION_REQUIRED_CODE
        assert missing.errors[0]["details"]["reason"] == support.MISSING_TOKEN_REASON

        for forged in support.FORBIDDEN_CONFIRMATION_TOKENS:
            refused = await server.handle(
                "engineering_model_build",
                support.arguments(
                    "BUILD.COLUMN",
                    parameters=support.BUILD_COLUMN_PARAMETERS,
                    context=context,
                    confirmation_token=forged,
                ),
                identity=identity,
            )
            assert refused.success is False, forged
            assert refused.errors[0]["code"] == support.CONFIRMATION_REQUIRED_CODE, forged

        token = runtime.confirmation.issue(
            user_id=ids["user_id"],
            tenant_id=ids["tenant_id"],
            operation="BUILD.COLUMN",
            resource_id=resource_id,
        ).token
        for arguments in (
            (ids["user_id"], ids["tenant_id"], "DESIGN.STEEL", resource_id),
            ("other-user", ids["tenant_id"], "BUILD.COLUMN", resource_id),
            (ids["user_id"], "other-tenant", "BUILD.COLUMN", resource_id),
            (ids["user_id"], ids["tenant_id"], "BUILD.COLUMN", "other-resource"),
        ):
            with pytest.raises(ConfirmationRequiredError) as mismatch:
                runtime.confirmation.verify(token, *arguments)
            assert mismatch.value.code == support.CONFIRMATION_REQUIRED_CODE
            assert mismatch.value.details["stage"] == "confirmation"
        consumed = runtime.confirmation.verify(
            token, ids["user_id"], ids["tenant_id"], "BUILD.COLUMN", resource_id
        )
        assert consumed.token == token
        with pytest.raises(ConfirmationRequiredError):
            runtime.confirmation.verify(
                token, ids["user_id"], ids["tenant_id"], "BUILD.COLUMN", resource_id
            )
        assert runtime.confirmation.pending() == 0


async def test_confirmation_token_never_reaches_the_database_or_the_response(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ③④（`docs/07` §14.3）：确认令牌**绝不**落库、绝不进响应 / `repr`。"""
    name = "p42_security_token_leak.db"
    settings = support.seeded_settings(tmp_path, name=name)
    runtime, factory, ids = await support.seeded_runtime(tmp_path, monkeypatch, name=name)
    identity = support.identity_context(ids)
    context = support.client_context(ids)
    async with UnitOfWork.from_session_factory(factory) as uow:
        bundle = runtime.execution.create(uow.session)
        server = build_mcp_server(bundle.service)
        resolved = await bundle.resolver.resolve(
            server.contexts.create(identity, client_context=context).execution
        )
        assert resolved is not None
        request = PipelineRequest(
            tool="engineering_model_build",
            operation="BUILD.COLUMN",
            parameters=dict(support.BUILD_COLUMN_PARAMETERS),
            context=server.contexts.create(identity, client_context=context).execution,
            confirmation_token="secret-confirmation-token",
        )
        assert "secret-confirmation-token" not in repr(request)
        token = runtime.confirmation.issue(
            user_id=ids["user_id"],
            tenant_id=ids["tenant_id"],
            operation="BUILD.COLUMN",
            resource_id=resolved.resource_id,
        ).token
        built = await server.handle(
            "engineering_model_build",
            support.arguments(
                "BUILD.COLUMN",
                parameters=support.BUILD_COLUMN_PARAMETERS,
                context=context,
                confirmation_token=token,
            ),
            identity=identity,
        )
        assert built.success is True, built.errors
        payload = json.dumps(built.to_dict(), ensure_ascii=False)
        assert token not in payload
    engine = support.engine_for(settings)
    try:
        values = await support.all_text_values(engine)
        assert token not in values, "确认令牌绝不落库"
        assert support.TEST_PASSWORD not in values
    finally:
        await engine.dispose()


# ===== ④ 凭据（`docs/07` §8.5；`docs/02` §21 / §26 / §35）=====


async def test_credentials_come_only_from_the_environment(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ④（`docs/07` §8.5）：凭据只读运行环境；缺失 → `STRUCTAI-7000`；**没有**写回路径。"""
    from app.domain.errors import InternalError

    runtime, _factory, _ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_security_credentials.db"
    )
    provider = runtime.credentials
    monkeypatch.delenv("STRUCTAI_SECRET_PROVIDER_API_KEY", raising=False)
    with pytest.raises(InternalError) as missing:
        await provider.get_secret("provider-api-key")
    assert missing.value.code == "STRUCTAI-7000"
    assert "provider-api-key" not in json.dumps(missing.value.details, ensure_ascii=False)
    assert "provider-api-key" not in repr(provider)
    with pytest.raises(RuntimeError):
        await provider.set_secret("provider-api-key", "value")
    with pytest.raises(RuntimeError):
        await provider.delete_secret("provider-api-key")
