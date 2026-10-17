#!/usr/bin/env python3
"""P180 · 参数化模板工具：`Gen Verification` 导出 → 模板库 → 按参数生成导入 JSON。

链路
----
    .tmp_p180/exports/<模型>.json          （DOC.EXPORT 的原生快照）
        --build-->  templates/gen_verification/<模型>.json   （模板：可填参数）
        --fill -->  <输出>.json                               （DBG，交给 MODEL.IMPORT）

用法
----
    python registry/tools/model_template_p180.py --build            # 建模板库 + index.json
    python registry/tools/model_template_p180.py --check            # 离线自洽（逐模板往返）
    python registry/tools/model_template_p180.py --show Static-02   # 列出可填参数
    python registry/tools/model_template_p180.py --fill Static-02 \
        --set material.1.elastic_modulus=210000000 \
        --set beam_load.1.0.p.0=-25.5 --out .tmp_p180/filled.json
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
    EXCLUDED_TABLES,
    TEMPLATE_FORMAT,
    TEMPLATE_VERSION,
    MaterializeError,
    build_template,
    dumps_template,
    materialize,
    parameter_values,
)

EXPORTS: Final[pathlib.Path] = REPO / ".tmp_p180" / "exports"
TEMPLATES: Final[pathlib.Path] = REPO / "templates" / "gen_verification"
INDEX: Final[pathlib.Path] = TEMPLATES / "index.json"


def _family_of(name: str) -> str:
    """样本名 → 族（`Buckling-01-1` → `Buckling`；`Cable 01` → `Cable`）。"""
    return name.split("-")[0].split(" ")[0]


def _load(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _skip_source(source: pathlib.Path) -> bool:
    """同目录的 `.bak` 等非导出文件不参与。"""
    return source.suffix != ".json"


def build_library() -> int:
    """从 `.tmp_p180/exports` 生成模板库与索引（幂等）。"""
    if not EXPORTS.is_dir():
        print(f"🛑 缺导出目录 {EXPORTS}（先跑 export_gen_verification_p180.py --probe）")
        return 1
    TEMPLATES.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for source in sorted(EXPORTS.glob("*.json")):
        if _skip_source(source):
            continue
        payload = _load(source)
        if not isinstance(payload, dict) or "DBG" not in payload:
            print(f"  跳过（不是 DBG 导出）：{source.name}")
            continue
        template = build_template(
            payload,
            name=source.stem,
            family=_family_of(source.stem),
            source=str(source.relative_to(REPO)).replace("\\", "/"),
        )
        target = TEMPLATES / f"{source.stem}.json"
        target.write_text(dumps_template(template), encoding="utf-8")
        entries.append(
            {
                "name": source.stem,
                "family": _family_of(source.stem),
                "file": target.name,
                "parameters": len(template["parameters"]),
                "tables": len(template["model"]),
                "key_parameters": _key_parameters(template),
            }
        )
        print(f"  {source.stem}: 参数 {len(template['parameters'])} · 表 {len(template['model'])}")

    families: dict[str, list[str]] = {}
    for entry in entries:
        families.setdefault(str(entry["family"]), []).append(str(entry["name"]))
    index = {
        "format": "structai.model_template_index",
        "version": 1,
        "template_format": TEMPLATE_FORMAT,
        "template_version": TEMPLATE_VERSION,
        "count": len(entries),
        "families": {name: sorted(names) for name, names in sorted(families.items())},
        "templates": entries,
    }
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"⇒ 模板 {len(entries)} 个 · 族 {len(families)} 个 · 索引 {INDEX.relative_to(REPO)}")
    return 0


def _key_parameters(template: dict[str, Any]) -> list[str]:
    """挑出最能代表模型形状的参数（给索引与 Agent 选模板用）。"""
    interesting = (
        "units.",
        "material.",
        "section.",
        "analysis.",
        "load_case.",
    )
    values = parameter_values(template)
    picked = [name for name in values if name.startswith(interesting)]
    return picked[:12]


def check_library() -> int:
    """逐模板：格式/版本 + **往返无损** + 序列化稳定。

    ⚠️ `.tmp_p180/exports` **不进仓库**（与 `templates/` 的取舍：模板是交付物，
    导出快照可由 `export_gen_verification_p180.py --probe` 重建）。⇒ 只有在导出快照
    **存在时**才做「materialize == 原导出」的逐表比对；否则退化为**结构性自洽**
    （表数 / 参数数 == 索引、materialize 可执行、序列化稳定），并在输出里**明说**。
    """
    if not INDEX.is_file():
        print(f"❌ 缺索引 {INDEX.relative_to(REPO)}（先跑 --build）")
        return 1
    index = _load(INDEX)
    problems: list[str] = []
    checked = 0
    lossless_checked = 0
    for entry in index.get("templates") or []:
        name = str(entry.get("name"))
        template_path = TEMPLATES / str(entry.get("file"))
        if not template_path.is_file():
            problems.append(f"{name}: 缺模板文件")
            continue
        template = _load(template_path)
        if template.get("format") != TEMPLATE_FORMAT or template.get("version") != TEMPLATE_VERSION:
            problems.append(f"{name}: 格式/版本不符")
            continue
        rebuilt = materialize(template)
        if len(rebuilt["DBG"]) != int(entry.get("tables") or -1):
            problems.append(f"{name}: materialize 表数与索引不符")
        if len(template.get("parameters") or {}) != int(entry.get("parameters") or -1):
            problems.append(f"{name}: 参数数与索引不符")

        source_path = EXPORTS / f"{name}.json"
        if source_path.is_file():
            original = _load(source_path)["DBG"]
            for table, rows in original.items():
                if table in EXCLUDED_TABLES:
                    continue
                if rebuilt["DBG"].get(table) != rows:
                    problems.append(f"{name}: 表 {table} 往返不一致")
                    break
            lossless_checked += 1
        # 稳定性：同一模板序列化两次逐字节相同
        if dumps_template(template) != dumps_template(_load(template_path)):
            problems.append(f"{name}: 序列化不稳定")
        checked += 1
    if problems:
        for item in problems[:20]:
            print(f"❌ {item}")
        print(f"（共 {len(problems)} 处）")
        return 1
    if lossless_checked == checked:
        print(f"✅ 模板 {checked} 个：格式/版本正确 · 往返无损 · 序列化稳定")
    else:
        print(
            f"✅ 模板 {checked} 个：格式/版本正确 · 序列化稳定"
            f"（往返逐表比对 {lossless_checked} 个；其余缺导出快照 ⇒ 未比对，"
            f"跑 export_gen_verification_p180.py --probe 可恢复）"
        )
    return 0


def _parse_value(raw: str) -> Any:
    """`--set` 的取值：先按 JSON 解析（数字 / 布尔 / 数组），失败则当字符串。"""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _load_template(name: str) -> dict[str, Any]:
    candidate = TEMPLATES / (name if name.endswith(".json") else f"{name}.json")
    if not candidate.is_file():
        raise SystemExit(f"🛑 模板不存在：{candidate}")
    return _load(candidate)


def show_parameters(name: str) -> int:
    """列出模板的可填参数。"""
    template = _load_template(name)
    values = parameter_values(template)
    print(f"模板 {template['meta'].get('name')} · 参数 {len(values)} 个")
    for key in sorted(values):
        entry = template["parameters"][key]
        unit = entry.get("unit")
        suffix = f" [{unit}]" if unit else ""
        print(f"  {key} = {values[key]!r}{suffix}")
        print(f"      {entry.get('description')}  ← {entry.get('source')}")
    return 0


def fill_template(name: str, assignments: list[str], output: pathlib.Path) -> int:
    """按 `--set` 生成导入用 DBG JSON。"""
    template = _load_template(name)
    defaults = parameter_values(template)
    overrides: dict[str, Any] = {}
    for assignment in assignments:
        if "=" not in assignment:
            raise SystemExit(f"🛑 --set 需要 NAME=VALUE 形式：{assignment!r}")
        key, raw = assignment.split("=", 1)
        key = key.strip()
        if key not in defaults:
            close = [item for item in defaults if key.lower() in item.lower()]
            hint = f"；相近参数：{close[:5]}" if close else ""
            raise SystemExit(f"🛑 未知参数 {key!r}{hint}")
        overrides[key] = _parse_value(raw.strip())
    payload = materialize(template, overrides)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    changed = {k: (defaults[k], v) for k, v in overrides.items() if defaults[k] != v}
    print(f"模板 {template['meta'].get('name')} → {output}")
    print(f"覆盖 {len(overrides)} 项，其中 {len(changed)} 项真的不同：")
    for key, (before, after) in sorted(changed.items()):
        print(f"  {key}: {before!r} → {after!r}")
    print(f"`DBG` 表 {len(payload['DBG'])} 张")
    return 0


def main() -> int:
    """入口。"""
    parser = argparse.ArgumentParser(description="Gen Verification 参数化模板工具")
    parser.add_argument("--build", action="store_true", help="从导出快照建模板库")
    parser.add_argument("--check", action="store_true", help="离线自洽（逐模板往返）")
    parser.add_argument("--show", metavar="TEMPLATE", help="列出模板参数")
    parser.add_argument("--fill", metavar="TEMPLATE", help="按参数生成导入 JSON")
    parser.add_argument("--set", action="append", default=[], metavar="NAME=VALUE", help="覆盖参数")
    parser.add_argument("--out", type=pathlib.Path, help="--fill 的输出路径")
    args = parser.parse_args()

    if args.build:
        return build_library()
    if args.check:
        return check_library()
    if args.show:
        return show_parameters(args.show)
    if args.fill:
        if args.out is None:
            raise SystemExit("🛑 --fill 需要 --out")
        return fill_template(args.fill, args.set, args.out)
    parser.print_help()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MaterializeError as error:
        print(f"🛑 {error}")
        raise SystemExit(2) from error
