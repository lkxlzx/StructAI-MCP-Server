"""P150 / **R117** —— 请求方向 Schema 的「覆盖不全」收口（只读自省来源 `GET /info/db/<CODE>`）。

背景
----
`registry/schema/**` 的**请求方向** Schema 是**手册子集**的转录；端点定义里**已登记**一个
**只读**的机械来源 `schema_ref.introspect`（`info/db/<CODE>`，`registry/README.md` §4 / §2.3）。
两者逐字段比对即可机械量化「数据侧只转录了子集」——本文件的**可执行判定**：

1. **目标集 244 逐条可复算**（`targets()`）：全部「`schema_ref.introspect` 非空」的端点；
   工具**只发 `GET`**（源码里**没有** `.post(` / `.put(` / `.delete(` 调用）。
2. **证据诚实**：**244** 行；`verdict` = **199** `PASSED` + **45** `FAILED`（全部 `404`）；
   `aborted` 为空；`criterion_version` = **1**；实例 = `gen-local` / `GEN_NX` / `2026-10-11`。
3. **45 个 `404` 逐条可解释**：**23** 个 `unverified`（**R85**）· **15** 个
   `unavailable_on` 含 `gen-local` · **7** 个 **CIVIL_DESIGNER 独有**（`/info/db/<CODE>`
   是 NX 系路由）⇒ 本证据**不**写任何 `availability` / `unavailable_on`（自省路由 `404`
   **不**等于端点不可用 —— 那是**另一条**路由，需**另一次**实测）。
4. **裁决 R117 逐条可复算**：`add_fields` **21** · `record_left_out` **3** · `no_gap` **175** ·
   `NOT_COMPARABLE` **45**；3 个留缺的原因逐条（`product_not_probed` / `strict_schema_conflict`
   + `invalid_introspect_node`）。
5. **补 Schema 已落盘且幂等**：`--check` 退出码 **0**；21 个端点**逐条**已无待补字段；
   逐条补入 **212** 个字段名（来源 `introspect:<uri>`，逐条记在证据里）。
6. **反向缺口（`data_only`）一行未动**：**12** 个端点的「数据侧有、自省没有」字段**仍全部在**
   （逐条断言 `data_only` 与证据一致）——**不**删、**不**改名。
7. **留缺端点未被改动**：`DB.KFAC` / `DB.SSEIS` / `DB.SWIND` 的 Schema 文件相对 `HEAD`
   **一字未改**（`git diff --quiet`）。
8. **不引入非法 Schema 片段**：**只**搬进合法片段（`type` 合法 + 数组带 `items`）；
   `registry/schema/**` 仍 **625** 个合法对象、**没有**任何 `multi object`。
9. **判定未放宽**：`check_write_templates` 仍 **71 / 71** 非空判、**0** 未知字段、**0** 不可判
   body；
   且新增字段让 **3** 个父节点由「裸 `object` ⇒ **不判**」变成**可判**（判定在该处**变强**）。
10. **工具纪律**：`CHUNK_SIZE` = **20** + 块间只读健康检查 `GET /DB/NODE`；证据里**没有**凭据。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录。"""

TOOL_PATH = REPO_ROOT / "registry" / "tools" / "sync_introspect_fields.py"
"""R117 的复算工具（`--probe` 只读 / `--write` / `--check`）。"""

CHECK_TOOL_PATH = REPO_ROOT / "registry" / "tools" / "check_write_templates.py"
"""字段白名单的**唯一**判定点（P150 起「条目形状判定」抽成纯函数 `item_schema_of()`）。"""

EVIDENCE_PATH = REPO_ROOT / "registry" / "live" / "introspect_field_diff.json"
"""只读自省扫描的证据（244 行；含自省**原文** ⇒ `--write` / `--check` 可离线复算）。"""

MANIFEST_PATH = REPO_ROOT / "registry" / "manifest.json"
TEMPLATES_PATH = REPO_ROOT / "registry" / "live" / "write_templates.json"

INSTANCE_ALIAS = "gen-local"
INSTANCE_PRODUCT = "GEN_NX"
PROBED_AT = "2026-10-11"
CRITERION_VERSION = 1

EXPECTED_TARGETS = 244
"""有 `schema_ref.introspect` 的端点（**全部**只读扫描；不按可用性过滤）。"""

EXPECTED_PASSED = 199
EXPECTED_FAILED = 45
EXPECTED_DECISIONS = {
    "add_fields": 21,
    "record_left_out": 3,
    "no_gap": 175,
    "NOT_COMPARABLE": 45,
}
EXPECTED_ADDED_FIELDS = 212
"""逐条补入的字段名（21 个端点合计）。"""

EXPECTED_ADD_ENDPOINTS = (
    "DB.ACTL",
    "DB.GALD",
    "DB.HPCE",
    "DB.LCOM-CONC",
    "DB.LCOM-GEN",
    "DB.LCOM-SEISMIC",
    "DB.LCOM-SRC",
    "DB.LCOM-STEEL",
    "DB.LCOM-STLCOMP",
    "DB.MATD",
    "DB.MVHL",
    "DB.PJCF",
    "DB.POSL",
    "DB.SECT",
    "DB.SPFC",
    "DB.STAG",
    "DB.STOR",
    "DB.TDMT",
    "DB.THGC",
    "DB.THIK",
    "DB.THIS",
)

EXPECTED_LEFT_OUT = {
    "DB.KFAC": ("product_not_probed",),
    "DB.SSEIS": ("strict_schema_conflict", "invalid_introspect_node"),
    "DB.SWIND": ("strict_schema_conflict", "invalid_introspect_node"),
}
"""`record_left_out`（**如实留缺**）：端点**不可比** / 自省节点**非法** / 父节点**手工收紧**。"""

EXPECTED_REVERSE_GAP = {
    "DB.ACTL": ("CLATS",),
    "DB.CSCS": ("OPT_UPDATE_ALL_H",),
    "DB.ELEM": ("W_CON",),
    "DB.EPMT": (
        "MASONRY.BM.COMP_STRENGTH",
        "MASONRY.BM.FRICTION_ANGLE",
        "MASONRY.BM.V1",
        "MASONRY.BM.V2",
        "MASONRY.BM.V3",
        "MASONRY.BM.V4",
        "MASONRY.BM.V5",
        "MASONRY.BM.V6",
        "MASONRY.BM.V7",
        "MASONRY.BED_JOINT.COMP_STRENGTH",
        "MASONRY.BED_JOINT.BOND_WRENCH_STRENGTH",
        "MASONRY.HEAD_JOINT.COMP_STRENGTH",
        "MASONRY.HEAD_JOINT.BOND_WRENCH_STRENGTH",
    ),
    "DB.FIMP": ("ASSIGN_TYPE",),
    "DB.HHCT": ("ITEM.OPT_USE_CREEP_SHRINKAGE",),
    "DB.MVLD": ("PERMIT_LOAD.ECC",),
    "DB.POSL": ("CALC_OPT",),
    "DB.SBDO": ("AXIS_VECTOR", "REBAR_AXIS_TYPE", "STR_UCS", "MEMB_TYPE_CIVIL"),
    "DB.SLANOP": ("LANE_ID",),
    "DB.SPFC": ("OPT.LARGEBRIDEGE",),
    "DB.SSEIS": ("PARAMETERS", "ADDITIONAL_LOAD"),
    "DB.STBK": ("LCNAME",),
    "DB.SWIND": ("SCALE_FACTOR_X", "SCALE_FACTOR_Y", "PARAMETERS", "ADDITIONAL_LOAD"),
}
"""**反向缺口**（数据侧有、自省没有）：**一律不动**、只如实记录（12 个端点）。"""

EXPECTED_FAILED_UNVERIFIED = 23
"""`FAILED` 里 `availability: unverified` 的（**R85**：本 build `404`）。"""

EXPECTED_FAILED_UNAVAILABLE = 15
"""`FAILED` 里 `unavailable_on` 含 `gen-local` 的。"""

EXPECTED_FAILED_OTHER_PRODUCT = 7
"""`FAILED` 里 **CIVIL_DESIGNER 独有**的（`/info/db/<CODE>` 是 NX 系路由）。"""

EXPECTED_NEWLY_JUDGED_PARENTS = {
    "DB.GALD": ("SUBTYPE", "LOAD"),
    "DB.SECT": ("SECT_BEFORE.SECT_I.CF_STIFF_ULS",),
}
"""补字段后由「裸 `object` ⇒ **不判**」变成**可判**的父节点（判定在该处**变强**）。"""

EXPECTED_SCHEMA_FILES = 625
EXPECTED_TEMPLATES = 71
EXPECTED_BODIES = 115


def _load(path: Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tool() -> Any:
    """R117 工具。"""
    return _load(TOOL_PATH, "structai_sync_introspect_fields_p150")


def _check_tool() -> Any:
    """字段白名单工具（**唯一**判定点）。"""
    return _load(CHECK_TOOL_PATH, "structai_check_write_templates_p150")


def _evidence() -> dict[str, Any]:
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def _manifest() -> dict[str, dict[str, Any]]:
    document = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {str(entry["key"]): entry for entry in document["endpoints"]}


def _node_at(item: dict[str, Any], dotted: str) -> Any:
    """条目 Schema 里该字段路径的节点。"""
    node: Any = item
    for name in dotted.split("."):
        node = (node.get("properties") or {})[name]
    return node


def _unchanged_since_head(path: Path) -> bool:
    """该文件相对 `HEAD` **一字未改**（`git diff --quiet` 的退出码判定）。"""
    result = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", str(path)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


# ===== 1. 目标集（判定 1）=====


def test_p150_the_target_set_is_every_endpoint_with_a_registered_introspect_source() -> None:
    """门槛（判定 1）：目标集 = **244**，逐条可复算；工具**只发 `GET`**。"""
    tool = _tool()
    keys = tool.target_keys(REPO_ROOT)
    assert len(keys) == EXPECTED_TARGETS
    assert keys == sorted(keys)
    # 目标集**不**按可用性 / 产品过滤：本工具是**只读**的（`--probe` 零副作用）
    assert set(keys) == set(_evidence()["endpoints"])
    manifest = _manifest()
    import yaml  # noqa: PLC0415 - 仓库既有依赖

    for key in keys:
        definition = REPO_ROOT / "registry" / str(manifest[key]["definition"])
        document = yaml.safe_load(definition.read_text(encoding="utf-8"))
        assert str((document.get("schema_ref") or {}).get("introspect") or "") != "", key
    # 纪律：源码里**没有**写请求调用（只读来源）
    source = TOOL_PATH.read_text(encoding="utf-8")
    for verb in (".post(", ".put(", ".patch(", ".delete("):
        assert verb not in source, verb


# ===== 2. 证据（判定 2 / 3）=====


def test_p150_the_evidence_records_the_scan_honestly() -> None:
    """门槛（判定 2）：**244** 行；`verdict` = **199** `PASSED` + **45** `FAILED`；未中止。"""
    document = _evidence()
    assert document["criterion_version"] == CRITERION_VERSION
    assert document["instance"]["alias"] == INSTANCE_ALIAS
    assert document["instance"]["product"] == INSTANCE_PRODUCT
    assert document["instance"]["probed_at"] == PROBED_AT
    assert document["aborted"] == ""
    assert len(document["endpoints"]) == EXPECTED_TARGETS
    assert document["counts"] == {"PASSED": EXPECTED_PASSED, "FAILED": EXPECTED_FAILED}
    assert document["decisions"] == EXPECTED_DECISIONS
    assert document["instance"]["scope"].startswith("schema_ref.introspect")


def test_p150_the_forty_five_unavailable_introspect_routes_are_explained_per_bucket() -> None:
    """门槛（判定 3）：45 个 `404` = **23** `unverified`（R85）+ **15** `unavailable_on` +
    **7** CIVIL_DESIGNER 独有；且**未**写任何 `availability` / `unavailable_on`。
    """
    document = _evidence()
    manifest = _manifest()
    failed = {key: row for key, row in document["endpoints"].items() if row["verdict"] == "FAILED"}
    assert len(failed) == EXPECTED_FAILED
    unverified = 0
    unavailable = 0
    other = 0
    for key, row in failed.items():
        assert row["status_code"] == 404, key
        assert row["decision"] == "NOT_COMPARABLE", key
        assert row["basis"] == "not_available_on_instance", key
        entry = manifest[key]
        if str(entry["availability"]) == "unverified":
            unverified += 1
        elif INSTANCE_ALIAS in [str(name) for name in (entry.get("unavailable_on") or [])]:
            unavailable += 1
        else:
            other += 1
            # 未记 `unavailable_on` 的只有 CIVIL_DESIGNER 独有端点（NX 系路由不存在）
            assert [str(name) for name in entry["products"]] == ["CIVIL_DESIGNER"], key
    assert (unverified, unavailable, other) == (
        EXPECTED_FAILED_UNVERIFIED,
        EXPECTED_FAILED_UNAVAILABLE,
        EXPECTED_FAILED_OTHER_PRODUCT,
    )
    # ⚠️ 本证据**只**断言「自省路由在本 build 上 404」，**不**断言端点不可用 ⇒ 端点 YAML 一行未改
    for key in failed:
        definition = REPO_ROOT / "registry" / str(manifest[key]["definition"])
        assert _unchanged_since_head(definition), key


# ===== 3. 裁决（判定 4）=====


def test_p150_the_verdict_is_recomputed_per_endpoint() -> None:
    """门槛（判定 4）：`add_fields` **21** · `record_left_out` **3** · `no_gap` **175**。"""
    document = _evidence()
    added = tuple(
        sorted(key for key, row in document["endpoints"].items() if row["decision"] == "add_fields")
    )
    assert added == EXPECTED_ADD_ENDPOINTS
    left_out = {
        key: tuple(row["reasons"])
        for key, row in document["endpoints"].items()
        if row["decision"] == "record_left_out"
    }
    assert left_out == EXPECTED_LEFT_OUT
    for key, reasons in EXPECTED_LEFT_OUT.items():
        row = document["endpoints"][key]
        assert row["introspect_only"], key
        assert row["basis"] == reasons[0], key
    # 可补的端点**必须**有缺口；留缺 / 无缺口的端点**必须**没有阻断原因
    for key, row in document["endpoints"].items():
        if row["decision"] == "add_fields":
            assert row["introspect_only"], key
            assert row["reasons"] == [], key
            assert row["basis"] == "introspect_declared_and_schema_compatible", key
        elif row["decision"] == "no_gap":
            assert row["introspect_only"] == [], key
            assert row["reasons"] == [], key
            assert row["basis"] == "no_field_diff", key


def test_p150_the_three_left_out_endpoints_are_unchanged_and_the_gap_is_recorded() -> None:
    """门槛（判定 4 / 7）：留缺的 **3** 个端点**一行未改**，缺口**逐条**记在证据里。"""
    document = _evidence()
    manifest = _manifest()
    assert document["endpoints"]["DB.KFAC"]["introspect_only"] == ["Ky", "Kz", "Kt"]
    for key in ("DB.SSEIS", "DB.SWIND"):
        assert document["endpoints"][key]["introspect_only"] == ["INPUTS", "PROFILE"], key
    for key in EXPECTED_LEFT_OUT:
        relative = str(manifest[key]["schema"])
        assert _unchanged_since_head(REPO_ROOT / "registry" / relative), key


# ===== 4. 落盘与幂等（判定 5 / 6 / 8）=====


def test_p150_the_additions_are_on_disk_and_idempotent() -> None:
    """门槛（判定 5）：`--check` 退出码 **0**；21 个端点逐条已无待补字段；合计 **212** 条。"""
    tool = _tool()
    check_tool = _check_tool()
    assert tool.check(REPO_ROOT) == 0
    document = _evidence()
    total = 0
    for key in EXPECTED_ADD_ENDPOINTS:
        row = document["endpoints"][key]
        item = check_tool.request_schema(REPO_ROOT, str(row["schema"]), key)
        assert item is not None, key
        assert tool.plan_additions(row["introspect"], item) == [], key
        total += len(row["introspect_only"])
    assert total == EXPECTED_ADDED_FIELDS


def test_p150_the_reverse_gap_is_recorded_and_untouched() -> None:
    """门槛（判定 6）：**12** 个反向缺口端点的字段**仍全部在**（**不**删、**不**改名）。"""
    tool = _tool()
    check_tool = _check_tool()
    document = _evidence()
    recorded = {
        key: tuple(row["data_only"])
        for key, row in document["endpoints"].items()
        if row["data_only"]
    }
    assert recorded == EXPECTED_REVERSE_GAP
    for key, paths in EXPECTED_REVERSE_GAP.items():
        row = document["endpoints"][key]
        item = check_tool.request_schema(REPO_ROOT, str(row["schema"]), key)
        assert item is not None, key
        assert tuple(tool.data_only_paths(row["introspect"], item)) == paths, key


def test_p150_no_invalid_schema_fragment_was_imported() -> None:
    """门槛（判定 8）：**只**搬进合法片段；`registry/schema/**` 仍 **625** 个合法对象、
    **没有**任何 `multi object`；自省里那 **4** 处非法 `type` **如实**记在证据里。
    """
    tool = _tool()
    document = _evidence()
    # 逐条：补进去的每个字段，其**整棵子树**都必须合法
    for key in EXPECTED_ADD_ENDPOINTS:
        row = document["endpoints"][key]
        item = _check_tool().request_schema(REPO_ROOT, str(row["schema"]), key)
        assert item is not None, key
        for dotted in row["introspect_only"]:
            assert tool.invalid_schema_fragments(_node_at(item, dotted)) == [], (key, dotted)
    files = sorted((REPO_ROOT / "registry" / "schema").rglob("*.json"))
    assert len(files) == EXPECTED_SCHEMA_FILES
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "multi object" not in text, path
        assert isinstance(json.loads(text).get("schema"), dict), path
    # 自省里那 **4** 处非法 `type`（`DB.GALD.SUBTYPE` / `DB.GALD.LOAD` / `DB.SSEIS.INPUTS` /
    # `DB.SWIND.INPUTS`）**如实**记在证据里 —— `DB.SSEIS` / `DB.SWIND` 因此**留缺**（未搬）、
    # `DB.GALD` 的两处在**父节点**上（只补其**子字段**，父节点类型未动）
    for key in ("DB.GALD", "DB.SSEIS", "DB.SWIND"):
        node = document["endpoints"][key]["introspect"]
        assert tool.invalid_schema_fragments(node), key


# ===== 5. 判定未放宽（判定 9）=====


def test_p150_the_field_whitelist_check_stayed_non_vacuous_and_got_stronger() -> None:
    """门槛（判定 9）：`check_write_templates` 仍 **71 / 71** 非空判、**0** 未知字段；
    补字段让 **3** 个父节点由「裸 `object` ⇒ 不判」变成**可判**（判定在该处**变强**）。
    """
    check_tool = _check_tool()
    errors, notes, counts = check_tool.check(REPO_ROOT)
    assert errors == []
    assert counts["templates"] == EXPECTED_TEMPLATES
    assert counts["bodies"] == EXPECTED_BODIES
    assert counts["unverifiable"] == 0
    assert [note for note in notes if "不可判" in note] == []
    templates = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    manifest = _manifest()
    vacuous = []
    for key, template in sorted(templates.items()):
        bodies = [(key, template.get("body"))]
        for prerequisite in template.get("prerequisites") or []:
            bodies.append((str(prerequisite.get("key") or ""), prerequisite.get("body")))
        for owner, _body in bodies:
            relative = str(manifest[owner]["schema"])
            item = check_tool.request_schema(REPO_ROOT, relative, owner)
            assert item is not None, owner
            properties = item.get("properties")
            if not isinstance(properties, dict) or not properties:
                vacuous.append(owner)
    assert vacuous == [], "字段白名单检查**不得**退回空判"
    # 判定**变强**：新增字段让这些父节点现在**声明**了 properties（原来只有 `type: object`）
    for key, parents in EXPECTED_NEWLY_JUDGED_PARENTS.items():
        row = _evidence()["endpoints"][key]
        item = check_tool.request_schema(REPO_ROOT, str(row["schema"]), key)
        assert item is not None, key
        for dotted in parents:
            node = _node_at(item, dotted)
            assert isinstance(node.get("properties"), dict) and node["properties"], (key, dotted)


# ===== 6. 工具纪律（判定 10）=====


def test_p150_the_tool_chunks_health_checks_and_leaks_nothing() -> None:
    """门槛（判定 10）：分块 ≤ **20** + 块间只读健康检查；证据里**没有**凭据。"""
    tool = _tool()
    assert tool.CHUNK_SIZE == 20
    assert tool.HEALTH_PATH == "/DB/NODE"
    assert tool.CRITERION_VERSION == CRITERION_VERSION
    assert "chunk_size" in tool.probe.__code__.co_varnames
    document = _evidence()
    assert set(document) == {
        "note",
        "criterion_version",
        "instance",
        "counts",
        "decisions",
        "aborted",
        "endpoints",
    }
    allowed = {
        "uri",
        "schema",
        "products",
        "introspect",
        "introspect_only",
        "data_only",
        "decision",
        "reasons",
        "basis",
        "status_code",
        "verdict",
        "detail",
    }
    for key, row in document["endpoints"].items():
        assert set(row) <= allowed, key
    # 凭据**取值**绝不落盘：说明文字可以**提到** `MAPI-Key` 这个名字，但**不得**带值 ⇒
    # 逐条断言「证据里**没有**任何键名像凭据」（取值形态无法与 Schema 描述机械区分）
    forbidden = {
        "mapi-key",
        "mapi_key",
        "authorization",
        "bearer",
        "token",
        "password",
        "secret",
        "credential",
        "api_key",
        "apikey",
    }
    found: list[str] = []

    def _walk_keys(node: Any) -> None:
        if isinstance(node, dict):
            for name, value in node.items():
                if str(name).strip().lower() in forbidden:
                    found.append(str(name))
                _walk_keys(value)
        elif isinstance(node, list):
            for item in node:
                _walk_keys(item)

    _walk_keys(document)
    assert found == []
