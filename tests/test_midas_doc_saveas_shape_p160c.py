"""P160c / R143：`DOC.SAVEAS` / `OPEN` 的体是**路径字符串**；`SAVE` 必须"路径已确立"。

⚠️ **两次实测事故（都发生在 P160c 的真机测量里）**：

1. **字符串被拆成字符数组**：`client._wrap` 对 `Argument` 包装的**非 Mapping** 体一律
   `{"Argument": {"ITEMS": list(body)}}` —— 字符串因此被 `list()` 拆成**字符数组**。
   原生对那个垃圾体**静默 `200` 却什么都不做**（R128 同族的**假成功陷阱**）⇒ 文件**没**落盘。
2. **`SAVE` 弹出「另存为」模态窗口**：项目**仍无路径**（因为第 1 条的 `SAVEAS` 没生效），
   紧接着发 `SAVE` ⇒ 原生弹窗 ⇒ **挂起 API**（**由用户手动取消**才解除）。
   ⇒ 教训：**调用方给了路径 ≠ 项目真的有路径**；核心必须按**自己确知**的状态拦。
"""

from __future__ import annotations

import pytest
from tests import midas_p119_p126_support as support
from tests.test_midas_e2e_p125_p126 import _NO_CONTEXT

from app.domain.errors import EngineeringValidationError

MODEL_PATH = r"E:\MCP\MMCP\.tmp_p160c\p160c-model.mgbx"


async def _adapter() -> object:
    transport = support.RecordingTransport()
    adapter = support.adapter(transport=transport)
    await adapter.connect(support.connect_config())
    transport.clear()
    return adapter, transport


async def test_p160c_r143_save_as_carries_the_path_as_a_plain_string() -> None:
    """门槛（**事故 1 的钉子**）：`SAVEAS` 的体 = `{"Argument": "<路径>"}`，**不**是字符数组。"""
    adapter, transport = await _adapter()
    await adapter.execute_normalized("SAVE_AS", {"project_path": MODEL_PATH}, _NO_CONTEXT)
    body = transport.calls[-1][2]
    assert body == {"Argument": MODEL_PATH}, body
    assert not isinstance(body["Argument"], dict), body
    await adapter.disconnect()


async def test_p160c_r143_open_carries_the_path_as_a_plain_string() -> None:
    """门槛：`OPEN` 同上。"""
    adapter, transport = await _adapter()
    await adapter.execute_normalized("OPEN", {"project_path": MODEL_PATH}, _NO_CONTEXT)
    assert transport.calls[-1][2] == {"Argument": MODEL_PATH}
    await adapter.disconnect()


async def test_p160c_r143_save_is_refused_until_the_path_is_established() -> None:
    """门槛（**事故 2 的钉子**）：**未**确立路径时发 `SAVE` ⇒ 拒绝，且**零请求**。"""
    adapter, transport = await _adapter()
    # ⚠️ 经 `execute_normalized` 后，MIDAS 错误被**翻译**成域错误（`base/errors.py`）
    with pytest.raises(EngineeringValidationError) as caught:
        await adapter.execute_normalized("SAVE", {"project_path": MODEL_PATH}, _NO_CONTEXT)
    assert caught.value.code == "STRUCTAI-1200", caught.value.to_dict()
    assert caught.value.details["reason"] == "project_path_not_established", caught.value.to_dict()
    assert transport.calls == [], transport.calls
    await adapter.disconnect()


async def test_p160c_r143_save_is_allowed_after_a_successful_save_as() -> None:
    """门槛：`SAVE_AS` **成功后**，`SAVE` 才放行；体仍按手册 = `{"Argument": {}}`。"""
    adapter, transport = await _adapter()
    await adapter.execute_normalized("SAVE_AS", {"project_path": MODEL_PATH}, _NO_CONTEXT)
    transport.clear()
    await adapter.execute_normalized("SAVE", {"project_path": MODEL_PATH}, _NO_CONTEXT)
    assert transport.calls[-1][2] == {"Argument": {}}
    await adapter.disconnect()


async def test_p160c_r143_new_clears_the_established_path_again() -> None:
    """门槛：`NEW`（新建）⇒ 路径**清空** ⇒ `SAVE` 重新被拒（**不**留错误状态）。"""
    adapter, transport = await _adapter()
    await adapter.execute_normalized("SAVE_AS", {"project_path": MODEL_PATH}, _NO_CONTEXT)
    await adapter.execute_normalized("NEW", {"arguments": {}}, _NO_CONTEXT)
    transport.clear()
    with pytest.raises(EngineeringValidationError) as caught:
        await adapter.execute_normalized("SAVE", {"project_path": MODEL_PATH}, _NO_CONTEXT)
    assert caught.value.details["reason"] == "project_path_not_established"
    assert transport.calls == []
    await adapter.disconnect()
