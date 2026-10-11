"""P149-D —— **R107**：无 `DELETE` 的单例 / 设置表的**取设置表判据**（`registry/README.md` §8.14）。

GEN NX 上有 **14** 个端点**没有** `DELETE`（L5 三步链第 3 步走不通）：**11** 个 `GET`+`PUT` ·
**3** 个 `GET`+`POST`（`OPE.SECTPROP` / `OPE.STORY_IRR_PARAM` / `OPE.STORY_PARAM`）。
判据（**与三步链并列的第三条**；**单独成桶** `no_delete_singleton`，**不**并入 L5 覆盖率分子）：

1. **前置闸门（先做，只读）**：`GET <uri>` 必须返回**非空**原值；空 ⇒ **如实留缺**
   （`empty_singleton_put_creates_undeletable_record`，**绝不**发 `PUT`）；
2. **判据** = 「读回原值 → `PUT` **改动过**的值（手册示例）→ 读回确认**改动生效** →
   `PUT` **还原**原值（逐字段照抄跑前读回）→ 读回确认**逐字节**等于原值」。

本文件的**可执行判定**
----------------------
1. **目标集 14 逐条可复算**（GEN NX ∧ 有 `GET` ∧ 无 `DELETE` ∧ 有写方法 ∧ 非破坏性）。
2. **证据完整**：`PASSED` **2** · `FAILED` **7** · 留缺 **5**；`aborted == ""`。
3. **`PASSED` 逐字节还原**：`restore_byte_identical is True` 且
   `restored_sha256 == original_sha256`；全量 `restored == PASSED 数`（⇒ **零残留**）。
4. **`FAILED` 零副作用**：`put_sent is False`（空原值 ⇒ **没有**发 `PUT`）且原因 =
   `empty_singleton_put_creates_undeletable_record`。
5. **子桶口径单独报出**：`sub_bucket == "no_delete_singleton"`；**不**并入三步链。
6. **落盘一致**：`--check` 退出码 **0**；`PASSED` 的 `availability: verified` + `verified_on`
   含 `gen-local`。
7. **不泄密**：证据里没有凭据、没有读回 / 写回原文（只记 `sha256`）。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录。"""

TOOL_PATH = REPO_ROOT / "registry" / "tools" / "probe_singleton_tables.py"
"""本批的取设置表工具（只依赖标准库 + `httpx`）。"""

EVIDENCE_PATH = REPO_ROOT / "registry" / "live" / "singleton_table_probe.json"
"""取设置表判据的**实测证据**（不含凭据、不含读回原文）。"""

EXPECTED_TARGETS = 14
"""目标集（GEN NX ∧ 有 `GET` ∧ 无 `DELETE` ∧ 有写方法 ∧ 非破坏性）。"""

EXPECTED_COUNTS = {"PASSED": 2, "FAILED": 7}
"""两态计数（`PASSED` = 判据全成立且**已逐字节还原**）。"""

EXPECTED_PASSED = ("DB.STYP", "DB.UNIT")
"""判据成立的端点（`GET` 返回**非空**原值 ⇒ 可还原）。"""

EXPECTED_FAILED = (
    "DB.CLDR",
    "DB.CO_F",
    "DB.CO_M",
    "DB.CO_S",
    "DB.CO_T",
    "DB.MATD",
    "DESIGN.RC.KDS-41-20-2022.SRDF",
)
"""**空原值** ⇒ 前置闸门**拒绝**发 `PUT` 的端点（`PUT` 会创建**不可删**的记录）。"""

EXPECTED_GAPS = {
    "DB.CPSETTINGS": "no_manual_entry",
    "DB.PZEF": "empty_singleton_put_creates_undeletable_record",
    "OPE.SECTPROP": "no_put_method",
    "OPE.STORY_IRR_PARAM": "no_put_method",
    "OPE.STORY_PARAM": "no_put_method",
}
"""如实留缺：无手册示例 · 空原值（已实测）· 无 `PUT`（只有 `GET` + `POST`）。"""

SUB_BUCKET = "no_delete_singleton"
INSTANCE_ALIAS = "gen-local"
EMPTY_SINGLETON = "empty_singleton_put_creates_undeletable_record"


def _load(path: Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tool() -> Any:
    """取设置表工具（`probe_singleton_tables.py`）。"""
    return _load(TOOL_PATH, "structai_probe_singleton_p149d")


def _evidence() -> dict[str, Any]:
    """取设置表证据原文。"""
    return json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))


def test_p149d_the_no_delete_bucket_is_fourteen_by_measurement() -> None:
    """门槛（判定 1）：目标集 = **14**（GEN NX ∧ 有 `GET` ∧ 无 `DELETE` ∧ 有写方法）。"""
    tool = _tool()
    keys = tool.targets(REPO_ROOT, ())
    assert len(keys) == EXPECTED_TARGETS
    entries = tool.manifest_entries(REPO_ROOT)
    put_capable = 0
    post_only = 0
    for key in keys:
        entry = entries[key]
        assert "GEN_NX" in entry["products"], key
        methods = {part.strip().upper() for part in str(entry["methods"]).split(",")}
        assert "GET" in methods and "DELETE" not in methods, key
        assert (entry.get("wrapper") or {}).get("read_root"), key
        if "PUT" in methods:
            put_capable += 1
        else:
            post_only += 1
    assert (put_capable, post_only) == (11, 3)
    # 纯读端点（无写方法）**不**属本桶
    assert "OPE.PROJECTSTATUS" not in keys
    assert "VIEW.SELECT" not in keys


def test_p149d_the_evidence_records_the_two_state_counts_and_the_gaps() -> None:
    """门槛（判定 2）：`PASSED` **2** · `FAILED` **7** · 留缺 **5**；未中止。"""
    document = _evidence()
    assert document["counts"] == EXPECTED_COUNTS
    assert document["aborted"] == ""
    assert document["gaps"] == EXPECTED_GAPS

    def _verdict_keys(verdict: str) -> tuple[str, ...]:
        return tuple(
            sorted(key for key, row in document["endpoints"].items() if row["verdict"] == verdict)
        )

    assert _verdict_keys("PASSED") == tuple(sorted(EXPECTED_PASSED))
    assert _verdict_keys("FAILED") == tuple(sorted(EXPECTED_FAILED))


def test_p149d_every_passed_endpoint_was_restored_byte_identically() -> None:
    """门槛（判定 3）：`PASSED` 全部**逐字节**还原 ⇒ **零残留**。"""
    document = _evidence()
    assert document["restored"] == EXPECTED_COUNTS["PASSED"]
    for key in EXPECTED_PASSED:
        row = document["endpoints"][key]
        assert row["verdict"] == "PASSED", key
        assert row["put_sent"] is True, key
        assert row["change_effective"] is True, key
        assert row["restore_byte_identical"] is True, key
        assert row["restored_sha256"] == row["original_sha256"], key
        assert document["residue"]["final_reads"][key] == row["original_sha256"], key


def test_p149d_the_gate_refused_to_write_when_the_original_is_empty() -> None:
    """门槛（判定 4）：空原值 ⇒ `FAILED` ∧ **没有**发 `PUT`（零副作用）。"""
    document = _evidence()
    for key in EXPECTED_FAILED:
        row = document["endpoints"][key]
        assert row["verdict"] == "FAILED", key
        assert row["put_sent"] is False, key
        assert row["detail"] == EMPTY_SINGLETON, key
        assert "change_effective" not in row, key
        assert "restore_status" not in row, key


def test_p149d_the_sub_bucket_is_reported_separately() -> None:
    """门槛（判定 5）：结论**单独成桶**，**不**并入 L5 三步链（原口径照旧报出）。"""
    document = _evidence()
    assert document["sub_bucket"] == SUB_BUCKET
    assert all(row["sub_bucket"] == SUB_BUCKET for row in document["endpoints"].values())
    # 子桶**不**改 L5 覆盖率的口径：本桶端点**全部**无 `DELETE` ⇒ 本来就不在 `candidate_keys()` 里
    tool = _tool()
    entries = tool.manifest_entries(REPO_ROOT)
    for key in tool.targets(REPO_ROOT, ()):
        methods = {part.strip().upper() for part in str(entries[key]["methods"]).split(",")}
        assert "DELETE" not in methods, key


def test_p149d_the_data_side_matches_the_evidence() -> None:
    """门槛（判定 6）：`--check` 退出码 **0**；`PASSED` 已 `verified` + `verified_on` 含别名。"""
    tool = _tool()
    assert tool.check(REPO_ROOT) == 0
    files = tool.endpoint_files(REPO_ROOT)
    for key in EXPECTED_PASSED:
        availability, verified_on = tool.read_availability(files[key])
        assert availability == "verified", key
        assert INSTANCE_ALIAS in verified_on, (key, verified_on)


def test_p149d_the_evidence_carries_no_secret_and_no_raw_payload() -> None:
    """门槛（判定 7）：证据里没有凭据、没有读回 / 写回原文（只记 `sha256`）。"""
    text = EVIDENCE_PATH.read_text(encoding="utf-8")
    for forbidden in ("MAPI-Key", "MIDAS_MAPI_KEY", "midas-test.env", "FORCE", "OPT_OFFSET"):
        assert forbidden not in text, forbidden
    for key, row in _evidence()["endpoints"].items():
        assert set(row) <= {
            "uri",
            "read_root",
            "example_id",
            "changed_sha256",
            "sub_bucket",
            "original_sha256",
            "changed_status",
            "change_effective",
            "restore_status",
            "restored_sha256",
            "restore_byte_identical",
            "put_sent",
            "verdict",
            "detail",
        }, key
        assert len(row["original_sha256"]) == 64, key
        assert len(row["changed_sha256"]) == 64, key
