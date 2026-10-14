"""C 批落地（MD-60 / MD-16）：SPFC 拼写错字段 + MVHL 分支必填性与缺字段。"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
REG = REPO / "registry" / "schema" / "common" / "db"
WRITE = "--write" in sys.argv


def load(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    eol = "\r\n" if b"\r\n" in raw else "\n"
    return json.loads(raw.decode("utf-8")), eol


def save(path: Path, doc: dict, eol: str) -> None:
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    if eol == "\r\n":
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))


# ===================== MD-60: /db/SPFC =====================
p = REG / "SPFC.json"
doc, eol = load(p)
opt = doc["schema"]["SPFC"]["properties"]["OPT"]["properties"]
removed = opt.pop("LARGEBRIDEGE", None)
print(f"MD-60 {p.name}: 移除 OPT.LARGEBRIDEGE -> {removed is not None}")
strp = doc["schema"]["SPFC"]["properties"]["STR"]
strp["description"] = (
    "SpectrumTypeData。⚠️ **MD-60**：手册的 EURO2004 表把 `SPECTYPE` / `GROUTYPE` / "
    "`NATIONALANNEX` 放在 **`OPT`**，并把 `VAL.ag` 一并放在那里；该 body 在**两个产品**上都被拒 "
    "（`Unknown Error`），去掉 `OPT`、换成 `VAL.AG`、或两者都改**同样被拒** —— "
    "**至今未找到任何可用的 EURO2004 请求**。服务端 `/info` 把这三个声明在 **`STR`**（字符串），"
    "本 Schema 从 `/info`。"
)
if WRITE:
    save(p, doc, eol)
print(f"   STR.description 已注明 MD-60；OPT 现有 {len(opt)} 个字段")

# ===================== MD-16: /db/MVHL =====================
p = REG / "MVHL.json"
doc, eol = load(p)
mv = doc["schema"]["MVHL"]
props = mv["properties"]

# 1) 补 /info 声明而我方缺的字段
li = props["LOAD_ITEMS"]["items"]["properties"]
added = "POINT_DIST2" not in li
if added:
    li["POINT_DIST2"] = {"description": "Point Distance 2", "type": "number"}
print(f"MD-16 {p.name}: 补 LOAD_ITEMS[].POINT_DIST2 -> {added}")

# 2) 分支判别子：加 enum + 说明
props["VEHICLE_LOAD_NUM"]["enum"] = [1, 2]
props["VEHICLE_LOAD_NUM"]["description"] = (
    "VehicularLoadNumber。**分支判别子**：`1` = 标准车辆（Standard），`2` = 用户定义（User Defined）。"
    "手册的公共 Specifications 表**没有**提到它，却把只属分支 1 的字段写成**无条件**必填（MD-16）。"
)

# 3) 条件必填：VEHICLE_TYPE_NAME 仅在分支 1 必填
mv.setdefault("allOf", []).append(
    {
        "description": (
            "MD-16 / 实测：`VEHICLE_TYPE_NAME` **只在 `VEHICLE_LOAD_NUM = 1` 时必填** —— "
            "缺它得到 `(Item:Length of Vehicular Load Type(0 ~ 40 characters))`；"
            "在分支 2 下送它会被**丢弃**。"
        ),
        "if": {"properties": {"VEHICLE_LOAD_NUM": {"const": 1}}, "required": ["VEHICLE_LOAD_NUM"]},
        "then": {"required": ["VEHICLE_TYPE_NAME"]},
    }
)

# 4) 两处「手册说 Required、实测不是」的字段：如实加注，**不**做成闸门
props["STANDARD_CODE"]["description"] = (
    "StandardCode。⚠️ **MD-16**：手册标 **Required**，实测**两个分支都不需要** —— "
    "省略后记录照样落库（未报错）。"
)
props["USER_LOAD_TYPE"]["description"] = (
    "UserLoadType。⚠️ **MD-16**：仅在 `VEHICLE_LOAD_NUM = 2` 有意义；"
    "在 `MVLD_CODE = 2` 下它**根本不是输入** —— `\"Train\"` / `\"Lane\"` / `\"Truck\"` / "
    "`\"TruckLane\"` 与省略**都**存成 `\"Truck/Lane\"`。"
)
if WRITE:
    save(p, doc, eol)
print("   分支说明 + if/then 条件必填 + 两处如实加注")

print()
print("applied" if WRITE else "dry-run")
