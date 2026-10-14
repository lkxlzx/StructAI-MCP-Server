"""NXSDK 外部证据裁决（第二批）—— `/db/REB*` 家族形状与 `/db/PRES` 必填性（可执行判定）。

权威来源
--------
- `docs/nxsdk_review/00_评估与查漏补缺报告_v1.0.md` · `MIDAS_API_Online_Manual_勘误与补全_v1.0.md`。
- 外部项目 `Dennis5882/MIDAS-API-NX-SDK`：`contracts/endpoints/db-reb*.yaml`（**已复核契约**，
  与 `GET /info` 在四个端点上**逐路径一致**：45/45 · 22/22 · 17/17 · 20/20）·
  `docs/live_verification_notes.md` 的实测发现 **A-01**（`/db/REBW`，含 `PUT` 往返）·
  **A-02**（`/db/REBC`，POST 形状被拒 / 数组被接受）· **A-03**（`/db/REBB`，多种载荷全被拒）·
  **A-04**（`/db/REBR`，长键被拒、短键到达域检查）。

本文件的**可执行判定**
--------------------
1. **`/db/REB*` 家族按原生短键重建**：四个端点的 `ITEMS` 条目字段集与 `GET /info` **逐路径一致**，
   且手册的长名**一个都不在**。
2. **`/db/PRES` 的 `DIRECTION` 必须显式给出**（MD-17）：`required` 含它，
   `enum` 为服务端承认的八个值，且**没有** `default` —— 省略会让服务端套用手册的默认值 `"NORMAL"`，
   而该值在 `PLATE`+`FACE` 上被拒（「省略」与「填 NORMAL」**同样失败**）。
3. **`VECTORS` 恰好 3 个分量**；`EDGE_FACE` 有 `minimum`/`maximum`。
4. **不改的**：`/db/REBW` 的 `vSTORY_NAME` 是**字符串数组**（不是 `{FROM,TO}` 范围）；
   `/db/REBB` 的 `ID` 必填但写路径**从未成功**（不得据此声称可用）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录。"""

MANIFEST_PATH = REPO_ROOT / "registry" / "manifest.json"
"""端点清单（YAML 的派生物）。"""

REB_ITEM_KEYS: dict[str, tuple[str, ...]] = {
    "DB.REBB": (
        "BAR_SECTOR_I",
        "BAR_SECTOR_J",
        "BAR_SECTOR_M",
        "ID",
        "MAIN_BAR_DC_BOT",
        "MAIN_BAR_DC_TOP",
        "bSAME_SIZE_IMJ",
        "bSAME_SIZE_LAYER",
        "bSAME_SIZE_TOP_BOT",
    ),
    "DB.REBC": (
        "HOOK_TYPE",
        "HOOP_TYPE",
        "ID",
        "NUM_BAR_BC_JOINT",
        "SHEAR_BAR_CEN",
        "SHEAR_BAR_END",
        "bSAME_SPACE_END_CEN",
        "vMAIN_BAR",
    ),
    "DB.REBR": ("HOOP_TYPE", "ID", "SHEAR_BAR_CEN", "SHEAR_BAR_END", "vMAIN_BAR"),
    "DB.REBW": (
        "BE_HOR_BAR",
        "BE_LENGTH",
        "DE",
        "DW",
        "END_BAR",
        "HOR_BAR",
        "ID",
        "NUM_END_BAR",
        "THICK",
        "VER_BAR",
        "bUSE_MODEL_THICK",
        "vSTORY_NAME",
    ),
}
"""四个端点的 `ITEMS` 条目字段集 —— 逐条等于 `GET /info` 的声明。"""

DOCUMENTED_WRONG_NAMES: dict[str, tuple[str, ...]] = {
    "DB.REBB": ("LAYER1", "LAYER2", "CREATE_SUB_SECTION", "ELEMS"),
    "DB.REBC": ("MAIN_BAR", "DO", "CREATE_SUB_SECTION", "ELEMS"),
    "DB.REBR": ("MAIN_BAR", "DO", "CREATE_SUB_SECTION", "ELEMS"),
    "DB.REBW": (
        "VERTICAL_REBAR",
        "HORIZONTAL_REBAR",
        "END_REBAR",
        "BE_HORIZONTAL_REBAR",
        "STORY",
        "SUB_WALL_ID",
        "CREATE_SUB_WALL_ID",
        "USE_END_REBAR",
        "USE_MODEL_THICKNESS",
        "THICKNESS",
        "BOUNDARY_ELEMENT_LENGTH",
        "CONCRETE_FACE_TO_CENTER_OF_REBAR",
    ),
}
"""手册（及官方文章）给的长名 —— 实测**一个都不被原生接受**，不得出现在 Schema 里。"""

VMAIN_BAR_MEMBERS: dict[str, tuple[str, ...]] = {
    "DB.REBC": ("NAME", "NUM", "ROW", "D0", "bUSE_CORNER", "NAME_CORNER"),
    "DB.REBR": ("NAME", "NUM", "ROW", "D0"),
}
"""`vMAIN_BAR` 的数组成员。手册把覆盖层写成**顶层 `DO`**（字母 O），
原生是**每条目内的 `D0`**（数字零）。"""

PRES_DIRECTION_ENUM: tuple[str, ...] = (
    "NORMAL",
    "LX",
    "LY",
    "LZ",
    "GX",
    "GY",
    "GZ",
    "VECTOR",
)
"""`GET /info` 承认的八个取值 —— 自造的拼写（如 `"LOCAL_Z"`）得到泛化的 `Wrong Field`。"""


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


def _reb_item(key: str) -> dict:
    """`Assign.patternProperties["^[0-9]+$"].properties.ITEMS.items`。"""
    document = _schema(key)
    assign = document["schema"]["properties"]["Assign"]
    item = next(iter(assign["patternProperties"].values()))
    return item["properties"]["ITEMS"]["items"]


# ===== 1. /db/REB* 家族按原生短键重建 =====


@pytest.mark.parametrize("key", sorted(REB_ITEM_KEYS))
def test_p162_the_reb_family_uses_the_native_short_keys(key: str) -> None:
    """门槛（判定 1）：`ITEMS` 条目字段集逐条等于 `GET /info` 的声明。"""
    item = _reb_item(key)
    assert tuple(sorted(item["properties"])) == tuple(sorted(REB_ITEM_KEYS[key])), key


@pytest.mark.parametrize("key", sorted(DOCUMENTED_WRONG_NAMES))
def test_p162_the_documented_long_names_are_gone(key: str) -> None:
    """门槛（判定 1）：手册的长名**一个都不在** —— 实测全部 `Wrong Field`。"""
    raw = json.dumps(_reb_item(key), ensure_ascii=False)
    for wrong in DOCUMENTED_WRONG_NAMES[key]:
        assert f'"{wrong}"' not in raw, (key, wrong)


@pytest.mark.parametrize("key", sorted(VMAIN_BAR_MEMBERS))
def test_p162_vmain_bar_is_an_array_and_the_cover_is_d0(key: str) -> None:
    """门槛（判定 1）：`vMAIN_BAR` 是**数组**，覆盖层是每条目内的 **`D0`**（数字零）。"""
    props = _reb_item(key)["properties"]
    vmain = props["vMAIN_BAR"]
    assert vmain["type"] == "array", key
    assert tuple(sorted(vmain["items"]["properties"])) == tuple(sorted(VMAIN_BAR_MEMBERS[key])), key
    # 顶层不得再有 `DO`（字母 O）
    assert "DO" not in props, key


def test_p162_rebb_bar_sectors_carry_the_native_sub_members() -> None:
    """门槛（判定 1）：`/db/REBB` 的三个 `BAR_SECTOR_*` 各含原生子成员（含 `vMAIN_BAR_*` 数组）。"""
    props = _reb_item("DB.REBB")["properties"]
    for sector in ("BAR_SECTOR_I", "BAR_SECTOR_J", "BAR_SECTOR_M"):
        sub = props[sector]
        assert sub["type"] == "object", sector
        assert tuple(sorted(sub["properties"])) == (
            "SHEAR_BAR",
            "SKIN_BAR_NAME",
            "SKIN_BAR_NUM",
            "vMAIN_BAR_BOT",
            "vMAIN_BAR_TOP",
        ), sector
        for arr in ("vMAIN_BAR_BOT", "vMAIN_BAR_TOP"):
            assert sub["properties"][arr]["type"] == "array", (sector, arr)
            assert tuple(sorted(sub["properties"][arr]["items"]["properties"])) == ("NAME", "NUM")
        assert tuple(sorted(sub["properties"]["SHEAR_BAR"]["properties"])) == (
            "DIST",
            "LEG",
            "NAME",
        )


def test_p162_rebw_story_is_a_string_array_not_a_range() -> None:
    """门槛（判定 4）：`/db/REBW` 的 `vSTORY_NAME` 是**字符串数组**，
    不是手册的 `{FROM, TO}` 范围。"""
    props = _reb_item("DB.REBW")["properties"]
    story = props["vSTORY_NAME"]
    assert story["type"] == "array"
    assert story["items"]["type"] == "string"
    assert "STORY" not in props
    assert "FROM" not in json.dumps(story, ensure_ascii=False)


def test_p162_rebb_id_is_present_and_the_write_path_is_not_claimed() -> None:
    """门槛（判定 4）：`ID` 在且其说明记下「省略 `ID` → `Wrong Field`」；但**不得**声称可写。

    实测（2026-08-27 / 09-03 / 09-27 / 10-04）多种载荷**全部** `Wrong Field` 或 `Unknown Error`，
    **从未观察到任何一次写入成功** —— 与 `/db/NLLP`、`/db/WVLD` 同类。
    ⚠️ `ID` **不**列入 `required`：`/info` 不声明 `required` 数组，requiredness 记为 `unstated`；
    但实测缺它会得到 `Wrong Field`，故该事实记在它的 `description` 里（口径不臆造）。
    """
    item = _reb_item("DB.REBB")
    assert "ID" in item["properties"]
    assert "Wrong Field" in item["properties"]["ID"]["description"]
    # 契约的 required 集只含 live_verified 的成员，`ID` 不在其中
    assert tuple(sorted(item.get("required") or [])) == (
        "BAR_SECTOR_I",
        "BAR_SECTOR_J",
        "BAR_SECTOR_M",
        "MAIN_BAR_DC_BOT",
        "MAIN_BAR_DC_TOP",
    )


# ===== 2. /db/PRES 的 DIRECTION 必须显式给出（MD-17）=====


def _pres_item() -> dict:
    return _schema("DB.PRES")["schema"]["PRES"]["properties"]["ITEMS"]["items"]


def test_p162_pres_direction_is_required_so_no_bad_default_can_apply() -> None:
    """门槛（判定 2）：`DIRECTION` 在 `required` 里 —— 省略即让服务端套用手册的坏默认值。"""
    item = _pres_item()
    assert "DIRECTION" in (item.get("required") or [])
    assert "LCNAME" in (item.get("required") or [])
    assert "FACE_EDGE_TYPE" in (item.get("required") or [])


def test_p162_pres_direction_has_the_server_enum_and_no_default() -> None:
    """门槛（判定 2）：`enum` = 服务端承认的八个值；**没有** `default`。"""
    direction = _pres_item()["properties"]["DIRECTION"]
    assert tuple(direction["enum"]) == PRES_DIRECTION_ENUM
    assert "default" not in direction, (
        '手册的 "NORMAL" 默认值在 PLATE+FACE 上被拒，不得记录为默认值'
    )


def test_p162_pres_vectors_is_exactly_three_and_edge_face_is_bounded() -> None:
    """门槛（判定 3）：`VECTORS` 恰好 3 个分量；`EDGE_FACE` 有 1..6 的界。"""
    props = _pres_item()["properties"]
    assert props["VECTORS"]["minItems"] == 3
    assert props["VECTORS"]["maxItems"] == 3
    assert props["EDGE_FACE"]["minimum"] == 1
    assert props["EDGE_FACE"]["maximum"] == 6


def test_p162_pres_keeps_the_eleventh_member_the_manual_omits() -> None:
    """门槛（判定 2）：`PSLT_KEY` 在 —— 手册的 Specifications 表未列它，但 `/info` 两产品均声明。"""
    assert "PSLT_KEY" in _pres_item()["properties"]


def test_p162_pres_normal_is_not_gated_out_of_a_plate_face() -> None:
    """门槛（判定 4）：`"NORMAL"` **不**被硬闸门排除。

    对方契约刻意把它做成 `kind: warn` 而非 `reject_request`：该值对另外三种
    `ELEM_TYPE`/`FACE_EDGE_TYPE` 组合是合法的，原生错误本身是显式的，
    而拒绝调用方**显式给出**的值等于替工程师做工程决策。
    """
    item = _pres_item()
    assert "NORMAL" in item["properties"]["DIRECTION"]["enum"]
    # 不得出现把 PLATE+FACE 与 NORMAL 对立起来的条件闸门
    raw = json.dumps(item, ensure_ascii=False)
    assert '"not"' not in raw and '"if"' not in raw, "不得把该排除做成硬闸门"
