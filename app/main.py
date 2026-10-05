"""StructAI MCP Server —— 进程入口（P01 Bootstrap）。

验收门槛（docs/07 §12 P01、docs/08 §3）：

    python -m app.main      → 能启动并正常退出（退出码 0）

后续批次接管点：

- P02：日志初始化改由 `app/config/logging.py` 承担（structlog），Settings 生效值在此打印。
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
from app.container import AppContainer, build_container

__all__ = ["async_main", "main"]

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

logger = logging.getLogger("structai")


def _configure_bootstrap_logging(level: str = "INFO") -> None:
    """临时日志配置；P02 由 `app/config/logging.py` 接管并改用 structlog。"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=_LOG_FORMAT,
    )


async def async_main() -> int:
    """异步主流程：装配容器 → startup → shutdown → 返回退出码。"""
    _configure_bootstrap_logging()

    container: AppContainer = build_container()

    logger.info("%s %s starting (batch=P01)", __app_name__, __version__)

    await container.startup()
    try:
        logger.info("%s initialized: version=%s", __app_name__, __version__)
    finally:
        await container.shutdown()

    logger.info("%s stopped cleanly", __app_name__)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """同步入口，返回进程退出码（正常为 0）。"""
    parser = argparse.ArgumentParser(
        prog="structai-mcp",
        description=f"{__app_name__} {__version__} — Core bootstrap (P01)",
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
