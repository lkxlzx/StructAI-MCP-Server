"""MD-29 落地：/DESIGN/RC/KDS-41-20-2022/REBB 的 ITEMS 条目按**该节自己的示例**重建。

依据：`contracts/endpoints/design-rc-kds-41-20-2022-rebb.yaml` 的 `manualDefects` ——
该节的 JSON Schema / Parameters 表给的是 `MAIN_BAR_TOP`/`MAIN_BAR_BOT`（`{LAYER1, LAYER2}` 对象）
+ `DT`/`DB` + `SKIN_BAR` 对象；而**该节自己的** Request Body / Response Body / Python 示例
一律用 `vMAIN_BAR_TOP`/`vMAIN_BAR_BOT` **数组** + `MAIN_BAR_DC_TOP`/`MAIN_BAR_DC_BOT` +
扁平 `SKIN_BAR_NAME`/`SKIN_BAR_NUM` + 三个 `bSAME_SIZE_*`，且该节有一处 callout
**明说以示例为准**（"실제 전송 시에는 아래 예제 형식을 그대로 따르는 것이 안전합니다"）。
"""
import json
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
SDK = REPO / ".tmp_nxsdk"
P = REPO / "registry" / "schema" / "design" / "rc" / "KDS-41-20-2022" / "REBB.json"
WRITE = "--write" in sys.argv

KEEP = ("enum", "minimum", "maximum", "minItems", "maxItems")


def to_schema(field: dict) -> dict:
    out: dict = {}
    ftype = field.get("type")
    if ftype:
        out["type"] = ftype
    for k in KEEP:
        if field.get(k) is not None:
            out[k] = field[k]
    if field.get("description"):
        out["description"] = field["description"]

    props = field.get("properties")
    sub, sub_req = (None, None)
    if isinstance(props, list) and props:
        sub, sub_req = to_properties(props)

    items = field.get("items")
    if ftype == "array":
        if sub:
            item: dict = {"type": "object", "properties": sub}
            if sub_req:
                item["required"] = sub_req
        elif isinstance(items, dict) and items:
            item = to_schema(items)
        else:
            item = {"type": "object"}
        out["items"] = item
    else:
        if sub:
            out["properties"] = sub
            if sub_req:
                out["required"] = sub_req
    return out


def to_properties(fields: list) -> tuple[dict, list]:
    props, required = {}, []
    for f in fields or []:
        if not isinstance(f, dict) or not f.get("key"):
            continue
        props[f["key"]] = to_schema(f)
        if f.get("requirement") == "required":
            required.append(f["key"])
    return props, required


c = yaml.safe_load((SDK / "contracts" / "endpoints" / "design-rc-kds-41-20-2022-rebb.yaml")
                   .read_text(encoding="utf-8"))
assign = c["fields"][0]
items = assign["properties"][0]
assert items["key"] == "ITEMS", items["key"]

new_item = to_schema(items)
new_item["description"] = (
    "콘크리트 보 철근 항목。⚠️ **MD-29**：本节的 **JSON Schema / Parameters 表**给的是 "
    "`MAIN_BAR_TOP`/`MAIN_BAR_BOT`（`{LAYER1, LAYER2}` 对象）+ `DT`/`DB` + `SKIN_BAR` 对象；"
    "而**本节自己的** Request Body / Response Body / Python 示例**一律**用 "
    "`vMAIN_BAR_TOP`/`vMAIN_BAR_BOT` **数组** + `MAIN_BAR_DC_TOP`/`MAIN_BAR_DC_BOT` + "
    "扁平 `SKIN_BAR_NAME`/`SKIN_BAR_NUM` + 三个 `bSAME_SIZE_*`，且该节有一处 callout **明说以示例为准**。"
    "本 Schema 从示例（与章节 24 的姊妹端点 `/db/REBB` 的 `GET /info` 形状一致，互为印证）。"
)

raw = P.read_bytes()
eol = "\r\n" if b"\r\n" in raw else "\n"
doc = json.loads(raw.decode("utf-8"))
target = (doc["schema"]["properties"]["Assign"]["patternProperties"]["^[0-9]+$"]
          ["properties"]["ITEMS"])
old_keys = set((target.get("items", {}).get("properties") or {}))
# `new_item` 是**数组** schema（成员在其 `items` 里）⇒ 整体替换 ITEMS 的内容，
# 但保留我方原有的 `minItems: 1`（手册要求至少一条）。
keep_min = target.get("minItems")
target.clear()
target.update(new_item)
if keep_min is not None:
    target["minItems"] = keep_min
new_keys = set(target["items"]["properties"])

print(f"MD-29 {P.name}: {len(old_keys)} -> {len(new_keys)} 顶层成员")
print(f"  移除: {sorted(old_keys - new_keys)}")
print(f"  新增: {sorted(new_keys - old_keys)}")
print(f"  新 required: {target['items'].get('required')}")
print("  BAR_SECTOR_I 成员:", sorted(target["items"]["properties"]["BAR_SECTOR_I"]["properties"]))
print("  BAR_SECTOR_I required:", target["items"]["properties"]["BAR_SECTOR_I"].get("required"))

if WRITE:
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    if eol == "\r\n":
        text = text.replace("\n", "\r\n")
    P.write_bytes(text.encode("utf-8"))
    print("  WROTE")
else:
    print("  dry-run")
