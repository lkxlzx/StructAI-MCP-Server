"""P160d / R148：`VIEW.*` 各步**各有参数通道**（三步形状不同，**不**能共用一份 arguments）。

⚠️ **实测事故（P160d）**：`VIEW.*` 的两三步原先共用 `parameters["arguments"]`，而三步形状不同：

| 步 | 体 | 转换器 |
| --- | --- | --- |
| `VIEW.DISPLAY` | **原生键**（`{"ELEMENT": {"ELEM_NUMBER": true}}`） | **无** |
| `VIEW.RESULTGRAPHIC` | **原生键**（`CURRENT_MODE` / `LOAD_CASE_COMB` …） | **无** |
| `VIEW.CAPTURE` | **canonical 键**（`export_path` …） | **有**（白名单） |

⇒ 传**并集** ⇒ 转换器白名单**拒**（`transformer_field_not_in_schema`）；
传**子集** ⇒ `VIEW.DISPLAY` **`400`**
⇒ 7 个 `VIEW.*` Operation **全部不可用**。按 **R141 的先例**拆成各自的通道。

⚠️ 另两条**实测取值**（手册示例**不**适用）：

* `SET_MODE`：手册示例 `"post"` ⇒ **`400`**「Post Mode is not available」（**需要分析结果**）；
  `"pre"` / `"PRE"` / **省略** ⇒ `200`；`"model"` ⇒ `400`。
* `FIGURE_NAME`：**只能**引用**已存在**的图形名 —— 任意标签 ⇒ **`400`**
  「It's not found Figure Name」。
"""

from __future__ import annotations

from app.infrastructure.adapters.midas.adapter import VIEW_ARGUMENT_CHANNELS
from app.infrastructure.adapters.midas.operations import plan_for
from app.infrastructure.adapters.midas.transforms import TRANSFORMER_REGISTRY, ViewTransformer


def test_p160d_r148_each_view_step_has_its_own_argument_channel() -> None:
    """门槛（**R148 的钉子**）：三步各有通道，且**不**共用 `arguments`。"""
    assert VIEW_ARGUMENT_CHANNELS == {
        "view_display": "display",
        "view_result": "result_graphic",
        "view_capture": "capture",
    }
    assert "view" not in VIEW_ARGUMENT_CHANNELS


def test_p160d_r148_the_view_plans_use_the_three_distinct_intents() -> None:
    """门槛：7 个 `VIEW.*` Operation 的步**只用**这三个意图（**不**再有共用的 `view`）。"""
    seen: set[str] = set()
    for name in (
        "VIEW.MODEL",
        "VIEW.DEFORMED_MODEL",
        "VIEW.DISPLACEMENT",
        "VIEW.FORCE",
        "VIEW.REACTION",
        "VIEW.STRESS",
        "VIEW.MODE_SHAPE",
    ):
        plan = plan_for(name)
        for step in plan.steps:
            seen.add(step.intent)
            if step.key == "VIEW.CAPTURE":
                assert step.transformer == "midas.view.capture.v1", step
            else:
                assert step.transformer is None, step
    assert seen == {"view_display", "view_result", "view_capture"}, seen


def test_p160d_the_capture_transformer_carries_the_manual_example_fields() -> None:
    """门槛：`ViewTransformer` 覆盖手册示例的**全部**字段（缺 `SET_MODE` 等会 `400`）。"""
    canonical = {field.canonical for field in ViewTransformer.fields}
    assert {
        "figure_name",
        "export_path",
        "width",
        "height",
        "set_mode",
        "set_hidden",
        "stage_name",
        "display",
        "result_graphic",
        "active",
        "angle",
    } <= canonical, canonical
    assert TRANSFORMER_REGISTRY["midas.view.capture.v1"] is ViewTransformer
