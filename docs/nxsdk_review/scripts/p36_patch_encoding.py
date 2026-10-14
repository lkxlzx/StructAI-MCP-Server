"""Add the UTF-8 stdout/stderr guard to every registry tool that lacks it.

Windows consoles default to cp949/cp936. Tools that print Chinese or emoji raise
UnicodeEncodeError when their stdout is captured by `subprocess.run(..., encoding="utf-8")`,
which is exactly how the test suite invokes them — 13 tests fail for this reason alone.
"""
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

TOOLS = Path(r"E:\MCP\MMCP\registry\tools")
WRITE = "--write" in sys.argv

GUARD = (
    "\n"
    "# Windows 控制台默认 cp949/cp936：本工具会打印中文/符号，不重设编码会 UnicodeEncodeError，\n"
    "# 且在 `subprocess.run(..., encoding=\"utf-8\")` 捕获时会让断言标记匹配失败。\n"
    "if hasattr(sys.stdout, \"reconfigure\"):\n"
    "    sys.stdout.reconfigure(encoding=\"utf-8\")\n"
    "    sys.stderr.reconfigure(encoding=\"utf-8\")\n"
)

# top-level imports only (column 0)
IMPORT_RE = re.compile(r"^(?:import|from) [^\n]*$", re.MULTILINE)
# first top-level def/class/assignment that ends the header region
HEADER_END_RE = re.compile(r"^(?:def |class |[A-Za-z_][A-Za-z0-9_]*\s*(?::[^=\n]+)?=)", re.MULTILINE)


def patch(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    if "reconfigure" in text:
        return None
    if not re.search(r"[^\x00-\x7F]", text):
        return None

    header_end = len(text)
    m = HEADER_END_RE.search(text)
    if m:
        header_end = m.start()

    imports = [im for im in IMPORT_RE.finditer(text) if im.end() <= header_end]
    if not imports:
        return "no top-level import found"

    last = imports[-1]
    new = text[: last.end()] + "\n" + GUARD + text[last.end():]

    if not re.search(r"^import sys$", new, re.MULTILINE):
        new = re.sub(r"^(import [^\n]*)$", r"import sys\n\1", new, count=1, flags=re.MULTILINE)

    if WRITE:
        path.write_text(new, encoding="utf-8", newline="\n")
    return "patched"


changed = []
for p in sorted(TOOLS.glob("*.py")):
    r = patch(p)
    if r:
        changed.append((p.name, r))
        print(f"  {'WROTE' if WRITE else 'WOULD PATCH'}  {p.name}  ({r})")

print()
print(f"{'patched' if WRITE else 'would patch'}: {len(changed)} files")
