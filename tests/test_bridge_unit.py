"""Unit tests for :mod:`bridge.flexdiag_bridge` (Option B bridge core).

Covers (FR-11 "Option B transport" / FR-12 "identical protocol both
transports", docs/03 §2/§4.2):

- :class:`FakeVectorCom` dispatch for all 7 ``ReqKind`` values (RAW,
  READDTC, CLEARDTC, SECURITY full seed/key unlock, SESSION, TP START/STOP),
  mirroring ``tests/test_mock_uds.py``'s direct ``Ecu.handle`` coverage but
  through the ``cmd_q``/``evt_q`` interface.
- :func:`encode_response`'s ``RspStatus`` 0-4 -> wire-line mapping, including
  ``OK SEC <level>`` derivation (``level = data[1] - 1``) and the
  ``ERR 500 keygen_fail`` / ``ERR 504 ecu_timeout`` synthetic statuses.
- The WS-facing ``_dispatch_line``/``handle`` ERR-400-vs-422 behavior
  (unknown verb, bad hex, bad arg range), mirroring
  ``mock_ecu/server.py``'s dispatch tests in ``tests/test_server_negatives.py``.
"""

from __future__ import annotations

import pytest

from bridge.flexdiag_bridge import (
    KIND_CLEARDTC,
    KIND_RAW,
    KIND_READDTC,
    KIND_SECURITY,
    KIND_SESSION,
    KIND_TP_START,
    KIND_TP_STOP,
    STATUS_ERR_KEYGEN,
    STATUS_ERR_TIMEOUT,
    STATUS_NEGATIVE,
    STATUS_OK,
    STATUS_POSITIVE,
    BridgeServer,
    FakeVectorCom,
    encode_response,
)
from protocol.wire import parse_response
from terminal.transport_ws import WsTransport

# ---------------------------------------------------------------------------
# FakeVectorCom._dispatch -- one test per ReqKind
# ---------------------------------------------------------------------------


def test_dispatch_raw():
    vec = FakeVectorCom()
    vec.start()
    try:
        vec.cmd_q.put((1, KIND_RAW, 0, bytes([0x10, 0x03])))
        seq, status, kind, data = vec.evt_q.get(timeout=5)
        assert seq == 1
        assert status == STATUS_POSITIVE
        assert kind == KIND_RAW
        assert data[:2] == bytes([0x50, 0x03])
    finally:
        vec.stop()


def test_dispatch_readdtc():
    vec = FakeVectorCom()
    vec.start()
    try:
        vec.cmd_q.put((2, KIND_READDTC, 0xFF, None))
        seq, status, kind, data = vec.evt_q.get(timeout=5)
        assert seq == 2
        assert status == STATUS_POSITIVE
        assert kind == KIND_READDTC
        assert data[:3] == bytes([0x59, 0x02, 0xFF])
        assert data[3:] == bytes([0x00, 0x12, 0x34, 0x2F, 0x00, 0x56, 0x78, 0x08])
    finally:
        vec.stop()


def test_dispatch_cleardtc():
    vec = FakeVectorCom()
    vec.start()
    try:
        vec.cmd_q.put((3, KIND_CLEARDTC, 0, None))
        seq, status, kind, data = vec.evt_q.get(timeout=5)
        assert seq == 3
        assert status == STATUS_POSITIVE
        assert kind == KIND_CLEARDTC
        assert data == bytes([0x54])
    finally:
        vec.stop()


def test_dispatch_session():
    vec = FakeVectorCom()
    vec.start()
    try:
        vec.cmd_q.put((4, KIND_SESSION, 0x03, None))
        seq, status, kind, data = vec.evt_q.get(timeout=5)
        assert seq == 4
        assert status == STATUS_POSITIVE
        assert kind == KIND_SESSION
        assert data[:2] == bytes([0x50, 0x03])
        assert vec.ecu.session == 0x03
    finally:
        vec.stop()


def test_dispatch_security_full_unlock():
    vec = FakeVectorCom()
    vec.start()
    try:
        vec.cmd_q.put((5, KIND_SECURITY, 0x01, None))
        seq, status, kind, data = vec.evt_q.get(timeout=5)
        assert seq == 5
        assert status == STATUS_OK
        assert kind == KIND_SECURITY
        # key_rsp = 67 <evenLevel> -> data[1] == 0x02
        assert data == bytes([0x67, 0x02])
        assert vec.ecu.unlocked is True
    finally:
        vec.stop()


def test_dispatch_tp_start():
    vec = FakeVectorCom()
    vec.start()
    try:
        vec.cmd_q.put((6, KIND_TP_START, 0, None))
        seq, status, kind, data = vec.evt_q.get(timeout=5)
        assert seq == 6
        assert status == STATUS_OK
        assert kind == KIND_TP_START
        assert data == b""
    finally:
        vec.stop()


def test_dispatch_tp_stop():
    vec = FakeVectorCom()
    vec.start()
    try:
        vec.cmd_q.put((7, KIND_TP_STOP, 0, None))
        seq, status, kind, data = vec.evt_q.get(timeout=5)
        assert seq == 7
        assert status == STATUS_OK
        assert kind == KIND_TP_STOP
        assert data == b""
    finally:
        vec.stop()


# ---------------------------------------------------------------------------
# encode_response -- RspStatus 0-4 -> wire-line mapping
# ---------------------------------------------------------------------------


def test_encode_response_positive_rsp():
    line = encode_response(1, STATUS_POSITIVE, KIND_RAW, bytes([0x50, 0x03]))
    assert line == "1 RSP 50 03\n"


def test_encode_response_negative_nrc():
    line = encode_response(2, STATUS_NEGATIVE, KIND_READDTC, bytes([0x7F, 0x19, 0x31]))
    resp = parse_response(line)
    assert resp.verb == "NRC"
    assert resp.sid == 0x19
    assert resp.nrc == 0x31


def test_encode_response_negative_nrc_short_data_defaults_zero():
    # data shorter than 3 bytes -> sid/nrc default to 0 per docstring.
    line = encode_response(3, STATUS_NEGATIVE, KIND_RAW, bytes([0x7F]))
    resp = parse_response(line)
    assert resp.verb == "NRC"
    assert resp.sid == 0
    assert resp.nrc == 0


def test_encode_response_ok_tp_for_kind_5_and_6():
    for kind in (KIND_TP_START, KIND_TP_STOP):
        line = encode_response(4, STATUS_OK, kind, b"")
        resp = parse_response(line)
        assert resp.verb == "OK"
        assert resp.kind == "TP"


def test_encode_response_ok_sec_derives_odd_level():
    # data = 67 <evenLevel>; level = evenLevel - 1.
    line = encode_response(5, STATUS_OK, KIND_SECURITY, bytes([0x67, 0x02]))
    resp = parse_response(line)
    assert resp.verb == "OK"
    assert resp.kind == "SEC"
    assert resp.level == 0x01


def test_encode_response_ok_sec_missing_data_defaults_zero_level():
    # data shorter than 2 bytes -> even_level defaults to 0 -> odd_level
    # wraps to 0xFF (per (-1) & 0xFF).
    line = encode_response(6, STATUS_OK, KIND_SECURITY, bytes([0x67]))
    resp = parse_response(line)
    assert resp.verb == "OK"
    assert resp.kind == "SEC"
    assert resp.level == 0xFF


def test_encode_response_err_keygen_fail():
    line = encode_response(7, STATUS_ERR_KEYGEN, KIND_SECURITY, b"")
    resp = parse_response(line)
    assert resp.verb == "ERR"
    assert resp.code == 500
    assert resp.text == "keygen_fail"


def test_encode_response_err_ecu_timeout():
    line = encode_response(8, STATUS_ERR_TIMEOUT, KIND_RAW, b"")
    resp = parse_response(line)
    assert resp.verb == "ERR"
    assert resp.code == 504
    assert resp.text == "ecu_timeout"


def test_encode_response_unknown_status_raises():
    with pytest.raises(ValueError):
        encode_response(9, 99, KIND_RAW, b"")


# ---------------------------------------------------------------------------
# Byte-accuracy (NFR-4): client request bytes -> bytes dispatched to the ECU
# ---------------------------------------------------------------------------
#
# The bridge's only transformation of a RAW request is
# protocol.wire.hex_to_bytes(); for READDTC/CLEARDTC/SECURITY/SESSION it
# constructs the UDS request bytes from (kind, arg). In both cases
# FakeVectorCom._dispatch hands those bytes directly to Ecu.handle(), which
# is what flexdiag_sysvar.can + flexdiag_core.can would write to
# Diag::ReqData / send on the bus (docs/03 §4). These tests pin that mapping
# byte-for-byte for one request per RAW/READDTC/CLEARDTC/SESSION.


def test_raw_request_bytes_match_wire_hex():
    """``RAW 22 F1 90`` -> cmd_q data == bytes([0x22, 0xF1, 0x90]) (exact)."""
    from protocol.wire import hex_to_bytes, parse_command

    cmd = parse_command("1 RAW 22 F1 90")
    assert cmd.data == bytes([0x22, 0xF1, 0x90])
    assert cmd.data == hex_to_bytes("22 F1 90")

    vec = FakeVectorCom()
    vec.start()
    try:
        vec.cmd_q.put((cmd.seq, KIND_RAW, 0, cmd.data))
        seq, status, kind, data = vec.evt_q.get(timeout=5)
        # 0x22 is unimplemented by the mock ECU -> NRC 22 11, but the
        # dispatched *request* SID (echoed in the NRC) confirms the exact
        # request bytes reached Ecu.handle unchanged.
        assert seq == 1
        assert status == STATUS_NEGATIVE
        assert data == bytes([0x7F, 0x22, 0x11])
    finally:
        vec.stop()


def test_readdtc_request_bytes_are_19_02_mask():
    """``READDTC FF`` -> dispatched UDS request is exactly ``19 02 FF``."""
    vec = FakeVectorCom()
    vec.start()
    try:
        vec.cmd_q.put((2, KIND_READDTC, 0xFF, None))
        seq, status, kind, data = vec.evt_q.get(timeout=5)
        assert seq == 2
        assert status == STATUS_POSITIVE
        # rsp[:3] echoes the request SID/subfunction/mask: 59 02 FF.
        assert data[:3] == bytes([0x59, 0x02, 0xFF])
    finally:
        vec.stop()


def test_cleardtc_request_bytes_are_14_ff_ff_ff():
    """``CLEARDTC`` -> dispatched UDS request is exactly ``14 FF FF FF``."""
    vec = FakeVectorCom()
    vec.start()
    try:
        vec.cmd_q.put((3, KIND_CLEARDTC, 0, None))
        seq, status, kind, data = vec.evt_q.get(timeout=5)
        assert seq == 3
        assert status == STATUS_POSITIVE
        assert data == bytes([0x54])  # positive response to 14 FF FF FF
    finally:
        vec.stop()


def test_session_request_bytes_are_10_sub():
    """``SESSION 03`` -> dispatched UDS request is exactly ``10 03``."""
    vec = FakeVectorCom()
    vec.start()
    try:
        vec.cmd_q.put((4, KIND_SESSION, 0x03, None))
        seq, status, kind, data = vec.evt_q.get(timeout=5)
        assert seq == 4
        assert status == STATUS_POSITIVE
        assert data[:2] == bytes([0x50, 0x03])  # positive response to 10 03
    finally:
        vec.stop()


# ---------------------------------------------------------------------------
# WS front-end: ERR 400 (unknown verb) vs ERR 422 (bad args)
# ---------------------------------------------------------------------------


@pytest.fixture
def bridge_server():
    srv = BridgeServer(host="127.0.0.1", port=0)
    srv.start()
    try:
        yield srv
    finally:
        srv.stop()


@pytest.fixture
async def ws(bridge_server):
    t = WsTransport("127.0.0.1", bridge_server.bound_port)
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


async def test_unknown_verb_err_400(ws):
    lines = ws.recv_lines()
    await _drain_banner(lines)

    await ws.send("5 FROBNICATE")
    resp = parse_response(await lines.__anext__())
    assert resp.seq == 5
    assert resp.verb == "ERR"
    assert resp.code == 400
    assert resp.text == "unknown_verb"

    # Peer stays alive.
    await ws.send("1 PING")
    resp2 = parse_response(await lines.__anext__())
    assert resp2.seq == 1
    assert resp2.verb == "PONG"


async def test_malformed_single_token_bad_args(ws):
    lines = ws.recv_lines()
    await _drain_banner(lines)

    await ws.send("garbage")
    resp = parse_response(await lines.__anext__())
    assert resp.seq == 0
    assert resp.verb == "ERR"
    assert resp.code == 422
    assert resp.text == "bad_args"

    await ws.send("1 PING")
    resp2 = parse_response(await lines.__anext__())
    assert resp2.seq == 1
    assert resp2.verb == "PONG"


async def test_multi_token_garbage_is_unknown_verb(ws):
    lines = ws.recv_lines()
    await _drain_banner(lines)

    await ws.send("not a real command")
    resp = parse_response(await lines.__anext__())
    assert resp.seq == 0
    assert resp.verb == "ERR"
    assert resp.code == 400
    assert resp.text == "unknown_verb"


async def test_raw_bad_hex_is_bad_args(ws):
    lines = ws.recv_lines()
    await _drain_banner(lines)

    await ws.send("2 RAW ZZ")
    resp = parse_response(await lines.__anext__())
    assert resp.seq == 2
    assert resp.verb == "ERR"
    assert resp.code == 422
    assert resp.text == "bad_args"


async def test_raw_no_data_is_bad_args(ws):
    lines = ws.recv_lines()
    await _drain_banner(lines)

    await ws.send("3 RAW")
    resp = parse_response(await lines.__anext__())
    assert resp.seq == 3
    assert resp.verb == "ERR"
    assert resp.code == 422
    assert resp.text == "bad_args"


async def test_session_out_of_range_is_bad_args(ws):
    lines = ws.recv_lines()
    await _drain_banner(lines)

    await ws.send("4 SESSION 100")
    resp = parse_response(await lines.__anext__())
    assert resp.seq == 4
    assert resp.verb == "ERR"
    assert resp.code == 422
    assert resp.text == "bad_args"


async def test_readdtc_bad_mask_is_bad_args(ws):
    lines = ws.recv_lines()
    await _drain_banner(lines)

    await ws.send("5 READDTC ZZ")
    resp = parse_response(await lines.__anext__())
    assert resp.seq == 5
    assert resp.verb == "ERR"
    assert resp.code == 422
    assert resp.text == "bad_args"


async def test_readdtc_too_many_args_is_bad_args(ws):
    lines = ws.recv_lines()
    await _drain_banner(lines)

    await ws.send("6 READDTC FF FF")
    resp = parse_response(await lines.__anext__())
    assert resp.seq == 6
    assert resp.verb == "ERR"
    assert resp.code == 422
    assert resp.text == "bad_args"


async def test_cleardtc_with_args_is_bad_args(ws):
    lines = ws.recv_lines()
    await _drain_banner(lines)

    await ws.send("7 CLEARDTC FF")
    resp = parse_response(await lines.__anext__())
    assert resp.seq == 7
    assert resp.verb == "ERR"
    assert resp.code == 422
    assert resp.text == "bad_args"


async def test_security_bad_level_is_bad_args(ws):
    lines = ws.recv_lines()
    await _drain_banner(lines)

    await ws.send("8 SECURITY GG")
    resp = parse_response(await lines.__anext__())
    assert resp.seq == 8
    assert resp.verb == "ERR"
    assert resp.code == 422
    assert resp.text == "bad_args"


async def test_tp_bad_arg_is_bad_args(ws):
    lines = ws.recv_lines()
    await _drain_banner(lines)

    await ws.send("9 TP SIDEWAYS")
    resp = parse_response(await lines.__anext__())
    assert resp.seq == 9
    assert resp.verb == "ERR"
    assert resp.code == 422
    assert resp.text == "bad_args"


async def test_bye_closes_connection(ws):
    lines = ws.recv_lines()
    await _drain_banner(lines)

    await ws.send("10 BYE")
    with pytest.raises(StopAsyncIteration):
        await lines.__anext__()
