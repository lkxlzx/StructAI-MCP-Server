"""Infrastructure · Adapters · MIDAS · Health —— 健康检查（`docs/02` §25；`docs/04` §6）。

权威来源
--------
- `docs/02` §25 / §33（adapter）—— `health_check()` 的统一返回形状：
  `{"healthy": bool, "state": str, "version": str, "latency_ms": int}`。
- `docs/02` §52 / §53 —— 健康检查**永不**抛出；失败只暴露异常**类名**
  （一个实例挂掉不得让 Core 失去 READY，`docs/07` §14.4）。
- `docs/07` §6.2 —— `/OPE/PROJECTSTATUS` 是数据里 `verified` 的只读端点，
  适合做健康探测（零副作用）。
- `docs/07` §14.3 —— **绝不记录 secret**：健康结果里不得出现凭据。

落地裁决（只补实现手段，不改形状）
--------------------------------
1. **探测端点 = `/OPE.PROJECTSTATUS`（GET）**：它是数据里 `verified` 的只读端点
   （`registry/manifest.json`），探测零副作用；路径取自 Registry，**不**硬编码。
2. **失败只回类名**：`{"healthy": false, "state": "ERROR", "error": {"type": <类名>}}`
   （`docs/02` §52 的形状）—— 不回显原生 message，避免泄露部署细节 / 凭据。
3. **`version` 取实例声明**：MIDAS 的 REST 数据里**没有**版本端点
   （`registry/README.md` §4 无版本字段），故版本只来自连接配置 / Manifest 声明，
   探测不到即空串，**不**猜。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与同包的 `client.py` / `registry.py`；**不**引用 SQLAlchemy /
FastAPI / MCP SDK，**不**依赖 `app.interfaces`。
"""

from __future__ import annotations

import time
from typing import Any, Final

from app.infrastructure.adapters.base.adapter import AdapterState
from app.infrastructure.adapters.midas.client import MidasHttpClient

__all__ = ["HEALTH_CHECK_ENDPOINT", "HEALTH_KEYS", "MidasHealthChecker"]

HEALTH_CHECK_ENDPOINT: Final[str] = "OPE.PROJECTSTATUS"
"""健康探测端点（`docs/07` §6.2；数据里 `verified` 的只读端点）。"""

HEALTH_KEYS: Final[tuple[str, ...]] = ("healthy", "state", "version", "latency_ms")
"""`docs/02` §25 的健康结果形状（**恰好四键**）。"""


class MidasHealthChecker:
    """MIDAS 健康检查器（`docs/02` §52；见模块裁决 1）。"""

    def __init__(self, client: MidasHttpClient) -> None:
        """绑定客户端（**不**做 I/O）。"""
        self._client = client

    async def check(self, *, version: str, path: str) -> dict[str, Any]:
        """探测一次（**永不**抛出，见裁决 2）。

        Args:
            version: 实例声明的软件版本（探测不到即空串，见裁决 3）。
            path: 探测路径（由 Registry 给出，**不**硬编码）。

        Returns:
            `docs/02` §25 的四键形状。
        """
        started = time.perf_counter()
        try:
            await self._client.get(path)
        except Exception as error:
            return {
                "healthy": False,
                "state": AdapterState.ERROR.value,
                "version": str(version),
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "error": {"type": type(error).__name__},
            }
        return {
            "healthy": True,
            "state": AdapterState.READY.value,
            "version": str(version),
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
