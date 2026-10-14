"""Debug why _logic_unchanged_since_head still reports a difference for check_write_templates.py."""
import difflib
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO_ROOT = Path(r"E:\MCP\MMCP")
MARKERS = ("reconfigure", "cp949", "UnicodeEncodeError")


def strip(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines()
        if line.strip() and not any(m in line for m in MARKERS)
    )


path = REPO_ROOT / "registry" / "tools" / "check_write_templates.py"
rel = path.relative_to(REPO_ROOT).as_posix()
result = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=REPO_ROOT,
                        check=False, capture_output=True, encoding="utf-8")
print("git show rc:", result.returncode)
before = strip(result.stdout)
after = strip(path.read_text(encoding="utf-8"))
print("equal after strip:", before == after)
if before != after:
    diff = list(difflib.unified_diff(before.splitlines(), after.splitlines(),
                                     "HEAD", "now", lineterm="", n=2))
    print(f"diff lines: {len(diff)}")
    for line in diff[:40]:
        print("   ", repr(line))
