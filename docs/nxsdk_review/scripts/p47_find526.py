"""Find every text file in the repo whose byte at offset 526 is 0xa1 (the decode failure point)."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
SKIP = {".git", ".venv", ".tmp_nxsdk", ".tmp_analysis", "__pycache__", ".mypy_cache",
        ".pytest_cache", ".ruff_cache", "node_modules", "data"}

hits = []
for p in REPO.rglob("*"):
    if not p.is_file():
        continue
    if any(part in SKIP for part in p.parts):
        continue
    try:
        raw = p.read_bytes()
    except OSError:
        continue
    if len(raw) > 526 and raw[526] == 0xA1:
        hits.append(p)
    # also: any file that is not valid utf-8
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        if 500 < exc.start < 560:
            hits.append(p)

print(f"candidates: {len(hits)}")
for p in hits:
    print("  ", p.relative_to(REPO))
