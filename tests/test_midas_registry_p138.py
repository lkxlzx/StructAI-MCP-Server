"""P138 · 数据侧缺陷收口（R19 / R5）+ L5 空项目闸门与批量覆盖（R4 / R14）。

权威来源
--------
- `docs/07` §16 **R19**（`registry/schema/**` 的 5 个数据缺陷）· **R5**（20 个无 Schema 端点）·
  **R4 / R14**（写路径实测覆盖）· `docs/04` §8（`VERIFIED` 的 7 项 AND）·
  §71 / §72（L4 / L5 分层）。
- `registry/README.md` §2.1 / §2.2（请求 / 响应两个方向）· §8（生成与校验工具）。
- 上游手册源数据 `MIDAS_API_Online_Manual_数据_v1.0.json`（`endpoints[].json_schema`）·
  `MIDAS_API_开发文档_v1.0.md`（`...(전체 N개)` 占位串的**手册原文**）。

落地裁决（本文件的硬事实，不美化）
--------------------------------
1. **R19 收口在生成链**：新增 `registry/tools/fix_schema_defects.py`（只依赖标准库、默认预演、
   `--write` 写回、幂等）：`DB.MBTP` 的坏串**从上游手册重新生成**（补齐缺失的尾部闭合符 → 对象），
   22 处占位分支换成**合法**兜底分支（`oneOf` → `anyOf`，否则兜底分支会让已转录取值**匹配两次**），
   `type` 大小写归一 → **616/616 可装载**、`SchemaEngine.check_schema()` 失败 **4 → 0**。
2. **R5 按实测分类**（**不**臆造）：20 个无 Schema 端点分成 5 类，逐类给出**可执行**判据；
   **一个 Schema 文件都没有新增**。
3. **`request_schema_confirmed` 对无请求体端点「不适用」**（P138b 裁决）：`methods` 不含
   `POST` / `PUT` / `PATCH` ⇒ 没有请求体就没有请求 Schema 可确认 → 该项视为满足并由
   `live.not_applicable_items()` **如实报出**；**不**改任何 `verification_status`（仍只由
   `availability` 机械映射，`docs/07` §7.2 / §16 R78）。
4. **空项目闸门（P138c）**：`MidasLiveWriteProbe` 在发**任何**写请求前用只读 `GET` 核对
   `EMPTINESS_GATE_KEYS`；非空 ⇒ `STRUCTAI-3000 dedicated_test_project_not_empty` + **零**写请求；
   哨兵全不可读 ⇒ `dedicated_test_project_emptiness_unverified`（**不**盲写）。
5. **R4 / R14 共用一条可执行口径**：`live.write_path_coverage()`（分子 = `midas_api_verifications`
   的 L5 `PASSED` 去重 key ∩ 写路径端点；分母 = `live.write_path_keys()`），**旧数 11 / 369 与 379
   作废**（与任何可执行判定都对不上）。
6. **真实 L5 只在专用测试项目上执行**：缺声明 → `pytest.skip`（**不**失败、**不**伪造）；
   专用项目非空 → 闸门按设计拒绝（**零**写请求），用例同样 `skip` 并如实说明。
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

import midas_p119_p126_support as support
from app.application.execution.validation import SchemaEngine
from app.infrastructure.adapters.midas.client import (
    MidasEnvironmentCredential,
    MidasHttpClient,
)
from app.infrastructure.adapters.midas.live import (
    EMPTY_BLOCK_KEY,
    LIVE_PROJECT_ENV,
    MIDAS_LIVE_ENV,
    PROBE_PASSED,
    STATUS_PARTIAL,
    STATUS_VERIFIED,
    DedicatedTestProject,
    dedicated_test_project_from_env,
    has_request_body,
    live_opt_in_from_env,
    not_applicable_items,
    registry_evidence,
    seven_and_verdict,
    write_only_keys,
    write_path_coverage,
    write_path_keys,
)
from app.infrastructure.adapters.midas.registry import MidasRegistry
from app.infrastructure.adapters.midas.write_probe import (
    EMPTINESS_GATE_KEYS,
    WRITE_PROBE_FAILED,
    WRITE_PROBE_NO_PAYLOAD,
    WRITE_PROBE_NO_READBACK,
    WRITE_PROBE_PASSED,
    MidasLiveWriteProbe,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录（生成器 / 上游手册都在这里）。"""

SCHEMA_ROOT = REPO_ROOT / "registry" / "schema"
"""`registry/schema/**`（本批改动的**唯一**数据面）。"""

MANUAL_PATH = REPO_ROOT / "MIDAS_API_Online_Manual_数据_v1.0.json"
"""上游手册源数据（`endpoints[].json_schema` 是 `DB.MBTP` 坏串的出处）。"""

DOC_PATH = REPO_ROOT / "MIDAS_API_开发文档_v1.0.md"
"""`...(전체 N개)` 占位串的**手册原文**出处（22 处）。"""

FIX_TOOL_PATH = REPO_ROOT / "registry" / "tools" / "fix_schema_defects.py"
"""R19 收口的**唯一**实现落点（生成链归一工具）。"""

EXPECTED_SCHEMA_FILES = 616
"""`registry/schema/**` 文件数（P138a **未**新增 / 未删除文件）。"""

PLACEHOLDER_FILES = (
    "design/src/AIK-SRC2K/BC-TABLE.json",
    "design/src/AIK-SRC2K/CC-TABLE.json",
    "design/src/AIK-SRC2K/LLRF.json",
    "design/src/AIK-SRC2K/MATD.json",
    "design/src/AIK-SRC2K/MCRD.json",
    "design/src/AIK-SRC2K/MRBD.json",
    "design/src/AIK-SRC2K/TABLE/SRC.json",
)
"""含 `...(전체 N개)` 占位分支的 **7** 个文件（22 处占位，本批全部换成合法分支）。"""

PLACEHOLDER_TOTAL = 22
"""占位分支总数（= `MIDAS_API_开发文档_v1.0.md` 里 `...(전체 N개)` 的出现次数，逐条核对）。"""

FALLBACK_MARKER = "手册该表共"
"""合法兜底分支 `description` 的标记（**如实**说明手册该表共 N 项、未逐项转录）。"""

R5_ENDPOINTS = (
    "DB.LCOM",
    "DOC.CLOSEALL",
    "DOC.EXIT",
    "OPE.BMLD",
    "OPE.CPCREATE",
    "OPE.CPEXPORT",
    "OPE.CPUPDATEMODEL",
    "OPE.CPUPDATERESULT",
    "OPE.MEMB",
    "OPE.PROJECTSTATUS",
    "OPE.SECTPROP",
    "OPE.STOR",
    "OPE.STORPROP",
    "OPE.STORYPROP",
    "OPE.STORY_IRR_PARAM",
    "OPE.STORY_PARAM",
    "POST.TABLE.CONCURRENT_JOINT_FORCE",
    "POST.TABLE.STORY_SHEAR_FORCE_COEFFICIENT",
    "POST.TABLE.WEIGHT_IRREGULARITY_X",
    "VIEW.SELECT",
)
"""`docs/07` §16 R5：数据侧 **20** 个没有 JSON Schema 的端点。"""

WRITE_PATH_TOTAL = 609
"""写路径端点（`methods` 含 `POST` / `PUT` / `DELETE` / `PATCH`）= R4 / R14 的**分母**。"""

WRITE_ONLY_TOTAL = 368
"""其中**连 `GET` 都没有**的端点 —— 只读 L4 探针**完全**覆盖不到的那部分。"""


# ===== 辅助 =====


def _registry() -> MidasRegistry:
    """数据侧 Registry（`registry/` 的唯一权威来源）。"""
    return support.registry()


def _document(relative: str) -> dict[str, Any]:
    """读取一个数据侧 Schema 文件（相对 `registry/schema/`）。"""
    return json.loads((SCHEMA_ROOT / relative).read_text(encoding="utf-8"))


def _manifest_entries() -> list[dict[str, Any]]:
    """`registry/manifest.json` 的端点条目。"""
    document = json.loads((_registry().root / "manifest.json").read_text(encoding="utf-8"))
    return list(document["endpoints"])


def _manual_entries() -> list[dict[str, Any]]:
    """上游手册的端点条目（`json_schema` 是**字符串**）。"""
    payload = json.loads(MANUAL_PATH.read_text(encoding="utf-8"))
    return list(payload["endpoints"])


def _load_fix_tool() -> Any:
    """按路径装载 `registry/tools/fix_schema_defects.py`（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location("structai_fix_schema_defects", FIX_TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _walk(node: object, path: str = "") -> Any:
    """递归产出 `(路径, 值)`（确定性顺序）。"""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from _walk(item, f"{path}[{index}]")
    else:
        yield path, node


def _fallback_branches(schema: object) -> list[tuple[str, str]]:
    """找出所有合法兜底分支（`description` 带 `FALLBACK_MARKER`），返回 `(路径, 说明)`。"""
    found: list[tuple[str, str]] = []
    for path, value in _walk(schema):
        if path.endswith("/description") and isinstance(value, str) and FALLBACK_MARKER in value:
            found.append((path, value))
    return found


class _NxStub(httpx.MockTransport):
    """有状态 NX 假传输（**只**实现 `DB.NODE` 的 GET / POST / DELETE 路径 key）。"""

    def __init__(self, *, nodes: dict[str, Any] | None = None) -> None:
        self.nodes: dict[str, Any] = dict(nodes or {})
        self.calls: list[tuple[str, str]] = []
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/civil"):
            path = path[len("/civil") :]
        self.calls.append((request.method, path))
        if path == "/DB/NODE" and request.method == "GET":
            return httpx.Response(200, json={"NODE": dict(self.nodes)})
        if path == "/DB/NODE" and request.method == "POST":
            body = json.loads(request.content) if request.content else {}
            assign = dict((body or {}).get("Assign") or {})
            self.nodes.update({str(key): value for key, value in assign.items()})
            return httpx.Response(200, json={"Assign": assign})
        if request.method == "DELETE" and path.startswith("/DB/NODE/"):
            for key in path.rsplit("/", 1)[-1].split(","):
                self.nodes.pop(key, None)
            return httpx.Response(200, json={EMPTY_BLOCK_KEY: ""})
        return httpx.Response(404, json={"message": "not found"})

    @property
    def write_calls(self) -> list[tuple[str, str]]:
        """非只读调用（拒绝路径**必须**为空）。"""
        return [call for call in self.calls if call[0] != "GET"]


def _client(transport: httpx.AsyncBaseTransport) -> MidasHttpClient:
    """**离线**客户端（固定假 Base URL / 假 Key；**不**读运行环境）。"""
    return MidasHttpClient(
        base_url=support.BASE_URL,
        credential_provider=MidasEnvironmentCredential({"MIDAS_MAPI_KEY": support.SECRET}),
        secret_ref="MIDAS_MAPI_KEY",
        transport=transport,
    )


def _probe(
    transport: httpx.AsyncBaseTransport,
    *,
    product: str = "CIVIL_NX",
    only: tuple[str, ...] = ("DB.NODE",),
    limit: int = 0,
    project: DedicatedTestProject | None = None,
) -> MidasLiveWriteProbe:
    """构造写路径探针（缺省带专用测试项目声明 + **默认**空项目闸门）。"""
    return MidasLiveWriteProbe(
        _client(transport),
        _registry(),
        product=product,
        project=project or DedicatedTestProject(name="p138"),
        limit=limit,
        only=only,
    )


# ===== P138a：R19 数据侧缺陷收口（生成链）=====


def test_p138a_schema_registry_loads_all_616_and_check_schema_is_clean() -> None:
    """门槛：616 个文件 → **616** 个登记、**0** 个无法还原、`check_schema` **0** 失败。"""
    from app.infrastructure.registry.schema_registry import SchemaRegistry

    registry = SchemaRegistry.load(REPO_ROOT / "registry")
    report = registry.report()
    assert report is not None
    assert report.files == EXPECTED_SCHEMA_FILES
    assert report.registered == EXPECTED_SCHEMA_FILES
    assert report.unresolvable == ()

    engine = SchemaEngine(registry)
    failures: list[str] = []
    for schema_id in registry.registered_ids():
        try:
            engine.check_schema(schema_id)
        except Exception as error:  # noqa: BLE001 - 回归时这里就是失败证据
            failures.append(f"{schema_id}: {error}")
    assert failures == [], failures
    assert len(registry) == EXPECTED_SCHEMA_FILES


def test_p138a_mbpt_request_schema_is_rebuilt_from_the_upstream_bad_string() -> None:
    """`DB.MBTP`：产物里的坏串与上游**同一条**，已按上游重建为**对象**（`response` 块未动）。"""
    document = _document("products/gen_nx/db/MBTP.json")
    schema = document["schema"]
    assert isinstance(schema, dict), "P138a：`schema` 必须落成**对象**"

    upstream = [entry for entry in _manual_entries() if entry["input_uri"].lower() == "db/mbtp"]
    assert len(upstream) == 1
    bad = upstream[0]["json_schema"]
    assert isinstance(bad, str)
    with pytest.raises(ValueError):
        json.loads(bad)
    tool = _load_fix_tool()
    repaired = tool.repair_json_text(bad)
    assert repaired is not None and repaired.endswith("}")
    assert schema == json.loads(repaired), "产物 = 上游手册原文 + 补齐的闭合符（**不**手改产物）"
    # 响应方向（P136b 生成）**一行未改**
    assert document["response"]["direction"] == "response"
    assert document["response"]["source"] == "l4_measured_envelope"


def test_p138a_placeholder_branches_are_legal_and_never_invent_values() -> None:
    """22 处占位分支 → 合法兜底分支；已转录取值**逐个保留**；`oneOf` 已改 `anyOf`。"""
    doc_text = DOC_PATH.read_text(encoding="utf-8")
    total = 0
    for relative in PLACEHOLDER_FILES:
        document = _document(relative)
        text = json.dumps(document["schema"], ensure_ascii=False)
        assert "전체" not in text, f"{relative}: 仍有占位串"
        branches = _fallback_branches(document["schema"])
        assert branches, relative
        for _path, description in branches:
            # 兜底分支必须**如实**说明「手册该表共 N 项」，且 N 与手册原文一致
            number = description.split(FALLBACK_MARKER)[1].split("项")[0].strip()
            assert f"...(전체 {number}개)" in doc_text, (relative, number)
            assert "未逐项转录" in description
        total += len(branches)
    assert total == PLACEHOLDER_TOTAL, "22 处占位（与手册原文出现次数逐条一致）"
    # `oneOf` → `anyOf`（否则兜底分支会让已转录取值匹配两次 → 合法取值全被判非法）
    mcrd = json.dumps(_document("design/src/AIK-SRC2K/MCRD.json")["schema"], ensure_ascii=False)
    assert '"oneOf"' not in mcrd
    assert '"anyOf"' in mcrd
    # 已转录取值**没有被改动**（MATD 的已转录钢号仍在）
    matd = json.dumps(_document("design/src/AIK-SRC2K/MATD.json")["schema"], ensure_ascii=False)
    assert "SS450" in matd


def test_p138a_type_case_is_normalized_and_the_edmp_defect_is_gone() -> None:
    """`type` 大小写全库归一：无 `Number` / `String` / … 变体；`OPE.EDMP` 2 处已是小写。"""
    tool = _load_fix_tool()
    bad_names = set(tool.TYPE_CASE_MAP)
    offenders: list[str] = []
    for path in sorted(SCHEMA_ROOT.rglob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for item, value in _walk(document.get("schema")):
            if item.endswith("/type") and isinstance(value, str) and value in bad_names:
                offenders.append(f"{path.relative_to(SCHEMA_ROOT).as_posix()}:{item}={value}")
    assert offenders == []
    edmp = _document("products/gen_nx/ope/EDMP.json")["schema"]
    assert edmp["EDMP"]["properties"]["Argument"]["properties"]["PARAMETER"]["type"] == "number"
    assert edmp["EDMP"]["properties"]["Argument"]["properties"]["H_VS"]["type"] == "number"


def test_p138a_the_generation_chain_tool_is_idempotent_and_checks_invariants() -> None:
    """生成链归一**可复算**：连跑两次第二次差异 0；不变量自检为空。"""
    tool = _load_fix_tool()
    assert FIX_TOOL_PATH.exists()
    assert tool.check_invariants(REPO_ROOT / "registry") == []
    assert tool.main(["--repo", str(REPO_ROOT)]) == 0, "第二次预演必须报 0 处改动（幂等）"
    assert tool.main(["--repo", str(REPO_ROOT), "--check"]) == 0


def test_p138a_the_repair_is_deterministic_and_refuses_to_guess() -> None:
    """尾部闭合符修复**只**补结构；其余损坏一律 `None`（**不**猜内容）。"""
    tool = _load_fix_tool()
    assert tool.repair_json_text('{"a": {"b": 1}') == '{"a": {"b": 1}}'
    assert tool.repair_json_text('{"a": [1, 2') == '{"a": [1, 2]}'
    # 已闭合 / 结构交叉 / 字符串未闭合 → 一律拒绝
    assert tool.repair_json_text('{"a": 1}') is None
    assert tool.repair_json_text('{"a": }') is None
    assert tool.repair_json_text('{"a": "unterminated') is None
    assert tool.repair_json_text("}") is None
    # 占位串只认手册那一种形态
    assert tool.PLACEHOLDER_RE.match("...(전체 19개)")
    assert tool.PLACEHOLDER_RE.match("...(전체 68개)")
    assert not tool.PLACEHOLDER_RE.match("전체 19개")
    assert not tool.PLACEHOLDER_RE.match("...(전체 19)")


def test_p138a_the_two_existing_generators_report_no_diff() -> None:
    """两个既有生成器预演差异 **0**（数据侧改动**可复算**，`registry/README.md` §8）。"""
    for script, marker in (
        ("registry/tools/sync_manifest.py", "字段差异总数 = 0"),
        ("registry/tools/sync_response_schemas.py", "补 response Schema 的端点 = 0"),
    ):
        completed = subprocess.run(  # noqa: S603
            [sys.executable, script],
            cwd=REPO_ROOT,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert completed.returncode == 0, (script, completed.stderr[-400:])
        assert marker in completed.stdout, (script, completed.stdout[-400:])


# ===== P138b：R5 按实测分类收口 =====


def _r5_class(key: str, manual_uris: dict[str, list[str]], code_uris: dict[str, list[str]]) -> str:
    """按**实测**把无 Schema 端点归类（判据全部来自数据文件本身）。"""
    definition = _registry().endpoint(key)
    methods = {str(method).upper() for method in definition.methods}
    if not methods & {"POST", "PUT", "PATCH"}:
        return "no_request_body"
    if key.startswith("POST.TABLE."):
        return "post_table_key_without_manual_table_type"
    uri = definition.uri.lstrip("/").lower()
    if manual_uris.get(uri):
        return "manual_has_no_json_schema"
    if code_uris.get(key.split(".")[-1].lower()):
        return "uri_differs_in_manual"
    return "absent_from_nx_manual"


def test_p138b_the_twenty_missing_schemas_are_classified_by_measurement() -> None:
    """R5：20 个无 Schema 端点 → **5** 类，逐类条数**实测**（**不**沿用猜测分组）。"""
    manual_uris: dict[str, list[str]] = {}
    code_uris: dict[str, list[str]] = {}
    for entry in _manual_entries():
        uri = str(entry["input_uri"]).lower()
        manual_uris.setdefault(uri, []).append(str(entry["endpoint"]))
        code_uris.setdefault(uri.rsplit("/", 1)[-1], []).append(uri)
    manifest = {entry["key"]: entry for entry in _manifest_entries()}
    assert set(R5_ENDPOINTS) == {key for key, entry in manifest.items() if not entry.get("schema")}

    classes: dict[str, list[str]] = {
        "no_request_body": [],
        "manual_has_no_json_schema": [],
        "uri_differs_in_manual": [],
        "post_table_key_without_manual_table_type": [],
        "absent_from_nx_manual": [],
    }
    for key in R5_ENDPOINTS:
        classes[_r5_class(key, manual_uris, code_uris)].append(key)
    assert {name: len(keys) for name, keys in classes.items()} == {
        "no_request_body": 4,
        "manual_has_no_json_schema": 5,
        "uri_differs_in_manual": 1,
        "post_table_key_without_manual_table_type": 3,
        "absent_from_nx_manual": 7,
    }
    assert sum(len(keys) for keys in classes.values()) == 20
    # 与提示词里的猜测分组**不同**的两处，如实固定为实测结果：
    # ① `OPE.MEMB` / `OPE.STOR` / `OPE.STORPROP` / `OPE.STORY_*_PARAM` 的手册条目**就是同一 URI**，
    #    只是手册没有 `json_schema`（只有参数表）—— 不是「URI 不同」；
    # ② `POST.TABLE.*` 的 3 个端点：手册条目的 `table_types` 为空，无法机械确认同一操作。
    assert classes["uri_differs_in_manual"] == ["OPE.BMLD"]
    assert classes["manual_has_no_json_schema"] == [
        "OPE.MEMB",
        "OPE.STOR",
        "OPE.STORPROP",
        "OPE.STORY_IRR_PARAM",
        "OPE.STORY_PARAM",
    ]
    assert classes["no_request_body"] == [
        "DB.LCOM",
        "OPE.PROJECTSTATUS",
        "OPE.SECTPROP",
        "VIEW.SELECT",
    ]
    assert classes["absent_from_nx_manual"] == [
        "DOC.CLOSEALL",
        "DOC.EXIT",
        "OPE.CPCREATE",
        "OPE.CPEXPORT",
        "OPE.CPUPDATEMODEL",
        "OPE.CPUPDATERESULT",
        "OPE.STORYPROP",
    ]


def test_p138b_no_schema_was_invented_for_the_r5_endpoints() -> None:
    """R5 收口**不**臆造：Schema 文件仍 **616** 个，20 个端点仍无 Schema。"""
    assert len(sorted(SCHEMA_ROOT.rglob("*.json"))) == EXPECTED_SCHEMA_FILES
    manifest = {entry["key"]: entry for entry in _manifest_entries()}
    assert [key for key in R5_ENDPOINTS if manifest[key].get("schema")] == []
    assert all(_registry().schema_json(key) is None for key in R5_ENDPOINTS)


def test_p138b_request_schema_is_not_applicable_without_a_request_body() -> None:
    """P138b 裁决：无请求体 ⇒ `request_schema_confirmed` **不适用**（可执行判定）。"""
    registry = _registry()
    for key in ("OPE.PROJECTSTATUS", "OPE.SECTPROP", "VIEW.SELECT", "DB.LCOM"):
        assert has_request_body(registry, key) is False, key
        assert not_applicable_items(registry, key) == ("request_schema_confirmed",), key
        evidence = registry_evidence(
            registry,
            key=key,
            product=registry.endpoint(key).products[0],
            version="2026",
            supported_versions=support.SUPPORTED_VERSIONS_SPEC,
            live_outcome=PROBE_PASSED,
        )
        assert evidence["request_schema_confirmed"] is True, key
        assert evidence["response_schema_confirmed"] is False, key
    # 带请求体的端点（手册**没有**给 Schema）仍**如实**判假 —— 裁决只覆盖无请求体端点
    for key in ("OPE.STORY_PARAM", "OPE.STORY_IRR_PARAM", "OPE.MEMB", "OPE.STOR"):
        assert has_request_body(registry, key) is True, key
        assert not_applicable_items(registry, key) == (), key
        evidence = registry_evidence(
            registry,
            key=key,
            product=registry.endpoint(key).products[0],
            version="2026",
            supported_versions=support.SUPPORTED_VERSIONS_SPEC,
            live_outcome=PROBE_PASSED,
        )
        assert evidence["request_schema_confirmed"] is False, key


def test_p138b_the_na_adjudication_never_promotes_a_verification_status() -> None:
    """裁决**不**改判定口径：`verification_status` 仍只由 `availability` 机械映射。"""
    registry = _registry()
    mapping = {
        "verified": STATUS_VERIFIED,
        "unverified": "UNVERIFIED",
        "untested": "PARTIAL",
    }
    for key in R5_ENDPOINTS:
        definition = registry.endpoint(key)
        assert definition.verification_status == mapping[definition.availability], key
    # 无请求体的 3 个「已实测」端点仍是 `PARTIAL`（真实缺口 = 无 Schema 文件 → 无 `response` 块）
    for key in ("OPE.PROJECTSTATUS", "OPE.SECTPROP", "VIEW.SELECT"):
        verdict = seven_and_verdict(
            registry_evidence(
                registry,
                key=key,
                product="GEN_NX",
                version="2026",
                supported_versions=support.SUPPORTED_VERSIONS_SPEC,
                live_outcome=PROBE_PASSED,
            )
        )
        assert verdict.status == STATUS_PARTIAL, key
        assert verdict.missing == ("response_schema_confirmed",), key


# ===== P138c：L5 空项目闸门 + 批量覆盖 + R4 / R14 重算 =====


def test_p138c_the_default_gate_uses_the_documented_sentinels() -> None:
    """闸门默认哨兵 = 4 个只读端点，且都在数据侧存在（有 `GET` + `read_root`）。"""
    assert EMPTINESS_GATE_KEYS == ("DB.NODE", "DB.ELEM", "DB.MATL", "DB.SECT")
    registry = _registry()
    for key in EMPTINESS_GATE_KEYS:
        definition = registry.endpoint(key)
        assert "GET" in definition.methods, key
        assert definition.read_root, key


async def test_p138c_a_non_empty_project_is_refused_with_zero_write_requests() -> None:
    """非空项目 → `STRUCTAI-3000 dedicated_test_project_not_empty` + **零**写请求。"""
    transport = _NxStub(nodes={"1": {"X": 0.0, "Y": 0.0, "Z": 0.0}})
    probe = _probe(transport)
    with pytest.raises(Exception) as failure:
        await probe.probe()
    assert getattr(failure.value, "code", "") == "STRUCTAI-3000"
    assert failure.value.details["reason"] == "dedicated_test_project_not_empty"
    assert failure.value.details["endpoint"] == "DB.NODE"
    assert failure.value.details["existing"] == 1
    assert transport.write_calls == [], "拒绝路径**零**写请求（只有只读 GET）"
    assert transport.calls and all(method == "GET" for method, _path in transport.calls)


async def test_p138c_an_empty_project_passes_the_gate_and_the_three_step_chain_runs() -> None:
    """空项目 → 闸门放行；三步链只碰自建编号（`list → create → read_back → delete`）。"""
    transport = _NxStub()
    report = await _probe(transport).probe()
    assert report.keys() == ("DB.NODE",)
    outcome = report.outcomes[0]
    assert outcome.is_passed is True, outcome
    assert outcome.created_id == "1"
    assert outcome.read_back is True and outcome.deleted is True
    assert transport.nodes == {}, "清理后项目**再次为空**"
    # 闸门的只读 GET 全部在**任何**写请求之前（哨兵不可读的会被跳过，故只断言「先只读」）
    methods = [method for method, _path in transport.calls]
    first_write = next(index for index, method in enumerate(methods) if method != "GET")
    assert all(method == "GET" for method in methods[:first_write]), methods
    assert methods[first_write:] == ["POST", "GET", "DELETE"]


async def test_p138c_an_unreadable_sentinel_set_is_refused_instead_of_writing_blind() -> None:
    """哨兵全不可读 → `dedicated_test_project_emptiness_unverified` + **零**写请求。"""

    class _AllMissing(httpx.MockTransport):
        """一切请求都 `404` 的假传输（模拟「哨兵读不到」）。"""

        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []
            super().__init__(self._handle)

        def _handle(self, request: httpx.Request) -> httpx.Response:
            self.calls.append((request.method, request.url.path))
            return httpx.Response(404, json={"message": "not found"})

    transport = _AllMissing()
    probe = _probe(transport)
    with pytest.raises(Exception) as failure:
        await probe.probe()
    assert getattr(failure.value, "code", "") == "STRUCTAI-3000"
    assert failure.value.details["reason"] == "dedicated_test_project_emptiness_unverified"
    assert [method for method, _path in transport.calls] == ["GET"] * len(transport.calls)


async def test_p138c_a_batch_run_records_one_four_state_outcome_per_candidate() -> None:
    """批量跑 `candidate_keys()`（小 `limit`）：逐条记录四态，不隐藏任何一条。"""
    transport = _NxStub()
    probe = _probe(transport, only=(), limit=2)
    candidates = probe.candidate_keys()
    assert len(candidates) == 2
    report = await probe.probe()
    assert report.keys() == candidates
    states = {
        WRITE_PROBE_PASSED,
        WRITE_PROBE_FAILED,
        WRITE_PROBE_NO_PAYLOAD,
        WRITE_PROBE_NO_READBACK,
    }
    assert all(outcome.outcome in states for outcome in report.outcomes)
    assert set(report.counts()) == states
    assert sum(report.counts().values()) == 2


def test_p138c_r4_and_r14_share_one_executable_criterion() -> None:
    """R4 / R14 用**同一条**可执行口径重算：分母 609（其中只写 368），分子 = L5 `PASSED` 去重。"""
    registry = _registry()
    write_keys = write_path_keys(registry)
    assert len(write_keys) == WRITE_PATH_TOTAL
    assert len(write_only_keys(registry)) == WRITE_ONLY_TOTAL

    class _Row:
        """最小验证记录（只提供判定需要的三个字段）。"""

        def __init__(self, key: str, level: str, status: str) -> None:
            self.endpoint_key = key
            self.contract_level = level
            self.status = status

    assert write_path_coverage(registry, []).ratio == f"0 / {WRITE_PATH_TOTAL}"
    rows = [
        _Row("DB.NODE", "L5", PROBE_PASSED),
        _Row("DB.NODE", "L5", PROBE_PASSED),  # 重复行只算一次
        _Row("DB.ELEM", "L5", WRITE_PROBE_FAILED),
        _Row("DB.MATL", "L4", PROBE_PASSED),  # L4 行**不**计入 L5 覆盖
        _Row("DB.SECT", "L5", PROBE_PASSED),
    ]
    coverage = write_path_coverage(registry, rows)
    assert coverage.covered == 2
    assert coverage.covered_keys == ("DB.NODE", "DB.SECT")
    assert coverage.total == WRITE_PATH_TOTAL
    assert coverage.write_only == WRITE_ONLY_TOTAL
    assert coverage.ratio == f"2 / {WRITE_PATH_TOTAL}"
    assert coverage.as_dict()["covered_keys"] == ["DB.NODE", "DB.SECT"]
    # 旧记录（R4 = 11 / 369、R14 = 379）与任何可执行判定都对不上 → **作废**，不沿用
    assert 369 != coverage.total and 379 != coverage.total


def _live_ready() -> bool:
    """真实 L5 的执行条件（`docs/04` §72 四要素 + 显式 opt-in）。"""
    if not live_opt_in_from_env(os.environ):
        return False
    if dedicated_test_project_from_env(os.environ) is None:
        return False
    return bool((os.environ.get("MIDAS_BASE_URL") or "").strip()) and bool(
        (os.environ.get("MIDAS_MAPI_KEY") or "").strip()
    )


def test_p138c_the_live_batch_is_skipped_without_the_documented_declaration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缺声明 → 用例 `skip`（判定只依赖环境声明，**不**回落当前项目、**不**伪造）。"""
    for name in (MIDAS_LIVE_ENV, LIVE_PROJECT_ENV, "MIDAS_BASE_URL", "MIDAS_MAPI_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert live_opt_in_from_env(os.environ) is False
    assert dedicated_test_project_from_env(os.environ) is None
    assert _live_ready() is False


@pytest.mark.skipif(
    not _live_ready(),
    reason="真实 L5 需 MIDAS_LIVE_L4=1 + MIDAS_LIVE_PROJECT + MIDAS_BASE_URL + MIDAS_MAPI_KEY",
)
async def test_p138c_live_batch_records_l5_rows_and_the_recounted_coverage(
    tmp_path: Path,
) -> None:
    """真实 L5 批量（小 `limit`）：空项目闸门 → 逐条四态 → 落 L5 行 → 重算 R4 / R14 覆盖。"""
    from sqlalchemy import select as sql_select

    from app.infrastructure.adapters.midas.models import MidasApiVerificationORM
    from app.infrastructure.database.base import utcnow

    engine = support.engine_for(tmp_path)
    await support.midas_tables(engine)
    factory = support.session_factory_for(engine)
    client = MidasHttpClient(
        base_url=os.environ["MIDAS_BASE_URL"],
        credential_provider=MidasEnvironmentCredential(),
        secret_ref="MIDAS_MAPI_KEY",
    )
    registry = _registry()
    probe = MidasLiveWriteProbe(
        client,
        registry,
        product="GEN_NX",
        project=dedicated_test_project_from_env(os.environ),
        # `0` = 跑**全部**可探候选（GEN NX 上 = **10** 个）；可用 `MIDAS_LIVE_WRITE_LIMIT`
        # 先给小值谨慎试跑（P138c 实测先跑了 `limit=3`：3 个候选全部 400 `software_api_error`、
        # **零**残留，清理核对通过）。
        limit=int(os.environ.get("MIDAS_LIVE_WRITE_LIMIT") or 0),
    )
    try:
        report = await probe.probe()
    except Exception as error:  # noqa: BLE001 - 闸门按设计拒绝时**不**算失败
        reason = getattr(error, "details", {}).get("reason", "")
        if reason in {
            "dedicated_test_project_not_empty",
            "dedicated_test_project_emptiness_unverified",
        }:
            pytest.skip(f"专用空项目闸门按设计拒绝（**零**写请求）：{reason}")
        raise
    assert report.keys(), "批量覆盖必须至少跑一个候选端点"
    async with factory() as session:
        for outcome in report.outcomes:
            session.add(
                MidasApiVerificationORM(
                    endpoint_key=outcome.key,
                    contract_level="L5",
                    product="GEN_NX",
                    version_range="2025-2026",
                    method=outcome.method,
                    path=outcome.path,
                    status=outcome.outcome,
                    schema_hash="",
                    detail=outcome.detail,
                    verified_at=utcnow(),
                )
            )
        await session.commit()
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    sql_select(MidasApiVerificationORM).where(
                        MidasApiVerificationORM.contract_level == "L5"
                    )
                )
            )
            .scalars()
            .all()
        )
    await engine.dispose()
    assert len(rows) == len(report.keys())
    coverage = write_path_coverage(registry, rows)
    assert coverage.total == len(write_path_keys(registry))
    assert coverage.covered == len(report.passed())
    assert coverage.ratio.startswith(f"{coverage.covered} / ")


def test_p138c_candidates_are_the_probeable_set_only() -> None:
    """候选集**只**含「Transformer **已注册**」的端点（否则 `limit` 白占、覆盖永远为 0）。

    P138c 的**真实批量实测**暴露：`candidate_keys()` 原先只校验「Transformer 名可派生」，
    于是 `DB.ACTL` / `DB.ACTL-M1` / `DB.BCCT` 这些**未注册** Transformer 的端点占满了前 3 个
    名额 → 三条全记 `NO_PAYLOAD_TEMPLATE`、**零**写请求、覆盖率仍 `0 / 609`。
    """
    from app.infrastructure.adapters.midas.transforms import TRANSFORMER_REGISTRY
    from app.infrastructure.adapters.midas.write_probe import transformer_name_for

    probe = _probe(_NxStub(), only=(), limit=0, product="CIVIL_NX")
    keys = probe.candidate_keys()
    assert keys, "候选集不得为空（否则批量覆盖无意义）"
    for key in keys:
        assert TRANSFORMER_REGISTRY.get(transformer_name_for(key)) is not None, key
    # `-M1`（`HYPER_S` 专属）没有已注册的 Transformer → 不入候选
    assert all("-M1" not in key for key in keys)
    # 已实现三步链的端点**必须**在候选集里（否则真实批量永远跑不出 PASSED）
    assert "DB.NODE" in keys
