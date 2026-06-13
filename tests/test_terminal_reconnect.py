"""Reconnection + timeout tests for the terminal client (FR-16, NFR-5).

Covers ``terminal/repl.py``'s bounded auto-reconnect with exponential
backoff:

- On transport loss, in-flight requests fail immediately with a clear
  :class:`TransportError` (not left to hang until the per-request timeout).
- The client then attempts bounded reconnection (capped attempts, capped
  exponential backoff).
- If the server comes back before the attempts are exhausted, the client
  reconnects and resumes normal operation.
- If all attempts are exhausted, the client surfaces a clear error and stays
  cleanly disconnected (no hang, no crash).

Also covers the existing per-request timeout (``_send_and_wait``'s 5s
default, parametrized down for test speed): a server that accepts the
connection but never responds must fail the request with
:class:`TransportError`, not hang.
"""

from __future__ import annotations

import asyncio

import pytest

from bridge.flexdiag_bridge import BridgeServer
from terminal.repl import ReconnectPolicy, Repl
from terminal.transport_ws import TransportError


@pytest.fixture
def server():
    srv = BridgeServer(host="127.0.0.1", port=0)
    srv.start()
    try:
        yield srv
    finally:
        srv.stop()


async def _drain_banner(repl: Repl) -> None:
    # connectb's _read_loop processes the READY banner internally (seq 0);
    # nothing to drain explicitly here. Kept for readability at call sites.
    await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# In-flight request failed immediately on transport drop
# ---------------------------------------------------------------------------


async def test_inflight_request_fails_immediately_on_drop(server):
    """A request awaiting a response must fail as soon as the transport
    drops -- not wait for the 5s per-request timeout.
    """
    repl = Repl(reconnect=ReconnectPolicy(max_attempts=0))
    await repl.connectb("127.0.0.1", server.bound_port)
    await _drain_banner(repl)

    # Inject a drop so the in-flight READDTC never gets a response.
    server.ecu.inject_next(drop=True)

    send_task = asyncio.create_task(repl.run_command("readdtc"))

    # Give the request a moment to be sent and registered as pending.
    await asyncio.sleep(0.05)

    # Simulate transport loss by stopping the server.
    server.stop()

    with pytest.raises(TransportError):
        await asyncio.wait_for(send_task, timeout=2.0)


# ---------------------------------------------------------------------------
# Bounded reconnect: recovers if the server comes back in time
# ---------------------------------------------------------------------------


async def test_bounded_reconnect_recovers(server):
    """If the server comes back before attempts are exhausted, the client
    reconnects and a subsequent command succeeds.
    """
    port = server.bound_port

    repl = Repl(reconnect=ReconnectPolicy(max_attempts=5, base_delay=0.01, max_delay=0.05))
    await repl.connectb("127.0.0.1", port)
    await _drain_banner(repl)

    # Drop the connection by stopping the server.
    server.stop()

    # Wait for the reader loop to notice the drop and start reconnecting.
    await asyncio.sleep(0.05)

    # Bring the server back on the same port.
    server2 = BridgeServer(host="127.0.0.1", port=port)
    server2.start()
    try:
        # Wait for reconnection to complete (bounded backoff + a margin).
        for _ in range(100):
            if repl.transport is not None and not repl.transport.closed:
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("client did not reconnect within the expected window")

        # A subsequent command should work normally on the new connection.
        resp = await repl._send_and_wait(f"{repl.seq_alloc.next()} PING")
        assert resp.verb == "PONG"
    finally:
        server2.stop()
        await repl.disconnect()


# ---------------------------------------------------------------------------
# Bounded reconnect: exhausts cleanly if the server never comes back
# ---------------------------------------------------------------------------


async def test_bounded_reconnect_exhausts_cleanly(server):
    """If the server never comes back, reconnect attempts are bounded and
    the client ends up cleanly disconnected (no hang, no crash).
    """
    port = server.bound_port

    repl = Repl(reconnect=ReconnectPolicy(max_attempts=3, base_delay=0.01, max_delay=0.02))
    await repl.connectb("127.0.0.1", port)
    await _drain_banner(repl)

    server.stop()

    # Wait long enough for all bounded attempts to be exhausted.
    for _ in range(100):
        if repl.transport is None:
            break
        await asyncio.sleep(0.02)
    else:
        pytest.fail("reconnect attempts never exhausted")

    assert repl.transport is None
    assert repl._pending == {}


# ---------------------------------------------------------------------------
# Per-request timeout: server accepts but never responds
# ---------------------------------------------------------------------------


async def test_per_request_timeout_no_response(server):
    """A server that accepts the connection but never replies must fail the
    request with TransportError (not hang).
    """
    repl = Repl(reconnect=ReconnectPolicy(max_attempts=0))
    await repl.connectb("127.0.0.1", server.bound_port)
    await _drain_banner(repl)

    server.ecu.inject_next(drop=True)

    with pytest.raises(TransportError):
        await repl._send_and_wait(f"{repl.seq_alloc.next()} READDTC FF", timeout=0.2)
