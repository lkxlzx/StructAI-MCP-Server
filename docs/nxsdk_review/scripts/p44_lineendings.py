"""Detect which registry tool files had their line endings changed by the encoding patch."""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")


def head_bytes(rel: str) -> bytes | None:
    r = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=REPO,
                       check=False, capture_output=True)
    return r.stdout if r.returncode == 0 else None


print(f"{'file':44s} {'HEAD':>6s} {'now':>6s}  changed?")
crlf_files = []
for p in sorted((REPO / "registry" / "tools").glob("*.py")):
    rel = p.relative_to(REPO).as_posix()
    before = head_bytes(rel)
    if before is None:
        continue
    now = p.read_bytes()
    b_crlf = before.count(b"\r\n")
    n_crlf = now.count(b"\r\n")
    changed = "YES" if (b_crlf > 0) != (n_crlf > 0) else ""
    if changed:
        crlf_files.append((rel, b_crlf, n_crlf))
    print(f"  {p.name:42s} {b_crlf:6d} {n_crlf:6d}  {changed}")

print()
print(f"files whose line-ending style changed: {len(crlf_files)}")
for rel, b, n in crlf_files:
    print(f"  {rel}  HEAD CRLF={b} -> now CRLF={n}")
