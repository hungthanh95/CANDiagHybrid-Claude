"""Unit tests for :mod:`protocol.wire` (proto=1 wire codec).

Covers ``bytes_to_hex``/``hex_to_bytes`` round-trips and error cases,
``Command.encode()``/``parse_command`` round-trips for every client verb,
``parse_response`` round-trips for every server verb, and
:class:`SeqAllocator`.
"""

from __future__ import annotations

import pytest

from protocol.wire import (
    MAX_LINE,
    Command,
    ProtocolError,
    SeqAllocator,
    Verb,
    bytes_to_hex,
    hex_to_bytes,
    parse_command,
    parse_response,
)

# ---------------------------------------------------------------------------
# bytes_to_hex / hex_to_bytes
# ---------------------------------------------------------------------------


def test_bytes_to_hex_basic():
    assert bytes_to_hex(b"") == ""
    assert bytes_to_hex(bytes([0x00])) == "00"
    assert bytes_to_hex(bytes([0x22, 0xF1, 0x90])) == "22 F1 90"
    assert bytes_to_hex(bytes([0xFF, 0x0A])) == "FF 0A"


def test_hex_to_bytes_round_trip():
    for data in (b"", bytes([0x22, 0xF1, 0x90]), bytes(range(256))):
        assert hex_to_bytes(bytes_to_hex(data)) == data


def test_hex_to_bytes_empty_and_whitespace():
    assert hex_to_bytes("") == b""
    assert hex_to_bytes("   ") == b""


def test_hex_to_bytes_lowercase_accepted():
    # hex_to_bytes accepts both cases per its docstring (strict on token
    # *shape*, not case).
    assert hex_to_bytes("22 f1 90") == bytes([0x22, 0xF1, 0x90])
    assert hex_to_bytes("aB") == bytes([0xAB])


def test_hex_to_bytes_odd_length_token_raises():
    with pytest.raises(ValueError):
        hex_to_bytes("1")
    with pytest.raises(ValueError):
        hex_to_bytes("22 F")


def test_hex_to_bytes_non_hex_chars_raises():
    with pytest.raises(ValueError):
        hex_to_bytes("GG")
    with pytest.raises(ValueError):
        hex_to_bytes("22 ZZ")


def test_hex_to_bytes_0x_prefix_raises():
    with pytest.raises(ValueError):
        hex_to_bytes("0x22")
    with pytest.raises(ValueError):
        hex_to_bytes("0xFF")


# ---------------------------------------------------------------------------
# Command.encode() / parse_command round-trips
# ---------------------------------------------------------------------------


def test_command_round_trip_hello():
    cmd = Command(seq=1, verb=Verb.HELLO.value, args=["proto=1"])
    line = cmd.encode()
    assert line == "1 HELLO proto=1\n"
    parsed = parse_command(line)
    assert parsed.seq == 1
    assert parsed.verb == Verb.HELLO.value
    assert parsed.args == ["proto=1"]


def test_command_round_trip_session():
    cmd = Command(seq=16, verb=Verb.SESSION.value, args=["03"])
    line = cmd.encode()
    assert line == "16 SESSION 03\n"
    parsed = parse_command(line)
    assert parsed.seq == 16
    assert parsed.verb == Verb.SESSION.value
    assert parsed.args == ["03"]


def test_command_round_trip_readdtc_with_mask():
    cmd = Command(seq=12, verb=Verb.READDTC.value, args=["FF"])
    line = cmd.encode()
    assert line == "12 READDTC FF\n"
    parsed = parse_command(line)
    assert parsed.seq == 12
    assert parsed.verb == Verb.READDTC.value
    assert parsed.args == ["FF"]


def test_command_round_trip_readdtc_without_mask():
    cmd = Command(seq=12, verb=Verb.READDTC.value, args=[])
    line = cmd.encode()
    assert line == "12 READDTC\n"
    parsed = parse_command(line)
    assert parsed.seq == 12
    assert parsed.verb == Verb.READDTC.value
    assert parsed.args == []


def test_command_round_trip_cleardtc():
    cmd = Command(seq=7, verb=Verb.CLEARDTC.value)
    line = cmd.encode()
    assert line == "7 CLEARDTC\n"
    parsed = parse_command(line)
    assert parsed.seq == 7
    assert parsed.verb == Verb.CLEARDTC.value
    assert parsed.args == []


def test_command_round_trip_security():
    cmd = Command(seq=13, verb=Verb.SECURITY.value, args=["01"])
    line = cmd.encode()
    assert line == "13 SECURITY 01\n"
    parsed = parse_command(line)
    assert parsed.seq == 13
    assert parsed.verb == Verb.SECURITY.value
    assert parsed.args == ["01"]


def test_command_round_trip_tp_start_stop():
    for sub in ("START", "STOP"):
        cmd = Command(seq=15, verb=Verb.TP.value, args=[sub])
        line = cmd.encode()
        assert line == f"15 TP {sub}\n"
        parsed = parse_command(line)
        assert parsed.seq == 15
        assert parsed.verb == Verb.TP.value
        assert parsed.args == [sub]


def test_command_round_trip_raw_multiple_bytes():
    cmd = Command(
        seq=14, verb=Verb.RAW.value, args=["22", "F1", "90"], data=bytes([0x22, 0xF1, 0x90])
    )
    line = cmd.encode()
    assert line == "14 RAW 22 F1 90\n"
    parsed = parse_command(line)
    assert parsed.seq == 14
    assert parsed.verb == Verb.RAW.value
    assert parsed.args == ["22", "F1", "90"]
    assert parsed.data == bytes([0x22, 0xF1, 0x90])


def test_command_round_trip_ping():
    cmd = Command(seq=8, verb=Verb.PING.value)
    line = cmd.encode()
    assert line == "8 PING\n"
    parsed = parse_command(line)
    assert parsed.seq == 8
    assert parsed.verb == Verb.PING.value


def test_command_round_trip_bye():
    cmd = Command(seq=2, verb=Verb.BYE.value)
    line = cmd.encode()
    assert line == "2 BYE\n"
    parsed = parse_command(line)
    assert parsed.seq == 2
    assert parsed.verb == Verb.BYE.value


# ---------------------------------------------------------------------------
# parse_command error cases
# ---------------------------------------------------------------------------


def test_parse_command_empty_line_raises():
    with pytest.raises(ProtocolError):
        parse_command("")
    with pytest.raises(ProtocolError):
        parse_command("\n")
    with pytest.raises(ProtocolError):
        parse_command("   ")


def test_parse_command_non_numeric_seq_raises():
    with pytest.raises(ProtocolError):
        parse_command("abc PING\n")


def test_parse_command_line_too_long_raises():
    # MAX_LINE = 4095, build something longer than that.
    huge = "1 RAW " + " ".join(["FF"] * 2048) + "\n"
    assert len(huge) > MAX_LINE
    with pytest.raises(ProtocolError):
        parse_command(huge)


def test_parse_command_bad_raw_hex_raises():
    with pytest.raises(ProtocolError):
        parse_command("1 RAW ZZ\n")
    with pytest.raises(ProtocolError):
        parse_command("1 RAW 2\n")


def test_parse_command_unknown_verb_raises():
    with pytest.raises(ProtocolError):
        parse_command("1 FROBNICATE\n")


def test_parse_command_server_verb_rejected():
    # READY/RSP/etc are server->client verbs, not valid client commands.
    with pytest.raises(ProtocolError):
        parse_command("1 RSP 50 03\n")


# ---------------------------------------------------------------------------
# parse_response round-trips
# ---------------------------------------------------------------------------


def test_response_round_trip_ready():
    from protocol.wire import encode_ready

    line = encode_ready(0, "CANoe", "A")
    assert line == "0 READY proto=1 tool=CANoe transport=A\n"
    resp = parse_response(line)
    assert resp.seq == 0
    assert resp.verb == Verb.READY.value
    assert resp.proto == 1
    assert resp.tool == "CANoe"
    assert resp.transport == "A"


def test_response_round_trip_rsp():
    from protocol.wire import encode_rsp

    line = encode_rsp(12, bytes([0x59, 0x02, 0xFF]))
    assert line == "12 RSP 59 02 FF\n"
    resp = parse_response(line)
    assert resp.seq == 12
    assert resp.verb == Verb.RSP.value
    assert resp.data == bytes([0x59, 0x02, 0xFF])


def test_response_round_trip_nrc():
    from protocol.wire import encode_nrc

    line = encode_nrc(13, 0x27, 0x35)
    assert line == "13 NRC 27 35\n"
    resp = parse_response(line)
    assert resp.seq == 13
    assert resp.verb == Verb.NRC.value
    assert resp.sid == 0x27
    assert resp.nrc == 0x35


def test_response_round_trip_ok_tp():
    from protocol.wire import encode_ok_tp

    line = encode_ok_tp(15)
    assert line == "15 OK TP\n"
    resp = parse_response(line)
    assert resp.seq == 15
    assert resp.verb == Verb.OK.value
    assert resp.kind == "TP"


def test_response_round_trip_ok_sec():
    from protocol.wire import encode_ok_sec

    line = encode_ok_sec(13, 0x01)
    assert line == "13 OK SEC 01\n"
    resp = parse_response(line)
    assert resp.seq == 13
    assert resp.verb == Verb.OK.value
    assert resp.kind == "SEC"
    assert resp.level == 0x01


def test_response_round_trip_err():
    from protocol.wire import encode_err

    line = encode_err(0, 422, "bad_args")
    assert line == "0 ERR 422 bad_args\n"
    resp = parse_response(line)
    assert resp.seq == 0
    assert resp.verb == Verb.ERR.value
    assert resp.code == 422
    assert resp.text == "bad_args"


def test_response_round_trip_evt():
    from protocol.wire import Response

    resp_obj = Response(seq=0, verb=Verb.EVT.value, name="something", args=["a", "b"])
    line = resp_obj.encode()
    assert line == "0 EVT something a b\n"
    resp = parse_response(line)
    assert resp.seq == 0
    assert resp.verb == Verb.EVT.value
    assert resp.name == "something"
    assert resp.args == ["a", "b"]


def test_response_round_trip_pong():
    from protocol.wire import encode_pong

    line = encode_pong(8)
    assert line == "8 PONG\n"
    resp = parse_response(line)
    assert resp.seq == 8
    assert resp.verb == Verb.PONG.value


# ---------------------------------------------------------------------------
# parse_response error cases
# ---------------------------------------------------------------------------


def test_parse_response_empty_line_raises():
    with pytest.raises(ProtocolError):
        parse_response("")


def test_parse_response_non_numeric_seq_raises():
    with pytest.raises(ProtocolError):
        parse_response("abc PONG\n")


def test_parse_response_line_too_long_raises():
    huge = "0 RSP " + " ".join(["FF"] * 2048) + "\n"
    assert len(huge) > MAX_LINE
    with pytest.raises(ProtocolError):
        parse_response(huge)


def test_parse_response_nrc_requires_two_args():
    with pytest.raises(ProtocolError):
        parse_response("1 NRC 27\n")
    with pytest.raises(ProtocolError):
        parse_response("1 NRC 27 35 extra\n")


def test_parse_response_nrc_bad_hex_args():
    with pytest.raises(ProtocolError):
        parse_response("1 NRC ZZ 35\n")


def test_parse_response_client_verb_rejected():
    with pytest.raises(ProtocolError):
        parse_response("1 READDTC FF\n")


# ---------------------------------------------------------------------------
# SeqAllocator
# ---------------------------------------------------------------------------


def test_seq_allocator_starts_at_one_and_increments():
    alloc = SeqAllocator()
    assert alloc.next() == 1
    assert alloc.next() == 2
    assert alloc.next() == 3
