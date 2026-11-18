"""敏感键清洗与判定（`docs/07` §8.5 / §14.3；`docs/02` §9）。

日志 / 事件载荷 / 审计元数据 / 追踪属性在落盘或序列化前，**必须**经过本模块：
任何键名命中敏感词表的字段一律视为 secret，**不**记录其值。

导出：
- `SENSITIVE_KEY_PARTS`：敏感键词表（`tests/.../test_storage_artifact_p29.py`
  的 `SENSITIVE_KEY_PARTS_SPEC` 逐字一致，本批不得扩/缩）。
- `REDACTION_MARKER`：脱敏占位符 `<redacted>`。
- `looks_sensitive(name)`：键名是否敏感（大小写不敏感，子串匹配）。
- `redact_value(value)`：把一个值脱敏为 `REDACTION_MARKER`。
- `sanitize_mapping(mapping)`：返回去掉敏感键后的**新** dict（递归；不改入参）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

__all__ = [
    "REDACTION_MARKER",
    "SENSITIVE_KEY_PARTS",
    "looks_sensitive",
    "redact_value",
    "sanitize_mapping",
]

SENSITIVE_KEY_PARTS: Final[tuple[str, ...]] = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "api-key",
    "private_key",
    "privatekey",
    "credential",
    "mapi",
    "mcp_key",
    "authorization",
)
"""`docs/07` §8.5 / §14.3 的敏感键词表（逐字抄写；子串、大小写不敏感）。"""

REDACTION_MARKER: Final[str] = "<redacted>"
"""脱敏后的占位文本（`docs/07` §14.3）。"""


def looks_sensitive(name: object) -> bool:
    """键名是否敏感（大小写不敏感，子串匹配 `SENSITIVE_KEY_PARTS`）。

    Args:
        name: 键名（任意对象，内部转 `str` 并小写）。

    Returns:
        `True` 表示该键名的值**不得**记录。
    """
    text = str(name).strip().lower()
    if not text:
        return False
    return any(part in text for part in SENSITIVE_KEY_PARTS)


def redact_value(value: Any) -> str:
    """把一个值脱敏为 `REDACTION_MARKER`（值本身**不**保留）。"""
    return REDACTION_MARKER


def sanitize_mapping(mapping: Mapping[Any, Any] | None) -> dict[Any, Any]:
    """返回去掉敏感键后的新 dict（递归处理嵌套结构；不修改入参）。

    - 顶层与嵌套 dict 中键名敏感者一律**丢键**；
    - list / tuple 内的 dict 元素递归清洗，非映射元素原样保留；
    - 其它值原样返回。

    Args:
        mapping: 待清洗的映射；`None` → 空 dict。

    Returns:
        清洗后的新 dict。
    """
    if not mapping:
        return {}
    cleaned: dict[Any, Any] = {}
    for key, value in mapping.items():
        if looks_sensitive(key):
            continue
        cleaned[key] = _sanitize_value(value)
    return cleaned


def _sanitize_value(value: Any) -> Any:
    """递归清洗单个值（dict / list / tuple → 清洗版；其它原样）。"""
    if isinstance(value, Mapping):
        return sanitize_mapping(value)
    if isinstance(value, (list, tuple)):
        return type(value)(_sanitize_value(item) for item in value)
    return value
