"""Application · Services · ModelService（`docs/07` §12 P30；`docs/02` §48 / §32 / §33 / §73）。

权威来源
--------
- `docs/02` §48（`exec`）—— `ModelService` 的读方法名：`query_node` / `query_element` /
  `query_material` / `query_section` / `query_boundary` / `query_load`，以及写方法名
  `assign_material` / `assign_section` / `assign_boundary` / `assign_load`。
  同一节写明「Tool 不直接调用 Repository」。
- `docs/02` §32（`blue` / `source9`）—— 后置条件与「操作必须产生可验证状态」：
  写操作要落到模型上，读操作只回答事实。
- `docs/02` §33（`source9`）—— 结果归一化 / 分页属**结果层**（本批的 `ResultService`），
  服务层只回原始规范映射。
- `docs/02` §73（`exec`）—— `ResolvedResource(resource_type, resource_id, tenant_id,
  project_id)`：本服务消费的是**已解析**的软件实例（租户边界由 `ResourceResolver` 负责，
  `docs/07` §9 第 7 步）。
- `docs/07` §9 —— **26 步执行流水线**：写操作必须经 `ExecutionService`（RBAC / Confirmation /
  Idempotency / Lock / Capability 全在该链上）；`docs/07` §12 P30 —— 本批落地读路径。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **`docs/02` §48 的方法名归一化为 Operation 名**：`query_node` → `MODEL.NODE.QUERY`、
   `query_element` → `MODEL.ELEMENT.QUERY`、`query_material` → `MODEL.MATERIAL.QUERY`、
   `query_section` → `MODEL.SECTION.QUERY`、`query_boundary` → `MODEL.BOUNDARY.QUERY`、
   `query_load` → `MODEL.LOAD.QUERY`；`assign_material` → `MODEL.MATERIAL.ASSIGN`、
   `assign_section` → `MODEL.SECTION.ASSIGN`、`assign_boundary` → `MODEL.BOUNDARY.ASSIGN`、
   `assign_load` → `MODEL.LOAD.ASSIGN`。方法名是 `docs/02` 的 Python 口径，Operation 名是
   P08 `operations` 表的注册口径（`docs/02` §24）；两者**一一对应**，常量固化为可断言的
   `QUERY_OPERATIONS` / `ASSIGN_OPERATIONS`。
2. **读方法只回原始规范映射**（`docs/02` §33）：本服务**不**做字段归一化、**不**分页、
   **不**裁剪 —— 那些是 `ResultService` 的**唯一**职责（`normalize` / `paginated`）。
   一个关注点一处实现：Adapter（P19–P20）负责 native → canonical 的字段映射
   （`docs/02` §89），`ResultService` 负责信封与分页，本服务只把请求交给来源。
3. **写方法只构造载荷，绝不执行**（`docs/02` §48；`docs/07` §9）：`assign_*` 返回
   `ModelAssignment`（Operation 名 + 冻结参数载荷），**不**触碰任何 Adapter / 数据库 /
   执行链。写操作必须走 26 步流水线，否则 RBAC / Confirmation / Idempotency / Lock /
   Capability 会**全部被绕过**（`docs/07` §9 的不可变依据）。`docs/02` §48 的
   「Tool 不直接调用 Repository」由此满足：Tool 对**读**调用 `ModelService`，
   对**写**调用 `ExecutionService`（由后者在流水线第 18 步落到 Adapter）。
4. **来源是本地收窄契约 `ModelQuerySource`**：Application 层**不得**依赖
   `app.infrastructure`（`docs/07` §14.1），故这里只声明「问什么问题」，由 Adapter /
   执行层在装配期结构性地满足它（与 R38 的 `RuntimeCapabilitySource` 同一做法）。
   本模块因此**不**导入任何 Adapter 实现。
5. **参数载荷的键名口径**：`query_*` 的标识序列键按查询对象命名（`node_ids` /
   `element_ids` / `material_ids` / `section_ids` / `boundary_ids` / `load_ids`），
   `assign_*` 统一用 `element_ids` + 一个赋值的业务键（`material` / `section` /
   `boundary` / `load`，即 Operation 名后缀的小写形式）。调用方传入的额外关键字参数
   原样并入载荷（不静默丢弃），故新增过滤条件无需改本模块。
6. **`query_*` 的 `node_ids` 等是可选的**：`docs/02` §48 的查询既可「查全部」也可
   「按标识查」。`None` 表示不限定标识（载荷里**不**出现该键，而不是空列表 ——
   空列表是「查这些标识（一个都没有）」，语义不同）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，
**不**依赖 `app.infrastructure`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Protocol

__all__ = [
    "ASSIGN_OPERATIONS",
    "MODEL_SERVICE_STAGE",
    "QUERY_OPERATIONS",
    "ModelAssignment",
    "ModelQuerySource",
    "ModelService",
]

MODEL_SERVICE_STAGE: Final[str] = "model_service"
"""本模块的诊断阶段名（`docs/07` §11 的 `details.stage` 口径）。"""

QUERY_OPERATIONS: Final[tuple[str, ...]] = (
    "MODEL.NODE.QUERY",
    "MODEL.ELEMENT.QUERY",
    "MODEL.MATERIAL.QUERY",
    "MODEL.SECTION.QUERY",
    "MODEL.BOUNDARY.QUERY",
    "MODEL.LOAD.QUERY",
)
"""六个查询 Operation（`docs/02` §48 的读方法名归一化；见模块裁决 1）。"""

ASSIGN_OPERATIONS: Final[tuple[str, ...]] = (
    "MODEL.MATERIAL.ASSIGN",
    "MODEL.SECTION.ASSIGN",
    "MODEL.BOUNDARY.ASSIGN",
    "MODEL.LOAD.ASSIGN",
)
"""四个赋值 Operation（`docs/02` §48 的写方法名归一化；见模块裁决 1）。

⚠️ 本服务**只构造**这些操作的载荷，**不执行**它们（见模块裁决 3）。
"""

_QUERY_IDS_KEY: Final[Mapping[str, str]] = MappingProxyType(
    {
        "MODEL.NODE.QUERY": "node_ids",
        "MODEL.ELEMENT.QUERY": "element_ids",
        "MODEL.MATERIAL.QUERY": "material_ids",
        "MODEL.SECTION.QUERY": "section_ids",
        "MODEL.BOUNDARY.QUERY": "boundary_ids",
        "MODEL.LOAD.QUERY": "load_ids",
    }
)
"""查询 Operation → 标识序列的载荷键（见模块裁决 5）。"""

_ASSIGN_VALUE_KEY: Final[Mapping[str, str]] = MappingProxyType(
    {
        "MODEL.MATERIAL.ASSIGN": "material",
        "MODEL.SECTION.ASSIGN": "section",
        "MODEL.BOUNDARY.ASSIGN": "boundary",
        "MODEL.LOAD.ASSIGN": "load",
    }
)
"""赋值 Operation → 业务值的载荷键（见模块裁决 5）。"""


class ModelQuerySource(Protocol):
    """模型查询的**本地收窄契约**（收窄契约 pattern，同 R38 的 `RuntimeCapabilitySource`）。

    执行 / Adapter 层**结构上**满足它：它接受 Operation 名与冻结参数载荷，返回
    canonical 映射。Application 层因此**不**依赖 `app.infrastructure`（`docs/07` §14.1），
    也**不**依赖 P19–P20 的 Adapter 实现（它们可能尚未落地）。
    """

    async def query(
        self,
        *,
        software_instance_id: str,
        operation: str,
        parameters: Mapping[str, Any],
        context: object,
    ) -> Mapping[str, Any]:
        """对某个软件实例执行一个查询 Operation（`docs/02` §48）。"""
        ...


@dataclass(frozen=True, slots=True)
class ModelAssignment:
    """一个**待执行**的模型赋值（`docs/02` §48；见模块裁决 3）。

    Attributes:
        operation: Operation 名（`ASSIGN_OPERATIONS` 之一）。
        parameters: 冻结的参数载荷（`element_ids` + 业务值 + 调用方的额外参数）。
    """

    operation: str
    parameters: Mapping[str, Any]


class ModelService:
    """模型读服务 + 赋值载荷构造（`docs/02` §48 / §32 / §33；`docs/07` §9）。

    ⚠️ 本服务**只读**：`query_*` 委托注入的来源，`assign_*` 只返回载荷。
    它**不**写任何表、**不** `commit` / `rollback`（`docs/07` §14.4）、
    **不**触碰 Adapter（见模块裁决 3）。
    """

    def __init__(self, source: ModelQuerySource) -> None:
        """绑定查询来源。

        Args:
            source: 满足 `ModelQuerySource` 的只读来源（装配期注入，见模块裁决 4）。
        """
        self._source = source

    @property
    def source(self) -> ModelQuerySource:
        """查询来源（只读用途）。"""
        return self._source

    # ===== 读（`docs/02` §48）=====

    async def query_node(
        self,
        *,
        software_instance_id: str,
        context: object,
        node_ids: Sequence[int] | None = None,
        **filters: Any,
    ) -> Mapping[str, Any]:
        """查询节点（`MODEL.NODE.QUERY`；`docs/02` §48）。

        Returns:
            来源返回的原始 canonical 映射（归一化 / 分页由 `ResultService` 负责，
            见模块裁决 2）。
        """
        return await self._query(
            "MODEL.NODE.QUERY",
            software_instance_id=software_instance_id,
            context=context,
            ids=node_ids,
            filters=filters,
        )

    async def query_element(
        self,
        *,
        software_instance_id: str,
        context: object,
        element_ids: Sequence[int] | None = None,
        **filters: Any,
    ) -> Mapping[str, Any]:
        """查询单元（`MODEL.ELEMENT.QUERY`；`docs/02` §48）。"""
        return await self._query(
            "MODEL.ELEMENT.QUERY",
            software_instance_id=software_instance_id,
            context=context,
            ids=element_ids,
            filters=filters,
        )

    async def query_material(
        self,
        *,
        software_instance_id: str,
        context: object,
        material_ids: Sequence[int] | None = None,
        **filters: Any,
    ) -> Mapping[str, Any]:
        """查询材料（`MODEL.MATERIAL.QUERY`；`docs/02` §48）。"""
        return await self._query(
            "MODEL.MATERIAL.QUERY",
            software_instance_id=software_instance_id,
            context=context,
            ids=material_ids,
            filters=filters,
        )

    async def query_section(
        self,
        *,
        software_instance_id: str,
        context: object,
        section_ids: Sequence[int] | None = None,
        **filters: Any,
    ) -> Mapping[str, Any]:
        """查询截面（`MODEL.SECTION.QUERY`；`docs/02` §48）。"""
        return await self._query(
            "MODEL.SECTION.QUERY",
            software_instance_id=software_instance_id,
            context=context,
            ids=section_ids,
            filters=filters,
        )

    async def query_boundary(
        self,
        *,
        software_instance_id: str,
        context: object,
        boundary_ids: Sequence[int] | None = None,
        **filters: Any,
    ) -> Mapping[str, Any]:
        """查询边界条件（`MODEL.BOUNDARY.QUERY`；`docs/02` §48）。"""
        return await self._query(
            "MODEL.BOUNDARY.QUERY",
            software_instance_id=software_instance_id,
            context=context,
            ids=boundary_ids,
            filters=filters,
        )

    async def query_load(
        self,
        *,
        software_instance_id: str,
        context: object,
        load_ids: Sequence[int] | None = None,
        **filters: Any,
    ) -> Mapping[str, Any]:
        """查询荷载（`MODEL.LOAD.QUERY`；`docs/02` §48）。"""
        return await self._query(
            "MODEL.LOAD.QUERY",
            software_instance_id=software_instance_id,
            context=context,
            ids=load_ids,
            filters=filters,
        )

    # ===== 写载荷（`docs/02` §48；见模块裁决 3）=====

    def assign_material(
        self,
        *,
        element_ids: Sequence[int],
        material: str,
        **extra: Any,
    ) -> ModelAssignment:
        """构造「给单元赋材料」的载荷（`MODEL.MATERIAL.ASSIGN`；**不执行**）。"""
        return self._assignment(
            "MODEL.MATERIAL.ASSIGN", element_ids=element_ids, value=material, extra=extra
        )

    def assign_section(
        self,
        *,
        element_ids: Sequence[int],
        section: str,
        **extra: Any,
    ) -> ModelAssignment:
        """构造「给单元赋截面」的载荷（`MODEL.SECTION.ASSIGN`；**不执行**）。"""
        return self._assignment(
            "MODEL.SECTION.ASSIGN", element_ids=element_ids, value=section, extra=extra
        )

    def assign_boundary(
        self,
        *,
        element_ids: Sequence[int],
        boundary: str,
        **extra: Any,
    ) -> ModelAssignment:
        """构造「给单元赋边界条件」的载荷（`MODEL.BOUNDARY.ASSIGN`；**不执行**）。"""
        return self._assignment(
            "MODEL.BOUNDARY.ASSIGN", element_ids=element_ids, value=boundary, extra=extra
        )

    def assign_load(
        self,
        *,
        element_ids: Sequence[int],
        load: str,
        **extra: Any,
    ) -> ModelAssignment:
        """构造「给单元赋荷载」的载荷（`MODEL.LOAD.ASSIGN`；**不执行**）。"""
        return self._assignment(
            "MODEL.LOAD.ASSIGN", element_ids=element_ids, value=load, extra=extra
        )

    def operations(self) -> tuple[str, ...]:
        """本服务涉及的全部 Operation 名（读 + 写；`docs/02` §48）。"""
        return QUERY_OPERATIONS + ASSIGN_OPERATIONS

    # ===== 内部 =====

    async def _query(
        self,
        operation: str,
        *,
        software_instance_id: str,
        context: object,
        ids: Sequence[int] | None,
        filters: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """构造载荷并委托来源（`docs/02` §48 / §33；见模块裁决 2 / 5）。"""
        parameters: dict[str, Any] = {}
        if ids is not None:
            parameters[_QUERY_IDS_KEY[operation]] = [int(value) for value in ids]
        parameters.update(filters)
        return await self._source.query(
            software_instance_id=str(software_instance_id),
            operation=operation,
            parameters=parameters,
            context=context,
        )

    def _assignment(
        self,
        operation: str,
        *,
        element_ids: Sequence[int],
        value: str,
        extra: Mapping[str, Any],
    ) -> ModelAssignment:
        """构造赋值的冻结载荷（见模块裁决 3 / 5）。"""
        parameters: dict[str, Any] = {
            "element_ids": [int(element_id) for element_id in element_ids],
            _ASSIGN_VALUE_KEY[operation]: str(value),
        }
        parameters.update(extra)
        return ModelAssignment(operation=operation, parameters=parameters)
