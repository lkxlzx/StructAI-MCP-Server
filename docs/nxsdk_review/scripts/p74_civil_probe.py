"""CIVIL_NX 产品级只读路由探针 —— 判定 B 级 21 条候选。

**只发 `GET`**（零副作用）。分块 + 块间只读健康检查 `GET /DB/NODE`；非 200 立即中止。
证据写到 `.tmp_analysis/`（**不**入库）。凭据只从进程环境 / 外部凭据文件读，绝不打印取值。

判据（沿用 L4 口径，并区分「路由存在」与「读回成功」）：
  * 非 `200`                              ⇒ `ABSENT`（路由**不在**该产品上 —— 唯一可用于产品归属的判据）
  * `200` 且响应顶层键 == 该端点的 `read_root`  ⇒ `PASSED`（路由在 + 读回成功）
  * `200` 但顶层键不符（如 `{"message": ""}` = 空表）⇒ `PRESENT_EMPTY`（路由在，本模型无数据）

⚠️ **`instances.yaml` 记载 civil-cloud 的语义**：未知 URI 返回 `404`（可靠）；
**空表返回 `200` + `{"message": ""}`**。故本探针**不**把空表读成失败 ——
「路由存在」的判据是 `200`，不是「读回非空」。
"""
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
OUT = REPO / "registry" / "live" / "civil_product_probe.json"
CREDS = Path(os.environ.get("USERPROFILE", "")) / ".structai" / "midas-test.env"

# B 级 21 条（我方只声明 GEN_NX，服务端 /info 或对方契约含 civil）
B_LEVEL = [
    "DB.DCTL", "DB.DSTL", "DB.EPSE", "DB.ESSF", "DB.LENG", "DB.LLAN", "DB.LLANID",
    "DB.LTSR", "DB.MBTP", "DB.MEMB", "DB.POSL", "DB.POSP", "DB.WMAK",
    "DOC.STAGAS", "OPE.EDMP", "OPE.GSBG", "OPE.GUSTFACTOR", "OPE.MEMB", "OPE.SSPS",
    "POST.STEELCODECHECK", "VIEW.PRECAPTURE",
]
# 对照组 A：两产品共有端点（必须 PASSED —— 证明探针本身有效）
CONTROL_OK = ["DB.NODE", "DB.MATL"]
# 对照组 B：Hyper-S `-M1`（第一/二批已改为 CIVIL_NX 专属）——
#   若在 CIVIL_NX 上存在，则**用我方自己的实测**印证了那 21 条的归属更正
CONTROL_HYPER_S = ["DB.STCT-M1", "DB.MATL-M1", "DB.STYP-M1"]
# 第四组：**全部 21 条** Hyper-S `-M1`（不靠 3 条外推 —— 逐条实测）
HYPER_S_ALL = [
    "DB.ACTL-M1", "DB.BCGA-M1", "DB.BCGD-M1", "DB.EIGV-M1", "DB.EPMT-M1",
    "DB.HHCT-M1", "DB.IEHG-BEAM-M1", "DB.IEHG-GL-M1", "DB.IEHG-PSS-M1", "DB.IEHG-TRUSS-M1",
    "DB.IMFM-M1", "DB.MATL-M1", "DB.NLCT-M1", "DB.NLNK-M1", "DB.POGD-M1",
    "DB.POLC-M1", "DB.STCT-M1", "DB.STYP-M1", "DB.THGC-M1", "DB.THIS-M1", "DB.THOO-M1",
]
# 对照组 C：§8.2 已按实测从 CIVIL_NX 摘除的端点（必须不存在 —— 阴性对照）
CONTROL_ABSENT = ["DB.SDHY", "DB.SDIS"]

HEALTH_PATH = "/DB/NODE"
CHUNK = 20


def load_creds(instance: str = "civil") -> tuple[str, str]:
    """从外部凭据文件读 `[instance]` 段（**不**打印取值）。"""
    base = os.environ.get("MIDAS_BASE_URL", "").rstrip("/")
    key = os.environ.get("MIDAS_MAPI_KEY", "")
    if base and key:
        return base, key
    if not CREDS.is_file():
        raise SystemExit(f"credentials file not found: {CREDS}")
    section = ""
    values: dict[str, str] = {}
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
    base = values.get("MIDAS_BASE_URL", "").rstrip("/")
    key = values.get("MIDAS_MAPI_KEY", "")
    if not base or not key:
        raise SystemExit(f"section [{instance}] missing MIDAS_BASE_URL / MIDAS_MAPI_KEY")
    return base, key


def main() -> int:
    import httpx

    base, key = load_creds()
    manifest = {
        str(item["key"]): item
        for item in json.loads((REPO / "registry" / "manifest.json").read_text(encoding="utf-8"))["endpoints"]
    }
    print(f"实例 base_url 主机: {base.split('//')[-1].split('/')[0]}  (取值不打印)")
    print(f"目标 {len(B_LEVEL)} 条 + 对照 {len(CONTROL_OK) + len(CONTROL_ABSENT)} 条\n")

    results: dict[str, dict] = {}
    aborted = ""
    targets = CONTROL_OK + CONTROL_HYPER_S + CONTROL_ABSENT + B_LEVEL + HYPER_S_ALL
    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=30.0) as client:
        for start in range(0, len(targets), CHUNK):
            chunk = targets[start : start + CHUNK]
            for key_ in chunk:
                item = manifest[key_]
                uri = "/" + str(item["uri"]).strip("/")
                read_root = str((item.get("wrapper") or {}).get("read_root") or "")
                try:
                    resp = client.get(uri)
                    code = resp.status_code
                    try:
                        body = resp.json()
                    except Exception:  # noqa: BLE001
                        body = None
                    top = list(body) if isinstance(body, dict) else []
                except Exception as exc:  # noqa: BLE001
                    code, top = -1, [f"transport: {type(exc).__name__}"]
                if code != 200:
                    verdict = "ABSENT"
                elif read_root and read_root in top:
                    verdict = "PASSED"
                else:
                    verdict = "PRESENT_EMPTY"
                results[key_] = {
                    "uri": uri, "read_root": read_root, "status_code": code,
                    "top_keys": top[:8], "verdict": verdict,
                }
                print(f"  {key_:24s} {uri:34s} -> {code}  {verdict:8s} top={top[:4]}")
            health = client.get(HEALTH_PATH).status_code
            print(f"  -- 块 {start // CHUNK + 1} 完成；健康检查 {HEALTH_PATH} -> {health}")
            if health != 200:
                aborted = f"健康检查 {HEALTH_PATH} -> {health}（立即中止）"
                print(f"  ⚠️ {aborted}")
                break

    counts: dict[str, int] = {}
    for row in results.values():
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1

    document = {
        "note": [
            "CIVIL_NX **产品级路由探针**（B 级 21 条候选 + 三组对照）。**只发 GET**，零副作用。",
            "判据：非 200 ⇒ ABSENT（路由不在该产品上 —— 唯一可用于产品归属的判据）；",
            "200 且顶层键 == read_root ⇒ PASSED；200 但空表（`{\"message\": \"\"}`）⇒ PRESENT_EMPTY。",
            "⚠️ civil-cloud 的语义（instances.yaml）：未知 URI 返回 404（可靠）；空表返回 200 + message。",
            "对照：DB.NODE/DB.MATL 必须存在；DB.SDHY/DB.SDIS（§8.2 已摘除 CIVIL_NX）必须不存在；",
            "DB.STCT-M1/DB.MATL-M1/DB.STYP-M1 用于复核第一/二批的 Hyper-S 归属更正。",
            "生成器 = .tmp_analysis/p74_civil_probe.py（归档于 docs/nxsdk_review/scripts/）。",
        ],
        "instance": {
            "alias": "civil-cloud",
            "product": "CIVIL_NX",
            "base_url": "https://moa-engineers.midasit.cn:443/civil",
            "probed_at": "2026-10-14",
            "scope": "B 级 21 条候选（我方仅声明 GEN_NX）+ 三组对照",
        },
        "counts": counts,
        "aborted": aborted,
        "controls": {
            "present_expected": CONTROL_OK,
            "absent_expected": CONTROL_ABSENT,
            "hyper_s_recheck": CONTROL_HYPER_S,
        },
        "hyper_s_family": HYPER_S_ALL,
        "endpoints": results,
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(REPO)}")

    # 探针自检：三组对照都必须符合预期，否则本次结果不可用。
    # ⚠️ 对照组 A 的判据是「**路由存在**」（`200`），**不是**「读回非空」——
    #    civil-cloud 上空表返回 `200 + {"message": ""}`（instances.yaml 记载）。
    ctl_ok = all(results[k]["status_code"] == 200 for k in CONTROL_OK)
    ctl_absent = all(results[k]["verdict"] == "ABSENT" for k in CONTROL_ABSENT)
    hyper = {k: results[k]["verdict"] for k in CONTROL_HYPER_S}
    print(f"\n探针自检：共有端点路由存在={ctl_ok}  阴性对照不存在={ctl_absent}")
    print(f"  Hyper-S 组（第一/二批的归属更正）在 CIVIL_NX 上：{hyper}")
    if not (ctl_ok and ctl_absent):
        print("⚠️ 对照组不符预期 ⇒ 本次结果**不可用**，先查实例/模型状态")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
