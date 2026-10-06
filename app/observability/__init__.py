"""Observability（`docs/07` §3.3 冻结结构；`docs/02` §61–§66）。

| 文件 | 内容 | 规范 |
| --- | --- | --- |
| `audit.py` | `AuditService`：审计写入 + **Hash Chain** | `docs/02` §7–§9 / §44 |
| `tracing.py` | `TraceService`：Span 的开始 / 结束与查询 | `docs/02` §10–§12 / §53 / §63 |
| `metrics.py` | `MetricsService`：Prometheus 寄存器 | `docs/02` §13–§15 |
| `health.py` | `HealthService` / `HealthRegistry` | `docs/02` §16 / §41 |

本包是 `app` 根下的**旁路支撑层**（`docs/07` §3.3）。它只依赖标准库与 `app.domain`：
- `docs/07` §2.2 的冻结依赖方向是 `Interface → Application → Domain`，
  故 `app/application/**` **不**直接引用本包；执行主干改为依赖
  `app.domain.protocols` 的收窄契约 `AuditRecorder` / `TraceRecorder` / `MetricsRecorder`
  / `HealthChecker`，本包的四个服务**结构上**满足它们
  （与 `docs/07` §16 R38 的 `RuntimeCapabilitySource` 同一手法）。
- 因此本包**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，也**不**出现任何厂商专属内容。
  真实数据库 / Registry / Task Engine 的检查器由 `app/container.py`（Infrastructure 侧）
  构造后注入 `HealthRegistry`。

🔴 绝不记录 secret（`docs/07` §14.3）：审计 / Trace 属性 / 指标标签三处都做了
敏感键清洗（`app/infrastructure/secrets/base.py` 的 `sanitize_mapping` /
`looks_sensitive`），并在各自模块的裁决里写明「清洗是被测试的显式步骤」。
"""

from __future__ import annotations

from app.observability.audit import (
    AUDIT_ACTIONS,
    AUDIT_CHAIN_LOCK_KEY,
    AUDIT_HASH_ALGORITHM,
    AUDIT_STAGE,
    AuditService,
    ChainVerification,
    audit_payload,
    canonical_json,
    compute_entry_hash,
    normalize_resource,
)
from app.observability.health import (
    HEALTH_CHECKS,
    HEALTH_PATH,
    HEALTH_STAGE,
    LIVENESS_PATH,
    NOT_READY,
    READINESS_CHECKS,
    READINESS_PATH,
    READY,
    STATUS_KEY,
    CallableHealthChecker,
    HealthRegistry,
    HealthService,
    is_ready_status,
)
from app.observability.metrics import (
    ALLOWED_LABELS,
    HIGH_CARDINALITY_LABELS,
    METRICS_STAGE,
    PROMETHEUS_CONTENT_TYPE,
    STANDARD_METRICS,
    MetricSample,
    MetricsService,
)
from app.observability.tracing import (
    DEFAULT_SPAN_KIND,
    STANDARD_SPAN_KINDS,
    TRACE_STAGE,
    InMemoryTraceStore,
    TraceService,
    is_standard_kind,
)

__all__ = [
    "ALLOWED_LABELS",
    "AUDIT_ACTIONS",
    "AUDIT_CHAIN_LOCK_KEY",
    "AUDIT_HASH_ALGORITHM",
    "AUDIT_STAGE",
    "DEFAULT_SPAN_KIND",
    "HEALTH_CHECKS",
    "HEALTH_PATH",
    "HEALTH_STAGE",
    "HIGH_CARDINALITY_LABELS",
    "LIVENESS_PATH",
    "METRICS_STAGE",
    "NOT_READY",
    "PROMETHEUS_CONTENT_TYPE",
    "READINESS_CHECKS",
    "READINESS_PATH",
    "READY",
    "STANDARD_METRICS",
    "STANDARD_SPAN_KINDS",
    "STATUS_KEY",
    "TRACE_STAGE",
    "AuditService",
    "CallableHealthChecker",
    "ChainVerification",
    "HealthRegistry",
    "HealthService",
    "InMemoryTraceStore",
    "MetricSample",
    "MetricsService",
    "TraceService",
    "audit_payload",
    "canonical_json",
    "compute_entry_hash",
    "is_ready_status",
    "is_standard_kind",
    "normalize_resource",
]
