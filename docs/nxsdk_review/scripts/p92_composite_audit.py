"""离线审计：全部 composite OperationPlan 的每一步，是否与端点的原生 `methods` 相符。

R141（DESIGN.STEEL）/ R153（DESIGN.CONCRETE）的缺陷形态 = **配置端点被编排成 `_read`（GET）**。
本脚本把它机械化为一条可复算的判据：`_read` 的端点若原生支持 `PUT`/`POST`，即为**可疑**。
"""
import ast
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
SRC = REPO / "app" / "infrastructure" / "adapters" / "midas" / "operations.py"

man = {
    str(e["key"]): e
    for e in json.loads((REPO / "registry" / "manifest.json").read_text(encoding="utf-8"))["endpoints"]
}

text = SRC.read_text(encoding="utf-8")
tree = ast.parse(text)


def steps_of(call: ast.Call) -> list[ast.Call]:
    """取 OperationPlan 的 steps=_steps(...) 里的每个步骤调用。"""
    for kw in call.keywords:
        if kw.arg == "steps" and isinstance(kw.value, ast.Call):
            return [a for a in kw.value.args if isinstance(a, ast.Call)]
    return []


def step_info(call: ast.Call) -> dict:
    fn = call.func.id if isinstance(call.func, ast.Name) else "?"
    endpoint = call.args[0].value if call.args and isinstance(call.args[0], ast.Constant) else "?"
    info = {"kind": fn, "endpoint": endpoint}
    for kw in call.keywords:
        if kw.arg == "method" and isinstance(kw.value, ast.Constant):
            info["method"] = kw.value.value
    return info


rows = []
for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue
    fname = node.func.id if isinstance(node.func, ast.Name) else None
    if fname != "OperationPlan":
        continue
    op = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else "?"
    steps = steps_of(node)
    if not steps:
        continue
    for st in steps:
        info = step_info(st)
        entry = man.get(info["endpoint"], {})
        methods = {p.strip().upper() for p in str(entry.get("methods") or "").split(",") if p.strip()}
        info["operation"] = op
        info["native_methods"] = sorted(methods)
        # 判据：`_read` 却原生支持 PUT/POST（或 `_write` 却原生不支持该方法）
        info["suspect_read_on_config"] = info["kind"] == "_read" and bool(methods & {"PUT", "POST"})
        declared = str(info.get("method") or ("GET" if info["kind"] == "_read" else "POST")).upper()
        info["suspect_method_mismatch"] = bool(methods) and declared not in methods
        rows.append(info)

print(f"composite 步骤总数: {len(rows)}")
print()
bad = [r for r in rows if r["suspect_read_on_config"] or r["suspect_method_mismatch"]]
print(f"⚠️ 可疑步骤: {len(bad)}")
print()
print(f"{'operation':34s} {'kind':7s} {'endpoint':40s} {'declared':9s} native")
for r in sorted(bad, key=lambda x: (x["operation"], x["endpoint"])):
    flag = "READ-ON-CONFIG" if r["suspect_read_on_config"] else "METHOD-MISMATCH"
    print(f"{r['operation']:34s} {r['kind']:7s} {r['endpoint']:40s} "
          f"{str(r.get('method') or ('GET' if r['kind'] == '_read' else 'POST')):9s} "
          f"{','.join(r['native_methods']):22s} {flag}")

print()
print("--- 按 operation 汇总（全部步骤）---")
from collections import defaultdict

byop = defaultdict(list)
for r in rows:
    byop[r["operation"]].append(r)
for op, rs in sorted(byop.items()):
    n_bad = sum(1 for r in rs if r["suspect_read_on_config"] or r["suspect_method_mismatch"])
    mark = " ⚠️" if n_bad else "  "
    print(f"{mark} {op:34s} {len(rs):2d} 步 / {n_bad} 可疑")

json.dump(rows, open(REPO / ".tmp_analysis" / "composite_step_audit.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print()
print("wrote .tmp_analysis/composite_step_audit.json")
