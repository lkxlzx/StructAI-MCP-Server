"""Interface · MCP · 错误信封（`docs/02` §58 / §71；`docs/03` §7 / §63；`docs/07` §11）。

权威来源
--------
- `docs/02` §58（`Tool Dispatcher`）—— 未知 Tool **必须**抛错：

  ```python
  tool = self.registry.get(tool_name)
  if tool is None:
      raise ProtocolError(f"Unknown tool: {tool_name}")
  ```

  即「未知工具 → 明确错误」是**规范原文**，而不是本批的补充；错误码取自
  `docs/07` §11 的既有 **20 码**（`STRUCTAI-1000` 未知 Tool / 请求格式非法）。
- `docs/03` §7 / §63 —— 对外错误信封字段 `code` / `type` / `message` / `details` /
  `retryable`；`cause` 属服务端诊断，**不得**直接暴露给客户端。
- `docs/02` §71 —— 统一响应里的 `errors` 是列表（同步 / 异步两种形状）。
- `docs/07` §14.3 —— 绝不记录 secret（password / API key / token / private key /
  confirmation token）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **错误信封 = `StructAIError.to_dict()` ＋ 键级脱敏**：字段与顺序照抄
   `docs/03` §7（`code` / `type` / `message` / `details` / `retryable`），
   只在 `details` 上做**递归键级**清洗（见裁决 2）。**不**新增 `STRUCTAI-xxxx` 码
   （`docs/07` §11 的 20 码是封闭契约），**不**回显 `cause`（`docs/03` §63）。
2. **脱敏按「键名」而不是「值」**：只丢弃键名含敏感词的条目
   （`password` / `secret` / `token` / `api_key` / `private_key` / `credential` /
   `authorization`）。理由：本项目的 `details` 里**从不**放 secret 的值，
   而按值猜测会误伤合法诊断信息（如 `reason = "missing_token"` 是**原因**，
   不是 token 本身，必须原样保留）。递归只进 `Mapping` 与 `Sequence`。
3. **未知工具 / 请求格式非法复用 `STRUCTAI-1000`**（`docs/07` §11 逐字：
   「未知 Tool / 请求格式非法」）：`message` 用规范原文的固定前缀，被拒的
   **工具名 / 原因**放在 `details` 里（工具名不是 secret，可回显；
   `details.reason` 与 `CONFIRMATION_FAILURE_REASONS` 同风格，便于机器判定）。
4. **本模块只构造信封，不做业务判断**：权限 / Schema / Capability 的判定仍在
   26 步管线（`docs/07` §9）—— 接口层**只**把已经发生的失败翻译成信封。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`（`docs/07` §11 的错误契约）：
**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖
`app.infrastructure` / `app.observability`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from app.domain.errors import ProtocolError, StructAIError

__all__ = [
    "INVALID_ARGUMENTS_MESSAGE",
    "MCP_ERROR_STAGE",
    "REDACTION_MARKER",
    "SENSITIVE_DETAIL_KEY_PARTS",
    "UNKNOWN_TOOL_MESSAGE",
    "error_envelope",
    "invalid_arguments_error",
    "INVALID_REQUEST_ID_REASON",
    "INVALID_TRACE_ID_REASON",
    "is_sensitive_key",
    "sanitize_details",
    "unknown_tool_error",
]

MCP_ERROR_STAGE: Final[str] = "mcp"
"""本层错误 `details.stage` 的固定取值。"""

UNKNOWN_TOOL_MESSAGE: Final[str] = "Unknown tool"
"""未知 Tool 的固定消息（`docs/02` §58 的原文语义；工具名放 `details`，见落地裁决 3）。"""

INVALID_ARGUMENTS_MESSAGE: Final[str] = "Invalid tool arguments"
"""请求信封非法的固定消息（`docs/07` §11 的「请求格式非法」= `STRUCTAI-1000`）。"""

REDACTION_MARKER: Final[str] = "<redacted>"
"""敏感条目的替换标记（与 `adapters/base/errors.py` 的同一记号，`docs/07` §14.3）。"""

SENSITIVE_DETAIL_KEY_PARTS: Final[tuple[str, ...]] = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "api-key",
    "private_key",
    "private-key",
    "credential",
    "authorization",
    "access_key",
)
"""敏感键名片段（命中即丢弃该条 `details`，见落地裁决 2）。"""

UNKNOWN_TOOL_REASON: Final[str] = "unknown_tool"
"""未知工具的原因取值（`docs/02` §58）。"""

MISSING_OPERATION_REASON: Final[str] = "missing_operation"
"""请求信封缺 `operation` 的原因取值（`docs/02` §54：`operation` 必填）。"""

NOT_A_MAPPING_REASON: Final[str] = "arguments_not_a_mapping"
"""请求信封不是对象的原因取值（`docs/02` §54）。"""

INVALID_REQUEST_ID_REASON: Final[str] = "invalid_request_id"
"""显式传入的 `request_id` 形态非法的原因取值（见 `context.py` 裁决 2 与 `server.py` 裁决 6）。"""

INVALID_TRACE_ID_REASON: Final[str] = "invalid_trace_id"
"""显式传入的 `trace_id` 形态非法的原因取值（同上）。"""


def is_sensitive_key(key: object) -> bool:
    """该键名是否敏感（见落地裁决 2）。"""
    text = str(key).lower()
    return any(part in text for part in SENSITIVE_DETAIL_KEY_PARTS)


def sanitize_details(details: Mapping[str, Any] | None) -> dict[str, Any]:
    """递归清洗 `details`（`docs/07` §14.3；见落地裁决 2）。

    Args:
        details: 领域异常的 `details` 映射（可为 `None`）。

    Returns:
        只含非敏感键的新字典；嵌套 `Mapping` 递归清洗，`Sequence`（非字符串）
        逐项清洗并保持 `list` 形状，敏感键的**值**替换为 `REDACTION_MARKER`。

    ⚠️ 只丢弃**键名**命中的条目；合法诊断（如 `reason = "missing_token"`）
    原样保留（见落地裁决 2）。
    """
    if not details:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in details.items():
        if is_sensitive_key(key):
            cleaned[str(key)] = REDACTION_MARKER
            continue
        cleaned[str(key)] = _sanitize_value(value)
    return cleaned


def _sanitize_value(value: Any) -> Any:
    """递归清洗一个值（`Mapping` / `Sequence`；其余原样返回）。"""
    if isinstance(value, Mapping):
        return sanitize_details({str(key): item for key, item in value.items()})
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_sanitize_value(item) for item in value]
    return value


def error_envelope(error: StructAIError) -> dict[str, Any]:
    """把领域异常翻成对外错误信封（`docs/03` §7 / §63；见落地裁决 1）。

    Args:
        error: 20 码契约内的任何 `StructAIError`。

    Returns:
        `{"code", "type", "message", "details", "retryable"}`；`details` 已经过
        键级脱敏，**不**含 `cause`（`docs/03` §63）。
    """
    return {
        "code": error.code,
        "type": error.error_type,
        "message": error.message,
        "details": sanitize_details(error.details),
        "retryable": error.retryable,
    }


def unknown_tool_error(tool_name: str) -> ProtocolError:
    """构造「未知工具」的 `STRUCTAI-1000`（`docs/02` §58；见落地裁决 3）。

    Args:
        tool_name: 被请求的工具名（**不是** secret，可回显）。

    Returns:
        `ProtocolError`（`STRUCTAI-1000`），`details = {stage, reason, tool}`。

    ⚠️ **不**静默回落（既不猜测相近的工具名，也不落到某个默认工具）——
    「未知工具」必须是一个可被客户端识别的明确错误。
    """
    return ProtocolError(
        UNKNOWN_TOOL_MESSAGE,
        details={
            "stage": MCP_ERROR_STAGE,
            "reason": UNKNOWN_TOOL_REASON,
            "tool": str(tool_name),
        },
    )


def invalid_arguments_error(reason: str) -> ProtocolError:
    """构造「请求信封非法」的 `STRUCTAI-1000`（`docs/02` §54；见落地裁决 3）。

    Args:
        reason: 原因取值（`MISSING_OPERATION_REASON` / `NOT_A_MAPPING_REASON`）。

    Returns:
        `ProtocolError`（`STRUCTAI-1000`），`details = {stage, reason}`。
    """
    return ProtocolError(
        INVALID_ARGUMENTS_MESSAGE,
        details={"stage": MCP_ERROR_STAGE, "reason": str(reason)},
    )
