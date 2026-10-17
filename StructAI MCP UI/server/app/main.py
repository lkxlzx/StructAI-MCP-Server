"""
MIDAS MCP 管理器 · Web 版服务端
- 托管共享前端（web/），浏览器访问即得与 Win 版完全一致的界面
- 提供 REST API（当前由 mock 数据驱动，接入真实 MCP 服务时替换 service 层实现）
- 预留 MCP 服务进程控制接口（启动/停止/状态）

运行：python -m uvicorn server.app.main:app --host 0.0.0.0 --port 8765
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = pathlib.Path(__file__).resolve().parents[2]
WEB_DIR = ROOT / "web"

app = FastAPI(title="MIDAS MCP 管理器", version="1.0.0")


@app.middleware("http")
async def no_cache(request, call_next):
    """静态资源禁用缓存，避免改了前端却看到旧页面。"""
    resp = await call_next(request)
    resp.headers["Cache-Control"] = "no-store, must-revalidate"
    return resp

# ---------------------------------------------------------------- 状态与数据
STATE: dict[str, Any] = {
    "running": True,
    "version": "v1.0.0",
    "port": 8765,
    "clients": 2,
    "clientsTotal": 5,
    "activeTasks": 1,
    "queued": 0,
    "failed": 1,
    "requestsToday": 128,
    "requestsYesterday": 114,
    "avgResponseMs": 45,
    "avgResponseMsYesterday": 55,
}

EVENTS = [
    {"time": "14:23:45", "text": "MCP 服务启动成功", "level": "ok"},
    {"time": "14:22:10", "text": "CIVIL NX 连接成功", "level": "ok"},
    {"time": "14:18:33", "text": "任务 JOB-20250816-001 开始执行", "level": "info"},
    {"time": "14:15:21", "text": "任务 JOB-20250816-003 已完成", "level": "info"},
    {"time": "14:13:05", "text": "GEN NX 连接断开", "level": "error"},
    {"time": "14:10:12", "text": "重新连接 GEN NX 成功", "level": "ok"},
    {"time": "14:08:44", "text": "MCP 客户端连接: 192.168.1.100", "level": "info"},
    {"time": "14:05:21", "text": "API 请求异常: /db/NODE", "level": "error"},
    {"time": "14:02:18", "text": "系统初始化完成", "level": "ok"},
    {"time": "14:00:01", "text": "MCP 服务启动中...", "level": "info"},
]

TASKS = [
    {"id": "JOB-20250816-001", "type": "计算分析", "client": "CIVIL NX (本机)", "status": "running", "progress": 60, "start": "14:23:45"},
    {"id": "JOB-20250816-002", "type": "建模", "client": "GEN NX (服务器)", "status": "running", "progress": 30, "start": "14:22:10"},
    {"id": "JOB-20250816-003", "type": "结果查询", "client": "CIVIL NX (本机)", "status": "done", "progress": 100, "start": "14:15:21"},
    {"id": "JOB-20250816-004", "type": "设计校核", "client": "FEA NX", "status": "done", "progress": 100, "start": "13:50:12"},
    {"id": "JOB-20250816-005", "type": "计算书生成", "client": "CIVIL NX (本机)", "status": "failed", "progress": 0, "start": "13:30:14"},
]

TREND = {
    "xLabels": ["08-10", "08-11", "08-12", "08-13", "08-14", "08-15", "08-16"],
    "yTicks": [0, 5, 10, 15, 20],
    "series": [
        {"name": "成功", "color": "#06A65A", "data": [6, 15, 13, 12, 15, 11, 16]},
        {"name": "失败", "color": "#FE3B36", "data": [1, 3, 2, 4, 2, 2, 1]},
        {"name": "运行中", "color": "#0065FE", "data": [3, 8, 6, 7, 4, 4, 7]},
    ],
}


# ---------------------------------------------------------------- API
@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "midas-mcp-manager", "version": STATE["version"]}


@app.get("/api/status")
def status() -> dict:
    """首页顶部状态与侧栏服务卡片使用。"""
    return dict(STATE)


@app.post("/api/service/start")
def service_start() -> dict:
    STATE["running"] = True
    return {"ok": True, "running": True}


@app.post("/api/service/stop")
def service_stop() -> dict:
    STATE["running"] = False
    return {"ok": True, "running": False}


@app.get("/api/stats")
def stats() -> list[dict]:
    """首页 5 张指标卡。"""
    return [
        {"key": "service", "label": "MCP 服务状态", "value": "运行中" if STATE["running"] else "已停止",
         "tone": "green" if STATE["running"] else "gray", "foot": STATE["version"]},
        {"key": "clients", "label": "已连接客户端", "value": str(STATE["clients"]),
         "foot": f"总计 {STATE['clientsTotal']}"},
        {"key": "tasks", "label": "活跃任务", "value": str(STATE["activeTasks"]),
         "foot": f"排队 {STATE['queued']} | 失败 {STATE['failed']}"},
        {"key": "requests", "label": "今日请求数", "value": str(STATE["requestsToday"]),
         "delta": "+12%", "foot": f"昨日 {STATE['requestsYesterday']}"},
        {"key": "latency", "label": "平均响应时间", "value": f"{STATE['avgResponseMs']} ms",
         "delta": "-18%", "foot": f"昨日 {STATE['avgResponseMsYesterday']} ms"},
    ]


@app.get("/api/tasks")
def tasks(limit: int = 5) -> dict:
    return {"total": len(TASKS), "items": TASKS[:limit]}


@app.get("/api/events")
def events(limit: int = 10) -> dict:
    return {"total": len(EVENTS), "items": EVENTS[:limit]}


@app.get("/api/chart/trend")
def chart_trend() -> dict:
    return TREND


# ---------------------------------------------------------------- 静态前端
@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/favicon.ico")
def favicon() -> JSONResponse:
    return JSONResponse({}, status_code=204)


app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    print(json.dumps({"web": str(WEB_DIR)}, ensure_ascii=False))
    uvicorn.run(app, host="127.0.0.1", port=STATE["port"])
