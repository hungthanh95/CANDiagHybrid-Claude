"""Capability-matrix recorder (Mock-ECU column, Option B).

Runs each ``tests/flex/cap_*_b.flex`` script (Option B, against
:class:`bridge.flexdiag_bridge.BridgeServer` +
:class:`bridge.flexdiag_bridge.FakeVectorCom`) and prints a pass/fail line
per capability, formatted for easy pasting into ``docs/STATUS.md`` §2's
Option B (COM/sysvar) column (Mock-ECU topology -- CLAUDE.md rule 6, "single
transport, every capability").

This is a standalone utility for ``flexdiag-status`` -- it does NOT write to
``docs/STATUS.md`` itself; it only prints. Usage::

    python -m tests.cap_matrix
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from bridge.flexdiag_bridge import BridgeServer

FLEX_DIR = Path(__file__).parent / "flex"

# (Option B script, capability label for docs/STATUS.md §2)
CAPABILITIES = [
    ("cap_readdtc_b.flex", "Read DTC"),
    ("cap_tester_present_b.flex", "Tester Present"),
    ("cap_security_b.flex", "Security Access"),
    ("cap_session_b.flex", "Session control"),
    ("cap_clear_dtc_b.flex", "Clear DTC"),
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
    for flex_b, label in CAPABILITIES:
        server_b = BridgeServer(host="127.0.0.1", port=0)
        server_b.start()
        try:
            ok_b = _run_flex_script(flex_b, server_b.bound_port)
        finally:
            server_b.stop()

        status_b = "PASS" if ok_b else "FAIL"
        all_pass = all_pass and ok_b
        print(f"| {label:<16} | Option B (COM/sysvar): {status_b} |")

    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
