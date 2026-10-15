#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P168 / **R161** 的效果判据（**铁律 ⓪**）：`spec_guard` 的**枚举收口**到底有没有用。

本批的两处数据侧收口
--------------------
| 收口 | 生成器 | 内容 |
| --- | --- | --- |
| **① `VIEW.RESULTGRAPHIC` 的 `CURRENT_MODE`**（**缺枚举**，**R155** 留缺） | `sync_result_graphic_modes.py` | 补 **36** 个取值（手册 **34** 篇变体文章 / **56** 条示例的并集） |
| **② 6 个变体端点的 `TABLE_TYPE`**（**来源太窄**，**R151** 的同类） | `sync_table_type_variant_enum.py` | 把**登记表的 token** 追加进枚举（`FIBR_*` ×5 + `REACTIONLSURFACESPRING`） |

⚠️ **为什么这两处**必须**在「恢复 `spec_guard` 可见性」（**R161** 的核心 1 行：
`adapter._build` 由 `schema_json()` 改用 `effective_schema()`）**之后**才谈效果**：
普查发现 **104 / 225** 个带枚举的 Schema 文件的**根键是包装键** ⇒ `spec_guard` 的
`schema["properties"][包装键]` 下钻约定**取不到** ⇒ 这些端点**一个字段都不检查**
（**盲区**）。可见性一恢复，这些枚举**立刻生效** ⇒ 若枚举**缺**合法取值，就**会**把合法调用拦死
（**R151 的镜像事故**）。⇒ 两处收口是**可见性修复的前置条件**。

判据（**铁律 ⓪**：效果，**不是**状态码）
--------------------------------------
| 相 | 判据 |
| --- | --- |
| **变体 `TABLE_TYPE`（原生）** | 登记 token ⇒ 原生**收到并处理**（`2xx` 或**业务级** `4xx`，**不**是崩溃 / **不**是未知 token 的拒绝） |
| **变体 `TABLE_TYPE`（核心闸门）** | 登记 token ⇒ **不抛**（放行）；伪 token ⇒ `STRUCTAI-1200 value_not_in_spec_enum`（**零请求**） |
| **变体枚举**真的被查**（端到端）** | `RESULT.NODE.DISPLACEMENT`（**不**传 `table_type` ⇒ 用端点**自己的** `table_type`）经 MCP Tool 契约 ⇒ `success` ∧ 规范化结果有**真数据行** ∧ 原生 `200`（**可见性修复后**这条路径**真的**走了变体文件的枚举） |
| **`CURRENT_MODE`（核心阳性）** | 合法取值经 `engineering_view` / `VIEW.DISPLACEMENT` ⇒ 请求**真的发出去**（原生 `POST /VIEW/RESULTGRAPHIC` `200`） |
| **`CURRENT_MODE`（核心阴性）** | 非法取值（`"displacement"`，**不在** 36 个变体里）⇒ `STRUCTAI-1200` ∧ **零请求**（**R140** 的保护**首次**覆盖本端点） |
| **`CURRENT_MODE`（原生真效果）** | 图形关 / 开 `DisplacementContour` / 换 `DeformedShape` 三张截图 ⇒ **字节两两不同**（画面**真的**变） |
| **零残留** | 跑前 / 跑后 **6** 个模型哨兵**逐项一致**（取报表 + 视图类操作**不**写模型） |

⚠️ **只**发 `POST /POST/TABLE`（取报表，**不**落文件）、`POST /VIEW/RESULTGRAPHIC` 与
`POST /VIEW/CAPTURE`（截图落 `.tmp_p164c/`，**在 `.gitignore` 内**）+ 只读 `GET`
（健康检查 / 哨兵）；**绝不**碰 `DESIGN.{RC,SRC}` 的 `*-ANAL`（**R154** 的崩溃族，见自检）。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import pathlib
import sys
from typing import Any, Final

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
"""仓库根目录（`registry/tools/` 的上两级）。"""

EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "spec_enum_probe.json"
"""证据落点（**不含**凭据、**不含**响应原文；只留结构形态、状态码与字节数 / 哈希）。"""

AUDIT: Final[pathlib.Path] = REPO / "registry" / "live" / "spec_enum_audit.json"
"""**R161** 的普查证据（盲区 / 误伤 / 台账；本探针引用它的计数）。"""

SHOTS: Final[pathlib.Path] = REPO / ".tmp_p164c" / "p168_view"
"""截图落点（**在 `.gitignore` 内**；证据里只留字节数与 sha256）。"""

DEFAULT_PROJECT: Final[str] = ".tmp_p164c/p164c-concrete.mgbx"
"""自建项目（**只碰它**；`--project` 可覆盖）。它**已有分析结果**（判据的前提）。"""

ADAPTER_RELATIVE: Final[str] = "app/infrastructure/adapters/midas/adapter.py"
"""**生产路径的绑定**：`_build` 里 `spec_guard` 的**唯一**调用点（本探针用 AST 断言）。"""

VARIANT_ENDPOINTS: Final[tuple[str, ...]] = (
    "POST.TABLE.FIBR_ELASTREMAIN",
    "POST.TABLE.FIBR_EVENTSTEP",
    "POST.TABLE.FIBR_MAXCONTRACT",
    "POST.TABLE.FIBR_MEANCOMPCONTRACT",
    "POST.TABLE.FIBR_YILEDSTRENGTH",
    "POST.TABLE.REACTIONLSURFACESPRING",
)
"""**来源太窄**的 6 个变体端点（收口对象；登记 token 原先**不在**自己的枚举里）。"""

FAKE_TOKEN: Final[str] = "NOT_A_REAL_TABLE_XYZ"
"""阴性对照用的**伪** token（登记表 / 枚举里都没有 ⇒ 必须被拦在**发请求之前**）。"""

MODE_A: Final[str] = "DisplacementContour"
MODE_B: Final[str] = "DeformedShape"
"""两个**表内**取值（都在 `registry/live/view_result_modes.json` 的 36 个里）。"""

ILLEGAL_MODE: Final[str] = "displacement"
"""**非法**取值（**R150 / R155** 实测被原生 `400` 拒的那个）—— 收口后必须**零请求**被拦。"""

LOAD_CASE: Final[str] = "DL"

SENTINEL: Final[tuple[str, ...]] = (
    "/DB/NODE",
    "/DB/ELEM",
    "/DB/MATL",
    "/DB/SECT",
    "/DB/STLD",
    "/DB/CNLD",
)
"""零残留哨兵（**6** 项）。"""

HEALTH_PATH: Final[str] = "/DB/NODE"

ALLOWED_PATHS: Final[tuple[str, ...]] = (
    "/POST/TABLE",
    "/VIEW/RESULTGRAPHIC",
    "/VIEW/CAPTURE",
    "/DOC/OPEN",
)
"""本探针**允许**出现的**写**方法路径（`POST`）—— 其余一律只读 `GET`。

⚠️ `--probe` 前会**显式自检**：这些路径 ∩ `NATIVE_CRASH_ENDPOINTS`（**R154** 的崩溃族，
`DESIGN.{RC,SRC}` 的 `*-ANAL`）= **∅**，且逐个过一遍 `guard_native_crash_path()`
（真在崩族里 ⇒ 那里就会抛，**零请求**）。
"""

TOOL_RESULT: Final[str] = "engineering_result"
TOOL_VIEW: Final[str] = "engineering_view"
OP_DISPLACEMENT: Final[str] = "RESULT.NODE.DISPLACEMENT"
OP_SUMMARY: Final[str] = "RESULT.ANALYSIS.SUMMARY"
OP_VIEW_MODEL: Final[str] = "VIEW.MODEL"
OP_VIEW_DISPLACEMENT: Final[str] = "VIEW.DISPLACEMENT"

PRODUCT_KEY: Final[str] = "GEN_NX"
CRITERION_VERSION: Final[int] = 1
PROBED_AT: Final[str] = "2026-10-15"
INSTANCE_ALIAS: Final[str] = "gen-local"
INSTANCE_PRODUCT: Final[str] = "GEN NX"

PASSED: Final[str] = "PASSED"
FAILED: Final[str] = "FAILED"


def _sibling(name: str) -> Any:
    """按路径装载同目录的模块（`registry/tools` 不是包）—— **不**复制它的逻辑。"""
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


def graphic_block(mode: str) -> dict[str, Any]:
    """**打开**结果图形的请求体（`TYPE_OF_DISPLAY.<子块>.OPT_CHECK = true` 是**关键**，R159）。"""
    return {
        "CURRENT_MODE": mode,
        "LOAD_CASE_COMB": {"TYPE": "ST", "NAME": LOAD_CASE},
        "TYPE_OF_DISPLAY": {
            "CONTOUR": {"OPT_CHECK": True, "NUM_OF_COLOR": 6, "COLOR_TYPE": "rgb"},
            "DEFORM": {"OPT_CHECK": True},
            "VALUES": {"OPT_CHECK": True},
            "LEGEND": {"OPT_CHECK": True},
        },
    }


def graphic_off_block(mode: str) -> dict[str, Any]:
    """**关掉**结果图形的请求体（同形状、所有 `OPT_CHECK = false`）—— 基线的定义（R159 先例）。"""
    body = graphic_block(mode)
    body["TYPE_OF_DISPLAY"] = {key: {"OPT_CHECK": False} for key in body["TYPE_OF_DISPLAY"]}
    return body


def guard_paths() -> None:
    """发请求**之前**的自检（`app/**` 的崩溃族 + 本探针声明的路径）。"""
    sys.path.insert(0, str(REPO))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        NATIVE_CRASH_ENDPOINTS,
        guard_native_crash_path,
    )

    crash_paths = {"/" + str(item).replace(".", "/") for item in NATIVE_CRASH_ENDPOINTS}
    overlap = sorted(set(ALLOWED_PATHS) & crash_paths)
    if overlap:
        raise SystemExit(f"❌ 本探针声明的路径与崩溃族相交：{overlap} ⇒ **拒绝运行**")
    for path in ALLOWED_PATHS:
        guard_native_crash_path(path)  # 真在崩族里 ⇒ 这里就会抛（**零请求**）
    print(f"闸门自检：声明路径 {list(ALLOWED_PATHS)} ∩ 崩溃族（{len(crash_paths)} 条）= ∅")


# ===== 离线事实（**可复算**）=====


def adapter_binding(repo: pathlib.Path) -> dict[str, Any]:
    """**AST** 断言：`MidasAdapter._build` 里的 `spec_guard` 用的是 `effective_schema()`。

    ⚠️ 这是「闸门行为 ↔ 生产路径」的**唯一**绑定：`_build` 是 `spec_guard` 在 `app/**` 里的
    **唯一**调用点（`grep` 可复核）。断言「**收口后的口径**」= `registry.effective_schema(...)`。
    """
    tree = ast.parse((repo / ADAPTER_RELATIVE).read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "guard_spec_values"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if (
            isinstance(first, ast.Call)
            and isinstance(first.func, ast.Attribute)
            and isinstance(first.func.value, ast.Name)
        ):
            found.append(f"{first.func.value.id}.{first.func.attr}")
    return {
        "file": ADAPTER_RELATIVE,
        "guard_calls": len(found),
        "first_argument": found[0] if found else "",
        "uses_effective_schema": bool(found) and all(item.endswith("effective_schema") for item in found),
    }


def closure_facts(repo: pathlib.Path) -> dict[str, Any]:
    """两处收口的**离线复算**（生成器 / 普查证据的计数）。"""
    modes = _sibling("sync_result_graphic_modes.py")
    variants = _sibling("sync_table_type_variant_enum.py")
    audit = json.loads(AUDIT.read_text(encoding="utf-8")) if AUDIT.is_file() else {}
    visibility = ((audit.get("guard") or {}).get("visibility") or {}) if audit else {}
    return {
        "current_mode": {
            "generator": "registry/tools/sync_result_graphic_modes.py",
            "values": len(modes.expected_enum(repo)),
            "manual": len(modes.manual_modes(repo)),
            "evidence": len(modes.evidence_modes(repo)),
            "agrees_with_evidence": set(modes.manual_modes(repo)) == set(modes.evidence_modes(repo)),
            "applied": modes.is_applied(repo),
            "illegal_absent": ILLEGAL_MODE not in set(modes.expected_enum(repo)),
            "mode_a_present": MODE_A in set(modes.expected_enum(repo)),
            "mode_b_present": MODE_B in set(modes.expected_enum(repo)),
        },
        "variant_table_type": {
            "generator": "registry/tools/sync_table_type_variant_enum.py",
            "endpoints": list(VARIANT_ENDPOINTS),
            "applied": variants.is_applied(repo),
            "enums": {key: variants.expected_enum(repo, key) for key in VARIANT_ENDPOINTS},
        },
        "guard_visibility": {
            "files_with_constraints": visibility.get("files_with_constraints"),
            "drillable_with_schema_json": visibility.get("drillable_with_schema_json"),
            "drillable_with_effective_schema": visibility.get("drillable_with_effective_schema"),
            "blind_with_schema_json": visibility.get("blind_with_schema_json"),
            "blind_with_effective_schema": visibility.get("blind_with_effective_schema"),
        },
        "adapter_binding": adapter_binding(repo),
    }


def registered_token(repo: pathlib.Path, key: str) -> str:
    """端点在**登记表**里声明的 `table_type`（**不**猜；取不到 ⇒ 报错）。"""
    document = json.loads((repo / "registry" / "manifest.json").read_text(encoding="utf-8"))
    for entry in document["endpoints"]:
        if str(entry.get("key") or "") == key:
            token = str(entry.get("table_type") or "")
            if not token:
                raise SystemExit(f"❌ {key} 在登记表里没有 `table_type` ⇒ 本探针用错了端点")
            return token
    raise SystemExit(f"❌ 登记表里没有端点 {key!r}")


def guard_behaviour(repo: pathlib.Path, key: str, token: str) -> dict[str, Any]:
    """**核心闸门**行为（与 `adapter._build` **逐字同一**调用）：放行 / 拦（含归因）。"""
    sys.path.insert(0, str(repo))
    from app.infrastructure.adapters.midas.errors import MidasValidationError  # noqa: PLC0415
    from app.infrastructure.adapters.midas.registry import MidasRegistry  # noqa: PLC0415
    from app.infrastructure.adapters.midas.spec_guard import guard_spec_values  # noqa: PLC0415

    registry = MidasRegistry.load(repo / "registry")
    schema = registry.effective_schema(key)
    try:
        guard_spec_values(
            schema, {"Argument": {"TABLE_TYPE": token}}, endpoint=key, wrapper="Argument"
        )
    except MidasValidationError as error:
        return {
            "token": token,
            "raised": True,
            "code": "STRUCTAI-1200",
            "native_reason": str((error.details or {}).get("reason") or ""),
            "problems": [str(item) for item in (error.details or {}).get("problems") or []][:2],
        }
    return {"token": token, "raised": False, "code": "", "native_reason": "", "problems": []}


# ===== 真机 =====


AUTH_ERROR_MARKERS: Final[tuple[str, ...]] = (
    "MAPI Key is invalid",
    "invalid key",
    "MAPI-Key",
)
"""原生**鉴权失败**的文案标记。

⚠️ **实测教训（本批首跑）**：一次 `POST /POST/TABLE` 回 `400 {"error": {"message": "MAPI Key is invalid."}}`
—— 那是**实例侧的瞬时状态**（**不**是枚举结论）。若不识别，证据里会混进一条**看似业务级**的 `400`
⇒ 判据会被**误判**为「原生拒绝」。⇒ 出现鉴权失败 ⇒ **中止**，**不**写证据。
"""


def _is_auth_error(text: str) -> bool:
    """原生答复是否是**鉴权失败**（见 `AUTH_ERROR_MARKERS`）。"""
    return any(marker.lower() in text.lower() for marker in AUTH_ERROR_MARKERS)


def native_table(base: str, key: str, endpoint: str, token: str, *, attempts: int = 3) -> dict[str, Any]:
    """原生口径：`POST /POST/TABLE {TABLE_TYPE: <token>}`（**取报表，不落文件、不写模型**）。

    ⚠️ **重试（实测驱动）**：本机 `gen-local` 偶发把**合法**请求回成
    `400 {"error": {"message": "MAPI Key is invalid."}}`（同一 Key 的只读 `GET` 同时正常）
    —— 那是**实例侧的瞬时状态**（`docs/07` §15.4 已登记「云端中继**间歇性掉线**」同类）。
    ⇒ 遇鉴权失败**重试**（最多 `attempts` 次）；仍失败由调用方**中止**（**不**写证据）。
    """
    import time  # noqa: PLC0415

    import httpx  # noqa: PLC0415

    row: dict[str, Any] = {"endpoint": endpoint, "token": token, "attempts": 0}
    for attempt in range(1, attempts + 1):
        with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=180.0) as client:
            response = client.post("/POST/TABLE", json={"Argument": {"TABLE_TYPE": token}})
        row = {
            "endpoint": endpoint,
            "token": token,
            "attempts": attempt,
            "status": int(response.status_code),
            "envelope_key": "",
            "head_columns": 0,
            "data_rows": 0,
            "native_error": "",
            "auth_error": _is_auth_error(response.text),
        }
        if not row["auth_error"]:
            break
        time.sleep(2.0)
    try:
        payload = response.json()
    except ValueError:
        row["native_error"] = response.text[:120]
        return row
    if isinstance(payload, dict) and payload:
        envelope = next(iter(payload))
        row["envelope_key"] = str(envelope)
        block = payload[envelope]
        if isinstance(block, dict):
            head = block.get("HEAD")
            data = block.get("DATA")
            row["head_columns"] = len(head) if isinstance(head, list) else 0
            row["data_rows"] = len(data) if isinstance(data, list) else 0
        if int(response.status_code) >= 400 or not block:
            row["native_error"] = json.dumps(payload, ensure_ascii=False)[:160]
    return row


def sentinels(base: str, key: str) -> dict[str, Any]:
    """只读哨兵（**6** 项；`GET` 每个端点 → 状态码 + 既有编号数）。"""
    import httpx  # noqa: PLC0415

    snapshot: dict[str, Any] = {}
    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=60.0) as client:
        for path in SENTINEL:
            response = client.get(path)
            count: int | None = None
            try:
                payload = response.json()
                root = next(iter(payload))
                block = payload[root]
                count = len(block) if isinstance(block, (dict, list)) else 0
            except Exception:  # noqa: BLE001 - 读不回如实留 None
                count = None
            snapshot[path] = {"status": int(response.status_code), "count": count}
    return snapshot


def _error_of(response: Any) -> dict[str, Any]:
    """统一信封里的错误块（**只**留判定字段）。"""
    error = (response or {}).get("error") or {}
    return {
        "code": str(error.get("code") or ""),
        "native_reason": str((error.get("details") or {}).get("reason") or error.get("reason") or ""),
        "native_stage": str((error.get("details") or {}).get("stage") or error.get("stage") or ""),
        "native_endpoint": str(
            (error.get("details") or {}).get("endpoint") or error.get("endpoint") or ""
        ),
    }


def core_rows(repo: pathlib.Path, workdir: pathlib.Path) -> dict[str, Any]:
    """核心口径的**四条**调用（**生产路径**，`allow_unverified=False`）：

    1. `RESULT.NODE.DISPLACEMENT`（**不**传 `table_type`）⇒ 用端点自己的 token
       ⇒ **可见性修复后**这条路径真的走了变体文件的枚举；
    2. `RESULT.ANALYSIS.SUMMARY` + **伪** token ⇒ 必须**零请求**被拦（R140 的保护）；
    3. `VIEW.MODEL` + 截图（post 模式）⇒ **基线**；
    4. `VIEW.DISPLACEMENT` + `CURRENT_MODE = DisplacementContour` ⇒ 打开图形（**真效果**）；
    5. `VIEW.DISPLACEMENT` + `CURRENT_MODE = DeformedShape` ⇒ **换取值真的换画面**；
    6. `VIEW.DISPLACEMENT` + `CURRENT_MODE = "displacement"`（**非法**）⇒ **零请求**被拦。
    """
    import asyncio  # noqa: PLC0415

    stack_module = _sibling("probe_interface_paths.py")
    SHOTS.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {}

    async def run() -> None:
        async with stack_module._Stack(  # noqa: SLF001 - 复用既有装配（**不**复制）
            repo, workdir, read_mode=True, allow_unverified=False
        ) as stack:

            async def once(
                tag: str, tool: str, operation: str, parameters: dict[str, Any]
            ) -> dict[str, Any]:
                stack.log.clear()
                outcome = await stack.run_operation(tool, operation, parameters)
                requests = list(stack.log)
                # ⚠️ 归因**复用** `probe_interface_paths._error_of`（**不**另写一套）：它会把
                # ASYNC 任务的 `error_json` 里的 `native_reason` / `native_stage` 一并提出来
                # （`spec_guard` 在**发请求之前**抛 ⇒ 响应只报 `task_not_completed`，
                # **真正的归因**在 `details` 里）。
                error = stack_module._error_of(outcome["response"])  # noqa: SLF001
                return {
                    "tag": tag,
                    "operation": operation,
                    "success": bool(outcome["response"].get("success")),
                    "error": error,
                    "task": dict(outcome.get("task") or {}),
                    "readback": stack_module._readback_of(  # noqa: SLF001 - 复用既有口径
                        "result", outcome.get("data")
                    ),
                    "requests": [
                        {
                            "method": item.get("method"),
                            "path": item.get("path"),
                            "status": item.get("status"),
                            "body_keys": sorted((item.get("body") or {}).keys())
                            if isinstance(item.get("body"), dict)
                            else [],
                            "current_mode": (
                                ((item.get("body") or {}).get("Argument") or {}).get("CURRENT_MODE")
                                if isinstance((item.get("body") or {}).get("Argument"), dict)
                                else None
                            ),
                            "table_type": (
                                ((item.get("body") or {}).get("Argument") or {}).get("TABLE_TYPE")
                                if isinstance((item.get("body") or {}).get("Argument"), dict)
                                else None
                            ),
                        }
                        for item in requests
                    ],
                }

            def shot(name: str) -> pathlib.Path:
                return SHOTS / f"{name}.jpg"

            # ① 变体枚举**真的被查**（不传 table_type ⇒ 端点自己的 token）
            result["variant_result"] = await once(
                "RESULT.NODE.DISPLACEMENT", TOOL_RESULT, OP_DISPLACEMENT, {}
            )
            # ② 伪 token ⇒ 零请求被拦
            result["fake_token"] = await once(
                "RESULT.ANALYSIS.SUMMARY 伪 token",
                TOOL_RESULT,
                OP_SUMMARY,
                {"table_type": FAKE_TOKEN},
            )
            # ③④⑤⑥ 视图：基线（图形关） / 两个合法取值 / 一个非法取值
            for tag, mode, body, name in (
                ("基线（图形全关）", MODE_A, graphic_off_block(MODE_A), "base"),
                ("打开 DisplacementContour", MODE_A, graphic_block(MODE_A), "mode_a"),
                ("换 DeformedShape", MODE_B, graphic_block(MODE_B), "mode_b"),
            ):
                target = shot(name)
                if target.exists():
                    target.unlink()
                row = await once(
                    tag,
                    TOOL_VIEW,
                    OP_VIEW_DISPLACEMENT,
                    {
                        "result_graphic": body,
                        "capture": {"set_mode": "post", "export_path": str(target)},
                    },
                )
                row["shot"] = {
                    "name": name,
                    "exists": target.exists(),
                    "bytes": target.stat().st_size if target.exists() else 0,
                    "sha256": _sha(target) if target.exists() else "",
                }
                result["views"][tag] = row
            result["illegal_mode"] = await once(
                "非法 CURRENT_MODE",
                TOOL_VIEW,
                OP_VIEW_DISPLACEMENT,
                {
                    "result_graphic": graphic_block(ILLEGAL_MODE),
                    "capture": {"set_mode": "post", "export_path": str(shot("illegal"))},
                },
            )

    result["views"] = {}
    asyncio.run(run())
    return result


def run_probe(repo: pathlib.Path, project: str) -> int:
    """真机受控测量（`--probe`）：原生 + 核心闸门 + 端到端 + 截图效果 + 哨兵。"""
    guard_paths()
    base, key = _load_credentials()
    project_path = (repo / project).resolve()

    import httpx  # noqa: PLC0415

    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=60.0) as client:
        health = int(client.get(HEALTH_PATH).status_code)
        opened = False
        if health != 200:
            if not project_path.exists():
                print(f"🛑 项目不存在：{project_path}")
                return 1
            response = client.post("/DOC/OPEN", json={"Argument": str(project_path)})
            opened = response.status_code == 200
            print(f"POST /DOC/OPEN → {response.status_code}（自建项目）")
            health = int(client.get(HEALTH_PATH).status_code)
    print(f"实例 {base} · 项目 {project} · 健康检查 {HEALTH_PATH} → {health}")
    if health != 200:
        print("🛑 实例不可达 / 项目未打开 ⇒ 一个业务请求都不发")
        return 1

    before = sentinels(base, key)
    print(f"跑前哨兵：{ {k: v['count'] for k, v in before.items()} }")
    if all(not value["count"] for value in before.values()):
        print("🛑 项目**为空** ⇒ 判据不适用（取报表需要分析结果）")
        return 1

    # ---- ① 变体 TABLE_TYPE：原生 + 核心闸门 ----
    print("\n① 变体 TABLE_TYPE（登记 token ⇒ 原生收到 / 核心放行；伪 token ⇒ 核心零请求）：")
    variant_rows: list[dict[str, Any]] = []
    for endpoint in VARIANT_ENDPOINTS:
        token = registered_token(repo, endpoint)
        native = native_table(base, key, endpoint, token)
        allowed = guard_behaviour(repo, endpoint, token)
        blocked = guard_behaviour(repo, endpoint, FAKE_TOKEN)
        row = {
            "endpoint": endpoint,
            "token": token,
            "native": native,
            "guard_allows_registered_token": not allowed["raised"],
            "guard_blocks_fake_token": bool(blocked["raised"]),
            "guard_fake": blocked,
        }
        variant_rows.append(row)
        print(
            f"  {endpoint:42s} token={token:26s} 原生 {native['status']} · "
            f"HEAD {native['head_columns']} / DATA {native['data_rows']} · "
            f"核心放行={row['guard_allows_registered_token']} · 伪 token 拦={row['guard_blocks_fake_token']}"
        )
    if any(row["native"]["auth_error"] for row in variant_rows):
        print(
            "🛑 原生回了**鉴权失败**（`MAPI Key is invalid.`）—— 那是实例侧的瞬时状态，"
            "**不**是枚举结论 ⇒ **中止**（**不**写证据，重跑即可）"
        )
        return 1

    # ---- ②③④ 核心口径（生产路径 + 截图效果）----
    import tempfile  # noqa: PLC0415

    print("\n② 核心口径（生产路径 `allow_unverified=False`）：")
    with tempfile.TemporaryDirectory(prefix="p168-spec-enum-") as raw:
        core = core_rows(repo, pathlib.Path(raw))

    variant_result = core["variant_result"]
    variant_requests = variant_result["requests"]
    variant_readback = variant_result["readback"]
    variant_ok = (
        variant_result["success"]
        and bool(variant_requests)
        and all(200 <= int(item["status"] or 0) < 300 for item in variant_requests)
        and int(variant_readback.get("count") or 0) > 0
    )
    print(
        f"  {OP_DISPLACEMENT} → success={variant_result['success']} "
        f"requests={[(item['path'], item['status'], item['table_type']) for item in variant_requests]} "
        f"rows={variant_readback.get('count')}"
    )

    fake = core["fake_token"]
    fake_ok = (
        not fake["requests"]
        and fake["error"]["code"] == "STRUCTAI-1200"
        and fake["error"]["native_reason"] == "value_not_in_spec_enum"
    )
    print(
        f"  伪 token（{OP_SUMMARY}）→ requests={len(fake['requests'])} "
        f"code={fake['error']['code']} reason={fake['error']['native_reason']} "
        f"stage={fake['error']['native_stage']} task={fake['task'].get('status')}"
    )

    views = core["views"]
    base_row = views["基线（图形全关）"]
    mode_a_row = views["打开 DisplacementContour"]
    mode_b_row = views["换 DeformedShape"]
    base_shot = base_row["shot"]
    mode_a_shot = mode_a_row["shot"]
    mode_b_shot = mode_b_row["shot"]
    for tag, row in views.items():
        print(f"  {tag:24s} → success={row['success']} 截图 {row['shot']['bytes']} 字节")
    picture_changes = (
        base_shot["exists"]
        and mode_a_shot["exists"]
        and mode_b_shot["exists"]
        and base_shot["sha256"] != mode_a_shot["sha256"]
        and mode_a_shot["sha256"] != mode_b_shot["sha256"]
    )
    print(
        f"  原生真效果：基线 {base_shot['bytes']} → A {mode_a_shot['bytes']} → "
        f"B {mode_b_shot['bytes']} 字节 · 两两不同={picture_changes}"
    )

    legal_sent = bool(mode_a_row["requests"]) and all(
        200 <= int(item["status"] or 0) < 300 for item in mode_a_row["requests"]
    )
    illegal = core["illegal_mode"]
    illegal_ok = (
        not illegal["requests"]
        and illegal["error"]["code"] == "STRUCTAI-1200"
        and illegal["error"]["native_reason"] == "value_not_in_spec_enum"
    )
    print(
        f"  合法取值经生产路径**真的**发出去：{legal_sent} "
        f"（{[(item['path'], item['status'], item['current_mode']) for item in mode_a_row['requests']]}）"
    )
    print(
        f"  非法取值（{ILLEGAL_MODE!r}）→ requests={len(illegal['requests'])} "
        f"code={illegal['error']['code']} reason={illegal['error']['native_reason']}"
    )

    after = sentinels(base, key)
    unchanged = after == before
    print(f"跑后哨兵：{ {k: v['count'] for k, v in after.items()} }   一致：{unchanged}")

    variant_gate_ok = all(
        row["guard_allows_registered_token"] and row["guard_blocks_fake_token"] for row in variant_rows
    )
    native_accepted = all(int(row["native"]["status"]) == 200 for row in variant_rows)
    verdict = (
        PASSED
        if (
            variant_gate_ok
            and native_accepted
            and variant_ok
            and fake_ok
            and picture_changes
            and legal_sent
            and illegal_ok
            and unchanged
        )
        else FAILED
    )
    payload = {
        "phase": "effect",
        "criterion_version": CRITERION_VERSION,
        "instance": {
            "alias": INSTANCE_ALIAS,
            "product": INSTANCE_PRODUCT,
            "probed_at": PROBED_AT,
        },
        "project": project,
        "project_opened_by_probe": opened,
        "closure": closure_facts(repo),
        "variant_table_type": variant_rows,
        "variant_native_accepted": native_accepted,
        "core": {
            "variant_result": variant_result,
            "variant_result_ok": variant_ok,
            "fake_token": fake,
            "fake_token_ok": fake_ok,
            "views": views,
            "picture_changes": picture_changes,
            "legal_mode_sent": legal_sent,
            "illegal_mode": illegal,
            "illegal_mode_blocked": illegal_ok,
        },
        "sentinel": {
            "keys": list(SENTINEL),
            "before": before,
            "after": after,
            "unchanged": unchanged,
        },
        "verdict": verdict,
        "note": (
            "判据 = **效果**（铁律 ⓪）：① 6 个变体端点的**登记 token** 经核心闸门**放行**、"
            "**伪** token **零请求**被拦；② `RESULT.NODE.DISPLACEMENT`（**不**传 `table_type`）"
            "经 MCP Tool 契约取到**真数据行** ⇒ **可见性修复后**这条路径**真的**走了变体文件的枚举；"
            "③ `CURRENT_MODE` 的**合法**取值经 `VIEW.DISPLACEMENT` **真的**发出去且三张截图"
            "**两两不同**（原生真效果）；④ **非法**取值（`displacement`）**零请求**被 `spec_guard` 拦"
            "（**R140** 的保护**首次**覆盖 `VIEW.RESULTGRAPHIC`）。"
        ),
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"⇒ 判定：{'✅ PASSED' if verdict == PASSED else '❌ FAILED'}")
    print(f"wrote {EVIDENCE.relative_to(REPO)}")
    return 0 if verdict == PASSED else 1


# ===== 离线自洽（`--check`，**零请求**）=====


def check_offline(repo: pathlib.Path) -> int:
    """`--check`：证据齐备 + 判据全真 + 与数据侧（生成器 / 普查）一致。"""
    if not EVIDENCE.is_file():
        print(f"❌ 缺证据 {EVIDENCE.relative_to(REPO)}（先跑 --probe）")
        return 1
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    problems: list[str] = []
    facts = closure_facts(repo)

    current = facts["current_mode"]
    if not current["applied"]:
        problems.append("`CURRENT_MODE` 的收口**未落盘**（生成器 --check 不过）")
    if not current["agrees_with_evidence"]:
        problems.append("手册复算的取值表与 `registry/live/view_result_modes.json` **不一致**")
    if not current["illegal_absent"]:
        problems.append(f"非法取值 {ILLEGAL_MODE!r} 出现在枚举里 ⇒ 负向对照不成立")
    if not (current["mode_a_present"] and current["mode_b_present"]):
        problems.append("试的合法取值不在枚举里 ⇒ 正向对照不成立")
    variants = facts["variant_table_type"]
    if not variants["applied"]:
        problems.append("变体 `TABLE_TYPE` 的收口**未落盘**（生成器 --check 不过）")
    for key, enum in variants["enums"].items():
        if not enum:
            problems.append(f"{key} 的 `TABLE_TYPE` 枚举为空")
    binding = facts["adapter_binding"]
    if not binding["uses_effective_schema"]:
        problems.append(
            f"`{ADAPTER_RELATIVE}` 的 `spec_guard` **没有**用 `effective_schema()` "
            f"（实际 {binding['first_argument']!r}）⇒ 盲区未修复"
        )
    if int(facts["guard_visibility"].get("blind_with_effective_schema") or 0) != 0:
        problems.append("`effective_schema()` 下仍有**盲区**文件 ⇒ 与 R161 的结论矛盾")

    core = document.get("core") or {}
    if document.get("verdict") != PASSED:
        problems.append(f"证据里的 verdict 应为 PASSED，实际 {document.get('verdict')!r}")
    for key in ("variant_result_ok", "fake_token_ok", "picture_changes", "legal_mode_sent",
                "illegal_mode_blocked"):
        if core.get(key) is not True:
            problems.append(f"核心判据 {key} 不为真 ⇒ 效果结论不成立")
    if not (document.get("sentinel") or {}).get("unchanged"):
        problems.append("跑后哨兵与跑前不一致 ⇒ 有残留，结论不可用")
    rows = document.get("variant_table_type") or []
    if len(rows) != len(VARIANT_ENDPOINTS):
        problems.append(f"变体证据行数 {len(rows)} ≠ {len(VARIANT_ENDPOINTS)}")
    if document.get("variant_native_accepted") is not True:
        problems.append("6 个变体端点的**登记 token** 原生**没有**全部 `200` ⇒ 阳性不成立")
    for row in rows:
        if not (row.get("guard_allows_registered_token") and row.get("guard_blocks_fake_token")):
            problems.append(f"{row.get('endpoint')} 的核心闸门判据不为真")
        if row.get("native", {}).get("auth_error"):
            problems.append(f"{row.get('endpoint')} 的原生答复是**鉴权失败** ⇒ 证据不可用")

    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    print(
        f"✅ 离线自洽：`CURRENT_MODE` **{current['values']}** 个取值（与 R155 的证据机械一致）· "
        f"6 个变体端点的登记 token **放行**、伪 token **零请求**被拦 · "
        f"`effective_schema()` 盲区 **{facts['guard_visibility']['blind_with_effective_schema']}** · "
        f"生产路径取到真数据行 · 三张截图两两不同 · 哨兵 6 项一致 ⇒ **R161** 成立"
    )
    return 0


def main() -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="spec_guard 枚举收口的效果证据（R161）")
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="自建项目（相对仓库根）")
    parser.add_argument("--probe", action="store_true", help="真发请求（默认只预演）")
    parser.add_argument("--check", action="store_true", help="离线自洽断言（零请求）")
    args = parser.parse_args()
    if args.check:
        return check_offline(REPO)

    guard_paths()
    facts = closure_facts(REPO)
    print(
        f"收口事实：`CURRENT_MODE` **{facts['current_mode']['values']}** 个取值"
        f"（与 R155 的证据一致：{facts['current_mode']['agrees_with_evidence']}）· "
        f"变体 `TABLE_TYPE` 收口已落盘：{facts['variant_table_type']['applied']} · "
        f"盲区（`effective_schema`）：{facts['guard_visibility']['blind_with_effective_schema']} · "
        f"生产路径绑定 `effective_schema()`：{facts['adapter_binding']['uses_effective_schema']}"
    )
    if not args.probe:
        print("\n（预演；加 --probe 才真发）")
        return 0
    print()
    return run_probe(REPO, args.project)


if __name__ == "__main__":
    raise SystemExit(main())
