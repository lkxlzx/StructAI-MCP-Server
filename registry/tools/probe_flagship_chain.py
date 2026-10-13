#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P157：`docs/07` §13.5 的**旗舰五步链**在**真机**上的端到端实测（判据**走接口层**）。

为什么需要这个工具
------------------
`docs/reports/P0_裁决清单_v1.0.md` §0：**R126 卡住 42 / 69 个 Operation（≈ 61%）**，
而 `docs/07` §13.5 的五步链

    BUILD.COLUMN → MODEL.LOAD.ASSIGN → ANALYSIS.STATIC
    → RESULT.NODE.DISPLACEMENT → DESIGN.STEEL

**在真机上从未跑通**（只在 L3 / Mock 层通过，见 P119–P126；真机 L5 只做到「建 1 节点 →
读回 → 删」，P137c）。本工具把这条链**逐条**打出来，判据**全部**取接口层的响应
（`MCP Tool → ExecutionService → Adapter → MIDAS`），**不**走数据侧旁路。

两个阶段（**为什么有两个**）
----------------------------
* **阶段 A = 规格链**：`docs/07` §13.5 **逐字**（① `BUILD.COLUMN` + ②–⑤）。
* **阶段 B = 替代前缀**：**仅当**阶段 A 的 ① 失败时跑 —— 用 `docs/07` §6.5 里
  `BUILD.COLUMN` **自己组合**的那四个**原子** Operation（`MODEL.MATERIAL.ASSIGN` ·
  `MODEL.SECTION.ASSIGN` · `MODEL.NODE.CREATE` ×2 · `MODEL.ELEMENT.CREATE`）先把模型建出来，
  再跑 ②–⑤。取值 = **手册示例 / 用户实测给定**（材质 = `GB50017-17(S)` + 数据库 `Q355`；
  截面 = 手册 `db/SECT` 示例 6001），**不**新造取值、**不**放宽判定。
  ⇒ 目的是把 ②–⑤（分析 / 结果 / 设计，即 **R127a** 的未知面）**也**打出来，
  **不**是把阶段 A 的失败掩盖成通过。
  ⚠️ **R131 的更正（P157，用户给出证据）**：`BUILD.COLUMN` 的材质载荷**混用了两条互斥路线** ——
  声明 `TYPE=STEEL`（**规范库**路线）却给"用户自定义"的属性、且**一个库判据都不给**
  （`P_TYPE` / `STANDARD` / `DB` / `CODE`）⇒ 原生 `400 Wrong Field`。
  手册 `db/MATL` 的 **3** 个示例划清了边界：`Standard`（规范库：`TYPE=STEEL/CONC/SRC`
  + `P_TYPE=1` + `STANDARD` + `DB` + `CODE`）·
  `Isotropic - User Defined`（`TYPE=USER` + `P_TYPE=2` + 属性值）·
  `Orthotropic - User Defined`（`TYPE=USER` + `P_TYPE=3` + `*_M` 数组）——
  **`TYPE`+`P_TYPE` 决定哪组属性有效**。

判据（**先写清楚再动手**）
--------------------------
| 步 | `PASSED` 的判据 |
| --- | --- |
| 建模（① / ①′） | 无错误 ∧ **再读** `DB.NODE` / `DB.ELEM` / `DB.MATL` / `DB.SECT` **都在** |
| ② `MODEL.LOAD.ASSIGN` | 无错误 ∧ **再读** `DB.CNLD` 里该**节点编号**在（见下方 R128） |
| ③ `ANALYSIS.STATIC` | 无错误 ∧ 原生 `2xx` |
| ④ `RESULT.NODE.DISPLACEMENT` | 无错误 ∧ **行数 ≥ 1**（数值**不**硬编码，逐条取自响应） |
| ⑤ `DESIGN.STEEL` | 无错误 ∧ 设计结果表**行数 ≥ 1** |

⚠️ **R128**：`ITEMS` 形态的 `Assign` 外层键无效时原生**静默 `200` 却不建** ⇒
② **必须**以**再读**为准（**不**以 `2xx` 为准）。

* **只碰自建编号**：编号取既有编号的 `max + 1`（专用空项目 ⇒ `1` / `2`）。
* **跑前 / 跑后只读哨兵**（`GET`）：**读不到 ⇒ 一个请求都不发**（P155 加固）；
  **跑前非空 ⇒ 一个写请求都不发**（P138c 的空项目闸门）。
* **逆序清理**：`DB.CNLD` → `DB.CONS` → `DB.ELEM` → `DB.NODE` → `DB.MATL` → `DB.SECT` →
  `DB.STLD`；每一步**再读确认**（R119）。⚠️ 接口层的 `MODEL.LOAD.DELETE` **不**覆盖
  `DB.CNLD`（只覆盖 `DB.STLD` / `DB.BMLD`）⇒ 节点荷载靠**删除节点**连带清掉（如实记录）。
* ⚠️ **分析结果可能清不掉**（`POST.TABLE` 的持久化不在本工具的清理能力内）⇒ 如实记录
  `analysis_result_persists`，**不**声称「项目回到空」。
* **有界**：阶段 A **5** 步 · 阶段 B **10** 步 + 清理（请求数 ≤ `MAX_REQUESTS`）；
  **不**逐端点连发试探。
* 证据里**绝不**出现凭据；**失败**响应只留 `error.message` 前 200 字。

用法
----
    python registry/tools/probe_flagship_chain.py --probe     # 真机五步链（需要 MIDAS_* 环境）
    python registry/tools/probe_flagship_chain.py --check     # 离线复算
    python registry/tools/probe_flagship_chain.py --summary
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import pathlib
import tempfile
from typing import Any

REPO_DEFAULT = "."
EVIDENCE_RELATIVE = "live/flagship_chain_probe.json"
CRITERION_VERSION = 1
PROBED_AT = "2026-10-11"
INSTANCE_ALIAS = "gen-local"
INSTANCE_PRODUCT = "GEN NX"
MAX_NATIVE_ERROR = 200
MAX_REQUESTS = 160
STACK_TOOL_RELATIVE = "registry/tools/probe_interface_paths.py"
"""复用 P152–P157 的**同一条**装配链（临时库 + 专用实例 + MCP Server）。"""

PASSED = "PASSED"
FAILED = "FAILED"
NOT_RUN = "NOT_RUN"
SKIPPED = "SKIPPED"
"""**已知产品边界**（**不**调用）—— 例如 `DESIGN.*` 的执行会驱动 MIDAS 界面
（弹模态对话框 + 崩溃风险，见 `docs/07` §16.1 **R140**）⇒ 如实登记、**不**硬试。"""

# ===== `docs/07` §13.5 的钢柱（6 m 高 Q355B，H400×400×13×21，柱底固定，柱顶 500 kN 竖向）=====

BASE_NODE = 1
BOUNDARY_NODE = BASE_NODE
"""**柱底固定**的节点编号（= 柱底节点；支承编号就是它所在节点的编号 —— R128 的外层键口径）。"""
TOP_NODE = 2
ELEMENT_ID = 1
MATERIAL_ID = 1
SECTION_ID = 1
LOAD_CASE = "AXIAL"
AXIAL_FZ = -500_000.0
HEIGHT = 6.0

MATERIAL_NAME = "Q355"
"""材料名（= **钢号**）。

⚠️ §13.5 原文写的 `Q355B` **不在** `GB50017-17(S)` 的钢号库里。
"""

MATERIAL_STANDARD = "GB50017-17(S)"
"""钢材·**规范**（GEN NX「材料数据」对话框实测可选值，P157 由用户给定）。"""

MATERIAL_GRADE = "Q355"
"""钢材·**数据库**（`DB`）—— ⚠️ **P157 更正**：`DB` 装的是**钢号**，`CODE`（产品）留空；
手册 `Standard` 示例同构（`EN05(S)` + `DB:"S450"` + `CODE:""`）。"""

MATERIAL_ELAST = 206_000_000.0
"""弹性模量，单位 **kN/m²**（与对话框一致：选 `Q355` 后自动带出 `2.0600e+08`）。
⚠️ 旧探针发的 `2.1e11` 是 **Pa**，量纲差 **1000×**。"""

MATERIAL_DAMP_RAT = 0.02
"""阻尼比（手册 `Standard` 示例的值）。"""

RESULT_ATTEMPTS = 6
"""取结果步骤的**有界**重试次数（`RESULT.*`）。

⚠️ **R135（P157 新发现）**：`ANALYSIS.STATIC`（`DOC.ANAL`）在真机上是**触发式**的 ——
接口层 `POST /DOC/ANAL` 返回 **`200`** 时，分析**未必**已经算完；紧接着的取结果会拿到
**`200 {}`**（空对象），而**不是**「没有分析结果」的 `400`。
⇒ 取结果必须**有界等待 + 重试**（**不**无限轮询）。"""

RESULT_DELAY_SECONDS = 3.0
"""每次重试之间的等待秒数（有界：最多 `RESULT_ATTEMPTS × RESULT_DELAY_SECONDS`）。"""


def _material_parameters() -> dict[str, Any]:
    """`MODEL.MATERIAL.ASSIGN` 的规范化参数（**规范库路线**；P157 由用户给定取值）。

    取值来源（**不**臆造）：
    * **结构** = 手册 `db/MATL` 的 `Standard` 示例（与 `registry/live/write_templates.json`
      的 `DB.MATL.body` 同源）：`PARAM[0]` 带 `P_TYPE` / `STANDARD` / `DB` / `CODE` /
      `bELAST` / `ELAST`；
    * `STANDARD` = **GB50017-17(S)** · `DB` = **Q355**（钢号）· `ELAST` = **2.06e8 kN/m²** ——
      用户在 GEN NX「材料数据」对话框上实测给定；
    * `CODE` = `""`（**产品**为空）、`bELAST` = `false`（与手册示例一致）。

    ⚠️ **不**给 `POISN` / `DEN` —— 钢材的属性由**规范库**带出（对话框里弹性模量是**自动**填的），
    用户**不能**自定义 ⇒ 这正是 **R131** 的成因（`BUILD.COLUMN` 的载荷给了"用户自定义"的属性、
    却声明 `TYPE=STEEL`（规范库路线），两条路线混用 ⇒ 原生 `400 Wrong Field`）。
    """
    return {
        "materials": [
            {
                "id": str(MATERIAL_ID),
                "name": MATERIAL_NAME,
                "type": "STEEL",
                "he_spec": 0,
                "he_cond": 0,
                "plmt": 0,
                "p_name": "",
                "bmass_dens": False,
                "damp_rat": MATERIAL_DAMP_RAT,
                "p_type": 1,
                "standard": MATERIAL_STANDARD,
                "db": MATERIAL_GRADE,
                "code": "",
                "belast": False,
                "elastic_modulus": MATERIAL_ELAST,
            }
        ]
    }


BOUNDARY_CONSTRAINT = "1111110"
"""柱底固定的 `CONSTRAINT`（**7** 位 = `DX,DY,DZ,RX,RY,RZ,RW`）。

⚠️ **R134（P157 新发现）**：`docs/07` §13.5 的提示词写「**柱底固定**」，而 §6.5 给 `BUILD.COLUMN`
的组合（= `BUILD.BEAM` 的「同上」）**不含** `DB.CONS` ⇒ 建出来的模型**没有边界条件** ⇒
`POST /DOC/ANAL` 被原生拒绝 **`[错误] 边界条件 没有定义。`**（③ 的**真实**成因）。
对比 §6.5 的 `BUILD.STEEL_FRAME` **含** `DB.CONS` ⇒ **§6.5 内部不一致**。
⚠️ 取值口径：**六个经典自由度全约束**（=「固定」）；第 **7** 位 `rw`（翘曲）取 **`False`** ——
与 P157 写路径**已实测接受**的 `seven_digits_rw0` 一致，**不**臆造 `True`。
"""


def _boundary_parameters() -> dict[str, Any]:
    """`MODEL.BOUNDARY.ASSIGN` 的规范化参数（**柱底固定**；`docs/04` §31 的 7 个自由度）。

    ⚠️ **P157 / D2 = A 的落地在此被**真机用到**：`rw` 由**调用方显式**给出（**不**给默认值）——
    这正是 D2 裁决 A 的意义（见 `registry/live/constraint_value_probe.json`）。
    """
    return {
        "boundaries": [
            {
                "id": str(BOUNDARY_NODE),
                "node_id": BOUNDARY_NODE,
                "group_name": "",
                "ux": True,
                "uy": True,
                "uz": True,
                "rx": True,
                "ry": True,
                "rz": True,
                "rw": False,
            }
        ]
    }


COLUMN_PARAMETERS: dict[str, Any] = {
    "base_node": {"x": 0.0, "y": 0.0, "z": 0.0},
    "height": HEIGHT,
    "material": "Q355B",
    "section": "H400x400x13x21",
    "section_type": "DBUSER",
    "elastic_modulus": 2.06e11,
    "poisson_ratio": 0.3,
    "density": 7850.0,
}
"""`docs/07` §13.5 的钢柱参数（与 L3 的 `CIVIL_NX_COLUMN_PARAMETERS` **同一份**）。

⚠️ **P157 / R131 更正**：`material` 原文是 **`Q355B`**，而 `GB50017-17(S)` 的钢号库里
**没有** `Q355B`（只有 Q235 / Q355 / Q390 / Q420 / Q460 / Q345GJ / Q345）⇒ 这里**保持 §13.5 原文**
（阶段 A 是"逐字"链），**不**改它；阶段 B 用库里存在的 **`Q355`**（见 `MATERIAL_NAME`）。
"""

LOAD_PARAMETERS: dict[str, Any] = {
    "load_type": "NODE_FORCE",
    "load": {"id": TOP_NODE, "load_case": LOAD_CASE, "fz": AXIAL_FZ},
    # ⚠️ **P157 / R132（改法 A）**：`DB.CNLD` 要求 `LCNAME` 指向**已存在**的工况 ⇒ 这里**显式**给
    # 工况定义，`select_steps` 便会**先**执行编排里**已声明**的 `DB.STLD`（`write_load_case`）步。
    # 取值来源（**不**臆造）：手册 `db/STLD` 的示例 + **实测可用**的同形取值
    # （`registry/live/put_edit_probe.json` 的 `DB.STLD` 行：`status_code = 200` ·
    # `read_back = true` · `deleted = true`；其 body 来自 `write_templates.json` 的
    # `{"NAME": "DL", "TYPE": "D", "DESC": …}`）
    # ⇒ 这里**只**把 `NAME` / `DESC` 改成 `AXIAL`，`TYPE` 沿用**已实测**的 `"D"`。
    "load_case_definition": {"name": LOAD_CASE, "type": "D", "description": LOAD_CASE},
}
"""⚠️ `load.id` = **柱顶节点编号** —— R128：`DB.CNLD` 的 `Assign` 外层键 = 该条目里映射到
原生 `ID` 的 canonical 字段（= `id`），**必须**是**存在的**节点编号，否则原生静默 `200` 却不建。

⚠️ **R132（P157 修复）**：`load_case_definition` = 建工况的载荷入口（`adapter.py` 的
`_build_payloads` 早就读它，见 `docs/07` §16.1 的 R132 行）；`select_steps` 现在据此
**先建工况、再加载荷**（**未**给则保持原样）。
⚠️ **未实测（如实登记）**：工况**已存在**时再发一次建工况的**幂等性**；本批的链在**空项目**上跑，
工况必不存在 ⇒ **不**依赖该行为。
"""

COMBINATION_KIND = "STEEL"
"""荷载组合的种类（→ `DB.LCOM-STEEL`；`DESIGN.STEEL` 的验算读它）。"""

LOAD_COMBINATION_PARAMETERS: dict[str, Any] = {
    "combination_kind": COMBINATION_KIND,
    "load_combinations": [
        {
            "no": 1,
            "name": "sLCB1",
            "active": "STRENGTH",
            # ⚠️ **R137**：`bCB` 在 `db/LCOM-*` 的**输入 Schema** 里标注 **`(ReadOnly)`** ⇒ **不**发
            # （**单变量 A/B** 已证明它**不是**成因；厂商记录里它是 `false`）。
            "i_type": 0,
            "description": "",
            # ⚠️ **R137 的取值依据 = 厂商真值**（**只读**读回官方验证模型
            # `Gen Verification\Static-01.mgbx` 的 `GET /DB/LCOM-GEN`）：
            #   {"NO": 1, "NAME": "LCOMB1", "ACTIVE": "ACTIVE", "bCB": false, "iTYPE": 0,
            #    "DESC": "", "vCOMB": [{"ANAL": "ST", "LCNAME": "CASE1", "FACTOR": 1.0}]}
            # ⇒ `ANAL` 的真值是 **"ST"（Static）**；手册 `db/LCOM-STEEL` 示例里的 `"CS"`
            # **不**被真机接受（实测 `400 Unknown Error`）—— **不**照抄手册的错示例。
            "combination_items": [{"ANAL": "ST", "LCNAME": LOAD_CASE, "FACTOR": 1.0}],
        }
    ],
}
"""⚠️ **R136（P157 / 用户裁决 = B）**：`DESIGN.*` 的验算需要**荷载组合**（原生弹窗
「验算荷载组合不存在」）。取值**照手册** `db/LCOM-STEEL` 的示例结构
（`NO` / `NAME` / `ACTIVE` / `bCB` / `iTYPE` / `DESC` / `vCOMB`），
⚠️ **只**把 `vCOMB[0].LCNAME` 换成**本链自建**的工况名 `AXIAL`（**不**臆造取值）。
`combination_kind` = **分派键**（→ `DB.LCOM-STEEL`），**不**是该端点 Schema 里的字段。
"""

ANALYSIS_PARAMETERS: dict[str, Any] = {"analysis_type": "STATIC"}
RESULT_PARAMETERS: dict[str, Any] = {"node_ids": [TOP_NODE]}
"""⚠️ **§13.5 的第 4 步只给 `node=[2]`**（**不**给工况过滤）—— 这里照此办；
工况过滤（`load_cases`）**未**给，避免把「过滤条件不匹配」与「结果为空」混为一谈。"""

DESIGN_PARAMETERS: dict[str, Any] = {
    # ⚠️ **R140（事故驱动）**：原值 `"DESIGN"` **不在**该端点的枚举里
    # （Schema = `ALL` / `ELEMS` / `SECTIONS`，写在 `oneOf[].const`）——
    # 原生对非法枚举回 `200` 但随后**弹模态框并崩溃**（实测）。取值照 Schema。
    "perform_type": "ALL",
    # ⚠️ **P157 / R138**：`DESIGN.*.*-TABLE` 的请求体**由调用方给出**
    # （`adapter.py` 的 `_design_result` 明写「本方法**不**臆造字段」），且该端点的 Schema 要
    # **`Argument`** 信封 + **必填** `TABLE_TYPE`（enum `MEMB`/`PROP`）+
    # `ELEMS`/`SECTIONS`（`oneOf` 必填其一）—— 取值照 `registry/schema/design/steel/
    # KDS-41-30-2022/CODE-TABLE.json`（**不**臆造）。
    # 取值**照手册** `DESIGN/RC/KDS-41-20-2022/BC-TABLE` 的示例形状
    # （`TABLE_TYPE: "MEMB"` + `SECTIONS: [..]` + `PRI_SORT` / `RESULT`）；
    # ⚠️ 手册示例里**没有** `UNIT` 字段 ⇒ **不**臆造它。
    "arguments": {
        "TABLE_TYPE": "MEMB",
        "SECTIONS": [SECTION_ID],
        "PRI_SORT": 1,
        "RESULT": 0,
    },
}

MODEL_READBACK: tuple[str, ...] = ("DB.NODE", "DB.ELEM", "DB.MATL", "DB.SECT")

STEP_LOAD: dict[str, Any] = {
    "order": 2,
    "operation": "MODEL.LOAD.ASSIGN",
    "tool": "engineering_model_assign",
    "label": "荷载（先建工况 AXIAL，再在柱顶加 500 kN 竖向）",
    "parameters": LOAD_PARAMETERS,
    "confirm": True,
    # ⚠️ **R132**：**两个**端点都要**再读**确认 —— 工况 `DB.STLD` **在** ∧ 荷载 `DB.CNLD` **在**
    # （R128：外层键无效时原生静默 `200` 却不建 ⇒ 判据**必须**以再读为准）。
    "readback": ("DB.STLD", "DB.CNLD"),
}
STEP_ANALYSIS: dict[str, Any] = {
    "order": 3,
    "operation": "ANALYSIS.STATIC",
    "tool": "engineering_analysis",
    "label": "分析（STATIC）",
    "parameters": ANALYSIS_PARAMETERS,
    "confirm": True,
    "readback": (),
}
STEP_RESULT: dict[str, Any] = {
    "order": 4,
    "operation": "RESULT.NODE.DISPLACEMENT",
    "tool": "engineering_result",
    "label": "结果（柱顶位移）",
    "parameters": RESULT_PARAMETERS,
    "confirm": False,
    "readback": (),
}
STEP_DESIGN: dict[str, Any] = {
    # ⚠️ **P157 / R140（事故复盘；结论**只**写到有证据的那一步）**
    # ① **请求体已改对**：`CODE-ANAL` 照手册示例发 `{"Argument": {"PERFORM_TYPE": "ALL"}}`
    #    ⇒ 真机 **`200` `{"message": "success"}`**（阶段 1 单独实测，见报告 §2.10）——
    #    所以**不是**「我们的请求形状不对」这一层的问题了。
    # ② **但随后 MIDAS 侧出错**：其「截面验算」对话框弹出并报
    #    **`Error occured while setting unit`**（信息窗口同时显示「开始验算构件- GB50017-17」、
    #    且表格里**已算出结果行**）⇒ 模态框**阻塞 API** ⇒ 应用**崩溃**（实测两次）。
    # ③ 已排除：`GET /DB/UNIT` = `KN / M / KJ / C`（与对话框显示的「单位: kN, m」一致）
    #    ⇒ **不是**模型单位设错。
    # ⇒ **成因在 MIDAS 的验算界面侧**，本批**无法**靠继续调 API 诊断（每次尝试都可能让应用崩溃）
    #    ⇒ 该步记 `SKIPPED`（**未跑通**，**不**声称是产品边界、**也**不声称是我们的 bug）。
    # 恢复条件 = 用户提供「手工跑截面验算时是否也报同一错」的观察，或改用只读取结果表。
    "skip": "not_verified_midas_design_ui_setting_unit_error_blocks_api_and_crashes",
    "order": 5,
    "operation": "DESIGN.STEEL",
    "tool": "engineering_design",
    "label": "设计（钢构件校核）",
    "parameters": DESIGN_PARAMETERS,
    "confirm": True,
    "readback": (),
}


def _tail_steps(start: int, *, with_combination: bool) -> tuple[dict[str, Any], ...]:
    """②–⑤（荷载 / 分析 / 结果 / 设计）—— 两个阶段**同一份**声明，**不**另立判定。

    `start` 只改 `order`（阶段 A 从 2 起、阶段 B 从 8 起），**不**改任何判据。
    ⚠️ `with_combination`：**只**阶段 B 追加 `MODEL.LOAD_COMBINATION.ASSIGN`（**R136**）——
    阶段 A 是 `docs/07` §13.5 的**逐字** 5 步，**不**加任何一步。
    """
    # ⚠️ **R137（实测驱动）**：荷载组合是**分析的输入** —— 组合必须在 `DOC.ANAL` **之前**建，
    # 否则分析**不**为组合算结果，`DESIGN.STEEL` 的 `CODE-TABLE` 会 `400`
    # （实测：组合放在分析**之后**时 `CODE-ANAL` `200` 但 `CODE-TABLE` `400`）。
    # ⚠️ **只**阶段 B 有这一步（阶段 A 是 §13.5 逐字 5 步）。
    combination = (
        (
            {
                "order": start + 1,
                "operation": "MODEL.LOAD_COMBINATION.ASSIGN",
                "tool": "engineering_model_assign",
                "label": "②′ **荷载组合**（`DB.LCOM-STEEL`；R136/R137 —— 分析的输入）",
                "parameters": LOAD_COMBINATION_PARAMETERS,
                "confirm": True,
                "readback": ("DB.LCOM-STEEL",),
            },
        )
        if with_combination
        else ()
    )
    shift = 1 if with_combination else 0
    return (
        {**STEP_LOAD, "order": start},
        *combination,
        {**STEP_ANALYSIS, "order": start + 1 + shift},
        {**STEP_RESULT, "order": start + 2 + shift},
        {**STEP_DESIGN, "order": start + 3 + shift},
    )


SPEC_STEPS: tuple[dict[str, Any], ...] = (
    {
        "order": 1,
        "operation": "BUILD.COLUMN",
        "tool": "engineering_model_build",
        "label": "① 建模（钢柱：2 节点 + 1 单元 + 材质 + 截面）",
        "parameters": COLUMN_PARAMETERS,
        "confirm": True,
        "readback": MODEL_READBACK,
    },
    *_tail_steps(2, with_combination=False),
)
"""**阶段 A = `docs/07` §13.5 逐字**（① `BUILD.COLUMN` + ②–⑤）。"""

SENTINEL_ENDPOINTS: tuple[str, ...] = (
    "DB.CNLD",
    "DB.CONS",
    "DB.ELEM",
    "DB.GRUP",
    "DB.LCOM-STEEL",
    "DB.MATL",
    "DB.NODE",
    "DB.SECT",
    "DB.STLD",
)
"""跑前 / 跑后只读哨兵 = **全部**会被触碰的端点 ∪ 全部前置端点。"""

CLEANUP_ORDER: tuple[tuple[str, str], ...] = (
    ("DB.LCOM-STEEL", "MODEL.LOAD.DELETE", {"combination_kind": COMBINATION_KIND}),
    ("DB.CNLD", "MODEL.LOAD.DELETE", {}),
    ("DB.CONS", "MODEL.BOUNDARY.DELETE", {}),
    ("DB.ELEM", "MODEL.ELEMENT.DELETE", {}),
    ("DB.NODE", "MODEL.NODE.DELETE", {}),
    ("DB.MATL", "MODEL.MATERIAL.DELETE", {}),
    ("DB.SECT", "MODEL.SECTION.DELETE", {}),
    ("DB.STLD", "MODEL.LOAD.DELETE", {}),
)
"""**逆序**清理（先删依赖方，再删被依赖方）；每步**再读确认**。"""


def _substitute_steps(module: Any) -> tuple[dict[str, Any], ...]:
    """**阶段 B 的 ①′**：用 `BUILD.COLUMN` **自己组合**的四个原子 Operation 建模型。

    取值（**不**新造）：
    * **材质** = 本模块的 `_material_parameters()`（**规范库路线**：
      `GB50017-17(S)` + 数据库 `Q355`；由用户在 GEN NX 对话框上给定 —— 见 **R131** 的更正）；
    * **截面** = `probe_interface_paths` 的规范化参数（= 手册 `db/SECT` 示例 `6001`
      `Offset : Left-Top` 的逐字节照抄，**不是**臆造）；
    * **节点 / 单元** = 同模块的规范化参数（P154 / P157 已实测可用）。

    顺序 = 先材质 / 截面（被引用方），再节点，最后单元（引用方）—— 与 `docs/07` §6.5 的组合一致，
    但把**被引用方提前**（`BUILD.COLUMN` 的编排是 NODE → ELEM → MATL → SECT，
    单元会先于材质 / 截面建立）。
    """
    material = _material_parameters()
    section = module._section_parameters(str(SECTION_ID))  # noqa: SLF001
    base = module._node_parameters(str(BASE_NODE), x=0.0, y=0.0, z=0.0)  # noqa: SLF001
    top = module._node_parameters(str(TOP_NODE), x=0.0, y=0.0, z=HEIGHT)  # noqa: SLF001
    element = module._element_parameters(  # noqa: SLF001
        str(ELEMENT_ID),
        nodes=[str(BASE_NODE), str(TOP_NODE)],
        materials=[str(MATERIAL_ID)],
        sections=[str(SECTION_ID)],
    )
    return (
        {
            "order": 1,
            "operation": "MODEL.MATERIAL.ASSIGN",
            "tool": "engineering_model_assign",
            "label": "①′ 材质（`DB.MATL`；**规范库路线**：GB50017-17(S) + 数据库 Q355）",
            "parameters": material,
            "confirm": True,
            "readback": ("DB.MATL",),
        },
        {
            "order": 2,
            "operation": "MODEL.SECTION.ASSIGN",
            "tool": "engineering_model_assign",
            "label": "①′ 截面（`DB.SECT`；取值 = P154 A′ 已实测可用）",
            "parameters": section,
            "confirm": True,
            "readback": ("DB.SECT",),
        },
        {
            "order": 3,
            "operation": "MODEL.NODE.CREATE",
            "tool": "engineering_model_assign",
            "label": "①′ 柱底节点（`DB.NODE`）",
            "parameters": base,
            "confirm": True,
            "readback": ("DB.NODE",),
        },
        {
            "order": 4,
            "operation": "MODEL.NODE.CREATE",
            "tool": "engineering_model_assign",
            "label": "①′ 柱顶节点（`DB.NODE`）",
            "parameters": top,
            "confirm": True,
            "readback": ("DB.NODE",),
        },
        {
            "order": 5,
            "operation": "MODEL.ELEMENT.CREATE",
            "tool": "engineering_model_assign",
            "label": "①′ 单元（`DB.ELEM`，引用自建材质 / 截面）",
            "parameters": element,
            "confirm": True,
            "readback": ("DB.ELEM",),
        },
        {
            "order": 6,
            "operation": "MODEL.BOUNDARY.ASSIGN",
            "tool": "engineering_model_assign",
            "label": "①′ **柱底固定**（`DB.CONS`；`CONSTRAINT` = **7** 位 —— D2 = A 的真机落地）",
            "parameters": _boundary_parameters(),
            "confirm": True,
            "readback": ("DB.CONS",),
        },
        *_tail_steps(7, with_combination=True),
    )


def _load_stack_module(repo: pathlib.Path) -> Any:
    """按路径装载 `probe_interface_paths`（`registry/tools` 不是包）。"""
    path = repo / STACK_TOOL_RELATIVE
    spec = importlib.util.spec_from_file_location("structai_probe_interface_paths_p157", path)
    if spec is None or spec.loader is None:  # pragma: no cover - 环境损坏
        raise SystemExit(f"❌ 无法装载 {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


def _error_of(response: Any) -> dict[str, Any]:
    """接口层响应的错误块（`{}` = 无错误）。"""
    if not isinstance(response, dict):
        return {}
    error = response.get("error")
    if isinstance(error, dict) and error:
        return dict(error)
    if error:
        return {"code": "STRUCTAI-0000", "message": str(error)}
    if response.get("success") is False:
        return {"code": "STRUCTAI-0000", "message": str(response.get("message") or "failed")}
    return {}


def _native_error_of(requests: list[dict[str, Any]]) -> str:
    """该步**原生**拒绝文案（`>= 400` 的最后一条；无 ⇒ 空串）。"""
    texts = [
        str(item.get("native_error") or "")
        for item in requests
        if int(item.get("status") or 0) >= 400
    ]
    return texts[-1][:MAX_NATIVE_ERROR] if texts else ""


def _requests_of(stack: Any) -> list[dict[str, Any]]:
    """接口层**实际**发出的请求（只留方法 / 路径 / 状态 / 请求体 / 原生文案）。"""
    rows: list[dict[str, Any]] = []
    for item in list(stack.log):
        record: dict[str, Any] = {
            "method": str(item.get("method")),
            "path": str(item.get("path")),
            "status": int(item.get("status") or 0),
        }
        if item.get("body") is not None:
            record["body"] = item.get("body")
        if item.get("shape") is not None:
            record["shape"] = item.get("shape")
        if item.get("shape_error"):
            record["shape_error"] = item.get("shape_error")
        if item.get("shape_raw_length") is not None:
            record["shape_raw_length"] = item.get("shape_raw_length")
        text = str(item.get("native_error") or "")
        if text:
            record["native_error"] = text[:MAX_NATIVE_ERROR]
        rows.append(record)
    return rows


def _rows_of(payload: Any) -> list[dict[str, Any]]:
    """从任意嵌套结构里找**结果行**（`rows` 列表；找不到 ⇒ 空）。"""
    if isinstance(payload, dict):
        rows = payload.get("rows")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        for value in payload.values():
            found = _rows_of(value)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _rows_of(value)
            if found:
                return found
    return []


def _numeric(value: Any) -> float | None:
    """能解析成数就返回（**不**臆造；解析不了 ⇒ `None`）。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _collect_numbers(result: Any) -> dict[str, Any]:
    """从结果步骤的响应里**逐条取出**真实数值（**不**硬编码、**不**臆造）。

    只取两类：① 柱顶节点的位移分量（`ux..rz`）；② 设计结果的 `ratio` / `status`。
    """
    numbers: dict[str, Any] = {}
    rows = _rows_of(result)
    for row in rows:
        node = row.get("node_id")
        if node is not None and str(node) == str(TOP_NODE):
            for name in ("ux", "uy", "uz", "rx", "ry", "rz"):
                if name in row:
                    value = _numeric(row.get(name))
                    if value is not None:
                        numbers[f"displacement.{name}"] = value
            break
    for row in rows:
        ratio = _numeric(row.get("ratio"))
        if ratio is not None:
            numbers["design.ratio"] = ratio
            if row.get("status") is not None:
                numbers["design.status"] = str(row.get("status"))
            break
    return numbers


def _readback_of(stack: Any, step: dict[str, Any]) -> dict[str, Any]:
    """该步声明的端点的**再读**结果（`{端点: {ids, present}}`；R119 / R128 的判据）。"""
    readback: dict[str, Any] = {}
    for endpoint in step.get("readback") or ():
        ids = stack.read_ids(str(endpoint))
        readback[str(endpoint)] = {"ids": list(ids), "present": bool(ids)}
    return readback


async def _run_step(stack: Any, step: dict[str, Any]) -> dict[str, Any]:
    """跑一步（判据**只**看接口层响应 + 再读）。

    ⚠️ 带 `skip` 的步骤 = **已知产品边界** ⇒ **不**发任何请求，如实记 `SKIPPED`。
    """
    if step.get("skip"):
        return {
            "order": int(step["order"]),
            "operation": str(step["operation"]),
            "tool": str(step["tool"]),
            "label": str(step["label"]),
            "status": SKIPPED,
            "detail": str(step["skip"]),
            "error": {},
            "task": {},
            "native_error": "",
            "readback": {},
            "numbers": {},
            "attempts": 0,
            "requests": [],
        }
    stack.log.clear()
    row: dict[str, Any] = {
        "order": int(step["order"]),
        "operation": str(step["operation"]),
        "tool": str(step["tool"]),
        "label": str(step["label"]),
        "status": FAILED,
        "detail": "",
        "error": {},
        "task": {},
        "native_error": "",
        "readback": {},
        "numbers": {},
        "attempts": 0,
        "requests": [],
    }
    # ⚠️ **R135**：取结果步骤**有界**重试（`DOC.ANAL` 是触发式的 ⇒ 结果稍后才可用）。
    is_result = str(step["operation"]).startswith("RESULT.")
    limit = RESULT_ATTEMPTS if is_result else 1
    outcome: dict[str, Any] = {}
    while True:
        row["attempts"] = int(row["attempts"]) + 1
        try:
            outcome = await stack.run_operation(
                str(step["tool"]),
                str(step["operation"]),
                dict(step["parameters"]),
                confirm=bool(step["confirm"]),
            )
        except Exception as error:  # noqa: BLE001 - 逐条隔离（单条失败不打死整批）
            row["detail"] = f"{type(error).__name__}:{error}"[:200]
            row["requests"] = _requests_of(stack)
            return row
        row["error"] = _error_of(outcome["response"])
        task = dict(outcome.get("task") or {})
        row["task"] = task
        if task:
            row["error"] = task.get("error") or row["error"]
            if str(task.get("status")) != "COMPLETED":
                row["error"] = row["error"] or {"code": "STRUCTAI-5000", "message": "task_failed"}
        row["native_error"] = _native_error_of(_requests_of(stack))
        if not row["error"] or int(row["attempts"]) >= limit:
            break
        await asyncio.sleep(RESULT_DELAY_SECONDS)
    if row["task"] and str(row["task"].get("status")) != "COMPLETED":
        # ⚠️ 任务**失败**也要把**再读**记下来（它正是「哪一步真的落库了」的证据）
        row["readback"] = _readback_of(stack, step)
        row["detail"] = f"task_{str(row['task'].get('status')).lower()}"
        row["requests"] = _requests_of(stack)
        return row
    readback = _readback_of(stack, step)
    row["readback"] = readback
    if row["error"]:
        row["detail"] = f"interface_error:{row['error'].get('code')}"
        row["requests"] = _requests_of(stack)
        return row
    if readback and not all(bool(item["present"]) for item in readback.values()):
        row["detail"] = "readback_absent"
        row["requests"] = _requests_of(stack)
        return row
    result = outcome.get("result") or outcome.get("data")
    row["numbers"] = _collect_numbers(result)
    if str(step["operation"]).startswith("RESULT.") and not _rows_of(result):
        row["detail"] = "empty_result_table"
        row["requests"] = _requests_of(stack)
        return row
    if str(step["operation"]).startswith("DESIGN.") and not _rows_of(result):
        row["detail"] = "empty_design_table"
        row["requests"] = _requests_of(stack)
        return row
    row["status"] = PASSED
    row["requests"] = _requests_of(stack)
    return row


async def _run_chain(
    stack: Any, steps: tuple[dict[str, Any], ...], health_path: str
) -> list[dict[str, Any]]:
    """按顺序跑一条链（**首个失败即停**，其余记 `NOT_RUN`）。"""
    rows: list[dict[str, Any]] = []
    for step in steps:
        row = await _run_step(stack, step)
        rows.append(row)
        print(
            f"  [{row['order']}] {row['operation']} = {row['status']} "
            f"{row.get('detail') or ''} {row.get('numbers') or ''}"
        )
        if row["status"] in (PASSED, SKIPPED):
            try:
                health = int(stack.client.get(health_path).status_code)
            except Exception as error:  # noqa: BLE001 - 传输失败如实中止
                print(f"  ⚠️ 健康检查传输失败（{type(error).__name__}）⇒ 立即中止")
                break
            if health != 200:
                print(f"  ⚠️ 健康检查 → {health}（立即中止）")
                break
            continue
        for rest in steps[len(rows) :]:
            rows.append(
                {
                    "order": int(rest["order"]),
                    "operation": str(rest["operation"]),
                    "tool": str(rest["tool"]),
                    "label": str(rest["label"]),
                    "status": NOT_RUN,
                    "detail": "chain_stopped_at_previous_failure",
                    "error": {},
                    "task": {},
                    "native_error": "",
                    "readback": {},
                    "numbers": {},
                    "requests": [],
                }
            )
        break
    return rows


async def _cleanup(stack: Any) -> list[dict[str, Any]]:
    """**逆序**清理 + **收尾再读**（R119）。

    ⚠️ **P157 加固（实测驱动）**：`DB.CNLD` / `DB.CONS` **没有**可用的删除路由
    （`MODEL.LOAD.DELETE` 只覆盖 `DB.STLD` / `DB.BMLD`），它们靠**删除节点**连带清掉 ⇒
    按依赖顺序删完之后**必须**再读一次，`gone` 记的是**最终**状态（**不**是"自己那一步之后"）。
    """
    cleanup: list[dict[str, Any]] = []
    for endpoint, operation, extra in CLEANUP_ORDER:
        stack.log.clear()
        before = list(stack.read_ids(endpoint))
        if not before:
            cleanup.append({"endpoint": endpoint, "operation": operation, "ids": [], "gone": True})
            continue
        outcome = await stack.run_operation(
            "engineering_model_delete",
            operation,
            {"item_ids": before, **extra},
            confirm=True,
        )
        after = list(stack.read_ids(endpoint))
        cleanup.append(
            {
                "endpoint": endpoint,
                "operation": operation,
                "ids": before,
                "remaining": list(after),
                "gone": not after,
                "error": (
                    _error_of(outcome["response"])
                    or dict(outcome.get("task") or {}).get("error")
                    or {}
                ),
                "requests": _requests_of(stack),
            }
        )
    # ⚠️ **收尾再读**：以**最终**状态为准（连带删除 / 后序步骤可能已经把前面的清掉了）
    for item in cleanup:
        remaining = list(stack.read_ids(str(item["endpoint"])))
        item["remaining"] = remaining
        item["gone"] = not remaining
    return cleanup


async def _analysis_persists(stack: Any) -> bool | None:
    """分析结果是否仍在（`POST.TABLE.DISPLACEMENTG` 是否还能取到行）。"""
    stack.log.clear()
    try:
        outcome = await stack.run_operation(
            "engineering_result", "RESULT.NODE.DISPLACEMENT", dict(RESULT_PARAMETERS)
        )
    except Exception:  # noqa: BLE001 - 传输 / 装配失败 ⇒ 未知
        return None
    if _error_of(outcome["response"]):
        return False
    return bool(_rows_of(outcome.get("result") or outcome.get("data")))


async def _probe(
    repo: pathlib.Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """真机五步链：哨兵 → **阶段 A** →（①失败则）逆序清理 → **阶段 B** → 逆序清理 → 哨兵。"""
    module = _load_stack_module(repo)
    spec_rows: list[dict[str, Any]] = []
    substitute_rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "aborted": "",
        "sentinel_before": {},
        "sentinel_mid": {},
        "sentinel_after": {},
        "cleanup": [],
        "cleanup_mid": [],
        "residue": {},
        "analysis_result_persists": None,
        "numbers": {},
        "substitute_reason": "",
    }
    with tempfile.TemporaryDirectory(prefix="structai-p157-") as workdir:
        # ⚠️ **Contract Test 口径**（`docs/04` §71 的 L4/L5）：本探针要**测量**旗舰链，
        # 而 `DOC.ANAL` 的 `availability` 是 **`untested`**（`verified_on = []`）⇒ 生产路径下会被
        # `registry_mapping_not_verified`（`STRUCTAI-3000`）拦住。`allow_unverified=True` 是
        # `MidasAdapter` **唯一**为此存在的开关（`adapter.py` 裁决 4：「只服务 Contract Test」；
        # `write_probe.py` 的 L5 写路径实测**同样**用它）。⚠️ **不**改 `registry/**` 的
        # `availability` —— 本次**测量**的结论只作**证据**，升级与否属**数据侧裁决**。
        async with module._Stack(  # noqa: SLF001
            repo, pathlib.Path(workdir), allow_unverified=True, capture_shape=True
        ) as stack:
            before = stack.sentinel(SENTINEL_ENDPOINTS)
            summary["sentinel_before"] = before
            unreadable = sorted(
                key
                for key, value in before.items()
                if int(value.get("status") or 0) == 0 or value.get("error")
            )
            if unreadable:
                summary["aborted"] = (
                    "跑前哨兵**不可读**（实例不可达 / 传输失败）⇒ 一个请求都不发："
                    f"{unreadable[:5]}（P138c：读不到就**不盲写**）"
                )
                print(f"⚠️ {summary['aborted']}")
                summary["sentinel_after"] = before
                summary["sentinel_mid"] = before
                return spec_rows, substitute_rows, summary
            blocked = {key: value["ids"] for key, value in before.items() if value.get("ids")}
            if blocked:
                summary["aborted"] = f"跑前哨兵**非空** ⇒ 一个写请求都不发（{sorted(blocked)[:5]}）"
                print(f"⚠️ {summary['aborted']}")
                summary["sentinel_after"] = before
                summary["sentinel_mid"] = before
                return spec_rows, substitute_rows, summary

            print("=== 阶段 A：docs/07 §13.5 逐字（① BUILD.COLUMN + ②–⑤）===")
            spec_rows = await _run_chain(stack, SPEC_STEPS, str(module.HEALTH_PATH))
            for row in spec_rows:
                summary["numbers"].update(row["numbers"])

            build_ok = bool(spec_rows) and spec_rows[0]["status"] == PASSED
            if not build_ok:
                summary["substitute_reason"] = (
                    "阶段 A 的 ① `BUILD.COLUMN` 未通过 ⇒ 用 `docs/07` §6.5 的**同一组原子"
                    " Operation** 建模型（①′）后跑 ②–⑤；**不**掩盖 ① 的失败。"
                )
                summary["cleanup_mid"] = await _cleanup(stack)
                mid = stack.sentinel(SENTINEL_ENDPOINTS)
                summary["sentinel_mid"] = mid
                mid_blocked = {key: value["ids"] for key, value in mid.items() if value.get("ids")}
                if mid_blocked:
                    summary["aborted"] = (
                        f"阶段 A 清理后哨兵**非空** ⇒ **不**进入阶段 B（{sorted(mid_blocked)[:5]}）"
                    )
                    print(f"⚠️ {summary['aborted']}")
                else:
                    print("=== 阶段 B：替代前缀（①′ 原子 Operation 组合）+ ②–⑤ ===")
                    substitute_rows = await _run_chain(
                        stack, _substitute_steps(module), str(module.HEALTH_PATH)
                    )
                    for row in substitute_rows:
                        summary["numbers"].update(row["numbers"])

            summary["cleanup"] = await _cleanup(stack)
            after = stack.sentinel(SENTINEL_ENDPOINTS)
            summary["sentinel_after"] = after
            summary["residue"] = {
                key: value["ids"] for key, value in after.items() if value.get("ids")
            }
            analyzed = any(
                row["operation"] == "ANALYSIS.STATIC" and row["status"] == PASSED
                for row in (*spec_rows, *substitute_rows)
            )
            if analyzed:
                summary["analysis_result_persists"] = await _analysis_persists(stack)
    return spec_rows, substitute_rows, summary


def _counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[str(row["status"])] = counts.get(str(row["status"]), 0) + 1
    return counts


def _verdict(rows: list[dict[str, Any]], total: int) -> str:
    return PASSED if _counts(rows).get(PASSED) == total else "NOT_PASSED"


def _write(
    repo: pathlib.Path,
    spec_rows: list[dict[str, Any]],
    substitute_rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> int:
    """落证据并给出结论。"""
    residue = dict(summary.get("residue") or {})
    document = {
        "note": [
            "P157：`docs/07` §13.5 的**旗舰五步链**在**真机**上的端到端实测（判据走**接口层**）。",
            "链路：`BUILD.COLUMN → MODEL.LOAD.ASSIGN → ANALYSIS.STATIC → "
            "RESULT.NODE.DISPLACEMENT → DESIGN.STEEL`（`docs/07` §13.5 / `docs/04` §74）。",
            "**阶段 A** = `docs/07` §13.5 逐字；**阶段 B** = **仅当** ① 失败时，用 §6.5 里 "
            "`BUILD.COLUMN` **自己组合**的原子 Operation 建模型（①′）后跑 ②–⑤"
            "（材质 = **规范库路线** `GB50017-17(S)` + 数据库 `Q355`；"
            "截面 = 手册 `db/SECT` 示例 6001；**不**新造取值、**不**掩盖 ① 的失败）。",
            "判定：每步 `PASSED` 的判据见工具 docstring（再读 / 行数 / 无错误）；"
            "**数值不硬编码**，逐条取自接口层响应（只留数值，不留响应原文）。",
            "纪律：只碰自建编号 · `DELETE` 必带路径 key · 删除以「再读确认不在」为准（R119）· "
            "跑前 / 跑后只读哨兵（**读不到就不盲写**；**跑前非空就不写**）· 逆序清理 · "
            f"阶段 A **{len(SPEC_STEPS)}** 步 / 阶段 B **{len(substitute_rows)}** 步"
            f"（请求数 ≤ {MAX_REQUESTS}）。",
            "⚠️ 接口层的 `MODEL.LOAD.DELETE` **不**覆盖 `DB.CNLD` ⇒ "
            "节点荷载靠**删除节点**连带清掉。",
            "⚠️ **分析结果可能清不掉**（不在本工具清理能力内）⇒ "
            "`analysis_result_persists` 如实记录。",
            "证据里**绝不**出现凭据；**失败**响应只留 `error.message` 前 200 字。",
            "⚠️ **Contract Test 口径**：`allow_unverified = True`（`docs/04` §71 的 L4/L5；"
            "`MidasAdapter` 唯一为此存在的开关）—— 因为 `DOC.ANAL` 的 `availability` 是 "
            "`untested`。**不**改 `registry/**` 的 `availability`；本次**测量**只作证据。",
            "⚠️ **ASYNC 判定**：`engineering_analysis` / `engineering_design` / "
            "`engineering_model_build` / `engineering_model_delete` 在 MCP 层只回 `QUEUED` ⇒ "
            "**必须**看**任务终态**（`QUEUED → FAILED` 会被误判为成功）。",
            "生成器 = `registry/tools/probe_flagship_chain.py --probe`（**零** `app/**` 改动）。",
        ],
        "criterion_version": CRITERION_VERSION,
        "instance": {
            "alias": INSTANCE_ALIAS,
            "product": INSTANCE_PRODUCT,
            "base_url": os.environ.get("MIDAS_BASE_URL", ""),
            "probed_at": PROBED_AT,
        },
        "spec": {
            "prompt": "6 m 高 Q355B 钢柱（H400×400×13×21），柱底固定，柱顶 500 kN 竖向荷载",
            "load_case": LOAD_CASE,
            "axial_fz": AXIAL_FZ,
            "top_node": TOP_NODE,
            "element_id": ELEMENT_ID,
        },
        "steps": spec_rows,
        "counts": _counts(spec_rows),
        "verdict": _verdict(spec_rows, len(SPEC_STEPS)),
        "substituted": substitute_rows,
        "substituted_counts": _counts(substitute_rows),
        "substituted_verdict": (
            _verdict(substitute_rows, len(substitute_rows)) if substitute_rows else NOT_RUN
        ),
        "substitute_reason": str(summary.get("substitute_reason") or ""),
        "aborted": str(summary.get("aborted") or ""),
        "sentinel_endpoints": list(SENTINEL_ENDPOINTS),
        "sentinel_before": summary.get("sentinel_before") or {},
        "sentinel_mid": summary.get("sentinel_mid") or {},
        "sentinel_after": summary.get("sentinel_after") or {},
        "cleanup_mid": summary.get("cleanup_mid") or [],
        "cleanup": summary.get("cleanup") or [],
        "residue": residue,
        "analysis_result_persists": summary.get("analysis_result_persists"),
        "numbers": summary.get("numbers") or {},
        "requests": [
            item for row in (*spec_rows, *substitute_rows) for item in (row.get("requests") or [])
        ][:MAX_REQUESTS],
    }
    path = repo / "registry" / EVIDENCE_RELATIVE
    if summary.get("aborted") and path.is_file():
        print(f"⚠️ 本次中止（{str(summary['aborted'])[:80]}）⇒ **不覆盖**既有证据")
    else:
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "verdict =",
        document["verdict"],
        " counts =",
        document["counts"],
        " 替代链 =",
        document["substituted_verdict"],
        document["substituted_counts"],
        " 中止 =",
        bool(summary.get("aborted")),
        " 残留 =",
        sorted(residue),
    )
    print(f"已写入 registry/{EVIDENCE_RELATIVE}")
    return 0 if document["verdict"] == PASSED and not summary.get("aborted") else 1


def probe(repo: pathlib.Path) -> int:
    """真机五步链（需要 `MIDAS_BASE_URL` / `MIDAS_MAPI_KEY`）。"""
    base_url = os.environ.get("MIDAS_BASE_URL", "").rstrip("/")
    key_value = os.environ.get("MIDAS_MAPI_KEY", "")
    if not base_url or not key_value:
        print("❌ --probe 需要 MIDAS_BASE_URL / MIDAS_MAPI_KEY（见 scripts/load-midas-env.ps1）")
        return 1
    spec_rows, substitute_rows, summary = asyncio.run(_probe(repo))
    return _write(repo, spec_rows, substitute_rows, summary)


def _check_rows(rows: list[dict[str, Any]], expected: list[str], problems: list[str]) -> None:
    """逐行断言一条链（判定与判据一致、失败必有成因）。"""
    if [str(row.get("operation")) for row in rows] != expected:
        problems.append("步集 ≠ 声明（判定点唯一）")
    for row in rows:
        status = str(row["status"])
        if status not in {PASSED, FAILED, NOT_RUN, SKIPPED}:
            problems.append(f"{row.get('operation')}: 未知状态 {status}")
        if status == PASSED and row.get("error"):
            problems.append(f"{row.get('operation')}: PASSED 却带接口错误")
        if status == PASSED and row.get("native_error"):
            problems.append(f"{row.get('operation')}: PASSED 却留了原生原文")
        if status == PASSED and row.get("task") and str(row["task"].get("status")) != "COMPLETED":
            problems.append(f"{row.get('operation')}: PASSED 但 ASYNC 任务未 COMPLETED")
        if status == FAILED and not (row.get("detail") or row.get("native_error")):
            problems.append(f"{row.get('operation')}: FAILED 但没有成因")
        if status == SKIPPED and not row.get("detail"):
            problems.append(f"{row.get('operation')}: SKIPPED 但没有登记成因")
        if status == SKIPPED and row.get("requests"):
            problems.append(f"{row.get('operation')}: SKIPPED 却发了请求")


def check(repo: pathlib.Path) -> int:
    """离线断言：证据自洽（步集 · 判定与判据一致 · 清理确认 · 计数与结论一致）。"""
    document = _read_json(repo / "registry" / EVIDENCE_RELATIVE)
    if not document:
        print(f"❌ 缺证据 registry/{EVIDENCE_RELATIVE}（先跑 --probe）")
        return 1
    problems: list[str] = []
    if int(document.get("criterion_version") or 0) != CRITERION_VERSION:
        problems.append(f"{EVIDENCE_RELATIVE}: criterion_version 不符")
    steps = list(document.get("steps") or [])
    _check_rows(steps, [str(item["operation"]) for item in SPEC_STEPS], problems)
    if _counts(steps) != dict(document.get("counts") or {}):
        problems.append(f"{EVIDENCE_RELATIVE}: counts 与逐行不符")
    if str(document.get("verdict")) != _verdict(steps, len(SPEC_STEPS)):
        problems.append(f"{EVIDENCE_RELATIVE}: verdict 与逐行不符")
    substituted = list(document.get("substituted") or [])
    if substituted:
        _check_rows(
            substituted,
            [str(item["operation"]) for item in _substitute_steps(_load_stack_module(repo))],
            problems,
        )
        if _counts(substituted) != dict(document.get("substituted_counts") or {}):
            problems.append(f"{EVIDENCE_RELATIVE}: substituted_counts 与逐行不符")
        if str(document.get("substituted_verdict")) != _verdict(substituted, len(substituted)):
            problems.append(f"{EVIDENCE_RELATIVE}: substituted_verdict 与逐行不符")
        if not str(document.get("substitute_reason") or ""):
            problems.append(f"{EVIDENCE_RELATIVE}: 有替代链却没有 substitute_reason")
    for item in [
        *(document.get("cleanup_mid") or []),
        *(document.get("cleanup") or []),
    ]:
        if not item.get("gone"):
            problems.append(f"清理未确认：{item.get('endpoint')}（剩 {item.get('remaining')}）")
    if document.get("aborted"):
        problems.append(f"{EVIDENCE_RELATIVE}: aborted 非空（{document['aborted']}）")
    if len(document.get("requests") or []) > MAX_REQUESTS:
        problems.append(f"{EVIDENCE_RELATIVE}: 请求数 > {MAX_REQUESTS}")
    if problems:
        print("❌ 旗舰链证据不自洽：")
        for item in problems:
            print(f"  - {item}")
        return 1
    print(
        f"✅ 旗舰链证据自洽：阶段 A {len(steps)} 步（{document.get('counts')}）· "
        f"结论 = `{document.get('verdict')}` · 替代链 {len(substituted)} 步"
        f"（{document.get('substituted_counts')}）= `{document.get('substituted_verdict')}` · "
        f"清理逐条确认 · 残留如实披露（{sorted(document.get('residue') or {})}）"
    )
    return 0


def summary(repo: pathlib.Path) -> int:
    """打印摘要（只读）。"""
    document = _read_json(repo / "registry" / EVIDENCE_RELATIVE)
    if not document:
        print(f"❌ 缺证据 registry/{EVIDENCE_RELATIVE}（先跑 --probe）")
        return 1
    print(f"`docs/07` §13.5 旗舰五步链：判据版本 {document.get('criterion_version')}")
    print(f"  实例：{document.get('instance')}")
    print(f"  阶段 A（规格链）结论：{document.get('verdict')} · {document.get('counts')}")
    for row in document.get("steps") or []:
        print(
            f"    [{row['order']}] {row['operation']:28s} {row['status']:8s} "
            f"{row.get('detail') or ''} {row.get('numbers') or ''}"
        )
    print(
        f"  阶段 B（替代前缀）结论：{document.get('substituted_verdict')} · "
        f"{document.get('substituted_counts')}"
    )
    for row in document.get("substituted") or []:
        print(
            f"    [{row['order']}] {row['operation']:28s} {row['status']:8s} "
            f"{row.get('detail') or ''} {row.get('numbers') or ''}"
        )
    print(f"  数值：{document.get('numbers')}")
    print(f"  残留：{document.get('residue')}")
    print(f"  分析结果仍在 = {document.get('analysis_result_persists')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="P157：docs/07 §13.5 旗舰五步链的真机实测")
    parser.add_argument("--repo", default=REPO_DEFAULT, help="仓库根目录（默认当前目录）")
    parser.add_argument("--probe", action="store_true", help="真机五步链（需要 MIDAS_* 环境）")
    parser.add_argument("--check", action="store_true", help="离线：断言证据自洽")
    parser.add_argument("--summary", action="store_true", help="打印摘要")
    args = parser.parse_args(argv)
    repo = pathlib.Path(args.repo).resolve()
    if args.probe:
        return probe(repo)
    if args.check:
        return check(repo)
    if args.summary:
        return summary(repo)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
