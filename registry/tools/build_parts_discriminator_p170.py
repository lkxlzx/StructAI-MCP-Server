#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P170 · **A 组**：建一个**可判别**的自建模型，让 P169 判为「不可判别」的 **3** 个 `PARTS`
端点**能**被裁决（`docs/07` §16.1 **R163**）。

为什么需要它
------------
P169 在 `.tmp_p164c/p164c-concrete.mgbx`（**纯梁**模型）上判定这 3 个端点的**基线就是空块**
⇒ 无法区分「取值无效」与「模型无数据」（**如实留缺**）：

| 端点 | P169 的「需要什么」 | P170 的**实测更正** |
| --- | --- | --- |
| `POST.TABLE.RESULTANT_FORCES` / `_VBM` | 「需**板 / 实体**单元」 | ⚠️ **不准确**：手册 `db/VSEC` + `db/VBEM` 表明该表由**虚拟梁**（= **两个虚拟截面**）驱动 ⇒ 缺的是**虚拟截面定义**，**不是**板单元。本工具**两样都建**（板网格 + 虚拟截面）以**一次**消除两个疑点 |
| `DESIGN.STEEL.KDS-41-30-2022.TABLE` | 「需**钢结构设计**结果」 | ✅ 成立：需要跑一次 `CODE-ANAL`（`MEMB` 已配好） |

模型（**只**用手册示例取值，**不**臆造）
----------------------------------------
* 单位 `M / KN`；材料 = 手册 `db/MATL` 示例（`STEEL` / `EN05(S)` / `S450`）。
* **板网格** 6×4 ⇒ **35** 节点 / **24** 板单元（手册 `db/ELEM` 的 Plate 示例形状）；
  厚度 = 手册 `db/THIK` 示例（`TYPE: "VALUE"`，`T_IN: 0.1`）。
* **钢柱** 2 节点 / 1 梁单元（手册 `db/SECT` 的 **H 截面**示例取值逐字照抄）
  ⇒ 供 `DESIGN.STEEL` 的 `MEMB` 指派（`CODE-ANAL` 需要**梁**单元）。
* **虚拟截面 2 个**（手册 `db/VSEC` 示例形状）+ **虚拟梁 1 个**（`db/VBEM`）
  ⇒ 供 `RESULTANT_FORCES`。
* 边界：柱底固定 · 板 `x=0` 边固定；工况 `DL` + 自重 + 柱顶节点荷载；静力分析。
* **钢结构设计链**（`DSTL → DCO → DCTL → MEMB → LCOM-STEEL → CODE-ANAL`，
  顺序**逐字照** `app/infrastructure/adapters/midas/operations.py` 的 `DESIGN.STEEL`）。

本工具顺带实测到的**两条**原生事实（**勘误** `MIDAS_API_Online_Manual_勘误与补全_v1.0.md`）
---------------------------------------------------------------------------------------
* **E-04**：`db/ELEM` 的 **`STYPE: 0` 对 `PLATE` 非法** —— 带它 ⇒ 原生
  `400 发现错误，将数据 单元 输入给了单元号 N`（**整批回滚**，一个板都建不出来）；
  去掉 `STYPE`（或 `1` / `3`）⇒ `201` 且**真的建出**。**梁**单元带 `STYPE: 0` **正常**。
* **E-05**：`DESIGN.STEEL.KDS-41-30-2022.TABLE` 的 `PARTS` **声明**含 `All`（= 该端点的
  `PARTS.default`），实测 `All` ⇒ **空块**（与**伪**取值 `PartZ` **同形**）⇒ 声明可疑。

用法
----
    python registry/tools/build_parts_discriminator_p170.py            # 预演（零请求）
    python registry/tools/build_parts_discriminator_p170.py --build    # 真机（**写模型**）
    python registry/tools/build_parts_discriminator_p170.py --check    # 离线自洽（零请求）

⚠️ **有副作用**：`--build` 会 `NEW` + `SAVEAS` **新建并覆盖**本工具自己的产物
`.tmp_p164c/p170-discriminator.mgbx`（在 `.gitignore` 内），并**写模型**。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Final

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
"""仓库根目录（`registry/tools/` 的上两级）。"""

TARGET: Final[pathlib.Path] = REPO / ".tmp_p164c" / "p170-discriminator.mgbx"
"""自建模型落点（**只**碰它；`.gitignore` 内）。"""

EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "parts_discriminator_p170.json"
"""证据落点（**不含**凭据、**不含**响应原文）。"""

COLS: Final[int] = 6
ROWS: Final[int] = 4
PLATE_T: Final[float] = 0.1
BEAM_TOP: Final[float] = 6.0
BEAM_X: Final[float] = 20.0
NODE_BASE: Final[int] = 36
NODE_TOP: Final[int] = 37
ELEM_BEAM: Final[int] = 25
SECT_BEAM: Final[int] = 1
THIK_PLATE: Final[int] = 2
MATL: Final[int] = 1
PAD: Final[int] = 8
"""⚠️ 手册 `db/ELEM` 的**板示例**把 `NODE` **补齐到 8** 项（`[1,2,3,4,0,0,0,0]`）。
⚠️ **实测（本工具的隔离探针）**：`NODE` 补零与否**都行**；**`STYPE: 0` 对 `PLATE` 非法**。"""

BEAM_ELEM: Final[int] = ELEM_BEAM
LOAD_CASE: Final[str] = "DL"
DGN_CODE: Final[str] = "KDS 41 30 : 2022"
STEEL_TOKEN: Final[str] = "STEELMEMBERDESIGNFORCES"
"""⚠️ 本工具的目标端点**不在** `NATIVE_CRASH_ENDPOINTS`（**R154**）—— `guard_paths()` 会自检。"""


def _node_id(row: int, col: int) -> int:
    """板网格节点编号（**连续** 1..35，行主序）。"""
    return row * (COLS + 1) + col + 1


def _elem_id(row: int, col: int) -> int:
    """板单元编号（**连续** 1..24，行主序）。"""
    return row * COLS + col + 1


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


def guard_paths() -> None:
    """发请求**之前**的自检（`app/**` 的崩溃族，**R154**）。"""
    sys.path.insert(0, str(REPO))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        NATIVE_CRASH_ENDPOINTS,
        guard_native_crash_path,
    )

    targets = (
        "/DB/NODE", "/DB/ELEM", "/DB/THIK", "/DB/VSEC", "/DB/VBEM",
        "/DB/LCOM-STEEL", "/DESIGN/STEEL/KDS-41-30-2022/CODE-ANAL",
    )
    crash = {"/" + str(item).replace(".", "/") for item in NATIVE_CRASH_ENDPOINTS}
    hit = sorted(set(targets) & crash)
    if hit:
        raise SystemExit(f"❌ {hit} 在崩溃族里（**R154**）⇒ **拒绝运行**")
    guard_native_crash_path("/POST/TABLE")  # 真在崩族里 ⇒ 这里就会抛（**零请求**）
    print(f"闸门自检：目标 {len(targets)} 个端点 ∩ 崩溃族（{len(crash)} 条）= ∅ · /POST/TABLE 放行")


# ===== 请求体（**只**用手册示例取值）=====


def model_bodies() -> list[dict[str, Any]]:
    """建模的逐请求（标签 / 方法 / URI / 体 / 读回端点）。"""
    nodes: dict[str, Any] = {
        str(_node_id(r, c)): {"X": float(c), "Y": float(r), "Z": 0.0}
        for r in range(ROWS + 1)
        for c in range(COLS + 1)
    }
    nodes[str(NODE_BASE)] = {"X": BEAM_X, "Y": 0.0, "Z": 0.0}
    nodes[str(NODE_TOP)] = {"X": BEAM_X, "Y": 0.0, "Z": BEAM_TOP}

    elems: dict[str, Any] = {}
    for r in range(ROWS):
        for c in range(COLS):
            quad = [_node_id(r, c), _node_id(r, c + 1), _node_id(r + 1, c + 1), _node_id(r + 1, c)]
            elems[str(_elem_id(r, c))] = {
                "TYPE": "PLATE",
                "MATL": MATL,
                "SECT": THIK_PLATE,
                "NODE": quad + [0] * (PAD - len(quad)),
                "ANGLE": 0,
                # ⚠️ **不带 `STYPE`**：`STYPE: 0` 对 `PLATE` 非法（见模块 docstring 的 E-04）
            }
    elems[str(ELEM_BEAM)] = {
        "TYPE": "BEAM",
        "MATL": MATL,
        "SECT": SECT_BEAM,
        "NODE": [NODE_BASE, NODE_TOP] + [0] * (PAD - 2),
        "ANGLE": 0,
        "STYPE": 0,  # 梁单元带 `STYPE: 0` 正常（与 `PLATE` 相反）
    }

    cons: dict[str, Any] = {str(NODE_BASE): {"ITEMS": [{"ID": 1, "CONSTRAINT": "1111000"}]}}
    for r in range(ROWS + 1):
        cons[str(_node_id(r, 0))] = {"ITEMS": [{"ID": 1, "CONSTRAINT": "1111111"}]}

    def vsec(name: str, row: int) -> dict[str, Any]:
        return {
            "NAME": name,
            "CENT_CALC_TYPE": 0,
            "CEN_PT_X": COLS / 2.0,
            "CEN_PT_Y": row + 0.5,
            "CEN_PT_Z": 0.0,
            "NORMAL_X": 0.0,
            "NORMAL_Y": 0.0,
            "NORMAL_Z": 1.0,
            "NODE_LIST": [_node_id(row, c) for c in range(COLS + 1)]
            + [_node_id(row + 1, c) for c in range(COLS + 1)],
            "ELEM_LIST": [_elem_id(row, c) for c in range(COLS)],
        }

    return [
        {"label": "单位 M/KN", "method": "PUT", "uri": "/db/unit",
         "body": {"Assign": {"1": {"DIST": "M", "FORCE": "KN"}}}, "root": ""},
        {"label": "材料 STEEL（手册 db/MATL 示例）", "method": "POST", "uri": "/db/matl",
         "root": "MATL", "body": {"Assign": {str(MATL): {
             "TYPE": "STEEL", "NAME": "DB_Steel", "HE_SPEC": 0, "HE_COND": 0, "PLMT": 0,
             "P_NAME": "", "bMASS_DENS": False, "DAMP_RAT": 0.02,
             "PARAM": [{"P_TYPE": 1, "STANDARD": "EN05(S)", "CODE": "", "DB": "S450",
                        "bELAST": False, "ELAST": 210000000}]}}}},
        {"label": "厚度 VALUE 0.1（手册 db/THIK 示例）", "method": "POST", "uri": "/db/thik",
         "root": "THIK", "body": {"Assign": {str(THIK_PLATE): {
             "NAME": "2", "TYPE": "VALUE", "bINOUT": False, "T_IN": PLATE_T,
             "T_OUT": 0, "O_VALUE": 0}}}},
        {"label": "截面 H（手册 db/SECT 示例取值逐字）", "method": "POST", "uri": "/db/sect",
         "root": "SECT", "body": {"Assign": {str(SECT_BEAM): {
             "SECTTYPE": "DBUSER", "SECT_NAME": "DB-H",
             "SECT_BEFORE": {"OFFSET_PT": "CC", "OFFSET_CENTER": 0, "USER_OFFSET_REF": 0,
                             "HORZ_OFFSET_OPT": 0, "USERDEF_OFFSET_YI": 0,
                             "VERT_OFFSET_OPT": 0, "USERDEF_OFFSET_ZI": 0,
                             "USE_SHEAR_DEFORM": True, "USE_WARPING_EFFECT": False,
                             "SHAPE": "H", "DATATYPE": 2,
                             "SECT_I": {"vSIZE": [1, 0.3, 0.05, 0.03, 0.3, 0.035, 0.03, 0.02, 0, 0]}}}}}},
        {"label": f"节点 {len(nodes)} 个", "method": "POST", "uri": "/db/node",
         "body": {"Assign": nodes}, "root": "NODE"},
        {"label": f"单元 {len(elems)} 个（{ROWS * COLS} 板 + 1 梁）", "method": "POST",
         "uri": "/db/elem", "body": {"Assign": elems}, "root": "ELEM"},
        {"label": f"边界 {len(cons)} 个", "method": "POST", "uri": "/db/cons",
         "body": {"Assign": cons}, "root": "CONS"},
        {"label": "工况 DL", "method": "POST", "uri": "/db/stld", "root": "STLD",
         "body": {"Assign": {"1": {"NAME": LOAD_CASE, "TYPE": "USER", "DESC": "Dead Load"}}}},
        {"label": "自重 FV=[0,0,-1]", "method": "POST", "uri": "/db/bodf", "root": "BODF",
         "body": {"Assign": {"1": {"LCNAME": LOAD_CASE, "FV": [0, 0, -1]}}}},
        {"label": f"柱顶节点荷载（节点 {NODE_TOP}）", "method": "POST", "uri": "/db/cnld",
         "root": "CNLD", "body": {"Assign": {str(NODE_TOP): {"ITEMS": [
             {"ID": 1, "LCNAME": LOAD_CASE, "GROUP_NAME": "", "FX": 0, "FY": 0, "FZ": -500}]}}}},
        {"label": "虚拟截面 1（板带 y∈[1,2]）", "method": "POST", "uri": "/db/vsec",
         "root": "VSEC", "body": {"Assign": {"1": vsec("P170_Strip1", 1)}}},
        {"label": "虚拟截面 2（板带 y∈[2,3]）", "method": "POST", "uri": "/db/vsec",
         "root": "VSEC", "body": {"Assign": {"2": vsec("P170_Strip2", 2)}}},
        {"label": "虚拟梁 1 = VSEC1 + VSEC2", "method": "POST", "uri": "/db/vbem",
         "root": "VBEM", "body": {"Assign": {"1": {"VSEC1": 1, "VSEC2": 2}}}},
    ]


def design_bodies() -> list[dict[str, Any]]:
    """钢结构设计链（顺序**逐字照** `operations.py` 的 `DESIGN.STEEL`）。"""
    return [
        {"label": "① 设计规范 DSTL", "method": "PUT", "uri": "/DESIGN/STEEL/DSTL",
         "body": {"Assign": {"DGNCODE": DGN_CODE}}},
        {"label": "② 设计选项 DCO", "method": "PUT",
         "uri": "/DESIGN/STEEL/KDS-41-30-2022/DCO", "body": {"Assign": {"1": {
             "DGNCODE": DGN_CODE, "LAT_BRACE": False, "DEFL_CHK": True, "SEISMIC": False,
             "COMB_RATIO": 0, "SEIS_SYS": "Special Moment Frames", "COL_WEAK": True,
             "UNDGR_LD": True}}}},
        {"label": "③ 框架控制 DCTL", "method": "PUT",
         "uri": "/DESIGN/STEEL/KDS-41-30-2022/DCTL", "body": {"Assign": {"1": {
             "FRAMEX": "Braced Non-sway", "FRAMEY": "Braced Non-sway",
             "bAUTOKF": False, "DT": "3D"}}}},
        {"label": "④ 构件指派 MEMB", "method": "PUT",
         "uri": "/DESIGN/STEEL/KDS-41-30-2022/MEMB",
         "body": {"Assign": {"1": {"AELEM": [BEAM_ELEM], "bREVERSE": False}}}},
        {"label": "⑤ 荷载组合 LCOM-STEEL", "method": "POST", "uri": "/DB/LCOM-STEEL",
         "body": {"Assign": {"1": {"NAME": "sLCB1", "ACTIVE": "ACTIVE", "iTYPE": 0, "DESC": "",
                                   "vCOMB": [{"ANAL": "ST", "LCNAME": LOAD_CASE, "FACTOR": 1.0}]}}}},
        {"label": "⑥ 设计执行 CODE-ANAL", "method": "POST",
         "uri": "/DESIGN/STEEL/KDS-41-30-2022/CODE-ANAL",
         "body": {"Argument": {"PERFORM_TYPE": "ELEMS", "ELEMS": {"KEYS": [BEAM_ELEM]}}}},
    ]


def _count(client: Any, root: str) -> int | None:
    """读回条目数（`None` = 读不回）。"""
    if not root:
        return None
    try:
        payload = client.get(f"/DB/{root}").json()
    except Exception:  # noqa: BLE001 - 读不回如实留 None
        return None
    block = payload.get(root) if isinstance(payload, dict) else None
    if isinstance(block, dict) and "ITEMS" in block:
        return len(block["ITEMS"])
    return len(block) if isinstance(block, dict) else None


def _table_rows(client: Any, token: str) -> int | None:
    """`POST /POST/TABLE {TABLE_TYPE}` 的**数据行数**（`None` = 空块 / 读不回）。"""
    response = client.post("/POST/TABLE", json={"Argument": {"TABLE_TYPE": token}})
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict) or not payload:
        return None
    block = payload[next(iter(payload))]
    data = block.get("DATA") if isinstance(block, dict) else None
    return len(data) if isinstance(data, list) else None


# ===== 真机 =====


def run_build(repo: pathlib.Path) -> int:
    """真机受控测量（`--build`）：建模型 + 钢结构设计 + 逐表行数判据。"""
    guard_paths()
    base, key = _load_credentials()

    import httpx  # noqa: PLC0415

    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=180.0) as client:
        health = int(client.get("/DB/NODE").status_code)
        print(f"实例 {base} · 模型 {TARGET.name} · 跑前健康检查 /DB/NODE → {health}")
        if health != 200:
            print("🛑 实例不可达 ⇒ 按纪律**不盲写**，中止")
            return 2

        if TARGET.exists():
            print(f"⚠️ 覆盖本工具自己的产物：{TARGET.name}（{TARGET.stat().st_size} 字节）")
        client.post("/DOC/NEW", json={"Argument": {}})
        client.post("/DOC/SAVEAS", json={"Argument": str(TARGET)})
        landed = TARGET.exists() and TARGET.stat().st_size > 0
        print(f"① DOC.NEW + SAVEAS ⇒ **文件落盘**：{landed}（exists={TARGET.exists()}）")
        if not landed:
            print("🛑 新模型**未**落盘 ⇒ 中止（不写一个没有归属的模型）")
            return 2

        print("\n② 建模（逐步**读回验效果**）：")
        model: list[dict[str, Any]] = []
        for index, step in enumerate(model_bodies(), 1):
            response = client.request(step["method"], step["uri"], json=step["body"])
            want = len(step["body"].get("Assign") or {})
            got = _count(client, str(step["root"]))
            ok = (got is not None and got >= want) if step["root"] else response.status_code < 400
            print(f"  [{index:2d}] {step['method']:5s} {step['uri']:12s} → {response.status_code}  "
                  f"读回 {step['root'] or '-'}={got}（期望 ≥{want}）{'✅' if ok else '❌'}")
            model.append({"label": step["label"], "uri": step["uri"],
                          "status": int(response.status_code), "readback": got,
                          "expected": want, "ok": ok})
            if index % 8 == 0:
                client.get("/DB/NODE")

        print("\n③ 静力分析：")
        response = client.post("/DOC/ANAL", json={"Argument": {"TYPE": "STATIC"}})
        print(f"  POST /DOC/ANAL → {response.status_code}")

        print("\n④ 钢结构设计链（**逐字照** `DESIGN.STEEL` 编排）：")
        design: list[dict[str, Any]] = []
        for step in design_bodies():
            response = client.request(step["method"], step["uri"], json=step["body"])
            print(f"  {step['label']} → {response.status_code}  {response.text[:80]}")
            design.append({"label": step["label"], "uri": step["uri"],
                           "status": int(response.status_code), "ok": response.status_code < 400})

        client.post("/DOC/SAVE", json={"Argument": {}})
        size = TARGET.stat().st_size if TARGET.exists() else 0
        print(f"\n⑤ DOC.SAVE ⇒ 文件 {size} 字节")

        print("\n⑥ 效果判据（**结果表行数**，铁律 ⓪）：")
        tokens = ["RESULTANT_FORCES", "RESULTANT_FORCESVBM", "BEAMFORCE", STEEL_TOKEN]
        rows = {token: _table_rows(client, token) for token in tokens}
        for token, count in rows.items():
            print(f"  {token:26s} rows={count}")

        sentinel = {
            root: _count(client, root)
            for root in ("NODE", "ELEM", "MATL", "SECT", "THIK", "VSEC", "VBEM")
        }
        print(f"\n⑦ 跑后哨兵：{sentinel}")

    # ⚠️ **DSTL** 实测回 `400 Wrong Field`（**已知**：`docs/nxsdk_review/evidence/02_实测发现_中文摘要.md`
    #    记 Civil 上同样如此；Gen NX 亦同）。它**不**阻塞设计链 —— `DCO` 的体**自带** `DGNCODE`
    #    ⇒ 设计**真的**跑出结果（`STEELMEMBERDESIGNFORCES` 有数据行）。本工具**如实记录**它，
    #    **不**把它算作本批的失败（也**不**改 `app/**` —— 本批不改核心）。
    design_blocking = [item for item in design if not item["uri"].endswith("/DSTL")]
    passed = (
        all(item["ok"] for item in model)
        and all(item["ok"] for item in design_blocking)
        and all(count for count in rows.values())
    )
    payload = {
        "phase": "discriminator",
        "instance_alias": "gen-local",
        "probed_at": "2026-10-15",
        "project": str(TARGET.relative_to(REPO)).replace("\\", "/"),
        "model": model,
        "design": design,
        "table_rows": rows,
        "sentinel": sentinel,
        "verdict": "PASSED" if passed else "FAILED",
        "note": (
            "A 组：建一个**可判别**的模型（板网格 + 虚拟截面/虚拟梁 + 钢结构设计结果）⇒ "
            "让 P169 判为「不可判别」的 **3** 个 `PARTS` 端点能被裁决。"
            "判据 = **效果**（`POST.TABLE` 的**数据行数** > 0），**不是**状态码。"
            "⚠️ **E-04**：`db/ELEM` 的 `STYPE: 0` 对 `PLATE` 非法（整批 `400` 回滚）；"
            "⚠️ **E-05**：`DESIGN.STEEL.KDS-41-30-2022.TABLE` 的 `PARTS` 声明含 `All`，实测**空块**；"
            "⚠️ **E-06**：`DESIGN.STEEL.DSTL` 实测 `400 Wrong Field`（**已知**：Civil 上同样如此），"
            "**不**阻塞设计链 —— `DCO` 的体**自带** `DGNCODE` ⇒ 设计**真的**出结果。"
        ),
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"⇒ 判定：{'✅ PASSED' if passed else '❌ FAILED'}")
    print(f"wrote {EVIDENCE.relative_to(REPO)}")
    return 0 if passed else 1


# ===== 离线自洽（`--check`，**零请求**）=====


def check_offline(repo: pathlib.Path) -> int:
    """`--check`：证据齐备 + 判据全真 + 模型构成可复算。"""
    if not EVIDENCE.is_file():
        print(f"❌ 缺证据 {EVIDENCE.relative_to(REPO)}（先跑 --build）")
        return 1
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    problems: list[str] = []
    if document.get("verdict") != "PASSED":
        problems.append(f"证据里的 verdict 应为 PASSED，实际 {document.get('verdict')!r}")
    rows = document.get("table_rows") or {}
    # **可判别化的判据** = 三个原本「不可判别」的表**都有数据行**
    for token in ("RESULTANT_FORCES", "RESULTANT_FORCESVBM", STEEL_TOKEN):
        if not rows.get(token):
            problems.append(f"{token} 的基线仍是空块 ⇒ **未**实现可判别化")
    # 模型构成可复算
    model = document.get("model") or []
    by_uri = {str(item["uri"]): item for item in model}
    for uri in ("/db/node", "/db/elem", "/db/thik", "/db/vsec", "/db/vbem"):
        if uri not in by_uri or not by_uri[uri].get("ok"):
            problems.append(f"{uri} 的写入**未**通过读回验证")
    if by_uri.get("/db/elem", {}).get("expected") != ROWS * COLS + 1:
        problems.append("`/db/elem` 的期望单元数不是「板网格 + 1 根梁」")
    # 设计链的**顺序**必须与 `operations.py` 的 `DESIGN.STEEL` 一致（R141）
    order = [str(item["uri"]) for item in (document.get("design") or [])]
    expected_order = [
        "/DESIGN/STEEL/DSTL",
        "/DESIGN/STEEL/KDS-41-30-2022/DCO",
        "/DESIGN/STEEL/KDS-41-30-2022/DCTL",
        "/DESIGN/STEEL/KDS-41-30-2022/MEMB",
        "/DB/LCOM-STEEL",
        "/DESIGN/STEEL/KDS-41-30-2022/CODE-ANAL",
    ]
    if order != expected_order:
        problems.append(f"设计链顺序与 `DESIGN.STEEL` 编排不一致：{order}")

    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    print(
        f"✅ 离线自洽：**{len(model)}** 步建模 + **{len(order)}** 步设计链 · "
        f"`RESULTANT_FORCES` {rows['RESULTANT_FORCES']} 行 · "
        f"`RESULTANT_FORCESVBM` {rows['RESULTANT_FORCESVBM']} 行 · "
        f"`{STEEL_TOKEN}` {rows[STEEL_TOKEN]} 行 ⇒ **3** 个原「不可判别」端点**可裁决**（R163）"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="建可判别模型（P170 · R163）")
    parser.add_argument("--build", action="store_true", help="真机建模型（默认只预演）")
    parser.add_argument("--check", action="store_true", help="离线自洽断言（零请求）")
    args = parser.parse_args(argv)
    if args.check:
        return check_offline(REPO)

    guard_paths()
    print(f"目标模型：{TARGET.relative_to(REPO)}")
    for step in model_bodies():
        print(f"  {step['method']:5s} {step['uri']:12s} {step['label']:40s} "
              f"条目={len(step['body'].get('Assign') or {})}")
    print("  -- 静力分析 POST /DOC/ANAL")
    for step in design_bodies():
        print(f"  {step['method']:5s} {step['uri']:46s} {step['label']}")
    if not args.build:
        print("\n（预演；加 --build 才真发 —— ⚠️ **会写模型**）")
        return 0
    print()
    return run_build(REPO)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
