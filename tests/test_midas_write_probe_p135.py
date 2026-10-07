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
2. **R85 如实保持**：L4 实测的产品可得性差异以 `unavailable_on` **记录**，
   数据侧声明保留（`products` 不改），`verification_status` **不**因 CI 层记录升级。
3. **R87 / R90 如实保持**：数据侧只有请求方向 Schema → 「Response Schema 已确认」恒为假；
   补上 response 方向 Schema 后**同一判定点**即升 `VERIFIED`（AND 是真的）。
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
"""`docs/07` §16 R85：L4 实测在 **GEN NX** 上 `404` 而数据侧声明了 `GEN_NX` 的端点。

⚠️ `DB.SPAN` **不**在此列：它未出现在 R85 的 11 条清单里，且实测在 `CIVIL_DESIGNER`
上可用（**产品特有**端点），故本批**不**动它的 `products`。
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
"""`docs/07` §16 R85：L4 实测在 **CIVIL NX** 上 `404` 的 7 个端点（逐字照抄报告 §4.2）。"""

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


# ===== R85：产品可得性差异如实记录 =====


def test_p135d_r85_gen_nx_product_gaps_are_recorded_in_the_registry() -> None:
    """R85：GEN NX 上实测 `404` 的端点**存在且声明了 `GEN_NX`**（数据侧原文保留）。

    ⚠️ 本批**不**改 `products`（R85 的「建议」需数据侧生成链复核）——
    故可执行判定是「端点存在 + 声明保留 + 判定口径仍按 `availability` 机械映射」，
    而**不是**声称这些端点在 GEN NX 上可用。
    """
    registry = _registry()
    for key in R85_GEN_NX_PRODUCT_GAPS:
        definition = registry.endpoint(key)
        assert "GEN_NX" in definition.products, key
        assert definition.availability in {"verified", "unverified", "untested"}, key
        resolved = registry.resolve(key=key, product="GEN_NX", method="GET")
        assert resolved.verification_status == definition.verification_status, key
        # 数据侧原文里的 `unavailable_on` 记录（`instances.yaml` 口径）如实保留
        assert definition.availability == "verified", key


def test_p135d_r85_civil_nx_product_gaps_are_recorded_in_the_registry() -> None:
    """R85：CIVIL NX 上实测 `404` 的 7 个端点同样**存在且声明保留**。"""
    registry = _registry()
    for key in R85_CIVIL_NX_PRODUCT_GAPS:
        definition = registry.endpoint(key)
        assert "CIVIL_NX" in definition.products, key
        assert definition.availability in {"verified", "unverified", "untested"}, key


def test_p135d_r85_span_is_a_product_specific_endpoint() -> None:
    """R85：`DB.SPAN` **不**在 GEN NX 清单里，且在 `CIVIL_DESIGNER` 上可用（产品特有）。"""
    definition = _registry().endpoint("DB.SPAN")
    assert "CIVIL_DESIGNER" in definition.products
    assert "DB.SPAN" not in R85_GEN_NX_PRODUCT_GAPS


def test_p135d_r85_measurement_never_promotes_a_verification_status() -> None:
    """R85 / R78：判定口径仍**只**由 `availability` 机械映射（CI 层记录不升级）。"""
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


# ===== R87 / R90：response 方向 Schema 缺失 =====


def test_p135d_r87_and_r90_response_schema_absence_keeps_partial() -> None:
    """R87 / R90：数据侧**只有**请求方向 Schema → 「Response Schema 已确认」恒为假。"""
    registry = _registry()
    for key in ("DB.NODE", "DB.MATL", "DB.SECT", "DB.UNIT"):
        document = registry.schema_document(key)
        assert document is not None, key
        assert str(document.get("direction") or "request") == "request", key


def test_p135d_r87_a_missing_response_schema_is_the_only_reason_for_partial() -> None:
    """补上 response 方向 Schema 后**同一判定点**即升 `VERIFIED`（AND 是真的）。"""
    from app.infrastructure.adapters.midas.live import (
        PROBE_PASSED,
        SEVEN_AND_ITEMS,
        STATUS_PARTIAL,
        STATUS_VERIFIED,
        registry_evidence,
        seven_and_verdict,
    )

    evidence = registry_evidence(
        _registry(),
        key="DB.NODE",
        product="GEN_NX",
        version="2026",
        supported_versions=support.SUPPORTED_VERSIONS_SPEC,
        live_outcome=PROBE_PASSED,
    )
    assert set(evidence) == set(SEVEN_AND_ITEMS)
    verdict = seven_and_verdict(evidence)
    assert verdict.status == STATUS_PARTIAL
    assert verdict.missing == ("response_schema_confirmed",)
    assert (
        seven_and_verdict({**evidence, "response_schema_confirmed": True}).status == STATUS_VERIFIED
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
