#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为「无 `DELETE` 的单例 / 设置表」落成**取设置表判据**（P149-D / `docs/07` §16.1 **R107**）。

为什么需要这个工具
------------------
GEN NX 上有 **14** 个端点**没有** `DELETE`（`docs/07` §16 R4 / R14 的 L5 三步链第 3 步走不通），
其中 **11** 个有 `GET` + `PUT`（`DB.CLDR` / `DB.CO_F` / `DB.CO_M` / `DB.CO_S` / `DB.CO_T` /
`DB.CPSETTINGS` / `DB.MATD` / `DB.PZEF` / `DB.STYP` / `DB.UNIT` /
`DESIGN.RC.KDS-41-20-2022.SRDF`），另 **3** 个只有 `GET` + `POST`（`OPE.SECTPROP` /
`OPE.STORY_IRR_PARAM` / `OPE.STORY_PARAM`）。它们都是**单例 / 设置表**：**没有**「自建编号」可
读回 / 可删，三步链**结构上不适用**。

判据（R107，**与三步链并列的第三条**；`registry/README.md` §8.14）
------------------------------------------------------------------
1. **前置闸门（**先**做，只读）**：`GET <uri>` 必须返回**非空**原值
   （`{<read_root>: {"1": {…}}}`）。⚠️ **实测**：空项目下 `DB.PZEF` 的 `GET` 是 `{}`，
   而 `PUT` 会**创建**一条记录，且该端点**没有** `DELETE` ⇒ **无法还原** ⇒ 这类端点
   **必须**如实留缺（`empty_singleton_put_creates_undeletable_record`，**不**发 `PUT`）——
   这是**零残留纪律**的硬约束，**不**放宽。
2. **判据** = 「读回原值 → `PUT` **改动过**的值（手册示例；改动逐条记录）→ 读回确认**改动生效**
   → `PUT` **还原**原值（逐字段照抄跑前读回）→ 读回确认**逐字节**等于原值」。
3. 三步链**结构上不适用** ⇒ 本判据的结论**单独成桶**（`no_delete_singleton`），
   **不**并入 L5 三步链的覆盖率分子；**原口径照旧报出、不过滤、不隐藏**。
4. 无 `PUT`（3 个 `OPE.*`）/ 无手册示例 ⇒ **如实留缺**（`no_put_method` / `no_manual_entry`）。

用法（仓库根目录执行；`--probe` 需要 `MIDAS_BASE_URL` / `MIDAS_MAPI_KEY`）
------------------------------------------------------------------------
    python registry/tools/probe_singleton_tables.py --probe     # 有界实测（先闸门后 PUT）
    python registry/tools/probe_singleton_tables.py --write     # availability 只升不降
    python registry/tools/sync_manifest.py --write
    python registry/tools/probe_singleton_tables.py --check     # 断言（不发请求）

纪律
----
* **先闸门后写**：`GET` 为空 ⇒ **绝不**发 `PUT`（会留下**不可删**的记录）。
* **改动必须可逆**：`PUT` 的值来自**手册示例**（可复算）；**还原**的值**逐字段照抄**跑前读回。
* **只升不降**：`--write` 只把 `availability: untested → verified`；`unverified` 一律不碰。
* 证据里**绝不**出现凭据；`PUT` / `GET` 的原文**不**落盘（只记 `sha256` / 判定）。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, NamedTuple

REPO_DEFAULT = "."
EVIDENCE_RELATIVE = "live/singleton_table_probe.json"
MANIFEST_FILENAME = "manifest.json"
CHECK_TOOL_RELATIVE = "registry/tools/check_write_templates.py"
INSTANCE_ALIAS = "gen-local"
INSTANCE_PRODUCT = "GEN_NX"
PROBED_AT = "2026-10-11"

SUB_BUCKET = "no_delete_singleton"
"""R107 的**子桶口径**：无 `DELETE` 的单例 / 设置表（**单独报出**，**不**并入三步链）。"""

VERIFIED = "verified"
UPGRADABLE = ("PASSED",)
PASSED = "PASSED"
FAILED = "FAILED"
SKIPPED = "SKIPPED"

GAP_NO_PUT = "no_put_method"
GAP_EMPTY_SINGLETON = "empty_singleton_put_creates_undeletable_record"
GAP_NO_MANUAL_ENTRY = "no_manual_entry"

RECOVERY: dict[str, str] = {
    GAP_EMPTY_SINGLETON: "non_empty_dedicated_project",
    GAP_NO_PUT: "midas_side_adds_a_put_method",
    GAP_NO_MANUAL_ENTRY: "upstream_manual_entry",
}
"""**留缺的恢复条件**（R119 / P150：**只**更新条件，**不**在空项目上硬试）。

* `empty_singleton_put_creates_undeletable_record`（**7** 个）：`GET` 原值是 `{}` ⇒ `PUT` 会
  **创建**记录而该端点**没有** `DELETE` ⇒ **无法还原**（R116）。恢复条件 = **非空**专用项目
  （该表已有 `1` 号记录，`PUT` 才是「改」而不是「建」）；**没有**非空项目就**如实**保持留缺。
* `no_put_method`（**3** 个）：该端点**没有** `PUT` ⇒ 判据不适用。恢复条件 = **MIDAS 侧**
  提供 `PUT`（或另立判据）。
* `no_manual_entry`（**1** 个）：上游手册**没有**该端点的条目 ⇒ 无「改动过的值」可用。
  恢复条件 = 上游手册补条目。
"""
READ_ROOT_ITEM = "1"
"""单例 / 设置表的读回编号（实测：`{<read_root>: {"1": {…}}}`）。"""


class Plan(NamedTuple):
    """一个端点的判据计划（逐条可复算）。"""

    key: str
    uri: str
    read_root: str
    changed: dict[str, Any]
    example_id: str

    @property
    def changed_sha256(self) -> str:
        """改动值的 `sha256`（证据里**不**落原文）。"""
        canonical = json.dumps(self.changed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


READ_ROOT_ITEM = "1"
"""单例 / 设置表的读回编号（实测：`{<read_root>: {"1": {…}}}`）。"""

NEVER_PUT_EMPTY_ORIGINAL: dict[str, str] = {
    "DB.PZEF": GAP_EMPTY_SINGLETON,
}
"""**空原值** ⇒ **不**发 `PUT` 的端点（`docs/07` §16.1 **R107** 的前置闸门）。

`DB.PZEF`（Panel Zone Effects）：空项目下 `GET /DB/PZEF` → **`{}`**（实测），而 `PUT` 会**创建**
一条记录，且该端点**没有** `DELETE`（`methods = GET, POST, PUT`）⇒ **无法还原** ⇒ 违反零残留纪律。
故它**不**进入可探集（原因码 `empty_singleton_put_creates_undeletable_record`）。

⚠️ **如实记录**：P149-D 的**侦察**阶段曾对它发过一次 `PUT`（写入手册示例的值
`{"OPT_OFFSET": true, "OFFS_FACTOR": 1.0, "OUTPUT_POSITION": 1}`），事后确认**无法清除**
（`PUT {"Assign": {}}` 返回 200 但读回仍在；`PUT {}` → `400 Wrong Field`）⇒ 该记录是**侦察残留**，
见 `docs/reports/P149-D_*.md` 的「残留」一节（**不**声称零残留）。
"""


def load_module(path: Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法装载 {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_tool(repo: Path) -> Any:
    """`check_write_templates.py`（复用**同一套** `normalize_uri()` / `manual_examples()` 口径）。"""
    return load_module(repo / CHECK_TOOL_RELATIVE, "structai_probe_singleton_check")


def manifest_entries(repo: Path) -> dict[str, dict[str, Any]]:
    """`key → manifest 条目`。"""
    document = json.loads((repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    return {str(item["key"]): item for item in document["endpoints"]}


def is_no_delete(entry: dict[str, Any]) -> bool:
    """该条目是否属于 R107 的目标集（GEN NX ∧ 有 `GET` ∧ **无** `DELETE` ∧ 非破坏性）。"""
    if INSTANCE_PRODUCT not in (entry.get("products") or []):
        return False
    if not bool(entry.get("enabled", True)):
        return False
    methods = {part.strip().upper() for part in str(entry.get("methods") or "").split(",")}
    if "GET" not in methods or "DELETE" in methods:
        return False
    if not str((entry.get("wrapper") or {}).get("read_root") or ""):
        return False
    return not bool((entry.get("risk") or {}).get("destructive"))


def targets(repo: Path, only: tuple[str, ...]) -> tuple[str, ...]:
    """目标集（按 key 升序）；`only` 给定时只保留命中的 key。

    ⚠️ 必须**有写方法**（`PUT` / `POST` / `PATCH`）：否则它是**纯读**端点（如
    `OPE.PROJECTSTATUS` / `VIEW.SELECT`），不属于「无 `DELETE` 的单例 / 设置表」这一桶
    （GEN NX 上恰好 **14** 个：11 个 `GET`+`PUT` · 3 个 `GET`+`POST`）。
    """
    keys = [
        key
        for key, entry in manifest_entries(repo).items()
        if is_no_delete(entry)
        and any(
            method in {part.strip().upper() for part in str(entry.get("methods") or "").split(",")}
            for method in ("PUT", "POST", "PATCH")
        )
    ]
    if only:
        wanted = set(only)
        keys = [key for key in keys if key in wanted]
    return tuple(sorted(keys))


def example_body(tool: Any, examples: dict[str, dict[str, dict[str, Any]]], entry: dict[str, Any]) -> tuple[str, dict[str, Any]] | str:
    """手册示例（`Assign` 包装的**改动值**）；取不到 ⇒ 原因码。"""
    uri = tool.normalize_uri(entry.get("uri") or "")
    bucket = examples.get(uri) or {}
    if not bucket:
        return GAP_NO_MANUAL_ENTRY
    title = sorted(bucket)[0]
    body = bucket[title]
    if not isinstance(body, dict) or not isinstance(body.get("Assign"), dict) or not body["Assign"]:
        return GAP_NO_MANUAL_ENTRY
    return title, json.loads(json.dumps(body))


# ===== 只读 / 写入的裸传输 =====


def _client() -> Any:
    """`httpx.Client`（凭据只经环境变量）。"""
    import httpx  # noqa: PLC0415

    base = os.environ.get("MIDAS_BASE_URL", "").rstrip("/")
    key_value = os.environ.get("MIDAS_MAPI_KEY", "")
    if not base or not key_value:
        raise SystemExit("❌ 需要 MIDAS_BASE_URL / MIDAS_MAPI_KEY（见 scripts/load-midas-env.ps1）")
    return httpx.Client(
        base_url=base,
        headers={"MAPI-Key": key_value, "Content-Type": "application/json"},
        timeout=120.0,
    )


def _read(client: Any, uri: str, read_root: str) -> dict[str, Any] | None:
    """读回（只读）；非 200 / 非对象 ⇒ `None`。"""
    response = client.get(uri)
    if response.status_code != 200:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    block = payload.get(read_root)
    return block if isinstance(block, dict) else {}


def _digest(value: Any) -> str:
    """对象的 `sha256`（**不**落原文）。"""
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def probe(repo: Path, only: tuple[str, ...], limit: int, fresh: bool) -> int:
    """有界取设置表实测 → 证据文件（**先闸门后写**；可续跑）。"""
    tool = check_tool(repo)
    examples = tool.manual_examples(repo)
    entries = manifest_entries(repo)
    keys = targets(repo, only)
    if limit:
        keys = keys[:limit]

    plans: dict[str, Plan] = {}
    gaps: dict[str, str] = {}
    for key in keys:
        entry = entries[key]
        if key in NEVER_PUT_EMPTY_ORIGINAL:
            gaps[key] = NEVER_PUT_EMPTY_ORIGINAL[key]
            continue
        methods = {part.strip().upper() for part in str(entry.get("methods") or "").split(",")}
        if "PUT" not in methods:
            gaps[key] = GAP_NO_PUT
            continue
        picked = example_body(tool, examples, entry)
        if isinstance(picked, str):
            gaps[key] = picked
            continue
        title, body = picked
        plans[key] = Plan(
            key=key,
            uri="/" + str(entry["uri"]).lstrip("/"),
            read_root=str((entry.get("wrapper") or {}).get("read_root") or ""),
            changed=body,
            example_id=title,
        )

    print(f"取设置表判据目标 = {len(keys)}（可探 {len(plans)} + 留缺 {len(gaps)}）")
    for reason in (GAP_NO_PUT, GAP_EMPTY_SINGLETON, GAP_NO_MANUAL_ENTRY):
        members = sorted(key for key, value in gaps.items() if value == reason)
        if members:
            print(f"  留缺 [{reason}] = {len(members)} {members}")

    previous = {} if fresh else _previous_rows(repo)
    endpoints: dict[str, dict[str, Any]] = {
        key: row for key, row in previous.items() if key in plans and _conclusive(row)
    }
    if endpoints:
        print(f"续跑：沿用已有结论 {len(endpoints)} 条")
    pending = [key for key in sorted(plans) if key not in endpoints]
    client = _client()
    residue: dict[str, Any] = {}
    aborted = ""
    try:
        for key in pending:
            plan = plans[key]
            endpoints[key] = _probe_key(client, plan)
        residue["final_reads"] = {
            key: _digest(_read(client, plans[key].uri, plans[key].read_root))
            for key in sorted(endpoints)
            if str(endpoints[key].get("verdict")) == PASSED
        }
    except Exception as error:  # noqa: BLE001 - 传输失败如实中止
        aborted = f"{type(error).__name__}: {error}"
        print(f"  ⚠️ {aborted}")
        residue["final_reads"] = {}
    finally:
        client.close()

    counts: dict[str, int] = {}
    for row in endpoints.values():
        verdict = str(row.get("verdict"))
        counts[verdict] = counts.get(verdict, 0) + 1
    restored = sum(
        1
        for key, row in endpoints.items()
        if row.get("verdict") == PASSED and residue["final_reads"].get(key) == row.get("original_sha256")
    )
    document = {
        "note": [
            "P149-D / R107：**无 `DELETE` 的单例 / 设置表**的取设置表判据实测证据（**子桶**口径）。",
            "判据：`GET` 读回**非空**原值（**空 ⇒ 如实留缺**：`PUT` 会创建**不可删**的记录）"
            "⇒ `PUT` 手册示例（**改动过**的值）⇒ 读回确认**改动生效** ⇒ `PUT` **还原**原值"
            "（逐字段照抄跑前读回）⇒ 读回确认**逐字节**等于原值。",
            "⚠️ 三步链（创建 → 读回 → 按路径 key 删除）对本桶**结构上不适用**（无 `DELETE`）"
            "⇒ 结论**单独成桶**，**不**并入 L5 覆盖率分子；原口径照旧报出、不过滤、不隐藏。",
            "生成器 = `registry/tools/probe_singleton_tables.py --probe`；落盘 = `--write`"
            "（`availability` **只升不降**），随后跑 `sync_manifest.py --write`。",
            "凭据**绝不**写入本文件；读回 / 写回的原文**不**落盘（只记 `sha256`）。",
            "**R119**：留缺**逐条**给出恢复条件（`recovery`）—— 空原值单例表的恢复条件 = "
            "**非空**专用项目（`PUT` 才是「改」而不是「建」；空项目上 `PUT` 会留下**不可删**的记录，"
            "见 **R116**）；**没有**非空项目就**如实**保持留缺，**不**硬试。",
        ],
        "instance": {
            "alias": INSTANCE_ALIAS,
            "product": INSTANCE_PRODUCT,
            "base_url": os.environ.get("MIDAS_BASE_URL", "").rstrip("/"),
            "probed_at": PROBED_AT,
            "scope": "GEN_NX ∧ enabled ∧ 有 GET ∧ 无 DELETE ∧ 非 destructive ∧ 有 read_root",
        },
        "sub_bucket": SUB_BUCKET,
        "counts": counts,
        "restored": restored,
        "aborted": aborted,
        "residue": residue,
        "gaps": dict(sorted(gaps.items())),
        "recovery": {reason: RECOVERY.get(reason, "") for reason in sorted(gaps.values())},
        "endpoints": dict(sorted(endpoints.items())),
    }
    path = repo / "registry" / EVIDENCE_RELATIVE
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "汇总 =", counts,
        " 已还原 =", restored, "/", counts.get(PASSED, 0),
        " 零残留 =", restored == counts.get(PASSED, 0),
    )
    print(f"已写入 registry/{EVIDENCE_RELATIVE}")
    return 1 if aborted else 0


def _probe_key(client: Any, plan: Plan) -> dict[str, Any]:
    """单端点：**先闸门后写**（空原值 ⇒ 如实留缺，**绝不**发 `PUT`）。"""
    row: dict[str, Any] = {
        "uri": plan.uri,
        "read_root": plan.read_root,
        "example_id": plan.example_id,
        "changed_sha256": plan.changed_sha256,
        "sub_bucket": SUB_BUCKET,
    }
    try:
        original = _read(client, plan.uri, plan.read_root)
    except Exception as error:  # noqa: BLE001
        return {**row, "verdict": SKIPPED, "detail": type(error).__name__}
    if original is None:
        return {**row, "verdict": SKIPPED, "detail": "read_failed"}
    row["original_sha256"] = _digest(original)
    if not original:
        # **先闸门后写**：空原值 ⇒ **绝不**发 `PUT`（会留下**不可删**的记录）。
        return {**row, "verdict": FAILED, "detail": GAP_EMPTY_SINGLETON, "put_sent": False}
    row["put_sent"] = True
    changed_response = client.put(plan.uri, json=plan.changed)
    after_change = _read(client, plan.uri, plan.read_root)
    row["changed_status"] = changed_response.status_code
    row["change_effective"] = bool(after_change) and _digest(after_change) != row["original_sha256"]
    restore_response = client.put(plan.uri, json={"Assign": {READ_ROOT_ITEM: original[READ_ROOT_ITEM]}})
    after_restore = _read(client, plan.uri, plan.read_root)
    row["restore_status"] = restore_response.status_code
    row["restored_sha256"] = _digest(after_restore) if after_restore is not None else ""
    row["restore_byte_identical"] = row["restored_sha256"] == row["original_sha256"]
    if row["change_effective"] and row["restore_byte_identical"]:
        return {**row, "verdict": PASSED, "detail": ""}
    return {
        **row,
        "verdict": FAILED,
        "detail": "change_not_effective" if not row["change_effective"] else "restore_mismatch",
    }


def _previous_rows(repo: Path) -> dict[str, dict[str, Any]]:
    """上次证据文件里的逐条结论（缺 / 读不动 ⇒ 空）。"""
    path = repo / "registry" / EVIDENCE_RELATIVE
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = document.get("endpoints")
    return rows if isinstance(rows, dict) else {}


def _conclusive(row: dict[str, Any]) -> bool:
    """该行是否已取得结论（`SKIPPED` 会重测）。"""
    return str(row.get("verdict")) in (PASSED, FAILED)


# ===== 落盘 / 断言 =====


def load_evidence(repo: Path) -> dict[str, Any]:
    """读证据文件。"""
    path = repo / "registry" / EVIDENCE_RELATIVE
    if not path.is_file():
        raise SystemExit(f"❌ 缺证据文件 registry/{EVIDENCE_RELATIVE}（先跑 --probe）")
    return json.loads(path.read_text(encoding="utf-8"))


def endpoint_files(repo: Path) -> dict[str, Path]:
    """`key → YAML 路径`。"""
    document = json.loads((repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    return {
        str(item["key"]): repo / "registry" / str(item["definition"])
        for item in document["endpoints"]
    }


def upgrade_lines(text: str, alias: str) -> tuple[str, bool]:
    """`availability: untested → verified` + `verified_on` 合并（**只升不降**）。"""
    import yaml  # noqa: PLC0415

    lines = text.splitlines(keepends=True)
    availability_index = None
    verified_index = None
    for index, line in enumerate(lines):
        if line.startswith("availability:"):
            availability_index = index
        elif line.startswith("verified_on:"):
            verified_index = index
    if availability_index is None or lines[availability_index].strip() != "availability: untested":
        return text, False
    lines[availability_index] = "availability: verified\n"
    if verified_index is None:
        lines.insert(availability_index + 1, f'verified_on: ["{alias}"]\n')
    else:
        current = yaml.safe_load("".join(lines))["verified_on"]
        names = [str(item) for item in current]
        if alias not in names:
            names.append(alias)
            rendered = ", ".join(f'"{name}"' for name in names)
            lines[verified_index] = f"verified_on: [{rendered}]\n"
    return "".join(lines), True



def read_availability(path: Path) -> tuple[str, list[str]]:
    """YAML 里的 `(availability, verified_on)`。"""
    import yaml  # noqa: PLC0415

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    verified_on = document.get("verified_on") or []
    return str(document.get("availability") or ""), [str(item) for item in verified_on]


def write_back(repo: Path) -> int:
    """据证据收口 `availability`（**只升不降**）。"""
    evidence = load_evidence(repo)
    files = endpoint_files(repo)
    upgraded: list[str] = []
    for key, row in sorted(evidence["endpoints"].items()):
        if str(row.get("verdict")) not in UPGRADABLE:
            continue
        text, modified = upgrade_lines(files[key].read_text(encoding="utf-8"), INSTANCE_ALIAS)
        if modified:
            files[key].write_text(text, encoding="utf-8")
            upgraded.append(key)
    print(f"availability 收口 = {len(upgraded)} {upgraded}")
    print("⚠️ 请接着跑：python registry/tools/sync_manifest.py --write")
    return 0


def check(repo: Path) -> int:
    """断言：数据侧 == 取设置表证据（**不**发请求）。"""
    evidence = load_evidence(repo)
    files = endpoint_files(repo)
    errors: list[str] = []
    for key, row in sorted(evidence["endpoints"].items()):
        availability, verified_on = read_availability(files[key])
        if str(row.get("verdict")) in UPGRADABLE:
            if availability != VERIFIED:
                errors.append(f"{key}: availability = {availability!r}（证据 verdict = PASSED）")
            elif INSTANCE_ALIAS not in verified_on:
                errors.append(f"{key}: verified_on = {verified_on}（缺 {INSTANCE_ALIAS!r}）")
            if row.get("restore_byte_identical") is not True:
                errors.append(f"{key}: PASSED 必须已**逐字节**还原原值")
        elif str(row.get("verdict")) == FAILED:
            # ⚠️ **不**断言 `availability != verified`：`availability`（§4：至少一个实例 GET 成功）
            # 与本判据（取设置表判据）是**两个不同的判定**，前者由 `sync_availability.py` 拥有。
            # 这里断言的是**本判据**的硬约束：空原值 ⇒ **零副作用**（**没有**发 `PUT`）。
            if row.get("put_sent") is not False:
                errors.append(f"{key}: FAILED 必须**没有**发 `PUT`（空原值 ⇒ 会留下不可删的记录）")
            if str(row.get("detail")) != GAP_EMPTY_SINGLETON:
                errors.append(f"{key}: FAILED 的原因必须是 {GAP_EMPTY_SINGLETON}")
    if errors:
        print("❌ 与取设置表证据不一致：")
        for line in errors:
            print("  ", line)
        return 1
    print(
        f"✅ 与取设置表证据一致（子桶 {evidence['sub_bucket']}："
        f"PASSED {sum(1 for r in evidence['endpoints'].values() if r.get('verdict') == PASSED)} · "
        f"FAILED {sum(1 for r in evidence['endpoints'].values() if r.get('verdict') == FAILED)} · "
        f"留缺 {len(evidence.get('gaps') or {})}）"
    )
    return 0


def refresh_recovery(repo: Path) -> int:
    """**离线**补齐 `recovery`（R119 / P150）：**只**加**派生**字段与说明行，**不**发任何请求。

    ⚠️ 本模式**不**改任何结论：`counts` / `restored` / `residue` / `gaps` / `endpoints`
    **逐字节保留**；`recovery` 完全由**已记录的** `gaps` 派生（`RECOVERY` 常量）。
    空原值单例表的恢复条件 = **非空**专用项目 —— **没有**就**如实**保持留缺（**不**硬试，R116）。
    """
    path = repo / "registry" / EVIDENCE_RELATIVE
    if not path.is_file():
        print(f"❌ 缺证据文件 registry/{EVIDENCE_RELATIVE}（先跑 --probe）")
        return 1
    document = json.loads(path.read_text(encoding="utf-8"))
    gaps = document.get("gaps") or {}
    document["recovery"] = {
        str(reason): RECOVERY.get(str(reason), "") for reason in sorted(set(gaps.values()))
    }
    line = (
        "**R119**：留缺**逐条**给出恢复条件（`recovery`）—— 空原值单例表的恢复条件 = "
        "**非空**专用项目（`PUT` 才是「改」而不是「建」；空项目上 `PUT` 会留下**不可删**的记录，"
        "见 **R116**）；**没有**非空项目就**如实**保持留缺，**不**硬试。"
    )
    note = document.setdefault("note", [])
    if line not in note:
        note.append(line)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已离线补齐 recovery = {document['recovery']}")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=REPO_DEFAULT)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--only", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument(
        "--refresh-recovery",
        action="store_true",
        help="**离线**补齐 `recovery`（R119；不发任何请求、不改任何结论）",
    )
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    only = tuple(part.strip() for part in args.only.split(",") if part.strip())

    status = 0
    if args.probe:
        status = max(status, probe(repo, only, args.limit, args.fresh))
    if args.write:
        status = max(status, write_back(repo))
    if args.check:
        status = max(status, check(repo))
    if args.refresh_recovery:
        status = max(status, refresh_recovery(repo))
    if not (args.probe or args.write or args.check or args.refresh_recovery):
        print(__doc__)
    return status


if __name__ == "__main__":
    sys.exit(main())
