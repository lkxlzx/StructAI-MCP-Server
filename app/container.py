"""应用容器（P01 Bootstrap / P02 Config / P03 Domain）。

- 本文件是**唯一**的依赖装配点（`docs/07` §3.3 冻结结构）。
- 禁止在模块层创建全局单例（`blue` §123：禁止 `global TaskEngine()`）。
- 形状对齐 `docs/02` §33（Bootstrap Container），字段由后续批次逐个接入：

| 字段 | 接入批次 |
| --- | --- |
| `settings` / `runtime_config` | **P02 ✅** |
| `engine` / `session_factory` | P04 |
| `operation_registry` | P08 |
| `execution_service` | P36 |
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from app.config.runtime_config import RuntimeConfig, build_runtime_config
from app.config.settings import Settings

__all__ = ["BATCH_ID", "AppContainer", "build_container"]

BATCH_ID: Final[str] = "P03"


@dataclass(slots=True)
class AppContainer:
    """应用依赖容器。

    P02：`settings` / `runtime_config` 已接入；其余依赖位为空（后续批次填充）。
    `started` 仅表示生命周期已进入运行态。
    """

    settings: Settings
    runtime_config: RuntimeConfig
    engine: Any = None
    session_factory: Any = None
    operation_registry: Any = None
    execution_service: Any = None
    started: bool = field(default=False, repr=False)

    async def startup(self) -> None:
        """启动钩子。

        - P02：仅置位，不做任何外部 I/O。
        - P04：建立并校验数据库连接（禁止启动时静默 `ALTER TABLE`，docs/07 §14.3）。
        - P08：加载并校验 Registry；校验失败时 Server 不得进入 READY（docs/07 §14.4）。
        """
        self.started = True

    async def shutdown(self) -> None:
        """关闭钩子。

        - P02：仅置位。
        - P04：在此 `await engine.dispose()`，确保进程可干净退出。
        """
        self.started = False


def build_container(settings: Settings) -> AppContainer:
    """构造应用容器（`docs/02` §33）。

    P04 起在此装配 `engine` / `session_factory`，P08 起装配 `operation_registry`。
    """
    return AppContainer(
        settings=settings,
        runtime_config=build_runtime_config(settings),
    )
