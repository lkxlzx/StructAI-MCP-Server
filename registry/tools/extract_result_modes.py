"""P164-d：`VIEW.RESULTGRAPHIC` 的 `CURRENT_MODE` **取值表**（**离线**、零请求、零副作用）。

背景（R150 的成因更正）
----------------------
P160d 曾对 `POST /VIEW/RESULTGRAPHIC` 发 `{"CURRENT_MODE": "displacement", ...}` ⇒ 原生
**`400`** `{"error":{"message":"MIDAS GEN NX second query is wrong"}}`，当时把成因记为
「**未定**」（缺分析结果？取值不符？）。

本工具**离线**给出答案：`VIEW.RESULTGRAPHIC` 是**多变体端点** —— 手册里 **34** 篇文章
（`… - Result Display` / `… - Moving Tracer Display` / `… - Mode Shapes Display` /
`… - Heat of Hydration Display`）都映射到 `view/RESULTGRAPHIC`，**由 `CURRENT_MODE`
选变体**，共 **36** 个取值。而 `"displacement"` **不在**这 36 个里 ⇒
**那一次的 `400` 是「变体选择子取值非法」，不是「缺分析结果」。**

⚠️ 本工具**只做取证**：
* **不**发任何请求（不碰实例）；
* **不**改 `availability`、**不**改 Schema；
* 输出 = `registry/live/view_result_modes.json`（逐条可回溯到手册的文章 URL 与示例名）。
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, Final

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
"""仓库根目录（`registry/tools/` 的上两级）。"""

MANUAL: Final[pathlib.Path] = REPO / "MIDAS_API_Online_Manual_Gen_NX_v1.0.json"
"""手册（数据侧真源之一）。"""

EVIDENCE: Final[pathlib.Path] = REPO / "registry" / "live" / "view_result_modes.json"
"""证据落点。"""

ENDPOINT_SUFFIX: Final[str] = "resultgraphic"
"""按 `input_uri` 的**末段**匹配（手册里写作 `view/RESULTGRAPHIC`）。"""

REJECTED: Final[str] = "displacement"
"""P160d 实测被拒的那个取值（**不在**手册的取值表里）。"""


def load_entries(manual: pathlib.Path = MANUAL) -> list[dict[str, Any]]:
    """取手册里 `input_uri` 末段 = `resultgraphic` 的**全部**条目。"""
    document = json.loads(manual.read_text(encoding="utf-8"))
    return [
        entry
        for entry in document.get("endpoints") or []
        if str(entry.get("input_uri", "")).lower().endswith(ENDPOINT_SUFFIX)
    ]


def collect_modes(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """按示例体里的 `Argument.CURRENT_MODE` 归并取值表（**逐条**留出处）。"""
    modes: dict[str, dict[str, Any]] = {}
    examples = 0
    key_counts: dict[str, int] = {}
    families: dict[str, int] = {}
    for entry in entries:
        families[_family_of(entry)] = families.get(_family_of(entry), 0) + 1
        for example in entry.get("examples") or []:
            raw = example.get("json")
            if not isinstance(raw, str):
                continue
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(body, dict):
                continue
            argument = body.get("Argument")
            if not isinstance(argument, dict):
                continue
            examples += 1
            mode = argument.get("CURRENT_MODE")
            key = str(mode)
            slot = modes.setdefault(
                key,
                {
                    "current_mode": mode,
                    "count": 0,
                    "sibling_keys": sorted(k for k in argument if k != "CURRENT_MODE"),
                    "articles": [],
                    "examples_without_type_of_display": 0,
                },
            )
            slot["count"] += 1
            if "TYPE_OF_DISPLAY" not in argument:
                slot["examples_without_type_of_display"] += 1
            slot["articles"].append(
                {"title": entry.get("title"), "example": example.get("name"), "url": entry.get("url")}
            )
            for name in argument:
                if name != "CURRENT_MODE":
                    key_counts[name] = key_counts.get(name, 0) + 1
    return {
        "examples": examples,
        "modes": modes,
        "argument_keys": dict(sorted(key_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "families": dict(sorted(families.items(), key=lambda kv: (-kv[1], kv[0]))),
    }


FAMILY_SUFFIXES: Final[tuple[str, ...]] = (
    "- Result Display",
    "- Moving Tracer Display",
    "- Mode Shapes Display",
    "- Heat of Hydration Display",
)
"""手册里映射到本端点的**文章族**（按标题后缀归类；**只**用于描述，不作判据）。"""


def _family_of(entry: dict[str, Any]) -> str:
    """按标题后缀归类文章族（归类不上就记原标题）。"""
    title = str(entry.get("title") or "")
    for suffix in FAMILY_SUFFIXES:
        if title.endswith(suffix):
            return suffix
    return f"(other) {title}"


def build(manual: pathlib.Path = MANUAL) -> dict[str, Any]:
    """构造证据文档（**纯函数**，便于测试复算）。"""
    entries = load_entries(manual)
    collected = collect_modes(entries)
    modes = collected["modes"]
    return {
        "tool": "registry/tools/extract_result_modes.py",
        "endpoint": "VIEW.RESULTGRAPHIC",
        "uri": "VIEW/RESULTGRAPHIC",
        "source": {
            "manual": MANUAL.name,
            "input_uri_suffix": ENDPOINT_SUFFIX,
            "note": "逐条回溯到手册的文章标题 / 示例名 / URL；**不**臆造取值",
        },
        "articles": len(entries),
        "examples": collected["examples"],
        "mode_count": len(modes),
        "families": collected["families"],
        "argument_keys": collected["argument_keys"],
        "modes_without_type_of_display": sorted(
            key
            for key, slot in modes.items()
            if slot["examples_without_type_of_display"] == slot["count"]
        ),
        "modes_partially_without_type_of_display": sorted(
            key
            for key, slot in modes.items()
            if 0 < slot["examples_without_type_of_display"] < slot["count"]
        ),
        "modes": {key: modes[key] for key in sorted(modes)},
        "rejected": {
            "value": REJECTED,
            "in_manual_table": REJECTED in modes,
            "note": (
                "P160d 实测 `400` `MIDAS GEN NX second query is wrong` 时用的取值；"
                "**不在**手册的取值表里 ⇒ 那一次的成因 = **变体选择子取值非法**"
            ),
        },
    }


def main() -> int:
    """写证据（幂等）。"""
    document = build()
    EVIDENCE.write_text(
        json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"文章 {document['articles']} 篇 · 示例 {document['examples']} 条 · "
          f"`CURRENT_MODE` 取值 {document['mode_count']} 个")
    print(f"被拒取值 {REJECTED!r} 在表内？ {document['rejected']['in_manual_table']}")
    print(f"wrote {EVIDENCE.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
