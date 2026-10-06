"""Interface · HTTP（`docs/07` §3.3 冻结结构；`docs/02` §95）。

`docs/02` §95 的目录形状是：

```text
interfaces/http/
├── api.py
├── health.py
└── management/
    ├── software.py
    ├── tasks.py
    └── system.py
```

本批只落地 `health.py`（`docs/02` §16 / §41 / §94 的三个健康入口：
`GET /livez` / `GET /readyz` / `GET /health`）。`api.py` 与 `management/**`
属**后续批次**，本包**不**为它们导出任何占位名。

⚠️ `docs/02` §95 明确：HTTP 管理面「**不是** MCP Tool」—— 它是与 9 Tool 契约并列的
**另一条**对外面，服务于健康 / 系统管理 / Adapter / 软件实例 / Task / Logs / Metrics。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本包**允许**依赖 FastAPI（Web 框架属接口层的正当依赖），但**禁止**
`Interface → SQLAlchemy` / `Interface → Adapter` / `Interface → Filesystem`。
因此这里的三个处理器只是「HTTP 协议 → `HealthService`」的转发，不含业务逻辑、
不访问数据库、不访问 Adapter。
"""

from __future__ import annotations

from app.interfaces.http.health import (
    HEALTH_ROUTER_PREFIX,
    HEALTH_ROUTER_TAG,
    INTERFACE_STAGE,
    create_health_router,
    health_report,
    livez,
    readyz,
)

__all__ = [
    "HEALTH_ROUTER_PREFIX",
    "HEALTH_ROUTER_TAG",
    "INTERFACE_STAGE",
    "create_health_router",
    "health_report",
    "livez",
    "readyz",
]
