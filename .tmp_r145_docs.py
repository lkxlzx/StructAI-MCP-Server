"""P160c 临时：台账补 R145（跑完即删）。"""

from __future__ import annotations

import pathlib

REPO = pathlib.Path(__file__).resolve().parent


def patch(relative: str, pairs: tuple[tuple[str, str], ...]) -> None:
    path = REPO / relative
    raw = path.read_text(encoding="utf-8")
    applied = 0
    for old, new in pairs:
        hits = raw.count(old)
        if hits == 0:
            continue
        raw = raw.replace(old, new, 1)
        applied += 1
    path.write_text(raw, encoding="utf-8")
    print(f"OK {relative}: {applied} 处")


patch(
    "docs/07_开发方案与任务续接_v1.0.md",
    (
        (
            "| **R140** |",
            "| **R145** | **`DOC.NEW` 带路径 ⇒ 原生**接受但忽略**（`200` 假成功），项目**仍无路径**"
            "**（P160c 新发现；✅ **已闭环**）** | **P160c** 实测（**用户要求"NEW 也必须带路径"后验证**）："
            "`POST /gen/DOC/NEW` 体 = `{\"Argument\": \"<路径>\"}` ⇒ 原生回 **`200`**，但"
            "**文件没创建、项目仍无路径** ⇒ 紧接着的 `SAVE` 走「另存为」弹窗并**挂起 API**"
            "（体形态见 `registry/live/` 未落盘；请求体已实测打印）。⚠️ 手册体本来就是 `{}` "
            "| ✅ **已闭环**（`app/**` = `adapter.py`）：`DOC.NEW` **不**在 `DOC_PATH_OPERATIONS` 里；"
            "给 `NEW` 传路径 ⇒ 体**仍是 `{}`**（`_doc_arguments` 的提前返回，**不**发原生会忽略的体）；"
            "`_remember_project_path` 对 `NEW` **清空**路径 ⇒ 之后的 `SAVE` 被拒（**零请求**）。"
            "**结论**：**唯一**给项目路径的办法是 `SAVE_AS` / `OPEN` "
            "| `tests/test_midas_doc_saveas_shape_p160c.py`（R145 三项） |\n"
            "| **R140** |",
        ),
    ),
)

patch(
    "docs/08_会话交接与续接提示词_v1.0.md",
    (
        (
            "⚠️ **R144**：`NEW` 之后**尽快** `SAVE_AS`"
            "（无路径 + 自动保存 ⇒ 原生自己弹窗挂起 API）",
            "⚠️ **R144**：`NEW` 之后**尽快** `SAVE_AS`"
            "（无路径 + 自动保存 ⇒ 原生自己弹窗挂起 API）；"
            "⚠️ **R145**：**`NEW` 带路径无效**（原生接受但忽略）⇒ **唯一**给项目路径的办法是 "
            "`SAVE_AS` / `OPEN`；核心已把 `NEW` 的体固定为 `{}` 并**清空**路径状态",
        ),
    ),
)

print("完成")
