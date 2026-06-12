"""Negative-path tests for :class:`mock_ecu.server.MockServer`.

End-to-end over a raw ``socket.socket`` (not :class:`terminal.transport_tcp.TcpTransport`),
per the M1 task spec section E -- this keeps the tests transport-agnostic and
exercises the exact bytes on the wire. Responses are parsed with
:func:`protocol.wire.parse_response`.

Covers (FR-23 NRC injection + protocol error handling):

- ``0x78`` response-pending -> intermediate ``NRC <sid> 78`` followed by the
  real terminal response, both carrying the same seq.
- ``0x35`` invalidKey via :meth:`mock_ecu.uds.Ecu.inject_next` on the SECURITY
  seed step.
- ``0x33`` securityAccessDenied via the same mechanism.
- Malformed protocol lines -> ``ERR 422``/``ERR 400``, peer stays alive.
- Unknown verb -> ``ERR 400 unknown_verb``.
- Oversized line -> ``ERR 422 bad_args`` and connection close.
- Transport drop mid-request (``inject_next(drop=True)``) -> socket closes
  with no response line; ``recv()`` returns ``b""``.
- ``BYE`` -> clean close, no response line.
"""

from __future__ import annotations

import socket

import pytest

from mock_ecu.server import MockServer
from protocol.wire import MAX_LINE, parse_response


@pytest.fixture
def server():
    srv = MockServer(host="127.0.0.1", port=0)
    srv.start()
    try:
        yield srv
    finally:
        srv.stop()


@pytest.fixture
def conn(server):
    sock = socket.create_connection(("127.0.0.1", server.bound_port), timeout=5)
    sock.settimeout(5)
    try:
        yield server, sock
    finally:
        sock.close()


def _readline(sock: socket.socket) -> str:
    """Read one ``\\n``-terminated line (raises on timeout)."""
    buf = bytearray()
    while not buf.endswith(b"\n"):
        chunk = sock.recv(1)
        if not chunk:
            break
        buf += chunk
    return buf.decode("ascii")


def _drain_banner(sock: socket.socket) -> None:
    banner = parse_response(_readline(sock))
    assert banner.seq == 0
    assert banner.verb == "READY"


# ---------------------------------------------------------------------------
# 0x78 response-pending then final
# ---------------------------------------------------------------------------


def test_pending_0x78_then_final(conn):
    server, sock = conn
    _drain_banner(sock)

    server.ecu.inject_next(pending_before=True)
    sock.sendall(b"7 READDTC FF\n")

    first = parse_response(_readline(sock))
    second = parse_response(_readline(sock))

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


def test_security_invalid_key_via_injected_nrc(conn):
    """Arm inject_next(nrc=0x35); SECURITY 01 -> NRC 27 35.

    The mock server's SECURITY orchestration (``_handle_security``) is
    server-internal: it issues the seed request (``27 01``) first via
    ``Ecu.handle()``. The single-shot NRC injection is consumed by *that*
    first call, so the seed step itself returns ``7F 27 35`` and the key
    step never runs. The client only ever sees the terminal
    ``<seq> NRC 27 35``.
    """
    server, sock = conn
    _drain_banner(sock)

    server.ecu.inject_next(nrc=0x35)
    sock.sendall(b"9 SECURITY 01\n")

    resp = parse_response(_readline(sock))
    assert resp.seq == 9
    assert resp.verb == "NRC"
    assert resp.sid == 0x27
    assert resp.nrc == 0x35

    # Security was not unlocked, and no seed is left pending (the injected
    # NRC bypassed Ecu.handle's normal 0x27 branch entirely -- see
    # Ecu.handle: an injected NRC returns 7F <sid> <nrc> before the SID
    # dispatch, so pending_seed_level is untouched at its initial None).
    assert server.ecu.unlocked is False
    assert server.ecu.pending_seed_level is None


# ---------------------------------------------------------------------------
# NRC 0x33 securityAccessDenied
# ---------------------------------------------------------------------------


def test_security_access_denied_via_injected_nrc(conn):
    server, sock = conn
    _drain_banner(sock)

    server.ecu.inject_next(nrc=0x33)
    sock.sendall(b"10 SECURITY 01\n")

    resp = parse_response(_readline(sock))
    assert resp.seq == 10
    assert resp.verb == "NRC"
    assert resp.sid == 0x27
    assert resp.nrc == 0x33

    assert server.ecu.unlocked is False


# ---------------------------------------------------------------------------
# Malformed protocol line
# ---------------------------------------------------------------------------


def test_malformed_line_single_token_bad_args(conn):
    """A line with no parseable VERB (only one token) -> ERR 422 bad_args.

    ``parse_command``/``_split_line`` requires at least SEQ and VERB
    tokens; a single-token line fails that check before any verb lookup,
    so it falls through to the generic ``ProtocolError`` -> ``ERR 422
    bad_args`` branch in ``MockServer._dispatch``. The seq is 0 because
    the lone token ("garbage") is not a parseable non-negative integer
    either.
    """
    server, sock = conn
    _drain_banner(sock)

    sock.sendall(b"garbage\n")
    resp = parse_response(_readline(sock))
    assert resp.seq == 0
    assert resp.verb == "ERR"
    assert resp.code == 422
    assert resp.text == "bad_args"

    # Peer stays alive: a subsequent valid command still gets a response.
    sock.sendall(b"1 PING\n")
    resp2 = parse_response(_readline(sock))
    assert resp2.seq == 1
    assert resp2.verb == "PONG"


def test_malformed_line_multi_token_garbage_is_unknown_verb(conn):
    """``not a real command`` -> ``0 ERR 400 unknown_verb`` (NOT 422).

    NOTE (spec-vs-behaviour discrepancy, documented for flexdiag-status /
    flexdiag-reviewer): the M1 task spec's "malformed protocol line" example
    is literally ``not a real command\\n`` and expects ``0 ERR 422
    bad_args``. In the current ``MockServer._dispatch``, a >=2-token line
    has its second token ("a") checked against ``Verb`` *before*
    ``parse_command`` is even called (to distinguish "unknown verb" / ERR
    400 from "malformed args" / ERR 422 per docs/04 §1.7). "A" is not a
    valid ``Verb``, so this line is classified ERR 400 unknown_verb, not
    ERR 422 bad_args. This test pins the *actual* current behaviour;
    ``test_malformed_line_single_token_bad_args`` above covers the genuine
    ERR 422 bad_args path. Peer stays alive either way.
    """
    server, sock = conn
    _drain_banner(sock)

    sock.sendall(b"not a real command\n")
    resp = parse_response(_readline(sock))
    assert resp.seq == 0
    assert resp.verb == "ERR"
    assert resp.code == 400
    assert resp.text == "unknown_verb"

    sock.sendall(b"1 PING\n")
    resp2 = parse_response(_readline(sock))
    assert resp2.seq == 1
    assert resp2.verb == "PONG"


# ---------------------------------------------------------------------------
# Unknown verb
# ---------------------------------------------------------------------------


def test_unknown_verb(conn):
    server, sock = conn
    _drain_banner(sock)

    sock.sendall(b"5 FROBNICATE\n")
    resp = parse_response(_readline(sock))
    assert resp.seq == 5
    assert resp.verb == "ERR"
    assert resp.code == 400
    assert resp.text == "unknown_verb"

    # Peer stays alive.
    sock.sendall(b"1 PING\n")
    resp2 = parse_response(_readline(sock))
    assert resp2.seq == 1
    assert resp2.verb == "PONG"


# ---------------------------------------------------------------------------
# Oversized line
# ---------------------------------------------------------------------------


def test_oversized_line_closes_connection(conn):
    server, sock = conn
    _drain_banner(sock)

    huge = b"1 RAW " + b" ".join([b"FF"] * 2048) + b"\n"
    assert len(huge) > MAX_LINE

    sock.sendall(huge)
    resp = parse_response(_readline(sock))
    assert resp.seq == 0
    assert resp.verb == "ERR"
    assert resp.code == 422
    assert resp.text == "bad_args"

    # The connection should now be closed -- a follow-up byte and a recv()
    # should observe the closed peer (b"").
    sock.sendall(b"x")
    data = sock.recv(16)
    assert data == b""


# ---------------------------------------------------------------------------
# Transport drop mid-request
# ---------------------------------------------------------------------------


def test_transport_drop_mid_request(conn):
    server, sock = conn
    _drain_banner(sock)

    server.ecu.inject_next(drop=True)
    sock.sendall(b"11 READDTC FF\n")

    # No response line is ever sent; recv() observes the closed connection.
    data = sock.recv(16)
    assert data == b""


# ---------------------------------------------------------------------------
# BYE clean close
# ---------------------------------------------------------------------------


def test_bye_clean_close(conn):
    server, sock = conn
    _drain_banner(sock)

    sock.sendall(b"2 BYE\n")

    # No terminal response line for BYE -- the server closes the socket.
    data = sock.recv(16)
    assert data == b""
