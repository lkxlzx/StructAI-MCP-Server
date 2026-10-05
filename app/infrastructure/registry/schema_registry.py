"""Registry · SchemaRegistry —— Schema 注册表（`docs/07` §12 P08；`docs/02` §12 / §14 / §15 / §22）。

权威来源
--------
- `docs/02` §15（SchemaRegistry）—— **原文实现**：`register(schema_id, schema)` / `get(schema_id)`；
  未注册的 id → `raise NotFoundError(f"Schema not found: {schema_id}")`。
- `docs/02` §14 / §22 —— Schema URI 口径：`structai://schema/model/node/v1`、
  `structai://schema/model/node/query/v1`、`structai://schema/build/column/v1` …
- `docs/02` §12 —— 「旧版本**不可**覆盖」：靠**版本化 id** 表达（`…/v1` 与 `…/v2` 是不同 id），
  因此 `register` 不需要额外的「禁止覆盖」逻辑。
- `docs/07` §12 P08 门槛 ④ —— `register` / `get`；未注册 id → `NotFoundError`。
- P07 的 `seed.py` 已固化 `input_schema` / `output_schema` 的 URI 生成口径
  （`structai://schema/<operation 名小写、"." → "/">/v1`），本批沿用同一口径。

`NotFoundError` 与 20 码错误契约
--------------------------------
`docs/07` §11 冻结的是 **20 码**，其中**没有** NotFound 码；`docs/02` §9（`source9`）另给了
一个 `STRUCTAI-70xx` 段的新码（即**第 21 个码**），与本项目唯一权威的错误码清单冲突。
本批的裁决（已登记到 `docs/07` §11 补充说明）：`NotFoundError` **不携带** `STRUCTAI-xxxx`，
也不继承
`StructAIError` —— 它只用于 Registry 装配期的内部查找失败（`docs/07` §14.4），
不会被序列化成对外错误。

落地补充（只补实现手段，不改方法名 / 语义）
------------------------------------------
- `register` 对传入 schema 做**浅拷贝**，避免调用方在注册后改动同一对象而「悄悄改库」。
- 本类**不**校验 schema 的 JSON Schema 合法性 —— 那是 P09 SchemaEngine 的职责
  （`docs/02` §13 / §16）；P09 会用 `registry/schema/` 下的 616 个 Schema 文件填充本注册表。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from app.domain.errors import NotFoundError

__all__ = ["SCHEMA_URI_PREFIX", "SchemaRegistry"]

SCHEMA_URI_PREFIX: Final[str] = "structai://schema/"
"""Schema id 前缀（`docs/02` §14 / §22）。"""


class SchemaRegistry:
    """Schema 注册表（`docs/02` §15；`docs/07` §12 P08 门槛 ④）。

    ⚠️ `register` / `get` 是**同步**方法 —— 与 `docs/02` §15 的原文签名逐项一致
    （Schema 是进程内不可变引用数据，不涉及 I/O；数据库 / 文件装载由 P09 负责）。
    """

    def __init__(self) -> None:
        """空注册表（`docs/02` §15）。"""
        self._schemas: dict[str, dict[str, Any]] = {}

    def register(self, schema_id: str, schema: Mapping[str, Any]) -> None:
        """登记一个 Schema（`docs/02` §15）。

        Args:
            schema_id: Schema URI，形如 `structai://schema/model/node/v1`（`docs/02` §14）。
            schema: JSON Schema 对象（draft 2020-12，`docs/02` §12 / §22）。

        ⚠️ 同名 id 再次登记 = 覆盖（`docs/02` §15 的原文语义）；「旧版本不可覆盖」靠
        **版本化 id** 表达（`…/v1` 与 `…/v2` 不同 id），不是靠禁止覆盖（`docs/02` §12）。
        """
        self._schemas[schema_id] = dict(schema)

    def get(self, schema_id: str) -> dict[str, Any]:
        """按 id 读取 Schema（`docs/02` §15）。

        Args:
            schema_id: Schema URI。

        Returns:
            已登记的 JSON Schema。

        Raises:
            NotFoundError: 该 id 未登记（`docs/02` §15 的原文写法）。
        """
        schema = self._schemas.get(schema_id)
        if schema is None:
            raise NotFoundError(f"Schema not found: {schema_id}")
        return schema

    def registered_ids(self) -> tuple[str, ...]:
        """已登记的 id（升序元组；输出确定性）。"""
        return tuple(sorted(self._schemas))

    def is_registered(self, schema_id: str) -> bool:
        """该 id 是否已登记（不抛异常的探测口径）。"""
        return schema_id in self._schemas

    def __len__(self) -> int:
        return len(self._schemas)

    def __contains__(self, schema_id: object) -> bool:
        return schema_id in self._schemas
