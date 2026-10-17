"""P168 / **R161**：`spec_guard` 的枚举**来源普查** + 两处枚举收口 + **可见性修复**。

本批的三件事（**互相依赖，缺一不可**）
------------------------------------
1. **普查**（`registry/tools/check_spec_enums.py`，**零请求**）：把 `registry/schema/**` 的
   **每一个**枚举约束逐条分类来源（**登记表** / **手册声明** / **单篇文章** / **无法追溯**），
   并给出三个可执行标志：**来源太窄**（会拦住合法调用）、**缺枚举**（非法取值抓不到）、
   **拦住手册自己的示例**（**R151** 的**直接签名**）。
2. **可见性修复**（**R161** 的核心 1 行，**用户已授权**）：`adapter._build` 原先传
   `registry.schema_json(key)`（**原样、含包装根键**）⇒ 对 **393 / 652** 个「根键 = 包装键」的文件，
   `spec_guard` 的 `schema["properties"][包装键]` 下钻**取不到** ⇒ **一个字段都不检查**
   （**盲区 104 / 225 个带枚举的文件**）。改用 `registry.effective_schema(key)`（P09 的
   `unwrap_schema()`，`request_schema_fields()` 一直用它）⇒ **225 / 225** 可下钻、
   **104** 个由盲变可见、已可见的 **121** 个**零回归**。
3. **两处收口**（**可见性修复的前置条件**）：**盲区一恢复，这些枚举立刻生效** ⇒ 若枚举**缺**
   合法取值，就**会**把合法调用拦死（**R151 的镜像事故**）：
   * **①** `VIEW.RESULTGRAPHIC` 的 `CURRENT_MODE`（**缺枚举**，**R155** 留缺）⇒ 补 **36** 个取值
     （手册 **34** 篇变体文章 / **56** 条示例的并集；生成器 `sync_result_graphic_modes.py`）；
   * **②** **6** 个变体端点的 `TABLE_TYPE`（**来源太窄**）⇒ 把**登记表的 token** 追加进枚举
     （`FIBR_*` ×5 + `REACTIONLSURFACESPRING`；生成器 `sync_table_type_variant_enum.py`）。

本文件钉住的判据（**铁律 ⓪**：效果，**不**是状态码）
-------------------------------------------------
1. 普查**可复算**且**台账完整**（每个标志项都有处置，**缺口不许静默**）；
2. **可见性**：`effective_schema()` 下**零盲区**，且对已可见的文件**零回归**（unwrap 是 no-op）；
3. **收口可复算 + 只增不减**（枚举 == 机械结果；丢掉已落盘取值**结构上不可能**）；
4. **核心闸门**（离线，**与 `adapter._build` 逐字同一调用**）：合法取值**放行**、非法取值**拦**；
5. **真机效果**（证据 `registry/live/spec_enum_probe.json`）：6 个变体端点的登记 token 原生
   **`200`** ·
   `RESULT.NODE.DISPLACEMENT`（**不**传 `table_type`）取到 **63** 行真数据（⇒ 这条路径**真的**走了
   变体文件的枚举）· `CURRENT_MODE` 的合法取值经生产路径**真的发出去**且三张截图**两两不同** ·
   **非法** `CURRENT_MODE` **零请求**被拦 · 跑前 / 跑后 **6** 个哨兵**逐项一致**。
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
"""仓库根目录。"""

CENSUS_TOOL = REPO_ROOT / "registry" / "tools" / "check_spec_enums.py"
"""普查工具（`--check` **零请求**；四个来源分类 + 三个标志 + 台账）。"""

MODES_TOOL = REPO_ROOT / "registry" / "tools" / "sync_result_graphic_modes.py"
"""`CURRENT_MODE` 的收口生成器（**只**拥有 `enum` / `description`）。"""

VARIANT_TOOL = REPO_ROOT / "registry" / "tools" / "sync_table_type_variant_enum.py"
"""变体 `TABLE_TYPE` 的收口生成器（**只**拥有 `enum` / `description`）。"""

PROBE_TOOL = REPO_ROOT / "registry" / "tools" / "probe_spec_enums_p168.py"
"""效果判据探针（默认预演 / `--probe` 真机 / `--check` 离线自洽）。"""

AUDIT = REPO_ROOT / "registry" / "live" / "spec_enum_audit.json"
"""普查证据（**R161**）。"""

PROBE_EVIDENCE = REPO_ROOT / "registry" / "live" / "spec_enum_probe.json"
"""真机效果证据（**R161**）。"""

MODES_EVIDENCE = REPO_ROOT / "registry" / "live" / "view_result_modes.json"
"""**R155** 的取证物（**36** 个取值，逐条可回溯）—— 收口必须与它**机械一致**。"""

SCHEMA_RESULTGRAPHIC = REPO_ROOT / "registry" / "schema" / "common" / "view" / "RESULTGRAPHIC.json"
SCHEMA_GENERIC_TABLE = REPO_ROOT / "registry" / "schema" / "common" / "post" / "TABLE.json"
SCHEMA_DESIGN_CODE_ANAL = (
    REPO_ROOT / "registry" / "schema" / "design" / "steel" / "KDS-41-30-2022" / "CODE-ANAL.json"
)
"""`R140` 的**原始事故端点**（`PERFORM_TYPE` 的枚举在 `oneOf[].const` 里）—— 本批**不得**回退。"""

ADAPTER = REPO_ROOT / "app" / "infrastructure" / "adapters" / "midas" / "adapter.py"
SPEC_GUARD = REPO_ROOT / "app" / "infrastructure" / "adapters" / "midas" / "spec_guard.py"
MANIFEST = REPO_ROOT / "registry" / "manifest.json"

DOCS_07 = REPO_ROOT / "docs" / "07_开发方案与任务续接_v1.0.md"
DOCS_08 = REPO_ROOT / "docs" / "08_会话交接与续接提示词_v1.0.md"
REGISTRY_README = REPO_ROOT / "registry" / "README.md"
ROOT_README = REPO_ROOT / "README.md"

FAKE_TOKEN = "NOT_A_REAL_TABLE_XYZ"
ILLEGAL_MODE = "displacement"
MODE_A = "DisplacementContour"
MODE_B = "DeformedShape"

VARIANT_ENDPOINTS = (
    "POST.TABLE.FIBR_ELASTREMAIN",
    "POST.TABLE.FIBR_EVENTSTEP",
    "POST.TABLE.FIBR_MAXCONTRACT",
    "POST.TABLE.FIBR_MEANCOMPCONTRACT",
    "POST.TABLE.FIBR_YILEDSTRENGTH",
    "POST.TABLE.REACTIONLSURFACESPRING",
)
"""**来源太窄**的 6 个变体端点（登记 token 原先**不在**自己的枚举里）。"""

EXPECTED_CONSTRAINTS = 754
"""枚举约束总数（**R161** 收口后：`enum` **639** + `oneOf.const` **115**）。"""

EXPECTED_BY_CLASS = {
    # ⚠️ **P175 / R168（事实变更）**：`manifest` 101 → **102**、`single_article` 158 → **157**
    # —— 新增的 27 张表带进 1 条枚举约束，其来源被归为「登记表」（原先那条算「单篇文章」）。
    # 合计仍 **754**（本批**未**新增枚举约束）。
    # ⚠️ **P177 / R169（事实变更）**：`manual` 225 → **223**、`untraceable` 270 → **272**
    # —— `DESIGN.RC.DRC` / `DESIGN.STEEL.DSTL` 的 `DGNCODE` 由 **1** 个取值补到 **65 / 66**
    # （来源 = 手册**规格表**，`registry/tools/sync_design_code_selector_enum.py`）。
    # 手册的 `json_schema` **只**声明 **1** 个取值（`KDS 41 20 : 2022` / `KDS 41 30 : 2022`），
    # 故并集**不再**落进「任一文章的 `json_schema` 声明并集」⇒ 这 **2** 条由 `manual` 变
    # `untraceable`。⚠️ **与 P169 / R162 同源**（那批是 `POST.TEXT` 的 3 条，**-2 / +2**）。
    # 取值本身**仍可追溯**（手册规格表 = 弱来源）⇒ `unexplained` 标志**仍为 0**（未变）。
    # 约束**总数**（**754**）与其余两类**一字未变**。
    # ⚠️ **P178 / R171（事实变更）**：`manual` 223 → **222**、`single_article` 157 → **156**、
    # `untraceable` 272 → **274** —— `DB.SWIND` / `DB.SSEIS` 的枚举各补了 `USER TYPE`
    # （**R170 修好后**闸门才看见这两个窄枚举；来源 = 本端点自己的手册示例）。
    # 补全后它们**不再**落进「`json_schema` 声明并集」⇒ `WIND_CODE` 由 `manual`、
    # `SEIS_CODE` 由 `single_article` 变为 `untraceable`。
    # ⚠️ **与 P169 / R162 / P177 同源**（同一类事实变更）。
    "manifest": 102,
    "manual": 222,
    "single_article": 156,
    "untraceable": 274,
}
"""四个来源分类的规模（合计 **754**）。

⚠️ **P169 / R162 更新（只改现状声称、不篡改历史）**：P168 当时是
`manual 227 / untraceable 268`。**P169** 把 `POST.TEXT` 的枚举**来源**从「一篇文章的 3 个取值」
扩到「同一 URI 12 篇文章的 **29** 个」⇒ 那 **3** 条约束的**分类**由 `manual` 变为 `untraceable`
（29 个取值跨 **12** 篇文章、不再落进**任一**文章的声明并集）⇒ **-2 / +2**。
⚠️ 约束**总数**（**754**）与其余两类**一字未变**。

⚠️ **P177 / R169（同类事实变更）**：`DESIGN.RC.DRC` / `DESIGN.STEEL.DSTL` 的 `DGNCODE`
由 **1** 个取值补到 **65 / 66**（手册**规格表**）⇒ 同样**不再**落进 `json_schema` 的声明并集
⇒ `manual -2 / untraceable +2`。**取值的可追溯性没有变差**：它们仍能从手册规格表复算
（`sync_design_code_selector_enum.py --check` 会**交叉断言**手册码表 == `design_codes.yaml`）。
⚠️ **R170 的边界**：这 **2** 条在 `patternProperties` 下 ⇒ 闸门**本来就没在检查**它们，
本次补全的收益是**数据一致性**（与 `design_codes.yaml` / 手册同源），**不是**「闸门现在会拦」。
"""

EXPECTED_BLIND_WITH_SCHEMA_JSON = 104
"""`schema_json()`（**旧口径**）下的**盲区**文件数（带枚举的 **225** 个里）。"""

EXPECTED_CURRENT_MODES = 36
EXPECTED_RESULT_ROWS = 63
"""自建混凝土简支梁的位移结果行数（**真值**）。"""


def _load(path: pathlib.Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _audit() -> dict:
    return json.loads(AUDIT.read_text(encoding="utf-8"))


def _probe() -> dict:
    return json.loads(PROBE_EVIDENCE.read_text(encoding="utf-8"))


def _schema(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["schema"]


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


# ===== 1. 普查：可复算 + 台账完整 =====


def test_p168_the_census_classifies_every_enum_constraint() -> None:
    """门槛（**普查**）：**每一个**枚举约束都有一条来源分类，且分类规模可复算。"""
    tool = _load(CENSUS_TOOL, "check_spec_enums_p168")
    document = tool.build(REPO_ROOT)
    summary = document["summary"]
    assert summary["constraints"]["total"] == EXPECTED_CONSTRAINTS, summary["constraints"]
    assert summary["constraints"]["enum"] + summary["constraints"]["oneOf.const"] == (
        EXPECTED_CONSTRAINTS
    )
    assert summary["by_class"] == EXPECTED_BY_CLASS, summary["by_class"]
    assert sum(summary["by_class"].values()) == EXPECTED_CONSTRAINTS
    assert len(document["constraints"]) == EXPECTED_CONSTRAINTS, "逐条清单必须与总数一致"
    for row in document["constraints"]:
        assert row["class"] in EXPECTED_BY_CLASS, row
        assert row["kind"] in {"enum", "oneOf.const"}, row
        assert row["value_count"] >= 1, row
        assert row["value_set"] in document["value_sets"], "取值集合必须可在 value_sets 里复算"


def test_p168_the_census_evidence_is_on_disk_and_idempotent() -> None:
    """门槛（**幂等**）：`--check` 零请求且与机械结果**逐条一致**。"""
    tool = _load(CENSUS_TOOL, "check_spec_enums_p168_check")
    assert tool.main(["--repo", str(REPO_ROOT), "--check"]) == 0


def test_p168_every_flagged_item_has_a_disposition() -> None:
    """门槛（**缺口不许静默**）：三个标志的**每一个**项都在处置台账里。

    （`closed` 或 `left_open` —— 见 `check_spec_enums.py` 的 `DISPOSITIONS`。）
    """
    document = _audit()
    dispositions = document["dispositions"]
    assert dispositions, "台账不得为空"
    missing = [item["key"] for item in dispositions if item["status"] == "missing"]
    assert missing == [], f"这些标志项没有处置：{missing}"
    flagged = {item["key"] for item in document["flags"]["narrow"]}
    flagged |= {
        f"{item['endpoints'][0]}::{item['field']}" for item in document["flags"]["missing_enum"]
    }
    flagged |= {item["key"] for item in document["flags"]["example_blocked"]}
    covered = {item["key"] for item in dispositions}
    assert flagged <= covered, f"漏掉的标志项：{sorted(flagged - covered)}"


def test_p168_the_closed_items_are_verified_against_their_generators() -> None:
    """门槛（**收口不可回退**）：每个 `closed` 项的生成器都与已落盘**一致**。"""
    closed = [item for item in _audit()["dispositions"] if item["status"] == "closed"]
    assert len(closed) >= 7, (
        f"本批应至少收口 7 项（1 个 CURRENT_MODE + 6 个变体），实际 {len(closed)}"
    )
    regressed = [item["key"] for item in closed if not item.get("generator_agrees")]
    assert regressed == [], f"这些已收口项**回退**了：{regressed}"


# ===== 2. 可见性修复（核心 1 行）=====


def test_p168_the_guard_takes_the_effective_schema() -> None:
    """门槛（**生产路径的绑定**）：`adapter._build` 里的 `spec_guard` 用 `effective_schema()`。"""
    text = ADAPTER.read_text(encoding="utf-8")
    assert "registry.effective_schema(resolved.definition.key)" in text, (
        "闸门必须用**剥离包装根键**后的生效 Schema（R161）"
    )
    assert "registry.schema_json(resolved.definition.key)" not in text, (
        "**旧口径**（原样、含包装根键）会让 104 个文件成为盲区 ⇒ 不得回退"
    )
    guard = SPEC_GUARD.read_text(encoding="utf-8")
    for value in (FAKE_TOKEN, "WEIGHT_IRREGULARITY_X", "TABLE_TYPE"):
        assert value not in guard, f"`spec_guard` 里出现了 MIDAS 取值 / 字段名 {value}"


def test_p168_unwrap_is_a_noop_for_the_files_that_were_already_visible() -> None:
    """门槛（**零回归**）：对 `properties` 根形态的文件，`unwrap_schema` **逐字节**不变。"""
    sys.path.insert(0, str(REPO_ROOT))
    from app.infrastructure.adapters.midas.registry import unwrap_schema  # noqa: PLC0415

    for path in (SCHEMA_GENERIC_TABLE, SCHEMA_DESIGN_CODE_ANAL):
        schema = _schema(path)
        assert unwrap_schema(schema) == schema, f"{path.name} 被 unwrap 改写了 ⇒ 有回归风险"


def test_p168_the_blind_spot_is_gone() -> None:
    """门槛（**盲区归零**）：`schema_json` 盲区 **104** ⇒ `effective_schema` 下 **0**。"""
    visibility = _audit()["guard"]["visibility"]
    assert visibility["blind_with_schema_json"] == EXPECTED_BLIND_WITH_SCHEMA_JSON, visibility
    assert visibility["blind_with_effective_schema"] == 0, visibility
    assert visibility["drillable_with_effective_schema"] == visibility["files_with_constraints"]


def test_p168_the_guard_now_reaches_the_variant_table_type_enum() -> None:
    """门槛（**可见性 → 枚举真的被查**）：变体文件的 `TABLE_TYPE` 现在**真的**会被判定。"""
    sys.path.insert(0, str(REPO_ROOT))
    from app.infrastructure.adapters.midas.registry import MidasRegistry  # noqa: PLC0415

    registry = MidasRegistry.load(REPO_ROOT / "registry")
    for endpoint in VARIANT_ENDPOINTS:
        schema = registry.effective_schema(endpoint)
        token = next(
            str(item["table_type"])
            for item in json.loads(MANIFEST.read_text(encoding="utf-8"))["endpoints"]
            if item["key"] == endpoint
        )
        legal = _guard(schema, {"Argument": {"TABLE_TYPE": token}}, endpoint=endpoint)
        illegal = _guard(schema, {"Argument": {"TABLE_TYPE": FAKE_TOKEN}}, endpoint=endpoint)
        assert legal == [], f"{endpoint} 拦住了自己的登记 token：{legal}"
        assert illegal, f"{endpoint} **没有**拦住伪 token ⇒ 闸门没生效"


def test_p168_the_guard_blocks_the_illegal_current_mode() -> None:
    """门槛（**收口的效果**，离线）：非法 `CURRENT_MODE` 被拦，合法取值放行。"""
    sys.path.insert(0, str(REPO_ROOT))
    from app.infrastructure.adapters.midas.registry import MidasRegistry  # noqa: PLC0415

    registry = MidasRegistry.load(REPO_ROOT / "registry")
    schema = registry.effective_schema("VIEW.RESULTGRAPHIC")
    body = {
        "Argument": {"CURRENT_MODE": ILLEGAL_MODE, "LOAD_CASE_COMB": {"TYPE": "ST", "NAME": "DL"}}
    }
    problems = _guard(schema, body, endpoint="VIEW.RESULTGRAPHIC")
    assert problems and ILLEGAL_MODE in problems[0], problems
    for mode in (MODE_A, MODE_B):
        assert (
            _guard(schema, {"Argument": {"CURRENT_MODE": mode}}, endpoint="VIEW.RESULTGRAPHIC")
            == []
        ), f"合法取值 {mode} 被拦 ⇒ 收口把闸门收得太紧"


def test_p168_the_generic_table_type_gate_is_not_relaxed() -> None:
    """门槛（**R140 不得放松**）：通用入口 `POST.TABLE` 的伪 token 仍被拦。"""
    sys.path.insert(0, str(REPO_ROOT))
    from app.infrastructure.adapters.midas.registry import MidasRegistry  # noqa: PLC0415

    registry = MidasRegistry.load(REPO_ROOT / "registry")
    schema = registry.effective_schema("POST.TABLE")
    assert _guard(schema, {"Argument": {"TABLE_TYPE": FAKE_TOKEN}}, endpoint="POST.TABLE")
    assert (
        _guard(schema, {"Argument": {"TABLE_TYPE": "DISPLACEMENTG"}}, endpoint="POST.TABLE") == []
    )


# ===== 3. 收口：可复算 + 只增不减 =====


def test_p168_the_current_mode_enum_is_the_manual_union() -> None:
    """门槛（**收口①**）：`CURRENT_MODE` 的枚举 == 手册**全部变体文章**的并集（**36**）。"""
    tool = _load(MODES_TOOL, "sync_result_graphic_modes_p168")
    manual = tool.manual_modes(REPO_ROOT)
    enum = tool.expected_enum(REPO_ROOT)
    assert len(enum) == EXPECTED_CURRENT_MODES, len(enum)
    assert enum == sorted(set(enum)), "枚举必须去重且有序（确定性）"
    assert set(manual) <= set(enum), "枚举必须包含手册的**全部**取值"
    assert ILLEGAL_MODE not in set(enum), "被原生拒过的取值**不得**进枚举"
    assert tool.on_disk_enum(REPO_ROOT) == enum, "已落盘枚举必须逐条等于机械结果"
    assert tool.is_applied(REPO_ROOT)
    evidence = json.loads(MODES_EVIDENCE.read_text(encoding="utf-8"))
    assert sorted(evidence["modes"]) == enum, "必须与 R155 的取证物**机械一致**"


def test_p168_the_variant_table_type_enums_contain_their_tokens() -> None:
    """门槛（**收口②**）：6 个变体端点的枚举**都**含自己的登记 token，且生成器 `--check` 绿。"""
    tool = _load(VARIANT_TOOL, "sync_table_type_variant_enum_p168")
    entries = {
        str(item["key"]): item
        for item in json.loads(MANIFEST.read_text(encoding="utf-8"))["endpoints"]
    }
    for endpoint in VARIANT_ENDPOINTS:
        token = str(entries[endpoint]["table_type"])
        enum = tool.expected_enum(REPO_ROOT, endpoint)
        assert token in enum, f"{endpoint} 的枚举缺自己的 token {token}"
        assert enum == sorted(set(enum)), enum
        on_disk = tool.on_disk_enum(REPO_ROOT / "registry" / str(entries[endpoint]["schema"]))
        assert on_disk == enum, f"{endpoint} 已落盘枚举 != 机械结果"
    assert tool.targets(REPO_ROOT) == [], "收口后**不应**再有待收口的端点（幂等）"
    assert tool.is_applied(REPO_ROOT)
    assert tool.main(["--repo", str(REPO_ROOT), "--check"]) == 0


def test_p168_the_variant_generator_never_shrinks_the_enum(tmp_path: pathlib.Path) -> None:
    """门槛（**只增不减**）：合成仓库里枚举缺 token ⇒ 机械结果 = 枚举 ∪ {token}（**不**删取值）。"""
    tool = _load(VARIANT_TOOL, "sync_table_type_variant_enum_p168_shrink")
    schema = {
        "key": "POST.TABLE.DEMO",
        "uri": "POST/TABLE",
        "source": "help_center",
        "schema": {
            "properties": {
                "Argument": {
                    "type": "object",
                    "properties": {"TABLE_TYPE": {"type": "string", "enum": ["KEEP_ME"]}},
                }
            }
        },
    }
    target = tmp_path / "registry" / "schema" / "common" / "post" / "TABLE" / "DEMO.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (tmp_path / "registry" / "manifest.json").write_text(
        json.dumps(
            {
                "endpoints": [
                    {
                        "key": "POST.TABLE.DEMO",
                        "table_type": "DEMO",
                        "schema": "schema/common/post/TABLE/DEMO.json",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    assert tool.expected_enum(tmp_path, "POST.TABLE.DEMO") == ["DEMO", "KEEP_ME"]
    assert tool.main(["--repo", str(tmp_path), "--write"]) == 0
    assert tool.is_applied(tmp_path), "写入后必须自洽（幂等）"
    written = json.loads(target.read_text(encoding="utf-8"))["schema"]["properties"]["Argument"][
        "properties"
    ]["TABLE_TYPE"]["enum"]
    assert written == ["DEMO", "KEEP_ME"], "旧取值 **一个不丢**（只增不减）"


def test_p168_the_modes_generator_keeps_an_unexplained_on_disk_value(
    tmp_path: pathlib.Path,
) -> None:
    """门槛（**只增不减**）：已落盘但手册里没有的取值**必须**留在机械结果里（**不**静默丢掉）。"""
    tool = _load(MODES_TOOL, "sync_result_graphic_modes_p168_keep")
    schema = {
        "key": "VIEW.RESULTGRAPHIC",
        "uri": "VIEW/RESULTGRAPHIC",
        "source": "help_center",
        "schema": {
            "RESULTGRAPHIC": {
                "properties": {
                    "Argument": {
                        "type": "object",
                        "properties": {
                            "CURRENT_MODE": {"type": "string", "enum": ["HAND_WRITTEN_VALUE"]}
                        },
                    }
                }
            }
        },
    }
    target = tmp_path / "registry" / "schema" / "common" / "view" / "RESULTGRAPHIC.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manual = {
        "endpoints": [
            {
                "input_uri": "view/RESULTGRAPHIC",
                "title": "Demo - Result Display",
                "examples": [
                    {"name": "Demo #1", "json": '{"Argument": {"CURRENT_MODE": "DemoMode"}}'}
                ],
            }
        ]
    }
    for name in (
        "MIDAS_API_Online_Manual_Gen_NX_v1.0.json",
        "MIDAS_API_Online_Manual_数据_v1.0.json",
    ):
        (tmp_path / name).write_text(json.dumps(manual), encoding="utf-8")
    enum = tool.expected_enum(tmp_path)
    assert enum == ["DemoMode", "HAND_WRITTEN_VALUE"], enum


# ===== 4. 真机效果（铁律 ⓪）=====


def test_p168_the_probe_check_is_green() -> None:
    """门槛（**离线自洽**）：探针 `--check` 通过（证据齐备 + 判据全真 + 与数据侧一致）。"""
    tool = _load(PROBE_TOOL, "probe_spec_enums_p168_check")
    assert tool.check_offline(REPO_ROOT) == 0


def test_p168_the_real_machine_verdict_is_passed() -> None:
    """门槛（**效果**）：真机证据的判定 = `PASSED` 且各分判据全真、哨兵逐项一致。"""
    document = _probe()
    assert document["verdict"] == "PASSED", document.get("note")
    core = document["core"]
    for key in (
        "variant_result_ok",
        "fake_token_ok",
        "picture_changes",
        "legal_mode_sent",
        "illegal_mode_blocked",
    ):
        assert core[key] is True, f"{key} 不为真 ⇒ 效果结论不成立"
    assert document["variant_native_accepted"] is True
    assert document["sentinel"]["unchanged"] is True, "跑后哨兵与跑前不一致 ⇒ 有残留"


def test_p168_the_variant_tokens_are_accepted_by_the_native() -> None:
    """门槛（**原生阳性**）：6 个变体端点的**登记 token** 原生 **`200`**（**不**是鉴权失败）。"""
    rows = _probe()["variant_table_type"]
    assert len(rows) == len(VARIANT_ENDPOINTS), len(rows)
    for row in rows:
        assert row["native"]["status"] == 200, row
        assert row["native"]["auth_error"] is False, row
        assert row["guard_allows_registered_token"] is True, row
        assert row["guard_blocks_fake_token"] is True, row


def test_p168_the_variant_result_really_reads_rows_through_the_production_path() -> None:
    """门槛（**端到端**）：`RESULT.NODE.DISPLACEMENT`（**不**传 `table_type`）取到 **63** 行。

    ⚠️ 这条路径的 `TABLE_TYPE` 来自**端点自己的登记 token** ⇒ 它**真的**走了**变体文件**的枚举
    （可见性修复前那条路径是**盲**的）⇒ 这是「可见性修复 + 收口②」的**联合**判据。
    """
    result = _probe()["core"]["variant_result"]
    assert result["success"] is True, result
    assert result["readback"]["count"] == EXPECTED_RESULT_ROWS, result["readback"]
    requests = result["requests"]
    assert requests, "必须真的发出请求"
    assert all(200 <= int(item["status"]) < 300 for item in requests), requests
    assert requests[0]["table_type"] == "DISPLACEMENTG", requests[0]
    assert requests[0]["path"].endswith("/POST/TABLE"), requests[0]


def test_p168_the_illegal_current_mode_is_blocked_with_zero_requests() -> None:
    """门槛（**核心阴性**）：非法 `CURRENT_MODE` ⇒ **零请求** + `STRUCTAI-1200`。"""
    row = _probe()["core"]["illegal_mode"]
    assert row["requests"] == [], "**零请求**：闸门必须在**发请求之前**拦"
    error = row["error"]
    assert error["code"] == "STRUCTAI-1200", error
    assert error["native_reason"] == "value_not_in_spec_enum", error
    assert error["native_stage"] == "midas_adapter", error
    assert error["native_endpoint"] == "VIEW.RESULTGRAPHIC", error


def test_p168_the_picture_really_changes_and_the_legal_mode_is_sent() -> None:
    """门槛（**原生真效果**）：三张截图**两两不同**，且合法取值经生产路径**真的**发出去。"""
    core = _probe()["core"]
    views = core["views"]
    shots = {tag: row["shot"] for tag, row in views.items()}
    assert all(item["exists"] and item["bytes"] > 0 for item in shots.values()), shots
    hashes = {item["sha256"] for item in shots.values()}
    assert len(hashes) == len(shots), f"截图**没有**两两不同（{shots}）"
    mode_a = views["打开 DisplacementContour"]["requests"]
    assert mode_a, "合法取值必须真的发出去"
    assert any(item["path"].endswith("/VIEW/RESULTGRAPHIC") for item in mode_a), mode_a
    assert any(item["current_mode"] == MODE_A for item in mode_a), mode_a
    assert all(200 <= int(item["status"]) < 300 for item in mode_a), mode_a


# ===== 5. 文档 / 裁决 =====


def test_p168_the_ruling_is_recorded_in_docs_07() -> None:
    """门槛（**可回溯**）：`docs/07` §16.1 有 **R161** 一行，写明盲区 / 收口 / 效果。"""
    text = DOCS_07.read_text(encoding="utf-8")
    assert "R161" in text, "必须登记裁决编号 R161"
    for fragment in ("104", "225", "effective_schema", "CURRENT_MODE"):
        assert fragment in text, f"R161 行必须写明 {fragment}"


def test_p168_the_registry_readme_and_root_readme_are_updated() -> None:
    """门槛（**现状文档**）：`registry/README.md` 有 §8.22；根 `README.md` 引用本批。"""
    registry_readme = REGISTRY_README.read_text(encoding="utf-8")
    assert "§8.22" in registry_readme or "### 8.22" in registry_readme, (
        "registry/README 必须新增 §8.22"
    )
    assert "R161" in registry_readme
    root_readme = ROOT_README.read_text(encoding="utf-8")
    assert "R161" in root_readme, "根 README 的现状声称必须跟上"


def test_p168_the_next_batch_prompt_replaces_the_current_one() -> None:
    """门槛（**交接协议**）：`docs/08` §3 有 P168 行、§4 的**当前块**已是**后续批次**的提示词。

    ⚠️ §4 里**保留**历批提示词（`> ### 历史（…，保留备查）`）⇒ 只在**第一个历史块之前**
    检查「当前提示词」，**不**把历史记录当成残留。
    ⚠️ **P171 起本判据改为「不锁定具体批号」**：原先钉死 `P169`（当时的下一批），
    每过一批就**必然**红一次 —— 那是**把快照当判据**。改为断言「当前块**不是** P168 自己
    的提示词」，且**历批提示词确实被保留**（这才是**交接协议**真正要守的东西）。
    """
    text = DOCS_08.read_text(encoding="utf-8")
    assert "| **P168** |" in text, "§3 状态表必须有 P168 行"
    section = text.split("## 4. 当前续接提示词", 1)[1]
    current = section.split("> ### 历史（", 1)[0]
    assert "唯一任务" in current, "§4 的**当前块**必须是一份**下一批**的提示词"
    assert "P168 · 唯一任务" not in current, "§4 的**当前块**不得残留本批的提示词"
    assert "历史（P168 的提示词，保留备查）" in text, (
        "本批的提示词必须**保留**为历史（不改历史记录）"
    )
