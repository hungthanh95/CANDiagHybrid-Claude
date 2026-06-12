"""Unit tests for :mod:`protocol.dtc` (DTC decode from ``59 02`` payloads).

Per ``docs/03-TECHNICAL-DETAIL.md`` §6.1. Note: ``decode_dtc`` currently
produces a 6-character code (e.g. ``"P01234"``) per the literal §6.1
sketch, not the conventional 5-character ISO 15031-6 form (``"P0123"``).
These tests pin that *current* behaviour so a future fix is a deliberate,
reviewed change rather than a silent regression.
"""

from __future__ import annotations

import pytest

from protocol.dtc import Dtc, decode_dtc, parse_read_dtc_payload

# ---------------------------------------------------------------------------
# decode_dtc letter selection
# ---------------------------------------------------------------------------


def test_decode_dtc_letter_p():
    # top 2 bits 00 -> P
    assert decode_dtc(0x00, 0x12, 0x34).startswith("P")


def test_decode_dtc_letter_c():
    # top 2 bits 01 -> C
    assert decode_dtc(0x40, 0x00, 0x00).startswith("C")


def test_decode_dtc_letter_b():
    # top 2 bits 10 -> B
    assert decode_dtc(0x80, 0x00, 0x00).startswith("B")


def test_decode_dtc_letter_u():
    # top 2 bits 11 -> U
    assert decode_dtc(0xC0, 0x00, 0x00).startswith("U")


# ---------------------------------------------------------------------------
# decode_dtc literal §6.1 sketch behaviour
# ---------------------------------------------------------------------------


def test_decode_dtc_canonical_example():
    # (0x00, 0x12, 0x34) -> letter=P, d1=(0x00>>4)&0x03=0, rest=((0x00&0x3F)<<16)|0x1234=0x1234
    # -> "P0" + "1234" -> "P01234" (6-char form, per current code).
    assert decode_dtc(0x00, 0x12, 0x34) == "P01234"


def test_decode_dtc_second_canonical_example():
    # (0x00, 0x56, 0x78) -> "P0" + "5678" -> "P05678"
    assert decode_dtc(0x00, 0x56, 0x78) == "P05678"


# ---------------------------------------------------------------------------
# parse_read_dtc_payload on the canonical mock output
# ---------------------------------------------------------------------------


def test_parse_read_dtc_payload_canonical():
    # 59 02 FF 00 12 34 2F 00 56 78 08
    payload = bytes([0x59, 0x02, 0xFF, 0x00, 0x12, 0x34, 0x2F, 0x00, 0x56, 0x78, 0x08])
    mask, dtcs = parse_read_dtc_payload(payload)
    assert mask == 0xFF
    assert len(dtcs) == 2

    d0, d1 = dtcs
    assert isinstance(d0, Dtc)
    assert (d0.b2, d0.b1, d0.b0, d0.status) == (0x00, 0x12, 0x34, 0x2F)
    assert d0.code == decode_dtc(0x00, 0x12, 0x34)
    assert d0.code == "P01234"

    assert (d1.b2, d1.b1, d1.b0, d1.status) == (0x00, 0x56, 0x78, 0x08)
    assert d1.code == decode_dtc(0x00, 0x56, 0x78)
    assert d1.code == "P05678"


def test_parse_read_dtc_payload_empty_dtc_list():
    payload = bytes([0x59, 0x02, 0xFF])
    mask, dtcs = parse_read_dtc_payload(payload)
    assert mask == 0xFF
    assert dtcs == []


def test_parse_read_dtc_payload_max_length():
    # A large number of synthetic DTC records; should decode without error.
    n = 1000
    body = bytearray()
    for i in range(n):
        body += bytes([(i >> 16) & 0xFF, (i >> 8) & 0xFF, i & 0xFF, 0xFF])
    payload = bytes([0x59, 0x02, 0xFF]) + bytes(body)
    mask, dtcs = parse_read_dtc_payload(payload)
    assert mask == 0xFF
    assert len(dtcs) == n
    # status byte 0xFF -> all status bits set
    assert all(d.status == 0xFF for d in dtcs)


# ---------------------------------------------------------------------------
# parse_read_dtc_payload error cases
# ---------------------------------------------------------------------------


def test_parse_read_dtc_payload_truncated_only_sid_subfunction():
    with pytest.raises(ValueError):
        parse_read_dtc_payload(bytes([0x59, 0x02]))


def test_parse_read_dtc_payload_truncated_partial_record():
    # 3 (header incl. mask) + 3 trailing bytes -> a partial/truncated DTC
    # record (not a multiple of 4). NB: bytes([0x59, 0x02, 0xFF]) (3 bytes,
    # just the mask with zero DTCs) is itself VALID -- see
    # test_parse_read_dtc_payload_empty_dtc_list above.
    with pytest.raises(ValueError):
        parse_read_dtc_payload(bytes([0x59, 0x02, 0xFF, 0x00, 0x12, 0x34]))  # 3 trailing bytes


def test_parse_read_dtc_payload_wrong_leading_byte():
    with pytest.raises(ValueError):
        parse_read_dtc_payload(bytes([0x49, 0x02, 0xFF]))
    with pytest.raises(ValueError):
        parse_read_dtc_payload(bytes([0x59, 0x01, 0xFF]))


def test_parse_read_dtc_payload_wrong_length_not_multiple_of_four():
    # 3 (header) + 5 trailing bytes -> not 3 + 4*N
    payload = bytes([0x59, 0x02, 0xFF, 0x00, 0x12, 0x34, 0x2F, 0x00])
    with pytest.raises(ValueError):
        parse_read_dtc_payload(payload)
