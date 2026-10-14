"""P164-c 只读侦察：设计配置端点的**未配置基线** + 项目哨兵（**零副作用，只发 GET**）。"""
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
CONFIG_PATHS = (
    "DESIGN/STEEL/DSTL",
    "DESIGN/STEEL/KDS-41-30-2022/DCO",
    "DESIGN/STEEL/KDS-41-30-2022/DCTL",
    "DESIGN/STEEL/KDS-41-30-2022/MEMB",
    "DESIGN/RC/DRC",
    "DESIGN/RC/KDS-41-20-2022/DCO",
    "DESIGN/RC/KDS-41-20-2022/DCTL",
    "DESIGN/RC/KDS-41-20-2022/MEMB",
    "DESIGN/SRC/AIK-SRC2K/DSRC",
    "DESIGN/SRC/AIK-SRC2K/DCO",
    "DESIGN/SRC/AIK-SRC2K/DCTL",
    "DESIGN/SRC/AIK-SRC2K/MEMB",
)
SENTINEL_PATHS = (
    "DB/NODE", "DB/ELEM", "DB/MATL", "DB/SECT", "DB/STLD",
    "DB/CNLD", "DB/CONS", "DB/GRUP", "DB/LCOM-STEEL", "DB/LCOM-CONC",
)

with httpx.Client(base_url=BASE, headers={"MAPI-Key": KEY}, timeout=20.0) as client:
    print(f"实例 {BASE}")
    health = client.get("/DB/NODE")
    print(f"健康检查 GET /DB/NODE -> {health.status_code} {health.text[:60]}")
    print()
    print("=== 设计配置端点的**当前**状态（未配置基线）===")
    for path in CONFIG_PATHS:
        r = client.get("/" + path)
        body = r.text[:150].replace("\n", " ")
        print(f"  GET /{path:36s} -> {r.status_code}  {body}")
    print()
    print("=== 项目哨兵（必须全空）===")
    empty = True
    for path in SENTINEL_PATHS:
        r = client.get("/" + path)
        try:
            payload = r.json()
            keys = list(payload) if isinstance(payload, dict) else []
            block = payload.get(keys[0]) if keys else None
            n = len(block) if isinstance(block, (dict, list)) else ("-" if block is None else 1)
        except Exception:  # noqa: BLE001
            keys, n = ["<非 JSON>"], "?"
        flag = "" if (r.status_code != 200 or n in (0, "-")) else "  ⚠️ 非空"
        if flag:
            empty = False
        print(f"  GET /{path:16s} -> {r.status_code}  顶层={keys} 条目={n}{flag}")
    print()
    print("哨兵全空:", empty)
