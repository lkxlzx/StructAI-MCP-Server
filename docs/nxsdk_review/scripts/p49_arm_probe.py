"""TEMPORARY diagnostic — append a read_text probe to tests/conftest.py (remove afterwards)."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
p = Path(r"E:\MCP\MMCP\tests\conftest.py")
text = p.read_text(encoding="utf-8")
if "decode_probe" in text:
    print("probe already present")
    raise SystemExit

probe = '''

# ---------------------------------------------------------------------------
# TEMPORARY DIAGNOSTIC (decode_probe) — remove before committing.
# ---------------------------------------------------------------------------
import pathlib as _pathlib
import traceback as _traceback

_PROBE_LOG = _pathlib.Path(r"E:\\MCP\\MMCP\\.tmp_analysis\\decode_probe.log")
_orig_read_text = _pathlib.Path.read_text


def _probe_read_text(self, encoding=None, errors=None):  # noqa: ANN001, ANN202
    try:
        return _orig_read_text(self, encoding=encoding, errors=errors)
    except UnicodeDecodeError as exc:
        with _PROBE_LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"read_text FAIL {self} encoding={encoding} err={exc}\\n")
            handle.write("".join(_traceback.format_stack()[-8:]) + "\\n")
        raise


_pathlib.Path.read_text = _probe_read_text  # type: ignore[method-assign]
'''
p.write_text(text + probe, encoding="utf-8", newline="\n")
print("probe appended; conftest lines now:", len((text + probe).splitlines()))
