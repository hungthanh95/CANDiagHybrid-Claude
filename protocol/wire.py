"""Wire-protocol codec for FlexDiag proto=1.

Implements the line-based ASCII protocol from ``docs/03-TECHNICAL-DETAIL.md``
§1: one message per line, ``<SEQ> <VERB> [args...]\\n``, hex bytes uppercase
space-separated with no ``0x`` prefix.

This module is the single parser/encoder for the protocol in Python; both
``mock_ecu`` and ``terminal`` must import from here (see
``docs/04-RULES-AND-CONVENTIONS.md`` §3.5 — one protocol parser per language).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

PROTO = 1

# Maximum line length in bytes, including the trailing newline. Matches
# `kMaxLen` in `flexdiag_core.can` (docs/03 §3.1) and the RAW byte payload
# cap (docs/03 §1.5).
MAX_LINE = 4095


class ProtocolError(ValueError):
    """Raised when a wire-protocol line is malformed or violates grammar."""


class Verb(str, Enum):
    """Protocol verbs (docs/03 §1.2 client->server, §1.3 server->client)."""

    # Client -> server
    HELLO = "HELLO"
    SESSION = "SESSION"
    READDTC = "READDTC"
    CLEARDTC = "CLEARDTC"
    SECURITY = "SECURITY"
    TP = "TP"
    RAW = "RAW"
    PING = "PING"
    BYE = "BYE"

    # Server -> client
    READY = "READY"
    RSP = "RSP"
    NRC = "NRC"
    OK = "OK"
    ERR = "ERR"
    EVT = "EVT"
    PONG = "PONG"


CLIENT_VERBS = {
    Verb.HELLO,
    Verb.SESSION,
    Verb.READDTC,
    Verb.CLEARDTC,
    Verb.SECURITY,
    Verb.TP,
    Verb.RAW,
    Verb.PING,
    Verb.BYE,
}

# Backwards-compatible alias (kept private for any in-module callers).
_CLIENT_VERBS = CLIENT_VERBS

_SERVER_VERBS = {
    Verb.READY,
    Verb.RSP,
    Verb.NRC,
    Verb.OK,
    Verb.ERR,
    Verb.EVT,
    Verb.PONG,
}


def bytes_to_hex(b: bytes) -> str:
    """Encode bytes as uppercase, space-separated hex (no ``0x``)."""
    return " ".join(f"{byte:02X}" for byte in b)


def hex_to_bytes(s: str) -> bytes:
    """Decode space-separated hex bytes (e.g. ``"22 F1 90"``) to ``bytes``.

    Strict: each token must be exactly two hex digits. Raises
    ``ValueError`` on malformed input (odd-length tokens, non-hex
    characters, etc.). Empty input (or whitespace-only) yields ``b""``.
    """
    tokens = s.split()
    out = bytearray()
    for tok in tokens:
        if len(tok) != 2 or not all(c in "0123456789abcdefABCDEF" for c in tok):
            raise ValueError(f"invalid hex byte: {tok!r}")
        out.append(int(tok, 16))
    return bytes(out)


@dataclass
class Command:
    """A client -> server command line.

    ``args`` holds the verb-specific arguments as raw tokens (strings),
    in the order they appeared on the wire. For ``RAW``, ``data`` holds
    the decoded byte payload (also derivable from ``args`` via
    ``hex_to_bytes(" ".join(args))``, but precomputed for convenience).
    """

    seq: int
    verb: str
    args: list[str] = field(default_factory=list)
    data: bytes | None = None

    def encode(self) -> str:
        """Render as a single protocol line, including the trailing ``\\n``."""
        parts = [str(self.seq), self.verb, *self.args]
        line = " ".join(parts) + "\n"
        if len(line) > MAX_LINE:
            raise ProtocolError(f"encoded command exceeds MAX_LINE: {len(line)}")
        return line


@dataclass
class Response:
    """A server -> client response line.

    Only the fields relevant to ``verb`` are populated; the rest stay at
    their default (``None`` / empty). See the "Response shapes" table in
    the M1 task spec / ``docs/03`` §1.3 for which fields apply to which
    verb.
    """

    seq: int
    verb: str

    # READY
    proto: int | None = None
    tool: str | None = None
    transport: Literal["A", "B"] | None = None

    # RSP
    data: bytes | None = None

    # NRC
    sid: int | None = None
    nrc: int | None = None

    # OK
    kind: Literal["TP", "SEC"] | None = None
    level: int | None = None

    # ERR
    code: int | None = None
    text: str | None = None

    # EVT
    name: str | None = None
    args: list[str] = field(default_factory=list)

    def encode(self) -> str:
        """Render as a single protocol line, including the trailing ``\\n``."""
        verb = self.verb
        if verb == Verb.READY:
            line = (
                f"{self.seq} READY proto={self.proto} "
                f"tool={self.tool} transport={self.transport}"
            )
        elif verb == Verb.RSP:
            assert self.data is not None
            line = f"{self.seq} RSP {bytes_to_hex(self.data)}"
        elif verb == Verb.NRC:
            assert self.sid is not None and self.nrc is not None
            line = f"{self.seq} NRC {self.sid:02X} {self.nrc:02X}"
        elif verb == Verb.OK:
            if self.kind == "TP":
                line = f"{self.seq} OK TP"
            elif self.kind == "SEC":
                assert self.level is not None
                line = f"{self.seq} OK SEC {self.level:02X}"
            else:
                raise ProtocolError(f"OK response missing/invalid kind: {self.kind!r}")
        elif verb == Verb.ERR:
            assert self.code is not None and self.text is not None
            line = f"{self.seq} ERR {self.code} {self.text}"
        elif verb == Verb.EVT:
            assert self.name is not None
            parts = [str(self.seq), "EVT", self.name, *self.args]
            line = " ".join(parts)
        elif verb == Verb.PONG:
            line = f"{self.seq} PONG"
        else:
            raise ProtocolError(f"cannot encode unknown response verb: {verb!r}")

        line += "\n"
        if len(line) > MAX_LINE:
            raise ProtocolError(f"encoded response exceeds MAX_LINE: {len(line)}")
        return line


def _split_line(line: str) -> tuple[int | None, str, list[str], str]:
    """Strip newline/whitespace and split into (seq, verb, rest_tokens, raw).

    Tolerant of extra leading/trailing/internal whitespace. Raises
    ``ProtocolError`` if the line is too long, empty, or missing a verb.
    Returns ``seq=None`` if the seq token is not a valid non-negative
    integer (caller decides how to handle, per spec "use seq 0 if seq
    cannot be parsed").
    """
    if len(line) > MAX_LINE:
        raise ProtocolError("line exceeds MAX_LINE")

    stripped = line.strip("\r\n")
    tokens = stripped.split()
    if len(tokens) < 2:
        raise ProtocolError(f"malformed line (need at least SEQ and VERB): {line!r}")

    seq_tok, verb_tok, *rest = tokens
    try:
        seq: int | None = int(seq_tok, 10)
        if seq < 0:
            seq = None
    except ValueError:
        seq = None

    return seq, verb_tok, rest, stripped


def parse_command(line: str) -> Command:
    """Parse a client -> server command line.

    Raises ``ProtocolError`` on malformed input (bad seq, unknown verb for
    this direction, bad hex for ``RAW``). Tolerant of extra whitespace.
    """
    seq, verb_tok, rest, _ = _split_line(line)
    if seq is None:
        raise ProtocolError(f"malformed seq: {line!r}")

    verb_upper = verb_tok.upper()
    try:
        verb = Verb(verb_upper)
    except ValueError as exc:
        raise ProtocolError(f"unknown verb: {verb_tok!r}") from exc

    if verb not in CLIENT_VERBS:
        raise ProtocolError(f"not a client verb: {verb_tok!r}")

    data: bytes | None = None
    if verb == Verb.RAW:
        try:
            data = hex_to_bytes(" ".join(rest))
        except ValueError as exc:
            raise ProtocolError(f"bad RAW hex payload: {exc}") from exc

    return Command(seq=seq, verb=verb.value, args=rest, data=data)


def parse_response(line: str) -> Response:
    """Parse a server -> client response line.

    Raises ``ProtocolError`` on malformed input. Tolerant of extra
    whitespace, strict on grammar per verb.
    """
    seq, verb_tok, rest, _ = _split_line(line)
    if seq is None:
        raise ProtocolError(f"malformed seq: {line!r}")

    verb_upper = verb_tok.upper()
    try:
        verb = Verb(verb_upper)
    except ValueError as exc:
        raise ProtocolError(f"unknown verb: {verb_tok!r}") from exc

    if verb not in _SERVER_VERBS:
        raise ProtocolError(f"not a server verb: {verb_tok!r}")

    if verb == Verb.READY:
        # "proto=1 tool=<...> transport=<A|B>"
        kv: dict[str, str] = {}
        for tok in rest:
            if "=" not in tok:
                raise ProtocolError(f"malformed READY arg: {tok!r}")
            key, _, val = tok.partition("=")
            kv[key] = val
        try:
            proto = int(kv["proto"])
            tool = kv["tool"]
            transport_val = kv["transport"]
        except KeyError as exc:
            raise ProtocolError(f"missing READY field: {exc}") from exc
        if transport_val not in ("A", "B"):
            raise ProtocolError(f"invalid READY transport: {transport_val!r}")
        return Response(
            seq=seq,
            verb=verb.value,
            proto=proto,
            tool=tool,
            transport=transport_val,  # type: ignore[arg-type]
        )

    if verb == Verb.RSP:
        try:
            data = hex_to_bytes(" ".join(rest))
        except ValueError as exc:
            raise ProtocolError(f"bad RSP hex payload: {exc}") from exc
        return Response(seq=seq, verb=verb.value, data=data)

    if verb == Verb.NRC:
        if len(rest) != 2:
            raise ProtocolError(f"NRC requires exactly 2 args, got {rest!r}")
        try:
            sid = int(rest[0], 16)
            nrc = int(rest[1], 16)
        except ValueError as exc:
            raise ProtocolError(f"bad NRC hex args: {rest!r}") from exc
        return Response(seq=seq, verb=verb.value, sid=sid, nrc=nrc)

    if verb == Verb.OK:
        if not rest:
            raise ProtocolError("OK requires at least one arg")
        what = rest[0].upper()
        if what == "TP":
            if len(rest) != 1:
                raise ProtocolError(f"OK TP takes no extra args, got {rest!r}")
            return Response(seq=seq, verb=verb.value, kind="TP")
        if what == "SEC":
            if len(rest) != 2:
                raise ProtocolError(f"OK SEC requires a level arg, got {rest!r}")
            try:
                level = int(rest[1], 16)
            except ValueError as exc:
                raise ProtocolError(f"bad OK SEC level: {rest[1]!r}") from exc
            return Response(seq=seq, verb=verb.value, kind="SEC", level=level)
        raise ProtocolError(f"unknown OK kind: {rest[0]!r}")

    if verb == Verb.ERR:
        if len(rest) < 2:
            raise ProtocolError(f"ERR requires code and text, got {rest!r}")
        try:
            code = int(rest[0], 10)
        except ValueError as exc:
            raise ProtocolError(f"bad ERR code: {rest[0]!r}") from exc
        text = " ".join(rest[1:])
        return Response(seq=seq, verb=verb.value, code=code, text=text)

    if verb == Verb.EVT:
        if not rest:
            raise ProtocolError("EVT requires a name")
        return Response(seq=seq, verb=verb.value, name=rest[0], args=rest[1:])

    if verb == Verb.PONG:
        if rest:
            raise ProtocolError(f"PONG takes no args, got {rest!r}")
        return Response(seq=seq, verb=verb.value)

    raise ProtocolError(f"cannot parse unknown response verb: {verb!r}")


# ---------------------------------------------------------------------------
# Mock-side encoders: build response lines directly without constructing a
# Response dataclass first. Convenience wrappers used by mock_ecu's framing.
# ---------------------------------------------------------------------------


def encode_rsp(seq: int, data: bytes) -> str:
    """``<seq> RSP <hex bytes>``"""
    return Response(seq=seq, verb=Verb.RSP.value, data=data).encode()


def encode_nrc(seq: int, sid: int, nrc: int) -> str:
    """``<seq> NRC <sid_hex> <nrc_hex>``"""
    return Response(seq=seq, verb=Verb.NRC.value, sid=sid, nrc=nrc).encode()


def encode_ok_tp(seq: int) -> str:
    """``<seq> OK TP``"""
    return Response(seq=seq, verb=Verb.OK.value, kind="TP").encode()


def encode_ok_sec(seq: int, level: int) -> str:
    """``<seq> OK SEC <level_hex>``"""
    return Response(seq=seq, verb=Verb.OK.value, kind="SEC", level=level).encode()


def encode_err(seq: int, code: int, text: str) -> str:
    """``<seq> ERR <code> <text>``"""
    return Response(seq=seq, verb=Verb.ERR.value, code=code, text=text).encode()


def encode_ready(seq: int, tool: str, transport: str) -> str:
    """``<seq> READY proto=1 tool=<tool> transport=<A|B>``"""
    return Response(
        seq=seq,
        verb=Verb.READY.value,
        proto=PROTO,
        tool=tool,
        transport=transport,  # type: ignore[arg-type]
    ).encode()


def encode_pong(seq: int) -> str:
    """``<seq> PONG``"""
    return Response(seq=seq, verb=Verb.PONG.value).encode()


class SeqAllocator:
    """Monotonic per-connection sequence id allocator.

    ``seq=0`` is reserved for unsolicited/async (``EVT``) messages per
    docs/03 §1.1, so allocation starts at 1.
    """

    def __init__(self) -> None:
        self._next = 1

    def next(self) -> int:
        seq = self._next
        self._next += 1
        return seq
