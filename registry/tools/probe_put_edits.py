#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R118：写路径「编辑（PUT）」的**判据**（P150）。

为什么需要这个工具
------------------
L5 三步链只覆盖「**创建** → 读回 → 按路径 key **删除**」（`docs/07` §16 R4 / R14），
**PUT（编辑）没有判据**。本工具把「编辑」这一步落成**可复算**的判据 + 证据：

    只读哨兵（全部目标端点必须**空**）→
    自建一条记录（**该端点的写入方法** = `POST`，没有 `POST` 时用 `PUT`；**只**用自建编号）→ 读回 →
    **PUT 一个改动过的值**（逐条记录 `{path, from, to, why}`）→ 读回确认**改动生效** →
    按路径 key **删除**（DELETE `<uri>/<id>`）→ 读回确认消失 →
    **无副作用观察**：对**已删除**的编号再发一次同一 PUT，看记录是否**重新出现**
    （⇒ 「PUT 是否要求记录已存在」）→ 把该观察留下的编号**删净** → 只读哨兵（必须**空**）。

判据（**先写清楚再动手**）
--------------------------
| 取值 | 判据 | 说明 |
| --- | --- | --- |
| `PASSED` | `POST 200` ∧ 读回在 ∧ `PUT 200` ∧ 读回**改动生效** ∧ `DELETE 200` ∧ 读回消失 | 「创建 → 读回 → 编辑 → 读回确认 → 删除 → 读回消失」**六步全成立** |
| `FAILED` | 上述任一步不成立（原生拒绝 / 读不回 / 改动未生效 / 删不掉） | 逐条记 `detail` / 状态码 / 尝试过的 PUT 形状；**不**放宽 |
| `LEFT_OUT` | 请求体里**没有**可机械改动的标量（`boolean` / 无 `enum` 的 `number` / `integer`） | 如实留缺（`no_editable_scalar`）；仍走「创建 → 读回 → 删除」保证**零残留**（删除**以再读确认为准**，未确认 ⇒ `+delete_unconfirmed`） |
| `SKIPPED` | 传输失败 / 实例不可达（`The project is not opened`） | **不**计入结论，续跑时重测 |

**改动值的选择是机械的**（`--check` 可离线复算）：按 body 的**声明顺序**深度优先，取**第一个**
`boolean`（翻面）或**第一个**无 `enum` / `const` 的 `number` / `integer`（`+1`）；逐条记进证据。

⚠️ **本桶与 R107 的取设置表判据（无 `DELETE` 的单例表）分开**，也**不**并入 L5 三步链的
覆盖率分子（`live.write_path_coverage()` **不变**）——「读得回 / 写得进 / 编辑生效 / 删得掉」
是**四个**判定，本工具只补「编辑生效」这一个。

残留与别名（P150 实测）
----------------------
* **`DELETE` 会「假成功」**：本 build 上 `DELETE` 可以**返回 `200` 并回显被删记录**却不真正删除
  ⇒ 判据**必须**以「再读一次、该编号确实不在」为准（只信状态码会把残留当成零残留）。
* **`DESIGN.*` 别名路由的 `DELETE` 不生效**：`/DESIGN/RC/DRC`、`/DESIGN/RC/KDS-41-20-2022/DCTL`、
  `/DESIGN/STEEL/DSTL` 与 `/DB/DCON`、`/DB/DCTL`、`/DB/DSTL` **同表**，但别名路由的 `DELETE`
  删不掉 ⇒ 残留**只能**经**同表的 `DB.*` 路由**清理（`DELETE /DB/<CODE>/<自建编号>`）。
* **`/DESIGN/SRC/AIK-SRC2K/DSRC`** 无 `DB.*` 别名、实测**删不掉**（路径 key / 无 key / 带 body 三种
  形式都返回 `200` 而记录仍在）⇒ 只能**如实披露**（`--allow-residue DESIGN.SRC.AIK-SRC2K.DSRC`），
  成因需 **MIDAS 侧**排查。
* `--allow-residue` **只**放行**已披露**的残留 key：跑前哨兵其余非空一律**中止**（零写请求）；
  `residue ⊄ allowed_residue` ⇒ 退出码 1。

目标集
------
`有数据侧模板`（⇒ 有真实请求体）∧ GEN NX 上 `methods` 含 `PUT` ∧ `DELETE` ∧ `GET` ∧
有 `read_root` ∧ 已启用 ∧ 非破坏性 ∧ 非「按主体删全表」。**本批只处理「零前置链」的端点**
（`prerequisites` 为空）：前置链的创建 / 回收与 L5 **同一**机制，本批**不**重复实现；
带前置链的端点如实记 `left_out`（原因 `prerequisite_chain_out_of_scope`，
恢复条件 = 沿用 L5 的前置链机制续跑）。

纪律
----
* **只碰自建编号**：编号 = 该端点既有编号的 `max + 1`（空项目 ⇒ `1`）；删除**必带路径 key**。
* **跑前 / 跑后只读哨兵**：对**全部**目标端点做只读 `GET`；**跑前非空 ⇒ 一个写请求都不发**
  （`aborted`）；**跑后非空 ⇒ 如实记 `residue`**（**不**声称零残留）；`residue ⊄ allowed_residue`
  ⇒ 退出码 1（**只**放行已披露且实测删不掉的残留，见「残留与别名」）。
* **分块 + 健康检查**（P149-B2 两次实例崩溃的教训）：每块 ≤ `--chunk-size`（默认 **10**）条，
  块间做**只读**健康检查 `GET /DB/NODE`；非 `200` ⇒ **立即中止**。
* **累积 + 续跑**：既有证据的行**逐字节保留**，`--limit` 限制单次尝试条数（默认 = 一块）；
  `CRITERION_VERSION` 变更 ⇒ 既有行**全部**重测。
* 证据里**绝不**出现凭据；也**不**保存响应体原文（只存判定所需的编号 / 状态码 / 字段改动）。
* 只依赖标准库 + `httpx`（探针必需）；「条目形状判定」复用同目录 `check_write_templates.py`
  （**唯一**判定点）。

用法（仓库根目录执行；`--probe` 需要 `MIDAS_BASE_URL` / `MIDAS_MAPI_KEY`）
------------------------------------------------------------------------
    # 有界侦察（默认一块 ≤ 10 条 + 块间只读健康检查 + 跑前 / 跑后只读哨兵）
    python registry/tools/probe_put_edits.py --probe
    python registry/tools/probe_put_edits.py --probe --limit 3 --only DB.SECT
    python registry/tools/probe_put_edits.py --probe --limit 20 --chunk-size 10

    # 断言证据与数据侧一致（CI 用）；已披露残留见「残留与别名」
    python registry/tools/probe_put_edits.py --check
    python registry/tools/probe_put_edits.py --summary
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import sys
from typing import Any

REPO_DEFAULT = "."
EVIDENCE_RELATIVE = "live/put_edit_probe.json"
MANIFEST_FILENAME = "manifest.json"
TEMPLATES_RELATIVE = "live/write_templates.json"
CHECK_TOOL_FILENAME = "check_write_templates.py"

INSTANCE_ALIAS = "gen-local"
INSTANCE_PRODUCT = "GEN_NX"
PROBED_AT = "2026-10-11"
CRITERION_VERSION = 3

CHUNK_SIZE = 10
"""每块端点上限（**≤ 20** 的纪律；默认 **10** —— 每个端点要发多次写请求）。"""

HEALTH_PATH = "/DB/NODE"
"""块间**只读**健康检查路径；非 `200` ⇒ **立即中止**。"""

INSTANCE_DOWN_MARKER = "The project is not opened"
"""实例崩溃后重启会**关闭项目** —— 该形态归 `SKIPPED`（**不**冒充端点被拒）。"""

PASSED = "PASSED"
FAILED = "FAILED"
LEFT_OUT = "LEFT_OUT"
SKIPPED = "SKIPPED"

SHAPE_ASSIGN_ITEM = "assign_keyed_item"
"""`{"Assign": {"<自建编号>": <条目>}}` —— 与 POST 同一形状（**首选**）。"""

SHAPE_BARE_ITEM = "bare_item"
"""条目**不**包装（`is_flat` 形态）。"""

SHAPE_ARGUMENT_ITEM = "argument_wrapped_item"
"""`{"Argument": <条目>}` —— 换个包装键再试一次。"""

PUT_SHAPES = (SHAPE_ASSIGN_ITEM, SHAPE_BARE_ITEM, SHAPE_ARGUMENT_ITEM)

REASON_NO_EDITABLE_SCALAR = "no_editable_scalar"
REASON_PREREQUISITE_CHAIN = "prerequisite_chain_out_of_scope"
REASON_NOT_AVAILABLE = "not_available_on_instance"

LEGAL_EDIT_TYPES = frozenset({"boolean", "number", "integer"})
"""可机械改动的标量类型（`boolean` 翻面；`number` / `integer` `+1`）。"""

SCALAR_TYPES = frozenset({"boolean", "number", "integer", "string"})


# ===== 同目录工具（条目形状的**唯一**判定点）=====


def _load_check_tool() -> Any:
    path = pathlib.Path(__file__).resolve().parent / CHECK_TOOL_FILENAME
    spec = importlib.util.spec_from_file_location("structai_check_write_templates", path)
    if spec is None or spec.loader is None:  # pragma: no cover - 防御性
        raise SystemExit(f"❌ 无法装载 {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ===== 目标集 =====


def _methods(value: Any) -> set[str]:
    return {part.strip().upper() for part in str(value or "").split(",") if part.strip()}


def targets(repo: pathlib.Path) -> list[dict[str, Any]]:
    """全部「有数据侧模板 ∧ GEN NX 有 PUT ∧ 有 DELETE / GET / `read_root` ∧ 已启用」的端点。

    Returns:
        `[{key, uri, read_root, wrapper, products, prerequisites, template_body}, ...]`（按 key 排序）。
    """
    manifest = json.loads((repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    templates = json.loads(
        (repo / "registry" / TEMPLATES_RELATIVE).read_text(encoding="utf-8")
    )["templates"]
    rows: list[dict[str, Any]] = []
    for item in manifest["endpoints"]:
        key = str(item["key"])
        template = templates.get(key)
        if template is None:
            continue
        if not bool(item.get("enabled", True)):
            continue
        if bool((item.get("risk") or {}).get("destructive")):
            continue
        if bool(item.get("delete_all_via_body")):
            continue
        methods = _methods(item.get("methods"))
        if not {"PUT", "DELETE", "GET"} <= methods:
            continue
        if INSTANCE_PRODUCT not in [str(name) for name in (item.get("products") or [])]:
            continue
        read_root = str((item.get("wrapper") or {}).get("read_root") or "")
        if not read_root:
            continue
        prerequisites = template.get("prerequisites") or []
        rows.append(
            {
                "key": key,
                "uri": "/" + str(item.get("uri") or "").lstrip("/"),
                "read_root": read_root,
                "wrapper": str(template.get("wrapper") or ""),
                "write_method": "POST" if "POST" in methods else "PUT",
                "products": [str(name) for name in (item.get("products") or [])],
                "prerequisites": len(prerequisites),
                "template_body": template.get("body"),
            }
        )
    return sorted(rows, key=lambda row: str(row["key"]))


def zero_prerequisite_targets(repo: pathlib.Path) -> list[dict[str, Any]]:
    """本批可探的目标 = 零前置链的那些（见模块文档）。"""
    return [row for row in targets(repo) if int(row["prerequisites"]) == 0]


def left_out_prerequisite_chains(repo: pathlib.Path) -> list[str]:
    """带前置链、本批**不**处理的端点（如实留缺）。"""
    return [str(row["key"]) for row in targets(repo) if int(row["prerequisites"]) > 0]


# ===== 机械改动值 =====


def _leaves(body: Any, node: Any, path: str = "") -> list[tuple[str, Any, Any]]:
    """body 的**标量叶子**（深度优先、按声明顺序）：`[(路径, 取值, Schema 节点)]`。

    `node` 是该层级的 **Schema 节点**（含 `properties`）；数组**不**展开（不是标量叶子）。
    """
    found: list[tuple[str, Any, Any]] = []
    if not isinstance(body, dict):
        return found
    properties = node.get("properties") if isinstance(node, dict) else None
    if not isinstance(properties, dict):
        properties = {}
    for name, value in body.items():
        where = f"{path}.{name}" if path else name
        child = properties.get(name)
        if isinstance(value, dict):
            found.extend(_leaves(value, child, where))
        elif isinstance(value, bool) or isinstance(value, (int, float)):
            found.append((where, value, child))
    return found

def editable_change(body: Any, item_schema: Any) -> dict[str, Any] | None:
    """机械选定一处**可改动**的标量改动（**不**猜字段；取不到 ⇒ `None`）。

    顺序（**唯一**判定点，`--check` 与探针同源）：先找 `boolean`（翻面），再找
    无 `enum` / `const` 的 `number` / `integer`（`+1`）。`string` **不**动（可能是枚举 / 编号）。
    """
    leaves = _leaves(body, item_schema)
    for want in ("boolean", "number", "integer"):
        for dotted, value, node in leaves:
            if not isinstance(node, dict) or node.get("type") != want:
                continue
            if "enum" in node or "const" in node:
                continue
            if want == "boolean" and isinstance(value, bool):
                return {
                    "path": dotted,
                    "from": value,
                    "to": not value,
                    "schema_type": want,
                    "why": "boolean 翻面（Schema 声明 type=boolean ∧ 无 enum/const）",
                }
            if want in {"number", "integer"} and isinstance(value, (int, float)) and not isinstance(
                value, bool
            ):
                return {
                    "path": dotted,
                    "from": value,
                    "to": value + 1,
                    "schema_type": want,
                    "why": f"{want} +1（Schema 声明 type={want} ∧ 无 enum/const）",
                }
    return None


def apply_change(body: Any, dotted: str, value: Any) -> Any:
    """把改动写进**副本**（路径不存在 ⇒ 抛错，**不**静默）。"""
    document = json.loads(json.dumps(body))
    parts = dotted.split(".")
    node = document
    for name in parts[:-1]:
        node = node[name]
    node[parts[-1]] = value
    return document


def read_at(body: Any, dotted: str) -> Any:
    """按路径读值（取不到 ⇒ `KeyError`，由调用方归类）。"""
    node = body
    for name in dotted.split("."):
        if isinstance(node, dict):
            node = node[name]
        elif isinstance(node, list):
            node = node[int(name)]
        else:
            raise KeyError(dotted)
    return node


# ===== 只读哨兵 / 读回 =====


def _ids_of(payload: Any, read_root: str) -> tuple[str, ...] | None:
    """`read_root` 块下的编号集合（块不存在 / 不是对象 ⇒ `None`）。"""
    if not isinstance(payload, dict):
        return None
    block = payload.get(read_root)
    if not isinstance(block, dict):
        return None
    return tuple(str(name) for name in block)


def _get(client: Any, uri: str, read_root: str) -> dict[str, Any]:
    """只读 `GET` → `{status_code, ids, detail}`（**只**读，零副作用）。"""
    try:
        response = client.get(uri)
    except Exception as error:  # noqa: BLE001
        return {"status_code": "", "ids": None, "detail": type(error).__name__}
    if response.status_code != 200:
        detail = ""
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            detail = str(payload["error"].get("message") or "")[:200]
        return {"status_code": response.status_code, "ids": None, "detail": detail}
    try:
        payload = response.json()
    except ValueError:
        payload = None
    ids = _ids_of(payload, read_root)
    return {
        "status_code": 200,
        "ids": ids,
        "detail": "" if ids is not None else "read_root_missing",
        "payload": payload,
    }


def sentinel(client: Any, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """**只读**哨兵：逐端点读既有编号（`{key: {status_code, ids, detail}}`）。"""
    snapshot: dict[str, dict[str, Any]] = {}
    for row in rows:
        result = _get(client, str(row["uri"]), str(row["read_root"]))
        snapshot[str(row["key"])] = {
            "status_code": result["status_code"],
            "ids": list(result["ids"] or ()),
            "readable": result["ids"] is not None,
            "detail": str(result["detail"]),
        }
    return snapshot


def residue_of(snapshot: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    """哨兵里**非空**的端点（⇒ 残留）。"""
    return {
        key: list(row["ids"])
        for key, row in snapshot.items()
        if row["readable"] and row["ids"]
    }


# ===== 写请求（**只**用自建编号）=====


def _wrap(shape: str, item: Any, item_id: str) -> Any:
    """按形状包装请求体（`Assign` = 编号键控条目；`Argument` = 单条目；裸 = 平铺）。"""
    if shape == SHAPE_BARE_ITEM:
        return item
    if shape == SHAPE_ARGUMENT_ITEM:
        return {"Argument": item}
    return {"Assign": {str(item_id): item}}


def _send(client: Any, method: str, uri: str, payload: Any = None) -> dict[str, Any]:
    """发一次写请求 → `{status_code, detail}`（**不**上抛）。"""
    try:
        if method == "DELETE":
            response = client.delete(uri)
        elif method == "PUT":
            response = client.put(uri, json=payload)
        else:
            response = client.post(uri, json=payload)
    except Exception as error:  # noqa: BLE001 - 传输失败如实归类
        return {"status_code": "", "detail": type(error).__name__, "transport_error": True}
    detail = ""
    if response.status_code != 200:
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and isinstance(body.get("error"), dict):
            detail = str(body["error"].get("message") or "")[:200]
    return {
        "status_code": response.status_code,
        "detail": detail,
        "transport_error": INSTANCE_DOWN_MARKER in detail,
    }


def _gone(client: Any, uri: str, read_root: str, own_id: str) -> bool:
    """**保守**判定「该编号已不在」：读不动（`ids is None`）⇒ `False`（**不**假设已删）。"""
    state = _get(client, uri, read_root)
    return state["ids"] is not None and own_id not in state["ids"]


def probe_key(client: Any, row: dict[str, Any], repo: pathlib.Path) -> dict[str, Any]:
    """单端点的「创建 → 读回 → 编辑 → 读回确认 → 删除 → 读回消失」+ 无副作用观察。

    ⚠️ 删除**必须**以「再读一次、该编号确实不在」为判据 —— 实测本 build 上
    `DELETE` 会**返回 `200` 并回显被删记录**却**不真正删除**（`DESIGN.SRC.AIK-SRC2K.DSRC`）
    ⇒ 只信状态码就会把残留当成零残留（P150 实测踩过）。
    """
    check_tool = _load_check_tool()
    key = str(row["key"])
    uri = str(row["uri"])
    read_root = str(row["read_root"])
    create_method = str(row["write_method"])
    base: dict[str, Any] = {
        "uri": uri,
        "read_root": read_root,
        "wrapper": str(row["wrapper"]),
        "write_method": create_method,
        "products": list(row["products"]),
        "prerequisites": int(row["prerequisites"]),
        "created_id": "",
        "read_back": False,
        "edit": None,
        "edit_confirmed": False,
        "deleted": False,
        "put_shape": "",
        "put_status_code": "",
        "put_attempts": [],
        "put_absent_status": "",
        "put_absent_recreated": None,
        "requires_existing_record": None,
        "detail": "",
        "payload_source": "data_side_template",
    }
    before = _get(client, uri, read_root)
    if before["ids"] is None:
        verdict = SKIPPED if before["status_code"] == "" else FAILED
        return {
            **base,
            "status_code": before["status_code"],
            "verdict": verdict,
            "detail": f"read_before_failed:{before['detail'] or before['status_code']}",
        }
    existing = [int(name) for name in before["ids"] if str(name).isdigit()]
    own_id = str(max(existing, default=0) + 1)
    body = row["template_body"]
    item_schema = check_tool.request_schema(repo, _schema_relative(repo, key), key)
    edit = editable_change(body, item_schema)
    base["created_id"] = own_id
    if edit is None:
        # 无可机械改动的标量 ⇒ 如实留缺，但仍走「创建 → 读回 → 删除」保证**零残留**
        created = _send(
            client, create_method, uri, _wrap(_create_shape(row), body, own_id)
        )
        base["status_code"] = created["status_code"]
        base["read_back"] = own_id in (_get(client, uri, read_root)["ids"] or ())
        removed = _send(client, "DELETE", f"{uri}/{own_id}")
        base["deleted"] = removed["status_code"] == 200 and _gone(
            client, uri, read_root, own_id
        )
        base["detail"] = (
            REASON_NO_EDITABLE_SCALAR
            if base["deleted"]
            else f"{REASON_NO_EDITABLE_SCALAR}+delete_unconfirmed"
        )
        return {**base, "verdict": LEFT_OUT}
    base["edit"] = edit
    changed = apply_change(body, str(edit["path"]), edit["to"])
    created = _send(client, create_method, uri, _wrap(_create_shape(row), body, own_id))
    base["status_code"] = created["status_code"]
    if created["status_code"] != 200:
        if created.get("transport_error"):
            return {
                **base,
                "verdict": SKIPPED,
                "detail": f"create_transport:{created['detail']}",
            }
        _send(client, "DELETE", f"{uri}/{own_id}")
        base["deleted"] = _gone(client, uri, read_root, own_id)
        return {
            **base,
            "verdict": FAILED,
            "detail": f"create_rejected:{created['status_code']}:{created['detail']}",
        }
    base["read_back"] = own_id in (_get(client, uri, read_root)["ids"] or ())
    attempts: list[dict[str, Any]] = []
    for shape in PUT_SHAPES:
        result = _send(client, "PUT", uri, _wrap(shape, changed, own_id))
        attempts.append(
            {
                "shape": shape,
                "status_code": result["status_code"],
                "detail": result["detail"],
            }
        )
        if result["status_code"] == 200:
            base["put_shape"] = shape
            base["put_status_code"] = result["status_code"]
            break
    base["put_attempts"] = attempts
    if not base["put_shape"]:
        _send(client, "DELETE", f"{uri}/{own_id}")
        base["deleted"] = _gone(client, uri, read_root, own_id)
        return {
            **base,
            "verdict": FAILED,
            "detail": f"put_rejected:{attempts[-1]['status_code']}:{attempts[-1]['detail']}",
        }
    after_put = _get(client, uri, read_root)
    block = (after_put.get("payload") or {}).get(read_root)
    observed = block.get(own_id) if isinstance(block, dict) else None
    if isinstance(observed, dict):
        try:
            base["edit_confirmed"] = read_at(observed, str(edit["path"])) == edit["to"]
        except KeyError:
            base["edit_confirmed"] = False
    removed = _send(client, "DELETE", f"{uri}/{own_id}")
    base["deleted"] = removed["status_code"] == 200 and _gone(
        client, uri, read_root, own_id
    )
    # 无副作用观察：记录**已删除**后对同一编号再发一次同一 PUT 的结果
    absent = _send(client, "PUT", uri, _wrap(base["put_shape"], changed, own_id))
    base["put_absent_status"] = absent["status_code"]
    base["put_absent_recreated"] = own_id in (_get(client, uri, read_root)["ids"] or ())
    base["requires_existing_record"] = not base["put_absent_recreated"]
    # 该观察若留下了记录 ⇒ 立刻删净（**只**碰自建编号；跑前哨兵保证该编号不是别人的）
    if base["put_absent_recreated"]:
        _send(client, "DELETE", f"{uri}/{own_id}")
    final_gone = _gone(client, uri, read_root, own_id)
    passed = bool(
        base["read_back"] and base["edit_confirmed"] and base["deleted"] and final_gone
    )
    if passed:
        detail = ""
    elif not base["read_back"]:
        detail = "read_back_missing"
    elif not base["edit_confirmed"]:
        detail = "edit_not_effective"
    else:
        detail = "delete_failed"
    return {**base, "verdict": PASSED if passed else FAILED, "detail": detail}


def _create_shape(row: dict[str, Any]) -> str:
    """创建（写入方法）的包装形状（与 L5 同一判定：`wrapper` = `Assign` ⇒ 编号键控条目）。"""
    return SHAPE_ASSIGN_ITEM if str(row["wrapper"]) == "Assign" else SHAPE_ARGUMENT_ITEM


def _schema_relative(repo: pathlib.Path, key: str) -> str:
    """该端点的请求 Schema 相对路径（缺 ⇒ 空串，`request_schema()` 返回 `None`）。"""
    manifest = json.loads((repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    for item in manifest["endpoints"]:
        if str(item["key"]) == key:
            return str(item.get("schema") or "")
    return ""

def _write_method_of(repo: pathlib.Path, key: str) -> str:
    """该端点在 GEN NX 上的**写入方法**（与 L5 同一判定：`POST` 优先，否则 `PUT`）。"""
    manifest = json.loads((repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    for item in manifest["endpoints"]:
        if str(item["key"]) == key:
            return "POST" if "POST" in _methods(item.get("methods")) else "PUT"
    return ""


# ===== 证据读写 =====


def _existing_document(repo: pathlib.Path) -> dict[str, Any]:
    path = repo / "registry" / EVIDENCE_RELATIVE
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


def _existing_rows(repo: pathlib.Path) -> dict[str, dict[str, Any]]:
    document = _existing_document(repo)
    if int(document.get("criterion_version") or 0) != CRITERION_VERSION:
        return {}
    rows = document.get("endpoints")
    return rows if isinstance(rows, dict) else {}


def probe(
    repo: pathlib.Path,
    only: tuple[str, ...],
    limit: int,
    chunk_size: int,
    allow_residue: tuple[str, ...] = (),
) -> int:
    """有界侦察 → 证据文件（分块 + 块间只读健康检查 + 跑前 / 跑后只读哨兵）。"""
    import httpx  # noqa: PLC0415

    base_url = os.environ.get("MIDAS_BASE_URL", "").rstrip("/")
    key_value = os.environ.get("MIDAS_MAPI_KEY", "")
    if not base_url or not key_value:
        print("❌ --probe 需要 MIDAS_BASE_URL / MIDAS_MAPI_KEY（见 scripts/load-midas-env.ps1）")
        return 1
    all_targets = targets(repo)
    probeable = zero_prerequisite_targets(repo)
    endpoints = _existing_rows(repo)
    pending = [row for row in probeable if not only or str(row["key"]) in only]
    pending = [row for row in pending if str(row["key"]) not in endpoints][:limit]
    print(
        f"PUT 编辑判据：目标 {len(all_targets)} 个（零前置链 {len(probeable)} 个；"
        f"既有证据 {len(endpoints)} 行 ⇒ 本次待测 {len(pending)} 个）"
        f"（实例 {INSTANCE_ALIAS} / {INSTANCE_PRODUCT}）"
    )
    aborted = ""
    sentinel_before: dict[str, dict[str, Any]] = {}
    sentinel_after: dict[str, dict[str, Any]] = {}
    with httpx.Client(
        base_url=base_url, headers={"MAPI-Key": key_value}, timeout=60.0
    ) as client:
        sentinel_before = sentinel(client, all_targets)
        blocked = {
            name: ids
            for name, ids in residue_of(sentinel_before).items()
            if name not in allow_residue
        }
        if blocked:
            aborted = f"跑前哨兵**非空** ⇒ 一个写请求都不发（{sorted(blocked)[:5]}）"
            print(f"⚠️ {aborted}")
        else:
            for start in range(0, len(pending), chunk_size):
                chunk = pending[start : start + chunk_size]
                for row in chunk:
                    endpoints[str(row["key"])] = probe_key(client, row, repo)
                health = client.get(HEALTH_PATH).status_code
                print(f"  块 {start // chunk_size + 1} 完成（{len(chunk)} 条）；健康检查 → {health}")
                if health != 200:
                    aborted = f"健康检查 {HEALTH_PATH} → {health}（**立即中止**，P149-B2 的教训）"
                    print(f"  ⚠️ {aborted}")
                    break
        sentinel_after = sentinel(client, all_targets)
    counts: dict[str, int] = {}
    for row in endpoints.values():
        counts[str(row.get("verdict"))] = counts.get(str(row.get("verdict")), 0) + 1
    document = {
        "note": [
            "判据（**裁决 R118**）：只读哨兵（全空）→ POST 自建编号 → 读回 → **PUT 改动过的值**"
            "（逐条记 `{path, from, to, why}`）→ 读回确认**改动生效** → DELETE 按路径 key → 读回消失"
            "⇒ `PASSED`；任一步不成立 ⇒ `FAILED`；无可机械改动的标量 ⇒ `LEFT_OUT`。",
            "「PUT 是否要求记录已存在」= **无副作用观察**：记录删除后对同一编号再发一次同一 PUT，"
            "看它是否**重新出现** ⇒ `put_absent_recreated` / `requires_existing_record`；"
            "观察若留下记录**立刻**删净（跑前哨兵保证项目为空 ⇒ 该编号只可能是自建的）。",
            "改动值的选择是**机械**的（`boolean` 翻面 / 无 `enum` 的 `number`·`integer` `+1`，"
            "按 body 声明顺序取**第一个**）⇒ `--check` 可离线复算。",
            "生成器 = `registry/tools/probe_put_edits.py --probe`（**分块** ≤ `--chunk-size` + "
            f"块间只读健康检查 `{HEALTH_PATH}` + 跑前 / 跑后只读哨兵；**累积**：既有行逐字节保留）。",
            "⚠️ 本桶与 **R107** 的取设置表判据（无 `DELETE` 的单例表）**分开**，也**不**并入 L5 "
            "三步链的覆盖率分子（`live.write_path_coverage()` **不变**）。",
            "证据里**没有**凭据、也**没有**响应体原文（只存判定所需的编号 / 状态码 / 字段改动）。",
            "⚠️ `allowed_residue`（`--allow-residue`）只用于**已披露且实测删不掉**的残留"
            "（`DELETE` 返回 `200` 却不删；见报告 §残留）：跑前哨兵**只**放行这些 key，"
            "其余非空一律**中止**（零写请求）；`residue ⊄ allowed_residue` ⇒ 退出码 1。",
        ],
        "criterion_version": CRITERION_VERSION,
        "instance": {
            "alias": INSTANCE_ALIAS,
            "product": INSTANCE_PRODUCT,
            "base_url": base_url,
            "probed_at": PROBED_AT,
            "scope": "有数据侧模板 ∧ GEN NX 有 PUT ∧ 有 DELETE / GET / read_root ∧ 已启用 ∧ 零前置链",
        },
        "targets": len(all_targets),
        "probeable": len(probeable),
        "left_out_prerequisite_chain": left_out_prerequisite_chains(repo),
        "counts": counts,
        "aborted": aborted,
        "sentinel_before": sentinel_before,
        "sentinel_after": sentinel_after,
        "residue": residue_of(sentinel_after),
        "allowed_residue": sorted(allow_residue),
        "endpoints": dict(sorted(endpoints.items())),
    }
    (repo / "registry" / EVIDENCE_RELATIVE).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    undisclosed = {
        name for name in document["residue"] if name not in allow_residue
    }
    print(
        "verdict =",
        counts,
        " 中止 =",
        bool(aborted),
        " 残留 =",
        sorted(document["residue"]),
        " 未披露残留 =",
        sorted(undisclosed),
    )
    print(f"已写入 registry/{EVIDENCE_RELATIVE}（{len(endpoints)} 行）")
    return 1 if (aborted or undisclosed) else 0


def load_evidence(repo: pathlib.Path) -> dict[str, dict[str, Any]]:
    document = _existing_document(repo)
    if not document:
        raise SystemExit(f"❌ 缺证据文件 registry/{EVIDENCE_RELATIVE}（先跑 --probe）")
    if int(document.get("criterion_version") or 0) != CRITERION_VERSION:
        raise SystemExit(
            f"❌ 证据的 criterion_version = {document.get('criterion_version')!r}，"
            f"本工具为 {CRITERION_VERSION}（判据已变 ⇒ 先重跑 --probe）"
        )
    return document["endpoints"]


# ===== 校验 =====


def check(repo: pathlib.Path) -> int:
    """断言证据与数据侧**逐条**一致（可离线复算；CI 用）。"""
    check_tool = _load_check_tool()
    document = _existing_document(repo)
    if not document:
        print(f"❌ 缺 registry/{EVIDENCE_RELATIVE}")
        return 1
    endpoints = load_evidence(repo)
    errors: list[str] = []
    counts: dict[str, int] = {}
    for key, row in sorted(endpoints.items()):
        counts[str(row.get("verdict"))] = counts.get(str(row.get("verdict")), 0) + 1
        if int(row.get("prerequisites") or 0) != 0:
            errors.append(f"{key}: 本批**只**处理零前置链的端点")
        edit = row.get("edit")
        if str(row.get("verdict")) == LEFT_OUT:
            if edit is not None:
                errors.append(f"{key}: `LEFT_OUT` 的行不得带 `edit`")
            detail = str(row.get("detail") or "")
            if detail not in (
                REASON_NO_EDITABLE_SCALAR,
                f"{REASON_NO_EDITABLE_SCALAR}+delete_unconfirmed",
            ):
                errors.append(f"{key}: `LEFT_OUT` 的原因必须是 {REASON_NO_EDITABLE_SCALAR!r}")
            continue
        if str(row.get("verdict")) not in {PASSED, FAILED}:
            continue
        if not isinstance(edit, dict):
            errors.append(f"{key}: 缺 `edit`（可探行必须逐条记录改动）")
            continue
        relative = _schema_relative(repo, key)
        item_schema = check_tool.request_schema(repo, relative, key)
        if str(row.get("write_method") or "") not in {"POST", "PUT"}:
            errors.append(f"{key}: `write_method` = {row.get('write_method')!r} 不在允许集合里")
        if str(row.get("write_method")) != _write_method_of(repo, key):
            errors.append(f"{key}: `write_method` 与数据侧不一致")
        body = _template_body(repo, key)
        expected = editable_change(body, item_schema)
        if expected is None:
            errors.append(f"{key}: 盘面上**没有**可机械改动的标量（证据却记了 `edit`）")
            continue
        if {name: edit.get(name) for name in ("path", "from", "to")} != {
            name: expected[name] for name in ("path", "from", "to")
        }:
            errors.append(f"{key}: `edit` 与机械结果不一致（{edit} vs {expected}）")
        if str(row.get("put_shape") or "") and str(row.get("put_shape")) not in PUT_SHAPES:
            errors.append(f"{key}: `put_shape` = {row.get('put_shape')!r} 不在允许集合里")
        if str(row.get("verdict")) == PASSED and not str(row.get("put_shape") or ""):
            errors.append(f"{key}: `PASSED` 的行必须记录成功的 `put_shape`")
        if str(row.get("verdict")) == PASSED and row.get("requires_existing_record") is None:
            errors.append(f"{key}: `PASSED` 的行必须记录「PUT 是否要求记录已存在」的观察")
    if document.get("counts") != counts:
        errors.append(f"证据 counts = {document.get('counts')}，复算 = {counts}")
    if document.get("aborted"):
        errors.append(f"证据记录了一次中止：{document['aborted']}")
    if document.get("residue") and not set(document["residue"]) <= set(
        document.get("allowed_residue") or ()
    ):
        errors.append(f"证据记录了残留：{sorted(document['residue'])}")
    if errors:
        print("❌ 与数据侧不一致：")
        for line in errors:
            print("  ", line)
        return 1
    disclosed = sorted(document.get("residue") or ())
    print(
        f"✅ 与数据侧一致（可探 {len(endpoints)} 行：{counts}；"
        f"已披露残留 = {disclosed or '无'}）"
    )
    return 0


def _template_body(repo: pathlib.Path, key: str) -> Any:
    templates = json.loads(
        (repo / "registry" / TEMPLATES_RELATIVE).read_text(encoding="utf-8")
    )["templates"]
    return (templates.get(key) or {}).get("body")


def summary(repo: pathlib.Path) -> int:
    """只打印汇总（逐条改动见证据文件）。"""
    document = _existing_document(repo)
    if not document:
        print(f"（缺 registry/{EVIDENCE_RELATIVE}）")
        return 0
    print(f"criterion_version = {document.get('criterion_version')}")
    print(f"实例 = {document.get('instance')}")
    print(f"目标 = {document.get('targets')}；零前置链 = {document.get('probeable')}；"
          f"带前置链留缺 = {len(document.get('left_out_prerequisite_chain') or [])}")
    print(f"verdict = {document.get('counts')}")
    print(f"中止 = {document.get('aborted')!r}；残留 = {document.get('residue')}")
    for key, row in sorted(document["endpoints"].items()):
        edit = row.get("edit") or {}
        print(
            f"  {key}: {row.get('verdict')} id={row.get('created_id')} "
            f"shape={row.get('put_shape') or '-'} edit={edit.get('path')} "
            f"{edit.get('from')} -> {edit.get('to')} confirmed={row.get('edit_confirmed')} "
            f"requires_existing={row.get('requires_existing_record')} detail={row.get('detail')!r}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R118：写路径「编辑（PUT）」判据")
    parser.add_argument("--repo", default=REPO_DEFAULT)
    parser.add_argument("--probe", action="store_true", help="有界侦察（分块 + 哨兵；**有写请求**）")
    parser.add_argument("--check", action="store_true", help="断言证据与数据侧一致（CI）")
    parser.add_argument("--summary", action="store_true", help="只打印汇总")
    parser.add_argument("--only", default="", help="只处理这些 key（逗号分隔）")
    parser.add_argument("--limit", type=int, default=CHUNK_SIZE, help="本次尝试的端点上限")
    parser.add_argument(
        "--allow-residue",
        default="",
        help="已披露且实测删不掉的残留 key（逗号分隔；跑前哨兵只放行这些）",
    )
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    args = parser.parse_args(argv)
    repo = pathlib.Path(args.repo).resolve()
    only = tuple(part.strip() for part in args.only.split(",") if part.strip())

    status = 0
    if args.probe:
        allow = tuple(part.strip() for part in args.allow_residue.split(",") if part.strip())
        status = max(status, probe(repo, only, args.limit, args.chunk_size, allow))
    if args.check:
        status = max(status, check(repo))
    if args.summary:
        status = max(status, summary(repo))
    if not (args.probe or args.check or args.summary):
        print(__doc__)
    return status


if __name__ == "__main__":
    sys.exit(main())
