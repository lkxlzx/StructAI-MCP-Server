"""P149-B2：**模板由工具拥有**（机械化补齐）+ **两轮真实 L5 批量（两次实例崩溃）**（可执行判定）。

权威来源
--------
- `docs/reports/P149-B2_写路径模板机械化与批量实测中断_v1.0.md`（本批报告）。
- `registry/tools/sync_write_templates.py`（生成器：`--write` / `--check`）。
- `registry/live/write_template_left_out.json`（**留缺账本**：账本里的 key **必须**没有模板）。
- `registry/live/write_batch_p149b2.json`（两轮**原始**实测证据：第一轮 **179** 条 +
  第二轮 **67** 条补测）。
- `registry/tools/check_write_templates.py`（P149-B2 修：`request_schema()` 支持
  `patternProperties`）。

本文件的**可执行判定**
--------------------
1. **复算一致**：`sync_write_templates.py --check` 退出码 0（已落盘 == 机械结果，逐字节）。
2. **池子**：本批落盘**前** = **205**；落盘后 `analyze()` 只剩「**仍**缺模板」的 **193**
   = 留缺账本 **180** + 无可用示例 **13**（那 12 个已验证的已有模板）。判据 = `enabled` ∧
   非 `destructive` ∧ 有写方法 ∧ 非 `delete_all_via_body` ∧ 本 build 路由存在 ∧
   有 `GET` + `read_root` + `DELETE` ∧ **无 Transformer** ∧ **无模板**。
3. **池子排除两类**：已有 Transformer 的端点（`DB.NODE`）· 无写方法的端点（3 个 `DESIGN.*.LCTB`）。
4. **留缺账本自洽**：**180** 条；账本里的 key **没有**模板；
   `落盘前池子 = 账本 ∪ 12 个已验证模板 ∪ 13 个无示例`；
   四类原因（R101–R105 / R109 / R110 / R111 / R113）齐全。
5. **12 个新候选**（两轮真实 `PASSED`）：模板**逐字节**等于上游手册示例条目
   （`manual_example`、零 `adjustments`、零前置链）。
6. **`patternProperties` 形状已可判**（P149-B2 修）；**「按端点代码键控」的根仍**不可判
   （**R112**，本测试**钉住**）。
7. **两次崩溃如实**：第一轮 179 条（3 `PASSED`；**67** 条 `request_timed_out` = 实例已死）；
   第二轮分块补测 67 条（**9** `PASSED` + **58** `FAILED`），`DB.NSPR` = **`transport_error`**
   ⇒ **R113**
   （该端点使实例崩溃、**永不再试**）；两次**跑后**哨兵读数均标记为**无效**（不声称零残留），
   第二轮**跑前**只读残留核对**全空**。
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
"""两轮原始实测证据。"""

TEMPLATES_PATH = REPO_ROOT / "registry" / "live" / "write_templates.json"
"""模板文件（两轮后 **69** 条）。"""

EXPECTED_POOL = 193
"""`analyze()` 当前返回的池子（**仍缺模板**）：**180** 条在留缺账本里 + **13** 条无可用示例。"""

EXPECTED_BATCH_POOL = 205
"""本批落盘**前**的池子：`EXPECTED_POOL` + 12 个已验证模板（`VERIFIED_KEYS`）。"""

EXPECTED_PICKS = 180
"""当前池子里**有可用示例**的端点数（= 留缺账本里那些：有示例但实测未通过）。"""

EXPECTED_GAPS: dict[str, int] = {
    "no_manual_entry": 11,
    "example_item_empty": 1,
    "example_shape_unusable": 1,
}
"""无可用示例的**如实**归类（合计 13）。"""

EXPECTED_LEDGER = 180
"""留缺账本条数（R101–R105 **11** · R109 **2** · R110 **117** · R111 **49** · R113 **1**）。"""

EXPECTED_TEMPLATES = 69
"""模板条数（P148 的 57 + 本批两轮共 12 条真实 L5 `PASSED`）。"""

VERIFIED_KEYS: tuple[str, ...] = (
    # 第一轮（3）
    "DB.BNGR",
    "DB.GRUP",
    "DB.NPLN",
    # 第二轮分块补测（9）
    "DB.PSLT",
    "DB.VSEC",
    "DB.WMAK",
    "DESIGN.RC.DRC",
    "DESIGN.RC.KDS-41-20-2022.DCO",
    "DESIGN.RC.KDS-41-20-2022.DCTL",
    "DESIGN.SRC.AIK-SRC2K.DCO",
    "DESIGN.STEEL.DSTL",
    "DESIGN.STEEL.KDS-41-30-2022.DCO",
)
"""本批在 GEN NX 空项目上真实跑通三步链的 **12** 个端点（两轮合计）。"""

CRASH_KEY = "DB.NSPR"
"""使 NX 实例崩溃的端点（**R113**）：两轮各触发一次「发生了无法确定的问题需要终止程序」。"""

CRASH_REASON = "R113_instance_crash_transport_error"
"""留缺原因：该端点使实例崩溃 ⇒ **永不再试**。"""

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


def test_p149b2_the_pool_is_193_with_13_gaps() -> None:
    """门槛：池子 193 = 可生成 180 + 无可用示例 13；落盘前 = 205。"""
    analysis = _sync_tool().analyze(REPO_ROOT)
    assert len(analysis.pool) == EXPECTED_POOL
    assert len(analysis.picks) == EXPECTED_PICKS
    assert len(analysis.pool) + len(VERIFIED_KEYS) == EXPECTED_BATCH_POOL
    reasons: dict[str, int] = {}
    for _key, reason in analysis.gaps:
        reasons[reason] = reasons.get(reason, 0) + 1
    assert reasons == EXPECTED_GAPS
    gap_keys = {key for key, _ in analysis.gaps}
    # 三个边界样本：条目为空对象 / 形状不可用 / 两个来源都没有该 URI
    assert {"DB.DRLS", "DB.NUCS", "DB.ULCT"} <= gap_keys


def test_p149b2_the_pool_excludes_transformer_owners_and_keys_without_a_write_method() -> None:
    """门槛：池子**不**含已有 Transformer 的端点，也**不**含无写方法的端点。"""
    tool = _sync_tool()
    analysis = tool.analyze(REPO_ROOT)
    pool = set(analysis.pool)
    registry = analysis.registry
    assert registry.write_template(TRANSFORMER_OWNER) is None
    assert tool.has_transformer(TRANSFORMER_OWNER) is True
    assert TRANSFORMER_OWNER not in pool
    for key in NO_WRITE_METHOD_KEYS:
        methods = set(registry.methods_for(key=key, product="GEN_NX"))
        assert methods == {"GET", "DELETE"}, key
        assert key not in pool


# ===== 3. 留缺账本自洽（判定 4）=====


def test_p149b2_the_ledger_is_self_consistent() -> None:
    """门槛：账本 180 条；账本里的 key **没有**模板；
    `落盘前池子 = 账本 ∪ 12 已验证 ∪ 13 无示例`。"""
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    templates = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    keys = set(ledger["keys"])
    assert len(keys) == EXPECTED_LEDGER
    assert keys & set(templates) == set()
    analysis = _sync_tool().analyze(REPO_ROOT)
    gaps = {key for key, _ in analysis.gaps}
    assert set(analysis.pool) == keys | gaps
    assert len(keys | gaps | set(VERIFIED_KEYS)) == EXPECTED_BATCH_POOL
    reasons = ledger["keys"]
    assert all(value for value in reasons.values())
    # R113：使实例崩溃的端点必须留在账本里（**永不再试**）
    assert reasons[CRASH_KEY] == CRASH_REASON
    # 第一轮「未取得结论」的临时原因**必须**已清空（67 条已全部补测完毕）
    assert not [value for value in reasons.values() if value.startswith("UNVERIFIED")]


def test_p149b2_the_verified_templates_are_verbatim_manual_examples() -> None:
    """门槛：12 条新模板**逐字节**等于手册示例条目，且在三步链里真实跑通。"""
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
    assert tool.unknown_fields({"TOTALLY_MADE_UP_FIELD": 1}, schema) == []


# ===== 5. 两次崩溃如实（判定 7）=====


def test_p149b2_the_evidence_records_both_rounds_and_the_crashes_honestly() -> None:
    """门槛：第一轮 179 条（3 `PASSED`）+ 第二轮 67 条补测（9 `PASSED`）；两次跑后读数**无效**。"""
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    first = evidence["outcomes"]
    assert len(first) == 179
    assert evidence["counts"]["PASSED"] == 3
    assert evidence["sentinels_after_invalid"] is True
    assert CRASH_KEY in str(evidence["crashed_at"])

    resume = evidence["resume"]
    assert len(resume["outcomes"]) == 67
    assert resume["chunks"] == 4
    assert resume["residue_before"]["dirty"] == []
    assert resume["residue_before"]["unreadable"] == []
    assert resume["residue_after_invalid"] is True
    assert resume["untested"] == []

    # 收尾：实例**第二次恢复后**的只读残留核对 —— **零残留**（122 个端点全空、0 不可读）
    final = evidence["residue_final"]
    assert final["checked"] == 122
    assert final["dirty"] == []
    assert final["unreadable"] == []
    assert final["clean"] is True

    # 两轮 `PASSED` 合起来**恰好**是模板里那 12 个
    passed = {row["key"] for row in first if row["outcome"] == "PASSED"}
    passed |= {row["key"] for row in resume["outcomes"] if row["outcome"] == "PASSED"}
    assert passed == set(VERIFIED_KEYS)
    # `DB.NSPR`：第二轮 `transport_error`（使实例崩溃）⇒ 留缺、**不**在候选集里
    crash = [row for row in resume["outcomes"] if row["key"] == CRASH_KEY]
    assert crash and crash[0]["detail"] == "transport_error", crash
    assert crash[0]["outcome"] == "FAILED"
