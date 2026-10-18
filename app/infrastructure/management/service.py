"""Infrastructure · Management —— `ManagementPort` 的装配实现（P181）。

职责
----
把 Web UI 需要的普通 REST 数据，映射到**既有** Application / Core 能力：

| 端口方法 | 复用 |
| --- | --- |
| `login` / `logout` / `identity` | `SecurityServices.guard` / `sessions`（P10–P13） |
| `overview` | 端点目录 + 模板库 + 任务/实例计数 |
| `clients` | `software` / `software_products` / `software_versions` / `software_instances` |
| `tasks` / `task` / `cancel` | `TaskRepository` / `TaskEngine`（P22–P28） |
| `events` | `AuditStore.chain`（P32，append-only） |
| `call` | `MCPServer.handle`（**同一** 9 Tool 契约，`docs/02` §124） |
| `import_template` | `materialize` → 服务器侧 JSON → `MODEL.IMPORT`（经 MCP） |

⚠️ 本模块是 **Infrastructure**：允许 SQLAlchemy，但**不**写业务判定 ——
权限 / 租户 / 任务状态一律交给既有服务；本层只做查询与转发。
⚠️ 不出现任何厂商名（`docs/07` §14.2）：厂商知识只在 `registry/` 与 Adapter 子包。
"""

from __future__ import annotations

import json
import os
import pathlib
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sqlalchemy import delete, func, select

from app.application.management import ManagementPort
from app.application.registry_catalog import EndpointCatalog
from app.application.security import build_security_services
from app.application.templates.library import MaterializeError, TemplateLibrary
from app.domain.errors import (
    EngineeringValidationError,
    InternalError,
    NotFoundError,
    PermissionDeniedError,
    ProtocolError,
    StructAIError,
)
from app.infrastructure.database.models.audit import AuditRecordORM
from app.infrastructure.database.models.role import RoleORM
from app.infrastructure.database.models.task import TaskORM
from app.infrastructure.database.models.user import UserORM, UserRoleORM
from app.infrastructure.database.repositories import build_audit_store, build_security_stores
from app.infrastructure.database.repositories.task import TaskRepository
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.infrastructure.management.clients import ClientManagementMixin
from app.infrastructure.management.common import (
    client_counts,
    days,
    iso,
    names_of,
    task_counts,
    tenant_of,
)
from app.infrastructure.management.data_admin import DataManagementMixin
from app.infrastructure.management.settings_admin import SettingsManagementMixin
from app.interfaces.mcp.server import build_mcp_server

__all__ = ["ManagementService", "build_management_service"]

_PROCESS_STARTED_AT: Final[datetime] = datetime.now(UTC)
"""进程启动时刻（服务状态卡展示运行时长；**不**是数据库里的值）。"""


class ManagementService(
    ClientManagementMixin, SettingsManagementMixin, DataManagementMixin, ManagementPort
):
    """`ManagementPort` 的实现（每个方法一个短会话）。"""

    def __init__(
        self,
        *,
        runtime: Any,
        catalog: EndpointCatalog,
        templates: TemplateLibrary,
        import_root: pathlib.Path,
        version: str,
        settings: Any = None,
    ) -> None:
        """绑定进程级运行时与只读数据源。

        Args:
            settings: `SettingsStore`（P183 的系统设置落点）；`None` 时按
                `runtime.settings` 的路径惰性装配 —— 便于既有测试不传该参数。
        """
        self._runtime = runtime
        self._catalog = catalog
        self._templates = templates
        self._import_root = import_root
        self._version = version
        self._settings = settings
        self._rate_window: dict[str, list[float]] = {}

    # ===== 会话 =====

    def _factory(self) -> Any:
        """进程级会话工厂（未配备 ⇒ 7000）。"""
        factory = self._runtime.session_factory
        if factory is None:
            raise InternalError(
                "database session factory is not bound",
                details={"stage": "management", "reason": "session_factory_not_bound"},
            )
        return factory

    def _security(self, session: Any) -> Any:
        """按会话装配安全服务（与传输层同一口径）。"""
        return build_security_services(
            build_security_stores(session),
            password_service=self._runtime.password_service,
            session_lifetime_seconds=self._runtime.settings.session_expire_seconds,
        )

    async def login(self, username: str, password: str) -> Mapping[str, Any]:
        """口令登录（失败形状与既有认证链一致，**不**泄露用户是否存在）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            security = self._security(uow.session)
            result = await security.guard.login(username, password)
            identity = result.identity
            return {
                "token": result.access_token,
                "user": str(identity.user_id),
                "tenant": str(identity.tenant_id),
                "roles": list(identity.roles),
                "authentication_method": identity.authentication_method,
            }

    async def logout(self, token: str) -> bool:
        """注销会话（未知 token ⇒ `False`）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            security = self._security(uow.session)
            try:
                identity = await security.sessions.validate_token(token)
            except StructAIError:
                return False
            return await security.sessions.revoke(str(identity.session_id or ""))

    async def change_password(self, token: str, current: str, new: str) -> Mapping[str, Any]:
        """当前登录用户修改自己的口令（旧口令 + 策略 + 历史校验）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            security = self._security(uow.session)
            context = await security.guard.build_context(token)
            user_id = str(context.identity.user_id)
            user = (
                await uow.session.execute(select(UserORM).where(UserORM.id == user_id))
            ).scalar_one_or_none()
            if user is None:
                raise NotFoundError("unknown user")
            if not self._password_service().verify(str(user.password_hash), str(current)):
                raise PermissionDeniedError(
                    "current password is incorrect",
                    details={"stage": "management", "reason": "invalid_credentials"},
                )
            problems = self._password_problems(str(new))
            if problems:
                raise ProtocolError(
                    "password does not satisfy the password policy",
                    details={
                        "stage": "management",
                        "reason": "password_policy",
                        "problems": problems,
                    },
                )
            await self._check_password_history(user_id, str(new))
            password_hash = self._password_service().hash(str(new))
            user.password_hash = password_hash
            await uow.session.flush()
        self._settings_store().append_password_history(user_id, password_hash)
        return {"changed": True}

    async def access_decision(self, ip: str) -> Mapping[str, Any]:
        """访问控制判定（白 / 黑名单 + 每分钟频率限制）。

        ⚠️ 这是**管理面**的准入判定：登录端点与写操作在路由层调用它；
        IP 规则来自 `security.access` 分区，计数在进程内滑动窗口。
        """
        import ipaddress
        import time

        access = self._settings_store().section("security").get("access", {})
        address = str(ip or "").strip()

        def _matches(entries: str) -> bool:
            for line in str(entries or "").splitlines():
                rule = line.strip()
                if not rule:
                    continue
                if rule == address:
                    return True
                try:
                    if ipaddress.ip_address(address) in ipaddress.ip_network(rule, strict=False):
                        return True
                except ValueError:
                    continue
            return False

        if access.get("blacklist_enabled") and _matches(access.get("blacklist", "")):
            return {"allowed": False, "reason": "blacklisted"}
        if access.get("whitelist_enabled") and not _matches(access.get("whitelist", "")):
            return {"allowed": False, "reason": "not_whitelisted"}
        if access.get("rate_limit_enabled"):
            limit = days(access.get("rate_per_minute"), 120)
            now = time.monotonic()
            window = self._rate_window.setdefault(address, [])
            while window and now - window[0] > 60.0:
                window.pop(0)
            if len(window) >= limit:
                return {"allowed": False, "reason": "rate_limited"}
            window.append(now)
        return {"allowed": True, "reason": None}

    async def identity(self, token: str) -> Mapping[str, Any]:
        """校验 token → 身份摘要。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            security = self._security(uow.session)
            context = await security.guard.build_context(token)
            return {
                "user": str(context.identity.user_id),
                "tenant": str(context.identity.tenant_id),
                "session": str(context.identity.session_id or ""),
                "roles": list(context.identity.roles),
                "permissions": sorted(context.permissions),
            }

    # ===== 总览 =====

    async def overview(self) -> Mapping[str, Any]:
        """首页 / 侧栏（计数来自数据库与只读目录）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            counts = await task_counts(uow.session)
            clients_total, clients_connected = await client_counts(uow.session)
        catalog = self._catalog.summary()
        templates = self._templates.summary()
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            usage = await _usage(uow.session)

        started = _PROCESS_STARTED_AT
        configured = self._settings_store().section("service")
        return {
            "service": {
                "running": True,
                "version": self._version,
                "registry_ready": bool(self._runtime.ready()),
                "pid": os.getpid(),
                "started_at": started.isoformat(),
                "uptime_seconds": int((datetime.now(UTC) - started).total_seconds()),
                # 运行期参数：已落库的值优先，缺省值来自实际运行环境。
                "host": configured.get("listen_host") or self._runtime.settings.host,
                "port": configured.get("port") or self._runtime.settings.port,
                "workers": configured.get("performance", {}).get("workers"),
            },
            "pid": os.getpid(),
            "started_at": started.isoformat(),
            "uptime_seconds": int((datetime.now(UTC) - started).total_seconds()),
            "tasks": counts,
            "clients": {"total": clients_total, "connected": clients_connected},
            "registry": {
                "available": catalog["available"],
                "endpoints": int((catalog.get("counts") or {}).get("keys") or 0),
                "schemas": int((catalog.get("counts") or {}).get("schemas") or 0),
                "namespaces": catalog.get("namespaces") or {},
            },
            "templates": {
                "available": templates["available"],
                "count": templates["count"],
                "families": len(templates["families"]),
            },
            "usage": usage,
        }

    # ===== 任务 =====

    async def tasks(self, *, limit: int, offset: int) -> Mapping[str, Any]:
        """任务列表（租户作用域）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            tenant_id = await tenant_of(uow.session)
            repository = TaskRepository(uow.session)
            rows = await repository.list_for_tenant(tenant_id, limit=limit, offset=offset)
            total = int(
                (
                    await uow.session.execute(
                        select(func.count())
                        .select_from(TaskORM)
                        .where(TaskORM.tenant_id == tenant_id)
                    )
                ).scalar_one()
            )
        return {"total": total, "items": [_task_row(row) for row in rows]}

    async def task(self, task_id: str) -> Mapping[str, Any]:
        """任务详情（含步骤）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            engine = self._engine(uow.session)
            tenant_id = await tenant_of(uow.session)
            try:
                view = await engine.get(task_id, tenant_id)
            except StructAIError as error:
                raise NotFoundError(str(error)) from error
            return {
                "task": _task_row(view.task),
                "steps": [
                    {
                        "name": step.name,
                        "status": step.status,
                        "started_at": iso(step.started_at),
                        "completed_at": iso(step.completed_at),
                    }
                    for step in view.steps
                ],
            }

    async def cancel(self, task_id: str) -> Mapping[str, Any]:
        """请求取消（返回真实结果，**不**伪造终态）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            engine = self._engine(uow.session)
            tenant_id = await tenant_of(uow.session)
            try:
                outcome = await engine.cancel(task_id, tenant_id)
            except StructAIError as error:
                raise NotFoundError(str(error)) from error
            return {
                "task_id": task_id,
                "cancelled": bool(getattr(outcome, "cancelled", False)),
                "reason": getattr(outcome, "reason", None),
                "status": getattr(outcome, "status", None),
            }

    # ===== 日志 =====

    async def events(self, *, limit: int) -> Sequence[Mapping[str, Any]]:
        """审计链最近 N 条（append-only；**不含** secret）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            tenant_id = await tenant_of(uow.session)
            entries = await build_audit_store(uow.session).chain(tenant_id=tenant_id, limit=limit)
        return [
            {
                "id": entry.id,
                "time": iso(entry.created_at),
                "action": entry.action,
                "resource": entry.resource,
                "result": entry.result,
                "user": entry.user_id,
            }
            for entry in entries
        ]

    # ===== 执行（与 MCP 同一条链）=====

    async def call(
        self,
        *,
        tool: str,
        operation: str,
        parameters: Mapping[str, Any],
        context: Mapping[str, Any],
        token: str,
    ) -> Mapping[str, Any]:
        """把一次 UI 请求转成 MCP Tool 调用（**不**复制业务逻辑）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            security = self._security(uow.session)
            security_context = await security.guard.build_context(token)
            service = self._runtime.execution.create_service(uow.session)
            server = build_mcp_server(service)
            response = await server.handle(
                tool,
                {
                    "operation": operation,
                    "parameters": dict(parameters),
                    "context": dict(context),
                },
                identity=security_context.identity,
                permissions=security_context.permissions,
            )
            return response.to_dict()

    # ===== 端点目录 =====

    async def registry(self) -> Mapping[str, Any]:
        """端点目录摘要（只读数据，**不**碰数据库）。"""
        return self._catalog.summary()

    async def endpoints(
        self, *, namespace: str = "", query: str = "", limit: int = 50, offset: int = 0
    ) -> Mapping[str, Any]:
        """端点列表（过滤 + 分页）。"""
        return self._catalog.list_endpoints(
            namespace=namespace, query=query, limit=limit, offset=offset
        )

    async def endpoint(self, key: str) -> Mapping[str, Any]:
        """端点详情（含请求 Schema 原文）。"""
        payload = self._catalog.endpoint(key)
        if payload is None:
            raise NotFoundError(f"unknown endpoint: {key}")
        return payload

    async def operations(self) -> Sequence[Mapping[str, Any]]:
        """运行时 Operation 清单（名字 + 归属 Tool；来自已装配的注册表）。"""
        registry = self._runtime.operation_registry
        if registry is None:
            return []
        return [
            {
                "name": definition.name,
                "tool": definition.tool,
                "risk_level": definition.risk_level,
                "execution_mode": definition.execution_mode,
            }
            for definition in (registry.require(name) for name in registry.names())
        ]

    # ===== 模板 =====

    async def templates(self) -> Mapping[str, Any]:
        """模板库摘要 + 模板列表（**不含**整份 model）。"""
        return {
            **self._templates.summary(),
            "items": [item.to_dict() for item in self._templates.templates],
        }

    async def template(self, name: str) -> Mapping[str, Any]:
        """单个模板的参数表。"""
        summary = self._templates.find(name)
        if summary is None:
            raise NotFoundError(f"unknown template: {name}")
        return {
            **summary.to_dict(),
            "parameters": self._templates.parameters(name),
        }

    # ===== 模板 =====

    async def import_template(
        self,
        *,
        name: str,
        overrides: Mapping[str, Any],
        project_path: str,
        token: str,
    ) -> Mapping[str, Any]:
        """模板 → 服务器侧 JSON → `MODEL.IMPORT`（经 MCP 契约）。

        `project_path` 是**当前打开的项目文件路径**（`DOC.IMPORT` 的路径守卫要求
        调用方显式给出，见 `adapter._doc_arguments`）；模板生成的 JSON 落在
        `management_import_root` 下，名字带随机后缀（不覆盖历史文件）。
        """
        try:
            payload = self._templates.render(name, overrides)
        except KeyError as error:
            raise NotFoundError(str(error)) from error
        except MaterializeError as error:
            raise EngineeringValidationError(
                str(error), details={"stage": "management", "reason": "template_invalid"}
            ) from error

        self._import_root.mkdir(parents=True, exist_ok=True)
        target = self._import_root / f"template-{uuid.uuid4().hex}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        # ⚠️ `MODEL.IMPORT` 的 `parameters.project_path` 是**要导入的 JSON 路径**；
        #    当前项目自身路径由 Adapter 自己记住（`DOC.OPEN` / `SAVE_AS` 之后）。
        #    ⇒ 这里传 target，不传调用方给的项目路径（那是**另一件事**）。
        envelope = await self.call(
            tool="engineering_doc",
            operation="MODEL.IMPORT",
            parameters={"project_path": str(target)},
            context={},
            token=token,
        )
        return {
            "template": name,
            "written": str(target),
            "overrides": dict(overrides),
            "project": project_path,
            "response": envelope,
        }

    # ===== 内部 =====

    def _settings_store(self) -> Any:
        """设置存储（未注入时按运行时配置惰性装配）。"""
        if self._settings is None:
            from app.infrastructure.management.settings import build_settings_store

            # 与模板导入同一目录（`MANAGEMENT_IMPORT_ROOT`），不新增 Settings 字段
            # （`docs/07` §16 R66：新增配置项必须走显式升级路径）。
            root = pathlib.Path(
                str(getattr(self._runtime.settings, "management_import_root", "./data/management"))
            )
            self._settings = build_settings_store(root / "settings.db")
        return self._settings

    def _password_service(self) -> Any:
        """口令服务（与认证链同一个实例；缺失时按默认参数装配）。"""
        service = getattr(self._runtime, "password_service", None)
        if service is None:
            from app.application.security import PasswordService

            service = PasswordService()
        return service

    async def _assign_roles(self, session: Any, tenant_id: str, user_id: str, roles: Any) -> None:
        """追加角色关联（未知角色名忽略，不静默提权）。"""
        for name in names_of(roles):
            role_id = (
                await session.execute(
                    select(RoleORM.id).where(RoleORM.tenant_id == tenant_id, RoleORM.name == name)
                )
            ).scalar_one_or_none()
            if role_id is not None:
                session.add(UserRoleORM(user_id=user_id, role_id=str(role_id)))

    async def _replace_roles(self, session: Any, tenant_id: str, user_id: str, roles: Any) -> None:
        """整体替换角色关联（空列表 = 收回全部角色）。"""
        await session.execute(delete(UserRoleORM).where(UserRoleORM.user_id == user_id))
        await self._assign_roles(session, tenant_id, user_id, roles)

    async def _is_last_admin(self, session: Any, tenant_id: str, user_id: str) -> bool:
        """该用户是否是**最后一个**启用中的 `system_admin`。"""
        admin_ids = set(
            (
                await session.execute(
                    select(UserRoleORM.user_id)
                    .join(RoleORM, RoleORM.id == UserRoleORM.role_id)
                    .where(RoleORM.tenant_id == tenant_id, RoleORM.name == "system_admin")
                )
            )
            .scalars()
            .all()
        )
        if str(user_id) not in admin_ids:
            return False
        active = (
            await session.execute(
                select(func.count())
                .select_from(UserORM)
                .where(
                    UserORM.tenant_id == tenant_id,
                    UserORM.id.in_(list(admin_ids)),
                    UserORM.is_active.is_(True),
                )
            )
        ).scalar_one()
        return int(active) <= 1

    def _engine(self, session: Any) -> Any:
        """会话级任务引擎（与 MCP 执行链同一装配）。"""
        return self._runtime.execution.create(session).engine


def build_management_service(
    runtime: Any,
    *,
    catalog: EndpointCatalog,
    templates: TemplateLibrary,
    import_root: str | pathlib.Path,
    version: str,
    settings: Any = None,
) -> ManagementService:
    """装配管理面服务（**不**做 I/O）。"""
    return ManagementService(
        runtime=runtime,
        catalog=catalog,
        templates=templates,
        import_root=pathlib.Path(import_root),
        version=version,
        settings=settings,
    )


# ===== 查询辅助（只读）=====


async def _usage(session: Any) -> dict[str, Any]:
    """今日 / 昨日请求数与平均响应时间（数据源 = 审计记录）。

    ⚠️ **口径**：`audit_records` 每次「已执行的调用」写一条（`docs/02` §8.3），
    因此「今日请求数」= 今日的审计条数。平均响应时间**不在**审计里（`audit_records`
    没有耗时列）⇒ 用同一时间窗内**已完成任务**的
    `completed_at - started_at` 均值；没有样本时返回 `None`（**不**编造 0）。
    """
    now = datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)

    async def count_between(start: datetime, end: datetime) -> int:
        return int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(AuditRecordORM)
                    .where(AuditRecordORM.created_at >= start, AuditRecordORM.created_at < end)
                )
            ).scalar_one()
        )

    async def latency_between(start: datetime, end: datetime) -> float | None:
        rows = (
            await session.execute(
                select(TaskORM.started_at, TaskORM.completed_at).where(
                    TaskORM.completed_at >= start,
                    TaskORM.completed_at < end,
                    TaskORM.started_at.is_not(None),
                )
            )
        ).all()
        values = [
            (completed - started).total_seconds()
            for started, completed in rows
            if started is not None and completed is not None
        ]
        if not values:
            return None
        return round(sum(values) / len(values) * 1000.0, 1)

    requests_today = await count_between(today, now)
    requests_yesterday = await count_between(yesterday, today)
    latency_today = await latency_between(today, now)
    latency_yesterday = await latency_between(yesterday, today)
    return {
        "requests": {
            "today": requests_today,
            "yesterday": requests_yesterday,
            "delta_percent": _delta_percent(requests_today, requests_yesterday),
        },
        "latency_ms": {
            "today": latency_today,
            "yesterday": latency_yesterday,
            "delta_percent": _delta_percent(latency_today, latency_yesterday, inverse=True),
        },
    }


def _delta_percent(today: Any, yesterday: Any, *, inverse: bool = False) -> float | None:
    """环比百分比（昨日为 0 / 缺失 ⇒ `None`，**不**编造）。

    `inverse=True` 用于响应时间：下降是好事，返回**负值**表示改善。
    """
    if today is None or yesterday is None or float(yesterday) == 0:
        return None
    change = (float(today) - float(yesterday)) / float(yesterday) * 100.0
    return round(-change if inverse else change, 1)


def _task_row(task: Any) -> dict[str, Any]:
    """`TaskRecord` → JSON 行（**不含** result / error 原文）。"""
    return {
        "id": task.id,
        "tool": task.tool,
        "operation": task.operation,
        "status": task.status,
        "progress": task.progress,
        "project_id": task.project_id,
        "created_at": iso(task.created_at),
        "started_at": iso(task.started_at),
        "completed_at": iso(task.completed_at),
        "retry_count": task.retry_count,
        "cancel_requested": task.cancel_requested,
    }


# ===== P183：系统设置辅助 =====
