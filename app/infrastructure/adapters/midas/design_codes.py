"""Infrastructure · Adapters · MIDAS · Design Code Field Sets（`docs/07` §16.1 **R168** 续）。

为什么需要它
------------
`DESIGN.CONCRETE` 的配置端点（`DCO` 等）**可接受字段集随生效规范变化** —— 这是 P176 实测的：

| 生效规范（`DRC.DGNCODE`） | `DCO` 可接受 |
| --- | --- |
| `KDS 41 20 : 2022` | **12 / 13**（`CONC_STRS_STRN` 被原生拒） |
| `GB/T50010-10` | **0**（`DESIGN_CD` 也被拒；空体 `200`） |

而接口层原先把 13 个字段**写死**在 `DesignRcOptionTransformer.fields`
⇒ **换个规范必失败**（`400 Wrong Field`）—— 这正是本模块要消除的硬编码。

⚠️ **为什么字段集只能来自实测**
--------------------------------
① **自省不反映它**：`GET /info/design/RC/KDS-41-20-2022/DCO` 在两种规范下返回**同一份**
   13 字段 ⇒ 它是**端点声明的形状**，**不是**当前规范接受的集合。
② **规范码不能进路径**：`/design/RC/GB-T50010-10/DCO` → `404`
   ⇒ 路径段 `KDS-41-20-2022` 是**固定路由名**，切换规范只能靠 `DGNCODE` 字段。
⇒ 本模块读的 `registry/live/design_code_field_sets.json` 是**实测落盘**的数据，
   **不**从自省推导、**不**臆造（缺记录 ⇒ 调用方显式失败，见 `field_set_for` 的语义）。

分层：本模块只依赖标准库与 `errors.py`（与 `write_templates.py` 同口径）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from app.infrastructure.adapters.midas.errors import MidasConnectionError

__all__ = [
    "DESIGN_CODE_FIELD_SETS_RELATIVE_PATH",
    "DesignCodeFieldSet",
    "DesignCodeFieldSets",
    "load_design_code_field_sets",
]

DESIGN_CODE_FIELD_SETS_RELATIVE_PATH: Final[str] = "live/design_code_field_sets.json"
"""相对 `registry/` 的数据文件路径（与 `write_templates.json` 同目录口径）。"""

_KNOWN_SOURCES: Final[frozenset[str]] = frozenset({"measured", "manual"})
"""允许的来源种类（`measured` = 真机实测；`manual` = 手册声明）。⚠️ **不**允许 `introspect`。"""


@dataclass(frozen=True, slots=True)
class DesignCodeFieldSet:
    """一个 `(material, code)` 下、**某个配置端点**的可接受字段集。

    Attributes:
        material: 材料族（`RC` / `STEEL` / `SRC`）。
        code: 生效规范码（与 `DRC.DGNCODE` 的取值逐字一致，如 `GB/T50010-10`）。
        endpoint: 配置端点的**末段**（`DCO` / `DCTL` / `MEMB`）。
        fields: 可接受的原生字段名（**空元组 = 该规范下不配此端点**）。
        source: 来源种类（`_KNOWN_SOURCES` 之一）。
        evidence: 证据文件（相对仓库根；供复算）。
        note: 逐条说明（**不**参与判定，只作留痕）。
    """

    material: str
    code: str
    endpoint: str
    fields: tuple[str, ...]
    source: str = ""
    evidence: str = ""
    note: tuple[str, ...] = ()

    def accepts(self, native_field: str) -> bool:
        """该规范下是否接受此原生字段。"""
        return str(native_field) in self.fields

    def __repr__(self) -> str:
        """诊断表示（字段集是数据、非敏感）。"""
        return (
            f"DesignCodeFieldSet(material={self.material!r}, code={self.code!r}, "
            f"endpoint={self.endpoint!r}, fields={len(self.fields)})"
        )


@dataclass(frozen=True, slots=True)
class DesignCodeFieldSets:
    """一次装载的字段集集合（缺文件 → **空集合**，**不**静默造假）。"""

    path: Path | None = None
    sets: Mapping[tuple[str, str, str], DesignCodeFieldSet] = field(default_factory=dict)

    def get(self, material: str, code: str, endpoint: str) -> DesignCodeFieldSet | None:
        """按 `(material, code, endpoint)` 取（无记录 → `None`）。

        ⚠️ `None` 的语义是「**未实测**」——调用方**不**得据此臆造字段，
        应显式失败或跳过（见 `adapter.py` 的 `design_option_not_characterized_for_code`）。
        """
        key = (str(material), str(code), str(endpoint))
        return self.sets.get(key)

    def codes(self, material: str) -> tuple[str, ...]:
        """某材料下**已实测**的规范码（升序，确定性）。"""
        return tuple(sorted({code for mat, code, _ in self.sets if mat == str(material)}))

    def __len__(self) -> int:
        """记录条数。"""
        return len(self.sets)

    def as_dict(self) -> dict[str, Any]:
        """诊断映射（**不含**凭据）。"""
        return {
            "path": "" if self.path is None else str(self.path),
            "count": len(self.sets),
            "keys": [list(key) for key in sorted(self.sets)],
        }


def load_design_code_field_sets(registry_root: str | Path) -> DesignCodeFieldSets:
    """装载数据侧字段集（`registry/live/design_code_field_sets.json`）。

    Args:
        registry_root: `registry/` 根目录。

    Returns:
        `DesignCodeFieldSets`；文件不存在 → **空集合**（调用方按「未实测」处理，
        **不**因缺文件而伪造任何字段集）。

    Raises:
        MidasConnectionError: `STRUCTAI-2000` —— 文件存在但不可读 / 非法 JSON /
            结构不符（数据缺陷**不**静默忽略）。
    """
    root = Path(registry_root)
    path = root / DESIGN_CODE_FIELD_SETS_RELATIVE_PATH
    if not path.is_file():
        return DesignCodeFieldSets(path=None)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MidasConnectionError(
            "registry_design_code_field_sets_unreadable",
            path=DESIGN_CODE_FIELD_SETS_RELATIVE_PATH,
            error=type(error).__name__,
        ) from error
    return parse_design_code_field_sets(document, path=path)


def parse_design_code_field_sets(
    document: object, *, path: Path | None = None
) -> DesignCodeFieldSets:
    """解析字段集文件（纯函数；结构不符 → 明确错误）。

    Raises:
        MidasConnectionError: `STRUCTAI-2000`，结构不符（逐条给原因）。
    """
    if not isinstance(document, Mapping):
        raise MidasConnectionError(
            "registry_design_code_field_sets_malformed",
            path=DESIGN_CODE_FIELD_SETS_RELATIVE_PATH,
            defect="root_not_object",
        )
    materials = document.get("materials")
    if not isinstance(materials, Mapping):
        raise MidasConnectionError(
            "registry_design_code_field_sets_malformed",
            path=DESIGN_CODE_FIELD_SETS_RELATIVE_PATH,
            defect="materials_missing",
        )

    parsed: dict[tuple[str, str, str], DesignCodeFieldSet] = {}
    for material, codes in materials.items():
        if not isinstance(codes, Mapping):
            raise MidasConnectionError(
                "registry_design_code_field_sets_malformed",
                path=DESIGN_CODE_FIELD_SETS_RELATIVE_PATH,
                defect=f"material_not_object:{material}",
            )
        for code, endpoints in codes.items():
            if not isinstance(endpoints, Mapping):
                raise MidasConnectionError(
                    "registry_design_code_field_sets_malformed",
                    path=DESIGN_CODE_FIELD_SETS_RELATIVE_PATH,
                    defect=f"code_not_object:{material}/{code}",
                )
            for endpoint, entry in endpoints.items():
                if not isinstance(entry, Mapping):
                    raise MidasConnectionError(
                        "registry_design_code_field_sets_malformed",
                        path=DESIGN_CODE_FIELD_SETS_RELATIVE_PATH,
                        defect=f"entry_not_object:{material}/{code}/{endpoint}",
                    )
                raw_fields = entry.get("fields")
                if not isinstance(raw_fields, list) or not all(
                    isinstance(item, str) for item in raw_fields
                ):
                    raise MidasConnectionError(
                        "registry_design_code_field_sets_malformed",
                        path=DESIGN_CODE_FIELD_SETS_RELATIVE_PATH,
                        defect=f"fields_not_string_list:{material}/{code}/{endpoint}",
                    )
                source = str(entry.get("source") or "")
                if source not in _KNOWN_SOURCES:
                    raise MidasConnectionError(
                        "registry_design_code_field_sets_malformed",
                        path=DESIGN_CODE_FIELD_SETS_RELATIVE_PATH,
                        defect=f"unknown_source:{source!r}",
                    )
                note = entry.get("note") or []
                parsed[(str(material), str(code), str(endpoint))] = DesignCodeFieldSet(
                    material=str(material),
                    code=str(code),
                    endpoint=str(endpoint),
                    fields=tuple(str(item) for item in raw_fields),
                    source=source,
                    evidence=str(entry.get("evidence") or ""),
                    note=tuple(str(item) for item in note) if isinstance(note, list) else (),
                )
    return DesignCodeFieldSets(path=path, sets=parsed)
