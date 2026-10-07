"""Infrastructure · Adapters · CSI ETABS · Hardening —— 生产加固的**显式**判定表（P133）。

权威来源
--------
- `docs/04` §151（Production Hardening Definition of Done）—— **19** 项清单，逐字照抄：
  Connection pool / Timeout / Retry / Circuit breaker / Rate limit / Concurrency /
  Resource lock / Credential rotation / Secret redaction / Structured logging / Metrics /
  Trace / Audit / Recovery / Reconcile / Contract test / E2E / Backup / Version migration。
- `docs/07` §14.4 —— 单实例失败不得拖垮服务器；`docs/02` §91 / `docs/07` §16 R52 ——
  资源锁的持有者是 **Worker**（Core），不是 Adapter。
- `docs/07` §16 R78 —— `verification_status` **不**因 CI 层记录升级为 `VERIFIED`。

落地裁决
--------
1. **每一项都必须有「可执行判定」或「未落地 + 理由」**：`decision` 写作**可运行的**
   判据（测试名 / 常量 / AST 断言），`reason` 写作未落地或委派的原因 ——
   不允许只写「已支持」这类不可验证的措辞。
2. **三种状态**：`IMPLEMENTED`（本子包落地）、`DELEGATED`（由 Core 承担，本子包**不**重复
   实现）、`NOT_IMPLEMENTED`（本批**没有**落地，理由见 `reason`）。
   ⚠️ `DELEGATED` 与 `NOT_IMPLEMENTED` 都**不**等于「已加固」——
   验收测试逐项断言状态取值，**不**允许把未落地写成已落地。
3. **`COM_SESSION_CONCURRENCY_SAFE = False`**：COM 会话**不**声明并发安全，
   因此部署方应把该软件实例的并发策略取 `SERIAL`（Core 的
   `InstanceConcurrencyPolicySource` 缺省值即 `SERIAL`，`docs/02` §20）。

分层红线：只依赖标准库与同包的 `errors.py`；**不**引用 SQLAlchemy / FastAPI / MCP SDK /
httpx，**不**依赖 `app.interfaces` / `app.application`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from app.infrastructure.adapters.etabs.errors import EtabsValidationError

__all__ = [
    "DELEGATED",
    "HARDENING",
    "HARDENING_ITEMS",
    "IMPLEMENTED",
    "NOT_IMPLEMENTED",
    "COM_SESSION_CONCURRENCY_SAFE",
    "HardeningItem",
    "as_dicts",
    "implemented",
    "not_implemented",
    "status_of",
]

IMPLEMENTED: Final[str] = "IMPLEMENTED"
DELEGATED: Final[str] = "DELEGATED"
NOT_IMPLEMENTED: Final[str] = "NOT_IMPLEMENTED"
"""三项状态取值（见裁决 2）。"""

COM_SESSION_CONCURRENCY_SAFE: Final[bool] = False
"""COM 会话是否声明并发安全（见裁决 3；实例策略应取 `SERIAL`）。"""

HARDENING_ITEMS: Final[tuple[str, ...]] = (
    "Connection pool",
    "Timeout",
    "Retry",
    "Circuit breaker",
    "Rate limit",
    "Concurrency",
    "Resource lock",
    "Credential rotation",
    "Secret redaction",
    "Structured logging",
    "Metrics",
    "Trace",
    "Audit",
    "Recovery",
    "Reconcile",
    "Contract test",
    "E2E",
    "Backup",
    "Version migration",
)
"""`docs/04` §151 的 **19** 项（逐字照抄；顺序不变）。"""


@dataclass(frozen=True, slots=True)
class HardeningItem:
    """一项加固判定（见裁决 1 / 2）。

    Attributes:
        item: `docs/04` §151 的条目名（逐字）。
        status: `IMPLEMENTED` / `DELEGATED` / `NOT_IMPLEMENTED`。
        decision: **可执行**判据（测试名 / 常量 / AST 断言）。
        reason: 未落地或委派的原因（必填；**不**允许留空）。
    """

    item: str
    status: str
    decision: str
    reason: str


HARDENING: Final[tuple[HardeningItem, ...]] = (
    HardeningItem(
        item="Connection pool",
        status=DELEGATED,
        decision="ComSession.attach/detach 幂等 + 会话复用（test_etabs_p127_p133.py 的 "
        "test_p127_session_attach_is_idempotent_and_detach_is_idempotent）",
        reason="COM 无连接池语义；会话由注入的 ComDispatch 承载，池化属部署方实现",
    ),
    HardeningItem(
        item="Timeout",
        status=IMPLEMENTED,
        decision="client.DEFAULT_BUDGET_SECONDS + asyncio.timeout → EtabsTimeoutError（2300）"
        "（test_p133_first_timeout_is_retried_then_the_circuit_breaker_opens）",
        reason="预算显式、可按实例覆盖（EtabsAdapter(budget_seconds=...)）",
    ),
    HardeningItem(
        item="Retry",
        status=IMPLEMENTED,
        decision="RetryPolicy.max_attempts（只对超时重试；"
        "test_p133_first_timeout_is_retried_then_the_circuit_breaker_opens）",
        reason="非超时的原生失败不重试（不猜测幂等性）",
    ),
    HardeningItem(
        item="Circuit breaker",
        status=IMPLEMENTED,
        decision="CircuitBreaker(failure_threshold, reset_seconds)；打开后发请求前抛 "
        "EtabsConnectionError(circuit_open)（2000；同一测试的零 transport 断言）",
        reason="阈值 / 复位窗口可按实例注入",
    ),
    HardeningItem(
        item="Rate limit",
        status=DELEGATED,
        decision="Core 第 12 步（Quota / Rate Limit，docs/07 §9）；"
        "AST 断言本子包不出现 quota / rate_limit 实现",
        reason="限流是 Core 的职责（docs/02 §43–§46），Adapter 重复实现会形成第二套判定",
    ),
    HardeningItem(
        item="Concurrency",
        status=DELEGATED,
        decision="COM_SESSION_CONCURRENCY_SAFE = False（实例策略应取 SERIAL）；"
        "四级并发由 Core 的 Scheduler 落地（docs/07 §16 R47）",
        reason="Adapter 侧不持有并发准入；只如实声明会话非并发安全",
    ),
    HardeningItem(
        item="Resource lock",
        status=DELEGATED,
        decision="锁的持有者是 Worker（docs/02 §91 / docs/07 §16 R52）；AST 断言本子包不出现锁实现",
        reason="Adapter 侧加锁会与 Worker 的锁形成第二套判定（重复持锁 / 死锁风险）",
    ),
    HardeningItem(
        item="Credential rotation",
        status=IMPLEMENTED,
        decision="凭据只在 attach 时经 CredentialProvider 解析、值不缓存；"
        "test_p133_credentials_are_re_resolved_on_every_attach_and_never_echoed",
        reason="轮换 = 换环境变量 + 重连；本子包不声明任何新的环境变量名（.env.example 不改）",
    ),
    HardeningItem(
        item="Secret redaction",
        status=IMPLEMENTED,
        decision="ComSession/EtabsComClient 的 repr 不含值；异常 details 只放非敏感字段；"
        "唯一归一化点 base/errors.py 另有键名白名单 + 文本脱敏"
        "（test_p133_credentials_are_re_resolved_on_every_attach_and_never_echoed）",
        reason="凭据绝不落库 / 落文件 / 落日志 / 进响应（docs/07 §14.3）",
    ),
    HardeningItem(
        item="Structured logging",
        status=NOT_IMPLEMENTED,
        decision="AST 断言本子包 0 处 logging 导入",
        reason="本批 Adapter 侧**零**日志：日志一律由 Core 的结构化日志承担，"
        "避免把凭据 / 业务数据带进日志（docs/07 §14.3）",
    ),
    HardeningItem(
        item="Metrics",
        status=DELEGATED,
        decision="Core 第 24 步（Metrics，docs/07 §9）；AST 断言本子包不导入 app.observability",
        reason="指标的唯一写入点是 Core 的 MetricsService（P29–P36）",
    ),
    HardeningItem(
        item="Trace",
        status=DELEGATED,
        decision="Core 第 23 步（Trace，docs/07 §9）；AST 断言本子包不导入 app.observability",
        reason="Span 由 Core 的 TraceService 生成（P29–P36）",
    ),
    HardeningItem(
        item="Audit",
        status=DELEGATED,
        decision="Core 的 AuditService（P29–P36）；AST 断言本子包不写库（0 处 SQLAlchemy 导入）",
        reason="审计与业务写同一 UnitOfWork；Adapter 不持有会话",
    ),
    HardeningItem(
        item="Recovery",
        status=DELEGATED,
        decision="Core 的 RecoveryService + 四入口状态（docs/07 §16 R45）；"
        "AST 断言本子包不出现恢复逻辑",
        reason="任务级恢复归 Task Engine（P22–P28）；Adapter 只如实报告会话状态",
    ),
    HardeningItem(
        item="Reconcile",
        status=IMPLEMENTED,
        decision="重连后重新探测会话状态：ComSession.is_attached() + "
        "EtabsAdapter.health_check() 如实反映真实状态"
        "（test_p133_health_reflects_the_real_session_state）",
        reason="对账只读真实会话态，不臆造「已连接」",
    ),
    HardeningItem(
        item="Contract test",
        status=IMPLEMENTED,
        decision="L1 Static Registry / L2 Schema / L3 Mock Transport 三层在 "
        "tests/test_etabs_p127_p133.py 落地；L4 / L5 **未**执行",
        reason="L4 / L5 需要真实 ETABS 实例与专用凭据（docs/04 §72），本机不存在；"
        "故 verification_status 保持 PARTIAL（docs/07 §16 R78）",
    ),
    HardeningItem(
        item="E2E",
        status=IMPLEMENTED,
        decision="同一 9 Tool 契约 + 同一 Execution Pipeline 在 L3（Mock Transport）跑通 "
        "engineering_analysis / ANALYSIS.STATIC（test_p132_engineering_analysis_runs_end_to_end）",
        reason="L4（真实实例）不可执行；本批不声称已对真实 ETABS 跑通",
    ),
    HardeningItem(
        item="Backup",
        status=DELEGATED,
        decision="Core 的 BackupService / RestoreService / RetentionService（P34–P35）；"
        "AST 断言本子包不出现备份实现",
        reason="Adapter 无持久化面（不建表、不写文件）",
    ),
    HardeningItem(
        item="Version migration",
        status=IMPLEMENTED,
        decision="supported_versions 严格精确匹配（version_not_supported → 1200）"
        "+ ETABS_CATALOGUE_VERSION 标记"
        "（test_p127_manifest_matches_the_traceable_facts）",
        reason="版本迁移 = 新增 catalogue 条目并推进 ETABS_CATALOGUE_VERSION，"
        "不回落「最新版本」（docs/02 §20）",
    ),
)
"""`docs/04` §151 的 19 项逐条判定（见裁决 1 / 2）。"""


def items() -> tuple[str, ...]:
    """加固条目名（= `docs/04` §151 的 19 项，顺序不变）。"""
    return HARDENING_ITEMS


def status_of(item: str) -> str:
    """取某项的判定状态（见裁决 2）。

    Raises:
        EtabsValidationError: `STRUCTAI-1200`，条目名不在 `docs/04` §151 内。
    """
    for entry in HARDENING:
        if entry.item == str(item):
            return entry.status
    raise EtabsValidationError("hardening_item_unknown", item=str(item))


def implemented() -> tuple[str, ...]:
    """判定为 `IMPLEMENTED` 的条目名。"""
    return tuple(entry.item for entry in HARDENING if entry.status == IMPLEMENTED)


def not_implemented() -> tuple[str, ...]:
    """**未**由本子包落地的条目名（`DELEGATED` + `NOT_IMPLEMENTED`）。"""
    return tuple(entry.item for entry in HARDENING if entry.status != IMPLEMENTED)


def as_dicts() -> tuple[dict[str, Any], ...]:
    """整表的结构化视图（**不含**凭据；供报告与验收证据）。"""
    return tuple(
        {
            "item": entry.item,
            "status": entry.status,
            "decision": entry.decision,
            "reason": entry.reason,
        }
        for entry in HARDENING
    )
