"""现场复核：用**已配置**的凭据打一次真实只读请求，证明连接是真的。

⚠️ 绝不打印凭据取值；只打印 base_url 主机、状态码与服务端**原始响应体**。
"""
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
CREDS = Path(os.environ.get("USERPROFILE", "")) / ".structai" / "midas-test.env"
USER_URL = "https://moa-engineers.midasit.cn:443/civil"


def load(instance: str = "civil") -> tuple[str, str]:
    base = os.environ.get("MIDAS_BASE_URL", "").rstrip("/")
    key = os.environ.get("MIDAS_MAPI_KEY", "")
    if base and key:
        return base, key
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


base, key = load()
print("凭据来源        :", "环境变量" if os.environ.get("MIDAS_MAPI_KEY") else str(CREDS))
print("我用的 base_url :", base)
print("你给的 base_url :", USER_URL)
print("两者是否一致    :", base == USER_URL)
print("凭据长度        :", len(key), "字符（取值不打印）")
print()

import httpx  # noqa: E402

with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=30.0) as client:
    for path in ("/DB/NODE", "/DB/MATL", "/DB/STCT-M1", "/DB/SDHY", "/mapikey/verify"):
        try:
            r = client.get(path)
            body = r.text[:220].replace("\n", " ")
            print(f"GET {path:20s} -> {r.status_code}  {body}")
        except Exception as exc:  # noqa: BLE001
            print(f"GET {path:20s} -> 传输失败 {type(exc).__name__}: {exc}")
