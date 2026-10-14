"""Find every file under registry/ that is not valid UTF-8 (a cp936 write on this Windows box)."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REG = Path(r"E:\MCP\MMCP\registry")

bad = []
for p in sorted(REG.rglob("*")):
    if not p.is_file() or "__pycache__" in p.parts or p.suffix == ".pyc":
        continue
    raw = p.read_bytes()
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        bad.append((p, str(exc), raw[:8]))

print(f"files under registry/ that are NOT valid UTF-8: {len(bad)}")
for p, exc, head in bad:
    print(f"  {p.relative_to(REG)}")
    print(f"      {exc}")
    print(f"      first bytes: {head}")
