"""Capability-matrix recorder (Mock-ECU column only).

Runs each ``tests/flex/cap_*.flex`` script against a fresh
:class:`mock_ecu.server.MockServer` (same approach as
``tests/test_flex_capabilities.py``) and prints a pass/fail line per
capability, formatted for easy pasting into ``docs/STATUS.md`` §2's Mock-ECU
column.

This is a standalone utility for ``flexdiag-status`` -- it does NOT write to
``docs/STATUS.md`` itself; it only prints. Usage::

    python -m tests.cap_matrix
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from mock_ecu.server import MockServer

FLEX_DIR = Path(__file__).parent / "flex"

# (script filename, capability label for docs/STATUS.md §2)
CAPABILITIES = [
    ("cap_readdtc.flex", "Read DTC"),
    ("cap_tester_present.flex", "Tester Present"),
    ("cap_security.flex", "Security Access"),
    ("cap_session.flex", "Session control"),
    ("cap_clear_dtc.flex", "Clear DTC"),
]


def _run_flex_script(flex_name: str, port: int) -> bool:
    content = (FLEX_DIR / flex_name).read_text(encoding="utf-8")
    rendered = content.replace("${PORT}", str(port))

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".flex", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(rendered)
        path = tf.name

    try:
        result = subprocess.run(
            [sys.executable, "-m", "terminal", "script", path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    finally:
        Path(path).unlink(missing_ok=True)


def main() -> int:
    all_pass = True
    for flex_name, label in CAPABILITIES:
        server = MockServer(host="127.0.0.1", port=0)
        server.start()
        try:
            ok = _run_flex_script(flex_name, server.bound_port)
        finally:
            server.stop()
        status = "PASS" if ok else "FAIL"
        all_pass = all_pass and ok
        print(f"| {label:<16} | Mock ECU (loopback) | {status} |")

    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
