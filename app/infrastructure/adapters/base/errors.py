"""Infrastructure · Adapters · Base · Errors —— 原生异常 → 20 码的**唯一**归一化点。

权威来源
--------
- `docs/02` §49（`adapter`）—— Mock 错误归一化：`MockValidationError` / `MockDuplicateError`
  → `STRUCTAI-1200`；其余 → `STRUCTAI-6000`（`message` 固定，**不**回显原生 message）。
- `docs/02` §50（`adapter`）—— Adapter Error 原则：「Core 不允许直接暴露 native exception」，
  Adapter 必须转换成 StructAI Error，统一为 `STRUCTAI-2000` / `2100` / `2200` / `2300` /
  `3000` / `6000`。
- `docs/02` §48（`adapter`）—— 无 handler → `AdapterCapabilityError`（`Unsupported operation`）。
- `docs/07` §11 —— **20 码**错误契约（本模块**不**新增码）。
- `docs/07` §9 第 19 步 / `docs/02` §33 —— Result Normalization：Adapter 只产出
  **规范化**结果，客户端不依赖任何软件原始字段。
- `docs/07` §14.3 —— **绝不记录 secret**（password / API key / token / private key）。

落地裁决（只补实现手段，不改码值 / 不改语义）
--------------------------------------------
1. **一张表、一个函数**：`normalize_error()` 是本项目**唯一**的「原生异常 → 20 码」映射点
   （`ADAPTER_NATIVE_ERROR_CODES` 是那张表）。Adapter 实现（含 `BaseAdapter`）一律
   委托它，不得各写一套 `if isinstance(...)`。
2. **原生异常不带 `STRUCTAI-xxxx` 码也不继承 `StructAIError`**：它们是 Adapter **内部**
   的失败信号（`AdapterNativeError`），码由上面的表给出。这样「哪些异常算哪一码」
   只有一处可改，也不会让原生异常被误当对外错误信封直接序列化。
3. **已经是 `StructAIError` 的原样透传**（`to_dict()`）：归一化是**幂等**的。
   这保证 Core 的 `STRUCTAI-4200` / `STRUCTAI-6100` 等既有语义**不会**被 Adapter
   重写成 `STRUCTAI-6000`（`docs/07` §16 R24 / R27 的裁决不被本批推翻）。
4. **不回显原生 message**：`message` 一律取**本模块声明的固定文案**
   （`docs/02` §50：只暴露归一化错误）。原生 message 只允许出现在服务端
   `cause`（`docs/02` §9 的 `cause` 属诊断字段，**不**进 MCP 信封）。
5. **`details` 白名单式净化**：丢弃键名含 password / passwd / secret / token /
   key / credential / authorization 的项，并对字符串值做凭据形态脱敏
   （`_redact`）—— 即使 Adapter 作者误传，也不会把 secret 带进响应（`docs/07` §14.3）。
6. **兜底 `STRUCTAI-6000`**（`docs/07` §11 的 `Adapter Error`）：`retryable` 取
   `docs/03` §124 的口径（`STRUCTAI-2000` / `STRUCTAI-2300` 可重试，其余默认 `False`）。

分层红线（`docs/07` §14.1 / §14.2 / `docs/02` §2）
------------------------------------------------
本模块只依赖标准库与 `app.domain`（**不**依赖 SQLAlchemy / FastAPI / MCP SDK / httpx，
**不**依赖 `app.interfaces`），也不出现任何厂商专属 endpoint / 参数 / 响应。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final, NoReturn

from app.domain import errors as domain_errors
from app.domain.errors import AdapterError, StructAIError

__all__ = [
    "ADAPTER_NATIVE_ERROR_CODES",
    "FALLBACK_ADAPTER_MESSAGE",
    "REDACTION_MARKER",
    "SENSITIVE_DETAIL_KEY_PARTS",
    "AdapterAPIError",
    "AdapterAuthenticationError",
    "AdapterCapabilityError",
    "AdapterConnectionError",
    "AdapterNativeError",
    "AdapterTimeoutError",
    "AdapterValidationError",
    "error_for",
    "normalize_error",
    "raise_normalized",
]

FALLBACK_ADAPTER_MESSAGE: Final[str] = "Adapter error"
"""`STRUCTAI-6000` 的固定对外文案（`docs/02` §50；**不**回显原生 message）。"""

REDACTION_MARKER: Final[str] = "<redacted>"
"""凭据脱敏后的占位符（`docs/07` §14.3）。"""

SENSITIVE_DETAIL_KEY_PARTS: Final[tuple[str, ...]] = (
    "password",
    "passwd",
    "secret",
    "token",
    "key",
    "credential",
    "authorization",
)
"""`details` 里**禁止**出现的键名片段（大小写无关；`docs/07` §14.3）。"""

_CREDENTIAL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|mapi[_-]?key|credential|authorization)\b"
    r"\s*[:=]?\s*\S*"
)
"""凭据形态文本（`name=value` / `name value`）—— 命中即整段替换为占位符。"""


# ===== 原生异常族（`docs/02` §49 / §50）=====


class AdapterNativeError(Exception):
    """Adapter 原生异常基类（`docs/02` §49 / §50）。

    这是 Adapter **内部**的失败信号：它**不**继承 `StructAIError`、也**不**携带
    `STRUCTAI-xxxx` 字面量（见模块裁决 2）。对外错误一律经 `normalize_error()`
    归一化后产生（`docs/07` §11 的 20 码）。

    Attributes:
        reason: Adapter **自己撰写**的短原因（非敏感、无厂商 endpoint、无凭据）；
            经 `_redact` 净化后才进入 `details.reason`。
        details: 附加的非敏感诊断信息；键名含敏感片段者会被丢弃。
        cause: 原始异常，仅服务端诊断（`docs/02` §9 的 `cause`）。
    """

    code: str = "STRUCTAI-6000"
    error_type: str = "ADAPTER_ERROR"
    retryable: bool = False
    default_message: str = FALLBACK_ADAPTER_MESSAGE

    def __init__(
        self,
        reason: str = "",
        *,
        details: Mapping[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        """记录原因与诊断信息（**不**做任何 I/O、**不**落日志）。"""
        super().__init__(reason)
        self.reason: str = str(reason)
        self.details: dict[str, Any] = dict(details or {})
        self.cause: Exception | None = cause


class AdapterValidationError(AdapterNativeError):
    """参数 / 模型语义非法 → `STRUCTAI-1200`（`docs/02` §49）。"""

    code = "STRUCTAI-1200"
    error_type = "ENGINEERING_VALIDATION_ERROR"
    default_message = "Engineering validation failed"


class AdapterConnectionError(AdapterNativeError):
    """连接失败 → `STRUCTAI-2000`（`docs/02` §50；可重试，`docs/03` §124）。"""

    code = "STRUCTAI-2000"
    error_type = "SOFTWARE_CONNECTION_ERROR"
    retryable = True
    default_message = "Software connection failed"


class AdapterAuthenticationError(AdapterNativeError):
    """软件侧凭据无效 → `STRUCTAI-2100`（`docs/02` §50；**不**回显凭据）。"""

    code = "STRUCTAI-2100"
    error_type = "SOFTWARE_AUTHENTICATION_ERROR"
    default_message = "Software authentication failed"


class AdapterAPIError(AdapterNativeError):
    """软件返回业务错误 → `STRUCTAI-2200`（`docs/02` §50）。"""

    code = "STRUCTAI-2200"
    error_type = "SOFTWARE_API_ERROR"
    default_message = "Software API error"


class AdapterTimeoutError(AdapterNativeError):
    """软件调用超时 → `STRUCTAI-2300`（`docs/02` §50；可重试，`docs/03` §124）。"""

    code = "STRUCTAI-2300"
    error_type = "SOFTWARE_TIMEOUT"
    retryable = True
    default_message = "Software call timed out"


class AdapterCapabilityError(AdapterNativeError):
    """实例不具备该操作的能力 → `STRUCTAI-3000`（`docs/02` §48 / §50）。"""

    code = "STRUCTAI-3000"
    error_type = "CAPABILITY_ERROR"
    default_message = "Capability not supported"


ADAPTER_NATIVE_ERROR_CODES: Final[tuple[tuple[type[AdapterNativeError], str], ...]] = (
    (AdapterConnectionError, AdapterConnectionError.code),
    (AdapterAuthenticationError, AdapterAuthenticationError.code),
    (AdapterAPIError, AdapterAPIError.code),
    (AdapterTimeoutError, AdapterTimeoutError.code),
    (AdapterCapabilityError, AdapterCapabilityError.code),
    (AdapterValidationError, AdapterValidationError.code),
)
"""原生异常族 → 20 码的**唯一**映射表（`docs/02` §49 / §50）。

兜底（不在本表内的一切异常）→ `STRUCTAI-6000`。
"""


# ===== 归一化（唯一实现点）=====


def normalize_error(error: Exception) -> dict[str, Any]:
    """把任意异常归一化成 20 码错误信封（`docs/02` §49 / §50；`docs/07` §11）。

    Args:
        error: Adapter 捕获到的异常。既可能是 `AdapterNativeError`，也可能是
            任意原生异常（`RuntimeError` / 第三方 SDK 异常……）。

    Returns:
        形状与 `StructAIError.to_dict()` 一致的错误信封
        （`code` / `type` / `message` / `details` / `retryable`）。
        `message` **永远**是固定文案 —— 原生 message 不出现在返回值里（见裁决 4）。

    Note:
        幂等：传入已是 `StructAIError` 的异常时原样返回其 `to_dict()`（见裁决 3）。
    """
    if isinstance(error, StructAIError):
        return error.to_dict()

    for error_class, code in ADAPTER_NATIVE_ERROR_CODES:
        if isinstance(error, error_class):
            # Adapter 自己给的 `details["reason"]`（机器可读码）**优先**；
            # 异常 message 只在缺省时作为 `reason` 回落（见裁决 4）。
            details: dict[str, Any] = dict(error.details)
            if error.reason:
                details.setdefault("reason", error.reason)
            return {
                "code": code,
                "type": error_class.error_type,
                "message": error_class.default_message,
                "details": _sanitize_details(details),
                "retryable": error_class.retryable,
            }

    return {
        "code": AdapterError.code,
        "type": AdapterError.error_type,
        "message": FALLBACK_ADAPTER_MESSAGE,
        "details": {},
        "retryable": AdapterError.retryable,
    }


def error_for(normalized: Mapping[str, Any]) -> StructAIError:
    """把归一化信封还原成对应的 `StructAIError` 实例（`docs/02` §50）。

    Core 侧（P36 的 `ExecutionService`）需要的是**异常**而不是 dict；
    本函数是「信封 → 领域异常」的唯一映射点，未知 / 非法码回落
    `STRUCTAI-6000`（`AdapterError`）。

    Args:
        normalized: `normalize_error()` 的产物（或等形 dict）。

    Returns:
        对应码的 `StructAIError` 派生实例；`details` 原样带入。
    """
    code = str(normalized.get("code", ""))
    error_class = _DOMAIN_ERRORS_BY_CODE.get(code, AdapterError)
    return error_class(
        str(normalized.get("message", FALLBACK_ADAPTER_MESSAGE)),
        details=dict(normalized.get("details") or {}),
    )


def raise_normalized(error: Exception) -> NoReturn:
    """归一化后抛出领域异常（`docs/02` §50；`docs/07` §9 第 18 步的出口）。

    Args:
        error: 待归一化的异常。

    Raises:
        StructAIError: 对应 20 码的领域异常；`__cause__` 为原始异常
            （服务端诊断用，`docs/02` §9 的 `cause`）。
    """
    normalized = error_for(normalize_error(error))
    raise normalized from error


# ===== 内部 =====


def _sanitize_details(details: Mapping[str, Any]) -> dict[str, Any]:
    """净化 `details`：丢敏感键、脱敏字符串值（见裁决 5）。"""
    sanitized: dict[str, Any] = {}
    for key, value in details.items():
        name = str(key)
        lowered = name.lower()
        if any(part in lowered for part in SENSITIVE_DETAIL_KEY_PARTS):
            continue
        sanitized[name] = _sanitize_value(value)
    return sanitized


def _sanitize_value(value: Any) -> Any:
    """递归净化单个值（`str` 脱敏，`dict` / `list` 逐项处理）。"""
    if isinstance(value, str):
        return _redact(value)
    if isinstance(value, Mapping):
        return _sanitize_details(value)
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return type(value).__name__


def _redact(text: str) -> str:
    """把凭据形态的文本片段替换为占位符（`docs/07` §14.3）。"""
    return _CREDENTIAL_PATTERN.sub(REDACTION_MARKER, text)


def _domain_error_index() -> dict[str, type[StructAIError]]:
    """`STRUCTAI-xxxx` → 领域异常类（`docs/07` §11 的 20 码，来自既有实现）。"""
    index: dict[str, type[StructAIError]] = {}
    for value in vars(domain_errors).values():
        if (
            isinstance(value, type)
            and issubclass(value, StructAIError)
            and value is not StructAIError
        ):
            index.setdefault(value.code, value)
    return index


_DOMAIN_ERRORS_BY_CODE: Final[dict[str, type[StructAIError]]] = _domain_error_index()
"""领域异常索引（**只读**；码值仍以 `app/domain/errors.py` 为唯一权威）。"""
