#!/usr/bin/env python3
"""
P176 · **经 MCP** 的设计规范切换（`docs/07` §16.1 **R168** 续的收尾判据）。

为什么需要它
------------
`probe_concrete_code_match_p176.py` 走**裸 HTTP**，证明「规范匹配 ⇒ 设计真的产出」。
本探针证明的是**另一件事**：这条链路能**经 MCP 契约**跑通 ——
`MCP Tool → OperationPlan → Adapter → MidasHttpClient → 原生`。
⚠️ 两者**不**可互相替代（端点可用 ≠ 在编排 / 护栏 / 权限 / 字段集之下可用）。

本批改了什么（被本探针验证的）
------------------------------
用户指出：**接口层写死了设计规范 / 材料 / 字段集**。本批把它变成**运行时数据**：
① `design_code` **裸字符串**被归一化（原先 `_mapping_list` 对字符串返回空列表
   ⇒ `DRC` 步**静默跳过** ⇒ 规范根本没切换，而调用方看不出异常）；
② 配置端点（`DCO`）的**可接受字段集随生效规范变化**（实测：KDS 12 / 13、`GB/T50010-10` **0**）
   ⇒ 从 `registry/live/design_code_field_sets.json` 按 `(material, code)` 注入。

判据（**铁律 ⓪**：效果，不是状态码）
------------------------------------
1. **切换真的生效** —— `GET /design/RC/DRC` 读回 `DGNCODE` == 调用方给的那个码；
2. **设计真的产出** —— `BD-ANAL` `200` ∧ `BD-TABLE` 的 `DATA` **行数 > 0**；
3. **跳过是显式的** —— `GB/T50010-10` 下 `DCO` 字段集为空 ⇒ 该步在 `skipped` 里，
   **不**报错（实测：`DCO` 为空时设计链照常跑通）；
4. **收尾有路径**（R144）。

用法
----
    python registry/tools/probe_design_code_via_mcp_p176.py            # 预演（零请求）
    python registry/tools/probe_design_code_via_mcp_p176.py --probe    # 真机（**有副作用**）
    python registry/tools/probe_design_code_via_mcp_p176.py --check    # 离线自洽（零请求）
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

EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "design_code_mcp_probe.json"
WORKSPACE: Final[pathlib.Path] = REPO / ".tmp_p176"
SAMPLE_SOURCE: Final[pathlib.Path] = REPO / ".tmp_p164c" / "p164c-concrete.mgbx"
BACKUP_NAME: Final[str] = "p176-mcp-backup.mgbx"
SAMPLE_NAME: Final[str] = "p176-mcp-sample.mgbx"

TOOL: Final[str] = "engineering_design"
OPERATION: Final[str] = "DESIGN.CONCRETE"
DESIGN_CODE: Final[str] = "GB/T50010-10"
"""中国混凝土规范（手册规范码表第 38 项；P176 实测被实例接受）。"""

ELEMENTS: Final[tuple[int, ...]] = tuple(range(1, 21))

MATERIAL_STANDARD: Final[str] = "GB/T10(RC)"
"""**材料库**名（与设计规范**同族** —— 中国）。

⚠️ 它是 `MATL.STANDARD` 的取值，**不是**设计规范码：`GB/T50010-10` 在此字段上
会被原生拒（`400 Unknown Error`，P176 逐值实测）。"""

MATERIAL_DB: Final[str] = "C30"
"""材料库内的**具体牌号**（实测被接受）。"""

# 配置端点的**末段** → `skipped` 里出现时的形态（`EndpointStep.key`）
DCO_KEY: Final[str] = "DESIGN.RC.KDS-41-20-2022.DCO"
ANAL_KEY: Final[str] = "DESIGN.RC.KDS-41-20-2022.BD-ANAL"
TABLE_KEY: Final[str] = "DESIGN.RC.KDS-41-20-2022.BD-TABLE"

ALLOWED_PATHS: Final[frozenset[str]] = frozenset(
    {
        "/DOC/OPEN",
        "/DOC/SAVEAS",
        "/DOC/ANAL",
        "/DB/NODE",
        "/DB/PJCF",
        "/DESIGN/RC/DRC",
        "/DESIGN/RC/KDS-41-20-2022/DCO",
        "/DESIGN/RC/KDS-41-20-2022/DCTL",
        "/DESIGN/RC/KDS-41-20-2022/MEMB",
        "/DESIGN/RC/KDS-41-20-2022/BD-ANAL",
        "/DESIGN/RC/KDS-41-20-2022/BD-TABLE",
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
    """发请求**之前**的自检（`BD-ANAL` 在崩溃族里 ⇒ 需用户显式授权）。"""
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


def _parameters() -> dict[str, Any]:
    """`DESIGN.CONCRETE` 的参数（**裸字符串** `design_code` —— 本批新支持的形式）。"""
    return {
        "perform_type": "ALL",
        # ⚠️ **裸字符串**（不是 `[{"dgn_code": ...}]`）—— 本批 Phase 1 才支持；
        # 原先它会被 `_mapping_list` 吞成空列表 ⇒ `DRC` 步**静默跳过**。
        "design_code": DESIGN_CODE,
        "design_members": [{"id": "1", "elements": list(ELEMENTS)}],
        # ⚠️ **P176 实测**：`DCTL`（框架控制）**必需** —— 不传它，该步会被
        #    `_has_payload` **跳过**，而设计引擎随后对 `BD-ANAL` 回**原生 `400`**
        #    （`STRUCTAI-2200`）。手工验证时配过它 ⇒ 才跑通。
        #    字段照 `registry/live/write_templates.json` 的 `DESIGN.RC...DCTL` 模板。
        "design_frame": [
            {
                "id": "1",
                "frame_x": "Braced Non-sway",
                "frame_y": "Braced Non-sway",
                "auto_kf": True,
            }
        ],
    }


def run_probe(repo: pathlib.Path, *, allow_crash: bool) -> int:
    """真机（**有副作用**；`BD-ANAL` 需 `--allow-native-crash-risk`）。"""
    guard_paths(allow_native_crash_risk=allow_crash)
    import asyncio  # noqa: PLC0415
    import os  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    import httpx  # noqa: PLC0415

    base_url, mapi_key = _load_credentials()
    os.environ.setdefault("MIDAS_BASE_URL", base_url)
    os.environ.setdefault("MIDAS_MAPI_KEY", mapi_key)

    import importlib.util  # noqa: PLC0415

    spec = importlib.util.spec_from_file_location(
        "probe_interface_paths", repo / "registry" / "tools" / "probe_interface_paths.py"
    )
    assert spec is not None and spec.loader is not None
    stack_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stack_module)

    WORKSPACE.mkdir(parents=True, exist_ok=True)
    backup = (WORKSPACE / BACKUP_NAME).resolve()
    sample = (WORKSPACE / SAMPLE_NAME).resolve()

    async def run() -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="p176-mcp-", ignore_cleanup_errors=True) as raw_dir:
            # ⚠️ **`allow_unverified=True`**（Contract-Test 口径）：`BD-ANAL` 的
            #    `availability` 是 **`untested`**（P164-c 事故留下的裁定）⇒ 生产口径下
            #    核心会**先拦**（`STRUCTAI-3000 registry_mapping_not_verified`，**零请求**）。
            #    本探针要**测量**它是否可用 ⇒ 必须走契约口径（这正是该参数的**唯一**用途）。
            # ⚠️ **`allow_native_crash_risk`**：`BD-ANAL` 在 `NATIVE_CRASH_ENDPOINTS` 里
            #    （P164-c 的事故留下）⇒ 默认**不发**（`STRUCTAI-1200 native_crash_risk`）。
            #    P176 已实测**不崩**（同版本），但护栏**不**因此自动放宽
            #    —— 必须显式 `--allow-native-crash-risk`（= 用户已授权）。
            async with stack_module._Stack(  # noqa: SLF001 - 复用既有装配
                repo,
                pathlib.Path(raw_dir),
                allow_unverified=True,
                allow_native_crash_risk=allow_crash,
            ) as stack:
                # ---- 第 0 步（R144）：备份现场 ----
                shutil.copy2(SAMPLE_SOURCE, sample)
                opened = await stack.call(
                    "engineering_doc", "OPEN", {"project_path": str(sample)}, confirm=True
                )
                print(f"  打开样本副本 → success={opened.get('success')}")
                await stack.call(
                    "engineering_doc", "SAVE_AS", {"project_path": str(backup)}, confirm=True
                )
                backup_ok = backup.is_file()
                print(f"  备份 → {backup.name}（落盘={backup_ok}）")

                # ---- 前置 ①：建混凝土设计组合（样本里没有；中国规范下 `OPE.LCOM-CONC` 不可用）----
                # ⚠️ **P176 实测**：`OPE.LCOM-CONC` 的端点名就写着 `- KDS 41 20 : 2022`
                #    ⇒ 非 KDS 规范下要**手工**写 `DB.LCOM-CONC`。
                async with httpx.AsyncClient(
                    base_url=base_url, headers={"MAPI-Key": mapi_key}, timeout=60.0
                ) as client:
                    existing = (await client.get("/db/LCOM-CONC")).json().get("LCOM-CONC") or {}
                    for item in existing:
                        await client.delete(f"/db/LCOM-CONC/{item}")
                    await client.post(
                        "/db/LCOM-CONC",
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
                print("  前置组合 → 手工建 `cLCB1`（中国规范下 `OPE.LCOM-CONC` 不可用）")

                # ---- 前置 ②：**材料规范同族对齐**（P176 实测的关键一步）----
                # ⚠️ **P176 实测踩到**：只切**设计规范**不够 —— 模型材料库仍是 `AS17(RC)`
                #    （**澳洲**）⇒ 引擎找不到「验算材料」⇒ `400 failed:LoadCombination`。
                #    **三处必须同族**：设计规范 `DRC.DGNCODE` · 材料库 `MATL.STANDARD`
                #    · 配筋库 `MDGN.CONC_CODE`。
                #    ⚠️ `MATL.STANDARD` 的**合法取值是材料库名**（`GB/T10(RC)`），
                #    **不是**设计规范码（`GB/T50010-10` 会被原生拒：`400 Unknown Error`）。
                async with httpx.AsyncClient(
                    base_url=base_url, headers={"MAPI-Key": mapi_key}, timeout=60.0
                ) as client:
                    material = (await client.get("/db/MATL")).json().get("MATL", {})
                    row = dict(material.get("1") or {})
                    row["PARAM"] = [
                        {
                            "P_TYPE": 1,
                            "STANDARD": MATERIAL_STANDARD,
                            "CODE": "",
                            "DB": MATERIAL_DB,
                            "bELAST": False,
                            "ELAST": 30000000,
                        }
                    ]
                    applied = await client.put("/db/MATL", json={"Assign": {"1": row}})
                    readback = (await client.get("/db/MATL")).json().get("MATL", {})
                params = ((readback.get("1") or {}).get("PARAM") or [{}])[0]
                actual_standard = params.get("STANDARD")
                material_aligned = actual_standard == MATERIAL_STANDARD
                print(
                    f"  前置材料 → STANDARD={actual_standard!r}"
                    f"（PUT {applied.status_code}）· 对齐={material_aligned}"
                )

                # ---- 前置 ③：跑分析（`DESIGN.CONCRETE` 的编排里**没有** `DOC.ANAL` 步）----
                # ⚠️ **P176 实测踩到**：设计引擎要求「先有分析结果」（否则 `BD-ANAL` 回
                #    `400 Please perform analysis`），而 `DESIGN.CONCRETE` 的 6 步里
                #    **不含**分析 ⇒ 必须由调用方**先**单独跑一次 `ANALYSIS.STATIC`。
                # ⚠️ **P176 实测踩到**：经 MCP 的 `ANALYSIS.STATIC` 回 `success=True`，
                #    但**分析结果仍是 0 行**（R135：`DOC.ANAL` 的 `200` **不**代表算完）。
                #    ⇒ 这里改用**裸 `DOC.ANAL` + 有界等待**，并以「结果行数 > 0」为判据。
                async with httpx.AsyncClient(
                    base_url=base_url, headers={"MAPI-Key": mapi_key}, timeout=300.0
                ) as client:
                    await client.post("/DOC/ANAL", json={"Argument": {"TYPE": "STATIC"}})
                    analyzed_rows = 0
                    for _ in range(10):
                        await asyncio.sleep(3)
                        payload = (
                            await client.post(
                                "/POST/TABLE",
                                json={"Argument": {"TABLE_TYPE": "DISPLACEMENTG"}},
                            )
                        ).json()
                        block = payload.get("empty") or {}
                        analyzed_rows = len(block.get("DATA") or [])
                        if analyzed_rows > 0:
                            break
                print(f"  前置分析 → 结果行 {analyzed_rows}（**有界等待**，判据 = 行数 > 0）")
                if analyzed_rows <= 0:
                    print("🛑 分析**没有**产出结果 ⇒ 设计引擎必然拒 ⇒ 判据不成立")
                    return 1

                # ---- 经 MCP 跑 DESIGN.CONCRETE ----
                parameters = _parameters()
                print(f"  `design_code` = {DESIGN_CODE!r}（**裸字符串**）")
                outcome = await stack.run_operation(TOOL, OPERATION, parameters, confirm=True)
                response = outcome.get("response") or {}
                task = outcome.get("task") or {}
                # ⚠️ **P176 实测**：`DESIGN.CONCRETE` 是 composite ⇒ ASYNC 任务跑完后
                #    `result_json` 仍为 `None`（`complete()` 返回 `{}`）⇒ **拿不到**
                #    `executed` / `skipped` 明细。⇒ 判据改为从**实际发出的请求**读 ——
                #    那才是「效果」的直接证据（比解析返回结构更硬）。
                calls = list(outcome.get("requests") or [])
                sent_paths = [str(call.get("path") or "") for call in calls]
                executed = sent_paths
                for call in calls:
                    print(
                        f"  [请求] {call.get('method')} {call.get('path')} "
                        f"body={json.dumps(call.get('body'), ensure_ascii=False)[:160]}"
                    )
                # 判据 ③：`DCO` 在**该规范下字段集为空** ⇒ 该步**不**被发出（跳过是显式的）
                dco_sent = any(path.endswith("/DCO") for path in sent_paths)
                dco_skipped = not dco_sent
                print(f"  ③ 发出 `DCO` 请求 = {dco_sent} ⇒ 跳过={dco_skipped}")

                # ---- 判据 ①：切换真的生效（读回 `DGNCODE`）----
                async with httpx.AsyncClient(
                    base_url=base_url, headers={"MAPI-Key": mapi_key}, timeout=60.0
                ) as client:
                    drc = (await client.get("/design/RC/DRC")).json()
                actual_code = ((drc.get("DCON") or {}).get("1") or {}).get("DGNCODE")
                switched = actual_code == DESIGN_CODE
                print(f"  ① 读回 DGNCODE = {actual_code!r} ⇒ 生效={switched}")

                # ---- 诊断：`BD-TABLE` 那一刻的三处规范是否同族 ----
                async with httpx.AsyncClient(
                    base_url=base_url, headers={"MAPI-Key": mapi_key}, timeout=60.0
                ) as client:
                    _drc = (await client.get("/design/RC/DRC")).json()
                    _matl = (await client.get("/db/MATL")).json()
                    _mdgn = (await client.get("/db/MDGN")).json()
                _code = ((_drc.get("DCON") or {}).get("1") or {}).get("DGNCODE")
                _std = ((((_matl.get("MATL") or {}).get("1") or {}).get("PARAM") or [{}])[0]).get(
                    "STANDARD"
                )
                _rebar = ((_mdgn.get("MDGN") or {}).get("1") or {}).get("CONC_CODE")
                print(f"  [诊断] DRC={_code!r} · MATL={_std!r} · MDGN={_rebar!r}")

                # ---- 判据 ②：设计真的产出（`BD-TABLE` 的 DATA 行数）----
                async with httpx.AsyncClient(
                    base_url=base_url, headers={"MAPI-Key": mapi_key}, timeout=180.0
                ) as client:
                    body = {
                        "Argument": {
                            "TABLE_TYPE": "MEMB",
                            "ELEMS": {"KEYS": list(ELEMENTS)},
                            "PRI_SORT": 1,
                            "RESULT": 0,
                        }
                    }
                    response = await client.post("/design/RC/KDS-41-20-2022/BD-TABLE", json=body)
                payload = response.json() if response.status_code == 200 else {}
                block: Any = {}
                for value in payload.values():
                    if isinstance(value, dict) and "DATA" in value:
                        block = value
                        break
                rows = list(block.get("DATA") or [])
                print(f"  ② BD-TABLE → {response.status_code} · 结果行 {len(rows)}")

                # ---- 收尾（R144）----
                await stack.call(
                    "engineering_doc", "OPEN", {"project_path": str(backup)}, confirm=True
                )
                async with httpx.AsyncClient(
                    base_url=base_url, headers={"MAPI-Key": mapi_key}, timeout=60.0
                ) as client:
                    pjcf_body = (await client.get("/db/PJCF")).json()
                pjcf = (pjcf_body.get("PJCF") or {}).get("1") or {}
                has_path = str(pjcf.get("FILE_NAME") or "") not in {"", "无标题"}
                print(f"  收尾：FILE_NAME={pjcf.get('FILE_NAME')!r}（有路径={has_path}）")

                return {
                    "executed": executed,
                    "dco_sent": dco_sent,
                    "switched": switched,
                    "actual_code": actual_code,
                    "table_status": int(response.status_code),
                    "design_rows": len(rows),
                    "sample_rows": rows[:2],
                    "dco_skipped": dco_skipped,
                    "backup_written": backup_ok,
                    "has_project_path": has_path,
                    "file_name": pjcf.get("FILE_NAME"),
                    "operation_error": outcome.get("error"),
                    "task_status": task.get("status"),
                    "task_error": task.get("error"),
                    "material_standard": actual_standard,
                    "material_aligned": material_aligned,
                }

    result = asyncio.run(run())
    ok = (
        result["switched"]
        and result["table_status"] == 200
        and result["design_rows"] > 0
        and result["dco_skipped"]
        and result["backup_written"]
        and result["has_project_path"]
    )
    evidence = {
        "note": [
            "P176 · **经 MCP** 的设计规范切换（`DESIGN.CONCRETE`，`design_code` 用**裸字符串**）。",
            "⚠️ 与 `concrete_code_match_probe.json` **不可互替**：那个证明**裸 HTTP** 可用，",
            "   本证据证明**经 MCP 契约**可用"
            "（Tool → OperationPlan → Adapter → 字段集注入 → 原生）。",
            "**判据（铁律 ⓪：效果，不是状态码）**：① `DRC` 读回 `DGNCODE` == 调用方给的码；",
            "   ② `BD-ANAL` `200` ∧ `BD-TABLE` 的 `DATA` **行数 > 0**；",
            "   ③ `DCO` 在 `skipped` 里（该规范字段集为空 ⇒ 跳过是**显式**的、**不**报错）；",
            "   ④ 收尾项目**有路径**（R144）。",
            "**本批消除的硬编码**：`design_code` 裸字符串原先被 `_mapping_list` 吞成空列表",
            "   ⇒ `DRC` 步**静默跳过**（规范没切换而调用方看不出）；配置端点字段集原先写死在",
            "   Transformer 类级常量 ⇒ 换规范必 `400`。",
        ],
        "criterion_version": CRITERION_VERSION,
        "tool": TOOL,
        "operation": OPERATION,
        "design_code": DESIGN_CODE,
        "result": result,
        "verdict": PASSED if ok else FAILED,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"⇒ 判定：{'✅ ' + PASSED if ok else '❌ ' + FAILED}")
    print(f"wrote {EVIDENCE.relative_to(REPO)}")
    return 0 if ok else 1


def check_offline(repo: pathlib.Path) -> int:
    """`--check`：证据齐备 + 四条判据全真（**零请求**）。"""
    if not EVIDENCE.is_file():
        print(f"❌ 缺证据 {EVIDENCE.relative_to(REPO)}（先跑 --probe）")
        return 1
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    result = document.get("result") or {}
    problems: list[str] = []

    if document.get("verdict") != PASSED:
        problems.append(f"顶层 verdict 应为 PASSED，实际 {document.get('verdict')!r}")
    if str(document.get("design_code") or "") != DESIGN_CODE:
        problems.append(f"证据里的规范应为 `{DESIGN_CODE}`")
    if result.get("switched") is not True:
        problems.append(f"① 切换未生效（读回 {result.get('actual_code')!r}）⇒ 裸字符串归一化不成立")
    if int(result.get("table_status") or 0) != 200:
        problems.append(f"② `BD-TABLE` 状态 {result.get('table_status')} ≠ 200")
    if int(result.get("design_rows") or 0) <= 0:
        problems.append("② **没有**设计结果行 ⇒ 「设计真的产出」不成立（`200` 不算数）")
    if result.get("dco_skipped") is not True:
        problems.append("③ `DCO` **未**被显式跳过 ⇒ 字段集注入或跳过语义不成立")
    if result.get("operation_error"):
        problems.append(f"操作报了错：{result.get('operation_error')}")
    if result.get("backup_written") is not True:
        problems.append("备份未真的落盘 ⇒ 无退路（R144）")
    if result.get("has_project_path") is not True:
        problems.append("收尾时项目**无路径**（R144 事故条件）")

    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    print(
        f"✅ 离线自洽：**经 MCP** 的规范切换成立 —— `design_code` 裸字符串 "
        f"`{DESIGN_CODE}` ⇒ `DRC` 读回同值 · `BD-TABLE` {result.get('table_status')} · "
        f"**{result.get('design_rows')} 行**真实结果 · `DCO` 显式跳过 · 收尾有路径 ✅"
    )
    return 0


def main() -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="经 MCP 的设计规范切换证据")
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

    print(f"工具/操作：`{TOOL}` / `{OPERATION}` · 规范 `{DESIGN_CODE}`（裸字符串）")
    print(f"样本（**只读**）：{SAMPLE_SOURCE}")
    print(f"证据：{EVIDENCE.relative_to(REPO)}")
    if not args.probe:
        print("\n（预演；加 --probe 才真发）")
        return 0
    print()
    return run_probe(REPO, allow_crash=args.allow_native_crash_risk)


if __name__ == "__main__":
    raise SystemExit(main())
