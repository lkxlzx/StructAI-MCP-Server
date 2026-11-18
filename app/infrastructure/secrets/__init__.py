"""Infrastructure · Secrets 包导出（`docs/07` §8.5 / §14.3；`docs/02` §9 / §26）。

凭据**只**由运行环境注入：
- `EnvironmentCredentialProvider`（容器级通用提供者）：按
  `<ENVIRONMENT_REFERENCE_PREFIX><REF>`（默认 `STRUCTAI_SECRET_<REF>`）读环境。
- 敏感键清洗原语：`looks_sensitive` / `sanitize_mapping` / `redact_value` /
  `REDACTION_MARKER` / `SENSITIVE_KEY_PARTS`。

红线（`docs/07` §14.3）：本模块**不**持有任何值存储，**不**把凭据写回任何持久层；
`set_secret` / `delete_secret` 恒拒绝。
"""

from __future__ import annotations

from app.infrastructure.secrets.base import (
    REDACTION_MARKER,
    SENSITIVE_KEY_PARTS,
    looks_sensitive,
    redact_value,
    sanitize_mapping,
)
from app.infrastructure.secrets.environment import (
    ENVIRONMENT_REFERENCE_PREFIX,
    EnvironmentCredentialProvider,
)

__all__ = [
    "ENVIRONMENT_REFERENCE_PREFIX",
    "EnvironmentCredentialProvider",
    "REDACTION_MARKER",
    "SENSITIVE_KEY_PARTS",
    "looks_sensitive",
    "redact_value",
    "sanitize_mapping",
]
