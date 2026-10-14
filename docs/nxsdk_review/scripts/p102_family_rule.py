"""验证是**族级规则**：`/DESIGN/{STEEL,RC,SRC}/…` 的 DELETE = 「写回产品默认」，而 `/db/*` 的 DELETE = 真删除。

对 STEEL 有**两条**路由：别名 `/DESIGN/STEEL/DSTL` 与规范 `/db/DSTL`（手册 Design 索引第 11 条）。
"""
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
import httpx  # noqa: E402

CREDS = Path(os.environ["USERPROFILE"]) / ".structai" / "midas-test.env"


def load() -> tuple[str, str]:
    section, values = "", {}
    for raw in CREDS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue
        if section == "gen" and "=" in line:
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip()
    return values["MIDAS_BASE_URL"].rstrip("/"), values["MIDAS_MAPI_KEY"]


BASE, KEY = load()
PAIRS = (
    ("STEEL", "/DESIGN/STEEL/DSTL", "/DB/DSTL", "DSTL"),
    ("RC", "/DESIGN/RC/DRC", "/DB/DCON", "DCON"),
    ("SRC", "/DESIGN/SRC/AIK-SRC2K/DSRC", None, "DSRC"),
)

with httpx.Client(base_url=BASE, headers={"MAPI-Key": KEY}, timeout=20.0) as c:
    for family, alias, canon, root in PAIRS:
        def read(path: str | None) -> object:
            if path is None:
                return "（无规范路由）"
            try:
                return c.get(path).json().get(root)
            except Exception as exc:  # noqa: BLE001
                return f"<{type(exc).__name__}>"

        print("=" * 88)
        print(f"{family}:  别名 {alias}   规范 {canon or '（无）'}")
        print(f"  跑前           别名={json.dumps(read(alias), ensure_ascii=False)}  规范={json.dumps(read(canon), ensure_ascii=False)}")
        # 先确保有一个**非默认**的值可观察
        seed = {"STEEL": "KDS 41 30 : 2022", "RC": "KDS 41 20 : 2022", "SRC": "AIK-SRC2K"}[family]
        r = c.put(alias, json={"Assign": {"1": {"DGNCODE": seed}}})
        print(f"  PUT 别名({seed}) -> {r.status_code}   别名={json.dumps(read(alias), ensure_ascii=False)}  规范={json.dumps(read(canon), ensure_ascii=False)}")
        # 别名 DELETE
        r = c.delete(alias)
        alias_after = read(alias)
        canon_after_alias_delete = read(canon)
        print(f"  DELETE 别名 -> {r.status_code}")
        print(f"      别名={json.dumps(alias_after, ensure_ascii=False)}  规范={json.dumps(canon_after_alias_delete, ensure_ascii=False)}")
        # 规范 DELETE
        if canon:
            r = c.delete(canon)
            print(f"  DELETE 规范 -> {r.status_code}")
            print(f"      别名={json.dumps(read(alias), ensure_ascii=False)}  规范={json.dumps(read(canon), ensure_ascii=False)}")
        print()
