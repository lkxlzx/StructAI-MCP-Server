"""Infrastructure · Adapters · MIDAS · Transforms —— Canonical ↔ Native 十类转换（`docs/07` §7.4）。

权威来源
--------
- `docs/07` §7.4（Transformer 规格）—— 十类：Node / Element / Material / Section /
  Boundary / Load / Analysis / Result / View / Design；禁止 `StructAI Schema == MIDAS Schema`，
  必须走 `Canonical → StructAI Schema Validation → Transformer → MIDAS Schema Validation → HTTP`。
- `docs/04` §19–§55 —— 每类的硬约束（逐条落在各类 docstring）。
- `docs/04` §102 / §103 —— Transformer 目录与 Registry：数据库只保存**标识**
  （如 `midas.node.v1`），代码负责实现。
- `registry/schema/**/*.json` —— 原生字段名的**唯一**来源；本模块**不**硬编码任何
  未在 Schema 中登记的字段（`docs/04` §21：Transformer → Registry Schema）。

落地裁决（只补实现手段，不改任何取值 / 不改语义）
------------------------------------------------
1. **字段白名单来自 Registry Schema**：每个 Transformer 声明的原生字段都会先在对应
   端点的生效 Schema 里查一次；**不在** Schema 里 → `MidasTransformerError`
   （`1200`，`details.reason = "transformer_field_not_in_schema"`）——
   这是「不臆造参数名」的**可执行**实现（`docs/04` §107）。
2. **缺失值一律 `null`，绝不虚构 `0`**（`docs/04` §44）：`from_native` 里原生缺字段 →
   canonical 写 `None`；`to_native` 里 canonical 为 `None` → **不写**该键。
3. **包装键由 Schema 决定**：生效 Schema 根级若恰好是 `Argument` / `Assign` 之一，
   以它为准（`POST.TABLE` / `DOC.ANAL` / `CODE-ANAL` 的 Schema 逐字如此，即使数据的
   `wrapper.write` 写作别的值）；否则回落数据的 `wrapper.write`；两者皆无 → 扁平体。
4. **单位必须显式**（`docs/04` §43）：结果类 canonical 一律带 `units`，取值**只**来自
   原生响应的 `FORCE` / `DIST` 等字段；取不到 → `None`，**不**假设 SI。
5. **结果表形态照官方手册响应示例**：`{<TABLE_NAME>: {"FORCE": .., "DIST": ..,
   "HEAD": [列名..], "DATA": [[值..]]}}`；不符 → `MidasResultShapeError`（`1200`）。
6. **`CODE-X` 只作占位**（`docs/04` §54）：设计结果的 `code` 原样透传，**不**伪装成
   官方规范名。
7. **未映射的荷载类型明确失败**（`docs/04` §32 的 `TEMPERATURE` 在 `registry/` 的 DB
   Schema 中无对应条目）→ `MidasValidationError`（`reason = "load_type_not_mapped"`）。
8. **结果过滤在解析后完成**：`docs/04` §47 的 `node_ids` / `element_ids` 在
   `POST.TABLE` 的 Schema 里没有对应字段（`additionalProperties: false`），故 Adapter 在
   canonical 侧过滤，**不**臆造请求字段。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与同包的 `errors.py` / `registry.py`；**不**引用 SQLAlchemy /
FastAPI / MCP SDK / httpx，**不**依赖 `app.interfaces`。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Final

from app.infrastructure.adapters.midas.errors import (
    MidasResultShapeError,
    MidasTransformerError,
    MidasValidationError,
)
from app.infrastructure.adapters.midas.registry import MidasRegistry

__all__ = [
    "LOAD_TRANSFORMERS",
    "TRANSFORMER_REGISTRY",
    "WRAPPER_KEYS",
    "AnalysisTransformer",
    "BeamLoadTransformer",
    "BodyForceTransformer",
    "BoundaryTransformer",
    "DesignResultTransformer",
    "DesignTransformer",
    "DisplacementTransformer",
    "ElementForceTransformer",
    "ElementTransformer",
    "FieldMap",
    "LoadCaseTransformer",
    "LoadTransformer",
    "MaterialTransformer",
    "NodalLoadTransformer",
    "NodeTransformer",
    "PressureLoadTransformer",
    "ReactionTransformer",
    "ResultRequestTransformer",
    "SchemaBoundTransformer",
    "SectionTransformer",
    "TableResult",
    "ViewTransformer",
    "constraint_flags",
    "constraint_string",
    "parse_table",
    "validate_material",
]

WRAPPER_KEYS: Final[tuple[str, ...]] = ("Argument", "Assign")
"""Schema 根级可能出现的请求体包装键（`registry/README.md` §4 的 `wrapper.write`）。"""

BOUNDARY_FLAGS: Final[tuple[str, ...]] = ("ux", "uy", "uz", "rx", "ry", "rz")
"""`docs/04` §31 + `DB.CONS` Schema 描述 `(DX,DY,DZ,RX,RY,RZ,RW)` 的前六自由度。"""


@dataclass(frozen=True, slots=True)
class FieldMap:
    """一条 canonical ↔ native 字段映射（`docs/07` §7.4 的字段表）。"""

    canonical: str
    native: str
    required: bool = False


@dataclass(frozen=True, slots=True)
class TableResult:
    """原生结果表（`docs/04` §46）。"""

    table_name: str
    head: tuple[str, ...]
    rows: tuple[Mapping[str, str], ...]
    units: Mapping[str, str]

    def column(self, *aliases: str) -> str | None:
        """按列名别名定位**首个**命中的列（大小写不敏感；未命中 → `None`）。"""
        lowered = {name.lower(): name for name in self.head}
        for alias in aliases:
            hit = lowered.get(alias.lower())
            if hit is not None:
                return hit
        return None


def parse_table(native: Mapping[str, Any], *, table_name: str) -> TableResult:
    """把原生结果表解析成 `TableResult`（`docs/04` §46；见模块裁决 5）。

    Raises:
        MidasResultShapeError: `STRUCTAI-1200`，形态不符 —— **不**臆造数值。
    """
    if not isinstance(native, Mapping) or len(native) != 1:
        raise MidasResultShapeError(table_name, "expected a single root key")
    root_key = next(iter(native))
    payload = native[root_key]
    if not isinstance(payload, Mapping):
        raise MidasResultShapeError(table_name, "root payload is not an object")
    head = payload.get("HEAD")
    data = payload.get("DATA")
    if not isinstance(head, Sequence) or isinstance(head, str) or not head:
        raise MidasResultShapeError(table_name, "missing HEAD list")
    if not isinstance(data, Sequence) or isinstance(data, str):
        raise MidasResultShapeError(table_name, "missing DATA list")
    labels = tuple(str(item) for item in head)
    rows: list[Mapping[str, str]] = []
    for row in data:
        if not isinstance(row, Sequence) or isinstance(row, str):
            raise MidasResultShapeError(table_name, "DATA row is not a list")
        values = tuple(str(item) for item in row)
        if len(values) != len(labels):
            raise MidasResultShapeError(table_name, "DATA row width differs from HEAD")
        rows.append(dict(zip(labels, values, strict=True)))
    units = {
        str(key): str(payload[key]) for key in ("FORCE", "DIST", "HEAT", "TEMP") if key in payload
    }
    return TableResult(table_name=str(root_key), head=labels, rows=tuple(rows), units=units)


def constraint_string(*flags: bool) -> str:
    """六个布尔自由度 → `DB.CONS` 的 `CONSTRAINT` 字符串（`docs/04` §31）。"""
    return "".join("1" if bool(flag) else "0" for flag in flags)


def constraint_flags(text: str) -> tuple[bool | None, ...]:
    """`CONSTRAINT` 字符串 → 六个布尔自由度（长度不足 / 非法字符 → `None`，**不**猜）。"""
    flags: list[bool | None] = []
    for char in str(text)[:6]:
        flags.append(char == "1" if char in {"1", "0"} else None)
    while len(flags) < 6:
        flags.append(None)
    return tuple(flags)


def validate_material(canonical: Mapping[str, Any]) -> None:
    """材料工程校验（`docs/04` §28）：`E > 0` / `density >= 0` / `fy > 0` / `fc > 0`。

    Raises:
        MidasValidationError: `STRUCTAI-1200`，任一约束不满足（**不**静默放过）。
    """
    elastic = canonical.get("elastic_modulus")
    if elastic is not None and not float(elastic) > 0:
        raise MidasValidationError("material_elastic_modulus_not_positive", field="elastic_modulus")
    density = canonical.get("density")
    if density is not None and float(density) < 0:
        raise MidasValidationError("material_density_negative", field="density")
    strength = canonical.get("fy") if canonical.get("fy") is not None else canonical.get("fc")
    if strength is not None and not float(strength) > 0:
        raise MidasValidationError("material_strength_not_positive", field="strength")


class SchemaBoundTransformer:
    """Schema 绑定的双向 Transformer 基类（`docs/04` §21 / §102）。"""

    name: ClassVar[str] = ""
    endpoint: ClassVar[str] = ""
    fields: ClassVar[tuple[FieldMap, ...]] = ()

    def __init__(self, registry: MidasRegistry) -> None:
        """绑定 Registry（**只读**；不做任何 I/O）。"""
        self._registry = registry

    # ===== Schema 访问（白名单的**唯一**来源，见裁决 1）=====

    def effective_schema(self) -> dict[str, Any]:
        """生效 Schema（剥离请求体包装根键后）。"""
        return self._registry.effective_schema(self.endpoint) or {}

    def wrapper_key(self) -> str:
        """请求体包装键（见裁决 3）：`Argument` / `Assign` / `none`。"""
        properties = self.effective_schema().get("properties")
        if isinstance(properties, Mapping):
            for candidate in WRAPPER_KEYS:
                if candidate in properties:
                    return candidate
        return self._registry.endpoint(self.endpoint).wrapper_write or "none"

    def root_properties(self) -> Mapping[str, Any]:
        """包装键下的**根级**字段表（`Argument` 子 Schema 或根 `properties`）。"""
        properties = self.effective_schema().get("properties")
        if not isinstance(properties, Mapping):
            return {}
        wrapper = self.wrapper_key()
        if wrapper in WRAPPER_KEYS:
            node = properties.get(wrapper)
            if isinstance(node, Mapping):
                inner = node.get("properties")
                return inner if isinstance(inner, Mapping) else {}
        return properties

    def is_items_style(self) -> bool:
        """该端点是否用 `ITEMS` 数组承载条目（`DB.CONS` / `DB.CNLD` / `DB.PRES` …）。"""
        return "ITEMS" in self.root_properties()

    def item_properties(self) -> Mapping[str, Any]:
        """**条目级**字段表：`ITEMS` 数组元素优先，否则等于根级字段表。"""
        properties = self.root_properties()
        items = properties.get("ITEMS")
        if isinstance(items, Mapping):
            element = items.get("items")
            if isinstance(element, Mapping):
                inner = element.get("properties")
                if isinstance(inner, Mapping):
                    return inner
        return properties

    def item_fields(self) -> frozenset[str]:
        """条目允许的原生字段名（白名单）。"""
        return frozenset(str(name) for name in self.item_properties())

    def nested_item_fields(self, native_path: str) -> frozenset[str]:
        """数组字段（如 `PARAM`）元素级的白名单（取不到 → 空集）。"""
        head = native_path.split("[]")[0].split(".")[0]
        node = self.item_properties().get(head)
        if not isinstance(node, Mapping):
            return frozenset()
        element = node.get("items")
        if not isinstance(element, Mapping):
            return frozenset()
        properties = element.get("properties")
        if not isinstance(properties, Mapping):
            return frozenset()
        return frozenset(str(name) for name in properties)

    # ===== 双向转换 =====

    def to_native(self, canonical: Mapping[str, Any]) -> dict[str, Any]:
        """Canonical → Native（**不**臆造字段、**不**虚构 `0`）。"""
        native: dict[str, Any] = {}
        for key, value in canonical.items():
            field_map = self.field_for(str(key))
            if field_map is None:
                raise MidasTransformerError(self.name, str(key), endpoint=self.endpoint)
            if value is None:
                continue
            leaf = _leaf_of(field_map.native)
            if leaf not in self.fields_for_path(field_map.native):
                raise MidasTransformerError(self.name, leaf, endpoint=self.endpoint)
            _assign(native, field_map.native, value)
        self._require(canonical)
        return native

    def fields_for_path(self, native_path: str) -> frozenset[str]:
        """路径**末段**所在层级的白名单（支持 `A.B` 与 `A[].B`；取不到 → 空集）。

        `docs/04` §107 / §21：字段名必须来自 Registry Schema —— 嵌套字段也一样，
        因此这里沿路径把 Schema 逐层走到底再取白名单。
        """
        node: Any = self.item_properties()
        for segment in native_path.split(".")[:-1]:
            key = segment.replace("[]", "")
            child = node.get(key) if isinstance(node, Mapping) else None
            if isinstance(child, Mapping) and "[]" in segment:
                child = child.get("items")
            if not isinstance(child, Mapping):
                return frozenset()
            node = child.get("properties") or {}
        if not isinstance(node, Mapping):
            return frozenset()
        return frozenset(str(name) for name in node)

    def from_native(self, native: Mapping[str, Any]) -> dict[str, Any]:
        """Native → Canonical（缺字段 → `None`，**不**虚构 `0`，见裁决 2）。"""
        return {field_map.canonical: _lookup(native, field_map.native) for field_map in self.fields}

    # ===== 内部 =====

    def field_for(self, canonical_key: str) -> FieldMap | None:
        """按 canonical 键找映射（未知 → `None`）。"""
        for field_map in self.fields:
            if field_map.canonical == canonical_key:
                return field_map
        return None

    def _require(self, canonical: Mapping[str, Any]) -> None:
        """必填字段缺失 → 明确失败（`docs/04` §25 的前置条件）。"""
        for field_map in self.fields:
            if field_map.required and canonical.get(field_map.canonical) is None:
                raise MidasValidationError(
                    "transformer_required_field_missing",
                    transformer=self.name,
                    field=field_map.canonical,
                )


# ===== 十类 Transformer（模型域）=====


class NodeTransformer(SchemaBoundTransformer):
    """Node（`docs/04` §20–§23）：`id/x/y/z` ↔ `DB.NODE` 的 `X/Y/Z`。

    §23 的 ID 策略：`EXPLICIT` / `AUTO` 都支持；`AUTO` 时原生编号由 `Assign` 键承载
    （`client.py` 负责包装），canonical 侧保留映射后的 `id`。
    """

    name = "midas.node.v1"
    endpoint = "DB.NODE"
    fields = (
        FieldMap("x", "X", required=True),
        FieldMap("y", "Y", required=True),
        FieldMap("z", "Z", required=True),
    )


class ElementTransformer(SchemaBoundTransformer):
    """Element（`docs/04` §24–§26）：`type/node_ids/material_id/section_id/angle`。

    §24：支持 BEAM / COLUMN / TRUSS / PLATE / SHELL / SOLID，但**不**在 Core 中定义
    厂商专用 element code —— canonical `type` **原样**透传给 `TYPE`（Schema 里 `TYPE`
    是 `string`），本模块**不**自建映射表（避免臆造）。
    """

    name = "midas.elem.v1"
    endpoint = "DB.ELEM"
    fields = (
        FieldMap("type", "TYPE", required=True),
        FieldMap("node_ids", "NODE", required=True),
        FieldMap("material_id", "MATL"),
        FieldMap("section_id", "SECT"),
        FieldMap("angle", "ANGLE"),
    )


class MaterialTransformer(SchemaBoundTransformer):
    """Material（`docs/04` §27–§28）：`name/type/properties` → `NAME/TYPE/PARAM[]`。

    §28 的工程校验由 `validate_material()` 表达；`PARAM` 的首个元素承载材料参数
    （Schema 里 `PARAM` 是对象数组，字段名 `ELAST` / `POISN` / `DEN` / `MASS` / `THERMAL`）。
    """

    name = "midas.matl.v1"
    endpoint = "DB.MATL"
    fields = (
        FieldMap("name", "NAME", required=True),
        FieldMap("type", "TYPE", required=True),
        FieldMap("elastic_modulus", "PARAM[].ELAST"),
        FieldMap("poisson_ratio", "PARAM[].POISN"),
        FieldMap("density", "PARAM[].DEN"),
        FieldMap("mass_density", "PARAM[].MASS"),
        FieldMap("thermal_coefficient", "PARAM[].THERMAL"),
    )

    def to_native(self, canonical: Mapping[str, Any]) -> dict[str, Any]:
        """先做 §28 的工程校验，再走通用映射。"""
        validate_material(canonical)
        return super().to_native(canonical)


class SectionTransformer(SchemaBoundTransformer):
    """Section（`docs/04` §29–§30）：`name/section_type/parameters` → `DB.SECT`。

    §30：截面**属性**计算（`/ope/SECTPROP`）**不**等于设计验算（`DESIGN.STEEL`）；
    本类只做截面定义的双向转换。
    """

    name = "midas.sect.v1"
    endpoint = "DB.SECT"
    fields = (
        FieldMap("name", "SECT_NAME", required=True),
        FieldMap("section_type", "SECTTYPE", required=True),
        FieldMap("shape", "SECT_BEFORE.SHAPE"),
        FieldMap("offset_point", "SECT_BEFORE.OFFSET_PT"),
    )


class BoundaryTransformer(SchemaBoundTransformer):
    """Boundary（`docs/04` §31）：`node_id/ux..rz` ↔ `DB.CONS` 的 `ITEMS[]`。

    `CONSTRAINT` 是按 `(DX,DY,DZ,RX,RY,RZ,RW)` 顺序的字符串（Schema 描述逐字）；
    canonical 只覆盖前六个自由度，`RW` **不**臆造。
    """

    name = "midas.cons.v1"
    endpoint = "DB.CONS"
    fields = (
        FieldMap("node_id", "ID", required=True),
        FieldMap("group_name", "GROUP_NAME"),
    )

    def to_native(self, canonical: Mapping[str, Any]) -> dict[str, Any]:
        """canonical → `{ID, GROUP_NAME?, CONSTRAINT}`。"""
        item = super().to_native(
            {key: value for key, value in canonical.items() if key not in BOUNDARY_FLAGS}
        )
        flags = [canonical.get(name) for name in BOUNDARY_FLAGS]
        if any(flag is None for flag in flags):
            raise MidasValidationError(
                "boundary_flags_incomplete", transformer=self.name, flags=list(BOUNDARY_FLAGS)
            )
        item["CONSTRAINT"] = constraint_string(*(bool(flag) for flag in flags))
        return item

    def from_native(self, native: Mapping[str, Any]) -> dict[str, Any]:
        """`{ID, GROUP_NAME?, CONSTRAINT}` → canonical（不足六位 → `None`）。"""
        canonical = super().from_native(native)
        parsed = constraint_flags(str(native.get("CONSTRAINT", "")))
        for name, flag in zip(BOUNDARY_FLAGS, parsed, strict=True):
            canonical[name] = flag
        return canonical


# ===== 荷载域（`docs/04` §32–§34）=====


class LoadCaseTransformer(SchemaBoundTransformer):
    """Load Case（`docs/04` §33）：`no/name/type/description` ↔ `DB.STLD`。

    §33 要求区分 Load Group / Case / Combination / Pattern / Type；本类只承载
    **Load Case**（`DB.STLD` 的四个原生字段逐字来自 Schema），其余概念由各自端点表达。
    """

    name = "midas.stld.v1"
    endpoint = "DB.STLD"
    fields = (
        FieldMap("no", "NO"),
        FieldMap("name", "NAME", required=True),
        FieldMap("type", "TYPE"),
        FieldMap("description", "DESC"),
    )


class NodalLoadTransformer(SchemaBoundTransformer):
    """节点荷载（`docs/04` §32 的 `NODE_FORCE` / `NODE_MOMENT`）→ `DB.CNLD`。"""

    name = "midas.cnld.v1"
    endpoint = "DB.CNLD"
    fields = (
        FieldMap("id", "ID"),
        FieldMap("load_case", "LCNAME", required=True),
        FieldMap("group_name", "GROUP_NAME"),
        FieldMap("fx", "FX"),
        FieldMap("fy", "FY"),
        FieldMap("fz", "FZ"),
        FieldMap("mx", "MX"),
        FieldMap("my", "MY"),
        FieldMap("mz", "MZ"),
    )


class BeamLoadTransformer(SchemaBoundTransformer):
    """梁荷载（`docs/04` §32 的 `BEAM_FORCE` / `BEAM_MOMENT`）→ `DB.BMLD`。"""

    name = "midas.bmld.v1"
    endpoint = "DB.BMLD"
    fields = (
        FieldMap("id", "ID"),
        FieldMap("load_case", "LCNAME", required=True),
        FieldMap("group_name", "GROUP_NAME"),
        FieldMap("command", "CMD"),
        FieldMap("load_type", "TYPE"),
        FieldMap("direction", "DIRECTION"),
        FieldMap("vx", "VX"),
        FieldMap("vy", "VY"),
        FieldMap("vz", "VZ"),
    )


class PressureLoadTransformer(SchemaBoundTransformer):
    """面荷载（`docs/04` §32 的 `PRESSURE`）→ `DB.PRES`。"""

    name = "midas.pres.v1"
    endpoint = "DB.PRES"
    fields = (
        FieldMap("id", "ID"),
        FieldMap("load_case", "LCNAME", required=True),
        FieldMap("command", "CMD"),
        FieldMap("element_type", "ELEM_TYPE"),
        FieldMap("face_edge_type", "FACE_EDGE_TYPE"),
        FieldMap("direction", "DIRECTION"),
        FieldMap("vectors", "VECTORS"),
        FieldMap("forces", "FORCES"),
    )


class BodyForceTransformer(SchemaBoundTransformer):
    """自重（`docs/04` §32 的 `SELF_WEIGHT`）→ `DB.BODF`。"""

    name = "midas.bodf.v1"
    endpoint = "DB.BODF"
    fields = (
        FieldMap("load_case", "LCNAME", required=True),
        FieldMap("group_name", "GROUP_NAME"),
        FieldMap("factors", "FV"),
    )


LOAD_TRANSFORMERS: Final[dict[str, type[SchemaBoundTransformer]]] = {
    "NODE_FORCE": NodalLoadTransformer,
    "NODE_MOMENT": NodalLoadTransformer,
    "BEAM_FORCE": BeamLoadTransformer,
    "BEAM_MOMENT": BeamLoadTransformer,
    "PRESSURE": PressureLoadTransformer,
    "SELF_WEIGHT": BodyForceTransformer,
}
"""`docs/04` §32 的荷载类型 → Transformer（`TEMPERATURE` **故意**缺席，见裁决 7）。"""


class LoadTransformer:
    """Load（`docs/04` §32–§34）：按 `load_type` 分派到具体 Transformer。

    未映射的荷载类型 → `STRUCTAI-1200`（`reason = "load_type_not_mapped"`），
    **不**回落、**不**猜测端点（`docs/07` §12 P122 的「未映射 → 明确错误」）。
    """

    name = "midas.load.v1"

    def __init__(self, registry: MidasRegistry) -> None:
        """绑定 Registry，并为每个荷载类型构造具体 Transformer。"""
        self._delegates = {
            load_type: transformer(registry) for load_type, transformer in LOAD_TRANSFORMERS.items()
        }

    def delegate(self, load_type: str) -> SchemaBoundTransformer:
        """取该荷载类型的 Transformer（未映射 → 明确错误）。"""
        delegate = self._delegates.get(str(load_type).upper())
        if delegate is None:
            raise MidasValidationError(
                "load_type_not_mapped",
                load_type=str(load_type),
                mapped=sorted(self._delegates),
            )
        return delegate

    def to_native(self, canonical: Mapping[str, Any]) -> dict[str, Any]:
        """canonical（含 `load_type`）→ 该荷载类型的原生条目。"""
        load_type = canonical.get("load_type")
        if load_type is None:
            raise MidasValidationError(
                "transformer_required_field_missing", transformer=self.name, field="load_type"
            )
        payload = {key: value for key, value in canonical.items() if key != "load_type"}
        return self.delegate(str(load_type)).to_native(payload)

    def from_native(self, load_type: str, native: Mapping[str, Any]) -> dict[str, Any]:
        """原生条目 + `load_type` → canonical。"""
        canonical = self.delegate(load_type).from_native(native)
        canonical["load_type"] = str(load_type).upper()
        return canonical


# ===== 分析 / 视图 / 设计 / 结果 =====


class AnalysisTransformer(SchemaBoundTransformer):
    """Analysis（`docs/04` §35–§41）：分析参数 ↔ `DOC.ANAL` 的 `Argument.TYPE`。

    §35：`ANALYSIS.STATIC` **不得**硬编码成 `/anal/STATIC`；执行一律经 `DOC.ANAL`。
    §36：是否支持某种分析由 Capability 决定，本类只做参数转换。
    """

    name = "midas.anal.v1"
    endpoint = "DOC.ANAL"
    fields = (FieldMap("analysis_type", "TYPE"),)


class ViewTransformer(SchemaBoundTransformer):
    """View（`docs/04` §48–§51）：视图状态 → `VIEW.CAPTURE` 的 `Argument`。

    §49：View **不得**修改 Canonical Model —— 本类只产出视图请求，不回流模型数据。
    §50：截图产物经 `ArtifactStorage` 落 `artifact_id`，**不**把图片塞进 task JSON。
    """

    name = "midas.view.capture.v1"
    endpoint = "VIEW.CAPTURE"
    fields = (
        FieldMap("figure_name", "FIGURE_NAME"),
        FieldMap("export_path", "EXPORT_PATH"),
        FieldMap("width", "WIDTH"),
        FieldMap("height", "HEIGHT"),
        FieldMap("active", "ACTIVE"),
        FieldMap("angle", "ANGLE"),
    )


class DesignTransformer(SchemaBoundTransformer):
    """Design（`docs/04` §52–§55）：设计执行参数 ↔ `CODE-ANAL` 的 `Argument`。

    §53：不能把 `ANALYSIS.STATIC` 的结果当成 `DESIGN.STEEL` 的结果。
    §55：`DESIGN.OPTIMIZE` 的写回必须经确认 —— 由 Core 的 Confirmation 把关，
    本类只做参数转换（`apply` 由 Operation 层承载）。
    """

    name = "midas.design.steel.v1"
    endpoint = "DESIGN.STEEL.KDS-41-30-2022.CODE-ANAL"
    fields = (
        FieldMap("perform_type", "PERFORM_TYPE"),
        FieldMap("elements", "ELEMS"),
        FieldMap("sections", "SECTIONS"),
    )


class ResultRequestTransformer(SchemaBoundTransformer):
    """Result 请求（`docs/04` §42–§47）：canonical → `POST.TABLE` 的 `Argument`。

    §47 的分页 / 过滤字段（`node_ids` / `element_ids`）在 `POST.TABLE` 的 Schema 里
    **没有**对应条目（`additionalProperties: false`），故过滤在**解析后**由 Adapter 在
    canonical 侧完成（见 `adapter.py`），**不**臆造请求字段（见裁决 8）。
    """

    name = "midas.result.request.v1"
    endpoint = "POST.TABLE"
    fields = (
        FieldMap("table_type", "TABLE_TYPE", required=True),
        FieldMap("components", "COMPONENTS"),
        FieldMap("load_cases", "LOAD_CASE_NAMES"),
        FieldMap("unit", "UNIT"),
        FieldMap("table_name", "TABLE_NAME"),
    )


class _ResultRowTransformer:
    """结果行解析基类（`docs/04` §43–§46）。"""

    name: ClassVar[str] = ""
    table_type: ClassVar[str] = ""
    columns: ClassVar[Mapping[str, tuple[str, ...]]] = {}
    numeric: ClassVar[tuple[str, ...]] = ()

    def parse(self, native: Mapping[str, Any], *, table_name: str = "") -> dict[str, Any]:
        """原生结果表 → canonical（`{table_type, units, rows}`）。

        ⚠️ 未映射的列**原样**保留在 `raw` 里（**不**丢信息、**不**改名）；
        取不到的字段写 `None`，**不**虚构 `0`（`docs/04` §44）。
        """
        table = parse_table(native, table_name=table_name or self.table_type)
        rows: list[dict[str, Any]] = []
        for row in table.rows:
            canonical: dict[str, Any] = {}
            for key, aliases in self.columns.items():
                column = table.column(*aliases)
                raw = row.get(column) if column is not None else None
                canonical[key] = _number(raw) if key in self.numeric else _text(raw)
            canonical["raw"] = dict(row)
            rows.append(canonical)
        return {
            "table_type": self.table_type,
            "units": dict(table.units),
            "columns": list(table.head),
            "rows": rows,
        }


class DisplacementTransformer(_ResultRowTransformer):
    """位移（`docs/04` §43）：`node_id/ux..rz` + **显式** `units`（`length` / `rotation`）。

    列名取自官方手册 `POST/TABLE` 的 `COMPONENTS` 示例（`Node` / `Load` / `DX` …
    `RZ`）；单位取自响应体的 `DIST` / `FORCE`，取不到即 `None`（**不**假设 SI）。
    """

    name = "midas.result.displacement.v1"
    table_type = "DISPLACEMENTG"
    columns = {
        "node_id": ("Node",),
        "load_case": ("Load",),
        "stage": ("Stage",),
        "step": ("Step",),
        "ux": ("DX", "Dx"),
        "uy": ("DY", "Dy"),
        "uz": ("DZ", "Dz"),
        "rx": ("RX", "Rx"),
        "ry": ("RY", "Ry"),
        "rz": ("RZ", "Rz"),
    }
    numeric = ("ux", "uy", "uz", "rx", "ry", "rz")


class ReactionTransformer(_ResultRowTransformer):
    """反力（`docs/04` §44）：必须含 `load_case` / `stage` / `step` / `units`。"""

    name = "midas.result.reaction.v1"
    table_type = "REACTIONG"
    columns = {
        "node_id": ("Node",),
        "load_case": ("Load",),
        "stage": ("Stage",),
        "step": ("Step",),
        "fx": ("FX", "Fx"),
        "fy": ("FY", "Fy"),
        "fz": ("FZ", "Fz"),
        "mx": ("MX", "Mx"),
        "my": ("MY", "My"),
        "mz": ("MZ", "Mz"),
    }
    numeric = ("fx", "fy", "fz", "mx", "my", "mz")


class ElementForceTransformer(_ResultRowTransformer):
    """构件内力（`docs/04` §45）：六个分量 + `coordinate_system` / `local_axis_definition`。

    不同软件的局部坐标定义不同，故这两项**必须**保留（取不到 → `None`，**不**假设）。
    """

    name = "midas.result.element_force.v1"
    table_type = "BEAMFORCE"
    columns = {
        "element_id": ("Elem", "Element"),
        "load_case": ("Load",),
        "position": ("Part", "Position"),
        "axial": ("Axial", "Axial Force"),
        "shear_y": ("Shear-y", "ShearY"),
        "shear_z": ("Shear-z", "ShearZ"),
        "torsion": ("Torsion",),
        "moment_y": ("Moment-y", "MomentY"),
        "moment_z": ("Moment-z", "MomentZ"),
        "coordinate_system": ("CS", "Coordinate System"),
        "local_axis_definition": ("Local Axis", "LocalAxis"),
    }
    numeric = ("axial", "shear_y", "shear_z", "torsion", "moment_y", "moment_z")


class DesignResultTransformer(_ResultRowTransformer):
    """设计结果（`docs/04` §54）：`element_id` / `ratio` / `status` / `code`。

    `CODE-X` 只作占位（见裁决 6）：`code` 原样透传，**不**伪装成官方规范名。
    """

    name = "midas.result.design.v1"
    table_type = "CODE-TABLE"
    columns = {
        "element_id": ("Elem", "Element"),
        "member_id": ("Member", "MEMB"),
        "code": ("Code", "CODE"),
        "ratio": ("Ratio", "Utilization", "Util"),
        "status": ("Status", "Result", "Check"),
    }
    numeric = ("ratio",)


TRANSFORMER_REGISTRY: Final[dict[str, type[Any]]] = {
    "midas.anal.v1": AnalysisTransformer,
    "midas.bmld.v1": BeamLoadTransformer,
    "midas.bodf.v1": BodyForceTransformer,
    "midas.cnld.v1": NodalLoadTransformer,
    "midas.cons.v1": BoundaryTransformer,
    "midas.design.steel.v1": DesignTransformer,
    "midas.elem.v1": ElementTransformer,
    "midas.matl.v1": MaterialTransformer,
    "midas.load.v1": LoadTransformer,
    "midas.node.v1": NodeTransformer,
    "midas.pres.v1": PressureLoadTransformer,
    "midas.result.design.v1": DesignResultTransformer,
    "midas.result.displacement.v1": DisplacementTransformer,
    "midas.result.element_force.v1": ElementForceTransformer,
    "midas.result.reaction.v1": ReactionTransformer,
    "midas.result.request.v1": ResultRequestTransformer,
    "midas.sect.v1": SectionTransformer,
    "midas.stld.v1": LoadCaseTransformer,
    "midas.view.capture.v1": ViewTransformer,
}
"""`docs/04` §103 的 Transformer 名 → 实现（数据库只存**名字**）。"""


# ===== 路径辅助（只做机械变换）=====


def _leaf_of(path: str) -> str:
    """取路径的末段字段名（`PARAM[].ELAST` → `ELAST`）。"""
    return path.split(".")[-1].replace("[]", "")


def _assign(target: dict[str, Any], path: str, value: Any) -> None:
    """按路径写入（`A.B` 嵌套；`PARAM[]` 表示数组首元素）。"""
    segments = path.split(".")
    node = target
    for segment in segments[:-1]:
        key = segment.replace("[]", "")
        child = node.get(key)
        if "[]" in segment:
            if not isinstance(child, list):
                child = [{}]
                node[key] = child
            node = child[0]
        else:
            if not isinstance(child, dict):
                child = {}
                node[key] = child
            node = child
    node[segments[-1].replace("[]", "")] = value


def _lookup(source: Mapping[str, Any], path: str) -> Any:
    """按路径读取（缺任一环 → `None`，**不**虚构默认值）。"""
    node: Any = source
    for segment in path.split("."):
        key = segment.replace("[]", "")
        if not isinstance(node, Mapping):
            return None
        node = node.get(key)
        if "[]" in segment and isinstance(node, Sequence) and not isinstance(node, str):
            node = node[0] if node else None
    return node


def _number(value: Any) -> float | None:
    """数值列 → `float`；不可解析（`None` / `"-"` / 空串）→ `None`（**不**虚构 `0`）。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "--", "N/A"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _text(value: Any) -> str | None:
    """文本列 → `str`；不可用（`None` / `"-"` / 空串）→ `None`。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "--", "N/A"}:
        return None
    return text
