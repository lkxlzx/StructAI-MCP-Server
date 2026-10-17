"""参数化模型模板：`DOC.EXPORT` 的原生 `DBG` JSON ↔ 可填参数的模板文件（P180）。

为什么要这一层
--------------
`DOC.EXPORT` 的产出是**原生快照**：表名 / 字段名是厂商大写，数值是**当前模型的具体值**。
把这份快照直接当模板用，就要求调用方（AI Agent / 前端）**理解整份 218 张表**才能改对一处。
本层把「**哪些数值是工程参数**」从数据里**显式抽出来**：

    DBG JSON（导出快照）
        --build_template-->  模板 { format, version, meta, parameters, model }
        --materialize----->  DBG JSON（可直接交给 `DOC.IMPORT`）

- `model`：原生 `DBG` 块（**去掉**会话元数据 `PJCF` 与颜色表 `CO_*`），
  可参数化的标量**保留位置**，用 `${参数名}` 占位；
- `parameters`：参数名 → `{value, kind, unit, description, source}`，
  `value` 就是**默认值**（= 样本模型的原值），改 `value` 即可改模型；
- `materialize` 把参数填回 `model`，产出 `{"DBG": {...}}`。

口径（**不发明、不丢表**）
--------------------------
1. 只参数化**有清晰工程含义**的标量：单位、材料、截面尺寸、节点坐标（小模型）、
   工况名、荷载分量、组合系数、分析控制参数、支座约束（小模型）。
2. 其余表 / 字段**原样保留**（含大量隐藏表，如 `THIK` / `RIGD` / `NMAS` / `SDSP`）——
   模板不是「精简模型」，导入后行为必须与样本一致。
3. `PJCF`（项目文件名 / 路径 / 时间戳）**不进模板**：它是会话状态，不是模型数据；
   导入它会把别人的项目名写进当前项目（`DOC.IMPORT` 是合并语义）。
   `CO_M` / `CO_S` / `CO_T`（颜色表）同样排除：与工程无关，且合并导入会覆盖用户配色。
4. `materialize` **严格**：未知占位符 / 未知参数 / 类型不匹配 ⇒ 报错，**不猜**。
5. 序列化**稳定**：表名升序、行按数值 id 升序、缩进 2、结尾换行 —— 同样输入逐字节同文本。

分层：只依赖标准库；不碰 I/O、不发请求、不引用 Registry。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Final

__all__ = [
    "EXCLUDED_TABLES",
    "NODE_PARAM_LIMIT",
    "SUPPORT_PARAM_LIMIT",
    "TEMPLATE_FORMAT",
    "TEMPLATE_VERSION",
    "MaterializeError",
    "build_template",
    "dumps_template",
    "materialize",
    "parameter_values",
]

TEMPLATE_FORMAT: Final[str] = "structai.model_template"
TEMPLATE_VERSION: Final[int] = 1

EXCLUDED_TABLES: Final[frozenset[str]] = frozenset({"PJCF", "CO_M", "CO_S", "CO_T"})
"""不进模板的表（会话元数据 + 颜色表；见模块口径 3）。"""

NODE_PARAM_LIMIT: Final[int] = 64
"""节点数 ≤ 此值时逐坐标参数化；更大的模型保留字面坐标（模板不至于无法阅读）。"""

SUPPORT_PARAM_LIMIT: Final[int] = 24
"""约束行数 ≤ 此值时逐行参数化约束串。"""

_PLACEHOLDER_PREFIX: Final[str] = "${"
_PLACEHOLDER_SUFFIX: Final[str] = "}"

_SECTION_DIMENSION_NAMES: Final[dict[str, tuple[str, ...]]] = {
    "H": ("h", "b", "tw", "tf"),
    "B": ("h", "b", "tw", "tf"),
    "SB": ("h", "b"),
    "P": ("d",),
    "SR": ("d",),
}
"""常见截面 `vSIZE` 各下标的工程含义（未列出的形状用 `dim[i]`）。"""


class MaterializeError(ValueError):
    """模板填写错误（未知参数 / 占位符 / 类型不匹配）——**不猜、不降级**。"""


def _id_key(raw: Any) -> tuple[int, int | str]:
    """行 id 排序键：数值优先，其次字符串（与 `model_document` 同口径）。"""
    try:
        return (0, int(str(raw)))
    except (TypeError, ValueError):
        return (1, str(raw))


def _sorted_rows(block: Any) -> list[tuple[str, Any]]:
    """把表块摊成 `(id, 行)` 并按数值 id 升序。"""
    if not isinstance(block, Mapping):
        return []
    rows = ((str(key), value) for key, value in block.items())
    return sorted(rows, key=lambda kv: _id_key(kv[0]))


def _placeholder(name: str) -> str:
    """参数名的占位符字面量。"""
    return f"{_PLACEHOLDER_PREFIX}{name}{_PLACEHOLDER_SUFFIX}"


def _kind_of(value: Any) -> str:
    """参数类型标签（供填写方判断该填什么）。"""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    return "string"


class _Parameters:
    """参数收集器（统一维护 `parameters` 与 `source` 说明）。"""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    def add(
        self,
        name: str,
        value: Any,
        *,
        source: str,
        description: str,
        unit: str | None = None,
    ) -> str:
        """登记一个参数并返回其占位符。"""
        entry: dict[str, Any] = {
            "value": value,
            "kind": _kind_of(value),
            "description": description,
            "source": source,
        }
        if unit is not None:
            entry["unit"] = unit
        self.items[name] = entry
        return _placeholder(name)


def _parameterize_unit(block: Any, params: _Parameters) -> dict[str, Any]:
    """单位系统（`UNIT` 表只有一行）。"""
    rows = _sorted_rows(block)
    if not rows:
        return {}
    row_id, row = rows[0]
    if not isinstance(row, Mapping):
        return dict(block)
    labels = {
        "FORCE": ("units.force", "力单位（如 KIPS / TONF / KN）", "force"),
        "DIST": ("units.dist", "长度单位（如 FT / M / IN）", "length"),
        "HEAT": ("units.heat", "热量单位（如 BTU / KCAL）", "heat"),
        "TEMPER": ("units.temper", "温度单位（如 C / F）", "temperature"),
    }
    out = dict(row)
    for field, (name, description, unit) in labels.items():
        if field in row:
            out[field] = params.add(
                name,
                row[field],
                source=f"UNIT/{row_id}/{field}",
                description=description,
                unit=unit,
            )
    return {row_id: out}


def _parameterize_material(block: Any, params: _Parameters) -> dict[str, Any]:
    """材料：名称 + 弹性模量 / 泊松比 / 密度 / 质量密度 / 线膨胀系数。"""
    out: dict[str, Any] = {}
    for row_id, row in _sorted_rows(block):
        if not isinstance(row, Mapping):
            out[row_id] = row
            continue
        record = dict(row)
        if "NAME" in record:
            record["NAME"] = params.add(
                f"material.{row_id}.name",
                record["NAME"],
                source=f"MATL/{row_id}/NAME",
                description="材料名称",
            )
        if "TYPE" in record:
            record["TYPE"] = params.add(
                f"material.{row_id}.type",
                record["TYPE"],
                source=f"MATL/{row_id}/TYPE",
                description="材料类型（USER / 规范库类型）",
            )
        param_list = record.get("PARAM")
        if isinstance(param_list, Sequence) and param_list and isinstance(param_list[0], Mapping):
            first = dict(param_list[0])
            fields = {
                "ELAST": ("elastic_modulus", "弹性模量 E", "force/length^2"),
                "POISN": ("poisson_ratio", "泊松比 ν", None),
                "DEN": ("density", "重度 / 密度", "force/length^3"),
                "MASS": ("mass_density", "质量密度", "mass/length^3"),
                "THERMAL": ("thermal_coefficient", "线膨胀系数 α", "1/temperature"),
            }
            for field, (suffix, description, unit) in fields.items():
                if field in first:
                    first[field] = params.add(
                        f"material.{row_id}.{suffix}",
                        first[field],
                        source=f"MATL/{row_id}/PARAM[0].{field}",
                        description=description,
                        unit=unit,
                    )
            record["PARAM"] = [first, *list(param_list[1:])]
        out[row_id] = record
    return out


def _parameterize_section(block: Any, params: _Parameters) -> dict[str, Any]:
    """截面：名称 / 形状 / `vSIZE` 尺寸数组（按形状给出尺寸名）。"""
    out: dict[str, Any] = {}
    for row_id, row in _sorted_rows(block):
        if not isinstance(row, Mapping):
            out[row_id] = row
            continue
        record = json.loads(json.dumps(row))  # 深拷贝（保持原生结构）
        if "SECT_NAME" in record:
            record["SECT_NAME"] = params.add(
                f"section.{row_id}.name",
                record["SECT_NAME"],
                source=f"SECT/{row_id}/SECT_NAME",
                description="截面名称",
            )
        before = record.get("SECT_BEFORE")
        if not isinstance(before, dict):
            out[row_id] = record
            continue
        shape = str(before.get("SHAPE") or "")
        if shape:
            before["SHAPE"] = params.add(
                f"section.{row_id}.shape",
                before["SHAPE"],
                source=f"SECT/{row_id}/SECT_BEFORE.SHAPE",
                description="截面形状代码（H / B / SB / P / SR …）",
            )
        sect_i = before.get("SECT_I")
        if isinstance(sect_i, dict) and isinstance(sect_i.get("vSIZE"), list):
            names = _SECTION_DIMENSION_NAMES.get(shape)
            sizes = []
            for index, value in enumerate(sect_i["vSIZE"]):
                label = names[index] if names and index < len(names) else f"dim{index}"
                sizes.append(
                    params.add(
                        f"section.{row_id}.vsize.{index}",
                        value,
                        source=f"SECT/{row_id}/SECT_BEFORE.SECT_I.vSIZE[{index}]",
                        description=f"截面尺寸 {label}（SHAPE={shape or '?'}）",
                        unit="length",
                    )
                )
            sect_i["vSIZE"] = sizes
        out[row_id] = record
    return out


def _parameterize_node(block: Any, params: _Parameters) -> dict[str, Any]:
    """节点坐标（仅小模型；大模型保留字面值）。"""
    rows = _sorted_rows(block)
    if len(rows) > NODE_PARAM_LIMIT:
        return dict(block) if isinstance(block, Mapping) else {}
    out: dict[str, Any] = {}
    for row_id, row in rows:
        if not isinstance(row, Mapping):
            out[row_id] = row
            continue
        record = dict(row)
        axes = (("X", "x", "length"), ("Y", "y", "length"), ("Z", "z", "length"))
        for field, suffix, unit in axes:
            if field in record:
                record[field] = params.add(
                    f"node.{row_id}.{suffix}",
                    record[field],
                    source=f"NODE/{row_id}/{field}",
                    description=f"节点 {row_id} 的 {field} 坐标",
                    unit=unit,
                )
        out[row_id] = record
    return out


def _parameterize_supports(block: Any, params: _Parameters) -> dict[str, Any]:
    """边界条件：`ITEMS[].CONSTRAINT`（7 位串，DX DY DZ RX RY RZ RW；仅小模型）。"""
    rows = _sorted_rows(block)
    if len(rows) > SUPPORT_PARAM_LIMIT:
        return dict(block) if isinstance(block, Mapping) else {}
    out: dict[str, Any] = {}
    for row_id, row in rows:
        if not isinstance(row, Mapping):
            out[row_id] = row
            continue
        record = json.loads(json.dumps(row))
        items = record.get("ITEMS")
        if isinstance(items, list) and items and isinstance(items[0], Mapping):
            first = dict(items[0])
            if "CONSTRAINT" in first:
                first["CONSTRAINT"] = params.add(
                    f"support.{row_id}.constraint",
                    first["CONSTRAINT"],
                    source=f"CONS/{row_id}/ITEMS[0].CONSTRAINT",
                    description=(f"节点 {row_id} 的约束串（7 位：DX DY DZ RX RY RZ RW，1=约束）"),
                )
            record["ITEMS"] = [first, *list(items[1:])]
        out[row_id] = record
    return out


def _parameterize_load_cases(block: Any, params: _Parameters) -> dict[str, Any]:
    """荷载工况名称（`STLD`）。"""
    out: dict[str, Any] = {}
    for row_id, row in _sorted_rows(block):
        if not isinstance(row, Mapping):
            out[row_id] = row
            continue
        record = dict(row)
        if "NAME" in record:
            record["NAME"] = params.add(
                f"load_case.{row_id}.name",
                record["NAME"],
                source=f"STLD/{row_id}/NAME",
                description=f"荷载工况 {row_id} 的名称",
            )
        out[row_id] = record
    return out


def _parameterize_nodal_loads(block: Any, params: _Parameters) -> dict[str, Any]:
    """节点荷载（`CNLD`）：每个 ITEM 的 FX / FY / FZ / MX / MY / MZ。"""
    out: dict[str, Any] = {}
    fields = (("FX", "fx"), ("FY", "fy"), ("FZ", "fz"), ("MX", "mx"), ("MY", "my"), ("MZ", "mz"))
    for row_id, row in _sorted_rows(block):
        if not isinstance(row, Mapping):
            out[row_id] = row
            continue
        record = json.loads(json.dumps(row))
        items = record.get("ITEMS")
        if isinstance(items, list):
            new_items = []
            for position, item in enumerate(items):
                if not isinstance(item, Mapping):
                    new_items.append(item)
                    continue
                entry = dict(item)
                for field, suffix in fields:
                    if field in entry:
                        entry[field] = params.add(
                            f"nodal_load.{row_id}.{position}.{suffix}",
                            entry[field],
                            source=f"CNLD/{row_id}/ITEMS[{position}].{field}",
                            description=f"节点 {row_id} 荷载分量 {field}",
                            unit="force" if field[0] == "F" else "force*length",
                        )
                new_items.append(entry)
            record["ITEMS"] = new_items
        out[row_id] = record
    return out


def _parameterize_beam_loads(block: Any, params: _Parameters) -> dict[str, Any]:
    """梁单元荷载（`BMLD`）：每个 ITEM 的 `P` 荷载数组。"""
    out: dict[str, Any] = {}
    for row_id, row in _sorted_rows(block):
        if not isinstance(row, Mapping):
            out[row_id] = row
            continue
        record = json.loads(json.dumps(row))
        items = record.get("ITEMS")
        if isinstance(items, list):
            new_items = []
            for position, item in enumerate(items):
                if not isinstance(item, Mapping):
                    new_items.append(item)
                    continue
                entry = dict(item)
                values = entry.get("P")
                if isinstance(values, list):
                    entry["P"] = [
                        params.add(
                            f"beam_load.{row_id}.{position}.p.{index}",
                            value,
                            source=f"BMLD/{row_id}/ITEMS[{position}].P[{index}]",
                            description=(
                                f"梁 {row_id} 荷载值 P[{index}]（TYPE={entry.get('TYPE', '?')}，"
                                f"方向 {entry.get('DIRECTION', '?')}）"
                            ),
                            unit="force or force/length",
                        )
                        for index, value in enumerate(values)
                    ]
                new_items.append(entry)
            record["ITEMS"] = new_items
        out[row_id] = record
    return out


def _parameterize_body_forces(block: Any, params: _Parameters) -> dict[str, Any]:
    """自重 / 体力（`BODF`）：`FV` 系数数组。"""
    out: dict[str, Any] = {}
    for row_id, row in _sorted_rows(block):
        if not isinstance(row, Mapping):
            out[row_id] = row
            continue
        record = dict(row)
        factors = record.get("FV")
        if isinstance(factors, list):
            record["FV"] = [
                params.add(
                    f"body_force.{row_id}.fv.{index}",
                    value,
                    source=f"BODF/{row_id}/FV[{index}]",
                    description=f"自重工况 {row_id} 的系数 FV[{index}]（X/Y/Z）",
                )
                for index, value in enumerate(factors)
            ]
        out[row_id] = record
    return out


def _parameterize_combinations(table: str, block: Any, params: _Parameters) -> dict[str, Any]:
    """荷载组合（`LCOM-*`）：`vCOMB[].FACTOR`。"""
    out: dict[str, Any] = {}
    for row_id, row in _sorted_rows(block):
        if not isinstance(row, Mapping):
            out[row_id] = row
            continue
        record = json.loads(json.dumps(row))
        if "NAME" in record:
            record["NAME"] = params.add(
                f"combination.{row_id}.name",
                record["NAME"],
                source=f"{table}/{row_id}/NAME",
                description=f"荷载组合 {row_id} 的名称",
            )
        entries = record.get("vCOMB")
        if isinstance(entries, list):
            new_entries = []
            for position, entry in enumerate(entries):
                if not isinstance(entry, Mapping):
                    new_entries.append(entry)
                    continue
                item = dict(entry)
                if "FACTOR" in item:
                    item["FACTOR"] = params.add(
                        f"combination.{row_id}.factor.{position}",
                        item["FACTOR"],
                        source=f"{table}/{row_id}/vCOMB[{position}].FACTOR",
                        description=(f"组合 {row_id} 中工况 {item.get('LCNAME', '?')} 的组合系数"),
                    )
                new_entries.append(item)
            record["vCOMB"] = new_entries
        out[row_id] = record
    return out


def _parameterize_analysis(tables: Mapping[str, Any], params: _Parameters) -> None:
    """分析控制参数（`EIGV` / `BUCK` / `NLCT` / `STYP`）。

    ⚠️ 这些表是**就地修改**（函数返回 `None`），因为它们分散在多张表里。
    """
    eigv = tables.get("EIGV")
    if isinstance(eigv, Mapping):
        for row_id, row in _sorted_rows(eigv):
            if not isinstance(row, Mapping):
                continue
            record = dict(row)
            for field, suffix, description in (
                ("iFREQ", "frequency_count", "提取的特征值 / 频率数量"),
                ("iITER", "iterations", "迭代次数上限"),
                ("TOL", "tolerance", "收敛容差"),
            ):
                if field in record:
                    record[field] = params.add(
                        f"analysis.eigen.{suffix}",
                        record[field],
                        source=f"EIGV/{row_id}/{field}",
                        description=description,
                    )
            eigv[row_id] = record  # type: ignore[index]

    buck = tables.get("BUCK")
    if isinstance(buck, Mapping):
        for row_id, row in _sorted_rows(buck):
            if not isinstance(row, Mapping):
                continue
            record = dict(row)
            if "MODE_NUM" in record:
                record["MODE_NUM"] = params.add(
                    "analysis.buckling.mode_count",
                    record["MODE_NUM"],
                    source=f"BUCK/{row_id}/MODE_NUM",
                    description="屈曲分析提取的模态数",
                )
            items = record.get("ITEMS")
            if isinstance(items, list):
                new_items = []
                for position, item in enumerate(items):
                    if not isinstance(item, Mapping):
                        new_items.append(item)
                        continue
                    entry = dict(item)
                    if "FACTOR" in entry:
                        entry["FACTOR"] = params.add(
                            f"analysis.buckling.factor.{position}",
                            entry["FACTOR"],
                            source=f"BUCK/{row_id}/ITEMS[{position}].FACTOR",
                            description=f"屈曲工况 {entry.get('LCNAME', '?')} 的比例系数",
                        )
                    new_items.append(entry)
                record["ITEMS"] = new_items
            buck[row_id] = record  # type: ignore[index]

    nlct = tables.get("NLCT")
    if isinstance(nlct, Mapping):
        for row_id, row in _sorted_rows(nlct):
            if not isinstance(row, Mapping):
                continue
            record = dict(row)
            for field, suffix, description in (
                ("NUMBER_STEPS", "steps", "非线性荷载步数"),
                ("MAX_ITERATIONS", "max_iterations", "每步最大迭代次数"),
            ):
                if field in record:
                    record[field] = params.add(
                        f"analysis.nonlinear.{suffix}",
                        record[field],
                        source=f"NLCT/{row_id}/{field}",
                        description=description,
                    )
            nlct[row_id] = record  # type: ignore[index]

    styp = tables.get("STYP")
    if isinstance(styp, Mapping):
        for row_id, row in _sorted_rows(styp):
            if not isinstance(row, Mapping):
                continue
            record = dict(row)
            if "GRAV" in record:
                record["GRAV"] = params.add(
                    "analysis.gravity",
                    record["GRAV"],
                    source=f"STYP/{row_id}/GRAV",
                    description="重力加速度（按当前单位系统）",
                    unit="length/time^2",
                )
            styp[row_id] = record  # type: ignore[index]


def build_template(
    native: Mapping[str, Any],
    *,
    name: str,
    family: str = "",
    source: str = "",
) -> dict[str, Any]:
    """原生 `DBG` 文档 → 参数化模板（纯函数）。

    Args:
        native: `DOC.EXPORT` 的整份 JSON（`{"DBG": {表: {id: 行}}}`）或裸 `DBG` 块。
        name: 模板名（通常是样本文件名去掉扩展名）。
        family: 样本族（Static / Eigen / Buckling …）。
        source: 来源路径（写进 `meta`，仅供追溯）。

    Returns:
        模板字典；`model` 内可参数化的标量被替换为 `${参数名}`。

    Raises:
        ValueError: 输入没有 `DBG` 块。
    """
    block = native.get("DBG") if isinstance(native.get("DBG"), Mapping) else native
    if not isinstance(block, Mapping):
        raise ValueError("model_template: 输入缺少 `DBG` 块")

    params = _Parameters()
    model: dict[str, Any] = {}
    for table in sorted(str(item) for item in block):
        rows = block.get(table)
        if table in EXCLUDED_TABLES:
            continue
        if not isinstance(rows, Mapping):
            model[table] = rows
            continue
        if table == "UNIT":
            model[table] = _parameterize_unit(rows, params)
        elif table == "MATL":
            model[table] = _parameterize_material(rows, params)
        elif table == "SECT":
            model[table] = _parameterize_section(rows, params)
        elif table == "NODE":
            model[table] = _parameterize_node(rows, params)
        elif table == "CONS":
            model[table] = _parameterize_supports(rows, params)
        elif table == "STLD":
            model[table] = _parameterize_load_cases(rows, params)
        elif table == "CNLD":
            model[table] = _parameterize_nodal_loads(rows, params)
        elif table == "BMLD":
            model[table] = _parameterize_beam_loads(rows, params)
        elif table == "BODF":
            model[table] = _parameterize_body_forces(rows, params)
        elif table.startswith("LCOM-"):
            model[table] = _parameterize_combinations(table, rows, params)
        else:
            model[table] = {str(key): value for key, value in _sorted_rows(rows)}
    _parameterize_analysis(model, params)

    return {
        "format": TEMPLATE_FORMAT,
        "version": TEMPLATE_VERSION,
        "meta": {
            "name": name,
            "family": family,
            "source": source,
            "tables": sorted(model),
            "row_counts": {
                table: len(rows) if isinstance(rows, Mapping) else 0
                for table, rows in sorted(model.items())
                if isinstance(rows, Mapping)
            },
            "notes": [
                "`parameters` 的 value 是**默认值**（= 样本原值），改它即可改模型。",
                "`model` 里的 `${参数名}` 由 materialize 填回；未知占位符会**报错**。",
                "`PJCF` / `CO_*` 不在模板内（会话元数据 / 颜色表，不是工程数据）。",
            ],
        },
        "parameters": params.items,
        "model": model,
    }


def parameter_values(template: Mapping[str, Any]) -> dict[str, Any]:
    """模板的默认参数值（`name → value`）。"""
    parameters = template.get("parameters")
    if not isinstance(parameters, Mapping):
        return {}
    return {
        str(name): entry.get("value")
        for name, entry in parameters.items()
        if isinstance(entry, Mapping)
    }


def _coerce(name: str, value: Any, original: Any) -> Any:
    """按默认值的类型校验覆盖值（**不做隐式转换**，除 `--set` 的字符串已在调用方解析）。"""
    if isinstance(original, bool):
        if not isinstance(value, bool):
            raise MaterializeError(f"参数 {name!r} 需要 boolean，收到 {value!r}")
        return value
    if isinstance(original, int) and not isinstance(original, bool):
        if isinstance(value, bool) or not isinstance(value, int):
            raise MaterializeError(f"参数 {name!r} 需要 integer，收到 {value!r}")
        return value
    if isinstance(original, float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MaterializeError(f"参数 {name!r} 需要 number，收到 {value!r}")
        return float(value)
    if isinstance(original, str):
        if not isinstance(value, str):
            raise MaterializeError(f"参数 {name!r} 需要 string，收到 {value!r}")
        return value
    if isinstance(original, list):
        if not isinstance(value, list):
            raise MaterializeError(f"参数 {name!r} 需要 array，收到 {value!r}")
        return value
    return value


def _fill(value: Any, values: Mapping[str, Any]) -> Any:
    """把 `${参数名}` 替换为参数值（递归；整串占位符按原类型替换）。"""
    if isinstance(value, str):
        if value.startswith(_PLACEHOLDER_PREFIX) and value.endswith(_PLACEHOLDER_SUFFIX):
            name = value[len(_PLACEHOLDER_PREFIX) : -len(_PLACEHOLDER_SUFFIX)]
            if name not in values:
                raise MaterializeError(f"未知参数 {name!r}（模板里出现了 {value!r}）")
            return values[name]
        return value
    if isinstance(value, Mapping):
        return {str(key): _fill(item, values) for key, item in value.items()}
    if isinstance(value, list):
        return [_fill(item, values) for item in value]
    return value


def materialize(
    template: Mapping[str, Any],
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """模板 + 参数覆盖 → 可直接交给 `DOC.IMPORT` 的 `{"DBG": {...}}`。

    Args:
        template: `build_template` 的产物。
        overrides: 要覆盖的参数（`name → value`）；缺省使用模板默认值。

    Returns:
        `{"DBG": 原生块}`。

    Raises:
        MaterializeError: 格式 / 版本不认识、未知参数、类型不匹配、未知占位符。
    """
    if template.get("format") != TEMPLATE_FORMAT:
        raise MaterializeError(
            f"未知模板格式 {template.get('format')!r}（期望 {TEMPLATE_FORMAT!r}）"
        )
    if template.get("version") != TEMPLATE_VERSION:
        raise MaterializeError(
            f"不支持的模板版本 {template.get('version')!r}（本实现 = {TEMPLATE_VERSION}）"
        )
    model = template.get("model")
    if not isinstance(model, Mapping):
        raise MaterializeError("模板缺少 `model` 块")

    defaults = parameter_values(template)
    values = dict(defaults)
    for name, value in (overrides or {}).items():
        key = str(name)
        if key not in defaults:
            raise MaterializeError(f"未知参数 {key!r}（用 parameter_values() 查看可用参数）")
        values[key] = _coerce(key, value, defaults[key])

    return {"DBG": _fill(model, values)}


def dumps_template(template: Mapping[str, Any]) -> str:
    """**稳定**序列化模板（表名 / 参数名升序；缩进 2；结尾换行）。"""
    payload = {
        "format": template.get("format"),
        "version": template.get("version"),
        "meta": template.get("meta") or {},
        "parameters": {
            name: template["parameters"][name] for name in sorted(template.get("parameters") or {})
        },
        "model": {table: template["model"][table] for table in sorted(template.get("model") or {})},
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
