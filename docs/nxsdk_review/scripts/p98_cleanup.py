"""P164-c：把两个**未清掉**的设计配置端点清干净（有界尝试，每步再读确认）。"""
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
TARGETS = {
    "DESIGN/RC/DRC": "DCON",
    "DESIGN/SRC/AIK-SRC2K/DSRC": "DSRC",
}

with httpx.Client(base_url=BASE, headers={"MAPI-Key": KEY}, timeout=25.0) as client:
    for path, root in TARGETS.items():
        print("=" * 80)
        print(f"{path}   (read_root={root})")
        cur = client.get("/" + path).json().get(root)
        print(f"  现状: {cur}")
        if not cur:
            print("  已空，跳过")
            continue
        for label, method, url, body in (
            ("DELETE per-id  /{path}/1", "DELETE", "/" + path + "/1", None),
            ("DELETE 带体   {\"Assign\": {\"1\": {}}}", "DELETE", "/" + path, {"Assign": {"1": {}}}),
            ("PUT 空体      {\"Assign\": {}}", "PUT", "/" + path, {"Assign": {}}),
        ):
            try:
                if method == "DELETE":
                    r = client.request("DELETE", url, json=body) if body is not None else client.delete(url)
                else:
                    r = client.put(url, json=body)
            except Exception as exc:  # noqa: BLE001
                print(f"  {label:44s} -> 传输失败 {type(exc).__name__}")
                continue
            now = client.get("/" + path).json().get(root)
            print(f"  {label:44s} -> {r.status_code}  再读={now}")
            if not now:
                print("  ✅ 已清空")
                break
