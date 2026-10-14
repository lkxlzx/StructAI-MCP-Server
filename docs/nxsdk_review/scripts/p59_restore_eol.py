"""Restore the original CRLF line endings on files my scripts rewrote with LF."""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")

changed = subprocess.run(["git", "diff", "--name-only"], cwd=REPO,
                         capture_output=True, encoding="utf-8").stdout.split()

restored = []
for rel in changed:
    p = REPO / rel
    if not p.is_file():
        continue
    before = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=REPO, capture_output=True).stdout
    if before.count(b"\r\n") == 0:
        continue  # HEAD 就是 LF，无需恢复
    now = p.read_bytes()
    if now.count(b"\r\n") > 0:
        continue  # 已是 CRLF
    text = now.decode("utf-8").replace("\r\n", "\n")
    p.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    restored.append(rel)

print(f"restored CRLF on {len(restored)} files:")
for rel in restored:
    print("  ", rel)

# re-verify
bad = []
for rel in changed:
    p = REPO / rel
    if not p.is_file():
        continue
    before = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=REPO, capture_output=True).stdout
    now = p.read_bytes()
    if (before.count(b"\r\n") > 0) != (now.count(b"\r\n") > 0):
        bad.append(rel)
print()
print(f"files still with a changed line-ending style: {len(bad)}")
for rel in bad:
    print("  ", rel)
