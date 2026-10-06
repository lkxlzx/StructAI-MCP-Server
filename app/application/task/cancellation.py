"""Application · Task · Cancellation（`docs/07` §10.2 / §12 P22–P28）。
覆盖 `docs/02` §28–§30 / §43 / §53 / §79 的取消语义。

权威来源
--------
- `docs/02` §43（`task`）—— `CANCEL_REQUESTED` 之后调 `Adapter.cancel()`；**成功**才
  `CANCELLED`，**不支持**则「保持真实 native state」。
- `docs/02` §30（`task`）—— 「Cancellation 必须真实」：软件不支持真正取消时
  `cannot cancel native operation`（本模块常量逐字照抄），**不要伪造** `CANCELLED`，
  必须保持 `CANCEL_REQUESTED`（或 `RECOVERING`），最终真实状态必须可追踪。
- `docs/02` §53（`task`）—— `cancel(task_id)` 的原文形态：
  `task.status = CANCEL_REQUESTED` → `await adapter.cancel(task_id)`。
- `docs/02` §79（Cancellation Test）—— `RUNNING` 发 cancel → `CANCEL_REQUESTED`；
  Adapter 支持 → `CANCELLED`；不支持 → `CANCEL_REQUESTED`。
- `docs/07` §10.2 —— `MCP Cancel → TaskEngine.cancel() → CANCEL_REQUESTED →
  Adapter.cancel() → CANCELLED`；**不得杀 Python 进程，不得伪造 `CANCELLED`**。
- `docs/07` §14.4 —— 取消**不得**杀 Python 进程；也不得把恢复中的任务标记 `COMPLETED`。
- `docs/07` §11 —— `STRUCTAI-5000`（任务不存在）、`STRUCTAI-6000`（Adapter 内部错误，
  本模块的兜底归一化码）、`STRUCTAI-1300`（非法转移，经 `TaskStateError`）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **「能不能取消」由冻结的转移表判定，不另写一份规则**：`CANCEL_REQUESTED` 不在
   `ALLOWED_TRANSITIONS[current]` 内即抛 `TaskStateError`（`STRUCTAI-1300`）。
   这样 `COMPLETED` / `CANCELLED` / `FAILED` / `TIMEOUT` / `RECOVERING` / `RETRYING` /
   `CANCEL_REQUESTED` 七种「不可取消」状态**自动**被拒，无需在此重复列举
   （`docs/07` §10.1：状态机必须集中实现，不得散落）。
2. **未执行的任务直接 `CANCELLED`**：`CREATED` / `VALIDATING` / `QUEUED` 还没进入执行，
   不存在「native 操作」需要停 —— 故直接 CAS 到 `CANCELLED` 并**不**调 Adapter
   （`docs/02` §7 / §8 的转移表允许这三条边）。`reason = "not_running"`。
3. **CAS 失败一律返回真实状态**：`CANCEL_REQUESTED` 的 CAS 失败说明状态已被别人推进，
   本模块**不**覆盖、**不**重试、**不**伪造结果 —— 返回
   `cancelled=False, reason="state_changed", status=<当前真实状态>`（`docs/07` §14.4）。
4. **Adapter 失败时保持 `CANCEL_REQUESTED` 并把归一化错误写入 `error_json`**：
   `docs/02` §30 要求「最终真实状态必须可追踪」。故把异常 `to_dict()` 的 JSON 落
   `tasks.error_json`（**只**放 20 码信封：`code` / `type` / `message` / `details` /
   `retryable`），**不**放原生 message（`docs/07` §14.3 / §14.4）。
   非 `StructAIError` 的兜底码取 **`STRUCTAI-6000`**（`docs/07` §11 的 `Adapter Error`，
   Adapter 内部错误；`docs/07` §14.4 的「不允许带病继续」要求**不**静默吞掉异常）。
5. **绝不杀进程**：本模块**不** import `os` / `signal` / `subprocess`，源码里没有
   `os.kill` / `signal.` / `SIGKILL` / `terminate()`。取消只是**请求**：
   真正的终止由 Adapter 自己决定，Core 不替它动手（`docs/07` §14.4）。
6. **Adapter 端口是收窄契约**：`AdapterCancellation.cancel(software_instance_id, task_id)`
   与 `AdapterManager.cancel(instance_id, task_id)` **结构上**一致
   （`app/infrastructure/adapters/base/manager.py`），但 Application 层**不得** import
   `app.infrastructure`（`docs/07` §14.1 / §2.2），故这里声明 Protocol 而非引用实现
   （P14–P18 R38 的同一做法）。
7. **`CancellationOutcome.error_code` 只放归一化后的 20 码**：**不**放原生 message，
   也**不**回显任务 / 实例标识以外的任何内容（`docs/07` §14.3）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，
**不**依赖 `app.infrastructure`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final, Protocol

from app.application.task.state_machine import TaskStateError
from app.domain.enums import TaskStatus
from app.domain.errors import AdapterError, StructAIError, TaskError
from app.domain.protocols import TaskRecord, TaskStore

__all__ = [
    "CANCELLATION_STAGE",
    "NON_CANCELLABLE_STATUSES",
    "CANCEL_UNSUPPORTED_MESSAGE",
    "FALLBACK_CANCELLATION_CODE",
    "AdapterCancellation",
    "CancellationOutcome",
    "CancellationService",
]

CANCELLATION_STAGE: Final[str] = "cancellation"
"""错误 `details.stage` 的固定取值（与 `state_machine` / `lease` 同口径）。"""

CANCEL_UNSUPPORTED_MESSAGE: Final[str] = "cannot cancel native operation"
"""软件不支持真正取消时的对外消息（`docs/02` §30 原文，逐字照抄）。"""

FALLBACK_CANCELLATION_CODE: Final[str] = AdapterError.code
"""非 `StructAIError` 异常的兜底归一化码（`STRUCTAI-6000`；见模块裁决 4）。"""

CANCEL_NOT_RUNNING: Final[str] = "not_running"
"""未执行任务被直接取消的 `reason`（见模块裁决 2）。"""

CANCEL_UNSUPPORTED: Final[str] = "cancel_unsupported"
"""取消未被真正执行时的 `reason`（`docs/02` §30；见模块裁决 4）。"""

CANCEL_STATE_CHANGED: Final[str] = "state_changed"
"""CAS 失败（状态已被别人推进）时的 `reason`（见模块裁决 3）。"""

NON_CANCELLABLE_STATUSES: Final[frozenset[TaskStatus]] = frozenset(
    {
        TaskStatus.COMPLETED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
        TaskStatus.TIMEOUT,
        TaskStatus.RECOVERING,
        TaskStatus.RETRYING,
        TaskStatus.CANCEL_REQUESTED,
    }
)
"""**不可取消**的状态集合（见模块裁决 1；`docs/02` §30 / §43 / §79）。

⚠️ 这里用**显式集合**而不是「`CANCEL_REQUESTED` 是否在冻结转移表里」：`CREATED` /
`VALIDATING` 的转移表**没有** `CANCEL_REQUESTED` 出边（只有 `CANCELLED`），
但它们**确实**可取消 —— 只是走「直接 `CANCELLED`」而不是「先请求取消」
（见模块裁决 2）。用转移表判定会把这两态误判为不可取消。
"""


class AdapterCancellation(Protocol):
    """取消端口（`docs/02` §53 的 `await adapter.cancel(task_id)`）。

    ⚠️ Application 层**不得** import `app.infrastructure`（`docs/07` §14.1 / §2.2），
    故这里声明**结构契约**：`AdapterManager.cancel(instance_id, task_id)` 在结构上
    即满足它（`docs/02` §51）。见模块裁决 6。

    🔴 实现**必须**只向软件发出取消请求：**不得**杀 Python 进程，也**不得**在软件
    不支持时假装成功（`docs/02` §30；`docs/07` §14.4）。
    """

    async def cancel(self, software_instance_id: str, task_id: str) -> None:
        """请求取消该实例上的任务（`docs/02` §53）。"""
        ...


@dataclass(frozen=True, slots=True)
class CancellationOutcome:
    """一次取消尝试的结果（`docs/02` §79 的三条分支）。

    Attributes:
        task_id: 任务标识。
        status: **真实**状态 —— 成功是 `CANCELLED`；未执行的任务直接 `CANCELLED`；
            软件不支持时**保持** `CANCEL_REQUESTED`；CAS 失败时是被别人推进后的状态。
        cancelled: 是否**确实**到达 `CANCELLED`（软件不支持时恒为 `False`）。
        reason: `""` / `"not_running"` / `"cancel_unsupported"` / `"state_changed"`。
        error_code: 归一化后的 20 码（**不**放原生 message —— 见模块裁决 7）；
            正常路径为 `None`。
    """

    task_id: str
    status: TaskStatus
    cancelled: bool
    reason: str
    error_code: str | None = None


class CancellationService:
    """任务取消（`docs/02` §28–§30 / §43 / §53 / §79；`docs/07` §10.2）。

    ⚠️ 持久化经 Domain 契约 `TaskStore` 注入：本模块**不**依赖 `app.infrastructure`
    （`docs/07` §14.1）。事务边界归调用方的 `UnitOfWork`（`docs/02` §16）——
    本类**从不** `commit` / `rollback`。
    """

    def __init__(self, store: TaskStore, cancellation: AdapterCancellation | None = None) -> None:
        """绑定任务存储与可选取消端口。

        Args:
            store: `docs/02` §34 的持久化入口（`get` / `transition`）。
            cancellation: 取消端口（`docs/02` §53）；缺省 `None` 表示本进程没有可用的
                Adapter —— 此时 `RUNNING` / `PROCESSING` 的任务**保持** `CANCEL_REQUESTED`
                （见模块裁决 4）。
        """
        self._store = store
        self._cancellation = cancellation

    @property
    def store(self) -> TaskStore:
        """被绑定的存储（只读用途）。"""
        return self._store

    @property
    def cancellation(self) -> AdapterCancellation | None:
        """被绑定的取消端口（只读用途；缺省 `None`）。"""
        return self._cancellation

    async def cancel(
        self,
        task_id: str,
        tenant_id: str,
        *,
        software_instance_id: str | None = None,
    ) -> CancellationOutcome:
        """取消一个任务（`docs/02` §30 / §43 / §79；`docs/07` §10.2）。

        Args:
            task_id: 任务标识。
            tenant_id: 租户标识（`docs/02` §11：读取必须同时限制租户）。
            software_instance_id: 目标软件实例；缺省 `None` 表示无实例可通知。

        Returns:
            `CancellationOutcome`：**真实**状态 + 是否确实取消 + `reason`
            （见 `CancellationOutcome` 的字段说明）。

        Raises:
            TaskError: `STRUCTAI-5000` —— 任务不存在（`details.reason = "unknown_task"`）。
            TaskStateError: `STRUCTAI-1300` —— 该状态**不可取消**（终态 / `RECOVERING` /
                `RETRYING` / `CANCEL_REQUESTED`）；**拒绝**而不静默忽略，也**不**伪造
                `CANCELLED`（`docs/02` §30；见模块裁决 1）。
        """
        task = await self._store.get(task_id, tenant_id)
        if task is None:
            raise TaskError(
                "Task not found",
                details={"stage": CANCELLATION_STAGE, "reason": "unknown_task"},
            )

        current = _status_of(task)
        if current in NON_CANCELLABLE_STATUSES:
            # 见模块裁决 1：不可取消的状态一律拒绝（状态机是唯一判定点）。
            raise TaskStateError(
                f"Invalid transition: {current} -> {TaskStatus.CANCEL_REQUESTED}",
                details={
                    "stage": CANCELLATION_STAGE,
                    "from": str(current),
                    "to": str(TaskStatus.CANCEL_REQUESTED),
                },
            )

        if current is not TaskStatus.RUNNING and current is not TaskStatus.PROCESSING:
            # 见模块裁决 2：还没在执行 → 直接 CANCELLED，**不**调 Adapter。
            return await self._cancel_without_running(task_id, tenant_id, current)

        # `RUNNING` / `PROCESSING`：先请求取消，再尝试真正取消。
        requested = await self._store.transition(
            task_id,
            expected=str(current),
            new=str(TaskStatus.CANCEL_REQUESTED),
            fields={"cancel_requested": True},
        )
        if not requested:
            latest = await self._store.get(task_id, tenant_id)
            return CancellationOutcome(
                task_id=task_id,
                status=_status_of(latest) if latest is not None else TaskStatus.CANCEL_REQUESTED,
                cancelled=False,
                reason=CANCEL_STATE_CHANGED,
            )

        if self._cancellation is None or not software_instance_id:
            # 见模块裁决 4：没有端口就**保持** CANCEL_REQUESTED（真实状态可追踪）。
            return CancellationOutcome(
                task_id=task_id,
                status=TaskStatus.CANCEL_REQUESTED,
                cancelled=False,
                reason=CANCEL_UNSUPPORTED,
            )

        try:
            await self._cancellation.cancel(software_instance_id, task_id)
        except StructAIError as error:
            return await self._keep_cancel_requested(task_id, error)
        except Exception as error:  # noqa: BLE001 —— 兜底归一化，见模块裁决 4
            return await self._keep_cancel_requested(
                task_id,
                AdapterError(
                    CANCEL_UNSUPPORTED_MESSAGE,
                    details={"stage": CANCELLATION_STAGE, "reason": CANCEL_UNSUPPORTED},
                    cause=error,
                ),
            )

        # 软件确认已取消 → 才落 CANCELLED（`docs/02` §30：不得伪造）。
        confirmed = await self._store.transition(
            task_id,
            expected=str(TaskStatus.CANCEL_REQUESTED),
            new=str(TaskStatus.CANCELLED),
        )
        if not confirmed:
            latest = await self._store.get(task_id, tenant_id)
            return CancellationOutcome(
                task_id=task_id,
                status=_status_of(latest) if latest is not None else TaskStatus.CANCEL_REQUESTED,
                cancelled=False,
                reason=CANCEL_STATE_CHANGED,
            )
        return CancellationOutcome(
            task_id=task_id,
            status=TaskStatus.CANCELLED,
            cancelled=True,
            reason="",
        )

    # ===== 内部 =====

    async def _cancel_without_running(
        self,
        task_id: str,
        tenant_id: str,
        current: TaskStatus,
    ) -> CancellationOutcome:
        """未执行的任务直接 CAS 到 `CANCELLED`（见模块裁决 2）。

        Raises:
            TaskStateError: `STRUCTAI-1300` —— CAS 失败且状态仍未到达 `CANCELLED`
                （状态已被别人推进；本模块**不**覆盖）。
        """
        cancelled = await self._store.transition(
            task_id,
            expected=str(current),
            new=str(TaskStatus.CANCELLED),
        )
        if cancelled:
            return CancellationOutcome(
                task_id=task_id,
                status=TaskStatus.CANCELLED,
                cancelled=True,
                reason=CANCEL_NOT_RUNNING,
            )
        latest = await self._store.get(task_id, tenant_id)
        status = _status_of(latest) if latest is not None else current
        if status is TaskStatus.CANCELLED:
            return CancellationOutcome(
                task_id=task_id,
                status=TaskStatus.CANCELLED,
                cancelled=True,
                reason=CANCEL_NOT_RUNNING,
            )
        raise TaskStateError(
            f"Invalid transition: {status} -> {TaskStatus.CANCELLED}",
            details={
                "stage": CANCELLATION_STAGE,
                "from": str(status),
                "to": str(TaskStatus.CANCELLED),
            },
        )

    async def _keep_cancel_requested(
        self,
        task_id: str,
        error: StructAIError,
    ) -> CancellationOutcome:
        """保持 `CANCEL_REQUESTED` 并把归一化错误写入 `error_json`（见模块裁决 4）。

        ⚠️ 只写 `error_json`，**不**改状态：真实状态必须可追踪（`docs/02` §30）。
        """
        await self._store.transition(
            task_id,
            expected=str(TaskStatus.CANCEL_REQUESTED),
            new=str(TaskStatus.CANCEL_REQUESTED),
            fields={"error_json": json.dumps(error.to_dict(), ensure_ascii=False, sort_keys=True)},
        )
        return CancellationOutcome(
            task_id=task_id,
            status=TaskStatus.CANCEL_REQUESTED,
            cancelled=False,
            reason=CANCEL_UNSUPPORTED,
            error_code=error.code,
        )


def _status_of(task: TaskRecord) -> TaskStatus:
    """把 `TaskRecord.status` 规整为 `TaskStatus`（`docs/07` §10.1 的 12 态）。

    Raises:
        ValueError: 取值不在 12 态内（数据错误，**不**静默当作某个状态）。
    """
    return TaskStatus(str(task.status))
