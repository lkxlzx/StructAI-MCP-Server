"""Infrastructure · Adapters · CSI ETABS · Client —— 请求构造 / 护栏 / 重试 / 熔断（P129–P133）。

权威来源
--------
- `docs/01` §20 L915–916 / `docs/03` §106 L3178–3180 —— 协议 `COM`、方法 `RunAnalysis`。
- `docs/02` §50 —— 原生异常 → 20 码（唯一归一化点是 `base/errors.py`，本模块只**抛**原生族）。
- `docs/07` §12 P130 —— 破坏性操作必须在**发请求之前**拒绝（零 transport 调用）。
- `docs/07` §16 R78 —— `verification_status != VERIFIED` 的条目在生产路径一律拒绝。
- `docs/04` §151 —— 超时 / 重试 / 熔断 / 凭据脱敏的落地口径（`hardening.py` 逐项判定）。

落地裁决（只补实现手段，不改语义）
--------------------------------
1. **护栏全部是纯函数、且都在发请求之前求值**（`docs/07` §12 P130）：任何一条不通过
   → 立即抛，**零** I/O。顺序：破坏性 → 协议 → 验证状态 → 参数形态。
2. **破坏性判据是 Operation 名后缀 `.DELETE`**：本批 catalogue 里**没有**任何删除类
   Operation，故「破坏性请求」只可能来自 Core 的删除族（`MODEL.*.DELETE`）；
   它们**先**在能力阶段落 `3000`（`catalogue.entry_for`），`guard_destructive()`
   是 catalogue 扩展后的**第二道门**（落 `1200`，`details.reason =
   "destructive_operation_rejected"`）。两道门的共同不变量：**零** transport 调用。
3. **超时预算显式**（`docs/04` §151 的 Timeout）：`budget_seconds` 缺省 3600s
   （分析类调用是长任务；参数名**不**叫 `timeout`，避免与 `ruff` 的 ASYNC109 冲突）。
4. **重试 + 熔断**（`docs/04` §151 的 Retry / Circuit breaker）：
   **只**对超时（`2300`，`docs/03` §124 标为可重试）重试，最多 `max_attempts` 次；
   连续失败达到 `failure_threshold` → 熔断打开，后续调用在**发请求前**抛
   `EtabsConnectionError("circuit_open")`（`2000`，可重试）。成功一次即复位。
   ⚠️ 非超时的原生失败**不**重试（不猜测幂等性），直接归一到 `2200`。
5. **原生返回值原样透传、不解释语义**：`invoke` 的返回值必须是映射，
   否则 `EtabsResultShapeError`（`1200`）—— **不**猜测字段名。
6. **凭据永不进入本类**：`EtabsComClient` 不持有凭据（那是 `ComSession` 的职责），
   `repr` 只含协议与预算（`docs/07` §14.3）。

分层红线：只依赖标准库与同包的 `catalogue.py` / `errors.py` / `lifecycle.py`；
**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖 `app.interfaces`。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from app.infrastructure.adapters.etabs.catalogue import VERIFIED, CatalogueEntry
from app.infrastructure.adapters.etabs.errors import (
    EtabsAPIError,
    EtabsCapabilityError,
    EtabsConnectionError,
    EtabsResultShapeError,
    EtabsTimeoutError,
    MappingNotVerified,
    ProtocolNotDeclared,
    UnsupportedRequest,
)
from app.infrastructure.adapters.etabs.lifecycle import ComDispatch
from app.infrastructure.adapters.etabs.manifest import ETABS_PROTOCOLS

__all__ = [
    "CIRCUIT_CLOSED",
    "CIRCUIT_OPEN",
    "COM_PROTOCOL",
    "DECLARED_PROTOCOLS",
    "DEFAULT_BUDGET_SECONDS",
    "DESTRUCTIVE_SUFFIXES",
    "BuiltRequest",
    "CircuitBreaker",
    "ComInvocation",
    "EtabsComClient",
    "RetryPolicy",
    "guard_arguments",
    "guard_destructive",
    "guard_protocol",
    "guard_verified",
    "is_destructive",
]

COM_PROTOCOL: Final[str] = "COM"
"""`docs/01` §20 L915：协议 token（逐字）。"""

DECLARED_PROTOCOLS: Final[tuple[str, ...]] = ETABS_PROTOCOLS
"""已声明协议集（**唯一**来源是 `manifest.py`，避免第二处声明）。"""

DEFAULT_BUDGET_SECONDS: Final[float] = 3600.0
"""分析类调用的缺省超时预算（`docs/04` §151 的 Timeout；见裁决 3）。"""

DESTRUCTIVE_SUFFIXES: Final[tuple[str, ...]] = (".DELETE",)
"""破坏性 Operation 的判据（Core 的删除族命名；见裁决 2）。"""

CIRCUIT_CLOSED: Final[str] = "CLOSED"
CIRCUIT_OPEN: Final[str] = "OPEN"
"""熔断器状态（`docs/04` §151 的 Circuit breaker）。"""


@dataclass(frozen=True, slots=True)
class ComInvocation:
    """一次**已发生**的原生调用（`docs/02` §88 的产物）。

    ⚠️ `arguments` / `payload` 可能含业务数据：`repr` **不**包含它们。
    """

    method: str
    arguments: Mapping[str, Any]
    payload: Mapping[str, Any]

    def __repr__(self) -> str:
        """诊断表示：只含方法名与载荷键数，**不含**内容。"""
        return f"ComInvocation(method={self.method!r}, payload_keys={len(self.payload)})"


@dataclass(frozen=True, slots=True)
class BuiltRequest:
    """一条**已构造**的请求（尚未发出；`docs/07` §12 P130 的「发请求前」分界）。"""

    operation: str
    protocol: str
    method: str
    arguments: Mapping[str, Any]
    verification_status: str
    budget_seconds: float

    def __repr__(self) -> str:
        """诊断表示：**不含**参数（可能含业务数据），只含定位字段。"""
        return (
            f"BuiltRequest(operation={self.operation!r}, protocol={self.protocol!r}, "
            f"method={self.method!r}, budget={self.budget_seconds})"
        )


@dataclass(slots=True)
class RetryPolicy:
    """重试策略（`docs/04` §151 的 Retry；见裁决 4）。"""

    max_attempts: int = 2

    def __post_init__(self) -> None:
        """拒绝非法的重试预算（**不**静默夹取）。"""
        if int(self.max_attempts) < 1:
            raise UnsupportedRequest("retry_budget_invalid", max_attempts=int(self.max_attempts))
        self.max_attempts = int(self.max_attempts)


@dataclass(slots=True)
class CircuitBreaker:
    """熔断器（`docs/04` §151 的 Circuit breaker；见裁决 4）。"""

    failure_threshold: int = 2
    reset_seconds: float = 30.0
    clock: Callable[[], float] = time.monotonic
    failures: int = 0
    state: str = CIRCUIT_CLOSED
    opened_at: float | None = field(default=None, repr=False)

    def allow(self) -> bool:
        """当前是否允许发请求（`OPEN` 且未到重置时刻 → `False`；见裁决 4）。"""
        if self.state == CIRCUIT_CLOSED:
            return True
        if self.opened_at is None:
            return False
        if self.clock() - self.opened_at >= float(self.reset_seconds):
            self.reset()
            return True
        return False

    def record_failure(self) -> None:
        """记录一次失败（达到阈值即打开）。"""
        self.failures += 1
        if self.failures >= int(self.failure_threshold):
            self.state = CIRCUIT_OPEN
            self.opened_at = self.clock()

    def record_success(self) -> None:
        """记录一次成功（复位）。"""
        self.reset()

    def reset(self) -> None:
        """复位为 `CLOSED`（诊断 / 测试用）。"""
        self.failures = 0
        self.state = CIRCUIT_CLOSED
        self.opened_at = None


def is_destructive(operation: str) -> bool:
    """该 Operation 是否属破坏性族（见裁决 2）。"""
    return str(operation).upper().endswith(DESTRUCTIVE_SUFFIXES)


# ===== 护栏（纯函数；见裁决 1）=====


def guard_destructive(operation: str) -> None:
    """破坏性 Operation → **发请求前**拒绝（`docs/07` §12 P130）。

    Raises:
        UnsupportedRequest: `STRUCTAI-1200`，`details.reason = "destructive_operation_rejected"`。
    """
    if is_destructive(operation):
        raise UnsupportedRequest("destructive_operation_rejected", operation=str(operation))


def guard_protocol(entry: CatalogueEntry) -> None:
    """catalogue 条目声明的协议必须在 `AdapterManifest.protocols` 内。

    Raises:
        ProtocolNotDeclared: `STRUCTAI-3000`（`details.stage = "capability"`）。
    """
    if entry.protocol not in DECLARED_PROTOCOLS:
        raise ProtocolNotDeclared(entry.protocol, DECLARED_PROTOCOLS, operation=entry.operation)


def guard_verified(entry: CatalogueEntry, *, allow_partial: bool) -> None:
    """`verification_status != VERIFIED` → 拒绝（除 Contract / E2E 模式；`docs/07` §16 R78）。

    Raises:
        MappingNotVerified: `STRUCTAI-3000`（`details.stage = "capability"`）。
    """
    if allow_partial:
        return
    if entry.verification_status != VERIFIED:
        raise MappingNotVerified(entry.operation, entry.verification_status)


def guard_arguments(arguments: Mapping[str, Any] | None) -> dict[str, Any]:
    """参数形态护栏：必须是映射（**不**猜测、**不**回显内容）。

    Raises:
        UnsupportedRequest: `STRUCTAI-1200`，`details.reason = "arguments_not_a_mapping"`。
    """
    if not isinstance(arguments, Mapping):
        raise UnsupportedRequest("arguments_not_a_mapping")
    return {str(key): value for key, value in arguments.items()}


class EtabsComClient:
    """COM 调用客户端（`docs/01` §20 / `docs/02` §88；见裁决 1–6）。

    ⚠️ 本类**不**做任何业务判断（那是 `operations.py` / `adapter.py` 的职责），
    只负责：护栏 → 构造 → 发请求（含重试 / 熔断）→ 形态校验。
    """

    def __init__(
        self,
        dispatch: ComDispatch,
        *,
        budget_seconds: float = DEFAULT_BUDGET_SECONDS,
        retry: RetryPolicy | None = None,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        """绑定派发端口与重试 / 熔断策略（**不**做任何 I/O）。"""
        self._dispatch = dispatch
        self._budget_seconds = float(budget_seconds)
        self._retry = retry or RetryPolicy()
        self._breaker = breaker or CircuitBreaker()
        self._attempts = 0

    # ===== 只读视图（绝不暴露凭据）=====

    @property
    def retry(self) -> RetryPolicy:
        """重试策略（只读用途）。"""
        return self._retry

    @property
    def breaker(self) -> CircuitBreaker:
        """熔断器（只读用途；诊断 / 验收断言）。"""
        return self._breaker

    @property
    def attempts(self) -> int:
        """最近一次 `send()` 实际发出的调用次数（诊断用）。"""
        return self._attempts

    @property
    def budget_seconds(self) -> float:
        """超时预算（`docs/04` §151 的 Timeout）。"""
        return self._budget_seconds

    def __repr__(self) -> str:
        """诊断表示：只含协议与预算，**不含**凭据 / 参数（见裁决 6）。"""
        return (
            f"EtabsComClient(protocol={COM_PROTOCOL!r}, budget={self._budget_seconds}, "
            f"max_attempts={self._retry.max_attempts})"
        )

    # ===== 请求构造（`docs/07` §12 P130）=====

    def build_request(
        self,
        entry: CatalogueEntry,
        *,
        operation: str,
        arguments: Mapping[str, Any] | None = None,
        allow_partial: bool = False,
    ) -> BuiltRequest:
        """护栏 + 构造（**不**发请求；见裁决 1）。

        Raises:
            UnsupportedRequest: 破坏性 Operation 或参数形态非法（`1200`）。
            ProtocolNotDeclared: 协议未声明（`3000`）。
            MappingNotVerified: `verification_status != VERIFIED`（`3000`）。
        """
        guard_destructive(operation)
        guard_protocol(entry)
        guard_verified(entry, allow_partial=allow_partial)
        body = guard_arguments(arguments)
        return BuiltRequest(
            operation=str(operation),
            protocol=entry.protocol,
            method=entry.method,
            arguments=body,
            verification_status=entry.verification_status,
            budget_seconds=self._budget_seconds,
        )

    # ===== 发请求（`docs/04` §151 的 Timeout / Retry / Circuit breaker）=====

    async def send(self, request: BuiltRequest) -> ComInvocation:
        """发出已构造的请求（超时 → 重试；连续失败 → 熔断；见裁决 4）。

        Raises:
            EtabsConnectionError: `2000` —— 熔断打开（**未**发请求）。
            EtabsTimeoutError: `2300` —— 重试预算耗尽仍超时。
            EtabsAPIError: `2200` —— 原生调用失败（非超时，**不**重试）。
            EtabsResultShapeError: `1200` —— 原生返回值不是映射。
        """
        self._attempts = 0
        last: Exception | None = None
        for _ in range(self._retry.max_attempts):
            if not self._breaker.allow():
                raise EtabsConnectionError(
                    "circuit_open", method=request.method, operation=request.operation
                )
            self._attempts += 1
            try:
                payload = await self._invoke(request)
            except (EtabsTimeoutError, TimeoutError) as error:
                self._breaker.record_failure()
                last = error
                continue
            except EtabsCapabilityError:
                raise
            except Exception as error:
                self._breaker.record_failure()
                raise EtabsAPIError(
                    "native_call_failed",
                    method=request.method,
                    operation=request.operation,
                    error=type(error).__name__,
                ) from error
            self._breaker.record_success()
            return ComInvocation(
                method=request.method,
                arguments=dict(request.arguments),
                payload=payload,
            )
        if last is not None:
            raise last
        raise EtabsConnectionError(  # pragma: no cover - 循环至少执行一次
            "native_call_failed", method=request.method, operation=request.operation
        )

    async def _invoke(self, request: BuiltRequest) -> dict[str, Any]:
        """真正调用原生派发（**唯一**的 transport 接触点）。"""
        try:
            async with asyncio.timeout(float(request.budget_seconds)):
                payload = await self._dispatch.invoke(
                    method=request.method, arguments=dict(request.arguments)
                )
        except TimeoutError as error:
            raise EtabsTimeoutError(
                "request_timed_out", method=request.method, operation=request.operation
            ) from error
        if not isinstance(payload, Mapping):
            raise EtabsResultShapeError(request.method, "payload is not a mapping")
        return {str(key): value for key, value in payload.items()}
