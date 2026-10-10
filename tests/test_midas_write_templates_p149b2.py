"""P149-B2：**模板由工具拥有**（机械化补齐）与**批量实测中断**的如实记录（可执行判定）。

权威来源
--------
- `docs/reports/P149-B2_写路径模板机械化与批量实测中断_v1.0.md`（本批报告）。
- `registry/tools/sync_write_templates.py`（生成器：`--write` / `--check`，**只增不减**除留缺外）。
- `registry/live/write_template_left_out.json`（**留缺账本**：账本里的 key **必须**没有模板）。
- `registry/live/write_batch_p149b2.json`（本批 **179** 条原始实测证据，含实例崩溃事实）。
- `registry/tools/check_write_templates.py`（P149-B2 修：`request_schema()` 支持
  `patternProperties` 形状）。

本文件的**可执行判定**
--------------------
1. **复算一致**：`sync_write_templates.py --check` 退出码 0（已落盘 == 机械结果，逐字节）。
2. **池子**：本批落盘**前** = **205**（可生成 **192** + 无可用示例 **13**）；落盘后 `analyze()` 只剩
   「**仍**缺模板」的 **202** = 留缺账本 **189** + 无可用示例 **13**（那 3 个已验证的已有模板）。
   判据 = `enabled` ∧ 非 `destructive` ∧ 有写方法 ∧ 非 `delete_all_via_body` ∧ 本 build 路由存在 ∧
   有 `GET` + `read_root` + `DELETE` ∧ **无 Transformer** ∧ **无模板**。
3. **池子排除两类**：已有 Transformer 的端点（如 `DB.NODE`，靠 `derive_body()` 已是候选）·
   无写方法的端点（3 个 `DESIGN.*.LCTB` 只有 `GET` + `DELETE`）。
4. **留缺账本自洽**：**189** 条；账本里的 key **没有**模板；
   `落盘前池子 = 账本 ∪ 3 个已验证模板 ∪ 13 个无示例`。
5. **3 个新候选**（`DB.BNGR` / `DB.GRUP` / `DB.NPLN`）：模板**逐字节**等于上游手册示例条目
   （`manual_example`、零 `adjustments`、零前置链），且在 GEN NX 与 CIVIL NX 都是候选。
6. **`patternProperties` 形状已可判**（P149-B2 修）；**「按端点代码键控」的根仍**不可判 ——
   这是**既有限制**（R112），本测试**钉住**它，改工具时必须同步改本测试。
7. **崩溃如实**：证据文件 **179** 条；**3** `PASSED`；**67** 条 `request_timed_out` 属
   「实例崩溃后无人应答」⇒ 未取得结论，与账本里的 `UNVERIFIED_instance_crashed_pending_retest`
   **一一对应**；跑后哨兵读数标记为**无效**（不声称零残留）。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录。"""

SYNC_TOOL_PATH = REPO_ROOT / "registry" / "tools" / "sync_write_templates.py"
"""模板生成器（`--check` 断言已落盘 == 机械结果）。"""

CHECK_TOOL_PATH = REPO_ROOT / "registry" / "tools" / "check_write_templates.py"
"""模板复算工具（P149-B2 起支持 `patternProperties` 形状）。"""

LEDGER_PATH = REPO_ROOT / "registry" / "live" / "write_template_left_out.json"
"""留缺账本（账本里的 key 必须没有模板）。"""

EVIDENCE_PATH = REPO_ROOT / "registry" / "live" / "write_batch_p149b2.json"
"""本批原始实测证据（179 条）。"""

TEMPLATES_PATH = REPO_ROOT / "registry" / "live" / "write_templates.json"
"""模板文件（本批后 **60** 条）。"""

EXPECTED_POOL = 202
"""`analyze()` 当前返回的池子（**仍缺模板**）：**189** 条在留缺账本里 + **13** 条无可用示例。"""

EXPECTED_BATCH_POOL = 205
"""本批落盘**前**的池子：`EXPECTED_POOL` + 3 个已验证模板（`VERIFIED_KEYS`）。"""

EXPECTED_PICKS = 189
"""当前池子里**有可用示例**的端点数（= 留缺账本里那些：有示例但实测未通过 / 未取得结论）。"""

EXPECTED_GAPS: dict[str, int] = {
    "no_manual_entry": 11,
    "example_item_empty": 1,
    "example_shape_unusable": 1,
}
"""无可用示例的**如实**归类（合计 13）。"""

EXPECTED_LEDGER = 189
"""留缺账本条数（13 条既有 R101–R105/R109 + 本批 176 条实测结论）。"""

EXPECTED_TEMPLATES = 60
"""模板条数（P148 的 57 + 本批 3 个真实 L5 `PASSED`）。"""

VERIFIED_KEYS: tuple[str, ...] = ("DB.BNGR", "DB.GRUP", "DB.NPLN")
"""本批在 GEN NX 空项目上真实跑通三步链的端点（唯一进入模板的 3 条）。"""

UNVERIFIED_REASON = "UNVERIFIED_instance_crashed_pending_retest"
"""留缺原因：实测被**实例崩溃**中断，未取得结论。"""

TRANSFORMER_OWNER = "DB.NODE"
"""已有 Transformer 却**无**模板的端点（靠 `derive_body()` 已是候选，**不**在池子里）。"""

NO_WRITE_METHOD_KEYS: tuple[str, ...] = (
    "DESIGN.RC.KDS-41-20-2022.LCTB",
    "DESIGN.SRC.AIK-SRC2K.LCTB",
    "DESIGN.STEEL.KDS-41-30-2022.LCTB",
)
"""只有 `GET` + `DELETE`（**无**写方法）的端点 —— 结构性不进写路径，**不**在池子里。"""

PATTERN_PROPERTIES_SCHEMA = "schema/common/db/REBB.json"
"""`Assign.patternProperties['^[0-9]+$']` 形状（P149-B2 修后**可判**）。"""

CODE_KEYED_SCHEMA = "schema/common/db/NODE.json"
"""`{"NODE": {...}}` 形状（**按端点代码键控**；R112：仍不可判）。"""


def _load(path: Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sync_tool() -> Any:
    return _load(SYNC_TOOL_PATH, "structai_sync_write_templates_p149b2")


def _check_tool() -> Any:
    return _load(CHECK_TOOL_PATH, "structai_check_write_templates_p149b2")


# ===== 1. 复算一致（判定 1）=====


def test_p149b2_the_sync_tool_check_is_green() -> None:
    """门槛：`sync_write_templates.py --check` 退出码 0（已落盘 == 机械结果）。"""
    completed = subprocess.run(  # noqa: S603
        [sys.executable, str(SYNC_TOOL_PATH), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stdout[-800:]
    assert "✅" in completed.stdout


# ===== 2. 池子（判定 2 / 3）=====


def test_p149b2_the_pool_is_205_with_13_gaps() -> None:
    """门槛：池子 205 = 可生成 192 + 无可用示例 13，且无示例的原因逐条如实。"""
    analysis = _sync_tool().analyze(REPO_ROOT)
    assert len(analysis.pool) == EXPECTED_POOL
    assert len(analysis.picks) == EXPECTED_PICKS
    # 本批落盘**前**的池子 = 当前池子 + 3 个已验证模板（那 3 个已带模板，不再「缺模板」）
    assert len(analysis.pool) + len(VERIFIED_KEYS) == EXPECTED_BATCH_POOL
    reasons: dict[str, int] = {}
    for _key, reason in analysis.gaps:
        reasons[reason] = reasons.get(reason, 0) + 1
    assert reasons == EXPECTED_GAPS
    gap_keys = {key for key, _ in analysis.gaps}
    # 三个边界样本：条目为空对象 / 形状不可用 / 两个来源都没有该 URI
    assert "DB.DRLS" in gap_keys
    assert "DB.NUCS" in gap_keys
    assert "DB.ULCT" in gap_keys


def test_p149b2_the_pool_excludes_transformer_owners_and_keys_without_a_write_method() -> None:
    """门槛：池子**不**含已有 Transformer 的端点，也**不**含无写方法的端点。"""
    tool = _sync_tool()
    analysis = tool.analyze(REPO_ROOT)
    pool = set(analysis.pool)
    registry = analysis.registry
    # 已有 Transformer（`DB.NODE`）⇒ 靠 `derive_body()` 已是候选，不属欠账
    assert registry.write_template(TRANSFORMER_OWNER) is None
    assert tool.has_transformer(TRANSFORMER_OWNER) is True
    assert TRANSFORMER_OWNER not in pool
    # 无写方法（`LCTB` 家族：只有 GET + DELETE）⇒ 结构性不进写路径
    for key in NO_WRITE_METHOD_KEYS:
        methods = set(registry.methods_for(key=key, product="GEN_NX"))
        assert methods == {"GET", "DELETE"}, key
        assert key not in pool


# ===== 3. 留缺账本自洽（判定 4）=====


def test_p149b2_the_ledger_is_self_consistent() -> None:
    """门槛：账本 189 条；账本里的 key **没有**模板；`池子 = 账本 ∪ 3 已验证 ∪ 13 无示例`。"""
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    templates = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    keys = set(ledger["keys"])
    assert len(keys) == EXPECTED_LEDGER
    assert keys & set(templates) == set()
    analysis = _sync_tool().analyze(REPO_ROOT)
    gaps = {key for key, _ in analysis.gaps}
    assert set(analysis.pool) == keys | gaps
    # 账本 + 无示例 + 3 个已验证模板 = 本批落盘前的池子
    assert len(keys | gaps | set(VERIFIED_KEYS)) == EXPECTED_BATCH_POOL
    # 本批四类结论与「未取得结论」都在账本里，且原因**可复算**（逐条前缀）
    reasons = ledger["keys"]
    assert sum(1 for value in reasons.values() if value == UNVERIFIED_REASON) == 67
    assert all(value for value in reasons.values())


def test_p149b2_the_three_verified_templates_are_verbatim_manual_examples() -> None:
    """门槛：3 条新模板**逐字节**等于手册示例条目，且在三步链里真实跑通。"""
    templates = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    assert len(templates) == EXPECTED_TEMPLATES
    tool = _check_tool()
    examples = tool.manual_examples(REPO_ROOT)
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))["keys"]
    for key in VERIFIED_KEYS:
        assert key not in ledger, key
        entry = templates[key]
        assert entry["source"]["kind"] == "manual_example", key
        assert entry["adjustments"] == []
        assert entry["prerequisites"] == []
        item = tool.manual_item(
            examples,
            uri=str(entry["source"]["uri"]),
            example=str(entry["source"]["example"]),
            item_id=str(entry["source"]["example_id"]),
        )
        assert item == entry["body"], key
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    passed = {row["key"] for row in evidence["outcomes"] if row["outcome"] == "PASSED"}
    assert passed == set(VERIFIED_KEYS)


# ===== 4. 复算工具的两种 Schema 形状（判定 6）=====


def test_p149b2_the_pattern_properties_shape_is_judged() -> None:
    """门槛：`patternProperties` 形状剥到**条目** Schema（P149-B2 修 ⇒ 判定变强）。"""
    tool = _check_tool()
    schema = tool.request_schema(REPO_ROOT, PATTERN_PROPERTIES_SCHEMA)
    assert schema is not None
    assert "ITEMS" in (schema.get("properties") or {})


def test_p149b2_the_code_keyed_shape_is_still_unjudgeable() -> None:
    """门槛（R112）：`{"NODE": {...}}` 形状下 `request_schema()` **取不到**条目字段。

    ⚠️ 这是**既有限制**：该形状下字段白名单检查是**空判**（`unknown_fields()` 直接返回 `[]`）。
    本测试把现状**钉死**；若将来扩展 `request_schema()` 支持该形状，本测试**必须**同步改成
    「可判」并逐条复算 —— 不得静默改变判定强度。
    """
    tool = _check_tool()
    schema = tool.request_schema(REPO_ROOT, CODE_KEYED_SCHEMA)
    assert schema is not None
    assert not (schema.get("properties") or {})
    # 空判：任何 body 都判不出「未声明字段」
    assert tool.unknown_fields({"TOTALLY_MADE_UP_FIELD": 1}, schema) == []


# ===== 5. 崩溃如实（判定 7）=====


def test_p149b2_the_batch_evidence_records_the_crash_honestly() -> None:
    """门槛：证据 179 条 / 3 `PASSED` / 67 条未取得结论与账本**一一对应**；不声称零残留。"""
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    outcomes = evidence["outcomes"]
    assert len(outcomes) == 179
    assert evidence["counts"]["PASSED"] == 3
    timed_out = {row["key"] for row in outcomes if row["detail"] == "request_timed_out"}
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))["keys"]
    unverified = {key for key, reason in ledger.items() if reason == UNVERIFIED_REASON}
    assert timed_out == unverified
    assert len(unverified) == 67
    # 跑后哨兵读数**无效**（应用已终止）⇒ 证据文件不声称零残留
    assert evidence["sentinels_after_invalid"] is True
    assert "DB.NSPR" in str(evidence["crashed_at"])
    assert "不是" in str(evidence["sentinels_after_note"]) or "无效" in str(
        evidence["sentinels_after_note"]
    )
