"""Move the console guard from module level into the `if __name__ == "__main__":` block.

Why: the test suite loads these tools with `importlib ... exec_module()`. A module-level
`sys.stdout.reconfigure(...)` therefore mutates **pytest's captured stdout**, which breaks
capture for every subsequent test (75 errors). Inside `__main__` it only runs when the tool
is actually executed as a script — which is the only case it is needed for.
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
TOOLS = Path(r"E:\MCP\MMCP\registry\tools")

HEAD_MARK = "Windows 控制台默认 cp949/cp936"
TAIL_MARK = 'sys.stderr.reconfigure(encoding="utf-8")'
GUARD = [
    "    # Windows 控制台默认 cp949/cp936：本工具会打印中文/符号，不重设编码会 UnicodeEncodeError。",
    "    # ⚠️ 必须在 `__main__` 块内：测试用 `exec_module()` 装载本模块，模块级调用会改写",
    "    #    **pytest 的捕获流**，破坏其后所有用例的 capture。",
    '    if hasattr(sys.stdout, "reconfigure"):',
    '        sys.stdout.reconfigure(encoding="utf-8")',
    '        sys.stderr.reconfigure(encoding="utf-8")',
]

fixed = []
for p in sorted(TOOLS.glob("*.py")):
    lines = p.read_text(encoding="utf-8").splitlines()
    start = next((i for i, l in enumerate(lines) if HEAD_MARK in l), None)
    if start is None:
        continue
    end = next((i for i in range(start, len(lines)) if TAIL_MARK in lines[i]), None)
    if end is None:
        print(f"  !! {p.name}: tail marker not found")
        continue
    # drop the guard, plus one blank line above it if present
    lo = start - 1 if start > 0 and not lines[start - 1].strip() else start
    del lines[lo : end + 1]

    main_idx = next((i for i, l in enumerate(lines) if l.startswith('if __name__ == "__main__":')), None)
    if main_idx is None:
        print(f"  !! {p.name}: no __main__ block")
        continue
    lines[main_idx + 1 : main_idx + 1] = GUARD

    # collapse runs of 3+ blank lines down to 2
    out: list[str] = []
    blanks = 0
    for line in lines:
        if line.strip():
            blanks = 0
            out.append(line)
        else:
            blanks += 1
            if blanks <= 2:
                out.append(line)

    p.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    fixed.append(p.name)

print(f"moved guard into __main__ for {len(fixed)} tools")
for name in fixed:
    print("  ", name)
