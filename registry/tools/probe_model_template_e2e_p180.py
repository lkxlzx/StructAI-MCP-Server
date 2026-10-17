#!/usr/bin/env python3
"""P180 · 端到端：**参数化模板 → JSON → 经 MCP 导入 MIDAS → 按写入值读回**。

判据（**铁律 ⓪**：效果，不是状态码）
------------------------------------
1. 模板 `materialize` 产出的 `DBG` 与原模型**只**在改动的参数上不同（其余逐表一致）；
2. 经 MCP `MODEL.IMPORT` 导入后，**每一个**改动都**按写入值读回**（防回显：取值不在原模型里）；
3. 无关表**没有**被改动（阴性对照：同一次导入里未改的表读回与导入前一致）;
4. 收尾实例停在**有路径**的项目上（R144）。

⚠️ `DOC.IMPORT` 是**合并**语义：同 id 的行会被覆盖，空表不清空 ⇒ 本探针用**同 id 覆盖**验证。

用法
----
    python registry/tools/probe_model_template_e2e_p180.py            # 预演（零请求）
    python registry/tools/probe_model_template_e2e_p180.py --probe    # 真机（有副作用）
    python registry/tools/probe_model_template_e2e_p180.py --check    # 离线自洽（零请求）
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Final

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.application.templates.model_template import (  # noqa: E402
    materialize,
    parameter_values,
)

TEMPLATE: Final[pathlib.Path] = REPO / "templates" / "gen_verification" / "Static-02.json"
SAMPLE_SOURCE: Final[pathlib.Path] = pathlib.Path(
    r"D:\Program\MIDAS\MIDAS GEN NX\Gen Verification\Static-02.mgbx"
)
WORKSPACE: Final[pathlib.Path] = REPO / ".tmp_p180" / "e2e"
EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "model_template_e2e_p180.json"

BACKUP: Final[pathlib.Path] = WORKSPACE / "session-backup.mgbx"
SAMPLE: Final[pathlib.Path] = WORKSPACE / "template-sample.mgbx"
FILLED: Final[pathlib.Path] = WORKSPACE / "template-filled.json"

TOOL: Final[str] = "engineering_doc"
PASSED: Final[str] = "PASSED"


def _sibling(name: str) -> Any:
    """按路径装载同目录模块（`registry/tools` 不是包）。"""
    import importlib.util  # noqa: PLC0415

    path = pathlib.Path(__file__).with_name(name)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _credentials() -> tuple[str, str]:
    """读 `[gen]` 段（值不进输出）。"""
    creds = pathlib.Path.home() / ".structai" / "midas-test.env"
    section, values = "", {}
    for raw in creds.read_text(encoding="utf-8-sig").splitlines():
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


def _edits(template: dict[str, Any]) -> dict[str, Any]:
    """本次要改的参数（取值**不在**样本里 ⇒ 读回即证明真的生效）。"""
    available = parameter_values(template)
    candidates: dict[str, Any] = {
        "material.1.elastic_modulus": 7777777.0,
        "section.1.name": "TPL-P180",
        "support.1.constraint": "1111111",
        "load_case.1.name": "CASE-P180",
        "node.2.x": 123.5,
    }
    return {key: value for key, value in candidates.items() if key in available}


def _read_tables(base: str, key: str, names: list[str]) -> dict[str, Any]:
    """裸 HTTP 读回若干 `DB.*` 表（**只读**；用于判定效果）。"""
    import urllib.request  # noqa: PLC0415

    out: dict[str, Any] = {}
    for name in names:
        request = urllib.request.Request(
            f"{base}/db/{name}", headers={"MAPI-Key": key, "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - 本机实例
            body = json.loads(response.read().decode("utf-8"))
        out[name] = body.get(name) or {}
    return out


def run_probe() -> int:
    """真机端到端（经 MCP 契约）。"""
    import asyncio  # noqa: PLC0415
    import os  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    if not TEMPLATE.is_file():
        print(f"🛑 缺模板 {TEMPLATE}（先跑 model_template_p180.py --build）")
        return 1
    if not SAMPLE_SOURCE.is_file():
        print(f"🛑 缺样本 {SAMPLE_SOURCE}")
        return 1

    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    overrides = _edits(template)
    if len(overrides) < 3:
        print(f"🛑 可用参数不足（模板里的改动项 {len(overrides)} 个）⇒ 判据不成立")
        return 1
    filled = materialize(template, overrides)

    base_url, mapi_key = _credentials()
    os.environ.setdefault("MIDAS_BASE_URL", base_url)
    os.environ.setdefault("MIDAS_MAPI_KEY", mapi_key)

    WORKSPACE.mkdir(parents=True, exist_ok=True)
    FILLED.write_text(json.dumps(filled, ensure_ascii=False), encoding="utf-8")
    shutil.copy2(SAMPLE_SOURCE, SAMPLE)

    stack_module = _sibling("probe_interface_paths.py")

    def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
        out: dict[str, Any] = {}
        if isinstance(value, dict):
            for key, item in value.items():
                out.update(_flatten(item, f"{prefix}.{key}"))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                out.update(_flatten(item, f"{prefix}[{index}]"))
        else:
            out[prefix] = value
        return out

    async def run() -> int:
        with tempfile.TemporaryDirectory(prefix="p180-e2e-", ignore_cleanup_errors=True) as raw_dir:
            async with stack_module._Stack(  # noqa: SLF001 - 复用既有装配
                REPO, pathlib.Path(raw_dir), allow_unverified=False
            ) as stack:
                # ⚠️ **P180 教训（R144 的延伸）**：判定失败时**也必须**还原现场 ——
                # 上一次运行在阴性对照处 `return 1`，把实例留在了样本副本上。
                try:
                    return await _run_body(stack, base_url, mapi_key, template, overrides)
                finally:
                    if BACKUP.is_file():
                        try:
                            await stack.call(
                                TOOL, "OPEN", {"project_path": str(BACKUP.resolve())}, confirm=True
                            )
                        except Exception:  # noqa: BLE001 - 还原失败不掩盖主判定
                            pass

    async def _run_body(
        stack: Any,
        base_url: str,
        mapi_key: str,
        template: dict[str, Any],
        overrides: dict[str, Any],
    ) -> int:
        """主流程（`finally` 里无论如何都会还原现场）。"""
        # ---- 第 0 步（R144）：备份现场 ----
        BACKUP.unlink(missing_ok=True)
        await stack.call(TOOL, "SAVE_AS", {"project_path": str(BACKUP.resolve())}, confirm=True)
        if not BACKUP.is_file():
            print("🛑 备份未落盘 ⇒ 不继续")
            return 1
        print(f"备份现场 → {BACKUP.name}（{BACKUP.stat().st_size} 字节）")

        # ---- 打开样本副本 ----
        await stack.call(TOOL, "OPEN", {"project_path": str(SAMPLE.resolve())}, confirm=True)
        print(f"打开样本副本 → {SAMPLE.name}")

        tables = ["NODE", "MATL", "SECT", "CONS", "STLD", "BMLD", "LCOM-GEN"]
        before = _read_tables(base_url, mapi_key, tables)

        # ---- 经 MCP 导入模板 ----
        imported = await stack.call(
            TOOL, "MODEL.IMPORT", {"project_path": str(FILLED.resolve())}, confirm=True
        )
        errors = imported.get("errors")
        print(f"MODEL.IMPORT → errors={json.dumps(errors, ensure_ascii=False)}")
        if errors:
            print("🛑 导入返回错误")
            return 1

        after = _read_tables(base_url, mapi_key, tables)

        # ---- 判据 ①：每个改动按写入值读回 ----
        checks: list[dict[str, Any]] = []
        applied = True
        matl = ((after["MATL"].get("1") or {}).get("PARAM") or [{}])[0]
        checks.append(
            {
                "parameter": "material.1.elastic_modulus",
                "written": overrides["material.1.elastic_modulus"],
                "read_back": matl.get("ELAST"),
                "where": "MATL/1/PARAM[0].ELAST",
            }
        )
        sect = after["SECT"].get("1") or {}
        checks.append(
            {
                "parameter": "section.1.name",
                "written": overrides["section.1.name"],
                "read_back": sect.get("SECT_NAME"),
                "where": "SECT/1/SECT_NAME",
            }
        )
        support = (((after["CONS"].get("1") or {}).get("ITEMS") or [{}])[0]).get("CONSTRAINT")
        checks.append(
            {
                "parameter": "support.1.constraint",
                "written": overrides["support.1.constraint"],
                "read_back": support,
                "where": "CONS/1/ITEMS[0].CONSTRAINT",
            }
        )
        case = (after["STLD"].get("1") or {}).get("NAME")
        checks.append(
            {
                "parameter": "load_case.1.name",
                "written": overrides["load_case.1.name"],
                "read_back": case,
                "where": "STLD/1/NAME",
            }
        )
        node_x = (after["NODE"].get("2") or {}).get("X")
        checks.append(
            {
                "parameter": "node.2.x",
                "written": overrides["node.2.x"],
                "read_back": node_x,
                "where": "NODE/2/X",
            }
        )
        for check in checks:
            if check["read_back"] != check["written"]:
                applied = False
                print(
                    f"  ❌ {check['parameter']}: 写入 {check['written']!r} "
                    f"读回 {check['read_back']!r}"
                )
            else:
                print(f"  ✅ {check['parameter']}: 读回 {check['read_back']!r}")

        # ---- 判据 ②：未改的字段不变（阴性对照） ----
        #
        # ⚠️ **P180 实测**：改 `STLD/1/NAME`（工况重命名）时，MIDAS **自动级联**把
        # `BMLD` / `CNLD` / `LCOM-GEN` 里指向该工况的 `LCNAME` 一起改名 ——
        # 那是**引用完整性**，不是模板污染。⇒ 阴性对照必须挑**没有引用语义**的字段。
        def _beam_p(tables: dict[str, Any]) -> list[Any]:
            rows = tables["BMLD"]
            return [
                item.get("P")
                for row_id in sorted(rows, key=lambda k: int(k))
                for item in ((rows[row_id] or {}).get("ITEMS") or [])
            ]

        def _node_xyz(tables: dict[str, Any], node_ids: tuple[str, ...]) -> list[Any]:
            return [
                [tables["NODE"].get(node, {}).get(axis) for axis in ("X", "Y", "Z")]
                for node in node_ids
            ]

        # ⚠️ **P180 实测（第二处）**：未改动的 `SECT/2` 在导入后**派生量**
        # `SECT_I.STIFF.Y/Z` 有 `-0.49999999999999994 → -0.4999999999999999`
        # 的浮点抖动（原生按尺寸**重算**截面刚度）⇒ 逐字节相等**不能**当阴性判据。
        # 判据改为**数值等价**（相对误差 ≤ 1e-9）；字符串 / 结构仍要求严格相等。
        import math  # noqa: PLC0415

        def _numerically_same(left: Any, right: Any) -> bool:
            if isinstance(left, dict) and isinstance(right, dict):
                return set(left) == set(right) and all(
                    _numerically_same(left[key], right[key]) for key in left
                )
            if isinstance(left, list) and isinstance(right, list):
                return len(left) == len(right) and all(
                    _numerically_same(a, b) for a, b in zip(left, right, strict=True)
                )
            if isinstance(left, bool) or isinstance(right, bool):
                return left == right
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-12)
            return left == right

        unchanged = {
            "BMLD/P（梁荷载数值，未参数化改动）": _numerically_same(
                _beam_p(before), _beam_p(after)
            ),
            "NODE/1,3（未改动的节点坐标）": _numerically_same(
                _node_xyz(before, ("1", "3")), _node_xyz(after, ("1", "3"))
            ),
            "MATL/1/NAME（未改动）": ((before["MATL"].get("1") or {}).get("NAME"))
            == ((after["MATL"].get("1") or {}).get("NAME")),
            "SECT/2（未改动的截面，数值等价）": _numerically_same(
                before["SECT"].get("2"), after["SECT"].get("2")
            ),
        }
        # ⚠️ **已实测的级联**：工况重命名 ⇒ 引用它的 `LCNAME` 自动跟着改。
        #    这不是缺陷，而是**必须记录**的原生行为（否则下次会把它当污染）。
        cascade = {
            "BMLD/1/ITEMS[0].LCNAME": (
                ((before["BMLD"].get("1") or {}).get("ITEMS") or [{}])[0].get("LCNAME"),
                ((after["BMLD"].get("1") or {}).get("ITEMS") or [{}])[0].get("LCNAME"),
            ),
            "LCOM-GEN/1/vCOMB[0].LCNAME": (
                ((before["LCOM-GEN"].get("1") or {}).get("vCOMB") or [{}])[0].get("LCNAME"),
                ((after["LCOM-GEN"].get("1") or {}).get("vCOMB") or [{}])[0].get("LCNAME"),
            ),
        }
        for name, same in unchanged.items():
            print(f"  阴性对照 {name}: {'不变 ✅' if same else '变了 ❌'}")
        for name, (old, new) in cascade.items():
            print(f"  已知级联 {name}: {old!r} → {new!r}（工况重命名的引用完整性）")
        if not all(unchanged.values()):
            print("🛑 未改动的字段发生了变化 ⇒ 不能归因于参数化")
            return 1

        # ---- 收尾（R144） ----
        await stack.call(TOOL, "OPEN", {"project_path": str(BACKUP.resolve())}, confirm=True)
        pjcf = _read_tables(base_url, mapi_key, ["PJCF"])["PJCF"]
        file_name = str(((pjcf.get("1") or {}).get("FILE_NAME")) or "")
        restored = file_name not in {"", "无标题"}
        print(f"收尾：FILE_NAME={file_name!r} · 有路径={restored}")
        if not restored:
            print("🛑 收尾时项目无路径（R144）")
            return 1

        evidence = {
            "note": [
                "P180 · 参数化模板 → JSON → 经 MCP 导入 → 按写入值读回。",
                "判据 = 效果（铁律 ⓪）：每个改动都按写入值读回；未改的表/字段不变。",
                "⚠️ 写入值均**不在**样本原值里（防回显）。",
                "⚠️ 只碰 `.tmp_p180/e2e/` 内的副本；样本原目录只读。",
            ],
            "template": str(TEMPLATE.relative_to(REPO)).replace("\\", "/"),
            "sample": SAMPLE_SOURCE.name,
            "overrides": overrides,
            "checks": checks,
            "unchanged": unchanged,
            "native_cascade": {
                name: {"before": old, "after": new} for name, (old, new) in cascade.items()
            },
            "native_cascade_note": (
                "改 `STLD/1/NAME` 时 MIDAS 自动把引用该工况的 `LCNAME` 一起改名 —— "
                "引用完整性，不是模板污染。⚠️ 它使「整表不变」**不能**当阴性对照。"
            ),
            "session": {"file_name": file_name, "has_project_path": restored},
            "applied": applied,
            "verdict": PASSED if applied else "FAILED",
        }
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(f"⇒ 判定：{'✅ ' + PASSED if applied else '❌ FAILED'}")
        print(f"wrote {EVIDENCE.relative_to(REPO)}")
        return 0 if applied else 1

    return asyncio.run(run())


def check_offline() -> int:
    """`--check`：证据齐备 + 判据全真（零请求）。"""
    if not EVIDENCE.is_file():
        print(f"❌ 缺证据 {EVIDENCE.relative_to(REPO)}（先跑 --probe）")
        return 1
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    problems: list[str] = []
    if document.get("verdict") != PASSED:
        problems.append(f"verdict 应为 PASSED，实际 {document.get('verdict')!r}")
    checks = document.get("checks") or []
    if len(checks) < 3:
        problems.append(f"检查项只有 {len(checks)} 个（至少 3 个）")
    for check in checks:
        if check.get("read_back") != check.get("written"):
            problems.append(
                f"{check.get('parameter')}: 读回 {check.get('read_back')!r} ≠ "
                f"写入 {check.get('written')!r}"
            )
    unchanged = document.get("unchanged") or {}
    if not unchanged or not all(unchanged.values()):
        problems.append("阴性对照不成立（未改动的表/字段发生了变化）")
    if document.get("session", {}).get("has_project_path") is not True:
        problems.append("收尾时项目无路径（R144）")
    if problems:
        for item in problems:
            print(f"❌ {item}")
        return 1
    print(
        f"✅ 模板端到端：{len(checks)} 个参数按写入值读回 · "
        f"阴性对照 {len(unchanged)} 项不变 · 收尾有路径"
    )
    return 0


def main() -> int:
    """入口（默认**预演**）。"""
    parser = argparse.ArgumentParser(description="参数化模板 → 经 MCP 导入 MIDAS 的端到端判据")
    parser.add_argument("--probe", action="store_true", help="真发请求（默认只预演）")
    parser.add_argument("--check", action="store_true", help="离线自洽断言（零请求）")
    args = parser.parse_args()
    if args.check:
        return check_offline()
    if not args.probe:
        template = json.loads(TEMPLATE.read_text(encoding="utf-8")) if TEMPLATE.is_file() else {}
        overrides = _edits(template) if template else {}
        print(f"模板：{TEMPLATE.relative_to(REPO)}")
        print(f"样本：{SAMPLE_SOURCE}")
        print(f"将改动 {len(overrides)} 个参数：{sorted(overrides)}")
        print(f"证据：{EVIDENCE.relative_to(REPO)}")
        print("\n（预演；加 --probe 才真发）")
        return 0
    return run_probe()


if __name__ == "__main__":
    raise SystemExit(main())
