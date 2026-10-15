"""P167 / **R160**：`POST.TABLE` 的 `TABLE_TYPE` 枚举收口 ⇒ 解锁 `RESULT.ANALYSIS.SUMMARY`。

R151 留下的问题（P160e-a 实测）
------------------------------
`RESULT.ANALYSIS.SUMMARY`（`docs/07` §6.7 的**通用取表入口**）在生产路径上
**一个请求都发不出去**：核心自己的 `spec_guard`（**R140**，防弹窗 / 防崩溃）
在**发请求之前**回 `STRUCTAI-1200 value_not_in_spec_enum`。

成因**不是**原生 —— 真机实测 `POST /POST/TABLE {"Argument": {"TABLE_TYPE": "DISPLACEMENTG"}}`
⇒ **`200`** 且 `HEAD` / `DATA` **都有真值**（自建混凝土简支梁的 **63** 行位移结果）。
拦住它的是 `registry/schema/common/post/TABLE.json` 里**只有 2 个取值**的
`TABLE_TYPE.enum`（来自 help center **一篇文章**的 `json_schema`）。

本批的裁决（**数据侧**，`docs/07` §16.1 **R160**）
-------------------------------------------------
枚举的来源换成**两个可复算来源的并集**（生成器 = `registry/tools/sync_table_type_enum.py`）：

* ① **登记表** = `registry/manifest.json` 里已登记的 `POST.TABLE.*` 端点的 `table_type`（**194**）；
* ② **手册声明** = `MIDAS_API_Online_Manual_数据_v1.0.json` 的全部 `json_schema` 里
  `TABLE_TYPE.enum`（**121**）；
* 并集 = **225** ⇒ **严格包含**旧枚举（`WEIGHT_IRREGULARITY_X` / `_Y` 一个不丢）。

⚠️ **只取①会丢掉 `WEIGHT_IRREGULARITY_Y`**（手册声明但未登记成独立端点）⇒ 那是把闸门
**收紧**，与 R151 的教训（枚举**可能不全**）**反向** ⇒ 故取并集。
⚠️ **R140 的保护照旧**：伪 token 两个来源都不在 ⇒ 仍被 `spec_guard` 拦在**发请求之前**（零请求）。

判据（**铁律 ⓪**：效果，**不**是状态码）
--------------------------------------
| 相 | 判据 |
| --- | --- |
| **阳性（原生）** | `POST /POST/TABLE {TABLE_TYPE: <已登记 token>}` ⇒ `200` ∧ 信封**恰好 1 个顶层键** ∧ 其值含 `HEAD` / `DATA` 两个**非空**数组 |
| **阳性（核心）** | 经 MCP Tool 契约 `engineering_result` / `RESULT.ANALYSIS.SUMMARY` ⇒ `success=true` ∧ 规范化结果 `data.result.rows` **非空**（**核心真的解析出数据行**） |
| **阴性（核心）** | 伪 token ⇒ `STRUCTAI-1200 value_not_in_spec_enum` ∧ **零请求**（`spec_guard` 在**发请求之前**拦） |
| **阴性（原生）** | 伪 token ⇒ `400`（原生也拒） |
| **零残留** | 跑前 / 跑后 **6** 个模型哨兵**逐项一致**（取报表**不**写模型） |

⚠️ **两个口径，都要**（`--probe` 与 `--probe --production`）：

* `--probe`（**Contract-Test 口径**，`allow_unverified=True`）—— 在 `availability` **还是**
  `untested` 时**测量效果**（否则可用性闸门会先拦掉，测不到 `spec_guard` 与原生）；
* `--probe --production`（**生产口径**，`allow_unverified=False`）—— 收口 `availability`
  **之后**再跑一次，证明**生产路径本身**已通（不再依赖任何旁路）。

⚠️ 本工具**只**产出证据 —— `availability` 的收口**由人裁决**（同 R159 的先例）；
⚠️ **只**发 `POST /POST/TABLE`（取报表，**不**落文件、**不**写模型）+ 只读 `GET`
（健康检查 / 哨兵）；**绝不**碰 `DESIGN.{RC,SRC}` 的 `*-ANAL`（R154 的崩溃族，见 `GUARDED_PATHS` 自检）。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys
from typing import Any, Final

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
"""仓库根目录（`registry/tools/` 的上两级）。"""

EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "post_table_enum_probe.json"
"""证据落点（**不含**凭据、**不含**响应原文；只留结构形态与计数）。"""

DEFAULT_PROJECT: Final[str] = ".tmp_p164c/p164c-concrete.mgbx"
"""自建项目（**只碰它**；`--project` 可覆盖）。它**已有分析结果**（本判据的前提）。"""

ENDPOINT: Final[str] = "POST.TABLE"
OPERATION: Final[str] = "RESULT.ANALYSIS.SUMMARY"
TOOL: Final[str] = "engineering_result"

TOKEN: Final[str] = "DISPLACEMENTG"
"""阳性用的 **已登记** token（`POST.TABLE.DISPLACEMENTG`，`availability: verified`）。"""

FAKE_TOKEN: Final[str] = "NOT_A_REAL_TABLE_XYZ"
"""阴性对照用的**伪** token（两个来源都不在 ⇒ 必须仍被拦）。"""

HISTORICAL_ENUM: Final[tuple[str, ...]] = ("WEIGHT_IRREGULARITY_X", "WEIGHT_IRREGULARITY_Y")
"""**旧**枚举（收口前落盘的 2 个取值）—— 新枚举必须**严格包含**它们（**只增不减**）。"""

SENTINEL: Final[tuple[str, ...]] = (
    "/DB/NODE",
    "/DB/ELEM",
    "/DB/MATL",
    "/DB/SECT",
    "/DB/STLD",
    "/DB/CNLD",
)
"""零残留哨兵（**6** 项；取报表**不**写模型 ⇒ 跑前 / 跑后必须逐项一致）。"""

HEALTH_PATH: Final[str] = "/DB/NODE"

ALLOWED_PATHS: Final[tuple[str, ...]] = ("/POST/TABLE",)
"""本探针**允许**出现的**写**方法路径（`POST`）—— 其余一律只读 `GET`。

⚠️ `--probe` 前会**显式自检**：这些路径 ∩ `NATIVE_CRASH_ENDPOINTS`（**R154** 的崩溃族，
`DESIGN.{RC,SRC}` 的 `*-ANAL`）= **∅**，且逐个过一遍 `guard_native_crash_path()`
（真在崩族里 ⇒ 那里就会抛，**零请求**）。
"""

ENVELOPE_HEAD: Final[str] = "HEAD"
ENVELOPE_DATA: Final[str] = "DATA"

YAML_RELATIVE: Final[str] = "common/post/TABLE.yaml"
SYNC_TOOL_RELATIVE: Final[str] = "registry/tools/sync_table_type_enum.py"
SYNC_TOOL_FILENAME: Final[str] = "sync_table_type_enum.py"

CRITERION_VERSION: Final[int] = 1
PROBED_AT: Final[str] = "2026-10-15"
INSTANCE_ALIAS: Final[str] = "gen-local"
INSTANCE_PRODUCT: Final[str] = "GEN NX"
PRODUCT_KEY: Final[str] = "GEN_NX"

PASSED: Final[str] = "PASSED"
FAILED: Final[str] = "FAILED"


def _sibling(name: str) -> Any:
    """按路径装载同目录的探针模块（`registry/tools` 不是包）—— **不**复制它的闸门逻辑。"""
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


# ===== 枚举事实（**离线可复算**）=====


def enum_facts(repo: pathlib.Path) -> dict[str, Any]:
    """枚举的**来源 / 规模 / 不变量**（复用 `sync_table_type_enum.py`，**不**另写一套）。"""
    tool = _sibling(SYNC_TOOL_FILENAME)
    registered = tool.registered_table_types(repo)
    manual = tool.manual_table_types(repo)
    enum = tool.expected_enum(repo)
    return {
        "source_tool": SYNC_TOOL_RELATIVE,
        "registered": len(registered),
        "manual": len(manual),
        "union": len(enum),
        "registered_only": len(set(registered) - set(manual)),
        "manual_only": len(set(manual) - set(registered)),
        "historical_enum": list(HISTORICAL_ENUM),
        "superset_of_historical": set(HISTORICAL_ENUM) <= set(enum),
        "token_registered": TOKEN in set(registered),
        "fake_token_absent": FAKE_TOKEN not in set(enum),
        "enum": enum,
    }


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


# ===== 真机 =====


def native_probe(base: str, key: str) -> dict[str, Any]:
    """原生口径：阳性（已登记 token ⇒ 真值）+ 阴性（伪 token ⇒ `400`）。"""
    import httpx  # noqa: PLC0415

    def one(token: str) -> dict[str, Any]:
        with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=180.0) as client:
            response = client.post(
                f"/{ENDPOINT.replace('.', '/')}", json={"Argument": {"TABLE_TYPE": token}}
            )
        row: dict[str, Any] = {
            "token": token,
            "status": int(response.status_code),
            "envelope_key": "",
            "head_columns": 0,
            "head_names": [],
            "data_rows": 0,
        }
        try:
            payload = response.json()
        except ValueError:
            return row
        if not isinstance(payload, dict) or len(payload) != 1:
            return row
        envelope = next(iter(payload))
        block = payload[envelope]
        row["envelope_key"] = str(envelope)
        if isinstance(block, dict):
            head = block.get(ENVELOPE_HEAD)
            data = block.get(ENVELOPE_DATA)
            row["head_columns"] = len(head) if isinstance(head, list) else 0
            row["head_names"] = [str(item) for item in head] if isinstance(head, list) else []
            row["data_rows"] = len(data) if isinstance(data, list) else 0
        return row

    positive = one(TOKEN)
    negative = one(FAKE_TOKEN)
    print(
        f"  原生阳性 {TOKEN} → {positive['status']} · 信封 {positive['envelope_key']!r} · "
        f"HEAD {positive['head_columns']} 列 · DATA {positive['data_rows']} 行"
    )
    print(f"  原生阴性 {FAKE_TOKEN} → {negative['status']}")
    return {"positive": positive, "negative": negative}


def core_row(*, allow_unverified: bool, token: str) -> dict[str, Any]:
    """核心口径：经 MCP Tool 契约跑一次 `RESULT.ANALYSIS.SUMMARY`（复用 `_Stack` / `_read_exercise`）。"""
    import asyncio  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    stack_module = _sibling("probe_interface_paths.py")

    async def run() -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="p167-table-enum-") as raw:
            async with stack_module._Stack(  # noqa: SLF001 - 复用既有装配（**不**复制）
                REPO,
                pathlib.Path(raw),
                read_mode=True,
                allow_unverified=allow_unverified,
            ) as stack:
                return await stack_module._read_exercise(  # noqa: SLF001
                    stack,
                    {
                        "tool": TOOL,
                        "operation": OPERATION,
                        "parameters": {"table_type": token},
                    },
                )

    row = asyncio.run(run())
    row["allow_unverified"] = allow_unverified
    row["parameters"] = {"table_type": token}
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


def _merge(path: pathlib.Path, section: str, payload: Any) -> dict[str, Any]:
    """把一段结果并进证据文件（**累积**：其它段逐字节保留）。"""
    document: dict[str, Any] = {}
    if path.is_file():
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            document = {}
    document["tool"] = "registry/tools/probe_post_table_enum.py"
    document["endpoint"] = ENDPOINT
    document["operation"] = OPERATION
    document["criterion_version"] = CRITERION_VERSION
    document["instance"] = {
        "alias": INSTANCE_ALIAS,
        "product": INSTANCE_PRODUCT,
        "probed_at": PROBED_AT,
    }
    document["enum"] = enum_facts(REPO)
    document[section] = payload
    path.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return document


def _core_verdict(row: dict[str, Any]) -> tuple[bool, str]:
    """核心口径的**效果**判据：`success` ∧ 规范化结果有**真数据行** ∧ 原生 `200`。"""
    requests = list(row.get("requests") or [])
    statuses = [int(item.get("status") or 0) for item in requests]
    rows = int((row.get("readback") or {}).get("count") or 0)
    ok = (
        str(row.get("status")) == PASSED
        and rows > 0
        and bool(statuses)
        and all(200 <= value < 300 for value in statuses)
    )
    return ok, f"status={row.get('status')} rows={rows} http={statuses}"


def _zero_request_rejection(row: dict[str, Any]) -> tuple[bool, str]:
    """阴性对照（核心口径）：`STRUCTAI-1200 value_not_in_spec_enum` ∧ **零请求**。

    ⚠️ 判据要落在**归因**上（R151 的签名）：`native_stage = midas_adapter`
    ⇒ 拦在**核心**（不是原生），`native_endpoint = POST.TABLE`。
    """
    error = row.get("error") or {}
    ok = (
        not (row.get("requests") or [])
        and str(error.get("code") or "") == "STRUCTAI-1200"
        and str(error.get("native_reason") or "") == "value_not_in_spec_enum"
        and str(error.get("native_stage") or "") == "midas_adapter"
        and str(error.get("native_endpoint") or "") == ENDPOINT
    )
    return ok, (
        f"requests={len(row.get('requests') or [])} code={error.get('code')} "
        f"native_reason={error.get('native_reason')} native_stage={error.get('native_stage')}"
    )


def run_probe(repo: pathlib.Path, project: str, *, production: bool) -> int:
    """真机实测（`--probe` = Contract-Test 口径；`--probe --production` = 生产口径）。"""
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
        print("🛑 项目**为空** ⇒ 本判据不适用（取报表需要分析结果；见 R106 的最小模型前置链）")
        return 1

    native = native_probe(base, key)
    if native["positive"]["data_rows"] <= 0 or native["positive"]["head_columns"] <= 0:
        print("🛑 原生阳性**没有真数据行** ⇒ 判据不成立，**不**收口")
        return 1
    if native["negative"]["status"] < 400:
        print("🛑 原生阴性**没有**被拒 ⇒ 负向对照不成立，**不**收口")
        return 1

    print(f"核心口径（allow_unverified={not production}）：")
    positive = core_row(allow_unverified=not production, token=TOKEN)
    positive_ok, positive_detail = _core_verdict(positive)
    print(f"  阳性 {OPERATION} → {positive_detail}")
    negative = core_row(allow_unverified=not production, token=FAKE_TOKEN)
    negative_ok, negative_detail = _zero_request_rejection(negative)
    print(f"  阴性 {FAKE_TOKEN} → {negative_detail}")

    after = sentinels(base, key)
    unchanged = after == before
    print(f"跑后哨兵：{ {k: v['count'] for k, v in after.items()} }   一致：{unchanged}")

    verdict = PASSED if (positive_ok and negative_ok and unchanged) else FAILED
    section = "production" if production else "effect"
    payload = {
        "phase": "production" if production else "contract_test",
        "allow_unverified": not production,
        "native": native,
        "positive": positive,
        "positive_ok": positive_ok,
        "negative_control": negative,
        "negative_control_ok": negative_ok,
        "sentinel": {
            "keys": list(SENTINEL),
            "before": before,
            "after": after,
            "unchanged": unchanged,
        },
        "project": project,
        "project_opened_by_probe": opened,
        "verdict": verdict,
        "note": (
            "判据 = **效果**（铁律 ⓪）：核心规范化结果 `data.result.rows` **非空** ∧ 原生 `200`；"
            "阴性对照 = 伪 token **零请求**被 `spec_guard` 拦（R140 的保护未丢）。"
            + (
                "**生产口径**：`allow_unverified=False`（**无**任何旁路）。"
                if production
                else "**Contract-Test 口径**：`allow_unverified=True`（`availability` 收口**前**测效果）。"
            )
        ),
    }
    _merge(EVIDENCE, section, payload)
    print(f"⇒ {section} 判定：{'✅ PASSED' if verdict == PASSED else '❌ FAILED（**不**收口）'}")
    print(f"wrote {EVIDENCE.relative_to(REPO)}")
    return 0 if verdict == PASSED else 1


# ===== 离线自洽（`--check`，**零请求**）=====


def check_offline(repo: pathlib.Path) -> int:
    """`--check`：证据齐备 + 判据全真 + 与数据侧（枚举 / YAML）一致。"""
    if not EVIDENCE.is_file():
        print(f"❌ 缺证据 {EVIDENCE.relative_to(REPO)}（先跑 --probe）")
        return 1
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    problems: list[str] = []

    facts = enum_facts(repo)
    recorded = document.get("enum") or {}
    for key in ("registered", "manual", "union"):
        if int(recorded.get(key) or 0) != int(facts[key]):
            problems.append(
                f"证据里的枚举 {key}={recorded.get(key)} 与机械结果 {facts[key]} 不一致"
            )
    if not facts["superset_of_historical"]:
        problems.append("新枚举**丢掉**了旧枚举的取值 ⇒ 枚举被收紧（需显式裁决）")
    if not facts["token_registered"]:
        problems.append(f"阳性 token {TOKEN} 不在登记表里 ⇒ 判据用错了取值")
    if not facts["fake_token_absent"]:
        problems.append(f"阴性 token {FAKE_TOKEN} 出现在枚举里 ⇒ 负向对照不成立")

    effect = document.get("effect")
    if not isinstance(effect, dict):
        problems.append("缺 `effect` 段（Contract-Test 口径的效果证据）⇒ 先跑 --probe")
    else:
        if effect.get("verdict") != PASSED:
            problems.append(f"effect.verdict 应为 PASSED，实际 {effect.get('verdict')!r}")
        if effect.get("positive_ok") is not True:
            problems.append("effect 的阳性判据不为真 ⇒ 效果结论不成立")
        if effect.get("negative_control_ok") is not True:
            problems.append("effect 的阴性对照不为真 ⇒ R140 的保护可能已丢")
        if not (effect.get("sentinel") or {}).get("unchanged"):
            problems.append("effect 跑后哨兵与跑前不一致 ⇒ 有残留，结论不可用")
        native = effect.get("native") or {}
        positive = native.get("positive") or {}
        negative = native.get("negative") or {}
        if int(positive.get("data_rows") or 0) <= 0 or int(positive.get("head_columns") or 0) <= 0:
            problems.append("原生阳性没有 HEAD / DATA 真值 ⇒ 「表里真的有数据行」不成立")
        if int(negative.get("status") or 0) < 400:
            problems.append("原生阴性没有被拒 ⇒ 负向对照不成立")

    production = document.get("production")
    if not isinstance(production, dict):
        problems.append("缺 `production` 段（生产口径）⇒ 收口后必须再跑 --probe --production")
    else:
        if production.get("verdict") != PASSED:
            problems.append(f"production.verdict 应为 PASSED，实际 {production.get('verdict')!r}")
        if production.get("positive_ok") is not True:
            problems.append("production 的阳性判据不为真 ⇒ 生产路径仍不通")
        if production.get("allow_unverified") is not False:
            problems.append("production 段必须**不带** allow_unverified（那是旁路）")
        if not (production.get("sentinel") or {}).get("unchanged"):
            problems.append("production 跑后哨兵与跑前不一致 ⇒ 有残留，结论不可用")

    yaml_text = (repo / "registry" / YAML_RELATIVE).read_text(encoding="utf-8")
    if "availability: verified" not in yaml_text:
        problems.append(f"{YAML_RELATIVE} 未按本证据收口（应写 availability: verified）")
    if "gen-local" not in yaml_text:
        problems.append(f"{YAML_RELATIVE} 未记录 verified_on（应含 gen-local）")

    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    print(
        f"✅ 离线自洽：`TABLE_TYPE` 枚举 = 登记表 **{facts['registered']}** ∪ 手册声明 "
        f"**{facts['manual']}** = **{facts['union']}**（**严格包含**旧枚举 ⇒ 只增不减）· "
        f"阳性 `{TOKEN}` 核心解析出真数据行 · 阴性 `{FAKE_TOKEN}` **零请求**仍被 `spec_guard` 拦 · "
        "**生产口径**（无旁路）已通 · 哨兵 6 项一致 ⇒ `POST.TABLE` 收口成立"
    )
    return 0


def main() -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="POST.TABLE 的 TABLE_TYPE 枚举收口证据")
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="自建项目（相对仓库根）")
    parser.add_argument("--probe", action="store_true", help="真发请求（默认只预演）")
    parser.add_argument(
        "--production",
        action="store_true",
        help="生产口径（`allow_unverified=False`；收口 availability **之后**才跑）",
    )
    parser.add_argument("--check", action="store_true", help="离线自洽断言（零请求）")
    args = parser.parse_args()
    repo = REPO
    if args.check:
        return check_offline(repo)

    guard_paths()
    facts = enum_facts(repo)
    print(
        f"`{ENDPOINT}` 的 TABLE_TYPE 枚举：登记表 {facts['registered']} ∪ 手册声明 "
        f"{facts['manual']} = **{facts['union']}**（旧枚举 ⊆ 新枚举：{facts['superset_of_historical']}）"
    )
    print(f"阳性 token = {TOKEN} · 阴性 token = {FAKE_TOKEN} · Operation = {OPERATION}")
    if not args.probe:
        print("\n（预演；加 --probe 才真发）")
        return 0
    print()
    return run_probe(repo, args.project, production=args.production)


if __name__ == "__main__":
    raise SystemExit(main())
