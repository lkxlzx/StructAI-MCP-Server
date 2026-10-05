"""配置层（`docs/07` §3.3 冻结结构）。

| 文件 | 职责 |
| --- | --- |
| `settings.py` | `Settings` —— 环境变量 / `.env` → 进程配置（pydantic-settings） |
| `runtime_config.py` | `RuntimeConfig` —— 运行期配置快照 |
| `logging.py` | `configure_logging` —— structlog 结构化日志（一律写 stderr） |

⚠️ 本包**故意不**在此处绑定 `settings` 这个名字：`app.config.settings` 必须始终解析为
**子模块**，否则 `import app.config.settings as m` 会拿到单例而不是模块。需要单例请按
`docs/02` §34 的写法：`from app.config.settings import settings`。
"""

from __future__ import annotations

from app.config.logging import TRACE_FIELDS, bind_context, clear_context, configure_logging
from app.config.runtime_config import RuntimeConfig, build_runtime_config
from app.config.settings import Settings

__all__ = [
    "TRACE_FIELDS",
    "RuntimeConfig",
    "Settings",
    "bind_context",
    "build_runtime_config",
    "clear_context",
    "configure_logging",
]
