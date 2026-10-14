"""Find test-side subprocess calls that do NOT capture output (their child writes to pytest's fd 1/2)."""
import ast
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
TESTS = Path(r"E:\MCP\MMCP\tests")

for p in sorted(TESTS.glob("*.py")):
    tree = ast.parse(p.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = None
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        if name not in {"run", "Popen", "check_call", "check_output", "call"}:
            continue
        kw = {k.arg for k in node.keywords if k.arg}
        has_capture = "capture_output" in kw or "stdout" in kw or "stderr" in kw
        if not has_capture:
            print(f"  {p.name}:{node.lineno}: {name}(...)  kwargs={sorted(kw)}")
