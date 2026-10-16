#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P174 · 收口 `POST.STEELCODECHECK`（`docs/07` §16.1 **R166** 的「我方唯一杠杆」；
**用户已显式授权**一次**写路径**真机测量）。

为什么需要它（`docs/reports/P160e-a` §1 + **R165**）
----------------------------------------------------
收益**已经算准**（`--benefit`）：收口它 ⇒ 解锁 `DESIGN.CODE_CHECK`（**+1**，
主指标 **68 → 69**）。⚠️ 但**收益 ≠ 可实施性**：它的**请求体来源在本仓不成立** ——

* 手册条目的 `sections_present` = `['Input URI','Active Methods','JSON Schema','Specifications']`
  —— **没有** `Request Examples` / `Response Examples`（`request_examples == []`）；
* 手册的 `json_schema` 根键 = `vSECT` / `vELEM`，规格表描述的是 **Combined Strength Ratio /
  Slenderness Ratio / Deflection / Allowable Deflection** ⇒ **结果量** ⇒ 那是**响应**形状；
* 我们**已落盘**的 Schema 与它**逐字节同形**且**没有** `properties`
  ⇒ `spec_guard`（**R140**）对它**一个字段都不检查**
  ⇒ ⚠️ **阴性对照不能靠核心闸门**（它什么都不拦）—— 必须让**原生**去拒。

⇒ 唯一出路 = 一次**有副作用**的授权测量（**R151** 的教训：**不**按示例体硬凑，这里**连示例体都没有**）。

判据（**铁律 ⓪**：效果，**不是**状态码）
--------------------------------------
本端点的 `json_schema` 是**结果表**形状 ⇒ 「效果」= **它答复里的结果行数**
（`vSECT` / `vELEM` 的元素个数），**不是** `200`。

⚠️ **R157 的方法学**：说「没变 / 无效」之前，必须先证明**仪器有效** ⇒ 本工具做**三段对照**：

| 相 | 时点 | 期望 | 说明 |
| --- | --- | --- | --- |
| **① 无设计结果** | `CODE-ANAL` **之前** | 行数 **= 0**（或原生拒） | 证明输出**真的**跟着设计状态走（**不是**「静默 `200`」） |
| **② 阳性参照** | 跑完 `CODE-ANAL` + `CODE-TABLE` | `CODE-TABLE` 行数 **> 0** | **阳性写入**；本相之后才取**阴性对照的基线**（同 **R164**） |
| **③ 有设计结果** | 同上之后，**同一批** `Argument` | 行数 **> 0** | ①→③ 的**行数差**才是「效果」，`200` 不判别任何东西 |

**阴性对照** = **伪** `Argument`（任何来源都没有的取值）⇒ 原生**拒**（`4xx`）或**零行**，
且**不得**改变行数（基线 = **③ 之后**）。

⚠️ 副作用受控：**只**碰自建项目 `.tmp_p164c/p174-steelcodecheck.mgbx`（`.gitignore` 内）；
**只**发建模 / 设计链必需的写请求 + 只读 `GET`；**绝不**碰 `DESIGN.{RC,SRC}` 的 `*-ANAL`（**R154**）；
跑完**哨兵逐项一致**（零残留）。

用法
----
    python registry/tools/probe_steelcodecheck_p174.py            # 预演（零请求）
    python registry/tools/probe_steelcodecheck_p174.py --probe    # 真机（**有副作用**，需授权）
    python registry/tools/probe_steelcodecheck_p174.py --check    # 离线自洽（零请求）
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

TARGET: Final[pathlib.Path] = REPO / ".tmp_p164c" / "p174-steelcodecheck.mgbx"
"""自建模型落点（**只**碰它；`.gitignore` 内）。"""

EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "steelcodecheck_probe.json"
"""证据落点（**不含**凭据、**不含**响应原文；只留状态码 / 行数 / 字段名）。"""

WRITE_PATH: Final[str] = "/POST/STEELCODECHECK"
"""被测端点（`availability: untested` ⇒ 本批要收口它）。"""

CODE_TABLE_PATH: Final[str] = "/DESIGN/STEEL/KDS-41-30-2022/CODE-TABLE"
"""阳性参照：钢构件规范校核**表**（已 `verified`，旗舰链 12/12 跑通）。"""

CODE_ANAL_PATH: Final[str] = "/DESIGN/STEEL/KDS-41-30-2022/CODE-ANAL"
"""设计执行（**不是** `RC`/`SRC` 的崩溃族 —— 它在旗舰链里真机跑通）。"""

SENTINEL: Final[tuple[str, ...]] = (
    "/DB/NODE",
    "/DB/ELEM",
    "/DB/MATL",
    "/DB/SECT",
    "/DB/STLD",
    "/DB/LCOM-STEEL",
    "/DB/CONS",
)
"""零残留哨兵（**7** 项）。"""

# ===== 候选 `Argument`（手册**没有**请求示例 ⇒ 只能**实测**试形状）=====

CANDIDATE_EMPTY: Final[dict[str, Any]] = {"Argument": {}}
"""① 最小体：`{}`（若该端点只是「取当前校核结果」，空体就够）。"""

CANDIDATE_TABLE_TYPE: Final[dict[str, Any]] = {"Argument": {"TABLE_TYPE": "STEELCODECHECK"}}
"""② 自名 `TABLE_TYPE`（与 `POST.TABLE` 同族端点的常见形状；**猜测**，见下注）。"""

CANDIDATE_AS_CODE_TABLE: Final[dict[str, Any]] = {
    "Argument": {"ELEMS": {"KEYS": [1]}, "PRI_SORT": 1, "RESULT": 0, "TABLE_TYPE": "PROP"}
}
"""③ **逐字照**已 `verified` 的 `CODE-TABLE` 的请求体（**P157 真机实测**通过的那个）。

⚠️ 这条最有信息量：若它 → 有行数，则 STEELCODECHECK 与 CODE-TABLE **同契约**（别名 / 同族）；
若它 → 拒，则两者**不同契约**（本端点另有形状）。
"""

CANDIDATE_NEGATIVE: Final[dict[str, Any]] = {
    "Argument": {"TABLE_TYPE": "NONSENSE_NOT_A_TYPE_P174"}
}
"""**伪** `TABLE_TYPE`（任何来源都没有）—— **不是**有效的阴性对照，见下注。

⚠️ **P174 实测（第一次跑就推翻了本设计）**：本端点对 `Argument` **完全不敏感** ——
空体 `{}` / 自名 `TABLE_TYPE` / **逐字照** `CODE-TABLE` 的体 / **伪** `TABLE_TYPE`
四者的**答复逐字节同形**（含取值）⇒ **没有**任何「非法取值」能让原生拒
⇒ 「坏取值被拦」这一**形态**的阴性对照在本端点**结构上不可用**（如实记录，
**不**硬凑一个假的对照 —— **R157** 的方法学）。

⇒ 本批改用**可用的**那个阴性对照：**同一个请求体**，在**没有设计结果**时
（`CODE-ANAL` 之前）⇒ **0 行**（见 `state_control`）。这才是「输出**真的**跟着设计状态走、
**不是**恒定答复」的判据。
"""

MANUAL_SAMPLE_ELEM: Final[int] = 10
"""手册 `json_schema` **示例体**里的 `vELEM.ELEM`（`10`）。

⚠️ 它是**防「静态回显」**的判据：本模型**没有**单元 `10`（只有单元 `1`）
⇒ 若响应回 `ELEM=10`，那是**手册 schema 的回显**，**不是**计算（**效果判据不成立**）。
"""

MANUAL_SAMPLE_RAT: Final[float] = 0.611917806624809
"""手册示例体的 `vSECT.RAT` —— 同上，用作回显指纹。"""

# ===== 建模（**逐字照** P157 / P160a 旗舰链 —— 真机 12/12 跑通的那一套）=====

MATL: Final[int] = 1
SECT: Final[int] = 1
ELEM: Final[int] = 1
LOAD_CASE: Final[str] = "AXIAL"

NODES: Final[dict[str, Any]] = {
    "1": {"X": 0.0, "Y": 0.0, "Z": 0.0},
    "2": {"X": 0.0, "Y": 0.0, "Z": 6.0},
}


def model_bodies() -> list[dict[str, Any]]:
    """**完整**的钢模型（**逐字照** `registry/live/flagship_chain_probe.json` 的 `substituted`）。

    ⚠️ **不臆造**取值 —— 全部来自那条**真机 12/12** 的证据，包括 `DESIGN.STEEL` 的 4 步配置。
    """
    return [
        {"label": "单位 M/KN", "method": "PUT", "uri": "/DB/UNIT",
         "body": {"Assign": {"1": {"DIST": "M", "FORCE": "KN", "HEAT": "KJ", "TEMPER": "C"}}}},
        {"label": "材料 Q355（GB50017-17(S)）", "method": "POST", "uri": "/DB/MATL",
         "body": {"Assign": {str(MATL): {
             "PARAM": [{"bELAST": False, "CODE": "", "DB": "Q355", "ELAST": 206000000.0,
                        "P_TYPE": 1, "STANDARD": "GB50017-17(S)"}],
             "bMASS_DENS": False, "DAMP_RAT": 0.02, "HE_COND": 0, "HE_SPEC": 0,
             "NAME": "Q355", "P_NAME": "", "PLMT": 0, "TYPE": "STEEL"}}}},
        {"label": "截面 P154S1（SB）", "method": "POST", "uri": "/DB/SECT",
         "body": {"Assign": {str(SECT): {
             "SECT_BEFORE": {"DATATYPE": 2, "HORZ_OFFSET_OPT": 0, "OFFSET_PT": "LT",
                             "SHAPE": "SB", "USE_SHEAR_DEFORM": False,
                             "USE_WARPING_EFFECT": False, "VERT_OFFSET_OPT": 0,
                             "SECT_I": {"vSIZE": [1, 1]}},
             "SECT_NAME": "P154S1", "SECTTYPE": "DBUSER"}}}},
        {"label": "节点 2 个（0,0,0）+（0,0,6）", "method": "POST", "uri": "/DB/NODE",
         "body": {"Assign": NODES}},
        {"label": "梁单元 1 个", "method": "POST", "uri": "/DB/ELEM",
         "body": {"Assign": {str(ELEM): {
             "MATL": MATL, "NODE": [1, 2], "SECT": SECT, "TYPE": "BEAM"}}}},
        {"label": "柱底固定（7 位 CONSTRAINT，rw=0）", "method": "POST", "uri": "/DB/CONS",
         "body": {"Assign": {"1": {"ITEMS": [{"GROUP_NAME": "", "ID": 1,
                                              "CONSTRAINT": "1111110"}]}}}},
        {"label": f"工况 {LOAD_CASE}", "method": "POST", "uri": "/DB/STLD",
         "body": {"Assign": {"1": {"DESC": "AXIAL", "NAME": LOAD_CASE, "TYPE": "D"}}}},
        {"label": "节点荷载 FZ=-500 kN（节点 2）", "method": "POST", "uri": "/DB/CNLD",
         "body": {"Assign": {"2": {"ITEMS": [{"FZ": -500000.0, "ID": 2,
                                              "LCNAME": LOAD_CASE}]}}}},
        {"label": "钢荷载组合 sLCB1（STRENGTH）", "method": "POST", "uri": "/DB/LCOM-STEEL",
         "body": {"Assign": {"1": {"ACTIVE": "STRENGTH",
                                   "vCOMB": [{"ANAL": "ST", "FACTOR": 1.0,
                                              "LCNAME": LOAD_CASE}],
                                   "DESC": "", "iTYPE": 0, "NAME": "sLCB1", "NO": 1}}}},
    ]


def design_chain_bodies() -> list[dict[str, Any]]:
    """钢结构设计链的前 **4** 步（配置，`PUT`）+ `CODE-ANAL`（执行）。

    ⚠️ **逐字照** `app/infrastructure/adapters/midas/operations.py` 的 `DESIGN.STEEL`（**R141**）。
    `CODE-TABLE` **不**在这里 —— 它是**阳性参照**，单独跑（见 `run_probe`）。
    """
    return [
        {"label": "DSTL 规范选择", "method": "PUT", "uri": "/DESIGN/STEEL/DSTL",
         "body": {"Assign": {"1": {"DGNCODE": "KDS 41 30 : 2022"}}}},
        {"label": "DCO 设计选项", "method": "PUT",
         "uri": "/DESIGN/STEEL/KDS-41-30-2022/DCO",
         "body": {"Assign": {"1": {
             "COL_WEAK": True, "COMB_RATIO": 0, "DEFL_CHK": True,
             "DGNCODE": "KDS 41 30 : 2022", "LAT_BRACE": False,
             "SEIS_SYS": "Special Moment Frames", "SEISMIC": False, "UNDGR_LD": True}}}},
        {"label": "DCTL 构件类型", "method": "PUT",
         "uri": "/DESIGN/STEEL/KDS-41-30-2022/DCTL",
         "body": {"Assign": {"1": {"bAUTOKF": False, "DT": "3D",
                                   "FRAMEX": "Braced Non-sway",
                                   "FRAMEY": "Braced Non-sway"}}}},
        {"label": "MEMB 构件指派（单元 1）", "method": "PUT",
         "uri": "/DESIGN/STEEL/KDS-41-30-2022/MEMB",
         "body": {"Assign": {"1": {"AELEM": [ELEM], "bREVERSE": False}}}},
        {"label": "CODE-ANAL 执行校核（PERFORM_TYPE=ALL）", "method": "POST",
         "uri": CODE_ANAL_PATH,
         "body": {"Argument": {"PERFORM_TYPE": "ALL"}}},
    ]


CODE_TABLE_BODY: Final[dict[str, Any]] = {
    "Argument": {"ELEMS": {"KEYS": [ELEM]}, "PRI_SORT": 1, "RESULT": 0, "TABLE_TYPE": "PROP"}
}
"""阳性参照 `CODE-TABLE` 的请求体（**逐字照** P157 真机实测通过的那一个）。"""


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


AUTH_ERROR_MARKERS: Final[tuple[str, ...]] = (
    "MAPI Key is invalid", "invalid key", "MAPI-Key",
)


def _is_auth_error(text: str) -> bool:
    """原生答复是否是**鉴权失败**（实例侧瞬时状态，**不**是裁决结论）。"""
    return any(marker.lower() in text.lower() for marker in AUTH_ERROR_MARKERS)


def guard_paths() -> None:
    """发请求**之前**的自检（`app/**` 的崩溃族，**R154**）。"""
    sys.path.insert(0, str(REPO))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        NATIVE_CRASH_ENDPOINTS,
        guard_native_crash_path,
    )

    guard_native_crash_path(WRITE_PATH)  # 不在崩族里 ⇒ 静默通过
    guard_native_crash_path(CODE_ANAL_PATH)  # 钢的 CODE-ANAL **不在**崩族（旗舰链跑通）
    crash = len({"/" + str(item).replace(".", "/") for item in NATIVE_CRASH_ENDPOINTS})
    print(f"闸门自检：写路径 {WRITE_PATH} ∩ 崩溃族（{crash} 条）= ∅")


def row_count(payload: Any) -> int:
    """结果**行数**（**效果判据**，铁律 ⓪）—— `vSECT` + `vELEM` 的元素个数。

    ⚠️ 本端点的 `json_schema` 根键就是 `vSECT` / `vELEM`（**结果量**）⇒ 行数是它**唯一**
    可判别的效果。原生若回 `{"message": "..."}`（无结果块）⇒ **0 行**（如实记，**不**当成功）。
    """
    if not isinstance(payload, dict):
        return 0
    total = 0
    for key in ("vSECT", "vELEM"):
        block = payload.get(key)
        if isinstance(block, list):
            total += len(block)
        elif isinstance(block, dict):
            total += len(block)
    return total


def result_roots(payload: Any) -> list[str]:
    """响应里**出现**的根键（**只**记键名，**不**记取值）—— 用于判「形状认不认」。"""
    return sorted(payload) if isinstance(payload, dict) else []


# ===== 真机 =====


def post_body(client: Any, label: str, body: dict[str, Any]) -> dict[str, Any]:
    """**一次**原生 `POST /POST/STEELCODECHECK`（**写路径**；授权范围内）。

    ⚠️ 记**状态码 + 行数 + 根键名 + 值指纹**（**不**记凭据 / MAPI-Key）。
    值指纹 = 每行的**标识列 + `RAT`**（`vSECT.SECT` / `vELEM.ELEM` + `RAT`）——
    用于判「返回的**真的**是本模型的设计结果」还是「手册 schema 的**静态回显**」。
    """
    response = client.post(WRITE_PATH, json=body)
    text = response.text
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001 - 非 JSON 时如实记空
        payload = None
    return {
        "label": label,
        "argument_keys": sorted((body.get("Argument") or {})),
        "status": int(response.status_code),
        "rows": row_count(payload),
        "roots": result_roots(payload),
        "fingerprint": value_fingerprint(payload),
        "message": text[:300] if response.status_code >= 400 else "",
        "auth_error": _is_auth_error(text),
    }


IDENTITY_KEYS: Final[tuple[str, ...]] = ("SECT", "ELEM", "RAT", "SLN")


def value_fingerprint(payload: Any) -> list[dict[str, Any]]:
    """每行的**值指纹**：只留标识列与**判据量**（`SECT`/`ELEM`/`RAT`/`SLN`）。

    ⚠️ 目的 = 区分「**真的**本模型结果」与「**手册 schema 的静态回显**」：
    手册的 `json_schema` 示例值（`SECT=1, RAT=0.6119…` · `ELEM=10, RAT=0.1236…`）
    若**逐字**出现在响应里 ⇒ 那是**回显**，**不是**计算。
    """
    fingerprint: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return fingerprint
    for root in ("vSECT", "vELEM"):
        block = payload.get(root)
        if not isinstance(block, list):
            continue
        for item in block:
            if not isinstance(item, dict):
                continue
            fingerprint.append(
                {key: item.get(key) for key in IDENTITY_KEYS if key in item}
            )
    return fingerprint


def code_table_rows(client: Any) -> dict[str, Any]:
    """阳性参照：`POST CODE-TABLE` ⇒ **行数**（证明「设计结果真的在」）。"""
    response = client.post(CODE_TABLE_PATH, json=CODE_TABLE_BODY)
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001
        payload = None
    roots = result_roots(payload)
    rows = 0
    if isinstance(payload, dict):
        block = payload.get("Result Table")
        if isinstance(block, dict):
            for child in block.values():
                if isinstance(child, list):
                    rows += len(child)
    return {
        "status": int(response.status_code),
        "roots": roots,
        "rows": rows,
        "message": response.text[:300] if response.status_code >= 400 else "",
        "auth_error": _is_auth_error(response.text),
    }


def sentinels(client: Any) -> dict[str, Any]:
    """只读哨兵（**7** 项）—— 逐项 `{status, count}`。"""
    snapshot: dict[str, Any] = {}
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


def _probe_batch(client: Any, phase: str) -> list[dict[str, Any]]:
    """在**同一相位**上跑全部候选体（`status` 之和在同一相位内可比）。"""
    rows: list[dict[str, Any]] = []
    for label, body in (
        ("最小体 `{}`", CANDIDATE_EMPTY),
        ("自名 TABLE_TYPE", CANDIDATE_TABLE_TYPE),
        ("逐字照 CODE-TABLE 的体", CANDIDATE_AS_CODE_TABLE),
    ):
        row = post_body(client, label, body)
        row["phase"] = phase
        rows.append(row)
        print(f"    [{phase}] {label:26s} → {row['status']} · 行数 {row['rows']} · 根键 {row['roots']}")
    return rows


def run_probe(repo: pathlib.Path) -> int:
    """真机受控测量（`--probe`）：**全新模型** + **三段对照** + **回查** + **零残留**。"""
    guard_paths()
    base, key = _load_credentials()

    import httpx  # noqa: PLC0415

    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=180.0) as client:
        # ⚠️ **两种「不健康」要分开**：连接失败 ⇒ 不盲写；`400`（无模型打开）⇒ 本工具本就要建新模型。
        try:
            health = int(client.get("/DB/NODE").status_code)
        except Exception as error:  # noqa: BLE001
            print(f"🛑 实例**连接失败**（{type(error).__name__}）⇒ 按纪律**不盲写**，中止")
            return 2
        print(f"实例 {base} · 健康检查 /DB/NODE → {health}")

        if TARGET.exists():
            print(f"⚠️ 覆盖本工具自己的产物：{TARGET.name}（{TARGET.stat().st_size} 字节）")
        client.post("/DOC/NEW", json={"Argument": {}})
        client.post("/DOC/SAVEAS", json={"Argument": str(TARGET)})
        landed = TARGET.exists() and TARGET.stat().st_size > 0
        print(f"① DOC.NEW + SAVEAS ⇒ **全新模型落盘**：{landed}")
        if not landed:
            print("🛑 新模型**未**落盘 ⇒ 中止（不写一个没有归属的模型）")
            return 2

        print("\n② 建钢模型（逐字照旗舰链）+ 分析：")
        model: list[dict[str, Any]] = []
        for index, step in enumerate(model_bodies(), 1):
            response = client.request(step["method"], step["uri"], json=step["body"])
            print(f"  [{index}] {step['method']:5s} {step['uri']:14s} → {response.status_code}")
            model.append({"label": step["label"], "uri": step["uri"],
                          "status": int(response.status_code),
                          "ok": response.status_code < 400})
        analysis = client.post("/DOC/ANAL", json={"Argument": {"TYPE": "STATIC"}})
        print(f"  [A] POST /DOC/ANAL → {analysis.status_code}")

        before = sentinels(client)
        print(f"\n③ 跑前哨兵：{ {k: v['count'] for k, v in before.items()} }")

        # ---- 相 ①：**没有设计结果** ⇒ 输出应**空**（证明仪器跟着设计状态走）----
        print(f"\n④ **相 ①（无设计结果）** 探 `{WRITE_PATH}`：")
        phase_before = _probe_batch(client, "无设计结果")

        # ---- 阳性参照：真的把设计跑出来 ----
        print("\n⑤ 设计链（DSTL/DCO/DCTL/MEMB + CODE-ANAL）：")
        chain: list[dict[str, Any]] = []
        for index, step in enumerate(design_chain_bodies(), 1):
            response = client.request(step["method"], step["uri"], json=step["body"])
            print(f"  [{index}] {step['method']:4s} {step['uri']:52s} → {response.status_code}")
            chain.append({"label": step["label"], "uri": step["uri"],
                          "status": int(response.status_code),
                          "ok": response.status_code < 400})
        table = code_table_rows(client)
        print(f"  阳性参照 `CODE-TABLE` → {table['status']} · 行数 {table['rows']} · 根键 {table['roots']}")

        # ---- 相 ③：**有设计结果** ⇒ 同一批 `Argument` 再看（这就是**阳性写入之后**的基线）----
        print(f"\n⑥ **相 ③（有设计结果）** 探 `{WRITE_PATH}`：")
        phase_after = _probe_batch(client, "有设计结果")

        # ---- 「坏取值被拦」这一形态**不可用**（P174 实测）⇒ 如实记录，不硬凑 ----
        print(f"\n⑦ ⚠️ 伪 `TABLE_TYPE`（**预期**：与合法体**逐字节同形** ⇒ 本端点对 `Argument` 不敏感）：")
        negative = post_body(client, "伪 TABLE_TYPE", CANDIDATE_NEGATIVE)
        negative["phase"] = "阴性（形态不可用）"
        print(f"    → {negative['status']} · 行数 {negative['rows']} · 根键 {negative['roots']}")
        same_as_positive = bool(
            phase_after
            and negative["fingerprint"] == phase_after[-1]["fingerprint"]
            and negative["status"] == phase_after[-1]["status"]
        )
        print(f"    与合法体逐字节同形：{same_as_positive} ⇒ "
              f"{'**该形态的阴性对照不成立**（本端点不校验 Argument）' if same_as_positive else '取值确实有判别力'}")

        # ---- 收尾：保存 + 哨兵 ----
        client.post("/DOC/SAVE", json={"Argument": {}})
        after = sentinels(client)
        unchanged = after == before
        print(f"\n⑧ 跑后哨兵：{ {k: v['count'] for k, v in after.items()} }   一致：{unchanged}")

        rows = phase_before + phase_after + [negative]

    if any(row["auth_error"] for row in rows) or table["auth_error"]:
        print("🛑 原生回了**鉴权失败**（实例侧瞬时状态，**不**是裁决结论）⇒ **中止**，**不**写证据")
        return 1

    # ---- 判定（**铁律 ⓪**：效果，**不是**状态码）----
    before_rows = max((row["rows"] for row in phase_before), default=0)
    after_rows = max((row["rows"] for row in phase_after), default=0)
    winner = max(phase_after, key=lambda row: row["rows"], default=None)
    design_exists = table["rows"] > 0
    # **判据 ①（状态对照）**：同一个请求体，**没**设计结果时 0 行 ⇒ 输出跟着**设计状态**走
    state_control = before_rows == 0 and after_rows > 0
    # **判据 ②（防回显）**：指纹**不得**等于手册 schema 的示例值（`ELEM=10` / `RAT=0.6119…`）
    fingerprint = list(winner["fingerprint"]) if winner else []
    echoes_manual = any(
        row.get("ELEM") == MANUAL_SAMPLE_ELEM
        or abs(float(row.get("RAT") or 0) - MANUAL_SAMPLE_RAT) < 1e-9
        for row in fingerprint
        if isinstance(row, dict)
    )
    not_echo = bool(fingerprint) and not echoes_manual
    # **判据 ③**：结果块**真的**带 `vSECT` / `vELEM` 两个根
    shape_ok = bool(winner) and winner["roots"] == ["vELEM", "vSECT"]
    passed = bool(design_exists and state_control and not_echo and shape_ok and unchanged)

    payload = {
        "phase": "steelcodecheck",
        "criterion_version": 1,
        "instance": {"alias": "gen-local", "probed_at": "2026-10-16"},
        "project": str(TARGET.relative_to(REPO)).replace("\\", "/"),
        "endpoint": WRITE_PATH,
        "contract_facts": {
            "note": (
                "手册条目**没有**请求形状：`sections_present` 不含 `Request Examples` / "
                "`Response Examples`，`request_examples == []`；`json_schema` 的根键是 "
                "`vSECT` / `vELEM`（规格表 = Combined Strength Ratio / Slenderness Ratio / "
                "Deflection / Allowable Deflection ⇒ **结果量**）⇒ 那是**响应**形状。"
                "⚠️ 我们落盘的 Schema 与它**逐字节同形**且**没有** `properties` ⇒ "
                "`spec_guard` **一个字段都不检查** ⇒ 阴性对照**不能**靠核心闸门（**R165**）。"
            ),
            "declared_sections": ["Input URI", "Active Methods", "JSON Schema", "Specifications"],
            "declared_schema_roots": ["vSECT", "vELEM"],
            "request_examples": [],
        },
        "model": model,
        "analysis": {"status": int(analysis.status_code)},
        "design_chain": chain,
        "positive_reference_code_table": table,
        "phase_no_design": phase_before,
        "phase_with_design": phase_after,
        "negative_control": {
            **negative,
            "verdict": (
                "INCONCLUSIVE_BY_DESIGN" if same_as_positive else "DISCRIMINATES"
            ),
            "note": (
                "⚠️ 本端点对 `Argument` **完全不敏感**（空体 / 自名 / 照 CODE-TABLE / **伪**取值 "
                "四者答复同形）⇒ 「坏取值被拦」这一**形态**的阴性对照在本端点**结构上不可用**。"
                "如实记录，**不**硬凑假对照（**R157**）。"
                if same_as_positive
                else "取值确实有判别力。"
            ),
        },
        "state_control": {
            "criterion": "同一个请求体（空体 `{}`），**没**设计结果 ⇒ 0 行；**有** ⇒ >0 行",
            "rows_without_design": before_rows,
            "rows_with_design": after_rows,
            "valid": state_control,
            "note": (
                "这是本批**可用**的阴性对照：它证明输出**真的**跟着设计状态走，"
                "**不是**恒定答复（比「坏取值被拦」更贴本端点的语义 —— 本端点**不**吃 `Argument`）。"
            ),
        },
        "echo_control": {
            "criterion": (
                "结果取值**不得**等于手册 `json_schema` 的示例值 —— 否则是**静态回显**，"
                "不是计算（**R157** 的仪器有效性）"
            ),
            "manual_sample_elem": MANUAL_SAMPLE_ELEM,
            "manual_sample_rat": MANUAL_SAMPLE_RAT,
            "observed_fingerprint": fingerprint,
            "echoes_manual": echoes_manual,
            "valid": not_echo,
            "note": (
                "手册示例的 `vELEM.ELEM = 10`，而本模型**没有**单元 `10`（只有单元 `1`）"
                "⇒ 响应回 `ELEM=1` ⇒ **不是**回显。这条判据是本批**最硬**的一条："
                "它把「端点真的读了模型」与「端点回了手册样例」区分开。"
            ),
        },
        "effect": {
            "criterion": "结果**行数**（vSECT + vELEM 的元素个数）—— **不**是状态码（铁律 ⓪）",
            "rows_without_design": before_rows,
            "rows_with_design": after_rows,
            "best_candidate": winner["label"] if winner else None,
            "roots": winner["roots"] if winner else [],
            "evidence": (
                "① 无设计结果 ⇒ 0 行；③ 有设计结果 ⇒ >0 行 ∧ 取值**不**等于手册示例 ⇒ "
                "端点**真的**在读本模型的设计结果（**不是**静默 `200`、**不是** schema 回显）"
            ),
        },
        "sentinel": {"keys": list(SENTINEL), "before": before, "after": after, "unchanged": unchanged},
        "verdict": "PASSED" if passed else "FAILED",
        "note": (
            "⚠️ 本批**只**测形状 / 行为，**不**改任何 `availability`（收口与否由**用户裁决**）—— "
            "`app/**` 一行未改。副作用受控：**只**碰自建项目 + 只读 `GET`；照**R141** 的口径"
            "**逐字照**旗舰链的请求体，**不**臆造字段（**R151**）。"
        ),
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n⇒ 判定：{'✅ PASSED（端点**真的**产出设计结果行）' if passed else '❌ FAILED'}")
    print(f"   无设计结果 {before_rows} 行 → 有设计结果 {after_rows} 行 · "
          f"最佳候选 = {winner['label'] if winner else '（无）'}")
    print(f"   状态对照（可用）={state_control} · 防回显={not_echo}（echoes_manual={echoes_manual}）· "
          f"形状={shape_ok} · 哨兵一致={unchanged}")
    print(f"   伪取值与合法体同形={same_as_positive} ⇒ "
          f"「坏取值被拦」这一形态{'**不成立**' if same_as_positive else '成立'}")
    print(f"wrote {EVIDENCE.relative_to(REPO)}")
    return 0 if passed else 1


# ===== 离线自洽（`--check`，**零请求**）=====


def check_offline() -> int:
    """`--check`：证据齐备 + 判据自洽（**零请求**）。"""
    if not EVIDENCE.is_file():
        print(f"❌ 缺证据 {EVIDENCE.relative_to(REPO)}（先跑 --probe）")
        return 1
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    problems: list[str] = []
    if document.get("verdict") != "PASSED":
        problems.append(f"证据里的 verdict 应为 PASSED，实际 {document.get('verdict')!r}")
    effect = document.get("effect") or {}
    if effect.get("rows_without_design") != 0:
        problems.append("相 ①（无设计结果）行数应为 0（否则仪器**不**跟着设计状态走）")
    if not effect.get("rows_with_design"):
        problems.append("相 ③（有设计结果）行数应 > 0")
    if not (document.get("positive_reference_code_table") or {}).get("rows"):
        problems.append("阳性参照 `CODE-TABLE` 应 > 0 行（否则「设计结果存在」不成立）")
    # **可用的**阴性对照 = 状态对照（同一个请求体，没设计结果 ⇒ 0 行）
    if not (document.get("state_control") or {}).get("valid"):
        problems.append("状态对照不成立（同一个请求体在无/有设计结果下应 0 行 → >0 行）")
    # 防回显：取值**不得**等于手册示例
    if not (document.get("echo_control") or {}).get("valid"):
        problems.append("防回显对照不成立（取值等于手册 `json_schema` 示例 ⇒ 可能是静态回显）")
    if (document.get("echo_control") or {}).get("echoes_manual"):
        problems.append("响应取值与手册示例相同 ⇒ 效果判据不成立")
    # 「坏取值被拦」这一形态**如实记为不可用**（**不**得伪造成成立）
    negative = document.get("negative_control") or {}
    if negative.get("verdict") != "INCONCLUSIVE_BY_DESIGN":
        problems.append(
            f"伪取值的结论应为 INCONCLUSIVE_BY_DESIGN（本端点不校验 `Argument`），"
            f"实际 {negative.get('verdict')!r}"
        )
    if not (document.get("sentinel") or {}).get("unchanged"):
        problems.append("跑后哨兵与跑前不一致 ⇒ 有残留，结论不可用")
    if (document.get("contract_facts") or {}).get("request_examples"):
        problems.append("`request_examples` 应仍为空（手册**确实**没有请求示例 —— R165 的前提）")
    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    print(
        f"✅ 离线自洽：`{WRITE_PATH}` 在**有设计结果**时产出 "
        f"{effect['rows_with_design']} 行（根键 {effect.get('roots')}）、**无**设计结果时 0 行；"
        f"取值**不**等于手册示例（非回显）；伪取值形态**如实记为不可用**；哨兵 7 项一致"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="POST.STEELCODECHECK 的收口测量（R166 / P174）")
    parser.add_argument("--probe", action="store_true", help="真发请求（**有副作用**；默认只预演）")
    parser.add_argument("--check", action="store_true", help="离线自洽断言（零请求）")
    args = parser.parse_args(argv)
    if args.check:
        return check_offline()

    guard_paths()
    print(f"目标端点     ：{WRITE_PATH}（`availability: untested`）")
    print(f"阳性参照     ：{CODE_TABLE_PATH}（已 verified）")
    print(f"自建模型落点 ：{TARGET.relative_to(REPO)}")
    print(f"证据落点     ：{EVIDENCE.relative_to(REPO)}")
    print(f"候选体       ：{len((CANDIDATE_EMPTY, CANDIDATE_TABLE_TYPE, CANDIDATE_AS_CODE_TABLE))} 个"
          f" + 阴性对照 1 个")
    print("判据         ：结果**行数**（铁律 ⓪）+ 三段对照（无设计 / 有设计 / 阴性）")
    if not args.probe:
        print("\n（预演模式；加 --probe 才会真发请求 —— **有副作用**，需用户授权）")
        return 0
    return run_probe(REPO)


if __name__ == "__main__":
    raise SystemExit(main())
