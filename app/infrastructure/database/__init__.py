"""Database 层（`docs/07` §3.3；`docs/02` §12 / §14–§18）。

构成（P04 / P05 / P06）：

| 文件 | 内容 | 规范 |
| --- | --- | --- |
| `base.py` | `Base` + `NAMING_CONVENTION`（+ 三个落地 Mixin） | `docs/02` §14 |
| `session.py` | `create_engine` / `create_session_factory` | `docs/02` §15 |
| `models/` | 24 个 ORM Model | `docs/07` §4.3；`docs/02` §17–§18 |
| `repositories/` | 最小集 6 个仓储 + 通用基类（P05） | `docs/02` §26 / §11 / §12 |
| `unit_of_work.py` | `UnitOfWork`：commit / rollback / close（P06） | `docs/02` §16 |

后续批次接管点：

- ~~P05：`repositories/`（最小集 CRUD）~~ ✅ **本批已落地**（最小集 6 个仓储 + 通用基类）。
- ~~P06：`unit_of_work.py`（commit / rollback / close）~~ ✅ **本批已落地**（`UnitOfWork`）。
- P07：`seed.py`（幂等 Seed）。

禁止项（`docs/07` §14.3）：本层只负责 persistence，**禁止启动时静默 `ALTER TABLE`**；
本批次只做 `Base.metadata.create_all`，schema 演进一律交给 Alembic。
"""

from __future__ import annotations

# ⚠️ 必须显式导入 models：ORM 类只有被导入后才会注册进 `Base.metadata`。
# 该导入使 `import app.infrastructure.database` 即完成 24 张表的元数据登记，
# 是 `Base.metadata.create_all` 与 Alembic `target_metadata` 的前提。
# P05：仓储层只依赖 Session / ORM；导入后可直接 `from ...database import repositories`。
from app.infrastructure.database import models, repositories
from app.infrastructure.database.base import (
    NAMING_CONVENTION,
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionMixin,
)
from app.infrastructure.database.session import create_engine, create_session_factory
from app.infrastructure.database.unit_of_work import UnitOfWork

__all__ = [
    "NAMING_CONVENTION",
    "Base",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "UnitOfWork",
    "VersionMixin",
    "create_engine",
    "create_session_factory",
    "models",
    "repositories",
]
