"""Interface · MCP · Transport · Streamable HTTP（`docs/03` §44–§59；`docs/02` §98 / §124）。

权威来源
--------
- `docs/03` §44（Streamable HTTP）—— 结构
  `HTTP Server → Authentication Middleware → MCP Session Middleware → MCP Protocol
  → ToolRuntime`；**禁止** `HTTP Route → Adapter`。
- `docs/03` §45 / §46（Endpoint / Methods）—— 建议 `/mcp`，**path 必须可配置**；
  `POST` / `GET` / `DELETE` 的语义「由 MCP SDK/协议版本决定」。
- `docs/03` §47–§49（HTTP Session / Session ID 安全 / Session Binding）——
  会话号必须**密码学随机**；会话必须绑定已认证身份，换身份**必须拒绝**。
- `docs/03` §50（Origin / Host）—— 显式允许列表；**禁止**默认 `allow all`。
- `docs/03` §51（CORS）—— 不需要浏览器直连时**禁用**；需要时只列显式 origin；
  **禁止** `*` 与凭证认证同用。
- `docs/03` §52–§56（Body Limit / Rate Limit / Timeout / Connection Limits /
  Backpressure）—— body 在**进入业务解析前**限制；传输层限流是**传输保护**，
  与 Core Quota 的**业务保护**不得混淆。
- `docs/03` §57–§59（Session Cleanup / Audit / Metrics）。
- `docs/07` §8.1 —— **HTTP 必须鉴权**；身份仍由**服务端**构造。
- `docs/07` §12 P41 / `docs/02` §124 —— 「加入 Streamable HTTP，**不**复制业务逻辑」。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **协议层与会话表由 SDK 承担**：`docs/03` §46 逐字要求「具体是否启用以及各方法的
   语义由 MCP SDK/协议版本决定，不要在 Core 中写死」。故本模块用 SDK 的
   `Server.streamable_http_app()`（自带 `POST` / `GET` / `DELETE`、会话表、空闲回收、
   `max_sessions`、`413` body 限制、`Origin` / `Host` 校验），**不**重写协议层。
2. **鉴权 / 会话绑定 / 限额 / 限流 / 超时在 SDK 应用外面包一层**：SDK 只在配置了
   OAuth `TokenVerifier` 时才绑定身份；本项目的凭据是 **P10–P13 的会话 Token**，
   故绑定由本模块的 `MCPHTTPMiddleware` 完成（§47–§49 的**语义**不变）。
3. **会话绑定判据是「认证主体」而非 Token 明文**（`docs/03` §49）：取
   `tenant_id:user_id`，故同一身份轮换 Token 不误判、换身份一定被拒。
4. **`Origin` / `Host` 走 SDK 的 `TransportSecuritySettings` 且**总是**传入允许列表**
   （`docs/03` §50）：本地默认 `127.0.0.1` / `localhost` / `[::1]` ＋ 配置 host，
   因此 DNS rebinding 保护**始终开启**，不存在 `allow all` 默认值。
5. **CORS 默认关闭**（`docs/03` §51）：本模块**不**默认挂 CORS；需要时由装配方给出
   显式 origin 列表，且显式拒绝 `*`（那会与凭证认证组合成漏洞）。
6. **`413` / `429` / `503` / `504` 都是**传输层**判定**（§52–§56）：**不**新增
   `STRUCTAI-xxxx` 码（20 码契约封闭），也**不**进 Core 管线；业务级限流仍归
   Core Quota（§53 逐字区分）。
7. **`STRUCTAI-5000` 的 backpressure 归 Core**（§56）：那是 Core Quota / TaskQueue
   的行为（P29–P36 已落地），本层**不**复制；本层只保证**不**无限接受（见裁决 6）。
8. **超时只包**请求-响应**型调用**（§54）：`GET` 上的 SSE 长连接不套请求超时
   （那会把合法的长流切断），其空闲回收由 SDK 的 `session_idle_timeout` 负责
   （`docs/03` §16 / §57）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库、`fastapi` / `starlette` / `mcp`（都在 `docs/07` §3.1 冻结清单内）
import time
与同包：**不**引用 SQLAlchemy / `app.infrastructure` / `app.observability`；
**不**出现任何 Operation 名、**不**判断权限 / Schema / Capability，
也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.application.execution.identity import MCPAuthenticator, MCPIdentity
from app.domain.errors import StructAIError
from app.interfaces.mcp.server import MCPServer
from app.interfaces.mcp.tools import TOOL_NAMES
from app.interfaces.mcp.transport.base import (
    HTTP_IDENTITY_STATE_KEY,
    MCPRuntimeLimits,
    ServerFactory,
    build_protocol_server,
)
from app.interfaces.mcp.transport.http_session import (
    SESSION_METRIC_NAMES,
    BodyReader,
    InflightCounter,
    RateLimiter,
    SessionTable,
    client_key,
    header_bytes,
    header_map,
    response_header_value,
)

__all__ = [
    "DEFAULT_HTTP_PATH",
    "HTTP_STAGE",
    "LOCAL_ALLOWED_HOSTS",
    "MCP_SESSION_ID_HEADER",
    "MCPHTTPMiddleware",
    "StreamableHTTPTransport",
    "build_http_app",
    "build_transport_security",
]

HTTP_STAGE: Final[str] = "mcp_http"
"""本模块的诊断 `stage` 取值（`docs/07` §11）。"""

DEFAULT_HTTP_PATH: Final[str] = "/mcp"
"""默认 MCP endpoint（`docs/03` §45 建议 `/mcp`；path 必须可配置）。"""

MCP_SESSION_ID_HEADER: Final[str] = "mcp-session-id"
"""MCP 会话号 header（MCP Streamable HTTP 规范；`docs/03` §47 / §48）。"""

LOCAL_ALLOWED_HOSTS: Final[tuple[str, ...]] = ("127.0.0.1", "localhost", "[::1]")
"""本地默认允许列表（`docs/03` §50 逐字：`localhost` / `127.0.0.1` / configured host）。"""

_MAX_HEADER_BYTES: Final[int] = 65_536
"""请求头总量上限（`docs/03` §54 的廉价保护）。"""

_AUTHORIZATION: Final[str] = "authorization"
_BEARER_PREFIX: Final[str] = "bearer "

logger = logging.getLogger("structai")


def build_transport_security(
    host: str,
    *,
    extra_hosts: Iterable[str] = (),
) -> TransportSecuritySettings:
    """构造显式的 `Origin` / `Host` 允许列表（`docs/03` §50；见落地裁决 4）。

    Args:
        host: 配置的绑定主机（`Settings.host`）。
        extra_hosts: 额外的允许主机（如浏览器直连时的显式来源）。

    Returns:
        已启用 DNS rebinding 保护的设置；允许列表**永远**非空（见落地裁决 4）。
    """
    hosts = tuple(dict.fromkeys((*LOCAL_ALLOWED_HOSTS, host, *extra_hosts)))
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[f"{item}:*" for item in hosts] + list(hosts),
        allowed_origins=[f"http://{item}:*" for item in hosts]
        + [f"https://{item}:*" for item in hosts],
    )


@dataclass(slots=True)
class _SessionRecorder:
    """转发 ASGI 响应，并从 `http.response.start` 里读出会话号（`docs/03` §47 / §49）。"""

    send: Send
    sessions: SessionTable
    metrics: dict[str, int]
    principal: str
    now: float

    async def __call__(self, message: Message) -> None:
        """转发一条消息；首见会话号即登记绑定（`docs/03` §58 的 `SESSION.CREATED`）。"""
        if message.get("type") == "http.response.start":
            raw = message.get("headers", [])
            session_id = response_header_value(list(raw), MCP_SESSION_ID_HEADER)
            if session_id and self.sessions.bind(session_id, self.principal, self.now):
                self.metrics["sessions_created_total"] += 1
                self.metrics["sessions_active"] = len(self.sessions)
                logger.info("MCP session created (stage=%s)", HTTP_STAGE)
        await self.send(message)


@dataclass(slots=True)
class MCPHTTPMiddleware:
    """Streamable HTTP 的鉴权 / 会话绑定 / 限额 / 限流 / 超时（`docs/03` §47–§56）。

    ⚠️ 本中间件**只**做通信层守门（见落地裁决 2 / 6）：**不**判断权限、**不**看
    Operation、**不**碰 Adapter —— 业务判定仍在 26 步管线（`docs/07` §9）。

    Attributes:
        app: 下游 ASGI 应用（SDK 的 Streamable HTTP 应用）。
        authenticator: 凭据 → 服务端身份的端口（`docs/03` §12）。
        limits: 运行期限制（`docs/03` §20 / §52–§55）。
    """

    app: ASGIApp
    authenticator: MCPAuthenticator
    limits: MCPRuntimeLimits = field(default_factory=MCPRuntimeLimits)
    path: str = DEFAULT_HTTP_PATH
    clock: Callable[[], float] = time.monotonic
    """单调时钟（测试可注入，便于断言会话过期 / 请求超时）。"""

    _sessions: SessionTable = field(init=False)
    _limiter: RateLimiter = field(init=False)
    _inflight: InflightCounter = field(init=False)
    _session_inflight: dict[str, int] = field(init=False, default_factory=dict)
    _metrics: dict[str, int] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        """派生会话表 / 限流器 / 计数器与指标（`docs/03` §47 / §53 / §59）。"""
        self._sessions = SessionTable(
            idle_timeout_seconds=self.limits.session_idle_timeout_seconds,
            max_lifetime_seconds=self.limits.session_max_lifetime_seconds,
        )
        self._limiter = RateLimiter(limit_per_minute=self.limits.rate_limit_per_minute)
        self._inflight = InflightCounter(limit=self.limits.max_inflight_requests)
        self._metrics = dict.fromkeys(SESSION_METRIC_NAMES, 0)

    # ===== 只读视图（供装配 / 验收断言）=====

    @property
    def session_count(self) -> int:
        """当前已绑定的会话数（`docs/03` §22 / §59 的 `sessions_active`）。"""
        return len(self._sessions)

    @property
    def metrics(self) -> Mapping[str, int]:
        """指标快照（`docs/03` §59 的六个名字）。"""
        return dict(self._metrics)

    def session_principal(self, session_id: str) -> str | None:
        """某会话绑定的认证主体（`docs/03` §49；只读用途）。"""
        return self._sessions.principal_of(session_id)

    # ===== ASGI 入口 =====

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """守门 + 转发（`docs/03` §44 的链路顺序）。"""
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        self._metrics["requests_total"] += 1
        now = self.clock()
        self._sweep(now)
        self._refresh_active()

        if _normalized_path(scope, self.path) != self.path:
            # docs/03 §45：MCP endpoint 之外的路径不属于本传输；交给下游（通常 404）。
            await self.app(scope, receive, send)
            return
        if False:
            # `docs/03` §45：MCP endpoint 之外的路径不属于本传输；交给下游（通常 404）。
            await self.app(scope, receive, send)
            return

        if header_bytes(scope) > _MAX_HEADER_BYTES:
            await _respond(send, 431, "Request header fields too large")
            return

        headers = header_map(scope)
        identity = await self._authenticate(headers, send)
        if identity is None:
            return

        principal = _principal_of(identity)
        session_id = headers.get(MCP_SESSION_ID_HEADER)
        if not await self._admit(principal, session_id, scope, now, send):
            return

        body = BodyReader(receive, self.limits.max_request_bytes)
        try:
            await self._dispatch(scope, body, send, identity, session_id, principal, now)
        except TimeoutError:
            self._metrics["request_errors_total"] += 1
            await _respond(send, 504, "MCP request timed out")
        finally:
            self._release_inflight(session_id)
        if body.exceeded:
            self._metrics["request_errors_total"] += 1
            await _respond(send, 413, "Request body too large")

    async def _dispatch(
        self,
        scope: Scope,
        body: BodyReader,
        send: Send,
        identity: MCPIdentity,
        session_id: str | None,
        principal: str,
        now: float,
    ) -> None:
        """执行一次（可能带超时的）下游调用，并记录会话绑定（`docs/03` §47 / §54）。"""
        state = scope.setdefault("state", {})
        if isinstance(state, dict):
            state[HTTP_IDENTITY_STATE_KEY] = identity
        if session_id is not None:
            self._sessions.touch(session_id, now)
        recorder = _SessionRecorder(
            send=send,
            sessions=self._sessions,
            metrics=self._metrics,
            principal=principal,
            now=now,
        )
        timeout = self.limits.request_timeout_seconds
        if timeout > 0 and _is_request_response(scope):
            async with asyncio.timeout(timeout):
                await self.app(scope, body, recorder)
        else:
            await self.app(scope, body, recorder)

    # ===== 守门步骤 =====

    async def _authenticate(self, headers: Mapping[str, str], send: Send) -> MCPIdentity | None:
        """`docs/03` §12：`HTTP Request → Authentication → IdentityContext`。

        ⚠️ 失败一律 `401` + `WWW-Authenticate`，**不**回显凭据、**不**泄露
        「用户是否存在」（`docs/02` §17）。
        """
        header = headers.get(_AUTHORIZATION, "")
        bearer = header.lower().startswith(_BEARER_PREFIX)
        token = header[len(_BEARER_PREFIX) :].strip() if bearer else ""
        if not token:
            self._metrics["auth_failures_total"] += 1
            await _unauthorized(send, "missing_token")
            return None
        try:
            return await self.authenticator.authenticate(token)
        except StructAIError:
            self._metrics["auth_failures_total"] += 1
            await _unauthorized(send, "invalid_token")
            return None

    async def _admit(
        self,
        principal: str,
        session_id: str | None,
        scope: Scope,
        now: float,
        send: Send,
    ) -> bool:
        """会话绑定 + 限额 + 限流（`docs/03` §22–§24 / §49 / §53 / §55）。

        Returns:
            放行 `True`；拒绝时返回 `False`（响应由本方法发出，`docs/03` §63）。
        """
        failure = self._binding_failure(principal, session_id)
        if failure is None:
            failure = self._limit_failure(principal, session_id)
        if failure is None and not self._allow_rate(principal, session_id, scope, now):
            failure = (429, "Rate limit exceeded")
        if failure is None and not self._inflight.acquire():
            failure = (503, "Too many in-flight requests")
        if failure is None:
            if session_id is not None:
                self._session_inflight[session_id] = self._session_inflight.get(session_id, 0) + 1
            return True
        self._metrics["request_errors_total"] += 1
        await _respond(send, failure[0], failure[1])
        return False

    def _binding_failure(self, principal: str, session_id: str | None) -> tuple[int, str] | None:
        """会话绑定判定（`docs/03` §49）：换身份的请求**必须拒绝**。"""
        if session_id is None:
            return None
        owner = self._sessions.principal_of(session_id)
        if owner is not None and owner != principal:
            logger.warning("rejecting MCP session reuse by another identity (stage=%s)", HTTP_STAGE)
            return (403, "Session belongs to another authenticated identity")
        return None

    def _limit_failure(self, principal: str, session_id: str | None) -> tuple[int, str] | None:
        """限额判定（`docs/03` §22 / §23 / §24 / §55）。"""
        if session_id is not None:
            limit = self.limits.max_requests_per_session
            if limit > 0 and self._session_inflight.get(session_id, 0) >= limit:
                return (503, "Too many requests for this session")
            return None
        per_identity = self.limits.max_connections_per_identity
        if per_identity > 0 and self._sessions.count_for(principal) >= per_identity:
            return (503, "Too many open sessions for this identity")
        sessions = self.limits.max_concurrent_sessions
        if sessions > 0 and len(self._sessions) >= sessions:
            return (503, "Too many open sessions")
        return None

    def _allow_rate(self, principal: str, session_id: str | None, scope: Scope, now: float) -> bool:
        """四个维度的限流（`docs/03` §53；见落地裁决 6）。"""
        tenant, _, _user = principal.partition(":")
        checks: list[tuple[str, str]] = [
            ("ip", client_key(scope)),
            ("identity", principal),
            ("tenant", tenant or principal),
        ]
        if session_id is not None:
            checks.append(("session", session_id))
        return all(self._limiter.allow(dimension, key, now) for dimension, key in checks)

    def _sweep(self, now: float) -> None:
        """回收过期会话（`docs/03` §57 / §58 的 `MCP.SESSION.EXPIRED`）。"""
        expired = self._sessions.sweep(now)
        if expired:
            self._metrics["sessions_closed_total"] += len(expired)
            logger.info("expired %d MCP session(s) (stage=%s)", len(expired), HTTP_STAGE)
        self._metrics["sessions_active"] = len(self._sessions)

    def _refresh_active(self) -> None:
        """刷新 `sessions_active`（`docs/03` §59 的即时值；见 `SESSION_METRIC_NAMES`）。"""
        self._metrics["sessions_active"] = len(self._sessions)

    def _release_inflight(self, session_id: str | None) -> None:
        """释放全局与（可选的）会话级在途名额（`docs/03` §23 / §24）。"""
        self._inflight.release()
        if session_id is None:
            return
        current = self._session_inflight.get(session_id, 0)
        if current <= 1:
            self._session_inflight.pop(session_id, None)
        else:
            self._session_inflight[session_id] = current - 1


@dataclass(slots=True)
class StreamableHTTPTransport:
    """Streamable HTTP 传输（`docs/03` §44–§59；`docs/02` §98 / §124）。

    ⚠️ 本类**只**负责通信（`docs/03` §2 / §60）：它不知道 `tool` / `operation` /
    `adapter` / `software` / `database`（`docs/03` §3 逐字）。

    Attributes:
        server: **P37–P39 已落地**的 `MCPServer`（9 Tool / Dispatcher 原样复用）。
        authenticator: 凭据 → 服务端身份（`docs/03` §12）。
    """

    server: MCPServer | ServerFactory
    authenticator: MCPAuthenticator
    limits: MCPRuntimeLimits = field(default_factory=MCPRuntimeLimits)
    path: str = DEFAULT_HTTP_PATH
    host: str = "127.0.0.1"
    json_response: bool = False
    _protocol: Any = field(init=False, default=None)
    _sdk_app: ASGIApp | None = field(init=False, default=None)
    _middleware: MCPHTTPMiddleware | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        """构造 SDK 的 Streamable HTTP 应用并包上守门中间件（见落地裁决 1 / 2）。"""
        self._protocol = build_protocol_server(self.server, identity=None)
        inner = self._protocol.streamable_http_app(
            streamable_http_path=self.path,
            json_response=self.json_response,
            transport_security=build_transport_security(self.host),
            max_request_body_size=self.limits.max_request_bytes,
            session_idle_timeout=float(self.limits.session_idle_timeout_seconds),
            max_sessions=self.limits.max_concurrent_sessions,
        )
        self._sdk_app: ASGIApp = inner
        self._middleware = MCPHTTPMiddleware(
            app=inner,
            authenticator=self.authenticator,
            limits=self.limits,
            path=self.path,
        )

    @property
    def asgi_app(self) -> ASGIApp:
        """**守门后**的 ASGI 应用（`docs/03` §44 的链路；已含鉴权 / 会话绑定）。"""
        assert self._middleware is not None  # noqa: S101 - `__post_init__` 已装配
        return self._middleware

    @property
    def protocol_app(self) -> ASGIApp:
        """**未守门**的 SDK Streamable HTTP 应用（协议 / 会话 / `GET` SSE 全归它）。

        ⚠️ `app()` 挂载的是**它**（再由守门中间件包在外面）：挂载 `asgi_app` 会造成
        「中间件 → 应用 → 中间件」的自我循环。
        """
        assert self._sdk_app is not None  # noqa: S101 - `__post_init__` 已装配
        return self._sdk_app

    @property
    def middleware(self) -> MCPHTTPMiddleware:
        """守门中间件（只读用途；验收断言会话绑定 / 限额用）。"""
        assert self._middleware is not None  # noqa: S101 - `__post_init__` 已装配
        return self._middleware

    @property
    def protocol_server(self) -> Any:
        """SDK 的 low-level `Server`（只读用途；协议方法由 SDK 承担）。"""
        return self._protocol

    @property
    def tool_names(self) -> tuple[str, ...]:
        """`tools/list` 会下发的工具名（`docs/03` §25；**恰好 9** 个）。

        ⚠️ 名字清单来自既有接口层：固定实例直接问它（`MCPServer.list_tools()`），
        按需装配的工厂则用 `docs/02` §123 冻结的**同一份** `TOOL_NAMES`
        （P37–P39 已逐条断言 `TOOL_NAMES` == 注册表 == 装配结果，故不会漂移）。
        """
        if callable(self.server):
            return TOOL_NAMES
        return self.server.list_tools()

    def app(self, *, cors_allow_origins: Sequence[str] = ()) -> Starlette:
        """构造可交给 ASGI 服务器的 Starlette 应用（`docs/03` §45 / §51 / §76）。

        Args:
            cors_allow_origins: 显式允许的浏览器来源；缺省**不**启用 CORS
                （`docs/03` §51；见落地裁决 5）。

        Returns:
            已挂载 MCP endpoint 的 Starlette 应用。lifespan 由 SDK 的应用承担
            （`StreamableHTTPSessionManager.run()`），因此可以直接交给 uvicorn。

        Raises:
            ValueError: `cors_allow_origins` 里出现 `*`（`docs/03` §51 逐字禁止
                与凭证认证同时使用通配来源）。
        """
        if any(origin.strip() == "*" for origin in cors_allow_origins):
            raise ValueError("CORS wildcard origin is forbidden with credential auth (docs/03 §51)")
        # ⚠️ **不**用 `Mount`：SDK 应用自带一条 `Route("/mcp")`，而 `Mount("/mcp", ...)`
        # 会把前缀剥掉（`/mcp` → `""`），于是它的 `Route` 匹配不到、Starlette 的
        # `redirect_slashes` 会回 `307 → /mcp/` —— 对 `POST tools/call` 是一次多余的
        # 往返，且客户端可能丢掉会话语义。这里**直接**把请求交给 SDK 应用（它是
        # 一个完整的 ASGI 应用），它的 `Route("/mcp")` 因此精确命中
        # （`docs/03` §45 只规定 path，未规定尾斜杠语义）。
        inner: ASGIApp = self.protocol_app
        # 2) 再用守门中间件把它包起来（`docs/03` §44 的链路顺序）
        gate = MCPHTTPMiddleware(
            app=inner,
            authenticator=self.authenticator,
            limits=self.limits,
            path=self.path,
        )
        middleware: list[Middleware] = [Middleware(_GateMiddleware, gate=gate)]
        if cors_allow_origins:
            middleware.append(
                Middleware(
                    CORSMiddleware,
                    allow_origins=[origin for origin in cors_allow_origins],
                    allow_credentials=True,
                    allow_methods=["POST", "GET", "DELETE"],
                    allow_headers=["authorization", "content-type", MCP_SESSION_ID_HEADER],
                )
            )
        # ⚠️ 用**纯 Starlette** 而不是 FastAPI：FastAPI 的 `mount("/mcp", ...)` 会把
        # `/mcp` 当**前缀**并对不带尾斜杠的请求先回 `307 → /mcp/`（`redirect_slashes`），
        # 这会把「未认证 → 401」变成一次重定向（`docs/03` §45 只规定 path，未规定
        # 尾斜杠语义）。这里把守门中间件放在**路由之前**（Starlette 的
        # `middleware=[...]` 是最外层），故 `/mcp` 与 `/mcp/` 都**当场**得到 `401`
        # （`docs/03` §12）；路由本身仍是 SDK 的 Streamable HTTP 应用。
        return Starlette(debug=False, routes=[], middleware=middleware)


def build_http_app(
    server: MCPServer | ServerFactory,
    *,
    authenticator: MCPAuthenticator,
    limits: MCPRuntimeLimits | None = None,
    path: str = DEFAULT_HTTP_PATH,
    host: str = "127.0.0.1",
    json_response: bool = False,
    cors_allow_origins: Sequence[str] = (),
) -> Starlette:
    """装配 Streamable HTTP 应用（`docs/03` §44 / §76；`docs/02` §124）。

    Args:
        server: 既有 `MCPServer`（**不**重写、**不**回退）。
        authenticator: 凭据 → 服务端身份（`docs/03` §12；`docs/07` §8.1 的硬性要求）。
        limits: 运行期限制；缺省用规范默认值。
        path: MCP endpoint（`docs/03` §45：**必须可配置**）。
        host: 绑定主机（用于 `Origin` / `Host` 允许列表，`docs/03` §50）。
        json_response: 是否用 JSON 响应替代 SSE（SDK 的开关；`docs/03` §46）。
        cors_allow_origins: 显式浏览器来源（缺省关闭 CORS，`docs/03` §51）。
    """
    transport = StreamableHTTPTransport(
        server=server,
        authenticator=authenticator,
        limits=limits or MCPRuntimeLimits(),
        path=path,
        host=host,
        json_response=json_response,
    )
    return transport.app(cors_allow_origins=cors_allow_origins)


# ===== 传输层响应辅助（**不**新增 STRUCTAI-xxxx 码；见落地裁决 6）=====


def _normalized_path(scope: Scope, endpoint: str) -> str:
    """归一化 ASGI 路径（`docs/03` §45；见 `app()` 的说明）。

    `docs/03` §45 只规定 path（`/mcp`），未规定尾斜杠语义。本层把
    `/mcp` 与 `/mcp/` 视为**同一个** endpoint（尾斜杠变体不触发重定向），
    其余路径一律交给下游（通常 404）。
    """
    raw = str(scope.get("path") or "")
    return raw.rstrip("/") or "/"


def _principal_of(identity: MCPIdentity) -> str:
    """认证主体（`docs/03` §49 的绑定判据；见落地裁决 3）。"""
    return f"{identity.identity.tenant_id}:{identity.identity.user_id}"


def _is_request_response(scope: Scope) -> bool:
    """该请求是否为「请求-响应」型（`docs/03` §54；见落地裁决 8）。

    `GET` 上是 SSE 长连接，**不**套请求超时；其余方法（`POST` / `DELETE`）是
    请求-响应型，套超时。
    """
    return str(scope.get("method", "")).upper() != "GET"


async def _respond(send: Send | None, status: int, message: str) -> None:
    """发送一个**不含**内部细节的传输层错误（`docs/03` §63；见落地裁决 6）。"""
    if send is None:
        return
    response = JSONResponse(
        {"error": {"type": "transport_error", "message": message}},
        status_code=status,
    )
    await response({"type": "http", "method": "POST", "headers": []}, _empty_receive, send)


async def _unauthorized(send: Send, reason: str) -> None:
    """`401` + `WWW-Authenticate`（`docs/03` §12；**不**回显凭据）。"""
    response = JSONResponse(
        {"error": {"type": "unauthorized", "reason": reason}},
        status_code=401,
        headers={"WWW-Authenticate": 'Bearer realm="structai-mcp"'},
    )
    await response({"type": "http", "method": "POST", "headers": []}, _empty_receive, send)


async def _empty_receive() -> Message:
    """给 `JSONResponse` 用的空 `receive`（传输层错误响应不需要请求体）。"""
    return {"type": "http.request", "body": b"", "more_body": False}


class _GateMiddleware:
    """把 `MCPHTTPMiddleware` 装进 Starlette 的 `middleware=[...]`（见 `app()` 的说明）。

    ⚠️ Starlette 的中间件必须满足 `__init__(app, **options)` 的工厂签名，而
    `MCPHTTPMiddleware` 是**数据类**（它自己就是 ASGI 应用）。这里因此只做一层
    极薄的适配：把上游 `app` 交给已经装配好身份的守门中间件。
    """

    def __init__(self, app: ASGIApp, *, gate: MCPHTTPMiddleware) -> None:
        """绑定守门中间件（`docs/03` §44 的链路）。

        ⚠️ 参数 `app` 由 Starlette 传入（它是守门中间件**自己**的上游），
        但守门中间件持有的下游才是要转发的目标，故这里只保留 `gate`。
        """
        self._gate = gate

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """转发给守门中间件（下游由守门中间件自己持有）。"""
        await self._gate(scope, receive, send)
