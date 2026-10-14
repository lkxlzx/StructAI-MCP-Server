"""P164-f：`VIEW.RESULTGRAPHIC` 的**效果判据**（铁律 ⓪）—— 改前/改后**截图字节对比**。

为什么不能拿 `200` 收口
----------------------
P164-e 已证明：**表内** `CURRENT_MODE` ⇒ `200`（不再报 `second query is wrong`）。
但 **R148 的先例**与**铁律 ⓪**都要求：**视图类**端点的判据必须是**画面真的变了**，
不是状态码。原生**静默 `200` 却什么都不做**在本项目已实测四次
（**R119** `ITEMS` 外层键 · **R128** `DB.CONS` 外层键 · **R145** `DOC.NEW` 带路径 ·
**R146** `DOC.SAVE` 带路径）⇒ 视图类**更**要验效果。

本工具做**受控测量**（缺一不可）：

| 步 | 动作 | 期望 |
| --- | --- | --- |
| ① | `RESULTGRAPHIC(A)` → `CAPTURE A` | — |
| ② | `RESULTGRAPHIC(B)` → `CAPTURE B` | **B ≠ A**（换取值 ⇒ 画面真的换） |
| ③ | `RESULTGRAPHIC(A)` → `CAPTURE C` | **C == A**（同取值可复现 ⇒ 排除「截图本来就不稳定」） |
| ④ | **阳性对照**：`DISPLAY(ELEM_NUMBER=true/false)` → `CAPTURE P1/P2` | **P2 ≠ P1**（**仪器有效** —— 截图确实能看见显示变化） |

**判据**：`② 有差异 ∧ ③ 无差异 ∧ ④ 仪器有效` ⇒ `PASSED`；否则 `FAILED`（**不**收口）。
⚠️ **④ 是必需项**：没有它，② 的「无差异」无法区分「原生空转」与「截图拍不到结果图形」。

⚠️ 只发 `VIEW.*`（**视图类**：不改模型、不落库）；jpg 落 `.tmp_p164c/view_effect/`（`.gitignore` 内），
证据里**只记字节数与 sha256**，**不**记图片内容。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys
from typing import Any, Final

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
"""仓库根目录（`registry/tools/` 的上两级）。"""

EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "view_result_effect_probe.json"
"""证据落点。"""

SHOTS: Final[pathlib.Path] = REPO / ".tmp_p164c" / "view_effect"
"""截图落点（**在 `.gitignore` 内**；证据里只留字节数与哈希）。"""

CREDS: Final[pathlib.Path] = pathlib.Path.home() / ".structai" / "midas-test.env"
"""实例凭据（`[gen]` 段；**值绝不**进任何输出）。"""

MODE_A: Final[str] = "DisplacementContour"
MODE_B: Final[str] = "DeformedShape"
"""两个**表内**取值（都来自 `registry/live/view_result_modes.json`）。"""

CONTROL_KEY: Final[str] = "ELEMENT.ELEM_NUMBER"
"""阳性对照用的显示开关（`VIEW.DISPLAY` 的手册字段）。"""


def _sibling(name: str) -> Any:
    """按路径装载同目录的探针模块（`registry/tools` 不是包）—— **不**复制它的闸门逻辑。"""
    path = pathlib.Path(__file__).with_name(name)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_credentials() -> tuple[str, str]:
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
    """`--check`：**零请求**的离线自洽断言（证据齐备 + 判据三条件都在）。"""
    if not EVIDENCE.exists():
        print(f"❌ 缺证据 {EVIDENCE.relative_to(REPO)}（先跑 --probe）")
        return 1
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    effect = document["effect"]
    problems: list[str] = []
    if not document["control"]["instrument_works"]:
        problems.append("阳性对照未通过 ⇒ 效果结论**不成立**（不该被当成证据）")
    if effect["graphic_changed_when_mode_changed"]:
        problems.append("画面会变 ⇒ 本批的 FAILED 结论要重写")
    if not effect["same_mode_reproducible"]:
        problems.append("同取值不可复现 ⇒ 截图本身不稳定，判据无效")
    if effect["verdict"] != "FAILED":
        problems.append(f"判定应为 FAILED，实际 {effect['verdict']!r}")
    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    print(
        f"✅ 离线自洽：阳性对照通过（仪器有效）· 换取值**未**改变画面 · "
        f"同取值可复现 ⇒ `VIEW.RESULTGRAPHIC` 的 `200` = **静默空转**（**不**收口）"
    )
    return 0


def run_probe(load_case: str) -> int:
    """真机受控测量（`--probe`）：③ 效果判据 + ④ 阳性对照。"""
    import httpx  # noqa: PLC0415

    modes = _sibling("probe_view_result_modes.py")
    table = modes.load_mode_table()
    modes.guard_modes((MODE_A, MODE_B), table)
    for path in ("/VIEW/RESULTGRAPHIC", "/VIEW/CAPTURE", "/VIEW/DISPLAY"):
        modes.guard_not_native_crash_path(path)

    SHOTS.mkdir(parents=True, exist_ok=True)
    base, key = _load_credentials()
    rows: list[dict[str, Any]] = []
    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=120.0) as client:
        print(f"实例 {base}   工况 {load_case!r}")
        print(f"跑前健康检查 GET /DB/NODE -> {client.get('/DB/NODE').status_code}")

        def set_mode(mode: str) -> int:
            return client.post(
                "/VIEW/RESULTGRAPHIC",
                json={
                    "Argument": {
                        "CURRENT_MODE": mode,
                        "LOAD_CASE_COMB": {"TYPE": "ST", "NAME": load_case},
                    }
                },
            ).status_code

        def capture(tag: str) -> dict[str, Any]:
            target = SHOTS / f"{tag}.jpg"
            if target.exists():
                target.unlink()
            status = client.post(
                "/VIEW/CAPTURE", json={"Argument": {"EXPORT_PATH": str(target)}}
            ).status_code
            exists = target.exists()
            return {
                "tag": tag,
                "capture_status": status,
                "exists": exists,
                "bytes": target.stat().st_size if exists else 0,
                "sha256": _sha(target) if exists else "",
            }

        for tag, mode in (("A", MODE_A), ("B", MODE_B), ("C", MODE_A)):
            status = set_mode(mode)
            shot = capture(tag)
            shot["current_mode"] = mode
            shot["resultgraphic_status"] = status
            rows.append(shot)
            print(
                f"  {tag}: RESULTGRAPHIC({mode}) -> {status} · CAPTURE -> "
                f"{shot['capture_status']} · {shot['bytes']} 字节 · {str(shot['sha256'])[:16]}"
            )

        control_rows: list[dict[str, Any]] = []
        for tag, enabled in (("P1", True), ("P2", False)):
            status = client.post(
                "/VIEW/DISPLAY", json={"Argument": {"ELEMENT": {"ELEM_NUMBER": enabled}}}
            ).status_code
            shot = capture(tag)
            shot["elem_number"] = enabled
            shot["display_status"] = status
            control_rows.append(shot)
            print(
                f"  {tag}: DISPLAY({CONTROL_KEY}={enabled}) -> {status} · CAPTURE -> "
                f"{shot['capture_status']} · {shot['bytes']} 字节 · {str(shot['sha256'])[:16]}"
            )

    a, b, c = rows
    p1, p2 = control_rows
    changed = bool(a["sha256"]) and a["sha256"] != b["sha256"]
    reproducible = a["sha256"] == c["sha256"]
    instrument_works = bool(p1["sha256"]) and p1["sha256"] != p2["sha256"]
    passed = changed and reproducible and instrument_works
    print()
    print(f"② 换取值 ⇒ 画面变化      : {changed}")
    print(f"③ 同取值可复现（对照）  : {reproducible}")
    print(f"④ 阳性对照（仪器有效）  : {instrument_works}")
    print(f"⇒ 效果判据（铁律 ⓪）    : {'✅ PASSED' if passed else '❌ FAILED（**不**收口）'}")

    document = {
        "tool": "registry/tools/probe_view_result_effect.py",
        "endpoint": "VIEW.RESULTGRAPHIC",
        "load_case": load_case,
        "mode_a": MODE_A,
        "mode_b": MODE_B,
        "mode_table": "registry/live/view_result_modes.json",
        "rows": rows,
        "control": {
            "what": f"VIEW.DISPLAY 的 {CONTROL_KEY} 开/关（R148 的先例）",
            "rows": control_rows,
            "instrument_works": instrument_works,
        },
        "effect": {
            "graphic_changed_when_mode_changed": changed,
            "same_mode_reproducible": reproducible,
            "verdict": "PASSED" if passed else "FAILED",
        },
        "note": (
            "铁律 ⓪：视图类端点的判据 = 改前/改后**截图字节**。"
            "阳性对照（④）用于区分「原生静默空转」与「截图拍不到结果图形」。"
            "⚠️ 本工具**不**改任何 availability —— 收口与否**由人裁决**。"
        ),
    }
    EVIDENCE.write_text(
        json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"wrote {EVIDENCE.relative_to(REPO)}")
    return 0 if passed else 1


def main() -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="VIEW.RESULTGRAPHIC 效果判据（截图字节对比）")
    parser.add_argument("--load-case", default="DL", help="项目里**真实存在**的工况名")
    parser.add_argument("--probe", action="store_true", help="真发请求（默认只预演）")
    parser.add_argument("--check", action="store_true", help="离线自洽断言（零请求）")
    args = parser.parse_args()
    if args.check:
        return check_offline()
    modes = _sibling("probe_view_result_modes.py")
    table = modes.load_mode_table()
    modes.guard_modes((MODE_A, MODE_B), table)
    print(f"效果判据：RESULTGRAPHIC({MODE_A}) vs ({MODE_B}) + 阳性对照 {CONTROL_KEY}")
    print(f"工况 {args.load_case!r}（必须是该项目里真实存在的工况）")
    if not args.probe:
        print("\n（预演；加 --probe 才真发 —— 会**动**用户的 MIDAS 画面）")
        return 0
    print()
    return run_probe(args.load_case)


if __name__ == "__main__":
    raise SystemExit(main())
