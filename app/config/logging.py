"""配置层 · 日志初始化（structlog）。

权威来源：

- `docs/02` §7（Logging）—— 必须支持：`structured log` · `stderr` ·
  `trace_id` · `request_id` · `task_id`；**不得把 MCP Protocol 数据写入 stdout**。
- `docs/06` §42（STDIO 日志）—— `stdout → MCP` · `stderr → logs`。
- `docs/07` §3.1（技术栈冻结）—— 日志实现为 structlog。

实现要点：

1. 全部日志写入 **stderr**：stdout 是 MCP 协议的专属通道，绝不能被日志污染。
2. 结构化字段通过 structlog **contextvars** 注入，由 `merge_contextvars` 自动合并，
   因此 `trace_id` / `request_id` / `task_id`（以及后续 `user_id` / `tenant_id` /
   `project_id` / `tool` / `operation` / `software` / `adapter`）无需逐处传参。
   本模块提供 `bind_context()` / `clear_context()` 作为唯一注入入口。
3. 标准库 `logging`（含 uvicorn 等第三方库）经 `ProcessorFormatter` 汇入同一渲染管线，
   保证格式与字段口径一致。
4. `configure_logging()` **幂等**：重复调用只更新本模块自己的 handler，不影响
   其他 handler（例如 pytest 的日志捕获）。

安全（`docs/07` §14.3）：调用方**绝不**把 secret（password / API key / token /
private key）绑定进上下文或写入日志。
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Final

import structlog

__all__ = ["TRACE_FIELDS", "bind_context", "clear_context", "configure_logging"]

_HANDLER_NAME: Final[str] = "structai-structlog"

TRACE_FIELDS: Final[tuple[str, ...]] = ("trace_id", "request_id", "task_id")
"""`docs/02` §7 要求日志必须支持的关联字段。"""


def _resolve_level(level: str) -> int:
    """把 `"DEBUG"` / `"info"` 之类的字符串解析为标准库日志级别，非法值回退 INFO。"""
    resolved = logging.getLevelName(str(level).upper())
    return resolved if isinstance(resolved, int) else logging.INFO


def _shared_processors() -> list[Any]:
    """structlog 与标准库共用的前置处理器链。"""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]


def configure_logging(level: str = "INFO", *, json_output: bool = False) -> None:
    """初始化结构化日志（幂等）。

    Args:
        level: 日志级别名（如 `"INFO"` / `"DEBUG"`），非法值回退 `INFO`。
        json_output: `True` 时输出 JSON 行（部署 / 采集场景），默认输出
            key=value 控制台格式（本地与证据留痕更易读）。
    """
    resolved_level = _resolve_level(level)
    shared_processors = _shared_processors()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    # stdout 保留给 MCP 协议数据（docs/06 §42）—— 日志一律走 stderr。
    handler = logging.StreamHandler(sys.stderr)
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    for existing in list(root_logger.handlers):
        if existing.get_name() == _HANDLER_NAME:
            root_logger.removeHandler(existing)
    root_logger.addHandler(handler)
    root_logger.setLevel(resolved_level)


def bind_context(**values: Any) -> None:
    """把关联字段绑定到当前上下文（`docs/02` §7）。

    典型用法：`bind_context(trace_id=..., request_id=..., task_id=...)`。
    绑定值会出现在其后所有日志中，直到 `clear_context()` 或上下文退出。
    """
    structlog.contextvars.bind_contextvars(**values)


def clear_context() -> None:
    """清空当前上下文的关联字段（请求 / 任务结束时调用）。"""
    structlog.contextvars.clear_contextvars()
