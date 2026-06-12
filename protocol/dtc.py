"""DTC decoding from ``19 02`` (ReadDtcInformation) response payloads.

Mirrors ``flutter_app/lib/codec/dtc.dart`` (docs/03 §6.1) — keep both in
sync if the decode algorithm ever changes (protocol/sysvar freeze rules
apply if that happens, see ``docs/04`` §1.2).
"""

from __future__ import annotations

from dataclasses import dataclass

_LETTERS = ("P", "C", "B", "U")


@dataclass
class Dtc:
    """A single decoded DTC record.

    ``code`` is the human-readable DTC string (e.g. ``"P01234"``),
    ``status`` is the raw DTCStatusMask byte, and ``(b2, b1, b0)`` are the
    original 3 DTC bytes as received on the wire.
    """

    code: str
    status: int
    b2: int
    b1: int
    b0: int


def decode_dtc(b2: int, b1: int, b0: int) -> str:
    """Decode 3 DTC bytes to a human-readable code string.

    Per ``docs/03`` §6.1:

    - Top 2 bits of ``b2`` select the letter: ``00->P``, ``01->C``,
      ``10->B``, ``11->U``.
    - Next 2 bits of ``b2`` (bits 5:4) are the first digit, ``0``-``3``.
    - The remaining 22 bits (low 6 bits of ``b2``, all of ``b1``, all of
      ``b0``) are rendered as 4 uppercase hex digits, zero-padded.

    Implemented faithfully to the §6.1 sketch: the result is
    ``letter + str(d1) + 4-hex-digit(rest)``, e.g.
    ``b2=0x00, b1=0x12, b0=0x34`` -> ``"P01234"``. This is a 6-character
    code (not the conventional 5-character ``P0123`` form); do not
    "correct" it without a protocol/codec review (see task note).
    """
    letter = _LETTERS[(b2 >> 6) & 0x03]
    d1 = (b2 >> 4) & 0x03
    rest = ((b2 & 0x3F) << 16) | (b1 << 8) | b0
    return f"{letter}{d1}{rest:04X}"


def parse_read_dtc_payload(payload: bytes) -> tuple[int, list[Dtc]]:
    """Parse a full ``59 02 <availabilityMask> [<b2><b1><b0><status>]...`` payload.

    Returns ``(availability_mask, [Dtc, ...])``. Raises ``ValueError`` if
    the payload is too short, has the wrong SID/sub-function, or has a
    truncated trailing record.
    """
    if len(payload) < 3:
        raise ValueError(f"READDTC payload too short: {payload!r}")
    if payload[0] != 0x59 or payload[1] != 0x02:
        raise ValueError(f"not a 59 02 payload: {payload[:2].hex().upper()}")

    availability_mask = payload[2]
    body = payload[3:]
    if len(body) % 4 != 0:
        raise ValueError(f"truncated DTC record(s): {len(body)} trailing bytes")

    dtcs: list[Dtc] = []
    for i in range(0, len(body), 4):
        b2, b1, b0, status = body[i : i + 4]
        dtcs.append(Dtc(code=decode_dtc(b2, b1, b0), status=status, b2=b2, b1=b1, b0=b0))

    return availability_mask, dtcs
