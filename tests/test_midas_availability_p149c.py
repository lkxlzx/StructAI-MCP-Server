"""P149-C：**只读 L4 收口 `availability`（R111 的恢复条件）** + 解锁后的写路径实测（可执行判定）。

权威来源
--------
- `registry/tools/sync_availability.py`（`--probe` / `--write` / `--check`）。
- `registry/live/live_read_probe.json`（**只读** L4 证据：49 个端点逐条 `read_root` 证实）。
- `registry/live/write_batch_p149c.json`（解锁后的**分块**写路径实测：49 条，零残留、未崩溃）。
- `registry/README.md` §4 —— `availability: verified` 的语义 = 「**至少一个实例 GET 成功**」。

本文件的**可执行判定**
--------------------
1. **复算一致**：`sync_availability.py --check` 退出码 0。
2. **读映射逐条证实**：证据里 **49** 个端点全部 `200` 且**响应顶层键 == `read_root`**
   （`PASSED` / `PARTIAL`；空项目下 `PARTIAL` 是正常形态）。
3. **收口只升不降**：这 49 个 YAML 已是 `availability: verified` + `verified_on` 含 `gen-local`；
   全库 `availability == verified` 共 **296**（P149-B2 时 **247**，+49）。
4. **解锁后写路径实测（分块）**：**3** 块（20 / 20 / 9）；**2** `PASSED` · **47** `FAILED`
   （**全部** `400 software_api_error`）；跑前 / 跑后只读核对**均全空** ⇒ **零残留**。
5. **如实留缺**：47 条进留缺账本（`R110_native_400_software_api_error`）；
   2 个 `PASSED` 的模板**逐字节**等于上游手册示例条目（`manual_example`、零 `adjustments`、
   零前置链）。
6. **级联可复算**：这 49 个端点的 Schema 文件都带上了 `response` 块
   （由 `sync_response_schemas.py` 派生）。
7. **不泄密**：两个证据文件里**没有**任何凭据串。
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

TOOL_PATH = REPO_ROOT / "registry" / "tools" / "sync_availability.py"
"""`availability` 收口工具（`--probe` / `--write` / `--check`）。"""

READ_EVIDENCE_PATH = REPO_ROOT / "registry" / "live" / "live_read_probe.json"
"""只读 L4 证据。"""

WRITE_EVIDENCE_PATH = REPO_ROOT / "registry" / "live" / "write_batch_p149c.json"
"""解锁后的分块写路径实测证据。"""

LEDGER_PATH = REPO_ROOT / "registry" / "live" / "write_template_left_out.json"
"""留缺账本。"""

TEMPLATES_PATH = REPO_ROOT / "registry" / "live" / "write_templates.json"
"""模板文件。"""

MANIFEST_PATH = REPO_ROOT / "registry" / "manifest.json"
"""端点清单（YAML 的派生物）。"""

INSTANCE_ALIAS = "gen-local"
"""只读实测所在的实例别名（写进 `verified_on`）。"""

EXPECTED_PROBED = 49
"""本次只读 L4 实测的端点数。"""

EXPECTED_VERIFIED_TOTAL = 296
"""全库 `availability == verified` 的端点数（P149-B2 的 247 + 本批 49）。"""

EXPECTED_PASSED: tuple[str, ...] = (
    "DESIGN.RC.KDS-41-20-2022.WMAK",
    "DESIGN.SRC.AIK-SRC2K.DSRC",
)
"""解锁后在 GEN NX 空项目上真实跑通三步链的 **2** 个端点。"""

FAILURE_REASON = "R110_native_400_software_api_error"
"""47 条失败的留缺原因（`400 software_api_error`）。"""

RESPONSE_BLOCK_KEYS = EXPECTED_PROBED
"""需要 `response` 块的端点数（= 本次收口的 49 个）。"""


def _load(path: Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_evidence() -> dict[str, dict[str, Any]]:
    return json.loads(READ_EVIDENCE_PATH.read_text(encoding="utf-8"))["endpoints"]


# ===== 1. 复算一致（判定 1）=====


def test_p149c_the_availability_tool_check_is_green() -> None:
    """门槛：`sync_availability.py --check` 退出码 0（YAML == 只读证据）。"""
    completed = subprocess.run(  # noqa: S603
        [sys.executable, str(TOOL_PATH), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stdout[-800:]
    assert "✅" in completed.stdout


# ===== 2. 读映射逐条证实（判定 2）=====


def test_p149c_every_probed_endpoint_confirms_its_read_root() -> None:
    """门槛：49 个端点全部 200 且响应顶层键 == `read_root`（只读，零副作用）。"""
    document = json.loads(READ_EVIDENCE_PATH.read_text(encoding="utf-8"))
    endpoints = document["endpoints"]
    assert len(endpoints) == EXPECTED_PROBED
    assert document["counts"] == {"PARTIAL": EXPECTED_PROBED}
    manifest = {
        str(item["key"]): item
        for item in json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["endpoints"]
    }
    for key, row in endpoints.items():
        read_root = str((manifest[key].get("wrapper") or {}).get("read_root") or "")
        assert row["read_root"] == read_root, key
        assert row["status_code"] == 200, key
        assert read_root in row["top_keys"], key
        assert row["verdict"] in {"PASSED", "PARTIAL"}, key
        assert row["uri"] == manifest[key]["uri"], key


# ===== 3. 收口只升不降（判定 3）=====


def test_p149c_the_upgrade_is_verified_and_recorded_on_the_instance() -> None:
    """门槛：49 个 YAML 已 `verified` + `verified_on` 含 `gen-local`；全库 `verified` = 296。"""
    tool = _load(TOOL_PATH, "structai_sync_availability_p149c")
    files = tool.endpoint_files(REPO_ROOT)
    for key in _read_evidence():
        availability, verified_on = tool.read_availability(files[key])
        assert availability == "verified", key
        assert INSTANCE_ALIAS in verified_on, (key, verified_on)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["endpoints"]
    verified = [item for item in manifest if str(item["availability"]) == "verified"]
    assert len(verified) == EXPECTED_VERIFIED_TOTAL


# ===== 4. 解锁后的分块写路径实测（判定 4 / 5）=====


def test_p149c_the_chunked_write_probe_is_recorded_honestly() -> None:
    """门槛：3 块 / 2 `PASSED` / 47 条 `400` / 零残留（未崩溃）。"""
    document = json.loads(WRITE_EVIDENCE_PATH.read_text(encoding="utf-8"))
    outcomes = document["outcomes"]
    assert len(outcomes) == EXPECTED_PROBED
    assert document["chunks"] == 3
    assert document["residue_before"]["dirty"] == []
    assert document["residue_before"]["unreadable"] == []
    assert document["residue_after"]["dirty"] == []
    assert document["residue_after"]["unreadable"] == []
    assert document["clean"] is True
    assert document["untested"] == []
    passed = {row["key"] for row in outcomes if row["outcome"] == "PASSED"}
    assert passed == set(EXPECTED_PASSED)
    failed = [row for row in outcomes if row["outcome"] != "PASSED"]
    assert len(failed) == EXPECTED_PROBED - len(EXPECTED_PASSED)
    assert {str(row["detail"]) for row in failed} == {"software_api_error"}


def test_p149c_the_failures_are_ledgered_and_the_passes_are_verbatim_examples() -> None:
    """门槛：47 条进账本（R110）；2 条模板**逐字节**等于手册示例条目。"""
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))["keys"]
    outcomes = json.loads(WRITE_EVIDENCE_PATH.read_text(encoding="utf-8"))["outcomes"]
    for row in outcomes:
        key = str(row["key"])
        if row["outcome"] == "PASSED":
            assert key not in ledger, key
        else:
            assert ledger[key] == FAILURE_REASON, key
    templates = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    check_tool = _load(
        REPO_ROOT / "registry" / "tools" / "check_write_templates.py",
        "structai_check_write_templates_p149c",
    )
    examples = check_tool.manual_examples(REPO_ROOT)
    for key in EXPECTED_PASSED:
        entry = templates[key]
        assert entry["source"]["kind"] == "manual_example", key
        assert entry["adjustments"] == []
        assert entry["prerequisites"] == []
        item = check_tool.manual_item(
            examples,
            uri=str(entry["source"]["uri"]),
            example=str(entry["source"]["example"]),
            item_id=str(entry["source"]["example_id"]),
        )
        assert item == entry["body"], key


# ===== 5. 级联与保密（判定 6 / 7）=====


def test_p149c_the_response_block_cascade_is_complete() -> None:
    """门槛：这 49 个端点的 Schema 文件都带上了 `response` 块。

    该块由 `sync_response_schemas.py` 按「已实测」规则派生。
    """
    manifest = {
        str(item["key"]): item
        for item in json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["endpoints"]
    }
    with_block = 0
    for key in _read_evidence():
        schema = manifest[key].get("schema") or ""
        assert schema, key
        document = json.loads((REPO_ROOT / "registry" / schema).read_text(encoding="utf-8"))
        assert isinstance(document.get("response"), dict), key
        with_block += 1
    assert with_block == RESPONSE_BLOCK_KEYS


def _opaque_tokens(node: object) -> list[str]:
    """递归收集「像凭据取值」的串（长度 ≥ 16 且只含 `[A-Za-z0-9]`）。"""
    found: list[str] = []
    if isinstance(node, dict):
        for value in node.values():
            found.extend(_opaque_tokens(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_opaque_tokens(value))
    elif isinstance(node, str) and len(node) >= 16 and node.isalnum():
        found.append(node)
    return found


def test_p149c_the_evidence_files_carry_no_credential_values() -> None:
    """门槛：证据文件里**没有凭据取值**（说明文字可以**提到** `MAPI-Key` 这个名字，但不得带值）。"""
    for path in (READ_EVIDENCE_PATH, WRITE_EVIDENCE_PATH):
        document = json.loads(path.read_text(encoding="utf-8"))
        assert _opaque_tokens(document) == [], path.name
