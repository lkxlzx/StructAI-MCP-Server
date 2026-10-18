"""Infrastructure · Management · 共享辅助（P185）。

`service.py` / `settings_admin.py` / `clients.py` 共用的只读查询与路径解析：

- `tenant_of` / `iso` —— 租户与时间；
- `CORE_TABLES` / `PURGE_TABLES` —— 统计与清空的白名单（**不**含审计）；
- `browse_roots` / `browse_directory` / `tail_lines` —— 目录浏览与日志尾部；
- `runtime_facts` / `database_path` / `backup_root` / `safe_backup_dir` ——
  关于系统页与备份路径（**不**编造：取不到就留空）。

⚠️ 本模块只做只读查询 / 路径解析，不做业务判定。
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Final

from sqlalchemy import func, select

from app.domain.errors import InternalError, NotFoundError, ProtocolError
from app.infrastructure.database.models.document import DocumentORM
from app.infrastructure.database.models.idempotency import IdempotencyRecordORM
from app.infrastructure.database.models.model import ModelORM
from app.infrastructure.database.models.project import ProjectMemberORM, ProjectORM
from app.infrastructure.database.models.resource_lock import ResourceLockORM
from app.infrastructure.database.models.session import SessionORM
from app.infrastructure.database.models.software import SoftwareInstanceORM
from app.infrastructure.database.models.task import TaskORM, TaskStepORM
from app.infrastructure.database.models.tenant import TenantORM

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


async def tenant_of(session: Any) -> str:
    """当前部署的租户（种子只有一个租户；取不到 ⇒ 7000，**不**猜）。"""
    tenant_id = (await session.execute(select(TenantORM.id))).scalars().first()
    if tenant_id is None:
        raise InternalError(
            "no tenant is provisioned",
            details={"stage": "management", "reason": "tenant_not_found"},
        )
    return str(tenant_id)


def iso(value: Any) -> str | None:
    """时间 → ISO 字符串（`None` 原样）。"""
    return None if value is None else str(value.isoformat())


CORE_TABLES: Final[tuple[str, ...]] = (
    "tenants",
    "users",
    "roles",
    "permissions",
    "user_roles",
    "role_permissions",
    "sessions",
    "projects",
    "project_members",
    "software",
    "software_products",
    "software_versions",
    "software_instances",
    "models",
    "documents",
    "capabilities",
    "operations",
    "operation_capabilities",
    "tasks",
    "task_steps",
    "artifacts",
    "resource_locks",
    "idempotency_records",
    "audit_records",
)
"""统计页展示的 Core 表（`docs/07` §4.3 的 24 张；只读计数）。"""

PURGE_TABLES: Final[tuple[tuple[str, Any, Any], ...]] = (
    ("task_steps", TaskStepORM, None),
    ("tasks", TaskORM, TaskORM.tenant_id),
    ("documents", DocumentORM, None),
    ("models", ModelORM, None),
    ("project_members", ProjectMemberORM, None),
    ("projects", ProjectORM, ProjectORM.tenant_id),
    ("sessions", SessionORM, SessionORM.tenant_id),
    ("idempotency_records", IdempotencyRecordORM, IdempotencyRecordORM.tenant_id),
    ("resource_locks", ResourceLockORM, None),
)
"""`purge_data()` 清理的表（审计 / 用户 / 角色 / 软件注册表**不在**其中）。"""


def browse_roots() -> dict[str, Any]:
    """根目录列表（Windows = 存在的盘符；其余 = `/`）。"""
    import string

    roots: list[dict[str, str]] = []
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.isdir(drive):
                roots.append({"name": drive, "path": drive})
    else:
        roots.append({"name": "/", "path": "/"})
    return {"path": "", "parent": "", "items": roots}


def browse_directory(target: pathlib.Path) -> dict[str, Any]:
    """列出目录的直接子目录（不可读 ⇒ `STRUCTAI-1000`）。"""
    entries: list[dict[str, str]] = []
    try:
        for entry in sorted(target.iterdir(), key=lambda item: item.name.lower()):
            try:
                if entry.is_dir():
                    entries.append({"name": entry.name, "path": str(entry)})
            except OSError:
                continue
    except OSError as error:
        raise ProtocolError(
            "directory is not readable",
            details={"stage": "management", "reason": "directory_unreadable"},
        ) from error
    parent = str(target.parent) if target.parent != target else ""
    return {"path": str(target), "parent": parent, "items": entries}


def tail_lines(path: pathlib.Path, limit: int) -> list[str]:
    """读取文件尾部最多 `limit` 行（避免把整份日志读进内存）。"""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            block = min(size, max(64 * 1024, limit * 400))
            handle.seek(size - block)
            data = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    return data.splitlines()[-limit:]


def runtime_facts(runtime: Any, version: str, store: Any) -> dict[str, Any]:
    """关于系统页的只读信息（**不**编造：取不到就留空）。"""
    import platform
    import sys

    from app.config.logging import log_directory

    database_path_value = database_path(runtime)
    import_root = str(getattr(runtime.settings, "management_import_root", ""))
    directory = log_directory()
    return {
        "version": version,
        "python": sys.version.split()[0],
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "database": str(database_path_value),
        "settings_path": str(store.path),
        "registry_root": str(getattr(runtime.settings, "registry_root", "")),
        "artifact_root": str(getattr(runtime.settings, "artifact_root", "")),
        "import_root": import_root,
        "log_dir": str(directory) if directory is not None else "",
        "build_time": datetime.fromtimestamp(pathlib.Path(__file__).stat().st_mtime, UTC).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "transport": "http",
    }


def database_path(runtime: Any) -> pathlib.Path:
    """从 `database_url` 解析 SQLite 文件路径（非 SQLite ⇒ 空路径）。

    相对路径按进程工作目录解析成绝对路径：关于系统页与备份路径都应显示可点击
    的真实位置，而不是 `./data/...`。
    """
    url = str(getattr(runtime.settings, "database_url", ""))
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        return pathlib.Path("")
    return pathlib.Path(url[len(prefix) :]).resolve()


def backup_root(runtime: Any) -> pathlib.Path:
    """备份根目录：数据库同级的 `backup/`（`docs/02` §20）。"""
    database_path_value = database_path(runtime)
    base = database_path_value.parent if str(database_path_value) else pathlib.Path("./data")
    return base / "backup"


def safe_backup_dir(runtime: Any, backup_id: str) -> pathlib.Path:
    """把备份标识解析为备份根下的直接子目录（拒绝路径穿越）。"""
    name = str(backup_id or "").strip()
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        # 用 404 而不是 400：`/data/backups/{id}` 的非法段会被路由当成别的路径，
        # 对调用方而言「这个备份不存在」才是可操作的信息（不暴露路径判定细节）。
        raise NotFoundError("unknown backup")
    root = backup_root(runtime)
    target = (root / name).resolve()
    if root.resolve() not in target.parents:
        raise NotFoundError("unknown backup")
    return target


def purge_backups(root: pathlib.Path, keep: int) -> int:
    """只保留最近 `keep` 份备份，其余删除（返回删除数量）。"""
    if not root.is_dir():
        return 0
    import shutil

    entries = sorted((item for item in root.iterdir() if item.is_dir()), reverse=True)
    removed = 0
    for entry in entries[max(keep, 1) :]:
        try:
            shutil.rmtree(entry)
            removed += 1
        except OSError:
            continue
    return removed


def directory_size(root: pathlib.Path) -> int:
    """目录占用（不存在 ⇒ 0；权限错误逐项跳过）。"""
    if not root.is_dir():
        return 0
    total = 0
    for item in root.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def purge_directory(root: pathlib.Path) -> int:
    """清空临时目录（只删文件，保留目录；返回删除数量）。"""
    if not root.is_dir():
        return 0
    removed = 0
    for item in root.rglob("*"):
        try:
            if item.is_file():
                item.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def days(value: Any, default: int) -> int:
    """天数参数（非正数 / 非数字 ⇒ 默认值）。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def names_of(roles: Any) -> list[str]:
    """角色入参归一（字符串或字符串列表）。"""
    if isinstance(roles, str):
        return [roles] if roles else []
    if isinstance(roles, Sequence):
        return [str(item) for item in roles if str(item)]
    return []


async def task_counts(session: Any) -> dict[str, Any]:
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


async def client_counts(session: Any) -> tuple[int, int]:
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
