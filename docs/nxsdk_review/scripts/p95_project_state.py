"""P164-c 只读侦察（续）：项目级状态 —— UI 是否开着 / 项目是否已保存（**只发 GET**）。"""
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
PATHS = (
    "OPE/PROJECTSTATUS",
    "OPE/STORYPROP",
    "DB/UNIT",
    "DB/GRUP",
    "DB/STYP",
    "DOC/INFO",
    "DB/NODE",
)

with httpx.Client(base_url=BASE, headers={"MAPI-Key": KEY}, timeout=20.0) as client:
    for path in PATHS:
        try:
            r = client.get("/" + path)
            body = r.text[:400].replace("\n", " ")
            print(f"GET /{path:22s} -> {r.status_code}  {body}")
        except Exception as e:  # noqa: BLE001
            print(f"GET /{path:22s} -> 传输失败 {type(e).__name__}: {str(e)[:80]}")
        print()
