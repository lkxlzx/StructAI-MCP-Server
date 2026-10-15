#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`spec_guard` 的枚举**来源普查**（P168 · `docs/07` §16.1 **R161**；**R160** 的同类复核）。

问题（**R151 / R155** 的共同成因）
---------------------------------
`spec_guard`（**R140**，为**防弹窗 / 防崩溃**而加）**只**能按 `registry/schema/**` 里
**已经写下的** `enum` / `oneOf[].const` 判定 ⇒ 枚举的**来源**决定了这道闸门的两个失效方向：

| 失效方向 | 形态 | 实例 |
| --- | --- | --- |
| **太窄**（**拦住合法调用**） | 枚举是从**一篇文章**的 `json_schema` 落下来的，而上游对同一字段还有别的取值 | **R151**：`POST.TABLE` 的 `TABLE_TYPE` 只有 **2** 个取值（P167 / **R160** 收口） |
| **缺枚举**（**非法取值抓不到**） | 请求 Schema **根本没声明**该字段的枚举，非法取值一路发到原生 | **R155**：`VIEW.RESULTGRAPHIC` 的 `CURRENT_MODE`（**36** 个变体，Schema 只声明了 `TYPE_OF_DISPLAY`） |

本工具把 `registry/schema/**` 的**每一个**枚举约束**逐条分类来源**，并给出三个**可执行**标志，
产出普查清单 `registry/live/spec_enum_audit.json`（**零请求**，只读数据文件）。

四个来源分类（**机械扫描，无人工取值**）
---------------------------------------
| 分类 | 判据 |
| --- | --- |
| **`manifest`**（**登记表**） | 取值 ⊆ `registry/manifest.json` 的**登记词汇**（端点 key 的每一段 · `table_type` · Schema 文件名 · `uri` 末段） |
| **`manual`**（**手册声明**） | 取值 ⊆ 上游手册**全部**条目 `json_schema` 里**同名字段**的 `enum` / `oneOf[].const` 并集，且声明该字段的文章数 **≥ 2** |
| **`single_article`**（**单篇文章**） | 同上，但声明该字段的文章数 **== 1** ⇒ ⚠️ **来源太窄**（**R151** 的形态） |
| **`untraceable`**（**无法追溯**） | 取值**既不**在登记表词汇里、**也不**在手册声明的并集里 |

⚠️ **口径**：这里的「手册声明」= 上游手册条目里**声明性**的取值表（`json_schema` 的
`enum` / `oneOf[].const`），**不**包含**示例体**里的取值 —— 这正是 **R151 的教训**
（「**不**按手册**示例体**硬凑」）。示例体 / 规格表 / 仓库内上游文档 / 自省证据只作**弱来源**
（`weak`），用来把 `untraceable` 再分成「弱可追溯」与「**真·无法追溯**」两档。

三个可执行标志
--------------
1. **`narrow`（来源太窄 ⇒ 会拦住**合法**调用）**：枚举 V **严格小于**「该端点**自身**的可复算词汇」
   U（`TABLE_TYPE` 取该端点**及后代端点**的 `table_type` / key 末段；其余字段取**同 URI** 的手册
   声明并集），且该端点**自己的 token 不在 V 里**（否则它拦不住自己的合法调用）。
   ⚠️ **大小写归一**后仍缺才算（**R160** §3 已实测原生对 `TABLE_TYPE` 大小写不敏感）。
2. **`missing_enum`（缺枚举 ⇒ 非法取值抓不到）**：同 URI 的**多篇文章**的示例体在该字段上给出
   **有限取值集合**（取值数 ≥ 2 且 **≥ 文章数的一半** ⇒ 该字段**切分**了变体），而该 URI 下的
   **任何** Schema 文件都**没有**为该字段声明枚举。自由文本 / 文件路径 / 布尔 / 纯数值按**机械规则**
   排除（见 `EXCLUSION_RULES`，逐条给判据）。
3. **`unexplained`（真·无法追溯）**：枚举的取值连**弱来源**里都找不到 ⇒ 必须逐条说明来历。

处置台账（**缺口不许静默**）
--------------------------
`DISPOSITIONS` 逐条登记标志项的处置：`left_open`（**如实留缺** + 写清「向谁问什么」）或
`closed`（已收口 + 生成器路径；`--check` 会**重新导入**该生成器并断言「已落盘 == 机械结果」，
⇒ **收口不可回退**）。`--check` 断言：**每一个**标志项都有处置，且**每一个** `closed` 项的生成器
仍然自洽。

用法
----
    python registry/tools/check_spec_enums.py            # 预演（只打印普查摘要）
    python registry/tools/check_spec_enums.py --write    # 写证据 JSON
    python registry/tools/check_spec_enums.py --check    # 断言「已落盘 == 机械结果」+ 台账覆盖完整

只依赖标准库（数据侧工具不引入新依赖）；**零请求**（不碰任何实例）。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import re
import sys
from typing import Any, Final, NamedTuple

MANIFEST_FILENAME: Final[str] = "manifest.json"
"""登记表（`registry/manifest.json`）。"""

MANUAL_FILENAMES: Final[tuple[str, ...]] = (
    "MIDAS_API_Online_Manual_Gen_NX_v1.0.json",
    "MIDAS_API_Online_Manual_数据_v1.0.json",
)
"""上游手册（**声明**来源：条目 `json_schema` 的 `enum` / `oneOf[].const`）。"""

WEAK_DOC_FILENAMES: Final[tuple[str, ...]] = (
    "MIDAS_API_开发文档_v1.0.md",
    "MIDAS_API_Online_Manual_完整API手册_v1.0.md",
    "MIDAS_API_Online_Manual_勘误与补全_v1.0.md",
    "MIDAS_API_DESIGN译名审查报告_v1.0.md",
    "MIDAS_API_手册覆盖对照_CivilDesigner_v1.0.md",
)
"""**弱来源**（仓库内上游文档）：只用于把 `untraceable` 再分档，**不**作为枚举的**声明**来源。"""

WEAK_EVIDENCE_RELATIVE: Final[str] = "live/introspect_field_diff.json"
"""**弱来源**（自省证据，`R117` 的落点）。"""

SCHEMA_DIRECTORY: Final[str] = "schema"
EVIDENCE_RELATIVE: Final[str] = "live/spec_enum_audit.json"
TOOLS_DIRECTORY: Final[str] = "registry/tools"

CLASS_MANIFEST: Final[str] = "manifest"
CLASS_MANUAL: Final[str] = "manual"
CLASS_SINGLE_ARTICLE: Final[str] = "single_article"
CLASS_UNTRACEABLE: Final[str] = "untraceable"
CLASS_ORDER: Final[tuple[str, ...]] = (
    CLASS_MANIFEST,
    CLASS_MANUAL,
    CLASS_SINGLE_ARTICLE,
    CLASS_UNTRACEABLE,
)

KIND_ENUM: Final[str] = "enum"
KIND_CONST: Final[str] = "oneOf.const"

SELECTOR_RATIO: Final[float] = 0.5
"""`missing_enum` 的判据之一：取值数 / 文章数 ≥ 本值 ⇒ 该字段**切分**了变体（变体选择子）。"""

DECLARED_SELECTOR_RATIO: Final[float] = 1.0
"""**声明选择子**判据（`narrow` 的适用范围）：声明该字段的文章数 ≥ 2 **且** 取值数 / 文章数 ≥ 本值
⇒ 平均每篇文章**至少贡献 1 个取值** ⇒ 该字段在**切分**文章（变体选择子）。

⚠️ **为什么需要它**：手册里**同名字段**的声明会**同名不同义** —— `FORMAT` 被 58 篇文章声明但
取值只有 5 个（`5 / 58 = 0.09` ⇒ 是**共享**的取值表，不是选择子）；`VALUE_TYPE` 同时出现在
`ISO_SURFACE.VALUE_MODE` 与 `APPLIED_LOADS` 两处（同一篇文章内**同名不同义**）。
⇒ 只有「切分文章」的字段才适用「并集来源」这条裁决。
"""

EXCLUSION_RULES: Final[dict[str, str]] = {
    "title_like": "取值全部是**某篇文章标题**的子串（大小写不敏感）⇒ 自由文本（表名 / 名称）",
    "name_like": "字段名含 `NAME`（`TABLE_NAME` / `LCNAME` / `LOAD_NAME` …）⇒ 名称类自由文本",
    "path_like": "取值全部含路径分隔符或文件扩展名 ⇒ 文件路径",
    "boolean_like": "取值全部 ∈ {true, false}（含大小写）⇒ 布尔字面量，不是选择子",
    "numeric_like": "取值全部可解析为数值 ⇒ 数值取值，不是选择子",
}
"""`missing_enum` 的**机械排除规则**（逐条给判据；命中即**不**算缺枚举）。"""

STRUCTURAL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "properties",
        "patternProperties",
        "items",
        "oneOf",
        "anyOf",
        "allOf",
        "additionalProperties",
        "$defs",
        "definitions",
    }
)
"""JSON Schema 的**结构键**（不是字段名）：下钻时**不**更新「当前字段名」。

⚠️ 否则 `.../properties/ITEM_TO_DISPLAY/items` 的枚举会被记成字段 `items`，与**别的**
数组字段的取值混成一张词汇表（P168 首轮跑出的假阳性来源之一）。
"""

CONDITIONAL_KEYS: Final[frozenset[str]] = frozenset({"if", "then", "else", "not"})
"""**条件分支键**：`allOf[i].if` 里的枚举是该字段的**收窄约束**（如 `GEO_NONL_TYPE` 的
`[0,1,2]` 之下再有 `if: [1,2]`），**不是**该字段的取值表 ⇒ **不**参与「来源太窄」的判定。

⚠️ 否则同一字段的**收窄分支**会被当成「比并集窄的枚举」（P168 第二轮跑出的假阳性来源）。
"""


class Disposition(NamedTuple):
    """标志项的处置（`closed` ⇒ 有生成器；`left_open` ⇒ 写清「向谁问什么」）。"""

    status: str
    ruling: str
    reason: str
    generator: str = ""
    ask: str = ""


_VARIANT_TABLE_TYPE: Final[Disposition] = Disposition(
    status="closed",
    ruling="R161",
    reason=(
        "**来源太窄**：本端点的**登记表 token**（`registry/manifest.json` 的 `table_type`）"
        "**不在**它自己的 `TABLE_TYPE.enum` 里 ⇒ 用**登记表的 token** 调用会被 `spec_guard` "
        "在**发请求之前**拦住（`STRUCTAI-1200`，**零请求**）。⚠️ 手册的**同一篇文章**的"
        "**示例体**用的**正是**登记表的 token ⇒ 两处独立证据一致。"
        "来源 = 登记表 token ∪ 已落盘枚举（**只增不减**）。"
    ),
    generator="registry/tools/sync_table_type_variant_enum.py",
)
"""变体端点的 `TABLE_TYPE` 收口（**同一处置**，逐条登记 key；见生成器）。"""

_PARTS_CLOSED: Final[Disposition] = Disposition(
    status="closed",
    ruling="R162",
    reason=(
        "**拦住手册自己的示例** / **来源太窄**：`PARTS`（输出部位）的枚举与手册**同一篇文章**的"
        "**示例体**互相矛盾（声明 `Part1`（数字 1），示例用 `PartI`（罗马数字 I））。"
        "**P169 真机裁决**（`registry/live/parts_disposition_probe.json`）："
        "`PartI` / `PartJ` / `Part1/4` / `Part2/4` / `Part3/4` ⇒ **有数据行且少于基线**（真的过滤）；"
        "`Part1` ⇒ **空块**（与**伪**取值 `PartZ` **同形**）⇒ 上游**声明是笔误**"
        "（同一份手册的**规格表**写 `Part I`，佐证）。来源 = 实测**有效**取值 ∪ 已落盘（**只增不减**）。"
    ),
    generator="registry/tools/sync_parts_enum.py",
)
"""`PARTS` 的「声明 vs 示例」冲突（**P169 真机裁决后收口**；见 `sync_parts_enum.py`）。"""

_PARTS_DECIDED_P170: Final[Disposition] = Disposition(
    status="closed",
    ruling="R163",
    reason=(
        "**P169 判为不可判别**（本模型无该表数据 ⇒ 基线就是空块），**P170 可判别化**："
        "建了一个**带相应结果**的自建模型（`registry/tools/build_parts_discriminator_p170.py`；"
        "**板网格 + 虚拟截面/虚拟梁**供 `RESULTANT_FORCES`；**钢结构设计**供 `DESIGN.STEEL.…TABLE`）"
        "⇒ 重跑 `registry/tools/probe_parts_disposition_p169.py --probe` "
        "（证据 = `registry/live/parts_disposition_probe_p170.json`）⇒ **6 / 6** 个端点**可判别**。"
        "⚠️ **P170 更正 P169 的「需要什么」**：`RESULTANT_FORCES` **不是**要**板 / 实体**单元，"
        "而是要**虚拟截面**（手册 `db/VSEC` + `db/VBEM`）—— 本批**两样都建**以一次消除疑点。"
        "实测：`PartI` / `PartJ` / `Part1/4` / `Part2/4` / `Part3/4` ⇒ **真的过滤**；"
        "`Part1` ⇒ **空块**（与伪取值 `PartZ` **同形**）⇒ 上游声明是**笔误**；"
        "⚠️ `DESIGN.STEEL.…TABLE` 的 `PARTS.default = ['All']` 实测**空块** ⇒ 声明可疑（**E-05**）。"
        "来源 = 实测**有效**取值 ∪ 已落盘（**只增不减**）。"
    ),
    generator="registry/tools/sync_parts_enum.py",
)
"""`PARTS` 冲突里 P169 **不可判别**、P170 **可判别化**的 3 个端点（**R163** 收口）。"""


DISPOSITIONS: Final[dict[str, Disposition]] = {
    "VIEW.RESULTGRAPHIC::CURRENT_MODE": Disposition(
        status="closed",
        ruling="R161",
        reason=(
            "**R155** 留缺：请求 Schema 的 `Argument` **只**声明 `TYPE_OF_DISPLAY` ⇒ 非法 "
            "`CURRENT_MODE` **抓不到**（一路发到原生，回 `400 second query is wrong`）。"
            "来源 = 手册里 `input_uri` 末段 = `resultgraphic` 的**全部变体文章**（34 篇 / 56 条示例）"
            "的 `Argument.CURRENT_MODE` 并集（**36** 个取值，逐条可回溯到文章 URL / 示例名）"
            "—— **不**是「一篇文章」的 `json_schema`（**R151** 的形态）。"
        ),
        generator="registry/tools/sync_result_graphic_modes.py",
    ),
    # ---- 变体端点：登记表的 token **不在**自己的 `TABLE_TYPE.enum` 里（**R151** 的形态）----
    "POST.TABLE.FIBR_ELASTREMAIN::TABLE_TYPE": _VARIANT_TABLE_TYPE,
    "POST.TABLE.FIBR_EVENTSTEP::TABLE_TYPE": _VARIANT_TABLE_TYPE,
    "POST.TABLE.FIBR_MAXCONTRACT::TABLE_TYPE": _VARIANT_TABLE_TYPE,
    "POST.TABLE.FIBR_MEANCOMPCONTRACT::TABLE_TYPE": _VARIANT_TABLE_TYPE,
    "POST.TABLE.FIBR_YILEDSTRENGTH::TABLE_TYPE": _VARIANT_TABLE_TYPE,
    "POST.TABLE.REACTIONLSURFACESPRING::TABLE_TYPE": _VARIANT_TABLE_TYPE,
    # ---- 如实留缺（**不**按手册示例体硬凑 —— R151 的教训）----
    "POST.TEXT::TABLE_TYPE": Disposition(
        status="closed",
        ruling="R162",
        reason=(
            "**来源太窄** + **请求键错误**（本端点是 `post/text` 这个 URI 的**唯一** Schema 文件）："
            "枚举只有 **3** 个取值（来自**一篇文章**），而同一 URI 的 **12** 篇文章在 `json_schema` 里"
            "声明了 **29** 个 ⇒ 收口来源可复算。⚠️ **P169 真机裁决**（用户已授权）另外裁定："
            "契约键是 **`TEXT_TYPE`**（手册**示例体** 29/29 都用它；合法值原生 `200` 并**真的产出文件**、"
            "伪值 ⇒ `400 second query is wrong`），而 `TABLE_TYPE` **任何**取值都回 `400 Wrong Field`"
            "（**键**错）⇒ 上游 `json_schema` 与**我们的旧 Schema** 都是**笔误**，已登记勘误。"
            "⇒ 收口 = **键重命名**（`TABLE_TYPE` → `TEXT_TYPE`）+ 枚举并集（**只增不减**）。"
        ),
        generator="registry/tools/sync_post_text_enum.py",
    ),
    "POST.TEXT::TEXT_TYPE": Disposition(
        status="closed",
        ruling="R162",
        reason=(
            "**缺枚举候选**（示例体用 `TEXT_TYPE`，29 个取值）—— **P169 真机裁决**已裁定"
            "`TEXT_TYPE` 就是**契约键**（见 `POST.TEXT::TABLE_TYPE`）⇒ 枚举挂在它下面，"
            "来源 = 手册声明并集 ∪ 已落盘（**只增不减**）。"
        ),
        generator="registry/tools/sync_post_text_enum.py",
    ),
    "OPE.LINEBMLD::TYPE": Disposition(
        status="left_open",
        ruling="R161",
        reason=(
            "**缺枚举候选**（`TYPE` 在示例体里有 **11** 个取值：`CONLOAD` / `UNILOAD` / `CURVED` …）。"
            "⚠️ `OPE.LINEBMLD` **不在任何 OperationPlan 的生产路径上**（`operations.py` 里 0 处），"
            "且示例体的取值集合混了**编号**（`'0'` / `'1'`）与**枚举名** ⇒ 口径不清。"
        ),
        ask="向数据侧问：`OPE.LINEBMLD` 的 `TYPE` 到底是「荷载类型枚举」还是「类型编号」？（需一次手册/产品侧澄清，**不**由示例体推断。）",
    ),
    "OPE.GSBG::BRDG_GROUP": Disposition(
        status="left_open",
        ruling="R161",
        reason=(
            "**缺枚举候选**（`BRDG_GROUP` = `BG_LEFT` / `BG_RIGHT`，**2** 个取值 / 2 篇文章）。"
            "⚠️ `OPE.GSBG` **不在任何 OperationPlan 的生产路径上**（0 处）。"
        ),
        ask="向数据侧问：`BRDG_GROUP` 是否是**受控词表**（若是，补 `enum`；若否，写清它是自由引用名）。",
    ),
    "OPE.LCOM-GEN::DGNCODE": Disposition(
        status="left_open",
        ruling="R162",
        reason=(
            "**缺枚举候选**（`DGNCODE` = `AIK-SRC2K` / `KDS 41 20 : 2022`）。"
            "**P169 真机裁决**判定为**不可判别**：本 build 对 `POST /OPE/LCOM-GEN` 的"
            "**任何**取值都回 `400 Wrong Field`（**形状 / 键错**，与取值**无关**）—— "
            "**连手册声明的合法值**也一样 ⇒ 无法区分「取值无效」与「本 build 不支持该形状」。"
            "⚠️ 该端点**不在任何 OperationPlan 的生产路径上**（`operations.py` 里 0 处）。"
        ),
        ask=(
            "需要**产品侧**澄清两件事：① 本 build 的 `POST /OPE/LCOM-GEN` 请求**形状**"
            "（手册示例体是**扁平**的 `Argument.OPTION/DGNCODE`，我们的 Schema 是 `oneOf` 三分支）；"
            "② `DGNCODE` 的取值表是否按「规范 × 产品」收口（本批**未**动它的枚举）。"
            "恢复条件：产品侧给出形状或一个**可写**的 `OPE.LCOM-GEN` 调用样例 ⇒ 重跑 "
            "`python registry/tools/probe_lcom_dgncode_p169.py --probe`。"
        ),
    ),
    "OPE.LCOM-SRC::DGNCODE": Disposition(
        status="closed",
        ruling="R162",
        reason=(
            "**拦住手册自己的示例**：`OPE.LCOM-SRC` 的文章示例用 `DGNCODE='AIK-SRC2K'`，"
            "而枚举只有 `['KDS 41 SRC : 2022']`（**同一 URI 的另一篇**文章的 `json_schema` 声明）。"
            "**P169 真机裁决**（**用户已授权**一次**写路径**测量，证据 = "
            "`registry/live/lcom_dgncode_probe.json`）：`POST /OPE/LCOM-SRC` 的答复分**三档** —— "
            "`KDS 41 SRC : 2022`（**声明**的合法值）与 `AIK-SRC2K`（**示例体**的值）"
            "**同档**（业务级 `Set_DefaultLoadComb failed` = 取值**通过**了规范校验、走到**下游**），"
            "而**伪**码 `NONSENSE-CODE` ⇒ `Unknown Error`（**取值非法**）⇒ `AIK-SRC2K` **合法**。"
            "来源 = 已落盘 ∪ 实测**合法**（**只增不减**）。"
        ),
        generator="registry/tools/sync_lcom_src_dgncode_enum.py",
    ),
    # ---- `PARTS`：**P169 真机裁决** ⇒ **可判别**的 3 个收口、**不可判别**的 3 个如实留缺 ----
    "POST.TABLE.BEAMFORCE::PARTS": _PARTS_CLOSED,
    "POST.TABLE.BEAMFORCEVBM::PARTS": _PARTS_CLOSED,
    "POST.TABLE.THISBEAMFORCE::PARTS": _PARTS_CLOSED,
    "POST.TABLE.RESULTANT_FORCES::PARTS": _PARTS_DECIDED_P170,
    "POST.TABLE.RESULTANT_FORCESVBM::PARTS": _PARTS_DECIDED_P170,
    "DESIGN.STEEL.KDS-41-30-2022.TABLE::PARTS": _PARTS_DECIDED_P170,
}
"""标志项 → 处置。⚠️ `--check` 断言**每一个**标志项都在此表里（缺口**不许静默**）。"""


# ===== 上游来源（全部**机械扫描**）=====


def _load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_entries(repo: pathlib.Path) -> list[dict[str, Any]]:
    """登记表的端点条目（`registry/manifest.json` 的 `endpoints`）。"""
    document = _load_json(repo / "registry" / MANIFEST_FILENAME)
    return list(document["endpoints"])


def manifest_vocabulary(entries: list[dict[str, Any]]) -> set[str]:
    """**登记表词汇**：端点 key 的每一段 · `table_type` · Schema 文件名 · `uri` 末段。"""
    vocabulary: set[str] = set()
    for entry in entries:
        key = str(entry.get("key") or "")
        vocabulary.update(part for part in key.split(".") if part)
        vocabulary.add(str(entry.get("table_type") or ""))
        schema = str(entry.get("schema") or "")
        if schema:
            vocabulary.add(pathlib.PurePosixPath(schema).stem)
        vocabulary.add(str(entry.get("uri") or "").rsplit("/", 1)[-1])
    vocabulary.discard("")
    return vocabulary


def endpoint_tokens(entries: list[dict[str, Any]]) -> dict[str, str]:
    """端点 key → **登记表里声明的 token**（`table_type`；为空 ⇒ 空串，**不**用 key 末段臆造）。"""
    return {str(entry.get("key") or ""): str(entry.get("table_type") or "") for entry in entries}


def endpoint_family_tokens(entries: list[dict[str, Any]]) -> dict[str, set[str]]:
    """端点 key → **它及后代端点**在登记表里声明的 token 集合（`POST.TABLE` ⇒ 194 个）。

    ⚠️ **只取 `table_type` 非空**的端点：登记表里 `table_type` 为空说明该端点的
    `TABLE_TYPE` **不是**它的 token（例如 `DESIGN.RC.KDS-41-20-2022.BC-TABLE` 的
    `TABLE_TYPE` 取值是 `MEMB` / `PROP`，与端点名无关）⇒ 用 key 末段臆造 token 会造假阳性。
    """
    family: dict[str, set[str]] = {}
    for entry in entries:
        token = str(entry.get("table_type") or "")
        if not token:
            continue
        parts = str(entry.get("key") or "").split(".")
        for index in range(1, len(parts) + 1):
            family.setdefault(".".join(parts[:index]), set()).add(token)
    return family


def _norm_uri(value: Any) -> str:
    """URI 归一（去空白 / 去首尾 `/` / 小写）—— 手册里 `DB/SWIND` 与 `/ope/lcom-src` 并存。"""
    return str(value or "").strip().strip("/").lower()


def wrapper_of(schema: Any) -> str:
    """Schema 的**包装根键**（只有一个非结构根键时取它；否则空串）。"""
    if not isinstance(schema, dict):
        return ""
    keys = [key for key in schema if key not in STRUCTURAL_KEYS]
    return keys[0] if len(keys) == 1 and len(schema) == 1 else ""


def _shape(pointer: str, wrapper: str = "") -> str:
    """枚举节点在 Schema 里的**形状路径**（去包装根键，只留**字段名**链）。

    ⚠️ 手册里 `TYPE` 同时出现在 `ELEMENT.TYPE` 与 `BOUNDARY.TYPE` 下 ⇒ 按**字段名**归并会
    把两套词汇混成一张表（假阳性）。按**形状**归并则各归各的。
    """
    parts = [
        part
        for part in pointer.split("/")
        if part
        and part != "#"
        and part not in STRUCTURAL_KEYS
        and part not in CONDITIONAL_KEYS
        and not part.isdigit()
        and not part.startswith("^")
    ]
    if wrapper and parts and parts[0] == wrapper:
        parts = parts[1:]
    return ".".join(parts)


def _is_conditional(pointer: str) -> bool:
    """枚举节点是否落在**条件分支**（`if` / `then` / `else` / `not`）里。"""
    return any(part in CONDITIONAL_KEYS for part in pointer.split("/"))


def _collect_declared(
    node: object, sink: dict[str, set[str]], wrapper: str, pointer: str = ""
) -> None:
    """递归收集 `json_schema` 里**声明**的取值（`enum` 与 `oneOf[].const`），按**形状路径**归并。

    ⚠️ 条件分支里的枚举（`if` / `then` / `else`）**不**收 —— 它们是收窄约束，不是取值表。
    """
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{pointer}/{key}"
            if isinstance(value, dict):
                declared = value.get("enum")
                if isinstance(declared, list) and declared and not _is_conditional(child):
                    sink.setdefault(_shape(child, wrapper), set()).update(
                        _norm(item) for item in declared
                    )
                branches = value.get("oneOf")
                if isinstance(branches, list) and branches and not _is_conditional(child):
                    consts = [
                        branch.get("const")
                        for branch in branches
                        if isinstance(branch, dict) and "const" in branch
                    ]
                    if consts and len(consts) == len(branches):
                        sink.setdefault(_shape(child, wrapper), set()).update(
                            _norm(item) for item in consts
                        )
            _collect_declared(value, sink, wrapper, child)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _collect_declared(item, sink, wrapper, f"{pointer}/{index}")


def _norm(value: Any) -> str:
    """取值的**规范文本**（非字符串按 JSON 写法；枚举比较一律用它）。"""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _walk_example(node: object, sink: dict[str, set[str]]) -> None:
    """递归收集**示例体**里的叶子取值（按字段名归并）—— 只进**弱来源**。"""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, (str, int, float, bool)):
                sink.setdefault(key, set()).add(_norm(value))
            else:
                _walk_example(value, sink)
    elif isinstance(node, list):
        for item in node:
            _walk_example(item, sink)


def manual_sources(repo: pathlib.Path) -> dict[str, Any]:
    """手册侧来源（**声明** + **弱**：示例体 / 规格表）。

    Returns:
        含 `declared`（**字段名** → 取值，供来源分类）、`declared_articles`（字段名 → 文章 id 集合）、
        `declared_shapes` / `shape_articles`（**形状路径** → 取值 / 文章 id，供「来源太窄」的
        同 URI 词汇）、`uri_shapes`（uri → 形状路径集合）、`uri_examples`（`(uri, 字段)` → 取值）、
        `uri_articles`（uri → 文章 id 集合）、`uri_titles`、`uri_argument_fields`、`weak_tokens`。
    """
    declared: dict[str, set[str]] = {}
    declared_articles: dict[str, set[str]] = {}
    declared_shapes: dict[str, set[str]] = {}
    shape_articles: dict[str, set[str]] = {}
    uri_shapes: dict[tuple[str, str], set[str]] = {}
    uri_shape_articles: dict[tuple[str, str], set[str]] = {}
    uri_examples: dict[tuple[str, str], set[str]] = {}
    uri_articles: dict[str, set[str]] = {}
    uri_titles: dict[str, set[str]] = {}
    uri_argument_fields: dict[str, set[str]] = {}
    weak_tokens: set[str] = set()

    for filename in MANUAL_FILENAMES:
        document = _load_json(repo / filename)
        for index, entry in enumerate(document.get("endpoints") or []):
            article = f"{filename}#{index}"
            uri = _norm_uri(entry.get("input_uri"))
            uri_articles.setdefault(uri, set()).add(article)
            uri_titles.setdefault(uri, set()).add(str(entry.get("title") or ""))
            raw = entry.get("json_schema")
            if raw:
                try:
                    schema = json.loads(str(raw))
                except (TypeError, ValueError):
                    schema = None
                if schema is not None:
                    found: dict[str, set[str]] = {}
                    _collect_declared(schema, found, wrapper_of(schema))
                    for shape, values in found.items():
                        declared_shapes.setdefault(shape, set()).update(values)
                        shape_articles.setdefault(shape, set()).add(article)
                        uri_shapes.setdefault((uri, shape), set()).update(values)
                        uri_shape_articles.setdefault((uri, shape), set()).add(article)
                        field = shape.rsplit(".", 1)[-1]
                        declared.setdefault(field, set()).update(values)
                        declared_articles.setdefault(field, set()).add(article)
            for example in entry.get("examples") or []:
                body = example.get("json")
                if not isinstance(body, str):
                    continue
                try:
                    parsed = json.loads(body)
                except json.JSONDecodeError:
                    continue
                found = {}
                _walk_example(parsed, found)
                for field, values in found.items():
                    uri_examples.setdefault((uri, field), set()).update(values)
                    weak_tokens.update(values)
                if isinstance(parsed, dict) and isinstance(parsed.get("Argument"), dict):
                    uri_argument_fields.setdefault(uri, set()).update(parsed["Argument"])
            for row in entry.get("specifications") or []:
                if isinstance(row, list):
                    weak_tokens.update(str(cell) for cell in row)
            for example in (entry.get("request_examples") or []) + (
                entry.get("response_examples") or []
            ):
                weak_tokens.add(
                    example if isinstance(example, str) else json.dumps(example, ensure_ascii=False)
                )
    return {
        "declared": declared,
        "declared_articles": declared_articles,
        "declared_shapes": declared_shapes,
        "shape_articles": shape_articles,
        "uri_shapes": uri_shapes,
        "uri_shape_articles": uri_shape_articles,
        "uri_examples": uri_examples,
        "uri_articles": uri_articles,
        "uri_titles": uri_titles,
        "uri_argument_fields": uri_argument_fields,
        "weak_tokens": weak_tokens,
    }


def weak_vocabulary(repo: pathlib.Path, weak_tokens: set[str]) -> tuple[set[str], str]:
    """**弱来源**词汇 = （示例体 / 规格表取值 ∪ 仓库内上游文档 ∪ 自省证据 的词元，去空白小写长串）。

    Returns:
        `(tokens, blob)`：`tokens` 用于**逐字**命中；`blob` 用于**去空白后子串**命中
        （上游文档里的 `Min & Max` 与枚举里的 `Min&Max` 只是**空格写法**不同，不该算「无法追溯」）。
    """
    tokens = set(weak_tokens)
    chunks: list[str] = []
    for filename in WEAK_DOC_FILENAMES:
        path = repo / filename
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            tokens.update(re.findall(r"[A-Za-z0-9_.\-/]+", text))
            chunks.append(text)
    evidence = repo / "registry" / WEAK_EVIDENCE_RELATIVE
    if evidence.is_file():
        text = evidence.read_text(encoding="utf-8", errors="ignore")
        tokens.update(re.findall(r"[A-Za-z0-9_.\-/]+", text))
        chunks.append(text)
    chunks.append("\n".join(sorted(weak_tokens)))
    blob = re.sub(r"\s+", "", "\n".join(chunks)).lower()
    return tokens, blob


def _weakly_traced(value: str, tokens: set[str], blob: str) -> bool:
    """取值是否能在**弱来源**里找到（逐字命中，或**去空白**后的子串命中）。"""
    return value in tokens or value.lower().replace(" ", "") in blob


# ===== `registry/schema/**` 的枚举约束 =====


def constraint_nodes(document: dict[str, Any]) -> list[tuple[str, str, str, list[Any]]]:
    """Schema 文件里的全部枚举约束 `[(kind, pointer, field, values)]`（**逐条**，含嵌套）。

    `kind` = `enum`（`{"enum": [...]}`）或 `oneOf.const`（`oneOf[].const` 全覆盖 —— 与
    `spec_guard._allowed_values()` 的两种形态**逐字对应**）。

    ⚠️ `field` = **最近一个非结构键**（`STRUCTURAL_KEYS` 不更新它）⇒ `.../ITEMS/items` 的枚举
    归到字段 `ITEMS` 名下（而不是笼统的 `items`）。
    """
    found: list[tuple[str, str, str, list[Any]]] = []

    def walk(node: object, pointer: str, field: str) -> None:
        if isinstance(node, dict):
            enum = node.get("enum")
            if isinstance(enum, list) and enum:
                found.append((KIND_ENUM, pointer, field, list(enum)))
            branches = node.get("oneOf")
            if isinstance(branches, list) and branches:
                consts = [
                    branch.get("const")
                    for branch in branches
                    if isinstance(branch, dict) and "const" in branch
                ]
                if consts and len(consts) == len(branches):
                    found.append((KIND_CONST, pointer, field, consts))
            for key, value in node.items():
                walk(value, f"{pointer}/{key}", field if key in STRUCTURAL_KEYS else key)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{pointer}/{index}", field)

    walk(document.get("schema"), "#", "")
    return found


def schema_documents(repo: pathlib.Path) -> list[tuple[str, dict[str, Any]]]:
    """`[(相对路径, 文档)]`（`registry/schema/**/*.json`，路径排序 ⇒ 确定性）。"""
    root = repo / "registry" / SCHEMA_DIRECTORY
    return [
        (path.relative_to(repo).as_posix(), _load_json(path))
        for path in sorted(root.rglob("*.json"))
    ]


def _problem_field(problems: list[str]) -> str:
    """从 `spec_guard` 的违例文案里取**字段名**（`"Argument.PARTS[0]='PartI' 不在…"` ⇒ `PARTS`）。"""
    if not problems:
        return ""
    path = problems[0].split("=", 1)[0]
    return re.sub(r"\[\d+\]$", "", path).rsplit(".", 1)[-1]


def _digest(values: list[str]) -> str:
    """取值集合的**稳定摘要**（排序后 sha1 前 12 位）—— 供 `value_sets` 去重引用。"""
    payload = "\n".join(sorted(values)).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]


def endpoint_wrappers(repo: pathlib.Path) -> dict[str, str]:
    """端点 key → 数据侧声明的**请求体包装键**（端点 YAML 的 `wrapper.write`；**不**猜）。"""
    wrappers: dict[str, str] = {}
    for path in (repo / "registry").rglob("*.yaml"):
        if path.name == "instances.yaml" or SCHEMA_DIRECTORY in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        key = re.search(r"^key:\s*(\S+)\s*$", text, re.M)
        if key is None:
            continue
        wrapper = re.search(r"^wrapper:\s*\n\s+write:\s*(\S+)\s*$", text, re.M)
        wrappers[key.group(1)] = wrapper.group(1) if wrapper else ""
    return wrappers


def _drillable(schema: Any) -> bool:
    """`spec_guard` 能否**下钻**到请求体：`schema["properties"]` 是**非空**对象。

    `check_spec_values()` 正是按 `schema["properties"][key]` 逐键下钻的 ⇒ 根形态若是
    `{<包装键>: {"properties": …}}`（**根键 = 包装键**），`root` 为空 ⇒ **一个字段都不检查**。
    """
    if not isinstance(schema, dict):
        return False
    properties = schema.get("properties")
    return isinstance(properties, dict) and bool(properties)


def guard_visibility(repo: pathlib.Path, documents: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """**盲区普查**：`schema_json()`（现状口径）与 `effective_schema()`（R161 收口口径）的可下钻性。

    ⚠️ 只统计**带枚举约束**的文件（不带约束的文件拦不拦都一样）。
    """
    from app.infrastructure.adapters.midas.registry import unwrap_schema  # noqa: PLC0415

    blind_raw: list[dict[str, Any]] = []
    blind_effective: list[dict[str, Any]] = []
    total = 0
    raw_ok = 0
    effective_ok = 0
    for relative, document in documents:
        schema = document.get("schema")
        if not isinstance(schema, dict) or not constraint_nodes(document):
            continue
        total += 1
        key = str(document.get("key") or "")
        raw_ok += int(_drillable(schema))
        effective = unwrap_schema(schema)
        effective_ok += int(_drillable(effective))
        if not _drillable(schema):
            blind_raw.append({"endpoint": key, "file": relative, "file_source": document.get("source")})
        if not _drillable(effective):
            blind_effective.append({"endpoint": key, "file": relative})
    return {
        "note": (
            "`schema_json()` = 端点 Schema 文件的 `schema` **原样**（含包装根键）；"
            "`effective_schema()` = P09 的 `unwrap_schema()`（剥掉包装根键，"
            "`request_schema_fields()` 一直用它）。"
        ),
        "files_with_constraints": total,
        "drillable_with_schema_json": raw_ok,
        "drillable_with_effective_schema": effective_ok,
        "blind_with_schema_json": len(blind_raw),
        "blind_with_effective_schema": len(blind_effective),
        "blind_endpoints_with_schema_json": sorted(item["endpoint"] for item in blind_raw),
    }


def _casefold(node: Any) -> Any:
    """把 `enum` / `const` 的**字符串取值**与字符串**字面量**统一成小写（只用于**大小写对照**）。"""
    if isinstance(node, dict):
        result: dict[str, Any] = {}
        for key, value in node.items():
            if key in {"enum", "const"} and isinstance(value, list):
                result[key] = [item.lower() if isinstance(item, str) else item for item in value]
            elif key == "const" and isinstance(value, str):
                result[key] = value.lower()
            else:
                result[key] = _casefold(value)
        return result
    if isinstance(node, list):
        return [_casefold(item) for item in node]
    return node.lower() if isinstance(node, str) else node


def guard_examples(
    repo: pathlib.Path,
    documents: list[tuple[str, dict[str, Any]]],
    wrappers: dict[str, str],
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """**误伤普查**：把上游手册的**全部示例体**喂给收口后的 guard ⇒ 逐条记违例（**离线、零请求**）。

    ⚠️ 这是**铁律 ⓪** 正向判据的**离线代理**：R151 的签名就是「拦住手册**自己的**示例」
    （合法取值被拦）。判据 = `spec_guard.guard_spec_values(effective_schema(端点), 示例体, wrapper)`
    —— **同一个函数、同一份 Schema**（与 `adapter._build` 的调用**逐字一致**）。

    ⚠️ **示例要归到它自己的端点**：同一 URI 下有 **194** 个 `POST.TABLE.*` 变体文件，
    把每条示例都对**全部**变体跑一遍会凭空放大 **195 倍**（首轮跑出的假象）。
    归属判据（**机械**）：① URI 只对应一个端点 ⇒ 就是它；② 否则用示例体 `Argument` 里的
    **选择子取值**（`TABLE_TYPE` / `TEXT_TYPE` / `CURRENT_MODE`）去登记表里找 token 匹配的端点；
    ③ 匹配不上 ⇒ 记 `unattributed`（**不**猜）。

    ⚠️ **大小写差异单独**计数（**R160** §3 已实测原生对 `TABLE_TYPE` 大小写不敏感，
    而 `spec_guard` 是**逐字**比较）：把 Schema 与体的字符串**统一小写**后重跑一遍，
    仍违例 ⇒ **真**缺口；通过 ⇒ 仅大小写写法差异。
    """
    from app.infrastructure.adapters.midas.errors import MidasValidationError  # noqa: PLC0415
    from app.infrastructure.adapters.midas.registry import unwrap_schema  # noqa: PLC0415
    from app.infrastructure.adapters.midas.spec_guard import guard_spec_values  # noqa: PLC0415

    by_uri: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for relative, document in documents:
        by_uri.setdefault(_norm_uri(document.get("uri")), []).append((relative, document))
    token_to_key: dict[str, str] = {}
    for entry in entries:
        token = str(entry.get("table_type") or "")
        key = str(entry.get("key") or "")
        if token:
            token_to_key.setdefault(token.lower(), key)
        token_to_key.setdefault(key.rsplit(".", 1)[-1].lower(), key)

    def pick(candidates: list[tuple[str, dict[str, Any]]], body: Any) -> Any:
        """把示例归到**它自己的**端点（见 docstring 的三条判据）。"""
        if len(candidates) == 1:
            return candidates[0]
        argument = body.get("Argument") if isinstance(body, dict) else None
        if isinstance(argument, dict):
            for field in ("TABLE_TYPE", "TEXT_TYPE", "CURRENT_MODE"):
                value = argument.get(field)
                if not isinstance(value, str):
                    continue
                key = token_to_key.get(value.lower())
                for candidate in candidates:
                    if key and str(candidate[1].get("key") or "") == key:
                        return candidate
        return None

    violations: list[dict[str, Any]] = []
    checked = 0
    unattributed = 0
    for filename in MANUAL_FILENAMES:
        document = _load_json(repo / filename)
        for index, entry in enumerate(document.get("endpoints") or []):
            candidates = by_uri.get(_norm_uri(entry.get("input_uri")))
            if not candidates:
                continue
            for example in entry.get("examples") or []:
                body = example.get("json")
                if not isinstance(body, str):
                    continue
                try:
                    parsed = json.loads(body)
                except json.JSONDecodeError:
                    continue
                chosen = pick(candidates, parsed)
                if chosen is None:
                    unattributed += 1
                    continue
                relative, schema_document = chosen
                key = str(schema_document.get("key") or "")
                wrapper = wrappers.get(key) or "none"
                effective = unwrap_schema(schema_document.get("schema"))
                checked += 1
                try:
                    guard_spec_values(effective, parsed, endpoint=key, wrapper=wrapper)
                except MidasValidationError as error:
                    problems = [str(item) for item in (error.details or {}).get("problems") or []]
                    case_only = True
                    try:
                        guard_spec_values(
                            _casefold(effective),
                            _casefold(parsed),
                            endpoint=key,
                            wrapper=wrapper,
                        )
                    except MidasValidationError:
                        case_only = False
                    violations.append(
                        {
                            "endpoint": key,
                            "file": relative,
                            "article": f"{filename}#{index}",
                            "title": str(entry.get("title") or ""),
                            "example": str(example.get("name") or ""),
                            "wrapper": wrapper,
                            "problems": problems[:3],
                            "problem_count": len(problems),
                            "case_insensitive_only": case_only,
                        }
                    )
    by_endpoint: dict[str, int] = {}
    for item in violations:
        by_endpoint[item["endpoint"]] = by_endpoint.get(item["endpoint"], 0) + 1
    return {
        "checked": checked,
        "unattributed": unattributed,
        "violations": len(violations),
        "violations_case_insensitive_only": sum(
            1 for item in violations if item["case_insensitive_only"]
        ),
        "endpoints_with_violations": len(by_endpoint),
        "top_endpoints": sorted(by_endpoint.items(), key=lambda kv: (-kv[1], kv[0]))[:20],
        "items": violations[:200],
    }


def _classify(
    values: set[str],
    *,
    vocabulary: set[str],
    declared: dict[str, set[str]],
    declared_articles: dict[str, set[str]],
    field: str,
) -> str:
    """四个来源分类（**登记表 → 手册声明 → 单篇文章 → 无法追溯**，优先级即此序）。"""
    if values <= vocabulary:
        return CLASS_MANIFEST
    known = declared.get(field, set())
    if values and values <= known:
        return CLASS_MANUAL if len(declared_articles.get(field, set())) >= 2 else CLASS_SINGLE_ARTICLE
    return CLASS_UNTRACEABLE


def _case_insensitive_gap(own: set[str], values: set[str]) -> list[str]:
    """`own - values`（**大小写归一**后仍缺的取值，排序）。"""
    lowered = {item.lower() for item in values}
    return sorted(item for item in own if item.lower() not in lowered)


def _exclusion_of(values: list[str], *, field: str, titles: set[str]) -> str:
    """`missing_enum` 候选的**机械排除**规则（返回规则名；不命中 ⇒ 空串）。"""
    lowered = [value.lower() for value in values]
    if "NAME" in field.upper():
        return "name_like"
    if lowered and all(value in {"true", "false"} for value in lowered):
        return "boolean_like"
    if all(_is_numeric(value) for value in values):
        return "numeric_like"
    if all(
        ("/" in value or "\\" in value or re.search(r"\.[A-Za-z0-9]{1,5}$", value))
        for value in values
    ):
        return "path_like"
    if titles and all(
        any(value.lower() in title.lower() for title in titles if title) for value in values
    ):
        return "title_like"
    return ""


def _is_numeric(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


# ===== 普查 =====


def build(repo: pathlib.Path) -> dict[str, Any]:
    """机械普查（**纯函数**：只读数据文件，便于测试复算）。"""
    entries = manifest_entries(repo)
    vocabulary = manifest_vocabulary(entries)
    family_tokens = endpoint_family_tokens(entries)
    own_tokens = endpoint_tokens(entries)
    manual = manual_sources(repo)
    weak, weak_blob = weak_vocabulary(repo, manual["weak_tokens"])

    documents = schema_documents(repo)
    by_uri: dict[str, list[str]] = {}
    for relative, document in documents:
        by_uri.setdefault(_norm_uri(document.get("uri")), []).append(str(document.get("key") or ""))

    # **声明选择子**（`narrow` 的适用范围）：**同一 URI** 下手册**多篇文章**声明该**形状路径**，
    # 且取值在**切分**文章（平均每篇 ≥ 1 个取值）。
    selectors: set[tuple[str, str]] = set()
    for shape_key, values in manual["uri_shapes"].items():
        articles = manual["uri_shape_articles"].get(shape_key, set())
        if len(articles) >= 2 and len(values) / len(articles) >= DECLARED_SELECTOR_RATIO:
            selectors.add(shape_key)

    constraints: list[dict[str, Any]] = []
    value_sets: dict[str, list[str]] = {}
    by_class: dict[str, int] = {name: 0 for name in CLASS_ORDER}
    kind_counts = {KIND_ENUM: 0, KIND_CONST: 0}
    narrow: list[dict[str, Any]] = []
    unexplained: list[dict[str, Any]] = []
    fields_with_enum: set[tuple[str, str]] = set()

    for relative, document in documents:
        key = str(document.get("key") or "")
        uri = _norm_uri(document.get("uri"))
        file_source = str(document.get("source") or "")
        wrapper = wrapper_of(document.get("schema"))
        for kind, pointer, field, raw_values in constraint_nodes(document):
            values = sorted({_norm(item) for item in raw_values})
            value_set = set(values)
            digest = _digest(values)
            value_sets.setdefault(digest, values)
            kind_counts[kind] += 1
            klass = _classify(
                value_set,
                vocabulary=vocabulary,
                declared=manual["declared"],
                declared_articles=manual["declared_articles"],
                field=field,
            )
            by_class[klass] += 1
            fields_with_enum.add((uri, field))
            shape = _shape(pointer, wrapper)
            constraints.append(
                {
                    "file": relative,
                    "endpoint": key,
                    "field": field,
                    "shape": shape,
                    "kind": kind,
                    "pointer": pointer,
                    "class": klass,
                    "value_set": digest,
                    "value_count": len(values),
                    "declaring_articles": len(manual["declared_articles"].get(field, set())),
                    "file_source": file_source,
                }
            )
            # ---- 标志 ①：来源太窄（会拦住合法调用）----
            own: set[str] = set()
            source_of_own = ""
            family = family_tokens.get(key, set())
            token = own_tokens.get(key, "")
            key_hint = key.rsplit(".", 1)[-1]
            if field == "TABLE_TYPE" and family:
                own |= family
                source_of_own = "登记表 `table_type`"
            shape_values = manual["uri_shapes"].get((uri, shape), set())
            if shape_values:
                own |= shape_values
                source_of_own = f"{source_of_own} + 同 URI 同形状的手册声明".strip(" +")
            own.discard("")
            gap = _case_insensitive_gap(own, value_set)
            # ⚠️ **适用范围**（三条**并列**判据，见模块文档「标志 ①」）：
            #   ① 该**形状**是「声明选择子」（同一 URI 下多篇文章声明且取值切分文章）；
            #   ② 缺口非空（大小写归一后仍缺）；
            #   ③ 该端点**不是**「自己的 token 已在枚举里」的变体端点；
            #   ④ 落在 `if` / `then` **条件分支**里的枚举是收窄约束 ⇒ 跳过；
            #   ⑤ **来源可复算**：登记表的 token 词汇（`TABLE_TYPE`）**或**该 URI 只有**一个** Schema
            #      文件（⇒ 这个文件就是该 URI 全部文章的入口，手册声明即它的词汇表）。
            self_serving = any(
                candidate and candidate.lower() in {item.lower() for item in values}
                for candidate in (token, key_hint)
            )
            from_manifest = field == "TABLE_TYPE" and bool(family) and not family <= value_set
            single_schema = len(by_uri.get(uri, ())) == 1
            if (
                (uri, shape) in selectors
                and gap
                and not self_serving
                and not _is_conditional(pointer)
                and (from_manifest or single_schema)
            ):
                narrow.append(
                    {
                        "key": f"{key}::{field}",
                        "file": relative,
                        "endpoint": key,
                        "field": field,
                        "shape": shape,
                        "pointer": pointer,
                        "value_count": len(values),
                        "own_token": token,
                        "missing_count": len(gap),
                        "missing_sample": gap[:8],
                        "missing_value_set": _digest(gap),
                        "source_of_own": source_of_own,
                    }
                )
                value_sets.setdefault(_digest(gap), gap)
            # ---- 标志 ③：真·无法追溯 ----
            unknown = sorted(
                value
                for value in values
                if value not in vocabulary and not _weakly_traced(value, weak, weak_blob)
            )
            if unknown:
                unexplained.append(
                    {
                        "file": relative,
                        "endpoint": key,
                        "field": field,
                        "pointer": pointer,
                        "file_source": file_source,
                        "unknown_count": len(unknown),
                        "unknown_sample": unknown[:8],
                        "unknown_value_set": _digest(unknown),
                    }
                )
                value_sets.setdefault(_digest(unknown), unknown)

    # ---- 标志 ②：缺枚举（非法取值抓不到）----
    missing: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for uri, fields in sorted(manual["uri_argument_fields"].items()):
        articles = manual["uri_articles"].get(uri, set())
        if len(articles) < 2 or not by_uri.get(uri):
            continue
        for field in sorted(fields):
            if (uri, field) in fields_with_enum:
                continue
            values = sorted(manual["uri_examples"].get((uri, field), set()))
            if len(values) < 2:
                continue
            ratio = len(values) / len(articles)
            record = {
                "uri": uri,
                "field": field,
                "endpoints": sorted(by_uri[uri]),
                "articles": len(articles),
                "value_count": len(values),
                "ratio": round(ratio, 3),
                "values": values,
            }
            rule = _exclusion_of(values, field=field, titles=manual["uri_titles"].get(uri, set()))
            if rule:
                record["excluded_by"] = rule
                excluded.append(record)
            elif ratio >= SELECTOR_RATIO:
                missing.append(record)
    missing.sort(key=lambda item: (-item["value_count"], item["uri"], item["field"]))
    excluded.sort(key=lambda item: (item["uri"], item["field"]))

    guard: dict[str, Any]
    example_blocked: list[dict[str, Any]] = []
    try:
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        wrappers = endpoint_wrappers(repo)
        visibility = guard_visibility(repo, documents)
        examples = guard_examples(repo, documents, wrappers, entries)
        guard = {
            "available": True,
            "visibility": visibility,
            "examples": examples,
        }
        # **标志 ④**：上游手册**自己的示例**会被 guard 拦住（**大小写差异不计**）
        # ⇒ 这是 **R151** 的**直接签名**（合法取值被拦）。
        for item in examples["items"]:
            if item["case_insensitive_only"]:
                continue
            example_blocked.append(
                {
                    "key": f"{item['endpoint']}::{_problem_field(item['problems'])}",
                    "endpoint": item["endpoint"],
                    "file": item["file"],
                    "article": item["article"],
                    "title": item["title"],
                    "example": item["example"],
                    "problems": item["problems"],
                    "problem_count": item["problem_count"],
                }
            )
    except ImportError as error:  # 合成仓库（测试用）里没有 `app` 包 ⇒ **如实**跳过
        guard = {"available": False, "reason": f"app 包不可导入：{type(error).__name__}"}

    flagged_keys = {item["key"] for item in narrow}
    flagged_keys |= {f"{item['endpoints'][0]}::{item['field']}" for item in missing}
    flagged_keys |= {f"{item['endpoint']}::{item['field']}" for item in unexplained}
    flagged_keys |= {item["key"] for item in example_blocked}
    # ⚠️ **已收口项**（`closed`）**永远**进台账 —— 即使它们已经不在标志里（收口后自然消失）。
    # 这样 `--check` 每次都会**重新导入**生成器复算 ⇒ **收口不可回退**（回退即 `--check` 红）。
    flagged_keys |= {key for key, item in DISPOSITIONS.items() if item.status == "closed"}
    dispositions = [_disposition_record(key, repo) for key in sorted(flagged_keys)]

    return {
        "tool": f"{TOOLS_DIRECTORY}/check_spec_enums.py",
        "ruling": "R161",
        "purpose": "spec_guard（R140）的枚举来源普查（R151 / R155 的同类复核）",
        "sources": {
            "manifest": {
                "file": f"registry/{MANIFEST_FILENAME}",
                "role": "登记表（来源分类 ①）",
                "vocabulary": len(vocabulary),
            },
            "manual_declarations": {
                "files": list(MANUAL_FILENAMES),
                "role": "手册声明（来源分类 ② / ③；**只**取 json_schema 的 enum / oneOf.const）",
                "fields": len(manual["declared"]),
                "values": sum(len(item) for item in manual["declared"].values()),
            },
            "weak": {
                "files": list(WEAK_DOC_FILENAMES) + [f"registry/{WEAK_EVIDENCE_RELATIVE}"],
                "role": "弱来源（示例体 / 规格表 / 上游文档 / 自省；**只**用于分档 untraceable）",
                "tokens": len(weak),
            },
            "note": (
                "「手册声明」**不**包含示例体取值（**R151** 的教训：**不**按手册**示例体**硬凑）；"
                "示例体只作弱来源。"
            ),
        },
        "summary": {
            "schema_files": len(documents),
            "constraints": {
                "total": sum(kind_counts.values()),
                KIND_ENUM: kind_counts[KIND_ENUM],
                KIND_CONST: kind_counts[KIND_CONST],
            },
            "by_class": by_class,
            "flags": {
                "narrow": len(narrow),
                "missing_enum": len(missing),
                "unexplained": len(unexplained),
                "example_blocked": len(example_blocked),
                "missing_enum_excluded": len(excluded),
            },
            "distinct_value_sets": len(value_sets),
            "guard": (
                {
                    "drillable_with_schema_json": guard["visibility"][
                        "drillable_with_schema_json"
                    ],
                    "drillable_with_effective_schema": guard["visibility"][
                        "drillable_with_effective_schema"
                    ],
                    "blind_with_schema_json": guard["visibility"]["blind_with_schema_json"],
                    "blind_with_effective_schema": guard["visibility"][
                        "blind_with_effective_schema"
                    ],
                    "example_bodies_checked": guard["examples"]["checked"],
                    "example_violations": guard["examples"]["violations"],
                    "example_violations_case_insensitive_only": guard["examples"][
                        "violations_case_insensitive_only"
                    ],
                }
                if guard["available"]
                else {"available": False}
            ),
        },
        "guard": guard,
        "value_sets": {key: value_sets[key] for key in sorted(value_sets)},
        "constraints": constraints,
        "flags": {
            "narrow": narrow,
            "missing_enum": missing,
            "unexplained": unexplained,
            "example_blocked": example_blocked,
            "missing_enum_excluded": excluded,
        },
        "dispositions": dispositions,
    }


def _disposition_record(key: str, repo: pathlib.Path) -> dict[str, Any]:
    """标志项 → 处置记录（`closed` 项**顺带**复算生成器，断言收口未回退）。"""
    item = DISPOSITIONS.get(key)
    if item is None:
        return {"key": key, "status": "missing", "ruling": "", "reason": ""}
    record: dict[str, Any] = {
        "key": key,
        "status": item.status,
        "ruling": item.ruling,
        "reason": item.reason,
    }
    if item.status == "closed":
        record["generator"] = item.generator
        record["generator_agrees"] = _generator_agrees(repo, item.generator)
    elif item.ask:
        record["ask"] = item.ask
    return record


def _generator_agrees(repo: pathlib.Path, generator: str) -> bool:
    """重新导入收口生成器并断言「已落盘 == 机械结果」（**收口不可回退**）。"""
    path = repo / generator
    if not path.is_file():
        return False
    spec = importlib.util.spec_from_file_location(f"_p168_{path.stem}", path)
    if spec is None or spec.loader is None:
        return False
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    check = getattr(module, "is_applied", None)
    return bool(check(repo)) if callable(check) else False


def render(document: dict[str, Any]) -> str:
    """落盘文本（与其他 `registry/live/*.json` 一致：`indent=1` + 结尾换行）。"""
    return json.dumps(document, ensure_ascii=False, indent=1) + "\n"


def print_summary(document: dict[str, Any]) -> None:
    """打印普查摘要（**逐条**标志项一行）。"""
    summary = document["summary"]
    classes = summary["by_class"]
    print(
        f"Schema 文件 {summary['schema_files']} 个 · 枚举约束 "
        f"{summary['constraints']['total']} 条"
        f"（enum {summary['constraints'][KIND_ENUM]} · "
        f"oneOf.const {summary['constraints'][KIND_CONST]}）"
    )
    print(
        f"来源分类：登记表 {classes[CLASS_MANIFEST]} · 手册声明 {classes[CLASS_MANUAL]} · "
        f"**单篇文章** {classes[CLASS_SINGLE_ARTICLE]} · **无法追溯** {classes[CLASS_UNTRACEABLE]}"
    )
    flags = summary["flags"]
    print(
        f"标志：来源太窄（会拦住合法调用）**{flags['narrow']}** · "
        f"缺枚举（非法取值抓不到）**{flags['missing_enum']}** · "
        f"真·无法追溯 **{flags['unexplained']}** · "
        f"**拦住手册自己的示例 {flags['example_blocked']}** · "
        f"（缺枚举候选里被机械规则排除 {flags['missing_enum_excluded']}）"
    )
    guard = document.get("guard") or {}
    if guard.get("available"):
        visibility = guard["visibility"]
        examples = guard["examples"]
        print(
            f"**spec_guard 盲区普查**：带枚举的文件 {visibility['files_with_constraints']} 个 ⇒ "
            f"现状（`schema_json`）可下钻 **{visibility['drillable_with_schema_json']}** · "
            f"改用 `effective_schema` 后 **{visibility['drillable_with_effective_schema']}**"
            f"（**盲区 {visibility['blind_with_schema_json']} → "
            f"{visibility['blind_with_effective_schema']}**）"
        )
        print(
            f"**误伤普查**（上游手册示例体喂给收口后的 guard）：检查 {examples['checked']} 条 ⇒ "
            f"违例 **{examples['violations']}** 条"
            f"（其中**仅大小写**差异 {examples['violations_case_insensitive_only']} 条）· "
            f"涉及 {examples['endpoints_with_violations']} 个端点"
        )
        for endpoint, count in examples["top_endpoints"][:8]:
            print(f"    ⚠️ 示例违例 {endpoint} × {count}")
    for item in document["flags"]["missing_enum"]:
        print(
            f"  ⚠️ 缺枚举 {item['uri']} :: {item['field']} ⇒ {item['value_count']} 个取值 / "
            f"{item['articles']} 篇文章（端点 {', '.join(item['endpoints'][:3])}）"
        )
    for item in document["flags"]["narrow"]:
        print(
            f"  ⚠️ 来源太窄 {item['endpoint']} :: {item['field']} ⇒ 缺 {item['missing_count']} 个"
            f"（例 {item['missing_sample'][:3]}；自己的 token = {item['own_token']!r}）"
        )
    for item in document["flags"]["example_blocked"]:
        print(
            f"  ⚠️ 拦住手册示例 {item['endpoint']} :: {item['problems'][0][:90]}"
        )
    for item in document["dispositions"]:
        mark = "✅ 已收口" if item["status"] == "closed" else "⏳ 留缺"
        if item["status"] == "missing":
            mark = "❌ 未处置"
        print(f"  {mark} {item['key']}（{item['ruling']}）")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="spec_guard 的枚举来源普查（R161）")
    parser.add_argument("--repo", default=".", help="仓库根目录（默认当前目录）")
    parser.add_argument("--write", action="store_true", help="写回证据 JSON（默认只预演）")
    parser.add_argument("--check", action="store_true", help="断言已落盘 == 机械结果 + 台账完整")
    args = parser.parse_args(argv)

    repo = pathlib.Path(args.repo).resolve()
    path = repo / "registry" / EVIDENCE_RELATIVE
    document = build(repo)
    text = render(document)
    current = path.read_text(encoding="utf-8") if path.is_file() else None

    print_summary(document)

    unhandled = [item["key"] for item in document["dispositions"] if item["status"] == "missing"]
    if unhandled:
        print(f"❌ 有 {len(unhandled)} 个标志项**没有**处置（缺口不许静默）：{unhandled[:8]}")
        return 1
    regressed = [
        item["key"]
        for item in document["dispositions"]
        if item["status"] == "closed" and not item.get("generator_agrees")
    ]
    if regressed:
        print(f"❌ 已收口项**回退**（生成器与已落盘不一致）：{regressed}")
        return 1

    if current == text:
        print(f"✅ {EVIDENCE_RELATIVE} 与机械结果一致（无差异）")
        return 0
    print(f"  需写入 {EVIDENCE_RELATIVE}")
    if args.check:
        print("❌ --check：已落盘内容与机械结果不一致（或文件缺失）")
        return 1
    if args.write:
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"WROTE registry/{EVIDENCE_RELATIVE}")
    else:
        print("（预演模式；加 --write 才会写回）")
    return 0


if __name__ == "__main__":
    # Windows 控制台默认 cp949/cp936：本工具会打印中文/符号，不重设编码会 UnicodeEncodeError。
    # ⚠️ 必须在 `__main__` 块内：测试用 `exec_module()` 装载本模块，模块级调用会改写
    #    **pytest 的捕获流**，破坏其后所有用例的 capture。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
