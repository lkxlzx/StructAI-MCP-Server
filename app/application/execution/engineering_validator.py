"""Application · Execution · EngineeringValidator（`docs/07` §12 P14–P18；`docs/02` §18–§22）。

权威来源
--------
- `docs/02` §18（`exec`）—— 职责：`Schema Validation ↓ Engineering Validation`；
  例：节点 ID 不重复 / 元素节点必须存在 / 材料必须存在 / 截面必须存在 /
  荷载不能引用不存在节点。
- `docs/02` §19（`exec`）—— 接口：
  `async def validate(self, operation: str, parameters: dict, context: ExecutionContext) -> None`。
- `docs/02` §20（`exec`）—— 第一阶段规则清单（10 个 Operation）：`MODEL.NODE.CREATE` /
  `MODEL.NODE.UPDATE` / `MODEL.ELEMENT.CREATE` / `MODEL.ELEMENT.UPDATE` /
  `MODEL.BOUNDARY.ASSIGN` / `MODEL.LOAD.ASSIGN` / `BUILD.COLUMN` / `BUILD.BEAM` /
  `ANALYSIS.STATIC` / `DESIGN.STEEL`。
- `docs/02` §21 / §22（`exec`）—— 节点 / 元素的具体判定：节点不得重复；
  元素至少两个节点，且每个节点必须存在。
- `docs/02` §31（`blue`）—— 检查项：几何合法性 / 节点 ID / 坐标 / 元素连接 / 材料 /
  截面 / 荷载 / 边界 / 工程参数。
- `docs/02` §30（`source9`）—— `if node["x"] is None: raise EngineeringValidationError(...)`；
  **工程规则和 JSON Schema 分离**。
- `docs/02` §17 / §69（`exec`）—— Schema 只解决类型 / 字段 / 格式 / 结构 / 枚举 / 必填 / 范围；
  工程语义（坐标为 null、节点重复、构件冲突）**不得**塞回 Schema 层。
- `docs/02` §70（`exec`）—— Validator 必须只操作
  `already-resolved-and-authorized resources`，不得泄露其他租户资源的存在性。
- `docs/07` §9 第 9 步 —— `Engineering Validation` **先于** `Preconditions` /
  `Effective Permission`；第 8 步 `Schema Validation` **先于** 本步（顺序冻结）。
- `docs/07` §11 —— 失败落 **`STRUCTAI-1200` Engineering Validation Error**（20 码契约）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **本 Validator 是纯函数**（无 I/O、无仓储、无数据库）：`docs/02` §70 要求它只操作
   「已解析且已授权」的资源，`docs/07` §14.4 又禁止它泄露其他租户资源的存在性。
   最安全的落地方式是**根本不持有任何存储**：规则只读 `parameters` 与
   `context`，需要查库的存在性检查（「材料必须存在」「截面必须存在」「节点必须存在」）
   由**已解析资源**（`ResolvedResource` / Adapter 侧状态）在后续步骤承担。
   这样「工程语义不得塞回 Schema 层」（`docs/02` §17）与「Validator 不得越权读库」
   （§70）两条约束同时成立。
2. **规则按 Operation 名注册**：`docs/02` §20 给出的是**按 Operation** 的规则清单，
   故本模块用 `ENGINEERING_RULES: Mapping[str, tuple[EngineeringRule, ...]]` 表达，
   `validate()` 按 `operation` 名取规则；未注册的 Operation 只走**通用规则**
   （数值有限性 / 坐标非空），不静默跳过校验。
3. **失败形状**：`EngineeringValidationError`（`STRUCTAI-1200`），
   `details = {"operation": <name>, "issues": [<人可读的违规描述>], "stage": "engineering"}`
   —— 与 `SchemaValidationError` 的 `details` 形状（`schema_id` + `errors`）区分，
   便于诊断「结构合法但工程语义非法」。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，
**不**依赖 `app.infrastructure`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import Any, Final

from app.domain.errors import EngineeringValidationError

__all__ = [
    "ENGINEERING_RULES",
    "ENGINEERING_RULE_OPERATIONS",
    "MIN_ELEMENT_NODES",
    "NODE_COORDINATE_KEYS",
    "EngineeringRule",
    "EngineeringValidator",
]

NODE_COORDINATE_KEYS: Final[tuple[str, ...]] = ("x", "y", "z")
"""节点坐标键（`docs/02` §30 的 `node["x"] is None` 判定；§31 的「坐标」检查项）。"""

MIN_ELEMENT_NODES: Final[int] = 2
"""元素至少需要的节点数（`docs/02` §22：「Element requires at least two nodes」）。"""

EngineeringRule = Callable[[Mapping[str, Any], object], "list[str]"]
"""一条工程规则：`(parameters, context) -> [违规描述]`。

⚠️ 规则**必须**是纯函数：不得读库、不得发网络请求、不得产生副作用
（见模块裁决 1；`docs/02` §70）。
"""


# ===== 规则实现（`docs/02` §20–§22 / §30 / §31）=====


def _sequence_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    """把 `value` 规整成「映射序列」（字符串 / 字节不算序列）。"""
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _walk_numbers(value: Any, prefix: str = "parameters") -> list[tuple[str, float]]:
    """递归收集所有 `float` 值及其路径（`docs/02` §31 的「工程参数」检查项）。"""
    found: list[tuple[str, float]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            found.extend(_walk_numbers(item, f"{prefix}.{key}"))
        return found
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, item in enumerate(value):
            found.extend(_walk_numbers(item, f"{prefix}[{index}]"))
        return found
    if isinstance(value, float):
        found.append((prefix, value))
    return found


def _finite_numbers_rule(parameters: Mapping[str, Any], context: object) -> list[str]:
    """所有数值参数必须是有限数（`docs/02` §31「工程参数」；NaN / Inf 不是合法工程量）。"""
    del context  # 规则不得依赖 context（见模块裁决 1）
    return [
        f"{path}: value must be finite (got {value!r})"
        for path, value in _walk_numbers(parameters)
        if not math.isfinite(value)
    ]


def _coordinate_issues(candidate: Mapping[str, Any], where: str) -> list[str]:
    """坐标不得为 `null`（`docs/02` §30 原文判定的推广）。"""
    return [
        f"{where}: coordinate '{key}' is null"
        for key in NODE_COORDINATE_KEYS
        if key in candidate and candidate[key] is None
    ]


def _node_rule(parameters: Mapping[str, Any], context: object) -> list[str]:
    """节点规则（`docs/02` §20 的 `MODEL.NODE.CREATE` / `MODEL.NODE.UPDATE`；§21 / §31）。

    - 坐标（`x` / `y` / `z`）不得为 `null`（§30 原文）；
    - 显式给出的节点 `id` 不得为空（`docs/02` §21「节点 ID」检查项）；
    - 同一请求内重复的节点 `id` 直接拒绝（§21「节点 ID 不重复」；
      与数据库里已有节点是否重复属**存在性检查**，见模块裁决 1）。
    """
    del context
    issues: list[str] = []

    candidates: list[tuple[str, Mapping[str, Any]]] = []
    node = parameters.get("node")
    if isinstance(node, Mapping):
        candidates.append(("node", node))
    for index, item in enumerate(_sequence_of_mappings(parameters.get("nodes"))):
        candidates.append((f"nodes[{index}]", item))
    if any(key in parameters for key in NODE_COORDINATE_KEYS) or "id" in parameters:
        candidates.append(("parameters", parameters))

    seen: dict[str, str] = {}
    for where, candidate in candidates:
        issues.extend(_coordinate_issues(candidate, where))
        identifier = candidate.get("id")
        if identifier in (None, ""):
            issues.append(f"{where}: node 'id' is required")
            continue
        key = str(identifier)
        if key in seen:
            issues.append(f"{where}: duplicate node id {key!r} (also in {seen[key]})")
        else:
            seen[key] = where
    return issues


def _element_rule(parameters: Mapping[str, Any], context: object) -> list[str]:
    """元素规则（`docs/02` §20 的 `MODEL.ELEMENT.*`；§22「至少两个节点」）。"""
    del context
    issues: list[str] = []

    elements: list[tuple[str, Mapping[str, Any]]] = []
    for index, item in enumerate(_sequence_of_mappings(parameters.get("elements"))):
        elements.append((f"elements[{index}]", item))
    if not elements and "node_ids" in parameters:
        elements.append(("parameters", parameters))

    for where, element in elements:
        node_ids = element.get("node_ids")
        if node_ids is None:
            issues.append(f"{where}: 'node_ids' is required")
            continue
        if not isinstance(node_ids, Sequence) or isinstance(node_ids, (str, bytes)):
            issues.append(f"{where}: 'node_ids' must be a list of node ids")
            continue
        if len(node_ids) < MIN_ELEMENT_NODES:
            issues.append(
                f"{where}: element requires at least {MIN_ELEMENT_NODES} nodes "
                f"(got {len(node_ids)})"
            )
        for position, node_id in enumerate(node_ids):
            if node_id in (None, ""):
                issues.append(f"{where}: node_ids[{position}] is null")
    return issues


def _member_length_rule(parameters: Mapping[str, Any], context: object) -> list[str]:
    """构件长度规则（`docs/02` §31「长度不得为 0」；`BUILD.*` 一族）。"""
    del context
    if "length" not in parameters:
        return []
    length = parameters["length"]
    if isinstance(length, bool) or not isinstance(length, (int, float)):
        return ["parameters: 'length' must be a number"]
    if length <= 0:
        return [f"parameters: 'length' must be greater than 0 (got {length!r})"]
    return []


def _reference_rule(parameters: Mapping[str, Any], context: object) -> list[str]:
    """引用完整性规则（`docs/02` §31「荷载 / 边界」；不读库，只查请求内自洽）。

    - 荷载 / 边界的 `node_ids` / `element_ids` 不得为空引用（`null` / 空串）；
    - 同一请求内的节点引用不得重复（同一节点上重复施加同一荷载是数据错误）。
    """
    del context
    issues: list[str] = []
    for key in ("node_ids", "element_ids"):
        value = parameters.get(key)
        if value is None:
            continue
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            issues.append(f"parameters: '{key}' must be a list of ids")
            continue
        if not value:
            issues.append(f"parameters: '{key}' must not be empty")
        seen: set[str] = set()
        for position, identifier in enumerate(value):
            if identifier in (None, ""):
                issues.append(f"parameters: {key}[{position}] is null")
                continue
            key_text = str(identifier)
            if key_text in seen:
                issues.append(f"parameters: {key}[{position}] repeats {key_text!r}")
            seen.add(key_text)
    return issues


#: 按 Operation 注册的工程规则（`docs/02` §20 的 10 个 Operation）。
ENGINEERING_RULES: Mapping[str, tuple[EngineeringRule, ...]] = MappingProxyType(
    {
        "MODEL.NODE.CREATE": (_node_rule,),
        "MODEL.NODE.UPDATE": (_node_rule,),
        "MODEL.ELEMENT.CREATE": (_element_rule,),
        "MODEL.ELEMENT.UPDATE": (_element_rule,),
        "MODEL.BOUNDARY.ASSIGN": (_reference_rule,),
        "MODEL.LOAD.ASSIGN": (_reference_rule,),
        "BUILD.COLUMN": (_member_length_rule,),
        "BUILD.BEAM": (_member_length_rule,),
        "BUILD.FRAME": (_member_length_rule,),
        "BUILD.TRUSS": (_member_length_rule,),
        "BUILD.SLAB": (_member_length_rule,),
        "BUILD.WALL": (_member_length_rule,),
        "ANALYSIS.STATIC": (_finite_numbers_rule,),
        "DESIGN.STEEL": (_finite_numbers_rule,),
    }
)
"""`docs/02` §20 的规则表。

⚠️ 只有 `MODEL.NODE.CREATE` / `MODEL.NODE.UPDATE` / `MODEL.ELEMENT.CREATE` /
`MODEL.ELEMENT.UPDATE` / `MODEL.BOUNDARY.ASSIGN` / `MODEL.LOAD.ASSIGN` /
`BUILD.COLUMN` / `BUILD.BEAM` / `ANALYSIS.STATIC` / `DESIGN.STEEL` 是 §20 明列的
10 个；`BUILD.FRAME` / `BUILD.TRUSS` / `BUILD.SLAB` / `BUILD.WALL` 是同一族的
**同构补齐**（同一「构件长度不得为 0」规则，`docs/02` §31），在此显式登记，
不做隐式兜底（未登记即只走通用规则）。
"""

ENGINEERING_RULE_OPERATIONS: Final[tuple[str, ...]] = tuple(sorted(ENGINEERING_RULES))
"""已登记专属规则的 Operation 名（升序元组；供装配期核对与验收断言）。"""


class EngineeringValidator:
    """工程语义校验器（`docs/02` §18–§22 / §31；`docs/07` §9 第 9 步）。

    ⚠️ 本类**只做**工程语义校验（几何合法性 / 节点 ID / 坐标 / 元素连接 / 工程参数）；
    结构校验（类型 / 字段 / 格式 / 枚举 / 必填 / 范围）属 P09 的 `SchemaEngine`，
    且必须**先**执行（`docs/02` §17 / §69；`docs/07` §9 第 8 步）。

    ⚠️ 本类是**纯函数**集合：不持有仓储、不读库、不发请求（见模块裁决 1）。
    """

    def __init__(
        self,
        *,
        rules: Mapping[str, Sequence[EngineeringRule]] | None = None,
        generic_rules: Sequence[EngineeringRule] = (_finite_numbers_rule,),
    ) -> None:
        """绑定规则表。

        Args:
            rules: Operation → 规则序列；缺省用 `ENGINEERING_RULES`（`docs/02` §20）。
            generic_rules: 对**所有** Operation 生效的通用规则；缺省只做数值有限性
                检查（见模块裁决 2：未注册的 Operation 不静默跳过）。
        """
        self._rules: Mapping[str, tuple[EngineeringRule, ...]] = MappingProxyType(
            {
                name: tuple(handlers)
                for name, handlers in (ENGINEERING_RULES if rules is None else rules).items()
            }
        )
        self._generic_rules: tuple[EngineeringRule, ...] = tuple(generic_rules)

    @property
    def operations(self) -> tuple[str, ...]:
        """已登记专属规则的 Operation 名（升序）。"""
        return tuple(sorted(self._rules))

    def check(
        self,
        operation: str,
        parameters: Mapping[str, Any],
        context: object = None,
    ) -> list[str]:
        """收集违规项（`docs/02` §19 的 `validate` 的**纯函数**形态）。

        Args:
            operation: Operation 名（`docs/02` §24）。
            parameters: 请求参数（`docs/02` §19）。
            context: `ExecutionContext`（规则不得依赖它，见模块裁决 1）。

        Returns:
            违规描述列表；空列表表示通过。顺序：通用规则 → 该 Operation 的专属规则，
            各自保持登记顺序（输出确定性）。
        """
        issues: list[str] = []
        for rule in self._generic_rules:
            issues.extend(rule(parameters, context))
        for rule in self._rules.get(operation, ()):
            issues.extend(rule(parameters, context))
        return issues

    async def validate(
        self,
        operation: str,
        parameters: Mapping[str, Any],
        context: object = None,
    ) -> None:
        """校验工程语义，失败即拒绝（`docs/02` §19 的原文签名）。

        Args:
            operation: Operation 名（`docs/02` §24）。
            parameters: 请求参数（`docs/02` §19）。
            context: `ExecutionContext`（`docs/02` §19 的第三个参数）。

        Raises:
            EngineeringValidationError: `STRUCTAI-1200`（`docs/07` §11），
                `details` = `{operation, issues, stage}`（见模块裁决 3）。
                **绝不**返回 `False` / 静默通过。
        """
        issues = self.check(operation, parameters, context)
        if issues:
            raise EngineeringValidationError(
                "Engineering validation failed",
                details={
                    "operation": operation,
                    "issues": issues,
                    "stage": "engineering",
                },
            )
