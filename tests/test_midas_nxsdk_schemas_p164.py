"""NXSDK 外部证据裁决（第四批）—— 手册勘误 MD-60 / MD-03 / MD-16 / MD-29（可执行判定）。

权威来源
--------
- `MIDAS_API_Online_Manual_勘误与补全_v1.0.md`（62 条 MD 逐条说明）。
- 外部项目 `Dennis5882/MIDAS-API-NX-SDK` 的 `contracts/endpoints/*.yaml`：
  `db-spfc.yaml`（MD-60）· `db-matl-m1.yaml`（MD-03）· `db-mvhl.yaml`（MD-16）·
  `design-rc-kds-41-20-2022-rebb.yaml`（MD-29）。

本文件的**可执行判定**
--------------------
1. **MD-60（`/db/SPFC`）**：手册的 EURO2004 表把 `SPECTYPE`/`GROUTYPE`/`NATIONALANNEX`
   放在 **`OPT`**，服务端 `/info` 把它们声明在 **`STR`** ⇒ 本 Schema 从 `/info`
   （`STR` 有、`OPT` 无）。
   ⚠️ 手册把同一字段拼成 `LARGEBRIDEGE`（描述也拼成 `LargeBridege`）而 `/info` 拼 `LARGEBRIDGE`
   —— 按 **R117「反向缺口一律不动」**，手册的拼写**保留**并互相加注，**不删**。
2. **MD-03（`/db/MATL-M1`）**：它与 `/db/MATL` **不共用 wire key** —— 我方已是 `-M1` 自己的
   `MATL_NAME`/`MATL_TYPE`/`PARAM`/`DAMP_RAT`；且 `PARAM[].P_TYPE` 在本端点是 **0-based**
   （`/db/MATL` 是 1-based）。⇒ 已正确，**不改数据**。
3. **MD-16（`/db/MVHL`）**：`VEHICLE_LOAD_NUM` 是**分支判别子**（1 标准 / 2 用户定义）；
   `VEHICLE_TYPE_NAME` **只在分支 1 必填**（`if/then` 表达）；手册标 Required 的 `STANDARD_CODE`
   实测**两个分支都不需要**；`USER_LOAD_TYPE` 在 `MVLD_CODE = 2` 下**不是输入**。
4. **MD-29（`/DESIGN/RC/KDS-41-20-2022/REBB`）**：该节的 **JSON Schema / Parameters 表**与
   **它自己的三个示例**描述不同 payload，且该节有一处 callout **明说以示例为准** ⇒
   按**示例**（`vMAIN_BAR_*` 数组 + `MAIN_BAR_DC_*` + 三个 `bSAME_SIZE_*`），
   **不**按表（`MAIN_BAR_TOP`/`MAIN_BAR_BOT` 对象 + `DT`/`DB`）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录。"""

MANIFEST_PATH = REPO_ROOT / "registry" / "manifest.json"
"""端点清单（YAML 的派生物）。"""

SPFC_EURO_FIELDS: tuple[str, ...] = ("SPECTYPE", "GROUTYPE", "NATIONALANNEX")
"""MD-60：手册放在 `OPT`、服务端 `/info` 声明在 `STR` 的三个 EURO2004 字段。"""

DESIGN_REBB_ITEM_KEYS: tuple[str, ...] = (
    "BAR_SECTOR_I",
    "BAR_SECTOR_J",
    "BAR_SECTOR_M",
    "CREATE_SUB_SECTION",
    "ELEMS",
    "ID",
    "MAIN_BAR_DC_BOT",
    "MAIN_BAR_DC_TOP",
    "bSAME_SIZE_IMJ",
    "bSAME_SIZE_LAYER",
    "bSAME_SIZE_TOP_BOT",
)
"""MD-29：按**示例**的条目字段集（11 个）。手册的表给的是另一套（含 `DT`/`DB`）。"""

DESIGN_REBB_TABLE_ONLY: tuple[str, ...] = ("MAIN_BAR_TOP", "MAIN_BAR_BOT", "DT", "DB", "SKIN_BAR")
"""MD-29：**只**出现在手册表里的名字 —— 示例里没有，**不得**出现在 Schema 里。"""


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _entry(key: str) -> dict:
    for item in _manifest()["endpoints"]:
        if item["key"] == key:
            return item
    raise AssertionError(f"{key} not in registry/manifest.json")


def _schema(key: str) -> dict:
    relative = str(_entry(key)["schema"])
    assert relative, f"{key} 没有 Schema 文件"
    return json.loads((REPO_ROOT / "registry" / relative).read_text(encoding="utf-8"))


def _top_props(key: str, code: str) -> dict:
    """`schema.<code>.properties`（`CODEKEY_JSONSCHEMA_FLAT` 形态）。"""
    return _schema(key)["schema"][code]["properties"]


def _map_item(key: str) -> dict:
    """取 `Assign` 键控映射的**单条记录** schema。

    各端点 Schema 的根形态**不统一**（`Assign.patternProperties` / `Assign.additionalProperties` /
    裸 `properties.Assign` / 直接 `properties`），故按结构查找而非写死路径。
    """
    root = _schema(key)["schema"]
    if "properties" not in root:
        raise AssertionError(f"{key}: 无 properties")
    wrapper = root["properties"].get("Assign")
    if isinstance(wrapper, dict):
        pp = wrapper.get("patternProperties")
        if isinstance(pp, dict) and pp:
            inner = next(iter(pp.values()))
        else:
            inner = wrapper.get("additionalProperties")
        if isinstance(inner, dict) and "properties" in inner:
            return inner
    return root


def _items_array_item(key: str) -> dict:
    """取「记录里有一个 `ITEMS` 数组」的端点其**数组条目** schema。"""
    record = _map_item(key)
    return record["properties"]["ITEMS"]["items"]


# ===== 1. MD-60：/db/SPFC =====


def test_p164_md60_the_euro2004_fields_are_in_str_not_opt() -> None:
    """门槛（判定 1）：EURO2004 三字段在 **`STR`**（服务端 `/info`），
    **不在** `OPT`（手册的表）。"""
    document = _schema("DB.SPFC")["schema"]["SPFC"]["properties"]
    str_props = document["STR"]["properties"]
    opt_props = document["OPT"]["properties"]
    for field in SPFC_EURO_FIELDS:
        assert field in str_props, ("STR 缺", field)
        assert str_props[field]["type"] == "string", field
        assert field not in opt_props, ("OPT 不该有", field)


def test_p164_md60_the_manuals_misspelling_is_kept_with_a_note() -> None:
    """门槛（判定 1）：手册的拼写 `LARGEBRIDEGE` **保留**（R117 反向缺口一律不动）且互相加注。

    ⚠️ 本用例是一次**自我纠正**的记录：初版把 `OPT.LARGEBRIDEGE` 当成我方转写笔误删掉了，
    核对后发现该拼写**确实出自官方手册**（`MIDAS_API_Online_Manual_*` 四处），
    而 R117 明令「手册声明而本 build 自省没有的字段**不删**、**不改名**」⇒ 已恢复。
    """
    opt = _top_props("DB.SPFC", "SPFC")["OPT"]["properties"]
    assert "LARGEBRIDGE" in opt, "服务端 /info 的拼写必须在"
    assert "LARGEBRIDEGE" in opt, "手册的拼写必须保留（R117）"
    assert "LARGEBRIDEGE" in opt["LARGEBRIDGE"]["description"], "两个拼写应互相指认"
    assert "LARGEBRIDGE" in opt["LARGEBRIDEGE"]["description"]


def test_p164_md60_the_str_note_records_the_unusable_branch() -> None:
    """门槛（判定 1）：`STR` 的说明记下「EURO2004 的 body 在两个产品上都被拒、无可用请求」。"""
    note = _top_props("DB.SPFC", "SPFC")["STR"]["description"]
    assert "MD-60" in note
    assert "Unknown Error" in note


# ===== 2. MD-03：/db/MATL-M1 不共用 /db/MATL 的 wire key =====


def test_p164_md03_matl_m1_has_its_own_wire_keys() -> None:
    """门槛（判定 2）：`/db/MATL-M1` 用 `MATL_NAME`/`MATL_TYPE`，
    **不**用 `/db/MATL` 的 `NAME`/`TYPE`。"""
    item = _map_item("DB.MATL-M1")
    keys = set(item["properties"])
    assert keys == {"MATL_NAME", "MATL_TYPE", "PARAM", "DAMP_RAT"}, keys
    # `/db/MATL` 的顶层名与 Hyper-S 专属字段都**不得**出现在这里
    for wrong in ("NAME", "TYPE", "HE_COND", "HE_SPEC", "PLMT", "P_NAME", "bMASS_DENS"):
        assert wrong not in keys, wrong


def test_p164_md03_p_type_is_zero_based_here() -> None:
    """门槛（判定 2）：`PARAM[].P_TYPE` 在本端点是 **0-based**（`/db/MATL` 是 1-based）。"""
    ptype = _map_item("DB.MATL-M1")["properties"]["PARAM"]["items"]["properties"]["P_TYPE"]
    assert ptype["type"] == "integer"
    assert ptype["enum"] == [0, 1, 2], ptype.get("enum")


# ===== 3. MD-16：/db/MVHL 的分支必填性 =====


def test_p164_md16_the_missing_field_from_info_is_present() -> None:
    """门槛（判定 3）：`LOAD_ITEMS[].POINT_DIST2`（`/info` 声明、我方原先缺）。"""
    items = _top_props("DB.MVHL", "MVHL")["LOAD_ITEMS"]["items"]["properties"]
    assert "POINT_DIST2" in items
    assert items["POINT_DIST2"]["type"] == "number"


def test_p164_md16_vehicle_load_num_is_the_branch_discriminator() -> None:
    """门槛（判定 3）：`VEHICLE_LOAD_NUM` 有 `enum: [1, 2]` 且说明记下它是分支判别子。"""
    field = _top_props("DB.MVHL", "MVHL")["VEHICLE_LOAD_NUM"]
    assert field["enum"] == [1, 2]
    assert "分支判别子" in field["description"]
    assert "MD-16" in field["description"]


def test_p164_md16_vehicle_type_name_is_conditionally_required() -> None:
    """门槛（判定 3）：`VEHICLE_TYPE_NAME` **只在 `VEHICLE_LOAD_NUM = 1` 时必填**（`if/then`）。"""
    mvhl = _schema("DB.MVHL")["schema"]["MVHL"]
    branches = [
        b
        for b in (mvhl.get("allOf") or [])
        if "then" in b and "VEHICLE_TYPE_NAME" in (b["then"].get("required") or [])
    ]
    assert len(branches) == 1, mvhl.get("allOf")
    cond = branches[0]["if"]
    assert cond["properties"]["VEHICLE_LOAD_NUM"]["const"] == 1
    assert cond.get("required") == ["VEHICLE_LOAD_NUM"]


def test_p164_md16_the_two_documented_required_fields_are_not_gated() -> None:
    """门槛（判定 3）：手册标 Required 的 `STANDARD_CODE` / `USER_LOAD_TYPE` **不**做成闸门。

    实测：`STANDARD_CODE` 两个分支都不需要（省略后照样落库）；`USER_LOAD_TYPE` 在
    `MVLD_CODE = 2` 下根本不是输入。两者**只加注**，不进 `required` —— 与 `PRES.DIRECTION`
    不同：那里契约给的是 `reject_request`，这里没有。
    """
    mvhl = _schema("DB.MVHL")["schema"]["MVHL"]
    required_anywhere = set(mvhl.get("required") or [])
    for branch in mvhl.get("allOf") or []:
        required_anywhere |= set((branch.get("then") or {}).get("required") or [])
    assert "STANDARD_CODE" not in required_anywhere
    assert "USER_LOAD_TYPE" not in required_anywhere
    props = mvhl["properties"]
    assert "MD-16" in props["STANDARD_CODE"]["description"]
    assert "MD-16" in props["USER_LOAD_TYPE"]["description"]


# ===== 4. MD-29：/DESIGN/RC/KDS-41-20-2022/REBB 按示例 =====


def test_p164_md29_the_item_follows_the_sections_own_examples() -> None:
    """门槛（判定 4）：条目字段集 = 该节**示例**的 11 个成员。"""
    item = _items_array_item("DESIGN.RC.KDS-41-20-2022.REBB")
    assert tuple(sorted(item["properties"])) == tuple(sorted(DESIGN_REBB_ITEM_KEYS))
    assert tuple(sorted(item.get("required") or [])) == (
        "BAR_SECTOR_I",
        "BAR_SECTOR_J",
        "BAR_SECTOR_M",
        "MAIN_BAR_DC_BOT",
        "MAIN_BAR_DC_TOP",
    )


@pytest.mark.parametrize("wrong", DESIGN_REBB_TABLE_ONLY)
def test_p164_md29_the_table_only_names_are_gone(wrong: str) -> None:
    """门槛（判定 4）：**只**出现在手册表里的名字
    （`MAIN_BAR_TOP` / `DT` / `DB` / `SKIN_BAR`）不得在。"""
    raw = json.dumps(_items_array_item("DESIGN.RC.KDS-41-20-2022.REBB"), ensure_ascii=False)
    assert f'"{wrong}"' not in raw, wrong


def test_p164_md29_the_bar_sectors_carry_array_main_bars() -> None:
    """门槛（判定 4）：`BAR_SECTOR_*` 用 `vMAIN_BAR_TOP`/`vMAIN_BAR_BOT` **数组**
    + 扁平 `SKIN_BAR_*`。"""
    props = _items_array_item("DESIGN.RC.KDS-41-20-2022.REBB")["properties"]
    for sector in ("BAR_SECTOR_I", "BAR_SECTOR_J", "BAR_SECTOR_M"):
        sub = props[sector]
        assert tuple(sorted(sub["properties"])) == (
            "SHEAR_BAR",
            "SKIN_BAR_NAME",
            "SKIN_BAR_NUM",
            "vMAIN_BAR_BOT",
            "vMAIN_BAR_TOP",
        ), sector
        assert tuple(sorted(sub.get("required") or [])) == (
            "SHEAR_BAR",
            "vMAIN_BAR_BOT",
            "vMAIN_BAR_TOP",
        ), sector
        for arr in ("vMAIN_BAR_TOP", "vMAIN_BAR_BOT"):
            assert sub["properties"][arr]["type"] == "array", (sector, arr)
            assert tuple(sorted(sub["properties"][arr]["items"]["properties"])) == ("NAME", "NUM")
        assert tuple(sorted(sub["properties"]["SHEAR_BAR"]["properties"])) == (
            "DIST",
            "LEG",
            "NAME",
        )
        assert sub["properties"]["SKIN_BAR_NAME"]["type"] == "string"
        assert sub["properties"]["SKIN_BAR_NUM"]["type"] == "integer"


def test_p164_md29_the_three_same_size_flags_are_present() -> None:
    """门槛（判定 4）：三个 `bSAME_SIZE_*` 布尔 —— 手册的表**一个都没列**，示例里有。"""
    props = _items_array_item("DESIGN.RC.KDS-41-20-2022.REBB")["properties"]
    for flag in ("bSAME_SIZE_TOP_BOT", "bSAME_SIZE_IMJ", "bSAME_SIZE_LAYER"):
        assert props[flag]["type"] == "boolean", flag


def test_p164_md29_the_design_sibling_stays_gen_only() -> None:
    """门槛（判定 4）：该 DESIGN 端点仍为 `GEN_NX` 专属（第一/二批的 `products` 更正）。"""
    assert _entry("DESIGN.RC.KDS-41-20-2022.REBB")["products"] == ["GEN_NX"]
