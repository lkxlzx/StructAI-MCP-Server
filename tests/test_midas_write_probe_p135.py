"""P135d 验收（第二片）：R4 / R14 写路径收口 + R85 / R87 / R90 数据侧 + 新模块红线。

权威来源
--------
- `docs/07` §16 **R4**（写路径实测覆盖 11 / 369）· **R14**（写路径端点未被只读探针覆盖）·
  **R85**（L4 实测的 43 条产品可得性差异）· **R87** / **R90**（缺 response 方向 Schema）。
- `docs/07` §6.4 / §7.6 —— NX 系 `DELETE` **必须**带路径 key（不带 = 删全表）。
- `docs/04` §72 —— 专用测试项目声明**只**经环境变量。

落地裁决（本文件的硬事实，不美化）
--------------------------------
1. **R4 / R14 收口**：`MidasLiveWriteProbe` 对「有写方法 + 有读路径 + 有 Transformer」的端点
   逐个执行 `list → create → read_back → delete`，**只**碰自己创建的编号、
   `DELETE` **必须**带路径 key、危险端点一律排除；无专用测试项目声明 → **明确拒绝**
   （`STRUCTAI-3000`）。
2. **R85 已按实测落进数据（P136a）**：不可得的产品从 `products` 摘除、`unavailable_on`
   保留实例级记录；判定口径（`availability` → `verification_status`）**一行未改**，
   故本批**不**升级任何 `verification_status`（改数据不改判定）。
3. **R87 已收口（P136b）**：数据侧为**已实测**的端点补了 `direction: response` 的
   `response` 块（`registry/tools/sync_response_schemas.py`），故「Response Schema 已确认」
   **按数据如实判定**：实测端点（`DB.NODE` 等）7 项 AND 全满足 → `VERIFIED`；
   未实测 / 无 Schema 的端点仍**如实**缺项并保持 `PARTIAL`（**不**臆造）。
   **R90（ETABS）不变**：无 ETABS 实测 → 不升。
4. **新模块不得越界**（`docs/07` §14.1 / §14.2）。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

import midas_p119_p126_support as support
from app.infrastructure.adapters.midas import write_probe
from app.infrastructure.adapters.midas.client import (
    MidasEnvironmentCredential,
    MidasHttpClient,
)
from app.infrastructure.adapters.midas.live import DedicatedTestProject
from app.infrastructure.adapters.midas.registry import MidasRegistry

R85_GEN_NX_PRODUCT_GAPS: tuple[str, ...] = (
    "DB.CAMB",
    "DB.CJFG",
    "DB.CMCS",
    "DB.CRGR",
    "DB.DYFG",
    "DB.DYLA",
    "DB.DYNF",
    "DB.EWSF",
    "DB.GCMB",
    "DB.GSBG",
    "DB.PLCB",
    "DB.RCHK",
    "DB.STRPSSM",
    "DB.WVLD",
)
"""`docs/07` §16 R85：L4 实测在 **GEN NX** 上 `404` 而数据侧曾声明 `GEN_NX` 的 14 个端点。

⚠️ `DB.SPAN` **不**在此列：R85 的 15 条「桥梁 / 铁路专项表」里它**不算**产品差异
（实测在 `CIVIL_NX` + `CIVIL_DESIGNER` 上可用，是**产品特有**端点），故本批**不**动它。
"""

R85_CIVIL_NX_PRODUCT_GAPS: tuple[str, ...] = (
    "DB.SDHY",
    "DB.SDIS",
    "DB.THRS",
    "DB.UFTR",
    "DB.UTBL",
    "DESIGN.RC.KDS-41-20-2022.MATD",
    "DESIGN.SRC.AIK-SRC2K.MATD",
)
"""`docs/07` §16 R85：L4 实测在 **CIVIL NX** 上 `404` 的 7 个端点（逐条复算报告 §4.2）。"""

R85_CIVIL_NX_PRODUCT_GAPS_REMOVED: tuple[str, ...] = (
    "DB.SDHY",
    "DB.SDIS",
    "DB.THRS",
    "DESIGN.RC.KDS-41-20-2022.MATD",
    "DESIGN.SRC.AIK-SRC2K.MATD",
)
"""其中数据侧原先声明了 `CIVIL_NX` → 已按实测**摘除**（P136a）。"""

R85_CIVIL_NX_PRODUCT_GAPS_UNVERIFIED: tuple[str, ...] = ("DB.UFTR", "DB.UTBL")
"""其中数据侧**本来**就标了 `availability: unverified` + `unavailable_on: [civil-cloud]`
（`products` 保留 `CIVIL_NX`）→ 已如实记录，本批**不动**（改反而会臆造）。"""

NODE_KEY = "DB.NODE"


class NxTransport(httpx.MockTransport):
    """有状态的 NX 假传输：创建后读回可见、按路径 key 删除后消失。"""

    def __init__(self, *, prefix: str = "/civil") -> None:
        """空节点表（含一个既有编号 `1`，用于验证「只挑未占用编号」）。"""
        self.nodes: dict[str, Any] = {"1": {"X": 0.0, "Y": 0.0, "Z": 0.0}}
        self.calls: list[tuple[str, str, Any]] = []
        self._prefix = prefix
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        """按 `(method, path)` 应答（未命中 → `404`，与真实软件同形）。"""
        path = request.url.path
        if self._prefix and path.startswith(self._prefix):
            path = path[len(self._prefix) :]
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


def _registry() -> MidasRegistry:
    """数据侧 Registry（`registry/` 的唯一权威来源）。"""
    return support.registry()


def _manifest_entry(key: str) -> dict[str, Any]:
    """`registry/manifest.json` 的一条端点记录（`unavailable_on` 等字段的唯一来源）。"""
    document = json.loads((_registry().root / "manifest.json").read_text(encoding="utf-8"))
    for entry in document["endpoints"]:
        if entry["key"] == key:
            return entry
    raise AssertionError(f"{key} not in registry/manifest.json")


_UNSET: Any = object()
"""哨兵：区分「未传 project」与「显式传 `None`」（后者必须被拒绝）。"""


def _probe(transport: NxTransport, *, limit: int = 1, project: Any = _UNSET) -> Any:
    """构造一个写路径探针（缺省带专用测试项目声明；显式传 `None` 即「未声明」）。"""
    declared = DedicatedTestProject(name="p135") if project is _UNSET else project
    return write_probe.MidasLiveWriteProbe(
        _client(transport),
        _registry(),
        product="CIVIL_NX",
        project=declared,
        limit=limit,
    )


def _first_transformer_key(probe: Any) -> str:
    """候选端点里**有**数据侧 Transformer 的第一个 key（写路径三步链需要它）。"""
    from app.infrastructure.adapters.midas.transforms import TRANSFORMER_REGISTRY

    for key in probe.candidate_keys():
        if write_probe.transformer_name_for(key) in TRANSFORMER_REGISTRY:
            return key
    raise AssertionError("no candidate endpoint has a registered transformer")


# ===== R4 / R14：写路径收口 =====


def test_p135d_transformer_names_are_derived_only_for_db_endpoints() -> None:
    """Transformer 名由端点 key 机械派生（`midas.<code 小写>.v1`）；其余一律空串。"""
    assert write_probe.transformer_name_for("DB.NODE") == "midas.node.v1"
    assert write_probe.transformer_name_for("DB.MATL") == "midas.matl.v1"
    assert write_probe.transformer_name_for("POST.TABLE") == ""
    assert write_probe.transformer_name_for("DESIGN.STEEL") == ""
    assert write_probe.transformer_name_for("DB.") == ""


def test_p135d_body_derivation_prefers_declared_values_and_never_invents() -> None:
    """请求体**只**按 Schema 取 `default` / `const` / `enum[0]` / `examples[0]` / 类型零值。"""
    assert write_probe.derive_body({"default": 7, "type": "integer"}) == 7
    assert write_probe.derive_body({"const": "X"}) == "X"
    assert write_probe.derive_body({"enum": ["A", "B"], "type": "string"}) == "A"
    assert write_probe.derive_body({"type": "string"}) == "structai-probe"
    assert write_probe.derive_body({"type": "boolean"}) is False
    assert write_probe.derive_body({"type": "array"}) == []
    assert write_probe.derive_body({"type": "object"}) == {}
    assert write_probe.derive_body(
        {"type": "object", "required": ["a"], "properties": {"a": {"type": "integer"}}}
    ) == {"a": 0}
    # 取不到 → `None`（调用方据此记 `NO_PAYLOAD_TEMPLATE`，**不**猜）
    assert write_probe.derive_body(None) is None
    assert (
        write_probe.derive_body({"type": "object", "required": ["a"], "properties": {"a": {}}})
        is None
    )


def test_p135d_candidate_keys_exclude_destructive_and_unreadable_endpoints() -> None:
    """候选端点**只**取「有写方法 + 有读路径 + 有 Transformer + 非危险形态」（见裁决 1）。"""
    probe = _probe(NxTransport(), limit=0)
    keys = probe.candidate_keys()
    key = _first_transformer_key(probe)
    assert key in keys
    assert all(candidate.startswith("DB.") for candidate in keys)
    definition = _registry().endpoint(key)
    assert definition.enabled is True and definition.destructive is False
    assert "POST" in definition.methods and "GET" in definition.methods
    # `-M1`（HYPER_S 专属）不进入候选：它要求 `solver = HYPER_S`
    assert all("-M1" not in candidate for candidate in keys)


async def test_p135d_write_probe_creates_reads_back_and_deletes_only_its_own_id() -> None:
    """三步链：只挑**未被占用**的编号 → 创建 → 读回 → **带路径 key** 删除（见裁决 1）。"""
    transport = NxTransport()
    # 用 `DB.NODE` 的语义做三步链（假传输只实现它；候选集合由 `candidate_keys` 决定）
    assert write_probe.transformer_name_for("DB.NODE") == "midas.node.v1"
    probe = write_probe.MidasLiveWriteProbe(
        _client(transport),
        _registry(),
        product="CIVIL_NX",
        project=DedicatedTestProject(name="p135"),
        limit=0,
        only=("DB.NODE",),
    )
    report = await probe.probe()
    assert report.product == "CIVIL_NX"
    assert report.keys() == ("DB.NODE",)
    outcome = report.outcomes[0]
    assert outcome.is_passed is True, outcome
    assert outcome.created_id == "2", "既有编号 1 → 只挑未占用的 2（绝不覆盖既有节点）"
    assert outcome.read_back is True and outcome.deleted is True
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
    assert "2" not in transport.nodes and "1" in transport.nodes
    assert support.SECRET not in json.dumps(
        {
            "key": outcome.key,
            "method": outcome.method,
            "path": outcome.path,
            "detail": outcome.detail,
            "created_id": outcome.created_id,
        },
        default=str,
    )


async def test_p135d_write_probe_refuses_without_a_dedicated_test_project() -> None:
    """缺专用测试项目声明 → **明确拒绝**（`STRUCTAI-3000`），**不**回落当前项目。"""
    transport = NxTransport()
    probe = _probe(transport, project=None)
    assert probe.project is None
    with pytest.raises(Exception) as failure:
        await probe.probe()
    assert getattr(failure.value, "code", "") == "STRUCTAI-3000"
    assert failure.value.details["reason"] == "dedicated_test_project_not_declared"
    assert transport.calls == [], "拒绝路径**零** transport 调用"


async def test_p135d_write_probe_reports_native_failures_without_raising() -> None:
    """原生失败只**归类**（`FAILED`），**不**上抛；且兜底只删自己创建的编号。"""

    class SilentCreateTransport(NxTransport):
        """POST **不**写入节点表的假传输（读回必然缺失）。"""

        def _handle(self, request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                body = json.loads(request.content) if request.content else None
                self.calls.append((request.method, request.url.path, body))
                return httpx.Response(200, json={"Assign": {}})
            return super()._handle(request)

    transport = SilentCreateTransport()
    probe = write_probe.MidasLiveWriteProbe(
        _client(transport),
        _registry(),
        product="CIVIL_NX",
        project=DedicatedTestProject(name="p135"),
        limit=0,
        only=("DB.NODE",),
    )
    report = await probe.probe()
    outcome = report.outcomes[0]
    assert outcome.outcome == write_probe.WRITE_PROBE_FAILED, outcome
    assert outcome.detail == "read_back_missing", outcome
    assert outcome.created_id == "2"
    assert report.failures() and not report.passed()
    assert any(path == "/DB/NODE/2" for _method, path, _body in transport.calls)


def test_p135d_a_short_write_surface_is_reported_not_hidden() -> None:
    """R4 的**可执行判定**：候选写路径端点数是**实测出来的**，不是声称的。

    只读探针覆盖不到写路径（R14），故这里如实报出「本批可自动跑通的写路径端点数」。
    """
    probe = _probe(NxTransport(), limit=0)
    keys = probe.candidate_keys()
    assert len(keys) >= 1
    assert len(keys) == len(set(keys))
    assert all(_registry().endpoint(key).destructive is False for key in keys)
    assert keys == tuple(sorted(keys, key=lambda key: _registry().keys().index(key)))


# ===== R85：产品可得性差异按实测落进数据（P136a）=====


def test_p135d_r85_gen_nx_product_gaps_are_recorded_as_measured() -> None:
    """R85：GEN NX 上实测 `404` 的端点**已按实测**把 `GEN_NX` 从 `products` 摘除。

    数据侧改动 = **只**改 `products`（`unavailable_on` 保留实例级实测记录）；
    判定口径（`availability` → `verification_status`）**一行未改**，故解析期对
    `GEN_NX` **如实失败**（`STRUCTAI-3000`），而不是发出一个必然 `404` 的请求。
    """
    registry = _registry()
    for key in R85_GEN_NX_PRODUCT_GAPS:
        definition = registry.endpoint(key)
        assert "GEN_NX" not in definition.products, key
        assert "CIVIL_NX" in definition.products, key
        assert "gen-local" in _manifest_entry(key)["unavailable_on"], key
        assert definition.availability == "verified", key
        with pytest.raises(Exception) as failure:
            registry.resolve(key=key, product="GEN_NX", method="GET")
        assert getattr(failure.value, "code", "") == "STRUCTAI-3000", key
        assert failure.value.details["reason"] == "endpoint_not_available_for_product", key
        resolved = registry.resolve(key=key, product="CIVIL_NX", method="GET")
        assert resolved.verification_status == definition.verification_status, key


def test_p135d_r85_civil_nx_product_gaps_are_recorded_as_measured() -> None:
    """R85：CIVIL NX 上实测 `404` 的 7 个端点同样按实测收口（两种情形都如实记录）。"""
    registry = _registry()
    for key in R85_CIVIL_NX_PRODUCT_GAPS:
        assert "civil-cloud" in _manifest_entry(key)["unavailable_on"], key
    for key in R85_CIVIL_NX_PRODUCT_GAPS_REMOVED:
        definition = registry.endpoint(key)
        assert "CIVIL_NX" not in definition.products, key
        assert "GEN_NX" in definition.products, key
        with pytest.raises(Exception) as failure:
            registry.resolve(key=key, product="CIVIL_NX", method="GET")
        assert getattr(failure.value, "code", "") == "STRUCTAI-3000", key
    for key in R85_CIVIL_NX_PRODUCT_GAPS_UNVERIFIED:
        definition = registry.endpoint(key)
        # 数据侧原本已标 `unverified` + `unavailable_on` → **不动**（改反而会臆造）
        assert definition.products == ("CIVIL_NX",), key
        assert definition.availability == "unverified", key
        assert definition.verification_status == "UNVERIFIED", key


def test_p135d_r85_span_is_a_product_specific_endpoint() -> None:
    """R85：`DB.SPAN` **不**在 GEN NX 清单里，且在 `CIVIL_DESIGNER` 上可用（产品特有）。"""
    definition = _registry().endpoint("DB.SPAN")
    assert "CIVIL_DESIGNER" in definition.products
    assert "DB.SPAN" not in R85_GEN_NX_PRODUCT_GAPS


def test_p135d_r85_measurement_never_promotes_a_verification_status() -> None:
    """R85 / R78：判定口径仍**只**由 `availability` 机械映射（数据改动不升级状态）。"""
    registry = _registry()
    for key in (*R85_GEN_NX_PRODUCT_GAPS, *R85_CIVIL_NX_PRODUCT_GAPS):
        definition = registry.endpoint(key)
        resolved = registry.resolve(key=key, product=definition.products[0], method="GET")
        assert resolved.verification_status == definition.verification_status, key
        assert resolved.verification_status in {
            "VERIFIED",
            "UNVERIFIED",
            "PARTIAL",
            "DEPRECATED",
        }


# ===== R87：response 方向 Schema 已按实测补齐（P136b）=====


def test_p135d_r87_response_schema_is_declared_for_measured_endpoints() -> None:
    """R87：已实测端点声明了 `direction: response`；请求方向原文**未被改写**。"""
    registry = _registry()
    for key in ("DB.NODE", "DB.MATL", "DB.SECT", "DB.UNIT"):
        document = registry.schema_document(key)
        assert document is not None, key
        # 请求方向：数据侧原文（无 `direction` 键 → 按 `request` 解读，一行未改）
        assert str(document.get("direction") or "request") == "request", key
        block = registry.response_schema_document(key)
        assert block is not None and block["direction"] == "response", key
        assert registry.response_schema_json(key) is not None, key
    # 未实测 / 无 Schema 的端点**没有** response 块（**不**臆造）
    assert registry.response_schema_document("DB.SWIND") is None
    assert registry.response_schema_document("OPE.PROJECTSTATUS") is None


def test_p135d_r87_the_response_schema_is_the_only_reason_for_partial() -> None:
    """R87 / R78：补上 response 方向 Schema 后**同一判定点**升 `VERIFIED`（AND 是真的）。"""
    from app.infrastructure.adapters.midas.live import (
        PROBE_PASSED,
        SEVEN_AND_ITEMS,
        STATUS_PARTIAL,
        STATUS_VERIFIED,
        registry_evidence,
        seven_and_verdict,
    )

    registry = _registry()
    evidence = registry_evidence(
        registry,
        key="DB.NODE",
        product="GEN_NX",
        version="2026",
        supported_versions=support.SUPPORTED_VERSIONS_SPEC,
        live_outcome=PROBE_PASSED,
    )
    assert set(evidence) == set(SEVEN_AND_ITEMS)
    assert evidence["response_schema_confirmed"] is True
    verdict = seven_and_verdict(evidence)
    assert verdict.status == STATUS_VERIFIED
    assert verdict.missing == ()
    # 把该项改回假 → **只**缺这一项、立刻回到 `PARTIAL`（证明 AND 是真的）
    downgraded = seven_and_verdict({**evidence, "response_schema_confirmed": False})
    assert downgraded.status == STATUS_PARTIAL
    assert downgraded.missing == ("response_schema_confirmed",)
    # 无请求 Schema 的端点仍缺**两项**（如实标注，**不**补）
    project_status = seven_and_verdict(
        registry_evidence(
            registry,
            key="OPE.PROJECTSTATUS",
            product="GEN_NX",
            version="2026",
            supported_versions=support.SUPPORTED_VERSIONS_SPEC,
            live_outcome=PROBE_PASSED,
        )
    )
    assert project_status.status == STATUS_PARTIAL
    assert project_status.missing == (
        "request_schema_confirmed",
        "response_schema_confirmed",
    )


# ===== 红线 =====


def test_p135d_new_modules_do_not_cross_the_layer_boundaries() -> None:
    """新模块**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx / `app.application`（红线）。"""
    paths = (
        Path("app/infrastructure/adapters/midas/hardening.py"),
        Path("app/infrastructure/adapters/midas/write_probe.py"),
        Path("app/infrastructure/adapters/etabs/hardening.py"),
        Path("app/infrastructure/adapters/etabs/dispatch.py"),
        Path("app/infrastructure/adapters/etabs/concurrency.py"),
    )
    forbidden = (
        "sqlalchemy",
        "fastapi",
        "mcp",
        "httpx",
        "app.interfaces",
        "app.observability",
        "app.application",
        "app.container",
    )
    for path in paths:
        modules = _imported_modules(path)
        for name in forbidden:
            assert not any(module == name or module.startswith(f"{name}.") for module in modules), (
                path,
                name,
            )


def test_p135d_write_probe_module_is_read_only_about_the_database() -> None:
    """写路径探针**不**碰数据库 / 不建表（只经 `registry/` + 注入的客户端）。"""
    modules = _imported_modules(Path("app/infrastructure/adapters/midas/write_probe.py"))
    assert not any(name.startswith("app.infrastructure.database") for name in modules)
    assert "app.infrastructure.adapters.midas.live" in modules


def _imported_modules(path: Path) -> set[str]:
    """模块级 import 的模块名集合（AST 扫描）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules
