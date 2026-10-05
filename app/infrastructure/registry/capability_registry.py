"""Registry · CapabilityRegistry —— 能力注册表（`docs/07` §12 P08；`docs/02` §10 / §20 / §27 / §31）。

权威来源
--------
- `docs/02` §20（CapabilityRegistry）—— 能力码清单（`MODEL.*` / `ANALYSIS.*` / `RESULT.*` /
  `DESIGN.*` …）。
- `docs/02` §10（Capability）—— `CapabilityDefinition` 的字段形状
  （`code` / `category` / `name` / `version` / `description`）。
- `docs/07` §5.6 ＋ `docs/02` §70 —— 能力码种子集合（P07 已落库 `capabilities` 表，**41** 条）。
- `docs/02` §27 / §31 —— `operation_capabilities`（Operation ↔ Capability）关系；
  P08 门槛 ③ 要求「`capabilities` 表 41 条可查询」且该关系**由本批落库**。
- `docs/07` §14.2 —— Capability 取值**不得**出现厂商名（红线检查：`app/` 内 0 处）。

落地补充（只补实现手段，不改字段名 / 取值）
------------------------------------------
- `category` 取能力码的**首段**（`MODEL.NODE.READ` → `MODEL`；`DOCUMENT.NEW` → `DOCUMENT`）——
  纯机械切分，不引入新词表。`name` 取能力码本身（规范未给独立显示名）。
- 能力码的**权威集合**是数据库 `capabilities` 表（P07 Seed，41 条）；本类只做**只读**装配。
- Operation ↔ Capability 关系的**权威**是 `operation_registry.OPERATION_CAPABILITIES`
  （逐条带章节出处）；`operation_capabilities` 表是它的**落库形态**
  （由 `sync_operation_capabilities` 写入）。表为空时以静态映射为准并提示运行同步命令。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.domain.errors import NotFoundError
from app.infrastructure.database.models import (
    CapabilityORM,
    OperationCapabilityORM,
    OperationORM,
)
from app.infrastructure.registry.operation_registry import OPERATION_CAPABILITIES

__all__ = ["CapabilityDefinition", "CapabilityRegistry"]

logger = logging.getLogger("structai.registry")


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    """能力定义（`docs/02` §10；`docs/02` §20）。

    `category` / `name` 的推导口径见模块 docstring：`category` = 能力码首段，`name` = 能力码。
    """

    code: str
    category: str
    name: str
    version: str = "1.0"
    description: str = ""

    @classmethod
    def from_row(cls, code: str, description: str | None = None) -> CapabilityDefinition:
        """由 `capabilities` 表的一行构造（`docs/07` §4.3 #16：`code` + `description`）。"""
        return cls(
            code=code,
            category=code.split(".", 1)[0],
            name=code,
            description=description or "",
        )


class CapabilityRegistry:
    """能力注册表（`docs/02` §20；`docs/07` §12 P08 门槛 ③）。

    **只读**：不写任何行、不提交事务（`docs/02` §45 Registry 最终边界；`docs/07` §14.4）。
    """

    def __init__(
        self,
        definitions: Iterable[CapabilityDefinition] = (),
        *,
        capabilities_by_operation: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        """由能力定义与 Operation ↔ Capability 关系构造。"""
        self._capabilities: dict[str, CapabilityDefinition] = {
            definition.code: definition for definition in definitions
        }
        relations = capabilities_by_operation or OPERATION_CAPABILITIES
        self._capabilities_by_operation: Mapping[str, tuple[str, ...]] = MappingProxyType(
            {name: tuple(codes) for name, codes in relations.items()}
        )
        operations_by_capability: dict[str, list[str]] = {}
        for operation, codes in self._capabilities_by_operation.items():
            for code in codes:
                operations_by_capability.setdefault(code, []).append(operation)
        self._operations_by_capability: Mapping[str, tuple[str, ...]] = MappingProxyType(
            {code: tuple(sorted(names)) for code, names in operations_by_capability.items()}
        )

    # ===== 查询（`docs/02` §20）=====

    async def get(self, code: str) -> CapabilityDefinition | None:
        """按能力码读取；未登记返回 `None`。"""
        return self._capabilities.get(code)

    async def list(self) -> list[CapabilityDefinition]:
        """全部能力定义，按 `code` 升序（输出确定性）。"""
        return [self._capabilities[code] for code in sorted(self._capabilities)]

    def require(self, code: str) -> CapabilityDefinition:
        """按能力码读取；未登记 → `NotFoundError`（`docs/02` §15 的查找失败口径）。"""
        definition = self._capabilities.get(code)
        if definition is None:
            raise NotFoundError(f"Capability not found: {code}")
        return definition

    def codes(self) -> tuple[str, ...]:
        """全部能力码（升序元组）。"""
        return tuple(sorted(self._capabilities))

    def capabilities_for(self, operation: str) -> tuple[str, ...]:
        """某 Operation 需要的能力码（`docs/02` §31）。"""
        return self._capabilities_by_operation.get(operation, ())

    def operations_for(self, capability: str) -> tuple[str, ...]:
        """依赖某能力码的 Operation（`docs/02` §27 的反向查询）。"""
        return self._operations_by_capability.get(capability, ())

    def summary(self) -> dict[str, Any]:
        """装配摘要（供启动日志与验收证据；**不含** secret）。"""
        return {
            "capabilities": len(self._capabilities),
            "operations_with_capabilities": len(self._capabilities_by_operation),
            "relations": sum(len(codes) for codes in self._capabilities_by_operation.values()),
        }

    def __len__(self) -> int:
        return len(self._capabilities)

    def __contains__(self, code: object) -> bool:
        return code in self._capabilities

    # ===== 装配 =====

    @classmethod
    async def load(
        cls,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> CapabilityRegistry | None:
        """从数据库装配能力注册表（`docs/02` §20）。

        Args:
            engine: 只用于只读地探查表是否存在（不建表、不改表）。
            session_factory: `create_session_factory(engine)` 的产物（P04）。

        Returns:
            已装配的注册表；`capabilities` 表不存在时返回 `None`（数据库未配备）。

        Raises:
            NotFoundError: 库中 `operations` / `capabilities` 行缺失，无法解析
                `operation_capabilities` 的关联（说明该库未按 P07 Seed 配备）。
        """
        tables = await _table_names(engine)
        if "capabilities" not in tables:
            logger.warning(
                "capability registry not provisioned: table 'capabilities' is absent; "
                "run `python -m app.infrastructure.database.seed`"
            )
            return None

        async with session_factory() as session:
            rows = list((await session.execute(select(CapabilityORM))).scalars().all())
            definitions = [CapabilityDefinition.from_row(row.code, row.description) for row in rows]
            relations = await _load_relations(session, tables)

        registry = cls(definitions, capabilities_by_operation=relations)
        logger.info("capability registry assembled: %s", registry.summary())
        return registry


async def _table_names(engine: AsyncEngine) -> set[str]:
    """只读地取库中表名（**不**建表 / 不改表，`docs/07` §14.3）。"""
    async with engine.connect() as connection:
        return set(
            await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_table_names()
            )
        )


async def _load_relations(
    session: AsyncSession,
    tables: set[str],
) -> Mapping[str, tuple[str, ...]]:
    """读取 `operation_capabilities` 关系（`docs/02` §27）。

    表为空 / 不存在时回落到静态映射 `OPERATION_CAPABILITIES` —— 静态映射是权威，
    数据库只是它的落库形态（`sync_operation_capabilities` 写入）。

    顺序：`operation_capabilities` 是**集合**语义（复合主键，表内无顺序）。为与
    `OperationDefinition.required_capabilities`（`docs/02` §86 的声明顺序）一致，
    已知 Operation 按**静态映射的顺序**输出，额外的码追加在末尾（升序）。
    """
    if "operation_capabilities" not in tables or "operations" not in tables:
        return OPERATION_CAPABILITIES

    rows = (
        await session.execute(
            select(
                OperationCapabilityORM.operation_id,
                OperationCapabilityORM.capability_id,
            )
        )
    ).all()
    if not rows:
        logger.warning(
            "operation_capabilities is empty: falling back to the static mapping; run "
            "`python -m app.infrastructure.registry.operation_registry` to persist it"
        )
        return OPERATION_CAPABILITIES

    operation_names = {
        str(identifier): str(name)
        for identifier, name in (
            await session.execute(select(OperationORM.id, OperationORM.name))
        ).all()
    }
    capability_codes = {
        str(identifier): str(code)
        for identifier, code in (
            await session.execute(select(CapabilityORM.id, CapabilityORM.code))
        ).all()
    }

    relations: dict[str, set[str]] = {}
    for operation_id, capability_id in rows:
        operation = operation_names.get(str(operation_id))
        capability = capability_codes.get(str(capability_id))
        if operation is None or capability is None:
            raise NotFoundError(
                f"operation_capabilities has a dangling row: {operation_id} -> {capability_id}"
            )
        relations.setdefault(operation, set()).add(capability)

    ordered: dict[str, tuple[str, ...]] = {}
    for name, codes in relations.items():
        declared = [code for code in OPERATION_CAPABILITIES.get(name, ()) if code in codes]
        ordered[name] = tuple(declared + sorted(codes - set(declared)))
    return ordered
