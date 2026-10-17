"""模板库：读取 `templates/gen_verification/` 的索引与模板（P181 管理面数据源）。

为什么在 Application 层
------------------------
模板是**工程数据**，不是传输格式也不是厂商专属内容：UI / MCP / CLI 都要用同一份
`index.json` 与同一套 `materialize`。放在 Application 层 ⇒ 接口层只做转发
（`docs/07` §14.1 的 Interface 禁止项），且**不**出现任何厂商名。

口径
----
1. **只读**：模板库是交付物（`templates/` 进仓库），本层**不**写回；
2. **路径来自构造参数**（`template_root`），不在模块内硬编码；
3. 索引缺失 ⇒ 返回空库并如实报告 `available=False`（**不**伪造模板）；
4. `materialize` 复用 `model_template.materialize`（唯一实现点，**不**复制逻辑）。
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from app.application.templates.model_template import (
    MaterializeError,
    materialize,
    parameter_values,
)

__all__ = [
    "INDEX_FILENAME",
    "MaterializeError",
    "TemplateLibrary",
    "TemplateSummary",
    "load_library",
]

INDEX_FILENAME: Final[str] = "index.json"


@dataclass(frozen=True, slots=True)
class TemplateSummary:
    """模板库索引里的一条（**不含** `model`，列表页不需要整份模型）。"""

    name: str
    family: str
    file: str
    parameters: int
    tables: int
    key_parameters: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """列表页用的 JSON 形状。"""
        return {
            "name": self.name,
            "family": self.family,
            "file": self.file,
            "parameters": self.parameters,
            "tables": self.tables,
            "key_parameters": list(self.key_parameters),
        }


@dataclass(frozen=True, slots=True)
class TemplateLibrary:
    """`templates/<family>/**` 的只读视图。"""

    root: pathlib.Path
    available: bool
    families: Mapping[str, tuple[str, ...]]
    templates: tuple[TemplateSummary, ...]

    def summary(self) -> dict[str, Any]:
        """索引摘要（列表页 / 首页卡片）。"""
        return {
            "available": self.available,
            "root": str(self.root),
            "count": len(self.templates),
            "families": {name: list(names) for name, names in self.families.items()},
        }

    def find(self, name: str) -> TemplateSummary | None:
        """按模板名查找（**不做**模糊匹配：名字来自索引）。"""
        target = str(name)
        return next((item for item in self.templates if item.name == target), None)

    def parameters(self, name: str) -> dict[str, Any]:
        """某模板的全部可填参数（`name → {value, kind, description, source, unit?}`）。

        Raises:
            KeyError: 模板不在索引里。
        """
        template = self._load(name)
        parameters = template.get("parameters")
        return dict(parameters) if isinstance(parameters, Mapping) else {}

    def defaults(self, name: str) -> dict[str, Any]:
        """某模板的默认参数值（`name → value`）。"""
        return parameter_values(self._load(name))

    def render(self, name: str, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """按覆盖值生成 `{"DBG": {...}}`（可直接交给 `DOC.IMPORT`）。

        Raises:
            KeyError: 模板不在索引里。
            MaterializeError: 未知参数 / 类型不匹配 / 未知占位符（**不猜**）。
        """
        return materialize(self._load(name), overrides)

    def _load(self, name: str) -> dict[str, Any]:
        """读取模板文件（索引里登记的**那个**文件，不接受任意路径）。"""
        entry = self.find(name)
        if entry is None:
            raise KeyError(f"unknown template: {name}")
        path = self.root / entry.file
        if not path.is_file():
            raise KeyError(f"template file is missing: {entry.file}")
        return json.loads(path.read_text(encoding="utf-8"))


def load_library(root: str | pathlib.Path) -> TemplateLibrary:
    """装载模板库（**只读**；索引缺失 ⇒ `available=False`，不抛）。"""
    base = pathlib.Path(root)
    index_path = base / INDEX_FILENAME
    if not index_path.is_file():
        return TemplateLibrary(root=base, available=False, families={}, templates=())

    payload = json.loads(index_path.read_text(encoding="utf-8"))
    families = {
        str(name): tuple(str(item) for item in names)
        for name, names in (payload.get("families") or {}).items()
    }
    templates = tuple(
        TemplateSummary(
            name=str(item.get("name")),
            family=str(item.get("family")),
            file=str(item.get("file")),
            parameters=int(item.get("parameters") or 0),
            tables=int(item.get("tables") or 0),
            key_parameters=tuple(str(value) for value in item.get("key_parameters") or ()),
        )
        for item in payload.get("templates") or []
        if isinstance(item, Mapping)
    )
    return TemplateLibrary(root=base, available=True, families=families, templates=templates)
