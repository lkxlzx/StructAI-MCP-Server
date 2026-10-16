"""P171 / **R164**：P170 留缺 **3** 项（**全部**产品 / 数据侧）逐条推到底。

本批**零请求**（3 项**都不**在**任何** OperationPlan 的生产路径上 ⇒ 只用**本仓可读**证据）
----------------------------------------------------------------------------------
* **① `OPE.LINEBMLD::TYPE`** —— 口径**澄清** = 「**荷载类型枚举**（String），**不是**编号」。
  原先记的「示例体混了编号 `'0'`/`'1'`」是**普查的取值表口径错**：`check_spec_enums.py` 的
  `uri_examples` 是**递归**收集 ⇒ 把**同名不同义**的嵌套字段（`Argument.LOAD.TYPE` =
  Distance Type（**Integer**）· `Argument.ECCEN.TYPE` = Centroid/Offset（**Integer**））
  并成了**一张**表。**判据修正** = 候选取值**只**取**包装键体下第一层**的叶子。
* **② `OPE.GSBG::BRDG_GROUP`** —— 裁决 = 「**不是**受控词表」⇒ 此处**没有** `enum` 是**正确**的。
* **③ `OPE.LCOM-GEN::DGNCODE`** —— 「形状不明」**不**成立（手册**自己的** `json_schema` 与
  我们**已落盘**的 Schema **逐字节同形**）⇒ 收窄为**一次是非问答**。

本文件钉住的判据
----------------
1. **判据修正可复算**：`uri_direct_examples` 只收**包装键体下第一层**的叶子；`TYPE` = **9** 个
   枚举名（**不含** `'0'`/`'1'`）；**递归**口径的 `uri_examples` **保留**（弱来源不受影响）；
2. **不静默丢弃**：取值**只**来自嵌套同名子字段 ⇒ 进 `missing_enum_nested_only` 一档；
3. **台账**：3 项 `ruling == "R164"` · `status == "left_open"` · 都有 `ask`（**向谁问什么**）；
4. **收口数不变**：`closed` **14** · `left_open` **3**（本批**不**改收口数）；
5. **端点 YAML**：只改注释（`sync_manifest.py` **0** 差异）；**没有**往任何 Schema 里塞 `enum`；
6. **主指标不变**：`check_operation_availability --check` = **68 / 71**；
7. **零请求**：本批**不**碰真机（`app/**` 一行未改）。
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
"""仓库根目录。"""

TOOLS = REPO_ROOT / "registry" / "tools"
LIVE = REPO_ROOT / "registry" / "live"

CENSUS_TOOL = TOOLS / "check_spec_enums.py"
AVAILABILITY_TOOL = TOOLS / "check_operation_availability.py"
MANIFEST_TOOL = TOOLS / "sync_manifest.py"
AUDIT = LIVE / "spec_enum_audit.json"

YAML_LINEBMLD = REPO_ROOT / "registry" / "common" / "ope" / "LINEBMLD.yaml"
YAML_GSBG = REPO_ROOT / "registry" / "products" / "gen_nx" / "ope" / "GSBG.yaml"
YAML_LCOM_GEN = REPO_ROOT / "registry" / "products" / "gen_nx" / "ope" / "LCOM-GEN.yaml"

MANUAL_DATA = REPO_ROOT / "MIDAS_API_Online_Manual_数据_v1.0.json"
SCHEMA_LCOM_GEN = (
    REPO_ROOT / "registry" / "schema" / "products" / "gen_nx" / "ope" / "LCOM-GEN.json"
)

LINEBMLD_TYPES = (
    "CONLOAD",
    "CONMOMENT",
    "CURVED",
    "TRALOAD",
    "TRAMOMENT",
    "TRAPRESSURE",
    "UNILOAD",
    "UNIMOMENT",
    "UNIPRESSURE",
)
"""修正后 `Argument.TYPE` 的 **9** 个取值（**全部**是枚举名）。"""

NESTED_TYPE_VALUES = ("0", "1")
"""来自 `Argument.LOAD.TYPE` / `Argument.ECCEN.TYPE`（都是 **Integer**）的**编号** ——
**不**属于 `Argument.TYPE`。"""

LEFT_OPEN_R164 = (
    "OPE.GSBG::BRDG_GROUP",
    "OPE.LCOM-GEN::DGNCODE",
    "OPE.LINEBMLD::TYPE",
)


def _load(path: pathlib.Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _manual_articles() -> list[tuple[int, dict]]:
    """`MIDAS_API_Online_Manual_数据_v1.0.json` 的条目（**带序号** ⇒ 文章 id 可复算）。"""
    return list(enumerate(_json(MANUAL_DATA)["endpoints"]))


# ===== 1. 判据修正（取值表的口径）=====


def test_p171_the_census_collects_direct_children_only() -> None:
    """门槛（**判据修正**）：`uri_direct_examples` 只收**包装键体下第一层**的叶子。"""
    tool = _load(CENSUS_TOOL, "check_spec_enums_p171")
    manual = tool.manual_sources(REPO_ROOT)
    direct = manual["uri_direct_examples"]
    assert ("ope/linebmld", "TYPE") in direct, "直接子键表必须存在"
    assert set(direct[("ope/linebmld", "TYPE")]) == set(LINEBMLD_TYPES), direct[
        ("ope/linebmld", "TYPE")
    ]
    # 递归口径**保留**（弱来源），且**仍**含嵌套同名字段的编号 ⇒ 两个口径**必须**并存。
    recursive = manual["uri_examples"]
    assert set(NESTED_TYPE_VALUES) <= set(recursive[("ope/linebmld", "TYPE")])


def test_p171_the_recursive_values_are_attributed_to_their_parents() -> None:
    """门槛（**同名不同义**）：`'0'`/`'1'` 来自 `LOAD.TYPE` / `ECCEN.TYPE`（**Integer**）。

    ⚠️ 示例体**只**在 **Gen NX 手册**里（数据手册的那一条 `examples` 为空）。
    """
    by_parent: dict[str, set[str]] = {}
    for filename in ("MIDAS_API_Online_Manual_Gen_NX_v1.0.json",):
        for entry in _json(REPO_ROOT / filename)["endpoints"]:
            if str(entry.get("input_uri") or "") != "ope/LINEBMLD":
                continue
            for example in entry.get("examples") or []:
                argument = json.loads(example["json"])["Argument"]
                assert "TYPE" in argument, "示例体必须直接给出 Argument.TYPE"
                by_parent.setdefault("Argument", set()).add(str(argument["TYPE"]))
                for holder in ("LOAD", "ECCEN"):
                    if holder in argument and "TYPE" in argument[holder]:
                        by_parent.setdefault(holder, set()).add(str(argument[holder]["TYPE"]))
    assert by_parent["Argument"] == set(LINEBMLD_TYPES)
    assert by_parent["LOAD"] == set(NESTED_TYPE_VALUES)
    assert by_parent["ECCEN"] == {"0"}


def test_p171_the_manual_spec_table_types_the_three_type_fields() -> None:
    """门槛（**上游佐证**）：手册**规格表**逐行给出三处 `TYPE` 的**类型列**。"""
    rows: list[list[str]] = []
    for _, entry in _manual_articles():
        if str(entry.get("input_uri") or "") != "ope/LINEBMLD":
            continue
        for spec in entry.get("specifications") or []:
            if isinstance(spec, list) and len(spec) >= 6 and spec[2] == '"TYPE"':
                rows.append(spec)
    assert len(rows) == 3, rows
    strings = [row for row in rows if row[3] == "String"]
    integers = [row for row in rows if row[3] == "Integer"]
    assert len(strings) == 1, rows
    assert len(integers) == 2, rows
    assert strings[0][5] == "Required", strings[0]
    assert strings[0][1].startswith("Load Type"), strings[0]
    # 第 **(3)** 行（Distance Type）也标 `Required` ⇒ **不能**只按 `Required` 认 `Argument.TYPE`。
    assert any(row[5] == "Required" for row in integers), rows
    for value in LINEBMLD_TYPES:
        assert value in strings[0][1], value


def test_p171_the_census_evidence_is_written_and_idempotent() -> None:
    """门槛（**可复算**）：已落盘 == 机械结果（`--check` 零请求）。"""
    tool = _load(CENSUS_TOOL, "check_spec_enums_p171_idem")
    assert tool.main(["--repo", str(REPO_ROOT), "--check"]) == 0


# ===== 2. 不静默丢弃 =====


def test_p171_nested_only_candidates_are_bucketed_not_dropped() -> None:
    """门槛（**不静默丢弃**）：新增一档 `missing_enum_nested_only`（机械结果里为 **0**）。"""
    document = _json(AUDIT)
    flags = document["flags"]
    assert "missing_enum_nested_only" in flags, "取值只来自嵌套同名子字段必须**如实**另立一档"
    assert flags["missing_enum_nested_only"] == []
    assert document["summary"]["flags"]["missing_enum_nested_only"] == 0
    # 本批**不**改「缺枚举」的数量（仍是那 3 项产品 / 数据侧）。
    assert len(flags["missing_enum"]) == 3
    linebmld = [item for item in flags["missing_enum"] if item["uri"] == "ope/linebmld"]
    assert len(linebmld) == 1
    assert set(linebmld[0]["values"]) == set(LINEBMLD_TYPES)
    assert linebmld[0]["value_count"] == 9, "修正后**不得**再含 '0'/'1'"


# ===== 3. 台账（3 项 R164）=====


def test_p171_the_three_left_open_items_are_ruled_r164() -> None:
    """门槛（**裁决号 + 留缺**）：3 项都挂 **R164** · 仍 `left_open` · 都写明「向谁问什么」。"""
    dispositions = {item["key"]: item for item in _json(AUDIT)["dispositions"]}
    for key in LEFT_OPEN_R164:
        item = dispositions[key]
        assert item["status"] == "left_open", item
        assert item["ruling"] == "R164", key
        assert item.get("ask"), f"{key} 的留缺必须写明「向谁问什么」"


def test_p171_the_closed_count_is_unchanged() -> None:
    """门槛（**收口数不变**）：`closed` **16** · `left_open` **3**（本批**不**改收口数）。

    ⚠️ **口径更正（P171）**：P170 的**文档**把 P170 收尾写成「**收口 11 → 14**」，而
    `registry/live/spec_enum_audit.json` 里实际是 **16 / 3**（`git show 61f6f63` 可复算）
    ⇒ 那 **+2** 是 **R161 的变体 `TABLE_TYPE` 项**（`DISPOSITIONS` 里**6** 条共用
    `_VARIANT_TABLE_TYPE`，其中 `POST.TABLE.FIBR_ELASTREMAIN` / `REACTIONLSURFACESPRING`
    是 P168 之后**新**进台账的）—— P169 / P170 的文档**漏计**。**本批**把文档口径改为
    **与台账一致**（`16 / 3`），**不**改任何处置本身。
    """
    dispositions = _json(AUDIT)["dispositions"]
    closed = [item for item in dispositions if item["status"] == "closed"]
    left_open = [item for item in dispositions if item["status"] == "left_open"]
    assert len(dispositions) == 19
    assert len(closed) == 16
    assert len(left_open) == 3
    assert {item["key"] for item in left_open} == set(LEFT_OPEN_R164)
    for item in closed:
        assert item.get("generator_agrees") is True, f"{item['key']} 的生成器与已落盘不一致"


def test_p171_the_clarification_is_recorded_in_the_dispositions() -> None:
    """门槛（**结论入台账**）：三项的 `reason` 都写清**本批的裁决内容**。"""
    dispositions = {item["key"]: item for item in _json(AUDIT)["dispositions"]}
    assert "String" in dispositions["OPE.LINEBMLD::TYPE"]["reason"]
    assert "不是受控词表" in dispositions["OPE.GSBG::BRDG_GROUP"]["reason"]
    gen = dispositions["OPE.LCOM-GEN::DGNCODE"]
    assert "逐字节同形" in gen["reason"], gen["reason"]
    assert "OPTION" in gen["ask"], gen["ask"]


# ===== 4. 端点 YAML（只改注释）=====


def test_p171_the_endpoint_yamls_record_the_ruling() -> None:
    """门槛（**结论入端点 YAML**）：三份 YAML 的头部注释都写了 **R164** 的裁决。"""
    assert "R164" in YAML_LINEBMLD.read_text(encoding="utf-8")
    assert "R164" in YAML_GSBG.read_text(encoding="utf-8")
    assert "R164" in YAML_LCOM_GEN.read_text(encoding="utf-8")
    gsbg = YAML_GSBG.read_text(encoding="utf-8")
    assert "不是受控词表" in gsbg
    linebmld = YAML_LINEBMLD.read_text(encoding="utf-8")
    assert "荷载类型枚举" in linebmld
    assert "LOAD.TYPE" in linebmld and "ECCEN.TYPE" in linebmld


def test_p171_no_enum_was_invented_for_the_three_fields() -> None:
    """门槛（**不硬凑枚举**）：三处字段的 Schema 里**没有**被塞进 `enum`。"""
    gsbg = _json(REPO_ROOT / "registry/schema/products/gen_nx/ope/GSBG.json")["schema"]
    node = gsbg["properties"]["Argument"]["properties"]["BRDG_GROUP"]
    assert "enum" not in node, "`BRDG_GROUP` 是**自由引用名** ⇒ 不得硬凑枚举"
    assert node["type"] == "string"

    linebmld = _json(REPO_ROOT / "registry/schema/common/ope/LINEBMLD.json")["schema"]
    node = linebmld["LINEBMLD"]["properties"]["Argument"]["properties"]["TYPE"]
    assert "enum" not in node, "`Argument.TYPE` 的词表**未**经权威确认 ⇒ 不得硬凑枚举"
    assert node["type"] == "string"

    # `DGNCODE` 仍是**三个** `oneOf` 分支里的 `const`（**不**是 `enum`）。
    lcom = _json(SCHEMA_LCOM_GEN)["schema"]["properties"]["Argument"]
    branches = lcom["oneOf"]
    assert len(branches) == 3, branches
    consts = [branch["properties"]["DGNCODE"].get("const") for branch in branches]
    assert all(isinstance(item, str) for item in consts), consts
    assert all("enum" not in branch["properties"]["DGNCODE"] for branch in branches)


def test_p171_the_yaml_edits_do_not_move_the_manifest(monkeypatch: Any, capsys: Any) -> None:
    """门槛（**只改注释**）：`sync_manifest.py` 预演 **0** 差异（**不**写回）。"""
    tool = _load(MANIFEST_TOOL, "sync_manifest_p171")
    monkeypatch.setattr("sys.argv", ["sync_manifest.py", "--repo", str(REPO_ROOT)])
    assert tool.main() == 0
    output = capsys.readouterr().out
    assert "manifest 条目数 = 636" in output, output
    assert "字段差异总数 = 0" in output, output


# ===== 5. `LCOM-GEN` 的形状分歧不成立 =====


def test_p171_the_manual_and_our_schema_for_lcom_gen_are_byte_identical() -> None:
    """门槛（**同源**）：手册**自己的** `json_schema` 与我们**已落盘**的 Schema **同形**。"""
    manual_schema = None
    for index, entry in _manual_articles():
        if str(entry.get("input_uri") or "") == "ope/LCOM-GEN":
            raw = entry.get("json_schema")
            assert raw, f"手册第 {index} 条必须带 json_schema"
            manual_schema = json.loads(raw)
    assert manual_schema is not None, "手册里必须有 ope/LCOM-GEN 的 json_schema"
    ours = _json(SCHEMA_LCOM_GEN)["schema"]
    assert json.dumps(manual_schema, sort_keys=True) == json.dumps(ours, sort_keys=True)
    description = manual_schema["properties"]["Argument"]["description"]
    assert "CODE_SELECTION" in description


# ===== 6. 主指标不变 =====


def test_p171_the_main_metric_is_consistent() -> None:
    """门槛：`--check` 自洽（本批价值在**澄清**与**判据修正**，**不**在主指标）。

    ⚠️ 本批（P171）时是「**主指标不变**」+ `68 / 71`。
    **R166（P174）** 用真机实测收口 `POST.STEELCODECHECK` ⇒ 主指标为 **`69 / 71`**。
    ⇒ 本用例改为钉**当前**值 + `--check` 自洽（**不**再声称「不变」—— 那已不是事实）。
    """
    tool = _load(AVAILABILITY_TOOL, "check_operation_availability_p171")
    document = tool.compute()
    assert document["available"] == 69
    assert document["total"] == 71
    assert document["blocked"] == 2
    assert document["blocker_endpoint_count"] == 4
    assert tool.check() == 0


# ===== 7. 零请求 =====


def test_p171_the_batch_ran_no_probes() -> None:
    """门槛（**零请求**）：本批**没有**新增任何 `*_probe.json`（`--probe` 一次都没跑）。"""
    probes = sorted(path.name for path in LIVE.glob("*probe*.json"))
    assert not any("p171" in name for name in probes), probes
