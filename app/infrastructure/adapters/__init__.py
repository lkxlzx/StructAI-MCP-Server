"""Infrastructure · Adapters（`docs/07` §3.3 冻结结构）。

| 子包 | 内容 | 规范 |
| --- | --- | --- |
| `base/` | Adapter ABC / Manifest / 错误归一化 / Manager | `docs/02` §32 / §33 |
| `mock/` | Mock Adapter / 进程内模型状态 / Mock 静力分析 | `docs/02` §27–§51 / §117 |

🔴 厂商专属实现（如未来的真实厂商子包 `vendor_product/`）只允许新增子包 + API Registry 数据，
**不得**改动 9 Tool 契约与 Core（`docs/07` §14.5 / §2.1）。
"""

from __future__ import annotations

from app.infrastructure.adapters.base import (
    ADAPTER_METHODS,
    AdapterContext,
    AdapterHealthManager,
    AdapterManager,
    AdapterManifest,
    AdapterNotFoundError,
    AdapterState,
    BaseAdapter,
    EngineeringSoftwareAdapter,
    adapter_context_from,
    manifest_key,
    normalize_error,
)
from app.infrastructure.adapters.mock import (
    MOCK_CAPABILITIES,
    MOCK_PROTOCOL,
    MOCK_SUPPORTED_OPERATIONS,
    MOCK_SUPPORTED_VERSIONS,
    MOCK_VENDOR,
    MockAdapter,
    MockModelStore,
)

__all__ = [
    "ADAPTER_METHODS",
    "MOCK_CAPABILITIES",
    "MOCK_PROTOCOL",
    "MOCK_SUPPORTED_OPERATIONS",
    "MOCK_SUPPORTED_VERSIONS",
    "MOCK_VENDOR",
    "AdapterContext",
    "AdapterHealthManager",
    "AdapterManager",
    "AdapterManifest",
    "AdapterNotFoundError",
    "AdapterState",
    "BaseAdapter",
    "EngineeringSoftwareAdapter",
    "MockAdapter",
    "MockModelStore",
    "adapter_context_from",
    "manifest_key",
    "normalize_error",
]
