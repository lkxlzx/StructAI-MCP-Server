"""P07 Seed —— 幂等种子数据（`docs/07` §12 P07；`docs/02` §43–§46 / §69–§72 / §100–§101）。

权威来源
--------
- `docs/02` §43（Seed）—— 必须创建：1 Tenant · 1 System Admin · Engineer / Viewer /
  AI Agent；权限：`Permission` / `Role` / `RolePermission` / `User` / `UserRole` 行；
  开发环境管理员 `username = admin`。
- `docs/02` §44（Seed Admin）—— 口令**只能**来自环境变量
  `STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD`；缺失即 `RuntimeError`；数据库只写
  `password_hash`（`password_service.hash(password)`）。
- `docs/02` §45（Seed 幂等）—— `python -m app.infrastructure.database.seed` 连跑多次
  不得重复创建 Tenant / Role / Permission / User / UserRole；原则 =
  **natural key / unique constraint + upsert / get-or-create**。
- `docs/02` §46（Seed 顺序）—— Tenant → Permission → Role → RolePermission → User →
  UserRole → Project → ProjectMember，**不能反过来**。
- `docs/02` §69 / §70 / §71 / §72 —— Operation（69 条，含 2026-10-05 新增
  `DESIGN.SRC`）/ Capability / Permission（12）/ Default Roles（4）的取值清单。
- `docs/02` §100 / §101（Seed Data / Mock Software）—— Mock Software：Vendor =
  `StructAI` · Product = `Mock Engineering Software` · Version = `1.0`；以及 Mock Instance。
- `docs/07` §4.3 —— 落库的 14 张表（`docs/07` §12 P07 的内容清单所需的全部表）。
- `docs/07` §5.6 / §5.7 —— Capability Seed 与 Permission / Role Seed 的取值。
- `docs/07` §5.1 —— 每个 Tool 的 Risk / Mode（Operation 行的 `risk_level` /
  `execution_mode` 取值来源）。

幂等（`docs/02` §45）
--------------------
每张表都定义**自然键**（natural key），一律走 `select()` 命中即复用、未命中才
`INSERT`（get-or-create）：

| 表 | 自然键 |
| --- | --- |
| `tenants` | `name` |
| `permissions` | `code`（唯一约束） |
| `roles` | `(tenant_id, name)` |
| `role_permissions` | `(role_id, permission_id)` |
| `users` | `username`（**全局**唯一约束，`docs/07` §4.3 #2） |
| `user_roles` | `(user_id, role_id)` |
| `projects` | `(tenant_id, name)` |
| `project_members` | `(project_id, user_id)` |
| `capabilities` | `code`（唯一约束） |
| `operations` | `name`（唯一约束） |
| `software` | `(vendor, name)` |
| `software_products` | `(software_id, product)` |
| `software_versions` | `(product_id, version)` |
| `software_instances` | `(version_id, name)` |

因此第 2 / 第 3 次运行**不新增任何行**（`docs/02` §45）。唯一的「upsert」语义落在
管理员口令上：若库中 `password_hash` 已不能校验当前环境变量里的口令（或需要按当前
Argon2 参数重哈希），则**原地更新该行**（不新增行）—— 使库收敛到环境变量声明的期望
状态，避免「首次 Seed 之后改口令无效」的运维陷阱。其余字段一律只读不改。

⚠️ 并发边界：`roles` / `projects` / `software` / `software_products` /
`software_versions` / `software_instances` 在 `docs/07` §4.3 中**没有**唯一约束
（P04 未擅自添加），因此「先查后插」在**两个 Seed 进程同时启动**时仍可能双插。
Seed 是引导动作，按**单写者**使用（`docs/02` §45 的幂等口径即顺序重跑）；
若将来需要并发引导，必须以 Alembic 迁移为这些表补唯一约束，不得靠本模块兜底。

顺序（`docs/02` §46）
--------------------
    Tenant → Permission → Role → RolePermission → User → UserRole → Project → ProjectMember

之后追加与租户链**无依赖**的三组：Capability → Operation → Mock Software
（`software` → `software_products` → `software_versions` → `software_instances`）。
实际顺序见 `SEED_ORDER`，并被 `tests/test_seed_p07.py` 用 SQL 级录制断言。

事务（`docs/02` §16；`docs/07` §14.4）
-------------------------------------
Seed 的提交 / 回滚**一律**走 P06 的 `UnitOfWork`：本模块**不出现**任何裸
`commit` / `rollback`（由 `async with UnitOfWork(session)` 决定事务边界），
数据写入只 `flush`。唯一例外是 `--create-tables` 的 **DDL**：`Base.metadata.create_all`
在 `engine.begin()` 里执行（DDL 自带隐式提交），它只建表、不写任何业务数据，
且仅在显式开关下发生（`docs/02` §102）。

安全（`docs/07` §14.3）
----------------------
- 管理员口令只经环境变量 `STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD` 注入（**必须导出到进程
  环境**：pydantic-settings 读 `.env` 只填充 `Settings` 字段，不会写进 `os.environ`）；
  本模块**不提供**任何口令参数 / 配置字段 / 默认值，也不把口令写入日志、异常信息或任何文件。
- 库中只写 `password_hash`（Argon2id，`docs/02` §7；`docs/07` §8.3）；CLI **强制**
  `echo=False` —— SQL echo 会把绑定参数（含 `password_hash`）打进日志，而
  `docs/02` §8 明确禁止日志出现 `password` / `password_hash`。
- Mock 实例的 `credential_reference` 为 `None`：Mock Adapter 是进程内适配器，
  不需要凭据；**绝不允许**把明文密钥写进库（`docs/07` §14.3）。

命令行
------
    python -m app.infrastructure.database.seed                    # 幂等 Seed
    python -m app.infrastructure.database.seed --create-tables    # 开发 / 验收：先建表再 Seed

⚠️ `--create-tables` 是**显式**的开发 / 验收便利开关（P04 的 `Base.metadata.create_all`
入口）；`docs/02` §102 禁止**运行时自动**建表 / 改表，生产数据库必须走 Alembic 迁移
（`docs/07` §14.3：禁止启动时静默 `ALTER TABLE`）。默认**不**建表：表缺失时直接以
明确的错误信息失败。

规范之上的落地说明（只补实现手段，不改任何字段名 / 取值 / 顺序）
------------------------------------------------------------
- **口令哈希服务**：`docs/02` §44 要求 `password_service.hash(password)`，故本批同时
  落地 `app/application/security/password.py`（`docs/02` §7 指定的文件路径，
  Argon2id）；依赖 `argon2-cffi>=23.1,<26` 已登记进 `pyproject.toml`。P10 的
  `AuthenticationService` 将直接复用同一个 `PasswordService`。
- **Schema URI**：`docs/02` §14 / §86 给出形如 `structai://schema/build/column/v1`、
  `structai://schema/model/node/query/v1` 的引用（`docs/02` §38 的 output 为
  `structai://schema/model/node/result/v1`）。本批据此固化一条**确定性**规则：
  `input_schema` = `structai://schema/<operation 名小写、"." → "/">/v1`；单段名
  （`engineering_doc` 的 `NEW` / `OPEN` / …）加 Tool 前缀避免歧义，即
  `structai://schema/doc/new/v1`；`output_schema` = `input_schema` 的尾部 `/v1`
  换成 `/result/v1`。P09 Schema 落地真实 JSON Schema 时以本规则为引用口径。
- **`ai_agent` 不落静态 RolePermission**：`docs/02` §72 / `docs/07` §5.7 规定其权限
  「根据 Agent Scope 动态限制」「= 用户有效权限 ∩ Agent 权限，不得提权」。
  静态授予任何权限都会变成提权面（`docs/07` §14.3），故该角色只有 `roles` 行。
- **`operation_capabilities` 不落库**：`docs/07` §12 P08 才要求
  `operation_registry.get("BUILD.COLUMN")` 返回**完整** `OperationDefinition`
  （含 `required_capabilities`）；Operation ↔ Capability 的对应关系属 P08 Registry
  的职责，本批不预先臆造 69 条映射。
- **仓储 vs 会话**：本模块覆盖 14 张表，而 P05 最小集只有 6 个仓储；为保持单一、
  可读的幂等路径，统一用 `select()` + `session.add` / `flush()` 直连会话
  （事务边界仍由 `UnitOfWork` 决定，`docs/02` §16）。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from sqlalchemy import inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.security.password import PasswordService
from app.config.logging import configure_logging
from app.config.settings import settings
from app.domain.enums import (
    Capability,
    ExecutionMode,
    PermissionCode,
    RiskLevel,
    SoftwareConnectionState,
    SoftwareStatus,
)
from app.infrastructure.database.base import Base
from app.infrastructure.database.models import (
    CapabilityORM,
    OperationORM,
    PermissionORM,
    ProjectMemberORM,
    ProjectORM,
    RoleORM,
    RolePermissionORM,
    SoftwareInstanceORM,
    SoftwareORM,
    SoftwareProductORM,
    SoftwareVersionORM,
    TenantORM,
    UserORM,
    UserRoleORM,
)
from app.infrastructure.database.session import create_engine, create_session_factory
from app.infrastructure.database.unit_of_work import UnitOfWork

__all__ = [
    "ADMIN_PASSWORD_ENV",
    "ADMIN_USERNAME",
    "DEFAULT_PROJECT_NAME",
    "DEFAULT_TENANT_NAME",
    "MOCK_INSTANCE_NAME",
    "MOCK_PRODUCT",
    "MOCK_VENDOR",
    "MOCK_VERSION",
    "OPERATIONS",
    "ROLE_NAMES",
    "ROLE_PERMISSIONS",
    "SEED_ORDER",
    "SeedReport",
    "input_schema_uri",
    "main",
    "output_schema_uri",
    "seed",
]

logger = logging.getLogger("structai.seed")

# ===== 环境变量（`docs/02` §43 / §44）=====

ADMIN_PASSWORD_ENV: Final[str] = "STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD"
"""管理员引导口令的**唯一**注入通道（`docs/02` §43 / §44）。

⚠️ 规范把变量名固定为 `STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD`，它不是 `Settings` 字段名的
大写形式（`docs/08` §4 的命名约定），因此本模块**直接读环境变量**而**不**新增
`Settings` 字段 —— 否则变量名会被迫改成 `BOOTSTRAP_ADMIN_PASSWORD`，与规范不符。
该变量已登记在 `.env.example`（值一律留空，绝不入库）。
"""

# ===== 种子内容（`docs/02` §43 / §71 / §72；`docs/07` §5.7）=====

DEFAULT_TENANT_NAME: Final[str] = "default"
"""默认租户名（`docs/02` §100：`default tenant`）。"""

ADMIN_USERNAME: Final[str] = "admin"
"""开发环境管理员用户名（`docs/02` §43）。"""

DEFAULT_PROJECT_NAME: Final[str] = "default"
"""默认项目名（`docs/02` §46 的 Seed 顺序要求 Project / ProjectMember 落库）。"""

SYSTEM_ADMIN_ROLE: Final[str] = "system_admin"
ENGINEER_ROLE: Final[str] = "engineer"
VIEWER_ROLE: Final[str] = "viewer"
AI_AGENT_ROLE: Final[str] = "ai_agent"

ROLE_NAMES: Final[tuple[str, ...]] = (
    SYSTEM_ADMIN_ROLE,
    ENGINEER_ROLE,
    VIEWER_ROLE,
    AI_AGENT_ROLE,
)
"""默认角色 4 条（`docs/02` §72；`docs/07` §5.7 / §4.3 #3）。"""

ROLE_PERMISSIONS: Final[Mapping[str, tuple[PermissionCode, ...]]] = {
    SYSTEM_ADMIN_ROLE: tuple(PermissionCode),
    ENGINEER_ROLE: (
        PermissionCode.MODEL_READ,
        PermissionCode.MODEL_WRITE,
        PermissionCode.MODEL_DELETE,
        PermissionCode.ANALYSIS_EXECUTE,
        PermissionCode.DESIGN_EXECUTE,
        PermissionCode.DESIGN_MODIFY,
        PermissionCode.RESULT_READ,
        PermissionCode.DOCUMENT_READ,
        PermissionCode.DOCUMENT_WRITE,
    ),
    VIEWER_ROLE: (
        PermissionCode.MODEL_READ,
        PermissionCode.RESULT_READ,
        PermissionCode.DOCUMENT_READ,
    ),
    AI_AGENT_ROLE: (),
}
"""角色 → 权限映射（`docs/02` §72；`docs/07` §5.7）。

- `system_admin` → **ALL**（12 条全量）。
- `engineer` → 9 条（`MODEL_READ/WRITE/DELETE` · `ANALYSIS_EXECUTE` ·
  `DESIGN_EXECUTE/MODIFY` · `RESULT_READ` · `DOCUMENT_READ/WRITE`）。
- `viewer` → 3 条（`MODEL_READ` · `RESULT_READ` · `DOCUMENT_READ`）。
- `ai_agent` → **空**：权限按 Agent Scope 动态求交，不得静态授予（不得提权）。
"""

MOCK_VENDOR: Final[str] = "StructAI"
MOCK_PRODUCT: Final[str] = "Mock Engineering Software"
MOCK_VERSION: Final[str] = "1.0"
MOCK_SOFTWARE_NAME: Final[str] = MOCK_PRODUCT
MOCK_INSTANCE_NAME: Final[str] = "Mock Instance"
"""Mock 软件 / 实例（`docs/02` §100 / §101）。"""

TOOL_PROFILES: Final[Mapping[str, tuple[RiskLevel, ExecutionMode]]] = {
    "engineering_doc": (RiskLevel.MEDIUM, ExecutionMode.SYNC),
    "engineering_model_query": (RiskLevel.LOW, ExecutionMode.SYNC),
    "engineering_model_assign": (RiskLevel.MEDIUM, ExecutionMode.SYNC),
    "engineering_model_delete": (RiskLevel.HIGH, ExecutionMode.ASYNC),
    "engineering_model_build": (RiskLevel.HIGH, ExecutionMode.ASYNC),
    "engineering_view": (RiskLevel.LOW, ExecutionMode.SYNC),
    "engineering_result": (RiskLevel.LOW, ExecutionMode.SYNC),
    "engineering_design": (RiskLevel.HIGH, ExecutionMode.ASYNC),
    "engineering_analysis": (RiskLevel.HIGH, ExecutionMode.ASYNC),
}
"""Tool → (Risk, Mode)（`docs/07` §5.1 的 Tool 总表）。

`engineering_model_assign` 在总表中记为 `SYNC/ASYNC`（按 Operation 取值）；本批统一取
`SYNC`（单次小写入），待 P08 Registry 按 Operation 细化 —— 该细化不改本表口径，
只影响 `operations` 行的取值。
"""

SEED_ORDER: Final[tuple[str, ...]] = (
    "tenants",
    "permissions",
    "roles",
    "role_permissions",
    "users",
    "user_roles",
    "projects",
    "project_members",
    "capabilities",
    "operations",
    "software",
    "software_products",
    "software_versions",
    "software_instances",
)
"""实际写入顺序（`docs/02` §46 + 追加的无依赖三组）。

前 8 张即 `docs/02` §46 的强制顺序（不得反过来）；后 6 张与租户链无依赖，
故置于其后。`tests/test_seed_p07.py` 以 SQL 级录制断言前 8 张的相对顺序。
"""

_SCHEMA_URI_PREFIX: Final[str] = "structai://schema/"

OPERATIONS: Final[tuple[tuple[str, str], ...]] = (
    # `engineering_doc`（6）
    ("engineering_doc", "NEW"),
    ("engineering_doc", "OPEN"),
    ("engineering_doc", "SAVE"),
    ("engineering_doc", "SAVE_AS"),
    ("engineering_doc", "CLOSE"),
    ("engineering_doc", "INFO"),
    # `engineering_model_query`（8）
    ("engineering_model_query", "MODEL.QUERY"),
    ("engineering_model_query", "MODEL.NODE.QUERY"),
    ("engineering_model_query", "MODEL.ELEMENT.QUERY"),
    ("engineering_model_query", "MODEL.MATERIAL.QUERY"),
    ("engineering_model_query", "MODEL.SECTION.QUERY"),
    ("engineering_model_query", "MODEL.BOUNDARY.QUERY"),
    ("engineering_model_query", "MODEL.LOAD.QUERY"),
    ("engineering_model_query", "MODEL.GROUP.QUERY"),
    # `engineering_model_assign`（8）
    ("engineering_model_assign", "MODEL.NODE.CREATE"),
    ("engineering_model_assign", "MODEL.NODE.UPDATE"),
    ("engineering_model_assign", "MODEL.ELEMENT.CREATE"),
    ("engineering_model_assign", "MODEL.ELEMENT.UPDATE"),
    ("engineering_model_assign", "MODEL.MATERIAL.ASSIGN"),
    ("engineering_model_assign", "MODEL.SECTION.ASSIGN"),
    ("engineering_model_assign", "MODEL.BOUNDARY.ASSIGN"),
    ("engineering_model_assign", "MODEL.LOAD.ASSIGN"),
    # `engineering_model_delete`（7）
    ("engineering_model_delete", "MODEL.NODE.DELETE"),
    ("engineering_model_delete", "MODEL.ELEMENT.DELETE"),
    ("engineering_model_delete", "MODEL.LOAD.DELETE"),
    ("engineering_model_delete", "MODEL.BOUNDARY.DELETE"),
    ("engineering_model_delete", "MODEL.GROUP.DELETE"),
    ("engineering_model_delete", "MODEL.MATERIAL.DELETE"),
    ("engineering_model_delete", "MODEL.SECTION.DELETE"),
    # `engineering_model_build`（14）
    ("engineering_model_build", "BUILD.NODE_GRID"),
    ("engineering_model_build", "BUILD.BEAM"),
    ("engineering_model_build", "BUILD.COLUMN"),
    ("engineering_model_build", "BUILD.FRAME"),
    ("engineering_model_build", "BUILD.TRUSS"),
    ("engineering_model_build", "BUILD.SLAB"),
    ("engineering_model_build", "BUILD.WALL"),
    ("engineering_model_build", "BUILD.FOUNDATION"),
    ("engineering_model_build", "BUILD.STEEL_FRAME"),
    ("engineering_model_build", "MODEL.COPY"),
    ("engineering_model_build", "MODEL.MOVE"),
    ("engineering_model_build", "MODEL.MIRROR"),
    ("engineering_model_build", "MODEL.PATTERN"),
    ("engineering_model_build", "MODEL.GENERATE_GRID"),
    # `engineering_view`（7）
    ("engineering_view", "VIEW.MODEL"),
    ("engineering_view", "VIEW.DEFORMED_MODEL"),
    ("engineering_view", "VIEW.REACTION"),
    ("engineering_view", "VIEW.DISPLACEMENT"),
    ("engineering_view", "VIEW.STRESS"),
    ("engineering_view", "VIEW.FORCE"),
    ("engineering_view", "VIEW.MODE_SHAPE"),
    # `engineering_result`（6）
    ("engineering_result", "RESULT.NODE.DISPLACEMENT"),
    ("engineering_result", "RESULT.NODE.REACTION"),
    ("engineering_result", "RESULT.ELEMENT.FORCE"),
    ("engineering_result", "RESULT.ELEMENT.STRESS"),
    ("engineering_result", "RESULT.MODE.SHAPE"),
    ("engineering_result", "RESULT.ANALYSIS.SUMMARY"),
    # `engineering_design`（6，含 2026-10-05 新增 `DESIGN.SRC`）
    ("engineering_design", "DESIGN.STEEL"),
    ("engineering_design", "DESIGN.CONCRETE"),
    ("engineering_design", "DESIGN.SRC"),
    ("engineering_design", "DESIGN.FOUNDATION"),
    ("engineering_design", "DESIGN.CODE_CHECK"),
    ("engineering_design", "DESIGN.OPTIMIZE"),
    # `engineering_analysis`（7）
    ("engineering_analysis", "ANALYSIS.STATIC"),
    ("engineering_analysis", "ANALYSIS.MODAL"),
    ("engineering_analysis", "ANALYSIS.SEISMIC"),
    ("engineering_analysis", "ANALYSIS.SPECTRUM"),
    ("engineering_analysis", "ANALYSIS.BUCKLING"),
    ("engineering_analysis", "ANALYSIS.TIME_HISTORY"),
    ("engineering_analysis", "ANALYSIS.NONLINEAR"),
)
"""Operation 全量清单 69 条（`docs/02` §69；`docs/07` §5.1）。

每项为 `(tool, operation_name)`；数量 6+8+8+7+14+7+6+6+7 = **69**。
"""


# ===== 结果报告 =====


@dataclass(slots=True)
class SeedReport:
    """一次 Seed 的结果（`docs/02` §45：第 2 / 第 3 次运行必须是「零新增」）。"""

    created: dict[str, int] = field(default_factory=dict)
    """表名 → 本次**新增**行数；幂等重跑时为空（或全 0）。"""

    updated: dict[str, int] = field(default_factory=dict)
    """表名 → 本次**原地更新**行数（当前只可能是 `users` 的口令收敛）。"""

    @property
    def total_created(self) -> int:
        """本次新增行数合计。"""
        return sum(self.created.values())

    @property
    def total_updated(self) -> int:
        """本次原地更新行数合计。"""
        return sum(self.updated.values())

    @property
    def is_noop(self) -> bool:
        """是否「零新增且零更新」（幂等重跑的期望结果，`docs/02` §45）。"""
        return self.total_created == 0 and self.total_updated == 0

    def summary(self) -> str:
        """单行摘要（**绝不含任何 secret**，`docs/07` §14.3）。"""
        created = ", ".join(f"{table}={count}" for table, count in self._ordered(self.created))
        updated = ", ".join(f"{table}={count}" for table, count in self._ordered(self.updated))
        return (
            f"created {self.total_created} row(s) [{created or '-'}]; "
            f"updated {self.total_updated} row(s) [{updated or '-'}]"
        )

    @staticmethod
    def _ordered(counts: Mapping[str, int]) -> list[tuple[str, int]]:
        """按 `SEED_ORDER` 排序，未登记的表名追加在后 —— 输出确定性。"""
        known = [(table, counts[table]) for table in SEED_ORDER if table in counts]
        extra = sorted((table, count) for table, count in counts.items() if table not in SEED_ORDER)
        return known + extra


# ===== Schema URI（`docs/02` §14 / §38 / §86）=====


def input_schema_uri(tool: str, operation: str) -> str:
    """构造 Operation 的 `input_schema` 引用（`docs/02` §14 / §86）。

    规则（本批固化，见模块 docstring）：`structai://schema/<operation 名小写、"." → "/">/v1`；
    单段名（`engineering_doc` 的 `NEW` / `OPEN` / …）加 Tool 前缀避免歧义。

    Args:
        tool: Tool 名（如 `engineering_model_build`）。
        operation: Operation 名（如 `BUILD.COLUMN`）。

    Returns:
        形如 `structai://schema/build/column/v1` 的引用字符串。
    """
    if "." in operation:
        slug = operation.lower().replace(".", "/")
    else:
        slug = f"{tool.removeprefix('engineering_').replace('_', '/')}/{operation.lower()}"
    return f"{_SCHEMA_URI_PREFIX}{slug}/v1"


def output_schema_uri(input_schema: str) -> str:
    """由 `input_schema` 派生 `output_schema`（`docs/02` §86 的 `…/result/v1`）。

    Args:
        input_schema: `input_schema_uri` 的产物。

    Returns:
        把尾部 `/v1` 换成 `/result/v1` 的引用字符串。
    """
    return f"{input_schema.removesuffix('/v1')}/result/v1"


# ===== 执行体 =====


class _Seeder:
    """单次 Seed 的执行体。

    只 `flush`，**绝不** `commit` / `rollback`（`docs/07` §14.4：事务边界归 UnitOfWork）。
    """

    def __init__(self, session: AsyncSession, password_service: PasswordService) -> None:
        """绑定会话与口令服务（两者都由 `seed()` 注入）。"""
        self._session = session
        self._password_service = password_service
        self.report = SeedReport()

    # ===== 通用：natural key + get-or-create（`docs/02` §45）=====

    async def _find(self, model: type[Any], *, natural_key: Mapping[str, object]) -> Any | None:
        """按自然键读取一行（只读，不建表、不改表）。"""
        statement = select(model).where(
            *(getattr(model, column) == value for column, value in natural_key.items())
        )
        return (await self._session.execute(statement)).scalars().first()

    async def _get_or_create(
        self,
        model: type[Any],
        *,
        table: str,
        natural_key: Mapping[str, object],
        values: Mapping[str, object] | None = None,
    ) -> tuple[Any, bool]:
        """按自然键 get-or-create（`docs/02` §45）。

        Args:
            model: ORM 类。
            table: 表名（仅用于报告计数）。
            natural_key: 自然键（列名 → 值）；命中即复用，**不**改任何字段。
            values: 仅**新建**时写入的附加列。

        Returns:
            `(实体, 是否本次新增)`。
        """
        existing = await self._find(model, natural_key=natural_key)
        if existing is not None:
            return existing, False

        entity = model(**natural_key, **(values or {}))
        self._session.add(entity)
        await self._session.flush()
        self._mark_created(table)
        return entity, True

    def _mark_created(self, table: str) -> None:
        """记录一次新增（`SeedReport.created`）。"""
        self.report.created[table] = self.report.created.get(table, 0) + 1

    def _mark_updated(self, table: str) -> None:
        """记录一次原地更新（`SeedReport.updated`）。"""
        self.report.updated[table] = self.report.updated.get(table, 0) + 1

    # ===== 编排（`docs/02` §46 的顺序）=====

    async def run(self, admin_password: str) -> SeedReport:
        """按 `docs/02` §46 的顺序执行一次完整 Seed。

        Args:
            admin_password: 来自环境变量的管理员引导口令（**不缓存、不记录**）。

        Returns:
            本次运行的 `SeedReport`。
        """
        tenant = await self._seed_tenant()
        permissions = await self._seed_permissions()
        roles = await self._seed_roles(tenant)
        await self._seed_role_permissions(roles, permissions)
        admin = await self._seed_admin(tenant, admin_password)
        await self._seed_user_roles(admin, roles)
        project = await self._seed_project(tenant)
        await self._seed_project_members(project, admin)
        await self._seed_capabilities()
        await self._seed_operations()
        await self._seed_mock_software()
        return self.report

    # ===== ① Tenant =====

    async def _seed_tenant(self) -> Any:
        """① Tenant：默认租户（`docs/02` §43 / §46；`docs/07` §4.3 #1）。"""
        tenant, _ = await self._get_or_create(
            TenantORM,
            table="tenants",
            natural_key={"name": DEFAULT_TENANT_NAME},
        )
        return tenant

    # ===== ② Permission（12）=====

    async def _seed_permissions(self) -> dict[PermissionCode, Any]:
        """② Permission 12 条（`docs/02` §71；`docs/07` §5.7）。"""
        permissions: dict[PermissionCode, Any] = {}
        for code in PermissionCode:
            permission, _ = await self._get_or_create(
                PermissionORM,
                table="permissions",
                natural_key={"code": code.value},
            )
            permissions[code] = permission
        return permissions

    # ===== ③ Role（4）=====

    async def _seed_roles(self, tenant: Any) -> dict[str, Any]:
        """③ Role 4 条：`system_admin` / `engineer` / `viewer` / `ai_agent`（`docs/02` §72）。"""
        roles: dict[str, Any] = {}
        for name in ROLE_NAMES:
            role, _ = await self._get_or_create(
                RoleORM,
                table="roles",
                natural_key={"tenant_id": tenant.id, "name": name},
            )
            roles[name] = role
        return roles

    # ===== ④ RolePermission =====

    async def _seed_role_permissions(
        self,
        roles: Mapping[str, Any],
        permissions: Mapping[PermissionCode, Any],
    ) -> None:
        """④ RolePermission：按 `ROLE_PERMISSIONS` 建关联（`docs/02` §72）。

        `ai_agent` 的权限集合为空 —— 其有效权限按 Agent Scope 动态求交，
        静态授予任何权限都会变成提权面（`docs/07` §5.7 / §14.3）。
        """
        for role_name, codes in ROLE_PERMISSIONS.items():
            for code in codes:
                await self._get_or_create(
                    RolePermissionORM,
                    table="role_permissions",
                    natural_key={
                        "role_id": roles[role_name].id,
                        "permission_id": permissions[code].id,
                    },
                )

    # ===== ⑤ User（admin）=====

    async def _seed_admin(self, tenant: Any, admin_password: str) -> Any:
        """⑤ User：`username = admin`（`docs/02` §43 / §44）。

        - 自然键 = `username`（`users.username` 是**全局**唯一约束，`docs/07` §4.3 #2）：
          若改用 `(tenant_id, username)` 查询，则当库中已存在**其他租户**下的同名
          `admin` 时会查不到而插入 → 撞全局唯一约束、整次 Seed 回滚且无法自愈。
        - 新建：只写 `password_hash`（Argon2id），明文口令不落库、不落日志。
        - 已存在：口令收敛（upsert）—— 仅当库中哈希无法校验当前口令、或需要按当前
          Argon2 参数重哈希时，**原地更新**该行（不新增行，`docs/02` §45）。
          其余字段（`is_active` / `locked` / `failed_login_count`）一律不改，
          以免 Seed 覆盖运行期的认证状态。
        """
        existing = await self._find(UserORM, natural_key={"username": ADMIN_USERNAME})
        if existing is not None:
            current_hash = str(existing.password_hash)
            stale = not self._password_service.verify(current_hash, admin_password)
            if stale or self._password_service.needs_rehash(current_hash):
                existing.password_hash = self._password_service.hash(admin_password)
                await self._session.flush()
                self._mark_updated("users")
            return existing

        admin = UserORM(
            tenant_id=tenant.id,
            username=ADMIN_USERNAME,
            password_hash=self._password_service.hash(admin_password),
            is_active=True,
            locked=False,
            failed_login_count=0,
        )
        self._session.add(admin)
        await self._session.flush()
        self._mark_created("users")
        return admin

    # ===== ⑥ UserRole =====

    async def _seed_user_roles(self, admin: Any, roles: Mapping[str, Any]) -> None:
        """⑥ UserRole：`admin` ↔ `system_admin`（`docs/02` §46）。"""
        await self._get_or_create(
            UserRoleORM,
            table="user_roles",
            natural_key={"user_id": admin.id, "role_id": roles[SYSTEM_ADMIN_ROLE].id},
        )

    # ===== ⑦ Project =====

    async def _seed_project(self, tenant: Any) -> Any:
        """⑦ Project：默认项目（`docs/02` §46；`docs/07` §4.3 #8）。"""
        project, _ = await self._get_or_create(
            ProjectORM,
            table="projects",
            natural_key={"tenant_id": tenant.id, "name": DEFAULT_PROJECT_NAME},
        )
        return project

    # ===== ⑧ ProjectMember =====

    async def _seed_project_members(self, project: Any, admin: Any) -> None:
        """⑧ ProjectMember：`admin` 以 `system_admin` 加入默认项目（`docs/02` §46）。"""
        await self._get_or_create(
            ProjectMemberORM,
            table="project_members",
            natural_key={"project_id": project.id, "user_id": admin.id},
            values={"role": SYSTEM_ADMIN_ROLE},
        )

    # ===== Capability =====

    async def _seed_capabilities(self) -> None:
        """Capability 全量（`docs/02` §70；`docs/07` §5.6）。

        取值 = `app.domain.enums.Capability` —— P03 冻结的类型化视图
        （`docs/02` §70 与 `docs/07` §5.6 的并集，且**不含**任何厂商名，
        `docs/07` §14.2）。`docs/07` §5.6 的 `VIEW.*` 是通配写法、不是能力码，
        故不作为 `capabilities` 行。
        """
        for capability in Capability:
            await self._get_or_create(
                CapabilityORM,
                table="capabilities",
                natural_key={"code": capability.value},
            )

    # ===== Operation =====

    async def _seed_operations(self) -> None:
        """Operation 69 条（`docs/02` §69；`docs/07` §5.1）。

        `risk_level` / `execution_mode` 取 `TOOL_PROFILES`（Tool 总表），
        `input_schema` / `output_schema` 取 `docs/02` §14 的 Schema URI 口径。
        Operation ↔ Capability 的对应关系属 P08 Registry，不在本批落库。
        """
        for tool, name in OPERATIONS:
            risk_level, execution_mode = TOOL_PROFILES[tool]
            input_schema = input_schema_uri(tool, name)
            await self._get_or_create(
                OperationORM,
                table="operations",
                natural_key={"name": name},
                values={
                    "tool": tool,
                    "risk_level": risk_level.value,
                    "execution_mode": execution_mode.value,
                    "input_schema": input_schema,
                    "output_schema": output_schema_uri(input_schema),
                },
            )

    # ===== Mock Software / Product / Version / Instance =====

    async def _seed_mock_software(self) -> None:
        """Mock Software 链（`docs/02` §100 / §101）。

        Vendor = `StructAI` · Product = `Mock Engineering Software` · Version = `1.0`。

        - `software.status` = `ENABLED`：Core Alpha 唯一可用的软件注册项。
        - `software_instances.status` = `DISCONNECTED`：实例的**初始**状态；
          连接 / 健康状态由 AdapterManager 在运行期驱动（`docs/02` §19），
          Seed 不谎报 `CONNECTED`。
        - `credential_reference` = `None`：Mock Adapter 是进程内适配器，不需要凭据；
          凭据值只能经运行环境注入，绝不入库（`docs/07` §14.3）。
        """
        software, _ = await self._get_or_create(
            SoftwareORM,
            table="software",
            natural_key={"vendor": MOCK_VENDOR, "name": MOCK_SOFTWARE_NAME},
            values={"status": SoftwareStatus.ENABLED.value},
        )
        product, _ = await self._get_or_create(
            SoftwareProductORM,
            table="software_products",
            natural_key={"software_id": software.id, "product": MOCK_PRODUCT},
        )
        version, _ = await self._get_or_create(
            SoftwareVersionORM,
            table="software_versions",
            natural_key={"product_id": product.id, "version": MOCK_VERSION},
        )
        await self._get_or_create(
            SoftwareInstanceORM,
            table="software_instances",
            natural_key={"version_id": version.id, "name": MOCK_INSTANCE_NAME},
            values={
                "endpoint": None,
                "status": SoftwareConnectionState.DISCONNECTED.value,
                "credential_reference": None,
            },
        )


# ===== 公开入口 =====


def _require_admin_password() -> str:
    """从环境变量读取管理员引导口令（`docs/02` §43 / §44）。

    Returns:
        环境变量 `STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD` 的值。

    Raises:
        RuntimeError: 变量缺失或为空（`docs/02` §44 的硬性要求：缺失即拒绝 Seed）。

    ⚠️ 返回值只用于**当次哈希**，不缓存、不落日志、不写入任何文件（`docs/07` §14.3）。
    """
    password = os.environ.get(ADMIN_PASSWORD_ENV)
    if not password:
        raise RuntimeError(f"{ADMIN_PASSWORD_ENV} is required")
    return password


async def seed(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    password_service: PasswordService | None = None,
) -> SeedReport:
    """幂等 Seed（`docs/02` §43–§46；`docs/07` §12 P07）。

    Args:
        session_factory: `create_session_factory(engine)` 的产物（P04）。
        password_service: 可选注入（默认 `PasswordService()`，`docs/02` §7）。

    Returns:
        `SeedReport`：本次新增 / 原地更新的行数；幂等重跑应为**零新增**
        （`docs/02` §45）。

    Raises:
        RuntimeError: 环境变量 `STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD` 缺失（`docs/02` §44）。
            该检查在任何数据库读写**之前**完成 —— 口令缺失时库中不会留下半成品数据。

    事务（`docs/02` §16；`docs/07` §14.4）：整次 Seed 在**一个** `UnitOfWork` 内完成，
    正常退出 → `commit`；任何异常 → `rollback`（不会留下部分数据）。
    """
    admin_password = _require_admin_password()
    service = password_service if password_service is not None else PasswordService()

    async with session_factory() as session:
        async with UnitOfWork(session):
            report = await _Seeder(session, service).run(admin_password)

    logger.info("seed completed: %s", report.summary())
    return report


# ===== 命令行 =====


def _build_parser() -> argparse.ArgumentParser:
    """构造 Seed CLI 的参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="python -m app.infrastructure.database.seed",
        description=(
            "P07 幂等 Seed（docs/02 §43–§46 / §69–§72 / §100–§101）；"
            f"管理员口令只经环境变量 {ADMIN_PASSWORD_ENV} 注入。"
        ),
    )
    parser.add_argument(
        "--create-tables",
        action="store_true",
        help=(
            "开发 / 验收用：Seed 前按 ORM 元数据建表（Base.metadata.create_all）。"
            "默认关闭；生产数据库必须走 Alembic 迁移（docs/02 §102）。"
        ),
    )
    return parser


async def _schema_present(engine: AsyncEngine) -> bool:
    """库中是否已有 Seed 需要的**全部** 14 张表（只读检查：不建表、不改表）。

    只查 `tenants` 是不够的：半迁移的库（有 `tenants`、缺其它表）会让 Seed 中途
    撞 `OperationalError`；这里一次性给出「库未就绪」的明确判断（`docs/02` §102）。
    """
    async with engine.connect() as connection:
        table_names = await connection.run_sync(
            lambda sync_connection: set(inspect(sync_connection).get_table_names())
        )
    return set(SEED_ORDER) <= table_names


async def async_main(argv: Sequence[str] | None = None) -> int:
    """异步主流程：建表（可选）→ 幂等 Seed → 输出摘要。"""
    args = _build_parser().parse_args(argv)
    configure_logging(settings.log_level)

    # ⚠️ 强制 echo=False：SQL echo 会打印绑定参数，包含 users.password_hash，
    #    而 docs/02 §8 禁止日志出现 password / password_hash（docs/07 §14.3）。
    engine = create_engine(settings.database_url, echo=False)
    try:
        if args.create_tables:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            logger.warning(
                "schema created via Base.metadata.create_all (--create-tables; "
                "dev/acceptance only — production must use Alembic)"
            )
        elif not await _schema_present(engine):
            raise RuntimeError(
                "database schema is incomplete (missing table(s) from the 24-table set); "
                "run Alembic migrations, or use --create-tables on a development database"
            )

        report = await seed(create_session_factory(engine))
    finally:
        await engine.dispose()

    print(f"seed ok: {report.summary()}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """同步入口，返回进程退出码（成功 `0`；口令缺失 / 库未就绪 / 数据库错误 `2`）。

    ⚠️ 失败信息只含变量名、表名与数据库错误摘要，**绝不含**任何 secret
    （`docs/07` §14.3）；`SQLAlchemyError` 不打印完整 traceback，避免把绑定参数
    之类的内容带进日志。
    """
    try:
        return asyncio.run(async_main(argv))
    except RuntimeError as error:
        print(f"seed failed: {error}", file=sys.stderr)
        return 2
    except SQLAlchemyError as error:
        print(f"seed failed: database error: {type(error).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
