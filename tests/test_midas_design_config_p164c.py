"""P164-c（分块 1）—— `DESIGN.*` **配置步**真机验证的可执行判定。

权威证据
--------
`registry/live/design_config_probe.json`（生成器 = `registry/tools/probe_design_config.py --probe`，
**只发 `GET`/`PUT`/`DELETE` 且只碰设计配置端点**）。

本文件钉住的事实
----------------
1. **配置写入有效**：RC / SRC 的 **4** 个配置端点 `PUT` 后**读回验到值**（**铁律 ⓪**：
   判据是读回里的值，**不是** `200`）⇒ P160e-b / P164-b 的修法在真机上成立。
2. **`DELETE` 语义与"删除"不符**：4 个里**只有 2 个**真的清空；`DESIGN.RC.DRC` 被换成
   服务端默认 `GB/T50010-10`，`DESIGN.SRC.AIK-SRC2K.DSRC` 是**静默 no-op**
   —— 设计规范代码是「单例且必须存在」⇒ **无法**回到未选状态。
3. **一个被静默丢弃的字段**：`SEISMIC.SHEAR_DES.A2`（手册示例与 Schema 都有）在
   `MTHD="Ve1"` 下**送了但不存** ⇒ 如实记进 `dropped_fields`。
4. **模型哨兵全空**：本批**未**触碰节点 / 单元 / 材料 / 截面 / 荷载 / 工况。
   ⚠️ `DB/GRUP` 的 26 条是 **app 自建**（2026-10-11 的探针记录为空），**不**算残留。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录。"""

EVIDENCE = REPO_ROOT / "registry" / "live" / "design_config_probe.json"
"""P164-c 分块 1 的证据。"""

TOOL = REPO_ROOT / "registry" / "tools" / "probe_design_config.py"
"""证据生成器（`--check` 可离线断言）。"""

EXPECTED_TARGETS: tuple[str, ...] = (
    "DESIGN.RC.DRC",
    "DESIGN.RC.KDS-41-20-2022.DCO",
    "DESIGN.SRC.AIK-SRC2K.DSRC",
    "DESIGN.SRC.AIK-SRC2K.DCO",
)
"""本批验证的 4 个配置端点。"""

NOT_CLEARED: dict[str, str] = {
    "DESIGN.SRC.AIK-SRC2K.DSRC": "AIK-SRC2K",
}
"""`DELETE` 之后**仍非空**的端点 → 残留的 `DGNCODE`。

⚠️ **初版结论已更正**：不是「单例不可清」，而是 ——
`/DESIGN/<族>/…` 的 `DELETE` = **写回产品默认值**（≠ 删除）；`/db/*` 的才是真删除。
`DESIGN.SRC.AIK-SRC2K.DSRC` **没有** `/db/*` 规范路由 ⇒ 只能"重置"，
而其唯一合法值 `AIK-SRC2K` **就是**默认值 ⇒ 重置与 no-op **不可区分**。
"""

CANONICAL_DELETE: dict[str, str | None] = {
    "DESIGN.RC.DRC": "/DB/DCON",
    "DESIGN.RC.KDS-41-20-2022.DCO": "DESIGN/RC/KDS-41-20-2022/DCO",
    "DESIGN.SRC.AIK-SRC2K.DSRC": None,
    "DESIGN.SRC.AIK-SRC2K.DCO": "DESIGN/SRC/AIK-SRC2K/DCO",
}
"""清理实际走的**规范路由**（`None` = 没有规范路由 ⇒ 无法删除）。"""

MODEL_SENTINELS: tuple[str, ...] = (
    "DB/NODE",
    "DB/ELEM",
    "DB/MATL",
    "DB/SECT",
    "DB/STLD",
    "DB/CNLD",
    "DB/CONS",
    "DB/LCOM-STEEL",
    "DB/LCOM-CONC",
)
"""模型侧哨兵 —— **必须全空**（`DB/GRUP` 除外：app 自建）。"""


def _document() -> dict:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def test_p164c_the_tool_check_mode_agrees_offline() -> None:
    """门槛：证据与判定点一致（离线可复算）。"""
    result = subprocess.run(
        [sys.executable, str(TOOL), "--check"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_p164c_all_four_config_writes_landed() -> None:
    """门槛（铁律 ⓪）：4 个配置端点 `PUT` 后**读回都验到值** —— 不是看 `200`。"""
    document = _document()
    steps = {s["key"]: s for s in document["steps"]}
    assert tuple(steps) == EXPECTED_TARGETS
    for key in EXPECTED_TARGETS:
        step = steps[key]
        assert step["status_code"] == 200, key
        assert step["effect_ok"] is True, (key, step["readback"])
        # 效果 = **读回里真的有那个值**
        assert step["readback"], key
        for native, want in step["identity"].items():
            assert step["found"][native] == want, (key, native)
        for name in step["presence"]:
            assert name in step["present"], (key, name)


def test_p164c_the_delete_semantics_are_recorded_not_assumed() -> None:
    """门槛：`DELETE` 的实际效果**逐条记录**，且清理走**规范路由**。

    ⚠️ **本用例记录的是更正后的结论**（初版曾错误地写成「单例不可清」）：
    `/DESIGN/<族>/…` 的 `DELETE` = **写回产品默认值**（实测 STEEL → `GB50017-17`、
    RC → `GB/T50010-10`）；`/db/*` 的 `DELETE` = **真删除**。两者作用于**同一份数据**。
    """
    document = _document()
    cleanup = {c["key"]: c for c in document["cleanup"]}
    assert tuple(cleanup) == EXPECTED_TARGETS
    for key, row in cleanup.items():
        assert row.get("delete_uri") == CANONICAL_DELETE[key], (key, row.get("delete_uri"))
    cleared = {k for k, v in cleanup.items() if v["cleared"]}
    assert cleared == {k for k, v in CANONICAL_DELETE.items() if v is not None}
    for key, code in NOT_CLEARED.items():
        assert cleanup[key]["cleared"] is False, key
        assert cleanup[key]["delete_uri"] is None, key
        assert cleanup[key]["reason"] == "no_canonical_route", key
        assert cleanup[key]["after"]["1"]["DGNCODE"] == code, (key, cleanup[key]["after"])
    assert document["counts"]["not_cleared"] == len(NOT_CLEARED)


def test_p164c_the_silently_dropped_field_is_recorded() -> None:
    """门槛：送了但读回里没有的字段**如实记录**（不判失败、也不隐藏）。

    实测：`SEISMIC.SHEAR_DES.A2` 在 `MTHD="Ve1"` 下送了不存 ——
    疑为按分支才生效的可选字段。⚠️ 若它在**任何** `MTHD` 下都存不进去，则应另立一条。
    """
    document = _document()
    steps = {s["key"]: s for s in document["steps"]}
    dropped = {k: v["dropped_fields"] for k, v in steps.items() if v["dropped_fields"]}
    assert dropped == {"DESIGN.RC.KDS-41-20-2022.DCO": {"SEISMIC.SHEAR_DES.A2": 1.2}}, dropped


def test_p164c_the_route_families_have_different_delete_semantics() -> None:
    """门槛（**本批的决定性发现**，已更正初版结论）：两条路由**共用同一份数据**，
    但 `DELETE` 语义**不同**。

    ```text
    PUT    /DESIGN/RC/DRC  KDS 41 20 : 2022  ->  两条路由的 GET 都看得到（同一份数据）
    DELETE /DESIGN/RC/DRC                    ->  写回**产品默认值** GB/T50010-10（**不是**删除）
    DELETE /DB/DCON                          ->  真删除（{}）
    ```

    ⇒ 初版「设计规范代码是单例且必须存在、选过就回不到未选」**是错的**
    （那是**只测了别名路由**就下的结论）。正确表述：`/DESIGN/<族>/…` 的 `DELETE`
    是「**把该模块的设置重置为产品默认值**」；`/db/*` 的 `DELETE` 才是删除。
    """
    document = _document()
    routes = document["route_semantics"]
    assert routes["alias_uri"] == "/DESIGN/RC/DRC"
    assert routes["canonical_uri"] == "/DB/DCON"
    states = {s["step"]: s["state"] for s in routes["steps"]}
    # ① `PUT` 别名 → 规范路由立刻可见 ⇒ **同一份数据**
    assert states["put_alias"]["alias"] == states["put_alias"]["canonical"]
    assert states["put_alias"]["alias"]["1"]["DGNCODE"] == routes["seed"]
    # ② `DELETE` 别名 → **写回默认值**，不是清空
    assert routes["verdict"]["alias_delete_clears"] is False
    assert routes["verdict"]["alias_delete_writes_default"] is True
    assert states["delete_alias"]["alias"] == states["delete_alias"]["canonical"]
    assert routes["verdict"]["routes_share_storage"] is True
    # ③ `DELETE` 规范路由 → **真的清空**
    assert routes["verdict"]["canonical_delete_clears"] is True
    assert states["delete_canonical"]["alias"] == {}
    assert states["delete_canonical"]["canonical"] == {}


def test_p164c_the_model_sentinels_are_empty() -> None:
    """门槛：模型侧哨兵**全空** —— 本批**未**触碰节点 / 单元 / 材料 / 截面 / 荷载 / 工况。"""
    document = _document()
    for moment in ("sentinel_before", "sentinel_after"):
        snapshot = document[moment]
        for path in MODEL_SENTINELS:
            assert snapshot[path]["count"] == 0, (moment, path, snapshot[path])
    # `DB/GRUP` 是 app 自建（已知非空）—— 只断言两次一致，不断言为空
    assert (
        document["sentinel_before"]["DB/GRUP"]["count"]
        == document["sentinel_after"]["DB/GRUP"]["count"]
    )


def test_p164c_the_probe_only_touched_design_config_endpoints() -> None:
    """门槛：请求只落在设计配置端点上（**不**碰模型数据）。"""
    document = _document()
    uris = {s["uri"] for s in document["steps"]} | {c["uri"] for c in document["cleanup"]}
    for uri in uris:
        assert uri.startswith("DESIGN/"), uri
    assert {s["uri"] for s in document["steps"]} == {
        "DESIGN/RC/DRC",
        "DESIGN/RC/KDS-41-20-2022/DCO",
        "DESIGN/SRC/AIK-SRC2K/DSRC",
        "DESIGN/SRC/AIK-SRC2K/DCO",
    }
