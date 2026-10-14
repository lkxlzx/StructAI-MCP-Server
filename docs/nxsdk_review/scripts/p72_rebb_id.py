"""Record the live observation about REBB's ID in its description (it is not in `required`)."""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
REG = REPO / "registry" / "schema" / "common" / "db"

NOTE = (
    "ID。⚠️ 实测：**省略 `ID` 会得到 `Wrong Field`**（2026-09-27，Gen NX v2.2 build 09/24/2026）—— "
    "`Wrong Field` 在本端点**不**意味着字段名错，而意味着**缺 `ID`** 或用了官方文章的**长名**。"
    "`/info` 不声明 `required` 数组，故本 Schema **不**把它列入 `required`（requiredness 记为 `unstated`），"
    "但调用方必须送它。R144 / MD-34 / 实测发现 A-03。"
)

p = REG / "REBB.json"
raw = p.read_bytes()
eol = "\r\n" if b"\r\n" in raw else "\n"
doc = json.loads(raw.decode("utf-8"))
item = (doc["schema"]["properties"]["Assign"]["patternProperties"]["^[0-9]+$"]
        ["properties"]["ITEMS"]["items"])
item["properties"]["ID"]["description"] = NOTE
text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
if eol == "\r\n":
    text = text.replace("\n", "\r\n")
p.write_bytes(text.encode("utf-8"))
print("WROTE REBB.json: ID description updated")
print("ID now:", json.dumps(item["properties"]["ID"], ensure_ascii=False)[:200])
