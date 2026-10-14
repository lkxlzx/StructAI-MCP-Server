"""Restore conftest.py and append a broader decode probe (io.TextIOWrapper)."""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"E:\MCP\MMCP")
p = REPO / "tests" / "conftest.py"

# restore from git first
subprocess.run(["git", "checkout", "--", "tests/conftest.py"], cwd=REPO, check=False)
text = p.read_text(encoding="utf-8")
print("conftest restored, lines:", len(text.splitlines()))

probe = '''

# ---------------------------------------------------------------------------
# TEMPORARY DIAGNOSTIC (decode_probe) — remove before committing.
# ---------------------------------------------------------------------------
import io as _io
import pathlib as _pathlib
import traceback as _traceback

_PROBE_LOG = _pathlib.Path(r"E:\\MCP\\MMCP\\.tmp_analysis\\decode_probe.log")
_orig_wrapper_read = _io.TextIOWrapper.read
_orig_read_text = _pathlib.Path.read_text


def _probe_wrapper_read(self, *args, **kwargs):  # noqa: ANN001, ANN202
    try:
        return _orig_wrapper_read(self, *args, **kwargs)
    except UnicodeDecodeError as exc:
        name = getattr(self, "name", "<unknown>")
        with _PROBE_LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"TextIOWrapper.read FAIL name={name} err={exc}\\n")
            handle.write("".join(_traceback.format_stack()[-10:]) + "\\n")
        raise


def _probe_read_text(self, encoding=None, errors=None):  # noqa: ANN001, ANN202
    try:
        return _orig_read_text(self, encoding=encoding, errors=errors)
    except UnicodeDecodeError as exc:
        with _PROBE_LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"read_text FAIL {self} encoding={encoding} err={exc}\\n")
            handle.write("".join(_traceback.format_stack()[-10:]) + "\\n")
        raise


_io.TextIOWrapper.read = _probe_wrapper_read  # type: ignore[method-assign]
_pathlib.Path.read_text = _probe_read_text  # type: ignore[method-assign]
'''
p.write_text(text + probe, encoding="utf-8", newline="\n")
print("broader probe appended, lines:", len((text + probe).splitlines()))

# clean stray __pycache__ under registry/tools (created by my py_compile runs)
removed = 0
for cache in (REPO / "registry").rglob("__pycache__"):
    for f in cache.iterdir():
        f.unlink(missing_ok=True)
    cache.rmdir()
    removed += 1
print("removed __pycache__ dirs under registry/:", removed)
