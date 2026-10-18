"""Infrastructure · Management · 设置 / 用户 / 角色 / 模型（P183 / P185）。

`ManagementService` 的设置侧能力（mixin）：

- 设置分区读写（默认值 ⊕ 落库值；`system` 只读）；
- 用户 CRUD（口令只落 Argon2id 哈希；按「密码策略」校验 + 历史口令拒绝复用）；
- 角色 CRUD（权限码封闭集合；最后一个管理员 / 仍被引用的角色拒绝删除）；
- 模型列表（列表语义整体替换；API Key 只回显「是否已配置」）。

⚠️ 落点 = 独立运维库（`SettingsStore`），**不**新增 Core 表（`docs/07` §4.3）。
"""

from __future__ import annotations

import pathlib
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final

from sqlalchemy import delete, func, select

from app.domain.enums import PermissionCode
from app.domain.errors import NotFoundError, ProtocolError
from app.infrastructure.database.models.permission import PermissionORM
from app.infrastructure.database.models.role import RoleORM, RolePermissionORM
from app.infrastructure.database.models.session import SessionORM
from app.infrastructure.database.models.user import UserORM, UserRoleORM
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.infrastructure.management.common import backup_root, iso, runtime_facts, tenant_of


class SettingsManagementMixin:
    """`ManagementPort` 的设置 / 用户 / 角色 / 模型（由 `ManagementService` 混入）。"""

    # 由 `ManagementService` 提供
    _runtime: Any
    _version: str

    def _factory(self) -> Any:  # pragma: no cover - 类型声明
        raise NotImplementedError

    async def clients(self) -> Any:  # pragma: no cover - 由 ClientManagementMixin 提供
        raise NotImplementedError

    def _settings_store(self) -> Any:  # pragma: no cover - 类型声明
        raise NotImplementedError

    def _password_service(self) -> Any:  # pragma: no cover - 类型声明
        raise NotImplementedError

    async def _assign_roles(
        self, session: Any, tenant_id: str, user_id: str, roles: Any
    ) -> None:  # pragma: no cover - 类型声明
        raise NotImplementedError

    async def _replace_roles(
        self, session: Any, tenant_id: str, user_id: str, roles: Any
    ) -> None:  # pragma: no cover - 类型声明
        raise NotImplementedError

    async def _is_last_admin(
        self, session: Any, tenant_id: str, user_id: str
    ) -> bool:  # pragma: no cover - 类型声明
        raise NotImplementedError

    # ===== 系统设置（P183）=====

    async def settings(self) -> Mapping[str, Any]:
        """全部设置分区 ＋ 运行时只读信息（关于系统页）。"""
        store = self._settings_store()
        payload = store.read()
        facts = runtime_facts(self._runtime, self._version, store)
        payload["system"] = {**payload.get("system", {}), **facts}
        # 未显式配置的路径只补**可确证**的运行时目录；其余留空（不把占位值当真）。
        paths = payload.setdefault("paths", {})
        import tempfile

        # `project_dir` 只在数据库目录可解析时才补（否则留空，避免相对路径显示成 `data`）。
        database_dir = pathlib.Path(facts.get("database") or "").parent
        defaults = {
            "software_home": "",
            "temp_dir": tempfile.gettempdir(),
            "project_dir": str(database_dir) if facts.get("database") else "",
            "model_dir": "",
            "result_dir": facts.get("artifact_root", ""),
        }
        for key, value in defaults.items():
            if not paths.get(key):
                paths[key] = value
        backup = payload.setdefault("data", {}).setdefault("backup", {})
        if not backup.get("path"):
            backup["path"] = str(backup_root(self._runtime))
        behavior = payload.setdefault("behavior", {})
        if not behavior.get("default_software") or not behavior.get("default_version"):
            software = await self._default_software()
            behavior["default_software"] = behavior.get("default_software") or software[0]
            behavior["default_version"] = behavior.get("default_version") or software[1]
        return payload

    async def _default_software(self) -> tuple[str, str]:
        """已登记的第一个软件实例（`settings()` 的默认软件 / 版本）。"""
        try:
            clients = await self.clients()
        except Exception:  # noqa: BLE001 - 缺库时如实留空，不影响设置页
            return "", ""
        if not clients:
            return "", ""
        first = clients[0]
        return str(first.get("name") or ""), str(first.get("version") or "")

    async def update_settings(self, section: str, values: Mapping[str, Any]) -> Mapping[str, Any]:
        """深合并一个设置分区（`system` 只读；未知分区 → `STRUCTAI-1000`）。"""
        return {"section": section, "values": self._settings_store().update(section, values)}

    async def users(self, *, query: str = "") -> Mapping[str, Any]:
        """用户列表（Core `users` ⊕ 本机档案；**不含** `password_hash`）。"""
        needle = query.strip().lower()
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            tenant_id = await tenant_of(uow.session)
            rows = (
                (
                    await uow.session.execute(
                        select(UserORM)
                        .where(UserORM.tenant_id == tenant_id)
                        .order_by(UserORM.created_at.asc())
                    )
                )
                .scalars()
                .all()
            )
            role_rows = (
                await uow.session.execute(
                    select(UserORM.id, RoleORM.name)
                    .join(UserRoleORM, UserRoleORM.user_id == UserORM.id)
                    .join(RoleORM, RoleORM.id == UserRoleORM.role_id)
                    .where(UserORM.tenant_id == tenant_id)
                    .order_by(RoleORM.name)
                )
            ).all()
            session_rows = (
                await uow.session.execute(
                    select(SessionORM.user_id, SessionORM.last_seen_at).where(
                        SessionORM.tenant_id == tenant_id,
                        SessionORM.revoked.is_(False),
                    )
                )
            ).all()
        roles: dict[str, list[str]] = {}
        for user_id, role_name in role_rows:
            roles.setdefault(str(user_id), []).append(str(role_name))
        seen: dict[str, Any] = {}
        for user_id, last_seen in session_rows:
            if last_seen is not None:
                seen[str(user_id)] = last_seen
        profiles = self._settings_store().read_profiles()
        items = []
        for row in rows:
            profile = profiles.get(str(row.id), {})
            item = _user_row(row, roles.get(str(row.id), []), seen.get(str(row.id)), profile)
            if (
                needle
                and needle
                not in " ".join(
                    str(item.get(key) or "")
                    for key in ("username", "display_name", "email", "role_label")
                ).lower()
            ):
                continue
            items.append(item)
        return {"total": len(items), "items": items}

    async def verify_password_policy(self, password: str) -> Mapping[str, Any]:
        """按当前密码策略校验口令（**不**回显口令）。"""
        problems = self._password_problems(str(password))
        return {"valid": not problems, "problems": problems}

    def _password_problems(self, password: str) -> list[str]:
        """按 `security.password` 分区校验口令，返回未满足的规则（中文提示）。"""
        policy = self._settings_store().section("security").get("password", {})
        problems: list[str] = []
        minimum = _days(policy.get("min_length"), 8)
        if len(password) < minimum:
            problems.append(f"长度至少 {minimum} 位")
        if policy.get("require_upper", True) and not any(c.isupper() for c in password):
            problems.append("必须包含大写字母")
        if policy.get("require_lower", True) and not any(c.islower() for c in password):
            problems.append("必须包含小写字母")
        if policy.get("require_digit", True) and not any(c.isdigit() for c in password):
            problems.append("必须包含数字")
        if policy.get("require_special", True) and not any(not c.isalnum() for c in password):
            problems.append("必须包含特殊字符")
        return problems

    async def _check_password_history(self, user_id: str, password: str) -> None:
        """拒绝复用最近 N 个历史口令（只比对哈希，**不**存明文）。"""
        policy = self._settings_store().section("security").get("password", {})
        keep = _days(policy.get("history"), 5)
        if keep <= 1:
            return
        passwords = self._password_service()
        for previous in self._settings_store().read_password_history(user_id, limit=keep - 1):
            if passwords.verify(previous, password):
                raise ProtocolError(
                    "password was used recently",
                    details={"stage": "management", "reason": "password_reused"},
                )

    async def create_user(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """新建用户（口令只哈希落库；用户名全局唯一；按策略校验口令）。"""
        username = str(payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        if not username or not password:
            raise ProtocolError(
                "username and password are required",
                details={"stage": "management", "reason": "user_fields_missing"},
            )
        problems = self._password_problems(password)
        if problems:
            raise ProtocolError(
                "password does not satisfy the password policy",
                details={
                    "stage": "management",
                    "reason": "password_policy",
                    "problems": problems,
                },
            )
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            tenant_id = await tenant_of(uow.session)
            exists = (
                await uow.session.execute(select(UserORM.id).where(UserORM.username == username))
            ).scalar_one_or_none()
            if exists is not None:
                raise ProtocolError(
                    "username already exists",
                    details={"stage": "management", "reason": "username_taken"},
                )
            password_hash = self._password_service().hash(password)
            user = UserORM(
                tenant_id=tenant_id,
                username=username,
                password_hash=password_hash,
                is_active=bool(payload.get("is_active", True)),
            )
            uow.session.add(user)
            await uow.session.flush()
            await self._assign_roles(uow.session, tenant_id, str(user.id), payload.get("roles"))
            user_id = str(user.id)
            created = _user_row(user, _names(payload.get("roles")), None, {})
        self._settings_store().append_password_history(user_id, password_hash)
        self._settings_store().write_profile(
            user_id,
            {
                "display_name": str(payload.get("display_name") or ""),
                "email": str(payload.get("email") or ""),
                "phone": str(payload.get("phone") or ""),
                "note": str(payload.get("note") or ""),
            },
        )
        return created

    async def update_user(self, user_id: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """更新用户（档案 / 角色 / 启用 / 锁定 / 重置口令）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            tenant_id = await tenant_of(uow.session)
            user = (
                await uow.session.execute(
                    select(UserORM).where(UserORM.id == user_id, UserORM.tenant_id == tenant_id)
                )
            ).scalar_one_or_none()
            if user is None:
                raise NotFoundError(f"unknown user: {user_id}")
            if "is_active" in payload:
                user.is_active = bool(payload["is_active"])
            if "locked" in payload:
                user.locked = bool(payload["locked"])
                if not user.locked:
                    user.failed_login_count = 0
            password = str(payload.get("password") or "")
            password_hash = ""
            if password:
                problems = self._password_problems(password)
                if problems:
                    raise ProtocolError(
                        "password does not satisfy the password policy",
                        details={
                            "stage": "management",
                            "reason": "password_policy",
                            "problems": problems,
                        },
                    )
                await self._check_password_history(user_id, password)
                password_hash = self._password_service().hash(password)
                user.password_hash = password_hash
            await uow.session.flush()
            if "roles" in payload:
                await self._replace_roles(uow.session, tenant_id, user_id, payload.get("roles"))
            await uow.session.flush()
            roles = (
                (
                    await uow.session.execute(
                        select(RoleORM.name)
                        .join(UserRoleORM, UserRoleORM.role_id == RoleORM.id)
                        .where(UserRoleORM.user_id == user_id)
                        .order_by(RoleORM.name)
                    )
                )
                .scalars()
                .all()
            )
            updated = _user_row(user, [str(name) for name in roles], None, {})
        if password_hash:
            self._settings_store().append_password_history(user_id, password_hash)
        profile_keys = ("display_name", "email", "phone", "note")
        if any(key in payload for key in profile_keys):
            self._settings_store().write_profile(
                user_id,
                {key: str(payload.get(key) or "") for key in profile_keys if key in payload},
            )
        updated.update(self._settings_store().read_profiles().get(user_id, {}))
        return updated

    async def delete_user(self, user_id: str) -> Mapping[str, Any]:
        """删除用户（不允许删除**最后一个**启用中的系统管理员）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            tenant_id = await tenant_of(uow.session)
            user = (
                await uow.session.execute(
                    select(UserORM).where(UserORM.id == user_id, UserORM.tenant_id == tenant_id)
                )
            ).scalar_one_or_none()
            if user is None:
                raise NotFoundError(f"unknown user: {user_id}")
            if await self._is_last_admin(uow.session, tenant_id, user_id):
                raise ProtocolError(
                    "cannot delete the last administrator",
                    details={"stage": "management", "reason": "last_admin"},
                )
            await uow.session.execute(delete(UserRoleORM).where(UserRoleORM.user_id == user_id))
            await uow.session.execute(delete(SessionORM).where(SessionORM.user_id == user_id))
            await uow.session.delete(user)
            await uow.session.flush()
        self._settings_store().delete_profile(user_id)
        self._settings_store().clear_password_history(user_id)
        return {"deleted": user_id}

    async def roles(self) -> Mapping[str, Any]:
        """角色列表（名称 / 权限码 / 用户数）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            tenant_id = await tenant_of(uow.session)
            rows = (
                (
                    await uow.session.execute(
                        select(RoleORM).where(RoleORM.tenant_id == tenant_id).order_by(RoleORM.name)
                    )
                )
                .scalars()
                .all()
            )
            permissions = (
                await uow.session.execute(
                    select(RolePermissionORM.role_id, PermissionORM.code)
                    .join(PermissionORM, PermissionORM.id == RolePermissionORM.permission_id)
                    .join(RoleORM, RoleORM.id == RolePermissionORM.role_id)
                    .where(RoleORM.tenant_id == tenant_id)
                    .order_by(PermissionORM.code)
                )
            ).all()
            counts = (
                await uow.session.execute(
                    select(UserRoleORM.role_id, func.count())
                    .join(RoleORM, RoleORM.id == UserRoleORM.role_id)
                    .where(RoleORM.tenant_id == tenant_id)
                    .group_by(UserRoleORM.role_id)
                )
            ).all()
        by_role: dict[str, list[str]] = {}
        for role_id, code in permissions:
            by_role.setdefault(str(role_id), []).append(str(code))
        user_counts = {str(role_id): int(count) for role_id, count in counts}
        return {
            "items": [
                {
                    "id": str(row.id),
                    "name": row.name,
                    "label": _ROLE_LABELS.get(str(row.name), str(row.name)),
                    "permissions": by_role.get(str(row.id), []),
                    "users": user_counts.get(str(row.id), 0),
                }
                for row in rows
            ],
            "permissions": sorted(code.value for code in PermissionCode),
        }

    async def update_role(self, role_id: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """更新角色（权限码 / 显示名；权限码必须是已登记的 12 码之一）。"""
        wanted = [str(code) for code in (payload.get("permissions") or [])]
        unknown = sorted(set(wanted) - {code.value for code in PermissionCode})
        if unknown:
            raise ProtocolError(
                "unknown permission code",
                details={"stage": "management", "reason": "unknown_permission"},
            )
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            tenant_id = await tenant_of(uow.session)
            role = (
                await uow.session.execute(
                    select(RoleORM).where(RoleORM.id == role_id, RoleORM.tenant_id == tenant_id)
                )
            ).scalar_one_or_none()
            if role is None:
                raise NotFoundError(f"unknown role: {role_id}")
            permission_ids = {
                str(row[0]): str(row[1])
                for row in (
                    await uow.session.execute(select(PermissionORM.id, PermissionORM.code))
                ).all()
            }
            await uow.session.execute(
                delete(RolePermissionORM).where(RolePermissionORM.role_id == role_id)
            )
            for code in wanted:
                permission_id = next(
                    (pid for pid, value in permission_ids.items() if value == code), None
                )
                if permission_id is not None:
                    uow.session.add(RolePermissionORM(role_id=role_id, permission_id=permission_id))
            await uow.session.flush()
            return {"id": role_id, "name": role.name, "permissions": sorted(set(wanted))}

    async def create_role(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """新建角色（角色名租户内唯一；权限码必须是已登记的 12 码）。"""
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ProtocolError(
                "role name is required",
                details={"stage": "management", "reason": "role_name_missing"},
            )
        wanted = [str(code) for code in (payload.get("permissions") or [])]
        unknown = sorted(set(wanted) - {code.value for code in PermissionCode})
        if unknown:
            raise ProtocolError(
                "unknown permission code",
                details={"stage": "management", "reason": "unknown_permission"},
            )
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            tenant_id = await tenant_of(uow.session)
            exists = (
                await uow.session.execute(
                    select(RoleORM.id).where(RoleORM.tenant_id == tenant_id, RoleORM.name == name)
                )
            ).scalar_one_or_none()
            if exists is not None:
                raise ProtocolError(
                    "role already exists",
                    details={"stage": "management", "reason": "role_taken"},
                )
            role = RoleORM(tenant_id=tenant_id, name=name)
            uow.session.add(role)
            await uow.session.flush()
            permission_ids = {
                str(row[1]): str(row[0])
                for row in (
                    await uow.session.execute(select(PermissionORM.id, PermissionORM.code))
                ).all()
            }
            for code in sorted(set(wanted)):
                permission_id = permission_ids.get(code)
                if permission_id is not None:
                    uow.session.add(
                        RolePermissionORM(role_id=str(role.id), permission_id=permission_id)
                    )
            await uow.session.flush()
            return {
                "id": str(role.id),
                "name": role.name,
                "label": _ROLE_LABELS.get(role.name, role.name),
                "permissions": sorted(set(wanted)),
                "users": 0,
            }

    async def delete_role(self, role_id: str) -> Mapping[str, Any]:
        """删除角色（仍有用户关联 / 系统管理员角色时拒绝）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            tenant_id = await tenant_of(uow.session)
            role = (
                await uow.session.execute(
                    select(RoleORM).where(RoleORM.id == role_id, RoleORM.tenant_id == tenant_id)
                )
            ).scalar_one_or_none()
            if role is None:
                raise NotFoundError(f"unknown role: {role_id}")
            if role.name == "system_admin":
                raise ProtocolError(
                    "the system administrator role cannot be deleted",
                    details={"stage": "management", "reason": "system_role"},
                )
            users = int(
                (
                    await uow.session.execute(
                        select(func.count())
                        .select_from(UserRoleORM)
                        .where(UserRoleORM.role_id == role_id)
                    )
                ).scalar_one()
            )
            if users:
                raise ProtocolError(
                    "role is still assigned to users",
                    details={"stage": "management", "reason": "role_in_use", "users": users},
                )
            await uow.session.execute(
                delete(RolePermissionORM).where(RolePermissionORM.role_id == role_id)
            )
            await uow.session.delete(role)
            await uow.session.flush()
        return {"deleted": role_id}

    async def models(self) -> Mapping[str, Any]:
        """模型列表 ＋ 默认模型 ＋ 参数 / 连接配置（**不含**明文 API Key）。"""
        section = self._settings_store().section("models")
        return section

    async def update_models(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """整体替换模型列表 / 默认模型 / 参数（列表语义）。"""
        store = self._settings_store()
        if "items" in payload:
            items = payload.get("items")
            if not isinstance(items, list):
                raise ProtocolError(
                    "models.items must be a list",
                    details={"stage": "management", "reason": "models_type_mismatch"},
                )
            store.replace_items("models", "items", [_model_row(item) for item in items])
        rest = {
            key: value
            for key, value in payload.items()
            if key in {"default", "parameters", "connection"}
        }
        if rest:
            store.update("models", rest)
        return store.section("models")

    async def test_model(self, model_id: str) -> Mapping[str, Any]:
        """测试模型（**不**发起外部网络请求：只核对配置完整性，如实报告）。"""
        section = self._settings_store().section("models")
        item = next(
            (row for row in section.get("items", []) if str(row.get("id")) == str(model_id)), None
        )
        if item is None:
            raise NotFoundError(f"unknown model: {model_id}")
        connection = section.get("connection", {})
        configured = bool(connection.get("api_key_configured")) and bool(connection.get("base_url"))
        return {
            "id": model_id,
            "name": item.get("name"),
            "reachable": configured and bool(item.get("available", True)),
            "reason": None if configured else "api_key_not_configured",
            "checked_at": iso(datetime.now(UTC)),
        }


_ROLE_LABELS: Final[dict[str, str]] = {
    "system_admin": "超级管理员",
    "engineer": "工程师",
    "viewer": "访客",
    "ai_agent": "AI Agent",
}
"""角色显示名（Core 角色名是稳定标识，界面用中文标签）。"""


def _days(value: Any, default: int) -> int:
    """天数参数（非正数 / 非数字 ⇒ 默认值）。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _names(roles: Any) -> list[str]:
    """角色入参归一（字符串或字符串列表）。"""
    if isinstance(roles, str):
        return [roles] if roles else []
    if isinstance(roles, Sequence):
        return [str(item) for item in roles if str(item)]
    return []


def _user_row(
    row: Any,
    roles: list[str],
    last_seen: Any,
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    """`users` 行 → 前端行（**不含** `password_hash`）。"""
    primary = roles[0] if roles else ""
    return {
        "id": str(row.id),
        "username": row.username,
        "display_name": str(profile.get("display_name") or ""),
        "email": str(profile.get("email") or ""),
        "phone": str(profile.get("phone") or ""),
        "note": str(profile.get("note") or ""),
        "roles": list(roles),
        "role_label": _ROLE_LABELS.get(primary, primary),
        "is_active": bool(row.is_active),
        "locked": bool(row.locked),
        "failed_login_count": int(row.failed_login_count),
        "last_seen_at": iso(last_seen),
        "created_at": iso(row.created_at),
    }


def _model_row(item: Any) -> dict[str, Any]:
    """模型行归一（**丢弃**任何明文密钥字段）。"""
    import uuid

    if not isinstance(item, Mapping):
        return {}
    return {
        "id": str(item.get("id") or uuid.uuid4().hex[:12]),
        "name": str(item.get("name") or ""),
        "provider": str(item.get("provider") or ""),
        "kind": str(item.get("kind") or "对话模型"),
        "context": str(item.get("context") or ""),
        "available": bool(item.get("available", True)),
        "is_default": bool(item.get("is_default", False)),
        "description": str(item.get("description") or ""),
    }
