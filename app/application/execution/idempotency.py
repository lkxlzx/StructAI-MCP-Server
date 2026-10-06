"""Application · Execution · IdempotencyService（`docs/07` §10.3 / §12 P21；`docs/02` §28–§35）。

落点裁定（本批裁决，已回填 `docs/07` §16 R39）
----------------------------------------------
**`app/application/execution/idempotency.py`** —— 归**执行流水线**，不落
`app/application/services/`。依据：

1. **规范原文直接给出该路径**：`docs/02` §37（`blue` 来源）逐字写明
   「文件：`application/execution/idempotency.py`」，唯一键与原子写入写在同一节。
2. **`docs/07` §9 把 Idempotency 列为流水线第 14 步**（「Idempotency ← 先于 Lock」），
   其不可变依据写明「重复请求直接返回，不抢锁」—— 语义完全由流水线位置定义。
3. **它不跨流程**：`app/application/services/`（`docs/07` §3.3）列的是
   `adapter_resolver` / `capability_resolver` / `document` / `model` / `result` /
   `quota` / `backup` —— 这些会被**多条流程**复用（如 `CapabilityResolver` 同时被
   流水线与 Adapter 运行时消费）。幂等只在执行入口被消费一次，故与 `confirmation.py` /
   `preconditions.py` / `postconditions.py` 同层。
4. `docs/07` §3.3 的冻结树**未**列出该文件（它是后续批次的产物），§9 的步骤归属
   是「就近落点」的唯一依据。

权威来源
--------
- `docs/02` §28（Atomic Idempotency；`blue`）—— 唯一键 `tenant_id + idempotency_key`，
  **必须** `atomic INSERT`，**不是** `SELECT` 然后 `INSERT`；重复请求必须返回已有响应。
- `docs/02` §28（Idempotency Service；`source9`）—— `get_existing` / `reserve` /
  `complete` 三个方法；「必须有数据库唯一约束」。
- `docs/02` §31（Idempotency Key）—— Key 必须与 `tenant` 绑定；唯一逻辑 `(tenant_id, key)`。
- `docs/02` §32（Request Hash）—— 不能只存 key，还必须存 `request_hash`：
  「`key = A` / `request = X`」成功后「`key = A` / `request = Y`」**必须拒绝**。
- `docs/02` §33（IdempotencyService）—— `hash_request(request)` 的**逐字实现**：
  `payload = {tool, operation, parameters, context, dry_run}` →
  `json.dumps(sort_keys=True, separators=(",", ":"))` → `sha256(...).hexdigest()`。
- `docs/02` §34（Idempotency Check）—— 记录不存在 → `None`；`request_hash` 不同 →
  抛错；否则返回 `record.response_json`。
- `docs/02` §35（Idempotency Atomicity）—— 禁止 `SELECT → 不存在 → INSERT`；
  **必须** `UNIQUE(tenant_id, key)` 然后捕获 `IntegrityError` 重新读取已有记录。
- `docs/02` §57（Pipeline Step 7：Idempotency）—— 有 key 就 `hash_request` 查历史结果；
  有则**直接返回历史结果**，无则继续执行。
- `docs/02` §64（Pipeline Step 14：Idempotency Store）—— 执行成功 → 响应转 JSON →
  `IdempotencyRecord`；以后重复请求直接返回相同响应。
- `docs/02` §90（Task Engine 与 Idempotency）—— 顺序 `ExecutionService → Idempotency →
  Task Create`：**不得**先建 Task，否则重复请求会创建多个 Task。
- `docs/07` §10.3（幂等原子性）—— 唯一键 `(tenant_id, idempotency_key)`；
  `request_hash` 不同 → **`STRUCTAI-1300`**（冲突）。
- `docs/07` §9 第 14 步 —— `Idempotency` **先于** `Concurrency / Resource Lock`（第 15 步）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **`STRUCTAI-1300` 而不是 `STRUCTAI-1100`**（本批裁决，见 `docs/07` §16 R39）：
   `docs/02` §34 写的是 `ValidationError`、§87（Idempotency Conflict Test）的期望是
   `STRUCTAI-1100`，而 `docs/07` §10.3 明确「`request_hash` 不同 → `STRUCTAI-1300`」，
   §11 的错误契约也把「**幂等键冲突**」直接归到 `STRUCTAI-1300 Concurrency Conflict`。
   本模块以 **`docs/07` §10.3 / §11 为准**（本项目错误契约的权威，且 §11 的触发场景逐字
   包含「幂等键冲突」），统一抛 `ConcurrencyConflictError`（`STRUCTAI-1300`）。
2. **`hash_request` 的 `context` 需要规范化**：`docs/02` §33 的原文是
   `"context": request.context`，而 `context` 在 P14 落地为 `ExecutionContext`
   （frozen dataclass，含 `UUID` / `StrEnum` 字段），**不能**直接被 `json.dumps`
   序列化。故本模块先做一次**确定性规范化**（dataclass → 字段字典、`Enum` → `value`、
   `UUID` → 字符串、`set` → 排序列表），再按 §33 的 `sort_keys` / `separators` 序列化。
   规范化只做类型转换，**不**改变任何取值，因此「同一请求 → 同一摘要」仍然成立。
3. **「同键同摘要但尚无响应」= `STRUCTAI-1300`（`in_flight`）**：`docs/02` §34 的
   原文会返回 `record.response_json`（可能为 `None`），§28 的 `reserve` / `complete`
   之间确实存在「已抢占、未完成」的窗口。返回 `None` 会让调用方**无从区分**
   「没有历史响应」与「有历史响应但是空的」，且 `docs/07` §9 的「重复请求直接返回」
   在无响应时无法成立。故本模块把该情形判为**并发冲突**（同族码 `STRUCTAI-1300`，
   `details.reason = "in_flight"`）：既不返回半截响应，也**不**重复执行 Adapter。
4. **冲突绝不写库**：`request_hash` 不同 / `in_flight` 两条失败路径都只做**回读**，
   不产生新记录、不修改既有记录（`docs/02` §35 的「重新读取」）；
   验收门槛 ⑤ 逐条核验失败路径不留半条记录。
5. **`details` 不含幂等键原文**：错误信封只放 `stage` / `reason`
   （`docs/07` §14.3：绝不记录 secret；此处采取更严格口径 —— 不把客户端提交的
   业务标识回显到错误信息里）。
6. **响应只在首次成功时写入**（`complete` 的 `WHERE response_json IS NULL`，
   见 `repositories/idempotency.py` 模块裁决 3）。

分层红线（`docs/07` §14.1 / §2.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 ORM / Web 框架 / MCP SDK / httpx，
**不**依赖 `app.infrastructure`（持久化经 Domain 契约 `IdempotencyStore` 注入），
也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from enum import Enum, StrEnum
from typing import Any, Final
from uuid import UUID

from app.domain.errors import ConcurrencyConflictError, InternalError
from app.domain.protocols import (
    IdempotencyRecord,
    IdempotencyReservation,
    IdempotencyStore,
)

__all__ = [
    "IDEMPOTENCY_CONFLICT_MESSAGE",
    "IDEMPOTENCY_FAILURE_REASONS",
    "IDEMPOTENCY_HASH_ALGORITHM",
    "IDEMPOTENCY_HASH_FIELDS",
    "IDEMPOTENCY_IN_FLIGHT_MESSAGE",
    "IDEMPOTENCY_STAGE",
    "REQUEST_HASH_LENGTH",
    "IdempotencyDecision",
    "IdempotencyOutcome",
    "IdempotencyService",
    "canonical_payload",
    "decode_response",
    "encode_response",
    "hash_payload",
]

IDEMPOTENCY_HASH_FIELDS: Final[tuple[str, ...]] = (
    "tool",
    "operation",
    "parameters",
    "context",
    "dry_run",
)
"""`docs/02` §33 的 `hash_request` 载荷字段（逐字照抄，顺序即规范顺序）。"""

IDEMPOTENCY_HASH_ALGORITHM: Final[str] = "sha256"
"""摘要算法（`docs/02` §33 原文 `hashlib.sha256(...).hexdigest()`）。"""

REQUEST_HASH_LENGTH: Final[int] = 64
"""`request_hash` 的十六进制长度（SHA-256 = 32 字节 → 64 字符；`docs/02` §33）。

与 P04 落地的列宽一致：`idempotency_records.request_hash` 是 `String(128)`
（`app/infrastructure/database/models/idempotency.py` 给了余量以兼容更强的摘要）。
"""

IDEMPOTENCY_STAGE: Final[str] = "idempotency"
"""错误 `details.stage` 的固定取值（与 `confirmation` / `preconditions` 同口径）。"""

IDEMPOTENCY_CONFLICT_MESSAGE: Final[str] = "Idempotency key reused with different request"
"""同键不同摘要的对外消息（`docs/02` §34 原文，逐字照抄）。"""

IDEMPOTENCY_IN_FLIGHT_MESSAGE: Final[str] = "Idempotency key is already in flight"
"""同键同摘要但尚无响应的对外消息（见模块裁决 3）。"""

IDEMPOTENCY_FAILURE_REASONS: Final[tuple[str, ...]] = (
    "request_hash_mismatch",
    "in_flight",
)
"""失败原因词表（见模块裁决 3；两者都落 `STRUCTAI-1300`）。"""


class IdempotencyOutcome(StrEnum):
    """一次幂等判定的结果（`docs/02` §32 的 `Atomic Insert → Conflict?` 两个分支）。

    - `RESERVED` —— 本次 `INSERT` 抢占成功 → **继续执行**（`docs/02` §32 的 `No` 分支）；
    - `REPLAY` —— 同键同摘要且已有响应 → **直接返回既有响应，不执行 Adapter**
      （`docs/02` §32 的 `Yes` 分支 / §57 / §86）。

    失败（`request_hash` 不同 / `in_flight`）**不**是本枚举的取值：它们是错误，
    由 `begin()` 直接抛 `STRUCTAI-1300`（`docs/07` §10.3；见模块裁决 1 / 3）。
    """

    RESERVED = "RESERVED"
    REPLAY = "REPLAY"


@dataclass(frozen=True, slots=True)
class IdempotencyDecision:
    """`begin()` 的返回（`docs/02` §32 / §57）。

    - `record` —— 本次归属的记录（抢占成功时是刚插入的那一行，重放时是既有行）；
    - `response` —— 仅 `REPLAY` 时有值：**已经发生过**的响应快照
      （`docs/02` §86「直接 `return cached response`」）。

    ⚠️ 只有 `RESERVED` 才允许调用 Adapter；`REPLAY` **必须**原样返回 `response`
    （`docs/02` §86：不执行 Adapter）。
    """

    outcome: IdempotencyOutcome
    record: IdempotencyRecord
    response: Mapping[str, Any] | None = None

    @property
    def reserved(self) -> bool:
        """本次是否抢占了幂等键（→ 调用方继续执行）。"""
        return self.outcome is IdempotencyOutcome.RESERVED

    @property
    def replayed(self) -> bool:
        """本次是否为重放（→ 调用方直接返回 `response`，**不**执行 Adapter）。"""
        return self.outcome is IdempotencyOutcome.REPLAY


class IdempotencyService:
    """幂等键的原子抢占 / 重放 / 冲突判定（`docs/02` §28–§35；`docs/07` §10.3）。

    ⚠️ 持久化经 Domain 契约 `IdempotencyStore` 注入：本模块**不**依赖
    `app.infrastructure`（`docs/07` §14.1）。事务边界归调用方的 `UnitOfWork`
    （`docs/02` §16）—— 本类**从不** `commit` / `rollback`。
    """

    def __init__(self, store: IdempotencyStore) -> None:
        """绑定幂等记录存储。

        Args:
            store: `docs/02` §28 的持久化入口（`reserve` / `existing` / `complete`）。
        """
        self._store = store

    @property
    def store(self) -> IdempotencyStore:
        """被绑定的存储（只读用途）。"""
        return self._store

    # ===== `docs/02` §33：hash_request =====

    def hash_request(self, request: Mapping[str, Any] | object) -> str:
        """按 `docs/02` §33 计算请求摘要（逐字实现规范载荷与序列化口径）。

        Args:
            request: 具备 `tool` / `operation` / `parameters` / `context` / `dry_run`
                五个字段的请求（`Mapping` 或带同名属性的对象）。

        Returns:
            `sha256` 十六进制摘要（64 字符）。

        Raises:
            TypeError: 请求缺少 §33 要求的任一字段（不静默用空值兜底 ——
                那样会让「字段缺失」与「字段为空」产生同一摘要）。
            TypeError: 字段取值无法确定性地序列化（见模块裁决 2）。
        """
        payload = {name: _field_of(request, name) for name in IDEMPOTENCY_HASH_FIELDS}
        return hash_payload(payload)

    # ===== `docs/02` §28 / §34：读取与抢占 =====

    async def get_existing(
        self,
        tenant_id: str,
        key: str,
    ) -> IdempotencyRecord | None:
        """读取既有记录（`docs/02` §28 的 `get_existing`）。

        ⚠️ **只读**，**不是**抢占路径：抢占**必须**走 `reserve()`（`docs/02` §35）。
        """
        return await self._store.existing(tenant_id=tenant_id, idempotency_key=key)

    async def check(
        self,
        tenant_id: str,
        key: str,
        request_hash: str,
    ) -> Mapping[str, Any] | None:
        """`docs/02` §34 的 `check`（查询历史结果，不写入）。

        Args:
            tenant_id: 租户标识（`docs/02` §31）。
            key: 幂等键。
            request_hash: 本次请求摘要。

        Returns:
            - 记录不存在 → `None`（`docs/02` §34 的 `record is None` → `return None`）；
            - 同键同摘要且已有响应 → 既有响应快照（`record.response_json`）；
            - 同键同摘要但尚无响应 → `None`（尚未完成；调用方应改用 `begin()`）。

        Raises:
            ConcurrencyConflictError: 同键**不同**摘要（`STRUCTAI-1300`；
                `docs/07` §10.3 / §11；见模块裁决 1）。
        """
        record = await self._store.existing(tenant_id=tenant_id, idempotency_key=key)
        if record is None:
            return None
        if record.request_hash != request_hash:
            raise self._conflict("request_hash_mismatch")
        if record.response_json is None:
            return None
        return decode_response(record.response_json)

    async def reserve(
        self,
        tenant_id: str,
        key: str,
        request_hash: str,
    ) -> IdempotencyReservation:
        """原子抢占幂等键（`docs/02` §28 的 `reserve`；§32 / §35 的 `Atomic Insert`）。

        ⚠️ 本方法**不**做存在性预查：唯一键冲突由**数据库约束**发现并回读
        （`docs/02` §35）。判定「继续执行还是重放」请用 `begin()`。
        """
        return await self._store.reserve(
            tenant_id=tenant_id,
            idempotency_key=key,
            request_hash=request_hash,
        )

    async def complete(
        self,
        record_id: str,
        response: Mapping[str, Any],
    ) -> bool:
        """写入首次成功执行的响应快照（`docs/02` §28 的 `complete`；§64）。

        Args:
            record_id: `reserve()` / `begin()` 返回的记录 id。
            response: 归一化响应（`docs/02` §64 的 `response → JSON → IdempotencyRecord`）。

        Returns:
            `True` 表示本次写入了响应；`False` 表示记录不存在或已有响应
            （后者**不可覆盖** —— 见 `repositories/idempotency.py` 模块裁决 3）。
        """
        return await self._store.complete(record_id, encode_response(response))

    # ===== `docs/02` §32 / §57：一步到位的原子入口 =====

    async def begin(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> IdempotencyDecision:
        """原子抢占 + 重放判定（`docs/02` §32 的 `Atomic Insert → Conflict?` 全流程）。

        `docs/02` §57 的流水线语义：有历史结果 → **直接返回**；没有 → 继续执行。

        Args:
            tenant_id: 租户标识（`docs/02` §31：Key 与 tenant 绑定）。
            idempotency_key: 客户端提交的幂等键。
            request_hash: `hash_request()` 的结果。

        Returns:
            `IdempotencyDecision`：
            - `RESERVED` —— 抢占成功，调用方**继续执行**，成功后调用 `complete()`；
            - `REPLAY` —— 同键同摘要且已有响应，调用方**直接返回** `response`，
              **不得**执行 Adapter（`docs/02` §86）。

        Raises:
            ConcurrencyConflictError: `STRUCTAI-1300`（`docs/07` §10.3 / §11）——
                同键**不同**摘要（`reason="request_hash_mismatch"`，
                `docs/02` §32：`key = A` / `request = Y` 必须拒绝），
                或同键同摘要但**尚无响应**（`reason="in_flight"`，见模块裁决 3）。
                两条路径都**不**写入、**不**修改任何记录。
        """
        reservation = await self.reserve(tenant_id, idempotency_key, request_hash)
        if reservation.created:
            return IdempotencyDecision(
                outcome=IdempotencyOutcome.RESERVED,
                record=reservation.record,
            )

        record = reservation.record
        if record.request_hash != request_hash:
            raise self._conflict("request_hash_mismatch")
        if record.response_json is None:
            raise self._in_flight()

        return IdempotencyDecision(
            outcome=IdempotencyOutcome.REPLAY,
            record=record,
            response=decode_response(record.response_json),
        )

    # ===== 错误构造（形状一致；见模块裁决 5）=====

    def _conflict(self, reason: str) -> ConcurrencyConflictError:
        """同键不同摘要 → `STRUCTAI-1300`（`docs/07` §10.3 / §11）。"""
        return ConcurrencyConflictError(
            IDEMPOTENCY_CONFLICT_MESSAGE,
            details={"stage": IDEMPOTENCY_STAGE, "reason": reason},
        )

    def _in_flight(self) -> ConcurrencyConflictError:
        """同键同摘要但尚无响应 → `STRUCTAI-1300`（见模块裁决 3）。"""
        return ConcurrencyConflictError(
            IDEMPOTENCY_IN_FLIGHT_MESSAGE,
            details={"stage": IDEMPOTENCY_STAGE, "reason": "in_flight"},
        )


# ===== `docs/02` §33 的摘要与 `docs/02` §64 的响应序列化 =====


def canonical_payload(payload: Mapping[str, Any]) -> str:
    """`docs/02` §33 的规范化 JSON 文本（`sort_keys=True` + `separators=(",", ":")`）。

    先经 `_jsonable` 做确定性规范化（见模块裁决 2），再按规范的两个参数序列化；
    `ensure_ascii=False` 只影响文本的字节表示，**不**影响摘要的确定性
    （同一输入永远得到同一文本）。
    """
    return json.dumps(
        _jsonable(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def hash_payload(payload: Mapping[str, Any]) -> str:
    """`sha256(canonical_payload(payload))`（`docs/02` §33）。"""
    canonical = canonical_payload(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def encode_response(response: Mapping[str, Any]) -> str:
    """响应快照 → JSON 文本（`docs/02` §64 的 `response ↓ JSON ↓ IdempotencyRecord`）。

    与 `canonical_payload` 同口径（排序 + 紧凑分隔符），使**同一响应**永远得到
    同一文本 —— 重放返回的内容因此逐字节稳定。
    """
    return canonical_payload(response)


def decode_response(response_json: str) -> dict[str, Any]:
    """JSON 文本 → 响应快照（`docs/02` §64 的重放路径）。

    Raises:
        InternalError: 存储里的文本不是合法 JSON，或不是 JSON 对象
            （`STRUCTAI-7000` 兜底 —— 属数据损坏，**不**静默当作空响应；
            见 `docs/07` §14.4：不允许「带病继续」）。
    """
    try:
        parsed: Any = json.loads(response_json)
    except json.JSONDecodeError as error:
        raise InternalError(
            "stored idempotency response is not valid JSON",
            details={"stage": IDEMPOTENCY_STAGE, "reason": "corrupt_response"},
            cause=error,
        ) from error
    if not isinstance(parsed, dict):
        raise InternalError(
            "stored idempotency response is not a JSON object",
            details={"stage": IDEMPOTENCY_STAGE, "reason": "corrupt_response"},
        )
    return {str(key): value for key, value in parsed.items()}


def _field_of(request: Mapping[str, Any] | object, name: str) -> Any:
    """取 §33 载荷字段（`Mapping` 优先，其次同名属性）。

    Raises:
        TypeError: 字段缺失（见 `hash_request` 的 `Raises`）。
    """
    if isinstance(request, Mapping):
        if name not in request:
            raise TypeError(f"idempotency request is missing field: {name}")
        return request[name]
    if not hasattr(request, name):
        raise TypeError(f"idempotency request is missing field: {name}")
    return getattr(request, name)


def _jsonable(value: Any) -> Any:
    """把值确定性地转成 `json.dumps` 可序列化的形式（见模块裁决 2）。

    转换规则（**只**做类型转换，不改变任何取值）：

    - `Mapping` → `{str(key): _jsonable(value)}`（键统一成字符串，避免 int / str 键
      在 `sort_keys` 下产生歧义）；
    - dataclass 实例 → `{字段名: _jsonable(值)}`（如 P14 的 `ExecutionContext`，
      其 `identity` / `software` / `project` 同样是 dataclass，递归处理）；
    - `Enum` → `value`（如 `RiskLevel` / `ExecutionMode` 等 `StrEnum`）；
    - `UUID` → `str(value)`；`datetime` / `date` → `isoformat()`；
    - `set` / `frozenset` → 按规范化后的字符串**排序**的列表（集合无序，
      不排序会让同一请求产生不同摘要）；
    - `tuple` / `list` → 列表（顺序有意义，**不**排序）；
    - `None` / `bool` / `int` / `float` / `str` → 原样。

    Raises:
        TypeError: 出现无法确定性序列化的类型（如自定义对象）。
            **不**回落 `str(value)`：`repr` 里可能带内存地址或凭据形态的内容，
            既不确定（同一请求两次摘要不同）也可能泄漏信息
            （`docs/07` §14.3：绝不记录 secret）。
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return _jsonable(value.value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, set | frozenset):
        return sorted(json.dumps(_jsonable(item), sort_keys=True) for item in value)
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    raise TypeError(f"idempotency payload contains a non-canonical type: {type(value).__name__}")
