"""0001 · MIDAS Adapter 专属 7 张表（`docs/07` §4.4；`docs/04` §9–§12）

Revision ID: 0001_midas_registry_tables
Revises:
Create Date: 2026-10-08

权威来源
--------
- `docs/07` §12 P119 门槛 ⑦ —— 「**若**新增 MIDAS 表，必须走 Alembic 迁移」。
- `docs/07` §4.4 —— 7 张表的字段表（其中 4 张由本批自行设计并回填文档）。
- `docs/04` §9–§12 —— 表名与前三张表的字段定义。
- `docs/07` §14.3 —— 禁止启动时静默建表 / 改表；改表一律走 Alembic。

落地裁决（只补实现手段，不改任何字段）
------------------------------------
1. **逐表 `create` 而不是整库 `create_all`**：本迁移**只**创建 MIDAS 的 7 张表
   （`MIDAS_TABLE_NAMES`），Core 的 24 张表**不**在此处创建（它们由既有
   `Base.metadata.create_all` 路径负责，见 `midas/models.py` 裁决 1）。
2. **DDL 来自模型元数据**：列名 / 类型 / 可空性 / 唯一约束由
   `app.infrastructure.adapters.midas.models` 的 `MIDAS_METADATA` **单点**给出，
   避免迁移与模型漂移（验收测试会逐列比对迁移结果与模型元数据）。
3. **`downgrade` 逆序删表**：逆序可避免未来加外键时的依赖问题。
4. **幂等性**：`upgrade` 前先检查 `alembic_version`（Alembic 自带），
   重复执行 `alembic upgrade head` 不会重复建表。
"""

from __future__ import annotations

from alembic import op

from app.infrastructure.adapters.midas.models import MIDAS_METADATA, MIDAS_TABLE_NAMES

revision = "0001_midas_registry_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建 MIDAS 专属的 7 张表（见模块裁决 1 / 2）。"""
    bind = op.get_bind()
    for name in MIDAS_TABLE_NAMES:
        MIDAS_METADATA.tables[name].create(bind, checkfirst=False)


def downgrade() -> None:
    """逆序删除 MIDAS 的 7 张表（见模块裁决 3）。"""
    bind = op.get_bind()
    for name in reversed(MIDAS_TABLE_NAMES):
        MIDAS_METADATA.tables[name].drop(bind, checkfirst=False)