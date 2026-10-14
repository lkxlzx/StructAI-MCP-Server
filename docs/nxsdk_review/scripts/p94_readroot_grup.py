"""P164-c 只读侦察（续）：① 12 个设计配置端点的 `read_root` vs 实测顶层键；② `DB.GRUP` 的 26 条是什么。"""
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
import httpx  # noqa: E402

REPO = Path(r"E:\MCP\MMCP")
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
manifest = {
    e["key"]: e
    for e in json.loads((REPO / "registry" / "manifest.json").read_text(encoding="utf-8"))["endpoints"]
}
KEYS = (
    "DESIGN.STEEL.DSTL", "DESIGN.STEEL.KDS-41-30-2022.DCO",
    "DESIGN.STEEL.KDS-41-30-2022.DCTL", "DESIGN.STEEL.KDS-41-30-2022.MEMB",
    "DESIGN.RC.DRC", "DESIGN.RC.KDS-41-20-2022.DCO",
    "DESIGN.RC.KDS-41-20-2022.DCTL", "DESIGN.RC.KDS-41-20-2022.MEMB",
    "DESIGN.SRC.AIK-SRC2K.DSRC", "DESIGN.SRC.AIK-SRC2K.DCO",
    "DESIGN.SRC.AIK-SRC2K.DCTL", "DESIGN.SRC.AIK-SRC2K.MEMB",
)

with httpx.Client(base_url=BASE, headers={"MAPI-Key": KEY}, timeout=20.0) as client:
    print("=== read_root（数据侧） vs 实测顶层键 ===")
    bad = []
    for key in KEYS:
        entry = manifest[key]
        declared = str((entry.get("wrapper") or {}).get("read_root") or "")
        uri = "/" + str(entry["uri"]).lstrip("/")
        r = client.get(uri)
        try:
            top = list(r.json())
        except Exception:  # noqa: BLE001
            top = ["<非 JSON>"]
        ok = declared in top
        if not ok:
            bad.append((key, declared, top))
        print(f"  {key:34s} read_root={declared!r:10s} live顶层={top} {'✓' if ok else '✗ 不符'}")
    print()
    print(f"read_root 不符: {len(bad)}")
    for key, declared, top in bad:
        print(f"   ✗ {key}: 声明 {declared!r} 而实测 {top}")
    print()
    print("=== DB.GRUP 的 26 条是什么 ===")
    g = client.get("/DB/GRUP").json()["GRUP"]
    names = [(k, v.get("NAME") if isinstance(v, dict) else None) for k, v in g.items()]
    print(f"  条目 {len(g)}")
    for k, name in names[:30]:
        print(f"    {k:>4}  {name}")
