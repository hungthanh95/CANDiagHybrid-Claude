"""FlexDiag shared wire-protocol codec (proto=1).

This package is the single source of truth for encoding and parsing the
line-based ASCII protocol described in ``docs/03-TECHNICAL-DETAIL.md`` §1.
Both ``mock_ecu`` and ``terminal`` import from here; do not re-implement
framing logic elsewhere (see ``docs/04-RULES-AND-CONVENTIONS.md`` §3.5).
"""

from protocol.wire import (
    CLIENT_VERBS,
    MAX_LINE,
    PROTO,
    Command,
    ProtocolError,
    Response,
    SeqAllocator,
    Verb,
    bytes_to_hex,
    encode_err,
    encode_nrc,
    encode_ok_sec,
    encode_ok_tp,
    encode_pong,
    encode_ready,
    encode_rsp,
    hex_to_bytes,
    parse_command,
    parse_response,
)

__all__ = [
    "CLIENT_VERBS",
    "MAX_LINE",
    "PROTO",
    "Command",
    "ProtocolError",
    "Response",
    "SeqAllocator",
    "Verb",
    "bytes_to_hex",
    "encode_err",
    "encode_nrc",
    "encode_ok_sec",
    "encode_ok_tp",
    "encode_pong",
    "encode_ready",
    "encode_rsp",
    "hex_to_bytes",
    "parse_command",
    "parse_response",
]
