"""P140 —— R5 剩余补齐（4 个请求 Schema 从上游资料**机械生成**）。

权威来源
--------
- `docs/07` §16 **R5** / **§16.1**（P139 回填 + R5 剩余）。
- `docs/reports/P139_写路径L5覆盖推进_v1.0.md` §5.2（P139 的 R5 剩余结论，本批**更正**）。
- `docs/reports/P140_R5剩余补齐_v1.0.md`（本批证据）。

本文件的**可执行判定**
--------------------
1. **来源可复算**：4 个新 Schema 文件 == `registry/tools/sync_request_schemas.py` 的机械结果
   （逐字节），且逐条断言它取自哪里：
   - `POST.TABLE.WEIGHT_IRREGULARITY_X` / `POST.TABLE.CONCURRENT_JOINT_FORCE` → 手册 `json_schema`
     （`TABLE_TYPE.enum` **包含**该端点 token —— P139 只看 `table_types` 字段，漏了 schema 本体）；
   - `POST.TABLE.STORY_SHEAR_FORCE_COEFFICIENT` → 手册**同族条目**的规格表（字段逐条来自表格）；
   - `OPE.BMLD` → `MIDAS_API_开发文档_v1.0.md` 里**已给出的完整 JSON Schema**。
2. **`OPE.BMLD` 与 `DB.BMLD` 不是同一操作**（`title` 与方法集都不同）。
3. **不臆造**：`registry/schema/**` = **620**（原 616 + 4），仍无 Schema 的端点 = **16**（原 20）。
4. **不改判定**：4 个端点的 `verification_status` 仍只由 `availability` 机械映射。
5. **真实实测（门控）**：专用空项目上建最小模型 → 跑静态分析 → 查表判别 —— 伪 token 必须
   `400` 且带 `error creating utbl` 标记，被接受的 token 必须 `200` 且**不带**该标记；
   跑完模型**再次为空**（只碰自建 ID）。
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest

import midas_p119_p126_support as support
from app.infrastructure.adapters.midas.client import (
    MidasEnvironmentCredential,
    MidasHttpClient,
)
from app.infrastructure.adapters.midas.live import (
    LIVE_PROJECT_ENV,
    MIDAS_LIVE_ENV,
    dedicated_test_project_from_env,
    live_opt_in_from_env,
)
from app.infrastructure.adapters.midas.registry import (
    MidasRegistry,
    verification_status_for,
)
from app.infrastructure.registry.schema_registry import SchemaRegistry

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录（上游手册 / 开发文档 / 数据侧工具都在这里）。"""

TOOL_PATH = REPO_ROOT / "registry" / "tools" / "sync_request_schemas.py"
"""本批**唯一**的生成落点（只依赖标准库；`--check` 断言「已落盘 == 机械结果」）。"""

MANUAL_PATH = REPO_ROOT / "MIDAS_API_Online_Manual_数据_v1.0.json"
"""上游手册（`endpoints[].json_schema` / `specifications`）。"""

DEV_DOC_PATH = REPO_ROOT / "MIDAS_API_开发文档_v1.0.md"
"""开发文档（`/OPE/BMLD` 章节里有**完整** JSON Schema，来源《midas Civil NX - API 用户手册》）。"""

SCHEMA_ROOT = REPO_ROOT / "registry" / "schema"
"""`registry/schema/**`（P140 起 **616 → 620**；P141 再 → **625**）。"""

EXPECTED_SCHEMA_FILES = 625
"""本批之后的数据侧 Schema 文件数（P141 起 **625**）。"""

EXPECTED_WITHOUT_SCHEMA = 11
"""本批之后仍无 Schema 的端点数（P138b 的 20 − P140 的 4 − P141 的 5）。"""

CLOSED_KEYS = (
    "OPE.BMLD",
    "POST.TABLE.CONCURRENT_JOINT_FORCE",
    "POST.TABLE.STORY_SHEAR_FORCE_COEFFICIENT",
    "POST.TABLE.WEIGHT_IRREGULARITY_X",
)
"""本批补齐的 **4** 个端点（P138b 的两类：URI 不同 + 手册无 table_type）。"""

MANUAL_JSON_SCHEMA_KEYS = (
    "POST.TABLE.CONCURRENT_JOINT_FORCE",
    "POST.TABLE.WEIGHT_IRREGULARITY_X",
)
"""由手册 `json_schema`（`TABLE_TYPE.enum`）机械定位的两个端点。"""

SPEC_TABLE_KEY = "POST.TABLE.STORY_SHEAR_FORCE_COEFFICIENT"
"""由手册**同族条目**的规格表机械生成的端点。"""

DEV_DOC_KEY = "OPE.BMLD"
"""由开发文档里**已给出**的完整 JSON Schema 取用的端点。"""

TOKEN_MISMATCH_MARKER = "error creating utbl"
"""伪 token（未知表类型）的错误形态标记 —— 用于判别「token 被接受」与「token 被拒」。"""


# ===== 辅助 =====


def _registry() -> MidasRegistry:
    """数据侧 Registry（`registry/` 的唯一权威来源）。"""
    return support.registry()


def _tool() -> Any:
    """按路径装载 `registry/tools/sync_request_schemas.py`（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location("structai_sync_request_schemas", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manual_entries() -> list[dict[str, Any]]:
    """上游手册的端点条目（`json_schema` 是**字符串**）。"""
    payload = json.loads(MANUAL_PATH.read_text(encoding="utf-8"))
    return list(payload["endpoints"])


def _document(relative: str) -> dict[str, Any]:
    """读取一个 Schema 文件（相对 `registry/`）。"""
    return json.loads((REPO_ROOT / "registry" / relative).read_text(encoding="utf-8"))


def _schema_path(key: str) -> str:
    """该端点的数据侧 Schema 路径（`schema_ref.local` 的落点）。"""
    path = _registry().endpoint(key).schema_path
    assert path, f"{key}: 本批之后必须已有 Schema 文件"
    return path


def _dev_doc_json_schema() -> dict[str, Any]:
    """开发文档 `/OPE/BMLD` 章节里给出的 JSON Schema（原样解析）。"""
    text = DEV_DOC_PATH.read_text(encoding="utf-8", errors="ignore")
    start = text.find("| URI | `/OPE/BMLD` |")
    assert start >= 0, "开发文档里找不到 /OPE/BMLD 的条目"
    fence = text.find("#### 请求示例", start)
    assert fence >= 0
    block = text[fence : text.find("```", fence + 20)]
    raw = block[block.find("```json") + len("```json") :].strip()
    return json.loads(raw)


# ===== 1. 来源可复算（离线）=====


def test_p140_the_four_files_match_the_mechanical_result() -> None:
    """门槛：P140 的 4 个文件**逐字节**等于生成器的机械结果；`--check` 退出码 0。

    P141 起生成器覆盖 **9** 个端点（P140 的 4 个 + P141 的 5 个）—— 本用例只断言
    P140 的 **4** 个，P141 的 5 个由 `test_midas_request_schemas_p141.py` 断言
    （各批自证，**不**互相代替）。文件内容按工具的**装配口径**比较
    （`with_preserved_response()` 会透传由 `sync_response_schemas.py` 追加的 `response` 块）。
    """
    module = _tool()
    documents = module.build_documents(REPO_ROOT)
    selected = [item for item in documents if item[1]["key"] in CLOSED_KEYS]
    assert len(selected) == len(CLOSED_KEYS)
    for relative, document, _origin in selected:
        path = REPO_ROOT / "registry" / relative
        merged = module.with_preserved_response(path, document)
        text = json.dumps(merged, ensure_ascii=False, indent=2) + "\n"
        assert path.read_text(encoding="utf-8") == text, relative
    assert module.main(["--repo", str(REPO_ROOT), "--check"]) == 0


def test_p140_the_two_manual_json_schema_files_carry_the_table_type_enum() -> None:
    """门槛：这 2 个端点的 Schema **就是**手册 `json_schema`（含本端点 token）。"""
    registry = _registry()
    module = _tool()
    entries = _manual_entries()
    for key in MANUAL_JSON_SCHEMA_KEYS:
        token = str(registry.endpoint(key).table_type)
        matches = [
            entry
            for entry in entries
            if token in module.table_type_tokens(str(entry.get("json_schema") or ""))
        ]
        assert len(matches) == 1, f"{key}: 手册里带该 TABLE_TYPE.enum 的条目数 = {len(matches)}"
        document = _document(_schema_path(key))
        assert document["schema"] == json.loads(str(matches[0]["json_schema"]))
        assert document["source"] == "help_center"


def test_p140_the_spec_table_file_is_faithful_to_the_manual_rows() -> None:
    """门槛：字段名与类型**逐条**来自手册规格表；`TABLE_TYPE` 注明 token 来源（API 实测）。"""
    registry = _registry()
    token = str(registry.endpoint(SPEC_TABLE_KEY).table_type)
    entry = next(
        item
        for item in _manual_entries()
        if "Story Shear Force Coefficient" in str(item.get("title") or "")
    )
    # 手册该条目**没有** json_schema（只有规格表）—— 这正是它走 `manual_spec_table` 的原因
    assert not entry.get("json_schema")
    document = _document(_schema_path(SPEC_TABLE_KEY))
    assert document["source"] == "help_center_spec_table"
    argument = document["schema"]["properties"]["Argument"]
    spec_names = {
        str(row[2]).strip().strip('"')
        for row in entry["specifications"]
        if isinstance(row, list) and len(row) >= 6 and str(row[2]).startswith('"')
    }
    assert set(argument["properties"]) <= spec_names
    assert argument["required"] == ["TABLE_TYPE"]
    # 类型映射（规格表的 `String` / `Object` / `Array [String]` → 小写 JSON Schema 类型）
    assert argument["properties"]["TABLE_NAME"]["type"] == "string"
    assert argument["properties"]["UNIT"]["type"] == "object"
    assert argument["properties"]["COMPONENTS"]["type"] == "array"
    # token 的取值来源如实注明（手册记的是**兄弟** token `STORY_SHEAR_FOR_RS`）
    description = argument["properties"]["TABLE_TYPE"]["description"]
    assert token in description
    assert "API" in description and "STORY_SHEAR_FOR_RS" in description


def test_p140_the_dev_doc_schema_is_taken_verbatim() -> None:
    """门槛：`OPE.BMLD` 的 Schema **逐字**来自开发文档里已给出的 JSON Schema（来源可追溯）。"""
    document = _document(_schema_path(DEV_DOC_KEY))
    assert document["schema"] == _dev_doc_json_schema()
    assert document["source"] == "civil_nx_manual"
    assert document["schema"]["required"] == ["Argument"]
    assert set(document["schema"]["properties"]["Argument"]["required"]) == {
        "LOAD_CASE_COMB",
        "ELEMENT",
        "STRESS_TYPE",
    }


def test_p140_ope_bmld_is_not_the_same_operation_as_db_bmld() -> None:
    """门槛：两条路由**不是**同一操作（语义 / 方法集 / 来源都不同）——P139 的留缺据此结案。"""
    registry = _registry()
    ope = registry.endpoint(DEV_DOC_KEY)
    db = registry.endpoint("DB.BMLD")
    assert ope.uri == "/OPE/BMLD" and db.uri == "/DB/BMLD"
    assert ope.methods == ("POST",) and "GET" in db.methods
    assert ope.products == ("CIVIL_NX",) and "GEN_NX" in db.products
    assert ope.title == "Beam Detail Analysis", "开发文档的中文名 = 梁详细分析"
    assert db.title == "Beam Loads"
    # 手册里**没有** `ope/BMLD` 条目（只有 `db/BMLD`）→ 两者的 Schema 来自**不同**来源
    manual_uris = {str(entry.get("input_uri") or "") for entry in _manual_entries()}
    assert "ope/BMLD" not in manual_uris and "db/BMLD" in manual_uris
    assert (
        _document(_schema_path(DEV_DOC_KEY))["schema"]
        != _document(_schema_path("DB.BMLD"))["schema"]
    )


# ===== 2. 计数与判定（离线）=====


def test_p140_the_closure_adds_exactly_four_files_and_leaves_eleven_without() -> None:
    """门槛：`registry/schema/**` = **625**；仍无 Schema 的端点 = **11**（20 − 4 − 5，P141 起）。"""
    files = sorted(SCHEMA_ROOT.rglob("*.json"))
    assert len(files) == EXPECTED_SCHEMA_FILES
    registry = _registry()
    for key in CLOSED_KEYS:
        assert registry.schema_json(key) is not None, key
    manifest = json.loads((REPO_ROOT / "registry" / "manifest.json").read_text(encoding="utf-8"))
    without = sorted(entry["key"] for entry in manifest["endpoints"] if not entry.get("schema"))
    assert len(without) == EXPECTED_WITHOUT_SCHEMA
    assert not set(without) & set(CLOSED_KEYS)
    # 数据侧登记数与 manifest 的 `schema` 字段仍 **1:1**（P08 / P09 的不变量）
    report = SchemaRegistry.load(REPO_ROOT / "registry").report()
    assert report.files == EXPECTED_SCHEMA_FILES
    assert report.registered == EXPECTED_SCHEMA_FILES
    assert report.unresolvable == ()


def test_p140_the_closure_never_promotes_a_verification_status() -> None:
    """门槛：4 个端点的 `verification_status` 仍只由 `availability` 机械映射（判定口径未改）。"""
    registry = _registry()
    for key in CLOSED_KEYS:
        definition = registry.endpoint(key)
        assert definition.verification_status == verification_status_for(
            availability=definition.availability, enabled=definition.enabled
        ), key


# ===== 3. 真实实测（门控；含判别对照）=====

LIVE_MODEL: tuple[tuple[str, str, object], ...] = (
    ("STLD", "1", {"NAME": "D", "TYPE": "D", "DESC": "DeadLoads"}),
    (
        "MATL",
        "1",
        {
            "TYPE": "STEEL",
            "NAME": "DB_Steel",
            "HE_SPEC": 0,
            "HE_COND": 0,
            "PLMT": 0,
            "P_NAME": "",
            "bMASS_DENS": False,
            "DAMP_RAT": 0.02,
            "PARAM": [
                {
                    "P_TYPE": 1,
                    "STANDARD": "EN05(S)",
                    "CODE": "",
                    "DB": "S450",
                    "bELAST": False,
                    "ELAST": 210000000,
                }
            ],
        },
    ),
    (
        "SECT",
        "1",
        {
            "SECTTYPE": "DBUSER",
            "SECT_NAME": "LT_Const",
            "SECT_BEFORE": {
                "OFFSET_PT": "LT",
                "HORZ_OFFSET_OPT": 0,
                "VERT_OFFSET_OPT": 0,
                "USE_SHEAR_DEFORM": False,
                "USE_WARPING_EFFECT": False,
                "SHAPE": "SB",
                "DATATYPE": 2,
                "SECT_I": {"vSIZE": [1, 1]},
            },
        },
    ),
    ("NODE", "1", {"X": 0.0, "Y": 0.0, "Z": 0.0}),
    ("NODE", "2", {"X": 1.0, "Y": 0.0, "Z": 0.0}),
    ("ELEM", "1", {"TYPE": "BEAM", "MATL": 1, "SECT": 1, "NODE": [1, 2], "ANGLE": 0}),
    ("CONS", "1", {"ITEMS": [{"ID": 1, "GROUP_NAME": "", "CONSTRAINT": "1111000"}]}),
    (
        "BMLD",
        "1",
        {
            "ITEMS": [
                {
                    "ID": 1,
                    "LCNAME": "D",
                    "GROUP_NAME": "",
                    "CMD": "BEAM",
                    "TYPE": "UNILOAD",
                    "DIRECTION": "GZ",
                    "USE_PROJECTION": False,
                    "USE_ECCEN": False,
                    "D": [0, 1, 0, 0],
                    "P": [-50, -50, 0, 0],
                }
            ]
        },
    ),
)
"""最小模型（**只**用自建 ID；跑完**逆序**清理）。"""

SENTINELS = ("NODE", "ELEM", "MATL", "SECT")
"""空项目哨兵（与 `write_probe.EMPTINESS_GATE_KEYS` 同口径）。"""

LIVE_TOKENS = (
    "WEIGHT_IRREGULARITY_X",
    "STORY_SHEAR_FORCE_COEFFICIENT",
)
"""本批实测**判别成立**的 token（`POST /POST/TABLE` → `200`；伪 token → `400` 且带判别标记）。"""

LIVE_UNDISCRIMINATED = "CONCURRENT_JOINT_FORCE"
"""本批实测**未能判别**的 token：其必填体需要**移动荷载 / 后处理模式**的模型，本批最小模型下
它与伪 token 的错误**同形** → 以手册 `json_schema`（`TABLE_TYPE.enum = ["CONCURRENT_JOINT_FORCE"]`）
为准，API 侧**如实标注未判别**（**不**假装已判别）。"""


def _live_ready() -> bool:
    """真实实测的执行条件（`docs/04` §72 四要素 + 显式 opt-in）。"""
    if not live_opt_in_from_env(os.environ):
        return False
    if dedicated_test_project_from_env(os.environ) is None:
        return False
    return bool((os.environ.get("MIDAS_BASE_URL") or "").strip()) and bool(
        (os.environ.get("MIDAS_MAPI_KEY") or "").strip()
    )


def test_p140_the_live_probe_is_skipped_without_the_documented_declaration(
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
    reason="真实实测需 MIDAS_LIVE_L4=1 + MIDAS_LIVE_PROJECT + MIDAS_BASE_URL + MIDAS_MAPI_KEY",
)
async def test_p140_live_table_tokens_are_accepted_on_a_minimal_model() -> None:
    """真实实测：建最小模型 → `POST /DOC/ANAL` → 查表判别 → 逆序清理（只碰自建 ID）。

    判别口径（**不**看成功本身，只看**错误形态**）：伪 token（`STRUCTAI_NOT_A_TABLE_TYPE`）
    必须 `400` 且**带** `error creating utbl` 标记；被接受的 token 必须 `200` 且**不带**该标记。
    ⚠️ 不带 `EXPORT_PATH` → **不**落任何文件；前后各核对一次哨兵（模型必须为空）。
    """
    registry = _registry()
    credential = MidasEnvironmentCredential()
    client = MidasHttpClient(
        base_url=os.environ["MIDAS_BASE_URL"],
        credential_provider=credential,
        secret_ref="MIDAS_MAPI_KEY",
    )
    created: list[tuple[str, str]] = []
    try:
        # ① 前置：专用项目必须为空（只读）
        for code in SENTINELS:
            payload = await client.get(f"/DB/{code}")
            assert (payload.get(code) or {}) == {}, f"专用项目非空：/DB/{code}"
        # ② 建最小模型（只碰自建 ID）
        for endpoint, item_id, body in LIVE_MODEL:
            resolved = registry.resolve(key=f"DB.{endpoint}", product="GEN_NX", method="POST")
            request = client.build_request(
                resolved,
                operation="P140.LIVE.CREATE",
                body=body,
                wrapper="Assign",
                item_id=item_id,
                allow_unverified=True,
            )
            await client.send(request)
            created.append((endpoint, item_id))
        # ③ 跑静态分析（空体 = Perform Analysis）
        anal = registry.resolve(key="DOC.ANAL", product="GEN_NX", method="POST")
        await client.send(
            client.build_request(
                anal,
                operation="P140.LIVE.ANAL",
                wrapper="Argument",
                body={},
                allow_unverified=True,
            )
        )
        # ④ 查表判别（裸传输只为读**错误形态**；凭据只从运行环境取，**不**落任何输出）
        secret = await credential.get_secret("MIDAS_MAPI_KEY")
        async with httpx.AsyncClient(
            base_url=os.environ["MIDAS_BASE_URL"],
            headers={"MAPI-Key": secret, "Content-Type": "application/json"},
            timeout=120.0,
        ) as raw:
            control = await raw.post(
                "/POST/TABLE", json={"Argument": {"TABLE_TYPE": "STRUCTAI_NOT_A_TABLE_TYPE"}}
            )
            assert control.status_code == 400, control.status_code
            assert TOKEN_MISMATCH_MARKER in control.text, "对照组的错误形态变了 → 判别口径失效"
            for token in LIVE_TOKENS:
                response = await raw.post(
                    "/POST/TABLE",
                    json={"Argument": {"TABLE_TYPE": token, "LOAD_CASE_NAMES": ["D"]}},
                )
                assert response.status_code == 200, (token, response.status_code)
                assert TOKEN_MISMATCH_MARKER not in response.text, token
            undiscriminated = await raw.post(
                "/POST/TABLE",
                json={
                    "Argument": {
                        "TABLE_TYPE": LIVE_UNDISCRIMINATED,
                        "LOAD_CASE_NAMES": ["D"],
                        "ADDITIONAL": {
                            "SET_REACTION_PARAMS": {"NODE_KEY": 1, "COMPONENT": "111111"}
                        },
                    }
                },
            )
            assert undiscriminated.status_code == 400, undiscriminated.status_code
            assert TOKEN_MISMATCH_MARKER in undiscriminated.text, (
                "如实标注：与伪 token 同形 → 未判别"
            )
    finally:
        # ⑤ 逆序清理（只删自建 ID；`DELETE` 必带路径 key）
        for endpoint, item_id in reversed(created):
            try:
                resolved = registry.resolve(key=f"DB.{endpoint}", product="GEN_NX", method="DELETE")
                await client.send(
                    client.build_request(
                        resolved, operation="P140.LIVE.CLEANUP", item_ids=(item_id,)
                    )
                )
            except Exception:  # noqa: BLE001 - 清理不得掩盖原始结论
                pass
        for code in SENTINELS:
            payload = await client.get(f"/DB/{code}")
            assert (payload.get(code) or {}) == {}, f"清理后仍有残留：/DB/{code}"
        await client.close()
