"""配置层 · RuntimeConfig（运行期配置快照）。

权威来源：`docs/02` §6（Runtime Config）—— 两份规范互补，本文件取并集：

- `source9` §6：`RuntimeConfig(environment, debug, database_url, log_level)` 由
  `Settings` 快照而来，并提供 `build_runtime_config()` 构造器。
- `source7` §6：进程内运行期参数（shutdown / poll / lease / heartbeat）带固定默认值。

设计要点：

- 运行期参数（`source7` §6 四项）**不作为环境变量暴露**，故不登记到 `.env.example`。
- 本模块不依赖 SQLAlchemy / FastAPI / MCP（`docs/07` §14.1 分层红线）。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import Settings, settings

__all__ = ["RuntimeConfig", "build_runtime_config"]


@dataclass(slots=True)
class RuntimeConfig:
    """运行期配置快照。

    前四项来自 `Settings`（`source9` §6，随环境变量变化）；
    后四项是进程内运行期参数（`source7` §6，取规范默认值）。
    """

    # ===== 来自 Settings（source9 §6）=====
    environment: str
    debug: bool
    database_url: str
    log_level: str

    # ===== 进程内运行期参数（source7 §6）=====
    shutdown_timeout_seconds: int = 30
    task_poll_interval_seconds: float = 0.5
    lease_seconds: int = 30
    heartbeat_seconds: int = 10


def build_runtime_config(source: Settings | None = None) -> RuntimeConfig:
    """由 `Settings` 构造 `RuntimeConfig`（`source9` §6 的 `build_runtime_config()`）。

    `source` 缺省时使用进程级单例；显式传入便于测试与后续按租户 / 实例派生。
    """
    resolved = source if source is not None else settings
    return RuntimeConfig(
        environment=resolved.environment,
        debug=resolved.debug,
        database_url=resolved.database_url,
        log_level=resolved.log_level,
    )
