"""Infrastructure · Adapters · Mock · Model Store —— 进程内模型状态（`docs/02` §27 / §28 / §35）。

权威来源
--------
- `docs/02` §27（`adapter`）—— `MockNode` / `MockElement` / `MockLoad` 三个 dataclass 的字段。
- `docs/02` §28（`adapter`）—— `MockModelStore` 的六个容器（`nodes` / `elements` /
  `loads` / `materials` / `sections` / `boundaries`）与 `clear()`。
- `docs/02` §35（`source7`）—— Mock Model Store 的硬要求：
  **线程 / 协程安全、ID 自动分配、版本控制、查询、更新、删除**。
- `docs/02` §34 / §36 / §39 / §40（`adapter`）—— 各操作对状态的具体写法
  （重复 id 拒绝、节点必须存在、`boundaries` / `loads` 以 `node_id` 为键）。
- `docs/02` §43 / §44（`adapter`）—— `MATERIALS` / `SECTIONS` 两张**测试数据**表。
- `docs/02` §38（`adapter`）—— `BUILD.COLUMN` 的默认材料 / 截面。

落地裁决（只补实现手段，不改字段名 / 取值）
------------------------------------------
1. **`boundaries` / `loads` 用 `dict[node_id, ...]`**：`docs/02` §35 的摘要写作
   `list[dict]`，而 §28（`self.loads = {}`）与 §39 / §40（`self.store.loads[node_id] = ...`）
   的**可执行代码**都是字典。以代码为准（§39 / §40 是唯一给出写法的章节），
   并补一个 `MockBoundary` 记录类型把 §39 的六个布尔自由度**类型化**。
2. **原生错误用 `AdapterValidationError`（→ `STRUCTAI-1200`）**：`docs/02` §34 的
   `MockDuplicateError` 与 §36 / §39 / §40 的 `MockValidationError` 在 §49 里
   **都映射到 `STRUCTAI-1200`**。本模块不再区分两个类，统一用
   `AdapterValidationError` + `details.reason`（`duplicate_node` / `node_not_found` /
   `duplicate_element` / `material_not_found` / `section_not_found` …）——
   错误码契约不变，诊断信息更细（见 `base/errors.py`）。
3. **校验放在 Store，不放在 Handler**：§36 在 handler 里校验节点存在性；若 handler 与
   Store 各写一遍，两条路径会漂移。本模块把「节点必须存在」「id 不得重复」
   收敛到 Store 的**唯一**实现点，handler 只做参数规整。
4. **协程安全用 `asyncio.Lock`**：§35 要求「线程 / 协程安全」。所有**写**方法都在
   锁内完成「校验 + 写入 + 版本自增」；只读查询方法直接读（Store 只被单个事件循环
   使用，读操作不会看到半成品 —— 写入在锁内是原子的）。
5. **版本控制在 Store 上**：§35 要求「版本控制」。每次成功写入 `version += 1`；
   `clear()` 复位为 `0`。该版本号是 **Mock 侧的模型版本**，与
   `docs/02` §12 的乐观并发版本（数据库 `version` 列）无关，**不**写库。
6. **`clear()` 保持同步**（照抄 §28）：它只用于测试 / 装配隔离，调用方在
   `await` 之外使用；实现上不持锁（测试串行调用）。

分层红线（`docs/07` §14.1 / §14.2 / §14.3）
------------------------------------------
本模块只依赖标准库与同层的 `base/errors`（**不**引用 SQLAlchemy / FastAPI / MCP SDK /
httpx，**不**依赖 `app.interfaces`）；**不**写表、**不** `commit`、**不**记录 secret。
`MATERIALS` / `SECTIONS` 是**测试数据**，不是规范数据库（`docs/02` §43 / §44）。
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Final

from app.infrastructure.adapters.base.errors import AdapterValidationError

__all__ = [
    "DEFAULT_MATERIAL",
    "DEFAULT_SECTION",
    "MOCK_MATERIALS",
    "MOCK_SECTIONS",
    "MockBoundary",
    "MockElement",
    "MockLoad",
    "MockMaterial",
    "MockModelStore",
    "MockNode",
    "MockSection",
]

DEFAULT_MATERIAL: Final[str] = "Q355B"
"""`BUILD.COLUMN` 的默认材料（`docs/02` §38）。"""

DEFAULT_SECTION: Final[str] = "H400x400x13x21"
"""`BUILD.COLUMN` 的默认截面（`docs/02` §38）。"""


# ===== 记录类型（`docs/02` §27 / §39 / §43 / §44）=====


@dataclass(frozen=True, slots=True)
class MockNode:
    """节点（`docs/02` §27，逐字段照抄）。"""

    id: int
    x: float
    y: float
    z: float


@dataclass(frozen=True, slots=True)
class MockElement:
    """单元（`docs/02` §27，逐字段照抄）。"""

    id: int
    node_ids: tuple[int, ...]
    material: str | None = None
    section: str | None = None


@dataclass(frozen=True, slots=True)
class MockLoad:
    """节点荷载（`docs/02` §27 / §40，逐字段照抄）。"""

    node_id: int
    fx: float
    fy: float
    fz: float


@dataclass(frozen=True, slots=True)
class MockBoundary:
    """节点边界条件（`docs/02` §39 的六个自由度，类型化）。"""

    node_id: int
    ux: bool = False
    uy: bool = False
    uz: bool = False
    rx: bool = False
    ry: bool = False
    rz: bool = False


@dataclass(frozen=True, slots=True)
class MockMaterial:
    """材料测试数据（`docs/02` §43；`E` / `fy` 照抄）。"""

    code: str
    elastic_modulus: float
    yield_strength: float


@dataclass(frozen=True, slots=True)
class MockSection:
    """截面测试数据（`docs/02` §44；`area` / `iy` / `iz` 照抄）。"""

    code: str
    area: float
    iy: float
    iz: float


MOCK_MATERIALS: Final[Mapping[str, MockMaterial]] = MappingProxyType(
    {
        "Q355B": MockMaterial(code="Q355B", elastic_modulus=2.06e11, yield_strength=355e6),
        "Q235B": MockMaterial(code="Q235B", elastic_modulus=2.06e11, yield_strength=235e6),
    }
)
"""材料表（`docs/02` §43，逐条照抄；⚠️ **测试数据**，不是规范数据库）。"""

MOCK_SECTIONS: Final[Mapping[str, MockSection]] = MappingProxyType(
    {
        "H400x400x13x21": MockSection(code="H400x400x13x21", area=0.025, iy=0.20, iz=0.20),
    }
)
"""截面表（`docs/02` §44，逐条照抄；⚠️ **测试数据**，不是规范数据库）。"""


# ===== 进程内状态（`docs/02` §28 / §35）=====


class MockModelStore:
    """Mock 的进程内模型状态（`docs/02` §28 / §35）。

    - **协程安全**：所有写方法在 `asyncio.Lock` 内完成「校验 + 写入 + 版本自增」（§35）。
    - **ID 自动分配**：`create_node()` / `create_element()` 不传 id 时按当前最大 id + 1
      分配（§35）。
    - **版本控制**：每次成功写入 `version += 1`（§35）。
    - **查询 / 更新 / 删除**：每个实体族都有对应方法（§35）。

    ⚠️ 一个 Store 只属于一个 Adapter 实例；`AdapterManager.bind_instance()` 为每个软件实例
    创建独立 Adapter（因此状态天然隔离，`docs/02` §14）。
    """

    def __init__(self) -> None:
        """初始化六个容器（`docs/02` §28）与并发 / 版本状态。"""
        self.nodes: dict[int, MockNode] = {}
        self.elements: dict[int, MockElement] = {}
        self.loads: dict[int, MockLoad] = {}
        self.materials: dict[str, MockMaterial] = {}
        self.sections: dict[str, MockSection] = {}
        self.boundaries: dict[int, MockBoundary] = {}
        self._lock = asyncio.Lock()
        self._version = 0

    # ===== 版本 / 摘要（`docs/02` §35）=====

    @property
    def version(self) -> int:
        """Mock 侧模型版本（每次成功写入自增；见裁决 5）。"""
        return self._version

    def summary(self) -> dict[str, int]:
        """各类实体计数 + 版本（诊断 / 验收证据；**不含**任何 secret）。"""
        return {
            "version": self._version,
            "nodes": len(self.nodes),
            "elements": len(self.elements),
            "loads": len(self.loads),
            "materials": len(self.materials),
            "sections": len(self.sections),
            "boundaries": len(self.boundaries),
        }

    def clear(self) -> None:
        """清空全部状态并复位版本（`docs/02` §28；见裁决 6）。"""
        self.nodes.clear()
        self.elements.clear()
        self.loads.clear()
        self.materials.clear()
        self.sections.clear()
        self.boundaries.clear()
        self._version = 0

    # ===== 节点（`docs/02` §34 / §35）=====

    async def create_node(
        self,
        *,
        x: float,
        y: float,
        z: float,
        node_id: int | None = None,
    ) -> MockNode:
        """新建节点（`docs/02` §34 / §35）。

        Args:
            x: X 坐标。
            y: Y 坐标。
            z: Z 坐标。
            node_id: 指定 id；缺省按「当前最大 id + 1」自动分配（§35）。

        Returns:
            新建的节点。

        Raises:
            AdapterValidationError: `STRUCTAI-1200` —— id 已存在（§34 的
                `MockDuplicateError` 口径）。
        """
        async with self._lock:
            target = self._next_node_id() if node_id is None else int(node_id)
            if target in self.nodes:
                raise AdapterValidationError(
                    "Node already exists",
                    details={"stage": "mock_model_store", "reason": "duplicate_node"},
                )
            node = MockNode(id=target, x=float(x), y=float(y), z=float(z))
            self.nodes[target] = node
            self._version += 1
            return node

    async def update_node(
        self,
        node_id: int,
        *,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
    ) -> MockNode:
        """更新节点坐标（`docs/02` §35 的「更新」）。

        Raises:
            AdapterValidationError: `STRUCTAI-1200` —— 节点不存在。
        """
        async with self._lock:
            current = self._require_node(node_id)
            node = replace(
                current,
                x=current.x if x is None else float(x),
                y=current.y if y is None else float(y),
                z=current.z if z is None else float(z),
            )
            self.nodes[int(node_id)] = node
            self._version += 1
            return node

    async def delete_node(self, node_id: int) -> bool:
        """删除节点及其边界 / 荷载（`docs/02` §35 的「删除」）。

        Returns:
            是否真的删除了节点。
        """
        async with self._lock:
            target = int(node_id)
            if target not in self.nodes:
                return False
            del self.nodes[target]
            self.boundaries.pop(target, None)
            self.loads.pop(target, None)
            self._version += 1
            return True

    def node(self, node_id: int) -> MockNode | None:
        """按 id 查询节点；不存在返回 `None`（`docs/02` §35 的「查询」）。"""
        return self.nodes.get(int(node_id))

    def all_nodes(self) -> tuple[MockNode, ...]:
        """全部节点（按 id 升序，输出确定性）。"""
        return tuple(self.nodes[key] for key in sorted(self.nodes))

    # ===== 单元（`docs/02` §36 / §37 / §38）=====

    async def create_element(
        self,
        *,
        node_ids: Iterable[int],
        material: str | None = None,
        section: str | None = None,
        element_id: int | None = None,
    ) -> MockElement:
        """新建单元（`docs/02` §36 / §38）。

        Args:
            node_ids: 组成单元的节点 id 序列；**每个**节点都必须已存在（§36）。
            material: 材料码（可为空）。
            section: 截面码（可为空）。
            element_id: 指定 id；缺省按「当前最大 id + 1」自动分配（§35）。

        Returns:
            新建的单元。

        Raises:
            AdapterValidationError: `STRUCTAI-1200` —— 节点不存在（§36）或 id 已存在。
        """
        async with self._lock:
            members = tuple(int(node_id) for node_id in node_ids)
            for node_id in members:
                if node_id not in self.nodes:
                    raise AdapterValidationError(
                        f"Node not found: {node_id}",
                        details={"stage": "mock_model_store", "reason": "node_not_found"},
                    )
            target = self._next_element_id() if element_id is None else int(element_id)
            if target in self.elements:
                raise AdapterValidationError(
                    "Element already exists",
                    details={"stage": "mock_model_store", "reason": "duplicate_element"},
                )
            element = MockElement(
                id=target,
                node_ids=members,
                material=None if material is None else str(material),
                section=None if section is None else str(section),
            )
            self.elements[target] = element
            self._version += 1
            return element

    async def update_element(
        self,
        element_id: int,
        *,
        node_ids: Iterable[int] | None = None,
        material: str | None = None,
        section: str | None = None,
    ) -> MockElement:
        """更新单元（`docs/02` §35 的「更新」）。

        Raises:
            AdapterValidationError: `STRUCTAI-1200` —— 单元不存在或节点不存在。
        """
        async with self._lock:
            target = int(element_id)
            current = self.elements.get(target)
            if current is None:
                raise AdapterValidationError(
                    "Element not found",
                    details={"stage": "mock_model_store", "reason": "element_not_found"},
                )
            members = current.node_ids if node_ids is None else tuple(int(n) for n in node_ids)
            for node_id in members:
                if node_id not in self.nodes:
                    raise AdapterValidationError(
                        f"Node not found: {node_id}",
                        details={"stage": "mock_model_store", "reason": "node_not_found"},
                    )
            element = replace(
                current,
                node_ids=members,
                material=current.material if material is None else str(material),
                section=current.section if section is None else str(section),
            )
            self.elements[target] = element
            self._version += 1
            return element

    async def delete_element(self, element_id: int) -> bool:
        """删除单元（`docs/02` §35 的「删除」）。"""
        async with self._lock:
            target = int(element_id)
            if target not in self.elements:
                return False
            del self.elements[target]
            self._version += 1
            return True

    def element(self, element_id: int) -> MockElement | None:
        """按 id 查询单元（`docs/02` §35 的「查询」）。"""
        return self.elements.get(int(element_id))

    def all_elements(self) -> tuple[MockElement, ...]:
        """全部单元（按 id 升序）。"""
        return tuple(self.elements[key] for key in sorted(self.elements))

    # ===== 材料 / 截面（`docs/02` §43 / §44）=====

    async def assign_material(self, code: str) -> MockMaterial:
        """登记材料（`docs/02` §43 的表）。

        Raises:
            AdapterValidationError: `STRUCTAI-1200` —— 材料码不在测试数据表内。
        """
        async with self._lock:
            material = MOCK_MATERIALS.get(str(code))
            if material is None:
                raise AdapterValidationError(
                    "Material not found",
                    details={"stage": "mock_model_store", "reason": "material_not_found"},
                )
            self.materials[material.code] = material
            self._version += 1
            return material

    async def delete_material(self, code: str) -> bool:
        """移除材料（`docs/02` §30 的 `MODEL.MATERIAL.*` 语义）。"""
        async with self._lock:
            removed = self.materials.pop(str(code), None) is not None
            if removed:
                self._version += 1
            return removed

    def all_materials(self) -> tuple[MockMaterial, ...]:
        """已登记的材料（按 code 升序）。"""
        return tuple(self.materials[key] for key in sorted(self.materials))

    async def assign_section(self, code: str) -> MockSection:
        """登记截面（`docs/02` §44 的表）。

        Raises:
            AdapterValidationError: `STRUCTAI-1200` —— 截面码不在测试数据表内。
        """
        async with self._lock:
            section = MOCK_SECTIONS.get(str(code))
            if section is None:
                raise AdapterValidationError(
                    "Section not found",
                    details={"stage": "mock_model_store", "reason": "section_not_found"},
                )
            self.sections[section.code] = section
            self._version += 1
            return section

    async def delete_section(self, code: str) -> bool:
        """移除截面（`docs/02` §30 的 `MODEL.SECTION.*` 语义）。"""
        async with self._lock:
            removed = self.sections.pop(str(code), None) is not None
            if removed:
                self._version += 1
            return removed

    def all_sections(self) -> tuple[MockSection, ...]:
        """已登记的截面（按 code 升序）。"""
        return tuple(self.sections[key] for key in sorted(self.sections))

    # ===== 边界 / 荷载（`docs/02` §39 / §40）=====

    async def assign_boundary(
        self,
        node_id: int,
        *,
        ux: bool = False,
        uy: bool = False,
        uz: bool = False,
        rx: bool = False,
        ry: bool = False,
        rz: bool = False,
    ) -> MockBoundary:
        """指派节点边界条件（`docs/02` §39）。

        Raises:
            AdapterValidationError: `STRUCTAI-1200` —— 节点不存在（§39 的
                `MockValidationError` 口径）。
        """
        async with self._lock:
            target = int(node_id)
            if target not in self.nodes:
                raise AdapterValidationError(
                    "Node does not exist",
                    details={"stage": "mock_model_store", "reason": "node_not_found"},
                )
            boundary = MockBoundary(
                node_id=target,
                ux=bool(ux),
                uy=bool(uy),
                uz=bool(uz),
                rx=bool(rx),
                ry=bool(ry),
                rz=bool(rz),
            )
            self.boundaries[target] = boundary
            self._version += 1
            return boundary

    async def delete_boundary(self, node_id: int) -> bool:
        """移除节点边界条件（`docs/02` §30 的 `MODEL.BOUNDARY.*` 语义）。"""
        async with self._lock:
            removed = self.boundaries.pop(int(node_id), None) is not None
            if removed:
                self._version += 1
            return removed

    def boundary(self, node_id: int) -> MockBoundary | None:
        """按节点 id 查询边界条件（`docs/02` §35 的「查询」）。"""
        return self.boundaries.get(int(node_id))

    def all_boundaries(self) -> tuple[MockBoundary, ...]:
        """全部边界条件（按 node_id 升序）。"""
        return tuple(self.boundaries[key] for key in sorted(self.boundaries))

    async def assign_load(
        self,
        node_id: int,
        *,
        fx: float = 0.0,
        fy: float = 0.0,
        fz: float = 0.0,
    ) -> MockLoad:
        """指派节点荷载（`docs/02` §40）。

        Raises:
            AdapterValidationError: `STRUCTAI-1200` —— 节点不存在（§40 的
                `MockValidationError` 口径）。
        """
        async with self._lock:
            target = int(node_id)
            if target not in self.nodes:
                raise AdapterValidationError(
                    "Node does not exist",
                    details={"stage": "mock_model_store", "reason": "node_not_found"},
                )
            load = MockLoad(
                node_id=target,
                fx=float(fx),
                fy=float(fy),
                fz=float(fz),
            )
            self.loads[target] = load
            self._version += 1
            return load

    async def delete_load(self, node_id: int) -> bool:
        """移除节点荷载（`docs/02` §30 的 `MODEL.LOAD.DELETE` 语义）。"""
        async with self._lock:
            removed = self.loads.pop(int(node_id), None) is not None
            if removed:
                self._version += 1
            return removed

    def load(self, node_id: int) -> MockLoad | None:
        """按节点 id 查询荷载（`docs/02` §35 的「查询」）。"""
        return self.loads.get(int(node_id))

    def all_loads(self) -> tuple[MockLoad, ...]:
        """全部荷载（按 node_id 升序）。"""
        return tuple(self.loads[key] for key in sorted(self.loads))

    # ===== 内部（**必须**在锁内调用）=====

    def _next_node_id(self) -> int:
        """下一个可用节点 id（`docs/02` §35 的「ID 自动分配」）。"""
        return max(self.nodes, default=0) + 1

    def _next_element_id(self) -> int:
        """下一个可用单元 id（`docs/02` §35 的「ID 自动分配」）。"""
        return max(self.elements, default=0) + 1

    def _require_node(self, node_id: int) -> MockNode:
        """取节点；不存在 → `STRUCTAI-1200`（§36 / §39 / §40 的统一口径）。"""
        node = self.nodes.get(int(node_id))
        if node is None:
            raise AdapterValidationError(
                "Node does not exist",
                details={"stage": "mock_model_store", "reason": "node_not_found"},
            )
        return node
