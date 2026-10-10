"""P139 —— 写路径 L5 覆盖推进（R4 / R14 的分子）+ R5 剩余裁决 + 状态码保真度。

权威来源
--------
- `docs/07` §16 **R4 / R14**（写路径实测覆盖：分母恒为 **633** —— P149-A 起，只读 `OPTIONS` 实测
  修正方法集后由 609 上修；分子只统计真实 L5 `PASSED`）。
- `docs/07` §16 **R5 / R87**（20 个无 Schema 端点；7 项 AND 的判定点）。
- `docs/reports/P138_数据侧缺陷收口与L5空项目闸门_v1.0.md` §4.3 / §8（P138c 实测：10 个候选里
  `DB.NODE` `PASSED`、其余 **9** 个 `400 software_api_error`）。
  P139 本批实测：**10 / 10** `PASSED`、写路径覆盖 **10 / 609**（见 `docs/reports/P139_*.md`）。

本文件的**可执行判定**（不含任何真实请求）
------------------------------------------
1. **模板来源可复算**：`registry/live/write_templates.json` 的每一条 body 都必须等于
   「上游手册示例 + 本文件声明的 `adjustments`」（由 `registry/tools/check_write_templates.py`
   复算），且逐条通过**数据侧请求 Schema**（按声明方言）校验。
2. **模板不硬编码进 Core**：模板的取值**只**出现在 `registry/**`，`app/**` 里 0 处。
3. **前置链只碰自建编号**：按顺序创建、目标删除后**逆序**删除；前置失败 → 目标如实 `FAILED`
   且**零**目标写请求。
4. **状态码保真**：`status_code` 来自响应（`2xx` 原样回传），不再是常量 `200`。
5. **R5 裁决 B**（无请求体 ⇒ 不建文件）：`OPE.PROJECTSTATUS` / `OPE.SECTPROP` / `VIEW.SELECT`
   的**唯一**缺口是 `response_schema_confirmed` → 如实保持 `PARTIAL`（写明依据与恢复条件）。
6. **R5 剩余如实留缺**：`POST.TABLE.*` × 3 与 `OPE.BMLD` 的缺口**逐条**由数据侧事实支撑。
"""

from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from jsonschema.validators import validator_for

import midas_p119_p126_support as support
from app.infrastructure.adapters.midas.client import (
    MidasEnvironmentCredential,
    MidasHttpClient,
)
from app.infrastructure.adapters.midas.errors import MidasConnectionError
from app.infrastructure.adapters.midas.live import (
    PROBE_PASSED,
    STATUS_PARTIAL,
    DedicatedTestProject,
    has_request_body,
    not_applicable_items,
    registry_evidence,
    seven_and_verdict,
)
from app.infrastructure.adapters.midas.registry import MidasRegistry, verification_status_for
from app.infrastructure.adapters.midas.write_probe import (
    EMPTINESS_GATE_KEYS,
    PAYLOAD_SOURCE_SCHEMA_DERIVED,
    WRITE_PROBE_FAILED,
    WRITE_PROBE_PASSED,
    MidasLiveWriteProbe,
    derive_body,
)
from app.infrastructure.adapters.midas.write_templates import (
    WritePayloadTemplate,
    WritePrerequisite,
    parse_write_templates,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录（上游手册 / 数据侧工具都在这里）。"""

TEMPLATES_PATH = REPO_ROOT / "registry" / "live" / "write_templates.json"
"""P139 的**唯一**模板来源（数据侧；见模块文档第 1 条）。"""

MANUAL_PATH = REPO_ROOT / "MIDAS_API_Online_Manual_数据_v1.0.json"
"""上游手册源数据（模板来源的**复算**依据）。"""

CHECK_TOOL_PATH = REPO_ROOT / "registry" / "tools" / "check_write_templates.py"
"""模板复算工具（只依赖标准库；见 `registry/README.md` §8）。"""

SCHEMA_ROOT = REPO_ROOT / "registry" / "schema"
"""`registry/schema/**`（R5 裁决 B：**不**为无请求体端点新增文件）。"""
EXPECTED_SCHEMA_FILES = 625
"""Schema 文件数（P141 起 **625**；R5 裁决 B 本身仍**不**为无请求体端点新增文件）。"""

TEMPLATE_KEYS = (
    "DB.BMLD",
    "DB.BODF",
    "DB.CCFC",
    "DB.CNLD",
    "DB.CONS",
    "DB.CUTL",
    "DB.DCON",
    "DB.DCTL",
    "DB.DSTL",
    "DB.EFCT",
    "DB.EIGV",
    "DB.ELEM",
    "DB.EPMT",
    "DB.ETFC",
    "DB.EXLD",
    "DB.FBLD",
    "DB.FIMP",
    "DB.GSTP",
    "DB.HHCT",
    "DB.HSFC",
    "DB.IEHC",
    "DB.LDGR",
    "DB.LDSQ",
    "DB.LENG",
    "DB.MATL",
    "DB.MBTP",
    "DB.MLFC",
    "DB.MVCD",
    "DB.MVCTBS",
    "DB.MVCTCH",
    "DB.MVCTID",
    "DB.MVCTTR",
    "DB.MVHLTR",
    "DB.NMAS",
    "DB.PDEL",
    "DB.PJCF",
    "DB.PNLD",
    "DB.POGD",
    "DB.POSL",
    "DB.POSP",
    "DB.PRES",
    "DB.SDHY",
    "DB.SDIS",
    "DB.SDST",
    "DB.SDVE",
    "DB.SDVI",
    "DB.SECT",
    "DB.SMCT",
    "DB.SPFC",
    "DB.STLD",
    "DB.STOR",
    "DB.TDGR",
    "DB.TDME",
    "DB.TDMT",
    "DB.TDNT",
    "DB.THFC",
    "DB.THIK",
)
"""P139 9 + P142 1 + P144 7 + P145 11 + P146 7 + P147 10 + P148 12 = **57** 个模板。"""

PROBED_KEYS = (
    "DB.BMLD",
    "DB.BODF",
    "DB.CCFC",
    "DB.CNLD",
    "DB.CONS",
    "DB.CUTL",
    "DB.DCON",
    "DB.DCTL",
    "DB.DSTL",
    "DB.EFCT",
    "DB.EIGV",
    "DB.ELEM",
    "DB.EPMT",
    "DB.ETFC",
    "DB.EXLD",
    "DB.FBLD",
    "DB.FIMP",
    "DB.GSTP",
    "DB.HHCT",
    "DB.HSFC",
    "DB.IEHC",
    "DB.LDGR",
    "DB.LDSQ",
    "DB.LENG",
    "DB.MATL",
    "DB.MBTP",
    "DB.MLFC",
    "DB.MVCD",
    "DB.MVCTBS",
    "DB.MVCTCH",
    "DB.MVCTID",
    "DB.MVCTTR",
    "DB.MVHLTR",
    "DB.NMAS",
    "DB.NODE",
    "DB.PDEL",
    "DB.PJCF",
    "DB.PNLD",
    "DB.POGD",
    "DB.POSL",
    "DB.POSP",
    "DB.PRES",
    "DB.SDHY",
    "DB.SDIS",
    "DB.SDST",
    "DB.SDVE",
    "DB.SDVI",
    "DB.SECT",
    "DB.SMCT",
    "DB.SPFC",
    "DB.STLD",
    "DB.STOR",
    "DB.TDGR",
    "DB.TDME",
    "DB.TDMT",
    "DB.TDNT",
    "DB.THFC",
    "DB.THIK",
)
"""GEN NX 上的 **58** 个可探候选（P148 起；`DB.NODE` 走机械派生的 body）。"""

EXPECTED_BODIES = 101
"""复算的 body 总数（P148 起 **101** = 57 个目标 + 44 个前置对象）。"""
R5_NO_REQUEST_BODY = ("OPE.PROJECTSTATUS", "VIEW.SELECT")
"""`methods` 不含 `POST` / `PUT` / `PATCH` 的端点（R5 裁决 B 的对象）。

**P149-A 更正**：`OPE.SECTPROP` 的 `POST` 由只读 `OPTIONS` 实测（`Allow` 头 = 路由真实方法集）
确认 ⇒ 它**有**请求体 ⇒ 裁决 B 的适用范围收窄为真正无请求体的**两个**端点。"""

R5_POST_TABLE = (
    "POST.TABLE.CONCURRENT_JOINT_FORCE",
    "POST.TABLE.STORY_SHEAR_FORCE_COEFFICIENT",
    "POST.TABLE.WEIGHT_IRREGULARITY_X",
)
"""`table_types` 为空 ⇒ 无法机械确认同一操作（R5 剩余，如实留缺）。"""

CORE_FORBIDDEN_LITERALS = (
    "DB_Steel",
    "LT_Const",
    "EN05(S)",
    "S450",
    "Element_Type1",
    "Floor_example",
    "UNILOAD",
    "DeadLoads",
    "1111000",
    "vSIZE",
)
"""模板里的**特征取值**（`app/**` 里出现即等于把模板硬编码进 Core）。"""


# ===== 辅助 =====


def _registry() -> MidasRegistry:
    """数据侧 Registry（`registry/` 的唯一权威来源）。"""
    return support.registry()


def _document() -> dict[str, Any]:
    """数据侧模板文件原文。"""
    return json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))


def _manual_entries() -> list[dict[str, Any]]:
    """上游手册的端点条目（`json_schema` 是字符串）。"""
    payload = json.loads(MANUAL_PATH.read_text(encoding="utf-8"))
    return list(payload["endpoints"])


def _check_tool() -> Any:
    """按路径装载 `registry/tools/check_write_templates.py`（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location("structai_check_write_templates", CHECK_TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _client(transport: httpx.AsyncBaseTransport) -> MidasHttpClient:
    """**离线**客户端（固定假 Base URL / 假 Key；**不**读运行环境）。"""
    return MidasHttpClient(
        base_url=support.BASE_URL,
        credential_provider=MidasEnvironmentCredential({"MIDAS_MAPI_KEY": support.SECRET}),
        secret_ref="MIDAS_MAPI_KEY",
        transport=transport,
    )


def _bare(code: str) -> str:
    """`DB.NODE` → `NODE`（假传输按原生 code 建索引，与真实 URI 一致）。"""
    return str(code).split(".")[-1]


_BASE_PATH = "/civil"
"""`support.BASE_URL` 的路径段（假传输据此剥离前缀，与 P138 的 `_NxStub` 同口径）。"""


class _NxStore(httpx.MockTransport):
    """通用 NX 假传输：对 `/DB/<CODE>` 实现 `GET` / `POST` / `DELETE <path key>`。

    读回按数据侧解包链（`{<read_root>: {...}}`）如实回放 —— 与真实实例同形。
    """

    def __init__(
        self,
        *,
        codes: tuple[str, ...],
        fail_post: tuple[str, ...] = (),
        post_status: int = 200,
        initial: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.rows: dict[str, dict[str, Any]] = {_bare(code): {} for code in codes}
        for code, values in (initial or {}).items():
            self.rows.setdefault(_bare(code), {}).update(values)
        self.calls: list[tuple[str, str, Any]] = []
        self._fail_post = {_bare(item) for item in fail_post}
        self._post_status = int(post_status)
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith(_BASE_PATH):
            path = path[len(_BASE_PATH) :]
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, path, body))
        parts = [part for part in path.split("/") if part]
        if len(parts) < 2:
            return httpx.Response(404, json={"message": "not found"})
        code = _bare(parts[1])
        if request.method == "GET" and len(parts) == 2 and code in self.rows:
            return httpx.Response(200, json={code: dict(self.rows[code])})
        if request.method == "POST" and len(parts) == 2 and code in self.rows:
            if code in self._fail_post:
                return httpx.Response(400, json={"error": {"message": "rejected"}})
            assign = dict((body or {}).get("Assign") or {})
            self.rows[code].update({str(key): value for key, value in assign.items()})
            return httpx.Response(self._post_status, json={"Assign": assign})
        if request.method == "DELETE" and len(parts) == 3 and code in self.rows:
            for item in parts[2].split(","):
                self.rows[code].pop(item, None)
            return httpx.Response(200, json={"message": ""})
        return httpx.Response(404, json={"message": "not found"})

    def write_calls(self) -> list[tuple[str, str, Any]]:
        """非只读调用（按发生顺序）。"""
        return [call for call in self.calls if call[0] != "GET"]

    def paths(self) -> list[str]:
        """全部调用的路径（按发生顺序）。"""
        return [path for _method, path, _body in self.calls]


def _probe(
    transport: httpx.AsyncBaseTransport,
    *,
    templates: dict[str, WritePayloadTemplate] | None = None,
    only: tuple[str, ...] = ("DB.NODE",),
    product: str = "GEN_NX",
) -> MidasLiveWriteProbe:
    """构造写路径探针（缺省带专用测试项目声明 + **默认**空项目闸门）。"""
    return MidasLiveWriteProbe(
        _client(transport),
        _registry(),
        product=product,
        project=DedicatedTestProject(name="p139"),
        limit=0,
        only=only,
        templates=templates,
    )


# ===== 1. 数据侧：模板来源可复算 =====


def test_p139_the_data_side_declares_templates_for_the_probed_endpoints() -> None:
    """门槛：模板**恰好**覆盖 P139 实测 `400` 的 9 个端点 + 本批新增的 `DB.FBLD`。"""
    assert TEMPLATES_PATH.is_file(), "模板必须落在数据侧（**不**进 Core）"
    document = _document()
    assert tuple(sorted(document["templates"])) == TEMPLATE_KEYS
    registry = _registry()
    for key in TEMPLATE_KEYS:
        assert registry.has(key), key
        template = registry.write_template(key)
        assert template is not None, key
        assert template.body is not None, key
        assert template.source in {
            "manual_example",
            "manual_example_adjusted",
            "explicit_injection",
        }, key
        assert template.origin, f"{key}: 来源定位串不能为空（模板必须可追溯）"
    # `DB.NODE` 的机械派生 body 已被 P138c 实测接受 → **不**加模板（回落路径保持可用）
    assert registry.write_template("DB.NODE") is None
    assert registry.write_templates().as_dict()["count"] == len(TEMPLATE_KEYS)


def test_p139_every_body_is_recomputable_from_the_upstream_manual() -> None:
    """门槛：34 条 body 全部等于「上游手册示例 + 声明的 adjustments」（逐条复算）。"""
    module = _check_tool()
    errors, _notes, counts = module.check(REPO_ROOT)
    assert errors == [], "\n".join(errors)
    assert counts["templates"] == len(TEMPLATE_KEYS)
    assert counts["bodies"] == EXPECTED_BODIES
    assert counts["manual_example"] == EXPECTED_BODIES
    assert counts["unverifiable"] == 0


def test_p139_every_body_validates_against_the_data_side_request_schema() -> None:
    """门槛：34 条 body 逐条通过**数据侧请求 Schema**（按各自声明的方言）。"""
    registry = _registry()
    document = _document()
    checked = 0
    for key, template in sorted(document["templates"].items()):
        pairs = [(key, template)] + [
            (item["key"], item) for item in template.get("prerequisites", [])
        ]
        for owner, entry in pairs:
            schema = registry.effective_schema(owner)
            assert schema is not None, f"{owner}: 模板必须对应有 Schema 的端点"
            validator = validator_for(schema)(schema)
            errors = sorted(validator.iter_errors(entry["body"]), key=lambda item: list(item.path))
            assert not errors, f"{owner}: {[error.message for error in errors]}"
            checked += 1
    assert checked == EXPECTED_BODIES


def test_p139_the_checker_refuses_a_drifted_body_and_a_missing_example() -> None:
    """负向对照：body 与手册不一致 / 示例不存在 → 复算工具**必须**报错（不是恒真）。"""
    module = _check_tool()
    examples = module.manual_examples(REPO_ROOT)
    schema = module.request_schema(REPO_ROOT, "schema/common/db/STLD.json")
    counts = {"bodies": 0, "manual_example": 0, "unverifiable": 0}
    notes: list[str] = []
    drifted = {
        "source": {
            "kind": "manual_example",
            "uri": "db/STLD",
            "example": "Static Load Cases",
            "example_id": "1",
        },
        "adjustments": [],
        "body": {"NAME": "DL", "TYPE": "L", "DESC": "DeadLoads"},
    }
    errors = module._check_body("DB.STLD", drifted, schema, examples, counts, notes, indent="")
    assert errors and "不一致" in errors[0]
    missing = dict(drifted)
    missing["source"] = dict(drifted["source"], example="No Such Example")
    errors = module._check_body("DB.STLD", missing, schema, examples, counts, notes, indent="")
    assert errors and "找不到" in errors[0]
    # 原样照抄的种类**不得**带 adjustments（否则等于手工改写）
    touched = dict(drifted, adjustments=[{"path": "NAME", "from": "DL", "to": "D"}])
    errors = module._check_body("DB.STLD", touched, schema, examples, counts, notes, indent="")
    assert any("不得带 adjustments" in error for error in errors)


def test_p139_the_loader_refuses_malformed_templates() -> None:
    """结构缺陷（缺 body / 来源缺失 / 未知来源种类）→ **明确**错误，不静默忽略。"""
    with pytest.raises(MidasConnectionError) as failure:
        parse_write_templates({"templates": {"DB.NODE": {"source": {"kind": "manual_example"}}}})
    assert failure.value.details["defect"] == "template_body_missing"
    with pytest.raises(MidasConnectionError) as failure:
        parse_write_templates({"templates": {"DB.NODE": {"body": {}, "source": {"kind": "magic"}}}})
    assert "template_source_kind_unknown" in failure.value.details["defect"]
    with pytest.raises(MidasConnectionError) as failure:
        parse_write_templates({"endpoints": {}})
    assert failure.value.details["defect"] == "templates_missing"
    with pytest.raises(MidasConnectionError) as failure:
        parse_write_templates({"templates": {"DB.NODE": {"body": {}, "source": {}}}})
    assert failure.value.details["defect"] == "template_source_missing"
    # ⚠️ 空映射**不**算缺陷：文件在、但**一条模板都没有** → 空集合（探针回落 `derive_body`）
    assert len(parse_write_templates({"templates": {}})) == 0


def test_p139_no_template_payload_is_hardcoded_in_core() -> None:
    """门槛：模板取值**只**在 `registry/**`；`app/**` 里 0 处（Core 不硬编码模板）。"""
    hits: list[str] = []
    for path in sorted((REPO_ROOT / "app").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for literal in CORE_FORBIDDEN_LITERALS:
            if literal in text:
                hits.append(f"{path.relative_to(REPO_ROOT)}: {literal}")
    assert hits == [], hits
    assert TEMPLATES_PATH.is_relative_to(REPO_ROOT / "registry")


# ===== 2. 探针：模板 + 前置链 + 状态码保真 =====


async def test_p139_a_declared_template_is_sent_and_its_chain_runs_in_order() -> None:
    """门槛：模板 body 取代机械派生值；前置**先建**、目标后建、清理**逆序**。"""
    transport = _NxStore(codes=("DB.NODE", "DB.STLD"))
    template = WritePayloadTemplate(
        key="DB.NODE",
        body={"X": 9.0, "Y": 9.0, "Z": 9.0},
        source="explicit_injection",
        origin="unit-test",
        prerequisites=(
            WritePrerequisite(
                key="DB.STLD",
                item_id="7",
                body={"NAME": "L", "TYPE": "L", "DESC": "DeadLoads"},
                source="explicit_injection",
                origin="unit-test",
            ),
        ),
    )
    report = await _probe(transport, templates={"DB.NODE": template}).probe()
    outcome = report.outcomes[0]
    assert outcome.outcome == WRITE_PROBE_PASSED, outcome
    assert outcome.payload_source == "explicit_injection"
    # ⚠️ P141 / R96：模板里的 `item_id = "7"` 只是**来源定位**；探针把编号**重新分配**成
    # 「该端点既有编号的 max + 1」（此处 `DB.STLD` 为空 → 1），因此标签是 #1 而不是 #7。
    assert outcome.prerequisites == ("DB.STLD#1",)
    assert outcome.status_code == 200
    assert outcome.created_id == "1"
    assert outcome.read_back is True and outcome.deleted is True
    # 顺序：只读闸门（4 个哨兵）→ 目标 list → **前置端点既有编号**（R96 的 max+1 依据）
    # → **前置创建** → 目标创建 → 读回 → 目标删除 → 前置删除
    assert transport.paths() == [
        "/DB/NODE",
        "/DB/ELEM",
        "/DB/MATL",
        "/DB/SECT",
        "/DB/NODE",
        "/DB/STLD",
        "/DB/STLD",
        "/DB/NODE",
        "/DB/NODE",
        "/DB/NODE/1",
        "/DB/STLD/1",
    ]
    posted = [
        body for method, path, body in transport.calls if method == "POST" and path == "/DB/NODE"
    ]
    assert posted == [{"Assign": {"1": {"X": 9.0, "Y": 9.0, "Z": 9.0}}}]
    assert transport.rows["STLD"] == {}
    assert transport.rows["NODE"] == {}


async def test_p139_a_failing_prerequisite_marks_the_target_failed_with_zero_target_writes() -> (
    None
):
    """门槛：前置创建失败 → 目标如实 `FAILED`（`detail` 带前置与原因），**零**目标写请求。"""
    transport = _NxStore(codes=("DB.NODE", "DB.STLD"), fail_post=("DB.STLD",))
    template = WritePayloadTemplate(
        key="DB.NODE",
        body={"X": 0.0, "Y": 0.0, "Z": 0.0},
        source="explicit_injection",
        prerequisites=(
            WritePrerequisite(key="DB.STLD", item_id="7", body={"NAME": "L"}, source="unit-test"),
        ),
    )
    report = await _probe(transport, templates={"DB.NODE": template}).probe()
    outcome = report.outcomes[0]
    assert outcome.outcome == WRITE_PROBE_FAILED, outcome
    assert outcome.detail == "prerequisite_failed:DB.STLD#1:software_api_error"
    assert outcome.status_code == 400
    assert outcome.created_id == "" and outcome.read_back is False and outcome.deleted is False
    assert [path for _method, path, _body in transport.write_calls()] == ["/DB/STLD"]
    assert report.failures() == (outcome,)


async def test_p139_status_code_comes_from_the_response_not_a_constant() -> None:
    """门槛：`status_code` 来自**响应**（`201` 原样回传；`400` 由异常归类给出）。"""
    transport = _NxStore(codes=("DB.NODE",), post_status=201)
    report = await _probe(transport).probe()
    assert report.outcomes[0].outcome == WRITE_PROBE_PASSED
    assert report.outcomes[0].status_code == 201, "常量 200 会掩盖原生状态码（P135 的保真度缺口）"

    rejecting = _NxStore(codes=("DB.NODE",), fail_post=("DB.NODE",))
    failed = (await _probe(rejecting).probe()).outcomes[0]
    assert failed.outcome == WRITE_PROBE_FAILED
    assert failed.status_code == 400
    assert failed.detail == "software_api_error"


async def test_p139_without_a_template_the_derived_body_is_still_used() -> None:
    """门槛：无模板 → 仍走 `derive_body()`（来源如实标注），**不**因缺模板而失败。"""
    transport = _NxStore(codes=("DB.NODE",))
    report = await _probe(transport, templates={}).probe()
    outcome = report.outcomes[0]
    assert outcome.outcome == WRITE_PROBE_PASSED, outcome
    assert outcome.payload_source == PAYLOAD_SOURCE_SCHEMA_DERIVED
    assert outcome.prerequisites == ()
    derived = derive_body(_registry().effective_schema("DB.NODE"))
    posted = [
        body for method, path, body in transport.calls if method == "POST" and path == "/DB/NODE"
    ]
    assert posted == [{"Assign": {"1": derived}}]


async def test_p139_injection_overrides_the_data_side_template() -> None:
    """门槛：显式注入优先于数据侧模板（离线用例可控，生产路径仍读数据侧）。"""
    registry = _registry()
    data_side = registry.write_template("DB.BMLD")
    assert data_side is not None and data_side.prerequisites
    transport = _NxStore(codes=("DB.BMLD", *EMPTINESS_GATE_KEYS))
    injected = WritePayloadTemplate(
        key="DB.BMLD",
        body={"ITEMS": [{"ID": 1, "LCNAME": "D", "GROUP_NAME": "", "CMD": "BEAM"}]},
        source="explicit_injection",
        origin="unit-test",
    )
    report = await _probe(transport, templates={"DB.BMLD": injected}, only=("DB.BMLD",)).probe()
    outcome = report.outcomes[0]
    assert outcome.outcome == WRITE_PROBE_PASSED, outcome
    assert outcome.prerequisites == (), "注入的模板没有前置链 → **不**得偷偷用数据侧的前置"
    posted = [
        body for method, path, body in transport.calls if method == "POST" and path == "/DB/BMLD"
    ]
    assert posted == [{"Assign": {"1": injected.body}}]


def test_p139_templates_cannot_promote_a_verification_status() -> None:
    """门槛：`verification_status` 只由 `availability` 机械映射 —— 模板**没有**入口。"""
    parameters = set(inspect.signature(verification_status_for).parameters)
    assert parameters == {"availability", "enabled"}
    document = _document()
    for key, template in document["templates"].items():
        for field in ("availability", "verification_status", "products", "verified_on"):
            assert field not in template, f"{key}: 模板不得声明 {field}（判定口径与模板无关）"
    registry = _registry()
    for key in TEMPLATE_KEYS:
        definition = registry.endpoint(key)
        assert definition.verification_status == verification_status_for(
            availability=definition.availability, enabled=definition.enabled
        ), key


# ===== 3. R5 裁决 B + R5 剩余如实留缺 =====


def test_p139_r5_decision_b_no_response_only_schema_file() -> None:
    """R5 裁决 **B**：无请求体 ⇒ **不**建 Schema 文件，如实保持 7 项 AND 的 `PARTIAL`。

    依据（全部可执行）：① 这些端点确实没有请求体（`methods` 不含 `POST` / `PUT` / `PATCH`）；
    ② `registry/schema/**` 的文件数**不变**（**不**新增「只带 response 块」的文件）；
    ③ 唯一缺口 = `response_schema_confirmed`（`request_schema_confirmed` 按 P138b 裁决「不适用」）；
    ④ `verification_status` 仍只由 `availability` 机械映射（`docs/07` §16 R78：与 7 项 AND **不是**
    同一件事 —— 前者是数据侧可得性，后者是完整确认度）。

    **P149-A 更正**：`OPE.SECTPROP` 的 `POST` 由只读 `OPTIONS` 实测（`Allow` 头 = 路由真实方法集）
    确认 ⇒ 它**有**请求体 ⇒ **不**再适用裁决 B（本表由 3 个收窄为 **2** 个）；它现在**同时**缺
    请求与响应 Schema（见 `tests/test_midas_registry_p138.py`）。

    恢复条件（**不**在本批实现）：若将来数据侧允许「无请求体端点的 response-only Schema 文件」，
    则须同步 P08 / P09 的「文件数 ↔ manifest 1:1」断言与 `registry/README.md` §2.1 / §3，
    届时这 **2** 个端点的第 4 项才会由假转真。
    """
    registry = _registry()
    assert len(list(SCHEMA_ROOT.rglob("*.json"))) == EXPECTED_SCHEMA_FILES
    for key in R5_NO_REQUEST_BODY:
        definition = registry.endpoint(key)
        assert has_request_body(registry, key) is False, key
        assert "POST" not in definition.methods, key
        assert registry.schema_document(key) is None, key
        assert registry.response_schema_document(key) is None, key
        assert not_applicable_items(registry, key) == ("request_schema_confirmed",), key
        evidence = registry_evidence(
            registry,
            key=key,
            product=definition.products[0],
            version="2025",
            supported_versions=("2025",),
            live_outcome=PROBE_PASSED,
        )
        assert evidence["request_schema_confirmed"] is True, key
        assert evidence["response_schema_confirmed"] is False, key
        verdict = seven_and_verdict(evidence)
        assert verdict.status == STATUS_PARTIAL, key
        assert verdict.missing == ("response_schema_confirmed",), key
        assert definition.verification_status == verification_status_for(
            availability=definition.availability, enabled=definition.enabled
        ), key
    # `DB.LCOM` **不**在这 2 个里：它连实测解包链都没有 → 连 response 块都无从生成
    assert has_request_body(registry, "DB.LCOM") is False
    assert not registry.endpoint("DB.LCOM").read_root
    assert registry.response_schema_document("DB.LCOM") is None


def _post_table_entry(title_fragment: str) -> dict[str, Any]:
    """上游手册里标题含该片段的 `post/table` 条目（**唯一**来源，取不到即断言失败）。"""
    matches = [
        entry
        for entry in _manual_entries()
        if str(entry.get("input_uri") or "").lower().startswith("post/table")
        and title_fragment.lower() in str(entry.get("title") or "").lower()
    ]
    assert len(matches) == 1, f"{title_fragment}: 手册条目数 = {len(matches)}"
    return matches[0]


def test_p139_r5_remaining_gaps_are_backed_by_data_side_facts() -> None:
    """R5 剩余：`POST.TABLE.*` × 3 与 `OPE.BMLD` 的缺口**逐条**有数据侧依据（**不**臆造）。"""
    registry = _registry()
    manual = _manual_entries()
    post_table = [
        entry
        for entry in manual
        if str(entry.get("input_uri") or "").lower().startswith("post/table")
    ]
    declared = {str(item) for entry in post_table for item in (entry.get("table_types") or [])}
    for key in R5_POST_TABLE:
        table_type = str(registry.endpoint(key).table_type)
        assert table_type, key
        assert table_type not in declared, f"{key}: 手册已声明该 TABLE_TYPE → 应改为机械映射"
    # 依据（逐条）：近名条目**要么**没有 `table_types` 链接、**要么**声明的是别的 token
    weight = _post_table_entry("Weight Irregularity Check")
    assert weight["table_types"] == [] and weight.get("json_schema"), "有 schema 但**没有**链接"
    concurrent = _post_table_entry("Concurrent Joint Force")
    assert concurrent["table_types"] == [] and concurrent.get("json_schema")
    shear = _post_table_entry("Story Shear Force Coefficient")
    assert "STORY_SHEAR_FOR_RS" in (shear.get("table_types") or []), "手册记的是兄弟 token"
    assert not shear.get("json_schema")

    # `OPE.BMLD`：手册**没有** `ope/BMLD` 条目；数据侧也没有 Schema 文件 / 解包链
    manual_uris = {str(entry.get("input_uri") or "") for entry in manual}
    assert "ope/BMLD" not in manual_uris
    assert "db/BMLD" in manual_uris
    ope = registry.endpoint("OPE.BMLD")
    db = registry.endpoint("DB.BMLD")
    assert ope.uri == "/OPE/BMLD" and ope.methods == ("POST",)
    assert db.uri == "/DB/BMLD" and "GET" in db.methods
    assert not ope.read_root, "`/OPE/BMLD` 仍无实测解包链（P140 只补了**请求** Schema）"
    # ⚠️ 实测（P139，gen-local，**只读** `GET`，零副作用）：`/OPE/BMLD` → `405`（只允许 `POST`）、
    # `/DB/BMLD` → `200` ⇒ 方法集不同 ⇒ **不是**同一操作（P140 起其 Schema 另有来源）。
    # 该实测**不**在 CI 里复跑（需真实实例），证据见 `P139_…md` §5 与 `P140_…md` §3。
    assert ope.products == ("CIVIL_NX",), "云实例**不**调用：本批只在 GEN NX 上做只读复核"
    # P140：这 4 条 R5 缺口已由 `registry/tools/sync_request_schemas.py` **机械补齐** →
    # `schema_document` 不再为 `None`（P139 时记的是 `None`；本行由 P140 逐条更新，**不**放宽）。
    assert registry.schema_document("OPE.BMLD") is not None
