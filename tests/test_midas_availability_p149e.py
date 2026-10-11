"""P149-E —— 只读 L4 **补测收口**：把剩余可探的只读端点据实收口 + 据实更正「317」的记法。

背景（`docs/07` §15.5 的 P149-D 结果 ⑦）：P149-D 结束时账上仍写「其余 **317** 个 `availability !=
verified` 的只读端点可用 `sync_availability.py --probe` 只读扫」——**该记法偏松**：317 = 132
`untested` + 23 `unverified` + ... 而其中**只有 35 个**真的可探（`GET` + `read_root` + 已启用）：

| 构成 | 条数 | 能否只读收口 |
| --- | --- | --- |
| `availability != verified` ∧ 有 `GET` ∧ 有 `read_root` ∧ 已启用 | **35** | ✅ 可探 |
| 同上但**没有** `GET` | **119** | ❌ 只读探针**完全**覆盖不到 |
| 已禁用 | **1** | ❌ 客户端直接拒绝 |
| **合计** | **155** | — |

⚠️ 其中 **23** 个是 `unverified`（`-M1` 家族，R85：本 build `404`）—— **只升不降** ⇒ `--write`
**不**碰它们；本批**复测**只为**如实复核** R85 是否仍成立。

本文件的**可执行判定**
----------------------
1. **目标集 35 逐条可复算**（`probe_targets()`）；「119 无 `GET` + 1 禁用」的构成据实可复算。
2. **证据累积**：`live_read_probe.json` **84** 行 = **61** `PARTIAL` + **23** `FAILED`；未中止。
3. **12 个收口**：`availability: untested → verified` + `verified_on` 含 `gen-local`；
   且与 P149-C 的 49 个**不重叠**（累积**未**覆盖既有结论）。
4. **23 个复现 `404`**（R85 仍成立）：`FAILED` ∧ 非 `200` ∧ `top_keys == []`。
5. **只升不降**：这 23 个 YAML 相对 `HEAD` **一字未改**（`git diff --quiet` 判定）。
6. **落盘一致**：`--check` 退出码 **0**；全库 `verified` = **493**、`response` 块 = **317**。
7. **工具纪律**：分块 ≤ **20** + 块间只读健康检查 `GET /DB/NODE`（`CHUNK_SIZE` / `HEALTH_PATH`）；
   证据里**没有**凭据取值。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录。"""

TOOL_PATH = REPO_ROOT / "registry" / "tools" / "sync_availability.py"
"""只读收口工具（P149-E 起支持 `--chunk-size` + 块间只读健康检查 + **累积**）。"""

READ_EVIDENCE_PATH = REPO_ROOT / "registry" / "live" / "live_read_probe.json"
"""只读 L4 证据（P149-C **49** 行 + P149-E **35** 行 ⇒ **84** 行）。"""

WRITE_EVIDENCE_PATH = REPO_ROOT / "registry" / "live" / "write_batch_p149c.json"
"""P149-C 的写路径证据（其 `outcomes` 的 key = 那 **49** 个端点，**唯一**权威）。"""

MANIFEST_PATH = REPO_ROOT / "registry" / "manifest.json"
"""端点清单（YAML 的派生物）。"""

INSTANCE_ALIAS = "gen-local"
EXPECTED_TARGETS = 35
"""本批可探目标（`availability != verified ∧ GET ∧ read_root ∧ enabled`）。"""

EXPECTED_UPGRADED = (
    "DESIGN.RC.KDS-41-20-2022.CMFT",
    "DESIGN.RC.KDS-41-20-2022.DCREM",
    "DESIGN.RC.KDS-41-20-2022.EQCT",
    "DESIGN.RC.KDS-41-20-2022.MBTP",
    "DESIGN.RC.KDS-41-20-2022.MCMB",
    "DESIGN.RC.KDS-41-20-2022.MLLR",
    "DESIGN.RC.KDS-41-20-2022.MRFT",
    "DESIGN.RC.KDS-41-20-2022.REBB",
    "DESIGN.RC.KDS-41-20-2022.SDGN",
    "DESIGN.RC.KDS-41-20-2022.SUEQ",
    "DESIGN.RC.KDS-41-20-2022.TRFT",
    "DESIGN.STEEL.KDS-41-30-2022.SLRS",
)
"""本批收口的 **12** 个端点（`200` ∧ 块为空 ⇒ `PARTIAL` ⇒ `availability: untested → verified`）。"""

EXPECTED_REFUSED = 23
"""本批**复测**仍 `404` 的 `-M1` 家族（**R85** 仍成立；`unverified` ⇒ **只升不降** ⇒ 一行未动）。"""

EXPECTED_ROWS = 84
EXPECTED_PARTIAL = 61
EXPECTED_FAILED = 23
EXPECTED_VERIFIED_TOTAL = 493
EXPECTED_RESPONSE_BLOCKS = 317
NO_GET = 119
DISABLED = 1


def _load(path: Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tool() -> Any:
    """只读收口工具。"""
    return _load(TOOL_PATH, "structai_sync_availability_p149e")


def _read_evidence() -> dict[str, Any]:
    return json.loads(READ_EVIDENCE_PATH.read_text(encoding="utf-8"))


def _unchanged_since_head(path: Path) -> bool:
    """该文件相对 `HEAD` **一字未改**（`git diff --quiet` 的退出码判定）。"""
    result = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", str(path)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


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


def _p149c_keys() -> set[str]:
    """P149-C 那 **49** 个端点。"""
    document = json.loads(WRITE_EVIDENCE_PATH.read_text(encoding="utf-8"))
    return {str(row["key"]) for row in document["outcomes"]}


def test_p149e_the_probeable_target_set_is_thirty_five_by_measurement() -> None:
    """门槛（判定 1）：本批**探测了 35 个**（证据 84 − P149-C 的 49），
    收口后 `probe_targets()` 只剩 **23**（`unverified`）；「119 无 `GET` + 1 禁用」逐条可复算。
    """
    tool = _tool()
    document = _read_evidence()
    probed_this_batch = set(document["endpoints"]) - _p149c_keys()
    assert len(probed_this_batch) == EXPECTED_TARGETS
    # 收口后剩余目标 = 那 23 个 `unverified`（**只升不降** ⇒ 仍在目标集里）
    remaining = tool.probe_targets(REPO_ROOT, ())
    assert len(remaining) == EXPECTED_REFUSED
    assert set(remaining) == {
        key for key, row in document["endpoints"].items() if row["verdict"] == "FAILED"
    }
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["endpoints"]
    no_get = 0
    disabled = 0
    probeable = 0
    for item in manifest:
        methods = {part.strip().upper() for part in str(item.get("methods") or "").split(",")}
        state = tool.read_availability(REPO_ROOT / "registry" / str(item["definition"]))[0]
        if state == "verified":
            continue
        if "GET" not in methods:
            no_get += 1
        elif not str((item.get("wrapper") or {}).get("read_root") or ""):
            continue
        elif not bool(item.get("enabled", True)):
            disabled += 1
        else:
            probeable += 1
    assert no_get == NO_GET
    assert disabled == DISABLED
    # 收口后仍可探的 = 那 23 个 `unverified`（12 个已 `verified` ⇒ 不再出现在目标集里）
    assert probeable == EXPECTED_REFUSED


def test_p149e_the_evidence_is_cumulative_and_honest() -> None:
    """门槛（判定 2）：**84** 行 = **61** `PARTIAL` + **23** `FAILED`；未中止。"""
    document = _read_evidence()
    assert len(document["endpoints"]) == EXPECTED_ROWS
    assert document["counts"] == {"PARTIAL": EXPECTED_PARTIAL, "FAILED": EXPECTED_FAILED}
    assert document["aborted"] == ""
    assert document["instance"]["alias"] == INSTANCE_ALIAS
    assert document["instance"]["probed_at"] == "2026-10-11"
    # 累积**未**覆盖既有结论：P149-C 的 49 个仍在且仍 `PARTIAL`
    endpoints = document["endpoints"]
    p149c = _p149c_keys()
    assert len(p149c) == 49
    assert p149c <= set(endpoints)
    for key in sorted(p149c):
        assert endpoints[key]["verdict"] == "PARTIAL", key
        assert endpoints[key]["status_code"] == 200, key


def test_p149e_the_twelve_endpoints_were_upgraded_and_are_disjoint_from_p149c() -> None:
    """门槛（判定 3）：12 个收口；与 P149-C 的 49 个**不重叠**。"""
    document = _read_evidence()
    upgraded = {
        key
        for key, row in document["endpoints"].items()
        if row["verdict"] == "PARTIAL" and key not in _p149c_keys()
    }
    assert tuple(sorted(upgraded)) == tuple(sorted(EXPECTED_UPGRADED))
    tool = _tool()
    files = tool.endpoint_files(REPO_ROOT)
    for key in EXPECTED_UPGRADED:
        availability, verified_on = tool.read_availability(files[key])
        assert availability == "verified", key
        assert INSTANCE_ALIAS in verified_on, (key, verified_on)
        assert document["endpoints"][key]["top_keys"] == [key.split(".")[-1]], key


def test_p149e_the_twenty_three_unverified_endpoints_still_return_404() -> None:
    """门槛（判定 4 / 5）：**23** 个 `unverified` 复测仍 `404`（**R85** 仍成立）；
    `availability` / `unavailable_on` **一行未动**（**只升不降**）。
    """
    document = _read_evidence()
    refused = sorted(
        key for key, row in document["endpoints"].items() if row["verdict"] == "FAILED"
    )
    assert len(refused) == EXPECTED_REFUSED
    tool = _tool()
    files = tool.endpoint_files(REPO_ROOT)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["endpoints"]
    unverified = {
        str(item["key"])
        for item in manifest
        if tool.read_availability(REPO_ROOT / "registry" / str(item["definition"]))[0]
        == "unverified"
    }
    # 全库 `unverified` **恰好**就是这批（本批**不**新增、**不**减少）
    assert set(refused) == unverified
    for key in refused:
        row = document["endpoints"][key]
        assert row["status_code"] != 200, key
        assert row["top_keys"] == [], key
        assert row["detail"] != "", key
        availability, _ = tool.read_availability(files[key])
        # **只升不降**：实测不可用的判定需要另一方向的证据 ⇒ 本批**不**动
        assert availability == "unverified", key
        # **只升不降**：这 23 个 YAML 相对 `HEAD` **一字未改**（最强的「一行未动」判定）
        assert _unchanged_since_head(files[key]), key


def test_p149e_the_data_side_matches_the_evidence_and_the_counts_are_pinned() -> None:
    """门槛（判定 6）：`--check` 退出码 **0**；全库 `verified` = **493**、
    `response` 块 = **317**。"""
    tool = _tool()
    assert tool.check(REPO_ROOT) == 0
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["endpoints"]
    verified = sum(1 for item in manifest if str(item["availability"]) == "verified")
    assert verified == EXPECTED_VERIFIED_TOTAL
    blocks = 0
    for item in manifest:
        relative = str(item.get("schema") or "")
        path = REPO_ROOT / "registry" / relative
        if not relative or not path.is_file():
            continue
        if isinstance(json.loads(path.read_text(encoding="utf-8")).get("response"), dict):
            blocks += 1
    assert blocks == EXPECTED_RESPONSE_BLOCKS


def test_p149e_the_tool_chunks_and_health_checks_and_leaks_nothing() -> None:
    """门槛（判定 7）：分块 ≤ **20** + 块间只读健康检查；证据里**没有**凭据取值。"""
    tool = _tool()
    assert tool.CHUNK_SIZE == 20
    assert tool.HEALTH_PATH == "/DB/NODE"
    assert "chunk_size" in tool.probe.__code__.co_varnames
    assert tool.UPGRADABLE == ("PASSED", "PARTIAL")
    # 凭据**取值**绝不落盘（说明文字可以**提到** `MAPI-Key` 这个名字，但不得带值）
    assert _opaque_tokens(_read_evidence()) == []
    for key, row in _read_evidence()["endpoints"].items():
        assert set(row) <= {
            "uri",
            "read_root",
            "status_code",
            "top_keys",
            "verdict",
            "detail",
        }, key
        if key in _p149c_keys():
            continue  # P149-C 的行由更早的版本记录（无 `detail`），本批**不改写**既有结论
        assert row["detail"] == "" or row["status_code"] != 200, key
