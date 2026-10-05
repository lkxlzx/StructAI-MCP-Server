"""Registry · SchemaRegistry —— Schema 注册表（`docs/07` §12 P08 / P09；`docs/02` §12 / §14 / §15 / §22）。

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
  （`docs/02` §13 / §16；`SchemaEngine.check_schema`）。

P09 落地补充：用 `registry/` 的真实 Schema 填充本注册表
------------------------------------------------------
数据源：`registry/schema/**/*.json`（`registry/README.md` §2 / §3 —— **616** 个文件，
每个文件形如 `{"key": "DB.ACTL", "uri": "DB/ACTL", "source": …, "schema": {…}}`）。

**① id 口径（`docs/02` §14 / §22；与 P07 同一条规则）**

    id = `structai://schema/<key 小写、"." → "/">/v1`

P07 的 `input_schema_uri` 对**单段** Operation 名会补 Tool 前缀（如 `structai://schema/doc/new/v1`）；
数据侧端点 key 实测 **616 / 616 都含 "."**，故本装载器不需要前缀分支（见 `schema_id_for`）。

**② 与 P07 的 Operation URI 对齐（本批实测，逐条可复算）**

| 项 | 数量 | 说明 |
| --- | --- | --- |
| 数据侧 Schema 文件 | **616** | 与 `registry/manifest.json` 里带 `schema` 的端点 **1:1**（无孤儿、无缺文件） |
| 数据侧端点**无** Schema | **20** | `docs/07` §16 R5；本批留空，不臆造 |
| 69 个 Operation 的 URI | 138 | 69 `input_schema` + 69 `output_schema`（P07 固化） |
| 其中能被数据侧解析 | **4** | `structai://schema/doc/{new,open,save,close}/v1` = 数据侧 `DOC.NEW` / `DOC.OPEN` / `DOC.SAVE` / `DOC.CLOSE` |
| 其中 `…/result/v1` 可解析 | **0** | 数据侧没有响应 Schema（`schema_ref.introspect` 是软件侧自省路径） |
| 唯一形态差异 | **1** | `engineering_doc` 的 `SAVE_AS` → `…/doc/save_as/v1`（P07 保留下划线）；数据侧 `DOC.SAVEAS` → `…/doc/saveas/v1` |
| 其余 Operation | 65 | 数据侧无对应 Schema；其 URI 指向 Core 自有的 `schemas/`（`docs/02` §22），本批不产出（P36+ / Mock Adapter 接管） |

**③ 请求体包装的还原（机械规则，不改任何取值）**

数据侧 `schema` 字段是**请求体包装**：`{<根键>: <JSON Schema>}`（根键形如 `ACTL` / `Argument` /
`TABLE`），也有直接就是 JSON Schema 的写法。装载时按 `_effective_schema` 的**机械**规则还原：
根键**不是** JSON Schema 关键字且是唯一键 → 取内层对象；否则原样保留。根键（厂商专属包装名）
因此**不会**出现在 Core 代码里（`docs/07` §14.2）。

**④ 数据缺陷（本批实测，登记为 `docs/07` §16 R19）**

| 端点 key | 缺陷 | 本批处置 |
| --- | --- | --- |
| `DB.MBTP` | `schema` 是**字符串**且**不是合法 JSON**（缺 1 个 `}`） | 无法还原成对象 → **跳过**并计入 `unresolvable`（**不**臆造内容、**不**报错中断） |
| `DESIGN.SRC.AIK-SRC2K.MATD` / `.MCRD` / `.MRBD`、`OPE.EDMP` | 不是合法的 JSON Schema（占位字符串 / 非法子 schema） | **照原样登记**（数据侧是权威来源），由 `SchemaEngine.check_schema` 诊断 |

只读：本模块不写数据库、不提交事务（`docs/02` §45；`docs/07` §14.4）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from app.domain.errors import InternalError, NotFoundError

__all__ = [
    "JSON_SCHEMA_KEYWORDS",
    "SCHEMA_DIR",
    "SCHEMA_URI_PREFIX",
    "SCHEMA_VERSION",
    "UNDECLARED_DIALECT",
    "SchemaLoadReport",
    "SchemaRegistry",
    "schema_id_for",
]

logger = logging.getLogger("structai.registry")

SCHEMA_URI_PREFIX: Final[str] = "structai://schema/"
"""Schema id 前缀（`docs/02` §14 / §22）。"""

SCHEMA_DIR: Final[str] = "schema"
"""`registry_root` 下存放 JSON Schema 的子目录（`registry/README.md` §2；`docs/02` §22 的 `schemas/` 口径）。"""

SCHEMA_VERSION: Final[str] = "v1"
"""Schema id 的版本段（`docs/02` §12 / §14：旧版本靠版本化 id 表达，不靠禁止覆盖）。"""


UNDECLARED_DIALECT: Final[str] = "<undeclared>"
"""数据侧未声明 `$schema` 的标记（装载报告用；`docs/07` §16 R18 实测 175 个）。"""

JSON_SCHEMA_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "$anchor",
        "$comment",
        "$defs",
        "$dynamicAnchor",
        "$dynamicRef",
        "$id",
        "$ref",
        "$schema",
        "$vocabulary",
        "additionalProperties",
        "allOf",
        "anyOf",
        "const",
        "contains",
        "contentEncoding",
        "contentMediaType",
        "default",
        "definitions",
        "dependencies",
        "dependentRequired",
        "dependentSchemas",
        "deprecated",
        "description",
        "else",
        "enum",
        "examples",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "format",
        "if",
        "items",
        "maxItems",
        "maxLength",
        "maxProperties",
        "maximum",
        "minItems",
        "minLength",
        "minProperties",
        "minimum",
        "multipleOf",
        "not",
        "oneOf",
        "pattern",
        "patternProperties",
        "prefixItems",
        "properties",
        "propertyNames",
        "readOnly",
        "required",
        "then",
        "title",
        "type",
        "unevaluatedItems",
        "unevaluatedProperties",
        "uniqueItems",
        "writeOnly",
    }
)
"""JSON Schema 关键字集合（draft-07 ∪ 2020-12）。

只用于 `_effective_schema` 判断「唯一键是数据侧包装根键还是 Schema 关键字」这一件事，
**不**参与任何取值改写（`docs/02` §12 / §22）。
"""


def schema_id_for(key: str) -> str:
    """由数据侧端点 key 机械生成 Schema id（`docs/02` §14 / §22；与 P07 同一条规则）。

    Args:
        key: `registry/schema/**/*.json` 的 `key`（如 `DB.ACTL` / `POST.TABLE.DISPLACEMENTG`）。

    Returns:
        `structai://schema/<key 小写、"." → "/">/v1`，如 `structai://schema/db/actl/v1`。

    Raises:
        InternalError: `key` 为空或非字符串（数据侧缺字段属装配错误，`docs/07` §14.4）。
    """
    if not isinstance(key, str) or not key.strip():
        raise InternalError(
            "schema key is empty",
            details={"key": repr(key)},
        )
    return f"{SCHEMA_URI_PREFIX}{key.strip().lower().replace('.', '/')}/{SCHEMA_VERSION}"


def _effective_schema(content: object) -> tuple[dict[str, Any] | None, str]:
    """把数据侧 `schema` 字段机械还原成 JSON Schema 对象（**不改任何取值**）。

    规则（`registry/README.md` §2 / §4 的数据形态实测）：

    1. 字符串 → 先 `json.loads`（数据侧有 1 个端点把 JSON 存成了字符串）；
    2. 是对象且**唯一**键**不是** JSON Schema 关键字 → 该键是数据侧的**请求体包装根键**
       （如 `ACTL` / `Argument` / `TABLE`）→ 取内层对象；
    3. 其余情况（本身已是 JSON Schema、或多根键）→ **原样**保留。

    Args:
        content: 数据文件的 `schema` 字段。

    Returns:
        `(schema, kind)`；`schema` 为 `None` 表示无法还原成对象（原因在 `kind` 中）。

    Raises:
        无：无法还原时返回 `(None, 原因)`，由调用方计数上报（**不**臆造内容）。
    """
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError as error:
            return None, f"schema is a string that is not valid JSON: {error.msg}"
    if not isinstance(content, dict):
        return None, f"schema is not a JSON object: {type(content).__name__}"
    if len(content) == 1:
        root, inner = next(iter(content.items()))
        if root not in JSON_SCHEMA_KEYWORDS and isinstance(inner, dict):
            return inner, "envelope"
    return content, "verbatim"


@dataclass(frozen=True, slots=True)
class SchemaLoadReport:
    """一次 Schema 装载的结果（供启动日志与验收证据；**不含** secret）。"""

    files: int
    """扫描到的 `*.json` 文件数（`registry/README.md` §3：**616**）。"""

    registered: int
    """实际登记进注册表的 Schema 数（= `files` − `unresolvable`）。"""

    unresolvable: tuple[tuple[str, str], ...] = ()
    """无法还原成对象的文件：`(相对路径, 原因)`（本批 1 个，`docs/07` §16 R19）。"""

    dialects: tuple[tuple[str, int], ...] = ()
    """数据侧 `$schema` 取值分布：`(方言, 条数)`（升序；未声明记为 `"<undeclared>"`）。"""

    envelopes: int = 0
    """按包装根键还原的数量（`_effective_schema` 规则 2）。"""

    verbatim: int = 0
    """原样登记的数量（规则 3：本身即 JSON Schema，或多根键）。"""

    def summary(self) -> dict[str, Any]:
        """装配摘要（供启动日志与验收证据；**不含** secret）。"""
        return {
            "files": self.files,
            "schemas": self.registered,
            "envelopes": self.envelopes,
            "verbatim": self.verbatim,
            "dialects": dict(self.dialects),
            "unresolvable": [list(item) for item in self.unresolvable],
        }


class SchemaRegistry:
    """Schema 注册表（`docs/02` §15；`docs/07` §12 P08 门槛 ④ / P09 门槛 ①–③）。

    ⚠️ `register` / `get` 是**同步**方法 —— 与 `docs/02` §15 的原文签名逐项一致
    （Schema 是进程内不可变引用数据，不涉及 I/O；数据库 / 文件装载由 P09 负责）。
    """

    def __init__(self, *, report: SchemaLoadReport | None = None) -> None:
        """空注册表（`docs/02` §15）。

        Args:
            report: `load()` 的装载报告（可选关键字参数；`SchemaRegistry()` 的原文构造
                方式保持不变，`docs/02` §15）。
        """
        self._schemas: dict[str, dict[str, Any]] = {}
        self._report: SchemaLoadReport | None = report

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

    def report(self) -> SchemaLoadReport | None:
        """本注册表的装载报告（未由 `load()` 构造时为 `None`）。"""
        return self._report

    def summary(self) -> dict[str, Any]:
        """装配摘要（供启动日志与验收证据；**不含** secret）。"""
        if self._report is None:
            return {"schemas": len(self._schemas)}
        return self._report.summary()

    def __len__(self) -> int:
        return len(self._schemas)

    def __contains__(self, schema_id: object) -> bool:
        return schema_id in self._schemas

    # ===== 装配（P09；`registry/README.md` §2 / §5）=====

    @classmethod
    def load(cls, registry_root: str | Path) -> SchemaRegistry:
        """从 `registry/schema/` 装载真实 JSON Schema（`docs/02` §14 / §22）。

        Args:
            registry_root: 数据目录（由 `Settings.registry_root` 给出）。

        Returns:
            已装载的 `SchemaRegistry`（`report()` 给出逐项计数与无法装载的原因）。

        Raises:
            NotFoundError: 数据目录里没有 `schema/` 子目录（数据源缺失）。
            InternalError: 文件不可读 / 不可解析，记录缺 `key`，或同一 id 重复登记
                （`docs/07` §14.4：Registry 校验失败 → Server MUST NOT become READY）。
        """
        root = Path(registry_root)
        schema_dir = root / SCHEMA_DIR
        if not schema_dir.is_dir():
            raise NotFoundError(f"schema directory not found: {schema_dir}")

        files = sorted(schema_dir.rglob("*.json"))
        if not files:
            raise InternalError(
                "no schema file was found",
                details={"path": str(schema_dir)},
            )

        registry = cls()
        unresolvable: list[tuple[str, str]] = []
        dialects: dict[str, int] = {}
        envelopes = 0
        verbatim = 0
        origins: dict[str, str] = {}

        for path in files:
            relative = path.relative_to(schema_dir).as_posix()
            document = _read_document(path, relative)
            key = document.get("key")
            if not isinstance(key, str) or not key.strip():
                raise InternalError(
                    "schema file has no `key`",
                    details={"path": relative, "key": repr(key)},
                )
            schema_id = schema_id_for(key)
            if schema_id in origins:
                raise InternalError(
                    "duplicate schema id",
                    details={"schema_id": schema_id, "first": origins[schema_id], "second": relative},
                )
            origins[schema_id] = relative

            schema, kind = _effective_schema(document.get("schema"))
            if schema is None:
                unresolvable.append((relative, kind))
                continue

            registry.register(schema_id, schema)
            declared = schema.get("$schema")
            dialect = str(declared) if declared else UNDECLARED_DIALECT
            dialects[dialect] = dialects.get(dialect, 0) + 1
            if kind == "envelope":
                envelopes += 1
            else:
                verbatim += 1

        report = SchemaLoadReport(
            files=len(files),
            registered=len(registry),
            unresolvable=tuple(unresolvable),
            dialects=tuple(sorted(dialects.items())),
            envelopes=envelopes,
            verbatim=verbatim,
        )
        registry._report = report
        logger.info("schema registry loaded: %s", report.summary())
        return registry


def _read_document(path: Path, relative: str) -> dict[str, Any]:
    """读取并解析一个 Schema 文件（`registry/README.md` §2 的数据形态）。

    Raises:
        InternalError: 文件不可读、不是合法 JSON、或缺 `key`。
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InternalError(
            "schema file is unreadable",
            details={"path": relative, "error": type(error).__name__},
        ) from error
    if not isinstance(document, dict):
        raise InternalError(
            "schema file is not a JSON object",
            details={"path": relative},
        )
    return document
