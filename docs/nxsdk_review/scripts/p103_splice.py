"""把更正后的 §3 / §5 / §6 拼回 P164-c 报告（保行尾）。"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
REPORT = REPO / "docs" / "reports" / "P164-c_配置步真机验证_v1.0.md"
TMP = REPO / ".tmp_analysis"

new3 = (TMP / "p164c_section3.md").read_text(encoding="utf-8")
new5 = (TMP / "p164c_section5.md").read_text(encoding="utf-8")
new6 = """## 6. 本批的残留（**如实披露**）

清理**改走规范路由**（`/DB/DCON`）之后，残留从 2 条降到 **1** 条：

| 端点 | 跑前 | 跑后 | 说明 |
| --- | --- | --- | --- |
| `DESIGN/RC/DRC` | `{}` | **`{}`** | ✅ 用 `/DB/DCON` 的 `DELETE` **真的清空了** |
| `DESIGN/RC/KDS-41-20-2022/DCO` | `{}` | `{}` | ✅ 已清空 |
| `DESIGN/SRC/AIK-SRC2K/DCO` | `{}` | `{}` | ✅ 已清空 |
| `DESIGN/SRC/AIK-SRC2K/DSRC` | `{}` | `{"1": {"DGNCODE": "AIK-SRC2K"}}` | ⚠️ **无规范路由** ⇒ 无法删除；其唯一合法值**就是**默认值 |

**顺带清掉的（非本批造成）**：`DESIGN/STEEL/DSTL` 与 `DESIGN/STEEL/KDS-41-30-2022/DCO`
原是 **P157 遗留**的配置值（`KDS 41 30 : 2022` 等），本批验证族级规则时经 `/DB/DSTL` 的 `DELETE`
**一并清空** ⇒ 现在是 `{}`（比跑前更干净）。

**未触碰**：`DESIGN/*/DCTL`（三条都是 `{"FRAMEX":"Braced Non-sway", …}`）—— 它们在跑前就存在、
**三族完全相同**，是 **app 默认值**而非残留 ⇒ **不动**。

**模型侧**：节点 / 单元 / 材料 / 截面 / 荷载 / 工况 **全 0**（本批**未**触碰）。

---
"""

text = REPORT.read_text(encoding="utf-8")
lines = text.splitlines(keepends=True)


def block(start_prefix: str, end_prefix: str) -> tuple[int, int]:
    start = next(i for i, line in enumerate(lines) if line.startswith(start_prefix))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith(end_prefix))
    return start, end


# §6 先做（行号在后面），再做 §5、§3
s6, e6 = block("## 6. 本批的残留", "## 7. ")
lines[s6:e6] = [new6, "\n"]
s5, e5 = block("## 5. 📌", "## 6. ")
lines[s5:e5] = [new5, "\n"]
s3, e3 = block("## 3. ⚠️ 新发现", "## 4. ")
lines[s3:e3] = [new3, "\n"]

REPORT.write_text("".join(lines), encoding="utf-8", newline="")
print("spliced §3 / §5 / §6")
for i, line in enumerate("".join(lines).splitlines(), 1):
    if line.startswith("## "):
        print(f"  {i}: {line}")
