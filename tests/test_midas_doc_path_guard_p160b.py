"""P160b / R143：DOC **文件操作必须带项目路径**（缺路径 ⇒ **零请求**）。

⚠️ **事故形态（P160b 实测，用户给出产品规则）**：在**无项目路径**的新建项目上发
`POST /gen/DOC/SAVE` ⇒ MIDAS 弹出**「另存为」模态窗口** ⇒ **挂起 API、阻塞链路**
（该次由**用户手动操作**才解除；`200` 因此**不能**作为「生产可用」的证据，判定作废）。

⇒ **规则**：保存 / 另存**必须**带项目路径，文件操作一律在**项目文件夹**内；
核心**先拦**（缺路径 ⇒ `STRUCTAI-1200` `project_path_required`，**一条请求都不发**）。
"""

from __future__ import annotations

import pytest

from app.infrastructure.adapters.midas.adapter import (
    DOC_PATH_OPERATIONS,
    _doc_arguments,
)
from app.infrastructure.adapters.midas.errors import MidasValidationError
from app.infrastructure.adapters.midas.operations import EndpointStep

OPEN = EndpointStep(key="DOC.OPEN", method="POST", intent="write_doc", transformer=None)
SAVE = EndpointStep(key="DOC.SAVE", method="POST", intent="write_doc", transformer=None)
SAVE_AS = EndpointStep(key="DOC.SAVEAS", method="POST", intent="write_doc", transformer=None)
NEW = EndpointStep(key="DOC.NEW", method="POST", intent="write_doc", transformer=None)


def test_p160b_r143_the_path_requiring_operations_are_exactly_three() -> None:
    """门槛：需要项目路径的恰好是 `OPEN` / `SAVE` / `SAVEAS` 三个。"""
    assert DOC_PATH_OPERATIONS == frozenset({"DOC.OPEN", "DOC.SAVE", "DOC.SAVEAS"})


@pytest.mark.parametrize("step", [OPEN, SAVE, SAVE_AS])
def test_p160b_r143_a_missing_project_path_is_refused_before_any_request(
    step: EndpointStep,
) -> None:
    """门槛（**安全判据**）：缺项目路径 ⇒ `project_path_required`，**不**返回任何请求体。"""
    with pytest.raises(MidasValidationError) as caught:
        _doc_arguments(step, {})
    assert caught.value.reason == "project_path_required", caught.value.details
    assert caught.value.details["endpoint"] == step.key, caught.value.details


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_p160b_r143_a_blank_project_path_is_refused_too(blank: object) -> None:
    """门槛：**空白**路径与缺路径同判（否则原生仍会弹窗）。"""
    with pytest.raises(MidasValidationError) as caught:
        _doc_arguments(SAVE_AS, {"project_path": blank})
    assert caught.value.reason == "project_path_required"


def test_p160b_r143_open_and_save_as_carry_the_path_as_a_plain_string() -> None:
    """门槛（**形状**）：`OPEN` / `SAVEAS` 的体**就是**路径字符串（手册示例口径）。"""
    path = r"E:\MCP\MMCP\.tmp_p160b\model.mgbx"
    assert _doc_arguments(OPEN, {"project_path": path}) == path
    assert _doc_arguments(SAVE_AS, {"project_path": path}) == path
    # 也接受直接给 `arguments`（字符串）
    assert _doc_arguments(SAVE_AS, {"arguments": path}) == path


def test_p160b_r143_save_asserts_the_path_but_keeps_the_manual_body() -> None:
    """门槛：`SAVE` 只做**前置断言**（路径由项目自身持有），体仍按手册 = `{}`。"""
    assert _doc_arguments(SAVE, {"project_path": r"E:\MCP\MMCP\.tmp_p160b\model.mgbx"}) == {}


def test_p160b_r143_operations_without_a_file_do_not_require_a_path() -> None:
    """门槛（**不**误伤）：`DOC.NEW` 等**不**做文件操作 ⇒ **不**要求路径，体照旧是对象。

    ⚠️ **P160b 实测教训**：守卫最初**漏了提前返回** ⇒ `DOC.NEW` 也被要求路径
    （**生产回归**，由既有用例 `test_p123_requests_follow_the_registry_wrapper_and_path_key` 抓到）
    ⇒ 本用例**必须真的调用**它，不能只断言常量。
    """
    assert "DOC.NEW" not in DOC_PATH_OPERATIONS
    assert _doc_arguments(NEW, {}) == {}
    assert _doc_arguments(NEW, {"arguments": {}}) == {}
