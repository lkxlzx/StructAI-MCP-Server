"""Check whether the YAML/schema files edited by the import tool changed line-ending style."""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")

files = subprocess.run(["git", "diff", "--name-only"], cwd=REPO,
                       capture_output=True, encoding="utf-8").stdout.split()

bad = []
for rel in files:
    p = REPO / rel
    if not p.is_file():
        continue
    before = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=REPO, capture_output=True).stdout
    now = p.read_bytes()
    b, n = before.count(b"\r\n"), now.count(b"\r\n")
    if (b > 0) != (n > 0):
        bad.append((rel, b, n))

print(f"files whose line-ending style changed: {len(bad)}")
for rel, b, n in bad:
    print(f"  {rel}   HEAD CRLF={b}  now CRLF={n}")
