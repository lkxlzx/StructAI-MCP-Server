"""P164-c 修正实验：`/DESIGN/RC/DRC` vs `/db/DCON` 的 **DELETE 语义对比**（同一份数据，两条路由）。"""
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
import httpx  # noqa: E402

CREDS = Path(os.environ["USERPROFILE"]) / ".structai" / "midas-test.env"


def load(instance: str) -> tuple[str, str]:
    section, values = "", {}
    for raw in CREDS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue
        if section == instance and "=" in line:
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip()
    return values["MIDAS_BASE_URL"].rstrip("/"), values["MAPI-Key"] if False else values["MIDAS_MAPI_KEY"]


BASE, KEY = load("gen")
ALIAS = "/DESIGN/RC/DRC"
CANON = "/DB/DCON"

with httpx.Client(base_url=BASE, headers={"MAPI-Key": KEY}, timeout=20.0) as c:
    def show(label: str) -> None:
        a = c.get(ALIAS).json().get("DCON")
        b = c.get(CANON).json().get("DCON")
        print(f"  {label:38s} /DESIGN/RC/DRC={json.dumps(a, ensure_ascii=False):46s} /db/DCON={json.dumps(b, ensure_ascii=False)}")

    print("① 起始状态")
    show("跑前")
    print()
    print("② PUT 别名路由（写入 KDS 41 20 : 2022）")
    r = c.put(ALIAS, json={"Assign": {"1": {"DGNCODE": "KDS 41 20 : 2022"}}})
    print(f"  PUT -> {r.status_code}")
    show("PUT 之后")
    print()
    print("③ DELETE **别名**路由")
    r = c.delete(ALIAS)
    print(f"  DELETE {ALIAS} -> {r.status_code}  响应体={r.text[:80]}")
    show("DELETE 别名之后")
    print()
    print("④ DELETE **规范**路由（/DB/DCON）")
    r = c.delete(CANON)
    print(f"  DELETE {CANON} -> {r.status_code}  响应体={r.text[:80]}")
    show("DELETE 规范路由之后")
    print()
    print("⑤ 复位检查：两条路由是否都回到 {}")
    show("最终")
