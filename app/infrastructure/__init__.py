"""Infrastructure 层（`docs/07` §3.3 冻结结构）。

分层红线（`docs/07` §14.1）：

- 允许依赖：Domain、标准库、第三方基础设施库（SQLAlchemy / httpx / 文件系统等）。
- 禁止依赖：Interface 层（禁止反向依赖）。
- ORM 只允许出现在 `app/infrastructure/database/`（`docs/07` §14.1）。

P04 已落地 `database/`（Base · Engine · Session · 24 个 ORM Model）；
`registry/` / `adapters/` / `storage/` / `secrets/` / `events/` / `notifications/` / `locks/`
由后续批次（P08 / P19+ / P29+ 等）逐个接入。
"""

from __future__ import annotations

__all__: list[str] = []
