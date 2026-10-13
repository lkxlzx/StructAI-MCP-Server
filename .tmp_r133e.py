"""P159 临时：旗舰链的第 0 步 = 先定单位（R133）（跑完即删）。"""

from __future__ import annotations

import pathlib

REPO = pathlib.Path(__file__).resolve().parent
path = REPO / "registry/tools/probe_flagship_chain.py"
raw = path.read_text(encoding="utf-8")


def sub(old: str, new: str) -> None:
    global raw
    hits = raw.count(old)
    assert hits == 1, (old[:70], hits)
    raw = raw.replace(old, new, 1)


# ① 参数常量
sub(
    "LOAD_COMBINATION_PARAMETERS: dict[str, Any] = {\n",
    "UNIT_PARAMETERS: dict[str, Any] = {\n"
    "    # ⚠️ **P159 / R133（用户裁决）**：单位是**输入**（UI 新建模型时选 / AI 建模时**先定口径**），\n"
    "    # **不**在核心里写死 ⇒ 本链把它作为**第 0 步**显式给出。取值 = 该实例的**实测默认**\n"
    "    # （P157 `GET /DB/UNIT` = `{\"FORCE\": \"KN\", \"DIST\": \"M\", \"HEAT\": \"KJ\", \"TEMPER\": \"C\"}`）。\n"
    '    "unit": [{"id": "1", "force": "KN", "dist": "M", "heat": "KJ", "temper": "C"}],\n'
    "}\n"
    '"""单位系统（`DB.UNIT`；**四个字段全给** —— 缺一即 `transformer_required_field_missing`）。"""\n\n'
    "LOAD_COMBINATION_PARAMETERS: dict[str, Any] = {\n",
)

# ② 步序列：第 0 步
sub(
    "    return (\n"
    "        {\n"
    '            "order": 1,\n'
    '            "operation": "MODEL.MATERIAL.ASSIGN",\n',
    "    return (\n"
    "        {\n"
    '            "order": 0,\n'
    '            "operation": "MODEL.UNIT.ASSIGN",\n'
    '            "tool": "engineering_model_assign",\n'
    '            "label": "⓪ **先定单位口径**（`DB.UNIT`；R133 —— UI / AI 提示词的**输入**）",\n'
    '            "parameters": UNIT_PARAMETERS,\n'
    '            "confirm": True,\n'
    '            "readback": ("DB.UNIT",),\n'
    "        },\n"
    "        {\n"
    '            "order": 1,\n'
    '            "operation": "MODEL.MATERIAL.ASSIGN",\n',
)

path.write_text(raw, encoding="utf-8")
print("OK 链的第 0 步 = 定单位")
