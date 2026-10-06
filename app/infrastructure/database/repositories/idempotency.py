"""幂等记录持久化（`docs/07` §12 P21 / §10.3；`docs/02` §28 / §31–§35）。

为什么需要这个模块
------------------
P21 的 Application 层服务（`app/application/execution/idempotency.py`）**不得**依赖
`app.infrastructure`（`docs/07` §14.1 / §2.2），而「原子 `INSERT` 抢占 + 冲突回读」
必须落在 `idempotency_records` 表上。故本模块把「需要什么」实现为 Domain 侧的结构化
契约 `app.domain.protocols.IdempotencyStore`（P09 的 `SchemaLookup`、P10–P13 的
`SecurityStores`、P14–P18 的 `ResourceStore` 是同一做法的先例）。

🔴 原子性（`docs/07` §10.3；`docs/02` §28 / §32 / §35）
-------------------------------------------------------
`docs/02` §35 明列**禁止**的写法与后果：

    Request A → SELECT   （不存在）
    Request B → SELECT   （不存在）
    A → INSERT
    B → INSERT           ← 两条记录 / 两次执行

正确写法（§28 / §32 / §35 的一致口径）：

    Atomic Insert → Unique Conflict → Return Existing Result

因此 `reserve()` 的实现是：**直接 `INSERT`**（唯一键 `UNIQUE(tenant_id,
idempotency_key)` 由**数据库约束**保证，`docs/02` §28 / §31），捕获
`IntegrityError` 后**回读**既有记录并返回 `created=False`。
**没有**任何「先 `SELECT` 判断存在性」的分支。

落地补充（只提供实现手段，不改变任何字段名 / 类型 / 语义）
----------------------------------------------------------
1. **`SAVEPOINT` 而不是回滚整个事务**：`INSERT` 被唯一约束拒绝时，SQLite / PostgreSQL
   都会把当前语句所在的事务标记为「需要回滚」。若直接 `rollback()`，会连带丢弃调用方
   在同一 `UnitOfWork` 里已经做过的其他写操作（事务边界归 `UnitOfWork`，
   `docs/02` §16；`docs/07` §14.4）。故本模块把 `INSERT` 包在
   `session.begin_nested()`（= `SAVEPOINT`）里：冲突只回滚到保存点，
   **外层事务继续可用**，随后在同一事务内回读既有记录。
   SQL 级证据：`SAVEPOINT` → `INSERT INTO idempotency_records …` →
   `ROLLBACK TO SAVEPOINT` → `SELECT …`，**没有** `SELECT` 先于 `INSERT`。
2. **冲突回读失败即原样上抛**：若回读拿不到记录（理论上只有「唯一约束冲突的同时该行被
   并发删除」才可能），说明约束与读取口径不一致，本模块**不**掩盖它 ——
   裸 `raise` 让原始 `IntegrityError` 继续向上，交由兜底错误处理
   （`docs/07` §14.4：不允许「带病继续」）。
3. **`complete()` 只写一次**：`UPDATE … WHERE id = :id AND response_json IS NULL`。
   `docs/02` §28 的 `complete(record_id, response)` 没有写条件，但幂等的语义是
   「首次成功执行的响应快照」（`docs/02` §64），后到的覆盖会让**先前的重放**与
   **之后的重放**返回不同结果。故本模块拒绝覆盖已写入的响应（返回 `False`），
   未完成（`response_json IS NULL`）的记录仍可正常完成。
4. **租户是读取的一部分**：`existing()` / `reserve()` 一律带 `tenant_id`
   （`docs/02` §31：Key 必须与 tenant 绑定），**不存在**「不过滤租户」的读法。

5. **`SAVEPOINT` 之前必须先确保「事务真的开始了」**（本批实测得出的修正）：
   pysqlite 只在遇到 DML 时才隐式 `BEGIN`；若本次会话的第一条语句就是 `SAVEPOINT`，
   它便成为**最外层**保存点，而 SQLite 规定「由 `SAVEPOINT` 开启的事务在被 `RELEASE`
   时即提交」—— 那会让一次「抢占」**替调用方 `commit`**，直接违反 `docs/02` §16 的
   「只有 `UnitOfWork` 能 commit / rollback」（实测：抢占后回滚，行仍留在库里）。
   故 `reserve()` 先问清驱动层的事实（`sqlite3.Connection.in_transaction`），
   必要时显式 `BEGIN`（`_ensure_real_transaction`）。**不改引擎层配置** ——
   全局打开显式事务会让只读会话持有 SHARED 锁，使「两读一写」的并发场景在 SQLite 上
   直接 `database is locked`（P05 的乐观并发用例即如此），那是 P29–P35 / P36 的
   基础设施议题（见 `docs/07` §16 R40）。非 SQLite 后端没有 `in_transaction`
   属性 → 直接跳过（PostgreSQL 等的事务总是真实的）。

红线（`docs/07` §14.1 / §14.3 / §14.4）
---------------------------------------
- 只做 persistence：**不**做幂等判定、**不**做冲突判定（判定在 Application 层）；
- 全部方法**绝不** `commit` / `rollback`（事务边界归 P06 `UnitOfWork`）；
- **不得**改表：只使用 P04 已落地的 `idempotency_records`（`docs/07` §4.3 #23）；
- 记录里**不含**任何 secret（`request_hash` 是 SHA-256 摘要、`response_json` 是业务响应）；
- 不出现任何厂商专属内容。
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import CursorResult, select, text
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.protocols import IdempotencyRecord, IdempotencyReservation
from app.infrastructure.database.models import IdempotencyRecordORM

__all__ = ["IdempotencyStoreRepository", "build_idempotency_store"]


class IdempotencyStoreRepository:
    """`IdempotencyStore` 的 SQLAlchemy 实现（`docs/02` §28 / §34 / §35）。

    ⚠️ 唯一写入口是 `reserve()`（原子 `INSERT`）与 `complete()`（一次性响应写入）；
    两者都**不** `commit` / `rollback`（`docs/07` §14.4）。
    """

    def __init__(self, session: AsyncSession) -> None:
        """绑定一个已存在的会话（`docs/02` §16：会话由上层 / `UnitOfWork` 提供）。"""
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """当前会话（只读用途；事务边界不在此处决定）。"""
        return self._session

    # ===== 契约：`docs/02` §28（reserve / complete）+ §34 / §35 =====

    async def reserve(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> IdempotencyReservation:
        """原子抢占一个幂等键（`docs/02` §28 / §32 / §35；`docs/07` §10.3）。

        **直接 `INSERT`**，不做任何存在性预查；唯一键冲突时回读既有记录。

        Args:
            tenant_id: 租户标识；幂等键与租户绑定（`docs/02` §31）。
            idempotency_key: 客户端提交的幂等键（`docs/02` §31）。
            request_hash: 请求摘要（`docs/02` §32 / §33）。

        Returns:
            `IdempotencyReservation`：`created=True` 表示本次抢占成功（记录刚插入、
            `response_json` 为 `None`）；`created=False` 表示命中既有记录（冲突回读）。

        Raises:
            ValueError: `tenant_id` / `idempotency_key` / `request_hash` 为空
                （装配 / 调用错误，不静默接受）。
            IntegrityError: 唯一键冲突**且**回读不到既有记录（见模块裁决 2）。
        """
        tenant = self._require(tenant_id, "tenant_id")
        key = self._require(idempotency_key, "idempotency_key")
        digest = self._require(request_hash, "request_hash")

        # 见模块裁决 5：先确保事务真的开始，`SAVEPOINT` 才是嵌套的。
        await self._ensure_real_transaction()

        row = IdempotencyRecordORM(
            tenant_id=tenant,
            idempotency_key=key,
            request_hash=digest,
            response_json=None,
        )
        try:
            # `SAVEPOINT`：冲突只回滚到这里，外层事务（`UnitOfWork`）继续可用。
            async with self._session.begin_nested():
                self._session.add(row)
                await self._session.flush()
        except IntegrityError:
            # `docs/02` §35：捕获 `IntegrityError` → 重新读取已有记录。
            existing = await self.existing(tenant_id=tenant, idempotency_key=key)
            if existing is None:
                raise  # 见模块裁决 2：不掩盖口径不一致
            return IdempotencyReservation(record=existing, created=False)

        return IdempotencyReservation(record=_to_record(row), created=True)

    async def _ensure_real_transaction(self) -> None:
        """确保底层连接真的处在一个 SQLite 事务里（见模块裁决 5）。

        ⚠️ 本方法**不**决定事务何时提交 / 回滚（那是 `UnitOfWork` 的职责）——
        它只保证「事务已经开始」，使随后的 `SAVEPOINT` 是**嵌套**的，
        而不是「最外层保存点」（后者会在 `RELEASE` 时提交整个事务）。
        """
        connection = await self._session.connection()
        raw = await connection.get_raw_connection()
        driver = getattr(raw, "driver_connection", None)
        if getattr(driver, "in_transaction", None) is False:
            await self._session.execute(text("BEGIN"))

    async def existing(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
    ) -> IdempotencyRecord | None:
        """按 `(tenant_id, idempotency_key)` 读取既有记录（`docs/02` §34）。

        ⚠️ 这是**只读**入口（`docs/02` §34 的 `check` 用它）。它**不是**抢占路径：
        抢占**必须**走 `reserve()` 的原子 `INSERT`（`docs/02` §35），
        任何「先 `existing()` 判断不存在再 `reserve()`」的写法都是被禁止的
        `SELECT → INSERT` 竞态。

        Returns:
            命中的记录；不存在返回 `None`（不抛异常）。
        """
        tenant = self._require(tenant_id, "tenant_id")
        key = self._require(idempotency_key, "idempotency_key")
        result = await self._session.execute(
            select(IdempotencyRecordORM).where(
                IdempotencyRecordORM.tenant_id == tenant,
                IdempotencyRecordORM.idempotency_key == key,
            )
        )
        row = result.scalar_one_or_none()
        return None if row is None else _to_record(row)

    async def complete(self, record_id: str, response_json: str) -> bool:
        """写入首次成功执行的响应快照（`docs/02` §28 / §64）。

        `UPDATE … WHERE id = :id AND response_json IS NULL`：只完成**尚未完成**的记录，
        已写入的响应**不可覆盖**（见模块裁决 3）。

        Args:
            record_id: `reserve()` 返回的记录 id。
            response_json: 响应快照的 JSON 文本（序列化在 Application 层完成）。

        Returns:
            `True` 表示本次确实写入了响应；`False` 表示该记录不存在，
            或已有响应（两种情况**不做区分** —— 都不改变既有数据）。

        ⚠️ 只 `UPDATE`，**不** `commit`（`docs/07` §14.4）。
        """
        outcome = cast(
            CursorResult[Any],
            await self._session.execute(
                sa_update(IdempotencyRecordORM)
                .where(
                    IdempotencyRecordORM.id == self._require(record_id, "record_id"),
                    IdempotencyRecordORM.response_json.is_(None),
                )
                .values(response_json=response_json)
                .execution_options(synchronize_session=False)
            ),
        )
        return outcome.rowcount == 1

    @staticmethod
    def _require(value: str, name: str) -> str:
        """必填参数校验（空值即拒绝；`docs/02` §31 的键必须真实存在）。"""
        if not value:
            raise ValueError(f"{name} is required for idempotency records")
        return str(value)


def _to_record(row: IdempotencyRecordORM) -> IdempotencyRecord:
    """ORM 行 → Domain 记录（只映射契约里的五列）。"""
    return IdempotencyRecord(
        id=str(row.id),
        tenant_id=str(row.tenant_id),
        idempotency_key=str(row.idempotency_key),
        request_hash=str(row.request_hash),
        response_json=None if row.response_json is None else str(row.response_json),
    )


def build_idempotency_store(session: AsyncSession) -> IdempotencyStoreRepository:
    """为一个会话装配幂等记录存储（`docs/02` §33 / §123）。

    Args:
        session: 已存在的 `AsyncSession`（通常由 P06 `UnitOfWork` 提供）。

    Returns:
        `IdempotencyStoreRepository`：绑定该会话，因此与同会话的其他仓储共享同一事务
        —— 「抢占」与「执行」的可见性由调用方的 `UnitOfWork` 决定。

    ⚠️ 本函数**不**开事务、**不**提交、**不**建立连接（`docs/02` §16；`docs/07` §14.4）。
    """
    return IdempotencyStoreRepository(session)
