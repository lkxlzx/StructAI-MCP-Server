"""Infrastructure · Adapters · CSI ETABS · Health —— 健康检查（`docs/02` §25 / §52）。

权威来源
--------
- `docs/02` §25 / §33（adapter）—— `health_check()` 的统一返回形状：
  `{"healthy": bool, "state": str, "version": str, "latency_ms": int}`。
- `docs/02` §52 / §53 —— 健康检查**永不**抛出；失败只暴露异常**类名**
  （一个实例挂掉不得让 Core 失去 READY，`docs/07` §14.4）。
- `docs/07` §14.3 —— **绝不记录 secret**：健康结果里不得出现凭据。

落地裁决（只补实现手段，不改形状）
--------------------------------
1. **探针 = COM 会话可用性**（`ComSession.is_attached()`）：这是**生命周期**层面的探测，
   零副作用，且**不**需要任何厂商方法名（本仓库没有可追溯的健康端点）。
2. **失败只回类名**：`{"healthy": false, "state": "ERROR", "error": {"type": <类名>}}`
   （`docs/02` §52 的形状）—— 不回显原生 message，避免泄露部署细节 / 凭据。
3. **`version` 取实例声明**：本仓库**没有**任何 ETABS 版本查询方法的事实依据，
   故版本只来自连接配置 / Manifest 声明，探测不到即空串，**不**猜。

分层红线：只依赖标准库与同包的 `lifecycle.py`。
"""

from __future__ import annotations

import time
from typing import Any, Final

from app.infrastructure.adapters.base.adapter import AdapterState
from app.infrastructure.adapters.etabs.lifecycle import ComSession

__all__ = ["HEALTH_KEYS", "EtabsHealthChecker"]

HEALTH_KEYS: Final[tuple[str, ...]] = ("healthy", "state", "version", "latency_ms")
"""`docs/02` §25 的健康结果形状（**恰好四键**）。"""


class EtabsHealthChecker:
    """COM 会话健康检查器（`docs/02` §52；见裁决 1）。"""

    def __init__(self, session: ComSession, *, version: str) -> None:
        """绑定会话与实例声明的版本（**不**做 I/O）。"""
        self._session = session
        self._version = str(version)

    async def check(self) -> dict[str, Any]:
        """探测一次（**永不**抛出，见裁决 2）。

        Returns:
            `docs/02` §25 的四键形状；失败时额外带 `error = {"type": <类名>}`。
        """
        started = time.perf_counter()
        try:
            attached = await self._session.is_attached()
        except Exception as error:  # pragma: no cover - `is_attached()` 已吞异常
            return {
                "healthy": False,
                "state": AdapterState.ERROR.value,
                "version": self._version,
                "latency_ms": _elapsed_ms(started),
                "error": {"type": type(error).__name__},
            }
        return {
            "healthy": bool(attached),
            "state": AdapterState.READY.value if attached else AdapterState.ERROR.value,
            "version": self._version,
            "latency_ms": _elapsed_ms(started),
        }


def _elapsed_ms(started: float) -> int:
    """自 `started` 起的毫秒数（`docs/02` §25 的 `latency_ms`）。"""
    return int((time.perf_counter() - started) * 1000)
