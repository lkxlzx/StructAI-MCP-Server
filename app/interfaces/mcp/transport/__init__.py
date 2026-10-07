"""Interface · MCP · Transport（P40 STDIO / P41 Streamable HTTP）。

`docs/07` §3.3 的冻结结构原本**没有**传输文件（`interfaces/mcp/` 只有
`server.py` / `context.py` / `dispatcher.py` / `responses.py` / `errors.py` /
`tools/`），而 `docs/03` §80 给出的 Core Alpha 目录形状是：

```text
app/interfaces/mcp/
├── protocol.py · session.py · authentication.py · progress.py · cancellation.py
└── transport/
    ├── base.py
    ├── stdio.py
    └── http.py
```

本批据此裁决落点（见 `docs/07` §3.3 的登记与 §16 的裁决）：

| 章节 | 落点 |
| --- | --- |
| `docs/03` §3（Transport 抽象）· §20–§24（限制）· §25–§34（协议）| `transport/base.py` |
| `docs/03` §40–§43（STDIO Transport / 骨架 / 日志 / 安全）| `transport/stdio.py` |
| `docs/03` §44–§59（Streamable HTTP 全节）| `transport/http.py` |

⚠️ 传输层**只**做通信（`docs/03` §2 / §60）：不侵入 Core 执行管线、
不复制 9 Tool Contract（`docs/02` §124）、不出现任何软件专属逻辑。
"""

from __future__ import annotations

from app.interfaces.mcp.transport.base import (
    HTTP_IDENTITY_STATE_KEY,
    MCP_TRANSPORT_STAGE,
    SERVER_INSTRUCTIONS,
    TOOL_INPUT_SCHEMA,
    MCPRuntimeLimits,
    MCPTransport,
    build_protocol_server,
    tool_definition,
)

__all__ = [
    "HTTP_IDENTITY_STATE_KEY",
    "MCP_TRANSPORT_STAGE",
    "MCPRuntimeLimits",
    "MCPTransport",
    "SERVER_INSTRUCTIONS",
    "TOOL_INPUT_SCHEMA",
    "build_protocol_server",
    "tool_definition",
]
