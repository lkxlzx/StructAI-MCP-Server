"""Infrastructure · Management · 软件客户端（P185）。

`software` → `software_products` → `software_versions` → `software_instances`
四级注册表的**写**侧（读侧也在此，因为前端客户端页需要同一条链）：

- `clients()` / `client_options()` —— 列表与候选值；
- `create_client()` / `update_client()` / `delete_client()` —— 按 (vendor, product,
  version) 三元组**按需创建**版本链；删除实例后清理不再被引用的孤儿行；
- `test_client()` —— 真实探测（已绑定 Adapter ⇒ 健康检查；只有地址 ⇒ HTTP 探测）；
- `client_events()` —— 本机运维库里的连接测试 / 生命周期事件。

⚠️ 描述等展示字段落在独立运维库（`SettingsStore.client_profiles`）：
   Core 的 `software_instances` 是冻结口径（`docs/07` §4.3），不得加列。
⚠️ 凭据只存引用名（`credential_reference`），值由运行环境注入。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import func, select

from app.domain.enums import SoftwareConnectionState, SoftwareStatus
from app.domain.errors import NotFoundError, ProtocolError
from app.infrastructure.database.models.software import (
    SoftwareInstanceORM,
    SoftwareORM,
    SoftwareProductORM,
    SoftwareVersionORM,
)
from app.infrastructure.database.unit_of_work import UnitOfWork

__all__ = ["ClientManagementMixin", "client_row"]


class ClientManagementMixin:
    """`ManagementPort` 的客户端 CRUD（由 `ManagementService` 混入）。"""

    # 由 `ManagementService` 提供
    _runtime: Any

    def _factory(self) -> Any:  # pragma: no cover - 类型声明
        raise NotImplementedError

    def _settings_store(self) -> Any:  # pragma: no cover - 类型声明
        raise NotImplementedError

    # ===== 读 =====

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
        profiles = self._settings_store().read_client_profiles()
        return [
            client_row(
                instance,
                version,
                product,
                software,
                description=str(profiles.get(str(instance.id), {}).get("description") or ""),
            )
            for instance, version, product, software in rows
        ]

    async def client_options(self) -> Mapping[str, Any]:
        """候选值：已登记的软件 / 产品 / 版本链 + 可用的凭据引用。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            software = (
                (await uow.session.execute(select(SoftwareORM).order_by(SoftwareORM.vendor)))
                .scalars()
                .all()
            )
            products = (
                (
                    await uow.session.execute(
                        select(SoftwareProductORM).order_by(SoftwareProductORM.product)
                    )
                )
                .scalars()
                .all()
            )
            versions = (
                (
                    await uow.session.execute(
                        select(SoftwareVersionORM).order_by(SoftwareVersionORM.version)
                    )
                )
                .scalars()
                .all()
            )
            instances = (await uow.session.execute(select(SoftwareInstanceORM))).scalars().all()
        software_by_id = {str(row.id): row for row in software}
        product_by_id = {str(row.id): row for row in products}
        return {
            "software": [
                {"id": str(row.id), "vendor": row.vendor, "name": row.name} for row in software
            ],
            "products": [
                {
                    "id": str(row.id),
                    "product": row.product,
                    "software_id": str(row.software_id),
                    "vendor": software_by_id[str(row.software_id)].vendor
                    if str(row.software_id) in software_by_id
                    else "",
                }
                for row in products
            ],
            "versions": [
                {
                    "id": str(row.id),
                    "version": row.version,
                    "product_id": str(row.product_id),
                    "product": product_by_id[str(row.product_id)].product
                    if str(row.product_id) in product_by_id
                    else "",
                }
                for row in versions
            ],
            "statuses": [state.value for state in SoftwareConnectionState],
            "credential_references": sorted(
                {str(row.credential_reference) for row in instances if row.credential_reference}
            ),
        }

    # ===== 写 =====

    async def create_client(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """登记一个软件实例（自动补齐 software → product → version 链）。"""
        name = str(payload.get("name") or "").strip()
        vendor = str(payload.get("vendor") or "").strip()
        product_name = str(payload.get("product") or "").strip()
        version_name = str(payload.get("version") or "").strip()
        if not name or not vendor or not product_name or not version_name:
            raise ProtocolError(
                "name, vendor, product and version are required",
                details={"stage": "management", "reason": "client_fields_missing"},
            )
        status = str(payload.get("status") or SoftwareConnectionState.DISCONNECTED.value).upper()
        if status not in {state.value for state in SoftwareConnectionState}:
            raise ProtocolError(
                "unknown software connection state",
                details={"stage": "management", "reason": "client_status_invalid"},
            )
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            version = await _ensure_chain(uow.session, vendor, product_name, version_name)
            instance = SoftwareInstanceORM(
                version_id=str(version.id),
                name=name,
                endpoint=str(payload.get("endpoint") or "") or None,
                status=status,
                credential_reference=str(payload.get("credential_reference") or "") or None,
            )
            uow.session.add(instance)
            await uow.session.flush()
            client_id = str(instance.id)
            created = client_row(instance, version, None, None)
        description = str(payload.get("description") or "")
        self._settings_store().write_client_profile(client_id, {"description": description})
        self._settings_store().append_client_event(
            client_id,
            {"action": "create", "result": "SUCCESS", "detail": f"登记实例 {name}"},
        )
        created["description"] = description
        created["vendor"] = vendor
        created["product"] = product_name
        return created

    async def update_client(self, client_id: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """更新软件实例（名称 / 产品 / 版本 / 地址 / 凭据引用 / 状态 / 描述）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            instance = (
                await uow.session.execute(
                    select(SoftwareInstanceORM).where(SoftwareInstanceORM.id == client_id)
                )
            ).scalar_one_or_none()
            if instance is None:
                raise NotFoundError(f"unknown client: {client_id}")
            if "name" in payload:
                name = str(payload.get("name") or "").strip()
                if not name:
                    raise ProtocolError(
                        "client name must not be blank",
                        details={"stage": "management", "reason": "client_name_blank"},
                    )
                instance.name = name
            if "endpoint" in payload:
                instance.endpoint = str(payload.get("endpoint") or "") or None
            if "credential_reference" in payload:
                instance.credential_reference = (
                    str(payload.get("credential_reference") or "") or None
                )
            if "status" in payload:
                status = str(payload.get("status") or "").upper()
                if status not in {state.value for state in SoftwareConnectionState}:
                    raise ProtocolError(
                        "unknown software connection state",
                        details={"stage": "management", "reason": "client_status_invalid"},
                    )
                instance.status = status
            if any(key in payload for key in ("vendor", "product", "version")):
                current = (
                    await uow.session.execute(
                        select(SoftwareVersionORM, SoftwareProductORM, SoftwareORM)
                        .join(
                            SoftwareProductORM,
                            SoftwareProductORM.id == SoftwareVersionORM.product_id,
                        )
                        .join(SoftwareORM, SoftwareORM.id == SoftwareProductORM.software_id)
                        .where(SoftwareVersionORM.id == instance.version_id)
                    )
                ).one()
                version_row, product_row, software_row = current
                vendor = str(payload.get("vendor") or software_row.vendor).strip()
                product_name = str(payload.get("product") or product_row.product).strip()
                version_name = str(payload.get("version") or version_row.version).strip()
                if not vendor or not product_name or not version_name:
                    raise ProtocolError(
                        "vendor, product and version must not be blank",
                        details={"stage": "management", "reason": "client_fields_missing"},
                    )
                version = await _ensure_chain(uow.session, vendor, product_name, version_name)
                instance.version_id = str(version.id)
            await uow.session.flush()
            row = (
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
                    .where(SoftwareInstanceORM.id == client_id)
                )
            ).one()
            updated = client_row(*row)
        if "description" in payload:
            self._settings_store().write_client_profile(
                client_id, {"description": str(payload.get("description") or "")}
            )
        updated["description"] = str(
            self._settings_store().read_client_profiles().get(client_id, {}).get("description")
            or ""
        )
        self._settings_store().append_client_event(
            client_id, {"action": "update", "result": "SUCCESS", "detail": "更新实例配置"}
        )
        return updated

    async def delete_client(self, client_id: str) -> Mapping[str, Any]:
        """删除软件实例（并清理不再被引用的版本 / 产品 / 软件行）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            instance = (
                await uow.session.execute(
                    select(SoftwareInstanceORM).where(SoftwareInstanceORM.id == client_id)
                )
            ).scalar_one_or_none()
            if instance is None:
                raise NotFoundError(f"unknown client: {client_id}")
            version_id = str(instance.version_id)
            await uow.session.delete(instance)
            await uow.session.flush()
            version = (
                await uow.session.execute(
                    select(SoftwareVersionORM).where(SoftwareVersionORM.id == version_id)
                )
            ).scalar_one_or_none()
            product_id = str(version.product_id) if version is not None else ""
            if version is not None and await _unreferenced(
                uow.session, SoftwareInstanceORM, SoftwareInstanceORM.version_id, version_id
            ):
                await uow.session.delete(version)
                await uow.session.flush()
            product = (
                await uow.session.execute(
                    select(SoftwareProductORM).where(SoftwareProductORM.id == product_id)
                )
            ).scalar_one_or_none()
            software_id = str(product.software_id) if product is not None else ""
            if product is not None and await _unreferenced(
                uow.session, SoftwareVersionORM, SoftwareVersionORM.product_id, product_id
            ):
                await uow.session.delete(product)
                await uow.session.flush()
            if software_id and await _unreferenced(
                uow.session, SoftwareProductORM, SoftwareProductORM.software_id, software_id
            ):
                software = (
                    await uow.session.execute(
                        select(SoftwareORM).where(SoftwareORM.id == software_id)
                    )
                ).scalar_one_or_none()
                if software is not None:
                    await uow.session.delete(software)
        self._settings_store().delete_client_profile(client_id)
        return {"deleted": client_id}

    # ===== 连接测试 / 事件 =====

    async def test_client(self, client_id: str) -> Mapping[str, Any]:
        """测试实例连通性（真实探测；无地址时如实报告未配置）。"""
        from datetime import UTC, datetime

        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            instance = (
                await uow.session.execute(
                    select(SoftwareInstanceORM).where(SoftwareInstanceORM.id == client_id)
                )
            ).scalar_one_or_none()
            if instance is None:
                raise NotFoundError(f"unknown client: {client_id}")
            endpoint = str(instance.endpoint or "")
            name = str(instance.name)
        checked_at = datetime.now(UTC).isoformat()
        adapters = getattr(self._runtime, "adapters", None)
        bound = (
            adapters is not None
            and hasattr(adapters, "bound_instance_ids")
            and client_id in adapters.bound_instance_ids()
        )
        if bound and adapters is not None:
            try:
                health = await adapters.health_check(client_id)
                reachable = bool(health.get("healthy"))
                result = {
                    "id": client_id,
                    "name": name,
                    "reachable": reachable,
                    "reason": None if reachable else "health_check_failed",
                    "latency_ms": health.get("latency_ms"),
                    "checked_at": checked_at,
                    "transport": "adapter",
                }
            except Exception as error:  # noqa: BLE001 - 如实报告，不让测试接口 500
                result = {
                    "id": client_id,
                    "name": name,
                    "reachable": False,
                    "reason": _error_reason(error),
                    "latency_ms": None,
                    "checked_at": checked_at,
                    "transport": "adapter",
                }
        elif endpoint:
            result = await _probe_endpoint(client_id, name, endpoint, checked_at)
        else:
            result = {
                "id": client_id,
                "name": name,
                "reachable": False,
                "reason": "endpoint_not_configured",
                "latency_ms": None,
                "checked_at": checked_at,
                "transport": "none",
            }
        self._settings_store().append_client_event(
            client_id,
            {
                "action": "test_connection",
                "result": "SUCCESS" if result["reachable"] else "FAILED",
                "detail": result.get("reason") or f"{result.get('latency_ms')} ms",
            },
        )
        return result

    # ===== 连接 / 断开（P185）=====

    async def connect_client(self, client_id: str) -> Mapping[str, Any]:
        """连接实例：按需注册 Adapter → 绑定 → 连接 → 健康检查 → 回写状态。

        `AdapterManager` 启动时只注册 Mock Adapter；真实厂商 Adapter 在首次连接时
        经 `plugins.adapter_class_for()` 发现并注册（`docs/07` §14.2：不在 Core 写厂商名）。

        Raises:
            ProtocolError: 没有可用的 Adapter 实现（`STRUCTAI-1000`）。
        """
        from app.infrastructure.adapters.plugins import adapter_class_for

        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            instance = (
                await uow.session.execute(
                    select(SoftwareInstanceORM).where(SoftwareInstanceORM.id == client_id)
                )
            ).scalar_one_or_none()
            if instance is None:
                raise NotFoundError(f"unknown client: {client_id}")
            version_row, product_row, software_row = (
                await uow.session.execute(
                    select(SoftwareVersionORM, SoftwareProductORM, SoftwareORM)
                    .join(
                        SoftwareProductORM,
                        SoftwareProductORM.id == SoftwareVersionORM.product_id,
                    )
                    .join(SoftwareORM, SoftwareORM.id == SoftwareProductORM.software_id)
                    .where(SoftwareVersionORM.id == instance.version_id)
                )
            ).one()
            name = str(instance.name)
            endpoint = str(instance.endpoint or "")
            credential = str(instance.credential_reference or "")
            vendor = str(software_row.vendor)
            product = str(product_row.product)
            version = str(version_row.version)

        adapters = getattr(self._runtime, "adapters", None)
        if adapters is None:
            raise ProtocolError(
                "adapter manager is not assembled",
                details={"stage": "management", "reason": "adapter_manager_missing"},
            )
        adapter_class = adapter_class_for(vendor, product)
        if adapter_class is None:
            raise ProtocolError(
                f"no adapter is available for {vendor} / {product}",
                details={
                    "stage": "management",
                    "reason": "adapter_not_found",
                    "vendor": vendor,
                    "product": product,
                },
            )
        key = (str(adapter_class.vendor), str(adapter_class.product))
        if key not in adapters.registered_keys():
            adapters.register(adapter_class())
        config = {
            key_name: value
            for key_name, value in {
                "base_url": endpoint,
                "product": product,
                "version": version,
                "secret_ref": credential or None,
            }.items()
            if value
        }
        result = await self._connect_bound(adapters, client_id, key, config)
        await self._set_status(client_id, "CONNECTED" if result["connected"] else "DEGRADED")
        self._settings_store().append_client_event(
            client_id,
            {
                "action": "connect",
                "result": "SUCCESS" if result["connected"] else "FAILED",
                "detail": result.get("reason") or name,
            },
        )
        result.update({"id": client_id, "name": name, "vendor": vendor, "product": product})
        return result

    async def disconnect_client(self, client_id: str) -> Mapping[str, Any]:
        """断开实例（幂等；未绑定也返回成功）。"""
        adapters = getattr(self._runtime, "adapters", None)
        if adapters is None:
            raise ProtocolError(
                "adapter manager is not assembled",
                details={"stage": "management", "reason": "adapter_manager_missing"},
            )
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            instance = (
                await uow.session.execute(
                    select(SoftwareInstanceORM).where(SoftwareInstanceORM.id == client_id)
                )
            ).scalar_one_or_none()
            if instance is None:
                raise NotFoundError(f"unknown client: {client_id}")
            name = str(instance.name)
        reason = None
        if client_id in adapters.bound_instance_ids():
            try:
                await adapters.disconnect(client_id)
            except Exception as error:  # noqa: BLE001 - 如实报告，不吞成 500
                reason = _error_reason(error)
            adapters.unbind_instance(client_id)
        await self._set_status(client_id, "DISCONNECTED")
        self._settings_store().append_client_event(
            client_id,
            {
                "action": "disconnect",
                "result": "SUCCESS" if reason is None else "FAILED",
                "detail": reason or name,
            },
        )
        return {"id": client_id, "name": name, "connected": False, "reason": reason}

    async def _connect_bound(
        self,
        adapters: Any,
        client_id: str,
        key: tuple[str, str],
        config: Mapping[str, Any],
    ) -> dict[str, Any]:
        """绑定 + 连接 + 健康检查（异常归一化为结果，**不**抛给路由）。"""
        try:
            adapters.bind_instance(client_id, vendor=key[0], product=key[1], config=config)
            health = await adapters.connect(client_id)
        except Exception as error:  # noqa: BLE001 - 连接失败是正常结果，不是 500
            return {"connected": False, "reason": _error_reason(error), "health": None}
        return {
            "connected": bool(health.get("healthy")),
            "reason": None if health.get("healthy") else health.get("state"),
            "health": dict(health),
        }

    async def _set_status(self, client_id: str, status: str) -> None:
        """回写实例状态（`software_instances.status` 是真实连接状态）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            instance = (
                await uow.session.execute(
                    select(SoftwareInstanceORM).where(SoftwareInstanceORM.id == client_id)
                )
            ).scalar_one_or_none()
            if instance is not None:
                instance.status = status
                await uow.session.flush()

    async def client_events(
        self, client_id: str, *, limit: int = 50
    ) -> Sequence[Mapping[str, Any]]:
        """实例的连接测试 / 生命周期事件（本机运维库，最新在前）。"""
        return self._settings_store().read_client_events(client_id, limit=limit)


# ===== 辅助 =====


async def _ensure_chain(
    session: Any, vendor: str, product_name: str, version_name: str
) -> SoftwareVersionORM:
    """按 (vendor, product, version) 取或建四级链，返回版本行。"""
    software = (
        await session.execute(
            select(SoftwareORM).where(
                SoftwareORM.vendor == vendor, SoftwareORM.name == product_name
            )
        )
    ).scalar_one_or_none()
    if software is None:
        software = SoftwareORM(
            vendor=vendor, name=product_name, status=SoftwareStatus.ENABLED.value
        )
        session.add(software)
        await session.flush()
    product = (
        await session.execute(
            select(SoftwareProductORM).where(
                SoftwareProductORM.software_id == str(software.id),
                SoftwareProductORM.product == product_name,
            )
        )
    ).scalar_one_or_none()
    if product is None:
        product = SoftwareProductORM(software_id=str(software.id), product=product_name)
        session.add(product)
        await session.flush()
    version = (
        await session.execute(
            select(SoftwareVersionORM).where(
                SoftwareVersionORM.product_id == str(product.id),
                SoftwareVersionORM.version == version_name,
            )
        )
    ).scalar_one_or_none()
    if version is None:
        version = SoftwareVersionORM(product_id=str(product.id), version=version_name)
        session.add(version)
        await session.flush()
    return version


async def _unreferenced(session: Any, model: Any, column: Any, value: str) -> bool:
    """`model` 中是否**没有**任何行引用 `column == value`（删除孤儿链用）。"""
    count = (
        await session.execute(select(func.count()).select_from(model).where(column == value))
    ).scalar_one()
    return int(count) == 0


async def _probe_endpoint(
    client_id: str, name: str, endpoint: str, checked_at: str
) -> dict[str, Any]:
    """对 HTTP 端点做一次真实探测（能建立 HTTP 连接即视为可达）。"""
    import time

    import httpx

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
            await client.get(endpoint)
    except httpx.HTTPError as error:
        return {
            "id": client_id,
            "name": name,
            "reachable": False,
            "reason": type(error).__name__,
            "latency_ms": None,
            "checked_at": checked_at,
            "transport": "http",
        }
    latency = round((time.perf_counter() - started) * 1000.0, 1)
    return {
        "id": client_id,
        "name": name,
        "reachable": True,
        "reason": None,
        "latency_ms": latency,
        "checked_at": checked_at,
        "transport": "http",
    }


def _error_reason(error: Exception) -> str:
    """异常 → 非敏感短原因（优先 `details.reason`，其次异常类名）。"""
    details = getattr(error, "details", None)
    if isinstance(details, Mapping) and details.get("reason"):
        return str(details["reason"])
    return type(error).__name__


def client_row(
    instance: Any,
    version: Any,
    product: Any = None,
    software: Any = None,
    *,
    description: str = "",
) -> dict[str, Any]:
    """实例 + 版本链 → 前端行（**不含**凭据值；链缺失时字段留空）。"""
    return {
        "id": str(instance.id),
        "name": instance.name,
        "vendor": getattr(software, "vendor", "") if software is not None else "",
        "product": getattr(product, "product", "") if product is not None else "",
        "version": getattr(version, "version", "") if version is not None else "",
        "endpoint": instance.endpoint,
        "status": instance.status,
        "online": str(instance.status).upper() == "CONNECTED",
        "credential_reference": instance.credential_reference,
        "description": description,
    }
