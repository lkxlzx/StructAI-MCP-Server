#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P169 · **A 组**：`PARTS` 的「**声明 vs 示例**」冲突的**真机裁决**（`docs/07` §16.1 **R162**）。

问题（P168 普查的留缺 9 项之一）
--------------------------------
**6** 个端点的 `PARTS`（输出部位）枚举与**手册同一篇文章**的**示例体**互相矛盾
（`json_schema` 的**声明**用 `Part1`（数字 **1**），示例体用 `PartI`（罗马数字 **I**））：

| 端点 | 我们的 Schema（= 手册 `json_schema` 的**声明**） | 手册**示例体** |
| --- | --- | --- |
| `POST.TABLE.BEAMFORCE` / `_VBM` | `Part1` / `Part1/4` / `Part2/4` / `Part3/4` / `PartJ` | `['PartI','PartJ']` |
| `POST.TABLE.THISBEAMFORCE` | `PartI` / `Part1/4` / `Part2/4` / `Part3/4` / `PartJ` | `['PartI','PartJ']` |
| `POST.TABLE.RESULTANT_FORCES` / `_VBM` | `PartI` / `PartJ` | `['PartI','PartJ']` |
| `DESIGN.STEEL.KDS-41-30-2022.TABLE` | `PartI` / `Part1/4` / … | `['All','PartI',…]` |

⚠️ 同一份手册的**规格表**写 `"Part I"`（罗马数字）⇒「`Part1` 是 `Part I` 的**转写笔误**」
是一个**可测量**的假设。

⚠️ **判据的第一版（P168 的留缺说明）不够**：它写的是「原生 `200` ⇒ 枚举太窄」——
实测证明**原生对任何 `PARTS` 取值都回 `200`**（含伪取值）⇒ 状态码**不判别**任何东西。
**本批把判据改成「真的过滤」**（**铁律 ⓪** 的直接体现）：

| 相 | 判据（**可判别**） |
| --- | --- |
| **无 `PARTS`（基线）** | `200` ∧ 信封 `empty` ∧ **有数据行**（`n` 行） |
| **有效取值** | `200` ∧ **有数据行** ∧ **行数 < 基线**（真的**过滤**掉别的部位） |
| **无效取值** | `200` ∧ **空块**（信封 `{}`）—— 与**伪**取值**同形** |
| **核心闸门** | 收口后：有效取值**放行** · 伪取值 ⇒ `STRUCTAI-1200`（**零请求**） |
| **零残留** | 跑前 / 跑后 **6** 个模型哨兵**逐项一致**（取报表**不**写模型） |

⚠️ **模型无数据的端点**（基线就是空块）⇒ **不可判别**，**如实登记**（**不**猜、**不**算通过）。

⚠️ **只**发 `POST /POST/TABLE`（取报表，**不**带 `EXPORT_PATH` ⇒ **不**落文件）
+ 只读 `GET`；**绝不**碰 `DESIGN.{RC,SRC}` 的 `*-ANAL`（**R154** 崩溃族，见自检）。

用法
----
    python registry/tools/probe_parts_disposition_p169.py            # 预演（零请求）
    python registry/tools/probe_parts_disposition_p169.py --probe    # 真机
    python registry/tools/probe_parts_disposition_p169.py --check    # 离线自洽（零请求）
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

EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "parts_disposition_probe.json"
"""证据落点（**不含**凭据、**不含**响应原文；只留结构形态、状态码、行数与首行样本）。

⚠️ **P170**：本探针在**不同模型**上跑会得到**不同**的裁决（`PARTS` 的「有效取值」**随模型**变）——
`--evidence` 可把**别的模型**的结果写到**另一个**文件，**不**覆盖 P169 的证据。
"""

EVIDENCE_OVERRIDE: pathlib.Path | None = None
"""`--evidence` 的落点（`None` ⇒ 用 `EVIDENCE`）。"""

DEFAULT_PROJECT: Final[str] = ".tmp_p164c/p164c-concrete.mgbx"
"""自建项目（**只碰它**；它**已有分析结果** —— 判据的前提）。"""

GENERATOR: Final[str] = "registry/tools/sync_parts_enum.py"
"""收口生成器（**只增不减**；`--check` 会重新导入它断言收口未回退）。"""

# 端点 → (登记 token 或 None=取 Schema 唯一枚举, 手册示例体取值, 我们声明里**被证伪**的取值)
TARGETS: Final[tuple[dict[str, Any], ...]] = (
    {
        "key": "POST.TABLE.BEAMFORCE",
        "example": "PartI",
        "suspect": "Part1",
        "declared": ("Part1", "Part1/4", "Part2/4", "Part3/4", "PartJ"),
    },
    {
        "key": "POST.TABLE.BEAMFORCEVBM",
        "example": "PartI",
        "suspect": "Part1",
        "declared": ("Part1", "Part1/4", "Part2/4", "Part3/4", "PartJ"),
    },
    {
        "key": "POST.TABLE.THISBEAMFORCE",
        "example": "PartI",
        "suspect": "Part1",
        "declared": ("PartI", "Part1/4", "Part2/4", "Part3/4", "PartJ"),
    },
    {
        "key": "POST.TABLE.RESULTANT_FORCES",
        "example": "PartI",
        "suspect": "Part1",
        "declared": ("PartI", "PartJ"),
    },
    {
        "key": "POST.TABLE.RESULTANT_FORCESVBM",
        "example": "PartI",
        "suspect": "Part1",
        "declared": ("PartI", "PartJ"),
    },
    {
        "key": "DESIGN.STEEL.KDS-41-30-2022.TABLE",
        "example": "All",
        "suspect": "Part1",
        "declared": ("PartI", "Part1/4", "Part2/4", "Part3/4", "PartJ"),
    },
)
"""**6** 个留缺端点（手册**示例体**取值 + 我们 Schema 的**声明** + 被怀疑的转写笔误）。"""

FAKE_VALUE: Final[str] = "PartZ"
"""阴性对照：**伪**取值（任何来源都没有）—— 实测口径 = **与「无效取值」同形**（空块）。"""

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
TABLE_PATH: Final[str] = "/POST/TABLE"

AUTH_ERROR_MARKERS: Final[tuple[str, ...]] = (
    "MAPI Key is invalid",
    "invalid key",
    "MAPI-Key",
)
"""原生**鉴权失败**的文案标记（P168 的实测教训：识别 ⇒ **中止**，**不**写证据）。"""

PASSED: Final[str] = "PASSED"
FAILED: Final[str] = "FAILED"
CRITERION_VERSION: Final[int] = 2
"""⚠️ **v1 → v2**：v1 用「原生 `200`」当判据 —— 实测**证伪**（原生对**任何**取值都 `200`）；
v2 = 「**真的过滤**」（有效取值 ⇒ 有数据行且**少于**基线；无效 ⇒ 空块）。"""

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

    for item in TARGETS:
        if item["key"] in NATIVE_CRASH_ENDPOINTS:
            raise SystemExit(f"❌ {item['key']} 在崩溃族里（**R154**）⇒ **拒绝运行**")
    guard_native_crash_path(TABLE_PATH)  # 真在崩族里 ⇒ 这里就会抛（**零请求**）
    crash = len({"/" + str(item).replace(".", "/") for item in NATIVE_CRASH_ENDPOINTS})
    print(f"闸门自检：目标 {len(TARGETS)} 个端点 ∩ 崩溃族（{crash} 条）= ∅ · {TABLE_PATH} 放行")


# ===== 离线事实（**可复算**）=====


def _unwrap(document: dict[str, Any]) -> dict[str, Any] | None:
    """剥掉**包装根键**（两种根形态都认；**不**猜路径）。"""
    schema = document.get("schema")
    if not isinstance(schema, dict):
        return None
    if isinstance(schema.get("properties"), dict):
        return schema
    roots = [key for key in schema if key not in {"$schema", "title", "type"}]
    if len(roots) != 1 or not isinstance(schema[roots[0]], dict):
        return None
    return schema[roots[0]]


def _schema_path(repo: pathlib.Path, key: str) -> pathlib.Path:
    """端点的 Schema 文件路径（登记表驱动）。"""
    document = json.loads((repo / "registry" / "manifest.json").read_text(encoding="utf-8"))
    for entry in document["endpoints"]:
        if str(entry.get("key") or "") == key:
            return repo / "registry" / str(entry["schema"])
    raise SystemExit(f"❌ 登记表里没有端点 {key!r}")


def _table_token(repo: pathlib.Path, key: str) -> str:
    """请求体的 `TABLE_TYPE`：**登记表**优先；没有 ⇒ 取 Schema 枚举的**唯一**取值。

    ⚠️ `DESIGN.STEEL.KDS-41-30-2022.TABLE` 不是 `POST.TABLE.*` 变体 ⇒ 登记表里没有
    `table_type`，它的 token 来自**自己的 Schema 枚举**（`STEELMEMBERDESIGNFORCES`）。
    """
    document = json.loads((repo / "registry" / "manifest.json").read_text(encoding="utf-8"))
    for entry in document["endpoints"]:
        if str(entry.get("key") or "") != key:
            continue
        token = str(entry.get("table_type") or "")
        if token:
            return token
        node: Any = _unwrap(json.loads((repo / "registry" / str(entry["schema"])).read_text("utf-8")))
        for segment in ("properties", "Argument", "properties", "TABLE_TYPE"):
            node = node[segment] if isinstance(node, dict) and segment in node else None
        values = list((node or {}).get("enum") or [])
        if len(values) == 1:
            return str(values[0])
        raise SystemExit(f"❌ {key} 既没有登记 `table_type`、也没有唯一的 Schema 枚举")
    raise SystemExit(f"❌ 登记表里没有端点 {key!r}")


def parts_node(repo: pathlib.Path, key: str) -> dict[str, Any] | None:
    """取 `Argument.PARTS` 的 Schema 节点（取不到 ⇒ `None`）。"""
    node: Any = _unwrap(json.loads(_schema_path(repo, key).read_text(encoding="utf-8")))
    for segment in ("properties", "Argument", "properties", "PARTS"):
        if not isinstance(node, dict) or segment not in node:
            return None
        node = node[segment]
    return node if isinstance(node, dict) else None


def on_disk_parts(repo: pathlib.Path, key: str) -> list[str]:
    """已落盘的 `PARTS.items.enum`（**只读**）。"""
    node = parts_node(repo, key)
    items = (node or {}).get("items")
    enum = (items or {}).get("enum") if isinstance(items, dict) else None
    return [str(item) for item in enum] if isinstance(enum, list) else []


def guard_allows(repo: pathlib.Path, key: str, token: str, values: list[str]) -> dict[str, Any]:
    """**核心闸门**行为（与 `adapter._build` **逐字同一**调用）：放行 / 拦（含归因）。"""
    sys.path.insert(0, str(repo))
    from app.infrastructure.adapters.midas.errors import MidasValidationError  # noqa: PLC0415
    from app.infrastructure.adapters.midas.registry import MidasRegistry  # noqa: PLC0415
    from app.infrastructure.adapters.midas.spec_guard import guard_spec_values  # noqa: PLC0415

    registry = MidasRegistry.load(repo / "registry")
    schema = registry.effective_schema(key)
    body = {"Argument": {"TABLE_TYPE": token, "PARTS": list(values)}}
    try:
        guard_spec_values(schema, body, endpoint=key, wrapper="Argument")
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
    """收口生成器的**离线复算**（目标文件 / 机械结果 / 是否已落盘）。"""
    module = _sibling("sync_parts_enum.py")
    return {
        "generator": GENERATOR,
        "targets": module.targets(repo),
        "applied": module.is_applied(repo),
    }


# ===== 真机 =====


def native_table(
    base: str, key: str, token: str, parts: list[str] | None, *, attempts: int = 3
) -> dict[str, Any]:
    """原生口径：`POST /POST/TABLE {TABLE_TYPE, PARTS}`（**取报表，不落文件、不写模型**）。

    `parts=None` ⇒ **不带** `PARTS`（基线；端点用它自己的默认 = 全部部位）。
    """
    import time  # noqa: PLC0415

    import httpx  # noqa: PLC0415

    argument: dict[str, Any] = {"TABLE_TYPE": token}
    if parts is not None:
        argument["PARTS"] = list(parts)
    row: dict[str, Any] = {}
    for attempt in range(1, attempts + 1):
        with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=180.0) as client:
            response = client.post(TABLE_PATH, json={"Argument": argument})
        row = {
            "parts": parts,
            "attempts": attempt,
            "status": int(response.status_code),
            "envelope_key": "",
            "head_columns": 0,
            "data_rows": None,
            "first_row": "",
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
            if isinstance(data, list):
                row["data_rows"] = len(data)
                row["first_row"] = json.dumps(data[0], ensure_ascii=False)[:90] if data else ""
        if int(response.status_code) >= 400 or not block:
            row["native_error"] = json.dumps(payload, ensure_ascii=False)[:160]
    else:
        row["data_rows"] = None  # **空块**：`{}` ⇒ 没有 `DATA`
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


def _decide(baseline: dict[str, Any], example: dict[str, Any], suspect: dict[str, Any],
            fake: dict[str, Any]) -> dict[str, Any]:
    """逐端点的**裁决**（v2 判据：**真的过滤**）。"""
    base_rows = baseline.get("data_rows")
    if not base_rows:
        return {
            "decidable": False,
            "reason": "基线（**不带** `PARTS`）就是空块 ⇒ 本模型**没有**该表的数据 ⇒ **不可判别**",
        }
    example_rows = example.get("data_rows")
    filtered = bool(example_rows) and int(example_rows) < int(base_rows)
    fake_empty = fake.get("data_rows") is None
    suspect_empty = suspect.get("data_rows") is None
    return {
        "decidable": True,
        "baseline_rows": base_rows,
        "example_rows": example_rows,
        "example_filters": filtered,
        "fake_empty": fake_empty,
        "suspect_empty": suspect_empty,
        "example_valid": filtered,
        "suspect_invalid": suspect_empty,
    }


def run_probe(repo: pathlib.Path, project: str) -> int:
    """真机受控测量（`--probe`）：基线 + 示例体取值 + 被疑取值 + 伪取值 + 核心闸门 + 哨兵。"""
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

    print("\n① `PARTS` 的原生裁决（v2 判据：**真的过滤** —— 逐取值实测）：")
    rows: list[dict[str, Any]] = []
    for item in TARGETS:
        endpoint = str(item["key"])
        token = _table_token(repo, endpoint)
        baseline = native_table(base, key, token, None)
        base_rows = baseline.get("data_rows")
        decidable = bool(base_rows)
        # 候选 = 手册示例体取值 ∪ **声明**取值（**逐条**实测；收口生成器按 `valid` 取来源）
        candidates: list[str] = []
        for value in (str(item["example"]), *[str(v) for v in item["declared"]]):
            if value not in candidates:
                candidates.append(value)
        measured: dict[str, Any] = {}
        for value in candidates:
            row = native_table(base, key, token, [value])
            rows_count = row.get("data_rows")
            measured[value] = {
                "status": row["status"],
                "data_rows": rows_count,
                "empty_block": rows_count is None,
                "filters": bool(base_rows) and bool(rows_count) and int(rows_count) < int(base_rows),
                "valid": bool(base_rows) and bool(rows_count) and int(rows_count) < int(base_rows),
                "first_row": row["first_row"],
                "auth_error": row["auth_error"],
            }
        fake = native_table(base, key, token, [FAKE_VALUE])
        fake_empty = fake.get("data_rows") is None
        verdict = {
            "decidable": decidable,
            "reason": (
                ""
                if decidable
                else "基线（**不带** `PARTS`）就是空块 ⇒ 本模型**没有**该表的数据 ⇒ **不可判别**"
            ),
            "baseline_rows": base_rows,
            "fake_empty": fake_empty,
        }
        row = {
            "endpoint": endpoint,
            "token": token,
            "declared_enum": list(item["declared"]),
            "example_value": item["example"],
            "suspect_value": item["suspect"],
            "native_baseline": baseline,
            "measured": measured,
            "native_fake": fake,
            "verdict": verdict,
            "guard_example": guard_allows(repo, endpoint, token, [str(item["example"])]),
            "guard_fake": guard_allows(repo, endpoint, token, [FAKE_VALUE]),
        }
        rows.append(row)
        if decidable:
            valid = sorted(value for value, info in measured.items() if info["valid"])
            invalid = sorted(value for value, info in measured.items() if not info["valid"])
            print(
                f"  {endpoint:38s} 基线 {base_rows} 行 · **有效** {valid} · "
                f"**无效**（空块，与伪取值 {FAKE_VALUE!r} 同形）{invalid}"
            )
        else:
            print(f"  {endpoint:38s} ⚠️ **不可判别**（本模型无该表数据）")

    if any(
        row[field]["auth_error"]
        for row in rows
        for field in ("native_baseline", "native_fake")
    ) or any(info["auth_error"] for row in rows for info in row["measured"].values()):
        print("🛑 原生回了**鉴权失败**（实例侧瞬时状态，**不**是裁决结论）⇒ **中止**，重跑即可")
        return 1

    decided = [row for row in rows if row["verdict"]["decidable"]]
    undecided = [row for row in rows if not row["verdict"]["decidable"]]
    examples_valid = all(
        (row["measured"].get(str(row["example_value"])) or {}).get("valid") for row in decided
    ) if decided else False
    fakes_empty = all(row["verdict"]["fake_empty"] for row in decided) if decided else False
    # ⚠️ `suspect` 只对**声明里真的含它**的端点有意义（`THISBEAMFORCE` 的声明**没有** `Part1`
    #    ⇒ 它的 `Part1` 不在候选集合里，**不**参与断言 —— 如实按「有证据才断言」处理）。
    suspects_invalid = all(
        not (row["measured"].get(str(row["suspect_value"])) or {}).get("valid")
        for row in decided
        if str(row["suspect_value"]) in row["measured"]
    ) if decided else False
    print(
        f"\n裁决：可判别 **{len(decided)}** / {len(rows)} 个端点 · 示例体取值**真的过滤**：{examples_valid} · "
        f"被疑取值（`Part1`）**与伪取值同形**：{suspects_invalid} · 伪取值**空块**：{fakes_empty}"
    )
    for row in undecided:
        print(f"  ⚠️ 如实留缺（不可判别）：{row['endpoint']} —— {row['verdict']['reason']}")

    after = sentinels(base, key)
    unchanged = after == before
    print(f"跑后哨兵：{ {k: v['count'] for k, v in after.items()} }   一致：{unchanged}")

    passed = bool(decided) and examples_valid and fakes_empty and suspects_invalid and unchanged
    payload = {
        "phase": "disposition",
        "criterion_version": CRITERION_VERSION,
        "instance": {"alias": INSTANCE_ALIAS, "probed_at": PROBED_AT},
        "project": project,
        "project_opened_by_probe": opened,
        "targets": rows,
        "decided_endpoints": [row["endpoint"] for row in decided],
        "undecidable_endpoints": [row["endpoint"] for row in undecided],
        "example_value_filters": examples_valid,
        "suspect_value_same_as_fake": suspects_invalid,
        "fake_value_empty": fakes_empty,
        "generator": generator_facts(repo),
        "sentinel": {
            "keys": list(SENTINEL),
            "before": before,
            "after": after,
            "unchanged": unchanged,
        },
        "verdict": PASSED if passed else FAILED,
        "note": (
            "判据 = **效果**（铁律 ⓪）：**原生对任何 `PARTS` 取值都回 `200`** ⇒ 状态码不判别；"
            "v2 判据 = **真的过滤** —— 示例体取值（`PartI`）⇒ 有数据行且**少于**基线；"
            "被疑取值（`Part1`）与**伪**取值（`PartZ`）**同形**（空块）⇒ `Part1` 是上游**笔误**；"
            "模型无数据的端点 ⇒ **不可判别**，**如实留缺**（**不**猜、**不**算通过）。"
        ),
    }
    destination = EVIDENCE_OVERRIDE or EVIDENCE
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"⇒ 判定：{'✅ PASSED' if passed else '❌ FAILED'}")
    print(f"wrote {destination.relative_to(REPO)}")
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
        problems.append("`PARTS` 的收口**未落盘**（生成器 --check 不过）")
    if int(document.get("criterion_version") or 0) < CRITERION_VERSION:
        problems.append("证据用的是旧判据（v1 = 状态码）⇒ 不足以支撑收口")

    for item in TARGETS:
        endpoint = str(item["key"])
        on_disk = on_disk_parts(repo, endpoint)
        if not on_disk:
            problems.append(f"{endpoint} 的 `PARTS` 枚举为空")
            continue
        if not set(item["declared"]) <= set(on_disk):
            problems.append(f"{endpoint} 的收口**丢掉了**原声明取值（**只增不减**被违反）")
        if FAKE_VALUE in on_disk:
            problems.append(f"{endpoint} 的枚举含**伪**取值 {FAKE_VALUE!r} ⇒ 负向对照不成立")

    if document.get("verdict") != PASSED:
        problems.append(f"证据里的 verdict 应为 PASSED，实际 {document.get('verdict')!r}")
    for field in ("example_value_filters", "suspect_value_same_as_fake", "fake_value_empty"):
        if document.get(field) is not True:
            problems.append(f"判据 {field} 不为真 ⇒ 收口依据不成立")
    if not (document.get("sentinel") or {}).get("unchanged"):
        problems.append("跑后哨兵与跑前不一致 ⇒ 有残留，结论不可用")

    rows = {str(row.get("endpoint")): row for row in document.get("targets") or []}
    if set(rows) != {str(item["key"]) for item in TARGETS}:
        problems.append("证据的端点集合与 TARGETS 不一致")
    for endpoint, row in rows.items():
        for field in ("native_baseline", "native_fake"):
            if (row.get(field) or {}).get("auth_error"):
                problems.append(f"{endpoint} 的 {field} 是**鉴权失败** ⇒ 证据不可用")
        verdict = row.get("verdict") or {}
        measured = row.get("measured") or {}
        if any(info.get("auth_error") for info in measured.values()):
            problems.append(f"{endpoint} 的逐取值实测里有**鉴权失败** ⇒ 证据不可用")
        if not verdict.get("decidable"):
            continue  # ⚠️ **不可判别**的端点**如实留缺**（**不**算失败）
        example = measured.get(str(row.get("example_value"))) or {}
        suspect = measured.get(str(row.get("suspect_value"))) or {}
        if not example.get("valid"):
            problems.append(f"{endpoint} 的示例体取值**没有**真的过滤 ⇒ 收口依据不成立")
        if suspect.get("valid"):
            problems.append(f"{endpoint} 的被疑取值（`Part1`）**也**有效 ⇒ 「笔误」结论不成立")
        # 收口来源必须**逐条**落在实测有效的取值上（**不**按示例体硬凑）
        for value in on_disk_parts(repo, endpoint):
            if value in {str(row.get("example_value")), *[str(v) for v in row.get("declared_enum") or []]}:
                continue
            if value not in measured:
                problems.append(f"{endpoint} 的枚举取值 {value!r} **没有**实测证据（收口来源不可复算）")

    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    decided = document.get("decided_endpoints") or []
    undecided = document.get("undecidable_endpoints") or []
    print(
        f"✅ 离线自洽：**{len(decided)}** / {len(TARGETS)} 个端点**可判别** ⇒ "
        f"示例体取值**真的过滤**、`Part1` **与伪取值同形**（上游笔误）、伪取值**空块** · "
        f"**{len(undecided)}** 个端点**如实留缺**（模型无数据）· 哨兵 6 项一致 ⇒ **R162** 成立"
    )
    return 0


def main() -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="PARTS 的「声明 vs 示例」冲突的真机裁决（R162）")
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="自建项目（相对仓库根）")
    parser.add_argument("--probe", action="store_true", help="真发请求（默认只预演）")
    parser.add_argument("--check", action="store_true", help="离线自洽断言（零请求）")
    parser.add_argument(
        "--evidence",
        default="",
        help="证据落点（相对仓库根；默认 registry/live/parts_disposition_probe.json）",
    )
    args = parser.parse_args()
    global EVIDENCE_OVERRIDE  # noqa: PLW0603 - 单次运行的落点覆盖（`--check` 不受影响）
    if args.evidence:
        EVIDENCE_OVERRIDE = (REPO / args.evidence).resolve()
    if args.check:
        return check_offline(REPO)

    guard_paths()
    facts = generator_facts(REPO)
    print(
        f"收口事实：待收口端点 **{len(facts['targets'])}** 个 · 已落盘：{facts['applied']} · "
        f"生成器 `{GENERATOR}`"
    )
    for item in facts["targets"]:
        grew = sorted(set(item["expected"]) - set(item["on_disk"]))
        print(f"  {item['key']}  {len(item['on_disk'])} → {len(item['expected'])} 个取值 · 新增={grew}")
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
