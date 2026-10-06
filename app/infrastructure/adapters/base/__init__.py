"""Infrastructure · Adapters · Base（`docs/07` §3.3 冻结结构；`docs/02` §32 / §33）。

构成（P19–P20）：

| 文件 | 内容 | 规范 |
| --- | --- | --- |
| `adapter.py` | ABC（8 方法）+ `BaseAdapter` + `AdapterContext` | `docs/02` §32 / §4 / §5 / §9 |
| `manifest.py` | `AdapterManifest` + 校验 + 版本匹配 | `docs/02` §6 / §7 / §19 / §20 |
| `errors.py` | 原生异常族 + **唯一**的归一化点（原生 → 20 码） | `docs/02` §49 / §50 |
| `manager.py` | `AdapterManager` + `AdapterHealthManager` | `docs/02` §12–§14 / §52–§57 |

分层红线（`docs/07` §14.1 / §14.2）：本包**不得**依赖 `app.interfaces` / FastAPI /
MCP SDK；Core 内**不得**出现任何厂商专属 endpoint / 参数 / 响应。
"""

from __future__ import annotations

from app.infrastructure.adapters.base.adapter import (
    ADAPTER_METHODS,
    UNRESOLVED_INSTANCE_ID,
    AdapterContext,
    AdapterState,
    BaseAdapter,
    EngineeringSoftwareAdapter,
    adapter_context_from,
)
from app.infrastructure.adapters.base.errors import (
    ADAPTER_NATIVE_ERROR_CODES,
    FALLBACK_ADAPTER_MESSAGE,
    REDACTION_MARKER,
    SENSITIVE_DETAIL_KEY_PARTS,
    AdapterAPIError,
    AdapterAuthenticationError,
    AdapterCapabilityError,
    AdapterConnectionError,
    AdapterNativeError,
    AdapterTimeoutError,
    AdapterValidationError,
    error_for,
    normalize_error,
    raise_normalized,
)
from app.infrastructure.adapters.base.manager import (
    ADAPTER_ERROR_STAGE,
    AdapterFactory,
    AdapterHealthManager,
    AdapterManager,
    AdapterNotFoundError,
    BoundInstance,
    SoftwareInstanceLike,
    SoftwareInstanceLookup,
)
from app.infrastructure.adapters.base.manifest import (
    CAPABILITY_TOKEN_PATTERN,
    MANIFEST_TOKEN_PATTERN,
    AdapterManifest,
    manifest_key,
)

__all__ = [
    "ADAPTER_ERROR_STAGE",
    "ADAPTER_METHODS",
    "ADAPTER_NATIVE_ERROR_CODES",
    "CAPABILITY_TOKEN_PATTERN",
    "FALLBACK_ADAPTER_MESSAGE",
    "MANIFEST_TOKEN_PATTERN",
    "REDACTION_MARKER",
    "SENSITIVE_DETAIL_KEY_PARTS",
    "UNRESOLVED_INSTANCE_ID",
    "AdapterAPIError",
    "AdapterAuthenticationError",
    "AdapterCapabilityError",
    "AdapterConnectionError",
    "AdapterContext",
    "AdapterFactory",
    "AdapterHealthManager",
    "AdapterManager",
    "AdapterManifest",
    "AdapterNativeError",
    "AdapterNotFoundError",
    "AdapterState",
    "AdapterTimeoutError",
    "AdapterValidationError",
    "BaseAdapter",
    "BoundInstance",
    "EngineeringSoftwareAdapter",
    "SoftwareInstanceLike",
    "SoftwareInstanceLookup",
    "adapter_context_from",
    "error_for",
    "manifest_key",
    "normalize_error",
    "raise_normalized",
]
