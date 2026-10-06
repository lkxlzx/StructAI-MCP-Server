"""Infrastructure · Adapters · Mock · Adapter —— `MockAdapter`（`docs/02` §29–§51 / §117）。

权威来源
--------
- `docs/02` §117（`source7`）—— P19–P20 的顺序：**先 Adapter Base，再 Mock Adapter**，
  「**不要先开发真实厂商 Adapter**」。
- `docs/02` §29（`adapter`）—— `class MockAdapter(BaseAdapter)`：`name = "structai.mock"` /
  `vendor = "StructAI"` / `product = "MockEngineering"` / `version = "1.0"`。
- `docs/02` §30（`adapter`）—— `get_capabilities()` 的**至少** 21 条能力码（本模块逐条照抄）。
- `docs/02` §31 / §32 / §33（`adapter`）—— `_connect` / `get_version` / `health_check` 的写法。
- `docs/02` §34 / §35 / §36（`adapter`）—— 节点与单元的 CRUD 语义。
- `docs/02` §37 / §38 / §90（`adapter` / `source7`）—— `BUILD.COLUMN` 的入参与返回
  （§90：`{"node_ids": [...], "element_ids": [...]}`）。
- `docs/02` §39 / §40（`adapter`）—— 边界 / 荷载指派。
- `docs/02` §45 / §46 / §47（`adapter`）—— 静力分析 / 位移 / 钢结构设计（实现见 `analysis.py`）。
- `docs/02` §48（`adapter`）—— 操作分派表；无 handler → `AdapterCapabilityError`。
- `docs/02` §49 / §50（`adapter`）—— 错误归一化（实现见 `base/errors.py`）。
- `docs/02` §51（`adapter`）—— `cancel()` 立即返回（Mock 操作可立即取消）。
- `docs/02` §61 / §62（`adapter`）—— Mock 集成 / E2E 场景（`BUILD.COLUMN → BOUNDARY →
  LOAD → ANALYSIS.STATIC → DISPLACEMENT → DESIGN.STEEL`）。
- `docs/07` §12 P19–P20 门槛 ④ / §12.1 里程碑 ①②。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **`BUILD.COLUMN` 同时接受两种规范化入参**：`docs/02` §83（`source7` 的 Core 输入
   Schema）用 `base_node: {x, y, z}` + `height` + `material` + `section`；
   §38（Mock 的可执行代码）用 `base_node_id` / `top_node_id` + `height`。两者都是
   规范来源，故本实现**同时**支持：给了 `base_node` 就按其坐标建节点；给了
   `base_node_id` 就复用 / 按该 id 建节点；两者都没有则用 `(0, 0, 0)`。
   `height` 必须为正（§83 的 `exclusiveMinimum: 0`）。
   返回**严格**照抄 §90：`{"node_ids": [base, top], "element_ids": [element_id]}`。
2. **复用既有节点不覆盖几何**：§38 的 `if base_id not in self.store.nodes` 语义 ——
   已存在的节点**不**被重建 / 不被改写（否则会静默破坏用户模型）。
3. **handler 只做参数规整，校验归 `MockModelStore`**：见 `model_store.py` 裁决 3。
4. **查询类操作支持可选 `limit` / `cursor`**：`docs/02` §35 的默认返回是
   `{"items": [...], "pagination": {"has_more": False, "next_cursor": None}}`（照抄）；
   本实现额外支持可选 `limit` / `cursor`（游标 = 最后一条的 id），使
   `docs/07` §14.4「禁止无限 payload」在 Mock 上也可验证。不传时行为与 §35 完全一致。
5. **`MOCK_SUPPORTED_OPERATIONS` = 实际有 handler 的 Operation 集合**：能力码是**粗粒度**
   的（`MODEL.NODE.WRITE` 等），一个 Operation 通过能力检查**不**代表 Mock 一定有它的
   handler —— `docs/02` §48 的 `AdapterCapabilityError` 正是为这种情形准备的。
   本模块把「有 handler 的集合」固化为常量，供验收逐条断言（防「声明了却没人实现」）。
   ⚠️ 未实现的 `BUILD.*`（`BUILD.BEAM` / `FRAME` / `TRUSS` / …）属**组合编排**，
   归 P122（`docs/07` §16 R2），本批**不**臆造语义。
6. **`cancel()` 是无操作**（照抄 §51）：Mock 操作即时可取消；真实 Adapter 必须按实际
   API 判断（§51）。**不**杀进程、**不**伪造 `CANCELLED`（`docs/07` §14.4）。
7. **就绪判定不在 Adapter 内**：`execute()` 不检查自身状态；「未连接 / 未就绪」由
   `AdapterManager._require_executable()` 统一拦截（见 `manager.py` 裁决 3）。

分层红线（`docs/07` §14.1 / §14.2 / §14.3）
------------------------------------------
本模块只依赖标准库、`app.application.execution.context`（ABC 签名）与同层的
`base/*` / `mock/*`（**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖
`app.interfaces`）；**不**写表、**不** `commit`、**不**记录 secret。
`MockAdapter` **不允许**成为生产计算器（`docs/02` §65）：结果一律
`engineering_grade = false`。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from types import MappingProxyType
from typing import Any, Final

from app.application.execution.context import ExecutionContext
from app.infrastructure.adapters.base.adapter import AdapterState, BaseAdapter
from app.infrastructure.adapters.base.errors import AdapterCapabilityError, AdapterValidationError
from app.infrastructure.adapters.mock import analysis
from app.infrastructure.adapters.mock.model_store import (
    DEFAULT_MATERIAL,
    DEFAULT_SECTION,
    MOCK_MATERIALS,
    MOCK_SECTIONS,
    MockBoundary,
    MockElement,
    MockMaterial,
    MockModelStore,
    MockSection,
)

__all__ = [
    "MOCK_CAPABILITIES",
    "MOCK_NAME",
    "MOCK_PRODUCT",
    "MOCK_PROTOCOL",
    "MOCK_SUPPORTED_OPERATIONS",
    "MOCK_SUPPORTED_VERSIONS",
    "MOCK_VENDOR",
    "MOCK_VERSION",
    "MockAdapter",
]

MOCK_NAME: Final[str] = "structai.mock"
"""Adapter 包标识（`docs/02` §6 / §29，逐字照抄）。"""

MOCK_VENDOR: Final[str] = "StructAI"
"""厂商（`docs/02` §29；厂商名只允许出现在 Adapter 层，`docs/07` §14.2）。"""

MOCK_PRODUCT: Final[str] = "MockEngineering"
"""产品（`docs/02` §29，逐字照抄）。"""

MOCK_VERSION: Final[str] = "1.0"
"""软件版本（`docs/02` §29 / §32）。"""

MOCK_PROTOCOL: Final[str] = "IN_PROCESS"
"""通信协议（`docs/02` §6，逐字照抄）。"""

MOCK_SUPPORTED_VERSIONS: Final[tuple[str, ...]] = (MOCK_VERSION,)
"""声明的版本集合（严格精确匹配，`docs/02` §20）。"""

MOCK_CAPABILITIES: Final[tuple[str, ...]] = (
    "MODEL.NODE.READ",
    "MODEL.NODE.WRITE",
    "MODEL.NODE.DELETE",
    "MODEL.ELEMENT.READ",
    "MODEL.ELEMENT.WRITE",
    "MODEL.ELEMENT.DELETE",
    "MODEL.MATERIAL.READ",
    "MODEL.MATERIAL.WRITE",
    "MODEL.SECTION.READ",
    "MODEL.SECTION.WRITE",
    "MODEL.BOUNDARY.READ",
    "MODEL.BOUNDARY.WRITE",
    "MODEL.LOAD.READ",
    "MODEL.LOAD.WRITE",
    "MODEL.LOAD.DELETE",
    "ANALYSIS.STATIC",
    "RESULT.DISPLACEMENT",
    "RESULT.REACTION",
    "RESULT.ELEMENT_FORCE",
    "RESULT.STRESS",
    "DESIGN.STEEL",
)
"""Mock 的**运行时**能力清单（`docs/02` §30 的「至少」清单，逐条照抄）。

⚠️ 取值必须落在落库的 41 条能力词表内（`docs/07` §14.2；验收逐条断言）。
"""

MOCK_SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    "ANALYSIS.STATIC",
    "BUILD.COLUMN",
    "DESIGN.STEEL",
    "MODEL.BOUNDARY.ASSIGN",
    "MODEL.BOUNDARY.DELETE",
    "MODEL.BOUNDARY.QUERY",
    "MODEL.ELEMENT.CREATE",
    "MODEL.ELEMENT.DELETE",
    "MODEL.ELEMENT.QUERY",
    "MODEL.ELEMENT.UPDATE",
    "MODEL.LOAD.ASSIGN",
    "MODEL.LOAD.DELETE",
    "MODEL.LOAD.QUERY",
    "MODEL.MATERIAL.ASSIGN",
    "MODEL.MATERIAL.DELETE",
    "MODEL.MATERIAL.QUERY",
    "MODEL.NODE.CREATE",
    "MODEL.NODE.DELETE",
    "MODEL.NODE.QUERY",
    "MODEL.NODE.UPDATE",
    "MODEL.SECTION.ASSIGN",
    "MODEL.SECTION.DELETE",
    "MODEL.SECTION.QUERY",
    "RESULT.ELEMENT.FORCE",
    "RESULT.ELEMENT.STRESS",
    "RESULT.NODE.DISPLACEMENT",
    "RESULT.NODE.REACTION",
)
"""Mock **实现**了 handler 的 Operation 集合（升序；见裁决 5）。

⚠️ 全部取自 P07 落库的 69 个 Operation（验收逐条断言）。
"""

PAGINATION_FALSE: Final[dict[str, Any]] = {"has_more": False, "next_cursor": None}
"""`docs/02` §35 的默认分页段（不传 `limit` / `cursor` 时的返回，照抄）。"""

MockHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
"""Mock handler 签名（`docs/02` §48：`await handler(parameters)`）。"""


class MockAdapter(BaseAdapter):
    """Mock 工程软件适配器（`docs/02` §29 / §48；`docs/07` §12 P19–P20 门槛 ④）。

    ⚠️ **不允许**成为生产计算器（`docs/02` §65）：只用于 unit / integration / e2e /
    demo / development；所有结果 `engineering_grade = false`（§41 / §63）。

    Attributes:
        store: 进程内模型状态（`docs/02` §28 / §35）。
        version: 软件版本（`docs/02` §29 / §32）。
    """

    name = MOCK_NAME
    vendor = MOCK_VENDOR
    product = MOCK_PRODUCT
    supported_versions = MOCK_SUPPORTED_VERSIONS
    protocols = (MOCK_PROTOCOL,)
    capabilities = MOCK_CAPABILITIES

    def __init__(self) -> None:
        """初始化状态机、模型状态与分派表（**不**做任何 I/O）。"""
        super().__init__()
        self.store = MockModelStore()
        self.version = MOCK_VERSION
        self._config: dict[str, Any] = {}
        self._handlers: Mapping[str, MockHandler] = MappingProxyType(self._build_handlers())

    # ===== `docs/02` §31 / §32 / §33 =====

    async def _connect(self, config: dict[str, Any]) -> None:
        """Mock 不需要真实网络（`docs/02` §31）。

        ⚠️ `config` 可能含凭据：只留在**内存**（`repr=False` 的容器里），
        **绝不**落日志 / 落库 / 落文件（`docs/07` §8.5 / §14.3）。
        """
        self._config = dict(config)

    async def get_version(self) -> str:
        """读取版本（`docs/02` §32）。"""
        return self.version

    async def health_check(self) -> dict[str, Any]:
        """健康检查（`docs/02` §33，逐字段照抄）。"""
        return {
            "healthy": self.state is AdapterState.READY,
            "state": self.state.value,
            "version": self.version,
            "latency_ms": 0,
        }

    async def get_capabilities(self) -> list[str]:
        """运行时能力清单（`docs/02` §30）。"""
        return list(MOCK_CAPABILITIES)

    async def cancel(self, task_id: str) -> None:
        """取消（`docs/02` §51：Mock 操作可立即取消，故为无操作）。

        ⚠️ **不**杀 Python 进程、**不**伪造 `CANCELLED`（`docs/07` §14.4）。
        """
        return None

    # ===== 分派（`docs/02` §48）=====

    async def execute(
        self,
        operation: str,
        parameters: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """按 Operation 分派到 handler（`docs/02` §48）。

        Args:
            operation: 规范化 Operation 名。
            parameters: 规范化参数。
            context: 执行上下文（Mock 的 handler **不**读它；Core 侧的身份 / 租户 / 权限
                判定在流水线的更早步骤完成）。

        Returns:
            规范化结果（`docs/02` §33 / §37 / §89）。

        Raises:
            AdapterCapabilityError: `STRUCTAI-3000` —— 该 Operation 没有 handler
                （§48 的 `Unsupported operation`）。
            AdapterValidationError: `STRUCTAI-1200` —— 参数 / 模型语义非法（§49）。
        """
        handler = self._handlers.get(str(operation))
        if handler is None:
            raise AdapterCapabilityError(
                f"Unsupported operation: {operation}",
                details={
                    "stage": "mock_adapter",
                    "reason": "unsupported_operation",
                    "operation": str(operation),
                },
            )
        return await handler(dict(parameters))

    def supported_operations(self) -> tuple[str, ...]:
        """本 Adapter 实现了 handler 的 Operation（升序；见裁决 5）。"""
        return tuple(sorted(self._handlers))

    # ===== 分派表（`docs/02` §48 / §59）=====

    def _build_handlers(self) -> dict[str, MockHandler]:
        """构造「Operation → handler」表（`docs/02` §48 / §59）。"""
        return {
            "MODEL.NODE.CREATE": self._node_create,
            "MODEL.NODE.UPDATE": self._node_update,
            "MODEL.NODE.DELETE": self._node_delete,
            "MODEL.NODE.QUERY": self._node_query,
            "MODEL.ELEMENT.CREATE": self._element_create,
            "MODEL.ELEMENT.UPDATE": self._element_update,
            "MODEL.ELEMENT.DELETE": self._element_delete,
            "MODEL.ELEMENT.QUERY": self._element_query,
            "MODEL.MATERIAL.ASSIGN": self._material_assign,
            "MODEL.MATERIAL.DELETE": self._material_delete,
            "MODEL.MATERIAL.QUERY": self._material_query,
            "MODEL.SECTION.ASSIGN": self._section_assign,
            "MODEL.SECTION.DELETE": self._section_delete,
            "MODEL.SECTION.QUERY": self._section_query,
            "MODEL.BOUNDARY.ASSIGN": self._boundary_assign,
            "MODEL.BOUNDARY.DELETE": self._boundary_delete,
            "MODEL.BOUNDARY.QUERY": self._boundary_query,
            "MODEL.LOAD.ASSIGN": self._load_assign,
            "MODEL.LOAD.DELETE": self._load_delete,
            "MODEL.LOAD.QUERY": self._load_query,
            "BUILD.COLUMN": self._build_column,
            "ANALYSIS.STATIC": self._analysis_static,
            "RESULT.NODE.DISPLACEMENT": self._result_node_displacement,
            "RESULT.NODE.REACTION": self._result_node_reaction,
            "RESULT.ELEMENT.FORCE": self._result_element_force,
            "RESULT.ELEMENT.STRESS": self._result_element_stress,
            "DESIGN.STEEL": self._design_steel,
        }

    # ===== 节点 handler（`docs/02` §34 / §35）=====

    async def _node_create(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.NODE.CREATE`（`docs/02` §34，返回逐字段照抄）。"""
        node = await self.store.create_node(
            x=_number(parameters, ("x",)),
            y=_number(parameters, ("y",)),
            z=_number(parameters, ("z",)),
            node_id=_optional_integer(parameters, ("id", "node_id")),
        )
        return {"id": node.id, "x": node.x, "y": node.y, "z": node.z}

    async def _node_update(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.NODE.UPDATE`（`docs/02` §35 的「更新」）。"""
        node = await self.store.update_node(
            _integer(parameters, ("node_id", "id")),
            x=_optional_number(parameters, ("x",)),
            y=_optional_number(parameters, ("y",)),
            z=_optional_number(parameters, ("z",)),
        )
        return {"id": node.id, "x": node.x, "y": node.y, "z": node.z}

    async def _node_delete(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.NODE.DELETE`（`docs/02` §35 的「删除」）。"""
        node_id = _integer(parameters, ("node_id", "id"))
        return {"node_id": node_id, "deleted": await self.store.delete_node(node_id)}

    async def _node_query(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.NODE.QUERY`（`docs/02` §35，返回形状逐字段照抄）。"""
        rows = [
            {"id": node.id, "x": node.x, "y": node.y, "z": node.z}
            for node in self.store.all_nodes()
        ]
        return _page(parameters, rows)

    # ===== 单元 handler（`docs/02` §36 / §38）=====

    async def _element_create(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.ELEMENT.CREATE`（`docs/02` §36，返回逐字段照抄）。"""
        element = await self.store.create_element(
            node_ids=_node_id_list(parameters),
            material=_optional_text(parameters, ("material",)),
            section=_optional_text(parameters, ("section",)),
            element_id=_optional_integer(parameters, ("id", "element_id")),
        )
        return {"id": element.id, "node_ids": list(element.node_ids)}

    async def _element_update(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.ELEMENT.UPDATE`（`docs/02` §35 的「更新」）。"""
        element = await self.store.update_element(
            _integer(parameters, ("element_id", "id")),
            node_ids=(
                _node_id_list(parameters) if _first(parameters, ("node_ids",)) is not None else None
            ),
            material=_optional_text(parameters, ("material",)),
            section=_optional_text(parameters, ("section",)),
        )
        return _element_payload(element)

    async def _element_delete(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.ELEMENT.DELETE`（`docs/02` §35 的「删除」）。"""
        element_id = _integer(parameters, ("element_id", "id"))
        return {"element_id": element_id, "deleted": await self.store.delete_element(element_id)}

    async def _element_query(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.ELEMENT.QUERY`（`docs/02` §35 / §61 场景 4）。"""
        rows = [_element_payload(element) for element in self.store.all_elements()]
        return _page(parameters, rows)

    # ===== 材料 / 截面 handler（`docs/02` §43 / §44）=====

    async def _material_assign(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.MATERIAL.ASSIGN`（`docs/02` §43 的键名 `E` / `fy` 照抄）。"""
        material = await self.store.assign_material(_text(parameters, ("code", "material")))
        return _material_payload(material)

    async def _material_delete(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.MATERIAL.DELETE`（`docs/02` §30 的 `MODEL.MATERIAL.*` 语义）。"""
        code = _text(parameters, ("code", "material"))
        return {"code": code, "deleted": await self.store.delete_material(code)}

    async def _material_query(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.MATERIAL.QUERY`（`docs/02` §43）。"""
        rows = [_material_payload(item) for item in self.store.all_materials()]
        return _page(parameters, rows, key=None)

    async def _section_assign(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.SECTION.ASSIGN`（`docs/02` §44 的键名 `area` / `iy` / `iz` 照抄）。"""
        section = await self.store.assign_section(_text(parameters, ("code", "section")))
        return _section_payload(section)

    async def _section_delete(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.SECTION.DELETE`（`docs/02` §30 的 `MODEL.SECTION.*` 语义）。"""
        code = _text(parameters, ("code", "section"))
        return {"code": code, "deleted": await self.store.delete_section(code)}

    async def _section_query(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.SECTION.QUERY`（`docs/02` §44）。"""
        rows = [_section_payload(item) for item in self.store.all_sections()]
        return _page(parameters, rows, key=None)

    # ===== 边界 / 荷载 handler（`docs/02` §39 / §40）=====

    async def _boundary_assign(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.BOUNDARY.ASSIGN`（`docs/02` §39，六个自由度照抄）。"""
        boundary = await self.store.assign_boundary(
            _integer(parameters, ("node_id", "id")),
            ux=_boolean(parameters, ("ux",)),
            uy=_boolean(parameters, ("uy",)),
            uz=_boolean(parameters, ("uz",)),
            rx=_boolean(parameters, ("rx",)),
            ry=_boolean(parameters, ("ry",)),
            rz=_boolean(parameters, ("rz",)),
        )
        return _boundary_payload(boundary)

    async def _boundary_delete(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.BOUNDARY.DELETE`（`docs/02` §30 的 `MODEL.BOUNDARY.*` 语义）。"""
        node_id = _integer(parameters, ("node_id", "id"))
        return {"node_id": node_id, "deleted": await self.store.delete_boundary(node_id)}

    async def _boundary_query(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.BOUNDARY.QUERY`（`docs/02` §39）。"""
        rows = [_boundary_payload(item) for item in self.store.all_boundaries()]
        return _page(parameters, rows, key="node_id")

    async def _load_assign(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.LOAD.ASSIGN`（`docs/02` §40，返回逐字段照抄）。"""
        load = await self.store.assign_load(
            _integer(parameters, ("node_id", "id")),
            fx=_number(parameters, ("fx",), default=0.0),
            fy=_number(parameters, ("fy",), default=0.0),
            fz=_number(parameters, ("fz",), default=0.0),
        )
        return {"node_id": load.node_id, "fx": load.fx, "fy": load.fy, "fz": load.fz}

    async def _load_delete(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.LOAD.DELETE`（`docs/02` §30 的 `MODEL.LOAD.DELETE` 语义）。"""
        node_id = _integer(parameters, ("node_id", "id"))
        return {"node_id": node_id, "deleted": await self.store.delete_load(node_id)}

    async def _load_query(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`MODEL.LOAD.QUERY`（`docs/02` §40）。"""
        rows = [
            {"node_id": item.node_id, "fx": item.fx, "fy": item.fy, "fz": item.fz}
            for item in self.store.all_loads()
        ]
        return _page(parameters, rows, key="node_id")

    # ===== BUILD.COLUMN（`docs/02` §37 / §38 / §90；见裁决 1 / 2）=====

    async def _build_column(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`BUILD.COLUMN`（`docs/02` §37 / §38；返回照抄 §90）。"""
        height = _number(parameters, ("height",))
        if height <= 0:
            raise AdapterValidationError(
                "Column height must be positive",
                details={"stage": "mock_adapter", "reason": "invalid_height"},
            )

        base = parameters.get("base_node")
        base_x, base_y, base_z = 0.0, 0.0, 0.0
        if isinstance(base, Mapping):
            base_x = _number(base, ("x",), default=0.0)
            base_y = _number(base, ("y",), default=0.0)
            base_z = _number(base, ("z",), default=0.0)
        elif base is not None:
            raise AdapterValidationError(
                "base_node must be an object",
                details={"stage": "mock_adapter", "reason": "invalid_base_node"},
            )

        material = _optional_text(parameters, ("material",)) or DEFAULT_MATERIAL
        section = _optional_text(parameters, ("section",)) or DEFAULT_SECTION

        base_id = await self._node_for(
            _optional_integer(parameters, ("base_node_id",)),
            x=base_x,
            y=base_y,
            z=base_z,
        )
        top_id = await self._node_for(
            _optional_integer(parameters, ("top_node_id",)),
            x=base_x,
            y=base_y,
            z=base_z + height,
        )
        await self._register_if_known(material=material, section=section)
        element = await self.store.create_element(
            node_ids=(base_id, top_id),
            material=material,
            section=section,
            element_id=_optional_integer(parameters, ("element_id",)),
        )
        return {"node_ids": [base_id, top_id], "element_ids": [element.id]}

    async def _node_for(self, node_id: int | None, *, x: float, y: float, z: float) -> int:
        """复用既有节点或按给定坐标新建（`docs/02` §38；见裁决 2）。"""
        if node_id is not None and node_id in self.store.nodes:
            return node_id
        node = await self.store.create_node(node_id=node_id, x=x, y=y, z=z)
        return node.id

    async def _register_if_known(self, *, material: str, section: str) -> None:
        """把测试数据表内已知的材料 / 截面登记进 Store（`docs/02` §37 的 ASSIGN 步骤）。

        未知码**不**拒绝：它们仍记在单元上，只是没有 `E` / `A`（结果按 §46 回落，
        见 `analysis.py` 裁决 1）。
        """
        if material in MOCK_MATERIALS:
            await self.store.assign_material(material)
        if section in MOCK_SECTIONS:
            await self.store.assign_section(section)

    # ===== 分析 / 结果 / 设计（`docs/02` §45–§47）=====

    async def _analysis_static(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`ANALYSIS.STATIC`（`docs/02` §45 / §91）。"""
        return analysis.static_analysis(self.store)

    async def _result_node_displacement(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`RESULT.NODE.DISPLACEMENT`（`docs/02` §46）。"""
        return analysis.node_displacement(self.store, _integer(parameters, ("node_id", "id")))

    async def _result_node_reaction(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`RESULT.NODE.REACTION`（`docs/02` §30 的 `RESULT.REACTION`）。"""
        return analysis.node_reaction(self.store, _integer(parameters, ("node_id", "id")))

    async def _result_element_force(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`RESULT.ELEMENT.FORCE`（`docs/02` §30 的 `RESULT.ELEMENT_FORCE`）。"""
        return analysis.element_force(self.store, _integer(parameters, ("element_id", "id")))

    async def _result_element_stress(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`RESULT.ELEMENT.STRESS`（`docs/02` §30 的 `RESULT.STRESS`）。"""
        return analysis.element_stress(self.store, _integer(parameters, ("element_id", "id")))

    async def _design_steel(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """`DESIGN.STEEL`（`docs/02` §47 / §92）。"""
        return analysis.steel_design(self.store, _integer(parameters, ("element_id", "id")))


# ===== 参数规整（handler 只做规整，校验归 Store，见裁决 3）=====


def _first(parameters: Mapping[str, Any], names: Sequence[str]) -> Any:
    """取第一个存在且非 `None` 的同义参数（如 `id` / `node_id`）。"""
    for name in names:
        if name in parameters and parameters[name] is not None:
            return parameters[name]
    return None


def _invalid(parameter: str, reason: str) -> AdapterValidationError:
    """构造参数错误（`STRUCTAI-1200`；`details` 只带参数名，**不**回显原值）。"""
    return AdapterValidationError(
        f"Invalid parameter: {parameter}",
        details={"stage": "mock_adapter", "reason": reason, "parameter": parameter},
    )


def _text(parameters: Mapping[str, Any], names: Sequence[str]) -> str:
    """取必填文本参数（`docs/02` §43 / §44 的 `code`）。"""
    value = _first(parameters, names)
    if value is None:
        raise _invalid(names[0], "missing_parameter")
    if isinstance(value, (Mapping, list, tuple, set)) or isinstance(value, bool):
        raise _invalid(names[0], "invalid_parameter")
    return str(value)


def _optional_text(parameters: Mapping[str, Any], names: Sequence[str]) -> str | None:
    """取可选文本参数；缺失返回 `None`。"""
    return None if _first(parameters, names) is None else _text(parameters, names)


def _as_float(value: Any, parameter: str) -> float:
    """把值规整成浮点数；非法 → `STRUCTAI-1200`。"""
    if isinstance(value, bool) or isinstance(value, (Mapping, list, tuple, set)):
        raise _invalid(parameter, "invalid_parameter")
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise _invalid(parameter, "invalid_parameter") from error


def _as_int(value: Any, parameter: str) -> int:
    """把值规整成整数；非法 / 非整浮点 → `STRUCTAI-1200`。"""
    if isinstance(value, bool) or isinstance(value, (Mapping, list, tuple, set)):
        raise _invalid(parameter, "invalid_parameter")
    if isinstance(value, float) and not value.is_integer():
        raise _invalid(parameter, "invalid_parameter")
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise _invalid(parameter, "invalid_parameter") from error


def _number(
    parameters: Mapping[str, Any],
    names: Sequence[str],
    *,
    default: float | None = None,
) -> float:
    """取数值参数（`docs/02` §34 的 `x` / `y` / `z`；§37 的 `height`）。"""
    value = _first(parameters, names)
    if value is None:
        if default is None:
            raise _invalid(names[0], "missing_parameter")
        return float(default)
    return _as_float(value, names[0])


def _optional_number(parameters: Mapping[str, Any], names: Sequence[str]) -> float | None:
    """取可选数值参数；缺失返回 `None`（表示「不修改该分量」）。"""
    return None if _first(parameters, names) is None else _number(parameters, names)


def _integer(
    parameters: Mapping[str, Any],
    names: Sequence[str],
    *,
    default: int | None = None,
) -> int:
    """取整数参数（节点 / 单元 id）。"""
    value = _first(parameters, names)
    if value is None:
        if default is None:
            raise _invalid(names[0], "missing_parameter")
        return int(default)
    return _as_int(value, names[0])


def _optional_integer(parameters: Mapping[str, Any], names: Sequence[str]) -> int | None:
    """取可选整数参数；缺失返回 `None`（表示「自动分配」，`docs/02` §35）。"""
    return None if _first(parameters, names) is None else _integer(parameters, names)


def _boolean(parameters: Mapping[str, Any], names: Sequence[str]) -> bool:
    """取布尔参数（`docs/02` §39 的六个自由度）；缺失按 `False`。"""
    value = _first(parameters, names)
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n", ""}:
            return False
        raise _invalid(names[0], "invalid_parameter")
    if isinstance(value, (int, float)):
        return bool(value)
    raise _invalid(names[0], "invalid_parameter")


def _node_id_list(
    parameters: Mapping[str, Any],
    names: Sequence[str] = ("node_ids",),
) -> tuple[int, ...]:
    """取节点 id 序列（`docs/02` §36 的 `node_ids`；至少 1 个）。"""
    value = _first(parameters, names)
    if value is None:
        raise _invalid(names[0], "missing_parameter")
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, (list, tuple)):
        raise _invalid(names[0], "invalid_parameter")
    if not value:
        raise _invalid(names[0], "invalid_parameter")
    return tuple(_as_int(item, names[0]) for item in value)


def _page(
    parameters: Mapping[str, Any],
    rows: Sequence[dict[str, Any]],
    *,
    key: str | None = "id",
) -> dict[str, Any]:
    """组装 `{"items": [...], "pagination": {...}}`（`docs/02` §35；见裁决 4）。

    Args:
        parameters: 请求参数；可选 `limit`（≥1）与 `cursor`（上一页最后一条的键值）。
        rows: 已排序的行。
        key: 游标字段；`None` 表示该集合不支持游标（如按 `code` 索引的材料 / 截面）。

    Returns:
        不传 `limit` 时与 `docs/02` §35 完全一致（`has_more = False` /
        `next_cursor = None`）。

    Raises:
        AdapterValidationError: `STRUCTAI-1200` —— `limit` < 1 或非法。
    """
    limit = _optional_integer(parameters, ("limit",))
    if limit is not None and limit < 1:
        raise _invalid("limit", "invalid_parameter")
    selected = list(rows)
    if key is not None:
        cursor = _optional_integer(parameters, ("cursor",))
        if cursor is not None:
            selected = [row for row in rows if int(row[key]) > cursor]
    if limit is None:
        return {"items": selected, "pagination": dict(PAGINATION_FALSE)}
    window = selected[:limit]
    has_more = len(selected) > len(window)
    next_cursor = int(window[-1][key]) if has_more and window and key is not None else None
    return {
        "items": window,
        "pagination": {"has_more": has_more, "next_cursor": next_cursor},
    }


# ===== 结果形状（`docs/02` §27 / §39 / §43 / §44 的字段名照抄）=====


def _element_payload(element: MockElement) -> dict[str, Any]:
    """单元行（`docs/02` §27 的字段）。"""
    return {
        "id": element.id,
        "node_ids": list(element.node_ids),
        "material": element.material,
        "section": element.section,
    }


def _material_payload(material: MockMaterial) -> dict[str, Any]:
    """材料行（`docs/02` §43 的键名 `E` / `fy`）。"""
    return {
        "code": material.code,
        "E": material.elastic_modulus,
        "fy": material.yield_strength,
    }


def _section_payload(section: MockSection) -> dict[str, Any]:
    """截面行（`docs/02` §44 的键名 `area` / `iy` / `iz`）。"""
    return {
        "code": section.code,
        "area": section.area,
        "iy": section.iy,
        "iz": section.iz,
    }


def _boundary_payload(boundary: MockBoundary) -> dict[str, Any]:
    """边界条件行（`docs/02` §39 的六个自由度）。"""
    return {
        "node_id": boundary.node_id,
        "ux": boundary.ux,
        "uy": boundary.uy,
        "uz": boundary.uz,
        "rx": boundary.rx,
        "ry": boundary.ry,
        "rz": boundary.rz,
    }
