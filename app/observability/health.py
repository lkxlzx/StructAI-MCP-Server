"""Observability · Health（`docs/07` §12 P34；`docs/02` §16.1–§16.3 / §17 / §41 / §46 / §94）。

权威来源
--------
- `docs/02` §16（`exec`）—— 三个 HTTP 入口：`GET /livez` / `GET /readyz` /
  `GET /health`。
- `docs/02` §16.1（`exec`）—— `/livez` 只回答「进程是否存活」；**不检查**
  DB / Adapter / Task Engine。
- `docs/02` §16.2（`exec`）—— `/readyz` 检查 `Database` / `Registry` /
  `Task Engine` / `Event Dispatcher`，返回 `{"status": "READY"}`。
- `docs/02` §16.3（`exec`）—— `/health` 返回完整状态（`status` / `database` /
  `task_engine` / `adapters`），并明确「单个软件不可用 ≠ Core DOWN」。
- `docs/02` §17（`exec`）—— `HealthService.liveness` / `readiness` / `health`
  三个方法；检查器契约 `HealthChecker.check()`；注册方式
  `health_registry.register("database", …)`。
- `docs/02` §41（`blue`）—— 同一组三个 HTTP 入口的「最小可运行形态」。
- `docs/02` §46（`exec`）—— `/health` 可能披露软件 / Adapter / 数据库信息，
  因此默认只应暴露在**管理面或本地绑定**的接口上（本模块只返回状态 / 原因 / 计数）。
- `docs/02` §94（`exec`）—— `livez = Process Alive`；
  `readyz = Core DB + Registry + Task Engine`；
  `health = DB + Registry + Task Engine + Adapter Manager + Software Instances`；
  「单个工程软件不可用不得导致 Core ready = false」（`docs/02` §94 原文提到一个具体
  厂商名，`docs/07` §14.2 禁止在 `app/` 内出现厂商名，故此处只保留其语义）。
- `docs/07` §14.4 —— 「Registry 校验失败 → **Server MUST NOT become READY**」；
  「单实例失败不得让整个服务器不可用」。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **`readiness` 用字面量 `READY` / `NOT_READY`，`liveness` / `health` 用
   `HealthStatus`**：`docs/02` §16.2 的返回体写的是 `{"status": "READY"}`（两个
   字面量），而 §16.1 / §16.3 / §94 的状态词表是 `app.domain.enums.HealthStatus`
   （`HEALTHY` / `DEGRADED` / `UNAVAILABLE`）。两者**不**混用：`readiness` 是对
   负载均衡器的**就绪**回答，`health` 是对人的**健康**回答（见模块常量
   `READY` / `NOT_READY`）。
2. **`registry` 恒为关键检查**：`docs/07` §14.4 明令「Registry 校验失败 → Server
   MUST NOT become READY」。`docs/02` §16.2 列出的检查项含 `Registry`，故
   `HealthService` 在构造时把 `registry` **强制并入**关键集合 —— 即使调用方传入
   的关键集合漏掉它，也不会出现「Registry 挂了但 `/readyz` 说 READY」。
3. **`liveness` **绝不**查注册表**：`docs/02` §16.1 明确 `/livez` **不检查**
   DB / Adapter / Task Engine。故 `liveness()` 是一个**纯函数式**回答（常量
   `{"status": HEALTHY}`）—— 连注册表都不读，否则「依赖挂了就重启进程」会让
   可恢复的故障变成进程重启（Kubernetes 的 liveness 语义）。
4. **检查器**绝不**抛异常**：`docs/02` §17 的 `HealthChecker.check()` 返回数据，
   而 `docs/07` §14.4 要求「单实例失败不得让整个服务器不可用」。故
   `CallableHealthChecker` 把任何异常转成
   `{"status": UNAVAILABLE, "reason": <异常类名>}` —— **只**记录异常**类名**，
   **绝不**记录 `str(error)`：连接串 / 口令常出现在异常消息里（`docs/07` §14.3）。
5. **未注册的名字是 `UNAVAILABLE`，不是 `HEALTHY`**：`docs/02` §16.2 / §94 的
   就绪定义是「这些依赖可用」。一个尚未装配的依赖（`container.py` 还没注册
   检查器）**不**等于可用，故 `run()` 对未注册名返回
   `{"status": UNAVAILABLE, "reason": "checker_not_registered"}`。
6. **非关键失败 → `DEGRADED`，只有关键失败 → `UNAVAILABLE`**：`docs/02` §16.3 /
   §94 的 🔴「单个软件不可用 ≠ Core DOWN」正是指这一点。`adapters` /
   `software_instances` 属非关键；`database` / `registry` / `task_engine` 属关键。
7. **`/health` 的键是 `database` / `task_engine` / `adapters`**：`docs/02` §16.3
   的示例只有这三组。`docs/02` §94 的五个检查项按**语义**归组：`adapter_manager`
   与 `software_instances` 都落在 `adapters` 下（前者是管理器整体，后者是各实例），
   其余保持各自的键；`registry` 单独成键（它是 `docs/07` §14.4 的硬门槛）。
8. **模块保持零框架依赖**：`docs/07` §14.1 的依赖方向是 `Interface → Application
   → Domain`，`app/observability/` 是 app 根下的**旁路支撑层**（`docs/07` §3.3）。
   本模块只 import 标准库与 `app.domain` —— **不** import SQLAlchemy / FastAPI /
   `app.infrastructure` / `app.application`：真实的数据库 / Registry / 任务引擎
   检查器由 `app/container.py` 注入（`docs/02` §17 的 `register` 示例）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`（含 `HealthStatus` 与 `HealthChecker` 契约）：
**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖
`app.infrastructure` / `app.interfaces` / `app.application`，也**不**出现任何
厂商专属内容。返回体只含状态 / 原因 / 计数，**绝不**含连接串、凭据或 payload。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Final

from app.domain.enums import HealthStatus
from app.domain.errors import InternalError
from app.domain.protocols import HealthChecker

__all__ = [
    "HEALTH_CHECKS",
    "HEALTH_PATH",
    "HEALTH_STAGE",
    "LIVENESS_PATH",
    "NOT_READY",
    "READINESS_CHECKS",
    "READINESS_PATH",
    "READY",
    "STATUS_KEY",
    "CallableHealthChecker",
    "HealthRegistry",
    "HealthService",
    "is_ready_status",
]

HEALTH_STAGE: Final[str] = "health"
"""错误 `details["stage"]` 的固定取值（`docs/07` §11；本模块所有 raise 都用它）。"""

LIVENESS_PATH: Final[str] = "/livez"
"""存活探针路径（`docs/02` §16 / §41 / §94，逐字照抄）。"""

READINESS_PATH: Final[str] = "/readyz"
"""就绪探针路径（`docs/02` §16 / §41 / §94，逐字照抄）。"""

HEALTH_PATH: Final[str] = "/health"
"""完整健康路径（`docs/02` §16 / §41 / §94，逐字照抄）。"""

READINESS_CHECKS: Final[tuple[str, ...]] = ("database", "registry", "task_engine")
"""`docs/02` §16.2 / §94 的就绪检查项（逐字抄写）。

⚠️ `docs/02` §16.2 的清单里还有 `Event Dispatcher`：本批**没有**独立的
Event Dispatcher 组件（`docs/02` §5.4 把完整 Outbox 记为 Alpha 限制），故它
不在本元组里 —— 需要时由 `app/container.py` 注册同名检查器并显式传入
`critical_checks`，本模块**不**为它伪造一个恒真的检查器。
"""

HEALTH_CHECKS: Final[tuple[str, ...]] = (
    "database",
    "registry",
    "task_engine",
    "adapter_manager",
    "software_instances",
)
"""`docs/02` §94 的完整健康检查项（逐字抄写：DB + Registry + Task Engine +
Adapter Manager + Software Instances）。"""

READY: Final[str] = "READY"
"""`docs/02` §16.2 的就绪字面量（`{"status": "READY"}`，逐字照抄）。"""

NOT_READY: Final[str] = "NOT_READY"
"""就绪的否定值（见模块裁决 1：与 `HealthStatus` **不**混用）。"""

STATUS_KEY: Final[str] = "status"
"""返回体里的状态键（`docs/02` §16.2 / §16.3 / §17 的 `{"status": …}`）。"""


class CallableHealthChecker:
    """把「一个可等待的检查函数」适配成 `HealthChecker`（`docs/02` §17）。

    🔴 `check()` **绝不**抛出：任何异常都转成
    `{"status": UNAVAILABLE, "reason": <异常类名>}`。**只**记录类名 ——
    异常消息可能带连接串 / 口令（`docs/07` §14.3），不得进入响应体或日志。
    """

    def __init__(
        self,
        name: str,
        check: Callable[[], Awaitable[Mapping[str, Any]]],
        *,
        critical: bool = True,
    ) -> None:
        """绑定检查名与检查函数。

        Args:
            name: 检查名（`docs/02` §17 的 `"database"` / `"task_engine"` / …）。
            check: 无参异步函数，返回含 `status` 的映射（`docs/02` §17）。
            critical: 是否关键；关键失败会让 `/readyz` 与 `/health` 变成
                非就绪 / `UNAVAILABLE`（见模块裁决 6）。
        """
        self._name = name
        self._check = check
        self._critical = critical

    @property
    def name(self) -> str:
        """检查名（只读）。"""
        return self._name

    @property
    def critical(self) -> bool:
        """是否关键检查（只读）。"""
        return self._critical

    async def check(self) -> Mapping[str, Any]:
        """执行检查（`docs/02` §17）。

        Returns:
            检查函数返回的映射；异常时
            `{"status": UNAVAILABLE, "reason": <异常类名>}`（见模块裁决 4）。
        """
        try:
            return await self._check()
        except Exception as error:  # noqa: BLE001 —— 契约要求**绝不**抛出
            # 只放异常**类名**：消息可能携带连接串 / 凭据（`docs/07` §14.3）。
            return {
                STATUS_KEY: HealthStatus.UNAVAILABLE,
                "reason": type(error).__name__,
            }


class HealthRegistry:
    """健康检查器的注册表（`docs/02` §17）。

    ⚠️ 注册名重复是**装配错误**，不是「后注册者覆盖前者」：静默覆盖会让
    「谁在检查数据库」变得不可判定（`docs/07` §14.3 的同源原则）。
    """

    def __init__(self) -> None:
        """创建空注册表。"""
        self._checkers: dict[str, HealthChecker] = {}

    def register(self, name: str, checker: HealthChecker) -> None:
        """注册一个检查器（`docs/02` §17 的 `health_registry.register(...)`）。

        Args:
            name: 检查名（非空白）。
            checker: `HealthChecker` 实现。

        Raises:
            InternalError: `STRUCTAI-7000` `reason="invalid_checker"`（空名）
                或 `reason="duplicate_checker"`（重名）。
        """
        if not name or not name.strip():
            raise InternalError(
                "Health checker name must not be blank",
                details={"stage": HEALTH_STAGE, "reason": "invalid_checker"},
            )
        if name in self._checkers:
            raise InternalError(
                "Health checker is already registered",
                details={"stage": HEALTH_STAGE, "reason": "duplicate_checker"},
            )
        self._checkers[name] = checker

    def names(self) -> tuple[str, ...]:
        """已注册的检查名（按注册顺序）。"""
        return tuple(self._checkers)

    def get(self, name: str) -> HealthChecker | None:
        """取检查器；未注册时 `None`。"""
        return self._checkers.get(name)

    async def run(self, names: Sequence[str]) -> dict[str, dict[str, Any]]:
        """**并发**跑指定的检查（`docs/02` §17 / §94）。

        Args:
            names: 要跑的检查名（顺序即结果字典的插入顺序）。

        Returns:
            检查名 → 结果映射。**绝不**抛出：

            - 未注册的名字 → `{"status": UNAVAILABLE, "reason":
              "checker_not_registered"}`（见模块裁决 5）；
            - 检查器自身抛异常 → `{"status": UNAVAILABLE, "reason": <类名>}`；
            - 返回体缺少 `status` → 视为 `UNAVAILABLE`（`docs/02` §17 要求该键必填）。
        """
        unique = list(dict.fromkeys(names))
        results = await asyncio.gather(
            *(self._run_one(name) for name in unique),
            return_exceptions=True,
        )
        payload: dict[str, dict[str, Any]] = {}
        for name, result in zip(unique, results, strict=True):
            if isinstance(result, BaseException):
                payload[name] = {
                    STATUS_KEY: HealthStatus.UNAVAILABLE,
                    "reason": type(result).__name__,
                }
            else:
                payload[name] = dict(result)
        return payload

    async def _run_one(self, name: str) -> Mapping[str, Any]:
        """跑单个检查并归一化结果（未注册 → `checker_not_registered`）。"""
        checker = self._checkers.get(name)
        if checker is None:
            return {
                STATUS_KEY: HealthStatus.UNAVAILABLE,
                "reason": "checker_not_registered",
            }
        try:
            result = await checker.check()
        except Exception as error:  # noqa: BLE001 —— 契约要求**绝不**抛出
            return {
                STATUS_KEY: HealthStatus.UNAVAILABLE,
                "reason": type(error).__name__,
            }
        if STATUS_KEY not in result:
            return {
                STATUS_KEY: HealthStatus.UNAVAILABLE,
                "reason": "status_missing",
            }
        return result


class HealthService:
    """健康 / 就绪 / 存活服务（`docs/02` §16.1–§16.3 / §17 / §94）。

    🔴 `docs/02` §46：`/health` 可能披露软件 / Adapter / 数据库信息，因此它默认
    只应暴露在**管理面或本地绑定**的接口上。本服务只返回状态 / 原因 / 计数 ——
    **绝不**返回连接串、凭据或 payload（`docs/07` §14.3）。
    """

    def __init__(
        self,
        registry: HealthRegistry,
        *,
        critical_checks: Sequence[str] = READINESS_CHECKS,
        reported_checks: Sequence[str] = HEALTH_CHECKS,
    ) -> None:
        """绑定注册表与两组检查名。

        Args:
            registry: 检查器注册表（`docs/02` §17）。
            critical_checks: 关键检查（`docs/02` §16.2）；`registry` 会被**强制**
                并入（见模块裁决 2）。
            reported_checks: `/health` 报告的检查（`docs/02` §94）。
        """
        self._registry = registry
        critical = list(dict.fromkeys(critical_checks))
        if "registry" not in critical:
            # 见模块裁决 2：`docs/07` §14.4 的硬门槛不因调用方漏传而失效。
            critical.append("registry")
        self._critical_checks: tuple[str, ...] = tuple(critical)
        reported = list(dict.fromkeys(reported_checks))
        for name in self._critical_checks:
            if name not in reported:
                reported.append(name)
        self._reported_checks: tuple[str, ...] = tuple(reported)

    @property
    def registry(self) -> HealthRegistry:
        """检查器注册表（只读）。"""
        return self._registry

    @property
    def critical_checks(self) -> tuple[str, ...]:
        """关键检查名（含被强制并入的 `registry`）。"""
        return self._critical_checks

    @property
    def reported_checks(self) -> tuple[str, ...]:
        """`/health` 报告的检查名。"""
        return self._reported_checks

    # ===== `docs/02` §16.1：/livez =====

    async def liveness(self) -> dict[str, Any]:
        """存活探针（`docs/02` §16.1 / §94 的 `Process Alive`）。

        Returns:
            `{"status": HEALTHY}` —— **不**咨询注册表（见模块裁决 3）：
            `/livez` 只回答「进程是否存活」，**不检查** DB / Adapter / Task Engine。
        """
        return {STATUS_KEY: HealthStatus.HEALTHY}

    # ===== `docs/02` §16.2：/readyz =====

    async def readiness(self) -> dict[str, Any]:
        """就绪探针（`docs/02` §16.2 / §94 的 `Core DB + Registry + Task Engine`）。

        Returns:
            `{"status": READY}` —— **仅当**关键检查**全部** `HEALTHY`；
            否则 `{"status": NOT_READY, "checks": {...}}`。

        🔴 `docs/07` §14.4：Registry 校验失败 **MUST NOT** become READY ——
        `registry` 恒在关键集合里（见模块裁决 2）。
        """
        checks = await self._registry.run(self._critical_checks)
        if all(_is_healthy(payload) for payload in checks.values()):
            return {STATUS_KEY: READY}
        return {STATUS_KEY: NOT_READY, "checks": checks}

    # ===== `docs/02` §16.3 / §94：/health =====

    async def health(self) -> dict[str, Any]:
        """完整健康（`docs/02` §16.3 / §94）。

        Returns:
            `{"status": …, "database": {...}, "registry": {...},
            "task_engine": {...}, "adapters": {...}}`。

        🔴 「单个软件不可用 ≠ Core DOWN」（`docs/02` §16.3 / §94；
        `docs/07` §14.4）：非关键失败（某个 Adapter / 某个软件实例 DOWN）只让整体
        变成 `DEGRADED`，**绝不**变成 `UNAVAILABLE`；只有**关键**检查不是
        `HEALTHY` 时才是 `UNAVAILABLE`（见模块裁决 6 / 7）。
        """
        checks = await self._registry.run(self._reported_checks)
        payload: dict[str, Any] = {STATUS_KEY: HealthStatus.HEALTHY}
        adapters: dict[str, Any] = {}
        for name in self._reported_checks:
            result = checks[name]
            if name == "adapter_manager":
                adapters["manager"] = result
            elif name == "software_instances":
                adapters["software_instances"] = result
            else:
                payload[name] = result
        payload["adapters"] = adapters
        payload[STATUS_KEY] = self._overall_status(checks)
        return payload

    def _overall_status(self, checks: Mapping[str, Mapping[str, Any]]) -> HealthStatus:
        """由各检查结果汇总整体状态（见模块裁决 6）。"""
        for name in self._critical_checks:
            if not _is_healthy(checks[name]):
                return HealthStatus.UNAVAILABLE
        for name in self._reported_checks:
            if not _is_healthy(checks[name]):
                return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY


def _is_healthy(payload: Mapping[str, Any]) -> bool:
    """该检查结果是否 `HEALTHY`（`docs/02` §16.2 的「全部可用」口径）。"""
    return str(payload.get(STATUS_KEY, "")) == str(HealthStatus.HEALTHY)


def is_ready_status(payload: Mapping[str, Any]) -> bool:
    """`payload` 是否表达「就绪」（`docs/02` §16.2 的 `READY`）。

    Args:
        payload: 任一返回体（`readiness()` 的产物，或 HTTP 层的响应体）。

    Returns:
        `payload[STATUS_KEY] == READY` 时为 `True`；否则 `False`。

    ⚠️ 它**只**认 `READY`：`HEALTHY` / `DEGRADED` / `NOT_READY` 都不是就绪
    （见模块裁决 1：两套词表不得混用）。
    """
    return str(payload.get(STATUS_KEY, "")) == READY
