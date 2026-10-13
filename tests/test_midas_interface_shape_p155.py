"""P155 / **R128 的修复**（`ITEMS` 形态的 `Assign` 必须带外层**编号键**）+ 探针加固。

背景
----
P154 实测（`registry/live/boundary_shape_probe.json`）：
`DB.CONS` 的 `Assign` 只发 `{"Assign": {"ITEMS": […]}}` → 原生 **`400 Wrong Field`**；
`{"Assign": {"<节点编号>": {"ITEMS": […]}}}` → **`200` 且落库**。
⚠️ 外层键**不是**存在的对象编号时原生 **`200` 却什么都不建**（**假成功陷阱**）。
另：**数据侧**探针一直用的是**编号键控**形状（`tests/test_midas_write_coverage_p142.py` 的
`{"Assign": {"1": {"ITEMS": [{"ID": 1}]}}}`）⇒ 接口层的 `_wrap` 是**异类**，本批对齐。

本文件的判定点
--------------
1. **`_wrap`（唯一构造点）**：`Assign` + `ITEMS` ⇒ `{"Assign": {"<键>": {"ITEMS": […]}}}`。
2. **键的来源（由代码导出）**：该 Transformer 字段表里**映射到原生 `ID`** 的 canonical 字段
   —— `DB.CONS` = `node_id`，节点 / 梁 / 面荷载 = `id`；**取不到即明确失败**（`STRUCTAI-1200`），
   **不**回落到 `"1"`（否则会撞上「静默 `200` 不落库」）。
3. **每个 `ITEMS` 形态端点都有原生 `ID` 字段** ⇒ 键**总是**可解析（结构不变量）。
4. **Adapter 每条一个请求**：多个条目 ⇒ 多个请求，各自带自己的键。
5. **探针加固（实测事故驱动）**：哨兵**不可读**（实例不可达）⇒ **零写请求** + **不覆盖**既有证据。
6. **不变量**：`write_path_coverage()` = `0 / 633` · 缺口 `517` = `271` + `246` · R118 子桶未动。
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.infrastructure.adapters.midas.adapter import MidasAdapter
from app.infrastructure.adapters.midas.client import MidasHttpClient
from app.infrastructure.adapters.midas.errors import MidasValidationError
from app.infrastructure.adapters.midas.live import write_path_coverage
from app.infrastructure.adapters.midas.operations import EndpointStep
from app.infrastructure.adapters.midas.registry import MidasRegistry
from app.infrastructure.adapters.midas.transforms import (
    BeamLoadTransformer,
    BoundaryTransformer,
    NodalLoadTransformer,
    PressureLoadTransformer,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录。"""

PROBE_TOOL = REPO_ROOT / "registry" / "tools" / "probe_interface_paths.py"
WRITE_EVIDENCE = REPO_ROOT / "registry" / "live" / "interface_path_probe.json"
GAP_EVIDENCE = REPO_ROOT / "registry" / "live" / "interface_mapping_gap.json"
BOUNDARY_EVIDENCE = REPO_ROOT / "registry" / "live" / "boundary_shape_probe.json"

ITEMS_STYLE_KEYS = ("DB.BMLD", "DB.CNLD", "DB.CONS", "DB.PRES")
"""**全部** `Assign` + `ITEMS` 形态的写端点（R128 的适用面）。"""

EXPECTED_GAP_TOTAL = 510
EXPECTED_GAP_NOT_IN_CONTRACT = 264
EXPECTED_GAP_NO_READBACK = 246
EXPECTED_WRITE_PATH_TOTAL = 633
EXPECTED_MODEL_WRITE_TOTAL = 434


def _load(path: Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _registry() -> MidasRegistry:
    return MidasRegistry.load(REPO_ROOT / "registry")


# ===== 1. `_wrap`：`ITEMS` 形态必须带外层编号键（R128 的修复点）=====


def test_p155_the_items_style_assign_carries_the_outer_key() -> None:
    """门槛：`Assign` + `ITEMS` ⇒ `{"Assign": {"<键>": {"ITEMS": […]}}}`（**不**再裸 `ITEMS`）。"""
    registry = _registry()
    client = MidasHttpClient("http://example.invalid", lambda: "unused", "TEST_REF")
    resolved = registry.resolve(key="DB.CONS", product="GEN_NX", method="POST")
    item = {"ID": 7, "GROUP_NAME": "", "CONSTRAINT": "1111000"}
    request = client.build_request(
        resolved,
        operation="MODEL.BOUNDARY.ASSIGN",
        body=[item],
        wrapper="Assign",
        items_style=True,
        item_id="7",
        allow_unverified=True,
    )
    assert request.body == {"Assign": {"7": {"ITEMS": [item]}}}, request.body
    # 反向：**不**允许裸 `ITEMS`
    assert request.body != {"Assign": {"ITEMS": [item]}}


def test_p155_the_items_style_assign_keeps_the_inner_items_array() -> None:
    """门槛：内层**仍是** `ITEMS` 数组（修复**只**加外层键，**不**改内层形态）。"""
    registry = _registry()
    client = MidasHttpClient("http://example.invalid", lambda: "unused", "TEST_REF")
    resolved = registry.resolve(key="DB.CNLD", product="GEN_NX", method="POST")
    item = {"ID": 3, "LCNAME": "D", "FZ": -1.0}
    request = client.build_request(
        resolved,
        operation="MODEL.LOAD.ASSIGN",
        body=[item],
        wrapper="Assign",
        items_style=True,
        item_id="3",
        allow_unverified=True,
    )
    outer = request.body["Assign"]
    assert list(outer) == ["3"], outer
    assert outer["3"] == {"ITEMS": [item]}, outer


# ===== 2. 键的来源：映射到原生 `ID` 的 canonical 字段 =====


def test_p155_the_item_key_comes_from_the_native_id_field() -> None:
    """门槛：键 = 该 Transformer 里**映射到原生 `ID`** 的 canonical 字段。"""
    registry = _registry()
    from app.infrastructure.adapters.midas.adapter import _item_key  # noqa: PLC0415

    # `DB.CONS`：**节点编号**（支承的编号就是它所在节点的编号）—— 即使条目里另有 `id`
    boundary = BoundaryTransformer(registry)
    assert _item_key({"id": 99, "node_id": 4}, boundary, endpoint="DB.CONS") == 4
    # 荷载：`id`
    for factory in (NodalLoadTransformer, BeamLoadTransformer, PressureLoadTransformer):
        transformer = factory(registry)
        assert _item_key({"id": 5}, transformer, endpoint=transformer.endpoint) == 5


def test_p155_a_missing_key_is_an_explicit_failure() -> None:
    """门槛：**取不到键** ⇒ `STRUCTAI-1200`（**不**回落 `"1"`，否则撞上「静默 `200` 不落库」）。"""
    registry = _registry()
    from app.infrastructure.adapters.midas.adapter import _item_key  # noqa: PLC0415

    with pytest.raises(MidasValidationError) as failure:
        _item_key({}, BoundaryTransformer(registry), endpoint="DB.CONS")
    assert failure.value.details["reason"] == "assign_item_key_missing"
    assert failure.value.code == "STRUCTAI-1200"


def test_p155_every_items_style_endpoint_has_a_native_id_field() -> None:
    """门槛（结构不变量）：4 个 `ITEMS` 形态端点**都**有映射到原生 `ID` 的字段 ⇒ 键总可解析。"""
    registry = _registry()
    for key in ITEMS_STYLE_KEYS:
        factory = {
            "DB.CONS": BoundaryTransformer,
            "DB.CNLD": NodalLoadTransformer,
            "DB.BMLD": BeamLoadTransformer,
            "DB.PRES": PressureLoadTransformer,
        }[key]
        transformer = factory(registry)
        assert transformer.endpoint == key, key
        assert transformer.is_items_style() is True, key
        assert [field.canonical for field in transformer.fields if field.native == "ID"], key


# ===== 3. Adapter：每条一个请求（各带自己的键）=====


class _StubClient:
    """只记录 `build_request` 的入参（**不**发请求）。"""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def build_request(self, resolved: Any, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return object()

    async def send(self, request: Any) -> dict[str, Any]:
        return {"ok": True}


async def test_p155_the_adapter_sends_one_request_per_item() -> None:
    """门槛：`ITEMS` 形态 ⇒ **每条一个请求**，各自带自己的外层键（`DB.CONS` 用 `node_id`）。"""
    registry = _registry()
    adapter = MidasAdapter(registry=registry, product="GEN NX", allow_unverified=True)
    stub = _StubClient()
    adapter._client = stub  # noqa: SLF001 - 测试注入（**不**发真实请求）
    resolved = registry.resolve(key="DB.CONS", product="GEN_NX", method="POST")
    step = EndpointStep(
        key="DB.CONS", method="POST", intent="write_boundary", transformer="midas.cons.v1"
    )
    payloads = {
        "write_boundary": [
            {
                "id": 1,
                "node_id": 1,
                "group_name": "",
                "ux": True,
                "uy": True,
                "uz": True,
                "rx": False,
                "ry": False,
                "rz": False,
                "rw": False,
            },
            {
                "id": 2,
                "node_id": 2,
                "group_name": "",
                "ux": True,
                "uy": True,
                "uz": True,
                "rx": False,
                "ry": False,
                "rz": False,
                "rw": False,
            },
        ]
    }
    outcome = await adapter._write(  # noqa: SLF001 - 只测写步骤的构造
        "MODEL.BOUNDARY.ASSIGN", step, resolved, payloads
    )
    assert len(stub.requests) == 2, stub.requests
    assert [item["item_id"] for item in stub.requests] == [1, 2]
    for item in stub.requests:
        assert item["items_style"] is True, item
        assert item["wrapper"] == "Assign", item
        assert len(item["body"]) == 1, item
        # ⚠️ **P157 / D2 = A**：第 7 个自由度 `rw` 进 canonical ⇒ `CONSTRAINT` **恰好 7** 位
        assert len(str(item["body"][0]["CONSTRAINT"])) == 7, item["body"]
    assert len(outcome["responses"]) == 2


# ===== 4. 探针加固：实例不可达 ⇒ 零写请求 + 不覆盖证据（P155 实测事故的回归测试）=====


def test_p155_the_probe_aborts_without_writing_when_the_instance_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """门槛（**回归测试**）：哨兵**不可读** ⇒ **一个请求都不发**、**不覆盖**既有证据、退出码 1。

    P154 的 `--probe` 在实例不可达时：5 条行全失败 → 块间健康检查**抛异常** → 进程崩溃
    ⇒ 证据文件**没写成**（而此前已把好证据删掉）⇒ 好证据被冲掉。本用例把那次事故**钉住**。
    """
    before = WRITE_EVIDENCE.read_bytes()
    monkeypatch.setenv("MIDAS_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("MIDAS_MAPI_KEY", "unused")
    result = subprocess.run(
        [sys.executable, str(PROBE_TOOL), "--probe", "--limit", "20"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "不可读" in result.stdout, result.stdout
    assert "不覆盖" in result.stdout, result.stdout
    # **零写请求**：证据**逐字节**不变
    assert WRITE_EVIDENCE.read_bytes() == before


def test_p155_the_write_evidence_helper_keeps_the_previous_file_on_abort(
    tmp_path: Path,
) -> None:
    """门槛：`_write_evidence` 在 `aborted` 非空且**已有**文件时**保留**既有证据。"""
    tool = _load(PROBE_TOOL, "structai_probe_interface_paths_p155")
    path = tmp_path / "evidence.json"
    path.write_text('{"keep": true}\n', encoding="utf-8")
    assert tool._write_evidence(path, {"keep": False}, "boom") is False
    assert path.read_text(encoding="utf-8") == '{"keep": true}\n'
    # 首次（无既有文件）⇒ 如实写入
    fresh = tmp_path / "fresh.json"
    assert tool._write_evidence(fresh, {"keep": False}, "boom") is True
    assert fresh.is_file()


# ===== 5. 不变量 =====


def test_p155_the_invariants_are_untouched() -> None:
    """门槛：写路径分母 / 缺口 / 分类**一行未变**（本批只改请求构造与探针）。"""
    registry = _registry()
    coverage = write_path_coverage(registry, [])
    assert coverage.ratio == f"0 / {EXPECTED_WRITE_PATH_TOTAL}"
    assert coverage.model_write_ratio == f"0 / {EXPECTED_MODEL_WRITE_TOTAL}"
    gap = json.loads(GAP_EVIDENCE.read_text(encoding="utf-8"))
    assert int(gap["gap_total"]) == EXPECTED_GAP_TOTAL
    assert len(gap["gap_three_step"]) == EXPECTED_GAP_NOT_IN_CONTRACT
    assert len(gap["gap_no_readback"]) == EXPECTED_GAP_NO_READBACK


def test_p155_the_evidence_never_carries_credentials() -> None:
    """门槛（`docs/07` §14.3）：三份证据里**没有**凭据形态。"""
    for path in (WRITE_EVIDENCE, GAP_EVIDENCE, BOUNDARY_EVIDENCE):
        raw = path.read_text(encoding="utf-8")
        for marker in ("MAPI-Key", "MAPI_KEY", "mapi-key", "password", "secret"):
            assert marker not in raw, (path.name, marker)


# ===== 6. 实例门控 =====


def _live_ready() -> bool:
    return bool((os.environ.get("MIDAS_BASE_URL") or "").strip()) and bool(
        (os.environ.get("MIDAS_MAPI_KEY") or "").strip()
    )


@pytest.mark.skipif(
    not _live_ready(),
    reason="真实接口层探针需 MIDAS_BASE_URL + MIDAS_MAPI_KEY（见 scripts/load-midas-env.ps1）",
)
def test_p155_the_live_reverification_is_recorded_when_the_instance_is_up() -> None:
    """门槛（**环境门控**）：实例可用时，写路径证据里 `DB.CONS` **不再**是失败项。

    ⚠️ **P155 的实测受环境阻塞**：修复落地时 `gen-local` **不可达**（`WinError 10061`），
    故本用例在实例恢复前如实 `skip`。恢复后**必须**重跑
    `python -m registry.tools.probe_interface_paths --probe --limit 20`
    并把 `counts` 更新为 `{'PASSED': 13}`（**只**改数字与注释）。
    """
    document = json.loads(WRITE_EVIDENCE.read_text(encoding="utf-8"))
    failed = {
        (str(row["path"]), str(row["endpoint"]))
        for row in document["paths"]
        if row["status"] == "FAILED"
    }
    assert failed == set(), failed
