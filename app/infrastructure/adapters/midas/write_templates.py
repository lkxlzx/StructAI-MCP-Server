"""Infrastructure · Adapters · MIDAS · Write templates（P139，`docs/07` §16 R4 / R14 的分子）。

权威来源
--------
- `docs/04` §69–§72 —— Contract Test 分层（L1–L3 属 CI，L4 / L5 属**专用环境**）。
- `docs/07` §16 **R4 / R14** —— 写路径实测覆盖（分母恒为 `609`，分子只统计**真实** L5 `PASSED`）。
- `docs/reports/P138_数据侧缺陷收口与L5空项目闸门_v1.0.md` §4.3 / §8 —— P138c 的真实批量实测：
  GEN NX 的 **10** 个可探候选里 `DB.NODE` `PASSED`，其余 **9** 个被实例拒绝
  （`400 software_api_error`）。根因：请求体由 `write_probe.derive_body()` 从数据侧 Schema
  **机械派生**（`default` / `const` / `enum[0]` / 类型零值）→ 产出零值 / 空引用。

本模块补的那一环（**模板来源可追溯**，不把模板硬编码进 Core）
-----------------------------------------------------------
P139 的裁决：**请求体模板是数据**，放在数据侧 `registry/live/write_templates.json`
（由 `registry/tools/check_write_templates.py` 逐条**复算**校验），Core 只做三件事：

1. **读取**（本模块 `load_write_templates`）—— 只解析、只校验结构，**不**解释工程语义；
2. **优先取模板**（`write_probe.MidasLiveWriteProbe`）—— 有模板用模板，无模板仍走
   `derive_body()`；两者都取不到 → 如实记 `NO_PAYLOAD_TEMPLATE`（**不**猜、**不**发请求）；
3. **前置链**（`WritePrerequisite`）—— 模板可以声明「先建必要的引用对象」，
   由探针按顺序创建、读回、**逆序删除**，且**只**碰自建的编号。

⚠️ **不**放宽任何判定：模板只影响「请求体长什么样」，`PASSED` 仍要求
「创建 → 读回 → 按路径 key 删除」三步全成立（`write_probe` 裁决 6）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与同包 `errors.py`；**不**引用 SQLAlchemy / FastAPI / MCP SDK，
**不**依赖 `app.interfaces` / `app.application`，**不**接触任何凭据值。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from app.infrastructure.adapters.midas.errors import MidasConnectionError

__all__ = [
    "WRITE_TEMPLATES_RELATIVE_PATH",
    "WritePayloadTemplate",
    "WritePrerequisite",
    "WriteTemplateSet",
    "load_write_templates",
    "parse_write_templates",
]

WRITE_TEMPLATES_RELATIVE_PATH: Final[str] = "live/write_templates.json"
"""数据侧模板文件（相对 `registry/`）—— **唯一**来源，见模块文档。"""

_SOURCE_KINDS: Final[frozenset[str]] = frozenset(
    {
        "manual_example",
        "manual_example_adjusted",
        "explicit_injection",
    }
)
"""允许的模板来源种类（**如实**标注；未知种类 → 数据缺陷，直接拒绝）。"""


@dataclass(frozen=True, slots=True)
class WritePrerequisite:
    """一个**前置对象**（三步链之前必须先建好的引用对象；见模块文档第 3 条）。

    Attributes:
        key: 前置端点的 Registry key（如 `DB.STLD`）。
        item_id: 前置对象的编号（**自建**；引用它的请求体按该编号取值）。
        body: 前置对象的请求体（数据侧模板，未包装）。
        source: 来源种类（`_SOURCE_KINDS` 之一）。
        origin: 来源定位串（如 `db/STLD#Static Load Cases`），供报告与复算使用。
    """

    key: str
    item_id: str
    body: Any
    source: str = ""
    origin: str = ""

    def __repr__(self) -> str:
        """诊断表示：只含定位字段（**不**回显请求体）。"""
        return (
            f"WritePrerequisite(key={self.key!r}, item_id={self.item_id!r}, source={self.source!r})"
        )

    def label(self) -> str:
        """`<key>#<item_id>` 形态的短标签（写进 L5 证据的**非敏感**诊断串）。"""
        return f"{self.key}#{self.item_id}"


@dataclass(frozen=True, slots=True)
class WritePayloadTemplate:
    """一个写路径端点的请求体模板（数据侧声明；见模块文档）。

    Attributes:
        key: 端点 key（与 `registry/` 一致）。
        body: 请求体（未包装；包装键仍由数据侧 Transformer 决定）。
        wrapper: 声明的包装键（仅作证据；实际包装仍取 Transformer 的 `wrapper_key()`）。
        source: 来源种类（`_SOURCE_KINDS` 之一）。
        origin: 来源定位串（如 `db/BMLD#Beam Loads`）。
        prerequisites: 前置对象（按声明顺序创建、**逆序**删除）。
    """

    key: str
    body: Any
    wrapper: str = ""
    source: str = ""
    origin: str = ""
    prerequisites: tuple[WritePrerequisite, ...] = ()

    def __repr__(self) -> str:
        """诊断表示：只含定位字段（**不**回显请求体）。"""
        return (
            f"WritePayloadTemplate(key={self.key!r}, source={self.source!r}, "
            f"origin={self.origin!r}, prerequisites={len(self.prerequisites)})"
        )

    def prerequisite_labels(self) -> tuple[str, ...]:
        """前置对象的短标签（按声明顺序）。"""
        return tuple(item.label() for item in self.prerequisites)


@dataclass(frozen=True, slots=True)
class WriteTemplateSet:
    """一次装载的模板集合（缺文件 → 空集合，**不**静默造假）。"""

    path: Path | None = None
    templates: Mapping[str, WritePayloadTemplate] = field(default_factory=dict)

    def get(self, key: str) -> WritePayloadTemplate | None:
        """按端点 key 取模板（无模板 → `None`，调用方回落 `derive_body`）。"""
        return self.templates.get(str(key))

    def keys(self) -> tuple[str, ...]:
        """已声明模板的端点 key（升序，确定性）。"""
        return tuple(sorted(self.templates))

    def __len__(self) -> int:
        """模板条数。"""
        return len(self.templates)

    def as_dict(self) -> dict[str, Any]:
        """诊断映射（**不含**凭据；请求体是**数据侧模板**，非敏感）。"""
        return {
            "path": "" if self.path is None else str(self.path),
            "count": len(self.templates),
            "keys": list(self.keys()),
        }


def load_write_templates(registry_root: str | Path) -> WriteTemplateSet:
    """装载数据侧写路径模板（`registry/live/write_templates.json`）。

    Args:
        registry_root: `registry/` 根目录。

    Returns:
        `WriteTemplateSet`；文件不存在 → **空集合**（此时探针仍走 `derive_body()`，
        **不**因缺文件而伪造任何模板）。

    Raises:
        MidasConnectionError: `STRUCTAI-2000` —— 文件存在但不可读 / 不是合法 JSON /
            结构不符合约定（数据缺陷**不**静默忽略）。
    """
    root = Path(registry_root)
    path = root / WRITE_TEMPLATES_RELATIVE_PATH
    if not path.is_file():
        return WriteTemplateSet(path=None)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MidasConnectionError(
            "registry_write_templates_unreadable",
            path=WRITE_TEMPLATES_RELATIVE_PATH,
            error=type(error).__name__,
        ) from error
    return parse_write_templates(document, path=path)


def parse_write_templates(document: object, *, path: Path | None = None) -> WriteTemplateSet:
    """解析模板文件（纯函数；结构不符 → 明确错误，见 `load_write_templates`）。

    Raises:
        MidasConnectionError: `STRUCTAI-2000` —— 结构缺陷（逐条给出**非敏感**定位）。
    """
    if not isinstance(document, Mapping):
        raise _defect("root_not_object", path=path)
    raw = document.get("templates")
    if not isinstance(raw, Mapping):
        raise _defect("templates_missing", path=path)
    parsed: dict[str, WritePayloadTemplate] = {}
    for key, entry in raw.items():
        name = str(key)
        if not name:
            raise _defect("template_key_empty", path=path)
        parsed[name] = _template(name, entry, path=path)
    return WriteTemplateSet(path=path, templates=parsed)


def _template(key: str, entry: object, *, path: Path | None) -> WritePayloadTemplate:
    """一个模板条目 → 数据类（结构不符即拒绝）。"""
    if not isinstance(entry, Mapping):
        raise _defect("template_not_object", path=path, key=key)
    if "body" not in entry:
        raise _defect("template_body_missing", path=path, key=key)
    source = _source_of(entry.get("source"), path=path, key=key)
    prerequisites = tuple(
        _prerequisite(key, item, path=path) for item in _sequence(entry.get("prerequisites"))
    )
    return WritePayloadTemplate(
        key=key,
        body=entry["body"],
        wrapper=str(entry.get("wrapper") or ""),
        source=source[0],
        origin=source[1],
        prerequisites=prerequisites,
    )


def _prerequisite(owner: str, entry: object, *, path: Path | None) -> WritePrerequisite:
    """一个前置条目 → 数据类（结构不符即拒绝）。"""
    if not isinstance(entry, Mapping):
        raise _defect("prerequisite_not_object", path=path, key=owner)
    prereq_key = str(entry.get("key") or "")
    item_id = str(entry.get("item_id") or "")
    if not prereq_key or not item_id:
        raise _defect("prerequisite_key_or_id_missing", path=path, key=owner)
    if "body" not in entry:
        raise _defect("prerequisite_body_missing", path=path, key=owner)
    source = _source_of(entry.get("source"), path=path, key=owner)
    return WritePrerequisite(
        key=prereq_key,
        item_id=item_id,
        body=entry["body"],
        source=source[0],
        origin=source[1],
    )


def _source_of(value: object, *, path: Path | None, key: str) -> tuple[str, str]:
    """`source` 块 → `(种类, 定位串)`；未知种类 → 数据缺陷（**不**接受「无名模板」）。"""
    if not isinstance(value, Mapping):
        raise _defect("template_source_missing", path=path, key=key)
    kind = str(value.get("kind") or "")
    if not kind:
        raise _defect("template_source_missing", path=path, key=key)
    if kind not in _SOURCE_KINDS:
        raise _defect(f"template_source_kind_unknown:{kind}", path=path, key=key)
    uri = str(value.get("uri") or "")
    example = str(value.get("example") or "")
    origin = f"{uri}#{example}" if uri and example else (uri or example)
    return kind, origin


def _sequence(value: object) -> tuple[object, ...]:
    """序列归一（`None` → 空；非序列 → 空，由结构校验负责报错）。"""
    if isinstance(value, Sequence) and not isinstance(value, str):
        return tuple(value)
    return ()


def _defect(reason: str, *, path: Path | None, key: str = "") -> MidasConnectionError:
    """构造数据缺陷错误（**不**回显任何取值）。"""
    return MidasConnectionError(
        "registry_write_templates_defect",
        path=WRITE_TEMPLATES_RELATIVE_PATH if path is None else str(path.name),
        endpoint=key,
        defect=reason,
    )
