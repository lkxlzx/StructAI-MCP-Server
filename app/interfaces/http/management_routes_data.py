"""Interface · HTTP · 管理面 · 数据 / 日志 / 安全概览路由（P185）。

⚠️ 全部是**薄转发**：备份 / 恢复 / 清理 / 导入的判定在 Application 端口，
本模块只做 HTTP 形状与鉴权（写操作要求 `SYSTEM_ADMIN`）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.application.management import ManagementPort
from app.domain.errors import NotFoundError, StructAIError
from app.interfaces.http.management_shared import (
    AdminDependency,
    IdentityDependency,
    error_response,
    json_payload,
)


def register_data_routes(
    router: APIRouter,
    port: ManagementPort,
    *,
    identity: IdentityDependency,
    admin: AdminDependency,
) -> None:
    """把数据管理 / 日志 / 安全概览路由挂到 `router` 上。"""

    # ===== 数据统计 / 备份 =====

    @router.get("/data/stats")
    async def data_stats(request: Request) -> Any:
        """数据库 / 存储 / 表行数 / 备份摘要。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload(await port.storage_stats())

    @router.post("/data/backup")
    async def data_backup(request: Request) -> Any:
        """立即备份（SQLite backup API；含设置库）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        try:
            return json_payload(await port.create_backup())
        except StructAIError as error:
            return error_response(error)

    @router.get("/data/backups")
    async def data_backups(request: Request) -> Any:
        """备份记录。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload({"items": list(await port.backups())})

    @router.delete("/data/backups/{backup_id}")
    async def data_backup_delete(request: Request, backup_id: str) -> Any:
        """删除备份。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        try:
            return json_payload(await port.delete_backup(backup_id))
        except StructAIError as error:
            return error_response(error)

    @router.get("/data/backups/{backup_id}/download")
    async def data_backup_download(request: Request, backup_id: str) -> Any:
        """下载备份（zip 文件流；文件名只取备份标识）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        try:
            archive = await port.backup_archive(backup_id)
        except StructAIError as error:
            return error_response(error)
        from fastapi.responses import FileResponse

        return FileResponse(
            str(archive["path"]),
            media_type="application/zip",
            filename=f"{backup_id}.zip",
        )

    @router.post("/data/backups/{backup_id}/restore")
    async def data_backup_restore(request: Request, backup_id: str) -> Any:
        """从备份恢复（先自动生成 pre-restore 备份）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        try:
            return json_payload(await port.restore_backup(backup_id))
        except StructAIError as error:
            return error_response(error)

    # ===== 清理 / 清空 / 导入 / 导出 =====

    @router.post("/data/cleanup")
    async def data_cleanup(request: Request) -> Any:
        """按类别清理（审计记录永不删除）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        body = await request.json()
        return json_payload(await port.cleanup(dict(body or {})))

    @router.post("/data/purge")
    async def data_purge(request: Request) -> Any:
        """清空业务数据（保留管理员 / 角色 / 软件注册表；审计不删）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload(await port.purge_data())

    @router.post("/data/import")
    async def data_import(request: Request) -> Any:
        """导入导出的设置（只接受 settings 分区）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        body = await request.json()
        try:
            return json_payload(await port.import_data(dict(body or {})))
        except StructAIError as error:
            return error_response(error)

    @router.get("/data/export")
    async def data_export(request: Request) -> Any:
        """导出设置与摘要（不含口令哈希 / 明文密钥）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload(await port.export_data())

    # ===== 日志 / 目录浏览 / 安全概览 =====

    @router.get("/logs")
    async def logs(request: Request, level: str = "", q: str = "", limit: int = 200) -> Any:
        """运行日志尾部（按级别 / 关键词过滤）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload(
            await port.logs(level=level, query=q, limit=_bounded(limit, default=200, maximum=1000))
        )

    @router.get("/fs/browse")
    async def fs_browse(request: Request, path: str = "") -> Any:
        """目录浏览（选择目录用；只列子目录）。"""
        current = await admin(request)
        if isinstance(current, JSONResponse):
            return current
        try:
            return json_payload(await port.browse(path))
        except StructAIError as error:
            return error_response(error)
        except NotFoundError as error:
            return JSONResponse(
                status_code=404,
                content={"code": "NOT_FOUND", "message": str(error), "details": {}},
            )

    @router.get("/security/overview")
    async def security_overview(request: Request) -> Any:
        """安全统计（锁定账号 / 活跃会话 / 24h 审计 / 最近审计链）。"""
        current = await identity(request)
        if isinstance(current, JSONResponse):
            return current
        return json_payload(await port.security_overview())


def _bounded(value: int, *, default: int = 20, maximum: int = 200) -> int:
    """列表条数上限（**禁止**无限 payload，`docs/07` §14.4）。"""
    if value <= 0:
        return default
    return min(int(value), maximum)
