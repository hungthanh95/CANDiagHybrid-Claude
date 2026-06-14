"""Negative-path tests for Option B (:mod:`bridge.flexdiag_bridge`).

Drives :class:`bridge.flexdiag_bridge.BridgeServer` (WebSocket +
:class:`bridge.flexdiag_bridge.FakeVectorCom`) via
:class:`terminal.transport_ws.WsTransport`, covering the required negative
paths (CLAUDE.md "What you test" / docs/04):

- ``0x78`` response-pending -> intermediate ``NRC <sid> 78`` then the final
  terminal response, both carrying the same seq.
- ``0x35`` invalidKey via ``inject_next(nrc=0x35)`` on ``SECURITY`` ->
  ``NRC 27 35``, security not unlocked.
- ``0x33`` securityAccessDenied via ``inject_next(nrc=0x33)``.
- Transport drop mid-request (``inject_next(drop=True)``) -> in-flight
  request fails with a clear transport error / connection close, never
  hangs.
"""

from __future__ import annotations

import pytest

from bridge.flexdiag_bridge import BridgeServer
from protocol.wire import parse_response
from terminal.transport_ws import TransportError, WsTransport


@pytest.fixture
def server():
    srv = BridgeServer(host="127.0.0.1", port=0)
    srv.start()
    try:
        yield srv
    finally:
        srv.stop()


@pytest.fixture
async def ws(server):
    t = WsTransport("127.0.0.1", server.bound_port)
    await t.connect()
    try:
        yield t
    finally:
        await t.close()


async def _drain_banner(lines) -> None:
    banner = parse_response(await lines.__anext__())
    assert banner.seq == 0
    assert banner.verb == "READY"
    assert banner.transport == "B"


# ---------------------------------------------------------------------------
# 0x78 response-pending then final
# ---------------------------------------------------------------------------


async def test_pending_0x78_then_final(server, ws):
    lines = ws.recv_lines()
    await _drain_banner(lines)

    server.ecu.inject_next(pending_before=True)
    await ws.send("7 READDTC FF")

    first = parse_response(await lines.__anext__())
    second = parse_response(await lines.__anext__())

    # Both lines carry the same (request) seq.
    assert first.seq == 7
    assert second.seq == 7

    # First line: intermediate NRC 19 78 (responsePending).
    assert first.verb == "NRC"
    assert first.sid == 0x19
    assert first.nrc == 0x78

    # Second line: the real DTC payload (terminal response).
    assert second.verb == "RSP"
    assert second.data is not None
    assert second.data[:3] == bytes([0x59, 0x02, 0xFF])
    assert second.data[3:] == bytes([0x00, 0x12, 0x34, 0x2F, 0x00, 0x56, 0x78, 0x08])


# ---------------------------------------------------------------------------
# NRC 0x35 invalidKey
# ---------------------------------------------------------------------------


async def test_security_invalid_key_via_injected_nrc(server, ws):
    """``inject_next(nrc=0x35)``; SECURITY 01 -> NRC 27 35.

    Mirrors ``tests/test_server_negatives.py::test_security_invalid_key_via_injected_nrc``:
    the single-shot NRC injection is consumed by the seed request (``27
    01``) inside ``FakeVectorCom._do_security``, so the key step never runs
    and the client only ever sees the terminal ``<seq> NRC 27 35``.
    """
    lines = ws.recv_lines()
    await _drain_banner(lines)

    server.ecu.inject_next(nrc=0x35)
    await ws.send("9 SECURITY 01")

    resp = parse_response(await lines.__anext__())
    assert resp.seq == 9
    assert resp.verb == "NRC"
    assert resp.sid == 0x27
    assert resp.nrc == 0x35

    assert server.ecu.unlocked is False
    assert server.ecu.pending_seed_level is None


# ---------------------------------------------------------------------------
# NRC 0x33 securityAccessDenied
# ---------------------------------------------------------------------------


async def test_security_access_denied_via_injected_nrc(server, ws):
    lines = ws.recv_lines()
    await _drain_banner(lines)

    server.ecu.inject_next(nrc=0x33)
    await ws.send("10 SECURITY 01")

    resp = parse_response(await lines.__anext__())
    assert resp.seq == 10
    assert resp.verb == "NRC"
    assert resp.sid == 0x27
    assert resp.nrc == 0x33

    assert server.ecu.unlocked is False


# ---------------------------------------------------------------------------
# Transport drop mid-request
# ---------------------------------------------------------------------------


async def test_transport_drop_mid_request(server, ws):
    """``inject_next(drop=True)`` -> in-flight request never gets a response.

    ``FakeVectorCom._respond_uds`` consumes the drop flag and returns
    without pushing anything to ``evt_q``, so the bridge never sends a
    response line. The client's read should observe the connection close
    (here: the server is stopped while the request is "in flight", and the
    read raises/ends rather than hanging forever).
    """
    lines = ws.recv_lines()
    await _drain_banner(lines)

    server.ecu.inject_next(drop=True)
    await ws.send("11 READDTC FF")

    # No response line is ever sent for this request. Stop the server to
    # unblock the read side deterministically (mirrors "never hangs":
    # closing the underlying connection ends recv_lines() rather than
    # blocking indefinitely).
    server.stop()

    with pytest.raises((StopAsyncIteration, TransportError)):
        await lines.__anext__()


# ---------------------------------------------------------------------------
# BYE clean close
# ---------------------------------------------------------------------------


async def test_bye_clean_close(server, ws):
    lines = ws.recv_lines()
    await _drain_banner(lines)

    await ws.send("2 BYE")

    # No terminal response line for BYE -- the server closes the connection.
    with pytest.raises(StopAsyncIteration):
        await lines.__anext__()


# ---------------------------------------------------------------------------
# Command timeout (Feature 1: STATUS_ERR_TIMEOUT -> ERR <seq> 504 ecu_timeout)
# ---------------------------------------------------------------------------


async def test_command_timeout_yields_err_504(server, ws):
    """``inject_next(drop=True)`` -> ``ERR <seq> 504 ecu_timeout`` within bound time.

    Unlike ``test_transport_drop_mid_request`` (which simulates an
    indefinite hang and stops the server to observe), this exercises
    ``FakeVectorCom``'s ``cmd_timeout`` synthesis of ``STATUS_ERR_TIMEOUT``
    (docs/03 §2 RspStatus 4 -> ``ERR 504 ecu_timeout``), proving the bridge
    never hangs the WebSocket client even without external intervention.
    """
    lines = ws.recv_lines()
    await _drain_banner(lines)

    server.ecu.inject_next(drop=True)
    await ws.send("12 READDTC FF")

    resp = parse_response(await lines.__anext__())
    assert resp.seq == 12
    assert resp.verb == "ERR"
    assert resp.code == 504
    assert resp.text == "ecu_timeout"

    # Peer stays alive -- a subsequent request gets a normal response.
    await ws.send("13 READDTC FF")
    resp2 = parse_response(await lines.__anext__())
    assert resp2.seq == 13
    assert resp2.verb == "RSP"
