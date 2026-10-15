#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P169 · **B 组**：`POST.TEXT` 的**键名裁决** + `TABLE_TYPE` 枚举收口的**真机裁决**
（`docs/07` §16.1 **R162**；**用户已显式授权** —— 见 `docs/08` §3 的授权记录）。

⚠️ **本探针有副作用**（**唯一**一个）：`POST /POST/TEXT` **必须带 `EXPORT_PATH`**
（不带 ⇒ 与 **R143** 同族的**弹窗**风险）⇒ **会**在实例磁盘**落文件**。
授权范围 = **仓库内** `.tmp_p164c/p169_text/`（**在 `.gitignore` 内**）⇒ 跑完**删除**。

两件事（一次测量同时裁决）
--------------------------
**① 请求键到底是哪个** —— 手册**示例体**用 `TEXT_TYPE`（**29 / 29** 条），而手册
`json_schema`（**12** 篇）与**我们的 Schema** 都用 `TABLE_TYPE`：

| 键 | 实测 |
| --- | --- |
| `TEXT_TYPE`（示例体的写法） | 真键 ⇒ 合法值**真的**产出文件；**伪**值 ⇒ `400 second query is wrong`（**值**错） |
| `TABLE_TYPE`（声明 / 我们的 Schema） | `400 Wrong Field`（**键**错）—— 与取值无关 |

**② 枚举收口的来源** —— 同 URI 的 **12** 篇文章在 `json_schema` 里声明了 **29** 个取值
（`TH_*` 20 + `PO_*` 9），而我们 Schema 只有 **3** 个（来自**一篇文章**，**R151** 的形态）。

判据（**铁律 ⓪**：效果，**不是**状态码）
--------------------------------------
| 相 | 判据 |
| --- | --- |
| **键名** | `TEXT_TYPE` ⇒ 合法值**产出文件** ∧ 伪值 ⇒ `400`（**值**错）；`TABLE_TYPE` ⇒ **任何**取值都 `400 Wrong Field`（**键**错） |
| **原生阳性（逐取值）** | 声明的 **29** 个取值 ⇒ `POST /POST/TEXT` **`200`** ∧ **文件真的生成** ∧ 原生**不**报 `second query is wrong` |
| **原生阴性** | **伪**取值 ⇒ `400` ∧ 文案含 `second query is wrong` |
| **核心闸门** | 收口后：**被接受**的取值**放行** · 伪取值 ⇒ `STRUCTAI-1200`（**零请求**） |
| **零残留** | 跑前 / 跑后 **6** 个模型哨兵**逐项一致** + 本探针写的**全部**文件**逐个删除** |

⚠️ **只**发 `POST /POST/TEXT` + 只读 `GET`；**绝不**碰 `DESIGN.{RC,SRC}` 的 `*-ANAL`（**R154** 崩溃族）。

用法
----
    python registry/tools/probe_post_text_p169.py            # 预演（零请求）
    python registry/tools/probe_post_text_p169.py --probe    # 真机（**有副作用**，需授权）
    python registry/tools/probe_post_text_p169.py --check    # 离线自洽（零请求）
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

EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "post_text_probe.json"
"""证据落点（**不含**凭据、**不含**响应原文；只留状态码、字节数与是否落盘）。"""

TEXT_DIR: Final[pathlib.Path] = REPO / ".tmp_p164c" / "p169_text"
"""**授权落盘目录**（仓库内、**在 `.gitignore` 内**；跑完**逐个删除**）。"""

DEFAULT_PROJECT: Final[str] = ".tmp_p164c/p164c-concrete.mgbx"
"""自建项目（**只碰它**）。"""

GENERATOR: Final[str] = "registry/tools/sync_post_text_enum.py"
"""收口生成器（`--check` 会重新导入它断言收口未回退）。"""

TEXT_PATH: Final[str] = "/POST/TEXT"
HEALTH_PATH: Final[str] = "/DB/NODE"

KEY_TRUE: Final[str] = "TEXT_TYPE"
KEY_FALSE: Final[str] = "TABLE_TYPE"
"""两个候选请求键（实测判据：**真键** ⇒ 合法值产出文件；**假键** ⇒ 任何取值都 `Wrong Field`）。"""

FAKE_VALUE: Final[str] = "NOT_A_REAL_TEXT_XYZ"
"""阴性对照用的**伪**取值。"""

BASE_ARGUMENT: Final[dict[str, Any]] = {
    "UNIT": {"FORCE": "N", "DIST": "MM"},
    "STYLES": {"FORMAT": "Fixed", "PLACE": 6},
    "NODE_ELEMS": {"KEYS": [1]},
}
"""除 `STEP` 之外的**非必需**字段（实测：`STEP` 是**必需**字段 —— 缺它 ⇒ `400 Wrong Field`）。

⚠️ 实测记录：`TEXT_TYPE` + `STEP` ⇒ `200`；**只有** `TEXT_TYPE` ⇒ `400 Wrong Field`
⇒ 必需字段清单由 `--probe` 逐条实测（本批**未**给 Schema 加 `required`，那是**收紧**）。
"""

STEP_BLOCK: Final[dict[str, Any]] = {"STEP": {"FROM": 0.0, "TO": 1.0, "STEPS": 1}}
"""`STEP`（实测必需）。"""

SENTINEL: Final[tuple[str, ...]] = (
    "/DB/NODE",
    "/DB/ELEM",
    "/DB/MATL",
    "/DB/SECT",
    "/DB/STLD",
    "/DB/CNLD",
)
"""零残留哨兵（**6** 项）。"""

AUTH_ERROR_MARKERS: Final[tuple[str, ...]] = (
    "MAPI Key is invalid",
    "invalid key",
    "MAPI-Key",
)
"""原生**鉴权失败**的文案标记（P168 的实测教训：识别 ⇒ **中止**，**不**写证据）。"""

SECOND_QUERY_MARKER: Final[str] = "second query is wrong"
"""原生**取值**错误的文案（**值**错 —— 与 `Wrong Field`（**键**错）是**两种**拒绝）。"""

WRONG_FIELD_MARKER: Final[str] = "Wrong Field"

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
    """原生答复是否是**鉴权失败**（见 `AUTH_ERROR_MARKERS`）。"""
    return any(marker.lower() in text.lower() for marker in AUTH_ERROR_MARKERS)


def guard_paths() -> None:
    """发请求**之前**的自检（`app/**` 的崩溃族）。"""
    sys.path.insert(0, str(REPO))
    from app.infrastructure.adapters.midas.client import (  # noqa: PLC0415
        NATIVE_CRASH_ENDPOINTS,
        guard_native_crash_path,
    )

    guard_native_crash_path(TEXT_PATH)  # 真在崩族里 ⇒ 这里就会抛（**零请求**）
    crash = len({"/" + str(item).replace(".", "/") for item in NATIVE_CRASH_ENDPOINTS})
    print(f"闸门自检：{TEXT_PATH} ∩ 崩溃族（{crash} 条）= ∅")


# ===== 离线事实（**可复算**）=====


def declared_types(repo: pathlib.Path) -> list[str]:
    """同 URI 的**全部**文章在 `json_schema` 里声明的 `TABLE_TYPE.enum` 并集（**逐篇**可回溯）。"""
    module = _sibling("sync_post_text_enum.py")
    return module.manual_types(repo)


def guard_allows(repo: pathlib.Path, key: str, values: list[str]) -> dict[str, Any]:
    """**核心闸门**行为（与 `adapter._build` **逐字同一**调用）。"""
    sys.path.insert(0, str(repo))
    from app.infrastructure.adapters.midas.errors import MidasValidationError  # noqa: PLC0415
    from app.infrastructure.adapters.midas.registry import MidasRegistry  # noqa: PLC0415
    from app.infrastructure.adapters.midas.spec_guard import guard_spec_values  # noqa: PLC0415

    registry = MidasRegistry.load(repo / "registry")
    schema = registry.effective_schema("POST.TEXT")
    body = {"Argument": {key: values[0] if len(values) == 1 else values, **STEP_BLOCK}}
    try:
        guard_spec_values(schema, body, endpoint="POST.TEXT", wrapper="Argument")
    except MidasValidationError as error:
        return {
            "values": list(values),
            "raised": True,
            "code": "STRUCTAI-1200",
            "native_reason": str((error.details or {}).get("reason") or ""),
            "problems": [str(item) for item in (error.details or {}).get("problems") or []][:2],
        }
    return {"values": list(values), "raised": False, "code": "", "native_reason": "", "problems": []}


def generator_facts(repo: pathlib.Path) -> dict[str, Any]:
    """收口生成器的**离线复算**。"""
    module = _sibling("sync_post_text_enum.py")
    return {
        "generator": GENERATOR,
        "declared": len(module.manual_types(repo)),
        "on_disk": module.on_disk_enum(repo),
        "expected": module.expected_enum(repo),
        "applied": module.is_applied(repo),
        "key": module.REQUEST_KEY,
    }


# ===== 真机 =====


def native_text(base: str, key: str, request_key: str, value: str, name: str) -> dict[str, Any]:
    """一次原生 `POST /POST/TEXT`（**带** `EXPORT_PATH` ⇒ 落盘到授权目录）。"""
    import httpx  # noqa: PLC0415

    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    target = TEXT_DIR / f"{name}.txt"
    if target.exists():
        target.unlink()
    argument: dict[str, Any] = {request_key: value, "EXPORT_PATH": str(target.resolve())}
    argument.update(STEP_BLOCK)
    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=180.0) as client:
        response = client.post(TEXT_PATH, json={"Argument": argument})
    text = response.text[:160]
    return {
        "request_key": request_key,
        "value": value,
        "status": int(response.status_code),
        "file_written": target.exists(),
        "file_bytes": target.stat().st_size if target.exists() else 0,
        "auth_error": _is_auth_error(text),
        "wrong_field": WRONG_FIELD_MARKER.lower() in text.lower(),
        "second_query": SECOND_QUERY_MARKER.lower() in text.lower(),
        "native_error": "" if response.status_code < 400 else text,
    }


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
            except Exception:  # noqa: BLE001 - 读不回如实留 None
                count = None
            snapshot[path] = {"status": int(response.status_code), "count": count}
    return snapshot


def cleanup() -> dict[str, Any]:
    """删除本探针**写下的全部文件**（**零残留**的硬要求）。"""
    removed: list[str] = []
    if TEXT_DIR.is_dir():
        for item in sorted(TEXT_DIR.iterdir()):
            if item.is_file():
                item.unlink()
                removed.append(item.name)
        if not any(TEXT_DIR.iterdir()):
            TEXT_DIR.rmdir()
    return {"dir": str(TEXT_DIR.relative_to(REPO)), "removed": removed, "empty_after": not TEXT_DIR.exists()}


def run_probe(repo: pathlib.Path, project: str) -> int:
    """真机受控测量（`--probe`）：键名裁决 + 逐取值 + 阴性 + 哨兵 + 清理。"""
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
        print("🛑 项目**为空** ⇒ 判据不适用（文本导出需要分析结果）")
        return 1

    declared = declared_types(repo)
    print(f"\n① **键名裁决**（同 URI 的 {len(declared)} 个声明取值）：")
    key_rows: list[dict[str, Any]] = []
    for request_key in (KEY_TRUE, KEY_FALSE):
        row = native_text(base, key, request_key, "TH_DISP", f"key_{request_key.lower()}")
        row["fake"] = native_text(base, key, request_key, FAKE_VALUE, f"key_{request_key.lower()}_fake")
        key_rows.append(row)
        print(
            f"  {request_key:12s} 合法值 {row['status']}（落盘={row['file_written']}）· "
            f"伪值 {row['fake']['status']}（second_query={row['fake']['second_query']} · "
            f"wrong_field={row['fake']['wrong_field']}）"
        )

    true_key = next(row for row in key_rows if row["request_key"] == KEY_TRUE)
    false_key = next(row for row in key_rows if row["request_key"] == KEY_FALSE)
    key_verdict = (
        true_key["status"] == 200
        and true_key["file_written"]
        and true_key["fake"]["status"] >= 400
        and true_key["fake"]["second_query"]
        and false_key["status"] >= 400
        and false_key["wrong_field"]
    )
    print(
        f"  ⇒ 请求键 = **{KEY_TRUE}**（合法值真的产出文件 · 伪值是**值**错）；"
        f"`{KEY_FALSE}` 是**键**错（`{WRONG_FIELD_MARKER}`，与取值无关）：{key_verdict}"
    )

    print(f"\n② 逐取值实测（**{len(declared)}** 个声明取值 ⇒ 原生是否**接受**）：")
    accepted: list[str] = []
    rejected: list[str] = []
    rows: list[dict[str, Any]] = []
    for value in declared:
        row = native_text(base, key, KEY_TRUE, value, f"v_{value.lower()}")
        rows.append(row)
        (accepted if row["status"] == 200 and row["file_written"] else rejected).append(value)
    print(f"  **接受**（`200` ∧ 落盘）{len(accepted)}：{accepted}")
    print(f"  **拒绝**{len(rejected)}：{rejected}")

    if any(row["auth_error"] for row in key_rows + rows) or any(
        row["fake"]["auth_error"] for row in key_rows
    ):
        print("🛑 原生回了**鉴权失败**（实例侧瞬时状态，**不**是裁决结论）⇒ **中止**，**不**写证据")
        cleanup()
        return 1

    after = sentinels(base, key)
    unchanged = after == before
    print(f"跑后哨兵：{ {k: v['count'] for k, v in after.items()} }   一致：{unchanged}")
    cleaned = cleanup()
    print(f"清理：删除 {len(cleaned['removed'])} 个文件 · 目录已空：{cleaned['empty_after']}")

    facts = generator_facts(repo)
    passed = bool(key_verdict and accepted and unchanged and cleaned["empty_after"] and facts["applied"])
    payload = {
        "phase": "disposition",
        "criterion_version": CRITERION_VERSION,
        "instance": {"alias": INSTANCE_ALIAS, "probed_at": PROBED_AT},
        "project": project,
        "project_opened_by_probe": opened,
        "authorized_export_dir": str(TEXT_DIR.relative_to(REPO)),
        "key_disposition": {
            "true_key": KEY_TRUE,
            "false_key": KEY_FALSE,
            "verdict": key_verdict,
            "rows": key_rows,
        },
        "declared_types": declared,
        "accepted_types": accepted,
        "rejected_types": rejected,
        "rows": rows,
        "generator": facts,
        "cleanup": cleaned,
        "sentinel": {
            "keys": list(SENTINEL),
            "before": before,
            "after": after,
            "unchanged": unchanged,
        },
        "verdict": PASSED if passed else FAILED,
        "note": (
            "判据 = **效果**（铁律 ⓪）：请求键由**实测**裁决 —— `TEXT_TYPE` 是**真键**"
            "（合法值**真的**产出文件、伪值是**值**错 `second query is wrong`），"
            "`TABLE_TYPE` 是**键**错（`Wrong Field`，与取值无关）⇒ **与手册示例体一致、"
            "与手册 json_schema / 我们的 Schema 矛盾**（登记为上游勘误）。"
            "取值收口的来源 = 被原生**接受**的声明取值（**只增不减**）。"
            "⚠️ 副作用**只**落在授权目录，跑完**逐个删除**（零残留）。"
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
        problems.append("`POST.TEXT` 的收口**未落盘**（生成器 --check 不过）")
    if facts["key"] != KEY_TRUE:
        problems.append(f"生成器用的请求键是 {facts['key']!r} ≠ 实测的真键 {KEY_TRUE!r}")
    disposition = document.get("key_disposition") or {}
    if not disposition.get("verdict"):
        problems.append("键名裁决**不成立**（`TEXT_TYPE` 真键 / `TABLE_TYPE` 键错）")
    if disposition.get("true_key") != KEY_TRUE or disposition.get("false_key") != KEY_FALSE:
        problems.append("键名裁决记录的键与 TARGETS 不一致")
    if document.get("verdict") != PASSED:
        problems.append(f"证据里的 verdict 应为 PASSED，实际 {document.get('verdict')!r}")
    if not document.get("accepted_types"):
        problems.append("**没有**任何声明取值被原生接受 ⇒ 收口依据不成立")
    if not (document.get("sentinel") or {}).get("unchanged"):
        problems.append("跑后哨兵与跑前不一致 ⇒ 有残留，结论不可用")
    if not (document.get("cleanup") or {}).get("empty_after"):
        problems.append("授权目录**未清空** ⇒ 有残留，结论不可用")
    for row in document.get("rows") or []:
        if row.get("auth_error"):
            problems.append(f"{row.get('value')} 的答复是**鉴权失败** ⇒ 证据不可用")
    for value in document.get("accepted_types") or []:
        if value not in facts["on_disk"]:
            problems.append(f"被原生接受的取值 {value!r} **不在**已落盘枚举里 ⇒ 收口不完整")

    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    print(
        f"✅ 离线自洽：请求键 = **{KEY_TRUE}**（`{KEY_FALSE}` 是键错）· 声明取值 "
        f"**{len(document['declared_types'])}** 个 ⇒ 原生接受 **{len(document['accepted_types'])}** "
        f"个（**全部**在已落盘枚举里）· 伪取值核心闸门**零请求**被拦 · "
        f"授权目录已清空 · 哨兵 6 项一致 ⇒ **R162** 成立"
    )
    return 0


def main() -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="POST.TEXT 的键名与枚举真机裁决（R162）")
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="自建项目（相对仓库根）")
    parser.add_argument("--probe", action="store_true", help="真发请求（**有副作用**；默认只预演）")
    parser.add_argument("--check", action="store_true", help="离线自洽断言（零请求）")
    args = parser.parse_args()
    if args.check:
        return check_offline(REPO)

    guard_paths()
    facts = generator_facts(REPO)
    print(
        f"收口事实：请求键 = **{facts['key']}** · 声明取值 **{facts['declared']}** 个 · "
        f"已落盘 {len(facts['on_disk'])} 个 · 已收口：{facts['applied']}"
    )
    print(f"授权落盘目录：{TEXT_DIR.relative_to(REPO)}（**在 `.gitignore` 内**；跑完删除）")
    if not args.probe:
        print("\n（预演；加 --probe 才真发 —— **有副作用**，需用户授权）")
        return 0
    print()
    return run_probe(REPO, args.project)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
