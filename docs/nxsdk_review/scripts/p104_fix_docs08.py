"""更正 docs/08 §3 的 P164-c 行（把两条错误结论换成实测事实）。"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
P = Path(r"E:\MCP\MMCP\docs\08_会话交接与续接提示词_v1.0.md")
text = P.read_text(encoding="utf-8")

OLD_4 = (
    "④ **新发现（本批最重要）**：`DESIGN.*` 配置端点的 **`DELETE` 语义与「删除」不符** —— "
    "**4 个里只有 2 个**真的清空；`DESIGN.RC.DRC` 被换成**服务端默认 `GB/T50010-10`**、"
    "`DESIGN.SRC.AIK-SRC2K.DSRC` 是**静默 no-op**（穷举 `DELETE /{path}/1` · 带体 `DELETE` · "
    "`PUT {\"Assign\":{}}` · `DGNCODE:\"\"`(400) 均无效）⇒ 设计规范代码是**单例且必须存在**，"
    "**无法**回到未选状态 ⇒ **必然留痕**。这是**第 5 / 6 次**实测到「原生静默 `200` 却什么都不做」。"
)
NEW_4 = (
    "④ **新发现（本批最重要，且**推翻了初版结论**）**：`DELETE` 语义**按路由族不同** —— "
    "**`/DESIGN/<族>/<模块>`（未编入索引）的 `DELETE` = 「把该模块的设置写回产品默认值」**"
    "（实测 STEEL → `GB50017-17`、RC → `GB/T50010-10`），**不是**删除，且其响应体**回显删除前的状态**；"
    "**`/db/*`（编入索引）的 `DELETE` 才是真删除**（⇒ `{}`）。两条路由**作用于同一份数据**"
    "（给别名 `PUT`，规范路由 `GET` 立刻可见）。⚠️ **初版曾错误地写成「单例且必须存在、选过就回不到未选」**"
    "—— 那是**只测了别名路由**且**没查手册路由索引**；真相由 `en/Design/README.md`（`/db/DCON` = RC Design Code）"
    "+ `Unindexed/DESIGN/RC/DRC-…`（`/DESIGN/RC/DRC`，响应根键 `DCON`）定案。"
    "**SRC 看起来像 no-op 的真因**：它**没有** `/db/*` 规范路由（索引里只有 `/db/DSTL`/`/db/DCON`，"
    "**无 `/db/DSRC`**）⇒ 只能「重置」，而其唯一合法值 `AIK-SRC2K` **就是**默认值 ⇒ 重置与 no-op **不可区分**。"
    "清理改走规范路由后：**清空 3 / 未清空 1**（唯一剩下 SRC）。"
)
OLD_7 = (
    "⑦ **新登记的潜在数据缺口**：`DESIGN.RC.DRC` 的 `DGNCODE` 枚举**只有 1 个值**"
    "（`KDS 41 20 : 2022`），而手册「RC Design Code」值表里还有 `GB/T50010-10`"
    "（**正是服务端 `DELETE` 后的默认值**）⇒ 我方枚举会**拒掉服务端自己在用的值**；"
    "⚠️ **本批不修**（值表机械抽取需单独一次干净的证据作业）。"
)
NEW_7 = (
    "⑦ **~~潜在数据缺口~~ 已撤回（初版判断错误）**：初版称「`DESIGN.RC.DRC` 的 `DGNCODE` 枚举 1/64 是缺口」"
    "—— **错**。单值枚举 `[\"KDS 41 20 : 2022\"]` **是该路由的正确取值**（KDS-41-20 专用模块路由）；"
    "64 条属于**另一条路由** `/db/DCON`。真正的（较小）缺口：**`DB.DCON` / `DB.DSTL` 没有 enum**，"
    "而手册有值表（`DB.DCON` 64 条）—— ⚠️ **本批不修**：该表带产品分叉（文末两张图分别标 "
    "`MIDAS CIVIL NX only` / `MIDAS GEN NX only`）且中文版抓取后**列错位** ⇒ 须以英文版为准 + 按产品分叉 "
    "+ 与 `/info` 交叉核对，属单独一次证据作业。"
)

for old, new, tag in ((OLD_4, NEW_4, "④"), (OLD_7, NEW_7, "⑦")):
    if old in text:
        text = text.replace(old, new)
        print(f"  ✓ 替换 {tag}")
    else:
        print(f"  ✗ 未匹配 {tag}（{len(old)} 字）")

P.write_text(text, encoding="utf-8", newline="")
print("done")
