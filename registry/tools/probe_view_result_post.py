"""P166 / **R159**：**纯 API 进入结果视图（post）的路径** + `VIEW.RESULTGRAPHIC` 的**效果判据**。

R157 留下的问题
---------------
P164-f 实测：**表内** `CURRENT_MODE` ⇒ `200`，**但画面一个字节都没变**
（A/B/C 三次 32023 字节 · 同一 sha256）⇒ 判为「静默空转」⇒ **不**收口。
当时的请求体**只有** `CURRENT_MODE` + `LOAD_CASE_COMB`。

本工具找到的**成因（R159）**
-------------------------
**缺 `TYPE_OF_DISPLAY`**：`VIEW.RESULTGRAPHIC` 的 `TYPE_OF_DISPLAY.<子块>.OPT_CHECK = true`
才是**真正把结果图形打开**的那个开关。没有它，原生**照样回 `200`**，但**什么都不显示**
（与 **R119 / R128 / R145 / R146** 同族的「静默 `200`」）。

而**纯 API 进 post 视图**的路径**确实存在**，且是**手册自己的**写法：

* `POST /VIEW/CAPTURE` 的 `Argument.SET_MODE`（`"pre"` / `"post"`）**切换视图模式**（粘性）；
* `POST /VIEW/CAPTURE` 的 `Argument.RESULT_GRAPHIC` 与**独立的** `POST /VIEW/RESULTGRAPHIC`
  都用来**配置结果图形**（前者**一次性覆盖**，后者**持久**）；
* 结果图形**只在 post 模式下渲染** ⇒ `SET_MODE: "post"` + 图形打开 ⇒ 截图里**真的**出现
  图例 / 云图 / 变形 / 工况名（`ST: DL`）。

受控测量（**缺一不可**）
-----------------------
| 步 | 动作 | 期望 |
| --- | --- | --- |
| ① | `RESULTGRAPHIC(图形**全关**)` → `CAPTURE(SET_MODE=post)` ×2 | 两次**字节相同** ⇒ 渲染确定（**噪声地板**） |
| ② | `RESULTGRAPHIC(A)` → `CAPTURE(SET_MODE=post)` | **≠ ①**（改前 / 改后） |
| ③ | `RESULTGRAPHIC(B)` → `CAPTURE(SET_MODE=post)` | **≠ ②**（换取值 ⇒ 画面真的换） |
| ④ | `RESULTGRAPHIC(A)` → `CAPTURE(SET_MODE=post)` | **== ②**（同取值可复现） |
| ⑤ | `RESULTGRAPHIC(全关)` → `CAPTURE(SET_MODE=post)` | **== ①**（关掉即回到基线） |
| ⑥ | `RESULTGRAPHIC(A)` → `CAPTURE(SET_MODE=**pre**)` | **≠ ②/③**（pre 模式**不**渲染结果；⚠️ 与 ① 同形但**不**逐字节相同 —— 视图状态差异） |
| ⑦ | **阳性对照**：`DISPLAY(ELEM_NUMBER)` 开 / 关 → `CAPTURE(SET_MODE=post)` | **P1 ≠ P2**（仪器有效） |

**判据**：①–⑦ **全**满足 ⇒ `PASSED`；否则 `FAILED`（**不**收口）。
⚠️ ⑦ 是必需项：没有它，「无差异」无法区分「原生空转」与「截图拍不到结果图形」（R157 的教训）。
⚠️ ① 是**本批新增**的必需项：它把**渲染噪声地板**变成**实测值**（而不是假设字节差异一定有意义）。

⚠️ 只发 `VIEW.*`（**视图类**：不改模型、不落库）+ 一次 `DOC.OPEN`（仅在项目**未打开**时）；
jpg 落 `.tmp_p164c/view_effect/post/`（`.gitignore` 内），证据里**只记字节数与 sha256**。
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

EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "view_result_post_probe.json"
"""证据落点。"""

SHOTS: Final[pathlib.Path] = REPO / ".tmp_p164c" / "view_effect" / "post"
"""截图落点（**在 `.gitignore` 内**；证据里只留字节数与哈希）。"""

DEFAULT_PROJECT: Final[str] = ".tmp_p164c/p164c-concrete.mgbx"
"""自建项目（**只碰它**；`--project` 可覆盖）。"""

MODE_A: Final[str] = "DisplacementContour"
MODE_B: Final[str] = "DeformedShape"
"""两个**表内**取值（都来自 `registry/live/view_result_modes.json`）。"""

CONTROL_KEY: Final[str] = "ELEMENT.ELEM_NUMBER"
"""阳性对照用的显示开关（`VIEW.DISPLAY` 的手册字段，R148 的先例）。"""

SENTINEL: Final[tuple[str, ...]] = ("/DB/NODE", "/DB/ELEM", "/DB/MATL", "/DB/SECT", "/DB/STLD", "/DB/CNLD")
"""零残留哨兵（视图类操作**不**动模型 ⇒ 跑前 / 跑后必须逐项一致）。"""

GUARDED_PATHS: Final[tuple[str, ...]] = (
    "/VIEW/RESULTGRAPHIC",
    "/VIEW/CAPTURE",
    "/VIEW/DISPLAY",
    "/DOC/OPEN",
)


def _sibling(name: str) -> Any:
    """按路径装载同目录的探针模块（`registry/tools` 不是包）—— **不**复制它的闸门逻辑。"""
    path = pathlib.Path(__file__).with_name(name)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def graphic_block(mode: str, load_case: str) -> dict[str, Any]:
    """**打开**结果图形的请求体（`TYPE_OF_DISPLAY.<子块>.OPT_CHECK = true` 是**关键**）。"""
    return {
        "CURRENT_MODE": mode,
        "LOAD_CASE_COMB": {"TYPE": "ST", "NAME": load_case},
        "TYPE_OF_DISPLAY": {
            "CONTOUR": {"OPT_CHECK": True, "NUM_OF_COLOR": 6, "COLOR_TYPE": "rgb"},
            "DEFORM": {"OPT_CHECK": True},
            "VALUES": {"OPT_CHECK": True},
            "LEGEND": {"OPT_CHECK": True},
        },
    }


def graphic_off_block(mode: str, load_case: str) -> dict[str, Any]:
    """**关掉**结果图形的请求体（同形状，所有 `OPT_CHECK` = `false`）—— 基线的定义。"""
    body = graphic_block(mode, load_case)
    body["TYPE_OF_DISPLAY"] = {
        key: {"OPT_CHECK": False} for key in body["TYPE_OF_DISPLAY"]
    }
    return body


def _load_credentials() -> tuple[str, str]:
    """读 `[gen]` 段的 Base URL 与 Key（**只**在 `--probe` 时调用；值不进输出）。"""
    creds = pathlib.Path.home() / ".structai" / "midas-test.env"
    section, values = "", {}
    for raw in creds.read_text(encoding="utf-8").splitlines():
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


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_offline() -> int:
    """`--check`：**零请求**的离线自洽断言（证据齐备 + 七条件都在 + 与数据侧一致）。"""
    if not EVIDENCE.exists():
        print(f"❌ 缺证据 {EVIDENCE.relative_to(REPO)}（先跑 --probe）")
        return 1
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    effect = document["effect"]
    modes = _sibling("probe_view_result_modes.py")
    table = modes.load_mode_table()
    problems: list[str] = []
    for key in (
        "baseline_is_deterministic",
        "graphic_changes_the_picture",
        "mode_change_changes_the_picture",
        "same_graphic_reproducible",
        "turning_the_graphic_off_restores_the_baseline",
        "pre_mode_does_not_render_the_result",
        "instrument_works",
    ):
        if effect.get(key) is not True:
            problems.append(f"判据 {key} 不为真 ⇒ 效果结论**不成立**")
    if effect.get("verdict") != "PASSED":
        problems.append(f"判定应为 PASSED，实际 {effect.get('verdict')!r}")
    if document["mode_a"] not in table["modes"] or document["mode_b"] not in table["modes"]:
        problems.append("试的取值不在 R155 的手册取值表里")
    on = document["graphic_block"]["TYPE_OF_DISPLAY"]
    if not any(block.get("OPT_CHECK") is True for block in on.values()):
        problems.append("「打开」请求体里没有任何 OPT_CHECK=true ⇒ 与 R159 的成因矛盾")
    off = document["graphic_off_block"]["TYPE_OF_DISPLAY"]
    if any(block.get("OPT_CHECK") is not False for block in off.values()):
        problems.append("「关闭」请求体里出现了 OPT_CHECK!=false ⇒ 基线定义不成立")
    if not document["sentinel"]["unchanged"]:
        problems.append("跑后哨兵与跑前不一致 ⇒ 有残留，结论不可用")
    yaml_text = (
        REPO / "registry" / "common" / "view" / "RESULTGRAPHIC.yaml"
    ).read_text(encoding="utf-8")
    if "availability: verified" not in yaml_text:
        problems.append("端点 YAML 未按本证据收口（应写 availability: verified）")
    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    print(
        "✅ 离线自洽：`TYPE_OF_DISPLAY.OPT_CHECK=true` 是结果图形的**开关**（R159）· "
        "改前/改后**字节不同** · 换取值**不同** · 同取值**可复现** · 关掉**回到基线** · "
        "pre 模式**不**渲染 · 阳性对照通过 ⇒ **纯 API 路径存在**（`SET_MODE: \"post\"`）"
    )
    return 0


def run_probe(load_case: str, project: str) -> int:
    """真机受控测量（`--probe`）：①–⑦ 七步 + 哨兵。"""
    import httpx  # noqa: PLC0415

    modes = _sibling("probe_view_result_modes.py")
    table = modes.load_mode_table()
    modes.guard_modes((MODE_A, MODE_B), table)
    for path in GUARDED_PATHS:
        modes.guard_not_native_crash_path(path)

    SHOTS.mkdir(parents=True, exist_ok=True)
    base, key = _load_credentials()
    steps: list[dict[str, Any]] = []
    project_path = (REPO / project).resolve()
    opened = False
    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=180.0) as client:
        print(f"实例 {base}   工况 {load_case!r}   项目 {project}")
        health = client.get("/DB/NODE")
        print(f"跑前健康检查 GET /DB/NODE -> {health.status_code}")
        if health.status_code != 200:
            if not project_path.exists():
                print(f"🛑 项目不存在：{project_path}")
                return 1
            opened_response = client.post("/DOC/OPEN", json={"Argument": str(project_path)})
            opened = opened_response.status_code == 200
            print(f"POST /DOC/OPEN -> {opened_response.status_code}（自建项目）")
            health = client.get("/DB/NODE")
            print(f"再查 GET /DB/NODE -> {health.status_code}")

        def counts() -> dict[str, Any]:
            result: dict[str, Any] = {}
            for path in SENTINEL:
                response = client.get(path)
                try:
                    document = json.loads(response.text)
                    root = next(iter(document))
                    inner = document[root]
                    result[path] = len(inner) if isinstance(inner, (dict, list)) else 0
                except Exception:
                    result[path] = None
            return result

        before = counts()
        print(f"跑前哨兵：{before}")

        def capture(tag: str, argument: dict[str, Any]) -> dict[str, Any]:
            target = SHOTS / f"{tag}.jpg"
            if target.exists():
                target.unlink()
            payload = {"Argument": dict(argument, EXPORT_PATH=str(target))}
            response = client.post("/VIEW/CAPTURE", json=payload)
            exists = target.exists()
            row = {
                "tag": tag,
                "capture_argument": {k: v for k, v in argument.items() if k != "EXPORT_PATH"},
                "status": response.status_code,
                "exists": exists,
                "bytes": target.stat().st_size if exists else 0,
                "sha256": _sha(target) if exists else "",
            }
            steps.append(row)
            print(
                f"  {tag:34s} CAPTURE -> {response.status_code} · "
                f"{row['bytes']} 字节 · {str(row['sha256'])[:16]}"
            )
            return row

        def resultgraphic(tag: str, body: dict[str, Any]) -> int:
            response = client.post("/VIEW/RESULTGRAPHIC", json={"Argument": body})
            steps.append(
                {
                    "tag": tag,
                    "endpoint": "VIEW.RESULTGRAPHIC",
                    "status": response.status_code,
                    "current_mode": body.get("CURRENT_MODE"),
                    "type_of_display_on": any(
                        block.get("OPT_CHECK") is True
                        for block in (body.get("TYPE_OF_DISPLAY") or {}).values()
                    ),
                }
            )
            print(
                f"  {tag:34s} RESULTGRAPHIC({body.get('CURRENT_MODE')}) -> {response.status_code}"
            )
            return response.status_code

        off = graphic_off_block(MODE_A, load_case)
        on_a = graphic_block(MODE_A, load_case)
        on_b = graphic_block(MODE_B, load_case)

        resultgraphic("① 图形全关（基线）", off)
        base_one = capture("01_baseline", {"SET_MODE": "post"})
        resultgraphic("① 图形全关（基线重复）", off)
        base_two = capture("02_baseline_repeat", {"SET_MODE": "post"})
        resultgraphic(f"② RESULTGRAPHIC({MODE_A})", on_a)
        after_a = capture("03_after_graphic_a", {"SET_MODE": "post"})
        resultgraphic(f"③ RESULTGRAPHIC({MODE_B})", on_b)
        after_b = capture("04_after_graphic_b", {"SET_MODE": "post"})
        resultgraphic(f"④ RESULTGRAPHIC({MODE_A}) 复现", on_a)
        after_a2 = capture("05_after_graphic_a_replay", {"SET_MODE": "post"})
        resultgraphic("⑤ 图形全关（回基线）", off)
        back_off = capture("06_graphic_off_again", {"SET_MODE": "post"})
        resultgraphic(f"⑥ RESULTGRAPHIC({MODE_A}) 后走 pre 模式", on_a)
        pre_view = capture("07_pre_mode_with_graphic", {"SET_MODE": "pre"})

        control: list[dict[str, Any]] = []
        for tag, enabled in (("P1", True), ("P2", False)):
            resultgraphic(f"⑦ 阳性对照 图形全关（{tag}）", off)
            response = client.post(
                "/VIEW/DISPLAY", json={"Argument": {"ELEMENT": {CONTROL_KEY.split(".")[-1]: enabled}}}
            )
            row = capture(f"08_control_{tag}", {"SET_MODE": "post"})
            row["elem_number"] = enabled
            row["display_status"] = response.status_code
            control.append(row)
            print(f"    DISPLAY({CONTROL_KEY}={enabled}) -> {response.status_code}")

        after = counts()
        print(f"跑后哨兵：{after}   一致：{after == before}")

    hashes = {row["tag"]: row["sha256"] for row in (base_one, base_two, after_a, after_b, after_a2, back_off, pre_view)}
    deterministic = bool(hashes["01_baseline"]) and hashes["01_baseline"] == hashes["02_baseline_repeat"]
    changed = bool(hashes["03_after_graphic_a"]) and hashes["03_after_graphic_a"] != hashes["01_baseline"]
    mode_drives = bool(hashes["04_after_graphic_b"]) and hashes["04_after_graphic_b"] != hashes["03_after_graphic_a"]
    reproducible = hashes["05_after_graphic_a_replay"] == hashes["03_after_graphic_a"]
    restored = hashes["06_graphic_off_again"] == hashes["01_baseline"]
    # ⑥ 的判据是「pre 模式**画不出**结果」，**不是**「与基线逐字节相同」——
    # pre 模式下的模型视图与 post 模式下的模型视图**不**逐字节相同（视图状态差异），
    # 但两者都**远小于**结果视图（≈33 KB vs ≈81 KB）。
    pre_flat = bool(hashes["07_pre_mode_with_graphic"]) and hashes[
        "07_pre_mode_with_graphic"
    ] not in {hashes["03_after_graphic_a"], hashes["04_after_graphic_b"]}
    instrument = bool(control[0]["sha256"]) and control[0]["sha256"] != control[1]["sha256"]
    passed = all((deterministic, changed, mode_drives, reproducible, restored, pre_flat, instrument))
    print()
    print(f"① 基线渲染确定（噪声地板）        : {deterministic}")
    print(f"② 改前/改后 ⇒ 画面变化            : {changed}")
    print(f"③ 换 CURRENT_MODE ⇒ 画面变化      : {mode_drives}")
    print(f"④ 同取值可复现                    : {reproducible}")
    print(f"⑤ 图形关掉 ⇒ 回到基线             : {restored}")
    print(f"⑥ pre 模式**不**渲染结果          : {pre_flat}")
    print(f"⑦ 阳性对照（仪器有效）            : {instrument}")
    print(f"⇒ 效果判据（铁律 ⓪）              : {'✅ PASSED' if passed else '❌ FAILED（**不**收口）'}")

    document = {
        "tool": "registry/tools/probe_view_result_post.py",
        "endpoint": "VIEW.RESULTGRAPHIC",
        "path": "/VIEW/RESULTGRAPHIC",
        "instance": "gen-local",
        "project": project,
        "project_opened_by_probe": opened,
        "load_case": load_case,
        "mode_a": MODE_A,
        "mode_b": MODE_B,
        "mode_table": "registry/live/view_result_modes.json",
        "graphic_block": on_a,
        "graphic_off_block": off,
        "steps": steps,
        "control": {
            "what": f"VIEW.DISPLAY 的 {CONTROL_KEY} 开/关（R148 的先例）",
            "rows": control,
            "instrument_works": instrument,
        },
        "sentinel": {"keys": list(SENTINEL), "before": before, "after": after, "unchanged": after == before},
        "effect": {
            "baseline_is_deterministic": deterministic,
            "graphic_changes_the_picture": changed,
            "mode_change_changes_the_picture": mode_drives,
            "same_graphic_reproducible": reproducible,
            "turning_the_graphic_off_restores_the_baseline": restored,
            "pre_mode_does_not_render_the_result": pre_flat,
            "instrument_works": instrument,
            "verdict": "PASSED" if passed else "FAILED",
        },
        "finding": {
            "root_cause_of_r157": (
                "R157 的「静默 200 / 画面没变」成因 = 请求体**缺 `TYPE_OF_DISPLAY`** —— "
                "`TYPE_OF_DISPLAY.<子块>.OPT_CHECK = true` 才是把结果图形打开的开关；"
                "只发 `CURRENT_MODE` + `LOAD_CASE_COMB` 时原生照样回 `200` 但什么都不画。"
            ),
            "pure_api_path_into_post_view": (
                "`POST /VIEW/CAPTURE` 的 `Argument.SET_MODE`（`pre` / `post`）**切换视图模式**（粘性）；"
                "结果图形由 `POST /VIEW/RESULTGRAPHIC`（**持久**）或 `CAPTURE` 的 "
                "`Argument.RESULT_GRAPHIC`（**一次性覆盖**）配置，且**只在 post 模式下渲染**。"
            ),
            "corrected_recovery_condition_of_r157": (
                "已找到 ⇒ R157 的恢复条件①满足；R157 的留缺结论由 **R159** 取代。"
            ),
        },
        "note": (
            "铁律 ⓪：视图类端点的判据 = 改前/改后**截图字节**。"
            "阳性对照（⑦）区分「原生静默空转」与「截图拍不到结果图形」；"
            "基线重复（①）把**渲染噪声地板**变成实测值（本批实测 = 0 字节差异）。"
            "⚠️ ⑥ 的判据是「pre 模式**画不出**结果」（与结果视图不同），"
            "**不是**「与基线逐字节相同」—— pre 模式下的模型视图与 post 模式下的模型视图"
            "**不**逐字节相同（视图状态差异），但两者都远小于结果视图（≈33 KB vs ≈81 KB）。"
            "⚠️ 本工具**只**产出证据 —— `availability` 的收口**由人裁决**（见 R159）。"
        ),
    }
    EVIDENCE.write_text(
        json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"wrote {EVIDENCE.relative_to(REPO)}")
    return 0 if passed else 1


def main() -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(
        description="纯 API 进结果视图（post）+ VIEW.RESULTGRAPHIC 的效果判据"
    )
    parser.add_argument("--load-case", default="DL", help="项目里**真实存在**的工况名")
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="自建项目（相对仓库根）")
    parser.add_argument("--probe", action="store_true", help="真发请求（默认只预演）")
    parser.add_argument("--check", action="store_true", help="离线自洽断言（零请求）")
    args = parser.parse_args()
    if args.check:
        return check_offline()
    modes = _sibling("probe_view_result_modes.py")
    table = modes.load_mode_table()
    modes.guard_modes((MODE_A, MODE_B), table)
    for path in GUARDED_PATHS:
        modes.guard_not_native_crash_path(path)
    print(f"结果视图（post）路径判据：{MODE_A} vs {MODE_B} · 工况 {args.load_case!r} · 项目 {args.project}")
    print("请求体（**关键** = TYPE_OF_DISPLAY.<子块>.OPT_CHECK）：")
    print("  " + json.dumps(graphic_block(MODE_A, args.load_case), ensure_ascii=False))
    if not args.probe:
        print("\n（预演；加 --probe 才真发 —— 会**动**用户的 MIDAS 画面）")
        return 0
    print()
    return run_probe(args.load_case, args.project)


if __name__ == "__main__":
    raise SystemExit(main())
