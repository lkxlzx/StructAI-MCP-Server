"""Interface · MCP · Tool 基类与统一请求信封（`docs/02` §53 / §54 / §59 / §70 / §73）。

权威来源
--------
- `docs/02` §54 / §70 —— 统一请求信封（逐字段照抄）：

  ```python
  class ToolRequest(BaseModel):
      operation: str
      parameters: dict = {}
      context: dict = {}
      idempotency_key: str | None = None
      confirmation_token: str | None = None
      dry_run: bool = False
  ```

- `docs/02` §53 —— 每个 Tool 都是 **thin wrapper**，最终

  ```python
  return await execution_service.execute(...)
  ```

- `docs/02` §59（Tool Implementation Pattern）—— `handle()` → resolve operation →
  build ExecutionContext → `ExecutionService.execute()` → Unified Response。
- `docs/02` §73（Tool Base Class）—— `BaseEngineeringTool`：`name` ＋
  `async def handle(request, context)`；Tool **只**负责「接收请求 / 解析请求 /
  调用 Application Service / 返回统一结果」。
- `docs/07` §12 P37–P39 —— 9 个 Tool **只是 thin wrapper**；**不**把业务逻辑复制到接口层。
- `docs/07` §14.1 —— 禁止 `Interface → SQLAlchemy` / `Interface → Adapter` /
  `Interface → Filesystem`。
- `docs/07` §14.3 —— 绝不记录 secret（**含 confirmation token**）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **`ToolRequest` 是不可变 dataclass（不是 Pydantic 模型）**：`docs/02` §54 的原文是
   Pydantic 写法，但本项目把「MCP SDK / Pydantic 模型」留在传输层（P40 / P41），
   接口层的信封只需**解析 + 校验**两件事。故用 `frozen=True` 的 dataclass：
   下游无法就地改写 `operation` / `dry_run`，也不可能被提权（`docs/07` §14.3）。
   字段名与顺序与 §54 逐条一致。
2. **`confirmation_token` 声明为 `repr=False`**：它是 **secret**（`docs/07` §8.4 / §14.3），
   绝不允许经 `repr` / 日志 / 异常信息带出去。`docs/02` §54 只要求「原样透传」，
   本模块据此**只**做「原样搬运」：不校验取值、不比较、不入 `metadata` / 响应。
3. **`context` 由 MCP 层消费，Tool **不**读它**：`docs/02` §54 的 `context` 是**客户端**
   声明的资源标识，第 4 步（`MCPContextFactory`）已把它按**白名单**解析进
   `MCPContext.execution`。Tool 因此只用 `context.execution` 构造 `PipelineRequest` ——
   客户端**没有**第二条路径能影响身份或资源解析（`docs/07` §8.1）。
4. **信封格式非法 → `STRUCTAI-1000`**（`docs/07` §11 逐字含「请求格式非法」）：
   `operation` 缺失 / 非字符串、`parameters` / `context` 不是对象、
   `idempotency_key` / `confirmation_token` 不是字符串、`dry_run` 不是布尔 —— 全部拒绝。
   **不**静默强转（把 `"false"` 当真值会让 Dry Run 变成一次真实写操作）。
   未登记的键**一律忽略**（客户端多发的 `identity` / `user_id` 等因此连读都不读）。
5. **失败在 Tool 边界翻成响应信封**（`responses.failure_response`）：`StructAIError`
   不向上抛（MCP 的「一个请求 → 一个结果」要求如此），而**非** `StructAIError`
   （编程错误）继续上抛 —— 绝不把 Bug 伪装成业务失败（`docs/03` §63）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 **Application** 层（`app.application.execution`）＋ 同包：
**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖 `app.infrastructure`
（仓储 / 事务 / Adapter 一律不可见），也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar, Final

from app.application.execution.pipeline import PipelineRequest
from app.application.execution.service import ExecutionService
from app.domain.errors import StructAIError
from app.interfaces.mcp.context import MCPContext
from app.interfaces.mcp.errors import NOT_A_MAPPING_REASON, invalid_arguments_error
from app.interfaces.mcp.responses import ToolResponse, failure_response, success_response

__all__ = [
    "CONTEXT_NOT_A_MAPPING_REASON",
    "INVALID_CONFIRMATION_TOKEN_REASON",
    "INVALID_DRY_RUN_REASON",
    "INVALID_IDEMPOTENCY_KEY_REASON",
    "MISSING_OPERATION_REASON",
    "PARAMETERS_NOT_A_MAPPING_REASON",
    "TOOL_REQUEST_FIELDS",
    "TOOL_STAGE",
    "BaseEngineeringTool",
    "ToolRequest",
]

TOOL_STAGE: Final[str] = "mcp_tool"
"""本层错误 `details.stage` 的固定取值。"""

TOOL_REQUEST_FIELDS: Final[tuple[str, ...]] = (
    "operation",
    "parameters",
    "context",
    "idempotency_key",
    "confirmation_token",
    "dry_run",
)
"""统一请求信封的**恰好 6** 个字段（`docs/02` §54 / §70 逐条；验收测试逐字段断言）。"""

MISSING_OPERATION_REASON: Final[str] = "missing_operation"
"""缺 `operation` 的原因取值（`docs/02` §54：`operation` 必填）。"""

PARAMETERS_NOT_A_MAPPING_REASON: Final[str] = "parameters_not_a_mapping"
"""`parameters` 不是对象的原因取值（`docs/02` §54 的 `dict`）。"""

CONTEXT_NOT_A_MAPPING_REASON: Final[str] = "context_not_a_mapping"
"""`context` 不是对象的原因取值（`docs/02` §54 的 `dict`）。"""

INVALID_IDEMPOTENCY_KEY_REASON: Final[str] = "invalid_idempotency_key"
"""`idempotency_key` 不是字符串的原因取值（`docs/02` §31）。"""

INVALID_CONFIRMATION_TOKEN_REASON: Final[str] = "invalid_confirmation_token"
"""`confirmation_token` 不是字符串的原因取值（`docs/07` §8.4）。"""

INVALID_DRY_RUN_REASON: Final[str] = "invalid_dry_run"
"""`dry_run` 不是布尔的原因取值（`docs/02` §92）。"""


@dataclass(frozen=True, slots=True)
class ToolRequest:
    """统一请求信封（`docs/02` §54 / §70；见落地裁决 1）。

    Attributes:
        operation: 规范化 Operation 名（`docs/02` §24）；必填。
        parameters: 已规范化的参数（`docs/02` §89：Adapter 只接受规范化输入）。
        context: 客户端声明的资源标识（**只**允许 `docs/02` §69 的 4 个白名单键；
            身份字段一律忽略）—— 由 MCP 层消费，Tool 不读（见落地裁决 3）。
        idempotency_key: 可选幂等键（`docs/02` §31）。
        confirmation_token: 可选确认令牌（`docs/07` §8.4）；**原样透传**，
            绝不进日志 / 审计 / 响应（`repr=False`，见落地裁决 2）。
        dry_run: Dry Run 标志（`docs/02` §92）；`True` 时只走 Dry Run、不落库不执行。
    """

    operation: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    context: Mapping[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    confirmation_token: str | None = field(default=None, repr=False)
    dry_run: bool = False

    @classmethod
    def from_mapping(cls, arguments: Mapping[str, Any] | None) -> ToolRequest:
        """由客户端参数构造请求信封（`docs/02` §54；见落地裁决 4）。

        Args:
            arguments: MCP 调用的 `arguments`（可为 `None`，等价于空对象）。

        Returns:
            不可变的 `ToolRequest`；未登记的键被忽略（含 `identity` / `user_id` /
            `tenant_id` / `roles` / `permissions` / `session_id`）。

        Raises:
            ProtocolError: `STRUCTAI-1000` —— 信封非法（缺 `operation`、类型不符等）。
                错误 `details = {stage, reason}`，**不**回显任何取值（可能含 secret）。
        """
        if arguments is None:
            raise invalid_arguments_error(MISSING_OPERATION_REASON)
        if not isinstance(arguments, Mapping):
            raise invalid_arguments_error(NOT_A_MAPPING_REASON)

        operation = arguments.get("operation")
        if not isinstance(operation, str) or not operation.strip():
            raise invalid_arguments_error(MISSING_OPERATION_REASON)

        parameters = arguments.get("parameters")
        if parameters is not None and not isinstance(parameters, Mapping):
            raise invalid_arguments_error(PARAMETERS_NOT_A_MAPPING_REASON)

        context = arguments.get("context")
        if context is not None and not isinstance(context, Mapping):
            raise invalid_arguments_error(CONTEXT_NOT_A_MAPPING_REASON)

        idempotency_key = arguments.get("idempotency_key")
        if idempotency_key is not None and not isinstance(idempotency_key, str):
            raise invalid_arguments_error(INVALID_IDEMPOTENCY_KEY_REASON)

        confirmation_token = arguments.get("confirmation_token")
        if confirmation_token is not None and not isinstance(confirmation_token, str):
            raise invalid_arguments_error(INVALID_CONFIRMATION_TOKEN_REASON)

        dry_run = arguments.get("dry_run", False)
        if not isinstance(dry_run, bool):
            raise invalid_arguments_error(INVALID_DRY_RUN_REASON)

        return cls(
            operation=operation,
            parameters=dict(parameters or {}),
            context=dict(context or {}),
            idempotency_key=idempotency_key,
            confirmation_token=confirmation_token or None,
            dry_run=dry_run,
        )


class BaseEngineeringTool(ABC):
    """9 个 MCP Tool 的基类（`docs/02` §73；`docs/07` §12 P37–P39）。

    ⚠️ 本类**只**做「参数 → `ExecutionService`」的搬运（`docs/02` §53 / §59）：
    **不**承载工程语义、**不**重复 26 步管线中的任何一步、**不**碰仓储 / 事务 / Adapter。
    权限 / Schema / Engineering / Capability / Confirmation / Idempotency 的判定
    全部仍在管线内（`docs/07` §9）。

    Attributes:
        name: MCP Tool 名（`docs/07` §5.1；必须与 `OperationDefinition.tool` 一致，
            否则管线第 5 步按 `docs/02` §82 拒绝）。
    """

    name: ClassVar[str] = ""

    def __init__(self, execution: ExecutionService) -> None:
        """绑定会话级执行服务（`docs/02` §53；由装配方注入，**不**自建）。"""
        self._execution = execution

    @property
    def execution(self) -> ExecutionService:
        """被绑定的执行服务（只读用途；验收测试据此断言「只依赖这一条契约」）。"""
        return self._execution

    @abstractmethod
    async def handle(self, request: ToolRequest, context: MCPContext) -> ToolResponse:
        """处理一次调用（`docs/02` §73 的原文签名）。

        Args:
            request: 统一请求信封（`docs/02` §54）。
            context: **服务端** MCP 上下文（`docs/02` §57；身份不可由客户端覆盖）。

        Returns:
            统一响应信封（`docs/02` §71）。
        """

    def pipeline_request(self, request: ToolRequest, context: MCPContext) -> PipelineRequest:
        """把请求信封转成管线请求（`docs/02` §27 / §33；见落地裁决 3）。

        `tool` 取自 `self.name`（**不**取客户端输入），`context` 取自
        `context.execution`（第 4 步的产物）—— 客户端因此无法声明身份或工具。
        `confirmation_token` **原样透传**（`docs/02` §54；见落地裁决 2）。
        """
        return PipelineRequest(
            tool=self.name,
            operation=request.operation,
            parameters=dict(request.parameters),
            context=context.execution,
            idempotency_key=request.idempotency_key,
            confirmation_token=request.confirmation_token,
            dry_run=request.dry_run,
        )

    async def invoke(self, request: ToolRequest, context: MCPContext) -> ToolResponse:
        """执行一次请求并组装响应（`docs/02` §53 的 thin wrapper 本体）。

        Args:
            request: 统一请求信封。
            context: 服务端 MCP 上下文。

        Returns:
            统一响应信封（成功 / 失败都是「一个响应」，见落地裁决 5）。

        Raises:
            Exception: **非** `StructAIError` 的异常（编程错误）原样上抛。
        """
        try:
            result = await self._execution.execute_request(self.pipeline_request(request, context))
        except StructAIError as error:
            return failure_response(
                tool=self.name,
                operation=request.operation,
                error=error,
                context=context,
            )
        return success_response(
            tool=self.name,
            operation=request.operation,
            context=context,
            result=result,
        )
