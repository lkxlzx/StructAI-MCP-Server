"""Fix the two defects my encoding patcher introduced:
1. `import sys` inserted before `import argparse` (breaks isort / I001) in 3 files.
2. probe_flagship_chain.py's CRLF line endings converted to LF.
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
TOOLS = Path(r"E:\MCP\MMCP\registry\tools")

FIXES = {
    "probe_boundary_shape.py": (
        "from __future__ import annotations\n\nimport sys\nimport argparse\nimport json\nimport os\nimport pathlib\nfrom typing import Any\n",
        "from __future__ import annotations\n\nimport argparse\nimport json\nimport os\nimport pathlib\nimport sys\nfrom typing import Any\n",
    ),
    "probe_constraint_value.py": (
        "from __future__ import annotations\n\nimport sys\nimport argparse\nimport json\nimport os\nimport pathlib\nfrom typing import Any\n",
        "from __future__ import annotations\n\nimport argparse\nimport json\nimport os\nimport pathlib\nimport sys\nfrom typing import Any\n",
    ),
    "probe_flagship_chain.py": (
        "from __future__ import annotations\n\nimport sys\nimport argparse\nimport asyncio\nimport importlib.util\nimport json\nimport os\nimport pathlib\nimport tempfile\nfrom typing import Any\n",
        "from __future__ import annotations\n\nimport argparse\nimport asyncio\nimport importlib.util\nimport json\nimport os\nimport pathlib\nimport sys\nimport tempfile\nfrom typing import Any\n",
    ),
}

for name, (old, new) in FIXES.items():
    p = TOOLS / name
    text = p.read_text(encoding="utf-8")
    if text.count(old) != 1:
        print(f"  !! {name}: pattern found {text.count(old)} times")
        continue
    p.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    print(f"  FIXED import order: {name}")

# restore CRLF for the one file that had it
p = TOOLS / "probe_flagship_chain.py"
text = p.read_text(encoding="utf-8")
p.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
print("  RESTORED CRLF: probe_flagship_chain.py")
