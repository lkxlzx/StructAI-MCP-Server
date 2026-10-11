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
有 `read_root` ∧ 已启用 ∧ 非破坏性 ∧ 非「按主体删全表」= **71** 个端点。
**P150** 只处理「零前置链」的 **56** 个（带前置链的 **15** 个如实留缺
`prerequisite_chain_out_of_scope`）。
**P151 续跑**：判据不变、证据文件不变，把 **15** 个带前置链的端点补齐 —— 前置链沿用
**L5** 的机制（`app/infrastructure/adapters/midas/write_probe.py` 的 `_plan` 规则，
模板声明由 `app/infrastructure/adapters/midas/write_templates.py` **唯一**解析）：
前置编号 = 该端点既有编号的 `max + 1`（`id_source = "target"` 的前置取**目标**编号；
目标可用 `target_id_source` **反向**取某个前置的编号），按模板声明的
`references` / `self_references` 把编号写回，**按声明顺序创建**、**逆序删除**，
**只**碰自建编号。前置链的判定点**不**重写：编号分配 = 本文件 `plan_chain()`，
由 `tests/test_midas_put_edits_p151.py` 逐条断言与 L5 的 `_plan` **等价**。

别名路由（R120，P151 工具化）
-----------------------------
`DESIGN.*` 别名路由的 `DELETE` 在本 build 上**不生效**（返回 `200` 而记录仍在）⇒ 清理路径 =
**同表 `DB.*` 路由**（`DELETE /DB/<CODE>/<自建编号>`）。⚠️ 别名映射**必须来自实测**：
`ALIAS_ROUTES` 的每一对都由本工具的 `--probe-aliases` **当批实测**（自建编号经别名路由创建 ⇒
出现在同表 `DB.*` 路由的读回块里 ⇒ `DB.*` 路由 `DELETE` 后**两个**路由再读均不在），
逐条记进证据的 `alias_cleanup` 块（`same_table_observed` / `alias_delete_effective` /
`db_delete_effective` / `delete_confirmed`），**不**按名字臆造任何映射。
证据里**区分**「删除已确认」（本端点路由再读不在）/「别名清理已确认」/「删除未确认」（如实记残留）。

纪律
----
* **只碰自建编号**：编号 = 该端点既有编号的 `max + 1`（空项目 ⇒ `1`）；删除**必带路径 key**。
* **跑前 / 跑后只读哨兵**：对**全部**目标端点做只读 `GET`；**跑前非空 ⇒ 一个写请求都不发**
  （`aborted`）；**跑后非空 ⇒ 如实记 `residue`**（**不**声称零残留）；`residue ⊄ allowed_residue`
  ⇒ 退出码 1（**只**放行已披露且实测删不掉的残留，见「残留与别名」）。
* **分块 + 健康检查**（P149-B2 两次实例崩溃的教训）：每块 ≤ `--chunk-size`（默认 **10**）条，
  块间做**只读**健康检查 `GET /DB/NODE`；非 `200` ⇒ **立即中止**。
* **前置链（P151）**：前置对象**按声明顺序**创建、目标清理后**逆序**删除；编号一律**重新分配**
  （见「目标集」）；哨兵**额外**覆盖前置端点（只读），跑前 / 跑后都必须为空。
* **累积 + 续跑**：既有证据的行**逐字节保留**，`--limit` 限制单次尝试条数（默认 = 一块）；
  `CRITERION_VERSION` 变更 ⇒ 既有行**全部**重测（P151 **未**改判据 ⇒ 版本仍 **3**）。
* 证据里**绝不**出现凭据；也**不**保存响应体原文（只存判定所需的编号 / 状态码 / 字段改动）。
* 只依赖标准库 + `httpx`（探针必需）+ `app/`（模板声明的**唯一**解析点：`write_templates.py`）；
  「条目形状判定」复用同目录 `check_write_templates.py`（**唯一**判定点）。

用法（仓库根目录执行；`--probe` 需要 `MIDAS_BASE_URL` / `MIDAS_MAPI_KEY`）
------------------------------------------------------------------------
    # 有界侦察（默认一块 ≤ 10 条 + 块间只读健康检查 + 跑前 / 跑后只读哨兵）
    python registry/tools/probe_put_edits.py --probe
    python registry/tools/probe_put_edits.py --probe --limit 3 --only DB.SECT
    python registry/tools/probe_put_edits.py --probe --limit 20 --chunk-size 10
    python registry/tools/probe_put_edits.py --probe --only DB.BMLD --limit 1 --allow-residue DESIGN.SRC.AIK-SRC2K.DSRC

    # R120：别名路由的**实测** + 收尾清理（自建编号；两个路由再读确认）
    python registry/tools/probe_put_edits.py --probe-aliases

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

# ===== 前置链（L5 机制；R118 续跑 = P151）=====

OWNER_BODY_LABEL = "owner"
"""`references[].in` 里代表「目标自身 body」的标签（与 L5 的 `write_templates` 同一取值）。"""

ID_SOURCE_TARGET = "target"
"""前置编号来源：**目标**分配到的编号（与 L5 的 `write_templates` 同一取值）。"""

DELETE_CONFIRMED = "delete_confirmed"
DELETE_VIA_ALIAS = "delete_confirmed_via_alias"
DELETE_UNCONFIRMED = "delete_unconfirmed"
"""「删除已确认」（本端点路由再读不在）/「别名清理已确认」/「删除未确认」（如实记残留）。"""

# ===== R120：`DESIGN.*` 别名路由的**候选**（映射本身必须由 `--probe-aliases` **实测**）=====

ALIAS_ROUTES: dict[str, dict[str, str]] = {
    "DESIGN.RC.DRC": {
        "alias_uri": "/DESIGN/RC/DRC",
        "db_key": "DB.DCON",
        "db_uri": "/DB/DCON",
    },
    "DESIGN.RC.KDS-41-20-2022.DCTL": {
        "alias_uri": "/DESIGN/RC/KDS-41-20-2022/DCTL",
        "db_key": "DB.DCTL",
        "db_uri": "/DB/DCTL",
    },
    "DESIGN.STEEL.DSTL": {
        "alias_uri": "/DESIGN/STEEL/DSTL",
        "db_key": "DB.DSTL",
        "db_uri": "/DB/DSTL",
    },
}
"""P150 实测出的**候选**配对（`DESIGN.*` 别名路由 → **同表** `DB.*` 路由）。

⚠️ 这里**只**是候选：每一对都必须由 `--probe-aliases` 当批**实测**（自建编号经别名路由创建 ⇒
出现在 `DB.*` 路由的读回块里 ⇒ `DB.*` 路由 `DELETE` 后**两个**路由再读均不在）才可用于清理；
`same_table_observed` 为 `false` 的候选**不**参与清理（如实记进证据，**不**按名字臆造映射）。
"""


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


def prerequisite_chain_targets(repo: pathlib.Path) -> list[str]:
    """**带**前置链的目标端点（数据侧事实；P151 起由本工具**一并实测**）。"""
    return [str(row["key"]) for row in targets(repo) if int(row["prerequisites"]) > 0]


def left_out_prerequisite_chains(repo: pathlib.Path, rows: Any = None) -> list[str]:
    """**仍未**取得结论的带前置链端点 = 数据侧带链的端点 − 证据里已有行（P151 起为空）。

    Args:
        rows: 本次即将落盘的 `{key: row}`（`probe()` 传入**内存**行，否则读盘面）。
    """
    done = set(_existing_rows(repo) if rows is None else rows)
    return [key for key in prerequisite_chain_targets(repo) if key not in done]


# ===== 前置链（L5 机制；P151）=====


def load_templates(repo: pathlib.Path) -> Any:
    """装载数据侧模板（`app/.../write_templates.load_write_templates` —— **唯一**解析点）。

    ⚠️ 前置链的声明（`prerequisites` / `references` / `self_references` / `target_id_source` /
    `id_source`）**只**由这一个解析器解释 —— 本工具**不**另写一份解析规则。
    """
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from app.infrastructure.adapters.midas.write_templates import (  # noqa: PLC0415
        load_write_templates,
    )

    return load_write_templates(repo / "registry")


def template_of(repo: pathlib.Path, key: str) -> Any:
    """该端点的数据侧模板（`WritePayloadTemplate`；无模板 ⇒ `None`）。"""
    return load_templates(repo).get(key)


def prerequisite_keys(repo: pathlib.Path, key: str) -> list[str]:
    """该端点模板声明的前置端点 key（**按声明顺序**、**保留重复** —— 同一端点可被多次引用）。"""
    template = template_of(repo, key)
    if template is None:
        return []
    return [str(item.key) for item in template.prerequisites]


def _set_at(body: Any, path: Any, value: int) -> None:
    """按路径（字符串键 + 整数下标）把编号写回 body（与 L5 的 `_set_at` **同一**语义）。

    Raises:
        ValueError: 路径在 body 里不存在（数据缺陷**不**静默跳过）。
    """
    steps = list(path)
    node = body
    for step in steps[:-1]:
        try:
            node = node[step]
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError("write_template_reference_path_missing") from error
    last = steps[-1]
    if isinstance(node, list) and isinstance(last, int) and -len(node) <= last < len(node):
        node[last] = value
        return
    if isinstance(node, dict) and last in node:
        node[last] = value
        return
    raise ValueError("write_template_reference_path_missing")


def plan_chain(
    template: Any, owner_body: Any, own_id: Any, existing_by_key: dict[str, Any]
) -> tuple[Any, list[tuple[str, str, Any]], str]:
    """L5 前置链的编号分配与引用写回（**纯函数** ⇒ `--check` 可**离线**复算）。

    规则与 `app/infrastructure/adapters/midas/write_probe.py::_plan` **逐条一致**
    （由 `tests/test_midas_put_edits_p151.py` 的等价性用例断言）：

    ① 前置编号 = 该端点既有编号的 `max + 1`（同一端点的多个前置按声明顺序依次 `+1`）；
    ② `target_id_source` 声明的目标编号 = 那个前置分配到的编号（缺省 = `own_id`）；
    ③ `id_source = "target"` 的前置反过来取**目标**编号；
    ④ `self_references` / `references` 声明编号出现的路径，逐条写回（路径不存在 ⇒ 抛错）。

    Returns:
        `(改写后的目标请求体, [(前置 key, 实分配编号, 已写回的请求体), ...], 目标的实分配编号)`。

    Raises:
        ValueError: 模板声明的引用路径 / 承载 body / 目标编号来源不存在。
    """
    if template is None or not template.prerequisites:
        return owner_body, [], str(own_id)
    bodies: dict[str, Any] = {OWNER_BODY_LABEL: json.loads(json.dumps(owner_body))}
    for prerequisite in template.prerequisites:
        bodies[prerequisite.label()] = json.loads(json.dumps(prerequisite.body))
    next_ids: dict[str, int] = {}
    allocated: dict[str, str] = {}
    for prerequisite in template.prerequisites:
        if prerequisite.id_source == ID_SOURCE_TARGET:
            continue
        if prerequisite.key not in next_ids:
            existing = existing_by_key.get(prerequisite.key, ())
            next_ids[prerequisite.key] = (
                max((int(item) for item in existing if str(item).isdigit()), default=0) + 1
            )
        allocated[prerequisite.label()] = str(next_ids[prerequisite.key])
        next_ids[prerequisite.key] += 1
    target_id = str(own_id)
    if template.target_id_source:
        if template.target_id_source not in allocated:
            raise ValueError("write_template_target_id_source_unknown")
        target_id = allocated[template.target_id_source]
    for prerequisite in template.prerequisites:
        if prerequisite.id_source == ID_SOURCE_TARGET:
            allocated[prerequisite.label()] = target_id
    for path in template.self_references:
        _set_at(bodies[OWNER_BODY_LABEL], path, int(target_id))
    planned: list[tuple[str, str, Any]] = []
    for prerequisite in template.prerequisites:
        item_id = allocated[prerequisite.label()]
        for reference in prerequisite.references:
            container = bodies.get(reference.in_label)
            if container is None:
                raise ValueError("write_template_reference_unknown_body")
            _set_at(container, reference.path, int(item_id))
        planned.append((str(prerequisite.key), item_id, bodies[prerequisite.label()]))
    return bodies[OWNER_BODY_LABEL], planned, target_id

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


def _manifest_index(repo: pathlib.Path) -> dict[str, dict[str, Any]]:
    """`registry/manifest.json` 的 `key -> 条目` 索引（**只读**）。"""
    document = json.loads((repo / "registry" / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    return {str(entry["key"]): entry for entry in document["endpoints"]}


def sentinel_rows(repo: pathlib.Path) -> list[dict[str, Any]]:
    """哨兵端点 = 全部目标 ∪ 全部**前置**端点（**只读**）。

    P151 起前置链也会创建 / 删除记录 ⇒ 只核对目标端点**不够**：前置端点（如 `DB.NODE`）
    也必须一并进跑前 / 跑后哨兵（**不**声称零残留，见「残留与别名」）。
    """
    rows = list(targets(repo))
    index = _manifest_index(repo)
    seen = {str(row["key"]) for row in rows}
    extra: list[dict[str, Any]] = []
    for row in rows:
        for key in prerequisite_keys(repo, str(row["key"])):
            if key in seen or key not in index:
                continue
            seen.add(key)
            extra.append(
                {
                    "key": key,
                    "uri": "/" + str(index[key].get("uri") or "").lstrip("/"),
                    "read_root": str((index[key].get("wrapper") or {}).get("read_root") or ""),
                }
            )
    return rows + extra


def _write_wrapper_of(repo: pathlib.Path, key: str) -> str:
    """该端点数据侧声明的**写**包装键（`wrapper.write`；缺 ⇒ 空串）。"""
    entry = _manifest_index(repo).get(key) or {}
    return str((entry.get("wrapper") or {}).get("write") or "")


def _shape_for_wrapper(wrapper: str) -> str:
    """包装键 → 请求体形状（与 L5 同一判定：`Assign` ⇒ 编号键控条目）。"""
    return SHAPE_ASSIGN_ITEM if wrapper == "Assign" else SHAPE_ARGUMENT_ITEM

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

def _cleanup_chain(client: Any, repo: pathlib.Path, chain: list[dict[str, Any]]) -> None:
    """**逆序**删除本次创建的前置对象（**只**碰自建编号；逐条以「再读确认不在」为准 —— R119）。"""
    index = _manifest_index(repo)
    for item in reversed(chain):
        if not item.get("created"):
            continue
        entry = index.get(str(item["key"])) or {}
        uri = "/" + str(entry.get("uri") or "").lstrip("/")
        read_root = str((entry.get("wrapper") or {}).get("read_root") or "")
        result = _send(client, "DELETE", f"{uri}/{item['item_id']}")
        item["delete_status"] = result["status_code"]
        item["deleted"] = _gone(client, uri, read_root, str(item["item_id"]))


def probe_key_chained(client: Any, row: dict[str, Any], repo: pathlib.Path) -> dict[str, Any]:
    """带前置链的「创建 → 读回 → 编辑 → 读回确认 → 删除 → 读回消失」（P151 续跑）。

    与零前置链的 `probe_key()` **同一判据**，差别只有两处：
    ① 目标创建**之前**先按模板**按声明顺序**创建前置对象（编号一律**重新分配**，见
       `plan_chain()`；`--check` 可用「模板 + `scope_before` + `created_id`」**离线**复算）；
    ② 目标清理后**逆序**删除前置对象，且删除一律以「**再读确认不在**」为准（R119）。
    """
    check_tool = _load_check_tool()
    key = str(row["key"])
    uri = str(row["uri"])
    read_root = str(row["read_root"])
    create_method = str(row["write_method"])
    template = template_of(repo, key)
    base: dict[str, Any] = {
        "uri": uri,
        "read_root": read_root,
        "wrapper": str(row["wrapper"]),
        "write_method": create_method,
        "products": list(row["products"]),
        "prerequisites": int(row["prerequisites"]),
        "created_id": "",
        "own_id": "",
        "target_id": "",
        "scope_before": {},
        "prerequisite_chain": [],
        "read_back": False,
        "edit": None,
        "edit_confirmed": False,
        "deleted": False,
        "delete_state": "",
        "put_shape": "",
        "put_status_code": "",
        "put_attempts": [],
        "put_absent_status": "",
        "put_absent_recreated": None,
        "requires_existing_record": None,
        "detail": "",
        "payload_source": "data_side_template",
    }
    if template is None:
        return {**base, "verdict": FAILED, "detail": "no_data_side_template"}
    before = _get(client, uri, read_root)
    if before["ids"] is None:
        verdict = SKIPPED if before["status_code"] == "" else FAILED
        return {
            **base,
            "status_code": before["status_code"],
            "verdict": verdict,
            "detail": f"read_before_failed:{before['detail'] or before['status_code']}",
        }
    own_id = str(max((int(name) for name in before["ids"] if str(name).isdigit()), default=0) + 1)
    base["own_id"] = own_id
    base["created_id"] = own_id
    base["scope_before"] = {key: list(before["ids"])}
    # 前置端点的既有编号：**只读**读一次（编号分配的依据 ⇒ 证据里逐条可离线复算）
    index = _manifest_index(repo)
    existing_by_key: dict[str, list[str]] = {}
    for prereq_key in prerequisite_keys(repo, key):
        if prereq_key in existing_by_key:
            continue
        entry = index.get(prereq_key)
        if entry is None:
            return {**base, "verdict": FAILED, "detail": f"prerequisite_not_in_manifest:{prereq_key}"}
        state = _get(
            client,
            "/" + str(entry.get("uri") or "").lstrip("/"),
            str((entry.get("wrapper") or {}).get("read_root") or ""),
        )
        if state["ids"] is None:
            return {**base, "verdict": FAILED, "detail": f"prerequisite_unreadable:{prereq_key}"}
        existing_by_key[prereq_key] = list(state["ids"])
        base["scope_before"][prereq_key] = list(state["ids"])
    try:
        body, planned, target_id = plan_chain(template, template.body, own_id, existing_by_key)
    except ValueError as error:
        return {**base, "verdict": FAILED, "detail": f"plan_failed:{error}"}
    base["target_id"] = target_id
    base["created_id"] = target_id
    item_schema = check_tool.request_schema(repo, _schema_relative(repo, key), key)
    edit = editable_change(body, item_schema)
    base["edit"] = edit
    changed = body if edit is None else apply_change(body, str(edit["path"]), edit["to"])
    # ① 前置对象：**按声明顺序**创建（只碰自建编号；失败 ⇒ 立刻逆序回收已建的）
    chain: list[dict[str, Any]] = []
    base["prerequisite_chain"] = chain
    for prereq_key, item_id, prereq_body in planned:
        entry = index.get(prereq_key) or {}
        method = "POST" if "POST" in _methods(entry.get("methods")) else "PUT"
        shape = _shape_for_wrapper(_write_wrapper_of(repo, prereq_key))
        result = _send(
            client,
            method,
            "/" + str(entry.get("uri") or "").lstrip("/"),
            _wrap(shape, prereq_body, item_id),
        )
        chain.append(
            {
                "key": prereq_key,
                "item_id": item_id,
                "create_method": method,
                "create_status": result["status_code"],
                "created": result["status_code"] == 200,
                "delete_status": "",
                "deleted": False,
            }
        )
        if result["status_code"] != 200:
            _cleanup_chain(client, repo, chain)
            if result.get("transport_error"):
                return {**base, "verdict": SKIPPED, "detail": f"prerequisite_transport:{prereq_key}"}
            return {
                **base,
                "verdict": FAILED,
                "detail": f"prerequisite_rejected:{prereq_key}:{result['status_code']}",
            }
    # ② 目标：创建 → 读回
    created = _send(client, create_method, uri, _wrap(_create_shape(row), body, target_id))
    base["status_code"] = created["status_code"]
    if created["status_code"] != 200:
        _cleanup_chain(client, repo, chain)
        if created.get("transport_error"):
            return {**base, "verdict": SKIPPED, "detail": f"create_transport:{created['detail']}"}
        return {
            **base,
            "verdict": FAILED,
            "detail": f"create_rejected:{created['status_code']}:{created['detail']}",
        }
    base["read_back"] = target_id in (_get(client, uri, read_root)["ids"] or ())
    if edit is None:
        # 无可机械改动的标量 ⇒ 如实留缺，但仍走「创建 → 读回 → 删除 → 逆序回收前置」保证零残留
        removed = _send(client, "DELETE", f"{uri}/{target_id}")
        base["deleted"] = removed["status_code"] == 200 and _gone(client, uri, read_root, target_id)
        base["delete_state"] = DELETE_CONFIRMED if base["deleted"] else DELETE_UNCONFIRMED
        _cleanup_chain(client, repo, chain)
        base["detail"] = (
            REASON_NO_EDITABLE_SCALAR
            if base["deleted"]
            else f"{REASON_NO_EDITABLE_SCALAR}+delete_unconfirmed"
        )
        return {**base, "verdict": LEFT_OUT}
    # ③ 编辑（PUT 一个**改动过的值**）→ 读回确认**改动生效**
    attempts: list[dict[str, Any]] = []
    for shape in PUT_SHAPES:
        result = _send(client, "PUT", uri, _wrap(shape, changed, target_id))
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
        removed = _send(client, "DELETE", f"{uri}/{target_id}")
        base["deleted"] = removed["status_code"] == 200 and _gone(client, uri, read_root, target_id)
        base["delete_state"] = DELETE_CONFIRMED if base["deleted"] else DELETE_UNCONFIRMED
        _cleanup_chain(client, repo, chain)
        return {
            **base,
            "verdict": FAILED,
            "detail": f"put_rejected:{attempts[-1]['status_code']}:{attempts[-1]['detail']}",
        }
    after_put = _get(client, uri, read_root)
    block = (after_put.get("payload") or {}).get(read_root)
    observed = block.get(target_id) if isinstance(block, dict) else None
    if isinstance(observed, dict):
        try:
            base["edit_confirmed"] = read_at(observed, str(edit["path"])) == edit["to"]
        except KeyError:
            base["edit_confirmed"] = False
    # ④ 删除（**带路径 key**）→ 读回确认消失；⑤ 无副作用观察（删除后再发同一 PUT）
    removed = _send(client, "DELETE", f"{uri}/{target_id}")
    base["deleted"] = removed["status_code"] == 200 and _gone(client, uri, read_root, target_id)
    absent = _send(client, "PUT", uri, _wrap(base["put_shape"], changed, target_id))
    base["put_absent_status"] = absent["status_code"]
    base["put_absent_recreated"] = target_id in (_get(client, uri, read_root)["ids"] or ())
    base["requires_existing_record"] = not base["put_absent_recreated"]
    if base["put_absent_recreated"]:
        _send(client, "DELETE", f"{uri}/{target_id}")
        base["deleted"] = _gone(client, uri, read_root, target_id)
    # ⑥ 前置对象：**逆序**删除 → 逐条再读确认
    _cleanup_chain(client, repo, chain)
    base["delete_state"] = DELETE_CONFIRMED if base["deleted"] else DELETE_UNCONFIRMED
    chain_clean = all(bool(item["deleted"]) for item in chain)
    final_gone = _gone(client, uri, read_root, own_id)
    passed = bool(
        base["read_back"]
        and base["edit_confirmed"]
        and base["deleted"]
        and chain_clean
        and final_gone
    )
    if passed:
        detail = ""
    elif not base["read_back"]:
        detail = "read_back_missing"
    elif not base["edit_confirmed"]:
        detail = "edit_not_effective"
    elif not chain_clean:
        detail = "prerequisite_cleanup_failed"
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
    probeable = list(all_targets)
    endpoints = _existing_rows(repo)
    pending = [row for row in probeable if not only or str(row["key"]) in only]
    pending = [row for row in pending if str(row["key"]) not in endpoints][:limit]
    sentries = sentinel_rows(repo)
    print(
        f"PUT 编辑判据：目标 {len(all_targets)} 个（零前置链 "
        f"{len(zero_prerequisite_targets(repo))} 个 · 带前置链 "
        f"{len(prerequisite_chain_targets(repo))} 个）；哨兵 {len(sentries)} 个端点；"
        f"既有证据 {len(endpoints)} 行 ⇒ 本次待测 {len(pending)} 个"
        f"（实例 {INSTANCE_ALIAS} / {INSTANCE_PRODUCT}）"
    )
    aborted = ""
    sentinel_before: dict[str, dict[str, Any]] = {}
    sentinel_after: dict[str, dict[str, Any]] = {}
    with httpx.Client(
        base_url=base_url, headers={"MAPI-Key": key_value}, timeout=60.0
    ) as client:
        sentinel_before = sentinel(client, sentries)
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
                    probe_one = probe_key_chained if int(row["prerequisites"]) > 0 else probe_key
                    endpoints[str(row["key"])] = probe_one(client, row, repo)
                health = client.get(HEALTH_PATH).status_code
                print(f"  块 {start // chunk_size + 1} 完成（{len(chunk)} 条）；健康检查 → {health}")
                if health != 200:
                    aborted = f"健康检查 {HEALTH_PATH} → {health}（**立即中止**，P149-B2 的教训）"
                    print(f"  ⚠️ {aborted}")
                    break
        sentinel_after = sentinel(client, sentries)
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
            "**P151 续跑**：带前置链的端点由 `probe_key_chained()` 走**同一判据** —— 目标创建**之前**"
            "按模板**按声明顺序**创建前置对象（编号一律**重新分配**：该端点既有编号的 `max + 1`；"
            '`id_source = "target"` 的前置取**目标**编号），目标清理后**逆序**删除；'
            "分配依据 = `scope_before`（只读快照）+ `created_id` ⇒ `--check` 可**离线**复算。",
            "前置链的声明（`prerequisites` / `references` / `self_references` / `target_id_source` / "
            "`id_source`）由 `app/infrastructure/adapters/midas/write_templates.py` **唯一**解析，"
            "编号分配与 L5 的 `_plan` **逐条等价**（见 `tests/test_midas_put_edits_p151.py`）。",
            "⚠️ 哨兵覆盖 = 全部目标 ∪ 全部**前置**端点（只读；前置链同样可能留下残留 ⇒ 一并核对）。",
            "`alias_cleanup`（**R120**）：`DESIGN.*` 别名路由的 `DELETE` **不生效**（返回 `200` 而记录仍在）"
            "⇒ 清理走**同表 `DB.*` 路由**；映射由 `--probe-aliases` **当批实测**（`same_table_observed`），"
            "证据里**区分**「删除已确认」（本端点路由再读不在）/「别名清理已确认」/「删除未确认」。",
        ],
        "criterion_version": CRITERION_VERSION,
        "instance": {
            "alias": INSTANCE_ALIAS,
            "product": INSTANCE_PRODUCT,
            "base_url": base_url,
            "probed_at": PROBED_AT,
            "scope": "有数据侧模板 ∧ GEN NX 有 PUT ∧ 有 DELETE / GET / read_root ∧ 已启用"
            "（零前置链 + 带前置链）",
        },
        "targets": len(all_targets),
        "probeable": len(probeable),
        "zero_prerequisite": len(zero_prerequisite_targets(repo)),
        "prerequisite_chain_targets": prerequisite_chain_targets(repo),
        "left_out_prerequisite_chain": left_out_prerequisite_chains(repo, endpoints),
        "counts": counts,
        "aborted": aborted,
        "sentinel_endpoints": sorted(str(row["key"]) for row in sentries),
        "sentinel_before": sentinel_before,
        "sentinel_after": sentinel_after,
        "residue": residue_of(sentinel_after),
        "allowed_residue": sorted(allow_residue),
        "alias_cleanup": _existing_document(repo).get("alias_cleanup") or {},
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


# ===== 离线复算（P151：前置链 + R120 别名清理）=====


def check_chain_row(repo: pathlib.Path, key: str, row: dict[str, Any]) -> list[str]:
    """带前置链的行的**离线**复算：编号分配（`plan_chain`）+ 逆序删除逐条核对。"""
    errors: list[str] = []
    scope = row.get("scope_before")
    own_id = str(row.get("own_id") or "")
    if not isinstance(scope, dict) or not scope:
        return [f"{key}: 带前置链的行必须记录 `scope_before`（只读快照）"]
    if not own_id.isdigit():
        return [f"{key}: `own_id` 必须是自建编号（正整数）"]
    template = template_of(repo, key)
    if template is None:
        return [f"{key}: 盘面上没有该端点的数据侧模板"]
    try:
        _body, planned, target_id = plan_chain(template, template.body, own_id, scope)
    except ValueError as error:
        return [f"{key}: `plan_chain` 复算失败：{error}"]
    if str(row.get("target_id") or "") != target_id:
        errors.append(f"{key}: `target_id` = {row.get('target_id')!r}，复算 = {target_id!r}")
    if str(row.get("created_id") or "") != target_id:
        errors.append(f"{key}: `created_id` = {row.get('created_id')!r}，复算 = {target_id!r}")
    chain = row.get("prerequisite_chain")
    if not isinstance(chain, list) or len(chain) != len(planned):
        errors.append(f"{key}: `prerequisite_chain` 条数与复算不一致")
        return errors
    for item, plan in zip(chain, planned, strict=True):
        prereq_key, item_id, _prereq_body = plan
        if str(item.get("key")) != prereq_key or str(item.get("item_id")) != item_id:
            errors.append(
                f"{key}: 前置链条目 {item.get('key')}#{item.get('item_id')} 与复算 "
                f"{prereq_key}#{item_id} 不一致"
            )
    # 结论与删除状态**必须**自洽：`PASSED` 要求目标 + **全部**前置都「再读确认不在」
    if str(row.get("verdict")) == PASSED:
        if not bool(row.get("deleted")):
            errors.append(f"{key}: `PASSED` 的行必须确认目标已删除")
        if not all(bool(item.get("deleted")) for item in chain):
            errors.append(f"{key}: `PASSED` 的行必须逐条确认前置对象已删除")
    return errors


def check_alias_cleanup(document: dict[str, Any]) -> list[str]:
    """R120：`alias_cleanup` 与逐行状态**自洽**（**离线**复算，**不**重新实测）。"""
    errors: list[str] = []
    cleanup = document.get("alias_cleanup") or {}
    if not isinstance(cleanup, dict):
        return ["`alias_cleanup` 必须是对象"]
    if sorted(cleanup) != sorted(ALIAS_ROUTES):
        errors.append(f"`alias_cleanup` 的键 = {sorted(cleanup)}；实测候选 = {sorted(ALIAS_ROUTES)}")
    rows = document.get("endpoints") or {}
    residue = document.get("residue") or {}
    for key, entry in sorted(cleanup.items()):
        candidate = ALIAS_ROUTES.get(key)
        if candidate is None:
            errors.append(f"{key}: 不在实测候选里（**不**得臆造别名映射）")
            continue
        if not isinstance(entry, dict):
            errors.append(f"{key}: `alias_cleanup` 的条目必须是对象")
            continue
        for field, expected in sorted(candidate.items()):
            if str(entry.get(field) or "") != expected:
                errors.append(f"{key}: `{field}` = {entry.get(field)!r}；候选 = {expected!r}")
        if entry.get("measured") is not True:
            errors.append(f"{key}: 别名配对必须**实测**（`measured` 必须为真）")
            continue
        row = rows.get(key)
        if not isinstance(row, dict):
            errors.append(f"{key}: `alias_cleanup` 有该配对，但证据里没有这一行")
            continue
        state = str(row.get("delete_state") or "")
        if state not in {DELETE_CONFIRMED, DELETE_VIA_ALIAS, DELETE_UNCONFIRMED}:
            errors.append(f"{key}: `delete_state` = {state!r} 不在允许集合里")
        if entry.get("same_table_observed") is not True:
            errors.append(f"{key}: `same_table_observed` 不为真 ⇒ 该配对**不**可用于清理")
            continue
        # R120 的判据本身：别名路由的 `DELETE` **不生效**，同表 `DB.*` 路由**生效**
        if entry.get("alias_delete_effective") is not False:
            errors.append(
                f"{key}: R120 要求别名路由 `DELETE` **不生效**"
                "（实测 `alias_delete_effective` 必须为假）"
            )
        if entry.get("db_delete_effective") is not True:
            errors.append(f"{key}: 同表 `DB.*` 路由 `DELETE` 必须**生效**（这才是清理路径）")
        confirmed = entry.get("delete_confirmed") is True
        if confirmed:
            if state != DELETE_VIA_ALIAS:
                errors.append(f"{key}: 别名清理已确认 ⇒ `delete_state` 必须是 {DELETE_VIA_ALIAS!r}")
            if bool(row.get("deleted")):
                errors.append(f"{key}: 别名清理已确认 ⇒ 本端点路由本就不该能删掉（`deleted` 应为假）")
            if key in residue:
                errors.append(f"{key}: 别名清理已确认 ⇒ **不得**留在 `residue` 里")
        else:
            if state != DELETE_UNCONFIRMED:
                errors.append(f"{key}: 别名清理**未**确认 ⇒ `delete_state` 必须是 {DELETE_UNCONFIRMED!r}")
            if key not in residue:
                errors.append(f"{key}: 别名清理未确认 ⇒ 必须在 `residue` 里如实披露")
    # 「删除已确认」**不得**留残留；「删除未确认」**必须**如实披露
    for key, row in sorted(rows.items()):
        if not isinstance(row, dict):
            continue
        state = str(row.get("delete_state") or "")
        if state == DELETE_CONFIRMED and key in residue:
            errors.append(f"{key}: 删除已确认 ⇒ **不得**留在 `residue` 里")
        if state == DELETE_UNCONFIRMED and key not in residue:
            errors.append(f"{key}: 删除未确认 ⇒ 必须在 `residue` 里如实披露")
    return errors


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
        # 前置链条数**逐行**由数据侧复算（P150 的 56 行 = 0；P151 的 15 行 = 模板声明数）
        declared = len(prerequisite_keys(repo, key))
        if int(row.get("prerequisites") or 0) != declared:
            errors.append(
                f"{key}: `prerequisites` = {row.get('prerequisites')}，数据侧复算 = {declared}"
            )
        if declared:
            errors.extend(check_chain_row(repo, key, row))
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
    errors.extend(check_alias_cleanup(document))
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


def _counts(rows: dict[str, Any]) -> dict[str, int]:
    """逐行 `verdict` 计数（`--probe` / `--probe-aliases` / `--check` 共用）。"""
    counts: dict[str, int] = {}
    for row in rows.values():
        if isinstance(row, dict):
            counts[str(row.get("verdict"))] = counts.get(str(row.get("verdict")), 0) + 1
    return counts


def probe_aliases(repo: pathlib.Path, allow_residue: tuple[str, ...] = ()) -> int:
    """R120：**实测** `DESIGN.*` 别名路由 ↔ 同表 `DB.*` 路由，并走同表路由清理（自建编号）。

    判据（**先写清楚再动手**；逐条记进证据的 `alias_cleanup`）：

    1. 跑前哨兵（全部目标 ∪ 全部前置端点）必须**为空**（已披露残留可 `--allow-residue` 放行）；
    2. 自建编号 = 两个路由既有编号的 `max + 1`（空 ⇒ `1`）；**只**碰自建编号；
    3. 经**别名路由**创建 ⇒ 该编号**必须**出现在同表 `DB.*` 路由的读回块里 ⇒ `same_table_observed`；
    4. 别名路由 `DELETE` → **再读**（记录仍在 ⇒ `alias_delete_effective = false`；R119 / R120）；
    5. 同表 `DB.*` 路由 `DELETE` → **两个**路由再读**都**不在 ⇒ `db_delete_effective` / `delete_confirmed`；
    6. 清理失败 ⇒ **如实**记 `delete_confirmed = false` 并进 `residue`（退出码 1）。

    ⚠️ `same_table_observed` 为 `false` 的候选**不**可用于清理（**不**按名字臆造映射）；
    `DESIGN.*` 路由 `DELETE` 不生效的成因需 **MIDAS 侧**排查（R120）。
    """
    import httpx  # noqa: PLC0415

    base_url = os.environ.get("MIDAS_BASE_URL", "").rstrip("/")
    key_value = os.environ.get("MIDAS_MAPI_KEY", "")
    if not base_url or not key_value:
        print("❌ --probe-aliases 需要 MIDAS_BASE_URL / MIDAS_MAPI_KEY（见 scripts/load-midas-env.ps1）")
        return 1
    document = _existing_document(repo)
    if not document:
        print(f"❌ 缺 registry/{EVIDENCE_RELATIVE}（先跑 --probe）")
        return 1
    rows = _existing_rows(repo)
    if not rows:
        print(f"❌ 证据的 criterion_version 与本工具不一致（先重跑 --probe）")
        return 1
    index = _manifest_index(repo)
    sentries = sentinel_rows(repo)
    cleanup: dict[str, Any] = dict(document.get("alias_cleanup") or {})
    residue: dict[str, list[str]] = {
        str(key): list(value) for key, value in (document.get("residue") or {}).items()
    }
    failed = False
    with httpx.Client(
        base_url=base_url, headers={"MAPI-Key": key_value}, timeout=60.0
    ) as client:
        blocked = {
            name: ids
            for name, ids in residue_of(sentinel(client, sentries)).items()
            if name not in allow_residue
        }
        if blocked:
            print(f"⚠️ 跑前哨兵**非空** ⇒ 一个写请求都不发（{sorted(blocked)[:5]}）")
            return 1
        for alias_key, candidate in sorted(ALIAS_ROUTES.items()):
            template = template_of(repo, alias_key)
            entry = index.get(alias_key) or {}
            db_entry = index.get(candidate["db_key"]) or {}
            if template is None:
                cleanup[alias_key] = {**candidate, "measured": False, "detail": "no_template"}
                failed = True
                continue
            alias_root = str((entry.get("wrapper") or {}).get("read_root") or "")
            db_root = str((db_entry.get("wrapper") or {}).get("read_root") or "")
            before_ids = list(_get(client, candidate["alias_uri"], alias_root)["ids"] or ())
            before_ids += list(_get(client, candidate["db_uri"], db_root)["ids"] or ())
            own_id = str(
                max((int(name) for name in before_ids if str(name).isdigit()), default=0) + 1
            )
            method = "POST" if "POST" in _methods(entry.get("methods")) else "PUT"
            created = _send(
                client,
                method,
                candidate["alias_uri"],
                _wrap(_shape_for_wrapper(_write_wrapper_of(repo, alias_key)), template.body, own_id),
            )
            alias_after = _get(client, candidate["alias_uri"], alias_root)
            db_after = _get(client, candidate["db_uri"], db_root)
            same_table = bool(
                own_id in (alias_after["ids"] or ()) and own_id in (db_after["ids"] or ())
            )
            alias_delete = _send(client, "DELETE", f"{candidate['alias_uri']}/{own_id}")
            alias_effective = _gone(client, candidate["alias_uri"], alias_root, own_id)
            db_delete = _send(client, "DELETE", f"{candidate['db_uri']}/{own_id}")
            alias_gone = _gone(client, candidate["alias_uri"], alias_root, own_id)
            db_gone = _gone(client, candidate["db_uri"], db_root, own_id)
            confirmed = bool(same_table and alias_gone and db_gone)
            cleanup[alias_key] = {
                **candidate,
                "measured": True,
                "created_id": own_id,
                "create_status": created["status_code"],
                "same_table_observed": same_table,
                "alias_delete_status": alias_delete["status_code"],
                "alias_delete_effective": bool(alias_effective),
                "db_delete_status": db_delete["status_code"],
                "db_delete_effective": bool(db_gone),
                "delete_confirmed": confirmed,
                "detail": "" if confirmed else "delete_unconfirmed",
            }
            row = rows.get(alias_key)
            if isinstance(row, dict):
                row["delete_state"] = (
                    DELETE_VIA_ALIAS if confirmed else DELETE_UNCONFIRMED
                )
            print(
                f"  {alias_key}: same_table={same_table} alias_delete_effective={alias_effective} "
                f"db_delete_effective={db_gone} delete_confirmed={confirmed}"
            )
            if not confirmed:
                failed = True
        residue = residue_of(sentinel(client, sentries))
        # R121：**无**别名的残留 ⇒ 如实记「删除未确认」（**不**臆造别名映射）
        for key in sorted(residue):
            row = rows.get(key)
            if isinstance(row, dict) and not str(row.get("delete_state") or ""):
                row["delete_state"] = DELETE_UNCONFIRMED
    document["alias_cleanup"] = cleanup
    document["residue"] = residue
    document["endpoints"] = dict(sorted(rows.items()))
    document["counts"] = _counts(rows)
    (repo / "registry" / EVIDENCE_RELATIVE).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"已写入 registry/{EVIDENCE_RELATIVE}（alias_cleanup {len(cleanup)} 对；"
        f"残留 = {sorted(residue)}）"
    )
    return 1 if failed else 0


def summary(repo: pathlib.Path) -> int:
    """只打印汇总（逐条改动见证据文件）。"""
    document = _existing_document(repo)
    if not document:
        print(f"（缺 registry/{EVIDENCE_RELATIVE}）")
        return 0
    print(f"criterion_version = {document.get('criterion_version')}")
    print(f"实例 = {document.get('instance')}")
    print(
        f"目标 = {document.get('targets')}；零前置链 = {document.get('zero_prerequisite')}；"
        f"带前置链 = {len(document.get('prerequisite_chain_targets') or [])}；"
        f"仍未取得结论 = {len(document.get('left_out_prerequisite_chain') or [])}"
    )
    print(f"verdict = {document.get('counts')}")
    print(f"中止 = {document.get('aborted')!r}；残留 = {document.get('residue')}")
    print(f"别名清理（R120）= {sorted(document.get('alias_cleanup') or ())}")
    for key, row in sorted(document["endpoints"].items()):
        edit = row.get("edit") or {}
        chain = row.get("prerequisite_chain") or []
        print(
            f"  {key}: {row.get('verdict')} id={row.get('created_id')} "
            f"chain={len(chain)} shape={row.get('put_shape') or '-'} edit={edit.get('path')} "
            f"{edit.get('from')} -> {edit.get('to')} confirmed={row.get('edit_confirmed')} "
            f"requires_existing={row.get('requires_existing_record')} "
            f"delete_state={row.get('delete_state') or '-'} detail={row.get('detail')!r}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R118：写路径「编辑（PUT）」判据")
    parser.add_argument("--repo", default=REPO_DEFAULT)
    parser.add_argument("--probe", action="store_true", help="有界侦察（分块 + 哨兵；**有写请求**）")
    parser.add_argument(
        "--probe-aliases",
        action="store_true",
        help="R120：实测别名路由配对 + 同表 DB.* 路由清理（**有写请求**）",
    )
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
    if args.probe_aliases:
        allow = tuple(part.strip() for part in args.allow_residue.split(",") if part.strip())
        status = max(status, probe_aliases(repo, allow))
    if args.summary:
        status = max(status, summary(repo))
    if not (args.probe or args.check or args.summary or args.probe_aliases):
        print(__doc__)
    return status


if __name__ == "__main__":
    sys.exit(main())
