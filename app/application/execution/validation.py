"""Application · Execution · SchemaEngine —— 「Schema → 参数」校验（`docs/07` §12 P09）。

权威来源
--------
- `docs/02` §13（SchemaEngine）—— 职责链：`operation → input_schema → JSON Schema →
  validate parameters`；标准 = **JSON Schema Draft 2020-12**。
- `docs/02` §16（SchemaEngine 实现）—— **原文**：`SchemaEngine(registry)` +
  `validate(schema_id, data)`，用 `Draft202012Validator(schema).iter_errors(data)`，
  错误按 `list(error.path)` 排序，失败时抛异常并带
  `details={"errors": [{"path": [...], "message": ...}, ...]}`。
- `docs/02` §13 / §17（Validation Engine / Schema Validation 原则）—— 顺序**冻结**为
  `Schema Validation → Engineering Validation`；Schema **只**解决
  类型 / 字段 / 格式 / 结构 / 枚举 / 必填 / 范围，
  「结构是否合理 / 材料是否适合 / 节点是否重复」等**工程语义**归 `EngineeringValidator`
  （`docs/02` §18–§22）—— **本批不实现**（`docs/07` §14.1 分层边界）。
- `docs/02` §114（P09 门槛）—— `load schema` → `validate valid data` → `reject invalid data`。
- `docs/07` §11 —— 拒绝必须落 **`STRUCTAI-1100` Schema Validation Error**（20 码契约）。

原文签名的两处落地对齐（只补实现手段，不改语义）
------------------------------------------------
1. **异常类名**：`docs/02` §16 原文写 `raise ValidationError(...)`；本项目唯一的错误码
   契约是 `docs/07` §11 的 20 码，其中「JSON Schema 校验失败」= **`STRUCTAI-1100`**，
   在 P03 已落地为 `app.domain.errors.SchemaValidationError`。
   本批据此落地该异常类，**不新增**异常 / 错误码（20 码契约不扩）。
   失败时**抛异常**，绝不返回 `False`、绝不静默通过（`docs/07` §12 P09 门槛 ①）。
2. **依赖类型**：`docs/02` §16 原文写 `registry: SchemaRegistry`。按 `docs/07` §2.2 冻结的
   依赖方向（`Interface → Application → Domain`，Application **不得**依赖 Infrastructure），
   本文件把该参数收窄为**结构化契约** `SchemaLookup`（只有 `get(schema_id) -> dict`）；
   `app.infrastructure.registry.SchemaRegistry` 结构上即满足它，容器在装配期注入实例。
   这与 P03 把 `OperationRegistry` 声明为 Domain Protocol 是同一条规则。

R18 裁决（Draft 2020-12 vs 数据侧的 draft-07）
--------------------------------------------
规范侧（`docs/02` §12 / §13 / §22）要求 **Draft 2020-12**；数据侧（`registry/schema/`，实测）：
**440** 个在 `$schema` 声明 `http://json-schema.org/draft-07/schema#`、**175** 个未声明、
**1** 个 `schema` 是非法 JSON 字符串（无法装载，见 `docs/07` §16 R19）。

**裁决：按各 Schema 自身声明的方言选择校验器；未声明者按项目标准 2020-12 校验。**
依据（逐条可复核）：
1. `registry/` 是外部软件 API 的**唯一权威来源**，Schema 内容**原样登记**（不改写任何取值）；
   强行按 2020-12 解释 draft-07 文档会**静默改变语义**（如 `exclusiveMinimum` 在 draft-07 是
   布尔修饰符、在 2020-12 是数值；`definitions` / `items` / `prefixItems` 亦不同），
   属于「用错方言」，比报错更危险。
2. 该结论与 `docs/07` §16 R18 的**建议**一致（「按各文件自身 `$schema` 选择 validator，
   未声明者按 2020-12 校验并把差异写进验收证据」）。
3. `docs/02` 的 Draft 2020-12 仍是 **Core 自有 Schema** 的标准（`schemas/`，`docs/02` §22；
   69 个 Operation 的 `input_schema` / `output_schema`），本批不产出它们。
4. 实测未出现 2020-12 声明（440 + 175 + 1 = 616），故映射表只需 draft-07 一条别名；
   出现未知方言时**回落**到 2020-12，并由 `dialect_of()` 如实返回生效方言。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库、`jsonschema` 与 `app.domain`：**不**引用 SQLAlchemy / FastAPI /
MCP SDK / httpx，**不**依赖 `app.infrastructure`，也**不**出现任何厂商专属
endpoint / 参数 / 响应（`grep -ri` 厂商名预期 0 处）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, Protocol

# ⚠️ `jsonschema` 不自带 `py.typed` / 类型存根；装 `types-jsonschema` 会改动冻结的依赖
# 清单（`docs/07` §3.1 / §3.2「不得引入新依赖」），故此处按 mypy 的标准做法显式忽略。
from jsonschema import Draft7Validator, Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import (  # type: ignore[import-untyped]
    SchemaError,
    ValidationError,
)
from jsonschema.protocols import Validator  # type: ignore[import-untyped]

from app.domain.errors import InternalError, SchemaValidationError

__all__ = [
    "DEFAULT_DIALECT",
    "DRAFT7_URI",
    "SCHEMA_2020_12_URI",
    "SUPPORTED_DIALECTS",
    "SchemaEngine",
    "SchemaLookup",
    "dialect_of",
    "validator_for",
]

DRAFT7_URI: Final[str] = "http://json-schema.org/draft-07/schema#"
"""draft-07 的官方方言 URI（数据侧 **440** 个 Schema 用它，实测）。"""

DRAFT7_URI_ALTERNATE: Final[str] = "https://json-schema.org/draft-07/schema"
"""同一 draft-07 方言的 https 写法（数据侧当前未出现；接受它以免将来刷新数据时误回落）。"""

SCHEMA_2020_12_URI: Final[str] = "https://json-schema.org/draft/2020-12/schema"
"""项目标准方言（`docs/02` §12 / §13 / §22）：Draft 2020-12。"""

DEFAULT_DIALECT: Final[str] = SCHEMA_2020_12_URI
"""未声明 `$schema` 时生效的方言（**175** 个数据侧 Schema 走这条路径）。"""

SUPPORTED_DIALECTS: Final[Mapping[str, type[Validator]]] = {
    DRAFT7_URI: Draft7Validator,
    DRAFT7_URI_ALTERNATE: Draft7Validator,
}
"""方言 URI → 校验器（`docs/07` §16 R18 裁决：按数据侧声明选择，缺省 2020-12）。"""


class SchemaLookup(Protocol):
    """Schema 查找契约（`docs/02` §15 的 `SchemaRegistry.get`）。

    只有 `get` 一个方法 —— `SchemaEngine` 不需要登记 / 枚举能力，收窄依赖面
    （`docs/07` §2.2：Application 不依赖 Infrastructure，容器在装配期注入实现）。
    """

    def get(self, schema_id: str) -> dict[str, Any]: ...


def dialect_of(schema: Mapping[str, Any]) -> str:
    """该 Schema **生效**的 JSON Schema 方言（`docs/07` §16 R18 裁决）。

    Args:
        schema: 已登记的 JSON Schema 对象。

    Returns:
        `$schema` 声明的方言（若在 `SUPPORTED_DIALECTS` 内）；否则 `DEFAULT_DIALECT`
        （未声明 **或** 未知方言都回落到项目标准 2020-12）。
    """
    declared = schema.get("$schema")
    if isinstance(declared, str) and declared in SUPPORTED_DIALECTS:
        return declared
    return DEFAULT_DIALECT


def validator_for(schema: Mapping[str, Any]) -> type[Validator]:
    """该 Schema 应使用的 `jsonschema` 校验器类（`docs/02` §16；R18 裁决）。

    Args:
        schema: 已登记的 JSON Schema 对象。

    Returns:
        `Draft7Validator`（声明 draft-07 时）或 `Draft202012Validator`（其余情况）。
    """
    return SUPPORTED_DIALECTS.get(dialect_of(schema), Draft202012Validator)


def _error_sort_key(error: ValidationError) -> tuple[tuple[int, Any], ...]:
    """校验错误的**总序**排序键（`docs/02` §16 原文排序语义的落地实现）。

    `docs/02` §16 原文用 `key=lambda error: list(error.path)`；`error.path` 的元素类型
    随路径混合（对象键是 `str`、数组下标是 `int`），纯 `list` 排序在混合路径上会
    `TypeError`。此处改为 `(类型秩, 值)` 元组：数字分量内部仍按数值比较、字符串分量内部
    按字典序比较，两条路径**永不**跨类型比较 —— 对同构路径的排序与原文逐项一致。
    """
    return tuple((0, part) if isinstance(part, int) else (1, str(part)) for part in error.path)


class SchemaEngine:
    """「Schema → 参数」校验引擎（`docs/02` §13 / §16；`docs/07` §12 P09 门槛 ①）。

    ⚠️ 本引擎**只**做结构校验（类型 / 字段 / 格式 / 结构 / 枚举 / 必填 / 范围，
    `docs/02` §17）；工程语义（坐标为 null、节点重复、材料不存在 …）属
    `EngineeringValidator`（`docs/02` §18–§22），**不在本批**，且按 `docs/02` §13 的顺序
    必须**后于**本引擎执行。
    """

    def __init__(self, registry: SchemaLookup) -> None:
        """绑定 Schema 来源（`docs/02` §16 原文的 `self.registry = registry`）。

        Args:
            registry: 满足 `SchemaLookup` 的 Schema 来源（装配期由容器注入）。
        """
        self.registry = registry

    def validate(self, schema_id: str, data: object) -> None:
        """按 Schema 校验参数（`docs/02` §16 原文签名与错误形状）。

        Args:
            schema_id: Schema URI（`structai://schema/<…>/v1`，`docs/02` §14）。
            data: 待校验的参数（`docs/02` §16 原文标注 `dict`；此处放宽为 `object`，
                使「传入非对象」也走同一条拒绝路径，而不是 `TypeError`）。

        Raises:
            NotFoundError: `schema_id` 未登记（`docs/02` §15；**不**携带 `STRUCTAI-xxxx`，
                它只用于装配期查找失败，见 `app/domain/errors.py`）。
            SchemaValidationError: `STRUCTAI-1100`，校验失败（`docs/07` §11）。
                `details` 形状 = `docs/02` §16 原文的 `errors`（逐项 `path` + `message`），
                另附 `schema_id` 便于诊断。**绝不**返回 `False` / 静默通过。
            InternalError: `STRUCTAI-7000`（兜底码，20 码内既有），**Schema 自身**无法被应用
                （方言不匹配 / 非法 Schema，见 `check_schema`）—— 这是装配问题，不是数据问题；
                数据非法一律走 `SchemaValidationError`。
        """
        schema = self.registry.get(schema_id)
        validator = validator_for(schema)(schema)

        try:
            errors = sorted(validator.iter_errors(data), key=_error_sort_key)
        except Exception as error:  # noqa: BLE001 - 方言不匹配 / 非法 Schema 的兜底，见 docstring
            raise InternalError(
                "schema could not be applied to the parameters",
                details={
                    "schema_id": schema_id,
                    "dialect": dialect_of(schema),
                    "error": type(error).__name__,
                    "reason": str(error)[:200],
                },
            ) from error
        if errors:
            raise SchemaValidationError(
                "Schema validation failed",
                details={
                    "schema_id": schema_id,
                    "errors": [
                        {"path": list(error.path), "message": error.message} for error in errors
                    ],
                },
            )

    def check_schema(self, schema_id: str) -> None:
        """校验**已登记的 Schema 自身**是否合法（`docs/02` §13 的 SchemaEngine 职责）。

        `SchemaRegistry` 只负责登记，不判断 JSON Schema 合法性（`docs/02` §13 / §16）；
        数据侧的 Schema 由外部来源提供，可能本身不合规（实测 4 个，`docs/07` §16 R19），
        故本方法是**诊断入口**：装配期 / 验收脚本可对全部已登记 id 逐个调用。

        ⚠️ 不合规的 Schema 在 `validate()` 中不会抛异常（`jsonschema` 在实例校验时**不**
        检查 Schema 自身），而是**静默忽略**非法关键字、变得更宽松 —— 这正是必须显式诊断的原因。

        Args:
            schema_id: Schema URI。

        Raises:
            NotFoundError: `schema_id` 未登记（`docs/02` §15）。
            InternalError: `STRUCTAI-7000`，该 Schema 不是其方言下的合法 JSON Schema
                （装配期信号，`docs/07` §14.4：Registry 校验失败 → Server MUST NOT become READY）。
        """
        schema = self.registry.get(schema_id)
        dialect = dialect_of(schema)
        try:
            validator_for(schema).check_schema(schema)
        except SchemaError as error:
            raise InternalError(
                "registered schema is not a valid JSON Schema",
                details={
                    "schema_id": schema_id,
                    "dialect": dialect,
                    "reason": error.message,
                },
            ) from error

    def dialect(self, schema_id: str) -> str:
        """该 Schema 生效的方言（`docs/07` §16 R18 裁决的运行时可见性）。

        Args:
            schema_id: Schema URI。

        Raises:
            NotFoundError: `schema_id` 未登记（`docs/02` §15）。
        """
        return dialect_of(self.registry.get(schema_id))
