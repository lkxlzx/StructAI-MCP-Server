"""Compute the new pinned candidate/blocked counts using the project's own registry + tool logic."""
import importlib.util
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
print("registry keys:", len(registry.keys()))


def counts(product: str) -> tuple[int, int]:
    candidates = 0
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
        except Exception:
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
        candidates += 1
    return candidates, blocked


for p in ("GEN_NX", "CIVIL_NX", "CIVIL_DESIGNER"):
    c, b = counts(p)
    print(f"  {p:16s} candidates={c:4d}  blocked={b:4d}")

print()
print("--- -M1 endpoints now on CIVIL_NX only ---")
m1 = [k for k in registry.keys() if k.endswith("-M1")]
print(f"  count={len(m1)}  first={m1[0]}")
for p in ("GEN_NX", "CIVIL_NX"):
    print(f"  {p}: " + ", ".join(f"{k}={p in registry.endpoint(k).products}" for k in m1[:3]))
