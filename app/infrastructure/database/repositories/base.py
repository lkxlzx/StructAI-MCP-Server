"""通用 Repository 基类（`docs/02` §26；`docs/07` §12 P05）。

契约与权威来源
--------------
- `docs/02` §26（`source9`）—— `app/infrastructure/database/repositories/base.py` 的
  `Repository(Generic[T])`：`get` / `add` / `delete`。本文件逐项实现，类名写作
  `BaseRepository`，以免与 `app.domain.protocols.Repository`（§11 的 Domain 契约）同名。
- `docs/02` §11（`blue`）—— Domain 侧 `Repository` 契约：`get` / `add` / `remove`
  （P03 已冻结在 `app.domain.protocols.Repository`）。故 `remove` 是本文件的实现名，
  `delete` 保留为**同一语义的别名**，使 §26 与 §11 两处口径都能对上。
- `docs/02` §16 —— `Application Service → UnitOfWork → Repository → SQLAlchemy`：
  **Repository 不负责决定事务何时提交**。因此本模块**不提供 `commit`**
  （`docs/07` §14.4 红线），只提供 `flush`（把挂起变更推入当前事务）；
  事务边界归 P06 UnitOfWork。
- `docs/02` §11（Tenant Isolation）—— Tenant-scoped 查询必须**同时**限制
  `tenant_id` + `resource_id`；**禁止依赖 UI / 上层过滤**（`docs/07` §14.3）。
  本文件据此把该规则**落在仓储自身**：`TenantScopedRepository` 覆写 `get` / `list_all`，
  缺少 `tenant_id` 时直接拒绝，不提供「不过滤租户」的读法；跨租户更新由
  `update_for_tenant` 先做归属校验（失败 → `STRUCTAI-4200`）。
- `docs/02` §12（Optimistic Concurrency）—— 可变资源按 `WHERE version = :expected`
  条件更新，影响行数为 0 → `STRUCTAI-1300`。
- `docs/02` §17 / §44 —— Repository 只负责 persistence：不承载 MCP / RBAC /
  capability / adapter / 工程计算 / AI 逻辑，也不得出现任何厂商专属内容。

落地补充（只提供实现手段，不改变任何字段名 / 类型 / 语义）：

- 主键口径沿用 P04：`String(36)` 的 UUID 字符串。`get` 接受 `UUID | str`，
  统一 `str(...)` 后比对，避免调用方因类型不同而查不到行。
- `add` / `remove` 内部 `flush()`：让 Python 侧列默认值（`id` / `created_at` /
  `updated_at` / `version`）在方法返回时已落到当前事务，且唯一约束冲突在此处即暴露。
  **`flush` 不是 `commit`**，事务仍由上层决定是否提交。
- 列表查询一律显式 `order_by(created_at)`，并带**有界**默认页大小
  `DEFAULT_PAGE_SIZE`（`docs/07` §14.4：禁止无限 payload）。
- 条件更新使用 `synchronize_session=False`：UPDATE 绕过身份映射，冲突时**不**改动
  内存实体（否则会出现在「数据库没改、内存已改」的假象）；成功路径由
  `Session.refresh()` 回填真实值。
- 受保护列（`id` / `version` / `tenant_id`）沿 MRO **取并集**：菱形继承
  （`TenantScopedRepository` + `VersionedRepository`）下任何一层都不能被覆盖掉。

分层红线（`docs/07` §14.1）：本包只允许落在 `app/infrastructure/database/`；
`app/domain/` 不得引用本包，本包也不得反向依赖 Interface 层。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Final, cast
from uuid import UUID

from sqlalchemy import ColumnElement, CursorResult, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import ConcurrencyConflictError, TenantAccessDeniedError

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "BaseRepository",
    "TenantScopedRepository",
    "VersionedRepository",
]

DEFAULT_PAGE_SIZE: Final[int] = 100
"""列表查询的默认页大小（`docs/07` §14.4：禁止无限 payload）。

调用方可以显式传入更大的 `limit`，但**不存在**「不传就是无限」的默认值。
"""


class BaseRepository[EntityT]:
    """通用 Repository 基类（`docs/02` §26）。

    子类必须赋值 `model`（本仓储负责的 ORM 类）；`add` / `remove` / `update` 只做持久化，
    绝不 `commit`（`docs/07` §14.4）。
    """

    model: ClassVar[type[Any]]
    """本仓储负责的 ORM 类（`docs/02` §18–§24）。子类必须赋值。"""

    _PROTECTED_COLUMNS: ClassVar[frozenset[str]] = frozenset({"id"})
    """`update` 不得触碰的列（`docs/02` §26：主键由 `add` 决定，更新不可改）。

    ⚠️ 子类可以**追加**（见 `_protected_columns`），但不要依赖「覆盖」：
    菱形继承下各层声明会取并集。
    """

    def __init__(self, session: AsyncSession) -> None:
        """绑定一个已存在的会话（`docs/02` §16：会话由上层 / UnitOfWork 提供）。"""
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """当前会话（只读用途；事务边界不在此处决定）。"""
        return self._session

    # ===== 契约：`docs/02` §26 + §11 =====

    async def get(self, entity_id: str | UUID) -> EntityT | None:
        """按主键读取（`docs/02` §26）。

        ⚠️ Tenant-owned 实体不要用本方法：`TenantScopedRepository` 已覆写为**必须**
        带 `tenant_id`（`docs/02` §11）。

        Args:
            entity_id: UUID 或 UUID 字符串；内部统一为 `str` 比对（P04 的 `String(36)` 口径）。

        Returns:
            命中的实体；不存在返回 `None`（不抛异常）。
        """
        result = await self._session.execute(
            select(self.model).where(self.model.id == str(entity_id))
        )
        return result.scalar_one_or_none()

    async def add(self, entity: EntityT) -> EntityT:
        """持久化新实体（`docs/02` §26 的 `add(entity: T) -> T`）。

        只 `add` + `flush`，**不 `commit`**（`docs/07` §14.4）。
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def remove(self, entity: EntityT) -> None:
        """删除实体（`app.domain.protocols.Repository.remove`）。

        只 `delete` + `flush`，**不 `commit`**（`docs/07` §14.4）。
        """
        await self._session.delete(entity)
        await self._session.flush()

    async def delete(self, entity: EntityT) -> None:
        """`remove` 的别名（`docs/02` §26 的 `delete`）；同一语义，不是第二个实现。"""
        await self.remove(entity)

    async def update(self, entity: EntityT, **changes: object) -> EntityT:
        """按字段写入并 `flush`（**不 `commit`**）。

        这是**非可变资源**（无 `version` 列）的更新路径；可变资源由
        `VersionedRepository.update` 覆写为带版本守卫的条件更新（`docs/02` §12）。
        Tenant-owned 实体的推荐路径是 `TenantScopedRepository.update_for_tenant`
        （先校验归属，`docs/02` §11）。

        Args:
            entity: 已 `get` 出来的实体（必须属于当前会话）。
            **changes: 待更新的列（列名 → 新值）；受保护列不可在此传入。

        Returns:
            传入的实体（同一对象，已 `flush`）。

        Raises:
            ValueError: 传入了不存在的列，或试图改受保护列（`id` 等）。

        ⚠️ 只 `flush`，**不 `commit`**（`docs/07` §14.4）。
        """
        self._validate_changes(changes)
        for name, value in changes.items():
            setattr(entity, name, value)
        await self._session.flush()
        return entity

    # ===== 通用查询 / 事务内同步 =====

    async def list_all(
        self,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[EntityT]:
        """列出实体，按 `created_at` 升序，页大小默认 `DEFAULT_PAGE_SIZE`。

        `docs/07` §14.4：禁止无限 payload —— 因此**没有**「不传 limit 就取全表」的语义。
        """
        result = await self._session.execute(self._ordered(select(self.model), limit, offset))
        return list(result.scalars().all())

    async def flush(self) -> None:
        """把挂起变更推入当前事务 —— **不是 `commit`**（`docs/02` §16；`docs/07` §14.4）。"""
        await self._session.flush()

    def _ordered(self, stmt: Any, limit: int, offset: int) -> Any:
        """统一列表排序与分页（`created_at` 升序 + `offset` / `limit`）。"""
        return stmt.order_by(self.model.created_at).offset(offset).limit(limit)

    def _protected_columns(self) -> frozenset[str]:
        """沿 MRO 汇总各层声明的受保护列（`docs/02` §12 / §26）。

        ⚠️ 必须**取并集**：`ProjectRepository` 同时继承 `TenantScopedRepository`
        与 `VersionedRepository`，若只取 MRO 上第一个 `_PROTECTED_COLUMNS`，
        另一层的保护（`version` 或 `tenant_id`）会静默失效。
        """
        names: set[str] = set()
        for klass in type(self).__mro__:
            declared = klass.__dict__.get("_PROTECTED_COLUMNS")
            if declared is not None:
                names |= set(declared)
        return frozenset(names)

    def _validate_changes(self, changes: Mapping[str, object]) -> None:
        """校验待更新列：必须真实存在，且不得触碰受保护列。"""
        blocked = sorted(self._protected_columns() & set(changes))
        if blocked:
            raise ValueError(f"immutable column(s) for update: {', '.join(blocked)}")
        unknown = sorted(set(changes) - set(self.model.__table__.columns.keys()))
        if unknown:
            raise ValueError(
                f"unknown column(s) for {self.model.__tablename__}: {', '.join(unknown)}"
            )


class TenantScopedRepository[EntityT](BaseRepository[EntityT]):
    """Tenant-owned 实体仓储（`docs/02` §11 Tenant Isolation）。

    规范要求：查询必须**同时**限制 `tenant_id` + `resource_id`，且禁止依赖 UI / 上层过滤
    （`docs/07` §14.3）。因此本类：

    - **覆写** `get` / `list_all`：缺少 `tenant_id` 直接抛 `ValueError`，
      绝不退化为「不过滤租户」的全局查；
    - 提供 `get_for_tenant` / `list_for_tenant` / `remove_for_tenant` 作为显式入口；
    - 提供 `update_for_tenant`：先校验该行确实属于该租户（失败 → `STRUCTAI-4200`），
      再委托 `update`（可变资源仍走版本守卫）；
    - 把 `tenant_id` 列为受保护列：任何更新都**不能**把行搬到别的租户。
    """

    _PROTECTED_COLUMNS: ClassVar[frozenset[str]] = frozenset({"id", "tenant_id"})
    """`id` 不可改；`tenant_id` 不可改（否则等于跨租户搬行，`docs/02` §11）。"""

    def tenant_criteria(self, tenant_id: str) -> ColumnElement[bool]:
        """租户过滤条件；默认直接用本表的 `tenant_id` 列。

        ⚠️ 不直接持有 `tenant_id` 的表（如 `models`：租户归属经 `projects` 传递）
        **必须覆写**本方法，用 JOIN / `IN (SELECT ...)` 追到所属租户；
        禁止放宽为「不过滤」（`docs/02` §11）。
        """
        return self.model.tenant_id == tenant_id

    def _require_tenant(self, tenant_id: str | None) -> str:
        """租户参数必填（`docs/02` §11）；缺失即拒绝，绝不静默退化为全局查。"""
        if not tenant_id:
            raise ValueError(
                f"tenant_id is required for tenant-scoped access to {self.model.__tablename__}"
            )
        return tenant_id

    # ===== 覆写：禁止无租户过滤的读 =====

    async def get(
        self,
        entity_id: str | UUID,
        *,
        tenant_id: str | None = None,
    ) -> EntityT | None:
        """在指定租户内按主键读取（覆写 `BaseRepository.get`，`docs/02` §11）。

        Raises:
            ValueError: 未提供 `tenant_id`（不允许无租户过滤的读取）。
        """
        return await self.get_for_tenant(entity_id, self._require_tenant(tenant_id))

    async def list_all(
        self,
        *,
        tenant_id: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[EntityT]:
        """列出指定租户的实体（覆写 `BaseRepository.list_all`，`docs/02` §11）。

        Raises:
            ValueError: 未提供 `tenant_id`。
        """
        return await self.list_for_tenant(
            self._require_tenant(tenant_id),
            limit=limit,
            offset=offset,
        )

    # ===== 显式租户入口 =====

    async def get_for_tenant(self, entity_id: str | UUID, tenant_id: str) -> EntityT | None:
        """在指定租户内按主键读取（`docs/02` §11：`tenant_id` + `resource_id`）。"""
        result = await self._session.execute(
            select(self.model).where(
                self.model.id == str(entity_id),
                self.tenant_criteria(tenant_id),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_tenant(
        self,
        tenant_id: str,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[EntityT]:
        """列出指定租户的实体（`docs/02` §11）；绝不返回其他租户的行。"""
        stmt = select(self.model).where(self.tenant_criteria(tenant_id))
        result = await self._session.execute(self._ordered(stmt, limit, offset))
        return list(result.scalars().all())

    async def remove_for_tenant(self, entity_id: str | UUID, tenant_id: str) -> bool:
        """在指定租户内按主键删除（`docs/02` §11）。

        Returns:
            `True` 表示确实删除了本租户的行；`False` 表示该 id 不属于本租户或不存在
            （两种情况**不做区分**，避免跨租户存在性泄露，`docs/02` §48）。
        """
        entity = await self.get_for_tenant(entity_id, tenant_id)
        if entity is None:
            return False
        await self.remove(entity)
        return True

    async def update_for_tenant(
        self,
        entity: EntityT,
        tenant_id: str,
        **changes: object,
    ) -> EntityT:
        """租户内更新（`docs/02` §11 / §12）。

        先确认该行**确实属于该租户**，再委托 `update`：可变资源
        （`VersionedRepository`）仍走 `WHERE version = :expected` 条件更新。

        Args:
            entity: 已取得的实体。
            tenant_id: 调用方声明的租户。
            **changes: 待更新的列（列名 → 新值）；受保护列不可传入。

        Raises:
            TenantAccessDeniedError: 该行不属于该租户（或不存在）—— `STRUCTAI-4200`，
                两种情况**不做区分**（`docs/02` §48）。
            ValueError: 传入了不存在的列，或试图改受保护列。

        ⚠️ 只 `flush` / `UPDATE`，**不 `commit`**（`docs/07` §14.4）。
        """
        record = cast("Any", entity)
        entity_id = str(record.id)

        if await self.get_for_tenant(entity_id, tenant_id) is None:
            raise TenantAccessDeniedError(
                "tenant access denied",
                details={
                    "resource": self.model.__tablename__,
                    "resource_id": entity_id,
                },
            )

        return await super().update(entity, **changes)


class VersionedRepository[EntityT](BaseRepository[EntityT]):
    """带 `version` 的可变资源仓储（`docs/07` §4.3；`docs/02` §12）。

    适用范围：`projects` / `software_instances` / `models` / `tasks`（`docs/07` §4.3）。
    """

    _PROTECTED_COLUMNS: ClassVar[frozenset[str]] = frozenset({"id", "version"})
    """`update` 不允许直接改 `id` / `version` —— 版本号由条件更新自增（`docs/02` §12）。"""

    async def update(self, entity: EntityT, **changes: object) -> EntityT:
        """条件更新（`docs/02` §12）。

        以内存实体的 `version` 作为 `expected_version`，执行
        `UPDATE ... SET <changes>, version = expected + 1 WHERE id = :id AND version = :expected`；
        影响行数为 0 → 抛 `ConcurrencyConflictError`（`STRUCTAI-1300`），
        **不得覆盖其他写入者的修改**。

        Args:
            entity: 已 `get` 出来的实体；其 `version` 即 `expected_version`。
            **changes: 待更新的列（列名 → 新值）；受保护列不可在此传入。

        Returns:
            更新后的实体（已从数据库刷新，`version` 为 `expected + 1`）。

        Raises:
            ValueError: 传入了不存在的列，或试图直接改 `id` / `version`。
            ConcurrencyConflictError: 版本不匹配（`STRUCTAI-1300`）；此时内存实体
                **保持原值**（UPDATE 使用 `synchronize_session=False`），
                调用方应重新读取后再决定重试。

        ⚠️ 本方法只执行 `UPDATE`，**不 `commit`**（`docs/07` §14.4）。
        """
        self._validate_changes(changes)

        record = cast("Any", entity)
        expected = int(record.version)
        entity_id = str(record.id)

        outcome = cast(
            CursorResult[Any],
            await self._session.execute(
                sa_update(self.model)
                .where(
                    self.model.id == entity_id,
                    self.model.version == expected,
                )
                .values(**changes, version=expected + 1)
                .execution_options(synchronize_session=False)
            ),
        )
        if outcome.rowcount != 1:
            raise ConcurrencyConflictError(
                "optimistic concurrency check failed",
                details={
                    "resource": self.model.__tablename__,
                    "resource_id": entity_id,
                    "expected_version": expected,
                },
            )

        await self._session.refresh(entity)
        return entity
