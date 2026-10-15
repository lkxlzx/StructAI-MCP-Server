"""P169 / **R162**：P168 留缺 9 项的**逐条推进**（真机裁决 + 产品侧澄清）。

本批的四组（`docs/07` §15.5 的 P169 入口）
----------------------------------------
* **A** `PARTS` 的「**声明 vs 示例**」冲突（**6** 个端点）：
  **3** 个**可判别** ⇒ 收口 · **3** 个**不可判别** ⇒ 如实留缺。
* **B** `POST.TEXT` 的 `TABLE_TYPE`（**来源太窄**）：**键名裁决** ⇒ 契约键是 `TEXT_TYPE`
  ⇒ 键重命名 + 枚举收口。
* **C** `OPE.LCOM-SRC` / `OPE.LCOM-GEN` 的 `DGNCODE`：前者 `AIK-SRC2K` **实测合法** ⇒ 收口；
  后者 **不可判别** ⇒ 留缺。
* **D** `VIEW.RESULTGRAPHIC` 的 `LOAD_CASE_COMB`（**R155** 记录的**缺字段**）：
  补字段 + **真效果**（换工况 ⇒ 截图 **sha256 不同**）。

⚠️ A 组的判据是 **v2**（**真的过滤**）：实测证明**原生对任何 `PARTS` 取值都回 `200`**
⇒ 状态码**不**判别任何东西；`Part1`（上游声明）与**伪**取值 `PartZ` **同形**（空块）。

本文件钉住的判据（**铁律 ⓪**：效果，**不**是状态码）
-------------------------------------------------
1. **收口可复算 + 只增不减**：四组生成器 `--check` 全绿；**丢掉**已落盘取值**结构上不可能**；
2. **核心闸门**（离线，**与 `adapter._build` 逐字同一调用**）：合法取值**放行**、伪取值**拦**；
3. **真机效果**（证据在 `registry/live/`）：`PARTS` 的**过滤** · `TEXT_TYPE` 的**落盘** ·
   `DGNCODE` 的**档位** · `LOAD_CASE_COMB` 的**截图变化**；
4. **不可判别的端点如实留缺**（**不**猜、**不**算通过）；
5. **台账**：`check_spec_enums.py` 的 `DISPOSITIONS` 里每一项都有处置（`closed` 带生成器）。
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

PARTS_TOOL = TOOLS / "sync_parts_enum.py"
PARTS_PROBE_TOOL = TOOLS / "probe_parts_disposition_p169.py"
PARTS_EVIDENCE = LIVE / "parts_disposition_probe.json"

TEXT_TOOL = TOOLS / "sync_post_text_enum.py"
TEXT_PROBE_TOOL = TOOLS / "probe_post_text_p169.py"
TEXT_EVIDENCE = LIVE / "post_text_probe.json"

DGNCODE_TOOL = TOOLS / "sync_lcom_src_dgncode_enum.py"
DGNCODE_PROBE_TOOL = TOOLS / "probe_lcom_dgncode_p169.py"
DGNCODE_EVIDENCE = LIVE / "lcom_dgncode_probe.json"

LCC_TOOL = TOOLS / "sync_result_graphic_lcc.py"
LCC_PROBE_TOOL = TOOLS / "probe_load_case_comb_p169.py"
LCC_EVIDENCE = LIVE / "load_case_comb_probe.json"

CENSUS_TOOL = TOOLS / "check_spec_enums.py"
AUDIT = LIVE / "spec_enum_audit.json"
MANIFEST = REPO_ROOT / "registry" / "manifest.json"

SCHEMA_RESULTGRAPHIC = REPO_ROOT / "registry" / "schema" / "common" / "view" / "RESULTGRAPHIC.json"
SCHEMA_POST_TEXT = REPO_ROOT / "registry" / "schema" / "common" / "post" / "TEXT.json"
SCHEMA_LCOM_SRC = (
    REPO_ROOT / "registry" / "schema" / "products" / "gen_nx" / "ope" / "LCOM-SRC.json"
)
ERRATA = REPO_ROOT / "MIDAS_API_Online_Manual_勘误与补全_v1.0.md"

PARTS_DECIDABLE = ("POST.TABLE.BEAMFORCE", "POST.TABLE.BEAMFORCEVBM", "POST.TABLE.THISBEAMFORCE")
PARTS_UNDECIDABLE = (
    "POST.TABLE.RESULTANT_FORCES",
    "POST.TABLE.RESULTANT_FORCESVBM",
    "DESIGN.STEEL.KDS-41-30-2022.TABLE",
)
"""A 组的 **6** 个端点（**3** 可判别 ⇒ 收口 · **3** 不可判别 ⇒ 留缺）。"""

FAKE_PART = "PartZ"
FAKE_TEXT_TYPE = "NOT_A_REAL_TEXT_XYZ"
FAKE_DGNCODE = "NONSENSE-CODE"

EXPECTED_TEXT_TYPES = 29
"""`POST.TEXT` 的收口规模（同一 URI 的 **12** 篇文章声明的并集）。"""

EXPECTED_DGNCODE = ("AIK-SRC2K", "KDS 41 SRC : 2022")
"""`OPE.LCOM-SRC` 的收口后枚举（已落盘 ∪ 实测合法）。"""


def _load(path: pathlib.Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _guard(schema: Any, body: Any, *, endpoint: str, wrapper: str = "Argument") -> list[str]:
    """跑一次**核心闸门**（与 `adapter._build` **逐字同一**函数）⇒ 返回违例（**不**抛）。"""
    sys.path.insert(0, str(REPO_ROOT))
    from app.infrastructure.adapters.midas.errors import MidasValidationError  # noqa: PLC0415
    from app.infrastructure.adapters.midas.spec_guard import guard_spec_values  # noqa: PLC0415

    try:
        guard_spec_values(schema, body, endpoint=endpoint, wrapper=wrapper)
    except MidasValidationError as error:
        return [str(item) for item in (error.details or {}).get("problems") or []]
    return []


def _effective_schema(key: str) -> dict:
    """生产口径的 Schema（`effective_schema`，**R161** 起 `spec_guard` 用的就是它）。"""
    sys.path.insert(0, str(REPO_ROOT))
    from app.infrastructure.adapters.midas.registry import MidasRegistry  # noqa: PLC0415

    return MidasRegistry.load(REPO_ROOT / "registry").effective_schema(key) or {}


# ===== 1. A 组：`PARTS` =====


def test_p169_the_parts_generator_is_recomputable_and_monotone() -> None:
    """门槛（**收口可复算**）：`PARTS` 的生成器与已落盘一致，且**只增不减**。"""
    tool = _load(PARTS_TOOL, "sync_parts_enum_p169")
    assert tool.is_applied(REPO_ROOT), "生成器 --check 不过 ⇒ 收口回退"
    for item in tool.targets(REPO_ROOT):
        assert set(item["on_disk"]) <= set(item["expected"]), item["key"]
    assert tool.main(["--repo", str(REPO_ROOT), "--check"]) == 0


def test_p169_the_parts_evidence_marks_the_three_decidable_endpoints() -> None:
    """门槛（**真机裁决**）：**3** 个端点可判别（**真的过滤**）· **3** 个不可判别（如实留缺）。"""
    document = _json(PARTS_EVIDENCE)
    assert document["verdict"] == "PASSED", document["verdict"]
    assert int(document["criterion_version"]) >= 2, "v1 判据（状态码）**不**判别任何东西"
    assert set(document["decided_endpoints"]) == set(PARTS_DECIDABLE), document["decided_endpoints"]
    assert set(document["undecidable_endpoints"]) == set(PARTS_UNDECIDABLE)
    assert document["example_value_filters"] is True
    assert document["suspect_value_same_as_fake"] is True, "`Part1` 必须与伪取值**同形**（空块）"
    assert document["sentinel"]["unchanged"] is True
    for row in document["targets"]:
        verdict = row["verdict"]
        if not verdict["decidable"]:
            continue
        measured = row.get("measured") or {}
        example = measured[str(row["example_value"])]
        assert example["valid"] is True, row["endpoint"]
        assert example["data_rows"] < verdict["baseline_rows"], "必须**真的过滤**（少于基线）"
        # ⚠️ `suspect`（`Part1`）只对**声明里真的含它**的端点有意义 —— `THISBEAMFORCE` 的声明
        #    本来就没有 `Part1` ⇒ 它不在候选集合里，**不**参与断言。
        suspect = measured.get(str(row["suspect_value"]))
        if suspect is not None:
            assert suspect["valid"] is False, f"{row['endpoint']}：`Part1` 不该有效"


def test_p169_the_parts_closure_keeps_the_declared_values() -> None:
    """门槛（**只增不减**）：收口**没有**丢掉原声明取值（`Part1` 留着 —— 未断言它无效）。"""
    tool = _load(PARTS_TOOL, "sync_parts_enum_p169_keep")
    for item in tool.targets(REPO_ROOT):
        on_disk = set(item["on_disk"])
        for value in item["expected"]:
            assert value in on_disk, f"{item['key']} 丢了 {value!r}"
    on_disk = {item["key"]: set(item["on_disk"]) for item in tool.targets(REPO_ROOT)}
    for key in PARTS_DECIDABLE:
        enum = on_disk[key]
        assert "PartI" in enum, f"{key} 的枚举必须含示例体取值 `PartI`"
        assert FAKE_PART not in enum, f"{key} 的枚举**不得**含伪取值"


def test_p169_the_parts_guard_passes_example_values_and_blocks_fake() -> None:
    """门槛（**核心闸门**）：示例体取值**放行** · 伪取值**拦**（**零请求**）。"""
    for key in PARTS_DECIDABLE:
        schema = _effective_schema(key)
        token = _token_for(key)
        assert (
            _guard(schema, {"Argument": {"TABLE_TYPE": token, "PARTS": ["PartI"]}}, endpoint=key)
            == []
        )
        assert (
            _guard(schema, {"Argument": {"TABLE_TYPE": token, "PARTS": [FAKE_PART]}}, endpoint=key)
            != []
        )


def _token_for(key: str) -> str:
    """端点的 `TABLE_TYPE`（登记表优先；没有 ⇒ 取 Schema 枚举的唯一取值）。"""
    for entry in _json(MANIFEST)["endpoints"]:
        if str(entry.get("key") or "") != key:
            continue
        token = str(entry.get("table_type") or "")
        if token:
            return token
    tool = _load(PARTS_TOOL, "sync_parts_enum_p169_token")
    enum = tool.on_disk_parts(REPO_ROOT, key)
    assert len(enum) >= 1, key
    return enum[0] if key == "DESIGN.STEEL.KDS-41-30-2022.TABLE" else enum[0]


# ===== 2. B 组：`POST.TEXT` =====


def test_p169_the_post_text_key_is_renamed_by_measurement() -> None:
    """门槛（**键名裁决**）：契约键是 `TEXT_TYPE`，**旧键** `TABLE_TYPE` 已移除。"""
    properties = _json(SCHEMA_POST_TEXT)["schema"]["TEXT"]["properties"]["Argument"]["properties"]
    assert "TEXT_TYPE" in properties, "契约键必须按实测命名为 `TEXT_TYPE`"
    assert "TABLE_TYPE" not in properties, "旧键（实测 `Wrong Field`）**不得**留下"
    document = _json(TEXT_EVIDENCE)
    disposition = document["key_disposition"]
    assert disposition["true_key"] == "TEXT_TYPE"
    assert disposition["false_key"] == "TABLE_TYPE"
    assert disposition["verdict"] is True


def test_p169_the_post_text_closure_covers_every_declared_value() -> None:
    """门槛（**收口可复算**）：枚举 = 手册声明并集（**29**）∪ 已落盘，且原生**全部**接受。"""
    tool = _load(TEXT_TOOL, "sync_post_text_p169")
    assert tool.is_applied(REPO_ROOT), "生成器 --check 不过 ⇒ 收口回退"
    enum = tool.expected_enum(REPO_ROOT)
    assert len(enum) == EXPECTED_TEXT_TYPES, enum
    assert set(tool.manual_types(REPO_ROOT)) <= set(enum)
    document = _json(TEXT_EVIDENCE)
    assert document["verdict"] == "PASSED"
    assert sorted(document["accepted_types"]) == sorted(enum), "被原生接受的取值**全部**在枚举里"
    assert document["cleanup"]["empty_after"] is True, "授权目录必须清空（零残留）"
    assert document["sentinel"]["unchanged"] is True


def test_p169_the_post_text_guard_blocks_fake_values() -> None:
    """门槛（**核心闸门**）：合法取值**放行** · 伪取值**拦**（**零请求**）。"""
    schema = _effective_schema("POST.TEXT")
    assert _guard(schema, {"Argument": {"TEXT_TYPE": "TH_DISP"}}, endpoint="POST.TEXT") == []
    assert _guard(schema, {"Argument": {"TEXT_TYPE": FAKE_TEXT_TYPE}}, endpoint="POST.TEXT") != []


def test_p169_the_authorized_export_dir_is_git_ignored() -> None:
    """门槛（**副作用受控**）：探针的落盘目录在 `.gitignore` 内。"""
    ignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".tmp_p164c" in ignore, "授权落盘目录必须在 `.gitignore` 内"


# ===== 3. C 组：`DGNCODE` =====


def test_p169_the_dgncode_closure_is_measured_and_monotone() -> None:
    """门槛（**写路径裁决**）：`AIK-SRC2K` 实测合法 ⇒ 收口；**声明值未丢**。"""
    tool = _load(DGNCODE_TOOL, "sync_lcom_src_dgncode_p169")
    assert tool.is_applied(REPO_ROOT), "生成器 --check 不过 ⇒ 收口回退"
    assert tuple(tool.on_disk_enum(REPO_ROOT)) == EXPECTED_DGNCODE
    assert tool.main(["--repo", str(REPO_ROOT), "--check"]) == 0


def test_p169_the_dgncode_evidence_uses_band_equivalence() -> None:
    """门槛（**分档判据**）：待裁决候选与**声明**的合法值**同档**、与**伪**值**不同档**。"""
    document = _json(DGNCODE_EVIDENCE)
    assert document["verdict"] == "PASSED"
    verdicts = document["verdicts"]
    src = verdicts["OPE.LCOM-SRC"]
    assert src["decidable"] is True
    assert src["pending_legitimate"] is True
    assert src["declared_bands"] == src["pending_bands"], "同档 ⇒ 候选合法"
    assert src["fake_band"] not in src["pending_bands"], "伪取值必须在**另一档**"
    gen = verdicts["OPE.LCOM-GEN"]
    assert gen["decidable"] is False, "本 build 对**任何**取值都 `Wrong Field` ⇒ 不可判别"
    assert document["sentinel"]["unchanged"] is True
    for row in document["rows"]:
        assert not set(row["created"]) - set(row["removed"]), f"{row['key']} 有残留编号"


def test_p169_the_dgncode_guard_passes_measured_and_blocks_fake() -> None:
    """门槛（**核心闸门**）：实测合法的 `AIK-SRC2K` **放行** · 伪码**拦**（**零请求**）。"""
    schema = _effective_schema("OPE.LCOM-SRC")
    body_ok = {"Argument": {"OPTION": "ADD", "DGNCODE": "AIK-SRC2K"}}
    body_bad = {"Argument": {"OPTION": "ADD", "DGNCODE": FAKE_DGNCODE}}
    assert _guard(schema, body_ok, endpoint="OPE.LCOM-SRC") == []
    assert _guard(schema, body_bad, endpoint="OPE.LCOM-SRC") != []


def test_p169_the_undecidable_endpoint_is_left_open() -> None:
    """门槛（**不猜**）：`OPE.LCOM-GEN` 的 `DGNCODE` 在台账里是 `left_open` + 写明恢复条件。

    ⚠️ **P171 / R164 更新**：P169 的裁决号 `R162` 已被本批的**问题收窄**取代（`R164`）——
    仍**留缺**（`left_open`），但问题从「请求形状不明」收窄为「**一次是非问答**」（`OPTION` 键名）。
    """
    dispositions = {item["key"]: item for item in _json(AUDIT)["dispositions"]}
    item = dispositions["OPE.LCOM-GEN::DGNCODE"]
    assert item["status"] == "left_open", item
    assert item["ruling"] == "R164"
    assert "形状不明" in item["reason"], item["reason"]
    ask = item.get("ask", "")
    assert ask, "留缺必须写明「向谁问什么」"
    assert "OPTION" in ask, ask
    assert "是非" in ask, ask


# ===== 4. D 组：`LOAD_CASE_COMB` =====


def test_p169_the_load_case_comb_field_is_declared() -> None:
    """门槛（**缺字段补全**）：`Argument` 声明了 `LOAD_CASE_COMB`，形状 = 示例体并集。"""
    tool = _load(LCC_TOOL, "sync_result_graphic_lcc_p169")
    assert tool.is_applied(REPO_ROOT), "生成器 --check 不过 ⇒ 字段回退"
    properties = _json(SCHEMA_RESULTGRAPHIC)["schema"]["RESULTGRAPHIC"]["properties"]["Argument"][
        "properties"
    ]
    assert "LOAD_CASE_COMB" in properties, "**R155** 记录的缺字段必须补上"
    node = properties["LOAD_CASE_COMB"]
    assert set(node["properties"]) == set(tool.observed_inner_keys(REPO_ROOT))
    assert "required" not in node, "内键随变体而变（交集为空）⇒ **不得**臆造必填性"


def test_p169_the_load_case_comb_evidence_shows_a_real_effect() -> None:
    """门槛（**真效果**）：换工况 ⇒ 两张截图 **sha256 不同** · 不存在的工况 ⇒ 原生 `400`。"""
    document = _json(LCC_EVIDENCE)
    assert document["verdict"] == "PASSED"
    assert document["native_effect"] is True
    assert document["picture_changes"] is True, "**只换工况**画面必须真的变"
    assert document["bogus_rejected"] is True
    assert document["sentinel"]["unchanged"] is True
    runs = document["runs"]
    assert runs["case_a"]["shot"]["sha256"] != runs["case_b"]["shot"]["sha256"]
    assert runs["bogus"]["graphic_status"] >= 400


def test_p169_the_load_case_comb_does_not_widen_the_guard() -> None:
    """门槛（**零回归**）：补字段**不**拦合法调用（无枚举的字段 `spec_guard` **不**校验）。"""
    schema = _effective_schema("VIEW.RESULTGRAPHIC")
    body = {
        "Argument": {
            "CURRENT_MODE": "DisplacementContour",
            "LOAD_CASE_COMB": {"TYPE": "ST", "NAME": "DL"},
        }
    }
    assert _guard(schema, body, endpoint="VIEW.RESULTGRAPHIC") == []


def test_p169_the_generator_does_not_shrink_the_modes_enum() -> None:
    """门槛（**跨工具不打架**）：补字段**没有**影响 `CURRENT_MODE` 的收口（同一文件）。"""
    modes = _load(TOOLS / "sync_result_graphic_modes.py", "sync_result_graphic_modes_p169")
    assert modes.is_applied(REPO_ROOT), "`CURRENT_MODE` 的收口被本批的写回覆盖了"
    assert len(modes.on_disk_enum(REPO_ROOT)) == 36


# ===== 5. 台账 + 勘误 =====


def test_p169_the_census_ledger_is_complete_and_generator_checked() -> None:
    """门槛（**缺口不许静默**）：每个标志项都有处置；`closed` 项的生成器与已落盘一致。"""
    tool = _load(CENSUS_TOOL, "check_spec_enums_p169")
    assert tool.main(["--repo", str(REPO_ROOT), "--check"]) == 0
    dispositions = _json(AUDIT)["dispositions"]
    assert [item["key"] for item in dispositions if item["status"] == "missing"] == []
    closed = [item for item in dispositions if item["status"] == "closed"]
    assert closed, "本批必须至少收口一项"
    for item in closed:
        assert item.get("generator"), item
        assert item.get("generator_agrees") is True, f"{item['key']} 的生成器与已落盘不一致"


def test_p169_the_three_new_closures_are_registered_as_r162() -> None:
    """门槛（**裁决号**）：本批的**新**收口项都挂 **R162**（`R161` 的项保持不动）。"""
    dispositions = {item["key"]: item for item in _json(AUDIT)["dispositions"]}
    for key in (
        "POST.TABLE.BEAMFORCE::PARTS",
        "POST.TABLE.BEAMFORCEVBM::PARTS",
        "POST.TABLE.THISBEAMFORCE::PARTS",
        "POST.TEXT::TEXT_TYPE",
        "POST.TEXT::TABLE_TYPE",
        "OPE.LCOM-SRC::DGNCODE",
    ):
        assert dispositions[key]["status"] == "closed", key
        assert dispositions[key]["ruling"] == "R162", key
    for key in ("VIEW.RESULTGRAPHIC::CURRENT_MODE", "POST.TABLE.FIBR_EVENTSTEP::TABLE_TYPE"):
        assert dispositions[key]["ruling"] == "R161", f"{key} 的裁决号**不得**被改动"


def test_p169_the_errata_registers_the_three_upstream_defects() -> None:
    """门槛（**勘误登记**）：三条「声明 vs 示例」的实测结论都写进了勘误文件。"""
    text = ERRATA.read_text(encoding="utf-8")
    assert "E-01" in text and "E-02" in text and "E-03" in text
    assert "TEXT_TYPE" in text, "E-01 必须写明键名的实测结论"
    assert "Part I" in text, "E-02 必须写明规格表的佐证"


def test_p169_the_probe_tools_are_offline_safe_by_default() -> None:
    """门槛（**零请求默认**）：四个探针**不带** `--probe` 时都不发请求（预演模式）。"""
    for path in (PARTS_PROBE_TOOL, TEXT_PROBE_TOOL, DGNCODE_PROBE_TOOL, LCC_PROBE_TOOL):
        text = path.read_text(encoding="utf-8")
        assert '"--probe", action="store_true"' in text, path.name
        assert "if not args.probe:" in text, path.name


def test_p169_no_credential_leaks_into_the_evidence() -> None:
    """门槛（**绝不记录 secret**）：四份证据里**没有**凭据字段。"""
    for path in (PARTS_EVIDENCE, TEXT_EVIDENCE, DGNCODE_EVIDENCE, LCC_EVIDENCE):
        text = path.read_text(encoding="utf-8")
        for marker in ("MAPI-Key", "MIDAS_MAPI_KEY", "Authorization"):
            assert marker not in text, f"{path.name} 含凭据标记 {marker}"
