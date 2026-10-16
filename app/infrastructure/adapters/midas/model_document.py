"""模型文档层：MIDAS 全模型 JSON（`DBG`）↔ 参数化 canonical 模型（`docs/07` §16.1 **R168**）。

为什么需要这一层
----------------
`DOC.EXPORT` 产出的 JSON 是所有表的**原生**快照（`{"DBG": {表名: {id: {原生字段}}}}`），
而 `DOC.IMPORT` 吃的是同一形状。它是**机械的、无工程语义的**：
字段名是厂商大写（`X` / `SECT_NAME` / `PARAM[].ELAST`），单位随模型走，且表名与
Registry 端点**只是相交、不可互推**（实测：导出 218 张表 vs 登记 244 个 `DB.*` 端点）。

参数化建模需要的是**规范化、与传输解耦**的表示：小写 canonical 字段名、单位显式、
稳定的实体顺序。本模块就是这两者之间的**转换层** —— 它**不**新增任何 canonical 字段名，
而是**复用** `transforms.py` 里已经存在的 `TRANSFORMER_REGISTRY`（`docs/07` §7.4 的字段表）。

⚠️ 本模块**不**做 I/O、**不**碰 Registry 以外的状态（纯函数 + 已绑定的 Transformer）。
传输由 Adapter 的 `MODEL.EXPORT` / `MODEL.IMPORT` 两个 Operation 负责。

口径（实测锚定，见 `registry/live/model_doc_probe.json`）
--------------------------------------------------------
1. **空表保留**：导出里空表也占位（实测 204 / 218 张为空）⇒ canonical 侧同样保留
   空列表，**不**静默丢弃（否则「模型里有什么」不可判断）。
2. **顺序稳定**：canonical 实体按**数值 id 升序**排列（原生 JSON 的键序不可依赖）。
3. **id 口径**：原生 JSON 的键是**字符串**（`"1"`），canonical 侧还原为 `int`；
   非数值键（极少）**如实保留为字符串**，不臆造。
4. **未映射的表**：表名在本层没有 Transformer ⇒ **原样透传**（`native` 块），
   既不丢弃也不假装理解 —— 这样 `canonical → native` 往返对**任意**模型都无损。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from app.infrastructure.adapters.midas.adapter import _explode_items
from app.infrastructure.adapters.midas.transforms import TRANSFORMER_REGISTRY

__all__ = [
    "MODEL_TABLES",
    "ModelDocument",
    "canonical_to_native",
    "native_to_canonical",
]

DBG_ROOT: Final[str] = "DBG"
"""导出文件的根键（实测：`{"DBG": {...}}`，别无他键）。"""

MODEL_TABLES: Final[tuple[tuple[str, str], ...]] = (
    ("UNIT", "midas.unit.v1"),
    ("NODE", "midas.node.v1"),
    ("ELEM", "midas.elem.v1"),
    ("MATL", "midas.matl.v1"),
    ("SECT", "midas.sect.v1"),
    ("CONS", "midas.cons.v1"),
    ("STLD", "midas.stld.v1"),
)
"""主干实体：canonical 模型**一等公民**的表 → Transformer 名。

顺序 = 建模的**依赖顺序**（单位 → 节点 → 单元 → 材料 → 截面 → 边界 → 工况）：
`ELEM` 引用 `MATL` / `SECT`，`CONS` 引用 `NODE` ⇒ 按此序回写不会出现悬空引用。

⚠️ 本常量**只**声明「哪些表有一等公民待遇」，**不**声称这是全部可建模的表 ——
其余表走 `native` 透传（见模块 docstring 口径 4）。
"""

_TABLE_TRANSFORMERS: Final[dict[str, str]] = dict(MODEL_TABLES)


@dataclass(frozen=True, slots=True)
class ModelDocument:
    """一个模型的**参数化**表示（与传输 / 厂商字段名解耦）。"""

    entities: Mapping[str, tuple[dict[str, Any], ...]]
    """表名 → canonical 实体（按 id 升序）。主干表在此。"""

    native: Mapping[str, Mapping[str, Any]]
    """表名 → **原样**保留的原生块（未映射的表，以及映射表的原生形态）。

    ⚠️ 映射表**同时**出现在 `entities`（规范化视图）与 `native`（无损视图）里 ——
    这样「用 canonical 参数化建模」与「一字不改地回写」两件事都做得到。
    """

    units: Mapping[str, Any] = field(default_factory=dict)
    """单位系统（canonical，来自 `UNIT` 表；空模型 ⇒ `{}`）。"""

    def table_names(self) -> tuple[str, ...]:
        """本模型出现过的**全部**表名（升序）。"""
        return tuple(sorted(self.native))


def _sorted_items(block: Any) -> list[tuple[Any, Any]]:
    """把原生块摊成 `(id, 记录)` 列表并按**数值 id 升序**（口径 2 / 3）。"""
    if not isinstance(block, Mapping):
        return []
    items = list(block.items())

    def sort_key(item: tuple[Any, Any]) -> tuple[int, int | str]:
        raw = item[0]
        try:
            return (0, int(str(raw)))
        except (TypeError, ValueError):
            return (1, str(raw))

    items.sort(key=sort_key)
    return items


def _canonical_id(raw: Any) -> int | str:
    """原生键 → canonical id（数值键转 `int`，非数值键如实保留为字符串）。"""
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return str(raw)


def _registry_transformers(registry: Any) -> dict[str, Any]:
    """实例化**本层用到的** Transformer（按名字取 `TRANSFORMER_REGISTRY`，**不**自建字段表）。

    ⚠️ 只碰 `MODEL_TABLES` 里声明的那几个 —— `TRANSFORMER_REGISTRY` 里有一部分是
    **结果类 / 设计类**转换器（`DesignResultTransformer` 等），它们的构造签名不同
    （无参），全量实例化会 `TypeError`。本层与它们无关。
    """
    return {
        name: TRANSFORMER_REGISTRY[name](registry)
        for _, name in MODEL_TABLES
        if name in TRANSFORMER_REGISTRY
    }


def _native_record_of(block: Any, entity_id: Any) -> Mapping[str, Any]:
    """从原生块里取某个编号的**记录**（`ITEMS` 形态则取首个元素）。"""
    if not isinstance(block, Mapping):
        return {}
    raw = block.get(str(entity_id))
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        return {}
    for name in ("ITEMS", "items"):
        nested = raw.get(name)
        if isinstance(nested, Sequence) and not isinstance(nested, str):
            first = next((item for item in nested if isinstance(item, Mapping)), None)
            return dict(first) if first is not None else {}
    return dict(raw)


def _merge_native(original: Mapping[str, Any], produced: Mapping[str, Any]) -> dict[str, Any]:
    """把原生记录的**未表达字段**合并回 canonical 产出的记录（`produced` 优先）。

    规则：同键时 `produced` 赢（那是 canonical 明确表达过的）；仅在 `original` 里
    存在的键**原样保留**；两侧都是映射则递归（如 `SECT_BEFORE` 这类子树）。
    """
    merged = dict(original)
    for key, value in produced.items():
        if key in merged and isinstance(merged[key], Mapping) and isinstance(value, Mapping):
            merged[key] = _merge_native(merged[key], value)
        else:
            merged[key] = value
    return merged


def native_to_canonical(payload: Mapping[str, Any], registry: Any) -> ModelDocument:
    """原生 `DBG` 文档 → 参数化 `ModelDocument`。

    Args:
        payload: `DOC.EXPORT` 产出的整份 JSON（或等价的 `{"DBG": {...}}`）。
        registry: 已装载的 `MidasRegistry`（Transformer 的白名单来源）。

    Returns:
        规范化文档。未映射的表原样进 `native`；映射表**同时**产出 canonical 实体。

    Raises:
        ValueError: `payload` 没有 `DBG` 根（不是本层认识的形状 ⇒ 不猜）。
    """
    block = payload.get(DBG_ROOT)
    if not isinstance(block, Mapping):
        raise ValueError("model_document: 输入缺少 `DBG` 根 ⇒ 不是 DOC.EXPORT 的形状")

    transformers = _registry_transformers(registry)
    entities: dict[str, tuple[dict[str, Any], ...]] = {}
    native: dict[str, Mapping[str, Any]] = {}

    for table, table_block in block.items():
        name = str(table)
        if isinstance(table_block, Mapping):
            native[name] = dict(table_block)
        else:  # 形状异常 ⇒ 如实包一层，不丢
            native[name] = {"__raw__": table_block}

        transformer_name = _TABLE_TRANSFORMERS.get(name)
        if transformer_name is None:
            continue
        transformer = transformers.get(transformer_name)
        if transformer is None:  # pragma: no cover - 注册表缺项属配置错误
            continue

        rows: list[dict[str, Any]] = []
        for raw_id, record in _sorted_items(table_block):
            if not isinstance(record, Mapping):
                continue
            # ⚠️ **P158 / R130 复用**：`ITEMS` 形态的表（`DB.CONS` / `DB.CNLD` / `DB.BMLD` /
            # `DB.PRES`）读回来是 `{<编号>: {"ITEMS": [<条目>, …]}}` ⇒ **必须**逐元素展开，
            # 否则 Transformer 在包装体这一层取不到字段、canonical 全 `None`（实测踩到过）。
            for _key, entry in _explode_items(str(raw_id), record):
                canonical = dict(transformer.from_native(entry))
                canonical.setdefault("id", _canonical_id(raw_id))
                rows.append(canonical)
        entities[name] = tuple(rows)

    units = entities.get("UNIT", ())
    return ModelDocument(
        entities=entities,
        native=native,
        units=dict(units[0]) if units else {},
    )


def canonical_to_native(document: ModelDocument, registry: Any) -> dict[str, Any]:
    """参数化 `ModelDocument` → 原生 `DBG` 文档（可交给 `DOC.IMPORT`）。

    ⚠️ **无损优先**：对每张表，先取 canonical 实体（若有）转成原生记录；
    表在本层**没有** canonical 视图时（或 canonical 为空而 native 非空），
    原样使用 `native` 块。⇒ 用 canonical 改过主干表、其余表一字不动，往返仍然完整。

    Raises:
        ValueError: canonical 实体缺 `id`（无法定位行 ⇒ 不猜编号）。
    """
    transformers = _registry_transformers(registry)
    out: dict[str, Any] = {}

    for table in sorted(set(document.native) | set(document.entities)):
        transformer_name = _TABLE_TRANSFORMERS.get(table)
        rows = document.entities.get(table)

        raw_block = document.native.get(table)
        transformer = transformers.get(transformer_name) if transformer_name else None
        # 三种情形直接**原样回写**（无损，不经 canonical）：
        #   ① 本层没有该表的 canonical 视图；② 注册表缺项；③ canonical 为空而 native 非空
        #      （= 这一层没参与编辑）。
        if transformer is None or not rows:
            # ⚠️ **空表也要落回**（模块口径 1：导出里空表占位，canonical 侧同样保留）——
            #    判据是 `raw_block is not None`（该表在文档里**出现过**），
            #    而**不是**真值判断：空 dict 是 falsy，用真值判断会把空表整张丢掉（实测踩到）。
            if transformer is None or raw_block is not None:
                out[table] = {str(k): v for k, v in _sorted_items(raw_block)}
            continue

        items_style = bool(getattr(transformer, "is_items_style", lambda: False)())
        block: dict[str, Any] = {}
        for entity in rows:
            if "id" not in entity:
                raise ValueError(f"model_document: `{table}` 的 canonical 实体缺 `id` ⇒ 无法定位行")
            entity_id = entity["id"]
            # ⚠️ `id` 是本层的**行定位键**（原生侧由 `{<id>: {...}}` 的外层键承载），
            #    **不**属于 Transformer 的字段白名单 ⇒ 不能喂给 `to_native`
            #    （否则 `transformer_field_not_in_schema`）。
            payload = {key: value for key, value in entity.items() if key != "id"}
            record = dict(transformer.to_native(payload))
            # ⚠️ **canonical 只是「可参数化的视图」，不是原生字段的**全集**：
            #    `transforms.py` 的白名单只覆盖**已裁决**字段 —— 例如 `DB.ELEM` 的 `STYPE`、
            #    `DB.SECT` 的整棵 `SECT_BEFORE` 子树都**不在** canonical 里（实测）。
            #    ⇒ 回写时把**原生侧多出来的部分**补回来，canonical 里表达过的字段以 canonical 为准。
            #    这样「用 canonical 改主干字段」与「未表达字段一字不动」同时成立。
            original = _native_record_of(document.native.get(table), entity_id)
            record = _merge_native(original, record)
            # ⚠️ **P158 / R130 的另一半**：`ITEMS` 形态的表（`DB.CONS` / `DB.CNLD` /
            # `DB.BMLD` / `DB.PRES`）原生侧是 `{<编号>: {"ITEMS": [<条目>, …]}}` ——
            # 回写时**必须**把行包回 `ITEMS` 数组，否则原生解不出条目（往返必失真，实测）。
            block[str(entity_id)] = {"ITEMS": [record]} if items_style else record
        out[table] = block

    return {DBG_ROOT: out}
