"""Registry · OperationRegistry —— 运行时操作注册表（`docs/07` §12 P08；`docs/02` §11 / §21 / §28）。

权威来源
--------
- `docs/07` §4.2 / `docs/02` §11（`source7` §11 · `impl` §10 · `py` §10）—— `OperationDefinition`
  的 **12 字段**。P03 已把它冻结在 `app.domain.protocols.OperationDefinition`，本批**只消费**，
  不新造第二个定义类。
- `docs/07` §12 P08 / `docs/02` §113 —— 门槛：`operation_registry.get("BUILD.COLUMN")`
  返回**完整**定义；69 个 Operation **全部**可 `get`。
- `docs/02` §28（Core Operation Registry）—— Database Registry + Runtime Registry：
  数据库保存 operation / capability / software / …，运行时保存 `OperationDefinition`。
- `docs/07` §4.3 #17 / `docs/02` §23 —— `operations` 表**只**持久化 6 个字段
  （`name` / `tool` / `risk_level` / `execution_mode` / `input_schema` / `output_schema`），
  由 P07 Seed 落库。
- `docs/02` §27 / §31 —— `operation_capabilities`（Operation ↔ Capability）关系表；
  P07 明确把它留给 P08（`seed.py` 模块 docstring「规范之上的落地说明」）。
- `docs/07` §14.4 —— Registry 校验失败 → Server MUST NOT become READY。

装配口径（六字段来自 DB，六字段由本 Registry 补齐）
--------------------------------------------------
| `OperationDefinition` 字段 | 来源 |
| --- | --- |
| `name` / `tool` / `risk_level` / `execution_mode` / `input_schema` / `output_schema` | **P07 落库的 `operations` 表**（`docs/02` §23 的持久化口径） |
| `required_permissions` / `required_capabilities` / `transactional` / `rollback_supported` / `dry_run_supported` / `recovery_policy` | 本模块的 `OPERATION_PROFILES` —— 逐条带 `anchor`，指回具体章节 |

补齐规则（逐条可指回章节；`OperationProfile.anchor` 即该条的出处）
------------------------------------------------------------------
1. **`required_permissions`** ← `docs/07` §5.1（Tool 总表）。
   总表里的 `/` 表示「按 Operation 二选一」—— 依据是同一张表里 `engineering_view` 的
   `MODEL_READ/RESULT_READ`（`docs/07` §6.6 把 `VIEW.MODEL` 归为模型视图、其余归为结果视图）：
   `engineering_doc` 的 `DOCUMENT_READ/WRITE` → 只读的 `INFO` 取 `DOCUMENT_READ`，其余取
   `DOCUMENT_WRITE`；`engineering_view` → `VIEW.MODEL` 取 `MODEL_READ`，其余取 `RESULT_READ`。
   `engineering_design` 的 `DESIGN_EXECUTE(+DESIGN_MODIFY)`：`+` 是条件权限，按 `docs/07` §5.4
   （确认矩阵：「`DESIGN.OPTIMIZE` + `apply=true`」）与 §6.8（`DESIGN.OPTIMIZE` 是自研循环，
   会「改 `DB.SECT`」→ 写模型）只挂在 `DESIGN.OPTIMIZE` 上；其余 5 条设计 Operation 取
   `DESIGN_EXECUTE`。
2. **`required_capabilities`** ← `docs/02` §31（Operation → Capability 示例）＋ §5.5 / §87
   （语义示例）＋ `docs/07` §5.6（能力码集合）。取值**只能**是 `capabilities` 表已登记的能力码
   （41 条，`docs/02` §70 ＋ `docs/07` §5.6），因此：
   - 能力码族里有对应动作码（如 `MODEL.NODE.DELETE`）→ 用动作码；
   - 族里**没有**该动作码时（词表缺口）→ 取同族**最接近**的能力码，并按缺口登记
     （见 `docs/07` §16 R17）：`MODEL.BOUNDARY.DELETE` / `MODEL.MATERIAL.DELETE` /
     `MODEL.SECTION.DELETE` → 同族 `…WRITE`；`MODEL.GROUP.DELETE` → `MODEL.GROUP.READ`
     （族里只有 READ）。
   - `docs/07` §5.6 的 `VIEW.*` 是**通配写法**，不是能力码（P03 已在 `Capability` 枚举注明）
     → 视图类 Operation 取 `MODEL.READ` / `RESULT.*`。
   - `BUILD.*` 取 `docs/02` §86 的 `BUILD.COLUMN` 示例口径
     （`MODEL.NODE.WRITE` ＋ `MODEL.ELEMENT.WRITE`），`BUILD.NODE_GRID` 只取
     `MODEL.NODE.WRITE`（`docs/07` §6.5：仅 `DB.NODE`）；§6.5 组合端点里的
     `DB.MATL` / `DB.SECT` / `DB.CONS` 属 **Adapter 编排**（P122）的端点组合，不进入
     `OperationDefinition` 的能力声明 —— 差异登记见 `docs/07` §16 R16。
   - `RESULT.ANALYSIS.SUMMARY` 是 `docs/07` §6.7 的**通用入口**（需 `TABLE_TYPE` 选具体表）
     → 登记 RESULT 域全部 5 个能力码，运行期由 CapabilityResolver 按 `TABLE_TYPE` 收窄（P14）。
3. **`transactional`** ← `docs/07` §6.10（映射覆盖率小结的「映射性质」列）＋ §6.5。
   §6.10 标注为 **🟡 组合 / 🟢 组合+自研** 的三类（`engineering_model_build` 14 ·
   `engineering_result` 6 · `engineering_design` 6 = **26** 条）取 `True`；
   标注为 **✅ 直接** 的六类（doc 6 · query 8 · assign 8 · delete 7 · view 7 · analysis 7
   = **43** 条）取 `False`。§6.5 对 Build 类的原话即「在 Core 中以**组合 Operation** 实现
   （`OperationDefinition.transactional=true`）」。26 + 43 = **69**。
4. **`rollback_supported`** ← 与 `transactional` 同值：`docs/07` §6.5 明示组合 Operation
   「失败时按 §5.4 的事务回滚优先级处理」，即存在明确回滚路径（Native Transaction →
   Snapshot/Restore → Compensating Actions → Best Effort）；单端点 Operation 的原子性由
   软件侧原生事务保证，Core **不**额外声明可回滚。
5. **`dry_run_supported`** ← `docs/07` §5.4 的 Dry Run 矩阵：
   `build`=必须 → `True`；`assign` / `delete` / `design` / `analysis`=推荐 → `True`；
   `query` / `view` / `result`=无意义 → `False`。矩阵**未列举**的 `engineering_doc`
   取 `False`（未规定即不声明支持）。
6. **`recovery_policy`** ← `docs/02` §45（Recovery Policy 分类：
   `SAFE_RETRY` / `STATE_RECONCILE` / `MANUAL_REVIEW` / `FAIL`，并明确「最终由
   `OperationDefinition` 指定」）：
   - 只读类（query / view / result / `INFO`）→ `SAFE_RETRY`（§45 示例 `MODEL.NODE.QUERY`）；
   - 改变软件侧状态的类（doc 写 / assign / delete / build / analysis / design 的构件设计）
     → `STATE_RECONCILE`（§45 示例 `BUILD.COLUMN`、`MODEL.DELETE`）；
   - `DESIGN.OPTIMIZE` → `MANUAL_REVIEW`（§45 示例）。
   `FAIL` 是 `OperationDefinition.recovery_policy` 的**默认值**（`docs/02` §11）；
   本批 69 条**全部**有明确归类，故无一条落 `FAIL` —— 未登记项会被装配校验直接拒绝
   （见 `_validate`），不会静默退化为默认值。

⚠️ 已登记的规范内部冲突（本批裁决，见 `docs/07` §16 R15–R17）
------------------------------------------------------------
- **R15**：`docs/02` §86 的示例写作 `recovery_policy="RETRY_SAFE"`，而 §45 的**分类词表**是
  `SAFE_RETRY` / `STATE_RECONCILE` / `MANUAL_REVIEW` / `FAIL`，且 §45 对 `BUILD.COLUMN`
  明示 `STATE_RECONCILE`。本批以 **§45** 为准（§45 是专门定义该字段分类的章节，且明确
  「最终由 `OperationDefinition` 指定」；§86 的 `RETRY_SAFE` 不在任何词表内）。
- **R16**：`docs/02` §86 的 `BUILD.COLUMN.required_capabilities` 只有
  `MODEL.NODE.WRITE` ＋ `MODEL.ELEMENT.WRITE`，而 `docs/07` §6.5 的组合端点还含
  `DB.MATL` / `DB.SECT`。本批以 **§86** 为准（它是 `OperationDefinition` 的示例口径，
  也是 §12 P08 门槛直接引用的章节）；§6.5 的端点组合属 Adapter 编排（P122）。
- **R17**：Capability 词表（41 条）缺 `MODEL.GROUP.WRITE` / `MODEL.GROUP.DELETE` /
  `MODEL.MATERIAL.DELETE` / `MODEL.SECTION.DELETE` / `MODEL.BOUNDARY.DELETE`，
  而 Operation 契约含对应的 4 条 DELETE。本批按第 2 条规则回退并登记。

事务边界（`docs/02` §16；`docs/07` §14.4）
------------------------------------------
本模块**只读装配**：`load()` 不写任何行；`sync_operation_capabilities()` 只 `flush()`，
**绝不** `commit()` / `rollback()` —— 事务边界归 `UnitOfWork`（与 P07 Seed 同一口径）。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from sqlalchemy import inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config.logging import configure_logging
from app.config.settings import settings
from app.domain.enums import Capability, ExecutionMode, PermissionCode, RiskLevel
from app.domain.errors import InternalError, NotFoundError
from app.domain.protocols import OperationDefinition
from app.infrastructure.database.models import (
    CapabilityORM,
    OperationCapabilityORM,
    OperationORM,
)
from app.infrastructure.database.session import create_engine, create_session_factory
from app.infrastructure.database.unit_of_work import UnitOfWork

__all__ = [
    "OPERATION_CAPABILITIES",
    "OPERATION_COUNT",
    "OPERATION_PROFILES",
    "RECOVERY_POLICIES",
    "OperationCapabilitySyncReport",
    "OperationProfile",
    "OperationRegistry",
    "main",
    "sync_operation_capabilities",
]

logger = logging.getLogger("structai.registry")

OPERATION_COUNT: Final[int] = 69
"""冻结的 Operation 总数（`docs/07` §5.1：6+8+8+7+14+7+6+6+7 = **69**；`docs/02` §69）。"""

# ===== Recovery Policy（`docs/02` §45 的四值词表）=====

RECOVERY_SAFE_RETRY: Final[str] = "SAFE_RETRY"
RECOVERY_STATE_RECONCILE: Final[str] = "STATE_RECONCILE"
RECOVERY_MANUAL_REVIEW: Final[str] = "MANUAL_REVIEW"
RECOVERY_FAIL: Final[str] = "FAIL"

RECOVERY_POLICIES: Final[frozenset[str]] = frozenset(
    {RECOVERY_SAFE_RETRY, RECOVERY_STATE_RECONCILE, RECOVERY_MANUAL_REVIEW, RECOVERY_FAIL}
)
"""`docs/02` §45 的 Recovery Policy 分类（`FAIL` 为 `docs/02` §11 的默认值）。"""


# ===== 补齐映射（逐条 `anchor` 指回章节）=====


@dataclass(frozen=True, slots=True)
class OperationProfile:
    """`OperationDefinition` 中**不由数据库持久化**的 6 个字段（`docs/07` §4.2；`docs/02` §21）。

    `anchor` 是**出处标注**（规范章节号），使「每条映射都能指回具体章节」可被机器检查
    （`tests/test_registry_p08.py` 逐条断言其非空且含 `docs/07` / `docs/02` 章节引用）。
    """

    required_permissions: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    transactional: bool
    rollback_supported: bool
    dry_run_supported: bool
    recovery_policy: str
    anchor: str


def _profile(
    *,
    permissions: tuple[PermissionCode, ...],
    capabilities: tuple[Capability, ...],
    transactional: bool,
    dry_run_supported: bool,
    recovery_policy: str,
    anchor: str,
) -> OperationProfile:
    """构造一条补齐映射。

    `rollback_supported` 与 `transactional` **同值**（模块 docstring 规则 4），故不单独传参，
    避免两处口径漂移。
    """
    return OperationProfile(
        required_permissions=tuple(code.value for code in permissions),
        required_capabilities=tuple(code.value for code in capabilities),
        transactional=transactional,
        rollback_supported=transactional,
        dry_run_supported=dry_run_supported,
        recovery_policy=recovery_policy,
        anchor=anchor,
    )


def _build_profiles() -> dict[str, OperationProfile]:
    """构造 69 条补齐映射（`docs/07` §5.1 · §5.4 · §5.5 · §6.1–§6.10；`docs/02` §31 · §45 · §86–§87）。"""
    profiles: dict[str, OperationProfile] = {}

    def add(
        names: tuple[str, ...],
        capabilities: tuple[tuple[Capability, ...], ...],
        *,
        permissions: tuple[PermissionCode, ...],
        transactional: bool,
        dry_run_supported: bool,
        recovery_policy: str,
        anchor: str,
    ) -> None:
        """按组写入映射：`names` 与 `capabilities` 一一对应（长度不等即编码错误）。"""
        if len(names) != len(capabilities):
            raise ValueError(f"profile table arity mismatch: {names!r} vs {capabilities!r}")
        for name, codes in zip(names, capabilities, strict=True):
            profiles[name] = _profile(
                permissions=permissions,
                capabilities=codes,
                transactional=transactional,
                dry_run_supported=dry_run_supported,
                recovery_policy=recovery_policy,
                anchor=anchor,
            )

    # ===== ① `engineering_doc`（6）—— `docs/07` §6.1 =====

    doc_anchor = (
        "docs/07 §5.1（Tool 权限 `DOCUMENT_READ/WRITE`；`/` 按 Operation 二选一）· §6.1"
        "（Operation → 端点映射）· §5.4（Dry Run 矩阵未列举 `engineering_doc` → 不声明支持）· "
        "docs/02 §31 / §70（`DOCUMENT.*` 能力码）· §45（只读 → `SAFE_RETRY`，改状态 → `STATE_RECONCILE`）"
    )
    add(
        ("INFO",),
        ((Capability.DOCUMENT_INFO,),),
        permissions=(PermissionCode.DOCUMENT_READ,),
        transactional=False,
        dry_run_supported=False,
        recovery_policy=RECOVERY_SAFE_RETRY,
        anchor=doc_anchor,
    )
    add(
        ("NEW", "OPEN", "SAVE", "SAVE_AS", "CLOSE"),
        (
            (Capability.DOCUMENT_NEW,),
            (Capability.DOCUMENT_OPEN,),
            (Capability.DOCUMENT_SAVE,),
            (Capability.DOCUMENT_SAVE_AS,),
            (Capability.DOCUMENT_CLOSE,),
        ),
        permissions=(PermissionCode.DOCUMENT_WRITE,),
        transactional=False,
        dry_run_supported=False,
        recovery_policy=RECOVERY_STATE_RECONCILE,
        anchor=doc_anchor,
    )

    # ===== ② `engineering_model_query`（8）—— `docs/07` §6.2 =====

    add(
        (
            "MODEL.QUERY",
            "MODEL.NODE.QUERY",
            "MODEL.ELEMENT.QUERY",
            "MODEL.MATERIAL.QUERY",
            "MODEL.SECTION.QUERY",
            "MODEL.BOUNDARY.QUERY",
            "MODEL.LOAD.QUERY",
            "MODEL.GROUP.QUERY",
        ),
        (
            (Capability.MODEL_READ,),
            (Capability.MODEL_NODE_READ,),
            (Capability.MODEL_ELEMENT_READ,),
            (Capability.MODEL_MATERIAL_READ,),
            (Capability.MODEL_SECTION_READ,),
            (Capability.MODEL_BOUNDARY_READ,),
            (Capability.MODEL_LOAD_READ,),
            (Capability.MODEL_GROUP_READ,),
        ),
        permissions=(PermissionCode.MODEL_READ,),
        transactional=False,
        dry_run_supported=False,
        recovery_policy=RECOVERY_SAFE_RETRY,
        anchor=(
            "docs/07 §5.1（`MODEL_READ`）· §6.2（Operation → 端点映射）· §5.4（Dry Run：query 无意义）· "
            "docs/02 §31（`MODEL.NODE.QUERY → MODEL.NODE.READ` 等）· §87 与 §5.5"
            "（`MODEL.NODE.QUERY → SAFE_RETRY`）"
        ),
    )

    # ===== ③ `engineering_model_assign`（8）—— `docs/07` §6.3 =====

    add(
        (
            "MODEL.NODE.CREATE",
            "MODEL.NODE.UPDATE",
            "MODEL.ELEMENT.CREATE",
            "MODEL.ELEMENT.UPDATE",
            "MODEL.MATERIAL.ASSIGN",
            "MODEL.SECTION.ASSIGN",
            "MODEL.BOUNDARY.ASSIGN",
            "MODEL.LOAD.ASSIGN",
        ),
        (
            (Capability.MODEL_NODE_WRITE,),
            (Capability.MODEL_NODE_WRITE,),
            (Capability.MODEL_ELEMENT_WRITE,),
            (Capability.MODEL_ELEMENT_WRITE,),
            (Capability.MODEL_MATERIAL_WRITE,),
            (Capability.MODEL_SECTION_WRITE,),
            (Capability.MODEL_BOUNDARY_WRITE,),
            (Capability.MODEL_LOAD_WRITE,),
        ),
        permissions=(PermissionCode.MODEL_WRITE,),
        transactional=False,
        dry_run_supported=True,
        recovery_policy=RECOVERY_STATE_RECONCILE,
        anchor=(
            "docs/07 §5.1（`MODEL_WRITE`）· §6.3（Operation → 端点映射）· §5.4（Dry Run：assign=推荐）· "
            "docs/02 §31（`MODEL.NODE.CREATE → MODEL.NODE.WRITE`）· §87 / §5.5（`MODEL.NODE.CREATE`）· "
            "§45（改状态 → `STATE_RECONCILE`）"
        ),
    )

    # ===== ④ `engineering_model_delete`（7）—— `docs/07` §6.4 =====

    add(
        (
            "MODEL.NODE.DELETE",
            "MODEL.ELEMENT.DELETE",
            "MODEL.LOAD.DELETE",
            "MODEL.BOUNDARY.DELETE",
            "MODEL.GROUP.DELETE",
            "MODEL.MATERIAL.DELETE",
            "MODEL.SECTION.DELETE",
        ),
        (
            (Capability.MODEL_NODE_DELETE,),
            (Capability.MODEL_ELEMENT_DELETE,),
            (Capability.MODEL_LOAD_DELETE,),
            (Capability.MODEL_BOUNDARY_WRITE,),
            (Capability.MODEL_GROUP_READ,),
            (Capability.MODEL_MATERIAL_WRITE,),
            (Capability.MODEL_SECTION_WRITE,),
        ),
        permissions=(PermissionCode.MODEL_DELETE,),
        transactional=False,
        dry_run_supported=True,
        recovery_policy=RECOVERY_STATE_RECONCILE,
        anchor=(
            "docs/07 §5.1（`MODEL_DELETE`）· §6.4（`DELETE {uri}/{id}`）· §5.4"
            "（Dry Run：delete=推荐；确认：`MODEL.*.DELETE` 默认需要）· docs/02 §31 / §87 / §5.5"
            "（`MODEL.NODE.DELETE → MODEL.NODE.DELETE`）· §45（`MODEL.DELETE → STATE_RECONCILE`）· "
            "词表缺口回退见模块 docstring 规则 2 与 §16 R17"
        ),
    )

    # ===== ⑤ `engineering_model_build`（14）—— `docs/07` §6.5 =====

    build_pair = (Capability.MODEL_NODE_WRITE, Capability.MODEL_ELEMENT_WRITE)
    add(
        (
            "BUILD.BEAM",
            "BUILD.COLUMN",
            "BUILD.FRAME",
            "BUILD.TRUSS",
            "BUILD.SLAB",
            "BUILD.WALL",
            "BUILD.FOUNDATION",
            "BUILD.STEEL_FRAME",
            "MODEL.COPY",
            "MODEL.MOVE",
            "MODEL.MIRROR",
            "MODEL.PATTERN",
            "MODEL.GENERATE_GRID",
        ),
        (build_pair,) * 13,
        permissions=(PermissionCode.MODEL_WRITE,),
        transactional=True,
        dry_run_supported=True,
        recovery_policy=RECOVERY_STATE_RECONCILE,
        anchor=(
            "docs/07 §5.1（`MODEL_WRITE`）· §6.5（组合编排；原话「在 Core 中以组合 Operation 实现"
            "（`OperationDefinition.transactional=true`）」）· §6.10（映射性质：🟡 组合编排 9 · "
            "❌ 无直接 API 5）· §5.4（Dry Run：build=必须）· docs/02 §86（`BUILD.COLUMN` 示例："
            "`MODEL_WRITE` / `MODEL.NODE.WRITE`+`MODEL.ELEMENT.WRITE` / `transactional=True` / "
            "`rollback_supported=True` / `dry_run_supported=True`）· §45（`BUILD.COLUMN → STATE_RECONCILE`）"
        ),
    )
    add(
        ("BUILD.NODE_GRID",),
        ((Capability.MODEL_NODE_WRITE,),),
        permissions=(PermissionCode.MODEL_WRITE,),
        transactional=True,
        dry_run_supported=True,
        recovery_policy=RECOVERY_STATE_RECONCILE,
        anchor=(
            "docs/07 §5.1（`MODEL_WRITE`）· §6.5（`BUILD.NODE_GRID` 仅组合 `DB.NODE`；"
            "`transactional=true`）· §6.10 · §5.4（Dry Run：build=必须）· docs/02 §86"
            "（`BUILD.COLUMN` 示例的写能力口径）· §45（`STATE_RECONCILE`）"
        ),
    )

    # ===== ⑥ `engineering_view`（7）—— `docs/07` §6.6 =====

    view_anchor = (
        "docs/07 §5.1（`MODEL_READ/RESULT_READ`，按 Operation 二选一）· §6.6"
        "（`VIEW.MODEL` 用 `DISPLAY`+`CAPTURE`；其余用 `RESULTGRAPHIC`+`CAPTURE`）· §6.10"
        "（映射性质：✅ 直接「2 组共用端点」）· §5.4（Dry Run：view 无意义）· "
        "docs/02 §70（`VIEW.*` 是通配写法、不是能力码）· §45（只读 → `SAFE_RETRY`）"
    )
    add(
        ("VIEW.MODEL",),
        ((Capability.MODEL_READ,),),
        permissions=(PermissionCode.MODEL_READ,),
        transactional=False,
        dry_run_supported=False,
        recovery_policy=RECOVERY_SAFE_RETRY,
        anchor=view_anchor,
    )
    add(
        (
            "VIEW.DEFORMED_MODEL",
            "VIEW.REACTION",
            "VIEW.DISPLACEMENT",
            "VIEW.STRESS",
            "VIEW.FORCE",
            "VIEW.MODE_SHAPE",
        ),
        (
            (Capability.RESULT_DISPLACEMENT,),
            (Capability.RESULT_REACTION,),
            (Capability.RESULT_DISPLACEMENT,),
            (Capability.RESULT_STRESS,),
            (Capability.RESULT_ELEMENT_FORCE,),
            (Capability.RESULT_MODE_SHAPE,),
        ),
        permissions=(PermissionCode.RESULT_READ,),
        transactional=False,
        dry_run_supported=False,
        recovery_policy=RECOVERY_SAFE_RETRY,
        anchor=view_anchor,
    )

    # ===== ⑦ `engineering_result`（6）—— `docs/07` §6.7 =====

    add(
        (
            "RESULT.NODE.DISPLACEMENT",
            "RESULT.NODE.REACTION",
            "RESULT.ELEMENT.FORCE",
            "RESULT.ELEMENT.STRESS",
            "RESULT.MODE.SHAPE",
            "RESULT.ANALYSIS.SUMMARY",
        ),
        (
            (Capability.RESULT_DISPLACEMENT,),
            (Capability.RESULT_REACTION,),
            (Capability.RESULT_ELEMENT_FORCE,),
            (Capability.RESULT_STRESS,),
            (Capability.RESULT_MODE_SHAPE,),
            (
                Capability.RESULT_DISPLACEMENT,
                Capability.RESULT_REACTION,
                Capability.RESULT_ELEMENT_FORCE,
                Capability.RESULT_STRESS,
                Capability.RESULT_MODE_SHAPE,
            ),
        ),
        permissions=(PermissionCode.RESULT_READ,),
        transactional=True,
        dry_run_supported=False,
        recovery_policy=RECOVERY_SAFE_RETRY,
        anchor=(
            "docs/07 §5.1（`RESULT_READ`）· §6.7（组合：`POST /POST/TABLE` + `Argument.TABLE_TYPE`）· "
            "§6.10（映射性质：🟡 组合「需选 `TABLE_TYPE`」）· §5.4（Dry Run：result 无意义）· "
            "docs/02 §31 / §70（`RESULT.*` 能力码）· §45（只读 → `SAFE_RETRY`）；"
            "`RESULT.ANALYSIS.SUMMARY` 是通用入口 → 登记 RESULT 域全部 5 个能力码"
        ),
    )

    # ===== ⑧ `engineering_design`（6）—— `docs/07` §6.8 =====

    design_anchor = (
        "docs/07 §5.1（`DESIGN_EXECUTE(+DESIGN_MODIFY)`；`+` 为条件权限）· §6.8"
        "（组合：规范选择 → `DCO` → `DCTL` → `MEMB` → 设计/校核 → `*-TABLE`）· §6.10"
        "（映射性质：🟡 组合 3 · 🟢 组合 + 自研引擎 3）· §5.4（Dry Run：design=推荐；"
        "确认：`DESIGN.OPTIMIZE + apply=true`）· docs/02 §31（`DESIGN.STEEL → DESIGN.STEEL`）· §45"
    )
    add(
        (
            "DESIGN.STEEL",
            "DESIGN.CONCRETE",
            "DESIGN.SRC",
            "DESIGN.FOUNDATION",
            "DESIGN.CODE_CHECK",
        ),
        (
            (Capability.DESIGN_STEEL,),
            (Capability.DESIGN_CONCRETE,),
            (Capability.DESIGN_SRC,),
            (Capability.DESIGN_FOUNDATION,),
            (Capability.DESIGN_CODE_CHECK,),
        ),
        permissions=(PermissionCode.DESIGN_EXECUTE,),
        transactional=True,
        dry_run_supported=True,
        recovery_policy=RECOVERY_STATE_RECONCILE,
        anchor=design_anchor,
    )
    add(
        ("DESIGN.OPTIMIZE",),
        ((Capability.DESIGN_OPTIMIZATION,),),
        permissions=(PermissionCode.DESIGN_EXECUTE, PermissionCode.DESIGN_MODIFY),
        transactional=True,
        dry_run_supported=True,
        recovery_policy=RECOVERY_MANUAL_REVIEW,
        anchor=(
            design_anchor + "（`DESIGN.OPTIMIZE → MANUAL_REVIEW`）· §6.8"
            "（自研优化循环「改 `DB.SECT`」→ 写模型 → 需 `DESIGN_MODIFY`）"
        ),
    )

    # ===== ⑨ `engineering_analysis`（7）—— `docs/07` §6.9 =====

    add(
        (
            "ANALYSIS.STATIC",
            "ANALYSIS.MODAL",
            "ANALYSIS.SEISMIC",
            "ANALYSIS.SPECTRUM",
            "ANALYSIS.BUCKLING",
            "ANALYSIS.TIME_HISTORY",
            "ANALYSIS.NONLINEAR",
        ),
        (
            (Capability.ANALYSIS_STATIC,),
            (Capability.ANALYSIS_MODAL,),
            (Capability.ANALYSIS_SEISMIC,),
            (Capability.ANALYSIS_SPECTRUM,),
            (Capability.ANALYSIS_BUCKLING,),
            (Capability.ANALYSIS_TIME_HISTORY,),
            (Capability.ANALYSIS_NONLINEAR,),
        ),
        permissions=(PermissionCode.ANALYSIS_EXECUTE,),
        transactional=False,
        dry_run_supported=True,
        recovery_policy=RECOVERY_STATE_RECONCILE,
        anchor=(
            "docs/07 §5.1（`ANALYSIS_EXECUTE`）· §6.9（`DOC.ANAL` + 前置表）· §6.10"
            "（映射性质：✅ 直接）· §5.4（Dry Run：analysis=推荐）· docs/02 §87（`ANALYSIS.STATIC`："
            "`ANALYSIS_EXECUTE` / `ANALYSIS.STATIC` / ASYNC / Task REQUIRED）· §45"
            "（`ANALYSIS.STATIC → SAFE_RETRY / STATE_RECONCILE`，本批取后者：分析会改变软件侧状态）"
        ),
    )

    return profiles


OPERATION_PROFILES: Final[Mapping[str, OperationProfile]] = MappingProxyType(_build_profiles())
"""Operation 名 → 补齐字段（`docs/07` §12 P08 门槛 ②）。共 `OPERATION_COUNT` 条。"""

OPERATION_CAPABILITIES: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {name: profile.required_capabilities for name, profile in OPERATION_PROFILES.items()}
)
"""Operation 名 → 能力码元组（`docs/02` §27 / §31 的 `operation_capabilities` 数据源）。"""


# ===== 运行时注册表（`docs/02` §11 / §28）=====


class OperationRegistry:
    """运行时操作注册表（`docs/02` §11 / §28；`docs/07` §12 P08）。

    实现 `app.domain.protocols.OperationRegistry`（`register` / `get` / `list`），
    并只读地持有装配好的 `OperationDefinition`。**不**执行任何 API、**不**提交事务
    （`docs/02` §45 Registry 最终边界；`docs/07` §14.4）。
    """

    def __init__(self, definitions: Iterable[OperationDefinition] = ()) -> None:
        """由定义序列构造（同名后写覆盖先写，与 `register` 同语义）。"""
        self._operations: dict[str, OperationDefinition] = {}
        for definition in definitions:
            self._operations[definition.name] = definition

    # ===== 域契约：`app.domain.protocols.OperationRegistry` =====

    async def register(self, definition: OperationDefinition) -> None:
        """登记（或覆盖）一条定义（`docs/02` §28）。"""
        self._operations[definition.name] = definition

    async def get(self, name: str) -> OperationDefinition | None:
        """按名读取定义；未登记返回 `None`（域契约口径，不抛异常）。

        ⚠️ `docs/07` §12 P08 的门槛是「69 个 Operation **全部**可 `get`」——
        任一返回 `None` 即失败，因此 `None` 只可能来自「数据库未配备」（`load()` 返回
        `None`）或未登记的 Operation 名。
        """
        return self._operations.get(name)

    async def list(self) -> list[OperationDefinition]:
        """全部定义，按 `name` 升序（输出确定性）。"""
        return [self._operations[name] for name in sorted(self._operations)]

    # ===== 只读便捷入口 =====

    def require(self, name: str) -> OperationDefinition:
        """按名读取定义；未登记 → `NotFoundError`（`docs/02` §15 的查找失败口径）。

        ⚠️ 这是**同步**方法（`get` 的严格版），供装配期 / 内部调用使用；
        对外仍以域契约的异步 `get` 为准。
        """
        definition = self._operations.get(name)
        if definition is None:
            raise NotFoundError(f"Operation not found: {name}")
        return definition

    def names(self) -> tuple[str, ...]:
        """已登记的 Operation 名（升序元组）。"""
        return tuple(sorted(self._operations))

    def for_tool(self, tool: str) -> tuple[OperationDefinition, ...]:
        """某个 Tool 下的全部定义（`docs/07` §5.1 的 Tool → Operation 归属）。"""
        return tuple(
            self._operations[name]
            for name in sorted(self._operations)
            if self._operations[name].tool == tool
        )

    def summary(self) -> dict[str, Any]:
        """装配摘要（供启动日志与验收证据；**不含**任何 secret，`docs/07` §14.3）。"""
        return {
            "operations": len(self._operations),
            "tools": sorted({definition.tool for definition in self._operations.values()}),
            "transactional": sum(1 for item in self._operations.values() if item.transactional),
            "dry_run_supported": sum(
                1 for item in self._operations.values() if item.dry_run_supported
            ),
        }

    def __len__(self) -> int:
        return len(self._operations)

    def __contains__(self, name: object) -> bool:
        return name in self._operations

    # ===== 装配（Database Registry → Runtime Registry，`docs/02` §28）=====

    @classmethod
    async def load(
        cls,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> OperationRegistry | None:
        """从数据库装配运行时注册表（`docs/02` §28；`docs/07` §12 P08 门槛 ②）。

        - 六个字段（`name` / `tool` / `risk_level` / `execution_mode` / `input_schema` /
          `output_schema`）取自 P07 落库的 `operations` 表；
        - 其余六个字段取自 `OPERATION_PROFILES`（逐条带章节出处）。

        Args:
            engine: 只用于**只读**地探查表是否存在（不建表、不改表，`docs/07` §14.3）。
            session_factory: `create_session_factory(engine)` 的产物（P04）。

        Returns:
            已装配的 `OperationRegistry`；`operations` 表**不存在**时返回 `None`，
            表示数据库尚未配备（P01–P07 的回归门槛要求 `python -m app.main` 在未配备的
            开发库上仍以退出码 0 结束，故「未配备」不等于校验失败）。

        Raises:
            InternalError: 表存在但内容不合法（缺 / 多 Operation、非法枚举值、
                引用了 `capabilities` 表未登记的能力码、`operation_capabilities` 与
                静态映射不一致）→ **Registry 校验失败** → Server MUST NOT become READY
                （`docs/07` §14.4）。用 `STRUCTAI-7000`（`docs/07` §11 既有兜底码），
                **不新增错误码**。
        """
        tables = await _table_names(engine)
        if "operations" not in tables:
            logger.warning(
                "operation registry not provisioned: table 'operations' is absent; "
                "run `python -m app.infrastructure.database.seed` (registry left unassembled)"
            )
            return None

        async with session_factory() as session:
            operations = list((await session.execute(select(OperationORM))).scalars().all())
            capabilities = list((await session.execute(select(CapabilityORM))).scalars().all())
            relations: list[OperationCapabilityORM] = []
            if "operation_capabilities" in tables:
                relations = list(
                    (await session.execute(select(OperationCapabilityORM))).scalars().all()
                )

        definitions = _validate(operations, capabilities, relations)
        if not relations:
            logger.warning(
                "operation_capabilities is empty: run "
                "`python -m app.infrastructure.registry.operation_registry` to persist the "
                "Operation <-> Capability mapping (docs/02 §27 / §31)"
            )

        registry = cls(definitions)
        logger.info("operation registry assembled: %s", registry.summary())
        return registry


# ===== 装配校验（`docs/07` §14.4：失败 → MUST NOT become READY）=====


async def _table_names(engine: AsyncEngine) -> set[str]:
    """只读地取库中表名（**不**建表 / 不改表，`docs/07` §14.3）。"""
    async with engine.connect() as connection:
        return set(
            await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_table_names()
            )
        )


def _validate(
    operations: Sequence[OperationORM],
    capabilities: Sequence[CapabilityORM],
    relations: Sequence[OperationCapabilityORM],
) -> list[OperationDefinition]:
    """校验数据库内容与静态映射的自洽性（`docs/07` §14.4）。

    Args:
        operations: `operations` 表全量行（P07 落库）。
        capabilities: `capabilities` 表全量行（P07 落库，41 条）。
        relations: `operation_capabilities` 表全量行（可为空 = 尚未落库）。

    Returns:
        通过校验的 `OperationDefinition` 列表（按 `name` 升序）。

    Raises:
        InternalError: 任一校验项失败；`details["failures"]` 一次列出全部失败项。
    """
    failures: list[str] = []

    by_name = {row.name: row for row in operations}
    if len(by_name) != OPERATION_COUNT:
        failures.append(
            f"`operations` holds {len(by_name)} row(s), expected {OPERATION_COUNT} "
            "(docs/07 §5.1)"
        )
    missing = sorted(set(OPERATION_PROFILES) - set(by_name))
    unexpected = sorted(set(by_name) - set(OPERATION_PROFILES))
    if missing:
        failures.append(f"`operations` is missing operation(s): {missing}")
    if unexpected:
        failures.append(f"`operations` has unexpected operation(s): {unexpected}")

    capability_codes = {row.code for row in capabilities}
    for name, profile in OPERATION_PROFILES.items():
        unknown = sorted(set(profile.required_capabilities) - capability_codes)
        if unknown:
            failures.append(f"{name}: capability code(s) not in `capabilities`: {unknown}")

    code_by_id = {row.id: row.code for row in capabilities}
    name_by_id = {row.id: row.name for row in operations}
    actual: set[tuple[str, str]] = set()
    for relation in relations:
        operation_name = name_by_id.get(relation.operation_id)
        capability_code = code_by_id.get(relation.capability_id)
        if operation_name is None or capability_code is None:
            failures.append(
                "`operation_capabilities` has a dangling row: "
                f"{relation.operation_id} -> {relation.capability_id}"
            )
            continue
        actual.add((operation_name, capability_code))

    if relations:
        expected = {
            (name, code) for name, codes in OPERATION_CAPABILITIES.items() for code in codes
        }
        extra = sorted(actual - expected)
        absent = sorted(expected - actual)
        if extra:
            failures.append(
                f"`operation_capabilities` has mapping(s) outside the profile table: {extra}"
            )
        if absent:
            failures.append(
                f"`operation_capabilities` is missing {len(absent)} mapping(s), e.g. {absent[:5]}"
            )

    definitions: list[OperationDefinition] = []
    for name in sorted(by_name):
        row = by_name[name]
        resolved = OPERATION_PROFILES.get(name)
        if resolved is None:
            continue
        try:
            risk_level = RiskLevel(row.risk_level)
            execution_mode = ExecutionMode(row.execution_mode)
        except ValueError as error:
            failures.append(f"{name}: invalid risk_level / execution_mode ({error})")
            continue
        if not row.input_schema or not row.output_schema:
            failures.append(f"{name}: empty input_schema / output_schema")
            continue
        definitions.append(
            OperationDefinition(
                name=row.name,
                tool=row.tool,
                risk_level=risk_level,
                execution_mode=execution_mode,
                input_schema=row.input_schema,
                output_schema=row.output_schema,
                required_permissions=resolved.required_permissions,
                required_capabilities=resolved.required_capabilities,
                transactional=resolved.transactional,
                rollback_supported=resolved.rollback_supported,
                dry_run_supported=resolved.dry_run_supported,
                recovery_policy=resolved.recovery_policy,
            )
        )

    if failures:
        raise InternalError(
            "operation registry validation failed",
            details={"failures": failures},
        )
    return definitions


# ===== Operation ↔ Capability 落库（`docs/02` §27 / §31；P08 门槛 ③）=====


@dataclass(frozen=True, slots=True)
class OperationCapabilitySyncReport:
    """一次 `operation_capabilities` 同步的结果（幂等重跑应为「零新增」）。"""

    created: int
    existing: int

    @property
    def total(self) -> int:
        """同步后 `operation_capabilities` 的关联总数。"""
        return self.created + self.existing

    def summary(self) -> str:
        """单行摘要（**绝不含**任何 secret，`docs/07` §14.3）。"""
        return f"created {self.created} row(s); existing {self.existing} row(s)"


async def sync_operation_capabilities(session: AsyncSession) -> OperationCapabilitySyncReport:
    """把 `OPERATION_CAPABILITIES` 落库到 `operation_capabilities`（`docs/02` §27 / §31）。

    P07 明确把该关系留给 P08（`seed.py` 模块 docstring「规范之上的落地说明」）。
    幂等：按复合主键 `(operation_id, capability_id)` 先查后插，重复执行**零新增**。

    ⚠️ 只 `flush()`，**绝不** `commit()` / `rollback()` —— 事务边界归 `UnitOfWork`
    （`docs/02` §16；`docs/07` §14.4）。

    Args:
        session: 已绑定到某个 `UnitOfWork` 的会话（`docs/02` §16）。

    Returns:
        `OperationCapabilitySyncReport`。

    Raises:
        InternalError: `operations` / `capabilities` 未 Seed 到 69 / 41 行（先跑 P07 Seed）。
    """
    operation_ids = {
        str(name): str(identifier)
        for name, identifier in (
            await session.execute(select(OperationORM.name, OperationORM.id))
        ).all()
    }
    capability_ids = {
        str(code): str(identifier)
        for code, identifier in (
            await session.execute(select(CapabilityORM.code, CapabilityORM.id))
        ).all()
    }
    pairs = {
        (str(operation_id), str(capability_id))
        for operation_id, capability_id in (
            await session.execute(
                select(
                    OperationCapabilityORM.operation_id,
                    OperationCapabilityORM.capability_id,
                )
            )
        ).all()
    }
    existing = len(pairs)

    for name, codes in OPERATION_CAPABILITIES.items():
        operation_id = operation_ids.get(name)
        if operation_id is None:
            raise InternalError(
                "operation_capabilities sync requires the P07 seed",
                details={"missing_operation": name},
            )
        for code in codes:
            capability_id = capability_ids.get(code)
            if capability_id is None:
                raise InternalError(
                    "operation_capabilities sync requires the P07 seed",
                    details={"missing_capability": code},
                )
            pair = (operation_id, capability_id)
            if pair in pairs:
                continue
            session.add(
                OperationCapabilityORM(operation_id=operation_id, capability_id=capability_id)
            )
            pairs.add(pair)

    await session.flush()
    return OperationCapabilitySyncReport(created=len(pairs) - existing, existing=existing)


# ===== 命令行（把映射落库；`docs/08` §1 的交接证据入口之一）=====


async def async_main(argv: Sequence[str] | None = None) -> int:
    """异步主流程：同步 Operation ↔ Capability → 输出摘要。"""
    _build_parser().parse_args(argv)
    configure_logging(settings.log_level)

    engine = create_engine(settings.database_url, echo=False)
    try:
        async with create_session_factory(engine)() as session:
            async with UnitOfWork(session):
                report = await sync_operation_capabilities(session)
    finally:
        await engine.dispose()

    print(f"operation_capabilities sync ok: {report.summary()}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """构造 CLI 参数解析器。"""
    return argparse.ArgumentParser(
        prog="python -m app.infrastructure.registry.operation_registry",
        description=(
            "P08：把 Operation <-> Capability 映射落库到 operation_capabilities"
            "（docs/02 §27 / §31）。需要先跑 P07 Seed。"
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """同步入口，返回进程退出码（成功 `0`；库未 Seed / 数据库错误 `2`）。

    ⚠️ 失败信息只含 Operation / Capability 码与数据库错误摘要，**绝不含** secret
    （`docs/07` §14.3）。
    """
    try:
        return asyncio.run(async_main(argv))
    except InternalError as error:
        print(f"operation_capabilities sync failed: {error}", file=sys.stderr)
        return 2
    except SQLAlchemyError as error:
        print(
            f"operation_capabilities sync failed: database error: {type(error).__name__}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
