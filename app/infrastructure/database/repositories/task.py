"""任务仓储（`docs/07` §12 P05 最小集；`docs/02` §11 / §12 / §24）。

`tasks` 是 Tenant-owned（`tenant_id` 列，`docs/07` §4.3 #19）＋ 可变资源
（`version` 列）→ 同时继承 `TenantScopedRepository` 与 `VersionedRepository`。

本仓储**只做 persistence**：状态机（12 态）、队列、租约、恢复、取消全部属于
P22–P28（`docs/02` §10 / §34 / §40；`docs/07` §10）。因此这里**不**做状态校验、
**不**改 `status` 以外的业务语义、**不**把恢复中的任务标记为 `COMPLETED`
（`docs/07` §14.4）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, or_, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.task.dag import encode_depends_on
from app.domain.enums import TaskStepStatus
from app.domain.protocols import (
    TaskDraft,
    TaskRecord,
    TaskStepDraft,
    TaskStepRecord,
)
from app.infrastructure.database.models.task import TaskORM, TaskStepORM
from app.infrastructure.database.repositories.base import (
    DEFAULT_PAGE_SIZE,
    TenantScopedRepository,
    VersionedRepository,
)

__all__ = ["TaskRepository", "TaskStoreRepository", "build_task_store"]


class TaskRepository(TenantScopedRepository[TaskORM], VersionedRepository[TaskORM]):
    """任务仓储（`docs/02` §24；`docs/07` §4.3 #19）。

    能力：`get` / `add` / `remove` / `list_all`（`docs/02` §26）＋
    `get_for_tenant` / `list_for_tenant` / `remove_for_tenant`（`docs/02` §11）＋
    `list_by_project` / `list_by_status` ＋ `update`（乐观并发，`docs/02` §12）。
    绝不 `commit`（`docs/07` §14.4）。
    """

    model = TaskORM

    async def list_by_project(
        self,
        project_id: str | UUID,
        tenant_id: str,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[TaskORM]:
        """列出某项目下的任务（`docs/02` §11：`tenant_id` + `project_id` 同时限制）。"""
        stmt = select(TaskORM).where(
            TaskORM.project_id == str(project_id),
            self.tenant_criteria(tenant_id),
        )
        result = await self.session.execute(self._ordered(stmt, limit, offset))
        return list(result.scalars().all())

    async def list_by_status(
        self,
        status: str,
        tenant_id: str,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[TaskORM]:
        """列出某租户下指定状态的任务（`docs/02` §11；状态取值见 `TaskStatus`）。

        `status` 只作为**列过滤**，本仓储不判断状态迁移是否合法
        （状态机归 P22，`docs/02` §4 / §10）。
        """
        stmt = select(TaskORM).where(
            TaskORM.status == status,
            self.tenant_criteria(tenant_id),
        )
        result = await self.session.execute(self._ordered(stmt, limit, offset))
        return list(result.scalars().all())


class TaskStoreRepository:
    """`TaskStore` 的 SQLAlchemy 实现（`docs/02` §9 / §11 / §34 / §36；`docs/07` §10.2）。

    ⚠️ 本类**不继承**任何仓储基类（`BaseRepository` / `TenantScopedRepository` /
    `VersionedRepository`；见模块裁决）：Domain 契约 `TaskStore.get(task_id, tenant_id)`
    要求 `tenant_id` **位置传参**且返回 Domain 记录，与父类
    `TenantScopedRepository.get(entity_id, *, tenant_id=None) -> EntityT | None` 的签名与
    返回类型都**不兼容** —— 靠 `# type: ignore[override]` 消音会让「按父类契约调用
    `repo.get(id, tenant_id=X)`」在运行期抛 `TypeError`（潜伏回归）。故本类自带
    `__init__` / `session` / `tenant_criteria`（租户过滤已在各方法内直接实现），
    **不**声明任何 `type: ignore`。P05 的 `TaskRepository` 与
    `build_repositories(session).task` **保持原样**（仍是 `TaskRepository`）。

    只做 persistence：**不**判定状态合法性（那是 `state_machine.py`）、**不**决定事务
    （那是 `UnitOfWork`）、**不**写业务语义。全部方法**绝不** `commit` / `rollback`
    （`docs/07` §14.4）。

    🔴 **原子性**（`docs/02` §36）：

    - `acquire_lease` 是**单条**条件 `UPDATE`（`WHERE lease_owner IS NULL OR
      lease_until < now`），影响行数 **1** 才算获得租约；**禁止** `SELECT → UPDATE`
      （否则两个 Worker 会同时抢到同一任务）；
    - `heartbeat` / `release_lease` / `update_progress` / `transition` / `update_step`
      同样是**条件更新**：影响 0 行即失败（由调用方判定，本层**不**抛异常）。

    ⚠️ **读路径强制刷新**（见模块裁决）：全部写操作都用
    `synchronize_session=False`（照抄 `base.py` 的做法），ORM 身份映射里的对象因此会
    变成**陈旧**的。故本类的读一律带 `populate_existing=True`，保证返回的
    `TaskRecord` 反映**数据库现状**（与 `VersionedRepository.update` 之后
    `session.refresh(entity)` 是同一目的）。

    ⚠️ **时间口径**：SQLite 不保存时区，`DateTime(timezone=True)` 读回来是 naive。
    故本类在构造 Domain 记录时统一用 `_as_utc()` 补 `UTC`（照抄
    `repositories/security.py` 的既有做法），使 `lease_until < now` 是
    「感知 vs 感知」比较（`docs/02` §36）。
    """

    def __init__(self, session: AsyncSession) -> None:
        """绑定一个已存在的会话（`docs/02` §16：会话由 `UnitOfWork` 提供）。

        Args:
            session: 已存在的 `AsyncSession`（本类**不**开事务、**不** `commit`）。
        """
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """当前会话（只读用途；事务边界不在此处决定）。"""
        return self._session

    def tenant_criteria(self, tenant_id: str) -> Any:
        """租户过滤条件（`docs/02` §11：`tenant_id` + `resource_id` 同时限制）。"""
        return TaskORM.tenant_id == tenant_id

    # ===== `docs/02` §9 / §47：创建 =====

    async def create(
        self,
        draft: TaskDraft,
        steps: Sequence[TaskStepDraft] = (),
    ) -> TaskRecord:
        """落库一个新任务（及其 DAG 步骤），返回 `TaskRecord`（`docs/02` §9 / §47）。

        ⚠️ `status` 的**合法性**由调用方（`state_machine.py`）保证，本层只写入
        （`domain.protocols.TaskDraft` 的说明）。

        Args:
            draft: 任务草稿；`id` / `created_at` / `version` 由列默认值生成。
            steps: DAG 步骤草稿（`docs/07` §4.3 #20）；逐个落 `task_steps`，
                `status` 固定 `PENDING`（`docs/02` §50 的初始态），
                `depends_on_json` 由 `encode_depends_on` 规范化（排序后去重）。

        Returns:
            新建任务的 `TaskRecord`（`created_at` / `version` 已由 `flush` 回填）。
        """
        row = TaskORM(
            tenant_id=str(draft.tenant_id),
            project_id=None if draft.project_id is None else str(draft.project_id),
            request_id=str(draft.request_id),
            trace_id=str(draft.trace_id),
            tool=str(draft.tool),
            operation=str(draft.operation),
            status=str(draft.status),
            priority=int(draft.priority),
            max_retries=int(draft.max_retries),
            progress=0,
            retry_count=0,
            cancel_requested=False,
        )
        self.session.add(row)
        await self.session.flush()

        for step in steps:
            self.session.add(
                TaskStepORM(
                    task_id=str(row.id),
                    step_key=str(step.step_key),
                    operation=str(step.operation),
                    status=str(TaskStepStatus.PENDING),
                    parameters_json=str(step.parameters_json),
                    depends_on_json=encode_depends_on(step.depends_on),
                )
            )
        await self.session.flush()
        return _to_record(row)

    # ===== `docs/02` §11 / §34：读取 =====

    async def get(self, task_id: str, tenant_id: str) -> TaskRecord | None:
        """在租户内按主键读取（`docs/02` §11：`tenant_id` + `resource_id`）。

        ⚠️ 本类**不继承**任何仓储基类（见类 docstring）：本签名即 Domain 契约
        `TaskStore.get(task_id, tenant_id)` 的原样 —— `tenant_id` **位置传参**
        （`docs/02` §11 的「同时限制租户 + 资源」），返回 Domain 记录而非 ORM 行。
        因此**不存在**与父类签名 / 返回类型冲突的问题，也**不需要** `type: ignore`。


        Returns:
            命中的 `TaskRecord`；不存在或不属于该租户时返回 `None`
            （两种情况**不做区分**，避免跨租户存在性泄露，`docs/02` §48）。
        """
        row = await self._fresh(task_id, tenant_id=tenant_id)
        return None if row is None else _to_record(row)

    async def unfinished(
        self,
        *,
        statuses: Sequence[str],
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> Sequence[TaskRecord]:
        """列出未完成任务（`docs/02` §42 / §52；`docs/07` §10.2 的启动恢复扫描）。

        ⚠️ 这是**唯一**的跨租户读：启动恢复必须能扫到全部租户的未完成任务
        （`docs/02` §42 的 `RecoveryManager` 在**服务启动时**运行，此时没有租户上下文）。

        Args:
            statuses: 入口状态（`recovery.RECOVERY_ENTRY_STATUSES` 的四态）。
            limit: 返回上限；缺省 `DEFAULT_PAGE_SIZE`（`docs/07` §14.4：**有界**）。

        Returns:
            按 `priority` + `created_at` 升序的 `TaskRecord` 元组
            （`docs/02` §17 的排序键；恢复顺序因此与队列一致）。
        """
        stmt = (
            select(TaskORM)
            .where(TaskORM.status.in_([str(status) for status in statuses]))
            .order_by(TaskORM.priority, TaskORM.created_at)
            .limit(int(limit))
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return tuple(_to_record(row) for row in result.scalars().all())

    async def list_steps(self, task_id: str) -> Sequence[TaskStepRecord]:
        """列出某任务的 DAG 步骤（`docs/02` §52；`docs/07` §4.3 #20）。

        Returns:
            按 `created_at` 升序（即落库顺序）的 `TaskStepRecord` 元组。
        """
        stmt = (
            select(TaskStepORM)
            .where(TaskStepORM.task_id == str(task_id))
            .order_by(TaskStepORM.created_at)
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return tuple(_to_step_record(row) for row in result.scalars().all())

    # ===== `docs/02` §12 / §36：条件更新 =====

    async def transition(
        self,
        task_id: str,
        *,
        expected: str,
        new: str,
        fields: Mapping[str, object] | None = None,
    ) -> bool:
        """条件状态更新（`docs/02` §12 的 CAS；`domain.protocols.TaskStore` 的约定）。

        **单条** `UPDATE tasks SET status = :new, <fields>, version = version + 1
        WHERE id = :id AND status = :expected`；**禁止**先 `SELECT` 再 `UPDATE`
        （`docs/02` §36 的同理）。

        Args:
            task_id: 任务标识。
            expected: 期望的当前状态（`WHERE` 条件）。
            new: 目标状态。
            fields: 随同更新的附加列（如 `retry_count` / `started_at` /
                `error_json` / `result_json` / `completed_at`）。

        Returns:
            `True` 表示影响 **1** 行（本次推进成功）；`False` 表示影响 0 行
            （状态已被别人改过）—— 本层**不**抛异常，由调用方判定
            （`docs/07` §10.2 的「保持真实状态」）。
        """
        values: dict[str, Any] = {"status": str(new)}
        if fields:
            values.update({str(key): value for key, value in fields.items()})
        return await self._conditional_update(task_id, expected=expected, values=values)

    async def acquire_lease(
        self,
        task_id: str,
        *,
        worker_id: str,
        now: datetime,
        lease_until: datetime,
    ) -> TaskRecord | None:
        """抢占租约（`docs/02` §35 / §36 的原子更新；`docs/07` §10.2）。

        **单条**条件 `UPDATE ... WHERE id = :id AND (lease_owner IS NULL OR
        lease_until < :now)`；影响行数 **1** 才代表获得租约（`docs/02` §36）。

        Returns:
            抢占成功后的 `TaskRecord`（回读，见类 docstring）；影响行数不为 1
            时返回 `None`（租约被别人持有且未过期 —— Worker B 不得执行，
            `docs/02` §80）。
        """
        outcome = cast(
            CursorResult[Any],
            await self.session.execute(
                sa_update(TaskORM)
                .where(
                    TaskORM.id == str(task_id),
                    or_(
                        TaskORM.lease_owner.is_(None),
                        TaskORM.lease_until < now,
                    ),
                )
                .values(
                    lease_owner=str(worker_id),
                    lease_until=lease_until,
                    heartbeat_at=now,
                    version=TaskORM.version + 1,
                )
                .execution_options(synchronize_session=False)
            ),
        )
        if outcome.rowcount != 1:
            return None
        row = await self._fresh(task_id)
        return None if row is None else _to_record(row)

    async def heartbeat(
        self,
        task_id: str,
        *,
        worker_id: str,
        heartbeat_at: datetime,
        lease_until: datetime,
    ) -> bool:
        """续租（`docs/02` §38；条件 `WHERE lease_owner = :worker`）。

        Returns:
            `True` 表示影响 1 行（调用方确实是租约持有者）；`False` 表示影响 0 行
            —— 续租**绝不**续到别人手里的租约。
        """
        outcome = cast(
            CursorResult[Any],
            await self.session.execute(
                sa_update(TaskORM)
                .where(
                    TaskORM.id == str(task_id),
                    TaskORM.lease_owner == str(worker_id),
                )
                .values(
                    heartbeat_at=heartbeat_at,
                    lease_until=lease_until,
                    version=TaskORM.version + 1,
                )
                .execution_options(synchronize_session=False)
            ),
        )
        return outcome.rowcount == 1

    async def release_lease(self, task_id: str, *, worker_id: str) -> bool:
        """释放租约（`docs/02` §40；条件 `WHERE lease_owner = :worker`）。

        Returns:
            `True` 表示影响 1 行（确实释放了自己的租约）；`False` 表示影响 0 行
            —— **不**区分「不是持有者」与「本就没有租约」，且绝不释放别人的租约。
        """
        outcome = cast(
            CursorResult[Any],
            await self.session.execute(
                sa_update(TaskORM)
                .where(
                    TaskORM.id == str(task_id),
                    TaskORM.lease_owner == str(worker_id),
                )
                .values(
                    lease_owner=None,
                    lease_until=None,
                    version=TaskORM.version + 1,
                )
                .execution_options(synchronize_session=False)
            ),
        )
        return outcome.rowcount == 1

    async def record_error(
        self,
        task_id: str,
        *,
        error_json: str,
        expected_status: str | None = None,
    ) -> bool:
        """只写 `error_json`、**不**改状态（`docs/02` §30；`TaskStore.record_error`）。

        🔴 **这不是状态转移**：`status` 保持原值，故**不**走冻结的转移表。**单条**
        `UPDATE tasks SET error_json = :e, version = version + 1 WHERE id = :id
        [AND status = :expected]`；**禁止** `SELECT → UPDATE`（`docs/02` §36）。

        Args:
            task_id: 任务标识。
            error_json: 归一化错误信封的 JSON 文本（**只**放 20 码字段，`docs/07` §14.3）。
            expected_status: 给了就要求当前状态**恰为**该值（否则影响 0 行）。

        Returns:
            `True` 表示影响 1 行；`False` 表示影响 0 行（不存在 / 状态不符）——
            本层**不**抛异常，由调用方判定（`docs/07` §10.2 的「保持真实状态」）。
        """
        statement = sa_update(TaskORM).where(TaskORM.id == str(task_id))
        if expected_status is not None:
            statement = statement.where(TaskORM.status == str(expected_status))
        outcome = cast(
            CursorResult[Any],
            await self.session.execute(
                statement.values(
                    error_json=str(error_json),
                    version=TaskORM.version + 1,
                ).execution_options(synchronize_session=False)
            ),
        )
        return outcome.rowcount == 1

    async def update_progress(
        self,
        task_id: str,
        progress: int,
        *,
        tenant_id: str | None = None,
    ) -> bool:
        """写入进度（`docs/02` §31 的 `update_progress`；`docs/02` §11 的租户隔离）。

        Args:
            task_id: 任务标识。
            progress: 已规整到 `[0, 100]` 的进度值（规整由 `progress.py` 负责 ——
                本层只做 persistence）。
            tenant_id: 可选租户限制；给了就追加 `AND tenant_id = :tenant`
                （与 `get(task_id, tenant_id)` 同口径，避免用另一租户的 `task_id`
                改到本租户的行）。

        Returns:
            `True` 表示影响 1 行；`False` 表示该任务不存在（或不属于该租户）。
        """
        statement = sa_update(TaskORM).where(TaskORM.id == str(task_id))
        if tenant_id is not None:
            statement = statement.where(self.tenant_criteria(str(tenant_id)))
        outcome = cast(
            CursorResult[Any],
            await self.session.execute(
                statement.values(
                    progress=int(progress),
                    version=TaskORM.version + 1,
                ).execution_options(synchronize_session=False)
            ),
        )
        return outcome.rowcount == 1

    async def update_step(
        self,
        step_id: str,
        *,
        status: str,
        result_json: str | None = None,
        error_json: str | None = None,
    ) -> bool:
        """更新一个 DAG 步骤（`docs/02` §50 / §52；`docs/07` §4.3 #20）。

        ⚠️ `task_steps` **没有** `version` 列（`docs/07` §4.3 #20），故条件更新只按
        `id` 判定（影响 0 行 = 该步骤不存在）。

        Returns:
            `True` 表示影响 1 行；`False` 表示该步骤不存在。
        """
        values: dict[str, Any] = {"status": str(status)}
        if result_json is not None:
            values["result_json"] = str(result_json)
        if error_json is not None:
            values["error_json"] = str(error_json)
        outcome = cast(
            CursorResult[Any],
            await self.session.execute(
                sa_update(TaskStepORM)
                .where(TaskStepORM.id == str(step_id))
                .values(**values)
                .execution_options(synchronize_session=False)
            ),
        )
        return outcome.rowcount == 1

    # ===== 内部 =====

    async def _conditional_update(
        self,
        task_id: str,
        *,
        expected: str,
        values: Mapping[str, Any],
    ) -> bool:
        """`transition` 的单条条件 `UPDATE`（`docs/02` §12 的乐观并发口径）。"""
        outcome = cast(
            CursorResult[Any],
            await self.session.execute(
                sa_update(TaskORM)
                .where(
                    TaskORM.id == str(task_id),
                    TaskORM.status == str(expected),
                )
                .values(**values, version=TaskORM.version + 1)
                .execution_options(synchronize_session=False)
            ),
        )
        return outcome.rowcount == 1

    async def _fresh(self, task_id: str, *, tenant_id: str | None = None) -> TaskORM | None:
        """按主键读回**最新**的 ORM 行（强制刷新，见类 docstring）。

        Args:
            task_id: 任务标识。
            tenant_id: 给了就额外限制租户（`docs/02` §11）；缺省只按主键
                （`acquire_lease` 的回读路径没有租户上下文 —— 调用方刚刚拿到该行的租约）。
        """
        stmt = select(TaskORM).where(TaskORM.id == str(task_id))
        if tenant_id is not None:
            stmt = stmt.where(self.tenant_criteria(tenant_id))
        result = await self.session.execute(stmt.execution_options(populate_existing=True))
        return result.scalar_one_or_none()


def build_task_store(session: AsyncSession) -> TaskStoreRepository:
    """为一个会话装配任务存储（`docs/02` §33 / §123）。

    Args:
        session: 已存在的 `AsyncSession`（通常由 P06 `UnitOfWork` 提供）。

    Returns:
        `TaskStoreRepository`：绑定该会话，因此与同会话的其他仓储共享同一事务
        —— 状态推进 / 租约 / 进度的可见性由调用方的 `UnitOfWork` 决定。

    ⚠️ 本函数**不**开事务、**不**提交、**不**建立连接（`docs/02` §16；`docs/07` §14.4）。
    签名与 `build_idempotency_store(session: AsyncSession)` 同风格（会话级装配）。
    """
    return TaskStoreRepository(session)


def _as_utc(value: datetime) -> datetime:
    """把数据库读回的时间统一为**带时区**的 UTC（见类 docstring 的时间口径）。

    Args:
        value: `DateTime(timezone=True)` 列的值（SQLite 上可能是 naive）。

    Returns:
        带 `UTC` 时区的同一时刻；已是带时区的值按同一时刻换算。
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _as_utc_optional(value: datetime | None) -> datetime | None:
    """`_as_utc` 的可空版本。"""
    return None if value is None else _as_utc(value)


def _to_record(row: TaskORM) -> TaskRecord:
    """ORM 行 → Domain 记录（只映射契约里的列；时间一律补 `UTC`）。"""
    return TaskRecord(
        id=str(row.id),
        tenant_id=str(row.tenant_id),
        request_id=str(row.request_id),
        trace_id=str(row.trace_id),
        tool=str(row.tool),
        operation=str(row.operation),
        status=str(row.status),
        created_at=_as_utc(row.created_at),
        project_id=None if row.project_id is None else str(row.project_id),
        progress=int(row.progress),
        retry_count=int(row.retry_count),
        max_retries=int(row.max_retries),
        cancel_requested=bool(row.cancel_requested),
        lease_owner=None if row.lease_owner is None else str(row.lease_owner),
        lease_until=_as_utc_optional(row.lease_until),
        heartbeat_at=_as_utc_optional(row.heartbeat_at),
        priority=int(row.priority),
        error_json=None if row.error_json is None else str(row.error_json),
        result_json=None if row.result_json is None else str(row.result_json),
        started_at=_as_utc_optional(row.started_at),
        completed_at=_as_utc_optional(row.completed_at),
        version=int(row.version),
    )


def _to_step_record(row: TaskStepORM) -> TaskStepRecord:
    """ORM 行 → Domain 步骤记录（只映射契约里的列）。"""
    return TaskStepRecord(
        id=str(row.id),
        task_id=str(row.task_id),
        step_key=str(row.step_key),
        operation=str(row.operation),
        status=str(row.status),
        parameters_json=str(row.parameters_json),
        depends_on_json=str(row.depends_on_json),
        result_json=None if row.result_json is None else str(row.result_json),
        error_json=None if row.error_json is None else str(row.error_json),
    )
