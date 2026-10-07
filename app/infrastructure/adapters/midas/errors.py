"""Infrastructure · Adapters · MIDAS · Errors —— 原生错误族与护栏拒绝（`docs/07` §7.5）。

权威来源
--------
- `docs/07` §7.5（错误归一化）—— 连接失败 `STRUCTAI-2000` · 鉴权失败 `2100` ·
  软件 API 报错 `2200` · 超时 `2300` · 能力不支持 `3000` · Adapter 内部 `6000`；
  并明确：`verification_status != VERIFIED` → `RegistryMappingNotVerified`。
- `docs/07` §11（20 码契约）—— 本模块**不**新增 `STRUCTAI-xxxx` 码。
- `docs/07` §7.6（实测行为约束）—— NX 系 `DELETE` 必须带路径 key；Designer 空主体 /
  `Type=0` = 删全部；`-M1` 变体仅 Hyper-S 求解器可用。
- `docs/04` §50（错误归一化）/ §130（`RegistryMappingNotVerified`）。
- `registry/README.md` §4 —— `enabled: false` → 客户端**直接拒绝调用**。

落地裁决（只补实现手段，不改码值 / 不改语义）
--------------------------------------------
1. **全部继承既有原生错误族**：本模块的异常都派生自
   `app/infrastructure/adapters/base/errors.py` 的 `AdapterNativeError` 子类，
   因此「原生异常 → 20 码」仍只有**一处**实现（`normalize_error()`），
   MIDAS 侧不新增第二套映射。
2. **`RegistryMappingNotVerified` 落 `STRUCTAI-3000`**：`docs/04` §130 要求该异常，
   而它**不在** 20 码契约内（`docs/07` §11）。裁决：实现为 `AdapterCapabilityError`
   的子类（`details.reason = "registry_mapping_not_verified"`）——
   「该端点未通过验证」正是「该实例不具备该能力」的一种，且**不**新增码。
3. **破坏性护栏拒绝落 `STRUCTAI-1200`**：`docs/07` §12 P123 要求「在**发请求前**拒绝」，
   此时「什么都没做」，与 P14–P18 的 R28（前置 / 语义非法 → `1200`）同口径。
   求解器门控是**能力**问题（`docs/07` §7.3 的 `SolverUnsupported`）→ `STRUCTAI-3000`。
4. **`details` 只放非敏感诊断**：`reason` / `method` / `path` / `solver` /
   `verification_status` 等；**绝不**放 MAPI-Key、请求体或响应体原文（`docs/07` §14.3）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与既有 Adapter 基座；**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx。
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
    "MIDAS_ERROR_STAGE",
    "MidasAPIError",
    "MidasAuthenticationError",
    "MidasCapabilityError",
    "MidasConnectionError",
    "MidasEndpointDisabled",
    "MidasGlobalDeleteRejected",
    "MidasResultShapeError",
    "MidasSchemaShapeMismatch",
    "MidasSolverUnsupported",
    "MidasTimeoutError",
    "MidasTransformerError",
    "MidasValidationError",
    "RegistryMappingNotVerified",
]

MIDAS_ERROR_STAGE: Final[str] = "midas_adapter"
"""归一化错误 `details.stage` 的固定取值（诊断定位用，非敏感）。"""


def _details(reason: str, **kwargs: Any) -> dict[str, Any]:
    """统一构造 `details`：`stage` + **机器可读的 `reason`** + 非敏感诊断字段。

    `reason` 与异常的 message 同源，但它进 `details` 后**不必**经过
    `normalize_error()` 才能被读到 —— 验收测试与上层诊断都直接读它
    （`docs/07` §7.5 / §14.3：`details` 只放非敏感字段）。
    """
    return {"stage": MIDAS_ERROR_STAGE, "reason": reason, **kwargs}


class MidasValidationError(AdapterValidationError):
    """参数 / 工程语义非法 → `STRUCTAI-1200`（`docs/07` §7.5 的族归属）。"""

    def __init__(self, reason: str, **kwargs: Any) -> None:
        super().__init__(reason, details=_details(reason, **kwargs))


class MidasConnectionError(AdapterConnectionError):
    """连接失败 / 中继掉线 → `STRUCTAI-2000`（`docs/07` §7.5 / §11 补充）。"""

    def __init__(self, reason: str, **kwargs: Any) -> None:
        super().__init__(reason, details=_details(reason, **kwargs))


class MidasAuthenticationError(AdapterAuthenticationError):
    """鉴权失败 → `STRUCTAI-2100`（`docs/07` §7.5；**不**回显凭据）。"""

    def __init__(self, reason: str, **kwargs: Any) -> None:
        super().__init__(reason, details=_details(reason, **kwargs))


class MidasAPIError(AdapterAPIError):
    """软件返回业务错误 → `STRUCTAI-2200`（`docs/07` §7.5）。"""

    def __init__(self, reason: str, **kwargs: Any) -> None:
        super().__init__(reason, details=_details(reason, **kwargs))


class MidasTimeoutError(AdapterTimeoutError):
    """调用超时 → `STRUCTAI-2300`（`docs/07` §7.5；`docs/04` §57 的 UNKNOWN 语义）。"""

    def __init__(self, reason: str, **kwargs: Any) -> None:
        super().__init__(reason, details=_details(reason, **kwargs))


class MidasCapabilityError(AdapterCapabilityError):
    """实例不具备该能力 → `STRUCTAI-3000`（`docs/07` §7.5）。"""

    def __init__(self, reason: str, **kwargs: Any) -> None:
        super().__init__(reason, details=_details(reason, **kwargs))


class MidasSolverUnsupported(MidasCapabilityError):
    """求解器门控（`docs/07` §7.3 / §7.6：`-M1` 变体仅 Hyper-S 可用）→ `3000`。"""

    def __init__(self, required: str, available: str, **kwargs: Any) -> None:
        super().__init__(
            "solver_unsupported",
            required_solver=required,
            instance_solver=available,
            **kwargs,
        )


class MidasEndpointDisabled(MidasCapabilityError):
    """数据文件 `enabled: false`（`registry/README.md` §4）→ `STRUCTAI-3000`。"""

    def __init__(self, endpoint: str, reason: str = "", **kwargs: Any) -> None:
        super().__init__("endpoint_disabled", endpoint=endpoint, source_reason=reason, **kwargs)


class RegistryMappingNotVerified(MidasCapabilityError):
    """`verification_status != VERIFIED`（`docs/04` §130；`docs/07` §7.2）→ `3000`。

    见模块裁决 2：该异常名取自规范原文，但**不**新增 `STRUCTAI-xxxx` 码。
    """

    def __init__(self, operation: str, endpoint: str, status: str, **kwargs: Any) -> None:
        super().__init__(
            "registry_mapping_not_verified",
            operation=operation,
            endpoint=endpoint,
            verification_status=status,
            **kwargs,
        )


class MidasGlobalDeleteRejected(MidasValidationError):
    """破坏性护栏：全表删除被拒（`docs/07` §7.6；`registry/README.md` §4）→ `1200`。

    两种触发形态（**发请求前**拒绝）：
    ① NX 系 `DELETE {uri}` 不带路径 key = 删全表；
    ② Designer 空主体 / `Type=0` = 删全部。
    """

    def __init__(self, reason: str, **kwargs: Any) -> None:
        super().__init__("global_delete_rejected", guard=reason, **kwargs)


class MidasSchemaShapeMismatch(MidasValidationError):
    """请求体形态与数据文件的 `schema_shape` 不符（`docs/07` §7.3 第 4 步）→ `1200`。"""

    def __init__(self, endpoint: str, expected: str, **kwargs: Any) -> None:
        super().__init__("schema_shape_mismatch", endpoint=endpoint, expected=expected, **kwargs)


class MidasTransformerError(MidasValidationError):
    """Transformer 拒绝：字段未在 Registry Schema 中登记（**不**臆造）→ `1200`。"""

    def __init__(self, transformer: str, field: str, **kwargs: Any) -> None:
        super().__init__(
            "transformer_field_not_in_schema", transformer=transformer, field=field, **kwargs
        )


class MidasResultShapeError(MidasValidationError):
    """原生结果形态不符（`docs/04` §46）→ `1200`；**不**臆造数值。"""

    def __init__(self, table: str, reason: str, **kwargs: Any) -> None:
        super().__init__("result_shape_invalid", table=table, detail=reason, **kwargs)
