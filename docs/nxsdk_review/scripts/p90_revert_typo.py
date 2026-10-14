"""改正我自己的越界：`OPT.LARGEBRIDEGE` 是**手册的**拼写，按 R117「反向缺口一律不动」**必须保留**。

（`registry/tools/sync_introspect_fields.py` 的裁决 R117：手册声明而本 build 自省没有的字段
**不删**、**不改名** —— 删除会削弱既有判定。实测：该拼写确实出自官方手册，
`MIDAS_API_Online_Manual_数据_v1.0.json` / `_Gen_NX_v1.0.json` / `_开发文档` / `_完整API手册` 都有。）

改为**如实加注**：手册拼 `LARGEBRIDEGE`（描述也拼成 `LargeBridege`），
服务端 `/info` 拼 `LARGEBRIDGE` —— 同一字段的两种拼写。
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
P = Path(r"E:\MCP\MMCP\registry\schema\common\db\SPFC.json")
WRITE = "--write" in sys.argv

raw = P.read_bytes()
eol = "\r\n" if b"\r\n" in raw else "\n"
doc = json.loads(raw.decode("utf-8"))
opt = doc["schema"]["SPFC"]["properties"]["OPT"]["properties"]

already = "LARGEBRIDEGE" in opt
if not already:
    opt["LARGEBRIDEGE"] = {
        "description": (
            "LargeBridege。⚠️ **手册的拼写**（`MIDAS_API_Online_Manual_*` 四处均如此，描述也拼成 "
            "`LargeBridege`）；服务端 `GET /info/db/SPFC` 拼 **`LARGEBRIDGE`**。"
            "按 R117「反向缺口一律不动」**保留**（手册声明而自省没有的字段不删、不改名 —— "
            "删除会削弱既有判定）。实际发送时以 `LARGEBRIDGE` 为准。MD-60 附带发现。"
        ),
        "type": "boolean",
    }

# 让两个拼写互相指认
opt["LARGEBRIDGE"]["description"] = (
    " Large Bridge。⚠️ 手册把同一字段拼成 **`LARGEBRIDEGE`**（见该键）；"
    "服务端 `/info` 的拼写是本键。MD-60 附带发现。"
)

print(f"LARGEBRIDEGE 已在: {already} -> 现为 {('LARGEBRIDEGE' in opt)}")
print(f"OPT 字段数: {len(opt)}")
if WRITE:
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    if eol == "\r\n":
        text = text.replace("\n", "\r\n")
    P.write_bytes(text.encode("utf-8"))
    print("WROTE")
else:
    print("dry-run")
