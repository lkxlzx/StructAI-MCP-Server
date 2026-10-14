"""P164-c：收尾状态快照 + DELETE 语义的逐端点刻画（**只发 GET，除已做过的 DELETE 外不再写**）。"""
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
    return values["MIDAS_BASE_URL"].rstrip("/"), values["MIDAS_MAPI_KEY"]


BASE, KEY = load("gen")
CONFIG = {
    "DESIGN/STEEL/DSTL": "DSTL",
    "DESIGN/STEEL/KDS-41-30-2022/DCO": "DCO",
    "DESIGN/STEEL/KDS-41-30-2022/DCTL": "DCTL",
    "DESIGN/STEEL/KDS-41-30-2022/MEMB": "MEMB",
    "DESIGN/RC/DRC": "DCON",
    "DESIGN/RC/KDS-41-20-2022/DCO": "DCORC",
    "DESIGN/RC/KDS-41-20-2022/DCTL": "DCTL",
    "DESIGN/RC/KDS-41-20-2022/MEMB": "MEMB",
    "DESIGN/SRC/AIK-SRC2K/DSRC": "DSRC",
    "DESIGN/SRC/AIK-SRC2K/DCO": "SRCDCO",
    "DESIGN/SRC/AIK-SRC2K/DCTL": "DCTL",
    "DESIGN/SRC/AIK-SRC2K/MEMB": "MEMB",
}
MODEL = ("DB/NODE", "DB/ELEM", "DB/MATL", "DB/SECT", "DB/STLD", "DB/CNLD", "DB/CONS",
         "DB/LCOM-STEEL", "DB/LCOM-CONC", "DB/GRUP")

with httpx.Client(base_url=BASE, headers={"MAPI-Key": KEY}, timeout=25.0) as client:
    print("=== 设计配置端点最终状态 ===")
    state = {}
    for path, root in CONFIG.items():
        block = client.get("/" + path).json().get(root)
        state[path] = block
        mark = ""
        if path == "DESIGN/RC/DRC":
            mark = "   ← 已用规范路由 /DB/DCON 的 DELETE 清空"
        if path == "DESIGN/SRC/AIK-SRC2K/DSRC":
            mark = "   ← 无 /db/* 规范路由 ⇒ 无法删除；其唯一合法值即默认值"
        if path.startswith("DESIGN/") and path.endswith("/DCTL"):
            mark = "   ← 三族相同的 app 默认值（非残留）"
        if path.startswith("DESIGN/STEEL") and block:
            mark = "   ← P157 遗留"
        print(f"  {path:36s} {json.dumps(block, ensure_ascii=False)[:110]}{mark}")
    print()
    print("=== 模型哨兵（本批**未**触碰节点/单元/材料/截面）===")
    for path in MODEL:
        payload = client.get("/" + path).json()
        top = list(payload)
        block = payload.get(top[0]) if top else None
        n = len(block) if isinstance(block, (dict, list)) else 0
        print(f"  {path:16s} 条目={n}")
    (Path(r"E:\MCP\MMCP\.tmp_analysis") / "p164c_final_state.json").write_text(
        json.dumps({"config": state}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
