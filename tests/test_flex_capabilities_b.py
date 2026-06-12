"""End-to-end capability-matrix tests for Option B: one ``.flex`` script per
v1 capability, run against :class:`bridge.flexdiag_bridge.BridgeServer`
(WebSocket bridge + :class:`bridge.flexdiag_bridge.FakeVectorCom`).

Mirrors ``tests/test_flex_capabilities.py`` (Option A / :class:`mock_ecu.server.MockServer`)
exactly, but uses ``connectb`` and ``${PORT}`` substitution against
``BridgeServer.bound_port``. Together with the Option A tests, this proves
FR-12 ("identical protocol both transports") and completes the capability x
transport matrix (FR-11 "Option B transport") for:

- ``cap_readdtc_b.flex``        -> Read DTC
- ``cap_tester_present_b.flex`` -> Tester Present
- ``cap_security_b.flex``       -> Security Access (seed/key unlock)
- ``cap_session_b.flex``        -> Session control
- ``cap_clear_dtc_b.flex``      -> Clear DTC
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from bridge.flexdiag_bridge import BridgeServer

FLEX_DIR = Path(__file__).parent / "flex"


@pytest.fixture
def server():
    srv = BridgeServer(host="127.0.0.1", port=0)
    srv.start()
    try:
        yield srv
    finally:
        srv.stop()


def _run_flex_script(flex_name: str, port: int) -> subprocess.CompletedProcess[str]:
    content = (FLEX_DIR / flex_name).read_text(encoding="utf-8")
    rendered = content.replace("${PORT}", str(port))

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".flex", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(rendered)
        path = tf.name

    try:
        return subprocess.run(
            [sys.executable, "-m", "terminal", "script", path],
            capture_output=True,
            text=True,
            timeout=30,
        )
    finally:
        Path(path).unlink(missing_ok=True)


def test_cap_readdtc_b(server):
    result = _run_flex_script("cap_readdtc_b.flex", server.bound_port)
    assert result.returncode == 0, result.stdout + result.stderr


def test_cap_tester_present_b(server):
    result = _run_flex_script("cap_tester_present_b.flex", server.bound_port)
    assert result.returncode == 0, result.stdout + result.stderr


def test_cap_security_b(server):
    result = _run_flex_script("cap_security_b.flex", server.bound_port)
    assert result.returncode == 0, result.stdout + result.stderr


def test_cap_session_b(server):
    result = _run_flex_script("cap_session_b.flex", server.bound_port)
    assert result.returncode == 0, result.stdout + result.stderr


def test_cap_clear_dtc_b(server):
    result = _run_flex_script("cap_clear_dtc_b.flex", server.bound_port)
    assert result.returncode == 0, result.stdout + result.stderr
