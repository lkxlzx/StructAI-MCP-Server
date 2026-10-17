"""P179 / **R172 + R173**：留缺收口 + 参数化模型的**稳定序列化**（**零请求**）。

为什么需要它
------------
**R172**：P178 留下 **10** 条 `left_open`。P179 用**本仓可读**证据逐条推到底 ——
能复算的收口（钢筋规格 / `OPE.LINEBMLD::TYPE` / `PARTS`），不能的写清机械原因。
本文件把**收口结论**钉成判定，防止下一个会话把「已收口」当「仍留缺」再查一遍。

**R173**：参数化建模需要把 `ModelDocument` **落盘 / 传输 / 版本化**。没有固定格式时，
每个调用方各写一份 JSON ⇒ 同一模型两种表示，无法比较、无法回归。本文件钉住：

| # | 事实 | 为什么必须机器可读 |
| --- | --- | --- |
| 1 | **序列化逐字节稳定** | 不稳定 ⇒ 无法 diff / 无法做回归基线 |
| 2 | **格式/版本严格校验** | 静默降级会把不兼容的数据当兼容处理 |
| 3 | **往返无损** | canonical 视图漏字段时，回写会**悄悄丢数据** |
| 4 | **枚举只增不减** | 补枚举时丢掉既有取值 = 把闸门**放松**成另一种错 |

⚠️ **本批不改主指标**：仍 `71 / 73`（这些端点都不在 OperationPlan 的生产路径上）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

import pytest

from app.infrastructure.adapters.midas.model_document import (
    MODEL_DOCUMENT_FORMAT,
    MODEL_DOCUMENT_VERSION,
    ModelDocument,
    canonical_to_native,
    from_json,
    native_to_canonical,
    to_json,
)
from app.infrastructure.adapters.midas.registry import MidasRegistry
from app.infrastructure.adapters.midas.spec_guard import check_spec_values

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
REGISTRY_ROOT: Final[Path] = REPO_ROOT / "registry"
AUDIT: Final[Path] = REGISTRY_ROOT / "live" / "spec_enum_audit.json"

REBAR_ENDPOINTS: Final[tuple[str, ...]] = (
    "DESIGN.RC.KDS-41-20-2022.DCRE",
    "DESIGN.RC.KDS-41-20-2022.DCRM-WALL",
    "DESIGN.RC.KDS-41-20-2022.REBC",
    "DESIGN.RC.KDS-41-20-2022.REBR",
    "DESIGN.RC.KDS-41-20-2022.REBW",
)
"""R172 收口的 5 个钢筋规格端点。"""

REBAR_DIAMETERS: Final[frozenset[str]] = frozenset(
    {"D4", "D5", "D6", "D7", "D8", "D10", "D13", "D16", "D19", "D22", "D25", "D32", "D41"}
)
"""**可复算**的直径集合 = 已落盘 `D4`~`D8` ∪ 手册示例体出现过的 8 个。

⚠️ **不含** `D9` / `D11` / … / `D57` —— 它们在任何来源里都**没出现过**，
    闸门拦它们是**有意的**取舍（`description` 说 19 种，但手册无完整表）。
"""


def _registry() -> MidasRegistry:
    return MidasRegistry.load(str(REGISTRY_ROOT))


def _audit() -> dict[str, Any]:
    return json.loads(AUDIT.read_text(encoding="utf-8"))


# ===== R172：留缺收口 =====


def test_p179_rebar_enums_cover_every_manual_example_value() -> None:
    """门槛：5 个钢筋规格端点的手册示例取值**全部**在枚举里（否则合法调用被拦死）。"""
    registry = _registry()
    examples = {
        "DESIGN.RC.KDS-41-20-2022.DCRE": {
            "Assign": {"1": {"BEAM": {"MAIN_REBAR": ["D22"], "STIRRUPS": "D10", "SIDE_BAR": "D13"}}}
        },
        "DESIGN.RC.KDS-41-20-2022.DCRM-WALL": {
            "Assign": {
                "3": {
                    "ITEMS": [
                        {"VERTICAL_REBAR": "D22", "HORIZONTAL_REBAR": "D32", "BE_HORZ_REBAR": "D13"}
                    ]
                }
            }
        },
        "DESIGN.RC.KDS-41-20-2022.REBC": {
            "Assign": {
                "1": {
                    "ITEMS": [
                        {
                            "MAIN_BAR": {"NAME": "D19"},
                            "SHEAR_BAR_END": {"NAME": "D10"},
                            "SHEAR_BAR_CEN": {"NAME": "D10"},
                            "HOOP_TYPE": "Ties",
                        }
                    ]
                }
            }
        },
        "DESIGN.RC.KDS-41-20-2022.REBR": {
            "Assign": {
                "1": {
                    "ITEMS": [
                        {
                            "MAIN_BAR": {"NAME": "D22"},
                            "SHEAR_BAR_CEN": {"NAME": "D22"},
                            "HOOP_TYPE": "Spirals",
                        }
                    ]
                }
            }
        },
        "DESIGN.RC.KDS-41-20-2022.REBW": {
            "Assign": {
                "1": {
                    "ITEMS": [
                        {
                            "VERTICAL_REBAR": {"NAME": "D19"},
                            "HORIZONTAL_REBAR": {"NAME": "D16"},
                            "BE_HORIZONTAL_REBAR": {"NAME": "D19"},
                            "END_REBAR": {"NAME": "D25"},
                        }
                    ]
                }
            }
        },
    }
    for endpoint, body in examples.items():
        problems = check_spec_values(registry.effective_schema(endpoint), body, endpoint=endpoint)
        assert not problems, (endpoint, problems)


def test_p179_rebar_enums_still_block_bogus_values() -> None:
    """阴性对照：伪值 `D999` / `NONSENSE` 仍**必须**被拦（补枚举**没有**放松闸门）。"""
    registry = _registry()
    cases = {
        "DESIGN.RC.KDS-41-20-2022.DCRE": {"Assign": {"1": {"BEAM": {"MAIN_REBAR": ["D999"]}}}},
        "DESIGN.RC.KDS-41-20-2022.DCRM-WALL": {
            "Assign": {"3": {"ITEMS": [{"VERTICAL_REBAR": "D999"}]}}
        },
        "DESIGN.RC.KDS-41-20-2022.REBC": {
            "Assign": {"1": {"ITEMS": [{"MAIN_BAR": {"NAME": "D999"}}]}}
        },
        "DESIGN.RC.KDS-41-20-2022.REBR": {
            "Assign": {"1": {"ITEMS": [{"MAIN_BAR": {"NAME": "NONSENSE"}}]}}
        },
        "DESIGN.RC.KDS-41-20-2022.REBW": {
            "Assign": {"1": {"ITEMS": [{"VERTICAL_REBAR": {"NAME": "D999"}}]}}
        },
    }
    for endpoint, body in cases.items():
        problems = check_spec_values(registry.effective_schema(endpoint), body, endpoint=endpoint)
        assert problems, f"{endpoint}: 伪值居然被放行（闸门被放松）"


def test_p179_rebar_enums_are_exactly_the_computable_set() -> None:
    """门槛：5 个端点的**每一个**钢筋枚举 ⊇ 已落盘 `D4`~`D8`，且 ⊆ 可复算集合。

    ⚠️ **不要求端点之间相等** —— 每个端点只并入了**它自己**手册示例里出现过的直径
    （`DCRE` 有 `D10`/`D13`，`REBW` 有 `D16`/`D19`/`D25`，两者不同是**正确的**）。
    跨端点取并集会把「本端点没出现过的取值」塞进来，那是**发明**。
    """
    baseline = {"D4", "D5", "D6", "D7", "D8"}

    def rebar_enums(node: Any) -> list[list[str]]:
        """收集**全部**钢筋规格枚举节点（取值形如 `D<数字>`）。"""
        found: list[list[str]] = []
        if isinstance(node, dict):
            values = node.get("enum")
            if (
                isinstance(values, list)
                and values
                and all(isinstance(item, str) and item.startswith("D") for item in values)
            ):
                found.append(values)
            for value in node.values():
                found.extend(rebar_enums(value))
        elif isinstance(node, list):
            for item in node:
                found.extend(rebar_enums(item))
        return found

    for endpoint in REBAR_ENDPOINTS:
        document = json.loads(
            (
                REGISTRY_ROOT
                / "schema"
                / "design"
                / "rc"
                / "KDS-41-20-2022"
                / f"{endpoint.rsplit('.', 1)[-1]}.json"
            ).read_text(encoding="utf-8")
        )
        found = rebar_enums(document.get("schema"))
        assert found, endpoint
        for values in found:
            actual = set(values)
            assert baseline <= actual, (endpoint, "丢了已落盘取值", sorted(baseline - actual))
            assert actual <= REBAR_DIAMETERS, (
                endpoint,
                "含不可复算取值",
                sorted(actual - REBAR_DIAMETERS),
            )


def test_p179_linebmld_type_enum_is_the_manual_spec_table() -> None:
    """门槛：`OPE.LINEBMLD::TYPE` == 手册规格表第 3 行的 **9** 个取值。"""
    registry = _registry()
    expected = [
        "CONLOAD",
        "CONMOMENT",
        "UNILOAD",
        "UNIMOMENT",
        "TRALOAD",
        "TRAMOMENT",
        "UNIPRESSURE",
        "TRAPRESSURE",
        "CURVED",
    ]
    for value in expected:
        body = {"Argument": {"LCNAME": "LC1", "TYPE": value, "TARGET": {"METHOD": 0}}}
        problems = check_spec_values(
            registry.effective_schema("OPE.LINEBMLD"), body, endpoint="OPE.LINEBMLD"
        )
        assert not problems, (value, problems)
    bogus = {"Argument": {"LCNAME": "LC1", "TYPE": "BOGUS", "TARGET": {"METHOD": 0}}}
    assert check_spec_values(
        registry.effective_schema("OPE.LINEBMLD"), bogus, endpoint="OPE.LINEBMLD"
    ), "伪 TYPE 居然被放行"


def test_p179_the_ledger_shrank_and_every_remaining_item_is_type_conflict() -> None:
    """门槛：`left_open` 从 **10 → 4**，且**每一条**都写清了「向谁问什么」。

    ⚠️ 剩 4 条的**共同特征**：都是**类型冲突**或**自由引用名** —— 即
    「不是不知道取值，而是不知道**类型**」，这类只能由产品侧答复或真机测量裁决。
    """
    document = _audit()
    open_items = [item for item in document["dispositions"] if item["status"] == "left_open"]
    assert len(open_items) == 4, [item["key"] for item in open_items]
    keys = {item["key"] for item in open_items}
    assert keys == {
        "DB.REBR::HOOP_TYPE",
        "DESIGN.RC.KDS-41-20-2022.DCRE::SPLICED_BARS",
        "OPE.GSBG::BRDG_GROUP",
        "OPE.LCOM-GEN::DGNCODE",
    }, keys
    for item in open_items:
        assert item.get("ask"), f"{item['key']}: 留缺必须写清「向谁问什么」"


def test_p179_closed_items_are_not_regressed() -> None:
    """门槛：**每一个** `closed` 项的收口依据仍成立（生成器或实测证据）。"""
    document = _audit()
    closed = [item for item in document["dispositions"] if item["status"] == "closed"]
    assert len(closed) == 22, len(closed)
    regressed = [item["key"] for item in closed if not item.get("generator_agrees")]
    assert not regressed, regressed


# ===== R173：稳定序列化 =====


def _sample_document() -> ModelDocument:
    return ModelDocument(
        entities={
            "NODE": ({"id": 2, "x": 1.0}, {"id": 1, "x": 0.0}),
            "MATL": ({"id": 1, "name": "Q355"},),
        },
        native={},
        units={"force": "KN"},
    )


def test_p179_serialization_is_byte_stable() -> None:
    """门槛：同一模型**两次**序列化逐字节相同（不依赖 dict 插入顺序）。"""
    document = _sample_document()
    assert to_json(document) == to_json(document)
    # 打乱插入顺序后仍然相同（口径 2：按表名 / id 升序）
    shuffled = ModelDocument(
        entities={
            "MATL": ({"id": 1, "name": "Q355"},),
            "NODE": ({"id": 1, "x": 0.0}, {"id": 2, "x": 1.0}),
        },
        native={},
        units={"force": "KN"},
    )
    assert to_json(document) == to_json(shuffled)


def test_p179_serialization_roundtrip_is_lossless_for_entities() -> None:
    """门槛：`to_json` → `from_json` 往返后实体与单位**逐条相同**。

    ⚠️ 往返会按 **id 升序**规范化（口径 2）⇒ 比较前先对原文档做同样的排序。
    """
    document = _sample_document()
    restored = from_json(to_json(document))
    expected = {
        table: tuple(sorted(rows, key=lambda row: row["id"]))
        for table, rows in document.entities.items()
    }
    assert dict(restored.entities) == expected
    assert dict(restored.units) == dict(document.units)


def test_p179_serialization_rejects_unknown_format_or_version() -> None:
    """门槛：格式 / 版本不认识 ⇒ **报错**（不静默降级）。"""
    with pytest.raises(ValueError):
        from_json(json.dumps({"format": "something-else", "version": 1, "tables": {}}))
    with pytest.raises(ValueError):
        from_json(json.dumps({"format": MODEL_DOCUMENT_FORMAT, "version": 999, "tables": {}}))


def test_p179_serialization_header_is_explicit() -> None:
    """门槛：序列化结果**显式**带格式标识与版本（可被外部工具识别）。"""
    payload = json.loads(to_json(_sample_document()))
    assert payload["format"] == MODEL_DOCUMENT_FORMAT
    assert payload["version"] == MODEL_DOCUMENT_VERSION
    assert list(payload) == ["format", "version", "units", "tables"]


def test_p179_native_roundtrip_is_lossless_on_real_exports() -> None:
    """门槛：**真实导出样本**上 `native → canonical → native` 无损（R168 的判据保持）。"""
    samples = sorted((REPO_ROOT / ".tmp_p175").glob("*.json"))
    usable = []
    for path in samples:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and "DBG" in payload:
            usable.append((path, payload))
    if not usable:
        pytest.skip("没有可用的导出样本（.tmp_p175/*.json 为空或缺失）")

    registry = _registry()
    for path, payload in usable:
        document = native_to_canonical(payload, registry)
        restored = canonical_to_native(document, registry)
        assert json.dumps(restored, sort_keys=True) == json.dumps(payload, sort_keys=True), (
            path.name
        )
