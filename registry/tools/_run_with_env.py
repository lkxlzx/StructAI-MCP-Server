"""读 ~/.structai/midas-test.env 的 [gen] 段设环境变量，再 exec 目标脚本（纯 python，绕开 PowerShell stderr）。"""
import os, sys, runpy
inst = sys.argv[1] if len(sys.argv)>1 else "gen"
target = sys.argv[2]
envp = os.path.expanduser("~/.structai/midas-test.env")
section = None; vals = {}
for line in open(envp, encoding="utf-8").read().splitlines():
    s=line.strip()
    if s.startswith("[") and s.endswith("]"):
        section = s.strip("[]")
        continue
    if section == inst and "=" in s:
        k,v = s.split("=",1)
        vals[k.strip()] = v.strip()
for k,v in vals.items():
    os.environ[k]=v
print(f"[runner] instance={inst} base_url={os.environ.get('MIDAS_BASE_URL')} key_len={len(os.environ.get('MIDAS_MAPI_KEY',''))}", file=sys.stderr)
sys.argv = [target] + sys.argv[3:]
runpy.run_path(target, run_name="__main__")
