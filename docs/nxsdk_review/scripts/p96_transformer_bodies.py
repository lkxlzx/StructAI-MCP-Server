"""P164-c 静态校验：RC / SRC 配置转换器产出的**原生体** vs 手册示例（零请求）。

这一步把「我改的代码」与「数据侧记录的手册示例」对上 —— 如果两者一致，
那么接口层 PUT 出去的就是手册示例那个体。
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
sys.path.insert(0, str(REPO / "tests"))

import midas_p119_p126_support as support  # noqa: E402

from app.infrastructure.adapters.midas.transforms import TRANSFORMER_REGISTRY  # noqa: E402

registry = support.registry()
templates = json.loads((REPO / "registry" / "live" / "write_templates.json").read_text(encoding="utf-8"))[
    "templates"
]

CASES = (
    ("midas.design.rc-code.v1", "DESIGN.RC.DRC", "DESIGN.RC.DRC"),
    ("midas.design.rc-option.v1", "DESIGN.RC.KDS-41-20-2022.DCO", "DESIGN.RC.KDS-41-20-2022.DCO"),
    ("midas.design.rc-frame.v1", "DESIGN.RC.KDS-41-20-2022.DCTL", "DESIGN.RC.KDS-41-20-2022.DCTL"),
    ("midas.design.rc-member.v1", "DESIGN.RC.KDS-41-20-2022.MEMB", "DESIGN.RC.KDS-41-20-2022.MEMB"),
    ("midas.design.src-option.v1", "DESIGN.SRC.AIK-SRC2K.DCO", "DESIGN.SRC.AIK-SRC2K.DCO"),
    ("midas.design.src-frame.v1", "DESIGN.SRC.AIK-SRC2K.DCTL", "DESIGN.SRC.AIK-SRC2K.DCTL"),
    ("midas.design.src-member.v1", "DESIGN.SRC.AIK-SRC2K.MEMB", "DESIGN.SRC.AIK-SRC2K.MEMB"),
    ("midas.design.dstl.v1", "DESIGN.STEEL.DSTL", "DESIGN.STEEL.DSTL"),
    ("midas.design.dco.v1", "DESIGN.STEEL.KDS-41-30-2022.DCO", "DESIGN.STEEL.KDS-41-30-2022.DCO"),
)

for transformer_name, endpoint, template_key in CASES:
    cls = TRANSFORMER_REGISTRY[transformer_name]
    transformer = cls(registry)
    manual = (templates.get(template_key) or {}).get("body")
    print("=" * 92)
    print(f"{transformer_name}  →  {endpoint}")
    print(f"  wrapper_key = {transformer.wrapper_key()!r}")
    print(f"  手册示例: {json.dumps(manual, ensure_ascii=False)[:260] if manual else '(无模板)'}")
    if not manual:
        print("  ⇒ 无手册示例可比（跳过产出比对）")
        continue
    # 手册示例用的是**原生**字段名；`to_native` 要的是 **canonical** ⇒ 先按字段表反向映射
    canonical = {f.canonical: manual[f.native] for f in cls.fields if f.native in manual}
    missing = [f.native for f in cls.fields if f.native not in manual]
    try:
        native = transformer.to_native(canonical)
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️ to_native 抛错: {type(exc).__name__}: {exc}")
        continue
    print(f"  接口层产出: {json.dumps(native, ensure_ascii=False)[:300]}")
    # 逐字段比对：接口层产出的原生体 vs 手册示例
    covered = {f.native for f in cls.fields}
    only_manual = sorted(k for k in manual if k not in covered and k not in ("CMD", "ID", "id"))
    print(f"  字段表**未覆盖**手册示例的键: {only_manual if only_manual else '（无）'}")
    print(f"  手册示例有而字段表无: {missing if missing else '（无）'}")
    print()
