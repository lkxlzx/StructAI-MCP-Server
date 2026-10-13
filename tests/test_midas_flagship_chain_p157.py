"""P157：`docs/07` §13.5 的**旗舰五步链**在**真机**上的实测结论（**未跑通**，成因逐条钉住）。

一句话
------
**旗舰五步链在真机上仍未跑通** —— 而且这次**定位到了两处结构成因**（都**不是**探针问题）：

| 阶段 | 步 | 结果 | 原生成因 |
| --- | --- | --- | --- |
| **A（§13.5 逐字）** | ① `BUILD.COLUMN` | `FAILED` | `POST /DB/MATL` → **`400 Wrong Field`** |
| **B（替代前缀 ①′ + ②–⑤）** | ①′ 四个原子 Operation | **`PASSED` ×5** | —— |
| | ② `MODEL.LOAD.ASSIGN` | `FAILED` | `POST /DB/CNLD` → **`400 Not Found Key`** |
| | ③④⑤ | `NOT_RUN` | 链在 ② 停止（**有界**，不硬跑） |

⚠️ **两条都是 `app/**` 的结构缺口，本批未获授权 ⇒ 如实留缺、不修、不硬凑。**

⚠️ **R131 的成因经用户证据更正（本文件已按更正的结论写）**：**不**是"canonical 少 11 个字段"，
而是 **`BUILD.COLUMN` 的材质载荷混用了两条互斥路线** —— 它声明 `TYPE="STEEL"`（= **规范库**路线）
却给"用户自定义"的属性（`elastic_modulus` / `poisson_ratio` / `density`），且**一个库判据都不给**
（`p_type` / `standard` / `db` / `code`）⇒ 原生 `400 Wrong Field`。
手册 `db/MATL` 的 **3** 个示例划清了边界（`Standard` / `Isotropic - User Defined` /
`Orthotropic - User Defined`）：**`TYPE` + `P_TYPE` 决定哪一组属性有效**。
**修正后的取值**（用户给定：钢材 · `GB50017-17(S)` · 数据库 `Q355`）在 `MODEL.MATERIAL.ASSIGN` 下
**实测 `200` 且落库** ⇒ **R131 的材质面已闭环**（`app/**` **零**改动）。

* **R132（新，仍未闭环）**：`MODEL.LOAD.ASSIGN` **结构上**无法在**没有工况**的项目上成功 ——
  `DB.CNLD` 要求 `LCNAME` 指向**已存在**的工况（`400 Not Found Key`），而接口层
  **没有**任何 Operation 能**创建**工况：`MODEL.LOAD.ASSIGN` 的编排里**声明**了
  `DB.STLD` 的 `write_load_case` 步，但 `select_steps` **只**选出该荷载类型对应的那一步
  （`DB.STLD` 永不被执行）；`MODEL.LOAD.DELETE` 却**能删** `DB.STLD`（**不对称**）。

⚠️ **残留 = 0**：本批**自建**的编号**全部**逆序删除并**再读确认不在**（R119）；
跑前 / 跑后哨兵**一致且全空** ⇒ **项目未被弄脏**（`analysis_result_persists = None`：
③ 未运行，**没有**产生分析结果）。

⚠️ **R128 的判据在本批被**再验证**一次**：② 的 `2xx` **不**被当作通过 —— 它**是** `400`；
而 ①′ 的每一步都以**再读**为准（外层键无效时原生**静默 `200` 却不建**）。

本文件的判定点
--------------
1. **阶段 A 未通过**，成因是 `DB.MATL` 的 `Wrong Field`（**两条路线混用**；不是探针 / 端点不存在）。
2. **阶段 B 的 ①′ 通过 5 步**（建模链本身是通的；材质走**规范库路线** `GB50017-17(S)` + `Q355`）。
3. **阶段 B 的 ② 未通过**，成因是 `DB.CNLD` 的 `Not Found Key`（工况不存在）。
4. **R131 / R132 是结构事实**：离线**可复算**（不依赖证据文件）。
5. **零残留 + 哨兵一致**（项目未被弄脏）。
6. **不变量**：`write_path_coverage()` = `0 / 633` · 缺口 `517` = `271` + `246` ·
   分类 `271` = `0` + `51` + `220` · 写路径子桶 `13` = `13` · 读路径子桶 `15` = `2` + `7` + `6`。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.infrastructure.adapters.midas.live import write_path_coverage
from app.infrastructure.adapters.midas.registry import MidasRegistry

REPO_ROOT = Path(__file__).resolve().parents[1]
"""仓库根目录。"""

CHAIN_EVIDENCE = REPO_ROOT / "registry" / "live" / "flagship_chain_probe.json"
WRITE_EVIDENCE = REPO_ROOT / "registry" / "live" / "interface_path_probe.json"
READ_EVIDENCE = REPO_ROOT / "registry" / "live" / "interface_read_probe.json"
GAP_EVIDENCE = REPO_ROOT / "registry" / "live" / "interface_mapping_gap.json"
CHAIN_TOOL = REPO_ROOT / "registry" / "tools" / "probe_flagship_chain.py"
PROBE_TOOL = REPO_ROOT / "registry" / "tools" / "probe_interface_paths.py"

TOP_NODE = 2
"""柱顶节点编号（`docs/07` §13.5：柱底固定、柱顶受荷）—— 荷载条目的外层键（R128）。"""

SPEC_OPERATIONS = (
    "BUILD.COLUMN",
    "MODEL.LOAD.ASSIGN",
    "ANALYSIS.STATIC",
    "RESULT.NODE.DISPLACEMENT",
    "DESIGN.STEEL",
)
"""`docs/07` §13.5 的五步链（阶段 A 的步集）。"""

ELEMENT_ID = 1
"""柱单元编号（`DESIGN.STEEL` 的**构件指派** `MEMB.AELEM` 用它）。"""

SUBSTITUTE_OPERATIONS = (
    "MODEL.MATERIAL.ASSIGN",
    "MODEL.SECTION.ASSIGN",
    "MODEL.NODE.CREATE",
    "MODEL.NODE.CREATE",
    "MODEL.ELEMENT.CREATE",
    "MODEL.BOUNDARY.ASSIGN",
    "MODEL.LOAD.ASSIGN",
    "MODEL.LOAD_COMBINATION.ASSIGN",
    "ANALYSIS.STATIC",
    "RESULT.NODE.DISPLACEMENT",
    "DESIGN.STEEL",
)
"""阶段 B 的步集（①′ 的 5 步 + ②–⑤）。"""

MANUAL = REPO_ROOT / "MIDAS_API_Online_Manual_数据_v1.0.json"
"""上游手册（`db/MATL` 的 **3** 个示例在这里；**离线**可读）。"""

LIBRARY_ROUTE_KEYS = ("p_type", "standard", "db", "code", "belast")
"""**规范库路线**的判据键（`Standard` 示例里 `PARAM[0]` 的那一组）。"""

USER_ROUTE_PROPERTIES = ("elastic_modulus", "poisson_ratio", "density")
"""**用户自定义路线**的属性键（`_column_payloads` 只给这些）。"""

SENTINEL_ENDPOINTS = (
    "DB.CNLD",
    "DB.CONS",
    "DB.ELEM",
    "DB.GRUP",
    "DB.LCOM-STEEL",
    "DB.MATL",
    "DB.NODE",
    "DB.SECT",
    "DB.STLD",
)

EXPECTED_WRITE_COUNTS = {"PASSED": 13}
EXPECTED_READ_COUNTS = {"PASSED": 2, "PARTIAL": 7, "FAILED": 6}
EXPECTED_GAP_TOTAL = 511
EXPECTED_GAP_NOT_IN_CONTRACT = 265
EXPECTED_GAP_NO_READBACK = 246
EXPECTED_WRITE_PATH_TOTAL = 633
EXPECTED_MODEL_WRITE_TOTAL = 434


def _load(path: Path, name: str) -> Any:
    """按路径装载数据侧工具（`registry/tools` 不是包）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _matl_examples() -> dict[str, Any]:
    """上游手册 `db/MATL` 的**全部**示例（`{示例名: 解析后的 JSON}`；**离线**）。"""
    manual = _json(MANUAL)
    for endpoint in manual["endpoints"]:
        if str(endpoint.get("input_uri") or "").lower() == "db/matl":
            return {
                str(item["name"]): json.loads(str(item["json"]))
                for item in endpoint.get("examples") or []
            }
    raise AssertionError("db/MATL 不在上游手册里")


def _chain() -> dict[str, Any]:
    return _json(CHAIN_EVIDENCE)


def _step(document: dict[str, Any], key: str, operation: str) -> dict[str, Any]:
    rows = document.get(key) or []
    for row in rows:
        if str(row["operation"]) == operation:
            return row
    raise AssertionError(f"{operation} not in {key}")


def _rejections(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in row["requests"] if int(item["status"]) >= 400]


# ===== 1. 阶段 A：`docs/07` §13.5 逐字 —— **未通过** =====


def test_p157_the_spec_chain_does_not_pass_and_stops_at_the_first_step() -> None:
    """门槛：阶段 A **未通过**，且**首个失败即停**（其余记 `NOT_RUN`，**不**硬跑）。

    ⚠️ **P157 加固**：`engineering_model_build` 是 **ASYNC** ⇒ **必须**看**任务终态**
    （`task_failed`）；MCP 层只回 `QUEUED` **不**算通过（实测：`DOC.ANAL` 的
    `registry_mapping_not_verified` 就是这样被吞掉的）。
    """
    document = _chain()
    assert document["criterion_version"] == 1
    assert [str(row["operation"]) for row in document["steps"]] == list(SPEC_OPERATIONS)
    assert document["verdict"] == "NOT_PASSED"
    assert document["counts"] == {"FAILED": 1, "NOT_RUN": 4}
    assert document["aborted"] == ""
    build = document["steps"][0]
    assert build["status"] == "FAILED", build
    assert build["detail"] == "task_failed", build
    assert str(build["task"]["status"]) == "FAILED", build["task"]
    assert build["error"]["details"]["endpoint"] == "DB.MATL", build["error"]
    for row in document["steps"][1:]:
        assert row["status"] == "NOT_RUN", row
        assert row["detail"] == "chain_stopped_at_previous_failure", row


def test_p157_the_spec_chain_is_blocked_by_the_material_body() -> None:
    """门槛（**R131**）：① 的成因 = `POST /DB/MATL` 的 **`400 Wrong Field`**（**两条路线混用**）。

    ⚠️ **不是**端点不存在、**不是**形状（外层键是编号 `"1"`）、**不是**探针参数缺失 ——
    节点 / 单元**都**已建成（再读确认），只有材质被拒。
    """
    build = _chain()["steps"][0]
    assert build["readback"]["DB.NODE"]["present"] is True, build["readback"]
    assert build["readback"]["DB.ELEM"]["present"] is True, build["readback"]
    assert build["readback"]["DB.MATL"]["present"] is False, build["readback"]
    assert build["readback"]["DB.SECT"]["present"] is False, build["readback"]
    rejected = _rejections(build)
    assert len(rejected) == 1, rejected
    assert rejected[0]["method"] == "POST", rejected[0]
    assert str(rejected[0]["path"]).endswith("/DB/MATL"), rejected[0]
    assert "Wrong Field" in str(rejected[0]["native_error"]), rejected[0]
    body = rejected[0]["body"]["Assign"]
    assert list(body) == ["1"], body  # 外层键 = **编号**（形状是对的）
    entry = body["1"]
    assert entry["NAME"] == "Q355B" and entry["TYPE"] == "STEEL", entry
    # ⚠️ 被拒的 body：声明了 `TYPE=STEEL`（规范库路线）却只给**用户自定义**的属性，
    #    且**一个库判据都没有**（见下一个用例的逐条断言）
    assert set(entry) == {"NAME", "TYPE", "PARAM"}, entry
    assert set(entry["PARAM"][0]) == {"ELAST", "POISN", "DEN"}, entry["PARAM"][0]


def test_p157_r131_the_manual_defines_two_mutually_exclusive_routes() -> None:
    """门槛（**R131 的判据**，**离线**可复算）：手册 `db/MATL` 的 **3** 个示例划清两条**互斥**路线。

    * `Standard`（**规范库**）：`TYPE=STEEL/CONC/SRC` + `P_TYPE=1` + `STANDARD` + `DB` + `CODE`
      + `bELAST`；**属性值由库带出**（`POISN` / `DEN` **不**在示例里 ⇒ 用户不可自定义）。
    * `Isotropic - User Defined`：`TYPE=USER` + `P_TYPE=2` + `ELAST` / `POISN` / `THERMAL` /
      `DEN` / `MASS`；**没有** `STANDARD` / `DB` / `CODE`。
    * `Orthotropic - User Defined`：`TYPE=USER` + `P_TYPE=3` + `ELAST_M` / `POISN_M` /
      `THERMAL_M` / `SHEAR_M`。

    ⇒ **`TYPE` + `P_TYPE` 决定哪一组属性有效**；混用即 `Wrong Field`。
    """
    examples = _matl_examples()
    assert set(examples) == {
        "Standard",
        "Isotropic - User Defined",
        "Orthotropic - User Defined",
    }, sorted(examples)

    standard = examples["Standard"]["Assign"]["1"]
    assert standard["TYPE"] == "STEEL", standard
    param = standard["PARAM"][0]
    assert param["P_TYPE"] == 1, param
    assert {"STANDARD", "DB", "CODE", "bELAST"} <= set(param), param
    # 规范库路线**不**给属性值（E 由库带出）
    assert "POISN" not in param and "DEN" not in param, param

    isotropic = examples["Isotropic - User Defined"]["Assign"]["5"]
    assert isotropic["TYPE"] == "USER", isotropic
    assert isotropic["PARAM"][0]["P_TYPE"] == 2, isotropic
    assert {"ELAST", "POISN", "THERMAL", "DEN", "MASS"} <= set(isotropic["PARAM"][0]), isotropic
    assert "STANDARD" not in isotropic["PARAM"][0], isotropic
    assert "DB" not in isotropic["PARAM"][0], isotropic

    orthotropic = examples["Orthotropic - User Defined"]["Assign"]["6"]
    assert orthotropic["TYPE"] == "USER", orthotropic
    assert orthotropic["PARAM"][0]["P_TYPE"] == 3, orthotropic
    assert {"ELAST_M", "POISN_M", "THERMAL_M", "SHEAR_M"} <= set(orthotropic["PARAM"][0]), (
        orthotropic
    )


def test_p157_r131_build_column_mixes_the_two_routes() -> None:
    """门槛（**R131，更正后的成因**，离线可复算）：`BUILD.COLUMN` 的材质载荷**混用两条路线**。

    它声明 `TYPE="STEEL"`（= **规范库**路线）却给"用户自定义"的属性
    （`elastic_modulus` / `poisson_ratio` / `density`），且**一个库判据都不给**
    （`p_type` / `standard` / `db` / `code`）⇒ 原生 `400 Wrong Field`（实测）。
    """
    from app.infrastructure.adapters.midas.adapter import _column_payloads  # noqa: PLC0415

    tool = _load(CHAIN_TOOL, "structai_probe_flagship_chain_p157")
    material = _column_payloads(dict(tool.COLUMN_PARAMETERS))["write_material"][0]
    # ① 声明了**规范库**路线
    assert material["type"] == "STEEL", material
    # ② 却给**用户自定义**的属性
    for field in USER_ROUTE_PROPERTIES:
        assert field in material, field
    # ③ 而**库判据一个都没有**
    for field in LIBRARY_ROUTE_KEYS:
        assert field not in material, field


def test_p157_r131_the_corrected_material_body_is_accepted() -> None:
    """门槛（**R131 的材质面闭环**，有实测依据）：修正后的**规范库**取值被原生 `200` 接受且落库。

    取值由用户给定：**钢材 · `GB50017-17(S)` · 数据库（钢号）`Q355`**；
    ⚠️ `DB` 装**钢号**、`CODE`（产品）留空 —— 与手册 `Standard` 示例同构（`EN05(S)` + `S450`）。
    """
    document = _chain()
    material_row = _step(document, "substituted", "MODEL.MATERIAL.ASSIGN")
    assert material_row["status"] == "PASSED", material_row
    assert material_row["readback"]["DB.MATL"]["present"] is True, material_row["readback"]
    accepted = next(
        item
        for item in material_row["requests"]
        if item["method"] == "POST" and str(item["path"]).endswith("/DB/MATL")
    )
    assert int(accepted["status"]) == 200, accepted
    entry = accepted["body"]["Assign"]["1"]
    assert entry["TYPE"] == "STEEL", entry
    assert entry["NAME"] == "Q355", entry
    param = entry["PARAM"][0]
    assert param["P_TYPE"] == 1, param
    assert param["STANDARD"] == "GB50017-17(S)", param
    assert param["DB"] == "Q355", param
    assert param["CODE"] == "", param
    assert param["bELAST"] is False, param
    # ⚠️ 单位：对话框显示 `2.0600e+08 kN/m²` ⇒ `ELAST` 按 **kN/m²** 发（**不**是 Pa）
    assert float(param["ELAST"]) == 206_000_000.0, param
    # 规范库路线**不**给属性值
    assert "POISN" not in param and "DEN" not in param, param


def test_p157_r133_the_material_unit_convention_is_unresolved() -> None:
    """门槛（**R133**，**如实登记**）：`DB.MATL` 的**单位口径**在 canonical 侧**未**定义。

    * 上游手册 `Standard` 示例的 `ELAST` = `210000000` —— 与 GEN NX「材料数据」对话框一致
      （**kN/m²**；选 `Q355` 后自动带出 `2.0600e+08`）；
    * 用户自定义示例的 `DEN` = `76.98`（**kN/m³**）；
    * ⚠️ 而**写路径探针**（`probe_interface_paths._material_parameters`）发的是
      `elastic_modulus = 2.1e11`（**Pa**）与 `density = 7850.0`（**kg/m³**）⇒ 量纲差
      **1000× / 100×**。原生**不**校验量级 ⇒ 两者都 `200`，但**工程含义不同**。

    ⇒ 本批**只**登记（**未**改探针、**未**改 canonical）："canonical 的长度 / 质量单位"
    属**契约**决定。⚠️ 本文件的旗舰链**按 UI 口径**发（`kN/m²`），并在此**逐条**钉住差异。
    """
    standard = _matl_examples()["Standard"]["Assign"]["1"]["PARAM"][0]
    assert float(standard["ELAST"]) == 210_000_000.0, standard  # kN/m²
    user = _matl_examples()["Isotropic - User Defined"]["Assign"]["5"]["PARAM"][0]
    assert float(user["DEN"]) == pytest.approx(76.98), user  # kN/m³
    # 写路径探针发的是 Pa / kg·m⁻³（量纲差 1000× / 100×）—— 如实钉住**现状**
    probe = _load(PROBE_TOOL, "structai_probe_interface_paths_p157_units")
    material = probe._material_parameters("1")["materials"][0]  # noqa: SLF001 - 判定点
    assert float(material["elastic_modulus"]) == 210_000_000_000.0, material
    assert float(material["density"]) == 7850.0, material
    # 本文件的旗舰链**按 UI 口径**发（kN/m²）
    chain_material = _step(_chain(), "substituted", "MODEL.MATERIAL.ASSIGN")
    accepted = next(
        item for item in chain_material["requests"] if str(item["path"]).endswith("/DB/MATL")
    )
    assert float(accepted["body"]["Assign"]["1"]["PARAM"][0]["ELAST"]) == 206_000_000.0


# ===== 2. 阶段 B：①′ 通过（建模链是通的）=====


def test_p157_the_substituted_prefix_builds_the_model() -> None:
    """门槛：①′ 的 **6** 步**全部** `PASSED`（材质 / 截面 / 2 节点 / 单元 / **柱底固定**）。

    ⚠️ **R134（P157）**：第 **6** 步 `MODEL.BOUNDARY.ASSIGN`（柱底固定）是**必需**的 ——
    `docs/07` §13.5 的提示词写「柱底固定」，而 §6.5 给 `BUILD.COLUMN` 的组合**不含** `DB.CONS`
    ⇒ 没有它，`POST /DOC/ANAL` 会被原生拒绝 **`[错误] 边界条件 没有定义。`**（实测）。
    """
    document = _chain()
    assert [str(row["operation"]) for row in document["substituted"]] == list(SUBSTITUTE_OPERATIONS)
    assert document["substitute_reason"], document
    prefix = document["substituted"][:6]
    assert [str(row["status"]) for row in prefix] == ["PASSED"] * 6, prefix
    for row in prefix:
        assert not row["error"], row
        assert not _rejections(row), row
        for endpoint, snapshot in row["readback"].items():
            assert snapshot["present"] is True, (endpoint, snapshot)
    assert document["substituted_counts"] == {"PASSED": 11}
    assert document["substituted_verdict"] == "PASSED"


def test_p157_r132_the_load_case_is_created_then_the_load_is_assigned() -> None:
    """门槛（**R132 已闭环**，有实测依据）：`MODEL.LOAD.ASSIGN` **先建工况、再加载荷**。

    `select_steps` 在调用方**显式**给了 `load_case_definition` 时返回
    `(DB.STLD 步, 荷载步)` ⇒ 两条请求**逐条**进证据，且**两个**端点都**再读确认在**
    （R128：外层键无效时原生静默 `200` 却不建 ⇒ 判据**必须**以再读为准）。
    """
    load = _step(_chain(), "substituted", "MODEL.LOAD.ASSIGN")
    assert load["status"] == "PASSED", load
    assert not load["error"], load["error"]
    assert load["readback"]["DB.STLD"]["present"] is True, load["readback"]
    assert load["readback"]["DB.CNLD"]["present"] is True, load["readback"]
    posts = [
        item
        for item in load["requests"]
        if item["method"] == "POST" and str(item["path"]).rsplit("/", 1)[-1] in {"STLD", "CNLD"}
    ]
    assert [str(item["path"]).rsplit("/", 1)[-1] for item in posts] == ["STLD", "CNLD"], posts
    assert [int(item["status"]) for item in posts] == [200, 200], posts
    entry = posts[0]["body"]["Assign"]["1"]
    assert entry["NAME"] == "AXIAL", entry
    assert entry["TYPE"] == "D", entry  # 手册示例 / P150 实测可用的取值
    # 荷载条目的外层键 = **柱顶节点编号**（R128）
    assert list(posts[1]["body"]["Assign"]) == [str(TOP_NODE)], posts[1]["body"]


def test_p157_r134_the_fixed_base_is_created_with_a_seven_digit_constraint() -> None:
    """门槛（**R134**）：①′ 第 **6** 步 = **柱底固定**，`CONSTRAINT` **7** 位（D2 = A 的真机落地）。

    ⚠️ 没有这一步时 `POST /DOC/ANAL` 被原生拒绝 **`[错误] 边界条件 没有定义。`**（实测）。
    """
    boundary = _step(_chain(), "substituted", "MODEL.BOUNDARY.ASSIGN")
    assert boundary["status"] == "PASSED", boundary
    assert boundary["readback"]["DB.CONS"]["present"] is True, boundary["readback"]
    post = next(item for item in boundary["requests"] if str(item["path"]).endswith("/DB/CONS"))
    assert int(post["status"]) == 200, post
    outer = post["body"]["Assign"]
    entry = outer[next(iter(outer))]["ITEMS"][0]
    constraint = str(entry["CONSTRAINT"])
    assert len(constraint) == 7, entry  # 7 位 = DX,DY,DZ,RX,RY,RZ,RW
    assert constraint == "1111110", entry  # 六自由度全约束；rw=False（不臆造 True）


def test_p157_r135_the_result_query_must_not_filter_by_load_case() -> None:
    """门槛（**R135**）：取结果**不**带 `LOAD_CASE_NAMES` 过滤，且**实测取到了真实数值**。

    ⚠️ 实测：带 `{"LOAD_CASE_NAMES": ["AXIAL"]}` 时原生回 **`200 {}`**（空对象 ⇒
    `parse_table` 报 `result_shape_invalid`）；**去掉过滤**后同一端点返回真表
    （信封根键 = `"empty"`）⇒ 这是**探针参数**问题，**不**是端点问题。
    ⚠️ **数值不硬编码**：逐条取自响应。
    """
    row = _step(_chain(), "substituted", "RESULT.NODE.DISPLACEMENT")
    assert row["status"] == "PASSED", row
    post = next(item for item in row["requests"] if str(item["path"]).endswith("/POST/TABLE"))
    assert int(post["status"]) == 200, post
    assert "LOAD_CASE_NAMES" not in post["body"]["Argument"], post["body"]
    assert row["attempts"] == 1, row  # 去掉过滤后**一次**就拿到（无需重试）
    numbers = row["numbers"]
    for name in ("displacement.ux", "displacement.uy", "displacement.uz"):
        assert isinstance(numbers.get(name), float), numbers
    assert numbers["displacement.uz"] != 0.0, numbers


def test_p157_r136_r137_r141_the_whole_chain_passes_eleven_of_eleven() -> None:
    """门槛（**五步链在真机上 11/11 全绿**）：配置 → 验算 → 取表，全部 `200`。

    **R136**（用户裁决 = B）：新增 `MODEL.LOAD_COMBINATION.ASSIGN`（Operation **69 → 70**）。
    **R137**（✅）：组合取值 = **厂商真值** `ANAL: "ST"`（**只读**读回官方验证模型
    `Static-01.mgbx`）；组合是**分析的输入** ⇒ 必须先于 `DOC.ANAL`。
    **R138**（✅）：12 个 `DESIGN.*.*-TABLE` 的 `wrapper.write` 由 `Assign` 修为 **`Argument`**
    （45 处全库一并修 + 加全库闸门）。
    **R141**（✅，**手册驱动**）：`DESIGN.STEEL` 的前四步（`DSTL` / `DCO` / `DCTL` / `MEMB`）
    手册方法是 **`GET, PUT, DELETE`** —— 它们是**配置**入口；原编排当 `GET` 读 ⇒ 设计**从未被配置**
    （尤其**构件指派** `MEMB`）⇒ MIDAS 验算对话框报 `Error occured while setting unit`、阻塞 API、
    应用崩溃。现按手册改为 **PUT 配置 → `CODE-ANAL` → `CODE-TABLE`**（端点集不变）。
    """
    document = _chain()
    assert document["substituted_verdict"] == "PASSED", document
    assert document["substituted_counts"] == {"PASSED": 11}, document

    design = _step(document, "substituted", "DESIGN.STEEL")
    assert design["status"] == "PASSED", design
    assert not design["error"], design["error"]
    calls = [
        (str(i["path"]).rsplit("/", 1)[-1], i["method"], int(i["status"]))
        for i in design["requests"]
    ]
    assert calls == [
        ("DSTL", "PUT", 200),
        ("DCO", "PUT", 200),
        ("DCTL", "PUT", 200),
        ("MEMB", "PUT", 200),
        ("CODE-ANAL", "POST", 200),
        ("CODE-TABLE", "POST", 200),
    ], calls
    # ⚠️ **构件指派**是原先缺的那一步（手册方法 `GET, PUT, DELETE`）
    memb = next(i for i in design["requests"] if str(i["path"]).endswith("/MEMB"))
    assert memb["body"] == {"Assign": {"1": {"AELEM": [ELEMENT_ID], "bREVERSE": False}}}, memb[
        "body"
    ]
    # ⚠️ 验算体照手册示例；结果表体照手册 STEEL 示例（`TABLE_TYPE: "PROP"` + `ELEMS.KEYS`）
    anal = next(i for i in design["requests"] if str(i["path"]).endswith("/CODE-ANAL"))
    assert anal["body"] == {"Argument": {"PERFORM_TYPE": "ALL"}}, anal["body"]
    table = next(i for i in design["requests"] if str(i["path"]).endswith("/CODE-TABLE"))
    assert table["body"]["Argument"]["TABLE_TYPE"] == "PROP", table["body"]
    assert table["body"]["Argument"]["ELEMS"] == {"KEYS": [ELEMENT_ID]}, table["body"]


def test_p157_the_run_left_no_residue_and_the_sentinels_agree() -> None:
    """门槛：**零残留** + 跑前 / 跑中 / 跑后哨兵**一致且全空**（R119）。

    ⚠️ `analysis_result_persists` 现在是 **`False`**（**不**再是 `None`）：③ **真的跑了**，
    收尾清理删掉模型之后 `POST.TABLE` 重新变成**错误**（模型没了 ⇒ 结果不可取）——
    **不**声称「分析结果已被清掉」，只声称**当前不可取**。
    """
    document = _chain()
    assert document["residue"] == {}, document["residue"]
    assert tuple(document["sentinel_endpoints"]) == SENTINEL_ENDPOINTS
    for key in ("sentinel_before", "sentinel_mid", "sentinel_after"):
        snapshot = document[key]
        assert sorted(snapshot) == sorted(SENTINEL_ENDPOINTS), key
        for endpoint, value in snapshot.items():
            assert int(value["status"]) == 200, (key, endpoint, value)
            assert value["ids"] == [], (key, endpoint, value)
    assert document["sentinel_before"] == document["sentinel_after"]
    for phase in ("cleanup_mid", "cleanup"):
        for item in document[phase]:
            assert item["gone"] is True, (phase, item)
    assert document["analysis_result_persists"] is False, document["analysis_result_persists"]
    analysis = _step(document, "substituted", "ANALYSIS.STATIC")
    assert analysis["status"] == "PASSED", analysis
    assert str(analysis["task"]["status"]) == "COMPLETED", analysis["task"]


def test_p157_the_evidence_never_carries_credentials() -> None:
    """门槛（`docs/07` §14.3）：证据里**没有**凭据形态。"""
    raw = CHAIN_EVIDENCE.read_text(encoding="utf-8")
    for marker in ("MAPI-Key", "MAPI_KEY", "mapi-key", "password", "secret"):
        assert marker not in raw, marker


def test_p157_the_check_mode_agrees_offline() -> None:
    """门槛：`probe_flagship_chain --check` 离线跑通（退出码 0）。"""
    result = subprocess.run(
        [sys.executable, str(CHAIN_TOOL), "--check"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "旗舰链证据自洽" in result.stdout


# ===== 5. 不变量（本批**不得**放宽既有判定）=====


def test_p157_the_invariants_are_untouched() -> None:
    """门槛：数据侧分母 / 缺口 / 写路径与读路径子桶**一行未变**。"""
    registry = MidasRegistry.load(REPO_ROOT / "registry")
    coverage = write_path_coverage(registry, [])
    assert coverage.ratio == f"0 / {EXPECTED_WRITE_PATH_TOTAL}"
    assert coverage.model_write_ratio == f"0 / {EXPECTED_MODEL_WRITE_TOTAL}"
    gap = _json(GAP_EVIDENCE)
    assert int(gap["gap_total"]) == EXPECTED_GAP_TOTAL
    assert len(gap["gap_three_step"]) == EXPECTED_GAP_NOT_IN_CONTRACT
    assert len(gap["gap_no_readback"]) == EXPECTED_GAP_NO_READBACK
    assert _json(WRITE_EVIDENCE)["counts"] == EXPECTED_WRITE_COUNTS
    assert _json(READ_EVIDENCE)["counts"] == EXPECTED_READ_COUNTS


def test_p157_the_chain_probe_is_bounded_and_declares_its_cleanup_order() -> None:
    """门槛：探针**有界**且**逆序**清理 —— 纪律参数可被**读出**（本用例**不**重跑请求）。"""
    tool = _load(CHAIN_TOOL, "structai_probe_flagship_chain_p157_bounded")
    assert tool.MAX_REQUESTS <= 200
    assert len(tool.SPEC_STEPS) == 5
    assert [str(step["operation"]) for step in tool.SPEC_STEPS] == list(SPEC_OPERATIONS)
    assert tool.PASSED == "PASSED"
    # 逆序：依赖方在前、被依赖方在后
    order = [endpoint for endpoint, _operation, _extra in tool.CLEANUP_ORDER]
    assert order == [
        "DB.LCOM-STEEL",
        "DB.CNLD",
        "DB.CONS",
        "DB.ELEM",
        "DB.NODE",
        "DB.MATL",
        "DB.SECT",
        "DB.STLD",
    ], order
    # ⚠️ 工况**没有**接口层创建路径（R132）⇒ 清理里**有**它（删除侧存在）
    assert "DB.STLD" in order
    assert tool.SENTINEL_ENDPOINTS == SENTINEL_ENDPOINTS
