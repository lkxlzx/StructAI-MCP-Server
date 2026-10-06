"""Application · Task · DAG（`docs/07` §10.2 / §12 P22–P28；`docs/02` §19 / §46–§51 / §54）。

权威来源
--------
- `docs/02` §46（Task DAG）—— 复杂工程任务不是单一步骤：
  `BUILD.COLUMN → ANALYSIS.STATIC → RESULT.DISPLACEMENT → DESIGN.STEEL`。
- `docs/02` §47（DAG 数据结构）—— `TaskStep(step_id, operation, parameters,
  depends_on=())` 与 `TaskGraph(steps: dict[str, TaskStep])`，逐字段照抄。
- `docs/02` §48（DAG 校验）—— 必须检测 `missing dependency` / `cycle` /
  `duplicate step` / `unknown step`。
- `docs/02` §49（DAG Cycle Detection）—— `validate_dag(graph)` 的**原文实现**：
  `visiting` / `visited` 两集合的 DFS；环 → `ValidationError("Task DAG contains
  cycle")`；依赖缺失 → `ValidationError(f"Unknown dependency: {dependency}")`。
- `docs/02` §50（DAG Scheduling）—— 状态 `PENDING` / `READY` / `RUNNING` /
  `COMPLETED` / `FAILED` / `SKIPPED`；「全部依赖 `COMPLETED` → `READY`」；
  依赖 `FAILED` → 默认 `SKIPPED`，除非显式 `continue_on_failure = true`。
- `docs/02` §51（Parallel DAG）—— 同层步骤可并行，汇聚步骤等待全部前置完成。
- `docs/02` §54 / §19（`docs/07` §10.2 / §14.4）—— 「依赖满足后才能执行」；
  **循环依赖必须在提交前拒绝**（禁止循环依赖的任务提交）。

落地裁决（只补实现手段，不改任何取值）
--------------------------------------
1. **环 / 缺依赖 / 重复 / 未知步骤统一落 `STRUCTAI-1200`**：`docs/02` §49 原文抛
   `ValidationError`，而 20 码契约（`docs/07` §11）里**没有**该码、也**不允许**
   新增码。DAG 校验发生在**任务提交之前**（§19），此时「什么都没做」—— 与
   P14–P18 的 R28 裁决同口径（语义非法 / 前置不满足 → `STRUCTAI-1200`）。
   故统一抛 `EngineeringValidationError`，`details = {stage: "dag", reason: ...}`。
2. **四类缺陷各有 `reason`**（§48 逐条落地）：`duplicate_step`（同 `step_id`
   出现两次）/ `missing_dependency`（`depends_on` 指向的 key 不在图内）/ `cycle`
   （DFS 命中 `visiting`）/ `unknown_step`（步骤的 `operation` 不在调用方给定的
   已登记 Operation 集合内 —— 仅在传入 `known_operations` 时检查）。
3. **`validate_dag` 顺带产出拓扑序**：§49 的原文只做校验。本模块让校验产出
   §82 的执行序（`A → B → C`），使「校验」与「调度」共用**同一次**遍历 ——
   避免出现第二份环判定（`docs/02` §28「只允许一处实现」同理）。
4. **`continue_on_failure` 是内存字段**：§50 的「除非明确配置」需要载体，而
   `task_steps` 表**没有**该列（`docs/07` §4.3 #20，本批**不得改表**），故它只
   存在于 `TaskStep` 上，缺省 `False`（§50 的默认行为）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 SQLAlchemy / FastAPI / MCP SDK /
httpx，**不**依赖 `app.infrastructure`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from app.domain.enums import TaskStepStatus
from app.domain.errors import EngineeringValidationError
from app.domain.protocols import TaskStepDraft

__all__ = [
    "DAG_STAGE",
    "DAG_VALIDATION_REASONS",
    "TERMINAL_STEP_STATUSES",
    "DagPlan",
    "TaskGraph",
    "TaskStep",
    "blocked_steps",
    "graph_from_drafts",
    "ready_steps",
    "step_plan",
    "topological_order",
    "validate_dag",
]

DAG_STAGE: Final[str] = "dag"
"""错误 `details.stage` 的固定取值（与 `state_machine` / `progress` 同口径）。"""

DAG_VALIDATION_REASONS: Final[tuple[str, ...]] = (
    "duplicate_step",
    "missing_dependency",
    "cycle",
    "unknown_step",
)
"""`docs/02` §48 的四类缺陷（逐条照抄，作为 `details.reason` 的词表）。"""

TERMINAL_STEP_STATUSES: Final[frozenset[TaskStepStatus]] = frozenset(
    {
        TaskStepStatus.COMPLETED,
        TaskStepStatus.FAILED,
        TaskStepStatus.SKIPPED,
    }
)
"""步骤终态（`docs/02` §50）：到终态后不再变化。"""


@dataclass(frozen=True, slots=True)
class TaskStep:
    """一个 DAG 节点（`docs/02` §47 逐字段照抄 ＋ 一个内存配置位）。

    Attributes:
        step_id: 步骤键（落 `task_steps.step_key`，`docs/07` §4.3 #20）。
        operation: Operation 名（`docs/02` §24 的规范化标识）。
        parameters: 规范化参数（`docs/02` §24 的 `input_schema` 口径）。
        depends_on: 前置步骤键（`docs/07` §4.3 #20 的 `depends_on`）。
        continue_on_failure: 前置失败时是否继续执行本步骤（`docs/02` §50 的
            「除非明确配置 `continue_on_failure = true`」）；缺省 `False`，
            即前置失败 → 本步骤 `SKIPPED`。见模块裁决 4。
    """

    step_id: str
    operation: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    continue_on_failure: bool = False


@dataclass(frozen=True, slots=True)
class TaskGraph:
    """一张 DAG（`docs/02` §47 的 `TaskGraph(steps: dict[str, TaskStep])`）。"""

    steps: Mapping[str, TaskStep]

    def __len__(self) -> int:
        """步骤数。"""
        return len(self.steps)

    def __contains__(self, step_id: object) -> bool:
        """是否含某步骤键。"""
        return step_id in self.steps

    def step(self, step_id: str) -> TaskStep:
        """取一个步骤。

        Raises:
            EngineeringValidationError: `STRUCTAI-1200`，未知步骤键。
        """
        step = self.steps.get(step_id)
        if step is None:
            raise EngineeringValidationError(
                f"Unknown step: {step_id}",
                details={"stage": DAG_STAGE, "reason": "missing_dependency"},
            )
        return step


@dataclass(frozen=True, slots=True)
class DagPlan:
    """一次调度决策（`docs/02` §50 / §51）。

    - `ready`: 依赖全部 `COMPLETED` 的 `PENDING` 步骤（可并行执行，§51）；
    - `skipped`: 因前置 `FAILED` / `SKIPPED` 且**未**配置 `continue_on_failure`
      而应置 `SKIPPED` 的步骤；
    - `running`: 仍在执行的步骤；
    - `finished`: 已处于终态的步骤。
    """

    ready: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    running: tuple[str, ...] = ()
    finished: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        """是否所有步骤都已到终态（`docs/02` §50）。"""
        return not self.ready and not self.running and not self.skipped

    @property
    def has_failure(self) -> bool:
        """是否存在失败 / 被跳过的步骤（用于决定任务级结果）。"""
        return bool(self.skipped)


def graph_from_drafts(drafts: Iterable[TaskStepDraft]) -> TaskGraph:
    """由持久化草稿构造 DAG（`docs/07` §4.3 #20 → `docs/02` §47）。

    Args:
        drafts: 步骤草稿（`domain.protocols.TaskStepDraft`）；`parameters_json`
            是 JSON 文本，`depends_on` 是前置步骤键元组。

    Returns:
        `TaskGraph`（**未**做环校验；调用方随后必须 `validate_dag`）。

    Raises:
        EngineeringValidationError: `STRUCTAI-1200` —— 同 `step_key` 重复
            （`docs/02` §48 的 `duplicate step`），或 `parameters_json` 不是合法
            JSON 对象（**不**静默当作空参数）。
    """
    steps: dict[str, TaskStep] = {}
    for draft in drafts:
        if draft.step_key in steps:
            raise EngineeringValidationError(
                f"Duplicate step: {draft.step_key}",
                details={
                    "stage": DAG_STAGE,
                    "reason": "duplicate_step",
                    "step": draft.step_key,
                },
            )
        steps[draft.step_key] = TaskStep(
            step_id=draft.step_key,
            operation=draft.operation,
            parameters=_decode_parameters(draft.parameters_json, draft.step_key),
            depends_on=tuple(str(item) for item in draft.depends_on),
        )
    return TaskGraph(steps=steps)


def encode_depends_on(depends_on: Iterable[str]) -> str:
    """前置步骤键 → `task_steps.depends_on_json` 的 JSON 数组文本。

    ⚠️ 用 `sort_keys=True` 之外还**排序元素**：集合语义的前置条件不应因书写顺序
    不同而产生不同的落库文本（否则「同一 DAG」会有多种持久化表示）。
    """
    return json.dumps(sorted({str(item) for item in depends_on}), ensure_ascii=False)


def validate_dag(
    graph: TaskGraph,
    *,
    known_operations: Iterable[str] | None = None,
) -> tuple[str, ...]:
    """校验 DAG 并返回拓扑序（`docs/02` §48 / §49；`docs/07` §10.2）。

    逐项检测 §48 的四类缺陷（见模块裁决 1 / 2）：

    - `duplicate_step` —— 由 `graph_from_drafts` 在构造期拒绝（字典键天然唯一）；
    - `missing_dependency` —— `depends_on` 指向的 key 不在图内；
    - `cycle` —— DFS 命中 `visiting`（§49 的原文判定）；
    - `unknown_step` —— 步骤的 `operation` 不在 `known_operations` 内
      （仅当传入该参数时检查）。

    Args:
        graph: 待校验的 DAG。
        known_operations: 已登记的 Operation 名集合（如 P08 `OperationRegistry.names()`）；
            缺省 `None` 表示**不**检查 Operation 合法性。

    Returns:
        拓扑序（前置步骤在前），即 `docs/02` §82 的执行序。

    Raises:
        EngineeringValidationError: `STRUCTAI-1200` —— 任一缺陷命中；
            错误在**提交之前**抛出（`docs/02` §19），因此不会有半个任务落库。
    """
    if known_operations is not None:
        allowed = frozenset(str(name) for name in known_operations)
        for step in graph.steps.values():
            if step.operation not in allowed:
                raise EngineeringValidationError(
                    f"Unknown step operation: {step.operation}",
                    details={
                        "stage": DAG_STAGE,
                        "reason": "unknown_step",
                        "step": step.step_id,
                        "operation": step.operation,
                    },
                )

    visiting: set[str] = set()
    visited: set[str] = set()
    order: list[str] = []

    def visit(node: str) -> None:
        if node in visiting:
            raise EngineeringValidationError(
                "Task DAG contains cycle",
                details={"stage": DAG_STAGE, "reason": "cycle", "step": node},
            )
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph.step(node).depends_on:
            if dependency not in graph.steps:
                raise EngineeringValidationError(
                    f"Unknown dependency: {dependency}",
                    details={
                        "stage": DAG_STAGE,
                        "reason": "missing_dependency",
                        "step": node,
                        "dependency": dependency,
                    },
                )
            visit(dependency)
        visiting.discard(node)
        visited.add(node)
        order.append(node)

    for node in graph.steps:
        visit(node)
    return tuple(order)


def topological_order(graph: TaskGraph) -> tuple[str, ...]:
    """拓扑序（`docs/02` §82 的执行序；等价于 `validate_dag` 的返回值）。"""
    return validate_dag(graph)


def ready_steps(
    graph: TaskGraph,
    statuses: Mapping[str, TaskStepStatus | str],
) -> tuple[str, ...]:
    """当前可以进入 `READY` 的步骤（`docs/02` §50 的「全部依赖 `COMPLETED`」）。

    Args:
        graph: DAG。
        statuses: 各步骤的当前状态（缺省视为 `PENDING`）。

    Returns:
        依赖全部 `COMPLETED` 且自身仍为 `PENDING` 的步骤键（§51：可并行执行）。
    """
    ready: list[str] = []
    for step_id, step in graph.steps.items():
        if _status_of(statuses, step_id) is not TaskStepStatus.PENDING:
            continue
        if all(
            _status_of(statuses, dependency) is TaskStepStatus.COMPLETED
            for dependency in step.depends_on
        ):
            ready.append(step_id)
    return tuple(ready)


def blocked_steps(
    graph: TaskGraph,
    statuses: Mapping[str, TaskStepStatus | str],
) -> tuple[str, ...]:
    """应被置为 `SKIPPED` 的步骤（`docs/02` §50 的默认行为）。

    规则：任一前置为 `FAILED` / `SKIPPED`，且本步骤**未**配置
    `continue_on_failure = true` → `SKIPPED`。递归传播（被跳过的步骤同样会
    阻塞其后继）。
    """
    skipped: set[str] = set()
    changed = True
    while changed:
        changed = False
        for step_id, step in graph.steps.items():
            if step_id in skipped or step.continue_on_failure:
                continue
            if _status_of(statuses, step_id) in TERMINAL_STEP_STATUSES:
                continue
            for dependency in step.depends_on:
                if dependency in skipped or _status_of(statuses, dependency) in {
                    TaskStepStatus.FAILED,
                    TaskStepStatus.SKIPPED,
                }:
                    skipped.add(step_id)
                    changed = True
                    break
    return tuple(sorted(skipped))


def step_plan(
    graph: TaskGraph,
    statuses: Mapping[str, TaskStepStatus | str],
) -> DagPlan:
    """一次完整的调度决策（`docs/02` §50 / §51）。

    Args:
        graph: DAG。
        statuses: 各步骤的当前状态。

    Returns:
        `DagPlan`：`ready` / `skipped` / `running` / `finished` 四组步骤键。
    """
    skipped = blocked_steps(graph, statuses)
    ready = ready_steps(graph, statuses)
    running = tuple(
        step_id
        for step_id in graph.steps
        if _status_of(statuses, step_id) is TaskStepStatus.RUNNING
    )
    finished = tuple(
        step_id
        for step_id in graph.steps
        if _status_of(statuses, step_id) in TERMINAL_STEP_STATUSES
    )
    return DagPlan(ready=ready, skipped=skipped, running=running, finished=finished)


def _status_of(
    statuses: Mapping[str, TaskStepStatus | str],
    step_id: str,
) -> TaskStepStatus:
    """取某步骤的状态；缺省 `PENDING`（`docs/02` §50 的初始态）。"""
    raw = statuses.get(step_id, TaskStepStatus.PENDING)
    return raw if isinstance(raw, TaskStepStatus) else TaskStepStatus(str(raw))


def _decode_parameters(parameters_json: str, step_key: str) -> dict[str, Any]:
    """`parameters_json` → 结构化参数（`docs/02` §47 的 `parameters: dict`）。

    Raises:
        EngineeringValidationError: `STRUCTAI-1200` —— 非法 JSON 或不是 JSON 对象
            （**不**臆造内容、**不**静默当作空参数）。
    """
    try:
        parsed: Any = json.loads(parameters_json or "{}")
    except json.JSONDecodeError as error:
        raise EngineeringValidationError(
            "Task step parameters are not valid JSON",
            details={"stage": DAG_STAGE, "reason": "unknown_step", "step": step_key},
            cause=error,
        ) from error
    if not isinstance(parsed, dict):
        raise EngineeringValidationError(
            "Task step parameters are not a JSON object",
            details={"stage": DAG_STAGE, "reason": "unknown_step", "step": step_key},
        )
    return {str(key): value for key, value in parsed.items()}
