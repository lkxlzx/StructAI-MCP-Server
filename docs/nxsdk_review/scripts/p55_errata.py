"""Update the errata doc's now-stale `products` values for the Hyper-S -M1 endpoints."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
p = Path(r"E:\MCP\MMCP\MIDAS_API_Online_Manual_勘误与补全_v1.0.md")
lines = p.read_text(encoding="utf-8").splitlines()

changed = []
for i, line in enumerate(lines):
    if "-M1" in line and "[GEN_NX]" in line:
        lines[i] = line.replace("[GEN_NX]", "[CIVIL_NX]")
        changed.append(i + 1)

p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print(f"updated {len(changed)} lines: {changed}")

# report any remaining -M1 rows for manual review
for i, line in enumerate(lines):
    if "-M1" in line and ("products" in line or "[CIVIL" in line or "[GEN" in line):
        print(f"  {i + 1}: {line.strip()[:150]}")
