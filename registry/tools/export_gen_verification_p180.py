#!/usr/bin/env python3
"""P180 · 把 `Gen Verification` 的官方样本**批量导出**为 `DBG` JSON（模板的原料）。

为什么需要它
------------
`Gen Verification` 的 156 个样本全是 `.mgbx` 二进制（magic `MGNX`），逆向代价极高；
官方已提供 `DOC.EXPORT`（模型 → JSON）⇒ **不**逆向，直接让 MIDAS 自己导出。
本工具只负责**取样**：`DOC.OPEN` 样本副本 → `DOC.EXPORT` → 落盘。
参数化模板由 `app/application/templates/model_template.py` 生成。

红线（与既有各批一致）
----------------------
- 样本原目录 **只读**：只复制到 `.tmp_p180/workspace/` 再打开；
- **一次都不发 `DOC.NEW`**（R144）；开跑前先 `SAVE_AS` 备份现场并确立项目路径；
- 收尾用 `GET /db/PJCF` 核对 `FILE_NAME` ≠ `无标题`；
- 凭据只从 `~/.structai/midas-test.env` 读，**不**入库、**不**打印值。

用法
----
    python registry/tools/export_gen_verification_p180.py            # 预演（零请求）
    python registry/tools/export_gen_verification_p180.py --probe    # 真机批量导出（有副作用）
    python registry/tools/export_gen_verification_p180.py --check    # 离线自洽（零请求）
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys
import time
import urllib.request
from typing import Any, Final

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]

SAMPLES_DIR: Final[pathlib.Path] = pathlib.Path(r"D:\Program\MIDAS\MIDAS GEN NX\Gen Verification")
WORKSPACE: Final[pathlib.Path] = REPO / ".tmp_p180"
EXPORTS: Final[pathlib.Path] = WORKSPACE / "exports"
EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "gen_verification_exports_p180.json"

BACKUP: Final[pathlib.Path] = WORKSPACE / "session-backup.mgbx"

TIMEOUT: Final[float] = 300.0


def _credentials() -> tuple[str, str]:
    """读 `[gen]` 段的 Base URL 与 Key（**只**在真机模式调用；值不进输出）。"""
    creds = pathlib.Path.home() / ".structai" / "midas-test.env"
    section: str = ""
    values: dict[str, str] = {}
    for raw in creds.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue
        if section == "gen" and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values["MIDAS_BASE_URL"].rstrip("/"), values["MIDAS_MAPI_KEY"]


def _post(
    base: str, key: str, path: str, body: Any, *, timeout: float = TIMEOUT
) -> tuple[int, str]:
    """发一次 POST（返回 `(status, text)`）。"""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base}{path}",
        data=data,
        headers={"MAPI-Key": key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - 本机实例
        return int(response.status), response.read().decode("utf-8")


def _get(base: str, key: str, path: str) -> tuple[int, Any]:
    """发一次 GET。"""
    request = urllib.request.Request(
        f"{base}{path}", headers={"MAPI-Key": key, "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 - 本机实例
        return int(response.status), json.loads(response.read().decode("utf-8"))


def _nonempty_tables(payload: Any) -> dict[str, int]:
    """`DBG` 里**非空**的表 → 行数（模板关心的只有这些）。"""
    block = payload.get("DBG") if isinstance(payload, dict) else None
    if not isinstance(block, dict):
        return {}
    return {str(name): len(rows) for name, rows in block.items() if isinstance(rows, dict) and rows}


def run_probe() -> int:
    """真机批量导出（可续跑：已存在且可解析的导出直接跳过）。"""
    if not SAMPLES_DIR.is_dir():
        print(f"🛑 样本目录不存在：{SAMPLES_DIR}")
        return 1
    EXPORTS.mkdir(parents=True, exist_ok=True)
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    base, key = _credentials()

    # ---- R144：先备份现场（也让项目有路径）----
    BACKUP.unlink(missing_ok=True)
    status, _ = _post(base, key, "/DOC/SAVEAS", {"Argument": str(BACKUP)})
    if status != 200 or not BACKUP.is_file():
        print("🛑 备份未落盘 ⇒ 拒绝继续（不在无退路的实例上做写操作）")
        return 1
    print(f"备份现场 → {BACKUP.name}（{BACKUP.stat().st_size} 字节）")

    samples = sorted(SAMPLES_DIR.glob("*.mgbx"))
    print(f"样本 {len(samples)} 个 · 输出目录 {EXPORTS}")
    rows: list[dict[str, Any]] = []
    exported = skipped = failed = 0

    for index, source in enumerate(samples, start=1):
        target = EXPORTS / f"{source.stem}.json"
        if target.is_file():
            try:
                payload = json.loads(target.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict) and "DBG" in payload:
                skipped += 1
                rows.append(
                    {
                        "sample": source.name,
                        "status": "skipped",
                        "tables": len(payload["DBG"]),
                        "nonempty": _nonempty_tables(payload),
                    }
                )
                continue

        copy = WORKSPACE / f"{source.stem}.mgbx"
        shutil.copy2(source, copy)
        started = time.perf_counter()
        try:
            open_status, _ = _post(base, key, "/DOC/OPEN", {"Argument": str(copy)})
            export_status, _ = _post(base, key, "/DOC/EXPORT", {"Argument": str(target)})
        except Exception as error:  # noqa: BLE001 - 单个样本失败不应中断整批
            failed += 1
            rows.append({"sample": source.name, "status": "failed", "error": str(error)})
            print(f"  [{index}/{len(samples)}] {source.name} ❌ {error}")
            continue
        elapsed = time.perf_counter() - started

        ok = (
            open_status == 200
            and export_status == 200
            and target.is_file()
            and target.stat().st_size > 0
        )
        if not ok:
            failed += 1
            rows.append(
                {
                    "sample": source.name,
                    "status": "failed",
                    "open_status": open_status,
                    "export_status": export_status,
                }
            )
            print(
                f"  [{index}/{len(samples)}] {source.name} ❌ "
                f"open={open_status} export={export_status}"
            )
            continue

        payload = json.loads(target.read_text(encoding="utf-8"))
        exported += 1
        rows.append(
            {
                "sample": source.name,
                "status": "exported",
                "tables": len(payload.get("DBG") or {}),
                "nonempty": _nonempty_tables(payload),
                "bytes": target.stat().st_size,
                "seconds": round(elapsed, 3),
            }
        )
        nonempty = len(_nonempty_tables(payload))
        print(
            f"  [{index}/{len(samples)}] {source.name} ✅ "
            f"{target.stat().st_size} 字节 · 非空表 {nonempty} · {elapsed:.2f}s"
        )

    # ---- 收尾（R144）：还原现场并核对有路径 ----
    _post(base, key, "/DOC/OPEN", {"Argument": str(BACKUP)})
    _, pjcf_body = _get(base, key, "/db/PJCF")
    pjcf = (pjcf_body.get("PJCF") or {}).get("1") or {}
    file_name = str(pjcf.get("FILE_NAME") or "")
    restored = file_name not in {"", "无标题"}
    print(f"收尾：FILE_NAME={file_name!r} · 有路径={restored}")
    if not restored:
        print("🛑 收尾时项目无路径（R144 事故条件）")
        return 1

    evidence = {
        "note": [
            "P180 · `Gen Verification` 官方样本批量导出为 `DBG` JSON（参数化模板的原料）。",
            "判据：每个样本都经 `DOC.OPEN` + `DOC.EXPORT` 真的落盘且可解析。",
            "⚠️ 样本原目录只读；只碰 `.tmp_p180/` 内的副本。",
        ],
        "samples_dir": str(SAMPLES_DIR),
        "counts": {
            "total": len(samples),
            "exported": exported,
            "skipped": skipped,
            "failed": failed,
        },
        "session": {"file_name": file_name, "has_project_path": restored},
        "samples": rows,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"⇒ 导出 {exported} · 跳过 {skipped} · 失败 {failed} · 证据 {EVIDENCE.relative_to(REPO)}")
    return 0 if failed == 0 else 1


def check_offline() -> int:
    """`--check`：证据存在且计数自洽（**零请求**）。"""
    if not EVIDENCE.is_file():
        print(f"❌ 缺证据 {EVIDENCE.relative_to(REPO)}（先跑 --probe）")
        return 1
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    counts = document.get("counts") or {}
    problems: list[str] = []
    if int(counts.get("exported") or 0) <= 0:
        problems.append("导出的样本数为 0 ⇒ 判据不成立")
    if int(counts.get("failed") or 0) != 0:
        problems.append(f"存在失败样本 {counts.get('failed')} 个")
    if document.get("session", {}).get("has_project_path") is not True:
        problems.append("收尾时项目无路径（R144）")
    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    print(
        f"✅ 批量导出：{counts.get('exported')} 个样本落盘 · "
        f"{counts.get('skipped')} 个跳过 · {counts.get('failed')} 个失败 · 收尾有路径"
    )
    return 0


def main() -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="Gen Verification 批量导出为 DBG JSON")
    parser.add_argument("--probe", action="store_true", help="真发请求（默认只预演）")
    parser.add_argument("--check", action="store_true", help="离线自洽断言（零请求）")
    args = parser.parse_args()
    if args.check:
        return check_offline()
    if not args.probe:
        count = len(list(SAMPLES_DIR.glob("*.mgbx"))) if SAMPLES_DIR.is_dir() else 0
        print(f"样本：{SAMPLES_DIR}（{count} 个 .mgbx）")
        print(f"输出：{EXPORTS}")
        print(f"证据：{EVIDENCE.relative_to(REPO)}")
        print("\n（预演；加 --probe 才真发）")
        return 0
    return run_probe()


if __name__ == "__main__":
    raise SystemExit(main())
