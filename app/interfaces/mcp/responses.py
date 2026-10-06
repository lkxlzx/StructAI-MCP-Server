"""Interface · MCP · 统一响应信封（`docs/02` §71 / §89；`docs/07` §5.3）。

权威来源
--------
- `docs/02` §71（Unified Response）—— 同步 / 异步两种形状：

  ```json
  { "success": true, "request_id": "req_001", "trace_id": "trace_001",
    "tool": "engineering_model_query", "operation": "MODEL.NODE.QUERY",
    "execution": {"mode": "SYNC", "status": "COMPLETED"},
    "data": {}, "warnings": [], "errors": [], "metadata": {} }
  ```

  异步形状把 `execution` 换成 `{"mode": "ASYNC", "status": "QUEUED", "task_id": "…"}`、
  `data` 为 `null`。
- `docs/07` §5.3 —— 同一信封（`success` / `request_id` / `trace_id` / `tool` /
  `operation` / `execution` / `data` / `warnings` / `errors` / `metadata`）。
- 本批提示词 ③ —— 统一响应信封还须含 `pagination` / `artifacts` / `error`
  （`docs/02` §90 的规范化信封：`data` / `pagination` / `artifacts`）。
- `docs/02` §89 / §90 —— `ExecutionResult` 的规范化结果；`docs/07` §9 第 26 步
  （`MCP Response`）由本层组装。
- `docs/02` §12（Standard Trace Tree）—— `MCP → Tool → …` 的 Span 树；
  `request_id` / `trace_id` 必须能在响应里被客户端看到并用于定位。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **信封 = §71 的 10 个键 ∪ `pagination` / `artifacts` / `error`**：§71 与 `docs/07` §5.3
   给的是同一份 10 键信封；本批提示词 ③ 额外要求 `pagination` / `artifacts` / `error`。
   故 `to_dict()` 恒返回 **13** 个键（`errors` 恒为列表，`error` 为其中第一条或 `null`），
   客户端只需读一种形状（见验收测试的键集合断言）。
2. **`data` / `pagination` / `artifacts` / `warnings` 从规范化结果里**拆出**：
   `docs/02` §90 的信封把「主体数据」与「分页 / 产物 / 警告」并列，故本层把结果映射里的
   `pagination` / `artifacts` / `warnings` 三个键提到信封顶层，其余进 `data`。
   拆分是**纯搬运**：不改取值、不丢字段（`items` 留在 `data` 里，与 §89 一致）。
3. **`execution` 直接来自 `ExecutionResult`**：`mode` / `status` / `task_id` / `steps` /
   `unprovisioned_schemas` / `replayed` 逐字段照抄（`docs/02` §89 / §92；`docs/07` §16 R54 /
   R57 —— 未配备的 Schema 必须**如实**出现，`steps` 从第 5 步起）。
4. **失败也是「一个响应」**：`StructAIError` 在接口边界翻成 `success=false` ＋
   `errors=[信封]`（`docs/02` §71 的 `errors` 列表；`docs/03` §7 的字段），
   **不**抛出、**不**回落成空数据 —— 「失败」与「成功但没数据」必须可区分。
   非 `StructAIError` 的异常（编程错误）**继续上抛**，绝不伪装成业务失败。
5. **`metadata.mcp_steps` 记录 MCP 层实际完成的步骤**：第 1–4 步（`docs/07` §9）属本层，
   而 `ExecutionResult.steps` 从第 5 步起（R57）。把两者分开如实记录，客户端因此能看出
   「MCP 层做了哪 4 步、Core 管线做了哪 22 步」，而**不**去篡改 26 步冻结顺序。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 **Application** 层（`app.application.execution.service` 的
`ExecutionResult`）：**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖
`app.infrastructure` / `app.observability`，也**不**出现任何厂商专属内容。
信封里**绝不**含 confirmation token（`docs/07` §14.3）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from app.application.execution.service import ExecutionResult
from app.domain.errors import StructAIError
from app.interfaces.mcp.context import MCP_REQUEST_STEP, MCP_STEPS, MCPContext
from app.interfaces.mcp.errors import error_envelope

__all__ = [
    "ARTIFACTS_KEY",
    "ERROR_KEY",
    "PAGINATION_KEY",
    "RESPONSE_KEYS",
    "WARNINGS_KEY",
    "ToolResponse",
    "execution_envelope",
    "FAILURE_EXECUTION_ENVELOPE",
    "failure_response",
    "success_response",
]

PAGINATION_KEY: Final[str] = "pagination"
"""分页段的键名（`docs/02` §90 / §35 的信封）。"""

ARTIFACTS_KEY: Final[str] = "artifacts"
"""产物段的键名（`docs/02` §90）。"""

WARNINGS_KEY: Final[str] = "warnings"
"""警告段的键名（`docs/02` §71）。"""

ERROR_KEY: Final[str] = "error"
"""单条错误的键名（本批提示词 ③；与列表 `errors` 并存，见落地裁决 1）。"""

RESPONSE_KEYS: Final[tuple[str, ...]] = (
    "success",
    "request_id",
    "trace_id",
    "tool",
    "operation",
    "execution",
    "data",
    PAGINATION_KEY,
    ARTIFACTS_KEY,
    WARNINGS_KEY,
    "errors",
    ERROR_KEY,
    "metadata",
)
"""统一响应信封的**恰好 13** 个键（`docs/02` §71 ∪ 本批提示词 ③；见落地裁决 1）。"""

FAILED_STATUS: Final[str] = "FAILED"
"""失败响应的 `execution.status`（**不**伪造任何 `TaskStatus` 取值，见落地裁决 4）。"""

FAILURE_EXECUTION_ENVELOPE: Final[Mapping[str, Any]] = {
    "mode": None,
    "status": FAILED_STATUS,
    "task_id": None,
    "steps": [],
    "unprovisioned_schemas": [],
    "replayed": False,
}
"""失败响应的 `execution` 段（**与成功同形**，见落地裁决 1 / 4）。

键集合与 `execution_envelope()` **逐条相同**（6 个键）—— 消费方不必按成功 / 失败
分支写两套取值路径（`mode` / `status` / `task_id` / `steps` / `unprovisioned_schemas` /
`replayed`）；失败时前三个为 `None` / `FAILED` / `None`，后三个为空 / 未重放。
"""
UNKNOWN_OPERATION: Final[str] = ""
"""请求信封不可解析时的 `operation` 占位（空串 —— **不**猜一个 Operation 名）。"""


@dataclass(frozen=True, slots=True)
class ToolResponse:
    """统一响应信封（`docs/02` §71；`docs/07` §5.3）。

    Attributes:
        success: 是否成功（失败时 `errors` 必非空，见落地裁决 4）。
        request_id: 服务端请求标识（与 `MCPContext.request_id` 逐字节相同）。
        trace_id: 服务端链路标识（贯穿整条管线）。
        tool: MCP Tool 名（`docs/07` §5.1）。
        operation: 规范化 Operation 名（`docs/02` §24）；不可解析时为空串。
        execution: 执行段（`docs/02` §71 / §89；见落地裁决 3）。
        data: 主体数据；`null` 表示本次没有主体数据（如 ASYNC 首次响应）。
        pagination: 分页段（`docs/02` §90）。
        artifacts: 产物段（`docs/02` §90）。
        warnings: 警告列表（`docs/02` §71）。
        errors: 错误信封列表（`docs/03` §7；失败时非空）。
        metadata: 诊断元数据（含 MCP 层步骤与「已忽略的客户端身份字段」，见落地裁决 5）。
    """

    success: bool
    request_id: str
    trace_id: str
    tool: str
    operation: str
    execution: Mapping[str, Any] = field(default_factory=dict)
    data: Mapping[str, Any] | None = None
    pagination: Mapping[str, Any] | None = None
    artifacts: tuple[Mapping[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[Mapping[str, Any], ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def error(self) -> Mapping[str, Any] | None:
        """第一条错误（`docs/03` §7 的字段集合）；无错误时 `None`。"""
        return self.errors[0] if self.errors else None

    def to_dict(self) -> dict[str, Any]:
        """归一化响应（**恰好** `RESPONSE_KEYS` 的 13 个键，见落地裁决 1）。"""
        return {
            "success": self.success,
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "tool": self.tool,
            "operation": self.operation,
            "execution": dict(self.execution),
            "data": None if self.data is None else dict(self.data),
            PAGINATION_KEY: None if self.pagination is None else dict(self.pagination),
            ARTIFACTS_KEY: [dict(item) for item in self.artifacts],
            WARNINGS_KEY: [str(item) for item in self.warnings],
            "errors": [dict(item) for item in self.errors],
            ERROR_KEY: None if self.error is None else dict(self.error),
            "metadata": dict(self.metadata),
        }


def execution_envelope(result: ExecutionResult) -> dict[str, Any]:
    """`ExecutionResult` → 响应信封的 `execution` 段（`docs/02` §71 / §89）。

    ⚠️ `steps` 是**第 5–26 步**（`docs/07` §16 R57）；MCP 层的 4 步记在
    `metadata.mcp_steps`（见落地裁决 5），两者不混。
    """
    return {
        "mode": result.mode,
        "status": result.status,
        "task_id": result.task_id,
        "steps": list(result.steps),
        "unprovisioned_schemas": list(result.unprovisioned_schemas),
        "replayed": result.replayed,
    }


def success_response(
    *,
    tool: str,
    operation: str,
    context: MCPContext,
    result: ExecutionResult,
    metadata: Mapping[str, Any] | None = None,
) -> ToolResponse:
    """由一次成功的执行组装响应（`docs/02` §71 / §90；见落地裁决 2 / 3）。

    Args:
        tool: MCP Tool 名。
        operation: 规范化 Operation 名。
        context: MCP 上下文（提供 `request_id` / `trace_id` / 忽略字段证据）。
        result: `ExecutionService.execute_request` 的返回值。
        metadata: 额外的诊断元数据（与基础元数据合并，后者优先保留）。

    Returns:
        `success=True` 的 `ToolResponse`。
    """
    data, pagination, artifacts, warnings = split_payload(result.result)
    merged = base_metadata(context)
    if metadata:
        merged.update({str(key): value for key, value in metadata.items()})
    return ToolResponse(
        success=True,
        request_id=context.request_id,
        trace_id=context.trace_id,
        tool=tool,
        operation=operation,
        execution=execution_envelope(result),
        data=data,
        pagination=pagination,
        artifacts=artifacts,
        warnings=warnings,
        metadata=merged,
    )


def failure_response(
    *,
    tool: str,
    operation: str,
    error: StructAIError,
    context: MCPContext | None = None,
    request_id: str = "",
    trace_id: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> ToolResponse:
    """由一次失败组装响应（`docs/02` §71 的 `errors`；见落地裁决 4）。

    Args:
        tool: MCP Tool 名。
        operation: 规范化 Operation 名（不可解析时用 `UNKNOWN_OPERATION`）。
        error: 20 码契约内的领域异常。
        context: MCP 上下文；`None` 表示请求信封尚未构造成功（此时用 `request_id` /
            `trace_id` 的显式取值）。
        request_id: 显式请求标识（`context` 为 `None` 时使用）。
        trace_id: 显式链路标识（同上）。
        metadata: 额外的诊断元数据。

    Returns:
        `success=False` 的 `ToolResponse`；`errors` 恰好一条（`docs/03` §7 的字段）。
    """
    merged = base_metadata(context)
    if metadata:
        merged.update({str(key): value for key, value in metadata.items()})
    return ToolResponse(
        success=False,
        request_id=request_id if context is None else context.request_id,
        trace_id=trace_id if context is None else context.trace_id,
        tool=tool,
        operation=operation,
        execution=FAILURE_EXECUTION_ENVELOPE,
        errors=(error_envelope(error),),
        metadata=merged,
    )


def split_payload(
    result: Mapping[str, Any] | None,
) -> tuple[
    Mapping[str, Any] | None,
    Mapping[str, Any] | None,
    tuple[Mapping[str, Any], ...],
    tuple[str, ...],
]:
    """把规范化结果拆成 `data` / `pagination` / `artifacts` / `warnings`（见落地裁决 2）。

    Args:
        result: `ExecutionResult.result`（可为 `None`，如 ASYNC 首次响应）。

    Returns:
        `(data, pagination, artifacts, warnings)`；`result` 为 `None` 时 `data` 也为 `None`
        （`docs/02` §71 的异步形状：`"data": null`）。
    """
    if result is None:
        return None, None, (), ()
    payload = {str(key): value for key, value in result.items()}
    pagination = payload.pop(PAGINATION_KEY, None)
    artifacts = payload.pop(ARTIFACTS_KEY, None)
    warnings = payload.pop(WARNINGS_KEY, None)
    return (
        payload,
        pagination if isinstance(pagination, Mapping) else None,
        _as_artifact_tuple(artifacts),
        _as_warning_tuple(warnings),
    )


def base_metadata(context: MCPContext | None) -> dict[str, Any]:
    """基础诊断元数据（见落地裁决 5）。

    `mcp_steps` = MCP 层**实际完成**的步骤名；请求信封尚未构造成功时只完成第 1 步
    （`MCP Request`）—— 如实记录，**不**谎报 4 步全跑。
    `ignored_identity_fields` = 客户端尝试声明、但被**忽略**的身份字段（可审计证据）。
    """
    if context is None:
        return {"mcp_steps": [MCP_REQUEST_STEP], "ignored_identity_fields": []}
    return {
        "mcp_steps": list(MCP_STEPS),
        "ignored_identity_fields": list(context.ignored_identity_fields),
    }


def _as_artifact_tuple(value: Any) -> tuple[Mapping[str, Any], ...]:
    """把 `artifacts` 规整成映射元组（非映射条目被丢弃 —— 不臆造产物）。"""
    if isinstance(value, Mapping) or not isinstance(value, Sequence) or isinstance(value, str):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, Mapping))


def _as_warning_tuple(value: Any) -> tuple[str, ...]:
    """把 `warnings` 规整成字符串元组。"""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value)
    return ()
