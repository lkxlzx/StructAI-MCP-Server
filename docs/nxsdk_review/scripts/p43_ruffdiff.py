"""Find the genuinely-new ruff violation (ignoring line-number shifts)."""
import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
PY = sys.executable


def run() -> list[str]:
    r = subprocess.run([PY, "-m", "ruff", "check", "registry/tools", "--output-format", "concise"],
                       cwd=REPO, capture_output=True, encoding="utf-8", errors="replace")
    out = []
    for line in r.stdout.splitlines():
        m = re.match(r"^(.*?):\d+:\d+: (\S+.*)$", line)
        if m:
            out.append(f"{m.group(1)} :: {m.group(2)}")
    return sorted(out)


now = run()
print(f"current violations (line-numbers normalised): {len(now)}")
for item in now:
    if "reconfigure" in item or "cp949" in item or "UnicodeEncodeError" in item:
        print("  MINE:", item)
print()
print("first 5:", *now[:5], sep="\n  ")
