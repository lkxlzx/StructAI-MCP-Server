"""P158 / R130：`ITEMS` 形态端点的**读回**必须逐元素展开（`adapter._items_of`）。

⚠️ **事故形态（P157 定位、P158 修复）**：`DB.CONS` / `DB.CNLD` / `DB.BMLD` / `DB.PRES`
读回来是 `{<编号>: {"ITEMS": [<条目>, …]}}`；原先 `_items_of` 把**外层 `ITEMS` 包装体**
当成条目 ⇒ Transformer 在包装体这一层找不到 `ID` / `CONSTRAINT` / `LCNAME` …
⇒ canonical 取值**全 `None`**（只剩由**编号键**补的 `id`）。

**真机实测（P158）**：修后 `MODEL.BOUNDARY.QUERY` 读回
`{"id": "1", "node_id": 1, "group_name": "", "ux": true, …, "rw": false}` —— 7 个自由度全在。
"""

from __future__ import annotations

from app.infrastructure.adapters.midas.adapter import _items_of


def test_p158_r130_the_items_wrapper_is_unwrapped_to_its_elements() -> None:
    """门槛：`{<编号>: {"ITEMS": [<条目>]}}` ⇒ 条目**本身**（**不**是包装体）。"""
    payload = {"1": {"ITEMS": [{"ID": 1, "GROUP_NAME": "", "CONSTRAINT": "1111110"}]}}
    assert _items_of(payload) == [("1", {"ID": 1, "GROUP_NAME": "", "CONSTRAINT": "1111110"})]


def test_p158_r130_one_key_may_hold_several_items() -> None:
    """门槛：一个编号键下多条 ⇒ **逐条**展开（编号仍作兜底 `id`）。"""
    payload = {"2": {"ITEMS": [{"FZ": -1.0, "ID": 2}, {"FZ": -2.0, "ID": 3}]}}
    assert _items_of(payload) == [("2", {"FZ": -1.0, "ID": 2}), ("2", {"FZ": -2.0, "ID": 3})]


def test_p158_r130_plain_numbered_mappings_are_unchanged() -> None:
    """门槛（**不**能改坏）：普通编号映射（`DB.NODE` 形态）仍**整体**一条。"""
    assert _items_of({"1": {"X": 0.0}, "2": {"X": 1.0}}) == [
        ("1", {"X": 0.0}),
        ("2", {"X": 1.0}),
    ]


def test_p158_r130_top_level_items_and_single_object_are_unchanged() -> None:
    """门槛（**不**能改坏）：顶层 `ITEMS` 数组与单对象两种形态保持原样。"""
    assert _items_of({"ITEMS": [{"A": 1}]}) == [(None, {"A": 1})]
    assert _items_of({"X": 1.0}) == [(None, {"X": 1.0})]
    assert _items_of([]) == []
