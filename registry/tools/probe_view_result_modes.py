"""P164-e：`VIEW.RESULTGRAPHIC` 的**真机重测**探针（默认**预演**；`--probe` 才发请求）。

为什么有这道工具
----------------
**R155** 已离线定案：该端点是**多变体端点**，`Argument.CURRENT_MODE` 是**变体选择子**
（手册 **36** 个取值，见 `registry/live/view_result_modes.json`）；P160d 实测被拒的
`"displacement"` **不在**表里 ⇒ 那一次 `400` = **取值非法**，**不是**缺分析结果。

本工具要回答的**唯一**问题：**用表内的取值**，`400 second query is wrong` 还在不在？

三道纪律
--------
1. **硬闸门（离线，发请求之前）**：`CURRENT_MODE` **必须**在取值表里；否则**直接拒绝**
   —— 这正是把 R150 那个 `"displacement"` 挡在门外的那道闸。
2. **默认零请求**：不带 `--probe` 只打印「会发什么」。
3. **不**升级 `availability`：视图类端点的**真实效果**需要**改前 / 改后截图对比**
   （`VIEW.CAPTURE`，R148 的先例）；本工具只产出**「合法取值是否被接受」**这一步的证据，
   收口与否**由人裁决**。

⚠️ 本工具**自带 `httpx.Client`**（不走 `MidasHttpClient`）⇒ **原生崩溃护栏管不到它**
（`.tmp_analysis/` 与 `registry/tools/probe_*.py` 的同类脚本都一样）。因此它**自己**做一次
同源自检：目标路径若落在崩溃族里 ⇒ **拒绝运行**（复用 `app/**` 的那份路径表，不另抄一份）。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Final

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
"""仓库根目录（`registry/tools/` 的上两级）。"""

MODES_EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "view_result_modes.json"
"""取值表（**R155** 的离线证据；生成器 = `extract_result_modes.py`）。"""

EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "view_result_modes_probe.json"
"""本探针的落点。"""

CREDS: Final[pathlib.Path] = pathlib.Path.home() / ".structai" / "midas-test.env"
"""实例凭据（`[gen]` 段；**值绝不**进任何输出）。"""

PATH: Final[str] = "/VIEW/RESULTGRAPHIC"
"""原生路径。"""

KNOWN_FAILURE: Final[str] = "second query is wrong"
"""P160d 实测的失败标记（**R150** 的原文）。"""

DEFAULT_MODES: Final[tuple[str, ...]] = ("DisplacementContour", "DeformedShape")
"""默认试的**表内**取值 —— 与「简支梁 + 静力位移结果」相称的两个变体。"""

DEFAULT_LOAD_CASE: Final[str] = "DL"
"""`LOAD_CASE_COMB.NAME` 的默认值（P164-c 的混凝土简支梁上确有 `DL` 工况）。

⚠️ 手册示例用的是 `{"TYPE": "ST", "NAME": "DL"}`；`NAME` 必须是**该项目里真实存在**的工况
⇒ 换成别的项目时要**显式**用 `--load-case` 给出。
"""


def load_mode_table() -> dict[str, Any]:
    """读取值表（**R155** 的证据）。"""
    return json.loads(MODES_EVIDENCE.read_text(encoding="utf-8"))


def guard_modes(modes: tuple[str, ...], table: dict[str, Any]) -> None:
    """**硬闸门**：每个 `CURRENT_MODE` 必须在手册取值表里（否则发请求**之前**拒绝）。

    Raises:
        SystemExit: 取值不在表内（**这正是 R150 的成因**）。
    """
    known = set(table["modes"])
    unknown = [mode for mode in modes if mode not in known]
    if unknown:
        print(f"🛑 拒绝：这些 CURRENT_MODE 不在手册取值表里（共 {len(known)} 个合法取值）")
        for mode in unknown:
            print(f"   ✗ {mode!r}")
        if "displacement" in unknown:
            print("   ⚠️ 这正是 R150 实测被拒的那个取值（400 second query is wrong）")
        print(f"   合法取值见 {MODES_EVIDENCE.relative_to(REPO)}")
        raise SystemExit(3)


def native_crash_key_of(path: str) -> str | None:
    """查路径是否属于崩溃族（**只**读 `app/**` 的那份表，**不**另抄一份）。

    ⚠️ 本工具自带 `httpx.Client` ⇒ `MidasHttpClient._raw()` 那道护栏**管不到**它
    ⇒ 这里**自己**查一次。崩溃族端点会让 MIDAS Gen NX 在 `wg_db.dll` 里访问违例终止。
    """
    sys.path.insert(0, str(REPO))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        native_crash_key_for_path,
    )

    return native_crash_key_for_path(path)


def guard_not_native_crash_path(path: str) -> None:
    """同源自检：目标路径**不得**落在原生崩溃族里。

    Raises:
        SystemExit: 路径属于崩溃族（会打崩 MIDAS）。
    """
    key = native_crash_key_of(path)
    if key is not None:
        print(f"🛑 拒绝：{path} 属于原生崩溃族（{key}）—— 会打崩 MIDAS Gen NX")
        raise SystemExit(4)


def request_body(mode: str, load_case: str) -> dict[str, Any]:
    """构造请求体（**只**用取值表内的 `CURRENT_MODE` + 真实存在的工况名）。"""
    return {
        "Argument": {
            "CURRENT_MODE": mode,
            "LOAD_CASE_COMB": {"TYPE": "ST", "NAME": load_case},
        }
    }


def load_credentials() -> tuple[str, str]:
    """读 `[gen]` 段的 Base URL 与 Key（**只**在 `--probe` 时调用；值不进输出）。"""
    section, values = "", {}
    for raw in CREDS.read_text(encoding="utf-8").splitlines():
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


def check_offline() -> int:
    """`--check`：**零请求**的离线自洽断言（取值表 / 硬闸门 / 请求体 / 不碰崩溃族）。"""
    table = load_mode_table()
    problems: list[str] = []
    if table["rejected"]["in_manual_table"]:
        problems.append("取值表把被拒取值算成合法了")
    for mode in DEFAULT_MODES:
        if mode not in table["modes"]:
            problems.append(f"默认取值 {mode!r} 不在表内")
    if "displacement" in table["modes"]:
        problems.append("被拒取值出现在表里 ⇒ R155 的结论要重写")
    body = request_body(DEFAULT_MODES[0], DEFAULT_LOAD_CASE)
    if set(body) != {"Argument"} or set(body["Argument"]) != {"CURRENT_MODE", "LOAD_CASE_COMB"}:
        problems.append(f"请求体形状不符：{body}")
    if native_crash_key_of(PATH) is not None:
        problems.append(f"{PATH} 落在崩溃族里 ⇒ 不该由本工具试")
    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    print(
        f"✅ 离线自洽：取值表 {table['mode_count']} 个取值 · 默认试 {len(DEFAULT_MODES)} 个 · "
        f"被拒取值 {table['rejected']['value']!r} 不在表内 · {PATH} 不在崩溃族"
    )
    return 0


def native_crash_key_of(path: str) -> str | None:
    """查路径是否属于崩溃族（**只**读 `app/**` 的那份表，不另抄一份）。"""
    sys.path.insert(0, str(REPO))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        native_crash_key_for_path,
    )

    return native_crash_key_for_path(path)


def run_probe(path: str, modes: tuple[str, ...], load_case: str) -> int:
    """真机重测（`--probe`）：只发 `POST {path}`，判据 = 是否仍报已知失败标记。"""
    import httpx  # noqa: PLC0415

    base, key = load_credentials()
    rows: list[dict[str, Any]] = []
    with httpx.Client(
        base_url=base, headers={"MAPI-Key": key}, timeout=60.0
    ) as client:
        health = client.get("/DB/NODE")
        print(f"跑前健康检查 GET /DB/NODE -> {health.status_code}")
        for mode in modes:
            response = client.post(path, json=request_body(mode, load_case))
            text = response.text
            payload: dict[str, Any] = {}
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                payload = parsed
            row = {
                "current_mode": mode,
                "load_case": load_case,
                "status": response.status_code,
                "known_failure_marker": KNOWN_FAILURE in text,
                "payload_top_keys": sorted(payload),
                "body_bytes": len(text.encode("utf-8")),
            }
            rows.append(row)
            verdict = "仍报已知失败" if row["known_failure_marker"] else "未报已知失败"
            print(f"  {mode:24s} -> {response.status_code}  {verdict}")
    document = {
        "tool": "registry/tools/probe_view_result_modes.py",
        "endpoint": "VIEW.RESULTGRAPHIC",
        "path": path,
        "known_failure_marker": KNOWN_FAILURE,
        "load_case": load_case,
        "mode_table": str(MODES_EVIDENCE.relative_to(REPO)),
        "rows": rows,
        "note": (
            "⚠️ 判据**只**到「合法取值是否被接受」这一步。视图类端点的**真实效果**需要"
            "改前 / 改后截图对比（VIEW.CAPTURE，R148 的先例）⇒ 收口与否**由人裁决**；"
            "本工具**不**改任何 availability。"
        ),
    }
    EVIDENCE.write_text(
        json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"wrote {EVIDENCE.relative_to(REPO)}")
    return 0


def main() -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="VIEW.RESULTGRAPHIC 真机重测探针")
    parser.add_argument("--modes", nargs="*", default=list(DEFAULT_MODES),
                        help="要试的 CURRENT_MODE（必须都在手册取值表里）")
    parser.add_argument("--load-case", default=DEFAULT_LOAD_CASE,
                        help="项目里**真实存在**的工况名（LOAD_CASE_COMB.NAME）")
    parser.add_argument("--path", default=PATH,
                        help="原生路径（默认 VIEW.RESULTGRAPHIC；**崩溃族路径会被拒**）")
    parser.add_argument("--probe", action="store_true", help="真发请求（默认只预演）")
    parser.add_argument("--check", action="store_true", help="离线自洽断言（零请求）")
    args = parser.parse_args()

    if args.check:
        return check_offline()

    modes = tuple(args.modes)
    table = load_mode_table()
    guard_modes(modes, table)
    guard_not_native_crash_path(args.path)

    print(f"目标 {args.path}   取值表 {table['mode_count']} 个合法 CURRENT_MODE")
    print(f"工况 {args.load_case!r}（必须是该项目里真实存在的工况）")
    for mode in modes:
        print(f"  -> {json.dumps(request_body(mode, args.load_case), ensure_ascii=False)}")
    if not args.probe:
        print("\n（预演；加 --probe 才真发 —— 会**动**用户的 MIDAS 画面）")
        return 0
    print()
    return run_probe(args.path, modes, args.load_case)


if __name__ == "__main__":
    raise SystemExit(main())
