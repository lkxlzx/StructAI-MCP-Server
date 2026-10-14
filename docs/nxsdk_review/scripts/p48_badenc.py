"""Find every file in the repo that is NOT valid UTF-8 (excluding vendored/venv dirs)."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
SKIP = {".git", ".venv", ".tmp_nxsdk", ".tmp_analysis", "__pycache__", ".mypy_cache",
        ".pytest_cache", ".ruff_cache", "node_modules", "data", "archive"}

bad = []
for p in REPO.rglob("*"):
    if not p.is_file():
        continue
    if any(part in SKIP for part in p.parts):
        continue
    if p.suffix in {".pyc", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".zip", ".whl",
                    ".db", ".sqlite", ".sqlite3", ".xlsx", ".docx", ".pdf"}:
        continue
    try:
        p.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        bad.append((p, exc))

print(f"files that are NOT valid UTF-8: {len(bad)}")
for p, exc in bad:
    print(f"  {p.relative_to(REPO)}")
    print(f"      {exc}")
