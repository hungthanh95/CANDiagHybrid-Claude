"""End-to-end capability-matrix tests: one ``.flex`` script per v1 capability.

Each script in ``tests/flex/`` is rendered against a fresh
:class:`mock_ecu.server.MockServer` (``port=0`` -> ephemeral port) with
``${PORT}`` substituted, then run via ``python -m terminal script <path>`` as
a subprocess (the dev's ``.flex`` runner, ``terminal/script.py``). Asserts
return code 0.

Mapping to the M1 capability matrix (Mock-ECU column, transport=A
TCP-loopback per docs/03 §5):

- ``cap_readdtc.flex``        -> Read DTC
- ``cap_tester_present.flex`` -> Tester Present
- ``cap_security.flex``       -> Security Access (seed/key unlock)
- ``cap_session.flex``        -> Session control
- ``cap_clear_dtc.flex``      -> Clear DTC

``${PORT}`` substitution (chosen approach, per M1 task spec section F option
(a)/(b)): the ``.flex`` runner has no ``--port`` flag, so each script is
rendered into a tempfile with ``${PORT}`` replaced by the
``MockServer.bound_port`` of a fresh server bound to ``port=0``. This keeps
tests independent (no shared/fixed ports) without adding a CLI flag to
``terminal/script.py``.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from mock_ecu.server import MockServer

FLEX_DIR = Path(__file__).parent / "flex"


@pytest.fixture
def server():
    srv = MockServer(host="127.0.0.1", port=0)
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


def test_cap_readdtc(server):
    result = _run_flex_script("cap_readdtc.flex", server.bound_port)
    assert result.returncode == 0, result.stdout + result.stderr


def test_cap_tester_present(server):
    result = _run_flex_script("cap_tester_present.flex", server.bound_port)
    assert result.returncode == 0, result.stdout + result.stderr


def test_cap_security(server):
    result = _run_flex_script("cap_security.flex", server.bound_port)
    assert result.returncode == 0, result.stdout + result.stderr


def test_cap_session(server):
    result = _run_flex_script("cap_session.flex", server.bound_port)
    assert result.returncode == 0, result.stdout + result.stderr


def test_cap_clear_dtc(server):
    result = _run_flex_script("cap_clear_dtc.flex", server.bound_port)
    assert result.returncode == 0, result.stdout + result.stderr
