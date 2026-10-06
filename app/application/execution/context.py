"""Application · Execution · ExecutionContext（`docs/07` §12 P14–P18；`docs/02` §6 / §29）。

权威来源
--------
- `docs/02` §3 / §29（`exec` / `blue` §29）—— 文件 `app/application/execution/context.py`；
  `SoftwareContext` / `ProjectContext` / `ExecutionContext` 逐字段照抄（含
  `default_factory` 的默认值形态）。
- `docs/02` §3（`exec`）—— `ResourceContext(model_id, document_id)`；`ExecutionContext`
  的 `resource` 字段。
- `docs/02` §4 / §5（`exec`）—— 「ExecutionContext 构造规则」与 `ExecutionContextFactory`：
  客户端**最多**提供 `software_instance_id` / `project_id` / `model_id` / `document_id`，
  服务器负责认证并构造 `IdentityContext`。
- `docs/02` §6（`impl` §6）—— 「ExecutionContext：身份必须由服务器生成」：客户端不得
  决定 `user_id` / `tenant_id` / `roles` / `permissions`。
- `docs/07` §8.1 / §14.3 —— 客户端可提供 `project_id` / `software_instance_id`；
  **客户端不可提供** `user_id` / `tenant_id` / `roles` / `permissions` / `session_id`；
  客户端提供的 `context.identity` **必须被忽略 / 拒绝**，不得覆盖。
- `docs/07` §9 —— 流水线第 3–4 步（`Build Server IdentityContext` → `Build ExecutionContext`）。

落地裁决（只补实现手段，不改字段名 / 类型 / 语义）
--------------------------------------------------
1. **客户端 context 白名单过滤**：`docs/02` §4 只列出 4 个客户端可提供的键。
   `ExecutionContextFactory.from_client_context()` 因此**只**读
   `CLIENT_PROVIDABLE_RESOURCE_FIELDS`，其余键（尤其 `identity` / `user_id` /
   `tenant_id` / `roles` / `permissions` / `session_id`）**一律丢弃**，
   连「读进来再比对」都不做 —— 这是 `docs/07` §8.1「必须被忽略」的最强形式：
   被忽略的输入无法影响任何分支。`ignored_client_identity_fields()` 提供可审计证据。
2. **非法 UUID → `STRUCTAI-1000`**：`docs/02` §5 直接写 `UUID(software_instance_id)`，
   客户端传非 UUID 字符串会抛裸 `ValueError`。本项目唯一的对外错误契约是 20 码
   （`docs/07` §11），其中「请求格式非法」= `STRUCTAI-1000 ProtocolError`，
   故此处把 `ValueError` 转成 `ProtocolError`（**不**新增错误码）。
3. **身份参数必填且不可由 context 覆盖**：`create()` 的第一个位置参数是**服务端**的
   `IdentityContext`（`docs/02` §5 原文签名），`ExecutionContext.identity` 只来自它。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain` / `app.application.security`（**同层**的
`IdentityContext` 定义处，`docs/02` §26）：**不**引用 SQLAlchemy / FastAPI / MCP SDK /
httpx，**不**依赖 `app.infrastructure`，也**不**出现任何厂商专属 endpoint / 参数 / 响应。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final
from uuid import UUID, uuid4

from app.application.security.context import IdentityContext
from app.domain.errors import ProtocolError

__all__ = [
    "CLIENT_CONTROLLED_IDENTITY_FIELDS",
    "CLIENT_PROVIDABLE_RESOURCE_FIELDS",
    "ExecutionContext",
    "ExecutionContextFactory",
    "ProjectContext",
    "ResourceContext",
    "SoftwareContext",
    "ignored_client_identity_fields",
]

CLIENT_PROVIDABLE_RESOURCE_FIELDS: Final[tuple[str, ...]] = (
    "software_instance_id",
    "project_id",
    "model_id",
    "document_id",
)
"""客户端**允许**提供的资源标识（`docs/02` §4；`docs/07` §8.1）。

其余任何键都不参与构造 —— 见 `from_client_context()`。
"""

CLIENT_CONTROLLED_IDENTITY_FIELDS: Final[tuple[str, ...]] = (
    "identity",
    "user_id",
    "tenant_id",
    "roles",
    "permissions",
    "session_id",
)
"""客户端**绝对不可**提供的身份字段（`docs/07` §8.1 / §14.3）。

列出来是为了给出可审计的「已忽略」证据（`ignored_client_identity_fields()`），
**不是**为了「先读取再拒绝」—— 实现里这些键连读都不读。
"""


@dataclass(frozen=True, slots=True)
class SoftwareContext:
    """软件实例上下文（`docs/02` §3 / §29）。

    `instance_id` 是客户端可提供的资源标识（`docs/07` §8.1），其**归属**必须由
    `ResourceResolver` 在租户边界内解析（`docs/02` §12）；
    `product` / `version` 由解析结果回填，客户端不得直接声明。
    """

    instance_id: UUID | None = None
    product: str | None = None
    version: str | None = None


@dataclass(frozen=True, slots=True)
class ProjectContext:
    """项目上下文（`docs/02` §3 / §29）。`project_id` 是客户端可提供的资源标识。"""

    project_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ResourceContext:
    """模型 / 文档上下文（`docs/02` §3）。

    `model_id` / `document_id` 是客户端可提供的资源标识；两者的租户归属经
    `project_id` 传递（`docs/02` §11 / §22）。
    """

    model_id: UUID | None = None
    document_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """一次执行的上下文（`docs/02` §3 / §29；`docs/07` §4.2）。

    🔴 **只能由 Core 构造**：`identity` 必须来自服务端认证链
    （`AuthenticationService` / `SessionService`），客户端提供的 `context.identity`
    及其同名字段一律忽略（`docs/07` §8.1 / §14.3）。本类型不可变（`frozen=True`），
    下游服务无法就地提权。

    Attributes:
        request_id: 服务端生成的请求标识（`docs/02` §5）。
        trace_id: 服务端生成的链路标识（`docs/02` §5）。
        identity: 服务端身份上下文（`docs/02` §26）。
        software: 软件实例上下文；默认空（`docs/02` §3 的 `default_factory`）。
        project: 项目上下文；默认空。
        resource: 模型 / 文档上下文；默认空。
    """

    request_id: str
    trace_id: str
    identity: IdentityContext
    software: SoftwareContext = field(default_factory=SoftwareContext)
    project: ProjectContext = field(default_factory=ProjectContext)
    resource: ResourceContext = field(default_factory=ResourceContext)


def ignored_client_identity_fields(client_context: Mapping[str, Any] | None) -> tuple[str, ...]:
    """客户端 context 里**被忽略**的身份字段（`docs/07` §8.1 / §14.3 的审计证据）。

    Args:
        client_context: 客户端提交的 context 映射（可为 `None`）。

    Returns:
        按 `CLIENT_CONTROLLED_IDENTITY_FIELDS` 顺序列出的命中键。命中说明客户端
        尝试声明身份 —— 这些键**不会**进入 `ExecutionContext`（见模块裁决 1）。
    """
    if not client_context:
        return ()
    return tuple(name for name in CLIENT_CONTROLLED_IDENTITY_FIELDS if name in client_context)


class ExecutionContextFactory:
    """服务端 ExecutionContext 工厂（`docs/02` §5）。

    ⚠️ 本类**不**做认证：`identity` 必须由调用方（认证 / 会话链）传入
    （`docs/02` §5 原文签名；`docs/07` §8.1）。
    """

    def create(
        self,
        identity: IdentityContext,
        *,
        software_instance_id: str | None = None,
        project_id: str | None = None,
        model_id: str | None = None,
        document_id: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> ExecutionContext:
        """构造执行上下文（`docs/02` §5 原文签名与默认值）。

        Args:
            identity: **服务端**身份上下文（`docs/02` §26）；必填。
            software_instance_id: 客户端可提供的实例标识（`docs/02` §4）。
            project_id: 客户端可提供的项目标识。
            model_id: 客户端可提供的模型标识。
            document_id: 客户端可提供的文档标识。
            request_id: 服务端请求标识；缺省时生成 `req_<hex>`（`docs/02` §5）。
            trace_id: 服务端链路标识；缺省时生成 `trace_<hex>`（`docs/02` §5）。

        Returns:
            不可变的 `ExecutionContext`。

        Raises:
            ProtocolError: `STRUCTAI-1000`，任一标识不是合法 UUID（见模块裁决 2）。
        """
        return ExecutionContext(
            request_id=request_id or f"req_{uuid4().hex}",
            trace_id=trace_id or f"trace_{uuid4().hex}",
            identity=identity,
            software=SoftwareContext(instance_id=_optional_uuid(software_instance_id)),
            project=ProjectContext(project_id=_optional_uuid(project_id)),
            resource=ResourceContext(
                model_id=_optional_uuid(model_id),
                document_id=_optional_uuid(document_id),
            ),
        )

    def from_client_context(
        self,
        identity: IdentityContext,
        client_context: Mapping[str, Any] | None,
        *,
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> ExecutionContext:
        """由客户端 context **白名单**构造执行上下文（`docs/02` §4；`docs/07` §8.1）。

        只读取 `CLIENT_PROVIDABLE_RESOURCE_FIELDS`；`identity` / `user_id` /
        `tenant_id` / `roles` / `permissions` / `session_id` 等键**一律忽略**
        （连读取都不发生，见模块裁决 1）。

        Args:
            identity: **服务端**身份上下文；客户端提供的同名字段不参与构造。
            client_context: 客户端提交的 context（可为 `None` / 空）。
            request_id: 服务端请求标识；缺省时生成。
            trace_id: 服务端链路标识；缺省时生成。

        Returns:
            不可变的 `ExecutionContext`；资源标识为 `None` 时对应 context 为空。

        Raises:
            ProtocolError: `STRUCTAI-1000`，白名单字段不是合法 UUID。
        """
        provided = client_context or {}
        return self.create(
            identity,
            software_instance_id=_as_optional_str(provided.get("software_instance_id")),
            project_id=_as_optional_str(provided.get("project_id")),
            model_id=_as_optional_str(provided.get("model_id")),
            document_id=_as_optional_str(provided.get("document_id")),
            request_id=request_id,
            trace_id=trace_id,
        )


def _as_optional_str(value: Any) -> str | None:
    """把客户端提供的值规整成 `str | None`（非字符串按 `str()` 规整，空值按 `None`）。

    ⚠️ 只作用于**白名单**字段（见模块裁决 1）；身份字段根本不经过本函数。
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Iterable) and not isinstance(value, Mapping):
        # 序列 / 集合不是合法标识；交由 `_optional_uuid` 报 `STRUCTAI-1000`。
        return str(value)
    return str(value)


def _optional_uuid(value: str | None) -> UUID | None:
    """把可选字符串解析为 UUID（`docs/02` §5）。

    Raises:
        ProtocolError: `STRUCTAI-1000`，非空但不是合法 UUID（见模块裁决 2）。
            错误 `details` 只回显**被拒字段值本身**（资源标识，非 secret）。
    """
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as error:
        raise ProtocolError(
            "resource identifier is not a valid UUID",
            details={"value": str(value), "stage": "context"},
        ) from error
