"""Observability · Audit（`docs/02` §7–§9 / §39 / §44 / §65；`docs/07` §14.3）。

权威来源
--------
- `docs/02` §7.1（AuditRecord）—— 审计字段清单；§44 / §65 同口径。
- `docs/02` §8（Audit Hash Chain）—— `entry_hash = SHA256(previous_hash + canonical_payload)`。
- `docs/02` §8.1（Canonical JSON）—— `json.dumps(value, sort_keys=True, separators=(",", ":"),
  ensure_ascii=False)`，**逐字照抄**。
- `docs/02` §8.2（Hash）—— `sha256(((previous_hash or "") + canonical_json(payload))` 的十六进制，
  **逐字照抄**。
- `docs/02` §8.3（Audit Service）—— `record(ctx, action, resource_type, resource_id, result,
  metadata=None)` 与**必须记录**的 16 个动作名。
- `docs/02` §9（Audit 安全规则）—— 禁止写入 `password` / `API key` / `access token` /
  `refresh token` / `private key` / `secret` / `credential`；允许 `secret_reference` /
  `credential_id` / `authentication_method`。
- `docs/02` §44 / §65 —— append-only（普通用户不得删除）、用于**检测篡改**。
- `docs/02` §35（Transaction Boundary）—— 审计写入与业务写**同一** `UnitOfWork`。
- `docs/07` §14.3 —— 绝不记录 secret。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **哈希链的载荷只由 `audit_records` **实际存在**的列构成**：`docs/02` §7.1 还有
   `request_id` / `trace_id` / `task_id` / `metadata_json`，但它们**不在**
   `docs/07` §4.3 的 24 张表内，本批**不得改表**。故 `audit_payload` 只用
   `action` / `resource` / `result` / `tenant_id` / `user_id` / `previous_hash`
   —— 链的可验证性因此与「库里有什么」严格一致（**不**把不落库的字段混进哈希，
   否则重启后无法复算）。
2. **`metadata` 只做「敏感键丢弃」而不入哈希**：`docs/02` §9 要求审计**绝不**写入
   secret，而 §7.1 的 `metadata_json` 列不存在。故 `metadata` 经
   `sanitize_mapping` 清洗后**不**落库、**不**入哈希 —— 既满足「不记录 secret」，
   也不让哈希依赖一个不存在的列。**不**静默丢整个 `metadata`：
   敏感键被丢弃，其余键由调用方经 `resource` / `action` 表达。
3. **`resource` 的规范化只有一处**：`resource = f"{resource_type}:{resource_id}"`
   （有 id 时）、否则 `resource_type`、否则 `None`。写入与校验**共用**同一个
   `normalize_resource`，否则链无法复算。
4. **链按租户分段**：`audit_records.tenant_id` 可为 `NULL`（系统动作），
   而 §8 的链是**单链**语义。本实现以 `tenant_id` 分段（同一租户一条链），
   并把 `tenant_id=None` 视为**独立的系统链** —— 理由：跨租户单链会让
   「读某租户的链」泄漏别的租户的写入时序（`docs/02` §48 的不泄露口径）。
5. **追加期间的串行化可选**：注入了 `lock`（任意提供异步 `hold(key, ...)`
   上下文管理器的对象，实现 = `app/infrastructure/locks/in_memory.InMemoryLock`）时，
   `record` 在「读 `previous_hash` → 计算 → 追加」这一段持有 `"audit-chain"` 锁，
   避免两个并发写入算出同一个 `previous_hash`（§8 的链因此**结构性**成立）。
   未注入时行为不变（单线程 / 测试场景）。
6. **`verify_chain` 同时校验两件事**：每条记录的 `entry_hash` 是否等于用其**自身**
   字段复算的结果（内容篡改），以及 `previous_hash` 是否等于上一条的 `entry_hash`
   （链断裂 / 插入 / 删除）。`first_broken_id` 指向**第一处**不成立的记录。
7. **`AuditService` 不是 Domain 契约本身**：Domain 侧只声明收窄契约
   `AuditRecorder`（`app/domain/protocols.py`），本类**结构上**满足它 ——
   于是 `app/application/**` 不必依赖 `app.observability`（`docs/07` §2.2）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，
**不**依赖 `app.application` / `app.interfaces`（`record_context` 只经 `getattr`
读取上下文），也**不**出现任何厂商专属内容。事务边界归调用方的 `UnitOfWork`
（`docs/02` §16）—— 本模块**从不** `commit` / `rollback`。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from app.domain.enums import AuditResult
from app.domain.errors import InternalError
from app.domain.protocols import AuditEntry, AuditEntryDraft, AuditStore

__all__ = [
    "AUDIT_ACTIONS",
    "AUDIT_CHAIN_LOCK_KEY",
    "AUDIT_HASH_ALGORITHM",
    "AUDIT_STAGE",
    "AuditService",
    "ChainVerification",
    "audit_payload",
    "canonical_json",
    "compute_entry_hash",
    "normalize_resource",
]

AUDIT_STAGE: Final[str] = "audit"
"""错误 `details.stage` 的固定取值。"""

AUDIT_HASH_ALGORITHM: Final[str] = "sha256"
"""哈希算法（`docs/02` §8.2 原文 `hashlib.sha256`）。"""

ENTRY_HASH_LENGTH: Final[int] = 64
"""`entry_hash` 的十六进制长度（SHA-256 = 32 字节 → 64 字符）。"""

AUDIT_CHAIN_LOCK_KEY: Final[str] = "audit-chain"
"""哈希链串行化用的锁键（见模块裁决 5）。"""

AUDIT_ACTIONS: Final[tuple[str, ...]] = (
    "LOGIN",
    "LOGOUT",
    "DOCUMENT.NEW",
    "DOCUMENT.OPEN",
    "DOCUMENT.SAVE",
    "DOCUMENT.CLOSE",
    "MODEL.CREATE",
    "MODEL.UPDATE",
    "MODEL.DELETE",
    "ANALYSIS.RUN",
    "DESIGN.RUN",
    "TASK.CANCEL",
    "ADAPTER.CONNECT",
    "ADAPTER.DISCONNECT",
    "PERMISSION.DENIED",
    "CONFIRMATION.REQUIRED",
)
"""`docs/02` §8.3 逐字照抄的 16 个**必须记录**的动作名。"""


def canonical_json(value: Mapping[str, Any]) -> str:
    """规范化 JSON 文本（`docs/02` §8.1，逐字照抄）。

    Args:
        value: 待规范化的映射。

    Returns:
        键排序 + 紧凑分隔符 + 非 ASCII 原样的 JSON 文本。
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def compute_entry_hash(previous_hash: str | None, payload: Mapping[str, Any]) -> str:
    """计算一条审计记录的 `entry_hash`（`docs/02` §8.2，逐字照抄）。

    Args:
        previous_hash: 上一条的 `entry_hash`；链首为 `None`。
        payload: 本条记录的规范化载荷（见 `audit_payload`）。

    Returns:
        `sha256(((previous_hash or "") + canonical_json(payload)).encode("utf-8"))` 的十六进制摘要。
    """
    raw = ((previous_hash or "") + canonical_json(payload)).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def normalize_resource(resource_type: str | None, resource_id: str | None) -> str | None:
    """把资源标识规范成单列文本（见模块裁决 3）。

    Returns:
        有 id → `"{resource_type}:{resource_id}"`；只有类型 → `resource_type`；
        两者都无 → `None`。
    """
    if resource_type and resource_id:
        return f"{resource_type}:{resource_id}"
    return resource_type or None


def audit_payload(
    *,
    action: str,
    resource: str | None,
    result: str,
    tenant_id: str | None,
    user_id: str | None,
    previous_hash: str | None,
) -> dict[str, Any]:
    """审计记录的规范化载荷（`docs/02` §8 / §8.1；见模块裁决 1）。

    ⚠️ 字段集合**恰好**是 `audit_records` 实际存在的列：任何多出的键都会让
    `verify_chain` 在重启后无法复算。
    """
    return {
        "action": action,
        "resource": resource,
        "result": result,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "previous_hash": previous_hash,
    }


@dataclass(frozen=True, slots=True)
class ChainVerification:
    """一次哈希链校验的结果（`docs/02` §44 的「检测篡改」）。

    Attributes:
        total: 参与校验的记录条数。
        valid: 链是否完整（内容与前后关系都成立）。
        first_broken_id: **第一处**不成立的记录 id；`valid` 为 `True` 时是 `None`。
        reason: 不成立的原因词（`hash_mismatch` / `chain_break`），合法时为 `""`。
    """

    total: int
    valid: bool
    first_broken_id: str | None = None
    reason: str = ""


class AuditService:
    """审计写入与完整性校验（`docs/02` §8.3 / §44 / §65）。

    ⚠️ 持久化经 Domain 契约 `AuditStore` 注入：本模块**不**依赖 `app.infrastructure`
    （`docs/07` §14.1）。事务边界归调用方的 `UnitOfWork`（`docs/02` §16）——
    本类**从不** `commit` / `rollback`，因此「业务写失败 → 审计一起回滚」是
    **结构性**的（`docs/02` §35）。

    🔴 append-only：本类**不**提供任何修改 / 删除审计的方法（`docs/02` §65）。
    """

    def __init__(self, store: AuditStore, *, lock: object | None = None) -> None:
        """绑定审计存储与可选的链锁。

        Args:
            store: 审计记录的持久化入口（`docs/02` §7 / §43）。
            lock: 可选的链锁（见模块裁决 5）；需提供异步 `hold(key, ...)`
                上下文管理器。缺省 `None` 表示不串行化。
        """
        self._store = store
        self._lock = lock
        self._written = 0

    # ===== 只读视图 =====

    @property
    def store(self) -> AuditStore:
        """被绑定的审计存储（只读用途）。"""
        return self._store

    def records_written(self) -> int:
        """本实例写入的审计条数（诊断 / 指标用）。"""
        return self._written

    # ===== `docs/02` §8.3：写入 =====

    async def record(
        self,
        *,
        action: str,
        result: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> AuditEntry:
        """写入一条审计记录（`docs/02` §8.3 ＋ §8 的哈希链）。

        Args:
            action: 动作名（`docs/02` §8.3 的 16 个之一，或调用方自定的业务动作名）。
            result: 结果（`AuditResult` 取值：`SUCCESS` / `FAILURE` / `DENIED`）。
            tenant_id: 租户标识；系统动作为 `None`（`docs/02` §7.1 允许为空）。
            user_id: 用户标识；系统动作为 `None`。
            resource_type: 资源类型（如 `engineering_model_build`）。
            resource_id: 资源标识。
            metadata: 可选附加信息；**只**用于敏感键检查（见模块裁决 2）。

        Returns:
            已落库的 `AuditEntry`（含 `previous_hash` / `entry_hash`）。

        Raises:
            InternalError: `STRUCTAI-7000` —— `result` 不在 `AuditResult` 内
                （`reason = "invalid_result"`）。**不**静默写入一个非法结果。
        """
        if str(result) not in {str(item) for item in AuditResult}:
            raise InternalError(
                "Audit result is not a known AuditResult value",
                details={"stage": AUDIT_STAGE, "reason": "invalid_result"},
            )
        # 见模块裁决 2：metadata 只做敏感键清洗，不落库、不入哈希。
        _ = _sanitized(metadata)
        resource = normalize_resource(resource_type, resource_id)
        if self._lock is None:
            return await self._append(
                action=action,
                result=str(result),
                resource=resource,
                tenant_id=tenant_id,
                user_id=user_id,
            )
        async with self._lock.hold(AUDIT_CHAIN_LOCK_KEY):  # type: ignore[attr-defined]
            return await self._append(
                action=action,
                result=str(result),
                resource=resource,
                tenant_id=tenant_id,
                user_id=user_id,
            )

    async def record_context(
        self,
        context: object,
        *,
        action: str,
        result: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> AuditEntry:
        """按执行上下文写入审计（Domain `AuditRecorder` 契约的实现）。

        ⚠️ `context` 声明为 `object` 并只经 `getattr` 读取 `identity.tenant_id` /
        `identity.user_id` —— 本模块因此**不**依赖 `app.application`（`docs/07` §2.2），
        与 `app/application/resource/resolver.py` 同一手法。
        """
        identity = getattr(context, "identity", None)
        tenant_id = _as_str(getattr(identity, "tenant_id", None))
        user_id = _as_str(getattr(identity, "user_id", None))
        return await self.record(
            action=action,
            result=result,
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
        )

    # ===== `docs/02` §44：校验 =====

    async def verify_chain(
        self,
        *,
        tenant_id: str | None = None,
        limit: int = 1000,
    ) -> ChainVerification:
        """复算哈希链（`docs/02` §44「用于检测篡改」；见模块裁决 6）。

        Args:
            tenant_id: 要校验的租户链（见模块裁决 4）；`None` 表示系统链。
            limit: 最多校验的条数（`docs/07` §14.4 的有界读）。

        Returns:
            `ChainVerification`；任何内容篡改或链断裂都会让 `valid` 为 `False`
            并指出 `first_broken_id`。
        """
        entries = list(await self._store.chain(tenant_id=tenant_id, limit=limit))
        previous: str | None = None
        for index, entry in enumerate(entries):
            expected = compute_entry_hash(
                entry.previous_hash,
                audit_payload(
                    action=entry.action,
                    resource=entry.resource,
                    result=entry.result,
                    tenant_id=entry.tenant_id,
                    user_id=entry.user_id,
                    previous_hash=entry.previous_hash,
                ),
            )
            if expected != entry.entry_hash:
                return ChainVerification(
                    total=len(entries),
                    valid=False,
                    first_broken_id=entry.id,
                    reason="hash_mismatch",
                )
            if index > 0 and entry.previous_hash != previous:
                return ChainVerification(
                    total=len(entries),
                    valid=False,
                    first_broken_id=entry.id,
                    reason="chain_break",
                )
            previous = entry.entry_hash
        return ChainVerification(total=len(entries), valid=True)

    # ===== 内部 =====

    async def _append(
        self,
        *,
        action: str,
        result: str,
        resource: str | None,
        tenant_id: str | None,
        user_id: str | None,
    ) -> AuditEntry:
        """读上一条哈希 → 计算 → 追加（**唯一**的链推进点）。"""
        previous_hash = await self._store.last_hash(tenant_id=tenant_id)
        payload = audit_payload(
            action=action,
            resource=resource,
            result=result,
            tenant_id=tenant_id,
            user_id=user_id,
            previous_hash=previous_hash,
        )
        entry_hash = compute_entry_hash(previous_hash, payload)
        entry = await self._store.append(
            AuditEntryDraft(
                tenant_id=tenant_id,
                user_id=user_id,
                action=action,
                resource=resource,
                result=result,
                previous_hash=previous_hash,
                entry_hash=entry_hash,
            )
        )
        self._written += 1
        return entry


def _sanitized(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """对 `metadata` 做敏感键清洗（`docs/02` §9；见模块裁决 2）。

    清洗结果**不**落库、**不**入哈希；本函数存在的意义是：**读一遍** `metadata`，
    使「有没有 secret 混进来」成为一次显式的、可单测的判定，而不是靠调用方自觉。
    """
    if not metadata:
        return {}
    from app.infrastructure.secrets.base import sanitize_mapping

    return sanitize_mapping(metadata)


def _as_str(value: Any) -> str | None:
    """任意标识 → `str | None`（`None` 原样返回）。"""
    return None if value is None else str(value)
