"""StructAI MCP Server —— 进程入口（P01 Bootstrap / P02 Config / P03 Domain / P04 Database）。

验收门槛（`docs/07` §12 P01、`docs/08` §3）：

    python -m app.main      → 能启动并正常退出（退出码 0）

装配顺序（`docs/02` §34）：

    configure_logging(settings.log_level)   → 日志先就绪（structlog → stderr）
    build_container(settings)               → 装配 settings / runtime_config

后续批次接管点：

- P04：容器在此建立并校验数据库连接（`container.startup()`）。
- P08：Registry 校验通过后才允许进入 READY。
- P40 / P41：按 `MCP_TRANSPORT` 选择 STDIO 或 Streamable HTTP 传输。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence

from app import __app_name__, __version__
from app.config.logging import configure_logging
from app.config.settings import settings
from app.container import BATCH_ID, AppContainer, build_container

__all__ = ["async_main", "main"]

logger = logging.getLogger("structai")


async def async_main() -> int:
    """异步主流程：初始化日志 → 装配容器 → startup → shutdown → 返回退出码。"""
    configure_logging(settings.log_level)

    container: AppContainer = build_container(settings)

    logger.info("%s %s starting (batch=%s)", __app_name__, __version__, BATCH_ID)

    await container.startup()
    try:
        logger.info(
            "%s initialized: version=%s environment=%s transport=%s",
            __app_name__,
            settings.app_version,
            settings.environment,
            settings.mcp_transport,
        )
    finally:
        await container.shutdown()

    logger.info("%s stopped cleanly", __app_name__)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """同步入口，返回进程退出码（正常为 0）。"""
    parser = argparse.ArgumentParser(
        prog="structai-mcp",
        description=f"{__app_name__} {__version__} — Core bootstrap (P04)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{__app_name__} {__version__}",
    )
    parser.parse_args(argv)

    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:  # pragma: no cover - 交互式中断
        logger.warning("interrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())
