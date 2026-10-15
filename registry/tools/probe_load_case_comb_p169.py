#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P169 · **D 组**：`VIEW.RESULTGRAPHIC` 的 `LOAD_CASE_COMB` **缺字段补全**的**真效果**判据
（`docs/07` §16.1 **R162**；**R155** 记录的缺字段）。

问题（**缺字段**，**不**是缺枚举）
--------------------------------
`VIEW.RESULTGRAPHIC` 的请求 Schema 的 `Argument` 原先**没有** `LOAD_CASE_COMB`，
而上游手册里 **66 / 66** 条示例**都**带它（**R155** 记录）。
⚠️ **枚举普查（R161）的口径只管枚举** ⇒ 本项**单独**一次数据侧作业。

判据（**铁律 ⓪**：效果，**不是**状态码）
--------------------------------------
| 相 | 判据 |
| --- | --- |
| **原生真效果** | 同一模型、同一 `CURRENT_MODE`，**只换** `LOAD_CASE_COMB.NAME`（`DL` → `SIDL`）⇒ `POST /VIEW/RESULTGRAPHIC` **`200`** ∧ `POST /VIEW/CAPTURE` **`200`** ∧ **截图 sha256 不同**（画面**真的**变） |
| **原生阴性** | 不存在的工况名 ⇒ `POST /VIEW/RESULTGRAPHIC` **`400`** ∧ 错误文案含 `Can not find load case` |
| **核心闸门（补字段后）** | 合法体（含 `LOAD_CASE_COMB`）⇒ **放行**（补字段**不**拦任何调用 —— 无枚举的字段 `spec_guard` **不**校验） |
| **缺字段的代价（可执行证据）** | 补字段**前**：`transformer_field_not_in_schema`（该字段**不在** Schema ⇒ Transformer 白名单拒）⇒ 换工况**做不到**；补字段**后**：`to_native` 接受 `load_case_comb` |
| **零残留** | 跑前 / 跑后 **6** 个模型哨兵**逐项一致**（视图类操作**不**写模型） |

⚠️ **只**发 `POST /VIEW/RESULTGRAPHIC` + `POST /VIEW/CAPTURE`（截图落 `.tmp_p164c/`，
**在 `.gitignore` 内**）+ 只读 `GET`；**绝不**碰 `DESIGN.{RC,SRC}` 的 `*-ANAL`（**R154** 崩溃族）。

用法
----
    python registry/tools/probe_load_case_comb_p169.py            # 预演（零请求）
    python registry/tools/probe_load_case_comb_p169.py --probe    # 真机
    python registry/tools/probe_load_case_comb_p169.py --check    # 离线自洽（零请求）
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys
from typing import Any, Final

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
"""仓库根目录（`registry/tools/` 的上两级）。"""

EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "load_case_comb_probe.json"
"""证据落点（**不含**凭据、**不含**响应原文；只留状态码、字节数与 sha256）。"""

SHOTS: Final[pathlib.Path] = REPO / ".tmp_p164c" / "p169_lcc"
"""截图落点（**在 `.gitignore` 内**）。"""

DEFAULT_PROJECT: Final[str] = ".tmp_p164c/p164c-concrete.mgbx"
"""自建项目（**只碰它**；它**已有分析结果**且**有 2 个静力工况** —— 判据的前提）。"""

GENERATOR: Final[str] = "registry/tools/sync_result_graphic_lcc.py"
"""补字段生成器（`--check` 会重新导入它断言字段未回退）。"""

MODE: Final[str] = "DisplacementContour"
"""`CURRENT_MODE` 的合法取值（在 **36** 个里；与 P168 的探针**同一**取值）。"""

CASE_A: Final[str] = "DL"
CASE_B: Final[str] = "SIDL"
"""自建模型上的**两个**静力工况（`GET /DB/STLD` 实测：`DL` / `SIDL`）。"""

BOGUS_CASE: Final[str] = "NO_SUCH_CASE"
"""阴性对照：**不存在**的工况名（原生实测回 `400 Can not find load case.`）。"""

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
GRAPHIC_PATH: Final[str] = "/VIEW/RESULTGRAPHIC"
CAPTURE_PATH: Final[str] = "/VIEW/CAPTURE"
ALLOWED_PATHS: Final[tuple[str, ...]] = (GRAPHIC_PATH, CAPTURE_PATH, "/DOC/OPEN")
"""本探针**允许**出现的**写**方法路径（`POST`）—— 其余一律只读 `GET`。"""

AUTH_ERROR_MARKERS: Final[tuple[str, ...]] = (
    "MAPI Key is invalid",
    "invalid key",
    "MAPI-Key",
)
"""原生**鉴权失败**的文案标记（P168 的实测教训：识别 ⇒ **中止**，**不**写证据）。"""

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


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_auth_error(text: str) -> bool:
    """原生答复是否是**鉴权失败**（见 `AUTH_ERROR_MARKERS`）。"""
    return any(marker.lower() in text.lower() for marker in AUTH_ERROR_MARKERS)


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


def graphic_body(case: str) -> dict[str, Any]:
    """请求体（与 P168 的探针**同一**形状；`LOAD_CASE_COMB` 是**本批**要补的字段）。"""
    return {
        "CURRENT_MODE": MODE,
        "LOAD_CASE_COMB": {"TYPE": "ST", "NAME": case},
        "TYPE_OF_DISPLAY": {
            "CONTOUR": {"OPT_CHECK": True, "NUM_OF_COLOR": 6, "COLOR_TYPE": "rgb"},
            "DEFORM": {"OPT_CHECK": True},
            "VALUES": {"OPT_CHECK": True},
            "LEGEND": {"OPT_CHECK": True},
        },
    }


def guard_behaviour(repo: pathlib.Path) -> dict[str, Any]:
    """**核心闸门**行为（与 `adapter._build` **逐字同一**调用）：含 `LOAD_CASE_COMB` 的体 ⇒ 放行？"""
    sys.path.insert(0, str(repo))
    from app.infrastructure.adapters.midas.errors import MidasValidationError  # noqa: PLC0415
    from app.infrastructure.adapters.midas.registry import MidasRegistry  # noqa: PLC0415
    from app.infrastructure.adapters.midas.spec_guard import guard_spec_values  # noqa: PLC0415

    registry = MidasRegistry.load(repo / "registry")
    schema = registry.effective_schema("VIEW.RESULTGRAPHIC")
    try:
        guard_spec_values(
            schema,
            {"Argument": graphic_body(CASE_A)},
            endpoint="VIEW.RESULTGRAPHIC",
            wrapper="Argument",
        )
    except MidasValidationError as error:
        return {
            "raised": True,
            "code": "STRUCTAI-1200",
            "native_reason": str((error.details or {}).get("reason") or ""),
            "problems": [str(item) for item in (error.details or {}).get("problems") or []][:2],
        }
    return {"raised": False, "code": "", "native_reason": "", "problems": []}


def schema_field_declared(repo: pathlib.Path) -> bool:
    """`Argument.properties` 里**是否**声明了 `LOAD_CASE_COMB`（**补字段**的直接判据）。"""
    document = json.loads(
        (repo / "registry" / "schema/common/view/RESULTGRAPHIC.json").read_text(encoding="utf-8")
    )
    node: Any = document.get("schema")
    for segment in ("RESULTGRAPHIC", "properties", "Argument", "properties"):
        node = node.get(segment) if isinstance(node, dict) and segment in node else None
    return isinstance(node, dict) and "LOAD_CASE_COMB" in node


def transformer_accepts(repo: pathlib.Path) -> dict[str, Any]:
    """**生产路径**的字段白名单是否接受 `load_case_comb`（补字段**前 / 后**的差别）。

    ⚠️ 这是「缺字段的**代价**」的**可执行证据**：`SchemaBoundTransformer.to_native()` 的
    白名单来自 `request_schema_fields()` ⇒ 字段**不在** Schema 里就**进不了**原生请求
    （实测错误 = `transformer_field_not_in_schema`）⇒ **换工况做不到**。
    """
    sys.path.insert(0, str(repo))
    from app.infrastructure.adapters.midas.errors import MidasTransformerError  # noqa: PLC0415
    from app.infrastructure.adapters.midas.registry import MidasRegistry  # noqa: PLC0415
    from app.infrastructure.adapters.midas.transforms import ViewTransformer  # noqa: PLC0415

    registry = MidasRegistry.load(repo / "registry")
    transformer = ViewTransformer(registry)
    try:
        native = transformer.to_native({"result_graphic": graphic_body(CASE_A)})
    except MidasTransformerError as error:
        return {"accepted": False, "error": str(error)[:120], "native_keys": []}
    return {
        "accepted": True,
        "error": "",
        "native_keys": sorted(str(key) for key in native),
    }


def generator_facts(repo: pathlib.Path) -> dict[str, Any]:
    """补字段生成器的**离线复算**。"""
    module = _sibling("sync_result_graphic_lcc.py")
    return {
        "generator": GENERATOR,
        "examples": len(module.load_examples(repo)),
        "inner_keys": module.observed_inner_keys(repo),
        "applied": module.is_applied(repo),
    }


# ===== 真机 =====


def shot(base: str, key: str, case: str, name: str) -> dict[str, Any]:
    """一次「设图形 + 截图」：`POST /VIEW/RESULTGRAPHIC` + `POST /VIEW/CAPTURE`。"""
    import httpx  # noqa: PLC0415

    SHOTS.mkdir(parents=True, exist_ok=True)
    target = SHOTS / f"{name}.jpg"
    if target.exists():
        target.unlink()
    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=180.0) as client:
        graphic = client.post(GRAPHIC_PATH, json={"Argument": graphic_body(case)})
        capture = client.post(
            CAPTURE_PATH,
            json={
                "Argument": {
                    "EXPORT_PATH": str(target.resolve()),
                    "SET_MODE": "post",
                    "WIDTH": 800,
                    "HEIGHT": 600,
                }
            },
        )
    return {
        "case": case,
        "graphic_status": int(graphic.status_code),
        "capture_status": int(capture.status_code),
        "graphic_error": "" if graphic.status_code < 400 else graphic.text[:120],
        "auth_error": _is_auth_error(graphic.text) or _is_auth_error(capture.text),
        "shot": {
            "name": name,
            "exists": target.exists(),
            "bytes": target.stat().st_size if target.exists() else 0,
            "sha256": _sha(target) if target.exists() else "",
        },
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


def run_probe(repo: pathlib.Path, project: str) -> int:
    """真机受控测量（`--probe`）：两个工况的截图对比 + 阴性对照 + 哨兵。"""
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
        print("🛑 项目**为空** ⇒ 判据不适用（视图需要分析结果）")
        return 1

    print("\n① `LOAD_CASE_COMB` 的原生真效果（同一图形、只换工况）：")
    row_a = shot(base, key, CASE_A, "case_a")
    row_b = shot(base, key, CASE_B, "case_b")
    bogus = shot(base, key, BOGUS_CASE, "bogus")
    for row in (row_a, row_b, bogus):
        print(
            f"  NAME={row['case']:14s} 图形 {row['graphic_status']} · 截图 {row['capture_status']} · "
            f"{row['shot']['bytes']} 字节 · {row['shot']['sha256'][:12]}"
            + (f" · 错误 {row['graphic_error'][:60]}" if row["graphic_error"] else "")
        )

    if any(row["auth_error"] for row in (row_a, row_b, bogus)):
        print("🛑 原生回了**鉴权失败**（实例侧瞬时状态，**不**是结论）⇒ **中止**，重跑即可")
        return 1

    both_ok = (
        row_a["graphic_status"] == 200
        and row_a["capture_status"] == 200
        and row_b["graphic_status"] == 200
        and row_b["capture_status"] == 200
    )
    picture_changes = (
        row_a["shot"]["exists"]
        and row_b["shot"]["exists"]
        and row_a["shot"]["sha256"] != row_b["shot"]["sha256"]
    )
    bogus_rejected = bogus["graphic_status"] >= 400 and "load case" in bogus["graphic_error"].lower()
    print(
        f"  原生真效果：两个工况都 `200`={both_ok} · **截图两两不同**={picture_changes} · "
        f"不存在的工况被拒={bogus_rejected}"
    )

    after = sentinels(base, key)
    unchanged = after == before
    print(f"跑后哨兵：{ {k: v['count'] for k, v in after.items()} }   一致：{unchanged}")

    facts = generator_facts(repo)
    passed = bool(both_ok and picture_changes and bogus_rejected and unchanged and facts["applied"])
    payload = {
        "phase": "effect",
        "criterion_version": CRITERION_VERSION,
        "instance": {"alias": INSTANCE_ALIAS, "probed_at": PROBED_AT},
        "project": project,
        "project_opened_by_probe": opened,
        "generator": facts,
        "guard": guard_behaviour(repo),
        "schema_field_declared": schema_field_declared(repo),
        "transformer_accepts": transformer_accepts(repo),
        "runs": {"case_a": row_a, "case_b": row_b, "bogus": bogus},
        "native_effect": both_ok,
        "picture_changes": picture_changes,
        "bogus_rejected": bogus_rejected,
        "sentinel": {
            "keys": list(SENTINEL),
            "before": before,
            "after": after,
            "unchanged": unchanged,
        },
        "verdict": PASSED if passed else FAILED,
        "note": (
            "判据 = **效果**（铁律 ⓪）：补字段**前** `load_case_comb` **进不了**原生请求"
            "（`transformer_field_not_in_schema`，字段**不在** Schema 白名单里）；补字段**后** "
            "同一图形、**只换** `LOAD_CASE_COMB.NAME`（`DL` → `SIDL`）⇒ 两张截图**sha256 不同**"
            "（画面**真的**变）⇒ 这个字段**真的**被原生用来**选工况**；不存在的工况 ⇒ 原生 `400`。"
        ),
    }
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"⇒ 判定：{'✅ PASSED' if passed else '❌ FAILED'}")
    print(f"wrote {EVIDENCE.relative_to(REPO)}")
    return 0 if passed else 1


# ===== 离线自洽（`--check`，**零请求**）=====


def check_offline(repo: pathlib.Path) -> int:
    """`--check`：证据齐备 + 判据全真 + 字段已落盘（不可回退）。"""
    if not EVIDENCE.is_file():
        print(f"❌ 缺证据 {EVIDENCE.relative_to(REPO)}（先跑 --probe）")
        return 1
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    problems: list[str] = []
    facts = generator_facts(repo)
    if not facts["applied"]:
        problems.append("`LOAD_CASE_COMB` 的补字段**未落盘**（生成器 --check 不过）")
    if not document.get("schema_field_declared"):
        problems.append("`Argument.properties` 里**没有** `LOAD_CASE_COMB` ⇒ 补字段不成立")
    if document.get("verdict") != PASSED:
        problems.append(f"证据里的 verdict 应为 PASSED，实际 {document.get('verdict')!r}")
    for field in ("native_effect", "picture_changes", "bogus_rejected"):
        if document.get(field) is not True:
            problems.append(f"判据 {field} 不为真 ⇒ 真效果结论不成立")
    if not (document.get("sentinel") or {}).get("unchanged"):
        problems.append("跑后哨兵与跑前不一致 ⇒ 有残留，结论不可用")
    if (document.get("guard") or {}).get("raised"):
        problems.append("补字段后**核心闸门拦了**合法体 ⇒ 补字段造成了误伤")
    transformer = document.get("transformer_accepts") or {}
    if not transformer.get("accepted"):
        problems.append(
            f"生产路径的 Transformer **仍不接受** `result_graphic`（{transformer.get('error')!r}）"
        )
    runs = document.get("runs") or {}
    for name, row in runs.items():
        if (row or {}).get("auth_error"):
            problems.append(f"{name} 的答复是**鉴权失败** ⇒ 证据不可用")
    if not all((runs.get(name) or {}).get("shot", {}).get("exists") for name in ("case_a", "case_b")):
        problems.append("两个工况的截图**不都在** ⇒ 无法比较（证据不完整）")

    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    a = runs["case_a"]["shot"]
    b = runs["case_b"]["shot"]
    print(
        f"✅ 离线自洽：补字段已落盘（{len(facts['inner_keys'])} 个内键）· 生产路径的 Transformer "
        f"**接受** `load_case_comb` · 两个工况的截图 **{a['bytes']} → {b['bytes']}** 字节"
        f"（sha256 **不同**）⇒ 这个字段**真的**用来**选工况** · 不存在的工况原生 `400` · "
        f"核心闸门**未误伤** · 哨兵 6 项一致 ⇒ **R162** 成立"
    )
    return 0


def main() -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="LOAD_CASE_COMB 补字段的真效果（R162）")
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="自建项目（相对仓库根）")
    parser.add_argument("--probe", action="store_true", help="真发请求（默认只预演）")
    parser.add_argument("--check", action="store_true", help="离线自洽断言（零请求）")
    args = parser.parse_args()
    if args.check:
        return check_offline(REPO)

    guard_paths()
    facts = generator_facts(REPO)
    print(
        f"补字段事实：上游示例体 **{facts['examples']}** 条 · 内键 {facts['inner_keys']} · "
        f"已落盘：{facts['applied']} · Schema 里已声明：{schema_field_declared(REPO)}"
    )
    transformer = transformer_accepts(REPO)
    print(
        f"生产路径的 Transformer 接受 `result_graphic`：{transformer['accepted']}"
        + (f"（{transformer['error']}）" if not transformer["accepted"] else "")
    )
    if not args.probe:
        print("\n（预演；加 --probe 才真发）")
        return 0
    print()
    return run_probe(REPO, args.project)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
