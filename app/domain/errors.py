"""Domain Errors —— 统一异常与 20 条错误码（`docs/07` §11；`docs/02` §9）。

权威来源：

- `docs/02` §9（`source7` §9）—— 基类形状：类属性 `code` / `error_type` /
  `retryable`，构造函数 `(message, *, details, cause)`。
- `docs/07` §11 —— **20 条错误码**是冻结契约；本文件的每个派生异常恰好对应一条。
- `docs/02` §48 / `docs/03` §8 —— 同一份 20 码清单（三处一致）。
- `docs/03` §7 / §63 —— 对外错误信封字段：`code` / `type` / `message` / `details` /
  `retryable`，故提供 `to_dict()`。
- `docs/03` §124（Retry Rules）—— `retryable` 的**类默认值**只按规范明示设置：
  `STRUCTAI-2000` / `STRUCTAI-2300` / `STRUCTAI-5000` 为 `True`（§56 明确
  「Queue Full → STRUCTAI-5000，retryable = true」），其余为 `False`；
  规范同时说明「具体 Retry Policy 由 Operation Registry / Adapter 决定」，
  因此 `retryable` 是默认值，最终判定不在本层。

分层红线（`docs/07` §14.1 / §14.3；`docs/02` §6）：

- 本模块只依赖标准库，不得引用任何 ORM / Web 框架 / MCP SDK / HTTP 客户端（`docs/07` §14.1）。
- **绝不记录 secret**：`details` 只放非敏感诊断信息，禁止写入 password / API key /
  token / private key；异常信息中也不得出现任何厂商专属内容。
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "AdapterError",
    "ArtifactError",
    "CapabilityError",
    "ConcurrencyConflictError",
    "ConfirmationRequiredError",
    "EngineeringValidationError",
    "InternalError",
    "NotFoundError",
    "PermissionDeniedError",
    "ProtocolError",
    "ResourceLockedError",
    "SchemaValidationError",
    "SoftwareAPIError",
    "SoftwareAuthenticationError",
    "SoftwareConnectionError",
    "SoftwareTimeoutError",
    "StructAIError",
    "TaskCancelledError",
    "TaskError",
    "TaskRecoveryError",
    "TaskTimeoutError",
    "TenantAccessDeniedError",
]


class StructAIError(Exception):
    """所有 Core 异常的基类（`docs/02` §9）。

    - `code`：`STRUCTAI-NNNN`，20 码契约（`docs/07` §11）。
    - `error_type`：稳定的大写类型名，供 MCP 响应与日志使用（`docs/03` §8）。
    - `retryable`：默认值，最终重试策略由 Operation Registry / Adapter 决定（`docs/03` §124）。
    - `cause`：原始异常，仅用于服务端诊断，**不得**直接暴露给客户端（`docs/03` §63）。
    """

    code = "STRUCTAI-7000"
    error_type = "INTERNAL_ERROR"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}
        self.cause = cause

    def to_dict(self) -> dict[str, Any]:
        """归一化错误对象（`docs/03` §7 错误信封）。

        只输出规范允许的字段；`cause` 属于诊断信息，不在此返回。
        """
        return {
            "code": self.code,
            "type": self.error_type,
            "message": self.message,
            "details": self.details,
            "retryable": self.retryable,
        }


# ===== 1xxx 请求 / 校验 / 并发 =====


class ProtocolError(StructAIError):
    """`STRUCTAI-1000` 未知 Tool 或请求格式非法（`docs/07` §11）。"""

    code = "STRUCTAI-1000"
    error_type = "PROTOCOL_ERROR"


class SchemaValidationError(StructAIError):
    """`STRUCTAI-1100` JSON Schema 校验失败（`docs/07` §11）。"""

    code = "STRUCTAI-1100"
    error_type = "SCHEMA_VALIDATION_ERROR"


class EngineeringValidationError(StructAIError):
    """`STRUCTAI-1200` 工程语义非法（`docs/07` §11）。"""

    code = "STRUCTAI-1200"
    error_type = "ENGINEERING_VALIDATION_ERROR"


class ConcurrencyConflictError(StructAIError):
    """`STRUCTAI-1300` 乐观锁失败 / 幂等键冲突（`docs/07` §11）。"""

    code = "STRUCTAI-1300"
    error_type = "CONCURRENCY_CONFLICT"


# ===== 2xxx 外部工程软件 =====


class SoftwareConnectionError(StructAIError):
    """`STRUCTAI-2000` 无法连接工程软件（`docs/07` §11；可重试，`docs/03` §124）。"""

    code = "STRUCTAI-2000"
    error_type = "SOFTWARE_CONNECTION_ERROR"
    retryable = True


class SoftwareAuthenticationError(StructAIError):
    """`STRUCTAI-2100` 软件侧凭据无效（`docs/07` §11）。

    ⚠️ 凭据本身绝不写入 `message` / `details`（`docs/07` §14.3）。
    """

    code = "STRUCTAI-2100"
    error_type = "SOFTWARE_AUTHENTICATION_ERROR"


class SoftwareAPIError(StructAIError):
    """`STRUCTAI-2200` 工程软件返回业务错误（`docs/07` §11）。"""

    code = "STRUCTAI-2200"
    error_type = "SOFTWARE_API_ERROR"


class SoftwareTimeoutError(StructAIError):
    """`STRUCTAI-2300` 工程软件调用超时（`docs/07` §11；可重试，`docs/03` §124）。"""

    code = "STRUCTAI-2300"
    error_type = "SOFTWARE_TIMEOUT"
    retryable = True


# ===== 3xxx 能力 =====


class CapabilityError(StructAIError):
    """`STRUCTAI-3000` 实例不具备该能力（`docs/07` §11）。"""

    code = "STRUCTAI-3000"
    error_type = "CAPABILITY_ERROR"


# ===== 4xxx 安全 =====


class PermissionDeniedError(StructAIError):
    """`STRUCTAI-4000` 有效权限不足（`docs/07` §11）。"""

    code = "STRUCTAI-4000"
    error_type = "PERMISSION_DENIED"


class ConfirmationRequiredError(StructAIError):
    """`STRUCTAI-4100` 缺 Confirmation Token（`docs/07` §11 / §8.4）。"""

    code = "STRUCTAI-4100"
    error_type = "CONFIRMATION_REQUIRED"


class TenantAccessDeniedError(StructAIError):
    """`STRUCTAI-4200` 跨租户访问被拦截（`docs/07` §11 / §14.3）。"""

    code = "STRUCTAI-4200"
    error_type = "TENANT_ACCESS_DENIED"


# ===== 5xxx 任务 =====


class TaskError(StructAIError):
    """`STRUCTAI-5000` 任务执行失败（含队列满；可重试，`docs/03` §56 / §124）。"""

    code = "STRUCTAI-5000"
    error_type = "TASK_ERROR"
    retryable = True


class TaskTimeoutError(StructAIError):
    """`STRUCTAI-5100` 任务超时（`docs/07` §11）。

    ⚠️ 任务不得直接标记 `FAILED`，须由 Task Engine 按 Retry Policy 最终归类
    （`docs/03` §103）。
    """

    code = "STRUCTAI-5100"
    error_type = "TASK_TIMEOUT"


class TaskCancelledError(StructAIError):
    """`STRUCTAI-5200` 任务被取消（`docs/07` §11）。"""

    code = "STRUCTAI-5200"
    error_type = "TASK_CANCELLED"


class TaskRecoveryError(StructAIError):
    """`STRUCTAI-5300` 任务恢复失败（`docs/07` §11）。

    ⚠️ 恢复中的任务不得直接标记 `COMPLETED`（`docs/07` §14.4）。
    """

    code = "STRUCTAI-5300"
    error_type = "TASK_RECOVERY_ERROR"


# ===== 6xxx 适配器 / 资源 / 产物 =====


class AdapterError(StructAIError):
    """`STRUCTAI-6000` Adapter 内部错误（`docs/07` §11）。

    `docs/03` §124 只把「部分 `STRUCTAI-6000`」列为可重试，故类默认 `False`，
    是否重试由 Operation Registry / Adapter 的重试策略决定。
    """

    code = "STRUCTAI-6000"
    error_type = "ADAPTER_ERROR"


class ResourceLockedError(StructAIError):
    """`STRUCTAI-6100` 资源被锁（`docs/07` §11 / §15）。"""

    code = "STRUCTAI-6100"
    error_type = "RESOURCE_LOCKED"


class ArtifactError(StructAIError):
    """`STRUCTAI-6200` 产物读写失败（`docs/07` §11 / §29）。"""

    code = "STRUCTAI-6200"
    error_type = "ARTIFACT_ERROR"


# ===== 7xxx 兜底 =====


class InternalError(StructAIError):
    """`STRUCTAI-7000` 兜底内部错误（`docs/07` §11）。"""

    code = "STRUCTAI-7000"
    error_type = "INTERNAL_ERROR"


# ===== Registry / 资源查找（**不**属 20 码错误契约）=====


class NotFoundError(LookupError):
    """未找到指定资源（`docs/02` §15 / §9）。

    名称照抄 `docs/02` §15（`SchemaRegistry.get` 未注册 id 时 `raise NotFoundError(...)`）
    与 `docs/02` §9（`source9` 的 `class NotFoundError(StructAIError)`）。

    ⚠️ **本类刻意不继承 `StructAIError`、也不带任何 `STRUCTAI-xxxx` 码**：

    - `docs/07` §11 冻结的是 **20 码**错误契约，其中**没有** NotFound 码；
      `docs/02` §9（`source9`）另给了一个 `STRUCTAI-70xx` 段的新码（即**第 21 个码**），
      与本项目唯一权威的错误码清单（`docs/07` §11）冲突。
    - 本批的裁决（已登记到 `docs/07` §11 补充说明）：**不自造 `STRUCTAI-xxxx`**。
      查找失败是 **Registry 装配期**的内部信号（`docs/07` §14.4：Registry 校验失败 →
      Server MUST NOT become READY），它**不会**被序列化成 MCP 响应 ——
      对外错误一律走 20 码（`to_dict()` 的形状只属于 `StructAIError`）。
    - 继承 `LookupError` 使 `except LookupError` / `except KeyError` 之外的
      `except StructAIError` **不会**误吞它，两层错误语义不会混淆。

    用法（`docs/02` §15 原文写法）：未注册的 Schema id → `NotFoundError`。
    """
