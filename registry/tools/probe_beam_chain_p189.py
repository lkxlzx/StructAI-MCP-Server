#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P189 附：**简支钢梁**全链路真机实测（判据走接口层）。

与 `probe_flagship_chain.py`（钢柱）不同的模型 —— 本次**重新设计一个受弯构件**：

    简支钢梁，跨长 8 m（沿 +X），两端简支（左端铰支 / 右端滚动），
    跨中竖向集中荷载 P = 200 kN（向下），STATIC 分析 → 结果（跨中位移）→ 设计（KDS 41 30）。

复用（**不新造截面形状**，守 R151）：
* 材质 = Q355 规范库路线（`GB50017-17(S)` + `DB=Q355`）—— 与旗舰阶段 B 同一份，已实测可用；
* 截面 = 与旗舰阶段 B 同一份 `P154S1`（占位截面；本次同样**如实标注**，见计算书 §5 口径）；
* 装配栈 / 判据 / 清理 = 直接复用 `probe_flagship_chain` 的函数（**不**另立判定）。

只改：几何（节点坐标）、边界（简支）、荷载（跨中集中力）、结果取点（跨中节点）。
纪律：只碰自建编号 · 跑前/跑后只读哨兵 · 零残留 · 判据=效果（再读）· 证据不含凭据。

**参数化（本节重点）**：
* `--probe`：跑**单个**模型（默认 8m/200kN；可用 `--span`/`--mid-fz` 覆盖）。
* `--matrix`：跑**参数化矩阵** —— 固定简支梁骨架，遍历 `BEAM_MATRIX` 各用例（不同跨度/荷载）
  批量真机跑，汇总成矩阵（`registry/live/beam_matrix_probe_p189.json`）。
  每个用例独立临时库 + 专用实例 + 独立 SAVE_AS 路径（R143），互不污染。
  ⇒ 「一个固定模板套入数据、一条命令批量测、快速发现差异用例」。
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
from typing import Any

REPO_DEFAULT = "."
EVIDENCE_RELATIVE = "live/beam_chain_probe_p189.json"
CRITERION_VERSION = 1
PROBED_AT = "2026-11-18"
INSTANCE_ALIAS = "gen-local"
INSTANCE_PRODUCT = "GEN NX"
MAX_REQUESTS = 160

STACK_TOOL_RELATIVE = "registry/tools/probe_interface_paths.py"
FLAGSHIP_TOOL_RELATIVE = "registry/tools/probe_flagship_chain.py"

# ===== 简支梁（8 m，跨中集中荷载 200 kN）=====
SPAN = 8.0
NODE_LEFT = 1
NODE_MID = 2
NODE_RIGHT = 3
ELEMENT_LEFT = 1
ELEMENT_RIGHT = 2
MATERIAL_ID = 1
SECTION_ID = 1
LOAD_CASE = "BEAM_P"
MID_FZ = -200_000.0  # 跨中集中力 200 kN 向下（MIDAS 力单位制 N）

# ⚠️ R143 铁律：所有保存必须带路径。DESIGN 前先把项目 SAVEAS 到明确路径，避免「另存为」弹窗阻塞 API。
PROJECT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".tmp_p189")
PROJECT_PATH = os.path.join(PROJECT_DIR, "P189_beam.mgbx")

# ===== 参数化用例表（固定骨架 + 不同数据）=====
# 每个用例 = 一个简支梁模型（跨度 m / 跨中集中力 N）。同一模板套不同数据，批量真机跑，快速发现差异用例。
BEAM_MATRIX: tuple[dict[str, Any], ...] = (
    {"case": "beam-6m-150kN", "span": 6.0, "mid_fz": -150_000.0},
    {"case": "beam-8m-200kN", "span": 8.0, "mid_fz": -200_000.0},
    {"case": "beam-10m-250kN", "span": 10.0, "mid_fz": -250_000.0},
    {"case": "beam-12m-300kN", "span": 12.0, "mid_fz": -300_000.0},
)
"""参数化用例矩阵：一条命令批量跑多个简支梁模型（跨度/荷载不同），套同一骨架。"""

# ===== 截面参数化矩阵（验证「截面参数真的驱动设计」）=====
# ⚠️ R151：真实 H 型钢的 DBUSER `SHAPE`/`vSIZE` 语义在本仓**无权威来源** ⇒ **不臆造真实钢号尺寸**。
# 本矩阵用**同一 8m/200kN 模型、只改截面 vSIZE 缩放**，验证「截面参数变化 ⇒ 设计承载力变化」（机制验证）。
# 真实 H 型钢用例待获取权威 `SHAPE`/`vSIZE` 定义后加入（见报告「下一步」）。
SECTION_MATRIX: tuple[dict[str, Any], ...] = (
    {"case": "sect-vsize-1-1", "span": 8.0, "mid_fz": -200_000.0, "section_vsize": [1, 1]},
    {"case": "sect-vsize-5-5", "span": 8.0, "mid_fz": -200_000.0, "section_vsize": [5, 5]},
    {"case": "sect-vsize-10-10", "span": 8.0, "mid_fz": -200_000.0, "section_vsize": [10, 10]},
    {"case": "sect-vsize-20-20", "span": 8.0, "mid_fz": -200_000.0, "section_vsize": [20, 20]},
)
"""截面参数化矩阵（机制验证：只改 vSIZE 缩放，看设计承载力是否随之变）。"""

UNIT_PARAMETERS: dict[str, Any] = {
    "unit": [{"id": "1", "force": "KN", "dist": "M", "heat": "KJ", "temper": "C"}],
}


def _material_parameters() -> dict[str, Any]:
    """Q355 规范库路线（与旗舰阶段 B 同一份，已实测可用；**不**臆造）。"""
    return {
        "materials": [
            {
                "id": str(MATERIAL_ID),
                "name": "Q355",
                "type": "STEEL",
                "he_spec": 0,
                "he_cond": 0,
                "plmt": 0,
                "p_name": "",
                "bmass_dens": False,
                "damp_rat": 0.02,
                "p_type": 1,
                "standard": "GB50017-17(S)",
                "db": "Q355",
                "code": "",
                "belast": False,
                "elastic_modulus": 206_000_000.0,  # kN/m²（2.06e8）
            }
        ]
    }


def _section_parameters() -> dict[str, Any]:
    """截面（与旗舰阶段 B 同一份 P154S1；占位形状，**如实标注**）。"""
    return {
        "sections": [
            {
                "id": str(SECTION_ID),
                "name": "P154S1",
                "section_type": "DBUSER",
                "shape": "SB",
                "offset_point": "LT",
                "datatype": 2,
                "horz_offset_opt": 0,
                "vert_offset_opt": 0,
                "use_shear_deform": False,
                "use_warping_effect": False,
                "vsize": [1, 1],
            }
        ]
    }


def _node(own_id: str, *, x: float) -> dict[str, Any]:
    return {"nodes": [{"id": own_id, "x": x, "y": 0.0, "z": 0.0}]}


def _element(own_id: str, *, n1: str, n2: str) -> dict[str, Any]:
    return {
        "elements": [
            {
                "id": own_id,
                "type": "BEAM",
                "node_ids": [int(n1), int(n2)],
                "material_id": int(MATERIAL_ID),
                "section_id": int(SECTION_ID),
            }
        ]
    }


def _support(node_id: int, *, hinge: bool, own_id: str) -> dict[str, Any]:
    """简支边界：竖向 uz 约束；铰端另约束 ux/uy，滚端释放水平；转动 rx/ry/rz **全释放**。"""
    return {
        "boundaries": [
            {
                "id": own_id,
                "node_id": int(node_id),
                "group_name": "",
                "ux": bool(hinge),
                "uy": bool(hinge),
                "uz": True,
                "rx": False,
                "ry": False,
                "rz": False,
                "rw": False,
            }
        ]
    }


LOAD_PARAMETERS: dict[str, Any] = {
    "load_type": "NODE_FORCE",
    "load": {"id": NODE_MID, "load_case": LOAD_CASE, "fz": MID_FZ},
    "load_case_definition": {"name": LOAD_CASE, "type": "D", "description": LOAD_CASE},
}

LOAD_COMBINATION_PARAMETERS: dict[str, Any] = {
    "combination_kind": "STEEL",
    "load_combinations": [
        {
            "no": 1,
            "name": "sLCB1",
            "active": "STRENGTH",
            "i_type": 0,
            "description": "",
            "combination_items": [{"ANAL": "ST", "LCNAME": LOAD_CASE, "FACTOR": 1.0}],
        }
    ],
}

ANALYSIS_PARAMETERS: dict[str, Any] = {"analysis_type": "STATIC"}
RESULT_PARAMETERS: dict[str, Any] = {"node_ids": [NODE_MID]}

# ⚠️ 铁律：材质/荷载/设计规范必须**同区域**（不得中国材质 + 韩国规范）。
# 本模型用**中国体系**：材质 Q355（GB50017 钢号库）、设计规范 GB50017-03、材料库 GB50017-17(S)。
DESIGN_CODE = "GB50017-03"
DESIGN_PARAMETERS: dict[str, Any] = {
    "design_code": [{"id": "1", "dgn_code": "GB50017-03"}],
    # ⚠️ `design_option`(DCO) **省略**：R169 —— 配置项为空时设计链照常跑通；
    # 且 GB50017-03 的 DCO 字段集本仓未实测（design_codes.py 拒猜）。因此不传。
    "design_frame": [
        {"id": "1", "frame_x": "Braced Non-sway", "frame_y": "Braced Non-sway", "auto_kf": False, "design_type": "3D"}
    ],
    "design_frame": [
        {"id": "1", "frame_x": "Braced Non-sway", "frame_y": "Braced Non-sway", "auto_kf": False, "design_type": "3D"}
    ],
    "design_members": [{"id": "1", "elements": [ELEMENT_LEFT, ELEMENT_RIGHT], "reverse": False}],
    "perform_type": "ALL",
    "arguments": {"TABLE_TYPE": "PROP", "ELEMS": {"KEYS": [ELEMENT_LEFT, ELEMENT_RIGHT]}, "PRI_SORT": 1, "RESULT": 0},
}


SENTINEL_ENDPOINTS: tuple[str, ...] = (
    "DB.CNLD", "DB.CONS", "DB.ELEM", "DB.GRUP", "DB.LCOM-STEEL",
    "DB.MATL", "DB.NODE", "DB.SECT", "DB.STLD",
)

CLEANUP_ORDER: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("DB.LCOM-STEEL", "MODEL.LOAD.DELETE", {"combination_kind": "STEEL"}),
    ("DB.CNLD", "MODEL.LOAD.DELETE", {}),
    ("DB.CONS", "MODEL.BOUNDARY.DELETE", {}),
    ("DB.ELEM", "MODEL.ELEMENT.DELETE", {}),
    ("DB.NODE", "MODEL.NODE.DELETE", {}),
    ("DB.MATL", "MODEL.MATERIAL.DELETE", {}),
    ("DB.SECT", "MODEL.SECTION.DELETE", {}),
    ("DB.STLD", "MODEL.LOAD.DELETE", {}),
)


def _load_module(repo: pathlib.Path, rel: str, name: str) -> Any:
    path = repo / rel
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"❌ 无法装载 {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _beam_steps_via(stack_mod: Any, flag: Any, *, span: float = None, mid_fz: float = None, project_path: str = None,
                    section_shape: str = None, section_vsize: list = None, section_secttype: str = None) -> tuple[dict[str, Any], ...]:
    """用**旗舰/接口层已验证可用**的参数构造函数生成简支梁各步（不手写 body，避免键名缺漏）。

    **参数化**：
    * `span`（跨度 m）/ `mid_fz`（跨中集中力 N，向下为负）/ `project_path`（保存路径，R143）；
    * `section_shape` / `section_vsize` / `section_secttype`：截面参数（None ⇒ 沿用旗舰占位截面
      `P154S1`/`SB`/`[1,1]`，已验证可用）。传真实值即换真实截面（vSIZE 语义随 SHAPE，须权威来源 R151）。
    """
    span = SPAN if span is None else float(span)
    mid_fz = MID_FZ if mid_fz is None else float(mid_fz)
    project_path = PROJECT_PATH if project_path is None else str(project_path)
    material = stack_mod._material_parameters(str(MATERIAL_ID))  # noqa: SLF001
    section = stack_mod._section_parameters(str(SECTION_ID))  # noqa: SLF001
    # 让材质/截面与旗舰阶段 B **逐字节一致**：直接取旗舰 `_substitute_steps` 里对应步的 parameters
    for _s in flag._substitute_steps(stack_mod):  # noqa: SLF001
        if _s.get("operation") == "MODEL.SECTION.ASSIGN":
            section = _s["parameters"]
        elif _s.get("operation") == "MODEL.MATERIAL.ASSIGN":
            material = _s["parameters"]
    # 截面参数化：若给了 section_shape/vsize/secttype，覆盖占位截面
    if section_shape is not None or section_vsize is not None or section_secttype is not None:
        import copy as _copy
        section = _copy.deepcopy(section)
        item = section["sections"][0]
        if section_secttype is not None:
            item["section_type"] = str(section_secttype)
        if section_shape is not None:
            item["shape"] = str(section_shape)
        if section_vsize is not None:
            item["vsize"] = [float(x) for x in section_vsize]
    n_left = stack_mod._node_parameters(str(NODE_LEFT), x=0.0, y=0.0, z=0.0)  # noqa: SLF001
    n_mid = stack_mod._node_parameters(str(NODE_MID), x=span / 2, y=0.0, z=0.0)  # noqa: SLF001
    n_right = stack_mod._node_parameters(str(NODE_RIGHT), x=span, y=0.0, z=0.0)  # noqa: SLF001
    # 参数化荷载（工况名固定 BEAM_P；跨中集中力用传入 mid_fz）
    load_params = {
        "load_type": "NODE_FORCE",
        "load": {"id": NODE_MID, "load_case": LOAD_CASE, "fz": mid_fz},
        "load_case_definition": {"name": LOAD_CASE, "type": "D", "description": LOAD_CASE},
    }
    e1 = stack_mod._element_parameters(str(ELEMENT_LEFT), nodes=[str(NODE_LEFT), str(NODE_MID)], materials=[str(MATERIAL_ID)], sections=[str(SECTION_ID)])  # noqa: SLF001
    e2 = stack_mod._element_parameters(str(ELEMENT_RIGHT), nodes=[str(NODE_MID), str(NODE_RIGHT)], materials=[str(MATERIAL_ID)], sections=[str(SECTION_ID)])  # noqa: SLF001
    return (
        {"order": -1, "operation": "SAVE_AS", "tool": "engineering_doc",
         "label": "⓪′ 先给项目落明确路径（R143：保存必须带路径，杜绝另存为弹窗）",
         "parameters": {"project_path": project_path}, "confirm": True, "readback": ()},
        {"order": 0, "operation": "MODEL.UNIT.ASSIGN", "tool": "engineering_model_assign",
         "label": "⓪ 单位口径（KN/M）", "parameters": UNIT_PARAMETERS, "confirm": True, "readback": ("DB.UNIT",)},
        {"order": 1, "operation": "MODEL.MATERIAL.ASSIGN", "tool": "engineering_model_assign",
         "label": "① 材质 Q355（规范库路线）", "parameters": material, "confirm": True, "readback": ("DB.MATL",)},
        {"order": 2, "operation": "MODEL.SECTION.ASSIGN", "tool": "engineering_model_assign",
         "label": "① 截面 P154S1（旗舰同一份，已验证可用）", "parameters": section, "confirm": True, "readback": ("DB.SECT",)},
        {"order": 3, "operation": "MODEL.NODE.CREATE", "tool": "engineering_model_assign",
         "label": "① 左端节点(0,0,0)", "parameters": n_left, "confirm": True, "readback": ("DB.NODE",)},
        {"order": 4, "operation": "MODEL.NODE.CREATE", "tool": "engineering_model_assign",
         "label": "① 跨中节点(4,0,0)", "parameters": n_mid, "confirm": True, "readback": ("DB.NODE",)},
        {"order": 5, "operation": "MODEL.NODE.CREATE", "tool": "engineering_model_assign",
         "label": "① 右端节点(8,0,0)", "parameters": n_right, "confirm": True, "readback": ("DB.NODE",)},
        {"order": 6, "operation": "MODEL.ELEMENT.CREATE", "tool": "engineering_model_assign",
         "label": "① 单元1（左-中）", "parameters": e1, "confirm": True, "readback": ("DB.ELEM",)},
        {"order": 7, "operation": "MODEL.ELEMENT.CREATE", "tool": "engineering_model_assign",
         "label": "① 单元2（中-右）", "parameters": e2, "confirm": True, "readback": ("DB.ELEM",)},
        {"order": 8, "operation": "MODEL.BOUNDARY.ASSIGN", "tool": "engineering_model_assign",
         "label": "① 左端铰支", "parameters": _support(NODE_LEFT, hinge=True, own_id=str(NODE_LEFT)), "confirm": True, "readback": ("DB.CONS",)},
        {"order": 9, "operation": "MODEL.BOUNDARY.ASSIGN", "tool": "engineering_model_assign",
         "label": "① 右端滚动", "parameters": _support(NODE_RIGHT, hinge=False, own_id=str(NODE_RIGHT)), "confirm": True, "readback": ("DB.CONS",)},
        {"order": 10, "operation": "MODEL.LOAD.ASSIGN", "tool": "engineering_model_assign",
         "label": f"② 跨中集中荷载 {abs(mid_fz)/1000:.0f}kN ↓（先建工况）", "parameters": load_params, "confirm": True, "readback": ("DB.STLD", "DB.CNLD")},
        {"order": 11, "operation": "MODEL.LOAD_COMBINATION.ASSIGN", "tool": "engineering_model_assign",
         "label": "③ 荷载组合(DB.LCOM-STEEL)", "parameters": LOAD_COMBINATION_PARAMETERS, "confirm": True, "readback": ("DB.LCOM-STEEL",)},
        {"order": 12, "operation": "ANALYSIS.STATIC", "tool": "engineering_analysis",
         "label": "④ STATIC 分析", "parameters": ANALYSIS_PARAMETERS, "confirm": True, "readback": ()},
        {"order": 13, "operation": "RESULT.NODE.DISPLACEMENT", "tool": "engineering_result",
         "label": "⑤ 跨中位移", "parameters": RESULT_PARAMETERS, "confirm": False, "readback": ()},
        {"order": 14, "operation": "DESIGN.STEEL", "tool": "engineering_design",
         "label": "⑥ 钢构件验算(KDS 41 30)", "parameters": DESIGN_PARAMETERS, "confirm": True, "readback": ()},
    )


async def _cleanup(flag: Any, stack: Any) -> list[dict[str, Any]]:
    cleanup: list[dict[str, Any]] = []
    for endpoint, operation, extra in CLEANUP_ORDER:
        stack.log.clear()
        before = list(stack.read_ids(endpoint))
        if not before:
            cleanup.append({"endpoint": endpoint, "operation": operation, "ids": [], "gone": True})
            continue
        outcome = await stack.run_operation(
            "engineering_model_delete", operation, {"item_ids": before, **extra}, confirm=True
        )
        cleanup.append({
            "endpoint": endpoint, "operation": operation, "ids": before,
            "error": flag._error_of(outcome["response"]) or dict(outcome.get("task") or {}).get("error") or {},
            "requests": flag._requests_of(stack),
        })
    for item in cleanup:
        remaining = list(stack.read_ids(str(item["endpoint"])))
        item["remaining"] = remaining
        item["gone"] = not remaining
    return cleanup


async def _probe(repo: pathlib.Path, *, span: float = None, mid_fz: float = None, project_path: str = None,
                 section_shape: str = None, section_vsize: list = None, section_secttype: str = None) -> dict[str, Any]:
    stack_mod = _load_module(repo, STACK_TOOL_RELATIVE, "structai_probe_interface_paths_p189")
    flag = _load_module(repo, FLAGSHIP_TOOL_RELATIVE, "structai_probe_flagship_p189")
    span = SPAN if span is None else float(span)
    mid_fz = MID_FZ if mid_fz is None else float(mid_fz)
    summary: dict[str, Any] = {"aborted": "", "sentinel_before": {}, "sentinel_after": {}, "cleanup": [], "residue": {}, "numbers": {}}
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="structai-beam-p189-") as workdir:
        async with stack_mod._Stack(  # noqa: SLF001
            repo, pathlib.Path(workdir), allow_unverified=True, capture_shape=True
        ) as stack:
            before = stack.sentinel(SENTINEL_ENDPOINTS)
            summary["sentinel_before"] = before
            unreadable = sorted(k for k, v in before.items() if int(v.get("status") or 0) == 0 or v.get("error"))
            if unreadable:
                summary["aborted"] = f"跑前哨兵不可读 ⇒ 不盲写：{unreadable[:5]}"
                summary["sentinel_after"] = before
                return {"steps": rows, "summary": summary}
            blocked = {k: v["ids"] for k, v in before.items() if v.get("ids")}
            if blocked:
                summary["aborted"] = f"跑前哨兵非空 ⇒ 不写：{sorted(blocked)[:5]}"
                summary["sentinel_after"] = before
                return {"steps": rows, "summary": summary}

            steps = _beam_steps_via(stack_mod, flag, span=span, mid_fz=mid_fz, project_path=project_path,
                                    section_shape=section_shape, section_vsize=section_vsize, section_secttype=section_secttype)
            # R135 加固：GEN NX STATIC 分析是触发式的、可能较慢 ⇒ 加大取结果重试窗口。
            try:
                flag.RESULT_ATTEMPTS = 15
                flag.RESULT_DELAY_SECONDS = 6.0
            except Exception:
                pass
            print(f"=== 简支钢梁全链路（{span:.1f}m, 跨中 {abs(mid_fz)/1000:.0f}kN）===")
            for step in steps:
                row = await flag._run_step(stack, step)  # noqa: SLF001
                rows.append(row)
                print(f"  [{row['order']:2}] {row['operation']} = {row['status']} {row.get('detail') or ''}")
                if row["status"] not in ("PASSED", "SKIPPED"):
                    for rest in steps[len(rows):]:
                        rows.append({"order": rest["order"], "operation": rest["operation"], "tool": rest["tool"],
                                     "label": rest["label"], "status": "NOT_RUN", "detail": "chain_stopped_at_previous_failure",
                                     "error": {}, "task": {}, "native_error": "", "readback": {}, "numbers": {}, "requests": []})
                    break
                summary["numbers"].update(row["numbers"])
                if row["operation"] == "ANALYSIS.STATIC" and row["status"] == "PASSED":
                    await asyncio.sleep(20.0)
            summary["cleanup"] = await _cleanup(flag, stack)
            after = stack.sentinel(SENTINEL_ENDPOINTS)
            summary["sentinel_after"] = after
            summary["residue"] = {k: v["ids"] for k, v in after.items() if v.get("ids")}
    return {"steps": rows, "summary": summary}


def _counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    c: dict[str, int] = {}
    for r in rows:
        c[str(r["status"])] = c.get(str(r["status"]), 0) + 1
    return c


def probe(repo: pathlib.Path, *, span: float = None, mid_fz: float = None) -> int:
    base_url = os.environ.get("MIDAS_BASE_URL", "").rstrip("/")
    key_value = os.environ.get("MIDAS_MAPI_KEY", "")
    if not base_url or not key_value:
        print("❌ --probe 需要 MIDAS_BASE_URL / MIDAS_MAPI_KEY（见 scripts/load-midas-env.ps1）")
        return 1
    result = asyncio.run(_probe(repo, span=span, mid_fz=mid_fz))
    rows = result["steps"]
    summary = result["summary"]
    document = {
        "note": [
            "P189 附：**简支钢梁**全链路真机实测（判据走接口层）。",
            "模型：8 m 简支钢梁（节点 1/2/3 沿 +X @ 0/4/8m），跨中竖向集中荷载 200 kN↓，STATIC → 跨中位移 → 设计(KDS 41 30)。",
            "复用旗舰阶段 B 的材质(Q355 规范库)/截面(P154S1 占位) 参数（不新造截面形状，守 R151）；只改几何/边界/荷载/取点。",
            "纪律：只碰自建编号 · 跑前/跑后只读哨兵 · 零残留 · 判据=效果（再读）。",
            "证据绝不出现凭据；失败响应只留 error.message 前 200 字。",
        ],
        "criterion_version": CRITERION_VERSION,
        "instance": {"alias": INSTANCE_ALIAS, "product": INSTANCE_PRODUCT,
                     "base_url": os.environ.get("MIDAS_BASE_URL", ""), "probed_at": PROBED_AT},
        "spec": {"prompt": "8 m 简支钢梁，跨中集中荷载 200 kN 向下，两端简支",
                 "span_m": (SPAN if span is None else span), "mid_fz": (MID_FZ if mid_fz is None else mid_fz), "mid_node": NODE_MID,
                 "elements": [ELEMENT_LEFT, ELEMENT_RIGHT]},
        "steps": rows,
        "counts": _counts(rows),
        "verdict": "PASSED" if rows and _counts(rows).get("PASSED") == len(rows) else "NOT_PASSED",
        "aborted": str(summary.get("aborted") or ""),
        "sentinel_endpoints": list(SENTINEL_ENDPOINTS),
        "sentinel_before": summary.get("sentinel_before") or {},
        "sentinel_after": summary.get("sentinel_after") or {},
        "cleanup": summary.get("cleanup") or [],
        "residue": summary.get("residue") or {},
        "numbers": summary.get("numbers") or {},
        "requests": [i for r in rows for i in (r.get("requests") or [])][:MAX_REQUESTS],
    }
    path = repo / "registry" / EVIDENCE_RELATIVE
    if summary.get("aborted"):
        print(f"⚠️ 中止（{str(summary['aborted'])[:80]}）⇒ 不覆盖既有证据")
    else:
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"已写入 registry/{EVIDENCE_RELATIVE}")
    print("verdict =", document["verdict"], " counts =", document["counts"],
          " 残留 =", sorted(document["residue"]), " 中止 =", bool(summary.get("aborted")))
    return 0 if document["verdict"] == "PASSED" and not summary.get("aborted") else 1


def matrix(repo: pathlib.Path, which: str = "beam") -> int:
    """**参数化矩阵**：遍历用例表，每用例独立 stack 真机跑全链路，汇总成矩阵。

    `which`：`beam`（跨度/荷载矩阵 `BEAM_MATRIX`）/ `sections`（截面 vSIZE 缩放矩阵 `SECTION_MATRIX`）。
    """
    if not (os.environ.get("MIDAS_BASE_URL") and os.environ.get("MIDAS_MAPI_KEY")):
        print("❌ --matrix 需要 MIDAS_BASE_URL / MIDAS_MAPI_KEY")
        return 1
    table = SECTION_MATRIX if which == "sections" else BEAM_MATRIX
    out_name = "beam_section_matrix_probe_p189.json" if which == "sections" else "beam_matrix_probe_p189.json"
    os.makedirs(PROJECT_DIR, exist_ok=True)
    cases_out: list[dict[str, Any]] = []
    for i, case in enumerate(table):
        span = float(case["span"]); mid_fz = float(case["mid_fz"])
        vsize = case.get("section_vsize")
        proj = os.path.join(PROJECT_DIR, f"{case['case']}.mgbx")
        tag = f"（span={span}m, P={abs(mid_fz)/1000:.0f}kN" + (f", vSIZE={vsize}" if vsize else "") + "）"
        print(f"\n===== 用例 {i+1}/{len(table)}: {case['case']}{tag}=====")
        result = asyncio.run(_probe(repo, span=span, mid_fz=mid_fz, project_path=proj, section_vsize=vsize))
        rows = result["steps"]; summary = result["summary"]
        nums = summary.get("numbers") or {}
        case_verdict = "PASSED" if rows and _counts(rows).get("PASSED") == len(rows) else "NOT_PASSED"
        cases_out.append({
            "case": case["case"], "span_m": span, "mid_fz": mid_fz, "section_vsize": vsize,
            "verdict": case_verdict, "counts": _counts(rows),
            "aborted": str(summary.get("aborted") or ""), "residue": summary.get("residue") or {},
            "numbers": nums,
        })
    document = {
        "note": [
            "P189 附4：**参数化矩阵**真机实测 —— 固定简支梁骨架，套不同数据批量跑全链路。",
            f"本轮矩阵：{which}（{'截面 vSIZE 缩放（机制验证：截面参数是否驱动设计）' if which=='sections' else '跨度/荷载'}）。",
            "每用例独立临时库 + 专用实例 + 独立 SAVE_AS 路径（R143）；跑前/跑后只读哨兵；零残留。",
            "判据 = 全链路步全 PASSED；数值逐条取自接口层响应。",
            "⚠️ R151：真实 H 型钢 SHAPE/vSIZE 语义本仓无权威来源 ⇒ 截面矩阵只做 vSIZE 缩放机制验证，不臆造钢号尺寸。",
        ],
        "criterion_version": CRITERION_VERSION,
        "instance": {"alias": INSTANCE_ALIAS, "product": INSTANCE_PRODUCT,
                     "base_url": os.environ.get("MIDAS_BASE_URL", ""), "probed_at": PROBED_AT},
        "cases": cases_out,
    }
    path = repo / "registry" / "live" / out_name
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n======= 矩阵汇总 =======")
    for c in cases_out:
        n = c["numbers"]
        vs = f" vSIZE={c['section_vsize']}" if c.get("section_vsize") else ""
        print(f"  {c['case']:18s} span={c['span_m']:.0f}m P={abs(c['mid_fz'])/1000:.0f}kN{vs}  verdict={c['verdict']:9s} "
              f"{c['counts']} uz={n.get('displacement.uz')} My={n.get('design.moment_y')} Mcy={n.get('design.moment_y_capacity')} Mg={n.get('design.status')}")
    print(f"已写入 registry/live/{out_name}")
    return 0 if all(c["verdict"] == "PASSED" for c in cases_out) else 1


def summary(repo: pathlib.Path) -> int:
    path = repo / "registry" / EVIDENCE_RELATIVE
    if not path.is_file():
        print(f"❌ 缺证据 registry/{EVIDENCE_RELATIVE}")
        return 1
    d = json.loads(path.read_text(encoding="utf-8"))
    print(f"简支梁全链路：{d['verdict']} · {d['counts']} · 残留 {sorted(d['residue'])}")
    for r in d["steps"]:
        print(f"  [{r['order']}] {r['operation']:28s} {r['status']:8s} {r.get('detail') or ''} {r.get('numbers') or ''}")
    print("numbers:", json.dumps(d["numbers"], ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="P189 附：简支钢梁全链路真机实测")
    p.add_argument("--repo", default=REPO_DEFAULT)
    p.add_argument("--probe", action="store_true")
    p.add_argument("--matrix", action="store_true", help="参数化矩阵：批量跑用例表")
    p.add_argument("--matrix-kind", choices=["beam", "sections"], default="beam", help="矩阵类型：beam(跨度/荷载) / sections(截面vSIZE缩放)")
    p.add_argument("--span", type=float, default=None, help="单模型跨度 m（默认 8.0）")
    p.add_argument("--mid-fz", type=float, default=None, help="单模型跨中集中力 N（向下为负，默认 -200000）")
    p.add_argument("--summary", action="store_true")
    args = p.parse_args(argv)
    repo = pathlib.Path(args.repo).resolve()
    if args.probe:
        return probe(repo, span=args.span, mid_fz=args.mid_fz)
    if args.matrix:
        return matrix(repo, which=args.matrix_kind)
    if args.summary:
        return summary(repo)
    p.print_help()
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
