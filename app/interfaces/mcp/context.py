"""Interface · MCP · MCPContext（`docs/02` §54 / §57 / §69；`docs/07` §9 第 1–4 步）。

权威来源
--------
- `docs/02` §57 —— `MCPContext(request_id, trace_id, identity)`（逐字段照抄；本模块在其上
  补足 §69 要求的会话 / 权限与第 4 步的 `ExecutionContext`，见落地裁决 1）。
- `docs/02` §69 —— MCP Context 负责：MCP Session / Request ID / Trace ID /
  Authentication Context / Execution Context；客户端**可以**提供
  `software_instance_id` / `project_id` / `model_id` / `document_id`，
  **不能**提供并覆盖 `user_id` / `tenant_id` / `roles` / `effective_permissions`。
- `docs/02` §54 —— 「`context.identity` 不得由客户端覆盖」。
- `docs/02` §42 —— `SecurityContext(identity, permissions)`：认证 + 有效权限的合并视图。
- `docs/07` §9 —— 第 1–4 步（`MCP Request` / `Authenticate` /
  `Build Server IdentityContext` / `Build ExecutionContext`）是 **P37–P39** 的落点；
  `ExecutionResult.steps` 因此从第 **5** 步起（`docs/07` §16 R57）。
- `docs/07` §8.1 / §14.3 —— 身份必须由服务器生成；禁止客户端声明身份。
- `app/application/execution/context.py`（P14–P18）—— `ExecutionContext` 与
  `ExecutionContextFactory` 的**唯一**构造口径：客户端 context 走**白名单**
  （`CLIENT_PROVIDABLE_RESOURCE_FIELDS`），身份字段连读都不读。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **`MCPContext` = §57 的三字段 ＋ §69 的会话 / 权限 ＋ 第 4 步的 `ExecutionContext`**：
   §57 只给出核心三字段，§69 又要求承载 Authentication Context 与 Execution Context。
   本模块因此把 `execution`（第 4 步的产物）与 `permissions`（有效权限快照，
   `docs/02` §29 / §42）显式带上；`session_id` / `roles` 以**只读属性**转发 `identity`
   （单一真源 —— 不复制一份可能失同步的副本）。
2. **`request_id` / `trace_id` 由 Core 生成并贯穿整条管线**：本模块**不**另造一套 id，
   而是把两个标识交给 `ExecutionContextFactory`，再**回读** `ExecutionContext` 的同名值 ——
   于是「MCP 层的 `request_id` == 管线内的 `request_id` == 审计 / Trace 的 `request_id`」
   是**结构性**的，而不是靠调用方记得逐处传参。
3. **客户端 identity 一律忽略，并给出可审计证据**：沿用 P14–P18 的
   `ignored_client_identity_fields()` 口径，命中的键记入 `MCPContext.ignored_identity_fields`
   并随统一响应信封的 `metadata` 回给调用方 ——「已忽略」因此是可核对的事实。
4. **`permissions` 缺省为空集**：未提供有效权限快照时按**空集**处理，与 `docs/02` §51
   （AI Agent 未提供权限时按空集，**不得提权**）同一口径。真正的权限判定仍在第 11 步
   （`Effective Permission`），本层**不**做任何业务判断。
5. **认证不在本模块**：`MCPContextFactory` 要求调用方传入**已认证**的
   `IdentityContext`（`docs/07` §8.1 的 `Authenticate` 步骤由传输层 / 会话链负责，
   属 P40 / P41）。本层**绝不**从客户端输入推导身份。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 **Application** 层（`app.application.execution` /
`app.application.security`）：**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，
**不**依赖 `app.infrastructure` / `app.observability`（审计 / Trace 由调用方在 Application
侧接线），也**不**出现任何厂商专属 endpoint / 参数 / 响应。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final
from uuid import uuid4

from app.application.execution.context import (
    ExecutionContext,
    ExecutionContextFactory,
    ignored_client_identity_fields,
)
from app.application.security.context import IdentityContext, SecurityContext

__all__ = [
    "MCP_AUTHENTICATE_STEP",
    "MCP_CONTEXT_STAGE",
    "MCP_EXECUTION_STEP",
    "MCP_IDENTITY_STEP",
    "MCP_REQUEST_STEP",
    "MCP_STEPS",
    "MCPContext",
    "MCPContextFactory",
    "empty_client_context",
    "new_request_id",
    "new_trace_id",
]

MCP_CONTEXT_STAGE: Final[str] = "mcp_context"
"""本模块错误 `details.stage` 的固定取值（`docs/07` §11 的诊断口径）。"""

MCP_REQUEST_STEP: Final[str] = "MCP Request"
"""第 1 步：收到 MCP 请求（`docs/07` §9）。"""

MCP_AUTHENTICATE_STEP: Final[str] = "Authenticate"
"""第 2 步：认证（`docs/07` §9；由传输层 / 会话链提供已认证身份，见落地裁决 5）。"""

MCP_IDENTITY_STEP: Final[str] = "Build Server IdentityContext"
"""第 3 步：构造**服务端**身份（`docs/07` §9；客户端同名字段一律忽略）。"""

MCP_EXECUTION_STEP: Final[str] = "Build ExecutionContext"
"""第 4 步：构造执行上下文（`docs/02` §5；`docs/07` §9）。"""

MCP_STEPS: Final[tuple[str, ...]] = (
    MCP_REQUEST_STEP,
    MCP_AUTHENTICATE_STEP,
    MCP_IDENTITY_STEP,
    MCP_EXECUTION_STEP,
)
"""MCP 层实现的**前 4 步**（`docs/07` §9 的冻结顺序）。

⚠️ 必须**逐条等于** `app.application.execution.pipeline.MCP_PIPELINE_STEPS`
（`docs/07` §16 R57）—— 本模块自带一份是接口层的**落点声明**，
验收测试逐条断言两者相等，因此不会与 26 步冻结顺序漂移。
"""


def new_request_id() -> str:
    """生成服务端 `request_id`（`docs/02` §5 / §54：`req_<hex>`）。"""
    return f"req_{uuid4().hex}"


def new_trace_id() -> str:
    """生成服务端 `trace_id`（`docs/02` §5 / §54：`trace_<hex>`）。"""
    return f"trace_{uuid4().hex}"


@dataclass(frozen=True, slots=True)
class MCPContext:
    """一次 MCP 调用的上下文（`docs/02` §57 / §69；`docs/07` §9 第 1–4 步）。

    🔴 **身份只能来自服务端**：`identity` 由认证链构造，客户端提交的
    `identity` / `user_id` / `tenant_id` / `roles` / `permissions` / `session_id`
    **一律忽略**（`docs/07` §8.1 / §14.3），忽略证据见 `ignored_identity_fields`。
    本类型不可变（`frozen=True`），下游无法就地提权。

    Attributes:
        request_id: 服务端生成的请求标识（`docs/02` §5）。
        trace_id: 服务端生成的链路标识（`docs/02` §5）。
        identity: **服务端**身份上下文（`docs/02` §26 / §57）。
        execution: 第 4 步的执行上下文（`docs/02` §5；Tool 用它构造 `PipelineRequest`）。
        permissions: 有效权限快照（`docs/02` §29 / §42）；缺省空集（见落地裁决 4）。
        ignored_identity_fields: 客户端 context 里被忽略的身份字段（可审计证据，
            见落地裁决 3）。
    """

    request_id: str
    trace_id: str
    identity: IdentityContext
    execution: ExecutionContext
    permissions: frozenset[str] = frozenset()
    ignored_identity_fields: tuple[str, ...] = ()

    @property
    def session_id(self) -> str | None:
        """MCP 会话标识（`docs/02` §69 的 `MCP Session`）—— 转发 `identity`（单一真源）。"""
        return None if self.identity.session_id is None else str(self.identity.session_id)

    @property
    def roles(self) -> tuple[str, ...]:
        """服务端装载的角色名 —— 转发 `identity`（**不是**权限，`docs/02` §26）。"""
        return self.identity.roles


class MCPContextFactory:
    """服务端 MCP 上下文工厂（`docs/02` §57 / §69；`docs/07` §9 第 1–4 步）。

    ⚠️ 本类**不**做认证：`identity` 必须由调用方（传输层 / 会话链，P40 / P41）传入
    （见落地裁决 5）。本类只做第 3–4 步：把**服务端**身份与客户端**白名单**资源标识
    合成 `ExecutionContext`，并生成贯穿整条管线的 `request_id` / `trace_id`。
    """

    def __init__(self, *, executions: ExecutionContextFactory | None = None) -> None:
        """绑定执行上下文工厂（缺省用 P14–P18 的 `ExecutionContextFactory`）。"""
        self._executions = executions or ExecutionContextFactory()

    @property
    def executions(self) -> ExecutionContextFactory:
        """被绑定的执行上下文工厂（只读用途）。"""
        return self._executions

    def create(
        self,
        identity: IdentityContext,
        *,
        client_context: Mapping[str, Any] | None = None,
        permissions: Iterable[str] = (),
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> MCPContext:
        """构造 MCP 上下文（`docs/02` §54 / §57 / §69）。

        Args:
            identity: **服务端**身份上下文（`docs/02` §26）；客户端同名字段不参与构造。
            client_context: 客户端提交的 `context`（`docs/02` §54 的请求信封字段）；
                **只**读取 4 个白名单资源标识（`docs/02` §69），身份字段一律忽略。
            permissions: 服务端计算的有效权限快照（`docs/02` §42）；缺省空集。
            request_id: 服务端请求标识；缺省生成 `req_<hex>`（`docs/02` §5）。
            trace_id: 服务端链路标识；缺省生成 `trace_<hex>`（`docs/02` §5）。

        Returns:
            不可变的 `MCPContext`；`request_id` / `trace_id` 与 `execution` 内的同名值
            **逐字节相同**（见落地裁决 2）。

        Raises:
            ProtocolError: `STRUCTAI-1000` —— 白名单字段不是合法 UUID
                （`ExecutionContextFactory` 的既有口径，本层不另立码）。
        """
        execution = self._executions.from_client_context(
            identity,
            client_context,
            request_id=request_id,
            trace_id=trace_id,
        )
        return MCPContext(
            request_id=execution.request_id,
            trace_id=execution.trace_id,
            identity=identity,
            execution=execution,
            permissions=frozenset(str(permission) for permission in permissions),
            ignored_identity_fields=ignored_client_identity_fields(client_context),
        )

    def from_security_context(
        self,
        security: SecurityContext,
        *,
        client_context: Mapping[str, Any] | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> MCPContext:
        """由 `SecurityContext`（认证 + 有效权限）构造 MCP 上下文（`docs/02` §42）。

        `docs/02` §40 / §41 要求执行链**只**从 `SecurityContext` 这一个入口拿身份与权限，
        故这是装配侧的推荐入口；行为与 `create()` 完全一致（权限取自 `security.permissions`）。
        """
        return self.create(
            security.identity,
            client_context=client_context,
            permissions=security.permissions,
            request_id=request_id,
            trace_id=trace_id,
        )


def empty_client_context() -> Mapping[str, Any]:
    """空客户端 context（`docs/02` §54 的 `context: dict = {}` 默认值）。


    以函数而非可变默认值提供：`MCPContextFactory.create()` 的 `client_context=None`
    与空映射**等价**（两者都只走白名单，故都不含任何身份字段）。
    """
    return {}
