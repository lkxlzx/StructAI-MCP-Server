"""P171 / **R164**（B 组）：`OPE.LCOM-SRC` 的**落库**验证。

P169 只证到「**取值档位**」（`Set_DefaultLoadComb failed` = 取值**通过**了规范校验）
----------------------------------------------------------------------------
P169 的 C 组判据 = **同形性**（三档），跑完 `GET /DB/LCOM-SRC` 仍是**空块**
⇒ 收口依据**只到档位**，**不是**「组合**真的**建出来了」。

本批（**用户已授权**一次**写路径**测量）把它推到**效果**这一层
----------------------------------------------------------
在**全新**自建模型上补齐**规范要求的前置对象** ⇒ `POST /OPE/LCOM-SRC` **`200`** ∧
`GET /DB/LCOM-SRC` **22 行**（基线 **0**）⇒ **真的落库**。

⚠️ **本批同时更正 P169 的一条「恢复条件」**：P169 写「本模型无该规范所需的**荷载条件**」
—— **不准确**。实测缺的是**反应谱 + 施工阶段**，由原生文案**逐步点名**：

1. 最小模型（无反应谱）⇒ 文案点名 `stage gate`（门控）；
2. 加**手册完整示例体**（带 `RS_SCALE_FACTOR`）⇒ 文案换成
   `spectrum load case not found: RX(RS)` ⇒ **形状是对的**（原生**读到了**该字段
   并去查前置对象）⇒ 缺**反应谱工况**；
3. 加反应谱 `db/SPFC` + 工况 `db/SPLC`（`RX`/`RY`）⇒ 文案**退回** `stage gate`
   ⇒ 反应谱那一步**已满足**；
4. 加结构组 `db/GRUP` + 施工阶段 `db/STAG` ⇒ **`200`** ∧ **22 行** ⇒ **真的落库**。

本文件钉住的判据
----------------
1. **落库判据（铁律 ⓪）**：证据里 `created` 非空（行数 **>** 基线），且**不是**靠状态码；
2. **前置对象**：模型里**真的**建了 `db/SPFC` / `db/SPLC` / `db/GRUP` / `db/STAG`；
3. **零残留**：新建的 **22** 个编号**全部**删除，`after_cleanup.count == 0`，哨兵 **7** 项一致；
4. **阴性对照**：伪码被**核心闸门**拦下（**零请求**）∧ 行数**不变**；
5. **收口未回退**：生成器 `--check` 通过；
6. **`app/**` 一行未改**；凭据**不入**证据。
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
"""仓库根目录。"""

TOOLS = REPO_ROOT / "registry" / "tools"
LIVE = REPO_ROOT / "registry" / "live"

PROBE_TOOL = TOOLS / "probe_lcom_src_persistence_p171.py"
GENERATOR_TOOL = TOOLS / "sync_lcom_src_dgncode_enum.py"
EVIDENCE = LIVE / "lcom_src_persistence_probe.json"
AUDIT = LIVE / "spec_enum_audit.json"
YAML = REPO_ROOT / "registry" / "products" / "gen_nx" / "ope" / "LCOM-SRC.yaml"

EXPECTED_ROWS = 22
"""实测落库的**组合数**（`GET /DB/LCOM-SRC` 基线 0 ⇒ 22 行）。"""

FAKE_CODE = "NONSENSE-CODE"

PREREQUISITE_URIS = ("/db/spfc", "/db/splc", "/db/grup", "/db/stag")
"""规范要求的前置对象（**本批实测缺的就是这 4 个**）。"""


def _load(path: pathlib.Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ===== 1. 落库判据（铁律 ⓪）=====


def test_p171_b_the_write_really_persists() -> None:
    """门槛（**真的落库**）：`POST /OPE/LCOM-SRC` ⇒ `GET /DB/LCOM-SRC` 行数 **>** 基线。"""
    document = _json(EVIDENCE)
    assert document["verdict"] == "PASSED", document["verdict"]
    assert document["baseline"]["count"] == 0, document["baseline"]
    assert len(document["created"]) == EXPECTED_ROWS, document["created"]
    # ⚠️ **落库**的判据是 `created` 非空（**效果**）—— 阳性那一次的**状态码**是 `200`，
    #    但**状态码本身不判别任何东西**（P169 的教训：原生对**任何** `PARTS` 取值都回 `200`）。
    assert document["declared_row"]["status"] == 200, document["declared_row"]
    assert document["declared_row"]["auth_error"] is False


def test_p171_b_the_verdict_is_not_a_status_code() -> None:
    """门槛（**判据是行为**）：判定**不**依赖状态码 —— 最小模型下**同样**是 `400`。"""
    document = _json(EVIDENCE)
    note = document["note"]
    assert "效果" in note and "状态码" in note
    # 阴性对照那一次是 `400`，而阳性那一次是 `200` ⇒ 状态码**确实**在两次间变化，
    # 但**判据**是「行数 > 基线」（`created`）。
    assert document["fake_row"]["status"] == 400, document["fake_row"]


# ===== 2. 前置对象（本批更正 P169 的「需要什么」）=====


def test_p171_b_the_prerequisites_are_the_rs_and_stage_objects() -> None:
    """门槛（**更正 P169**）：缺的是**反应谱 + 施工阶段**，**不是**「荷载条件」。"""
    document = _json(EVIDENCE)
    model_uris = [step["uri"] for step in document["model"]]
    for uri in PREREQUISITE_URIS:
        assert uri in model_uris, f"前置对象 {uri} 必须在模型里（本批实测缺的就是它）"
    for step in document["model"]:
        assert step["ok"], step
    prerequisites = document["prerequisites"]
    assert prerequisites["rs_function"] == "RS_func"
    assert tuple(prerequisites["rs_cases"]) == ("RX", "RY")
    assert prerequisites["stage_name"] == "CS01"
    assert prerequisites["stage_group"] == "SG_01"


def test_p171_b_the_native_message_names_the_prerequisites() -> None:
    """门槛（**原生文案点名**）：`spectrum load case not found` 与 `stage gate` 都留了痕。"""
    document = _json(EVIDENCE)
    note = document["prerequisites"]["note"]
    assert "spectrum load case not found: RX(RS)" in note, note
    assert "stage gate" in note, note


# ===== 3. 零残留 =====


def test_p171_b_the_probe_leaves_no_residue() -> None:
    """门槛（**零残留**）：**22** 个新建编号**全部**删除 · 回查为空 · 哨兵一致。"""
    document = _json(EVIDENCE)
    assert set(document["created"]) <= set(document["removed"]), "新建的组合未全部删除"
    assert document["after_cleanup"]["count"] == 0, document["after_cleanup"]
    sentinel = document["sentinel"]
    assert sentinel["unchanged"] is True, sentinel
    assert len(sentinel["keys"]) == 7
    for key in sentinel["keys"]:
        assert sentinel["before"][key] == sentinel["after"][key], key


# ===== 4. 阴性对照 =====


def test_p171_b_the_fake_code_is_blocked_with_zero_requests() -> None:
    """门槛（**R140 未放松**）：伪码被**核心闸门**拦下（**零请求**）∧ 行数**不变**。"""
    document = _json(EVIDENCE)
    assert document["fake_gate"]["raised"] is True, document["fake_gate"]
    assert FAKE_CODE in document["fake_gate"]["problems"][0]
    # ⚠️ 对照基线 = **阳性写入之后**的行数（不是建模之后）—— 否则阳性成功时会**误判**。
    assert document["fake_row"]["band"] == "value_rejected", document["fake_row"]


def test_p171_b_the_guard_blocks_the_fake_code_offline() -> None:
    """门槛（**离线复算**）：核心闸门对伪码**抛**、对合法码**放行**（**零请求**）。"""
    tool = _load(PROBE_TOOL, "probe_lcom_src_persistence_p171_guard")
    assert tool.guard_allows(REPO_ROOT, FAKE_CODE)["raised"] is True
    assert tool.guard_allows(REPO_ROOT, tool.DECLARED_CODE)["raised"] is False
    assert tool.guard_allows(REPO_ROOT, tool.EXAMPLE_CODE)["raised"] is False


# ===== 5. 收口未回退 =====


def test_p171_b_the_closure_has_not_regressed() -> None:
    """门槛（**只增不减**）：生成器 `--check` 通过（收口不可回退）。"""
    tool = _load(GENERATOR_TOOL, "sync_lcom_src_dgncode_enum_p171b")
    assert tool.is_applied(REPO_ROOT), "生成器 --check 不过 ⇒ 收口回退"
    document = _json(EVIDENCE)
    assert document["generator"]["applied"] is True
    assert set(document["generator"]["on_disk"]) == {"AIK-SRC2K", "KDS 41 SRC : 2022"}


def test_p171_b_the_offline_check_is_green() -> None:
    """门槛（**离线自洽**）：`--check` 零请求通过。"""
    tool = _load(PROBE_TOOL, "probe_lcom_src_persistence_p171_check")
    assert tool.main(["--check"]) == 0


def test_p171_b_the_disposition_is_r164() -> None:
    """门槛（**台账**）：`OPE.LCOM-SRC::DGNCODE` 已收口 · 裁决号 **R164** · 写明落库依据。"""
    dispositions = {item["key"]: item for item in _json(AUDIT)["dispositions"]}
    item = dispositions["OPE.LCOM-SRC::DGNCODE"]
    assert item["status"] == "closed", item
    assert item["ruling"] == "R164", item
    assert "落库" in item["reason"], item["reason"]
    assert "22 行" in item["reason"], item["reason"]
    assert item.get("generator_agrees") is True, item


def test_p171_b_the_endpoint_yaml_records_the_persistence() -> None:
    """门槛（**结论入端点 YAML**）：头部注释写明 **R164** 的落库裁决 + 更正。"""
    text = YAML.read_text(encoding="utf-8")
    assert "R164" in text
    assert "落库" in text
    assert "22" in text
    assert "stage gate" in text, "必须写明实测点名的那条门控"
    assert "db/SPFC" in text and "db/STAG" in text


# ===== 6. 红线 =====


def test_p171_b_no_credential_leaks_into_the_evidence() -> None:
    """门槛（**绝不记录 secret**）：证据里**没有**凭据字段。"""
    text = EVIDENCE.read_text(encoding="utf-8")
    for marker in ("MAPI-Key", "MIDAS_MAPI_KEY", "Authorization", "localhost"):
        assert marker not in text, f"证据含 {marker}"


def test_p171_b_the_probe_is_offline_safe_by_default() -> None:
    """门槛（**零请求默认**）：不带 `--probe` 时**不**发请求（预演模式）。"""
    text = PROBE_TOOL.read_text(encoding="utf-8")
    assert '"--probe", action="store_true"' in text
    assert "if not args.probe:" in text
    assert "guard_native_crash_path" in text, "必须在**发请求之前**自检崩溃族（R154）"


def test_p171_b_the_probe_never_touches_the_crash_family() -> None:
    """门槛（**R154**）：写路径**不**在 `NATIVE_CRASH_ENDPOINTS` 里。"""
    sys.path.insert(0, str(REPO_ROOT))
    from app.infrastructure.adapters.midas.client import NATIVE_CRASH_ENDPOINTS  # noqa: PLC0415

    tool = _load(PROBE_TOOL, "probe_lcom_src_persistence_p171_crash")
    assert tool.WRITE_PATH.lstrip("/").replace("/", ".") not in set(NATIVE_CRASH_ENDPOINTS)
    assert not any("ANAL" in str(item) and "LCOM" in str(item) for item in NATIVE_CRASH_ENDPOINTS)
