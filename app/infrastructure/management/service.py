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
import pathlib
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sqlalchemy import func, select

from app.application.management import ManagementPort
from app.application.registry_catalog import EndpointCatalog
from app.application.security import build_security_services
from app.application.templates.library import MaterializeError, TemplateLibrary
from app.domain.errors import (
    EngineeringValidationError,
    InternalError,
    NotFoundError,
    StructAIError,
)
from app.infrastructure.database.models.audit import AuditRecordORM
from app.infrastructure.database.models.software import (
    SoftwareInstanceORM,
    SoftwareORM,
    SoftwareProductORM,
    SoftwareVersionORM,
)
from app.infrastructure.database.models.task import TaskORM
from app.infrastructure.database.repositories import build_audit_store, build_security_stores
from app.infrastructure.database.repositories.task import TaskRepository
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.interfaces.mcp.server import build_mcp_server

__all__ = ["ManagementService", "build_management_service"]

TASK_ACTIVE_STATUSES: Final[tuple[str, ...]] = (
    "CREATED",
    "VALIDATING",
    "QUEUED",
    "RUNNING",
    "PROCESSING",
    "RETRYING",
    "RECOVERING",
    "CANCEL_REQUESTED",
)
"""「活跃」任务的状态集合（与 `TaskStatus` 的终态互补；本层只做计数）。"""


class ManagementService(ManagementPort):
    """`ManagementPort` 的实现（每个方法一个短会话）。"""

    def __init__(
        self,
        *,
        runtime: Any,
        catalog: EndpointCatalog,
        templates: TemplateLibrary,
        import_root: pathlib.Path,
        version: str,
    ) -> None:
        """绑定进程级运行时与只读数据源。"""
        self._runtime = runtime
        self._catalog = catalog
        self._templates = templates
        self._import_root = import_root
        self._version = version

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
            counts = await _task_counts(uow.session)
            clients_total, clients_connected = await _client_counts(uow.session)
        catalog = self._catalog.summary()
        templates = self._templates.summary()
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            usage = await _usage(uow.session)
        return {
            "service": {
                "running": True,
                "version": self._version,
                "registry_ready": bool(self._runtime.ready()),
            },
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

    # ===== 客户端 =====

    async def clients(self) -> Sequence[Mapping[str, Any]]:
        """软件实例列表（**不含**凭据；`credential_reference` 只回显引用名）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            rows = (
                await uow.session.execute(
                    select(
                        SoftwareInstanceORM,
                        SoftwareVersionORM,
                        SoftwareProductORM,
                        SoftwareORM,
                    )
                    .join(
                        SoftwareVersionORM,
                        SoftwareVersionORM.id == SoftwareInstanceORM.version_id,
                    )
                    .join(
                        SoftwareProductORM,
                        SoftwareProductORM.id == SoftwareVersionORM.product_id,
                    )
                    .join(SoftwareORM, SoftwareORM.id == SoftwareProductORM.software_id)
                    .order_by(SoftwareInstanceORM.name.asc())
                )
            ).all()
        return [
            {
                "id": str(instance.id),
                "name": instance.name,
                "vendor": software.vendor,
                "product": product.product,
                "version": version.version,
                "endpoint": instance.endpoint,
                "status": instance.status,
                "online": str(instance.status).upper() == "CONNECTED",
                "credential_reference": instance.credential_reference,
            }
            for instance, version, product, software in rows
        ]

    # ===== 任务 =====

    async def tasks(self, *, limit: int, offset: int) -> Mapping[str, Any]:
        """任务列表（租户作用域）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            tenant_id = await _tenant_of(uow.session)
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
            tenant_id = await _tenant_of(uow.session)
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
                        "started_at": _iso(step.started_at),
                        "completed_at": _iso(step.completed_at),
                    }
                    for step in view.steps
                ],
            }

    async def cancel(self, task_id: str) -> Mapping[str, Any]:
        """请求取消（返回真实结果，**不**伪造终态）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            engine = self._engine(uow.session)
            tenant_id = await _tenant_of(uow.session)
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
            tenant_id = await _tenant_of(uow.session)
            entries = await build_audit_store(uow.session).chain(tenant_id=tenant_id, limit=limit)
        return [
            {
                "id": entry.id,
                "time": _iso(entry.created_at),
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
) -> ManagementService:
    """装配管理面服务（**不**做 I/O）。"""
    return ManagementService(
        runtime=runtime,
        catalog=catalog,
        templates=templates,
        import_root=pathlib.Path(import_root),
        version=version,
    )


# ===== 查询辅助（只读）=====


async def _task_counts(session: Any) -> dict[str, Any]:
    """按状态计数（一次分组查询）。"""
    rows = (
        await session.execute(
            select(TaskORM.status, func.count()).select_from(TaskORM).group_by(TaskORM.status)
        )
    ).all()
    counts = {str(status): int(count) for status, count in rows}
    active = sum(counts.get(status, 0) for status in TASK_ACTIVE_STATUSES)
    return {
        "total": sum(counts.values()),
        "active": active,
        "queued": counts.get("QUEUED", 0),
        "running": counts.get("RUNNING", 0),
        "failed": counts.get("FAILED", 0),
        "completed": counts.get("COMPLETED", 0),
        "by_status": counts,
    }


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


async def _client_counts(session: Any) -> tuple[int, int]:
    """实例总数 / 已连接数。"""
    total = int(
        (await session.execute(select(func.count()).select_from(SoftwareInstanceORM))).scalar_one()
    )
    connected = int(
        (
            await session.execute(
                select(func.count())
                .select_from(SoftwareInstanceORM)
                .where(SoftwareInstanceORM.status == "CONNECTED")
            )
        ).scalar_one()
    )
    return total, connected


async def _tenant_of(session: Any) -> str:
    """当前部署的租户（种子只有一个租户；取不到 ⇒ 7000，**不**猜）。"""
    from app.infrastructure.database.models.tenant import TenantORM

    tenant_id = (await session.execute(select(TenantORM.id))).scalars().first()
    if tenant_id is None:
        raise InternalError(
            "no tenant is provisioned",
            details={"stage": "management", "reason": "tenant_not_found"},
        )
    return str(tenant_id)


def _task_row(task: Any) -> dict[str, Any]:
    """`TaskRecord` → JSON 行（**不含** result / error 原文）。"""
    return {
        "id": task.id,
        "tool": task.tool,
        "operation": task.operation,
        "status": task.status,
        "progress": task.progress,
        "project_id": task.project_id,
        "created_at": _iso(task.created_at),
        "started_at": _iso(task.started_at),
        "completed_at": _iso(task.completed_at),
        "retry_count": task.retry_count,
        "cancel_requested": task.cancel_requested,
    }


def _iso(value: Any) -> str | None:
    """时间 → ISO 字符串（`None` 原样）。"""
    return None if value is None else str(value.isoformat())
