"""Find test code that runs a registry tool via subprocess, and whether output is captured."""
import ast
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
TESTS = Path(r"E:\MCP\MMCP\tests")

for p in sorted(TESTS.glob("*.py")):
    text = p.read_text(encoding="utf-8")
    if "registry" not in text or "subprocess" not in text:
        continue
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in {"run", "Popen", "check_call", "check_output"}:
            continue
        # must be subprocess.<attr>
        base = func.value
        base_name = base.id if isinstance(base, ast.Name) else (base.attr if isinstance(base, ast.Attribute) else "?")
        if base_name != "subprocess":
            continue
        kw = {k.arg for k in node.keywords if k.arg}
        has_capture = bool({"capture_output", "stdout", "stderr"} & kw)
        segment = ast.get_source_segment(text, node) or ""
        if not has_capture:
            print(f"  {p.name}:{node.lineno}  kwargs={sorted(kw)}")
            print(f"      {segment[:160].replace(chr(10), ' ')}")
