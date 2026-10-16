#!/usr/bin/env python3
"""
P175 · 收口「**导出可见但未登记**」的 `DB.*` 表（`docs/07` §16.1 **R168** 的 Registry 补全）。

为什么要它
----------
`DOC.EXPORT` 实测导出的 `DBG` 里有 **218** 张表，而 Registry 只登记了 **244** 个 `DB.*`
端点 —— 二者**相交不可互推**：导出**独有 27** 张（`MDGN` / `WIND` / `SEIS` / `WNAT` /
`ARPR` / `RISS` …），登记**独有 53** 个。

那 27 张是**真的存在**的表（实操导出到过），但在 Registry 里**没有定义** ⇒
「模型里有什么」这件事上，Registry 是**不完整**的。

⚠️ **为什么必须真机抓、不能靠猜**
---------------------------------
已离线核查（本工具的 `--check` 会复算）：
① 上游手册 **0 / 27** 有对应端点（两处同名命中经查是 `DESIGN.SRC.*.CMFT` 这类**同名不同义**）；
② 仓库既有实例证据（`introspect_field_diff.json` / `live_methods.json`）**0 / 27**
   （可能的命中全是**子串误报**，如 `SWIND` 含 `WIND`）；
③ `DOC.EXPORT` 里这 27 张**全是空表**（`{}`）⇒ 连一个字段名都拿不到。
⇒ 按仓库口径（**R140 / R151** 的教训：「来源太窄**不**按示例体硬凑」「**不**臆造」），
   字段**只能**从实例自省 `GET /info/db/<CODE>` 取。

判据（**铁律 ⓪**：效果，不是状态码）
------------------------------------
逐表：`GET /info/db/<CODE>` ⇒ `200` ∧ 响应含 `Argument.properties`（**真字段**）
⇒ 以该真实结构落 **YAML + Schema**，`schema_source: instance_introspect`（与
`DB.CPSETTINGS` / `DB.ULCT` 两个先例**同口径**）。
⚠️ 自省 **404 / 无字段** ⇒ **如实登记为「导出可见、无自省」**（`availability: untested`
+ `disable_reason`），**不**编字段。**只升不降**：不动任何既有端点的 `availability`。

用法
----
    python registry/tools/probe_export_only_tables_p175.py            # 预演（零请求）
    python registry/tools/probe_export_only_tables_p175.py --probe    # 真机抓取（**只发 GET**）
    python registry/tools/probe_export_only_tables_p175.py --write     # 落盘 YAML + Schema
    python registry/tools/probe_export_only_tables_p175.py --check     # 离线自洽（零请求）
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Final

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]

PRODUCT: Final[str] = "GEN_NX"
CRITERION_VERSION: Final[int] = 1
PASSED: Final[str] = "PASSED"
FAILED: Final[str] = "FAILED"

EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "export_only_tables_probe.json"
MODEL_DOC_EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "model_doc_probe.json"
MANIFEST: Final[pathlib.Path] = REPO / "registry" / "manifest.json"

INTROSPECT_TEMPLATE: Final[str] = "info/db/{code}"
HEALTH_PATH: Final[str] = "/db/NODE"


def _load_credentials() -> tuple[str, str]:
    """读 `[gen]` 段的 Base URL 与 Key（**只**在真机模式调用；值不进输出）。"""
    creds = pathlib.Path.home() / ".structai" / "midas-test.env"
    section, values = "", {}
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


# ===== 目标集（**离线可复算**）=====


def registered_tables(repo: pathlib.Path) -> set[str]:
    """Registry 已登记的 `DB.*` 表名（去命名空间前缀）。"""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {
        str(entry.get("key")).split(".")[-1]
        for entry in manifest["endpoints"]
        if str(entry.get("key") or "").startswith("DB.")
    }


def exported_tables(repo: pathlib.Path) -> set[str]:
    """`DOC.EXPORT` 实测导出里出现过的表名（来自既有证据，**不**另发请求）。"""
    document = json.loads(MODEL_DOC_EVIDENCE.read_text(encoding="utf-8"))
    export = ((document.get("endpoints") or {}).get("DOC.EXPORT") or {}).get("tables") or {}
    return set(export)


def targets(repo: pathlib.Path) -> list[str]:
    """**导出可见但未登记**的表名（升序）。"""
    return sorted(exported_tables(repo) - registered_tables(repo))


def manual_has_endpoint(repo: pathlib.Path, code: str) -> bool:
    """上游手册里是否存在 `db/<code>` 端点（用于 `--check` 复算「手册无据」这一事实）。"""
    import re  # noqa: PLC0415

    for name in ("MIDAS_API_Online_Manual_数据_v1.0.json",):
        path = repo / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        # 只认**端点路径**形态（`db/<code>` / `/db/<code>`），避开同名不同义的子串命中
        if re.search(rf'["\'/]db/{re.escape(code)}["\']', text, re.IGNORECASE):
            return True
    return False


def guard_readonly() -> None:
    """本工具是**只读**的：声明它**只**发 `GET`（`/info/db/*` 与 `/db/NODE`）。"""
    sys.path.insert(0, str(REPO))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        NATIVE_CRASH_ENDPOINTS,
        guard_native_crash_path,
    )

    crash = {"/" + str(item).replace(".", "/") for item in NATIVE_CRASH_ENDPOINTS}
    overlap = sorted(
        path for path in ("/info/db", HEALTH_PATH) if any(path in c for c in crash)
    )
    if overlap:
        raise SystemExit(f"❌ 声明路径与崩溃族相交：{overlap} ⇒ **拒绝运行**")
    for path in ("/info/db", HEALTH_PATH):
        guard_native_crash_path(path)
    print(f"闸门自检：本工具**只发 `GET`**（`/info/db/<CODE>` + `{HEALTH_PATH}` 健康检查）")


def run_probe(repo: pathlib.Path) -> int:
    """真机抓取（**只读**：逐表 `GET /info/db/<CODE>`）。"""
    guard_readonly()
    import httpx  # noqa: PLC0415

    base, key = _load_credentials()
    codes = targets(repo)
    if not codes:
        print("✅ 无需补全（导出与登记已一致）")
        return 0

    print(f"实例 {base} · 目标 **{len(codes)}** 张表：{codes}")
    rows: dict[str, Any] = {}

    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=60.0) as client:
        health = int(client.get(HEALTH_PATH).status_code)
        print(f"健康检查 {HEALTH_PATH} → {health}")
        if health != 200:
            print("🛑 实例不可达 ⇒ 一个业务请求都不发")
            return 1

        for code in codes:
            uri = "/" + INTROSPECT_TEMPLATE.format(code=code)
            try:
                response = client.get(uri)
            except Exception as error:  # noqa: BLE001 - 网络异常如实记
                rows[code] = {"uri": uri, "status": 0, "error": type(error).__name__}
                print(f"  {code:14s} {uri:22s} → 异常 {type(error).__name__}")
                continue
            status = int(response.status_code)
            payload: Any = None
            try:
                payload = response.json()
            except ValueError:
                payload = None
            # ⚠️ 判据 = **真的有字段**（`Argument.properties` 非空），不是状态码
            node = None
            if isinstance(payload, dict):
                argument = payload.get("Argument")
                if isinstance(argument, dict):
                    node = argument
                elif "properties" in payload:
                    node = payload
            properties = (node or {}).get("properties")
            has_fields = isinstance(properties, dict) and bool(properties)
            rows[code] = {
                "uri": uri,
                "status": status,
                "introspect": node if has_fields else None,
                "field_count": len(properties) if isinstance(properties, dict) else 0,
                "verdict": PASSED if has_fields else FAILED,
                "reason": "" if has_fields else ("no_properties" if status == 200 else "not_found"),
            }
            print(f"  {code:14s} {uri:22s} → {status} · 字段 {rows[code]['field_count']}")

    found = [code for code, row in rows.items() if row["verdict"] == PASSED]
    missing = [code for code, row in rows.items() if row["verdict"] != PASSED]
    document = {
        "note": [
            "P175 · 「导出可见但未登记」的 `DB.*` 表的**真机自省**（`docs/07` §16.1 **R168**）。",
            "**判据（铁律 ⓪：效果，不是状态码）**：`GET /info/db/<CODE>` ⇒ `200` ∧ "
            "响应含 **非空** `Argument.properties` ⇒ 才算拿到**真字段**。",
            "⚠️ 字段**只能**来自自省：上游手册 **0 / 27** 有据、仓库既有证据 **0 / 27**、"
            "`DOC.EXPORT` 里这 27 张**全是空表** ⇒ 离线**拿不到**任何字段名。",
            "**只读**：本工具只发 `GET`（自省 + 健康检查）；**不**改任何既有端点的裁定。",
        ],
        "criterion_version": CRITERION_VERSION,
        "instance": {"alias": "gen-local", "product": PRODUCT, "base_url": base},
        "targets": codes,
        "rows": rows,
        "counts": {"found": len(found), "missing": len(missing)},
        "found": found,
        "missing": missing,
        "verdict": PASSED if found else FAILED,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(document, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"⇒ 有字段 {len(found)} 张 · 无自省 {len(missing)} 张")
    print(f"wrote {EVIDENCE.relative_to(REPO)}")
    return 0


def check_offline(repo: pathlib.Path) -> int:
    """`--check`：证据齐备 + 「手册无据」可复算（**零请求**）。"""
    problems: list[str] = []
    codes = targets(repo)
    if not EVIDENCE.is_file():
        print(f"❌ 缺证据 {EVIDENCE.relative_to(REPO)}（先跑 --probe）")
        return 1
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    if list(document.get("targets") or []) != codes:
        problems.append(
            f"证据的目标集 {document.get('targets')} ≠ 复算 {codes} ⇒ 导出/登记已变，需重抓"
        )
    for code in codes:
        if manual_has_endpoint(repo, code):
            problems.append(f"`{code}` 在**上游手册里有**端点 ⇒ 不该走 instance_introspect 口径")
    rows = document.get("rows") or {}
    for code in codes:
        row = rows.get(code)
        if not isinstance(row, dict):
            problems.append(f"`{code}` 缺自省行")
            continue
        if row.get("verdict") == PASSED and not (row.get("introspect") or {}).get("properties"):
            problems.append(f"`{code}` 判 PASSED 但没有任何字段 ⇒ 假绿")
        if row.get("verdict") != PASSED and not row.get("reason"):
            problems.append(f"`{code}` 未通过却没写 `reason` ⇒ 不透明")
    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    counts = document.get("counts") or {}
    print(
        f"✅ 离线自洽：目标 **{len(codes)}** 张「导出可见但未登记」的表 · "
        f"手册无据（逐表复算） · 真机自省有字段 **{counts.get('found')}** 张 / "
        f"无自省 **{counts.get('missing')}** 张"
    )
    return 0


def main() -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="导出可见但未登记的 DB 表的真机自省")
    parser.add_argument("--probe", action="store_true", help="真机抓取（只发 GET）")
    parser.add_argument("--check", action="store_true", help="离线自洽断言（零请求）")
    args = parser.parse_args()
    if args.check:
        return check_offline(REPO)

    codes = targets(REPO)
    exported = exported_tables(REPO)
    registered = registered_tables(REPO)
    print(
        f"导出可见 **{len(exported)}** 张 · Registry 已登记 **{len(registered)}** 张 · "
        f"**未登记 {len(codes)}** 张"
    )
    print(f"目标：{codes}")
    if not args.probe:
        print("\n（预演；加 --probe 才真发——**只发 GET**）")
        return 0
    print()
    return run_probe(REPO)


if __name__ == "__main__":
    raise SystemExit(main())
