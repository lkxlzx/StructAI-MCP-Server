#!/usr/bin/env python3
"""
P176 · `DESIGN.CONCRETE` 的**规范匹配**收口（`docs/07` §16.1 **R168** 的续）。

背景（**P164-c 的结论被本批推翻**）
-----------------------------------
P164-c（2026-10-14）记录：`DESIGN.RC.KDS-41-20-2022.BD-ANAL` **四次**打崩 `GenNX.exe`
（`wg_db.dll` / `0xc0000005` @ `0x2d97e5c`，四次同一偏移）⇒ 判定「产品缺陷、我方无法规避」。

⚠️ **P176 实测（同版本 `26.9.1.1001`）**：`BD-ANAL` **不崩**，且**设计结果真的产出**。
⇒ 当时的归因**不完整** —— 真正的原因是**规范不匹配**，不是端点本身有缺陷。

**根因（本批实测）**
--------------------
| 层 | 现象 |
| --- | --- |
| 设计规范 `DRC.DGNCODE` | `KDS 41 20 : 2022`（韩国） |
| 材料 `MATL.PARAM[].STANDARD` | `AS17(RC)`（**澳洲**）⇒ **库对不上** |
| 引擎行为 | 找不到「验算材料 / 截面类型 / 荷载组合」⇒ **跳过所有单元** |

⇒ 报 `400 failed:LoadCombination`（**干净拒绝**，不是崩溃）+ MIDAS 弹「验算结果错误」。

**修法**：`PUT /design/RC/DRC` → `DGNCODE: "GB/T50010-10"`（**中国混凝土规范 2010**，
`MIDAS_API_Online_Manual_完整API手册_v1.0.md:6740` 的规范码表第 **38** 项）
⇒ 规范族**内部一致** ⇒ `BD-ANAL` `200 {"message":"success"}` ∧ `BD-TABLE` **有结果行**。

⚠️ **`DCO` 必须留空或与 `DRC` 同规范**：填 `KDS 41 20 : 2022` 而 `DRC` 是 `GB/T50010-10`
⇒ **又变回** `failed:LoadCombination`（实测）。中国规范下 `DCO` 的字段集**与 KDS 不同**
（`CONC_STRS_STRN` 被拒），手册**只给了 KDS 示例** ⇒ 本批**不**配 `DCO`。

判据（**铁律 ⓪**：效果，不是状态码）
------------------------------------
`BD-ANAL` `200 {"message":"success"}` ∧ `BD-TABLE` 的 **`DATA` 行数 > 0**（设计结果真的产出）。
⚠️ 只 `200` 不算 —— P164-c 之前也见过「`200` 但没结果」。

用法
----
    python registry/tools/probe_concrete_code_match_p176.py            # 预演（零请求）
    python registry/tools/probe_concrete_code_match_p176.py --probe    # 真机（**有副作用**）
    python registry/tools/probe_concrete_code_match_p176.py --check    # 离线自洽（零请求）
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Final

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]

PASSED: Final[str] = "PASSED"
FAILED: Final[str] = "FAILED"
CRITERION_VERSION: Final[int] = 1

EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "concrete_code_match_probe.json"
WORKSPACE: Final[pathlib.Path] = REPO / ".tmp_p176"

SAMPLE_SOURCE: Final[pathlib.Path] = REPO / ".tmp_p164c" / "p164c-concrete.mgbx"
"""P164-c 建的那个**混凝土简支梁**（21 节点 / 20 单元）—— 逐字复现当时的场景。"""

BACKUP_NAME: Final[str] = "p176-code-match-backup.mgbx"
SAMPLE_NAME: Final[str] = "p176-code-match.mgbx"

DESIGN_CODE: Final[str] = "GB/T50010-10"
"""中国混凝土规范 2010（手册规范码表第 38 项；实测被实例接受）。"""

PRIOR_CODE: Final[str] = "KDS 41 20 : 2022"
"""P164-c 当时用的规范（韩国）—— 与模型材料规范 `AS17(RC)` **不匹配**。"""

ANAL: Final[str] = "/design/RC/KDS-41-20-2022/BD-ANAL"
TABLE: Final[str] = "/design/RC/KDS-41-20-2022/BD-TABLE"
DRC: Final[str] = "/design/RC/DRC"
LCOM: Final[str] = "/db/LCOM-CONC"

ELEMENTS: Final[tuple[int, ...]] = tuple(range(1, 21))

HEALTH_PATH: Final[str] = "/db/NODE"

ALLOWED_PATHS: Final[frozenset[str]] = frozenset(
    {
        "/DOC/CLOSE",
        "/DOC/OPEN",
        "/DOC/SAVEAS",
        "/DOC/ANAL",
        ANAL,
        TABLE,
        DRC,
        LCOM,
    }
)


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


def guard_paths(*, allow_native_crash_risk: bool) -> None:
    """发请求**之前**的自检（复用 `app/**` 的崩溃族常量）。

    ⚠️ `BD-ANAL` 在 `NATIVE_CRASH_ENDPOINTS` 里（P164-c 的事故留下）⇒ 默认**拦住**；
    要跑必须显式 `allow_native_crash_risk=True`（= 用户已授权「可能打崩 MIDAS」）。
    """
    sys.path.insert(0, str(REPO))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        guard_native_crash_path,
    )

    for path in ALLOWED_PATHS:
        guard_native_crash_path(path, allow_native_crash_risk=allow_native_crash_risk)
    print(
        f"闸门自检：声明路径 {len(ALLOWED_PATHS)} 条 · "
        f"崩溃族放行 = {allow_native_crash_risk}（需用户显式授权）"
    )


def _design_rows(client: Any) -> tuple[int, list[Any]]:
    """取 `BD-TABLE` 的结果行（判据的落点）。"""
    body = {"Argument": {"TABLE_TYPE": "MEMB", "PRI_SORT": 1, "RESULT": 0}}
    response = client.post(TABLE, json=body)
    payload = response.json() if response.status_code == 200 else {}
    block: Any = {}
    for value in payload.values():
        if isinstance(value, dict) and "DATA" in value:
            block = value
            break
    rows = block.get("DATA") or []
    return len(rows), rows


def run_probe(repo: pathlib.Path, *, allow_crash: bool) -> int:
    """真机（**有副作用**；`BD-ANAL` 需 `--allow-native-crash-risk`）。"""
    guard_paths(allow_native_crash_risk=allow_crash)
    import shutil  # noqa: PLC0415
    import time  # noqa: PLC0415

    import httpx  # noqa: PLC0415

    base, key = _load_credentials()
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    backup = (WORKSPACE / BACKUP_NAME).resolve()
    sample = (WORKSPACE / SAMPLE_NAME).resolve()

    if not SAMPLE_SOURCE.is_file():
        print(f"🛑 样本不存在：{SAMPLE_SOURCE}")
        return 1

    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=300.0) as client:
        # ---- 第 0 步（R144）：备份现场 ----
        # ⚠️ **P176 实测踩到**：`SAVEAS` 在**无项目**时会**静默失败**（`200` 但不落盘）
        # ⇒ 备份**不能**只靠它。这里改为「先 `OPEN` 一个已知有路径的文件」——
        # 既确立路径（R144），又留下退路；样本文件本身就是那份混凝土模型。
        shutil.copy2(SAMPLE_SOURCE, sample)
        opened = client.post("/DOC/OPEN", json={"Argument": str(sample)}).status_code
        print(f"  打开样本副本 → {opened}（**只读源**；副本可写）")
        # 备份 = 再存一份到 `backup`（此时**确已**有项目 ⇒ `SAVEAS` 才真的落盘）
        saved = client.post("/DOC/SAVEAS", json={"Argument": str(backup)}).status_code
        backup_ok = backup.is_file()
        print(f"  备份现场 → {backup.name}（SAVEAS={saved} · 落盘={backup_ok}）")
        # `SAVEAS` 会把项目切到 `backup` ⇒ 切回样本副本继续测量
        client.post("/DOC/OPEN", json={"Argument": str(sample)})

        # ---- 相 ①：**KDS**（P164-c 当时的规范）+ 与材料规范不一致 ----
        client.put(DRC, json={"Assign": {"1": {"DGNCODE": PRIOR_CODE}}})
        # 组合按 KDS 生成（`OPE.LCOM-CONC` 只支持 KDS）
        for item in client.get(LCOM).json().get("LCOM-CONC") or {}:
            client.delete(f"{LCOM}/{item}")
        client.post("/ope/LCOM-CONC", json={"Argument": {"OPTION": "ADD", "DGNCODE": PRIOR_CODE}})
        client.post("/DOC/ANAL", json={"Argument": {"TYPE": "STATIC"}})
        time.sleep(4)
        prior = client.post(ANAL, json={"Argument": {"PERFORM_TYPE": "ALL"}})
        prior_rows, _ = _design_rows(client)
        print(f"  ① 规范={PRIOR_CODE} → BD-ANAL {prior.status_code} · 结果行 {prior_rows}")

        # ---- 相 ②：**中国规范**（与手册规范码表第 38 项一致）----
        switched = client.put(DRC, json={"Assign": {"1": {"DGNCODE": DESIGN_CODE}}}).status_code
        # ⚠️ `DCO` 必须**留空**（中国规范下字段集与 KDS 不同；填 KDS 值会让引擎又拒绝）
        client.delete("/design/RC/KDS-41-20-2022/DCO/1")
        # 清掉 KDS 组合，手工建一条（`OPE.LCOM-CONC` 只支持 KDS）
        for item in client.get(LCOM).json().get("LCOM-CONC") or {}:
            client.delete(f"{LCOM}/{item}")
        client.post(
            LCOM,
            json={
                "Assign": {
                    "1": {
                        "NO": 1,
                        "NAME": "cLCB1",
                        "ACTIVE": "STRENGTH",
                        "bCB": False,
                        "iTYPE": 0,
                        "DESC": "",
                        "vCOMB": [
                            {"ANAL": "ST", "LCNAME": "DL", "FACTOR": 1.2},
                            {"ANAL": "ST", "LCNAME": "SIDL", "FACTOR": 1.4},
                        ],
                    }
                }
            },
        )
        client.post("/DOC/ANAL", json={"Argument": {"TYPE": "STATIC"}})
        time.sleep(4)
        after = client.post(ANAL, json={"Argument": {"PERFORM_TYPE": "ALL"}})
        after_rows, rows = _design_rows(client)
        print(f"  ② 规范={DESIGN_CODE} → BD-ANAL {after.status_code} · 结果行 {after_rows}")

        ok = int(after.status_code) == 200 and after_rows > 0 and prior_rows == 0

        # ---- 收尾（R144）：还原现场 ----
        # ⚠️ **不**发 `CLOSE`（无项目时后续 `OPEN` 也可能 404）—— 直接 `OPEN` 回备份。
        restored = client.post("/DOC/OPEN", json={"Argument": str(backup)}).status_code
        pjcf = (client.get("/db/PJCF").json().get("PJCF") or {}).get("1") or {}
        has_path = str(pjcf.get("FILE_NAME") or "") not in {"", "无标题"}
        print(f"  收尾：OPEN={restored} · FILE_NAME={pjcf.get('FILE_NAME')!r}（有路径={has_path}）")

    evidence = {
        "note": [
            "P176 · `DESIGN.CONCRETE` 的**规范匹配**（推翻 P164-c 的「BD-ANAL 必崩」）。",
            "**判据（铁律 ⓪）**：`BD-ANAL` `200` ∧ `BD-TABLE` 的 `DATA` **行数 > 0**"
            "（设计结果真的产出）。",
            f"**根因**：设计规范（{PRIOR_CODE}）与模型材料规范（`AS17(RC)`）**不匹配**"
            " ⇒ 引擎找不到「验算材料 / 截面类型 / 荷载组合」⇒ **跳过所有单元**（不崩）。",
            f"**修法**：`DRC.DGNCODE` → `{DESIGN_CODE}`（手册规范码表第 38 项）"
            " ⇒ 规范族内部一致 ⇒ 设计真的跑出结果。",
            "⚠️ **`DCO` 必须留空或与 `DRC` 同规范**（填 KDS 值而 `DRC` 是中国规范 ⇒ 又失败）。",
            "⚠️ **`OPE.LCOM-CONC` 只支持 KDS**（端点名即 `- KDS 41 20 : 2022`）"
            " ⇒ 中国规范下组合要**手工建**。",
            "⚠️ 本探针的 `BD-ANAL` 步受 `NATIVE_CRASH_ENDPOINTS` 护栏约束"
            " ⇒ 需 `--allow-native-crash-risk`（用户已授权）。",
        ],
        "criterion_version": CRITERION_VERSION,
        "instance": {"alias": "gen-local", "product": "GEN_NX", "base_url": base},
        "sample": {"source": str(SAMPLE_SOURCE), "copy": sample.name},
        "phases": {
            "prior": {
                "design_code": PRIOR_CODE,
                "status": int(prior.status_code),
                "design_rows": prior_rows,
            },
            "matched": {
                "design_code": DESIGN_CODE,
                "drc_switch_status": int(switched),
                "status": int(after.status_code),
                "design_rows": after_rows,
                "sample_rows": rows[:3],
            },
        },
        "session": {
            "backup": backup.name,
            "backup_written": backup_ok,
            "restored": restored == 200,
            "file_name": pjcf.get("FILE_NAME"),
            "has_project_path": has_path,
        },
        "verdict": PASSED if ok and has_path else FAILED,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"⇒ 判定：{'✅ ' + PASSED if evidence['verdict'] == PASSED else '❌ ' + FAILED}")
    print(f"wrote {EVIDENCE.relative_to(REPO)}")
    return 0 if evidence["verdict"] == PASSED else 1


def check_offline(repo: pathlib.Path) -> int:
    """`--check`：证据齐备 + 判据全真 + **两相对照成立**（**零请求**）。"""
    if not EVIDENCE.is_file():
        print(f"❌ 缺证据 {EVIDENCE.relative_to(REPO)}（先跑 --probe）")
        return 1
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    problems: list[str] = []

    if document.get("verdict") != PASSED:
        problems.append(f"顶层 verdict 应为 PASSED，实际 {document.get('verdict')!r}")
    phases = document.get("phases") or {}
    prior = phases.get("prior") or {}
    matched = phases.get("matched") or {}
    # 相 ①（规范不匹配）⇒ 必须 **0 行**
    if int(prior.get("design_rows") or 0) != 0:
        problems.append("相 ①（规范不匹配）竟产出了结果行 ⇒ 根因不成立")
    # 相 ②（规范匹配）⇒ 必须 **> 0 行** 且 `200`
    if int(matched.get("status") or 0) != 200:
        problems.append(f"相 ② 的 `BD-ANAL` 状态 {matched.get('status')} ≠ 200")
    if int(matched.get("design_rows") or 0) <= 0:
        problems.append("相 ② **没有**设计结果行 ⇒ 「效果」不成立（`200` 不算数）")
    if int(matched.get("drc_switch_status") or 0) != 200:
        problems.append("`DRC` 切规范未成功")
    if str(matched.get("design_code") or "") != DESIGN_CODE:
        problems.append(f"相 ② 的规范应为 `{DESIGN_CODE}`")
    session = document.get("session") or {}
    if session.get("has_project_path") is not True:
        problems.append("收尾时项目**无路径**（R144 事故条件）")
    if session.get("restored") is not True:
        problems.append("现场未还原")
    if session.get("backup_written") is not True:
        problems.append("备份未真的落盘 ⇒ 无退路（R144）")
    if document.get("sample", {}).get("source") != str(SAMPLE_SOURCE):
        problems.append("样本来源与声明不符")

    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    print(
        f"✅ 离线自洽：**两相对照成立** —— 规范 `{PRIOR_CODE}`（不匹配）⇒ "
        f"`BD-ANAL` {prior.get('status')} · **0 行**；规范 `{DESIGN_CODE}`（匹配）⇒ "
        f"`BD-ANAL` {matched.get('status')} · **{matched.get('design_rows')} 行**"
        f" ⇒ 「规范匹配 ⇒ 设计真的产出」成立（⇒ 推翻 P164-c 的「必崩」归因）"
    )
    return 0


def main() -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="DESIGN.CONCRETE 的规范匹配收口证据")
    parser.add_argument("--probe", action="store_true", help="真发请求（默认只预演）")
    parser.add_argument("--check", action="store_true", help="离线自洽断言（零请求）")
    parser.add_argument(
        "--allow-native-crash-risk",
        action="store_true",
        help="放开崩溃族护栏（**需用户显式授权**：BD-ANAL 在 P164-c 打崩过 MIDAS）",
    )
    args = parser.parse_args()
    if args.check:
        return check_offline(REPO)

    print(f"样本（**只读**）：{SAMPLE_SOURCE}")
    print(f"相 ①：规范 `{PRIOR_CODE}`（与材料 `AS17(RC)` 不匹配）⇒ 预期 **0 行**")
    print(f"相 ②：规范 `{DESIGN_CODE}`（中国，手册规范码表第 38 项）⇒ 预期 **> 0 行**")
    if not args.probe:
        print("\n（预演；加 --probe 才真发）")
        return 0
    print()
    return run_probe(REPO, allow_crash=args.allow_native_crash_risk)


if __name__ == "__main__":
    raise SystemExit(main())
