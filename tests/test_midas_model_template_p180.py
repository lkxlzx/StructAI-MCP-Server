"""P180：参数化模型模板（`model_template.py`）的**离线**判定（零请求）。

为什么需要它
------------
「模板能导入」是探针的判据；本文件钉住**模板层本身**的口径：

| # | 事实 | 为什么必须机器可读 |
| --- | --- | --- |
| 1 | **往返无损** | 模板漏一张隐藏表 ⇒ 导入后模型**行为变了**但看不出来 |
| 2 | **排除 `PJCF` / `CO_*`** | 导入 `PJCF` 会把样本的项目名写进当前项目（合并语义） |
| 3 | **序列化稳定** | 不稳定 ⇒ 模板无法 diff / 无法做回归基线 |
| 4 | **未知参数 / 类型不匹配报错** | 静默忽略覆盖值 = 用户以为改了，实际没改（假绿） |
| 5 | **模板库齐全** | 156 个官方样本逐个可建模板且 `--check` 全绿 |

⚠️ 本批**不**改任何 Operation 裁定（不新增 / 不改 `OPERATION_PLANS`）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

import pytest

from app.infrastructure.adapters.midas.model_template import (
    EXCLUDED_TABLES,
    NODE_PARAM_LIMIT,
    SUPPORT_PARAM_LIMIT,
    TEMPLATE_FORMAT,
    TEMPLATE_VERSION,
    MaterializeError,
    build_template,
    dumps_template,
    materialize,
    parameter_values,
)

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
EXPORTS: Final[Path] = REPO_ROOT / ".tmp_p180" / "exports"
TEMPLATES: Final[Path] = REPO_ROOT / "templates" / "gen_verification"
INDEX: Final[Path] = TEMPLATES / "index.json"

SAMPLE: Final[Path] = EXPORTS / "Static-02.json"


def _require_sample() -> dict:
    """读样本导出（缺失 ⇒ skip，不伪造数据）。"""
    if not SAMPLE.is_file():
        pytest.skip(f"缺导出样本 {SAMPLE}（先跑 export_gen_verification_p180.py --probe）")
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def _template() -> dict:
    return build_template(_require_sample(), name="Static-02", family="Static")


# ===== 1. 往返无损 =====


def test_p180_template_roundtrip_is_lossless_except_excluded_tables() -> None:
    """门槛 ①：`materialize(build_template(x))` 与 `x` **逐表一致**（排除会话表）。"""
    source = _require_sample()["DBG"]
    rebuilt = materialize(_template())["DBG"]
    for table, rows in source.items():
        if table in EXCLUDED_TABLES:
            assert table not in rebuilt, f"{table} 不应进模板"
            continue
        assert rebuilt.get(table) == rows, f"表 {table} 往返不一致"


def test_p180_excluded_tables_are_session_state_not_model_data() -> None:
    """门槛 ②：`PJCF` / `CO_*` 不进模板 —— 导入它们会污染当前项目。"""
    template = _template()
    for table in EXCLUDED_TABLES:
        assert table not in template["model"]


# ===== 2. 序列化稳定 =====


def test_p180_serialization_is_byte_stable() -> None:
    """门槛 ③：同一模板序列化两次**逐字节相同**。"""
    template = _template()
    assert dumps_template(template) == dumps_template(json.loads(json.dumps(template)))
    assert dumps_template(template).endswith("\n")


# ===== 3. 参数覆盖真的落进 DBG =====


def test_p180_overrides_land_in_the_right_native_fields() -> None:
    """改参数 ⇒ 生成的 `DBG` 在**对应原生字段**上就是新值（不是只改了参数表）。"""
    template = _template()
    available = parameter_values(template)
    assert "material.1.elastic_modulus" in available
    rebuilt = materialize(template, {"material.1.elastic_modulus": 7777777.0})["DBG"]
    param = rebuilt["MATL"]["1"]["PARAM"][0]
    assert param["ELAST"] == 7777777.0
    # 未覆盖的参数保持默认值
    assert rebuilt["SECT"]["1"]["SECT_NAME"] == available["section.1.name"]


def test_p180_node_coordinates_are_parameterized_for_small_models_only() -> None:
    """小模型逐坐标参数化；大模型超过阈值后保留字面值（模板可读性）。"""
    source = _require_sample()["DBG"]
    node_count = len(source.get("NODE") or {})
    template = _template()
    if node_count <= NODE_PARAM_LIMIT:
        assert any(name.startswith("node.") for name in parameter_values(template))
    else:
        assert not any(name.startswith("node.") for name in parameter_values(template))
    assert NODE_PARAM_LIMIT > 0
    assert SUPPORT_PARAM_LIMIT > 0


# ===== 4. 严格性 =====


def test_p180_unknown_override_is_an_error_not_silently_ignored() -> None:
    """门槛 ④：未知参数**报错**（静默忽略 = 用户以为改了，实际没改）。"""
    with pytest.raises(MaterializeError, match="未知参数"):
        materialize(_template(), {"no.such.parameter": 1})


def test_p180_type_mismatch_is_an_error_not_coerced() -> None:
    """类型不匹配**报错**（把字符串塞进数值字段会在导入时才失败，归因困难）。"""
    with pytest.raises(MaterializeError, match="需要 number"):
        materialize(_template(), {"material.1.elastic_modulus": "not-a-number"})


def test_p180_unknown_format_or_version_is_rejected() -> None:
    """格式 / 版本不认识 ⇒ **报错不猜**（与 `model_document.from_json` 同口径）。"""
    template = _template()
    with pytest.raises(MaterializeError, match="未知模板格式"):
        materialize({**template, "format": "something.else"})
    with pytest.raises(MaterializeError, match="不支持的模板版本"):
        materialize({**template, "version": TEMPLATE_VERSION + 1})


def test_p180_unknown_placeholder_in_model_is_rejected() -> None:
    """`model` 里出现未登记占位符 ⇒ 报错（说明模板被手改坏了）。"""
    template = _template()
    template["model"]["NODE"]["999"] = {"X": "${ghost}", "Y": 0.0, "Z": 0.0}
    with pytest.raises(MaterializeError, match="未知参数"):
        materialize(template)


def test_p180_template_constants_are_pinned() -> None:
    """格式标识 / 版本是**对外契约**：改动必须走版本 +1。"""
    assert TEMPLATE_FORMAT == "structai.model_template"
    assert TEMPLATE_VERSION == 1


# ===== 5. 模板库齐全（156 个官方样本） =====


def test_p180_template_library_covers_every_exported_sample() -> None:
    """模板库与导出快照**一一对应**（少一个 ⇒ 那一族没有可复用的模板）。"""
    if not INDEX.is_file():
        pytest.skip(f"缺模板索引 {INDEX}（先跑 model_template_p180.py --build）")
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    exports = {path.stem for path in EXPORTS.glob("*.json")}
    covered = {str(entry["name"]) for entry in index["templates"]}
    assert index["count"] == len(covered)
    assert exports <= covered, f"缺模板：{sorted(exports - covered)}"


def test_p180_every_template_materializes_to_a_full_dbg() -> None:
    """每个模板都能 `materialize` 出含 `DBG` 的 JSON，且表数 == 索引里的表数。"""
    if not INDEX.is_file():
        pytest.skip(f"缺模板索引 {INDEX}")
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    for entry in index["templates"]:
        template = json.loads((TEMPLATES / entry["file"]).read_text(encoding="utf-8"))
        payload = materialize(template)
        assert set(payload) == {"DBG"}
        assert len(payload["DBG"]) == entry["tables"]
        assert len(parameter_values(template)) == entry["parameters"]
