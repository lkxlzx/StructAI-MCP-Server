"""Domain Enums —— 领域枚举（`docs/07` §4.1；`docs/02` §8）。

权威来源（逐项照抄，不重命名、不改取值）：

- `docs/02` §8（`source7` §8）：`RiskLevel` / `ExecutionMode` / `TaskStatus` /
  `ResourceType` / `LockMode` / `CapabilityStatus` / `SoftwareStatus` /
  `DocumentStatus` / `ArtifactStatus`。
- `docs/02` §5（`py` §5）：`HealthStatus` / `SoftwareConnectionState` / `PermissionEffect`。
- `docs/02` §17（`py` §17）：`TaskPriority` = LOW / NORMAL / HIGH / CRITICAL。
- `docs/02` §71（`source7` §71）＝ `docs/07` §5.7：`PermissionCode` 12 码。
  `docs/07` §4.1 把该枚举写作 `Permission`，本文件保留规范源码类名 `PermissionCode`，
  并给出 `Permission` 别名（同一对象，非新枚举）。
- `docs/02` §70（`source7` §70）＋ `docs/07` §5.6：`Capability` 能力码集合。
- `docs/02` §33 / §44（`py` §33 / §44）：`ArtifactType` / `AuditResult`。
  规范只给出产物类别与审计字段的中文描述，**未给出枚举取值**；这两个枚举是本文件
  **仅有的推导项**（见各自类注释），其余枚举一律照抄。

分层红线（`docs/07` §14.1 / §14.2；`docs/02` §6）：

- 本模块只用标准库 `enum`，不得引用任何 ORM / Web 框架 / MCP SDK / HTTP 客户端（`docs/07` §14.1）。
- 取值中**不得**出现任何厂商名（厂商专属名称只允许出现在 Adapter 层）。

技术栈（`docs/07` §3.1）：Python ≥3.12 → 使用 `enum.StrEnum`。
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "ACLPrincipalType",
    "ACLScope",
    "ArtifactStatus",
    "ArtifactType",
    "AuditResult",
    "AuthenticationMethod",
    "Capability",
    "CapabilityStatus",
    "DocumentStatus",
    "ExecutionMode",
    "HealthStatus",
    "LockMode",
    "Permission",
    "PermissionCode",
    "PermissionEffect",
    "ResourceType",
    "RoleName",
    "RiskLevel",
    "SoftwareConnectionState",
    "SoftwareStatus",
    "TaskPriority",
    "TaskStatus",
]


# ===== `docs/02` §8（source7 §8）=====


class RiskLevel(StrEnum):
    """操作风险等级（`docs/02` §8）。"""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ExecutionMode(StrEnum):
    """操作执行模式（`docs/02` §8）。"""

    SYNC = "SYNC"
    ASYNC = "ASYNC"
    STREAM = "STREAM"


class TaskStatus(StrEnum):
    """任务状态机 12 态（`docs/02` §8；`docs/07` §10.1）。"""

    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    RETRYING = "RETRYING"
    RECOVERING = "RECOVERING"


class ResourceType(StrEnum):
    """可加锁 / 可解析的资源类型（`docs/02` §8）。

    ⚠️ `docs/07` §4.1 的摘要漏写 `PROJECT`；本枚举以 `docs/02` §8（4 值）为准
    —— 项目本身是租户隔离与资源锁的对象（`docs/07` §4.3 `ProjectModel`）。
    """

    SOFTWARE_INSTANCE = "SOFTWARE_INSTANCE"
    PROJECT = "PROJECT"
    MODEL = "MODEL"
    DOCUMENT = "DOCUMENT"


class LockMode(StrEnum):
    """资源锁模式（`docs/02` §8 / §15）。"""

    READ = "READ"
    WRITE = "WRITE"
    EXCLUSIVE = "EXCLUSIVE"


class CapabilityStatus(StrEnum):
    """能力支持状态（`docs/02` §8）。"""

    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


class SoftwareStatus(StrEnum):
    """软件注册状态（`docs/02` §8）。"""

    REGISTERED = "REGISTERED"
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


class DocumentStatus(StrEnum):
    """文档生命周期状态（`docs/02` §8 / §30）。"""

    NEW = "NEW"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class ArtifactStatus(StrEnum):
    """产物状态（`docs/02` §8 / §33）。"""

    CREATED = "CREATED"
    READY = "READY"
    DELETED = "DELETED"


# ===== `docs/02` §5（py §5）=====


class HealthStatus(StrEnum):
    """健康状态（`docs/02` §5 / §41）。"""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class SoftwareConnectionState(StrEnum):
    """软件实例连接状态（`docs/02` §5 / §19）。"""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    RECONNECTING = "RECONNECTING"
    UNAVAILABLE = "UNAVAILABLE"


class PermissionEffect(StrEnum):
    """资源 ACL 的允许 / 拒绝效果（`docs/02` §5；`docs/07` §8.2）。"""

    ALLOW = "ALLOW"
    DENY = "DENY"


class AuthenticationMethod(StrEnum):
    """认证方式（`docs/02` §5；`docs/07` §8.3）。"""

    PASSWORD = "PASSWORD"
    LOCAL = "LOCAL"
    TOKEN = "TOKEN"


# ===== ACL（`docs/02` §24–§28；`docs/07` §8.2）=====


class ACLPrincipalType(StrEnum):
    """资源 ACL 的主体类型（`docs/02` §27；`docs/07` §8.2）。

    取值逐条照抄 `docs/02` §27（`ACLPrincipalType`）：`USER` / `ROLE` / `TENANT`。
    本枚举只描述**判定逻辑**所需的主体种类；ACL 的持久化见
    `app/application/security/permission.py` 的裁决说明（`resource_acls` 表不在
    `docs/07` §4.3 的 24 张表内，本批**不**改表）。
    """

    USER = "USER"
    ROLE = "ROLE"
    TENANT = "TENANT"


class ACLScope(StrEnum):
    """ACL 作用域四级（`docs/07` §8.2 的「四级取最严格」）。

    `docs/02` §28 只冻结了优先级（`Explicit DENY > Explicit ALLOW > Inherited ALLOW >
    Default DENY`）与「Deny wins」，未给出作用域的枚举取值；`docs/07` §8.2 的
    权限链则明确列出四级来源。本枚举是这四级的固化，一一对应、不多不少：

    - `GLOBAL` —— 全局（跨租户的全局角色 / 全局策略）
    - `TENANT` —— 租户级（Tenant Membership / Tenant Roles）
    - `USER` —— 用户级（User → 用户 ACL）
    - `RESOURCE` —— 实例级（Project / Model / Document / SoftwareInstance 等具体资源）

    判定规则：**同一权限在四级之间取最严格** —— 任一级 `DENY` 即 `DENY`
    （`docs/02` §28：Deny wins）。
    """

    GLOBAL = "GLOBAL"
    TENANT = "TENANT"
    USER = "USER"
    RESOURCE = "RESOURCE"


# ===== `docs/02` §17（py §17）=====


class TaskPriority(StrEnum):
    """任务优先级（`docs/02` §17）。

    Queue 必须按 `priority` + `created_at` 排序（`docs/02` §17）。
    """

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ===== `docs/02` §71（source7 §71）＝ `docs/07` §5.7 =====


class PermissionCode(StrEnum):
    """权限码 12 条（`docs/02` §71；`docs/07` §5.7）。

    角色到权限的默认映射见 `docs/07` §5.7 / `docs/02` §72；
    AI Agent 的有效权限 = 用户有效权限 ∩ Agent 权限，**不得提权**（`docs/07` §14.3）。
    """

    MODEL_READ = "MODEL_READ"
    MODEL_WRITE = "MODEL_WRITE"
    MODEL_DELETE = "MODEL_DELETE"
    ANALYSIS_EXECUTE = "ANALYSIS_EXECUTE"
    DESIGN_EXECUTE = "DESIGN_EXECUTE"
    DESIGN_MODIFY = "DESIGN_MODIFY"
    RESULT_READ = "RESULT_READ"
    DOCUMENT_READ = "DOCUMENT_READ"
    DOCUMENT_WRITE = "DOCUMENT_WRITE"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    TOOL_TEST = "TOOL_TEST"
    API_TEST = "API_TEST"


# `docs/07` §4.1 用的名字；与 `PermissionCode` 是同一个枚举对象。
Permission = PermissionCode


# ===== `docs/02` §70（source7 §70）＋ `docs/07` §5.6 =====


class Capability(StrEnum):
    """能力码种子集合（`docs/02` §70 ＋ `docs/07` §5.6）。

    - 成员名 = 能力码的标识符化写法（`.` → `_`），成员值 = 规范原文能力码。
    - 能力是**软件无关**的：取值中不得出现任何厂商名（`docs/07` §14.2）。
    - `docs/07` §5.6 的 `VIEW.*` 是通配写法，不是具体能力码，故不作为枚举成员；
      `VIEW.*` 由 Registry / 数据层在 P08 之后按实际支持情况表达。
    - Core Alpha 的权威能力集合仍是数据库中的 Capability 表（P07 Seed / P08 Registry）；
      本枚举是同一集合的**类型化视图**，供类型检查与静态引用使用。
    """

    # --- 模型读写 ---
    MODEL_NODE_READ = "MODEL.NODE.READ"
    MODEL_NODE_WRITE = "MODEL.NODE.WRITE"
    MODEL_NODE_DELETE = "MODEL.NODE.DELETE"
    MODEL_ELEMENT_READ = "MODEL.ELEMENT.READ"
    MODEL_ELEMENT_WRITE = "MODEL.ELEMENT.WRITE"
    MODEL_ELEMENT_DELETE = "MODEL.ELEMENT.DELETE"
    MODEL_MATERIAL_READ = "MODEL.MATERIAL.READ"
    MODEL_MATERIAL_WRITE = "MODEL.MATERIAL.WRITE"
    MODEL_SECTION_READ = "MODEL.SECTION.READ"
    MODEL_SECTION_WRITE = "MODEL.SECTION.WRITE"
    MODEL_BOUNDARY_READ = "MODEL.BOUNDARY.READ"
    MODEL_BOUNDARY_WRITE = "MODEL.BOUNDARY.WRITE"
    MODEL_LOAD_READ = "MODEL.LOAD.READ"
    MODEL_LOAD_WRITE = "MODEL.LOAD.WRITE"
    MODEL_LOAD_DELETE = "MODEL.LOAD.DELETE"
    MODEL_GROUP_READ = "MODEL.GROUP.READ"
    MODEL_READ = "MODEL.READ"

    # --- 文档 ---
    DOCUMENT_NEW = "DOCUMENT.NEW"
    DOCUMENT_OPEN = "DOCUMENT.OPEN"
    DOCUMENT_SAVE = "DOCUMENT.SAVE"
    DOCUMENT_SAVE_AS = "DOCUMENT.SAVE_AS"
    DOCUMENT_CLOSE = "DOCUMENT.CLOSE"
    DOCUMENT_INFO = "DOCUMENT.INFO"

    # --- 分析 ---
    ANALYSIS_STATIC = "ANALYSIS.STATIC"
    ANALYSIS_MODAL = "ANALYSIS.MODAL"
    ANALYSIS_SEISMIC = "ANALYSIS.SEISMIC"
    ANALYSIS_SPECTRUM = "ANALYSIS.SPECTRUM"
    ANALYSIS_BUCKLING = "ANALYSIS.BUCKLING"
    ANALYSIS_TIME_HISTORY = "ANALYSIS.TIME_HISTORY"
    ANALYSIS_NONLINEAR = "ANALYSIS.NONLINEAR"

    # --- 结果 ---
    RESULT_DISPLACEMENT = "RESULT.DISPLACEMENT"
    RESULT_REACTION = "RESULT.REACTION"
    RESULT_ELEMENT_FORCE = "RESULT.ELEMENT_FORCE"
    RESULT_STRESS = "RESULT.STRESS"
    RESULT_MODE_SHAPE = "RESULT.MODE_SHAPE"

    # --- 设计 ---
    DESIGN_STEEL = "DESIGN.STEEL"
    DESIGN_CONCRETE = "DESIGN.CONCRETE"
    DESIGN_SRC = "DESIGN.SRC"
    DESIGN_FOUNDATION = "DESIGN.FOUNDATION"
    DESIGN_OPTIMIZATION = "DESIGN.OPTIMIZATION"
    DESIGN_CODE_CHECK = "DESIGN.CODE_CHECK"


# ===== `docs/02` §33 / §44（py §33 / §44）—— 推导项 =====


class ArtifactType(StrEnum):
    """产物类型（`docs/07` §4.1 要求；取值推导）。

    `docs/02` §33 只给出产物类别的**中文描述**（工程文件 / 模型文件 / 分析结果 /
    计算书 / 报告 / 截图 / 导出文件），未给出枚举取值。本枚举是这些类别的
    英文固化，一一对应，不多不少：

    - 工程文件 → `ENGINEERING_FILE`
    - 模型文件 → `MODEL_FILE`
    - 分析结果 → `ANALYSIS_RESULT`
    - 计算书 → `CALCULATION_BOOK`
    - 报告 → `REPORT`
    - 截图 → `SCREENSHOT`
    - 导出文件 → `EXPORT`

    待 P29（Artifact）落地时若规范给出正式取值，以规范为准并回改本枚举。
    """

    ENGINEERING_FILE = "ENGINEERING_FILE"
    MODEL_FILE = "MODEL_FILE"
    ANALYSIS_RESULT = "ANALYSIS_RESULT"
    CALCULATION_BOOK = "CALCULATION_BOOK"
    REPORT = "REPORT"
    SCREENSHOT = "SCREENSHOT"
    EXPORT = "EXPORT"


class AuditResult(StrEnum):
    """审计结果（`docs/07` §4.1 要求；取值推导）。

    `docs/02` §44 / §65 定义了审计记录字段（含 `result`）与 Hash Chain，
    但**未给出 `result` 的取值集合**。按最小完备原则固化为三值：

    - `SUCCESS` —— 操作成功
    - `FAILURE` —— 操作失败（含被拒绝以外的错误）
    - `DENIED` —— 因权限 / 能力 / 确认缺失而被拒绝（对应 `STRUCTAI-4000` 等）

    待 P29（Audit）落地时若规范给出正式取值，以规范为准并回改本枚举。
    """

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    DENIED = "DENIED"


# ===== `docs/07` §5.7 / `docs/02` §72 —— 角色名（P10–P13 RBAC 的类型化视图）=====


class RoleName(StrEnum):
    """默认角色名 4 条（`docs/07` §5.7；`docs/02` §72；`docs/07` §4.3 #3）。

    取值 = `roles.name` 的落库值（P07 Seed 的 `ROLE_NAMES`，`app/infrastructure/
    database/seed.py`）。本枚举是同一集合的**类型化视图**，供 P10–P13 的 RBAC /
    Effective Permission 做静态引用；落库口径仍以 Seed 为准，
    `tests/test_security_p10_p13.py` 断言两者逐一相等（防漂移）。

    ⚠️ `AI_AGENT` **不是**系统管理员（`docs/02` §6 末注）：它的有效权限
    = 用户有效权限 ∩ Agent 权限，**不得提权**（`docs/07` §5.7 / §14.3）。
    """

    SYSTEM_ADMIN = "system_admin"
    ENGINEER = "engineer"
    VIEWER = "viewer"
    AI_AGENT = "ai_agent"
