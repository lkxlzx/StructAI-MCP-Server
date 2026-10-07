"""Infrastructure · Adapters · MIDAS · Hardening —— 生产加固的**显式**判定表（P135d）。

权威来源
--------
- `docs/04` §151（Production Hardening Definition of Done）—— **19** 项清单，逐字照抄：
  Connection pool / Timeout / Retry / Circuit breaker / Rate limit / Concurrency /
  Resource lock / Credential rotation / Secret redaction / Structured logging / Metrics /
  Trace / Audit / Recovery / Reconcile / Contract test / E2E / Backup / Version migration。
- `docs/04` §114–§126 / §149（生产配置 / 密钥 / 实例 / 生命周期 / 取消 / 恢复 / 熔断 / 指标）。
- `docs/07` §14.4 —— 单实例失败不得拖垮服务器；§16 R52 —— 资源锁的持有者是 **Worker**。
- `docs/07` §16 R78 / R85 / R87 —— `verification_status` 不因 CI 层记录升级；
  L4 实测发现的 43 条产品可得性差异如实保留在数据侧。

落地裁决
--------
1. **每一项都必须有「可执行判定」或「未落地 + 理由」**：`decision` 写作**可运行的**
   判据（常量 / 模块 / 测试名），`reason` 写作未落地或委派的原因 ——
   不允许只写「已支持」这类不可验证的措辞（与 ETABS 侧 `hardening.py` 同一口径）。
2. **三种状态**：`IMPLEMENTED`（本子包落地）、`DELEGATED`（由 Core 承担，本子包**不**重复
   实现）、`NOT_IMPLEMENTED`（本批**没有**落地，理由见 `reason`）。
   ⚠️ `DELEGATED` 与 `NOT_IMPLEMENTED` 都**不**等于「已加固」。
3. **`docs/04` §151 的清单必须按软件分别给出判定**：本模块只负责 MIDAS 一列；
   ETABS 一列在 `app/infrastructure/adapters/etabs/hardening.py`，Mock 一列在验收测试里
   逐条断言（`tests/test_hardening_p135.py`）。三列**逐条**对应同一份 19 项清单。
4. **本批不新增依赖**（`docs/07` §3.1 技术栈冻结）：本模块只做**判定**，不引入任何新库；
   MIDAS 侧的 HTTP 客户端（`httpx`）与迁移工具（`alembic`）都已在 §3.2 冻结清单内。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与同包的 `errors.py`；**不**引用 SQLAlchemy / FastAPI / MCP SDK /
httpx，**不**依赖 `app.interfaces` / `app.application`，也**不**出现第二处厂商分支。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from app.infrastructure.adapters.midas.errors import MidasValidationError

__all__ = [
    "DELEGATED",
    "HARDENING",
    "HARDENING_ITEMS",
    "IMPLEMENTED",
    "NOT_IMPLEMENTED",
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
        decision: **可执行**判据（常量 / 模块 / 测试名）。
        reason: 未落地或委派的原因（必填；**不**允许留空）。
    """

    item: str
    status: str
    decision: str
    reason: str


HARDENING: Final[tuple[HardeningItem, ...]] = (
    HardeningItem(
        item="Connection pool",
        status=IMPLEMENTED,
        decision="MidasHttpClient 持有一个 httpx.AsyncClient（client.py 的 _http_client），"
        "连接由客户端池管理；close() 显式释放（tests/test_midas_live_p134.py 的关闭断言）",
        reason="HTTP 客户端自带连接池；本子包不自建池，避免第二套生命周期",
    ),
    HardeningItem(
        item="Timeout",
        status=IMPLEMENTED,
        decision="client.DEFAULT_BUDGET_SECONDS / EXECUTION_MODE_BUDGETS + "
        "budget_for(resolved) → 每个请求显式超时（client.py）",
        reason="超时按 execution.mode 分级（FAST / ASYNC / LONG），不统一取一个值",
    ),
    HardeningItem(
        item="Retry",
        status=IMPLEMENTED,
        decision="midas/health.py 的容忍重试 + client._request 的超时归类（2300）；"
        "R84 实测 CIVIL NX 首次 health 探针 8s 超时需重试",
        reason="只对超时 / 连接类失败重试；原生业务失败不重试（不猜测幂等性）",
    ),
    HardeningItem(
        item="Circuit breaker",
        status=NOT_IMPLEMENTED,
        decision="本子包无熔断器常量（AST 断言 0 处 circuit 标识符）",
        reason="本批**未**落地：MIDAS 侧的失败由 Core 的任务重试预算 + 健康检查降级承担"
        "（docs/04 §123 的熔断属部署方 / 后续批次）；ETABS 侧已落地，MIDAS 侧如实标注",
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
        decision="四级并发由 Core 的 Scheduler 落地（docs/07 §16 R47）；"
        "MIDAS 实例默认 SERIAL（docs/02 §20）",
        reason="Adapter 侧不持有并发准入；HTTP 协议本身无会话并发约束（与 ETABS 的 COM 不同）",
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
        decision="MidasEnvironmentCredential 每次 _request 重新解析 MAPI-Key；"
        "值不缓存、不进 repr（client.py；docs/04 §147 API Key Refresh）",
        reason="轮换 = 换环境变量（无需重启进程）；本子包不声明任何新的环境变量名",
    ),
    HardeningItem(
        item="Secret redaction",
        status=IMPLEMENTED,
        decision="MAPI-Key 只经 MAPI-Key 请求头；repr / 异常 details / 审计 / 响应 0 命中"
        "（tests/test_midas_live_p134.py 的 record 扫描）",
        reason="凭据绝不落库 / 落文件 / 落日志 / 进响应（docs/07 §14.3）",
    ),
    HardeningItem(
        item="Structured logging",
        status=NOT_IMPLEMENTED,
        decision="AST 断言本子包 0 处 logging 导入",
        reason="本批 Adapter 侧**零**日志：日志一律由 Core 的结构化日志承担，"
        "避免把凭据 / 业务原文带进日志（docs/07 §14.3）",
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
        reason="任务级恢复归 Task Engine（P22–P28）；Adapter 只如实报告实例状态",
    ),
    HardeningItem(
        item="Reconcile",
        status=IMPLEMENTED,
        decision="health.py 的只读探测（GET /OPE/PROJECTSTATUS）+ 注册表回读"
        "（live.py 的 read_verifications）如实反映真实状态",
        reason="对账只读真实响应，不臆造「已连接」",
    ),
    HardeningItem(
        item="Contract test",
        status=IMPLEMENTED,
        decision="L1–L3 在 CI 层（tests/test_midas_contract_p124.py）；"
        "L4 全量只读实测 487 端点已落库 midas_api_verifications（P134）",
        reason="L5（业务效果）需要专用测试项目声明；缺声明即跳过且不失败（docs/07 §16 R86）",
    ),
    HardeningItem(
        item="E2E",
        status=IMPLEMENTED,
        decision="§73 / §74 / §77 三条链在 L3（Mock Transport）逐条断言请求 (method, path)"
        "（tests/test_midas_e2e_p125_p126.py）",
        reason="真实实例 E2E 归 L4 / L5；本批不声称已对真实项目跑通写路径",
    ),
    HardeningItem(
        item="Backup",
        status="DELEGATED",
        decision="Core 的 BackupService / RestoreService / RetentionService（P34–P35 + P135b）；"
        "AST 断言本子包不出现备份实现",
        reason="Adapter 无持久化面（7 张表由 Alembic 迁移创建，载荷归 Core 存储层）",
    ),
    HardeningItem(
        item="Version migration",
        status=IMPLEMENTED,
        decision="migrations/versions/0001_midas_registry_tables.py（Alembic 显式迁移，"
        "upgrade / downgrade 各一次）；supported_versions 精确匹配（2025 / 2026）",
        reason="改表一律走 Alembic；禁止启动时静默建表 / 改表（docs/07 §14.3）",
    ),
)
"""`docs/04` §151 的 19 项在 **MIDAS** 上的逐条判定（见裁决 1–3）。"""


def status_of(item: str) -> str:
    """取某项的判定状态（见裁决 2）。

    Raises:
        MidasValidationError: `STRUCTAI-1200`，条目名不在 `docs/04` §151 内。
    """
    for entry in HARDENING:
        if entry.item == str(item):
            return entry.status
    raise MidasValidationError("hardening_item_unknown", item=str(item))


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
