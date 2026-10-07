"""Infrastructure · Adapters · CSI ETABS · Transforms —— Canonical ↔ Native（P129）。

权威来源
--------
- `docs/02` §88 / §89 —— Adapter 负责 `native → canonical` 的**字段映射**；
  客户端不依赖任何软件原始字段。
- `docs/07` §7.4 的硬约束（同口径）—— 禁止 `StructAI Schema == 厂商 Schema`；
  必须走 `Canonical → StructAI Schema 校验 → Transformer → 原生 Schema 校验 → 原生调用`。
- `docs/04` §44（同口径）—— 缺失值一律 `None`，**绝不**虚构 `0`。

落地裁决（只补实现手段，不改任何取值）
------------------------------------
1. **本仓库没有 ETABS 原生参数的权威来源**，因此 native **参数**面如实为空：
   `request_to_native()` 只做 canonical 词表校验，返回 `{}`（「无可追溯的原生参数」）。
   **不**编造任何原生参数名 —— 编造即违反 `docs/07` §16 R76。
2. **canonical 的规范形态由 catalogue 推导**：`{"analysis_type": "STATIC"}`；
   缺省值来自 catalogue 条目（`ANALYSIS.STATIC` 的后缀），**不是**臆造。
   任何其他取值 → `EtabsValidationError("analysis_type_not_in_catalogue")`（`1200`）。
3. **未覆盖的转换明确失败**：canonical 里出现未声明字段 → `EtabsTransformerError`（`1200`）；
   native 里出现未声明字段 → 同样失败（**不**静默丢弃）。
4. **结果面双向**：`result_from_native()` 把 `ComInvocation` 转成 canonical 结果
   （`native_payload` / `native_keys` **原样**保留、**不**解释语义），
   `result_to_native()` 是它的反向。缺失值写 `None`（见 `docs/04` §44）。
5. **`verification_status` 随结果回传**：canonical 结果里如实标注条目状态
   （本批 = `PARTIAL`），使「未验证」在上层可见（`docs/07` §16 R78）。

分层红线：只依赖标准库与同包的 `catalogue.py` / `client.py` / `errors.py`。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Final

from app.infrastructure.adapters.etabs.capabilities import capability_for_operation
from app.infrastructure.adapters.etabs.catalogue import CatalogueEntry, entry_for
from app.infrastructure.adapters.etabs.client import COM_PROTOCOL, ComInvocation
from app.infrastructure.adapters.etabs.errors import (
    EtabsTransformerError,
    EtabsValidationError,
)

__all__ = [
    "ANALYSIS_TRANSFORMER_NAME",
    "RESULT_FIELDS",
    "TRANSFORMER_REGISTRY",
    "AnalysisTransformer",
    "transformer_for",
]

ANALYSIS_TRANSFORMER_NAME: Final[str] = "csi.analysis.v1"
"""Transformer 标识（数据库只存**名字**；本批无落库表，标识仅用于诊断与 Registry）。"""

RESULT_FIELDS: Final[tuple[str, ...]] = (
    "operation",
    "protocol",
    "method",
    "analysis_type",
    "completed",
    "arguments",
    "native_payload",
    "native_keys",
    "verification_status",
)
"""canonical 结果的字段集（**恰好**这些；见裁决 4）。"""


class AnalysisTransformer:
    """`ANALYSIS.STATIC` 的双向 Transformer（见裁决 1–5）。"""

    name: ClassVar[str] = ANALYSIS_TRANSFORMER_NAME
    operation: ClassVar[str] = "ANALYSIS.STATIC"
    canonical_fields: ClassVar[tuple[str, ...]] = ("analysis_type",)

    def __init__(self, entry: CatalogueEntry) -> None:
        """绑定 catalogue 条目（**不**做 I/O；条目不匹配即拒绝）。"""
        if entry.operation != self.operation:
            raise EtabsTransformerError(self.name, entry.operation)
        self._entry = entry

    # ===== 只读视图 =====

    @property
    def entry(self) -> CatalogueEntry:
        """被绑定的 catalogue 条目（只读用途）。"""
        return self._entry

    @property
    def method(self) -> str:
        """原生方法名（可追溯的事实）。"""
        return self._entry.method

    @property
    def analysis_type(self) -> str:
        """canonical 分析类型的**规范取值**（由 catalogue 推导；见裁决 2）。"""
        return self.operation.rsplit(".", 1)[-1]

    # ===== 请求面 =====

    def request_to_native(self, canonical: Mapping[str, Any]) -> dict[str, Any]:
        """canonical 参数 → 原生参数（本批为空；见裁决 1 / 2 / 3）。

        Raises:
            EtabsTransformerError: `1200`，canonical 出现未声明字段。
            EtabsValidationError: `1200`，`analysis_type` 不是规范取值。
        """
        for key in sorted(map(str, canonical)):
            if key not in self.canonical_fields:
                raise EtabsTransformerError(self.name, key)
        declared = canonical.get("analysis_type")
        if declared is not None and str(declared).upper() != self.analysis_type:
            raise EtabsValidationError(
                "analysis_type_not_in_catalogue",
                operation=self.operation,
                analysis_type=str(declared),
            )
        return {}

    def request_from_native(self, native: Mapping[str, Any]) -> dict[str, Any]:
        """原生参数 → canonical 参数（反向；见裁决 3）。

        Raises:
            EtabsTransformerError: `1200`，原生参数里出现未声明字段。
        """
        for key in sorted(map(str, native)):
            raise EtabsTransformerError(self.name, key)
        return {"analysis_type": self.analysis_type}

    # ===== 结果面 =====

    def result_from_native(self, invocation: ComInvocation) -> dict[str, Any]:
        """原生调用 → canonical 结果（`docs/02` §89；见裁决 4 / 5）。

        Returns:
            canonical 结果；空的原生参数 / 载荷写作 `None`（**不**虚构空对象，
            `docs/04` §44 的同一口径）。
        """
        return {
            "operation": self.operation,
            "protocol": COM_PROTOCOL,
            "method": invocation.method,
            "analysis_type": self.analysis_type,
            "completed": True,
            "arguments": dict(invocation.arguments) or None,
            "native_payload": dict(invocation.payload) or None,
            "native_keys": sorted(str(key) for key in invocation.payload),
            "verification_status": self._entry.verification_status,
        }

    def result_to_native(self, canonical: Mapping[str, Any]) -> dict[str, Any]:
        """canonical 结果 → 原生调用（反向；见裁决 3 / 4）。

        Raises:
            EtabsTransformerError: `1200`，canonical 出现未声明字段。
        """
        for key in sorted(map(str, canonical)):
            if key not in RESULT_FIELDS:
                raise EtabsTransformerError(self.name, key)
        arguments = canonical.get("arguments")
        payload = canonical.get("native_payload")
        return {
            "method": str(canonical.get("method") or self.method),
            "arguments": {} if arguments is None else dict(arguments),
            "payload": {} if payload is None else dict(payload),
        }


TRANSFORMER_REGISTRY: Final[dict[str, type[AnalysisTransformer]]] = {
    ANALYSIS_TRANSFORMER_NAME: AnalysisTransformer,
}
"""Transformer 标识 → 实现（数据库只存**名字**）。"""


def transformer_for(operation: str) -> AnalysisTransformer:
    """取该 Operation 的 Transformer（未覆盖 → 明确失败）。

    Raises:
        OperationNotInCatalogue: `STRUCTAI-3000`，该 Operation 不在 catalogue
            （`details.stage = "capability"`）。
    """
    entry = entry_for(str(operation), capability=capability_for_operation(operation))
    return AnalysisTransformer(entry)
