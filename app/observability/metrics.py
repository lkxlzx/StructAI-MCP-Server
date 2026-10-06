"""Observability · Metrics（`docs/02` §13 / §14 / §15 / §42 / §45 / §64 / §74；`docs/07` §14.3）。

权威来源
--------
- `docs/02` §13（P62 Metrics）—— `MetricsService` 契约（Prometheus 风格抽象）：
  `counter(name, value=1, labels=None)` / `gauge(name, value, labels=None)` /
  `observe(name, value, labels=None)`，**逐字照抄**。
- `docs/02` §14（标准 Metrics）—— Core Alpha 的标准指标名清单（15 个）。
- `docs/02` §15（Metrics 标签规则）—— **允许**的标签（`tool` / `operation` / `software` /
  `product` / `adapter` / `status`）与**谨慎使用**的高基数标签
  （`tenant_id` / `user_id` / `project_id` / `request_id` / `task_id`）。
- `docs/02` §45（Metrics Endpoint）—— 建议 `GET /metrics`，且**暴露必须由 HTTP 管理层控制**
  （不得直接暴露到不可信公网）；本模块只提供 `render()` 文本与 `content_type`。
- `docs/02` §42 / §64 —— 指标名清单与「Prometheus-compatible exposition」。
- `docs/07` §14.3 —— 绝不记录 secret（标签里也不许）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **高基数标签被**丢弃**而不是报错**（`docs/02` §15）：`tenant_id` / `user_id` /
   `project_id` / `request_id` / `task_id` 一律不作为 label —— 它们是「谨慎使用」项，
   而 Prometheus 的 label 基数爆炸是不可逆的运行事故。丢弃是**静默但可观测**的：
   `dropped_labels()` 记录被丢的键名（**不**记值），因此「指标口径被改动」这件事
   可以被断言，而不是靠猜。
2. **敏感键一律丢弃**（`docs/07` §14.3）：即使键名不在高基数清单里，
   只要 `looks_sensitive` 判定为敏感（`token` / `api_key` / `password` …）也丢弃并计入
   `dropped_labels()`。
3. **`counter` / `gauge` / `observe` **永不抛出**（`docs/07` §14.4）：
   指标写入失败不得影响业务结果。非法数值（`NaN` / `inf`）被丢弃并计数，
   **不**写进寄存器 —— 一个 `NaN` 会让整份 exposition 不可用。
4. **`render()` 的输出是确定性文本**：样本行按「指标名 → 标签序列化文本」排序，
   标签键排序，每行以换行结束 —— 同一状态两次渲染逐字节一致（便于验收与 diff）。
   本批**不**输出 `# HELP` / `# TYPE` 行（`docs/02` §42 只要求 compatible exposition），
   保持实现最小；标签化样本用 `name{...} value` 形式。
5. **`MetricsService` 结构上满足 Domain 收窄契约 `MetricsRecorder`**
   （`app/domain/protocols.py`），于是 `app/application/**` 不必依赖 `app.observability`
   （`docs/07` §2.2）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，
**不**依赖 `app.application` / `app.interfaces`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

__all__ = [
    "ALLOWED_LABELS",
    "HIGH_CARDINALITY_LABELS",
    "METRICS_STAGE",
    "PROMETHEUS_CONTENT_TYPE",
    "STANDARD_METRICS",
    "MetricSample",
    "MetricsService",
]

METRICS_STAGE: Final[str] = "metrics"
"""错误 / 诊断 `stage` 的固定取值。"""

PROMETHEUS_CONTENT_TYPE: Final[str] = "text/plain; version=0.0.4; charset=utf-8"
"""Prometheus 文本 exposition 的 Content-Type（`docs/02` §42）。"""

STANDARD_METRICS: Final[tuple[str, ...]] = (
    "structai_requests_total",
    "structai_request_duration_seconds",
    "structai_task_total",
    "structai_task_duration_seconds",
    "structai_task_failed_total",
    "structai_active_tasks",
    "structai_adapter_requests_total",
    "structai_adapter_errors_total",
    "structai_adapter_duration_seconds",
    "structai_mcp_connections",
    "structai_artifacts_total",
    "structai_artifact_bytes_total",
    "structai_events_total",
    "structai_event_publish_failed_total",
    "structai_audit_total",
)
"""`docs/02` §14 逐字照抄的 15 个标准指标名。"""

ALLOWED_LABELS: Final[tuple[str, ...]] = (
    "tool",
    "operation",
    "software",
    "product",
    "adapter",
    "status",
)
"""`docs/02` §15「允许」的标签（逐条照抄）。"""

HIGH_CARDINALITY_LABELS: Final[tuple[str, ...]] = (
    "tenant_id",
    "user_id",
    "project_id",
    "request_id",
    "task_id",
)
"""`docs/02` §15「谨慎使用」的高基数 ID（本实现一律**丢弃**，见模块裁决 1）。"""


@dataclass(frozen=True, slots=True)
class MetricSample:
    """一个样本点（指标名 + 标签 + 数值）。

    Attributes:
        name: 指标名。
        value: 数值。
        labels: 已清洗、已排序的标签元组（`((键, 值), ...)`）。
    """

    name: str
    value: float
    labels: tuple[tuple[str, str], ...] = ()

    def render(self) -> str:
        """渲染成一行 Prometheus 文本样本（`docs/02` §42）。"""
        if not self.labels:
            return f"{self.name} {_format_value(self.value)}"
        rendered = ",".join(f'{key}="{value}"' for key, value in self.labels)
        return f"{self.name}{{{rendered}}} {_format_value(self.value)}"


class MetricsService:
    """进程内指标寄存器（`docs/02` §13 / §14；见模块裁决 3）。

    🔴 本类**不**暴露任何 HTTP 端点（`docs/02` §45：暴露必须由 HTTP 管理层控制）；
    它只提供 `render()` 文本，供 P41 的管理接口按需挂载。
    """

    def __init__(self, *, extra_labels: Mapping[str, str] | None = None) -> None:
        """建立空寄存器。

        Args:
            extra_labels: 附加的**静态**标签（如部署名）；同样经过清洗
                （高基数 / 敏感键仍被丢弃）。
        """
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._observations: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = {}
        self._dropped: list[str] = []
        self._extra_labels = _clean_labels(extra_labels, self._dropped)

    # ===== 契约：Domain `MetricsRecorder`（`docs/02` §13）=====

    def counter(
        self,
        name: str,
        value: float = 1,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        """累加一个计数器（`docs/02` §13；单调递增）。"""
        key = self._key(name, labels)
        if key is None:
            return
        self._counters[key] = self._counters.get(key, 0.0) + value

    def gauge(
        self,
        name: str,
        value: float,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        """设置一个仪表值（`docs/02` §13；覆盖写）。"""
        key = self._key(name, labels, numeric=value)
        if key is None:
            return
        self._gauges[key] = value

    def observe(
        self,
        name: str,
        value: float,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        """记录一次观测（`docs/02` §13；用于直方图 / 摘要的 count / sum）。"""
        key = self._key(name, labels, numeric=value)
        if key is None:
            return
        self._observations.setdefault(key, []).append(value)

    # ===== 诊断 / 渲染 =====

    def value(self, name: str, labels: Mapping[str, str] | None = None) -> float:
        """读取某个计数器 / 仪表的值（诊断 / 验收断言用）。"""
        cleaned = _clean_labels(labels, self._dropped)
        key = (name, cleaned)
        if key in self._counters:
            return self._counters[key]
        if key in self._gauges:
            return self._gauges[key]
        return 0.0

    def observation_count(self, name: str, labels: Mapping[str, str] | None = None) -> int:
        """某组观测的样本条数（诊断用）。"""
        cleaned = _clean_labels(labels, self._dropped)
        return len(self._observations.get((name, cleaned), ()))

    def observation_sum(self, name: str, labels: Mapping[str, str] | None = None) -> float:
        """某组观测的数值总和（诊断用）。"""
        cleaned = _clean_labels(labels, self._dropped)
        return float(sum(self._observations.get((name, cleaned), ())))

    def names(self) -> tuple[str, ...]:
        """已登记的指标名（排序）。"""
        collected = {key[0] for key in (*self._counters, *self._gauges, *self._observations)}
        return tuple(sorted(collected))

    def dropped_labels(self) -> tuple[str, ...]:
        """被丢弃的标签**键名**（见模块裁决 1 / 2；**不**记值）。"""
        return tuple(dict.fromkeys(self._dropped))

    def samples(self) -> tuple[MetricSample, ...]:
        """全部样本（确定性排序；见模块裁决 4）。"""
        samples: list[MetricSample] = []
        for (name, labels), value in self._counters.items():
            samples.append(MetricSample(name=name, value=value, labels=labels))
        for (name, labels), value in self._gauges.items():
            samples.append(MetricSample(name=name, value=value, labels=labels))
        for (name, labels), values in self._observations.items():
            count_name = f"{name}_count"
            sum_name = f"{name}_sum"
            samples.append(MetricSample(name=count_name, value=float(len(values)), labels=labels))
            samples.append(MetricSample(name=sum_name, value=float(sum(values)), labels=labels))
        samples.sort(key=lambda sample: (sample.name, sample.labels))
        return tuple(samples)

    def render(self) -> str:
        """Prometheus 文本 exposition（`docs/02` §42 / §45；见模块裁决 4）。"""
        lines = [sample.render() for sample in self.samples()]
        if not lines:
            return ""
        return "\n".join(lines) + "\n"

    @property
    def content_type(self) -> str:
        """`render()` 的 Content-Type（`docs/02` §45）。"""
        return PROMETHEUS_CONTENT_TYPE

    def reset(self) -> None:
        """清空寄存器（测试 / 装配隔离用）。"""
        self._counters.clear()
        self._gauges.clear()
        self._observations.clear()
        self._dropped.clear()

    # ===== 内部 =====

    def _key(
        self,
        name: str,
        labels: Mapping[str, str] | None,
        *,
        numeric: float | None = None,
    ) -> tuple[str, tuple[tuple[str, str], ...]] | None:
        """构造寄存器键；非法输入一律**丢弃并计数**（见模块裁决 3）。"""
        if not name:
            self._dropped.append("<empty_metric_name>")
            return None
        if numeric is not None and not math.isfinite(numeric):
            self._dropped.append(f"{name}:<non_finite_value>")
            return None
        cleaned = _clean_labels(labels, self._dropped)
        if self._extra_labels:
            merged = dict(cleaned)
            for key, value in self._extra_labels:
                merged.setdefault(key, value)
            cleaned = tuple(sorted(merged.items()))
        return (name, cleaned)


def _clean_labels(
    labels: Mapping[str, str] | None,
    dropped: list[str],
) -> tuple[tuple[str, str], ...]:
    """清洗标签：丢弃高基数与敏感键，其余排序（见模块裁决 1 / 2）。"""
    if not labels:
        return ()
    cleaned: dict[str, str] = {}
    for key, value in labels.items():
        name = str(key)
        if name in HIGH_CARDINALITY_LABELS or _sensitive(name):
            dropped.append(name)
            continue
        cleaned[name] = str(value)
    return tuple(sorted(cleaned.items()))


def _sensitive(name: str) -> bool:
    """键名是否敏感（`docs/07` §14.3）。"""
    from app.infrastructure.secrets.base import looks_sensitive

    return looks_sensitive(name)


def _format_value(value: float) -> str:
    """数值 → Prometheus 文本（整数不带小数点；其余用 `repr` 的稳定形式）。"""
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return repr(float(value))
