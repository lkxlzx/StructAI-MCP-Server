"""Application · Services · ResultService（`docs/02` §49 / §33 / §89 / §90 / §31 / §35）。

权威来源
--------
- `docs/02` §33（`source9`）—— 结果归一化：Adapter 的 native 结果先变成**规范形状**，
  再经统一的信封返回；归一化是**一处**实现。
- `docs/02` §89（`blue`）—— 归一化的分工：**Adapter** 负责 native → canonical 的
  **字段映射**（P19–P20 落地）；结果层只负责**信封**。
- `docs/02` §90 / §31（`blue`）—— 分页信封的形状：
  `{"data": [...], "pagination": {"has_more": bool, "next_cursor": str}}`；
  `limit` 必填语义（禁止无限 payload）。
- `docs/02` §49（`blue`）—— `Result` 的 artifact linking：结果可以关联若干产物标识。
- `docs/02` §35（`blue`）—— 分页参数（`limit` / `cursor`）与不透明游标。
- `docs/07` §12 P30 / §14.4 —— 禁止无限 payload；`docs/07` §11 —— 非法输入落
  `STRUCTAI-1200`（工程校验族，20 码内既有）。
落地裁决（只补实现手段，不改语义）
----------------------------------
1. **`has_more is False` 时 `next_cursor` 必须是 `None`**：`docs/02` §31 的示例把
   `next_cursor` 画成字符串，但「还有更多」为假时**没有**下一个游标 —— 唯一诚实的值是
   `None`（回一个自造的游标会诱导客户端多请求一次空页）。`has_more` 为真时 `next_cursor`
   是**不透明**游标（`docs/02` §35），调用方不得解析它。
2. **游标是不透明 base64 的偏移量**：`encode_cursor(offset)` / `decode_cursor(cursor)`
   只承载**偏移**（`docs/02` §35 的 `cursor` 语义），非法 / 外来游标 →
   `STRUCTAI-1200`（`reason = "invalid_cursor"`）—— **绝不**静默回退到 0
   （`docs/07` §14.4：不接受无法验证的输入）。
3. **`normalize()` 只强制信封，不做字段映射**（`docs/02` §89）：native → canonical 的
   **字段**映射是 Adapter 的职责（P19–P20），本方法只保证「有 `data`」这一层形状。
   它接受三种输入：已规范的映射（含 `data`）、裸序列（多行）、裸映射（**单行**载荷）。
4. **`pagination` 只在**同时**具备 `has_more` 与 `next_cursor` 时保留**（`docs/02` §90）：
   形状不完整的分页对象一律**丢弃**（视为 `None`），**不**补齐、**不**猜测 ——
   伪造一个分页信封比没有分页更危险。
5. **`paginated()` 的 `artifacts` 键是 `docs/02` §49 的载体**：`docs/02` §90 的规范信封
   只有 `data` / `pagination`，而 §49 要求结果能关联产物。故本方法在规范信封之上**追加**
   一个 `artifacts` 键（不改变 `data` / `pagination` 的形状），这是 §49 的唯一落点。
6. **服务级默认页大小**：模块函数 `paginate()` 用 `DEFAULT_RESULT_LIMIT`；
   `ResultService.paginated()` 未传 `limit` 时用**服务自身**的 `default_limit`
   （构造参数），使「一个服务一个默认值」，且仍然**有界**（`docs/07` §14.4）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，
**不**依赖 `app.infrastructure`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Final

from app.domain.errors import EngineeringValidationError
from app.domain.value_objects import DEFAULT_PAGE_LIMIT

__all__ = [
    "ARTIFACTS_KEY",
    "DATA_KEY",
    "DEFAULT_RESULT_LIMIT",
    "HAS_MORE_KEY",
    "NEXT_CURSOR_KEY",
    "PAGINATION_KEY",
    "RESULT_STAGE",
    "CanonicalResult",
    "ResultService",
    "decode_cursor",
    "encode_cursor",
    "envelope",
    "paginate",
]

RESULT_STAGE: Final[str] = "result"
"""本模块所有异常 `details["stage"]` 的固定取值（`docs/07` §11 的诊断口径）。"""

DEFAULT_RESULT_LIMIT: Final[int] = DEFAULT_PAGE_LIMIT
"""默认页大小（= `app.domain.value_objects.DEFAULT_PAGE_LIMIT`；`docs/02` §31 / §35）。"""

PAGINATION_KEY: Final[str] = "pagination"
"""分页信封的键（`docs/02` §90）。"""

DATA_KEY: Final[str] = "data"
"""数据键（`docs/02` §90）。"""

HAS_MORE_KEY: Final[str] = "has_more"
"""「还有更多」键（`docs/02` §90）。"""

NEXT_CURSOR_KEY: Final[str] = "next_cursor"
"""「下一个游标」键（`docs/02` §90；见模块裁决 1）。"""

ARTIFACTS_KEY: Final[str] = "artifacts"
"""产物关联键（`docs/02` §49；见模块裁决 5）。"""


def encode_cursor(offset: int) -> str:
    """把偏移量编成不透明游标（`docs/02` §35；见模块裁决 2）。

    Args:
        offset: 下一页的起始偏移（>= 0）。

    Returns:
        URL-safe base64 文本（不透明；调用方不得解析）。
    """
    return base64.urlsafe_b64encode(str(int(offset)).encode("ascii")).decode("ascii")


def decode_cursor(cursor: str | None) -> int:
    """把游标解回偏移量（`docs/02` §35；见模块裁决 2）。

    Args:
        cursor: 不透明游标；`None` 表示从头开始。

    Returns:
        偏移量（>= 0）；`cursor is None` 时为 `0`。

    Raises:
        EngineeringValidationError: `STRUCTAI-1200`，游标非法 / 外来 / 指向负偏移
            （`details = {stage: "result", reason: "invalid_cursor"}`）—— **绝不**
            静默回退到 `0`。
    """
    if cursor is None:
        return 0
    try:
        raw = base64.b64decode(str(cursor), altchars=b"-_", validate=True)
        offset = int(raw.decode("ascii"))
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise _invalid_cursor() from error
    if offset < 0:
        raise _invalid_cursor()
    return offset


def paginate(
    items: Sequence[Any],
    *,
    limit: int | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    """按 `docs/02` §90 / §31 的信封分页（见模块裁决 1 / 2）。

    Args:
        items: 完整的结果行序列（调用方已归一化）。
        limit: 页大小；`None` 用 `DEFAULT_RESULT_LIMIT`。
        cursor: 不透明游标；`None` 表示第一页。

    Returns:
        `{"data": [...], "pagination": {"has_more": bool, "next_cursor": str | None}}`
        —— 形状与 `docs/02` §90 逐字一致；**永远**有界（`docs/07` §14.4）。

    Raises:
        EngineeringValidationError: `STRUCTAI-1200`，`limit <= 0`
            （`reason = "invalid_limit"`）或游标非法（`reason = "invalid_cursor"`）。
    """
    effective = DEFAULT_RESULT_LIMIT if limit is None else int(limit)
    if effective <= 0:
        raise EngineeringValidationError(
            "page limit must be positive",
            details={"stage": RESULT_STAGE, "reason": "invalid_limit"},
        )

    offset = decode_cursor(cursor)
    rows = list(items)
    window = rows[offset : offset + effective]
    has_more = offset + effective < len(rows)
    return {
        DATA_KEY: window,
        PAGINATION_KEY: {
            HAS_MORE_KEY: has_more,
            NEXT_CURSOR_KEY: encode_cursor(offset + effective) if has_more else None,
        },
    }


def envelope(data: Any, *, pagination: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """构造 `docs/02` §90 的信封（见模块裁决 1 / 5）。

    Args:
        data: 数据（已归一化）。
        pagination: 分页对象；`None` 时信封里**没有** `pagination` 键（不伪造）。

    Returns:
        `{"data": data}`，有分页时再加 `"pagination"`。
    """
    result: dict[str, Any] = {DATA_KEY: data}
    if pagination is not None:
        result[PAGINATION_KEY] = pagination
    return result


@dataclass(frozen=True, slots=True)
class CanonicalResult:
    """一次归一化后的规范结果（`docs/02` §33 / §49 / §89）。

    Attributes:
        operation: 产生该结果的 Operation 名（诊断 / 断言用）。
        data: 规范载荷（通常是一行列表；裸映射载荷则是映射本身）。
        pagination: 规范分页对象（仅当来源给出完整形状时；见模块裁决 4）。
        artifacts: 关联的产物标识（`docs/02` §49；`link_artifacts` 维护）。
    """

    operation: str
    data: Any
    pagination: Mapping[str, Any] | None = None
    artifacts: tuple[str, ...] = ()


class ResultService:
    """结果归一化 / 分页 / 产物关联（`docs/02` §33 / §49 / §89 / §90 / §31）。

    ⚠️ 本服务**只**处理信封：native → canonical 的**字段**映射是 Adapter 的职责
    （`docs/02` §89，P19–P20），一个关注点一处实现（见模块裁决 3）。
    它**不**写库、**不** `commit` / `rollback`（`docs/07` §14.4）。
    """

    def __init__(self, *, default_limit: int = DEFAULT_RESULT_LIMIT) -> None:
        """绑定服务级默认页大小。

        Args:
            default_limit: `paginated()` 未传 `limit` 时使用的页大小（见模块裁决 6）。

        Raises:
            EngineeringValidationError: `STRUCTAI-1200`，`default_limit <= 0`
                （装配错误，不静默接受）。
        """
        if int(default_limit) <= 0:
            raise EngineeringValidationError(
                "default result limit must be positive",
                details={"stage": RESULT_STAGE, "reason": "invalid_limit"},
            )
        self._default_limit = int(default_limit)

    @property
    def default_limit(self) -> int:
        """服务级默认页大小（`docs/02` §31）。"""
        return self._default_limit

    # ===== 归一化（`docs/02` §33 / §89）=====

    def normalize(
        self,
        operation: str,
        raw: Mapping[str, Any] | Sequence[Any],
    ) -> CanonicalResult:
        """把来源结果归一到规范信封（`docs/02` §33 / §89；见模块裁决 3 / 4）。

        Args:
            operation: 产生该结果的 Operation 名。
            raw: 三种形态之一 —— 含 `data` 的规范映射、裸序列（多行）、
                裸映射（**单行**载荷）。

        Returns:
            `CanonicalResult`：`pagination` 只在来源给出**完整**形状时保留。
        """
        data: Any
        pagination: Mapping[str, Any] | None
        if isinstance(raw, Mapping):
            if DATA_KEY in raw:
                data = raw[DATA_KEY]
                pagination = _complete_pagination(raw.get(PAGINATION_KEY))
            else:
                data = raw
                pagination = None
        elif isinstance(raw, (str, bytes, bytearray)):
            data = raw
            pagination = None
        elif isinstance(raw, Sequence):
            data = list(raw)
            pagination = None
        else:  # pragma: no cover - 契约只声明 Mapping | Sequence
            data = raw
            pagination = None
        return CanonicalResult(operation=str(operation), data=data, pagination=pagination)

    def link_artifacts(
        self,
        result: CanonicalResult,
        artifact_ids: Iterable[str],
    ) -> CanonicalResult:
        """关联产物标识（`docs/02` §49；去重且保持顺序）。

        Args:
            result: 待关联的规范结果。
            artifact_ids: 追加的产物标识。

        Returns:
            **新**的 `CanonicalResult`（原对象不变），`artifacts` 为
            已有 + 追加、按首次出现顺序去重后的元组。
        """
        merged: list[str] = list(result.artifacts)
        seen = set(merged)
        for artifact_id in artifact_ids:
            text = str(artifact_id)
            if text not in seen:
                seen.add(text)
                merged.append(text)
        return replace(result, artifacts=tuple(merged))

    def paginated(
        self,
        result: CanonicalResult,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """对规范结果分页并回填产物关联（`docs/02` §90 / §49；见模块裁决 5 / 6）。

        Args:
            result: 规范结果；`data` 必须是序列，映射按**单行**列表处理。
            limit: 页大小；`None` 用服务的 `default_limit`。
            cursor: 不透明游标。

        Returns:
            `{"data": [...], "pagination": {...}, "artifacts": [...]}` —— 前两个键与
            `docs/02` §90 逐字一致，`artifacts` 是 §49 的载体。

        Raises:
            EngineeringValidationError: `STRUCTAI-1200`，`limit <= 0` 或游标非法。
        """
        data = result.data
        if isinstance(data, (str, bytes, bytearray)) or not isinstance(data, Sequence):
            items: list[Any] = [data]
        else:
            items = list(data)
        effective = self._default_limit if limit is None else limit
        page = paginate(items, limit=effective, cursor=cursor)
        page[ARTIFACTS_KEY] = list(result.artifacts)
        return page


def _complete_pagination(value: object) -> Mapping[str, Any] | None:
    """只在**完整**时保留分页对象（`docs/02` §90；见模块裁决 4）。"""
    if not isinstance(value, Mapping):
        return None
    if HAS_MORE_KEY not in value or NEXT_CURSOR_KEY not in value:
        return None
    return dict(value)


def _invalid_cursor() -> EngineeringValidationError:
    """构造非法游标错误（`STRUCTAI-1200`；见模块裁决 2）。"""
    return EngineeringValidationError(
        "cursor is not a valid pagination cursor",
        details={"stage": RESULT_STAGE, "reason": "invalid_cursor"},
    )
