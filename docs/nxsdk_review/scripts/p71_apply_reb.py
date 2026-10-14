"""Apply the corrected ITEMS item shape to /db/REBB, /db/REBC, /db/REBW.

Shape source: the SDK's reviewed contracts (== GET /info path-for-path in all three).
Live refusal evidence: docs/live_verification_notes.md A-01 (REBW, PUT round trip),
A-02 (REBC, POST refused / array accepted), A-03 (REBB, every documented shape refused).
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
REG = REPO / "registry" / "schema" / "common" / "db"
WRITE = "--write" in sys.argv

NOTES = {
    "DB.REBB": "⚠️ 手册与官方文章的字段名**全部不对**（`{LAYER1, LAYER2}` 对象 vs 原生的 `{NAME, NUM}` **数组**），且**没有** `CREATE_SUB_SECTION`/`ELEMS`。实测（2026-08-27 / 09-03 / 09-27 / 10-04）多种载荷**全部** `Wrong Field`，**从未观察到任何一次写入成功**；短键能过字段校验并到达域检查。⚠️ `ID` 必填（缺它得到 `Wrong Field`）。R144 / MD-34 / 实测发现 A-03。",
    "DB.REBC": "⚠️ 手册与官方文章给**单个 `MAIN_BAR` 对象** + 顶层 `DO`；原生收 **`vMAIN_BAR` 数组**（每项含 `D0`，数字零）。实测（2026-08-27）：照手册发 → `Wrong Field`（形状被拒）；数组形状 → 域错误（形状被接受、目标缺失），且 POST→GET→PUT→DELETE→GET 往返成功 ⇒ 同时推翻手册的「POST only」。R144 / MD-34 / 实测发现 A-02。",
    "DB.REBW": "⚠️ 手册里**一个字段名都不对**（长名 `VERTICAL_REBAR`/`HORIZONTAL_REBAR`/`STORY:{FROM,TO}`/`THICKNESS`… vs 原生短名 `VER_BAR`/`HOR_BAR`/`vSTORY_NAME`（字符串数组，**不是** `{FROM,TO}` 范围）/`THICK`…）。实测（2026-07-29，真实生产模型 4044 节点/4686 单元）：`GET` 回显 + `/info` + **`PUT` 往返（改→验证→改回）** 三次独立确认 ⇒ 是**写契约**，不只是读。R144 / MD-34 / 实测发现 A-01。",
}

for key in ("DB.REBB", "DB.REBC", "DB.REBW"):
    gen = json.loads((REPO / ".tmp_analysis" / f"generated_{key.replace('.', '_')}.json")
                     .read_text(encoding="utf-8"))
    item_schema = gen["items_schema"]
    p = REG / f"{key.split('.')[-1]}.json"
    raw = p.read_bytes()
    eol = "\r\n" if b"\r\n" in raw else "\n"
    doc = json.loads(raw.decode("utf-8"))

    items = (doc["schema"]["properties"]["Assign"]["patternProperties"]["^[0-9]+$"]
             ["properties"]["ITEMS"])
    old = set((items.get("items", {}).get("properties") or {}))
    items["items"] = item_schema
    items["description"] = NOTES[key]
    new = set(item_schema["properties"])

    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    if eol == "\r\n":
        text = text.replace("\n", "\r\n")
    if WRITE:
        p.write_bytes(text.encode("utf-8"))
    print(f"{'WROTE' if WRITE else 'WOULD'} {p.name}: {len(old)} -> {len(new)} properties "
          f"({eol.strip() or 'LF'})")
    print(f"    removed: {sorted(old - new)}")
    print(f"    added  : {sorted(new - old)}")

print()
print("dry-run" if not WRITE else "applied")
