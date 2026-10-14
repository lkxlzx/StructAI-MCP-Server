"""R153 收尾（P164-b）—— `DESIGN.SRC` 的 3 个配置步从 `_read` 改 `_write(PUT)`（可执行判定）。

背景
----
**R141**（`DESIGN.STEEL`）与 **R153**（`DESIGN.CONCRETE`）实测的事故**逐条同形**：
`DESIGN.*` 的**配置**端点（手册方法 `GET, PUT, DELETE`）被编排成 `_read`（GET）
⇒ 设计规范 / 选项 / 控制 / 构件**从未被配置** ⇒ `*-ANAL` 必然失败
（真机表现为验算对话框报 `Error occured while setting unit` + 崩溃）。

P160e-b 修了 `DESIGN.CONCRETE`，其报告 §2④ 明写「`DESIGN.SRC` 同形部分**一并**修」但**未落地**。
本批（P164-b，**用户授权**）收尾：3 步改 `PUT` + 新增 **3** 个 SRC 绑定的转换器。

判据（**离线可复算**）
--------------------
1. `DESIGN.SRC` 的 3 个配置步必须是 `_write(..., method="PUT")` 且带 SRC 绑定的转换器。
2. 3 个新转换器的 `endpoint` 必须指向对应的 SRC 端点，字段表必须**逐个**等于端点 Schema
   （`不`臆造 —— 与 STEEL / RC 的字段表**不同**，故**不能**复用）。
3. **族不变量**：`DESIGN.{STEEL,CONCRETE,SRC}` 的**配置步**不得再出现 `_read`。
   ⚠️ `DESIGN.FOUNDATION` / `DESIGN.OPTIMIZE` **无步骤**（MIDAS 无 API，自研引擎）⇒ 不适用。
"""

from __future__ import annotations

import json
from pathlib import Path

from app.infrastructure.adapters.midas.operations import OPERATION_PLANS
from app.infrastructure.adapters.midas.transforms import TRANSFORMER_REGISTRY

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录。"""

SRC_CONFIG_STEPS: dict[str, tuple[str, str]] = {
    # endpoint: (intent, transformer)
    "DESIGN.SRC.AIK-SRC2K.DCO": ("write_design_option", "midas.design.src-option.v1"),
    "DESIGN.SRC.AIK-SRC2K.DCTL": ("write_design_frame", "midas.design.src-frame.v1"),
    "DESIGN.SRC.AIK-SRC2K.MEMB": ("write_design_member", "midas.design.src-member.v1"),
}
"""本批修的 3 步：端点 → `(intent, transformer)`。"""

SRC_FIELD_MAPS: dict[str, tuple[tuple[str, str, bool], ...]] = {
    "midas.design.src-option.v1": (
        ("dgn_code", "DGNCODE", True),
        ("seismic", "SEISMIC", True),
    ),
    "midas.design.src-frame.v1": (
        ("frame_x", "FRAMEX", False),
        ("frame_y", "FRAMEY", False),
        ("auto_kf", "bAUTOKF", False),
        ("design_type", "DT", False),
    ),
    "midas.design.src-member.v1": (
        ("elements", "AELEM", True),
        ("reverse", "bREVERSE", False),
    ),
}
"""3 个转换器的字段表（`(canonical, native, required)`）—— 逐个照端点 Schema。"""

DESIGN_FAMILY_CONFIG_KEYS: tuple[str, ...] = (
    "DESIGN.STEEL.DSTL",
    "DESIGN.STEEL.KDS-41-30-2022.DCO",
    "DESIGN.STEEL.KDS-41-30-2022.DCTL",
    "DESIGN.STEEL.KDS-41-30-2022.MEMB",
    "DESIGN.RC.DRC",
    "DESIGN.RC.KDS-41-20-2022.DCO",
    "DESIGN.RC.KDS-41-20-2022.DCTL",
    "DESIGN.RC.KDS-41-20-2022.MEMB",
    "DESIGN.SRC.AIK-SRC2K.DSRC",
    *SRC_CONFIG_STEPS,
)
"""设计族的**配置**端点（手册方法含 `PUT`）—— 编排里**都**必须是写步骤。"""


def _plan(name: str):
    return OPERATION_PLANS[name]


def _schema_properties(key: str) -> dict:
    """端点 Schema 的**条目**字段（`Assign` 包装已展开）。"""
    manifest = json.loads((REPO_ROOT / "registry" / "manifest.json").read_text(encoding="utf-8"))
    entry = next(e for e in manifest["endpoints"] if e["key"] == key)
    document = json.loads((REPO_ROOT / "registry" / entry["schema"]).read_text(encoding="utf-8"))
    wrapper = document["schema"].get("properties", {}).get("Assign")
    if wrapper is None:
        return document["schema"].get("properties", {})
    pattern = wrapper.get("patternProperties") or {}
    inner = next(iter(pattern.values())) if pattern else wrapper.get("additionalProperties")
    return (inner or {}).get("properties", {})


# ===== 1. 编排：3 步必须是 PUT 写 =====


def test_p164b_the_three_src_config_steps_are_writes() -> None:
    """门槛（判定 1）：`DESIGN.SRC` 的 3 个配置步是 `_write` + `method="PUT"` + 各自的转换器。"""
    steps = {step.key: step for step in _plan("DESIGN.SRC").steps}
    for key, (intent, transformer) in SRC_CONFIG_STEPS.items():
        step = steps[key]
        assert step.intent == intent, (key, step.intent)
        assert step.transformer == transformer, (key, step.transformer)
        assert step.method == "PUT", (key, step.method)


def test_p164b_the_src_plan_keeps_its_execution_steps() -> None:
    """门槛（判定 1）：本批**只**改配置步 —— `BC-ANAL` / `BC-TABLE` 与端点集**不变**。"""
    keys = [step.key for step in _plan("DESIGN.SRC").steps]
    assert keys == [
        "DESIGN.SRC.AIK-SRC2K.DSRC",
        "DESIGN.SRC.AIK-SRC2K.DCO",
        "DESIGN.SRC.AIK-SRC2K.DCTL",
        "DESIGN.SRC.AIK-SRC2K.MEMB",
        "DESIGN.SRC.AIK-SRC2K.BC-ANAL",
        "DESIGN.SRC.AIK-SRC2K.BC-TABLE",
    ]


# ===== 2. 转换器：注册 + 绑定 + 字段表 =====


def test_p164b_the_three_transformers_are_registered_and_bound() -> None:
    """门槛（判定 2）：3 个转换器已注册，且 `endpoint` 指向对应的 SRC 端点。"""
    for transformer, endpoint in (
        ("midas.design.src-option.v1", "DESIGN.SRC.AIK-SRC2K.DCO"),
        ("midas.design.src-frame.v1", "DESIGN.SRC.AIK-SRC2K.DCTL"),
        ("midas.design.src-member.v1", "DESIGN.SRC.AIK-SRC2K.MEMB"),
    ):
        cls = TRANSFORMER_REGISTRY[transformer]
        assert cls.endpoint == endpoint, (transformer, cls.endpoint)


def test_p164b_the_field_maps_match_the_endpoint_schemas() -> None:
    """门槛（判定 2）：字段表**逐个**等于端点 Schema（`不`臆造、`不`复用 STEEL / RC 的表）。"""
    for transformer, expected in SRC_FIELD_MAPS.items():
        cls = TRANSFORMER_REGISTRY[transformer]
        actual = tuple((f.canonical, f.native, f.required) for f in cls.fields)
        assert actual == expected, transformer
        # native 字段必须**确实存在**于端点 Schema
        schema = _schema_properties(cls.endpoint)
        for _canonical, native, _required in actual:
            assert native in schema, (transformer, native, sorted(schema))


def test_p164b_the_required_flags_follow_the_schema() -> None:
    """门槛（判定 2）：`required` 标志照端点 Schema 的 `required` 列表，**不**自行加减。"""
    for transformer in SRC_FIELD_MAPS:
        cls = TRANSFORMER_REGISTRY[transformer]
        schema = _schema_properties(cls.endpoint)
        # 从 manifest 取该端点的 required（重新读一次以拿到条目级 required）
        manifest = json.loads(
            (REPO_ROOT / "registry" / "manifest.json").read_text(encoding="utf-8")
        )
        entry = next(e for e in manifest["endpoints"] if e["key"] == cls.endpoint)
        document = json.loads(
            (REPO_ROOT / "registry" / entry["schema"]).read_text(encoding="utf-8")
        )
        wrapper = document["schema"]["properties"]["Assign"]
        pattern = wrapper.get("patternProperties") or {}
        inner = next(iter(pattern.values())) if pattern else wrapper["additionalProperties"]
        required = set(inner.get("required") or [])
        for field in cls.fields:
            assert field.required == (field.native in required), (
                transformer,
                field.native,
                field.required,
                sorted(required),
            )
        assert schema, cls.endpoint


# ===== 3. 族不变量 =====


def test_p164b_no_design_config_step_is_read_anymore() -> None:
    """门槛（判定 3，**族不变量**）：设计族的**配置**端点**都**已是写步骤。

    ⚠️ 这是 R141 / R153 反复出问题的那个形态 —— 一次把它按**族**钉住，
    而不是逐个端点补（P160e-b 报告 §4 教训 2：「修一个族的时候要把同族全查一遍」）。
    """
    offenders: list[str] = []
    for name in ("DESIGN.STEEL", "DESIGN.CONCRETE", "DESIGN.SRC"):
        for step in _plan(name).steps:
            if step.key in DESIGN_FAMILY_CONFIG_KEYS and step.method == "GET":
                offenders.append(f"{name}:{step.key}")
    assert offenders == [], offenders


def test_p164b_the_non_api_design_operations_have_no_steps() -> None:
    """门槛（判定 3）：`DESIGN.FOUNDATION` / `DESIGN.OPTIMIZE` **无步骤** ⇒ 不适用本判据。"""
    for name in ("DESIGN.FOUNDATION", "DESIGN.OPTIMIZE"):
        assert list(_plan(name).steps) == [], name
