"""Database 层（`docs/07` §3.3；`docs/02` §12 / §14–§18）。

构成（P04）：

| 文件 | 内容 | 规范 |
| --- | --- | --- |
| `base.py` | `Base` + `NAMING_CONVENTION`（+ 三个落地 Mixin） | `docs/02` §14 |
| `session.py` | `create_engine` / `create_session_factory` | `docs/02` §15 |
| `models/` | 24 个 ORM Model | `docs/07` §4.3；`docs/02` §17–§18 |

后续批次接管点：

- P05：`repositories/`（最小集 CRUD）。
- P06：`unit_of_work.py`（commit / rollback / close）。
- P07：`seed.py`（幂等 Seed）。

禁止项（`docs/07` §14.3）：本层只负责 persistence，**禁止启动时静默 `ALTER TABLE`**；
本批次只做 `Base.metadata.create_all`，schema 演进一律交给 Alembic。
"""

from __future__ import annotations

# ⚠️ 必须显式导入 models：ORM 类只有被导入后才会注册进 `Base.metadata`。
# 该导入使 `import app.infrastructure.database` 即完成 24 张表的元数据登记，
# 是 `Base.metadata.create_all` 与 Alembic `target_metadata` 的前提。
from app.infrastructure.database import models
from app.infrastructure.database.base import (
    NAMING_CONVENTION,
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionMixin,
)
from app.infrastructure.database.session import create_engine, create_session_factory

__all__ = [
    "NAMING_CONVENTION",
    "Base",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "VersionMixin",
    "create_engine",
    "create_session_factory",
    "models",
]
