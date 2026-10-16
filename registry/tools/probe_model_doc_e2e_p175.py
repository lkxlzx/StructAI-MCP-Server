#!/usr/bin/env python3
"""
P175 · 端到端：**模型 → JSON → 经 MCP 发到 MIDAS**（`docs/07` §16.1 **R168** 的核心判据）。

为什么要单独一个脚本
--------------------
`probe_model_doc_p175.py` 走的是**裸 HTTP**（直接 `POST /DOC/EXPORT`），它证明的是
**端点可用**。本脚本证明的是**另一件事**：这条链路能**经 MCP 契约**跑通 ——
即 `MCP Tool → OperationPlan → Adapter → MidasHttpClient → 原生`。
⚠️ 两者**不**可互相替代：端点可用 ≠ 在编排 / 护栏 / 权限 / Schema 之下可用。

链路（**双向**）
----------------
    MIDAS 模型  --DOC.EXPORT-->  DBG JSON  --压成 canonical-->  参数化模型
        ↑                                                          |
        |                                          （参数化改动 / 或原样）|
        +--DOC.IMPORT--  DBG JSON  <--展开回原生-- 参数化模型 <-------+

判据（**铁律 ⓪**：效果，不是状态码）
------------------------------------
1. `MODEL.EXPORT` 经 MCP ⇒ 目标文件**真的落盘** ∧ 可解析 ∧ `DBG` 非空；
2. `model_document` 往返**无损**（表集合相同 ∧ 字段逐条相同）；
3. **参数化改动真的生效**：在 canonical 上**改一个坐标**，回写、经 MCP 导入
   ⇒ 读回该节点**就是改后的值**（这是「参数化建模」的定义性判据）；
4. 收尾：实例停在**有路径**的项目上（R144）∧ 哨兵无残留。

用法
----
    python registry/tools/probe_model_doc_e2e_p175.py            # 预演（零请求）
    python registry/tools/probe_model_doc_e2e_p175.py --probe    # 真机（有副作用）
    python registry/tools/probe_model_doc_e2e_p175.py --check    # 离线自洽（零请求）
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Final

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]

CRITERION_VERSION: Final[int] = 1
PASSED: Final[str] = "PASSED"
FAILED: Final[str] = "FAILED"

EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "model_doc_e2e_probe.json"
WORKSPACE: Final[pathlib.Path] = REPO / ".tmp_p175"

SAMPLE_SOURCE: Final[pathlib.Path] = pathlib.Path(
    r"D:\Program\MIDAS\MIDAS GEN NX\Gen Verification\Eigen-01.mgbx"
)

BACKUP_NAME: Final[str] = "p175-e2e-session-backup.mgbx"
SAMPLE_NAME: Final[str] = "p175-e2e-sample.mgbx"
EXPORT_NAME: Final[str] = "p175-e2e-export.json"
EDITED_NAME: Final[str] = "p175-e2e-edited.json"

TOOL: Final[str] = "engineering_doc"
EXPORT_OPERATION: Final[str] = "MODEL.EXPORT"
IMPORT_OPERATION: Final[str] = "MODEL.IMPORT"

# 参数化改动的落点：把节点 1 的 X 从 0.0 改成这个值（样本里**不存在**的取值 ⇒ 防回显）
EDITED_NODE: Final[int] = 1
EDITED_X: Final[float] = 123.5

WATCH: Final[tuple[str, ...]] = ("NODE", "ELEM", "MATL", "SECT", "CONS", "EIGV", "NMAS")

ALLOWED_PATHS: Final[frozenset[str]] = frozenset(
    {"/DOC/EXPORT", "/DOC/IMPORT", "/DOC/SAVEAS", "/DOC/OPEN", "/DOC/CLOSE", "/DB/NODE"}
)


def _sibling(name: str) -> Any:
    """按路径装载同目录的模块（`registry/tools` 不是包）。"""
    import importlib.util  # noqa: PLC0415

    path = pathlib.Path(__file__).with_name(name)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def guard_paths() -> None:
    """发请求**之前**的自检（复用 `app/**` 的崩溃族常量）。"""
    sys.path.insert(0, str(REPO))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        NATIVE_CRASH_ENDPOINTS,
        guard_native_crash_path,
    )

    crash_paths = {"/" + str(item).replace(".", "/") for item in NATIVE_CRASH_ENDPOINTS}
    overlap = sorted(set(ALLOWED_PATHS) & crash_paths)
    if overlap:
        raise SystemExit(f"❌ 声明路径与崩溃族相交：{overlap} ⇒ **拒绝运行**")
    for path in ALLOWED_PATHS:
        guard_native_crash_path(path)
    print(f"闸门自检：声明路径 {len(ALLOWED_PATHS)} 条 ∩ 崩溃族（{len(crash_paths)} 条）= ∅")


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    """把嵌套结构摊平成 `路径 → 标量`（用于逐字段比对）。"""
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            out.update(_flatten(item, f"{prefix}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            out.update(_flatten(item, f"{prefix}[{index}]"))
    else:
        out[prefix] = value
    return out


def run_probe(repo: pathlib.Path) -> int:
    """真机端到端（**经 MCP 契约**）。"""
    guard_paths()
    import asyncio  # noqa: PLC0415

    # ⚠️ `_Stack` 从 `os.environ["MIDAS_BASE_URL"]` 读实例地址（`probe_interface_paths.py`
    #    的装配口径）⇒ 这里把仓库**外**的凭据注入**进程**环境（**不**入库、**不**打印值）。
    import os  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    from app.infrastructure.adapters.midas.model_document import (  # noqa: PLC0415
        canonical_to_native,
        native_to_canonical,
    )
    from app.infrastructure.adapters.midas.registry import MidasRegistry  # noqa: PLC0415

    base_url, mapi_key = _load_credentials()
    os.environ.setdefault("MIDAS_BASE_URL", base_url)
    os.environ.setdefault("MIDAS_MAPI_KEY", mapi_key)

    stack_module = _sibling("probe_interface_paths.py")
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    exported = (WORKSPACE / EXPORT_NAME).resolve()
    edited = (WORKSPACE / EDITED_NAME).resolve()
    sample = (WORKSPACE / SAMPLE_NAME).resolve()
    backup = (WORKSPACE / BACKUP_NAME).resolve()
    registry = MidasRegistry.load(repo / "registry")

    if not SAMPLE_SOURCE.is_file():
        print(f"🛑 样本不存在：{SAMPLE_SOURCE}")
        return 1

    async def run() -> int:
        # ⚠️ **P175 实测**：Windows 上 `TemporaryDirectory.__exit__` 会在 sqlite 文件仍被
        # 占用时抛 `PermissionError`（引擎尚未完全释放）⇒ 它**掩盖主流程结果**（异常栈把
        # 判定输出挤掉）。⇒ 显式 `ignore_cleanup_errors=True`，让清理失败**不**影响判定。
        with tempfile.TemporaryDirectory(
            prefix="p175-e2e-", ignore_cleanup_errors=True
        ) as raw_dir:
            async with stack_module._Stack(  # noqa: SLF001 - 复用既有装配
                repo, pathlib.Path(raw_dir), allow_unverified=False
            ) as stack:
                base, key = base_url, mapi_key

                # ---- 第 0 步（R144）：备份现场（顺带确立项目路径）----
                backup.unlink(missing_ok=True)
                saved = await stack.call(
                    TOOL, "SAVE_AS", {"project_path": str(backup)}, confirm=True
                )
                print(f"  SAVE_AS 返回：{json.dumps(saved.get('errors'), ensure_ascii=False)}")
                if not backup.is_file():
                    print("🛑 备份未落盘 ⇒ **不**继续（拒绝在无退路的实例上做写操作）")
                    return 1
                print(f"  备份现场 → {backup.name}（{backup.stat().st_size} 字节）")

                # ---- 打开样本副本 ----
                shutil.copy2(SAMPLE_SOURCE, sample)
                await stack.call(TOOL, "OPEN", {"project_path": str(sample)}, confirm=True)
                print(f"  打开样本副本 → {sample.name}")

                # ---- ① MODEL.EXPORT（经 MCP）----
                exported.unlink(missing_ok=True)
                logged_before = len(stack.log)
                exported_result = await stack.call(
                    TOOL, EXPORT_OPERATION, {"project_path": str(exported)}, confirm=True
                )
                written = exported.is_file() and exported.stat().st_size > 0
                sent = stack.log[logged_before:]
                print(f"  ① {EXPORT_OPERATION} → 落盘={written} · 请求 {len(sent)} 条")
                if not written:
                    errors = json.dumps(exported_result.get("errors"), ensure_ascii=False)
                    execution = json.dumps(exported_result.get("execution"), ensure_ascii=False)
                    print(f"     核心返回：{errors}")
                    print(f"     执行状态：{execution[:300]}")
                    print("🛑 导出未落盘 ⇒ 判据不成立")
                    return 1

                source = json.loads(exported.read_text(encoding="utf-8"))
                document = native_to_canonical(source, registry)
                print(
                    f"     `DBG` 表 {len(document.table_names())} 张 · "
                    f"canonical 实体 {len(document.entities)} 张"
                )

                # ---- ② 往返无损 ----
                roundtrip = canonical_to_native(document, registry)
                flat_a, flat_b = _flatten(source["DBG"]), _flatten(roundtrip["DBG"])
                keys = sorted(set(flat_a) | set(flat_b))
                differing = [k for k in keys if flat_a.get(k, "<A>") != flat_b.get(k, "<A>")]
                lossless = not differing and set(source["DBG"]) == set(roundtrip["DBG"])
                print(
                    f"  ② 往返：表 {len(source['DBG'])} → {len(roundtrip['DBG'])} · "
                    f"字段差异 {len(differing)}"
                )
                if not lossless:
                    print(f"     ⚠️ 前 5 处：{differing[:5]}")
                    return 1

                # ---- ③ 参数化改动真的生效 ----
                node_rows = document.entities.get("NODE", ())
                if not node_rows:
                    print("🛑 canonical 里没有节点 ⇒ 判据不成立")
                    return 1
                before_x = dict(node_rows[0]).get("x")
                edited_rows = tuple(
                    {**dict(row), "x": EDITED_X} if row.get("id") == EDITED_NODE else dict(row)
                    for row in node_rows
                )
                edited_document = type(document)(
                    entities={**dict(document.entities), "NODE": edited_rows},
                    native=document.native,
                    units=document.units,
                )
                native_edited = canonical_to_native(edited_document, registry)
                edited.write_text(json.dumps(native_edited, ensure_ascii=False), encoding="utf-8")
                print(f"  ③ 参数化改动：节点 {EDITED_NODE} 的 X {before_x} → {EDITED_X}")

                await stack.call(
                    TOOL, IMPORT_OPERATION, {"project_path": str(edited)}, confirm=True
                )
                # ⚠️ 读回**具体取值**（比行数强：证明改动真的进去，而不只是多了一行）
                import httpx  # noqa: PLC0415

                async with httpx.AsyncClient(
                    base_url=base, headers={"MAPI-Key": key}, timeout=60.0
                ) as client:
                    body = (await client.get("/db/NODE")).json()
                nodes = body.get("NODE") or {}
                actual = (nodes.get(str(EDITED_NODE)) or {}).get("X")
                applied = actual == EDITED_X
                print(f"     读回节点 {EDITED_NODE} 的 X = {actual!r} ⇒ 生效={applied}")
                if not applied:
                    print("🛑 参数化改动**没有**生效 ⇒ 判据不成立")
                    return 1

                # ---- 收尾（R144）：还原现场 ----
                await stack.call(TOOL, "OPEN", {"project_path": str(backup)}, confirm=True)
                async with httpx.AsyncClient(
                    base_url=base, headers={"MAPI-Key": key}, timeout=60.0
                ) as client:
                    pjcf_body = (await client.get("/db/PJCF")).json()
                pjcf = (pjcf_body.get("PJCF") or {}).get("1") or {}
                restored = str(pjcf.get("FILE_NAME") or "") not in {"", "无标题"}
                print(f"  收尾：FILE_NAME={pjcf.get('FILE_NAME')!r}（有路径 ✅）")
                if not restored:
                    print("🛑 收尾时项目**无路径**（R144 事故条件）⇒ 拒绝收尾")
                    return 1

                evidence = {
                    "note": [
                        "P175 · **模型 → JSON → 经 MCP 发到 MIDAS** 的端到端判据"
                        "（`docs/07` §16.1 **R168**）。",
                        "⚠️ 与 `model_doc_probe.json` **不可互替**："
                        "那个证明**端点可用**（裸 HTTP），",
                        "   本证据证明**经 MCP 契约**可用"
                        "（Tool → OperationPlan → Adapter → 原生）。",
                        "**判据（铁律 ⓪：效果，不是状态码）**："
                        "① 导出**真的落盘**；② `model_document` 往返**无损**；",
                        "   ③ **参数化改动真的生效**（改一个坐标，导入后**按改后的值读回**）"
                        " —— 这是「参数化建模」的定义性判据；④ 收尾项目**有路径**（R144）。",
                        f"⚠️ 改动取值 `{EDITED_X}` **不在**样本里"
                        f"（`{before_x}` 是原值）⇒ 读回它 = **防回显**（R157）。",
                        "**副作用受控**：只碰 `.tmp_p175/` 内的样本**副本**；样本原目录**只读**。",
                    ],
                    "criterion_version": CRITERION_VERSION,
                    "tool": TOOL,
                    "operations": {"export": EXPORT_OPERATION, "import": IMPORT_OPERATION},
                    "export": {
                        "file_written": bool(written),
                        "file_size": exported.stat().st_size,
                        "table_count": len(document.table_names()),
                        "canonical_tables": len(document.entities),
                    },
                    "roundtrip": {
                        "tables_in": len(source["DBG"]),
                        "tables_out": len(roundtrip["DBG"]),
                        "field_differences": len(differing),
                        "lossless": lossless,
                    },
                    "parametric_edit": {
                        "table": "NODE",
                        "node_id": EDITED_NODE,
                        "before": before_x,
                        "written": EDITED_X,
                        "read_back": actual,
                        "applied": applied,
                    },
                    "session": {
                        "backup": backup.name,
                        "restored_file_name": pjcf.get("FILE_NAME"),
                        "has_project_path": restored,
                    },
                    "sample": {
                        "source": str(SAMPLE_SOURCE),
                        "source_untouched": SAMPLE_SOURCE.is_file(),
                    },
                    "verdict": PASSED,
                }
                EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
                EVIDENCE.write_text(
                    json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8"
                )
                print(f"⇒ 判定：✅ {PASSED}")
                print(f"wrote {EVIDENCE.relative_to(REPO)}")
                return 0

    return asyncio.run(run())


def check_offline(repo: pathlib.Path) -> int:
    """`--check`：证据齐备 + 判据全真（**零请求**）。"""
    if not EVIDENCE.is_file():
        print(f"❌ 缺证据 {EVIDENCE.relative_to(REPO)}（先跑 --probe）")
        return 1
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    problems: list[str] = []

    if document.get("verdict") != PASSED:
        problems.append(f"顶层 verdict 应为 PASSED，实际 {document.get('verdict')!r}")
    export = document.get("export") or {}
    if export.get("file_written") is not True or int(export.get("file_size") or 0) <= 0:
        problems.append("导出未落盘 / 大小为 0 ⇒ 「效果」不成立")
    if int(export.get("table_count") or 0) <= 0:
        problems.append("导出的 `DBG` 为空 ⇒ 口径不成立")
    trip = document.get("roundtrip") or {}
    if trip.get("lossless") is not True:
        problems.append(f"往返**有损**（字段差异 {trip.get('field_differences')}）⇒ 转换层不成立")
    if int(trip.get("tables_in") or 0) != int(trip.get("tables_out") or -1):
        problems.append("往返前后**表数不同** ⇒ 有表被丢弃")
    edit = document.get("parametric_edit") or {}
    if edit.get("applied") is not True:
        problems.append("参数化改动**没有**生效 ⇒ 「参数化建模」判据不成立")
    if edit.get("read_back") != edit.get("written"):
        problems.append(
            f"读回值 {edit.get('read_back')!r} ≠ 写入值 {edit.get('written')!r} ⇒ 不可信"
        )
    if edit.get("written") == edit.get("before"):
        problems.append("改动值与原值相同 ⇒ **测不出**任何东西（无效对照）")
    session = document.get("session") or {}
    if session.get("has_project_path") is not True:
        problems.append("收尾时项目**无路径**（R144 事故条件）⇒ 收口不成立")
    if document.get("sample", {}).get("source_untouched") is not True:
        problems.append("样本原文件不可达 ⇒ 前提不成立")

    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    print(
        f"✅ 端到端自洽：经 MCP 的 `{EXPORT_OPERATION}` 落盘 {export.get('file_size')} 字节 · "
        f"`DBG` {export.get('table_count')} 张表 · 往返无损（{trip.get('tables_in')} 表 / "
        f"{trip.get('field_differences')} 差异）· **参数化改动真的生效**"
        f"（NODE {edit.get('node_id')} 的 X {edit.get('before')} → {edit.get('written')}，"
        f"读回 {edit.get('read_back')}）· 收尾有路径 ✅"
    )
    return 0


def main() -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="模型 → JSON → 经 MCP 发到 MIDAS 的端到端判据")
    parser.add_argument("--probe", action="store_true", help="真发请求（默认只预演）")
    parser.add_argument("--check", action="store_true", help="离线自洽断言（零请求）")
    args = parser.parse_args()
    if args.check:
        return check_offline(REPO)

    guard_paths()
    print(
        f"链路：模型 --{EXPORT_OPERATION}--> DBG JSON --canonical--> "
        f"参数化模型 --{IMPORT_OPERATION}--> 模型"
    )
    print(f"工具：{TOOL} · 样本（**只读**）：{SAMPLE_SOURCE}")
    print(f"证据：{EVIDENCE.relative_to(REPO)}")
    if not args.probe:
        print("\n（预演；加 --probe 才真发）")
        return 0
    print()
    return run_probe(REPO)


if __name__ == "__main__":
    raise SystemExit(main())
