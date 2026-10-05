"""UnitOfWork —— 唯一的事务边界（`docs/02` §16；`docs/07` §12 P06 / §14.4）。

权威来源
--------
- `docs/02` §16（`source9`）—— `app/infrastructure/database/unit_of_work.py` 的
  `UnitOfWork(session)`：`__aenter__` 返回自身；`__aexit__` 正常退出 → `commit`，
  异常退出 → `rollback`；另有显式 `commit` / `rollback`。
- `docs/02` §16（`source7`）—— 同一文件的 `SQLAlchemyUnitOfWork(session_factory)`：
  由会话工厂创建会话、退出时 `close()`。本实现以
  `UnitOfWork.from_session_factory(session_factory)` 覆盖该口径（不新造第二个类）。
- `docs/02` §11（`blue`）—— Domain 契约 `app.domain.protocols.UnitOfWork` 只暴露
  `commit` / `rollback`；**上下文管理与 `close` 由本实现负责**（P03 已冻结该契约）。
- `docs/02` §42 / §43 —— Commit Test / Rollback Test：提交后新会话可见；
  回滚（异常或显式）后新会话不可见。
- `docs/07` §12 P06 —— 门槛「事务测试通过」，内容 = `commit` / `rollback` / `close`。
- `docs/02` §35（Transaction Boundary）—— 推荐用法
  `async with unit_of_work: ... await unit_of_work.commit()`：显式 `commit()` 之后
  正常退出**不得**报错（`__aexit__` 的提交对已提交事务是幂等的）。
- `docs/02` §126（Database Transaction Rules）—— 数据库事务不得包住长时间 Native API
  调用，故 UoW 的作用域必须是**短事务**。

事务边界（`docs/02` §16）
------------------------
    Application Service → UnitOfWork → Repository → SQLAlchemy

**只有本类决定何时 `commit` / `rollback`**（`docs/07` §14.4）；Repository 只 `flush`。
本模块是全项目唯一允许出现 `commit` / `rollback` 的模块。

会话所有权（两种构造方式）
--------------------------
1. `UnitOfWork(session)` —— 包装调用方已开的会话（`source9` §16；也是
   `build_repositories(session)` 绑定的那个会话）。**不**在退出时关闭它：
   会话所有权仍在调用方，典型写法

       async with session_factory() as session:
           async with UnitOfWork(session) as uow:
               ...

   需要提前释放会话 / 归还连接时显式 `await uow.close()`。
2. `UnitOfWork.from_session_factory(session_factory)` —— 会话由本类创建
   （`source7` §16 的 `SQLAlchemyUnitOfWork`）；退出时 `close()`，连接归还连接池。

异常语义（P06 门槛 ②）
----------------------
`__aexit__` **不吞异常、也不替换异常**：异常路径先 `rollback()`，再返回 `None`，
原异常对象沿调用栈继续向上抛（`BaseException` 亦如此，如 `asyncio.CancelledError`）。

禁止项（`docs/07` §14.3 / §14.4）：本模块不建表、不改表，不记录任何 secret。
"""

from __future__ import annotations

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

__all__ = ["UnitOfWork"]


class UnitOfWork:
    """一个业务事务 = 一个明确 UnitOfWork（`docs/02` §16）。

    同时满足 `app.domain.protocols.UnitOfWork`（`commit` / `rollback`）与
    `docs/02` §16 的 `SQLAlchemyUnitOfWork`（上下文管理 + `close`）。

    ⚠️ 会话是**短生命周期**对象：本类不得被放进进程级容器或全局单例
    （`docs/02` §33；`app.container` 只持有 `session_factory`）。
    """

    session: AsyncSession
    """本工作单元绑定的会话；同一 UoW 内的全部仓储必须绑定这**同一个**会话。"""

    def __init__(self, session: AsyncSession) -> None:
        """包装调用方提供的会话（`docs/02` §16，`source9`）。

        Args:
            session: 已存在的 `AsyncSession`；所有权仍在调用方，
                `__aexit__` 不会关闭它。
        """
        self.session = session
        self._owns_session = False

    @classmethod
    def from_session_factory(
        cls,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> UnitOfWork:
        """由会话工厂创建会话（`docs/02` §16，`source7` 的 `SQLAlchemyUnitOfWork`）。

        与 `UnitOfWork(session)` 的区别只在**所有权**：会话由本类创建，
        因此 `__aexit__` 与 `close()` 都会关闭它，把连接归还连接池。

        会话对象本身不持有连接（SQLAlchemy 会话惰性获取连接），
        故本构造方法不产生数据库 I/O。

        Args:
            session_factory: `create_session_factory(engine)` 的产物（P04）。

        Returns:
            绑定新会话的 `UnitOfWork`。
        """
        unit_of_work = cls(session_factory())
        unit_of_work._owns_session = True
        return unit_of_work

    # ===== 上下文管理（`docs/02` §16；门槛 ②）=====

    async def __aenter__(self) -> Self:
        """进入工作单元；不开启额外事务（事务由会话首次使用时自动开始）。"""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """退出工作单元：正常退出 → `commit`；异常退出 → `rollback`。

        - 返回 `None` 表示**不抑制**异常：原异常对象继续向上抛（不吞、不替换）。
        - 由本类创建的会话（`from_session_factory`）在此一并 `close()`。
        - 已显式 `commit()` 过的事务再次提交是幂等的（`docs/02` §35 的用法）。
        """
        if exc_type is not None:
            await self.rollback()
        else:
            await self.commit()

        if self._owns_session:
            await self.close()

    # ===== 契约：`app.domain.protocols.UnitOfWork` =====

    async def commit(self) -> None:
        """提交当前事务（`docs/02` §11 / §16）。

        ⚠️ 这是**唯一**允许提交数据库事务的地方（`docs/07` §14.4）。
        """
        await self.session.commit()

    async def rollback(self) -> None:
        """回滚当前事务（`docs/02` §11 / §16）。

        回滚后会话仍可继续使用（SQLAlchemy 在下次使用时自动开始新事务），
        因此 `__aexit__` 的异常路径不会让调用方「拿到一个坏掉的会话」。
        """
        await self.session.rollback()

    # ===== 会话释放（`docs/07` §12 P06：close）=====

    async def close(self) -> None:
        """关闭会话并把连接归还连接池（`docs/07` §12 P06；`docs/02` §80）。

        - 会话中未提交的变更随关闭一起丢弃（SQLAlchemy 语义：等价于回滚）。
        - 幂等：重复 `close()` 安全。
        - 调用本方法后不得继续使用本 UoW；`await engine.dispose()` 时不再有
          未归还的连接（无泄漏）。
        """
        await self.session.close()
