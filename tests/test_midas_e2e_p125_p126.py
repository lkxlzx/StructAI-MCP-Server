"""P125–P126 验收：CIVIL NX / GEN NX E2E 与第二软件验证（`docs/04` §73–§77 / §154）。

权威来源
--------
- `docs/04` §73（CIVIL NX E2E 八步）/ §74（完整工程 E2E）/ §75（预期 MCP 行为）。
- `docs/04` §76（GEN NX Adapter 共享 Core 契约）/ §77（GEN NX E2E 链路）。
- `docs/04` §154（第二软件接入原则）—— 接入 ETABS/SAP2000 **不应该**修改 9 MCP Tools /
  Task Engine / RBAC / MCP Session / Core Execution Pipeline；只增加 Adapter / Registry /
  Schema / Transformer / Capability Mapping / Contract Test。
- `docs/07` §13.5 —— 第一条 E2E 的 Prompt 与五步链。

落地裁决（本环境的**硬事实**，不美化）
------------------------------------
1. **L4/L5（真实实例）在本机不可执行**：`docs/04` §72 要求专用实例 / 专用 API Key /
   专用项目 / 专用测试模型；本机既无凭据也无实例（`docs/07` §15.4 还记录云端中继间歇掉线）。
   故 E2E 在 **L3（Mock Transport）** 层执行（§71 明确把 L3 归 CI），
   并逐条断言「请求与 `docs/07` §6 的映射一致 + 响应被正确解析」。
   **不**声称已对真实 MIDAS 实例跑通。
2. **`allow_unverified=True` 只用于 Contract/E2E 模式**：E2E 链上的 `DOC.*` / `POST.*`
   在数据里是 `PARTIAL`，生产路径会被 `RegistryMappingNotVerified` 拒绝
   （见 `test_midas_p119_p123.py` 的门槛 ④ 断言）。
3. **第二软件验证用测试侧 Adapter**：`docs/07` §14.2 禁止 Core 出现厂商名，
   故第二软件（OpenSees）的 Adapter **只**存在于测试里 —— 这本身就是
   「架构软件无关」的最强证据：加一个软件**不**需要动 Core。
"""

from __future__ import annotations

from typing import Any

import pytest

import midas_p119_p126_support as support
from app.infrastructure.adapters.base.adapter import BaseAdapter
from app.infrastructure.adapters.base.errors import AdapterCapabilityError, normalize_error
from app.infrastructure.adapters.base.manager import AdapterManager
from app.infrastructure.adapters.midas.operations import select_steps

_NO_CONTEXT: Any = None
"""测试用的占位执行上下文（Adapter 侧只做转发，见 `tests/test_midas_p119_p123.py`）。"""

SECOND_SOFTWARE_VENDOR = "OpenSees"
SECOND_SOFTWARE_PRODUCT = "OpenSees"
SECOND_SOFTWARE_VERSION = "3.7"
SECOND_SOFTWARE_CAPABILITY = "MODEL.NODE.WRITE"


class SecondSoftwareAdapter(BaseAdapter):
    """测试侧的第二个软件 Adapter（`docs/04` §154 的「只增加 Adapter」）。

    ⚠️ 它**不**在 `app/` 里 —— 加一个软件不该改动 Core（`docs/07` §14.2 / §14.5）。
    """

    name = "structai.second"
    vendor = SECOND_SOFTWARE_VENDOR
    product = SECOND_SOFTWARE_PRODUCT
    supported_versions = (SECOND_SOFTWARE_VERSION,)
    protocols = ("IN_PROCESS",)
    capabilities = ()

    def __init__(self) -> None:
        """初始化（**不**做 I/O）。"""
        super().__init__()
        self.connected = False
        self.executed: list[str] = []

    async def _connect(self, config: dict[str, Any]) -> None:
        """原生连接钩子。"""
        self.connected = True

    async def _disconnect(self) -> None:
        """原生断开钩子。"""
        self.connected = False

    async def health_check(self) -> dict[str, Any]:
        """`docs/02` §25 的四键形状。"""
        return {
            "healthy": self.connected,
            "state": "READY" if self.connected else "ERROR",
            "version": SECOND_SOFTWARE_VERSION,
            "latency_ms": 0,
        }

    async def get_version(self) -> str:
        """软件版本。"""
        return SECOND_SOFTWARE_VERSION

    async def get_capabilities(self) -> list[str]:
        """运行时能力（软件无关词表）。"""
        return [SECOND_SOFTWARE_CAPABILITY]

    async def execute(
        self, operation: str, parameters: dict[str, Any], context: Any
    ) -> dict[str, Any]:
        """规范化执行（只回显规范化结果，**不**暴露任何软件原始字段）。"""
        self.executed.append(operation)
        return {"operation": operation, "nodes": list(parameters.get("nodes") or [])}

    async def cancel(self, task_id: str) -> None:
        """**明确失败**：该软件没有取消入口（**不**伪造取消，`docs/07` §14.4）。"""
        raise AdapterCapabilityError("cancel_not_supported", details={"task_id": str(task_id)})

    def normalize_error(self, error: Exception) -> dict[str, Any]:
        """委托 20 码的**唯一**归一化点（`docs/02` §49 / §50）。"""
        return normalize_error(error)


# ===== P125：CIVIL NX / GEN NX E2E（L3 层）=====


async def test_p125_civil_nx_first_e2e_chain() -> None:
    """`docs/04` §73 的**八步**链：Connect → Health → Version → Node CRUD → Save。"""
    transport = support.RecordingTransport()
    adapter = support.adapter(transport=transport)
    observed: list[str] = []

    await adapter.connect(support.connect_config())
    observed.append("connect")
    health = await adapter.health_check()
    observed.append("health")
    assert health["healthy"] is True and health["state"] == "READY"
    version = await adapter.get_version()
    observed.append("version")
    assert version == "2026"

    query = await adapter.execute_normalized("MODEL.NODE.QUERY", {}, _NO_CONTEXT)
    observed.append("node_query")
    assert query["executed"][0]["endpoint"] == "DB.NODE"
    assert query["data"]["read"][0]["x"] == 0.0

    created = await adapter.execute_normalized(
        "MODEL.NODE.CREATE", {"nodes": [{"id": 9, "x": 1.0, "y": 2.0, "z": 3.0}]}, _NO_CONTEXT
    )
    observed.append("node_create")
    assert created["executed"][0]["endpoint"] == "DB.NODE"

    again = await adapter.execute_normalized("MODEL.NODE.QUERY", {}, _NO_CONTEXT)
    observed.append("node_query_again")
    assert again["executed"][0]["uri"] == "/DB/NODE"

    deleted = await adapter.execute_normalized("MODEL.NODE.DELETE", {"item_ids": [9]}, _NO_CONTEXT)
    observed.append("node_delete")
    assert transport.paths()[-1] == "/DB/NODE/9"

    await adapter.execute_normalized("SAVE", {"arguments": {}}, _NO_CONTEXT)
    observed.append("document_save")
    assert transport.paths()[-1] == "/DOC/SAVE"
    await adapter.disconnect()

    assert tuple(observed) == support.CIVIL_NX_FIRST_E2E_SPEC
    assert deleted["executed"][0]["method"] == "DELETE"


async def test_p125_civil_nx_full_project_chain_follows_docs_07_section_6() -> None:
    """`docs/04` §74 / `docs/07` §13.5：五步链，且每步的端点序列与 §6 映射**逐条**一致。"""
    transport = support.RecordingTransport()
    adapter = support.adapter(transport=transport)
    await adapter.connect(support.connect_config())

    load = {
        "load_type": "NODE_FORCE",
        "load": {"id": 1, "load_case": "AXIAL", "fz": -500_000.0},
    }
    expected: dict[str, list[str]] = {}
    for operation in support.END_TO_END_OPERATIONS_SPEC:
        parameters: dict[str, Any] = {}
        if operation == "BUILD.COLUMN":
            parameters = dict(support.CIVIL_NX_COLUMN_PARAMETERS)
        elif operation == "MODEL.LOAD.ASSIGN":
            parameters = load
        elif operation == "ANALYSIS.STATIC":
            parameters = {"analysis_type": "STATIC"}
        elif operation == "RESULT.NODE.DISPLACEMENT":
            parameters = {"node_ids": [2], "load_cases": ["AXIAL"]}
        elif operation == "DESIGN.STEEL":
            parameters = {"perform_type": "DESIGN"}
        transport.clear()
        outcome = await adapter.execute_normalized(operation, parameters, _NO_CONTEXT)
        executed = [step["endpoint"] for step in outcome["executed"]]
        expected[operation] = [step.key for step in select_steps(operation, parameters)]
        assert executed == expected[operation], operation
        # 请求的 (method, path) 必须落在 Registry 的该端点定义上
        for step in outcome["executed"]:
            definition = support.registry().endpoint(step["endpoint"])
            assert step["method"] in (definition.methods or (step["method"],))

    result = await adapter.execute_normalized(
        "RESULT.NODE.DISPLACEMENT", {"node_ids": [2]}, _NO_CONTEXT
    )
    row = result["data"]["result"]["rows"][0]
    assert row["node_id"] == "2" and row["uz"] == pytest.approx(support.DISPLACEMENT_UZ_M)
    design = await adapter.execute_normalized(
        "DESIGN.STEEL", {"perform_type": "DESIGN"}, _NO_CONTEXT
    )
    table = design["data"]["design_result"]
    assert table["rows"][0]["ratio"] == pytest.approx(support.DESIGN_RATIO)
    assert table["rows"][0]["status"] == "PASS"
    await adapter.disconnect()


async def test_p125_gen_nx_e2e_chain_uses_the_same_implementation() -> None:
    """`docs/04` §76 / §77：GEN NX 与 CIVIL NX 共享同一实现，只换产品视图。"""
    transport = support.RecordingTransport()
    adapter = support.adapter(transport=transport, product="GEN NX")
    await adapter.connect(support.connect_config())
    assert adapter.product == "CIVIL NX"  # Manifest 的注册键（`docs/07` §7.1）
    assert adapter.product_key == "GEN_NX"  # 实例级产品视图

    queries: tuple[tuple[str, dict[str, Any]], ...] = (
        ("MODEL.NODE.QUERY", {}),
        ("MODEL.ELEMENT.QUERY", {}),
        ("MODEL.MATERIAL.QUERY", {}),
        ("MODEL.SECTION.QUERY", {}),
        ("MODEL.BOUNDARY.QUERY", {}),
    )
    for operation, parameters in queries:
        outcome = await adapter.execute_normalized(operation, parameters, _NO_CONTEXT)
        assert outcome["product"] == "GEN NX"
        assert outcome["executed"][0]["endpoint"] in {
            "DB.NODE",
            "DB.ELEM",
            "DB.MATL",
            "DB.SECT",
            "DB.CONS",
        }
    capabilities = await adapter.get_capabilities()
    assert "MODEL.NODE.READ" in capabilities
    await adapter.disconnect()


async def test_p125_designer_product_overrides_drive_the_request_shape() -> None:
    """`docs/07` §7.6（`registry/README.md` §4 的 `product_overrides`）：Designer 为**扁平**体。"""
    registry = support.registry()
    designer = registry.resolve(key="DB.MEMB", product="CIVIL_DESIGNER", method="POST")
    assert designer.is_flat is True
    assert designer.requires_array_body is True
    assert designer.uri == "/DB/MEMB"
    nx = registry.resolve(key="DB.NODE", product="CIVIL_NX", method="POST")
    assert nx.is_flat is False
    assert nx.wrapper_write == "Assign"


# ===== P126：第二软件验证（`docs/04` §154）=====


async def test_p126_second_software_runs_on_the_same_core_contract() -> None:
    """`docs/04` §154：同一 `AdapterManager` 上再加一个软件，**不**改任何 Core 契约。"""
    manager = AdapterManager()
    midas_manifest = manager.register(support.adapter())
    assert midas_manifest.product == "CIVIL NX"
    second = SecondSoftwareAdapter()
    second_manifest = manager.register(second)
    assert second_manifest.vendor == SECOND_SOFTWARE_VENDOR
    assert manager.registered_keys() == (
        ("MIDAS", "CIVIL NX"),
        (SECOND_SOFTWARE_VENDOR, SECOND_SOFTWARE_PRODUCT),
    )

    manager.bind_instance(
        "second-1", vendor=SECOND_SOFTWARE_VENDOR, product=SECOND_SOFTWARE_PRODUCT
    )
    health = await manager.connect("second-1")
    assert health["healthy"] is True
    result = await manager.execute(
        "second-1",
        "MODEL.NODE.CREATE",
        {"nodes": [{"id": 1, "x": 0.0, "y": 0.0, "z": 0.0}]},
        _NO_CONTEXT,
    )
    assert result == {
        "operation": "MODEL.NODE.CREATE",
        "nodes": [{"id": 1, "x": 0.0, "y": 0.0, "z": 0.0}],
    }
    bound = manager.adapter_for_instance("second-1")
    assert isinstance(bound, SecondSoftwareAdapter)
    assert bound.executed == ["MODEL.NODE.CREATE"]
    assert manager.runtime_capabilities("second-1") == frozenset({SECOND_SOFTWARE_CAPABILITY})
    with pytest.raises(Exception) as cancel_failure:
        await manager.cancel("second-1", "task-1")
    assert getattr(cancel_failure.value, "code", "") == "STRUCTAI-3000"
    await manager.disconnect_all()


def test_p126_second_software_needs_no_core_change() -> None:
    """`docs/04` §154：只增加 Adapter / Registry / Schema / Transformer / Capability Mapping。

    可执行判据：9 Tool 契约与容器形状不变；`app/` 里**没有**第二软件的任何字样
    （它的 Adapter 只存在于测试侧）。
    """
    from app.container import AppContainer

    assert len(AppContainer.__dataclass_fields__) == 7
    assert len(support.OPERATION_COUNTS_SPEC) == 9
    offenders: list[str] = []
    for path in support.app_module_paths():
        lowered = path.read_text(encoding="utf-8").lower()
        if SECOND_SOFTWARE_VENDOR.lower() in lowered:
            offenders.append(path.name)
    assert offenders == [], offenders
    assert support.MIDAS_PACKAGE_DIR.is_dir()  # 第一个软件（MIDAS）也只在自己子包里
