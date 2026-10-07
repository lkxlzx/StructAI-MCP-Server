"""Interface · MCP · Transport · Streamable HTTP · 会话与限额原语（`docs/03` §47–§59）。

本模块是 `transport/http.py` 的**内部原语**：会话绑定表、限流器、在途计数、
带大小上限的 `receive` 包装。拆出来的理由：`docs/03` §47–§59 是一整节
「HTTP 会话 / 限额 / 清理」的规则，与「ASGI 守门」是两件事，分开后各自可单测。

权威来源
--------
- `docs/03` §16（Session 超时）—— `session_idle_timeout` / `session_max_lifetime`。
- `docs/03` §22–§24（Concurrent Sessions / Per-Session Request Limit /
  Global Inflight Limit）。
- `docs/03` §47–§49（HTTP Session / Session ID 安全 / Session Binding）。
- `docs/03` §52–§55（Body Limit / Rate Limit / Timeout / Connection Limits）。
- `docs/03` §57（MCP Session Cleanup）· §59（Session Metrics）。

分层红线（`docs/07` §14.1 / §14.2）：本模块只依赖标准库，无任何框架 / 领域依赖。
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from starlette.types import Message, Receive

__all__ = [
    "RATE_WINDOW_SECONDS",
    "SESSION_METRIC_NAMES",
    "BodyReader",
    "InflightCounter",
    "RateLimiter",
    "SessionBinding",
    "SessionTable",
]

RATE_WINDOW_SECONDS: Final[float] = 60.0
"""限流窗口长度（`docs/03` §53 的「per minute」）。"""

RATE_WINDOW_MAX_KEYS: Final[int] = 4096
"""窗口表的硬上限（防内存攻击：传输保护**不得**成为新的 DoS 面）。"""

SESSION_METRIC_NAMES: Final[tuple[str, ...]] = (
    "sessions_created_total",
    "sessions_closed_total",
    "sessions_active",
    "auth_failures_total",
    "requests_total",
    "request_errors_total",
)
"""`docs/03` §59 的**六个**指标名（逐条照抄，去掉规范里的 `structai_mcp_` 前缀）。

⚠️ `sessions_active` 是**即时值**（不是累计计数器），由守门层在每次请求时刷新。
"""


@dataclass(slots=True)
class SessionBinding:
    """一次 HTTP MCP 会话的绑定记录（`docs/03` §47 / §49）。

    Attributes:
        principal: 认证主体（`tenant_id:user_id` —— 服务端已确认的事实）。
        created_at: 会话创建时刻（§16 的 `session_max_lifetime` 判定）。
        last_activity: 最后一次活动时刻（§16 的 `session_idle_timeout` 判定）。
    """

    principal: str
    created_at: float
    last_activity: float


@dataclass(slots=True)
class SessionTable:
    """HTTP MCP 会话表（`docs/03` §47 / §48 / §57）。

    只存「会话号 → 绑定记录」：协议状态由 SDK 的 Streamable HTTP 会话管理器持有，
    本表只做**身份绑定**与**过期回收**。两表以同一个 `mcp-session-id` 为键；
    本表先到期即让 SDK 返回 `404`（`docs/03` §49 的「如同该会话不存在」）。
    """

    idle_timeout_seconds: int
    max_lifetime_seconds: int
    bindings: dict[str, SessionBinding] = field(default_factory=dict)

    def expired(self, now: float) -> tuple[str, ...]:
        """已过期的会话号（空闲超时 ∪ 最长存活；`docs/03` §16）。"""
        return tuple(
            session_id
            for session_id, binding in self.bindings.items()
            if self.is_expired(binding, now)
        )

    def is_expired(self, binding: SessionBinding, now: float) -> bool:
        """该绑定是否已过期（空闲超时 ∪ 最长存活；`docs/03` §16）。

        ⚠️ 用 `max(0.0, now - ...)` 而不是裸差值：绑定的时间戳可能来自**另一个**
        时钟基准（测试注入 / 装配顺序），裸差值会把「未来时间戳」算成负数而**误判
        为未过期**，也会把「更早的基准」算成很久以前而误判为已过期。取 `>= 0`
        的差值让判定只依赖**同一时钟内的间隔**。
        """
        idle = self.idle_timeout_seconds
        lifetime = self.max_lifetime_seconds
        idle_for = max(0.0, now - binding.last_activity)
        alive_for = max(0.0, now - binding.created_at)
        return (idle > 0 and idle_for > idle) or (lifetime > 0 and alive_for > lifetime)

    def sweep(self, now: float) -> tuple[str, ...]:
        """回收过期会话并返回被回收的会话号（`docs/03` §57）。"""
        expired = self.expired(now)
        for session_id in expired:
            self.bindings.pop(session_id, None)
        return expired

    def bind(self, session_id: str, principal: str, now: float) -> bool:
        """登记一个新会话；已存在则返回 `False`（**不**覆盖既有绑定）。"""
        if session_id in self.bindings:
            return False
        self.bindings[session_id] = SessionBinding(
            principal=principal,
            created_at=now,
            last_activity=now,
        )
        return True

    def touch(self, session_id: str, now: float) -> None:
        """刷新最后活动时刻（`docs/03` §47 的 `last_activity`）。"""
        binding = self.bindings.get(session_id)
        if binding is not None:
            binding.last_activity = now

    def principal_of(self, session_id: str) -> str | None:
        """会话绑定的认证主体（`docs/03` §49；未知会话返回 `None`）。"""
        binding = self.bindings.get(session_id)
        return None if binding is None else binding.principal

    def count_for(self, principal: str) -> int:
        """该主体当前持有的会话数（`docs/03` §55 的 per-identity 限制）。"""
        return sum(1 for binding in self.bindings.values() if binding.principal == principal)

    def __len__(self) -> int:
        """当前会话数（`docs/03` §22 / §59 的 `sessions_active`）。"""
        return len(self.bindings)


@dataclass(slots=True)
class RateLimiter:
    """固定窗口限流器（`docs/03` §53：per IP / identity / tenant / session）。

    简单、无外部依赖、无后台任务：每个请求顺带清理过期窗口。
    """

    limit_per_minute: int
    clock: Callable[[], float] = time.monotonic
    windows: dict[tuple[str, str], list[float]] = field(default_factory=dict)

    def allow(self, dimension: str, key: str, now: float) -> bool:
        """该维度的一次请求是否放行（超限 → `False`）。"""
        if self.limit_per_minute <= 0:
            return True
        window = self.windows.get((dimension, key), [])
        entry = [stamp for stamp in window if stamp > now - RATE_WINDOW_SECONDS]
        if len(entry) >= self.limit_per_minute:
            self.windows[(dimension, key)] = entry
            return False
        entry.append(now)
        self.windows[(dimension, key)] = entry
        self._prune(now)
        return True

    def _prune(self, now: float) -> None:
        """窗口表超过硬上限时清理空窗口（见 `RATE_WINDOW_MAX_KEYS`）。"""
        if len(self.windows) <= RATE_WINDOW_MAX_KEYS:
            return
        cutoff = now - RATE_WINDOW_SECONDS
        for key in tuple(self.windows):
            entry = self.windows[key]
            if not entry or entry[-1] <= cutoff:
                self.windows.pop(key, None)


@dataclass(slots=True)
class InflightCounter:
    """在途请求计数（`docs/03` §23 / §24）。"""

    limit: int
    active: int = 0

    def acquire(self) -> bool:
        """尝试占用一个名额（超限 → `False`）。"""
        if self.limit > 0 and self.active >= self.limit:
            return False
        self.active += 1
        return True

    def release(self) -> None:
        """释放名额（幂等保护：不会降到 0 以下）。"""
        if self.active > 0:
            self.active -= 1


@dataclass(slots=True)
class BodyReader:
    """带大小上限的 `receive` 包装（`docs/03` §52）。

    `docs/03` §52 要求「服务器必须在 body 进入业务解析前限制 `Content-Length` /
    streaming body size」，故本包装在**下游看到第一个字节之前**就累计字节数，
    超限即截断为「已结束的空 body」并置位 `exceeded`（由守门层回 `413`）。
    """

    receive: Receive
    limit: int
    seen: int = 0
    exceeded: bool = False

    async def __call__(self) -> Message:
        """读取一条 ASGI 消息；超限时截断。"""
        message = await self.receive()
        if message.get("type") == "http.request":
            body = message.get("body", b"")
            if isinstance(body, bytes):
                self.seen += len(body)
            if self.limit > 0 and self.seen > self.limit:
                self.exceeded = True
                return {"type": "http.request", "body": b"", "more_body": False}
        return message


def client_key(scope: Mapping[str, Any]) -> str:
    """限流用的客户端标识（`docs/03` §53 的 *per IP*）。

    取 ASGI `client` 的地址；缺失时回落到 `"unknown"`（**不**伪造一个 IP）。
    """
    client = scope.get("client")
    if isinstance(client, (tuple, list)) and client:
        return str(client[0])
    return "unknown"


def header_map(scope: Mapping[str, Any]) -> dict[str, str]:
    """ASGI headers → 小写键的映射（重复 header 取**第一个**）。"""
    headers: dict[str, str] = {}
    for key, value in scope.get("headers", []):
        name = key.decode("latin-1").lower()
        if name not in headers:
            headers[name] = value.decode("latin-1")
    return headers


def header_bytes(scope: Mapping[str, Any]) -> int:
    """请求头总字节数（`docs/03` §54 的廉价保护）。"""
    return sum(len(key) + len(value) for key, value in scope.get("headers", []))


def response_header_value(headers: list[Any], name: str) -> str | None:
    """从 ASGI 响应头列表里取一个值（大小写不敏感）。"""
    target = name.encode("latin-1").lower()
    for key, value in headers:
        if bytes(key).lower() == target:
            return bytes(value).decode("latin-1")
    return None
