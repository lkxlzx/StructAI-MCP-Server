"""量化 `DESIGN.RC.DRC` 的 `DGNCODE` 取值表缺口（手册「RC Design Code」文章 vs 我方 enum）。"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
raw = (REPO / "MIDAS_API_Online_Manual_数据_v1.0.json").read_text(encoding="utf-8")

# 定位 "RC Design Code" 那篇文章，取其后的编号值表
anchor = raw.rfind('"title": "RC Design Code')
assert anchor > 0, "找不到 RC Design Code 文章"
window = raw[anchor : anchor + 40000]
# 值表形态：["<n>", "<VALUE>", "\"<VALUE>\""]（JSON 转义后）
rows = re.findall(r'\[\s*"(\d+)"\s*,\s*"([^"]+)"\s*,\s*"', window)
print(f'手册「RC Design Code」值表：抽到 {len(rows)} 条')
values = []
for num, val in rows:
    values.append(val)
    print(f'  {num:>3}  {val}')
print()

ours = json.loads((REPO / "registry" / "schema" / "design" / "rc" / "DRC.json").read_text(encoding="utf-8"))
wrapper = ours["schema"]["properties"]["Assign"]
inner = next(iter((wrapper.get("patternProperties") or {}).values()))
enum = inner["properties"]["DGNCODE"].get("enum") or []
print(f"我方 enum: {enum}（{len(enum)} 条）")
print(f"手册值表: {len(set(values))} 个不同取值")
missing = [v for v in dict.fromkeys(values) if v not in enum]
print(f"**我方缺** {len(missing)} 个：{missing[:12]}{' …' if len(missing) > 12 else ''}")
print(f"服务端 DELETE 后的默认值 `GB/T50010-10` 在手册值表里: {'GB/T50010-10' in values}")
print(f"  且在我方 enum 里: {'GB/T50010-10' in enum}")
