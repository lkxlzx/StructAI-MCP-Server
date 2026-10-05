"""Database 层（`docs/07` §3.3；`docs/02` §12 / §14–§18）。

构成（P04 / P05 / P06 / P07）：

| 文件 | 内容 | 规范 |
| --- | --- | --- |
| `base.py` | `Base` + `NAMING_CONVENTION`（+ 三个落地 Mixin） | `docs/02` §14 |
| `session.py` | `create_engine` / `create_session_factory` | `docs/02` §15 |
| `models/` | 24 个 ORM Model | `docs/07` §4.3；`docs/02` §17–§18 |
| `repositories/` | 最小集 6 个仓储 + 通用基类（P05） | `docs/02` §26 / §11 / §12 |
| `unit_of_work.py` | `UnitOfWork`：commit / rollback / close（P06） | `docs/02` §16 |
| `seed.py` | 幂等 Seed（P07）：`seed()` / `SeedReport` / `SEED_ORDER` | `docs/02` §43–§46 |

后续批次接管点：

- ~~P05：`repositories/`（最小集 CRUD）~~ ✅ **本批已落地**（最小集 6 个仓储 + 通用基类）。
- ~~P06：`unit_of_work.py`（commit / rollback / close）~~ ✅ **本批已落地**（`UnitOfWork`）。
- ~~P07：`seed.py`（幂等 Seed）~~ ✅ **本批已落地**（`seed()` + `SeedReport` + `SEED_ORDER`）。
  ⚠️ `seed` 既是子模块名又是函数名：若直接导出函数，包属性 `seed` 会被函数覆盖，使
  `import app.infrastructure.database.seed as m` 拿到函数而非模块；故此处以
  `seed_database` 之名导出入口，模块本身仍按 `python -m app.infrastructure.database.seed` 使用。

禁止项（`docs/07` §14.3）：本层只负责 persistence，**禁止启动时静默 `ALTER TABLE`**；
建表只允许在验收脚本 / 测试 / Seed CLI 的 `--create-tables` 显式开关中触发，
schema 演进一律交给 Alembic（`docs/02` §102）。
"""

from __future__ import annotations

import importlib
from typing import Any

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
    "SEED_ORDER",
    "SeedReport",
    "seed_database",
]


# ===== P07 Seed 入口（惰性导出，PEP 562）=====
# ⚠️ `seed` 既是子模块名又是函数名。若在包顶部 `from ...seed import seed as seed_database`，
#    则 `python -m app.infrastructure.database.seed` 会在执行前就把该模块放进 `sys.modules`，
#    runpy 随即报「found in sys.modules … prior to execution」的重复导入警告。
#    故此处惰性导出 —— `from app.infrastructure.database import seed_database` 与
#    `python -m app.infrastructure.database.seed` 两种用法都干净。
_SEED_EXPORTS: dict[str, str] = {
    "SEED_ORDER": "SEED_ORDER",
    "SeedReport": "SeedReport",
    "seed_database": "seed",
}
"""包级名 → `seed.py` 内的名字（`seed()` 函数以 `seed_database` 之名导出）。"""


def __getattr__(name: str) -> Any:
    """惰性解析 Seed 导出（`docs/07` §12 P07；PEP 562）。"""
    attribute = _SEED_EXPORTS.get(name)
    if attribute is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module("app.infrastructure.database.seed"), attribute)
