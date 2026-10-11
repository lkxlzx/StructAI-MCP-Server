#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为「结果表 / 文本查询」端点（`POST.*`）落成**取报表判据**（P149-D / `docs/07` §16.1 **R106**）。

为什么需要这个工具
------------------
`POST.*` 的 **197** 个端点（GEN NX：`POST.TABLE.*` **194** + `POST.PM` / `POST.TEXT` /
`POST.STEELCODECHECK`）在 `docs/07` §16 R4 / R14 的 **L5 三步链**（创建 → 读回 → 按路径 key 删除）
下**结构上不适用**：它们**只**有 `POST`、**没有** `GET` / `read_root`，请求体是
`Argument.TABLE_TYPE`（取表），响应就是表本身 —— **没有「自建 ID」可读回、可删**。
故 P149-C 之前它们一律落在「无读回」桶里，**从未取得结论**。

判据（R106，**与三步链并列的第二条判据**；`registry/README.md` §8.13）
------------------------------------------------------------------
在**已分析**的专用空项目上，对每个端点：

1. **前置链** = 最小模型（`MINIMAL_MODEL`，**只**用自建编号）+ `POST /DOC/ANAL`（空体 = 执行分析）；
   —— 实测确认（P149-D 侦察）：空项目下 `POST /POST/TABLE` → `400
   "[empty] Cannot generate table data as there is no analysis result."` ⇒ **必须有分析结果**，
   故判据**必须**带最小模型前置链（**不**放宽）。
2. **请求体** = 上游手册里该端点**自己那张表**的示例（定位见 `select_example()`），
   并**唯一**改动 = **剥掉 `Argument.EXPORT_PATH`**（带它会让实例**落文件**，违反零副作用纪律）；
   改动逐条记进证据的 `adjustments`，body 另存 `sha256`（**不**落原文）。
3. **判定** = `HTTP 200` ∧ **实测信封形状**（恰好 1 个顶层键 ∧ 其值是对象 ∧ 同时含 `HEAD` 与
   `DATA` 两个数组）⇒ `PASSED`（**实测到的键逐条记进证据的 `envelope_key`** —— 键名逐端点
   不同，多数是 `Example`，也有表自己的名字与字面 `empty`）；
   `HTTP 200` ∧ **空块**（`{}` 或 `{"message": ""}`）⇒ `PARTIAL`（该表在最小模型上**无数据**，
   与 P134 的 `EMPTY_BLOCK_KEY` 同口径）；
   其余状态码 / 非预期形状 ⇒ `FAILED`；传输失败 ⇒ `SKIPPED`。
4. **零残留** = 跑前 / 跑后模型哨兵（7 个 `DB.*`）**逐条相同**（取报表**不**写模型数据 ⇒ 只读）；
   跑完**逆序**清理自建模型，清理后再核对哨兵**全空**。
5. 无示例 / 无法机械定位示例 ⇒ **如实留缺**（`gaps`，`no_manual_entry` /
   `no_example_for_table_type` / `no_example_by_title`），**不**猜字段、**不**发请求。

用法（仓库根目录执行；`--probe` 需要 `MIDAS_BASE_URL` / `MIDAS_MAPI_KEY`）
------------------------------------------------------------------------
    # 有界实测（默认 20 条一块，块间只读健康检查；可只测一部分）
    python registry/tools/probe_result_tables.py --probe
    python registry/tools/probe_result_tables.py --probe --only POST.PM,POST.TEXT

    # 据证据落盘（YAML `availability` 只升不降 + 追加 `response` 块）
    python registry/tools/probe_result_tables.py --write
    python registry/tools/sync_manifest.py --write

    # 断言一致（CI 用；**不**发任何请求）
    python registry/tools/probe_result_tables.py --check

纪律
----
* **绝不**发原生试探：每块 ≤ `CHUNK_SIZE`（20）条，块间只读健康检查 `GET /DB/NODE`；
  健康检查非 200 ⇒ **立即中止**（P149-B2 两次实例崩溃的教训）。
* **只碰自建编号**：最小模型只用 `1` / `2`；清理**逆序**且**必带路径 key**。
* **不改写任何既有判定**：`--write` 只做两件事 —— `availability: untested → verified`
  （**只升不降**，`unverified` 一律不碰）与**追加** `response` 块；`methods` / `products` /
  `verification_status` / `request` Schema 一律不动。
* 证据文件与 YAML 里**绝不**出现凭据（`MAPI-Key` 只经环境变量注入），也**不**落请求体 / 响应体原文。
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
EVIDENCE_RELATIVE = "live/result_table_probe.json"
MANIFEST_FILENAME = "manifest.json"
CHECK_TOOL_RELATIVE = "registry/tools/check_write_templates.py"
INSTANCE_ALIAS = "gen-local"
INSTANCE_PRODUCT = "GEN_NX"
PROBED_AT = "2026-10-11"

NAMESPACE = "POST"
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")

ENVELOPE_HEAD = "HEAD"
ENVELOPE_DATA = "DATA"
"""**实测信封**：`POST.*` 取报表端点在有数据时的响应**形状**（`docs/07` §16.1 **R106** 的判据）。

P149-D 实测（197 条目标集全量、两次批量）：`200` 的**有数据**响应**一律**是

    {"<信封键>": {"FORCE": …, "DIST": …, "HEAD": [列名…], "DATA": [[行…]]}}

⚠️ **信封键是逐端点不同的**（**不**是全局常量）：多数表是 `"Example"`，但实测还有
`"ElementPropertiesatEachStage"` / `"TendonGroup"` / `"TendonProfile"` / `"TendonProperty"`
（表自己的名字）与 `"empty"`（该表的字面键名）。故判据**只**断言**形状**（恰好 1 个顶层键、
其值是**对象**、含 `HEAD` 与 `DATA` 两个**数组**），并把**实测到的键**逐端点记进证据
（`envelope_key`）后落成该端点的 `response` 块 —— 这**不**是从 URI / 手册猜的
（`registry/README.md` §8.1 的同一条纪律）。
"""

CRITERION_VERSION = 2
"""判据版本：证据行**必须**带同一版本才算「已取得结论」（判据修订后**自动**重测）。"""

EMPTY_BLOCK_KEY = "message"
"""**实测空块**：`200` ∧ 顶层键只有 `message` 且其值为空串 ⇒ `PARTIAL`（与 `live.EMPTY_BLOCK_KEY` 同口径）。"""

RESPONSE_SOURCE = "l4_measured_envelope"
DIALECT = "https://json-schema.org/draft/2020-12/schema"

VERIFIED = "verified"
UPGRADABLE = ("PASSED", "PARTIAL")

PASSED = "PASSED"
PARTIAL = "PARTIAL"
FAILED = "FAILED"
SKIPPED = "SKIPPED"

CHUNK_SIZE = 20
HEALTH_PATH = "/DB/NODE"
SENTINELS = ("NODE", "ELEM", "MATL", "SECT", "STLD", "CONS", "BMLD")
"""空项目哨兵（与 `write_probe.EMPTINESS_GATE_KEYS` / P140 的 `SENTINELS` 同口径）。"""

MINIMAL_MODEL: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("STLD", "1", {"NAME": "D", "TYPE": "D", "DESC": "DeadLoads"}),
    (
        "MATL",
        "1",
        {
            "TYPE": "STEEL",
            "NAME": "DB_Steel",
            "HE_SPEC": 0,
            "HE_COND": 0,
            "PLMT": 0,
            "P_NAME": "",
            "bMASS_DENS": False,
            "DAMP_RAT": 0.02,
            "PARAM": [
                {
                    "P_TYPE": 1,
                    "STANDARD": "EN05(S)",
                    "CODE": "",
                    "DB": "S450",
                    "bELAST": False,
                    "ELAST": 210000000,
                }
            ],
        },
    ),
    (
        "SECT",
        "1",
        {
            "SECTTYPE": "DBUSER",
            "SECT_NAME": "LT_Const",
            "SECT_BEFORE": {
                "OFFSET_PT": "LT",
                "HORZ_OFFSET_OPT": 0,
                "VERT_OFFSET_OPT": 0,
                "USE_SHEAR_DEFORM": False,
                "USE_WARPING_EFFECT": False,
                "SHAPE": "SB",
                "DATATYPE": 2,
                "SECT_I": {"vSIZE": [1, 1]},
            },
        },
    ),
    ("NODE", "1", {"X": 0.0, "Y": 0.0, "Z": 0.0}),
    ("NODE", "2", {"X": 1.0, "Y": 0.0, "Z": 0.0}),
    ("ELEM", "1", {"TYPE": "BEAM", "MATL": 1, "SECT": 1, "NODE": [1, 2], "ANGLE": 0}),
    ("CONS", "1", {"ITEMS": [{"ID": 1, "GROUP_NAME": "", "CONSTRAINT": "1111000"}]}),
    (
        "BMLD",
        "1",
        {
            "ITEMS": [
                {
                    "ID": 1,
                    "LCNAME": "D",
                    "GROUP_NAME": "",
                    "CMD": "BEAM",
                    "TYPE": "UNILOAD",
                    "DIRECTION": "GZ",
                    "USE_PROJECTION": False,
                    "USE_ECCEN": False,
                    "D": [0, 1, 0, 0],
                    "P": [-50, -50, 0, 0],
                }
            ]
        },
    ),
)
"""最小模型（**只**用自建编号；与 P140 的 `LIVE_MODEL` 同源、逐字节一致）。

`SECT_BEFORE.DATATYPE` / `SECT_I` 是本 build 自省（`GET /info/db/SECT`）声明、且手册示例实际使用的
字段 —— 数据侧请求 Schema 曾缺这两个（**R112**，P149-D 已按自省来源补齐）。
"""

DOC_ANAL_URI = "/DOC/ANAL"
DOC_ANAL_WRAPPER = "Argument"

GAP_NO_MANUAL_ENTRY = "no_manual_entry"
GAP_NO_EXAMPLE_FOR_TABLE_TYPE = "no_example_for_table_type"
GAP_NO_EXAMPLE_BY_TITLE = "no_example_by_title"
GAP_CRASHES_INSTANCE = "crashes_instance"

EXPORT_PATH = "EXPORT_PATH"

INSTANCE_DOWN_MARKER = "The project is not opened"
"""实例崩溃后重启会**关闭项目**，其原生响应就是这句 —— 该形态**不**算「端点被拒」。"""

NEVER_RETRY: dict[str, str] = {
    "POST.TABLE.FIBR_MAXCONTRACT": "R115",
}
"""**永不再试**的取报表端点（使 NX 实例**崩溃**；`docs/07` §16.1 **R115**）。

`POST.TABLE.FIBR_MAXCONTRACT`（Fiber Model 最大压应变）在 P149-D 实测**两次**让实例崩溃：
① 全量批量第 41 条（响应 `ReadError` ⇒ 连接被断开 ⇒ 实例重启 ⇒ 后续 `400 The project is not
opened`）；② **单独**一条（建完最小模型 + `DOC.ANAL` 后只发这一条）复现同样的连接被拒
（`WinError 10061`）⇒ 归因**确定**，不是累积负载。成因需 **MIDAS 侧**排查（数据侧无法从证据推出）。"""


class Selection(NamedTuple):
    """一个端点的**取报表请求体**定位（逐条可复算）。"""

    uri: str
    wrapper: str
    example_id: str
    example_title: str
    body: dict[str, Any]
    adjustments: tuple[dict[str, Any], ...]

    @property
    def body_sha256(self) -> str:
        """实际发出请求体的 `sha256`（证据里**不**落原文）。"""
        canonical = json.dumps(self.body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    return load_module(repo / CHECK_TOOL_RELATIVE, "structai_probe_result_tables_check")


def manifest_entries(repo: Path) -> dict[str, dict[str, Any]]:
    """`key → manifest 条目`（唯一权威索引）。"""
    document = json.loads((repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    return {str(item["key"]): item for item in document["endpoints"]}


def is_result_query(entry: dict[str, Any]) -> bool:
    """该条目是否属于 R106 的目标集（`POST.*` ∧ GEN NX 可得 ∧ 无读回 ∧ 有写方法）。

    判据只看**数据侧**事实：`namespace` / `products` / `enabled` / `methods` / `wrapper.read_root`。
    与 `_derived_candidates()` 的「无读回」桶同源（GEN NX 的 `POST.*` = **197**）。
    """
    if str(entry.get("namespace") or "") != NAMESPACE:
        return False
    if INSTANCE_PRODUCT not in (entry.get("products") or []):
        return False
    if not bool(entry.get("enabled", True)):
        return False
    methods = {part.strip().upper() for part in str(entry.get("methods") or "").split(",")}
    if not any(method in methods for method in WRITE_METHODS):
        return False
    if "GET" in methods:
        return False
    return not str((entry.get("wrapper") or {}).get("read_root") or "")


def targets(repo: Path, only: tuple[str, ...]) -> tuple[str, ...]:
    """目标集（按 key 升序）；`only` 给定时只保留命中的 key。"""
    keys = [key for key, entry in manifest_entries(repo).items() if is_result_query(entry)]
    if only:
        keys = [key for key in keys if key in set(only)]
    return tuple(sorted(keys))


def _strip_example_suffix(title: str) -> str:
    """示例名 → 可比较的标题（剥掉尾部 ` #<n>`，小写）。"""
    text = str(title).strip()
    if " #" in text:
        head, _, tail = text.rpartition(" #")
        if tail.strip().isdigit():
            text = head.strip()
    return text.lower()


def _argument(body: Any) -> dict[str, Any]:
    """示例 JSON 的内层 `Argument`（取不到 → 空字典）。"""
    if not isinstance(body, dict):
        return {}
    argument = body.get("Argument")
    return argument if isinstance(argument, dict) else {}


def select_example(
    tool: Any,
    examples: dict[str, dict[str, dict[str, Any]]],
    entry: dict[str, Any],
) -> Selection | str:
    """该端点的**取报表请求体**（定位失败 → 如实的原因码）。

    定位判据（逐条可复算；`registry/README.md` §8.13）：

    1. 候选 = 上游手册（**两个来源**合并）里该端点 `uri` 下的**全部**条目；
    2. `table_type` 非空 ⇒ 先按 `Argument.TABLE_TYPE`（或 `Argument.TEXT_TYPE`）**精确**匹配；
    3. 未命中（或 `table_type` 为空）⇒ 按**端点 `title`** 与示例名（剥掉尾部 ` #<n>`）做
       大小写无关的**前缀**匹配；
    4. 仍多解 ⇒ 取**字典序第一个**并在证据里记 `example_candidates`（多形态端点**只**探其中一个
       形态，其余形态**不**声称覆盖）；
    5. 仍无解 ⇒ 返回原因码（**不**猜、**不**发请求）。
    """
    uri = tool.normalize_uri(entry.get("uri") or "")
    bucket = examples.get(uri) or {}
    if not bucket:
        return GAP_NO_MANUAL_ENTRY

    table_type = str(entry.get("table_type") or "")
    chosen: list[str] = []
    if table_type:
        for title in sorted(bucket):
            argument = _argument(bucket[title])
            token = str(argument.get("TABLE_TYPE") or argument.get("TEXT_TYPE") or "")
            if token == table_type:
                chosen.append(title)
        if not chosen:
            return GAP_NO_EXAMPLE_FOR_TABLE_TYPE

    if not chosen:
        wanted = _strip_example_suffix(entry.get("title") or "")
        if wanted:
            chosen = [title for title in sorted(bucket) if _strip_example_suffix(title).startswith(wanted)]
        if not chosen:
            return GAP_NO_EXAMPLE_BY_TITLE

    title = chosen[0]
    body = json.loads(json.dumps(bucket[title]))
    adjustments: list[dict[str, Any]] = []
    argument = body.get("Argument") if isinstance(body, dict) else None
    if isinstance(argument, dict) and EXPORT_PATH in argument:
        adjustments.append(
            {
                "path": ["Argument", EXPORT_PATH],
                "from": argument[EXPORT_PATH],
                "to": None,
                "why": "R106：不带 EXPORT_PATH（带它会让实例落文件，违反零副作用纪律）",
            }
        )
        del argument[EXPORT_PATH]
    return Selection(
        uri=uri,
        wrapper=str((entry.get("wrapper") or {}).get("write") or "none"),
        example_id=title,
        example_title=title,
        body=body,
        adjustments=tuple(adjustments),
    )


# ===== 只读 / 写入的裸传输（**只**发工具自己构造的请求）=====


def _client() -> Any:
    """`httpx.Client`（凭据只经环境变量；缺任一 ⇒ 拒绝执行）。"""
    import httpx  # noqa: PLC0415

    base = os.environ.get("MIDAS_BASE_URL", "").rstrip("/")
    key_value = os.environ.get("MIDAS_MAPI_KEY", "")
    if not base or not key_value:
        raise SystemExit(
            "❌ 需要 MIDAS_BASE_URL / MIDAS_MAPI_KEY（见 scripts/load-midas-env.ps1）"
        )
    return httpx.Client(
        base_url=base,
        headers={"MAPI-Key": key_value, "Content-Type": "application/json"},
        timeout=180.0,
    )


def _read_sentinels(client: Any) -> dict[str, list[str]]:
    """模型哨兵（**只读**）：`/DB/<CODE>` 的现有编号（升序）。"""
    snapshot: dict[str, list[str]] = {}
    for code in SENTINELS:
        payload = client.get(f"/DB/{code}").json()
        block = payload.get(code) if isinstance(payload, dict) else None
        snapshot[code] = sorted(str(item) for item in (block or {}))
    return snapshot


def _health(client: Any) -> int:
    """块间只读健康检查（`GET /DB/NODE`）。"""
    return client.get(HEALTH_PATH).status_code


def _build_model(client: Any) -> list[tuple[str, str]]:
    """建最小模型（`Assign` 包装 + 自建编号）。"""
    created: list[tuple[str, str]] = []
    for endpoint, item_id, body in MINIMAL_MODEL:
        response = client.post(f"/DB/{endpoint}", json={"Assign": {item_id: body}})
        if response.status_code not in (200, 201):
            raise SystemExit(
                f"❌ 建最小模型失败：DB.{endpoint} #{item_id} → {response.status_code} "
                f"{response.text[:200]}"
            )
        created.append((endpoint, item_id))
    return created


def _run_analysis(client: Any) -> int:
    """`POST /DOC/ANAL`（空体 = 执行分析）。"""
    return client.post(DOC_ANAL_URI, json={DOC_ANAL_WRAPPER: {}}).status_code


def _cleanup(client: Any, created: list[tuple[str, str]]) -> list[str]:
    """逆序清理（**只**碰自建编号；`DELETE` 必带路径 key）。"""
    failures: list[str] = []
    for endpoint, item_id in reversed(created):
        try:
            response = client.delete(f"/DB/{endpoint}/{item_id}")
            if response.status_code not in (200, 204):
                failures.append(f"DB.{endpoint}#{item_id} → {response.status_code}")
        except Exception as error:  # noqa: BLE001 - 清理失败必须如实记录
            failures.append(f"DB.{endpoint}#{item_id} → {type(error).__name__}")
    return failures


def _envelope_key(payload: dict[str, Any]) -> str | None:
    """有数据的取报表响应 → **实测信封键**（形状不符 ⇒ `None`）。

    判据（**只**看形状，**不**看键名）：恰好 1 个顶层键 ∧ 其值是**对象** ∧
    同时含 `HEAD` 与 `DATA` 两个**数组** ⇒ 该键就是本端点的实测信封键。
    """
    if len(payload) != 1:
        return None
    key, value = next(iter(payload.items()))
    if not isinstance(value, dict):
        return None
    if not isinstance(value.get(ENVELOPE_HEAD), list):
        return None
    if not isinstance(value.get(ENVELOPE_DATA), list):
        return None
    return str(key)


def _is_empty_block(payload: dict[str, Any]) -> bool:
    """`200` 的**空块**形态（与 L4 的 `EMPTY_BLOCK_KEY` 同口径）：

    `{}`（该表在最小模型上无数据）或 `{"message": ""}`（实例的**空结果**提示，P134 实测形态）。
    非空 `message`（例如实例报错却给 `200`）**不**算空块 —— 如实落 `FAILED`。
    """
    if not payload:
        return True
    return list(payload) == [EMPTY_BLOCK_KEY] and payload.get(EMPTY_BLOCK_KEY) == ""

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
    """该行是否**已取得结论**（实例崩溃 / 传输失败的行会在续跑时**重测**）。

    ⚠️ 「实例崩溃后重启、项目被关闭」的原生响应（`INSTANCE_DOWN_MARKER`）**不**算端点被拒 ——
    早期版本的证据行可能把它记成 `FAILED`，故这里按 `detail` 再判一次（**不**冒充结论）。
    """
    if row.get("criterion_version") != CRITERION_VERSION:
        return False
    if row.get("instance_down"):
        return False
    if INSTANCE_DOWN_MARKER in str(row.get("detail") or ""):
        return False
    return str(row.get("verdict")) in (PASSED, PARTIAL, FAILED)




def _read_sentinels_safe(client: Any) -> dict[str, list[str]] | None:
    """模型哨兵（只读）；实例不可达 ⇒ `None`（**不**上抛 —— 崩溃后仍要落证据）。"""
    try:
        return _read_sentinels(client)
    except Exception:  # noqa: BLE001 - 实例崩溃是**实测结果**，不是本工具的缺陷
        return None


def _send_query(client: Any, selection: Selection) -> dict[str, Any]:
    """发**一次**取报表请求 → 证据行（任何失败都被归类而**不**上抛）。"""
    try:
        response = client.post(selection.uri, json=selection.body)
    except Exception as error:  # noqa: BLE001 - 传输失败 / 实例崩溃如实归类
        return _row(selection, "", [], SKIPPED, type(error).__name__, instance_down=True)
    top: list[str] = []
    size = 0
    verdict = FAILED
    detail = ""
    down = False
    envelope = ""
    if response.status_code == 200:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            top = [str(name) for name in payload]
            size = len(response.content)
            measured = _envelope_key(payload)
            if measured is not None:
                verdict = PASSED
                envelope = measured
            elif _is_empty_block(payload):
                verdict = PARTIAL
            else:
                detail = "unexpected_envelope_shape"
        else:
            detail = "payload_not_an_object"
    else:
        detail = _error_message(response)
        if INSTANCE_DOWN_MARKER in detail:
            # 实例崩溃后重启会**关闭项目** ⇒ 这一条**没有**取得结论，续跑时重测。
            verdict = SKIPPED
            down = True
    return _row(
        selection,
        response.status_code,
        top,
        verdict,
        detail,
        size,
        instance_down=down,
        envelope_key=envelope,
    )


def probe(
    repo: Path,
    only: tuple[str, ...],
    limit: int,
    chunk_size: int,
    fresh: bool,
) -> int:
    """有界取报表实测 → 证据文件（**零残留**；崩溃时如实记录并支持**续跑**）。

    ⚠️ 本 build 上**确有**取报表端点让 NX 实例**崩溃**（`POST.TABLE.FIBR_MAXCONTRACT`，P149-D 实测
    **两次**：一次在批量里、一次**单独**复现 ⇒ 见 `NEVER_RETRY` / **R115**）。崩溃后实例重启会
    **关闭项目**，故「实例不可达 / `The project is not opened`」的行标成 `instance_down` 而**不**
    冒充 `FAILED`；续跑（缺省行为）**只**重测这些行，已取得结论的行**逐字节保留**。
    """
    tool = check_tool(repo)
    examples = tool.manual_examples(repo)
    entries = manifest_entries(repo)
    keys = targets(repo, only)
    if limit:
        keys = keys[:limit]

    selections: dict[str, Selection] = {}
    gaps: dict[str, str] = {}
    for key in keys:
        if key in NEVER_RETRY:
            gaps[key] = GAP_CRASHES_INSTANCE
            continue
        picked = select_example(tool, examples, entries[key])
        if isinstance(picked, str):
            gaps[key] = picked
        else:
            selections[key] = picked

    print(f"取报表判据目标 = {len(keys)}（可探 {len(selections)} + 留缺 {len(gaps)}）")
    for reason in (
        GAP_CRASHES_INSTANCE,
        GAP_NO_MANUAL_ENTRY,
        GAP_NO_EXAMPLE_FOR_TABLE_TYPE,
        GAP_NO_EXAMPLE_BY_TITLE,
    ):
        members = sorted(key for key, value in gaps.items() if value == reason)
        if members:
            print(f"  留缺 [{reason}] = {len(members)} {members}")

    previous = {} if fresh else _previous_rows(repo)
    endpoints: dict[str, dict[str, Any]] = {
        key: row for key, row in previous.items() if key in selections and _conclusive(row)
    }
    if endpoints:
        print(f"续跑：沿用已有结论 {len(endpoints)} 条")
    pending = [key for key in sorted(selections) if key not in endpoints]

    client = _client()
    residue: dict[str, Any] = {}
    created: list[tuple[str, str]] = []
    aborted = ""
    try:
        residue["before"] = _read_sentinels_safe(client)
        if residue["before"] is None:
            aborted = "实例不可达（跑前哨兵读不到）—— 等实例恢复后重跑 --probe（已有结论会保留）"
            print(f"  ⚠️ {aborted}")
        elif any(residue["before"].values()):
            raise SystemExit(f"❌ 专用项目非空（跑前哨兵）：{residue['before']}")
        else:
            created = _build_model(client)
            analysis_status = _run_analysis(client)
            print(f"最小模型 {len(created)} 个对象已建；DOC.ANAL → {analysis_status}")
            for start in range(0, len(pending), chunk_size):
                chunk = pending[start : start + chunk_size]
                for key in chunk:
                    endpoints[key] = _send_query(client, selections[key])
                health = _health(client)
                print(f"  块 {start // chunk_size + 1} 完成（{len(chunk)} 条）；健康检查 → {health}")
                if health != 200:
                    aborted = f"健康检查 {HEALTH_PATH} → {health}（**立即中止**，P149-B2 的教训）"
                    print(f"  ⚠️ {aborted}")
                    break
            residue["after_model"] = _read_sentinels_safe(client)
    finally:
        residue["cleanup_failures"] = _cleanup(client, created) if created else []
        residue["after_cleanup"] = _read_sentinels_safe(client)
        client.close()

    expected: dict[str, list[str]] = {code: [] for code in SENTINELS}
    for endpoint, item_id in created:
        expected.setdefault(endpoint, []).append(item_id)
    for code in expected:
        expected[code] = sorted(expected[code])
    residue["expected_model"] = expected
    residue["model_untouched"] = residue.get("after_model") is not None and (
        residue.get("after_model") == expected
    )
    after_cleanup = residue.get("after_cleanup")
    residue["clean"] = bool(
        after_cleanup is not None
        and not any(after_cleanup.values())
        and not residue["cleanup_failures"]
    )

    counts: dict[str, int] = {}
    for row in endpoints.values():
        verdict = str(row.get("verdict"))
        counts[verdict] = counts.get(verdict, 0) + 1

    document = {
        "note": [
            "P149-D / R106：`POST.*`「结果表 / 文本查询」端点的**取报表判据**实测证据。",
            "判据：最小模型（只碰自建编号）+ `POST /DOC/ANAL` ⇒ 逐端点发**该端点自己那张表**的"
            "手册示例（**唯一**改动 = 剥掉 `Argument.EXPORT_PATH`）⇒ `HTTP 200` ∧ **实测信封形状**"
            f"（恰好 1 个顶层键、其值是对象、含 `{ENVELOPE_HEAD}` 与 `{ENVELOPE_DATA}` 两个数组）"
            f"⇒ `PASSED`（实测键逐条记在 `envelope_key`）；`200` ∧ 空块（`{{}}` 或只有空的 "
            f"`{EMPTY_BLOCK_KEY}`）⇒ `PARTIAL`；其余 ⇒ `FAILED`。",
            "零残留：跑前 / 跑后模型哨兵逐条相同（取报表**不**写模型数据），清理后哨兵全空。",
            "生成器 = `registry/tools/probe_result_tables.py --probe`；落盘 = `--write`"
            "（`availability` **只升不降** + 追加 `response` 块），随后跑 `sync_manifest.py --write`。",
            "凭据**绝不**写入本文件；请求体 / 响应体原文**不**落盘（只记 `sha256` / 顶层键 / 字节数）。",
        ],
        "instance": {
            "alias": INSTANCE_ALIAS,
            "product": INSTANCE_PRODUCT,
            "base_url": os.environ.get("MIDAS_BASE_URL", "").rstrip("/"),
            "probed_at": PROBED_AT,
            "scope": "namespace == POST ∧ GEN_NX ∧ enabled ∧ 有写方法 ∧ 无 GET ∧ 无 read_root",
        },
        "criterion": {
            "prerequisite": {
                "minimal_model": [f"DB.{endpoint}#{item_id}" for endpoint, item_id, _ in MINIMAL_MODEL],
                "analysis": f"POST {DOC_ANAL_URI}（{DOC_ANAL_WRAPPER} 空体）",
                "sentinels": list(SENTINELS),
            },
            "body_source": "上游手册该 uri 下、该端点**自己那张表**的示例；唯一改动 = 剥掉 Argument.EXPORT_PATH",
            "envelope_shape": {
                "top_level_keys": 1,
                "value_has_lists": [ENVELOPE_HEAD, ENVELOPE_DATA],
            },
            "verdicts": {
                PASSED: (
                    f"HTTP 200 ∧ 恰好 1 个顶层键 ∧ 其值是对象 ∧ 含 `{ENVELOPE_HEAD}` 与 "
                    f"`{ENVELOPE_DATA}` 两个数组（实测键逐条记录）"
                ),
                PARTIAL: (
                    f"HTTP 200 ∧ 空块（{{}} 或 {{'{EMPTY_BLOCK_KEY}': ''}} —— "
                    "该表在最小模型上无数据）"
                ),
                FAILED: "非 200 或顶层键不符",
                SKIPPED: "传输失败 / 超时 / 实例不可达（`instance_down`，续跑时重测）",
            },
            "zero_residue": "跑前 / 跑后哨兵逐条相同；清理后全空",
        },
        "counts": counts,
        "aborted": aborted,
        "residue": residue,
        "gaps": dict(sorted(gaps.items())),
        "never_retry": dict(sorted(NEVER_RETRY.items())),
        "endpoints": dict(sorted(endpoints.items())),
    }
    path = repo / "registry" / EVIDENCE_RELATIVE
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "汇总 =", counts,
        " 零残留 =", residue["clean"],
        " 模型未被改动 =", residue["model_untouched"],
        " 已完成 =", len(endpoints), "/", len(selections),
    )
    print(f"已写入 registry/{EVIDENCE_RELATIVE}")
    return 1 if aborted else 0


def _row(
    selection: Selection,
    status_code: Any,
    top: list[str],
    verdict: str,
    detail: str,
    payload_bytes: int = 0,
    instance_down: bool = False,
    envelope_key: str = "",
) -> dict[str, Any]:
    """证据里的一行（**不**含请求体 / 响应体原文）。"""
    return {
        "uri": "/" + selection.uri.lstrip("/"),
        "wrapper": selection.wrapper,
        "example_id": selection.example_id,
        "body_sha256": selection.body_sha256,
        "adjustments": list(selection.adjustments),
        "status_code": status_code,
        "top_keys": top,
        "payload_bytes": payload_bytes,
        "envelope_key": envelope_key,
        "criterion_version": CRITERION_VERSION,
        "verdict": verdict,
        "detail": detail,
        "instance_down": instance_down,
    }


def _error_message(response: Any) -> str:
    """原生错误形态（只取 `error.message`，**不**落整段响应）。"""
    try:
        payload = response.json()
    except ValueError:
        return "non_json_error"
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or "")[:200]
    return "unexpected_error_shape"


# ===== 落盘 / 断言 =====


def load_evidence(repo: Path) -> dict[str, Any]:
    """读证据文件（缺 → 报错退出）。"""
    path = repo / "registry" / EVIDENCE_RELATIVE
    if not path.is_file():
        raise SystemExit(f"❌ 缺证据文件 registry/{EVIDENCE_RELATIVE}（先跑 --probe）")
    return json.loads(path.read_text(encoding="utf-8"))


def endpoint_files(repo: Path) -> dict[str, Path]:
    """`key → YAML 路径`（按 `manifest.json` 的 `definition` 字段）。"""
    document = json.loads((repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    return {
        str(item["key"]): repo / "registry" / str(item["definition"])
        for item in document["endpoints"]
    }


def response_block(envelope_key: str) -> dict[str, Any]:
    """取报表端点的 `response` 块（**唯一**构造点；只断言**实测到**的信封键）。

    Args:
        envelope_key: 该端点**实测**的信封键（逐端点不同；**不**是全局常量）。
    """
    return {
        "direction": "response",
        "source": RESPONSE_SOURCE,
        "schema": {
            "$schema": DIALECT,
            "type": "object",
            "required": [envelope_key],
            "properties": {envelope_key: {"type": "object"}},
        },
    }


def upgrade_lines(text: str, alias: str) -> tuple[str, bool]:
    """YAML 文本 → 收口后的文本（`availability: untested → verified` + `verified_on` 合并）。

    Returns:
        `(新文本, 是否改动)`；`unverified`（实测全部失败）**不**动 —— **只升不降**。
    """
    import yaml  # noqa: PLC0415

    lines = text.splitlines(keepends=True)
    availability_index = None
    verified_index = None
    for index, line in enumerate(lines):
        if line.startswith("availability:"):
            availability_index = index
        elif line.startswith("verified_on:"):
            verified_index = index
    if availability_index is None:
        return text, False
    if lines[availability_index].strip() != "availability: untested":
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


def write_back(repo: Path) -> int:
    """据证据落盘（`availability` 只升不降 + 追加 `response` 块）。"""
    evidence = load_evidence(repo)
    files = endpoint_files(repo)
    entries = manifest_entries(repo)
    upgraded: list[str] = []
    blocked: list[str] = []
    for key, row in sorted(evidence["endpoints"].items()):
        if str(row.get("verdict")) not in UPGRADABLE:
            continue
        path = files[key]
        text, modified = upgrade_lines(path.read_text(encoding="utf-8"), INSTANCE_ALIAS)
        if modified:
            path.write_text(text, encoding="utf-8")
            upgraded.append(key)
        if str(row.get("verdict")) != PASSED:
            continue
        relative = str(entries[key].get("schema") or "")
        schema_path = repo / "registry" / relative
        if not relative or not schema_path.is_file():
            continue
        document = json.loads(schema_path.read_text(encoding="utf-8"))
        envelope_key = str(row.get("envelope_key") or "")
        if not envelope_key:
            continue
        block = response_block(envelope_key)
        if document.get("response") == block:
            continue
        document["response"] = block
        schema_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        blocked.append(key)
    print(f"availability 收口 = {len(upgraded)}；追加 response 块 = {len(blocked)}")
    print("⚠️ 请接着跑：python registry/tools/sync_manifest.py --write")
    return 0


def check(repo: Path) -> int:
    """断言：数据侧 == 取报表证据（**不**发任何请求）。"""
    evidence = load_evidence(repo)
    files = endpoint_files(repo)
    entries = manifest_entries(repo)
    errors: list[str] = []
    for key, row in sorted(evidence["endpoints"].items()):
        verdict = str(row.get("verdict"))
        availability, verified_on = read_availability(files[key])
        if verdict in UPGRADABLE:
            if availability != VERIFIED:
                errors.append(f"{key}: availability = {availability!r}（证据 verdict = {verdict}）")
            elif INSTANCE_ALIAS not in verified_on:
                errors.append(f"{key}: verified_on = {verified_on}（缺 {INSTANCE_ALIAS!r}）")
        else:
            if availability == VERIFIED:
                errors.append(f"{key}: availability = verified（证据 verdict = {verdict}，不得收口）")
        relative = str(entries[key].get("schema") or "")
        schema_path = repo / "registry" / relative
        if not relative or not schema_path.is_file():
            continue
        block = json.loads(schema_path.read_text(encoding="utf-8")).get("response")
        envelope_key = str(row.get("envelope_key") or "")
        if verdict == PASSED and (not envelope_key or block != response_block(envelope_key)):
            errors.append(f"{key}: response 块 != 取报表实测信封（envelope_key = {envelope_key!r}）")
        if verdict != PASSED and block is not None and block.get("source") == RESPONSE_SOURCE:
            errors.append(f"{key}: 非 PASSED 却有 l4_measured_envelope response 块")
    for key in sorted(evidence.get("gaps") or {}):
        availability, _ = read_availability(files[key])
        if availability == VERIFIED:
            errors.append(f"{key}: 留缺端点不得 availability = verified")
    if errors:
        print("❌ 与取报表证据不一致：")
        for line in errors:
            print("  ", line)
        return 1
    total = len(evidence["endpoints"])
    upgradable = sum(1 for row in evidence["endpoints"].values() if row.get("verdict") in UPGRADABLE)
    print(
        f"✅ 与取报表证据一致（实测 {total} 条：可收口 {upgradable} · "
        f"留缺 {len(evidence.get('gaps') or {})}）"
    )
    return 0


def read_availability(path: Path) -> tuple[str, list[str]]:
    """YAML 里的 `(availability, verified_on)`。"""
    import yaml  # noqa: PLC0415

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    verified_on = document.get("verified_on") or []
    return str(document.get("availability") or ""), [str(item) for item in verified_on]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=REPO_DEFAULT)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--only", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="丢弃既有证据重测（缺省 = 续跑：已取得结论的行逐字节保留）",
    )
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    only = tuple(part.strip() for part in args.only.split(",") if part.strip())

    status = 0
    if args.probe:
        status = max(status, probe(repo, only, args.limit, args.chunk_size, args.fresh))
    if args.write:
        status = max(status, write_back(repo))
    if args.check:
        status = max(status, check(repo))
    if not (args.probe or args.write or args.check):
        print(__doc__)
    return status


if __name__ == "__main__":
    sys.exit(main())
