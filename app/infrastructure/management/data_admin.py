"""Infrastructure · Management · 数据管理（P183 / P185）。

`ManagementService` 的数据侧能力（mixin）：

- 统计 / 备份 / 恢复 / 删除 / 下载（SQLite backup API；设置库一并备份）；
- 按类别清理（审计记录**永不**删除）与清空业务数据；
- 导出 / 导入设置；运行日志尾部；目录浏览；SMTP 测试；检查更新；服务控制。

⚠️ 全部方法只做查询 / 文件 I/O 与转发，不做业务判定。
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select, text

from app.application.services.backup import backup_database
from app.domain.errors import InternalError, NotFoundError, ProtocolError
from app.infrastructure.database.models.audit import AuditRecordORM
from app.infrastructure.database.models.session import SessionORM
from app.infrastructure.database.models.task import TaskORM
from app.infrastructure.database.models.user import UserORM
from app.infrastructure.database.repositories import build_audit_store
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.infrastructure.management.common import (
    CORE_TABLES,
    PURGE_TABLES,
    backup_root,
    browse_directory,
    browse_roots,
    client_counts,
    database_path,
    days,
    directory_size,
    iso,
    purge_backups,
    purge_directory,
    safe_backup_dir,
    tail_lines,
    task_counts,
    tenant_of,
)


class DataManagementMixin:
    """`ManagementPort` 的数据管理（由 `ManagementService` 混入）。"""

    # 由 `ManagementService` 提供
    _runtime: Any
    _version: str
    _templates: Any
    _catalog: Any

    def _factory(self) -> Any:  # pragma: no cover - 类型声明
        raise NotImplementedError

    async def settings(self) -> Any:  # pragma: no cover - 由 SettingsManagementMixin 提供
        raise NotImplementedError

    def _settings_store(self) -> Any:  # pragma: no cover - 类型声明
        raise NotImplementedError

    async def storage_stats(self) -> Mapping[str, Any]:
        """数据管理统计（表行数 / 数据库与存储占用 / 备份摘要）。"""
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            tables = {}
            for table in CORE_TABLES:
                try:
                    count = (
                        await uow.session.execute(
                            text(f"SELECT COUNT(*) FROM {table}")  # noqa: S608 - 固定表名白名单
                        )
                    ).scalar_one()
                except Exception:  # noqa: BLE001 - 缺表时如实记 0，不让统计整体失败
                    count = 0
                tables[table] = int(count)
        database_path_value = database_path(self._runtime)
        storage_root = pathlib.Path(str(getattr(self._runtime.settings, "artifact_root", "")))
        backups = await self.backups()
        return {
            "database": {
                "path": str(database_path),
                "size": database_path_value.stat().st_size if database_path_value.is_file() else 0,
            },
            "storage": {
                "path": str(storage_root),
                "size": directory_size(storage_root),
            },
            "tables": tables,
            # 备份目录里已有的份数（设置里的「保留备份数量」据此给出建议）。
            "backups": backups,
            "backup_keep": days(
                self._settings_store().section("data").get("backup", {}).get("keep"), 7
            ),
            "retention": {
                "task_days": 30,
                "log_days": 60,
                "audit_days": 180,
            },
        }

    async def create_backup(self, kind: str = "manual") -> Mapping[str, Any]:
        """立即备份（`docs/02` §21 的 SQLite backup API；清单最后写）。

        同时备份设置库（`settings.db`）：它是独立文件，不随 Core 库一起复制。
        """
        database_path_value = database_path(self._runtime)
        if not database_path_value.is_file():
            raise InternalError(
                "database file is not available",
                details={"stage": "management", "reason": "database_missing"},
            )
        root = backup_root(self._runtime)
        moment = datetime.now(UTC)
        target = root / moment.strftime("%Y%m%dT%H%M%S")
        suffix = 1
        while target.exists():
            target = root / f"{moment.strftime('%Y%m%dT%H%M%S')}-{suffix}"
            suffix += 1
        target.mkdir(parents=True, exist_ok=True)
        backup_database(database_path_value, target / "structai.db")
        store = self._settings_store()
        if store.path.is_file():
            store.backup_to(target / "settings.db")
        manifest = {
            "backup_id": target.name,
            "created_at": iso(moment),
            "type": "manual" if kind != "pre-restore" else "pre-restore",
            "database": {
                "file": "structai.db",
                "size": (target / "structai.db").stat().st_size,
            },
            "settings": {
                "file": "settings.db",
                "size": (target / "settings.db").stat().st_size
                if (target / "settings.db").is_file()
                else 0,
            },
            "artifacts": {"count": 0, "bytes": 0},
            "version": "2.0",
        }
        (target / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        return {"ok": True, **manifest, "path": str(target)}

    async def restore_backup(self, backup_id: str) -> Mapping[str, Any]:
        """从备份恢复（恢复前先做一份 `pre-restore` 备份；设置库一并恢复）。

        ⚠️ Core 库的覆盖使用 SQLite backup API（不是文件复制），避免运行中的
        连接读到半写状态；恢复后要求调用方重启进程以重新装配 Registry。
        """
        target = safe_backup_dir(self._runtime, backup_id)
        source_db = target / "structai.db"
        if not source_db.is_file():
            raise NotFoundError(f"backup has no database file: {backup_id}")
        database_path_value = database_path(self._runtime)
        if not database_path_value.is_file():
            raise InternalError(
                "database file is not available",
                details={"stage": "management", "reason": "database_missing"},
            )
        emergency = await self.create_backup(kind="pre-restore")
        backup_database(source_db, database_path_value)
        settings_restored = False
        source_settings = target / "settings.db"
        if source_settings.is_file():
            self._settings_store().restore_from(source_settings)
            settings_restored = True
        return {
            "restored": True,
            "backup_id": backup_id,
            "pre_restore_backup": emergency["backup_id"],
            "database_restored": True,
            "settings_restored": settings_restored,
            "restart_required": True,
        }

    async def backups(self) -> Sequence[Mapping[str, Any]]:
        """备份记录（目录扫描；无 manifest 的目录如实标记为 incomplete）。"""
        root = backup_root(self._runtime)
        if not root.is_dir():
            return []
        items: list[Mapping[str, Any]] = []
        for entry in sorted(root.iterdir(), reverse=True):
            if not entry.is_dir():
                continue
            manifest_path = entry / "manifest.json"
            payload: dict[str, Any] = {}
            if manifest_path.is_file():
                try:
                    payload = dict(json.loads(manifest_path.read_text(encoding="utf-8")))
                except (OSError, json.JSONDecodeError):
                    payload = {}
            size = sum(item.stat().st_size for item in entry.rglob("*") if item.is_file())
            items.append(
                {
                    "id": entry.name,
                    "created_at": payload.get("created_at"),
                    "type": payload.get("type", "auto"),
                    "size": size,
                    "complete": bool(payload),
                    "has_settings": (entry / "settings.db").is_file(),
                    "path": str(entry),
                }
            )
        return items

    async def cleanup(self, categories: Mapping[str, Any]) -> Mapping[str, Any]:
        """按类别清理（任务 / 会话 / 临时目录；**审计记录永不删除**）。"""
        removed: dict[str, int] = {}
        now = datetime.now(UTC)
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            tenant_id = await tenant_of(uow.session)
            if categories.get("tasks", {}).get("enabled"):
                task_days = days(categories.get("tasks", {}).get("days"), 30)
                cutoff = now - timedelta(days=task_days)
                outcome = cast(
                    "CursorResult[Any]",
                    await uow.session.execute(
                        delete(TaskORM).where(
                            TaskORM.tenant_id == tenant_id,
                            TaskORM.completed_at.is_not(None),
                            TaskORM.completed_at < cutoff,
                        )
                    ),
                )
                removed["tasks"] = int(outcome.rowcount or 0)
            if categories.get("logs", {}).get("enabled"):
                log_days = days(categories.get("logs", {}).get("days"), 60)
                cutoff = now - timedelta(days=log_days)
                outcome = cast(
                    "CursorResult[Any]",
                    await uow.session.execute(
                        delete(SessionORM).where(
                            SessionORM.tenant_id == tenant_id,
                            SessionORM.expires_at < cutoff,
                        )
                    ),
                )
                removed["sessions"] = int(outcome.rowcount or 0)
        if categories.get("logs", {}).get("enabled"):
            # 日志清理同时清掉**过期**备份（保留最近 `backup.keep` 份）。
            keep = days(self._settings_store().section("data").get("backup", {}).get("keep"), 7)
            removed["backups"] = purge_backups(backup_root(self._runtime), keep)
        if categories.get("temp", {}).get("enabled"):
            temp_root = pathlib.Path(
                str(getattr(self._runtime.settings, "management_import_root", ""))
            )
            removed["temp_files"] = purge_directory(temp_root)
        removed["audit"] = 0  # docs/02 §29 / §45：审计记录不得由普通 retention 删除
        return {"removed": removed}

    async def security_overview(self) -> Mapping[str, Any]:
        """安全设置页统计（真实数据：锁定账号 / 24h 审计 / 最近审计链）。"""
        now = datetime.now(UTC)
        since = now - timedelta(hours=24)
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            tenant_id = await tenant_of(uow.session)
            locked = int(
                (
                    await uow.session.execute(
                        select(func.count())
                        .select_from(UserORM)
                        .where(UserORM.tenant_id == tenant_id, UserORM.locked.is_(True))
                    )
                ).scalar_one()
            )
            failed_total = int(
                (
                    await uow.session.execute(
                        select(func.coalesce(func.sum(UserORM.failed_login_count), 0)).where(
                            UserORM.tenant_id == tenant_id
                        )
                    )
                ).scalar_one()
            )
            active_sessions = int(
                (
                    await uow.session.execute(
                        select(func.count())
                        .select_from(SessionORM)
                        .where(
                            SessionORM.tenant_id == tenant_id,
                            SessionORM.revoked.is_(False),
                            SessionORM.expires_at > now,
                        )
                    )
                ).scalar_one()
            )
            audits_24h = int(
                (
                    await uow.session.execute(
                        select(func.count())
                        .select_from(AuditRecordORM)
                        .where(
                            AuditRecordORM.tenant_id == tenant_id,
                            AuditRecordORM.created_at >= since,
                        )
                    )
                ).scalar_one()
            )
            entries = await build_audit_store(uow.session).chain(tenant_id=tenant_id, limit=20)
        return {
            "locked_accounts": locked,
            "failed_login_total": failed_total,
            "active_sessions": active_sessions,
            "audit_24h": audits_24h,
            "events": [
                {
                    "time": iso(entry.created_at),
                    "action": entry.action,
                    "resource": entry.resource,
                    "result": entry.result,
                    "user": entry.user_id,
                }
                for entry in reversed(entries)
            ],
        }

    async def reset_settings(self, section: str = "") -> Mapping[str, Any]:
        """把分区（空串 = 全部）恢复为默认值。"""
        store = self._settings_store()
        if section:
            store.reset(section)
        else:
            store.reset()
        return await self.settings()

    async def test_notification(self, email: str) -> Mapping[str, Any]:
        """校验通知邮箱并**真实**尝试 SMTP 投递（未配置 ⇒ `delivered=False`）。

        SMTP 配置来自 `notify.smtp` 分区；口令**只**从环境变量
        `STRUCTAI_SMTP_PASSWORD` 读取（`docs/07` §14.3：禁止明文密钥入库）。
        """
        import smtplib
        from email.message import EmailMessage

        address = str(email or "").strip()
        valid = bool(address) and "@" in address and "." in address.split("@")[-1]
        if not valid:
            return {
                "email": address,
                "valid": False,
                "delivered": False,
                "reason": "invalid_email",
                "channel": "smtp",
                "configured": False,
            }
        smtp = self._settings_store().section("notify").get("smtp", {})
        host = str(smtp.get("host") or "").strip()
        if not host:
            return {
                "email": address,
                "valid": True,
                "delivered": False,
                "reason": "smtp_not_configured",
                "channel": "smtp",
                "configured": False,
            }
        port = days(smtp.get("port"), 587)
        sender = str(smtp.get("from") or smtp.get("username") or address)
        message = EmailMessage()
        message["Subject"] = "StructAI MCP 测试邮件"
        message["From"] = sender
        message["To"] = address
        message.set_content("这是一封来自 StructAI MCP 管理器的测试邮件。")
        password = os.environ.get("STRUCTAI_SMTP_PASSWORD", "")

        def _send() -> None:
            if smtp.get("tls", True):
                client = smtplib.SMTP(host, port, timeout=10)
                client.starttls()
            else:
                client = smtplib.SMTP(host, port, timeout=10)
            try:
                username = str(smtp.get("username") or "")
                if username and password:
                    client.login(username, password)
                client.send_message(message)
            finally:
                client.quit()

        try:
            await asyncio.to_thread(_send)
        except Exception as error:  # noqa: BLE001 - 如实报告，不让测试接口 500
            return {
                "email": address,
                "valid": True,
                "delivered": False,
                "reason": f"smtp_error:{type(error).__name__}",
                "channel": "smtp",
                "configured": True,
            }
        return {
            "email": address,
            "valid": True,
            "delivered": True,
            "reason": None,
            "channel": "smtp",
            "configured": True,
        }

    async def check_update(self) -> Mapping[str, Any]:
        """检查更新（无更新源 ⇒ 如实报告「当前已是最新」）。"""
        return {
            "current": self._version,
            "latest": self._version,
            "update_available": False,
            "source": None,
        }

    async def delete_backup(self, backup_id: str) -> Mapping[str, Any]:
        """删除一个备份目录（只允许备份根下的直接子目录）。"""
        target = safe_backup_dir(self._runtime, backup_id)
        if not target.is_dir():
            raise NotFoundError(f"unknown backup: {backup_id}")
        import shutil

        shutil.rmtree(target)
        return {"deleted": backup_id}

    async def backup_path(self, backup_id: str) -> str:
        """备份目录的绝对路径（路径守卫见 `_safe_backup_dir`）。"""
        target = safe_backup_dir(self._runtime, backup_id)
        if not target.is_dir():
            raise NotFoundError(f"unknown backup: {backup_id}")
        return str(target)

    async def backup_archive(self, backup_id: str) -> Mapping[str, Any]:
        """把备份目录打包成 zip（浏览器下载用；落在临时目录）。"""
        import shutil
        import tempfile

        target = safe_backup_dir(self._runtime, backup_id)
        if not target.is_dir():
            raise NotFoundError(f"unknown backup: {backup_id}")
        archive_dir = pathlib.Path(tempfile.gettempdir()) / "structai-backups"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive = archive_dir / f"{backup_id}.zip"
        if archive.is_file():
            archive.unlink()
        await asyncio.to_thread(
            shutil.make_archive, str(archive.with_suffix("")), "zip", str(target)
        )
        return {"backup_id": backup_id, "path": str(archive), "size": archive.stat().st_size}

    async def export_data(self) -> Mapping[str, Any]:
        """导出设置与只读摘要（**不含**口令哈希 / 明文密钥）。"""
        settings = await self.settings()
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            counts = await task_counts(uow.session)
            clients_total, clients_connected = await client_counts(uow.session)
        return {
            "exported_at": iso(datetime.now(UTC)),
            "version": self._version,
            "settings": settings,
            "summary": {
                "tasks": counts,
                "clients": {"total": clients_total, "connected": clients_connected},
                "templates": self._templates.summary(),
                "registry": self._catalog.summary(),
            },
        }

    async def import_data(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """导入导出的设置（只接受 `settings` 分区；`system` / 未知分区忽略）。"""
        settings = payload.get("settings")
        if not isinstance(settings, Mapping):
            raise ProtocolError(
                "import payload must contain a settings object",
                details={"stage": "management", "reason": "import_payload_invalid"},
            )
        applied = self._settings_store().replace_sections(settings)
        return {"imported": applied, "settings": await self.settings()}

    async def purge_data(self) -> Mapping[str, Any]:
        """清空业务数据（保留管理员 / 角色 / 权限 / 软件注册表；审计不删）。

        删除范围：任务与步骤、文档、模型、项目与成员、会话、幂等记录、资源锁。
        审计链（`audit_records`）**永不**由清理删除（`docs/02` §29 / §45）。
        """
        removed: dict[str, int] = {}
        async with UnitOfWork.from_session_factory(self._factory()) as uow:
            tenant_id = await tenant_of(uow.session)
            for name, model, column in PURGE_TABLES:
                statement = delete(model)
                if column is not None:
                    statement = statement.where(column == tenant_id)
                outcome = cast("CursorResult[Any]", await uow.session.execute(statement))
                removed[name] = int(outcome.rowcount or 0)
        removed["audit"] = 0
        return {"removed": removed}

    async def logs(
        self, *, level: str = "", query: str = "", limit: int = 200
    ) -> Mapping[str, Any]:
        """运行日志尾部（来自 `logs/structai.log`；按级别 / 关键词过滤）。

        日志文件由 `configure_logging()` 写入；未启用文件日志时
        如实返回空列表与 `available=False`，**不**伪造。
        """
        from app.config.logging import LOG_FILE_NAME, log_directory

        directory = log_directory()
        path = directory / LOG_FILE_NAME if directory is not None else None
        if path is None or not path.is_file():
            return {
                "available": False,
                "path": str(path) if path is not None else "",
                "items": [],
            }
        needle = query.strip().lower()
        wanted = level.strip().upper()
        lines = await asyncio.to_thread(tail_lines, path, 5000)
        items: list[dict[str, Any]] = []
        for line in reversed(lines):
            text = line.rstrip("\n")
            if not text:
                continue
            upper = text.upper()
            if wanted and f"LEVEL={wanted}" not in upper and wanted not in upper:
                continue
            if needle and needle not in text.lower():
                continue
            items.append({"line": text})
            if len(items) >= max(1, min(int(limit), 1000)):
                break
        return {"available": True, "path": str(path), "items": items}

    async def browse(self, path: str = "") -> Mapping[str, Any]:
        """目录浏览（选择目录用；只列子目录，拒绝不存在 / 非目录路径）。"""
        candidate = str(path or "").strip()
        if not candidate:
            return await asyncio.to_thread(browse_roots)
        target = pathlib.Path(candidate)
        if not await asyncio.to_thread(target.is_dir):
            raise NotFoundError(f"directory not found: {candidate}")
        return await asyncio.to_thread(browse_directory, target)

    async def service_control(self, action: str) -> Mapping[str, Any]:
        """服务控制（`stop` / `restart`；装配方未注入钩子时如实报告）。"""
        if action not in {"stop", "restart", "start"}:
            raise ProtocolError(
                "unknown service action",
                details={"stage": "management", "reason": "unknown_service_action"},
            )
        hook = getattr(self._runtime, "service_control", None)
        if hook is None:
            return {
                "action": action,
                "applied": False,
                "reason": "service_control_not_wired",
                "running": True,
            }
        result = hook(action)
        if hasattr(result, "__await__"):
            result = await result
        return {"action": action, "applied": True, **dict(result or {})}
