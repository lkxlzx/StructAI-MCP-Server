"""Infrastructure · Adapters · CSI ETABS · Errors —— 原生错误族（`docs/07` §11 / §14.2）。

权威来源
--------
- `docs/07` §11 —— **20 码**错误契约；本模块**不**新增 `STRUCTAI-xxxx` 码。
- `docs/02` §49 / §50 —— 原生异常 → StructAI Error 的族归属
  （连接 `2000` / 鉴权 `2100` / 软件 API `2200` / 超时 `2300` / 能力 `3000` / 内部 `6000`）。
- `docs/07` §12 P127–P133 —— 第二个软件（ETABS / CSI）只允许新增
  Adapter / Registry / Schema / Transformer / Capability Mapping / Contract Test，
  **不**改 Core 契约。
- `docs/07` §16 R63 —— 能力拒绝的 `details` 口径：`stage = "capability"` +
  `missing` / `statuses`（**不**静默成功、**不**回落、**不**新增码）。
- `docs/04` §151 —— 生产加固清单（`hardening.py` 逐项给出判定）。

落地裁决（只补实现手段，不改码值 / 不改语义）
--------------------------------------------
1. **全部继承既有原生错误族**：本模块的异常都派生自
   `app/infrastructure/adapters/base/errors.py` 的 `AdapterNativeError` 子类，
   因此「原生异常 → 20 码」仍只有**一处**实现（`normalize_error()`）——
   本子包**不**建第二套映射表。
2. **能力阶段拒绝的 `stage` 写作 `capability`**（`docs/07` §16 R63 的既有口径）：
   `OperationNotInCatalogue` / `ProtocolNotDeclared` / `MappingNotVerified` 三条
   都落 `STRUCTAI-3000`，且 `details.stage = "capability"` —— 与 Core 第 16 步
   （`Capability Check`）的拒绝形状一致，客户端无法区分「Core 判定不支持」与
   「Adapter 判定不支持」，这正是「能力问题只有一种对外形状」的要求。
3. **破坏性拒绝落 `STRUCTAI-1200`**：`docs/07` §12 P130 要求「在**发请求前**拒绝」，
   此时「什么都没做」，与 P14–P18 的 R28（前置 / 语义非法 → `1200`）同口径。
   ⚠️ 但**未**进入 catalogue 的破坏性 Operation（如 `MODEL.NODE.DELETE`）**先**在
   能力阶段落 `3000`（见裁决 2 与 `catalogue.py`）—— `guard_destructive()` 是
   catalogue 扩展后的第二道门，两者的共同不变量是「**零** transport 调用」。
4. **`details` 只放非敏感诊断**：`operation` / `method` / `protocol` /
   `verification_status` 等；**绝不**放凭据、请求体或原生响应体原文
   （`docs/07` §14.3）。本模块**不**接收原生 message。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与既有 Adapter 基座；**不**引用 SQLAlchemy / FastAPI / MCP SDK /
httpx，**不**依赖 `app.interfaces` / `app.application`。
"""

from __future__ import annotations

from typing import Any, Final

from app.infrastructure.adapters.base.errors import (
    AdapterAPIError,
    AdapterAuthenticationError,
    AdapterCapabilityError,
    AdapterConnectionError,
    AdapterTimeoutError,
    AdapterValidationError,
)

__all__ = [
    "CAPABILITY_STAGE",
    "ETABS_ERROR_STAGE",
    "CatalogueNotTraceable",
    "EtabsAPIError",
    "EtabsAuthenticationError",
    "EtabsCapabilityError",
    "EtabsConnectionError",
    "EtabsResultShapeError",
    "EtabsTimeoutError",
    "EtabsTransformerError",
    "EtabsValidationError",
    "MappingNotVerified",
    "OperationNotInCatalogue",
    "ProtocolNotDeclared",
    "UnsupportedRequest",
]

ETABS_ERROR_STAGE: Final[str] = "etabs_adapter"
"""归一化错误 `details.stage` 的固定取值（诊断定位用，非敏感）。"""

CAPABILITY_STAGE: Final[str] = "capability"
"""能力阶段拒绝的 `details.stage`（`docs/07` §16 R63 的既有口径；见模块裁决 2）。"""


def _details(reason: str, *, stage: str = ETABS_ERROR_STAGE, **kwargs: Any) -> dict[str, Any]:
    """统一构造 `details`：`stage` + **机器可读的 `reason`** + 非敏感诊断字段。

    `reason` 与异常的 message 同源，但它进 `details` 后**不必**经过
    `normalize_error()` 才能被读到 —— 验收测试与上层诊断都直接读它
    （`docs/07` §14.3：`details` 只放非敏感字段）。
    """
    return {"stage": stage, "reason": reason, **kwargs}


class EtabsValidationError(AdapterValidationError):
    """参数 / 工程语义非法 → `STRUCTAI-1200`（`docs/02` §50 的族归属）。"""

    def __init__(self, reason: str, **kwargs: Any) -> None:
        """记录原因与诊断信息。"""
        super().__init__(reason, details=_details(reason, **kwargs))


class EtabsConnectionError(AdapterConnectionError):
    """连接失败 / 会话不可用 / 熔断打开 → `STRUCTAI-2000`（可重试，`docs/03` §124）。"""

    def __init__(self, reason: str, **kwargs: Any) -> None:
        """记录原因与诊断信息。"""
        super().__init__(reason, details=_details(reason, **kwargs))


class EtabsAuthenticationError(AdapterAuthenticationError):
    """软件侧凭据无效 → `STRUCTAI-2100`（**不**回显凭据）。"""

    def __init__(self, reason: str, **kwargs: Any) -> None:
        """记录原因与诊断信息。"""
        super().__init__(reason, details=_details(reason, **kwargs))


class EtabsAPIError(AdapterAPIError):
    """软件返回业务错误 → `STRUCTAI-2200`（`docs/02` §50）。"""

    def __init__(self, reason: str, **kwargs: Any) -> None:
        """记录原因与诊断信息。"""
        super().__init__(reason, details=_details(reason, **kwargs))


class EtabsTimeoutError(AdapterTimeoutError):
    """原生调用超时 → `STRUCTAI-2300`（可重试；见 `client.py` 的重试 / 熔断）。"""

    def __init__(self, reason: str, **kwargs: Any) -> None:
        """记录原因与诊断信息。"""
        super().__init__(reason, details=_details(reason, **kwargs))


class EtabsCapabilityError(AdapterCapabilityError):
    """实例不具备该能力 → `STRUCTAI-3000`（`docs/07` §11）。"""

    def __init__(self, reason: str, **kwargs: Any) -> None:
        """记录原因与诊断信息。"""
        super().__init__(reason, details=_details(reason, **kwargs))


class OperationNotInCatalogue(EtabsCapabilityError):
    """该 Operation **不在**可追溯 catalogue 里 → `STRUCTAI-3000`（见模块裁决 2）。

    `details.stage = "capability"`、`details.missing = [<能力码>]`，
    形状与 Core 第 16 步（`Capability Check`）的拒绝一致（`docs/07` §16 R63）。
    """

    def __init__(self, operation: str, *, capability: str | None = None, **kwargs: Any) -> None:
        """记录未覆盖的 Operation；能力码**只**在已知时带上（见 `capabilities.py` 裁决 2）。"""
        extra: dict[str, Any] = {}
        if capability is not None:
            extra = {"missing": [str(capability)], "statuses": ["UNSUPPORTED"]}
        super().__init__(
            "operation_not_in_catalogue",
            stage=CAPABILITY_STAGE,
            operation=str(operation),
            **extra,
            **kwargs,
        )


class ProtocolNotDeclared(EtabsCapabilityError):
    """catalogue 条目声明的协议不在 `AdapterManifest.protocols` 内 → `STRUCTAI-3000`。"""

    def __init__(self, protocol: str, declared: tuple[str, ...], **kwargs: Any) -> None:
        """记录条目协议与已声明协议集。"""
        super().__init__(
            "protocol_not_declared",
            stage=CAPABILITY_STAGE,
            protocol=str(protocol),
            declared=list(declared),
            **kwargs,
        )


class MappingNotVerified(EtabsCapabilityError):
    """catalogue 条目的 `verification_status != VERIFIED` → `STRUCTAI-3000`。

    与 MIDAS 侧 `RegistryMappingNotVerified` 同口径（`docs/07` §16 R78）：
    `VERIFIED` 的判定是 **7 项 AND**（含「至少一次真实 Contract Test 通过」），
    本批**没有**任何 ETABS 实例 / 凭据，故条目如实登记为 `PARTIAL`，
    生产路径一律拒绝；只有 Contract / E2E 模式（`allow_partial=True`）才放行。
    """

    def __init__(self, operation: str, status: str, **kwargs: Any) -> None:
        """记录 Operation 与它当前的验证状态。"""
        super().__init__(
            "catalogue_entry_not_verified",
            stage=CAPABILITY_STAGE,
            operation=str(operation),
            verification_status=str(status),
            **kwargs,
        )


class UnsupportedRequest(EtabsValidationError):
    """破坏性 / 未声明形态的请求被拒（**发请求前**）→ `STRUCTAI-1200`（见模块裁决 3）。"""

    def __init__(self, reason: str, **kwargs: Any) -> None:
        """记录被拒的原因（机器可读 `reason`）。"""
        super().__init__(reason, **kwargs)


class EtabsTransformerError(EtabsValidationError):
    """Transformer 拒绝：canonical 字段未在本批声明的词表内（**不**臆造原生字段）→ `1200`。"""

    def __init__(self, transformer: str, field: str, **kwargs: Any) -> None:
        """记录 Transformer 名与未覆盖的字段名。"""
        super().__init__(
            "transformer_field_not_declared",
            transformer=str(transformer),
            field=str(field),
            **kwargs,
        )


class EtabsResultShapeError(EtabsValidationError):
    """原生调用结果形态不符（`docs/02` §89）→ `1200`；**不**臆造语义。"""

    def __init__(self, method: str, reason: str, **kwargs: Any) -> None:
        """记录 COM 方法与形态缺陷原因。"""
        super().__init__("result_shape_invalid", method=str(method), detail=str(reason), **kwargs)


class CatalogueNotTraceable(EtabsCapabilityError):
    """catalogue 条目缺少出处锚点 / 形状非法 → `STRUCTAI-3000`（装配期自检，**不**静默放行）。"""

    def __init__(self, operation: str, reason: str, **kwargs: Any) -> None:
        """记录条目与自检失败原因。"""
        super().__init__(
            "catalogue_entry_not_traceable",
            stage=CAPABILITY_STAGE,
            operation=str(operation),
            detail=str(reason),
            **kwargs,
        )
