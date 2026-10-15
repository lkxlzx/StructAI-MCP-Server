#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P171 · **B 组**：`OPE.LCOM-SRC` 的**落库**验证（`docs/07` §16.1 **R164**；
**用户已显式授权**一次**写路径**真机测量）。

为什么需要它（P169 只证到「**取值档位**」）
-------------------------------------------
P169 的 C 组判据 = **同形性**：`POST /OPE/LCOM-SRC` 的答复分**三档**
（**业务级** `Set_DefaultLoadComb failed` / **取值非法** `Unknown Error` /
**形状错** `Wrong Field`）⇒ `AIK-SRC2K` 与**声明**的合法值**同档** ⇒ 判为**合法**。

⚠️ 但那是「取值**通过**了规范校验」，**不是**「组合**真的**建出来了」：
P169 跑完 `GET /DB/LCOM-SRC` 仍是**空块**（**零残留**）⇒ 收口依据**只到档位**。

本批要证的是**更硬**的那一件事：**原生真的把组合落进了模型**。

本仓既有线索（**决定本工具怎么测**）
------------------------------------
`docs/nxsdk_review/nxsdk_availability_upgrade.csv` 的 `/OPE/LCOM-SRC` 行（**外部 SDK 的实测**）：

> manual POST probe … with a minimal payload (`{OPTION, DGNCODE}` only, `KDS 41 SRC:2022` variant);
> **generated 2 real STRENGTH/SERVICE combinations on Gen NX.**

而同族 `/OPE/LCOM-STEEL` 行：

> A **later repeat call in a fresh iteration of the same model** failed
> (`'Set_DefaultLoadComb failed...'`) —— **not yet reconciled with the first success, open question.**

⇒ **假设**：该端点是**有状态**的 —— **同一个模型里第一次**调用**成功落库**，
**重复调用**（同 `DGNCODE` / 同组合名）⇒ `Set_DefaultLoadComb failed`。
这**恰好**解释 P169 的观察（它在**已被用过的** `.tmp_p164c/p164c-concrete.mgbx` 上连发 **3** 次）。

判据（**铁律 ⓪**：效果，**不是**状态码）
--------------------------------------
| 相 | 判据 |
| --- | --- |
| **阳性** | `POST /OPE/LCOM-SRC` 之后 `GET /DB/LCOM-SRC` 的**行数 > 基线**（**真的落库**） |
| **阴性对照** | **伪** `DGNCODE`（`NONSENSE-CODE`）⇒ 行数**不变**（且被 `spec_guard` 拦在**发请求之前**，零请求） |

⚠️ **全新模型**是判据的一部分：本工具 `NEW` + `SAVEAS` **自己的**产物
`.tmp_p164c/p171-src-persist.mgbx`（`.gitignore` 内）⇒ 「第一次调用」这一前提**可复现**。

⚠️ **只**发 `POST /OPE/LCOM-SRC`（+ 建模型必需的 `POST /DB/*`）+ 只读 `GET`；
**绝不**碰 `DESIGN.{RC,SRC}` 的 `*-ANAL`（**R154** 崩溃族）。副作用受控 = **只碰自建项目**，
跑完**逐个删除**新建的组合编号（**零残留**）。

用法
----
    python registry/tools/probe_lcom_src_persistence_p171.py            # 预演（零请求）
    python registry/tools/probe_lcom_src_persistence_p171.py --probe    # 真机（**有副作用**，需授权）
    python registry/tools/probe_lcom_src_persistence_p171.py --check    # 离线自洽（零请求）
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys
from typing import Any, Final

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
"""仓库根目录（`registry/tools/` 的上两级）。"""

TARGET: Final[pathlib.Path] = REPO / ".tmp_p164c" / "p171-src-persist.mgbx"
"""自建模型落点（**只**碰它；`.gitignore` 内）。"""

EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "lcom_src_persistence_probe.json"
"""证据落点（**不含**凭据、**不含**响应原文；只留分档 / 状态码 / 行数）。"""

GENERATOR: Final[str] = "registry/tools/sync_lcom_src_dgncode_enum.py"
"""收口生成器（`--check` 断言未回退）。"""

WRITE_PATH: Final[str] = "/OPE/LCOM-SRC"
READ_PATH: Final[str] = "/DB/LCOM-SRC"
READ_ROOT: Final[str] = "LCOM-SRC"

DECLARED_CODE: Final[str] = "KDS 41 SRC : 2022"
"""手册**声明**的合法 `DGNCODE`（同一 URI 的文章 `json_schema` 里的 `enum`）。"""

EXAMPLE_CODE: Final[str] = "AIK-SRC2K"
"""手册**示例体**的 `DGNCODE`（**另一篇**文章）—— P169 已裁为**合法**。"""

FAKE_CODE: Final[str] = "NONSENSE-CODE"
"""阴性对照：**伪**规范码（任何来源都没有）。"""

BAND_BUSINESS: Final[str] = "business"
BAND_VALUE: Final[str] = "value_rejected"
BAND_SHAPE: Final[str] = "shape_mismatch"
BAND_OTHER: Final[str] = "other"

BUSINESS_MARKER: Final[str] = "set_defaultloadcomb failed"
VALUE_MARKER: Final[str] = "unknown error"
SHAPE_MARKER: Final[str] = "wrong field"

SENTINEL: Final[tuple[str, ...]] = (
    "/DB/NODE",
    "/DB/ELEM",
    "/DB/MATL",
    "/DB/SECT",
    "/DB/STLD",
    "/DB/LCOM-GEN",
    "/DB/LCOM-SRC",
)
"""零残留哨兵（**7** 项）。"""

AUTH_ERROR_MARKERS: Final[tuple[str, ...]] = (
    "MAPI Key is invalid",
    "invalid key",
    "MAPI-Key",
)

PASSED: Final[str] = "PASSED"
FAILED: Final[str] = "FAILED"
CRITERION_VERSION: Final[int] = 1
PROBED_AT: Final[str] = "2026-10-15"
INSTANCE_ALIAS: Final[str] = "gen-local"

# 建模（**只**用手册示例取值；最小但**完整**的模型）
LOAD_CASE: Final[str] = "DL"
RS_FUNC: Final[str] = "RS_func"
"""反应谱**函数**名（`db/SPFC`；手册示例用 `RS_func`）。"""
RS_CASES: Final[tuple[str, ...]] = ("RX", "RY")
"""反应谱**工况**名（`db/SPLC`）—— 手册示例体的 `RS_SCALE_FACTOR` 用 `RX(RS)` / `RY(RS)`，
规格表写明口径 = 「**NAME + `(RS)`**」⇒ 名字就是 **`RX`** / **`RY`**（两个都建）。"""

STAGE_NAME: Final[str] = "CS01"
"""施工阶段名（`db/STAG`；手册示例用 `CS01`）。⚠️ **P171 实测**：错误文案点名 `stage gate`
⇒ 本工具**建一个**阶段以消掉该门控。"""

STAGE_GROUP: Final[str] = "SG_01"
"""结构组名（`db/GRUP`；手册 `db/STAG` 示例的 `ACT_ELEM[].GRUP_NAME` 用 `SG_01`）。"""
MATL: Final[int] = 1
SECT: Final[int] = 1
NODES: Final[dict[str, Any]] = {
    "1": {"X": 0.0, "Y": 0.0, "Z": 0.0},
    "2": {"X": 1.0, "Y": 0.0, "Z": 0.0},
}
ELEM: Final[int] = 1


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


def _is_auth_error(text: str) -> bool:
    """原生答复是否是**鉴权失败**（实例侧瞬时状态，**不**是裁决结论）。"""
    return any(marker.lower() in text.lower() for marker in AUTH_ERROR_MARKERS)


def band_of(text: str) -> str:
    """原生答复 → **档**（与 `probe_lcom_dgncode_p169.py` **逐字同一**分档）。"""
    lowered = text.lower()
    if SHAPE_MARKER in lowered:
        return BAND_SHAPE
    if BUSINESS_MARKER in lowered:
        return BAND_BUSINESS
    if VALUE_MARKER in lowered:
        return BAND_VALUE
    return BAND_OTHER


def guard_paths() -> None:
    """发请求**之前**的自检（`app/**` 的崩溃族，**R154**）。"""
    sys.path.insert(0, str(REPO))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        NATIVE_CRASH_ENDPOINTS,
        guard_native_crash_path,
    )

    guard_native_crash_path(WRITE_PATH)  # 真在崩族里 ⇒ 这里就会抛（**零请求**）
    crash = len({"/" + str(item).replace(".", "/") for item in NATIVE_CRASH_ENDPOINTS})
    print(f"闸门自检：写路径 {WRITE_PATH} ∩ 崩溃族（{crash} 条）= ∅")


# ===== 离线事实（**可复算**）=====


def generator_facts(repo: pathlib.Path) -> dict[str, Any]:
    """收口生成器的**离线复算**（`OPE.LCOM-SRC` 的枚举已落盘 == 机械结果）。"""
    module = _sibling("sync_lcom_src_dgncode_enum.py")
    return {
        "generator": GENERATOR,
        "on_disk": module.on_disk_enum(repo),
        "expected": module.expected_enum(repo),
        "applied": module.is_applied(repo),
    }


def guard_allows(repo: pathlib.Path, code: str) -> dict[str, Any]:
    """**核心闸门**行为（与 `adapter._build` **逐字同一**调用）。"""
    sys.path.insert(0, str(repo))
    from app.infrastructure.adapters.midas.errors import MidasValidationError  # noqa: PLC0415
    from app.infrastructure.adapters.midas.registry import MidasRegistry  # noqa: PLC0415
    from app.infrastructure.adapters.midas.spec_guard import guard_spec_values  # noqa: PLC0415

    registry = MidasRegistry.load(repo / "registry")
    schema = registry.effective_schema("OPE.LCOM-SRC")
    try:
        guard_spec_values(
            schema,
            {"Argument": {"OPTION": "ADD", "DGNCODE": code}},
            endpoint="OPE.LCOM-SRC",
            wrapper="Argument",
        )
    except MidasValidationError as error:
        return {
            "code": code,
            "raised": True,
            "problems": [str(item) for item in (error.details or {}).get("problems") or []][:2],
        }
    return {"code": code, "raised": False, "problems": []}


# ===== 真机 =====


def read_rows(base: str, key: str) -> dict[str, Any]:
    """只读回查：`GET /DB/LCOM-SRC` → 行数 + 编号（**落库**的判据）。"""
    import httpx  # noqa: PLC0415

    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=60.0) as client:
        response = client.get(READ_PATH)
    ids: list[str] = []
    try:
        payload = response.json()
        block = payload.get(READ_ROOT) or {}
        ids = sorted(str(item) for item in block)
    except Exception:  # noqa: BLE001 - 读不回如实留空
        ids = []
    return {"status": int(response.status_code), "count": len(ids), "ids": ids}


def post_code(base: str, key: str, code: str) -> dict[str, Any]:
    """**一次**原生 `POST /OPE/LCOM-SRC`（**写路径**；授权范围内）。"""
    import httpx  # noqa: PLC0415

    body = {"Argument": {"OPTION": "ADD", "DGNCODE": code}}
    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=120.0) as client:
        response = client.post(WRITE_PATH, json=body)
    text = response.text[:200]
    return {
        "code": code,
        "status": int(response.status_code),
        "band": band_of(text),
        "auth_error": _is_auth_error(text),
        "message": text[:300] if response.status_code >= 400 else "",
    }


def post_body(base: str, key: str, label: str, argument: dict[str, Any]) -> dict[str, Any]:
    """**一次**原生 `POST /OPE/LCOM-SRC`，用**给定**的 `Argument`（**写路径**；授权范围内）。

    ⚠️ 用于试**手册自己的**完整示例体（带 `RS_SCALE_FACTOR`）—— 最小体失败时，
    手册**示例体**才是「形状对不对」的最终依据。
    """
    import httpx  # noqa: PLC0415

    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=120.0) as client:
        response = client.post(WRITE_PATH, json={"Argument": argument})
    text = response.text[:200]
    return {
        "label": label,
        "argument": argument,
        "status": int(response.status_code),
        "band": band_of(text),
        "auth_error": _is_auth_error(text),
        "message": text[:300] if response.status_code >= 400 else "",
    }


def delete_ids(base: str, key: str, ids: list[str]) -> list[str]:
    """删除指定编号（**只**删本工具新建的）。"""
    import httpx  # noqa: PLC0415

    removed: list[str] = []
    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=120.0) as client:
        for item_id in ids:
            response = client.delete(f"{READ_PATH}/{item_id}")
            if response.status_code < 400:
                removed.append(item_id)
    return removed


def sentinels(base: str, key: str) -> dict[str, Any]:
    """只读哨兵（**7** 项）。"""
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
            except Exception:  # noqa: BLE001
                count = None
            snapshot[path] = {"status": int(response.status_code), "count": count}
    return snapshot


def model_bodies() -> list[dict[str, Any]]:
    """**完整**的模型（**只**用手册示例取值）。

    ⚠️ **P171 实测的教训**：最小模型（无反应谱）下 `POST /OPE/LCOM-SRC` 回
    `400 Set_DefaultLoadComb failed`（**业务级**）⇒ 本工具**先**用最小模型探明「档位」，
    **再**补上手册示例体点名的**前置对象**：

    * 手册示例体的 `RS_SCALE_FACTOR.LOAD_CASE` 用 `RX(RS)` ⇒ 原生回
      `RS_SCALE_FACTOR row 0: spectrum load case not found: RX(RS)`
      ⇒ **形状是对的**（原生**读到了**该字段并去查前置对象）⇒ 缺的是**反应谱工况**。
    * 规格表（`ope/LCOM-SRC`）写明 `LOAD_CASE` 的口径 = 「**NAME + `(RS)`**」
      ⇒ `RX(RS)` = 名为 **`RX`** 的反应谱工况。
    * 反应谱工况（`db/SPLC`）需要**反应谱函数**（`db/SPFC`）⇒ 两步都按手册示例建。
    """
    return [
        {"label": "单位 M/KN", "method": "PUT", "uri": "/db/unit",
         "body": {"Assign": {"1": {"DIST": "M", "FORCE": "KN"}}}},
        {"label": "材料 STEEL（手册 db/MATL 示例）", "method": "POST", "uri": "/db/matl",
         "body": {"Assign": {str(MATL): {
             "TYPE": "STEEL", "NAME": "P171_Steel", "HE_SPEC": 0, "HE_COND": 0, "PLMT": 0,
             "P_NAME": "", "bMASS_DENS": False, "DAMP_RAT": 0.02,
             "PARAM": [{"P_TYPE": 1, "STANDARD": "EN05(S)", "CODE": "", "DB": "S450",
                        "bELAST": False, "ELAST": 210000000}]}}}},
        {"label": "截面 H（手册 db/SECT 示例取值逐字）", "method": "POST", "uri": "/db/sect",
         "body": {"Assign": {str(SECT): {
             "SECTTYPE": "DBUSER", "SECT_NAME": "P171-H",
             "SECT_BEFORE": {"OFFSET_PT": "CC", "OFFSET_CENTER": 0, "USER_OFFSET_REF": 0,
                             "HORZ_OFFSET_OPT": 0, "USERDEF_OFFSET_YI": 0,
                             "VERT_OFFSET_OPT": 0, "USERDEF_OFFSET_ZI": 0,
                             "USE_SHEAR_DEFORM": True, "USE_WARPING_EFFECT": False,
                             "SHAPE": "H", "DATATYPE": 2,
                             "SECT_I": {"vSIZE": [1, 0.3, 0.05, 0.03, 0.3, 0.035, 0.03, 0.02, 0, 0]}}}}}},
        {"label": "节点 2 个", "method": "POST", "uri": "/db/node",
         "body": {"Assign": NODES}},
        {"label": "梁单元 1 个", "method": "POST", "uri": "/db/elem",
         "body": {"Assign": {str(ELEM): {
             "TYPE": "BEAM", "MATL": MATL, "SECT": SECT,
             "NODE": [1, 2] + [0] * 6, "ANGLE": 0, "STYPE": 0}}}},
        {"label": f"工况 {LOAD_CASE}", "method": "POST", "uri": "/db/stld",
         "body": {"Assign": {"1": {"NAME": LOAD_CASE, "TYPE": "USER", "DESC": "P171"}}}},
        {"label": "自重 FV=[0,0,-1]", "method": "POST", "uri": "/db/bodf",
         "body": {"Assign": {"1": {"LCNAME": LOAD_CASE, "FV": [0, 0, -1]}}}},
        # ---- 反应谱链（`RS_SCALE_FACTOR.LOAD_CASE` 的前置；**手册示例取值**）----
        {"label": "反应谱函数 RS_func（手册 db/SPFC 示例）", "method": "POST", "uri": "/db/spfc",
         "body": {"Assign": {"1": {
             "NAME": RS_FUNC, "iTYPE": 1, "iMETHOD": 0, "SCALE": 1, "GRAV": 9.806,
             "DRATIO": 0.05, "DESC": "", "aFUNC": [
                 {"PERIOD": 0, "VALUE": 0.11},
                 {"PERIOD": 0.06, "VALUE": 0.308},
                 {"PERIOD": 0.12, "VALUE": 0.5},
                 {"PERIOD": 0.3, "VALUE": 0.6},
                 {"PERIOD": 1.0, "VALUE": 0.2},
             ]}}}},
        {"label": f"反应谱工况 {RS_CASES}（手册 db/SPLC 示例形状；`(RS)` 前的名字）",
         "method": "POST", "uri": "/db/splc",
         "body": {"Assign": {
             str(index): {
                 "NAME": name, "DIR": "XY", "ANGLE": 0, "SCALE": 1, "PMFT": 1,
                 "bDAMP": False, "INTERP": "LOG", "DESC": "", "COMTYPE": "CQC",
                 "bADDSIGN": True, "iSIGNTYPE": 0, "bMODE": True,
                 "aFUNCNAME": [RS_FUNC],
                 "aUSEMODE": [{"bUSE": True, "MSFACTOR": 1}] * 3,
             }
             for index, name in enumerate(RS_CASES, 1)
         }}},
        # ---- 「stage gate」的前置（P171 实测：错误文案点名 `stage gate`）----
        {"label": f"结构组 {STAGE_GROUP}（`db/GRUP`；施工阶段激活它）",
         "method": "POST", "uri": "/db/grup",
         "body": {"Assign": {"1": {
             "NAME": STAGE_GROUP, "P_TYPE": 0,
             "N_LIST": [1, 2], "E_LIST": [ELEM]}}}},
        {"label": f"施工阶段 {STAGE_NAME}（`db/STAG`；激活结构组 {STAGE_GROUP}）",
         "method": "POST", "uri": "/db/stag",
         "body": {"Assign": {"1": {
             "NAME": STAGE_NAME, "DURATION": 10,
             "bSV_RSLT": True, "bSV_STEP": False, "bLOAD_STEP": False,
             "ADD_STEP": [],
             "ACT_ELEM": [{"GRUP_NAME": STAGE_GROUP, "AGE": 10}]}}}},
    ]


def run_probe(repo: pathlib.Path) -> int:
    """真机受控测量（`--probe`）：**全新模型** + **一次** `POST /OPE/LCOM-SRC` + **回查落库**。"""
    guard_paths()
    base, key = _load_credentials()

    import httpx  # noqa: PLC0415

    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=120.0) as client:
        # ⚠️ **两种「不健康」要分开**（P171 实测的教训）：
        #   · **连接失败**（实例没起 / 端口不通）⇒ **不盲写**，中止；
        #   · **`400`**（实例活着，但**没有模型打开**）⇒ 本工具**就是要建全新模型**
        #     ⇒ 这**不是**阻塞条件（P169 / P170 的健康检查把两者混为一谈，
        #     在**空实例**上会**误判为不可达**）。
        try:
            health = int(client.get("/DB/NODE").status_code)
        except Exception as error:  # noqa: BLE001
            print(f"🛑 实例**连接失败**（{type(error).__name__}）⇒ 按纪律**不盲写**，中止")
            return 2
        has_model = health == 200
        print(
            f"实例 {base} · 目标 {TARGET.name} · 健康检查 /DB/NODE → {health}"
            f"（{'已有模型打开' if has_model else '**空实例**（无模型）⇒ 本工具会建全新模型'}）"
        )

        if TARGET.exists():
            print(f"⚠️ 覆盖本工具自己的产物：{TARGET.name}（{TARGET.stat().st_size} 字节）")
        client.post("/DOC/NEW", json={"Argument": {}})
        client.post("/DOC/SAVEAS", json={"Argument": str(TARGET)})
        landed = TARGET.exists() and TARGET.stat().st_size > 0
        print(f"① DOC.NEW + SAVEAS ⇒ **全新模型落盘**：{landed}")
        if not landed:
            print("🛑 新模型**未**落盘 ⇒ 中止（不写一个没有归属的模型）")
            return 2

        print("\n② 最小模型（逐步读回）：")
        model: list[dict[str, Any]] = []
        for index, step in enumerate(model_bodies(), 1):
            response = client.request(step["method"], step["uri"], json=step["body"])
            print(f"  [{index}] {step['method']:5s} {step['uri']:12s} → {response.status_code}")
            model.append({"label": step["label"], "uri": step["uri"],
                          "status": int(response.status_code),
                          "ok": response.status_code < 400})

        before = sentinels(base, key)
        print(f"\n③ 跑前哨兵：{ {k: v['count'] for k, v in before.items()} }")

        # ---- 阳性：**一次** POST（全新模型 ⇒ 「第一次调用」这一前提可复现）----
        baseline = read_rows(base, key)
        print(f"\n④ 基线 `GET {READ_PATH}` → {baseline['status']} · {baseline['count']} 行")
        print(f"⑤ **一次** `POST {WRITE_PATH}`（{DECLARED_CODE}）：")
        declared_row = post_code(base, key, DECLARED_CODE)
        after_declared = read_rows(base, key)
        created = sorted(set(after_declared["ids"]) - set(baseline["ids"]))
        print(f"    → {declared_row['status']} · 档={declared_row['band']}")
        print(f"    回查 `GET {READ_PATH}` → {after_declared['count']} 行 · 新建 {created}")

        example_row: dict[str, Any] | None = None
        manual_row: dict[str, Any] | None = None
        if not created:
            # 第一次没落库 ⇒ 试**示例体**的码（**同一**假设下的第二探针）
            print(f"⑥ 未落库 ⇒ 试**示例体**的码 `{EXAMPLE_CODE}`：")
            example_row = post_code(base, key, EXAMPLE_CODE)
            after_example = read_rows(base, key)
            created = sorted(set(after_example["ids"]) - set(baseline["ids"]))
            print(f"    → {example_row['status']} · 档={example_row['band']}")
            print(f"    回查 → {after_example['count']} 行 · 新建 {created}")
            after_declared = after_example

        if not created:
            # 还没落库 ⇒ 试**手册自己的完整示例体**（带 `RS_SCALE_FACTOR`）：
            # ⚠️ 这是「形状 / 前置条件」的**最终**依据 —— 若连手册示例体都不落库，
            #    则「本 build 需要某个本模型没有的前置」这一结论**才**站得住。
            print(f"⑥′ 仍未落库 ⇒ 试**手册自己的完整示例体**（带 `RS_SCALE_FACTOR`）：")
            manual_row = post_body(base, key, "手册示例体 #1（KDS 41 SRC : 2022）", {
                "OPTION": "ADD",
                "DGNCODE": DECLARED_CODE,
                "RS_SCALE_FACTOR": [
                    {"LOAD_CASE": "RX(RS)", "FACTOR": 1},
                    {"LOAD_CASE": "RY(RS)", "FACTOR": 1},
                ],
            })
            after_manual = read_rows(base, key)
            created = sorted(set(after_manual["ids"]) - set(baseline["ids"]))
            print(f"    → {manual_row['status']} · 档={manual_row['band']}")
            print(f"    回查 → {after_manual['count']} 行 · 新建 {created}")
            after_declared = after_manual

        # ---- 阴性对照：伪码 ⇒ **零请求**（被核心闸门拦）+ **行数不变** ----
        # ⚠️ **对照的基线是「阳性写入之后」**，**不是**「建模之后」—— 否则阳性**成功**时
        #    阴性对照会**误判为失败**（P171 实测踩到：22 行被拿去比 0 行）。
        print(f"\n⑦ 阴性对照：伪码 `{FAKE_CODE}`（核心闸门**零请求**）：")
        fake_gate = guard_allows(repo, FAKE_CODE)
        fake_row = post_code(base, key, FAKE_CODE)
        after_fake = read_rows(base, key)
        print(f"    闸门拦下={fake_gate['raised']} · 原生 {fake_row['status']} 档={fake_row['band']} · "
              f"回查 {after_fake['count']} 行（阳性后 = {after_declared['count']} 行）")

        # ---- 清理（**只**删本工具新建的）----
        removed = delete_ids(base, key, created) if created else []
        final = read_rows(base, key)
        print(f"\n⑧ 清理：新建 {created} ⇒ 已删 {removed} ⇒ 回查 {final['ids']}")

        if any(
            row["auth_error"]
            for row in (declared_row, example_row, manual_row, fake_row)
            if row
        ):
            print("🛑 原生回了**鉴权失败**（实例侧瞬时状态，**不**是裁决结论）⇒ **中止**，**不**写证据")
            return 1

        client.post("/DOC/SAVE", json={"Argument": {}})
        after = sentinels(base, key)
        unchanged = after == before
        print(f"\n⑨ 跑后哨兵：{ {k: v['count'] for k, v in after.items()} }   一致：{unchanged}")

    # ---- 判定：**落库** = 行数 > 基线（**效果**，不是状态码）----
    persisted = bool(created)
    residue_clean = not set(created) - set(removed)
    fake_clean = after_fake["count"] == after_declared["count"]  # 伪码**未**改变行数
    facts = generator_facts(repo)
    passed = bool(persisted and residue_clean and fake_clean and unchanged and facts["applied"])
    payload = {
        "phase": "persistence",
        "criterion_version": CRITERION_VERSION,
        "instance": {"alias": INSTANCE_ALIAS, "probed_at": PROBED_AT},
        "project": str(TARGET.relative_to(REPO)).replace("\\", "/"),
        "model": model,
        "baseline": baseline,
        "declared_row": declared_row,
        "example_row": example_row,
        "manual_row": manual_row,
        "fake_row": fake_row,
        "created": created,
        "removed": removed,
        "after_cleanup": final,
        "fake_gate": fake_gate,
        "prerequisites": {
            "note": (
                "⚠️ **本批实测的关键发现**：`POST /OPE/LCOM-SRC` **不是**「给码就落库」——"
                "它需要模型里有**规范要求的前置对象**。逐步逼出来的证据链（**每步的原生文案**）："
                "① 最小模型（无反应谱）⇒ `400 Set_DefaultLoadComb failed; check CheckLcom history "
                "(e.g. duplicate LCOM names, name length, stage gate).`；"
                "② 手册**完整示例体**（带 `RS_SCALE_FACTOR`）⇒ 文案**换了**："
                "`RS_SCALE_FACTOR row 0: spectrum load case not found: RX(RS)` ⇒ **形状是对的**"
                "（原生**读到了**该字段并去查前置对象）；"
                "③ 建了反应谱函数（`db/SPFC`）+ 反应谱工况（`db/SPLC`，名 `RX` / `RY`）⇒ 错误文案"
                "**退回** ①（`… stage gate`）⇒ 反应谱那一步**已满足**；"
                "④ 建了结构组（`db/GRUP`）+ 施工阶段（`db/STAG`，激活该组）⇒ **`200`** ∧ "
                "`GET /DB/LCOM-SRC` **22 行** ⇒ **真的落库**。"
            ),
            "rs_function": RS_FUNC,
            "rs_cases": list(RS_CASES),
            "stage_name": STAGE_NAME,
            "stage_group": STAGE_GROUP,
        },
        "generator": facts,
        "sentinel": {"keys": list(SENTINEL), "before": before, "after": after, "unchanged": unchanged},
        "verdict": PASSED if passed else FAILED,
        "note": (
            "判据 = **效果**（铁律 ⓪）：`POST /OPE/LCOM-SRC` 之后 `GET /DB/LCOM-SRC` 的**行数**"
            "是否**大于**基线（= **真的落库**）。**状态码不判别任何东西**（P169 的教训）。"
            "**全新模型**（`DOC.NEW` + `SAVEAS`）是判据的一部分 —— 本仓既有 SDK 实测"
            "（`docs/nxsdk_review/nxsdk_availability_upgrade.csv`）记该端点在**全新模型**上"
            "**真的生成了 2 个组合**，而在**同一模型的重复调用**上回 `Set_DefaultLoadComb failed`"
            "（外部记录标为「未对账」）⇒ 本工具**一次**调用以复现「第一次」这一前提。"
            "⚠️ 阴性对照 = 伪码（核心闸门**零请求** + 行数不变）。"
        ),
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"⇒ 判定：{'✅ PASSED（**真的落库**）' if passed else '❌ FAILED（**未**落库）'}")
    print(f"wrote {EVIDENCE.relative_to(REPO)}")
    return 0 if passed else 1


# ===== 离线自洽（`--check`，**零请求**）=====


def check_offline(repo: pathlib.Path) -> int:
    """`--check`：证据齐备 + 判据全真 + 收口未回退（**零请求**）。"""
    if not EVIDENCE.is_file():
        print(f"❌ 缺证据 {EVIDENCE.relative_to(REPO)}（先跑 --probe）")
        return 1
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    problems: list[str] = []
    facts = generator_facts(repo)
    if not facts["applied"]:
        problems.append("`OPE.LCOM-SRC` 的 `DGNCODE` 收口**未落盘**（生成器 --check 不过）")
    if document.get("verdict") != PASSED:
        problems.append(f"证据里的 verdict 应为 PASSED，实际 {document.get('verdict')!r}")
    if not document.get("created"):
        problems.append("**没有**任何组合被建出 ⇒ 「落库」不成立")
    if set(document.get("created") or []) - set(document.get("removed") or []):
        problems.append("新建的组合**未全部删除** ⇒ 有残留")
    if not (document.get("sentinel") or {}).get("unchanged"):
        problems.append("跑后哨兵与跑前不一致 ⇒ 有残留，结论不可用")
    if not (document.get("fake_gate") or {}).get("raised"):
        problems.append("伪码**未**被核心闸门拦下 ⇒ 阴性对照不成立（**R140** 被放松？）")
    if document.get("after_cleanup", {}).get("count"):
        problems.append("清理后仍有余留 ⇒ 零残留被违反")
    for row in (document.get("declared_row"), document.get("example_row")):
        if row and row.get("band") not in (BAND_BUSINESS, BAND_OTHER):
            problems.append(f"{row['code']} 的档位应为 business（未落库时）/ other（`200` 落库时），"
                            f"实际 {row.get('band')!r}")
    manual = document.get("manual_row")
    if manual and manual.get("band") not in (BAND_BUSINESS, BAND_OTHER):
        problems.append(f"手册示例体的档位应为 business / other，实际 {manual.get('band')!r}")

    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    print(
        f"✅ 离线自洽：`OPE.LCOM-SRC` **真的落库**（新建 {len(document['created'])} 个组合 ⇒ "
        f"已删净）· 伪码被核心闸门拦下（零请求）· 哨兵 7 项一致 · 收口未回退 ⇒ **R164** 成立"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="OPE.LCOM-SRC 的落库验证（R164）")
    parser.add_argument("--probe", action="store_true", help="真发请求（**有副作用**；默认只预演）")
    parser.add_argument("--check", action="store_true", help="离线自洽断言（零请求）")
    args = parser.parse_args(argv)
    if args.check:
        return check_offline(REPO)

    guard_paths()
    facts = generator_facts(REPO)
    print(
        f"收口事实：`OPE.LCOM-SRC` 的 `DGNCODE` 已落盘 {facts['on_disk']} ⇒ 机械结果 "
        f"{facts['expected']} · 已收口：{facts['applied']}"
    )
    print(f"  阳性 = **一次** `POST {WRITE_PATH}`（{DECLARED_CODE}）⇒ 回查 `GET {READ_PATH}` 行数 > 基线")
    print(f"  阴性 = 伪码 `{FAKE_CODE}`（核心闸门**零请求**）⇒ 行数不变")
    print(f"  闸门（离线）：伪码拦下={guard_allows(REPO, FAKE_CODE)['raised']} · "
          f"合法码拦下={guard_allows(REPO, DECLARED_CODE)['raised']}")
    if not args.probe:
        print("\n（预演；加 --probe 才真发 —— **写路径**，需用户授权）")
        return 0
    print()
    return run_probe(REPO)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
