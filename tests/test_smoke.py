"""End-to-end smoke test: MockServer + TcpTransport over a software loopback.

Starts :class:`mock_ecu.server.MockServer` on an ephemeral port in a
background thread, then drives it via :class:`terminal.transport_tcp.TcpTransport`
covering one HELLO/READY, one READDTC FF, one TP START/STOP, one SECURITY 01,
and one RAW 22 F1 90. This is the M1 "leave in place for the tester" smoke
test (the tester will expand from here with negative-path coverage).
"""

from __future__ import annotations

import pytest

from mock_ecu.server import MockServer
from protocol.dtc import parse_read_dtc_payload
from protocol.wire import parse_response
from terminal.transport_tcp import TcpTransport


@pytest.fixture
async def server_port():
    server = MockServer(host="127.0.0.1", port=0, tool_label="Mock", transport_label="A")
    server.start()
    try:
        yield server.bound_port
    finally:
        server.stop()


@pytest.fixture
async def transport(server_port):
    t = TcpTransport("127.0.0.1", server_port)
    await t.connect()
    try:
        yield t
    finally:
        await t.close()


async def _send_and_recv(transport: TcpTransport, line: str):
    lines = transport.recv_lines()
    await transport.send(line)
    while True:
        raw = await lines.__anext__()
        resp = parse_response(raw)
        if resp.seq != 0:
            return resp


async def test_banner_on_connect(server_port):
    t = TcpTransport("127.0.0.1", server_port)
    await t.connect()
    try:
        lines = t.recv_lines()
        raw = await lines.__anext__()
        resp = parse_response(raw)
        assert resp.seq == 0
        assert resp.verb == "READY"
        assert resp.proto == 1
        assert resp.tool == "Mock"
        assert resp.transport == "A"
    finally:
        await t.close()


async def test_hello(transport):
    # Drain the unsolicited banner first.
    lines = transport.recv_lines()
    banner = parse_response(await lines.__anext__())
    assert banner.verb == "READY"

    await transport.send("1 HELLO")
    resp = parse_response(await lines.__anext__())
    assert resp.seq == 1
    assert resp.verb == "READY"
    assert resp.proto == 1
    assert resp.transport == "A"


async def test_readdtc(transport):
    lines = transport.recv_lines()
    await lines.__anext__()  # banner

    await transport.send("2 READDTC FF")
    resp = parse_response(await lines.__anext__())
    assert resp.seq == 2
    assert resp.verb == "RSP"
    mask, dtcs = parse_read_dtc_payload(resp.data)
    assert mask == 0xFF
    codes = {d.code for d in dtcs}
    assert "P01234" in codes  # 0x001234
    assert "P05678" in codes  # 0x005678


async def test_tp_start_stop(transport):
    lines = transport.recv_lines()
    await lines.__anext__()  # banner

    await transport.send("3 TP START")
    resp = parse_response(await lines.__anext__())
    assert resp.seq == 3
    assert resp.verb == "OK"
    assert resp.kind == "TP"

    await transport.send("4 TP STOP")
    resp = parse_response(await lines.__anext__())
    assert resp.seq == 4
    assert resp.verb == "OK"
    assert resp.kind == "TP"


async def test_security_01(transport):
    lines = transport.recv_lines()
    await lines.__anext__()  # banner

    await transport.send("5 SECURITY 01")
    resp = parse_response(await lines.__anext__())
    assert resp.seq == 5
    assert resp.verb == "OK"
    assert resp.kind == "SEC"
    assert resp.level == 0x01


async def test_raw_22_f1_90(transport):
    lines = transport.recv_lines()
    await lines.__anext__()  # banner

    # 0x22 (ReadDataByIdentifier) is not implemented by the mock -> NRC 0x11.
    await transport.send("6 RAW 22 F1 90")
    resp = parse_response(await lines.__anext__())
    assert resp.seq == 6
    assert resp.verb == "NRC"
    assert resp.sid == 0x22
    assert resp.nrc == 0x11
