#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P169 · **C 组**：`DGNCODE` 的**真机裁决**（`docs/07` §16.1 **R162**；
**用户已显式授权**一次**写路径**真机裁决 —— 见 `docs/08` §3 的授权记录）。

问题（P168 留缺的 4 个端点里的 2 个）
------------------------------------
| 端点 | 现状 | 本批要裁决的 |
| --- | --- | --- |
| `OPE.LCOM-SRC` | 枚举只有 `['KDS 41 SRC : 2022']`（**一篇文章**的声明），而同 URI 的**另一篇**文章的**示例体**用 `AIK-SRC2K`（普查的 `example_blocked` 逐条列出） | `AIK-SRC2K` 到底**合法**吗？ |
| `OPE.LCOM-GEN` | Schema 里 `DGNCODE` 是**三个** `oneOf` 分支里的 `const`（`KDS 41 20 : 2022` / `KDS 41 30 : 2022` / `KDS 41 SRC : 2022`） | 本 build 接受哪些？ |

⚠️ **这是写路径**（创建荷载组合）⇒ **会**改模型。授权范围 = 自建项目
`.tmp_p164c/p164c-concrete.mgbx`；探针**只**发 `POST /OPE/LCOM-{SRC,GEN}`，
跑前记录 `GET /DB/LCOM-{SRC,GEN}` 的既有编号，跑后**逐个删除**新出现的编号。

判据（**铁律 ⓪**：效果，**不是**状态码）
--------------------------------------
`POST /OPE/LCOM-{SRC,GEN}` 的答复分**三档**（本批实测的**原生**文案）：

| 档 | 原生文案 | 含义 |
| --- | --- | --- |
| **业务级（取值合法）** | `Set_DefaultLoadComb failed; check CheckLcom history …` | 取值**通过了**规范校验、走到了**下游**（本自建模型无该规范所需的荷载条件） |
| **取值非法** | `Unknown Error` | **取值**被拒（与合法值**不同形**） |
| **形状 / 键错** | `Wrong Field` | 请求**形状**与本 build 不符（与取值无关）⇒ **不可判别** |

⇒ 判据 = **同形性**：合法候选（手册**声明**的取值）与**待裁决**候选（手册**示例体**的取值）
必须**同一档**，且**伪**取值必须落在**另一档**。

⚠️ **只**发 `POST /OPE/LCOM-{SRC,GEN}` + 只读 `GET`；**绝不**碰 `DESIGN.{RC,SRC}` 的 `*-ANAL`。

用法
----
    python registry/tools/probe_lcom_dgncode_p169.py            # 预演（零请求）
    python registry/tools/probe_lcom_dgncode_p169.py --probe    # 真机（**有副作用**，需授权）
    python registry/tools/probe_lcom_dgncode_p169.py --check    # 离线自洽（零请求）
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

EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "lcom_dgncode_probe.json"
"""证据落点（**不含**凭据、**不含**响应原文；只留分档与状态码）。"""

DEFAULT_PROJECT: Final[str] = ".tmp_p164c/p164c-concrete.mgbx"
"""自建项目（**只碰它**）。"""

GENERATOR: Final[str] = "registry/tools/sync_lcom_src_dgncode_enum.py"
"""收口生成器（**只**收 `OPE.LCOM-SRC` 的 `DGNCODE`；`--check` 断言未回退）。"""

# 端点 → (写路径, 只读回查路径, 本 build 上**合法**的候选（手册声明）, 待裁决的候选（手册示例体）)
TARGETS: Final[tuple[dict[str, Any], ...]] = (
    {
        "key": "OPE.LCOM-SRC",
        "write_path": "/OPE/LCOM-SRC",
        "read_path": "/DB/LCOM-SRC",
        "read_root": "LCOM-SRC",
        "declared": ["KDS 41 SRC : 2022"],
        "pending": ["AIK-SRC2K"],
        "evidence": "`MIDAS_API_Online_Manual_Gen_NX_v1.0.json#519`（示例体用 `AIK-SRC2K`）",
    },
    {
        "key": "OPE.LCOM-GEN",
        "write_path": "/OPE/LCOM-GEN",
        "read_path": "/DB/LCOM-GEN",
        "read_root": "LCOM-GEN",
        "declared": ["KDS 41 20 : 2022", "KDS 41 30 : 2022", "KDS 41 SRC : 2022"],
        "pending": ["AIK-SRC2K"],
        "evidence": "`MIDAS_API_Online_Manual_Gen_NX_v1.0.json#515`（示例体用 `AIK-SRC2K`）",
    },
)
"""**2** 个 `DGNCODE` 端点（另一个 `OPE.LINEBMLD::TYPE` / `OPE.GSBG::BRDG_GROUP` 是**产品侧澄清**，
本探针**不**碰 —— 它们连「候选取值」都没有权威来源）。"""

FAKE_CODE: Final[str] = "NONSENSE-CODE"
"""阴性对照：**伪**规范码（任何来源都没有）。"""

BAND_BUSINESS: Final[str] = "business"
BAND_VALUE: Final[str] = "value_rejected"
BAND_SHAPE: Final[str] = "shape_mismatch"
BAND_OTHER: Final[str] = "other"

BUSINESS_MARKER: Final[str] = "set_defaultloadcomb failed"
"""**业务级**答复的文案标记（取值**通过**了规范校验、走到下游）。"""

VALUE_MARKER: Final[str] = "unknown error"
"""**取值非法**的文案标记。"""

SHAPE_MARKER: Final[str] = "wrong field"
"""**形状 / 键错**的文案标记（与取值**无关** ⇒ 该端点**不可判别**）。"""

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
    """原生答复是否是**鉴权失败**。"""
    return any(marker.lower() in text.lower() for marker in AUTH_ERROR_MARKERS)


def band_of(text: str) -> str:
    """原生答复 → **档**（见模块头部的三档表）。"""
    lowered = text.lower()
    if SHAPE_MARKER in lowered:
        return BAND_SHAPE
    if BUSINESS_MARKER in lowered:
        return BAND_BUSINESS
    if VALUE_MARKER in lowered:
        return BAND_VALUE
    return BAND_OTHER


def guard_paths() -> None:
    """发请求**之前**的自检（`app/**` 的崩溃族）。"""
    sys.path.insert(0, str(REPO))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        NATIVE_CRASH_ENDPOINTS,
        guard_native_crash_path,
    )

    for item in TARGETS:
        guard_native_crash_path(str(item["write_path"]))  # 真在崩族里 ⇒ 这里就会抛（**零请求**）
    crash = len({"/" + str(item).replace(".", "/") for item in NATIVE_CRASH_ENDPOINTS})
    print(f"闸门自检：{len(TARGETS)} 个写路径 ∩ 崩溃族（{crash} 条）= ∅")


# ===== 离线事实（**可复算**）=====


def guard_allows(repo: pathlib.Path, key: str, code: str) -> dict[str, Any]:
    """**核心闸门**行为（与 `adapter._build` **逐字同一**调用）。"""
    sys.path.insert(0, str(repo))
    from app.infrastructure.adapters.midas.errors import MidasValidationError  # noqa: PLC0415
    from app.infrastructure.adapters.midas.registry import MidasRegistry  # noqa: PLC0415
    from app.infrastructure.adapters.midas.spec_guard import guard_spec_values  # noqa: PLC0415

    registry = MidasRegistry.load(repo / "registry")
    schema = registry.effective_schema(key)
    try:
        guard_spec_values(
            schema, {"Argument": {"OPTION": "ADD", "DGNCODE": code}}, endpoint=key, wrapper="Argument"
        )
    except MidasValidationError as error:
        return {
            "code": code,
            "raised": True,
            "native_reason": str((error.details or {}).get("reason") or ""),
            "problems": [str(item) for item in (error.details or {}).get("problems") or []][:2],
        }
    return {"code": code, "raised": False, "native_reason": "", "problems": []}


def generator_facts(repo: pathlib.Path) -> dict[str, Any]:
    """收口生成器的**离线复算**。"""
    module = _sibling("sync_lcom_src_dgncode_enum.py")
    return {
        "generator": GENERATOR,
        "on_disk": module.on_disk_enum(repo),
        "expected": module.expected_enum(repo),
        "applied": module.is_applied(repo),
    }


# ===== 真机 =====


def read_state(base: str, key: str, item: dict[str, Any]) -> dict[str, Any]:
    """只读回查：`GET <read_path>` → 既有编号集合。"""
    import httpx  # noqa: PLC0415

    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=60.0) as client:
        response = client.get(str(item["read_path"]))
    names: list[str] = []
    try:
        payload = response.json()
        block = payload.get(str(item["read_root"])) or {}
        names = sorted(str(item) for item in block)
    except Exception:  # noqa: BLE001 - 读不回如实留空
        names = []
    return {"status": int(response.status_code), "ids": names}


def post_code(base: str, key: str, item: dict[str, Any], code: str) -> dict[str, Any]:
    """一次原生 `POST /OPE/LCOM-*`（**写路径**；授权范围内）。"""
    import httpx  # noqa: PLC0415

    body = {"Argument": {"OPTION": "ADD", "DGNCODE": code}}
    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=120.0) as client:
        response = client.post(str(item["write_path"]), json=body)
    text = response.text[:200]
    return {
        "code": code,
        "status": int(response.status_code),
        "band": band_of(text),
        "auth_error": _is_auth_error(text),
        "message": text[:120] if response.status_code >= 400 else "",
    }


def delete_ids(base: str, key: str, item: dict[str, Any], ids: list[str]) -> list[str]:
    """删除指定编号（**只**删本探针新建的）。"""
    import httpx  # noqa: PLC0415

    removed: list[str] = []
    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=120.0) as client:
        for item_id in ids:
            response = client.delete(f"{item['read_path']}/{item_id}")
            if response.status_code < 400:
                removed.append(item_id)
    return removed


def sentinels(base: str, key: str) -> dict[str, Any]:
    """只读哨兵（**6** 项）。"""
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


def run_probe(repo: pathlib.Path, project: str) -> int:
    """真机受控测量（`--probe`）：逐端点分档 + 清理 + 哨兵。"""
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

    rows: list[dict[str, Any]] = []
    for item in TARGETS:
        print(f"\n① {item['key']}（写路径 {item['write_path']}）：")
        state_before = read_state(base, key, item)
        declared_rows = [post_code(base, key, item, code) for code in item["declared"]]
        pending_rows = [post_code(base, key, item, code) for code in item["pending"]]
        fake_row = post_code(base, key, item, FAKE_CODE)
        state_after = read_state(base, key, item)
        created = sorted(set(state_after["ids"]) - set(state_before["ids"]))
        removed = delete_ids(base, key, item, created) if created else []
        final = read_state(base, key, item)
        for row in declared_rows + pending_rows + [fake_row]:
            print(f"    {row['code']:22s} {row['status']} · 档={row['band']}")
        print(f"    新建编号 {created} ⇒ 已删 {removed} ⇒ 回查 {final['ids']}")
        rows.append(
            {
                "key": item["key"],
                "evidence": item["evidence"],
                "declared_rows": declared_rows,
                "pending_rows": pending_rows,
                "fake_row": fake_row,
                "created": created,
                "removed": removed,
                "state_before": state_before,
                "state_after_cleanup": final,
            }
        )

    if any(
        row["auth_error"]
        for item in rows
        for row in item["declared_rows"] + item["pending_rows"] + [item["fake_row"]]
    ):
        print("🛑 原生回了**鉴权失败**（实例侧瞬时状态，**不**是裁决结论）⇒ **中止**，**不**写证据")
        return 1

    after = sentinels(base, key)
    unchanged = after == before
    print(f"\n跑后哨兵：{ {k: v['count'] for k, v in after.items()} }   一致：{unchanged}")

    # 逐端点裁决：合法候选与待裁决候选**同档** ∧ 伪取值**不同档** ∧ 不是 shape_mismatch
    verdicts: dict[str, Any] = {}
    for item, row in zip(TARGETS, rows):
        declared_bands = {entry["band"] for entry in row["declared_rows"]}
        pending_bands = {entry["band"] for entry in row["pending_rows"]}
        fake_band = row["fake_row"]["band"]
        decidable = BAND_SHAPE not in declared_bands and BAND_OTHER not in declared_bands
        legitimate = decidable and pending_bands <= declared_bands and fake_band not in pending_bands
        verdicts[str(item["key"])] = {
            "decidable": decidable,
            "declared_bands": sorted(declared_bands),
            "pending_bands": sorted(pending_bands),
            "fake_band": fake_band,
            "pending_legitimate": legitimate,
            "reason": (
                ""
                if decidable
                else f"本 build 对**所有**取值都回 `{SHAPE_MARKER}`（形状 / 键错）⇒ **不可判别**"
            ),
        }
        print(
            f"  {item['key']:16s} 可判别={decidable} · 声明档={sorted(declared_bands)} · "
            f"待裁决档={sorted(pending_bands)} · 伪档={fake_band} ⇒ 待裁决合法={legitimate}"
        )

    facts = generator_facts(repo)
    decidable_any = any(v["decidable"] for v in verdicts.values())
    passed = bool(decidable_any and unchanged and facts["applied"])
    payload = {
        "phase": "disposition",
        "criterion_version": CRITERION_VERSION,
        "instance": {"alias": INSTANCE_ALIAS, "probed_at": PROBED_AT},
        "project": project,
        "project_opened_by_probe": opened,
        "rows": rows,
        "verdicts": verdicts,
        "generator": facts,
        "sentinel": {
            "keys": list(SENTINEL),
            "before": before,
            "after": after,
            "unchanged": unchanged,
        },
        "verdict": PASSED if passed else FAILED,
        "note": (
            "判据 = **效果**（铁律 ⓪）：`POST /OPE/LCOM-*` 的答复分**三档** —— "
            "**业务级**（`Set_DefaultLoadComb failed`：取值**通过**了规范校验、走到**下游**）· "
            "**取值非法**（`Unknown Error`）· **形状 / 键错**（`Wrong Field`，与取值无关）。"
            "待裁决候选与**声明**的合法候选**同档** ∧ 伪取值**不同档** ⇒ 该候选**合法**。"
            "⚠️ 本 build 对 `OPE.LCOM-GEN` **任何**取值都回 `Wrong Field` ⇒ **不可判别**（如实留缺）。"
        ),
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"⇒ 判定：{'✅ PASSED' if passed else '❌ FAILED'}")
    print(f"wrote {EVIDENCE.relative_to(REPO)}")
    return 0 if passed else 1


# ===== 离线自洽（`--check`，**零请求**）=====


def check_offline(repo: pathlib.Path) -> int:
    """`--check`：证据齐备 + 判据全真 + 收口已落盘（不可回退）。"""
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
    if not (document.get("sentinel") or {}).get("unchanged"):
        problems.append("跑后哨兵与跑前不一致 ⇒ 有残留，结论不可用")
    verdicts = document.get("verdicts") or {}
    legitimate = {
        key: value
        for key, value in verdicts.items()
        if value.get("decidable") and value.get("pending_legitimate")
    }
    if not legitimate:
        problems.append("**没有**任何端点的待裁决候选被判为合法 ⇒ 收口依据不成立")
    for key, value in verdicts.items():
        if not value.get("decidable"):
            continue  # ⚠️ **不可判别**的端点**如实留缺**（**不**算失败）
        if not value.get("pending_legitimate"):
            problems.append(f"{key} 的待裁决候选**未**被判为合法 ⇒ 不得据此收口")
    for row in document.get("rows") or []:
        if row.get("created") and set(row["created"]) - set(row.get("removed") or []):
            problems.append(f"{row.get('key')} 新建的编号**未全部删除** ⇒ 有残留")
    # 收口必须**只增不减**：**已收口**（可判别 ∧ 待裁决合法）的端点的**声明**取值必须仍在枚举里。
    # ⚠️ **不可判别**的端点（`OPE.LCOM-GEN`）**未**收口 ⇒ 它的声明值在 `oneOf[].const` 里
    # （**不是** `enum`），本断言**不**适用于它。
    closed_keys = set(legitimate)
    for item in TARGETS:
        if str(item["key"]) not in closed_keys:
            continue
        for code in item["declared"]:
            if code not in facts["on_disk"]:
                problems.append(f"{item['key']} 的收口**丢掉了**声明取值 {code!r}（只增不减被违反）")
    if FAKE_CODE in facts["on_disk"]:
        problems.append(f"枚举含**伪**取值 {FAKE_CODE!r} ⇒ 负向对照不成立")

    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    undecidable = sorted(key for key, value in verdicts.items() if not value.get("decidable"))
    print(
        f"✅ 离线自洽：`OPE.LCOM-SRC` 的 `DGNCODE` 收口已落盘（{len(facts['on_disk'])} 个取值）· "
        f"**{len(legitimate)}** 个端点的待裁决候选**合法**（与声明取值**同档**、与伪取值**不同档**）· "
        f"**不可判别**（如实留缺）：{undecidable} · 新建编号已删净 · 哨兵 6 项一致 ⇒ **R162** 成立"
    )
    return 0


def main() -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="DGNCODE 的写路径真机裁决（R162）")
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="自建项目（相对仓库根）")
    parser.add_argument("--probe", action="store_true", help="真发请求（**有副作用**；默认只预演）")
    parser.add_argument("--check", action="store_true", help="离线自洽断言（零请求）")
    args = parser.parse_args()
    if args.check:
        return check_offline(REPO)

    guard_paths()
    facts = generator_facts(REPO)
    print(
        f"收口事实：`OPE.LCOM-SRC` 的 `DGNCODE` 已落盘 {facts['on_disk']} ⇒ 机械结果 "
        f"{facts['expected']} · 已收口：{facts['applied']}"
    )
    for item in TARGETS:
        print(f"  {item['key']:16s} 声明={item['declared']} · 待裁决={item['pending']}")
    if not args.probe:
        print("\n（预演；加 --probe 才真发 —— **写路径**，需用户授权）")
        return 0
    print()
    return run_probe(REPO, args.project)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
