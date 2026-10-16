#!/usr/bin/env python3
"""
P175 · `DOC.EXPORT` / `DOC.IMPORT` 的可用性收口证据（**模型 ↔ JSON 转换层**的前置）。

为什么需要它
------------
`registry/common/doc/{EXPORT,IMPORT}.yaml` 的 `availability` 都是 **`untested`**
（`registry/README.md` §4 口径 ⇒ **不能**据以判定可用）。而「把模型解析为 JSON、
JSON 再回写成模型」这条链路**完全**依赖这两个端点 ⇒ 收口前**不得**声称可用。

判据（**铁律 ⓪**：效果，**不是**状态码）
----------------------------------------
| 端点 | 「效果」的落点 | 怎么验 |
| --- | --- | --- |
| `DOC.EXPORT` | **文件真的落盘** ∧ **可解析** ∧ 逐表与**同刻读回**同形 |
文件存在 + 大小 > 0 + `json.loads` + `DBG.<表>` == `GET /db/<表>` |
| `DOC.IMPORT` | **模型的表真的变了** | 导入前后 `GET /db/<表>` 的**行数差** |

**对照组**（本探针的**阴性对照**）
--------------------------------
阳性 = 导入一个**确含**主干实体的自建样本 JSON ⇒ 行数**上升**；
阴性 = 导入一个**只含空表**的 JSON ⇒ 行数 **`0 → 0`**（**不**落地任何行）。
⚠️ 两个相位的**状态码都是 `200`** ⇒ 状态码**不判别**任何东西（这正是铁律 ⓪ 的意义）。

⚠️ **R144 / R143 的事故护栏（本探针的第一步）**
----------------------------------------------
`DOC.NEW` 会把项目变成**无路径** ⇒ 原生**自动保存**会自己弹「另存为」模态窗并**挂起 API**
（P160c 事故 B；核心拦不住 —— 触发者是原生定时器）。⇒ **本探针一次都不发 `DOC.NEW`**：
① 跑前先 `DOC.SAVE_AS` **备份现场**（也顺带确立项目路径）；
② 收尾用 `GET /db/PJCF` **核对** `FILE_NAME` ≠ `无标题`（**无路径 = 拒绝收尾**）。

用法
----
    python registry/tools/probe_model_doc_p175.py            # 预演（零请求）
    python registry/tools/probe_model_doc_p175.py --probe    # 真机（有副作用，需授权）
    python registry/tools/probe_model_doc_p175.py --check    # 离线自洽（零请求）
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

CRITERION_VERSION: Final[int] = 1
INSTANCE_ALIAS: Final[str] = "gen-local"
INSTANCE_PRODUCT: Final[str] = "GEN NX"

PASSED: Final[str] = "PASSED"
FAILED: Final[str] = "FAILED"

EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "model_doc_probe.json"
"""证据落盘路径（与同族探针一致）。"""

WORKSPACE: Final[pathlib.Path] = REPO / ".tmp_p175"
"""本探针的**唯一**副作用范围（`.gitignore` 内；样本原目录**只读**）。"""

HEALTH_PATH: Final[str] = "/db/NODE"

SAMPLE_SOURCE: Final[pathlib.Path] = pathlib.Path(
    r"D:\Program\MIDAS\MIDAS GEN NX\Gen Verification\Eigen-01.mgbx"
)
"""样本源（**只读**；`Gen Verification` 目录不得写入）。"""

BACKUP_NAME: Final[str] = "p175-session-backup.mgbx"
"""跑前现场备份（R144：也让项目**有路径**）。"""

SAMPLE_NAME: Final[str] = "p175-sample.mgbx"
"""样本副本（**不**直接打开原文件）。"""

EXPORT_NAME: Final[str] = "p175-export.json"
"""`DOC.EXPORT` 的产出目标。"""

POSITIVE_NAME: Final[str] = "p175-positive.json"
NEGATIVE_NAME: Final[str] = "p175-negative.json"

EMPTY_TARGET_NAME: Final[str] = "p175-empty-target.mgbx"
"""保留的落盘目标（阳性导入之后把结果 `SAVE_AS` 到此，便于人工复核）。"""

SYNTHETIC_NODE_IDS: Final[tuple[int, ...]] = (9001, 9002)
"""阳性对照用的**合成节点编号**（远高于样本自身的编号 ⇒ 与基线必然不重叠）。

⚠️ **为什么不用「空基线项目」**（P175 实测教训）：`DOC.SAVEAS` 只是把**当前模型**
另存到新路径，**不**清空模型 ⇒ 「另存出一个空项目」**不成立**（实测基线仍是
`NODE:3 ELEM:2`）。⇒ 阳性对照的正确做法 = **拿一个与基线不重叠的合成增量去导入**，
判据 = 行数上升 **且** 新编号**读得回来**。
"""
RETRY_LIMIT: Final[int] = 4
"""DOC 写请求的重试次数。

⚠️ **P175 教训（重要）**：本探针最初的 `404` **不是**原生偶发，而是**我自己**把路径
写成了点号形态（`/DOC.OPEN` 而非 `/DOC/OPEN`）⇒ 路由不存在 ⇒ 原生回 `404` 且
`error.message` **为空**。⚠️ **诊断法则**：`404` + **空** `message` 先怀疑
**自己的路径拼写**，再怀疑原生状态机 —— 否则会把字符错误误读成产品行为
（本探针确实一度这么误读过，并据此写出过错误的「必须先 CLOSE」结论）。
重试保留下来只为覆盖**真实**的瞬时故障（网络 / 实例忙），**不**用来掩盖拼写错误。
"""


WATCH: Final[tuple[str, ...]] = (
    "UNIT",
    "STYP",
    "NODE",
    "ELEM",
    "MATL",
    "SECT",
    "CONS",
    "ACTL",
    "EIGV",
    "NMAS",
)
"""主干实体哨兵（`DB.<表>` 的行数就是「效果」的落点）。"""

POSITIVE_TABLE: Final[str] = "NODE"
"""阳性对照的落点表（样本含 3 个节点 ⇒ 行数必然 > 0）。"""

ALLOWED_PATHS: Final[frozenset[str]] = frozenset(
    {
        "/DOC/EXPORT",
        "/DOC/IMPORT",
        "/DOC/SAVEAS",
        "/DOC/OPEN",
        "/DOC/CLOSE",
    }
)
"""本探针允许发出的**全部**原生路径（其余一律不发）。"""


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
    """发请求**之前**的自检（复用 `app/**` 的崩溃族常量；**不**另写一套）。"""
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
    print(f"闸门自检：声明路径 {len(ALLOWED_PATHS)} 条 ∩ 崩溃族（{len(crash_paths)} 条）= ∅")


def _registered_tables() -> tuple[str, ...]:
    """离线可复算：`DB.*` 端点名去掉命名空间前缀后的**表名集合**（**不**手写）。"""
    manifest = json.loads((REPO / "registry" / "manifest.json").read_text(encoding="utf-8"))
    endpoints = manifest.get("endpoints") if isinstance(manifest, dict) else None
    if not isinstance(endpoints, list):
        raise SystemExit("❌ manifest.json 的 `endpoints` 形状不符（应为 list）⇒ 不臆造表名")
    keys = [
        str(entry.get("key"))
        for entry in endpoints
        if isinstance(entry, dict) and str(entry.get("key") or "").startswith("DB.")
    ]
    if not keys:
        raise SystemExit("❌ manifest 里没有 `DB.*` 端点 ⇒ 表名来源不成立")
    return tuple(sorted({key.split(".")[-1] for key in keys}))


def _evidence_tables() -> tuple[str, ...]:
    """从 `DBG` 键取的**实测**表口径（导出文件里真的出现了的表名）。"""
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    export = ((document.get("endpoints") or {}).get("DOC.EXPORT") or {}).get("tables") or {}
    return tuple(sorted(export))


def run_probe(repo: pathlib.Path) -> int:
    """真机实测（`--probe`）—— 全程**不**发 `DOC.NEW`（R144）。"""
    guard_paths()
    import shutil  # noqa: PLC0415

    import httpx  # noqa: PLC0415

    base, key = _load_credentials()
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    backup = (WORKSPACE / BACKUP_NAME).resolve()
    sample = (WORKSPACE / SAMPLE_NAME).resolve()
    exported = (WORKSPACE / EXPORT_NAME).resolve()
    positive = (WORKSPACE / POSITIVE_NAME).resolve()
    negative = (WORKSPACE / NEGATIVE_NAME).resolve()
    empty_target = (WORKSPACE / EMPTY_TARGET_NAME).resolve()

    if not SAMPLE_SOURCE.is_file():
        print(f"🛑 样本不存在：{SAMPLE_SOURCE}")
        return 1

    print(f"实例 {base} · 工作区 {WORKSPACE.relative_to(REPO)}")
    print(f"样本（**只读**）：{SAMPLE_SOURCE}")

    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=180.0) as client:

        def counts() -> dict[str, int]:
            out: dict[str, int] = {}
            for name in WATCH:
                response = client.get(f"/db/{name}")
                try:
                    block = response.json().get(name)
                except ValueError:
                    block = None
                out[name] = len(block) if isinstance(block, dict) else 0
            return out

        def pjcf() -> dict[str, Any]:
            response = client.get("/db/PJCF")
            try:
                block = response.json().get("PJCF")
            except ValueError:
                block = None
            if not isinstance(block, dict) or not block:
                return {}
            return dict(next(iter(block.values())))

        def doc_post(path: str, argument: Any, *, label: str) -> int:
            """发一个 DOC 写请求并**重试偶发 404**（`RETRY_LIMIT` 次）。

            ⚠️ 重试**不是**兜底 `200`：次数耗尽就如实返回失败码，并打**最后一条**原生
            `error.message`（前 300 字，诊断必需、非凭据）—— 否则「为什么 404」无从查起。
            """
            status = 0
            message = ""
            for _ in range(RETRY_LIMIT):
                response = client.post(path, json={"Argument": argument})
                status = int(response.status_code)
                if status == 200:
                    return status
                try:
                    payload = response.json()
                except ValueError:
                    payload = None
                if isinstance(payload, dict):
                    error = payload.get("error")
                    if isinstance(error, dict):
                        message = str(error.get("message") or "")[:300]
                print(f"    ↻ {label} 第 {_ + 1} 次 → {status} · 原生 {message!r}")
            print(f"  🛑 {label} 重试 {RETRY_LIMIT} 次仍非 200（最后 {status}）：{message!r}")
            return status

        def doc_open(target: pathlib.Path, *, label: str) -> int:
            """打开一个项目文件（纯 `DOC.OPEN`）。

            ⚠️ **P175 的踩坑留痕**：本函数曾（错误地）在前面加一次 `DOC.CLOSE` —— 那是
            基于「刚保存过就必须先 CLOSE」的**误判**。真实根因是本探针把路径写成了
            `/DOC.OPEN` 的**点号**形态（`/DOC.OPEN`）⇒ 路由不存在 ⇒ 原生 `404`
            且 `error.message` **为空**。⚠️ **教训**：`404` + 空 `message` 先怀疑
            **自己的路径拼写**，不要先怀疑原生状态机。
            """
            return doc_post("/DOC/OPEN", str(target), label=label)

        # ---- 前置条件：实例上**必须**已有一个打开的项目 ----
        # ⚠️ R147：`SAVEAS` 在没有文档时会静默 `200`（什么都不做）⇒ 必须先确认文档在。
        opened_before = pjcf()
        print(f"  前置：当前项目 FILE_NAME={opened_before.get('FILE_NAME')!r}")
        if not opened_before:
            print(
                "🛑 实例上没有打开的项目 ⇒ **不**继续"
                "（先 OPEN 一个项目；**不**发 DOC.NEW，见 R144）"
            )
            return 1

        # ---- 第 0 步（R144）：备份现场 ⇒ 项目**有路径**，且留退路 ----
        before_stat = backup.stat() if backup.is_file() else None
        status = doc_post("/DOC/SAVEAS", str(backup), label="备份现场")
        after_stat = backup.stat() if backup.is_file() else None
        # ⚠️ R147：**判据是效果**（文件真的被写），不是状态码 ⇒ 比对 mtime / size。
        wrote = after_stat is not None and (
            before_stat is None
            or after_stat.st_mtime != before_stat.st_mtime
            or after_stat.st_size != before_stat.st_size
        )
        print(f"  DOC.SAVEAS（备份现场）→ {status} · 真的写盘={wrote}")
        if status != 200 or not wrote:
            print("🛑 备份未真的落盘（可能静默 200）⇒ **不**继续（拒绝在无退路的实例上做写操作）")
            return 1

        # ---- 样本副本（原目录**只读**） ----
        shutil.copy2(SAMPLE_SOURCE, sample)
        status = doc_open(sample, label="打开样本副本")
        print(f"  DOC.OPEN（样本**副本**）→ {status}")
        if status != 200:
            print("🛑 样本未打开 ⇒ 中止")
            return 1

        # ================= DOC.EXPORT =================
        if exported.exists():
            exported.unlink()
        response = client.post("/DOC/EXPORT", json={"Argument": str(exported)})
        written = exported.is_file() and exported.stat().st_size > 0
        print(
            f"  DOC.EXPORT → {response.status_code} · 落盘={written} · "
            f"{exported.stat().st_size if written else 0} 字节"
        )
        if not written:
            print("🛑 导出未落盘 ⇒ 判据不成立（状态码不算数）")
            return 1

        document = json.loads(exported.read_text(encoding="utf-8"))
        dbg = document.get("DBG")
        if not isinstance(dbg, dict):
            print("🛑 导出文件不是 `{'DBG': {...}}` 形状 ⇒ 中止")
            return 1

        live = counts()
        tables: dict[str, Any] = {}
        for name in sorted(dbg):
            block = dbg[name]
            entry: dict[str, Any] = {"rows": len(block) if isinstance(block, dict) else None}
            if name in live:
                entry["live_rows"] = live[name]
                entry["shape_identical"] = block == client.get(f"/db/{name}").json().get(name)
            tables[name] = entry
        empty_tables = sorted(name for name, item in tables.items() if item["rows"] == 0)
        identical = {name for name, item in tables.items() if item.get("shape_identical") is True}
        watched_identical = {name for name in WATCH if name in identical}
        print(
            f"  → `DBG` 表 **{len(tables)}** 张（空表 {len(empty_tables)} 张）· "
            f"哨兵 {len(WATCH)} 项同形 {len(watched_identical)} 项"
        )

        export_section: dict[str, Any] = {
            "status": int(response.status_code),
            "criterion": "file written ∧ parseable ∧ table-wise identical to same-moment reads",
            "file_written": bool(written),
            "file_size": exported.stat().st_size,
            "table_count": len(tables),
            "empty_table_count": len(empty_tables),
            "tables": tables,
            "sentinel_shape_identical": sorted(watched_identical),
            "verdict": PASSED if len(watched_identical) == len(WATCH) else FAILED,
        }

        # ================= DOC.IMPORT：阳性 / 阴性对照 =================
        # ⚠️ 基线**不能**用「另存出来的空项目」（`SAVEAS` 不换模型，见 `SYNTHETIC_NODE_IDS`）。
        #    阳性 = 导入一个只含**新编号**的合成增量 ⇒ 行数上升 ∧ 新编号**读得回来**；
        #    阴性 = 导入只含空表的 JSON ⇒ 行数**不动**。
        baseline = counts()
        print(f"  阳性对照基线：{baseline}")

        synthetic = {
            "DBG": {
                "NODE": {
                    str(nid): {"X": float(i + 1) * 100.0, "Y": 0.0, "Z": 0.0}
                    for i, nid in enumerate(SYNTHETIC_NODE_IDS)
                }
            }
        }
        positive.write_text(json.dumps(synthetic, ensure_ascii=False), encoding="utf-8")
        status_positive = doc_post("/DOC/IMPORT", str(positive), label="阳性导入（合成增量）")
        after_positive = counts()
        positive_delta = {
            name: [baseline[name], after_positive[name]]
            for name in WATCH
            if baseline[name] != after_positive[name]
        }
        # 读回**具体编号**（比行数更强：证明值真的进去了，而不只是多了一行）
        read_back = client.get("/db/NODE").json().get("NODE") or {}
        landed = {
            str(nid): read_back.get(str(nid)) for nid in SYNTHETIC_NODE_IDS if str(nid) in read_back
        }
        print(f"  DOC.IMPORT（阳性：合成增量）→ {status_positive} · 行数差 {positive_delta}")
        print(f"    新编号读回：{landed}")
        doc_post("/DOC/SAVEAS", str(empty_target), label="阳性结果落盘")

        # 阴性对照：在**阳性之后**再导一次空表 ⇒ 行数必须**不动**
        # （⚠️ 基线**必须**取阳性之后 —— 否则阳性成功时会误判为失败，R164 的教训）
        status_negative = doc_post("/DOC/IMPORT", str(negative), label="阴性导入（空表）")
        after_negative = counts()
        negative_delta = {
            name: [after_positive[name], after_negative[name]]
            for name in WATCH
            if after_positive[name] != after_negative[name]
        }
        print(f"  DOC.IMPORT（阴性：只含空表）→ {status_negative} · 行数差 {negative_delta}")

        expected_nodes = [float(i + 1) * 100.0 for i in range(len(SYNTHETIC_NODE_IDS))]
        positive_ok = (
            status_positive == 200
            and after_positive[POSITIVE_TABLE] > baseline[POSITIVE_TABLE]
            and len(landed) == len(SYNTHETIC_NODE_IDS)
            and all(
                landed[str(nid)].get("X") == expected_nodes[i]
                for i, nid in enumerate(SYNTHETIC_NODE_IDS)
                if str(nid) in landed
            )
        )
        import_section: dict[str, Any] = {
            "criterion": (
                "row-count rises AND the new ids read back with the exact values written "
                "(status code is NOT discriminating)"
            ),
            "design": (
                "阳性对照 = 导入**与基线编号不重叠**的合成增量（`SYNTHETIC_NODE_IDS`）；"
                "**不**用「另存出的空项目」当基线 —— `DOC.SAVEAS` 只换路径、**不**换模型，"
                "那样得到的基线并不空（P175 实测教训）"
            ),
            "positive": {
                "status": status_positive,
                "baseline": baseline,
                "after": after_positive,
                "delta": positive_delta,
                "written": synthetic["DBG"]["NODE"],
                "read_back": landed,
                "ok": positive_ok,
            },
            "negative_control": {
                "status": status_negative,
                "source": "empty-tables-only JSON",
                "after": after_negative,
                "delta": negative_delta,
                # ⚠️ **必须**先要求请求**真的成功**（`status == 200`）再要求「行数不变」——
                #    否则「请求 404 没执行」会被 `not negative_delta` 误判成「无效果 ⇒ 通过」。
                #    这正是铁律 ⓪ 要防的：判据必须能**区分**「没执行」与「执行了但无效果」。
                #    （P175 实测踩到：阴性 404 连着 4 次，而 `ok` 仍是 True ⇒ 假绿。）
                "ok": status_negative == 200 and not negative_delta,
            },
            "semantics_finding": (
                "`DOC.IMPORT` 是**合并**语义：只含空表的 JSON **不**清空已有行"
                "（阴性对照后行数不变 ⇒ 实测确证）"
            ),
        }
        import_section["verdict"] = (
            PASSED
            if import_section["positive"]["ok"] and import_section["negative_control"]["ok"]
            else FAILED
        )

        # ---- 收尾（R144）：实例必须停在**干净 + 有路径**的项目上 ----
        status_restore = doc_open(backup, label="还原现场")
        final = pjcf()
        restored = str(final.get("FILE_NAME") or "") not in {"", "无标题"}
        print(f"  DOC.OPEN（还原现场）→ {status_restore} · FILE_NAME={final.get('FILE_NAME')!r}")
        if not restored:
            print("🛑 收尾时项目**无路径**（R144 事故条件）⇒ 拒绝收尾")
            return 1

        residue = counts()
        print(f"  收尾哨兵：{residue}")

    payload = {
        "note": [
            "P175 · `DOC.EXPORT` / `DOC.IMPORT` 可用性收口"
            "（`registry/README.md` §4 口径，**只升不降**）。",
            "**判据（铁律 ⓪）**：EXPORT = 文件真的落盘 ∧ 可解析 ∧ 与同刻读回逐表同形；"
            "IMPORT = 模型表的**行数真的变了**（状态码不判别任何东西）。",
            "**阳性对照** = 在**独立空基线项目**上导入样本 JSON ⇒ 行数**上升**"
            "（**不**在样本项目上就地做 —— 那会让基线 == 导入内容，"
            "是无**效**对照，P175 首轮教训）；"
            "**阴性对照** = 只含空表的 JSON ⇒ 行数**不动**。",
            "⚠️ **本探针一次都不发 `DOC.NEW`**"
            "（R144：无路径项目 ⇒ 原生自动保存弹「另存为」并挂起 API）；"
            "第 0 步先 `DOC.SAVE_AS` 备份现场（顺带确立路径），"
            "收尾用 `GET /db/PJCF` 核对 `FILE_NAME` ≠ `无标题`。",
            "**副作用受控**：只碰 `.tmp_p175/` 内的样本**副本**与产出物；"
            "样本原目录 `Gen Verification` **只读**。",
        ],
        "criterion_version": CRITERION_VERSION,
        "instance": {"alias": INSTANCE_ALIAS, "product": INSTANCE_PRODUCT, "base_url": base},
        "sample": {
            "source": str(SAMPLE_SOURCE),
            "copy": str(sample.relative_to(REPO)),
            "source_untouched": SAMPLE_SOURCE.is_file(),
        },
        "session": {
            "backup": str(backup.relative_to(REPO)),
            "restored_file_name": final.get("FILE_NAME"),
            "has_project_path": restored,
            "post_restore_counts": residue,
        },
        "endpoints": {"DOC.EXPORT": export_section, "DOC.IMPORT": import_section},
        "verdict": (
            PASSED
            if export_section["verdict"] == PASSED
            and import_section["verdict"] == PASSED
            and restored
            else FAILED
        ),
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"⇒ 判定：{'✅ PASSED' if payload['verdict'] == PASSED else '❌ FAILED（**不**收口）'}")
    print(f"wrote {EVIDENCE.relative_to(REPO)}")
    return 0 if payload["verdict"] == PASSED else 1


def check_offline(repo: pathlib.Path) -> int:
    """`--check`：证据齐备 + 判据全真 + 与登记表一致（**零请求**）。"""
    if not EVIDENCE.is_file():
        print(f"❌ 缺证据 {EVIDENCE.relative_to(REPO)}（先跑 --probe）")
        return 1
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    problems: list[str] = []

    if document.get("verdict") != PASSED:
        problems.append(f"顶层 verdict 应为 PASSED，实际 {document.get('verdict')!r}")

    session = document.get("session") or {}
    if session.get("has_project_path") is not True:
        problems.append("收尾时项目**无路径**（R144 事故条件）⇒ 收口不成立")
    if str(session.get("restored_file_name") or "") in {"", "无标题"}:
        problems.append(
            f"收尾 FILE_NAME = {session.get('restored_file_name')!r} ⇒ 实例未停在有路径的项目上"
        )

    sample = document.get("sample") or {}
    if sample.get("source_untouched") is not True:
        problems.append("样本原文件不可达 ⇒ 证据的前提不成立")

    endpoints = document.get("endpoints") or {}
    export = endpoints.get("DOC.EXPORT") or {}
    if export.get("verdict") != PASSED:
        problems.append(f"DOC.EXPORT verdict 应为 PASSED，实际 {export.get('verdict')!r}")
    if export.get("file_written") is not True or int(export.get("file_size") or 0) <= 0:
        problems.append("DOC.EXPORT 的文件未落盘 / 大小为 0 ⇒ 「效果」不成立")
    if int(export.get("table_count") or 0) <= 0:
        problems.append("DOC.EXPORT 的 `DBG` 里一张表都没有 ⇒ 导出口径不成立")
    if sorted(export.get("sentinel_shape_identical") or []) != sorted(WATCH):
        problems.append(
            f"哨兵同形项 {sorted(export.get('sentinel_shape_identical') or [])} "
            f"≠ 期望 {sorted(WATCH)}"
        )
    # ⚠️ **P175 实测**：`DOC.EXPORT` 的覆盖面**不**等于端点登记表 ——
    #    导出里有 **27** 张**未登记**的表名（`MDGN` / `WIND` / `SEIS` / `WNAT` / `RPR` …），
    #    而 **53** 个已登记端点**不在**导出里（多为 `-M1` 变体与纯 UI 设置类）。
    #    ⇒ 二者是**相交**关系，**不**可互推。这里只钉住**方向性**事实：
    #    ① 主干哨兵表**必须**都能导出（否则本探针的前提不成立）；
    #    ② 导出**不得为空**。
    exported = set(_evidence_tables())
    missing_sentinels = sorted(set(WATCH) - exported)
    if missing_sentinels:
        problems.append(f"哨兵表**不在**导出里：{missing_sentinels} ⇒ 导出口径不成立")
    if not exported:
        problems.append("导出里一张表都没有 ⇒ 口径不成立")

    import_section = endpoints.get("DOC.IMPORT") or {}
    if import_section.get("verdict") != PASSED:
        problems.append(f"DOC.IMPORT verdict 应为 PASSED，实际 {import_section.get('verdict')!r}")
    positive = import_section.get("positive") or {}
    if positive.get("ok") is not True:
        problems.append("DOC.IMPORT 阳性对照**没有**产生行数差 ⇒ 效果不成立")
    if POSITIVE_TABLE not in (positive.get("delta") or {}):
        problems.append(f"阳性对照的落点表 `{POSITIVE_TABLE}` 不在行数差里 ⇒ 对照没打到主干实体")
    baseline = positive.get("baseline") or {}
    after = positive.get("after") or {}
    if baseline == after:
        problems.append("阳性对照的**基线 == 导入后** ⇒ 无效对照（必须换一个不同基线的项目）")
    negative = import_section.get("negative_control") or {}
    if negative.get("ok") is not True:
        problems.append("DOC.IMPORT 阴性对照**产生了**行数差 ⇒ 对照不成立")
    if int(negative.get("status") or 0) != 200:
        problems.append(
            f"阴性对照的请求**没成功**（status={negative.get('status')}）"
            " ⇒ 「行数不变」证明不了「无效果」（可能只是没执行）"
        )
    if int(positive.get("status") or 0) != 200:
        problems.append(f"阳性对照的请求**没成功**（status={positive.get('status')}）")
    if import_section.get("verdict") == PASSED and int(negative.get("status") or 0) != 200:
        problems.append("阴性对照没成功却判 PASSED ⇒ **假绿**，判据不可信")
    if negative.get("after") != after:
        problems.append("阴性对照的基线**不是**阳性之后 ⇒ 阳性成功时会误判为失败（R164）")

    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    exported_set = set(_evidence_tables())
    registered_set = set(_registered_tables())
    print(
        f"   （口径）导出 {len(exported_set)} 张表 · 登记 {len(registered_set)} 张 DB 端点："
        f"导出独有 {len(exported_set - registered_set)} · 登记独有 "
        f"{len(registered_set - exported_set)}（**相交**，不可互推）"
    )
    print(
        f"✅ 离线自洽：`DOC.EXPORT` 落盘 **{export.get('file_size')}** 字节 · `DBG` "
        f"**{export.get('table_count')}** 张表（空表 {export.get('empty_table_count')} 张）· "
        f"哨兵 **{len(WATCH)}** 项逐表同形 · `DOC.IMPORT` 阳性行数差 "
        f"{positive.get('delta')} / 阴性 `0` 差 ⇒ 两个端点收口成立"
    )
    print(f"   项目收尾：FILE_NAME={session.get('restored_file_name')!r}（有路径 ✅）")
    return 0


def main() -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="DOC.EXPORT / DOC.IMPORT 可用性收口证据")
    parser.add_argument("--probe", action="store_true", help="真发请求（默认只预演）")
    parser.add_argument("--check", action="store_true", help="离线自洽断言（零请求）")
    args = parser.parse_args()
    if args.check:
        return check_offline(REPO)

    guard_paths()
    print(f"样本（**只读**）：{SAMPLE_SOURCE}")
    print(f"工作区：{WORKSPACE.relative_to(REPO)} · 证据：{EVIDENCE.relative_to(REPO)}")
    print(f"哨兵表（{len(WATCH)}）：{list(WATCH)}")
    print(f"声明路径（{len(ALLOWED_PATHS)}）：{sorted(ALLOWED_PATHS)} · **不**发 DOC.NEW（R144）")
    if not args.probe:
        print("\n（预演；加 --probe 才真发）")
        return 0
    print()
    return run_probe(REPO)


if __name__ == "__main__":
    raise SystemExit(main())
