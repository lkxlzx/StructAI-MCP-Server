"""Compute the new candidate key lists per product (for p143's CIVIL_CODES) and the counts."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO))

import midas_p119_p126_support as support  # noqa: E402

from app.infrastructure.adapters.midas.transforms import TRANSFORMER_REGISTRY  # noqa: E402
from app.infrastructure.adapters.midas.write_probe import (  # noqa: E402
    WRITE_METHODS,
    transformer_name_for,
)

registry = support.registry()

for product in ("GEN_NX", "CIVIL_NX", "CIVIL_DESIGNER"):
    keys = []
    blocked = 0
    for key in registry.keys():
        d = registry.endpoint(key)
        if product not in d.products or not d.enabled:
            continue
        methods = registry.methods_for(key=key, product=product)
        if not any(m in methods for m in WRITE_METHODS):
            continue
        try:
            resolved = registry.resolve(key=key, product=product)
        except Exception:  # noqa: BLE001
            continue
        if d.destructive or resolved.delete_all_via_body:
            continue
        has_source = (
            TRANSFORMER_REGISTRY.get(transformer_name_for(key)) is not None
            or registry.write_template(key) is not None
        )
        if not has_source:
            blocked += 1
            continue
        if "GET" not in methods or not d.read_root or "DELETE" not in methods:
            continue
        keys.append(key)
    print(f"--- {product}: candidates={len(keys)} blocked={blocked} ---")
    if product != "GEN_NX":
        for k in sorted(keys):
            print(f'    "{k}",')
