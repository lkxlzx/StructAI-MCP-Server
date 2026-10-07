"""P134 验收：真实 L4 / L5 闭环 + R83 响应信封。

权威来源（`docs/04` §69–§72 / §18；`docs/07` §16 R78 / R83 / R84）
------------------------------------------------------------------
- `docs/04` §69 / §71 / §72 —— Contract Test 目的、五层分层（CI = L1–L3，专用环境 = L4–L5）
  与 Live 安全四要素（专用实例 / 专用 Key / 专用项目 / 专用测试模型）。
- `docs/04` §8 —— `VERIFIED` 的 **7 项 AND**；§18 —— API Contract Snapshot。
- `docs/07` §16 **R83**（`CIVIL_DESIGNER` 实测信封在 `result.return_value`）·
  **R84**（三实例只读 L4 实测）· **R78**（7 项 AND 的落地程度）· **R14**（`read_root` 未实测）。

落地裁决（本文件的硬事实，不美化）
--------------------------------
1. **L4/L5 用例可跳过**：真实实例只在显式 opt-in（`MIDAS_LIVE_L4=1` + Base URL / MAPI-Key
   齐备）时执行；缺环境一律 `pytest.skip`，**不失败、不伪造**（§71 把 L4–L5 归专用环境）。
2. **L5 另需专用测试项目声明**（§72 第 3 要素）：缺声明即**不执行** —— 实测两实例均已打开
   **非空模型**（GEN NX 的 `GET /DB/NODE` 返回 12 个节点），写入即触碰真实项目。
3. **离线路径用 Mock Transport 覆盖同一实现**：信封分类、记录落库与可回查、7 项 AND、
   L5 三步链的请求形态，全部在**无网络**下断言（CI 可跑）。
4. **R83 的两种信封都被钉住**：NX 系 = `{read_root: {...}}`；Designer =
   `{command, function, result: {return_value, message}}`。取不到即**明确报错**，
   **不得**静默降级（旧实现退回整包 → 转换器字段全 `None`）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select

import midas_p119_p126_support as support
from app.infrastructure.adapters.midas.adapter import _unwrap
from app.infrastructure.adapters.midas.client import (
    MidasEnvironmentCredential,
    MidasHttpClient,
)
from app.infrastructure.adapters.midas.import_registry import (
    VERSION_RANGE,
    MidasRegistryImporter,
)
from app.infrastructure.adapters.midas.live import (
    CONTRACT_LEVEL_L4,
    LIVE_PROJECT_ENV,
    MIDAS_LIVE_ENV,
    PROBE_FAILED,
    PROBE_PARTIAL,
    PROBE_PASSED,
    SEVEN_AND_ITEMS,
    STATUS_PARTIAL,
    STATUS_VERIFIED,
    DedicatedTestProject,
    MidasLiveBusinessEffect,
    MidasLiveProber,
    dedicated_test_project_from_env,
    live_opt_in_from_env,
    read_verifications,
    record_verifications,
    registry_evidence,
    seven_and_verdict,
)
from app.infrastructure.adapters.midas.models import MidasApiVerificationORM
from app.infrastructure.adapters.midas.registry import (
    EndpointDefinition,
    MidasRegistry,
    ResolvedEndpoint,
)

_NO_CONTEXT: Any = None
"""占位执行上下文（Adapter 侧只做转发）。"""

DESIGNER_READ_KEYS: tuple[str, ...] = (
    "DB.BTCP",
    "DB.CAPSIZE",
    "DB.CWRC",
    "DB.DCOD",
    "DB.ELEM",
    "DB.KFAC",
    "DB.LCOM",
    "DB.LENG",
    "DB.MEMB",
    "DB.MODULE",
    "DB.NODE",
    "DB.SPAN",
    "DB.TRPT",
    "DOC.UNIT",
)
"""`CIVIL_DESIGNER` 上**只读可用**的 14 个端点（P134 实测覆盖全量）。"""

READ_ROOT_FIXES: tuple[tuple[str, str], ...] = (
    ("OPE.PROJECTSTATUS", "PROJECTSTATUS"),
    ("OPE.SECTPROP", "SECTPROP"),
    ("OPE.STORY_IRR_PARAM", "STORY_IRR_PARAM"),
    ("OPE.STORY_PARAM", "STORY_PARAM"),
    ("VIEW.SELECT", "SELECT"),
)
"""P134 实测发现并修复的 5 处 `read_root` 缺失（R14 收口）。"""

LIVE_KEYS: tuple[str, ...] = (
    "OPE.PROJECTSTATUS",
    "DB.NODE",
    "DB.MATL",
    "DB.SECT",
    "DB.UNIT",
    "DB.GRUP",
)
"""L4 实测抽样端点（GEN NX 本机；覆盖 R84 列出的五个 + `DB.GRUP`）。"""

LIVE_BASE_ENV = "MIDAS_BASE_URL"
LIVE_KEY_ENV = "MIDAS_MAPI_KEY"


# ===== 假传输（离线路径）=====


class EnvelopeTransport(httpx.MockTransport):
    """按 `(method, path)` 查表的假传输（记录全部请求；未命中 → `404`）。"""

    def __init__(self, routes: dict[tuple[str, str], Any], prefix: str = "/civil") -> None:
        """绑定路由表（**不**发真实请求）。"""
        self.calls: list[tuple[str, str, Any]] = []
        self._routes = dict(routes)
        self._prefix = prefix
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        """记录 → 查表 → 应答（未命中 `404`，与真实软件同形）。"""
        path = request.url.path
        if self._prefix and path.startswith(self._prefix):
            path = path[len(self._prefix) :]
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, path, body))
        payload = self._routes.get((request.method, path))
        if payload is None:
            return httpx.Response(404, json={"message": "not found"})
        return httpx.Response(200, json=payload)


def _designer_envelope(return_value: Any, command: str = "GetNode") -> dict[str, Any]:
    """`CIVIL_DESIGNER` 的实测信封（R83；结构照实测，值已脱敏）。"""
    return {
        "command": command,
        "function": "get",
        "result": {"return_value": return_value, "message": [{"code": 0, "message": "OK"}]},
    }


def _designer_transport() -> EnvelopeTransport:
    """Designer 侧假传输（读 / 写 / 删各一条；信封照 R83）。"""
    return EnvelopeTransport(
        {
            ("GET", "/DB/NODE"): _designer_envelope([{"ID": 1, "X": 0.0, "Y": 0.0, "Z": 0.0}]),
            ("POST", "/DB/NODE"): _designer_envelope([{"ID": 7}], command="SetNode"),
            ("DELETE", "/DB/NODE/7"): _designer_envelope(None, command="DeleteNode"),
        }
    )


class NxNodeTransport(EnvelopeTransport):
    """有状态的 NX 节点表假传输（创建后读回可见、删除后消失）。"""

    def __init__(self) -> None:
        """空路由表 + 一条既有节点（编号 `1`）。"""
        self.nodes: dict[str, Any] = {"1": {"X": 0.0, "Y": 0.0, "Z": 0.0}}
        super().__init__({})

    def _handle(self, request: httpx.Request) -> httpx.Response:
        """维护节点表（`Assign` 包装 + 编号键映射，`registry/README.md` §4）。"""
        path = request.url.path
        if path.startswith("/civil"):
            path = path[len("/civil") :]
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, path, body))
        if path == "/DB/NODE" and request.method == "GET":
            return httpx.Response(200, json={"NODE": dict(self.nodes)})
        if path == "/DB/NODE" and request.method == "POST":
            assign = dict((body or {}).get("Assign") or {})
            self.nodes.update({str(key): value for key, value in assign.items()})
            return httpx.Response(200, json={"Assign": assign})
        if request.method == "DELETE" and path.startswith("/DB/NODE/"):
            for key in path.rsplit("/", 1)[-1].split(","):
                self.nodes.pop(key, None)
            return httpx.Response(200, json={"message": ""})
        return httpx.Response(404, json={"message": "not found"})


def _client(transport: httpx.AsyncBaseTransport | None = None) -> MidasHttpClient:
    """**离线**客户端（固定假 Base URL / 假 Key；**不**读运行环境）。"""
    return MidasHttpClient(
        base_url=support.BASE_URL,
        credential_provider=MidasEnvironmentCredential({"MIDAS_MAPI_KEY": support.SECRET}),
        secret_ref="MIDAS_MAPI_KEY",
        transport=transport,
    )


def _live_client() -> MidasHttpClient:
    """**真实实例**客户端（Base URL / Key **只**来自环境变量，见 `docs/07` §14.3）。"""
    return MidasHttpClient(
        base_url=os.environ[LIVE_BASE_ENV],
        credential_provider=MidasEnvironmentCredential(),
        secret_ref=LIVE_KEY_ENV,
    )


def _live_enabled() -> bool:
    """L4/L5 是否具备执行条件（显式 opt-in + 环境变量齐备）。"""
    if not live_opt_in_from_env(os.environ):
        return False
    return bool((os.environ.get(LIVE_BASE_ENV) or "").strip()) and bool(
        (os.environ.get(LIVE_KEY_ENV) or "").strip()
    )


# ===== P134b：R83 两种信封 =====


def test_p134_designer_read_path_is_declared_for_every_read_endpoint() -> None:
    """数据侧为 Designer 的**全部**只读端点声明了 `result.return_value` 解包链（R83）。"""
    registry = support.registry()
    for key in DESIGNER_READ_KEYS:
        definition = registry.endpoint(key)
        resolved = registry.resolve(key=key, product="CIVIL_DESIGNER", method="GET")
        assert resolved.read_path == ("result", "return_value"), key
        declared = bool(definition.read_root_path) or "wrapper" in (
            definition.overrides.get("CIVIL_DESIGNER") or {}
        )
        assert declared, key
    nx = registry.resolve(key="DB.NODE", product="GEN_NX", method="GET")
    assert nx.read_path == (nx.read_root,) == ("NODE",)


def test_p134_read_root_missing_entries_are_fixed_per_measurement() -> None:
    """R14 收口：实测发现 5 处 `read_root` 缺失，已按实测值补齐（**不**猜）。"""
    registry = support.registry()
    for key, expected in READ_ROOT_FIXES:
        definition = registry.endpoint(key)
        assert definition.read_root == expected, key
        assert definition.read_root_path == ()
        assert definition.uri.rsplit("/", 1)[-1] == expected


async def test_p134_nx_envelope_is_unwrapped_by_read_root() -> None:
    """NX 系信封：`{<read_root>: {...}}` → 逐条进 canonical（编号取自键）。"""
    transport = support.RecordingTransport()
    adapter = support.adapter(transport=transport, product="CIVIL_NX")
    await adapter.connect(support.connect_config())
    outcome = await adapter.execute_normalized("MODEL.NODE.QUERY", {}, _NO_CONTEXT)
    items = outcome["data"]["read"]
    assert items and items[0]["id"] == "1" and items[0]["x"] == 0.0
    assert transport.calls[-1][:2] == ("GET", "/DB/NODE")
    await adapter.disconnect()


async def test_p134_designer_envelope_is_unwrapped_by_result_return_value() -> None:
    """`CIVIL_DESIGNER` 信封：业务载荷在 `result.return_value`（R83）。"""
    transport = _designer_transport()
    adapter = support.adapter(transport=transport, product="CIVIL_DESIGNER")
    await adapter.connect(support.connect_config())
    outcome = await adapter.execute_normalized("MODEL.NODE.QUERY", {}, _NO_CONTEXT)
    items = outcome["data"]["read"]
    # 业务载荷确实来自 `result.return_value`（R83）：几何被 Transformer 映射为 canonical
    assert items and items[0]["x"] == 0.0 and items[0]["y"] == 0.0 and items[0]["z"] == 0.0
    assert transport.calls[-1][:2] == ("GET", "/DB/NODE")
    assert adapter.registry is not None
    assert adapter.registry.resolve(
        key="DB.NODE", product="CIVIL_DESIGNER", method="GET"
    ).read_path == ("result", "return_value")
    await adapter.disconnect()


async def test_p134_swapped_envelopes_fail_loudly_instead_of_degrading_silently() -> None:
    """信封互换**必须明确报错**（旧实现退回整包 → 字段全 `None`，R83 的静默降级）。"""
    wrong = EnvelopeTransport(
        {("GET", "/DB/NODE"): {"NODE": {"1": {"X": 0.0, "Y": 0.0, "Z": 0.0}}}}
    )
    adapter = support.adapter(transport=wrong, product="CIVIL_DESIGNER")
    await adapter.connect(support.connect_config())
    with pytest.raises(Exception) as failure:
        await adapter.execute_normalized("MODEL.NODE.QUERY", {}, _NO_CONTEXT)
    assert getattr(failure.value, "code", "") == "STRUCTAI-2200"
    assert failure.value.details["reason"] == "response_envelope_mismatch"
    assert failure.value.details["missing_step"] == "result"
    await adapter.disconnect()

    other = EnvelopeTransport({("GET", "/DB/NODE"): _designer_envelope([])})
    adapter = support.adapter(transport=other, product="CIVIL_NX")
    await adapter.connect(support.connect_config())
    with pytest.raises(Exception) as failure:
        await adapter.execute_normalized("MODEL.NODE.QUERY", {}, _NO_CONTEXT)
    assert failure.value.details["missing_step"] == "NODE"
    await adapter.disconnect()


def test_p134_undeclared_read_path_is_rejected_by_the_single_unwrap_point() -> None:
    """数据侧**未声明**解包链 → `STRUCTAI-3000`（**不**把整包当载荷）。"""
    resolved = _synthetic_endpoint(key="SYNTHETIC.NO_ROOT", read_root="")
    assert resolved.read_path == ()
    with pytest.raises(Exception) as failure:
        _unwrap({"anything": 1}, resolved)
    assert getattr(failure.value, "code", "") == "STRUCTAI-3000"
    assert failure.value.details["reason"] == "endpoint_read_path_undeclared"


def _synthetic_endpoint(*, key: str, read_root: str) -> ResolvedEndpoint:
    """构造一个合成端点（分类与解包链的单元断言用）。"""
    definition = EndpointDefinition(
        key=key,
        namespace="DB",
        uri=f"/DB/{key.rsplit('.', 1)[-1]}",
        methods=("GET",),
        products=("CIVIL_NX",),
        wrapper_write="Argument",
        read_root=read_root,
        schema_path="",
        schema_shape="",
        solver="",
        execution_mode="FAST",
        availability="verified",
        enabled=True,
        disable_reason="",
        risk_level="low",
        destructive=False,
        delete_without_body_is_global=False,
        table_type="",
        title="",
        provenance=("probe",),
        overrides={},
    )
    return ResolvedEndpoint(
        definition=definition,
        product="CIVIL_NX",
        method="GET",
        uri=definition.uri,
        wrapper_write="Argument",
        wrapper_shape="",
        body_kind="",
        read_root=read_root,
        delete_all_via_body=False,
    )


def _synthetic_registry() -> MidasRegistry:
    """合成 Registry（分类口径的单元断言用）。"""
    definitions = {
        "DB.OK": _synthetic_endpoint(key="DB.OK", read_root="OK").definition,
        "DB.EMPTY": _synthetic_endpoint(key="DB.EMPTY", read_root="EMPTY").definition,
        "DB.MISSING": _synthetic_endpoint(key="DB.MISSING", read_root="MISSING").definition,
        "DB.UNROOTED": _synthetic_endpoint(key="DB.UNROOTED", read_root="").definition,
        "DB.ABSENT": _synthetic_endpoint(key="DB.ABSENT", read_root="ABSENT").definition,
    }
    return MidasRegistry(root=Path("."), definitions=definitions, order=tuple(definitions))


# ===== P134a：L4 探针 =====


async def test_p134_l4_probe_classifies_status_and_envelope() -> None:
    """分类口径（R76 / R84）：命中 / 空块 / 信封不符 / 未声明 / 404。"""
    transport = EnvelopeTransport(
        {
            ("GET", "/DB/OK"): {"OK": {"1": {"X": 0.0}}},
            ("GET", "/DB/EMPTY"): {"message": ""},
            ("GET", "/DB/MISSING"): {"OTHER": {"1": {}}},
            ("GET", "/DB/UNROOTED"): {"ANY": 1},
        }
    )
    client = _client(transport)
    prober = MidasLiveProber(client, _synthetic_registry(), instance="probe", product="CIVIL_NX")
    assert prober.instance == "probe" and prober.product == "CIVIL_NX"
    report = await prober.probe_all_read_endpoints()
    outcomes = {result.key: (result.outcome, result.detail) for result in report.results}
    assert outcomes["DB.OK"] == (PROBE_PASSED, "envelope_confirmed")
    assert outcomes["DB.EMPTY"] == (PROBE_PARTIAL, "empty_data_block")
    assert outcomes["DB.MISSING"] == (PROBE_FAILED, "response_envelope_mismatch:MISSING")
    assert outcomes["DB.UNROOTED"] == (PROBE_PARTIAL, "read_root_undeclared_in_registry")
    assert outcomes["DB.ABSENT"] == (PROBE_FAILED, "http_404")
    assert report.counts() == {PROBE_FAILED: 2, PROBE_PARTIAL: 2, PROBE_PASSED: 1}
    assert len(report.failures()) == 2 and len(report.undeclared()) == 1
    assert prober.read_keys() == ("DB.OK", "DB.EMPTY", "DB.MISSING", "DB.UNROOTED", "DB.ABSENT")
    # 记录里**只**有状态码 / 键名 / 哈希，不含响应体原文与凭据
    passed = next(result for result in report.results if result.key == "DB.OK")
    record = passed.as_record(version_range=VERSION_RANGE)
    assert set(record) == {
        "endpoint_key",
        "contract_level",
        "product",
        "version_range",
        "method",
        "path",
        "status",
        "schema_hash",
        "detail",
        "verified_at",
    }
    assert support.SECRET not in json.dumps(record, default=str)
    await client.close()


async def test_p134_l4_records_are_written_and_queryable(tmp_path: Path) -> None:
    """L4 记录**真实写入且可回查**，且幂等（`docs/04` §18）。"""
    engine = support.engine_for(tmp_path)
    await support.midas_tables(engine)
    factory = support.session_factory_for(engine)
    async with factory() as session:
        await MidasRegistryImporter(support.registry()).import_all(session)
        await session.commit()

    transport = EnvelopeTransport(
        {
            ("GET", "/OPE/PROJECTSTATUS"): {"PROJECTSTATUS": {"NAME": "P134"}},
            ("GET", "/DB/NODE"): {"NODE": {"1": {"X": 0.0, "Y": 0.0, "Z": 0.0}}},
        }
    )
    client = _client(transport)
    prober = MidasLiveProber(client, support.registry(), instance="l4-offline", product="CIVIL_NX")
    report = await prober.probe_keys(("OPE.PROJECTSTATUS", "DB.NODE"))
    assert report.counts() == {PROBE_PASSED: 2}

    async with factory() as session:
        first = await record_verifications(session, report.results, version_range=VERSION_RANGE)
        await session.commit()
    assert first == {"inserted": 2, "updated": 0, "unchanged": 0}

    async with factory() as session:
        rows = await read_verifications(session, key="DB.NODE")
        assert len(rows) == 1
        row = rows[0]
        assert row.contract_level == CONTRACT_LEVEL_L4
        assert (row.status, row.method, row.path) == (PROBE_PASSED, "GET", "/DB/NODE")
        assert row.detail == "envelope_confirmed"
        assert row.schema_hash.startswith("sha256:") and row.verified_at is not None

    async with factory() as session:
        second = await record_verifications(session, report.results, version_range=VERSION_RANGE)
        await session.commit()
    # 第二次**不新增行**（`verified_at` 按语义推进 → 记 `updated`，但绝无重复行）
    assert second["inserted"] == 0
    assert second["updated"] + second["unchanged"] == 2
    async with factory() as session:
        levels = (
            (await session.execute(select(MidasApiVerificationORM.contract_level))).scalars().all()
        )
    assert list(levels) == [CONTRACT_LEVEL_L4, CONTRACT_LEVEL_L4]
    await client.close()
    await engine.dispose()


# ===== P134d：7 项 AND（R78）=====


def test_p134_seven_and_verdict_requires_every_item() -> None:
    """缺任何一项都**不得** `VERIFIED`；缺键按 False 处理（**不**假定满足）。"""
    assert SEVEN_AND_ITEMS == (
        "official_endpoint_confirmed",
        "http_method_confirmed",
        "request_schema_confirmed",
        "response_schema_confirmed",
        "product_scope_confirmed",
        "version_range_confirmed",
        "live_contract_test_passed",
    )
    empty = seven_and_verdict({})
    assert empty.status == STATUS_PARTIAL
    assert empty.missing == SEVEN_AND_ITEMS and empty.is_verified is False
    complete = seven_and_verdict({item: True for item in SEVEN_AND_ITEMS})
    assert complete.status == STATUS_VERIFIED and complete.is_verified is True
    assert complete.missing == ()


def test_p134_measured_endpoints_stay_partial_because_response_schema_is_missing() -> None:
    """实测通过 L4 的端点**仍**保持 `PARTIAL`：缺「Response Schema 已确认」（R78）。"""
    registry = support.registry()

    def evidence(key: str, **overrides: Any) -> dict[str, bool]:
        base = registry_evidence(
            registry,
            key=key,
            product="GEN_NX",
            version="2026",
            supported_versions=support.SUPPORTED_VERSIONS_SPEC,
            live_outcome=PROBE_PASSED,
        )
        assert set(base) == set(SEVEN_AND_ITEMS)
        return {**base, **overrides}

    for key in ("DB.NODE", "DB.MATL", "DB.SECT", "DB.UNIT"):
        verdict = seven_and_verdict(evidence(key))
        assert verdict.status == STATUS_PARTIAL, key
        assert verdict.missing == ("response_schema_confirmed",), key
        assert verdict.as_dict()["satisfied"] == [
            item for item in SEVEN_AND_ITEMS if item != "response_schema_confirmed"
        ]
    # 无请求 Schema 的端点缺**两项**，同样如实标注（**不**猜、**不**补）
    project_status = seven_and_verdict(evidence("OPE.PROJECTSTATUS"))
    assert project_status.status == STATUS_PARTIAL
    assert project_status.missing == (
        "request_schema_confirmed",
        "response_schema_confirmed",
    )
    # 补上 response Schema 后同一判定点会升级（证明 AND 是真的）
    assert seven_and_verdict(evidence("DB.NODE", response_schema_confirmed=True)).status == (
        STATUS_VERIFIED
    )
    # 未实测 → 第 7 项为假；版本不在声明范围 → 第 6 项为假
    assert seven_and_verdict(evidence("DB.NODE", live_contract_test_passed=False)).status == (
        STATUS_PARTIAL
    )
    assert (
        registry_evidence(
            registry,
            key="DB.NODE",
            product="GEN_NX",
            version="2027",
            supported_versions=support.SUPPORTED_VERSIONS_SPEC,
            live_outcome=PROBE_PASSED,
        )["version_range_confirmed"]
        is False
    )


# ===== P134c：L5 业务效果 =====


async def test_p134_l5_offline_create_read_delete_only_touches_its_own_id() -> None:
    """L5 三步链：创建 → 读回 → 删除，`DELETE` **必须**带路径 key（`docs/07` §6.4）。"""
    transport = NxNodeTransport()
    client = _client(transport)
    effect = MidasLiveBusinessEffect(
        client,
        support.registry(),
        product="CIVIL_NX",
        project=DedicatedTestProject(name="dedicated"),
        node_key="DB.NODE",
        marker=1.0,
    )
    outcome = await effect.run()
    assert outcome.outcome == PROBE_PASSED
    assert outcome.steps == ("list_existing", "create", "read_back", "delete")
    # 只挑**未被占用**的编号（既有 `1` → 新建 `2`），绝不覆盖既有节点
    assert outcome.created_id == "2" and outcome.read_back and outcome.deleted
    assert [method for method, _path, _body in transport.calls] == [
        "GET",
        "POST",
        "GET",
        "DELETE",
    ]
    assert [path for _method, path, _body in transport.calls] == [
        "/DB/NODE",
        "/DB/NODE",
        "/DB/NODE",
        "/DB/NODE/2",
    ]
    # 创建体走数据侧的 Transformer（canonical → native）与 `Assign` 包装
    create_body = transport.calls[1][2]
    assert isinstance(create_body, dict) and set(create_body) == {"Assign"}
    assert set(create_body["Assign"]) == {"2"}
    await client.close()


async def test_p134_l5_refuses_without_a_dedicated_test_project_declaration() -> None:
    """缺专用测试项目声明 → **明确拒绝**（`STRUCTAI-3000`），**不**回落当前项目。"""
    client = _client(_designer_transport())
    effect = MidasLiveBusinessEffect(
        client, support.registry(), product="CIVIL_DESIGNER", project=None
    )
    assert effect.project is None
    with pytest.raises(Exception) as failure:
        await effect.run()
    assert getattr(failure.value, "code", "") == "STRUCTAI-3000"
    assert failure.value.details["reason"] == "dedicated_test_project_not_declared"
    assert dedicated_test_project_from_env({}) is None
    declared = dedicated_test_project_from_env({LIVE_PROJECT_ENV: "P134-DEDICATED"})
    assert declared is not None and declared.name == "P134-DEDICATED"
    assert "P134-DEDICATED" not in repr(declared)  # 项目名不进诊断表示
    assert live_opt_in_from_env({MIDAS_LIVE_ENV: "1"}) is True
    assert live_opt_in_from_env({}) is False
    await client.close()


# ===== 真实实例（L4 / L5）：无环境即跳过 =====


@pytest.mark.skipif(not _live_enabled(), reason="L4/L5 需显式 opt-in + MIDAS 实例环境")
async def test_p134_l4_live_probe_writes_records_for_the_real_instance(tmp_path: Path) -> None:
    """真实 L4：只读探测 → 写记录 → 回查（`docs/04` §69 / §71）。"""
    engine = support.engine_for(tmp_path)
    await support.midas_tables(engine)
    factory = support.session_factory_for(engine)
    async with factory() as session:
        await MidasRegistryImporter(support.registry()).import_all(session)
        await session.commit()

    client = _live_client()
    prober = MidasLiveProber(client, support.registry(), instance="live", product="GEN_NX")
    report = await prober.probe_keys(LIVE_KEYS)
    assert len(report.results) == len(LIVE_KEYS)
    for result in report.results:
        assert result.method == "GET"
        assert result.status_code in {200, 0}
        assert support.SECRET not in json.dumps(
            result.as_record(version_range=VERSION_RANGE), default=str
        )
    passed = [result for result in report.results if result.is_passed]
    assert passed, report.counts()

    async with factory() as session:
        counts = await record_verifications(session, report.results, version_range=VERSION_RANGE)
        await session.commit()
    assert counts["inserted"] == len(LIVE_KEYS)
    async with factory() as session:
        rows = await read_verifications(session, key=passed[0].key)
        assert rows and rows[0].status == passed[0].outcome
    await client.close()
    await engine.dispose()


@pytest.mark.skipif(
    not _live_enabled() or dedicated_test_project_from_env(os.environ) is None,
    reason="L5 需专用测试项目声明（docs/04 §72 第 3 要素）",
)
async def test_p134_l5_live_business_effect_on_the_dedicated_project(tmp_path: Path) -> None:
    """真实 L5：专用测试项目上「创建 → 读回 → 删除」**只**碰自己创建的 ID。"""
    engine = support.engine_for(tmp_path)
    await support.midas_tables(engine)
    factory = support.session_factory_for(engine)
    client = _live_client()
    effect = MidasLiveBusinessEffect(
        client,
        support.registry(),
        product="GEN_NX",
        project=dedicated_test_project_from_env(os.environ),
        node_key="DB.NODE",
    )
    outcome = await effect.run()
    assert outcome.deleted is True
    assert outcome.created_id, "L5 必须记下自己创建的 ID"
    assert outcome.read_back is True and outcome.is_passed, outcome.detail
    async with factory() as session:
        session.add(
            MidasApiVerificationORM(
                **outcome.as_record(version_range=VERSION_RANGE, path="/DB/NODE")
            )
        )
        await session.commit()
    async with factory() as session:
        stored = (
            (
                await session.execute(
                    select(MidasApiVerificationORM).where(
                        MidasApiVerificationORM.contract_level == "L5"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(stored) == 1 and stored[0].status == PROBE_PASSED
    await client.close()
    await engine.dispose()
