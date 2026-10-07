"""P127–P133 验收：第二个工程软件 Adapter（CSI ETABS）—— 分层 Contract Test + E2E + 加固。

权威来源
--------
- `docs/07` §12 P127–P133（本批任务卡）与 §12.2（P119–P126 的先例）。
- `docs/04` §71（Contract Test 分层 L1–L5；CI = L1–L3）· §151（生产加固 19 项）·
  §154（第二个软件接入原则：不改 9 Tool / Task Engine / RBAC / MCP Session / Pipeline）。
- `docs/02` §88 L7602–7612 / `docs/03` §106 L3173–3181 —— `ANALYSIS.STATIC` → `COM RunAnalysis`
  （本仓库内**唯一**可追溯的 ETABS 原生事实）。
- `docs/07` §11（**20** 码）· §14.2（厂商名只允许出现在 Adapter 子包）· §16 R63 / R78 / R81。

落地裁决（本环境的硬事实，不美化）
--------------------------------
1. **本仓库没有 ETABS 原生参数的权威来源**，故除 `ANALYSIS.STATIC` 外**一律**不写数据：
   这些 Operation 在能力阶段明确失败为 `STRUCTAI-3000`（`details.stage = "capability"`），
   **不**静默成功、**不**回落 —— 并把「除 `ANALYSIS.STATIC` 外条目数为 0」钉成断言。
2. **L4 / L5（真实实例）在本机不可执行**：没有 ETABS 安装、没有专用凭据
   （`docs/04` §72 的四要素不存在），故 E2E 在 **L3（Mock Transport）** 层执行，
   `verification_status` 保持 `PARTIAL`（`docs/07` §16 R78）。**不**声称已对真实 ETABS 跑通。
3. **原生派发必须注入**：本仓库**不**引入 COM 依赖（`docs/07` §3.1 技术栈冻结），
   故生产路径的 `connect()` 会明确失败为 `STRUCTAI-2000`
   （`reason = "dispatch_not_configured"`）—— 该限制在 `hardening.py` 与报告里如实登记。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema  # type: ignore[import-untyped]
import pytest

import etabs_p127_p133_support as support
import p42_p48_support as core
from app.domain.errors import InternalError, StructAIError
from app.infrastructure.adapters.base.adapter import ADAPTER_METHODS, AdapterState
from app.infrastructure.adapters.base.errors import AdapterNativeError, normalize_error
from app.infrastructure.adapters.base.manager import AdapterManager
from app.infrastructure.adapters.etabs import (
    CAPABILITY_STAGE,
    CATALOGUE,
    COM_PROTOCOL,
    DEFAULT_BUDGET_SECONDS,
    DELEGATED,
    ETABS_CATALOGUE_VERSION,
    HARDENING,
    IMPLEMENTED,
    NATIVE_STEPS,
    NOT_IMPLEMENTED,
    PARTIAL,
    RESULT_FIELDS,
    TRANSFORMER_REGISTRY,
    BuiltRequest,
    EtabsAdapter,
    EtabsCapabilityError,
    EtabsComClient,
    EtabsConnectionError,
    EtabsTimeoutError,
    EtabsTransformerError,
    EtabsValidationError,
    MappingNotVerified,
    OperationNotInCatalogue,
    UnsupportedRequest,
    capability_codes,
    capability_for_operation,
    catalogue_size,
    entry_for,
    etabs_manifest,
    guard_destructive,
    has,
    install,
    partial_operations,
    plan_for,
    status_of,
    transformer_for,
    unknown_codes,
    verify_traceable,
)
from app.infrastructure.adapters.etabs.hardening import COM_SESSION_CONCURRENCY_SAFE
from app.infrastructure.adapters.etabs.lifecycle import ComSessionState
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.interfaces.mcp import build_mcp_server

_NO_CONTEXT: Any = None
"""测试用的占位执行上下文（Adapter 侧只做转发）。"""

TWENTY_CODES: frozenset[str] = core.ERROR_CODES_SPEC
"""`docs/07` §11 的 **20** 码（测试侧副本，不从被测模块导入）。"""


def _validator_for(schema: dict[str, Any]) -> Any:
    """按 Schema 自身声明的方言选校验器（P09 裁决 R18 的同一口径）。"""
    declared = str(schema.get("$schema") or "")
    if "draft-07" in declared:
        return jsonschema.Draft7Validator
    return jsonschema.Draft202012Validator


CANONICAL_RESULT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "operation",
        "protocol",
        "method",
        "analysis_type",
        "completed",
        "verification_status",
        "adapter",
        "product",
    ],
    "properties": {
        "operation": {"const": "ANALYSIS.STATIC"},
        "protocol": {"const": "COM"},
        "method": {"const": "RunAnalysis"},
        "analysis_type": {"const": "STATIC"},
        "completed": {"type": "boolean"},
        "arguments": {"type": ["object", "null"]},
        "native_payload": {"type": ["object", "null"]},
        "native_keys": {"type": "array", "items": {"type": "string"}},
        "verification_status": {"enum": ["VERIFIED", "PARTIAL", "UNVERIFIED", "DEPRECATED"]},
        "adapter": {"const": "csi.etabs"},
        "product": {"const": "ETABS"},
    },
    "additionalProperties": False,
}
"""canonical 结果的 Schema（**我们自己**的规范形状；`docs/04` §71 的 L2 层）。

⚠️ 它**不是**任何厂商 Schema —— 本批**没有** ETABS 的 JSON Schema 来源，
故 L2 校验的对象只能是「我们声明给客户端的 canonical 形状」。
"""


# ===== P127：Adapter / Manifest / 注册（L1 静态层）=====


def test_p127_manifest_matches_the_traceable_facts() -> None:
    """门槛 ①（`docs/07` §12 P127）：Manifest 逐字段取自可追溯事实且通过既有校验。"""
    adapter = support.etabs_adapter(support.RecordingDispatch())
    manifest = adapter.manifest.validate()
    assert (manifest.name, manifest.vendor, manifest.product) == support.MANIFEST_SPEC
    assert manifest.supported_versions == support.SUPPORTED_VERSIONS_SPEC
    assert manifest.protocols == support.PROTOCOLS_SPEC
    assert manifest.capabilities == ()  # 静态清单留空（运行时由 catalogue 推导）
    assert adapter.adapter_key == ("CSI", "ETABS")
    assert manifest.supports_version("22") is True
    assert manifest.supports_version("21") is False  # 严格精确，**不**回落
    assert etabs_manifest().validate().name == "csi.etabs"
    assert ETABS_CATALOGUE_VERSION == "csi.etabs.v1"


def test_p127_adapter_implements_exactly_the_eight_documented_methods() -> None:
    """门槛 ①（`docs/02` §32）：八个方法齐备，且继承既有 `BaseAdapter`。"""
    adapter = support.etabs_adapter(support.RecordingDispatch())
    for name in ADAPTER_METHODS:
        assert callable(getattr(adapter, name)), name
    assert isinstance(adapter, EtabsAdapter)
    assert adapter.normalize_error(EtabsTimeoutError("x"))["code"] == "STRUCTAI-2300"
    assert adapter.normalize_error(TimeoutError("x"))["code"] == "STRUCTAI-6000"  # 兜底
    assert adapter.runtime_capabilities is None  # 未连接 → UNKNOWN（`docs/07` §16 R38）


def test_p127_registers_into_the_existing_adapter_manager_and_rejects_duplicates() -> None:
    """门槛 ①（`docs/07` §16 R81）：注册进既有 `AdapterManager`；重复注册 → 7000。"""
    manager = AdapterManager()
    manifest = install(manager, adapter=support.etabs_adapter(support.RecordingDispatch()))
    assert manager.registered_keys() == (("CSI", "ETABS"),)
    assert (manifest.vendor, manifest.product) == ("CSI", "ETABS")
    with pytest.raises(InternalError) as failure:
        install(manager)
    assert failure.value.code == "STRUCTAI-7000"
    assert failure.value.details["stage"] == "adapter_manager"
    assert failure.value.details["vendor"] == "CSI"


async def test_p127_bind_instance_creates_independent_adapters() -> None:
    """门槛 ①（`docs/02` §14 / §54）：每个软件实例一个**独立** Adapter 实例。"""
    manager = AdapterManager()
    dispatch = support.RecordingDispatch(payload={"completed": True})
    install(
        manager,
        adapter=support.etabs_adapter(dispatch),
        factory=lambda: support.etabs_adapter(dispatch),
    )
    first = manager.bind_instance(
        "etabs-a", vendor="CSI", product="ETABS", config=support.connect_config()
    )
    second = manager.bind_instance(
        "etabs-b", vendor="CSI", product="ETABS", config=support.connect_config()
    )
    assert first is not second
    assert manager.bound_instance_ids() == ("etabs-a", "etabs-b")
    health = await manager.connect("etabs-a")
    assert health["healthy"] is True and health["state"] == "READY"
    assert health["version"] == "22"
    assert manager.runtime_capabilities("etabs-a") == frozenset({"ANALYSIS.STATIC"})
    assert manager.runtime_capabilities("etabs-b") is None  # 未连接 → UNKNOWN
    await manager.disconnect_all()
    assert manager.adapter_for_instance("etabs-a").state is AdapterState.DISCONNECTED


def test_p127_second_software_needs_no_core_change() -> None:
    """`docs/04` §154：只增加 Adapter；Core 形状与 9 Tool 契约不变，厂商名不出子包。"""
    from app.container import BATCH_ID, AppContainer

    assert tuple(AppContainer.__dataclass_fields__) == core.CONTAINER_FIELDS_SPEC
    assert len(AppContainer.__dataclass_fields__) == 7
    assert BATCH_ID == "P42"  # `docs/07` §16 R82：本批**不**推进批次标记
    assert len(support.OPERATION_COUNTS_SPEC) == 9
    assert sum(count for _tool, count in support.OPERATION_COUNTS_SPEC) == 69

    offenders: list[str] = []
    for path in support.app_module_paths():
        lowered = path.read_text(encoding="utf-8").lower()
        for vendor in support.VENDOR_NAMES:
            if vendor.lower() in lowered:
                offenders.append(f"{path.name}:{vendor}")
    assert offenders == [], offenders

    # 豁免区**必须**确实存在且确实含厂商名（证明豁免不是空豁免）
    assert support.ETABS_PACKAGE_DIR.is_dir()
    inside = "\n".join(
        path.read_text(encoding="utf-8") for path in support.ETABS_PACKAGE_DIR.glob("*.py")
    )
    assert "ETABS" in inside and "CSI" in inside
    # P127–P133 交付 12 个文件；P135 新增 `dispatch.py` / `concurrency.py`（R88 / R93 裁决）
    # → 仍**只**在本子包内增长，Core 一行未改（`docs/07` §14.2 的厂商红线不变）。
    assert len(list(support.ETABS_PACKAGE_DIR.glob("*.py"))) == 14


# ===== P128：可追溯的 Registry / Schema / Capability 映射 =====


def test_p128_catalogue_has_exactly_one_traceable_entry() -> None:
    """门槛 ②（`docs/07` §12 P128）：除 `ANALYSIS.STATIC` 外条目数为 **0**（可执行断言）。"""
    assert catalogue_size() == 1
    assert tuple(CATALOGUE) == support.PARTIAL_OPERATIONS_SPEC
    assert catalogue_size() - (1 if has("ANALYSIS.STATIC") else 0) == 0
    assert has("MODEL.NODE.QUERY") is False
    assert has("DESIGN.STEEL") is False
    assert has("ANALYSIS.MODAL") is False
    assert partial_operations() == support.PARTIAL_OPERATIONS_SPEC


def test_p128_every_entry_carries_a_provenance_anchor() -> None:
    """门槛 ②：每条目都带 `docs/02` §88 / `docs/03` §106 的出处锚点（装配期自检通过）。"""
    assert verify_traceable() == ()
    entry = entry_for("ANALYSIS.STATIC")
    assert entry.provenance == support.PROVENANCE_ANCHORS_SPEC
    assert "docs/02 §88 L7602-7612" in entry.provenance
    assert "docs/03 §106 L3173-3181" in entry.provenance
    assert (entry.operation, entry.tool, entry.protocol, entry.method) == (
        support.TRACEABLE_FACT_SPEC
    )
    assert entry.verification_status == PARTIAL
    assert entry.note  # 非空：如实标注「其余 Operation 无权威数据源」


def test_p128_catalogue_entries_are_not_verified() -> None:
    """门槛 ②（`docs/07` §16 R78）：本批**不**升级任何 `verification_status`。"""
    assert {entry.verification_status for entry in CATALOGUE.values()} == {PARTIAL}
    assert entry_for("ANALYSIS.STATIC").verification_status != "VERIFIED"


def test_p128_capability_mapping_only_declares_the_traceable_code() -> None:
    """门槛 ②（`docs/07` §14.2）：能力码只来自落库的 41 条词表，且只声明确实支持的码。"""
    assert capability_codes() == ("ANALYSIS.STATIC",)
    assert unknown_codes() == ()
    assert capability_for_operation("ANALYSIS.STATIC") == "ANALYSIS.STATIC"
    assert capability_for_operation("MODEL.NODE.QUERY") is None
    from app.domain.enums import Capability

    vocabulary = {code.value for code in Capability}
    assert set(capability_codes()) <= vocabulary
    assert len(vocabulary) == 41


def test_p128_native_plans_are_derived_from_the_catalogue() -> None:
    """门槛 ②：编排由 catalogue **机械推导**（1 条 → 1 步），未覆盖的 Operation 明确失败。"""
    assert len(NATIVE_STEPS) == catalogue_size() == 1
    step = plan_for("ANALYSIS.STATIC")
    assert (step.protocol, step.method, step.intent) == (COM_PROTOCOL, "RunAnalysis", "analyze")
    assert step.arguments == ()  # 无可追溯的原生参数（**不**臆造）
    with pytest.raises(OperationNotInCatalogue) as failure:
        plan_for("MODEL.NODE.QUERY")
    assert failure.value.code == "STRUCTAI-3000"
    assert failure.value.details["stage"] == CAPABILITY_STAGE
    assert failure.value.details["reason"] == "operation_not_in_catalogue"


# ===== P129：Transformer（L2 Schema 层）=====


def test_p129_canonical_to_native_is_the_identity_on_the_declared_vocabulary() -> None:
    """门槛 ③：canonical ↔ native 双向；缺省值来自 catalogue（**不**臆造）。"""
    transformer = transformer_for("ANALYSIS.STATIC")
    assert transformer.name in TRANSFORMER_REGISTRY
    assert transformer.request_to_native({"analysis_type": "STATIC"}) == {}
    assert transformer.request_to_native({}) == {}
    assert transformer.request_from_native({}) == {"analysis_type": "STATIC"}
    canonical = transformer.request_from_native(
        transformer.request_to_native({"analysis_type": "static"})
    )
    assert canonical == {"analysis_type": "STATIC"}  # 规范形态的往返


def test_p129_undeclared_transformations_fail_loudly() -> None:
    """门槛 ③：未覆盖的转换必须**明确失败**（**不**静默丢弃、**不**猜字段名）。"""
    transformer = transformer_for("ANALYSIS.STATIC")
    with pytest.raises(EtabsTransformerError) as extra:
        transformer.request_to_native({"analysis_type": "STATIC", "load_case": "AXIAL"})
    assert extra.value.code == "STRUCTAI-1200"
    assert extra.value.details["reason"] == "transformer_field_not_declared"
    with pytest.raises(EtabsValidationError) as wrong:
        transformer.request_to_native({"analysis_type": "MODAL"})
    assert wrong.value.details["reason"] == "analysis_type_not_in_catalogue"
    with pytest.raises(EtabsTransformerError):
        transformer.request_from_native({"TYPE": "STATIC"})  # 原生参数面本批为空
    with pytest.raises(EtabsTransformerError):
        transformer.result_to_native({"operation": "ANALYSIS.STATIC", "load_case": "X"})


async def test_p131_l2_canonical_result_validates_against_the_declared_schema() -> None:
    """门槛 ⑤（`docs/04` §71 的 **L2**）：产物必须能过我们声明的 canonical Schema。"""
    dispatch = support.RecordingDispatch(payload={"return_value": [], "message": []})
    adapter = support.etabs_adapter(dispatch)
    await adapter.connect(support.connect_config())
    result = await adapter.execute_normalized("ANALYSIS.STATIC", {}, _NO_CONTEXT)
    validator = _validator_for(CANONICAL_RESULT_SCHEMA)
    errors = list(validator(CANONICAL_RESULT_SCHEMA).iter_errors(result))
    assert errors == [], errors[:2]
    assert result["native_keys"] == ["message", "return_value"]
    assert result["completed"] is True
    assert result["verification_status"] == PARTIAL
    await adapter.disconnect()


async def test_p129_missing_values_are_none_and_never_fabricated() -> None:
    """门槛 ③（`docs/04` §44）：缺失值写 `None`，**绝不**虚构 `0` / 空对象。"""
    dispatch = support.RecordingDispatch(payload={})
    adapter = support.etabs_adapter(dispatch)
    await adapter.connect(support.connect_config())
    result = await adapter.execute_normalized("ANALYSIS.STATIC", {}, _NO_CONTEXT)
    assert result["arguments"] is None
    assert result["native_payload"] is None
    assert result["native_keys"] == []
    assert result["native_payload"] != 0
    transformer = transformer_for("ANALYSIS.STATIC")
    core_result = {key: value for key, value in result.items() if key in RESULT_FIELDS}
    assert transformer.result_to_native(core_result)["payload"] == {}
    await adapter.disconnect()


# ===== P131：L3 Mock Transport（逐条断言请求 == Registry 数据）=====


async def test_p131_l3_requests_match_the_catalogue_entry_by_entry() -> None:
    """门槛 ⑤（`docs/04` §71 的 **L3**）：逐条断言发出的原生请求与 catalogue 数据一致。"""
    dispatch = support.RecordingDispatch(payload={"status": "OK"})
    adapter = support.etabs_adapter(dispatch)
    await adapter.connect(support.connect_config())
    entry = entry_for("ANALYSIS.STATIC")
    step = plan_for(entry.operation)

    result = await adapter.execute_normalized("ANALYSIS.STATIC", {}, _NO_CONTEXT)
    assert dispatch.calls == [(entry.method, {})]
    method, arguments = dispatch.calls[0]
    assert method == entry.method == step.method == "RunAnalysis"
    assert arguments == {}  # 无可追溯的原生参数
    assert entry.protocol == COM_PROTOCOL == step.protocol
    assert result["method"] == entry.method
    assert result["protocol"] == entry.protocol
    assert result["analysis_type"] == entry.operation.rsplit(".", 1)[-1]
    assert result["native_payload"] == {"status": "OK"}
    assert result["verification_status"] == entry.verification_status
    await adapter.disconnect()
    assert dispatch.detach_count == 1


async def test_p131_l3_health_check_uses_the_lifecycle_probe_only() -> None:
    """门槛 ⑤（`docs/02` §25）：健康检查是**生命周期**探测，不产生任何原生方法调用。"""
    dispatch = support.RecordingDispatch(payload={"status": "OK"})
    adapter = support.etabs_adapter(dispatch)
    await adapter.connect(support.connect_config())
    health = await adapter.health_check()
    assert tuple(health) == ("healthy", "state", "version", "latency_ms")
    assert health["healthy"] is True and health["state"] == "READY"
    assert health["version"] == "22"
    assert dispatch.calls == []  # 零原生方法调用
    await adapter.disconnect()


# ===== P130：破坏性护栏 / 门控 / 错误归一化 =====


async def test_p130_destructive_operations_are_rejected_with_zero_transport_calls() -> None:
    """门槛 ④（`docs/07` §12 P130）：破坏性操作在**发请求之前**拒绝（零 transport 调用）。"""
    dispatch = support.RecordingDispatch(payload={"status": "OK"})
    adapter = support.etabs_adapter(dispatch)
    await adapter.connect(support.connect_config())
    dispatch.calls.clear()
    with pytest.raises(StructAIError) as failure:
        await adapter.execute_normalized("MODEL.NODE.DELETE", {"item_ids": [1]}, _NO_CONTEXT)
    assert failure.value.code == "STRUCTAI-3000"
    assert failure.value.details["stage"] == CAPABILITY_STAGE
    assert dispatch.calls == []

    with pytest.raises(UnsupportedRequest) as guard:
        guard_destructive("MODEL.NODE.DELETE")
    assert guard.value.code == "STRUCTAI-1200"
    assert guard.value.details["reason"] == "destructive_operation_rejected"
    guard_destructive("ANALYSIS.STATIC")  # 非破坏性 → 放行
    await adapter.disconnect()


async def test_p130_every_other_operation_is_structai_3000_with_zero_transport_calls() -> None:
    """门槛 ④：其余 Operation 一律 `STRUCTAI-3000`（**不**静默成功、**不**回落）。"""
    dispatch = support.RecordingDispatch(payload={"status": "OK"})
    adapter = support.etabs_adapter(dispatch)
    await adapter.connect(support.connect_config())
    for operation in (
        "MODEL.NODE.QUERY",
        "BUILD.COLUMN",
        "ANALYSIS.MODAL",
        "ANALYSIS.SEISMIC",
        "RESULT.NODE.DISPLACEMENT",
        "DESIGN.STEEL",
        "INFO",
    ):
        with pytest.raises(StructAIError) as failure:
            await adapter.execute_normalized(operation, {}, _NO_CONTEXT)
        assert failure.value.code == "STRUCTAI-3000", operation
        assert failure.value.details["stage"] == CAPABILITY_STAGE, operation
        assert failure.value.details["reason"] == "operation_not_in_catalogue", operation
    assert dispatch.calls == []
    await adapter.disconnect()


async def test_p130_production_mode_refuses_partial_entries() -> None:
    """门槛 ④（`docs/07` §16 R78）：生产路径（`allow_partial=False`）拒绝 `PARTIAL` 条目。"""
    dispatch = support.RecordingDispatch(payload={"status": "OK"})
    adapter = support.etabs_adapter(dispatch, allow_partial=False)
    await adapter.connect(support.connect_config())
    with pytest.raises(StructAIError) as failure:
        await adapter.execute_normalized("ANALYSIS.STATIC", {}, _NO_CONTEXT)
    assert failure.value.code == "STRUCTAI-3000"
    assert failure.value.details["stage"] == CAPABILITY_STAGE
    assert failure.value.details["verification_status"] == PARTIAL
    assert dispatch.calls == []
    await adapter.disconnect()


def test_p130_errors_are_normalized_by_the_single_base_mapping() -> None:
    """门槛 ④（`docs/07` §11）：归一化**只**复用 `base/errors.py`，且**不**新增码。"""
    adapter = support.etabs_adapter(support.RecordingDispatch())
    samples: tuple[tuple[Exception, str], ...] = (
        (EtabsValidationError("x"), "STRUCTAI-1200"),
        (EtabsConnectionError("x"), "STRUCTAI-2000"),
        (EtabsTimeoutError("x"), "STRUCTAI-2300"),
        (EtabsCapabilityError("x"), "STRUCTAI-3000"),
        (OperationNotInCatalogue("MODEL.NODE.QUERY"), "STRUCTAI-3000"),
        (MappingNotVerified("ANALYSIS.STATIC", PARTIAL), "STRUCTAI-3000"),
        (UnsupportedRequest("destructive_operation_rejected"), "STRUCTAI-1200"),
    )
    for error, code in samples:
        assert isinstance(error, AdapterNativeError)
        assert normalize_error(error)["code"] == code
        assert adapter.normalize_error(error)["code"] == code
        assert normalize_error(error)["code"] in TWENTY_CODES
    assert normalize_error(RuntimeError("boom"))["code"] == "STRUCTAI-6000"  # 兜底（6000）
    envelope = normalize_error(OperationNotInCatalogue("MODEL.NODE.QUERY"))
    assert envelope["details"]["stage"] == CAPABILITY_STAGE
    assert envelope["details"]["reason"] == "operation_not_in_catalogue"
    assert core.structai_code_literals() == set(TWENTY_CODES)  # **恰好 20** 个码字面量


def test_p130_request_guards_are_pure_functions_evaluated_before_the_transport() -> None:
    """门槛 ④（`docs/07` §12 P130）：四道护栏都是纯函数、**发请求前**求值。"""
    entry = entry_for("ANALYSIS.STATIC")
    dispatch = support.RecordingDispatch(payload={"status": "OK"})
    client = EtabsComClient(dispatch, budget_seconds=DEFAULT_BUDGET_SECONDS)
    request = client.build_request(
        entry, operation="ANALYSIS.STATIC", arguments={}, allow_partial=True
    )
    assert isinstance(request, BuiltRequest)
    assert (request.protocol, request.method) == (entry.protocol, entry.method)
    assert request.verification_status == PARTIAL
    assert request.budget_seconds == DEFAULT_BUDGET_SECONDS
    assert repr(request).find("arguments") == -1  # repr 不含参数
    with pytest.raises(MappingNotVerified):
        client.build_request(entry, operation="ANALYSIS.STATIC", arguments={})
    with pytest.raises(UnsupportedRequest):
        client.build_request(entry, operation="MODEL.NODE.DELETE", arguments={})
    assert dispatch.calls == []


# ===== P133：生产加固（`docs/04` §151）=====


async def test_p133_first_timeout_is_retried_then_the_circuit_breaker_opens() -> None:
    """门槛（`docs/04` §151 的 Timeout / Retry / Circuit breaker）：可执行用例。"""
    dispatch = support.RecordingDispatch(
        payload={"status": "OK"}, failures=("timeout", "timeout", "timeout")
    )
    adapter = support.etabs_adapter(dispatch)
    await adapter.connect(support.connect_config())
    dispatch.calls.clear()
    with pytest.raises(StructAIError) as failure:
        await adapter.execute_normalized("ANALYSIS.STATIC", {}, _NO_CONTEXT)
    assert failure.value.code == "STRUCTAI-2300"
    assert failure.value.details["reason"] == "request_timed_out"
    assert len(dispatch.calls) == 2  # 首次超时 + 一次重试

    calls_before = len(dispatch.calls)
    with pytest.raises(StructAIError) as open_circuit:
        await adapter.execute_normalized("ANALYSIS.STATIC", {}, _NO_CONTEXT)
    assert open_circuit.value.code == "STRUCTAI-2000"
    assert open_circuit.value.details["reason"] == "circuit_open"
    assert len(dispatch.calls) == calls_before  # 熔断打开后**零** transport 调用

    assert adapter.client is not None
    breaker = adapter.client.breaker
    assert breaker.state == "OPEN"
    assert breaker.failures >= 2
    breaker.reset()
    result = await adapter.execute_normalized("ANALYSIS.STATIC", {}, _NO_CONTEXT)
    assert result["completed"] is True
    assert breaker.state == "CLOSED"
    await adapter.disconnect()


async def test_p133_credentials_are_re_resolved_on_every_attach_and_never_echoed() -> None:
    """门槛（`docs/04` §151 的 Credential rotation / Secret redaction）。"""
    provider = support.FakeCredentialProvider({"etabs-credential": support.SECRET})
    dispatch = support.RecordingDispatch(payload={"status": "OK"})
    adapter = support.etabs_adapter(
        dispatch, credential_provider=provider, credential_reference="etabs-credential"
    )
    await adapter.connect(support.connect_config())
    assert dispatch.secrets == [support.SECRET]
    await adapter.disconnect()
    provider.values["etabs-credential"] = "rotated-credential"
    await adapter.connect(support.connect_config())
    assert dispatch.secrets == [support.SECRET, "rotated-credential"]
    assert provider.references == ["etabs-credential", "etabs-credential"]
    assert support.SECRET not in repr(adapter.session)
    assert "rotated-credential" not in repr(adapter.session)
    with pytest.raises(StructAIError) as failure:
        await adapter.execute_normalized("MODEL.NODE.QUERY", {}, _NO_CONTEXT)
    assert support.SECRET not in json.dumps(normalize_error(failure.value))
    assert support.SECRET not in json.dumps(failure.value.to_dict())
    await adapter.disconnect()


async def test_p133_health_reflects_the_real_session_state() -> None:
    """门槛（`docs/04` §151 的 Reconcile）：健康检查如实反映真实会话态。"""
    dispatch = support.RecordingDispatch(payload={"status": "OK"})
    adapter = support.etabs_adapter(dispatch)
    await adapter.connect(support.connect_config())
    assert (await adapter.health_check())["healthy"] is True
    dispatch.attached = False  # 模拟会话掉线（对账只读真实状态）
    dropped = await adapter.health_check()
    assert dropped["healthy"] is False and dropped["state"] == "ERROR"
    assert dropped["version"] == "22"
    assert adapter.last_health == dropped
    await adapter.disconnect()
    assert adapter.session.state is ComSessionState.DETACHED
    assert (await adapter.health_check())["healthy"] is False


async def test_p127_session_lifecycle_is_idempotent_and_loud_without_a_dispatch() -> None:
    """门槛 ①（`docs/02` §10 / §54）：attach / detach 幂等；无 dispatch 明确失败。"""
    dispatch = support.RecordingDispatch(payload={"status": "OK"})
    adapter = support.etabs_adapter(dispatch)
    await adapter.connect(support.connect_config())
    await adapter.connect(support.connect_config())
    assert dispatch.attach_count == 1  # 幂等
    assert adapter.state is AdapterState.READY
    await adapter.disconnect()
    await adapter.disconnect()
    assert dispatch.detach_count == 1  # 幂等

    without = EtabsAdapter()
    with pytest.raises(EtabsConnectionError) as failure:
        await without.connect(support.connect_config())
    assert failure.value.code == "STRUCTAI-2000"
    assert failure.value.details["reason"] == "dispatch_not_configured"
    assert without.state is AdapterState.ERROR


async def test_p127_version_must_be_declared_exactly() -> None:
    """门槛 ①（`docs/02` §20）：版本**严格精确**；未声明版本 → `STRUCTAI-1200`。"""
    adapter = support.etabs_adapter(support.RecordingDispatch())
    with pytest.raises(EtabsValidationError) as failure:
        await adapter.connect(support.connect_config(version="21"))
    assert failure.value.code == "STRUCTAI-1200"
    assert failure.value.details["reason"] == "version_not_supported"
    assert failure.value.details["declared"] == list(support.SUPPORTED_VERSIONS_SPEC)


async def test_p127_cancel_is_explicitly_unsupported() -> None:
    """门槛 ①（`docs/07` §14.4）：**不**伪造取消 —— 明确 `STRUCTAI-3000`。"""
    adapter = support.etabs_adapter(support.RecordingDispatch())
    await adapter.connect(support.connect_config())
    with pytest.raises(EtabsCapabilityError) as failure:
        await adapter.cancel("task-1")
    assert failure.value.code == "STRUCTAI-3000"
    assert failure.value.details["reason"] == "cancel_not_supported"
    await adapter.disconnect()


def test_p133_hardening_table_covers_docs_04_section_151_item_by_item() -> None:
    """门槛 ⑥（`docs/04` §151）：**19** 项逐条给出判定或如实标注未落地。"""
    assert tuple(item.item for item in HARDENING) == support.HARDENING_ITEMS_SPEC
    statuses = {IMPLEMENTED, DELEGATED, NOT_IMPLEMENTED}
    for item in HARDENING:
        assert item.status in statuses, item.item
        assert item.decision.strip(), item.item
        assert item.reason.strip(), item.item
    for implemented_item in (
        "Timeout",
        "Retry",
        "Circuit breaker",
        "Credential rotation",
        "Secret redaction",
        "Reconcile",
        "Contract test",
        "E2E",
        "Version migration",
    ):
        assert status_of(implemented_item) == IMPLEMENTED, implemented_item
    for delegated_item in (
        "Rate limit",
        "Concurrency",
        "Resource lock",
        "Metrics",
        "Trace",
        "Audit",
    ):
        assert status_of(delegated_item) == DELEGATED, delegated_item
    assert status_of("Structured logging") == NOT_IMPLEMENTED
    assert COM_SESSION_CONCURRENCY_SAFE is False
    with pytest.raises(EtabsValidationError):
        status_of("Not a documented item")


def test_p133_subpackage_holds_no_logging_observability_or_persistence() -> None:
    """门槛 ⑥：Adapter 侧**零**日志 / 零观测 / 零持久化（`docs/07` §14.1 / §14.3）。"""
    modules = sorted(support.ETABS_PACKAGE_DIR.glob("*.py"))
    assert len(modules) == 14
    imported: set[str] = set()
    for path in modules:
        imported.update(core.imported_modules(path))
    for forbidden in ("logging", "sqlalchemy", "httpx", "fastapi", "mcp"):
        assert forbidden not in imported, forbidden
    assert not any(name.startswith("app.observability") for name in imported)
    assert not any(name.startswith("app.application") for name in imported)
    assert not any(name.startswith("app.interfaces") for name in imported)
    # 也不允许出现 `commit` / `rollback`（事务边界只归 UnitOfWork）
    for path in modules:
        assert core.commit_or_rollback_calls(path) == [], path.name


def test_p133_contract_layers_l1_to_l3_are_implemented_and_l4_l5_are_not_claimed() -> None:
    """门槛 ⑥（`docs/04` §71 / §72）：CI 三层落地；L4 / L5 **不**声称。"""
    assert support.CONTRACT_LEVELS_CI == ("L1", "L2", "L3")
    assert support.CONTRACT_LEVELS_DEDICATED == ("L4", "L5")
    contract_item = next(item for item in HARDENING if item.item == "Contract test")
    assert "L4" in contract_item.reason and "L5" in contract_item.reason
    # L2 校验的对象只能是「我们声明的 canonical 形状」：仓库里**没有** ETABS 的 Schema 数据
    assert not list((support.REPO_ROOT / "registry").glob("*etabs*"))
    assert not (support.ETABS_PACKAGE_DIR / "schemas").exists()
    assert entry_for("ANALYSIS.STATIC").verification_status == PARTIAL


# ===== P132：E2E（同一 9 Tool 契约 + 同一 Execution Pipeline；L3 层）=====


async def _connected_etabs_runtime(
    tmp_path: Path,
    monkeypatch: Any,
    *,
    name: str = "p127_e2e.db",
) -> tuple[Any, Any, dict[str, str], support.RecordingDispatch]:
    """装配运行时 + 注册 / 绑定 / 连接 ETABS 实例（返回 4 元组）。"""
    runtime, factory, ids, dispatch = await support.seeded_etabs_runtime(
        tmp_path, monkeypatch, name=name
    )
    runtime.adapters.bind_instance(
        ids["instance_id"],
        vendor=support.MANIFEST_SPEC[1],
        product=support.MANIFEST_SPEC[2],
        config=support.connect_config(),
    )
    health = await runtime.adapters.connect(ids["instance_id"])
    assert health["healthy"] is True, health
    assert runtime.adapters.runtime_capabilities(ids["instance_id"]) == frozenset(
        {"ANALYSIS.STATIC"}
    )
    return runtime, factory, ids, dispatch


async def test_p132_engineering_analysis_runs_end_to_end(tmp_path: Path, monkeypatch: Any) -> None:
    """门槛 ⑥（`docs/04` §154；`docs/07` §13.2）：MCP Tool → 管线 → Adapter 全链跑通。"""
    runtime, factory, ids, dispatch = await _connected_etabs_runtime(tmp_path, monkeypatch)
    identity = core.identity_context(ids)
    context = core.client_context(ids)
    async with UnitOfWork.from_session_factory(factory) as uow:
        bundle = runtime.execution.create(uow.session)
        server = build_mcp_server(bundle.service)
        assert len(server.list_tools()) == 9  # 9 Tool 契约不变
        resolved = await bundle.resolver.resolve(
            server.contexts.create(identity, client_context=context).execution
        )
        assert resolved is not None
        token = runtime.confirmation.issue(
            user_id=ids["user_id"],
            tenant_id=ids["tenant_id"],
            operation="ANALYSIS.STATIC",
            resource_id=resolved.resource_id,
        ).token
        built = await server.handle(
            "engineering_analysis",
            core.arguments("ANALYSIS.STATIC", context=context, confirmation_token=token),
            identity=identity,
        )
        assert built.success is True, built.errors
        assert built.execution["mode"] == "ASYNC"
        assert "Effective Permission" in built.execution["steps"], "RBAC 闸门"
        assert "Capability Check" in built.execution["steps"], "Capability 闸门"
        assert "Task / Transaction" in built.execution["steps"]
        assert "Adapter" not in built.execution["steps"], "Adapter 在 Worker 里跑"

        task_id = built.execution["task_id"]
        assert isinstance(task_id, str)
        record = await bundle.engine.run_task(task_id)
        assert str(record.status) == "COMPLETED", record.status
        assert record.started_at is not None
        assert await bundle.pipeline.locks.held_count() == 0, "完成后释放资源锁"

        result = json.loads(record.result_json or "{}")
        entry = entry_for("ANALYSIS.STATIC")
        assert result["operation"] == entry.operation
        assert result["protocol"] == entry.protocol
        assert result["method"] == entry.method
        assert result["adapter"] == "csi.etabs"
        assert result["product"] == "ETABS"
        assert result["verification_status"] == entry.verification_status
        assert bundle.audit.records_written() >= 1, "Audit"

    # 逐条断言：发出的原生请求 == Registry（catalogue）数据
    assert dispatch.calls == [(entry.method, {})]
    assert dispatch.methods() == [entry.method]
    assert dispatch.attach_count == 1
    assert await runtime.outbox.count() >= 1, "Event"
    await runtime.adapters.disconnect_all()
    assert dispatch.detach_count == 1


async def test_p132_other_operations_are_refused_with_structai_3000(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """门槛 ⑥：同一管线上的其余 Operation 在新软件上**明确** `STRUCTAI-3000`。"""
    runtime, factory, ids, dispatch = await _connected_etabs_runtime(
        tmp_path, monkeypatch, name="p127_e2e_refuse.db"
    )
    identity = core.identity_context(ids)
    context = core.client_context(ids)
    async with UnitOfWork.from_session_factory(factory) as uow:
        bundle = runtime.execution.create(uow.session)
        server = build_mcp_server(bundle.service)
        resolved = await bundle.resolver.resolve(
            server.contexts.create(identity, client_context=context).execution
        )
        assert resolved is not None
        for tool, operation in (
            ("engineering_model_query", "MODEL.NODE.QUERY"),
            ("engineering_doc", "INFO"),
            ("engineering_analysis", "ANALYSIS.MODAL"),
            ("engineering_result", "RESULT.NODE.DISPLACEMENT"),
        ):
            token = runtime.confirmation.issue(
                user_id=ids["user_id"],
                tenant_id=ids["tenant_id"],
                operation=operation,
                resource_id=resolved.resource_id,
            ).token
            response = (
                await server.handle(
                    tool,
                    core.arguments(operation, context=context, confirmation_token=token),
                    identity=identity,
                )
            ).to_dict()
            assert response["success"] is False, operation
            assert response["errors"][0]["code"] == "STRUCTAI-3000", operation
            assert response["errors"][0]["details"]["stage"] == CAPABILITY_STAGE, operation
            assert response["errors"][0]["details"]["statuses"] == ["UNSUPPORTED"], operation
    assert dispatch.calls == [], "能力拒绝不得触碰 transport"
    assert dispatch.attach_count == 1
    await runtime.adapters.disconnect_all()
